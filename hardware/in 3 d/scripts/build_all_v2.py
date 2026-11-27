"""One-command reproducible FreeCAD 1.1 runner for all 3D-Print Set v2 parts.

Invokes:
  1. build_panels_v2.py   (30 screwless house panels with dovetails & mortises)
  2. build_mounts_v2.py   (18 screwless clips, PCB/module snap mounts & water liner)
  3. build_furniture_v2.py (9 house-scale floor-pegged furniture items)

Usage:
    python "hardware/in 3 d/scripts/build_all_v2.py"
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import time

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
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


def main() -> int:
    fc = find_freecadcmd()
    t0 = time.time()
    for name in ("build_panels_v2.py", "build_mounts_v2.py", "build_furniture_v2.py"):
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
