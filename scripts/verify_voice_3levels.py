"""Script kiem dinh 3-Level Voice Auth & Voice Command API (Local TestClient hoac Live Vercel Preview URL).

Nap file am thanh giong nguoi that (Level 1 Owner, Level 2 VIVOS/CommonVoice/FOSD Speaker A,
Level 3 VIVOS/CommonVoice/FOSD Speaker B) vao POST /api/voice_command va bao cao theo tung cap do:
- recognized_text
- intent
- permission (ALLOWED / DENIED)
- action (trang thai thiet bi)
- latency_ms (do tre xu ly)
"""

from __future__ import annotations

import argparse
import base64
import glob
import json
import pathlib
import sys
import time
import urllib.request
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VOICES_DIR = pathlib.Path(r"C:\Users\LENOVO\datn-wt\voices")
SEP_DIR = ROOT / "test_audio" / "cac_cau_lenh_cua_sep"


def detect_level1_owner_hook() -> tuple[bool, pathlib.Path | None]:
    """Kiem tra xem file C:/Users/LENOVO/datn-wt/voices/level1_owner.* co ton tai khong."""
    if VOICES_DIR.exists():
        matches = sorted(glob.glob(str(VOICES_DIR / "level1_owner.*")))
        for m in matches:
            p = pathlib.Path(m)
            if p.is_file() and p.stat().st_size > 100:
                return True, p
    return False, None


def build_test_matrix() -> tuple[bool, pathlib.Path | None, list[dict[str, Any]]]:
    has_l1_custom, l1_custom_path = detect_level1_owner_hook()
    l1_cmd_dir = VOICES_DIR / "level1_commands"
    cmd_dir = l1_cmd_dir if l1_cmd_dir.exists() else SEP_DIR

    matrix: list[dict[str, Any]] = [
        # 7 clip cau lenh Chu nha Level 1 (C:\Users\LENOVO\datn-wt\voices\level1_commands\cau_1..cau_7)
        {
            "level": 1,
            "speaker_label": "Level 1 — Owner (Sếp Tuấn Anh, Câu 1 Chào & Xác thực)",
            "audio_path": cmd_dir / "cau_1_xin_chao_chu_nha_cap1.wav",
            "transcript_hint": "",
            "expected_permission": "ALLOWED",
            "expected_device": "",
            "expected_state": None,
        },
        {
            "level": 1,
            "speaker_label": "Level 1 — Owner (Sếp Tuấn Anh, Câu 2 Mở cửa chính)",
            "audio_path": cmd_dir / "cau_2_mo_cua_chinh.wav",
            "transcript_hint": "",
            "expected_permission": "ALLOWED",
            "expected_device": "main_door",
            "expected_state": True,
        },
        {
            "level": 1,
            "speaker_label": "Level 1 — Owner (Sếp Tuấn Anh, Câu 3 Đóng cửa chính)",
            "audio_path": cmd_dir / "cau_3_dong_cua_chinh.wav",
            "transcript_hint": "",
            "expected_permission": "ALLOWED",
            "expected_device": "main_door",
            "expected_state": False,
        },
        {
            "level": 1,
            "speaker_label": "Level 1 — Owner (Sếp Tuấn Anh, Câu 4 Bật đèn phòng khách)",
            "audio_path": cmd_dir / "cau_4_bat_den_phong_khach.wav",
            "transcript_hint": "",
            "expected_permission": "ALLOWED",
            "expected_device": "living_room_light",
            "expected_state": True,
        },
        {
            "level": 1,
            "speaker_label": "Level 1 — Owner (Sếp Tuấn Anh, Câu 5 Bật quạt trần & điều hòa)",
            "audio_path": cmd_dir / "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav",
            "transcript_hint": "",
            "expected_permission": "ALLOWED",
            "expected_device": "fan",
            "expected_state": True,
        },
        {
            "level": 1,
            "speaker_label": "Level 1 — Owner (Sếp Tuấn Anh, Câu 6 Tắt hết đèn)",
            "audio_path": cmd_dir / "cau_6_tat_het_den.wav",
            "transcript_hint": "",
            "expected_permission": "ALLOWED",
            "expected_device": "living_room_light",
            "expected_state": False,
        },
        {
            "level": 1,
            "speaker_label": "Level 1 — Owner (Sếp Tuấn Anh, Câu 7 Đóng hết cửa)",
            "audio_path": cmd_dir / "cau_7_dong_het_cua.wav",
            "transcript_hint": "",
            "expected_permission": "ALLOWED",
            "expected_device": "main_door",
            "expected_state": False,
        },
        # Level 1 E2E 'tat quat'
        {
            "level": 1,
            "speaker_label": "Level 1 — Owner (Sếp Tuấn Anh, E2E Tắt quạt)",
            "audio_path": cmd_dir / "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav",
            "transcript_hint": "tat quat",
            "expected_permission": "ALLOWED",
            "expected_device": "fan",
            "expected_state": False,
        },
        # Level 2: Thanh vien gia dinh (Family Member - Tier 2, Speaker A Nu F0~274Hz)
        {
            "level": 2,
            "speaker_label": "Level 2 — Family (VIVOS/CV/FOSD Speaker A, F0~261Hz)",
            "audio_path": VOICES_DIR / "level2_bat_den_phong_khach.wav",
            "transcript_hint": "",
            "expected_permission": "ALLOWED",
            "expected_device": "living_room_light",
            "expected_state": True,
        },
        {
            "level": 2,
            "speaker_label": "Level 2 — Family (VIVOS/CV/FOSD Speaker A, F0~284Hz)",
            "audio_path": VOICES_DIR / "level2_tat_quat.wav",
            "transcript_hint": "",
            "expected_permission": "ALLOWED",
            "expected_device": "fan",
            "expected_state": False,
        },
        {
            "level": 2,
            "speaker_label": "Level 2 — Family (VIVOS/CV/FOSD Speaker A, F0~279Hz)",
            "audio_path": VOICES_DIR / "level2_mo_cua_chinh.wav",
            "transcript_hint": "",
            "expected_permission": "DENIED",
            "expected_device": "main_door",
            "expected_state": False,
        },
        # Level 3: Khach (Guest - Tier 3, Speaker B Nam F0~130Hz)
        {
            "level": 3,
            "speaker_label": "Level 3 — Guest (VIVOS/CV/FOSD Speaker B, F0~123Hz)",
            "audio_path": VOICES_DIR / "level3_bat_den_phong_khach.wav",
            "transcript_hint": "",
            "expected_permission": "ALLOWED",
            "expected_device": "living_room_light",
            "expected_state": True,
        },
        {
            "level": 3,
            "speaker_label": "Level 3 — Guest (VIVOS/CV/FOSD Speaker B, F0~125Hz)",
            "audio_path": VOICES_DIR / "level3_tat_quat.wav",
            "transcript_hint": "",
            "expected_permission": "ALLOWED",
            "expected_device": "fan",
            "expected_state": False,
        },
        {
            "level": 3,
            "speaker_label": "Level 3 — Guest (VIVOS/CV/FOSD Speaker B, F0~139Hz)",
            "audio_path": VOICES_DIR / "level3_mo_cua_chinh.wav",
            "transcript_hint": "",
            "expected_permission": "DENIED",
            "expected_device": "main_door",
            "expected_state": False,
        },
    ]
    return has_l1_custom, l1_custom_path, matrix


def post_json_http(base_url: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    data_bytes = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "SmartHomeVoiceVerifier/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_evaluation(base_url: str | None = None) -> list[dict[str, Any]]:
    has_l1_custom, l1_custom_path, matrix = build_test_matrix()
    print(
        f"[Level 1 Hook] C:\\Users\\LENOVO\\datn-wt\\voices\\level1_owner.* -> "
        f"{'PRESENT (' + str(l1_custom_path) + ')' if has_l1_custom else 'ABSENT (Ready; using Sep real voice recordings)'}"
    )

    client = None
    if not base_url:
        from fastapi.testclient import TestClient
        from simulator.server import app

        client = TestClient(app)

    # Bước 0: Enroll Level 1 từ C:\Users\LENOVO\datn-wt\voices\level1_owner.wav
    if has_l1_custom and l1_custom_path and l1_custom_path.exists():
        enroll_b64 = base64.b64encode(l1_custom_path.read_bytes()).decode("ascii")
        enroll_payload = {
            "wav_b64": enroll_b64,
            "user_id": "tuan_anh",
            "user_name": "Nguyễn Tuấn Anh",
            "tier": 1,
        }
        t_enr = time.perf_counter()
        if base_url:
            enr_res = post_json_http(base_url, "/api/voice_auth/enroll_tier_pcm", enroll_payload)
        else:
            resp_enr = client.post("/api/voice_auth/enroll_tier_pcm", json=enroll_payload)
            assert resp_enr.status_code == 200, resp_enr.text
            enr_res = resp_enr.json()
        enr_ms = round((time.perf_counter() - t_enr) * 1000.0, 2)
        assert enr_res.get("ok") is True, f"Enroll level1_owner.wav that bai: {enr_res}"
        print(
            f"[Level 1 Enroll] Enrolled {l1_custom_path.name} -> ok={enr_res.get('ok')}, "
            f"tier={enr_res.get('profile', {}).get('tier')}, f0={enr_res.get('profile', {}).get('f0_hz')}Hz, "
            f"latency={enr_ms}ms"
        )

    results_rows: list[dict[str, Any]] = []

    for case in matrix:
        audio_path: pathlib.Path = case["audio_path"]
        if not audio_path.exists():
            raise FileNotFoundError(f"Khong tim thay file audio: {audio_path}")

        wav_b64 = base64.b64encode(audio_path.read_bytes()).decode("ascii")
        payload: dict[str, Any] = {"wav_b64": wav_b64}
        if case["transcript_hint"]:
            payload["transcript"] = case["transcript_hint"]

        t_req_start = time.perf_counter()
        if base_url:
            data = post_json_http(base_url, "/api/voice_command", payload)
        else:
            from simulator.api.deps import _REST_ENGINE

            _REST_ENGINE.devices["living_room_light"]["state"] = "OFF"
            _REST_ENGINE.devices["fan"]["state"] = "ON"
            _REST_ENGINE.devices["main_door"]["state"] = "CLOSED"
            resp = client.post("/api/voice_command", json=payload)
            assert resp.status_code in (200, 403), resp.text
            data = resp.json()
        e2e_ms = round((time.perf_counter() - t_req_start) * 1000.0, 2)

        server_latency_ms = float(data.get("latency_ms") or e2e_ms)
        row = {
            "level": int(data.get("level", case["level"])),
            "speaker": case["speaker_label"],
            "audio_file": audio_path.name,
            "recognized_text": str(data.get("recognized_text", "")),
            "intent": str(data.get("intent", "")),
            "permission": str(data.get("permission", "")),
            "action": str(data.get("action", "")),
            "server_latency_ms": server_latency_ms,
            "e2e_latency_ms": e2e_ms,
        }
        results_rows.append(row)

        assert row["level"] == case["level"], f"Sai level: {row} vs {case}"
        assert row["permission"] == case["expected_permission"], f"Sai permission: {row} vs {case}"

    print("\n### Voice Auth 3-Level Evaluation Results Table\n")
    print("| Level | Speaker / Dataset Source | Audio File | Recognized Text | Intent | Permission | Action | Server Latency (ms) | E2E Latency (ms) |")
    print("| :---: | :--- | :--- | :--- | :--- | :---: | :--- | :---: | :---: |")
    for r in results_rows:
        print(
            f"| **Level {r['level']}** | {r['speaker']} | `{r['audio_file']}` | "
            f"`{r['recognized_text']}` | `{r['intent']}` | **{r['permission']}** | "
            f"`{r['action']}` | {r['server_latency_ms']:.2f} | {r['e2e_latency_ms']:.2f} |"
        )
    return results_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify 3-Level Voice Auth & Voice Command API")
    parser.add_argument("--url", default="", help="Optional live base URL (e.g. Vercel Preview URL)")
    parser.add_argument("--json-out", default="", help="Optional path to save JSON results")
    args = parser.parse_args()

    rows = run_evaluation(base_url=args.url.strip() or None)
    if args.json_out:
        out_p = pathlib.Path(args.json_out)
        out_p.write_bytes((json.dumps(rows, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
