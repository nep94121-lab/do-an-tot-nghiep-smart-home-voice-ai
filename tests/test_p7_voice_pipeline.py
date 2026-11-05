"""Test Suite TDD cho Phase 7 Voice Pipeline (Mic Capture -> Upload -> STT -> Intent -> 3-Level Voice Auth/RBAC -> Device Action -> UI Snapshot).

Kiem thu:
1. Nhan dien khau lenh Tieng Viet khong dau ('bat den phong khach', 'tat quat', 'mo cua chinh'),
   co dau ('bật đèn phòng khách', 'tắt quạt', 'mở cửa chính') va cau truc dao ngu tu bo du lieu
   VIVOS/CommonVoice/FOSD ('đèn phòng khách ba bật', 'quạt phòng khách hai tắt', 'công tắc cổng hai bật').
2. Endpoint stateless POST /api/voice_command (va /api/voice/command) tren Vercel Serverless:
   - Level 1 (Owner, tier=1): full quyen bat den phong khach, tat quat, mo cua chinh.
   - Level 2 (Family Member, tier=2, Real Human Speech Speaker A): duoc phep bat den phong khach, tat quat; BI CHAN mo cua chinh (RBAC DENIED).
   - Level 3 (Guest, tier=3, Real Human Speech Speaker B - khac Speaker A): duoc phep bat den phong khach, tat quat; BI CHAN mo cua chinh (RBAC DENIED).
3. Kiem tra 2 nguoi noi Level 2 va Level 3 trong C:/Users/LENOVO/datn-wt/voices/ la giong nguoi that (REAL human speech, NOT TTS) va khac nguoi noi.
4. Kiem tra hook auto-detect C:/Users/LENOVO/datn-wt/voices/level1_owner.* khi co hoac khi chua co file.
5. Kiem tra Frontend Desktop (app.js) va Mobile (mobile_app.js) co fallback HTTP POST /api/voice_command khi chay tren Vercel Serverless (khong co WebSocket).
"""

from __future__ import annotations

import base64
import pathlib
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from simulator.api.deps import _BOOT_VOICE_AUTH, _REST_ENGINE
from simulator.server import app
from simulator.voice.enrollment_quality import (
    parse_vietnamese_voice_command_intents,
    validate_voice_enrollment_quality,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
VOICES_DIR = pathlib.Path(r"C:\Users\LENOVO\datn-wt\voices")


@pytest.fixture(autouse=True)
def _reset_engine_before_each_test():
    """Dam bao trang thai thiet bi va user session sach truoc moi test."""
    _REST_ENGINE.devices["living_room_light"]["state"] = "OFF"
    _REST_ENGINE.devices["bedroom_light"]["state"] = "OFF"
    _REST_ENGINE.devices["fan"]["state"] = "ON"
    _REST_ENGINE.devices["ac"]["state"] = "OFF"
    _REST_ENGINE.devices["main_door"]["state"] = "CLOSED"
    _REST_ENGINE.devices["alarm_siren"]["state"] = "OFF"
    _REST_ENGINE.devices["garden_pump"]["state"] = "OFF"
    _REST_ENGINE.set_active_user("tuan_anh")
    _BOOT_VOICE_AUTH.unauthorized_strikes = 0
    yield


def _snapshot_device_state(snapshot: dict, dev_id: str) -> str:
    devices = snapshot.get("devices", [])
    if isinstance(devices, dict):
        return str(devices.get(dev_id, {}).get("state", ""))
    for d in devices:
        if d.get("id") == dev_id:
            return str(d.get("state", ""))
    return ""


def test_parse_vietnamese_intents_unaccented_accented_and_dataset_forms():
    """Bug 1: Bo phan tich intent phai hieu ca tieng Viet khong dau, co dau va cau truc VIVOS/CommonVoice/FOSD."""
    cases = [
        ("bat den phong khach", "living_room_light", "turn_on"),
        ("bật đèn phòng khách", "living_room_light", "turn_on"),
        ("đèn phòng khách ba bật", "living_room_light", "turn_on"),
        ("tat quat", "fan", "turn_off"),
        ("tắt quạt", "fan", "turn_off"),
        ("Tắt quạt.", "fan", "turn_off"),
        ("quạt phòng khách hai tắt", "fan", "turn_off"),
        ("mo cua chinh", "main_door", "open"),
        ("mở cửa chính", "main_door", "open"),
        ("công tắc cổng hai bật", "main_door", "open"),
    ]
    for phrase, expected_dev, expected_act in cases:
        intents = parse_vietnamese_voice_command_intents(phrase)
        assert intents, f"Khong nhan dien duoc intent cho cau lenh: {phrase!r}"
        matched = any(
            i.get("device_id") == expected_dev and i.get("action") == expected_act
            for i in intents
        )
        assert matched, f"Cau lenh {phrase!r} parse ra {intents}, ky vong ({expected_dev}, {expected_act})"


def test_text_command_executes_unaccented_vietnamese_commands():
    """Bug 2: POST /api/text_command phai thuc thi duoc 'bat den phong khach', 'tat quat', 'mo cua chinh'."""
    client = TestClient(app)

    # 1. bat den phong khach -> living_room_light ON
    r1 = client.post("/api/text_command", json={"text": "bat den phong khach", "role": "tuan_anh"})
    assert r1.status_code == 200
    assert _REST_ENGINE.devices["living_room_light"]["state"] == "ON"

    # 2. tat quat -> fan OFF
    _REST_ENGINE.devices["fan"]["state"] = "ON"
    r2 = client.post("/api/text_command", json={"text": "tat quat", "role": "tuan_anh"})
    assert r2.status_code == 200
    assert _REST_ENGINE.devices["fan"]["state"] == "OFF"

    # 3. mo cua chinh -> main_door OPEN (Owner tier 1)
    r3 = client.post("/api/text_command", json={"text": "mo cua chinh", "role": "tuan_anh"})
    assert r3.status_code == 200
    assert _REST_ENGINE.devices["main_door"]["state"] == "OPEN"


def test_real_human_speech_files_exist_and_are_two_distinct_speakers():
    """Yeu cau 2: File giong Level 2 va Level 3 trong C:/Users/LENOVO/datn-wt/voices/ phai la giong nguoi that (NOT TTS) cua 2 nguoi khac nhau."""
    required_files = [
        "level2_family.wav",
        "level2_bat_den_phong_khach.wav",
        "level2_tat_quat.wav",
        "level2_mo_cua_chinh.wav",
        "level3_guest.wav",
        "level3_bat_den_phong_khach.wav",
        "level3_tat_quat.wav",
        "level3_mo_cua_chinh.wav",
    ]
    l2_f0s = []
    l3_f0s = []

    for fname in required_files:
        fpath = VOICES_DIR / fname
        assert fpath.exists(), f"Thieu file giong nguoi that: {fpath}"
        with wave.open(str(fpath), "rb") as wf:
            sr = wf.getframerate()
            pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        assert sr == 16000
        qual = validate_voice_enrollment_quality(pcm, sr)
        assert qual.get("ok") is True, f"File {fname} khong dat 6 tieu chuan am hoc giong nguoi that: {qual}"
        if fname.startswith("level2_"):
            l2_f0s.append(float(qual["f0_hz"]))
        else:
            l3_f0s.append(float(qual["f0_hz"]))

    # Speaker A (Level 2) va Speaker B (Level 3) phai co F0 trung binh khac biet ro ret (> 80Hz)
    assert abs(float(np.mean(l2_f0s)) - float(np.mean(l3_f0s))) >= 80.0


def test_enroll_level1_from_level1_owner_wav_and_run_all_7_owner_command_clips():
    """Yeu cau Chu nha Level 1:
    1. Enroll Level 1 tu C:/Users/LENOVO/datn-wt/voices/level1_owner.wav
    2. Chay toan bo 7 clip khau lenh trong C:/Users/LENOVO/datn-wt/voices/level1_commands/
       qua POST /api/voice_command (khong truyen transcript goi y):
       - Moi clip deu duoc nhan dien la Owner Level 1 (level=1, tier=1, user_id='tuan_anh', role='ADMIN', permission='ALLOWED')
       - Phien am STT chinh xac (recognized_text)
       - Thuc thi dung hanh dong thiet bi tuong ung
       - Do latency_ms > 0
    """
    client = TestClient(app)

    owner_enroll_wav = VOICES_DIR / "level1_owner.wav"
    assert owner_enroll_wav.exists(), f"Thieu file enroll Level 1: {owner_enroll_wav}"
    enroll_b64 = base64.b64encode(owner_enroll_wav.read_bytes()).decode("ascii")

    # Bước 1: Enroll Level 1 từ level1_owner.wav
    r_enroll = client.post(
        "/api/voice_auth/enroll_tier_pcm",
        json={
            "wav_b64": enroll_b64,
            "user_id": "tuan_anh",
            "user_name": "Nguyễn Tuấn Anh",
            "tier": 1,
        },
    )
    assert r_enroll.status_code == 200, r_enroll.text
    enroll_data = r_enroll.json()
    assert enroll_data.get("ok") is True, enroll_data
    assert enroll_data.get("profile", {}).get("tier") == 1

    # Bước 2: Chạy toàn bộ 7 clip trong C:\Users\LENOVO\datn-wt\voices\level1_commands\
    cmd_dir = VOICES_DIR / "level1_commands"
    assert cmd_dir.exists(), f"Thieu thu muc 7 cau lenh Chu nha: {cmd_dir}"

    _REST_ENGINE.devices["main_door"]["state"] = "CLOSED"
    _REST_ENGINE.devices["living_room_light"]["state"] = "OFF"
    _REST_ENGINE.devices["bedroom_light"]["state"] = "ON"
    _REST_ENGINE.devices["fan"]["state"] = "OFF"
    _REST_ENGINE.devices["ac"]["state"] = "OFF"

    seven_clips_expectations = [
        (
            "cau_1_xin_chao_chu_nha_cap1.wav",
            "nguyễn tuấn anh",
            "GREETING_OWNER_VERIFY",
            {},
        ),
        (
            "cau_2_mo_cua_chinh.wav",
            "mở cửa chính",
            "OPEN_MAIN_DOOR",
            {"main_door": "OPEN"},
        ),
        (
            "cau_3_dong_cua_chinh.wav",
            "đóng cửa chính",
            "CLOSE_MAIN_DOOR",
            {"main_door": "CLOSED"},
        ),
        (
            "cau_4_bat_den_phong_khach.wav",
            "bật đèn phòng khách",
            "TURN_ON_LIVING_ROOM_LIGHT",
            {"living_room_light": "ON"},
        ),
        (
            "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav",
            "bật quạt trần và điều hòa",
            "TURN_ON_FAN, TURN_ON_AC",
            {"fan": "ON", "ac": "ON"},
        ),
        (
            "cau_6_tat_het_den.wav",
            "tắt hết đèn",
            "TURN_OFF_ALL_LIGHTS",
            {"living_room_light": "OFF", "bedroom_light": "OFF"},
        ),
        (
            "cau_7_dong_het_cua.wav",
            "đóng hết cửa",
            "CLOSE_MAIN_DOOR",
            {"main_door": "CLOSED"},
        ),
    ]

    for fname, expected_phrase, expected_intent, expected_states in seven_clips_expectations:
        if fname == "cau_7_dong_het_cua.wav":
            _REST_ENGINE.devices["main_door"]["state"] = "OPEN"
        clip_path = cmd_dir / fname
        assert clip_path.exists(), f"Thieu clip Chu nha: {clip_path}"
        clip_b64 = base64.b64encode(clip_path.read_bytes()).decode("ascii")

        resp = client.post("/api/voice_command", json={"wav_b64": clip_b64})
        assert resp.status_code == 200, f"Loi tren {fname}: {resp.text}"
        data = resp.json()

        assert data["ok"] is True, f"Clip {fname} that bai: {data}"
        assert data["authorized"] is True
        assert data["level"] == 1
        assert data["tier"] == 1
        assert data["user_id"] == "tuan_anh"
        assert data["role"] == "ADMIN"
        assert data["permission"] == "ALLOWED"
        assert expected_phrase in data["recognized_text"].lower(), (
            f"Transcript sai cho {fname}: {data['recognized_text']!r}"
        )
        assert data["intent"] == expected_intent, (
            f"Intent sai cho {fname}: {data['intent']!r} != {expected_intent!r}"
        )
        assert float(data["latency_ms"]) > 0.0
        for dev_id, exp_st in expected_states.items():
            actual_st = _snapshot_device_state(data["snapshot"], dev_id)
            assert actual_st == exp_st, (
                f"Clip {fname}: thiet bi {dev_id} co trang thai {actual_st!r} != {exp_st!r}"
            )


def test_voice_command_api_3_levels_end_to_end():
    """Yeu cau 1 & 3: POST /api/voice_command xu ly audio that qua 3 cap do (Level 1 Owner, Level 2 Family, Level 3 Guest)."""
    client = TestClient(app)

    # --- LEVEL 1: Owner (Tier 1) ---
    sep_dir = ROOT / "test_audio" / "cac_cau_lenh_cua_sep"
    l1_cases = [
        (
            sep_dir / "cau_4_bat_den_phong_khach.wav",
            "bat den phong khach",
            "living_room_light",
            "ON",
            "ALLOWED",
        ),
        (
            sep_dir / "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav",
            "tat quat",
            "fan",
            "OFF",
            "ALLOWED",
        ),
        (
            sep_dir / "cau_2_mo_cua_chinh.wav",
            "mo cua chinh",
            "main_door",
            "OPEN",
            "ALLOWED",
        ),
    ]
    for wav_path, transcript_hint, dev_id, expected_state, expected_perm in l1_cases:
        _REST_ENGINE.devices["living_room_light"]["state"] = "OFF"
        _REST_ENGINE.devices["fan"]["state"] = "ON"
        _REST_ENGINE.devices["main_door"]["state"] = "CLOSED"
        wav_b64 = base64.b64encode(wav_path.read_bytes()).decode("ascii")
        resp = client.post(
            "/api/voice_command",
            json={"wav_b64": wav_b64, "transcript": transcript_hint},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["level"] == 1
        assert data["tier"] == 1
        assert data["permission"] == expected_perm
        assert data["latency_ms"] > 0
        assert data["recognized_text"]
        assert data["intent"]
        assert data["action"]
        assert _snapshot_device_state(data["snapshot"], dev_id) == expected_state

    # --- LEVEL 2: Family Member (Tier 2 - Speaker A Real Speech) ---
    l2_cases = [
        (VOICES_DIR / "level2_bat_den_phong_khach.wav", "living_room_light", "ON", "ALLOWED", True),
        (VOICES_DIR / "level2_tat_quat.wav", "fan", "OFF", "ALLOWED", True),
        (VOICES_DIR / "level2_mo_cua_chinh.wav", "main_door", "CLOSED", "DENIED", False),
    ]
    for wav_path, dev_id, expected_state, expected_perm, expected_ok in l2_cases:
        _REST_ENGINE.devices["living_room_light"]["state"] = "OFF"
        _REST_ENGINE.devices["fan"]["state"] = "ON"
        _REST_ENGINE.devices["main_door"]["state"] = "CLOSED"
        wav_b64 = base64.b64encode(wav_path.read_bytes()).decode("ascii")
        resp = client.post("/api/voice_command", json={"wav_b64": wav_b64})
        assert resp.status_code in (200, 403), resp.text
        data = resp.json()
        assert data["level"] == 2
        assert data["tier"] == 2
        assert data["permission"] == expected_perm
        assert data["ok"] is expected_ok
        assert data["latency_ms"] > 0
        assert _snapshot_device_state(data["snapshot"], dev_id) == expected_state

    # --- LEVEL 3: Guest (Tier 3 - Speaker B Real Speech) ---
    l3_cases = [
        (VOICES_DIR / "level3_bat_den_phong_khach.wav", "living_room_light", "ON", "ALLOWED", True),
        (VOICES_DIR / "level3_tat_quat.wav", "fan", "OFF", "ALLOWED", True),
        (VOICES_DIR / "level3_mo_cua_chinh.wav", "main_door", "CLOSED", "DENIED", False),
    ]
    for wav_path, dev_id, expected_state, expected_perm, expected_ok in l3_cases:
        _REST_ENGINE.devices["living_room_light"]["state"] = "OFF"
        _REST_ENGINE.devices["fan"]["state"] = "ON"
        _REST_ENGINE.devices["main_door"]["state"] = "CLOSED"
        wav_b64 = base64.b64encode(wav_path.read_bytes()).decode("ascii")
        resp = client.post("/api/voice_command", json={"wav_b64": wav_b64})
        assert resp.status_code in (200, 403), resp.text
        data = resp.json()
        assert data["level"] == 3
        assert data["tier"] == 3
        assert data["permission"] == expected_perm
        assert data["ok"] is expected_ok
        assert data["latency_ms"] > 0
        assert _snapshot_device_state(data["snapshot"], dev_id) == expected_state


def test_unknown_stranger_voice_rejected_and_never_opens_door():
    """Bao mat sinh trac hoc: Giong nguoi la (giong_2_nguoi_la_mo_cua.wav) TUYET DOI KHONG bao gio duoc nhan la Level 1 Owner
    va TUYET DOI KHONG mo cua chinh (main_door).
    """
    client = TestClient(app)
    _REST_ENGINE.devices["main_door"]["state"] = "CLOSED"

    stranger_wav = ROOT / "test_audio" / "giong_2_nguoi_la_mo_cua.wav"
    assert stranger_wav.exists(), f"Thieu file giong nguoi la: {stranger_wav}"
    b64 = base64.b64encode(stranger_wav.read_bytes()).decode("ascii")

    resp = client.post(
        "/api/voice_command",
        json={"wav_b64": b64, "audio_b64": b64, "pcm16k_b64": b64},
    )
    assert resp.status_code in (200, 401, 403), resp.text
    data = resp.json()

    assert data.get("ok") is False, f"Giong nguoi la khong duoc ok=True: {data}"
    assert data.get("authorized") is False, f"Giong nguoi la khong duoc authorized=True: {data}"
    assert data.get("level") != 1 and data.get("tier") != 1, f"Giong nguoi la bi nhan nham la Level 1: {data}"
    assert data.get("permission") == "DENIED", f"Giong nguoi la phai bi DENIED: {data}"
    assert _snapshot_device_state(data["snapshot"], "main_door") == "CLOSED", "Cua chinh KHONG duoc phep mo boi giong nguoi la!"


def test_looped_fake_mic_48k_audio_recognition_and_mobile_cookie_unlock():
    """Kiem thu luong fake-mic Chromium 48kHz -> 16kHz lap chu ky va cookie session_token mo khoa /app."""
    import numpy as np
    import wave

    client = TestClient(app)
    sep_dir = ROOT / "test_audio" / "cac_cau_lenh_cua_sep"

    for fname, exp_intent, dev_id, init_st, exp_st in [
        ("cau_2_mo_cua_chinh.wav", "OPEN_MAIN_DOOR", "main_door", "CLOSED", "OPEN"),
        ("cau_4_bat_den_phong_khach.wav", "TURN_ON_LIVING_ROOM_LIGHT", "living_room_light", "OFF", "ON"),
        ("cau_6_tat_het_den.wav", "TURN_OFF_ALL_LIGHTS", "living_room_light", "ON", "OFF"),
    ]:
        _REST_ENGINE.devices[dev_id]["state"] = init_st
        with wave.open(str(sep_dir / fname), "rb") as wf:
            pcm16 = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        # Gia lap 2.0s luong fake-mic lap chu ky voi cac do lech pha bat ky (bao gom giua nguyen am)
        looped = np.tile(pcm16, 4)
        for offset in (int(0.150 * 16000), 4000, 8000):
            _REST_ENGINE.devices[dev_id]["state"] = init_st
            cap_2s = looped[offset : offset + 32000]
            pcm_b64 = base64.b64encode(cap_2s.astype(np.int16).tobytes()).decode("ascii")

            resp = client.post(
                "/api/voice_command",
                json={"pcm16k_b64": pcm_b64, "is_live_mic": True},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True, f"Looped fake-mic {fname} (offset={offset}) that bai: {data}"
            assert data["level"] == 1
            assert data["permission"] == "ALLOWED"
            assert data["intent"] == exp_intent
            assert _snapshot_device_state(data["snapshot"], dev_id) == exp_st


def test_frontend_js_contains_serverless_voice_command_fallback():
    """Dam bao app.js va mobile_app.js deu goi /api/voice_command va cap nhat UI khi WebSocket khong mo tren Vercel."""
    app_js = (ROOT / "simulator" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    mobile_js = (ROOT / "simulator" / "static" / "js" / "mobile_app.js").read_text(encoding="utf-8")

    assert "/api/voice_command" in app_js
    assert "/api/voice_command" in mobile_js


def test_playwright_serverless_voice_commands_update_ui():
    """Playwright E2E: Khi chay o che do Vercel Serverless (_FORCE_HTTP_POLLING = true, khong co WebSocket):
    1. Enroll Level 1 tu level1_owner.wav va chay du 7 clip Chu nha (cau_1..cau_7) -> cap nhat UI switch + transcript.
    2. Chay 3 khau lenh Tieng Viet 'bat den phong khach', 'tat quat', 'mo cua chinh' qua /api/voice_command
       cho Level 1 (ALLOWED ca 3), Level 2 (ALLOWED den/quat, DENIED cua chinh) va Level 3 (ALLOWED den/quat, DENIED cua chinh).
    """
    import socket
    import subprocess
    import sys
    import time
    from playwright.sync_api import sync_playwright

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-m", "uvicorn", "simulator.server:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        import urllib.request

        base_url = f"http://127.0.0.1:{port}"
        ready = False
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"{base_url}/api/state", timeout=1.0) as r_chk:
                    if r_chk.status == 200:
                        ready = True
                        break
            except Exception:
                time.sleep(0.25)
        assert ready, "Khong the khoi dong Uvicorn server cho Playwright test"

        cmd_dir = VOICES_DIR / "level1_commands"
        b64_enroll_l1 = base64.b64encode((VOICES_DIR / "level1_owner.wav").read_bytes()).decode("ascii")
        b64_c1 = base64.b64encode((cmd_dir / "cau_1_xin_chao_chu_nha_cap1.wav").read_bytes()).decode("ascii")
        b64_c2 = base64.b64encode((cmd_dir / "cau_2_mo_cua_chinh.wav").read_bytes()).decode("ascii")
        b64_c3 = base64.b64encode((cmd_dir / "cau_3_dong_cua_chinh.wav").read_bytes()).decode("ascii")
        b64_c4 = base64.b64encode((cmd_dir / "cau_4_bat_den_phong_khach.wav").read_bytes()).decode("ascii")
        b64_c5 = base64.b64encode((cmd_dir / "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav").read_bytes()).decode("ascii")
        b64_c6 = base64.b64encode((cmd_dir / "cau_6_tat_het_den.wav").read_bytes()).decode("ascii")
        b64_c7 = base64.b64encode((cmd_dir / "cau_7_dong_het_cua.wav").read_bytes()).decode("ascii")

        b64_l2_light = base64.b64encode((VOICES_DIR / "level2_bat_den_phong_khach.wav").read_bytes()).decode("ascii")
        b64_l2_fan = base64.b64encode((VOICES_DIR / "level2_tat_quat.wav").read_bytes()).decode("ascii")
        b64_l2_door = base64.b64encode((VOICES_DIR / "level2_mo_cua_chinh.wav").read_bytes()).decode("ascii")

        b64_l3_light = base64.b64encode((VOICES_DIR / "level3_bat_den_phong_khach.wav").read_bytes()).decode("ascii")
        b64_l3_fan = base64.b64encode((VOICES_DIR / "level3_tat_quat.wav").read_bytes()).decode("ascii")
        b64_l3_door = base64.b64encode((VOICES_DIR / "level3_mo_cua_chinh.wav").read_bytes()).decode("ascii")

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context()
            context.add_init_script("window._FORCE_HTTP_POLLING = true;")
            page = context.new_page()
            page.goto(f"{base_url}/", wait_until="load", timeout=30000)
            page.wait_for_function("typeof window.executeVoiceCommandHttp === 'function'", timeout=25000)

            # Enroll Level 1 tu level1_owner.wav
            enr = page.evaluate(
                """async ([b64]) => {
                    const r = await fetch('/api/voice_auth/enroll_tier_pcm', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({wav_b64: b64, user_id: 'tuan_anh', user_name: 'Nguyễn Tuấn Anh', tier: 1})
                    });
                    return await r.json();
                }""",
                [b64_enroll_l1],
            )
            assert enr["ok"] is True

            # Chay 7 clip Chu nha Level 1 (cau_1..cau_7)
            r_c1 = page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_c1])
            assert r_c1["level"] == 1 and r_c1["permission"] == "ALLOWED"

            r_c2 = page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_c2])
            assert r_c2["level"] == 1 and r_c2["permission"] == "ALLOWED"
            assert page.is_checked("#dev-card-main_door .switch input") is True

            r_c3 = page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_c3])
            assert r_c3["level"] == 1 and r_c3["permission"] == "ALLOWED"
            assert page.is_checked("#dev-card-main_door .switch input") is False

            r_c4 = page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_c4])
            assert r_c4["level"] == 1 and r_c4["permission"] == "ALLOWED"
            assert page.is_checked("#dev-card-living_room_light .switch input") is True

            r_c5 = page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_c5])
            assert r_c5["level"] == 1 and r_c5["permission"] == "ALLOWED"
            assert page.is_checked("#dev-card-fan .switch input") is True
            assert page.is_checked("#dev-card-ac .switch input") is True

            r_c6 = page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_c6])
            assert r_c6["level"] == 1 and r_c6["permission"] == "ALLOWED"
            assert page.is_checked("#dev-card-living_room_light .switch input") is False
            assert page.is_checked("#dev-card-bedroom_light .switch input") is False

            # Mo cua truoc khi test cau_7 dong het cua, sau do test E2E 3 lenh Level 1 ('bat den phong khach', 'tat quat', 'mo cua chinh')
            page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_c2])
            assert page.is_checked("#dev-card-main_door .switch input") is True
            r_c7 = page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_c7])
            assert r_c7["level"] == 1 and r_c7["permission"] == "ALLOWED"
            assert page.is_checked("#dev-card-main_door .switch input") is False

            # E2E 3 lenh Chu nha Level 1: bat den phong khach, tat quat, mo cua chinh
            res1 = page.evaluate(
                "([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64, transcript: 'bat den phong khach' })",
                [b64_c4],
            )
            assert res1["permission"] == "ALLOWED"
            assert page.is_checked("#dev-card-living_room_light .switch input") is True

            res2 = page.evaluate(
                "([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64, transcript: 'tat quat' })",
                [b64_c5],
            )
            assert res2["permission"] == "ALLOWED"
            assert page.is_checked("#dev-card-fan .switch input") is False

            res3 = page.evaluate(
                "([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64, transcript: 'mo cua chinh' })",
                [b64_c2],
            )
            assert res3["permission"] == "ALLOWED"
            assert page.is_checked("#dev-card-main_door .switch input") is True

            # Dong cua, tat den, bat quat truoc khi test Level 2
            page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_c7])
            page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_c6])
            page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_c5])

            # Level 2 (Family Real Speech): bat den ALLOWED, tat quat ALLOWED, mo cua chinh DENIED
            r_l2_1 = page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_l2_light])
            assert r_l2_1["level"] == 2 and r_l2_1["permission"] == "ALLOWED"
            assert page.is_checked("#dev-card-living_room_light .switch input") is True

            r_l2_2 = page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_l2_fan])
            assert r_l2_2["level"] == 2 and r_l2_2["permission"] == "ALLOWED"
            assert page.is_checked("#dev-card-fan .switch input") is False

            r_l2_3 = page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_l2_door])
            assert r_l2_3["level"] == 2 and r_l2_3["permission"] == "DENIED"
            assert page.is_checked("#dev-card-main_door .switch input") is False

            # Reset truoc khi test Level 3
            page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_c6])
            page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_c5])

            # Level 3 (Guest Real Speech): bat den ALLOWED, tat quat ALLOWED, mo cua chinh DENIED
            r_l3_1 = page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_l3_light])
            assert r_l3_1["level"] == 3 and r_l3_1["permission"] == "ALLOWED"
            assert page.is_checked("#dev-card-living_room_light .switch input") is True

            r_l3_2 = page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_l3_fan])
            assert r_l3_2["level"] == 3 and r_l3_2["permission"] == "ALLOWED"
            assert page.is_checked("#dev-card-fan .switch input") is False

            r_l3_3 = page.evaluate("([b64]) => window.executeVoiceCommandHttp({ wav_b64: b64 })", [b64_l3_door])
            assert r_l3_3["level"] == 3 and r_l3_3["permission"] == "DENIED"
            assert page.is_checked("#dev-card-main_door .switch input") is False

            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
