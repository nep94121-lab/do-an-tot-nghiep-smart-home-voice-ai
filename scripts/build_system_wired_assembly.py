r"""Deterministic 3D Wired Hardware Assembly Builder & Studio Renderer.

Reads `hardware/wiring_contract.py` (Single Source of Truth) and imports the actual
KiCad 3D Central Hub PCB (`hardware/kicad/smarthome_hub/3d/smarthome_hub.glb`) at exact
1:1 physical millimeters (1 mm = 0.001 m), mounting NodeMCU v2 Amica flush on U1/U2 and
arranging all 14 off-board modules radially around the 100x80 mm 1-layer DIY hub PCB with all 40
color-coded plug-in Dupont / terminal wires (`W01..W40`).

Two execution modes:
  1. Blender mode (builds 3D assembly, runs programmatic verification, exports .blend/.glb,
     renders 2200x1500 studio PNGs + exports projected 2D pixel anchor coordinates):
       blender.exe --background --python scripts/build_system_wired_assembly.py -- \
           --out-dir C:\Users\LENOVO\datn-wt\agyhwwire1_20261120
  2. Annotate + GLB Verify mode (runs trimesh GLB audit + Pillow callout overlay pass):
       python.exe scripts/build_system_wired_assembly.py --annotate \
           --out-dir C:\Users\LENOVO\datn-wt\agyhwwire1_20261120
"""

from __future__ import annotations

import json
import math
import pathlib
import re
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hardware.wiring_contract import (  # noqa: E402
    HUB_CONNECTOR_MAP,
    HUB_CONNECTORS,
    MODULE_DIMENSIONS_MM,
    WIRE_COLORS,
    WIRING_TABLE,
)

KICAD_PCB_GLB = REPO_ROOT / "hardware" / "kicad" / "smarthome_hub" / "3d" / "smarthome_hub.glb"
OUT_BLEND = REPO_ROOT / "hardware" / "blender" / "system_wired_assembly.blend"
OUT_GLB = REPO_ROOT / "hardware" / "blender" / "system_wired_assembly.glb"

# Exact 1:1 physical millimeters -> meters (standard glTF / KiCad scale)
MM = 0.001

# Hub PCB elevation: FR4 bottom sits flush on 6.0 mm brass M3 standoffs above Z=0 workbench mat
PCB_W_MM = 100.0
PCB_H_MM = 80.0
PCB_Z_BOT = 6.0
PCB_FR4_THICK = 1.51  # exact measured thickness in smarthome_hub.glb
U12_SOCKET_TOP_Z = PCB_Z_BOT + 10.10  # 16.10 mm (measured socket top in smarthome_hub.glb)
NODEMCU_DX_MM = -1.57                 # U1/U2 center bx=48.43 - 50.0 = -1.57 mm
NODEMCU_DY_MM = +1.22                 # U1/U2 center by=41.22 - 40.0 = +1.22 mm (North/+Y)
DUPONT_TOP_Z = PCB_Z_BOT + 13.05      # 19.05 mm (wire emerges top of black 2.54mm Dupont plug)
PHOENIX_MOUTH_X = -45.60              # exact -X face of J1/J2 Phoenix terminal (bx=9.0 -> wx=-41.0, mouth -4.60)
PHOENIX_MOUTH_Z = PCB_Z_BOT + 6.50    # 12.50 mm horizontal wire entry center

# 7 top-side 22AWG insulated wire jumpers (JP1..JP7) from hardware/kicad/smarthome_hub/build_diy_hub.py
# Format: (ref, (x1_rel, y1_rel), (x2_rel, y2_rel), wire_color) in top-left PCB local mm (0..100, 0..80)
DIY_TOP_JUMPERS: tuple[tuple[str, tuple[float, float], tuple[float, float], str], ...] = (
    ("JP1", (43.00, 33.70), (55.70, 33.70), "Orange"),  # +3.3V belly -> right bus (12.70 mm)
    ("JP2", (40.50, 18.00), (22.72, 18.00), "Orange"),  # +3.3V belly -> J14 SOIL_A0 (17.78 mm)
    ("JP3", (76.00, 33.30), (76.00, 25.68), "Orange"),  # +3.3V right -> top pull-ups (7.62 mm)
    ("JP4", (36.50, 60.00), (72.06, 60.00), "Red"),     # +5V U1.15 -> right RLY2 bus (35.56 mm)
    ("JP5", (85.50, 64.28), (85.50, 51.58), "Red"),     # +5V RLY2 -> RLY1 (12.70 mm)
    ("JP6", (85.50, 47.00), (85.50, 26.68), "Red"),     # +5V RLY1 -> top tunnel (20.32 mm)
    ("JP7", (85.50, 12.70), (60.10, 12.70), "Red"),     # +5V top -> J3 SERVO_D1 (25.40 mm)
)

RENDER_W = 2200
RENDER_H = 1500


# ==============================================================================
# COORDINATE HELPERS (Exact 1:1 mm: +X Right, +Y Top/North, +Z Up)
# ==============================================================================
def pcb_rel_to_world_xy(rel_x_mm: float, rel_y_mm: float) -> tuple[float, float]:
    """Convert KiCad PCB local mm (origin top-left 0..100, 0..80) to centered world (X, Y) mm."""
    return (rel_x_mm - PCB_W_MM * 0.5, PCB_H_MM * 0.5 - rel_y_mm)


def hub_pin_world_xyz(hub_ref: str, hub_pin: str) -> tuple[float, float, float]:
    """Return exact 3D wire-attachment coordinate (mm) for a Hub PCB connector pin."""
    conn = HUB_CONNECTOR_MAP[hub_ref]
    for pnum, rx, ry, _net in conn.pins:
        if pnum == hub_pin:
            wx, wy = pcb_rel_to_world_xy(rx, ry)
            if conn.kind == "screw_508":
                return (PHOENIX_MOUTH_X, wy, PHOENIX_MOUTH_Z)
            return (wx, wy, DUPONT_TOP_Z)
    raise KeyError(f"Unknown hub pin {hub_ref}.{hub_pin}")


def smooth_polyline(pts: list[tuple[float, float, float]], fillet_mm: float = 3.2, subdiv: int = 4) -> list[tuple[float, float, float]]:
    """Apply clean quadratic Bezier corner fillets so cables arch smoothly without sharp kinks."""
    if len(pts) <= 2:
        return list(pts)
    out: list[tuple[float, float, float]] = [pts[0]]
    for i in range(1, len(pts) - 1):
        p0 = pts[i - 1]
        p1 = pts[i]
        p2 = pts[i + 1]
        v1 = (p0[0] - p1[0], p0[1] - p1[1], p0[2] - p1[2])
        v2 = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
        l1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2 + v1[2] ** 2)
        l2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2 + v2[2] ** 2)
        if l1 < 1e-4 or l2 < 1e-4:
            out.append(p1)
            continue
        r = min(fillet_mm, l1 * 0.42, l2 * 0.42)
        a = (p1[0] + v1[0] * (r / l1), p1[1] + v1[1] * (r / l1), p1[2] + v1[2] * (r / l1))
        b = (p1[0] + v2[0] * (r / l2), p1[1] + v2[1] * (r / l2), p1[2] + v2[2] * (r / l2))
        for k in range(subdiv + 1):
            t = k / subdiv
            mt = 1.0 - t
            qx = mt * mt * a[0] + 2 * mt * t * p1[0] + t * t * b[0]
            qy = mt * mt * a[1] + 2 * mt * t * p1[1] + t * t * b[1]
            qz = mt * mt * a[2] + 2 * mt * t * p1[2] + t * t * b[2]
            out.append((qx, qy, qz))
    out.append(pts[-1])
    return out


# ==============================================================================
# PART 1: BLENDER 3D SCENE BUILDER, VERIFIER & RENDERER
# ==============================================================================
def run_blender_pipeline(out_dir: pathlib.Path) -> None:
    import bmesh
    import bpy
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Euler, Vector

    def vmm(x: float, y: float, z: float) -> Vector:
        return Vector((x * MM, y * MM, z * MM))

    def clear_scene() -> None:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if bpy.context.scene.world is None:
            bpy.context.scene.world = bpy.data.worlds.new("WorkbenchStudioWorld")

    def make_mat(
        name: str,
        rgba: tuple[float, float, float, float],
        roughness: float = 0.42,
        metallic: float = 0.0,
        emission: tuple[float, float, float] | None = None,
        emission_strength: float = 0.0,
        alpha: float = 1.0,
    ):
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

    def make_group(name: str, x_mm: float, y_mm: float, z_mm: float, parent=None):
        empty = bpy.data.objects.new(name, None)
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = 5.0 * MM
        bpy.context.collection.objects.link(empty)
        if parent is not None:
            empty.parent = parent
        empty.location = vmm(x_mm, y_mm, z_mm)
        return empty

    def add_box(
        name: str,
        x_mm: float,
        y_mm: float,
        z_mm: float,
        sx_mm: float,
        sy_mm: float,
        sz_mm: float,
        mat,
        parent=None,
        bevel_mm: float = 0.0,
        rot_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ):
        mesh = bpy.data.meshes.new(name + "_mesh")
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(sx_mm * MM, sy_mm * MM, sz_mm * MM), verts=bm.verts)
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
        obj.location = vmm(x_mm, y_mm, z_mm)
        if any(abs(a) > 1e-6 for a in rot_deg):
            obj.rotation_euler = Euler([math.radians(a) for a in rot_deg], "XYZ")
        return obj

    def add_cyl(
        name: str,
        x_mm: float,
        y_mm: float,
        z_mm: float,
        radius_mm: float,
        height_mm: float,
        mat,
        parent=None,
        axis: str = "Z",
        segs: int = 24,
    ):
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
        obj.location = vmm(x_mm, y_mm, z_mm)
        if axis == "X":
            obj.rotation_euler = Euler((0.0, math.pi / 2.0, 0.0), "XYZ")
        elif axis == "Y":
            obj.rotation_euler = Euler((math.pi / 2.0, 0.0, 0.0), "XYZ")
        return obj

    def add_sphere(
        name: str,
        x_mm: float,
        y_mm: float,
        z_mm: float,
        radius_mm: float,
        mat,
        parent=None,
        segs: int = 20,
    ):
        mesh = bpy.data.meshes.new(name + "_mesh")
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=12, radius=radius_mm * MM)
        bm.to_mesh(mesh)
        bm.free()
        obj.data.materials.append(mat)
        if parent is not None:
            obj.parent = parent
        obj.location = vmm(x_mm, y_mm, z_mm)
        return obj

    def add_wire_curve(
        name: str,
        pts_mm: list[tuple[float, float, float]],
        radius_mm: float,
        mat,
        parent=None,
        bevel_res: int = 3,
    ):
        curve_data = bpy.data.curves.new(name + "_curve", type="CURVE")
        curve_data.dimensions = "3D"
        curve_data.resolution_u = 4
        curve_data.bevel_depth = radius_mm * MM
        curve_data.bevel_resolution = bevel_res
        curve_data.fill_mode = "FULL"
        curve_data.use_fill_caps = True

        spline = curve_data.splines.new("POLY")
        spline.points.add(len(pts_mm) - 1)
        for idx, (x, y, z) in enumerate(pts_mm):
            spline.points[idx].co = (x * MM, y * MM, z * MM, 1.0)

        obj = bpy.data.objects.new(name, curve_data)
        bpy.context.collection.objects.link(obj)
        obj.data.materials.append(mat)
        if parent is not None:
            obj.parent = parent
        return obj

    def build_materials() -> dict[str, Any]:
        mats: dict[str, Any] = {
            # Cool medium-light architectural cutting mat (high contrast for BOTH black AND white parts!)
            "mat_surface": make_mat("WorkbenchMatSurface", (0.56, 0.62, 0.68, 1.0), roughness=0.78),
            "mat_bezel":   make_mat("WorkbenchBezel",      (0.10, 0.13, 0.18, 1.0), roughness=0.38, metallic=0.25),
            "grid_minor":  make_mat("GridLineMinor",       (0.45, 0.51, 0.58, 1.0), roughness=0.82),
            "grid_major":  make_mat("GridLineMajor",       (0.32, 0.38, 0.46, 1.0), roughness=0.78),

            # Electronic hardware materials (rich studio saturation)
            "pcb_black":   make_mat("PCB_Black",       (0.03, 0.035, 0.045, 1.0), roughness=0.34, metallic=0.06),
            "pcb_blue":    make_mat("PCB_Blue",        (0.03, 0.16, 0.58, 1.0), roughness=0.32, metallic=0.05),
            "pcb_red":     make_mat("PCB_Red",         (0.62, 0.05, 0.06, 1.0), roughness=0.32, metallic=0.05),
            "pcb_green":   make_mat("PCB_Green",       (0.03, 0.36, 0.12, 1.0), roughness=0.32, metallic=0.05),
            "relay_cube":  make_mat("SongleRelayBlue", (0.04, 0.34, 0.80, 1.0), roughness=0.28),
            "term_blue":   make_mat("ScrewTermBlue",   (0.05, 0.26, 0.65, 1.0), roughness=0.36),
            "sg90_blue":   make_mat("ServoSG90Blue",   (0.06, 0.34, 0.84, 0.90), roughness=0.24, alpha=0.90),
            "sg90_label":  make_mat("ServoSticker",    (0.90, 0.72, 0.08, 1.0), roughness=0.40),
            "dht_blue":    make_mat("DHT11Blue",       (0.06, 0.48, 0.88, 1.0), roughness=0.34),
            "pump_white":  make_mat("PumpWhite",       (0.92, 0.94, 0.96, 1.0), roughness=0.32),
            "plastic_blk": make_mat("PlasticBlack",    (0.025, 0.025, 0.03, 1.0), roughness=0.42),
            "dupont_blk":  make_mat("DupontHousing",   (0.02, 0.02, 0.025, 1.0), roughness=0.36),
            "plastic_wht": make_mat("PlasticWhite",    (0.92, 0.93, 0.95, 1.0), roughness=0.34),
            "jumper_yel":  make_mat("JumperYellow",    (0.95, 0.76, 0.04, 1.0), roughness=0.34),
            "silver_mtl":  make_mat("BrushedSilver",   (0.76, 0.79, 0.83, 1.0), roughness=0.24, metallic=0.90),
            "brass":       make_mat("MachinedBrass",   (0.84, 0.64, 0.18, 1.0), roughness=0.24, metallic=0.90),
            "copper":      make_mat("GoldPin",         (0.90, 0.70, 0.18, 1.0), roughness=0.20, metallic=0.94),
            "ic_black":    make_mat("IC_EpoxyBlack",   (0.04, 0.04, 0.05, 1.0), roughness=0.30),
            "pot_blue":    make_mat("TrimmerPotBlue",  (0.05, 0.28, 0.76, 1.0), roughness=0.36),
            "mic_felt":    make_mat("ElectretFelt",    (0.03, 0.03, 0.04, 1.0), roughness=0.92),
            "led_lr":      make_mat("LED_LivingWarm",  (1.00, 0.86, 0.45, 1.0), roughness=0.14, emission=(1.0, 0.82, 0.30), emission_strength=1.2),
            "led_br":      make_mat("LED_BedroomAmb",  (1.00, 0.68, 0.25, 1.0), roughness=0.14, emission=(1.0, 0.60, 0.15), emission_strength=1.2),
            "led_red":     make_mat("LED_StatusRed",   (0.95, 0.10, 0.08, 1.0), roughness=0.18, emission=(0.95, 0.10, 0.08), emission_strength=0.9),
            "led_grn":     make_mat("LED_StatusGreen", (0.10, 0.85, 0.24, 1.0), roughness=0.18, emission=(0.10, 0.85, 0.24), emission_strength=0.9),
        }
        # Generate exact wire insulation materials directly from wiring_contract.WIRE_COLORS
        for cname, cinfo in WIRE_COLORS.items():
            r, g, b = cinfo["rgb"]
            if cname == "White":
                rgba = (0.94, 0.96, 0.98, 1.0)
            elif cname == "Black":
                rgba = (0.025, 0.025, 0.03, 1.0)
            else:
                rgba = (float(r), float(g), float(b), 1.0)
            mats[f"wire_{cname}"] = make_mat(f"Wire_{cname}", rgba, roughness=0.34, metallic=0.04)
        return mats

    def build_workbench(mats: dict[str, Any]):
        wb = make_group("WorkbenchMat", 0.0, 0.0, 0.0)
        # Main architectural cutting mat: 360 x 250 x 4 mm, top flush at Z = 0.0 mm
        mat_w, mat_h = 360.0, 250.0
        cy = -4.0
        add_box("Workbench_Bezel",   0.0, cy, -2.6, mat_w + 8.0, mat_h + 8.0, 5.2, mats["mat_bezel"], parent=wb, bevel_mm=1.0)
        add_box("Workbench_Surface", 0.0, cy, -1.5, mat_w,       mat_h,       3.0, mats["mat_surface"], parent=wb, bevel_mm=0.2)
        # Subtle 10mm engineering grid lines (flush at Z = +0.02 mm)
        x0, x1 = -170.0, 170.0
        y0, y1 = -120.0, 110.0
        for gx in range(int(x0), int(x1) + 1, 10):
            is_maj = (gx % 50 == 0)
            add_box(
                f"GridX_{gx}", gx, 0.5 * (y0 + y1), 0.02,
                0.35 if is_maj else 0.16, y1 - y0, 0.04,
                mats["grid_major"] if is_maj else mats["grid_minor"], parent=wb,
            )
        for gy in range(int(y0), int(y1) + 1, 10):
            is_maj = (gy % 50 == 0)
            add_box(
                f"GridY_{gy}", 0.5 * (x0 + x1), gy, 0.02,
                x1 - x0, 0.35 if is_maj else 0.16, 0.04,
                mats["grid_major"] if is_maj else mats["grid_minor"], parent=wb,
            )
        return wb

    def build_hub_pcb_and_nodemcu(mats: dict[str, Any]):
        if not KICAD_PCB_GLB.exists():
            raise FileNotFoundError(f"Missing KiCad 3D PCB GLB: {KICAD_PCB_GLB}")

        hub = make_group("hub_pcb", 0.0, 0.0, PCB_Z_BOT)
        # 4 brass M3 standoffs under M3 mounting holes (5.0 mm inset from 100x80 edges -> 90x70 mm pitch)
        standoffs = make_group("HubStandoffs", 0.0, 0.0, 0.0)
        for idx, (hx, hy) in enumerate([(5.0, 5.0), (95.0, 5.0), (5.0, 75.0), (95.0, 75.0)]):
            wx, wy = pcb_rel_to_world_xy(hx, hy)
            add_cyl(f"Hub_Standoff_M3_{idx + 1}", wx, wy, PCB_Z_BOT * 0.5, 2.5, PCB_Z_BOT, mats["brass"], parent=standoffs, segs=20)
            # M3 brass hex nut / screw cap on top of FR4
            add_cyl(f"Hub_ScrewHead_M3_{idx + 1}", wx, wy, PCB_Z_BOT + PCB_FR4_THICK + 0.9, 2.6, 1.8, mats["silver_mtl"], parent=standoffs, segs=6)

        # Import actual KiCad 3D PCB GLB at exact 1:1 m
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(KICAD_PCB_GLB))
        imported = [o for o in bpy.data.objects if o not in before]
        imported_roots = [o for o in imported if o.parent is None]
        bpy.context.view_layer.update()

        xs, ys, zs = [], [], []
        fr4_zmin = None
        for o in imported:
            if o.type == "MESH":
                mxs, mys, mzs = [], [], []
                for c in o.bound_box:
                    wc = o.matrix_world @ Vector(c)
                    xs.append(wc.x); ys.append(wc.y); zs.append(wc.z)
                    mxs.append(wc.x); mys.append(wc.y); mzs.append(wc.z)
                dz_m = max(mzs) - min(mzs)
                if (max(mxs) - min(mxs)) > 0.098 and (max(mys) - min(mys)) > 0.078 and 0.001 < dz_m < 0.003:
                    fr4_zmin = min(mzs)
        cx_m = 0.5 * (min(xs) + max(xs))
        cy_m = 0.5 * (min(ys) + max(ys))
        z_align_m = fr4_zmin if fr4_zmin is not None else 0.0

        for r in imported_roots:
            r.parent = hub
            r.location = Vector((r.location.x - cx_m, r.location.y - cy_m, r.location.z - z_align_m))

        # Add the 7 top-side 22AWG insulated wire jumpers (JP1..JP7) directly onto the 1-layer DIY hub PCB
        for jref, (x1, y1), (x2, y2), wcol in DIY_TOP_JUMPERS:
            wx1, wy1 = pcb_rel_to_world_xy(x1, y1)
            wx2, wy2 = pcb_rel_to_world_xy(x2, y2)
            dx, dy = wx2 - wx1, wy2 - wy1
            jlen = max(1e-3, math.hypot(dx, dy))
            ux, uy = dx / jlen, dy / jlen
            arch_z = 3.6  # local Z above FR4 bottom (2.0mm above FR4 top, well below NodeMCU bottom 10.1mm)
            jpts = [
                (wx1, wy1, 1.4),
                (wx1, wy1, arch_z - 0.5),
                (wx1 + ux * 0.9, wy1 + uy * 0.9, arch_z),
                (wx2 - ux * 0.9, wy2 - uy * 0.9, arch_z),
                (wx2, wy2, arch_z - 0.5),
                (wx2, wy2, 1.4),
            ]
            add_wire_curve(f"DIY_Jumper_{jref}", jpts, 0.55, mats[f"wire_{wcol}"], parent=hub, bevel_res=3)

        # Authentic ESP8266 NodeMCU v2 Amica seated flush on U1/U2 socket top (Z = 16.10 mm, XY = (-1.57, +1.22))
        # Official Amica PCB: 25.40 x 48.26 x 1.60 mm (~49.43 mm w/ Micro-USB overhang), total H = 7.14 mm
        mcu = make_group("nodemcu", NODEMCU_DX_MM, NODEMCU_DY_MM, U12_SOCKET_TOP_Z)
        for side, sx in [("L", -11.43), ("R", 11.43)]:
            add_box(f"NodeMCU_MaleHdr_{side}", sx, 0.0, 1.27, 2.54, 38.10, 2.54, mats["plastic_blk"], parent=mcu)
            add_box(f"NodeMCU_PinBar_{side}",  sx, 0.0, 4.64, 1.40, 37.50, 1.00, mats["copper"], parent=mcu)
        add_box("NodeMCU_PCB",            0.0,   0.0, 3.34, 25.40, 48.26, 1.60, mats["pcb_black"], parent=mcu, bevel_mm=0.2)
        add_box("NodeMCU_ESP12E_Shield",  0.0,   7.0, 5.64, 16.00, 12.00, 3.00, mats["silver_mtl"], parent=mcu, bevel_mm=0.2)
        add_box("NodeMCU_WiFi_Zone",      0.0,  18.5, 4.29, 16.00,  7.00, 0.30, mats["pcb_black"], parent=mcu)
        for k in range(5):
            add_box(f"NodeMCU_Ant_{k}", -6.0 + k * 3.0, 18.5, 4.49, 0.70, 5.80, 0.15, mats["copper"], parent=mcu)
        add_box("NodeMCU_CP2102",         0.0,  -9.5, 4.64,  5.00,  5.00, 1.00, mats["ic_black"], parent=mcu)
        add_box("NodeMCU_AMS1117",       -6.5, -15.0, 4.89,  6.50,  3.50, 1.50, mats["ic_black"], parent=mcu)
        add_box("NodeMCU_MicroUSB",       0.0, -22.5, 5.54,  7.80,  5.60, 2.80, mats["silver_mtl"], parent=mcu, bevel_mm=0.2)
        add_box("NodeMCU_Btn_RST",       -6.2, -20.5, 4.89,  3.20,  2.40, 1.50, mats["silver_mtl"], parent=mcu)
        add_box("NodeMCU_Btn_FLASH",      6.2, -20.5, 4.89,  3.20,  2.40, 1.50, mats["silver_mtl"], parent=mcu)
        add_box("NodeMCU_StatusLED",      6.2,  12.5, 4.54,  1.60,  0.80, 0.80, mats["dht_blue"], parent=mcu)

        return hub, mcu

    def build_offboard_modules(mats: dict[str, Any]) -> tuple[dict[str, Any], dict[tuple[str, str], tuple[float, float, float]]]:
        """Build all 14 off-board modules at exact datasheet dimensions.

        Returns (module_objects_by_id, exact_pin_coords_mm[(module_id, pin_label)]).
        """
        mods: dict[str, Any] = {}
        pins: dict[tuple[str, str], tuple[float, float, float]] = {}

        # ------------------------------------------------------------------
        # LEFT SIDE: pump_unit (facing J2) & psu_5v (facing J1)
        # ------------------------------------------------------------------
        # 1. Mini Submersible Water Pump (45.0 L x 24.0 dia x 33.0 H mm, Ø7.5 nozzle)
        px, py = -112.0, 20.0
        pump = make_group("pump_unit", px, py, 0.0)
        add_cyl("Pump_Body",        -5.0, 0.0, 12.0, 12.0, 35.0, mats["pump_white"], parent=pump, axis="X", segs=28)
        add_cyl("Pump_Intake",      17.5, 0.0, 12.0,  4.0, 10.0, mats["pump_white"], parent=pump, axis="X", segs=18)
        add_cyl("Pump_OutletNozzle", 7.0, 0.0, 28.5, 3.75,  9.0, mats["pump_white"], parent=pump, axis="Z", segs=18)
        # Re-orient intake to -X so wire exit rear cap faces +X cleanly toward J2!
        bpy.data.objects["Pump_Body"].location = vmm(5.0, 0.0, 12.0)
        bpy.data.objects["Pump_Intake"].location = vmm(-17.5, 0.0, 12.0)
        bpy.data.objects["Pump_OutletNozzle"].location = vmm(-7.0, 0.0, 28.5)
        mods["pump_unit"] = pump
        pins[("pump_unit", "Pump + (Red)")] = (px + 22.5, py + 2.5, 12.0)
        pins[("pump_unit", "Pump - (Black)")] = (px + 22.5, py - 2.5, 12.0)

        # 2. 5V 2A External Power Supply Terminal (34.0 x 22.0 x 16.0 mm)
        psx, psy = -106.0, -18.0
        psu = make_group("psu_5v", psx, psy, 0.0)
        add_box("PSU_BasePCB",       0.0,  0.0,  1.0, 34.0, 22.0,  2.0, mats["pcb_black"], parent=psu, bevel_mm=0.2)
        add_box("PSU_DC005_Jack",   -8.0,  0.0,  7.5, 14.5, 10.0, 11.0, mats["plastic_blk"], parent=psu, bevel_mm=0.3)
        add_cyl("PSU_BarrelSleeve",-15.8,  0.0,  7.5,  3.2,  2.4, mats["silver_mtl"], parent=psu, axis="X", segs=18)
        bpy.data.objects["PSU_BarrelSleeve"].location = vmm(-15.8, 0.0, 7.5)
        add_box("PSU_ScrewBlock",   11.5,  0.0,  9.0, 11.0, 12.0, 14.0, mats["term_blue"], parent=psu, bevel_mm=0.25)
        for k, sy in enumerate([2.54, -2.54]):
            add_cyl(f"PSU_Screw_{k}", 11.5, sy, 15.7, 1.8, 0.6, mats["silver_mtl"], parent=psu, axis="Z", segs=16)
        add_box("PSU_LED_5V",        1.5,  6.5,  2.6,  2.4,  1.6,  1.2, mats["led_red"], parent=psu)
        mods["psu_5v"] = psu
        pins[("psu_5v", "+5V")] = (psx + 17.0, psy + 2.54, 9.5)
        pins[("psu_5v", "GND")] = (psx + 17.0, psy - 2.54, 9.5)

        # ------------------------------------------------------------------
        # TOP SIDE: soil_probe, soil_lm393 (J14), led_living (J4), sg90_servo (J3), dht11_sensor (J13)
        # ------------------------------------------------------------------
        # 3. YL-69 Soil Fork Probe (60.0 x 20.0 x 1.6 mm)
        spx, spy = -120.0, 84.0
        probe = make_group("soil_probe", spx, spy, 0.0)
        add_box("SoilProbe_Head",    21.0,  0.0, 0.8, 18.0, 20.0, 1.6, mats["pcb_black"], parent=probe, bevel_mm=0.15)
        add_box("SoilProbe_ProngA",  -9.0,  5.0, 0.8, 42.0,  5.0, 1.6, mats["silver_mtl"], parent=probe, bevel_mm=0.1)
        add_box("SoilProbe_ProngB",  -9.0, -5.0, 0.8, 42.0,  5.0, 1.6, mats["silver_mtl"], parent=probe, bevel_mm=0.1)
        add_box("SoilProbe_PadA",    28.0,  1.27, 1.55, 2.6, 1.4, 0.1, mats["copper"], parent=probe)
        add_box("SoilProbe_PadB",    28.0, -1.27, 1.55, 2.6, 1.4, 0.1, mats["copper"], parent=probe)
        mods["soil_probe"] = probe
        pins[("soil_probe", "Prong A")] = (spx + 30.0, spy + 1.27, 1.6)
        pins[("soil_probe", "Prong B")] = (spx + 30.0, spy - 1.27, 1.6)

        # 4. Soil LM393 Comparator Module (32.0 x 14.0 x 12.1 mm -> oriented 14.0 X x 32.0 Y x 12.1 Z)
        lmx, lmy = -56.0, 78.0
        lm = make_group("soil_lm393", lmx, lmy, 0.0)
        add_box("LM393_BluePCB",   0.0,   0.0,  0.80, 14.0, 32.0, 1.60, mats["pcb_blue"], parent=lm, bevel_mm=0.18)
        add_box("LM393_TrimPot",   0.0,   2.0,  6.35,  4.8,  9.5, 9.50, mats["pot_blue"], parent=lm)
        add_cyl("LM393_PotScrew",  0.0,   4.5, 11.60,  1.2,  1.0,       mats["brass"], parent=lm, axis="Z", segs=16)
        add_box("LM393_IC",        0.0,  -6.5,  2.30,  4.0,  5.0, 1.40, mats["ic_black"], parent=lm)
        add_box("LM393_LED_Pwr",  -4.2,  -4.0,  2.10,  1.4,  2.2, 1.00, mats["led_red"], parent=lm)
        add_box("LM393_LED_DO",    4.2,  -4.0,  2.10,  1.4,  2.2, 1.00, mats["led_grn"], parent=lm)
        add_box("LM393_Hdr4",      0.0, -14.5,  2.87, 10.16, 3.0, 2.54, mats["plastic_blk"], parent=lm)
        add_box("LM393_Hdr2",     -5.5,   8.0,  2.87,  3.0, 5.08, 2.54, mats["plastic_blk"], parent=lm)
        mods["soil_lm393"] = lm
        pins[("soil_lm393", "VCC")] = (lmx - 3.81, lmy - 16.0, 2.87)
        pins[("soil_lm393", "GND")] = (lmx - 1.27, lmy - 16.0, 2.87)
        pins[("soil_lm393", "AO")]  = (lmx + 3.81, lmy - 16.0, 2.87)
        pins[("LM393", "P1")] = (lmx - 7.0, lmy + 9.27, 2.87)
        pins[("LM393", "P2")] = (lmx - 7.0, lmy + 6.73, 2.87)

        # 5. Living Room 5mm LED (exact Kingbright WP7113: Ø5.8 flange, Ø5.0 body+dome, 8.6 mm H)
        llx, lly = -8.0, 76.0
        led_lr = make_group("led_living", llx, lly, 6.0)
        add_cyl("LED_LR_Flange", 0.0, 0.0, 0.50, 2.9, 1.0, mats["led_lr"], parent=led_lr, axis="Z", segs=24)
        add_cyl("LED_LR_Body",   0.0, 0.0, 3.55, 2.5, 5.1, mats["led_lr"], parent=led_lr, axis="Z", segs=24)
        add_sphere("LED_LR_Dome", 0.0, 0.0, 6.10, 2.5, mats["led_lr"], parent=led_lr, segs=20)
        mods["led_living"] = led_lr
        pins[("led_living", "Anode (+)")]   = (llx - 1.27, lly - 1.27, 2.0)
        pins[("led_living", "Cathode (-)")] = (llx + 1.27, lly - 1.27, 2.0)

        # 6. SG90 Micro Servo (body 22.8x12.2x22.5, flange 32.2mm, overall H 31.0mm) facing J3 on top edge
        sgx, sgy = 18.0, 78.0
        sg = make_group("sg90_servo", sgx, sgy, 0.0)
        add_box("SG90_Body",       0.0, 0.0, 11.25, 22.8, 12.2, 22.5, mats["sg90_blue"], parent=sg, bevel_mm=0.35)
        add_box("SG90_Flange",     0.0, 0.0, 17.15, 32.2, 12.2,  2.5, mats["sg90_blue"], parent=sg)
        add_box("SG90_Sticker",    0.0,-6.05, 10.0, 11.0,  0.1, 11.0, mats["sg90_label"], parent=sg)
        add_cyl("SG90_GearHub",    5.4, 0.0, 24.60,  5.9,  4.2,       mats["sg90_blue"], parent=sg, axis="Z", segs=24)
        add_cyl("SG90_Shaft",      5.4, 0.0, 27.85,  2.4,  2.3,       mats["plastic_wht"], parent=sg, axis="Z", segs=18)
        add_box("SG90_WhiteHorn",  9.1, 0.0, 30.00, 14.0,  4.5,  2.0, mats["plastic_wht"], parent=sg, bevel_mm=0.3)
        mods["sg90_servo"] = sg
        pins[("sg90_servo", "PWM (Orange)")] = (sgx - 2.54, sgy - 6.1, 4.5)
        pins[("sg90_servo", "VCC (Red)")]    = (sgx,        sgy - 6.1, 4.5)
        pins[("sg90_servo", "GND (Brown)")]  = (sgx + 2.54, sgy - 6.1, 4.5)

        # 7. DHT11 3-Pin Breakout (28.0 x 14.0 x 7.1 mm -> oriented 14.0 X x 28.0 Y x 7.1 Z) facing J13 on top edge
        dhx, dhy = 54.0, 78.0
        dht = make_group("dht11_sensor", dhx, dhy, 0.0)
        add_box("DHT11_PCB",       0.0,   0.0, 0.80, 14.0, 28.0, 1.60, mats["pcb_blue"], parent=dht, bevel_mm=0.18)
        add_box("DHT11_BlueGrid",  0.0,   3.5, 4.35, 12.0, 15.5, 5.50, mats["dht_blue"], parent=dht, bevel_mm=0.25)
        for row in range(3):
            for col in range(3):
                add_box(f"DHT11_Vent_{row}_{col}", -3.2 + col * 3.2, -0.5 + row * 4.0, 6.95, 1.9, 1.9, 0.3, mats["plastic_blk"], parent=dht)
        add_box("DHT11_Hdr3",      0.0, -12.5, 2.87, 7.62,  3.0, 2.54, mats["plastic_blk"], parent=dht)
        mods["dht11_sensor"] = dht
        pins[("dht11_sensor", "VCC (+)")]    = (dhx + 2.54, dhy - 14.0, 2.87)
        pins[("dht11_sensor", "DATA (OUT)")] = (dhx,        dhy - 14.0, 2.87)
        pins[("dht11_sensor", "GND (-)")]    = (dhx - 2.54, dhy - 14.0, 2.87)

        # ------------------------------------------------------------------
        # RIGHT SIDE: led_bedroom (J5), ky037_sound (J15), relay1_pump (J7/J8), buzzer_alarm (J6)
        # ------------------------------------------------------------------
        # 8. Bedroom 5mm LED (exact Kingbright WP7113: Ø5.8 flange, Ø5.0 body+dome, 8.6 mm H)
        lbx, lby = 88.0, 34.0
        led_br = make_group("led_bedroom", lbx, lby, 6.0)
        add_cyl("LED_BR_Flange", 0.0, 0.0, 0.50, 2.9, 1.0, mats["led_br"], parent=led_br, axis="Z", segs=24)
        add_cyl("LED_BR_Body",   0.0, 0.0, 3.55, 2.5, 5.1, mats["led_br"], parent=led_br, axis="Z", segs=24)
        add_sphere("LED_BR_Dome", 0.0, 0.0, 6.10, 2.5, mats["led_br"], parent=led_br, segs=20)
        mods["led_bedroom"] = led_br
        pins[("led_bedroom", "Anode (+)")]   = (lbx - 1.27, lby + 1.27, 2.0)
        pins[("led_bedroom", "Cathode (-)")] = (lbx - 1.27, lby - 1.27, 2.0)

        # 9. KY-037 / KY-038 Sound Sensor (35.0 x 15.0 x 13.1 mm, red PCB, Ø9.7x6.7 mic, 3296W pot, 4-pin header)
        kyx, kyy = 106.0, 8.0
        ky = make_group("ky037_sound", kyx, kyy, 0.0)
        add_box("KY037_RedPCB",    0.0,  0.0,  0.80, 35.0, 15.0,  1.60, mats["pcb_red"], parent=ky, bevel_mm=0.18)
        add_cyl("KY037_MicCan",   11.5,  0.0,  4.95, 4.85,  6.7,        mats["silver_mtl"], parent=ky, axis="Z", segs=24)
        add_cyl("KY037_MicFelt",  11.5,  0.0,  8.25, 4.30,  0.3,        mats["mic_felt"], parent=ky, axis="Z", segs=24)
        add_box("KY037_TrimPot",  -2.0,  3.5,  6.60,  9.5,  4.8, 10.00, mats["pot_blue"], parent=ky)
        add_cyl("KY037_PotScrew", -5.0,  3.5, 12.35,  1.2,  1.5,        mats["brass"], parent=ky, axis="Z", segs=16)
        add_box("KY037_LM393",    -1.5, -3.8,  2.30,  5.0,  4.0,  1.40, mats["ic_black"], parent=ky)
        add_cyl("KY037_MountHole",-10.0, 0.0,  1.60,  1.5,  1.8,        mats["silver_mtl"], parent=ky, axis="Z", segs=16)
        add_box("KY037_Hdr4",     -16.0, 0.0,  2.87,  3.0, 10.16, 2.54, mats["plastic_blk"], parent=ky)
        mods["ky037_sound"] = ky
        pins[("ky037_sound", "+ (VCC)")] = (kyx - 17.5, kyy + 3.81, 2.87)
        pins[("ky037_sound", "G (GND)")] = (kyx - 17.5, kyy + 1.27, 2.87)
        pins[("ky037_sound", "DO")]      = (kyx - 17.5, kyy - 1.27, 2.87)

        # 10. Relay 1 Blue 5V 1-ch (50.0 x 26.0 x 18.5 mm; 44.5x20.5 mm holes)
        r1x, r1y = 114.0, -22.0
        r1 = make_group("relay1_pump", r1x, r1y, 0.0)
        for idx, (fx, fy) in enumerate([(-22.25, -10.25), (22.25, -10.25), (-22.25, 10.25), (22.25, 10.25)]):
            add_cyl(f"Rly1_Foot_{idx}", fx, fy, 0.75, 1.5, 1.5, mats["brass"], parent=r1, axis="Z", segs=12)
        add_box("Rly1_BluePCB",     0.0,  0.0,  2.30, 50.0, 26.0,  1.60, mats["pcb_blue"], parent=r1, bevel_mm=0.2)
        add_box("Rly1_SongleCube", -2.5,  0.0, 10.80, 19.0, 15.5, 15.40, mats["relay_cube"], parent=r1, bevel_mm=0.35)
        add_box("Rly1_ScrewTerm",  19.0,  0.0,  8.10,  8.0, 15.24, 10.0, mats["term_blue"], parent=r1, bevel_mm=0.25)
        for k in range(3):
            add_cyl(f"Rly1_Screw_{k}", 19.0, (k - 1) * 5.08, 13.2, 1.8, 0.6, mats["silver_mtl"], parent=r1, axis="Z", segs=14)
        add_box("Rly1_PinHdr",    -22.5,  0.0,  6.00, 2.54,  7.62, 7.00, mats["plastic_blk"], parent=r1)
        add_box("Rly1_LED_Pwr",   -14.5,  6.5,  3.60,  2.2,   1.4, 1.00, mats["led_red"], parent=r1)
        add_box("Rly1_LED_Trig",  -14.5, -6.5,  3.60,  2.2,   1.4, 1.00, mats["led_grn"], parent=r1)
        mods["relay1_pump"] = r1
        pins[("relay1_pump", "VCC")]         = (r1x - 22.5, r1y - 2.54, 11.5)
        pins[("relay1_pump", "GND")]         = (r1x - 22.5, r1y,        11.5)
        pins[("relay1_pump", "IN")]          = (r1x - 22.5, r1y + 2.54, 11.5)
        pins[("relay1_pump", "COM (Screw)")] = (r1x + 23.0, r1y,         8.5)
        pins[("relay1_pump", "NO (Screw)")]  = (r1x + 23.0, r1y + 5.08,  8.5)

        # 11. Active 5V Buzzer TMB12A05 (Ø12.0 x 9.5 mm) driven by Q1 S8050 on J6
        bzx, bzy = 96.0, -68.0
        buz = make_group("buzzer_alarm", bzx, bzy, 0.0)
        add_cyl("Buzzer_Body",     0.0, 0.0, 4.75, 6.0, 9.5, mats["plastic_blk"], parent=buz, axis="Z", segs=28)
        add_cyl("Buzzer_Port",     0.0, 0.0, 9.38, 1.5, 0.25, mats["silver_mtl"], parent=buz, axis="Z", segs=18)
        add_box("Buzzer_PlusBar1",-3.2, 0.0, 9.48, 1.8, 0.4, 0.08, mats["plastic_wht"], parent=buz)
        add_box("Buzzer_PlusBar2",-3.2, 0.0, 9.48, 0.4, 1.8, 0.08, mats["plastic_wht"], parent=buz)
        mods["buzzer_alarm"] = buz
        pins[("buzzer_alarm", "Buzzer (+)")] = (bzx - 6.0, bzy + 1.27, 2.5)
        pins[("buzzer_alarm", "Buzzer (-)")] = (bzx - 6.0, bzy - 1.27, 2.5)

        # ------------------------------------------------------------------
        # BOTTOM SIDE: relay2_speaker, pam8403_amp, speaker_mini
        # ------------------------------------------------------------------
        # 12. Relay 2 Red Opto 5V (50.0 x 26.0 x 18.5 mm; 44.5x20.5 mm holes, Songle cube + PC817 + Yellow Jumper H)
        r2x, r2y = -42.0, -84.0
        r2 = make_group("relay2_speaker", r2x, r2y, 0.0)
        for idx, (fx, fy) in enumerate([(-22.25, -10.25), (22.25, -10.25), (-22.25, 10.25), (22.25, 10.25)]):
            add_cyl(f"Rly2_Foot_{idx}", fx, fy, 0.75, 1.5, 1.5, mats["brass"], parent=r2, axis="Z", segs=12)
        add_box("Rly2_RedPCB",       0.0,  0.0,  2.30, 50.0, 26.0,  1.60, mats["pcb_red"], parent=r2, bevel_mm=0.2)
        add_box("Rly2_SongleCube",  -2.0,  0.0, 10.80, 19.0, 15.5, 15.40, mats["relay_cube"], parent=r2, bevel_mm=0.35)
        add_box("Rly2_ScrewTerm",   19.0,  0.0,  8.10,  8.0, 15.24, 10.0, mats["term_blue"], parent=r2, bevel_mm=0.25)
        for k in range(3):
            add_cyl(f"Rly2_Screw_{k}", 19.0, (k - 1) * 5.08, 13.2, 1.8, 0.6, mats["silver_mtl"], parent=r2, axis="Z", segs=14)
        add_box("Rly2_OptoPC817",  -14.5,  0.0,  4.70,  4.6,  6.5,  3.20, mats["ic_black"], parent=r2)
        add_box("Rly2_JumperH",    -14.5,  7.5,  6.00,  5.2,  2.6,  5.80, mats["jumper_yel"], parent=r2)
        add_box("Rly2_PinHdr",     -22.5,  0.0,  6.00, 2.54,  7.62, 7.00, mats["plastic_blk"], parent=r2)
        add_box("Rly2_LED_Pwr",    -15.5, -7.5,  3.60,  2.2,   1.4, 1.00, mats["led_grn"], parent=r2)
        add_box("Rly2_LED_Trig",   -15.5, -4.5,  3.60,  2.2,   1.4, 1.00, mats["led_red"], parent=r2)
        mods["relay2_speaker"] = r2
        pins[("relay2_speaker", "DC+")]         = (r2x - 22.5, r2y - 2.54, 11.5)
        pins[("relay2_speaker", "DC-")]         = (r2x - 22.5, r2y,        11.5)
        pins[("relay2_speaker", "IN")]          = (r2x - 22.5, r2y + 2.54, 11.5)
        pins[("relay2_speaker", "COM (Screw)")] = (r2x + 23.0, r2y,         8.5)
        pins[("relay2_speaker", "NO (Screw)")]  = (r2x + 23.0, r2y + 5.08,  8.5)

        # 13. PAM8403 Green Audio Amplifier (21.0 x 18.0 x 3.1 mm, SOP-16 IC)
        pmx, pmy = 12.0, -84.0
        pam = make_group("pam8403_amp", pmx, pmy, 0.0)
        add_box("PAM8403_GreenPCB", 0.0, 0.0, 0.80, 21.0, 18.0, 1.60, mats["pcb_green"], parent=pam, bevel_mm=0.15)
        add_box("PAM8403_SOIC16",   0.0, 0.0, 2.35,  3.9,  9.9, 1.50, mats["ic_black"], parent=pam)
        for sx in (-2.48, 2.48):
            for k in range(8):
                add_box(f"PAM_Pin_{sx}_{k}", sx, -4.445 + k * 1.27, 1.75, 1.05, 0.42, 0.25, mats["silver_mtl"], parent=pam)
        for px_o, py_o in [(-7.0, 7.5), (-4.46, 7.5), (3.5, 7.5), (6.04, 7.5), (9.0, 1.27), (9.0, -1.27)]:
            add_cyl(f"PAM_Pad_{px_o}_{py_o}", px_o, py_o, 1.62, 0.85, 0.16, mats["copper"], parent=pam, axis="Z", segs=12)
        mods["pam8403_amp"] = pam
        pins[("pam8403_amp", "5V+")]           = (pmx - 7.00, pmy + 9.0, 2.0)
        pins[("pam8403_amp", "5V-")]           = (pmx - 4.46, pmy + 9.0, 2.0)
        pins[("pam8403_amp", "L (Audio In)")]  = (pmx + 3.50, pmy + 9.0, 2.0)
        pins[("pam8403_amp", "GND (Audio ⊥)")] = (pmx + 6.04, pmy + 9.0, 2.0)
        pins[("PAM8403", "L_OUT+")]            = (pmx + 10.5, pmy + 1.27, 2.0)
        pins[("PAM8403", "L_OUT-")]            = (pmx + 10.5, pmy - 1.27, 2.0)

        # 14. Mini Speaker 28mm 8Ω 0.5W (PUI Audio AS02808MR-R: exact Ø28.0 x 5.2 mm)
        skx, sky = 54.0, -84.0
        spk = make_group("speaker_mini", skx, sky, 0.0)
        add_cyl("Speaker_SilverRim",  0.0, 0.0, 2.30, 14.0, 4.6, mats["silver_mtl"], parent=spk, axis="Z", segs=32)
        add_cyl("Speaker_InnerCone",  0.0, 0.0, 4.60, 11.5, 0.6, mats["plastic_blk"], parent=spk, axis="Z", segs=28)
        add_cyl("Speaker_CenterCap",  0.0, 0.0, 4.90,  5.2, 0.6, mats["silver_mtl"], parent=spk, axis="Z", segs=24)
        mods["speaker_mini"] = spk
        pins[("speaker_mini", "SPK +")] = (skx - 14.0, sky + 1.27, 2.2)
        pins[("speaker_mini", "SPK -")] = (skx - 14.0, sky - 1.27, 2.2)

        return mods, pins

    def build_all_40_wires_and_dupont_housings(
        mats: dict[str, Any],
        mod_pins: dict[tuple[str, str], tuple[float, float, float]],
    ) -> dict[str, dict[str, Any]]:
        """Build all 40 contract wires + black 2.54mm Dupont housings at both ends."""
        harness = make_group("DupontWiringHarness", 0.0, 0.0, 0.0)
        WIRE_R = 0.68  # ~1.36 mm OD (realistic 22-26AWG Dupont PVC insulation)

        # 1. Black 2.54mm Dupont female connector housings on ALL 13 Hub 2.54mm pin headers (J3..J15)
        for conn in HUB_CONNECTORS:
            if conn.kind != "header_254":
                continue
            n = len(conn.pins)
            xs = [pcb_rel_to_world_xy(p[1], p[2])[0] for p in conn.pins]
            ys = [pcb_rel_to_world_xy(p[1], p[2])[1] for p in conn.pins]
            cx, cy = sum(xs) / n, sum(ys) / n
            is_horiz = (abs(max(xs) - min(xs)) > abs(max(ys) - min(ys)))
            sx = 2.54 * n if is_horiz else 2.54
            sy = 2.54 if is_horiz else 2.54 * n
            # Seated cleanly on male pins from Z = 10.05 to 19.05 mm (9.0 mm tall)
            add_box(f"HubDupontPlug_{conn.ref}", cx, cy, PCB_Z_BOT + 8.55, sx, sy, 9.0, mats["dupont_blk"], parent=harness, bevel_mm=0.12)

        # 2. Black 2.54mm Dupont connector housings seated on EVERY off-board module header/LED/buzzer
        # Soil LM393 4-pin side (1x2 for VCC/GND + 1x1 for AO, leaving DO visibly open!)
        add_box("ModPlug_LM393_Pwr", -58.54,  59.0, 2.87, 5.08, 6.0, 2.54, mats["dupont_blk"], parent=harness, bevel_mm=0.1)
        add_box("ModPlug_LM393_AO",  -52.19,  59.0, 2.87, 2.54, 6.0, 2.54, mats["dupont_blk"], parent=harness, bevel_mm=0.1)
        # Soil LM393 2-pin probe side & YL-69 probe head plug
        add_box("ModPlug_LM393_Prb", -66.0,   86.0, 2.87, 6.0, 5.08, 2.54, mats["dupont_blk"], parent=harness, bevel_mm=0.1)
        add_box("ModPlug_SoilProbe", -87.0,   84.0, 1.60, 6.0, 5.08, 2.54, mats["dupont_blk"], parent=harness, bevel_mm=0.1)
        # DHT11 1x3 plug
        add_box("ModPlug_DHT11",      54.0,   61.0, 2.87, 7.62, 6.0, 2.54, mats["dupont_blk"], parent=harness, bevel_mm=0.1)
        # Living & Bedroom 5mm LED vertical 1x2 Dupont sockets (Z = 0..6.0 mm directly under LED flange!)
        add_box("ModPlug_LED_LR",     -8.0,   76.0, 3.00, 5.08, 2.54, 6.0, mats["dupont_blk"], parent=harness, bevel_mm=0.1)
        add_box("ModPlug_LED_BR",     88.0,   34.0, 3.00, 2.54, 5.08, 6.0, mats["dupont_blk"], parent=harness, bevel_mm=0.1)
        # KY-037 1x3 plug (+, G, DO; AO pin left visibly open!)
        add_box("ModPlug_KY037",      85.5,    9.27, 2.87, 6.0, 7.62, 2.54, mats["dupont_blk"], parent=harness, bevel_mm=0.1)
        # Relay 1 1x3 vertical plug seated on pins
        add_box("ModPlug_Relay1_In",  91.5,  -22.0,  8.50, 2.54, 7.62, 6.0, mats["dupont_blk"], parent=harness, bevel_mm=0.1)
        # Buzzer 1x2 plug
        add_box("ModPlug_Buzzer",     87.5,  -68.0,  2.50, 5.0, 5.08, 2.54, mats["dupont_blk"], parent=harness, bevel_mm=0.1)
        # Relay 2 1x3 vertical plug seated on pins
        add_box("ModPlug_Relay2_In", -64.5,  -84.0,  8.50, 2.54, 7.62, 6.0, mats["dupont_blk"], parent=harness, bevel_mm=0.1)
        # PAM8403 1x2 power plug, 1x2 audio-in plug, 1x2 speaker-out plug
        add_box("ModPlug_PAM_Pwr",     6.27, -72.5,  2.00, 5.08, 5.0, 2.54, mats["dupont_blk"], parent=harness, bevel_mm=0.1)
        add_box("ModPlug_PAM_Aud",    16.77, -72.5,  2.00, 5.08, 5.0, 2.54, mats["dupont_blk"], parent=harness, bevel_mm=0.1)
        add_box("ModPlug_PAM_Out",    25.0,  -84.0,  2.00, 5.0, 5.08, 2.54, mats["dupont_blk"], parent=harness, bevel_mm=0.1)

        # 3. Deterministic, zero-clipping waypoints for EVERY wire W01..W40 around the 100x80 mm DIY Hub PCB
        wire_records: dict[str, dict[str, Any]] = {}

        for w in WIRING_TABLE:
            if w.hub_ref in HUB_CONNECTOR_MAP:
                p_start = hub_pin_world_xyz(w.hub_ref, w.hub_pin)
            else:
                p_start = mod_pins[(w.hub_ref, w.hub_pin)]
            p_end = mod_pins[(w.module_id, w.module_pin)]

            sx, sy, sz = p_start
            ex, ey, ez = p_end
            pts: list[tuple[float, float, float]] = [p_start]

            # Route cleanly by connector group so ribbons travel neatly together with ZERO clipping
            if w.hub_ref == "J1":  # Left Phoenix -> PSU
                pts += [(sx - 6.0, sy, sz), (sx - 20.0, (sy + ey) * 0.5, 11.5), (ex + 6.0, ey, ez)]
            elif w.hub_ref == "J2":  # Left Phoenix -> Pump
                pts += [(sx - 6.0, sy, sz), (sx - 20.0, (sy + ey) * 0.5, 13.5), (ex + 6.0, ey, ez)]
            elif w.hub_ref == "J14":  # Top edge -> Soil LM393
                dy_off = {"1": 0.0, "2": -2.2, "3": -4.4}[w.hub_pin]
                pts += [
                    (sx, sy, sz + 3.0),
                    (sx, 44.0, 20.5),
                    (ex, 52.0 + dy_off, 14.0),
                    (ex, ey - 5.5, ez),
                ]
            elif w.hub_ref == "LM393":  # LM393 -> Soil Probe
                pts += [(sx - 5.5, sy, sz), (0.5 * (sx + ex), 0.5 * (sy + ey), 5.0), (ex + 5.5, ey, ez)]
            elif w.hub_ref == "J4":  # Top edge -> Living LED
                pts += [
                    (sx, sy, sz + 3.0),
                    (sx, 45.0, 19.5),
                    (ex, 58.0, 11.0),
                    (ex, ey - 5.0, ez),
                ]
            elif w.hub_ref == "J3":  # Top edge -> SG90
                pts += [
                    (sx, sy, sz + 3.0),
                    (sx, 45.0, 19.5),
                    (ex, 58.0, 13.0),
                    (ex, ey - 5.5, ez),
                ]
            elif w.hub_ref == "J13":  # Top edge -> DHT11
                pts += [
                    (sx, sy, sz + 3.0),
                    (sx, 45.0, 19.5),
                    (ex, 54.0, 12.5),
                    (ex, ey - 5.5, ez),
                ]
            elif w.hub_ref == "J5":  # Right edge -> Bedroom LED
                pts += [
                    (sx, sy, sz + 3.0),
                    (56.0, sy, 19.5),
                    (72.0, ey, 11.0),
                    (ex - 5.0, ey, ez),
                ]
            elif w.hub_ref == "J15":  # Right edge -> KY-037
                pts += [
                    (sx, sy, sz + 3.0),
                    (56.0, sy, 20.0),
                    (74.0, ey, 12.5),
                    (ex - 5.5, ey, ez),
                ]
            elif w.hub_ref == "J7":  # Right edge -> Relay 1 coil/signal
                pts += [
                    (sx, sy, sz + 3.0),
                    (56.0, sy, 20.0),
                    (76.0, ey, 16.5),
                    (ex, ey, ez + 4.5),
                ]
            elif w.hub_ref == "J8":  # Left-inner J8 -> Perimeter route -> Relay 1 COM/NO screw terminals!
                # Zero clipping: rises to Z=23.5 over bare NW corner (clear of NodeMCU, J2, J14),
                # drops to Z=4.0 in the open North -> East -> South perimeter channel (under arched cables),
                # wraps around Relay 1 east end into COM/NO mouths!
                lane = 1.2 if w.hub_pin == "1" else -1.2
                pts += [
                    (sx, sy, 23.5),
                    (-38.0 + lane * 0.5, 25.0 + lane * 0.5, 23.5),
                    (-38.0 + lane * 0.5, 45.0 + lane, 18.0),
                    (-38.0 + lane * 0.5, 48.0 + lane, 4.0),
                    (67.5 + lane, 48.0 + lane, 4.0),
                    (67.5 + lane, -46.0 - lane, 4.0),
                    (146.5 + lane, -46.0 - lane, 4.0),
                    (146.5 + lane, ey, 8.5),
                    (ex + 3.5, ey, ez),
                ]
            elif w.hub_ref == "J9":  # Right edge -> South low perimeter channel -> Relay 2 coil/signal!
                lane = {"1": -1.6, "2": 0.0, "3": 1.6}[w.hub_pin]
                pts += [
                    (sx, sy, sz + 3.0),
                    (56.0, sy, 19.5),
                    (60.0 + lane, -44.0 + lane, 12.0),
                    (60.0 + lane, -54.0 + lane, 4.0),
                    (-75.0 + lane, -54.0 + lane, 4.0),
                    (-75.0 + lane, ey, 14.0),
                    (ex, ey, ez + 4.5),
                ]
            elif w.hub_ref == "J6":  # Bottom-right edge -> Buzzer
                lane = 1.2 if w.hub_pin == "1" else -1.2
                pts += [
                    (sx, sy, sz + 3.0),
                    (sx, -46.0 + lane, 19.0),
                    (74.0, ey, 11.0),
                    (ex - 5.0, ey, ez),
                ]
            elif w.hub_ref == "J10":  # Bottom edge -> Relay 2 COM/NO screw terminals
                lane = 1.3 if w.hub_pin == "1" else -1.3
                pts += [
                    (sx, sy, sz + 3.0),
                    (sx, -48.0, 18.0),
                    (-8.5 + lane, -62.0, 12.5),
                    (-8.5 + lane, ey, 9.0),
                    (ex + 3.5, ey, ez),
                ]
            elif w.hub_ref == "J11":  # Bottom edge -> PAM8403 Power
                pts += [
                    (sx, sy, sz + 3.0),
                    (sx, -46.0, 18.0),
                    (ex, -60.0, 10.5),
                    (ex, ey + 5.0, ez),
                ]
            elif w.hub_ref == "J12":  # Bottom edge -> PAM8403 Audio
                pts += [
                    (sx, sy, sz + 3.0),
                    (sx, -46.0, 18.0),
                    (ex, -60.0, 10.5),
                    (ex, ey + 5.0, ez),
                ]
            elif w.hub_ref == "PAM8403":  # PAM8403 -> Mini Speaker (BTL Yellow/Brown)
                pts += [(sx + 5.0, sy, sz), (0.5 * (sx + ex), 0.5 * (sy + ey), 5.5), (ex - 4.0, ey, ez)]
            else:
                raise RuntimeError(f"Unhandled wire group: {w.wire_id} ({w.hub_ref})")

            pts.append(p_end)
            smooth_pts = smooth_polyline(pts, fillet_mm=3.0, subdiv=4)
            wname = f"Wire_{w.wire_id}_{w.hub_ref}_{w.module_id}_{w.color}"
            add_wire_curve(wname, smooth_pts, WIRE_R, mats[f"wire_{w.color}"], parent=harness)

            wire_records[w.wire_id] = {
                "wire_id": w.wire_id,
                "object_name": wname,
                "hub_ref": w.hub_ref,
                "hub_pin": w.hub_pin,
                "module_id": w.module_id,
                "module_pin": w.module_pin,
                "color": w.color,
                "expected_start_mm": [round(v, 3) for v in p_start],
                "expected_end_mm": [round(v, 3) for v in p_end],
                "actual_start_mm": [round(v, 3) for v in smooth_pts[0]],
                "actual_end_mm": [round(v, 3) for v in smooth_pts[-1]],
                "polyline_mm": smooth_pts,
            }

        return wire_records

    def convert_curves_to_meshes() -> None:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in [o for o in bpy.data.objects if o.type == "CURVE"]:
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.convert(target="MESH")
            obj.select_set(False)

    def group_bbox_mm(root_obj, exclude_names: set[str] | None = None) -> dict[str, Any]:
        objs = [root_obj]
        q = [root_obj]
        while q:
            cur = q.pop()
            for ch in cur.children:
                objs.append(ch)
                q.append(ch)
        xs, ys, zs = [], [], []
        for o in objs:
            if o.type != "MESH":
                continue
            if exclude_names and o.name in exclude_names:
                continue
            for c in o.bound_box:
                w = o.matrix_world @ Vector(c)
                xs.append(w.x / MM)
                ys.append(w.y / MM)
                zs.append(w.z / MM)
        return {
            "min": [round(min(xs), 3), round(min(ys), 3), round(min(zs), 3)],
            "max": [round(max(xs), 3), round(max(ys), 3), round(max(zs), 3)],
            "size": [round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3), round(max(zs) - min(zs), 3)],
        }

    def run_verification_gate(
        module_objs: dict[str, Any],
        wire_records: dict[str, dict[str, Any]],
        gates_path: pathlib.Path,
    ) -> dict[str, Any]:
        bpy.context.view_layer.update()

        # 1. Measure all 16 contract modules
        module_checks: dict[str, Any] = {}
        dim_failures: list[str] = []
        module_bboxes: dict[str, dict[str, Any]] = {}

        for mid, spec in MODULE_DIMENSIONS_MM.items():
            obj = module_objs.get(mid)
            if obj is None:
                dim_failures.append(f"Missing module: {mid}")
                continue
            bb = group_bbox_mm(obj)
            module_bboxes[mid] = bb
            got_xy = sorted([bb["size"][0], bb["size"][1]], reverse=True)
            got_z = bb["size"][2]
            exp_l, exp_w, _exp_t = spec["dims_mm"]
            exp_h = float(spec["overall_h_mm"])
            exp_xy = sorted([float(exp_l), float(exp_w)], reverse=True)

            # SG90 flange tab extends X from 22.8 -> 32.2 mm per DIMENSIONS_AUDIT.md; verify body separately too!
            if mid == "sg90_servo":
                exp_xy = [32.2, 12.2]
            elif mid == "nodemcu":
                # Micro-USB protrudes ~1.17 mm beyond 48.26 mm PCB per DIMENSIONS_AUDIT.md (49.43 mm)
                exp_xy = [49.4, 25.4]

            err_l = abs(got_xy[0] - exp_xy[0])
            err_w = abs(got_xy[1] - exp_xy[1])
            err_h = abs(got_z - exp_h)
            ok = (err_l <= 1.0 and err_w <= 1.0 and err_h <= 1.0)
            if not ok:
                dim_failures.append(f"{mid}: got_xy={got_xy}, got_z={got_z:.2f}, exp_xy={exp_xy}, exp_h={exp_h}")
            module_checks[mid] = {
                "present": True,
                "bbox_min_mm": bb["min"],
                "bbox_max_mm": bb["max"],
                "measured_size_mm": bb["size"],
                "expected_footprint_mm": exp_xy,
                "expected_overall_h_mm": exp_h,
                "max_error_mm": round(max(err_l, err_w, err_h), 3),
                "pass": ok,
            }

        # 2. Module-vs-module pairwise AABB collision check (excluding hub_pcb <-> nodemcu socket mating)
        mod_ids = list(module_bboxes.keys())
        module_collisions: list[dict[str, Any]] = []
        for i in range(len(mod_ids)):
            for j in range(i + 1, len(mod_ids)):
                a, b = mod_ids[i], mod_ids[j]
                if {a, b} == {"hub_pcb", "nodemcu"}:
                    continue
                amn, amx = module_bboxes[a]["min"], module_bboxes[a]["max"]
                bmn, bmx = module_bboxes[b]["min"], module_bboxes[b]["max"]
                ov = [round(min(amx[k], bmx[k]) - max(amn[k], bmn[k]), 3) for k in range(3)]
                if all(v > 0.05 for v in ov):
                    module_collisions.append({"a": a, "b": b, "overlap_mm": ov})

        # 3. Wire count, color, endpoint accuracy (<= 0.5 mm), and dense 1.0 mm PER-MESH wire-vs-module collision check!
        # Collect every actual child MESH world AABB across hub_pcb, nodemcu, and all 14 off-board modules
        solid_boxes: list[tuple[str, str, list[float], list[float]]] = []
        for mid, root_obj in module_objs.items():
            q = [root_obj]
            while q:
                cur = q.pop()
                for ch in cur.children:
                    q.append(ch)
                if cur.type != "MESH":
                    continue
                mxs, mys, mzs = [], [], []
                for c in cur.bound_box:
                    w = cur.matrix_world @ Vector(c)
                    mxs.append(w.x / MM)
                    mys.append(w.y / MM)
                    mzs.append(w.z / MM)
                solid_boxes.append((
                    mid,
                    cur.name,
                    [min(mxs), min(mys), min(mzs)],
                    [max(mxs), max(mys), max(mzs)],
                ))

        wire_endpoint_checks: list[dict[str, Any]] = []
        endpoint_failures: list[str] = []
        wire_clip_violations: list[dict[str, Any]] = []

        def dist3(a: list[float], b: list[float]) -> float:
            return math.sqrt(sum((a[k] - b[k]) ** 2 for k in range(3)))

        for w in WIRING_TABLE:
            rec = wire_records[w.wire_id]
            d_start = dist3(rec["actual_start_mm"], rec["expected_start_mm"])
            d_end = dist3(rec["actual_end_mm"], rec["expected_end_mm"])
            ep_ok = (d_start <= 0.5 and d_end <= 0.5)
            if not ep_ok:
                endpoint_failures.append(f"{w.wire_id}: start_err={d_start:.3f}, end_err={d_end:.3f}")
            wire_endpoint_checks.append({
                "wire_id": w.wire_id,
                "hub": f"{w.hub_ref}.{w.hub_pin}",
                "module": f"{w.module_id}.{w.module_pin}",
                "color": w.color,
                "start_err_mm": round(d_start, 4),
                "end_err_mm": round(d_end, 4),
                "pass": ep_ok,
            })

            # Sample polyline every 1.0 mm along arc length
            poly = rec["polyline_mm"]
            cum_len = [0.0]
            for idx in range(1, len(poly)):
                cum_len.append(cum_len[-1] + dist3(poly[idx - 1], poly[idx]))
            total_len = cum_len[-1]
            n_steps = max(10, int(total_len / 1.0))
            for step in range(1, n_steps):
                s_dist = (step / n_steps) * total_len
                seg_i = 0
                while seg_i + 1 < len(cum_len) and cum_len[seg_i + 1] < s_dist:
                    seg_i += 1
                seg_l = max(1e-6, cum_len[seg_i + 1] - cum_len[seg_i])
                t = (s_dist - cum_len[seg_i]) / seg_l
                pt = [poly[seg_i][k] * (1.0 - t) + poly[seg_i + 1][k] * t for k in range(3)]

                for mod_id, mesh_name, bmn, bmx in solid_boxes:
                    # Allow the final 3.5 mm of wire right where it enters its OWN connected terminal/pin
                    if mod_id == w.module_id and (total_len - s_dist) <= 3.5:
                        continue
                    if mod_id == "hub_pcb" and w.hub_ref in HUB_CONNECTOR_MAP and s_dist <= 3.5:
                        continue
                    if (w.hub_ref == "PAM8403" and mod_id == "pam8403_amp" and s_dist <= 3.5):
                        continue
                    if (w.hub_ref == "LM393" and mod_id == "soil_lm393" and s_dist <= 3.5):
                        continue
                    eps = 0.15
                    if (
                        bmn[0] + eps < pt[0] < bmx[0] - eps
                        and bmn[1] + eps < pt[1] < bmx[1] - eps
                        and bmn[2] + eps < pt[2] < bmx[2] - eps
                    ):
                        wire_clip_violations.append({
                            "wire_id": w.wire_id,
                            "clipped_module": mod_id,
                            "clipped_mesh": mesh_name,
                            "point_mm": [round(v, 2) for v in pt],
                            "arc_mm": round(s_dist, 2),
                        })
                        break

        # Verify all 15 hub connectors have wires
        connected_hub_refs = sorted({w.hub_ref for w in WIRING_TABLE if w.hub_ref in HUB_CONNECTOR_MAP})
        all_15_connectors = len(connected_hub_refs) == 15

        report = {
            "schema_version": "1.0",
            "source_of_truth": "hardware/wiring_contract.py",
            "scale_contract": "1:1 physical millimeters (1 mm = 0.001 m)",
            "summary": {
                "total_modules_expected": len(MODULE_DIMENSIONS_MM),
                "total_modules_present": len(module_checks),
                "offboard_modules_count": len(MODULE_DIMENSIONS_MM) - 2,
                "hub_connectors_connected": len(connected_hub_refs),
                "all_15_hub_connectors_wired": all_15_connectors,
                "all_dimensions_within_1mm": len(dim_failures) == 0,
                "dimension_failures": dim_failures,
                "module_collisions_count": len(module_collisions),
                "total_wires_expected": len(WIRING_TABLE),
                "total_wires_present": len(wire_records),
                "all_wire_endpoints_within_0_5mm": len(endpoint_failures) == 0,
                "endpoint_failures": endpoint_failures,
                "wire_clipping_violations_count": len(wire_clip_violations),
                "overall_pass": (
                    len(module_checks) == len(MODULE_DIMENSIONS_MM)
                    and all_15_connectors
                    and len(dim_failures) == 0
                    and len(module_collisions) == 0
                    and len(wire_records) == len(WIRING_TABLE)
                    and len(endpoint_failures) == 0
                    and len(wire_clip_violations) == 0
                ),
            },
            "modules": module_checks,
            "module_collisions": module_collisions,
            "wire_endpoints": wire_endpoint_checks,
            "wire_clipping_violations": wire_clip_violations[:25],
        }
        gates_path.parent.mkdir(parents=True, exist_ok=True)
        gates_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[VERIFY] Wrote {gates_path} -> overall_pass={report['summary']['overall_pass']}")
        if not report["summary"]["overall_pass"]:
            print("[VERIFY FAIL DETAILS]", json.dumps(report["summary"], indent=2))
            if wire_clip_violations:
                print("[FIRST CLIP VIOLATIONS]", wire_clip_violations[:5])
        return report

    def setup_lighting() -> None:
        scene = bpy.context.scene
        world = scene.world
        world.use_nodes = True
        bg = world.node_tree.nodes.get("Background")
        if bg:
            # Clean studio backdrop with controlled ambient fill so shadows and colors stay deep & crisp
            bg.inputs["Color"].default_value = (0.76, 0.81, 0.87, 1.0)
            bg.inputs["Strength"].default_value = 0.20

        def add_area_light(name: str, pos_mm: tuple[float, float, float], tgt_mm: tuple[float, float, float],
                           energy_w: float, size_mm: float, color=(1.0, 1.0, 1.0)) -> None:
            ld = bpy.data.lights.new(name=name, type="AREA")
            ld.energy = energy_w
            ld.color = color
            ld.size = size_mm * MM
            lo = bpy.data.objects.new(name=name, object_data=ld)
            bpy.context.collection.objects.link(lo)
            lo.location = vmm(*pos_mm)
            direction = vmm(*tgt_mm) - lo.location
            lo.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

        # Properly calibrated 1:1 meter softbox studio lighting (~0.35 m subject distance)
        add_area_light("KeySoftbox",  (240.0, -240.0, 340.0), (0.0, 0.0, 10.0), 4.2, 240.0, (1.00, 0.98, 0.94))
        add_area_light("FillSoftbox", (-280.0, -140.0, 260.0), (0.0, 0.0, 10.0), 2.0, 300.0, (0.88, 0.94, 1.00))
        add_area_light("RimSoftbox",  (-40.0,  290.0, 250.0), (0.0, 0.0, 10.0), 1.9, 260.0, (0.94, 0.97, 1.00))
        add_area_light("TopDiffuser", (0.0,     0.0,  440.0), (0.0, 0.0,  0.0), 1.3, 360.0, (1.00, 1.00, 1.00))

    def create_cam(name: str, eye_mm: tuple[float, float, float], tgt_mm: tuple[float, float, float],
                   ortho: bool = False, lens_mm: float = 52.0, ortho_scale_mm: float = 410.0):
        cd = bpy.data.cameras.new(name)
        cd.clip_start = 0.005
        cd.clip_end = 10.0
        if ortho:
            cd.type = "ORTHO"
            cd.ortho_scale = ortho_scale_mm * MM
        else:
            cd.type = "PERSP"
            cd.lens = lens_mm
        cam = bpy.data.objects.new(name, cd)
        bpy.context.collection.objects.link(cam)
        cam.location = vmm(*eye_mm)
        direction = vmm(*tgt_mm) - cam.location
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        return cam

    def project_pt(scene, cam, pt_mm: tuple[float, float, float]) -> list[float]:
        co_ndc = world_to_camera_view(scene, cam, vmm(*pt_mm))
        px = co_ndc.x * RENDER_W
        py = (1.0 - co_ndc.y) * RENDER_H
        return [round(px, 1), round(py, 1)]

    # --- Execute full Blender pipeline ---
    clear_scene()
    mats = build_materials()
    build_workbench(mats)
    hub_obj, mcu_obj = build_hub_pcb_and_nodemcu(mats)
    offboard_objs, mod_pins = build_offboard_modules(mats)
    all_module_objs = {"hub_pcb": hub_obj, "nodemcu": mcu_obj, **offboard_objs}
    wire_records = build_all_40_wires_and_dupont_housings(mats, mod_pins)
    convert_curves_to_meshes()

    # Run programmatic gate BEFORE exporting & rendering
    gates_json = out_dir / "gates" / "assembly_3d_verify.json"
    report = run_verification_gate(all_module_objs, wire_records, gates_json)

    setup_lighting()

    # Cameras:
    # 1. Isometric 3/4 view (front-south slightly right, crisp framing with room for perimeter callouts)
    cam_iso = create_cam("Cam_ISO_34", (30.0, -325.0, 270.0), (-2.0, -4.0, 6.0), ortho=False, lens_mm=46.0)
    # 2. Clean top-down orthographic view (exact 2D wiring clarity, crisp scale with room for callouts & legend)
    cam_top = create_cam("Cam_Top_Ortho", (-2.0, -3.0, 460.0), (-2.0, -3.0, 0.0), ortho=True, ortho_scale_mm=396.0)
    bpy.context.scene.camera = cam_iso

    # Save native .blend
    OUT_BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))
    print(f"[BLEND] Saved {OUT_BLEND} ({OUT_BLEND.stat().st_size} bytes)")

    # Export clean GLB (< 5 MB, exclude lights & cameras)
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

    # Configure EEVEE high-resolution studio render
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = RENDER_W
    scene.render.resolution_y = RENDER_H
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 32
    vt_items = [i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items]
    scene.view_settings.view_transform = "AgX" if "AgX" in vt_items else "Filmic"
    look_items = [i.identifier for i in scene.view_settings.bl_rna.properties["look"].enum_items]
    if "AgX - Medium High Contrast" in look_items:
        scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.10

    # Export exact 2D projected pixel anchors for Pillow annotation pass
    bpy.context.view_layer.update()
    mod_anchor_pts_3d: dict[str, tuple[float, float, float]] = {}
    for mid, mdata in report["modules"].items():
        mn, mx = mdata["bbox_min_mm"], mdata["bbox_max_mm"]
        mod_anchor_pts_3d[mid] = (0.5 * (mn[0] + mx[0]), 0.5 * (mn[1] + mx[1]), mx[2])
    # Point Hub PCB anchor to its clearly visible emerald-green bottom-left corner (not hidden under NodeMCU!)
    mod_anchor_pts_3d["hub_pcb"] = (-27.0, -20.5, PCB_Z_BOT + PCB_FR4_THICK + 0.5)
    # Point NodeMCU anchor cleanly to its ESP-12E silver RF shield top
    mod_anchor_pts_3d["nodemcu"] = (0.0, 7.0, U12_SOCKET_TOP_Z + 7.2)

    conn_anchor_pts_3d: dict[str, tuple[float, float, float]] = {}
    for conn in HUB_CONNECTORS:
        xs = [pcb_rel_to_world_xy(p[1], p[2])[0] for p in conn.pins]
        ys = [pcb_rel_to_world_xy(p[1], p[2])[1] for p in conn.pins]
        z_pt = 21.4 if conn.kind == "screw_508" else 19.5
        conn_anchor_pts_3d[conn.ref] = (sum(xs) / len(xs), sum(ys) / len(ys), z_pt)

    anchors_out: dict[str, Any] = {"width": RENDER_W, "height": RENDER_H, "iso": {}, "top": {}}
    ss_dir = out_dir / "screenshots"
    ss_dir.mkdir(parents=True, exist_ok=True)

    for key, cam, fname in [
        ("iso", cam_iso, "_raw_51_pcb_modules_wired_3d_iso.png"),
        ("top", cam_top, "_raw_52_pcb_modules_wired_top.png"),
    ]:
        scene.camera = cam
        bpy.context.view_layer.update()
        anchors_out[key] = {
            "modules": {mid: project_pt(scene, cam, pt) for mid, pt in mod_anchor_pts_3d.items()},
            "connectors": {ref: project_pt(scene, cam, pt) for ref, pt in conn_anchor_pts_3d.items()},
        }
        raw_png = ss_dir / fname
        scene.render.filepath = str(raw_png)
        bpy.ops.render.render(write_still=True)
        print(f"[RENDER] Saved {raw_png} ({raw_png.stat().st_size} bytes)")

    anchors_file = ss_dir / "_render_anchors.json"
    anchors_file.write_text(json.dumps(anchors_out, indent=2), encoding="utf-8")
    print(f"[ANCHORS] Saved {anchors_file}")


# ==============================================================================
# PART 2: TRIMESH GLB AUDIT & PILLOW PUBLICATION-GRADE CALLOUT ANNOTATOR
# ==============================================================================
def run_annotate_and_glb_verify(out_dir: pathlib.Path) -> None:
    import trimesh
    from PIL import Image, ImageDraw, ImageFont

    # 1. Verify exported GLB with trimesh and update assembly_3d_verify.json
    assert OUT_GLB.exists(), f"Missing GLB: {OUT_GLB}"
    glb_bytes = OUT_GLB.stat().st_size
    glb_mb = round(glb_bytes / (1024 * 1024), 3)
    scene = trimesh.load(str(OUT_GLB))
    nodes = set(scene.graph.nodes)

    missing_mods = [m for m in MODULE_DIMENSIONS_MM if m not in nodes]
    wire_nodes = [n for n in nodes if n.startswith("Wire_W")]
    forbidden_tokens = ("fan", "ac", "vs1838", "ir", "breadboard")
    forbidden_found = []
    for n in nodes:
        toks = [t for t in re.split(r"[^a-z0-9]+", n.lower()) if t]
        if any(t in forbidden_tokens or t.startswith("vs1838") for t in toks):
            forbidden_found.append(n)

    gates_path = out_dir / "gates" / "assembly_3d_verify.json"
    report = json.loads(gates_path.read_text(encoding="utf-8"))
    report["glb_audit"] = {
        "glb_path": str(OUT_GLB),
        "glb_bytes": glb_bytes,
        "glb_mb": glb_mb,
        "size_under_5mb": glb_mb < 5.0,
        "total_nodes": len(nodes),
        "wire_nodes_found": len(wire_nodes),
        "missing_module_nodes": missing_mods,
        "forbidden_nodes": forbidden_found,
        "pass": (glb_mb < 5.0 and len(missing_mods) == 0 and len(wire_nodes) == len(WIRING_TABLE) and len(forbidden_found) == 0),
    }
    report["summary"]["glb_mb"] = glb_mb
    report["summary"]["glb_pass"] = report["glb_audit"]["pass"]
    report["summary"]["overall_pass"] = bool(report["summary"]["overall_pass"] and report["glb_audit"]["pass"])
    gates_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[GLB AUDIT] {glb_mb} MB | nodes={len(nodes)} | wires={len(wire_nodes)} | pass={report['glb_audit']['pass']}")

    # 2. Load crisp Windows TrueType fonts
    def load_font(size: int, bold: bool = False):
        candidates = (
            ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"]
            if bold
            else ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"]
        )
        for path in candidates:
            if pathlib.Path(path).exists():
                return ImageFont.truetype(path, size)
        return ImageFont.load_default()

    font_title = load_font(28, bold=True)
    font_sub = load_font(17, bold=False)
    font_card_t = load_font(17, bold=True)
    font_card_s = load_font(14, bold=False)
    font_j = load_font(14, bold=True)
    font_leg = load_font(14, bold=True)
    font_leg_r = load_font(13, bold=False)

    ss_dir = out_dir / "screenshots"
    anchors = json.loads((ss_dir / "_render_anchors.json").read_text(encoding="utf-8"))

    # Concise, crystal-clear callout copy for all 16 hardware blocks
    MODULE_CARDS: dict[str, tuple[str, str]] = {
        "soil_probe":     ("YL-69 Soil Fork Probe",         "60×20×1.6 mm  |  LM393 (Yel/Org)"),
        "soil_lm393":     ("Soil LM393 Comparator",         "32×14×12.1 mm  |  J14 (A0, 3.3V)"),
        "dht11_sensor":   ("DHT11 Temp/Humidity",           "28×14×7.1 mm  |  J13 (D2, 3.3V)"),
        "led_living":     ("Living Room 5mm LED",           "Ø5.8×8.6 mm  |  J4 (D0, R1 220Ω)"),
        "led_bedroom":    ("Bedroom 5mm LED",               "Ø5.8×8.6 mm  |  J5 (D4 Active-LOW)"),
        "sg90_servo":     ("SG90 Micro Servo (Door)",       "22.8×12.2×22.5 mm  |  J3 (D1, 5V)"),
        "ky037_sound":    ("KY-037/038 Sound Sensor",       "35×15×13.1 mm  |  J15 (D5, 3.3V)"),
        "relay1_pump":    ("Relay 1 (Blue 5V 1-ch)",        "50×26×18.5 mm  |  J7 (D6) & J8 (SW)"),
        "buzzer_alarm":   ("Active 5V Buzzer (TMB12A05)",   "Ø12×9.5 mm  |  J6 (D8 via Q1 S8050)"),
        "speaker_mini":   ("Mini Speaker 28mm (8Ω 0.5W)",   "Ø28×5.2 mm  |  PAM8403 BTL (Yel/Brn)"),
        "pam8403_amp":    ("PAM8403 Audio Amplifier",       "21×18×3.1 mm  |  J11 (5V) & J12 (D3)"),
        "relay2_speaker": ("Relay 2 (Red Opto 5V, Jmp=H)",  "50×26×18.5 mm  |  J9 (D7) & J10 (SW)"),
        "psu_5v":         ("5V 2A External PSU Input",      "34×22×16 mm  |  J1 (+5V / GND)"),
        "pump_unit":      ("Mini Submersible Pump (3-6V)",  "45×24×33 mm  |  J2 (Switched 5V)"),
        "hub_pcb":        ("1-Layer DIY Central Hub PCB",   "100×80×1.6 mm FR4  |  51 FPs, C1–C9 & D1–D2 On-Board"),
        "nodemcu":        ("ESP8266 NodeMCU v2 Amica",      "48.26×25.4 mm  |  U1/U2 Sockets (No Breadboard)"),
    }

    def draw_header_and_legend(img: Image.Image, title: str, subtitle: str) -> None:
        draw = ImageDraw.Draw(img, "RGBA")
        W, H = img.size

        # Top title banner
        draw.rectangle([(0, 0), (W, 82)], fill=(15, 23, 42, 240))
        draw.rectangle([(0, 82), (W, 86)], fill=(37, 99, 235, 255))
        draw.text((28, 13), title, fill=(248, 250, 252, 255), font=font_title)
        draw.text((28, 50), subtitle, fill=(148, 163, 184, 255), font=font_sub)

        # Bottom wire color legend bar (2 rows of 5 colors -> super legible!)
        leg_h = 92
        draw.rectangle([(0, H - leg_h), (W, H)], fill=(15, 23, 42, 240))
        draw.rectangle([(0, H - leg_h - 3), (W, H - leg_h)], fill=(51, 65, 85, 255))
        draw.text((24, H - leg_h + 8), "WIRE COLOR LEGEND (SSOT: hardware/wiring_contract.py)", fill=(148, 163, 184, 255), font=font_leg)

        short_roles = {
            "Red":    "+5V / +3V3 / Switched 5V",
            "Black":  "Ground (GND)",
            "Orange": "SG90 D1 / Buzz D8 / Rly2 NO / Prb B",
            "Yellow": "LED LR D0 / KY037 D5 / Rly1 NO / Spk+",
            "Green":  "Relay1 IN D6 / Soil AO A0",
            "Blue":   "DHT11 DATA D2",
            "Cyan":   "Relay2 IN D7",
            "Purple": "LED BR Anode (+3V3 via R2)",
            "White":  "LED BR Cathode D4 / Audio D3",
            "Brown":  "Speaker BTL- (NOT GND)",
        }
        items = list(WIRE_COLORS.items())
        col_w = (W - 48) // 5
        for idx, (cname, cinfo) in enumerate(items):
            row = idx // 5
            col = idx % 5
            x = 24 + col * col_w
            y = H - leg_h + 32 + row * 28
            hexc = str(cinfo["hex"])
            rgb = tuple(int(hexc[i : i + 2], 16) for i in (1, 3, 5))
            draw.rounded_rectangle([(x, y + 2), (x + 22, y + 18)], radius=4, fill=(*rgb, 255), outline=(226, 232, 240, 220), width=1)
            draw.text((x + 30, y), f"{cname}:", fill=(248, 250, 252, 255), font=font_leg)
            tw = draw.textlength(f"{cname}: ", font=font_leg)
            draw.text((x + 30 + tw, y + 1), short_roles[cname], fill=(203, 213, 225, 255), font=font_leg_r)

    def draw_callout_card(
        draw: ImageDraw.ImageDraw,
        box_xy: tuple[int, int],
        anchor_xy: tuple[float, float],
        title: str,
        sub: str,
        accent_rgb: tuple[int, int, int] = (37, 99, 235),
    ) -> None:
        pad_x, pad_y = 12, 8
        tw1 = draw.textlength(title, font=font_card_t)
        tw2 = draw.textlength(sub, font=font_card_s)
        cw = int(max(tw1, tw2)) + pad_x * 2 + 6
        ch = 48
        bx, by = box_xy
        x0, y0, x1, y1 = bx, by, bx + cw, by + ch

        # Closest attachment point on card border toward anchor
        cx = max(x0, min(x1, anchor_xy[0]))
        cy = max(y0, min(y1, anchor_xy[1]))
        # Clean leader line with subtle halo
        draw.line([(cx, cy), (anchor_xy[0], anchor_xy[1])], fill=(255, 255, 255, 210), width=5)
        draw.line([(cx, cy), (anchor_xy[0], anchor_xy[1])], fill=(*accent_rgb, 245), width=2)
        ax, ay = anchor_xy
        draw.ellipse([(ax - 5, ay - 5), (ax + 5, ay + 5)], fill=(*accent_rgb, 255), outline=(255, 255, 255, 255), width=2)

        # Card body
        draw.rounded_rectangle([(x0 + 2, y0 + 3), (x1 + 2, y1 + 3)], radius=7, fill=(15, 23, 42, 70))
        draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=7, fill=(255, 255, 255, 238), outline=(148, 163, 184, 255), width=1)
        draw.rounded_rectangle([(x0, y0), (x0 + 5, y1)], radius=3, fill=(*accent_rgb, 255))
        draw.text((x0 + pad_x + 2, y0 + 6), title, fill=(15, 23, 42, 255), font=font_card_t)
        draw.text((x0 + pad_x + 2, y0 + 26), sub, fill=(71, 85, 105, 255), font=font_card_s)

    def annotate_iso() -> None:
        img = Image.open(ss_dir / "_raw_51_pcb_modules_wired_3d_iso.png").convert("RGBA")
        draw = ImageDraw.Draw(img, "RGBA")
        m_pts = anchors["iso"]["modules"]

        # Curated perimeter card positions guaranteeing 100% zero overlap & unobstructed central PCB
        iso_layout: dict[str, tuple[int, int, tuple[int, int, int]]] = {
            # Top row
            "soil_probe":     (36,   106, (22, 163, 74)),
            "soil_lm393":     (415,  106, (22, 163, 74)),
            "dht11_sensor":   (780,  106, (37, 99, 235)),
            "led_living":     (1135, 106, (202, 138, 4)),
            "led_bedroom":    (1475, 106, (147, 51, 234)),
            "sg90_servo":     (1835, 106, (234, 88, 12)),
            # Left column
            "nodemcu":        (36,   215, (30, 41, 59)),
            "pump_unit":      (36,   455, (220, 38, 38)),
            "psu_5v":         (36,   765, (220, 38, 38)),
            "hub_pcb":        (36,   985, (16, 124, 65)),
            # Right column
            "ky037_sound":    (1835, 415, (202, 138, 4)),
            "relay1_pump":    (1835, 675, (22, 163, 74)),
            "buzzer_alarm":   (1835, 955, (234, 88, 12)),
            # Bottom row
            "relay2_speaker": (220,  1315, (8, 145, 178)),
            "pam8403_amp":    (860,  1315, (16, 124, 65)),
            "speaker_mini":   (1480, 1315, (120, 53, 15)),
        }
        for mid, (bx, by, accent) in iso_layout.items():
            title, sub = MODULE_CARDS[mid]
            ax, ay = m_pts[mid]
            draw_callout_card(draw, (bx, by), (ax, ay), title, sub, accent)

        draw_header_and_legend(
            img,
            "SMART HOME VOICE AI — 1-LAYER DIY CENTRAL HUB PCB & ALL PLUG-IN MODULES (3D ISOMETRIC, PCB-DIRECT)",
            "Exact 1:1 mm KiCad Hub PCB (100×80 mm, 51 FPs: C1–C9 & D1–D2 On-Board, Zero Breadboard) + NodeMCU v2 Amica + 14 Modules + 40 Wires",
        )
        out_path = ss_dir / "51_pcb_modules_wired_3d_iso.png"
        img.convert("RGB").save(out_path, optimize=True)
        print(f"[ANNOTATE] Saved {out_path} ({out_path.stat().st_size} bytes)")

    def annotate_top() -> None:
        img = Image.open(ss_dir / "_raw_52_pcb_modules_wired_top.png").convert("RGBA")
        draw = ImageDraw.Draw(img, "RGBA")
        m_pts = anchors["top"]["modules"]
        c_pts = anchors["top"]["connectors"]

        # Curated perimeter card positions for top orthographic view (zero overlap with modules or wires!)
        top_layout: dict[str, tuple[int, int, tuple[int, int, int]]] = {
            # Top row
            "soil_probe":     (36,   102, (22, 163, 74)),
            "soil_lm393":     (405,  102, (22, 163, 74)),
            "dht11_sensor":   (770,  102, (37, 99, 235)),
            "led_living":     (1125, 102, (202, 138, 4)),
            "led_bedroom":    (1475, 102, (147, 51, 234)),
            "sg90_servo":     (1835, 102, (234, 88, 12)),
            # Left column
            "pump_unit":      (36,   520, (220, 38, 38)),
            "psu_5v":         (36,   830, (220, 38, 38)),
            "nodemcu":        (36,   360, (30, 41, 59)),
            "hub_pcb":        (36,   1060, (16, 124, 65)),
            # Right column (clear of Relay 1 COM/NO perimeter loop)
            "ky037_sound":    (1835, 430, (202, 138, 4)),
            "relay1_pump":    (1865, 625, (22, 163, 74)),
            "buzzer_alarm":   (1835, 1020, (234, 88, 12)),
            # Bottom row
            "relay2_speaker": (220,  1320, (8, 145, 178)),
            "pam8403_amp":    (860,  1320, (16, 124, 65)),
            "speaker_mini":   (1480, 1320, (120, 53, 15)),
        }
        for mid, (bx, by, accent) in top_layout.items():
            title, sub = MODULE_CARDS[mid]
            ax, ay = m_pts[mid]
            draw_callout_card(draw, (bx, by), (ax, ay), title, sub, accent)

        # Crisp miniature J1..J15 header pill badges with clean radial offsets so ZERO badges overlap!
        j_offsets: dict[str, tuple[int, int]] = {
            "J1":  (-48,  20),
            "J2":  (-48, -24),
            "J8":  ( 28, -20),
            "J14": (-34, -36),
            "J13": (  0, -36),
            "J4":  (  0, -36),
            "J5":  ( 26, -36),
            "J3":  ( 42, -16),
            "J15": ( 42,  -4),
            "J7":  ( 42,   6),
            "J6":  ( 42,  22),
            "J9":  (-34,  34),
            "J10": (  0,  34),
            "J11": (  0,  34),
            "J12": ( 30,  34),
        }
        for conn in HUB_CONNECTORS:
            ax, ay = c_pts[conn.ref]
            ox, oy = j_offsets[conn.ref]
            bx, by = ax + ox, ay + oy
            label = conn.ref
            tw = draw.textlength(label, font=font_j)
            pw, ph = int(tw) + 12, 20
            x0, y0 = int(bx - pw / 2), int(by - ph / 2)
            draw.line([(bx, by), (ax, ay)], fill=(255, 255, 255, 220), width=3)
            draw.line([(bx, by), (ax, ay)], fill=(15, 23, 42, 240), width=1)
            draw.ellipse([(ax - 3, ay - 3), (ax + 3, ay + 3)], fill=(250, 204, 21, 255), outline=(15, 23, 42, 255), width=1)
            draw.rounded_rectangle([(x0, y0), (x0 + pw, y0 + ph)], radius=5, fill=(15, 23, 42, 235), outline=(250, 204, 21, 255), width=1)
            draw.text((x0 + 6, y0 + 2), label, fill=(254, 240, 138, 255), font=font_j)

        draw_header_and_legend(
            img,
            "SMART HOME VOICE AI — TOP ORTHOGRAPHIC WIRING MAP (PCB-DIRECT, ZERO BREADBOARD)",
            "Exact 1:1 mm Top Projection: Hub PCB (C1–C9 & D1–D2 On-Board, J1..J15) -> All 14 Plug-In Modules & 40 Color-Coded Wires",
        )
        out_path = ss_dir / "52_pcb_modules_wired_top.png"
        img.convert("RGB").save(out_path, optimize=True)
        print(f"[ANNOTATE] Saved {out_path} ({out_path.stat().st_size} bytes)")

    annotate_iso()
    annotate_top()


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    out_dir = REPO_ROOT / "hardware" / "blender" / "out"
    if "--out-dir" in args:
        idx = args.index("--out-dir")
        if idx + 1 < len(args):
            out_dir = pathlib.Path(args[idx + 1])

    if "--annotate" in args:
        run_annotate_and_glb_verify(out_dir)
    else:
        run_blender_pipeline(out_dir)


if __name__ == "__main__":
    main()
