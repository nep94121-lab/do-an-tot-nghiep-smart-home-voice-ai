"""Export 3MF files (from watertight STLs) and Dimensioned Technical Drawings (PDF + PNG).

Run with system Python (requires trimesh, matplotlib, numpy):
    python "hardware/in 3 d/scripts/export_3mf_and_drawings.py"
    python "hardware/in 3 d/scripts/export_3mf_and_drawings.py" --parts P16_PCB_PLATE,P02_WALL_BACK_piece1of2
    python "hardware/in 3 d/scripts/export_3mf_and_drawings.py" --shard panels-std
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
import textwrap
import time
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle as MplCircle, FancyBboxPatch, Polygon as MplPolygon, Rectangle as MplRect
import numpy as np
import trimesh

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PRINT3D_ROOT = SCRIPT_DIR.parent
MICA_DIR = PRINT3D_ROOT.parent / "mica"

for p in (str(SCRIPT_DIR), str(MICA_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import mica_design as md
import print_domain as pd_mod

STL_DIR = PRINT3D_ROOT / "STL"
THREEMF_DIR = PRINT3D_ROOT / "3MF"
DRAW_DIR = PRINT3D_ROOT / "drawings"
META_DIR = PRINT3D_ROOT / "build_meta"


def convert_stl_to_3mf(part_id: str) -> dict[str, Any]:
    """Load binary STL via trimesh, validate manifold/watertight, and export print-ready 3MF."""
    stl_path = STL_DIR / f"{part_id}.stl"
    out_3mf = THREEMF_DIR / f"{part_id}.3mf"
    THREEMF_DIR.mkdir(parents=True, exist_ok=True)

    mesh = trimesh.load_mesh(str(stl_path), force="mesh")
    if not isinstance(mesh, trimesh.Trimesh):
        raise TypeError(f"{stl_path} did not load as Trimesh")

    # Export with explicit metadata (millimeters)
    mesh.metadata["name"] = part_id
    mesh.metadata["units"] = "millimeters"
    mesh.export(str(out_3mf), file_type="3mf")

    # Re-load 3MF to prove round-trip integrity
    loaded = trimesh.load(str(out_3mf))
    if isinstance(loaded, trimesh.Scene):
        geom = list(loaded.geometry.values())[0]
    else:
        geom = loaded

    ext = mesh.extents
    bmin = mesh.bounds[0]
    return {
        "part_id": part_id,
        "stl_watertight": bool(mesh.is_watertight),
        "stl_is_volume": bool(mesh.is_volume),
        "stl_winding_consistent": bool(mesh.is_winding_consistent),
        "stl_bbox_mm": [round(float(ext[0]), 3), round(float(ext[1]), 3), round(float(ext[2]), 3)],
        "stl_z_min": round(float(bmin[2]), 4),
        "stl_volume_mm3": round(float(abs(mesh.volume)), 3),
        "threemf_file": f"3MF/{out_3mf.name}",
        "threemf_bytes": int(out_3mf.stat().st_size),
        "threemf_watertight": bool(getattr(geom, "is_watertight", False)),
    }


def _draw_dim_arrow(ax, x1: float, y1: float, x2: float, y2: float, label: str, offset_txt: tuple[float, float] = (0, 0), fontsize: float = 8.5) -> None:
    ax.annotate(
        "",
        xy=(x2, y2),
        xytext=(x1, y1),
        arrowprops=dict(arrowstyle="<->", color="#1b365d", lw=1.1, shrinkA=0, shrinkB=0),
    )
    mx = (x1 + x2) / 2.0 + offset_txt[0]
    my = (y1 + y2) / 2.0 + offset_txt[1]
    rot = 90 if abs(x2 - x1) < 1e-3 and abs(y2 - y1) > 1.0 else 0
    ax.text(
        mx,
        my,
        label,
        ha="center",
        va="center",
        fontsize=fontsize,
        fontweight="bold",
        color="#1b365d",
        rotation=rot,
        bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="#1b365d", lw=0.6, alpha=0.95),
    )


def _draw_panel_piece_drawing(
    piece: pd_mod.PanelPieceSpec,
    ev: dict[str, Any],
    meta: dict[str, Any],
    mesh: trimesh.Trimesh,
    cfg: pd_mod.PrintConfig,
) -> tuple[pathlib.Path, pathlib.Path]:
    """Render clean engineering drawing (PDF + PNG) of one panel or split piece from real 3D mesh + SSOT."""
    DRAW_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = DRAW_DIR / f"{piece.part_id}.pdf"
    png_path = DRAW_DIR / f"{piece.part_id}.png"

    W, H, T = meta["print_bbox_mm"]
    fig = plt.figure(figsize=(11.69, 8.27), dpi=160)  # A4 Landscape
    fig.patch.set_facecolor("white")

    # Main 2D top view (left 68%) + Side thickness view & Info block (right 28%)
    ax = fig.add_axes([0.055, 0.14, 0.63, 0.72])
    ax_side = fig.add_axes([0.73, 0.56, 0.23, 0.26])
    ax_info = fig.add_axes([0.72, 0.08, 0.25, 0.44])
    ax_info.axis("off")

    # Project actual STL triangles facing +Z onto XY so split dovetails & engraved text appear accurately!
    verts = mesh.vertices
    faces = mesh.faces
    normals = mesh.face_normals
    top_mask = normals[:, 2] > 0.85
    top_faces = faces[top_mask]
    # Separate flat outer top surface (Z > T - 0.15) vs recessed engraved floor (Z < T - 0.15)
    face_z = verts[top_faces][:, :, 2].mean(axis=1)
    main_faces = top_faces[face_z > T - 0.15]
    eng_faces = top_faces[face_z <= T - 0.15]

    if len(main_faces) > 0:
        ax.tripcolor(
            verts[:, 0],
            verts[:, 1],
            main_faces,
            np.ones(len(main_faces)),
            cmap=matplotlib.colors.ListedColormap(["#dceef8"]),
            edgecolors="none",
            zorder=1,
        )
    if len(eng_faces) > 0:
        ax.tripcolor(
            verts[:, 0],
            verts[:, 1],
            eng_faces,
            np.ones(len(eng_faces)),
            cmap=matplotlib.colors.ListedColormap(["#0f2b46"]),
            edgecolors="none",
            zorder=3,
        )

    # Draw crisp feature boundary edges (outline, cutouts, holes, dovetails)
    edges = mesh.edges[mesh.face_adjacency_edges] if len(mesh.face_adjacency_edges) else np.empty((0, 2), dtype=int)
    # Use dihedral angles > 35 deg for sharp CAD silhouettes
    if len(mesh.face_adjacency_angles) > 0:
        sharp_idx = np.where(mesh.face_adjacency_angles > np.radians(35.0))[0]
        sharp_edges = mesh.face_adjacency_edges[sharp_idx]
        # Keep edges lying near top face Z >= T - 0.08 for clean top orthographic projection
        e_v0 = verts[sharp_edges[:, 0]]
        e_v1 = verts[sharp_edges[:, 1]]
        on_top = (e_v0[:, 2] > T - 0.08) & (e_v1[:, 2] > T - 0.08)
        top_edges = sharp_edges[on_top]
        if len(top_edges) > 0:
            segs = np.stack([verts[top_edges[:, 0], :2], verts[top_edges[:, 1], :2]], axis=1)
            from matplotlib.collections import LineCollection
            lc = LineCollection(segs, colors="#0b2540", linewidths=1.15, zorder=4)
            ax.add_collection(lc)

    # Annotate circular holes falling inside this piece
    lmin_u, lmin_v = meta["local_bbox_min"][0], meta["local_bbox_min"][1]
    u_lo, u_hi = piece.u_range
    v_lo, v_hi = piece.v_range
    piece_holes: list[dict[str, Any]] = []
    for c in ev["circles"]:
        if (u_lo - 0.5 <= c["cx"] <= u_hi + 0.5) and (v_lo - 0.5 <= c["cy"] <= v_hi + 0.5):
            px = c["cx"] - lmin_u
            py = c["cy"] - lmin_v
            piece_holes.append({"name": c["name"], "x": px, "y": py, "dia": c["dia"]})
            ax.plot([px - 2.2, px + 2.2], [py, py], color="#c0392b", lw=0.7, zorder=5)
            ax.plot([px, px], [py - 2.2, py + 2.2], color="#c0392b", lw=0.7, zorder=5)

    # Outer dimension arrows
    pad_x = max(14.0, W * 0.14)
    pad_y = max(14.0, H * 0.14)
    # Bottom width dimension
    ax.plot([0, 0], [0, -pad_y * 0.58], color="#557", lw=0.6, ls="--")
    ax.plot([W, W], [0, -pad_y * 0.58], color="#557", lw=0.6, ls="--")
    _draw_dim_arrow(ax, 0, -pad_y * 0.45, W, -pad_y * 0.45, f"L = {W:.1f} mm")
    # Left height dimension
    ax.plot([0, -pad_x * 0.58], [0, 0], color="#557", lw=0.6, ls="--")
    ax.plot([0, -pad_x * 0.58], [H, H], color="#557", lw=0.6, ls="--")
    _draw_dim_arrow(ax, -pad_x * 0.45, 0, -pad_x * 0.45, H, f"W = {H:.1f} mm")

    # Show bed safety reference note
    ax.set_xlim(-pad_x * 0.95, W + pad_x * 0.45)
    ax.set_ylim(-pad_y * 0.95, H + pad_y * 0.45)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linestyle=":", color="#ccd6e0", linewidth=0.6)
    ax.set_xlabel("Truc X ban in (mm)", fontsize=9)
    ax.set_ylabel("Truc Y ban in (mm)", fontsize=9)
    ax.set_title(
        f"Hinh chieu bang (Mat khac chu huong len Z = {T:.1f} mm — Nam phang Z = 0)",
        fontsize=10,
        fontweight="bold",
        color="#0f2b46",
        pad=8,
    )

    # Side profile view (thickness T & engraving recess 0.6 mm)
    ax_side.add_patch(MplRect((0, 0), W, T, facecolor="#dceef8", edgecolor="#0b2540", lw=1.2))
    ax_side.add_patch(MplRect((W * 0.35, T - cfg.engrave_depth), W * 0.30, cfg.engrave_depth, facecolor="#0f2b46", edgecolor="none", alpha=0.8))
    ax_side.set_xlim(-W * 0.18, W * 1.18)
    ax_side.set_ylim(-T * 1.2, T * 2.4)
    _draw_dim_arrow(ax_side, W * 1.07, 0, W * 1.07, T, f"T={T:.1f}mm", fontsize=8)
    ax_side.text(W * 0.5, T * 1.45, f"Khac chim {cfg.engrave_depth:.1f} mm (mat tren)", ha="center", fontsize=7.5, color="#0f2b46")
    ax_side.text(W * 0.5, -T * 0.75, "Mat phang tiep xuc ban in (Z=0)", ha="center", fontsize=7.5, color="#1f618d")
    ax_side.set_title("Mat cat chieu day (Truc Z)", fontsize=9, fontweight="bold", color="#0f2b46")
    ax_side.set_xticks([])
    ax_side.set_yticks([0, T])

    # Vietnamese technical title block & hole summary
    bed_ok = "DAT (<= 210x210 mm)" if meta["bed_fit"] else "VUOT BAN IN"
    split_note = (
        f"Manh {piece.piece_index}/{piece.piece_count} (Tam goc: {ev['width']:.1f} x {ev['height']:.1f} mm)\n"
        f"Khop duoi en: {len(piece.dovetails)} moi, khe ho {cfg.dovetail_clearance:.2f} mm"
        if piece.piece_count > 1
        else "Nguyen tam 1 manh (khong can chia)"
    )
    hole_groups: dict[str, int] = {}
    for h in piece_holes:
        key = f"Dia {h['dia']:.1f}mm"
        hole_groups[key] = hole_groups.get(key, 0) + 1
    hole_summary = ", ".join(f"{cnt}x {k}" for k, cnt in sorted(hole_groups.items())) if hole_groups else "Khong co lo tron"

    info_lines = [
        f"MA CHI TIET: {piece.part_id}",
        f"TEN: {piece.vi_name}",
        f"SO LUONG IN: {piece.qty} cai",
        f"KICH THUOC IN: {W:.2f} x {H:.2f} x {T:.2f} mm",
        f"THE TICH: {meta['volume_mm3'] / 1000.0:.2f} cm3",
        f"CHIA MANH: {split_note}",
        f"CHU KHAC TREN VAT: {meta['engrave_text']}",
        f"LO KHOAN ({len(piece_holes)}): {hole_summary}",
        f"BAN IN 220x220 (LE 5mm): {bed_ok}",
        "VAT LIEU KHUYEN NGHI: PLA / PETG",
        "LAYER: 0.20 mm | INFILL: 20% | SUPPORT: KHONG",
        "NGUON SSOT: hardware/mica/mica_design.py",
    ]
    ax_info.add_patch(FancyBboxPatch((0.0, 0.0), 1.0, 1.0, boxstyle="round,pad=0.02", facecolor="#f7fafc", edgecolor="#1b365d", lw=1.2))
    ax_info.text(0.04, 0.95, "THONG SO KY THUAT IN 3D", fontsize=9.5, fontweight="bold", color="#1b365d", va="top")
    ax_info.text(0.04, 0.87, "\n".join(info_lines), fontsize=7.6, color="#1a2530", va="top", linespacing=1.42)

    fig.suptitle(
        f"BAN VE CHI TIET IN 3D: {piece.part_id}  ({W:.1f} x {H:.1f} x {T:.1f} mm)",
        fontsize=13,
        fontweight="bold",
        color="#0b2540",
        y=0.96,
    )
    fig.text(
        0.055,
        0.03,
        "Smart Home Voice AI — Bo ho so in 3D (hardware/in 3 d/) | Don vi: mm | Dung sai lap ghep: 0.20 mm",
        fontsize=8,
        color="#4a607a",
    )

    fig.savefig(str(pdf_path), format="pdf")
    fig.savefig(str(png_path), format="png", dpi=160)
    plt.close(fig)
    return pdf_path, png_path


def _draw_support_drawing(
    sup: pd_mod.SupportSpec,
    meta: dict[str, Any],
    mesh: trimesh.Trimesh,
) -> tuple[pathlib.Path, pathlib.Path]:
    """Render 3-view orthographic dimensioned technical drawing (PDF + PNG) for a printable support."""
    DRAW_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = DRAW_DIR / f"{sup.part_id}.pdf"
    png_path = DRAW_DIR / f"{sup.part_id}.png"

    X, Y, Z = meta["print_bbox_mm"]
    fig = plt.figure(figsize=(11.69, 8.27), dpi=160)
    fig.patch.set_facecolor("white")

    ax_top = fig.add_axes([0.06, 0.48, 0.36, 0.38])
    ax_front = fig.add_axes([0.06, 0.10, 0.36, 0.28])
    ax_right = fig.add_axes([0.46, 0.48, 0.22, 0.38])
    ax_info = fig.add_axes([0.48, 0.10, 0.47, 0.33])
    ax_info.axis("off")

    verts = mesh.vertices
    faces = mesh.faces
    sharp_edges = (
        mesh.face_adjacency_edges[np.where(mesh.face_adjacency_angles > np.radians(28.0))[0]]
        if len(mesh.face_adjacency_angles) > 0
        else np.empty((0, 2), dtype=int)
    )
    from matplotlib.collections import LineCollection

    def _plot_proj(ax, xi: int, yi: int, dx: float, dy: float, title: str, xl: str, yl: str, lx: str, ly: str) -> None:
        # Shaded silhouette from faces visible from +normal of 3rd axis
        zi = 3 - xi - yi
        vis = mesh.face_normals[:, zi] > 0.15
        if np.any(vis):
            ax.tripcolor(
                verts[:, xi],
                verts[:, yi],
                faces[vis],
                np.ones(int(np.sum(vis))),
                cmap=matplotlib.colors.ListedColormap(["#fdebd0"]),
                edgecolors="none",
                zorder=1,
            )
        if len(sharp_edges) > 0:
            segs = np.stack([verts[sharp_edges[:, 0]][:, [xi, yi]], verts[sharp_edges[:, 1]][:, [xi, yi]]], axis=1)
            ax.add_collection(LineCollection(segs, colors="#5d3a1a", linewidths=1.0, zorder=3))
        px = max(3.5, dx * 0.22)
        py = max(3.5, dy * 0.22)
        _draw_dim_arrow(ax, 0, -py * 0.55, dx, -py * 0.55, lx, fontsize=8)
        _draw_dim_arrow(ax, -px * 0.55, 0, -px * 0.55, dy, ly, fontsize=8)
        ax.set_xlim(-px * 1.05, dx + px * 0.45)
        ax.set_ylim(-py * 1.05, dy + py * 0.45)
        ax.set_aspect("equal", adjustable="box")
        ax.grid(True, linestyle=":", color="#ddd", linewidth=0.6)
        ax.set_xlabel(xl, fontsize=8)
        ax.set_ylabel(yl, fontsize=8)
        ax.set_title(title, fontsize=9.5, fontweight="bold", color="#5d3a1a")

    _plot_proj(ax_top, 0, 1, X, Y, "Hinh chieu bang (XY — Mat in)", "X (mm)", "Y (mm)", f"X={X:.1f}mm", f"Y={Y:.1f}mm")
    _plot_proj(ax_front, 0, 2, X, Z, "Hinh chieu dung (XZ)", "X (mm)", "Z (mm)", f"X={X:.1f}mm", f"H={Z:.1f}mm")
    _plot_proj(ax_right, 1, 2, Y, Z, "Hinh chieu canh (YZ)", "Y (mm)", "Z (mm)", f"Y={Y:.1f}mm", f"H={Z:.1f}mm")

    raw_lines = [
        f"MA PHU KIEN (SUPOT): {sup.part_id}",
        f"TEN TIENG VIET: {sup.vi_name}",
        f"PHAN LOAI: {sup.category.upper()} | SO LUONG CAN IN: {sup.qty} cai",
        f"KICH THUOC BAO (X x Y x Z): {X:.2f} x {Y:.2f} x {Z:.2f} mm",
        f"THE TICH: {meta['volume_mm3'] / 1000.0:.2f} cm3",
        f"VI TRI LAP GHEP: {sup.mating_source}",
        f"CHU KHAC: {meta['engrave_text']}",
        f"GHI CHU: {sup.notes}",
        "HUONG IN: Dat mat day Z=0 nam phang tren ban in | SUPPORT: KHONG CAN",
        "THONG SO IN: PLA/PETG, Layer 0.20mm, 3 thanh, Infill 25-30%",
    ]
    info_lines: list[str] = []
    for ln in raw_lines:
        info_lines.extend(textwrap.wrap(ln, width=64) or [""])
    ax_info.add_patch(FancyBboxPatch((0.0, 0.0), 1.0, 1.0, boxstyle="round,pad=0.02", facecolor="#fffaf3", edgecolor="#935116", lw=1.2))
    ax_info.text(0.03, 0.94, "THONG SO PHU KIEN GIA CO & GA LAP (IN 3D)", fontsize=9.2, fontweight="bold", color="#935116", va="top")
    ax_info.text(0.03, 0.84, "\n".join(info_lines), fontsize=7.6, color="#2c1d10", va="top", linespacing=1.32)

    fig.suptitle(
        f"BAN VE PHU KIEN IN 3D (SUPOT): {sup.part_id}  ({X:.1f} x {Y:.1f} x {Z:.1f} mm)",
        fontsize=12.5,
        fontweight="bold",
        color="#5d3a1a",
        y=0.96,
    )
    fig.text(0.06, 0.025, "Smart Home Voice AI — Bo ho so in 3D (hardware/in 3 d/) | Don vi: mm", fontsize=8, color="#665")

    fig.savefig(str(pdf_path), format="pdf")
    fig.savefig(str(png_path), format="png", dpi=160)
    plt.close(fig)
    return pdf_path, png_path


def main() -> int:
    t0 = time.time()
    ap = argparse.ArgumentParser(description="Export 3MF files and dimensioned PDF/PNG drawings")
    ap.add_argument("--parts", type=str, default="", help="Comma-separated part_ids")
    ap.add_argument("--shard", type=str, default="", help="Named shard from print_domain.get_swarm_shards()")
    args = ap.parse_args()

    cfg = pd_mod.PrintConfig()
    pieces, _ = pd_mod.build_panel_piece_specs(cfg)
    supports = pd_mod.build_support_specs(cfg)
    panels_raw, _ = md.build_design()
    ev_map = {ps.panel_id: md.evaluate_panel_2d(ps, T_mm=cfg.T_mm, tab_clr=cfg.tab_clr) for ps in panels_raw}

    target_ids: set[str] | None = None
    if args.shard:
        shards = pd_mod.get_swarm_shards(cfg)
        target_ids = set(shards[args.shard])
    elif args.parts:
        target_ids = {s.strip() for s in args.parts.split(",") if s.strip()}

    count = 0
    failures: list[str] = []

    for piece in pieces:
        if target_ids is not None and piece.part_id not in target_ids:
            continue
        meta_path = META_DIR / f"{piece.part_id}.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        res_3mf = convert_stl_to_3mf(piece.part_id)
        mesh = trimesh.load_mesh(str(STL_DIR / f"{piece.part_id}.stl"), force="mesh")
        pdf_p, png_p = _draw_panel_piece_drawing(piece, ev_map[piece.source_panel_id], meta, mesh, cfg)
        meta.update(res_3mf)
        meta["drawing_pdf"] = f"drawings/{pdf_p.name}"
        meta["drawing_png"] = f"drawings/{png_p.name}"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        ok = res_3mf["stl_watertight"] and res_3mf["threemf_watertight"]
        print(f"[{'OK' if ok else 'FAIL'}] 3MF+DRAW {piece.part_id}: watertight={res_3mf['stl_watertight']} 3mf={res_3mf['threemf_bytes']}B")
        if not ok:
            failures.append(piece.part_id)
        count += 1

    for sup in supports:
        if target_ids is not None and sup.part_id not in target_ids:
            continue
        meta_path = META_DIR / f"{sup.part_id}.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        res_3mf = convert_stl_to_3mf(sup.part_id)
        mesh = trimesh.load_mesh(str(STL_DIR / f"{sup.part_id}.stl"), force="mesh")
        pdf_p, png_p = _draw_support_drawing(sup, meta, mesh)
        meta.update(res_3mf)
        meta["drawing_pdf"] = f"drawings/{pdf_p.name}"
        meta["drawing_png"] = f"drawings/{png_p.name}"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        ok = res_3mf["stl_watertight"] and res_3mf["threemf_watertight"]
        print(f"[{'OK' if ok else 'FAIL'}] 3MF+DRAW {sup.part_id}: watertight={res_3mf['stl_watertight']} 3mf={res_3mf['threemf_bytes']}B")
        if not ok:
            failures.append(sup.part_id)
        count += 1

    print(f"DONE: exported 3MF + drawings for {count} parts in {round(time.time() - t0, 2)}s (failures={len(failures)})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
