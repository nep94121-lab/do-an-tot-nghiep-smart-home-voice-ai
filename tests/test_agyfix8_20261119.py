"""Regression test suite for agyfix8_20261119 covering all P1 and P2 UX Test findings:
- P1-1: Real Vietnamese 1.0x volume barge-in across 4+ WAVs (JS client & Python server) while blocking pure echo.
- P1-2: autoGainControl: false everywhere + AGC-resilient orthogonal echo suppression during AI warmup & playback.
- P1-3: Server-side + client-side auth protection on /wokwi, /logs, /static/wokwi.html, /static/logs.html.
- P1-4: confirm_or_cancel_pending_action rejects missing/null/non-boolean confirmed parameter (safe default False).
- P2-1 & P2-2: Dark mode WCAG AA contrast (>= 4.5:1) on / login modal and /app QR accordion & inputs.
- P2-3: Mobile touch targets >= 44x44px for password visibility toggle and login links.
- P2-4a: Natural Vietnamese duration humanization (600 -> '10 phút', 90 -> '1 phút 30 giây', 3600 -> '1 giờ', 5400 -> '1 giờ 30 phút').
- P2-4b: Desktop #ownerGuestInviteTier dropdown renders full label without clipping.
"""

from __future__ import annotations

import asyncio
import json
import math
import pathlib
import socket
import struct
import subprocess
import threading
import time
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import uvicorn
from fastapi.testclient import TestClient

from simulator.auth.session_store import UserSession, get_session_store
from simulator.automation_nlu import handle_confirmation_reply, process_automation_nlu_command
from simulator.automation_repo import format_duration_vi
from simulator.live.echo_and_speech_guard import ServerEchoGuard
from simulator.live.gemini_bridge import LiveBridgeSession
from simulator.live.prompt_builder import (
    fn_confirm_factory_reset,
    fn_confirm_or_cancel_pending_action,
    fn_confirm_pending_action,
)
from simulator.rule_engine import SmartHomeEngine
from simulator.server import _ACTIVE_BRIDGES, app

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ECHO_GUARD_JS = REPO_ROOT / "simulator" / "static" / "js" / "voice_echo_guard.js"
WAV_AOEDE_24K = REPO_ROOT / "simulator" / "data" / "aoede_repeat_24k.wav"

TRACKED_HUMAN_WAVS: dict[str, pathlib.Path] = {
    "cau_4_bat_den_phong_khach": REPO_ROOT / "test_audio" / "cac_cau_lenh_cua_sep" / "cau_4_bat_den_phong_khach.wav",
    "cau_1_xin_chao_chu_nha_cap1": REPO_ROOT / "test_audio" / "cac_cau_lenh_cua_sep" / "cau_1_xin_chao_chu_nha_cap1.wav",
    "hen_gio_5s_tat_den": REPO_ROOT / "test_audio" / "hen_gio_5s_tat_den.wav",
    "cau_2_mo_cua_chinh": REPO_ROOT / "test_audio" / "cac_cau_lenh_cua_sep" / "cau_2_mo_cua_chinh.wav",
}
OPTIONAL_UX_WAV = (
    pathlib.Path(r"C:\Users\LENOVO\Desktop\đồ án tốt nghiệp")
    / "test_audio"
    / "giong_tuan_anh_tach_cau"
    / "05_nhiet_do_trong_phong_bay_gio_la_bao_nhieu.wav"
)


def _all_human_wavs() -> dict[str, pathlib.Path]:
    wavs = dict(TRACKED_HUMAN_WAVS)
    if OPTIONAL_UX_WAV.exists():
        wavs["05_nhiet_do_trong_phong"] = OPTIONAL_UX_WAV
    return wavs


def _make_session(user_id: str, display_name: str, tier: int, role: str) -> UserSession:
    now = time.time()
    return UserSession(
        session_id=f"sess_fix8_{user_id}_{int(now * 1000)}",
        user_id=user_id,
        email=f"{user_id}@example.com",
        display_name=display_name,
        tier=tier,
        role=role,
        created_at=now,
        expires_at=now + 3600,
        source="test_agyfix8",
        is_authenticated=True,
    )


def _make_bridge(engine: SmartHomeEngine, session: UserSession) -> LiveBridgeSession:
    mock_ws = AsyncMock()
    mock_ws.headers = {}
    mock_ws.cookies = {}
    mock_ws.query_params = {}
    return LiveBridgeSession(ws=mock_ws, engine=engine, ws_session=session)


def _fc(name: str, args: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=f"fc_{name}", name=name, args={} if args is None else args)


def _load_wav_16k_floats(path: pathlib.Path) -> list[float]:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    samples = [x / 32768.0 for x in struct.unpack(f"<{len(raw) // 2}h", raw)]
    if sr == 24000:
        samples = [samples[int(i * 1.5)] for i in range(int(len(samples) / 1.5))]
    return samples


def _floats_to_pcm16_bytes(samples: list[float]) -> bytes:
    clamped = [max(-32767, min(32767, int(round(s * 32767.0)))) for s in samples]
    return struct.pack(f"<{len(clamped)}h", *clamped)


def _simulate_agc_floats(samples: list[float], target_rms: float = 0.14, max_gain: float = 5.0, step: int = 320) -> list[float]:
    gain = 1.0
    out: list[float] = []
    for i in range(0, len(samples), step):
        chunk = samples[i : i + step]
        if not chunk:
            break
        rms = math.sqrt(sum(x * x for x in chunk) / len(chunk))
        if rms > 0.005:
            desired = min(max_gain, target_rms / rms)
            alpha = 0.28 if desired > gain else 0.18
            gain = gain * (1.0 - alpha) + desired * alpha
        out.extend(max(-1.0, min(1.0, x * gain)) for x in chunk)
    return out


# =============================================================================
# P1-1 & P1-2: ECHO LOOPBACK + REAL 1.0x WAV BARGE-IN (AGC OFF & AGC ON)
# =============================================================================


class TestP1VoiceEchoAndBargeIn:
    def test_all_mic_surfaces_disable_auto_gain_control(self) -> None:
        voice_guard_js = ECHO_GUARD_JS.read_text(encoding="utf-8")
        app_js = (REPO_ROOT / "simulator" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        mobile_js = (REPO_ROOT / "simulator" / "static" / "js" / "mobile_app.js").read_text(encoding="utf-8")
        guest_enroll_js = (REPO_ROOT / "simulator" / "static" / "js" / "guest_enroll.js").read_text(encoding="utf-8")
        android_kt = (
            REPO_ROOT
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
        ).read_text(encoding="utf-8")

        for label, src in (
            ("voice_echo_guard.js", voice_guard_js),
            ("app.js", app_js),
            ("mobile_app.js", mobile_js),
            ("guest_enroll.js", guest_enroll_js),
        ):
            assert "autoGainControl: false" in src, f"{label} must explicitly set autoGainControl: false"
            assert "autoGainControl: true" not in src, f"{label} must not keep autoGainControl: true"
            assert "echoCancellation: true" in src, f"{label} must keep echoCancellation: true"

        assert "AutomaticGainControl.create(sessionId)?.apply { enabled = false }" in android_kt

    def test_client_js_loopback_echo_blocked_and_all_real_wavs_barge_in_agc_on_off(self) -> None:
        assert ECHO_GUARD_JS.exists()
        assert WAV_AOEDE_24K.exists()
        wavs = _all_human_wavs()
        assert len(wavs) >= 4

        node_script = r"""
const fs = require("fs");
const guardMod = require(process.argv[1]);
const aoedePath = process.argv[2];
const wavSpecJson = process.argv[3];
const wavMap = JSON.parse(wavSpecJson);

function readWav16k(filePath) {
  const buf = fs.readFileSync(filePath);
  let off = 12;
  let sr = 16000;
  let dataOff = 44;
  let dataLen = buf.length - 44;
  while (off + 8 <= buf.length) {
    const id = buf.toString("ascii", off, off + 4);
    const sz = buf.readUInt32LE(off + 4);
    if (id === "fmt ") {
      sr = buf.readUInt32LE(off + 12);
    } else if (id === "data") {
      dataOff = off + 8;
      dataLen = Math.min(sz, buf.length - dataOff);
      break;
    }
    off += 8 + sz + (sz % 2);
  }
  const n = Math.floor(dataLen / 2);
  const raw = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    raw[i] = buf.readInt16LE(dataOff + i * 2) / 32768.0;
  }
  if (sr === 24000) {
    const outLen = Math.floor(n / 1.5);
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) out[i] = raw[Math.floor(i * 1.5)];
    return out;
  }
  return raw;
}

function rmsOf(arr) {
  let s = 0;
  for (let i = 0; i < arr.length; i++) s += arr[i] * arr[i];
  return Math.sqrt(s / Math.max(1, arr.length));
}

function simulateAgc(samples, targetRms = 0.14, maxGain = 5.0) {
  const out = new Float32Array(samples.length);
  let gain = 1.0;
  for (let i = 0; i < samples.length; i += 320) {
    const end = Math.min(samples.length, i + 320);
    const sub = samples.subarray(i, end);
    const r = rmsOf(sub);
    if (r > 0.005) {
      const desired = Math.min(maxGain, targetRms / r);
      const alpha = desired > gain ? 0.28 : 0.18;
      gain = gain * (1.0 - alpha) + desired * alpha;
    }
    for (let j = i; j < end; j++) {
      out[j] = Math.max(-1, Math.min(1, samples[j] * gain));
    }
  }
  return out;
}

function makeLoopback(aoede, speech, atten, delayMs, speechOffsetMs, useAgc) {
  const delaySamples = Math.round(delayMs * 16);
  const speechOff = Math.round(speechOffsetMs * 16);
  const total = Math.max(aoede.length * 2, speech ? speechOff + speech.length + 1600 : aoede.length * 2);
  const ref = new Float32Array(total);
  const mic = new Float32Array(total);
  for (let i = 0; i < total; i++) {
    ref[i] = aoede[i % aoede.length];
    const src = i - delaySamples;
    if (src >= 0) mic[i] = aoede[src % aoede.length] * atten;
  }
  if (speech) {
    for (let i = 0; i < speech.length && speechOff + i < total; i++) {
      mic[speechOff + i] = Math.max(-1, Math.min(1, mic[speechOff + i] + speech[i]));
    }
  }
  return { ref, mic: useAgc ? simulateAgc(mic) : mic };
}

const aoede = readWav16k(aoedePath);

// (a) Pure echo loopback (AGC OFF and AGC ON, multiple delays & attenuations)
const pureEchoResults = [];
for (const useAgc of [false, true]) {
  for (const atten of [0.15, 0.22, 0.30]) {
    for (const delayMs of [20, 60, 100]) {
      const { ref, mic } = makeLoopback(aoede, null, atten, delayMs, 0, useAgc);
      let bargeCount = 0;
      let leaked = 0;
      let leakedWarmup = 0;
      const g = guardMod.createVoiceEchoGuard({ onBargeIn: () => { bargeCount += 1; } });
      g.notePlaybackQueued((ref.length / 16000) * 1000, 1000, { samples: ref, sampleRate: 16000 });
      for (let i = 0; i + 320 <= mic.length; i += 320) {
        const now = 1000 + (i / 16);
        const res = g.evaluateMicFrame({ samples: mic.subarray(i, i + 320), sampleRate: 16000, frameDurationMs: 20, nowMs: now });
        if (res.allowSend) {
          leaked += 1;
          if (now - 1000 < 400) leakedWarmup += 1;
        }
      }
      pureEchoResults.push({ useAgc, atten, delayMs, bargeCount, leaked, leakedWarmup });
    }
  }
}

// (b) Echo + 4 real Vietnamese WAVs at ORIGINAL 1.0x volume (AGC OFF and AGC ON)
const bargeResults = {};
for (const [name, p] of Object.entries(wavMap)) {
  const speech = readWav16k(p);
  bargeResults[name] = {};
  for (const useAgc of [false, true]) {
    const { ref, mic } = makeLoopback(aoede, speech, 0.22, 60, 500, useAgc);
    let bargeCount = 0;
    let triggeredAtMs = null;
    let leakedBeforeSpeech = 0;
    const g = guardMod.createVoiceEchoGuard({ onBargeIn: () => { bargeCount += 1; } });
    g.notePlaybackQueued((ref.length / 16000) * 1000, 1000, { samples: ref, sampleRate: 16000 });
    for (let i = 0; i + 320 <= mic.length; i += 320) {
      const now = 1000 + (i / 16);
      const res = g.evaluateMicFrame({ samples: mic.subarray(i, i + 320), sampleRate: 16000, frameDurationMs: 20, nowMs: now });
      if (now < 1500 && res.allowSend) leakedBeforeSpeech += 1;
      if (res.bargeInTriggered && triggeredAtMs === null) {
        triggeredAtMs = Math.round(now - 1500);
      }
    }
    bargeResults[name][useAgc ? "agc_on" : "agc_off"] = {
      bargeCount,
      triggeredAtMs,
      leakedBeforeSpeech,
    };
  }
  // Also test RMS-only fallback mode (no ref samples passed) at 1.0x volume
  let rmsOnlyBarge = 0;
  let rmsOnlyAt = null;
  const gRms = guardMod.createVoiceEchoGuard({ onBargeIn: () => { rmsOnlyBarge += 1; } });
  gRms.notePlaybackQueued(5000, 1000);
  for (let k = 0; k < 10; k++) {
    gRms.evaluateMicFrame({ rms: 0.025, frameDurationMs: 20, nowMs: 1000 + k * 20 });
  }
  for (let i = 0; i + 320 <= speech.length; i += 320) {
    const now = 1200 + (i / 16);
    const res = gRms.evaluateMicFrame({ rms: rmsOf(speech.subarray(i, i + 320)), frameDurationMs: 20, nowMs: now });
    if (res.bargeInTriggered && rmsOnlyAt === null) rmsOnlyAt = Math.round(now - 1200);
  }
  bargeResults[name].rms_only_1x = { bargeCount: rmsOnlyBarge, triggeredAtMs: rmsOnlyAt };
}

console.log(JSON.stringify({ pureEchoResults, bargeResults }));
"""
        wav_spec = json.dumps({k: str(v) for k, v in wavs.items()})
        proc = subprocess.run(
            ["node", "-e", node_script, str(ECHO_GUARD_JS), str(WAV_AOEDE_24K), wav_spec],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert proc.returncode == 0, f"Node loopback test failed: {proc.stderr}\n{proc.stdout}"
        data = json.loads(proc.stdout.strip().splitlines()[-1])

        for item in data["pureEchoResults"]:
            assert item["bargeCount"] == 0, f"Pure echo falsely triggered barge-in: {item}"
            assert item["leaked"] == 0, f"Pure echo leaked mic frames: {item}"
            assert item["leakedWarmup"] == 0, f"Pure echo leaked in warmup window: {item}"

        for name, res in data["bargeResults"].items():
            for mode in ("agc_off", "agc_on"):
                r = res[mode]
                assert r["leakedBeforeSpeech"] == 0, f"{name} ({mode}) leaked echo before user spoke: {r}"
                assert r["bargeCount"] >= 1, f"{name} ({mode}) failed to barge-in at 1.0x volume: {r}"
                assert r["triggeredAtMs"] is not None and 150 <= r["triggeredAtMs"] <= 1600, f"{name} ({mode}) bad trigger latency: {r}"
            assert res["rms_only_1x"]["bargeCount"] >= 1, f"{name} (rms_only_1x) failed to barge-in at 1.0x: {res['rms_only_1x']}"

    def test_server_echo_guard_and_bridge_block_agc_echo_and_allow_human_barge_in(self) -> None:
        aoede = _load_wav_16k_floats(WAV_AOEDE_24K)
        human = _load_wav_16k_floats(TRACKED_HUMAN_WAVS["cau_4_bat_den_phong_khach"])

        # Pure echo with simulated AGC ON -> 0 server barge-ins, 0 frames queued on LiveBridgeSession
        engine = SmartHomeEngine()
        sess = _make_session("fix8_owner", "Owner Fix8", 1, "ADMIN")
        bridge = _make_bridge(engine, sess)
        delay = 960  # 60ms @ 16kHz
        total = len(aoede)
        echo_only = [0.0] * total
        for i in range(delay, total):
            echo_only[i] = aoede[i - delay] * 0.22
        echo_agc = _simulate_agc_floats(echo_only)

        t0 = 100.0
        bridge.echo_guard.note_ai_audio_chunk(
            len(_floats_to_pcm16_bytes(aoede)),
            sample_rate=16000,
            pcm_bytes=_floats_to_pcm16_bytes(aoede),
            now=t0,
        )
        light_before = engine.devices["living_room_light"]["state"]
        turns_before = bridge.ai_turns_completed
        for idx in range(0, len(echo_agc) - 320, 320):
            chunk = _floats_to_pcm16_bytes(echo_agc[idx : idx + 320])
            allow, barged, _ = bridge.echo_guard.evaluate_mic_audio_chunk(
                chunk,
                is_barge_in_hint=False,
                sample_rate=16000,
                now=t0 + (idx + 320) / 16000.0,
            )
            assert allow is False and barged is False, f"Server leaked AGC echo at idx={idx}"
        assert bridge._mic_in_flight_queue.qsize() == 0
        assert bridge.ai_turns_completed == turns_before
        assert engine.devices["living_room_light"]["state"] == light_before

        # Echo + real Vietnamese speech -> server barge-in triggers cleanly
        guard = ServerEchoGuard()
        mix_len = max(len(aoede), 8000 + len(human) + 1600)
        ref_long = [aoede[i % len(aoede)] for i in range(mix_len)]
        mic_mix = [0.0] * mix_len
        for i in range(delay, mix_len):
            mic_mix[i] = ref_long[i - delay] * 0.22
        for i, v in enumerate(human):
            mic_mix[8000 + i] = max(-1.0, min(1.0, mic_mix[8000 + i] + v))

        guard.note_ai_audio_chunk(
            len(_floats_to_pcm16_bytes(ref_long)),
            sample_rate=16000,
            pcm_bytes=_floats_to_pcm16_bytes(ref_long),
            now=t0,
        )
        barged_at = None
        for idx in range(0, mix_len - 320, 320):
            chunk = _floats_to_pcm16_bytes(mic_mix[idx : idx + 320])
            now_s = t0 + (idx + 320) / 16000.0
            allow, barged, _ = guard.evaluate_mic_audio_chunk(chunk, sample_rate=16000, now=now_s)
            if now_s < t0 + 0.50:
                assert allow is False, f"Server leaked pre-speech echo at {now_s - t0:.3f}s"
            if barged and barged_at is None:
                barged_at = now_s - (t0 + 0.50)
                break
        assert barged_at is not None and 0.15 <= barged_at <= 1.2, f"Server barge-in failed: {barged_at}"


# =============================================================================
# P1-3: /wokwi, /logs AND STATIC HTML AUTH ENFORCEMENT
# =============================================================================


class TestP1WokwiAndProtectedRoutesAuth:
    def test_unauthenticated_protected_html_routes_redirect_without_hardware_leak(self) -> None:
        client = TestClient(app)
        protected_routes = (
            "/wokwi",
            "/logs",
            "/static/wokwi.html",
            "/static/logs.html",
            "/guest_legacy_removed",
        )
        for route in protected_routes:
            resp = client.get(route, follow_redirects=False)
            assert resp.status_code in (302, 303, 307, 401, 403), f"{route} must reject unauth, got {resp.status_code}"
            if resp.status_code in (302, 303, 307):
                assert "/login" in (resp.headers.get("location") or "")
            body = resp.text
            assert "Mạch mô phỏng" not in body, f"{route} leaked hardware title when unauthenticated"
            assert "ESP8266MOD" not in body, f"{route} leaked ESP8266 circuit when unauthenticated"
            assert "Xem nhật ký" not in body, f"{route} leaked /logs shortcut when unauthenticated"

    def test_authenticated_tier_access_for_wokwi_and_logs(self) -> None:
        client = TestClient(app)
        store = get_session_store()
        s_owner = store.create_session(
            user_id="fix8_t1",
            email="fix8_t1@example.com",
            display_name="Owner Test",
            tier=1,
            role="ADMIN",
            source="test_agyfix8",
        )
        s_family = store.create_session(
            user_id="fix8_t2",
            email="fix8_t2@example.com",
            display_name="Family Test",
            tier=2,
            role="FAMILY",
            source="test_agyfix8",
        )
        s_guest = store.create_session(
            user_id="fix8_t3",
            email="fix8_t3@example.com",
            display_name="Guest Test",
            tier=3,
            role="GUEST",
            source="test_agyfix8",
        )
        try:
            # Owner (Tier 1) -> 200 on both /wokwi and /logs
            r_w1 = client.get("/wokwi", headers={"X-Session-Token": s_owner.session_id}, follow_redirects=False)
            r_l1 = client.get("/logs", headers={"X-Session-Token": s_owner.session_id}, follow_redirects=False)
            assert r_w1.status_code == 200 and "Mạch mô phỏng" in r_w1.text
            assert 'id="wokwiLogsShortcut"' in r_w1.text and 'data-owner-only="true"' in r_w1.text
            assert r_l1.status_code == 200 and "auditLogsTbody" in r_l1.text

            # Family (Tier 2) -> 200 on /wokwi, 403 on /logs
            r_w2 = client.get("/wokwi", headers={"X-Session-Token": s_family.session_id}, follow_redirects=False)
            r_l2 = client.get("/logs", headers={"X-Session-Token": s_family.session_id}, follow_redirects=False)
            assert r_w2.status_code == 200
            assert r_l2.status_code == 403

            # Guest (Tier 3) -> 403 on both /wokwi and /logs
            r_w3 = client.get("/wokwi", headers={"X-Session-Token": s_guest.session_id}, follow_redirects=False)
            r_l3 = client.get("/logs", headers={"X-Session-Token": s_guest.session_id}, follow_redirects=False)
            assert r_w3.status_code == 403
            assert r_l3.status_code == 403
        finally:
            store.revoke_session(s_owner.session_id)
            store.revoke_session(s_family.session_id)
            store.revoke_session(s_guest.session_id)


# =============================================================================
# P1-4: STRICT CONFIRMATION BOOLEAN GUARD
# =============================================================================


class TestP1ConfirmToolSafeDefault:
    def test_confirmation_tool_schemas_require_boolean_confirmed(self) -> None:
        for decl in (fn_confirm_or_cancel_pending_action, fn_confirm_pending_action, fn_confirm_factory_reset):
            params = decl.parameters
            req = getattr(params, "required", None) or (params.get("required") if isinstance(params, dict) else [])
            props = getattr(params, "properties", None) or (params.get("properties") if isinstance(params, dict) else {})
            assert "confirmed" in (req or []), f"{decl.name} must require confirmed"
            conf_schema = props["confirmed"]
            ctype = str(getattr(conf_schema, "type", None) or (conf_schema.get("type") if isinstance(conf_schema, dict) else "")).upper()
            assert "BOOL" in ctype, f"{decl.name}.confirmed must be BOOLEAN, got {ctype}"

    @pytest.mark.parametrize(
        "bad_args",
        [
            {},
            {"confirmed": None},
            {"confirmed": False},
            {"confirmed": "false"},
            {"confirmed": "true"},
            {"confirmed": "ok"},
            {"confirmed": "chuoi_la"},
            {"confirmed": 1},
            {"confirmed": 0},
            {"confirm": True},
        ],
    )
    def test_missing_or_invalid_confirmed_never_executes_pending_door_open(self, bad_args: dict) -> None:
        engine = SmartHomeEngine()
        engine.devices["main_door"]["state"] = "CLOSED"
        owner = _make_session("fix8_conf_owner", "Owner Conf", 1, "ADMIN")
        bridge = _make_bridge(engine, owner)

        step1 = asyncio.run(bridge.handle_tool_call(_fc("set_device", {"device_id": "main_door", "action": "open"})))
        assert step1.get("requires_confirmation") is True
        assert engine.devices["main_door"]["state"] == "CLOSED"

        step2 = asyncio.run(bridge.handle_tool_call(_fc("confirm_or_cancel_pending_action", bad_args)))
        assert engine.devices["main_door"]["state"] == "CLOSED", (
            f"Pending main_door open executed with unsafe args={bad_args}: {step2}"
        )

    def test_explicit_boolean_true_executes_pending_action(self) -> None:
        engine = SmartHomeEngine()
        engine.devices["main_door"]["state"] = "CLOSED"
        owner = _make_session("fix8_conf_ok", "Owner Ok", 1, "ADMIN")
        bridge = _make_bridge(engine, owner)

        step1 = asyncio.run(bridge.handle_tool_call(_fc("set_device", {"device_id": "main_door", "action": "open"})))
        assert step1.get("requires_confirmation") is True
        step2 = asyncio.run(bridge.handle_tool_call(_fc("confirm_or_cancel_pending_action", {"confirmed": True})))
        assert step2.get("ok") is True
        assert engine.devices["main_door"]["state"] == "OPEN"
        engine.devices["main_door"]["state"] = "CLOSED"

    def test_engine_confirm_pending_action_default_is_false(self) -> None:
        engine = SmartHomeEngine()
        engine.pending_reset_confirmation = True
        res = asyncio.run(engine.confirm_pending_action())
        assert res.get("status") == "CANCELLED"
        assert engine.pending_reset_confirmation is False


# =============================================================================
# P2-4a: NATURAL VIETNAMESE DURATION HUMANIZATION
# =============================================================================


class TestP2VietnameseDurationHumanization:
    @pytest.mark.parametrize(
        "seconds, expected",
        [
            (0, "0 giây"),
            (5, "5 giây"),
            (45, "45 giây"),
            (60, "1 phút"),
            (90, "1 phút 30 giây"),
            (600, "10 phút"),
            (3600, "1 giờ"),
            (5400, "1 giờ 30 phút"),
            (3665, "1 giờ 1 phút 5 giây"),
        ],
    )
    def test_format_duration_vi_cases(self, seconds: float, expected: str) -> None:
        assert format_duration_vi(seconds) == expected

    def test_nlu_timer_prompt_and_listing_humanize_10_minutes(self) -> None:
        engine = SmartHomeEngine()
        owner = _make_session("fix8_dur_owner", "Owner Dur", 1, "ADMIN")

        res1 = asyncio.run(
            process_automation_nlu_command(
                text="đặt hẹn giờ tắt đèn phòng khách sau 10 phút",
                engine=engine,
                session=owner,
                source="test_agyfix8",
            )
        )
        assert res1 is not None
        p1 = res1.get("payload") if isinstance(res1.get("payload"), dict) else res1
        assert p1.get("requires_confirmation") is True
        spoken = str(p1.get("exact_spoken_reply") or p1.get("reply") or "")
        assert "10 phút" in spoken, f"Expected '10 phút' in confirmation prompt, got: {spoken}"
        assert "600 giây" not in spoken, f"Must not say '600 giây', got: {spoken}"

        res2 = asyncio.run(
            handle_confirmation_reply(
                raw_text="ok",
                engine=engine,
                session=owner,
                source="test_agyfix8",
            )
        )
        assert res2 is not None
        p2 = res2.get("payload") if isinstance(res2.get("payload"), dict) else res2
        assert p2.get("ok") is True

        res_list = asyncio.run(
            process_automation_nlu_command(
                text="tôi có những hẹn giờ nào",
                engine=engine,
                session=owner,
                source="test_agyfix8",
            )
        )
        assert res_list is not None
        p_list = res_list.get("payload") if isinstance(res_list.get("payload"), dict) else res_list
        list_spoken = str(p_list.get("exact_spoken_reply") or p_list.get("reply") or "")
        assert "phút" in list_spoken, f"Expected humanized minutes in timer listing, got: {list_spoken}"
        assert "600 giây" not in list_spoken and "599 giây" not in list_spoken


# =============================================================================
# P2-1, P2-2, P2-3, P2-4b: DARK MODE WCAG AA, MOBILE >=44PX, DESKTOP SELECT
# =============================================================================


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _launch_headless_chromium(p):
    import os

    args = ["--disable-dev-shm-usage", "--no-sandbox"]
    attempts: list[dict] = []
    env_exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "").strip()
    if env_exe and pathlib.Path(env_exe).exists():
        attempts.append({"executable_path": env_exe})
    home = pathlib.Path.home()
    for base in (home, home.parent, pathlib.Path(r"C:\Users\LENOVO")):
        pup_root = base / ".cache" / "puppeteer"
        if pup_root.exists():
            for pat in ("chrome-headless-shell.exe", "chrome.exe"):
                for exe in sorted(pup_root.rglob(pat), reverse=True):
                    if exe.exists():
                        attempts.append({"executable_path": str(exe)})
                        break
    attempts.extend([{"channel": "msedge"}, {"channel": "chrome"}, {}])
    last_err = None
    for kw in attempts:
        try:
            return p.chromium.launch(headless=True, args=args, **kw)
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"Could not launch headless Chromium: {last_err}")


def _wcag_contrast_js() -> str:
    return """(el) => {
        function parseRgb(str) {
            const m = String(str || '').match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\\)/);
            if (!m) return null;
            return { r: Number(m[1]), g: Number(m[2]), b: Number(m[3]), a: m[4] === undefined ? 1 : Number(m[4]) };
        }
        function effectiveBg(node) {
            let cur = node;
            while (cur && cur.nodeType === 1) {
                const c = parseRgb(getComputedStyle(cur).backgroundColor);
                if (c && c.a > 0.05) return c;
                cur = cur.parentElement;
            }
            return { r: 255, g: 255, b: 255, a: 1 };
        }
        function relLum(c) {
            const f = (v) => {
                const s = v / 255;
                return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
            };
            return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
        }
        const fg = parseRgb(getComputedStyle(el).color);
        const bg = effectiveBg(el);
        const l1 = Math.max(relLum(fg), relLum(bg));
        const l2 = Math.min(relLum(fg), relLum(bg));
        return {
            fg: getComputedStyle(el).color,
            bg: `rgb(${bg.r}, ${bg.g}, ${bg.b})`,
            ratio: Number(((l1 + 0.05) / (l2 + 0.05)).toFixed(2)),
        };
    }"""


class TestP2UiContrastTouchTargetsAndSelect:
    def test_dark_mode_contrast_mobile_touch_targets_and_desktop_select_browser(self) -> None:
        from playwright.sync_api import sync_playwright

        port = _get_free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{port}"

        import urllib.request

        for _ in range(80):
            try:
                with urllib.request.urlopen(f"{base_url}/api/health", timeout=0.5) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.1)

        store = get_session_store()
        owner_sess = store.create_session(
            user_id="fix8_ui_owner",
            email="fix8_ui_owner@example.com",
            display_name="Owner UI",
            tier=1,
            role="ADMIN",
            source="test_agyfix8_ui",
        )
        try:
            with sync_playwright() as p:
                browser = _launch_headless_chromium(p)
                try:
                    # 1. Mobile 412x915 Dark Mode Unauth: / and /app contrast & >= 44px touch targets
                    ctx_m = browser.new_context(
                        viewport={"width": 412, "height": 915},
                        is_mobile=True,
                        has_touch=True,
                        color_scheme="dark",
                    )
                    pg = ctx_m.new_page()
                    pg.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
                    pg.route("https://fonts.gstatic.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))

                    pg.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=15000)
                    pg.wait_for_selector("#homeLoginGateModal h3", state="visible", timeout=10000)
                    home_title_c = pg.locator("#homeLoginGateModal h3").evaluate(_wcag_contrast_js())
                    assert home_title_c["ratio"] >= 4.5, f"Dark mode / login title contrast too low: {home_title_c}"

                    pw_btn_home = pg.locator("#homeLoginGateModal .btn-toggle-pw").first.bounding_box()
                    assert pw_btn_home and pw_btn_home["width"] >= 44 and pw_btn_home["height"] >= 44, (
                        f"Home .btn-toggle-pw < 44x44: {pw_btn_home}"
                    )
                    forgot_home = pg.locator("#linkGateForgot").bounding_box()
                    assert forgot_home and forgot_home["height"] >= 44, f"Home forgot link height < 44: {forgot_home}"

                    # /app unauth dark mode + touch targets
                    pg.goto(f"{base_url}/app", wait_until="domcontentloaded", timeout=15000)
                    pg.wait_for_selector("#mobileLoginEmail", state="visible", timeout=10000)
                    app_input_c = pg.locator("#mobileLoginEmail").evaluate(_wcag_contrast_js())
                    assert app_input_c["ratio"] >= 4.5, f"Dark mode /app input contrast too low: {app_input_c}"
                    assert app_input_c["bg"] != "rgb(255, 255, 255)", f"Dark mode /app input stayed white: {app_input_c}"

                    pw_btn_app = pg.locator("#mobileLoginForm .btn-toggle-pw").first.bounding_box()
                    assert pw_btn_app and pw_btn_app["width"] >= 44 and pw_btn_app["height"] >= 44, (
                        f"App .btn-toggle-pw < 44x44: {pw_btn_app}"
                    )
                    forgot_app = pg.locator("#btnMobileForgotPassword").bounding_box()
                    assert forgot_app and forgot_app["height"] >= 44, f"App forgot button height < 44: {forgot_app}"

                    # /app authenticated dark mode: "Mời khách bằng mã QR" summary contrast >= 4.5:1
                    ctx_m.add_cookies([
                        {"name": "sh_session_token", "value": owner_sess.session_id, "url": base_url, "httpOnly": True, "sameSite": "Lax"}
                    ])
                    pg.goto(f"{base_url}/app", wait_until="domcontentloaded", timeout=15000)
                    pg.wait_for_selector("#mobileBottomNav:not([hidden])", timeout=10000)
                    pg.click('button[data-tab="account"]')
                    pg.wait_for_selector("#mobileDynamicQrCard > summary", state="visible", timeout=10000)
                    qr_sum_c = pg.locator("#mobileDynamicQrCard > summary").evaluate(_wcag_contrast_js())
                    assert qr_sum_c["ratio"] >= 4.5, f"Dark mode /app QR summary contrast too low: {qr_sum_c}"
                    ctx_m.close()

                    # 2. Desktop 1366x768 Authenticated: #ownerGuestInviteTier select not truncated
                    ctx_d = browser.new_context(viewport={"width": 1366, "height": 768})
                    ctx_d.add_cookies([
                        {"name": "sh_session_token", "value": owner_sess.session_id, "url": base_url, "httpOnly": True, "sameSite": "Lax"}
                    ])
                    pg_d = ctx_d.new_page()
                    pg_d.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
                    pg_d.route("https://fonts.gstatic.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
                    pg_d.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=15000)
                    pg_d.wait_for_selector("#ownerGuestInviteTier", state="visible", timeout=10000)
                    select_metrics = pg_d.locator("#ownerGuestInviteTier").evaluate("""(el) => {
                        const rect = el.getBoundingClientRect();
                        const style = getComputedStyle(el);
                        const canvas = document.createElement('canvas');
                        const ctx = canvas.getContext('2d');
                        ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
                        const selectedText = el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : '';
                        const textWidth = ctx.measureText(selectedText).width;
                        const padLeft = parseFloat(style.paddingLeft) || 0;
                        const padRight = parseFloat(style.paddingRight) || 0;
                        const available = rect.width - padLeft - padRight;
                        return {
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                            selectedText,
                            textWidth: Math.round(textWidth),
                            available: Math.round(available),
                            fits: textWidth <= available,
                        };
                    }""")
                    assert select_metrics["width"] >= 230, f"Desktop tier select too narrow: {select_metrics}"
                    assert select_metrics["height"] >= 40, f"Desktop tier select too short: {select_metrics}"
                    assert select_metrics["fits"] is True, f"Desktop tier select truncates text: {select_metrics}"
                    ctx_d.close()
                finally:
                    browser.close()
        finally:
            store.revoke_session(owner_sess.session_id)
            server.should_exit = True
            thread.join(timeout=3)
            for br in list(_ACTIVE_BRIDGES):
                try:
                    br._closed = True
                except Exception:
                    pass
            _ACTIVE_BRIDGES.clear()
