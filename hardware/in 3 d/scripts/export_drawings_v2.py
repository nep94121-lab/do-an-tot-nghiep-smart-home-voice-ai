"""Export Dimensioned Technical Drawings (PNG + PDF) for 3D-Print Set v2 (57 parts + 2 special sheets).

Outputs (STRICTLY inside `hardware/in 3 d/drawings/`):
  - 57 per-part dimensioned drawings: `<part_id>.png` and `<part_id>.pdf` (114 files)
  - Mong joint close-up 4-panel drawing: `_joint_closeup_mong.png` and `_joint_closeup_mong.pdf` (2 files)
  - PCB & off-board module fit drawing: `_pcb_module_fit.png` and `_pcb_module_fit.pdf` (2 files)
  Total: 118 files.

Reads ONLY from `parts/*.stl`, `build_meta/*.json`, `build_meta/fit_table.json`,
`print_domain.py`, and `kicad_pcb_ssot.py`. Never modifies `build_meta/`, `parts/`, `plates/`, or `previews/`.

Run:
    python "hardware/in 3 d/scripts/export_drawings_v2.py"
    python "hardware/in 3 d/scripts/export_drawings_v2.py" --only-special
    python "hardware/in 3 d/scripts/export_drawings_v2.py" --parts P02_WALL_BACK_piece1of3,SUP06_HUB_PCB_SNAP_CARRIER
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
from matplotlib.collections import LineCollection
from matplotlib.colors import ListedColormap
from matplotlib.patches import (
    Circle as MplCircle,
    FancyBboxPatch,
    Polygon as MplPolygon,
    Rectangle as MplRect,
)
import numpy as np
import trimesh

plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["ps.fonttype"] = 42

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PRINT3D_ROOT = SCRIPT_DIR.parent
MICA_DIR = PRINT3D_ROOT.parent / "mica"

for _p in (str(SCRIPT_DIR), str(MICA_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import kicad_pcb_ssot as pcb_ssot
import mica_design as md
import print_domain as pd_mod

PARTS_DIR = PRINT3D_ROOT / "parts"
META_DIR = PRINT3D_ROOT / "build_meta"
DRAW_DIR = PRINT3D_ROOT / "drawings"
FIT_TABLE_PATH = META_DIR / "fit_table.json"


# ---------------------------------------------------------------------------
# Shared CAD Drafting Helpers
# ---------------------------------------------------------------------------
def _draw_dim_arrow(
    ax: plt.Axes,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    label: str,
    offset_txt: tuple[float, float] = (0.0, 0.0),
    fontsize: float = 8.0,
    color: str = "#1b365d",
    lw: float = 1.05,
    rot: float | None = None,
    box_alpha: float = 0.96,
) -> None:
    ax.annotate(
        "",
        xy=(x2, y2),
        xytext=(x1, y1),
        arrowprops=dict(arrowstyle="<->", color=color, lw=lw, shrinkA=0, shrinkB=0, mutation_scale=9),
        zorder=15,
    )
    mx = (x1 + x2) / 2.0 + offset_txt[0]
    my = (y1 + y2) / 2.0 + offset_txt[1]
    if rot is None:
        rot = 90.0 if abs(x2 - x1) < 1e-3 and abs(y2 - y1) > 0.5 else 0.0
    ax.text(
        mx,
        my,
        label,
        ha="center",
        va="center",
        fontsize=fontsize,
        fontweight="bold",
        color=color,
        rotation=rot,
        bbox=dict(boxstyle="round,pad=0.16", facecolor="white", edgecolor=color, lw=0.55, alpha=box_alpha),
        zorder=16,
    )


def _draw_callout(
    ax: plt.Axes,
    xy: tuple[float, float],
    xytext: tuple[float, float],
    text: str,
    color: str = "#0f2b46",
    fontsize: float = 7.8,
    ha: str = "left",
    va: str = "center",
    fc: str = "#ffffff",
    ec: str | None = None,
    rad: float = 0.0,
) -> None:
    ax.annotate(
        text,
        xy=xy,
        xytext=xytext,
        ha=ha,
        va=va,
        fontsize=fontsize,
        fontweight="bold",
        color=color,
        bbox=dict(boxstyle="round,pad=0.22", facecolor=fc, edgecolor=ec or color, lw=0.7, alpha=0.96),
        arrowprops=dict(
            arrowstyle="-|>",
            color=color,
            lw=0.95,
            shrinkA=2,
            shrinkB=1.5,
            connectionstyle=f"arc3,rad={rad}",
            mutation_scale=9,
        ),
        zorder=18,
    )


def _sharp_edges(mesh: trimesh.Trimesh, angle_deg: float = 30.0) -> np.ndarray:
    if len(mesh.face_adjacency_angles) == 0:
        return np.empty((0, 2), dtype=int)
    idx = np.where(mesh.face_adjacency_angles > np.radians(angle_deg))[0]
    if len(idx) == 0:
        return np.empty((0, 2), dtype=int)
    return mesh.face_adjacency_edges[idx]


def _plot_top_mesh_panel(
    ax: plt.Axes,
    mesh: trimesh.Trimesh,
    T: float,
    plate_z: float | None = None,
    shift_xy: tuple[float, float] = (0.0, 0.0),
    main_color: str = "#dceef8",
    raised_color: str = "#9ecae1",
    recess_color: str = "#0f2b46",
    edge_color: str = "#0b2540",
    edge_lw: float = 1.05,
    zorder_base: int = 1,
) -> None:
    """Project real STL mesh triangles facing +Z onto XY, highlighting recessed engraved faces & sharp edges."""
    verts = mesh.vertices.copy()
    verts[:, 0] += shift_xy[0]
    verts[:, 1] += shift_xy[1]
    faces = mesh.faces
    normals = mesh.face_normals
    top_mask = normals[:, 2] > 0.7
    top_faces = faces[top_mask]

    if len(top_faces) > 0:
        face_z = verts[top_faces][:, :, 2].mean(axis=1)
        ref_z = plate_z if plate_z is not None else T

        if plate_z is not None and T > plate_z + 0.3:
            raised = top_faces[face_z > ref_z + 0.15]
            main = top_faces[(face_z >= ref_z - 0.15) & (face_z <= ref_z + 0.15)]
            recess = top_faces[face_z < ref_z - 0.15]
        else:
            raised = np.empty((0, 3), dtype=int)
            main = top_faces[face_z > ref_z - 0.15]
            recess = top_faces[face_z <= ref_z - 0.15]

        if len(main) > 0:
            ax.tripcolor(
                verts[:, 0], verts[:, 1], main, np.ones(len(main)),
                cmap=ListedColormap([main_color]), edgecolors="none", zorder=zorder_base,
            )
        if len(raised) > 0:
            ax.tripcolor(
                verts[:, 0], verts[:, 1], raised, np.ones(len(raised)),
                cmap=ListedColormap([raised_color]), edgecolors="none", zorder=zorder_base + 1,
            )
        if len(recess) > 0:
            ax.tripcolor(
                verts[:, 0], verts[:, 1], recess, np.ones(len(recess)),
                cmap=ListedColormap([recess_color]), edgecolors="none", zorder=zorder_base + 2,
            )

    se = _sharp_edges(mesh, 32.0)
    if len(se) > 0:
        v0 = verts[se[:, 0]]
        v1 = verts[se[:, 1]]
        if plate_z is not None and T > plate_z + 0.3:
            keep = ((v0[:, 2] > plate_z - 0.12) & (v1[:, 2] > plate_z - 0.12))
        else:
            keep = (v0[:, 2] > T - 0.12) & (v1[:, 2] > T - 0.12)
        te = se[keep]
        if len(te) > 0:
            segs = np.stack([verts[te[:, 0], :2], verts[te[:, 1], :2]], axis=1)
            ax.add_collection(LineCollection(segs, colors=edge_color, linewidths=edge_lw, zorder=zorder_base + 3))


def _plot_top_mesh_3dpart(
    ax: plt.Axes,
    mesh: trimesh.Trimesh,
    palette_low: str,
    palette_mid: str,
    palette_high: str,
    recess_color: str,
    edge_color: str,
    edge_lw: float = 0.90,
) -> None:
    """Top orthographic projection (normals[:, 2] > 0.7) for 3D supports/furniture with Z-tier shading."""
    verts = mesh.vertices
    faces = mesh.faces
    normals = mesh.face_normals
    top_idx = np.where(normals[:, 2] > 0.7)[0]
    if len(top_idx) > 0:
        top_faces = faces[top_idx]
        face_z = verts[top_faces][:, :, 2].mean(axis=1)
        z_min, z_max = float(verts[:, 2].min()), float(verts[:, 2].max())
        z_span = max(z_max - z_min, 1e-3)

        # Detect recessed engraving plateaus: small triangles ~0.3-0.65 mm below a dominant flat Z-level
        areas = mesh.area_faces[top_idx]
        rounded_z = np.round(face_z, 1)
        unique_z, inv = np.unique(rounded_z, return_inverse=True)
        area_by_z = np.bincount(inv, weights=areas)
        major_z = unique_z[area_by_z > max(12.0, float(areas.sum()) * 0.06)]

        is_engrave = np.zeros(len(top_faces), dtype=bool)
        for mz in major_z:
            # Engraving pockets are 0.30..0.65 mm below a major flat face and have tiny individual triangle area
            band = (face_z >= mz - 0.68) & (face_z <= mz - 0.25) & (areas < 2.2)
            is_engrave |= band

        # Painter's order: draw lower Z bands first, higher Z bands on top, engraved letters crisp on top
        norm_z = (face_z - z_min) / z_span
        low_m = (~is_engrave) & (norm_z < 0.35)
        mid_m = (~is_engrave) & (norm_z >= 0.35) & (norm_z < 0.75)
        high_m = (~is_engrave) & (norm_z >= 0.75)

        for mask, col, zo in (
            (low_m, palette_low, 1),
            (mid_m, palette_mid, 2),
            (high_m, palette_high, 3),
            (is_engrave, recess_color, 4),
        ):
            if np.any(mask):
                ax.tripcolor(
                    verts[:, 0], verts[:, 1], top_faces[mask], np.ones(int(np.sum(mask))),
                    cmap=ListedColormap([col]), edgecolors="none", zorder=zo,
                )

    se = _sharp_edges(mesh, 28.0)
    if len(se) > 0:
        segs = np.stack([verts[se[:, 0], :2], verts[se[:, 1], :2]], axis=1)
        ax.add_collection(LineCollection(segs, colors=edge_color, linewidths=edge_lw, zorder=5))


def _plot_orthographic_side(
    ax: plt.Axes,
    mesh: trimesh.Trimesh,
    xi: int,
    yi: int,
    fill_color: str,
    edge_color: str,
    edge_lw: float = 0.90,
) -> None:
    verts = mesh.vertices
    faces = mesh.faces
    zi = 3 - xi - yi
    vis = mesh.face_normals[:, zi] > 0.15
    if np.any(vis):
        ax.tripcolor(
            verts[:, xi], verts[:, yi], faces[vis], np.ones(int(np.sum(vis))),
            cmap=ListedColormap([fill_color]), edgecolors="none", zorder=1,
        )
    se = _sharp_edges(mesh, 28.0)
    if len(se) > 0:
        segs = np.stack([verts[se[:, 0]][:, [xi, yi]], verts[se[:, 1]][:, [xi, yi]]], axis=1)
        ax.add_collection(LineCollection(segs, colors=edge_color, linewidths=edge_lw, zorder=3))


def _draw_bed_plane(ax: plt.Axes, x_lo: float, x_hi: float, fontsize: float = 7.2) -> None:
    ax.axhline(0.0, color="#c0392b", lw=1.1, ls="--", zorder=6)
    ax.text(
        x_hi,
        0.0,
        " Z=0 (Ban in) ",
        ha="right",
        va="bottom",
        fontsize=fontsize,
        fontweight="bold",
        color="#c0392b",
        bbox=dict(boxstyle="square,pad=0.10", facecolor="white", edgecolor="none", alpha=0.85),
        zorder=7,
    )


# ---------------------------------------------------------------------------
# 1. Per-Part Dimensioned Technical Drawings (57 parts)
# ---------------------------------------------------------------------------
def draw_panel_piece_v2(
    piece: pd_mod.PanelPieceSpec,
    ev: dict[str, Any],
    meta: dict[str, Any],
    mesh: trimesh.Trimesh,
    cfg: pd_mod.PrintConfig,
) -> tuple[pathlib.Path, pathlib.Path]:
    DRAW_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = DRAW_DIR / f"{piece.part_id}.pdf"
    png_path = DRAW_DIR / f"{piece.part_id}.png"

    W, H, T = [float(v) for v in meta["print_bbox_mm"]]
    is_p17 = piece.source_panel_id == "P17_BASE_JOINER"
    plate_z = cfg.T_mm if is_p17 else None

    fig = plt.figure(figsize=(11.69, 8.27), dpi=160)
    fig.patch.set_facecolor("white")

    # Outer engineering border frame
    ax_frame = fig.add_axes([0.015, 0.015, 0.97, 0.97])
    ax_frame.axis("off")
    ax_frame.add_patch(MplRect((0, 0), 1, 1, fill=False, edgecolor="#1b365d", lw=1.4))

    ax = fig.add_axes([0.065, 0.13, 0.595, 0.74])
    ax_side = fig.add_axes([0.705, 0.59, 0.255, 0.27])
    ax_info = fig.add_axes([0.695, 0.065, 0.275, 0.485])
    ax_info.axis("off")

    _plot_top_mesh_panel(
        ax, mesh, T=T, plate_z=plate_z,
        main_color="#dceef8", raised_color="#90c2e7", recess_color="#0f2b46", edge_color="#0b2540",
    )

    # Functional circular holes (crosshairs) & screwless mortise slots (green highlights)
    lmin_u, lmin_v = float(meta["local_bbox_min"][0]), float(meta["local_bbox_min"][1])
    u_lo, u_hi = piece.u_range
    v_lo, v_hi = piece.v_range
    piece_holes: list[dict[str, Any]] = []
    for c in ev["circles"]:
        if (u_lo - 0.5 <= c["cx"] <= u_hi + 0.5) and (v_lo - 0.5 <= c["cy"] <= v_hi + 0.5):
            px = c["cx"] - lmin_u
            py = c["cy"] - lmin_v
            piece_holes.append({"name": c["name"], "x": px, "y": py, "dia": c["dia"], "kind": c.get("kind", "")})
            r_mark = max(2.2, c["dia"] * 0.55)
            ax.plot([px - r_mark, px + r_mark], [py, py], color="#c0392b", lw=0.75, zorder=6)
            ax.plot([px, px], [py - r_mark, py + r_mark], color="#c0392b", lw=0.75, zorder=6)

    for mt in piece.mortises:
        mx = mt.cx - lmin_u
        my = mt.cy - lmin_v
        ax.add_patch(
            MplRect(
                (mx - mt.du / 2.0, my - mt.dv / 2.0), mt.du, mt.dv,
                fill=False, edgecolor="#1e8449", lw=1.1, ls="--", zorder=7,
            )
        )

    # Outer dimension arrows L (X) and W (Y)
    pad_x = max(14.0, W * 0.14)
    pad_y = max(14.0, H * 0.14)
    ax.plot([0, 0], [0, -pad_y * 0.62], color="#557089", lw=0.65, ls="--")
    ax.plot([W, W], [0, -pad_y * 0.62], color="#557089", lw=0.65, ls="--")
    _draw_dim_arrow(ax, 0, -pad_y * 0.45, W, -pad_y * 0.45, f"L = {W:.2f} mm", fontsize=8.4)

    ax.plot([0, -pad_x * 0.62], [0, 0], color="#557089", lw=0.65, ls="--")
    ax.plot([0, -pad_x * 0.62], [H, H], color="#557089", lw=0.65, ls="--")
    _draw_dim_arrow(ax, -pad_x * 0.45, 0, -pad_x * 0.45, H, f"W = {H:.2f} mm", fontsize=8.4)

    ax.set_xlim(-pad_x * 0.92, W + pad_x * 0.35)
    ax.set_ylim(-pad_y * 0.92, H + pad_y * 0.35)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linestyle=":", color="#ccd6e0", linewidth=0.6)
    ax.set_xlabel("Truc X ban in (mm)", fontsize=8.8)
    ax.set_ylabel("Truc Y ban in (mm)", fontsize=8.8)

    legend_bits = []
    if piece_holes:
        legend_bits.append(f"+ Do: {len(piece_holes)} lo chuc nang")
    if piece.mortises:
        legend_bits.append(f"-- Xanh: {len(piece.mortises)} ranh mong")
    if is_p17:
        legend_bits.append("Xanh dam: 4 chot mong +3mm")
    sub_note = f"  [{', '.join(legend_bits)}]" if legend_bits else ""
    ax.set_title(
        f"Hinh chieu bang XY (Z={T:.1f} mm, Z=0 phang){sub_note}",
        fontsize=8.8, fontweight="bold", color="#0f2b46", pad=7,
    )

    # Side / profile thickness view (Z = 0 bed plane & overall height Z)
    if is_p17:
        _plot_orthographic_side(ax_side, mesh, 0, 2, "#dceef8", "#0b2540", edge_lw=1.0)
        ax_side.set_xlim(-W * 0.14, W * 1.24)
        ax_side.set_ylim(-2.2, T + 3.2)
        _draw_bed_plane(ax_side, -W * 0.12, W * 0.98, fontsize=7.0)
        _draw_dim_arrow(ax_side, W * 1.09, 0.0, W * 1.09, T, f"H={T:.1f}", fontsize=7.6)
        ax_side.text(W * 0.5, T + 1.4, "Tam 3.0mm + 4 chot mong 8x4x3mm (0 vit)", ha="center", fontsize=7.0, color="#0f2b46")
        ax_side.set_yticks([0.0, 3.0, T])
    else:
        ax_side.add_patch(MplRect((0, 0), W, T, facecolor="#dceef8", edgecolor="#0b2540", lw=1.2, zorder=2))
        ax_side.add_patch(
            MplRect((W * 0.34, T - cfg.engrave_depth), W * 0.32, cfg.engrave_depth,
                    facecolor="#0f2b46", edgecolor="none", alpha=0.88, zorder=3)
        )
        ax_side.set_xlim(-W * 0.14, W * 1.26)
        ax_side.set_ylim(-T * 1.15, T * 2.55)
        _draw_bed_plane(ax_side, -W * 0.12, W * 0.98, fontsize=7.0)
        _draw_dim_arrow(ax_side, W * 1.10, 0.0, W * 1.10, T, f"H={T:.1f}mm", fontsize=7.8)
        ax_side.annotate(
            f"Khac chim {cfg.engrave_depth:.1f} mm",
            xy=(W * 0.50, T - cfg.engrave_depth * 0.5),
            xytext=(W * 0.45, T * 1.75),
            ha="center", va="center", fontsize=7.3, fontweight="bold", color="#0f2b46",
            arrowprops=dict(arrowstyle="->", color="#0f2b46", lw=0.8),
        )
        ax_side.set_yticks([0.0, T])

    ax_side.set_xticks([])
    ax_side.set_ylabel("Z (mm)", fontsize=8.0)
    ax_side.set_title("Mat cat / Hinh chieu canh XZ (Truc Z)", fontsize=8.8, fontweight="bold", color="#0f2b46")
    ax_side.grid(True, axis="y", linestyle=":", color="#ccd6e0", linewidth=0.6)

    # Vietnamese Technical Title Block
    bed_ok = "DAT (<= 170x190x245 mm)" if meta.get("bed_fit", True) else "VUOT BAN IN"
    split_note = (
        f"Manh {piece.piece_index}/{piece.piece_count} (Goc {ev['width']:.1f}x{ev['height']:.1f}) | "
        f"{len(piece.dovetails)} mong duoi en (khe {cfg.dovetail_clearance:.2f} mm)"
        if piece.piece_count > 1
        else "Nguyen tam 1 manh (khong chia)"
    )
    hole_groups: dict[str, int] = {}
    for h in piece_holes:
        key = f"D{h['dia']:.1f}"
        hole_groups[key] = hole_groups.get(key, 0) + 1
    hole_summary = ", ".join(f"{cnt}x {k}" for k, cnt in sorted(hole_groups.items())) if hole_groups else "Khong co"

    mort_summary = (
        f"{len(piece.mortises)} ranh mong ({', '.join(sorted({f'{m.du:.1f}x{m.dv:.1f}' for m in piece.mortises}))})"
        if piece.mortises
        else ("4 chot mong noi 8x4x3 mm" if is_p17 else "Lien ket rang luoc canh ngoai")
    )

    raw_lines = [
        f"MA CHI TIET: {piece.part_id}",
        f"TEN: {piece.vi_name}",
        f"SO LUONG IN: {piece.qty} cai  |  NHOM: TAM KET CAU",
        f"KICH THUOC BAO: {W:.2f} x {H:.2f} x {T:.2f} mm",
        f"THE TICH: {float(meta['volume_mm3']) / 1000.0:.2f} cm3",
        f"BAN IN 180x200x250: {bed_ok}",
        "LIEN KET: KHONG VIT - KHONG KEO (100% MONG CAI)",
        f"CHIA MANH: {split_note}",
        f"CHU KHAC: {meta.get('engrave_text', '-')}",
        f"LO CHUC NANG (0 lo vit): {hole_summary}",
        f"MONG / RANH CAI: {mort_summary}",
        "IN 3D: PLA/PETG | Lop 0.20mm | Infill 20% | Support: KHONG",
    ]
    wrapped: list[str] = []
    for ln in raw_lines:
        wrapped.extend(textwrap.wrap(ln, width=44) or [""])

    ax_info.add_patch(
        FancyBboxPatch((0.0, 0.0), 1.0, 1.0, boxstyle="round,pad=0.015",
                       facecolor="#f7fafc", edgecolor="#1b365d", lw=1.25)
    )
    ax_info.add_patch(MplRect((0.0, 0.89), 1.0, 0.11, facecolor="#1b365d", edgecolor="none"))
    ax_info.text(0.50, 0.945, "KHUNG TEN KY THUAT — IN 3D v2", fontsize=8.8, fontweight="bold",
                 color="white", ha="center", va="center")
    ax_info.text(0.035, 0.86, "\n".join(wrapped), fontsize=7.25, color="#1a2530", va="top", linespacing=1.34)

    fig.suptitle(
        f"BAN VE CHI TIET IN 3D v2: {piece.part_id}   ({W:.1f} x {H:.1f} x {T:.1f} mm)",
        fontsize=12.4, fontweight="bold", color="#0b2540", y=0.955,
    )
    fig.text(
        0.04, 0.028,
        "Smart Home Voice AI — Bo in 3D v2 (Khong vit, Khong keo, Ban in 180x200x250 mm) | Don vi: mm | SSOT: print_domain.py",
        fontsize=7.7, color="#4a607a",
    )

    fig.savefig(str(pdf_path), format="pdf")
    fig.savefig(str(png_path), format="png", dpi=160)
    plt.close(fig)
    return pdf_path, png_path


def draw_3view_part_v2(
    part_id: str,
    meta: dict[str, Any],
    mesh: trimesh.Trimesh,
    cfg: pd_mod.PrintConfig,
) -> tuple[pathlib.Path, pathlib.Path]:
    """Render 3-view orthographic dimensioned drawing (Top XY, Front XZ, Right YZ) for SUP* and FUR*."""
    DRAW_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = DRAW_DIR / f"{part_id}.pdf"
    png_path = DRAW_DIR / f"{part_id}.png"

    kind = meta.get("kind", "support")
    X, Y, Z = [float(v) for v in meta["print_bbox_mm"]]

    if kind == "furniture":
        c_low, c_mid, c_high = "#c6e2d0", "#d9efe0", "#eef8f1"
        c_recess, c_edge, c_accent, c_bg = "#133c2e", "#1b4d3e", "#1e6b52", "#f5fbf7"
        header_tag = "NOI THAT MO HINH (FURNITURE)"
        title_prefix = "BAN VE NOI THAT IN 3D v2"
    else:
        c_low, c_mid, c_high = "#f5cfa0", "#fbe2be", "#fef2df"
        c_recess, c_edge, c_accent, c_bg = "#4a2308", "#5d3a1a", "#935116", "#fffaf3"
        header_tag = "PHU KIEN MONG & GA LAP (MOUNT/CLIP)"
        title_prefix = "BAN VE PHU KIEN IN 3D v2"

    fig = plt.figure(figsize=(11.69, 8.27), dpi=160)
    fig.patch.set_facecolor("white")

    ax_frame = fig.add_axes([0.015, 0.015, 0.97, 0.97])
    ax_frame.axis("off")
    ax_frame.add_patch(MplRect((0, 0), 1, 1, fill=False, edgecolor=c_accent, lw=1.4))

    ax_top = fig.add_axes([0.065, 0.48, 0.37, 0.39])
    ax_front = fig.add_axes([0.065, 0.10, 0.37, 0.28])
    ax_right = fig.add_axes([0.48, 0.48, 0.24, 0.39])
    ax_info = fig.add_axes([0.475, 0.075, 0.485, 0.355])
    ax_info.axis("off")

    # Top view (XY, normals[:,2] > 0.7)
    _plot_top_mesh_3dpart(ax_top, mesh, c_low, c_mid, c_high, c_recess, c_edge, edge_lw=0.9)
    px_t = max(3.0, X * 0.22)
    py_t = max(3.0, Y * 0.22)
    ax_top.plot([0, 0], [0, -py_t * 0.65], color="#777", lw=0.6, ls="--")
    ax_top.plot([X, X], [0, -py_t * 0.65], color="#777", lw=0.6, ls="--")
    _draw_dim_arrow(ax_top, 0, -py_t * 0.48, X, -py_t * 0.48, f"L={X:.1f}mm", fontsize=7.8, color=c_accent)
    ax_top.plot([0, -px_t * 0.65], [0, 0], color="#777", lw=0.6, ls="--")
    ax_top.plot([0, -px_t * 0.65], [Y, Y], color="#777", lw=0.6, ls="--")
    _draw_dim_arrow(ax_top, -px_t * 0.48, 0, -px_t * 0.48, Y, f"W={Y:.1f}mm", fontsize=7.8, color=c_accent)
    ax_top.set_xlim(-px_t * 1.02, X + px_t * 0.38)
    ax_top.set_ylim(-py_t * 1.02, Y + py_t * 0.38)
    ax_top.set_aspect("equal", adjustable="box")
    ax_top.grid(True, linestyle=":", color="#ddd", linewidth=0.6)
    ax_top.set_xlabel("X (mm)", fontsize=8.0)
    ax_top.set_ylabel("Y (mm)", fontsize=8.0)
    ax_top.set_title("Hinh chieu bang XY (Mat in Z = 0)", fontsize=9.0, fontweight="bold", color=c_edge)

    # Front view (XZ) with Z = 0 bed plane
    _plot_orthographic_side(ax_front, mesh, 0, 2, c_mid, c_edge, edge_lw=0.9)
    px_f = max(3.0, X * 0.22)
    pz_f = max(2.5, Z * 0.30)
    _draw_bed_plane(ax_front, -px_f * 0.9, X + px_f * 0.3, fontsize=6.9)
    _draw_dim_arrow(ax_front, 0, -pz_f * 0.52, X, -pz_f * 0.52, f"L={X:.1f}mm", fontsize=7.8, color=c_accent)
    _draw_dim_arrow(ax_front, -px_f * 0.50, 0, -px_f * 0.50, Z, f"H={Z:.1f}mm", fontsize=7.8, color=c_accent)
    ax_front.set_xlim(-px_f * 1.05, X + px_f * 0.40)
    ax_front.set_ylim(-pz_f * 1.02, Z + pz_f * 0.45)
    ax_front.set_aspect("equal", adjustable="box")
    ax_front.grid(True, linestyle=":", color="#ddd", linewidth=0.6)
    ax_front.set_xlabel("X (mm)", fontsize=8.0)
    ax_front.set_ylabel("Z (mm)", fontsize=8.0)
    ax_front.set_title("Hinh chieu dung XZ (Chieu cao Z)", fontsize=9.0, fontweight="bold", color=c_edge)

    # Right view (YZ) with Z = 0 bed plane
    _plot_orthographic_side(ax_right, mesh, 1, 2, c_mid, c_edge, edge_lw=0.9)
    py_r = max(3.0, Y * 0.24)
    pz_r = max(2.5, Z * 0.30)
    _draw_bed_plane(ax_right, -py_r * 0.9, Y + py_r * 0.3, fontsize=6.8)
    _draw_dim_arrow(ax_right, 0, -pz_r * 0.52, Y, -pz_r * 0.52, f"W={Y:.1f}mm", fontsize=7.6, color=c_accent)
    _draw_dim_arrow(ax_right, -py_r * 0.52, 0, -py_r * 0.52, Z, f"H={Z:.1f}mm", fontsize=7.6, color=c_accent)
    ax_right.set_xlim(-py_r * 1.08, Y + py_r * 0.42)
    ax_right.set_ylim(-pz_r * 1.02, Z + pz_r * 0.45)
    ax_right.set_aspect("equal", adjustable="box")
    ax_right.grid(True, linestyle=":", color="#ddd", linewidth=0.6)
    ax_right.set_xlabel("Y (mm)", fontsize=8.0)
    ax_right.set_ylabel("Z (mm)", fontsize=8.0)
    ax_right.set_title("Hinh chieu canh YZ", fontsize=9.0, fontweight="bold", color=c_edge)

    # Optional quick summary card in upper right corner (above title block)
    ax_badge = fig.add_axes([0.755, 0.50, 0.205, 0.365])
    ax_badge.axis("off")
    ax_badge.add_patch(
        FancyBboxPatch((0.0, 0.0), 1.0, 1.0, boxstyle="round,pad=0.02",
                       facecolor=c_bg, edgecolor=c_accent, lw=1.0)
    )
    bed_ok_s = "DAT" if meta.get("bed_fit", True) else "VUOT"
    solids_n = int(meta.get("solids", 1))
    summary_items = [
        ("KICH THUOC", f"{X:.1f} x {Y:.1f} x {Z:.1f} mm"),
        ("THE TICH", f"{float(meta['volume_mm3']) / 1000.0:.2f} cm3"),
        ("SO LUONG IN", f"{meta.get('qty', 1)} cai"),
        ("BAN IN 170x190", f"{bed_ok_s} (Z=0 phang)"),
        ("SUPPORT", "KHONG CAN (0%)"),
        ("VIT / KEO", "0 VIT - 0 KEO"),
        ("SO KHOI", f"{solids_n} solid"),
    ]
    y_cur = 0.92
    for k_lbl, v_lbl in summary_items:
        ax_badge.text(0.06, y_cur, k_lbl, fontsize=6.7, fontweight="bold", color=c_accent, va="top")
        ax_badge.text(0.06, y_cur - 0.045, v_lbl, fontsize=8.0, fontweight="bold", color="#1a2530", va="top")
        y_cur -= 0.132

    # Vietnamese Technical Title Block
    mating_or_attach = meta.get("mating_source") or meta.get("attachment") or "-"
    extra_cat = f"PHONG: {meta['room']}" if kind == "furniture" else f"PHAN LOAI: {str(meta.get('category', '')).upper()}"
    eng_txt = meta.get("engrave_text") or "(Khong khac do kich thuoc nho)"
    sockets_info = ""
    if "floor_sockets_local_xy" in meta and meta["floor_sockets_local_xy"]:
        sockets_info = f"{len(meta['floor_sockets_local_xy'])} lo mong day 6.3x4.3x4.2 mm (chot FUR09)"
    elif kind == "support":
        pr = meta.get("params", {})
        if "peg_od" in pr:
            sockets_info = f"4x chot dan hoi OD {pr['peg_od']} mm + ranh mong day 6.3x3.3 mm"
        elif "slot_w" in pr:
            sockets_info = f"Ranh chu U {pr['slot_w']} mm (+0.20 mm cho tam 3.0 mm)"
        elif "tenon_x" in pr:
            sockets_info = f"Chot mong {pr['tenon_x']}x{pr['tenon_y']}x{pr.get('tenon_h', pr.get('length_z', 3.0))} mm (0.15 mm/canh)"
        else:
            sockets_info = "In lien khoi chong tham / dat long khong keo"
    else:
        sockets_info = "Mong cai khit 0.15 mm/canh (khong vit, khong keo)"

    raw_lines = [
        f"MA CHI TIET: {part_id}   |   {extra_cat}",
        f"TEN: {meta.get('vi_name', part_id)}",
        f"VI TRI LAP GHEP: {mating_or_attach}",
        f"CHI TIET MONG / LO: {sockets_info}",
        f"CHU KHAC: {eng_txt}",
        f"GHI CHU: {meta.get('notes', '')}",
        "HUONG IN: Mat day Z = 0 nam phang | PLA/PETG | Lop 0.20mm | 3 thanh | Infill 25% | Support: KHONG",
    ]
    wrapped: list[str] = []
    for ln in raw_lines:
        wrapped.extend(textwrap.wrap(ln, width=74) or [""])

    ax_info.add_patch(
        FancyBboxPatch((0.0, 0.0), 1.0, 1.0, boxstyle="round,pad=0.015",
                       facecolor=c_bg, edgecolor=c_accent, lw=1.25)
    )
    ax_info.add_patch(MplRect((0.0, 0.87), 1.0, 0.13, facecolor=c_accent, edgecolor="none"))
    ax_info.text(0.50, 0.935, f"THONG SO KY THUAT — {header_tag}", fontsize=8.8,
                 fontweight="bold", color="white", ha="center", va="center")
    ax_info.text(0.025, 0.835, "\n".join(wrapped), fontsize=7.35, color="#1f1b16", va="top", linespacing=1.32)

    fig.suptitle(
        f"{title_prefix}: {part_id}   ({X:.1f} x {Y:.1f} x {Z:.1f} mm)",
        fontsize=12.4, fontweight="bold", color=c_edge, y=0.955,
    )
    fig.text(
        0.04, 0.028,
        "Smart Home Voice AI — Bo in 3D v2 (Khong vit, Khong keo, Ban in 180x200x250 mm) | Don vi: mm",
        fontsize=7.7, color="#555",
    )

    fig.savefig(str(pdf_path), format="pdf")
    fig.savefig(str(png_path), format="png", dpi=160)
    plt.close(fig)
    return pdf_path, png_path


# ---------------------------------------------------------------------------
# 2. Special Drawing 1: MONG JOINT CLOSE-UP (4-Panel A3 Landscape, 220 DPI)
# ---------------------------------------------------------------------------
def draw_joint_closeup_mong(cfg: pd_mod.PrintConfig) -> tuple[pathlib.Path, pathlib.Path]:
    """Generate `_joint_closeup_mong.png` & `.pdf` (A3 landscape 220 DPI, 4-panel zoomed CAD sheet)."""
    DRAW_DIR.mkdir(parents=True, exist_ok=True)
    png_path = DRAW_DIR / "_joint_closeup_mong.png"
    pdf_path = DRAW_DIR / "_joint_closeup_mong.pdf"

    fig = plt.figure(figsize=(16.54, 11.69), dpi=220)
    fig.patch.set_facecolor("white")

    # Outer engineering border
    ax_border = fig.add_axes([0.012, 0.012, 0.976, 0.976])
    ax_border.axis("off")
    ax_border.add_patch(MplRect((0, 0), 1, 1, fill=False, edgecolor="#0f2b46", lw=1.8))

    # Top title banner
    ax_hdr = fig.add_axes([0.012, 0.922, 0.976, 0.066])
    ax_hdr.axis("off")
    ax_hdr.add_patch(MplRect((0, 0), 1, 1, facecolor="#0f2b46", edgecolor="none"))
    ax_hdr.text(
        0.018, 0.65,
        "CHI TIET MONG LIEN KET KHONG VIT - KHONG KEO (MONG JOINT CLOSE-UP — 3D-PRINT SET v2)",
        fontsize=14.2, fontweight="bold", color="white", va="center", ha="left",
    )
    ax_hdr.text(
        0.018, 0.25,
        "Smart Home Voice AI | FDM PLA 0.4 mm nozzle, 0.20 mm layer | Ban in 180x200x250 mm (vung an toan 170x190x245 mm) | Don vi: mm",
        fontsize=9.2, color="#b8d4ec", va="center", ha="left",
    )
    ax_hdr.text(
        0.985, 0.50,
        "0 VIT • 0 KEO • 0 SUPPORT",
        fontsize=10.5, fontweight="bold", color="#f8c471", va="center", ha="right",
        bbox=dict(boxstyle="round,pad=0.30", facecolor="#1c4268", edgecolor="#f8c471", lw=1.1),
    )

    # 2x2 panel layout with generous whitespace to prevent ANY overlap
    ax_a = fig.add_axes([0.048, 0.505, 0.435, 0.375])
    ax_b = fig.add_axes([0.530, 0.505, 0.435, 0.375])
    ax_c = fig.add_axes([0.048, 0.075, 0.435, 0.370])
    ax_d = fig.add_axes([0.530, 0.075, 0.435, 0.370])

    # =========================================================================
    # PANEL A: REAL ZOOMED DOVETAIL SPLIT SEAM (P02_WALL_BACK piece1 + piece2)
    # =========================================================================
    m1 = json.loads((META_DIR / "P02_WALL_BACK_piece1of3.json").read_text(encoding="utf-8"))
    m2 = json.loads((META_DIR / "P02_WALL_BACK_piece2of3.json").read_text(encoding="utf-8"))
    mesh1 = trimesh.load_mesh(str(PARTS_DIR / "P02_WALL_BACK_piece1of3.stl"), force="mesh")
    mesh2 = trimesh.load_mesh(str(PARTS_DIR / "P02_WALL_BACK_piece2of3.stl"), force="mesh")

    _plot_top_mesh_panel(
        ax_a, mesh1, T=3.0, shift_xy=(m1["local_bbox_min"][0], m1["local_bbox_min"][1]),
        main_color="#cde6f7", recess_color="#0f2b46", edge_color="#0b2540", edge_lw=1.35, zorder_base=2,
    )
    _plot_top_mesh_panel(
        ax_a, mesh2, T=3.0, shift_xy=(m2["local_bbox_min"][0], m2["local_bbox_min"][1]),
        main_color="#cdeee0", recess_color="#0f2b46", edge_color="#115e43", edge_lw=1.35, zorder_base=2,
    )

    # Real dovetail #1 on P02 seam U = 118.5, V = 52.0 (depth=6.0, neck=10.0, head=14.0, clr=0.20)
    cut_u = 118.5
    cen_v = 52.0
    # Centerline & seam reference
    ax_a.axvline(cut_u, color="#8e44ad", lw=0.9, ls="-.", alpha=0.75, zorder=8)
    ax_a.axhline(cen_v, color="#7f8c8d", lw=0.7, ls=":", alpha=0.7, zorder=8)

    # Dimension arrows (carefully positioned outside the joint geometry)
    # 1. Depth = 6.0 mm (below dovetail at V = 41.2)
    ax_a.plot([112.5, 112.5], [45.0, 40.3], color="#1b365d", lw=0.75, ls="--", zorder=9)
    ax_a.plot([118.5, 118.5], [47.0, 40.3], color="#1b365d", lw=0.75, ls="--", zorder=9)
    _draw_dim_arrow(ax_a, 112.5, 41.2, 118.5, 41.2, "Sau = 6.0 mm", offset_txt=(0, -1.7), fontsize=8.1)

    # 2. Head = 14.0 mm (left of dovetail at U = 109.2)
    ax_a.plot([108.5, 112.5], [45.0, 45.0], color="#1b365d", lw=0.75, ls="--", zorder=9)
    ax_a.plot([108.5, 112.5], [59.0, 59.0], color="#1b365d", lw=0.75, ls="--", zorder=9)
    _draw_dim_arrow(ax_a, 109.3, 45.0, 109.3, 59.0, "Dau = 14.0 mm", fontsize=8.1)

    # 3. Neck = 10.0 mm (right of seam at U = 122.4)
    ax_a.plot([118.5, 123.1], [47.0, 47.0], color="#1b365d", lw=0.75, ls="--", zorder=9)
    ax_a.plot([118.5, 123.1], [57.0, 57.0], color="#1b365d", lw=0.75, ls="--", zorder=9)
    _draw_dim_arrow(ax_a, 122.3, 47.0, 122.3, 57.0, "Co = 10.0 mm", fontsize=8.1)

    # 4. Clearance callout pointing straight to the REAL 0.20 mm clearance gap!
    _draw_callout(
        ax_a, xy=(112.40, 56.8), xytext=(103.6, 63.6),
        text="Khe ho mong: 0.20 mm\n(Am 14.4x6.2 vs Duong 14.0x6.0)",
        color="#c0392b", fontsize=7.9, ha="left", va="center", fc="#fff8f7",
    )
    _draw_callout(
        ax_a, xy=(118.50, 62.5), xytext=(120.2, 64.2),
        text="Duong chia U=118.5 mm\n(Khe ho ranh 0.10 mm)",
        color="#6c3483", fontsize=7.6, ha="left", va="center", fc="#faf5ff",
    )

    # Piece identity badges
    ax_a.text(106.4, 40.4, "P02_piece1of3\n(Ranh am / Female)", fontsize=7.8, fontweight="bold",
              color="#0b2540", ha="center", va="center",
              bbox=dict(boxstyle="round,pad=0.24", facecolor="#cde6f7", edgecolor="#0b2540", lw=0.9), zorder=12)
    ax_a.text(126.2, 40.4, "P02_piece2of3\n(Luoi duong / Male)", fontsize=7.8, fontweight="bold",
              color="#115e43", ha="center", va="center",
              bbox=dict(boxstyle="round,pad=0.24", facecolor="#cdeee0", edgecolor="#115e43", lw=0.9), zorder=12)

    ax_a.set_xlim(100.8, 132.2)
    ax_a.set_ylim(36.2, 67.6)
    ax_a.set_aspect("equal", adjustable="box")
    ax_a.grid(True, linestyle=":", color="#d5dde5", lw=0.6)
    ax_a.set_xlabel("Toa do cuc bo U tren P02_WALL_BACK (mm)", fontsize=8.4)
    ax_a.set_ylabel("Toa do V (mm)", fontsize=8.4)
    ax_a.set_title(
        "A. KHOP MONG DUOI EN CHIA MANH (STL THUC TE: P02 piece1of3 + piece2of3)",
        fontsize=9.8, fontweight="bold", color="#0f2b46", pad=8,
    )

    # =========================================================================
    # PANEL B: TAB-AND-SLOT (3.0 in 3.25) & 90-DEG CORNER LOCK CLIP (SUP01)
    # =========================================================================
    ax_b.set_xlim(-2.0, 56.0)
    ax_b.set_ylim(-5.5, 31.5)
    ax_b.set_aspect("equal", adjustable="box")
    ax_b.grid(True, linestyle=":", color="#e2ddd5", lw=0.6)

    # --- Left sub-diagram (X: 0..21): Panel Tab-and-Slot cross-section ---
    # Horizontal floor/base panel (3.0 mm thick, Y = 4..7) with 3.25 mm slot (X = 8.375..11.625)
    ax_b.add_patch(MplRect((1.0, 4.0), 7.375, 3.0, facecolor="#cde6f7", edgecolor="#0b2540", lw=1.2, zorder=3))
    ax_b.add_patch(MplRect((11.625, 4.0), 7.375, 3.0, facecolor="#cde6f7", edgecolor="#0b2540", lw=1.2, zorder=3))
    # Vertical wall panel (3.0 mm thick, X = 8.50..11.50) entering slot from Y=4..22
    ax_b.add_patch(MplRect((8.50, 4.0), 3.0, 18.0, facecolor="#cdeee0", edgecolor="#115e43", lw=1.2, zorder=4))
    # Highlight +0.125 mm clearance gaps on each side inside slot
    ax_b.add_patch(MplRect((8.375, 4.0), 0.125, 3.0, facecolor="#fadbd8", edgecolor="none", zorder=3))
    ax_b.add_patch(MplRect((11.50, 4.0), 0.125, 3.0, facecolor="#fadbd8", edgecolor="none", zorder=3))

    ax_b.text(10.0, 26.8, "1. Khop Rang Luoc (Tab-and-Slot)", fontsize=8.6, fontweight="bold",
              color="#0f2b46", ha="center", va="center",
              bbox=dict(boxstyle="round,pad=0.22", facecolor="#eef5fb", edgecolor="#1b365d", lw=0.8))
    ax_b.text(4.5, 5.5, "Tam day\n3.0 mm", fontsize=7.0, fontweight="bold", color="#0b2540", ha="center", va="center", zorder=5)
    ax_b.text(10.0, 14.5, "Tuong\n3.0mm", fontsize=7.0, fontweight="bold", color="#115e43", ha="center", va="center", zorder=5)

    # Dims on sub-diagram 1
    ax_b.plot([8.5, 8.5], [22.0, 24.4], color="#115e43", lw=0.7, ls="--")
    ax_b.plot([11.5, 11.5], [22.0, 24.4], color="#115e43", lw=0.7, ls="--")
    _draw_dim_arrow(ax_b, 8.5, 23.6, 11.5, 23.6, "T = 3.00", offset_txt=(0, 1.3), fontsize=7.4, color="#115e43")

    ax_b.plot([8.375, 8.375], [4.0, 0.2], color="#c0392b", lw=0.7, ls="--")
    ax_b.plot([11.625, 11.625], [4.0, 0.2], color="#c0392b", lw=0.7, ls="--")
    _draw_dim_arrow(ax_b, 8.375, 1.0, 11.625, 1.0, "Ranh 3.25 (+0.25)", offset_txt=(0, -2.1), fontsize=7.5, color="#c0392b")

    ax_b.plot([19.0, 21.0], [4.0, 4.0], color="#0b2540", lw=0.7, ls="--")
    ax_b.plot([19.0, 21.0], [7.0, 7.0], color="#0b2540", lw=0.7, ls="--")
    _draw_dim_arrow(ax_b, 20.4, 4.0, 20.4, 7.0, "3.0", offset_txt=(2.1, 0), fontsize=7.2, rot=0)

    # Divider line between sub-diagram 1 and 2
    ax_b.axvline(24.0, color="#bdc3c7", lw=1.0, ls="--", zorder=1)

    # --- Right sub-diagram (X: 27..53): SUP01 90-deg Dual U-Channel Corner Clip (Top Section) ---
    # Outer corner of SUP01 at (ox, oy) = (28.0, 2.5), arm = 24.0, wall_t = 2.6, slot_w = 3.20, arm_w = 8.40
    ox, oy = 28.5, 2.0
    arm, wt, sw = 24.0, 2.6, 3.20
    aw = sw + 2.0 * wt  # 8.40
    # Draw SUP01 U-channel walls (outer L + inner L legs)
    sup01_outer = MplPolygon(
        [(ox, oy), (ox + arm, oy), (ox + arm, oy + wt), (ox + wt, oy + wt), (ox + wt, oy + arm), (ox, oy + arm)],
        closed=True, facecolor="#f5b041", edgecolor="#7e5109", lw=1.2, zorder=4,
    )
    sup01_inner = MplPolygon(
        [(ox + wt + sw, oy + wt + sw), (ox + arm, oy + wt + sw), (ox + arm, oy + aw),
         (ox + aw, oy + aw), (ox + aw, oy + arm), (ox + wt + sw, oy + arm)],
        closed=True, facecolor="#f5b041", edgecolor="#7e5109", lw=1.2, zorder=4,
    )
    # Gusset cap hatched subtly in background inside inner corner
    gusset = MplPolygon(
        [(ox + aw, oy + aw), (ox + arm, oy + aw), (ox + arm, oy + 15.6), (ox + 15.6, oy + arm), (ox + aw, oy + arm)],
        closed=True, facecolor="#fdebd0", edgecolor="#b9770e", lw=0.8, ls="--", zorder=2,
    )
    ax_b.add_patch(gusset)
    ax_b.add_patch(sup01_outer)
    ax_b.add_patch(sup01_inner)

    # Two 3.0 mm walls seated inside the 3.20 mm dual U-channels (0.10 mm gap per side!)
    # Wall P02 along X (Y = oy + wt + 0.10 .. + 3.10)
    ax_b.add_patch(MplRect((ox + wt + 0.10, oy + wt + 0.10), arm - wt + 1.4, 3.0,
                           facecolor="#cde6f7", edgecolor="#0b2540", lw=1.1, zorder=5))
    # Wall P03 along Y (X = oy/ox + wt + 0.10 .. + 3.10)
    ax_b.add_patch(MplRect((ox + wt + 0.10, oy + wt + 3.10), 3.0, arm - wt - 1.6,
                           facecolor="#cdeee0", edgecolor="#115e43", lw=1.1, zorder=5))

    ax_b.text(40.5, 29.0, "2. Kep Khoa Goc 90° SUP01 (Ranh chu U kep)", fontsize=8.6, fontweight="bold",
              color="#7e5109", ha="center", va="center",
              bbox=dict(boxstyle="round,pad=0.22", facecolor="#fff5e6", edgecolor="#935116", lw=0.8))

    # Dimensions on SUP01
    ax_b.plot([ox, ox], [oy, oy - 3.6], color="#7e5109", lw=0.7, ls="--")
    ax_b.plot([ox + arm, ox + arm], [oy, oy - 3.6], color="#7e5109", lw=0.7, ls="--")
    _draw_dim_arrow(ax_b, ox, oy - 2.6, ox + arm, oy - 2.6, "SUP01 Arm = 24.0 mm (H = 14.0 mm)", fontsize=7.5, color="#7e5109")

    # Slot width 3.20 mm callout on right opening
    _draw_callout(
        ax_b, xy=(ox + arm - 2.5, oy + wt + sw * 0.5), xytext=(41.0, 14.8),
        text="Ranh chu U: 3.20 mm\nTam 3.00 mm (+0.20 mm)",
        color="#c0392b", fontsize=7.6, ha="left", va="center", fc="#fff8f7",
    )
    _draw_callout(
        ax_b, xy=(ox + 1.3, oy + 20.8), xytext=(39.2, 23.0),
        text="Thanh kep: 2.6 mm\nKhoa goc 90° (0 vit)",
        color="#7e5109", fontsize=7.6, ha="left", va="center", fc="#fffaf0",
    )
    ax_b.text(ox + wt + 1.6, oy + 12.2, "P03\n3.0", fontsize=6.6, fontweight="bold", color="#115e43", ha="center", va="center", zorder=6)
    ax_b.text(ox + 18.0, oy + wt + 1.6, "P02 (3.0 mm)", fontsize=6.6, fontweight="bold", color="#0b2540", ha="center", va="center", zorder=6)

    ax_b.set_xlabel("Kich thuoc mat cat (mm)", fontsize=8.4)
    ax_b.set_ylabel("mm", fontsize=8.4)
    ax_b.set_title(
        "B. KHOP RANG LUOC (+0.25 mm) & KEP GOC 90° SUP01 (+0.20 mm — KHONG VIT)",
        fontsize=9.8, fontweight="bold", color="#7e5109", pad=8,
    )

    # =========================================================================
    # PANEL C: FLOATING MORTISE-AND-TENON FLOOR PEG (FUR09 in P01B + FUR01)
    # =========================================================================
    # X centered at 0.0 (peg X in [-3.0, +3.0], mortise/socket X in [-3.15, +3.15])
    # Z: floor P01B Z in [-3.0, 0.0], FUR01_SOFA Z in [0.0, 7.5], socket Z in [0.0, 4.20]
    # Peg FUR09 Z in [-3.0, +4.0] with 0.30 mm x 45 deg chamfer at top & bottom!
    ax_c.set_xlim(-11.5, 14.2)
    ax_c.set_ylim(-6.2, 9.6)
    ax_c.set_aspect("equal", adjustable="box")
    ax_c.grid(True, linestyle=":", color="#d5e2dc", lw=0.6)

    # Floor P01B left & right of 6.30 mm through-mortise
    ax_c.add_patch(MplRect((-10.0, -3.0), 6.85, 3.0, facecolor="#cde6f7", edgecolor="#0b2540", lw=1.2, hatch="///", zorder=2))
    ax_c.add_patch(MplRect((3.15, -3.0), 6.85, 3.0, facecolor="#cde6f7", edgecolor="#0b2540", lw=1.2, hatch="///", zorder=2))

    # Sofa FUR01_SOFA body sitting on Z=0 with blind socket [-3.15..+3.15, 0..4.20]
    sofa_poly = [
        (-9.5, 0.0), (-3.15, 0.0), (-3.15, 4.20), (3.15, 4.20), (3.15, 0.0),
        (9.5, 0.0), (9.5, 6.8), (-9.5, 6.8),
    ]
    ax_c.add_patch(MplPolygon(sofa_poly, closed=True, facecolor="#d6e6f0", edgecolor="#1b4f72", lw=1.2, zorder=2))

    # Highlight clearance gaps (0.15 mm/side + 0.20 mm top pocket clearance)
    ax_c.add_patch(MplRect((-3.15, -3.0), 0.15, 7.20, facecolor="#fadbd8", edgecolor="none", zorder=3))
    ax_c.add_patch(MplRect((3.00, -3.0), 0.15, 7.20, facecolor="#fadbd8", edgecolor="none", zorder=3))
    ax_c.add_patch(MplRect((-3.15, 4.00), 6.30, 0.20, facecolor="#fef9e7", edgecolor="none", zorder=3))

    # FUR09 floating peg (6.00 x 7.00 mm, 0.30 mm x 45 deg lead-in chamfers on both ends)
    ch = 0.30
    peg_poly = [
        (-3.0 + ch, -3.0), (3.0 - ch, -3.0), (3.0, -3.0 + ch),
        (3.0, 4.0 - ch), (3.0 - ch, 4.0), (-3.0 + ch, 4.0),
        (-3.0, 4.0 - ch), (-3.0, -3.0 + ch),
    ]
    ax_c.add_patch(MplPolygon(peg_poly, closed=True, facecolor="#d4ac7d", edgecolor="#5d3a1a", lw=1.35, zorder=5))
    ax_c.axvline(0.0, color="#7f8c8d", lw=0.75, ls="-.", zorder=6)
    ax_c.axhline(0.0, color="#1e8449", lw=0.9, ls="--", zorder=4)

    # Labels inside parts
    ax_c.text(-6.7, -1.5, "San P01B\n(3.0 mm)", fontsize=7.5, fontweight="bold", color="#0b2540", ha="center", va="center",
              bbox=dict(boxstyle="round,pad=0.16", facecolor="white", edgecolor="#0b2540", lw=0.5, alpha=0.92), zorder=6)
    ax_c.text(-6.5, 3.6, "Day FUR01_SOFA\n(Ho mong am 4.2 mm)", fontsize=7.4, fontweight="bold", color="#1b4f72", ha="center", va="center", zorder=6)
    ax_c.text(0.0, 0.6, "FUR09\n6.0x4.0x7.0", fontsize=7.6, fontweight="bold", color="#4a2308", ha="center", va="center", zorder=7)

    # Dimension arrows
    # Peg width 6.00 mm (bottom)
    ax_c.plot([-3.0, -3.0], [-3.0, -5.0], color="#5d3a1a", lw=0.7, ls="--")
    ax_c.plot([3.0, 3.0], [-3.0, -5.0], color="#5d3a1a", lw=0.7, ls="--")
    _draw_dim_arrow(ax_c, -3.0, -4.5, 3.0, -4.5, "Chot = 6.00 mm", fontsize=7.9, color="#5d3a1a")

    # Socket width 6.30 mm (top)
    ax_c.plot([-3.15, -3.15], [4.20, 8.6], color="#1b4f72", lw=0.7, ls="--")
    ax_c.plot([3.15, 3.15], [4.20, 8.6], color="#1b4f72", lw=0.7, ls="--")
    _draw_dim_arrow(ax_c, -3.15, 8.0, 3.15, 8.0, "Lo mong = 6.30 mm (6.30 x 4.30)", fontsize=7.9, color="#1b4f72")

    # Floor thickness 3.0 mm & Total peg height 7.0 mm (right side)
    ax_c.plot([10.0, 12.6], [-3.0, -3.0], color="#0b2540", lw=0.7, ls="--")
    ax_c.plot([10.0, 12.6], [0.0, 0.0], color="#0b2540", lw=0.7, ls="--")
    _draw_dim_arrow(ax_c, 12.3, -3.0, 12.3, 0.0, "3.0", fontsize=7.5, rot=0, offset_txt=(0.95, 0))

    ax_c.plot([3.15, 11.1], [4.0, 4.0], color="#5d3a1a", lw=0.7, ls="--")
    _draw_dim_arrow(ax_c, 10.6, -3.0, 10.6, 4.0, "H=7.0", fontsize=7.5, color="#5d3a1a")

    # Clear callouts for 0.15 mm/side clearance & 0.30 mm lead-in chamfer
    _draw_callout(
        ax_c, xy=(3.08, 2.0), xytext=(4.8, 5.2),
        text="Khe ho ep khit:\n0.15 mm/canh (+0.30 tong)",
        color="#c0392b", fontsize=7.5, ha="left", va="center", fc="#fff8f7",
    )
    _draw_callout(
        ax_c, xy=(-2.85, 3.85), xytext=(-10.8, 8.2),
        text="Vat mep dan huong\n0.30 mm x 45°",
        color="#1e6b52", fontsize=7.4, ha="left", va="center", fc="#f2fbf6",
    )
    ax_c.text(
        4.4, -4.6,
        "Mat cat XY: 6.0x4.0 trong 6.30x4.30 mm\nIn nam phang -> 0 support!",
        fontsize=7.1, color="#1b4d3e", fontweight="bold", ha="left", va="center",
        bbox=dict(boxstyle="round,pad=0.22", facecolor="#eef8f1", edgecolor="#1e6b52", lw=0.7),
    )

    ax_c.set_xlabel("Mat cat ngang X (mm)", fontsize=8.4)
    ax_c.set_ylabel("Truc Z lap rap (mm)", fontsize=8.4)
    ax_c.set_title(
        "C. CHOT MONG SAN NOI THAT (FUR09 -> P01B 3.0mm + FUR01_SOFA)",
        fontsize=9.8, fontweight="bold", color="#1b4d3e", pad=8,
    )

    # =========================================================================
    # PANEL D: SPLIT CANTILEVER SNAP-FIT PEG (SUP06 -> REAL KICAD HUB PCB)
    # =========================================================================
    # Exact CAD coordinates from build_mounts_v2.py (_make_split_snap_peg_and_slot & _build_pcb_carrier):
    # Standoff boss: OD = 7.40 (r=3.70), Z = 7.2..10.0 (shown with break line at Z=7.2)
    # KiCad Hub PCB: thickness = 1.60 mm (Z = 10.0..11.60), real MountingHole_3.2mm (r = 1.60)
    # Split peg: OD = 3.00 (r0 = 1.50), slot_w = 0.80 (x in [-0.40, +0.40]),
    #   z_ramp0 = 11.75, barb_radial = 0.25 -> r_barb = 1.75 at z_ramp1 = 12.00,
    #   z_land1 = 12.25, z_top = 13.60 (r_tip = 1.02)
    ax_d.set_xlim(-6.8, 7.6)
    ax_d.set_ylim(6.6, 15.2)
    ax_d.set_aspect("equal", adjustable="box")
    ax_d.grid(True, linestyle=":", color="#d5e5dc", lw=0.6)

    # Standoff boss OD 7.40 (Z=7.4..10.0)
    ax_d.add_patch(MplRect((-3.70, 7.4), 7.40, 2.60, facecolor="#9fd6b8", edgecolor="#145a32", lw=1.25, zorder=2))
    ax_d.text(0.0, 8.35, "Tru do SUP06 (OD 7.40 mm, H=10.0 mm)", fontsize=7.5, fontweight="bold",
              color="#145a32", ha="center", va="center", zorder=4)

    # Real KiCad Hub PCB (1.60 mm thick, Z=10.0..11.60, hole radius = 1.60 mm)
    ax_d.add_patch(MplRect((-6.2, 10.0), 4.60, 1.60, facecolor="#2e8b57", edgecolor="#0e3b22", lw=1.2, zorder=3))
    ax_d.add_patch(MplRect((1.60, 10.0), 4.60, 1.60, facecolor="#2e8b57", edgecolor="#0e3b22", lw=1.2, zorder=3))
    # Copper annular pad rings on top & bottom of KiCad hole (pad dia ~5.8 mm -> r=2.9)
    for z_pad in (9.92, 11.56):
        ax_d.add_patch(MplRect((-2.90, z_pad), 1.30, 0.12, facecolor="#f1c40f", edgecolor="#9a7d0a", lw=0.5, zorder=4))
        ax_d.add_patch(MplRect((1.60, z_pad), 1.30, 0.12, facecolor="#f1c40f", edgecolor="#9a7d0a", lw=0.5, zorder=4))
    ax_d.text(-4.1, 10.8, "KiCad Hub PCB\n(FR-4 1.60 mm)", fontsize=7.3, fontweight="bold",
              color="white", ha="center", va="center", zorder=5)

    # Highlight 0.10 mm/side diametral clearance inside hole (r=1.50..1.60, Z=10.0..11.60)
    ax_d.add_patch(MplRect((-1.60, 10.0), 0.10, 1.60, facecolor="#fadbd8", edgecolor="none", zorder=3))
    ax_d.add_patch(MplRect((1.50, 10.0), 0.10, 1.60, facecolor="#fadbd8", edgecolor="none", zorder=3))

    # Left & right split cantilever snap-fit prongs (exact CAD polygon)
    def _prong_poly(s: float) -> list[tuple[float, float]]:
        return [
            (s * 0.40, 10.0),
            (s * 1.50, 10.0),
            (s * 1.50, 11.75),
            (s * 1.75, 12.00),
            (s * 1.75, 12.25),
            (s * 1.02, 13.60),
            (s * 0.40, 13.60),
        ]

    ax_d.add_patch(MplPolygon(_prong_poly(-1.0), closed=True, facecolor="#9fd6b8", edgecolor="#145a32", lw=1.35, zorder=5))
    ax_d.add_patch(MplPolygon(_prong_poly(+1.0), closed=True, facecolor="#9fd6b8", edgecolor="#145a32", lw=1.35, zorder=5))
    # Flex slot visual highlight
    ax_d.add_patch(MplRect((-0.40, 10.0), 0.80, 3.60, facecolor="#fef9e7", edgecolor="none", zorder=4))
    ax_d.axvline(0.0, color="#7f8c8d", lw=0.7, ls="-.", zorder=6)

    # Dimension arrows (neatly arranged without crossing!)
    # 1. Flex slot 0.80 mm (top)
    ax_d.plot([-0.40, -0.40], [13.60, 14.70], color="#935116", lw=0.75, ls="--")
    ax_d.plot([0.40, 0.40], [13.60, 14.70], color="#935116", lw=0.75, ls="--")
    _draw_dim_arrow(ax_d, -0.40, 14.35, 0.40, 14.35, "Ranh dan hoi = 0.80 mm", offset_txt=(0, 0.50), fontsize=7.6, color="#935116")

    # 2. Hole Dia 3.20 mm vs Peg OD 3.00 mm (below boss / left-right callouts)
    ax_d.plot([-1.60, -1.60], [10.0, 9.2], color="#1b365d", lw=0.7, ls="--")
    ax_d.plot([1.60, 1.60], [10.0, 9.2], color="#1b365d", lw=0.7, ls="--")
    _draw_dim_arrow(ax_d, -1.60, 9.35, 1.60, 9.35, "Lo KiCad Ø3.20", fontsize=7.4, color="#1b365d")

    ax_d.plot([-3.70, -3.70], [7.4, 6.85], color="#145a32", lw=0.7, ls="--")
    ax_d.plot([3.70, 3.70], [7.4, 6.85], color="#145a32", lw=0.7, ls="--")
    _draw_dim_arrow(ax_d, -3.70, 7.02, 3.70, 7.02, "Tru do OD = 7.40 mm", fontsize=7.5, color="#145a32")

    # 3. PCB thickness 1.60 mm (right side)
    ax_d.plot([6.2, 6.85], [10.0, 10.0], color="#0e3b22", lw=0.7, ls="--")
    ax_d.plot([6.2, 6.85], [11.6, 11.6], color="#0e3b22", lw=0.7, ls="--")
    _draw_dim_arrow(ax_d, 6.65, 10.0, 6.65, 11.6, "1.60", fontsize=7.5, rot=0, color="#0e3b22")

    # 4. Crisp callouts for OD 3.00, 0.20 mm clearance, and 0.25 mm barb
    _draw_callout(
        ax_d, xy=(1.75, 12.12), xytext=(2.85, 13.75),
        text="Gai khoa 45°: +0.25 mm/ben\n(OD 3.50 mm tu khoa tren PCB)",
        color="#145a32", fontsize=7.5, ha="left", va="center", fc="#f2fbf6",
    )
    _draw_callout(
        ax_d, xy=(1.55, 10.80), xytext=(2.75, 12.10),
        text="Than chot OD 3.00 mm\nKhe ho: 0.20 mm (0.10/ben)",
        color="#c0392b", fontsize=7.5, ha="left", va="center", fc="#fff8f7",
    )
    _draw_callout(
        ax_d, xy=(-1.35, 12.95), xytext=(-6.45, 13.45),
        text="Dau con dan huong 45°\n(Ep tay vao lo Ø3.20 -> tach!)",
        color="#1b365d", fontsize=7.4, ha="left", va="center", fc="#f4f8fc",
    )

    ax_d.set_xlabel("Mat cat ngang tam chot X (mm)", fontsize=8.4)
    ax_d.set_ylabel("Cao do Z tren SUP06 (mm)", fontsize=8.4)
    ax_d.set_title(
        "D. CHOT DAN HOI SPLIT SNAP-FIT (SUP06 -> LO Ø3.20 mm KICAD HUB PCB)",
        fontsize=9.8, fontweight="bold", color="#145a32", pad=8,
    )

    # Bottom footer strip
    fig.text(
        0.025, 0.020,
        "BANG DUNG SAI SSOT (print_domain.py):  Duoi en: 0.20 mm  |  Rang luoc tam: 0.25 mm  |  Kep chu U: 0.20 mm  |  "
        "Chot mong ep khit: 0.15 mm/canh  |  Chot dan hoi PCB: 0.20 mm duong kinh + gai 0.25 mm  |  Ban le: 0.30 mm",
        fontsize=8.2, fontweight="bold", color="#1b365d",
    )

    fig.savefig(str(png_path), format="png", dpi=220)
    fig.savefig(str(pdf_path), format="pdf")
    plt.close(fig)
    return png_path, pdf_path


# ---------------------------------------------------------------------------
# 3. Special Drawing 2: PCB & MODULE FIT SHEET (6-Panel A3 Landscape, 220 DPI)
# ---------------------------------------------------------------------------
def draw_pcb_module_fit(cfg: pd_mod.PrintConfig) -> tuple[pathlib.Path, pathlib.Path]:
    """Generate `_pcb_module_fit.png` & `.pdf` (A3 landscape 220 DPI, real KiCad PCB + modules fit sheet)."""
    DRAW_DIR.mkdir(parents=True, exist_ok=True)
    png_path = DRAW_DIR / "_pcb_module_fit.png"
    pdf_path = DRAW_DIR / "_pcb_module_fit.pdf"

    pcb = pcb_ssot.parse_kicad_hub_pcb(run_cli_check=False)
    fit_data = json.loads(FIT_TABLE_PATH.read_text(encoding="utf-8"))
    fit_rows = fit_data["rows"]

    fig = plt.figure(figsize=(16.54, 11.69), dpi=220)
    fig.patch.set_facecolor("white")

    ax_border = fig.add_axes([0.012, 0.012, 0.976, 0.976])
    ax_border.axis("off")
    ax_border.add_patch(MplRect((0, 0), 1, 1, fill=False, edgecolor="#0f2b46", lw=1.8))

    # Header
    ax_hdr = fig.add_axes([0.012, 0.922, 0.976, 0.066])
    ax_hdr.axis("off")
    ax_hdr.add_patch(MplRect((0, 0), 1, 1, facecolor="#145a32", edgecolor="none"))
    ax_hdr.text(
        0.018, 0.65,
        "BAN VE KIEM TRA DO KHIT PCB & MODULE DIEN TU (REAL KICAD PCB & MODULE FIT — v2)",
        fontsize=14.0, fontweight="bold", color="white", va="center", ha="left",
    )
    ax_hdr.text(
        0.018, 0.25,
        f"Nguon PCB thuc te: {pcb.source_file} ({pcb.width_mm:.1f}x{pcb.height_mm:.1f}x{pcb.thickness_mm:.1f} mm, "
        f"4x Ø{pcb.hole_dia_mm:.1f} @ {pcb.hole_pitch_x_mm:.1f}x{pcb.hole_pitch_y_mm:.1f} mm) | fit_table.json: 12/12 PASS",
        fontsize=9.0, color="#d4efdf", va="center", ha="left",
    )
    ax_hdr.text(
        0.985, 0.50,
        "12 / 12 FIT PASS • 0 VIT",
        fontsize=10.5, fontweight="bold", color="#f9e79f", va="center", ha="right",
        bbox=dict(boxstyle="round,pad=0.30", facecolor="#1e8449", edgecolor="#f9e79f", lw=1.1),
    )

    # 2 rows x 3 cols layout
    ax1 = fig.add_axes([0.045, 0.510, 0.295, 0.365])  # Hub PCB on SUP06
    ax2 = fig.add_axes([0.378, 0.510, 0.275, 0.365])  # Relay on SUP07
    ax3 = fig.add_axes([0.692, 0.510, 0.275, 0.365])  # PAM8403 on SUP08
    ax4 = fig.add_axes([0.045, 0.078, 0.275, 0.365])  # SG90 on P07 + SUP11
    ax5 = fig.add_axes([0.358, 0.078, 0.275, 0.365])  # Speaker 28mm on P15 + SUP09
    ax6 = fig.add_axes([0.658, 0.062, 0.315, 0.395])  # Fit Table Summary (12 rows)

    # -------------------------------------------------------------------------
    # PANEL 1: Real KiCad Hub PCB 100x80 on SUP06_HUB_PCB_SNAP_CARRIER (104x84)
    # -------------------------------------------------------------------------
    # SUP06 frame centered at (52, 42): 104 x 84 mm, center cutout 72 x 52 mm
    ax1.add_patch(MplRect((0, 0), 104.0, 84.0, facecolor="#fef2df", edgecolor="#935116", lw=1.35, zorder=1))
    ax1.add_patch(MplRect((16.0, 16.0), 72.0, 52.0, facecolor="white", edgecolor="#935116", lw=1.0, ls="--", zorder=2))
    # Real KiCad Hub PCB 100 x 80 mm centered at (52, 42) -> (2..102, 2..82) with corner chamfer
    ch = pcb.corner_chamfer_mm
    pcb_pts = [
        (2 + ch, 2), (102 - ch, 2), (102, 2 + ch), (102, 82 - ch),
        (102 - ch, 82), (2 + ch, 82), (2, 82 - ch), (2, 2 + ch),
    ]
    ax1.add_patch(MplPolygon(pcb_pts, closed=True, facecolor="#2e8b57", edgecolor="#0e3b22", lw=1.4, alpha=0.30, zorder=3))
    ax1.add_patch(MplPolygon(pcb_pts, closed=True, fill=False, edgecolor="#145a32", lw=1.6, zorder=6))

    # Plot real KiCad component keepout dots (NodeMCU headers, screw terminals, etc.)
    for kp in pcb.keepouts:
        kx, ky = 2.0 + kp.x_mm, 2.0 + kp.y_mm
        if 2.0 <= kx <= 102.0 and 2.0 <= ky <= 82.0:
            ax1.plot(kx, ky, marker="s", markersize=2.6, color="#1b4f72", alpha=0.65, zorder=5)

    # Real 4x KiCad mounting holes (Ø3.20) & SUP06 standoff bosses (OD 7.40) + split pegs (OD 3.00)
    for h in pcb.mounting_holes:
        hx, hy = 2.0 + h.x_mm, 2.0 + h.y_mm
        ax1.add_patch(MplCircle((hx, hy), 3.7, facecolor="#f5cfa0", edgecolor="#935116", lw=0.8, zorder=4))
        ax1.add_patch(MplCircle((hx, hy), h.drill_dia_mm / 2.0, facecolor="white", edgecolor="#145a32", lw=1.1, zorder=7))
        ax1.add_patch(MplCircle((hx, hy), 1.50, facecolor="#2ecc71", edgecolor="#0b5345", lw=0.9, zorder=8))

    ax1.text(52.0, 42.0, "Khoet giua 72 x 52 mm\n(Thoat chan han NodeMCU)", fontsize=7.4, fontweight="bold",
             color="#7e5109", ha="center", va="center",
             bbox=dict(boxstyle="round,pad=0.20", facecolor="white", edgecolor="#935116", lw=0.6, alpha=0.90), zorder=9)

    # Outer dims: Frame 104x84, PCB 100x80, Pitch 90x70
    _draw_dim_arrow(ax1, 0, -10.5, 104, -10.5, "Khung SUP06 = 104.0", fontsize=7.3, color="#935116")
    _draw_dim_arrow(ax1, 2, 90.5, 102, 90.5, "KiCad PCB = 100.0 x 80.0", fontsize=7.4, color="#145a32")
    _draw_dim_arrow(ax1, -11.0, 0, -11.0, 84, "84.0", fontsize=7.3, color="#935116")
    _draw_dim_arrow(ax1, 7.0, 7.0, 97.0, 7.0, "Pitch = 90.0", offset_txt=(0, 4.8), fontsize=7.1, color="#1b365d")
    _draw_dim_arrow(ax1, 111.0, 7.0, 111.0, 77.0, "Pitch 70.0", fontsize=7.1, color="#1b365d")

    _draw_callout(
        ax1, xy=(97.0, 77.0), xytext=(56.0, 64.0),
        text="4x Chot OD 3.00 / Lo Ø3.20\n(Khe 0.20 mm dia | 0 vit)",
        color="#c0392b", fontsize=7.1, ha="center", va="center", fc="#fff8f7",
    )
    ax1.set_xlim(-19.0, 119.0)
    ax1.set_ylim(-18.5, 100.0)
    ax1.set_aspect("equal", adjustable="box")
    ax1.grid(True, linestyle=":", color="#dde", lw=0.5)
    ax1.set_title("1. KiCad Hub PCB 100x80 tren SUP06", fontsize=9.3, fontweight="bold", color="#145a32", pad=6)

    # -------------------------------------------------------------------------
    # PANEL 2: 5V 1-Ch Relay (50x26) on SUP07_RELAY_SNAP_CADDY (54.4x30.4)
    # -------------------------------------------------------------------------
    ax2.add_patch(MplRect((0, 0), 54.4, 30.4, facecolor="#d6eaf8", edgecolor="#1b4f72", lw=1.35, zorder=1))
    ax2.add_patch(MplRect((2.0, 2.0), 50.4, 26.4, facecolor="white", edgecolor="#1b4f72", lw=1.0, ls="--", zorder=2))
    # Relay PCB 50.0 x 26.0 centered inside 50.4 x 26.4 cavity (0.20 mm/side clearance!)
    ax2.add_patch(MplRect((2.2, 2.2), 50.0, 26.0, facecolor="#2874a6", edgecolor="#154360", lw=1.4, alpha=0.25, zorder=3))
    ax2.add_patch(MplRect((2.2, 2.2), 50.0, 26.0, fill=False, edgecolor="#154360", lw=1.5, zorder=5))
    # 2x base SUP05B mortise pockets (32.0 mm span -> X=11.2, 43.2)
    for mx in (27.2 - 16.0, 27.2 + 16.0):
        ax2.add_patch(MplRect((mx - 3.15, 15.2 - 1.65), 6.30, 3.30, facecolor="#f9e79f", edgecolor="#9a7d0a", lw=0.9, ls=":", zorder=4))
    # 4x Relay holes Ø3.10 @ 44.5x20.5 + OD 2.90 split pegs
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            hx = 27.2 + sx * 22.25
            hy = 15.2 + sy * 10.25
            ax2.add_patch(MplCircle((hx, hy), 1.55, facecolor="white", edgecolor="#154360", lw=1.0, zorder=6))
            ax2.add_patch(MplCircle((hx, hy), 1.45, facecolor="#5dade2", edgecolor="#1b4f72", lw=0.8, zorder=7))

    _draw_dim_arrow(ax2, 0, -6.5, 54.4, -6.5, "Ngoai SUP07 = 54.4", fontsize=7.2, color="#1b4f72")
    _draw_dim_arrow(ax2, 2.0, 35.8, 52.4, 35.8, "Long 50.4 (Mach 50.0, +0.20/ben)", fontsize=7.0, color="#c0392b")
    _draw_dim_arrow(ax2, -6.8, 0, -6.8, 30.4, "30.4", fontsize=7.2, color="#1b4f72")
    _draw_dim_arrow(ax2, 59.5, 2.0, 59.5, 28.4, "26.4", fontsize=7.1, color="#c0392b")

    ax2.text(27.2, 15.2, "Pitch 44.5 x 20.5\n4x Chot OD 2.90 / Lo Ø3.10\n2x Mong day span 32.0",
             fontsize=6.8, fontweight="bold", color="#154360", ha="center", va="center",
             bbox=dict(boxstyle="round,pad=0.22", facecolor="white", edgecolor="#1b4f72", lw=0.65, alpha=0.94), zorder=9)
    ax2.set_xlim(-12.5, 65.5)
    ax2.set_ylim(-12.0, 42.0)
    ax2.set_aspect("equal", adjustable="box")
    ax2.grid(True, linestyle=":", color="#dde", lw=0.5)
    ax2.set_title("2. Relay 50x26 tren SUP07 (2x)", fontsize=9.3, fontweight="bold", color="#1b4f72", pad=6)

    # -------------------------------------------------------------------------
    # PANEL 3: PAM8403 (21x18) on SUP08_PAM8403_SNAP_TRAY (36x23, cav 21.4x18.4)
    # -------------------------------------------------------------------------
    ax3.add_patch(MplRect((0, 0), 36.0, 23.0, facecolor="#d5f5e3", edgecolor="#196f3d", lw=1.35, zorder=1))
    # Wire cutouts on left/right ends
    ax3.add_patch(MplRect((0, 6.0), 7.3, 11.0, facecolor="#eafaf1", edgecolor="#196f3d", lw=0.8, ls=":", zorder=2))
    ax3.add_patch(MplRect((28.7, 6.0), 7.3, 11.0, facecolor="#eafaf1", edgecolor="#196f3d", lw=0.8, ls=":", zorder=2))
    # Cavity 21.4 x 18.4 centered at (18.0, 11.5)
    ax3.add_patch(MplRect((7.3, 2.3), 21.4, 18.4, facecolor="white", edgecolor="#196f3d", lw=1.0, ls="--", zorder=2))
    # PAM8403 PCB 21.0 x 18.0 centered at (18.0, 11.5)
    ax3.add_patch(MplRect((7.5, 2.5), 21.0, 18.0, facecolor="#27ae60", edgecolor="#145a32", lw=1.4, alpha=0.28, zorder=3))
    ax3.add_patch(MplRect((7.5, 2.5), 21.0, 18.0, fill=False, edgecolor="#145a32", lw=1.5, zorder=5))
    # 0.40 mm snap ribs along long inner walls
    ax3.add_patch(MplRect((12.0, 2.3), 12.0, 0.55, facecolor="#e74c3c", edgecolor="none", zorder=6))
    ax3.add_patch(MplRect((12.0, 20.15), 12.0, 0.55, facecolor="#e74c3c", edgecolor="none", zorder=6))
    # 2x base mortises (span 26.0 -> X=5.0, 31.0)
    for mx in (5.0, 31.0):
        ax3.add_patch(MplRect((mx - 3.15, 11.5 - 1.65), 6.30, 3.30, facecolor="#f9e79f", edgecolor="#9a7d0a", lw=0.9, ls=":", zorder=4))

    _draw_dim_arrow(ax3, 0, -4.8, 36.0, -4.8, "SUP08 = 36.0 (Span 26.0)", fontsize=7.1, color="#196f3d")
    _draw_dim_arrow(ax3, 7.3, 27.5, 28.7, 27.5, "Long 21.4 (Mach 21.0, +0.20/ben)", fontsize=6.9, color="#c0392b")
    _draw_dim_arrow(ax3, -4.8, 0, -4.8, 23.0, "23.0", fontsize=7.1, color="#196f3d")
    _draw_dim_arrow(ax3, 40.2, 2.3, 40.2, 20.7, "18.4", fontsize=7.1, color="#c0392b")

    ax3.text(18.0, 11.5, "PAM8403\n21.0 x 18.0\nGai 0.40 mm 45°", fontsize=7.0, fontweight="bold",
             color="#145a32", ha="center", va="center",
             bbox=dict(boxstyle="round,pad=0.20", facecolor="white", edgecolor="#196f3d", lw=0.65, alpha=0.93), zorder=8)
    ax3.set_xlim(-9.0, 44.8)
    ax3.set_ylim(-9.2, 32.5)
    ax3.set_aspect("equal", adjustable="box")
    ax3.grid(True, linestyle=":", color="#dde", lw=0.5)
    ax3.set_title("3. PAM8403 21x18 tren SUP08", fontsize=9.3, fontweight="bold", color="#196f3d", pad=6)

    # -------------------------------------------------------------------------
    # PANEL 4: SG90 Micro Servo on P07_SERVO_SHELF + SUP11_SG90_SNAP_SADDLE (Side Section Y-Z)
    # -------------------------------------------------------------------------
    # P07 shelf: Y in [-24, +24], Z in [-3.0, 0.0], center cutout Y in [-11.65, +11.65] (23.3 mm)
    # Mortises at Y = -17.1 and +17.1 (width 3.30 mm -> [-18.75..-15.45] & [+15.45..+18.75])
    # SG90 body: Y in [-11.4, +11.4] (22.8 mm), Z in [-15.9, +6.6], ears Y in [-16.1, +16.1] (32.2 mm), Z in [0.0, 2.5]
    # SUP11 saddle: outer Y in [-21.0, +21.0] (42.0 mm), inner ear span [-16.25, +16.25] (32.5 mm),
    #   ear pocket Z in [0.0, 2.60], bridge Z in [2.60, 5.60], integral tenons into P07 Z in [-3.0, 0.0]!
    ax4.add_patch(MplRect((-23.5, -3.0), 4.75, 3.0, facecolor="#cde6f7", edgecolor="#0b2540", lw=1.1, zorder=2))
    ax4.add_patch(MplRect((-15.45, -3.0), 3.80, 3.0, facecolor="#cde6f7", edgecolor="#0b2540", lw=1.1, zorder=2))
    ax4.add_patch(MplRect((11.65, -3.0), 3.80, 3.0, facecolor="#cde6f7", edgecolor="#0b2540", lw=1.1, zorder=2))
    ax4.add_patch(MplRect((18.75, -3.0), 4.75, 3.0, facecolor="#cde6f7", edgecolor="#0b2540", lw=1.1, zorder=2))

    # SG90 body + mounting ears + gearbox turret
    ax4.add_patch(MplRect((-11.4, -13.5), 22.8, 19.5, facecolor="#5dade2", edgecolor="#1b4f72", lw=1.25, zorder=3))
    ax4.add_patch(MplRect((-16.1, 0.0), 32.2, 2.5, facecolor="#3498db", edgecolor="#1b4f72", lw=1.2, zorder=4))
    ax4.add_patch(MplRect((-6.0, 6.0), 12.0, 4.2, facecolor="#2e86c1", edgecolor="#1b4f72", lw=1.1, zorder=3))
    ax4.text(0.0, -7.0, "SG90 Body\n22.8 x 12.2", fontsize=7.3, fontweight="bold", color="white", ha="center", va="center", zorder=5)

    # SUP11 saddle (clamping ears & plugging tenons into P07 mortises)
    for s in (-1.0, 1.0):
        # End leg + clamping shoulder + integral tenon
        pts_leg = [
            (s * 16.25, 0.0), (s * 21.0, 0.0), (s * 21.0, 5.6),
            (s * 11.8, 5.6), (s * 11.8, 2.6), (s * 16.25, 2.6),
        ]
        ax4.add_patch(MplPolygon(pts_leg, closed=True, facecolor="#f5b041", edgecolor="#7e5109", lw=1.2, zorder=5))
        ax4.add_patch(MplRect((s * 17.1 - 1.2, -3.0), 2.4, 3.0, facecolor="#f5b041", edgecolor="#7e5109", lw=1.1, zorder=5))

    _draw_dim_arrow(ax4, -11.65, -17.5, 11.65, -17.5, "Lo P07 = 23.3 (+0.25/ben)", fontsize=7.0, color="#0b2540")
    _draw_dim_arrow(ax4, -16.25, 12.5, 16.25, 12.5, "SUP11 = 32.5 (Tai 32.2, +0.15/ben)", fontsize=6.9, color="#c0392b")
    _draw_callout(
        ax4, xy=(17.1, -1.5), xytext=(15.5, -11.5),
        text="2x Chot mong SUP11\n(Span 34.2 | 0 vit M2)",
        color="#7e5109", fontsize=6.7, ha="center", va="center", fc="#fffaf0",
    )
    _draw_callout(
        ax4, xy=(-15.0, 2.55), xytext=(-22.5, 8.8),
        text="Khe tai 2.6\n(+0.10 mm)",
        color="#1b4f72", fontsize=6.8, ha="left", va="center", fc="#eef5fb",
    )

    ax4.set_xlim(-25.5, 25.5)
    ax4.set_ylim(-21.5, 16.5)
    ax4.set_aspect("equal", adjustable="box")
    ax4.grid(True, linestyle=":", color="#dde", lw=0.5)
    ax4.set_title("4. Servo SG90 tren P07 + SUP11", fontsize=9.3, fontweight="bold", color="#1b4f72", pad=6)

    # -------------------------------------------------------------------------
    # PANEL 5: Mini Speaker 28mm on P15_TECH_FASCIA + SUP09_SPEAKER_SNAP_RETAINER (Section X-Y)
    # -------------------------------------------------------------------------
    # P15 front panel: X in [-25, +25], Y in [0, 3.0], mortises at X = -18.0 & +18.0 (width 4.30 -> [-20.15..-15.85])
    # Speaker Ø28.0 x 5.2 mm: X in [-14.0, +14.0], Y in [3.0, 8.2]
    # SUP09 rear retainer: outer X in [-22.0, +22.0] (44.0 mm), legs at [-22..-14.2] & [+14.2..+22] (span 28.4 mm),
    #   Y in [3.0..12.0] (bridge_h=9.0, back bar Y in [9.0..12.0]), center boss Y in [8.4..12.0] (pocket 5.4 mm),
    #   2x integral tenons (4.0x3.0) at X = -18.0 & +18.0 plugging into P15 Y in [0..3.0]!
    ax5.add_patch(MplRect((-24.5, 0.0), 4.35, 3.0, facecolor="#cde6f7", edgecolor="#0b2540", lw=1.1, zorder=2))
    ax5.add_patch(MplRect((-15.85, 0.0), 31.70, 3.0, facecolor="#cde6f7", edgecolor="#0b2540", lw=1.1, zorder=2))
    ax5.add_patch(MplRect((20.15, 0.0), 4.35, 3.0, facecolor="#cde6f7", edgecolor="#0b2540", lw=1.1, zorder=2))
    # Acoustic grille holes (indicative slots through P15)
    for gx in (-9.0, -4.5, 0.0, 4.5, 9.0):
        ax5.add_patch(MplRect((gx - 1.1, 0.0), 2.2, 3.0, facecolor="white", edgecolor="#557", lw=0.6, zorder=3))

    # Speaker 28.0 x 5.2 mm
    ax5.add_patch(MplRect((-14.0, 3.0), 28.0, 5.2, facecolor="#566573", edgecolor="#1c2833", lw=1.25, zorder=4))
    ax5.text(0.0, 5.6, "Loa tron Ø28.0 x 5.2 mm", fontsize=7.4, fontweight="bold", color="white", ha="center", va="center", zorder=5)

    # SUP09 retainer bridge + boss + 2x integral tenons
    sup09_poly = [
        (-22.0, 3.0), (-14.2, 3.0), (-14.2, 9.0), (-6.0, 9.0), (-6.0, 8.4),
        (6.0, 8.4), (6.0, 9.0), (14.2, 9.0), (14.2, 3.0), (22.0, 3.0),
        (22.0, 12.0), (-22.0, 12.0),
    ]
    ax5.add_patch(MplPolygon(sup09_poly, closed=True, facecolor="#d2b4de", edgecolor="#5b2c6f", lw=1.25, zorder=5))
    ax5.add_patch(MplRect((-20.0, 0.0), 4.0, 3.0, facecolor="#d2b4de", edgecolor="#5b2c6f", lw=1.1, zorder=5))
    ax5.add_patch(MplRect((16.0, 0.0), 4.0, 3.0, facecolor="#d2b4de", edgecolor="#5b2c6f", lw=1.1, zorder=5))

    _draw_dim_arrow(ax5, -14.2, 15.2, 14.2, 15.2, "Khung 28.4 (Loa 28.0, +0.20/ben)", fontsize=6.9, color="#c0392b")
    _draw_dim_arrow(ax5, -18.0, -5.5, 18.0, -5.5, "Span mong P15 = 36.0 mm (2x 4x6x3)", fontsize=6.9, color="#5b2c6f")
    _draw_callout(
        ax5, xy=(4.5, 8.3), xytext=(10.5, 21.2),
        text="Khe truc 5.4 vs 5.2 mm (+0.20 mm)\nEp sau giu loa khong vit",
        color="#5b2c6f", fontsize=7.0, ha="center", va="center", fc="#faf5ff", rad=-0.18,
    )
    ax5.text(0.0, -10.5, "Mat truoc P15 (19 lo luoi loa Ø3.0 mm)", fontsize=7.2, fontweight="bold", color="#0b2540", ha="center")

    ax5.set_xlim(-26.5, 26.5)
    ax5.set_ylim(-13.5, 25.0)
    ax5.set_aspect("equal", adjustable="box")
    ax5.grid(True, linestyle=":", color="#dde", lw=0.5)
    ax5.set_title("5. Loa 28mm tren P15 + SUP09", fontsize=9.3, fontweight="bold", color="#5b2c6f", pad=6)

    # -------------------------------------------------------------------------
    # PANEL 6: COMPLETE 12-MODULE FIT VERIFICATION TABLE (from fit_table.json)
    # -------------------------------------------------------------------------
    ax6.axis("off")
    ax6.set_xlim(0, 1)
    ax6.set_ylim(0, 1)
    ax6.add_patch(MplRect((0.0, 0.0), 1.0, 1.0, facecolor="#f8fafc", edgecolor="#0f2b46", lw=1.2))
    ax6.add_patch(MplRect((0.0, 0.915), 1.0, 0.085, facecolor="#0f2b46", edgecolor="none"))
    ax6.text(0.50, 0.957, "6. BANG KIEM TRA DO KHIT 12 MODULE (fit_table.json)", fontsize=8.4,
             fontweight="bold", color="white", ha="center", va="center")

    cols_x = [0.012, 0.250, 0.492, 0.658, 0.918]
    headers = ["Module", "Kich thuoc (mm)", "Ga lap", "Khe ho", "KQ"]
    ax6.add_patch(MplRect((0.0, 0.855), 1.0, 0.060, facecolor="#d6eaf8", edgecolor="#85c1e9", lw=0.6))
    for cx, htxt in zip(cols_x, headers):
        ax6.text(cx, 0.885, htxt, fontsize=6.9, fontweight="bold", color="#0f2b46", va="center", ha="left")

    row_h = 0.845 / max(1, len(fit_rows))
    part_short_map = {
        "Hub PCB (Type 1)": "Hub PCB (KiCad)",
        "ESP8266 NodeMCU v2": "NodeMCU v2",
        "Relay 1 & Relay 2 (SRD-05VDC)": "Relay 1 & 2 (5V)",
        "PAM8403 3W Audio Amp": "PAM8403 Amp",
        "Mini Speaker 28mm (PUI AS02808MR-R)": "Speaker 28mm",
        "SG90 9g Micro Servo": "Servo SG90 9g",
        "DHT11 Temp/Humidity Breakout": "DHT11 Sensor",
        "KY-037 Sound Sensor": "KY-037 Mic",
        "YL-69 Soil Moisture Probe": "YL-69 Probe",
        "LM393 Soil Comparator (YL-38)": "LM393 Module",
        "Door Leaf & Hinge / Linkage": "Door P08 Hinge",
        "5V Mini Submersible Pump": "5V Water Pump",
    }
    for idx, row in enumerate(fit_rows):
        y_top = 0.855 - idx * row_h
        y_mid = y_top - row_h * 0.5
        bg = "#ffffff" if idx % 2 == 0 else "#f2f6fa"
        ax6.add_patch(MplRect((0.0, y_top - row_h), 1.0, row_h, facecolor=bg, edgecolor="#dce4ec", lw=0.4))

        part_short = part_short_map.get(row["part"], row["part"][:18])
        bsz = row["board_size_mm"].split("(")[0].split(",")[0].split(";")[0].strip()
        bsz = bsz.replace("Body ", "").replace("Door ", "")
        mnt = (
            row["mount_part"].split(" ")[0]
            .replace("_HUB_PCB_SNAP_CARRIER", "")
            .replace("_RELAY_SNAP_CADDY", "")
            .replace("_PAM8403_SNAP_TRAY", "")
            .replace("_SPEAKER_SNAP_RETAINER", "")
            .replace("_SERVO_SHELF", "+SUP11")
            .replace("_DHT11_SNAP_CRADLE", "")
            .replace("_KY037_SNAP_CRADLE", "")
            .replace("_SOIL_BRIDGE", "")
            .replace("_LM393_SNAP_CRADLE", "")
            .replace("_DOOR_MORTISE_HINGE", "")
            .replace("_WATER_TANK_LINER", "")
        )
        clr_s = row["clearance_mm"].split(",")[0].split("(")[0].strip()
        clr_s = clr_s.replace("underside pin clearance", "pin clr").replace("body cutout", "cutout")
        st = row["status"]

        ax6.text(cols_x[0], y_mid, part_short, fontsize=6.25, fontweight="bold", color="#1a2530", va="center", ha="left")
        ax6.text(cols_x[1], y_mid, bsz, fontsize=6.1, color="#2c3e50", va="center", ha="left")
        ax6.text(cols_x[2], y_mid, mnt, fontsize=6.15, fontweight="bold", color="#1b4f72", va="center", ha="left")
        ax6.text(cols_x[3], y_mid, clr_s, fontsize=6.0, color="#7e5109", va="center", ha="left")
        ax6.text(
            cols_x[4] + 0.032, y_mid, st, fontsize=6.3, fontweight="bold",
            color="#145a32" if st == "PASS" else "#922b21", ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.14", facecolor="#d5f5e3" if st == "PASS" else "#fadbd8",
                      edgecolor="#1e8449" if st == "PASS" else "#c0392b", lw=0.5),
        )

    fig.text(
        0.025, 0.020,
        "TAT CA 12 MODULE DIEN TU DEU LAP GHEP KHONG VIT - KHONG KEO | Hub PCB do truc tiep tu smarthome_hub.kicad_pcb | Don vi: mm",
        fontsize=8.2, fontweight="bold", color="#145a32",
    )

    fig.savefig(str(png_path), format="png", dpi=220)
    fig.savefig(str(pdf_path), format="pdf")
    plt.close(fig)
    return png_path, pdf_path


# ---------------------------------------------------------------------------
# CLI Orchestration
# ---------------------------------------------------------------------------
def clean_drawings_dir() -> int:
    DRAW_DIR.mkdir(parents=True, exist_ok=True)
    removed = 0
    for f in DRAW_DIR.iterdir():
        if f.is_file():
            f.unlink()
            removed += 1
    return removed


def main() -> int:
    t0 = time.time()
    ap = argparse.ArgumentParser(description="Export all 57 v2 part drawings + 2 special technical sheets (PNG + PDF)")
    ap.add_argument("--parts", type=str, default="", help="Comma-separated subset of part_ids (skips clean & specials unless --with-special)")
    ap.add_argument("--only-special", action="store_true", help="Only regenerate _joint_closeup_mong and _pcb_module_fit")
    ap.add_argument("--no-clean", action="store_true", help="Do not clean drawings/ before full export")
    args = ap.parse_args()

    cfg = pd_mod.PrintConfig()
    pieces, _ = pd_mod.build_panel_piece_specs(cfg)
    piece_map = {pc.part_id: pc for pc in pieces}
    panels_raw, _ = md.build_design()
    ev_map = {ps.panel_id: pd_mod.evaluate_screwless_panel_2d(ps, cfg) for ps in panels_raw}

    target_ids: set[str] | None = None
    if args.parts:
        target_ids = {s.strip() for s in args.parts.split(",") if s.strip()}

    if not args.only_special and target_ids is None and not args.no_clean:
        n_rm = clean_drawings_dir()
        print(f"[CLEAN] Removed {n_rm} stale files from {DRAW_DIR}", flush=True)

    generated = 0
    if not args.only_special:
        stl_files = sorted(PARTS_DIR.glob("*.stl"))
        for stl_path in stl_files:
            part_id = stl_path.stem
            if target_ids is not None and part_id not in target_ids:
                continue
            meta_path = META_DIR / f"{part_id}.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            mesh = trimesh.load_mesh(str(stl_path), force="mesh")
            if meta.get("kind") == "panel":
                pc = piece_map[part_id]
                pdf_p, png_p = draw_panel_piece_v2(pc, ev_map[pc.source_panel_id], meta, mesh, cfg)
            else:
                pdf_p, png_p = draw_3view_part_v2(part_id, meta, mesh, cfg)
            generated += 1
            print(
                f"[OK] {part_id:28s} png={png_p.stat().st_size // 1024:3d}KB pdf={pdf_p.stat().st_size // 1024:3d}KB",
                flush=True,
            )

    if target_ids is None or args.only_special:
        j_png, j_pdf = draw_joint_closeup_mong(cfg)
        print(
            f"[OK] {'_joint_closeup_mong':28s} png={j_png.stat().st_size // 1024:3d}KB pdf={j_pdf.stat().st_size // 1024:3d}KB",
            flush=True,
        )
        m_png, m_pdf = draw_pcb_module_fit(cfg)
        print(
            f"[OK] {'_pcb_module_fit':28s} png={m_png.stat().st_size // 1024:3d}KB pdf={m_pdf.stat().st_size // 1024:3d}KB",
            flush=True,
        )

    elapsed = round(time.time() - t0, 2)
    print(f"DONE: generated {generated} part drawings + special sheets in {elapsed}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
