"""Standalone Runner for Smart Home Voice AI E2E Test Suite.
Có thể chạy độc lập không phụ thuộc vào pytest qua:
    python -X utf8 tests/e2e/run_all_e2e.py
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_e2e_suite() -> int:
    import pytest

    print("=" * 80)
    print("🚀 SMART HOME VOICE AI — E2E TEST SUITE RUNNER (4 TIERS, 14 FEATURES)")
    print("=" * 80)
    print(f"Working Directory: {ROOT}")
    print(f"Test Directory   : {ROOT / 'tests' / 'e2e'}\n")

    start_time = time.perf_counter()

    args = [
        str(ROOT / "tests" / "e2e"),
        "-v",
        "--tb=short",
        "-s",
    ]

    ret_code = pytest.main(args)
    elapsed = round(time.perf_counter() - start_time, 2)

    print("\n" + "=" * 80)
    if ret_code == 0:
        print(f"🎉 TẤT CẢ CÁC BÀI TEST E2E ĐỀU VƯỢT QUA 100% TRONG {elapsed}s (EXIT CODE: 0)!")
    else:
        print(f"❌ CÓ BÀI TEST THẤT BẠI HOẶC GẶP LỖI (EXIT CODE: {ret_code}) TRONG {elapsed}s!")
    print("=" * 80)
    return ret_code


if __name__ == "__main__":
    raise SystemExit(run_e2e_suite())
