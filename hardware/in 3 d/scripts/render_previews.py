"""Headless FreeCAD 1.1 Coin3D Offscreen 3D Renderer for 3D-Printable Parts, Supports & Assembly.

Renders crisp shaded PNG previews (with sharp edges + clear engraved dimension visibility)
without opening any GUI window (`FreeCADGui.setupWithoutGUI` + `pivy.coin.SoOffscreenRenderer`).

Run via FreeCADCmd:
    "C:\\Users\\LENOVO\\AppData\\Local\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe" "hardware/in 3 d/scripts/render_previews.py" -- --shard panels-std
    "C:\\Users\\LENOVO\\AppData\\Local\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe" "hardware/in 3 d/scripts/render_previews.py" -- --assembly
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import struct
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
import FreeCADGui
import Part
from pivy import coin
from PIL import Image, ImageDraw, ImageFont

import mica_design as md
import print_domain as pd_mod

STEP_DIR = PRINT3D_ROOT / "STEP"
PREV_DIR = PRINT3D_ROOT / "previews"
META_DIR = PRINT3D_ROOT / "build_meta"


def _read_sgi_rgb(path: pathlib.Path) -> Image.Image:
    """Decode Coin3D SGI .rgb offscreen output into a PIL RGB Image."""
    raw = path.read_bytes()
    magic, storage, bpc, dim, xsize, ysize, zsize = struct.unpack(">HBBHHHH", raw[:12])
    if magic != 474 or storage != 0 or bpc != 1:
        raise ValueError(f"Unsupported SGI format in {path}: magic={magic}, storage={storage}, bpc={bpc}")
    plane = xsize * ysize
    offset = 512
    r = raw[offset : offset + plane]
    g = raw[offset + plane : offset + 2 * plane]
    b = raw[offset + 2 * plane : offset + 3 * plane]
    # SGI scanlines are bottom-to-top -> flip vertically
    im_r = Image.frombytes("L", (xsize, ysize), r)
    im_g = Image.frombytes("L", (xsize, ysize), g)
    im_b = Image.frombytes("L", (xsize, ysize), b)
    return Image.merge("RGB", (im_r, im_g, im_b)).transpose(Image.FLIP_TOP_BOTTOM)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/segoeui" + ("b.ttf" if bold else ".ttf"),
        "C:/Windows/Fonts/arial" + ("bd.ttf" if bold else ".ttf"),
    ]
    for c in candidates:
        if pathlib.Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def _shape_to_coin_node(
    shape: Any,
    rgb: tuple[float, float, float],
    edge_rgb: tuple[float, float, float] = (0.08, 0.16, 0.26),
    transparency: float = 0.0,
    edge_width: float = 1.4,
    tess_tol: float = 0.20,
):
    sep = coin.SoSeparator()
    verts, tris = shape.tessellate(tess_tol)

    face_sep = coin.SoSeparator()
    mat = coin.SoMaterial()
    mat.diffuseColor.setValue(*rgb)
    mat.ambientColor.setValue(rgb[0] * 0.45, rgb[1] * 0.45, rgb[2] * 0.45)
    mat.specularColor.setValue(0.28, 0.30, 0.34)
    mat.shininess.setValue(0.45)
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

    # Sharp edges
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
            pts = edge.discretize(Deflection=0.25)
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


def _render_scene_to_png(
    root: Any,
    eye: tuple[float, float, float],
    target: tuple[float, float, float],
    out_png: pathlib.Path,
    width: int = 1024,
    height: int = 768,
    fov_deg: float = 34.0,
    bg_rgb: tuple[float, float, float] = (0.96, 0.975, 0.99),
    title_banner: str = "",
    subtitle_banner: str = "",
) -> None:
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
    cam.farDistance.setValue(8000.0)
    scene.addChild(cam)

    for direction, intensity, col in [
        ((-0.42, 0.62, -0.82), 0.92, (1.0, 1.0, 1.0)),
        ((0.72, 0.32, -0.45), 0.56, (0.92, 0.96, 1.0)),
        ((0.15, -0.82, -0.32), 0.42, (1.0, 0.98, 0.94)),
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

    out_png.parent.mkdir(parents=True, exist_ok=True)
    tmp_rgb = out_png.with_suffix(".tmp.rgb")
    ren.writeToRGB(str(tmp_rgb))
    img = _read_sgi_rgb(tmp_rgb)
    tmp_rgb.unlink(missing_ok=True)

    if title_banner:
        draw = ImageDraw.Draw(img)
        f_title = _load_font(24 if width >= 1200 else 18, bold=True)
        f_sub = _load_font(15 if width >= 1200 else 12, bold=False)
        bar_h = 66 if width >= 1200 else 52
        draw.rectangle([(0, 0), (width, bar_h)], fill=(15, 39, 68))
        draw.text((18, 8), title_banner, fill=(255, 255, 255), font=f_title)
        if subtitle_banner:
            draw.text((18, 38 if width >= 1200 else 31), subtitle_banner, fill=(196, 224, 248), font=f_sub)

    img.save(str(out_png), format="PNG")


def place_piece_in_world(shape: Any, meta: dict[str, Any], origin_override: list[float] | None = None) -> Any:
    """Transform a print-ready STEP shape back into exact 3D assembled house world coordinates."""
    s = shape.copy()
    lmin = meta["local_bbox_min"]
    su = float(meta["shift_u"])
    sv = float(meta["shift_v"])
    # Undo print-bed origin shift + undo evaluate_panel_2d shift -> back to raw panel local (u, v, w)
    s.translate(FreeCAD.Vector(lmin[0] - su, lmin[1] - sv, lmin[2]))

    plane = meta["plane"]
    ox, oy, oz = origin_override if origin_override is not None else meta["origin_xyz"]

    if plane == "XY":
        # (u, v, w) -> (ox + u, oy + v, oz + w)
        s.translate(FreeCAD.Vector(ox, oy, oz))
    elif plane == "XZ":
        # (u, v, w) -> (ox + u, oy + w, oz + v)
        # Rotate +90 deg around X maps (u, v, w) -> (u, -w, v); to get +w in Y, first mirror? No:
        # Matrix: X' = u + ox, Y' = w + oy, Z' = v + oz (det = -1 if mirrored, so rotate around X by +90 and flip w):
        # Better: rotate +90 around X maps (u, v, w) -> (u, -w, v). Since panel thickness is symmetric on w in [0, T],
        # translating by (ox, oy + T, oz) puts w in [0, T] at Y in [oy, oy + T]!
        T = float(meta["print_bbox_mm"][2])
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
        s.translate(FreeCAD.Vector(ox, oy + T, oz))
    elif plane == "YZ":
        # (u, v, w) -> (ox + w, oy + u, oz + v)
        # Rotate +90 around X -> (u, -w, v), then rotate +90 around Z -> (w, u, v)! det = +1 (pure rigid rotation!)
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 90.0)
        s.translate(FreeCAD.Vector(ox, oy, oz))
    else:
        raise ValueError(f"Unknown plane {plane}")
    return s


def place_support_in_world(shape: Any, sup_meta: dict[str, Any], pl: dict[str, Any]) -> Any:
    """Transform a print-ready support STEP shape into its world 3D assembly placement."""
    s = shape.copy()
    cat = sup_meta["category"]
    pid = sup_meta["part_id"]
    bx, by, bz = sup_meta["print_bbox_mm"]

    if cat == "clip":
        # Printed upside-down (cap at Z=0, legs rising); flip 180 deg around X so cap is on top and legs point down
        s.rotate(FreeCAD.Vector(0, by / 2.0, bz / 2.0), FreeCAD.Vector(1, 0, 0), 180.0)
    elif cat == "standoff":
        # Standoff center is at (flange_od/2, flange_od/2) in print coords -> center bore on (0, 0)
        fod = float(sup_meta["print_bbox_mm"][1])
        s.translate(FreeCAD.Vector(-fod / 2.0, -fod / 2.0, 0.0))
    elif pid == "SUP11_SPEAKER_28MM_RETAINER":
        # Rotate to vertical XZ plane behind speaker
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
        s.translate(FreeCAD.Vector(0, bz, 0))
    elif pid == "SUP12_DOOR_HINGE_BRACKET":
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 90.0)
        s.translate(FreeCAD.Vector(0, bz, 0))

    rot_z = float(pl.get("rot_z", 0.0))
    if abs(rot_z) > 1e-4:
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), rot_z)
    s.translate(FreeCAD.Vector(float(pl["x"]), float(pl["y"]), float(pl["z"])))
    return s


def render_single_part(part_id: str) -> pathlib.Path:
    meta = json.loads((META_DIR / f"{part_id}.json").read_text(encoding="utf-8"))
    shape = Part.Shape()
    shape.read(str(STEP_DIR / f"{part_id}.step"))
    bb = shape.BoundBox
    cx, cy, cz = bb.Center.x, bb.Center.y, bb.Center.z
    diag = max(25.0, math.hypot(bb.XLength, bb.YLength, bb.ZLength))

    root = coin.SoSeparator()
    rgb = tuple(meta.get("color_rgb", [0.72, 0.88, 0.96]))
    root.addChild(_shape_to_coin_node(shape, rgb=rgb, edge_rgb=(0.07, 0.16, 0.28), edge_width=1.35, tess_tol=0.15))

    # High isometric angle so engraved text on top face is super clear
    eye = (cx + diag * 0.58, cy - diag * 0.82, cz + diag * 1.15)
    target = (cx, cy, cz)
    out_png = PREV_DIR / f"{part_id}.png"
    bx, by, bz = meta["print_bbox_mm"]
    _render_scene_to_png(
        root,
        eye=eye,
        target=target,
        out_png=out_png,
        width=960,
        height=720,
        title_banner=f"{part_id}  ({bx:.1f} x {by:.1f} x {bz:.1f} mm)",
        subtitle_banner=f"{meta.get('vi_name', '')} | SL: {meta.get('qty', 1)} | Khac: {meta.get('engrave_text', '')}",
    )
    meta["preview_png"] = f"previews/{out_png.name}"
    (META_DIR / f"{part_id}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out_png


def render_assembly_and_showcases() -> list[pathlib.Path]:
    """Render assembled house + supports, exploded view, split-part showcase, and supports showcase."""
    cfg = pd_mod.PrintConfig()
    pieces, _ = pd_mod.build_panel_piece_specs(cfg)
    supports = pd_mod.build_support_specs(cfg)

    outputs: list[pathlib.Path] = []

    # 1. ASSEMBLED HOUSE + SUPPORTS
    root_asm = coin.SoSeparator()
    # Slight distinct tint per split piece so dovetail seams are visually unmistakable!
    split_tints = [
        (0.70, 0.88, 0.97),
        (0.58, 0.82, 0.95),
        (0.76, 0.91, 0.96),
        (0.64, 0.85, 0.93),
        (0.72, 0.86, 0.98),
        (0.60, 0.80, 0.92),
    ]
    for piece in pieces:
        meta = json.loads((META_DIR / f"{piece.part_id}.json").read_text(encoding="utf-8"))
        sh = Part.Shape()
        sh.read(str(STEP_DIR / f"{piece.part_id}.step"))
        rgb = split_tints[(piece.piece_index - 1) % len(split_tints)] if piece.piece_count > 1 else tuple(meta["color_rgb"])
        wsh = place_piece_in_world(sh, meta)
        root_asm.addChild(_shape_to_coin_node(wsh, rgb=rgb, edge_rgb=(0.06, 0.20, 0.34), edge_width=1.25))
        for eo in meta.get("extra_origins_xyz", []):
            wsh2 = place_piece_in_world(sh, meta, origin_override=eo)
            root_asm.addChild(_shape_to_coin_node(wsh2, rgb=rgb, edge_rgb=(0.06, 0.20, 0.34), edge_width=1.25))

    for sup in supports:
        meta = json.loads((META_DIR / f"{sup.part_id}.json").read_text(encoding="utf-8"))
        if meta.get("exclude_from_default_assembly"):
            continue
        sh = Part.Shape()
        sh.read(str(STEP_DIR / f"{sup.part_id}.step"))
        for pl in meta["assembly_placements"]:
            wsh = place_support_in_world(sh, meta, pl)
            root_asm.addChild(_shape_to_coin_node(wsh, rgb=tuple(meta["color_rgb"]), edge_rgb=(0.25, 0.14, 0.05), edge_width=1.1))

    asm_png = PREV_DIR / "_assembled_house_3dprint.png"
    _render_scene_to_png(
        root_asm,
        eye=(590.0, -400.0, 360.0),
        target=(200.0, 185.0, 52.0),
        out_png=asm_png,
        width=1600,
        height=1050,
        title_banner="MO HINH NHA THONG MINH IN 3D — LAP RAP HOAN CHINH + PHU KIEN SUPOT",
        subtitle_banner="18 tam chia manh khop ban in 220x220mm (duoi en 0.20mm) + Ke goc, Kep noi, Chan de, Tru do PCB/Module | 0 va cham",
    )
    outputs.append(asm_png)

    # 2. EXPLODED VIEW (panels separated + split pieces pulled slightly apart along seam + supports exploded)
    root_exp = coin.SoSeparator()
    for piece in pieces:
        meta = json.loads((META_DIR / f"{piece.part_id}.json").read_text(encoding="utf-8"))
        sh = Part.Shape()
        sh.read(str(STEP_DIR / f"{piece.part_id}.step"))
        rgb = split_tints[(piece.piece_index - 1) % len(split_tints)] if piece.piece_count > 1 else tuple(meta["color_rgb"])
        wsh = place_piece_in_world(sh, meta)
        ex, ey, ez = meta["explode_xyz"]
        # Add subtle extra spread between split pieces so dovetails are clearly visible!
        if piece.piece_count > 1:
            spread = (piece.piece_index - (piece.piece_count + 1) / 2.0) * 18.0
            ex += spread
        wsh.translate(FreeCAD.Vector(ex, ey, ez))
        root_exp.addChild(_shape_to_coin_node(wsh, rgb=rgb, edge_rgb=(0.06, 0.20, 0.34), edge_width=1.2))

    for sup in supports:
        meta = json.loads((META_DIR / f"{sup.part_id}.json").read_text(encoding="utf-8"))
        if meta.get("exclude_from_default_assembly"):
            continue
        sh = Part.Shape()
        sh.read(str(STEP_DIR / f"{sup.part_id}.step"))
        for pl in meta["assembly_placements"]:
            wsh = place_support_in_world(sh, meta, pl)
            ez = -42.0 if sup.category == "foot" else (48.0 if sup.category in ("clip", "standoff") else 22.0)
            wsh.translate(FreeCAD.Vector(0.0, 0.0, ez))
            root_exp.addChild(_shape_to_coin_node(wsh, rgb=tuple(meta["color_rgb"]), edge_rgb=(0.25, 0.14, 0.05), edge_width=1.0))

    exp_png = PREV_DIR / "_exploded_house_3dprint.png"
    _render_scene_to_png(
        root_exp,
        eye=(740.0, -520.0, 490.0),
        target=(200.0, 185.0, 50.0),
        out_png=exp_png,
        width=1600,
        height=1050,
        title_banner="HINH CHIEU PHAN RA 3D — CAC TAM CHIA MANH & BO PHU KIEN SUPOT",
        subtitle_banner="Hien thi ro khop noi duoi en giua cac manh, chan de nang nha, ke goc 90 do, kep noi va tru do mach",
    )
    outputs.append(exp_png)

    # 3. SPLIT PART EXAMPLE SHOWCASE (P02_WALL_BACK_piece1of2 + piece2of2 side-by-side pulled 18mm apart)
    root_split = coin.SoSeparator()
    p02_pieces = [p for p in pieces if p.source_panel_id == "P02_WALL_BACK"]
    x_cursor = 0.0
    for idx, piece in enumerate(p02_pieces):
        meta = json.loads((META_DIR / f"{piece.part_id}.json").read_text(encoding="utf-8"))
        sh = Part.Shape()
        sh.read(str(STEP_DIR / f"{piece.part_id}.step"))
        # Place in flat local coordinates separated by 18mm gap so dovetail male/female are crystal clear
        sh.translate(FreeCAD.Vector(meta["local_bbox_min"][0] + idx * 18.0, meta["local_bbox_min"][1], 0.0))
        rgb = (0.68, 0.87, 0.97) if idx == 0 else (0.50, 0.78, 0.94)
        root_split.addChild(_shape_to_coin_node(sh, rgb=rgb, edge_rgb=(0.05, 0.18, 0.32), edge_width=1.5, tess_tol=0.12))

    split_png = PREV_DIR / "_split_part_example.png"
    _render_scene_to_png(
        root_split,
        eye=(205.0, -145.0, 340.0),
        target=(202.0, 75.0, 1.5),
        out_png=split_png,
        width=1600,
        height=1000,
        title_banner="VI DU TAM LON CHIA MANH: P02_WALL_BACK (386 x 150 mm -> 2 MANH DUOI EN)",
        subtitle_banner="piece1of2 + piece2of2 (<= 210x210 mm) | Khop duoi en khe ho 0.20 mm | Khac chim ma + kich thuoc mat tren",
    )
    outputs.append(split_png)

    # 4. ALL 12 PRINTABLE SUPPORTS GALLERY (arranged on a clean 4x3 virtual showcase tray)
    root_sup = coin.SoSeparator()
    cols = 4
    cell_x, cell_y = 112.0, 96.0
    for idx, sup in enumerate(supports):
        meta = json.loads((META_DIR / f"{sup.part_id}.json").read_text(encoding="utf-8"))
        sh = Part.Shape()
        sh.read(str(STEP_DIR / f"{sup.part_id}.step"))
        bb = sh.BoundBox
        r = idx // cols
        c = idx % cols
        cx = c * cell_x + cell_x / 2.0
        cy = (2 - r) * cell_y + cell_y / 2.0
        sh.translate(FreeCAD.Vector(cx - bb.XLength / 2.0, cy - bb.YLength / 2.0, 0.0))
        root_sup.addChild(_shape_to_coin_node(sh, rgb=tuple(meta["color_rgb"]), edge_rgb=(0.18, 0.12, 0.06), edge_width=1.35, tess_tol=0.12))

    sup_png = PREV_DIR / "_supports_showcase.png"
    _render_scene_to_png(
        root_sup,
        eye=(224.0, -190.0, 390.0),
        target=(224.0, 140.0, 6.0),
        out_png=sup_png,
        width=1600,
        height=1050,
        title_banner="BO 12 PHU KIEN SUPOT IN 3D (SUP01 - SUP12) — IN PHANG KHONG CAN SUPPORT",
        subtitle_banner="Ke goc tuong, Kep noi manh, Chan de nha, Tru do PCB 90x70 & Module 44.5x20.5, Gia PAM8403, Thanh ep loa, Ban le cua",
    )
    outputs.append(sup_png)

    return outputs


def parse_args() -> argparse.Namespace:
    argv = sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = [a for a in argv if not a.endswith(".py")]
    ap = argparse.ArgumentParser(description="Render 3D PNG previews via FreeCAD Coin3D")
    ap.add_argument("--parts", type=str, default=os.environ.get("PRINT3D_PARTS", ""), help="Comma-separated part_ids")
    ap.add_argument("--shard", type=str, default=os.environ.get("PRINT3D_SHARD", ""), help="Named shard from print_domain.get_swarm_shards()")
    ap.add_argument("--assembly", action="store_true", default=(os.environ.get("PRINT3D_ASSEMBLY", "") == "1"), help="Render assembled, exploded, split example, and supports showcase")
    args, _unknown = ap.parse_known_args(argv)
    return args


def main() -> int:
    t0 = time.time()
    args = parse_args()
    FreeCADGui.setupWithoutGUI()

    cfg = pd_mod.PrintConfig()
    pieces, _ = pd_mod.build_panel_piece_specs(cfg)
    supports = pd_mod.build_support_specs(cfg)
    all_ids = [p.part_id for p in pieces] + [s.part_id for s in supports]

    rendered = 0
    if args.assembly:
        outs = render_assembly_and_showcases()
        for o in outs:
            print(f"[OK] RENDER ASSEMBLY: {o.name}")
        rendered += len(outs)
    else:
        target_ids: list[str]
        if args.shard:
            target_ids = pd_mod.get_swarm_shards(cfg)[args.shard]
        elif args.parts:
            target_ids = [s.strip() for s in args.parts.split(",") if s.strip()]
        else:
            target_ids = all_ids
        for pid in target_ids:
            out = render_single_part(pid)
            print(f"[OK] RENDER {pid}: {out.name}")
            rendered += 1

    print(f"DONE: rendered {rendered} PNG previews in {round(time.time() - t0, 2)}s")
    return 0


if __name__ in ("__main__", "render_previews"):
    rc = main()
    if rc != 0:
        raise SystemExit(rc)
