"""Shared FreeCAD 1.1 CAD engraving, export, and bed-fit helpers for 3D-Print Set v2 builders.

Imported by:
  - build_panels_v2.py
  - build_mounts_v2.py
  - build_furniture_v2.py
Outputs STEP + binary STL directly into `hardware/in 3 d/parts/` and metadata into `build_meta/`.
"""

from __future__ import annotations

import json
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
import MeshPart
import Part

import print_domain as pd_mod

PARTS_DIR = PRINT3D_ROOT / "parts"
META_DIR = PRINT3D_ROOT / "build_meta"

FONT_DIR = "C:/Windows/Fonts/"
PRIMARY_FONT = "consolab.ttf"
FALLBACK_FONT = "arialbd.ttf"


def _wires_to_faces_with_holes(wires: list[Any]) -> list[Any]:
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
        y_off = (total_h / 2.0 - font_h) if (idx == 0 and len(lines) == 2) else (-total_h / 2.0 if len(lines) == 2 else -font_h / 2.0)
        comp.translate(FreeCAD.Vector(-(bb.XMin + bb.XMax) / 2.0, y_off - bb.YMin, 0.0))
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
    """Cut crisp engraved text into flat top face at Z = z_top, verifying single valid solid."""
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


def fits_bed_rotatable(bbox_mm: list[float], cfg: pd_mod.PrintConfig) -> bool:
    """True if part fits usable 170x190x245 mm bed envelope (allowing 0 or 90 deg XY rotation)."""
    lo = min(bbox_mm[0], bbox_mm[1])
    hi = max(bbox_mm[0], bbox_mm[1])
    return (lo <= cfg.usable_x + 0.05) and (hi <= cfg.usable_y + 0.05) and (bbox_mm[2] <= cfg.usable_z + 0.05)


def export_part_step_stl(shape: Any, part_id: str, linear_deflection: float = 0.05) -> tuple[pathlib.Path, pathlib.Path, int]:
    """Export exact BRep STEP and watertight binary STL into `hardware/in 3 d/parts/`."""
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    step_path = PARTS_DIR / f"{part_id}.step"
    stl_path = PARTS_DIR / f"{part_id}.stl"

    shape.exportStep(str(step_path))
    mesh_obj = MeshPart.meshFromShape(
        Shape=shape,
        LinearDeflection=linear_deflection,
        AngularDeflection=0.25,
        Relative=False,
    )
    mesh_obj.write(str(stl_path), Format="STL")
    return step_path, stl_path, int(mesh_obj.CountFacets)


def save_part_meta(part_id: str, meta: dict[str, Any]) -> pathlib.Path:
    META_DIR.mkdir(parents=True, exist_ok=True)
    out = META_DIR / f"{part_id}.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return out
