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
import mica_design as md
import print_domain as pd_mod


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
