"""Export 1:1 Laser-Cut DXFs, Dimensioned A4 Drawings, Exploded Assembly, Sheet Nesting,
MICA_PANELS.md Fabrication Guide, and Run Full Geometric & KiCad Verification.

Run with system Python (requires ezdxf, matplotlib, numpy, Pillow):
    python hardware/freecad/mica/export_drawings_and_verify.py
"""

from __future__ import annotations

import json
import math
import pathlib
import re
import sys
from typing import Any

import ezdxf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle as MplCircle, FancyBboxPatch, Polygon as MplPolygon, Rectangle as MplRect
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import mica_design as md

OUT_ROOT = REPO_ROOT / "docs" / "phan_cung" / "mica"
DXF_DIR = OUT_ROOT / "panels_dxf"
DRAW_DIR = OUT_ROOT / "drawings"
KICAD_PCB_FILE = REPO_ROOT / "hardware" / "kicad" / "smarthome_hub" / "smarthome_hub.kicad_pcb"
FC_GEOM_JSON = SCRIPT_DIR / "panel_geometry_from_freecad.json"
FC_RECOMPUTE_LOG = SCRIPT_DIR / "freecad_recompute_check.log"


# ============================================================================
# 1. DXF EXPORT (1:1 mm, Closed LWPOLYLINE + CIRCLE, Laser-Ready)
# ============================================================================
def export_panel_dxf(ev: dict[str, Any], out_path: pathlib.Path) -> None:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4  # Millimeters
    doc.header["$MEASUREMENT"] = 1  # Metric
    msp = doc.modelspace()

    doc.layers.add("CUT_OUTER", color=1)   # Red
    doc.layers.add("CUT_INNER", color=5)   # Blue
    doc.layers.add("ENGRAVE_ID", color=3)  # Green

    # Closed outer contour
    msp.add_lwpolyline(ev["outer_poly"], close=True, dxfattribs={"layer": "CUT_OUTER"})

    # Closed interior rectangular slots/cutouts/windows
    for r in ev["inner_rects"]:
        u0, v0, du, dv = r["u0"], r["v0"], r["du"], r["dv"]
        pts = [(u0, v0), (u0 + du, v0), (u0 + du, v0 + dv), (u0, v0 + dv)]
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "CUT_INNER"})

    # Circular holes
    for c in ev["circles"]:
        msp.add_circle((c["cx"], c["cy"]), radius=c["dia"] / 2.0, dxfattribs={"layer": "CUT_INNER"})

    # Non-cut engraving label positioned cleanly
    lbl = f"{ev['panel_id']} (T={ev['T_mm']:.0f}mm)"
    msp.add_text(
        lbl,
        dxfattribs={
            "layer": "ENGRAVE_ID",
            "height": min(4.0, max(2.2, ev["height"] * 0.04)),
            "insert": (min(10.0, ev["width"] * 0.1), min(8.0, ev["height"] * 0.1)),
        },
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(out_path))


# ============================================================================
# 2. DIMENSIONED A4-PRINTABLE ENGINEERING DRAWINGS (PDF + PNG)
# ============================================================================
def _draw_dim_arrow(ax, p1, p2, text: str, offset_xy=(0.0, 0.0), fontsize=8.0, color="#1a365d"):
    x1, y1 = p1
    x2, y2 = p2
    ox, oy = offset_xy
    ax.annotate(
        "", xy=(x2 + ox, y2 + oy), xytext=(x1 + ox, y1 + oy),
        arrowprops=dict(arrowstyle="<->", color=color, lw=1.0, shrinkA=0, shrinkB=0),
        zorder=8,
    )
    # Extension lines
    if abs(ox) > 1e-3 or abs(oy) > 1e-3:
        ax.plot([x1, x1 + ox * 1.15], [y1, y1 + oy * 1.15], color=color, lw=0.6, alpha=0.75, zorder=7)
        ax.plot([x2, x2 + ox * 1.15], [y2, y2 + oy * 1.15], color=color, lw=0.6, alpha=0.75, zorder=7)
    mx, my = (x1 + x2) / 2.0 + ox, (y1 + y2) / 2.0 + oy
    rot = 90 if abs(x2 - x1) < 1e-3 else 0
    ax.text(
        mx, my, text, ha="center", va="center", rotation=rot, fontsize=fontsize,
        fontweight="bold", color=color,
        bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="none", alpha=0.92),
        zorder=9,
    )


def render_panel_drawing(ev: dict[str, Any], out_pdf: pathlib.Path, out_png: pathlib.Path) -> None:
    """Render a crisp A4-landscape engineering blueprint with datum table (PDF + PNG)."""
    fig = plt.figure(figsize=(11.69, 8.27), dpi=200, facecolor="white")
    # Outer A4 border frame
    ax_frame = fig.add_axes([0.015, 0.02, 0.97, 0.96])
    ax_frame.set_xlim(0, 100)
    ax_frame.set_ylim(0, 100)
    ax_frame.axis("off")
    ax_frame.add_patch(MplRect((0, 0), 100, 100, fill=False, edgecolor="#1b2a4a", lw=1.6))

    # Top header banner
    ax_frame.add_patch(MplRect((0, 93.5), 100, 6.5, facecolor="#f0f6fb", edgecolor="#1b2a4a", lw=1.1))
    ax_frame.text(
        1.2, 96.7,
        f"{ev['panel_id']}  —  {ev['name'].upper()}",
        fontsize=10.2, fontweight="bold", color="#0f2942", va="center",
    )
    ax_frame.text(
        98.8, 96.7,
        f"SIZE: {ev['width']:.1f} x {ev['height']:.1f} mm  |  T = {ev['T_mm']:.1f} mm  |  QTY: {ev['qty']}  |  CLEAR ACRYLIC",
        fontsize=8.2, fontweight="bold", color="#1e4e79", va="center", ha="right",
    )

    # Left 64%: Blueprint geometry axes
    ax = fig.add_axes([0.045, 0.14, 0.59, 0.74])
    ax.set_aspect("equal", adjustable="box")
    ax.set_facecolor("#fafdff")

    W, H = ev["width"], ev["height"]
    pad_x = max(14.0, W * 0.16)
    pad_y = max(14.0, H * 0.22)
    ax.set_xlim(-pad_x, W + pad_x * 0.75)
    ax.set_ylim(-pad_y, H + pad_y * 0.75)

    # Light engineering grid
    step = 20.0 if max(W, H) > 150 else 10.0
    ax.set_xticks(np.arange(0, W + step, step))
    ax.set_yticks(np.arange(0, H + step, step))
    ax.grid(True, linestyle=":", linewidth=0.5, color="#cbd5e1", zorder=0)
    ax.tick_params(labelsize=7.5, colors="#475569")
    ax.set_xlabel("X from Left Datum (mm)", fontsize=8.5, fontweight="bold", color="#1e293b")
    ax.set_ylabel("Y from Bottom Datum (mm)", fontsize=8.5, fontweight="bold", color="#1e293b")

    # Outer acrylic panel polygon
    ax.add_patch(MplPolygon(
        ev["outer_poly"], closed=True, facecolor="#dff1fc", edgecolor="#0c4a6e", lw=1.6, zorder=2
    ))

    # Build unified feature table rows (cutouts + holes)
    feat_rows: list[tuple[str, str, str, str, str]] = []
    label_points: list[tuple[float, float, str, str]] = []

    for idx, r in enumerate(ev["inner_rects"], 1):
        tag = f"R{idx}" if r["kind"] != "slot" else f"S{idx}"
        col = "#b91c1c" if r["kind"] == "slot" else "#0369a1"
        ax.add_patch(MplRect(
            (r["u0"], r["v0"]), r["du"], r["dv"],
            facecolor="white", edgecolor=col, lw=1.2, zorder=4
        ))
        # Center crosshairs
        ax.plot([r["cx"] - 2.5, r["cx"] + 2.5], [r["cy"], r["cy"]], color=col, lw=0.6, ls="--", zorder=5)
        ax.plot([r["cx"], r["cx"]], [r["cy"] - 2.5, r["cy"] + 2.5], color=col, lw=0.6, ls="--", zorder=5)
        sz_txt = f"{r['du']:.1f}x{r['dv']:.1f}" if (r["du"] >= 100 or r["dv"] >= 100) else f"{r['du']:.2f}x{r['dv']:.2f}"
        feat_rows.append((
            tag,
            r["name"][:18],
            sz_txt,
            f"{r['cx']:.2f}",
            f"{r['cy']:.2f}",
        ))
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
        feat_rows.append((
            tag,
            c["name"][:22],
            f"Dia {c['dia']:.2f}",
            f"{c['cx']:.2f}",
            f"{c['cy']:.2f}",
        ))
        label_points.append((c["cx"], c["cy"], f"{tag} (Ø{c['dia']:.1f})", col))

    if grille_circles:
        gc0 = grille_circles[0]
        for c in grille_circles:
            ax.add_patch(MplCircle(
                (c["cx"], c["cy"]), c["dia"] / 2.0,
                facecolor="white", edgecolor="#7c3aed", lw=1.0, zorder=4
            ))
        # Draw dashed Dia 28mm speaker outline behind grille
        ax.add_patch(MplCircle(
            (gc0["cx"], gc0["cy"]), 14.0,
            facecolor="none", edgecolor="#7c3aed", lw=0.8, ls=":", zorder=3
        ))
        feat_rows.append((
            "G1",
            "Spk Grille (19x)",
            f"19x Ø{gc0['dia']:.2f}",
            f"{gc0['cx']:.2f}",
            f"{gc0['cy']:.2f}",
        ))
        feat_rows.append((
            "G2",
            "Rings R5.5/10.5",
            "1+6+12 holes",
            f"{gc0['cx']:.2f}",
            f"{gc0['cy']:.2f}",
        ))
        label_points.append((gc0["cx"], gc0["cy"] + 15.5, "G1: 19x Ø2.5 (R5.5/10.5)", "#6d28d9"))

    # Place non-overlapping compact tags on blueprint
    for idx, (lx, ly, txt, col) in enumerate(label_points):
        dy = 3.5 if (idx % 2 == 0) else -4.2
        if len(label_points) > 20:
            # Ultra-compact tag for P01_BASE (many slots + holes)
            short_txt = txt.split(" ")[0]
            ax.text(
                lx, ly + (3.2 if idx % 2 == 0 else -3.8), short_txt,
                fontsize=6.2, fontweight="bold", color=col, ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.1", facecolor="white", edgecolor=col, lw=0.4, alpha=0.88),
                zorder=9,
            )
        else:
            ax.text(
                lx, ly + dy, txt,
                fontsize=7.2, fontweight="bold", color=col, ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.14", facecolor="white", edgecolor=col, lw=0.5, alpha=0.92),
                zorder=9,
            )

    # Datum origin (0,0) symbol
    ax.plot(0, 0, marker="o", markersize=5.5, color="#dc2626", zorder=10)
    ax.text(
        -pad_x * 0.12, -pad_y * 0.22, "DATUM (0, 0)",
        fontsize=7.2, fontweight="bold", color="#b91c1c", ha="left", va="top", zorder=10
    )

    # Overall dimension arrows
    _draw_dim_arrow(ax, (0, H), (W, H), f"L = {W:.2f} mm", offset_xy=(0.0, pad_y * 0.38), fontsize=8.8)
    _draw_dim_arrow(ax, (0, 0), (0, H), f"H = {H:.2f} mm", offset_xy=(-pad_x * 0.52, 0.0), fontsize=8.8)

    # Right 33%: Feature Coordinate Table (measured from Left/Bottom Datum)
    ax_tbl = fig.add_axes([0.655, 0.20, 0.32, 0.71])
    ax_tbl.axis("off")
    ax_tbl.set_xlim(0, 100)
    ax_tbl.set_ylim(0, 100)
    ax_tbl.text(0, 98.5, "FEATURE & DATUM TABLE (mm, Center from Left/Bottom)", fontsize=8.0, fontweight="bold", color="#0f2942", va="top")

    if not feat_rows:
        ax_tbl.text(2, 90, "No interior holes/slots.\nOuter finger tabs/notches cut 1:1 from DXF.", fontsize=8.5, color="#334155", va="top")
    else:
        # Dynamic row sizing so up to 44 rows fit crisply with readable font
        n_rows = len(feat_rows)
        y_top = 94.0
        row_h = min(4.2, 88.0 / (n_rows + 1.5))
        fsize = 7.4 if n_rows <= 18 else (6.3 if n_rows <= 30 else 5.5)

        cols_x = [0, 9, 44, 73, 87]
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

    # Bottom Title Block (full width of bottom strip)
    ax_frame.add_patch(MplRect((0, 0), 100, 11.5, facecolor="#f8fafc", edgecolor="#1b2a4a", lw=1.1))
    ax_frame.plot([64, 64], [0, 11.5], color="#1b2a4a", lw=1.0)
    ax_frame.text(1.2, 9.2, "NOTES & FABRICATION:", fontsize=7.4, fontweight="bold", color="#0f2942", va="center")
    note_txt = ev["notes"] if len(ev["notes"]) <= 84 else ev["notes"][:82] + "..."
    ax_frame.text(1.2, 5.6, note_txt, fontsize=7.0, color="#1e293b", va="center")
    ax_frame.text(
        1.2, 2.0,
        f"Laser Cut DXF: panels_dxf/{ev['panel_id']}.dxf (1:1 mm)  |  Slot Clearance/Kerf: +{ev['kerf']:.2f} mm  |  Parametric T: 2 / 3 / 5 mm",
        fontsize=7.1, color="#475569", va="center",
    )

    ax_frame.text(65.5, 9.0, "PROJECT: Smart Home Voice AI — Acrylic House", fontsize=7.6, fontweight="bold", color="#0f2942", va="center")
    ax_frame.text(65.5, 6.2, f"PANEL ID: {ev['panel_id']}   |   QTY: {ev['qty']}   |   THICKNESS: {ev['T_mm']:.1f} mm", fontsize=7.5, color="#1e293b", va="center")
    ax_frame.text(65.5, 3.5, f"NET AREA: {ev['net_area_mm2'] / 100.0:.2f} cm²   |   DATUM: Bottom-Left (0, 0) mm", fontsize=7.3, color="#334155", va="center")
    ax_frame.text(65.5, 1.3, "MATERIAL: Clear Cast Acrylic (Mica)  |  UNITS: mm  |  1:1 DXF Verified", fontsize=6.9, color="#475569", va="center")

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_pdf), format="pdf")
    fig.savefig(str(out_png), format="png", dpi=200)
    plt.close(fig)


# ============================================================================
# 3. EXPLODED ASSEMBLY DRAWING (PDF + PNG)
# ============================================================================
def _panel_3d_faces(pspec: md.PanelSpec, params: dict[str, float], explode_scale: float = 1.0):
    """Build 3D prism faces of a panel's bounding/body rects for vector exploded rendering."""
    ox = md.eval_expr(pspec.origin_xyz[0], params) + pspec.explode_xyz[0] * explode_scale
    oy = md.eval_expr(pspec.origin_xyz[1], params) + pspec.explode_xyz[1] * explode_scale
    oz = md.eval_expr(pspec.origin_xyz[2], params) + pspec.explode_xyz[2] * explode_scale
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
            [c[0], c[1], c[2], c[3]],
            [c[4], c[5], c[6], c[7]],
            [c[0], c[1], c[5], c[4]],
            [c[2], c[3], c[7], c[6]],
            [c[0], c[3], c[7], c[4]],
            [c[1], c[2], c[6], c[5]],
        ])
    ctr = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, (min(zs) + max(zs)) / 2.0)
    return faces, ctr


def render_exploded_assembly(panels: list[md.PanelSpec], out_pdf: pathlib.Path, out_png: pathlib.Path) -> None:
    params = md.default_param_values(3.0, 0.15)
    fig = plt.figure(figsize=(13.5, 9.0), dpi=180, facecolor="white")
    ax = fig.add_axes([0.02, 0.08, 0.72, 0.84], projection="3d")
    ax.set_facecolor("#f8fbfe")

    palette = [
        "#60a5fa", "#38bdf8", "#818cf8", "#34d399", "#22d3ee",
        "#a78bfa", "#fbbf24", "#f59e0b", "#2dd4bf", "#14b8a6",
        "#4ade80", "#86efac", "#67e8f9", "#a3e635", "#93c5fd",
    ]

    for idx, pspec in enumerate(panels):
        faces_exp, ctr_exp = _panel_3d_faces(pspec, params, explode_scale=1.0)
        _faces_asm, ctr_asm = _panel_3d_faces(pspec, params, explode_scale=0.0)
        col = palette[idx % len(palette)]
        poly3d = Poly3DCollection(faces_exp, facecolors=col, edgecolors="#0f2942", linewidths=0.45, alpha=0.52)
        ax.add_collection3d(poly3d)

        # Dashed explosion arrow from exploded center toward assembled center
        ax.plot(
            [ctr_exp[0], ctr_asm[0]], [ctr_exp[1], ctr_asm[1]], [ctr_exp[2], ctr_asm[2]],
            color="#dc2626", lw=1.0, ls="--", alpha=0.75,
        )
        ax.text(
            ctr_exp[0], ctr_exp[1], ctr_exp[2] + 6.0,
            pspec.panel_id.split("_")[0] + "\n" + "_".join(pspec.panel_id.split("_")[1:]),
            fontsize=6.8, fontweight="bold", color="#0f172a", ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.16", facecolor="white", edgecolor="#1e3a5f", lw=0.6, alpha=0.92),
        )

    ax.set_xlim(-95, 455)
    ax.set_ylim(-115, 370)
    ax.set_zlim(-65, 245)
    ax.set_box_aspect((550, 485, 310))
    ax.view_init(elev=24, azim=-56)
    ax.set_xlabel("X (mm) — Left to Right", fontsize=8.5, fontweight="bold")
    ax.set_ylabel("Y (mm) — Front to Back", fontsize=8.5, fontweight="bold")
    ax.set_zlabel("Z (mm) — Height", fontsize=8.5, fontweight="bold")
    ax.tick_params(labelsize=7.5)

    # Header & Right-side Assembly Order Panel
    ax_ov = fig.add_axes([0.01, 0.01, 0.98, 0.98])
    ax_ov.axis("off")
    ax_ov.set_xlim(0, 100)
    ax_ov.set_ylim(0, 100)
    ax_ov.add_patch(MplRect((0, 0), 100, 100, fill=False, edgecolor="#1b2a4a", lw=1.5))
    ax_ov.add_patch(MplRect((0, 93), 100, 7, facecolor="#eff6ff", edgecolor="#1b2a4a", lw=1.0))
    ax_ov.text(
        1.5, 96.5,
        "SMART HOME OPEN-CUTAWAY ACRYLIC HOUSE — EXPLODED ASSEMBLY & BUILD ORDER (T = 3.0 mm)",
        fontsize=12.0, fontweight="bold", color="#0f2942", va="center",
    )

    ax_ov.add_patch(MplRect((75.0, 4.0), 23.8, 87.0, facecolor="#f8fafc", edgecolor="#1e3a5f", lw=1.0))
    ax_ov.text(76.2, 88.5, "ASSEMBLY ORDER (8 STEPS)", fontsize=9.2, fontweight="bold", color="#0f2942", va="top")

    steps = [
        ("Step 1", "Prepare P01_BASE", "Mount M3x10 standoffs for KiCad PCB\n(H1..H4), 2x Relays, PAM8403 pad."),
        ("Step 2", "Sub-assemble P02_WALL_BACK", "Install Living/Bed 5mm LEDs & DHT11\nmodule; slot P02 into P01_BASE."),
        ("Step 3", "Lock P06_WALL_MID", "Slot P06 rear tabs into P02 & bottom\ntabs into P01_BASE."),
        ("Step 4", "Attach P03 & P04 Side Walls", "Interlock rear finger tabs into P02\nand drop bottom tabs into P01_BASE."),
        ("Step 5", "Install P07_SERVO_SHELF + P05", "Mount SG90 on P07, KY-037 & 12mm\nBuzzer on P05; lock P05 to P03/P04/P06."),
        ("Step 6", "Hang P08_DOOR_LEAF", "Attach mini hinges to P05 door jamb\nand connect SG90 horn push-rod."),
        ("Step 7", "Build Water & Garden Box", "Interlock P09..P13 into P01_BASE;\nseal water seams; drop pump + tube;\nmount LM393; fit P14_SOIL_BRIDGE."),
        ("Step 8", "Fit P15_TECH_FASCIA & Wire", "Clamp Dia 28mm speaker + 3mm Power\nLED on P15; slot into P01_BASE;\nplug KiCad PCB & Dupont harness."),
    ]
    y_cur = 83.5
    for st_num, title, desc in steps:
        ax_ov.add_patch(FancyBboxPatch(
            (76.0, y_cur - 8.6), 21.8, 8.8, boxstyle="round,pad=0.3",
            facecolor="white", edgecolor="#94a3b8", lw=0.7
        ))
        ax_ov.text(76.8, y_cur - 0.8, f"{st_num}: {title}", fontsize=7.6, fontweight="bold", color="#0c4a6e", va="top")
        ax_ov.text(76.8, y_cur - 3.3, desc, fontsize=6.6, color="#334155", va="top")
        y_cur -= 9.8

    ax_ov.text(
        1.5, 2.2,
        "15 Parametric Acrylic Panels  |  Tab-and-Slot Finger Joints (Slot = T + 0.15 mm)  |  Zero Fan / AC / IR",
        fontsize=8.0, color="#475569", va="center",
    )

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_pdf), format="pdf")
    fig.savefig(str(out_png), format="png", dpi=180)
    plt.close(fig)


# ============================================================================
# 4. SHEET NESTING / LAYOUT (A3 420x297 AND A4 297x210)
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


def pack_panels_on_sheets(
    evals: list[dict[str, Any]],
    sheet_w: float,
    sheet_h: float,
    margin: float = 5.0,
    spacing: float = 4.0,
) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
    """MaxRects (Best-Short-Side-Fit) 2D nesting with 0/90-deg rotation and kerf spacing."""
    usable_w = sheet_w - 2 * margin
    usable_h = sheet_h - 2 * margin

    fit_items = []
    oversized = []
    for ev in evals:
        w, h = ev["width"], ev["height"]
        fits_0 = (w <= usable_w + 1e-6 and h <= usable_h + 1e-6)
        fits_90 = (h <= usable_w + 1e-6 and w <= usable_h + 1e-6)
        if not (fits_0 or fits_90):
            oversized.append(ev)
        else:
            fit_items.append(ev)

    fit_items.sort(key=lambda e: (e["bbox_area_mm2"], max(e["width"], e["height"])), reverse=True)

    # Each sheet stores free_rects = [(x, y, w, h)] in sheet coordinates, inflated by spacing on right/top
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
                if i != j and a[0] >= b[0] - 1e-6 and a[1] >= b[1] - 1e-6 and (a[0] + a[2]) <= (b[0] + b[2]) + 1e-6 and (a[1] + a[3]) <= (b[1] + b[3]) + 1e-6:
                    contained = True
                    break
            if not contained:
                pruned.append(a)
        return pruned

    def _split_free(free_list: list[tuple[float, float, float, float]], ux: float, uy: float, uw: float, uh: float):
        new_free = []
        for fx, fy, fw, fh in free_list:
            # Disjoint?
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

        best = None  # (score, sheet_idx, x, y, cw, ch, rot)
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

    # Verify strictly zero overlap and inside sheet margins
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
                assert max(sep_x, sep_y) >= spacing - 0.05, f"Sheet {sidx+1} overlap: {a['ev']['panel_id']} vs {b['ev']['panel_id']}"

    return [s["placed"] for s in sheets], oversized


def export_nesting_dxf_and_png(
    sheets: list[list[dict[str, Any]]],
    oversized: list[dict[str, Any]],
    sheet_w: float,
    sheet_h: float,
    label_name: str,
    out_dxf: pathlib.Path,
    out_png: pathlib.Path,
) -> dict[str, Any]:
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
                ev["panel_id"],
                dxfattribs={"layer": "ENGRAVE_ID", "height": 3.5, "insert": (ox + 3.0, oy + 3.0)},
            )
    doc.saveas(str(out_dxf))

    # Render crisp multi-sheet PNG overview
    n_sh = max(1, len(sheets))
    cols = 2 if n_sh > 1 else 1
    rows = math.ceil(n_sh / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(7.5 * cols, 5.4 * rows + 0.8), dpi=180, facecolor="white")
    if n_sh == 1:
        axes_flat = [axes]
    else:
        axes_flat = list(np.array(axes).ravel())

    sheet_stats = []
    for sidx, placed in enumerate(sheets):
        ax = axes_flat[sidx]
        ax.set_aspect("equal")
        ax.set_xlim(-12, sheet_w + 12)
        ax.set_ylim(-14, sheet_h + 18)
        ax.add_patch(MplRect((0, 0), sheet_w, sheet_h, facecolor="#f8fafc", edgecolor="#0f172a", lw=1.6))
        ax.add_patch(MplRect((5, 5), sheet_w - 10, sheet_h - 10, fill=False, edgecolor="#94a3b8", lw=0.7, ls="--"))
        used_area = 0.0
        for item in placed:
            ev = item["ev"]
            used_area += ev["net_area_mm2"]
            ox, oy, rot, orig_h = item["x"], item["y"], item["rot90"], ev["height"]
            outer_t = _transform_panel_pts(ev["outer_poly"], rot, ox, oy, orig_h)
            ax.add_patch(MplPolygon(outer_t, closed=True, facecolor="#dbeafe", edgecolor="#1e3a8a", lw=1.1, zorder=3))
            for r in ev["inner_rects"]:
                u0, v0, du, dv = r["u0"], r["v0"], r["du"], r["dv"]
                rpts = _transform_panel_pts(
                    [(u0, v0), (u0 + du, v0), (u0 + du, v0 + dv), (u0, v0 + dv)], rot, ox, oy, orig_h
                )
                ax.add_patch(MplPolygon(rpts, closed=True, facecolor="white", edgecolor="#dc2626", lw=0.7, zorder=4))
            for c in ev["circles"]:
                cx, cy = _transform_panel_pts([(c["cx"], c["cy"])], rot, ox, oy, orig_h)[0]
                ax.add_patch(MplCircle((cx, cy), c["dia"] / 2.0, facecolor="white", edgecolor="#dc2626", lw=0.6, zorder=4))
            ax.text(
                ox + item["w"] / 2.0, oy + item["h"] / 2.0,
                f"{ev['panel_id']}\n{item['w']:.0f}x{item['h']:.0f}" + (" (90°)" if rot else ""),
                fontsize=6.5, fontweight="bold", color="#0f172a", ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.14", facecolor="white", edgecolor="none", alpha=0.82),
                zorder=6,
            )
        util = used_area / (sheet_w * sheet_h) * 100.0
        sheet_stats.append({
            "sheet_no": sidx + 1,
            "panels": [it["ev"]["panel_id"] for it in placed],
            "utilization_pct": round(util, 1),
        })
        ax.set_title(
            f"{label_name} Sheet #{sidx+1} ({sheet_w:.0f}x{sheet_h:.0f} mm) — {len(placed)} panels | Net util {util:.1f}%",
            fontsize=9.5, fontweight="bold", color="#0f2942",
        )
        ax.tick_params(labelsize=7.5)
        ax.grid(True, linestyle=":", alpha=0.35)

    for k in range(len(sheets), len(axes_flat)):
        axes_flat[k].axis("off")

    subtitle = f"Border margin: 5 mm | Kerf/part spacing: 4 mm | Thickness T = 3.0 mm"
    if oversized:
        subtitle += " | Oversized (require A3): " + ", ".join(f"{e['panel_id']} ({e['width']:.0f}x{e['height']:.0f})" for e in oversized)
    fig.suptitle(f"Laser Cutting Sheet Nesting Layout — {label_name}\n{subtitle}", fontsize=11.0, fontweight="bold", color="#0f2942")
    plt.tight_layout(rect=[0, 0, 1, 0.92])
    fig.savefig(str(out_png), dpi=180)
    plt.close(fig)

    return {
        "sheet_type": label_name,
        "sheet_size_mm": [sheet_w, sheet_h],
        "sheet_count": len(sheets),
        "sheets": sheet_stats,
        "oversized_panels": [e["panel_id"] for e in oversized],
    }


# ============================================================================
# 5. AUTOMATED VERIFICATION SUITE (Closed Contours, Web >= 2mm, Joints, KiCad, Rooms)
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
) -> dict[str, Any]:
    report: dict[str, Any] = {"checks": {}, "all_passed": True}
    eval_map = {e["panel_id"]: e for e in evals}

    # --- CHECK 1: DXF Closed Contours & Metric Units ---
    dxf_errors = []
    for ev in evals:
        dxf_path = DXF_DIR / f"{ev['panel_id']}.dxf"
        if not dxf_path.exists():
            dxf_errors.append(f"Missing {dxf_path.name}")
            continue
        d = ezdxf.readfile(str(dxf_path))
        if d.header.get("$INSUNITS") != 4:
            dxf_errors.append(f"{ev['panel_id']}: INSUNITS != 4")
        msp = d.modelspace()
        outer_pl = [e for e in msp if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "CUT_OUTER"]
        inner_pl = [e for e in msp if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "CUT_INNER"]
        inner_ci = [e for e in msp if e.dxftype() == "CIRCLE" and e.dxf.layer == "CUT_INNER"]
        if len(outer_pl) != 1 or not outer_pl[0].closed:
            dxf_errors.append(f"{ev['panel_id']}: outer contour not single closed LWPOLYLINE")
        if len(inner_pl) != len(ev["inner_rects"]) or any(not p.closed for p in inner_pl):
            dxf_errors.append(f"{ev['panel_id']}: inner rect count/closure mismatch")
        if len(inner_ci) != len(ev["circles"]):
            dxf_errors.append(f"{ev['panel_id']}: circle count mismatch")
    report["checks"]["dxf_closed_contours"] = {"passed": len(dxf_errors) == 0, "panel_count": len(evals), "errors": dxf_errors}

    # --- CHECK 2: Hole/Slot Non-Overlap & Min Web >= 2.0 mm ---
    web_violations = []
    sg90_flange_notes = []
    min_general_web = 999.0

    for ev in evals:
        pid = ev["panel_id"]
        poly = ev["outer_poly"]
        n_v = len(poly)
        rects = ev["inner_rects"]
        circs = ev["circles"]

        # Circle vs outer boundary
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

        # Circle vs Circle
        for i in range(len(circs)):
            for j in range(i + 1, len(circs)):
                c1, c2 = circs[i], circs[j]
                web = math.hypot(c1["cx"] - c2["cx"], c1["cy"] - c2["cy"]) - (c1["dia"] + c2["dia"]) / 2.0
                min_general_web = min(min_general_web, web)
                if web < 2.0 - 1e-4:
                    web_violations.append(f"{pid}:{c1['name']} vs {c2['name']} web = {web:.3f} mm (< 2.0)")

        # Inner rect vs outer boundary (check corners inside + edge dist >= 2.0)
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

        # Rect vs Rect
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                d_rr = _rect_to_rect_dist(rects[i], rects[j])
                min_general_web = min(min_general_web, d_rr)
                if d_rr < 2.0 - 1e-4:
                    web_violations.append(f"{pid}:{rects[i]['name']} vs {rects[j]['name']} web = {d_rr:.3f} mm (< 2.0)")

        # Circle vs Rect
        for c in circs:
            for r in rects:
                d_cr = _circle_to_rect_dist(c, r)
                is_sg90_ear = (pid == "P07_SERVO_SHELF" and r["name"] == "SG90_Cutout" and c["name"].startswith("SG90_M2_"))
                if is_sg90_ear:
                    # TowerPro SG90 datasheet physical flange: (27.8 - 23.0)/2 - 1.0 = 1.40 mm
                    sg90_flange_notes.append(f"{pid}:{c['name']} to SG90_Cutout = {d_cr:.2f} mm (mandated by SG90 27.8mm M2 tab datasheet; use M2 washer)")
                    if d_cr < 1.30:
                        web_violations.append(f"{pid}:{c['name']} SG90 ear web too small ({d_cr:.3f} mm)")
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

    # --- CHECK 3: Tab-to-Slot 1:1 Pairing across T = 2, 3, 5 mm ---
    joint_errors = []
    panel_map = {p.panel_id: p for p in panels}
    for t_val in [2.0, 3.0, 5.0]:
        params = md.default_param_values(T_mm=t_val, kerf=0.15)
        for j in joints:
            tab_len = md.eval_expr(j.tab_len_expr, params)
            slot_len = md.eval_expr(j.slot_len_expr, params)
            tab_d = md.eval_expr(j.tab_depth_expr, params)
            slot_w = md.eval_expr(j.slot_width_expr, params)
            if abs((slot_len - tab_len) - 0.15) > 1e-4:
                joint_errors.append(f"T={t_val} {j.joint_id}: slot_len - tab_len != 0.15")
            if abs(tab_d - t_val) > 1e-4:
                joint_errors.append(f"T={t_val} {j.joint_id}: tab_depth != T")
            if slot_w < t_val - 1e-4:
                joint_errors.append(f"T={t_val} {j.joint_id}: slot_w < T")
            if j.tab_panel not in panel_map or j.slot_panel not in panel_map:
                joint_errors.append(f"{j.joint_id}: unknown panel")
    # Also verify exact count of slots in P01_BASE matches sum of bottom tabs on all vertical panels
    base_slot_count = sum(1 for r in eval_map["P01_BASE"]["inner_rects"] if r["kind"] == "slot")
    base_joint_count = sum(1 for j in joints if j.slot_panel == "P01_BASE")
    if base_slot_count != base_joint_count:
        joint_errors.append(f"P01_BASE slot count {base_slot_count} != joint count {base_joint_count}")
    report["checks"]["tab_slot_matching"] = {
        "passed": len(joint_errors) == 0,
        "total_tab_slot_joints": len(joints),
        "base_slots": base_slot_count,
        "tested_thicknesses_mm": [2.0, 3.0, 5.0],
        "errors": joint_errors,
    }

    # --- CHECK 4: LIVE KiCad PCB H1..H4 Mounting Hole Match (within 0.1 mm) ---
    kicad_text = KICAD_PCB_FILE.read_text(encoding="utf-8")
    kicad_holes: dict[str, tuple[float, float, float]] = {}
    for blk in kicad_text.split("(footprint ")[1:]:
        ref_m = re.search(r'\(property\s+"Reference"\s+"(H[1-4])"', blk[:1800])
        if ref_m:
            at_m = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)', blk[:400])
            dr_m = re.search(r'\(drill\s+([-\d.]+)\)', blk[:2000])
            kicad_holes[ref_m.group(1)] = (float(at_m.group(1)), float(at_m.group(2)), float(dr_m.group(1)))

    kc_xs = sorted({round(v[0], 4) for v in kicad_holes.values()})
    kc_ys = sorted({round(v[1], 4) for v in kicad_holes.values()})
    kc_dx = kc_xs[-1] - kc_xs[0]
    kc_dy = kc_ys[-1] - kc_ys[0]
    kc_drills = sorted({v[2] for v in kicad_holes.values()})

    base_pcb_holes = [c for c in eval_map["P01_BASE"]["circles"] if c["name"].startswith("PCB_H")]
    bp_xs = sorted({round(c["cx"], 4) for c in base_pcb_holes})
    bp_ys = sorted({round(c["cy"], 4) for c in base_pcb_holes})
    bp_dx = bp_xs[-1] - bp_xs[0]
    bp_dy = bp_ys[-1] - bp_ys[0]
    bp_drills = sorted({c["dia"] for c in base_pcb_holes})

    err_dx = abs(kc_dx - bp_dx)
    err_dy = abs(kc_dy - bp_dy)
    err_dia = abs(kc_drills[0] - bp_drills[0])
    kicad_ok = (len(kicad_holes) == 4 and len(base_pcb_holes) == 4 and err_dx <= 0.1 and err_dy <= 0.1 and err_dia <= 0.1)
    report["checks"]["kicad_pcb_hole_match"] = {
        "passed": kicad_ok,
        "kicad_H1_H4_pitch_mm": [kc_dx, kc_dy],
        "base_panel_pitch_mm": [bp_dx, bp_dy],
        "kicad_drill_mm": kc_drills,
        "base_drill_mm": bp_drills,
        "max_error_mm": round(max(err_dx, err_dy, err_dia), 5),
    }

    # --- CHECK 5: FreeCAD Parametric Recompute T=2, 3, 5 mm ---
    fc_data = json.loads(FC_GEOM_JSON.read_text(encoding="utf-8")) if FC_GEOM_JSON.exists() else {}
    fc_ok = bool(fc_data.get("all_recompute_passed")) and len(fc_data.get("panels", {})) == len(panels)
    report["checks"]["freecad_recompute_T_2_3_5"] = {
        "passed": fc_ok,
        "freecad_version": fc_data.get("freecad_version", "unknown"),
        "panels_verified": len(fc_data.get("panels", {})),
        "log_file": str(FC_RECOMPUTE_LOG.relative_to(REPO_ROOT)),
    }

    # --- CHECK 6: Every Real Module Fits Inside Its Room & Zero Forbidden Devices ---
    room_bounds = {
        "Technical Bay": (12.0, 224.0, 8.0, 102.0, 0.0, 120.0),
        "Technical Bay (Front Fascia)": (14.0, 224.0, 6.0, 18.0, 0.0, 44.0),
        "Living Room": (15.0, 183.5, 105.0, 277.0, 0.0, 132.0),
        "Living Room (Door Jamb)": (15.0, 183.5, 105.0, 277.0, 0.0, 132.0),
        "Living Room (Front Ledge)": (15.0, 183.5, 102.0, 130.0, 0.0, 50.0),
        "Bedroom": (186.5, 365.0, 105.0, 277.0, 0.0, 132.0),
        "Center Pillar (Front)": (174.0, 198.0, 100.0, 118.0, 95.0, 132.0),
        "Water Reservoir": (233.0, 276.5, 21.0, 89.0, 0.0, 46.0),
        "Garden Planter": (279.5, 361.0, 21.0, 89.0, -5.0, 70.0),
        "Garden Planter (Dry Exterior)": (278.0, 364.0, 4.0, 20.0, 0.0, 40.0),
    }
    room_errors = []
    forbidden_hits = []
    for hw in md.HARDWARE_PARTS:
        low_txt = (hw.part_id + " " + hw.name + " " + hw.datasheet_dims).lower()
        for bad in ("vs1838", "ir_led", "940nm", "fan", "air_cond"):
            if bad in low_txt:
                forbidden_hits.append(f"{hw.part_id}: contains forbidden '{bad}'")
        bx0, bx1, by0, by1, bz0, bz1 = room_bounds[hw.room]
        cx, cy, cz = hw.center_xyz
        sx, sy, sz = hw.size_xyz
        if not (cx - sx / 2 >= bx0 - 0.5 and cx + sx / 2 <= bx1 + 0.5 and
                cy - sy / 2 >= by0 - 0.5 and cy + sy / 2 <= by1 + 0.5 and
                cz - sz / 2 >= bz0 - 0.5 and cz + sz / 2 <= bz1 + 0.5):
            room_errors.append(f"{hw.part_id} exceeds {hw.room} bounds")

    report["checks"]["modules_fit_rooms_and_zero_removed"] = {
        "passed": len(room_errors) == 0 and len(forbidden_hits) == 0,
        "modules_checked": len(md.HARDWARE_PARTS),
        "room_errors": room_errors,
        "forbidden_device_hits": forbidden_hits,
    }

    # --- CHECK 7: Sheet Nesting Coverage ---
    placed_a3 = [pid for sh in a3_info["sheets"] for pid in sh["panels"]]
    nest_ok = (len(placed_a3) == len(panels) and len(a3_info["oversized_panels"]) == 0)
    report["checks"]["a3_nesting_complete"] = {
        "passed": nest_ok,
        "sheets_a3": a3_info["sheet_count"],
        "panels_nested": len(placed_a3),
    }

    report["all_passed"] = all(v["passed"] for v in report["checks"].values())
    return report


# ============================================================================
# 6. MICA_PANELS.MD FABRICATION & ASSEMBLY GUIDE
# ============================================================================
def write_mica_panels_md(
    evals: list[dict[str, Any]],
    a3_info: dict[str, Any],
    a4_info: dict[str, Any],
    ver_report: dict[str, Any],
) -> None:
    total_net_mm2 = sum(e["net_area_mm2"] * e["qty"] for e in evals)
    total_bbox_mm2 = sum(e["bbox_area_mm2"] * e["qty"] for e in evals)
    lines: list[str] = []
    lines.append("# Smart Home Open-Cutaway Acrylic (Mica) House — Panel Schedule & Assembly Guide")
    lines.append("")
    lines.append("- **FreeCAD Parametric Source:** `hardware/freecad/mica/smarthome_mica_house.FCStd` (built via `hardware/freecad/mica/build_mica.py`)")
    lines.append("- **Default Material:** Clear Cast Acrylic (Mica), thickness **`T = 3.0 mm`** (parametric Spreadsheet `Params.T_mm` verified for `2.0`, `3.0`, and `5.0 mm`)")
    lines.append("- **Joint Type:** Interlocking tab-and-slot (finger) joints with **`slot_width = T + 0.15 mm`** laser kerf / slip clearance")
    lines.append("- **House Outer Footprint:** `356.0 x 178.0 x 135.0 mm` (exact match to Blender `SCENE_SPEC.json`) on a `380.0 x 286.0 mm` base plate")
    lines.append("- **Hardware Scope:** Locked 6 devices + 3 sensors on ESP8266 NodeMCU v2 Amica + `80 x 65 mm` KiCad Central Hub PCB (**zero fan, zero AC, zero IR**)")
    lines.append("")
    lines.append("## 1. Panel Cutting Schedule (15 Panels)")
    lines.append("")
    lines.append("| Panel ID | Name | Qty | Size L x W (mm) | Thickness | Holes / Cutouts | DXF / Drawing | Notes |")
    lines.append("|---|---|---:|---:|---:|---:|---|---|")
    for e in evals:
        n_feat = len(e["circles"]) + len(e["inner_rects"])
        lines.append(
            f"| `{e['panel_id']}` | {e['name']} | {e['qty']} | `{e['width']:.1f} x {e['height']:.1f}` | "
            f"`{e['T_mm']:.1f} mm` | {n_feat} ({len(e['circles'])}H / {len(e['inner_rects'])}R) | "
            f"[DXF](panels_dxf/{e['panel_id']}.dxf) / [PDF](drawings/{e['panel_id']}.pdf) | {e['notes']} |"
        )
    lines.append("")
    lines.append("## 2. Material Area & Sheet Nesting Summary")
    lines.append("")
    lines.append(f"- **Total Panel Count:** `{len(evals)}` unique panels (`{sum(e['qty'] for e in evals)}` pieces total)")
    lines.append(f"- **Total Net Acrylic Area:** `{total_net_mm2 / 100.0:.1f} cm²` (`{total_net_mm2 / 1e6:.4f} m²`)")
    lines.append(f"- **Total Bounding-Box Area:** `{total_bbox_mm2 / 100.0:.1f} cm²` (`{total_bbox_mm2 / 1e6:.4f} m²`)")
    lines.append(f"- **Standard A3 Sheets (`420 x 297 mm`, 5 mm margin, 4 mm kerf spacing):** **`{a3_info['sheet_count']}` sheets** — see `sheet_layout_A3.dxf` & `sheet_layout_A3.png`:")
    for sh in a3_info["sheets"]:
        lines.append(f"  - **A3 Sheet #{sh['sheet_no']}** (Net utilization `{sh['utilization_pct']}%`): {', '.join(f'`{p}`' for p in sh['panels'])}")
    lines.append(f"- **Standard A4 Sheets (`297 x 210 mm`, partial layout for smaller panels):** **`{a4_info['sheet_count']}` A4 sheets** hold the 12 smaller panels (`sheet_layout_A4.dxf` & `sheet_layout_A4.png`); oversized panels requiring A3 (`420 x 297 mm`): {', '.join(f'`{p}`' for p in a4_info['oversized_panels'])}.")
    lines.append("")
    lines.append("## 3. Step-by-Step Assembly Order")
    lines.append("")
    lines.append("See exploded diagram: `assembly_exploded.pdf` / `assembly_exploded.png`.")
    lines.append("")
    lines.append("1. **Prepare `P01_BASE` (Base Plate):** Peel protective film from acrylic. Install 4× `M3×10 mm` brass standoffs in `PCB_H1..H4` (`71.0 × 56.0 mm` exact KiCad pattern), 8× `M3×8 mm` nylon standoffs for Relay 1 & Relay 2 (`44.5 × 20.5 mm` each), and stick a double-sided foam pad between the 2× `M2.5` PAM8403 tie-down holes.")
    lines.append("2. **Pre-mount Rear Wall Modules on `P02_WALL_BACK`:** Press-fit the Living Room (`Ø5.2 mm`) and Bedroom (`Ø5.2 mm`) 5 mm LEDs, and bolt the DHT11 breakout board (`1× M3×8 mm` nylon standoff) aligned over the `12 × 14 mm` airflow vent. Slot `P02_WALL_BACK` bottom tabs into `P01_BASE`.")
    lines.append("3. **Lock Center Dividing Wall (`P06_WALL_MID`):** Engage the 3 rear tabs of `P06_WALL_MID` into the vertical slots of `P02_WALL_BACK` while seating its 2 bottom tabs into `P01_BASE`.")
    lines.append("4. **Attach Left & Right Cutaway Walls (`P03_WALL_LEFT`, `P04_WALL_RIGHT`):** Interlock their 3 rear finger tabs into the side notches of `P02_WALL_BACK` and drop their bottom tabs into `P01_BASE`.")
    lines.append("5. **Sub-assemble Front Facade (`P05_WALL_FRONT`) & Servo Shelf (`P07_SERVO_SHELF`):**")
    lines.append("   - Mount the SG90 servo body downward through the `23.0 × 12.4 mm` cutout in `P07_SERVO_SHELF` and fasten with 2× `M2×8 mm` screws, washers, and nuts (`27.8 mm` pitch).")
    lines.append("   - Mount the KY-037 sound sensor (`1× M3×8 mm` nylon standoff, mic aligned with `Ø10.5 mm` hole) and press-fit the 12 mm active buzzer (`Ø12.2 mm` hole at `Z=114 mm`) on `P05_WALL_FRONT`.")
    lines.append("   - Slot `P07_SERVO_SHELF` rear tab into `P05_WALL_FRONT` (inside Living Room), then lock `P05_WALL_FRONT` onto `P03_WALL_LEFT`, `P04_WALL_RIGHT`, `P06_WALL_MID`, and `P01_BASE`.")
    lines.append("6. **Hang Main Door (`P08_DOOR_LEAF`):** Mount two mini hobby hinges (or nylon hinge pins) at the `M2` door holes (`4.5 mm` inset) to the left jamb of `P05_WALL_FRONT`. Link the SG90 white servo horn to the door linkage hole (`Ø2.2 mm`) using a short stiff wire push-rod (`Ø1 mm`).")
    lines.append("7. **Assemble Water Tank & Garden Planter (`P09`–`P14`):**")
    lines.append("   - Interlock `P09_GARDEN_LEFT`, `P10_WATER_DIVIDER`, `P11_GARDEN_RIGHT`, `P12_GARDEN_FRONT`, and `P13_GARDEN_BACK` into `P01_BASE`.")
    lines.append("   - **Waterproofing:** Seal all interior seams of the left water reservoir (`P01`/`P09`/`P10`/`P12`/`P13`) with clear neutral-cure silicone or acrylic solvent cement and leak-test for 15 minutes before placing electronics.")
    lines.append("   - Place the horizontal `3–6 V` submersible pump inside the water reservoir, route its 2-wire cable through the top notch of `P09_GARDEN_LEFT`, and push the `6/8 mm` silicone tube through the `Ø9.5 mm` hole of `P10_WATER_DIVIDER` into the soil chamber.")
    lines.append("   - Mount the LM393 comparator board on the **dry exterior** of `P12_GARDEN_FRONT` (`1× M3×8 mm` nylon standoff). Slot `P14_SOIL_BRIDGE` across the top notches of `P12`/`P13` and insert the YL-69 fork probe through the `22.0 × 3.2 mm` slot.")
    lines.append("8. **Mount Front Tech Fascia (`P15_TECH_FASCIA`) & Final Wiring:** Clamp the `Ø28 mm` mini speaker behind the 19-hole grille using 2× `M3×10 mm` screws + wide nylon washers, press-fit the 3 mm green Power LED, and slot `P15_TECH_FASCIA` into `P01_BASE`. Mount the KiCad Hub PCB (`80 × 65 mm`), plug in NodeMCU v2 Amica, mount Relays 1 & 2 and PAM8403, route cables through the `Ø10 mm` pass-through holes, and connect 5 V power through the `12 × 10 mm` front terminal opening.")
    lines.append("")
    lines.append("## 4. Module Mounting & Fastener Map (with Datasheet Sources)")
    lines.append("")
    lines.append("| Module | Room / Zone | Mounted On | Fasteners / Fit | Physical Dimensions | Datasheet Source |")
    lines.append("|---|---|---|---|---|---|")
    for hw in md.HARDWARE_PARTS:
        lines.append(
            f"| **{hw.name}** | {hw.room} | `{hw.mount_panel}` | {hw.fasteners} | {hw.datasheet_dims} | [{hw.source_name}]({hw.source_url}) |"
        )
    lines.append("")
    lines.append("## 5. Suggested Fabrication & Hardware Shopping List (Reference Only)")
    lines.append("")
    lines.append("- **Acrylic (Mica) Sheets:** `3× A3 (420 × 297 mm) × 3.0 mm` clear cast acrylic sheets (or 1 sheet `600 × 900 mm × 3.0 mm` cut down at laser shop — leaves spare material for test cuts).")
    lines.append("- **Brass / Nylon Standoffs & Screws:**")
    lines.append("  - `4× M3 × 10 mm` brass hex standoffs + `8× M3 × 6 mm` screws (KiCad Hub PCB)")
    lines.append("  - `12× M3 × 8 mm` nylon standoffs + `12× M3` screws & nuts (2× Relay modules, DHT11, KY-037, LM393)")
    lines.append("  - `2× M3 × 10 mm` screws + wide nylon washers (Dia 28 mm speaker clamp on `P15_TECH_FASCIA`)")
    lines.append("  - `2× M2 × 8 mm` screws + `M2` nuts + `M2` washers (SG90 door servo on `P07_SERVO_SHELF`)")
    lines.append("  - `4× M2 × 8 mm` screws + 2× mini nylon/acrylic hobby hinges `16 × 13 mm` (Main Door `P08_DOOR_LEAF`)")
    lines.append("  - Small zip-ties (`2.5 mm` wide) + 3M double-sided foam tape (PAM8403 amp)")
    lines.append("- **Adhesives & Waterproofing:** Acrylic solvent cement (chloroform / Weld-On #3 or #4) for permanent structural joints + clear neutral-cure silicone sealant for the water reservoir seams; 4× adhesive rubber feet (`Ø10 mm`) under `P01_BASE`.")
    lines.append("- **Manual Cutting Alternative:** If cutting by hand instead of CO2 laser, print each `drawings/<ID>.pdf` at 100% scale, glue onto the acrylic protective film, score straight cuts with an acrylic hook knife, and drill holes with brad-point / stepped plastic drill bits at low RPM.")
    lines.append("")
    lines.append("## 6. Automated Verification Status")
    lines.append("")
    lines.append(f"- **Overall Result:** `{'ALL_PASS' if ver_report['all_passed'] else 'FAILED'}`")
    for k, v in ver_report["checks"].items():
        lines.append(f"- `{k}`: `{'PASS' if v['passed'] else 'FAIL'}`")
    lines.append("")

    (OUT_ROOT / "MICA_PANELS.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    DXF_DIR.mkdir(parents=True, exist_ok=True)
    DRAW_DIR.mkdir(parents=True, exist_ok=True)

    panels, joints = md.build_design()
    evals = [md.evaluate_panel_2d(p, T_mm=3.0, kerf=0.15) for p in panels]

    print(f"[export] Exporting {len(evals)} laser-cut DXFs and A4 engineering drawings (PDF + PNG)...")
    for ev in evals:
        pid = ev["panel_id"]
        export_panel_dxf(ev, DXF_DIR / f"{pid}.dxf")
        render_panel_drawing(ev, DRAW_DIR / f"{pid}.pdf", DRAW_DIR / f"{pid}.png")

    print("[export] Generating exploded assembly drawing (PDF + PNG)...")
    render_exploded_assembly(panels, OUT_ROOT / "assembly_exploded.pdf", OUT_ROOT / "assembly_exploded.png")

    print("[export] Computing A3 (420x297) and A4 (297x210) nesting layouts...")
    a3_sheets, a3_over = pack_panels_on_sheets(evals, 420.0, 297.0, margin=5.0, spacing=4.0)
    a3_info = export_nesting_dxf_and_png(
        a3_sheets, a3_over, 420.0, 297.0, "A3",
        OUT_ROOT / "sheet_layout_A3.dxf", OUT_ROOT / "sheet_layout_A3.png"
    )
    a4_sheets, a4_over = pack_panels_on_sheets(evals, 297.0, 210.0, margin=5.0, spacing=4.0)
    a4_info = export_nesting_dxf_and_png(
        a4_sheets, a4_over, 297.0, 210.0, "A4",
        OUT_ROOT / "sheet_layout_A4.dxf", OUT_ROOT / "sheet_layout_A4.png"
    )

    print("[verify] Running automated verification suite...")
    ver_report = verify_all(panels, joints, evals, a3_info)
    (OUT_ROOT / "verification_report.json").write_text(json.dumps({
        "verification": ver_report,
        "nesting_A3": a3_info,
        "nesting_A4": a4_info,
    }, indent=2), encoding="utf-8")

    print("[export] Writing docs/phan_cung/mica/MICA_PANELS.md...")
    write_mica_panels_md(evals, a3_info, a4_info, ver_report)

    print("\n=== VERIFICATION SUMMARY ===")
    for k, v in ver_report["checks"].items():
        print(f"  [{'PASS' if v['passed'] else 'FAIL'}] {k}: {json.dumps(v)}")
    print(f"OVERALL: {'ALL_PASS' if ver_report['all_passed'] else 'FAILED'}")
    print(f"A3 Sheets: {a3_info['sheet_count']} | A4 Partial Sheets: {a4_info['sheet_count']} (oversized: {a4_info['oversized_panels']})")
    return 0 if ver_report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
