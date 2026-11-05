"""TDD Test Suite for P8 Voice Rejection TTS (Web WebSocket, REST, and Android).

Anchors verified:
1. simulator/live/tts_rejection_vi.py: Real Vietnamese TTS 24kHz PCM (edge-tts vi-VN precached + fallback),
   NOT stationary 215Hz formant/glottal buzz.
2. simulator/live/gemini_bridge.py: Sends voice_auth_rejected with pcm24k_b64 and blocks Gemini TTS;
   does NOT send dead turn_complete=True prompt asking Gemini to speak on rejected sample turn.
3. simulator/voice/stt_pipeline.py, simulator/api/routes_devices.py, simulator/static/js/app.js:
   REST /api/voice_command includes pcm24k_b64 on reject (and accept/RBAC where applicable);
   executeVoiceCommandHttp plays pcm24k_b64 if present, else speechSynthesis (vi-VN) of exact_spoken_reply,
   for BOTH accept and reject, respecting chkSpeakReply.
4. android_app/.../MainScreen.kt: Speaks rejection_speech / exact_spoken_reply from server JSON when present.
"""

from __future__ import annotations

import asyncio
import base64
import pathlib
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient

from simulator.api.deps import AUDIO_DIR, _BOOT_VOICE_AUTH, _REST_ENGINE
from simulator.live.gemini_bridge import LiveBridgeSession
from simulator.live.tts_rejection_vi import (
    REJECTION_SCRIPTS,
    get_rejection_audio_b64,
    synthesize_vi_rejection_audio_24k,
)
from simulator.server import app

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _is_stationary_formant_buzz(pcm_bytes: bytes, sr: int = 24000) -> bool:
    """Detect the legacy synthetic 215Hz formant/glottal buzz generator.
    Real Vietnamese speech has pauses, unvoiced consonants (fricatives/plosives with high ZCR),
    and varying frame-to-frame spectral centroid, whereas the legacy buzz is a continuous
    215Hz harmonic wave modulated by a sine envelope with zero unvoiced frames.
    """
    pcm = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    if pcm.size < sr // 2:
        return True

    frame_len = int(sr * 0.025)  # 25ms
    hop = int(sr * 0.010)        # 10ms
    zcr_list = []
    rms_list = []
    centroid_list = []
    freqs = np.fft.rfftfreq(frame_len, d=1.0 / sr)
    win = np.hanning(frame_len)

    for start in range(0, len(pcm) - frame_len, hop):
        frame = pcm[start : start + frame_len]
        rms = float(np.sqrt(np.mean(frame * frame)))
        rms_list.append(rms)
        if rms > 0.015:
            zc = float(np.mean(np.abs(np.diff(np.signbit(frame)))))
            zcr_list.append(zc)
            spec = np.abs(np.fft.rfft(frame * win)) + 1e-9
            centroid = float(np.sum(freqs * spec) / np.sum(spec))
            centroid_list.append(centroid)

    if not zcr_list or not centroid_list:
        return True

    # Real speech has unvoiced consonants (s, x, kh, th, t, ch, ph -> ZCR > 0.12)
    # and dynamic spectral centroid (std > 250 Hz), plus low-energy pauses between words.
    max_zcr = float(np.max(zcr_list))
    centroid_std = float(np.std(centroid_list))
    rms_arr = np.array(rms_list)
    low_energy_ratio = float(np.mean(rms_arr < (0.15 * np.max(rms_arr))))

    # The old formant buzz has max_zcr ~ 0.028, centroid_std < 30 Hz, low_energy_ratio ~ 0.02
    if max_zcr < 0.08 or centroid_std < 180.0 or low_energy_ratio < 0.03:
        return True
    return False


def test_anchor1_tts_rejection_vi_is_real_vietnamese_speech_not_formant_buzz():
    """Anchor 1: synthesize_vi_rejection_audio_24k and get_rejection_audio_b64 must return
    real Vietnamese TTS 24kHz 16-bit mono PCM for all REJECTION_SCRIPTS, not formant buzz.
    """
    for code, script_text in REJECTION_SCRIPTS.items():
        pcm_bytes = synthesize_vi_rejection_audio_24k(code)
        b64_str = get_rejection_audio_b64(code)
        assert isinstance(pcm_bytes, bytes) and len(pcm_bytes) > 24000, f"PCM too short for {code}"
        assert len(pcm_bytes) % 2 == 0, f"PCM must be 16-bit aligned for {code}"
        assert base64.b64decode(b64_str) == pcm_bytes
        assert not _is_stationary_formant_buzz(pcm_bytes), (
            f"Script {code} ({script_text!r}) is still stationary formant buzz instead of real Vietnamese TTS!"
        )


def test_anchor2_gemini_bridge_reject_sends_pcm24k_once_without_dead_gemini_tts_prompt():
    """Anchor 2: On unauthorized sample/mic turn, LiveBridgeSession must send voice_auth_rejected
    with pcm24k_b64 ONCE and must NOT ask Gemini via send_client_content(turn_complete=True)
    to speak the reject sentence.
    """
    sent_messages: list[dict] = []

    async def _run():
        bridge = LiveBridgeSession(ws=None)
        bridge.send_ws_json = AsyncMock(side_effect=lambda payload: sent_messages.append(payload))
        mock_gemini = MagicMock()
        mock_gemini.send_client_content = AsyncMock()
        mock_gemini.send_realtime_input = AsyncMock()
        bridge.gemini_session = mock_gemini
        bridge.voice_auth.reset_strikes()

        await bridge.stream_wav_sample("giong_2_nguoi_la_mo_cua")
        return bridge, mock_gemini

    bridge, mock_gemini = asyncio.run(_run())

    rejected_msgs = [m for m in sent_messages if m.get("type") == "voice_auth_rejected"]
    assert len(rejected_msgs) == 1, f"Expected exactly 1 voice_auth_rejected message, got {len(rejected_msgs)}"
    rej_msg = rejected_msgs[0]
    assert rej_msg.get("pcm24k_b64"), "voice_auth_rejected must carry non-empty pcm24k_b64"
    assert bridge.last_mic_turn_blocked is True

    # Must NOT have sent turn_complete=True prompt asking Gemini to speak the rejection sentence
    for call in mock_gemini.send_client_content.call_args_list:
        kwargs = call.kwargs or {}
        assert kwargs.get("turn_complete") is not True, (
            "Dead/duplicate Gemini TTS prompt with turn_complete=True must not be sent on rejected sample turn!"
        )


def test_anchor3_rest_voice_command_returns_pcm24k_b64_and_app_js_plays_it():
    """Anchor 3: POST /api/voice_command must include pcm24k_b64 on unauthorized (and accept where applicable),
    and executeVoiceCommandHttp in simulator/static/js/app.js must play pcm24k_b64 or fallback to speechSynthesis (vi-VN).
    """
    client = TestClient(app)

    # 1. Stranger WAV via REST /api/voice_command
    intruder_wav = (AUDIO_DIR / "giong_2_nguoi_la_mo_cua.wav").read_bytes()
    intruder_b64 = base64.b64encode(intruder_wav).decode("ascii")
    resp_rej = client.post(
        "/api/voice_command",
        json={"wav_b64": intruder_b64, "transcript": "bật phòng ngủ lên"},
    )
    assert resp_rej.status_code == 200
    data_rej = resp_rej.json()
    assert data_rej.get("authorized") is False
    assert data_rej.get("pcm24k_b64"), "REST /api/voice_command reject response is missing pcm24k_b64!"
    pcm_rej = base64.b64decode(data_rej["pcm24k_b64"])
    assert len(pcm_rej) > 24000 and not _is_stationary_formant_buzz(pcm_rej)

    # 2. Missing/short audio 403 reject path in routes_devices.py
    resp_403 = client.post("/api/voice_command", json={"transcript": "bật phòng ngủ lên"})
    assert resp_403.status_code == 403
    data_403 = resp_403.json()
    assert data_403.get("authorized") is False
    assert data_403.get("pcm24k_b64"), "REST /api/voice_command 403 reject response is missing pcm24k_b64!"

    # 2b. Unauthenticated 401 reject path on POST /api/device
    resp_401 = client.post("/api/device", json={"device_id": "main_door", "action": "open"})
    assert resp_401.status_code == 401
    data_401 = resp_401.json()
    assert data_401.get("ok") is False
    assert data_401.get("rejection_speech")
    assert data_401.get("pcm24k_b64"), "POST /api/device 401 reject response is missing pcm24k_b64!"

    # 3. Verify executeVoiceCommandHttp in simulator/static/js/app.js plays pcm24k_b64 and falls back to speechSynthesis
    app_js = (ROOT / "simulator" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    fn_start = app_js.find("async function executeVoiceCommandHttp")
    assert fn_start != -1, "executeVoiceCommandHttp not found in app.js"
    fn_end = app_js.find("window.executeVoiceCommandHttp =", fn_start)
    fn_body = app_js[fn_start:fn_end]
    assert "playPcm24kChunk" in fn_body, "executeVoiceCommandHttp must call playPcm24kChunk when pcm24k_b64 is present"
    assert "speechSynthesis" in fn_body or "speakVietnamese" in fn_body, (
        "executeVoiceCommandHttp must fallback to speechSynthesis (vi-VN) when pcm24k_b64 is absent"
    )


def test_anchor4_android_main_screen_speaks_server_rejection_and_exact_spoken_reply():
    """Anchor 4: MainScreen.kt must speak rejection_speech / exact_spoken_reply from server JSON when present."""
    kt_path = (
        ROOT
        / "android_app"
        / "app-core"
        / "src"
        / "main"
        / "kotlin"
        / "vn"
        / "edu"
        / "hust"
        / "seee"
        / "smarthome"
        / "ui"
        / "main"
        / "MainScreen.kt"
    )
    kt_src = kt_path.read_text(encoding="utf-8")
    assert "rejection_speech" in kt_src, "MainScreen.kt must inspect rejection_speech from server JSON"
    assert "exact_spoken_reply" in kt_src, "MainScreen.kt must inspect exact_spoken_reply from server JSON"


def test_anchor5_vietnamese_stt_verifies_intelligible_rejection_speech():
    """Audible check: Decode returned 24kHz PCM and run Vietnamese STT (faster-whisper)
    to confirm intelligible Vietnamese rejection speech is produced.
    """
    import json
    import subprocess
    import sys

    ws_b64 = get_rejection_audio_b64("STRANGER_BLOCKED")
    client = TestClient(app)
    resp_403 = client.post("/api/voice_command", json={"transcript": "bật phòng ngủ lên"})
    assert resp_403.status_code == 403
    rest_b64 = resp_403.json()["pcm24k_b64"]

    stt_script = """
import base64, json, sys, numpy as np
from faster_whisper import WhisperModel
payload = json.loads(sys.stdin.read())
model = WhisperModel("medium", device="cpu", compute_type="int8", local_files_only=True)
out = {}
for k, b64 in payload.items():
    pcm24 = np.frombuffer(base64.b64decode(b64), dtype=np.int16).astype(np.float32) / 32768.0
    pcm16 = np.interp(
        np.linspace(0, len(pcm24) - 1, int(len(pcm24) * 16000 / 24000)),
        np.arange(len(pcm24)),
        pcm24,
    ).astype(np.float32)
    segs, _ = model.transcribe(pcm16, language="vi", beam_size=1, without_timestamps=True)
    out[k] = " ".join(s.text for s in segs).strip().lower()
print("STT_JSON:" + json.dumps(out, ensure_ascii=False))
"""
    proc = subprocess.run(
        [sys.executable, "-c", stt_script],
        input=json.dumps({"ws": ws_b64, "rest": rest_b64}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    marker_line = [ln for ln in proc.stdout.splitlines() if ln.startswith("STT_JSON:")][-1]
    res = json.loads(marker_line.split("STT_JSON:", 1)[1])
    tx_ws = res["ws"]
    tx_rest = res["rest"]

    assert "không được phép" in tx_ws and "nhận lệnh" in tx_ws, (
        f"Vietnamese STT failed to recognize STRANGER_BLOCKED PCM: {tx_ws!r}"
    )
    assert "từ chối" in tx_rest and "không có quyền" in tx_rest, (
        f"Vietnamese STT failed to recognize REST /api/voice_command reject PCM: {tx_rest!r}"
    )



