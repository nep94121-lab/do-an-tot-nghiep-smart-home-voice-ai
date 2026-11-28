"""Shared FreeCAD 1.1 world-space 3D assembly transformer for 3D-Print Set v2.

Transforms every print-oriented STEP solid (`parts/*.step`) into its exact assembled
world 3D house position so both `verify_assembly_fit.py` (Gate G2 collision + fit audit)
and `render_previews_v2.py` (assembled & exploded 3D renders) use one exact SSOT transform.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PRINT3D_ROOT = SCRIPT_DIR.parent
MICA_DIR = PRINT3D_ROOT.parent / "mica"

for _p in (str(SCRIPT_DIR), str(MICA_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import FreeCAD
import Part

import kicad_pcb_ssot as pcb_ssot
import mica_design as md
import print_domain as pd_mod

PARTS_DIR = PRINT3D_ROOT / "parts"
META_DIR = PRINT3D_ROOT / "build_meta"


def load_all_metas() -> dict[str, dict[str, Any]]:
    metas: dict[str, dict[str, Any]] = {}
    for p in sorted(META_DIR.glob("*.json")):
        if p.stem in ("fit_table", "assembly_report", "plates_manifest", "slice_report", "user_like_test_report", "strength_report"):
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if "part_id" in d and "kind" in d:
            metas[d["part_id"]] = d
    return metas


def place_panel_in_world(shape: Any, meta: dict[str, Any], origin_override: list[float] | None = None) -> Any:
    """Transform a print-ready panel STEP shape back into exact 3D assembled house world coordinates."""
    s = shape.copy()
    lmin = meta["local_bbox_min"]
    lmax = meta["local_bbox_max"]
    su = float(meta["shift_u"])
    sv = float(meta["shift_v"])

    if meta.get("print_flipped_x180", False):
        # Undo normalize-to-zero and 180-deg X print flip (used by P07_SERVO_SHELF with underside lugs)
        s.translate(FreeCAD.Vector(float(lmin[0]), -float(lmax[1]), -float(lmax[2])))
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 180.0)
        s.translate(FreeCAD.Vector(-su, -sv, 0.0))
    else:
        s.translate(FreeCAD.Vector(lmin[0] - su, lmin[1] - sv, lmin[2]))

    plane = meta["plane"]
    ox, oy, oz = origin_override if origin_override is not None else meta["origin_xyz"]

    if plane == "XY":
        s.translate(FreeCAD.Vector(ox, oy, oz))
    elif plane == "XZ":
        T = float(meta["print_bbox_mm"][2])
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
        s.translate(FreeCAD.Vector(ox, oy + T, oz))
    elif plane == "YZ":
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 90.0)
        s.translate(FreeCAD.Vector(ox, oy, oz))
    else:
        raise ValueError(f"Unknown plane {plane}")
    return s


def place_support_in_world(shape: Any, meta: dict[str, Any], pl: dict[str, Any]) -> list[tuple[str, Any]]:
    """Transform one print-ready support placement into world 3D space (returns list of (sub_label, shape))."""
    cat = meta["category"]
    pid = meta["part_id"]
    bx, by, bz = meta["print_bbox_mm"]
    pr = meta.get("params", {})
    x, y, z = float(pl["x"]), float(pl["y"]), float(pl["z"])
    rot_z = float(pl.get("rot_z", 0.0))

    if cat == "corner_clip":
        s = shape.copy()
        # 180 deg around diagonal (1,1,0): (x,y,z)->(y,x,-z); shift Z by +bz so cap is on top
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 1, 0), 180.0)
        s.translate(FreeCAD.Vector(0.0, 0.0, bz))
        if abs(rot_z) > 1e-6:
            s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), rot_z)
        s.translate(FreeCAD.Vector(x, y, z))
        return [(pid, s)]

    if cat == "t_clip":
        s = shape.copy()
        wt = float(pr["wall_t"])
        sw = float(pr["slot_w"])
        s.translate(FreeCAD.Vector(-bx / 2.0, -(wt + sw / 2.0), 0.0))
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 180.0)
        s.translate(FreeCAD.Vector(0.0, 0.0, bz))
        if abs(rot_z) > 1e-6:
            s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), rot_z)
        s.translate(FreeCAD.Vector(x, y, z))
        return [(pid, s)]

    if cat == "seam_clip":
        s = shape.copy()
        s.rotate(FreeCAD.Vector(0, by / 2.0, bz / 2.0), FreeCAD.Vector(1, 0, 0), 180.0)
        if abs(rot_z) > 1e-6:
            s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), rot_z)
        s.translate(FreeCAD.Vector(x, y, z))
        return [(pid, s)]

    if cat == "foot_clip":
        s = shape.copy()
        if abs(rot_z) > 1e-6:
            s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), rot_z)
        s.translate(FreeCAD.Vector(x, y, z))
        return [(pid, s)]

    if cat == "tenon_riser":
        s = shape.copy()
        tc = meta.get("tenon_center_print", [bx / 2.0, by / 2.0, 1.5])
        s.translate(FreeCAD.Vector(-tc[0], -tc[1], -tc[2]))
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
        if abs(rot_z) > 1e-6:
            s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), rot_z)
        # World: body is Z=[0..6], tenons Z=[-3..0] and [6..9] -> center at Z = z + 3.0
        s.translate(FreeCAD.Vector(x, y, z + 3.0))
        return [(pid, s)]

    if cat == "tenon_peg":
        s = shape.copy()
        s.translate(FreeCAD.Vector(-bx / 2.0, 0.0, -bz / 2.0))
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
        if abs(rot_z) > 1e-6:
            s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), rot_z)
        s.translate(FreeCAD.Vector(x, y, z))
        return [(pid, s)]

    if cat in ("pcb_carrier", "relay_caddy", "pam_tray", "water_liner"):
        s = shape.copy()
        s.translate(FreeCAD.Vector(-bx / 2.0, -by / 2.0, 0.0))
        if abs(rot_z) > 1e-6:
            s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), rot_z)
        s.translate(FreeCAD.Vector(x, y, z))
        return [(pid, s)]

    if cat == "speaker_retainer":
        s = shape.copy()
        bh = float(pr["bridge_h"])  # 9.0
        s.translate(FreeCAD.Vector(-bx / 2.0, -by / 2.0, -bh))
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
        s.translate(FreeCAD.Vector(x, y, z))
        return [(pid, s)]

    if cat == "door_hinge":
        # 2 solids: Leaf A (X < 12) and Leaf B (X > 12)
        solids = sorted(shape.Solids, key=lambda sol: sol.BoundBox.XMin)
        if len(solids) != 2:
            raise ValueError(f"Expected 2 solids in SUP10 door hinge, got {len(solids)}")
        la = solids[0].copy()
        lb = solids[1].copy()
        # Leaf A: pivot=(7.5, 9.5), tenon Y=0..3, Z=0..6 -> exact coaxial pivot at world (77.0, 201.5, z)
        la.translate(FreeCAD.Vector(-7.5, -3.0, -3.0))
        la.translate(FreeCAD.Vector(77.0, y, z))
        # Leaf B: pivot=(24.0, 9.5), flip 180 deg around Y -> aligns bore over Leaf A pin & tenon into P08 at X=83.5
        lb.translate(FreeCAD.Vector(-24.0, -3.0, -3.0))
        lb.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 1, 0), 180.0)
        lb.translate(FreeCAD.Vector(77.0, y, z))
        return [(f"{pid}_LeafA", la), (f"{pid}_LeafB", lb)]

    if cat == "door_horn_coupler":
        s = shape.copy()
        off = meta.get("world_origin_offset", [82.5, 192.0, 94.0])
        s.translate(FreeCAD.Vector(float(off[0]), float(off[1]), float(off[2])))
        return [(pid, s)]

    if cat == "sg90_saddle":
        s = shape.copy()
        anc = meta.get("world_origin_anchor", [48.5, 211.8, 117.1])
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 180.0)
        s.translate(FreeCAD.Vector(float(anc[0]), float(anc[1]), float(anc[2])))
        return [(pid, s)]

    if cat == "wall_cradle":
        s = shape.copy()
        depth_h = float(pr["depth_h"])  # 8.0
        s.translate(FreeCAD.Vector(-bx / 2.0, -by / 2.0, -depth_h))
        rot_hint = meta.get("print_rotation_for_world", "rot_x_90")
        angle = -90.0 if rot_hint == "rot_x_-90" else 90.0
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), angle)
        if abs(rot_z) > 1e-6:
            s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), rot_z)
        s.translate(FreeCAD.Vector(x, y, z))
        return [(pid, s)]

    if cat == "dc022_strain_relief":
        s = shape.copy()
        depth_h = float(pr["depth_h"])  # 13.5
        s.translate(FreeCAD.Vector(-bx / 2.0, -by / 2.0, -depth_h))
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
        s.translate(FreeCAD.Vector(x, y, z))
        return [(pid, s)]

    if cat == "led5mm_collar":
        s = shape.copy()
        collar_h = float(pr["collar_h"])  # 5.0
        s.translate(FreeCAD.Vector(-bx / 2.0, -by / 2.0, -collar_h))
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
        if abs(rot_z) > 1e-6:
            s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), rot_z)
        s.translate(FreeCAD.Vector(x, y, z))
        return [(pid, s)]

    if cat == "buzzer_collar":
        s = shape.copy()
        depth_h = float(pr["depth_h"])  # 9.5
        s.translate(FreeCAD.Vector(-bx / 2.0, -by / 2.0, -depth_h))
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
        s.translate(FreeCAD.Vector(x, y, z))
        return [(pid, s)]

    raise ValueError(f"Unhandled support category: {cat}")


def place_furniture_in_world(shape: Any, meta: dict[str, Any]) -> list[tuple[str, Any]]:
    """Transform all assembly placements of one furniture part into world 3D space."""
    cat = meta["category"]
    pid = meta["part_id"]
    bx, by, bz = meta["print_bbox_mm"]
    pls = meta.get("assembly_placements", [])
    out: list[tuple[str, Any]] = []

    if cat == "mini_tree":
        solids = sorted(shape.Solids, key=lambda sol: sol.BoundBox.XMin)
        if len(solids) != 2:
            raise ValueError(f"Expected 2 solids in FUR07_MINI_TREE, got {len(solids)}")
        half_a_raw, half_b_raw = solids[0], solids[1]
        bba, bbb = half_a_raw.BoundBox, half_b_raw.BoundBox
        # Group placements by pot (pairs of 0/90 deg)
        pot_coords: list[tuple[float, float, float]] = []
        for pl in pls:
            key = (float(pl["x"]), float(pl["y"]), float(pl["z"]))
            if key not in pot_coords:
                pot_coords.append(key)
        for idx, (px, py, pz) in enumerate(pot_coords, 1):
            sa = half_a_raw.copy()
            sa.translate(FreeCAD.Vector(-(bba.XMin + bba.XMax) / 2.0, -bba.YMin, -(bba.ZMin + bba.ZMax) / 2.0))
            sa.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
            sa.translate(FreeCAD.Vector(px, py, pz))
            out.append((f"{pid}_Pot{idx}_A", sa))

            sb = half_b_raw.copy()
            sb.translate(FreeCAD.Vector(-(bbb.XMin + bbb.XMax) / 2.0, -bbb.YMin, -(bbb.ZMin + bbb.ZMax) / 2.0))
            sb.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
            sb.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 90.0)
            sb.translate(FreeCAD.Vector(px, py, pz))
            out.append((f"{pid}_Pot{idx}_B", sb))
        return out

    for idx, pl in enumerate(pls, 1):
        x, y, z = float(pl["x"]), float(pl["y"]), float(pl["z"])
        rot_z = float(pl.get("rot_z", 0.0))
        s = shape.copy()

        if cat == "tv_screen":
            ten_orig = meta.get("tenon_origin_local_mm", [bx / 2.0, 0.0, 2.0])
            s.translate(FreeCAD.Vector(-ten_orig[0], -ten_orig[1], -ten_orig[2]))
            s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
            if abs(rot_z) > 1e-6:
                s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), rot_z)
            s.translate(FreeCAD.Vector(x, y, z))
        elif cat == "floor_peg":
            s.translate(FreeCAD.Vector(-bx / 2.0, 0.0, -bz / 2.0))
            s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
            if abs(rot_z) > 1e-6:
                s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), rot_z)
            s.translate(FreeCAD.Vector(x, y, z))
        else:
            s.translate(FreeCAD.Vector(-bx / 2.0, -by / 2.0, 0.0))
            if abs(rot_z) > 1e-6:
                s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), rot_z)
            s.translate(FreeCAD.Vector(x, y, z))

        label = pid if len(pls) == 1 else f"{pid}_{idx}"
        out.append((label, s))
    return out


def build_real_kicad_pcb_world_solid(pcb: pcb_ssot.PcbSpec) -> tuple[Any, list[tuple[str, Any]]]:
    """Build exact 3D BRep of the real KiCad Hub PCB (with 4x 3.2 mm mounting holes + chamfered corners)."""
    hw_pcb = next(h for h in md.HARDWARE_PARTS if h.part_id == "HW_PCB")
    cx, cy, _cz = hw_pcb.center_xyz
    # Sits cleanly atop SUP06 standoff bosses at Z = 9.0 + 10.0 = 19.0 .. 20.6
    z0 = 19.0
    w, h, t = pcb.width_mm, pcb.height_mm, pcb.thickness_mm
    ch = pcb.corner_chamfer_mm
    x0, y0 = cx - w / 2.0, cy - h / 2.0

    pts = [
        FreeCAD.Vector(x0 + ch, y0, z0),
        FreeCAD.Vector(x0 + w - ch, y0, z0),
        FreeCAD.Vector(x0 + w, y0 + ch, z0),
        FreeCAD.Vector(x0 + w, y0 + h - ch, z0),
        FreeCAD.Vector(x0 + w - ch, y0 + h, z0),
        FreeCAD.Vector(x0 + ch, y0 + h, z0),
        FreeCAD.Vector(x0, y0 + h - ch, z0),
        FreeCAD.Vector(x0, y0 + ch, z0),
        FreeCAD.Vector(x0 + ch, y0, z0),
    ]
    board = Part.Face(Part.makePolygon(pts)).extrude(FreeCAD.Vector(0, 0, t))
    holes = [
        Part.makeCylinder(mh.drill_dia_mm / 2.0, t + 2.0, FreeCAD.Vector(x0 + mh.x_mm, y0 + mh.y_mm, z0 - 1.0))
        for mh in pcb.mounting_holes
    ]
    board = board.cut(Part.makeCompound(holes)).removeSplitter()

    # Build top-side keepout prisms for NodeMCU sockets, terminal blocks & on-board capacitors (C1-C9)
    keepouts: list[tuple[str, Any]] = []
    for kp in pcb.keepouts:
        fp_l = kp.footprint.lower()
        if "pinsocket_1x15" in fp_l:
            keepouts.append((f"PCB_{kp.ref}", Part.makeBox(2.6, 38.2, 8.5, FreeCAD.Vector(x0 + kp.x_mm - 1.3, y0 + kp.y_mm - 19.1, z0 + t))))
        elif "terminalblock" in fp_l:
            keepouts.append((f"PCB_{kp.ref}", Part.makeBox(10.0, 10.0, 10.0, FreeCAD.Vector(x0 + kp.x_mm - 5.0, y0 + kp.y_mm - 5.0, z0 + t))))
        elif "cp_radial" in fp_l:
            rad = 4.0 if "d8.0" in fp_l else (3.15 if "d6.3" in fp_l else 2.5)
            h_cap = 11.5 if "d8.0" in fp_l else 11.0
            keepouts.append((f"PCB_{kp.ref}", Part.makeCylinder(rad, h_cap, FreeCAD.Vector(x0 + kp.x_mm, y0 + kp.y_mm, z0 + t))))
        elif "c_disc" in fp_l:
            keepouts.append((f"PCB_{kp.ref}", Part.makeBox(5.0, 2.6, 6.0, FreeCAD.Vector(x0 + kp.x_mm - 2.5, y0 + kp.y_mm - 1.3, z0 + t))))
    return board, keepouts


def build_sg90_white_horn_solid(angle_deg: float = 0.0) -> Any:
    """Build exact TowerPro SG90 white single-arm horn at coaxial pivot (77.0, 201.5, Z=99.3..100.9)."""
    px, py = 77.0, 201.5
    z0, th = 99.3, 1.6
    hub = Part.makeCylinder(3.0, th, FreeCAD.Vector(px, py, z0))
    # Single arm length: center-to-tip 17.5 mm (arm box to R=15.25 + rounded tip R=2.25 -> tip at 17.5 mm)
    arm = Part.makeBox(15.25, 4.5, th, FreeCAD.Vector(px, py - 2.25, z0))
    tip = Part.makeCylinder(2.25, th, FreeCAD.Vector(px + 15.25, py, z0))
    horn = hub.fuse(arm).fuse(tip).removeSplitter()
    if abs(angle_deg) > 1e-6:
        horn.rotate(FreeCAD.Vector(px, py, 0.0), FreeCAD.Vector(0, 0, 1), angle_deg)
    return horn


def build_hardware_world_solids(pcb: pcb_ssot.PcbSpec) -> list[tuple[str, Any, tuple[float, float, float]]]:
    """Build world-space 3D solids for KiCad Hub PCB + all 14 off-board modules for fit & collision checks."""
    out: list[tuple[str, Any, tuple[float, float, float]]] = []
    pcb_solid, _kps = build_real_kicad_pcb_world_solid(pcb)
    out.append(("HW_PCB", pcb_solid, (0.08, 0.45, 0.18)))

    for h in md.HARDWARE_PARTS:
        if h.part_id == "HW_PCB":
            continue
        cx, cy, cz = h.center_xyz
        sx, sy, sz = h.size_xyz
        if h.part_id in ("HW_RELAY1", "HW_RELAY2"):
            # Realistic 2-tier model: 50x26x1.6 mm PCB (Z=8.0..9.6) with 4x 3.1mm corner holes + central relay/terminal body (36x20x16.9, Z=9.6..26.5)
            pcb_b = Part.makeBox(sx, sy, 1.6, FreeCAD.Vector(cx - sx / 2.0, cy - sy / 2.0, 8.0))
            holes = [
                Part.makeCylinder(3.1 / 2.0, 3.6, FreeCAD.Vector(cx + s_x * 44.5 / 2.0, cy + s_y * 20.5 / 2.0, 7.0))
                for s_x in (-1.0, 1.0) for s_y in (-1.0, 1.0)
            ]
            pcb_b = pcb_b.cut(Part.makeCompound(holes))
            cube = Part.makeBox(36.0, 20.0, sz - 1.6, FreeCAD.Vector(cx - 18.0, cy - 10.0, 9.6))
            box = pcb_b.fuse(cube).removeSplitter()
        elif h.part_id == "HW_PAM8403":
            # Realistic 2-tier model: 21x18x1.6 mm bare PCB (Z=4.8..6.4) below snap ribs + inboard SMD body (18x14x1.8, Z=6.4..8.2)
            pcb_b = Part.makeBox(sx, sy, 1.6, FreeCAD.Vector(cx - sx / 2.0, cy - sy / 2.0, 4.8))
            smd = Part.makeBox(sx - 3.0, sy - 4.0, sz - 1.6, FreeCAD.Vector(cx - (sx - 3.0) / 2.0, cy - (sy - 4.0) / 2.0, 6.4))
            box = pcb_b.fuse(smd).removeSplitter()
        elif h.part_id == "HW_PUMP":
            # Sits inside SUP15 water liner floor at Z=2.4..35.4
            box = Part.makeBox(sx, sy, sz, FreeCAD.Vector(cx - sx / 2.0, cy - sy / 2.0, 2.4))
        elif h.part_id == "HW_SPEAKER":
            # Round speaker Dia 28 x 5.2 mm behind P15 (Y=13.0..18.2, centered at X=223, Z=26)
            box = Part.makeCylinder(14.0, 5.2, FreeCAD.Vector(223.0, 13.0, 26.0), FreeCAD.Vector(0, 1, 0))
        elif h.part_id == "HW_SG90":
            # Realistic inverted TowerPro SG90 seated on P07_SERVO_SHELF (Z=108.5..111.5), coaxial shaft at (77.0, 201.5)
            body = Part.makeBox(22.8, 12.2, 22.5, FreeCAD.Vector(71.5 - 11.4, 201.5 - 6.1, 107.4))
            ears = Part.makeBox(32.2, 12.2, 2.5, FreeCAD.Vector(71.5 - 16.1, 201.5 - 6.1, 111.5))
            gear_hub = Part.makeCylinder(5.9, 4.2, FreeCAD.Vector(77.0, 201.5, 103.2))
            spline = Part.makeCylinder(2.4, 2.3, FreeCAD.Vector(77.0, 201.5, 100.9))
            box = body.fuse(ears).fuse(gear_hub).fuse(spline).removeSplitter()
        elif h.part_id == "HW_DC_JACK":
            # Realistic DC-022 M12 barrel jack: Dia 14x1 front flange + Dia 12x20 rear barrel inside SUP16
            flange = Part.makeCylinder(7.0, 1.0, FreeCAD.Vector(30.0, 9.0, 22.0), FreeCAD.Vector(0, 1, 0))
            barrel = Part.makeCylinder(6.0, 20.0, FreeCAD.Vector(30.0, 10.0, 22.0), FreeCAD.Vector(0, 1, 0))
            box = flange.fuse(barrel).removeSplitter()
        elif h.part_id == "HW_BUZZER":
            # Realistic TMB12A05 Dia 12.0 x 9.5 mm active buzzer seated inside SUP18 behind P05
            box = Part.makeCylinder(6.0, 9.5, FreeCAD.Vector(200.0, 192.05, 126.0), FreeCAD.Vector(0, 1, 0))
        elif h.part_id == "HW_LED_LR":
            # Realistic T-1 3/4 5mm LED seated in SUP17 (-X side of P06 @ Y=232, Z=126)
            flange = Part.makeCylinder(2.9, 1.0, FreeCAD.Vector(197.4, 232.0, 126.0), FreeCAD.Vector(1, 0, 0))
            dome = Part.makeCylinder(2.5, 7.6, FreeCAD.Vector(189.8, 232.0, 126.0), FreeCAD.Vector(1, 0, 0))
            box = flange.fuse(dome).removeSplitter()
        elif h.part_id == "HW_LED_BR":
            # Realistic T-1 3/4 5mm LED seated in SUP17 (+X side of P06 @ Y=258, Z=126)
            flange = Part.makeCylinder(2.9, 1.0, FreeCAD.Vector(201.6, 258.0, 126.0), FreeCAD.Vector(1, 0, 0))
            dome = Part.makeCylinder(2.5, 7.6, FreeCAD.Vector(202.6, 258.0, 126.0), FreeCAD.Vector(1, 0, 0))
            box = flange.fuse(dome).removeSplitter()
        else:
            box = Part.makeBox(sx, sy, sz, FreeCAD.Vector(cx - sx / 2.0, cy - sy / 2.0, cz - sz / 2.0))
        out.append((h.part_id, box, h.color_rgb))
    return out


def build_door_swing_envelope(step_deg: int = 5) -> Any:
    """90-deg swept arc of P08_DOOR_LEAF around unified coaxial hinge pivot (77.0, 201.5, Z=2..102)."""
    pivot = FreeCAD.Vector(77.0, 201.5, 2.0)
    r = 58.0
    pts = [pivot]
    for deg in range(0, 91, max(1, step_deg)):
        rad = math.radians(deg)
        pts.append(FreeCAD.Vector(77.0 + r * math.cos(rad), 201.5 + r * math.sin(rad), 2.0))
    pts.append(pivot)
    return Part.Face(Part.makePolygon(pts)).extrude(FreeCAD.Vector(0, 0, 100.0))


def build_door_swept_poses(
    moving_parts: list[tuple[str, Any]],
    pivot_xy: tuple[float, float] = (77.0, 201.5),
    angles_deg: tuple[int, ...] = tuple(range(0, 91, 5)),
) -> list[tuple[int, list[tuple[str, Any]]]]:
    """Rotate moving door assembly (P08 + SUP10_LeafB x2 + SUP10B + SG90_WhiteHorn) across 0..90 deg."""
    piv = FreeCAD.Vector(pivot_xy[0], pivot_xy[1], 0.0)
    axis = FreeCAD.Vector(0.0, 0.0, 1.0)
    poses: list[tuple[int, list[tuple[str, Any]]]] = []
    for deg in angles_deg:
        rotated: list[tuple[str, Any]] = []
        for name, sh in moving_parts:
            s = sh.copy()
            if deg != 0:
                s.rotate(piv, axis, float(deg))
            rotated.append((name, s))
        poses.append((deg, rotated))
    return poses
