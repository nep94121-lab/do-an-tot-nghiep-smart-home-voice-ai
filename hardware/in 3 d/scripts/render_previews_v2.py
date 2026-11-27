"""Publication-Grade 3D Previews, Build-Plate Layouts & PrusaSlicer Toolpath Renderer (v2).

Generates all v2 visual deliverables under `hardware/in 3 d/previews/`:
  FreeCAD Coin3D mode (`--mode freecad`, run via FreeCAD 1.1 `freecadcmd.exe`):
    - `_assembled_house_furniture.png`  (1600x1100) Full house + mounts + KiCad PCB/modules + furniture
    - `_exploded_house_v2.png`          (1600x1100) Exploded panels, clips SUP01..SUP15 & furniture FUR01..FUR09
    - `_furniture_showcase.png`         (1400x950)  3x3 labeled 3D card showcase of FUR01..FUR09
    - `_pcb_module_fit_3d.png`          (1400x950)  Zoomed Tech Bay PCB/module snap-fit close-up (s5_05_pcb_fit)

  Python matplotlib/trimesh mode (`--mode plates`, `--mode slicer`, or `--mode python`):
    - `_plate01_layout.png` .. `_plate17_layout.png` (17x 1200x1200 real projected STL triangles on 180x200 bed)
    - `_plates_overview.png`            (6x3 montage grid of all 17 build plates + summary legend)
    - `_slicer_plate_preview.png`       (1800x680 real PrusaSlicer CLI G-code toolpaths for 3 plates, s5_06)

Usage:
    "C:\\Users\\LENOVO\\AppData\\Local\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe" ^
        "hardware/in 3 d/scripts/render_previews_v2.py" -- --clean --mode freecad
    python "hardware/in 3 d/scripts/render_previews_v2.py" --mode python
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import re
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PRINT3D_ROOT = SCRIPT_DIR.parent
MICA_DIR = PRINT3D_ROOT.parent / "mica"

for _p in (str(SCRIPT_DIR), str(MICA_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PARTS_DIR = PRINT3D_ROOT / "parts"
PLATES_DIR = PRINT3D_ROOT / "plates"
PREV_DIR = PRINT3D_ROOT / "previews"
META_DIR = PRINT3D_ROOT / "build_meta"


# ---------------------------------------------------------------------------
# Common utilities (PIL fonts, cleaning stale v1 PNGs, 3D->2D camera projection)
# ---------------------------------------------------------------------------

def clean_previews_dir() -> int:
    """Remove all existing PNGs in `previews/` so no stale v1 renders remain."""
    PREV_DIR.mkdir(parents=True, exist_ok=True)
    removed = 0
    for p in list(PREV_DIR.glob("*.png")) + list(PREV_DIR.glob("*.tmp.rgb")):
        p.unlink(missing_ok=True)
        removed += 1
    print(f"[CLEAN] Removed {removed} stale files from {PREV_DIR}", flush=True)
    return removed


def _load_font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = [
        "C:/Windows/Fonts/segoeui" + ("b.ttf" if bold else ".ttf"),
        "C:/Windows/Fonts/arial" + ("bd.ttf" if bold else ".ttf"),
        "C:/Windows/Fonts/DejaVuSans" + ("-Bold.ttf" if bold else ".ttf"),
    ]
    for c in candidates:
        if pathlib.Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def _vsub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vdot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _vcross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _vnorm(a: tuple[float, float, float]) -> tuple[float, float, float]:
    n = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]) or 1e-9
    return (a[0] / n, a[1] / n, a[2] / n)


def project_3d_to_2d(
    pt: tuple[float, float, float],
    eye: tuple[float, float, float],
    target: tuple[float, float, float],
    width: int,
    height: int,
    fov_deg: float,
    up: tuple[float, float, float] = (0.0, 0.0, 1.0),
) -> tuple[float, float]:
    """Exact pinhole camera projection matching Coin3D SoPerspectiveCamera."""
    fwd = _vnorm(_vsub(target, eye))
    right = _vnorm(_vcross(fwd, up))
    cam_up = _vcross(right, fwd)
    d = _vsub(pt, eye)
    zc = _vdot(d, fwd)
    xc = _vdot(d, right)
    yc = _vdot(d, cam_up)
    if zc <= 1e-3:
        zc = 1e-3
    f = (height / 2.0) / math.tan(math.radians(fov_deg) / 2.0)
    px = width / 2.0 + f * (xc / zc)
    py = height / 2.0 - f * (yc / zc)
    return (px, py)


def draw_callout(
    draw: Any,
    anchor_xy: tuple[float, float],
    label_xy: tuple[float, float],
    text: str,
    accent_rgb: tuple[int, int, int] = (15, 58, 102),
    font_size: int = 14,
) -> None:
    """Draw a crisp leader line + dot + rounded pill label."""
    font = _load_font(font_size, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x, pad_y = 9, 5
    lx, ly = label_xy
    rect = [lx, ly, lx + tw + 2 * pad_x, ly + th + 2 * pad_y]

    # Pick nearest edge midpoint of pill for leader line
    cx = (rect[0] + rect[2]) / 2.0
    cy = (rect[1] + rect[3]) / 2.0
    ax, ay = anchor_xy
    if ax < rect[0]:
        ex, ey = rect[0], cy
    elif ax > rect[2]:
        ex, ey = rect[2], cy
    elif ay < rect[1]:
        ex, ey = cx, rect[1]
    else:
        ex, ey = cx, rect[3]

    # White halo + colored leader line
    draw.line([(ax, ay), (ex, ey)], fill=(255, 255, 255), width=4)
    draw.line([(ax, ay), (ex, ey)], fill=accent_rgb, width=2)
    r = 4.5
    draw.ellipse([(ax - r - 1.5, ay - r - 1.5), (ax + r + 1.5, ay + r + 1.5)], fill=(255, 255, 255))
    draw.ellipse([(ax - r, ay - r), (ax + r, ay + r)], fill=accent_rgb)

    # Pill background + crisp border + text
    draw.rounded_rectangle(rect, radius=6, fill=(255, 255, 255), outline=accent_rgb, width=2)
    draw.text((lx + pad_x, ly + pad_y - 1), text, fill=(14, 28, 46), font=font)


def draw_header_banner(img: Any, title: str, subtitle: str) -> None:
    from PIL import ImageDraw

    w, _h = img.size
    draw = ImageDraw.Draw(img)
    bar_h = 68 if w >= 1200 else 54
    f_title = _load_font(22 if w >= 1400 else 19, bold=True)
    f_sub = _load_font(14 if w >= 1400 else 12, bold=False)
    draw.rectangle([(0, 0), (w, bar_h)], fill=(13, 35, 62))
    draw.rectangle([(0, bar_h - 3), (w, bar_h)], fill=(38, 166, 154))
    draw.text((20, 9), title, fill=(255, 255, 255), font=f_title)
    if subtitle:
        draw.text((20, 40 if w >= 1200 else 32), subtitle, fill=(195, 224, 246), font=f_sub)


def draw_legend_strip(img: Any, items: list[tuple[tuple[int, int, int], str]]) -> None:
    from PIL import ImageDraw

    w, h = img.size
    draw = ImageDraw.Draw(img)
    bar_h = 38
    y0 = h - bar_h
    draw.rectangle([(0, y0), (w, h)], fill=(241, 245, 250))
    draw.line([(0, y0), (w, y0)], fill=(196, 209, 224), width=1)
    font = _load_font(13, bold=True)
    x = 20
    for rgb, lbl in items:
        draw.rounded_rectangle([(x, y0 + 10), (x + 18, y0 + 28)], radius=3, fill=rgb, outline=(40, 50, 65), width=1)
        draw.text((x + 24, y0 + 10), lbl, fill=(22, 36, 54), font=font)
        tb = draw.textbbox((0, 0), lbl, font=font)
        x += (tb[2] - tb[0]) + 44


# ---------------------------------------------------------------------------
# MODE 1: FreeCAD 1.1 Coin3D Offscreen 3D Renders
# ---------------------------------------------------------------------------

def _read_sgi_rgb(path: pathlib.Path):
    from PIL import Image

    raw = path.read_bytes()
    magic, storage, bpc, _dim, xsize, ysize, _zsize = struct.unpack(">HBBHHHH", raw[:12])
    if magic != 474 or storage != 0 or bpc != 1:
        raise ValueError(f"Unsupported SGI format in {path}: magic={magic}, storage={storage}, bpc={bpc}")
    plane = xsize * ysize
    offset = 512
    im_r = Image.frombytes("L", (xsize, ysize), raw[offset : offset + plane])
    im_g = Image.frombytes("L", (xsize, ysize), raw[offset + plane : offset + 2 * plane])
    im_b = Image.frombytes("L", (xsize, ysize), raw[offset + 2 * plane : offset + 3 * plane])
    return Image.merge("RGB", (im_r, im_g, im_b)).transpose(Image.FLIP_TOP_BOTTOM)


def _shape_to_coin_node(
    coin: Any,
    shape: Any,
    rgb: tuple[float, float, float],
    edge_rgb: tuple[float, float, float] = (0.09, 0.16, 0.25),
    transparency: float = 0.0,
    edge_width: float = 1.25,
    tess_tol: float = 0.20,
    draw_edges: bool = True,
):
    sep = coin.SoSeparator()
    verts, tris = shape.tessellate(tess_tol)
    if not verts or not tris:
        return sep

    face_sep = coin.SoSeparator()
    mat = coin.SoMaterial()
    mat.diffuseColor.setValue(*rgb)
    mat.ambientColor.setValue(rgb[0] * 0.48, rgb[1] * 0.48, rgb[2] * 0.48)
    mat.specularColor.setValue(0.24, 0.26, 0.30)
    mat.shininess.setValue(0.42)
    if transparency > 0.0:
        mat.transparency.setValue(transparency)
    face_sep.addChild(mat)

    coords = coin.SoCoordinate3()
    coords.point.setValues(0, len(verts), [(v.x, v.y, v.z) for v in verts])
    face_sep.addChild(coords)

    idx_list: list[int] = []
    for t0, t1, t2 in tris:
        idx_list.extend([t0, t1, t2, -1])
    fset = coin.SoIndexedFaceSet()
    fset.coordIndex.setValues(0, len(idx_list), idx_list)
    face_sep.addChild(fset)
    sep.addChild(face_sep)

    if draw_edges:
        edge_sep = coin.SoSeparator()
        emat = coin.SoMaterial()
        emat.diffuseColor.setValue(*edge_rgb)
        edge_sep.addChild(emat)
        ds = coin.SoDrawStyle()
        ds.lineWidth.setValue(edge_width)
        edge_sep.addChild(ds)

        e_pts: list[tuple[float, float, float]] = []
        e_idx: list[int] = []
        cur = 0
        for edge in shape.Edges:
            try:
                pts = edge.discretize(Deflection=0.28)
            except Exception:
                continue
            if len(pts) < 2:
                continue
            for pt in pts:
                e_pts.append((pt.x, pt.y, pt.z))
                e_idx.append(cur)
                cur += 1
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


def _render_coin_to_pil(
    coin: Any,
    root: Any,
    eye: tuple[float, float, float],
    target: tuple[float, float, float],
    width: int,
    height: int,
    fov_deg: float = 34.0,
    bg_rgb: tuple[float, float, float] = (0.965, 0.976, 0.990),
):
    scene = coin.SoSeparator()
    lm = coin.SoLightModel()
    lm.model.setValue(coin.SoLightModel.PHONG)
    scene.addChild(lm)

    hints = coin.SoShapeHints()
    hints.vertexOrdering.setValue(coin.SoShapeHints.COUNTERCLOCKWISE)
    hints.shapeType.setValue(coin.SoShapeHints.UNKNOWN_SHAPE_TYPE)
    scene.addChild(hints)

    cam = coin.SoPerspectiveCamera()
    cam.heightAngle.setValue(math.radians(fov_deg))
    cam.position.setValue(*eye)
    cam.pointAt(coin.SbVec3f(*target), coin.SbVec3f(0.0, 0.0, 1.0))
    cam.nearDistance.setValue(1.0)
    cam.farDistance.setValue(9000.0)
    scene.addChild(cam)

    for direction, intensity, col in [
        ((-0.40, 0.58, -0.85), 0.90, (1.0, 1.0, 1.0)),
        ((0.72, 0.30, -0.45), 0.55, (0.92, 0.96, 1.0)),
        ((0.12, -0.82, -0.35), 0.44, (1.0, 0.98, 0.94)),
    ]:
        dl = coin.SoDirectionalLight()
        dl.direction.setValue(*direction)
        dl.intensity.setValue(intensity)
        dl.color.setValue(*col)
        scene.addChild(dl)

    scene.addChild(root)

    vp = coin.SbViewportRegion(width, height)
    ren = coin.SoOffscreenRenderer(vp)
    ren.setBackgroundColor(coin.SbColor(*bg_rgb))
    ren.render(scene)

    PREV_DIR.mkdir(parents=True, exist_ok=True)
    tmp_rgb = PREV_DIR / f"_tmp_coin_{os.getpid()}.tmp.rgb"
    ren.writeToRGB(str(tmp_rgb))
    img = _read_sgi_rgb(tmp_rgb)
    tmp_rgb.unlink(missing_ok=True)
    return img


def _panel_visual_rgb(piece: Any, meta: dict[str, Any]) -> tuple[float, float, float]:
    spid = piece.source_panel_id
    idx = (piece.piece_index - 1) % 6
    if spid.startswith(("P01A", "P01B", "P17")):
        base_palette = [
            (0.76, 0.84, 0.91),
            (0.68, 0.78, 0.87),
            (0.79, 0.86, 0.92),
            (0.71, 0.81, 0.89),
            (0.75, 0.83, 0.90),
            (0.66, 0.76, 0.86),
        ]
        return base_palette[idx]
    if spid.startswith(("P09", "P10", "P11", "P12", "P13", "P14")):
        return (0.76, 0.90, 0.83)
    if spid == "P16_PCB_PLATE":
        return (0.64, 0.87, 0.82)
    if spid == "P15_TECH_FASCIA":
        return (0.74, 0.85, 0.95) if idx % 2 == 0 else (0.66, 0.80, 0.92)
    if spid == "P08_DOOR_LEAF":
        return (0.86, 0.72, 0.56)
    wall_palette = [
        (0.92, 0.93, 0.91),
        (0.86, 0.89, 0.88),
        (0.90, 0.92, 0.89),
    ]
    return wall_palette[idx % len(wall_palette)] if piece.piece_count > 1 else (0.91, 0.92, 0.90)


def _support_visual_rgb(pid: str, meta: dict[str, Any]) -> tuple[float, float, float]:
    if pid == "SUP06_HUB_PCB_SNAP_CARRIER":
        # High-contrast warm amber-orange so the 4 split snap pegs protruding through green PCB pop cleanly!
        return (0.92, 0.54, 0.16)
    if pid == "SUP07_RELAY_SNAP_CADDY":
        return (0.90, 0.60, 0.22)
    if pid == "SUP08_PAM8403_SNAP_TRAY":
        return (0.20, 0.62, 0.78)
    if pid == "SUP15_WATER_TANK_LINER":
        return (0.22, 0.62, 0.90)
    if pid.startswith(("SUP01", "SUP02", "SUP03", "SUP04", "SUP05")):
        return (0.88, 0.66, 0.22)
    return tuple(meta.get("color_rgb", [0.85, 0.55, 0.25]))


def _hardware_visual_rgb(hid: str, default_rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    if hid == "HW_PCB":
        return (0.07, 0.46, 0.17)  # Classic KiCad soldermask green
    if hid in ("HW_RELAY1", "HW_RELAY2"):
        return (0.14, 0.38, 0.76)  # SRD-05VDC blue relay module
    if hid == "HW_PAM8403":
        return (0.76, 0.18, 0.22)  # Red/crimson PAM8403 amp PCB
    if hid == "HW_PUMP":
        return (0.22, 0.28, 0.36)
    if hid == "HW_SPEAKER":
        return (0.20, 0.22, 0.26)
    return default_rgb


def _build_unengraved_world_sets():
    """Build exact un-engraved superset BRep solids for fast, razor-clean Coin3D assembly renders."""
    import FreeCAD
    import cad_common as cc
    import build_panels_v2 as bpv2
    import build_mounts_v2 as bmv2
    import build_furniture_v2 as bfv2
    import kicad_pcb_ssot as pcb_ssot
    import mica_design as md
    import print_domain as pd_mod
    import world_assembly_v2 as wa

    cfg = pd_mod.PrintConfig()
    pcb = pcb_ssot.parse_kicad_hub_pcb(run_cli_check=False)
    metas = wa.load_all_metas()

    orig_eng = cc.safe_engrave_top_face
    cc.safe_engrave_top_face = lambda shape, *a, **kw: (shape, True)
    try:
        panels_raw, _ = md.build_design()
        panel_map = {ps.panel_id: ps for ps in panels_raw}
        mortise_map = pd_mod.build_panel_mortise_map(cfg)
        pieces, _ = pd_mod.build_panel_piece_specs(cfg)
        base_cache: dict[str, tuple[Any, dict[str, Any]]] = {}

        panel_items: list[dict[str, Any]] = []
        for piece in pieces:
            meta = metas[piece.part_id]
            sh, _ = bpv2.build_panel_piece_solid(piece, panel_map[piece.source_panel_id], cfg, mortise_map, base_cache)
            origins = [meta["origin_xyz"]] + list(meta.get("extra_origins_xyz", []))
            for idx, orig in enumerate(origins):
                ws = wa.place_panel_in_world(sh, meta, origin_override=orig)
                panel_items.append({
                    "piece": piece,
                    "meta": meta,
                    "shape": ws,
                    "inst_idx": idx,
                    "rgb": _panel_visual_rgb(piece, meta),
                })

        support_items: list[dict[str, Any]] = []
        for sup in pd_mod.build_support_specs(cfg, pcb):
            meta = metas[sup.part_id]
            sh, _ = bmv2.build_mount_solid(sup, cfg)
            for idx, pl in enumerate(meta.get("assembly_placements", [])):
                for sub_lbl, ws in wa.place_support_in_world(sh, meta, pl):
                    support_items.append({
                        "sup": sup,
                        "meta": meta,
                        "label": sub_lbl,
                        "shape": ws,
                        "pl": pl,
                        "rgb": _support_visual_rgb(sup.part_id, meta),
                    })

        furniture_raw: dict[str, tuple[Any, dict[str, Any]]] = {}
        furniture_items: list[dict[str, Any]] = []
        for fur in pd_mod.build_furniture_specs(cfg):
            meta = metas[fur.part_id]
            sh, _ = bfv2.build_one_furniture(fur, cfg)
            furniture_raw[fur.part_id] = (sh, meta)
            for lbl, ws in wa.place_furniture_in_world(sh, meta):
                furniture_items.append({
                    "fur": fur,
                    "meta": meta,
                    "label": lbl,
                    "shape": ws,
                    "rgb": tuple(meta.get("color_rgb", [0.6, 0.5, 0.4])),
                })
    finally:
        cc.safe_engrave_top_face = orig_eng

    pcb_solid, pcb_keepouts = wa.build_real_kicad_pcb_world_solid(pcb)
    hw_solids = wa.build_hardware_world_solids(pcb)

    return {
        "cfg": cfg,
        "pcb": pcb,
        "metas": metas,
        "panels": panel_items,
        "supports": support_items,
        "furniture": furniture_items,
        "furniture_raw": furniture_raw,
        "pcb_solid": pcb_solid,
        "pcb_keepouts": pcb_keepouts,
        "hw_solids": hw_solids,
    }


def render_freecad_previews() -> list[pathlib.Path]:
    """Render all 4 Coin3D 3D views via headless FreeCAD 1.1."""
    import FreeCAD
    import FreeCADGui
    from pivy import coin
    from PIL import Image, ImageDraw

    t0 = time.time()
    FreeCADGui.setupWithoutGUI()
    print("[FREECAD] Building un-engraved superset world solids...", flush=True)
    ws_data = _build_unengraved_world_sets()
    print(f"[FREECAD] Solids ready in {time.time() - t0:.1f}s", flush=True)

    outputs: list[pathlib.Path] = []

    # ------------------------------------------------------------------
    # 1. _assembled_house_furniture.png (1600x1100)
    # ------------------------------------------------------------------
    root_asm = coin.SoSeparator()
    for it in ws_data["panels"]:
        root_asm.addChild(_shape_to_coin_node(
            coin, it["shape"], rgb=it["rgb"], edge_rgb=(0.14, 0.22, 0.32), edge_width=1.15, tess_tol=0.22
        ))
    for it in ws_data["supports"]:
        pid = it["sup"].part_id
        er = (0.10, 0.25, 0.42) if pid == "SUP15_WATER_TANK_LINER" else (0.30, 0.16, 0.05)
        root_asm.addChild(_shape_to_coin_node(
            coin, it["shape"], rgb=it["rgb"], edge_rgb=er, edge_width=1.05, tess_tol=0.18
        ))
    for it in ws_data["furniture"]:
        root_asm.addChild(_shape_to_coin_node(
            coin, it["shape"], rgb=it["rgb"], edge_rgb=(0.16, 0.12, 0.08), edge_width=1.1, tess_tol=0.18
        ))
    for hid, hsh, hrgb in ws_data["hw_solids"]:
        col = _hardware_visual_rgb(hid, hrgb)
        root_asm.addChild(_shape_to_coin_node(
            coin, hsh, rgb=col, edge_rgb=(0.06, 0.12, 0.08), edge_width=1.1, tess_tol=0.18
        ))
    for kname, ksh in ws_data["pcb_keepouts"]:
        kcol = (0.16, 0.17, 0.20) if ("U1" in kname or "U2" in kname or "J" not in kname) else (0.14, 0.42, 0.80)
        root_asm.addChild(_shape_to_coin_node(
            coin, ksh, rgb=kcol, edge_rgb=(0.06, 0.08, 0.10), edge_width=0.9, tess_tol=0.20
        ))

    W1, H1 = 1600, 1100
    eye1 = (475.0, -265.0, 690.0)
    tgt1 = (203.0, 192.0, 32.0)
    fov1 = 34.0
    img_asm = _render_coin_to_pil(coin, root_asm, eye1, tgt1, W1, H1, fov_deg=fov1)
    draw_header_banner(
        img_asm,
        "MO HINH NHA THONG MINH IN 3D v2 — LAP RAP KHONG VIT + NOI THAT & MACH THUC",
        "57 chi tiet (99 ban the) | 0 oc vit, 0 keo, 0 support | Phong khach (Sofa+TV), Phong ngu (Giuong+Den), Vuon (Be nuoc+Cay), Tech Bay (KiCad Hub PCB)",
    )
    draw1 = ImageDraw.Draw(img_asm)
    asm_callouts = [
        ((78.0, 352.0, 26.0), (36, 108), "PHONG KHACH: Sofa FUR01 + TV FUR02/03", (32, 92, 148)),
        ((326.0, 336.0, 22.0), (1120, 108), "PHONG NGU: Giuong FUR04 + Den ngu FUR05", (136, 86, 40)),
        ((122.0, 104.0, 24.0), (28, 720), "TECH BAY: KiCad Hub PCB 100x80 (SUP06)", (16, 114, 48)),
        ((226.0, 114.0, 20.0), (28, 925), "2x Relay (SUP07) + PAM8403 (SUP08)", (28, 78, 152)),
        ((376.0, 163.0, 36.0), (1185, 650), "Chau cay FUR06/08 + Cay mini FUR07", (34, 128, 56)),
        ((292.75, 89.0, 35.0), (1125, 880), "VUON: Be nuoc SUP15 (khong keo) + Bom 5V", (22, 108, 168)),
    ]
    for pt3, lxy, txt, acc in asm_callouts:
        px, py = project_3d_to_2d(pt3, eye1, tgt1, W1, H1, fov1)
        draw_callout(draw1, (px, py), lxy, txt, accent_rgb=acc, font_size=14)

    draw_legend_strip(img_asm, [
        ((186, 206, 226), "San P01A/P01B/P17 (duoi en)"),
        ((232, 235, 229), "Tuong P02..P08 (chot mong)"),
        ((194, 230, 212), "Vuon P09..P14 + SUP15"),
        ((235, 142, 42), "Kep & Gia do SUP01..SUP14"),
        ((18, 117, 43), "KiCad Hub PCB + Relays + PAM8403"),
        ((96, 148, 194), "Noi that FUR01..FUR09"),
    ])
    p_asm = PREV_DIR / "_assembled_house_furniture.png"
    img_asm.save(str(p_asm), format="PNG")
    outputs.append(p_asm)
    print(f"[OK] {p_asm.name} ({W1}x{H1})", flush=True)

    # ------------------------------------------------------------------
    # 2. _exploded_house_v2.png (1600x1100)
    # ------------------------------------------------------------------
    root_exp = coin.SoSeparator()

    def _piece_split_spread(piece: Any) -> tuple[float, float, float]:
        spid = piece.source_panel_id
        idx = piece.piece_index
        cnt = piece.piece_count
        if cnt <= 1:
            return (0.0, 0.0, 0.0)
        if spid == "P01B_BASE_HOUSE" and cnt == 6:
            # 3 columns x 2 rows
            col = (idx - 1) % 3  # 0,1,2
            row = (idx - 1) // 3  # 0,1
            return ((col - 1.0) * 26.0, (row - 0.5) * 26.0, 0.0)
        if spid in ("P01A_BASE_TECH", "P02_WALL_BACK", "P05_WALL_FRONT", "P15_TECH_FASCIA"):
            return ((idx - (cnt + 1) / 2.0) * 26.0, 0.0, 0.0)
        return (0.0, 0.0, 0.0)

    for it in ws_data["panels"]:
        sh = it["shape"].copy()
        ex, ey, ez = [float(v) * 0.85 for v in it["meta"].get("explode_xyz", [0, 0, 0])]
        sx, sy, sz = _piece_split_spread(it["piece"])
        sh.translate(FreeCAD.Vector(ex + sx, ey + sy, ez + sz))
        root_exp.addChild(_shape_to_coin_node(
            coin, sh, rgb=it["rgb"], edge_rgb=(0.14, 0.22, 0.32), edge_width=1.05, tess_tol=0.25
        ))

    for it in ws_data["supports"]:
        sh = it["shape"].copy()
        cat = it["meta"]["category"]
        if cat == "foot_clip":
            dx, dy, dz = (0.0, 0.0, -52.0)
        elif cat in ("corner_clip", "t_clip", "seam_clip"):
            dx, dy, dz = (0.0, 0.0, 72.0)
        elif cat == "tenon_riser":
            dx, dy, dz = (-35.0, -18.0, 32.0)
        elif cat == "tenon_peg":
            dx, dy, dz = (-15.0, -10.0, 56.0)
        elif cat == "pcb_carrier":
            dx, dy, dz = (-46.0, -18.0, 96.0)
        elif cat in ("relay_caddy", "pam_tray"):
            dx, dy, dz = (-12.0, -24.0, 88.0)
        elif cat == "water_liner":
            dx, dy, dz = (45.0, -25.0, 68.0)
        elif cat in ("door_hinge", "servo_link_clip", "sg90_saddle"):
            dx, dy, dz = (0.0, -45.0, 30.0)
        elif cat == "speaker_retainer":
            dx, dy, dz = (0.0, -68.0, 12.0)
        else:
            dx, dy, dz = (0.0, 22.0, 40.0)
        sh.translate(FreeCAD.Vector(dx, dy, dz))
        root_exp.addChild(_shape_to_coin_node(
            coin, sh, rgb=it["rgb"], edge_rgb=(0.28, 0.14, 0.05), edge_width=0.95, tess_tol=0.22
        ))

    for it in ws_data["furniture"]:
        sh = it["shape"].copy()
        cat = it["meta"]["category"]
        if cat == "floor_peg":
            dz = 26.0
        elif cat in ("tv_screen", "mini_tree"):
            dz = 138.0
        else:
            dz = 78.0
        sh.translate(FreeCAD.Vector(0.0, 14.0 if cat not in ("plant_pot", "plant_pot_small", "mini_tree") else -20.0, dz))
        root_exp.addChild(_shape_to_coin_node(
            coin, sh, rgb=it["rgb"], edge_rgb=(0.16, 0.12, 0.08), edge_width=1.0, tess_tol=0.22
        ))

    for hid, hsh, hrgb in ws_data["hw_solids"]:
        sh = hsh.copy()
        if hid == "HW_PCB":
            sh.translate(FreeCAD.Vector(-46.0, -18.0, 142.0))
        elif hid in ("HW_RELAY1", "HW_RELAY2", "HW_PAM8403"):
            sh.translate(FreeCAD.Vector(-12.0, -24.0, 134.0))
        elif hid == "HW_PUMP":
            sh.translate(FreeCAD.Vector(45.0, -25.0, 122.0))
        else:
            continue
        root_exp.addChild(_shape_to_coin_node(
            coin, sh, rgb=_hardware_visual_rgb(hid, hrgb), edge_rgb=(0.06, 0.12, 0.08), edge_width=1.0, tess_tol=0.22
        ))

    for kname, ksh in ws_data["pcb_keepouts"]:
        sh = ksh.copy()
        sh.translate(FreeCAD.Vector(-46.0, -18.0, 142.0))
        kcol = (0.16, 0.17, 0.20) if ("U1" in kname or "U2" in kname or "J" not in kname) else (0.14, 0.42, 0.80)
        root_exp.addChild(_shape_to_coin_node(
            coin, sh, rgb=kcol, edge_rgb=(0.06, 0.08, 0.10), edge_width=0.85, tess_tol=0.22
        ))

    W2, H2 = 1600, 1100
    eye2 = (745.0, -575.0, 655.0)
    tgt2 = (205.0, 195.0, 62.0)
    fov2 = 36.5
    img_exp = _render_coin_to_pil(coin, root_exp, eye2, tgt2, W2, H2, fov_deg=fov2)
    draw_header_banner(
        img_exp,
        "HINH CHIEU PHAN RA 3D v2 — TAM CHIA MANH DUOI EN, KEP KHONG VIT & NOI THAT",
        "Phan tach 29 manh tam (<= 170x190 mm), 19 bo kep/khay SUP01..SUP15 (0 oc vit), 9 nhom noi that FUR01..FUR09 + Hub PCB/Relays",
    )
    draw2 = ImageDraw.Draw(img_exp)
    exp_callouts = [
        ((36.0, 81.0, 162.0), (34, 150), "KiCad Hub PCB + SUP06 + P16", (16, 114, 48)),
        ((78.0, 366.0, 108.0), (480, 96), "Noi that FUR01..05 + Chot san FUR09", (38, 92, 152)),
        ((393.0, 382.0, 218.0), (1125, 115), "Kep goc SUP01/01B & Kep noi SUP03", (184, 96, 18)),
        ((337.0, 64.0, 158.0), (1165, 585), "Be nuoc SUP15 + Bom + Cay FUR06/07", (22, 108, 168)),
        ((200.0, 5.0, -55.0), (1135, 920), "Chan de SUP04 + San chia manh P01A/B", (52, 78, 112)),
    ]
    for pt3, lxy, txt, acc in exp_callouts:
        px, py = project_3d_to_2d(pt3, eye2, tgt2, W2, H2, fov2)
        draw_callout(draw2, (px, py), lxy, txt, accent_rgb=acc, font_size=14)

    draw_legend_strip(img_exp, [
        ((186, 206, 226), "Manh san P01A (3) + P01B (6)"),
        ((232, 235, 229), "Tuong P02 (3) + P05 (3) + P03/04/06"),
        ((235, 142, 42), "Kep & gia do SUP01..SUP15"),
        ((18, 117, 43), "Mach KiCad Hub PCB + Relays + PAM"),
        ((96, 148, 194), "Noi that FUR01..FUR09"),
    ])
    p_exp = PREV_DIR / "_exploded_house_v2.png"
    img_exp.save(str(p_exp), format="PNG")
    outputs.append(p_exp)
    print(f"[OK] {p_exp.name} ({W2}x{H2})", flush=True)

    # ------------------------------------------------------------------
    # 3. _furniture_showcase.png (1400x950 — 3x3 crisp Coin3D cards for FUR01..FUR09)
    # ------------------------------------------------------------------
    W3, H3 = 1400, 950
    canvas = Image.new("RGB", (W3, H3), (242, 246, 251))
    draw_header_banner(
        canvas,
        "BO 9 CHI TIET NOI THAT & CAY CANH IN 3D (FUR01 - FUR09) — KHONG SUPPORT, CHOT SAN",
        "Ty le mo hinh nha thong minh (386x190 mm) | Moi mon lap khop mong chot san FUR09 (0 keo, 0 vit) | In phang Z=0",
    )
    draw3 = ImageDraw.Draw(canvas)

    fur_order = [
        ("FUR01_SOFA", "Sofa 3 cho / Living Sofa"),
        ("FUR02_TV_STAND", "Ke Tivi / TV Stand"),
        ("FUR03_TV_SCREEN", "Man hinh TV / TV Screen"),
        ("FUR04_BED", "Giuong ngu / Double Bed"),
        ("FUR05_BEDSIDE_TABLE", "Tu & Den ngu / Bedside Lamp"),
        ("FUR06_PLANT_POT_LARGE", "Chau cay lon / Large Planter"),
        ("FUR07_MINI_TREE", "Cay mini 2 nua / Cross Mini Tree"),
        ("FUR08_PLANT_POT_SMALL", "Chau hoa nho / Small Pot"),
        ("FUR09_FLOOR_TENON_PEG", "Chot mong san / Floor Tenon Peg"),
    ]
    room_badge_col = {
        "Living Room": (38, 104, 168),
        "Bedroom": (152, 92, 42),
        "Outdoor / Garden": (34, 134, 68),
        "Living Room / Bedroom / Outdoor": (96, 82, 138),
    }

    margin_x, top_y, gap_x, gap_y = 24, 84, 18, 16
    card_w = (W3 - 2 * margin_x - 2 * gap_x) // 3  # 438
    card_h = (H3 - top_y - 20 - 2 * gap_y) // 3    # 271
    render_h = card_h - 68

    f_code = _load_font(15, bold=True)
    f_room = _load_font(12, bold=True)
    f_name = _load_font(14, bold=True)
    f_dims = _load_font(12, bold=False)

    for idx, (fid, bilingual_name) in enumerate(fur_order):
        r = idx // 3
        c = idx % 3
        x0 = margin_x + c * (card_w + gap_x)
        y0 = top_y + r * (card_h + gap_y)

        raw_sh, meta = ws_data["furniture_raw"][fid]
        col_rgb = tuple(meta.get("color_rgb", [0.55, 0.50, 0.42]))
        tile_root = coin.SoSeparator()

        if fid == "FUR03_TV_SCREEN":
            # Stand TV upright for recognizable showcase orientation
            s = raw_sh.copy()
            s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
            bb = s.BoundBox
            s.translate(FreeCAD.Vector(-bb.Center.x, -bb.Center.y, -bb.ZMin))
            tile_root.addChild(_shape_to_coin_node(coin, s, rgb=col_rgb, edge_rgb=(0.06, 0.08, 0.12), edge_width=1.4, tess_tol=0.12))
            vis_bb = s.BoundBox
        elif fid == "FUR07_MINI_TREE":
            # Assemble the 2 cross-halving solids into upright 3D tree
            solids = sorted(raw_sh.Solids, key=lambda sol: sol.BoundBox.XMin)
            sa = solids[0].copy()
            sb = solids[1].copy()
            bba, bbb = sa.BoundBox, sb.BoundBox
            sa.translate(FreeCAD.Vector(-(bba.XMin + bba.XMax) / 2.0, -bba.YMin, -(bba.ZMin + bba.ZMax) / 2.0))
            sa.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
            sb.translate(FreeCAD.Vector(-(bbb.XMin + bbb.XMax) / 2.0, -bbb.YMin, -(bbb.ZMin + bbb.ZMax) / 2.0))
            sb.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
            sb.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 90.0)
            tile_root.addChild(_shape_to_coin_node(coin, sa, rgb=(0.20, 0.62, 0.28), edge_rgb=(0.07, 0.24, 0.10), edge_width=1.3, tess_tol=0.12))
            tile_root.addChild(_shape_to_coin_node(coin, sb, rgb=(0.28, 0.70, 0.34), edge_rgb=(0.07, 0.24, 0.10), edge_width=1.3, tess_tol=0.12))
            vis_bb = sa.BoundBox
            vis_bb.add(sb.BoundBox)
        elif fid == "FUR09_FLOOR_TENON_PEG":
            # Stand peg upright so press-fit taper is crystal clear
            s = raw_sh.copy()
            s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
            bb = s.BoundBox
            s.translate(FreeCAD.Vector(-bb.Center.x, -bb.Center.y, -bb.ZMin))
            tile_root.addChild(_shape_to_coin_node(coin, s, rgb=col_rgb, edge_rgb=(0.25, 0.18, 0.08), edge_width=1.5, tess_tol=0.08))
            vis_bb = s.BoundBox
        else:
            s = raw_sh.copy()
            bb = s.BoundBox
            s.translate(FreeCAD.Vector(-bb.Center.x, -bb.Center.y, -bb.ZMin))
            tile_root.addChild(_shape_to_coin_node(coin, s, rgb=col_rgb, edge_rgb=(0.14, 0.11, 0.09), edge_width=1.35, tess_tol=0.12))
            vis_bb = s.BoundBox

        cx, cy, cz = vis_bb.Center.x, vis_bb.Center.y, vis_bb.Center.z
        diag = max(10.0, math.hypot(vis_bb.XLength, vis_bb.YLength, vis_bb.ZLength))
        eye_t = (cx + diag * 1.15, cy - diag * 1.38, cz + diag * 1.02)
        tgt_t = (cx, cy, cz)
        tile_img = _render_coin_to_pil(
            coin, tile_root, eye_t, tgt_t, card_w - 4, render_h, fov_deg=31.0, bg_rgb=(0.985, 0.990, 0.996)
        )

        # Card frame
        draw3.rounded_rectangle([(x0, y0), (x0 + card_w, y0 + card_h)], radius=10, fill=(255, 255, 255), outline=(188, 202, 218), width=2)
        canvas.paste(tile_img, (x0 + 2, y0 + 2))

        # Top badges inside card
        short_id = fid.split("_")[0]
        draw3.rounded_rectangle([(x0 + 10, y0 + 10), (x0 + 74, y0 + 34)], radius=5, fill=(15, 42, 74))
        draw3.text((x0 + 18, y0 + 12), short_id, fill=(255, 255, 255), font=f_code)

        room = meta.get("room", "")
        room_short = "All Rooms" if "/" in room and "Living" in room else room
        rcol = room_badge_col.get(room, (68, 92, 118))
        rb = draw3.textbbox((0, 0), room_short, font=f_room)
        rw = rb[2] - rb[0] + 16
        draw3.rounded_rectangle([(x0 + card_w - rw - 10, y0 + 10), (x0 + card_w - 10, y0 + 32)], radius=5, fill=rcol)
        draw3.text((x0 + card_w - rw - 2, y0 + 13), room_short, fill=(255, 255, 255), font=f_room)

        # Card footer
        fy = y0 + render_h + 4
        draw3.line([(x0 + 10, fy), (x0 + card_w - 10, fy)], fill=(214, 224, 236), width=1)
        draw3.text((x0 + 12, fy + 6), bilingual_name, fill=(16, 34, 56), font=f_name)
        bx, by, bz = meta["print_bbox_mm"]
        qty = meta.get("qty", 1)
        dim_line = f"In phang: {bx:.0f} x {by:.0f} x {bz:.0f} mm  |  SL: {qty}x  |  Khong support"
        draw3.text((x0 + 12, fy + 29), dim_line, fill=(76, 98, 122), font=f_dims)
        att = meta.get("vi_name", "")
        if len(att) > 54:
            att = att[:51] + "..."
        draw3.text((x0 + 12, fy + 47), att, fill=(96, 116, 138), font=f_dims)

    p_fur = PREV_DIR / "_furniture_showcase.png"
    canvas.save(str(p_fur), format="PNG")
    outputs.append(p_fur)
    print(f"[OK] {p_fur.name} ({W3}x{H3})", flush=True)

    # ------------------------------------------------------------------
    # 4. _pcb_module_fit_3d.png (1400x950 — Zoomed Tech Bay PCB/Module Fit Close-Up)
    # ------------------------------------------------------------------
    root_pcb = coin.SoSeparator()
    # Include Tech Bay floor P01A (pieces 1 & 2) + P16_PCB_PLATE
    for it in ws_data["panels"]:
        spid = it["piece"].source_panel_id
        if spid == "P01A_BASE_TECH" and it["piece"].piece_index in (1, 2):
            root_pcb.addChild(_shape_to_coin_node(
                coin, it["shape"], rgb=(0.82, 0.87, 0.92), edge_rgb=(0.35, 0.44, 0.54), edge_width=1.0, tess_tol=0.18
            ))
        elif spid == "P16_PCB_PLATE":
            root_pcb.addChild(_shape_to_coin_node(
                coin, it["shape"], rgb=(0.64, 0.88, 0.82), edge_rgb=(0.10, 0.32, 0.28), edge_width=1.35, tess_tol=0.14
            ))

    tech_sups = {
        "SUP05_P16_TENON_RISER",
        "SUP05B_CARRIER_TENON_PEG",
        "SUP06_HUB_PCB_SNAP_CARRIER",
        "SUP07_RELAY_SNAP_CADDY",
        "SUP08_PAM8403_SNAP_TRAY",
    }
    for it in ws_data["supports"]:
        pid = it["sup"].part_id
        if pid not in tech_sups:
            continue
        root_pcb.addChild(_shape_to_coin_node(
            coin, it["shape"], rgb=it["rgb"], edge_rgb=(0.24, 0.12, 0.04), edge_width=1.3, tess_tol=0.10
        ))

    tech_hws = {"HW_PCB", "HW_RELAY1", "HW_RELAY2", "HW_PAM8403"}
    for hid, hsh, hrgb in ws_data["hw_solids"]:
        if hid not in tech_hws:
            continue
        root_pcb.addChild(_shape_to_coin_node(
            coin, hsh, rgb=_hardware_visual_rgb(hid, hrgb), edge_rgb=(0.04, 0.12, 0.06), edge_width=1.35, tess_tol=0.10
        ))

    for kname, ksh in ws_data["pcb_keepouts"]:
        kcol = (0.16, 0.17, 0.20) if ("U1" in kname or "U2" in kname or "J" not in kname) else (0.14, 0.44, 0.84)
        root_pcb.addChild(_shape_to_coin_node(
            coin, ksh, rgb=kcol, edge_rgb=(0.04, 0.06, 0.08), edge_width=1.1, tess_tol=0.12
        ))

    W4, H4 = 1400, 950
    eye4 = (158.0, -118.0, 188.0)
    tgt4 = (158.0, 102.0, 12.0)
    fov4 = 35.0
    img_pcb = _render_coin_to_pil(coin, root_pcb, eye4, tgt4, W4, H4, fov_deg=fov4)
    draw_header_banner(
        img_pcb,
        "CAN CANH 3D LAP GHEP MACH HUB PCB & MODULE DIEN TU (TECH BAY — 0 OC VIT)",
        "Hub PCB thuc KiCad 100x80 (51 footprints + C8/C9, 4 lo Dia 3.2 @ 90x70) | P16 + 4x SUP05 | 2x Relay (SUP07) | PAM8403 (SUP08)",
    )
    draw4 = ImageDraw.Draw(img_pcb)
    pcb_callouts = [
        ((112.0, 112.0, 28.5), (34, 102), "Socket NodeMCU U1/U2, Terminals & C8/C9 (KiCad SSOT)", (28, 42, 62)),
        ((167.0, 139.0, 21.8), (540, 102), "4x Chot dan hoi SUP06 (OD 3.0 -> Lo PCB 3.2)", (204, 96, 12)),
        ((77.0, 69.0, 21.8), (28, 760), "Khung SUP06_HUB_PCB_SNAP_CARRIER (chot SUP05B)", (204, 96, 12)),
        ((180.0, 56.0, 4.0), (28, 845), "Tam P16_PCB_PLATE + 4x Chan nang SUP05 (6 mm)", (20, 116, 102)),
        ((226.0, 136.0, 26.5), (960, 112), "Relay 1 & Relay 2 (50x26) trong khay SUP07 (4 chot)", (24, 78, 162)),
        ((224.0, 52.0, 8.2), (920, 845), "Mach am thanh PAM8403 (21x18) trong khay SUP08", (176, 36, 44)),
    ]
    for pt3, lxy, txt, acc in pcb_callouts:
        px, py = project_3d_to_2d(pt3, eye4, tgt4, W4, H4, fov4)
        draw_callout(draw4, (px, py), lxy, txt, accent_rgb=acc, font_size=14)

    draw_legend_strip(img_pcb, [
        ((18, 117, 43), "Hub PCB KiCad (100x80x1.6)"),
        ((235, 138, 41), "SUP06/SUP07 Khay chot dan hoi"),
        ((163, 224, 209), "P16_PCB_PLATE + SUP05"),
        ((36, 97, 194), "Relay 1/2 (44.5x20.5)"),
        ((194, 46, 56), "PAM8403 + SUP08 Tray"),
        ((41, 44, 51), "NodeMCU Sockets & Terminals"),
    ])
    p_pcb = PREV_DIR / "_pcb_module_fit_3d.png"
    img_pcb.save(str(p_pcb), format="PNG")
    outputs.append(p_pcb)
    print(f"[OK] {p_pcb.name} ({W4}x{H4})", flush=True)

    return outputs


# ---------------------------------------------------------------------------
# MODE 2: Build-Plate Layout Renders (17x 1200x1200 + _plates_overview.png)
# ---------------------------------------------------------------------------

GROUP_COLORS = {
    "base": ("#5B9BD5", "#1F4E79", "Base (San)"),
    "walls": ("#70AD47", "#2B542C", "Walls (Tuong)"),
    "garden": ("#2A9D8F", "#15544C", "Garden (Vuon)"),
    "tech": ("#8E6AC8", "#432874", "Tech Bay"),
    "mounts": ("#F4A261", "#8C3D0A", "Mounts (SUP01..15)"),
    "furniture": ("#E76F51", "#7D2310", "Furniture (FUR01..09)"),
}


def _project_stl_item_2d(mesh: Any, x_mm: float, y_mm: float, w_mm: float, rotated_90: bool):
    """Transform mesh identically to nest_plates.py and return (top_tris_xy, feature_edges_xy)."""
    import numpy as np

    verts = mesh.vertices.copy()
    verts -= mesh.bounds[0]
    if rotated_90:
        # (x, y, z) -> (-y + w_mm, x, z) — MUST copy before writing in-place!
        orig_x = verts[:, 0].copy()
        orig_y = verts[:, 1].copy()
        verts[:, 0] = -orig_y + w_mm
        verts[:, 1] = orig_x
    verts[:, 0] += x_mm
    verts[:, 1] += y_mm

    faces = mesh.faces
    normals = mesh.face_normals
    # Keep triangles with significant XY projection (horizontal/sloped faces -> clean top-down fill)
    up_mask = normals[:, 2] > 0.15
    if not np.any(up_mask):
        up_mask = np.abs(normals[:, 2]) > 0.10
    tris_2d = verts[faces[up_mask]][:, :, :2]

    # Extract crisp CAD feature/silhouette edges (edges shared by a horizontal face & vertical face)
    fadj = mesh.face_adjacency
    fadj_edges = mesh.face_adjacency_edges
    nz0 = np.abs(normals[fadj[:, 0], 2])
    nz1 = np.abs(normals[fadj[:, 1], 2])
    feat_mask = ((nz0 > 0.45) & (nz1 < 0.25)) | ((nz1 > 0.45) & (nz0 < 0.25))
    feat_edges = fadj_edges[feat_mask]
    edge_segs = verts[feat_edges][:, :, :2] if len(feat_edges) > 0 else np.zeros((0, 2, 2))
    return tris_2d, edge_segs


def _short_part_label(part_id: str, w: float, h: float) -> str:
    """Produce a concise, readable label scaled to the part footprint."""
    s = part_id
    s = s.replace("_piece", "\np")
    # For small parts, use ultra-compact code
    min_dim = min(w, h)
    max_dim = max(w, h)
    if max_dim < 12.0:
        return part_id.split("_")[0]
    if max_dim < 26.0 or min_dim < 10.0:
        code = part_id.split("_")[0]
        return f"{code}\n{w:.0f}x{h:.0f}"
    if max_dim < 48.0 or min_dim < 20.0:
        parts = part_id.split("_")
        short = "_".join(parts[:2]) if len(parts) >= 2 else part_id
        return f"{short}\n{w:.0f}x{h:.0f}"
    # Large parts: full readable name + dimensions
    return f"{s}\n{w:.1f} x {h:.1f} mm"


def render_plate_layouts() -> list[pathlib.Path]:
    """Render _plate01_layout.png .. _plate17_layout.png (1200x1200) and _plates_overview.png."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection, PolyCollection
    from matplotlib.patches import Patch, Rectangle
    import trimesh
    from PIL import Image, ImageDraw

    t0 = time.time()
    manifest = json.loads((META_DIR / "plates_manifest.json").read_text(encoding="utf-8"))
    bed_x, bed_y, bed_z = manifest["bed_mm"]
    margin = manifest["margin_mm"]
    usable_x, usable_y, _uz = manifest["usable_mm"]
    plates = manifest["plates"]

    # Cache all unique part STL meshes once
    mesh_cache: dict[str, Any] = {}
    for pl in plates:
        for it in pl["items"]:
            pid = it["part_id"]
            if pid not in mesh_cache:
                mesh_cache[pid] = trimesh.load_mesh(str(PARTS_DIR / f"{pid}.stl"), force="mesh")
    print(f"[PLATES] Loaded {len(mesh_cache)} unique STL meshes in {time.time() - t0:.2f}s", flush=True)

    PREV_DIR.mkdir(parents=True, exist_ok=True)
    plate_pngs: list[tuple[dict[str, Any], pathlib.Path]] = []

    for pl in plates:
        pidx = int(pl["plate_index"])
        pid_name = pl["plate_id"]
        out_png = PREV_DIR / f"_plate{pidx:02d}_layout.png"

        # 7.5 x 7.5 in @ 160 dpi = exact 1200 x 1200 px
        fig = plt.figure(figsize=(7.5, 7.5), dpi=160)
        fig.patch.set_facecolor("white")
        ax = fig.add_axes([0.11, 0.145, 0.84, 0.715])

        # Bed outline (180x200 dark blue) + 5mm safe zone (170x190 dashed green)
        ax.add_patch(Rectangle((0, 0), bed_x, bed_y, facecolor="#F5F7FA", edgecolor="#1B365D", lw=2.4, zorder=1))
        ax.add_patch(Rectangle(
            (margin, margin), usable_x, usable_y,
            facecolor="#FFFFFF", edgecolor="#27AE60", lw=1.5, ls="--", zorder=2
        ))

        present_groups: set[str] = set()
        for it in pl["items"]:
            grp = it["group"]
            present_groups.add(grp)
            fill_hex, edge_hex, _glabel = GROUP_COLORS.get(grp, ("#8899AA", "#334455", grp))
            mesh = mesh_cache[it["part_id"]]
            tris_2d, edge_segs = _project_stl_item_2d(
                mesh, float(it["x_mm"]), float(it["y_mm"]), float(it["w_mm"]), bool(it["rotated_90"])
            )
            if len(tris_2d) > 0:
                pc = PolyCollection(
                    tris_2d, facecolors=fill_hex, edgecolors=fill_hex, linewidths=0.2,
                    antialiaseds=False, alpha=0.86, zorder=4
                )
                ax.add_collection(pc)
            if len(edge_segs) > 0:
                lc = LineCollection(edge_segs, colors=edge_hex, linewidths=0.72, alpha=0.95, zorder=5)
                ax.add_collection(lc)

            # Part label centered on bounding box
            x0, y0 = float(it["x_mm"]), float(it["y_mm"])
            w, h = float(it["w_mm"]), float(it["h_mm"])
            cx, cy = x0 + w / 2.0, y0 + h / 2.0
            lbl = _short_part_label(it["part_id"], w, h)
            rot = 90.0 if (h > w * 1.45 and max(w, h) >= 20.0) else 0.0
            min_side = min(w, h)
            max_side = max(w, h)
            if max_side < 10.0:
                fs = 5.2
            elif max_side < 24.0 or min_side < 12.0:
                fs = 6.0
            elif max_side < 48.0 or min_side < 22.0:
                fs = 6.8
            elif max_side < 90.0:
                fs = 7.6
            else:
                fs = 8.4
            ax.text(
                cx, cy, lbl,
                ha="center", va="center", rotation=rot,
                fontsize=fs, fontweight="bold", color="#0C1E33",
                bbox=dict(boxstyle="round,pad=0.16", facecolor="white", edgecolor=edge_hex, alpha=0.82, lw=0.6),
                zorder=8,
            )

        ax.set_xlim(-8, bed_x + 8)
        ax.set_ylim(-8, bed_y + 8)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xticks(range(0, int(bed_x) + 1, 20))
        ax.set_yticks(range(0, int(bed_y) + 1, 20))
        ax.grid(True, linestyle=":", color="#CBD5E1", linewidth=0.6, zorder=0)
        ax.set_xlabel("X ban in (mm) — 180 mm", fontsize=9.5, fontweight="bold", color="#1B365D")
        ax.set_ylabel("Y ban in (mm) — 200 mm", fontsize=9.5, fontweight="bold", color="#1B365D")
        ax.tick_params(labelsize=8.5)

        # Bed annotation tags
        ax.text(bed_x - 2, bed_y + 2.2, "Bed 180 x 200 mm", ha="right", va="bottom", fontsize=8, fontweight="bold", color="#1B365D")
        ax.text(margin + 2, margin + usable_y - 2.5, "Safe 170 x 190 mm (5 mm margin)", ha="left", va="top", fontsize=7.5, fontweight="bold", color="#1E8449", zorder=9)

        # Top banner via figure header
        ub = pl["used_bbox_mm"]
        fig.patches.append(Rectangle((0, 0.885), 1, 0.115, transform=fig.transFigure, facecolor="#0D233E", edgecolor="none"))
        fig.patches.append(Rectangle((0, 0.880), 1, 0.005, transform=fig.transFigure, facecolor="#26A69A", edgecolor="none"))
        fig.text(
            0.03, 0.948,
            f"BAN IN #{pidx:02d}/17 — {pid_name}",
            fontsize=14, fontweight="bold", color="white", va="center",
        )
        fig.text(
            0.03, 0.908,
            f"So chi tiet: {pl['part_count']}  |  BBox su dung: {ub[0]:.1f} x {ub[1]:.1f} x {ub[2]:.1f} mm  |  Dien tich: {pl['bbox_utilization_pct']:.1f}% bbox ({pl['solid_utilization_pct']:.1f}% solid)",
            fontsize=9.2, color="#C3E0F6", va="center",
        )

        # Bottom legend for groups present on this plate
        handles = [
            Patch(facecolor=GROUP_COLORS[g][0], edgecolor=GROUP_COLORS[g][1], label=GROUP_COLORS[g][2])
            for g in ("base", "walls", "garden", "tech", "mounts", "furniture")
            if g in present_groups
        ]
        handles.append(Patch(facecolor="#F5F7FA", edgecolor="#1B365D", lw=1.6, label="Bed 180x200"))
        handles.append(Patch(facecolor="none", edgecolor="#27AE60", ls="--", lw=1.4, label="Safe 170x190"))
        fig.legend(
            handles=handles, loc="lower center", ncol=min(5, len(handles)),
            frameon=True, facecolor="#F8FAFC", edgecolor="#CBD5E1",
            fontsize=8.0, bbox_to_anchor=(0.5, 0.012),
        )

        fig.savefig(str(out_png), format="PNG", dpi=160)
        plt.close(fig)
        plate_pngs.append((pl, out_png))

    print(f"[OK] Rendered {len(plate_pngs)} individual plate layouts (1200x1200) in {time.time() - t0:.1f}s", flush=True)

    # ------------------------------------------------------------------
    # _plates_overview.png (6x3 montage of all 17 plates + summary card #18)
    # ------------------------------------------------------------------
    cols, rows = 6, 3
    cell = 340
    pad = 14
    header_h = 84
    ov_w = cols * cell + (cols + 1) * pad
    ov_h = header_h + rows * cell + (rows + 1) * pad
    overview = Image.new("RGB", (ov_w, ov_h), (240, 244, 249))
    draw_header_banner(
        overview,
        "TONG QUAN 17 BAN IN 3D (180 x 200 x 250 mm) — 57 CHI TIET / 99 BAN THE (0 SUPPORT)",
        f"Vung an toan 170x190 mm (le 5 mm) | Khe ho >= 3.0 mm | Can duoi ly thuyet {manifest['theoretical_lower_bound_bbox_ceil']} ban -> Dat {manifest['achieved_plate_count']} ban (Gate G3 PASS)",
    )
    odraw = ImageDraw.Draw(overview)

    for idx, (_pl, p_path) in enumerate(plate_pngs):
        r = idx // cols
        c = idx % cols
        x0 = pad + c * (cell + pad)
        y0 = header_h + pad + r * (cell + pad)
        im = Image.open(p_path).convert("RGB").resize((cell, cell), Image.Resampling.LANCZOS)
        overview.paste(im, (x0, y0))
        odraw.rectangle([(x0, y0), (x0 + cell, y0 + cell)], outline=(148, 166, 188), width=2)

    # Cell 18 (row 2, col 5): Summary & Legend Card
    x18 = pad + 5 * (cell + pad)
    y18 = header_h + pad + 2 * (cell + pad)
    odraw.rounded_rectangle([(x18, y18), (x18 + cell, y18 + cell)], radius=10, fill=(255, 255, 255), outline=(27, 54, 93), width=2)
    odraw.rectangle([(x18, y18), (x18 + cell, y18 + 44)], fill=(13, 35, 62))
    odraw.text((x18 + 14, y18 + 12), "TONG KET BO IN v2", fill=(255, 255, 255), font=_load_font(16, bold=True))

    f_stat = _load_font(13, bold=True)
    f_leg = _load_font(12, bold=False)
    stats = [
        f"Ban in: {manifest['achieved_plate_count']} plates (180x200x250)",
        f"Safe zone: 170 x 190 mm (5 mm)",
        f"Chi tiet doc nhat: {manifest['total_unique_parts']} parts",
        f"Tong so ban the: {manifest['total_part_instances']} instances",
        f"Khoang cach min: >= {manifest['min_spacing_mm']:.1f} mm",
        "0 oc vit | 0 keo | 0 support",
    ]
    sy = y18 + 52
    for st in stats:
        odraw.text((x18 + 14, sy), "• " + st, fill=(18, 36, 56), font=f_stat)
        sy += 21

    odraw.line([(x18 + 12, sy + 4), (x18 + cell - 12, sy + 4)], fill=(203, 213, 225), width=1)
    sy += 11
    odraw.text((x18 + 14, sy), "MAU NHOM CHI TIET:", fill=(27, 54, 93), font=f_stat)
    sy += 20
    for g in ("base", "walls", "garden", "tech", "mounts", "furniture"):
        fh, eh, gl = GROUP_COLORS[g]
        rgb = tuple(int(fh[i : i + 2], 16) for i in (1, 3, 5))
        odraw.rectangle([(x18 + 16, sy + 2), (x18 + 32, sy + 14)], fill=rgb, outline=(40, 50, 60), width=1)
        odraw.text((x18 + 40, sy), gl, fill=(30, 44, 62), font=f_leg)
        sy += 17

    p_ov = PREV_DIR / "_plates_overview.png"
    overview.save(str(p_ov), format="PNG")
    print(f"[OK] {p_ov.name} ({ov_w}x{ov_h})", flush=True)
    return [p for _, p in plate_pngs] + [p_ov]


# ---------------------------------------------------------------------------
# MODE 3: PrusaSlicer CLI G-code Toolpath Preview (_slicer_plate_preview.png)
# ---------------------------------------------------------------------------

def find_prusaslicer_cli() -> pathlib.Path:
    candidates = [
        pathlib.Path(r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe"),
        pathlib.Path(r"C:\Users\LENOVO\datn-wt\agyfeat3_20261126\tools\prusaslicer"),
        PRINT3D_ROOT / ".tools" / "prusaslicer",
    ]
    for c in candidates:
        if c.is_file():
            return c
        if c.is_dir():
            hits = list(c.rglob("prusa-slicer-console.exe"))
            if hits:
                return hits[0]
    raise FileNotFoundError("prusa-slicer-console.exe not found")


def _parse_gcode_metrics_and_segments(gcode_text: str):
    """Parse real PrusaSlicer metrics + extrusion segments (handling both M82 absolute & M83 relative E)."""
    time_str = ""
    filament_mm = 0.0
    filament_g = 0.0

    m_t = re.search(r";\s*estimated printing time \(normal mode\)\s*=\s*(.+)", gcode_text)
    if m_t:
        time_str = m_t.group(1).strip()
    m_mm = re.search(r";\s*filament used \[mm\]\s*=\s*([0-9.]+)", gcode_text)
    if m_mm:
        filament_mm = float(m_mm.group(1))
    m_cm3 = re.search(r";\s*filament used \[cm3\]\s*=\s*([0-9.]+)", gcode_text)
    filament_cm3 = float(m_cm3.group(1)) if m_cm3 else 0.0
    m_g = re.search(r";\s*filament used \[g\]\s*=\s*([0-9.]+)", gcode_text)
    if m_g:
        filament_g = float(m_g.group(1))
    elif filament_cm3 > 0:
        filament_g = filament_cm3 * 1.24
    elif filament_mm > 0:
        filament_g = (filament_mm * math.pi * (1.75 / 2.0) ** 2 / 1000.0) * 1.24

    layer_count = len(re.findall(r"^;LAYER_CHANGE", gcode_text, flags=re.MULTILINE))
    mid_layer = max(2, layer_count // 2)
    top_layer = max(1, layer_count - 1)
    keep_layers = {1, 2, mid_layer, top_layer}

    segs_base: list[tuple[tuple[float, float], tuple[float, float]]] = []
    segs_upper: list[tuple[tuple[float, float], tuple[float, float]]] = []
    segs_skirt: list[tuple[tuple[float, float], tuple[float, float]]] = []

    cx, cy, ce = 0.0, 0.0, 0.0
    rel_e = False
    layer_idx = 0
    cur_type = ""

    re_x = re.compile(r"X([0-9.\-]+)")
    re_y = re.compile(r"Y([0-9.\-]+)")
    re_e = re.compile(r"E([0-9.\-]+)")

    for line in gcode_text.splitlines():
        if line.startswith(";LAYER_CHANGE"):
            layer_idx += 1
            continue
        if line.startswith(";TYPE:"):
            cur_type = line[6:].strip().lower()
            continue
        if line.startswith("M83"):
            rel_e = True
            continue
        if line.startswith("M82"):
            rel_e = False
            continue
        if line.startswith("G92"):
            me = re_e.search(line)
            if me:
                ce = float(me.group(1))
            continue

        if not (line.startswith("G1 ") or line.startswith("G0 ")):
            continue

        mx = re_x.search(line)
        my = re_y.search(line)
        me = re_e.search(line)
        nx = float(mx.group(1)) if mx else cx
        ny = float(my.group(1)) if my else cy
        de = 0.0
        if me:
            ev = float(me.group(1))
            if rel_e:
                de = ev
            else:
                de = ev - ce
                ce = ev

        if layer_idx in keep_layers and de > 1e-6 and (abs(nx - cx) > 1e-4 or abs(ny - cy) > 1e-4):
            seg = ((cx, cy), (nx, ny))
            if "skirt" in cur_type or "brim" in cur_type:
                segs_skirt.append(seg)
            elif layer_idx <= 2:
                segs_base.append(seg)
            else:
                segs_upper.append(seg)
        cx, cy = nx, ny

    metrics = {
        "time_str": time_str or "?",
        "filament_m": round(filament_mm / 1000.0, 2),
        "filament_g": round(filament_g, 1),
        "layer_count": layer_count,
    }
    return metrics, segs_skirt, segs_base, segs_upper


def render_slicer_plate_preview() -> pathlib.Path:
    """Slice 3 representative multi-object 3MF plates with PrusaSlicer CLI and render 1800x680 toolpath preview."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle

    t0 = time.time()
    slicer_exe = find_prusaslicer_cli()
    plates_man = json.loads((META_DIR / "plates_manifest.json").read_text(encoding="utf-8"))
    pl_list = plates_man["plates"]
    pick_indices = [0, 1, max(2, len(pl_list) - 2)]
    plate_files = [pathlib.Path(pl_list[i]["threemf_file"]).name for i in pick_indices]
    bed_x, bed_y = 180.0, 200.0
    margin = 5.0
    usable_x, usable_y = 170.0, 190.0

    # 11.25 x 4.25 in @ 160 dpi = exact 1800 x 680 px
    fig, axes = plt.subplots(1, 3, figsize=(11.25, 4.25), dpi=160)
    fig.patch.set_facecolor("white")

    with tempfile.TemporaryDirectory(prefix="slicer_v2_") as td:
        td_path = pathlib.Path(td)
        for ax, fname in zip(axes, plate_files):
            mf_path = PLATES_DIR / fname
            if not mf_path.exists():
                raise FileNotFoundError(f"Missing plate 3MF: {mf_path}")
            out_gcode = td_path / (mf_path.stem + ".gcode")
            cmd = [
                str(slicer_exe),
                "--export-gcode",
                "--dont-arrange",
                "--bed-shape", "0x0,180x0,180x200,0x200",
                "--max-print-height", "250",
                "--layer-height", "0.2",
                "--nozzle-diameter", "0.4",
                "--filament-diameter", "1.75",
                "--filament-density", "1.24",
                "--perimeters", "3",
                "--fill-density", "20%",
                "--support-material=0",
                "--skirts", "1",
                "--skirt-distance", "2",
                "--output", str(out_gcode),
                str(mf_path),
            ]
            print(f"[SLICER] Slicing {fname}...", flush=True)
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if proc.returncode != 0 or not out_gcode.exists():
                raise RuntimeError(f"PrusaSlicer failed on {fname} (rc={proc.returncode}): {proc.stderr[:400]}")

            gtxt = out_gcode.read_text(encoding="utf-8", errors="ignore")
            metrics, segs_skirt, segs_base, segs_upper = _parse_gcode_metrics_and_segments(gtxt)
            print(
                f"  -> {mf_path.stem}: {metrics['time_str']} | {metrics['filament_g']}g ({metrics['filament_m']}m) | "
                f"{metrics['layer_count']} layers | segs={len(segs_base)}+{len(segs_upper)}",
                flush=True,
            )

            # Draw 180x200 bed & 170x190 safe zone
            ax.add_patch(Rectangle((0, 0), bed_x, bed_y, facecolor="#F5F7FA", edgecolor="#1B365D", lw=2.0, zorder=1))
            ax.add_patch(Rectangle(
                (margin, margin), usable_x, usable_y,
                facecolor="#FFFFFF", edgecolor="#27AE60", lw=1.25, ls="--", zorder=2
            ))
            if segs_skirt:
                ax.add_collection(LineCollection(segs_skirt, colors="#16A085", linewidths=0.75, alpha=0.85, zorder=3))
            if segs_base:
                ax.add_collection(LineCollection(segs_base, colors="#E67E22", linewidths=0.55, alpha=0.88, zorder=4))
            if segs_upper:
                ax.add_collection(LineCollection(segs_upper, colors="#1F618D", linewidths=0.55, alpha=0.82, zorder=5))

            ax.set_xlim(-6, bed_x + 6)
            ax.set_ylim(-6, bed_y + 6)
            ax.set_aspect("equal", adjustable="box")
            ax.set_xticks(range(0, 181, 30))
            ax.set_yticks(range(0, 201, 40))
            ax.grid(True, linestyle=":", color="#CBD5E1", linewidth=0.5, zorder=0)
            ax.tick_params(labelsize=7.5)
            ax.set_xlabel("X ban in (mm)", fontsize=8.2, fontweight="bold", color="#1B365D")
            if ax is axes[0]:
                ax.set_ylabel("Y ban in (mm)", fontsize=8.2, fontweight="bold", color="#1B365D")
            ax.set_title(
                f"{mf_path.stem}\n{metrics['time_str']} | {metrics['filament_g']:.1f} g ({metrics['filament_m']:.2f} m) | {metrics['layer_count']} lop",
                fontsize=8.8, fontweight="bold", color="#0D233E", pad=6,
            )

    # Top dark banner
    fig.patches.append(Rectangle((0, 0.875), 1, 0.125, transform=fig.transFigure, facecolor="#0D233E", edgecolor="none"))
    fig.patches.append(Rectangle((0, 0.869), 1, 0.006, transform=fig.transFigure, facecolor="#26A69A", edgecolor="none"))
    fig.text(
        0.02, 0.952,
        "KIEM CHUNG CAT LOP PRUSASLICER CLI — DUONG CHAY G-CODE THUC TREN BAN IN 180 x 200 x 250 mm",
        fontsize=11.5, fontweight="bold", color="white", va="center",
    )
    fig.text(
        0.02, 0.902,
        "PLA 1.75 mm | Layer 0.20 mm | Nozzle 0.40 mm | 3 Perimeters | 20% Infill | Support: OFF (--dont-arrange, vung an toan 170x190 mm)",
        fontsize=8.3, color="#C3E0F6", va="center",
    )

    legend_handles = [
        Line2D([0], [0], color="#1B365D", lw=2.0, label="Bed 180 x 200 mm"),
        Line2D([0], [0], color="#27AE60", lw=1.3, ls="--", label="Safe zone 170 x 190 mm"),
        Line2D([0], [0], color="#16A085", lw=1.4, label="Skirt (2 mm)"),
        Line2D([0], [0], color="#E67E22", lw=1.5, label="Lop 1-2 (G1 extrusion)"),
        Line2D([0], [0], color="#1F618D", lw=1.5, label="Lop giua/dinh (G1 extrusion)"),
    ]
    fig.legend(
        handles=legend_handles, loc="lower center", ncol=5,
        frameon=True, facecolor="#F8FAFC", edgecolor="#CBD5E1",
        fontsize=7.8, bbox_to_anchor=(0.5, 0.01),
    )

    fig.subplots_adjust(left=0.055, right=0.985, top=0.77, bottom=0.175, wspace=0.16)
    out_png = PREV_DIR / "_slicer_plate_preview.png"
    PREV_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_png), format="PNG", dpi=160)
    plt.close(fig)
    print(f"[OK] {out_png.name} (1800x680) in {time.time() - t0:.1f}s", flush=True)
    return out_png


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    argv = sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = [a for a in argv if not a.endswith(".py")]
    ap = argparse.ArgumentParser(description="Render v2 3D previews, plate layouts, and slicer G-code previews")
    ap.add_argument("--clean", action="store_true", help="Clean stale PNGs in previews/ before rendering")
    ap.add_argument(
        "--mode",
        choices=("freecad", "plates", "slicer", "python", "all"),
        default=os.environ.get("RENDER_V2_MODE", "python"),
        help="Which stage to render",
    )
    args, _unknown = ap.parse_known_args(argv)
    return args


def main() -> int:
    t0 = time.time()
    args = parse_args()
    if args.clean:
        clean_previews_dir()

    if args.mode in ("freecad", "all"):
        render_freecad_previews()
    if args.mode in ("plates", "python", "all"):
        render_plate_layouts()
    if args.mode in ("slicer", "python", "all"):
        render_slicer_plate_preview()

    print(f"DONE (mode={args.mode}) in {time.time() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__" or any(pathlib.Path(a).stem == __name__ for a in sys.argv):
    rc = main()
    if rc != 0:
        raise SystemExit(rc)
