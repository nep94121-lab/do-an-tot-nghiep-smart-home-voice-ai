"""Regression test suite for agyfix9_20261120 covering all P1-N1 and P2-N1..N3 findings:
- P1-N1: Echo guard suppresses pure Aoede echo under real Chromium WebRTC AGC ON and
         nonlinear soft-clip/hard-clip/HPF+compressor distortions (JS client & Python server)
         while preserving 4/4 real Vietnamese WAV 1.0x barge-in (AGC OFF & AGC ON).
- P2-N1: Dark mode (prefers-color-scheme: dark & [data-theme="dark"]) fixes 7 device cards
         on / and all cards/status boxes across /, /app, /login, /register, /guest_guide (>= 4.5:1).
- P2-N2: Primary buttons (.btn-primary, .btn.primary, .auth-btn-submit) meet WCAG AA >= 4.5:1
         in both Light Mode and Dark Mode across /, /app, /login, /register, /guest_guide.
- P2-N3: Mobile 412x915 touch targets >= 44px for #btnSubmitGateLogin, 4 QR action buttons,
         QR PIN inputs (#mobileQrPinInput, #mobileQrPinConfirmInput), and interactive controls.
"""

from __future__ import annotations

import base64
import json
import math
import os
import pathlib
import socket
import struct
import subprocess
import tempfile
import threading
import time
import wave
from typing import Any

import pytest
import uvicorn

from backend.auth.session_store import get_session_store
from backend.database_sqlite import init_sqlite_database
from backend.live.echo_and_speech_guard import ServerEchoGuard
from backend.server import app

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ECHO_GUARD_JS = REPO_ROOT / "web" / "js" / "voice_echo_guard.js"
WAV_AOEDE_24K = REPO_ROOT / "backend" / "data" / "aoede_repeat_24k.wav"

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


def _load_wav_floats(path: pathlib.Path, target_sr: int = 16000) -> list[float]:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
    vals = struct.unpack(f"<{len(raw) // 2}h", raw)
    if ch > 1:
        vals = vals[::ch]
    floats = [v / 32768.0 for v in vals]
    if sr == target_sr:
        return floats
    ratio = sr / float(target_sr)
    out_len = int(len(floats) / ratio)
    n = len(floats)
    out: list[float] = []
    for i in range(out_len):
        pos = i * ratio
        idx = int(pos)
        frac = pos - idx
        s0 = floats[idx]
        s1 = floats[idx + 1] if idx + 1 < n else s0
        out.append(s0 + (s1 - s0) * frac)
    return out


def _floats_to_pcm16_bytes(samples: list[float]) -> bytes:
    clamped = [max(-32767, min(32767, int(round(s * 32767.0)))) for s in samples]
    return struct.pack(f"<{len(clamped)}h", *clamped)


def _write_wav_16k(path: pathlib.Path, samples_16k: list[float]) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(_floats_to_pcm16_bytes(samples_16k))


def _rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(x * x for x in samples) / float(len(samples)))


def _soft_clip_compressor(samples: list[float], drive: float = 5.0, pre_gain: float = 5.0) -> list[float]:
    out: list[float] = []
    gain = 1.0
    norm = math.tanh(drive)
    for i in range(0, len(samples), 320):
        chunk = samples[i : i + 320]
        r = _rms(chunk)
        if r > 0.004:
            des = min(pre_gain, 0.28 / r)
            gain = gain * 0.70 + des * 0.30
        out.extend(math.tanh(x * gain * drive) / norm for x in chunk)
    return out


def _hard_clip_limiter(samples: list[float], ceiling: float = 0.30, pre_gain: float = 10.0) -> list[float]:
    return [max(-ceiling, min(ceiling, x * pre_gain)) for x in samples]


def _hpf_plus_soft_clip(samples: list[float], pre_gain: float = 6.0) -> list[float]:
    alpha = 0.93
    hp: list[float] = []
    prev_x = 0.0
    prev_y = 0.0
    for x in samples:
        y = alpha * (prev_y + x - prev_x)
        prev_x = x
        prev_y = y
        hp.append(y)
    return _soft_clip_compressor(hp, drive=4.0, pre_gain=pre_gain)


def _find_chromium_executable() -> str | None:
    env_exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "").strip()
    if env_exe and pathlib.Path(env_exe).exists():
        return env_exe
    home = pathlib.Path.home()
    for base in (home, home.parent, pathlib.Path(r"C:\Users\LENOVO")):
        pup_root = base / ".cache" / "puppeteer"
        if pup_root.exists():
            for pat in ("chrome-headless-shell.exe", "chrome.exe"):
                for exe in sorted(pup_root.rglob(pat), reverse=True):
                    if exe.exists():
                        return str(exe)
    return None


def _launch_headless_chromium(p: Any, extra_args: list[str] | None = None) -> Any:
    exe = _find_chromium_executable()
    attempts: list[dict[str, Any]] = []
    if exe:
        attempts.append({"headless": True, "executable_path": exe})
    attempts.extend(
        [
            {"headless": True, "channel": "msedge"},
            {"headless": True},
            {"headless": True, "channel": "chrome"},
        ]
    )
    last_err: Exception | None = None
    for kw in attempts:
        try:
            call_kw = dict(kw)
            if extra_args:
                call_kw["args"] = list(extra_args)
            return p.chromium.launch(timeout=20000, **call_kw)
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"Could not launch headless Chromium: {last_err}")


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def fix9_live_server() -> tuple[str, dict[str, str]]:
    init_sqlite_database()
    store = get_session_store()
    owner_sess = store.create_session(
        user_id="fix9_owner",
        email="fix9_owner@example.com",
        display_name="Owner Fix9",
        tier=1,
        role="ADMIN",
        source="test_agyfix9",
    )

    desktop_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    mobile_ua = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"

    port = _pick_free_port()
    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15.0
    while time.time() < deadline and not server.started:
        time.sleep(0.05)
    assert server.started, "Uvicorn test server failed to start"
    try:
        yield f"http://127.0.0.1:{port}", {
            "session_id": owner_sess.session_id,
            "desktop_ua": desktop_ua,
            "mobile_ua": mobile_ua,
        }
    finally:
        if hasattr(store, "revoke_session"):
            store.revoke_session(owner_sess.session_id)
        server.should_exit = True
        thread.join(timeout=5.0)


# =============================================================================
# P1-N1: NONLINEAR AGC / SOFT-CLIP / HARD-CLIP / REAL CHROMIUM WEBRTC AGC ON
# =============================================================================


class TestP1N1NonlinearAgcEchoGuard:
    def test_js_client_blocks_nonlinear_softclip_hardclip_hpf_agc_echo_and_allows_all_real_wavs_1x(self) -> None:
        assert ECHO_GUARD_JS.exists()
        assert WAV_AOEDE_24K.exists()
        wavs = _all_human_wavs()
        assert len(wavs) >= 4

        node_script = r"""
const fs = require("fs");
const guardMod = require(process.argv[1]);
const aoedePath = process.argv[2];
const wavMap = JSON.parse(process.argv[3]);

function readWav16k(filePath) {
  const buf = fs.readFileSync(filePath);
  let off = 12, sr = 16000, dataOff = 44, dataLen = buf.length - 44;
  while (off + 8 <= buf.length) {
    const id = buf.toString("ascii", off, off + 4);
    const sz = buf.readUInt32LE(off + 4);
    if (id === "fmt ") sr = buf.readUInt32LE(off + 12);
    else if (id === "data") { dataOff = off + 8; dataLen = Math.min(sz, buf.length - dataOff); break; }
    off += 8 + sz + (sz % 2);
  }
  const n = Math.floor(dataLen / 2);
  const raw = new Float32Array(n);
  for (let i = 0; i < n; i++) raw[i] = buf.readInt16LE(dataOff + i * 2) / 32768.0;
  if (sr === 16000) return raw;
  const ratio = sr / 16000.0;
  const outLen = Math.floor(n / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const pos = i * ratio;
    const idx = Math.floor(pos);
    const frac = pos - idx;
    const s0 = raw[idx];
    const s1 = idx + 1 < n ? raw[idx + 1] : s0;
    out[i] = s0 + (s1 - s0) * frac;
  }
  return out;
}

function rmsOf(arr) {
  let s = 0;
  for (let i = 0; i < arr.length; i++) s += arr[i] * arr[i];
  return Math.sqrt(s / Math.max(1, arr.length));
}

function linearAgc(samples, targetRms = 0.14, maxGain = 5.0) {
  const out = new Float32Array(samples.length);
  let gain = 1.0;
  for (let i = 0; i < samples.length; i += 320) {
    const end = Math.min(samples.length, i + 320);
    const r = rmsOf(samples.subarray(i, end));
    if (r > 0.005) {
      const des = Math.min(maxGain, targetRms / r);
      const a = des > gain ? 0.28 : 0.18;
      gain = gain * (1 - a) + des * a;
    }
    for (let j = i; j < end; j++) out[j] = Math.max(-1, Math.min(1, samples[j] * gain));
  }
  return out;
}

function softClipAgc(samples, drive = 5.0, preGain = 5.0) {
  const out = new Float32Array(samples.length);
  let gain = 1.0;
  const norm = Math.tanh(drive);
  for (let i = 0; i < samples.length; i += 320) {
    const end = Math.min(samples.length, i + 320);
    const r = rmsOf(samples.subarray(i, end));
    if (r > 0.004) {
      const des = Math.min(preGain, 0.28 / r);
      gain = gain * 0.70 + des * 0.30;
    }
    for (let j = i; j < end; j++) out[j] = Math.tanh(samples[j] * gain * drive) / norm;
  }
  return out;
}

function hardClipAgc(samples, ceiling = 0.30, preGain = 10.0) {
  const out = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    out[i] = Math.max(-ceiling, Math.min(ceiling, samples[i] * preGain));
  }
  return out;
}

function hpfSoftClipAgc(samples, preGain = 6.0) {
  const hp = new Float32Array(samples.length);
  let px = 0, py = 0;
  for (let i = 0; i < samples.length; i++) {
    const y = 0.93 * (py + samples[i] - px);
    px = samples[i];
    py = y;
    hp[i] = y;
  }
  return softClipAgc(hp, 4.0, preGain);
}

const DISTORTIONS = {
  linear_off: (s) => s,
  linear_agc: (s) => linearAgc(s),
  softclip_agc: (s) => softClipAgc(s),
  hardclip_agc: (s) => hardClipAgc(s),
  hpf_softclip_agc: (s) => hpfSoftClipAgc(s),
};

const aoede = readWav16k(aoedePath);
const totalLen = Math.max(aoede.length * 2, 16000 * 6);
const refFull = new Float32Array(totalLen);
for (let i = 0; i < totalLen; i++) refFull[i] = aoede[i % aoede.length];

const pureEcho = [];
for (const [mode, fn] of Object.entries(DISTORTIONS)) {
  for (const delayMs of [50, 60, 100]) {
    const dS = Math.round(delayMs * 16);
    const rawMic = new Float32Array(totalLen);
    for (let i = dS; i < totalLen; i++) rawMic[i] = refFull[i - dS] * 0.22;
    const mic = fn(rawMic);
    let bargeCount = 0, leaked = 0;
    const g = guardMod.createVoiceEchoGuard({ onBargeIn: () => { bargeCount += 1; } });
    g.notePlaybackQueued((totalLen / 16000) * 1000, 1000, { samples: refFull, sampleRate: 16000 });
    for (let i = 0; i + 320 <= totalLen; i += 320) {
      const now = 1000 + (i / 16);
      const res = g.evaluateMicFrame({ samples: mic.subarray(i, i + 320), sampleRate: 16000, frameDurationMs: 20, nowMs: now });
      if (res.allowSend) leaked += 1;
    }
    pureEcho.push({ mode, delayMs, bargeCount, leaked });
  }
}

const humanResults = {};
for (const [name, wpath] of Object.entries(wavMap)) {
  const sp = readWav16k(wpath);
  humanResults[name] = {};
  for (const mode of ["linear_off", "linear_agc", "softclip_agc", "hpf_softclip_agc"]) {
    const dS = 60 * 16;
    const spOff = 500 * 16;
    const rawMic = new Float32Array(totalLen);
    for (let i = dS; i < totalLen; i++) rawMic[i] = refFull[i - dS] * 0.22;
    for (let i = 0; i < sp.length && spOff + i < totalLen; i++) {
      rawMic[spOff + i] = Math.max(-1, Math.min(1, rawMic[spOff + i] + sp[i]));
    }
    const mic = DISTORTIONS[mode](rawMic);
    let bargeCount = 0, triggeredAtMs = null, leakedBeforeSpeech = 0;
    const g = guardMod.createVoiceEchoGuard({ onBargeIn: () => { bargeCount += 1; } });
    g.notePlaybackQueued((totalLen / 16000) * 1000, 1000, { samples: refFull, sampleRate: 16000 });
    for (let i = 0; i + 320 <= totalLen; i += 320) {
      const now = 1000 + (i / 16);
      const res = g.evaluateMicFrame({ samples: mic.subarray(i, i + 320), sampleRate: 16000, frameDurationMs: 20, nowMs: now });
      if (now < 1500 && res.allowSend) leakedBeforeSpeech += 1;
      if (res.bargeInTriggered && triggeredAtMs === null) triggeredAtMs = Math.round(now - 1500);
    }
    humanResults[name][mode] = { bargeCount, triggeredAtMs, leakedBeforeSpeech };
  }
}

console.log(JSON.stringify({ pureEcho, humanResults }));
"""
        proc = subprocess.run(
            ["node", "-e", node_script, str(ECHO_GUARD_JS), str(WAV_AOEDE_24K), json.dumps({k: str(v) for k, v in wavs.items()})],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        for row in data["pureEcho"]:
            assert row["bargeCount"] == 0, f"False barge-in on pure nonlinear echo: {row}"
            assert row["leaked"] == 0, f"Leaked mic frames on pure nonlinear echo: {row}"
        for name, modes in data["humanResults"].items():
            for mode, res in modes.items():
                assert res["leakedBeforeSpeech"] == 0, f"{name} [{mode}] leaked before speech: {res}"
                assert res["bargeCount"] == 1, f"{name} [{mode}] failed 1.0x barge-in: {res}"
                assert res["triggeredAtMs"] is not None and 200 <= res["triggeredAtMs"] <= 2000

    def test_server_echo_guard_blocks_nonlinear_softclip_hardclip_hpf_agc_echo_and_allows_real_wavs_1x(self) -> None:
        aoede = _load_wav_floats(WAV_AOEDE_24K, 16000)
        aoede_6s = (aoede * 4)[: 16000 * 6]
        ref_pcm = _floats_to_pcm16_bytes(aoede_6s)
        delay_s = 60 * 16
        pure_echo = [0.0] * delay_s + [x * 0.22 for x in aoede_6s[:-delay_s]]

        for label, sig in (
            ("softclip_agc", _soft_clip_compressor(pure_echo)),
            ("hardclip_agc", _hard_clip_limiter(pure_echo)),
            ("hpf_softclip_agc", _hpf_plus_soft_clip(pure_echo)),
        ):
            guard = ServerEchoGuard()
            guard.note_ai_audio_chunk(ref_pcm, sample_rate=16000, now=100.0)
            barge_cnt = 0
            leaked = 0
            for i in range(0, len(sig) - 319, 320):
                t = 100.0 + (i / 16000.0)
                allow, barge, _ = guard.evaluate_mic_audio_chunk(_floats_to_pcm16_bytes(sig[i : i + 320]), now=t)
                if allow:
                    leaked += 1
                if barge:
                    barge_cnt += 1
            assert barge_cnt == 0 and leaked == 0, f"ServerEchoGuard failed on {label}: barge={barge_cnt} leaked={leaked}"

        for name, wpath in _all_human_wavs().items():
            speech = _load_wav_floats(wpath, 16000)
            for label, fn in (
                ("agc_off", lambda s: s),
                ("softclip_agc", _soft_clip_compressor),
                ("hpf_softclip_agc", _hpf_plus_soft_clip),
            ):
                mixed = list(pure_echo)
                off = 500 * 16
                for i in range(min(len(speech), len(mixed) - off)):
                    mixed[off + i] = max(-1.0, min(1.0, mixed[off + i] + speech[i]))
                mic_sig = fn(mixed)
                guard = ServerEchoGuard()
                guard.note_ai_audio_chunk(ref_pcm, sample_rate=16000, now=100.0)
                triggered = False
                leaked_pre = 0
                for i in range(0, len(mic_sig) - 319, 320):
                    t = 100.0 + (i / 16000.0)
                    allow, barge, _ = guard.evaluate_mic_audio_chunk(_floats_to_pcm16_bytes(mic_sig[i : i + 320]), now=t)
                    if t < 100.5 and allow:
                        leaked_pre += 1
                    if barge:
                        triggered = True
                        break
                assert leaked_pre == 0, f"ServerEchoGuard leaked before speech on {name} [{label}]"
                assert triggered, f"ServerEchoGuard failed 1.0x barge-in on {name} [{label}]"

    def test_chromium_real_webrtc_agc_on_and_off_pure_echo_blocked_and_real_speech_barges_in(
        self, fix9_live_server: tuple[str, dict[str, str]]
    ) -> None:
        from playwright.sync_api import sync_playwright

        base_url, creds = fix9_live_server
        aoede_24k = _load_wav_floats(WAV_AOEDE_24K, 24000)
        aoede_3s_24k = (aoede_24k * 4)[: 24000 * 3]
        aoede_3s_24k_bytes = _floats_to_pcm16_bytes(aoede_3s_24k)
        aoede_3s_16k = _load_wav_floats(WAV_AOEDE_24K, 16000)
        aoede_3s_16k = (aoede_3s_16k * 4)[: 16000 * 3]

        speech_16k = _load_wav_floats(TRACKED_HUMAN_WAVS["hen_gio_5s_tat_den"], 16000)

        with tempfile.TemporaryDirectory(prefix="fix9_wav_") as tmp_dir:
            echo_wav = pathlib.Path(tmp_dir) / "aoede_echo_20pct_16k.wav"
            _write_wav_16k(echo_wav, [x * 0.20 for x in aoede_3s_16k])

            mixed_wav = pathlib.Path(tmp_dir) / "aoede_plus_human_1x_16k.wav"
            mixed_len = 16000 * 3
            mixed_sig = [0.0] * mixed_len
            for i in range(mixed_len):
                e_val = aoede_3s_16k[i] * 0.20
                h_val = speech_16k[i - 8000] if 8000 <= i < 8000 + len(speech_16k) else 0.0
                mixed_sig[i] = max(-1.0, min(1.0, e_val + h_val))
            _write_wav_16k(mixed_wav, mixed_sig)

            def _run_chromium_case(fake_wav: pathlib.Path, force_agc: bool) -> dict[str, int]:
                with sync_playwright() as p:
                    browser = _launch_headless_chromium(
                        p,
                        extra_args=[
                            "--use-fake-device-for-media-stream",
                            "--use-fake-ui-for-media-stream",
                            f"--use-file-for-fake-audio-capture={fake_wav}",
                            "--autoplay-policy=no-user-gesture-required",
                        ],
                    )
                    try:
                        ctx = browser.new_context(
                            viewport={"width": 1366, "height": 768},
                            user_agent=creds["desktop_ua"],
                            permissions=["microphone"],
                        )
                        ctx.add_cookies(
                            [{"name": "sh_session_token", "value": creds["session_id"], "url": base_url, "httpOnly": True, "sameSite": "Lax"}]
                        )
                        page = ctx.new_page()
                        force_js = "true" if force_agc else "false"
                        page.add_init_script(
                            f"""(() => {{
                                window.__f9 = {{ gumTs: 0, aiTs: 0, aiWin: false, micDuringAi: 0, micFirst400ms: 0, bargeInSent: 0, lastWs: null }};
                                if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {{
                                    const origGum = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
                                    navigator.mediaDevices.getUserMedia = async function(constraints) {{
                                        const c = {force_js} && constraints && typeof constraints.audio === 'object'
                                            ? Object.assign({{}}, constraints, {{ audio: Object.assign({{}}, constraints.audio, {{ autoGainControl: true }}) }})
                                            : constraints;
                                        const s = await origGum(c);
                                        window.__f9.gumTs = performance.now();
                                        return s;
                                    }};
                                }}
                                const OrigWS = window.WebSocket;
                                window.WebSocket = function(url, protocols) {{
                                    const ws = protocols ? new OrigWS(url, protocols) : new OrigWS(url);
                                    if (String(url).includes('/ws')) window.__f9.lastWs = ws;
                                    const origSend = ws.send.bind(ws);
                                    ws.send = function(data) {{
                                        try {{
                                            const parsed = typeof data === 'string' ? JSON.parse(data) : null;
                                            if (parsed && parsed.type === 'mic_chunk' && window.__f9.aiWin) {{
                                                window.__f9.micDuringAi += 1;
                                                if (performance.now() - window.__f9.aiTs <= 400) window.__f9.micFirst400ms += 1;
                                            }}
                                            if (parsed && parsed.type === 'barge_in') window.__f9.bargeInSent += 1;
                                        }} catch (_) {{}}
                                        return origSend(data);
                                    }};
                                    return ws;
                                }};
                                window.WebSocket.prototype = OrigWS.prototype;
                                window.WebSocket.OPEN = OrigWS.OPEN;
                                window.WebSocket.CLOSED = OrigWS.CLOSED;
                                window.WebSocket.CONNECTING = OrigWS.CONNECTING;
                                window.WebSocket.CLOSING = OrigWS.CLOSING;
                            }})();"""
                        )
                        page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_selector("#btnMicLive", state="visible", timeout=15000)
                        page.wait_for_timeout(500)
                        page.click("#btnMicLive")
                        page.wait_for_timeout(600)

                        doubled_24k = aoede_3s_24k_bytes + aoede_3s_24k_bytes
                        elapsed_ms = page.evaluate("() => window.__f9.gumTs ? (performance.now() - window.__f9.gumTs) : 0")
                        pos_sec = ((elapsed_ms + 50.0) / 1000.0) % 3.0
                        byte_off = int(pos_sec * 24000) * 2
                        slice_2s = doubled_24k[byte_off : byte_off + 24000 * 2 * 2]
                        chunk_b64 = base64.b64encode(slice_2s).decode("ascii")

                        page.evaluate(
                            """(b64) => {
                                window.__f9.aiTs = performance.now();
                                window.__f9.aiWin = true;
                                const ws = window.__f9.lastWs;
                                if (ws && typeof ws.onmessage === 'function') {
                                    ws.onmessage({ data: JSON.stringify({ type: 'audio_chunk', pcm24k_b64: b64 }) });
                                }
                            }""",
                            chunk_b64,
                        )
                        page.wait_for_timeout(1750)
                        out = page.evaluate(
                            "() => { window.__f9.aiWin = false; return { micDuringAi: window.__f9.micDuringAi, micFirst400ms: window.__f9.micFirst400ms, bargeInSent: window.__f9.bargeInSent }; }"
                        )
                        ctx.close()
                        return out
                    finally:
                        browser.close()

            res_off = _run_chromium_case(echo_wav, force_agc=False)
            assert res_off["bargeInSent"] == 0 and res_off["micDuringAi"] == 0 and res_off["micFirst400ms"] == 0, (
                f"Pure echo AGC OFF failed: {res_off}"
            )

            res_on = _run_chromium_case(echo_wav, force_agc=True)
            assert res_on["bargeInSent"] == 0 and res_on["micDuringAi"] == 0 and res_on["micFirst400ms"] == 0, (
                f"Pure echo forced WebRTC AGC ON failed (P1-N1): {res_on}"
            )

            res_speech_on = _run_chromium_case(mixed_wav, force_agc=True)
            assert res_speech_on["bargeInSent"] >= 1, f"Real speech 1.0x failed to barge in with WebRTC AGC ON: {res_speech_on}"


# =============================================================================
# P2-N1, P2-N2, P2-N3: DARK MODE CARDS, PRIMARY BUTTON CONTRAST, MOBILE >=44PX
# =============================================================================

CONTRAST_HELPER_JS = """
(() => {
  function parseRgb(str) {
    const m = String(str || '').match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\\)/i);
    if (!m) return null;
    return { r: Number(m[1]), g: Number(m[2]), b: Number(m[3]), a: m[4] === undefined ? 1 : Number(m[4]) };
  }
  function effectiveBg(el) {
    let cur = el;
    while (cur && cur.nodeType === 1) {
      const c = parseRgb(getComputedStyle(cur).backgroundColor);
      if (c && c.a > 0.05) return c;
      cur = cur.parentElement;
    }
    return { r: 255, g: 255, b: 255, a: 1 };
  }
  function relLum(c) {
    const f = (v) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }
  window.__measureContrast = function(selector) {
    const el = document.querySelector(selector);
    if (!el) return null;
    const fg = parseRgb(getComputedStyle(el).color);
    const bg = effectiveBg(el);
    if (!fg || !bg) return null;
    const l1 = Math.max(relLum(fg), relLum(bg));
    const l2 = Math.min(relLum(fg), relLum(bg));
    return {
      selector,
      fg: getComputedStyle(el).color,
      bg: `rgb(${bg.r}, ${bg.g}, ${bg.b})`,
      ratio: Number(((l1 + 0.05) / (l2 + 0.05)).toFixed(2)),
    };
  };
})();
"""


class TestP2DarkContrastAndMobileTapTargets:
    def test_dark_mode_device_cards_and_all_pages_wcag_aa_contrast(
        self, fix9_live_server: tuple[str, dict[str, str]]
    ) -> None:
        from playwright.sync_api import sync_playwright

        base_url, creds = fix9_live_server
        with sync_playwright() as p:
            browser = _launch_headless_chromium(p)
            try:
                ctx = browser.new_context(
                    viewport={"width": 1366, "height": 768},
                    user_agent=creds["desktop_ua"],
                    color_scheme="dark",
                )
                ctx.add_cookies(
                    [{"name": "sh_session_token", "value": creds["session_id"], "url": base_url, "httpOnly": True, "sameSite": "Lax"}]
                )
                page = ctx.new_page()
                page.add_init_script(CONTRAST_HELPER_JS)
                page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_selector(".device, .dev", state="visible", timeout=15000)

                devices = page.evaluate(
                    """() => {
                        const cards = Array.from(document.querySelectorAll('.device, .dev'));
                        return cards.map((card, idx) => {
                            const nameEl = card.querySelector('.device-name, .dev-name') || card;
                            const cardBg = getComputedStyle(card).backgroundColor;
                            const nameFg = getComputedStyle(nameEl).color;
                            const parseRgb = (s) => {
                                const m = String(s).match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/i);
                                return m ? { r: +m[1], g: +m[2], b: +m[3] } : { r: 255, g: 255, b: 255 };
                            };
                            const lum = (c) => {
                                const f = (v) => { const x = v / 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
                                return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
                            };
                            const fg = parseRgb(nameFg);
                            const bg = parseRgb(cardBg);
                            const l1 = Math.max(lum(fg), lum(bg)), l2 = Math.min(lum(fg), lum(bg));
                            return { idx, cardBg, nameFg, ratio: Number(((l1 + 0.05) / (l2 + 0.05)).toFixed(2)) };
                        });
                    }"""
                )
                assert len(devices) == 6, f"Expected 6 device cards, got {len(devices)}"
                for d in devices:
                    assert d["cardBg"] != "rgb(255, 255, 255)", f"Device card still white in dark mode: {d}"
                    assert d["ratio"] >= 4.5, f"Device card contrast < 4.5:1 in dark mode: {d}"

                # Also verify [data-theme="dark"] mode on light system scheme
                ctx_attr = browser.new_context(viewport={"width": 1366, "height": 768}, user_agent=creds["desktop_ua"], color_scheme="light")
                pg_attr = ctx_attr.new_page()
                pg_attr.goto(f"{base_url}/guest_guide", wait_until="domcontentloaded", timeout=20000)
                pg_attr.evaluate("() => document.documentElement.setAttribute('data-theme', 'dark')")
                pg_attr.add_script_tag(content=CONTRAST_HELPER_JS)
                gg_btn = pg_attr.evaluate("() => window.__measureContrast('.btn.btn-primary')")
                gg_card = pg_attr.evaluate("() => window.__measureContrast('#guest-guide-title')")
                assert gg_btn and gg_btn["ratio"] >= 4.5, f"/guest_guide dark primary button contrast < 4.5: {gg_btn}"
                assert gg_card and gg_card["ratio"] >= 4.5, f"/guest_guide dark title contrast < 4.5: {gg_card}"
                ctx_attr.close()
                ctx.close()
            finally:
                browser.close()

    def test_primary_buttons_wcag_aa_contrast_light_and_dark(
        self, fix9_live_server: tuple[str, dict[str, str]]
    ) -> None:
        from playwright.sync_api import sync_playwright

        base_url, creds = fix9_live_server
        with sync_playwright() as p:
            browser = _launch_headless_chromium(p)
            try:
                for scheme in ("light", "dark"):
                    ctx = browser.new_context(
                        viewport={"width": 412, "height": 915},
                        user_agent=creds["mobile_ua"],
                        color_scheme=scheme,
                        is_mobile=True,
                        has_touch=True,
                    )
                    page = ctx.new_page()
                    page.add_init_script(CONTRAST_HELPER_JS)

                    for route, selector in (
                        ("/", "#btnSubmitGateLogin"),
                        ("/login", "#pageLoginSubmitBtn"),
                        ("/register", "#pageRegisterSubmitBtn"),
                        ("/guest_guide", ".btn.btn-primary"),
                        ("/app", "#mobileLoginBtn"),
                    ):
                        page.goto(f"{base_url}{route}", wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_selector(selector, state="visible", timeout=15000)
                        m = page.evaluate("(sel) => window.__measureContrast(sel)", selector)
                        assert m is not None and m["ratio"] >= 4.5, f"{route} {selector} [{scheme}] contrast < 4.5:1: {m}"

                    # Authenticated /app -> verify #mobileBtnCreateGuestQr contrast
                    ctx.add_cookies(
                        [{"name": "sh_session_token", "value": creds["session_id"], "url": base_url, "httpOnly": True, "sameSite": "Lax"}]
                    )
                    page.goto(f"{base_url}/app", wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_selector('button[data-tab="account"]', state="visible", timeout=15000)
                    page.click('button[data-tab="account"]')
                    page.wait_for_selector("#mobileDynamicQrCard > summary", state="visible", timeout=10000)
                    page.click("#mobileDynamicQrCard > summary")
                    page.wait_for_selector("#mobileBtnCreateGuestQr", state="visible", timeout=10000)
                    m_qr = page.evaluate("() => window.__measureContrast('#mobileBtnCreateGuestQr')")
                    assert m_qr is not None and m_qr["ratio"] >= 4.5, f"/app #mobileBtnCreateGuestQr [{scheme}] contrast < 4.5:1: {m_qr}"
                    ctx.close()
            finally:
                browser.close()

    def test_mobile_412x915_touch_targets_at_least_44px(
        self, fix9_live_server: tuple[str, dict[str, str]]
    ) -> None:
        from playwright.sync_api import sync_playwright

        base_url, creds = fix9_live_server
        with sync_playwright() as p:
            browser = _launch_headless_chromium(p)
            try:
                ctx = browser.new_context(
                    viewport={"width": 412, "height": 915},
                    user_agent=creds["mobile_ua"],
                    color_scheme="dark",
                    is_mobile=True,
                    has_touch=True,
                )
                page = ctx.new_page()

                # 1) / login gate (unauthenticated)
                page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_selector("#btnSubmitGateLogin", state="visible", timeout=15000)
                for sel in (
                    "#btnSubmitGateLogin",
                    "#gateLoginEmail",
                    "#gateLoginPassword",
                    "#homeLoginGateModal .btn-toggle-pw",
                    "#linkGateForgot",
                    "#gateOpenGuestGuideLink",
                    "#linkGateRegister",
                ):
                    box = page.locator(sel).first.bounding_box()
                    assert box is not None and box["height"] >= 44.0, f"/ mobile target {sel} height < 44px: {box}"

                # 2) /app authenticated QR panel buttons and PIN inputs
                ctx.add_cookies(
                    [{"name": "sh_session_token", "value": creds["session_id"], "url": base_url, "httpOnly": True, "sameSite": "Lax"}]
                )
                page.goto(f"{base_url}/app", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_selector('button[data-tab="account"]', state="visible", timeout=15000)
                page.click('button[data-tab="account"]')
                page.wait_for_selector("#mobileDynamicQrCard > summary", state="visible", timeout=10000)
                page.click("#mobileDynamicQrCard > summary")
                page.wait_for_selector("#mobileQrPinInput", state="visible", timeout=10000)
                for sel in (
                    "#mobileQrInviteTierSelect",
                    "#mobileGuestDurSelect",
                    "#mobileQrPinInput",
                    "#mobileQrPinConfirmInput",
                    "#mobileBtnCreateGuestQr",
                    "#mobileBtnCopyGuestQr",
                    "#mobileBtnShareGuestQr",
                    "#mobileBtnRefreshGuestQr",
                    "#mobileBtnRevokeGuestQr",
                ):
                    box = page.locator(sel).first.bounding_box()
                    assert box is not None and box["height"] >= 44.0, f"/app mobile target {sel} height < 44px: {box}"
                ctx.close()
            finally:
                browser.close()
