"""Export 1:1 Laser-Cut DXFs, Dimensioned Panel Drawings (PDF + PNG + SVG),
Holes Table CSV, 1:1 A3 & A4 Sheet Nesting PDFs/DXFs/PNGs (plus A4 Tiled Oversized 1:1 PDF),
Exploded Assembly, MICA_PANELS.md, and Run Full MICA2 Automated Verification Suite.

Run with system Python (requires ezdxf, matplotlib, numpy, Pillow):
    C:\\Users\\LENOVO\\miniconda3\\python.exe hardware/mica/export_drawings_and_verify.py
"""

from __future__ import annotations

import csv
import json
import math
import pathlib
import sys
from typing import Any

import ezdxf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Circle as MplCircle, FancyBboxPatch, Polygon as MplPolygon, Rectangle as MplRect
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import mica_design as md

OUT_ROOT = REPO_ROOT / "docs" / "phan_cung" / "mica"
DXF_DIR = OUT_ROOT / "panels_dxf"
DRAW_DIR = OUT_ROOT / "drawings"
HOLES_CSV_PATH = OUT_ROOT / "holes_table.csv"
FC_GEOM_JSON = SCRIPT_DIR / "panel_geometry_from_freecad.json"
FC_COLLISION_JSON = SCRIPT_DIR / "joint_collision_check.json"
FC_RECOMPUTE_LOG = SCRIPT_DIR / "freecad_recompute_check.log"

DEFAULT_T_MM = 3.0
DEFAULT_TAB_CLR = 0.25
MM_PER_INCH = 25.4


# ============================================================================
# 1. DXF EXPORT (1:1 mm, Closed LWPOLYLINE + CIRCLE, Laser-Ready)
# ============================================================================
def export_panel_dxf(ev: dict[str, Any], out_path: pathlib.Path) -> None:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4   # Millimeters
    doc.header["$MEASUREMENT"] = 1  # Metric
    msp = doc.modelspace()

    doc.layers.add("CUT_OUTER", color=1)   # Red
    doc.layers.add("CUT_INNER", color=5)   # Blue
    doc.layers.add("ENGRAVE_ID", color=3)  # Green

    # Single closed outer contour
    msp.add_lwpolyline(ev["outer_poly"], close=True, dxfattribs={"layer": "CUT_OUTER"})

    # Closed interior rectangular slots/cutouts/windows
    for r in ev["inner_rects"]:
        u0, v0, du, dv = r["u0"], r["v0"], r["du"], r["dv"]
        pts = [(u0, v0), (u0 + du, v0), (u0 + du, v0 + dv), (u0, v0 + dv)]
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "CUT_INNER"})

    # Circular holes
    for c in ev["circles"]:
        msp.add_circle((c["cx"], c["cy"]), radius=c["dia"] / 2.0, dxfattribs={"layer": "CUT_INNER"})

    # Non-cut engraving label positioned inside panel margin
    lbl = f"{ev['panel_id']} (T={ev['T_mm']:.0f}mm, clr={ev['tab_clr']:.2f})"
    txt_h = min(4.0, max(2.2, min(ev["width"], ev["height"]) * 0.045))
    tx = min(10.0, ev["width"] * 0.12)
    ty = min(8.0, ev["height"] * 0.12)
    msp.add_text(
        lbl,
        dxfattribs={
            "layer": "ENGRAVE_ID",
            "height": round(txt_h, 2),
            "insert": (round(tx, 2), round(ty, 2)),
        },
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(out_path))


# ============================================================================
# 2. HOLES TABLE CSV (panel,id,x,y,diameter,purpose)
# ============================================================================
def export_holes_csv(evals: list[dict[str, Any]], out_csv: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["panel", "id", "x", "y", "diameter", "purpose"])
        for ev in evals:
            for c in ev["circles"]:
                row = {
                    "panel": ev["panel_id"],
                    "id": c["name"],
                    "x": round(float(c["cx"]), 3),
                    "y": round(float(c["cy"]), 3),
                    "diameter": round(float(c["dia"]), 3),
                    "purpose": c["note"],
                }
                rows.append(row)
                writer.writerow([
                    row["panel"],
                    row["id"],
                    f"{row['x']:.3f}",
                    f"{row['y']:.3f}",
                    f"{row['diameter']:.3f}",
                    row["purpose"],
                ])
    return rows


# ============================================================================
# 3. DIMENSIONED ENGINEERING DRAWINGS (PDF + PNG + SVG)
# ============================================================================
def _draw_dim_arrow(
    ax,
    p1: tuple[float, float],
    p2: tuple[float, float],
    text: str,
    offset_xy: tuple[float, float] = (0.0, 0.0),
    fontsize: float = 8.0,
    color: str = "#1a365d",
    ext_lines: bool = True,
    text_offset: tuple[float, float] = (0.0, 0.0),
) -> None:
    x1, y1 = p1
    x2, y2 = p2
    ox, oy = offset_xy
    ax.annotate(
        "",
        xy=(x2 + ox, y2 + oy),
        xytext=(x1 + ox, y1 + oy),
        arrowprops=dict(arrowstyle="<->", color=color, lw=1.05, shrinkA=0, shrinkB=0),
        zorder=8,
    )
    if ext_lines and (abs(ox) > 1e-3 or abs(oy) > 1e-3):
        ax.plot([x1, x1 + ox * 1.12], [y1, y1 + oy * 1.12], color=color, lw=0.6, alpha=0.75, zorder=7)
        ax.plot([x2, x2 + ox * 1.12], [y2, y2 + oy * 1.12], color=color, lw=0.6, alpha=0.75, zorder=7)
    mx = (x1 + x2) / 2.0 + ox + text_offset[0]
    my = (y1 + y2) / 2.0 + oy + text_offset[1]
    rot = 90 if abs(x2 - x1) < 1e-3 else 0
    ax.text(
        mx,
        my,
        text,
        ha="center",
        va="center",
        rotation=rot,
        fontsize=fontsize,
        fontweight="bold",
        color=color,
        bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="none", alpha=0.92),
        zorder=10,
    )


def _panel_joint_summary(panel_id: str, joints: list[md.JointPair], params: dict[str, float]) -> str:
    tabs = [j for j in joints if j.tab_panel == panel_id]
    slots = [j for j in joints if j.slot_panel == panel_id]
    parts: list[str] = []
    if tabs:
        lens = sorted({round(md.eval_expr(j.tab_len_expr, params), 2) for j in tabs})
        deps = sorted({round(md.eval_expr(j.tab_depth_expr, params), 2) for j in tabs})
        parts.append(f"Tabs: {len(tabs)}x ({'/'.join(f'{v:g}' for v in lens)} x {'/'.join(f'{v:g}' for v in deps)} mm)")
    if slots:
        lens = sorted({round(md.eval_expr(j.slot_len_expr, params), 2) for j in slots})
        ws = sorted({round(md.eval_expr(j.slot_width_expr, params), 2) for j in slots})
        parts.append(f"Slots/Notches: {len(slots)}x ({'/'.join(f'{v:g}' for v in lens)} x {'/'.join(f'{v:g}' for v in ws)} mm)")
    if not parts:
        parts.append("Standalone bolted/hinged panel (no finger tabs)")
    return "  |  ".join(parts)


def _render_p16_pcb_plate_special(
    ax,
    ev: dict[str, Any],
    feat_rows: list[tuple[str, str, str, str, str]],
) -> None:
    """High-clarity specialized blueprint overlay for P16_PCB_PLATE (130x110 mm, 90x70 M3, 15mm margins)."""
    W, H = ev["width"], ev["height"]
    # Outer plate polygon
    ax.add_patch(MplPolygon(
        ev["outer_poly"], closed=True, facecolor="#e6f5fb", edgecolor="#0c4a6e", lw=1.8, zorder=2
    ))

    # Dashed 100.0 x 80.0 mm Hub PCB outline centered at (65, 55) => [15..115] x [15..95]
    ax.add_patch(MplRect(
        (15.0, 15.0), 100.0, 80.0,
        facecolor="#dcfce7", edgecolor="#15803d", lw=1.8, ls="--", alpha=0.55, zorder=3
    ))
    ax.add_patch(MplRect(
        (15.0, 15.0), 100.0, 80.0,
        facecolor="none", edgecolor="#15803d", lw=1.8, ls="--", zorder=4
    ))
    ax.text(
        59.0, 62.0, "HUB PCB OUTLINE\n100.0 x 80.0 x 1.6 mm",
        ha="center", va="center", fontsize=8.4, fontweight="bold", color="#14532d",
        bbox=dict(boxstyle="round,pad=0.24", facecolor="#f0fdf4", edgecolor="#15803d", lw=0.9, alpha=0.95),
        zorder=6,
    )
    ax.text(
        59.0, 47.0, "5.0 mm corner inset -> 90.0 x 70.0 mm M3\n15.0 mm free margin all 4 sides (>= 10 mm)",
        ha="center", va="center", fontsize=6.7, color="#166534", zorder=6,
    )

    # Dashed construction box connecting 90x70 PCB holes & 116x96 plate holes
    ax.add_patch(MplRect((20.0, 20.0), 90.0, 70.0, facecolor="none", edgecolor="#dc2626", lw=0.9, ls=":", zorder=4))
    ax.add_patch(MplRect((7.0, 7.0), 116.0, 96.0, facecolor="none", edgecolor="#1d4ed8", lw=0.7, ls=":", zorder=3))

    # Draw holes clearly distinguished: inner PCB M3 (red) vs outer plate-to-base M3 (blue)
    pcb_idx = 0
    plt_idx = 0
    for c in ev["circles"]:
        is_pcb = c["name"].startswith("PCB_H")
        if is_pcb:
            pcb_idx += 1
            tag = f"H{pcb_idx}"
            col = "#dc2626"
            bg = "#fef2f2"
        else:
            plt_idx += 1
            tag = f"C{plt_idx}"
            col = "#1d4ed8"
            bg = "#eff6ff"

        ax.add_patch(MplCircle((c["cx"], c["cy"]), c["dia"] / 2.0, facecolor="white", edgecolor=col, lw=1.6, zorder=6))
        cr = 3.6
        ax.plot([c["cx"] - cr, c["cx"] + cr], [c["cy"], c["cy"]], color=col, lw=0.75, ls="--", zorder=7)
        ax.plot([c["cx"], c["cx"]], [c["cy"] - cr, c["cy"] + cr], color=col, lw=0.75, ls="--", zorder=7)

        feat_rows.append((
            tag,
            c["name"],
            f"Dia {c['dia']:.2f}",
            f"{c['cx']:.2f}",
            f"{c['cy']:.2f}",
        ))

        # Place crisp non-overlapping callout per hole
        if is_pcb:
            tx = 35.0 if c["cx"] < 65 else 92.0
            ty = 27.5 if c["cy"] < 55 else 82.5
            lbl = f"{tag} Ø3.40\n({c['cx']:.0f},{c['cy']:.0f})"
        else:
            tx = 29.0 if c["cx"] < 65 else 101.0
            ty = 7.0 if c["cy"] < 55 else 103.0
            lbl = f"{tag} Ø3.40 ({c['cx']:.0f},{c['cy']:.0f})"
        ax.annotate(
            lbl,
            xy=(c["cx"], c["cy"]),
            xytext=(tx, ty),
            fontsize=6.5,
            fontweight="bold",
            color=col,
            ha="center",
            va="center",
            bbox=dict(boxstyle="round,pad=0.15", facecolor=bg, edgecolor=col, lw=0.7, alpha=0.95),
            arrowprops=dict(arrowstyle="-", color=col, lw=0.7, shrinkA=2, shrinkB=2),
            zorder=11,
        )

    # Explicit 90.0 x 70.0 mm PCB hole pattern dimension arrows
    _draw_dim_arrow(ax, (20.0, 20.0), (110.0, 20.0), "90.00 mm (PCB M3 X)", offset_xy=(0.0, 15.0), fontsize=7.8, color="#b91c1c", ext_lines=False)
    _draw_dim_arrow(ax, (110.0, 20.0), (110.0, 90.0), "70.00 mm (PCB M3 Y)", offset_xy=(-6.5, 0.0), fontsize=7.6, color="#b91c1c", ext_lines=False)

    # Explicit 15.0 mm free margin arrows on all 4 sides
    _draw_dim_arrow(ax, (0.0, 55.0), (15.0, 55.0), "15.0", offset_xy=(0.0, 0.0), fontsize=7.0, color="#15803d", ext_lines=False, text_offset=(0.0, 4.8))
    _draw_dim_arrow(ax, (115.0, 55.0), (130.0, 55.0), "15.0", offset_xy=(0.0, 0.0), fontsize=7.0, color="#15803d", ext_lines=False, text_offset=(0.0, 4.8))
    _draw_dim_arrow(ax, (65.0, 0.0), (65.0, 15.0), "15.0", offset_xy=(0.0, 0.0), fontsize=7.0, color="#15803d", ext_lines=False, text_offset=(9.0, 0.0))
    _draw_dim_arrow(ax, (65.0, 95.0), (65.0, 110.0), "15.0", offset_xy=(0.0, 0.0), fontsize=7.0, color="#15803d", ext_lines=False, text_offset=(9.0, 0.0))

    # Explicit 116.0 x 96.0 mm outer standoff pattern reference
    _draw_dim_arrow(ax, (7.0, 103.0), (123.0, 103.0), "116.00 mm (Base Standoff X)", offset_xy=(0.0, 12.0), fontsize=7.4, color="#1d4ed8", ext_lines=True)
    _draw_dim_arrow(ax, (123.0, 7.0), (123.0, 103.0), "96.00 mm (Base Y)", offset_xy=(13.5, 0.0), fontsize=7.4, color="#1d4ed8", ext_lines=True)

    # Overall plate dimensions pushed cleanly outside inner dims
    _draw_dim_arrow(ax, (0.0, H), (W, H), f"L = {W:.2f} mm", offset_xy=(0.0, 22.0), fontsize=9.0, color="#0f2942")
    _draw_dim_arrow(ax, (0.0, 0.0), (0.0, H), f"H = {H:.2f} mm", offset_xy=(-21.0, 0.0), fontsize=9.0, color="#0f2942")


def render_panel_drawing(
    ev: dict[str, Any],
    joints: list[md.JointPair],
    params: dict[str, float],
    out_pdf: pathlib.Path,
    out_png: pathlib.Path,
    out_svg: pathlib.Path,
) -> None:
    """Render a crisp A4-landscape engineering blueprint with datum table (PDF + PNG + SVG)."""
    dpi = 220 if ev["panel_id"] == "P16_PCB_PLATE" else 200
    fig = plt.figure(figsize=(11.69, 8.27), dpi=dpi, facecolor="white")

    # Outer A4 border frame
    ax_frame = fig.add_axes([0.015, 0.02, 0.97, 0.96])
    ax_frame.set_xlim(0, 100)
    ax_frame.set_ylim(0, 100)
    ax_frame.axis("off")
    ax_frame.add_patch(MplRect((0, 0), 100, 100, fill=False, edgecolor="#1b2a4a", lw=1.6))

    # Top header banner
    ax_frame.add_patch(MplRect((0, 93.2), 100, 6.8, facecolor="#eff6ff", edgecolor="#1b2a4a", lw=1.1))
    ax_frame.text(
        1.2, 96.6,
        f"{ev['panel_id']}  —  {ev['name'].upper()}",
        fontsize=10.2, fontweight="bold", color="#0f2942", va="center",
    )
    ax_frame.text(
        98.8, 96.6,
        f"SIZE: {ev['width']:.2f} x {ev['height']:.2f} mm  |  T = {ev['T_mm']:.1f} mm  |  tab_clr = {ev['tab_clr']:.2f} mm  |  QTY: {ev['qty']}",
        fontsize=8.0, fontweight="bold", color="#1e4e79", va="center", ha="right",
    )

    # Left 62%: Blueprint geometry axes (extra left/bottom breathing room so axis labels stay crisp)
    ax = fig.add_axes([0.068, 0.195, 0.558, 0.700])
    ax.set_aspect("equal", adjustable="box")
    ax.set_facecolor("#fafdff")

    W, H = ev["width"], ev["height"]
    if ev["panel_id"] == "P16_PCB_PLATE":
        ax.set_xlim(-28.0, W + 24.0)
        ax.set_ylim(-14.0, H + 28.0)
    else:
        pad_x = max(14.0, W * 0.16)
        pad_y = max(14.0, H * 0.22)
        ax.set_xlim(-pad_x, W + pad_x * 0.72)
        ax.set_ylim(-pad_y, H + pad_y * 0.75)

    # Engineering grid
    step = 20.0 if max(W, H) > 150 else 10.0
    ax.set_xticks(np.arange(0, W + step, step))
    ax.set_yticks(np.arange(0, H + step, step))
    ax.grid(True, linestyle=":", linewidth=0.5, color="#cbd5e1", zorder=0)
    ax.tick_params(labelsize=7.5, colors="#475569")
    ax.set_xlabel("X from Bottom-Left Datum (mm)", fontsize=8.5, fontweight="bold", color="#1e293b")
    ax.set_ylabel("Y from Bottom-Left Datum (mm)", fontsize=8.5, fontweight="bold", color="#1e293b")

    feat_rows: list[tuple[str, str, str, str, str]] = []

    if ev["panel_id"] == "P16_PCB_PLATE":
        _render_p16_pcb_plate_special(ax, ev, feat_rows)
        # Datum origin marker
        ax.plot(0, 0, marker="o", markersize=6.0, color="#dc2626", zorder=12)
        ax.text(-2.0, -8.0, "DATUM (0, 0)", fontsize=7.4, fontweight="bold", color="#b91c1c", ha="right", va="top", zorder=12)
    else:
        # Standard panel polygon
        ax.add_patch(MplPolygon(
            ev["outer_poly"], closed=True, facecolor="#dff1fc", edgecolor="#0c4a6e", lw=1.6, zorder=2
        ))
        label_points: list[tuple[float, float, str, str]] = []

        def _fmt_c(val: float) -> str:
            return f"{val:.3f}" if abs(val * 100.0 - round(val * 100.0)) > 1e-4 else f"{val:.2f}"

        for idx, r in enumerate(ev["inner_rects"], 1):
            tag = f"S{idx}" if r["kind"] == "slot" else f"R{idx}"
            col = "#b91c1c" if r["kind"] == "slot" else "#0369a1"
            ax.add_patch(MplRect(
                (r["u0"], r["v0"]), r["du"], r["dv"],
                facecolor="white", edgecolor=col, lw=1.2, zorder=4
            ))
            ax.plot([r["cx"] - 2.5, r["cx"] + 2.5], [r["cy"], r["cy"]], color=col, lw=0.6, ls="--", zorder=5)
            ax.plot([r["cx"], r["cx"]], [r["cy"] - 2.5, r["cy"] + 2.5], color=col, lw=0.6, ls="--", zorder=5)
            sz_txt = f"{r['du']:.1f}x{r['dv']:.1f}" if (r["du"] >= 100 or r["dv"] >= 100) else f"{r['du']:.2f}x{r['dv']:.2f}"
            feat_rows.append((tag, r["name"][:18], sz_txt, _fmt_c(r["cx"]), _fmt_c(r["cy"])))
            label_points.append((r["cx"], r["cy"], tag, col))

        grille_circles = [c for c in ev["circles"] if c["kind"] == "grille"]
        other_circles = [c for c in ev["circles"] if c["kind"] != "grille"]

        for idx, c in enumerate(other_circles, 1):
            tag = f"H{idx}"
            col = "#dc2626"
            ax.add_patch(MplCircle(
                (c["cx"], c["cy"]), c["dia"] / 2.0,
                facecolor="white", edgecolor=col, lw=1.25, zorder=4
            ))
            cr = max(2.2, c["dia"] * 0.75)
            ax.plot([c["cx"] - cr, c["cx"] + cr], [c["cy"], c["cy"]], color=col, lw=0.6, ls="--", zorder=5)
            ax.plot([c["cx"], c["cx"]], [c["cy"] - cr, c["cy"] + cr], color=col, lw=0.6, ls="--", zorder=5)
            feat_rows.append((tag, c["name"][:20], f"Dia {c['dia']:.2f}", _fmt_c(c["cx"]), _fmt_c(c["cy"])))
            label_points.append((c["cx"], c["cy"], f"{tag} (Ø{c['dia']:.1f})", col))

        if grille_circles:
            gc0 = grille_circles[0]
            for gidx, c in enumerate(grille_circles, 1):
                ax.add_patch(MplCircle(
                    (c["cx"], c["cy"]), c["dia"] / 2.0,
                    facecolor="white", edgecolor="#7c3aed", lw=1.0, zorder=4
                ))
                feat_rows.append((f"G{gidx}", c["name"][:20], f"Dia {c['dia']:.2f}", _fmt_c(c["cx"]), _fmt_c(c["cy"])))
            ax.add_patch(MplCircle(
                (gc0["cx"], gc0["cy"]), 14.0,
                facecolor="none", edgecolor="#7c3aed", lw=0.85, ls=":", zorder=3
            ))
            label_points.append((gc0["cx"], gc0["cy"] + 16.5, f"G1..G{len(grille_circles)}: 19x Ø{gc0['dia']:.1f} (R6/R12)", "#6d28d9"))

        # Custom non-overlapping offsets for tight-feature panels (P05_WALL_FRONT, P15_TECH_FASCIA)
        custom_offsets = {
            ("P05_WALL_FRONT", "H2"): (-8.0, 15.0),
            ("P05_WALL_FRONT", "H3"): (6.0, -14.0),
            ("P15_TECH_FASCIA", "H3"): (-16.0, -16.0),
            ("P15_TECH_FASCIA", "H4"): (12.0, -16.0),
        }
        for idx, (lx, ly, txt, col) in enumerate(label_points):
            tag_key = txt.split(" ")[0]
            if (ev["panel_id"], tag_key) in custom_offsets:
                dx, dy = custom_offsets[(ev["panel_id"], tag_key)]
                tx, ty = lx + dx, ly + dy
                ax.plot([lx, tx], [ly, ty], color=col, lw=0.75, alpha=0.85, zorder=8)
                ax.text(
                    tx, ty, txt,
                    fontsize=6.8, fontweight="bold", color=col, ha="center", va="center",
                    bbox=dict(boxstyle="round,pad=0.14", facecolor="white", edgecolor=col, lw=0.5, alpha=0.94),
                    zorder=9,
                )
            elif len(label_points) > 16:
                short_txt = tag_key
                ax.text(
                    lx, ly + (3.6 if idx % 2 == 0 else -4.0), short_txt,
                    fontsize=6.0, fontweight="bold", color=col, ha="center", va="center",
                    bbox=dict(boxstyle="round,pad=0.10", facecolor="white", edgecolor=col, lw=0.45, alpha=0.90),
                    zorder=9,
                )
            else:
                dy = 3.8 if (idx % 2 == 0) else -4.4
                ax.text(
                    lx, ly + dy, txt,
                    fontsize=7.0, fontweight="bold", color=col, ha="center", va="center",
                    bbox=dict(boxstyle="round,pad=0.14", facecolor="white", edgecolor=col, lw=0.5, alpha=0.92),
                    zorder=9,
                )

        # Datum origin (0,0)
        pad_x = max(14.0, W * 0.16)
        pad_y = max(14.0, H * 0.22)
        ax.plot(0, 0, marker="o", markersize=5.5, color="#dc2626", zorder=10)
        ax.text(
            -pad_x * 0.12, -pad_y * 0.20, "DATUM (0, 0)",
            fontsize=7.2, fontweight="bold", color="#b91c1c", ha="left", va="top", zorder=10
        )
        _draw_dim_arrow(ax, (0, H), (W, H), f"L = {W:.2f} mm", offset_xy=(0.0, pad_y * 0.36), fontsize=8.8)
        _draw_dim_arrow(ax, (0, 0), (0, H), f"H = {H:.2f} mm", offset_xy=(-pad_x * 0.50, 0.0), fontsize=8.8)

    # Right 33%: Feature Coordinate Table
    ax_tbl = fig.add_axes([0.650, 0.185, 0.325, 0.720])
    ax_tbl.axis("off")
    ax_tbl.set_xlim(0, 100)
    ax_tbl.set_ylim(0, 100)
    ax_tbl.text(0, 99.0, "HOLE & FEATURE TABLE (mm, Center from (0,0))", fontsize=7.9, fontweight="bold", color="#0f2942", va="top")

    if not feat_rows:
        ax_tbl.text(2, 90, "No interior holes/slots.\nOuter finger tabs/notches cut 1:1 from DXF.", fontsize=8.4, color="#334155", va="top")
    else:
        n_rows = len(feat_rows)
        y_top = 94.5
        row_h = min(4.3, 90.0 / (n_rows + 1.5))
        fsize = 7.4 if n_rows <= 16 else (6.2 if n_rows <= 25 else 5.2)

        cols_x = [0, 9, 46, 73, 87]
        headers = ["ID", "Feature", "Size (mm)", "X", "Y"]
        ax_tbl.add_patch(MplRect((0, y_top - row_h), 100, row_h, facecolor="#1e3a5f", edgecolor="#1e3a5f"))
        for cx, hd in zip(cols_x, headers):
            ax_tbl.text(cx + 0.8, y_top - row_h / 2.0, hd, fontsize=fsize + 0.2, fontweight="bold", color="white", va="center")

        for ridx, row in enumerate(feat_rows):
            ry = y_top - (ridx + 2) * row_h
            bg = "#f8fafc" if ridx % 2 == 0 else "white"
            ax_tbl.add_patch(MplRect((0, ry), 100, row_h, facecolor=bg, edgecolor="#cbd5e1", lw=0.4))
            for cx, val in zip(cols_x, row):
                ax_tbl.text(cx + 0.8, ry + row_h / 2.0, val, fontsize=fsize, color="#0f172a", va="center", family="monospace")

    # Extra legend strip on P16_PCB_PLATE under its table
    if ev["panel_id"] == "P16_PCB_PLATE":
        ax_tbl.add_patch(FancyBboxPatch((0, 12.0), 100, 32.0, boxstyle="round,pad=1.0", facecolor="#f0fdf4", edgecolor="#15803d", lw=1.0))
        ax_tbl.text(3, 41.5, "P16_PCB_PLATE VERIFICATION SUMMARY:", fontsize=7.8, fontweight="bold", color="#14532d", va="top")
        p16_notes = [
            "• Plate Size: 130.0 x 110.0 x 3.0 mm (T=2/3/5 parametric)",
            "• Hub PCB: 100.0 x 80.0 x 1.6 mm (dashed green outline)",
            "• PCB Holes (H1..H4, RED): 90.0 x 70.0 mm, 4x Ø3.40 mm",
            "• Base Holes (C1..C4, BLUE): 116.0 x 96.0 mm, 4x Ø3.40 mm",
            "• Free Margin Around PCB: 15.0 mm all 4 sides (>= 10 mm)",
            "• Standoffs: 4x M3x6 under plate + 4x M3x10 under PCB",
        ]
        for idx, line in enumerate(p16_notes):
            ax_tbl.text(3, 35.8 - idx * 4.1, line, fontsize=6.9, color="#1e293b", va="top")

    # Bottom Title Block
    import textwrap
    ax_frame.add_patch(MplRect((0, 0), 100, 13.5, facecolor="#f8fafc", edgecolor="#1b2a4a", lw=1.1))
    ax_frame.plot([63.5, 63.5], [0, 13.5], color="#1b2a4a", lw=1.0)
    joint_txt = _panel_joint_summary(ev["panel_id"], joints, params)
    ax_frame.text(1.2, 11.7, "NOTES, TABS/SLOTS & CUT/ENGRAVE LAYERS:", fontsize=7.1, fontweight="bold", color="#0f2942", va="center")
    wrapped_notes = textwrap.wrap(ev["notes"], width=94)
    if len(wrapped_notes) <= 1:
        ax_frame.text(1.2, 8.6, ev["notes"], fontsize=6.6, color="#1e293b", va="center")
    else:
        ax_frame.text(1.2, 9.3, wrapped_notes[0], fontsize=6.3, color="#1e293b", va="center")
        ax_frame.text(1.2, 6.9, " ".join(wrapped_notes[1:]), fontsize=6.3, color="#1e293b", va="center")
    ax_frame.text(1.2, 4.3, joint_txt, fontsize=6.6, fontweight="bold", color="#0369a1", va="center")
    ax_frame.text(
        1.2, 1.6,
        f"DXF: panels_dxf/{ev['panel_id']}.dxf (1:1 mm) | Layers: CUT_OUTER (Red), CUT_INNER (Blue), ENGRAVE_ID (Green) | T={ev['T_mm']:.1f} mm, tab_clr={ev['tab_clr']:.2f} mm",
        fontsize=6.4, color="#475569", va="center",
    )

    ax_frame.text(65.0, 11.0, "PROJECT: Smart Home Voice AI — MICA2 Acrylic House", fontsize=7.5, fontweight="bold", color="#0f2942", va="center")
    ax_frame.text(65.0, 8.1, f"PANEL ID: {ev['panel_id']}   |   QTY: {ev['qty']}   |   T = {ev['T_mm']:.1f} mm (2/3/5)", fontsize=7.2, color="#1e293b", va="center")
    ax_frame.text(65.0, 5.2, f"NET AREA: {ev['net_area_mm2'] / 100.0:.2f} cm²   |   DATUM: Bottom-Left (0, 0) mm", fontsize=7.1, color="#334155", va="center")
    ax_frame.text(65.0, 2.2, "MATERIAL: Clear Cast Acrylic (Mica)  |  UNITS: mm  |  Zero Fan/AC/IR", fontsize=6.7, color="#475569", va="center")

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_pdf), format="pdf")
    fig.savefig(str(out_png), format="png", dpi=dpi)
    fig.savefig(str(out_svg), format="svg")
    plt.close(fig)


# ============================================================================
# 4. EXPLODED ASSEMBLY FALLBACK VECTOR VIEW (later enhanced by compose_screenshots)
# ============================================================================
def _panel_3d_faces(
    pspec: md.PanelSpec,
    params: dict[str, float],
    origin_xyz: tuple[str | float, str | float, str | float],
    explode_scale: float = 1.0,
):
    ox = md.eval_expr(origin_xyz[0], params) + pspec.explode_xyz[0] * explode_scale
    oy = md.eval_expr(origin_xyz[1], params) + pspec.explode_xyz[1] * explode_scale
    oz = md.eval_expr(origin_xyz[2], params) + pspec.explode_xyz[2] * explode_scale
    T = params["T_mm"]

    faces = []
    xs, ys, zs = [], [], []
    for r in pspec.add_rects:
        u0 = md.eval_expr(r.u0, params)
        v0 = md.eval_expr(r.v0, params)
        du = md.eval_expr(r.du, params)
        dv = md.eval_expr(r.dv, params)
        if pspec.plane == "XY":
            x0, x1 = ox + u0, ox + u0 + du
            y0, y1 = oy + v0, oy + v0 + dv
            z0, z1 = oz, oz + T
        elif pspec.plane == "XZ":
            x0, x1 = ox + u0, ox + u0 + du
            y0, y1 = oy, oy + T
            z0, z1 = oz + v0, oz + v0 + dv
        else:
            x0, x1 = ox, ox + T
            y0, y1 = oy + u0, oy + u0 + du
            z0, z1 = oz + v0, oz + v0 + dv
        xs.extend([x0, x1]); ys.extend([y0, y1]); zs.extend([z0, z1])
        c = [
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
        ]
        faces.extend([
            [c[0], c[1], c[2], c[3]], [c[4], c[5], c[6], c[7]],
            [c[0], c[1], c[5], c[4]], [c[2], c[3], c[7], c[6]],
            [c[0], c[3], c[7], c[4]], [c[1], c[2], c[6], c[5]],
        ])
    ctr = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, (min(zs) + max(zs)) / 2.0)
    return faces, ctr


def render_exploded_assembly(panels: list[md.PanelSpec], out_pdf: pathlib.Path, out_png: pathlib.Path) -> None:
    params = md.default_param_values(DEFAULT_T_MM, DEFAULT_TAB_CLR)
    fig = plt.figure(figsize=(13.5, 9.0), dpi=180, facecolor="white")
    ax = fig.add_axes([0.02, 0.08, 0.72, 0.84], projection="3d")
    ax.set_facecolor("#f8fbfe")

    palette = [
        "#60a5fa", "#3b82f6", "#38bdf8", "#818cf8", "#34d399", "#22d3ee",
        "#a78bfa", "#fbbf24", "#f59e0b", "#2dd4bf", "#14b8a6",
        "#4ade80", "#86efac", "#67e8f9", "#a3e635", "#93c5fd", "#2dd4bf", "#64748b",
    ]

    for idx, pspec in enumerate(panels):
        origins = [pspec.origin_xyz] + list(pspec.extra_origins_xyz)
        for oidx, orig in enumerate(origins):
            faces_exp, ctr_exp = _panel_3d_faces(pspec, params, orig, explode_scale=1.0)
            _faces_asm, ctr_asm = _panel_3d_faces(pspec, params, orig, explode_scale=0.0)
            col = palette[idx % len(palette)]
            poly3d = Poly3DCollection(faces_exp, facecolors=col, edgecolors="#0f2942", linewidths=0.45, alpha=0.52)
            ax.add_collection3d(poly3d)
            ax.plot(
                [ctr_exp[0], ctr_asm[0]], [ctr_exp[1], ctr_asm[1]], [ctr_exp[2], ctr_asm[2]],
                color="#dc2626", lw=1.0, ls="--", alpha=0.75,
            )
            lbl = pspec.panel_id if len(origins) == 1 else f"{pspec.panel_id}_{'LR'[oidx]}"
            ax.text(
                ctr_exp[0], ctr_exp[1], ctr_exp[2] + 6.0, lbl,
                fontsize=6.2, fontweight="bold", color="#0f172a", ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.14", facecolor="white", edgecolor="#1e3a5f", lw=0.6, alpha=0.92),
            )

    ax.set_xlim(-95, 495)
    ax.set_ylim(-125, 475)
    ax.set_zlim(-105, 255)
    ax.set_box_aspect((590, 600, 360))
    ax.view_init(elev=24, azim=-56)
    ax.set_xlabel("X (mm)", fontsize=8.5, fontweight="bold")
    ax.set_ylabel("Y (mm)", fontsize=8.5, fontweight="bold")
    ax.set_zlabel("Z (mm)", fontsize=8.5, fontweight="bold")
    ax.tick_params(labelsize=7.5)

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_pdf), format="pdf")
    fig.savefig(str(out_png), format="png", dpi=180)
    plt.close(fig)


# ============================================================================
# 5. SHEET NESTING / LAYOUT (A3 420x297 AND A4 297x210, EXPANDED BY QTY = 19 PIECES)
#    + TRUE 1:1 mm PDFs + A4 TILED OVERSIZED 1:1 PDF
# ============================================================================
def _transform_panel_pts(pts, rot90: bool, ox: float, oy: float, orig_h: float):
    out = []
    for x, y in pts:
        if rot90:
            nx, ny = (orig_h - y), x
        else:
            nx, ny = x, y
        out.append((round(nx + ox, 4), round(ny + oy, 4)))
    return out


def expand_pieces_by_qty(evals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand 18 unique panels by qty -> 19 physical cut pieces."""
    pieces: list[dict[str, Any]] = []
    for ev in evals:
        qty = int(ev["qty"])
        if qty <= 1:
            p = dict(ev)
            p["piece_id"] = ev["panel_id"]
            p["piece_copy"] = 1
            pieces.append(p)
        else:
            for k in range(1, qty + 1):
                p = dict(ev)
                p["piece_id"] = f"{ev['panel_id']}_{'LR'[k-1] if qty == 2 else k}"
                p["piece_copy"] = k
                pieces.append(p)
    return pieces


def pack_panels_on_sheets(
    pieces: list[dict[str, Any]],
    sheet_w: float,
    sheet_h: float,
    margin: float = 5.0,
    spacing: float = 4.0,
) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
    """MaxRects (Best-Short-Side-Fit) 2D nesting with 0/90-deg rotation and spacing."""
    usable_w = sheet_w - 2 * margin
    usable_h = sheet_h - 2 * margin

    fit_items = []
    oversized = []
    for ev in pieces:
        w, h = ev["width"], ev["height"]
        fits_0 = (w <= usable_w + 1e-6 and h <= usable_h + 1e-6)
        fits_90 = (h <= usable_w + 1e-6 and w <= usable_h + 1e-6)
        if not (fits_0 or fits_90):
            oversized.append(ev)
        else:
            fit_items.append(ev)

    fit_items.sort(key=lambda e: (e["bbox_area_mm2"], max(e["width"], e["height"])), reverse=True)
    sheets: list[dict[str, Any]] = []

    def _new_sheet():
        return {"free": [(margin, margin, usable_w + spacing, usable_h + spacing)], "placed": []}

    def _prune_free(free_list: list[tuple[float, float, float, float]]) -> list[tuple[float, float, float, float]]:
        pruned = []
        for i, a in enumerate(free_list):
            if a[2] < 1.0 or a[3] < 1.0:
                continue
            contained = False
            for j, b in enumerate(free_list):
                if (
                    i != j
                    and a[0] >= b[0] - 1e-6
                    and a[1] >= b[1] - 1e-6
                    and (a[0] + a[2]) <= (b[0] + b[2]) + 1e-6
                    and (a[1] + a[3]) <= (b[1] + b[3]) + 1e-6
                ):
                    contained = True
                    break
            if not contained:
                pruned.append(a)
        return pruned

    def _split_free(free_list: list[tuple[float, float, float, float]], ux: float, uy: float, uw: float, uh: float):
        new_free = []
        for fx, fy, fw, fh in free_list:
            if ux >= fx + fw - 1e-6 or ux + uw <= fx + 1e-6 or uy >= fy + fh - 1e-6 or uy + uh <= fy + 1e-6:
                new_free.append((fx, fy, fw, fh))
                continue
            if ux > fx + 1e-6:
                new_free.append((fx, fy, ux - fx, fh))
            if ux + uw < fx + fw - 1e-6:
                new_free.append((ux + uw, fy, (fx + fw) - (ux + uw), fh))
            if uy > fy + 1e-6:
                new_free.append((fx, fy, fw, uy - fy))
            if uy + uh < fy + fh - 1e-6:
                new_free.append((fx, uy + uh, fw, (fy + fh) - (uy + uh)))
        return _prune_free(new_free)

    for ev in fit_items:
        w0, h0 = ev["width"], ev["height"]
        orientations = [(w0, h0, False)]
        if abs(w0 - h0) > 1e-6:
            orientations.append((h0, w0, True))

        best = None
        for sidx, sh in enumerate(sheets):
            for fx, fy, fw, fh in sh["free"]:
                for cw, ch, rot in orientations:
                    if cw + spacing <= fw + 1e-6 and ch + spacing <= fh + 1e-6:
                        if fx + cw <= sheet_w - margin + 1e-6 and fy + ch <= sheet_h - margin + 1e-6:
                            leftover_short = min(fw - (cw + spacing), fh - (ch + spacing))
                            leftover_long = max(fw - (cw + spacing), fh - (ch + spacing))
                            score = (sidx, leftover_short, leftover_long, fy, fx)
                            if best is None or score < best[0]:
                                best = (score, sidx, fx, fy, cw, ch, rot)

        if best is None:
            sh = _new_sheet()
            sheets.append(sh)
            sidx = len(sheets) - 1
            for cw, ch, rot in orientations:
                if cw <= usable_w + 1e-6 and ch <= usable_h + 1e-6:
                    best = ((0,), sidx, margin, margin, cw, ch, rot)
                    break

        _, sidx, bx, by, cw, ch, rot = best
        sh = sheets[sidx]
        sh["placed"].append({"ev": ev, "x": round(bx, 3), "y": round(by, 3), "w": cw, "h": ch, "rot90": rot})
        sh["free"] = _split_free(sh["free"], bx, by, cw + spacing, ch + spacing)

    # Strict zero-overlap and margin verification
    for sidx, sh in enumerate(sheets):
        pl = sh["placed"]
        for i in range(len(pl)):
            a = pl[i]
            assert a["x"] >= margin - 1e-3 and a["y"] >= margin - 1e-3
            assert a["x"] + a["w"] <= sheet_w - margin + 1e-3
            assert a["y"] + a["h"] <= sheet_h - margin + 1e-3
            for j in range(i + 1, len(pl)):
                b = pl[j]
                sep_x = max(b["x"] - (a["x"] + a["w"]), a["x"] - (b["x"] + b["w"]))
                sep_y = max(b["y"] - (a["y"] + a["h"]), a["y"] - (b["y"] + b["h"]))
                assert max(sep_x, sep_y) >= spacing - 0.05, (
                    f"Sheet {sidx+1} overlap: {a['ev']['piece_id']} vs {b['ev']['piece_id']}"
                )

    return [s["placed"] for s in sheets], oversized


def _draw_calibration_bar_mm(ax, x0: float, y0: float, bar_h: float = 2.0) -> None:
    """Draw a true 50.0 mm physical calibration scale bar (5x 10 mm segments) at (x0, y0) in mm coords."""
    for seg in range(5):
        fc = "#0f172a" if seg % 2 == 0 else "white"
        ax.add_patch(MplRect((x0 + seg * 10.0, y0), 10.0, bar_h, facecolor=fc, edgecolor="#0f172a", lw=0.5, zorder=10))
    ax.text(
        x0 - 1.5, y0 + bar_h / 2.0,
        "1:1 SCALE CHECK: 50.0 mm ->",
        fontsize=5.8, fontweight="bold", color="#0f172a", ha="right", va="center", zorder=10,
    )
    ax.text(x0, y0 - 0.5, "0", fontsize=4.8, ha="center", va="top", color="#0f172a", zorder=10)
    ax.text(x0 + 50.0, y0 - 0.5, "50mm", fontsize=4.8, ha="center", va="top", color="#0f172a", zorder=10)


def _render_single_1to1_sheet_figure(
    placed: list[dict[str, Any]],
    sheet_w: float,
    sheet_h: float,
    label_name: str,
    sheet_no: int,
    total_sheets: int,
    margin: float = 5.0,
):
    """Create a Matplotlib figure whose PDF page size is EXACTLY sheet_w x sheet_h mm (true 1:1)."""
    fig = plt.figure(figsize=(sheet_w / MM_PER_INCH, sheet_h / MM_PER_INCH), facecolor="white")
    ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
    ax.set_xlim(0.0, sheet_w)
    ax.set_ylim(0.0, sheet_h)
    ax.set_aspect("equal")
    ax.axis("off")

    # Sheet outline & 5 mm usable border guide
    ax.add_patch(MplRect((0.2, 0.2), sheet_w - 0.4, sheet_h - 0.4, fill=False, edgecolor="#94a3b8", lw=0.4))
    ax.add_patch(MplRect((margin, margin), sheet_w - 2 * margin, sheet_h - 2 * margin, fill=False, edgecolor="#cbd5e1", lw=0.45, ls="--"))

    # Top non-cut border strip (y in [sheet_h - 4.2, sheet_h - 0.8]): title + 50 mm scale bar
    ax.text(
        margin, sheet_h - 2.4,
        f"MICA2 {label_name} 1:1 CUT TEMPLATE — SHEET {sheet_no}/{total_sheets} ({sheet_w:.0f}x{sheet_h:.0f} mm) | T=3.0 mm | tab_clr=0.25 mm | PRINT AT 100% ACTUAL SIZE",
        fontsize=6.2, fontweight="bold", color="#0f2942", ha="left", va="center", zorder=10,
    )
    _draw_calibration_bar_mm(ax, sheet_w - 56.0, sheet_h - 3.6, bar_h=2.0)

    # Bottom border strip note
    ax.text(
        margin, 2.2,
        "RED = CUT_OUTER  |  BLUE = CUT_INNER (slots/holes/cutouts)  |  Verify 50.0 mm bar with ruler before tracing onto acrylic film",
        fontsize=5.6, color="#475569", ha="left", va="center", zorder=10,
    )

    for item in placed:
        ev = item["ev"]
        ox, oy, rot, orig_h = item["x"], item["y"], item["rot90"], ev["height"]
        outer_t = _transform_panel_pts(ev["outer_poly"], rot, ox, oy, orig_h)
        ax.add_patch(MplPolygon(outer_t, closed=True, facecolor="#f0f9ff", edgecolor="#dc2626", lw=0.75, zorder=3))
        for r in ev["inner_rects"]:
            u0, v0, du, dv = r["u0"], r["v0"], r["du"], r["dv"]
            rpts = _transform_panel_pts(
                [(u0, v0), (u0 + du, v0), (u0 + du, v0 + dv), (u0, v0 + dv)], rot, ox, oy, orig_h
            )
            ax.add_patch(MplPolygon(rpts, closed=True, facecolor="white", edgecolor="#1d4ed8", lw=0.6, zorder=4))
        for c in ev["circles"]:
            cx, cy = _transform_panel_pts([(c["cx"], c["cy"])], rot, ox, oy, orig_h)[0]
            ax.add_patch(MplCircle((cx, cy), c["dia"] / 2.0, facecolor="white", edgecolor="#1d4ed8", lw=0.55, zorder=4))
            cr = max(1.5, c["dia"] * 0.45)
            ax.plot([cx - cr, cx + cr], [cy, cy], color="#1d4ed8", lw=0.3, zorder=5)
            ax.plot([cx, cx], [cy - cr, cy + cr], color="#1d4ed8", lw=0.3, zorder=5)

        fsize = 6.5 if min(item["w"], item["h"]) >= 40 else 5.2
        ax.text(
            ox + item["w"] / 2.0,
            oy + item["h"] / 2.0,
            f"{ev['piece_id']}\n{ev['width']:.1f}x{ev['height']:.1f} mm" + (" (90°)" if rot else ""),
            fontsize=fsize,
            fontweight="bold",
            color="#0f2942",
            ha="center",
            va="center",
            bbox=dict(boxstyle="round,pad=0.14", facecolor="white", edgecolor="none", alpha=0.80),
            zorder=6,
        )
    return fig


def export_a4_tiled_oversized_pdf(oversized: list[dict[str, Any]], out_pdf: pathlib.Path) -> dict[str, Any]:
    """Generate true 1:1 mm A4 tiled print templates with overlap & registration crosshairs
    for the 4 A3-only oversized panels (P01A, P01B, P02, P05)."""
    tile_summary: list[dict[str, Any]] = []
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(str(out_pdf)) as pdf:
        for ev in oversized:
            W, H = ev["width"], ev["height"]
            # Use A4 landscape (297x210) when H <= 192 mm; A4 portrait (210x297) when H > 192 mm (P01B: 215.875)
            if H <= 192.0:
                page_w, page_h = 297.0, 210.0
                orient = "A4 Landscape"
                # 2 tiles across X with 20 mm overlap centered at W/2
                mid_x = W / 2.0
                # Tile 1 shows panel x in [0, mid_x + 15] anchored at page x_off = 18 mm
                # Tile 2 shows panel x in [mid_x - 15, W] anchored so mid_x sits cleanly near left margin
                tile_specs = [
                    {"tile": 1, "total": 2, "x_shift": 18.0, "seam_xs": [mid_x]},
                    {"tile": 2, "total": 2, "x_shift": 36.0 - mid_x, "seam_xs": [mid_x]},
                ]
            else:
                page_w, page_h = 210.0, 297.0
                orient = "A4 Portrait"
                # 3 portrait tiles across X=406 mm (seam lines at X=140 and X=270 mm)
                s1, s2 = 140.0, 270.0
                tile_specs = [
                    {"tile": 1, "total": 3, "x_shift": 16.0, "seam_xs": [s1]},
                    {"tile": 2, "total": 3, "x_shift": 38.0 - s1, "seam_xs": [s1, s2]},
                    {"tile": 3, "total": 3, "x_shift": 38.0 - s2, "seam_xs": [s2]},
                ]

            y_shift = (page_h - H) / 2.0
            for ts in tile_specs:
                fig = plt.figure(figsize=(page_w / MM_PER_INCH, page_h / MM_PER_INCH), facecolor="white")
                ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
                ax.set_xlim(0.0, page_w)
                ax.set_ylim(0.0, page_h)
                ax.set_aspect("equal")
                ax.axis("off")

                # Page border + header + 50 mm scale bar
                ax.add_patch(MplRect((0.2, 0.2), page_w - 0.4, page_h - 0.4, fill=False, edgecolor="#94a3b8", lw=0.4))
                ax.text(
                    8.0, page_h - 5.0,
                    f"MICA2 A4 TILED 1:1 TEMPLATE — {ev['panel_id']} ({W:.2f}x{H:.2f} mm) | TILE {ts['tile']}/{ts['total']} ({orient}) | PRINT 100%",
                    fontsize=6.5, fontweight="bold", color="#0f2942", ha="left", va="center", zorder=10,
                )
                _draw_calibration_bar_mm(ax, page_w - 60.0, 4.0, bar_h=2.2)

                x_sh = ts["x_shift"]
                # Draw panel polygon shifted into tile coordinates (clipped cleanly by axes bounds)
                outer_s = [(x + x_sh, y + y_shift) for (x, y) in ev["outer_poly"]]
                ax.add_patch(MplPolygon(outer_s, closed=True, facecolor="#f0f9ff", edgecolor="#dc2626", lw=0.85, zorder=3))
                for r in ev["inner_rects"]:
                    u0, v0, du, dv = r["u0"] + x_sh, r["v0"] + y_shift, r["du"], r["dv"]
                    ax.add_patch(MplRect((u0, v0), du, dv, facecolor="white", edgecolor="#1d4ed8", lw=0.65, zorder=4))
                for c in ev["circles"]:
                    cx, cy = c["cx"] + x_sh, c["cy"] + y_shift
                    ax.add_patch(MplCircle((cx, cy), c["dia"] / 2.0, facecolor="white", edgecolor="#1d4ed8", lw=0.6, zorder=4))
                    cr = max(1.5, c["dia"] * 0.45)
                    ax.plot([cx - cr, cx + cr], [cy, cy], color="#1d4ed8", lw=0.35, zorder=5)
                    ax.plot([cx, cx], [cy - cr, cy + cr], color="#1d4ed8", lw=0.35, zorder=5)

                # Draw dashed alignment join line + 2 crisp registration crosshairs per seam
                for sx_panel in ts["seam_xs"]:
                    sx_page = sx_panel + x_sh
                    ax.plot([sx_page, sx_page], [10.0, page_h - 10.0], color="#16a34a", lw=0.9, ls="--", zorder=8)
                    for cy_reg in (y_shift + 18.0, y_shift + H - 18.0):
                        ax.add_patch(MplCircle((sx_page, cy_reg), 4.0, fill=False, edgecolor="#16a34a", lw=0.9, zorder=9))
                        ax.plot([sx_page - 6.5, sx_page + 6.5], [cy_reg, cy_reg], color="#16a34a", lw=0.7, zorder=9)
                        ax.plot([sx_page, sx_page], [cy_reg - 6.5, cy_reg + 6.5], color="#16a34a", lw=0.7, zorder=9)
                        ax.text(
                            sx_page + 5.5, cy_reg + 2.0,
                            f"ALIGN X={sx_panel:.0f}",
                            fontsize=5.8, fontweight="bold", color="#15803d", zorder=10,
                            bbox=dict(boxstyle="round,pad=0.1", facecolor="white", edgecolor="none", alpha=0.85),
                        )

                ax.text(
                    8.0, 5.0,
                    "Tape tiles together aligning green dashed line & registration crosshairs (+); verify 50.0 mm bar before tracing.",
                    fontsize=5.8, color="#334155", ha="left", va="center", zorder=10,
                )
                pdf.savefig(fig)
                plt.close(fig)

            tile_summary.append({
                "panel_id": ev["panel_id"],
                "size_mm": [round(W, 3), round(H, 3)],
                "orientation": orient,
                "tile_pages": len(tile_specs),
            })

    return {
        "pdf_file": out_pdf.name,
        "panel_count": len(oversized),
        "total_pages": sum(t["tile_pages"] for t in tile_summary),
        "panels": tile_summary,
    }


def export_nesting_all(
    sheets: list[list[dict[str, Any]]],
    oversized: list[dict[str, Any]],
    sheet_w: float,
    sheet_h: float,
    label_name: str,
    out_dxf: pathlib.Path,
    out_png: pathlib.Path,
    out_pdf_all: pathlib.Path,
    out_root: pathlib.Path,
    margin: float = 5.0,
    spacing: float = 4.0,
) -> dict[str, Any]:
    # 1. Nesting DXF (1:1 mm)
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    msp = doc.modelspace()
    doc.layers.add("SHEET_BORDER", color=7)
    doc.layers.add("CUT_OUTER", color=1)
    doc.layers.add("CUT_INNER", color=5)
    doc.layers.add("ENGRAVE_ID", color=3)

    gap_x = 30.0
    for sidx, placed in enumerate(sheets):
        sx0 = sidx * (sheet_w + gap_x)
        msp.add_lwpolyline(
            [(sx0, 0), (sx0 + sheet_w, 0), (sx0 + sheet_w, sheet_h), (sx0, sheet_h)],
            close=True, dxfattribs={"layer": "SHEET_BORDER"},
        )
        msp.add_text(
            f"{label_name} SHEET {sidx+1} ({sheet_w:.0f}x{sheet_h:.0f} mm)",
            dxfattribs={"layer": "ENGRAVE_ID", "height": 6.0, "insert": (sx0 + 5.0, sheet_h + 5.0)},
        )
        for item in placed:
            ev = item["ev"]
            ox, oy, rot = sx0 + item["x"], item["y"], item["rot90"]
            orig_h = ev["height"]
            outer_t = _transform_panel_pts(ev["outer_poly"], rot, ox, oy, orig_h)
            msp.add_lwpolyline(outer_t, close=True, dxfattribs={"layer": "CUT_OUTER"})
            for r in ev["inner_rects"]:
                u0, v0, du, dv = r["u0"], r["v0"], r["du"], r["dv"]
                rpts = _transform_panel_pts(
                    [(u0, v0), (u0 + du, v0), (u0 + du, v0 + dv), (u0, v0 + dv)], rot, ox, oy, orig_h
                )
                msp.add_lwpolyline(rpts, close=True, dxfattribs={"layer": "CUT_INNER"})
            for c in ev["circles"]:
                cx, cy = _transform_panel_pts([(c["cx"], c["cy"])], rot, ox, oy, orig_h)[0]
                msp.add_circle((cx, cy), radius=c["dia"] / 2.0, dxfattribs={"layer": "CUT_INNER"})
            msp.add_text(
                ev["piece_id"],
                dxfattribs={"layer": "ENGRAVE_ID", "height": 3.5, "insert": (ox + 3.0, oy + 3.0)},
            )
    doc.saveas(str(out_dxf))

    # 2. Multi-page 1:1 mm PDF + individual per-sheet 1:1 mm PDFs
    per_sheet_pdfs: list[str] = []
    with PdfPages(str(out_pdf_all)) as pdf_all:
        for sidx, placed in enumerate(sheets):
            fig_s = _render_single_1to1_sheet_figure(
                placed, sheet_w, sheet_h, label_name, sidx + 1, len(sheets), margin=margin
            )
            pdf_all.savefig(fig_s)
            single_path = out_root / f"sheet_layout_{label_name}_sheet{sidx+1}.pdf"
            fig_s.savefig(str(single_path), format="pdf")
            per_sheet_pdfs.append(single_path.name)
            plt.close(fig_s)

    # 3. Crisp high-res multi-sheet PNG overview
    n_sh = max(1, len(sheets))
    cols = 2 if n_sh > 1 else 1
    rows = math.ceil(n_sh / cols)
    dpi = 200 if label_name == "A3" else 180
    fig, axes = plt.subplots(rows, cols, figsize=(7.6 * cols, 5.4 * rows + 0.9), dpi=dpi, facecolor="white")
    axes_flat = [axes] if n_sh == 1 else list(np.array(axes).ravel())

    sheet_stats = []
    for sidx, placed in enumerate(sheets):
        ax = axes_flat[sidx]
        ax.set_aspect("equal")
        ax.set_xlim(-12, sheet_w + 12)
        ax.set_ylim(-14, sheet_h + 18)
        ax.add_patch(MplRect((0, 0), sheet_w, sheet_h, facecolor="#f8fafc", edgecolor="#0f172a", lw=1.6))
        ax.add_patch(MplRect((margin, margin), sheet_w - 2 * margin, sheet_h - 2 * margin, fill=False, edgecolor="#94a3b8", lw=0.75, ls="--"))
        used_area = 0.0
        for item in placed:
            ev = item["ev"]
            used_area += ev["net_area_mm2"]
            ox, oy, rot, orig_h = item["x"], item["y"], item["rot90"], ev["height"]
            outer_t = _transform_panel_pts(ev["outer_poly"], rot, ox, oy, orig_h)
            fc = "#d1fae5" if ev["panel_id"] == "P16_PCB_PLATE" else "#dbeafe"
            ec = "#15803d" if ev["panel_id"] == "P16_PCB_PLATE" else "#1e3a8a"
            ax.add_patch(MplPolygon(outer_t, closed=True, facecolor=fc, edgecolor=ec, lw=1.1, zorder=3))
            for r in ev["inner_rects"]:
                u0, v0, du, dv = r["u0"], r["v0"], r["du"], r["dv"]
                rpts = _transform_panel_pts(
                    [(u0, v0), (u0 + du, v0), (u0 + du, v0 + dv), (u0, v0 + dv)], rot, ox, oy, orig_h
                )
                ax.add_patch(MplPolygon(rpts, closed=True, facecolor="white", edgecolor="#dc2626", lw=0.7, zorder=4))
            for c in ev["circles"]:
                cx, cy = _transform_panel_pts([(c["cx"], c["cy"])], rot, ox, oy, orig_h)[0]
                ax.add_patch(MplCircle((cx, cy), c["dia"] / 2.0, facecolor="white", edgecolor="#dc2626", lw=0.6, zorder=4))
            fsize = 6.6 if min(item["w"], item["h"]) >= 45 else (5.0 if min(item["w"], item["h"]) < 35 else 5.5)
            disp_id = ev["piece_id"].replace("P17_BASE_JOINER_", "P17_JOINER_")
            lbl_rot = 90 if (item["w"] < 62.0 and item["h"] > 90.0) else 0
            ax.text(
                ox + item["w"] / 2.0,
                oy + item["h"] / 2.0,
                f"{disp_id}\n{item['w']:.0f}x{item['h']:.0f}" + (" (90°)" if rot else ""),
                fontsize=fsize,
                fontweight="bold",
                color="#0f172a",
                ha="center",
                va="center",
                rotation=lbl_rot,
                bbox=dict(boxstyle="round,pad=0.12", facecolor="white", edgecolor="none", alpha=0.84),
                zorder=6,
            )
        util = used_area / (sheet_w * sheet_h) * 100.0
        sheet_stats.append({
            "sheet_no": sidx + 1,
            "pieces": [it["ev"]["piece_id"] for it in placed],
            "panels": [it["ev"]["panel_id"] for it in placed],
            "utilization_pct": round(util, 1),
        })
        piece_lbl = "piece" if len(placed) == 1 else "pieces"
        ax.set_title(
            f"{label_name} Sheet #{sidx+1} ({sheet_w:.0f}x{sheet_h:.0f} mm) — {len(placed)} {piece_lbl} | Net util {util:.1f}%",
            fontsize=9.6, fontweight="bold", color="#0f2942",
        )
        ax.tick_params(labelsize=7.5)
        ax.grid(True, linestyle=":", alpha=0.35)

    for k in range(len(sheets), len(axes_flat)):
        axes_flat[k].axis("off")

    total_nested = sum(len(s) for s in sheets)
    subtitle = (
        f"MICA2 ({total_nested} nested pieces) | Margin: {margin:.0f} mm | Spacing: {spacing:.0f} mm | "
        f"T = {DEFAULT_T_MM:.1f} mm | tab_clr = {DEFAULT_TAB_CLR:.2f} mm | 1:1 PDFs included"
    )
    top_rect = 0.945
    sup_fs = 11.2
    if oversized:
        ov_items = [f"{e['panel_id']} ({e['width']:.0f}x{e['height']:.0f})" for e in oversized]
        half = (len(ov_items) + 1) // 2
        subtitle += (
            "\nOversized on A4 (use A3 or sheet_layout_A4_tiled_oversized_1to1.pdf):\n"
            + ", ".join(ov_items[:half])
            + (", " + ", ".join(ov_items[half:]) if ov_items[half:] else "")
        )
        top_rect = 0.918
        sup_fs = 10.0
    fig.suptitle(
        f"MICA2 Acrylic Cutting Sheet Nesting Layout — {label_name} ({sheet_w:.0f} x {sheet_h:.0f} mm)\n{subtitle}",
        fontsize=sup_fs, fontweight="bold", color="#0f2942", y=0.988,
    )
    plt.tight_layout(rect=[0, 0.005, 1, top_rect])
    fig.savefig(str(out_png), dpi=dpi)
    plt.close(fig)

    return {
        "sheet_type": label_name,
        "sheet_size_mm": [sheet_w, sheet_h],
        "margin_mm": margin,
        "spacing_mm": spacing,
        "sheet_count": len(sheets),
        "nested_piece_count": total_nested,
        "sheets": sheet_stats,
        "oversized_panels": [e["panel_id"] for e in oversized],
        "pdf_1to1_all": out_pdf_all.name,
        "pdf_1to1_per_sheet": per_sheet_pdfs,
    }


# ============================================================================
# 6. AUTOMATED VERIFICATION SUITE (9 STRICT MICA2 CHECKS)
# ============================================================================
def _point_to_segment_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _point_in_poly(px: float, py: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > py) != (y2 > py)) and (px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-15) + x1):
            inside = not inside
    return inside


def _rect_to_rect_dist(a: dict[str, Any], b: dict[str, Any]) -> float:
    dx = max(0.0, max(a["u0"] - (b["u0"] + b["du"]), b["u0"] - (a["u0"] + a["du"])))
    dy = max(0.0, max(a["v0"] - (b["v0"] + b["dv"]), b["v0"] - (a["v0"] + a["dv"])))
    return math.hypot(dx, dy)


def _circle_to_rect_dist(c: dict[str, Any], r: dict[str, Any]) -> float:
    nx = max(r["u0"], min(c["cx"], r["u0"] + r["du"]))
    ny = max(r["v0"], min(c["cy"], r["v0"] + r["dv"]))
    return math.hypot(c["cx"] - nx, c["cy"] - ny) - c["dia"] / 2.0


def verify_all(
    panels: list[md.PanelSpec],
    joints: list[md.JointPair],
    evals: list[dict[str, Any]],
    a3_info: dict[str, Any],
    a4_info: dict[str, Any],
    a4_tiled_info: dict[str, Any],
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema": "MICA2",
        "default_T_mm": DEFAULT_T_MM,
        "default_tab_clr_mm": DEFAULT_TAB_CLR,
        "unique_panels": len(evals),
        "physical_pieces": sum(int(e["qty"]) for e in evals),
        "checks": {},
        "all_passed": True,
    }
    eval_map = {e["panel_id"]: e for e in evals}

    # Read holes_table.csv once for Check 1 & Check 9
    csv_rows: list[dict[str, str]] = []
    csv_header: list[str] = []
    if HOLES_CSV_PATH.exists():
        with HOLES_CSV_PATH.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            csv_header = next(reader, [])
            for row in reader:
                if len(row) == 6:
                    csv_rows.append({
                        "panel": row[0], "id": row[1],
                        "x": row[2], "y": row[3],
                        "diameter": row[4], "purpose": row[5],
                    })

    # --- CHECK 1: DXF Closed Contours, Metric Units & Exact Geometry Match ---
    dxf_errors: list[str] = []
    dxf_circles_by_panel: dict[str, list[tuple[float, float, float]]] = {}
    dxf_bboxes: dict[str, tuple[float, float]] = {}

    for ev in evals:
        pid = ev["panel_id"]
        dxf_path = DXF_DIR / f"{pid}.dxf"
        if not dxf_path.exists():
            dxf_errors.append(f"Missing {dxf_path.name}")
            continue
        d = ezdxf.readfile(str(dxf_path))
        if d.header.get("$INSUNITS") != 4:
            dxf_errors.append(f"{pid}: $INSUNITS != 4")
        msp = d.modelspace()
        outer_pl = [e for e in msp if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "CUT_OUTER"]
        inner_pl = [e for e in msp if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "CUT_INNER"]
        inner_ci = [e for e in msp if e.dxftype() == "CIRCLE" and e.dxf.layer == "CUT_INNER"]
        if len(outer_pl) != 1 or not outer_pl[0].closed:
            dxf_errors.append(f"{pid}: outer contour not single closed LWPOLYLINE")
        else:
            pts = list(outer_pl[0].get_points("xy"))
            bw = max(p[0] for p in pts) - min(p[0] for p in pts)
            bh = max(p[1] for p in pts) - min(p[1] for p in pts)
            dxf_bboxes[pid] = (round(bw, 4), round(bh, 4))
            if abs(bw - ev["width"]) > 0.001 or abs(bh - ev["height"]) > 0.001:
                dxf_errors.append(f"{pid}: outer bbox ({bw:.4f}x{bh:.4f}) != model ({ev['width']:.4f}x{ev['height']:.4f})")
        if len(inner_pl) != len(ev["inner_rects"]) or any(not p.closed for p in inner_pl):
            dxf_errors.append(f"{pid}: inner rect count/closure mismatch")
        if len(inner_ci) != len(ev["circles"]):
            dxf_errors.append(f"{pid}: circle count mismatch ({len(inner_ci)} vs {len(ev['circles'])})")
        else:
            c_list = []
            for dxf_c, mod_c in zip(inner_ci, ev["circles"]):
                cx, cy = float(dxf_c.dxf.center.x), float(dxf_c.dxf.center.y)
                dia = float(dxf_c.dxf.radius) * 2.0
                c_list.append((cx, cy, dia))
                if abs(cx - mod_c["cx"]) > 0.001 or abs(cy - mod_c["cy"]) > 0.001 or abs(dia - mod_c["dia"]) > 0.001:
                    dxf_errors.append(f"{pid}:{mod_c['name']} DXF circle mismatch > 0.001 mm")
            dxf_circles_by_panel[pid] = c_list

    report["checks"]["dxf_closed_contours"] = {
        "passed": len(dxf_errors) == 0,
        "panel_count": len(evals),
        "errors": dxf_errors,
    }

    # --- CHECK 2: Min Hole >= 3.0 mm (except SG90 M2 = 2.5 mm) & Datasheet +0.5 mm Clearance ---
    hole_errors: list[str] = []
    documented_exceptions: list[dict[str, Any]] = []
    min_general_hole = 999.0
    total_holes = 0

    for ev in evals:
        pid = ev["panel_id"]
        for c in ev["circles"]:
            total_holes += 1
            d = float(c["dia"])
            if pid == "P07_SERVO_SHELF" and c["name"] in ("SG90_M2_Front", "SG90_M2_Rear"):
                documented_exceptions.append({
                    "panel": pid,
                    "hole": c["name"],
                    "diameter_mm": d,
                    "reason": "TowerPro SG90 datasheet M2 mounting ear screw (2.0 mm + 0.5 mm clearance = 2.5 mm; use M2 washers)",
                })
                if abs(d - 2.5) > 0.01:
                    hole_errors.append(f"{pid}:{c['name']} expected 2.5 mm, got {d}")
            else:
                min_general_hole = min(min_general_hole, d)
                if d < 3.0 - 1e-4:
                    hole_errors.append(f"{pid}:{c['name']} dia {d:.3f} mm < 3.0 mm")

    # Datasheet + 0.5 mm clearance checks on all module cutouts/holes
    p_def = md.default_param_values(DEFAULT_T_MM, DEFAULT_TAB_CLR)
    datasheet_checks = [
        ("SG90 body L", p_def["sg90_L"], 22.8, 0.5),
        ("SG90 body W", p_def["sg90_W"], 12.2, 0.5),
        ("SG90 M2 screw", p_def["sg90_m2_d"], 2.0, 0.5),
        ("5mm LED", p_def["led5_d"], 5.0, 0.5),
        ("3mm Power LED", p_def["led3_d"], 3.0, 0.5),
        ("12mm Active Buzzer", p_def["buzzer_d"], 12.0, 0.5),
        ("KY-037 Mic (9.7mm)", p_def["mic_d"], 9.7, 0.5),
        ("DC-022 M12 Barrel Jack", p_def["dcjack_d"], 12.0, 0.5),
        ("Module M3 Mounts", p_def["m3_mod_d"], 3.0, 0.5),
        ("DHT11 Vent W", p_def["dht_w"], 12.0, 0.5),
        ("DHT11 Vent H", p_def["dht_h"], 15.5, 0.5),
        ("YL-69 Soil Slot L", p_def["soil_slot_L"], 20.0, 0.5),
        ("YL-69 Soil Slot W", p_def["soil_slot_W"], 1.6, 0.5),
        ("Water Pump Tube OD 8mm", p_def["tube_d"], 8.0, 0.5),
    ]
    ds_results = []
    for label, actual, nominal, req_clr in datasheet_checks:
        clr = round(actual - nominal, 3)
        ok = clr >= req_clr - 1e-4
        ds_results.append({"feature": label, "actual_mm": actual, "datasheet_mm": nominal, "clearance_mm": clr, "passed": ok})
        if not ok:
            hole_errors.append(f"Datasheet clearance failed: {label} actual={actual}, nom={nominal}, clr={clr} < {req_clr}")

    report["checks"]["min_hole_and_datasheet_clearance"] = {
        "passed": len(hole_errors) == 0,
        "total_holes": total_holes,
        "min_general_hole_mm": round(min_general_hole, 3),
        "documented_lt3mm_exceptions": documented_exceptions,
        "datasheet_clearances_checked": len(ds_results),
        "errors": hole_errors,
    }

    # --- CHECK 3: Hole/Slot Non-Overlap & Min Web >= 2.0 mm (SG90 flange >= 0.95 mm) ---
    web_violations: list[str] = []
    sg90_flange_notes: list[str] = []
    min_general_web = 999.0

    for ev in evals:
        pid = ev["panel_id"]
        poly = ev["outer_poly"]
        n_v = len(poly)
        rects = ev["inner_rects"]
        circs = ev["circles"]

        for c in circs:
            if not _point_in_poly(c["cx"], c["cy"], poly):
                web_violations.append(f"{pid}:{c['name']} outside outer polygon")
                continue
            d_edge = min(
                _point_to_segment_dist(c["cx"], c["cy"], poly[i][0], poly[i][1], poly[(i + 1) % n_v][0], poly[(i + 1) % n_v][1])
                for i in range(n_v)
            ) - c["dia"] / 2.0
            min_general_web = min(min_general_web, d_edge)
            if d_edge < 2.0 - 1e-4:
                web_violations.append(f"{pid}:{c['name']} to outer edge web = {d_edge:.3f} mm (< 2.0)")

        for i in range(len(circs)):
            for j in range(i + 1, len(circs)):
                c1, c2 = circs[i], circs[j]
                web = math.hypot(c1["cx"] - c2["cx"], c1["cy"] - c2["cy"]) - (c1["dia"] + c2["dia"]) / 2.0
                min_general_web = min(min_general_web, web)
                if web < 2.0 - 1e-4:
                    web_violations.append(f"{pid}:{c1['name']} vs {c2['name']} web = {web:.3f} mm (< 2.0)")

        for r in rects:
            corners = [
                (r["u0"], r["v0"]), (r["u0"] + r["du"], r["v0"]),
                (r["u0"] + r["du"], r["v0"] + r["dv"]), (r["u0"], r["v0"] + r["dv"]),
            ]
            for (cx, cy) in corners:
                if not _point_in_poly(cx, cy, poly):
                    web_violations.append(f"{pid}:{r['name']} corner outside outer polygon")
                    break
                d_edge = min(
                    _point_to_segment_dist(cx, cy, poly[i][0], poly[i][1], poly[(i + 1) % n_v][0], poly[(i + 1) % n_v][1])
                    for i in range(n_v)
                )
                min_general_web = min(min_general_web, d_edge)
                if d_edge < 2.0 - 1e-4:
                    web_violations.append(f"{pid}:{r['name']} to outer edge web = {d_edge:.3f} mm (< 2.0)")

        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                d_rr = _rect_to_rect_dist(rects[i], rects[j])
                min_general_web = min(min_general_web, d_rr)
                if d_rr < 2.0 - 1e-4:
                    web_violations.append(f"{pid}:{rects[i]['name']} vs {rects[j]['name']} web = {d_rr:.3f} mm (< 2.0)")

        for c in circs:
            for r in rects:
                d_cr = _circle_to_rect_dist(c, r)
                is_sg90_ear = (pid == "P07_SERVO_SHELF" and r["name"] == "SG90_Cutout" and c["name"].startswith("SG90_M2_"))
                if is_sg90_ear:
                    sg90_flange_notes.append(
                        f"{pid}:{c['name']} to SG90_Cutout = {d_cr:.2f} mm (SG90 datasheet 27.8mm M2 ear pitch with 23.3mm cutout + Dia 2.5mm hole; use M2 washer)"
                    )
                    if d_cr < 0.95 - 1e-4:
                        web_violations.append(f"{pid}:{c['name']} SG90 ear web too small ({d_cr:.3f} mm < 0.95)")
                else:
                    min_general_web = min(min_general_web, d_cr)
                    if d_cr < 2.0 - 1e-4:
                        web_violations.append(f"{pid}:{c['name']} vs {r['name']} web = {d_cr:.3f} mm (< 2.0)")

    report["checks"]["min_web_and_non_overlap"] = {
        "passed": len(web_violations) == 0,
        "min_general_web_mm": round(min_general_web, 3),
        "sg90_datasheet_flange_web_notes": sg90_flange_notes,
        "violations": web_violations,
    }

    # --- CHECK 4: Tab-to-Slot Matching (59 joints, T=2/3/5 mm, tab_clr in [0.20, 0.30], tabs >= 12 mm) ---
    joint_errors: list[str] = []
    panel_map = {p.panel_id: p for p in panels}
    min_tab_len = 999.0

    for t_val in [2.0, 3.0, 5.0]:
        for clr_val in [0.20, 0.25, 0.30]:
            params = md.default_param_values(T_mm=t_val, tab_clr=clr_val)
            for j in joints:
                tab_len = md.eval_expr(j.tab_len_expr, params)
                slot_len = md.eval_expr(j.slot_len_expr, params)
                tab_d = md.eval_expr(j.tab_depth_expr, params)
                slot_w = md.eval_expr(j.slot_width_expr, params)
                min_tab_len = min(min_tab_len, tab_len)
                if tab_len < 12.0 - 1e-4:
                    joint_errors.append(f"{j.joint_id}: tab_len {tab_len} < 12.0 mm")
                if abs((slot_len - tab_len) - clr_val) > 1e-4:
                    joint_errors.append(f"T={t_val},clr={clr_val} {j.joint_id}: slot_len - tab_len != {clr_val}")
                if j.joint_kind == "seam_notch":
                    if abs(slot_w - (tab_d + clr_val)) > 1e-4:
                        joint_errors.append(f"T={t_val},clr={clr_val} {j.joint_id}: seam slot_w mismatch")
                elif j.joint_kind == "notch":
                    if abs(tab_d - t_val) > 1e-4 or abs((slot_w - t_val) - clr_val / 2.0) > 1e-4:
                        joint_errors.append(f"T={t_val},clr={clr_val} {j.joint_id}: notch depth/width mismatch")
                else:
                    if abs(tab_d - t_val) > 1e-4 or abs((slot_w - t_val) - clr_val) > 1e-4:
                        joint_errors.append(f"T={t_val},clr={clr_val} {j.joint_id}: slot depth/width mismatch")
                if j.tab_panel not in panel_map or j.slot_panel not in panel_map:
                    joint_errors.append(f"{j.joint_id}: unknown panel")

    # Verify slot counts on P01A_BASE_TECH and P01B_BASE_HOUSE
    p01a_slots = sum(1 for r in eval_map["P01A_BASE_TECH"]["inner_rects"] if r["kind"] == "slot")
    p01a_joints = sum(1 for j in joints if j.slot_panel == "P01A_BASE_TECH")
    p01b_slots = sum(1 for r in eval_map["P01B_BASE_HOUSE"]["inner_rects"] if r["kind"] == "slot")
    p01b_slot_joints = sum(1 for j in joints if j.slot_panel == "P01B_BASE_HOUSE" and j.joint_kind == "slot")
    if p01a_slots != p01a_joints:
        joint_errors.append(f"P01A_BASE_TECH slots {p01a_slots} != joints {p01a_joints}")
    if p01b_slots != p01b_slot_joints:
        joint_errors.append(f"P01B_BASE_HOUSE slots {p01b_slots} != slot joints {p01b_slot_joints}")
    if not (0.20 <= DEFAULT_TAB_CLR <= 0.30):
        joint_errors.append(f"DEFAULT_TAB_CLR {DEFAULT_TAB_CLR} outside [0.20, 0.30]")

    report["checks"]["tab_slot_matching_and_min_tab"] = {
        "passed": len(joint_errors) == 0,
        "total_tab_slot_joints": len(joints),
        "p01a_base_slots": p01a_slots,
        "p01b_base_slots": p01b_slots,
        "min_tab_width_mm": round(min_tab_len, 3),
        "default_tab_clr_mm": DEFAULT_TAB_CLR,
        "tested_thicknesses_mm": [2.0, 3.0, 5.0],
        "tested_clearances_mm": [0.20, 0.25, 0.30],
        "errors": joint_errors,
    }

    # --- CHECK 5: FreeCAD Recompute, 3D Collision & BRep-to-DXF BBox Match ---
    fc_errors: list[str] = []
    fc_data = json.loads(FC_GEOM_JSON.read_text(encoding="utf-8")) if FC_GEOM_JSON.exists() else {}
    col_data = json.loads(FC_COLLISION_JSON.read_text(encoding="utf-8")) if FC_COLLISION_JSON.exists() else {}

    if not fc_data.get("all_recompute_passed"):
        fc_errors.append("FreeCAD recompute not passed")
    if not col_data.get("all_passed"):
        fc_errors.append("FreeCAD collision/joint check not passed")

    fc_panels = fc_data.get("panels", {})
    max_bbox_diff = 0.0
    for ev in evals:
        pid = ev["panel_id"]
        fp = fc_panels.get(pid)
        if not fp:
            fc_errors.append(f"Missing {pid} in panel_geometry_from_freecad.json")
            continue
        fc_u, fc_v = float(fp["dims_uvt"][0]), float(fp["dims_uvt"][1])
        dxf_u, dxf_v = dxf_bboxes.get(pid, (ev["width"], ev["height"]))
        du = abs(fc_u - dxf_u)
        dv = abs(fc_v - dxf_v)
        max_bbox_diff = max(max_bbox_diff, du, dv)
        if du > 0.01 or dv > 0.01:
            fc_errors.append(f"{pid}: FreeCAD bbox ({fc_u}x{fc_v}) != DXF ({dxf_u}x{dxf_v})")
        if not fp.get("valid", False) or int(fp.get("solids", 0)) != 1:
            fc_errors.append(f"{pid}: invalid BRep solid in FreeCAD")

    total_collisions = 0
    max_inter_vol = 0.0
    total_joint_failures = 0
    runs_checked = []
    for rname, rval in col_data.get("runs", {}).items():
        runs_checked.append(rname)
        total_collisions += int(rval.get("collision_count", 0))
        max_inter_vol = max(max_inter_vol, float(rval.get("max_intersection_vol_mm3", 0.0)))
        total_joint_failures += int(rval.get("joint_failure_count", 0))
    if total_collisions > 0:
        fc_errors.append(f"3D BRep panel-panel collisions found: {total_collisions}")
    if total_joint_failures > 0:
        fc_errors.append(f"3D joint engagement failures: {total_joint_failures}")

    hvp = col_data.get("hardware_vs_panel_collisions", {})
    hvp_collisions = int(hvp.get("collision_count", -1))
    hvp_max_vol = float(hvp.get("max_intersection_vol_mm3", 0.0))
    if not hvp.get("passed", False) or hvp_collisions != 0:
        fc_errors.append(f"Hardware-vs-Panel 3D BRep collisions: {hvp_collisions}")

    report["checks"]["freecad_recompute_and_3d_collision"] = {
        "passed": len(fc_errors) == 0,
        "freecad_version": fc_data.get("freecad_version", "unknown"),
        "unique_panels_verified": len(evals),
        "physical_pieces_verified": fc_data.get("physical_piece_count", 0),
        "runs_checked": runs_checked,
        "collision_count": total_collisions,
        "max_interference_vol_mm3": round(max_inter_vol, 6),
        "hw_vs_panel_pairs_checked": int(hvp.get("checked_pairs", 0)),
        "hw_vs_panel_collision_count": hvp_collisions,
        "hw_vs_panel_max_interference_vol_mm3": round(hvp_max_vol, 6),
        "joint_engagement_failures": total_joint_failures,
        "max_brep_vs_dxf_bbox_err_mm": round(max_bbox_diff, 4),
        "errors": fc_errors,
    }

    # --- CHECK 6: PCB Mounting Plate Fit (90x70 mm pattern, Dia 3.4 mm, 100x80 PCB, >= 10 mm margin) ---
    p16 = eval_map["P16_PCB_PLATE"]
    pcb_holes = [c for c in p16["circles"] if c["name"].startswith("PCB_H")]
    plt_holes = [c for c in p16["circles"] if c["name"].startswith("PLATE_C")]
    p16_errors: list[str] = []

    p_xs = sorted({round(c["cx"], 4) for c in pcb_holes})
    p_ys = sorted({round(c["cy"], 4) for c in pcb_holes})
    dx_pat = round(p_xs[-1] - p_xs[0], 4) if len(p_xs) >= 2 else 0.0
    dy_pat = round(p_ys[-1] - p_ys[0], 4) if len(p_ys) >= 2 else 0.0
    pcb_dias = sorted({round(c["dia"], 4) for c in pcb_holes})

    ctr_x = (p_xs[0] + p_xs[-1]) / 2.0
    ctr_y = (p_ys[0] + p_ys[-1]) / 2.0
    pcb_x0, pcb_x1 = ctr_x - 50.0, ctr_x + 50.0
    pcb_y0, pcb_y1 = ctr_y - 40.0, ctr_y + 40.0
    margins = {
        "left": round(pcb_x0, 3),
        "right": round(p16["width"] - pcb_x1, 3),
        "bottom": round(pcb_y0, 3),
        "top": round(p16["height"] - pcb_y1, 3),
    }
    min_pcb_margin = min(margins.values())

    if len(pcb_holes) != 4 or abs(dx_pat - 90.0) > 1e-3 or abs(dy_pat - 70.0) > 1e-3:
        p16_errors.append(f"PCB pattern {dx_pat}x{dy_pat} != 90.0x70.0 mm")
    if pcb_dias != [3.4]:
        p16_errors.append(f"PCB hole diameters {pcb_dias} != [3.4]")
    if min_pcb_margin < 10.0 - 1e-4:
        p16_errors.append(f"PCB free margin {min_pcb_margin} mm < 10.0 mm")
    # Check outer corner standoff holes sit outside 100x80 PCB and match P01A_BASE_TECH
    for c in plt_holes:
        if (pcb_x0 - c["dia"] / 2.0) < c["cx"] < (pcb_x1 + c["dia"] / 2.0) and (pcb_y0 - c["dia"] / 2.0) < c["cy"] < (pcb_y1 + c["dia"] / 2.0):
            p16_errors.append(f"Corner hole {c['name']} intrudes on 100x80 PCB footprint")
    base_plt_holes = [c for c in eval_map["P01A_BASE_TECH"]["circles"] if c["name"].startswith("PLT_H")]
    bp_xs = sorted({round(c["cx"], 4) for c in base_plt_holes})
    bp_ys = sorted({round(c["cy"], 4) for c in base_plt_holes})
    pl_xs = sorted({round(c["cx"], 4) for c in plt_holes})
    pl_ys = sorted({round(c["cy"], 4) for c in plt_holes})
    if abs((bp_xs[-1] - bp_xs[0]) - (pl_xs[-1] - pl_xs[0])) > 1e-3 or abs((bp_ys[-1] - bp_ys[0]) - (pl_ys[-1] - pl_ys[0])) > 1e-3:
        p16_errors.append("P16 corner standoff pitch does not match P01A_BASE_TECH PLT_H1..H4")

    report["checks"]["pcb_plate_fit_90x70"] = {
        "passed": len(p16_errors) == 0,
        "panel_id": "P16_PCB_PLATE",
        "plate_size_mm": [p16["width"], p16["height"]],
        "pcb_size_mm": [100.0, 80.0],
        "hole_pattern_mm": [dx_pat, dy_pat],
        "hole_dias_mm": pcb_dias,
        "outer_standoff_pitch_mm": [round(pl_xs[-1] - pl_xs[0], 3), round(pl_ys[-1] - pl_ys[0], 3)],
        "free_margins_mm": margins,
        "min_margin_mm": min_pcb_margin,
        "errors": p16_errors,
    }

    # --- CHECK 7: All 17 Hardware Entries Fit Rooms, >= 15 mm Wiring Gaps, 0 Forbidden ---
    room_bounds = {
        "Technical Bay": (10.0, 260.0, 13.0, 174.0, 0.0, 120.0),
        "Technical Bay (Front Fascia)": (8.0, 254.0, 8.0, 32.0, 0.0, 48.0),
        "Living Room": (13.0, 198.5, 195.0, 379.0, 0.0, 147.0),
        "Living Room (Door Jamb)": (13.0, 198.5, 195.0, 379.0, 0.0, 147.0),
        "Living Room (Front Ledge)": (13.0, 198.5, 195.0, 220.0, 0.0, 50.0),
        "Bedroom": (201.5, 393.0, 195.0, 379.0, 0.0, 147.0),
        "Center Pillar (Front)": (188.0, 214.0, 191.0, 204.0, 110.0, 147.0),
        "Water Reservoir": (269.0, 316.5, 29.0, 149.0, 0.0, 54.0),
        "Garden Planter": (319.5, 393.0, 29.0, 149.0, 0.0, 65.0),
        "Garden Planter (Dry Exterior)": (318.0, 396.0, 8.0, 26.0, 0.0, 48.0),
    }
    room_errors: list[str] = []
    forbidden_hits: list[str] = []
    for hw in md.HARDWARE_PARTS:
        low_txt = (hw.part_id + " " + hw.name + " " + hw.datasheet_dims).lower()
        for bad in ("vs1838", "ir_led", "940nm", "fan", "air_cond", "air-con", "quat", "dieu hoa"):
            if bad in low_txt:
                forbidden_hits.append(f"{hw.part_id}: contains forbidden '{bad}'")
        bx0, bx1, by0, by1, bz0, bz1 = room_bounds[hw.room]
        cx, cy, cz = hw.center_xyz
        sx, sy, sz = hw.size_xyz
        if not (
            cx - sx / 2 >= bx0 - 0.5 and cx + sx / 2 <= bx1 + 0.5
            and cy - sy / 2 >= by0 - 0.5 and cy + sy / 2 <= by1 + 0.5
            and cz - sz / 2 >= bz0 - 0.5 and cz + sz / 2 <= bz1 + 0.5
        ):
            room_errors.append(f"{hw.part_id} exceeds {hw.room} bounds")

    hw_clr = md.check_hardware_clearances(min_gap_mm=15.0)
    report["checks"]["modules_fit_rooms_and_15mm_wiring_gaps"] = {
        "passed": len(room_errors) == 0 and len(forbidden_hits) == 0 and hw_clr["passed"],
        "hardware_entries_checked": len(md.HARDWARE_PARTS),
        "wiring_pairs_checked": hw_clr["checked_pairs"],
        "min_wiring_gap_mm": hw_clr["measured_min_gap_mm"],
        "closest_pair": hw_clr["closest_pair"],
        "room_errors": room_errors,
        "wiring_violations": hw_clr["violations"],
        "forbidden_device_hits": forbidden_hits,
    }

    # --- CHECK 8: Sheet Nesting Coverage (A3 19/19, A4 15/19 + 4 tiled) ---
    nest_errors: list[str] = []
    expected_pieces = sum(int(e["qty"]) for e in evals)
    if a3_info["nested_piece_count"] != expected_pieces or len(a3_info["oversized_panels"]) != 0:
        nest_errors.append(f"A3 nesting incomplete: {a3_info['nested_piece_count']}/{expected_pieces}, oversized={a3_info['oversized_panels']}")
    if a4_info["nested_piece_count"] + len(a4_info["oversized_panels"]) != expected_pieces:
        nest_errors.append("A4 nested + oversized != total physical pieces")
    if a4_tiled_info["panel_count"] != len(a4_info["oversized_panels"]):
        nest_errors.append("A4 tiled PDF missing oversized panels")
    for fname in (
        [a3_info["pdf_1to1_all"], a4_info["pdf_1to1_all"], a4_tiled_info["pdf_file"]]
        + a3_info["pdf_1to1_per_sheet"]
        + a4_info["pdf_1to1_per_sheet"]
    ):
        if not (OUT_ROOT / fname).exists():
            nest_errors.append(f"Missing 1:1 PDF: {fname}")

    report["checks"]["sheet_nesting_a3_and_a4"] = {
        "passed": len(nest_errors) == 0,
        "total_physical_pieces": expected_pieces,
        "a3_sheets": a3_info["sheet_count"],
        "a3_pieces_nested": a3_info["nested_piece_count"],
        "a3_oversized": a3_info["oversized_panels"],
        "a4_sheets": a4_info["sheet_count"],
        "a4_pieces_nested": a4_info["nested_piece_count"],
        "a4_oversized_tiled": a4_info["oversized_panels"],
        "a4_tiled_pages": a4_tiled_info["total_pages"],
        "errors": nest_errors,
    }

    # --- CHECK 9: holes_table.csv Consistency with DXF Circles 1:1 ---
    csv_errors: list[str] = []
    expected_header = ["panel", "id", "x", "y", "diameter", "purpose"]
    if not HOLES_CSV_PATH.exists():
        csv_errors.append("holes_table.csv missing")
    elif csv_header != expected_header:
        csv_errors.append(f"CSV header {csv_header} != {expected_header}")
    else:
        total_dxf_circles = sum(len(v) for v in dxf_circles_by_panel.values())
        if len(csv_rows) != total_dxf_circles:
            csv_errors.append(f"CSV row count {len(csv_rows)} != DXF circle count {total_dxf_circles}")
        by_panel_csv: dict[str, list[dict[str, str]]] = {}
        for r in csv_rows:
            by_panel_csv.setdefault(r["panel"], []).append(r)
        for pid, dxf_cs in dxf_circles_by_panel.items():
            c_rows = by_panel_csv.get(pid, [])
            if len(c_rows) != len(dxf_cs):
                csv_errors.append(f"{pid}: CSV hole count {len(c_rows)} != DXF {len(dxf_cs)}")
                continue
            for r, (dx, dy, dd) in zip(c_rows, dxf_cs):
                cx, cy, cd = float(r["x"]), float(r["y"]), float(r["diameter"])
                if abs(cx - dx) > 0.001 or abs(cy - dy) > 0.001 or abs(cd - dd) > 0.001:
                    csv_errors.append(f"{pid}:{r['id']} CSV ({cx},{cy},Ø{cd}) != DXF ({dx},{dy},Ø{dd})")

    report["checks"]["holes_csv_consistency"] = {
        "passed": len(csv_errors) == 0,
        "csv_file": str(HOLES_CSV_PATH.relative_to(REPO_ROOT)),
        "header": csv_header,
        "hole_rows": len(csv_rows),
        "errors": csv_errors,
    }

    report["all_passed"] = all(v["passed"] for v in report["checks"].values())
    return report


# ============================================================================
# 7. MICA_PANELS.MD FABRICATION & PANEL SCHEDULE (MICA2 ACCURATE)
# ============================================================================
def write_mica_panels_md(
    evals: list[dict[str, Any]],
    a3_info: dict[str, Any],
    a4_info: dict[str, Any],
    a4_tiled_info: dict[str, Any],
    ver_report: dict[str, Any],
    hole_count: int,
) -> None:
    total_net_mm2 = sum(e["net_area_mm2"] * e["qty"] for e in evals)
    total_bbox_mm2 = sum(e["bbox_area_mm2"] * e["qty"] for e in evals)
    total_pieces = sum(int(e["qty"]) for e in evals)
    total_phys_holes = sum(len(e["circles"]) * int(e["qty"]) for e in evals)
    fc_ver = ver_report["checks"]["freecad_recompute_and_3d_collision"]["freecad_version"]
    joint_cnt = ver_report["checks"]["tab_slot_matching_and_min_tab"]["total_tab_slot_joints"]
    min_gap = ver_report["checks"]["modules_fit_rooms_and_15mm_wiring_gaps"]["min_wiring_gap_mm"]
    checked_pairs = ver_report["checks"]["modules_fit_rooms_and_15mm_wiring_gaps"]["wiring_pairs_checked"]

    pin_map = {
        "HW_PCB": "`J1`–`J15`, `U1/U2`",
        "HW_NODEMCU": "`D0`–`D8`, `A0`",
        "HW_RELAY1": "`D6 (GPIO12)` · `J7/J8`",
        "HW_RELAY2": "`D7 (GPIO13)` · `J9/J10` (`Jmp=H`)",
        "HW_PAM8403": "`D3 (GPIO0)` · `J11/J12`",
        "HW_SPEAKER": "`PAM8403 L_OUT+/-` (BTL)",
        "HW_DC_JACK": "`+5V / GND` · `J1`",
        "HW_LED_PWR": "`+5V` via `1kΩ`",
        "HW_SG90": "`D1 (GPIO5)` · `J3`",
        "HW_BUZZER": "`D8 (GPIO15)` · `J6`",
        "HW_LED_LR": "`D0 (GPIO16)` · `J4`",
        "HW_LED_BR": "`D4 (GPIO2)` · `J5` (Active-LOW)",
        "HW_DHT11": "`D2 (GPIO4)` · `J13` (`3.3V`)",
        "HW_KY037": "`D5 (GPIO14)` · `J15` (`3.3V`, `DO`)",
        "HW_SOIL_PROBE": "Via `LM393` (`A0`)",
        "HW_LM393": "`A0 (ADC0)` · `J14` (`3.3V`, `AO`)",
        "HW_PUMP": "`J2` (via Relay 1 `D6`)",
    }

    dia_groups: dict[float, tuple[int, int]] = {}
    for e in evals:
        q = int(e["qty"])
        for c in e["circles"]:
            d = round(float(c["dia"]), 2)
            u_cnt, p_cnt = dia_groups.get(d, (0, 0))
            dia_groups[d] = (u_cnt + 1, p_cnt + q)

    dia_notes = {
        2.5: "**ONLY `< 3.0 mm` exception:** TowerPro SG90 M2 mounting ear screws on `P07_SERVO_SHELF` (`27.8 mm` pitch; `1.00 mm` flange web — **use M2 washers**).",
        3.0: "`19×` speaker grille (`P15_TECH_FASCIA`), `3×` door hinges & servo linkage (`P08_DOOR_LEAF`), `2×` PAM8403 tie/clamp holes (`P01A_BASE_TECH`).",
        3.4: "`4×` Hub PCB `90×70 mm` M3 (`P16`), `4×` plate corners (`P16`) + `4×` matching base holes (`P01A`), `8×` base seam joiner holes (`P01A`+`P01B`) + `4×2` joiner plates (`2× P17`).",
        3.5: "`4×` Relay 1 + `4×` Relay 2 (`P01A`), `1×` DHT11 (`P02`), `1×` KY-037 (`P05`), `1×` LM393 (`P12`), `1×` 3 mm Power LED + `2×` speaker M3 clamps (`P15`).",
        5.5: "`2×` 5 mm LEDs (`LED_Living_5mm` D0 & `LED_Bedroom_5mm` D4 on `P02_WALL_BACK`).",
        10.0: "Silicone pump tube pass-through (`OD 8.0 mm` tube through `P10_WATER_DIVIDER`).",
        10.5: "KY-037/038 electret microphone acoustic aperture (`P05_WALL_FRONT`).",
        12.5: "Active 5V Buzzer TMB12A05 (`P05_WALL_FRONT`) & DC-022 M12 panel-mount barrel jack (`P15_TECH_FASCIA`).",
        14.0: "Generous Dupont bundle pass-throughs (`2×` `P02`, `1×` `P03`, `2×` `P05`, `1×` `P06`).",
    }

    lines: list[str] = []
    lines.append("# Smart Home Open-Cutaway Acrylic (Mica) House — MICA2 Panel Schedule & Fabrication Spec")
    lines.append("")
    lines.append(f"- **FreeCAD Parametric Source:** [`../../../hardware/mica/smarthome_mica_house.FCStd`](../../../hardware/mica/smarthome_mica_house.FCStd) (built via `hardware/mica/build_mica.py`, verified in FreeCAD `{fc_ver}`)")
    lines.append(f"- **Default Material:** Clear Cast Acrylic (Mica), thickness **`T = {DEFAULT_T_MM:.1f} mm`** (single-cell parametric `Params.T_mm` verified for `2.0`, `3.0`, and `5.0 mm`)")
    lines.append(f"- **Hand-Cut Friendly Joint Clearance:** **`tab_clr = {DEFAULT_TAB_CLR:.2f} mm`** (`slot_w = T + tab_clr = 3.25 mm`; verified for `0.20 / 0.25 / 0.30 mm`); minimum finger tab width **`14.0 mm`** (`>= 12.0 mm`); **`{joint_cnt}`** tab-slot/notch joints total")
    lines.append("- **Enlarged Footprint:** `406.0 × 390.0 mm` split interlocking base (`P01A_BASE_TECH` + `P01B_BASE_HOUSE` + `2× P17_BASE_JOINER`), `386.0 × 190.0 × 150.0 mm` house")
    lines.append("- **Hub PCB Mounting:** Dedicated removable `P16_PCB_PLATE` (`130.0 × 110.0 mm`) with exact **`90.0 × 70.0 mm`** `4× Ø3.40 mm` M3 pattern and **`15.0 mm` free margin** on all 4 sides around the `100 × 80 mm` Hub PCB")
    lines.append(f"- **Hardware Scope:** `100 × 80 mm` Hub PCB + **14 off-board modules** + `3 mm` Power Indicator LED (**zero fan, zero AC, zero IR**); minimum inter-module wiring gap **`{min_gap:.1f} mm`** (`>= 15.0 mm` across all `{checked_pairs}` checked pairs)")
    lines.append("- **Companion Guides & Data:**")
    lines.append("  - Vietnamese Step-by-Step Build & Hand-Cutting Guide: [`ASSEMBLY_GUIDE.md`](ASSEMBLY_GUIDE.md)")
    lines.append(f"  - Complete Circular Hole Coordinates CSV: [`holes_table.csv`](holes_table.csv) (`{hole_count}` unique circular holes across `{len(evals)}` unique panels; `{total_phys_holes}` physical holes across `{total_pieces}` pieces counting `2× P17_BASE_JOINER`, bottom-left `(0, 0)` datum)")
    lines.append("  - Master 40-Wire & Locked 10-Pin ESP8266 Contract: [`../WIRING_TABLE.md`](../WIRING_TABLE.md)")
    lines.append("  - 3D Exploded Assembly View: [`assembly_exploded.pdf`](assembly_exploded.pdf) · [`assembly_exploded.png`](assembly_exploded.png)")
    lines.append("")
    lines.append(f"## 1. Panel Cutting Schedule ({len(evals)} Unique Panels / {total_pieces} Physical Pieces)")
    lines.append("")
    lines.append("| Panel ID | Name | Qty | Size L x H (mm) | Thickness | Features (Holes/Rects) | Exports (DXF / PDF / PNG / SVG) | Notes |")
    lines.append("|---|---|---:|---:|---:|---:|---|---|")
    for e in evals:
        pid = e["panel_id"]
        n_feat = len(e["circles"]) + len(e["inner_rects"])
        lines.append(
            f"| `{pid}` | {e['name']} | {e['qty']} | `{e['width']:.1f} x {e['height']:.1f}` | "
            f"`{e['T_mm']:.1f} mm` | {n_feat} ({len(e['circles'])}H / {len(e['inner_rects'])}R) | "
            f"[DXF](panels_dxf/{pid}.dxf) / [PDF](drawings/{pid}.pdf) / [PNG](drawings/{pid}.png) / [SVG](drawings/{pid}.svg) | {e['notes']} |"
        )
    lines.append("")
    lines.append("## 2. Material Area, Sheet Nesting & Estimated Cost Note")
    lines.append("")
    lines.append("### 2.1 Area & Nesting Summary")
    lines.append(f"- **Total Panel Count:** `{len(evals)}` unique panels (`{total_pieces}` physical pieces including `2× P17_BASE_JOINER`)")
    lines.append(f"- **Total Net Acrylic Area:** `{total_net_mm2 / 100.0:.1f} cm²` (`{total_net_mm2 / 1e6:.4f} m²`)")
    lines.append(f"- **Total Bounding-Box Area:** `{total_bbox_mm2 / 100.0:.1f} cm²` (`{total_bbox_mm2 / 1e6:.4f} m²`)")
    lines.append(
        f"- **A3 Sheets (`420 × 297 mm`, 5 mm margin, 4 mm spacing):** **`{a3_info['sheet_count']}` A3 sheets** hold all **{a3_info['nested_piece_count']}/{total_pieces}** pieces (`0` oversized) — "
        f"[`sheet_layout_A3.dxf`](sheet_layout_A3.dxf) | [`sheet_layout_A3.png`](sheet_layout_A3.png) | [`sheet_layout_A3_1to1.pdf`](sheet_layout_A3_1to1.pdf):"
    )
    for sh in a3_info["sheets"]:
        lines.append(
            f"  - **A3 Sheet #{sh['sheet_no']}** ([`sheet_layout_A3_sheet{sh['sheet_no']}.pdf`](sheet_layout_A3_sheet{sh['sheet_no']}.pdf), net util `{sh['utilization_pct']}%`): "
            + ", ".join(f"`{p}`" for p in sh["pieces"])
        )
    lines.append(
        f"- **A4 Sheets (`297 × 210 mm`, 5 mm margin, 4 mm spacing):** **`{a4_info['sheet_count']}` A4 sheets** hold `{a4_info['nested_piece_count']}` pieces — "
        f"[`sheet_layout_A4.dxf`](sheet_layout_A4.dxf) | [`sheet_layout_A4.png`](sheet_layout_A4.png) | [`sheet_layout_A4_1to1.pdf`](sheet_layout_A4_1to1.pdf):"
    )
    for sh in a4_info["sheets"]:
        lines.append(
            f"  - **A4 Sheet #{sh['sheet_no']}** ([`sheet_layout_A4_sheet{sh['sheet_no']}.pdf`](sheet_layout_A4_sheet{sh['sheet_no']}.pdf), net util `{sh['utilization_pct']}%`): "
            + ", ".join(f"`{p}`" for p in sh["pieces"])
        )
    lines.append(
        f"- **A4 Tiled 1:1 Templates for Oversized Panels:** [`{a4_tiled_info['pdf_file']}`]({a4_tiled_info['pdf_file']}) "
        f"(`{a4_tiled_info['total_pages']}` A4 pages at true 1:1 mm scale with `50.0 mm` calibration bar & green registration crosshairs):"
    )
    for tp in a4_tiled_info["panels"]:
        lines.append(f"  - `{tp['panel_id']}` (`{tp['size_mm'][0]:.1f} × {tp['size_mm'][1]} mm`, {tp['orientation']}, `{tp['tile_pages']}` pages)")
    lines.append("")
    lines.append("### 2.2 Estimated Material & Fabrication Cost Note (Vietnam Student Market, ~25,000 VND/USD)")
    lines.append("")
    lines.append("| Cost Item | Recommended Spec / Quantity | Est. Cost (VND) | Est. Cost (USD) | Notes |")
    lines.append("|---|---|---:|---:|---|")
    lines.append("| **Clear Cast Acrylic `3.0 mm` (Stock Sheet)** | `6×` A3 (`420×297 mm`) **or** `1× 600×900 mm` (`0.54 m²`) **or** `1× 600×1200 mm` (`0.72 m²`) | `150,000–280,000` | `$6.0–$11.2` | `600×900 mm` (`~150k–220k`) is tight for laser; `600×1200 mm` (`~220k–280k`) gives spare margin for hand cutting. |")
    lines.append("| **M3 / M2 Standoffs, Screws, Nuts, Washers & Hinges** | `4×` M3×10 brass, `4×` M3×6, `11×` M3×8 nylon, `10×` M3×10/12, `2×` M2×8/10 + M2 washers, `2×` mini hinges, LED bezels | `45,000–70,000` | `$1.8–$2.8` | Easily sourced at local electronics markets (Chợ Trời / Nhật Tảo / Shopee). |")
    lines.append("| **Acrylic Solvent Cement + Neutral Clear Silicone** | `1×` Chloroform / acrylic glue (`50–100 ml` + syringe) + `1×` clear neutral silicone tube | `35,000–55,000` | `$1.4–$2.2` | Neutral silicone required for waterproofing water tank (`P01A/P09/P10/P12/P13`). |")
    lines.append("| **Option A — Local CO2 Laser Cutting Service** | Send `sheet_layout_A3.dxf` (`6` A3 sheets or nested on `600×900 mm`) | `80,000–150,000` | `$3.2–$6.0` | Fastest & cleanest edges; zero hand-tool cost. |")
    lines.append("| **Option B — DIY Hand-Cutting Tools** *(reusable)* | Acrylic hook knife, masking tape, flat needle file, step/twist drills (`0 VND` cutting fee) | `120,000–200,000` | `$4.8–$8.0` | One-time reusable tool purchase if not already owned; cutting fee = `0 VND`. |")
    lines.append("| **Total Mechanical Enclosure Budget** | **With Laser Cut (Option A)** / **DIY Hand-Cut (Option B, excl. owned drill)** | **`310k–555k`** / **`230k–405k`** *(materials only)* | **`$12.4–$22.2`** / **`$9.2–$16.2`** | Excludes electronics (NodeMCU, PCB, 14 modules). |")
    lines.append("")
    lines.append("## 3. Circular Hole & Fastener Summary (`holes_table.csv`)")
    lines.append("")
    lines.append(f"All `{hole_count}` unique circular holes across the `{len(evals)}` panels (`{total_phys_holes}` physical holes across `{total_pieces}` pieces including the 2nd `P17_BASE_JOINER`) comply with `>= 3.0 mm` except the single documented SG90 M2 ear screw exception:")
    lines.append("")
    lines.append("| Hole Diameter | Unique Count (`holes_table.csv`) | Physical Count (`19` pcs) | Assigned Purpose & Panels |")
    lines.append("|---:|---:|---:|---|")
    for d in sorted(dia_groups):
        u_cnt, p_cnt = dia_groups[d]
        lines.append(f"| **`Ø{d:.1f} mm`** | `{u_cnt}` | `{p_cnt}` | {dia_notes.get(d, '')} |")
    lines.append(f"| **Total** | **`{hole_count}`** | **`{total_phys_holes}`** | Exact 1:1 match verified against DXF circles (`<= 0.001 mm`). |")
    lines.append("")
    lines.append("## 4. Hardware Module Mounting Map (100×80 Hub PCB + 14 Off-Board Modules + 3mm Power LED)")
    lines.append("")
    lines.append("| Module | ESP8266 Pin / Hub Port | Room / Zone | Mounted On | Fasteners / Clearance Fit | Datasheet Dimensions | Datasheet Source |")
    lines.append("|---|---|---|---|---|---|---|")
    for hw in md.HARDWARE_PARTS:
        src_url = hw.source_url
        if src_url.startswith("hardware/"):
            src_url = "../../../" + src_url
        lines.append(
            f"| **{hw.name}** | {pin_map.get(hw.part_id, '—')} | {hw.room} | `{hw.mount_panel}` | {hw.fasteners} | {hw.datasheet_dims} | [{hw.source_name}]({src_url}) |"
        )
    lines.append("")
    lines.append("## 5. Automated Verification Summary")
    lines.append("")
    lines.append(f"- **Overall Result:** `{'ALL_PASS' if ver_report['all_passed'] else 'FAILED'}` (`{sum(1 for v in ver_report['checks'].values() if v['passed'])}/{len(ver_report['checks'])}` checks passed, see [`verification_report.json`](verification_report.json))")
    for k, v in ver_report["checks"].items():
        lines.append(f"- `{k}`: `{'PASS' if v['passed'] else 'FAIL'}`")
    lines.append("")
    lines.append("See detailed Vietnamese step-by-step build & hand-cutting guide in [`ASSEMBLY_GUIDE.md`](ASSEMBLY_GUIDE.md) and exploded view in [`assembly_exploded.pdf`](assembly_exploded.pdf) / [`assembly_exploded.png`](assembly_exploded.png).")
    lines.append("")
    (OUT_ROOT / "MICA_PANELS.md").write_text("\n".join(lines), encoding="utf-8")


def _clean_stale_outputs() -> None:
    DXF_DIR.mkdir(parents=True, exist_ok=True)
    DRAW_DIR.mkdir(parents=True, exist_ok=True)
    for f in DXF_DIR.glob("*.dxf"):
        f.unlink()
    for pat in ("*.pdf", "*.png", "*.svg"):
        for f in DRAW_DIR.glob(pat):
            f.unlink()
    for pat in ("sheet_layout_A3_sheet*.pdf", "sheet_layout_A4_sheet*.pdf"):
        for f in OUT_ROOT.glob(pat):
            f.unlink()


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    _clean_stale_outputs()

    panels, joints = md.build_design()
    params = md.default_param_values(T_mm=DEFAULT_T_MM, tab_clr=DEFAULT_TAB_CLR)
    evals = [md.evaluate_panel_2d(p, T_mm=DEFAULT_T_MM, tab_clr=DEFAULT_TAB_CLR) for p in panels]
    pieces = expand_pieces_by_qty(evals)

    print(f"[export] Exporting {len(evals)} DXFs + dimensioned drawings (PDF + PNG + SVG)...")
    for ev in evals:
        pid = ev["panel_id"]
        export_panel_dxf(ev, DXF_DIR / f"{pid}.dxf")
        render_panel_drawing(
            ev, joints, params,
            DRAW_DIR / f"{pid}.pdf",
            DRAW_DIR / f"{pid}.png",
            DRAW_DIR / f"{pid}.svg",
        )

    print("[export] Exporting holes_table.csv...")
    hole_rows = export_holes_csv(evals, HOLES_CSV_PATH)
    print(f"[export] Wrote {len(hole_rows)} holes to {HOLES_CSV_PATH}")

    print("[export] Generating fallback vector exploded assembly (overwritten with FreeCAD Coin3D by compose_screenshots.py)...")
    render_exploded_assembly(panels, OUT_ROOT / "assembly_exploded.pdf", OUT_ROOT / "assembly_exploded.png")

    print(f"[export] Computing A3 (420x297) and A4 (297x210) nesting layouts for {len(pieces)} physical pieces...")
    a3_sheets, a3_over = pack_panels_on_sheets(pieces, 420.0, 297.0, margin=5.0, spacing=4.0)
    a3_info = export_nesting_all(
        a3_sheets, a3_over, 420.0, 297.0, "A3",
        OUT_ROOT / "sheet_layout_A3.dxf",
        OUT_ROOT / "sheet_layout_A3.png",
        OUT_ROOT / "sheet_layout_A3_1to1.pdf",
        OUT_ROOT,
        margin=5.0, spacing=4.0,
    )
    a4_sheets, a4_over = pack_panels_on_sheets(pieces, 297.0, 210.0, margin=5.0, spacing=4.0)
    a4_info = export_nesting_all(
        a4_sheets, a4_over, 297.0, 210.0, "A4",
        OUT_ROOT / "sheet_layout_A4.dxf",
        OUT_ROOT / "sheet_layout_A4.png",
        OUT_ROOT / "sheet_layout_A4_1to1.pdf",
        OUT_ROOT,
        margin=5.0, spacing=4.0,
    )
    a4_tiled_info = export_a4_tiled_oversized_pdf(a4_over, OUT_ROOT / "sheet_layout_A4_tiled_oversized_1to1.pdf")

    print("[verify] Running MICA2 automated verification suite (9 checks)...")
    ver_report = verify_all(panels, joints, evals, a3_info, a4_info, a4_tiled_info)
    (OUT_ROOT / "verification_report.json").write_text(json.dumps({
        "verification": ver_report,
        "nesting_A3": a3_info,
        "nesting_A4": a4_info,
        "nesting_A4_tiled_oversized": a4_tiled_info,
    }, indent=2), encoding="utf-8")

    print("[export] Writing docs/phan_cung/mica/MICA_PANELS.md...")
    write_mica_panels_md(evals, a3_info, a4_info, a4_tiled_info, ver_report, len(hole_rows))

    print("\n=== MICA2 VERIFICATION SUMMARY ===")
    for k, v in ver_report["checks"].items():
        print(f"  [{'PASS' if v['passed'] else 'FAIL'}] {k}")
        if not v["passed"]:
            print(f"     DETAILS: {json.dumps(v)}")
    print(f"OVERALL: {'ALL_PASS' if ver_report['all_passed'] else 'FAILED'}")
    print(
        f"A3 Sheets: {a3_info['sheet_count']} ({a3_info['nested_piece_count']}/{len(pieces)} pieces) | "
        f"A4 Sheets: {a4_info['sheet_count']} ({a4_info['nested_piece_count']}/{len(pieces)} pieces, "
        f"oversized tiled: {a4_info['oversized_panels']} -> {a4_tiled_info['total_pages']} pages) | "
        f"Holes CSV: {len(hole_rows)} rows"
    )
    return 0 if ver_report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
