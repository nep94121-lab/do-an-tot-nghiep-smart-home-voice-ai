"""Blender 5.2 (bpy) Open-Cutaway Smart Home 3D Tabletop Model Builder (PCB-Direct, Zero Breadboard).

Builds a coherent 1:1 physical tabletop cutaway house (406x390 mm base, 386x190x147 mm cutaway house)
synchronized 100% with:
  - `hardware/component_dimensions_ssot.py` (canonical 26-item datasheet SSOT; NodeMCU v2 Amica 48.26x25.40 mm)
  - `hardware/mica/mica_design.py` (exact relocated mount coordinates so all 40 wires <= 30.0 cm)
  - `hardware/kicad/smarthome_hub/3d/smarthome_hub.glb` (51 footprints incl. on-board C8 100nF & C9 100uF 16V)
  - `hardware/wire_lengths.json` (all 40 routed 3D wire polylines `smooth_waypoints_house_mm`, exact `color_hex`)

Coordinate contract (matches `scripts/compute_wire_lengths.py` `house_mm_to_three_mm` & `waypoints_threejs` to 0.00 mm):
  - House world mm (`mica_design.py`): X in [0..406], Y in [0..390], Z in [-3..147]
  - Three.js / glTF tabletop mm:       tx = hx - 203.0, ty = hz, tz = 235.0 - hy
  - glTF meters (`scale_mm_to_gltf`):  0.025 (25x tabletop scale, +Y up)
  - Blender world units (+Z up):       (tx * 0.025, -tz * 0.025, ty * 0.025)

Outputs:
  - hardware/blender/smarthome_open_house.blend
  - hardware/blender/SCENE_SPEC.json
  - web/models/smarthome_villa.glb  (<10 MB optimized PBR GLB, 16/16 required contract nodes, 0 forbidden items)
  - Optional studio renders when invoked with `-- --render-dir <dir>` or explicit `--overview-png` / `--interior-png`.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys
import bpy
import bmesh
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Euler, Vector

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
MICA_DIR = REPO_ROOT / "hardware" / "mica"
if str(MICA_DIR) not in sys.path:
    sys.path.insert(0, str(MICA_DIR))
PRINT3D_SCRIPTS = REPO_ROOT / "hardware" / "in 3 d" / "scripts"
if str(PRINT3D_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PRINT3D_SCRIPTS))

from hardware.component_dimensions_ssot import COMPONENT_DIM_MAP, SG90_MECHANICAL_SPECS  # noqa: E402
from hardware.wiring_contract import HUB_CONNECTOR_MAP, HUB_CONNECTORS  # noqa: E402
import lightweight_policy as lw_policy  # noqa: E402
import mica_design as md  # noqa: E402

KICAD_PCB_GLB = REPO_ROOT / "hardware" / "kicad" / "smarthome_hub" / "3d" / "smarthome_hub.glb"
WIRE_LENGTHS_JSON = REPO_ROOT / "hardware" / "wire_lengths.json"
OUT_BLEND = REPO_ROOT / "hardware" / "blender" / "smarthome_open_house.blend"
OUT_SPEC = REPO_ROOT / "hardware" / "blender" / "SCENE_SPEC.json"
OUT_GLB = REPO_ROOT / "web" / "models" / "smarthome_villa.glb"

# Uniform display scale: 1 physical mm = 0.025 glTF units (25x tabletop scale).
SCENE_SCALE = 25.0
MM = 0.001 * SCENE_SCALE  # 0.025 units per mm

# Exact house_mm -> Three.js mm transform (synchronized with scripts/compute_wire_lengths.py)
HOUSE_TO_THREE_OFFSET_X = -203.0
HOUSE_TO_THREE_OFFSET_Y_INV = 235.0


def house_to_three_mm(hx: float, hy: float, hz: float) -> tuple[float, float, float]:
    """Convert mica_design.py house world mm (X right, Y rear, Z up) to Three.js mm (X right, Y up, Z front)."""
    return (hx + HOUSE_TO_THREE_OFFSET_X, hz, HOUSE_TO_THREE_OFFSET_Y_INV - hy)


def to_bpos_mm(tx_mm: float, ty_mm: float, tz_mm: float) -> Vector:
    """Convert Three.js coords in mm (X right, Y up, Z front) to Blender world units (X, -Z, Y)."""
    return Vector((tx_mm * MM, -tz_mm * MM, ty_mm * MM))


def to_bsize_mm(sx_mm: float, sy_mm: float, sz_mm: float) -> tuple[float, float, float]:
    """Convert Three.js dimensions in mm (W_x, H_y, D_z) to Blender (X, Y_depth, Z_up)."""
    return (sx_mm * MM, sz_mm * MM, sy_mm * MM)


def hex_to_linear_rgba(hex_str: str) -> tuple[float, float, float, float]:
    """Convert #RRGGBB hex string to Blender linear RGBA tuple."""
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return (0.5, 0.5, 0.5, 1.0)
    vals = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255.0
        # sRGB -> linear approximation for vibrant AgX color reproduction
        lin = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        vals.append(lin)
    return (vals[0], vals[1], vals[2], 1.0)


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


def add_box_house(
    name: str,
    hx0: float,
    hx1: float,
    hy0: float,
    hy1: float,
    hz0: float,
    hz1: float,
    mat: bpy.types.Material,
    parent=None,
    bevel_mm: float = 0.0,
) -> bpy.types.Object:
    """Create a box directly from mica_design.py house world mm bounds [hx0..hx1, hy0..hy1, hz0..hz1]."""
    cx, cy, cz = house_to_three_mm(0.5 * (hx0 + hx1), 0.5 * (hy0 + hy1), 0.5 * (hz0 + hz1))
    return add_box(name, cx, cy, cz, abs(hx1 - hx0), abs(hz1 - hz0), abs(hy1 - hy0), mat, parent=parent, bevel_mm=bevel_mm)


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
    res: int = 4,
    bevel_res: int = 2,
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


def add_honeycomb_wall_house(
    name: str,
    plane: str,
    fixed_0: float,
    fixed_1: float,
    u0: float,
    u1: float,
    v0: float,
    v1: float,
    mat_rim: bpy.types.Material,
    mat_web: bpy.types.Material,
    parent=None,
    keepout_uvs: tuple[tuple[float, float, float, float], ...] = (),
    rim_mm: float = 8.0,
    web_thick_mm: float = lw_policy.WEB_THICKNESS_MM,
    web_align: str = "high",
) -> int:
    """Build a coffered 3.0mm-rim / 2.2mm-web wall with regular hexagonal honeycomb through-cutouts.

    Coordinates are in mica_design.py house world mm:
      - plane == "Y": thickness along Y [fixed_0..fixed_1], u = X, v = Z.
      - plane == "X": thickness along X [fixed_0..fixed_1], u = Y, v = Z.
    Returns the exact number of hexagonal through-cutouts punched into the 2.2 mm web.
    """
    wu0, wu1 = u0 + rim_mm, u1 - rim_mm
    wv0, wv1 = v0 + rim_mm, v1 - rim_mm
    if wu1 - wu0 < 22.0 or wv1 - wv0 < 18.0:
        if plane == "Y":
            add_box_house(name, u0, u1, fixed_0, fixed_1, v0, v1, mat_rim, parent=parent, bevel_mm=0.2)
        else:
            add_box_house(name, fixed_0, fixed_1, u0, u1, v0, v1, mat_rim, parent=parent, bevel_mm=0.2)
        return 0

    def _box(bname: str, bu0: float, bu1: float, bv0: float, bv1: float) -> None:
        if bu1 - bu0 <= 0.05 or bv1 - bv0 <= 0.05:
            return
        if plane == "Y":
            add_box_house(bname, bu0, bu1, fixed_0, fixed_1, bv0, bv1, mat_rim, parent=parent, bevel_mm=0.15)
        else:
            add_box_house(bname, fixed_0, fixed_1, bu0, bu1, bv0, bv1, mat_rim, parent=parent, bevel_mm=0.15)

    # Full 3.0 mm perimeter frame (bottom, top, left, right)
    _box(f"{name}_RimBot",   u0, u1, v0, wv0)
    _box(f"{name}_RimTop",   u0, u1, wv1, v1)
    _box(f"{name}_RimLeft",  u0, wu0, wv0, wv1)
    _box(f"{name}_RimRight", wu1, u1, wv0, wv1)

    # Full 3.0 mm solid keepout islands (e.g. DHT11 mounting collar on P06)
    for k_idx, (ku0, kv0, ku1, kv1) in enumerate(keepout_uvs):
        _box(f"{name}_Keepout_{k_idx}", max(wu0, ku0), min(wu1, ku1), max(wv0, kv0), min(wv1, kv1))

    # Recessed 2.2 mm coffered web (flush on outer/aligned face -> visible 0.8 mm coffered step)
    if web_align == "low":
        f_mid = fixed_0 + 0.5 * web_thick_mm
    elif web_align == "center":
        f_mid = 0.5 * (fixed_0 + fixed_1)
    else:  # "high"
        f_mid = fixed_1 - 0.5 * web_thick_mm

    # Regular pointy-top hexagon grid matching lightweight_policy.py (15.0 mm flat-to-flat, 3.2 mm rib)
    hex_f = float(lw_policy.HEX_FLAT_TO_FLAT_MM)
    hex_r = hex_f / math.sqrt(3.0)
    hex_half_w = 0.5 * hex_f
    pitch_u = hex_f + float(lw_policy.HEX_MIN_RIB_MM)
    pitch_v = pitch_u * math.sqrt(3.0) / 2.0
    web_margin = max(2.5, float(lw_policy.HEX_EDGE_MARGIN_MM) - rim_mm + 2.5)
    keepout_margin = float(lw_policy.HEX_EDGE_MARGIN_MM)

    u_mid = 0.5 * (wu0 + wu1)
    v_mid = 0.5 * (wv0 + wv1)

    hex_centers: list[tuple[float, float]] = []
    n_rows = int(math.floor((wv1 - wv0) / pitch_v)) + 2
    n_cols = int(math.floor((wu1 - wu0) / pitch_u)) + 2
    for row in range(-n_rows, n_rows + 1):
        hv = v_mid + row * pitch_v
        if hv - hex_r < wv0 + web_margin or hv + hex_r > wv1 - web_margin:
            continue
        row_shift = 0.5 * pitch_u if (row % 2 != 0) else 0.0
        for col in range(-n_cols, n_cols + 1):
            hu = u_mid + col * pitch_u + row_shift
            if hu - hex_half_w < wu0 + web_margin or hu + hex_half_w > wu1 - web_margin:
                continue
            blocked = False
            for (ku0, kv0, ku1, kv1) in keepout_uvs:
                if (hu + hex_half_w > ku0 - keepout_margin and hu - hex_half_w < ku1 + keepout_margin
                        and hv + hex_r > kv0 - keepout_margin and hv - hex_r < kv1 + keepout_margin):
                    blocked = True
                    break
            if not blocked:
                hex_centers.append((hu, hv))

    # Build extruded 2D curve mesh (outer web rectangle minus hexagonal hole splines -> zero Boolean artifacts)
    curve_data = bpy.data.curves.new(name + "_WebCurve", type="CURVE")
    curve_data.dimensions = "2D"
    curve_data.fill_mode = "BOTH"
    curve_data.extrude = 0.5 * web_thick_mm * MM
    curve_data.resolution_u = 1

    half_wu = 0.5 * (wu1 - wu0) * MM
    half_wv = 0.5 * (wv1 - wv0) * MM
    outer = curve_data.splines.new("POLY")
    outer.points.add(3)
    for idx, (lx, ly) in enumerate([(-half_wu, -half_wv), (half_wu, -half_wv), (half_wu, half_wv), (-half_wu, half_wv)]):
        outer.points[idx].co = (lx, ly, 0.0, 1.0)
    outer.use_cyclic_u = True

    for hu, hv in hex_centers:
        sp = curve_data.splines.new("POLY")
        sp.points.add(5)
        for k in range(6):
            ang = math.radians(30.0 + 60.0 * k)  # pointy-top hexagon (flat sides vertical)
            lx = (hu + hex_r * math.cos(ang) - u_mid) * MM
            ly = (hv + hex_r * math.sin(ang) - v_mid) * MM
            sp.points[k].co = (lx, ly, 0.0, 1.0)
        sp.use_cyclic_u = True

    web_obj = bpy.data.objects.new(f"{name}_HoneycombWeb", curve_data)
    bpy.context.collection.objects.link(web_obj)
    web_obj.data.materials.append(mat_web)
    if parent is not None:
        web_obj.parent = parent
    if plane == "Y":
        tx, ty, tz = house_to_three_mm(u_mid, f_mid, v_mid)
        web_obj.location = to_bpos_mm(tx, ty, tz)
        web_obj.rotation_euler = Euler((math.pi / 2.0, 0.0, 0.0), "XYZ")
    else:
        tx, ty, tz = house_to_three_mm(f_mid, u_mid, v_mid)
        web_obj.location = to_bpos_mm(tx, ty, tz)
        web_obj.rotation_euler = Euler((math.pi / 2.0, 0.0, math.pi / 2.0), "XYZ")

    return len(hex_centers)


def convert_curves_to_meshes() -> None:
    """Convert all CURVE wire/tube/honeycomb objects to clean low-poly MESH before GLB export."""
    bpy.ops.object.select_all(action="DESELECT")
    curves = [o for o in bpy.data.objects if o.type == "CURVE"]
    for obj in curves:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.convert(target="MESH")
        obj.select_set(False)


# ==============================================================================
# MATERIALS PALETTE
# ==============================================================================
def build_materials() -> dict[str, bpy.types.Material]:
    return {
        # Architectural open-cutaway house materials
        "plinth":      make_mat("TabletopPlinth",   (0.11, 0.14, 0.20, 1.0), roughness=0.45, metallic=0.15),
        "plinth_trim": make_mat("PlinthEdgeTrim",   (0.20, 0.26, 0.35, 1.0), roughness=0.35, metallic=0.35),
        "tech_deck":   make_mat("TechBayDeck",      (0.15, 0.18, 0.24, 1.0), roughness=0.42, metallic=0.12),
        "pcb_plate":   make_mat("P16_PCB_Plate",    (0.22, 0.34, 0.38, 1.0), roughness=0.38, metallic=0.10),
        "oak_floor":   make_mat("OakFloorLiving",   (0.56, 0.39, 0.23, 1.0), roughness=0.40),
        "walnut_flr":  make_mat("WalnutFloorBed",   (0.38, 0.25, 0.16, 1.0), roughness=0.42),
        "wall_cream":  make_mat("WallOffWhite",     (0.92, 0.91, 0.88, 1.0), roughness=0.65),
        "wall_web":    make_mat("WallHoneycombWeb", (0.86, 0.85, 0.82, 1.0), roughness=0.62),
        "wall_trim":   make_mat("WallCharcoalCap",  (0.16, 0.20, 0.27, 1.0), roughness=0.40, metallic=0.20),
        "door_wood":   make_mat("MainDoorOak",      (0.45, 0.26, 0.13, 1.0), roughness=0.38),
        "glass":       make_mat("ClearGlass",       (0.68, 0.88, 0.98, 0.30), roughness=0.06, metallic=0.08, alpha=0.30),
        "water_tank":  make_mat("WaterReservoir",   (0.30, 0.72, 0.95, 0.45), roughness=0.05, alpha=0.45),
        "water_tube":  make_mat("SiliconeTube",     (0.76, 0.92, 0.98, 0.62), roughness=0.18, alpha=0.62),
        "terracotta":  make_mat("PlanterClay",      (0.56, 0.27, 0.15, 1.0), roughness=0.72),
        "soil_dark":   make_mat("GardenSoil",       (0.16, 0.10, 0.06, 1.0), roughness=0.92),

        # Real electronic component materials
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
        "pla_mount":   make_mat("PLA_SnapMount",    (0.56, 0.70, 0.80, 1.0), roughness=0.40, metallic=0.04),
        "pla_coupler": make_mat("PLA_HornCoupler",  (0.92, 0.44, 0.10, 1.0), roughness=0.35, metallic=0.05),
        "plug_yellow": make_mat("DCPlugYellowTip",  (0.95, 0.78, 0.06, 1.0), roughness=0.32),
        "led_lr":      make_mat("LED_LivingWarm",   (1.00, 0.92, 0.65, 1.0), roughness=0.12, emission=(1.0, 0.88, 0.48), emission_strength=6.5),
        "led_br":      make_mat("LED_BedroomWarm",  (1.00, 0.84, 0.48, 1.0), roughness=0.12, emission=(1.0, 0.76, 0.32), emission_strength=5.8),
        "led_lr_halo": make_mat("LED_LivingHalo",   (1.00, 0.90, 0.55, 0.24), roughness=0.10, emission=(1.0, 0.86, 0.42), emission_strength=3.5, alpha=0.24),
        "led_br_halo": make_mat("LED_BedroomHalo",  (1.00, 0.78, 0.40, 0.24), roughness=0.10, emission=(1.0, 0.74, 0.30), emission_strength=3.2, alpha=0.24),
        "led_red":     make_mat("LED_StatusRed",    (0.95, 0.14, 0.12, 1.0), roughness=0.18, emission=(0.95, 0.12, 0.10), emission_strength=1.4),
        "led_grn":     make_mat("LED_StatusGreen",  (0.12, 0.88, 0.28, 1.0), roughness=0.18, emission=(0.12, 0.88, 0.28), emission_strength=1.8),
        "jumper_yel":  make_mat("JumperYellow",     (0.95, 0.76, 0.04, 1.0), roughness=0.34),
        "callout_j1":  make_mat("Callout_J1_In",    (0.95, 0.16, 0.14, 1.0), roughness=0.28, emission=(0.95, 0.20, 0.12), emission_strength=1.2),
        "callout_j2":  make_mat("Callout_J2_Pump",  (0.06, 0.74, 0.92, 1.0), roughness=0.28, emission=(0.06, 0.74, 0.92), emission_strength=1.0),
        "callout_sw":  make_mat("Callout_RelaySw",  (0.96, 0.68, 0.08, 1.0), roughness=0.28, emission=(0.96, 0.68, 0.08), emission_strength=1.0),
        "callout_amp": make_mat("Callout_AmpOut",   (0.14, 0.84, 0.42, 1.0), roughness=0.28, emission=(0.14, 0.84, 0.42), emission_strength=1.0),

        # Top-side PCB jumper wire materials
        "w_red":       make_mat("WireRed_5V",       (0.86, 0.12, 0.12, 1.0), roughness=0.38),
        "w_orange":    make_mat("WireOrange_Sig",   (0.95, 0.46, 0.08, 1.0), roughness=0.38),
    }


# ==============================================================================
# 1. OPEN-CUTAWAY ARCHITECTURAL HOUSE (EXACT MATCH TO mica_design.py 406x390 mm)
# ==============================================================================
def build_open_cutaway_house(mats: dict[str, bpy.types.Material]) -> tuple[bpy.types.Object, int]:
    arch = make_group("OpenCutawayHouse", 0.0, 0.0, 0.0)
    honeycomb_total = 0

    # Tabletop base plinth: 406 x 390 x 9 mm (top surface at house Z = 0.0 mm) — CLOSED under electrical tech bay & water/planter
    add_box_house("TabletopPlinth", 0.0, 406.0, 0.0, 390.0, -9.0, 0.0, mats["plinth"], parent=arch, bevel_mm=1.0)
    add_box_house("PlinthTrim",     4.0, 402.0, 4.0, 386.0, -0.6, 0.2, mats["plinth_trim"], parent=arch)

    # Room floors (house Z = 0..1.5 mm)
    add_box_house("LivingRoomFloor",  13.0, 198.5, 195.0, 379.0, 0.0, 1.5, mats["oak_floor"], parent=arch)
    add_box_house("BedroomFloor",    201.5, 393.0, 195.0, 379.0, 0.0, 1.5, mats["walnut_flr"], parent=arch)

    # Technical Bay Deck (X: 8..258, Y: 10..174, thin 1.2mm CLOSED solid mat so all module Zs match mica_design.py)
    add_box_house("TechBayDeck", 8.0, 258.0, 10.0, 174.0, 0.0, 1.2, mats["tech_deck"], parent=arch)

    # P16_PCB_PLATE (130x110x3 mm at X=57..187, Y=49..159, Z=6..9) + 4 corner risers (Z=0..6)
    add_box_house("P16_PCB_Plate", 57.0, 187.0, 49.0, 159.0, 6.0, 9.0, mats["pcb_plate"], parent=arch, bevel_mm=0.3)
    for idx, (rx, ry) in enumerate([(64.0, 152.0), (180.0, 152.0), (64.0, 56.0), (180.0, 56.0)], 1):
        tx, ty, tz = house_to_three_mm(rx, ry, 3.0)
        add_cyl(f"P16_Riser_{idx}", tx, ty, tz, 3.0, 6.0, mats["plinth_trim"], parent=arch, segs=12)

    # Relay 1 & Relay 2 mounting standoffs (Z = 0..8.0 mm under relays at (226,136) and (226,92))
    for r_idx, (rcx, rcy) in enumerate([(226.0, 136.0), (226.0, 92.0)], 1):
        for k, (dx, dy) in enumerate([(-22.25, -10.25), (22.25, -10.25), (-22.25, 10.25), (22.25, 10.25)], 1):
            tx, ty, tz = house_to_three_mm(rcx + dx, rcy + dy, 4.0)
            add_cyl(f"Relay{r_idx}_Standoff_{k}", tx, ty, tz, 2.2, 8.0, mats["plinth_trim"], parent=arch, segs=10)

    # WALLS (3.0 mm full-thickness structural rims/joints + 2.2 mm coffered honeycomb webs on non-load-bearing living/bedroom walls)
    WALL_H = 147.0
    CUT_H = 34.0

    # P02_WALL_BACK: X in [10..396], Y in [379..382], Bedroom window X in [238..362], Z in [46..110]
    # Center T-spine X=[190..210] stays full 3.0 mm solid; Living Room field X=[10..190] & below-window field X=[238..362] get 2.2 mm honeycomb cutouts
    honeycomb_total += add_honeycomb_wall_house(
        "BackWallLiving", "Y", 379.0, 382.0, 10.0, 190.0, 0.0, WALL_H,
        mats["wall_cream"], mats["wall_web"], parent=arch, web_align="high",
    )
    add_box_house("BackWallMidSpine", 190.0, 210.0, 379.0, 382.0,   0.0, WALL_H, mats["wall_cream"], parent=arch, bevel_mm=0.2)
    add_box_house("BackWallBedLeft",  210.0, 238.0, 379.0, 382.0,   0.0, WALL_H, mats["wall_cream"], parent=arch, bevel_mm=0.2)
    honeycomb_total += add_honeycomb_wall_house(
        "BackWallBedBot", "Y", 379.0, 382.0, 238.0, 362.0, 0.0, 46.0,
        mats["wall_cream"], mats["wall_web"], parent=arch, rim_mm=7.5, web_align="high",
    )
    add_box_house("BackWallBedTop",   238.0, 362.0, 379.0, 382.0, 110.0, WALL_H, mats["wall_cream"], parent=arch, bevel_mm=0.2)
    add_box_house("BackWallBedRight", 362.0, 396.0, 379.0, 382.0,   0.0, WALL_H, mats["wall_cream"], parent=arch, bevel_mm=0.2)
    add_box_house("BedWindowGlass",   238.0, 362.0, 379.6, 381.4,  46.0,  110.0, mats["glass"],      parent=arch)
    add_box_house("BedWindowFrmTop",  236.0, 364.0, 378.5, 382.5, 109.0,  112.0, mats["wall_trim"],  parent=arch)
    add_box_house("BedWindowFrmBot",  236.0, 364.0, 378.5, 382.5,  44.0,   47.0, mats["wall_trim"],  parent=arch)
    add_box_house("BackWallCap",       10.0, 396.0, 378.5, 382.5, WALL_H, WALL_H + 2.5, mats["wall_trim"], parent=arch)

    # P03_WALL_LEFT: X in [10..13], Y in [192..382], step at Y = 256 (decorative wood slats removed; 2.2 mm honeycomb web on tall section)
    honeycomb_total += add_honeycomb_wall_house(
        "LeftWallBack", "X", 10.0, 13.0, 256.0, 379.0, 0.0, WALL_H,
        mats["wall_cream"], mats["wall_web"], parent=arch, web_align="low",
    )
    add_box_house("LeftWallFrontLow",  10.0, 13.0, 195.0, 256.0, 0.0,  CUT_H, mats["wall_cream"], parent=arch, bevel_mm=0.2)
    add_box_house("LeftWallCapBack",    9.5, 13.5, 256.0, 382.0, WALL_H, WALL_H + 2.5, mats["wall_trim"], parent=arch)
    add_box_house("LeftWallCapFront",   9.5, 13.5, 192.0, 256.0, CUT_H,  CUT_H + 2.0,  mats["wall_trim"], parent=arch)

    # P04_WALL_RIGHT: X in [393..396], Y in [192..382], step at Y = 264 (2.2 mm honeycomb web on tall section)
    honeycomb_total += add_honeycomb_wall_house(
        "RightWallBack", "X", 393.0, 396.0, 264.0, 379.0, 0.0, WALL_H,
        mats["wall_cream"], mats["wall_web"], parent=arch, web_align="high",
    )
    add_box_house("RightWallFrontLow", 393.0, 396.0, 195.0, 264.0, 0.0,  CUT_H, mats["wall_cream"], parent=arch, bevel_mm=0.2)
    add_box_house("RightWallCapBack",  392.5, 396.5, 264.0, 382.0, WALL_H, WALL_H + 2.5, mats["wall_trim"], parent=arch)
    add_box_house("RightWallCapFront", 392.5, 396.5, 192.0, 264.0, CUT_H,  CUT_H + 2.0,  mats["wall_trim"], parent=arch)

    # P06_WALL_MID: X in [198.5..201.5], Y in [195..379], interior doorway Y in [214..266] Z in [0..104]
    # Keep LED top band (MidWallDoorHeader) & buzzer front post (MidWallFrontLower) & DHT11 zone (Y=[266..314], Z=[68..114]) SOLID 3.0 mm!
    add_box_house("MidWallFrontLower", 198.5, 201.5, 195.0, 214.0,   0.0,  112.0, mats["wall_cream"], parent=arch)
    add_box_house("MidWallDoorHeader", 198.5, 201.5, 214.0, 266.0, 104.0, WALL_H, mats["wall_cream"], parent=arch)
    honeycomb_total += add_honeycomb_wall_house(
        "MidWallBack", "X", 198.5, 201.5, 266.0, 379.0, 0.0, WALL_H,
        mats["wall_cream"], mats["wall_web"], parent=arch,
        keepout_uvs=((266.0, 68.0, 314.0, 114.0),),  # P06_DHT11_ZONE solid 3.0 mm collar
        web_align="center",
    )
    add_box_house("MidWallBackCap",    198.0, 202.0, 214.0, 379.0, WALL_H, WALL_H + 2.5, mats["wall_trim"], parent=arch)

    # P05_WALL_FRONT: X in [10..396], Y in [192..195] — CLOSED & SOLID 3.0 mm (lower waist faces relays/PSU + door jamb + servo load path + center pillar)
    # Main Door opening X in [76..136], Z in [0..104]
    add_box_house("FrontCutawayLeft",  10.0,  38.0, 192.0, 195.0,   0.0,  CUT_H, mats["wall_cream"], parent=arch)
    add_box_house("FrontDoorPostL",    38.0,  76.0, 192.0, 195.0,   0.0,  120.0, mats["wall_cream"], parent=arch)
    add_box_house("FrontDoorPostR",   136.0, 148.0, 192.0, 195.0,   0.0,  120.0, mats["wall_cream"], parent=arch)
    add_box_house("FrontDoorHeader",   38.0, 148.0, 192.0, 195.0, 104.0,  120.0, mats["wall_trim"],  parent=arch)
    add_box_house("FrontKY037Ledge",  148.0, 188.0, 192.0, 195.0,   0.0,   48.0, mats["wall_cream"], parent=arch)
    add_box_house("FrontCenterPillar",188.0, 214.0, 192.0, 195.0,   0.0, WALL_H, mats["wall_cream"], parent=arch)
    add_box_house("FrontCenterCap",   187.5, 214.5, 191.5, 195.5, WALL_H, WALL_H + 2.5, mats["wall_trim"], parent=arch)
    add_box_house("FrontCutawayBed",  214.0, 396.0, 192.0, 195.0,   0.0,  CUT_H, mats["wall_cream"], parent=arch)
    add_box_house("FrontCutawayBedC", 214.0, 396.0, 191.5, 195.5, CUT_H,  CUT_H + 2.0, mats["wall_trim"], parent=arch)

    # P07_SERVO_SHELF: coaxial top-jamb horizontal SG90 mount shelf (X in [47..96], Y in [195.125..221.125], Z in [108.5..111.5])
    # SG90 cutout: X in [59.85..83.15], Y in [195.15..207.85] -> coaxial shaft at (77.0, 201.5)
    add_box_house("P07_ServoShelf_L",   47.0, 59.85, 195.125, 221.125, 108.5, 111.5, mats["wall_trim"], parent=arch, bevel_mm=0.2)
    add_box_house("P07_ServoShelf_R",   83.15, 96.0, 195.125, 221.125, 108.5, 111.5, mats["wall_trim"], parent=arch, bevel_mm=0.2)
    add_box_house("P07_ServoShelf_B",   59.85, 83.15, 207.85, 221.125, 108.5, 111.5, mats["wall_trim"], parent=arch, bevel_mm=0.2)
    add_box_house("P07_ServoShelf_Tab", 56.5, 86.5, 192.0, 195.15, 108.5, 111.5, mats["wall_trim"], parent=arch)

    # Integral non-stalling mechanical end-stop lugs on P07_SERVO_SHELF underside (Z = 98.5..108.5)
    add_box_house("P07_EndStop_Closed", 90.5, 94.5, 195.5, 198.7, 98.5, 108.5, mats["pla_coupler"], parent=arch, bevel_mm=0.2)
    add_box_house("P07_EndStop_Open",   70.3, 74.3, 212.0, 216.0, 98.5, 108.5, mats["pla_coupler"], parent=arch, bevel_mm=0.2)

    # SUP11_SG90_SNAP_SADDLE atop P07 (Z=111.5..115.2) clamping SG90 ears with center window for blue body
    add_box_house("SUP11_SG90_Saddle_L", 49.0, 59.7, 195.1, 207.9, 111.5, 115.2, mats["pla_mount"], parent=arch, bevel_mm=0.25)
    add_box_house("SUP11_SG90_Saddle_R", 83.3, 93.0, 195.1, 207.9, 111.5, 115.2, mats["pla_mount"], parent=arch, bevel_mm=0.25)
    add_box_house("SUP11_SG90_Saddle_B", 49.0, 93.0, 207.9, 211.5, 111.5, 115.2, mats["pla_mount"], parent=arch, bevel_mm=0.25)

    # Cable_Servo_D1 visual pass-through grommet ring on P05 (X=48.0, Y=193.5, Z=110.0)
    gx, gy, gz = house_to_three_mm(48.0, 193.5, 110.0)
    add_cyl("P05_CableServoGrommet", gx, gy, gz, 5.2, 3.6, mats["plastic_blk"], parent=arch, axis="Z", segs=20)

    # SUP10 fixed door-jamb hinge brackets on P05 at Z=18.0 and Z=78.0 -> coaxial pivot (77.0, 201.5)
    for htag, hz in [("Bot", 18.0), ("Top", 78.0)]:
        add_box_house(f"SUP10_FixedArm_{htag}", 70.0, 77.0, 195.0, 201.5, hz - 8.0, hz - 4.0, mats["pla_mount"], parent=arch, bevel_mm=0.2)
        add_box_house(f"SUP10_FixedArmU_{htag}", 70.0, 77.0, 195.0, 201.5, hz + 4.0, hz + 8.0, mats["pla_mount"], parent=arch, bevel_mm=0.2)
        kx, ky_l, kz = house_to_three_mm(77.0, 201.5, hz - 6.0)
        add_cyl(f"SUP10_FixedKnuckleL_{htag}", kx, ky_l, kz, 2.8, 4.0, mats["pla_mount"], parent=arch, segs=16)
        add_cyl(f"SUP10_FixedKnuckleU_{htag}", kx, hz + 6.0, kz, 2.8, 4.0, mats["pla_mount"], parent=arch, segs=16)
        add_cyl(f"SUP10_HingePin_{htag}", kx, hz, kz, 1.35, 17.0, mats["silver_mtl"], parent=arch, segs=14)

    # SUP18_BUZZER_SNAP_COLLAR behind P05_WALL_FRONT CenterPillar (strictly inside P06 relief zone Y<214, Z>112)
    add_box_house("SUP18_BuzzerSnapCollar_L", 193.0, 195.5, 195.0, 201.0, 116.5, 141.5, mats["pla_mount"], parent=arch, bevel_mm=0.2)
    add_box_house("SUP18_BuzzerSnapCollar_R", 204.5, 207.0, 195.0, 201.0, 116.5, 141.5, mats["pla_mount"], parent=arch, bevel_mm=0.2)
    add_box_house("SUP18_BuzzerSnapCollar_T", 193.0, 207.0, 195.0, 201.0, 134.0, 141.5, mats["pla_mount"], parent=arch, bevel_mm=0.2)
    add_box_house("SUP18_BuzzerSnapCollar_B", 193.0, 207.0, 195.0, 201.0, 116.5, 120.5, mats["pla_mount"], parent=arch, bevel_mm=0.2)

    # Exterior 5V 2A power cord stub exiting DC-022 barrel plug in front of P15_TECH_FASCIA
    add_tube(
        "DC022_ExtPowerCord",
        [
            (-173.0, 22.0, 241.5),
            (-173.5, 21.5, 248.0),
            (-178.0, 16.0, 253.5),
            (-186.0,  7.0, 256.0),
            (-196.0,  2.5, 256.0),
        ],
        radius_mm=1.9,
        mat=mats["plastic_blk"],
        parent=arch,
        res=6,
        bevel_res=3,
    )

    # P15_TECH_FASCIA: Front Technical Bay Power & Speaker Fascia (X in [8..254], Y in [10..13]) — CLOSED & SOLID 3.0 mm
    add_box_house("P15_PowerZone",     8.0,  64.0, 10.0, 13.0, 0.0, 42.0, mats["wall_trim"], parent=arch, bevel_mm=0.2)
    add_box_house("P15_USBCutaway",   64.0, 192.0, 10.0, 13.0, 0.0, 16.0, mats["wall_trim"], parent=arch, bevel_mm=0.2)
    add_box_house("P15_SpkBaffle",   192.0, 254.0, 10.0, 13.0, 0.0, 48.0, mats["wall_trim"], parent=arch, bevel_mm=0.2)

    # R6 Lightweight Policy: ALL decorative furniture (LivingSofa*, LivingPillow*, CoffeeTable*,
    # BedFrame, BedHeadboard, BedMattress, BedDuvet, BedPillow*, Nightstand, GardenStem_*, GardenFoliage*)
    # removed to save PLA and leave living/bedroom/garden inspection views 100% unobstructed.

    # Front-Right Water Tank (X in [266..318], Y in [26..152], H=54) & Garden Planter (X in [318..396], Y in [26..152], H=48)
    # Clear Water Reservoir walls (open top so pump & water level are clearly visible!)
    add_box_house("WaterTankLeft",   266.0, 269.0,  26.0, 152.0,  0.0, 54.0, mats["glass"], parent=arch)
    add_box_house("WaterTankDiv",    316.5, 319.5,  26.0, 152.0,  0.0, 54.0, mats["glass"], parent=arch)
    add_box_house("WaterTankFront",  269.0, 316.5,  26.0,  29.0,  0.0, 54.0, mats["glass"], parent=arch)
    add_box_house("WaterTankBack",   269.0, 316.5, 149.0, 152.0,  0.0, 54.0, mats["glass"], parent=arch)
    add_box_house("WaterLevel",      270.0, 315.5,  30.0, 148.0,  1.0, 26.0, mats["water_tank"], parent=arch)

    # Garden Planter walls + soil bed + P14_SOIL_BRIDGE (functional parts kept 100% intact; decorative stems/foliage removed)
    add_box_house("PlanterFront",    319.5, 396.0,  26.0,  29.0,  0.0, 48.0, mats["terracotta"], parent=arch)
    add_box_house("PlanterBack",     319.5, 396.0, 149.0, 152.0,  0.0, 48.0, mats["terracotta"], parent=arch)
    add_box_house("PlanterRight",    393.0, 396.0,  29.0, 149.0,  0.0, 48.0, mats["terracotta"], parent=arch)
    add_box_house("GardenSoilBed",   319.5, 393.0,  29.0, 149.0,  0.5, 30.0, mats["soil_dark"],  parent=arch)
    # P14_SOIL_BRIDGE across X in [342..374], Y in [29..149], Z in [45..48] (with visual rails flanking probe)
    add_box_house("P14_SoilBridge_F", 342.0, 374.0,  29.0,  76.0, 45.0, 48.0, mats["wall_trim"], parent=arch)
    add_box_house("P14_SoilBridge_B", 342.0, 374.0, 102.0, 149.0, 45.0, 48.0, mats["wall_trim"], parent=arch)

    print(f"[HOUSE] Built lightweight open-cutaway house (2.2 mm coffered webs, {honeycomb_total} honeycomb cutouts, 0 furniture)")
    return arch, honeycomb_total


# ==============================================================================
# 2. DIRECT IMPORT OF ACTUAL KICAD 3D PCB (`kicad_pcb_hub`) + NODEMCU (`nodemcu_esp8266`)
# ==============================================================================
HW_MAP = {h.part_id: h for h in md.HARDWARE_PARTS}
PCB_W_MM = float(COMPONENT_DIM_MAP["hub_pcb"].dims_mm[0])  # 100.0
PCB_H_MM = float(COMPONENT_DIM_MAP["hub_pcb"].dims_mm[1])  # 80.0
_PCB_HOUSE = HW_MAP["HW_PCB"].center_xyz  # (122.0, 104.0, 19.8)
PCB_CX_MM, _PCB_CY_MM, PCB_CZ_MM = house_to_three_mm(_PCB_HOUSE[0], _PCB_HOUSE[1], _PCB_HOUSE[2])
PCB_BOT_Y_MM = 19.0   # FR4 bottom sits at Z = 19.0 mm (10mm standoffs above P16_PCB_PLATE top at Z = 9.0 mm)

# Exact U1/U2 2x15 female socket center offset relative to 100x80mm PCB center (bx=48.43, by=41.22):
NODEMCU_DX_MM = -1.57
NODEMCU_DZ_MM = -1.22

# 7 top-side 22AWG insulated wire jumpers (JP1..JP7) from hardware/kicad/smarthome_hub/build_diy_hub.py
DIY_TOP_JUMPERS: tuple[tuple[str, tuple[float, float], tuple[float, float], str], ...] = (
    ("JP1", (43.00, 33.70), (55.70, 33.70), "w_orange"),
    ("JP2", (40.50, 18.00), (22.72, 18.00), "w_orange"),
    ("JP3", (76.00, 33.30), (76.00, 25.68), "w_orange"),
    ("JP4", (36.50, 60.00), (72.06, 60.00), "w_red"),
    ("JP5", (85.50, 64.28), (85.50, 51.58), "w_red"),
    ("JP6", (85.50, 47.00), (85.50, 26.68), "w_red"),
    ("JP7", (85.50, 12.70), (60.10, 12.70), "w_red"),
)


def pcb_pin_three_mm(x_rel_mm: float, y_rel_mm: float, z_top_offset_mm: float = 8.5) -> tuple[float, float, float]:
    """Convert KiCad PCB local mm (origin top-left 0..100, 0..80) to Three.js world mm."""
    tx = PCB_CX_MM + (x_rel_mm - PCB_W_MM * 0.5)
    tz = PCB_CZ_MM + (y_rel_mm - PCB_H_MM * 0.5)
    ty = PCB_BOT_Y_MM + 1.6 + z_top_offset_mm
    return (tx, ty, tz)


def import_kicad_pcb_and_nodemcu(mats: dict[str, bpy.types.Material]) -> tuple[bpy.types.Object, bpy.types.Object]:
    if not KICAD_PCB_GLB.exists():
        raise FileNotFoundError(f"KiCad 3D PCB GLB missing: {KICAD_PCB_GLB}")

    pcb_hub = make_group("kicad_pcb_hub", PCB_CX_MM, PCB_BOT_Y_MM, PCB_CZ_MM)

    # 4 Brass M3x10 standoffs (OD 5.0mm x 10.0mm) from P16_PCB_PLATE top (Y=9.0) to PCB bottom (Y=19.0)
    for idx, (hx, hy) in enumerate([(5.0, 5.0), (95.0, 5.0), (5.0, 75.0), (95.0, 75.0)]):
        add_cyl(
            f"PCB_Standoff_M3_{idx + 1}",
            hx - PCB_W_MM * 0.5, -5.0, hy - PCB_H_MM * 0.5,
            radius_mm=2.5, height_mm=10.0,
            mat=mats["brass"], parent=pcb_hub,
        )

    # Import the actual KiCad-exported 3D PCB GLB (51 footprints incl. on-board C8 100nF & C9 100uF 16V)
    before_objs = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(KICAD_PCB_GLB))
    imported = [o for o in bpy.data.objects if o not in before_objs]
    imported_roots = [o for o in imported if o.parent is None]

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
            if dx_m > 0.098 and dy_m > 0.078 and 0.001 < dz_m < 0.003:
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

    for r in imported_roots:
        r.parent = pcb_hub
        r.scale = (r.scale.x * SCENE_SCALE, r.scale.y * SCENE_SCALE, r.scale.z * SCENE_SCALE)
        r.location = Vector((
            (r.location.x - cx_m) * SCENE_SCALE,
            (r.location.y - cy_m) * SCENE_SCALE,
            (r.location.z - z_align_m) * SCENE_SCALE,
        ))

    # 7 physical top-side 22AWG insulated wire jumpers (JP1..JP7)
    for jref, (x1, y1), (x2, y2), mkey in DIY_TOP_JUMPERS:
        lx1, lz1 = x1 - PCB_W_MM * 0.5, y1 - PCB_H_MM * 0.5
        lx2, lz2 = x2 - PCB_W_MM * 0.5, y2 - PCB_H_MM * 0.5
        dx, dz = lx2 - lx1, lz2 - lz1
        jlen = max(1e-3, math.hypot(dx, dz))
        ux, uz = dx / jlen, dz / jlen
        arch_y = 3.6
        jpts = [
            (lx1, 1.4, lz1),
            (lx1, arch_y - 0.5, lz1),
            (lx1 + ux * 0.9, arch_y, lz1 + uz * 0.9),
            (lx2 - ux * 0.9, arch_y, lz2 - uz * 0.9),
            (lx2, arch_y - 0.5, lz2),
            (lx2, 1.4, lz2),
        ]
        add_tube(f"DIY_Jumper_{jref}", jpts, radius_mm=0.55, mat=mats[mkey], parent=pcb_hub, res=4, bevel_res=2)

    # ESP8266 NodeMCU v2 Amica (48.26 x 25.40 x 1.60 mm PCB, 22.86 mm row spacing, ~49.43 mm w/ Micro-USB)
    # Seated 0.00 mm flush on U1/U2 2x15 female sockets (Y = PCB_BOT_Y_MM + 10.1 = 29.10 mm)
    nodemcu = make_group(
        "nodemcu_esp8266",
        PCB_CX_MM + NODEMCU_DX_MM,
        PCB_BOT_Y_MM + 10.1,
        PCB_CZ_MM + NODEMCU_DZ_MM,
    )
    for side, sx in [("L", -11.43), ("R", 11.43)]:
        add_box(f"NodeMCU_MaleHdrStrip_{side}", sx, 1.27, 0.0, 2.54, 2.54, 38.10, mats["plastic_blk"], parent=nodemcu)
    add_box("NodeMCU_PCB", 0.0, 3.34, 0.0, 25.40, 1.60, 48.26, mats["pcb_black"], parent=nodemcu, bevel_mm=0.2)
    add_box("NodeMCU_ESP12_Shield", 0.0, 5.64, -7.0, 16.0, 3.0, 12.0, mats["silver_mtl"], parent=nodemcu, bevel_mm=0.2)
    add_box("NodeMCU_WiFi_AntennaArea", 0.0, 4.29, -18.5, 16.0, 0.3, 7.0, mats["pcb_black"], parent=nodemcu)
    for k in range(5):
        add_box(f"NodeMCU_AntTrace_{k}", -6.0 + k * 3.0, 4.49, -18.5, 0.7, 0.15, 5.8, mats["copper"], parent=nodemcu)
    add_box("NodeMCU_CP2102", 0.0, 4.64, 9.5, 5.0, 1.0, 5.0, mats["ic_black"], parent=nodemcu)
    add_box("NodeMCU_AMS1117", -6.5, 4.89, 15.0, 6.5, 1.5, 3.5, mats["ic_black"], parent=nodemcu)
    # Micro-USB faces +Z (toward P15 open USB cutaway!)
    add_box("NodeMCU_MicroUSB", 0.0, 5.54, 22.5, 7.8, 2.8, 5.6, mats["silver_mtl"], parent=nodemcu, bevel_mm=0.2)
    add_box("NodeMCU_Btn_RST", -6.2, 4.89, 20.5, 3.2, 1.5, 2.4, mats["silver_mtl"], parent=nodemcu)
    add_box("NodeMCU_Btn_FLASH", 6.2, 4.89, 20.5, 3.2, 1.5, 2.4, mats["silver_mtl"], parent=nodemcu)
    add_box("NodeMCU_StatusLED", 6.2, 4.54, -12.5, 1.6, 0.8, 0.8, mats["dht_blue"], parent=nodemcu)
    for side, sx in [("L", -11.43), ("R", 11.43)]:
        add_box(f"NodeMCU_HeaderBar_{side}", sx, 4.64, 0.0, 1.4, 1.0, 37.5, mats["copper"], parent=nodemcu)

    return pcb_hub, nodemcu


# ==============================================================================
# 3. ALL 6 REAL DEVICES + 3 REAL SENSORS + DC-022 POWER (EXACT SSOT & MICA COORDS)
# ==============================================================================
def build_hardware_devices_and_sensors(mats: dict[str, bpy.types.Material]) -> None:
    """Build every contract device and sensor at exact 1:1 SSOT dimensions & mica_design.py positions."""

    def C(part_id: str) -> tuple[float, float, float]:
        hx, hy, hz = HW_MAP[part_id].center_xyz
        return house_to_three_mm(hx, hy, hz)

    # ------------------------------------------------------------------
    # DEVICE 1: main_door (`door_pivot` / `main_door_leaf`) + Coaxial Top-Jamb Servo SG90 (D1)
    # Unified coaxial hinge & servo axis: House (77.0, 201.5) -> Three.js (tx=-126.0, tz=+33.5)
    # Door opening X=[76..136], Y=[192..195], Z=[0..104]; leaf 56x100x3 at X=[78..134], Z=[2..102]
    # ------------------------------------------------------------------
    door_pivot = make_group("door_pivot", -126.0, 0.0, 33.5)
    add_box("main_door_leaf", 29.0, 52.0, 8.0, 56.0, 100.0, 3.0, mats["door_wood"], parent=door_pivot, bevel_mm=0.4)
    add_box("MainDoorWindow", 29.0, 71.0, 8.0, 26.0, 30.0, 3.6, mats["glass"], parent=door_pivot)
    add_box("MainDoorHandle", 49.0, 48.0, 10.8, 4.0, 10.0, 2.6, mats["brass"], parent=door_pivot, bevel_mm=0.3)

    # Moving SUP10 door hinges at Z=18.0 and Z=78.0 (coaxial at local (0, Z, 0))
    for htag, hz in [("Bot", 18.0), ("Top", 78.0)]:
        add_cyl(f"SUP10_DoorKnuckle_{htag}", 0.0, hz, 0.0, 2.8, 7.6, mats["pla_mount"], parent=door_pivot, segs=16)
        add_box(f"SUP10_DoorArm_{htag}", 3.5, hz, 4.0, 7.0, 7.2, 6.2, mats["pla_mount"], parent=door_pivot, bevel_mm=0.2)
        add_box(f"SUP10_DoorTab_{htag}", 6.5, hz, 6.4, 5.0, 7.2, 2.0, mats["pla_mount"], parent=door_pivot, bevel_mm=0.15)

    # SUP10B_DoorHornCoupler: mounts at P08 MORT_DOOR_LINK (X=88, Y=195, Z=97 -> local (+11, 97, +6.5))
    # Extends back to coaxial horn plane Y=201.5 (local tz=0.0) forming open-top U-channel fork (inner W=4.9mm)
    add_box("SUP10B_CouplerBase",   11.0,  97.2,  5.7, 8.0, 6.8, 1.8, mats["pla_coupler"], parent=door_pivot, bevel_mm=0.2)
    add_box("SUP10B_CouplerBridge", 11.0,  97.8,  2.5, 6.5, 2.2, 6.4, mats["pla_coupler"], parent=door_pivot, bevel_mm=0.2)
    add_box("SUP10B_ForkFloor",     10.5,  98.2,  0.0, 7.2, 1.4, 8.5, mats["pla_coupler"], parent=door_pivot, bevel_mm=0.15)
    add_box("SUP10B_ForkWallF",     10.5, 100.3,  3.35, 7.2, 3.6, 1.8, mats["pla_coupler"], parent=door_pivot, bevel_mm=0.15)
    add_box("SUP10B_ForkWallB",     10.5, 100.3, -3.35, 7.2, 3.6, 1.8, mats["pla_coupler"], parent=door_pivot, bevel_mm=0.15)

    # Inverted Coaxial Top-Jamb SG90 Micro Servo at HW_SG90 (71.5, 201.5, 118.65) -> Three.js (-131.5, 118.65, +33.5)
    # Body 22.8 (X) x 22.5 (Y/up) x 12.2 (Z/depth), tab span 32.2 (X), overall H 31.0 (Y: Z=98.9..129.9)
    # Blue body rises proudly above P07 (Z=111.5..129.9); shaft descends coaxially at (X=77.0, Y=201.5)
    sgx, sgy, sgz = C("HW_SG90")
    sg90 = make_group("SG90_DoorServo", sgx, sgy, sgz)
    add_box("SG90_Body", 0.0, 0.0, 0.0, 22.8, 22.5, 12.2, mats["sg90_blue"], parent=sg90, bevel_mm=0.35)
    add_box("SG90_Flange", 0.0, -5.9, 0.0, 32.2, 2.5, 12.2, mats["sg90_blue"], parent=sg90)
    add_box("SG90_Sticker_In",  0.0, 1.5, -6.06, 12.0, 10.0, 0.08, mats["sg90_label"], parent=sg90)
    add_box("SG90_Sticker_Out", 0.0, 1.5,  6.06, 12.0, 10.0, 0.08, mats["sg90_label"], parent=sg90)
    add_cyl("SG90_GearHub", 5.5, -13.35, 0.0, 5.9, 4.2, mats["sg90_blue"], parent=sg90)
    add_cyl("SG90_OutputShaft", 5.5, -16.60, 0.0, 2.4, 2.3, mats["plastic_wht"], parent=sg90)
    # Dedicated coaxial rotating horn pivot at exact world (tx=-126.0, ty=100.1, tz=+33.5)
    sg90_horn_pivot = make_group("sg90_horn_pivot", 5.5, -18.55, 0.0, parent=sg90)
    add_cyl("SG90_HornHub", 0.0, 0.0, 0.0, 3.0, 2.4, mats["plastic_wht"], parent=sg90_horn_pivot, segs=18)
    add_box("SG90_WhiteHorn", 3.35, 0.0, 0.0, 14.5, 1.6, 4.5, mats["plastic_wht"], parent=sg90_horn_pivot, bevel_mm=0.25)

    # ------------------------------------------------------------------
    # DEVICE 2: led_living_room (5mm T-1 3/4 LED on D0, relocated to P06_WALL_MID -X face)
    # HW_LED_LR = (197.0, 232.0, 126.0) -> Three.js (-6.0, 126.0, +3.0)
    # ------------------------------------------------------------------
    lrx, lry, lrz = C("HW_LED_LR")
    led_lr = make_group("led_living_room", -4.5, lry, lrz)
    add_box("SUP17_LED_LR_Collar", -0.80, 0.0, 0.0, 1.8, 10.0, 14.0, mats["pla_mount"], parent=led_lr, bevel_mm=0.25)
    add_cyl("LED_LR_Flange", -0.50, 0.0, 0.0, 2.9, 1.0, mats["led_lr"], parent=led_lr, axis="X", segs=24)
    add_cyl("LED_LR_Body",   -3.55, 0.0, 0.0, 2.5, 5.1, mats["led_lr"], parent=led_lr, axis="X", segs=24)
    add_sphere("LED_LR_Dome",-6.10, 0.0, 0.0, 2.5, mats["led_lr"], parent=led_lr, segs=20)
    add_sphere("LED_LR_GlowHalo", -5.2, 0.0, 0.0, 6.8, mats["led_lr_halo"], parent=led_lr, segs=18)
    add_box("LED_LR_LeadA",   1.50,  1.27, 0.0, 3.0, 0.5, 0.5, mats["silver_mtl"], parent=led_lr)
    add_box("LED_LR_LeadK",   1.50, -1.27, 0.0, 3.0, 0.5, 0.5, mats["silver_mtl"], parent=led_lr)

    # ------------------------------------------------------------------
    # DEVICE 3: led_bedroom (5mm T-1 3/4 LED on D4 Active-LOW, relocated to P06_WALL_MID +X face)
    # HW_LED_BR = (203.0, 258.0, 126.0) -> Three.js (0.0, 126.0, -23.0)
    # ------------------------------------------------------------------
    brx, bry, brz = C("HW_LED_BR")
    led_br = make_group("led_bedroom", -1.5, bry, brz)
    add_box("SUP17_LED_BR_Collar",  0.80, 0.0, 0.0, 1.8, 10.0, 14.0, mats["pla_mount"], parent=led_br, bevel_mm=0.25)
    add_cyl("LED_BR_Flange",  0.50, 0.0, 0.0, 2.9, 1.0, mats["led_br"], parent=led_br, axis="X", segs=24)
    add_cyl("LED_BR_Body",    3.55, 0.0, 0.0, 2.5, 5.1, mats["led_br"], parent=led_br, axis="X", segs=24)
    add_sphere("LED_BR_Dome", 6.10, 0.0, 0.0, 2.5, mats["led_br"], parent=led_br, segs=20)
    add_sphere("LED_BR_GlowHalo", 5.2, 0.0, 0.0, 6.8, mats["led_br_halo"], parent=led_br, segs=18)
    add_box("LED_BR_LeadA",  -1.50,  1.27, 0.0, 3.0, 0.5, 0.5, mats["silver_mtl"], parent=led_br)
    add_box("LED_BR_LeadK",  -1.50, -1.27, 0.0, 3.0, 0.5, 0.5, mats["silver_mtl"], parent=led_br)

    # ------------------------------------------------------------------
    # DEVICE 4: garden_pump (`pump_unit`, `water_tube`, `relay1_pump`)
    # HW_PUMP = (292.0, 89.0, 16.5) -> Three.js (+89.0, 16.5, +146.0)
    # ------------------------------------------------------------------
    pmx, pmy, pmz = C("HW_PUMP")
    pump = make_group("pump_unit", pmx, pmy, pmz)
    add_cyl("Pump_WhiteBody",    0.0, -4.5, -5.0, 12.0, 35.0, mats["pump_white"], parent=pump, axis="Z", segs=24)
    add_cyl("Pump_FrontIntake",  0.0, -4.5, 17.5,  4.0, 10.0, mats["pump_white"], parent=pump, axis="Z", segs=16)
    add_cyl("Pump_OutletNozzle", 0.0, 12.0,  7.0, 3.75,  9.0, mats["pump_white"], parent=pump, axis="Y", segs=16)

    # Translucent 6/8mm (Ø8.0mm OD) silicone water tube from pump nozzle through P10 divider into planter soil
    add_tube(
        "water_tube",
        [
            (pmx, 33.0, pmz + 7.0),
            (pmx, 42.0, pmz + 7.0),
            (108.0, 42.0, pmz + 2.0),
            (116.5, 38.0, pmz),
            (132.0, 38.0, pmz),
            (144.0, 31.0, pmz),
        ],
        radius_mm=4.0,
        mat=mats["water_tube"],
        res=8,
        bevel_res=4,
    )

    # Relay 1 (BLUE 5V 1-ch relay, 50.0 x 18.5 x 26.0 mm) at HW_RELAY1 (226.0, 136.0, 17.25)
    r1x, _r1y, r1z = C("HW_RELAY1")
    rly1 = make_group("relay1_pump", r1x, 8.0, r1z)
    for idx, (fx, fz) in enumerate([(-22.25, -10.25), (22.25, -10.25), (-22.25, 10.25), (22.25, 10.25)]):
        add_cyl(f"Rly1_Foot_{idx}", fx, 0.75, fz, 1.5, 1.5, mats["brass"], parent=rly1, segs=12)
    add_box("Rly1_BluePCB", 0.0, 2.3, 0.0, 50.0, 1.6, 26.0, mats["pcb_blue"], parent=rly1, bevel_mm=0.2)
    add_box("Rly1_SongleCube", -2.5, 10.8, 0.0, 19.0, 15.4, 15.5, mats["relay_cube"], parent=rly1, bevel_mm=0.3)
    add_box("Rly1_ScrewTerm", 17.0, 8.1, 0.0, 8.0, 10.0, 15.24, mats["term_blue"], parent=rly1, bevel_mm=0.2)
    for k in range(3):
        add_cyl(f"Rly1_Screw_{k}", 17.0, 13.2, (k - 1) * 5.08, 1.8, 0.6, mats["silver_mtl"], parent=rly1)
    add_box("Rly1_PinHeader", -21.5, 6.0, 0.0, 2.54, 7.0, 7.62, mats["plastic_blk"], parent=rly1)
    add_box("Rly1_LED_Pwr", -14.5, 3.6, -6.5, 2.2, 1.0, 1.4, mats["led_red"], parent=rly1)
    add_box("Rly1_LED_Trig", -14.5, 3.6,  6.5, 2.2, 1.0, 1.4, mats["led_grn"], parent=rly1)

    # ------------------------------------------------------------------
    # DEVICE 5: alarm_siren (`buzzer_alarm`, TMB12A05 Ø12.0 x 9.5 mm)
    # HW_BUZZER = (200.0, 196.8, 126.0) -> Three.js (-3.0, 126.0, +38.2)
    # ------------------------------------------------------------------
    bzx, bzy, bzz = C("HW_BUZZER")
    buzzer = make_group("buzzer_alarm", bzx, bzy, 40.0)
    add_cyl("Buzzer_CylBody", 0.0, 0.0, 4.75, 6.0, 9.5, mats["plastic_blk"], parent=buzzer, axis="Z", segs=24)
    add_cyl("Buzzer_SoundHole", 0.0, 0.0, 9.35, 1.5, 0.3, mats["silver_mtl"], parent=buzzer, axis="Z", segs=16)
    add_cyl("Buzzer_PinPos", -3.8, 0.0, 0.1, 0.35, 0.2, mats["silver_mtl"], parent=buzzer, axis="Z", segs=10)
    add_cyl("Buzzer_PinNeg",  3.8, 0.0, 0.1, 0.35, 0.2, mats["silver_mtl"], parent=buzzer, axis="Z", segs=10)

    # ------------------------------------------------------------------
    # DEVICE 6: speaker_amp (`relay2_speaker`, `pam8403_module`, `speaker_mini`)
    # ------------------------------------------------------------------
    # Relay 2 (RED opto 5V 1-ch relay, 50.0 x 18.5 x 26.0 mm) at HW_RELAY2 (226.0, 92.0, 17.25)
    r2x, _r2y, r2z = C("HW_RELAY2")
    rly2 = make_group("relay2_speaker", r2x, 8.0, r2z)
    for idx, (fx, fz) in enumerate([(-22.25, -10.25), (22.25, -10.25), (-22.25, 10.25), (22.25, 10.25)]):
        add_cyl(f"Rly2_Foot_{idx}", fx, 0.75, fz, 1.5, 1.5, mats["brass"], parent=rly2, segs=12)
    add_box("Rly2_RedPCB", 0.0, 2.3, 0.0, 50.0, 1.6, 26.0, mats["pcb_red"], parent=rly2, bevel_mm=0.2)
    add_box("Rly2_SongleCube", -2.0, 10.8, 0.0, 19.0, 15.4, 15.5, mats["relay_cube"], parent=rly2, bevel_mm=0.3)
    add_box("Rly2_ScrewTerm", 17.0, 8.1, 0.0, 8.0, 10.0, 15.24, mats["term_blue"], parent=rly2, bevel_mm=0.2)
    for k in range(3):
        add_cyl(f"Rly2_Screw_{k}", 17.0, 13.2, (k - 1) * 5.08, 1.8, 0.6, mats["silver_mtl"], parent=rly2)
    add_box("Rly2_Optocoupler", -14.5, 4.7, 0.0, 4.6, 3.2, 6.5, mats["ic_black"], parent=rly2)
    add_box("Rly2_JumperH", -14.5, 6.0, -7.5, 5.2, 5.8, 2.6, mats["jumper_yel"], parent=rly2)
    add_box("Rly2_PinHeader", -21.5, 6.0, 0.0, 2.54, 7.0, 7.62, mats["plastic_blk"], parent=rly2)
    add_box("Rly2_LED_Pwr", -15.0, 3.6, -7.5, 2.2, 1.0, 1.4, mats["led_grn"], parent=rly2)
    add_box("Rly2_LED_Trig", -15.0, 3.6,  7.5, 2.2, 1.0, 1.4, mats["led_red"], parent=rly2)

    # PAM8403 Audio Amplifier (21.0 x 3.1 x 18.0 mm) at HW_PAM8403 (224.0, 52.0, 3.0)
    pax, _pay, paz = C("HW_PAM8403")
    pam = make_group("pam8403_module", pax, 1.5, paz)
    add_box("PAM8403_GreenPCB", 0.0, 0.8, 0.0, 21.0, 1.6, 18.0, mats["pcb_green"], parent=pam, bevel_mm=0.15)
    add_box("PAM8403_SOIC16", 0.0, 2.35, 0.0, 3.9, 1.5, 9.9, mats["ic_black"], parent=pam)
    for sx in (-2.48, 2.48):
        for k in range(8):
            add_box(f"PAM_Pin_{sx}_{k}", sx, 1.75, -4.445 + k * 1.27, 1.05, 0.25, 0.42, mats["silver_mtl"], parent=pam)
    for px, pz in [(-7.5, -7.2), (-4.5, -7.2), (4.5, -7.2), (7.5, -7.2), (-7.0, 7.2), (-4.0, 7.2), (4.5, 7.2), (7.5, 7.2)]:
        add_cyl(f"PAM_Pad_{px}_{pz}", px, 1.65, pz, 0.9, 0.2, mats["copper"], parent=pam, segs=12)

    # Mini Round Speaker 28mm (PUI Audio AS02808MR-R: Ø28.0 x 5.2 mm) behind P15_TECH_FASCIA
    # HW_SPEAKER = (223.0, 15.6, 26.0) -> Three.js (+20.0, 26.0, +219.4), axis along Z
    spx, spy, spz = C("HW_SPEAKER")
    spk = make_group("speaker_mini", spx, spy, spz)
    add_cyl("Speaker_SilverRim", 0.0, 0.0,  0.3, 14.0, 4.6, mats["silver_mtl"], parent=spk, axis="Z", segs=28)
    add_cyl("Speaker_InnerCone", 0.0, 0.0,  2.3, 11.5, 0.6, mats["plastic_blk"], parent=spk, axis="Z", segs=24)
    add_cyl("Speaker_CenterCap", 0.0, 0.0, -2.3,  5.2, 0.6, mats["silver_mtl"], parent=spk, axis="Z", segs=20)

    # DC-022 5V 2A Panel-Mount Barrel Power Jack + SUP16 Strain-Relief Collar + Exterior 5V Barrel Plug
    dcx, dcy, dcz = C("HW_DC_JACK")
    dcj = make_group("psu_5v_dc_jack", dcx, dcy, dcz)
    add_cyl("DC022_BarrelBody",     0.0,  0.0, -1.5, 6.0, 18.0, mats["plastic_blk"], parent=dcj, axis="Z", segs=20)
    add_cyl("DC022_FrontFlange",    0.0,  0.0,  9.0, 7.0,  3.0, mats["silver_mtl"],  parent=dcj, axis="Z", segs=20)
    add_box("SUP16_DC022_Collar",   0.0,  0.0,  3.8, 22.0, 15.0, 4.2, mats["pla_mount"], parent=dcj, bevel_mm=0.3)
    add_cyl("DC022_ExtPlug_Tip",    0.0,  0.0, 11.2, 4.6,  2.2, mats["plug_yellow"], parent=dcj, axis="Z", segs=18)
    add_cyl("DC022_ExtPlug_Barrel", 0.0,  0.0, 17.5, 4.9, 11.0, mats["plastic_blk"], parent=dcj, axis="Z", segs=18)
    add_cyl("DC022_ExtPlug_Boot",   0.0,  0.0, 25.0, 2.8,  5.5, mats["plastic_blk"], parent=dcj, axis="Z", segs=16)
    add_box("DC022_TermPos",        0.0,  2.5, -10.5, 2.2, 1.0, 3.0, mats["copper"],     parent=dcj)
    add_box("DC022_TermNeg",        0.0, -2.5, -10.5, 2.2, 1.0, 3.0, mats["silver_mtl"], parent=dcj)

    plx, ply, plz = C("HW_LED_PWR")
    pled = make_group("led_power_3mm", plx, ply, plz)
    add_cyl("PowerLED_Flange", 0.0, 0.0, 0.5, 1.9, 1.0, mats["led_grn"], parent=pled, axis="Z", segs=16)
    add_cyl("PowerLED_Body",   0.0, 0.0, 2.6, 1.5, 3.3, mats["led_grn"], parent=pled, axis="Z", segs=16)
    add_sphere("PowerLED_Dome",0.0, 0.0, 4.3, 1.5, mats["led_grn"], parent=pled, segs=14)

    # ------------------------------------------------------------------
    # SENSOR 1: sensor_dht11 (relocated to P06_WALL_MID Living Room -X face)
    # HW_DHT11 = (195.0, 286.0, 92.0) -> Three.js (-8.0, 92.0, -51.0)
    # Dimensions: 7.1 (X) x 28.0 (Y) x 14.0 (Z)
    # ------------------------------------------------------------------
    dhx, dhy, dhz = C("HW_DHT11")
    dht = make_group("sensor_dht11", -4.5, dhy, dhz)
    add_box("DHT11_BreakoutPCB", -0.80,  0.0, 0.0, 1.6, 28.0, 14.0, mats["pcb_blue"], parent=dht)
    add_box("DHT11_BlueGridBox", -4.35,  3.5, 0.0, 5.5, 15.5, 12.0, mats["dht_blue"], parent=dht, bevel_mm=0.25)
    for row in range(3):
        for col in range(3):
            add_box(f"DHT11_Vent_{row}_{col}", -6.90, -0.5 + row * 4.0, -3.2 + col * 3.2, 0.4, 1.9, 1.9, mats["plastic_blk"], parent=dht)
    add_box("DHT11_Pins", -2.87, -11.5, 0.0, 2.54, 5.0, 7.62, mats["silver_mtl"], parent=dht)

    # ------------------------------------------------------------------
    # SENSOR 2: sensor_soil (YL-69 probe in planter) + soil_lm393_board (on P13 dry rear)
    # HW_SOIL_PROBE = (358.0, 89.0, 32.0) -> Three.js (+155.0, 32.0, +146.0)
    # HW_LM393      = (292.0, 158.0, 24.0) -> Three.js (+89.0, 24.0, +77.0)
    # ------------------------------------------------------------------
    slx, sly, slz = C("HW_SOIL_PROBE")
    soil = make_group("sensor_soil", slx, sly, slz)
    # YL-69 2-prong fork probe: 1.6 (X) x 60.0 (Y) x 20.0 (Z)
    add_box("SoilProbe_Head",   0.0, 21.0,  0.0, 1.6, 18.0, 20.0, mats["pcb_black"], parent=soil)
    add_box("SoilProbe_ProngL", 0.0, -9.0, -5.0, 1.6, 42.0,  5.0, mats["silver_mtl"], parent=soil)
    add_box("SoilProbe_ProngR", 0.0, -9.0,  5.0, 1.6, 42.0,  5.0, mats["silver_mtl"], parent=soil)

    # Blue LM393 comparator board mounted on P13_GARDEN_BACK dry exterior rear (Y=152 -> tz=+83.0, facing -Z)
    # Size: 32.0 (X) x 14.0 (Y) x 12.1 (Z)
    lmx, lmy, lmz = C("HW_LM393")
    lm393 = make_group("soil_lm393_board", lmx, lmy, 83.0)
    add_box("Soil_LM393_PCB",    0.0, 0.0, -0.80, 32.0, 14.0,  1.6, mats["pcb_blue"], parent=lm393, bevel_mm=0.2)
    add_box("Soil_LM393_Pot",    2.0, 0.0, -6.35,  9.5,  4.8,  9.5, mats["pot_blue"], parent=lm393)
    add_cyl("Soil_LM393_Screw",  4.5, 0.0,-11.60,  1.2,  1.0,       mats["brass"],    parent=lm393, axis="Z")
    add_box("Soil_LM393_IC",    -6.0, 0.0, -2.30,  5.0,  4.0,  1.4, mats["ic_black"], parent=lm393)
    add_box("Soil_LM393_Hdr",  -14.0, 0.0, -2.87,  3.0, 10.16, 2.54, mats["silver_mtl"], parent=lm393)

    # ------------------------------------------------------------------
    # SENSOR 3: sensor_mic_ky037 (behind P05_WALL_FRONT KY037_Ledge)
    # HW_KY037 = (168.0, 201.6, 26.0) -> Three.js (-35.0, 26.0, +33.4)
    # Size: 35.0 (X) x 15.0 (Y) x 13.1 (Z)
    # ------------------------------------------------------------------
    kyx, kyy, kyz = C("HW_KY037")
    ky = make_group("sensor_mic_ky037", kyx, kyy, 40.0)
    add_box("KY037_RedPCB",     0.0,  0.0, -0.80, 35.0, 15.0,  1.6, mats["pcb_red"], parent=ky, bevel_mm=0.2)
    add_cyl("KY037_MicCan",   -11.5,  0.0, -4.95, 4.85,  6.7,       mats["silver_mtl"], parent=ky, axis="Z", segs=22)
    add_cyl("KY037_MicFelt",  -11.5,  0.0, -8.25, 4.30,  0.3,       mats["mic_felt"],   parent=ky, axis="Z", segs=22)
    add_box("KY037_TrimPot",    2.0, -3.5, -6.60,  9.5,  4.8, 10.0, mats["pot_blue"],   parent=ky)
    add_cyl("KY037_PotScrew",   5.0, -3.5,-12.35,  1.2,  1.5,       mats["brass"],      parent=ky, axis="Z")
    add_box("KY037_LM393",      1.5,  3.8, -2.30,  5.0,  4.0,  1.4, mats["ic_black"],   parent=ky)
    add_cyl("KY037_MountHole", 10.5,  0.0, -1.60,  1.5,  1.8,       mats["silver_mtl"], parent=ky, axis="Z")
    add_box("KY037_PinHeader", 15.5,  0.0, -2.87,  3.5, 10.16, 2.54, mats["plastic_blk"], parent=ky)


# ==============================================================================
# 4. ALL 40 ROUTED 3D WIRES FROM hardware/wire_lengths.json (`smooth_waypoints_house_mm`)
# ==============================================================================
def _wire_node_suffix(hub_ref: str, module_pin: str) -> str:
    """Produce node suffix compatible with BOTH W01..W40 and web/house3d.js inferGlbWireMeta()."""
    mapping = {
        "J1": "J1_PWR",
        "J2": "J2_PUMP",
        "J3": "J3_SERVO",
        "J4": "J4_LR_LED",
        "J5": "J5_BR_LED",
        "J6": "J6_BUZZ",
        "J7": "J7_RLY1",
        "J8": "J8_RLY1",
        "J9": "J9_RLY2",
        "J10": "J10_RLY2",
        "J11": "J11_AMP_PWR",
        "J12": "J12_AUDIO",
        "J13": "J13_DHT11",
        "J14": "J14_SOIL",
        "J15": "J15_KY037",
        "LM393": "J14_SOIL_Probe",
    }
    if hub_ref == "PAM8403":
        return "PAM_Spk_Pos" if "+" in module_pin else "PAM_Spk_Neg"
    return mapping.get(hub_ref, hub_ref)


def build_routed_40_wires(mats: dict[str, bpy.types.Material]) -> tuple[bpy.types.Object, int]:
    """Build all 40 routed 3D wire tubes from hardware/wire_lengths.json + PCB Dupont plugs."""
    if not WIRE_LENGTHS_JSON.exists():
        raise FileNotFoundError(f"Missing wire_lengths.json: {WIRE_LENGTHS_JSON}")
    wire_data = json.loads(WIRE_LENGTHS_JSON.read_text(encoding="utf-8"))
    wires_list = wire_data.get("wires", [])
    if len(wires_list) != 40:
        raise RuntimeError(f"Expected 40 wires in {WIRE_LENGTHS_JSON}, got {len(wires_list)}")

    harness = make_group("DupontWiringHarness", 0.0, 0.0, 0.0)

    # 1. Black 2.54mm Dupont plug housings on all 13 PCB 2.54mm headers (J3..J15)
    for conn in HUB_CONNECTORS:
        if conn.kind != "header_254":
            continue
        n = len(conn.pins)
        xs = [p[1] for p in conn.pins]
        ys = [p[2] for p in conn.pins]
        cx_rel = sum(xs) / n
        cy_rel = sum(ys) / n
        is_horiz = (abs(max(xs) - min(xs)) > abs(max(ys) - min(ys)))
        tx, ty, tz = pcb_pin_three_mm(cx_rel, cy_rel, z_top_offset_mm=9.5)
        sx = 2.54 * n if is_horiz else 2.54
        sz = 2.54 if is_horiz else 2.54 * n
        tag = _wire_node_suffix(conn.ref, "")
        add_box(f"DupontPlug_{tag}", tx, ty, tz, sx, 9.0, sz, mats["plastic_blk"], parent=harness, bevel_mm=0.1)

    # 1b. Subtle colored collar markers on PCB J1 (5V input) & switched outputs (J2 Pump, J8/J10 Relays, J11 Amp)
    callout_specs = [
        ("J1",  "callout_j1",  13.2),
        ("J2",  "callout_j2",  13.2),
        ("J8",  "callout_sw",  14.2),
        ("J10", "callout_sw",  14.2),
        ("J11", "callout_amp", 14.2),
    ]
    for cref, mkey, z_off in callout_specs:
        conn = HUB_CONNECTOR_MAP[cref]
        cx_rel = sum(p[1] for p in conn.pins) / len(conn.pins)
        cy_rel = sum(p[2] for p in conn.pins) / len(conn.pins)
        tx, ty, tz = pcb_pin_three_mm(cx_rel, cy_rel, z_top_offset_mm=z_off)
        add_cyl(f"PCB_CalloutMarker_{cref}", tx, ty, tz, 2.1, 0.9, mats[mkey], parent=harness, segs=16)

    # 2. All 40 routed 3D wire polylines colored by exact `color_hex`
    WR = 0.72  # ~1.44 mm OD realistic 22-26AWG Dupont insulation
    color_mats: dict[str, bpy.types.Material] = {}
    for w in wires_list:
        wid = str(w["wire_id"])
        chexc = str(w.get("color_hex", "#94A3B8")).upper()
        cname = str(w.get("color", "Wire"))
        mkey = f"WireHex_{cname}_{chexc.lstrip('#')}"
        if mkey not in color_mats:
            color_mats[mkey] = make_mat(mkey, hex_to_linear_rgba(chexc), roughness=0.36, metallic=0.04)

        pts_house = w["smooth_waypoints_house_mm"]
        pts_three = [house_to_three_mm(float(p[0]), float(p[1]), float(p[2])) for p in pts_house]
        suffix = _wire_node_suffix(str(w["hub_ref"]), str(w.get("module_pin", "")))
        wname = f"Wire_{wid}_{suffix}"
        add_tube(wname, pts_three, radius_mm=WR, mat=color_mats[mkey], parent=harness, res=3, bevel_res=2)

    print(f"[WIRES] Built {len(wires_list)} routed 3D wire tubes from {WIRE_LENGTHS_JSON.name}")
    return harness, len(wires_list)


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
        bg.inputs["Strength"].default_value = 0.32

    def add_light(name: str, ltype: str, pos_mm: tuple[float, float, float], target_mm: tuple[float, float, float],
                  energy: float, color=(1.0, 1.0, 1.0), size_mm: float = 180.0) -> None:
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

    add_light("KeyLight",  "AREA", (280.0, 390.0, 340.0),  (0.0, 40.0, 40.0),   1600.0, (1.00, 0.96, 0.90), 240.0)
    add_light("FillLight", "AREA", (-340.0, 260.0, 280.0), (-40.0, 30.0, 80.0),  720.0, (0.86, 0.92, 1.00), 260.0)
    add_light("RimLight",  "AREA", (40.0, 280.0, -340.0),  (0.0, 40.0, 20.0),    620.0, (0.88, 0.94, 1.00), 240.0)
    add_light("TechSpot",  "AREA", (-40.0, 210.0, 260.0),  (-35.0, 20.0, 130.0), 460.0, (1.00, 0.98, 0.95), 140.0)
    add_light("DoorInteriorFill", "AREA", (-15.0, 180.0, -90.0), (-115.0, 85.0, 32.0), 220.0, (0.98, 0.98, 1.00), 110.0)
    # Warm local point lights right next to the 5mm Living Room & Bedroom LEDs so both glow unmistakably
    add_light("Light_LED_Living",  "POINT", (-14.0, 126.0,   3.0), (-20.0, 120.0,   3.0), 38.0, (1.00, 0.88, 0.48))
    add_light("Light_LED_Bedroom", "POINT", (  8.0, 126.0, -23.0), ( 16.0, 120.0, -23.0), 34.0, (1.00, 0.78, 0.36))


def create_camera(name: str, eye_mm: tuple[float, float, float], target_mm: tuple[float, float, float], lens_mm: float = 38.0) -> bpy.types.Object:
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
        "SG90_DoorServo",
        "sg90_horn_pivot",
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
        "soil_lm393_board",
        "sensor_mic_ky037",
        "psu_5v_dc_jack",
        "kicad_pcb_hub",
        "nodemcu_esp8266",
    ]


def write_scene_spec(wire_count: int, honeycomb_count: int = 0) -> None:
    bpy.context.view_layer.update()
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
        "schema_version": "3.2",
        "architecture": "pcb_direct_no_breadboard",
        "breadboard_used": False,
        "furniture_removed": True,
        "wall_thinning_mm": float(lw_policy.WEB_THICKNESS_MM),
        "honeycomb_cutouts_enabled": True,
        "honeycomb_cutout_count": int(honeycomb_count),
        "routed_wires_count": wire_count,
        "authoritative_module_count": 14,
        "contract_node_count": len(node_positions),
        "door_servo_mechanism": SG90_MECHANICAL_SPECS["drive_mechanism"],
        "door_hinge_pivot_three_mm": [-126.0, 0.0, 33.5],
        "sg90_horn_pivot_three_mm": [-126.0, 100.1, 33.5],
        "model_file": "web/models/smarthome_villa.glb",
        "blend_file": "hardware/blender/smarthome_open_house.blend",
        "kicad_pcb_source": "hardware/kicad/smarthome_hub/3d/smarthome_hub.glb",
        "wire_routes_source": "hardware/wire_lengths.json",
        "units": "glTF meters (uniformly scaled 25x from 1:1 physical tabletop millimeters; synced to mica_design.py & wire_lengths.json)",
        "scale_mm_to_gltf": MM,
        "physical_scale_ratio": SCENE_SCALE,
        "house_to_three_transform": {
            "tx_mm": "hx - 203.0",
            "ty_mm": "hz",
            "tz_mm": "235.0 - hy",
        },
        "physical_dimensions_mm": {
            "tabletop_plinth": [406.0, 9.0, 390.0],
            "tech_bay_deck": [250.0, 1.2, 164.0],
            "open_cutaway_house": [386.0, 149.5, 190.0],
            "kicad_pcb_hub": [100.0, 17.3, 80.0],
            "nodemcu_esp8266": [25.4, 7.14, 49.4],
            "sg90_servo_body": [22.8, 22.5, 12.2],
            "sg90_servo_envelope": [32.2, 31.0, 12.2],
            "psu_5v_dc_jack": [14.0, 14.0, 21.0],
            "relay1_pump": [50.0, 18.5, 26.0],
            "relay2_speaker": [50.0, 18.5, 26.0],
            "pam8403_module": [21.0, 3.1, 18.0],
            "speaker_mini": [28.0, 28.0, 5.2],
            "pump_unit": [24.0, 33.0, 45.0],
            "buzzer_alarm": [12.0, 12.0, 9.5],
            "led_5mm_body": [8.6, 5.8, 5.8],
            "sensor_dht11": [7.1, 28.0, 14.0],
            "soil_probe_yl69": [1.6, 60.0, 20.0],
            "soil_lm393_board": [32.0, 14.0, 12.1],
            "sensor_mic_ky037": [35.0, 15.0, 13.1],
        },
        "bounding_box_gltf": {
            "min": [round(v, 4) for v in gmin],
            "max": [round(v, 4) for v in gmax],
            "extents": [round(gmax[i] - gmin[i], 4) for i in range(3)],
        },
        "camera_presets": {
            "overview": spherical_from_eye_target((235.0, 360.0, 520.0), (0.0, 38.0, 42.0)),
            "living":   spherical_from_eye_target((-15.0, 220.0, 225.0), (-95.0, 52.0, -50.0)),
            "bedroom":  spherical_from_eye_target((165.0, 220.0, 225.0), (95.0, 48.0, -52.0)),
            "door":     spherical_from_eye_target((-68.0, 130.0, 220.0), (-108.0, 72.0, 36.0)),
            "garden":   spherical_from_eye_target((180.0, 150.0, 310.0), (125.0, 30.0, 140.0)),
            "board":    spherical_from_eye_target((-60.0, 175.0, 305.0), (-55.0, 25.0, 131.0)),
        },
        "contract_nodes": node_positions,
        "removed_devices": [
            "fan",
            "ac",
            "ir_vs1838b",
            "ir_led_940nm",
            "breadboard",
            *lw_policy.REMOVED_BLENDER_FURNITURE_PREFIXES,
        ],
        "removed_furniture_ids": list(lw_policy.REMOVED_FURNITURE_IDS),
    }
    OUT_SPEC.parent.mkdir(parents=True, exist_ok=True)
    OUT_SPEC.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"[SPEC] Wrote {OUT_SPEC}")


def render_presentation_views(
    render_dir: pathlib.Path | None = None,
    overview_png: pathlib.Path | None = None,
    interior_png: pathlib.Path | None = None,
) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1066
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    vt_items = [i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items]
    scene.view_settings.view_transform = "AgX" if "AgX" in vt_items else "Filmic"
    scene.view_settings.exposure = -0.25

    cam_overview = create_camera("Cam_Overview", (235.0, 360.0, 520.0), (0.0, 38.0, 42.0), lens_mm=38.0)
    cam_interior = create_camera("Cam_Interior_PCB_Wires", (-25.0, 185.0, 320.0), (-30.0, 22.0, 125.0), lens_mm=34.0)

    targets: list[tuple[bpy.types.Object, pathlib.Path]] = []
    if render_dir is not None:
        render_dir.mkdir(parents=True, exist_ok=True)
        targets.append((cam_overview, render_dir / "hw12_blender_overview.png"))
        targets.append((cam_interior, render_dir / "hw12_blender_interior_pcb_wires.png"))
    if overview_png is not None:
        overview_png.parent.mkdir(parents=True, exist_ok=True)
        targets.append((cam_overview, overview_png))
    if interior_png is not None:
        interior_png.parent.mkdir(parents=True, exist_ok=True)
        targets.append((cam_interior, interior_png))

    seen: set[pathlib.Path] = set()
    for cam, out_png in targets:
        rp = out_png.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        scene.camera = cam
        scene.render.filepath = str(out_png)
        bpy.ops.render.render(write_still=True)
        print(f"[RENDER] Saved {out_png} ({out_png.stat().st_size} bytes)")


def _collect_callout_anchors_blender() -> dict[str, Vector]:
    """Return exact Blender world positions of all 14 modules + PCB + NodeMCU + key door/power parts."""
    bpy.context.view_layer.update()
    anchors: dict[str, Vector] = {}
    obj_targets = {
        "SG90_DoorServo":     ("SG90_Body", Vector((0.0, 0.0, 0.0))),
        "sg90_horn_pivot":    ("SG90_WhiteHorn", Vector((0.0, 0.0, 0.0))),
        "SUP11_Saddle":       ("SUP11_SG90_Saddle_B", Vector((0.0, 0.0, 0.0))),
        "P07_ServoShelf":     ("P07_ServoShelf_R", Vector((0.0, 0.0, 0.0))),
        "SUP10B_Coupler":     ("SUP10B_ForkWallF", Vector((0.0, 0.0, 0.0))),
        "SUP10_HingeTop":     ("SUP10_DoorKnuckle_Top", Vector((0.0, 0.0, 0.0))),
        "SUP10_HingeBot":     ("SUP10_DoorKnuckle_Bot", Vector((0.0, 0.0, 0.0))),
        "P07_EndStop_Closed": ("P07_EndStop_Closed", Vector((0.0, 0.0, 0.0))),
        "P07_EndStop_Open":   ("P07_EndStop_Open", Vector((0.0, 0.0, 0.0))),
        "main_door_leaf":     ("main_door_leaf", Vector((0.0, 0.0, 0.0))),
        "psu_5v_dc_jack":     ("DC022_ExtPlug_Barrel", Vector((0.0, 0.0, 0.0))),
        "kicad_pcb_hub":      ("kicad_pcb_hub", Vector((0.0, 0.0, 4.0 * MM))),
        "nodemcu_esp8266":    ("NodeMCU_ESP12_Shield", Vector((0.0, 0.0, 0.0))),
        "led_living_room":    ("LED_LR_Dome", Vector((0.0, 0.0, 0.0))),
        "led_bedroom":        ("LED_BR_Dome", Vector((0.0, 0.0, 0.0))),
        "buzzer_alarm":       ("Buzzer_CylBody", Vector((0.0, 0.0, 0.0))),
        "sensor_mic_ky037":   ("KY037_RedPCB", Vector((0.0, 0.0, 0.0))),
        "sensor_dht11":       ("DHT11_BlueGridBox", Vector((0.0, 0.0, 0.0))),
        "soil_lm393_board":   ("Soil_LM393_PCB", Vector((0.0, 0.0, 0.0))),
        "sensor_soil":        ("SoilProbe_Head", Vector((0.0, 0.0, 0.0))),
        "pump_unit":          ("Pump_WhiteBody", Vector((0.0, 0.0, 0.0))),
        "water_tube":         ("water_tube", Vector((0.0, 0.0, 0.0))),
        "speaker_mini":       ("Speaker_SilverRim", Vector((0.0, 0.0, 0.0))),
        "pam8403_module":     ("PAM8403_GreenPCB", Vector((0.0, 0.0, 0.0))),
        "relay1_pump":        ("Rly1_SongleCube", Vector((0.0, 0.0, 0.0))),
        "relay2_speaker":     ("Rly2_SongleCube", Vector((0.0, 0.0, 0.0))),
        "PCB_J1_Input":       ("PCB_CalloutMarker_J1", Vector((0.0, 0.0, 0.0))),
        "PCB_J2_PumpOut":     ("PCB_CalloutMarker_J2", Vector((0.0, 0.0, 0.0))),
        "PCB_J8_Rly1Sw":      ("PCB_CalloutMarker_J8", Vector((0.0, 0.0, 0.0))),
        "PCB_J10_Rly2Sw":     ("PCB_CalloutMarker_J10", Vector((0.0, 0.0, 0.0))),
        "PCB_J11_AmpPwr":     ("PCB_CalloutMarker_J11", Vector((0.0, 0.0, 0.0))),
        "Wall_Honeycomb_Cutout": ("BackWallLiving_HoneycombWeb", Vector((0.0, 0.0, 12.0 * MM))),
        "TechBay_Closed_Safety": ("P15_PowerZone", Vector((24.0 * MM, 0.0, 0.0))),
    }
    for key, (oname, offset) in obj_targets.items():
        obj = bpy.data.objects.get(oname)
        if obj is None:
            continue
        if obj.type == "MESH":
            # World-space bounding box center
            pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
            ctr = sum(pts, Vector((0.0, 0.0, 0.0))) / len(pts)
            anchors[key] = ctr + offset
        else:
            anchors[key] = obj.matrix_world.translation + offset
    return anchors


def render_hw14_views(raw_dir: pathlib.Path, proj_json: pathlib.Path) -> None:
    """Render the 2 HW14 lightweight presentation views (1600x1000 Eevee) + exact 2D projections."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    vt_items = [i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items]
    scene.view_settings.view_transform = "AgX" if "AgX" in vt_items else "Filmic"
    scene.view_settings.exposure = -0.15

    raw_dir.mkdir(parents=True, exist_ok=True)
    W, H = scene.render.resolution_x, scene.render.resolution_y

    views = [
        ("overview_lightweight", "Cam_HW14_Overview",  (220.0, 368.0, 545.0), (-8.0, 42.0, 48.0), 36.0),
        ("cutaway_14modules",    "Cam_HW14_Cutaway14", (-14.0, 625.0, 195.0), ( 2.0, 34.0, 58.0), 33.0),
    ]

    projections: dict[str, dict] = {"resolution": [W, H], "views": {}}
    for vkey, cname, eye_mm, tgt_mm, lens_mm in views:
        bpy.context.view_layer.update()
        cam = create_camera(cname, eye_mm, tgt_mm, lens_mm=lens_mm)
        scene.camera = cam
        out_png = raw_dir / f"raw_{vkey}.png"
        scene.render.filepath = str(out_png)
        bpy.ops.render.render(write_still=True)
        print(f"[HW14 RENDER] {vkey} -> {out_png} ({out_png.stat().st_size} bytes)")

        anchors = _collect_callout_anchors_blender()
        pts_2d: dict[str, list[float]] = {}
        for akey, wpos in anchors.items():
            co = world_to_camera_view(scene, cam, wpos)
            px = round(float(co.x) * W, 1)
            py = round((1.0 - float(co.y)) * H, 1)
            pts_2d[akey] = [px, py, round(float(co.z), 3)]
        projections["views"][vkey] = {
            "raw_png": str(out_png),
            "points": pts_2d,
        }

    proj_json.parent.mkdir(parents=True, exist_ok=True)
    proj_json.write_text(json.dumps(projections, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[HW14 PROJ] Saved exact 2D label projections to {proj_json}")


def render_hw13_views(raw_dir: pathlib.Path, proj_json: pathlib.Path) -> None:
    """Sequentially render all 6 hw13 views (1600x1000 Eevee) and export exact 2D pixel projections."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    vt_items = [i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items]
    scene.view_settings.view_transform = "AgX" if "AgX" in vt_items else "Filmic"
    scene.view_settings.exposure = -0.15

    raw_dir.mkdir(parents=True, exist_ok=True)
    W, H = scene.render.resolution_x, scene.render.resolution_y

    views = [
        ("overview",          "Cam_HW13_Overview",       (220.0, 368.0, 545.0), ( -8.0,  42.0,  48.0), 36.0, 0.0),
        ("topdown_cutaway",   "Cam_HW13_Topdown",        (-14.0, 625.0, 195.0), (  2.0,  34.0,  58.0), 33.0, 0.0),
        ("front_techbay",     "Cam_HW13_FrontTechBay",   (-24.0, 232.0, 535.0), (  4.0,  46.0, 118.0), 32.0, 0.0),
        ("interior_rooms",    "Cam_HW13_InteriorRooms",  (-78.0, 250.0, 248.0), ( 18.0,  76.0, -24.0), 28.0, 0.0),
        ("servo_door_closed", "Cam_HW13_ServoDoor",      (-10.0, 152.0,-112.0), (-108.0, 74.0,  28.0), 35.0, 0.0),
        ("servo_door_open",   "Cam_HW13_ServoDoorOpen",  (-10.0, 152.0,-112.0), (-108.0, 74.0,  28.0), 35.0, 90.0),
    ]

    door_pivot = bpy.data.objects.get("door_pivot")
    horn_pivot = bpy.data.objects.get("sg90_horn_pivot")

    projections: dict[str, dict] = {"resolution": [W, H], "views": {}}
    for vkey, cname, eye_mm, tgt_mm, lens_mm, door_deg in views:
        if door_pivot is not None:
            door_pivot.rotation_euler = Euler((0.0, 0.0, math.radians(door_deg)), "XYZ")
        if horn_pivot is not None:
            horn_pivot.rotation_euler = Euler((0.0, 0.0, math.radians(door_deg)), "XYZ")
        bpy.context.view_layer.update()

        cam = create_camera(cname, eye_mm, tgt_mm, lens_mm=lens_mm)
        scene.camera = cam
        out_png = raw_dir / f"raw_{vkey}.png"
        scene.render.filepath = str(out_png)
        bpy.ops.render.render(write_still=True)
        print(f"[HW13 RENDER] {vkey} (door={door_deg:.0f} deg) -> {out_png} ({out_png.stat().st_size} bytes)")

        # Record exact 2D pixel projections for every callout anchor
        anchors = _collect_callout_anchors_blender()
        pts_2d: dict[str, list[float]] = {}
        for akey, wpos in anchors.items():
            co = world_to_camera_view(scene, cam, wpos)
            px = round(float(co.x) * W, 1)
            py = round((1.0 - float(co.y)) * H, 1)
            pts_2d[akey] = [px, py, round(float(co.z), 3)]
        projections["views"][vkey] = {
            "raw_png": str(out_png),
            "door_angle_deg": door_deg,
            "points": pts_2d,
        }

    # Restore door to 0 deg cleanly
    if door_pivot is not None:
        door_pivot.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")
    if horn_pivot is not None:
        horn_pivot.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")
    bpy.context.view_layer.update()

    proj_json.parent.mkdir(parents=True, exist_ok=True)
    proj_json.write_text(json.dumps(projections, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[HW13 PROJ] Saved exact 2D label projections to {proj_json}")


def main() -> None:
    render_dir = None
    overview_png = None
    interior_png = None
    hw13_raw_dir = None
    hw14_raw_dir = None
    render_only = False
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1:]
        if "--render-dir" in args:
            idx = args.index("--render-dir")
            if idx + 1 < len(args):
                render_dir = pathlib.Path(args[idx + 1])
        if "--overview-png" in args:
            idx = args.index("--overview-png")
            if idx + 1 < len(args):
                overview_png = pathlib.Path(args[idx + 1])
        if "--interior-png" in args:
            idx = args.index("--interior-png")
            if idx + 1 < len(args):
                interior_png = pathlib.Path(args[idx + 1])
        if "--hw13-raw-dir" in args:
            idx = args.index("--hw13-raw-dir")
            if idx + 1 < len(args):
                hw13_raw_dir = pathlib.Path(args[idx + 1])
        if "--hw14-raw-dir" in args:
            idx = args.index("--hw14-raw-dir")
            if idx + 1 < len(args):
                hw14_raw_dir = pathlib.Path(args[idx + 1])
        if "--render-only" in args:
            render_only = True

    if render_only and hw14_raw_dir is not None and OUT_BLEND.exists():
        bpy.ops.wm.open_mainfile(filepath=str(OUT_BLEND))
        render_hw14_views(
            raw_dir=hw14_raw_dir,
            proj_json=REPO_ROOT / "hardware" / "blender" / "render_projections_hw14.json",
        )
        return

    if render_only and hw13_raw_dir is not None and OUT_BLEND.exists():
        bpy.ops.wm.open_mainfile(filepath=str(OUT_BLEND))
        render_hw13_views(
            raw_dir=hw13_raw_dir,
            proj_json=REPO_ROOT / "hardware" / "blender" / "render_projections.json",
        )
        return

    clear_scene()
    mats = build_materials()
    _arch, honeycomb_count = build_open_cutaway_house(mats)
    import_kicad_pcb_and_nodemcu(mats)
    build_hardware_devices_and_sensors(mats)
    _harness, wire_count = build_routed_40_wires(mats)
    convert_curves_to_meshes()
    setup_studio_lighting()

    cam_default = create_camera("Camera", (240.0, 355.0, 520.0), (0.0, 42.0, 45.0), lens_mm=38.0)
    bpy.context.scene.camera = cam_default

    OUT_BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))
    print(f"[BLEND] Saved {OUT_BLEND} ({OUT_BLEND.stat().st_size} bytes)")

    write_scene_spec(wire_count, honeycomb_count=honeycomb_count)

    # Export optimized PBR GLB (exclude lights & cameras)
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
    print(f"[GLB] Exported {OUT_GLB} ({OUT_GLB.stat().st_size} bytes / {OUT_GLB.stat().st_size / (1024*1024):.3f} MB)")

    if render_dir is not None or overview_png is not None or interior_png is not None:
        render_presentation_views(render_dir=render_dir, overview_png=overview_png, interior_png=interior_png)

    if hw13_raw_dir is not None:
        render_hw13_views(
            raw_dir=hw13_raw_dir,
            proj_json=REPO_ROOT / "hardware" / "blender" / "render_projections.json",
        )

    if hw14_raw_dir is not None:
        render_hw14_views(
            raw_dir=hw14_raw_dir,
            proj_json=REPO_ROOT / "hardware" / "blender" / "render_projections_hw14.json",
        )


if __name__ == "__main__":
    main()
