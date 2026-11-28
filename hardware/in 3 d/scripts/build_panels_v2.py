"""Headless FreeCAD 1.1 Builder for 3D-Print Set v2 Screwless Panels (180x200x250 bed).

Run via FreeCADCmd:
    "C:\\Users\\LENOVO\\AppData\\Local\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe" "hardware/in 3 d/scripts/build_panels_v2.py"
    "C:\\Users\\LENOVO\\AppData\\Local\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe" "hardware/in 3 d/scripts/build_panels_v2.py" -- --parts P17_BASE_JOINER,P01A_BASE_TECH_piece1of3

Outputs (under `hardware/in 3 d/`):
    - `parts/P*.step`       Exact BRep CAD solid (print-oriented, X_min=Y_min=Z_min=0)
    - `parts/P*.stl`        Watertight binary STL mesh (print-oriented, X_min=Y_min=Z_min=0)
    - `build_meta/P*.json`  Per-part geometry & assembly metadata
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

import cad_common
import lightweight_policy as lp
import mica_design as md
import print_domain as pd_mod


_CACHED_PIECES_AND_SPLITS: tuple[list[pd_mod.PanelPieceSpec], dict[str, Any]] | None = None


def _get_pieces_and_splits(cfg: pd_mod.PrintConfig) -> tuple[list[pd_mod.PanelPieceSpec], dict[str, Any]]:
    global _CACHED_PIECES_AND_SPLITS
    if _CACHED_PIECES_AND_SPLITS is None:
        _CACHED_PIECES_AND_SPLITS = pd_mod.build_panel_piece_specs(cfg)
    return _CACHED_PIECES_AND_SPLITS


def _build_2d_safe_face(
    ev: dict[str, Any],
    panel_id: str,
    panel_pieces: list[pd_mod.PanelPieceSpec],
    u_cuts: list[float],
    v_cuts: list[float],
    engrave_boxes: list[tuple[float, float, float, float]],
    ribs: list[tuple[float, float, float, float]],
    margin_mm: float,
    for_cutouts: bool,
) -> Any:
    """Build exact 2D FreeCAD Face of safe interior zones >= margin_mm from every edge/hole/dovetail/keepout."""
    W = float(ev["width"])
    H = float(ev["height"])
    poly = ev["outer_poly"]
    vecs = [FreeCAD.Vector(x, y, 0.0) for (x, y) in poly]
    vecs.append(vecs[0])
    outer_f = Part.Face(Part.makePolygon(vecs))

    bufs: list[Any] = []
    # 1. Outer boundary rim buffer (exact >= margin_mm from every outer edge, tab, notch, cutaway)
    n_poly = len(poly)
    for i in range(n_poly):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n_poly]
        xlo, xhi = min(x1, x2), max(x1, x2)
        ylo, yhi = min(y1, y2), max(y1, y2)
        if abs(x1 - x2) < 1e-3:
            bufs.append(Part.makePlane(2.0 * margin_mm, (yhi - ylo) + 2.0 * margin_mm, FreeCAD.Vector(xlo - margin_mm, ylo - margin_mm, 0.0)))
        elif abs(y1 - y2) < 1e-3:
            bufs.append(Part.makePlane((xhi - xlo) + 2.0 * margin_mm, 2.0 * margin_mm, FreeCAD.Vector(xlo - margin_mm, ylo - margin_mm, 0.0)))
        else:
            L = math.hypot(x2 - x1, y2 - y1)
            nx, ny = -(y2 - y1) / L * margin_mm, (x2 - x1) / L * margin_mm
            bufs.append(Part.Face(Part.makePolygon([
                FreeCAD.Vector(x1 + nx, y1 + ny, 0.0),
                FreeCAD.Vector(x2 + nx, y2 + ny, 0.0),
                FreeCAD.Vector(x2 - nx, y2 - ny, 0.0),
                FreeCAD.Vector(x1 - nx, y1 - ny, 0.0),
                FreeCAD.Vector(x1 + nx, y1 + ny, 0.0),
            ])))
            bufs.append(Part.Face(Part.Wire(Part.makeCircle(margin_mm, FreeCAD.Vector(x1, y1, 0.0)))))

    # 2. Inner rects (slots, mortises, BedWindow, DHT11_Airflow, SlotServoShelf) >= margin_mm collar
    for r in ev["inner_rects"]:
        bufs.append(Part.makePlane(
            r["du"] + 2.0 * margin_mm,
            r["dv"] + 2.0 * margin_mm,
            FreeCAD.Vector(r["u0"] - margin_mm, r["v0"] - margin_mm, 0.0),
        ))

    # 3. Functional circular holes >= margin_mm radial collar
    for c in ev["circles"]:
        bufs.append(Part.Face(Part.Wire(Part.makeCircle(c["dia"] / 2.0 + margin_mm, FreeCAD.Vector(c["cx"], c["cy"], 0.0)))))

    # 4. Split seams: straight seam >= margin_mm each side, PLUS every dovetail tooth >= depth + margin_mm!
    seam_straight = margin_mm if for_cutouts else float(lp.SEAM_BAND_HALF_MM)
    for uc in u_cuts:
        bufs.append(Part.makePlane(2.0 * seam_straight, H + 4.0, FreeCAD.Vector(uc - seam_straight, -2.0, 0.0)))
    for vc in v_cuts:
        bufs.append(Part.makePlane(W + 4.0, 2.0 * seam_straight, FreeCAD.Vector(-2.0, vc - seam_straight, 0.0)))
    if for_cutouts:
        for pc in panel_pieces:
            for dt in pc.dovetails:
                if dt.axis == "U":
                    x0 = dt.cut_pos - dt.depth - margin_mm
                    x1 = dt.cut_pos + dt.depth + margin_mm
                    y0 = dt.center_along - dt.head_w / 2.0 - margin_mm
                    y1 = dt.center_along + dt.head_w / 2.0 + margin_mm
                else:
                    x0 = dt.center_along - dt.head_w / 2.0 - margin_mm
                    x1 = dt.center_along + dt.head_w / 2.0 + margin_mm
                    y0 = dt.cut_pos - dt.depth - margin_mm
                    y1 = dt.cut_pos + dt.depth + margin_mm
                bufs.append(Part.makePlane(x1 - x0, y1 - y0, FreeCAD.Vector(x0, y0, 0.0)))

    # 5. Engraving pad islands (full 3.0 mm + 2.5 mm margin)
    eng_m = float(lp.ENGRAVE_ISLAND_MARGIN_MM)
    for ex0, ey0, ex1, ey1 in engrave_boxes:
        bufs.append(Part.makePlane((ex1 - ex0) + 2.0 * eng_m, (ey1 - ey0) + 2.0 * eng_m, FreeCAD.Vector(ex0 - eng_m, ey0 - eng_m, 0.0)))

    # 6. Anti-sag stiffening ribs (full 3.0 mm)
    for rx0, ry0, rx1, ry1 in ribs:
        bufs.append(Part.makePlane(rx1 - rx0, ry1 - ry0, FreeCAD.Vector(rx0, ry0, 0.0)))

    # 7. Policy PANEL_KEEPOUT_ZONES
    for kz in lp.PANEL_KEEPOUT_ZONES.get(panel_id, ()):
        if for_cutouts:
            if not kz.block_through_cutouts:
                continue
            # Structural spine/stiffening ribs already encode their full width; safety zones keep full margin_mm
            km = 0.0 if kz.name in ("MID_WALL_SPINE_RIB", "LONGITUDINAL_STIFF_RIB", "P02_MID_T_SPINE") else margin_mm
            bufs.append(Part.makePlane((kz.u1 - kz.u0) + 2.0 * km, (kz.v1 - kz.v0) + 2.0 * km, FreeCAD.Vector(kz.u0 - km, kz.v0 - km, 0.0)))
        else:
            if not kz.block_thinning:
                continue
            bufs.append(Part.makePlane(kz.u1 - kz.u0, kz.v1 - kz.v0, FreeCAD.Vector(kz.u0, kz.v0, 0.0)))

    return outer_f.cut(Part.makeCompound(bufs))


def _apply_lightweight_pockets_and_hexes(
    body: Any,
    pspec: md.PanelSpec,
    ev: dict[str, Any],
    cfg: pd_mod.PrintConfig,
) -> tuple[Any, dict[str, Any]]:
    """R5 (2.2 mm coffered recessed web) + R4 (conformal clipped hex honeycomb cutouts)."""
    all_pieces, split_summary = _get_pieces_and_splits(cfg)
    panel_pieces = [pc for pc in all_pieces if pc.source_panel_id == pspec.panel_id]
    sp = split_summary[pspec.panel_id]
    u_cuts = list(sp.get("u_cuts_mm", []))
    v_cuts = list(sp.get("v_cuts_mm", []))

    lw_plan = pd_mod.plan_panel_lightweight_features(
        panel_id=pspec.panel_id,
        ev=ev,
        panel_pieces=panel_pieces,
        u_cuts=u_cuts,
        v_cuts=v_cuts,
        cfg=cfg,
    )
    if not lw_plan["lightweight_enabled"]:
        return body, lw_plan

    W = float(ev["width"])
    H = float(ev["height"])
    T = float(cfg.T_mm)
    web_z = float(lp.WEB_THICKNESS_MM)
    slab_h = (T - web_z) + 1.0  # extends 1.0 mm above Z=T for clean boolean cut
    edge_m = float(lp.HEX_EDGE_MARGIN_MM)

    safe_cutout_face: Any = None
    if lw_plan.get("cutout_enabled", False):
        safe_cutout_face = _build_2d_safe_face(
            ev=ev,
            panel_id=pspec.panel_id,
            panel_pieces=panel_pieces,
            u_cuts=u_cuts,
            v_cuts=v_cuts,
            engrave_boxes=lw_plan["engrave_boxes"],
            ribs=lw_plan["ribs"],
            margin_mm=edge_m,
            for_cutouts=True,
        )

    # 1. R5 Coffered thinning pocket (Z in [2.2..3.0], bottom stays flat Z=0 -> 0 supports!)
    pocket_area_mm2 = 0.0
    if lw_plan.get("thinning_enabled", False):
        if safe_cutout_face is not None:
            # Align pocket boundary cleanly with safe_cutout_face so zero internal step-walls bloat honeycomb!
            pocket_2d = safe_cutout_face
        else:
            pocket_2d = _build_2d_safe_face(
                ev=ev,
                panel_id=pspec.panel_id,
                panel_pieces=panel_pieces,
                u_cuts=u_cuts,
                v_cuts=v_cuts,
                engrave_boxes=lw_plan["engrave_boxes"],
                ribs=lw_plan["ribs"],
                margin_mm=float(lp.JOINT_RIM_MARGIN_MM),
                for_cutouts=False,
            )
        kept_pockets: list[Any] = []
        for f in pocket_2d.Faces:
            bb = f.BoundBox
            if min(bb.XLength, bb.YLength) >= 4.0 and f.Area >= 35.0:
                sol = f.extrude(FreeCAD.Vector(0.0, 0.0, slab_h))
                sol.translate(FreeCAD.Vector(0.0, 0.0, web_z))
                kept_pockets.append(sol)
                pocket_area_mm2 += float(f.Area)
        if kept_pockets:
            body = body.cut(Part.makeCompound(kept_pockets)).removeSplitter()

    # 2. R4 Conformal clipped hexagonal honeycomb through-cutouts (exact >= 3.2 mm ribs, >= 6.5 mm margin)
    hex_centers_out: list[tuple[float, float]] = []
    hex_margins_out: list[float] = []
    hex_areas_out: list[float] = []
    if safe_cutout_face is not None and len(safe_cutout_face.Faces) > 0:
        F = float(pd_mod.CONFORMAL_HEX_FLAT_TO_FLAT_MM)
        RIB = float(lp.HEX_MIN_RIB_MM)
        P = F + RIB
        DY = P * math.sqrt(3.0) / 2.0

        # Pick best lattice phase (2x2 shift) maximizing total clipped cutout area
        best_cells: list[tuple[Any, float, float, float]] = []
        best_area = -1.0
        for iu in range(2):
            for iv in range(2):
                off_u = iu * P / 2.0
                off_v = iv * DY / 2.0
                cur_cells: list[tuple[Any, float, float, float]] = []
                cur_area = 0.0
                row = 0
                cy = off_v
                while cy <= H + DY:
                    cx = off_u + (P / 2.0 if row % 2 == 1 else 0.0)
                    while cx <= W + P:
                        pts = pd_mod._hex_vertices(cx, cy, F)
                        vecs = [FreeCAD.Vector(x, y, 0.0) for (x, y) in pts]
                        vecs.append(vecs[0])
                        hf = Part.Face(Part.makePolygon(vecs))
                        inter = hf.common(safe_cutout_face)
                        for f in inter.Faces:
                            bb = f.BoundBox
                            area = float(f.Area)
                            if area >= 35.0 and min(bb.XLength, bb.YLength) >= 4.0:
                                com = f.CenterOfMass
                                cur_cells.append((f, round(float(com.x), 3), round(float(com.y), 3), round(area, 2)))
                                cur_area += area
                        cx += P
                    cy += DY
                    row += 1
                if cur_area > best_area:
                    best_area = cur_area
                    best_cells = cur_cells

        if best_cells:
            cut_solids: list[Any] = []
            for f, ccx, ccy, area in best_cells:
                sol = f.extrude(FreeCAD.Vector(0.0, 0.0, T + 2.0))
                sol.translate(FreeCAD.Vector(0.0, 0.0, -1.0))
                cut_solids.append(sol)
                hex_centers_out.append((ccx, ccy))
                hex_margins_out.append(edge_m)
                hex_areas_out.append(area)
            body = body.cut(Part.makeCompound(cut_solids)).removeSplitter()

    lw_plan["hex_centers"] = hex_centers_out
    lw_plan["hex_margins"] = hex_margins_out
    lw_plan["hex_areas"] = hex_areas_out
    lw_plan["conformal_clipped"] = bool(hex_centers_out)
    lw_plan["pocket_area_mm2"] = round(pocket_area_mm2, 2)
    return body, lw_plan


P17_TENON_CENTERS: tuple[tuple[float, float], ...] = (
    (12.0, 6.0),
    (52.0, 6.0),
    (12.0, 22.0),
    (52.0, 22.0),
)
P17_TENON_SIZE_XY: tuple[float, float] = (8.0, 4.0)
P17_TENON_HEIGHT: float = 3.0


def build_flat_panel_solid(
    pspec: md.PanelSpec,
    cfg: pd_mod.PrintConfig,
    mortise_map: dict[str, list[pd_mod.MortiseSlotSpec]],
) -> tuple[Any, dict[str, Any]]:
    """Build exact screwless flat panel solid on Z in [0, T_mm] with bottom-left at (0, 0)."""
    p = md.default_param_values(T_mm=cfg.T_mm, tab_clr=cfg.tab_clr)
    ev = pd_mod.evaluate_screwless_panel_2d(pspec, cfg)
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
        if c.kind in pd_mod.STRIPPED_FASTENER_KINDS:
            continue
        cu = md.eval_expr(c.u, p) + su
        cv = md.eval_expr(c.v, p) + sv
        rad = md.eval_expr(c.dia, p) / 2.0
        cut_solids.append(
            Part.makeCylinder(rad, T + 2.0, FreeCAD.Vector(cu, cv, -1.0), FreeCAD.Vector(0, 0, 1))
        )

    for mt in mortise_map.get(pspec.panel_id, []):
        cut_solids.append(
            Part.makeBox(
                mt.du,
                mt.dv,
                T + 2.0,
                FreeCAD.Vector(mt.cx - mt.du / 2.0, mt.cy - mt.dv / 2.0, -1.0),
            )
        )

    if cut_solids:
        body = body.cut(Part.makeCompound(cut_solids))
        body = body.removeSplitter()

    if pspec.panel_id == "P07_SERVO_SHELF":
        # Two integral non-stalling end-stop lugs on P07 underside (Z < 0 in unflipped local frame):
        # 1) Closed stop (-2 deg): world X=89.5..92.5 (u_s=42.5..45.5), Y=195.6..197.3 (v_s=3.60..5.30),
        #    Z=102.5..108.5 (z=-6.0..0.5, clears P08 door top Z<=102.0 and MORT_SG90_R v_s>=6.35!)
        lug_closed = Part.makeBox(3.0, 1.7, 6.5, FreeCAD.Vector(42.5, 3.60, -6.0))
        # 2) Open stop (+92 deg): world (72.3, 214.0) -> (u_s=25.3, v_s=22.0), Dia 3.0 mm,
        #    Z=98.5..108.5 (z=-10.0..0.5, stops SG90 white horn cleanly at +92 deg!)
        lug_open = Part.makeCylinder(1.5, 10.5, FreeCAD.Vector(25.3, 22.0, -10.0), FreeCAD.Vector(0, 0, 1))
        body = body.fuse(lug_closed).fuse(lug_open).removeSplitter()

    if pspec.panel_id == "P17_BASE_JOINER":
        tx_w, ty_w = P17_TENON_SIZE_XY
        # Overlap base Z=0..T so BRep fusion has no coplanar seam at Z=T.
        for cx, cy in P17_TENON_CENTERS:
            tenon = Part.makeBox(
                tx_w,
                ty_w,
                T + P17_TENON_HEIGHT,
                FreeCAD.Vector(cx - tx_w / 2.0, cy - ty_w / 2.0, 0.0),
            )
            body = body.fuse(tenon)
        body = body.removeSplitter()

    if pspec.panel_id in lp.THINNED_AND_CUTOUT_PANELS or pspec.panel_id in pd_mod.CONFORMAL_CUTOUT_PANELS:
        body, lw_plan = _apply_lightweight_pockets_and_hexes(body, pspec, ev, cfg)
        ev["lightweight_plan"] = lw_plan
    else:
        ev["lightweight_plan"] = {
            "lightweight_enabled": False,
            "web_thickness_mm": cfg.T_mm,
            "rim_thickness_mm": cfg.T_mm,
            "pocket_depth_mm": 0.0,
            "max_unsupported_span_mm": 0.0,
            "hex_flat_to_flat_mm": None,
            "hex_min_rib_mm": None,
            "hex_centers": [],
            "hex_margins": [],
            "min_edge_margin_mm": None,
            "relay_psu_closed": True,
        }

    return body, ev


def _make_dovetail_prism(dt: pd_mod.DovetailJointSpec, is_female: bool, T_mm: float) -> Any:
    """Build an extruded trapezoidal dovetail prism (exact male or clearance-enlarged female)."""
    clr = dt.clearance if is_female else 0.0
    depth = dt.depth + clr
    half_neck = dt.neck_w / 2.0 + clr
    half_head = dt.head_w / 2.0 + clr
    c = dt.cut_pos
    ca = dt.center_along
    ext_sign = -1.0 if dt.male_side == +1 else +1.0
    back_off = -ext_sign * 0.8

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
    mortise_map: dict[str, list[pd_mod.MortiseSlotSpec]],
    base_solid_cache: dict[str, tuple[Any, dict[str, Any]]],
) -> tuple[Any, dict[str, Any]]:
    """Build one print-ready screwless panel or dovetail split piece with engraved ID + bbox."""
    if piece.source_panel_id not in base_solid_cache:
        base_solid_cache[piece.source_panel_id] = build_flat_panel_solid(pspec, cfg, mortise_map)
    full_solid, ev = base_solid_cache[piece.source_panel_id]

    if piece.piece_count == 1:
        shape = full_solid.copy()
    else:
        u_lo, u_hi = piece.u_range
        v_lo, v_hi = piece.v_range
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

    bb_pre = shape.BoundBox
    flipped_x180 = False
    flip_pre_min: list[float] | None = None
    flip_pre_max: list[float] | None = None

    if piece.source_panel_id == "P07_SERVO_SHELF":
        # Print P07 flipped upside-down (180 deg around X) so Z_world=111.5 sits flat on Z=0
        # and the 2 integral underside end-stop lugs point UP with ZERO overhang/supports!
        flipped_x180 = True
        flip_pre_min = [round(bb_pre.XMin, 4), round(bb_pre.YMin, 4), round(bb_pre.ZMin, 4)]
        flip_pre_max = [round(bb_pre.XMax, 4), round(bb_pre.YMax, 4), round(bb_pre.ZMax, 4)]
        shape.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 180.0)
        bb_f = shape.BoundBox
        shape.translate(FreeCAD.Vector(-bb_f.XMin, -bb_f.YMin, -bb_f.ZMin))
        bb_f2 = shape.BoundBox
        real_engrave = pd_mod.EngraveSpec(
            line1="P07",
            line2=f"{bb_f2.XLength:.0f}x{bb_f2.YLength:.0f}x{bb_f2.ZLength:.0f}",
            cx=12.0,
            cy=6.5,
            font_h=2.4,
            rotated_90=False,
        )
        shape_eng, engraved_ok = cad_common.safe_engrave_top_face(
            shape, real_engrave, cfg.T_mm, cfg.engrave_depth
        )
        shape_print = shape_eng.copy()
        bb_p = shape_print.BoundBox
        shape_print.translate(FreeCAD.Vector(-bb_p.XMin, -bb_p.YMin, -bb_p.ZMin))
        local_min = tuple(flip_pre_min)
        local_max = tuple(flip_pre_max)
    else:
        if piece.source_panel_id == "P17_BASE_JOINER":
            real_engrave = pd_mod.EngraveSpec(
                line1="P17",
                line2=f"{bb_pre.XLength:.0f}x{bb_pre.YLength:.0f}x{bb_pre.ZLength:.0f}mm",
                cx=32.0,
                cy=14.0,
                font_h=3.4,
                rotated_90=False,
            )
        else:
            real_engrave = pd_mod.EngraveSpec(
                line1=piece.engrave.line1,
                line2=f"{bb_pre.XLength:.0f}x{bb_pre.YLength:.0f}x{bb_pre.ZLength:.0f}mm",
                cx=piece.engrave.cx,
                cy=piece.engrave.cy,
                font_h=piece.engrave.font_h,
                rotated_90=piece.engrave.rotated_90,
            )

        shape_eng, engraved_ok = cad_common.safe_engrave_top_face(
            shape, real_engrave, cfg.T_mm, cfg.engrave_depth
        )

        bb_local = shape_eng.BoundBox
        local_min = (round(bb_local.XMin, 4), round(bb_local.YMin, 4), round(bb_local.ZMin, 4))
        local_max = (round(bb_local.XMax, 4), round(bb_local.YMax, 4), round(bb_local.ZMax, 4))

        shape_print = shape_eng.copy()
        shape_print.translate(FreeCAD.Vector(-bb_local.XMin, -bb_local.YMin, -bb_local.ZMin))

    bb_p = shape_print.BoundBox
    print_bbox = [round(bb_p.XLength, 3), round(bb_p.YLength, 3), round(bb_p.ZLength, 3)]

    lw_plan = ev.get("lightweight_plan", {})
    u_lo, u_hi = piece.u_range
    v_lo, v_hi = piece.v_range
    piece_hex_centers: list[list[float]] = []
    piece_hex_margins: list[float] = []
    piece_hex_area = 0.0
    hex_areas = lw_plan.get("hex_areas", [])
    for idx_h, ((hcx, hcy), hmarg) in enumerate(zip(lw_plan.get("hex_centers", []), lw_plan.get("hex_margins", []))):
        if u_lo <= hcx <= u_hi and v_lo <= hcy <= v_hi:
            piece_hex_centers.append([hcx, hcy])
            piece_hex_margins.append(hmarg)
            if idx_h < len(hex_areas):
                piece_hex_area += float(hex_areas[idx_h])
    piece_cutout_cnt = len(piece_hex_centers)
    piece_hex_f = float(lw_plan.get("hex_flat_to_flat_mm") or pd_mod.CONFORMAL_HEX_FLAT_TO_FLAT_MM)

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
        "print_flipped_x180": flipped_x180,
        "print_bbox_mm": print_bbox,
        "print_z_min": round(bb_p.ZMin, 4),
        "volume_mm3": round(shape_print.Volume, 3),
        "solids": len(shape_print.Solids),
        "valid": bool(shape_print.isValid()),
        "engraved_ok": engraved_ok,
        "engrave_text": f"{real_engrave.line1} | {real_engrave.line2}",
        "dovetail_count": len(piece.dovetails),
        "mortise_count": len(piece.mortises),
        "stripped_fastener_holes": list(piece.stripped_fastener_holes),
        "kept_functional_holes": list(piece.kept_functional_holes),
        "bed_fit": cad_common.fits_bed_rotatable(print_bbox, cfg),
        "color_rgb": list(piece.color_rgb),
        "lightweight": {
            "enabled": bool(lw_plan.get("lightweight_enabled", False)),
            "web_thickness_mm": float(lw_plan.get("web_thickness_mm", cfg.T_mm)),
            "rim_thickness_mm": float(lw_plan.get("rim_thickness_mm", cfg.T_mm)),
            "pocket_depth_mm": float(lw_plan.get("pocket_depth_mm", 0.0)),
            "max_unsupported_span_mm": float(lw_plan.get("max_unsupported_span_mm", 0.0)),
            "cutout_count": piece_cutout_cnt,
            "cutout_area_mm2": round(piece_hex_area, 2),
            "conformal_clipped": bool(lw_plan.get("conformal_clipped", False)) and piece_cutout_cnt > 0,
            "hex_flat_to_flat_mm": piece_hex_f if piece_cutout_cnt > 0 else None,
            "min_rib_mm": lp.HEX_MIN_RIB_MM if piece_cutout_cnt > 0 else None,
            "min_edge_margin_mm": round(min(piece_hex_margins), 3) if piece_hex_margins else None,
            "relay_psu_closed": bool(lw_plan.get("relay_psu_closed", True)),
            "cutout_centers_local_uv": piece_hex_centers,
        },
    }
    return shape_print, meta


def parse_args() -> argparse.Namespace:
    argv = sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = [a for a in argv if not a.endswith(".py")]
    ap = argparse.ArgumentParser(description="Build 3D-Print Set v2 screwless panels")
    ap.add_argument(
        "--parts",
        type=str,
        default=os.environ.get("PRINT3D_PARTS", ""),
        help="Comma-separated panel part_ids to build (default: all)",
    )
    args, _unknown = ap.parse_known_args(argv)
    return args


def _cleanup_stale_panel_outputs(expected_ids: set[str]) -> None:
    """Remove obsolete panel outputs (P*) not in the current v2 panel piece set."""
    for folder, exts in (
        (cad_common.PARTS_DIR, (".stl", ".step")),
        (cad_common.META_DIR, (".json",)),
    ):
        if not folder.exists():
            continue
        for fpath in folder.glob("P*"):
            if fpath.suffix.lower() in exts and fpath.stem not in expected_ids:
                fpath.unlink()


def main() -> int:
    t0 = time.time()
    args = parse_args()
    cfg = pd_mod.PrintConfig()
    pieces, _split_summary = pd_mod.build_panel_piece_specs(cfg)
    mortise_map = pd_mod.build_panel_mortise_map(cfg)
    panels_raw, _ = md.build_design()
    panel_map = {ps.panel_id: ps for ps in panels_raw}

    target_ids: set[str] | None = None
    if args.parts:
        target_ids = {s.strip() for s in args.parts.split(",") if s.strip()}
    else:
        _cleanup_stale_panel_outputs({pc.part_id for pc in pieces})

    base_cache: dict[str, tuple[Any, dict[str, Any]]] = {}
    built: list[dict[str, Any]] = []
    failures: list[str] = []

    for piece in pieces:
        if target_ids is not None and piece.part_id not in target_ids:
            continue
        shape, meta = build_panel_piece_solid(
            piece, panel_map[piece.source_panel_id], cfg, mortise_map, base_cache
        )
        step_p, stl_p, facets = cad_common.export_part_step_stl(shape, piece.part_id)
        meta["step_file"] = f"parts/{step_p.name}"
        meta["stl_file"] = f"parts/{stl_p.name}"
        meta["stl_facets"] = facets
        cad_common.save_part_meta(piece.part_id, meta)

        ok = (
            meta["valid"]
            and meta["solids"] == 1
            and meta["bed_fit"]
            and meta["engraved_ok"]
            and abs(meta["print_z_min"]) < 1e-3
        )
        status = "OK" if ok else "FAIL"
        print(
            f"[{status}] {piece.part_id}: bbox={meta['print_bbox_mm']} "
            f"vol={meta['volume_mm3']}mm3 mort={meta['mortise_count']} "
            f"dt={meta['dovetail_count']} eng={meta['engraved_ok']} facets={facets}"
        )
        if not ok:
            failures.append(piece.part_id)
        built.append(meta)

    elapsed = round(time.time() - t0, 2)
    print(f"DONE: built {len(built)} panel pieces in {elapsed}s (failures={len(failures)})")
    return 1 if failures else 0


if __name__ == "__main__" or any(pathlib.Path(a).stem == __name__ for a in sys.argv):
    rc = main()
    if rc != 0:
        raise SystemExit(rc)
