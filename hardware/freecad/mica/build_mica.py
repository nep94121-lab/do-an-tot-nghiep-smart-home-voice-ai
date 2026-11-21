"""Parametric FreeCAD 1.1 Builder for the Smart Home Acrylic (Mica) Open-Cutaway House (MICA2).

Run headless with FreeCADCmd:
    "C:\\Users\\LENOVO\\AppData\\Local\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe" hardware/freecad/mica/build_mica.py

Outputs:
    - hardware/freecad/mica/smarthome_mica_house.FCStd      (native parametric FreeCAD model, T=3.0 mm, tab_clr=0.25 mm)
    - hardware/freecad/mica/freecad_recompute_check.log     (recompute log for T=2,3,5 mm & tab_clr=0.20,0.25,0.30 mm)
    - hardware/freecad/mica/panel_geometry_from_freecad.json (exact BRep volumes, bboxes, face/solid counts)
    - hardware/freecad/mica/joint_collision_check.json      (19-piece 3D BRep pairwise collision, HW-vs-panel, joint-fit & clearance report)
"""

from __future__ import annotations

import json
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
OUT_COLLISION_JSON = SCRIPT_DIR / "joint_collision_check.json"


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
        cyl.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), -90)
        _set_expr(cyl, "Placement.Base.x", _expr_sum(ox, circ.u))
        _set_expr(cyl, "Placement.Base.y", _expr_sum(oy, "-1.0"))
        _set_expr(cyl, "Placement.Base.z", _expr_sum(oz, circ.v))
    elif plane == "YZ":
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


def _build_single_panel_instance(
    doc,
    inst_id: str,
    label: str,
    pspec: md.PanelSpec,
    origin_xyz: tuple[str | float, str | float, str | float],
):
    add_objs = []
    for idx, r in enumerate(pspec.add_rects, 1):
        b = _make_box_feature(doc, f"{inst_id}_Add{idx}_{r.name}", pspec.plane, origin_xyz, r, is_cut=False)
        add_objs.append(b)

    if len(add_objs) == 1:
        base_obj = add_objs[0]
    else:
        fuse = doc.addObject("Part::MultiFuse", f"{inst_id}_BodyFuse")
        fuse.Shapes = add_objs
        fuse.Refine = True
        base_obj = fuse

    cut_tools = []
    for idx, r in enumerate(pspec.cut_rects, 1):
        cb = _make_box_feature(doc, f"{inst_id}_CutR{idx}_{r.name}", pspec.plane, origin_xyz, r, is_cut=True)
        cut_tools.append(cb)
    for idx, c in enumerate(pspec.cut_circles, 1):
        cc = _make_cyl_feature(doc, f"{inst_id}_CutC{idx}_{c.name}", pspec.plane, origin_xyz, c)
        cut_tools.append(cc)

    if cut_tools:
        if len(cut_tools) == 1:
            tool_obj = cut_tools[0]
        else:
            comp = doc.addObject("Part::Compound", f"{inst_id}_CutTools")
            comp.Links = cut_tools
            tool_obj = comp
        final_obj = doc.addObject("Part::Cut", inst_id)
        final_obj.Base = base_obj
        final_obj.Tool = tool_obj
        final_obj.Refine = True
    else:
        comp = doc.addObject("Part::Compound", inst_id)
        comp.Links = [base_obj]
        final_obj = comp

    final_obj.Label = label
    return final_obj


def build_parametric_panels(doc, panels: list[md.PanelSpec]):
    """Build all 18 unique panels (19 physical instances, instantiating P17_BASE_JOINER_L & R)."""
    grp = doc.addObject("App::DocumentObjectGroup", "Acrylic_Panels")
    panel_objs: dict[str, object] = {}
    instance_objs: dict[str, tuple[md.PanelSpec, object]] = {}

    for pspec in panels:
        pid = pspec.panel_id
        if pspec.extra_origins_xyz:
            all_origins = [pspec.origin_xyz] + list(pspec.extra_origins_xyz)
            suffixes = ["L", "R"] if len(all_origins) == 2 else [str(i + 1) for i in range(len(all_origins))]
            for idx, (orig, suf) in enumerate(zip(all_origins, suffixes)):
                inst_id = f"{pid}_{suf}"
                obj = _build_single_panel_instance(doc, inst_id, f"{inst_id} - {pspec.name}", pspec, orig)
                grp.addObject(obj)
                instance_objs[inst_id] = (pspec, obj)
                if idx == 0:
                    panel_objs[pid] = obj
        else:
            obj = _build_single_panel_instance(doc, pid, f"{pid} - {pspec.name}", pspec, pspec.origin_xyz)
            grp.addObject(obj)
            panel_objs[pid] = obj
            instance_objs[pid] = (pspec, obj)

    return grp, panel_objs, instance_objs


def build_hardware_reference(doc):
    """Add accurate 3D reference models of redesigned 100x80 Hub PCB + all 14 off-board modules + Power LED."""
    grp = doc.addObject("App::DocumentObjectGroup", "Hardware_Reference")

    # 4 Brass M3x6 standoffs under P16_PCB_PLATE (Z = 0..6, 116x96 pitch centered at 82, 99)
    for idx, (dx, dy) in enumerate([(-58.0, -48.0), (58.0, -48.0), (-58.0, 48.0), (58.0, 48.0)], 1):
        st = doc.addObject("Part::Cylinder", f"Plate_Standoff_{idx}")
        st.Radius = 2.8
        st.Height = 6.0
        st.Placement.Base = FreeCAD.Vector(82.0 + dx, 99.0 + dy, 0.0)
        grp.addObject(st)

    # 4 Brass M3x10 standoffs between P16_PCB_PLATE (Z=6+T) and HW_PCB (90x70 pattern centered at 82, 99)
    for idx, (dx, dy) in enumerate([(-45.0, -35.0), (45.0, -35.0), (-45.0, 35.0), (45.0, 35.0)], 1):
        st = doc.addObject("Part::Cylinder", f"PCB_Standoff_{idx}")
        st.Radius = 2.8
        st.Height = 10.0
        _set_expr(st, "Placement.Base.x", 82.0 + dx)
        _set_expr(st, "Placement.Base.y", 99.0 + dy)
        _set_expr(st, "Placement.Base.z", "6.0 + Params.T_mm")
        grp.addObject(st)

    cyl_ids = {"HW_SPEAKER", "HW_BUZZER", "HW_LED_LR", "HW_LED_BR", "HW_LED_PWR", "HW_DC_JACK", "HW_PUMP"}
    for hw in md.HARDWARE_PARTS:
        cx, cy, cz = hw.center_xyz
        sx, sy, sz = hw.size_xyz
        if hw.part_id in cyl_ids:
            obj = doc.addObject("Part::Cylinder", hw.part_id)
            obj.Radius = sx / 2.0
            obj.Height = sy
            obj.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), -90)
            if hw.part_id == "HW_PUMP":
                obj.Placement.Base = FreeCAD.Vector(cx, cy - sy / 2.0, sx / 2.0)
            else:
                obj.Placement.Base = FreeCAD.Vector(cx, cy - sy / 2.0, cz)
        else:
            obj = doc.addObject("Part::Box", hw.part_id)
            obj.Length = sx
            obj.Width = sy
            obj.Height = sz
            obj.Placement.Base = FreeCAD.Vector(cx - sx / 2.0, cy - sy / 2.0, cz - sz / 2.0)
        obj.Label = f"{hw.part_id} - {hw.name}"
        grp.addObject(obj)

    # Silicone water tube arch from pump (292, 89, 33) through P10 hole (318, 89, 38) into planter (344, 89, 26)
    pts = [
        FreeCAD.Vector(292.0, 89.0, 33.0),
        FreeCAD.Vector(292.0, 89.0, 48.0),
        FreeCAD.Vector(305.0, 89.0, 44.0),
        FreeCAD.Vector(318.0, 89.0, 38.0),
        FreeCAD.Vector(332.0, 89.0, 34.0),
        FreeCAD.Vector(342.0, 89.0, 26.0),
    ]
    bs = Part.BSplineCurve()
    bs.interpolate(pts)
    edge = bs.toShape()
    circ = Part.makeCircle(4.0, pts[0], FreeCAD.Vector(0, 0, 1))
    pipe = Part.Wire([edge]).makePipeShell([Part.Wire([circ])], True, False)
    tube_obj = doc.addObject("Part::Feature", "HW_WATER_TUBE")
    tube_obj.Shape = pipe
    tube_obj.Label = "HW_WATER_TUBE - Silicone Pump Tube (OD 8.0mm)"
    grp.addObject(tube_obj)

    return grp


def _run_collision_and_joint_checks(
    instance_objs: dict[str, tuple[md.PanelSpec, object]],
    panel_objs: dict[str, object],
    joints: list[md.JointPair],
    t_val: float,
    clr_val: float,
) -> dict:
    """Run full 3D OpenCASCADE BRep pairwise collision check & joint engagement verification."""
    params = md.default_param_values(T_mm=t_val, tab_clr=clr_val)
    inst_names = sorted(instance_objs.keys())
    shapes = {name: instance_objs[name][1].Shape for name in inst_names}

    collisions = []
    max_inter_vol = 0.0
    checked_pairs = 0
    pair_inter_cache: dict[frozenset[str], float] = {}

    for i in range(len(inst_names)):
        na = inst_names[i]
        sa = shapes[na]
        bba = sa.BoundBox
        for j in range(i + 1, len(inst_names)):
            nb = inst_names[j]
            sb = shapes[nb]
            checked_pairs += 1
            bbb = sb.BoundBox
            # Quick bbox reject with 1e-4 tolerance
            if (
                bba.XMax < bbb.XMin - 1e-4 or bbb.XMax < bba.XMin - 1e-4
                or bba.YMax < bbb.YMin - 1e-4 or bbb.YMax < bba.YMin - 1e-4
                or bba.ZMax < bbb.ZMin - 1e-4 or bbb.ZMax < bba.ZMin - 1e-4
            ):
                pair_inter_cache[frozenset((na, nb))] = 0.0
                continue
            inter = sa.common(sb)
            vol = float(inter.Volume)
            pair_inter_cache[frozenset((na, nb))] = vol
            if vol > max_inter_vol:
                max_inter_vol = vol
            if vol >= 0.001:
                collisions.append({
                    "panel_a": na,
                    "panel_b": nb,
                    "intersection_vol_mm3": round(vol, 6),
                })

    joint_results = []
    joint_failures = []
    for jp in joints:
        tab_shp = panel_objs[jp.tab_panel].Shape
        cx = md.eval_expr(jp.world_center_expr[0], params)
        cy = md.eval_expr(jp.world_center_expr[1], params)
        cz = md.eval_expr(jp.world_center_expr[2], params)
        tab_len = md.eval_expr(jp.tab_len_expr, params)
        slot_len = md.eval_expr(jp.slot_len_expr, params)
        tab_dep = md.eval_expr(jp.tab_depth_expr, params)
        slot_w = md.eval_expr(jp.slot_width_expr, params)

        len_gap = round(slot_len - tab_len, 4)
        if jp.joint_kind == "notch":
            # Edge notch has open outer edge; inner clearance is tab_clr / 2, total equivalent is tab_clr
            width_gap = round((slot_w - t_val) * 2.0, 4)
        elif jp.joint_kind == "seam_notch":
            width_gap = round(slot_w - tab_dep, 4)
        else:
            width_gap = round(slot_w - t_val, 4)

        # Build the 3D envelope box of the slot/notch opening and verify the tab enters it
        if jp.joint_kind == "seam_notch":
            bx, by, bz = slot_len, slot_w, t_val
        elif jp.axis == "X":
            bx = slot_len
            by = slot_w if jp.slot_panel.startswith("P01") else t_val
            bz = t_val if jp.slot_panel.startswith("P01") else slot_w
        elif jp.axis == "Y":
            bx = slot_w
            by = slot_len
            bz = t_val
        else:  # axis == "Z"
            bx = slot_w
            by = t_val
            bz = slot_len

        env_box = Part.makeBox(bx, by, bz, FreeCAD.Vector(cx - bx / 2.0, cy - by / 2.0, cz - bz / 2.0))
        engaged_vol = float(tab_shp.common(env_box).Volume)
        inter_vol = pair_inter_cache.get(frozenset((jp.tab_panel, jp.slot_panel)), 0.0)

        gap_ok = (0.20 - 1e-4 <= len_gap <= 0.30 + 1e-4) and (0.20 - 1e-4 <= width_gap <= 0.30 + 1e-4)
        engaged_ok = engaged_vol > 1.0
        zero_inter_ok = inter_vol < 0.001
        ok = gap_ok and engaged_ok and zero_inter_ok

        rec = {
            "joint_id": jp.joint_id,
            "tab_panel": jp.tab_panel,
            "slot_panel": jp.slot_panel,
            "kind": jp.joint_kind,
            "axis": jp.axis,
            "tab_len_mm": round(tab_len, 3),
            "slot_len_mm": round(slot_len, 3),
            "len_gap_mm": len_gap,
            "width_gap_mm": width_gap,
            "engaged_vol_mm3": round(engaged_vol, 3),
            "interference_vol_mm3": round(inter_vol, 6),
            "passed": ok,
        }
        joint_results.append(rec)
        if not ok:
            joint_failures.append(rec)

    return {
        "T_mm": t_val,
        "tab_clr_mm": clr_val,
        "instance_count": len(inst_names),
        "checked_panel_pairs": checked_pairs,
        "max_intersection_vol_mm3": round(max_inter_vol, 6),
        "collision_count": len(collisions),
        "collisions": collisions,
        "joint_count": len(joint_results),
        "joint_failure_count": len(joint_failures),
        "joint_failures": joint_failures,
        "joints": joint_results,
        "passed": len(collisions) == 0 and len(joint_failures) == 0,
    }


def _check_hardware_vs_panel_collisions(
    doc,
    instance_objs: dict[str, tuple[md.PanelSpec, object]],
) -> dict:
    """Verify 0.000 mm^3 3D BRep collision between every hardware solid and all non-host acrylic panels."""
    # Intentional flange/mounting-ear seating against the module's own host panel:
    allowed_host_seating = {
        ("HW_SG90", "P07_SERVO_SHELF"),
        ("HW_DC_JACK", "P15_TECH_FASCIA"),
        ("HW_LED_PWR", "P15_TECH_FASCIA"),
        ("HW_LED_LR", "P02_WALL_BACK"),
        ("HW_LED_BR", "P02_WALL_BACK"),
    }
    hw_grp = doc.getObject("Hardware_Reference")
    hw_objs = [
        o for o in (hw_grp.Group if hw_grp else [])
        if hasattr(o, "Shape") and not o.Shape.isNull() and o.Name.startswith("HW_")
    ]
    checked_pairs = 0
    collisions = []
    max_inter_vol = 0.0

    for hobj in hw_objs:
        hshp = hobj.Shape
        hbb = hshp.BoundBox
        for inst_id, (pspec, pobj) in sorted(instance_objs.items()):
            if (hobj.Name, pspec.panel_id) in allowed_host_seating:
                continue
            checked_pairs += 1
            pshp = pobj.Shape
            pbb = pshp.BoundBox
            if (
                hbb.XMax < pbb.XMin - 1e-4 or pbb.XMax < hbb.XMin - 1e-4
                or hbb.YMax < pbb.YMin - 1e-4 or pbb.YMax < hbb.YMin - 1e-4
                or hbb.ZMax < pbb.ZMin - 1e-4 or pbb.ZMax < hbb.ZMin - 1e-4
            ):
                continue
            inter = hshp.common(pshp)
            vol = float(inter.Volume)
            if vol > max_inter_vol:
                max_inter_vol = vol
            if vol >= 0.01:
                collisions.append({
                    "hardware": hobj.Name,
                    "panel": inst_id,
                    "intersection_vol_mm3": round(vol, 4),
                })

    return {
        "hardware_solids": len(hw_objs),
        "checked_pairs": checked_pairs,
        "allowed_host_seating": [list(p) for p in sorted(allowed_host_seating)],
        "max_intersection_vol_mm3": round(max_inter_vol, 6),
        "collision_count": len(collisions),
        "collisions": collisions,
        "passed": len(collisions) == 0,
    }


def _check_pcb_plate_fit(panels: list[md.PanelSpec], T_mm: float = 3.0, tab_clr: float = 0.25) -> dict:
    p16 = next(p for p in panels if p.panel_id == "P16_PCB_PLATE")
    ev = md.evaluate_panel_2d(p16, T_mm=T_mm, tab_clr=tab_clr)
    pcb_holes = [c for c in ev["circles"] if c["name"].startswith("PCB_H")]
    xs = sorted(set(c["cx"] for c in pcb_holes))
    ys = sorted(set(c["cy"] for c in pcb_holes))
    dias = sorted(set(c["dia"] for c in pcb_holes))
    pattern_x = round(xs[-1] - xs[0], 4) if len(xs) == 2 else 0.0
    pattern_y = round(ys[-1] - ys[0], 4) if len(ys) == 2 else 0.0
    pcb_xmin, pcb_xmax = xs[0] - 5.0, xs[-1] + 5.0
    pcb_ymin, pcb_ymax = ys[0] - 5.0, ys[-1] + 5.0
    margins = {
        "left": round(pcb_xmin, 4),
        "right": round(ev["width"] - pcb_xmax, 4),
        "bottom": round(pcb_ymin, 4),
        "top": round(ev["height"] - pcb_ymax, 4),
    }
    min_margin = min(margins.values())
    passed = (
        abs(pattern_x - 90.0) < 1e-4
        and abs(pattern_y - 70.0) < 1e-4
        and dias == [3.4]
        and min_margin >= 10.0 - 1e-4
    )
    return {
        "panel_id": "P16_PCB_PLATE",
        "plate_size_mm": [ev["width"], ev["height"]],
        "pcb_size_mm": [100.0, 80.0],
        "hole_pattern_mm": [pattern_x, pattern_y],
        "hole_dias_mm": dias,
        "free_margins_mm": margins,
        "min_margin_mm": min_margin,
        "passed": passed,
    }


def verify_recompute_and_collisions(
    doc,
    sh,
    panels: list[md.PanelSpec],
    joints: list[md.JointPair],
    panel_objs: dict[str, object],
    instance_objs: dict[str, tuple[md.PanelSpec, object]],
):
    lines = []
    lines.append(f"FreeCAD Version: {'.'.join(FreeCAD.Version()[:4])}")
    lines.append(f"Document: {OUT_FCSTD.name}")
    lines.append(f"Unique Panels: {len(panels)} | Physical Instances: {len(instance_objs)} | Joints: {len(joints)}")
    lines.append("=" * 92)

    all_passed = True
    geom_at_default = {}
    collision_reports: dict[str, dict] = {}

    # 1. Test T = 2.0, 3.0, 5.0 mm at default tab_clr = 0.25 mm (with full BRep collision & joint checks)
    sh.set("B3", "0.25")
    for t_val in [2.0, 3.0, 5.0]:
        t0 = time.time()
        sh.set("B2", f"{t_val:.1f}")
        doc.recompute()
        dt = time.time() - t0
        doc_errors = [o.Name for o in doc.Objects if "Error" in o.State or "Invalid" in o.State]
        lines.append(f"\n[RECOMPUTE T = {t_val:.1f} mm | tab_clr = 0.25 mm | slot_w = {t_val + 0.25:.2f} mm | {dt:.2f}s]")
        lines.append(f"  Document errors: {doc_errors}")
        if doc_errors:
            all_passed = False

        for inst_id, (pspec, obj) in sorted(instance_objs.items()):
            shp = obj.Shape
            bb = shp.BoundBox
            eval2d = md.evaluate_panel_2d(pspec, T_mm=t_val, tab_clr=0.25)
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
                f"  {status} {inst_id:18s} | dims={actual_dims[0]:6.2f}x{actual_dims[1]:6.2f}x{actual_dims[2]:4.2f} "
                f"(exp {exp_dims[0]:6.2f}x{exp_dims[1]:6.2f}x{exp_dims[2]:4.2f}) | "
                f"vol={actual_vol:10.1f} (err {vol_err_pct:.4f}%) | solids={len(shp.Solids)}"
            )

            if abs(t_val - 3.0) < 1e-6:
                rec = {
                    "panel_id": pspec.panel_id,
                    "qty": pspec.qty,
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
                geom_at_default[inst_id] = rec
                if pspec.panel_id not in geom_at_default:
                    geom_at_default[pspec.panel_id] = rec

        creport = _run_collision_and_joint_checks(instance_objs, panel_objs, joints, t_val, 0.25)
        collision_reports[f"T_{int(t_val)}mm_clr_0.25mm"] = creport
        if not creport["passed"]:
            all_passed = False
        msg = (
            f"  [3D BREP COLLISION & JOINTS T={t_val:.1f}mm] "
            f"pairs={creport['checked_panel_pairs']}, collisions={creport['collision_count']}, "
            f"max_inter_vol={creport['max_intersection_vol_mm3']:.6f} mm3 | "
            f"joints={creport['joint_count']}, failures={creport['joint_failure_count']} -> "
            f"{'PASS' if creport['passed'] else 'FAIL'}"
        )
        lines.append(msg)
        print(msg, flush=True)

    # 2. Test tab_clr sweep = 0.20, 0.25, 0.30 mm at T = 3.0 mm
    sh.set("B2", "3.0")
    for clr_val in [0.20, 0.25, 0.30]:
        if abs(clr_val - 0.25) < 1e-6 and "T_3mm_clr_0.25mm" in collision_reports:
            creport = collision_reports["T_3mm_clr_0.25mm"]
            msg = (
                f"\n[CLEARANCE SWEEP T=3.0 mm | tab_clr={clr_val:.2f} mm | slot_w={3.0 + clr_val:.2f} mm | cached] "
                f"errors=0, collisions={creport['collision_count']}, "
                f"joint_failures={creport['joint_failure_count']} -> {'PASS' if creport['passed'] else 'FAIL'}"
            )
            lines.append(msg)
            print(msg.strip(), flush=True)
            continue
        t0 = time.time()
        sh.set("B3", f"{clr_val:.2f}")
        doc.recompute()
        dt = time.time() - t0
        doc_errors = [o.Name for o in doc.Objects if "Error" in o.State or "Invalid" in o.State]
        clr_ok = len(doc_errors) == 0
        for inst_id, (pspec, obj) in sorted(instance_objs.items()):
            shp = obj.Shape
            eval2d = md.evaluate_panel_2d(pspec, T_mm=3.0, tab_clr=clr_val)
            expected_vol = eval2d["net_area_mm2"] * 3.0
            vol_err_pct = abs(shp.Volume - expected_vol) / max(expected_vol, 1e-6) * 100.0
            if not (bool(shp.isValid()) and len(shp.Solids) == 1 and vol_err_pct < 0.05):
                clr_ok = False
        creport = _run_collision_and_joint_checks(instance_objs, panel_objs, joints, 3.0, clr_val)
        if not creport["passed"]:
            clr_ok = False
        if not clr_ok:
            all_passed = False
        collision_reports[f"T_3mm_clr_{clr_val:.2f}mm"] = creport
        msg = (
            f"\n[CLEARANCE SWEEP T=3.0 mm | tab_clr={clr_val:.2f} mm | slot_w={3.0 + clr_val:.2f} mm | {dt:.2f}s] "
            f"errors={len(doc_errors)}, collisions={creport['collision_count']}, "
            f"joint_failures={creport['joint_failure_count']} -> {'PASS' if clr_ok else 'FAIL'}"
        )
        lines.append(msg)
        print(msg.strip(), flush=True)

    # Restore default T = 3.0 mm, tab_clr = 0.25 mm
    sh.set("B2", "3.0")
    sh.set("B3", "0.25")
    doc.recompute()

    # 3. Hardware wiring clearance, Hardware-vs-Panel 3D BRep collision, & PCB plate margin checks
    hw_check = md.check_hardware_clearances(min_gap_mm=15.0)
    hw_panel_check = _check_hardware_vs_panel_collisions(doc, instance_objs)
    pcb_check = _check_pcb_plate_fit(panels, T_mm=3.0, tab_clr=0.25)
    if not hw_check["passed"] or not hw_panel_check["passed"] or not pcb_check["passed"]:
        all_passed = False

    lines.append("\n" + "=" * 92)
    lines.append(
        f"HARDWARE WIRING GAP CHECK: {hw_check['checked_pairs']} non-mated pairs | "
        f"min_gap={hw_check['measured_min_gap_mm']:.2f} mm ({hw_check['closest_pair'][0]} <-> {hw_check['closest_pair'][1]}) "
        f">= {hw_check['required_min_gap_mm']:.1f} mm -> {'PASS' if hw_check['passed'] else 'FAIL'}"
    )
    lines.append(
        f"HARDWARE VS PANEL 3D BREP CHECK (T=3.0mm): {hw_panel_check['checked_pairs']} pairs | "
        f"collisions={hw_panel_check['collision_count']}, max_inter_vol={hw_panel_check['max_intersection_vol_mm3']:.6f} mm3 "
        f"-> {'PASS' if hw_panel_check['passed'] else 'FAIL'}"
    )
    lines.append(
        f"PCB MOUNTING PLATE CHECK: plate={pcb_check['plate_size_mm']} mm, "
        f"pattern={pcb_check['hole_pattern_mm']} mm (Dia {pcb_check['hole_dias_mm']}), "
        f"min_margin={pcb_check['min_margin_mm']:.1f} mm (>= 10.0 mm) -> {'PASS' if pcb_check['passed'] else 'FAIL'}"
    )
    lines.append(f"OVERALL PARAMETRIC RECOMPUTE & 3D BREP VERIFICATION: {'ALL_PASS' if all_passed else 'FAILED'}")
    lines.append("Restored committed defaults: T_mm = 3.0 mm, tab_clr = 0.25 mm")

    full_collision_json = {
        "freecad_version": ".".join(FreeCAD.Version()[:4]),
        "default_T_mm": 3.0,
        "default_tab_clr_mm": 0.25,
        "all_passed": all_passed,
        "hardware_wiring_clearance": hw_check,
        "hardware_vs_panel_collisions": hw_panel_check,
        "pcb_plate_fit": pcb_check,
        "runs": collision_reports,
    }
    return all_passed, "\n".join(lines), geom_at_default, full_collision_json


def main() -> int:
    t_start = time.time()
    panels, joints = md.build_design()
    total_qty = sum(p.qty for p in panels)
    print(f"[build_mica] Building parametric FreeCAD model: {len(panels)} unique panels ({total_qty} pieces), {len(joints)} tab-slot joints...")

    doc = FreeCAD.newDocument("SmartHomeMicaHouse")
    sh = build_spreadsheet(doc)
    _grp_panels, panel_objs, instance_objs = build_parametric_panels(doc, panels)
    _grp_hw = build_hardware_reference(doc)

    doc.recompute()
    all_passed, log_text, geom_at_default, full_collision_json = verify_recompute_and_collisions(
        doc, sh, panels, joints, panel_objs, instance_objs
    )

    OUT_LOG.write_text(log_text + "\n", encoding="utf-8")
    OUT_GEOM_JSON.write_text(json.dumps({
        "freecad_version": ".".join(FreeCAD.Version()[:4]),
        "default_T_mm": 3.0,
        "default_tab_clr_mm": 0.25,
        "default_kerf_mm": 0.25,
        "unique_panel_count": len(panels),
        "physical_piece_count": total_qty,
        "joint_count": len(joints),
        "all_recompute_passed": all_passed,
        "panels": geom_at_default,
    }, indent=2), encoding="utf-8")
    OUT_COLLISION_JSON.write_text(json.dumps(full_collision_json, indent=2), encoding="utf-8")

    doc.saveAs(str(OUT_FCSTD))
    elapsed = time.time() - t_start
    print(log_text)
    print(f"\n[build_mica] Saved {OUT_FCSTD} ({OUT_FCSTD.stat().st_size:,} bytes) in {elapsed:.2f}s")
    return 0 if all_passed else 1


if __name__ in ("__main__", "build_mica"):
    rc = main()
    if rc != 0:
        raise SystemExit(rc)
