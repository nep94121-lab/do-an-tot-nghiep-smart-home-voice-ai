"""Headless FreeCAD 1.1 Coin3D Offscreen 3D Renderer for Smart Home Acrylic House Screenshots.

Renders crisp >=1920px 3D screenshots directly from `smarthome_mica_house.FCStd`
without opening any GUI window (uses FreeCADGui.setupWithoutGUI + pivy.coin.SoOffscreenRenderer).

Run with FreeCADCmd:
    "C:\\Users\\LENOVO\\AppData\\Local\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe" hardware/freecad/mica/render_freecad_views.py

Outputs raw RGB frames + camera projection metadata JSON for crisp Pillow annotation:
    - hardware/freecad/mica/_tmp_assembly.rgb
    - hardware/freecad/mica/_tmp_exploded.rgb
    - hardware/freecad/mica/_tmp_render_meta.json
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

    # Tessellate BRep faces cleanly
    verts, tris = shape.tessellate(0.25)

    # Shaded face geometry
    face_sep = coin.SoSeparator()
    mat = coin.SoMaterial()
    mat.diffuseColor.setValue(*rgb)
    mat.ambientColor.setValue(rgb[0] * 0.45, rgb[1] * 0.45, rgb[2] * 0.45)
    mat.specularColor.setValue(0.35, 0.38, 0.42)
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

    # Crisp wireframe BRep edges (highlights slots, tabs, holes, cutouts clearly!)
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


def _setup_lighting_and_camera(root, eye, target, up=(0.0, 0.0, 1.0), fov_deg=34.0):
    # Subtle ambient + key + fill + rim directional lights for crisp acrylic depth
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
    cam.farDistance.setValue(5000.0)
    root.addChild(cam)

    for direction, intensity, col in [
        ((-0.45, 0.65, -0.75), 0.90, (1.0, 1.0, 1.0)),
        ((0.70, 0.30, -0.40), 0.55, (0.90, 0.95, 1.0)),
        ((0.15, -0.80, -0.35), 0.40, (1.0, 0.98, 0.94)),
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


def render_views() -> int:
    FreeCADGui.setupWithoutGUI()
    doc = FreeCAD.openDocument(str(FCSTD_PATH))
    panels, _joints = md.build_design()
    panel_spec_map = {p.panel_id: p for p in panels}
    hw_spec_map = {h.part_id: h for h in md.HARDWARE_PARTS}

    vp = coin.SbViewportRegion(IMG_W, IMG_H)
    ren = coin.SoOffscreenRenderer(vp)
    ren.setBackgroundColor(coin.SbColor(0.965, 0.980, 0.995))

    # ------------------------------------------------------------------
    # VIEW 1: ASSEMBLED TRANSPARENT ACRYLIC HOUSE + REAL HARDWARE MODULES
    # ------------------------------------------------------------------
    root_asm = coin.SoSeparator()
    cam_asm = _setup_lighting_and_camera(
        root_asm,
        eye=(495.0, -345.0, 295.0),
        target=(188.0, 128.0, 42.0),
        fov_deg=34.0,
    )

    # Render opaque hardware FIRST so transparent acrylic panels blend cleanly over them!
    hw_grp = doc.getObject("Hardware_Reference")
    hw_labels_2d = []
    if hw_grp:
        for obj in hw_grp.Group:
            if not hasattr(obj, "Shape") or obj.Shape.isNull():
                continue
            if obj.Name in hw_spec_map:
                rgb = hw_spec_map[obj.Name].color_rgb
                lbl = hw_spec_map[obj.Name].part_id.replace("HW_", "")
            elif obj.Name.startswith("PCB_Standoff"):
                rgb = (0.84, 0.68, 0.24)
                lbl = None
            elif obj.Name == "HW_WATER_TUBE":
                rgb = (0.42, 0.80, 0.96)
                lbl = None
            else:
                rgb = (0.5, 0.5, 0.5)
                lbl = None
            root_asm.addChild(_shape_to_coin_node(obj.Shape, rgb, transparency=0.0, edge_rgb=(0.12, 0.14, 0.18), edge_width=1.0))
            if lbl:
                bb = obj.Shape.BoundBox
                c3 = (bb.Center.x, bb.Center.y, bb.ZMax)
                hw_labels_2d.append({"id": lbl, "xy": _project_3d_to_2d(cam_asm, vp, c3)})

    # Render transparent acrylic panels
    for pspec in panels:
        obj = doc.getObject(pspec.panel_id)
        if obj is None:
            continue
        root_asm.addChild(_shape_to_coin_node(
            obj.Shape,
            rgb=pspec.color_rgb,
            transparency=0.56,
            edge_rgb=(0.05, 0.24, 0.42),
            edge_width=1.7,
        ))

    ok1 = ren.render(root_asm)
    w1 = ren.writeToRGB(str(OUT_ASM_RGB))
    print(f"[render] Assembly view: render={ok1}, writeToRGB={w1}, size={OUT_ASM_RGB.stat().st_size:,}")

    # ------------------------------------------------------------------
    # VIEW 2: EXPLODED VIEW WITH ALIGNMENT LINES + PROJECTED PANEL IDs
    # ------------------------------------------------------------------
    root_exp = coin.SoSeparator()
    cam_exp = _setup_lighting_and_camera(
        root_exp,
        eye=(680.0, -510.0, 445.0),
        target=(185.0, 118.0, 46.0),
        fov_deg=36.0,
    )

    exp_labels_2d = []
    # Slight color variation per panel group for easy visual tracking
    exp_palette = [
        (0.58, 0.82, 0.98), (0.64, 0.87, 0.99), (0.68, 0.84, 0.99), (0.62, 0.90, 0.86),
        (0.58, 0.88, 0.96), (0.76, 0.80, 0.99), (0.98, 0.84, 0.56), (0.94, 0.82, 0.62),
        (0.56, 0.90, 0.92), (0.50, 0.86, 0.86), (0.62, 0.92, 0.76), (0.64, 0.90, 0.84),
        (0.60, 0.88, 0.90), (0.74, 0.94, 0.68), (0.66, 0.84, 0.99),
    ]
    for idx, pspec in enumerate(panels):
        obj = doc.getObject(pspec.panel_id)
        if obj is None:
            continue
        bb = obj.Shape.BoundBox
        c_asm = (bb.Center.x, bb.Center.y, bb.Center.z)
        ex, ey, ez = (pspec.explode_xyz[0] * 1.15, pspec.explode_xyz[1] * 1.15, pspec.explode_xyz[2] * 1.15)
        c_exp = (c_asm[0] + ex, c_asm[1] + ey, c_asm[2] + ez)

        _add_guide_line(root_exp, c_asm, c_exp)
        root_exp.addChild(_shape_to_coin_node(
            obj.Shape,
            rgb=exp_palette[idx % len(exp_palette)],
            transparency=0.42,
            edge_rgb=(0.05, 0.20, 0.36),
            offset=(ex, ey, ez),
            edge_width=1.7,
        ))
        anchor_3d = (c_exp[0], c_exp[1], bb.ZMax + ez + 4.0)
        exp_labels_2d.append({
            "panel_id": pspec.panel_id,
            "name": pspec.name,
            "xy": _project_3d_to_2d(cam_exp, vp, anchor_3d),
            "ctr_xy": _project_3d_to_2d(cam_exp, vp, c_exp),
        })

    ok2 = ren.render(root_exp)
    w2 = ren.writeToRGB(str(OUT_EXP_RGB))
    print(f"[render] Exploded view: render={ok2}, writeToRGB={w2}, size={OUT_EXP_RGB.stat().st_size:,}")

    OUT_META.write_text(json.dumps({
        "width": IMG_W,
        "height": IMG_H,
        "hw_labels": hw_labels_2d,
        "exp_labels": exp_labels_2d,
    }, indent=2), encoding="utf-8")

    FreeCAD.closeDocument(doc.Name)
    return 0 if (ok1 and w1 and ok2 and w2) else 1


if __name__ in ("__main__", "render_freecad_views"):
    rc = render_views()
    if rc != 0:
        raise SystemExit(rc)
