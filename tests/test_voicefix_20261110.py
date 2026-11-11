"""Bộ kiểm thử tự động toàn diện cho 8 yêu cầu sửa lỗi Voice Pipeline + Web RBAC + Durable Store (voicefix-20261110)."""

from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import json
import simulator.voice_auth
import simulator.rule_engine
import os
import pathlib
import statistics
import subprocess
import sys
import tempfile
import time
import wave
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from simulator import durable_store
from simulator.server import app
from simulator.auth.constants_and_crypto import DEFAULT_INVITE_LINKS
from simulator.auth.session_store import get_session_store
from simulator.auth_3layer import get_auth_3layer_manager
from simulator.durable_store import (
    DurableStateStore,
    load_durable_json,
    save_durable_json,
    simulate_cold_start_recovery,
)
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
    evaluate_audio_quality_gate,
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
    """Nạp câu tự kiểm tra độc lập (không trùng bất kỳ clip held-out 01..11 hay 00_*.wav)."""
    indep_sc = AUDIO_DIR / "giong_chu_nha_cap1_tuan_anh.wav"
    if indep_sc.exists():
        return indep_sc.read_bytes()
    raw_00 = _load_owner_00_wav_bytes()
    return raw_00[44 + 16000 * 2 * 14 :]


def test_req1_gate_audio_zero_bytes_stranger_and_owner_authorized() -> None:
    """Req 1: Buffer mic audio server-side; run speaker recognition FIRST; send 0 bytes to Gemini for strangers and synthetic tones."""
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

        # 1C. Round-2 regression: 0.5s synthetic tones (80..160Hz) MUST NOT authorize or reach Gemini
        for hz in (80, 85, 90, 95, 150, 155, 160):
            tone_pcm = (
                np.sin(2 * np.pi * hz * np.arange(8000) / 16000.0) * 4000
            ).astype(np.int16).tobytes()
            va.reset_strikes()
            r_tone = va.verify_pcm16k_and_apply_strikes(tone_pcm)
            assert r_tone["authorized"] is False, f"{hz}Hz 0.5s tone must not authorize: {r_tone}"
            assert r_tone["ask_repeat"] is True
            assert r_tone["message"] == SAFE_DENY_REPEAT_PHRASE_VI

            mock_session.send_realtime_input.reset_mock()
            await bridge.handle_mic_chunk(tone_pcm)
            await bridge.mic_speech_ended()
            assert mock_session.send_realtime_input.call_count == 0, (
                f"{hz}Hz 0.5s tone must send 0 bytes to Gemini"
            )
            assert bridge.last_mic_turn_blocked is True

        # 1D. Owner Tuấn Anh mic chunks -> buffered first (0 bytes during handle_mic_chunk),
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
        if bridge._mic_silence_task:
            bridge._mic_silence_task.cancel()

    asyncio.run(_run())


def test_req2_safe_deny_short_noisy_and_overlapping_speakers() -> None:
    """Req 2: Too-short (<~1.5s), noisy, or overlapping-speaker audio -> do not guess; ask to repeat with fixed Vietnamese phrase."""
    va = VoiceAuthManager(AUDIO_DIR)

    # 2A. Default evaluate_audio_quality_gate enforces >= 1.5s minimum duration
    for sub_sec in (0.35, 0.50, 0.85, 1.20):
        sub_pcm = (
            np.sin(2 * np.pi * 135.0 * np.arange(int(sub_sec * 16000)) / 16000.0) * 6000
        ).astype(np.int16).tobytes()
        q_sub = evaluate_audio_quality_gate(sub_pcm, sr=16000)
        assert q_sub["ok"] is False
        assert q_sub["reason"] == "AUDIO_TOO_SHORT"
        r_sub = va.verify_pcm16k_and_apply_strikes(sub_pcm)
        assert r_sub["authorized"] is False
        assert r_sub["ask_repeat"] is True
        assert r_sub["message"] == SAFE_DENY_REPEAT_PHRASE_VI

    # 2B. Too-short audio (11_bat.wav = 0.20s active speech)
    if (TACH_CAU_DIR / "11_bat.wav").exists():
        res_11 = va.verify_pcm16k_and_apply_strikes((TACH_CAU_DIR / "11_bat.wav").read_bytes())
        assert res_11["authorized"] is False
        assert res_11["ask_repeat"] is True
        assert res_11["message"] == SAFE_DENY_REPEAT_PHRASE_VI
        assert res_11["strikes"] == 0

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
    assert gate_pass["metrics"]["net_speech_s"] >= 11.0
    assert gate_pass["metrics"]["silence_ratio"] <= 0.60
    assert -30.0 <= gate_pass["metrics"]["speech_rms_dbfs"] <= -12.0
    assert gate_pass["metrics"]["clipping_pct"] <= 0.1
    assert gate_pass["metrics"]["estimated_snr_db"] >= 15.0
    assert gate_pass["consistency"]["mean_cosine"] >= 0.90
    assert gate_pass["consistency"]["min_cosine"] >= 0.85
    assert gate_pass["self_check"]["net_speech_s"] >= 3.0
    assert gate_pass["self_check"]["cosine"] >= 0.88

    # 3B. Fail cases on check_enrollment_quality_gate
    # Fail 1: Net speech < 11s (first 5 seconds of 00_*.wav)
    short_5s = wav_00[44 : 44 + 16000 * 2 * 5]
    fail_short = check_enrollment_quality_gate(short_5s, wav_sc, sr=16000)
    assert fail_short["ok"] is False
    assert fail_short["require_rerecord"] is True
    assert "11" in fail_short["message"]

    # Boundary: 10.9s net speech rejected; 11.0s net speech accepted for the duration check.
    from simulator.voice.enrollment_quality import ENROLL_QUALITY_RULES, measure_enrollment_audio

    def _prefix_near_net_speech(src: bytes, target_s: float, sr: int = 16000):
        x = pcm_bytes_to_float32_16k(src, sr)
        lo, hi = 0, int(x.size)
        best = x[: max(sr, 1)]
        best_err = 1e9
        best_net = 0.0
        for _ in range(28):
            mid = (lo + hi) // 2
            if mid < sr // 2:
                lo = mid + 1
                continue
            metrics, _speech = measure_enrollment_audio(x[:mid], sr=sr)
            net = float(metrics["net_speech_s"])
            err = abs(net - target_s)
            if err < best_err:
                best_err = err
                best = x[:mid]
                best_net = net
            if net < target_s:
                lo = mid + 1
            else:
                hi = mid
        return best, best_net

    prefix_109, net_109 = _prefix_near_net_speech(wav_00, 10.90)
    assert 10.80 <= net_109 <= 10.949, f"could not trim to ~10.9s net, got {net_109}"
    fail_109 = check_enrollment_quality_gate(prefix_109, wav_sc, sr=16000, require_self_check=True)
    assert fail_109["ok"] is False
    assert fail_109["require_rerecord"] is True
    assert fail_109["checks"]["net_speech"] is False
    assert "11" in fail_109["message"]

    prefix_110, net_110 = _prefix_near_net_speech(wav_00, 11.00)
    assert 11.00 <= net_110 <= 11.12, f"could not trim to ~11.0s net, got {net_110}"
    gate_110 = check_enrollment_quality_gate(prefix_110, wav_sc, sr=16000, require_self_check=True)
    assert gate_110["checks"]["net_speech"] is True, f"11.0s net must pass duration check: {gate_110}"
    assert float(gate_110["metrics"]["net_speech_s"]) >= float(ENROLL_QUALITY_RULES["min_speech_s"])
    if not gate_110.get("ok"):
        assert "quá ngắn" not in str(gate_110.get("message") or "").lower()
        assert gate_110["checks"]["net_speech"] is True

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

    # 3C. Round-2 regression: Default enroll_tier_voice_from_pcm16k WITHOUT enforce_12s_gate or self_check MUST fail
    va = VoiceAuthManager(AUDIO_DIR)
    with patch(
        "simulator.voice_auth.check_enrollment_quality_gate",
        wraps=check_enrollment_quality_gate,
    ) as strict_spy:
        default_5s = va.enroll_tier_voice_from_pcm16k(
            pcm_bytes=short_5s,
            user_id="verify_only",
            user_name="Verify Only",
            tier=3,
            role="CHILD_GUEST",
            check_duplicate=False,
        )
        assert default_5s["ok"] is False
        assert strict_spy.call_count >= 1

    # 3D. Enroll Owner Tuấn Anh (Cap 1) with independent self-check and test held-out clips 01..11
    enr_res = va.enroll_tier_voice_from_pcm16k(
        pcm_bytes=wav_00,
        user_id=OWNER_ID,
        user_name="Nguyễn Tuấn Anh",
        tier=1,
        role="ADMIN",
        self_check_pcm_bytes=wav_sc,
    )
    assert enr_res["ok"] is True

    if TACH_CAU_DIR.exists():
        clips = sorted(TACH_CAU_DIR.glob("[0-9][0-9]_*.wav"))
        recognized_valid = 0
        safe_denied_short = 0
        for cp in clips:
            if cp.name.startswith("00_"):
                continue
            res = va.verify_pcm16k_and_apply_strikes(cp.read_bytes())
            if cp.name.startswith("11_"):
                # 11_bat.wav (0.20s active speech core) is < ~1.5s active speech -> safe-denied as too short
                assert res["authorized"] is False, f"Too-short clip {cp.name} must be safe-denied: {res}"
                assert res["ask_repeat"] is True
                assert res["reason"] == "AUDIO_TOO_SHORT"
                assert res["message"] == SAFE_DENY_REPEAT_PHRASE_VI
                safe_denied_short += 1
            else:
                assert res["authorized"] is True, f"Held-out clip {cp.name} failed recognition: {res}"
                assert res["tier"] == 1
                assert res["user_id"] == OWNER_ID
                recognized_valid += 1
        assert safe_denied_short == 1
        assert recognized_valid == 10


def test_req4_unified_rejection_phrase_stranger_and_over_permission() -> None:
    """Req 4: One fixed Vietnamese rejection phrase for strangers AND over-permission requests, spoken by Aoede only."""
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

    # 4B. Verify zero browser speechSynthesis fallback and zero non-Aoede TTS (Edge HoaiMyNeural) in codebase
    app_js = (ROOT_DIR / "simulator" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    mobile_js = (ROOT_DIR / "simulator" / "static" / "js" / "mobile_app.js").read_text(encoding="utf-8")
    tts_py = (ROOT_DIR / "simulator" / "live" / "tts_rejection_vi.py").read_text(encoding="utf-8")
    assert "speechSynthesis" not in app_js and "SpeechSynthesisUtterance" not in app_js
    assert "speechSynthesis" not in mobile_js and "SpeechSynthesisUtterance" not in mobile_js
    assert "edge_tts" not in tts_py and "HoaiMyNeural" not in tts_py
    assert not (ROOT_DIR / "simulator" / "live" / "tts_rejection_precache_24k.npz").exists()

    # 4B2. Verify Aoede generation receipt and bundled WAV integrity
    receipt_p = ROOT_DIR / "simulator" / "data" / "AOEDE_AUDIO_RECEIPT.json"
    assert receipt_p.exists(), f"AOEDE_AUDIO_RECEIPT.json must exist: {receipt_p}"
    receipt = json.loads(receipt_p.read_text(encoding="utf-8"))
    assert receipt["voice_name"] == "Aoede"
    assert receipt["generator_model"] == "gemini-3.8-live"
    for pkey in ("rejection", "safe_deny_repeat"):
        entry = receipt["phrases"][pkey]
        wfile = ROOT_DIR / "simulator" / "data" / entry["filename"]
        assert wfile.exists()
        wbytes = wfile.read_bytes()
        assert hashlib.sha256(wbytes).hexdigest() == entry["metrics"]["sha256"]
        assert entry["metrics"]["sample_rate_hz"] == 24000
        assert entry["content_verified"] is True

    # 4C. Over-permission requests in SmartHomeEngine + WAV path triggers Aoede
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

        # Even if server_connected is False, WAV sample still triggers Aoede send_client_content (never no-audio branch)
        mock_session.send_client_content.reset_mock()
        bridge.engine.server_connected = False
        await bridge.stream_wav_sample("giong_2_nguoi_la_mo_cua")
        assert mock_session.send_client_content.call_count >= 1
        bridge.engine.server_connected = True

    asyncio.run(_run_rbac())


def test_req5_exclusive_cap1_rbac_and_server_session_checks() -> None:
    """Req 5: Only Cap 1 (Tuan Anh) can grant/revoke permissions and enroll voices; /ws resolves session server-side."""
    # 5A. INV-T2-TO-TIER3 completely removed
    assert "INV-T2-TO-TIER3" not in DEFAULT_INVITE_LINKS
    mgr = get_auth_3layer_manager()
    inv_t2 = mgr.get_invite_links_for_account("thanhviena.hust@gmail.com")
    assert inv_t2["can_invite"] is False
    assert inv_t2["allowed_target_tiers"] == []

    # 5B. Server-side session checks on HTTP endpoints
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

    # 5C. Real WebSocket /ws tests: unauthenticated & Tier 2 blocked on enroll_owner_voice, set_role, grant, revoke
    with patch.object(
        GeminiLiveBridge, "gemini_receive_loop", new=AsyncMock()
    ), patch.object(
        GeminiLiveBridge, "_periodic_timer_sync", new=AsyncMock()
    ):
        # Unauthenticated WebSocket
        with client.websocket_connect("/ws") as ws_anon:
            for _ in range(3):
                ws_anon.receive_json()
            ws_anon.send_json({"type": "enroll_owner_voice", "pcm16k_b64": "AAAA", "tier": 1})
            msg1 = ws_anon.receive_json()
            assert msg1["type"] == "rbac_blocked"
            assert msg1["action"] == "enroll_owner_voice"
            assert msg1["message"] == UNIFIED_REJECTION_PHRASE_VI
            msg2 = ws_anon.receive_json()
            assert msg2["type"] == "voice_enrolled"
            assert msg2["result"]["ok"] is False
            msg3 = ws_anon.receive_json()
            assert msg3["type"] == "aoede_voice_request"
            msg3_aud = ws_anon.receive_json()
            assert msg3_aud["type"] == "audio_chunk"
            assert msg3_aud.get("voice") == "Aoede" and msg3_aud.get("pcm24k_b64")

            ws_anon.send_json({"type": "set_role", "role": "tuan_anh"})
            msg_role = ws_anon.receive_json()
            assert msg_role["type"] == "rbac_blocked"
            assert msg_role["action"] == "set_role"
            ws_anon.receive_json()  # aoede_voice_request
            ws_anon.receive_json()  # audio_chunk

            ws_anon.send_json({"type": "grant_user_permission", "target_name": "Khách Z", "target_tier": 2})
            msg_grant = ws_anon.receive_json()
            assert msg_grant["type"] == "rbac_blocked"
            assert msg_grant["action"] == "grant_user_permission"
            ws_anon.receive_json()  # aoede_voice_request
            ws_anon.receive_json()  # audio_chunk

        # Tier 2 WebSocket session -> still blocked on Cap 1 actions
        with client.websocket_connect(f"/ws?token={t2_sess.session_id}") as ws_t2:
            for _ in range(3):
                ws_t2.receive_json()
            ws_t2.send_json({"type": "enroll_owner_voice", "pcm16k_b64": "AAAA", "tier": 1})
            m_t2 = ws_t2.receive_json()
            assert m_t2["type"] == "rbac_blocked"
            assert m_t2["role"] == "MEMBER"

        # Tier 1 Owner WebSocket session -> allowed on set_role
        with client.websocket_connect(f"/ws?token={t1_sess.session_id}") as ws_t1:
            for _ in range(3):
                ws_t1.receive_json()
            ws_t1.send_json({"type": "set_role", "role": "tuan_anh"})
            m_t1 = ws_t1.receive_json()
            assert m_t1["type"] == "state_snapshot"
            assert m_t1["snapshot"]["current_tier"] == 1


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
    """Req 7: Durable FREE persistence (MIME IMAP round-trip, cloud-fail return False, cross-process cold-start)."""
    assert hasattr(durable_store, "load_durable_json")
    assert hasattr(durable_store, "save_durable_json")

    with tempfile.TemporaryDirectory() as tmp_root:
        root_p = pathlib.Path(tmp_root)
        vault_dir_1 = root_p / "durable_vault_1"
        vault_dir_2 = root_p / "durable_vault_2"
        tmp_data_dir = root_p / "tmp_smarthome_data"
        tmp_data_dir.mkdir(parents=True, exist_ok=True)

        store1 = DurableStateStore(vault_dir=vault_dir_1, offline_sandbox=True)

        # 7A. save_state_file(sync_cloud=True) MUST return False when cloud write fails
        with patch.object(store1, "_save_bundle_to_upstash_kv", return_value=False), patch.object(
            store1, "_save_bundle_to_gmail_imap", return_value=False
        ):
            ok_fail = store1.save_state_file("voiceprints.json", b"{}", sync_cloud=True)
            assert ok_fail is False, "save_state_file must return False when cloud write fails!"

        # 7B. Gmail IMAP MIME round-trip (save + load across two separate DurableStateStore instances & directories)
        captured_rfc822: list[bytes] = []

        class FakeImap:
            def __init__(self, *a: Any, **k: Any) -> None:
                pass

            def __enter__(self) -> "FakeImap":
                return self

            def __exit__(self, *a: Any) -> None:
                pass

            def login(self, *a: Any) -> None:
                pass

            def select(self, *a: Any, **k: Any) -> tuple[str, list[Any]]:
                return ("OK", [])

            def append(self, folder: str, flags: str, date: Any, msg: bytes) -> tuple[str, list[Any]]:
                captured_rfc822.append(msg)
                return ("OK", [])

            def search(self, *a: Any) -> tuple[str, list[bytes]]:
                return ("OK", [b"1"] if captured_rfc822 else [b""])

            def fetch(self, *a: Any) -> tuple[str, list[tuple[bytes, bytes]]]:
                return ("OK", [(b"1 (RFC822)", captured_rfc822[-1])])

        vp_payload = {"tuan_anh": {"tier": 1, "f0_hz": 115.6, "wespeaker_embedding": [0.123] * 256}}
        acc_payload = [{"account_id": "tuan_anh", "email": OWNER_EMAIL, "tier": 1}]
        vp_bytes = json.dumps(vp_payload).encode("utf-8")
        acc_bytes = json.dumps(acc_payload).encode("utf-8")

        (tmp_data_dir / "voiceprints.json").write_bytes(vp_bytes)
        (tmp_data_dir / "accounts_3layer.json").write_bytes(acc_bytes)

        with patch.object(
            DurableStateStore, "_get_gmail_credentials", return_value=("unit@example.invalid", "app-pw-test")
        ), patch("imaplib.IMAP4_SSL", FakeImap):
            ok_cloud = store1.save_state_file(
                "voiceprints.json", vp_bytes, sync_cloud=True, data_dir=tmp_data_dir
            )
            assert ok_cloud is True
            assert len(captured_rfc822) == 1

            # Brand-new DurableStateStore in a different empty directory recovers from FakeImap
            store2 = DurableStateStore(vault_dir=vault_dir_2, offline_sandbox=False)
            fresh_target = root_p / "fresh_cold_start_dir"
            rec_cloud = simulate_cold_start_recovery(fresh_target, store=store2)
            assert rec_cloud["ok"] is True
            assert rec_cloud["cloud_loaded"] is True
            assert (fresh_target / "voiceprints.json").read_bytes() == vp_bytes
            assert (fresh_target / "accounts_3layer.json").read_bytes() == acc_bytes

        # 7C. Cold-start recovery in a brand-new Python subprocess using vault_dir_1
        cold_sub_dir = root_p / "subprocess_cold_start_dir"
        env_sub = os.environ.copy()
        env_sub["PYTHONPATH"] = str(ROOT_DIR)
        env_sub["SMARTHOME_DURABLE_DIR"] = str(vault_dir_1)
        env_sub["SIMULATOR_OFFLINE_SANDBOX"] = "1"
        sub_code = (
            "import pathlib, json; "
            "from simulator.durable_store import DurableStateStore, simulate_cold_start_recovery; "
            f"st = DurableStateStore(vault_dir=pathlib.Path(r'{vault_dir_1}'), offline_sandbox=True); "
            f"res = simulate_cold_start_recovery(pathlib.Path(r'{cold_sub_dir}'), store=st); "
            "print(json.dumps(res))"
        )
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", sub_code],
            env=env_sub,
            capture_output=True,
            text=True,
            timeout=15.0,
            check=True,
        )
        sub_res = json.loads(proc.stdout.strip().splitlines()[-1])
        assert sub_res["ok"] is True
        assert (cold_sub_dir / "voiceprints.json").read_bytes() == vp_bytes
        assert (cold_sub_dir / "accounts_3layer.json").read_bytes() == acc_bytes

        # 7D. load_durable_json & save_durable_json round-trip
        json_file = tmp_data_dir / "custom_rules_overlay.json"
        assert save_durable_json("custom_rules_overlay.json", {"test_rule": 123}, json_file, sync_cloud=False, store=store1) is True
        loaded_json = load_durable_json("custom_rules_overlay.json", json_file, store=store1)
        assert loaded_json == {"test_rule": 123}

        # 7E. Atomic multi-layer rollback on failed cloud write for voiceprints (no leftover in vault/SQLite, no restore by sync)
        va_test = VoiceAuthManager(AUDIO_DIR)
        f_vp = tmp_data_dir / "voiceprints_rollback_probe.json"
        baseline_vp = {"baseline": {"marker": "before"}}
        cand_vp = {**baseline_vp, "failed_probe": {"marker": "must_not_survive"}}
        f_vp.write_text(json.dumps(baseline_vp), encoding="utf-8")
        st_rb = DurableStateStore(vault_dir=root_p / "rb_vault_vp", offline_sandbox=False)
        with patch.object(simulator.voice_auth, "VOICEPRINT_FILE", f_vp), \
             patch("simulator.durable_store.get_durable_store", return_value=st_rb), \
             patch("simulator.durable_store.is_offline_sandbox_or_test", return_value=False), \
             patch.object(st_rb, "_save_bundle_to_upstash_kv", return_value=False), \
             patch.object(st_rb, "_save_bundle_to_gmail_imap", return_value=False), \
             patch.object(st_rb, "_load_bundle_from_upstash_kv", return_value=None), \
             patch.object(st_rb, "_load_bundle_from_gmail_imap", return_value=None):
            ret_vp = va_test._save_voiceprints_safe(cand_vp)
            assert ret_vp is False
            disk_after_vp = json.loads(f_vp.read_text(encoding="utf-8"))
            assert disk_after_vp == baseline_vp
            cached_vp = json.loads(st_rb.load_state_file("voiceprints.json", sync_cloud=False) or b"{}")
            assert "failed_probe" not in cached_vp
            sync_rb = st_rb.sync_from_durable_store(data_dir=tmp_data_dir, force_cloud=True)
            assert sync_rb["cloud_loaded"] is False
            after_sync_vp = json.loads(f_vp.read_text(encoding="utf-8"))
            assert "failed_probe" not in after_sync_vp

        # 7F. Atomic multi-layer rollback on failed cloud write for grant_user_permission (no leftover in fresh store/vault)
        e_test = SmartHomeEngine()
        e_test.set_active_user(OWNER_ID)
        e_test.emit = AsyncMock()
        before_users = copy.deepcopy(e_test.users)
        f_ov = tmp_data_dir / "custom_rules_overlay_probe.json"
        f_ov.write_text(json.dumps(e_test.overlay_rules), encoding="utf-8")
        st_rb_grant = DurableStateStore(vault_dir=root_p / "rb_vault_grant", offline_sandbox=False)
        with patch.object(simulator.rule_engine, "OVERLAY_FILE", f_ov), \
             patch("simulator.durable_store.get_durable_store", return_value=st_rb_grant), \
             patch("simulator.durable_store.is_offline_sandbox_or_test", return_value=False), \
             patch.object(st_rb_grant, "_save_bundle_to_upstash_kv", return_value=False), \
             patch.object(st_rb_grant, "_save_bundle_to_gmail_imap", return_value=False), \
             patch.object(st_rb_grant, "_load_bundle_from_upstash_kv", return_value=None), \
             patch.object(st_rb_grant, "_load_bundle_from_gmail_imap", return_value=None):
            r_grant = asyncio.run(e_test.grant_user_permission("Khách Hỏng Cloud", 3))
            assert r_grant.get("ok") is False
            assert r_grant.get("status") == "DURABLE_PERSISTENCE_FAILED"
            assert e_test.users == before_users
            fresh_st = DurableStateStore(vault_dir=root_p / "rb_vault_grant", offline_sandbox=True)
            fresh_cached = json.loads(fresh_st.load_state_file("custom_rules_overlay.json", sync_cloud=False) or b"{}")
            assert "khach_hong_cloud" not in fresh_cached.get("users", {})
            sync_grant = st_rb_grant.sync_from_durable_store(data_dir=tmp_data_dir, force_cloud=True)
            assert sync_grant["cloud_loaded"] is False
            restored_ov = json.loads(f_ov.read_text(encoding="utf-8"))
            assert "khach_hong_cloud" not in restored_ov.get("users", {})

        # 7G. Destination file did not exist: failed cloud write must not leave a new file
        # (Codex ROUND 4 F2). Child process must also not see the failed candidate.
        f_vp_new = tmp_data_dir / "voiceprints_newfile_probe.json"
        if f_vp_new.exists():
            f_vp_new.unlink()
        cand_new = {"failed_probe": {"marker": "must_not_survive_new_file"}}
        st_new = DurableStateStore(vault_dir=root_p / "rb_vault_vp_new", offline_sandbox=False)
        with patch.object(simulator.voice_auth, "VOICEPRINT_FILE", f_vp_new), \
             patch("simulator.durable_store.get_durable_store", return_value=st_new), \
             patch("simulator.durable_store.is_offline_sandbox_or_test", return_value=False), \
             patch.object(st_new, "_save_bundle_to_upstash_kv", return_value=False), \
             patch.object(st_new, "_save_bundle_to_gmail_imap", return_value=False), \
             patch.object(st_new, "_load_bundle_from_upstash_kv", return_value=None), \
             patch.object(st_new, "_load_bundle_from_gmail_imap", return_value=None):
            ret_new = va_test._save_voiceprints_safe(cand_new)
            assert ret_new is False
            assert not f_vp_new.exists(), "Failed new-file voiceprint save left a destination file"
            fresh_new = DurableStateStore(vault_dir=root_p / "rb_vault_vp_new", offline_sandbox=True)
            fresh_new_cached = json.loads(fresh_new.load_state_file("voiceprints.json", sync_cloud=False) or b"{}")
            assert "failed_probe" not in fresh_new_cached
            child = subprocess.run(
                [sys.executable, "-c", "import pathlib,sys; p=pathlib.Path(sys.argv[1]); sys.exit(0 if not p.exists() else 1)", str(f_vp_new)],
                check=False,
            )
            assert child.returncode == 0

        # 7H. Grant when overlay file did not exist: no leftover user on disk or in a new process
        f_ov_new = tmp_data_dir / "custom_rules_overlay_newfile_probe.json"
        if f_ov_new.exists():
            f_ov_new.unlink()
        e_new = SmartHomeEngine()
        e_new.set_active_user(OWNER_ID)
        e_new.emit = AsyncMock()
        st_grant_new = DurableStateStore(vault_dir=root_p / "rb_vault_grant_new", offline_sandbox=False)
        with patch.object(simulator.rule_engine, "OVERLAY_FILE", f_ov_new), \
             patch("simulator.durable_store.get_durable_store", return_value=st_grant_new), \
             patch("simulator.durable_store.is_offline_sandbox_or_test", return_value=False), \
             patch.object(st_grant_new, "_save_bundle_to_upstash_kv", return_value=False), \
             patch.object(st_grant_new, "_save_bundle_to_gmail_imap", return_value=False), \
             patch.object(st_grant_new, "_load_bundle_from_upstash_kv", return_value=None), \
             patch.object(st_grant_new, "_load_bundle_from_gmail_imap", return_value=None):
            r_new = asyncio.run(e_new.grant_user_permission("Khach File Moi", 3))
            assert r_new.get("ok") is False
            assert r_new.get("status") == "DURABLE_PERSISTENCE_FAILED"
            assert not f_ov_new.exists(), "Failed new-file grant left an overlay file"
            blob = f_ov_new.read_text(encoding="utf-8") if f_ov_new.exists() else ""
            assert "khach_file_moi" not in blob.lower() and "Khach File Moi" not in blob
            child2 = subprocess.run(
                [sys.executable, "-c", "import pathlib,sys; p=pathlib.Path(sys.argv[1]); sys.exit(0 if not p.exists() else 1)", str(f_ov_new)],
                check=False,
            )
            assert child2.returncode == 0


def test_req8_concise_system_prompt_and_latency_measurement() -> None:
    """Req 8: Concise complete Gemini system prompt + /api/version + latency benchmark for recognition & API."""
    engine = SmartHomeEngine()
    prompt = build_system_instruction(engine)
    lines = [ln for ln in prompt.strip().splitlines() if ln.strip()]
    assert len(lines) <= 45, f"System prompt should be concise (<=45 non-empty lines), got {len(lines)}"
    assert UNIFIED_REJECTION_PHRASE_VI in prompt
    assert SAFE_DENY_REPEAT_PHRASE_VI in prompt
    assert "Tôi có thể giúp gì cho bạn?" not in prompt
    assert "main_door" in prompt and "living_room_light" in prompt

    # Verify /api/version endpoint for Deployment SHA Proof
    client = TestClient(app)
    r_ver = client.get("/api/version")
    assert r_ver.status_code == 200
    ver_json = r_ver.json()
    assert ver_json["ok"] is True
    assert len(str(ver_json.get("commit_sha", ""))) >= 7
    assert ver_json.get("single_voice") == "Aoede"

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


def test_round3_req2_active_speech_padded_short_clips() -> None:
    """Round 3 Req 2: ~1.5s threshold MUST apply to active speech, NOT container length padded with silence/noise."""
    va = VoiceAuthManager(AUDIO_DIR)
    client = TestClient(app)

    src_path = (
        TACH_CAU_DIR / "01_bat_den_phong_khach.wav"
        if (TACH_CAU_DIR / "01_bat_den_phong_khach.wav").exists()
        else AUDIO_DIR / "00_doan_dau_mau_giong_chu_nha_tuan_anh.wav"
    )
    src_pcm = src_path.read_bytes()[44:]

    rng = np.random.default_rng(123)
    quiet_noise_2s = (rng.normal(0.0, 8e-5, 16000 * 2) * 32767.0).astype(np.int16).tobytes()

    for offset_s, dur_s in ((0.0, 0.8), (0.2, 1.0), (0.4, 1.2), (1.0, 1.2)):
        raw_slice = src_pcm[int(offset_s * 32000) : int((offset_s + dur_s) * 32000)]
        padded_zero = raw_slice + b"\x00" * max(0, 64000 - len(raw_slice))
        padded_noise = raw_slice + quiet_noise_2s[: max(0, 72000 - len(raw_slice))]

        for label, candidate in (("zero_pad_2s", padded_zero), ("noise_pad_2.25s", padded_noise)):
            q = evaluate_audio_quality_gate(candidate, sr=16000)
            assert q["ok"] is False, f"{label} slice ({offset_s},{dur_s}) bypassed quality gate: {q}"
            assert q["reason"] == "AUDIO_TOO_SHORT"

            va.reset_strikes()
            ver = va.verify_pcm16k_and_apply_strikes(candidate)
            assert ver["authorized"] is False, f"{label} slice ({offset_s},{dur_s}) authorized: {ver}"
            assert ver["ask_repeat"] is True
            assert ver["reason"] == "AUDIO_TOO_SHORT"
            assert ver["strikes"] == 0
            assert ver["message"] == SAFE_DENY_REPEAT_PHRASE_VI

    # Also verify HTTP /api/voice_command and /api/auth3/layer3_voice (mode=verify) enforce active speech >= ~1.5s
    slice_1_2s_padded = src_pcm[int(0.4 * 32000) : int(1.6 * 32000)] + b"\x00" * (64000 - int(1.2 * 32000))
    b64_padded = base64.b64encode(slice_1_2s_padded).decode("ascii")

    r_vc = client.post("/api/voice_command", json={"pcm16k_b64": b64_padded})
    assert r_vc.status_code == 200
    vc_json = r_vc.json()
    assert vc_json["authorized"] is False
    assert vc_json["ask_repeat"] is True
    assert vc_json["reason"] == "AUDIO_TOO_SHORT"
    assert vc_json["exact_spoken_reply"] == SAFE_DENY_REPEAT_PHRASE_VI

    r_l3 = client.post(
        "/api/auth3/layer3_voice",
        json={"mode": "verify", "email": OWNER_EMAIL, "pcm16k_b64": b64_padded},
    )
    l3_json = r_l3.json()
    assert l3_json["ok"] is False
    assert l3_json.get("ask_repeat") is True

    # Mid-utterance hard cut (Codex ROUND 4 F1, offset 1.0s into clip 01): must still safe-deny.
    hard_slice = src_pcm[int(1.0 * 32000) : int(2.2 * 32000)]
    hard_padded = (b"\x00" * int(0.4 * 32000)) + hard_slice + (b"\x00" * int(0.4 * 32000))
    q_hard = evaluate_audio_quality_gate(hard_padded, sr=16000)
    assert q_hard["ok"] is False
    assert q_hard["reason"] == "AUDIO_TOO_SHORT"
    va.reset_strikes()
    ver_hard = va.verify_pcm16k_and_apply_strikes(hard_padded)
    assert ver_hard["authorized"] is False
    assert ver_hard["ask_repeat"] is True
    assert ver_hard["reason"] == "AUDIO_TOO_SHORT"


def test_round3_req3_mandatory_strict_enrollment_all_rest_and_qr_e2e() -> None:
    """Round 3 Req 3: Strict >=11s + separate >=3s self-check mandatory on ALL REST/QR paths + Guest QR E2E success."""
    import copy
    from simulator.api.routes_auth import _BOOT_VOICE_AUTH
    from simulator.voice.synthesis_augment import transform_pcm_by_pitch_factor

    client = TestClient(app)
    store = get_session_store()
    mgr = get_auth_3layer_manager()

    t1_sess = store.create_session(
        user_id=OWNER_ID,
        tier=1,
        role="ADMIN",
        display_name="Nguyễn Tuấn Anh",
        email=OWNER_EMAIL,
    )
    t1_headers = {"Authorization": f"Bearer {t1_sess.session_id}"}

    wav_00 = _load_owner_00_wav_bytes()
    wav_sc = _load_owner_self_check_bytes()
    short_5s_pcm = wav_00[44 : 44 + 16000 * 2 * 5]
    short_b64 = base64.b64encode(short_5s_pcm).decode("ascii")
    full_00_b64 = base64.b64encode(wav_00[44:]).decode("ascii")

    from simulator.api.deps import ROOT, _REST_ENGINE
    from simulator.durable_store import get_durable_store

    vp_disk_path = ROOT / "simulator" / "data" / "voiceprints.json"
    acc_disk_path = ROOT / "simulator" / "data" / "accounts_3layer.json"
    saved_vp_bytes = vp_disk_path.read_bytes()
    saved_acc_bytes = acc_disk_path.read_bytes()
    saved_profiles = copy.deepcopy(_BOOT_VOICE_AUTH.profiles)
    saved_eng_profiles = copy.deepcopy(getattr(_REST_ENGINE, "voice_auth", _BOOT_VOICE_AUTH).profiles)
    saved_accounts = copy.deepcopy(mgr.accounts)
    try:
        # 1. All REST enrollment endpoints MUST reject 5s audio (even with enforce_12s_gate=False) AND >=11s audio missing self-check
        rest_cases = [
            (
                "/api/auth3/layer3_voice",
                {"mode": "enroll", "email": OWNER_EMAIL, "pcm16k_b64": short_b64, "enforce_12s_gate": False},
            ),
            (
                "/api/auth3/layer3_voice",
                {"mode": "enroll", "email": OWNER_EMAIL, "pcm16k_b64": full_00_b64, "enforce_12s_gate": False},
            ),
            (
                "/api/auth3/enroll_first_page_voice",
                {"email": OWNER_EMAIL, "pcm16k_b64": short_b64, "enforce_12s_gate": False},
            ),
            (
                "/api/auth3/enroll_first_page_voice",
                {"email": OWNER_EMAIL, "pcm16k_b64": full_00_b64, "enforce_12s_gate": False},
            ),
            (
                "/api/auth3/enroll_voice_sample",
                {"email": OWNER_EMAIL, "pcm16k_b64": short_b64, "enforce_12s_gate": False},
            ),
            (
                "/api/voice/enroll",
                {"user_id": OWNER_ID, "tier": 1, "pcm16k_b64": short_b64, "enforce_12s_gate": False},
            ),
            (
                "/api/mobile/enroll_voice",
                {"user_id": OWNER_ID, "tier": 1, "pcm16k_b64": short_b64, "enforce_12s_gate": False},
            ),
        ]
        for endpoint, payload in rest_cases:
            resp = client.post(endpoint, json=payload, headers=t1_headers)
            body = resp.json()
            assert resp.status_code == 400, f"{endpoint} did not return 400 on invalid enroll: {resp.status_code} {body}"
            assert body.get("ok") is False, f"{endpoint} accepted invalid enroll: {body}"

        # 2. End-to-End Guest QR Enrollment:
        #    Step A: Cap 1 generates dynamic QR token
        r_qr = client.get("/api/auth3/guest_qr_current", headers=t1_headers)
        assert r_qr.status_code == 200
        qr_data = r_qr.json()
        assert qr_data["ok"] is True

        #    Step B: Guest scans QR and performs handshake
        r_hs = client.post(
            "/api/auth3/guest_qr_handshake",
            json={
                "token": qr_data["token"],
                "window": qr_data["window"],
                "duration": qr_data["duration"],
            },
        )
        assert r_hs.status_code == 200
        hs_data = r_hs.json()
        assert hs_data["ok"] is True
        guest_sess_id = hs_data["guest_session_id"]

        #    Step C: Guest attempting 5s audio or missing self_check on /api/qr/guest_enroll MUST fail with 400
        r_qr_bad1 = client.post(
            "/api/qr/guest_enroll",
            json={
                "session_id": guest_sess_id,
                "guest_name": "Khách Ngắn",
                "pcm16k_b64": short_b64,
                "enforce_12s_gate": False,
            },
        )
        assert r_qr_bad1.status_code == 400
        assert r_qr_bad1.json()["ok"] is False

        #    Step D: Guest submits valid >=11s speech + >=3s separate self-check (real distinct human voice) -> succeeds E2E!
        with wave.open(str(AUDIO_DIR / "giong_2_nguoi_la_mo_cua.wav"), "rb") as wf_guest:
            stranger_pcm = wf_guest.readframes(wf_guest.getnframes())
        quiet_pad = (np.sin(2.0 * np.pi * 200.0 * np.arange(8000) / 16000.0) * 8.0).astype(np.int16).tobytes()
        guest_main_pcm = quiet_pad + (stranger_pcm * 9) + quiet_pad
        guest_sc_pcm = quiet_pad + (stranger_pcm * 3) + quiet_pad
        r_qr_verify = client.post(
            "/api/qr/guest_enroll",
            json={
                "session_id": guest_sess_id,
                "guest_name": "Khách QR Hợp Lệ",
                "pcm16k_b64": base64.b64encode(guest_main_pcm).decode("ascii"),
                "self_check_pcm_b64": base64.b64encode(guest_sc_pcm).decode("ascii"),
                "verify_only": True,
            },
        )
        assert r_qr_verify.status_code == 200, f"Guest QR verify_only failed: {r_qr_verify.text}"
        assert r_qr_verify.json()["ok"] is True

        r_qr_ok = client.post(
            "/api/qr/guest_enroll",
            json={
                "session_id": guest_sess_id,
                "guest_name": "Khách QR Hợp Lệ",
                "pcm16k_b64": base64.b64encode(guest_main_pcm).decode("ascii"),
                "self_check_pcm_b64": base64.b64encode(guest_sc_pcm).decode("ascii"),
            },
        )
        assert r_qr_ok.status_code == 200, f"Guest QR final enroll failed: {r_qr_ok.text}"
        qr_ok_body = r_qr_ok.json()
        assert qr_ok_body["ok"] is True
        assert qr_ok_body["tier"] == 3

        #    Step E: Held-out guest command is recognized as Tier 3 Guest!
        guest_cmd_pcm = stranger_pcm
        _BOOT_VOICE_AUTH.reset_strikes()
        ver_guest = _BOOT_VOICE_AUTH.verify_pcm16k_and_apply_strikes(guest_cmd_pcm)
        assert ver_guest["authorized"] is True, f"Enrolled QR guest not recognized on held-out clip: {ver_guest}"
        assert ver_guest["tier"] == 3
    finally:
        _BOOT_VOICE_AUTH.profiles = saved_profiles
        if hasattr(_REST_ENGINE, "voice_auth"):
            _REST_ENGINE.voice_auth.profiles = saved_eng_profiles
        mgr.accounts = saved_accounts
        vp_disk_path.write_bytes(saved_vp_bytes)
        acc_disk_path.write_bytes(saved_acc_bytes)
        get_durable_store().save_state_file("voiceprints.json", saved_vp_bytes, sync_cloud=False, data_dir=vp_disk_path.parent)
        get_durable_store().save_state_file("accounts_3layer.json", saved_acc_bytes, sync_cloud=False, data_dir=acc_disk_path.parent)


def test_round3_req4_aoede_audio_delivery_http_and_disconnected_wav() -> None:
    """Round 3 Req 4: Real 24kHz Aoede audio MUST be returned on HTTP /api/voice_command AND disconnected WAV."""
    import io
    import wave

    client = TestClient(app)

    def _assert_valid_aoede_wav(payload: dict[str, Any]) -> None:
        assert payload.get("audio_voice") == "Aoede"
        assert payload.get("audio_sample_rate") == 24000
        wav_b64 = payload.get("audio_wav_b64") or payload.get("audio_b64")
        pcm_b64 = payload.get("pcm24k_b64") or payload.get("pcm_b64")
        assert isinstance(wav_b64, str) and len(wav_b64) > 4000
        assert isinstance(pcm_b64, str) and len(pcm_b64) > 4000
        wav_bytes = base64.b64decode(wav_b64)
        assert wav_bytes[:4] == b"RIFF" and wav_bytes[8:12] == b"WAVE"
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            assert wf.getframerate() == 24000
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            frames = wf.readframes(wf.getnframes())
            samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            dur_s = len(samples) / 24000.0
            rms_db = 20.0 * np.log10(float(np.sqrt(np.mean(samples * samples))) + 1e-12)
            assert dur_s >= 1.0, f"Aoede audio too short: {dur_s:.2f}s"
            assert rms_db > -38.0, f"Aoede audio silent/too quiet: {rms_db:.1f} dBFS"

    # 1. HTTP /api/voice_command on short 0.5s 80Hz tone -> ask_repeat + real Aoede audio
    tone_05s = (np.sin(2 * np.pi * 80.0 * np.arange(8000) / 16000.0) * 4000).astype(np.int16).tobytes()
    r_tone = client.post("/api/voice_command", json={"pcm16k_b64": base64.b64encode(tone_05s).decode("ascii")})
    assert r_tone.status_code == 200
    j_tone = r_tone.json()
    assert j_tone["authorized"] is False
    assert j_tone["ask_repeat"] is True
    assert j_tone["exact_spoken_reply"] == SAFE_DENY_REPEAT_PHRASE_VI
    _assert_valid_aoede_wav(j_tone)

    # 2. HTTP /api/voice_command on stranger voice -> unified rejection phrase + real Aoede audio
    stranger_pcm = (AUDIO_DIR / "giong_2_nguoi_la_mo_cua.wav").read_bytes()[44:]
    r_str = client.post("/api/voice_command", json={"pcm16k_b64": base64.b64encode(stranger_pcm).decode("ascii")})
    assert r_str.status_code == 200
    j_str = r_str.json()
    assert j_str["authorized"] is False
    assert j_str["exact_spoken_reply"] == UNIFIED_REJECTION_PHRASE_VI
    _assert_valid_aoede_wav(j_str)

    # 3. Dedicated Aoede fixed-phrase endpoint for UI playback without /ws
    r_phrase = client.post("/api/voice/aoede_phrase", json={"phrase": UNIFIED_REJECTION_PHRASE_VI})
    assert r_phrase.status_code == 200
    _assert_valid_aoede_wav(r_phrase.json())

    r_bad_phrase = client.post("/api/voice/aoede_phrase", json={"phrase": "Arbitrary arbitrary text"})
    assert r_bad_phrase.status_code == 400

    # 4. Disconnected WAV sample with gemini_session=None and server_connected=False MUST emit audio_chunk
    async def _check_wav_offline() -> None:
        va = VoiceAuthManager(AUDIO_DIR)
        bridge = GeminiLiveBridge(engine=SmartHomeEngine(), voice_auth=va)
        bridge.engine.server_connected = False
        bridge.send_ws_json = AsyncMock()
        assert bridge.gemini_session is None
        await bridge.stream_wav_sample("giong_2_nguoi_la_mo_cua")
        events = [c.args[0] for c in bridge.send_ws_json.call_args_list]
        audio_events = [e for e in events if e.get("type") == "audio_chunk"]
        assert len(audio_events) >= 1, f"Expected audio_chunk events when gemini_session is None, got {[e.get('type') for e in events]}"
        assert all(bool(e.get("audio_b64") and e.get("pcm_b64") and e.get("pcm24k_b64")) for e in audio_events)

    asyncio.run(_check_wav_offline())


def test_round3_req5_gemini_tool_call_session_guard_and_ws_isolation() -> None:
    """Round 3 Req 5: Admin Gemini tool-calls require server-side Cap 1 session; no Cap 2 QR; per-WS identity isolation."""
    from types import SimpleNamespace

    # 1. Cap 2 cannot issue dynamic QR tokens in qr_totp_mixin
    mgr = get_auth_3layer_manager()
    r_qr_t2 = mgr.generate_dynamic_qr_token(issuer_tier=2, duration_type="1d")
    assert r_qr_t2["ok"] is False

    # 2. Gemini tool-call path MUST require server-side Cap 1 ws_session even if engine.current_tier == 1
    async def _check_tool_guards() -> None:
        va = VoiceAuthManager(AUDIO_DIR)
        store = get_session_store()
        t2_sess = store.create_session(
            user_id="thanh_vien_a",
            tier=2,
            role="MEMBER",
            display_name="Thành viên A",
            email="thanhviena.hust@gmail.com",
        )

        for ws_sess in (None, t2_sess):
            bridge = GeminiLiveBridge(engine=SmartHomeEngine(), voice_auth=va, ws_session=ws_sess)
            bridge.engine.set_active_user(OWNER_ID)
            assert bridge.engine.current_tier == 1
            bridge.send_ws_json = AsyncMock()
            bridge._sync_rules_context_to_gemini = AsyncMock()

            admin_tools = [
                ("grant_user_permission", {"target_name": "Probe Guest", "target_tier": 3}),
                ("revoke_user_permission", {"target_name": "Khách C"}),
                ("start_voice_enrollment", {"user_name": "Probe Guest", "tier": 3}),
                ("finalize_voice_enrollment", {}),
                ("set_query_permission_policy", {"allow_tier3_query": True}),
                ("admin_update_system_policy", {"key": "test", "value": "1"}),
                ("admin_upsert_knowledge_rag", {"topic": "t", "content": "c"}),
                ("factory_reset", {}),
            ]
            with patch.object(
                bridge.engine, "grant_user_permission", new=AsyncMock(return_value={"ok": False})
            ) as mock_grant, patch.object(
                bridge.engine, "revoke_user_permission", new=AsyncMock(return_value={"ok": False})
            ) as mock_revoke:
                for tool_name, args in admin_tools:
                    res = await bridge.handle_tool_call(SimpleNamespace(id="tc_1", name=tool_name, args=args))
                    assert res.get("ok") is False, f"Admin tool {tool_name} was not blocked without Cap1 session: {res}"
                    assert res.get("rbac_blocked") is True
                    assert res.get("message") == UNIFIED_REJECTION_PHRASE_VI
                assert mock_grant.call_count == 0
                assert mock_revoke.call_count == 0

    asyncio.run(_check_tool_guards())

    # 3. Per-WS connection identity isolation: Cap 1 set_role on WS1 MUST NOT leak Tier 1 to anonymous WS2
    client = TestClient(app)
    store = get_session_store()
    t1_sess = store.create_session(
        user_id=OWNER_ID,
        tier=1,
        role="ADMIN",
        display_name="Nguyễn Tuấn Anh",
        email=OWNER_EMAIL,
    )
    with patch.object(GeminiLiveBridge, "gemini_receive_loop", new=AsyncMock()), patch.object(
        GeminiLiveBridge, "_periodic_timer_sync", new=AsyncMock()
    ):
        with client.websocket_connect(f"/ws?token={t1_sess.session_id}") as ws1:
            for _ in range(3):
                ws1.receive_json()
            ws1.send_json({"type": "set_role", "role": "tuan_anh"})
            snap1 = ws1.receive_json()
            assert snap1["type"] == "state_snapshot"
            assert snap1["snapshot"]["current_tier"] == 1

            with client.websocket_connect("/ws") as ws2:
                init_msgs = [ws2.receive_json() for _ in range(3)]
                snaps2 = [m["snapshot"] for m in init_msgs if m.get("type") == "state_snapshot"]
                assert len(snaps2) >= 1
                assert snaps2[0]["current_tier"] != 1, f"WS1 Cap1 tier leaked to anonymous WS2: {snaps2[0]}"
                assert snaps2[0]["role"] == "UNKNOWN"


def test_round3_req7_cloud_persistence_failure_rolls_back_and_fails_closed() -> None:
    """Round 3 Req 7: Cloud write failures MUST return False, roll back in-memory mutations, and return ok=False."""
    import copy

    va = VoiceAuthManager(AUDIO_DIR)
    wav_00 = _load_owner_00_wav_bytes()
    wav_sc = _load_owner_self_check_bytes()

    # 1. _save_voiceprints_safe returns False when save_durable_json fails
    with patch("simulator.durable_store.save_durable_json", return_value=False) as mock_save_json:
        ret = va._save_voiceprints_safe()
        assert mock_save_json.call_count == 1
        assert ret is False

    # 2. Full enrollment fails closed and rolls back profiles when both KV and IMAP cloud backends fail
    before_profiles = copy.deepcopy(va.profiles)
    with tempfile.TemporaryDirectory() as td:
        st = DurableStateStore(vault_dir=pathlib.Path(td), offline_sandbox=False)
        with patch.object(st, "_save_bundle_to_upstash_kv", return_value=False) as mock_kv, patch.object(
            st, "_save_bundle_to_gmail_imap", return_value=False
        ) as mock_imap, patch("simulator.durable_store.get_durable_store", return_value=st), patch(
            "simulator.durable_store.is_offline_sandbox_or_test", return_value=False
        ), patch.object(st, "save_state_file", wraps=st.save_state_file) as spy_save:
            r_enr = va.enroll_tier_voice_from_pcm16k(
                pcm_bytes=wav_00,
                self_check_pcm_bytes=wav_sc,
                user_id="cloud_fail_probe_user",
                user_name="Cloud Fail Probe",
                tier=3,
                role="CHILD_GUEST",
                check_duplicate=False,
            )
            assert r_enr["ok"] is False, f"Enrollment succeeded despite forced cloud write failure: {r_enr}"
            assert r_enr["status"] == "DURABLE_PERSISTENCE_FAILED"
            assert spy_save.call_count >= 1
            assert mock_kv.call_count >= 1
            assert mock_imap.call_count >= 1
            assert "cloud_fail_probe_user" not in va.profiles
            assert set(va.profiles.keys()) == set(before_profiles.keys())

            # 3. Grant permission in SmartHomeEngine also fails closed and rolls back when cloud save fails
            async def _check_grant_rollback() -> None:
                engine = SmartHomeEngine()
                engine.set_active_user(OWNER_ID)
                before_users = copy.deepcopy(engine.users)
                r_gr = await engine.grant_user_permission("Khách Cloud Lỗi", 3)
                assert r_gr["ok"] is False, f"Grant succeeded despite cloud failure: {r_gr}"
                assert r_gr.get("status") == "DURABLE_PERSISTENCE_FAILED"
                assert engine.users == before_users

            asyncio.run(_check_grant_rollback())

def _guest_tach_cau_dir() -> pathlib.Path | None:
    """Locate the stranger/guest held-out WAV folder by path only (do not move or copy files)."""
    candidates = [
        pathlib.Path(r"C:\Users\LENOVO\Documents\Sound Recordings\Giong_Khach_Nguoi_La_Tach_Cau"),
    ]
    desktop = pathlib.Path(r"C:\Users\LENOVO\Desktop")
    if desktop.is_dir():
        for child in desktop.iterdir():
            cand = child / "test_audio" / "giong_khach_nguoi_la_tach_cau"
            if cand.is_dir():
                candidates.append(cand)
    for p in candidates:
        if p.is_dir() and any(p.glob("08_*.wav")):
            return p
    return None


def test_stranger_guest_clips_must_not_authorize_as_owner() -> None:
    """Regression: 12 guest/stranger WAVs must never be authorized as Cap 1 / owner.

    Files are referenced by path and must not be modified, moved, or committed.
    Privileged grant/revoke require a stricter WeSpeaker threshold than ordinary commands.
    """
    from simulator.voice.biometrics_neural import verify_speaker_identity_256d
    from simulator.voice_config import (
        THRESHOLD_WESPEAKER_PRIVILEGED,
        THRESHOLD_WESPEAKER_TIER1,
    )

    guest_dir = _guest_tach_cau_dir()
    if guest_dir is None:
        pytest.skip("guest/stranger held-out folder not present on this machine")

    va = VoiceAuthManager(AUDIO_DIR)
    stranger_official_as_owner = []
    stranger_helper_as_owner = []
    official_scores: dict[str, float] = {}
    clips = sorted(guest_dir.glob("[0-9][0-9]_*.wav"))
    assert len(clips) == 12, f"expected 12 guest clips in {guest_dir}, got {len(clips)}"

    for cp in clips:
        raw = cp.read_bytes()
        ver = va.verify_pcm16k_and_apply_strikes(raw)
        official_scores[cp.name] = float(ver.get("wespeaker_cosine") or 0.0)
        if ver.get("authorized") is True and int(ver.get("tier") or 0) == 1:
            stranger_official_as_owner.append((cp.name, ver))
        authorized, speaker_id, tier, _sim = verify_speaker_identity_256d(raw, va.profiles)
        if authorized and int(tier) == 1 and speaker_id == "owner_voice_1":
            stranger_helper_as_owner.append((cp.name, authorized, speaker_id, tier, _sim))
        # Privileged gate must also refuse (including mid-threshold fake owner scores).
        priv = va.evaluate_privileged_voice_gate(analysis=ver)
        assert priv.get("ok") is False, f"privileged gate must refuse stranger {cp.name}: {priv}"
        if cp.name.startswith("08_") or cp.name.startswith("09_"):
            assert ver.get("authorized") is not True
            assert int(ver.get("tier") or 99) != 1

    assert stranger_official_as_owner == [], f"official verifier authorized strangers as owner: {stranger_official_as_owner}"
    assert stranger_helper_as_owner == [], f"256d helper authorized strangers as owner: {stranger_helper_as_owner}"

    # Owner held-out must still pass the official verifier (except the known too-short 11_bat).
    if TACH_CAU_DIR.exists():
        owner_ok = 0
        for cp in sorted(TACH_CAU_DIR.glob("[0-9][0-9]_*.wav")):
            if cp.name.startswith("00_"):
                continue
            res = va.verify_pcm16k_and_apply_strikes(cp.read_bytes())
            if cp.name.startswith("11_"):
                assert res.get("authorized") is False
                assert res.get("reason") == "AUDIO_TOO_SHORT"
                continue
            assert res.get("authorized") is True, f"owner held-out failed: {cp.name} {res}"
            assert res.get("tier") == 1
            owner_ok += 1
            if cp.name.startswith("08_") or cp.name.startswith("09_"):
                priv = va.evaluate_privileged_voice_gate(analysis=res)
                assert priv.get("ok") is True, f"owner privileged clip must pass tighter gate: {cp.name} {priv}"
                assert float(priv.get("wespeaker_cosine") or 0.0) >= THRESHOLD_WESPEAKER_PRIVILEGED
        assert owner_ok == 10

    # Defense in depth: a bare 0.435-0.59 'owner' score must not unlock grant/revoke.
    mid = va.evaluate_privileged_voice_gate(
        analysis={
            "authorized": True,
            "tier": 1,
            "user_id": OWNER_ID,
            "wespeaker_cosine": max(THRESHOLD_WESPEAKER_TIER1, 0.45),
        }
    )
    assert mid.get("ok") is False
    assert mid.get("reason") == "PRIVILEGED_VOICE_THRESHOLD"
    assert THRESHOLD_WESPEAKER_PRIVILEGED >= 0.55
