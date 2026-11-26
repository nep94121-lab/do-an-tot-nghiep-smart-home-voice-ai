"""Automated Verification, PrusaSlicer CLI Slicing & 3D Assembly Collision Checker.

Run modes:
    1. Per-part/shard verification + PrusaSlicer CLI slicing (System Python):
       python "hardware/in 3 d/scripts/verify_and_slice.py" --shard panels-std --out-shard <json>
    2. Full assembly BRep collision + split reconstruction check (FreeCADCmd):
       "C:\\Users\\LENOVO\\AppData\\Local\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe" "hardware/in 3 d/scripts/verify_and_slice.py" -- --assembly-check
    3. Merge all metadata + generate manifest.json, verification_report.json, and slicer preview PNG:
       python "hardware/in 3 d/scripts/verify_and_slice.py" --merge
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
from typing import Any

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
STEP_DIR = PRINT3D_ROOT / "STEP"
DRAW_DIR = PRINT3D_ROOT / "drawings"
PREV_DIR = PRINT3D_ROOT / "previews"
META_DIR = PRINT3D_ROOT / "build_meta"


def find_prusaslicer_cli() -> pathlib.Path:
    """Locate portable PrusaSlicer CLI installed in run dir or standard system locations."""
    search_roots = [
        pathlib.Path(r"C:\Users\LENOVO\datn-wt\agyfeat3_20261126\tools\prusaslicer"),
        pathlib.Path(r"C:\Program Files\Prusa3D\PrusaSlicer"),
        PRINT3D_ROOT / ".tools" / "prusaslicer",
    ]
    for root in search_roots:
        if root.exists():
            hits = list(root.rglob("prusa-slicer-console.exe"))
            if hits:
                return hits[0]
    raise FileNotFoundError("prusa-slicer-console.exe not found in expected tool directories")


def parse_gcode_metrics(gcode_text: str) -> dict[str, Any]:
    """Parse real PrusaSlicer G-code comments for print time, filament length/weight, layers, and XY bounds."""
    time_str = ""
    filament_mm = 0.0
    filament_g = 0.0
    layer_count = 0

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
        # 1.75 mm PLA filament: cross-section 2.4053 mm^2, density 1.24 g/cm^3
        filament_g = (filament_mm * math.pi * (1.75 / 2.0) ** 2 / 1000.0) * 1.24
    layer_count = len(re.findall(r"^;LAYER_CHANGE", gcode_text, flags=re.MULTILINE))

    # Convert time string like "1h 23m 45s" or "12m 30s" to seconds
    total_sec = 0
    for val, unit in re.findall(r"(\d+)\s*([dhms])", time_str):
        v = int(val)
        total_sec += v * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]

    return {
        "estimated_time_str": time_str or f"{total_sec}s",
        "estimated_time_sec": total_sec,
        "filament_mm": round(filament_mm, 1),
        "filament_g": round(filament_g, 2),
        "layer_count": layer_count,
    }


def slice_one_part(
    slicer_exe: pathlib.Path,
    part_id: str,
    cfg: pd_mod.PrintConfig,
    save_gcode_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Slice one STL headlessly with PrusaSlicer CLI on a 220x220x250 mm PLA 0.20mm profile."""
    stl_path = STL_DIR / f"{part_id}.stl"
    with tempfile.TemporaryDirectory(prefix=f"slice_{part_id}_") as td:
        td_path = pathlib.Path(td)
        out_gcode = save_gcode_path if save_gcode_path is not None else (td_path / f"{part_id}.gcode")
        out_gcode.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            str(slicer_exe),
            "--export-gcode",
            "--center", f"{cfg.bed_x / 2.0:.1f},{cfg.bed_y / 2.0:.1f}",
            "--bed-shape", f"0x0,{cfg.bed_x:.0f}x0,{cfg.bed_x:.0f}x{cfg.bed_y:.0f},0x{cfg.bed_y:.0f}",
            "--layer-height", "0.2",
            "--first-layer-height", "0.2",
            "--nozzle-diameter", "0.4",
            "--filament-diameter", "1.75",
            "--filament-density", "1.24",
            "--perimeters", "3",
            "--fill-density", "20%",
            "--fill-pattern", "gyroid",
            "--support-material=0",
            "--skirts", "1",
            "--skirt-distance", "2",
            "--output", str(out_gcode),
            str(stl_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        ok = proc.returncode == 0 and out_gcode.exists() and out_gcode.stat().st_size > 200
        metrics: dict[str, Any] = {}
        if ok:
            gtxt = out_gcode.read_text(encoding="utf-8", errors="ignore")
            metrics = parse_gcode_metrics(gtxt)
        return {
            "slice_ok": bool(ok),
            "slicer_returncode": int(proc.returncode),
            "slicer_stderr": proc.stderr.strip()[:400],
            **metrics,
        }


def render_slicer_gcode_preview(
    slicer_exe: pathlib.Path,
    part_ids: list[str],
    out_png: pathlib.Path,
    cfg: pd_mod.PrintConfig,
) -> pathlib.Path:
    """Slice real parts into G-code and render a 220x220 mm print-bed toolpath visualization PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Rectangle

    fig, axes = plt.subplots(1, len(part_ids), figsize=(6.2 * len(part_ids), 6.6), dpi=160)
    if len(part_ids) == 1:
        axes = [axes]
    fig.patch.set_facecolor("white")

    with tempfile.TemporaryDirectory(prefix="slicer_prev_") as td:
        td_path = pathlib.Path(td)
        for ax, pid in zip(axes, part_ids):
            gcode_p = td_path / f"{pid}.gcode"
            res = slice_one_part(slicer_exe, pid, cfg, save_gcode_path=gcode_p)
            gtxt = gcode_p.read_text(encoding="utf-8", errors="ignore")

            # Parse extrusion segments (G1 X.. Y.. E..) from first layer and top/mid layers
            segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
            cx, cy = 0.0, 0.0
            layer_idx = 0
            for line in gtxt.splitlines():
                if line.startswith(";LAYER_CHANGE"):
                    layer_idx += 1
                    continue
                if layer_idx > 2 and layer_idx != max(1, res.get("layer_count", 1) - 1):
                    continue
                if line.startswith("G1 ") or line.startswith("G0 "):
                    mx = re.search(r"X([0-9.\-]+)", line)
                    my = re.search(r"Y([0-9.\-]+)", line)
                    me = re.search(r"E([0-9.\-]+)", line)
                    nx = float(mx.group(1)) if mx else cx
                    ny = float(my.group(1)) if my else cy
                    if me and float(me.group(1)) > 0 and (abs(nx - cx) > 1e-4 or abs(ny - cy) > 1e-4):
                        segs.append(((cx, cy), (nx, ny)))
                    cx, cy = nx, ny

            # Draw 220x220 bed grid + 5mm safe margin box (210x210)
            ax.add_patch(Rectangle((0, 0), cfg.bed_x, cfg.bed_y, facecolor="#f4f7fb", edgecolor="#1b365d", lw=2.0))
            ax.add_patch(Rectangle(
                (cfg.bed_margin, cfg.bed_margin),
                cfg.usable_x,
                cfg.usable_y,
                facecolor="none",
                edgecolor="#27ae60",
                lw=1.3,
                ls="--",
            ))
            if segs:
                ax.add_collection(LineCollection(segs, colors="#e67e22", linewidths=0.65, alpha=0.9))

            ax.set_xlim(-8, cfg.bed_x + 8)
            ax.set_ylim(-8, cfg.bed_y + 8)
            ax.set_aspect("equal", adjustable="box")
            ax.grid(True, linestyle=":", color="#ccd", linewidth=0.5)
            ax.set_xlabel("X ban in (mm)", fontsize=9)
            ax.set_ylabel("Y ban in (mm)", fontsize=9)
            ax.set_title(
                f"{pid}\nPrusaSlicer 0.20mm | {res.get('estimated_time_str', '?')} | {res.get('filament_g', 0):.1f}g | {res.get('layer_count', 0)} lop",
                fontsize=9.5,
                fontweight="bold",
                color="#0f2b46",
            )

    fig.suptitle(
        "KIEM CHUNG CAT LOP PRUSASLICER CLI — BAN IN 220x220x250 mm (VUNG AN TOAN 210x210 mm, KHONG SUPPORT)",
        fontsize=11.5,
        fontweight="bold",
        color="#0b2540",
        y=0.98,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_png), format="PNG", dpi=160)
    plt.close(fig)
    return out_png


def verify_parts_and_slice(target_ids: list[str], out_shard: str = "") -> int:
    """Verify manifold, bed fit, Z=0 flat orientation, 3MF/STEP/drawing/preview presence, and PrusaSlicer CLI."""
    import trimesh

    cfg = pd_mod.PrintConfig()
    slicer_exe = find_prusaslicer_cli()
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    for pid in target_ids:
        meta_path = META_DIR / f"{pid}.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        stl_p = STL_DIR / f"{pid}.stl"
        mf_p = THREEMF_DIR / f"{pid}.3mf"
        step_p = STEP_DIR / f"{pid}.step"
        pdf_p = DRAW_DIR / f"{pid}.pdf"
        png_p = DRAW_DIR / f"{pid}.png"
        prev_p = PREV_DIR / f"{pid}.png"

        mesh = trimesh.load_mesh(str(stl_p), force="mesh")
        ext = [round(float(x), 3) for x in mesh.extents]
        z_min = round(float(mesh.bounds[0][2]), 4)
        bed_fit = (ext[0] <= cfg.usable_x + 0.05) and (ext[1] <= cfg.usable_y + 0.05) and (ext[2] <= cfg.usable_z + 0.05)
        flat_z0 = abs(z_min) <= 0.05
        files_ok = all(p.exists() and p.stat().st_size > 100 for p in (stl_p, mf_p, step_p, pdf_p, png_p, prev_p))

        slice_res = slice_one_part(slicer_exe, pid, cfg)
        all_ok = bool(mesh.is_watertight and mesh.is_volume and bed_fit and flat_z0 and files_ok and slice_res["slice_ok"])

        meta.update({
            "verified_watertight": bool(mesh.is_watertight),
            "verified_is_volume": bool(mesh.is_volume),
            "verified_bed_fit": bed_fit,
            "verified_flat_z0": flat_z0,
            "verified_files_complete": files_ok,
            **slice_res,
            "part_all_passed": all_ok,
        })
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        results.append(meta)
        status = "PASS" if all_ok else "FAIL"
        print(
            f"[{status}] {pid}: bbox={ext} wt={mesh.is_watertight} bed={bed_fit} "
            f"slice={slice_res['slice_ok']} time={slice_res.get('estimated_time_str')} fil={slice_res.get('filament_g')}g"
        )
        if not all_ok:
            failures.append(pid)

    if out_shard:
        op = pathlib.Path(out_shard)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps({
            "count": len(results),
            "passed": len(results) - len(failures),
            "failures": failures,
            "parts": results,
        }, indent=2), encoding="utf-8")

    return 1 if failures else 0


def _build_unengraved_piece_solid(piece: pd_mod.PanelPieceSpec, pspec: md.PanelSpec, cfg: pd_mod.PrintConfig, cache: dict[str, tuple[Any, dict[str, Any]]]) -> Any:
    """Build exact un-engraved BRep solid (strict superset of engraved STEP) for fast exact OCCT collision checks."""
    import FreeCAD
    import Part
    import build_print_parts as bpp

    if piece.source_panel_id not in cache:
        cache[piece.source_panel_id] = bpp.build_flat_panel_solid(pspec, cfg)
    full_solid, ev = cache[piece.source_panel_id]

    if piece.piece_count == 1:
        shape = full_solid.copy()
    else:
        u_lo, u_hi = piece.u_range
        v_lo, v_hi = piece.v_range
        seam_half_gap = 0.05
        m_u0 = (u_lo + seam_half_gap) if u_lo > 1e-3 else -2.0
        m_u1 = (u_hi - seam_half_gap) if u_hi < ev["width"] - 1e-3 else (ev["width"] + 2.0)
        m_v0 = (v_lo + seam_half_gap) if v_lo > 1e-3 else -2.0
        m_v1 = (v_hi - seam_half_gap) if v_hi < ev["height"] - 1e-3 else (ev["height"] + 2.0)
        mask = Part.makeBox(m_u1 - m_u0, m_v1 - m_v0, cfg.T_mm + 2.0, FreeCAD.Vector(m_u0, m_v0, -1.0))
        for dt in piece.dovetails:
            if dt.axis == "U":
                piece_is_plus = abs(u_lo - dt.cut_pos) < 1e-3
                piece_is_minus = abs(u_hi - dt.cut_pos) < 1e-3
            else:
                piece_is_plus = abs(v_lo - dt.cut_pos) < 1e-3
                piece_is_minus = abs(v_hi - dt.cut_pos) < 1e-3
            if not (piece_is_plus or piece_is_minus):
                continue
            owns_male = (piece_is_plus and dt.male_side == +1) or (piece_is_minus and dt.male_side == -1)
            if owns_male:
                mask = mask.fuse(bpp._make_dovetail_prism(dt, is_female=False, T_mm=cfg.T_mm))
            else:
                mask = mask.cut(bpp._make_dovetail_prism(dt, is_female=True, T_mm=cfg.T_mm))
        shape = full_solid.common(mask).removeSplitter()

    bb = shape.BoundBox
    shape.translate(FreeCAD.Vector(-bb.XMin, -bb.YMin, -bb.ZMin))
    return shape


def _build_unengraved_support_solid(sup: pd_mod.SupportSpec, cfg: pd_mod.PrintConfig) -> Any:
    """Build exact un-engraved support BRep solid (strict superset of engraved STEP) for fast OCCT collision checks."""
    import FreeCAD
    import Part
    import build_print_parts as bpp

    # Temporarily bypass engraving inside build_support_solid by monkeypatching safe_engrave_top_face
    orig_eng = bpp.safe_engrave_top_face
    try:
        bpp.safe_engrave_top_face = lambda shape, *a, **kw: (shape, True)
        shape, _meta = bpp.build_support_solid(sup, cfg)
        return shape
    finally:
        bpp.safe_engrave_top_face = orig_eng


def run_freecad_assembly_check() -> int:
    """Run exact 3D OCCT BRep collision & split-panel dimensional reconstruction check inside FreeCADCmd."""
    import FreeCAD
    import Part
    import render_previews as rp

    t0 = time.time()
    cfg = pd_mod.PrintConfig()
    ref_geom = pd_mod.load_freecad_reference_geometry()["panels"]
    pieces, _split_summary = pd_mod.build_panel_piece_specs(cfg)
    supports = pd_mod.build_support_specs(cfg)
    panels_raw, _ = md.build_design()
    panel_map = {ps.panel_id: ps for ps in panels_raw}

    # 1. Verify exact dimensional reconstruction from the actual exported STEP files
    print("  [1/3] Checking exported STEP bounding-box reconstruction...", flush=True)
    grouped_step_bbs: dict[str, list[Any]] = {}
    for piece in pieces:
        meta = json.loads((META_DIR / f"{piece.part_id}.json").read_text(encoding="utf-8"))
        sh = Part.Shape()
        sh.read(str(STEP_DIR / f"{piece.part_id}.step"))
        wsh = rp.place_piece_in_world(sh, meta)
        grouped_step_bbs.setdefault(piece.source_panel_id, []).append(wsh.BoundBox)

    recon_checks: list[dict[str, Any]] = []
    recon_failures: list[str] = []
    for src_id, bbs in grouped_step_bbs.items():
        xmin = min(b.XMin for b in bbs)
        ymin = min(b.YMin for b in bbs)
        zmin = min(b.ZMin for b in bbs)
        xmax = max(b.XMax for b in bbs)
        ymax = max(b.YMax for b in bbs)
        zmax = max(b.ZMax for b in bbs)
        ref = ref_geom[src_id]
        rmin = ref["bbox_min"]
        rmax = ref["bbox_max"]
        err_min = max(abs(xmin - rmin[0]), abs(ymin - rmin[1]), abs(zmin - rmin[2]))
        err_max = max(abs(xmax - rmax[0]), abs(ymax - rmax[1]), abs(zmax - rmax[2]))
        max_err = round(max(err_min, err_max), 4)
        ok = max_err <= 0.05
        recon_checks.append({
            "source_panel_id": src_id,
            "piece_count": len(bbs),
            "ref_bbox_min": rmin,
            "ref_bbox_max": rmax,
            "actual_bbox_min": [round(xmin, 4), round(ymin, 4), round(zmin, 4)],
            "actual_bbox_max": [round(xmax, 4), round(ymax, 4), round(zmax, 4)],
            "max_err_mm": max_err,
            "passed": ok,
        })
        if not ok:
            recon_failures.append(src_id)
    print(f"  [1/3] STEP reconstruction done in {round(time.time() - t0, 1)}s (failures={len(recon_failures)})", flush=True)

    # 2. Pairwise 3D BRep collision check using exact un-engraved superset solids (fast, zero spline-font bottleneck)
    print("  [2/3] Checking pairwise 3D BRep panel-vs-panel collisions...", flush=True)
    base_cache: dict[str, tuple[Any, dict[str, Any]]] = {}
    world_panel_solids: list[tuple[str, str, Any]] = []
    for piece in pieces:
        meta = json.loads((META_DIR / f"{piece.part_id}.json").read_text(encoding="utf-8"))
        sh = _build_unengraved_piece_solid(piece, panel_map[piece.source_panel_id], cfg, base_cache)
        wsh = rp.place_piece_in_world(sh, meta)
        world_panel_solids.append((piece.part_id, piece.source_panel_id, wsh))
        for idx, eo in enumerate(meta.get("extra_origins_xyz", []), 2):
            wsh2 = rp.place_piece_in_world(sh, meta, origin_override=eo)
            world_panel_solids.append((f"{piece.part_id}_inst{idx}", piece.source_panel_id, wsh2))

    panel_collisions: list[dict[str, Any]] = []
    max_panel_inter = 0.0
    n_p = len(world_panel_solids)
    for i in range(n_p):
        id_a, _, sa = world_panel_solids[i]
        bba = sa.BoundBox
        for j in range(i + 1, n_p):
            id_b, _, sb = world_panel_solids[j]
            bbb = sb.BoundBox
            if (
                bba.XMax <= bbb.XMin + 1e-4 or bbb.XMax <= bba.XMin + 1e-4
                or bba.YMax <= bbb.YMin + 1e-4 or bbb.YMax <= bba.YMin + 1e-4
                or bba.ZMax <= bbb.ZMin + 1e-4 or bbb.ZMax <= bba.ZMin + 1e-4
            ):
                continue
            vol = round(float(sa.common(sb).Volume), 4)
            if vol > max_panel_inter:
                max_panel_inter = vol
            if vol > 0.05:
                panel_collisions.append({"a": id_a, "b": id_b, "volume_mm3": vol})
    print(f"  [2/3] Panel collisions done in {round(time.time() - t0, 1)}s (coll={len(panel_collisions)}, max={max_panel_inter}mm3)", flush=True)

    # 3. Support vs panel & support vs support 3D collision check
    print("  [3/3] Checking 3D BRep support-vs-panel and support-vs-support collisions...", flush=True)
    world_support_solids: list[tuple[str, Any]] = []
    for sup in supports:
        meta = json.loads((META_DIR / f"{sup.part_id}.json").read_text(encoding="utf-8"))
        if meta.get("exclude_from_default_assembly"):
            continue
        sh = _build_unengraved_support_solid(sup, cfg)
        for idx, pl in enumerate(meta["assembly_placements"], 1):
            wsh = rp.place_support_in_world(sh, meta, pl)
            world_support_solids.append((f"{sup.part_id}_{idx}", wsh))

    support_collisions: list[dict[str, Any]] = []
    max_sup_inter = 0.0
    for sid, ss in world_support_solids:
        bbs = ss.BoundBox
        for pid, _, sp in world_panel_solids:
            bbp = sp.BoundBox
            if (
                bbs.XMax <= bbp.XMin + 1e-4 or bbp.XMax <= bbs.XMin + 1e-4
                or bbs.YMax <= bbp.YMin + 1e-4 or bbp.YMax <= bbs.YMin + 1e-4
                or bbs.ZMax <= bbp.ZMin + 1e-4 or bbp.ZMax <= bbs.ZMin + 1e-4
            ):
                continue
            vol = round(float(ss.common(sp).Volume), 4)
            if vol > max_sup_inter:
                max_sup_inter = vol
            if vol > 0.05:
                support_collisions.append({"support": sid, "panel": pid, "volume_mm3": vol})

    for i in range(len(world_support_solids)):
        id_a, sa = world_support_solids[i]
        bba = sa.BoundBox
        for j in range(i + 1, len(world_support_solids)):
            id_b, sb = world_support_solids[j]
            bbb = sb.BoundBox
            if (
                bba.XMax <= bbb.XMin + 1e-4 or bbb.XMax <= bba.XMin + 1e-4
                or bba.YMax <= bbb.YMin + 1e-4 or bbb.YMax <= bba.YMin + 1e-4
                or bba.ZMax <= bbb.ZMin + 1e-4 or bbb.ZMax <= bba.ZMin + 1e-4
            ):
                continue
            vol = round(float(sa.common(sb).Volume), 4)
            if vol > max_sup_inter:
                max_sup_inter = vol
            if vol > 0.05:
                support_collisions.append({"support_a": id_a, "support_b": id_b, "volume_mm3": vol})

    # 4. Also check optional 1-piece cradles (SUP07 & SUP09) against all panels
    sup_by_id = {s.part_id: s for s in supports}
    for opt_id in ("SUP07_PCB_CARRIER_FRAME_90X70", "SUP09_RELAY_CADDY_44P5X20P5"):
        meta = json.loads((META_DIR / f"{opt_id}.json").read_text(encoding="utf-8"))
        sh = _build_unengraved_support_solid(sup_by_id[opt_id], cfg)
        for idx, pl in enumerate(meta["assembly_placements"], 1):
            wsh = rp.place_support_in_world(sh, meta, pl)
            bbs = wsh.BoundBox
            for pid, _, sp in world_panel_solids:
                bbp = sp.BoundBox
                if (
                    bbs.XMax <= bbp.XMin + 1e-4 or bbp.XMax <= bbs.XMin + 1e-4
                    or bbs.YMax <= bbp.YMin + 1e-4 or bbp.YMax <= bbs.YMin + 1e-4
                    or bbs.ZMax <= bbp.ZMin + 1e-4 or bbp.ZMax <= bbs.ZMin + 1e-4
                ):
                    continue
                vol = round(float(wsh.common(sp).Volume), 4)
                if vol > 0.05:
                    support_collisions.append({"optional_support": f"{opt_id}_{idx}", "panel": pid, "volume_mm3": vol})

    asm_report = {
        "panel_instances_checked": len(world_panel_solids),
        "support_instances_checked": len(world_support_solids),
        "elapsed_sec": round(time.time() - t0, 2),
        "reconstruction_checks": recon_checks,
        "reconstruction_failures": recon_failures,
        "panel_collisions": panel_collisions,
        "max_panel_intersection_mm3": max_panel_inter,
        "support_collisions": support_collisions,
        "max_support_intersection_mm3": max_sup_inter,
        "assembly_passed": (len(recon_failures) == 0 and len(panel_collisions) == 0 and len(support_collisions) == 0),
    }
    (META_DIR / "_assembly_check.json").write_text(json.dumps(asm_report, indent=2), encoding="utf-8")
    print(
        f"ASSEMBLY_CHECK: passed={asm_report['assembly_passed']} elapsed={asm_report['elapsed_sec']}s "
        f"recon_fail={len(recon_failures)} panel_coll={len(panel_collisions)} (max={max_panel_inter}mm3) "
        f"sup_coll={len(support_collisions)} (max={max_sup_inter}mm3)",
        flush=True,
    )
    if panel_collisions:
        print("  PANEL COLLISIONS:", panel_collisions[:5], flush=True)
    if support_collisions:
        print("  SUPPORT COLLISIONS:", support_collisions[:5], flush=True)
    if recon_failures:
        print("  RECON FAILURES:", recon_failures, flush=True)
    return 0 if asm_report["assembly_passed"] else 1


def merge_manifest_and_report() -> int:
    """Aggregate all build_meta/*.json + _assembly_check.json into manifest.json & verification_report.json."""
    cfg = pd_mod.PrintConfig()
    pieces, split_summary = pd_mod.build_panel_piece_specs(cfg)
    supports = pd_mod.build_support_specs(cfg)
    all_ids = [p.part_id for p in pieces] + [s.part_id for s in supports]

    parts_meta: list[dict[str, Any]] = []
    missing: list[str] = []
    failed_parts: list[str] = []
    total_time_sec = 0
    total_fil_g = 0.0

    for pid in all_ids:
        mp = META_DIR / f"{pid}.json"
        if not mp.exists():
            missing.append(pid)
            continue
        m = json.loads(mp.read_text(encoding="utf-8"))
        parts_meta.append(m)
        qty = int(m.get("qty", 1))
        total_time_sec += int(m.get("estimated_time_sec", 0)) * qty
        total_fil_g += float(m.get("filament_g", 0.0)) * qty
        if not m.get("part_all_passed", False):
            failed_parts.append(pid)

    asm_path = META_DIR / "_assembly_check.json"
    asm_data = json.loads(asm_path.read_text(encoding="utf-8")) if asm_path.exists() else {"assembly_passed": False}

    # Generate slicer preview image across 3 representative parts (1 standard, 1 split piece, 1 support)
    slicer_exe = find_prusaslicer_cli()
    slicer_prev = render_slicer_gcode_preview(
        slicer_exe,
        ["P16_PCB_PLATE", "P02_WALL_BACK_piece1of2", "SUP07_PCB_CARRIER_FRAME_90X70"],
        PREV_DIR / "_slicer_preview.png",
        cfg,
    )

    manifest = {
        "printer_bed_mm": [cfg.bed_x, cfg.bed_y, cfg.bed_z],
        "usable_bed_mm": [cfg.usable_x, cfg.usable_y, cfg.usable_z],
        "dovetail_clearance_mm": cfg.dovetail_clearance,
        "engrave_depth_mm": cfg.engrave_depth,
        "unique_source_panels": len(split_summary),
        "panel_piece_files": len(pieces),
        "support_files": len(supports),
        "total_printable_files": len(all_ids),
        "total_estimated_print_hours": round(total_time_sec / 3600.0, 2),
        "total_estimated_filament_g": round(total_fil_g, 1),
        "split_summary": split_summary,
        "parts": parts_meta,
    }
    (PRINT3D_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    all_passed = (len(missing) == 0 and len(failed_parts) == 0 and bool(asm_data.get("assembly_passed", False)))
    ver_report = {
        "all_passed": all_passed,
        "slicer_cli": str(slicer_exe.name),
        "total_expected_files": len(all_ids),
        "verified_files": len(parts_meta),
        "missing_files": missing,
        "failed_parts": failed_parts,
        "all_watertight": all(m.get("verified_watertight", False) for m in parts_meta),
        "all_bed_fit": all(m.get("verified_bed_fit", False) for m in parts_meta),
        "all_flat_z0": all(m.get("verified_flat_z0", False) for m in parts_meta),
        "all_sliced_ok": all(m.get("slice_ok", False) for m in parts_meta),
        "all_engraved_ok": all(m.get("engraved_ok", False) for m in parts_meta),
        "slicer_preview_png": f"previews/{slicer_prev.name}",
        "assembly": asm_data,
    }
    (PRINT3D_ROOT / "verification_report.json").write_text(json.dumps(ver_report, indent=2), encoding="utf-8")
    print(f"MERGED: all_passed={all_passed} files={len(parts_meta)}/{len(all_ids)} total_hours={manifest['total_estimated_print_hours']}h fil={manifest['total_estimated_filament_g']}g")
    return 0 if all_passed else 1


def parse_args() -> argparse.Namespace:
    argv = sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = [a for a in argv if not a.endswith(".py")]
    ap = argparse.ArgumentParser(description="Verify meshes, slice with PrusaSlicer CLI, and check 3D assembly")
    ap.add_argument("--parts", type=str, default=os.environ.get("PRINT3D_PARTS", ""), help="Comma-separated part_ids")
    ap.add_argument("--shard", type=str, default=os.environ.get("PRINT3D_SHARD", ""), help="Named shard")
    ap.add_argument("--out-shard", type=str, default=os.environ.get("PRINT3D_OUT_SHARD", ""), help="Optional output shard report JSON path")
    ap.add_argument("--assembly-check", action="store_true", default=(os.environ.get("PRINT3D_ASSEMBLY_CHECK", "") == "1"), help="Run inside FreeCADCmd for 3D BRep collision check")
    ap.add_argument("--merge", action="store_true", help="Merge all part metadata into manifest.json & verification_report.json")
    args, _unknown = ap.parse_known_args(argv)
    return args


def main() -> int:
    args = parse_args()
    if args.assembly_check:
        return run_freecad_assembly_check()
    if args.merge:
        return merge_manifest_and_report()

    cfg = pd_mod.PrintConfig()
    pieces, _ = pd_mod.build_panel_piece_specs(cfg)
    supports = pd_mod.build_support_specs(cfg)
    if args.shard:
        target_ids = pd_mod.get_swarm_shards(cfg)[args.shard]
    elif args.parts:
        target_ids = [s.strip() for s in args.parts.split(",") if s.strip()]
    else:
        target_ids = [p.part_id for p in pieces] + [s.part_id for s in supports]
    return verify_parts_and_slice(target_ids, out_shard=args.out_shard)


if __name__ == "__main__" or any(pathlib.Path(a).stem == __name__ for a in sys.argv):
    rc = main()
    if rc != 0:
        raise SystemExit(rc)
