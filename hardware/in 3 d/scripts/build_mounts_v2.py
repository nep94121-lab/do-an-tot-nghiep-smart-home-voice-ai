"""Headless FreeCAD 1.1 builder for all 18 screwless mounts, clips, hinges & water liner (3D-Print Set v2).

Run via FreeCADCmd:
    "C:\\Users\\LENOVO\\AppData\\Local\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe" "hardware/in 3 d/scripts/build_mounts_v2.py"
"""

from __future__ import annotations

import argparse
import math
import os
import pathlib
import sys
import time
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PRINT3D_ROOT = SCRIPT_DIR.parent
MICA_DIR = PRINT3D_ROOT.parent / "mica"

for _p in (str(SCRIPT_DIR), str(MICA_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import FreeCAD
import Part

import cad_common as cc
import kicad_pcb_ssot as pcb_ssot
import print_domain as pd_mod


def _make_rect_wire(cx: float, cy: float, dx: float, dy: float, z: float) -> Any:
    hx, hy = dx / 2.0, dy / 2.0
    pts = [
        FreeCAD.Vector(cx - hx, cy - hy, z),
        FreeCAD.Vector(cx + hx, cy - hy, z),
        FreeCAD.Vector(cx + hx, cy + hy, z),
        FreeCAD.Vector(cx - hx, cy + hy, z),
        FreeCAD.Vector(cx - hx, cy - hy, z),
    ]
    return Part.makePolygon(pts)


def _make_chamfered_tenon_up(
    cx: float,
    cy: float,
    tx: float,
    ty: float,
    z0: float,
    th: float,
    ch: float = 0.30,
) -> Any:
    """Rectangular upward tenon with 45-deg top lead-in frustum (0.5 mm root overlap into base)."""
    body_h = th - ch + 0.5
    shaft = Part.makeBox(tx, ty, body_h, FreeCAD.Vector(cx - tx / 2.0, cy - ty / 2.0, z0 - 0.5))
    w_bot = _make_rect_wire(cx, cy, tx, ty, z0 + th - ch)
    w_top = _make_rect_wire(cx, cy, max(0.8, tx - 2.0 * ch), max(0.8, ty - 2.0 * ch), z0 + th)
    tip = Part.makeLoft([w_bot, w_top], True, True)
    return shaft.fuse(tip).removeSplitter()


def _make_vaulted_mortise_pocket(
    cx: float,
    cy: float,
    du: float,
    dv: float,
    depth: float,
    z0: float = 0.0,
) -> Any:
    """Underside mortise pocket with 45-deg vaulted roof so blind pockets need zero supports/bridging."""
    box = Part.makeBox(du, dv, depth + 0.5, FreeCAD.Vector(cx - du / 2.0, cy - dv / 2.0, z0 - 0.5))
    # Vault along the shorter span (dv) so peak height is dv/2 at exact 45 deg
    x0 = cx - du / 2.0
    z_top = z0 + depth
    vault_h = dv / 2.0
    tri_pts = [
        FreeCAD.Vector(x0, cy - dv / 2.0, z_top - 0.05),
        FreeCAD.Vector(x0, cy + dv / 2.0, z_top - 0.05),
        FreeCAD.Vector(x0, cy, z_top + vault_h),
        FreeCAD.Vector(x0, cy - dv / 2.0, z_top - 0.05),
    ]
    tri_face = Part.Face(Part.makePolygon(tri_pts))
    vault = tri_face.extrude(FreeCAD.Vector(du, 0.0, 0.0))
    return box.fuse(vault).removeSplitter()


def _make_split_snap_peg_and_slot(
    cx: float,
    cy: float,
    z_base: float,
    peg_od: float,
    peg_h: float,
    board_t: float,
    slot_w: float = 0.80,
    barb_radial: float = 0.25,
) -> tuple[Any, Any]:
    """Return (solid_peg, flex_slot_cutter) for a vertical split cantilever snap-fit peg (45-deg barb)."""
    r0 = peg_od / 2.0
    r_barb = r0 + barb_radial
    r_tip = max(0.75, r0 * 0.68)

    z_ramp0 = z_base + board_t + 0.15
    z_ramp1 = z_ramp0 + barb_radial
    z_land1 = z_ramp1 + 0.25
    z_top = z_base + peg_h

    shaft = Part.makeCylinder(r0, (z_ramp0 - z_base) + 0.6, FreeCAD.Vector(cx, cy, z_base - 0.5))
    ramp = Part.makeCone(r0, r_barb, barb_radial + 0.05, FreeCAD.Vector(cx, cy, z_ramp0 - 0.05))
    land = Part.makeCylinder(r_barb, (z_land1 - z_ramp1) + 0.05, FreeCAD.Vector(cx, cy, z_ramp1 - 0.05))
    tip = Part.makeCone(r_barb, r_tip, max(0.4, z_top - z_land1) + 0.05, FreeCAD.Vector(cx, cy, z_land1 - 0.05))
    peg = shaft.fuse(ramp).fuse(land).fuse(tip).removeSplitter()

    slot_len = peg_od + 2.0 * barb_radial + 2.0
    slot = Part.makeBox(
        slot_w,
        slot_len,
        peg_h + 1.0,
        FreeCAD.Vector(cx - slot_w / 2.0, cy - slot_len / 2.0, z_base),
    )
    return peg, slot


def _make_snap_rib_x(
    x0: float,
    x1: float,
    y_wall: float,
    inward_sign: float,
    z_start: float,
    protrude: float = 0.40,
    land_h: float = 0.40,
) -> Any:
    """45-deg self-supporting horizontal snap retention rib along an inner Y wall."""
    # Overlap 0.25 mm into wall for clean boolean fuse
    y_back = y_wall - inward_sign * 0.25
    y_tip = y_wall + inward_sign * protrude
    z1 = z_start + protrude
    z2 = z1 + land_h
    z3 = z2 + protrude
    pts = [
        FreeCAD.Vector(x0, y_back, z_start),
        FreeCAD.Vector(x0, y_wall, z_start),
        FreeCAD.Vector(x0, y_tip, z1),
        FreeCAD.Vector(x0, y_tip, z2),
        FreeCAD.Vector(x0, y_wall, z3),
        FreeCAD.Vector(x0, y_back, z3),
        FreeCAD.Vector(x0, y_back, z_start),
    ]
    face = Part.Face(Part.makePolygon(pts))
    return face.extrude(FreeCAD.Vector(x1 - x0, 0.0, 0.0))


def _build_corner_clip(sup: pd_mod.SupportSpec) -> tuple[Any, dict[str, Any]]:
    pr = sup.params
    arm = float(pr["arm"])
    h = float(pr["height"])
    wt = float(pr["wall_t"])
    sw = float(pr["slot_w"])
    arm_w = sw + 2.0 * wt

    leg_x = Part.makeBox(arm, arm_w, h, FreeCAD.Vector(0.0, 0.0, 0.0))
    leg_y = Part.makeBox(arm_w, arm, h, FreeCAD.Vector(0.0, 0.0, 0.0))

    # Flat cap gusset web at Z=0..wt braces the 90-deg corner and provides a clean engraved ID surface
    g_edge = max(arm_w + 1.0, arm * 0.65)
    cap_pts = [
        FreeCAD.Vector(0.0, 0.0, 0.0),
        FreeCAD.Vector(arm, 0.0, 0.0),
        FreeCAD.Vector(arm, g_edge, 0.0),
        FreeCAD.Vector(g_edge, arm, 0.0),
        FreeCAD.Vector(0.0, arm, 0.0),
        FreeCAD.Vector(0.0, 0.0, 0.0),
    ]
    cap_web = Part.Face(Part.makePolygon(cap_pts)).extrude(FreeCAD.Vector(0.0, 0.0, wt))

    slot_x = Part.makeBox(arm - wt + 1.0, sw, h - wt + 1.0, FreeCAD.Vector(wt, wt, wt))
    slot_y = Part.makeBox(sw, arm - wt + 1.0, h - wt + 1.0, FreeCAD.Vector(wt, wt, wt))

    shape = leg_x.fuse(leg_y).fuse(cap_web).cut(Part.makeCompound([slot_x, slot_y])).removeSplitter()

    # Engrave inside the triangular cap gusset well clear of inner arm walls (x=arm_w, y=arm_w)
    eng_cx = arm_w + (arm - arm_w) * 0.36
    eng_cy = arm_w + (arm - arm_w) * 0.32
    eng_fh = 2.0 if arm >= 22.0 else 1.7
    eng_spec = pd_mod.EngraveSpec(sup.engrave.line1, "", round(eng_cx, 2), round(eng_cy, 2), eng_fh, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng_spec, wt, 0.45)

    return shape, {
        "engraved_ok": eng_ok,
        "engrave_text": eng_spec.line1,
        "print_rotation_for_world": "flip_xy_diag_180",
    }


def _build_t_clip(sup: pd_mod.SupportSpec) -> tuple[Any, dict[str, Any]]:
    pr = sup.params
    bar_len = float(pr["bar_len"])
    stem_len = float(pr["stem_len"])
    h = float(pr["height"])
    wt = float(pr["wall_t"])
    sw = float(pr["slot_w"])
    bar_w = sw + 2.0 * wt
    cx = bar_len / 2.0

    bar = Part.makeBox(bar_len, bar_w, h, FreeCAD.Vector(0.0, 0.0, 0.0))
    stem = Part.makeBox(bar_w, stem_len, h, FreeCAD.Vector(cx - bar_w / 2.0, 0.0, 0.0))

    # Small corner gussets on the cap at Z=0..wt reinforce the 90-deg T junction
    g_w = 5.0
    stem_x0 = cx - bar_w / 2.0
    stem_x1 = cx + bar_w / 2.0
    g_left = Part.Face(Part.makePolygon([
        FreeCAD.Vector(stem_x0 - g_w, bar_w - 0.5, 0.0),
        FreeCAD.Vector(stem_x0 + 0.5, bar_w - 0.5, 0.0),
        FreeCAD.Vector(stem_x0 + 0.5, bar_w + g_w, 0.0),
        FreeCAD.Vector(stem_x0 - g_w, bar_w - 0.5, 0.0),
    ])).extrude(FreeCAD.Vector(0.0, 0.0, wt))
    g_right = Part.Face(Part.makePolygon([
        FreeCAD.Vector(stem_x1 - 0.5, bar_w - 0.5, 0.0),
        FreeCAD.Vector(stem_x1 + g_w, bar_w - 0.5, 0.0),
        FreeCAD.Vector(stem_x1 - 0.5, bar_w + g_w, 0.0),
        FreeCAD.Vector(stem_x1 - 0.5, bar_w - 0.5, 0.0),
    ])).extrude(FreeCAD.Vector(0.0, 0.0, wt))

    slot_main = Part.makeBox(bar_len + 2.0, sw, h - wt + 1.0, FreeCAD.Vector(-1.0, wt, wt))
    slot_stem = Part.makeBox(sw, stem_len - wt + 1.0, h - wt + 1.0, FreeCAD.Vector(cx - sw / 2.0, wt, wt))

    shape = bar.fuse(stem).fuse(g_left).fuse(g_right).cut(Part.makeCompound([slot_main, slot_stem])).removeSplitter()

    eng_spec = pd_mod.EngraveSpec("SUP01B", "", cx, wt + sw / 2.0, 1.9, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng_spec, wt, 0.40)

    return shape, {
        "engraved_ok": eng_ok,
        "engrave_text": "SUP01B",
        "print_rotation_for_world": "rot_x_180_centered_bar",
    }


def _build_seam_clip(sup: pd_mod.SupportSpec) -> tuple[Any, dict[str, Any]]:
    pr = sup.params
    L = float(pr["length"])
    sw = float(pr["slot_w"])
    wt = float(pr["wall_t"])
    h = float(pr["height"])
    total_w = sw + 2.0 * wt

    outer = Part.makeBox(L, total_w, h, FreeCAD.Vector(0.0, 0.0, 0.0))
    slot = Part.makeBox(L + 2.0, sw, h - wt + 1.0, FreeCAD.Vector(-1.0, wt, wt))
    shape = outer.cut(slot).removeSplitter()

    eng_spec = pd_mod.EngraveSpec("SUP03", "", L / 2.0, wt + sw / 2.0, 2.0, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng_spec, wt, 0.40)

    return shape, {
        "engraved_ok": eng_ok,
        "engrave_text": "SUP03",
        "print_rotation_for_world": "rot_x_180",
    }


def _build_foot_clip(sup: pd_mod.SupportSpec) -> tuple[Any, dict[str, Any]]:
    pr = sup.params
    sz = float(pr["size"])
    lh = float(pr["lift_h"])
    lip_h = float(pr["lip_h"])
    # 0.15 mm slip-fit relief on inner face of L-lip so base corners drop in without BRep overlap
    lip_t = float(pr["lip_t"]) - 0.15

    pad = Part.makeBox(sz, sz, lh, FreeCAD.Vector(0.0, 0.0, 0.0))
    lip_x = Part.makeBox(sz, lip_t, lip_h, FreeCAD.Vector(0.0, 0.0, lh))
    lip_y = Part.makeBox(lip_t, sz, lip_h, FreeCAD.Vector(0.0, 0.0, lh))
    shape = pad.fuse(lip_x).fuse(lip_y).removeSplitter()

    shape, eng_ok = cc.safe_engrave_top_face(shape, sup.engrave, lh, 0.50)

    return shape, {
        "engraved_ok": eng_ok,
        "engrave_text": f"{sup.engrave.line1} {sup.engrave.line2}".strip(),
        "print_rotation_for_world": "identity",
    }


def _build_tenon_riser(sup: pd_mod.SupportSpec) -> tuple[Any, dict[str, Any]]:
    """Print lying on its side (X=14, Y=12, Z=9) with both tenons flush on Z=0 for zero overhang."""
    pr = sup.params
    bx = float(pr["body_x"])
    by = float(pr["body_y"])
    lh = float(pr["lift_h"])
    tx = float(pr["tenon_x"])
    ty = float(pr["tenon_y"])
    th = float(pr["tenon_h"])
    ch = 0.30

    # Central riser body (Y = th .. th + lh, full Z = 0..by)
    body = Part.makeBox(bx, lh, by, FreeCAD.Vector(0.0, th, 0.0))

    # Both tenons lie flat on Z = 0..ty with vertical 45-deg tip chamfers along X (zero overhang)
    def _flat_tenon(y_root: float, y_tip: float) -> Any:
        x0 = (bx - tx) / 2.0
        x1 = x0 + tx
        y_ch = y_tip - ch if y_tip > y_root else y_tip + ch
        pts = [
            FreeCAD.Vector(x0, y_root, 0.0),
            FreeCAD.Vector(x1, y_root, 0.0),
            FreeCAD.Vector(x1, y_ch, 0.0),
            FreeCAD.Vector(x1 - ch, y_tip, 0.0),
            FreeCAD.Vector(x0 + ch, y_tip, 0.0),
            FreeCAD.Vector(x0, y_ch, 0.0),
            FreeCAD.Vector(x0, y_root, 0.0),
        ]
        return Part.Face(Part.makePolygon(pts)).extrude(FreeCAD.Vector(0.0, 0.0, ty))

    t_bot = _flat_tenon(th + 0.5, 0.0)
    t_top = _flat_tenon(th + lh - 0.5, lh + 2.0 * th)
    shape = body.fuse(t_bot).fuse(t_top).removeSplitter()

    eng_spec = pd_mod.EngraveSpec("SUP05", "", bx / 2.0, th + lh / 2.0, 1.8, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng_spec, by, 0.40)

    return shape, {
        "engraved_ok": eng_ok,
        "engrave_text": "SUP05",
        "print_rotation_for_world": "rot_x_90",
        "tenon_center_print": [round(bx / 2.0, 3), round(th + lh / 2.0, 3), round(ty / 2.0, 3)],
    }


def _build_tenon_peg(sup: pd_mod.SupportSpec) -> tuple[Any, dict[str, Any]]:
    """Flat-printed 6.0x6.0x3.0 mm floating tenon peg with 0.3 mm lead-in chamfers (zero overhang)."""
    pr = sup.params
    tx = float(pr["tenon_x"])  # 6.0 along X
    ty = float(pr["tenon_y"])  # 3.0 along Z
    lz = float(pr["length_z"])  # 6.0 along Y
    ch = 0.30

    # Vertical corner chamfers on both ends Y=0 and Y=lz keep Z=0 completely flat
    pts = [
        FreeCAD.Vector(ch, 0.0, 0.0),
        FreeCAD.Vector(tx - ch, 0.0, 0.0),
        FreeCAD.Vector(tx, ch, 0.0),
        FreeCAD.Vector(tx, lz - ch, 0.0),
        FreeCAD.Vector(tx - ch, lz, 0.0),
        FreeCAD.Vector(ch, lz, 0.0),
        FreeCAD.Vector(0.0, lz - ch, 0.0),
        FreeCAD.Vector(0.0, ch, 0.0),
        FreeCAD.Vector(ch, 0.0, 0.0),
    ]
    base_prism = Part.Face(Part.makePolygon(pts)).extrude(FreeCAD.Vector(0.0, 0.0, ty - ch))

    # Top 45-deg chamfered bevel cap along Y=0 and Y=lz (Z = ty-ch .. ty)
    w_bot = Part.makePolygon([FreeCAD.Vector(p.x, p.y, ty - ch) for p in pts])
    pts_top = [
        FreeCAD.Vector(ch, ch, ty),
        FreeCAD.Vector(tx - ch, ch, ty),
        FreeCAD.Vector(tx, ch, ty),
        FreeCAD.Vector(tx, lz - ch, ty),
        FreeCAD.Vector(tx - ch, lz - ch, ty),
        FreeCAD.Vector(ch, lz - ch, ty),
        FreeCAD.Vector(0.0, lz - ch, ty),
        FreeCAD.Vector(0.0, ch, ty),
        FreeCAD.Vector(ch, ch, ty),
    ]
    # Keep 8 distinct vertices on top matching bottom for clean loft
    pts_top_clean = [
        FreeCAD.Vector(ch, ch, ty),
        FreeCAD.Vector(tx - ch, ch, ty),
        FreeCAD.Vector(tx - 0.15, ch + 0.15, ty),
        FreeCAD.Vector(tx - 0.15, lz - ch - 0.15, ty),
        FreeCAD.Vector(tx - ch, lz - ch, ty),
        FreeCAD.Vector(ch, lz - ch, ty),
        FreeCAD.Vector(0.15, lz - ch - 0.15, ty),
        FreeCAD.Vector(0.15, ch + 0.15, ty),
        FreeCAD.Vector(ch, ch, ty),
    ]
    w_top = Part.makePolygon(pts_top_clean)
    cap = Part.makeLoft([w_bot, w_top], True, True)
    shape = base_prism.fuse(cap).removeSplitter()

    # Too small (6x6x3 mm) for crisp 0.4 mm nozzle engraving; skip intentionally
    return shape, {
        "engraved_ok": False,
        "engrave_text": "",
        "print_rotation_for_world": "rot_x_90",
    }


def _build_pcb_carrier(sup: pd_mod.SupportSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, dict[str, Any]]:
    pr = sup.params
    ox = 104.0
    oy = 84.0
    base_h = float(pr["base_h"])  # 3.0
    standoff_h = float(pr["standoff_h"])  # 10.0
    px = float(pr["pitch_x"])  # 90.0
    py = float(pr["pitch_y"])  # 70.0
    pcb_t = float(pr["pcb_t"])  # 1.6
    peg_od = float(pr["peg_od"])  # 3.00
    peg_h = 3.6
    boss_od = 7.4
    c2 = 2.0 * cfg.mortise_clr_per_side  # +0.30
    mort_du = round(float(pr["tenon_x"]) + c2, 3)  # 6.30
    mort_dv = round(float(pr["tenon_y"]) + c2, 3)  # 3.30
    mort_d = float(pr["tenon_h"])  # 3.0

    # Open frame 104x84x3.0 with 72x52 center cutout clearing underside solder pins
    cut_x, cut_y = 72.0, 52.0
    base = Part.makeBox(ox, oy, base_h, FreeCAD.Vector(0.0, 0.0, 0.0))
    center_cut = Part.makeBox(
        cut_x, cut_y, base_h + 2.0,
        FreeCAD.Vector((ox - cut_x) / 2.0, (oy - cut_y) / 2.0, -1.0),
    )
    shape = base.cut(center_cut)

    boss_base_x, boss_base_y, boss_base_h = 12.0, 10.0, 5.4
    cutters: list[Any] = []
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            bx = ox / 2.0 + sx * px / 2.0
            by = oy / 2.0 + sy * py / 2.0
            # Lower 12x10x5.4 rectangular pedestal houses the 6.30x3.30x3.0 underside mortise + 45-deg vault
            ped = Part.makeBox(
                boss_base_x, boss_base_y, boss_base_h,
                FreeCAD.Vector(bx - boss_base_x / 2.0, by - boss_base_y / 2.0, 0.0),
            )
            # Upper cylindrical standoff boss OD=7.4 mm clears KiCad corner traces/pads
            boss = Part.makeCylinder(boss_od / 2.0, standoff_h, FreeCAD.Vector(bx, by, 0.0))
            peg, slot = _make_split_snap_peg_and_slot(
                bx, by, standoff_h, peg_od=peg_od, peg_h=peg_h, board_t=pcb_t, slot_w=0.80, barb_radial=0.25,
            )
            shape = shape.fuse(ped).fuse(boss).fuse(peg)
            cutters.append(slot)
            cutters.append(_make_vaulted_mortise_pocket(bx, by, mort_du, mort_dv, mort_d, z0=0.0))

    shape = shape.cut(Part.makeCompound(cutters)).removeSplitter()

    eng_spec = pd_mod.EngraveSpec("SUP06 PCB", "100x80", ox / 2.0, 8.0, 2.8, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng_spec, base_h, 0.45)

    return shape, {
        "engraved_ok": eng_ok,
        "engrave_text": "SUP06 PCB 100x80",
        "print_rotation_for_world": "identity",
    }


def _build_relay_caddy(sup: pd_mod.SupportSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, dict[str, Any]]:
    pr = sup.params
    cav_x = float(pr["cavity_x"])  # 50.4
    cav_y = float(pr["cavity_y"])  # 26.4
    wall_t = 2.0
    ox = round(cav_x + 2.0 * wall_t, 3)  # 54.4
    oy = round(cav_y + 2.0 * wall_t, 3)  # 30.4
    base_h = float(pr["base_h"])  # 2.4
    standoff_h = float(pr["standoff_h"])  # 8.0
    rim_h = 1.8
    total_wall_h = standoff_h + rim_h  # 9.8
    px = float(pr["pitch_x"])  # 44.5
    py = float(pr["pitch_y"])  # 20.5
    pcb_t = float(pr["pcb_t"])  # 1.6
    peg_od = float(pr["peg_od"])  # 2.90
    peg_h = 3.4
    boss_od = 6.4

    c2 = 2.0 * cfg.mortise_clr_per_side
    mort_du = round(float(pr["tenon_x"]) + c2, 3)  # 6.30
    mort_dv = round(float(pr["tenon_y"]) + c2, 3)  # 3.30
    mort_d = float(pr["tenon_h"])  # 3.0
    tenon_span = float(pr["tenon_span"])  # 32.0

    # Outer rim box with interior cavity above base_h and 20x12 center airflow cutout (clears mortise pads)
    outer = Part.makeBox(ox, oy, total_wall_h, FreeCAD.Vector(0.0, 0.0, 0.0))
    cavity = Part.makeBox(cav_x, cav_y, total_wall_h - base_h + 2.0, FreeCAD.Vector(wall_t, wall_t, base_h))
    air_x, air_y = 20.0, 12.0
    airflow = Part.makeBox(
        air_x, air_y, base_h + 2.0,
        FreeCAD.Vector((ox - air_x) / 2.0, (oy - air_y) / 2.0, -1.0),
    )
    shape = outer.cut(Part.makeCompound([cavity, airflow]))

    cutters: list[Any] = []
    # 4 corner standoff bosses (Z=0..8.0) + vertical split snap-fit pegs (Z=8.0..11.4)
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            bx = ox / 2.0 + sx * px / 2.0
            by = oy / 2.0 + sy * py / 2.0
            boss = Part.makeCylinder(boss_od / 2.0, standoff_h, FreeCAD.Vector(bx, by, 0.0))
            peg, slot = _make_split_snap_peg_and_slot(
                bx, by, standoff_h, peg_od=peg_od, peg_h=peg_h, board_t=pcb_t, slot_w=0.75, barb_radial=0.22,
            )
            shape = shape.fuse(boss).fuse(peg)
            cutters.append(slot)

    # 2 solid mortise pads (10x8x5.4 mm) at X = ox/2 +/- 16.0, Y = oy/2 for SUP05B floating tenons
    pad_x, pad_y, pad_h = 10.0, 8.0, 5.4
    for sx in (-1.0, 1.0):
        mx = ox / 2.0 + sx * tenon_span / 2.0
        my = oy / 2.0
        pad = Part.makeBox(pad_x, pad_y, pad_h, FreeCAD.Vector(mx - pad_x / 2.0, my - pad_y / 2.0, 0.0))
        shape = shape.fuse(pad)
        cutters.append(_make_vaulted_mortise_pocket(mx, my, mort_du, mort_dv, mort_d, z0=0.0))

    shape = shape.cut(Part.makeCompound(cutters)).removeSplitter()

    eng_spec = pd_mod.EngraveSpec("SUP07 RLY", "", ox / 2.0, 5.6, 2.2, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng_spec, base_h, 0.40)

    return shape, {
        "engraved_ok": eng_ok,
        "engrave_text": "SUP07 RLY",
        "print_rotation_for_world": "identity",
    }


def _build_pam_tray(sup: pd_mod.SupportSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, dict[str, Any]]:
    pr = sup.params
    # Widen outer_x to 36.0 mm (vs 34.0 nominal) so outer wall around 6.30mm mortise at span=26 is 1.85 mm (>=4 perimeters)
    ox = 36.0
    oy = float(pr["outer_y"])  # 23.0
    cav_x = float(pr["cavity_x"])  # 21.4
    cav_y = float(pr["cavity_y"])  # 18.4
    # Base height 4.8 mm fully clears the 3.0 mm mortise + 1.65 mm 45-deg vaulted ceiling below cavity floor
    base_h = 4.8
    wall_h = 8.8
    tenon_span = float(pr["tenon_span"])  # 26.0
    c2 = 2.0 * cfg.mortise_clr_per_side
    mort_du = round(float(pr["tenon_x"]) + c2, 3)  # 6.30
    mort_dv = round(float(pr["tenon_y"]) + c2, 3)  # 3.30
    mort_d = float(pr["tenon_h"])  # 3.0

    # Solid base block (Z=0..5.0) across full footprint + raised cavity perimeter walls (Z=0..wall_h)
    base_block = Part.makeBox(ox, oy, base_h, FreeCAD.Vector(0.0, 0.0, 0.0))
    wall_outer_x = cav_x + 4.0
    wall_outer_y = oy
    walls = Part.makeBox(
        wall_outer_x, wall_outer_y, wall_h,
        FreeCAD.Vector((ox - wall_outer_x) / 2.0, 0.0, 0.0),
    )
    shape = base_block.fuse(walls)

    cav_x0 = (ox - cav_x) / 2.0
    cav_y0 = (oy - cav_y) / 2.0
    pocket = Part.makeBox(cav_x, cav_y, wall_h - base_h + 2.0, FreeCAD.Vector(cav_x0, cav_y0, base_h))
    # Open wire channels on both short ends clearing audio/power wires
    wire_w = 11.0
    wire_slot = Part.makeBox(
        ox + 2.0, wire_w, wall_h - base_h + 2.0,
        FreeCAD.Vector(-1.0, (oy - wire_w) / 2.0, base_h),
    )

    cutters = [pocket, wire_slot]
    for sx in (-1.0, 1.0):
        mx = ox / 2.0 + sx * tenon_span / 2.0
        cutters.append(_make_vaulted_mortise_pocket(mx, oy / 2.0, mort_du, mort_dv, mort_d, z0=0.0))
    shape = shape.cut(Part.makeCompound(cutters))

    # Subtle 0.40 mm 45-deg snap retention ribs on both long inner walls holding the 1.6 mm PAM8403 PCB
    rib_x0 = ox / 2.0 - 6.0
    rib_x1 = ox / 2.0 + 6.0
    rib_z0 = base_h + 1.70  # clears 1.6 mm PCB seated on Z=base_h
    rib_front = _make_snap_rib_x(rib_x0, rib_x1, cav_y0, +1.0, rib_z0, protrude=0.40, land_h=0.40)
    rib_back = _make_snap_rib_x(rib_x0, rib_x1, cav_y0 + cav_y, -1.0, rib_z0, protrude=0.40, land_h=0.40)
    shape = shape.fuse(rib_front).fuse(rib_back).removeSplitter()

    eng_spec = pd_mod.EngraveSpec("SUP08", "PAM8403", ox / 2.0, oy / 2.0, 2.0, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng_spec, base_h, 0.40)

    return shape, {
        "engraved_ok": eng_ok,
        "engrave_text": "SUP08 PAM8403",
        "print_rotation_for_world": "identity",
    }


def _build_speaker_retainer(sup: pd_mod.SupportSpec) -> tuple[Any, dict[str, Any]]:
    pr = sup.params
    L = float(pr["length"])  # 44.0
    W = float(pr["width"])  # 14.0
    bridge_h = float(pr["bridge_h"])  # 9.0
    fh = float(pr["flange_h"])  # 3.0
    span = float(pr["tenon_span"])  # 36.0
    tx = float(pr["tenon_x"])  # 4.0
    ty = float(pr["tenon_y"])  # 6.0
    th = float(pr["tenon_h"])  # 3.0
    spk_od = float(pr["spk_od"])  # 28.4
    spk_d = float(pr["spk_depth"])  # 5.4

    bar = Part.makeBox(L, W, fh, FreeCAD.Vector(0.0, 0.0, 0.0))
    leg_w = (L - spk_od) / 2.0  # 7.8
    leg_l = Part.makeBox(leg_w, W, bridge_h, FreeCAD.Vector(0.0, 0.0, 0.0))
    leg_r = Part.makeBox(leg_w, W, bridge_h, FreeCAD.Vector(L - leg_w, 0.0, 0.0))

    # Center pressure boss supports speaker magnet back (gap bridge_h - boss_h == spk_depth)
    boss_h = round(max(fh + 0.5, bridge_h - spk_d), 2)  # 3.6
    boss = Part.makeCylinder(6.0, boss_h, FreeCAD.Vector(L / 2.0, W / 2.0, 0.0))

    t_l = _make_chamfered_tenon_up(L / 2.0 - span / 2.0, W / 2.0, tx, ty, bridge_h, th)
    t_r = _make_chamfered_tenon_up(L / 2.0 + span / 2.0, W / 2.0, tx, ty, bridge_h, th)
    shape = bar.fuse(leg_l).fuse(leg_r).fuse(boss).fuse(t_l).fuse(t_r).removeSplitter()

    eng_spec = pd_mod.EngraveSpec("SUP09", "", L / 2.0, W / 2.0, 2.0, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng_spec, boss_h, 0.40)

    return shape, {
        "engraved_ok": eng_ok,
        "engrave_text": "SUP09",
        "print_rotation_for_world": "rot_x_90_center_xz",
    }


def _build_door_hinge(sup: pd_mod.SupportSpec) -> tuple[Any, dict[str, Any]]:
    """Two-leaf lift-off mortise pin-and-knuckle hinge printed flat side-by-side (zero overhangs).

    Leaf A (jamb + vertical pin) prints upright on Z=0. Leaf B (door + bore barrel) prints
    upside-down on Z=0 so both plates, tenons, and knuckles sit flat on the bed; flipping
    Leaf B 180 deg in assembly places its barrel cleanly over Leaf A's pin while aligning both
    4x6x3 mm tenons at the exact same Z height (P05 & P08 mortises at Z=18 and Z=86).
    """
    pr = sup.params
    pt = float(pr["plate_t"])  # 3.0
    kod = 6.4  # slightly wider than 6.0 for 1.70 mm wall around 3.0 mm bore
    pin_d = float(pr["pin_d"])  # 2.7
    bore_d = float(pr["bore_d"])  # 3.0
    tx = float(pr["tenon_x"])  # 4.0
    ty = float(pr["tenon_y"])  # 6.0 (vertical along Z in print and world)
    th = float(pr["tenon_h"])  # 3.0 (along -Y into panel mortise)
    knuckle_h = 2.9  # leaves 0.2 mm axial clearance between Leaf A (0..2.9) and Leaf B (3.1..6.0)
    pin_h = 6.2
    plate_w = 7.0

    # --- Leaf A: Jamb leaf (world X=69.5..76.5, tenon center X=72.5, pivot X=77.0, Y=201.5) ---
    # Pivot sits at Y = th + pt + kod/2 + 0.3 = 9.5 so cylindrical barrel (Y=6.3..12.7) strictly clears both plates (Y=3..6)!
    plate_a = Part.makeBox(plate_w, pt, ty, FreeCAD.Vector(0.0, th, 0.0))
    tenon_a = Part.makeBox(tx, th + 0.5, ty, FreeCAD.Vector(1.0, 0.0, 0.0))
    pivot_ax, pivot_ay = 7.5, th + pt + kod / 2.0 + 0.3  # (7.5, 9.5) -> 0.3 mm clear behind plate Y=6.0
    knuckle_a = Part.makeCylinder(kod / 2.0, knuckle_h, FreeCAD.Vector(pivot_ax, pivot_ay, 0.0))
    bridge_a = Part.makeBox(3.5, pivot_ay - th, knuckle_h, FreeCAD.Vector(4.0, th, 0.0))
    pin_shaft = Part.makeCylinder(pin_d / 2.0, pin_h - 0.3, FreeCAD.Vector(pivot_ax, pivot_ay, 0.0))
    pin_tip = Part.makeCone(pin_d / 2.0, pin_d / 2.0 - 0.3, 0.35, FreeCAD.Vector(pivot_ax, pivot_ay, pin_h - 0.35))
    leaf_a = plate_a.fuse(tenon_a).fuse(knuckle_a).fuse(bridge_a).fuse(pin_shaft).fuse(pin_tip).removeSplitter()

    eng_a = pd_mod.EngraveSpec("10A", "", 3.5, th + pt / 2.0, 1.6, False)
    leaf_a, ok_a = cc.safe_engrave_top_face(leaf_a, eng_a, ty, 0.35)

    # --- Leaf B: Door leaf (world X=79.5..86.5, tenon center X=83.5, pivot X=77.0, Y=201.5) ---
    bx_off = 14.5  # clear bed spacing between Leaf A and Leaf B
    bx_piv = bx_off + 9.5
    plate_b = Part.makeBox(plate_w, pt, ty, FreeCAD.Vector(bx_piv - 9.5, th, 0.0))
    tenon_b = Part.makeBox(tx, th + 0.5, ty, FreeCAD.Vector(bx_piv - 8.5, 0.0, 0.0))
    knuckle_b = Part.makeCylinder(kod / 2.0, knuckle_h, FreeCAD.Vector(bx_piv, pivot_ay, 0.0))
    bridge_b = Part.makeBox(4.0, pivot_ay - th, knuckle_h, FreeCAD.Vector(bx_piv - 4.0, th, 0.0))
    bore_b = Part.makeCylinder(bore_d / 2.0, knuckle_h + 2.0, FreeCAD.Vector(bx_piv, pivot_ay, -1.0))
    leaf_b = plate_b.fuse(tenon_b).fuse(knuckle_b).fuse(bridge_b).cut(bore_b).removeSplitter()

    eng_b = pd_mod.EngraveSpec("10B", "", bx_piv - 6.0, th + pt / 2.0, 1.6, False)
    leaf_b, ok_b = cc.safe_engrave_top_face(leaf_b, eng_b, ty, 0.35)

    compound = Part.makeCompound([leaf_a, leaf_b])
    return compound, {
        "engraved_ok": bool(ok_a and ok_b),
        "engrave_text": "10A | 10B",
        "print_rotation_for_world": "split_2_leaves_leafA_identity_leafB_rot_y_180",
        "expected_solids": 2,
    }


def _build_servo_link_clip(sup: pd_mod.SupportSpec) -> tuple[Any, dict[str, Any]]:
    """Flat-printed linkage clip: tenon, base, and clevis arm all start on Z=0 for zero overhang."""
    pr = sup.params
    bx = float(pr["base_x"])  # 10.0
    bt = float(pr["base_t"])  # 3.0
    tx = float(pr["tenon_x"])  # 4.0
    ty = float(pr["tenon_y"])  # 6.0 (Z height in print & world)
    th = float(pr["tenon_h"])  # 3.0 (along -Y into P08)
    hole_d = float(pr["link_hole_d"])  # 1.8 mm pushrod wire eye (not a screw)
    base_h = 9.0
    arm_t = 3.5
    arm_w = 6.0
    eye_cy = th + bt + 4.0  # 10.0

    base = Part.makeBox(bx, bt, base_h, FreeCAD.Vector(0.0, th, 0.0))
    tenon = Part.makeBox(tx, th + 0.5, ty, FreeCAD.Vector((bx - tx) / 2.0, 0.0, 0.0))
    arm_rect = Part.makeBox(arm_w, 4.5, arm_t, FreeCAD.Vector((bx - arm_w) / 2.0, th + bt - 0.5, 0.0))
    arm_tip = Part.makeCylinder(arm_w / 2.0, arm_t, FreeCAD.Vector(bx / 2.0, eye_cy, 0.0))
    eye_hole = Part.makeCylinder(hole_d / 2.0, arm_t + 2.0, FreeCAD.Vector(bx / 2.0, eye_cy, -1.0))

    shape = base.fuse(tenon).fuse(arm_rect).fuse(arm_tip).cut(eye_hole).removeSplitter()

    eng_spec = pd_mod.EngraveSpec("10B", "", bx / 2.0, th + bt / 2.0, 1.6, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng_spec, base_h, 0.35)

    return shape, {
        "engraved_ok": eng_ok,
        "engrave_text": "10B",
        "print_rotation_for_world": "identity",
    }


def _build_sg90_saddle(sup: pd_mod.SupportSpec) -> tuple[Any, dict[str, Any]]:
    """Inverted SG90 retention saddle with center gearbox cutout & 2 integral mortise tenons."""
    pr = sup.params
    # 18.0 mm width gives 2.6 mm side rails flanking the 12.8x23.6 mm SG90 gearbox cutout (fits 34mm P07 shelf)
    wx = 18.0
    ly = float(pr["length_y"])  # 42.0
    bridge_t = 3.0
    ear_t = float(pr["ear_t"])  # 2.6 mm matching 2.5 mm SG90 mounting ears + 0.1 mm clearance
    leg_top_z = bridge_t + ear_t  # 5.6
    tx = float(pr["tenon_x"])  # 6.0
    th = float(pr["tenon_h"])  # 3.0

    # Top bridge on Z=0..3.0 with open center window clearing SG90 gearbox/horn (12.8 x 23.6 mm)
    bridge = Part.makeBox(wx, ly, bridge_t, FreeCAD.Vector(0.0, 0.0, 0.0))
    gb_x, gb_y = 12.8, 23.6
    gb_cut = Part.makeBox(
        gb_x, gb_y, bridge_t + 2.0,
        FreeCAD.Vector((wx - gb_x) / 2.0, (ly - gb_y) / 2.0, -1.0),
    )

    # End legs clear the 32.2 mm SG90 ear span (inner span 32.5 mm: Y=0..4.75 and Y=37.25..42.0)
    leg_y_len = 4.75
    leg_f = Part.makeBox(wx, leg_y_len, leg_top_z, FreeCAD.Vector(0.0, 0.0, 0.0))
    leg_r = Part.makeBox(wx, leg_y_len, leg_top_z, FreeCAD.Vector(0.0, ly - leg_y_len, 0.0))

    # Integral tenons (6.0 x 2.4 x 3.0 mm) sit squarely atop end legs (zero overhang) and fit P07 3.30 mm mortises
    ten_y = 2.40
    t_f = _make_chamfered_tenon_up(wx / 2.0, leg_y_len - ten_y / 2.0, tx, ten_y, leg_top_z, th)
    t_r = _make_chamfered_tenon_up(wx / 2.0, ly - leg_y_len + ten_y / 2.0, tx, ten_y, leg_top_z, th)

    shape = bridge.cut(gb_cut).fuse(leg_f).fuse(leg_r).fuse(t_f).fuse(t_r).removeSplitter()

    # Engrave on flat ear-clamping deck between leg_f (Y=4.75) and gearbox cutout (Y=9.2)
    eng_spec = pd_mod.EngraveSpec("SUP11", "", wx / 2.0, 7.0, 1.8, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng_spec, bridge_t, 0.40)

    return shape, {
        "engraved_ok": eng_ok,
        "engrave_text": "SUP11",
        "print_rotation_for_world": "rot_x_180",
    }


def _build_wall_cradle(sup: pd_mod.SupportSpec) -> tuple[Any, dict[str, Any]]:
    """Inverted sensor snap-cradle (SUP12 DHT11, SUP13 KY-037, SUP14 LM393) with 2 integral tenons."""
    pr = sup.params
    ox, oy, _oz = sup.size_xyz
    cav_x = float(pr["cavity_x"])
    cav_y = float(pr["cavity_y"])
    win_x = float(pr["window_x"])
    win_y = float(pr["window_y"])
    depth_h = float(pr["depth_h"])  # 8.0
    frame_t = 2.2
    span = float(pr["tenon_span"])
    tx = float(pr["tenon_x"])  # 3.0
    ty = float(pr["tenon_y"])  # 6.0
    th = float(pr["tenon_h"])  # 3.0

    outer = Part.makeBox(ox, oy, depth_h, FreeCAD.Vector(0.0, 0.0, 0.0))
    cav_x0 = (ox - cav_x) / 2.0
    cav_y0 = (oy - cav_y) / 2.0
    pocket = Part.makeBox(cav_x, cav_y, depth_h - frame_t + 2.0, FreeCAD.Vector(cav_x0, cav_y0, frame_t))
    # Open +Y end wall so sensor slides in cleanly and Dupont wires exit freely
    open_end = Part.makeBox(cav_x, oy - cav_y0 + 1.0, depth_h - frame_t + 2.0, FreeCAD.Vector(cav_x0, oy - 3.0, frame_t))
    window = Part.makeBox(
        win_x, win_y, frame_t + 2.0,
        FreeCAD.Vector((ox - win_x) / 2.0, (oy - win_y) / 2.0, -1.0),
    )

    shape = outer.cut(Part.makeCompound([pocket, open_end, window]))

    t_l = _make_chamfered_tenon_up(ox / 2.0 - span / 2.0, oy / 2.0, tx, ty, depth_h, th)
    t_r = _make_chamfered_tenon_up(ox / 2.0 + span / 2.0, oy / 2.0, tx, ty, depth_h, th)
    shape = shape.fuse(t_l).fuse(t_r).removeSplitter()

    # Choose flat interior ledge outside the window on Z = frame_t
    if sup.part_id == "SUP12_DHT11_SNAP_CRADLE":
        eng_spec = pd_mod.EngraveSpec("SUP12", "", ox / 2.0, 5.1, 2.0, False)
        rot_hint = "rot_x_-90"
    elif sup.part_id == "SUP13_KY037_SNAP_CRADLE":
        eng_spec = pd_mod.EngraveSpec("SUP13", "", 10.6, oy / 2.0, 1.9, True)
        rot_hint = "rot_x_90"
    else:
        eng_spec = pd_mod.EngraveSpec("SUP14", "", 9.4, oy / 2.0, 1.9, True)
        rot_hint = "rot_x_-90"

    shape, eng_ok = cc.safe_engrave_top_face(shape, eng_spec, frame_t, 0.40)

    return shape, {
        "engraved_ok": eng_ok,
        "engrave_text": eng_spec.line1,
        "print_rotation_for_world": rot_hint,
    }


def _build_water_liner(sup: pd_mod.SupportSpec) -> tuple[Any, dict[str, Any]]:
    pr = sup.params
    ox = float(pr["outer_x"])  # 46.5
    oy = float(pr["outer_y"])  # 119.0
    oz = float(pr["outer_z"])  # 45.0
    wt = float(pr["wall_t"])  # 2.0
    ft = float(pr["floor_t"])  # 2.4
    ny = float(pr["tube_notch_y"])  # 59.5
    nw = float(pr["tube_notch_w"])  # 11.0
    nz0 = float(pr["tube_notch_z0"])  # 34.0

    outer = Part.makeBox(ox, oy, oz, FreeCAD.Vector(0.0, 0.0, 0.0))
    cavity = Part.makeBox(ox - 2.0 * wt, oy - 2.0 * wt, oz - ft + 2.0, FreeCAD.Vector(wt, wt, ft))
    notch = Part.makeBox(wt + 3.0, nw, oz - nz0 + 2.0, FreeCAD.Vector(ox - wt - 1.5, ny - nw / 2.0, nz0))
    shape = outer.cut(Part.makeCompound([cavity, notch])).removeSplitter()

    shape, eng_ok = cc.safe_engrave_top_face(shape, sup.engrave, ft, 0.50)

    return shape, {
        "engraved_ok": eng_ok,
        "engrave_text": f"{sup.engrave.line1} {sup.engrave.line2}".strip(),
        "print_rotation_for_world": "identity",
    }


def build_mount_solid(sup: pd_mod.SupportSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, dict[str, Any]]:
    """Build exact BRep solid for one screwless support/mount, normalized flat on X=Y=Z=0."""
    cat = sup.category
    if cat == "corner_clip":
        shape, extra = _build_corner_clip(sup)
    elif cat == "t_clip":
        shape, extra = _build_t_clip(sup)
    elif cat == "seam_clip":
        shape, extra = _build_seam_clip(sup)
    elif cat == "foot_clip":
        shape, extra = _build_foot_clip(sup)
    elif cat == "tenon_riser":
        shape, extra = _build_tenon_riser(sup)
    elif cat == "tenon_peg":
        shape, extra = _build_tenon_peg(sup)
    elif cat == "pcb_carrier":
        shape, extra = _build_pcb_carrier(sup, cfg)
    elif cat == "relay_caddy":
        shape, extra = _build_relay_caddy(sup, cfg)
    elif cat == "pam_tray":
        shape, extra = _build_pam_tray(sup, cfg)
    elif cat == "speaker_retainer":
        shape, extra = _build_speaker_retainer(sup)
    elif cat == "door_hinge":
        shape, extra = _build_door_hinge(sup)
    elif cat == "servo_link_clip":
        shape, extra = _build_servo_link_clip(sup)
    elif cat == "sg90_saddle":
        shape, extra = _build_sg90_saddle(sup)
    elif cat == "wall_cradle":
        shape, extra = _build_wall_cradle(sup)
    elif cat == "water_liner":
        shape, extra = _build_water_liner(sup)
    else:
        raise ValueError(f"Unsupported support category: {cat}")

    bb = shape.BoundBox
    shape.translate(FreeCAD.Vector(-bb.XMin, -bb.YMin, -bb.ZMin))
    bb = shape.BoundBox
    bbox_mm = [round(bb.XLength, 3), round(bb.YLength, 3), round(bb.ZLength, 3)]

    expected_solids = int(extra.pop("expected_solids", 1))
    solids_count = len(shape.Solids)
    valid_solids = bool(shape.isValid()) and all(s.isValid() and s.Volume > 1e-3 for s in shape.Solids)

    meta: dict[str, Any] = {
        "part_id": sup.part_id,
        "kind": "support",
        "category": sup.category,
        "qty": sup.qty,
        "vi_name": sup.vi_name,
        "mating_source": sup.mating_source,
        "params": dict(sup.params),
        "assembly_placements": [dict(p) for p in sup.assembly_placements],
        "print_bbox_mm": bbox_mm,
        "print_z_min": round(bb.ZMin, 4),
        "volume_mm3": round(float(shape.Volume), 3),
        "solids": solids_count,
        "expected_solids": expected_solids,
        "valid": valid_solids,
        "bed_fit": cc.fits_bed_rotatable(bbox_mm, cfg),
        "color_rgb": list(sup.color_rgb),
        "notes": sup.notes,
        **extra,
    }
    return shape, meta


def parse_args() -> argparse.Namespace:
    argv = sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = [a for a in argv if not a.endswith(".py")]
    ap = argparse.ArgumentParser(description="Build 18 screwless mounts/clips (3D-Print Set v2)")
    ap.add_argument("--parts", type=str, default=os.environ.get("PRINT3D_PARTS", ""), help="Comma-separated part_ids")
    args, _ = ap.parse_known_args(argv)
    return args


def main() -> int:
    t0 = time.time()
    args = parse_args()
    cfg = pd_mod.PrintConfig()
    pcb = pcb_ssot.parse_kicad_hub_pcb(run_cli_check=False)
    supports = pd_mod.build_support_specs(cfg, pcb)

    target_ids: set[str] | None = None
    if args.parts:
        target_ids = {s.strip() for s in args.parts.split(",") if s.strip()}

    built = 0
    failures: list[str] = []
    for sup in supports:
        if target_ids is not None and sup.part_id not in target_ids:
            continue
        shape, meta = build_mount_solid(sup, cfg)
        step_p, stl_p, facets = cc.export_part_step_stl(shape, sup.part_id, linear_deflection=0.04)
        meta["step_file"] = f"parts/{step_p.name}"
        meta["stl_file"] = f"parts/{stl_p.name}"
        meta["stl_facets"] = facets
        cc.save_part_meta(sup.part_id, meta)

        ok = bool(
            meta["valid"]
            and meta["solids"] == meta["expected_solids"]
            and meta["bed_fit"]
            and abs(meta["print_z_min"]) <= 0.005
        )
        status = "OK" if ok else "FAIL"
        print(
            f"[{status}] {sup.part_id:28s} bbox={meta['print_bbox_mm']} "
            f"solids={meta['solids']} vol={meta['volume_mm3']:8.1f} "
            f"eng={meta['engraved_ok']} facets={facets}",
            flush=True,
        )
        if not ok:
            failures.append(sup.part_id)
        built += 1

    print(f"DONE: built {built}/{len(supports)} mounts in {time.time() - t0:.2f}s (failures={len(failures)})", flush=True)
    return 1 if failures else 0


if __name__ == "__main__" or any(pathlib.Path(a).stem == __name__ for a in sys.argv):
    rc = main()
    if rc != 0:
        raise SystemExit(rc)
