"""One-command reproducible FreeCAD 1.1 runner for all 3D-Print Set v2 parts (R6: zero decorative furniture).

Invokes:
  1. build_panels_v2.py   (30 screwless lightweight house panels with dovetails, mortises, 2.2mm webs & hex cutouts)
  2. build_mounts_v2.py   (21 screwless clips, PCB/module snap mounts & water liner)

Also cleans any stale FUR* furniture artifacts from parts/, build_meta/, drawings/, and previews/.

Usage:
    python "hardware/in 3 d/scripts/build_all_v2.py"
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import time

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PRINT3D_ROOT = SCRIPT_DIR.parent
FREECAD_CANDIDATES = [
    pathlib.Path(r"C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe"),
    pathlib.Path(r"C:\Users\LENOVO\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe"),
    pathlib.Path(r"C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe"),
]


def find_freecadcmd() -> pathlib.Path:
    for p in FREECAD_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("freecadcmd.exe not found")


def cleanup_stale_furniture_artifacts() -> int:
    """R6: remove any leftover FUR* parts, metadata, drawings, and _furniture_showcase.png."""
    removed = 0
    for folder, patterns in (
        (PRINT3D_ROOT / "parts", ("FUR*.stl", "FUR*.step")),
        (PRINT3D_ROOT / "build_meta", ("FUR*.json",)),
        (PRINT3D_ROOT / "drawings", ("FUR*.png", "FUR*.pdf")),
        (PRINT3D_ROOT / "previews", ("_furniture_showcase.png",)),
    ):
        if not folder.exists():
            continue
        for pat in patterns:
            for fp in folder.glob(pat):
                fp.unlink(missing_ok=True)
                removed += 1
    if removed:
        print(f"[R6 CLEANUP] Removed {removed} stale decorative furniture artifacts")
    return removed


def main() -> int:
    fc = find_freecadcmd()
    t0 = time.time()
    cleanup_stale_furniture_artifacts()
    for name in ("build_panels_v2.py", "build_mounts_v2.py"):
        script = SCRIPT_DIR / name
        print(f"=== Running {name} ===")
        proc = subprocess.run([str(fc), str(script)], check=False)
        if proc.returncode != 0:
            print(f"[FAIL] {name} exited with code {proc.returncode}")
            return proc.returncode
    print(f"ALL BUILDERS DONE in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
