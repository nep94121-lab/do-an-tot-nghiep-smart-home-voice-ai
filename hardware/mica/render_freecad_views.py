"""Headless FreeCAD 1.1 Coin3D Offscreen 3D Renderer for MICA2 Acrylic House Screenshots.

Renders 3 crisp 1920x1200 3D views directly from `smarthome_mica_house.FCStd`
without opening any GUI window (uses FreeCADGui.setupWithoutGUI + pivy.coin.SoOffscreenRenderer):
  1. `_tmp_assembly.rgb`        — Assembled transparent acrylic house (19 pieces) + 17 hardware solids
  2. `_tmp_exploded.rgb`        — Exploded 3D view (all 19 pieces + red dashed assembly axis lines)
  3. `_tmp_internal_layout.rgb` — High-angle interior layout (translucent walls, vivid opaque 17 hardware parts + P16 PCB plate)
  4. `_tmp_render_meta.json`    — Exact 3D->2D camera projections for crisp non-overlapping labels

Run headless with FreeCADCmd:
    "C:\\Users\\LENOVO\\AppData\\Local\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe" hardware/mica/render_freecad_views.py
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import FreeCAD
import FreeCADGui
from pivy import coin

import mica_design as md

FCSTD_PATH = SCRIPT_DIR / "smarthome_mica_house.FCStd"
OUT_ASM_RGB = SCRIPT_DIR / "_tmp_assembly.rgb"
OUT_EXP_RGB = SCRIPT_DIR / "_tmp_exploded.rgb"
OUT_INT_RGB = SCRIPT_DIR / "_tmp_internal_layout.rgb"
OUT_META = SCRIPT_DIR / "_tmp_render_meta.json"

IMG_W = 1920
IMG_H = 1200


def _shape_to_coin_node(
    shape,
    rgb: tuple[float, float, float],
    transparency: float = 0.0,
    edge_rgb: tuple[float, float, float] | None = (0.06, 0.22, 0.36),
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
    edge_width: float = 1.6,
):
    """Convert a FreeCAD Part.Shape into a Coin3D SoSeparator with shaded faces + crisp edges."""
    sep = coin.SoSeparator()

    if any(abs(v) > 1e-6 for v in offset):
        tr = coin.SoTranslation()
        tr.translation.setValue(*offset)
        sep.addChild(tr)

    verts, tris = shape.tessellate(0.25)

    face_sep = coin.SoSeparator()
    mat = coin.SoMaterial()
    mat.diffuseColor.setValue(*rgb)
    mat.ambientColor.setValue(rgb[0] * 0.48, rgb[1] * 0.48, rgb[2] * 0.48)
    mat.specularColor.setValue(0.32, 0.35, 0.40)
    mat.shininess.setValue(0.65 if transparency > 0 else 0.35)
    mat.transparency.setValue(transparency)
    face_sep.addChild(mat)

    coords = coin.SoCoordinate3()
    coords.point.setValues(0, len(verts), [(v.x, v.y, v.z) for v in verts])
    face_sep.addChild(coords)

    idx_list = []
    for t0, t1, t2 in tris:
        idx_list.extend([t0, t1, t2, -1])
    fset = coin.SoIndexedFaceSet()
    fset.coordIndex.setValues(0, len(idx_list), idx_list)
    face_sep.addChild(fset)
    sep.addChild(face_sep)

    if edge_rgb is not None:
        edge_sep = coin.SoSeparator()
        emat = coin.SoMaterial()
        emat.diffuseColor.setValue(*edge_rgb)
        emat.emissiveColor.setValue(edge_rgb[0] * 0.4, edge_rgb[1] * 0.4, edge_rgb[2] * 0.4)
        edge_sep.addChild(emat)

        ds = coin.SoDrawStyle()
        ds.lineWidth.setValue(edge_width)
        edge_sep.addChild(ds)

        e_pts = []
        e_idx = []
        pt_cursor = 0
        for edge in shape.Edges:
            pts = edge.discretize(Deflection=0.2)
            if len(pts) < 2:
                continue
            for p in pts:
                e_pts.append((p.x, p.y, p.z))
                e_idx.append(pt_cursor)
                pt_cursor += 1
            e_idx.append(-1)

        if e_pts:
            ecoord = coin.SoCoordinate3()
            ecoord.point.setValues(0, len(e_pts), e_pts)
            edge_sep.addChild(ecoord)
            lset = coin.SoIndexedLineSet()
            lset.coordIndex.setValues(0, len(e_idx), e_idx)
            edge_sep.addChild(lset)
            sep.addChild(edge_sep)

    return sep


def _add_guide_line(parent, p1: tuple[float, float, float], p2: tuple[float, float, float]):
    sep = coin.SoSeparator()
    mat = coin.SoMaterial()
    mat.diffuseColor.setValue(0.85, 0.14, 0.14)
    mat.emissiveColor.setValue(0.55, 0.08, 0.08)
    sep.addChild(mat)
    ds = coin.SoDrawStyle()
    ds.lineWidth.setValue(1.8)
    ds.linePattern.setValue(0xF0F0)
    sep.addChild(ds)
    coords = coin.SoCoordinate3()
    coords.point.setValues(0, 2, [p1, p2])
    sep.addChild(coords)
    ls = coin.SoLineSet()
    ls.numVertices.setValue(2)
    sep.addChild(ls)
    parent.addChild(sep)


def _setup_lighting_and_camera(root, eye, target, up=(0.0, 0.0, 1.0), fov_deg=35.0):
    lm = coin.SoLightModel()
    lm.model.setValue(coin.SoLightModel.PHONG)
    root.addChild(lm)

    hints = coin.SoShapeHints()
    hints.vertexOrdering.setValue(coin.SoShapeHints.COUNTERCLOCKWISE)
    hints.shapeType.setValue(coin.SoShapeHints.UNKNOWN_SHAPE_TYPE)
    root.addChild(hints)

    cam = coin.SoPerspectiveCamera()
    cam.heightAngle.setValue(math.radians(fov_deg))
    cam.position.setValue(*eye)
    cam.pointAt(coin.SbVec3f(*target), coin.SbVec3f(*up))
    cam.nearDistance.setValue(5.0)
    cam.farDistance.setValue(6000.0)
    root.addChild(cam)

    for direction, intensity, col in [
        ((-0.45, 0.65, -0.78), 0.92, (1.0, 1.0, 1.0)),
        ((0.70, 0.30, -0.42), 0.58, (0.92, 0.96, 1.0)),
        ((0.15, -0.80, -0.35), 0.42, (1.0, 0.98, 0.95)),
    ]:
        dl = coin.SoDirectionalLight()
        dl.direction.setValue(*direction)
        dl.intensity.setValue(intensity)
        dl.color.setValue(*col)
        root.addChild(dl)

    return cam


def _project_3d_to_2d(cam, vp, pt: tuple[float, float, float]) -> tuple[float, float]:
    vv = cam.getViewVolume(vp.getViewportAspectRatio())
    proj = vv.projectToScreen(coin.SbVec3f(*pt))
    px = float(proj[0]) * IMG_W
    py = (1.0 - float(proj[1])) * IMG_H
    return (round(px, 1), round(py, 1))


def _iter_panel_instances(doc, panels: list[md.PanelSpec]):
    """Yield (inst_name, pspec, obj, explode_override) for all 19 physical pieces."""
    for pspec in panels:
        if pspec.extra_origins_xyz:
            for suf, dx in [("L", -24.0), ("R", 24.0)]:
                inst_name = f"{pspec.panel_id}_{suf}"
                obj = doc.getObject(inst_name)
                if obj is not None:
                    ex = (pspec.explode_xyz[0] + dx, pspec.explode_xyz[1], pspec.explode_xyz[2])
                    yield inst_name, pspec, obj, ex
        else:
            obj = doc.getObject(pspec.panel_id)
            if obj is not None:
                yield pspec.panel_id, pspec, obj, pspec.explode_xyz


def _add_hardware_nodes(root, doc, hw_spec_map, cam, vp, edge_w: float = 1.05):
    hw_grp = doc.getObject("Hardware_Reference")
    labels_2d = []
    if not hw_grp:
        return labels_2d
    for obj in hw_grp.Group:
        if not hasattr(obj, "Shape") or obj.Shape.isNull():
            continue
        if obj.Name in hw_spec_map:
            rgb = hw_spec_map[obj.Name].color_rgb
            lbl = hw_spec_map[obj.Name].part_id.replace("HW_", "")
        elif obj.Name.startswith("PCB_Standoff") or obj.Name.startswith("Plate_Standoff"):
            rgb = (0.86, 0.70, 0.24)
            lbl = None
        elif obj.Name == "HW_WATER_TUBE":
            rgb = (0.28, 0.74, 0.96)
            lbl = None
        else:
            rgb = (0.5, 0.5, 0.5)
            lbl = None
        root.addChild(_shape_to_coin_node(
            obj.Shape, rgb, transparency=0.0, edge_rgb=(0.10, 0.12, 0.16), edge_width=edge_w
        ))
        if lbl:
            bb = obj.Shape.BoundBox
            if obj.Name == "HW_PCB":
                c3 = (118.0, 125.0, bb.ZMax)
                c3_mid = (118.0, 125.0, bb.ZMax)
            else:
                c3 = (bb.Center.x, bb.Center.y, bb.ZMax)
                c3_mid = (bb.Center.x, bb.Center.y, bb.Center.z)
            labels_2d.append({
                "id": lbl,
                "xy": _project_3d_to_2d(cam, vp, c3),
                "mid_xy": _project_3d_to_2d(cam, vp, c3_mid),
            })
    return labels_2d


def render_views() -> int:
    FreeCADGui.setupWithoutGUI()
    doc = FreeCAD.openDocument(str(FCSTD_PATH))
    panels, _joints = md.build_design()
    hw_spec_map = {h.part_id: h for h in md.HARDWARE_PARTS}

    vp = coin.SbViewportRegion(IMG_W, IMG_H)
    ren = coin.SoOffscreenRenderer(vp)
    ren.setBackgroundColor(coin.SbColor(0.965, 0.980, 0.995))

    # ------------------------------------------------------------------
    # VIEW 1: ASSEMBLED TRANSPARENT ACRYLIC HOUSE (19 PIECES) + HARDWARE
    # ------------------------------------------------------------------
    root_asm = coin.SoSeparator()
    cam_asm = _setup_lighting_and_camera(
        root_asm,
        eye=(585.0, -420.0, 375.0),
        target=(196.0, 178.0, 48.0),
        fov_deg=35.0,
    )
    hw_labels_asm = _add_hardware_nodes(root_asm, doc, hw_spec_map, cam_asm, vp, edge_w=1.0)

    for inst_name, pspec, obj, _ex in _iter_panel_instances(doc, panels):
        transp = 0.42 if pspec.panel_id == "P16_PCB_PLATE" else 0.56
        ec = (0.04, 0.36, 0.22) if pspec.panel_id == "P16_PCB_PLATE" else (0.05, 0.24, 0.42)
        root_asm.addChild(_shape_to_coin_node(
            obj.Shape, rgb=pspec.color_rgb, transparency=transp, edge_rgb=ec, edge_width=1.65
        ))

    ok1 = ren.render(root_asm)
    w1 = ren.writeToRGB(str(OUT_ASM_RGB))
    print(f"[render] View 1 (Assembly): render={ok1}, writeToRGB={w1}, size={OUT_ASM_RGB.stat().st_size:,}")

    # ------------------------------------------------------------------
    # VIEW 2: EXPLODED VIEW OF ALL 19 PIECES + RED DASHED GUIDE LINES
    # ------------------------------------------------------------------
    root_exp = coin.SoSeparator()
    cam_exp = _setup_lighting_and_camera(
        root_exp,
        eye=(780.0, -565.0, 520.0),
        target=(200.0, 178.0, 42.0),
        fov_deg=37.0,
    )

    exp_labels_2d = []
    exp_palette = [
        (0.56, 0.80, 0.98), (0.62, 0.84, 0.99), (0.66, 0.86, 0.99), (0.68, 0.84, 0.99),
        (0.60, 0.90, 0.86), (0.58, 0.88, 0.96), (0.76, 0.80, 0.99), (0.98, 0.84, 0.56),
        (0.94, 0.82, 0.62), (0.56, 0.90, 0.92), (0.50, 0.86, 0.86), (0.62, 0.92, 0.76),
        (0.64, 0.90, 0.84), (0.60, 0.88, 0.90), (0.74, 0.94, 0.68), (0.66, 0.84, 0.99),
        (0.52, 0.88, 0.76), (0.58, 0.76, 0.92), (0.58, 0.76, 0.92),
    ]
    for idx, (inst_name, pspec, obj, ex_raw) in enumerate(_iter_panel_instances(doc, panels)):
        bb = obj.Shape.BoundBox
        c_asm = (bb.Center.x, bb.Center.y, bb.Center.z)
        ex, ey, ez = (ex_raw[0] * 1.12, ex_raw[1] * 1.12, ex_raw[2] * 1.12)
        c_exp = (c_asm[0] + ex, c_asm[1] + ey, c_asm[2] + ez)

        _add_guide_line(root_exp, c_asm, c_exp)
        root_exp.addChild(_shape_to_coin_node(
            obj.Shape,
            rgb=exp_palette[idx % len(exp_palette)],
            transparency=0.40,
            edge_rgb=(0.05, 0.20, 0.36),
            offset=(ex, ey, ez),
            edge_width=1.65,
        ))
        anchor_3d = (c_exp[0], c_exp[1], bb.ZMax + ez + 4.0)
        exp_labels_2d.append({
            "panel_id": inst_name,
            "base_panel_id": pspec.panel_id,
            "name": pspec.name,
            "xy": _project_3d_to_2d(cam_exp, vp, anchor_3d),
            "ctr_xy": _project_3d_to_2d(cam_exp, vp, c_exp),
        })

    ok2 = ren.render(root_exp)
    w2 = ren.writeToRGB(str(OUT_EXP_RGB))
    print(f"[render] View 2 (Exploded): render={ok2}, writeToRGB={w2}, size={OUT_EXP_RGB.stat().st_size:,}")

    # ------------------------------------------------------------------
    # VIEW 3: HIGH-ANGLE INTERNAL LAYOUT (TRANSLUCENT WALLS + VIVID MODULES)
    # ------------------------------------------------------------------
    root_int = coin.SoSeparator()
    cam_int = _setup_lighting_and_camera(
        root_int,
        eye=(230.0, -330.0, 590.0),
        target=(203.0, 198.0, 40.0),
        fov_deg=38.0,
    )
    # Draw base floor & P16 plate FIRST with low transparency so they look crisp underneath modules
    base_ids = {"P01A_BASE_TECH", "P01B_BASE_HOUSE", "P17_BASE_JOINER_L", "P17_BASE_JOINER_R"}
    for inst_name, pspec, obj, _ex in _iter_panel_instances(doc, panels):
        if inst_name in base_ids:
            root_int.addChild(_shape_to_coin_node(
                obj.Shape, rgb=(0.86, 0.91, 0.96), transparency=0.06, edge_rgb=(0.24, 0.38, 0.54), edge_width=1.35
            ))
        elif inst_name == "P16_PCB_PLATE":
            root_int.addChild(_shape_to_coin_node(
                obj.Shape, rgb=(0.68, 0.92, 0.80), transparency=0.18, edge_rgb=(0.06, 0.44, 0.24), edge_width=1.8
            ))

    # Vivid opaque hardware modules + standoffs + water tube
    hw_labels_int = _add_hardware_nodes(root_int, doc, hw_spec_map, cam_int, vp, edge_w=1.2)

    # Very translucent walls (transparency=0.80) so EVERY internal module is clearly unobstructed
    for inst_name, pspec, obj, _ex in _iter_panel_instances(doc, panels):
        if inst_name in base_ids or inst_name == "P16_PCB_PLATE":
            continue
        root_int.addChild(_shape_to_coin_node(
            obj.Shape, rgb=pspec.color_rgb, transparency=0.80, edge_rgb=(0.12, 0.36, 0.56), edge_width=1.15
        ))

    # Project zone label anchors for the interior layout map
    zone_anchors = {
        "TECH_BAY": _project_3d_to_2d(cam_int, vp, (120.0, 18.0, 4.0)),
        "LIVING_ROOM": _project_3d_to_2d(cam_int, vp, (105.0, 295.0, 4.0)),
        "BEDROOM": _project_3d_to_2d(cam_int, vp, (305.0, 295.0, 4.0)),
        "WATER_GARDEN": _project_3d_to_2d(cam_int, vp, (335.0, 160.0, 4.0)),
        "P16_PLATE": _project_3d_to_2d(cam_int, vp, (82.0, 44.0, 9.0)),
        "WIRING_GAP": _project_3d_to_2d(cam_int, vp, (196.0, 114.0, 17.0)),
    }

    ok3 = ren.render(root_int)
    w3 = ren.writeToRGB(str(OUT_INT_RGB))
    print(f"[render] View 3 (Internal Layout): render={ok3}, writeToRGB={w3}, size={OUT_INT_RGB.stat().st_size:,}")

    OUT_META.write_text(json.dumps({
        "width": IMG_W,
        "height": IMG_H,
        "hw_labels_asm": hw_labels_asm,
        "exp_labels": exp_labels_2d,
        "hw_labels_int": hw_labels_int,
        "zone_anchors": zone_anchors,
    }, indent=2), encoding="utf-8")

    FreeCAD.closeDocument(doc.Name)
    return 0 if (ok1 and w1 and ok2 and w2 and ok3 and w3) else 1


if __name__ in ("__main__", "render_freecad_views"):
    rc = render_views()
    if rc != 0:
        raise SystemExit(rc)
