"""TDD Test Suite for P8 Voice Architecture (Requirement H Override):
Audio in -> speaker recognition decides the tier (1 owner / 2 family / 3 guest / stranger)
-> tier+name is injected into the Gemini Live session context
-> Gemini Live answers with its OWN fixed voice (Aoede).
No separate 24 kHz reject-TTS path (pcm24k_b64 removed from REST and voice_auth_rejected).
"""

from __future__ import annotations

import asyncio
import base64
import pathlib
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from simulator.api.deps import AUDIO_DIR
from simulator.live.gemini_bridge import LiveBridgeSession
from simulator.server import app

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_anchor1_separate_24khz_reject_tts_removed_from_pipeline_and_routes():
    """Anchor 1: stt_pipeline.py, routes_devices.py, and gemini_bridge.py must NOT attach
    separate 24kHz reject-TTS pcm24k_b64 payloads.
    """
    for rel in (
        "simulator/voice/stt_pipeline.py",
        "simulator/api/routes_devices.py",
        "simulator/live/gemini_bridge.py",
    ):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "get_rejection_audio_b64" not in src, f"{rel} still imports/uses get_rejection_audio_b64"
        assert "get_cached_speech_audio_b64" not in src, f"{rel} still imports/uses get_cached_speech_audio_b64"


def test_anchor2_gemini_bridge_injects_tier_and_name_into_gemini_live_context():
    """Anchor 2: On speaker recognition (both owner and stranger), LiveBridgeSession must inject
    the recognized tier + speaker name into Gemini Live session context via send_client_content,
    and voice_auth_rejected must NOT carry separate pcm24k_b64 TTS audio.
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
    assert len(rejected_msgs) == 1, f"Expected 1 voice_auth_rejected message, got {len(rejected_msgs)}"
    rej_msg = rejected_msgs[0]
    assert "pcm24k_b64" not in rej_msg, "voice_auth_rejected must NOT carry separate 24kHz reject-TTS pcm24k_b64"
    assert rej_msg.get("rejection_speech"), "voice_auth_rejected must include fixed Vietnamese rejection_speech"
    assert bridge.last_mic_turn_blocked is True
    assert bridge.last_mic_turn_silent_ignore is False

    # Verify tier+name context was injected into Gemini Live session
    assert mock_gemini.send_client_content.call_count >= 1
    injected_texts = []
    for call in mock_gemini.send_client_content.call_args_list:
        turns = (call.kwargs or {}).get("turns") or []
        for t in turns:
            for p in getattr(t, "parts", []) or []:
                if getattr(p, "text", None):
                    injected_texts.append(p.text)
    combined_ctx = "\n".join(injected_texts)
    assert "NGƯỜI LẠ" in combined_ctx or "UNKNOWN" in combined_ctx
    assert "Tôi không nhận ra giọng của bạn." in combined_ctx


def test_anchor3_rest_voice_command_and_tool_call_return_fixed_vietnamese_sentences_without_pcm24k():
    """Anchor 3: POST /api/voice_command and POST /api/device return fixed Vietnamese
    exact_spoken_reply / rejection_speech without separate pcm24k_b64 bloat.
    """
    client = TestClient(app)

    intruder_wav = (AUDIO_DIR / "giong_2_nguoi_la_mo_cua.wav").read_bytes()
    intruder_b64 = base64.b64encode(intruder_wav).decode("ascii")
    resp_rej = client.post(
        "/api/voice_command",
        json={"wav_b64": intruder_b64, "transcript": "bật phòng ngủ lên"},
    )
    assert resp_rej.status_code == 200
    data_rej = resp_rej.json()
    assert data_rej.get("authorized") is False
    assert "pcm24k_b64" not in data_rej
    assert data_rej.get("exact_spoken_reply")

    resp_403 = client.post("/api/voice_command", json={"transcript": "bật phòng ngủ lên"})
    assert resp_403.status_code == 403
    data_403 = resp_403.json()
    assert data_403.get("authorized") is False
    assert "pcm24k_b64" not in data_403
    assert data_403.get("exact_spoken_reply")

    resp_401 = client.post("/api/device", json={"device_id": "main_door", "action": "open"})
    assert resp_401.status_code == 401
    data_401 = resp_401.json()
    assert data_401.get("ok") is False
    assert "pcm24k_b64" not in data_401
    assert data_401.get("rejection_speech")

    app_js = (ROOT / "simulator" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    fn_start = app_js.find("async function executeVoiceCommandHttp")
    assert fn_start != -1, "executeVoiceCommandHttp not found in app.js"
    fn_end = app_js.find("window.executeVoiceCommandHttp =", fn_start)
    fn_body = app_js[fn_start:fn_end]
    assert "speakVietnameseFallback" in fn_body


def test_anchor4_android_main_screen_speaks_server_rejection_and_exact_spoken_reply():
    """Anchor 4: MainScreen.kt must inspect rejection_speech / exact_spoken_reply from server JSON."""
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
    assert "rejection_speech" in kt_src
    assert "exact_spoken_reply" in kt_src


def test_anchor7_only_tier1_can_grant_revoke_and_enroll():
    """Anchor 7 (Req I): ONLY Cấp 1 (Nguyễn Tuấn Anh) can grant/revoke permissions and enroll new voices."""
    import asyncio
    from simulator.live.prompt_builder import build_system_instruction, fn_admin_update_system_policy
    from simulator.rule_engine import SmartHomeEngine

    async def _run():
        eng = SmartHomeEngine()
        prompt = build_system_instruction(eng)
        enum_keys = fn_admin_update_system_policy.parameters.properties["policy_key"].enum
        for removed_key in ("tier2_can_revoke_same_tier", "tier2_can_grant_tier2", "tier3_can_grant_revoke"):
            assert removed_key not in eng.system_policies
            assert removed_key not in prompt
            assert removed_key not in enum_keys

        # Cấp 2 (thanh_vien_a) must be blocked from grant, revoke, and start_voice_enrollment
        eng.set_active_user("thanh_vien_a")
        assert eng.current_tier == 2
        g2 = await eng.grant_user_permission("Khách Thử", target_tier=3)
        r2 = await eng.revoke_user_permission("khach_c")
        e2 = await eng.start_voice_enrollment(target_tier=3, target_name="Khách Thử")
        assert g2["ok"] is False
        assert r2["ok"] is False
        assert e2["ok"] is False

        # Cấp 3 (khach_c) must be blocked from grant, revoke, and start_voice_enrollment
        eng.set_active_user("khach_c")
        assert eng.current_tier == 3
        g3 = await eng.grant_user_permission("Khách Thử", target_tier=3)
        r3 = await eng.revoke_user_permission("khach_c")
        e3 = await eng.start_voice_enrollment(target_tier=3, target_name="Khách Thử")
        assert g3["ok"] is False
        assert r3["ok"] is False
        assert e3["ok"] is False

        # Cấp 1 (tuan_anh) is allowed
        eng.set_active_user("tuan_anh")
        assert eng.current_tier == 1
        g1 = await eng.grant_user_permission("khach_c", target_tier=3)
        assert g1["ok"] is True

    asyncio.run(_run())
