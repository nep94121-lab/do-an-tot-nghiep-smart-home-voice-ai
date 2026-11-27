"""FreeCAD 1.1 CAD builder for 3D-Print Set v2 house-scale furniture (FUR01..FUR09).

Generates all 9 support-free, floor-pegged furniture items directly into:
  - hardware/in 3 d/parts/FUR*.step
  - hardware/in 3 d/parts/FUR*.stl
  - hardware/in 3 d/build_meta/FUR*.json

Run headlessly with FreeCAD 1.1:
  "C:\\Users\\LENOVO\\AppData\\Local\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe" "hardware/in 3 d/scripts/build_furniture_v2.py"
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
import print_domain as pd_mod


# Standard underside floor mortise socket for FUR09_FLOOR_TENON_PEG (6.0x4.0x7.0 mm)
FLOOR_SOCK_X = 6.30
FLOOR_SOCK_Y = 4.30
FLOOR_SOCK_Z = 4.20


def _vec(x: float, y: float, z: float) -> FreeCAD.Vector:
    return FreeCAD.Vector(float(x), float(y), float(z))


def _box(x0: float, y0: float, z0: float, dx: float, dy: float, dz: float) -> Any:
    return Part.makeBox(float(dx), float(dy), float(dz), _vec(x0, y0, z0))


def _chamfered_rect_wire(
    cx: float, cy: float, sx: float, sy: float, c: float, z: float
) -> Any:
    """Closed 8-vertex chamfered rectangle wire at height Z (consistent CCW order)."""
    hx = sx / 2.0
    hy = sy / 2.0
    c = max(0.05, min(c, hx - 0.1, hy - 0.1))
    pts = [
        _vec(cx - hx + c, cy - hy, z),
        _vec(cx + hx - c, cy - hy, z),
        _vec(cx + hx, cy - hy + c, z),
        _vec(cx + hx, cy + hy - c, z),
        _vec(cx + hx - c, cy + hy, z),
        _vec(cx - hx + c, cy + hy, z),
        _vec(cx - hx, cy + hy - c, z),
        _vec(cx - hx, cy - hy + c, z),
    ]
    pts.append(pts[0])
    return Part.makePolygon(pts)


def _rect_wire(cx: float, cy: float, sx: float, sy: float, z: float) -> Any:
    hx = sx / 2.0
    hy = sy / 2.0
    pts = [
        _vec(cx - hx, cy - hy, z),
        _vec(cx + hx, cy - hy, z),
        _vec(cx + hx, cy + hy, z),
        _vec(cx - hx, cy + hy, z),
        _vec(cx - hx, cy - hy, z),
    ]
    return Part.makePolygon(pts)


def _reg_poly_wire(
    cx: float, cy: float, r: float, n: int, z: float, angle_offset_deg: float = 0.0
) -> Any:
    pts = []
    a0 = math.radians(angle_offset_deg)
    for i in range(n):
        ang = a0 + 2.0 * math.pi * i / n
        pts.append(_vec(cx + r * math.cos(ang), cy + r * math.sin(ang), z))
    pts.append(pts[0])
    return Part.makePolygon(pts)


def _loft_sections(wires: list[Any]) -> Any:
    """Build a watertight ruled solid loft from stacked horizontal wires."""
    return Part.makeLoft(wires, True, True)


def _poly2d_extrude_z(pts_xy: list[tuple[float, float]], z0: float, dz: float) -> Any:
    pts = [_vec(x, y, z0) for x, y in pts_xy]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    wire = Part.makePolygon(pts)
    face = Part.Face(wire)
    return face.extrude(_vec(0.0, 0.0, dz))


def _poly_yz_extrude_x(pts_yz: list[tuple[float, float]], x0: float, dx: float) -> Any:
    pts = [_vec(x0, y, z) for y, z in pts_yz]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    wire = Part.makePolygon(pts)
    face = Part.Face(wire)
    return face.extrude(_vec(dx, 0.0, 0.0))


def _poly_xz_extrude_y(pts_xz: list[tuple[float, float]], y0: float, dy: float) -> Any:
    pts = [_vec(x, y0, z) for x, z in pts_xz]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    wire = Part.makePolygon(pts)
    face = Part.Face(wire)
    return face.extrude(_vec(0.0, dy, 0.0))


def _clean_solid(shape: Any) -> Any:
    try:
        cleaned = shape.removeSplitter()
        if cleaned.isValid() and len(cleaned.Solids) == len(shape.Solids) and cleaned.Volume > shape.Volume * 0.99:
            return cleaned
    except Exception:
        pass
    return shape


def _cut_floor_sockets(
    shape: Any,
    centers_xy: list[tuple[float, float]],
    sock_x: float = FLOOR_SOCK_X,
    sock_y: float = FLOOR_SOCK_Y,
    sock_z: float = FLOOR_SOCK_Z,
) -> Any:
    """Cut underside rectangular floor mortise sockets upward from Z = 0."""
    cur = shape
    for cx, cy in centers_xy:
        # Start 0.2 mm below Z = 0 so OCCT boolean produces a clean open bottom face
        cutter = _box(cx - sock_x / 2.0, cy - sock_y / 2.0, -0.2, sock_x, sock_y, sock_z + 0.2)
        cur = cur.cut(cutter)
    return cur


# ---------------------------------------------------------------------------
# Individual Furniture Builders (FUR01..FUR09)
# ---------------------------------------------------------------------------


def build_fur01_sofa(fur: pd_mod.FurnitureSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, bool, str, dict[str, Any]]:
    """FUR01_SOFA (76 x 34 x 34 mm): 3-seat living room sofa, printed upright on Z=0."""
    W = float(fur.params["width_x"])  # 76.0
    D = float(fur.params["depth_y"])  # 34.0
    H = float(fur.params["height_z"])  # 34.0
    seat_h = float(fur.params["seat_h"])  # 14.0
    arm_w = float(fur.params["arm_w"])  # 8.0
    back_t = float(fur.params["back_t"])  # 8.0
    arm_h = 22.0
    span_x = float(fur.params["peg_span_x"])  # 44.0

    # Solid seat & base block
    base = _box(0.0, 0.0, 0.0, W, D, seat_h)

    # Armrests (X=0..8 and X=68..76, height 22 mm) with 1.5 mm top inner/outer chamfers
    arm_prof_l = [
        (0.0, seat_h - 1.0),
        (arm_w, seat_h - 1.0),
        (arm_w, arm_h - 1.5),
        (arm_w - 1.5, arm_h),
        (1.5, arm_h),
        (0.0, arm_h - 1.5),
    ]
    arm_l = _poly_xz_extrude_y(arm_prof_l, 0.0, D)
    arm_prof_r = [(W - x, z) for x, z in reversed(arm_prof_l)]
    arm_r = _poly_xz_extrude_y(arm_prof_r, 0.0, D)

    # Backrest (Y=26..34, height 34 mm) with gentle front & rear top bevels
    back_y0 = D - back_t  # 26.0
    back_prof = [
        (back_y0, seat_h - 1.0),
        (D, seat_h - 1.0),
        (D, H - 1.2),
        (D - 1.2, H),
        (back_y0 + 2.0, H),
        (back_y0, H - 2.0),
    ]
    back = _poly_yz_extrude_x(back_prof, 0.0, W)

    shape = base.fuse(arm_l).fuse(arm_r).fuse(back)
    shape = _clean_solid(shape)

    # Sculpt 3 seat cushions with shallow 0.8 mm V/rectangular seams at X = 28 and X = 48
    seat_inner_w = W - 2.0 * arm_w  # 60.0
    seam_xs = [arm_w + seat_inner_w / 3.0, arm_w + 2.0 * seat_inner_w / 3.0]  # 28.0, 48.0
    for sx in seam_xs:
        # Seat top seam groove (0.8 mm deep, 1.4 mm wide at top tapering to 0.4 mm)
        groove_seat = _poly_xz_extrude_y(
            [(sx - 0.7, seat_h + 0.2), (sx + 0.7, seat_h + 0.2), (sx + 0.2, seat_h - 0.8), (sx - 0.2, seat_h - 0.8)],
            -0.2,
            back_y0 + 0.4,
        )
        shape = shape.cut(groove_seat)

        # Backrest front face cushion seam (0.8 mm deep on Y = back_y0, 45-deg self-supporting top)
        groove_back = _poly_yz_extrude_x(
            [(back_y0 - 0.2, seat_h - 0.2), (back_y0 + 0.8, seat_h - 0.2), (back_y0 + 0.8, H - 3.5), (back_y0 - 0.2, H - 2.5)],
            sx - 0.6,
            1.2,
        )
        shape = shape.cut(groove_back)

    # Front cushion separation V-groove (45-deg self-supporting, 0.7 mm deep at Z = 8.5)
    front_v = _poly_yz_extrude_x(
        [(-0.2, 7.6), (0.7, 8.5), (-0.2, 9.4)],
        arm_w,
        seat_inner_w,
    )
    shape = shape.cut(front_v)

    # 2 underside floor mortise sockets at X = 38 +/- 22 = 16, 60; Y = 17
    shape = _cut_floor_sockets(shape, [(W / 2.0 - span_x / 2.0, D / 2.0), (W / 2.0 + span_x / 2.0, D / 2.0)])

    # Engrave "FUR01 SOFA" cleanly inside center seat cushion (X=28..48, Y=0..26, Z=14)
    eng = pd_mod.EngraveSpec("FUR01", "SOFA", W / 2.0, back_y0 / 2.0, 2.5, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng, seat_h, 0.50)

    extra = {
        "print_rotation_for_world": "identity",
        "floor_sockets_local_xy": [[round(W / 2.0 - span_x / 2.0, 3), round(D / 2.0, 3)], [round(W / 2.0 + span_x / 2.0, 3), round(D / 2.0, 3)]],
    }
    return shape, eng_ok, "FUR01 SOFA", extra


def build_fur02_tv_stand(fur: pd_mod.FurnitureSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, bool, str, dict[str, Any]]:
    """FUR02_TV_STAND (56 x 22 x 18 mm): media console with top TV mortise & 2 floor sockets."""
    W = float(fur.params["width_x"])  # 56.0
    D = float(fur.params["depth_y"])  # 22.0
    H = float(fur.params["height_z"])  # 18.0
    span_x = float(fur.params["peg_span_x"])  # 32.0
    tv_sx = float(fur.params["tv_slot_x"])  # 24.30
    tv_sy = float(fur.params["tv_slot_y"])  # 4.30
    tv_sd = 5.20  # 5.2 mm deep to clear 5.0 mm tenon bottom

    shape = _box(0.0, 0.0, 0.0, W, D, H)

    # Decorative front shelf recess on Y = D (faces -X living room after rot_z=90)
    # 2.0 mm deep with 45-deg sloped upper ceiling so overhang <= 45 deg (zero bridge!)
    shelf_prof = [
        (D + 0.2, 5.0),
        (D - 2.0, 5.0),
        (D - 2.0, 12.0),
        (D + 0.2, 14.2),
    ]
    shelf_cut = _poly_yz_extrude_x(shelf_prof, 15.0, 26.0)
    shape = shape.cut(shelf_cut)

    # Left & right decorative cabinet door vertical seams + 45-deg horizontal V-groove handles on front Y = D
    for gx in (13.2, 42.8):
        vseam = _poly_yz_extrude_x(
            [(D + 0.2, 2.0), (D - 0.8, 2.0), (D - 0.8, H - 3.0), (D + 0.2, H - 2.0)],
            gx - 0.4,
            0.8,
        )
        shape = shape.cut(vseam)
    for hx0 in (4.5, 45.5):
        handle_v = _poly_yz_extrude_x(
            [(D + 0.2, 11.6), (D - 0.8, 12.6), (D + 0.2, 13.6)],
            hx0,
            6.0,
        )
        shape = shape.cut(handle_v)

    # Top center mortise slot for FUR03_TV_SCREEN (24.30 x 4.30 x 5.2 mm deep from Z=18 down)
    tv_slot = _box(W / 2.0 - tv_sx / 2.0, D / 2.0 - tv_sy / 2.0, H - tv_sd, tv_sx, tv_sy, tv_sd + 0.2)
    shape = shape.cut(tv_slot)

    # 2 underside floor mortise sockets at X = 28 +/- 16 = 12, 44; Y = 11
    shape = _cut_floor_sockets(shape, [(W / 2.0 - span_x / 2.0, D / 2.0), (W / 2.0 + span_x / 2.0, D / 2.0)])

    # Engrave "FUR02 TV" cleanly on flat top deck beside slot (Y = 17.6, between slot Y=13.15 and front Y=22)
    eng = pd_mod.EngraveSpec("FUR02 TV", "", W / 2.0, 17.6, 2.5, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng, H, 0.45)

    extra = {
        "print_rotation_for_world": "identity",
        "tv_slot_local_mm": [tv_sx, tv_sy, tv_sd],
        "floor_sockets_local_xy": [[round(W / 2.0 - span_x / 2.0, 3), round(D / 2.0, 3)], [round(W / 2.0 + span_x / 2.0, 3), round(D / 2.0, 3)]],
    }
    return shape, eng_ok, "FUR02 TV", extra


def build_fur03_tv_screen(fur: pd_mod.FurnitureSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, bool, str, dict[str, Any]]:
    """FUR03_TV_SCREEN (48 x 35 x 5 mm): flat-screen TV printed FLAT on rear face (Z=0..5)."""
    sw = float(fur.params["screen_w"])  # 48.0
    sh = float(fur.params["screen_h"])  # 28.0
    st = float(fur.params["screen_t"])  # 5.0
    bezel = float(fur.params["bezel_w"])  # 2.5
    rec_d = float(fur.params["recess_d"])  # 1.2
    nw = float(fur.params["neck_w"])  # 24.0
    nh = float(fur.params["neck_h"])  # 7.0
    tt = float(fur.params["tenon_t"])  # 4.0

    # Screen body: X=0..48, Y=7..35, Z=0..5
    screen = _box(0.0, nh, 0.0, sw, sh, st)

    # Integral stand neck/tenon: X=12..36, Y=0..7 (+1 mm overlap into screen), Z=0..4
    nx0 = (sw - nw) / 2.0  # 12.0
    # Slight 0.4 mm lead-in bevel at Y=0 left/right edges for easy insertion into FUR02 slot
    neck_pts = [
        (nx0 + 0.4, 0.0),
        (nx0 + nw - 0.4, 0.0),
        (nx0 + nw, 0.4),
        (nx0 + nw, nh + 1.0),
        (nx0, nh + 1.0),
        (nx0, 0.4),
    ]
    neck = _poly2d_extrude_z(neck_pts, 0.0, tt)

    shape = _clean_solid(screen.fuse(neck))

    # Cut recessed display screen face (1.2 mm deep from Z=5.0 down to Z=3.8)
    recess = _box(bezel, nh + bezel, st - rec_d, sw - 2.0 * bezel, sh - 2.0 * bezel, rec_d + 0.2)
    shape = shape.cut(recess)

    # Engrave "FUR03 TV" cleanly on recessed screen face at Z = 3.8
    eng = pd_mod.EngraveSpec("FUR03", "TV", sw / 2.0, nh + sh / 2.0, 3.2, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng, st - rec_d, 0.50)

    extra = {
        "print_rotation_for_world": "rot_x_90",
        "front_face_local": "+Z",
        "tenon_origin_local_mm": [round(sw / 2.0, 3), 0.0, round(tt / 2.0, 3)],
        "tenon_size_mm": [nw, nh, tt],
    }
    return shape, eng_ok, "FUR03 TV", extra


def build_fur04_bed(fur: pd_mod.FurnitureSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, bool, str, dict[str, Any]]:
    """FUR04_BED (90 x 62 x 28 mm): bedroom double bed with headboard, pillows, blanket step, 2 floor sockets."""
    W = float(fur.params["width_x"])  # 90.0
    D = float(fur.params["depth_y"])  # 62.0
    matt_h = float(fur.params["mattress_h"])  # 15.0
    hb_h = float(fur.params["headboard_h"])  # 28.0
    hb_t = float(fur.params["headboard_t"])  # 6.0
    pil_h = float(fur.params["pillow_h"])  # 4.0
    span_x = float(fur.params["peg_span_x"])  # 56.0

    # Frame & mattress (Z = 0..15)
    mattress = _box(0.0, 0.0, 0.0, W, D, matt_h)

    # Blanket fold step (+1.0 mm raised blanket layer at Y = 0..38 with chamfered fold edge)
    blanket_y = 38.0
    blanket_h = 1.0
    blanket_prof = [
        (0.0, matt_h - 0.5),
        (blanket_y, matt_h - 0.5),
        (blanket_y, matt_h + 0.2),
        (blanket_y - 0.8, matt_h + blanket_h),
        (0.8, matt_h + blanket_h),
        (0.0, matt_h + 0.2),
    ]
    blanket = _poly_yz_extrude_x(blanket_prof, 0.0, W)

    # Headboard (Y = 56..62, Z = 0..28) with 1.5 mm top chamfers
    hb_y0 = D - hb_t  # 56.0
    hb_prof = [
        (hb_y0, matt_h - 1.0),
        (D, matt_h - 1.0),
        (D, hb_h - 1.5),
        (D - 1.5, hb_h),
        (hb_y0 + 1.5, hb_h),
        (hb_y0, hb_h - 1.5),
    ]
    headboard = _poly_yz_extrude_x(hb_prof, 0.0, W)

    # 2 sculpted raised pillows (30 x 14 x 4 mm on Z = 15..19 with 45-deg chamfered top edges)
    pil_w, pil_d = 30.0, 14.0
    pil_cy = 47.0  # spans Y = 40..54 (2 mm clear of blanket Y=38 and headboard Y=56)
    pillows: list[Any] = []
    for pil_cx in (26.0, 64.0):
        w_bot = _chamfered_rect_wire(pil_cx, pil_cy, pil_w, pil_d, 2.0, matt_h - 0.4)
        w_mid = _chamfered_rect_wire(pil_cx, pil_cy, pil_w, pil_d, 2.0, matt_h + pil_h - 1.8)
        w_top = _chamfered_rect_wire(pil_cx, pil_cy, pil_w - 3.6, pil_d - 3.6, 1.4, matt_h + pil_h)
        pillows.append(_loft_sections([w_bot, w_mid, w_top]))

    shape = mattress.fuse(blanket).fuse(headboard).fuse(pillows[0]).fuse(pillows[1])
    shape = _clean_solid(shape)

    # Subtle decorative vertical headboard grooves on front face Y = 56 (45-deg self-supporting top)
    for gx in (18.0, 36.0, 54.0, 72.0):
        g = _poly_yz_extrude_x(
            [(hb_y0 - 0.2, matt_h + 1.5), (hb_y0 + 0.6, matt_h + 1.5), (hb_y0 + 0.6, hb_h - 3.0), (hb_y0 - 0.2, hb_h - 2.2)],
            gx - 0.4,
            0.8,
        )
        shape = shape.cut(g)

    # 2 underside floor mortise sockets at X = 45 +/- 28 = 17, 73; Y = 31
    shape = _cut_floor_sockets(shape, [(W / 2.0 - span_x / 2.0, D / 2.0), (W / 2.0 + span_x / 2.0, D / 2.0)])

    # Engrave "FUR04 BED" cleanly on flat blanket top (Z = 16.0, X=0..90, Y=0..38)
    eng = pd_mod.EngraveSpec("FUR04", "BED", W / 2.0, blanket_y / 2.0, 3.8, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng, matt_h + blanket_h, 0.55)

    extra = {
        "print_rotation_for_world": "identity",
        "floor_sockets_local_xy": [[round(W / 2.0 - span_x / 2.0, 3), round(D / 2.0, 3)], [round(W / 2.0 + span_x / 2.0, 3), round(D / 2.0, 3)]],
    }
    return shape, eng_ok, "FUR04 BED", extra


def build_fur05_bedside_table(fur: pd_mod.FurnitureSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, bool, str, dict[str, Any]]:
    """FUR05_BEDSIDE_TABLE (26 x 22 x 28 mm): nightstand + 45-deg self-supporting bedside lamp."""
    W = float(fur.params["width_x"])  # 26.0
    D = float(fur.params["depth_y"])  # 22.0
    tab_h = float(fur.params["table_h"])  # 18.0
    lamp_h = float(fur.params["lamp_h"])  # 10.0

    table = _box(0.0, 0.0, 0.0, W, D, tab_h)

    # Stylized self-supporting octagonal bedside lamp (Z = 18..28, max outward slope = 43 deg <= 45 deg)
    # Positioned slightly toward back (Y = 14.8) so front flat deck (Y = 0..9.6) holds crisp engraving
    lcx, lcy = W / 2.0, 14.8
    lamp_wires = [
        _reg_poly_wire(lcx, lcy, 4.2, 8, tab_h - 0.5, 22.5),
        _reg_poly_wire(lcx, lcy, 4.2, 8, tab_h + 0.8, 22.5),
        _reg_poly_wire(lcx, lcy, 2.3, 8, tab_h + 2.6, 22.5),  # tapers in (0 deg overhang)
        _reg_poly_wire(lcx, lcy, 5.1, 8, tab_h + 5.6, 22.5),  # dr=2.8 over dz=3.0 => 43.0 deg <= 45 deg
        _reg_poly_wire(lcx, lcy, 3.4, 8, tab_h + lamp_h, 22.5),  # tapers in to Z=28.0
    ]
    lamp = _loft_sections(lamp_wires)
    shape = _clean_solid(table.fuse(lamp))

    # Decorative front drawer grooves on Y = 0 (strictly <= 45-deg V-grooves => zero overhang!)
    for gz in (2.5, 9.0, 15.5):
        hgroove = _poly_yz_extrude_x([(-0.2, gz - 0.8), (0.6, gz), (-0.2, gz + 0.8)], 2.5, W - 5.0)
        shape = shape.cut(hgroove)
    for gx in (2.5, W - 2.5):
        vgroove = _poly_yz_extrude_x(
            [(-0.2, 2.5), (0.6, 2.5), (0.6, 14.7), (-0.2, 15.5)],
            gx - 0.4,
            0.8,
        )
        shape = shape.cut(vgroove)
    # Two small recessed drawer handle notches (45-deg V-grooves)
    for gz in (5.8, 12.2):
        hnd = _poly_yz_extrude_x([(-0.2, gz - 0.9), (0.7, gz), (-0.2, gz + 0.9)], W / 2.0 - 3.0, 6.0)
        shape = shape.cut(hnd)

    # 1 underside floor mortise socket at center (13, 11)
    shape = _cut_floor_sockets(shape, [(W / 2.0, D / 2.0)])

    # Engrave "FUR05" on flat front top deck (Z = 18.0, Y = 4.6)
    eng = pd_mod.EngraveSpec("FUR05", "", W / 2.0, 4.6, 2.4, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng, tab_h, 0.45)

    extra = {
        "print_rotation_for_world": "identity",
        "floor_sockets_local_xy": [[round(W / 2.0, 3), round(D / 2.0, 3)]],
    }
    return shape, eng_ok, "FUR05", extra


def build_fur06_plant_pot_large(fur: pd_mod.FurnitureSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, bool, str, dict[str, Any]]:
    """FUR06_PLANT_POT_LARGE (20 x 20 x 18 mm): tapered faceted planter with top cross-mortise & floor socket."""
    top_w = float(fur.params["top_w"])  # 20.0
    bot_w = float(fur.params["bot_w"])  # 15.0
    H = float(fur.params["height_z"])  # 18.0
    rim_h = float(fur.params["rim_h"])  # 3.0
    slot_w = float(fur.params["tree_slot_w"])  # 3.30
    slot_l = float(fur.params["tree_slot_l"])  # 8.30
    slot_d = 6.20

    cx, cy = top_w / 2.0, top_w / 2.0
    mid_w = 18.6  # flares gently from 15.0 to 18.6 (6.8 deg), then 41-deg rim flare to 20.0
    pot_wires = [
        _chamfered_rect_wire(cx, cy, bot_w, bot_w, 2.0, 0.0),
        _chamfered_rect_wire(cx, cy, mid_w, mid_w, 2.2, H - rim_h),
        _chamfered_rect_wire(cx, cy, top_w, top_w, 2.4, H - rim_h + 1.1),  # sides 32 deg, corners 39 deg < 45 deg
        _chamfered_rect_wire(cx, cy, top_w, top_w, 2.4, H),
    ]
    shape = _loft_sections(pot_wires)

    # Top cross-mortise socket (8.30 x 3.30 crossed with 3.30 x 8.30, 6.2 mm deep from Z=18 down)
    cross_a = _box(cx - slot_l / 2.0, cy - slot_w / 2.0, H - slot_d, slot_l, slot_w, slot_d + 0.2)
    cross_b = _box(cx - slot_w / 2.0, cy - slot_l / 2.0, H - slot_d, slot_w, slot_l, slot_d + 0.2)
    shape = shape.cut(cross_a.fuse(cross_b))

    # 1 underside floor mortise socket at center (10, 10)
    shape = _cut_floor_sockets(shape, [(cx, cy)])

    # Engrave "FUR06" on front flat top rim strip (Y = 0..5.85, X = 2.4..17.6, Z = 18.0)
    eng = pd_mod.EngraveSpec("FUR06", "", cx, 2.9, 1.85, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng, H, 0.40)

    extra = {
        "print_rotation_for_world": "identity",
        "tree_cross_slot_mm": [slot_l, slot_w, slot_d],
        "floor_sockets_local_xy": [[round(cx, 3), round(cy, 3)]],
    }
    return shape, eng_ok, "FUR06", extra


def _make_tree_silhouette(
    canopy_w: float,
    total_h: float,
    trunk_w: float,
    trunk_h: float,
    thickness: float,
    broad_top: bool,
) -> Any:
    """Build one symmetric 3-tier stylized pine/cypress silhouette in XY (Z=0..thickness)."""
    cx = canopy_w / 2.0
    hw = canopy_w / 2.0
    tw2 = trunk_w / 2.0

    # Right half profile scaled proportionally to canopy_w (zero hardcoded width)
    if not broad_top:
        right_pts = [
            (cx + tw2, 0.0),
            (cx + tw2, trunk_h),
            (cx + hw, trunk_h),
            (cx + max(tw2 + 1.2, hw * 0.55), 22.8),
            (cx + hw * 0.85, 21.8),
            (cx + max(tw2 + 0.6, hw * 0.44), 30.2),
            (cx + hw * 0.66, 29.2),
            (cx + 1.5, total_h),
        ]
    else:
        right_pts = [
            (cx + tw2, 0.0),
            (cx + tw2, trunk_h),
            (cx + hw, trunk_h),
            (cx + max(tw2 + 1.2, hw * 0.55), 22.8),
            (cx + hw * 0.85, 21.8),
            (cx + max(tw2 + 0.6, hw * 0.44), 30.2),
            (cx + hw * 0.66, 29.2),
            (cx + 4.2, total_h - 2.0),
        ]

    left_pts = [(2.0 * cx - x, y) for x, y in reversed(right_pts)]
    poly = right_pts + left_pts
    return _poly2d_extrude_z(poly, 0.0, thickness)


def build_fur07_mini_tree(fur: pd_mod.FurnitureSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, bool, str, dict[str, Any]]:
    """FUR07_MINI_TREE (55 x 38 x 3 mm): flat-printed cross-halving pair (Half A + Half B side-by-side)."""
    canopy_w = float(fur.params["canopy_w"])  # 26.0
    total_h = float(fur.params["total_h"])  # 38.0
    trunk_w = float(fur.params["trunk_w"])  # 7.6
    trunk_h = float(fur.params["trunk_h"])  # 14.0
    thickness = float(fur.params["thickness"])  # 3.0
    slot_w = float(fur.params["cross_slot_w"])  # 3.30
    pair_gap = 3.0
    cx = canopy_w / 2.0  # 13.0
    mid_y = total_h / 2.0  # 19.0

    # Half A: bottom-slotted (Y = 0..19.15) with intact pointed crown up to Y = 38.0
    half_a = _make_tree_silhouette(canopy_w, total_h, trunk_w, trunk_h, thickness, broad_top=False)
    slot_a = _box(cx - slot_w / 2.0, -0.2, -0.2, slot_w, mid_y + 0.15 + 0.2, thickness + 0.4)
    half_a = half_a.cut(slot_a)
    eng_a = pd_mod.EngraveSpec("F07A", "", cx, 24.5, 2.2, False)
    half_a, ok_a = cc.safe_engrave_top_face(half_a, eng_a, thickness, 0.45)

    # Half B: top-slotted (Y = 18.85..38.0) with intact solid trunk (Y=0..18.85) & 2.55 mm upper cheeks
    half_b = _make_tree_silhouette(canopy_w, total_h, trunk_w, trunk_h, thickness, broad_top=True)
    slot_b = _box(cx - slot_w / 2.0, mid_y - 0.15, -0.2, slot_w, total_h - (mid_y - 0.15) + 0.4, thickness + 0.4)
    half_b = half_b.cut(slot_b)
    eng_b = pd_mod.EngraveSpec("F07B", "", cx, 16.4, 2.0, False)
    half_b, ok_b = cc.safe_engrave_top_face(half_b, eng_b, thickness, 0.45)

    # Place Half B side-by-side with 3.0 mm gap (offset X = 29.0 mm)
    offset_x = canopy_w + pair_gap  # 29.0
    half_b.translate(_vec(offset_x, 0.0, 0.0))

    shape = Part.makeCompound([half_a, half_b])
    eng_ok = bool(ok_a and ok_b)

    extra = {
        "is_cross_pair": True,
        "qty_override": 2,  # 2 complete tree pairs for the 2 FUR06_PLANT_POT_LARGE pots
        "pair_gap_mm": pair_gap,
        "pair_half_offset_x_mm": offset_x,
        "half_a_local_x_range": [0.0, canopy_w],
        "half_b_local_x_range": [offset_x, offset_x + canopy_w],
        "print_rotation_for_world": "rot_x_90_cross_pair",
    }
    return shape, eng_ok, "F07A F07B", extra


def build_fur08_plant_pot_small(fur: pd_mod.FurnitureSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, bool, str, dict[str, Any]]:
    """FUR08_PLANT_POT_SMALL (16 x 16 x 14 mm): small faceted pot with 45-deg self-supporting bush rosette."""
    top_w = float(fur.params["top_w"])  # 16.0
    bot_w = float(fur.params["bot_w"])  # 12.0
    H = float(fur.params["height_z"])  # 14.0
    pot_h = 9.5
    cx, cy = top_w / 2.0, top_w / 2.0

    # Tapered faceted pot (Z = 0..9.5, sides 29 deg, corners 35 deg < 45 deg)
    pot_wires = [
        _chamfered_rect_wire(cx, cy, bot_w, bot_w, 1.6, 0.0),
        _chamfered_rect_wire(cx, cy, 15.0, 15.0, 1.9, 7.7),
        _chamfered_rect_wire(cx, cy, top_w, top_w, 2.0, 8.6),
        _chamfered_rect_wire(cx, cy, top_w, top_w, 2.0, pot_h),
    ]
    pot = _loft_sections(pot_wires)

    # Central self-supporting botanical bush dome (Z = 9.5..14.0, flat top R=3.5 for crisp "F08" engraving)
    dome_wires = [
        _reg_poly_wire(cx, cy, 6.0, 12, pot_h - 0.4, 15.0),
        _reg_poly_wire(cx, cy, 6.6, 12, pot_h + 0.8, 15.0),  # dr=0.6 over dz=1.2 => 26.6 deg
        _reg_poly_wire(cx, cy, 5.4, 12, pot_h + 2.7, 15.0),
        _reg_poly_wire(cx, cy, 3.6, 12, H, 15.0),
    ]
    bush = _loft_sections(dome_wires)
    shape = pot.fuse(bush)

    # 6 sculpted low rosette petal mounds around perimeter (strictly <= 45 deg, staying inside 16x16 footprint)
    for k in range(6):
        ang = math.radians(k * 60.0 + 30.0)
        px = cx + 4.0 * math.cos(ang)
        py = cy + 4.0 * math.sin(ang)
        pw = [
            _reg_poly_wire(px, py, 2.3, 6, pot_h - 0.4, k * 60.0),
            _reg_poly_wire(px, py, 2.9, 6, pot_h + 0.8, k * 60.0),  # dr=0.6 over dz=1.2 => 26.6 deg
            _reg_poly_wire(px, py, 2.1, 6, pot_h + 2.4, k * 60.0),
            _reg_poly_wire(px, py, 0.9, 6, pot_h + 3.4, k * 60.0),
        ]
        shape = shape.fuse(_loft_sections(pw))
    shape = _clean_solid(shape)

    # 1 underside floor mortise socket at center (8, 8)
    shape = _cut_floor_sockets(shape, [(cx, cy)])

    # Engrave "F08" on flat crown medallion at Z = 14.0 (diameter 7.2 mm)
    eng = pd_mod.EngraveSpec("F08", "", cx, cy, 1.7, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng, H, 0.40)

    extra = {
        "print_rotation_for_world": "identity",
        "floor_sockets_local_xy": [[round(cx, 3), round(cy, 3)]],
    }
    return shape, eng_ok, "F08", extra


def build_fur09_floor_tenon_peg(fur: pd_mod.FurnitureSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, bool, str, dict[str, Any]]:
    """FUR09_FLOOR_TENON_PEG (6.0 x 7.0 x 4.0 mm): flat-printed floating floor tenon with 0.3 mm end chamfers."""
    px = float(fur.params["peg_x"])  # 6.0
    py = float(fur.params["length_z"])  # 7.0 (printed along Y)
    pz = float(fur.params["peg_y"])  # 4.0 (printed along Z)
    ch = 0.30

    # Loft along Y so both insertion ends (Y=0 and Y=7) get clean 0.3 mm 45-deg lead-in chamfers
    def _xz_rect_wire(y_pos: float, inset: float) -> Any:
        x0, x1 = inset, px - inset
        z0, z1 = inset, pz - inset
        pts = [
            _vec(x0, y_pos, z0),
            _vec(x1, y_pos, z0),
            _vec(x1, y_pos, z1),
            _vec(x0, y_pos, z1),
            _vec(x0, y_pos, z0),
        ]
        return Part.makePolygon(pts)

    shape = _loft_sections([
        _xz_rect_wire(0.0, ch),
        _xz_rect_wire(ch, 0.0),
        _xz_rect_wire(py - ch, 0.0),
        _xz_rect_wire(py, ch),
    ])

    # Engrave "F09" on flat top face Z = 4.0
    eng = pd_mod.EngraveSpec("F09", "", px / 2.0, py / 2.0, 1.5, False)
    shape, eng_ok = cc.safe_engrave_top_face(shape, eng, pz, 0.35)

    extra = {
        "print_rotation_for_world": "rot_x_90",
        "cross_section_world_xy_mm": [px, pz],
        "vertical_length_world_z_mm": py,
    }
    return shape, eng_ok, "F09", extra


BUILDERS = {
    "FUR01_SOFA": build_fur01_sofa,
    "FUR02_TV_STAND": build_fur02_tv_stand,
    "FUR03_TV_SCREEN": build_fur03_tv_screen,
    "FUR04_BED": build_fur04_bed,
    "FUR05_BEDSIDE_TABLE": build_fur05_bedside_table,
    "FUR06_PLANT_POT_LARGE": build_fur06_plant_pot_large,
    "FUR07_MINI_TREE": build_fur07_mini_tree,
    "FUR08_PLANT_POT_SMALL": build_fur08_plant_pot_small,
    "FUR09_FLOOR_TENON_PEG": build_fur09_floor_tenon_peg,
}


def build_one_furniture(fur: pd_mod.FurnitureSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, dict[str, Any]]:
    builder = BUILDERS.get(fur.part_id)
    if builder is None:
        raise ValueError(f"No furniture builder registered for {fur.part_id}")

    shape, engraved_ok, engrave_text, extra = builder(fur, cfg)

    # Normalize to print-ready bed coordinates (X_min = 0, Y_min = 0, Z_min = 0)
    bb = shape.BoundBox
    shape.translate(_vec(-bb.XMin, -bb.YMin, -bb.ZMin))
    bb = shape.BoundBox

    bbox_mm = [round(bb.XLength, 3), round(bb.YLength, 3), round(bb.ZLength, 3)]
    qty = int(extra.pop("qty_override", fur.qty))

    meta: dict[str, Any] = {
        "part_id": fur.part_id,
        "kind": "furniture",
        "room": fur.room,
        "category": fur.category,
        "qty": qty,
        "vi_name": fur.vi_name,
        "attachment": fur.attachment,
        "assembly_placements": list(fur.assembly_placements),
        "print_bbox_mm": bbox_mm,
        "print_z_min": round(bb.ZMin, 4),
        "volume_mm3": round(shape.Volume, 3),
        "solids": len(shape.Solids),
        "valid": bool(shape.isValid()),
        "engraved_ok": bool(engraved_ok),
        "engrave_text": engrave_text,
        "bed_fit": bool(cc.fits_bed_rotatable(bbox_mm, cfg)),
        "color_rgb": list(fur.color_rgb),
        "notes": fur.notes,
    }
    meta.update(extra)
    return shape, meta


def parse_args() -> argparse.Namespace:
    argv = sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = [a for a in argv if not a.endswith(".py")]
    ap = argparse.ArgumentParser(description="Build 3D-printable house-scale furniture v2 (FUR01..FUR09)")
    ap.add_argument("--parts", type=str, default=os.environ.get("PRINT3D_PARTS", ""), help="Comma-separated FUR part_ids")
    args, _unknown = ap.parse_known_args(argv)
    return args


def main() -> int:
    t0 = time.time()
    args = parse_args()
    cfg = pd_mod.PrintConfig()
    furniture_specs = pd_mod.build_furniture_specs(cfg)

    target_ids: set[str] | None = None
    if args.parts:
        target_ids = {s.strip() for s in args.parts.split(",") if s.strip()}

    built: list[dict[str, Any]] = []
    failures: list[str] = []

    for fur in furniture_specs:
        if target_ids is not None and fur.part_id not in target_ids:
            continue
        shape, meta = build_one_furniture(fur, cfg)
        step_p, stl_p, facets = cc.export_part_step_stl(shape, fur.part_id)
        meta["step_file"] = f"parts/{step_p.name}"
        meta["stl_file"] = f"parts/{stl_p.name}"
        meta["stl_facets"] = facets
        cc.save_part_meta(fur.part_id, meta)

        expected_solids = 2 if meta.get("is_cross_pair") else 1
        ok = (
            meta["valid"]
            and meta["solids"] == expected_solids
            and meta["bed_fit"]
            and abs(meta["print_z_min"]) <= 1e-3
        )
        status = "OK" if ok else "FAIL"
        print(
            f"[{status}] {fur.part_id}: bbox={meta['print_bbox_mm']} zmin={meta['print_z_min']} "
            f"vol={meta['volume_mm3']}mm3 solids={meta['solids']} eng={meta['engraved_ok']} facets={facets}"
        )
        if not ok:
            failures.append(fur.part_id)
        built.append(meta)

    elapsed = round(time.time() - t0, 2)
    print(f"DONE: built {len(built)} furniture parts in {elapsed}s (failures={len(failures)})")
    return 1 if failures else 0


if __name__ == "__main__" or any(pathlib.Path(a).stem == __name__ for a in sys.argv):
    rc = main()
    if rc != 0:
        raise SystemExit(rc)
