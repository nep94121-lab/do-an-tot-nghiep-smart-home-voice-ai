"""Blender 5.2 (bpy) Open-Cutaway Smart Home 3D Tabletop Model Builder.

Builds a coherent 1:1 physical tabletop cutaway house (~360x270x140 mm on a 400x320 mm base)
matching the locked 6-device / 3-sensor ESP8266 NodeMCU v2 Amica hardware contract,
directly importing the actual KiCad 10.0.6 3D PCB (`hardware/kicad/smarthome_hub/3d/smarthome_hub.glb`).

Outputs:
  - hardware/blender/smarthome_open_house.blend
  - hardware/blender/SCENE_SPEC.json
  - simulator/static/models/smarthome_villa.glb  (<10 MB optimized PBR GLB)
  - Optional studio renders when invoked with `-- --render-dir <dir>`:
      05_blender_house_overview.png
      06_blender_pcb_closeup.png
"""

from __future__ import annotations

import json
import math
import pathlib
import sys
import bpy
import bmesh
from mathutils import Euler, Vector

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
KICAD_PCB_GLB = REPO_ROOT / "hardware" / "kicad" / "smarthome_hub" / "3d" / "smarthome_hub.glb"
OUT_BLEND = REPO_ROOT / "hardware" / "blender" / "smarthome_open_house.blend"
OUT_SPEC = REPO_ROOT / "hardware" / "blender" / "SCENE_SPEC.json"
OUT_GLB = REPO_ROOT / "simulator" / "static" / "models" / "smarthome_villa.glb"

# Uniform display scale: 1 physical mm = 0.025 glTF units (25x tabletop scale).
# Preserves 100% exact 1:1 relative proportions between the 360x270mm open-cutaway house,
# 80x65mm KiCad PCB, NodeMCU, SG90, DHT11, 2 relays, PAM8403, speaker, buzzer, pump, soil & KY-037,
# while fitting cleanly inside house3d.js camera bounds (~10 x 4 x 8 units, near=0.1).
SCENE_SCALE = 25.0
MM = 0.001 * SCENE_SCALE  # 0.025 units per mm


def to_bpos_mm(tx_mm: float, ty_mm: float, tz_mm: float) -> Vector:
    """Convert Three.js coords in mm (X right, Y up, Z front) to Blender world units (X, -Z, Y)."""
    return Vector((tx_mm * MM, -tz_mm * MM, ty_mm * MM))


def to_bsize_mm(sx_mm: float, sy_mm: float, sz_mm: float) -> tuple[float, float, float]:
    """Convert Three.js dimensions in mm (W_x, H_y, D_z) to Blender (X, Y_depth, Z_up)."""
    return (sx_mm * MM, sz_mm * MM, sy_mm * MM)


def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if bpy.context.scene.world is None:
        bpy.context.scene.world = bpy.data.worlds.new("StudioWorld")


def make_mat(
    name: str,
    rgba: tuple[float, float, float, float],
    roughness: float = 0.48,
    metallic: float = 0.0,
    emission: tuple[float, float, float] | None = None,
    emission_strength: float = 0.0,
    alpha: float = 1.0,
) -> bpy.types.Material:
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if alpha < 1.0:
            bsdf.inputs["Alpha"].default_value = alpha
            if hasattr(mat, "blend_method"):
                mat.blend_method = "BLEND"
        if emission and emission_strength > 0.0:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def make_group(name: str, tx_mm: float, ty_mm: float, tz_mm: float, parent=None) -> bpy.types.Object:
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = 6.0 * MM
    bpy.context.collection.objects.link(empty)
    if parent is not None:
        empty.parent = parent
        empty.location = Vector((tx_mm * MM, -tz_mm * MM, ty_mm * MM))
    else:
        empty.location = to_bpos_mm(tx_mm, ty_mm, tz_mm)
    return empty


def add_box(
    name: str,
    tx_mm: float,
    ty_mm: float,
    tz_mm: float,
    sx_mm: float,
    sy_mm: float,
    sz_mm: float,
    mat: bpy.types.Material,
    parent=None,
    bevel_mm: float = 0.0,
    rot_three_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name + "_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bx, by, bz = to_bsize_mm(sx_mm, sy_mm, sz_mm)
    bmesh.ops.scale(bm, vec=(bx, by, bz), verts=bm.verts)
    if bevel_mm > 0.0:
        bmesh.ops.bevel(
            bm,
            geom=list(bm.edges),
            offset=bevel_mm * MM,
            segments=2,
            affect="EDGES",
            clamp_overlap=True,
        )
    bm.to_mesh(mesh)
    bm.free()
    obj.data.materials.append(mat)
    if parent is not None:
        obj.parent = parent
        obj.location = Vector((tx_mm * MM, -tz_mm * MM, ty_mm * MM))
    else:
        obj.location = to_bpos_mm(tx_mm, ty_mm, tz_mm)
    if any(abs(a) > 1e-6 for a in rot_three_deg):
        rx, ry, rz = [math.radians(a) for a in rot_three_deg]
        obj.rotation_euler = Euler((rx, -rz, ry), "XYZ")
    return obj


def add_cyl(
    name: str,
    tx_mm: float,
    ty_mm: float,
    tz_mm: float,
    radius_mm: float,
    height_mm: float,
    mat: bpy.types.Material,
    parent=None,
    axis: str = "Y",
    segs: int = 20,
) -> bpy.types.Object:
    """Create a cylinder oriented along Three.js axis ('X', 'Y'=vertical, 'Z'=front-back)."""
    mesh = bpy.data.meshes.new(name + "_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segs,
        radius1=radius_mm * MM,
        radius2=radius_mm * MM,
        depth=height_mm * MM,
    )
    bm.to_mesh(mesh)
    bm.free()
    obj.data.materials.append(mat)
    if parent is not None:
        obj.parent = parent
        obj.location = Vector((tx_mm * MM, -tz_mm * MM, ty_mm * MM))
    else:
        obj.location = to_bpos_mm(tx_mm, ty_mm, tz_mm)
    if axis == "X":
        obj.rotation_euler = Euler((0.0, math.pi / 2.0, 0.0), "XYZ")
    elif axis == "Z":
        obj.rotation_euler = Euler((math.pi / 2.0, 0.0, 0.0), "XYZ")
    return obj


def add_sphere(
    name: str,
    tx_mm: float,
    ty_mm: float,
    tz_mm: float,
    radius_mm: float,
    mat: bpy.types.Material,
    parent=None,
    scale_xyz: tuple[float, float, float] = (1.0, 1.0, 1.0),
    segs: int = 16,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name + "_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=12, radius=radius_mm * MM)
    if scale_xyz != (1.0, 1.0, 1.0):
        bmesh.ops.scale(bm, vec=(scale_xyz[0], scale_xyz[2], scale_xyz[1]), verts=bm.verts)
    bm.to_mesh(mesh)
    bm.free()
    obj.data.materials.append(mat)
    if parent is not None:
        obj.parent = parent
        obj.location = Vector((tx_mm * MM, -tz_mm * MM, ty_mm * MM))
    else:
        obj.location = to_bpos_mm(tx_mm, ty_mm, tz_mm)
    return obj


def add_tube(
    name: str,
    pts_three_mm: list[tuple[float, float, float]],
    radius_mm: float,
    mat: bpy.types.Material,
    parent=None,
    res: int = 8,
    bevel_res: int = 4,
) -> bpy.types.Object:
    """Create a smooth 3D tubular cable or silicone water tube through Three.js mm waypoints."""
    curve_data = bpy.data.curves.new(name + "_curve", type="CURVE")
    curve_data.dimensions = "3D"
    curve_data.resolution_u = res
    curve_data.bevel_depth = radius_mm * MM
    curve_data.bevel_resolution = bevel_res
    curve_data.fill_mode = "FULL"
    curve_data.use_fill_caps = True

    spline = curve_data.splines.new("POLY")
    spline.points.add(len(pts_three_mm) - 1)
    for idx, (x, y, z) in enumerate(pts_three_mm):
        bv = to_bpos_mm(x, y, z)
        spline.points[idx].co = (bv.x, bv.y, bv.z, 1.0)

    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    if parent is not None:
        obj.parent = parent
    return obj


def convert_curves_to_meshes() -> None:
    """Convert all CURVE wire/tube objects to clean low-poly MESH before GLB export."""
    bpy.ops.object.select_all(action="DESELECT")
    curves = [o for o in bpy.data.objects if o.type == "CURVE"]
    for obj in curves:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.convert(target="MESH")
        obj.select_set(False)


# ==============================================================================
# MATERIALS PALETTE (MATCHING REAL REFERENCE PHOTOS 1 & 2)
# ==============================================================================
def build_materials() -> dict[str, bpy.types.Material]:
    return {
        # Architectural open-cutaway house materials
        "plinth":      make_mat("TabletopPlinth",   (0.11, 0.14, 0.20, 1.0), roughness=0.45, metallic=0.15),
        "plinth_trim": make_mat("PlinthEdgeTrim",   (0.20, 0.26, 0.35, 1.0), roughness=0.35, metallic=0.35),
        "tech_deck":   make_mat("TechBayDeck",      (0.15, 0.18, 0.24, 1.0), roughness=0.42, metallic=0.12),
        "oak_floor":   make_mat("OakFloorLiving",   (0.56, 0.39, 0.23, 1.0), roughness=0.40),
        "walnut_flr":  make_mat("WalnutFloorBed",   (0.38, 0.25, 0.16, 1.0), roughness=0.42),
        "wall_cream":  make_mat("WallOffWhite",     (0.92, 0.91, 0.88, 1.0), roughness=0.65),
        "wall_trim":   make_mat("WallCharcoalCap",  (0.16, 0.20, 0.27, 1.0), roughness=0.40, metallic=0.20),
        "wood_warm":   make_mat("WarmTeakWood",     (0.52, 0.31, 0.16, 1.0), roughness=0.45),
        "door_wood":   make_mat("MainDoorOak",      (0.45, 0.26, 0.13, 1.0), roughness=0.38),
        "glass":       make_mat("ClearGlass",       (0.68, 0.88, 0.98, 0.30), roughness=0.06, metallic=0.08, alpha=0.30),
        "water_tank":  make_mat("WaterReservoir",   (0.30, 0.72, 0.95, 0.45), roughness=0.05, alpha=0.45),
        "water_tube":  make_mat("SiliconeTube",     (0.76, 0.92, 0.98, 0.62), roughness=0.18, alpha=0.62),
        "sofa_blue":   make_mat("SofaNordicBlue",   (0.22, 0.42, 0.68, 1.0), roughness=0.65),
        "cushion":     make_mat("CushionWarm",      (0.92, 0.72, 0.35, 1.0), roughness=0.65),
        "bed_white":   make_mat("BedLinenWhite",    (0.95, 0.95, 0.97, 1.0), roughness=0.65),
        "bed_indigo":  make_mat("BedDuvetIndigo",   (0.26, 0.34, 0.64, 1.0), roughness=0.68),
        "terracotta":  make_mat("PlanterClay",      (0.56, 0.27, 0.15, 1.0), roughness=0.72),
        "soil_dark":   make_mat("GardenSoil",       (0.16, 0.10, 0.06, 1.0), roughness=0.92),
        "leaf_dark":   make_mat("PlantLeafDark",    (0.11, 0.46, 0.20, 1.0), roughness=0.52),
        "leaf_bright": make_mat("PlantLeafBright",  (0.19, 0.64, 0.28, 1.0), roughness=0.48),

        # Real electronic component materials (matched to reference photos 1 & 2)
        "pcb_black":   make_mat("PCB_NodeMCU_Blk",  (0.06, 0.07, 0.09, 1.0), roughness=0.36, metallic=0.08),
        "pcb_blue":    make_mat("PCB_Module_Blue",  (0.05, 0.24, 0.68, 1.0), roughness=0.35, metallic=0.05),
        "pcb_red":     make_mat("PCB_Module_Red",   (0.72, 0.08, 0.09, 1.0), roughness=0.35, metallic=0.05),
        "pcb_green":   make_mat("PCB_PAM8403_Grn",  (0.06, 0.44, 0.18, 1.0), roughness=0.35, metallic=0.05),
        "relay_cube":  make_mat("SongleRelayBlue",  (0.08, 0.45, 0.85, 1.0), roughness=0.32),
        "term_blue":   make_mat("ScrewTermBlue",    (0.09, 0.36, 0.72, 1.0), roughness=0.38),
        "sg90_blue":   make_mat("ServoSG90Blue",    (0.10, 0.42, 0.88, 0.88), roughness=0.25, alpha=0.88),
        "sg90_label":  make_mat("ServoSG90Sticker", (0.92, 0.76, 0.12, 1.0), roughness=0.40),
        "dht_blue":    make_mat("DHT11HousingBlue", (0.12, 0.56, 0.90, 1.0), roughness=0.36),
        "pump_white":  make_mat("PumpWhitePlastic", (0.94, 0.95, 0.96, 1.0), roughness=0.34),
        "plastic_blk": make_mat("PlasticBlack",     (0.05, 0.05, 0.06, 1.0), roughness=0.42),
        "plastic_wht": make_mat("PlasticWhite",     (0.92, 0.93, 0.94, 1.0), roughness=0.35),
        "silver_mtl":  make_mat("BrushedSilver",    (0.80, 0.82, 0.85, 1.0), roughness=0.22, metallic=0.92),
        "brass":       make_mat("MachinedBrass",    (0.85, 0.67, 0.24, 1.0), roughness=0.24, metallic=0.90),
        "copper":      make_mat("GoldPinHeader",    (0.90, 0.72, 0.22, 1.0), roughness=0.20, metallic=0.95),
        "ic_black":    make_mat("IC_EpoxyBlack",    (0.07, 0.07, 0.08, 1.0), roughness=0.32),
        "pot_blue":    make_mat("TrimmerPotBlue",   (0.10, 0.38, 0.82, 1.0), roughness=0.38),
        "mic_felt":    make_mat("ElectretFelt",     (0.06, 0.06, 0.07, 1.0), roughness=0.92),
        "led_lr":      make_mat("LED_LivingWarm",   (1.00, 0.90, 0.65, 1.0), roughness=0.14, emission=(1.0, 0.85, 0.45), emission_strength=1.2),
        "led_br":      make_mat("LED_BedroomWarm",  (1.00, 0.82, 0.50, 1.0), roughness=0.14, emission=(1.0, 0.74, 0.32), emission_strength=1.1),
        "led_red":     make_mat("LED_StatusRed",    (0.95, 0.14, 0.12, 1.0), roughness=0.18, emission=(0.95, 0.12, 0.10), emission_strength=0.9),
        "led_grn":     make_mat("LED_StatusGreen",  (0.12, 0.88, 0.28, 1.0), roughness=0.18, emission=(0.12, 0.88, 0.28), emission_strength=0.9),

        # Color-coded Dupont wire insulation
        "w_red":       make_mat("WireRed_5V",       (0.86, 0.12, 0.12, 1.0), roughness=0.38),
        "w_black":     make_mat("WireBlack_GND",    (0.08, 0.08, 0.10, 1.0), roughness=0.40),
        "w_orange":    make_mat("WireOrange_Sig",   (0.95, 0.46, 0.08, 1.0), roughness=0.38),
        "w_yellow":    make_mat("WireYellow_Sig",   (0.94, 0.80, 0.12, 1.0), roughness=0.38),
        "w_green":     make_mat("WireGreen_Sig",    (0.14, 0.68, 0.24, 1.0), roughness=0.38),
        "w_blue":      make_mat("WireBlue_Sig",     (0.12, 0.45, 0.90, 1.0), roughness=0.38),
        "w_purple":    make_mat("WirePurple_Sig",   (0.56, 0.22, 0.82, 1.0), roughness=0.38),
        "w_white":     make_mat("WireWhite_Sig",    (0.92, 0.93, 0.95, 1.0), roughness=0.38),
        "w_cyan":      make_mat("WireCyan_Sig",     (0.08, 0.74, 0.82, 1.0), roughness=0.38),
    }


# ==============================================================================
# 1. OPEN-CUTAWAY ARCHITECTURAL HOUSE (360 x 270 x 138 mm on 400 x 320 mm PLINTH)
# ==============================================================================
def build_open_cutaway_house(mats: dict[str, bpy.types.Material]) -> bpy.types.Object:
    arch = make_group("OpenCutawayHouse", 0.0, 0.0, 0.0)

    # Tabletop display plinth: 400 x 320 x 8 mm (top surface at Y = 0.0 mm)
    add_box("TabletopPlinth", 0.0, -4.5, 8.0, 404.0, 9.0, 324.0, mats["plinth"], parent=arch, bevel_mm=1.2)
    add_box("PlinthTrim",     0.0, -0.4, 8.0, 396.0, 1.2, 316.0, mats["plinth_trim"], parent=arch, bevel_mm=0.3)

    # Room floors (Y = 0..2 mm)
    # Living Room: X = -175..-5 (W=170), Z = -132..+40 (D=172)
    add_box("LivingRoomFloor", -90.0, 1.0, -46.0, 170.0, 2.0, 172.0, mats["oak_floor"], parent=arch)
    # Bedroom: X = -5..+175 (W=180), Z = -132..+40 (D=172)
    add_box("BedroomFloor",    +85.0, 1.0, -46.0, 180.0, 2.0, 172.0, mats["walnut_flr"], parent=arch)

    # Front-Left Technical Electronics Bay deck (X = -175..+25, Z = +46..+152 -> 200 x 106 mm)
    add_box("TechBayDeck", -75.0, 3.0, 99.0, 200.0, 6.0, 106.0, mats["tech_deck"], parent=arch, bevel_mm=0.8)
    add_box("TechBayTrim", -75.0, 6.2, 99.0, 196.0, 0.6, 102.0, mats["plinth_trim"], parent=arch)

    # WALLS (Open Roof = ZERO roof slab! Cutaway Front Walls = crisp unobstructed interior view!)
    WALL_H = 132.0
    WALL_T = 6.0
    CUT_H = 26.0

    # Rear Wall (Z = -132 mm, X = -178..+178) with panoramic Bedroom glass window
    add_box("BackWallLiving", -90.0, WALL_H / 2, -132.0, 176.0, WALL_H, WALL_T, mats["wall_cream"], parent=arch, bevel_mm=0.4)
    add_box("BackWallBedBot",  88.0, 22.0,       -132.0, 180.0, 44.0,   WALL_T, mats["wall_cream"], parent=arch, bevel_mm=0.4)
    add_box("BackWallBedTop",  88.0, 118.0,      -132.0, 180.0, 28.0,   WALL_T, mats["wall_cream"], parent=arch, bevel_mm=0.4)
    add_box("BackWallBedPillarL",  14.0, 74.0,   -132.0, 32.0,  60.0,   WALL_T, mats["wall_cream"], parent=arch)
    add_box("BackWallBedPillarR", 162.0, 74.0,   -132.0, 32.0,  60.0,   WALL_T, mats["wall_cream"], parent=arch)
    add_box("BedWindowGlass",      88.0, 74.0,   -132.0, 116.0, 60.0,   1.8,    mats["glass"],      parent=arch)
    add_box("BedWindowFrameTop",   88.0, 104.5,  -132.0, 120.0, 2.5,    7.0,    mats["wall_trim"],  parent=arch)
    add_box("BedWindowFrameBot",   88.0, 43.5,   -132.0, 120.0, 2.5,    7.0,    mats["wall_trim"],  parent=arch)
    add_box("BackWallCap",          0.0, WALL_H + 1.5, -132.0, 358.0, 3.0, 8.0, mats["wall_trim"],  parent=arch)

    # Left Wall (X = -175 mm): Full height at back, architectural diagonal/step cutaway in front
    add_box("LeftWallBack", -175.0, WALL_H / 2, -72.0, WALL_T, WALL_H, 120.0, mats["wall_cream"], parent=arch, bevel_mm=0.4)
    add_box("LeftWallFrontLow", -175.0, CUT_H / 2, 14.0, WALL_T, CUT_H, 56.0, mats["wall_cream"], parent=arch, bevel_mm=0.4)
    add_box("LeftWallCapBack", -175.0, WALL_H + 1.5, -72.0, 8.0, 3.0, 122.0, mats["wall_trim"], parent=arch)
    add_box("LeftWallCapFront", -175.0, CUT_H + 1.0, 14.0, 8.0, 2.0, 58.0, mats["wall_trim"], parent=arch)
    # Decorative vertical teak wood slats on Living Room left wall
    for i in range(6):
        add_box(f"LivingWoodSlat_{i}", -171.0, 66.0, -112.0 + i * 14.0, 2.0, 116.0, 5.0, mats["wood_warm"], parent=arch)

    # Right Wall (X = +175 mm): Full back half + low cutaway front half for clear bedroom visibility
    add_box("RightWallBack", 175.0, WALL_H / 2, -76.0, WALL_T, WALL_H, 112.0, mats["wall_cream"], parent=arch, bevel_mm=0.4)
    add_box("RightWallFrontLow", 175.0, CUT_H / 2, 10.0, WALL_T, CUT_H, 64.0, mats["wall_cream"], parent=arch, bevel_mm=0.4)
    add_box("RightWallCapBack", 175.0, WALL_H + 1.5, -76.0, 8.0, 3.0, 114.0, mats["wall_trim"], parent=arch)
    add_box("RightWallCapFront", 175.0, CUT_H + 1.0, 10.0, 8.0, 2.0, 66.0, mats["wall_trim"], parent=arch)

    # Center Dividing Wall (X = -5 mm) with clean doorway passage between Living Room & Bedroom
    add_box("MidWallBack", -5.0, WALL_H / 2, -78.0, WALL_T, WALL_H, 106.0, mats["wall_cream"], parent=arch, bevel_mm=0.4)
    add_box("MidWallBackCap", -5.0, WALL_H + 1.5, -78.0, 8.0, 3.0, 108.0, mats["wall_trim"], parent=arch)
    add_box("MidWallFrontPillar", -5.0, WALL_H / 2, 32.0, 10.0, WALL_H, 16.0, mats["wall_cream"], parent=arch, bevel_mm=0.4)
    add_box("MidWallFrontCap", -5.0, WALL_H + 1.5, 32.0, 12.0, 3.0, 18.0, mats["wall_trim"], parent=arch)

    # Cutaway Front Facade around Main Door (Z = +40 mm)
    # Main Door opening: X = -114 .. -60 mm (54 mm wide, 96 mm tall)
    add_box("FrontDoorFrameLeft",  -118.0, 52.0, 40.0, 8.0,  104.0, 8.0, mats["wall_trim"], parent=arch)
    add_box("FrontDoorFrameRight",  -56.0, 52.0, 40.0, 8.0,  104.0, 8.0, mats["wall_trim"], parent=arch)
    add_box("FrontDoorHeader",      -87.0, 106.0, 40.0, 72.0, 8.0,  9.0, mats["wall_trim"], parent=arch)
    # Low cutaway front waist walls left & right of door so interior & bay stay 100% open
    add_box("FrontCutawayLeft",  -146.0, CUT_H / 2, 40.0, 52.0, CUT_H, WALL_T, mats["wall_cream"], parent=arch)
    add_box("FrontCutawayMid",    -30.0, CUT_H / 2, 40.0, 44.0, CUT_H, WALL_T, mats["wall_cream"], parent=arch)
    add_box("FrontCutawayBed",     85.0, CUT_H / 2, 40.0, 174.0, CUT_H, WALL_T, mats["wall_cream"], parent=arch)
    add_box("FrontCutawayBedCap",  85.0, CUT_H + 1.0, 40.0, 176.0, 2.0, 8.0, mats["wall_trim"], parent=arch)

    # Minimalist Modern Furniture (scaled 1:1 to tabletop house, low-profile so modules stay visible)
    # Living room sofa against back wall
    add_box("LivingSofaBase", -95.0, 9.0, -104.0, 88.0, 14.0, 34.0, mats["sofa_blue"], parent=arch, bevel_mm=2.0)
    add_box("LivingSofaBack", -95.0, 24.0, -118.0, 88.0, 26.0, 10.0, mats["sofa_blue"], parent=arch, bevel_mm=2.0)
    add_box("LivingSofaArmL", -136.0, 18.0, -104.0, 8.0, 18.0, 34.0, mats["sofa_blue"], parent=arch, bevel_mm=1.5)
    add_box("LivingSofaArmR",  -54.0, 18.0, -104.0, 8.0, 18.0, 34.0, mats["sofa_blue"], parent=arch, bevel_mm=1.5)
    add_box("LivingPillow1",  -118.0, 22.0, -110.0, 16.0, 14.0, 6.0, mats["cushion"], parent=arch, bevel_mm=1.5)
    add_box("LivingPillow2",   -72.0, 22.0, -110.0, 16.0, 14.0, 6.0, mats["cushion"], parent=arch, bevel_mm=1.5)
    # Coffee table
    add_box("CoffeeTableTop",  -95.0, 15.0, -58.0, 52.0, 3.0, 28.0, mats["wood_warm"], parent=arch, bevel_mm=0.6)
    add_box("CoffeeTableBase", -95.0,  7.5, -58.0, 40.0, 12.0, 18.0, mats["wall_trim"], parent=arch)

    # Bedroom bed + nightstand
    add_box("BedFrame",       96.0, 8.0,  -78.0, 82.0, 12.0, 94.0, mats["wood_warm"], parent=arch, bevel_mm=1.0)
    add_box("BedHeadboard",   96.0, 26.0, -123.0, 86.0, 36.0, 5.0, mats["wood_warm"], parent=arch, bevel_mm=0.8)
    add_box("BedMattress",    96.0, 18.0, -78.0, 76.0, 10.0, 88.0, mats["bed_white"], parent=arch, bevel_mm=2.0)
    add_box("BedDuvet",       96.0, 19.5, -60.0, 78.0, 10.5, 56.0, mats["bed_indigo"], parent=arch, bevel_mm=2.0)
    add_box("BedPillowL",     76.0, 25.0, -108.0, 28.0, 6.0, 16.0, mats["bed_white"], parent=arch, bevel_mm=1.5)
    add_box("BedPillowR",    116.0, 25.0, -108.0, 28.0, 6.0, 16.0, mats["bed_white"], parent=arch, bevel_mm=1.5)
    add_box("Nightstand",     36.0, 14.0, -108.0, 24.0, 24.0, 22.0, mats["wood_warm"], parent=arch, bevel_mm=0.8)

    # Front-Right Garden Planter Box (X = +38..+176, Z = +52..+148 -> 138 x 96 mm)
    # Left chamber (X = +40..+82): clear water reservoir for submersible pump
    # Right chamber (X = +86..+174): terracotta soil planter with plants & soil sensor
    add_box("GardenPlanterWalls", 130.0, 16.0, 100.0, 92.0, 32.0, 92.0, mats["terracotta"], parent=arch, bevel_mm=1.0)
    add_box("GardenSoilBed",      130.0, 26.5, 100.0, 82.0, 14.0, 82.0, mats["soil_dark"], parent=arch)
    # 2 clean tabletop plants inside soil bed
    for idx, (px, pz, h) in enumerate([(106.0, 78.0, 34.0), (150.0, 120.0, 28.0)]):
        add_cyl(f"GardenStem_{idx}", px, 33.0 + h * 0.3, pz, 2.2, h * 0.6, mats["wood_warm"], parent=arch)
        add_sphere(f"GardenFoliageA_{idx}", px, 33.0 + h * 0.72, pz, 13.0, mats["leaf_dark"], parent=arch, scale_xyz=(1.1, 0.85, 1.1))
        add_sphere(f"GardenFoliageB_{idx}", px + 4.0, 33.0 + h * 0.96, pz - 2.0, 9.0, mats["leaf_bright"], parent=arch)

    # Clear Water Reservoir Tank beside planter (X = +60, Z = +100, 44 x 36 x 66 mm)
    add_box("WaterTankBase",  60.0, 2.0,  100.0, 46.0, 4.0,  72.0, mats["plinth_trim"], parent=arch)
    add_box("WaterTankGlass", 60.0, 22.0, 100.0, 44.0, 38.0, 70.0, mats["glass"], parent=arch)
    add_box("WaterLevel",     60.0, 14.0, 100.0, 40.0, 22.0, 66.0, mats["water_tank"], parent=arch)

    return arch


# ==============================================================================
# 2. DIRECT IMPORT OF ACTUAL KICAD 3D PCB (`kicad_pcb_hub`) + NODEMCU (`nodemcu_esp8266`)
# ==============================================================================
# Technical bay PCB center in Three.js mm:
PCB_CX_MM = -118.0
PCB_CZ_MM = 99.0
PCB_BOT_Y_MM = 12.0   # PCB bottom sits on 6mm brass M3 standoffs above 6mm TechBayDeck!


def pcb_pin_world_mm(x_rel_mm: float, y_rel_mm: float, z_top_offset_mm: float = 8.5) -> tuple[float, float, float]:
    """Convert KiCad PCB local mm (origin top-left 0..80, 0..65) to Three.js world mm."""
    tx = PCB_CX_MM + (x_rel_mm - 40.0)
    tz = PCB_CZ_MM + (y_rel_mm - 32.5)
    ty = PCB_BOT_Y_MM + 1.6 + z_top_offset_mm
    return (tx, ty, tz)


def import_kicad_pcb_and_nodemcu(mats: dict[str, bpy.types.Material]) -> tuple[bpy.types.Object, bpy.types.Object]:
    if not KICAD_PCB_GLB.exists():
        raise FileNotFoundError(f"KiCad 3D PCB GLB missing: {KICAD_PCB_GLB}")

    pcb_hub = make_group("kicad_pcb_hub", PCB_CX_MM, PCB_BOT_Y_MM, PCB_CZ_MM)

    # 4 Brass M3 standoffs (OD 5.0mm x 6.0mm) under the 4 corner M3 mounting holes (inset 4.5mm from 80x65 edges)
    for idx, (hx, hy) in enumerate([(4.5, 4.5), (75.5, 4.5), (4.5, 60.5), (75.5, 60.5)]):
        add_cyl(
            f"PCB_Standoff_M3_{idx + 1}",
            hx - 40.0, -3.0, hy - 32.5,
            radius_mm=2.5, height_mm=6.0,
            mat=mats["brass"], parent=pcb_hub,
        )

    # Import the actual KiCad-exported 3D PCB GLB directly!
    before_objs = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(KICAD_PCB_GLB))
    imported = [o for o in bpy.data.objects if o not in before_objs]
    imported_roots = [o for o in imported if o.parent is None]

    # Measure imported PCB world bounding box AND locate the FR4 board substrate bottom
    # so the PCB sits flush on top of the brass standoffs at PCB_BOT_Y_MM (not on protruding pin tips).
    bpy.context.view_layer.update()
    xs, ys, zs = [], [], []
    board_zmin_m = None
    for o in imported:
        if o.type == "MESH":
            mxs, mys, mzs = [], [], []
            for corner in o.bound_box:
                wc = o.matrix_world @ Vector(corner)
                xs.append(wc.x)
                ys.append(wc.y)
                zs.append(wc.z)
                mxs.append(wc.x)
                mys.append(wc.y)
                mzs.append(wc.z)
            dx_m = max(mxs) - min(mxs)
            dy_m = max(mys) - min(mys)
            dz_m = max(mzs) - min(mzs)
            if dx_m > 0.078 and dy_m > 0.063 and dz_m < 0.003:
                board_zmin_m = min(mzs)
    if not xs:
        raise RuntimeError("Imported KiCad PCB GLB contained zero mesh geometry!")

    cx_m = 0.5 * (min(xs) + max(xs))
    cy_m = 0.5 * (min(ys) + max(ys))
    z_align_m = board_zmin_m if board_zmin_m is not None else (min(zs) + 0.001905)
    print(
        f"[KICAD IMPORT] Imported {len(imported)} objects "
        f"extents_mm=({(max(xs)-min(xs))*1000:.2f}, {(max(ys)-min(ys))*1000:.2f}, {(max(zs)-min(zs))*1000:.2f}) "
        f"fr4_zmin_mm={z_align_m*1000:.3f} pin_zmin_mm={min(zs)*1000:.3f}"
    )

    # Reparent imported KiCad PCB root(s) into kicad_pcb_hub at exact coherent SCENE_SCALE
    for r in imported_roots:
        r.parent = pcb_hub
        r.scale = (r.scale.x * SCENE_SCALE, r.scale.y * SCENE_SCALE, r.scale.z * SCENE_SCALE)
        r.location = Vector((
            (r.location.x - cx_m) * SCENE_SCALE,
            (r.location.y - cy_m) * SCENE_SCALE,
            (r.location.z - z_align_m) * SCENE_SCALE,
        ))

    # Build authentic ESP8266 NodeMCU v2 Amica plugged directly onto U1/U2 2x15 female sockets.
    # Official Amica v2 PCB: 25.40mm wide (X) x 48.26mm long (Z) x 1.60mm thick (~49.4mm w/ Micro-USB),
    # with 2.54mm male header plastic strips seated flush on top of 8.5mm female sockets (Y = 22.10 mm).
    nodemcu = make_group("nodemcu_esp8266", PCB_CX_MM, PCB_BOT_Y_MM + 10.1, PCB_CZ_MM)
    # 2x15 male header plastic insulator strips (2.54 x 2.54 x 38.10 mm) at exact 22.86mm row spacing
    for side, sx in [("L", -11.43), ("R", 11.43)]:
        add_box(f"NodeMCU_MaleHdrStrip_{side}", sx, 1.27, 0.0, 2.54, 2.54, 38.10, mats["plastic_blk"], parent=nodemcu)
    # Black PCB sits cleanly on top of the 2.54mm header strips (Y_local = 2.54 .. 4.14 mm)
    add_box("NodeMCU_PCB", 0.0, 3.34, 0.0, 25.40, 1.60, 48.26, mats["pcb_black"], parent=nodemcu, bevel_mm=0.2)
    # Silver ESP-12E RF metal shield can (16.0 x 12.0 x 3.0 mm) toward -Z (antenna end)
    add_box("NodeMCU_ESP12_Shield", 0.0, 5.64, -7.0, 16.0, 3.0, 12.0, mats["silver_mtl"], parent=nodemcu, bevel_mm=0.2)
    # PCB Wi-Fi meander antenna zone at top (-Z end)
    add_box("NodeMCU_WiFi_AntennaArea", 0.0, 4.29, -18.5, 16.0, 0.3, 7.0, mats["pcb_black"], parent=nodemcu)
    for k in range(5):
        add_box(f"NodeMCU_AntTrace_{k}", -6.0 + k * 3.0, 4.49, -18.5, 0.7, 0.15, 5.8, mats["copper"], parent=nodemcu)
    # CP2102 USB-UART IC + AMS1117 regulator
    add_box("NodeMCU_CP2102", 0.0, 4.64, 9.5, 5.0, 1.0, 5.0, mats["ic_black"], parent=nodemcu)
    add_box("NodeMCU_AMS1117", -6.5, 4.89, 15.0, 6.5, 1.5, 3.5, mats["ic_black"], parent=nodemcu)
    # Micro-USB metallic connector at bottom (+Z end, slight ~1.1mm board overhang)
    add_box("NodeMCU_MicroUSB", 0.0, 5.54, 22.5, 7.8, 2.8, 5.6, mats["silver_mtl"], parent=nodemcu, bevel_mm=0.2)
    # RST & FLASH tactile buttons
    add_box("NodeMCU_Btn_RST", -6.2, 4.89, 20.5, 3.2, 1.5, 2.4, mats["silver_mtl"], parent=nodemcu)
    add_box("NodeMCU_Btn_FLASH", 6.2, 4.89, 20.5, 3.2, 1.5, 2.4, mats["silver_mtl"], parent=nodemcu)
    # Onboard blue status LED near ESP-12E
    add_box("NodeMCU_StatusLED", 6.2, 4.54, -12.5, 1.6, 0.8, 0.8, mats["dht_blue"], parent=nodemcu)
    # 2x15 gold header solder nubs along left & right edges (exact 22.86mm pitch = +/-11.43mm)
    for side, sx in [("L", -11.43), ("R", 11.43)]:
        add_box(f"NodeMCU_HeaderBar_{side}", sx, 4.64, 0.0, 1.4, 1.0, 37.5, mats["copper"], parent=nodemcu)

    return pcb_hub, nodemcu


# ==============================================================================
# 3. ALL 6 REAL DEVICES + 3 REAL SENSORS (LOCKED GLB NODE NAMES, ZERO FAN/AC/IR)
# ==============================================================================
def build_hardware_devices_and_sensors(mats: dict[str, bpy.types.Material]) -> dict[str, tuple[float, float, float]]:
    """Build every contract device and sensor at exact 1:1 physical mm scale.

    Returns dict of wire anchor points (in Three.js mm) for clean Dupont cable routing.
    """
    anchors: dict[str, tuple[float, float, float]] = {}

    # ------------------------------------------------------------------
    # DEVICE 1: main_door (`door_pivot` / `main_door_leaf`) + Servo SG90 (D1)
    # Hinge at X = -114 mm, Z = +40 mm -> rotates around Y (0 deg closed, 90 deg open)
    # ------------------------------------------------------------------
    door_pivot = make_group("door_pivot", -114.0, 0.0, 40.0)
    # Door leaf: 54mm wide x 98mm tall x 5mm thick, offset +27mm from hinge pivot
    add_box("main_door_leaf", 27.0, 50.0, 0.0, 52.0, 96.0, 5.0, mats["door_wood"], parent=door_pivot, bevel_mm=0.6)
    add_box("MainDoorWindow", 27.0, 72.0, 0.0, 26.0, 30.0, 5.6, mats["glass"], parent=door_pivot)
    add_box("MainDoorHandle", 46.0, 46.0, 3.8, 4.0, 10.0, 3.0, mats["brass"], parent=door_pivot, bevel_mm=0.4)

    # SG90 Micro Servo (datasheet: body 22.8 x 12.2 x 22.5 mm, tab span 32.2 mm at 15.9 mm H,
    # gear tower 26.7 mm, shaft 29.0 mm, horn top 31.0 mm; positioned in front of door post with zero clipping)
    sg90 = make_group("SG90_DoorServo", -132.0, 17.75, 52.0)
    add_box("SG90_Body", 0.0, 0.0, 0.0, 22.8, 22.5, 12.2, mats["sg90_blue"], parent=sg90, bevel_mm=0.4)
    add_box("SG90_Flange", 0.0, 5.9, 0.0, 32.2, 2.5, 12.2, mats["sg90_blue"], parent=sg90)
    add_box("SG90_Sticker", 0.0, -1.0, 6.05, 11.0, 11.0, 0.1, mats["sg90_label"], parent=sg90)
    add_cyl("SG90_GearHub", 5.4, 13.35, 0.0, 5.9, 4.2, mats["sg90_blue"], parent=sg90)
    add_cyl("SG90_OutputShaft", 5.4, 16.6, 0.0, 2.4, 2.3, mats["plastic_wht"], parent=sg90)
    add_box("SG90_WhiteHorn", 9.1, 18.75, 0.0, 14.0, 2.0, 4.5, mats["plastic_wht"], parent=sg90, bevel_mm=0.3)
    anchors["servo"] = (-120.6, 12.0, 58.1)

    # ------------------------------------------------------------------
    # DEVICE 2: led_living_room (5mm T-1 3/4 LED on D0: Ø5.0 dome, Ø5.8 flange, 8.6mm H, 2.54mm leads)
    # Mounted flush on Living Room interior rear wall (Z = -129.0 mm)
    # ------------------------------------------------------------------
    led_lr = make_group("led_living_room", -95.0, 112.0, -129.0)
    add_cyl("LED_LR_Flange", 0.0, 0.0, 0.5, 2.9, 1.0, mats["led_lr"], parent=led_lr, axis="Z", segs=24)
    add_cyl("LED_LR_Body",   0.0, 0.0, 3.55, 2.5, 5.1, mats["led_lr"], parent=led_lr, axis="Z", segs=24)
    add_sphere("LED_LR_Dome", 0.0, 0.0, 6.1, 2.5, mats["led_lr"], parent=led_lr, segs=20)
    add_box("LED_LR_LeadA", -1.27, 0.0, -1.5, 0.5, 0.5, 3.0, mats["silver_mtl"], parent=led_lr)
    add_box("LED_LR_LeadK",  1.27, 0.0, -1.5, 0.5, 0.5, 3.0, mats["silver_mtl"], parent=led_lr)
    anchors["led_lr"] = (-95.0, 112.0, -129.0)

    # ------------------------------------------------------------------
    # DEVICE 3: led_bedroom (5mm T-1 3/4 LED on D4 safe-boot: Ø5.0 dome, Ø5.8 flange, 8.6mm H, 2.54mm leads)
    # Mounted flush on Bedroom interior rear wall (Z = -129.0 mm)
    # ------------------------------------------------------------------
    led_br = make_group("led_bedroom", 88.0, 116.0, -129.0)
    add_cyl("LED_BR_Flange", 0.0, 0.0, 0.5, 2.9, 1.0, mats["led_br"], parent=led_br, axis="Z", segs=24)
    add_cyl("LED_BR_Body",   0.0, 0.0, 3.55, 2.5, 5.1, mats["led_br"], parent=led_br, axis="Z", segs=24)
    add_sphere("LED_BR_Dome", 0.0, 0.0, 6.1, 2.5, mats["led_br"], parent=led_br, segs=20)
    add_box("LED_BR_LeadA", -1.27, 0.0, -1.5, 0.5, 0.5, 3.0, mats["silver_mtl"], parent=led_br)
    add_box("LED_BR_LeadK",  1.27, 0.0, -1.5, 0.5, 0.5, 3.0, mats["silver_mtl"], parent=led_br)
    anchors["led_br"] = (88.0, 116.0, -129.0)

    # ------------------------------------------------------------------
    # DEVICE 4: garden_pump (`pump_unit`, `water_tube`, `relay1_pump`)
    # ------------------------------------------------------------------
    # Horizontal 3-6V mini submersible water pump (datasheet: 45.0 L x 24.0 dia x 33.0 H mm, Ø7.5 outlet)
    pump = make_group("pump_unit", 60.0, 16.5, 100.0)
    add_cyl("Pump_WhiteBody",    0.0,  0.0, -5.0, 12.0, 35.0, mats["pump_white"], parent=pump, axis="Z", segs=24)
    add_cyl("Pump_FrontIntake",  0.0,  0.0, 17.5,  4.0, 10.0, mats["pump_white"], parent=pump, axis="Z", segs=16)
    add_cyl("Pump_OutletNozzle", 0.0, 16.5,  7.0, 3.75,  9.0, mats["pump_white"], parent=pump, axis="Y", segs=16)
    anchors["pump"] = (54.0, 26.0, 78.0)

    # Translucent 6/8mm (Ø8.0mm OD) silicone water tube arching from pump nozzle into garden planter soil
    add_tube(
        "water_tube",
        [
            (60.0, 36.0, 107.0),
            (60.0, 56.0, 107.0),
            (78.0, 60.0, 107.0),
            (96.0, 48.0, 107.0),
            (114.0, 38.0, 107.0),
            (126.0, 35.0, 107.0),
        ],
        radius_mm=4.0,
        mat=mats["water_tube"],
        res=12,
        bevel_res=6,
    )

    # Relay 1 (BLUE 5V 1-ch relay module, exact 50.0 x 26.0 x 18.5 mm, Songle SRD-05VDC-SL-C, 5.08mm terminal)
    rly1 = make_group("relay1_pump", -44.0, 6.5, 76.0)
    for idx, (fx, fz) in enumerate([(-22.5, -10.5), (22.5, -10.5), (-22.5, 10.5), (22.5, 10.5)]):
        add_cyl(f"Rly1_Foot_{idx}", fx, 0.75, fz, 1.5, 1.5, mats["brass"], parent=rly1, segs=12)
    add_box("Rly1_BluePCB", 0.0, 2.3, 0.0, 50.0, 1.6, 26.0, mats["pcb_blue"], parent=rly1, bevel_mm=0.2)
    add_box("Rly1_SongleCube", -2.5, 10.8, 0.0, 19.0, 15.4, 15.5, mats["relay_cube"], parent=rly1, bevel_mm=0.35)
    add_box("Rly1_ScrewTerm", 17.0, 8.1, 0.0, 8.0, 10.0, 15.24, mats["term_blue"], parent=rly1, bevel_mm=0.25)
    for k in range(3):
        add_cyl(f"Rly1_Screw_{k}", 17.0, 13.2, (k - 1) * 5.08, 1.8, 0.6, mats["silver_mtl"], parent=rly1)
    add_box("Rly1_PinHeader", -21.5, 6.0, 0.0, 2.54, 7.0, 7.62, mats["plastic_blk"], parent=rly1)
    add_box("Rly1_LED_Pwr", -14.5, 3.6, -6.5, 2.2, 1.0, 1.4, mats["led_red"], parent=rly1)
    add_box("Rly1_LED_Trig", -14.5, 3.6,  6.5, 2.2, 1.0, 1.4, mats["led_grn"], parent=rly1)
    anchors["rly1_in"] = (-65.5, 13.0, 76.0)
    anchors["rly1_sw"] = (-27.0, 13.5, 76.0)

    # ------------------------------------------------------------------
    # DEVICE 5: alarm_siren (`buzzer_alarm`, 5V active buzzer TMB12A05: Ø12.0 x 9.5 mm, 7.6 mm pin pitch)
    # Mounted flush on front face of center-front pillar (Z = 40.0 mm)
    # ------------------------------------------------------------------
    buzzer = make_group("buzzer_alarm", -5.0, 116.0, 40.0)
    add_cyl("Buzzer_CylBody", 0.0, 0.0, 4.75, 6.0, 9.5, mats["plastic_blk"], parent=buzzer, axis="Z", segs=24)
    add_cyl("Buzzer_SoundHole", 0.0, 0.0, 9.35, 1.5, 0.3, mats["silver_mtl"], parent=buzzer, axis="Z", segs=16)
    add_cyl("Buzzer_PinPos", -3.8, 0.0, 0.1, 0.35, 0.2, mats["silver_mtl"], parent=buzzer, axis="Z", segs=10)
    add_cyl("Buzzer_PinNeg",  3.8, 0.0, 0.1, 0.35, 0.2, mats["silver_mtl"], parent=buzzer, axis="Z", segs=10)
    anchors["buzzer"] = (-5.0, 110.0, 41.0)

    # ------------------------------------------------------------------
    # DEVICE 6: speaker_amp (`relay2_speaker` RED opto, `pam8403_module` GREEN, `speaker_mini` 28mm)
    # ------------------------------------------------------------------
    # Relay 2 (RED opto 5V 1-ch relay module, exact 50.0 x 26.0 x 18.5 mm, Songle SRD-05VDC-SL-C + PC817)
    rly2 = make_group("relay2_speaker", -44.0, 6.5, 122.0)
    for idx, (fx, fz) in enumerate([(-22.5, -10.5), (22.5, -10.5), (-22.5, 10.5), (22.5, 10.5)]):
        add_cyl(f"Rly2_Foot_{idx}", fx, 0.75, fz, 1.5, 1.5, mats["brass"], parent=rly2, segs=12)
    add_box("Rly2_RedPCB", 0.0, 2.3, 0.0, 50.0, 1.6, 26.0, mats["pcb_red"], parent=rly2, bevel_mm=0.2)
    add_box("Rly2_SongleCube", -2.0, 10.8, 0.0, 19.0, 15.4, 15.5, mats["relay_cube"], parent=rly2, bevel_mm=0.35)
    add_box("Rly2_ScrewTerm", 17.0, 8.1, 0.0, 8.0, 10.0, 15.24, mats["term_blue"], parent=rly2, bevel_mm=0.25)
    for k in range(3):
        add_cyl(f"Rly2_Screw_{k}", 17.0, 13.2, (k - 1) * 5.08, 1.8, 0.6, mats["silver_mtl"], parent=rly2)
    add_box("Rly2_Optocoupler", -14.5, 4.7, 0.0, 4.6, 3.2, 6.5, mats["ic_black"], parent=rly2)
    add_box("Rly2_PinHeader", -21.5, 6.0, 0.0, 2.54, 7.0, 7.62, mats["plastic_blk"], parent=rly2)
    add_box("Rly2_LED_Pwr", -15.0, 3.6, -7.5, 2.2, 1.0, 1.4, mats["led_grn"], parent=rly2)
    add_box("Rly2_LED_Trig", -15.0, 3.6,  7.5, 2.2, 1.0, 1.4, mats["led_red"], parent=rly2)
    anchors["rly2_in"] = (-65.5, 13.0, 122.0)
    anchors["rly2_sw"] = (-27.0, 13.5, 122.0)

    # PAM8403 Audio Amplifier (GREEN 21.0 x 18.0 x 3.1 mm PCB, SOP-16 IC 9.9 x 3.9 x 1.5 mm)
    pam = make_group("pam8403_module", 2.0, 6.5, 122.0)
    add_box("PAM8403_GreenPCB", 0.0, 0.8, 0.0, 21.0, 1.6, 18.0, mats["pcb_green"], parent=pam, bevel_mm=0.15)
    add_box("PAM8403_SOIC16", 0.0, 2.35, 0.0, 3.9, 1.5, 9.9, mats["ic_black"], parent=pam)
    for sx in (-2.48, 2.48):
        for k in range(8):
            add_box(f"PAM_Pin_{sx}_{k}", sx, 1.75, -4.445 + k * 1.27, 1.05, 0.25, 0.42, mats["silver_mtl"], parent=pam)
    for px, pz in [(-7.5, -7.2), (-4.5, -7.2), (4.5, -7.2), (7.5, -7.2), (-7.0, 7.2), (-4.0, 7.2), (4.5, 7.2), (7.5, 7.2)]:
        add_cyl(f"PAM_Pad_{px}_{pz}", px, 1.65, pz, 0.9, 0.2, mats["copper"], parent=pam, segs=12)
    anchors["pam_pwr"] = (2.0, 9.0, 130.0)
    anchors["pam_aud"] = (-4.0, 9.0, 130.0)
    anchors["pam_out"] = (2.0, 9.0, 114.0)

    # Mini Round Speaker: 28 mm 8 Ohm 0.5 W (PUI Audio AS02808MR-R: exact Ø28.0 x 5.2 mm)
    # Chosen 28mm over 40mm to fit cleanly in the 44mm technical bay slot beside relay1_pump with >=7mm clearance.
    spk = make_group("speaker_mini", 2.0, 6.5, 78.0)
    add_cyl("Speaker_SilverRim", 0.0, 2.3, 0.0, 14.0, 4.6, mats["silver_mtl"], parent=spk, axis="Y", segs=28)
    add_cyl("Speaker_InnerCone", 0.0, 4.6, 0.0, 11.5, 0.6, mats["plastic_blk"], parent=spk, axis="Y", segs=24)
    add_cyl("Speaker_CenterCap", 0.0, 4.9, 0.0,  5.2, 0.6, mats["silver_mtl"], parent=spk, axis="Y", segs=20)
    anchors["speaker"] = (2.0, 9.5, 91.0)

    # ------------------------------------------------------------------
    # SENSOR 1: sensor_dht11 (3-pin DHT11 breakout: PCB 14.0 x 28.0 x 1.6 mm, blue body 12.0 x 15.5 x 5.5 mm)
    # Mounted flush on Living Room interior rear wall (Z = -129.0 mm)
    # ------------------------------------------------------------------
    dht = make_group("sensor_dht11", -42.0, 88.0, -129.0)
    add_box("DHT11_BreakoutPCB", 0.0, 0.0, 0.8, 14.0, 28.0, 1.6, mats["pcb_blue"], parent=dht)
    add_box("DHT11_BlueGridBox", 0.0, 3.5, 4.35, 12.0, 15.5, 5.5, mats["dht_blue"], parent=dht, bevel_mm=0.25)
    for row in range(3):
        for col in range(3):
            add_box(f"DHT11_Vent_{row}_{col}", -3.2 + col * 3.2, -0.5 + row * 4.0, 6.9, 1.9, 1.9, 0.4, mats["plastic_blk"], parent=dht)
    add_box("DHT11_Pins", 0.0, -11.5, 2.87, 7.62, 5.0, 2.54, mats["silver_mtl"], parent=dht)
    anchors["dht11"] = (-42.0, 74.0, -127.0)

    # ------------------------------------------------------------------
    # SENSOR 2: sensor_soil (YL-69 fork probe 60.0 x 20.0 x 1.6 mm + LM393 PCB 32.0 x 14.0 x 12.1 mm)
    # ------------------------------------------------------------------
    soil = make_group("sensor_soil", 142.0, 36.0, 96.0)
    # YL-69 2-prong fork probe: 20.0 mm wide x 60.0 mm total height (18mm head + 42mm prongs) x 1.6 mm thick
    add_box("SoilProbe_Head", 0.0, 21.0, 0.0, 20.0, 18.0, 1.6, mats["pcb_black"], parent=soil)
    add_box("SoilProbe_ProngL", -5.0, -9.0, 0.0, 5.0, 42.0, 1.6, mats["silver_mtl"], parent=soil)
    add_box("SoilProbe_ProngR",  5.0, -9.0, 0.0, 5.0, 42.0, 1.6, mats["silver_mtl"], parent=soil)
    # Blue LM393 comparator breakout PCB seated flush on planter front rim (world Y=32.0, X=112.0, Z=140.0)
    lm_off = (-30.0, -4.0, 44.0)
    add_box("Soil_LM393_PCB", lm_off[0], lm_off[1] + 0.8, lm_off[2], 32.0, 1.6, 14.0, mats["pcb_blue"], parent=soil, bevel_mm=0.2)
    add_box("Soil_LM393_Pot", lm_off[0] + 2.0, lm_off[1] + 6.35, lm_off[2], 9.5, 9.5, 4.8, mats["pot_blue"], parent=soil)
    add_cyl("Soil_LM393_Screw", lm_off[0] + 4.5, lm_off[1] + 11.6, lm_off[2], 1.2, 1.0, mats["brass"], parent=soil)
    add_box("Soil_LM393_IC",  lm_off[0] - 6.0, lm_off[1] + 2.3, lm_off[2], 5.0, 1.4, 4.0, mats["ic_black"], parent=soil)
    add_box("Soil_LM393_Hdr", lm_off[0] - 14.0, lm_off[1] + 2.87, lm_off[2], 3.0, 2.54, 10.16, mats["silver_mtl"], parent=soil)
    # Probe-to-LM393 jumper pair
    add_tube(
        "SoilProbeCable",
        [(142.0, 65.0, 96.0), (142.0, 68.0, 118.0), (128.0, 36.0, 140.0)],
        radius_mm=1.1,
        mat=mats["w_yellow"],
    )
    anchors["soil"] = (96.0, 35.0, 140.0)

    # ------------------------------------------------------------------
    # SENSOR 3: sensor_mic_ky037 (KY-037/KY-038: PCB 35.0 x 15.0 x 1.6 mm, H 13.1 mm, mic Ø9.7 x 6.7 mm)
    # Mounted flush on Living Room front cutaway ledge (Y = 26.0 mm)
    # ------------------------------------------------------------------
    ky = make_group("sensor_mic_ky037", -32.0, 26.0, 40.0)
    add_box("KY037_RedPCB", 0.0, 0.8, 0.0, 35.0, 1.6, 15.0, mats["pcb_red"], parent=ky, bevel_mm=0.2)
    # Silver cylindrical electret mic capsule (ECM-9767: Ø9.7 x 6.7 mm) with black felt top
    add_cyl("KY037_MicCan", -11.5, 4.95, 0.0, 4.85, 6.7, mats["silver_mtl"], parent=ky, axis="Y", segs=22)
    add_cyl("KY037_MicFelt", -11.5, 8.25, 0.0, 4.3, 0.3, mats["mic_felt"], parent=ky, axis="Y", segs=22)
    # Blue 3296W multi-turn trimmer pot (9.5 x 10.0 x 4.8 mm) + 1.5 mm brass screw -> total H = 13.1 mm
    add_box("KY037_TrimPot", 2.0, 6.6, -3.5, 9.5, 10.0, 4.8, mats["pot_blue"], parent=ky)
    add_cyl("KY037_PotScrew", 5.0, 12.35, -3.5, 1.2, 1.5, mats["brass"], parent=ky)
    # LM393 comparator IC + Ø3.0 mm mounting hole + 4-pin 2.54mm male header (10.16 mm)
    add_box("KY037_LM393", 1.5, 2.3, 3.8, 5.0, 1.4, 4.0, mats["ic_black"], parent=ky)
    add_cyl("KY037_MountHole", 10.5, 1.6, 0.0, 1.5, 1.8, mats["silver_mtl"], parent=ky)
    add_box("KY037_PinHeader", 15.5, 2.87, 0.0, 3.5, 2.54, 10.16, mats["plastic_blk"], parent=ky)
    anchors["ky037"] = (-15.0, 29.0, 40.0)

    return anchors


# ==============================================================================
# 4. COLOR-CODED 3D DUPONT WIRES FROM LABELED KICAD PCB HEADERS TO COMPONENTS
# ==============================================================================
def build_dupont_wires(mats: dict[str, bpy.types.Material], anchors: dict[str, tuple[float, float, float]]) -> bpy.types.Object:
    wires = make_group("DupontWiringHarness", 0.0, 0.0, 0.0)
    WR = 0.85

    def route_bundle(name: str, pcb_xy: tuple[float, float], target_xyz: tuple[float, float, float],
                     mid_pts: list[tuple[float, float, float]], colors: list[str], orient: str = "V") -> None:
        px, py, pz = pcb_pin_world_mm(pcb_xy[0], pcb_xy[1], z_top_offset_mm=6.2)
        n = len(colors)
        if orient == "H":
            add_box(f"DupontPlug_{name}", px, py + 0.8, pz, max(2.54, 2.54 * n), 7.0, 2.54, mats["plastic_blk"], parent=wires)
        elif orient == "V":
            add_box(f"DupontPlug_{name}", px, py + 0.8, pz, 2.54, 7.0, max(2.54, 2.54 * n), mats["plastic_blk"], parent=wires)

        for idx, col_key in enumerate(colors):
            off = (idx - (n - 1) * 0.5) * 2.54
            if orient == "SCREW":
                # Phoenix 5.08mm terminal block horizontal wire entry from -X face
                z_entry = pz + (idx - 0.5) * 5.08
                pts = [(px - 4.5, PCB_BOT_Y_MM + 1.6 + 6.5, z_entry), (px - 9.0, PCB_BOT_Y_MM + 1.6 + 6.5, z_entry)]
            elif orient == "H":
                pts = [(px + off, py + 4.3, pz), (px + off, py + 8.5, pz)]
            else:
                pts = [(px, py + 4.3, pz + off), (px, py + 8.5, pz + off)]
            for mx, my, mz in mid_pts:
                pts.append((mx + off * 0.45, my, mz + off * 0.45))
            pts.append((target_xyz[0] + off * 0.45, target_xyz[1], target_xyz[2]))
            add_tube(f"Wire_{name}_{idx}", pts, radius_mm=WR, mat=mats[col_key], parent=wires)

    # Exact KiCad PCB header centers (matching hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb)
    route_bundle("J3_SERVO_D1", (74.50, 16.04), anchors["servo"],
                 [(-76.0, 14.0, 62.0), (-118.0, 14.0, 62.0)], ["w_orange", "w_red", "w_black"], orient="V")

    route_bundle("J4_LR_LED_D0", (45.77, 4.50), anchors["led_lr"],
                 [(-112.0, 18.0, 56.0), (-168.0, 18.0, 44.0), (-168.0, 18.0, -126.0), (-168.0, 112.0, -126.0)],
                 ["w_yellow", "w_black"], orient="H")

    route_bundle("J5_BR_LED_D4", (59.27, 4.50), anchors["led_br"],
                 [(-96.0, 18.0, 54.0), (4.0, 18.0, 48.0), (4.0, 18.0, -126.0), (4.0, 116.0, -126.0)],
                 ["w_purple", "w_white"], orient="H")

    route_bundle("J13_DHT11_D2", (31.54, 4.50), anchors["dht11"],
                 [(-126.0, 18.0, 52.0), (-14.0, 18.0, 46.0), (-14.0, 18.0, -126.0), (-42.0, 18.0, -126.0)],
                 ["w_red", "w_blue", "w_black"], orient="H")

    route_bundle("J15_KY037_D5", (74.50, 28.04), anchors["ky037"],
                 [(-72.0, 18.0, 58.0), (-15.0, 18.0, 52.0)],
                 ["w_red", "w_black", "w_yellow"], orient="V")

    route_bundle("J6_BUZZ_D8", (74.50, 50.77), anchors["buzzer"],
                 [(-74.0, 16.0, 50.0), (-5.0, 16.0, 46.0)],
                 ["w_orange", "w_black"], orient="V")

    route_bundle("J7_RLY1_D6", (74.50, 40.04), anchors["rly1_in"],
                 [(-74.0, 14.0, 86.0)],
                 ["w_red", "w_black", "w_green"], orient="V")

    route_bundle("J8_RLY1_SW", (16.50, 17.77), anchors["rly1_sw"],
                 [(-142.0, 15.0, 62.0), (-26.0, 15.0, 62.0)],
                 ["w_red", "w_yellow"], orient="V")

    route_bundle("J2_PUMP_OUT", (6.50, 19.04), anchors["pump"],
                 [(-164.0, 14.0, 84.0), (-164.0, 14.0, 144.0), (26.0, 14.0, 144.0), (36.0, 42.0, 78.0)],
                 ["w_red", "w_black"], orient="SCREW")

    route_bundle("J9_RLY2_D7", (18.54, 60.50), anchors["rly2_in"],
                 [(-136.0, 14.0, 138.0), (-74.0, 14.0, 138.0)],
                 ["w_red", "w_black", "w_cyan"], orient="H")

    route_bundle("J10_RLY2_SW", (32.27, 60.50), anchors["rly2_sw"],
                 [(-122.0, 14.0, 140.0), (-24.0, 14.0, 140.0)],
                 ["w_red", "w_orange"], orient="H")

    route_bundle("J11_AMP_PWR", (44.77, 60.50), anchors["pam_pwr"],
                 [(-108.0, 14.0, 142.0), (2.0, 14.0, 142.0)],
                 ["w_red", "w_black"], orient="H")

    route_bundle("J12_AUDIO_D3", (57.77, 60.50), anchors["pam_aud"],
                 [(-96.0, 15.0, 136.0), (-4.0, 15.0, 136.0)],
                 ["w_white", "w_black"], orient="H")

    # PAM8403 output -> 28mm mini round speaker
    add_tube("Wire_PAM_Spk_Pos", [anchors["pam_out"], (0.0, 11.5, 102.0), (0.0, 9.5, 91.0)], WR, mats["w_yellow"], parent=wires)
    add_tube("Wire_PAM_Spk_Neg", [(anchors["pam_out"][0] + 2.5, anchors["pam_out"][1], anchors["pam_out"][2]),
                                  (3.5, 11.5, 102.0), (3.5, 9.5, 91.0)], WR, mats["w_black"], parent=wires)

    route_bundle("J14_SOIL_A0", (17.04, 4.50), anchors["soil"],
                 [(-140.0, 16.0, 56.0), (24.0, 16.0, 56.0), (24.0, 16.0, 140.0)],
                 ["w_red", "w_black", "w_green"], orient="H")

    return wires


# ==============================================================================
# 5. STUDIO LIGHTING, CAMERAS, SCENE_SPEC.json & HIGH-RES PNG RENDERS
# ==============================================================================
def setup_studio_lighting() -> None:
    scene = bpy.context.scene
    world = scene.world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.10, 0.14, 0.22, 1.0)
        bg.inputs["Strength"].default_value = 0.28

    def add_light(name: str, ltype: str, pos_mm: tuple[float, float, float], target_mm: tuple[float, float, float],
                  energy: float, color=(1.0, 1.0, 1.0), size_mm: float = 160.0) -> None:
        ldata = bpy.data.lights.new(name=name, type=ltype)
        ldata.energy = energy
        ldata.color = color
        if ltype == "AREA":
            ldata.size = size_mm * MM
        lobj = bpy.data.objects.new(name=name, object_data=ldata)
        bpy.context.collection.objects.link(lobj)
        lobj.location = to_bpos_mm(*pos_mm)
        direction = to_bpos_mm(*target_mm) - lobj.location
        lobj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    # Balanced 3-point studio lighting (rich contrast, deep PCB emerald, crisp soft shadows)
    add_light("KeyLight",  "AREA", (260.0, 360.0, 280.0),  (0.0, 40.0, 10.0),   1400.0, (1.00, 0.96, 0.90), 220.0)
    add_light("FillLight", "AREA", (-320.0, 240.0, 220.0), (-40.0, 30.0, 40.0),  580.0, (0.82, 0.90, 1.00), 260.0)
    add_light("RimLight",  "AREA", (40.0, 260.0, -320.0),  (0.0, 40.0, 0.0),     520.0, (0.88, 0.94, 1.00), 240.0)
    add_light("TechSpot",  "AREA", (-75.0, 175.0, 195.0),  (-75.0, 15.0, 99.0),  280.0, (1.00, 0.98, 0.94), 120.0)


def create_camera(name: str, eye_mm: tuple[float, float, float], target_mm: tuple[float, float, float], lens_mm: float = 40.0) -> bpy.types.Object:
    cdata = bpy.data.cameras.new(name)
    cdata.lens = lens_mm
    cdata.clip_start = 0.05
    cdata.clip_end = 200.0
    cam = bpy.data.objects.new(name, cdata)
    bpy.context.collection.objects.link(cam)
    cam.location = to_bpos_mm(*eye_mm)
    direction = to_bpos_mm(*target_mm) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cam


def spherical_from_eye_target(eye_mm: tuple[float, float, float], tgt_mm: tuple[float, float, float]) -> dict[str, float]:
    """Compute house3d.js spherical camera preset (theta, phi, radius, targetX/Y/Z) in glTF units."""
    ex, ey, ez = [v * MM for v in eye_mm]
    tx, ty, tz = [v * MM for v in tgt_mm]
    dx, dy, dz = ex - tx, ey - ty, ez - tz
    radius = math.sqrt(dx * dx + dy * dy + dz * dz)
    phi = math.acos(max(-1.0, min(1.0, dy / radius)))
    theta = math.atan2(dx, dz)
    return {
        "theta": round(theta, 4),
        "phi": round(phi, 4),
        "radius": round(radius, 4),
        "targetX": round(tx, 4),
        "targetY": round(ty, 4),
        "targetZ": round(tz, 4),
        "eye_gltf": [round(ex, 4), round(ey, 4), round(ez, 4)],
        "target_gltf": [round(tx, 4), round(ty, 4), round(tz, 4)],
    }


def collect_contract_nodes() -> list[str]:
    return [
        "door_pivot",
        "main_door_leaf",
        "led_living_room",
        "led_bedroom",
        "pump_unit",
        "water_tube",
        "relay1_pump",
        "relay2_speaker",
        "buzzer_alarm",
        "speaker_mini",
        "pam8403_module",
        "sensor_dht11",
        "sensor_soil",
        "sensor_mic_ky037",
        "kicad_pcb_hub",
        "nodemcu_esp8266",
    ]


def write_scene_spec() -> None:
    bpy.context.view_layer.update()
    # Compute global glTF bounding box (+Y up: glTF X = B.x, Y = B.z, Z = -B.y)
    gmin = [1e9, 1e9, 1e9]
    gmax = [-1e9, -1e9, -1e9]
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            for c in obj.bound_box:
                w = obj.matrix_world @ Vector(c)
                gx, gy, gz = w.x, w.z, -w.y
                gmin[0] = min(gmin[0], gx)
                gmin[1] = min(gmin[1], gy)
                gmin[2] = min(gmin[2], gz)
                gmax[0] = max(gmax[0], gx)
                gmax[1] = max(gmax[1], gy)
                gmax[2] = max(gmax[2], gz)

    node_positions = {}
    for nname in collect_contract_nodes():
        obj = bpy.data.objects.get(nname)
        if obj is not None:
            w = obj.matrix_world.translation
            node_positions[nname] = {
                "gltf_xyz": [round(w.x, 4), round(w.z, 4), round(-w.y, 4)],
                "physical_mm": [round(w.x / MM, 2), round(w.z / MM, 2), round(-w.y / MM, 2)],
            }

    spec = {
        "schema_version": "2.0",
        "model_file": "simulator/static/models/smarthome_villa.glb",
        "blend_file": "hardware/blender/smarthome_open_house.blend",
        "kicad_pcb_source": "hardware/kicad/smarthome_hub/3d/smarthome_hub.glb",
        "units": "glTF meters (uniformly scaled 25x from 1:1 physical tabletop millimeters to fit house3d.js camera bounds)",
        "scale_mm_to_gltf": MM,
        "physical_scale_ratio": SCENE_SCALE,
        "physical_dimensions_mm": {
            "tabletop_plinth": [404.0, 9.0, 324.0],
            "open_cutaway_house": [356.0, 135.0, 178.0],
            "kicad_pcb_hub": [80.0, 17.3, 65.0],
            "nodemcu_esp8266": [25.4, 7.14, 49.4],
            "sg90_servo_body": [22.8, 22.5, 12.2],
            "sg90_servo_envelope": [32.2, 31.0, 12.2],
            "relay1_pump": [50.0, 18.5, 26.0],
            "relay2_speaker": [50.0, 18.5, 26.0],
            "pam8403_module": [21.0, 3.1, 18.0],
            "speaker_mini": [28.0, 5.2, 28.0],
            "pump_unit": [24.0, 33.0, 45.0],
            "buzzer_alarm": [12.0, 12.0, 9.5],
            "led_5mm_body": [5.8, 5.8, 8.6],
            "sensor_dht11": [14.0, 28.0, 7.1],
            "soil_probe_yl69": [20.0, 60.0, 1.6],
            "soil_lm393_board": [32.0, 12.1, 14.0],
            "sensor_mic_ky037": [35.0, 13.1, 15.0],
        },
        "bounding_box_gltf": {
            "min": [round(v, 4) for v in gmin],
            "max": [round(v, 4) for v in gmax],
            "extents": [round(gmax[i] - gmin[i], 4) for i in range(3)],
        },
        "camera_presets": {
            "overview": spherical_from_eye_target((195.0, 325.0, 465.0), (-4.0, 36.0, 12.0)),
            "living":   spherical_from_eye_target((-10.0, 210.0, 210.0), (-92.0, 48.0, -48.0)),
            "bedroom":  spherical_from_eye_target((160.0, 210.0, 210.0), (88.0, 45.0, -56.0)),
            "door":     spherical_from_eye_target((-60.0, 115.0, 215.0), (-90.0, 52.0, 40.0)),
            "garden":   spherical_from_eye_target((155.0, 130.0, 255.0), (102.0, 30.0, 100.0)),
            "board":    spherical_from_eye_target((-92.0, 138.0, 252.0), (-74.0, 16.0, 98.0)),
        },
        "contract_nodes": node_positions,
        "removed_devices": ["fan", "ac", "ir_vs1838b", "ir_led_940nm"],
    }
    OUT_SPEC.parent.mkdir(parents=True, exist_ok=True)
    OUT_SPEC.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"[SPEC] Wrote {OUT_SPEC}")


def render_presentation_views(render_dir: pathlib.Path) -> None:
    render_dir.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1066
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"
    scene.view_settings.exposure = -0.35

    cam_overview = create_camera("Cam_Overview", (195.0, 325.0, 465.0), (-4.0, 36.0, 12.0), lens_mm=40.0)
    cam_pcb = create_camera("Cam_PCB_Closeup", (-92.0, 138.0, 252.0), (-74.0, 16.0, 98.0), lens_mm=36.0)

    for cam, fname in [
        (cam_overview, "05_blender_house_overview.png"),
        (cam_pcb, "06_blender_pcb_closeup.png"),
    ]:
        scene.camera = cam
        out_png = render_dir / fname
        scene.render.filepath = str(out_png)
        bpy.ops.render.render(write_still=True)
        print(f"[RENDER] Saved {out_png} ({out_png.stat().st_size} bytes)")


def main() -> None:
    render_dir = None
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1:]
        if "--render-dir" in args:
            idx = args.index("--render-dir")
            if idx + 1 < len(args):
                render_dir = pathlib.Path(args[idx + 1])

    clear_scene()
    mats = build_materials()
    build_open_cutaway_house(mats)
    import_kicad_pcb_and_nodemcu(mats)
    anchors = build_hardware_devices_and_sensors(mats)
    build_dupont_wires(mats, anchors)
    convert_curves_to_meshes()
    setup_studio_lighting()

    # Save native Blender source file (with default overview camera)
    cam_default = create_camera("Camera", (195.0, 295.0, 405.0), (0.0, 42.0, 14.0), lens_mm=42.0)
    bpy.context.scene.camera = cam_default

    OUT_BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))
    print(f"[BLEND] Saved {OUT_BLEND} ({OUT_BLEND.stat().st_size} bytes)")

    write_scene_spec()

    # Export optimized PBR GLB (exclude lights & cameras so Three.js loads clean geometry + hierarchy)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.data.objects:
        if obj.type not in ("CAMERA", "LIGHT"):
            obj.select_set(True)

    OUT_GLB.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(OUT_GLB),
        export_format="GLB",
        use_selection=True,
        export_yup=True,
        export_apply=False,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
    )
    print(f"[GLB] Exported {OUT_GLB} ({OUT_GLB.stat().st_size} bytes)")

    if render_dir is not None:
        render_presentation_views(render_dir)


if __name__ == "__main__":
    main()
