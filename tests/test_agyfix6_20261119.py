"""Comprehensive real-user test suite for agyfix6_20261119:
1. Acoustic echo suppression (Client JS via Node.js + Server Python + Real WAV barge-in).
2. Natural Vietnamese AI output sanitizer & system prompt hygiene.
3. Full AI Tool Suite (devices, sensors, settings, timers, schedules) with RBAC, pool isolation, confirmation & cancel.
4. Guest QR UI structure & controls (desktop + mobile + dark mode).
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import subprocess
import time
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from simulator.auth.session_store import UserSession
from simulator.automation_repo import GUEST_ONLY_TOGGLE_MSG_VI
from simulator.live.echo_and_speech_guard import (
    ECHO_SIMILARITY_THRESHOLD,
    ECHO_WINDOW_SEC,
    SERVER_PLAYBACK_TAIL_SEC,
    ServerEchoGuard,
    sanitize_spoken_vietnamese_text,
)
from simulator.live.gemini_bridge import LiveBridgeSession, MODEL
from simulator.live.prompt_builder import (
    ALL_TOOLS,
    FIXED_REJECTION_PHRASE_VI,
    build_system_instruction,
    make_live_config,
)
from simulator.rule_engine import SmartHomeEngine
from simulator.voice.session_voice_command import (
    process_session_voice_command,
    reset_session_echo_guards,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ECHO_GUARD_JS = REPO_ROOT / "simulator" / "static" / "js" / "voice_echo_guard.js"
SAMPLE_USER_WAV = REPO_ROOT / "test_audio" / "cac_cau_lenh_cua_sep" / "cau_4_bat_den_phong_khach.wav"


def _make_session(user_id: str, display_name: str, tier: int, role: str) -> UserSession:
    now = time.time()
    return UserSession(
        session_id=f"sess_{user_id}_{int(now * 1000)}",
        user_id=user_id,
        email=f"{user_id}@example.com",
        display_name=display_name,
        tier=tier,
        role=role,
        created_at=now,
        expires_at=now + 3600,
        source="test_agyfix6",
        is_authenticated=True,
    )


def _make_bridge(engine: SmartHomeEngine, session: UserSession) -> LiveBridgeSession:
    mock_ws = AsyncMock()
    mock_ws.headers = {}
    mock_ws.cookies = {}
    mock_ws.query_params = {}
    return LiveBridgeSession(ws=mock_ws, engine=engine, ws_session=session)


def _fc(name: str, args: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=f"fc_{name}", name=name, args=args or {})


# =============================================================================
# 1. ACOUSTIC ECHO GUARD (CLIENT JS LOOPBACK + REAL WAV BARGE-IN + SERVER)
# =============================================================================


class TestEchoGuardClientAndServer:
    def test_client_js_echo_loopback_blocked_and_real_wav_barge_in(self) -> None:
        assert ECHO_GUARD_JS.exists(), "Missing voice_echo_guard.js"
        assert SAMPLE_USER_WAV.exists(), "Missing read-only user WAV sample"

        # Read real user WAV (strictly read-only) and compute peak/active frames
        with wave.open(str(SAMPLE_USER_WAV), "rb") as wf:
            sr = wf.getframerate()
            raw_pcm = wf.readframes(wf.getnframes())
        assert sr == 16000 and len(raw_pcm) > 6400

        node_script = r"""
const fs = require("fs");
const guardMod = require(process.argv[1]);
const wavPath = process.argv[2];

// Verify named constants and mandatory browser AEC constraints
const constraints = guardMod.getStandardMicConstraints({ channelCount: 1 });
if (constraints.audio.echoCancellation !== true ||
    constraints.audio.noiseSuppression !== true ||
    constraints.audio.autoGainControl !== false) {
  throw new Error("Standard mic constraints must enable AEC/NS and disable AGC");
}
if (guardMod.ECHO_TAIL_HOLD_MS !== 400) {
  throw new Error("Expected ECHO_TAIL_HOLD_MS === 400, got " + guardMod.ECHO_TAIL_HOLD_MS);
}
if (guardMod.BARGE_IN_HOLD_MS < 200 || guardMod.BARGE_IN_HOLD_MS > 350) {
  throw new Error("Unexpected BARGE_IN_HOLD_MS: " + guardMod.BARGE_IN_HOLD_MS);
}

// 1) Loopback test: AI plays 1000ms audio; mic picks up echo during playback + 400ms tail
let bargeCount = 0;
const guard = guardMod.createVoiceEchoGuard({
  onBargeIn: () => { bargeCount += 1; },
});
let t = 1000;
guard.notePlaybackQueued(1000, t); // playing from t=1000..2000, tail until 2400

let sentDuringPlayOrTail = 0;
for (let step = 0; step < 69; step++) { // 69 * 20ms = 1380ms (t=1000..2360)
  const res = guard.evaluateMicFrame({ rms: 0.032, frameDurationMs: 20, nowMs: t });
  if (res.allowSend) sentDuringPlayOrTail += 1;
  t += 20;
}
if (sentDuringPlayOrTail !== 0) {
  throw new Error("Echo leaked during playback/tail: " + sentDuringPlayOrTail);
}
if (bargeCount !== 0) {
  throw new Error("Echo falsely triggered barge-in: " + bargeCount);
}

// Immediately after 400ms tail (t=2420), mic must re-open for normal user speech
const afterTail = guard.evaluateMicFrame({ rms: 0.035, frameDurationMs: 20, nowMs: 2420 });
if (!afterTail.allowSend || afterTail.phase !== "IDLE") {
  throw new Error("Mic failed to re-open after 400ms tail: " + JSON.stringify(afterTail));
}

// 2) Short loud click (< 250ms) during AI playback must NOT trigger barge-in
guard.notePlaybackQueued(1500, 3000);
let shortSpikeSent = 0;
for (let k = 0; k < 8; k++) { // 160ms < 250ms
  const r = guard.evaluateMicFrame({ rms: 0.18, frameDurationMs: 20, nowMs: 3100 + k * 20 });
  if (r.allowSend) shortSpikeSent += 1;
}
if (shortSpikeSent !== 0 || bargeCount !== 0) {
  throw new Error("Short transient <250ms falsely triggered barge-in");
}

// 3) Real user WAV barge-in test: feed real user speech frames above echo level for >= 250ms
const wavBuf = fs.readFileSync(wavPath);
const pcmOffset = 44;
const totalSamples = Math.floor((wavBuf.length - pcmOffset) / 2);
const samples = new Int16Array(totalSamples);
for (let i = 0; i < totalSamples; i++) {
  samples[i] = wavBuf.readInt16LE(pcmOffset + i * 2);
}

// Find active speech window in real WAV and normalize to clear near-field speech level (~0.22 RMS)
const frameSamples = 320; // 20ms at 16kHz
const activeFrames = [];
for (let off = 0; off + frameSamples <= samples.length; off += frameSamples) {
  const slice = samples.subarray(off, off + frameSamples);
  const rms = guardMod.computePcm16Rms(slice);
  if (rms > 0.015) activeFrames.push(rms);
}
if (activeFrames.length < 20) {
  throw new Error("Expected >= 20 active speech frames in real user WAV, got " + activeFrames.length);
}
const meanSpeechRms = activeFrames.reduce((a, b) => a + b, 0) / activeFrames.length;
const gain = Math.max(1.0, 0.22 / Math.max(meanSpeechRms, 0.001));

guard.clearPlayback(5000);
guard.notePlaybackQueued(2000, 5000);
// Prime estimated echo level at ~0.03 RMS for 100ms
for (let k = 0; k < 5; k++) {
  guard.evaluateMicFrame({ rms: 0.03, frameDurationMs: 20, nowMs: 5000 + k * 20 });
}

let triggeredAtMs = -1;
let nowBarge = 5120;
for (let k = 0; k < Math.min(activeFrames.length, 30); k++) {
  const loudRms = Math.min(0.95, activeFrames[k] * gain);
  const res = guard.evaluateMicFrame({ rms: loudRms, frameDurationMs: 20, nowMs: nowBarge });
  if (res.bargeInTriggered) {
    triggeredAtMs = nowBarge - 5120;
    break;
  }
  nowBarge += 20;
}
if (triggeredAtMs < 240 || bargeCount !== 1) {
  throw new Error("Real WAV barge-in failed: triggeredAtMs=" + triggeredAtMs + " bargeCount=" + bargeCount);
}
console.log(JSON.stringify({
  ok: true,
  sentDuringPlayOrTail,
  afterTailAllowed: afterTail.allowSend,
  triggeredAtMs,
  bargeCount,
  activeWavFrames: activeFrames.length,
}));
"""
        proc = subprocess.run(
            ["node", "-e", node_script, str(ECHO_GUARD_JS), str(SAMPLE_USER_WAV)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert proc.returncode == 0, f"Node echo guard test failed: {proc.stderr}\n{proc.stdout}"
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        assert data["ok"] is True
        assert data["sentDuringPlayOrTail"] == 0
        assert data["afterTailAllowed"] is True
        assert data["bargeCount"] == 1
        assert data["triggeredAtMs"] >= 240

    def test_all_mic_capture_surfaces_enable_aec_and_fix_holdoff_sign(self) -> None:
        app_js = (REPO_ROOT / "simulator" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        mobile_js = (REPO_ROOT / "simulator" / "static" / "js" / "mobile_app.js").read_text(encoding="utf-8")
        guest_enroll_js = (REPO_ROOT / "simulator" / "static" / "js" / "guest_enroll.js").read_text(encoding="utf-8")
        android_kt = (
            REPO_ROOT / "android_app" / "app-core" / "src" / "main" / "kotlin" /
            "vn" / "edu" / "hust" / "seee" / "smarthome" / "ui" / "main" / "MainScreen.kt"
        ).read_text(encoding="utf-8")

        assert "echoCancellation: false" not in app_js
        assert "echoCancellation: true" in app_js
        assert "nextPlayTime > audioCtxOut.currentTime + TTS_HOLDOFF_SEC" not in app_js
        assert "echoCancellation: true" in mobile_js
        assert "noiseSuppression: true" in mobile_js
        assert "autoGainControl: false" in mobile_js
        assert "autoGainControl: true" not in mobile_js
        assert "echoCancellation: true" in guest_enroll_js
        assert "VOICE_COMMUNICATION" in android_kt
        assert "AcousticEchoCanceler" in android_kt

    def test_server_echo_guard_suppresses_loopback_and_allows_real_commands(self) -> None:
        guard = ServerEchoGuard()
        t0 = 100.0
        guard.record_ai_utterance("Đã bật đèn phòng khách rồi ạ.", now=t0)

        # Exact match within 8s -> suppressed
        is_echo, score, reason = guard.check_echo_transcript("Đã bật đèn phòng khách rồi ạ.", now=t0 + 1.5)
        assert is_echo is True and score >= ECHO_SIMILARITY_THRESHOLD and reason

        # Case / diacritics stripped / slight ASR drift -> suppressed
        is_echo2, score2, _ = guard.check_echo_transcript("da bat den phong khach roi a", now=t0 + 3.0)
        assert is_echo2 is True and score2 >= ECHO_SIMILARITY_THRESHOLD

        # Long substring of AI sentence -> suppressed
        is_echo3, _, reason3 = guard.check_echo_transcript("bật đèn phòng khách rồi", now=t0 + 4.0)
        assert is_echo3 is True and reason3

        # Unrelated user command -> NOT suppressed
        is_echo4, _, _ = guard.check_echo_transcript("Tắt quạt trần giúp mình", now=t0 + 2.0)
        assert is_echo4 is False

        # After 8s window expires -> NOT suppressed
        is_echo5, _, _ = guard.check_echo_transcript("Đã bật đèn phòng khách rồi ạ.", now=t0 + ECHO_WINDOW_SEC + 1.0)
        assert is_echo5 is False

        # Playback + 400ms tail tracking
        guard.note_ai_audio_chunk(48000, sample_rate=24000, now=t0)  # 1.0s audio -> ends at 101.0, tail to 101.4
        assert guard.is_playback_or_tail_active(now=t0 + 0.5) is True
        assert guard.is_playback_or_tail_active(now=t0 + 1.0 + SERVER_PLAYBACK_TAIL_SEC - 0.05) is True
        assert guard.is_playback_or_tail_active(now=t0 + 1.0 + SERVER_PLAYBACK_TAIL_SEC + 0.05) is False

    def test_live_bridge_and_http_voice_loopback_no_new_turn_no_device_change(self) -> None:
        reset_session_echo_guards()
        engine = SmartHomeEngine()
        owner_sess = _make_session("tuan_anh", "Nguyễn Tuấn Anh", 1, "ADMIN")
        bridge = _make_bridge(engine, owner_sess)

        # Simulate AI audio playing (1s chunk) + AI spoken phrase
        bridge.echo_guard.note_ai_audio_chunk(48000, sample_rate=24000)
        bridge.echo_guard.record_ai_utterance("Mình đã bật đèn phòng khách rồi ạ.")
        turns_before = bridge.ai_turns_completed
        light_before = engine.devices["living_room_light"]["state"]

        # Feed echoed PCM chunk during playback -> MUST be dropped (queue stays empty)
        asyncio.run(bridge.handle_mic_chunk(b"\x20\x00" * 640, is_sp=True, actor=owner_sess))
        assert bridge._mic_in_flight_queue.qsize() == 0
        assert bridge.ai_turns_completed == turns_before
        assert engine.devices["living_room_light"]["state"] == light_before

        # Real user barge-in with is_barge_in=True -> clears playback & forwards PCM immediately
        with wave.open(str(SAMPLE_USER_WAV), "rb") as wf:
            wav_pcm = wf.readframes(1600)
        asyncio.run(bridge.handle_mic_chunk(wav_pcm, is_sp=True, actor=owner_sess, is_barge_in=True))
        assert bridge._mic_in_flight_queue.qsize() > 0

        # HTTP voice loopback: after AI replies to a command, feeding AI's reply back as transcript does nothing
        resp1, status1 = asyncio.run(
            process_session_voice_command(
                engine=engine,
                session=owner_sess,
                payload={"transcript": "Bật đèn phòng khách"},
            )
        )
        assert status1 == 200 and resp1["ok"] is True
        assert engine.devices["living_room_light"]["state"] == "ON"
        ai_reply = resp1["exact_spoken_reply"]
        assert ai_reply

        # Now feed AI's own spoken reply back into mic path -> suppressed, no execution, silent
        resp_echo, status_echo = asyncio.run(
            process_session_voice_command(
                engine=engine,
                session=owner_sess,
                payload={"transcript": ai_reply},
            )
        )
        assert status_echo == 200
        assert resp_echo.get("echo_suppressed") is True
        assert resp_echo.get("executed") is False
        assert resp_echo.get("should_reply") is False


# =============================================================================
# 2. NATURAL VIETNAMESE SPEECH FILTER & SYSTEM PROMPT
# =============================================================================


class TestNaturalVietnameseSpeechAndPrompt:
    def test_speech_sanitizer_removes_command_syntax_json_and_tokens(self) -> None:
        raw1 = 'open main_door {"device_id": "main_door", "action": "open"} Mình đã mở cửa chính rồi ạ.'
        clean1 = sanitize_spoken_vietnamese_text(raw1)
        assert "open main_door" not in clean1.lower()
        assert "device_id" not in clean1.lower()
        assert "{" not in clean1 and "}" not in clean1
        assert "Mình đã mở cửa chính rồi ạ." in clean1

        raw2 = "control_device(device_id='living_room_light', action='turn_off') Đã tắt đèn phòng khách."
        clean2 = sanitize_spoken_vietnamese_text(raw2)
        assert "control_device" not in clean2
        assert "turn_off" not in clean2
        assert "Đã tắt đèn phòng khách." in clean2

        raw3 = "Trạng thái living_room_light [ON] đã xong."
        clean3 = sanitize_spoken_vietnamese_text(raw3)
        assert "living_room_light" not in clean3
        assert "[" not in clean3 and "]" not in clean3
        assert "đèn phòng khách" in clean3.lower()

    def test_system_prompt_has_no_command_syntax_examples_and_keeps_live_aoede(self) -> None:
        engine = SmartHomeEngine()
        prompt = build_system_instruction(engine)
        assert "open main_door" not in prompt
        assert "device_id" not in prompt
        assert "turn_on" not in prompt
        assert "turn_off" not in prompt
        assert "control_device" not in prompt
        assert "Mình sẽ tắt đèn phòng khách sau 10 phút, bạn đồng ý không?" in prompt
        assert "Vietnamese Prompt Guard" in prompt
        assert "Smart Home Domain Guard" in prompt

        assert MODEL == "gemini-3.8-live"
        cfg = make_live_config(engine)
        assert cfg.speech_config.voice_config.prebuilt_voice_config.voice_name == "Aoede"


# =============================================================================
# 3. AI TOOLS (RBAC, POOLS, PARAMETERS, CONFIRMATION) & REAL USER FLOWS
# =============================================================================


class TestAiToolsRbacPoolsAndRealUserFlows:
    def test_all_required_tools_declared_with_vietnamese_descriptions(self) -> None:
        decls = {fn.name: fn for tg in ALL_TOOLS for fn in (tg.function_declarations or [])}
        required_tools = {
            "list_devices",
            "get_device_state",
            "read_sensors",
            "set_device",
            "create_timer",
            "list_timers",
            "delete_timer",
            "create_schedule",
            "list_schedules",
            "delete_schedule",
        }
        assert required_tools.issubset(set(decls.keys()))
        for name in required_tools:
            desc = str(decls[name].description or "")
            assert len(desc) >= 20, f"Tool {name} missing clear Vietnamese description"

    def test_real_user_flow_timer_10m_confirm_and_cancel_and_sensors(self) -> None:
        reset_session_echo_guards()
        engine = SmartHomeEngine()
        owner_sess = _make_session("tuan_anh", "Nguyễn Tuấn Anh", 1, "ADMIN")
        bridge = _make_bridge(engine, owner_sess)

        # Flow A: "đặt hẹn giờ tắt đèn phòng khách sau 10 phút" -> AI nhắc lại bằng lời thường -> "ok" -> tạo timer
        step1 = asyncio.run(
            bridge.handle_tool_call(
                _fc("create_timer", {"device_id": "living_room_light", "action": "turn_off", "minutes": 10})
            )
        )
        assert step1["ok"] is True
        assert step1["requires_confirmation"] is True
        assert "10 phút" in step1["exact_spoken_reply"]
        assert "đèn phòng khách" in step1["exact_spoken_reply"].lower()
        assert "device_id" not in step1["exact_spoken_reply"]
        # Timer MUST NOT exist yet before confirmation
        before_list = asyncio.run(bridge.handle_tool_call(_fc("list_timers")))
        assert before_list["count"] == 0

        # User confirms "ok" -> timer created
        step2 = asyncio.run(bridge.handle_tool_call(_fc("confirm_or_cancel_pending_action", {"confirmed": True})))
        assert step2["ok"] is True
        assert step2["confirmed"] is True
        after_list = asyncio.run(bridge.handle_tool_call(_fc("list_timers")))
        assert after_list["count"] == 1
        assert after_list["timers"][0]["device_id"] == "living_room_light"
        assert 550 <= after_list["timers"][0]["remaining_seconds"] <= 605

        # Flow B: "nhiệt độ độ ẩm bây giờ bao nhiêu" -> exact sensor numbers (both Live tool and HTTP voice)
        asyncio.run(engine.update_sensor_telemetry(temp_c=24.6, humidity_pct=58.0))
        asyncio.run(engine.update_soil_moisture_telemetry(soil_moisture_pct=47.0))
        sens_tool = asyncio.run(bridge.handle_tool_call(_fc("read_sensors")))
        assert sens_tool["ok"] is True
        assert sens_tool["sensors"]["temperature_c"] == 24.6
        assert sens_tool["sensors"]["humidity_pct"] == 58.0
        assert sens_tool["sensors"]["soil_moisture_pct"] == 47.0

        sens_http, sens_code = asyncio.run(
            process_session_voice_command(
                engine=engine,
                session=owner_sess,
                payload={"transcript": "nhiệt độ độ ẩm bây giờ bao nhiêu"},
            )
        )
        assert sens_code == 200 and sens_http["ok"] is True
        assert "24.6" in sens_http["exact_spoken_reply"]
        assert "58" in sens_http["exact_spoken_reply"]

        # Flow C: Cancel ("không" / "hủy") does nothing
        asyncio.run(engine.execute_device_action("ac", "turn_off", bypass_rbac=True))
        assert engine.devices["ac"]["state"] == "OFF"
        stage_ac = asyncio.run(
            bridge.handle_tool_call(_fc("set_device", {"device_id": "ac", "action": "turn_on", "temperature_c": 22}))
        )
        assert stage_ac["ok"] is True and stage_ac["requires_confirmation"] is True
        assert engine.devices["ac"]["state"] == "OFF"

        cancel_ac = asyncio.run(
            bridge.handle_tool_call(_fc("confirm_or_cancel_pending_action", {"confirmed": False}))
        )
        assert cancel_ac["cancelled"] is True
        assert engine.devices["ac"]["state"] == "OFF"

    def test_set_device_values_and_invalid_params_and_rbac(self) -> None:
        engine = SmartHomeEngine()
        owner_sess = _make_session("tuan_anh", "Nguyễn Tuấn Anh", 1, "ADMIN")
        member_sess = _make_session("thanh_vien_a", "Thành viên A", 2, "MEMBER")
        guest_sess = _make_session("khach_c", "Khách C", 3, "CHILD_GUEST")

        b_owner = _make_bridge(engine, owner_sess)
        b_member = _make_bridge(engine, member_sess)
        b_guest = _make_bridge(engine, guest_sess)

        # list_devices obeys RBAC pool per tier
        devs_t1 = asyncio.run(b_owner.handle_tool_call(_fc("list_devices")))
        devs_t2 = asyncio.run(b_member.handle_tool_call(_fc("list_devices")))
        devs_t3 = asyncio.run(b_guest.handle_tool_call(_fc("list_devices")))
        assert devs_t1["count"] == 7
        assert {d["device_id"] for d in devs_t2["devices"]} == {
            "living_room_light", "bedroom_light", "fan", "ac", "garden_pump"
        }
        assert {d["device_id"] for d in devs_t3["devices"]} == {
            "living_room_light", "bedroom_light", "fan"
        }

        # get_device_state: guest allowed on light, denied on main_door with fixed rejection phrase
        g_ok = asyncio.run(b_guest.handle_tool_call(_fc("get_device_state", {"device_id": "living_room_light"})))
        assert g_ok["ok"] is True and g_ok["device"]["device_id"] == "living_room_light"
        g_deny = asyncio.run(b_guest.handle_tool_call(_fc("get_device_state", {"device_id": "main_door"})))
        assert g_deny["ok"] is False and g_deny.get("rbac_blocked") is True
        assert g_deny["exact_spoken_reply"] == FIXED_REJECTION_PHRASE_VI

        # set_device: Owner sets brightness / AC temp / fan speed (confirmed)
        for args, expected_key, expected_val in [
            ({"device_id": "living_room_light", "action": "turn_on", "brightness_pct": 65}, "brightness_pct", 65),
            ({"device_id": "ac", "action": "turn_on", "temperature_c": 23}, "temperature_c", 23),
            ({"device_id": "fan", "action": "turn_on", "fan_speed": 4}, "fan_speed", 4),
        ]:
            st1 = asyncio.run(b_owner.handle_tool_call(_fc("set_device", args)))
            assert st1["ok"] is True and st1["requires_confirmation"] is True
            st2 = asyncio.run(b_owner.handle_tool_call(_fc("confirm_or_cancel_pending_action", {"confirmed": True})))
            assert st2["ok"] is True and st2["confirmed"] is True
            st_read = asyncio.run(b_owner.handle_tool_call(_fc("get_device_state", {"device_id": args["device_id"]})))
            assert st_read["device"]["state"] == "ON"
            assert st_read["device"]["settings"][expected_key] == expected_val

        # Invalid parameters rejected cleanly
        bad_temp = asyncio.run(b_owner.handle_tool_call(_fc("set_device", {"device_id": "ac", "temperature_c": 45})))
        assert bad_temp["ok"] is False
        bad_param_dev = asyncio.run(
            b_owner.handle_tool_call(_fc("set_device", {"device_id": "living_room_light", "temperature_c": 22}))
        )
        assert bad_param_dev["ok"] is False
        bad_dev = asyncio.run(b_owner.handle_tool_call(_fc("set_device", {"device_id": "unknown_xyz", "action": "turn_on"})))
        assert bad_dev["ok"] is False

        # Out-of-pool RBAC denials (Member -> main_door; Guest -> ac)
        m_deny = asyncio.run(b_member.handle_tool_call(_fc("set_device", {"device_id": "main_door", "action": "open"})))
        assert m_deny["ok"] is False and m_deny.get("rbac_blocked") is True
        assert m_deny["exact_spoken_reply"] == FIXED_REJECTION_PHRASE_VI

        g_deny_ac = asyncio.run(b_guest.handle_tool_call(_fc("set_device", {"device_id": "ac", "action": "turn_on"})))
        assert g_deny_ac["ok"] is False and g_deny_ac.get("rbac_blocked") is True
        assert g_deny_ac["exact_spoken_reply"] == FIXED_REJECTION_PHRASE_VI

        # Guest CAN set_device on allowed light (with confirmation)
        g_stage = asyncio.run(b_guest.handle_tool_call(_fc("set_device", {"device_id": "bedroom_light", "action": "turn_on"})))
        assert g_stage["ok"] is True and g_stage["requires_confirmation"] is True
        g_conf = asyncio.run(b_guest.handle_tool_call(_fc("confirm_or_cancel_pending_action", {"confirmed": True})))
        assert g_conf["ok"] is True and engine.devices["bedroom_light"]["state"] == "ON"

    def test_timers_and_schedules_pool_isolation_and_rbac(self) -> None:
        engine = SmartHomeEngine()
        owner_sess = _make_session("tuan_anh", "Nguyễn Tuấn Anh", 1, "ADMIN")
        member_sess = _make_session("thanh_vien_a", "Thành viên A", 2, "MEMBER")
        guest_sess = _make_session("khach_c", "Khách C", 3, "CHILD_GUEST")

        b_owner = _make_bridge(engine, owner_sess)
        b_member = _make_bridge(engine, member_sess)
        b_guest = _make_bridge(engine, guest_sess)

        # Owner creates a schedule (22:30 daily) + a timer (300s)
        sc1 = asyncio.run(
            b_owner.handle_tool_call(
                _fc("create_schedule", {"device_id": "main_door", "action": "close", "time_hhmm": "22:30", "schedule_type": "daily"})
            )
        )
        assert sc1["ok"] is True and sc1["requires_confirmation"] is True
        sc1_ok = asyncio.run(b_owner.handle_tool_call(_fc("confirm_or_cancel_pending_action", {"confirmed": True})))
        assert sc1_ok["ok"] is True
        owner_sched_id = sc1_ok["schedule"]["schedule_id"]

        tm1 = asyncio.run(
            b_owner.handle_tool_call(_fc("create_timer", {"device_id": "fan", "action": "turn_off", "minutes": 5}))
        )
        assert tm1["ok"] is True and tm1["requires_confirmation"] is True
        tm1_ok = asyncio.run(b_owner.handle_tool_call(_fc("confirm_or_cancel_pending_action", {"confirmed": True})))
        assert tm1_ok["ok"] is True
        owner_timer_id = tm1_ok["timer_id"]

        # Member cannot see or delete Owner's schedule/timer
        m_scheds = asyncio.run(b_member.handle_tool_call(_fc("list_schedules")))
        assert m_scheds["ok"] is True and m_scheds["count"] == 0
        m_del_sched = asyncio.run(b_member.handle_tool_call(_fc("delete_schedule", {"schedule_id": owner_sched_id})))
        assert m_del_sched["ok"] is False and m_del_sched.get("rbac_blocked") is True
        assert m_del_sched["exact_spoken_reply"] == FIXED_REJECTION_PHRASE_VI

        m_timers = asyncio.run(b_member.handle_tool_call(_fc("list_timers")))
        assert m_timers["ok"] is True and m_timers["count"] == 0
        m_del_timer = asyncio.run(b_member.handle_tool_call(_fc("delete_timer", {"timer_id": owner_timer_id})))
        assert m_del_timer["ok"] is False and m_del_timer.get("rbac_blocked") is True

        # Member denied creating schedule on main_door (out of pool) & invalid HH:MM
        m_bad_dev = asyncio.run(
            b_member.handle_tool_call(_fc("create_schedule", {"device_id": "main_door", "action": "open", "time_hhmm": "08:00"}))
        )
        assert m_bad_dev["ok"] is False and m_bad_dev.get("rbac_blocked") is True
        m_bad_time = asyncio.run(
            b_member.handle_tool_call(_fc("create_schedule", {"device_id": "fan", "action": "turn_on", "time_hhmm": "25:99"}))
        )
        assert m_bad_time["ok"] is False

        # Guest denied timers & schedules
        for tool_call in (
            _fc("create_timer", {"device_id": "fan", "action": "turn_off", "minutes": 5}),
            _fc("list_timers"),
            _fc("delete_timer", {"timer_id": owner_timer_id}),
            _fc("create_schedule", {"device_id": "fan", "action": "turn_off", "time_hhmm": "21:00"}),
            _fc("list_schedules"),
            _fc("delete_schedule", {"schedule_id": owner_sched_id}),
        ):
            r = asyncio.run(b_guest.handle_tool_call(tool_call))
            assert r["ok"] is False and r.get("rbac_blocked") is True
            assert r["exact_spoken_reply"] == GUEST_ONLY_TOGGLE_MSG_VI

        # Owner deletes own schedule & timer (with confirmation)
        del_s1 = asyncio.run(b_owner.handle_tool_call(_fc("delete_schedule", {"schedule_id": owner_sched_id})))
        assert del_s1["ok"] is True and del_s1["requires_confirmation"] is True
        del_s2 = asyncio.run(b_owner.handle_tool_call(_fc("confirm_or_cancel_pending_action", {"confirmed": True})))
        assert del_s2["ok"] is True
        assert asyncio.run(b_owner.handle_tool_call(_fc("list_schedules")))["count"] == 0

        del_t1 = asyncio.run(b_owner.handle_tool_call(_fc("delete_timer", {"timer_id": owner_timer_id})))
        assert del_t1["ok"] is True and del_t1["requires_confirmation"] is True
        del_t2 = asyncio.run(b_owner.handle_tool_call(_fc("confirm_or_cancel_pending_action", {"confirmed": True})))
        assert del_t2["ok"] is True
        remaining_ids = [t["timer_id"] for t in asyncio.run(b_owner.handle_tool_call(_fc("list_timers")))["timers"]]
        assert owner_timer_id not in remaining_ids


# =============================================================================
# 4. GUEST QR UI STRUCTURE & CONTROLS
# =============================================================================


class TestGuestQrUiStructure:
    def test_desktop_and_mobile_qr_ui_controls_and_dark_mode(self) -> None:
        index_html = (REPO_ROOT / "simulator" / "static" / "index.html").read_text(encoding="utf-8")
        style_css = (REPO_ROOT / "simulator" / "static" / "css" / "style.css").read_text(encoding="utf-8")
        mobile_html = (REPO_ROOT / "mobile_app" / "index.html").read_text(encoding="utf-8")
        mobile_css = (REPO_ROOT / "simulator" / "static" / "css" / "mobile_app.css").read_text(encoding="utf-8")

        for dom_id in (
            "ownerGuestQrPanel",
            "ownerGuestQrStatusBadge",
            "ownerGuestQrCopyBtn",
            "ownerGuestQrShareBtn",
            "ownerGuestQrRefreshBtn",
            "ownerGuestQrRevokeBtn",
            "ownerGuestCountdownRow",
            "ownerGuestQrSvg",
        ):
            assert f'id="{dom_id}"' in index_html

        for dom_id in (
            "mobileDynamicQrCard",
            "mobileQrStatusBadge",
            "mobileBtnCopyGuestQr",
            "mobileBtnShareGuestQr",
            "mobileBtnRefreshGuestQr",
            "mobileBtnRevokeGuestQr",
            "mobileQrCountdownPill",
        ):
            assert f'id="{dom_id}"' in mobile_html

        assert "prefers-color-scheme: dark" in style_css
        assert "prefers-color-scheme: dark" in mobile_css
