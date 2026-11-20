"""Parametric FreeCAD 1.1 Builder for the Smart Home Acrylic (Mica) Open-Cutaway House.

Run headless with FreeCADCmd:
    "C:\\Users\\LENOVO\\AppData\\Local\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe" hardware/freecad/mica/build_mica.py

Outputs:
    - hardware/freecad/mica/smarthome_mica_house.FCStd  (native parametric FreeCAD model, default T=3 mm)
    - hardware/freecad/mica/freecad_recompute_check.log (verification log for T=2, 3, 5 mm recompute)
    - hardware/freecad/mica/panel_geometry_from_freecad.json (exact BRep volumes, bboxes, face/wire metrics)
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import sys
import time

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import FreeCAD
import Part

import mica_design as md


OUT_FCSTD = SCRIPT_DIR / "smarthome_mica_house.FCStd"
OUT_LOG = SCRIPT_DIR / "freecad_recompute_check.log"
OUT_GEOM_JSON = SCRIPT_DIR / "panel_geometry_from_freecad.json"
KICAD_PCB_STEP = REPO_ROOT / "hardware" / "kicad" / "smarthome_hub" / "3d" / "smarthome_hub.step"


def _expr_sum(a: str | float | int, b: str | float | int) -> str:
    sa, sb = md.fmt_expr(a), md.fmt_expr(b)
    if sa == "0":
        return sb
    if sb == "0":
        return sa
    return f"({sa}) + ({sb})"


def _set_expr(obj, prop: str, expr: str | float | int) -> None:
    """Bind a FreeCAD property either to a spreadsheet expression or numeric value."""
    s = md.fmt_expr(expr)
    if "Params." in s:
        obj.setExpression(prop, s)
    else:
        val = float(eval(s, {"__builtins__": {}}, {}))
        # Set nested Placement properties safely
        if "." in prop:
            obj.setExpression(prop, f"{val:.6f}")
        else:
            setattr(obj, prop, val)


def _make_box_feature(
    doc,
    name: str,
    plane: str,
    origin_xyz: tuple[str | float, str | float, str | float],
    rect: md.RectOp,
    is_cut: bool,
):
    box = doc.addObject("Part::Box", name)
    ox, oy, oz = origin_xyz
    pad = "1.0" if is_cut else "0"
    w_len = "Params.T_mm + 2.0" if is_cut else "Params.T_mm"
    w_off = "-1.0" if is_cut else "0"

    if plane == "XY":
        _set_expr(box, "Length", rect.du)
        _set_expr(box, "Width", rect.dv)
        _set_expr(box, "Height", w_len)
        _set_expr(box, "Placement.Base.x", _expr_sum(ox, rect.u0))
        _set_expr(box, "Placement.Base.y", _expr_sum(oy, rect.v0))
        _set_expr(box, "Placement.Base.z", _expr_sum(oz, w_off))
    elif plane == "XZ":
        _set_expr(box, "Length", rect.du)
        _set_expr(box, "Width", w_len)
        _set_expr(box, "Height", rect.dv)
        _set_expr(box, "Placement.Base.x", _expr_sum(ox, rect.u0))
        _set_expr(box, "Placement.Base.y", _expr_sum(oy, w_off))
        _set_expr(box, "Placement.Base.z", _expr_sum(oz, rect.v0))
    elif plane == "YZ":
        _set_expr(box, "Length", w_len)
        _set_expr(box, "Width", rect.du)
        _set_expr(box, "Height", rect.dv)
        _set_expr(box, "Placement.Base.x", _expr_sum(ox, w_off))
        _set_expr(box, "Placement.Base.y", _expr_sum(oy, rect.u0))
        _set_expr(box, "Placement.Base.z", _expr_sum(oz, rect.v0))
    else:
        raise ValueError(f"Unsupported plane: {plane}")
    return box


def _make_cyl_feature(
    doc,
    name: str,
    plane: str,
    origin_xyz: tuple[str | float, str | float, str | float],
    circ: md.CircleOp,
):
    cyl = doc.addObject("Part::Cylinder", name)
    ox, oy, oz = origin_xyz
    _set_expr(cyl, "Radius", f"({md.fmt_expr(circ.dia)}) / 2.0")
    _set_expr(cyl, "Height", "Params.T_mm + 2.0")

    if plane == "XY":
        cyl.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 0)
        _set_expr(cyl, "Placement.Base.x", _expr_sum(ox, circ.u))
        _set_expr(cyl, "Placement.Base.y", _expr_sum(oy, circ.v))
        _set_expr(cyl, "Placement.Base.z", _expr_sum(oz, "-1.0"))
    elif plane == "XZ":
        # Rotate +Z axis onto +Y axis (-90 deg around X)
        cyl.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), -90)
        _set_expr(cyl, "Placement.Base.x", _expr_sum(ox, circ.u))
        _set_expr(cyl, "Placement.Base.y", _expr_sum(oy, "-1.0"))
        _set_expr(cyl, "Placement.Base.z", _expr_sum(oz, circ.v))
    elif plane == "YZ":
        # Rotate +Z axis onto +X axis (+90 deg around Y)
        cyl.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90)
        _set_expr(cyl, "Placement.Base.x", _expr_sum(ox, "-1.0"))
        _set_expr(cyl, "Placement.Base.y", _expr_sum(oy, circ.u))
        _set_expr(cyl, "Placement.Base.z", _expr_sum(oz, circ.v))
    else:
        raise ValueError(f"Unsupported plane: {plane}")
    return cyl


def build_spreadsheet(doc):
    sh = doc.addObject("Spreadsheet::Sheet", "Params")
    sh.set("A1", "Parameter")
    sh.set("B1", "Value")
    sh.set("C1", "Alias")
    sh.set("D1", "Notes")
    for idx, (alias, label, val_str, note) in enumerate(md.PARAM_ROWS, start=2):
        sh.set(f"A{idx}", label)
        sh.set(f"B{idx}", val_str)
        sh.setAlias(f"B{idx}", alias)
        sh.set(f"C{idx}", alias)
        sh.set(f"D{idx}", note)
    return sh


def build_parametric_panels(doc, panels: list[md.PanelSpec]):
    grp = doc.addObject("App::DocumentObjectGroup", "Acrylic_Panels")
    panel_objs = {}

    for pspec in panels:
        pid = pspec.panel_id
        add_objs = []
        for idx, r in enumerate(pspec.add_rects, 1):
            b = _make_box_feature(doc, f"{pid}_Add{idx}_{r.name}", pspec.plane, pspec.origin_xyz, r, is_cut=False)
            add_objs.append(b)

        if len(add_objs) == 1:
            base_obj = add_objs[0]
        else:
            fuse = doc.addObject("Part::MultiFuse", f"{pid}_BodyFuse")
            fuse.Shapes = add_objs
            fuse.Refine = True
            base_obj = fuse

        cut_tools = []
        for idx, r in enumerate(pspec.cut_rects, 1):
            cb = _make_box_feature(doc, f"{pid}_CutR{idx}_{r.name}", pspec.plane, pspec.origin_xyz, r, is_cut=True)
            cut_tools.append(cb)
        for idx, c in enumerate(pspec.cut_circles, 1):
            cc = _make_cyl_feature(doc, f"{pid}_CutC{idx}_{c.name}", pspec.plane, pspec.origin_xyz, c)
            cut_tools.append(cc)

        if cut_tools:
            if len(cut_tools) == 1:
                tool_obj = cut_tools[0]
            else:
                comp = doc.addObject("Part::Compound", f"{pid}_CutTools")
                comp.Links = cut_tools
                tool_obj = comp
            final_obj = doc.addObject("Part::Cut", pid)
            final_obj.Base = base_obj
            final_obj.Tool = tool_obj
            final_obj.Refine = True
        else:
            final_obj = doc.addObject("Part::Refine", pid) if hasattr(Part, "Refine") else base_obj
            if final_obj is base_obj:
                # Wrap in a clean named Part::Feature copy? No, keep parametric link via Part::Compound(1)
                comp = doc.addObject("Part::Compound", pid)
                comp.Links = [base_obj]
                final_obj = comp

        final_obj.Label = f"{pid} - {pspec.name}"
        grp.addObject(final_obj)
        panel_objs[pid] = final_obj

    return grp, panel_objs


def build_hardware_reference(doc):
    """Add accurate 3D reference models of KiCad PCB + all real modules (zero fan/AC/IR)."""
    grp = doc.addObject("App::DocumentObjectGroup", "Hardware_Reference")

    # 4 Brass M3x10 standoffs under KiCad PCB (center 64, 56; H1..H4 at +-35.5, +-28.0)
    for idx, (dx, dy) in enumerate([(-35.5, 28.0), (35.5, 28.0), (-35.5, -28.0), (35.5, -28.0)], 1):
        st = doc.addObject("Part::Cylinder", f"PCB_Standoff_{idx}")
        st.Radius = 2.8
        st.Height = 10.0
        st.Placement.Base = FreeCAD.Vector(64.0 + dx, 56.0 + dy, 0.0)
        grp.addObject(st)

    # Create clean 3D geometric reference solids for every hardware module
    for hw in md.HARDWARE_PARTS:
        cx, cy, cz = hw.center_xyz
        sx, sy, sz = hw.size_xyz
        if hw.part_id in ("HW_SPEAKER", "HW_BUZZER", "HW_LED_LR", "HW_LED_BR", "HW_LED_PWR", "HW_PUMP"):
            obj = doc.addObject("Part::Cylinder", hw.part_id)
            if hw.part_id == "HW_PUMP":
                # Horizontal cylinder 45.0 (L along Y) x 24.0 (Dia) seated on base
                obj.Radius = sx / 2.0
                obj.Height = sy
                obj.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), -90)
                obj.Placement.Base = FreeCAD.Vector(cx, cy - sy / 2.0, sx / 2.0)
            else:
                obj.Radius = sx / 2.0
                obj.Height = sy
                obj.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), -90)
                obj.Placement.Base = FreeCAD.Vector(cx, cy - sy / 2.0, cz)
        else:
            obj = doc.addObject("Part::Box", hw.part_id)
            obj.Length = sx
            obj.Width = sy
            obj.Height = sz
            obj.Placement.Base = FreeCAD.Vector(cx - sx / 2.0, cy - sy / 2.0, cz - sz / 2.0)
        obj.Label = f"{hw.part_id} - {hw.name}"
        grp.addObject(obj)

    # Silicone water tube arch from pump (254, 55, 45) through P10 hole (278, 55, 33) into planter (308, 55, 28)
    pts = [
        FreeCAD.Vector(254.0, 55.0, 44.0),
        FreeCAD.Vector(254.0, 55.0, 52.0),
        FreeCAD.Vector(266.0, 55.0, 44.0),
        FreeCAD.Vector(278.0, 55.0, 33.0),
        FreeCAD.Vector(296.0, 55.0, 30.0),
        FreeCAD.Vector(304.0, 55.0, 22.0),
    ]
    wire = Part.makePolygon(pts)
    # Build smooth BSpline tube along waypoints
    bs = Part.BSplineCurve()
    bs.interpolate(pts)
    edge = bs.toShape()
    circ = Part.makeCircle(3.75, pts[0], FreeCAD.Vector(0, 0, 1))
    pipe = Part.Wire([edge]).makePipeShell([Part.Wire([circ])], True, False)
    tube_obj = doc.addObject("Part::Feature", "HW_WATER_TUBE")
    tube_obj.Shape = pipe
    tube_obj.Label = "HW_WATER_TUBE - Silicone Pump Tube (OD 7.5mm)"
    grp.addObject(tube_obj)

    return grp


def verify_recompute_for_thicknesses(doc, sh, panels: list[md.PanelSpec], panel_objs: dict):
    lines = []
    lines.append(f"FreeCAD Version: {'.'.join(FreeCAD.Version()[:4])}")
    lines.append(f"Document: {OUT_FCSTD.name}")
    lines.append(f"Panel Count: {len(panels)}")
    lines.append("=" * 84)

    all_passed = True
    geom_at_t3 = {}

    for t_val in [2.0, 3.0, 5.0]:
        t0 = time.time()
        sh.set("B2", f"{t_val:.1f}")
        doc.recompute()
        dt = time.time() - t0
        doc_errors = [o.Name for o in doc.Objects if "Error" in o.State or "Invalid" in o.State]
        lines.append(f"\n[RECOMPUTE T = {t_val:.1f} mm | kerf = 0.15 mm | slot_w = {t_val + 0.15:.2f} mm | {dt:.2f}s]")
        lines.append(f"  Document errors: {doc_errors}")
        if doc_errors:
            all_passed = False

        for pspec in panels:
            pid = pspec.panel_id
            obj = panel_objs[pid]
            shp = obj.Shape
            bb = shp.BoundBox
            eval2d = md.evaluate_panel_2d(pspec, T_mm=t_val, kerf=0.15)
            expected_vol = eval2d["net_area_mm2"] * t_val
            actual_vol = shp.Volume
            vol_err_pct = abs(actual_vol - expected_vol) / max(expected_vol, 1e-6) * 100.0

            if pspec.plane == "XY":
                actual_dims = (bb.XLength, bb.YLength, bb.ZLength)
            elif pspec.plane == "XZ":
                actual_dims = (bb.XLength, bb.ZLength, bb.YLength)
            else:
                actual_dims = (bb.YLength, bb.ZLength, bb.XLength)

            exp_dims = (eval2d["width"], eval2d["height"], t_val)
            dim_err = max(abs(a - b) for a, b in zip(actual_dims, exp_dims))
            valid = bool(shp.isValid()) and len(shp.Solids) == 1 and vol_err_pct < 0.05 and dim_err < 0.05
            if not valid:
                all_passed = False
            status = "PASS" if valid else "FAIL"
            lines.append(
                f"  {status} {pid:18s} | dims={actual_dims[0]:6.2f}x{actual_dims[1]:6.2f}x{actual_dims[2]:4.2f} "
                f"(exp {exp_dims[0]:6.2f}x{exp_dims[1]:6.2f}x{exp_dims[2]:4.2f}) | "
                f"vol={actual_vol:9.1f} (err {vol_err_pct:.4f}%) | solids={len(shp.Solids)}"
            )

            if abs(t_val - 3.0) < 1e-6:
                geom_at_t3[pid] = {
                    "plane": pspec.plane,
                    "bbox_min": [round(bb.XMin, 4), round(bb.YMin, 4), round(bb.ZMin, 4)],
                    "bbox_max": [round(bb.XMax, 4), round(bb.YMax, 4), round(bb.ZMax, 4)],
                    "dims_uvt": [round(d, 4) for d in actual_dims],
                    "volume_mm3": round(actual_vol, 3),
                    "expected_vol_mm3": round(expected_vol, 3),
                    "vol_err_pct": round(vol_err_pct, 5),
                    "solids": len(shp.Solids),
                    "valid": bool(shp.isValid()),
                    "faces": len(shp.Faces),
                }

    # Restore default T = 3.0 mm
    sh.set("B2", "3.0")
    doc.recompute()
    lines.append("\n" + "=" * 84)
    lines.append(f"OVERALL PARAMETRIC RECOMPUTE (T=2, 3, 5 mm): {'ALL_PASS' if all_passed else 'FAILED'}")
    lines.append("Restored committed default: T_mm = 3.0 mm")
    return all_passed, "\n".join(lines), geom_at_t3


def main() -> int:
    t_start = time.time()
    panels, joints = md.build_design()
    print(f"[build_mica] Building parametric FreeCAD model with {len(panels)} panels and {len(joints)} tab-slot joints...")

    doc = FreeCAD.newDocument("SmartHomeMicaHouse")
    sh = build_spreadsheet(doc)
    _grp_panels, panel_objs = build_parametric_panels(doc, panels)
    _grp_hw = build_hardware_reference(doc)

    doc.recompute()
    all_passed, log_text, geom_at_t3 = verify_recompute_for_thicknesses(doc, sh, panels, panel_objs)

    OUT_LOG.write_text(log_text + "\n", encoding="utf-8")
    OUT_GEOM_JSON.write_text(json.dumps({
        "freecad_version": ".".join(FreeCAD.Version()[:4]),
        "default_T_mm": 3.0,
        "default_kerf_mm": 0.15,
        "all_recompute_passed": all_passed,
        "panels": geom_at_t3,
    }, indent=2), encoding="utf-8")

    doc.saveAs(str(OUT_FCSTD))
    elapsed = time.time() - t_start
    print(log_text)
    print(f"\n[build_mica] Saved {OUT_FCSTD} ({OUT_FCSTD.stat().st_size:,} bytes) in {elapsed:.2f}s")
    return 0 if all_passed else 1


if __name__ in ("__main__", "build_mica"):
    rc = main()
    if rc != 0:
        raise SystemExit(rc)
