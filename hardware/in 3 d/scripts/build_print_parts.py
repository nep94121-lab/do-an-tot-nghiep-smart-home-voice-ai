"""Headless FreeCAD 1.1 Builder for 3D-Printable House Panels, Splits, Engraved Dims & Supports.

Run via FreeCADCmd:
    "C:\\Users\\LENOVO\\AppData\\Local\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe" "hardware/in 3 d/scripts/build_print_parts.py"
    "C:\\Users\\LENOVO\\AppData\\Local\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe" "hardware/in 3 d/scripts/build_print_parts.py" -- --parts P16_PCB_PLATE,P02_WALL_BACK_piece1of2,SUP07_PCB_CARRIER_FRAME_90X70

Outputs (under `hardware/in 3 d/`):
    - `STEP/<part_id>.step`   Exact BRep CAD solid (print-oriented, Z_min = 0)
    - `STL/<part_id>.stl`     Watertight binary STL mesh (print-oriented, Z_min = 0)
    - `build_meta/<part_id>.json` (per-part build geometry metadata; merged by export/verify scripts)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
import time
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PRINT3D_ROOT = SCRIPT_DIR.parent
MICA_DIR = PRINT3D_ROOT.parent / "mica"

for p in (str(SCRIPT_DIR), str(MICA_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import FreeCAD
import Mesh
import MeshPart
import Part

import mica_design as md
import print_domain as pd_mod

STEP_DIR = PRINT3D_ROOT / "STEP"
STL_DIR = PRINT3D_ROOT / "STL"
META_DIR = PRINT3D_ROOT / "build_meta"

FONT_DIR = "C:/Windows/Fonts/"
PRIMARY_FONT = "consolab.ttf"
FALLBACK_FONT = "arialbd.ttf"


# ---------------------------------------------------------------------------
# WireString -> Valid Extruded Text Solid (handles hollow glyphs like O, 0, 8, P)
# ---------------------------------------------------------------------------
def _wires_to_faces_with_holes(wires: list[Any]) -> list[Any]:
    """Convert a character's closed contour wires into planar faces with inner holes cut out."""
    face_infos: list[tuple[float, Any]] = []
    for w in wires:
        if not w.isClosed():
            continue
        try:
            f = Part.Face(w)
            if f.Area > 1e-4:
                face_infos.append((f.Area, f))
        except Exception:
            continue
    if not face_infos:
        return []
    # Sort descending by area: largest contour is outer boundary, smaller contained contours are holes
    face_infos.sort(key=lambda item: item[0], reverse=True)
    used = [False] * len(face_infos)
    result_faces: list[Any] = []
    for i, (_area_i, fi) in enumerate(face_infos):
        if used[i]:
            continue
        used[i] = True
        cur = fi
        bbi = fi.BoundBox
        for j in range(i + 1, len(face_infos)):
            if used[j]:
                continue
            fj = face_infos[j][1]
            bbj = fj.BoundBox
            if (
                bbj.XMin >= bbi.XMin - 0.05
                and bbj.XMax <= bbi.XMax + 0.05
                and bbj.YMin >= bbi.YMin - 0.05
                and bbj.YMax <= bbi.YMax + 0.05
            ):
                try:
                    cut_res = cur.cut(fj)
                    if cut_res.Faces:
                        cur = cut_res
                        used[j] = True
                except Exception:
                    pass
        result_faces.append(cur)
    return result_faces


def make_text_extrusion(
    line1: str,
    line2: str,
    font_h: float,
    depth: float,
    cx: float,
    cy: float,
    z_bottom: float,
    rotated_90: bool = False,
    font_file: str = PRIMARY_FONT,
) -> Any | None:
    """Build an extruded 3D compound of 1 or 2 centered lines of crisp vector text."""
    lines = [s for s in (line1.strip(), line2.strip()) if s]
    if not lines:
        return None

    line_shapes: list[Any] = []
    line_gap = font_h * 1.38
    total_h = font_h if len(lines) == 1 else (font_h + line_gap)

    for idx, txt in enumerate(lines):
        try:
            char_wires_list = Part.makeWireString(txt, FONT_DIR, font_file, float(font_h), 0.0)
        except Exception:
            char_wires_list = Part.makeWireString(txt, FONT_DIR, FALLBACK_FONT, float(font_h), 0.0)

        char_solids: list[Any] = []
        for cwires in char_wires_list:
            faces = _wires_to_faces_with_holes(cwires)
            for f in faces:
                try:
                    ext = f.extrude(FreeCAD.Vector(0, 0, float(depth)))
                    if ext.Volume > 1e-5:
                        char_solids.append(ext)
                except Exception:
                    continue
        if not char_solids:
            continue
        comp = Part.makeCompound(char_solids)
        bb = comp.BoundBox
        # Center this line horizontally around X=0, stack line1 above line2
        y_off = (total_h / 2.0 - font_h) if (idx == 0 and len(lines) == 2) else (-total_h / 2.0 if len(lines) == 2 else -font_h / 2.0)
        tr_x = -(bb.XMin + bb.XMax) / 2.0
        tr_y = y_off - bb.YMin
        comp.translate(FreeCAD.Vector(tr_x, tr_y, 0.0))
        line_shapes.append(comp)

    if not line_shapes:
        return None

    all_txt = Part.makeCompound(line_shapes)
    if rotated_90:
        all_txt.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 90.0)
    all_txt.translate(FreeCAD.Vector(float(cx), float(cy), float(z_bottom)))
    return all_txt


def safe_engrave_top_face(
    shape: Any,
    engrave: pd_mod.EngraveSpec,
    z_top: float,
    engrave_depth: float,
) -> tuple[Any, bool]:
    """Cut engraved text cleanly into the top face at Z = z_top, verifying single valid solid."""
    for font_file in (PRIMARY_FONT, FALLBACK_FONT):
        txt_solid = make_text_extrusion(
            line1=engrave.line1,
            line2=engrave.line2,
            font_h=engrave.font_h,
            depth=engrave_depth + 0.25,
            cx=engrave.cx,
            cy=engrave.cy,
            z_bottom=z_top - engrave_depth,
            rotated_90=engrave.rotated_90,
            font_file=font_file,
        )
        if txt_solid is None:
            continue
        try:
            cut_shape = shape.cut(txt_solid)
            if len(cut_shape.Solids) == 1 and cut_shape.isValid() and cut_shape.Volume > shape.Volume * 0.85:
                return cut_shape, True
        except Exception:
            pass
    # Fallback: cut character-by-character so one difficult glyph never breaks the whole label
    cur = shape
    cut_any = False
    for line_idx, txt in enumerate((engrave.line1, engrave.line2)):
        if not txt.strip():
            continue
        y_shift = (engrave.font_h * 0.68) if line_idx == 0 else (-engrave.font_h * 0.68)
        cx_l = engrave.cx - (y_shift if engrave.rotated_90 else 0.0)
        cy_l = engrave.cy + (0.0 if engrave.rotated_90 else y_shift)
        txt_s = make_text_extrusion(
            line1=txt,
            line2="",
            font_h=engrave.font_h,
            depth=engrave_depth + 0.25,
            cx=cx_l,
            cy=cy_l,
            z_bottom=z_top - engrave_depth,
            rotated_90=engrave.rotated_90,
            font_file=FALLBACK_FONT,
        )
        if txt_s is None:
            continue
        for sub in txt_s.Solids:
            try:
                cand = cur.cut(sub)
                if len(cand.Solids) == 1 and cand.isValid():
                    cur = cand
                    cut_any = True
            except Exception:
                continue
    return cur, cut_any


# ---------------------------------------------------------------------------
# Panel Solid & Interlocking Dovetail Split Builder (Local Flat XY Coordinates)
# ---------------------------------------------------------------------------
def build_flat_panel_solid(pspec: md.PanelSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, dict[str, Any]]:
    """Build exact flat panel solid lying on Z in [0, T_mm] with bottom-left at (0, 0)."""
    p = md.default_param_values(T_mm=cfg.T_mm, tab_clr=cfg.tab_clr)
    ev = md.evaluate_panel_2d(pspec, T_mm=cfg.T_mm, tab_clr=cfg.tab_clr)
    su = ev["shift_u"]
    sv = ev["shift_v"]
    T = cfg.T_mm

    add_solids: list[Any] = []
    for r in pspec.add_rects:
        u0 = md.eval_expr(r.u0, p) + su
        v0 = md.eval_expr(r.v0, p) + sv
        du = md.eval_expr(r.du, p)
        dv = md.eval_expr(r.dv, p)
        add_solids.append(Part.makeBox(du, dv, T, FreeCAD.Vector(u0, v0, 0.0)))

    body = add_solids[0]
    for b in add_solids[1:]:
        body = body.fuse(b)
    body = body.removeSplitter()

    cut_solids: list[Any] = []
    for r in pspec.cut_rects:
        u0 = md.eval_expr(r.u0, p) + su
        v0 = md.eval_expr(r.v0, p) + sv
        du = md.eval_expr(r.du, p)
        dv = md.eval_expr(r.dv, p)
        cut_solids.append(Part.makeBox(du, dv, T + 2.0, FreeCAD.Vector(u0, v0, -1.0)))

    for c in pspec.cut_circles:
        cu = md.eval_expr(c.u, p) + su
        cv = md.eval_expr(c.v, p) + sv
        rad = md.eval_expr(c.dia, p) / 2.0
        cut_solids.append(Part.makeCylinder(rad, T + 2.0, FreeCAD.Vector(cu, cv, -1.0), FreeCAD.Vector(0, 0, 1)))

    if cut_solids:
        body = body.cut(Part.makeCompound(cut_solids))
        body = body.removeSplitter()

    return body, ev


def _make_dovetail_prism(dt: pd_mod.DovetailJointSpec, is_female: bool, T_mm: float) -> Any:
    """Build an extruded trapezoidal dovetail prism (exact male or clearance-enlarged female)."""
    clr = dt.clearance if is_female else 0.0
    depth = dt.depth + clr
    half_neck = dt.neck_w / 2.0 + clr
    half_head = dt.head_w / 2.0 + clr
    c = dt.cut_pos
    ca = dt.center_along
    # Direction male tongue extends from cut_pos:
    # male_side == +1 means +side owns male, so tongue extends into -side (sign = -1)
    ext_sign = -1.0 if dt.male_side == +1 else +1.0
    back_off = -ext_sign * 0.8  # overlap into male base (or outside female edge)

    if dt.axis == "U":
        pts_2d = [
            (c + back_off, ca - half_neck),
            (c, ca - half_neck),
            (c + ext_sign * depth, ca - half_head),
            (c + ext_sign * depth, ca + half_head),
            (c, ca + half_neck),
            (c + back_off, ca + half_neck),
        ]
    else:
        pts_2d = [
            (ca - half_neck, c + back_off),
            (ca - half_neck, c),
            (ca - half_head, c + ext_sign * depth),
            (ca + half_head, c + ext_sign * depth),
            (ca + half_neck, c),
            (ca + half_neck, c + back_off),
        ]

    vecs = [FreeCAD.Vector(x, y, -1.0) for (x, y) in pts_2d]
    vecs.append(vecs[0])
    wire = Part.makePolygon(vecs)
    face = Part.Face(wire)
    return face.extrude(FreeCAD.Vector(0, 0, T_mm + 2.0))


def build_panel_piece_solid(
    piece: pd_mod.PanelPieceSpec,
    pspec: md.PanelSpec,
    cfg: pd_mod.PrintConfig,
    base_solid_cache: dict[str, tuple[Any, dict[str, Any]]],
) -> tuple[Any, dict[str, Any]]:
    """Build one print-ready panel or interlocking split piece with engraved ID + dimensions."""
    if piece.source_panel_id not in base_solid_cache:
        base_solid_cache[piece.source_panel_id] = build_flat_panel_solid(pspec, cfg)
    full_solid, ev = base_solid_cache[piece.source_panel_id]

    if piece.piece_count == 1:
        shape = full_solid.copy()
    else:
        u_lo, u_hi = piece.u_range
        v_lo, v_hi = piece.v_range
        # Half-gap of 0.05 mm on internal straight seams (0.10 mm total clearance) guarantees 0.0 mm^3 BRep overlap
        seam_half_gap = 0.05
        m_u0 = (u_lo + seam_half_gap) if u_lo > 1e-3 else -2.0
        m_u1 = (u_hi - seam_half_gap) if u_hi < ev["width"] - 1e-3 else (ev["width"] + 2.0)
        m_v0 = (v_lo + seam_half_gap) if v_lo > 1e-3 else -2.0
        m_v1 = (v_hi - seam_half_gap) if v_hi < ev["height"] - 1e-3 else (ev["height"] + 2.0)

        mask = Part.makeBox(m_u1 - m_u0, m_v1 - m_v0, cfg.T_mm + 2.0, FreeCAD.Vector(m_u0, m_v0, -1.0))

        for dt in piece.dovetails:
            if dt.axis == "U":
                piece_is_plus = abs(u_lo - dt.cut_pos) < 1e-3
                piece_is_minus = abs(u_hi - dt.cut_pos) < 1e-3
            else:
                piece_is_plus = abs(v_lo - dt.cut_pos) < 1e-3
                piece_is_minus = abs(v_hi - dt.cut_pos) < 1e-3

            if not (piece_is_plus or piece_is_minus):
                continue

            owns_male = (piece_is_plus and dt.male_side == +1) or (piece_is_minus and dt.male_side == -1)
            if owns_male:
                tongue = _make_dovetail_prism(dt, is_female=False, T_mm=cfg.T_mm)
                mask = mask.fuse(tongue)
            else:
                socket = _make_dovetail_prism(dt, is_female=True, T_mm=cfg.T_mm)
                mask = mask.cut(socket)

        shape = full_solid.common(mask)
        shape = shape.removeSplitter()

    # Compute actual clipped piece bbox before engraving so engraved dimensions match the real solid 1:1
    bb_pre = shape.BoundBox
    real_engrave = pd_mod.EngraveSpec(
        line1=piece.engrave.line1,
        line2=f"{bb_pre.XLength:.0f}x{bb_pre.YLength:.0f}x{bb_pre.ZLength:.0f}mm",
        cx=piece.engrave.cx,
        cy=piece.engrave.cy,
        font_h=piece.engrave.font_h,
        rotated_90=piece.engrave.rotated_90,
    )
    # Engrave ID + exact real dimensions on UP-facing top face (Z = T_mm) before shifting to origin
    shape_eng, engraved_ok = safe_engrave_top_face(shape, real_engrave, cfg.T_mm, cfg.engrave_depth)

    # Record pre-shift bbox in panel-local coordinates (used to place back into 3D house assembly!)
    bb_local = shape_eng.BoundBox
    local_min = (round(bb_local.XMin, 4), round(bb_local.YMin, 4), round(bb_local.ZMin, 4))
    local_max = (round(bb_local.XMax, 4), round(bb_local.YMax, 4), round(bb_local.ZMax, 4))

    # Normalize to print-ready bed coordinates: X_min=0, Y_min=0, Z_min=0
    shape_print = shape_eng.copy()
    shape_print.translate(FreeCAD.Vector(-bb_local.XMin, -bb_local.YMin, -bb_local.ZMin))

    bb_p = shape_print.BoundBox
    meta = {
        "part_id": piece.part_id,
        "kind": "panel",
        "source_panel_id": piece.source_panel_id,
        "piece_index": piece.piece_index,
        "piece_count": piece.piece_count,
        "qty": piece.qty,
        "vi_name": piece.vi_name,
        "plane": piece.plane,
        "origin_xyz": list(piece.origin_xyz),
        "extra_origins_xyz": [list(e) for e in piece.extra_origins_xyz],
        "explode_xyz": list(piece.explode_xyz),
        "shift_u": piece.shift_u,
        "shift_v": piece.shift_v,
        "local_bbox_min": list(local_min),
        "local_bbox_max": list(local_max),
        "print_bbox_mm": [round(bb_p.XLength, 3), round(bb_p.YLength, 3), round(bb_p.ZLength, 3)],
        "print_z_min": round(bb_p.ZMin, 4),
        "volume_mm3": round(shape_print.Volume, 3),
        "solids": len(shape_print.Solids),
        "valid": bool(shape_print.isValid()),
        "engraved_ok": engraved_ok,
        "engrave_text": f"{real_engrave.line1} | {real_engrave.line2}",
        "dovetail_count": len(piece.dovetails),
        "color_rgb": list(piece.color_rgb),
    }
    return shape_print, meta


# ---------------------------------------------------------------------------
# Printable Mechanical Supports (SUP01..SUP12) — Flat Print-Ready, Zero Overhang
# ---------------------------------------------------------------------------
def build_support_solid(sup: pd_mod.SupportSpec, cfg: pd_mod.PrintConfig) -> tuple[Any, dict[str, Any]]:
    """Build exact BRep solid for one printable support, oriented flat on Z=0 with engraved text."""
    pr = sup.params
    cat = sup.category
    engrave_z_top = sup.size_xyz[2]
    engrave_d = 0.50

    if cat == "bracket":
        # L-bracket lying on its base edge (Z = 0..height), zero overhang!
        arm = float(pr["arm"])
        h = float(pr["height"])
        wt = float(pr["wall_t"])
        hd = float(pr["hole_d"])
        leg_x = Part.makeBox(arm, wt, h, FreeCAD.Vector(0, 0, 0))
        leg_y = Part.makeBox(wt, arm, h, FreeCAD.Vector(0, 0, 0))
        shape = leg_x.fuse(leg_y)
        if pr.get("gusset"):
            # Bottom triangular reinforcing web (Z=0..wt) prints completely flat on bed!
            g_span = arm - 2.0
            g_pts = [
                FreeCAD.Vector(wt, wt, 0.0),
                FreeCAD.Vector(g_span, wt, 0.0),
                FreeCAD.Vector(wt, g_span, 0.0),
                FreeCAD.Vector(wt, wt, 0.0),
            ]
            g_face = Part.Face(Part.makePolygon(g_pts))
            gusset = g_face.extrude(FreeCAD.Vector(0, 0, wt))
            shape = shape.fuse(gusset)
            engrave_z_top = wt
            engrave_d = 0.45
        # M3 mounting holes through both legs (centered vertically)
        hx_pos = arm * 0.62
        c1 = Part.makeCylinder(hd / 2.0, wt + 4.0, FreeCAD.Vector(hx_pos, -2.0, h / 2.0), FreeCAD.Vector(0, 1, 0))
        c2 = Part.makeCylinder(hd / 2.0, wt + 4.0, FreeCAD.Vector(-2.0, hx_pos, h / 2.0), FreeCAD.Vector(1, 0, 0))
        shape = shape.cut(Part.makeCompound([c1, c2])).removeSplitter()

    elif cat == "clip":
        # U-channel clip printed upside-down (cap flat on bed Z=0..wall_t, two legs rising Z=wall_t..height) -> ZERO overhang!
        L = float(pr["length"])
        sw = float(pr["slot_w"])
        wt = float(pr["wall_t"])
        h = float(pr["height"])
        total_w = sw + 2.0 * wt
        outer = Part.makeBox(L, total_w, h, FreeCAD.Vector(0, 0, 0))
        slot = Part.makeBox(L + 2.0, sw, h - wt + 1.0, FreeCAD.Vector(-1.0, wt, wt))
        shape = outer.cut(slot).removeSplitter()
        # Engrave on bottom cap (which is at Z=0 -> engrave on Z=0? No, keep Z=0 flat, engrave on inner cap Z=wt!)
        engrave_z_top = wt
        engrave_d = 0.40

    elif cat == "foot":
        # Corner house foot: flat pad 30x30x11 mm + outer L-lip (3mm wide, 3mm tall) on X=[0..3] and Y=[0..3] -> ZERO overhang!
        sz = float(pr["size"])
        lh = float(pr["lift_h"])
        lip_h = float(pr["lip_h"])
        lip_t = float(pr["lip_t"])
        hd = float(pr["hole_d"])
        pad = Part.makeBox(sz, sz, lh, FreeCAD.Vector(0, 0, 0))
        lip_x = Part.makeBox(sz, lip_t, lip_h, FreeCAD.Vector(0, 0, lh))
        lip_y = Part.makeBox(lip_t, sz, lip_h, FreeCAD.Vector(0, 0, lh))
        shape = pad.fuse(lip_x).fuse(lip_y)
        # Optional M3 alignment/screw hole in corner pad
        hole = Part.makeCylinder(hd / 2.0, lh + 2.0, FreeCAD.Vector(sz - 7.0, sz - 7.0, -1.0), FreeCAD.Vector(0, 0, 1))
        shape = shape.cut(hole).removeSplitter()
        engrave_z_top = lh
        engrave_d = 0.50

    elif cat == "standoff":
        # Cylindrical standoff with flared bottom flange + M3 through-bore (prints upright, flat flange on Z=0)
        od = float(pr["od"])
        fod = float(pr["flange_od"])
        fh = float(pr["flange_h"])
        h = float(pr["height"])
        bd = float(pr["bore_d"])
        flange = Part.makeCylinder(fod / 2.0, fh, FreeCAD.Vector(fod / 2.0, fod / 2.0, 0.0))
        shaft = Part.makeCylinder(od / 2.0, h, FreeCAD.Vector(fod / 2.0, fod / 2.0, 0.0))
        bore = Part.makeCylinder(bd / 2.0, h + 2.0, FreeCAD.Vector(fod / 2.0, fod / 2.0, -1.0))
        shape = flange.fuse(shaft).cut(bore).removeSplitter()
        # Small chamfer-free flat top ring; engrave ID on flange top step if room, else skip top-ring cut on tiny OD
        engrave_z_top = fh
        engrave_d = 0.35

    elif cat == "cradle":
        # 1-piece multi-post carrier frame (SUP07 Hub PCB 90x70, SUP09 Relay 44.5x20.5)
        ox = float(pr["outer_x"])
        oy = float(pr["outer_y"])
        bh = float(pr["base_h"])
        th = float(pr["total_h"])
        px = float(pr["pitch_x"])
        py = float(pr["pitch_y"])
        bod = float(pr["boss_od"])
        bd = float(pr["bore_d"])
        cx_cut = float(pr["cutout_x"])
        cy_cut = float(pr["cutout_y"])

        base = Part.makeBox(ox, oy, bh, FreeCAD.Vector(0, 0, 0))
        # Center airflow & solder-pin cutout
        cut = Part.makeBox(cx_cut, cy_cut, bh + 2.0, FreeCAD.Vector((ox - cx_cut) / 2.0, (oy - cy_cut) / 2.0, -1.0))
        shape = base.cut(cut)

        # 4 integrated cylindrical bosses at exact pitch
        bosses: list[Any] = []
        bores: list[Any] = []
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                bx = ox / 2.0 + sx * px / 2.0
                by = oy / 2.0 + sy * py / 2.0
                bosses.append(Part.makeCylinder(bod / 2.0, th, FreeCAD.Vector(bx, by, 0.0)))
                bores.append(Part.makeCylinder(bd / 2.0, th + 2.0, FreeCAD.Vector(bx, by, -1.0)))
        for b in bosses:
            shape = shape.fuse(b)
        shape = shape.cut(Part.makeCompound(bores)).removeSplitter()
        engrave_z_top = bh
        engrave_d = 0.45

    elif cat == "retainer":
        if sup.part_id == "SUP10_PAM8403_CLIP_STAND":
            # Rectangular cradle with recessed pocket for 21x18 mm PAM8403 + 2 side mounting holes at 26.0 mm span
            ox = float(pr["outer_x"])
            oy = float(pr["outer_y"])
            bh = float(pr["base_h"])
            wh = float(pr["wall_h"])
            px = float(pr["pcb_x"])
            py = float(pr["pcb_y"])
            span = float(pr["hole_span"])
            hd = float(pr["hole_d"])
            # Base plate + 4 corner retention walls (with open wire cutouts on short ends)
            base = Part.makeBox(ox, oy, bh, FreeCAD.Vector(0, 0, 0))
            wall_box = Part.makeBox(px + 3.2, py + 3.2, wh, FreeCAD.Vector((ox - px - 3.2) / 2.0, (oy - py - 3.2) / 2.0, 0.0))
            pocket = Part.makeBox(px, py, wh - bh + 1.0, FreeCAD.Vector((ox - px) / 2.0, (oy - py) / 2.0, bh))
            # Open side slots for wire access
            wire_slot = Part.makeBox(ox + 2.0, 10.0, wh - bh + 1.0, FreeCAD.Vector(-1.0, (oy - 10.0) / 2.0, bh))
            h1 = Part.makeCylinder(hd / 2.0, wh + 2.0, FreeCAD.Vector(ox / 2.0 - span / 2.0, oy / 2.0, -1.0))
            h2 = Part.makeCylinder(hd / 2.0, wh + 2.0, FreeCAD.Vector(ox / 2.0 + span / 2.0, oy / 2.0, -1.0))
            shape = base.fuse(wall_box).cut(Part.makeCompound([pocket, wire_slot, h1, h2])).removeSplitter()
            engrave_z_top = bh
            engrave_d = 0.40
        else:
            # SUP11_SPEAKER_28MM_RETAINER: flat bridge bar with recessed speaker seat + 2x M3 clamp ears at 36.0 mm span
            L = float(pr["length"])
            W = float(pr["width"])
            H = float(pr["height"])
            fh = float(pr["flange_h"])
            span = float(pr["hole_span"])
            hd = float(pr["hole_d"])
            spk_od = float(pr["spk_od"])
            spk_d = float(pr["spk_depth"])
            # Print inverted (back bar flat on Z=0, two mounting feet rising up to Z=H) -> ZERO overhang!
            bar = Part.makeBox(L, W, fh, FreeCAD.Vector(0, 0, 0))
            foot_w = (L - spk_od) / 2.0
            f_l = Part.makeBox(foot_w, W, H, FreeCAD.Vector(0, 0, 0))
            f_r = Part.makeBox(foot_w, W, H, FreeCAD.Vector(L - foot_w, 0, 0))
            # Central gentle pressure boss supporting speaker magnet back (height = H - spk_d)
            boss_h = max(fh + 0.5, H - spk_d)
            boss = Part.makeCylinder(6.0, boss_h, FreeCAD.Vector(L / 2.0, W / 2.0, 0.0))
            h1 = Part.makeCylinder(hd / 2.0, H + 2.0, FreeCAD.Vector(L / 2.0 - span / 2.0, W / 2.0, -1.0))
            h2 = Part.makeCylinder(hd / 2.0, H + 2.0, FreeCAD.Vector(L / 2.0 + span / 2.0, W / 2.0, -1.0))
            shape = bar.fuse(f_l).fuse(f_r).fuse(boss).cut(Part.makeCompound([h1, h2])).removeSplitter()
            engrave_z_top = boss_h
            engrave_d = 0.40

    elif cat == "hinge":
        # Printable door hinge leaf bracket (flat plate + knuckle barrel, zero overhang)
        L = float(pr["length"])
        W = float(pr["width"])
        H = float(pr["height"])
        pt = float(pr["plate_t"])
        hd = float(pr["hole_d"])
        span = float(pr["pin_span"])
        plate = Part.makeBox(L, W, pt, FreeCAD.Vector(0, 0, 0))
        knuckle = Part.makeBox(5.5, W, H, FreeCAD.Vector(L / 2.0 - 2.75, 0, 0))
        # Pivot pin bore through knuckle along Y axis + two M3 mounting holes in leaves
        pin = Part.makeCylinder(1.2, W + 2.0, FreeCAD.Vector(L / 2.0, -1.0, H - 2.2), FreeCAD.Vector(0, 1, 0))
        h1 = Part.makeCylinder(hd / 2.0, pt + 2.0, FreeCAD.Vector(L / 2.0 - span / 2.0, W / 2.0, -1.0))
        h2 = Part.makeCylinder(hd / 2.0, pt + 2.0, FreeCAD.Vector(L / 2.0 + span / 2.0, W / 2.0, -1.0))
        shape = plate.fuse(knuckle).cut(Part.makeCompound([pin, h1, h2])).removeSplitter()
        engrave_z_top = pt
        engrave_d = 0.35
    else:
        raise ValueError(f"Unsupported support category: {cat}")

    # Engrave ID + dims on flat upper face (skip cylindrical standoffs whose top ring is only 1.7mm wide; emboss/mark flat flange instead)
    engraved_ok = False
    if cat == "standoff":
        # Add tiny flat index tab on flange perimeter so ID is visibly engraved on solid flat face
        fod = float(pr["flange_od"])
        fh = float(pr["flange_h"])
        tab = Part.makeBox(8.0, 5.0, fh, FreeCAD.Vector(fod - 1.5, fod / 2.0 - 2.5, 0.0))
        shape = shape.fuse(tab).removeSplitter()
        eng_spec = pd_mod.EngraveSpec(
            line1=sup.engrave.line1,
            line2="",
            cx=fod + 2.6,
            cy=fod / 2.0,
            font_h=2.0,
            rotated_90=False,
        )
        shape, engraved_ok = safe_engrave_top_face(shape, eng_spec, fh, 0.40)
    elif cat == "bracket":
        # Place text on bottom gusset diagonal corner
        arm = float(pr["arm"])
        wt = float(pr["wall_t"])
        eng_spec = pd_mod.EngraveSpec(
            line1=sup.engrave.line1,
            line2="",
            cx=wt + (arm - wt) * 0.30,
            cy=wt + (arm - wt) * 0.24,
            font_h=max(2.0, min(2.6, (arm - wt) * 0.14)),
            rotated_90=False,
        )
        shape, engraved_ok = safe_engrave_top_face(shape, eng_spec, wt, 0.45)
    elif cat == "hinge":
        # Engrave on top of knuckle
        L = float(pr["length"])
        W = float(pr["width"])
        H = float(pr["height"])
        eng_spec = pd_mod.EngraveSpec(sup.engrave.line1, "", L / 2.0, W / 2.0, 2.0, True)
        shape, engraved_ok = safe_engrave_top_face(shape, eng_spec, H, 0.35)
    elif sup.part_id == "SUP09_RELAY_CADDY_44P5X20P5":
        # Place along front frame rail (outside center cutout)
        ox = float(pr["outer_x"])
        bh = float(pr["base_h"])
        eng_spec = pd_mod.EngraveSpec("SUP09 52x28x8", "", ox / 2.0, 4.5, 2.6, False)
        shape, engraved_ok = safe_engrave_top_face(shape, eng_spec, bh, 0.45)
    elif sup.part_id == "SUP07_PCB_CARRIER_FRAME_90X70":
        ox = float(pr["outer_x"])
        bh = float(pr["base_h"])
        eng_spec = pd_mod.EngraveSpec("SUP07 100x80x10", "", ox / 2.0, 6.5, 3.6, False)
        shape, engraved_ok = safe_engrave_top_face(shape, eng_spec, bh, 0.50)
    elif sup.part_id == "SUP11_SPEAKER_28MM_RETAINER":
        L = float(pr["length"])
        W = float(pr["width"])
        eng_spec = pd_mod.EngraveSpec("S11", "", L / 2.0, W / 2.0, 2.6, False)
        shape, engraved_ok = safe_engrave_top_face(shape, eng_spec, engrave_z_top, 0.40)
    elif sup.part_id == "SUP03_SEAM_JOIN_CLIP":
        L = float(pr["length"])
        sw = float(pr["slot_w"])
        wt = float(pr["wall_t"])
        eng_spec = pd_mod.EngraveSpec("SUP03", "", L / 2.0, wt + sw / 2.0, 2.1, False)
        shape, engraved_ok = safe_engrave_top_face(shape, eng_spec, engrave_z_top, 0.40)
    else:
        shape, engraved_ok = safe_engrave_top_face(shape, sup.engrave, engrave_z_top, engrave_d)

    # Normalize to print-ready coordinates (X_min=0, Y_min=0, Z_min=0)
    bb = shape.BoundBox
    shape.translate(FreeCAD.Vector(-bb.XMin, -bb.YMin, -bb.ZMin))
    bb = shape.BoundBox

    meta = {
        "part_id": sup.part_id,
        "kind": "support",
        "category": sup.category,
        "qty": sup.qty,
        "vi_name": sup.vi_name,
        "mating_source": sup.mating_source,
        "print_bbox_mm": [round(bb.XLength, 3), round(bb.YLength, 3), round(bb.ZLength, 3)],
        "print_z_min": round(bb.ZMin, 4),
        "volume_mm3": round(shape.Volume, 3),
        "solids": len(shape.Solids),
        "valid": bool(shape.isValid()),
        "engraved_ok": engraved_ok,
        "engrave_text": f"{sup.engrave.line1} {sup.engrave.line2}".strip(),
        "assembly_placements": list(sup.assembly_placements),
        "exclude_from_default_assembly": sup.exclude_from_default_assembly,
        "color_rgb": list(sup.color_rgb),
        "notes": sup.notes,
    }
    return shape, meta


def export_shape_step_stl(shape: Any, part_id: str) -> tuple[pathlib.Path, pathlib.Path, int]:
    """Export exact BRep STEP and watertight binary STL."""
    STEP_DIR.mkdir(parents=True, exist_ok=True)
    STL_DIR.mkdir(parents=True, exist_ok=True)
    step_path = STEP_DIR / f"{part_id}.step"
    stl_path = STL_DIR / f"{part_id}.stl"

    shape.exportStep(str(step_path))
    mesh_obj = MeshPart.meshFromShape(
        Shape=shape,
        LinearDeflection=0.05,
        AngularDeflection=0.25,
        Relative=False,
    )
    mesh_obj.write(str(stl_path), Format="STL")
    return step_path, stl_path, int(mesh_obj.CountFacets)


def parse_args() -> argparse.Namespace:
    # Support both CLI args and env vars (FreeCADCmd strips unknown CLI flags)
    argv = sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = [a for a in argv if not a.endswith(".py")]
    ap = argparse.ArgumentParser(description="Build 3D-printable house panels & supports")
    ap.add_argument("--parts", type=str, default=os.environ.get("PRINT3D_PARTS", ""), help="Comma-separated part_ids to build (default: all)")
    ap.add_argument("--shard", type=str, default=os.environ.get("PRINT3D_SHARD", ""), help="Named shard from print_domain.get_swarm_shards()")
    args, _unknown = ap.parse_known_args(argv)
    return args


def main() -> int:
    t0 = time.time()
    args = parse_args()
    cfg = pd_mod.PrintConfig()
    pieces, split_summary = pd_mod.build_panel_piece_specs(cfg)
    supports = pd_mod.build_support_specs(cfg)
    panels_raw, _ = md.build_design()
    panel_map = {ps.panel_id: ps for ps in panels_raw}

    target_ids: set[str] | None = None
    if args.shard:
        shards = pd_mod.get_swarm_shards(cfg)
        if args.shard not in shards:
            raise ValueError(f"Unknown shard '{args.shard}'. Available: {list(shards.keys())}")
        target_ids = set(shards[args.shard])
    elif args.parts:
        target_ids = {s.strip() for s in args.parts.split(",") if s.strip()}

    META_DIR.mkdir(parents=True, exist_ok=True)
    base_cache: dict[str, tuple[Any, dict[str, Any]]] = {}
    built: list[dict[str, Any]] = []
    failures: list[str] = []

    for piece in pieces:
        if target_ids is not None and piece.part_id not in target_ids:
            continue
        shape, meta = build_panel_piece_solid(piece, panel_map[piece.source_panel_id], cfg, base_cache)
        step_p, stl_p, facets = export_shape_step_stl(shape, piece.part_id)
        meta["step_file"] = f"STEP/{step_p.name}"
        meta["stl_file"] = f"STL/{stl_p.name}"
        meta["stl_facets"] = facets
        meta["bed_fit"] = (
            meta["print_bbox_mm"][0] <= cfg.usable_x + 0.01
            and meta["print_bbox_mm"][1] <= cfg.usable_y + 0.01
            and meta["print_bbox_mm"][2] <= cfg.usable_z + 0.01
        )
        with (META_DIR / f"{piece.part_id}.json").open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        status = "OK" if (meta["valid"] and meta["solids"] == 1 and meta["bed_fit"]) else "FAIL"
        print(f"[{status}] {piece.part_id}: bbox={meta['print_bbox_mm']} vol={meta['volume_mm3']}mm3 eng={meta['engraved_ok']} facets={facets}")
        if status != "OK":
            failures.append(piece.part_id)
        built.append(meta)

    for sup in supports:
        if target_ids is not None and sup.part_id not in target_ids:
            continue
        shape, meta = build_support_solid(sup, cfg)
        step_p, stl_p, facets = export_shape_step_stl(shape, sup.part_id)
        meta["step_file"] = f"STEP/{step_p.name}"
        meta["stl_file"] = f"STL/{stl_p.name}"
        meta["stl_facets"] = facets
        meta["bed_fit"] = (
            meta["print_bbox_mm"][0] <= cfg.usable_x + 0.01
            and meta["print_bbox_mm"][1] <= cfg.usable_y + 0.01
            and meta["print_bbox_mm"][2] <= cfg.usable_z + 0.01
        )
        with (META_DIR / f"{sup.part_id}.json").open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        status = "OK" if (meta["valid"] and meta["solids"] == 1 and meta["bed_fit"]) else "FAIL"
        print(f"[{status}] {sup.part_id}: bbox={meta['print_bbox_mm']} vol={meta['volume_mm3']}mm3 eng={meta['engraved_ok']} facets={facets}")
        if status != "OK":
            failures.append(sup.part_id)
        built.append(meta)

    elapsed = round(time.time() - t0, 2)
    print(f"DONE: built {len(built)} parts in {elapsed}s (failures={len(failures)})")
    return 1 if failures else 0


if __name__ in ("__main__", "build_print_parts"):
    rc = main()
    if rc != 0:
        raise SystemExit(rc)
