"""Bộ kiểm thử tự động toàn diện cho 8 yêu cầu sửa lỗi Voice Pipeline + Web RBAC + Durable Store (voicefix-20261110)."""

from __future__ import annotations

import asyncio
import base64
import json
import pathlib
import statistics
import tempfile
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient

from simulator.server import app
from simulator.auth.constants_and_crypto import DEFAULT_INVITE_LINKS
from simulator.auth.session_store import get_session_store
from simulator.auth_3layer import get_auth_3layer_manager
from simulator.durable_store import DurableStateStore, simulate_cold_start_recovery
from simulator.live.gemini_bridge import GeminiLiveBridge, StatefulPcmFramingBuffer
from simulator.live.prompt_builder import build_system_instruction
from simulator.live.tts_rejection_vi import (
    SAFE_DENY_REPEAT_PHRASE_VI,
    UNIFIED_REJECTION_PHRASE_VI,
)
from simulator.rule_engine import SmartHomeEngine
from simulator.voice.enrollment_quality import check_enrollment_quality_gate
from simulator.voice.wespeaker_onnx import (
    _is_encoded_container_bytes,
    extract_wespeaker_embedding,
    pcm_bytes_to_float32_16k,
)
from simulator.voice_auth import VoiceAuthManager
from simulator.voice_config import OWNER_EMAIL, OWNER_ID

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT_DIR / "test_audio"
DATA_DIR = ROOT_DIR / "simulator" / "data"
TACH_CAU_DIR = pathlib.Path(
    r"C:\Users\LENOVO\Documents\Sound Recordings\Giong_Tuan_Anh_Tach_Cau"
)


@pytest.fixture(scope="module", autouse=True)
def _preserve_simulator_data():
    """Sao lưu và khôi phục simulator/data sau khi chạy bộ test để không làm bẩn dữ liệu gốc."""
    backups: dict[pathlib.Path, bytes | None] = {}
    tracked_names = [
        "accounts_3layer.json",
        "auth_3layer_events.json",
        "family_email_allowlist.json",
        "invite_links_3layer.json",
        "user_sessions.json",
        "voiceprints.json",
        "overlay_rules.json",
    ]
    for name in tracked_names:
        p = DATA_DIR / name
        backups[p] = p.read_bytes() if p.exists() else None
    yield
    for p, raw in backups.items():
        if raw is None:
            if p.exists():
                p.unlink(missing_ok=True)
        else:
            p.write_bytes(raw)


def _load_owner_00_wav_bytes() -> bytes:
    cand1 = TACH_CAU_DIR / "00_doan_dau_mau_giong_chu_nha_tuan_anh.wav"
    if cand1.exists():
        return cand1.read_bytes()
    cand2 = AUDIO_DIR / "00_doan_dau_mau_giong_chu_nha_tuan_anh.wav"
    return cand2.read_bytes()


def _load_owner_self_check_bytes() -> bytes:
    if TACH_CAU_DIR.exists():
        clips = sorted(TACH_CAU_DIR.glob("[0-9][0-9]_*.wav"))
        parts = [c.read_bytes()[44:] for c in clips[1:5]]
        if parts:
            return b"".join(parts)
    raw_00 = _load_owner_00_wav_bytes()
    return raw_00[44 + 16000 * 2 * 14 :]


def test_req1_gate_audio_zero_bytes_stranger_and_owner_authorized() -> None:
    """Req 1: Buffer mic audio server-side; run speaker recognition FIRST; send 0 bytes to Gemini for strangers."""
    async def _run() -> None:
        ws_sent: list[dict[str, Any]] = []

        async def mock_ws_send(msg: dict[str, Any]) -> None:
            ws_sent.append(msg)

        engine = SmartHomeEngine()
        va = VoiceAuthManager(AUDIO_DIR)
        bridge = GeminiLiveBridge(engine=engine, voice_auth=va)
        bridge.send_ws_json = AsyncMock(side_effect=mock_ws_send)

        mock_session = MagicMock()
        mock_session.send_realtime_input = AsyncMock()
        mock_session.send_client_content = AsyncMock()
        mock_session.send_tool_response = AsyncMock()
        bridge.gemini_session = mock_session

        # 1A. Stranger mic chunks -> 0 bytes sent to Gemini send_realtime_input
        stranger_wav = (AUDIO_DIR / "giong_2_nguoi_la_mo_cua.wav").read_bytes()
        stranger_pcm = stranger_wav[44:]
        chunk_size = 4096
        for i in range(0, len(stranger_pcm), chunk_size):
            await bridge.handle_mic_chunk(stranger_pcm[i : i + chunk_size])
            # While buffering mic chunks, NOTHING is sent to Gemini
            assert mock_session.send_realtime_input.call_count == 0

        await bridge.mic_speech_ended()
        assert mock_session.send_realtime_input.call_count == 0, (
            "Stranger mic audio MUST send 0 frames / 0 bytes to Gemini send_realtime_input"
        )
        assert bridge.last_mic_turn_blocked is True
        assert bridge.engine.current_role == "UNKNOWN"
        assert mock_session.send_client_content.call_count >= 1

        # 1B. Stranger via stream_wav_sample -> 0 bytes sent to Gemini send_realtime_input
        mock_session.send_realtime_input.reset_mock()
        mock_session.send_client_content.reset_mock()
        await bridge.stream_wav_sample("giong_2_nguoi_la_mo_cua")
        assert mock_session.send_realtime_input.call_count == 0, (
            "Stranger WAV sample MUST send 0 frames / 0 bytes to Gemini send_realtime_input"
        )
        assert mock_session.send_client_content.call_count >= 1

        # 1C. Owner Tuấn Anh mic chunks -> buffered first (0 bytes during handle_mic_chunk),
        # then recognized as Tier 1 in mic_speech_ended, bound server-side, and flushed in 640B frames
        mock_session.send_realtime_input.reset_mock()
        mock_session.send_client_content.reset_mock()
        owner_clip_path = (
            TACH_CAU_DIR / "01_bat_den_phong_khach.wav"
            if (TACH_CAU_DIR / "01_bat_den_phong_khach.wav").exists()
            else AUDIO_DIR / "giong_1_chu_nha_cau_2.wav"
        )
        owner_pcm = owner_clip_path.read_bytes()[44:]
        for i in range(0, len(owner_pcm), chunk_size):
            await bridge.handle_mic_chunk(owner_pcm[i : i + chunk_size])
            assert mock_session.send_realtime_input.call_count == 0

        await bridge.mic_speech_ended()
        assert bridge.last_mic_turn_blocked is False
        assert bridge.engine.current_tier == 1
        assert bridge.engine.current_user_id == OWNER_ID
        assert mock_session.send_realtime_input.call_count > 0

    asyncio.run(_run())


def test_req2_safe_deny_short_noisy_and_overlapping_speakers() -> None:
    """Req 2: Too-short, noisy, or overlapping-speaker audio -> do not guess; ask to repeat with fixed Vietnamese phrase."""
    va = VoiceAuthManager(AUDIO_DIR)

    # 2A. Too-short audio (11_bat.wav = 0.20s active speech)
    if (TACH_CAU_DIR / "11_bat.wav").exists():
        res_11 = va.verify_pcm16k_and_apply_strikes((TACH_CAU_DIR / "11_bat.wav").read_bytes())
        assert res_11["authorized"] is False
        assert res_11["ask_repeat"] is True
        assert res_11["message"] == SAFE_DENY_REPEAT_PHRASE_VI
        assert res_11["strikes"] == 0

    # 2B. Synthetic too-short audio (0.15s)
    short_pcm = (np.sin(2 * np.pi * 140.0 * np.arange(int(0.15 * 16000)) / 16000.0) * 8000).astype(np.int16).tobytes()
    res_short = va.verify_pcm16k_and_apply_strikes(short_pcm)
    assert res_short["authorized"] is False
    assert res_short["ask_repeat"] is True
    assert res_short["message"] == SAFE_DENY_REPEAT_PHRASE_VI

    # 2C. Low SNR / noisy audio
    rng = np.random.default_rng(42)
    noisy_pcm = (rng.normal(0.0, 0.25, 16000 * 2) * 32767.0).clip(-32768, 32767).astype(np.int16).tobytes()
    res_noisy = va.verify_pcm16k_and_apply_strikes(noisy_pcm)
    assert res_noisy["authorized"] is False
    assert res_noisy["ask_repeat"] is True
    assert res_noisy["message"] == SAFE_DENY_REPEAT_PHRASE_VI

    # 2D. Overlapping speakers (Owner + Stranger speaking together)
    overlap_wav = (AUDIO_DIR / "hai_nguoi_cung_noi_cap1_va_nguoi_la.wav").read_bytes()
    res_ov = va.verify_pcm16k_and_apply_strikes(overlap_wav)
    assert res_ov["authorized"] is False
    assert res_ov["ask_repeat"] is True
    assert res_ov["reason"] == "OVERLAPPING_SPEAKERS"
    assert res_ov["message"] == SAFE_DENY_REPEAT_PHRASE_VI
    assert res_ov["strikes"] == 0


def test_req3_enrollment_quality_gate_and_held_out_clips_01_to_11() -> None:
    """Req 3: Enrollment quality gate (owner + guests) + re-enroll Owner from 00_*.wav + held-out clips 01..11."""
    wav_00 = _load_owner_00_wav_bytes()
    wav_sc = _load_owner_self_check_bytes()

    # 3A. Valid Owner enrollment (22.2s + >=3s self-check) -> PASS
    gate_pass = check_enrollment_quality_gate(
        enroll_pcm=wav_00,
        self_check_pcm=wav_sc,
        sr=16000,
        require_self_check=True,
    )
    assert gate_pass["ok"] is True, f"Expected PASS on 00_*.wav, got: {gate_pass}"
    assert gate_pass["require_rerecord"] is False
    assert gate_pass["metrics"]["net_speech_s"] >= 12.0
    assert gate_pass["metrics"]["silence_ratio"] <= 0.60
    assert -30.0 <= gate_pass["metrics"]["speech_rms_dbfs"] <= -12.0
    assert gate_pass["metrics"]["clipping_pct"] <= 0.1
    assert gate_pass["metrics"]["estimated_snr_db"] >= 15.0
    assert gate_pass["consistency"]["mean_cosine"] >= 0.90
    assert gate_pass["consistency"]["min_cosine"] >= 0.85
    assert gate_pass["self_check"]["net_speech_s"] >= 3.0
    assert gate_pass["self_check"]["cosine"] >= 0.88

    # 3B. Fail cases on check_enrollment_quality_gate
    # Fail 1: Net speech < 12s (first 5 seconds of 00_*.wav)
    short_5s = wav_00[44 : 44 + 16000 * 2 * 5]
    fail_short = check_enrollment_quality_gate(short_5s, wav_sc, sr=16000)
    assert fail_short["ok"] is False
    assert fail_short["require_rerecord"] is True
    assert "12" in fail_short["message"]

    # Fail 2: Silence > 60% (22.2s speech padded with 35s quiet room noise -> 66.5% silence > 60%)
    x_00 = pcm_bytes_to_float32_16k(wav_00, 16000)
    rng_sil = np.random.default_rng(7)
    quiet_room_tail = rng_sil.normal(0.0, 1e-4, 16000 * 35).astype(np.float32)
    excess_sil = np.concatenate([x_00, quiet_room_tail])
    fail_sil = check_enrollment_quality_gate(excess_sil, wav_sc, sr=16000)
    assert fail_sil["ok"] is False
    assert fail_sil["require_rerecord"] is True
    assert "khoảng lặng" in fail_sil["message"].lower() or "im lặng" in fail_sil["message"].lower()

    # Fail 3: Speech RMS too quiet (< -30 dBFS)
    quiet_x = x_00 * 0.02
    fail_quiet = check_enrollment_quality_gate(quiet_x, wav_sc, sr=16000)
    assert fail_quiet["ok"] is False
    assert fail_quiet["require_rerecord"] is True
    assert "nhỏ" in fail_quiet["message"].lower()

    # Fail 4: Clipping > 0.1% and too loud (> -12 dBFS)
    clipped_x = np.clip(x_00 * 8.0, -1.0, 1.0)
    fail_clip = check_enrollment_quality_gate(clipped_x, wav_sc, sr=16000)
    assert fail_clip["ok"] is False
    assert fail_clip["require_rerecord"] is True

    # Fail 5: Inconsistent 3s segments (splice 9s of stranger audio into middle of 00_*.wav)
    stranger_x = pcm_bytes_to_float32_16k((AUDIO_DIR / "giong_2_nguoi_la_mo_cua.wav").read_bytes(), 16000)
    mixed_x = x_00.copy()
    stranger_9s = np.resize(stranger_x, 16000 * 9)
    mixed_x[16000 * 3 : 16000 * 12] = stranger_9s
    fail_cons = check_enrollment_quality_gate(mixed_x, wav_sc, sr=16000)
    assert fail_cons["ok"] is False
    assert fail_cons["require_rerecord"] is True

    # Fail 6: Self-check sentence mismatch (stranger voice >= 3s)
    stranger_sc = np.resize(stranger_x, 16000 * 5)
    fail_sc = check_enrollment_quality_gate(wav_00, stranger_sc, sr=16000)
    assert fail_sc["ok"] is False
    assert fail_sc["require_rerecord"] is True
    assert "kiểm tra" in fail_sc["message"].lower() or "self-check" in fail_sc["message"].lower()

    # 3C. Enroll Owner Tuấn Anh (Cap 1) and test held-out clips 01..11
    va = VoiceAuthManager(AUDIO_DIR)
    enr_res = va.enroll_tier_voice_from_pcm16k(
        pcm_bytes=wav_00,
        user_id=OWNER_ID,
        user_name="Nguyễn Tuấn Anh",
        tier=1,
        role="ADMIN",
        self_check_pcm_bytes=wav_sc,
        enforce_12s_gate=True,
    )
    assert enr_res["ok"] is True

    if TACH_CAU_DIR.exists():
        clips = sorted(TACH_CAU_DIR.glob("[0-9][0-9]_*.wav"))
        recognized_01_10 = 0
        for cp in clips:
            if cp.name.startswith("00_"):
                continue
            res = va.verify_pcm16k_and_apply_strikes(cp.read_bytes())
            if cp.name.startswith("11_"):
                # 11_bat.wav is 0.20s active speech -> safe-denied as too short
                assert res["authorized"] is False
                assert res["ask_repeat"] is True
                assert res["message"] == SAFE_DENY_REPEAT_PHRASE_VI
            else:
                assert res["authorized"] is True, f"Held-out clip {cp.name} failed recognition: {res}"
                assert res["tier"] == 1
                assert res["user_id"] == OWNER_ID
                recognized_01_10 += 1
        assert recognized_01_10 == 10


def test_req4_unified_rejection_phrase_stranger_and_over_permission() -> None:
    """Req 4: One fixed Vietnamese rejection phrase for strangers AND over-permission requests, spoken by Aoede."""
    va = VoiceAuthManager(AUDIO_DIR)
    stranger_bytes = (AUDIO_DIR / "giong_2_nguoi_la_mo_cua.wav").read_bytes()

    # 4A. Stranger strikes 1, 2, 3, 4 -> always UNIFIED_REJECTION_PHRASE_VI, never silent_ignore
    for expected_strike in range(1, 5):
        res = va.verify_pcm16k_and_apply_strikes(stranger_bytes)
        assert res["authorized"] is False
        assert res["strikes"] == expected_strike
        assert res["should_reply"] is True
        assert res["silent_ignore"] is False
        assert res["message"] == UNIFIED_REJECTION_PHRASE_VI

    # 4B. Over-permission requests in SmartHomeEngine
    async def _run_rbac() -> None:
        engine = SmartHomeEngine()
        # Tier 2 trying to open main_door (ADMIN only)
        engine.set_active_user("thanh_vien_a")
        r_door = await engine.execute_device_action("main_door", "OPEN")
        assert r_door["ok"] is False
        assert r_door["rbac_blocked"] is True
        assert r_door["message"] == UNIFIED_REJECTION_PHRASE_VI

        # Tier 2 trying to grant permission (ADMIN only)
        r_grant = await engine.grant_user_permission("Khách X", 3)
        assert r_grant["ok"] is False
        assert r_grant["rbac_blocked"] is True
        assert r_grant["message"] == UNIFIED_REJECTION_PHRASE_VI

        # Tier 3 trying to turn on AC (MEMBER+ only)
        engine.set_active_user("khach_c")
        r_ac = await engine.execute_device_action("ac", "ON")
        assert r_ac["ok"] is False
        assert r_ac["rbac_blocked"] is True
        assert r_ac["message"] == UNIFIED_REJECTION_PHRASE_VI

        # GeminiLiveBridge tool call over-permission triggers Aoede send_client_content
        ws_sent: list[dict[str, Any]] = []
        bridge = GeminiLiveBridge(
            engine=engine,
            voice_auth=va,
        )
        bridge.send_ws_json = AsyncMock(side_effect=lambda m: ws_sent.append(m))
        mock_session = MagicMock()
        mock_session.send_realtime_input = AsyncMock()
        mock_session.send_client_content = AsyncMock()
        mock_session.send_tool_response = AsyncMock()
        bridge.gemini_session = mock_session

        bridge.mic_turn_verified = True
        bridge.last_mic_turn_blocked = False
        bridge.engine.set_active_user("thanh_vien_a")

        fc = MagicMock()
        fc.id = "call_1"
        fc.name = "control_device"
        fc.args = {"device_id": "main_door", "action": "OPEN"}
        res_tc = await bridge.handle_tool_call(fc)
        assert res_tc["rbac_blocked"] is True
        assert res_tc["message"] == UNIFIED_REJECTION_PHRASE_VI
        assert mock_session.send_client_content.call_count >= 1

    asyncio.run(_run_rbac())


def test_req5_exclusive_cap1_rbac_and_server_session_checks() -> None:
    """Req 5: Only Cap 1 (Tuan Anh) can grant/revoke permissions and enroll voices; all Cap 2 invite paths removed."""
    # 5A. INV-T2-TO-TIER3 completely removed
    assert "INV-T2-TO-TIER3" not in DEFAULT_INVITE_LINKS
    mgr = get_auth_3layer_manager()
    inv_t2 = mgr.get_invite_links_for_account("thanhviena.hust@gmail.com")
    assert inv_t2["can_invite"] is False
    assert inv_t2["allowed_target_tiers"] == []

    # 5B. Server-side session checks on endpoints
    client = TestClient(app)
    store = get_session_store()

    t2_sess = store.create_session(
        user_id="thanh_vien_a",
        tier=2,
        role="MEMBER",
        display_name="Thành viên A",
        email="thanhviena.hust@gmail.com",
    )
    t1_sess = store.create_session(
        user_id=OWNER_ID,
        tier=1,
        role="ADMIN",
        display_name="Nguyễn Tuấn Anh",
        email=OWNER_EMAIL,
    )

    t2_headers = {"Authorization": f"Bearer {t2_sess.session_id}"}
    t1_headers = {"Authorization": f"Bearer {t1_sess.session_id}"}

    # Anonymous & Tier 2 must be blocked (401/403) on all grant/revoke/invite/QR/enroll endpoints
    protected_post_endpoints = [
        ("/api/auth3/add_family_email", {"target_email": "newguest@gmail.com", "target_tier": 3}),
        ("/api/auth3/create_invite_link", {"target_tier": 3}),
        ("/api/auth3/send_invite_email", {"invite_code": "INV-T1-TO-TIER3", "recipient_email": OWNER_EMAIL}),
        ("/api/auth3/qr/generate", {"duration": "1d", "target_tier": 3}),
        ("/api/voice/enroll", {"user_id": "khach_c", "tier": 3, "pcm16k_b64": base64.b64encode(b"\x00" * 6400).decode()}),
        ("/api/auth3/enroll_voice_sample", {"email": "khachc.guest@gmail.com", "pcm16k_b64": base64.b64encode(b"\x00" * 6400).decode()}),
        ("/api/voice/grant", {"target_name": "Khách C", "target_tier": 3}),
        ("/api/voice/revoke", {"target_name": "Khách C"}),
        ("/api/users/grant", {"target_name": "Khách C", "target_tier": 3}),
        ("/api/users/revoke", {"target_name": "Khách C"}),
        ("/api/auth3/voice_permission_command", {"spoken_text": "Xóa quyền của Khách C"}),
    ]

    for url, body in protected_post_endpoints:
        r_anon = client.post(url, json=body)
        assert r_anon.status_code in (401, 403), f"Anon POST {url} should be 401/403, got {r_anon.status_code}"
        r_t2 = client.post(url, json=body, headers=t2_headers)
        assert r_t2.status_code == 403, f"Tier 2 POST {url} should be 403, got {r_t2.status_code}: {r_t2.text}"

    # Privilege escalation via /api/session/role must be blocked for non-Admin
    r_esc_anon = client.post("/api/session/role", json={"role": "tuan_anh"})
    assert r_esc_anon.status_code in (401, 403)
    r_esc_t2 = client.post("/api/session/role", json={"role": "tuan_anh"}, headers=t2_headers)
    assert r_esc_t2.status_code == 403

    # Cap 1 (Owner) session succeeds on QR generation and invite link creation
    r_qr_t1 = client.get("/api/auth3/guest_qr_current", headers=t1_headers)
    assert r_qr_t1.status_code == 200
    assert r_qr_t1.json()["ok"] is True

    r_inv_t1 = client.post("/api/auth3/create_invite_link", json={"target_tier": 3}, headers=t1_headers)
    assert r_inv_t1.status_code == 200
    assert r_inv_t1.json()["ok"] is True


def test_req6_no_pcm_zero_padding_and_no_false_mp3_detection() -> None:
    """Req 6: Remove mid-utterance PCM zero-padding and false MP3 sync-word detection on PCM frames."""
    # 6A. StatefulPcmFramingBuffer(640) produces 0 mid-utterance zero padding on unaligned chunks (e.g. 4096B, 1366B)
    framer = StatefulPcmFramingBuffer(640)
    raw_stream = bytes([(i % 251) + 1 for i in range(4096 * 3 + 1366)])  # non-zero bytes
    emitted: list[bytes] = []
    for chunk in (raw_stream[:4096], raw_stream[4096:8192], raw_stream[8192:12288], raw_stream[12288:]):
        frames = framer.push(chunk)
        for f in frames:
            assert len(f) == 640
            assert b"\x00" not in f, "Mid-utterance frame MUST NOT contain zero-padding!"
            emitted.append(f)

    reconstructed = b"".join(emitted) + framer.flush_remainder(pad_final=False)
    assert reconstructed == raw_stream

    # 6B. Negative PCM16 samples starting with 0xFF 0xFF (-1) or 0xFF 0xE0 (-32) must NOT trigger MP3 container decode
    neg_pcm = b"\xff\xff\xff\xe0" * 4000  # 16,000 bytes (0.5s at 16kHz)
    assert _is_encoded_container_bytes(neg_pcm) is False
    t0 = time.perf_counter()
    flt = pcm_bytes_to_float32_16k(neg_pcm, 16000)
    dt_ms = (time.perf_counter() - t0) * 1000.0
    assert len(flt) == 8000
    assert dt_ms < 5.0, f"Raw negative PCM16 decoding took {dt_ms:.2f}ms (should not spawn ffmpeg)"


def test_req7_durable_free_persistence_cold_start_recovery() -> None:
    """Req 7: Durable FREE persistence survives simulated Vercel serverless cold-start (/tmp wipe)."""
    with tempfile.TemporaryDirectory() as tmp_root:
        root_p = pathlib.Path(tmp_root)
        vault_dir = root_p / "durable_vault"
        tmp_data_dir = root_p / "tmp_smarthome_data"
        tmp_data_dir.mkdir(parents=True, exist_ok=True)

        store = DurableStateStore(vault_dir=vault_dir, offline_sandbox=True)

        vp_payload = {"tuan_anh": {"tier": 1, "f0_hz": 115.6, "wespeaker_embedding": [0.123] * 256}}
        acc_payload = [{"account_id": "tuan_anh", "email": OWNER_EMAIL, "tier": 1}]

        vp_bytes = json.dumps(vp_payload).encode("utf-8")
        acc_bytes = json.dumps(acc_payload).encode("utf-8")

        (tmp_data_dir / "voiceprints.json").write_bytes(vp_bytes)
        (tmp_data_dir / "accounts_3layer.json").write_bytes(acc_bytes)

        store.save_state_file("voiceprints.json", vp_bytes, sync_cloud=False, data_dir=tmp_data_dir)
        store.save_state_file("accounts_3layer.json", acc_bytes, sync_cloud=False, data_dir=tmp_data_dir)

        # Simulate Vercel cold-start: wipe tmp_data_dir completely
        rec = simulate_cold_start_recovery(tmp_data_dir, store=store)
        assert rec["ok"] is True
        assert "voiceprints.json" in rec["restored_files"]
        assert "accounts_3layer.json" in rec["restored_files"]
        assert (tmp_data_dir / "voiceprints.json").read_bytes() == vp_bytes
        assert (tmp_data_dir / "accounts_3layer.json").read_bytes() == acc_bytes


def test_req8_concise_system_prompt_and_latency_measurement() -> None:
    """Req 8: Concise complete Gemini system prompt + latency benchmark for recognition & API."""
    engine = SmartHomeEngine()
    prompt = build_system_instruction(engine)
    lines = [ln for ln in prompt.strip().splitlines() if ln.strip()]
    assert len(lines) <= 45, f"System prompt should be concise (<=45 non-empty lines), got {len(lines)}"
    assert UNIFIED_REJECTION_PHRASE_VI in prompt
    assert SAFE_DENY_REPEAT_PHRASE_VI in prompt
    assert "main_door" in prompt and "living_room_light" in prompt

    # Measure speaker recognition latency across held-out clips
    va = VoiceAuthManager(AUDIO_DIR)
    rec_latencies_ms: list[float] = []
    if TACH_CAU_DIR.exists():
        for cp in sorted(TACH_CAU_DIR.glob("[0-9][0-9]_*.wav"))[1:11]:
            raw = cp.read_bytes()
            t0 = time.perf_counter()
            va.verify_pcm16k_and_apply_strikes(raw)
            rec_latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    # Measure REST API latency
    client = TestClient(app)
    api_latencies_ms: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        resp = client.get("/api/state")
        assert resp.status_code == 200
        api_latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    if rec_latencies_ms:
        mean_rec = statistics.mean(rec_latencies_ms)
        assert mean_rec < 500.0, f"Mean recognition latency too high: {mean_rec:.1f}ms"
    mean_api = statistics.mean(api_latencies_ms)
    assert mean_api < 200.0, f"Mean API latency too high: {mean_api:.1f}ms"
