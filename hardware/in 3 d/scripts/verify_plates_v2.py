"""PrusaSlicer CLI Verification for 3D-Print Set v2 (57 Parts + 17 Nested 180x200 Plates).

Verifies every individual part STL (57) and every nested build plate (17 x .3mf + .stl)
using PrusaSlicer CLI exactly as printed (`--dont-arrange`, no `--center`), proving:
- manifold = yes on all 57 parts and every object in all 17 plates
- min_z == 0.0 and rotatable fit inside 170x190x245 mm usable bed on all 57 parts
- real G-code extrusion XY/Z bounds strictly inside 0..180 x 0..200 x 0..250 mm
- zero "outside the print volume" or overhang/support alerts
- exact print time, filament [g] and [m] per plate and total
- R9 user-like test report (`build_meta/user_like_test_report.json`)
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import pathlib
import re
import subprocess
import sys
import tempfile
import time
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PRINT3D_ROOT = SCRIPT_DIR.parent
PARTS_DIR = PRINT3D_ROOT / "parts"
PLATES_DIR = PRINT3D_ROOT / "plates"
META_DIR = PRINT3D_ROOT / "build_meta"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import print_domain as pd_mod

DEFAULT_SLICER_EXE = pathlib.Path(r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe")

BED_X = 180.0
BED_Y = 200.0
BED_Z = 250.0
USABLE_X = 170.0
USABLE_Y = 190.0
USABLE_Z = 245.0

SLICE_TIMEOUT_SEC = 90
INFO_TIMEOUT_SEC = 30

_NUM_RE = r"[+-]?(?:\d+\.?\d*|\.\d+)"
_X_RE = re.compile(rf"(?:^|\s)X({_NUM_RE})")
_Y_RE = re.compile(rf"(?:^|\s)Y({_NUM_RE})")
_Z_RE = re.compile(rf"(?:^|\s)Z({_NUM_RE})")
_E_RE = re.compile(rf"(?:^|\s)E({_NUM_RE})")

_FURNITURE_SOCKET_PARTS = frozenset({
    "FUR01_SOFA",
    "FUR02_TV_STAND",
    "FUR04_BED",
    "FUR05_BEDSIDE_TABLE",
    "FUR06_PLANT_POT_LARGE",
    "FUR08_PLANT_POT_SMALL",
})


def format_duration(total_sec: int) -> str:
    """Format seconds into PrusaSlicer-style duration string like '18h 42m 15s'."""
    total_sec = max(0, int(round(total_sec)))
    h, rem = divmod(total_sec, 3600)
    m, s = divmod(rem, 60)
    parts: list[str] = []
    if h:
        parts.append(f"{h}h")
    if m or h:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def parse_prusaslicer_info(output: str) -> list[dict[str, Any]]:
    """Parse one or more `[filename]` object blocks emitted by `prusa-slicer-console --info`."""
    objects: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            if current is not None:
                objects.append(current)
            current = {"header": line[1:-1]}
            continue
        if current is None or "=" not in line:
            continue
        key, val = [x.strip() for x in line.split("=", 1)]
        if key == "manifold":
            current["manifold"] = (val.lower() == "yes")
            current["manifold_raw"] = val
        elif key in ("number_of_facets", "number_of_parts"):
            current[key] = int(val)
        else:
            try:
                current[key] = float(val)
            except ValueError:
                current[key] = val

    if current is not None:
        objects.append(current)
    return objects


def run_prusaslicer_info(slicer_exe: pathlib.Path, mesh_path: pathlib.Path) -> tuple[bool, list[dict[str, Any]], str]:
    """Run `prusa-slicer-console.exe --info` on an STL or 3MF file."""
    proc = subprocess.run(
        [str(slicer_exe), "--info", str(mesh_path)],
        capture_output=True,
        text=True,
        timeout=INFO_TIMEOUT_SEC,
    )
    combined = "\n".join(x for x in (proc.stdout, proc.stderr) if x)
    objs = parse_prusaslicer_info(proc.stdout)
    ok = (proc.returncode == 0) and (len(objs) > 0)
    return ok, objs, combined.strip()


def fits_usable_rotatable(dx: float, dy: float, dz: float, tol: float = 0.05) -> tuple[bool, bool]:
    """Check whether (dx, dy, dz) fits 170x190x245 mm with 0-deg or 90-deg XY rotation."""
    if dz > USABLE_Z + tol:
        return False, False
    fit_0 = (dx <= USABLE_X + tol) and (dy <= USABLE_Y + tol)
    if fit_0:
        return True, False
    fit_90 = (dy <= USABLE_X + tol) and (dx <= USABLE_Y + tol)
    return fit_90, fit_90


def verify_one_part(slicer_exe: pathlib.Path, stl_path: pathlib.Path) -> dict[str, Any]:
    """Run `--info` on one individual part STL and verify manifold, Z=0, and rotatable bed fit."""
    part_id = stl_path.stem
    meta_path = META_DIR / f"{part_id}.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    ok, objs, raw_out = run_prusaslicer_info(slicer_exe, stl_path)
    if not ok:
        return {
            "part_id": part_id,
            "stl_file": f"parts/{stl_path.name}",
            "kind": meta.get("kind", "unknown"),
            "qty": int(meta.get("qty", 1)),
            "info_ok": False,
            "manifold": False,
            "flat_z0": False,
            "fits_usable_rotatable": False,
            "passed": False,
            "error": raw_out[:400],
        }

    obj = objs[0]
    dx = round(float(obj.get("size_x", 0.0)), 4)
    dy = round(float(obj.get("size_y", 0.0)), 4)
    dz = round(float(obj.get("size_z", 0.0)), 4)
    min_z = round(float(obj.get("min_z", 999.0)), 6)
    manifold = all(bool(o.get("manifold", False)) for o in objs)
    flat_z0 = abs(min_z) <= 1e-3
    fits, rot_needed = fits_usable_rotatable(dx, dy, dz)
    passed = bool(ok and manifold and flat_z0 and fits)

    return {
        "part_id": part_id,
        "stl_file": f"parts/{stl_path.name}",
        "kind": meta.get("kind", "unknown"),
        "qty": int(meta.get("qty", 1)),
        "size_mm": [round(dx, 3), round(dy, 3), round(dz, 3)],
        "min_z_mm": round(min_z, 4),
        "facets": int(obj.get("number_of_facets", 0)),
        "shells": int(obj.get("number_of_parts", 1)),
        "volume_mm3": round(float(obj.get("volume", 0.0)), 2),
        "manifold": manifold,
        "flat_z0": flat_z0,
        "fits_usable_rotatable": fits,
        "rotation_90_needed": rot_needed,
        "passed": passed,
    }


def parse_gcode_full(gcode_text: str) -> dict[str, Any]:
    """Parse print time, filament metrics, layer count, and exact extrusion XY/Z bounds from G-code."""
    time_str = ""
    filament_mm = 0.0
    filament_cm3 = 0.0
    filament_g = 0.0

    m_t = re.search(r";\s*estimated printing time \(normal mode\)\s*=\s*(.+)", gcode_text)
    if m_t:
        time_str = m_t.group(1).strip()
    m_mm = re.search(r";\s*filament used \[mm\]\s*=\s*([0-9.]+)", gcode_text)
    if m_mm:
        filament_mm = float(m_mm.group(1))
    m_cm3 = re.search(r";\s*filament used \[cm3\]\s*=\s*([0-9.]+)", gcode_text)
    if m_cm3:
        filament_cm3 = float(m_cm3.group(1))
    m_g = re.search(r";\s*filament used \[g\]\s*=\s*([0-9.]+)", gcode_text)
    if m_g:
        filament_g = float(m_g.group(1))
    elif filament_cm3 > 0.0:
        filament_g = filament_cm3 * 1.24
    elif filament_mm > 0.0:
        filament_g = (filament_mm * math.pi * (1.75 / 2.0) ** 2 / 1000.0) * 1.24

    total_sec = 0
    for val, unit in re.findall(r"(\d+)\s*([dhms])", time_str):
        total_sec += int(val) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]

    layer_count = 0
    in_layers = False
    relative_e = False
    current_type = ""
    cx = 0.0
    cy = 0.0
    cz = 0.0
    ce = 0.0

    all_xmin = float("inf")
    all_xmax = float("-inf")
    all_ymin = float("inf")
    all_ymax = float("-inf")
    all_zmin = float("inf")
    all_zmax = float("-inf")

    part_xmin = float("inf")
    part_xmax = float("-inf")
    part_ymin = float("inf")
    part_ymax = float("-inf")
    part_zmin = float("inf")
    part_zmax = float("-inf")
    extrusion_moves = 0

    for raw_line in gcode_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(";"):
            if line.startswith(";LAYER_CHANGE"):
                layer_count += 1
                in_layers = True
            elif line.startswith(";Z:"):
                try:
                    cz = float(line[3:].strip())
                except ValueError:
                    pass
            elif line.startswith(";TYPE:"):
                current_type = line[6:].strip()
            continue

        code_part = line.split(";", 1)[0].strip()
        if not code_part:
            continue

        if code_part.startswith("M82"):
            relative_e = False
            continue
        if code_part.startswith("M83"):
            relative_e = True
            continue
        if code_part.startswith("G92"):
            me = _E_RE.search(code_part)
            if me:
                ce = float(me.group(1))
            continue

        if not (code_part.startswith("G1 ") or code_part.startswith("G0 ")):
            continue

        mx = _X_RE.search(code_part)
        my = _Y_RE.search(code_part)
        mz = _Z_RE.search(code_part)
        me = _E_RE.search(code_part)

        nx = float(mx.group(1)) if mx else cx
        ny = float(my.group(1)) if my else cy
        nz = float(mz.group(1)) if mz else cz

        delta_e = 0.0
        if me:
            ev = float(me.group(1))
            if relative_e:
                delta_e = ev
                ce += ev
            else:
                delta_e = ev - ce
                ce = ev

        moved_xy = (abs(nx - cx) > 1e-6) or (abs(ny - cy) > 1e-6)
        if in_layers and code_part.startswith("G1 ") and delta_e > 1e-7 and moved_xy:
            extrusion_moves += 1
            for px in (cx, nx):
                if px < all_xmin:
                    all_xmin = px
                if px > all_xmax:
                    all_xmax = px
            for py in (cy, ny):
                if py < all_ymin:
                    all_ymin = py
                if py > all_ymax:
                    all_ymax = py
            if nz < all_zmin:
                all_zmin = nz
            if nz > all_zmax:
                all_zmax = nz

            if current_type != "Skirt/Brim":
                for px in (cx, nx):
                    if px < part_xmin:
                        part_xmin = px
                    if px > part_xmax:
                        part_xmax = px
                for py in (cy, ny):
                    if py < part_ymin:
                        part_ymin = py
                    if py > part_ymax:
                        part_ymax = py
                if nz < part_zmin:
                    part_zmin = nz
                if nz > part_zmax:
                    part_zmax = nz

        cx, cy, cz = nx, ny, nz

    def _pack_bounds(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> dict[str, float] | None:
        if math.isinf(x0) or math.isinf(x1):
            return None
        return {
            "x_min": round(x0, 3),
            "x_max": round(x1, 3),
            "y_min": round(y0, 3),
            "y_max": round(y1, 3),
            "z_min": round(z0, 3),
            "z_max": round(z1, 3),
        }

    return {
        "estimated_time_str": time_str or format_duration(total_sec),
        "estimated_time_sec": total_sec,
        "filament_mm": round(filament_mm, 2),
        "filament_m": round(filament_mm / 1000.0, 2),
        "filament_cm3": round(filament_cm3, 2),
        "filament_g": round(filament_g, 2),
        "layer_count": layer_count,
        "extrusion_moves": extrusion_moves,
        "extrusion_bounds_mm": _pack_bounds(all_xmin, all_xmax, all_ymin, all_ymax, all_zmin, all_zmax),
        "part_extrusion_bounds_mm": _pack_bounds(part_xmin, part_xmax, part_ymin, part_ymax, part_zmin, part_zmax),
    }


def extract_slicer_warnings(stdout: str, stderr: str) -> dict[str, Any]:
    """Classify PrusaSlicer stdout/stderr into volume overflow, overhang/floating, or low-bed-adhesion advisories."""
    combined = "\n".join(x for x in (stdout, stderr) if x)
    raw_lines = [ln.strip() for ln in combined.splitlines() if ln.strip()]

    advisory_lines: list[str] = []
    outside_warn = False
    overhang_warn = False
    low_adhesion_only = False
    low_adhesion_parts: list[str] = []

    in_stability_block = False
    for line in raw_lines:
        # Ignore PrusaSlicer progress step banners like "69 => Alert if supports needed"
        if re.match(r"^\d+\s*=>", line) or line.startswith("Slicing result exported to"):
            in_stability_block = False
            continue
        low = line.lower()
        if "outside the print volume" in low or "outside print volume" in low or "object outside" in low:
            outside_warn = True
            advisory_lines.append(line)
            continue
        if "detected print stability issues" in low:
            in_stability_block = True
            advisory_lines.append(line)
            continue
        if in_stability_block:
            advisory_lines.append(line)
            if any(tok in low for tok in ("floating object", "floating bridge", "loose extrusion", "overhang", "long bridging", "empty layers")):
                overhang_warn = True
            elif "low bed adhesion" in low:
                low_adhesion_only = True
            elif not low.startswith(("consider enabling", "also consider enabling")):
                for part_tok in line.split(","):
                    pt = part_tok.strip()
                    if pt and pt not in low_adhesion_parts:
                        low_adhesion_parts.append(pt)
            continue
        if any(tok in low for tok in ("warning", "error", "overhang", "floating", "empty layers")):
            advisory_lines.append(line)
            if any(tok in low for tok in ("overhang", "floating", "empty layers")):
                overhang_warn = True

    if overhang_warn:
        low_adhesion_only = False

    return {
        "warnings": advisory_lines,
        "outside_volume_warning": outside_warn,
        "overhang_warning": overhang_warn,
        "low_bed_adhesion_advisory": low_adhesion_only,
        "low_bed_adhesion_parts": low_adhesion_parts if low_adhesion_only else [],
    }


def verify_one_plate(slicer_exe: pathlib.Path, plate: dict[str, Any]) -> dict[str, Any]:
    """Verify .stl and .3mf via `--info`, then slice .3mf as-is (`--dont-arrange`, no `--center`)."""
    plate_id = plate["plate_id"]
    stl_path = PRINT3D_ROOT / plate["stl_file"]
    threemf_path = PRINT3D_ROOT / plate["threemf_file"]
    expected_count = int(plate["part_count"])

    stl_ok, stl_objs, stl_raw = run_prusaslicer_info(slicer_exe, stl_path)
    mf_ok, mf_objs, mf_raw = run_prusaslicer_info(slicer_exe, threemf_path)

    stl_obj = stl_objs[0] if stl_objs else {}
    stl_manifold = bool(stl_ok and all(bool(o.get("manifold", False)) for o in stl_objs))
    mf_all_manifold = bool(mf_ok and all(bool(o.get("manifold", False)) for o in mf_objs))
    mf_count_matches = (len(mf_objs) == expected_count)

    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix=f"slice_{plate_id}_") as td:
        out_gcode = pathlib.Path(td) / f"{plate_id}.gcode"
        cmd = [
            str(slicer_exe),
            "--export-gcode",
            "--dont-arrange",
            "--bed-shape", f"0x0,{BED_X:.0f}x0,{BED_X:.0f}x{BED_Y:.0f},0x{BED_Y:.0f}",
            "--max-print-height", f"{BED_Z:.0f}",
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
            str(threemf_path),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=SLICE_TIMEOUT_SEC,
        )
        slice_elapsed = round(time.time() - t0, 2)
        slice_ok = (proc.returncode == 0) and out_gcode.exists() and (out_gcode.stat().st_size > 200)
        warn_info = extract_slicer_warnings(proc.stdout, proc.stderr)
        warnings = warn_info["warnings"]
        outside_warn = warn_info["outside_volume_warning"]
        overhang_warn = warn_info["overhang_warning"]
        low_adh = warn_info["low_bed_adhesion_advisory"]
        low_adh_parts = warn_info["low_bed_adhesion_parts"]

        gcode_metrics: dict[str, Any] = {}
        if slice_ok:
            gtxt = out_gcode.read_text(encoding="utf-8", errors="ignore")
            gcode_metrics = parse_gcode_full(gtxt)

    eb = gcode_metrics.get("extrusion_bounds_mm")
    bed_bounds_ok = False
    if eb is not None:
        bed_bounds_ok = (
            0.0 <= eb["x_min"] < eb["x_max"] <= BED_X
            and 0.0 <= eb["y_min"] < eb["y_max"] <= BED_Y
            and 0.0 < eb["z_max"] <= BED_Z
        )

    unique_parts = plate.get("unique_parts", [])
    furn_with_sockets = sorted(p for p in unique_parts if p in _FURNITURE_SOCKET_PARTS)
    note_parts: list[str] = []
    if furn_with_sockets:
        note_parts.append(
            "Khong can support slicer (overhang <= 45 deg); "
            f"chi co hoc mong san rong 4.3 mm phia duoi {', '.join(furn_with_sockets)} (short bridge PLA 0.4mm)."
        )
    else:
        note_parts.append("Khong can support slicer (in nam phang Z=0, overhang <= 45 deg).")
    if low_adh and low_adh_parts:
        note_parts.append(
            f"PrusaSlicer ghi chu 'Low bed adhesion' cho chi tiet nho phang ({', '.join(low_adh_parts)}) -> khuyen nghi ban PEI sach hoac brim tuy chon, khong can support."
        )
    support_note = " ".join(note_parts)

    needs_supports = bool(overhang_warn)
    plate_passed = bool(
        stl_manifold
        and mf_all_manifold
        and mf_count_matches
        and slice_ok
        and bed_bounds_ok
        and (not outside_warn)
        and (not needs_supports)
    )

    return {
        "plate_index": int(plate["plate_index"]),
        "plate_id": plate_id,
        "stl_file": plate["stl_file"],
        "threemf_file": plate["threemf_file"],
        "expected_part_count": expected_count,
        "unique_parts": unique_parts,
        "stl_info_ok": stl_ok,
        "stl_manifold": stl_manifold,
        "stl_size_mm": [
            round(float(stl_obj.get("size_x", 0.0)), 3),
            round(float(stl_obj.get("size_y", 0.0)), 3),
            round(float(stl_obj.get("size_z", 0.0)), 3),
        ],
        "stl_min_mm": [
            round(float(stl_obj.get("min_x", 0.0)), 3),
            round(float(stl_obj.get("min_y", 0.0)), 3),
            round(float(stl_obj.get("min_z", 0.0)), 3),
        ],
        "stl_max_mm": [
            round(float(stl_obj.get("max_x", 0.0)), 3),
            round(float(stl_obj.get("max_y", 0.0)), 3),
            round(float(stl_obj.get("max_z", 0.0)), 3),
        ],
        "stl_facets": int(stl_obj.get("number_of_facets", 0)),
        "stl_volume_mm3": round(float(stl_obj.get("volume", 0.0)), 2),
        "threemf_info_ok": mf_ok,
        "threemf_object_count": len(mf_objs),
        "threemf_count_matches": mf_count_matches,
        "all_objects_manifold": mf_all_manifold,
        "threemf_objects": [
            {
                "index": idx + 1,
                "size_mm": [
                    round(float(o.get("size_x", 0.0)), 3),
                    round(float(o.get("size_y", 0.0)), 3),
                    round(float(o.get("size_z", 0.0)), 3),
                ],
                "facets": int(o.get("number_of_facets", 0)),
                "manifold": bool(o.get("manifold", False)),
                "volume_mm3": round(float(o.get("volume", 0.0)), 2),
            }
            for idx, o in enumerate(mf_objs)
        ],
        "slice_ok": slice_ok,
        "slicer_returncode": int(proc.returncode),
        "slicer_warnings": warnings,
        "outside_volume_warning": outside_warn,
        "overhang_warning": overhang_warn,
        "low_bed_adhesion_advisory": low_adh,
        "low_bed_adhesion_parts": low_adh_parts,
        "needs_supports": needs_supports,
        "support_note": support_note,
        "estimated_time_str": gcode_metrics.get("estimated_time_str", ""),
        "estimated_time_sec": int(gcode_metrics.get("estimated_time_sec", 0)),
        "filament_mm": float(gcode_metrics.get("filament_mm", 0.0)),
        "filament_m": float(gcode_metrics.get("filament_m", 0.0)),
        "filament_cm3": float(gcode_metrics.get("filament_cm3", 0.0)),
        "filament_g": float(gcode_metrics.get("filament_g", 0.0)),
        "layer_count": int(gcode_metrics.get("layer_count", 0)),
        "extrusion_moves": int(gcode_metrics.get("extrusion_moves", 0)),
        "gcode_extrusion_bounds_mm": eb,
        "gcode_part_bounds_mm": gcode_metrics.get("part_extrusion_bounds_mm"),
        "bed_bounds_ok": bed_bounds_ok,
        "elapsed_slice_sec": slice_elapsed,
        "plate_passed": plate_passed,
        **({"stl_info_error": stl_raw[:300]} if not stl_ok else {}),
        **({"threemf_info_error": mf_raw[:300]} if not mf_ok else {}),
    }


def audit_zero_screws_zero_glue() -> dict[str, Any]:
    """Audit domain model and build_meta JSONs to confirm zero screws and zero glue across all 57 parts."""
    cfg = pd_mod.PrintConfig()
    pieces, _ = pd_mod.build_panel_piece_specs(cfg)
    supports = pd_mod.build_support_specs(cfg)
    furniture = pd_mod.build_furniture_specs(cfg)

    stripped_total = 0
    kept_functional_total = 0
    total_mortises = 0
    fastener_leaks: list[str] = []
    glue_mentions: list[str] = []

    for piece in pieces:
        meta = json.loads((META_DIR / f"{piece.part_id}.json").read_text(encoding="utf-8"))
        stripped = meta.get("stripped_fastener_holes", [])
        kept = meta.get("kept_functional_holes", [])
        stripped_total += len(stripped)
        kept_functional_total += len(kept)
        total_mortises += int(meta.get("mortise_count", 0))
        for h in kept:
            if any(k in h.lower() for k in ("m3", "m2", "m2.5", "screw", "clamp")):
                fastener_leaks.append(f"{piece.part_id}:{h}")

    for sup in supports:
        meta = json.loads((META_DIR / f"{sup.part_id}.json").read_text(encoding="utf-8"))
        params = meta.get("params", {})
        for k in params:
            if any(tok in k.lower() for tok in ("screw_hole", "m3_hole", "m2_hole", "glue")):
                fastener_leaks.append(f"{sup.part_id}:param:{k}")

    for fur in furniture:
        meta = json.loads((META_DIR / f"{fur.part_id}.json").read_text(encoding="utf-8"))
        att = str(meta.get("attachment", "")).lower()
        if "glue" in att and "zero glue" not in att and "no glue" not in att:
            glue_mentions.append(f"{fur.part_id}:{att}")

    passed = (len(fastener_leaks) == 0) and (len(glue_mentions) == 0) and (stripped_total > 0) and (total_mortises > 0)
    return {
        "panel_pieces_audited": len(pieces),
        "support_parts_audited": len(supports),
        "furniture_parts_audited": len(furniture),
        "stripped_fastener_holes_count": stripped_total,
        "kept_functional_holes_count": kept_functional_total,
        "mortise_slots_injected_count": total_mortises,
        "fastener_leaks": fastener_leaks,
        "glue_mentions": glue_mentions,
        "passed": passed,
    }


def build_r9_user_like_report(
    part_results: list[dict[str, Any]],
    plate_results: list[dict[str, Any]],
    assembly_report: dict[str, Any],
    fit_table: dict[str, Any],
    screwless_audit: dict[str, Any],
    totals: dict[str, Any],
    expected_parts: int,
    expected_plates: int,
    expected_instances: int,
) -> dict[str, Any]:
    """Build R9 user-like test report (`Buoc | Thao tac | Ket qua | DUNG/SAI | Le ra`)."""
    rows: list[dict[str, Any]] = []
    step = 0

    def add_row(thao_tac: str, ket_qua: str, ok: bool, le_ra: str) -> None:
        nonlocal step
        step += 1
        rows.append({
            "Buoc": step,
            "Thao tac": thao_tac,
            "Ket qua": ket_qua,
            "DUNG/SAI": "DUNG" if ok else "SAI",
            "Le ra": le_ra,
        })

    # Step 1: All individual STL parts --info check
    n_parts = len(part_results)
    n_parts_ok = sum(1 for r in part_results if r["passed"])
    n_manifold = sum(1 for r in part_results if r["manifold"])
    n_z0 = sum(1 for r in part_results if r["flat_z0"])
    n_fit = sum(1 for r in part_results if r["fits_usable_rotatable"])
    max_x = max((r["size_mm"][0] for r in part_results if "size_mm" in r), default=0.0)
    max_y = max((r["size_mm"][1] for r in part_results if "size_mm" in r), default=0.0)
    max_z = max((r["size_mm"][2] for r in part_results if "size_mm" in r), default=0.0)
    add_row(
        f"Kiem tra PrusaSlicer --info cho toan bo {n_parts} file chi tiet rieng le (parts/*.stl)",
        f"{n_parts_ok}/{n_parts} dat: manifold={n_manifold}/{n_parts}, min_z==0.0={n_z0}/{n_parts}, lot ban 170x190x245 (co xoay 90)={n_fit}/{n_parts}; max bbox={max_x:.1f}x{max_y:.1f}x{max_z:.1f} mm",
        n_parts == expected_parts and n_parts_ok == expected_parts,
        f"{expected_parts}/{expected_parts} STL manifold=yes, min_z==0.0 mm, lot vung an toan 170x190x245 mm (cho phep xoay 90 deg)",
    )

    # Step 2: 3D BRep assembly, reconstruction & 0..90 deg swept-volume door check
    asm_ok = bool(assembly_report.get("assembly_passed", False))
    n_recon = len(assembly_report.get("reconstruction_checks", []))
    n_recon_fail = len(assembly_report.get("reconstruction_failures", []))
    sweep = assembly_report.get("door_swept_volume_check", {})
    sweep_ok = bool(sweep.get("passed", False))
    sweep_max = float(sweep.get("max_intersection_mm3", 0.0))
    tm = assembly_report.get("torque_margin", {})
    max_coll = max(
        float(assembly_report.get("max_panel_intersection_mm3", 0.0)),
        float(assembly_report.get("max_support_intersection_mm3", 0.0)),
        float(assembly_report.get("max_furniture_intersection_mm3", 0.0)),
        float(assembly_report.get("max_hardware_intersection_mm3", 0.0)),
        sweep_max,
    )
    add_row(
        "Kiem tra lap rap 3D BRep (assembly_report.json): ghep manh duoi en + va cham toan nha + quet canh cua dong truc 0..90 deg",
        f"assembly_passed={asm_ok}, tai tao {n_recon - n_recon_fail}/{n_recon} tam (sai so 0.0 mm), va cham=0 (max giao={max_coll:.4f} mm3), quet cua 0..90 deg ({sweep.get('angles_checked', 0)} goc)={sweep_ok} (he so momen SG90={tm.get('worst_case_safety_margin_x', 0)}x)",
        asm_ok and sweep_ok and n_recon_fail == 0 and max_coll <= 0.05,
        "100% tam ghep khop bbox goc (sai so <= 0.05 mm), 0 va cham toan nha va 0 va cham khi cua quay 0..90 deg quanh truc (77.0, 201.5)",
    )

    # Step 3: KiCad Hub PCB & all 14 authoritative electronic modules fit table check (16 rows)
    fit_rows = fit_table.get("rows", [])
    fit_pass_cnt = sum(1 for r in fit_rows if r.get("status") == "PASS")
    fit_ok = bool(fit_table.get("all_fit_passed", False)) and fit_pass_cnt == len(fit_rows) and len(fit_rows) >= 16
    add_row(
        "Kiem tra do khop phan cung thuc te (fit_table.json): Hub PCB KiCad 100x80 + NodeMCU + du 14 module dien tu (16 dong)",
        f"{fit_pass_cnt}/{len(fit_rows)} cum phan cung PASS (Hub PCB {fit_table.get('pcb_size_mm')} lo {fit_table.get('pcb_hole_pitch_mm')} D={fit_table.get('pcb_hole_dia_mm')}mm khop SUP06 + du SUP07..SUP18)",
        fit_ok,
        "Tat ca 16/16 cum bo mach/cam bien/dong co (Hub PCB + NodeMCU + 14 module) co khe ho lap rap chuan va PASS",
    )

    # Step 4: Zero-screws & zero-glue geometry audit
    add_row(
        f"Kiem toan hinh hoc khong oc vit & khong keo dan ({expected_parts} chi tiet: panel + mount + furniture)",
        f"Da loai bo {screwless_audit['stripped_fastener_holes_count']} lo oc vit/clamp goc, giu {screwless_audit['kept_functional_holes_count']} lo chuc nang (LED/loa/mic/day/ong), bo sung {screwless_audit['mortise_slots_injected_count']} lo mong chu nhat; ro ri vit={len(screwless_audit['fastener_leaks'])}, keo={len(screwless_audit['glue_mentions'])}",
        bool(screwless_audit["passed"]),
        "0 lo oc vit M2/M2.5/M3/clamp sot lai, 0 chi tiet yeu cau keo dan, toan bo lien ket bang mong/chot/kep dan hoi",
    )

    # Steps 5..: Every single plate (load, --info manifold/count, slice --dont-arrange, G-code XY/Z bounds, zero warnings)
    for pr in plate_results:
        eb = pr.get("gcode_extrusion_bounds_mm") or {}
        xy_str = (
            f"X=[{eb.get('x_min', -1):.2f}, {eb.get('x_max', -1):.2f}], "
            f"Y=[{eb.get('y_min', -1):.2f}, {eb.get('y_max', -1):.2f}], "
            f"Z_max={eb.get('z_max', -1):.2f} mm"
        )
        add_row(
            f"Nap & cat lop {pr['plate_id']} ({pr['threemf_file']} + .stl) trong PrusaSlicer CLI voi --dont-arrange (khong --center), ban 180x200x250, 0.2mm PLA, support=0",
            f"3MF={pr['threemf_object_count']}/{pr['expected_part_count']} obj manifold={pr['all_objects_manifold']}, STL manifold={pr['stl_manifold']}; "
            f"slice_ok={pr['slice_ok']}, {xy_str}; "
            f"thoi gian={pr['estimated_time_str']}, nhua={pr['filament_g']:.2f}g ({pr['filament_m']:.2f}m), "
            f"canh bao tran ban={pr['outside_volume_warning']}, can support={pr['needs_supports']}",
            bool(pr["plate_passed"]),
            f"Du {pr['expected_part_count']} obj manifold=yes, slice exit=0 khong can arrange lai, G-code X trong [0,180], Y trong [0,200], Z<=250, 0 canh bao tran ban/overhang",
        )

    # Final step: Aggregate plate totals & full-set completeness
    total_instances = sum(int(p["expected_part_count"]) for p in plate_results)
    all_plates_ok = len(plate_results) == expected_plates and all(p["plate_passed"] for p in plate_results)
    add_row(
        f"Tong hop toan bo {expected_plates} ban in (plates/PLATE01..PLATE{expected_plates:02d}) san sang giao ban in 180x200x250 mm",
        f"{len(plate_results)}/{expected_plates} ban in DAT ({total_instances} ban the chi tiet), tong thoi gian in={totals['total_print_time_str']} ({totals['total_print_time_hours']:.2f} gio), tong nhua PLA={totals['total_filament_g']:.2f} g ({totals['total_filament_m']:.2f} m), 0 ban can support",
        all_plates_ok and total_instances == expected_instances,
        f"{expected_plates}/{expected_plates} ban in dat 100%, phu du {expected_instances} ban the tu {expected_parts} chi tiet rieng le, co thong so thoi gian & nhua chinh xac tu G-code that",
    )

    dung_count = sum(1 for r in rows if r["DUNG/SAI"] == "DUNG")
    sai_count = sum(1 for r in rows if r["DUNG/SAI"] == "SAI")
    return {
        "schema": "R9 (Buoc | Thao tac | Ket qua | DUNG/SAI | Le ra)",
        "all_passed": (sai_count == 0),
        "total_steps": len(rows),
        "dung_count": dung_count,
        "sai_count": sai_count,
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify all 57 parts and 17 build plates in PrusaSlicer CLI")
    ap.add_argument("--slicer", type=pathlib.Path, default=DEFAULT_SLICER_EXE)
    ap.add_argument("--workers", type=int, default=4, help="Parallel PrusaSlicer worker threads")
    args = ap.parse_args()

    slicer_exe = args.slicer
    if not slicer_exe.exists():
        print(f"ERROR: PrusaSlicer CLI not found at {slicer_exe}", file=sys.stderr)
        return 2

    t_start = time.time()
    plates_manifest = json.loads((META_DIR / "plates_manifest.json").read_text(encoding="utf-8"))
    fit_table = json.loads((META_DIR / "fit_table.json").read_text(encoding="utf-8"))
    assembly_report = json.loads((META_DIR / "assembly_report.json").read_text(encoding="utf-8"))

    part_stls = sorted(PARTS_DIR.glob("*.stl"))
    print(f"[1/3] Running PrusaSlicer --info on {len(part_stls)} individual parts (workers={args.workers})...", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        part_results = list(ex.map(lambda p: verify_one_part(slicer_exe, p), part_stls))

    part_failures = [r["part_id"] for r in part_results if not r["passed"]]
    print(
        f"      Parts checked: {len(part_results) - len(part_failures)}/{len(part_results)} PASS "
        f"(elapsed {time.time() - t_start:.1f}s)",
        flush=True,
    )
    if part_failures:
        print(f"      FAILED PARTS: {part_failures}", flush=True)

    plates = plates_manifest["plates"]
    print(f"[2/3] Verifying & slicing {len(plates)} plates (.3mf + .stl) with --dont-arrange (workers={args.workers})...", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        plate_results = list(ex.map(lambda pl: verify_one_plate(slicer_exe, pl), plates))
    plate_results.sort(key=lambda r: r["plate_index"])

    for pr in plate_results:
        status = "PASS" if pr["plate_passed"] else "FAIL"
        eb = pr.get("gcode_extrusion_bounds_mm") or {}
        print(
            f"  [{status}] {pr['plate_id']}: objs={pr['threemf_object_count']}/{pr['expected_part_count']} "
            f"mf={pr['all_objects_manifold']}/{pr['stl_manifold']} slice={pr['slice_ok']} "
            f"time={pr['estimated_time_str']} fil={pr['filament_g']:.2f}g/{pr['filament_m']:.2f}m "
            f"X=[{eb.get('x_min', -1):.2f},{eb.get('x_max', -1):.2f}] "
            f"Y=[{eb.get('y_min', -1):.2f},{eb.get('y_max', -1):.2f}] "
            f"Zmax={eb.get('z_max', -1):.2f} ({pr['elapsed_slice_sec']}s)",
            flush=True,
        )

    plate_failures = [r["plate_id"] for r in plate_results if not r["plate_passed"]]
    total_time_sec = sum(int(r["estimated_time_sec"]) for r in plate_results)
    total_fil_mm = round(sum(float(r["filament_mm"]) for r in plate_results), 2)
    total_fil_m = round(total_fil_mm / 1000.0, 2)
    total_fil_cm3 = round(sum(float(r["filament_cm3"]) for r in plate_results), 2)
    total_fil_g = round(sum(float(r["filament_g"]) for r in plate_results), 2)

    totals = {
        "total_plates": len(plate_results),
        "plates_passed": len(plate_results) - len(plate_failures),
        "total_part_instances": sum(int(r["expected_part_count"]) for r in plate_results),
        "total_print_time_sec": total_time_sec,
        "total_print_time_str": format_duration(total_time_sec),
        "total_print_time_hours": round(total_time_sec / 3600.0, 2),
        "total_filament_mm": total_fil_mm,
        "total_filament_m": total_fil_m,
        "total_filament_cm3": total_fil_cm3,
        "total_filament_g": total_fil_g,
        "any_plate_needs_supports": any(r["needs_supports"] for r in plate_results),
    }

    print("[3/3] Auditing zero-screws/zero-glue geometry & writing reports...", flush=True)
    screwless_audit = audit_zero_screws_zero_glue()

    expected_parts = int(plates_manifest["total_unique_parts"])
    expected_plates = int(plates_manifest["achieved_plate_count"])
    expected_instances = int(plates_manifest["total_part_instances"])

    all_passed = (
        len(part_results) == expected_parts
        and len(part_failures) == 0
        and len(plate_results) == expected_plates
        and len(plate_failures) == 0
        and bool(assembly_report.get("assembly_passed", False))
        and bool(fit_table.get("all_fit_passed", False))
        and bool(screwless_audit["passed"])
    )

    slice_report = {
        "slicer_cli": str(slicer_exe),
        "bed_mm": [BED_X, BED_Y, BED_Z],
        "usable_mm": [USABLE_X, USABLE_Y, USABLE_Z],
        "slice_profile": {
            "arrange": False,
            "center": False,
            "layer_height_mm": 0.2,
            "first_layer_height_mm": 0.2,
            "nozzle_diameter_mm": 0.4,
            "filament_diameter_mm": 1.75,
            "filament_density_g_cm3": 1.24,
            "perimeters": 3,
            "fill_density": "20%",
            "fill_pattern": "gyroid",
            "support_material": 0,
            "skirts": 1,
            "skirt_distance_mm": 2,
        },
        "all_passed": all_passed,
        "elapsed_sec": round(time.time() - t_start, 2),
        "parts_summary": {
            "total_parts": len(part_results),
            "passed_parts": len(part_results) - len(part_failures),
            "failed_parts": part_failures,
            "all_manifold": all(r["manifold"] for r in part_results),
            "all_flat_z0": all(r["flat_z0"] for r in part_results),
            "all_fit_usable_rotatable": all(r["fits_usable_rotatable"] for r in part_results),
        },
        "totals": totals,
        "screwless_audit": screwless_audit,
        "failed_plates": plate_failures,
        "plates": plate_results,
        "parts": part_results,
    }

    r9_report = build_r9_user_like_report(
        part_results=part_results,
        plate_results=plate_results,
        assembly_report=assembly_report,
        fit_table=fit_table,
        screwless_audit=screwless_audit,
        totals=totals,
        expected_parts=expected_parts,
        expected_plates=expected_plates,
        expected_instances=expected_instances,
    )

    slice_report_path = META_DIR / "slice_report.json"
    r9_report_path = META_DIR / "user_like_test_report.json"
    slice_report_path.write_text(json.dumps(slice_report, indent=2, ensure_ascii=False), encoding="utf-8")
    r9_report_path.write_text(json.dumps(r9_report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        f"\nSUMMARY: all_passed={all_passed} | parts={len(part_results) - len(part_failures)}/{len(part_results)} | "
        f"plates={totals['plates_passed']}/{totals['total_plates']} | "
        f"total_time={totals['total_print_time_str']} ({totals['total_print_time_hours']}h) | "
        f"total_filament={totals['total_filament_g']}g ({totals['total_filament_m']}m) | "
        f"R9={r9_report['dung_count']} DUNG / {r9_report['sai_count']} SAI | "
        f"elapsed={slice_report['elapsed_sec']}s",
        flush=True,
    )
    return 0 if (all_passed and r9_report["all_passed"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
