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
        if p.stem in ("fit_table", "assembly_report", "plates_manifest", "slice_report", "user_like_test_report"):
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if "part_id" in d and "kind" in d:
            metas[d["part_id"]] = d
    return metas


def place_panel_in_world(shape: Any, meta: dict[str, Any], origin_override: list[float] | None = None) -> Any:
    """Transform a print-ready panel STEP shape back into exact 3D assembled house world coordinates."""
    s = shape.copy()
    lmin = meta["local_bbox_min"]
    su = float(meta["shift_u"])
    sv = float(meta["shift_v"])
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
        # Leaf A: pivot=(7.5, 6.5), tenon Y=0..3, Z=0..6 -> pivot at world (77.0, 198.5, z)
        la.translate(FreeCAD.Vector(-7.5, -3.0, -3.0))
        la.translate(FreeCAD.Vector(77.0, y, z))
        # Leaf B: pivot=(24.0, 6.5), flip 180 deg around Y -> aligns bore over Leaf A pin & tenon into P08 at X=83.5
        lb.translate(FreeCAD.Vector(-24.0, -3.0, -3.0))
        lb.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 1, 0), 180.0)
        lb.translate(FreeCAD.Vector(77.0, y, z))
        return [(f"{pid}_LeafA", la), (f"{pid}_LeafB", lb)]

    if cat == "servo_link_clip":
        s = shape.copy()
        th = float(pr["tenon_h"])  # 3.0
        ty = float(pr["tenon_y"])  # 6.0
        s.translate(FreeCAD.Vector(-bx / 2.0, -th, -ty / 2.0))
        s.translate(FreeCAD.Vector(x, y, z))
        return [(pid, s)]

    if cat == "sg90_saddle":
        s = shape.copy()
        leg_top_z = 3.0 + float(pr["ear_t"])  # 5.6
        s.translate(FreeCAD.Vector(-bx / 2.0, -by / 2.0, -leg_top_z))
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 180.0)
        s.translate(FreeCAD.Vector(x, y, z))
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


def build_hardware_world_solids(pcb: pcb_ssot.PcbSpec) -> list[tuple[str, Any, tuple[float, float, float]]]:
    """Build world-space 3D solids for KiCad Hub PCB + key off-board modules for fit & collision checks."""
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
        else:
            box = Part.makeBox(sx, sy, sz, FreeCAD.Vector(cx - sx / 2.0, cy - sy / 2.0, cz - sz / 2.0))
        out.append((h.part_id, box, h.color_rgb))
    return out


def build_door_swing_envelope() -> Any:
    """95-degree swept arc of P08_DOOR_LEAF (56 mm radius around hinge pivot X=77, Y=198.5, Z=2..102)."""
    pivot = FreeCAD.Vector(77.0, 198.5, 2.0)
    r = 57.5
    pts = [pivot]
    for deg in range(0, 96, 5):
        rad = math.radians(deg)
        pts.append(FreeCAD.Vector(77.0 + r * math.cos(rad), 198.5 + r * math.sin(rad), 2.0))
    pts.append(pivot)
    return Part.Face(Part.makePolygon(pts)).extrude(FreeCAD.Vector(0, 0, 100.0))
