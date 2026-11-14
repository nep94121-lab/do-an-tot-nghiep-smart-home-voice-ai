"""Regression & E2E verification suite for Functional Fixes F1-F8 (2026-11-14)."""
from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import pathlib
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any, Generator

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.auth.session_store import (
    TRUSTED_DEVICE_COOKIE_NAME,
    TRUSTED_DEVICE_TTL_SECONDS,
    mint_trusted_device_token,
    verify_trusted_device_token,
)
from simulator.live import tts_rejection_vi as aoede_mod
from simulator.server import app
from simulator.voice_config import OWNER_EMAIL, OWNER_ID
from tests.live_auth_helpers import login_live_owner, prepare_live_auth


def _make_sine_pcm24k_bytes(freq_hz: float = 440.0, duration_sec: float = 0.2) -> bytes:
    sample_rate = 24000
    n_samples = int(sample_rate * duration_sec)
    buf = bytearray(n_samples * 2)
    for i in range(n_samples):
        val = int(12000 * math.sin(2.0 * math.pi * freq_hz * (i / sample_rate)))
        struct.pack_into("<h", buf, i * 2, val)
    return bytes(buf)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_server(base_url: str, timeout_s: float = 20.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/version", timeout=2.0) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"Server at {base_url} did not start within {timeout_s}s")


@pytest.fixture(scope="module")
def live_funcfix_server() -> Generator[dict[str, str], None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        port = _find_free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["SIMULATOR_OFFLINE_SANDBOX"] = "1"
        env["SMARTHOME_STATE_BACKEND"] = "file"
        env["SMARTHOME_STATE_FILE"] = str(pathlib.Path(tmpdir) / "live_funcfix_state.json")
        password = prepare_live_auth(env, tmpdir)
        for key in list(env):
            if any(s in key.upper() for s in ("BLOB_READ_WRITE_TOKEN", "VERCEL_OIDC_TOKEN")):
                env.pop(key, None)

        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "simulator.server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _wait_for_server(base_url)
            owner_token = login_live_owner(base_url, password)
            auth_init_script = f"""
                window._FORCE_HTTP_POLLING = true;
                window._disableWebSocket = true;
                sessionStorage.setItem('session_token', {json.dumps(owner_token)});
                localStorage.setItem('session_token', {json.dumps(owner_token)});
                localStorage.setItem('smarthome_auth_session', JSON.stringify({{
                    email: 'nep94121@gmail.com',
                    display_name: 'Nguyễn Tuấn Anh',
                    tier: 1,
                    role: 'ADMIN',
                    session_token: {json.dumps(owner_token)}
                }}));
                sessionStorage.setItem('mobileLoggedIn', '1');
                sessionStorage.setItem('mobileLoggedInEmail', 'nep94121@gmail.com');
                document.cookie = 'sh_session_token=' + {json.dumps(owner_token)} + '; path=/';
                document.cookie = 'session_token=' + {json.dumps(owner_token)} + '; path=/';
            """
            yield {
                "base_url": base_url,
                "owner_token": owner_token,
                "owner_password": password,
                "auth_init_script": auth_init_script,
            }
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
            user_sess_path = ROOT / "simulator" / "data" / "user_sessions.json"
            if user_sess_path.exists():
                try:
                    user_sess_path.unlink()
                except Exception:
                    pass


def _http_get_json(base_url: str, path: str, token: str = "") -> tuple[int, dict[str, Any]]:
    headers: dict[str, str] = {}
    if token:
        headers["X-Session-Token"] = token
    req = urllib.request.Request(f"{base_url}{path}", headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return int(resp.status), dict(json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = dict(json.loads(raw))
        except Exception:
            body = {"raw": raw}
        return int(exc.code), body


def _http_post_json(
    base_url: str, path: str, payload: dict[str, Any], token: str = ""
) -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Session-Token"] = token
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return int(resp.status), dict(json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = dict(json.loads(raw))
        except Exception:
            body = {"raw": raw}
        return int(exc.code), body


# ==============================================================================
# F1: GEMINI LIVE AOEDE 24kHz AUDIO RESPONSE & PLAYBACK (0 EXTERNAL TTS)
# ==============================================================================


class TestF1GeminiLiveAoedeAudio:
    def test_f1_html_and_source_invariants(self) -> None:
        web_html = (ROOT / "simulator" / "static" / "index.html").read_text(encoding="utf-8")
        mob_html = (ROOT / "mobile_app" / "index.html").read_text(encoding="utf-8")
        web_soup = BeautifulSoup(web_html, "html.parser")
        mob_soup = BeautifulSoup(mob_html, "html.parser")

        chk_web = web_soup.find(id="chkSpeakReply")
        chk_mob = mob_soup.find(id="ttsSpeakToggle")
        assert chk_web is not None and chk_web.has_attr("checked"), "#chkSpeakReply phải bật mặc định"
        assert chk_mob is not None and chk_mob.has_attr("checked"), "#ttsSpeakToggle phải bật mặc định"

        for js_rel in (
            "simulator/static/js/app.js",
            "simulator/static/js/mobile_app.js",
            "simulator/static/js/guest_control.js",
        ):
            src = (ROOT / js_rel).read_text(encoding="utf-8")
            assert "speechSynthesis.speak" not in src, f"{js_rel} không được dùng Web Speech API ngoài Aoede!"

        assert aoede_mod.AOEDE_VOICE_NAME == "Aoede"
        assert aoede_mod.AOEDE_LIVE_MODEL == "gemini-3.8-live"
        assert aoede_mod.SAMPLE_RATE == 24000

        # Non-fixed spoken confirmations must NEVER fall back to rejection WAV audio
        assert aoede_mod._load_bundled_aoede_pcm24k("Cửa chính đã mở.") == b""
        assert len(aoede_mod._load_bundled_aoede_pcm24k(aoede_mod.FIXED_REJECTION_PHRASE_VI)) > 2000
        assert len(aoede_mod._load_bundled_aoede_pcm24k(aoede_mod.FIXED_SAFE_DENY_REPEAT_PHRASE_VI)) > 2000

    def test_f1_api_voice_and_text_emit_aoede_24khz_pcm(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        monkeypatch.setenv("SMARTHOME_STATE_BACKEND", "file")
        monkeypatch.setenv("SMARTHOME_STATE_FILE", str(tmp_path / "f1_state.json"))
        sine_pcm = _make_sine_pcm24k_bytes(520.0, 0.25)

        async def _fake_live_aoede(phrase: str, _api_key: str) -> bytes:
            assert phrase.strip()
            return sine_pcm

        monkeypatch.setattr(aoede_mod, "_fetch_live_aoede_pcm24k", _fake_live_aoede)
        monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "0")
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-live-key")
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        saved_cache = dict(aoede_mod._LIVE_AOEDE_SESSION_CACHE)
        aoede_mod._LIVE_AOEDE_SESSION_CACHE.clear()
        try:
            empty_bundle = asyncio.run(
                aoede_mod.synthesize_aoede_phrase_audio("Đèn ngủ sáng dịu.", allow_live_refresh=False)
            )
            assert empty_bundle["pcm24k_b64"] == ""
            assert empty_bundle["audio_b64"] == ""

            with TestClient(app) as client:
                hdrs = {"X-Session-Token": "sess_owner_t1_nep94121"}

                r_voice = client.post("/api/voice_command", headers=hdrs, json={"transcript": "Mở cửa chính"})
                assert r_voice.status_code == 200, r_voice.text
                dv = r_voice.json()
                assert dv["ok"] is True
                assert dv["audio_voice"] == "Aoede"
                assert dv["audio_sample_rate"] == 24000
                assert dv["play_audio"] is True
                assert base64.b64decode(dv["pcm24k_b64"]) == sine_pcm

                r_text = client.post("/api/text_command", headers=hdrs, json={"text": "Bật đèn phòng khách"})
                assert r_text.status_code == 200, r_text.text
                dt = r_text.json()
                assert dt["ok"] is True
                assert dt["audio_voice"] == "Aoede"
                assert dt["audio_sample_rate"] == 24000
                assert dt["play_audio"] is True
                assert base64.b64decode(dt["pcm24k_b64"]) == sine_pcm

                r_phrase = client.post("/api/voice/aoede_phrase", headers=hdrs, json={"phrase": "Cửa chính đã mở."})
                assert r_phrase.status_code == 200, r_phrase.text
                dp = r_phrase.json()
                assert dp["audio_voice"] == "Aoede"
                assert dp["audio_sample_rate"] == 24000
                assert base64.b64decode(dp["pcm24k_b64"]) == sine_pcm
        finally:
            aoede_mod._LIVE_AOEDE_SESSION_CACHE.clear()
            aoede_mod._LIVE_AOEDE_SESSION_CACHE.update(saved_cache)

    def test_f1_playwright_web_plays_aoede_24khz_audio_on_text_command(
        self, live_funcfix_server: dict[str, str]
    ) -> None:
        sine_b64 = base64.b64encode(_make_sine_pcm24k_bytes(440.0, 0.15)).decode("ascii")

        async def _run() -> None:
            from playwright.async_api import async_playwright

            base_url = live_funcfix_server["base_url"]
            token = live_funcfix_server["owner_token"]
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, channel="chrome")
                ctx = await browser.new_context(viewport={"width": 1366, "height": 768})
                await ctx.add_cookies(
                    [{"name": n, "value": token, "url": base_url} for n in ("sh_session_token", "session_token")]
                )
                page = await ctx.new_page()
                await page.add_init_script(
                    live_funcfix_server["auth_init_script"]
                    + """
                    window.__recordedAudioStarts = [];
                    const _OrigAC = window.AudioContext || window.webkitAudioContext;
                    window.AudioContext = class extends _OrigAC {
                      createBufferSource() {
                        const src = super.createBufferSource();
                        const origStart = src.start.bind(src);
                        src.start = (...args) => {
                          const buf = src.buffer;
                          let maxAbs = 0;
                          if (buf) {
                            const ch = buf.getChannelData(0);
                            for (let i = 0; i < Math.min(ch.length, 400); i++) {
                              maxAbs = Math.max(maxAbs, Math.abs(ch[i]));
                            }
                          }
                          window.__recordedAudioStarts.push({
                            sampleRate: buf ? buf.sampleRate : 0,
                            length: buf ? buf.length : 0,
                            maxAbs
                          });
                          return origStart(...args);
                        };
                        return src;
                      }
                    };
                    window.webkitAudioContext = window.AudioContext;
                    """
                )

                async def _mock_aoede_phrase(route: Any, _req: Any) -> None:
                    await route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "ok": True,
                                "phrase": "Cửa chính đã mở.",
                                "pcm24k_b64": sine_b64,
                                "audio_sample_rate": 24000,
                                "audio_voice": "Aoede",
                            }
                        ),
                    )

                await page.route("**/api/voice/aoede_phrase", _mock_aoede_phrase)
                await page.goto(base_url + "/", wait_until="domcontentloaded")
                await page.wait_for_selector("#dev-card-main_door", timeout=15000)

                assert await page.is_checked("#chkSpeakReply") is True
                await page.fill("#txtCommand", "Mở cửa chính")
                await page.click("#btnSendText")
                await page.wait_for_function("() => (window.__recordedAudioStarts || []).length >= 1", timeout=8000)

                starts = await page.evaluate("() => window.__recordedAudioStarts")
                reply_text = await page.inner_text("#liveAiReply")
                assert "Cửa chính" in reply_text
                assert starts[0]["sampleRate"] == 24000
                assert starts[0]["length"] > 1000
                assert starts[0]["maxAbs"] > 0.05
                await browser.close()

        asyncio.run(_run())


# ==============================================================================
# F2: SINGLE SOURCE OF TRUTH — VOICE COMMAND THEN TOGGLE OFF IMMEDIATELY (ALL 7)
# ==============================================================================


class TestF2All7DevicesVoiceThenToggle:
    ALL_DEVICES = (
        ("main_door", "Mở cửa chính", "OPEN", "CLOSED"),
        ("living_room_light", "Bật đèn phòng khách", "ON", "OFF"),
        ("bedroom_light", "Bật đèn phòng ngủ", "ON", "OFF"),
        ("fan", "Bật quạt trần", "ON", "OFF"),
        ("ac", "Bật điều hòa", "ON", "OFF"),
        ("alarm_siren", "Bật còi báo động", "ON", "OFF"),
        ("garden_pump", "Bật máy bơm tưới cây", "ON", "OFF"),
    )

    def test_f2_all_7_devices_voice_on_then_web_toggle_off(
        self, live_funcfix_server: dict[str, str]
    ) -> None:
        async def _run() -> None:
            from playwright.async_api import async_playwright

            base_url = live_funcfix_server["base_url"]
            token = live_funcfix_server["owner_token"]
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, channel="chrome")
                ctx = await browser.new_context(viewport={"width": 1366, "height": 768})
                await ctx.add_cookies(
                    [{"name": n, "value": token, "url": base_url} for n in ("sh_session_token", "session_token")]
                )
                page = await ctx.new_page()
                await page.add_init_script(live_funcfix_server["auth_init_script"])
                await page.goto(base_url + "/", wait_until="domcontentloaded")
                await page.wait_for_selector("#dev-card-garden_pump", timeout=15000)

                for dev_id, phrase, expected_on, expected_off in self.ALL_DEVICES:
                    # 1) Set OFF/CLOSED cleanly first via API
                    _http_post_json(
                        base_url,
                        "/api/device",
                        {"device_id": dev_id, "target_state": expected_off, "client_id": "f2_prep", "client_seq": 1},
                        token=token,
                    )
                    # 2) Send real voice command transcript to turn ON/OPEN on server
                    st_code, vc_body = _http_post_json(
                        base_url,
                        "/api/voice_command",
                        {"transcript": phrase, "source": "f2_voice_e2e"},
                        token=token,
                    )
                    assert st_code == 200 and vc_body.get("ok") is True, f"{dev_id} voice failed: {vc_body}"

                    # Confirm server truth == ON/OPEN
                    code_s, snap = _http_get_json(base_url, "/api/state", token=token)
                    assert code_s == 200
                    srv_dev = next(d for d in snap["devices"] if d["id"] == dev_id)
                    assert srv_dev["state"] == expected_on, f"{dev_id} expected {expected_on}, got {srv_dev}"

                    # Force immediate UI sync and confirm card is checked/ON
                    await page.evaluate("() => window.pollRestStateFallback && window.pollRestStateFallback(true)")
                    await page.wait_for_selector(f'#dev-card-{dev_id}[data-state="on"]', timeout=6000)
                    assert await page.is_checked(f"#dev-card-{dev_id} .switch input") is True

                    # 3) Click web toggle to close/turn off immediately after voice command
                    await page.click(f"#dev-card-{dev_id} .switch")
                    await page.wait_for_selector(f'#dev-card-{dev_id}[data-state="off"]', timeout=6000)
                    await asyncio.sleep(0.35)

                    _, snap_after = _http_get_json(base_url, "/api/state", token=token)
                    srv_after = next(d for d in snap_after["devices"] if d["id"] == dev_id)
                    assert srv_after["state"] == expected_off, (
                        f"F2 regression on {dev_id}: expected {expected_off} after toggle, got {srv_after['state']}"
                    )
                    assert await page.is_checked(f"#dev-card-{dev_id} .switch input") is False

                await browser.close()

        asyncio.run(_run())


# ==============================================================================
# F3: REAL-TIME TWO-WAY SYNC WEB (/) <-> MOBILE APP (/app) WITHOUT RELOAD
# ==============================================================================


class TestF3TwoWaySyncWebAndMobileApp:
    def test_f3_realtime_two_way_sync_and_matching_labels(
        self, live_funcfix_server: dict[str, str]
    ) -> None:
        async def _run() -> None:
            from playwright.async_api import async_playwright

            base_url = live_funcfix_server["base_url"]
            token = live_funcfix_server["owner_token"]
            for dev_id, off_st in (("living_room_light", "OFF"), ("fan", "OFF"), ("main_door", "CLOSED")):
                _http_post_json(
                    base_url,
                    "/api/device",
                    {"device_id": dev_id, "target_state": off_st, "client_id": "f3_reset", "client_seq": 1},
                    token=token,
                )

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, channel="chrome")
                ctx = await browser.new_context(viewport={"width": 1366, "height": 768})
                await ctx.add_cookies(
                    [{"name": n, "value": token, "url": base_url} for n in ("sh_session_token", "session_token")]
                )
                page_web = await ctx.new_page()
                page_app = await ctx.new_page()
                await page_app.set_viewport_size({"width": 390, "height": 844})

                web_reloads = 0
                app_reloads = 0

                def _on_web_load() -> None:
                    nonlocal web_reloads
                    web_reloads += 1

                def _on_app_load() -> None:
                    nonlocal app_reloads
                    app_reloads += 1

                await page_web.add_init_script(live_funcfix_server["auth_init_script"])
                await page_app.add_init_script(live_funcfix_server["auth_init_script"])

                await page_web.goto(base_url + "/", wait_until="domcontentloaded")
                await page_app.goto(base_url + "/app", wait_until="domcontentloaded")
                await page_web.wait_for_selector("#dev-card-living_room_light", timeout=15000)
                await page_app.wait_for_selector("#mobileNavTabDevices", timeout=15000)
                await page_app.click("#mobileNavTabDevices")
                await page_app.wait_for_selector('#devGrid [data-device-id="fan"]', timeout=15000)
                await page_app.wait_for_selector('#devGrid [data-device-id="garden_pump"]', state="attached", timeout=15000)

                page_web.on("load", _on_web_load)
                page_app.on("load", _on_app_load)

                # Verify unified labels on /app match web
                mob_html_text = await page_app.evaluate(
                    "() => (document.getElementById('tabViewHome')?.innerText || '') + '\\n' + (document.getElementById('tabViewDevices')?.textContent || '')"
                )
                assert "Quạt trần" in mob_html_text
                assert "Máy bơm tưới cây" in mob_html_text
                assert "Toàn nhà" in mob_html_text

                # 1) Web -> /app
                await page_web.click("#dev-card-living_room_light .switch")
                await page_app.wait_for_selector(
                    '#devGrid [data-device-id="living_room_light"][data-state="on"]',
                    state="attached",
                    timeout=5000,
                )

                # 2) /app -> Web
                await page_app.click('#devGrid [data-device-id="fan"]')
                await page_web.wait_for_selector('#dev-card-fan[data-state="on"]', timeout=5000)

                # 3) Voice API -> Both Web & /app
                st_code, vc = _http_post_json(
                    base_url,
                    "/api/voice_command",
                    {"transcript": "Mở cửa chính", "source": "f3_voice"},
                    token=token,
                )
                assert st_code == 200 and vc.get("ok") is True
                await page_web.wait_for_selector('#dev-card-main_door[data-state="on"]', timeout=5000)
                await page_app.wait_for_selector('#devGrid [data-device-id="main_door"][data-state="on"]', timeout=5000)

                assert web_reloads == 0, "Web / không được reload khi đồng bộ hai chiều!"
                assert app_reloads == 0, "/app không được reload khi đồng bộ hai chiều!"
                await browser.close()

        asyncio.run(_run())


# ==============================================================================
# F4: 30-DAY TRUSTED DEVICE OTP COOKIE (sh_trusted_device)
# ==============================================================================


class TestF4TrustedDevice30DayOtp:
    def test_f4_trusted_device_cookie_skip_and_revocation_matrix(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")
        monkeypatch.setenv("PYTEST", "1")
        data_dir = tmp_path / "data"
        vault_dir = tmp_path / "vault"
        data_dir.mkdir()
        vault_dir.mkdir()
        monkeypatch.setenv("SMARTHOME_DATA_DIR", str(data_dir))
        monkeypatch.setenv("SMARTHOME_DURABLE_DIR", str(vault_dir))
        monkeypatch.setenv("SIMULATOR_SECURITY_STATE_DIR", str(data_dir))

        prep_dir = tmp_path / "prep"
        prep_dir.mkdir()
        env_tmp: dict[str, str] = {}
        ephemeral_pw = prepare_live_auth(env_tmp, str(prep_dir))
        # Copy freshly salted accounts_3layer.json into test data_dir & reload manager in-process
        (data_dir / "accounts_3layer.json").write_bytes(
            (pathlib.Path(env_tmp["SMARTHOME_DATA_DIR"]) / "accounts_3layer.json").read_bytes()
        )

        from simulator.auth_3layer import get_auth_3layer_manager

        mgr = get_auth_3layer_manager()
        saved_accounts = mgr.accounts
        try:
            mgr.accounts = json.loads((data_dir / "accounts_3layer.json").read_text(encoding="utf-8"))
            ua = {"User-Agent": "FuncFixTrustedBrowser/1.0"}

            with TestClient(app, base_url="https://testserver") as client_same_dev:
                # 1. First login requires Layer 2 OTP
                r1 = client_same_dev.post(
                    "/api/auth3/layer1_login",
                    headers=ua,
                    json={"email": OWNER_EMAIL, "password": ephemeral_pw, "send_gmail": False},
                )
                assert r1.status_code == 200, r1.text
                d1 = r1.json()
                assert d1.get("otp_required") is True
                assert "session_token" not in d1
                otp = d1.get("otp_code_for_test") or d1.get("demo_otp_preview")
                assert otp

                # 2. Verify OTP -> mints 30-day HttpOnly sh_trusted_device cookie
                r2 = client_same_dev.post(
                    "/api/auth3/layer2_verify_otp",
                    headers={**ua, "X-Forwarded-Proto": "https"},
                    json={"email": OWNER_EMAIL, "otp_code": otp},
                )
                assert r2.status_code == 200, r2.text
                d2 = r2.json()
                assert d2["ok"] is True
                assert d2["trusted_device_established"] is True
                assert d2["trusted_device_days"] == 30
                set_cookies_joined = "\n".join(r2.headers.get_list("set-cookie"))
                assert f"{TRUSTED_DEVICE_COOKIE_NAME}=" in set_cookies_joined
                assert "HttpOnly" in set_cookies_joined or "httponly" in set_cookies_joined.lower()
                assert f"Max-Age={TRUSTED_DEVICE_TTL_SECONDS}" in set_cookies_joined
                assert "Secure" in set_cookies_joined
                assert client_same_dev.get("/api/state").status_code == 200

                # 3. Normal logout revokes session but retains sh_trusted_device cookie
                r_out = client_same_dev.post("/api/auth/logout", headers=ua)
                assert r_out.status_code == 200
                assert client_same_dev.get("/api/state").status_code == 401
                assert client_same_dev.get("/api/session/role").status_code == 401
                assert client_same_dev.cookies.get(TRUSTED_DEVICE_COOKIE_NAME)

                # 4. Second login on SAME device skips OTP automatically
                r3 = client_same_dev.post(
                    "/api/auth3/layer1_login",
                    headers=ua,
                    json={"email": OWNER_EMAIL, "password": ephemeral_pw, "send_gmail": False},
                )
                assert r3.status_code == 200, r3.text
                d3 = r3.json()
                assert d3.get("trusted_device") is True
                assert not d3.get("otp_required")
                assert d3.get("session_token")
                assert client_same_dev.get("/api/state").status_code == 200

                # 5. Different User-Agent with stolen cookie MUST still require OTP
                r_diff_ua = client_same_dev.post(
                    "/api/auth3/layer1_login",
                    headers={"User-Agent": "OtherAttackerUA/9.9"},
                    json={"email": OWNER_EMAIL, "password": ephemeral_pw, "send_gmail": False},
                )
                assert r_diff_ua.status_code == 200
                assert r_diff_ua.json().get("otp_required") is True
                assert "session_token" not in r_diff_ua.json()

                # 6. Logout with revoke_trusted_device=true clears sh_trusted_device
                r_revoke = client_same_dev.post(
                    "/api/auth/logout",
                    headers=ua,
                    json={"revoke_trusted_device": True},
                )
                assert r_revoke.status_code == 200
                r_after_revoke = client_same_dev.post(
                    "/api/auth3/layer1_login",
                    headers=ua,
                    json={"email": OWNER_EMAIL, "password": ephemeral_pw, "send_gmail": False},
                )
                assert r_after_revoke.status_code == 200
                assert r_after_revoke.json().get("otp_required") is True
                assert "session_token" not in r_after_revoke.json()

            # 7. Fresh device (no cookie) + tampered cookie + expired (>30d) token require OTP
            with TestClient(app, base_url="https://testserver") as client_other_dev:
                r_fresh = client_other_dev.post(
                    "/api/auth3/layer1_login",
                    headers=ua,
                    json={"email": OWNER_EMAIL, "password": ephemeral_pw, "send_gmail": False},
                )
                assert r_fresh.json().get("otp_required") is True

                owner_acc = mgr.find_account(OWNER_EMAIL)
                assert owner_acc is not None
                valid_tok = mint_trusted_device_token(
                    OWNER_ID, OWNER_EMAIL, owner_acc["password_hash"], ua["User-Agent"]
                )
                assert verify_trusted_device_token(
                    valid_tok,
                    expected_account_id=OWNER_ID,
                    expected_email=OWNER_EMAIL,
                    expected_password_hash=owner_acc["password_hash"],
                    expected_user_agent=ua["User-Agent"],
                )
                # Expired after 30 days (+60s)
                assert (
                    verify_trusted_device_token(
                        valid_tok,
                        expected_account_id=OWNER_ID,
                        expected_email=OWNER_EMAIL,
                        expected_password_hash=owner_acc["password_hash"],
                        expected_user_agent=ua["User-Agent"],
                        now=time.time() + TRUSTED_DEVICE_TTL_SECONDS + 60,
                    )
                    is False
                )

                expired_tok = mint_trusted_device_token(
                    OWNER_ID,
                    OWNER_EMAIL,
                    owner_acc["password_hash"],
                    ua["User-Agent"],
                    ttl_seconds=60,
                    now=time.time() - 3600,
                )
                client_other_dev.cookies.set(TRUSTED_DEVICE_COOKIE_NAME, expired_tok)
                r_exp = client_other_dev.post(
                    "/api/auth3/layer1_login",
                    headers=ua,
                    json={"email": OWNER_EMAIL, "password": ephemeral_pw, "send_gmail": False},
                )
                assert r_exp.json().get("otp_required") is True
                assert "session_token" not in r_exp.json()
        finally:
            mgr.accounts = saved_accounts


# ==============================================================================
# F5, F6, F7, F8: ANONYMOUS GATES, /logs WARNING PRESERVATION, MOBILE 390 "Khách"
# ==============================================================================


class TestF5F6F7F8AnonymousSecurityAndMobileNav:
    def test_f5_anonymous_root_hides_owner_dom_and_state_returns_401(
        self, live_funcfix_server: dict[str, str]
    ) -> None:
        base_url = live_funcfix_server["base_url"]
        st_code, st_body = _http_get_json(base_url, "/api/state")
        assert st_code == 401 and st_body.get("authenticated") is False

        async def _run() -> None:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, channel="chrome")
                for vp in ({"width": 1366, "height": 768}, {"width": 390, "height": 844}):
                    ctx = await browser.new_context(viewport=vp)
                    page = await ctx.new_page()
                    page_errors: list[str] = []
                    page.on("pageerror", lambda e: page_errors.append(str(e)))
                    await page.goto(base_url + "/", wait_until="domcontentloaded")
                    await page.wait_for_selector("#homeLoginGateModal:not(.hidden)", timeout=10000)
                    await asyncio.sleep(0.3)

                    state = await page.evaluate(
                        """() => ({
                            hasShell: document.getElementById('homeAppShell') !== null,
                            hasDevicesGrid: document.getElementById('deviceGrid') !== null || document.getElementById('devicesGrid') !== null,
                            has3d: document.getElementById('house3dViewport') !== null,
                            hasQrMeta: document.getElementById('ownerGuestQrMeta') !== null,
                            bodyText: document.body.innerText,
                            scrollW: document.documentElement.scrollWidth,
                            innerW: window.innerWidth
                        })"""
                    )
                    assert state["hasShell"] is False
                    assert state["hasDevicesGrid"] is False
                    assert state["has3d"] is False
                    assert state["hasQrMeta"] is False
                    assert "28.5°C" not in state["bodyText"]
                    assert state["scrollW"] <= state["innerW"]
                    assert not page_errors
                    await ctx.close()
                await browser.close()

        asyncio.run(_run())

    def test_f6_f7_anonymous_logs_gate_and_load_more_warning_preserved(
        self, live_funcfix_server: dict[str, str]
    ) -> None:
        base_url = live_funcfix_server["base_url"]

        async def _run() -> None:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, channel="chrome")
                for vp in ({"width": 1366, "height": 768}, {"width": 390, "height": 844}):
                    ctx = await browser.new_context(viewport=vp)
                    page = await ctx.new_page()
                    await page.goto(base_url + "/logs", wait_until="domcontentloaded")
                    await page.wait_for_selector("#logsAccessDeniedGate", timeout=10000)
                    await asyncio.sleep(0.4)

                    snap = await page.evaluate(
                        """() => {
                            const gate = document.getElementById('logsAccessDeniedGate');
                            const shell = document.getElementById('logsAdminShell');
                            const actions = document.getElementById('logsHeaderActions');
                            const loginBtn = document.getElementById('btnLogsGateLogin');
                            return {
                                gateVisible: gate && !gate.hidden && gate.offsetParent !== null,
                                gateText: gate ? gate.innerText : '',
                                loginHref: loginBtn ? loginBtn.getAttribute('href') : '',
                                shellHidden: !shell || shell.hidden || shell.offsetParent === null,
                                actionsHidden: !actions || actions.hidden || actions.offsetParent === null,
                                loadMoreRet: typeof window.loadMoreLogs === 'function' ? window.loadMoreLogs() : null,
                                actionStatus: document.getElementById('logsActionStatus')?.textContent || '',
                                tbodyText: document.getElementById('auditLogsTbody')?.innerText || '',
                                btnMoreText: document.getElementById('btnLogsLoadMore')?.textContent || ''
                            };
                        }"""
                    )
                    assert snap["gateVisible"] is True
                    assert "Chủ nhà" in snap["gateText"]
                    assert snap["loginHref"] == "/login"
                    assert snap["shellHidden"] is True
                    assert snap["actionsHidden"] is True
                    assert snap["loadMoreRet"] is False
                    assert "Chủ nhà" in snap["actionStatus"]
                    assert "Chưa có sự kiện" not in snap["tbodyText"]
                    assert "Đã hiển thị tất cả" not in snap["btnMoreText"]
                    await ctx.close()
                await browser.close()

        asyncio.run(_run())

    def test_f8_mobile_390_guest_guide_link_visible_and_clickable(
        self, live_funcfix_server: dict[str, str]
    ) -> None:
        base_url = live_funcfix_server["base_url"]

        async def _run() -> None:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, channel="chrome")
                ctx = await browser.new_context(
                    viewport={"width": 390, "height": 844},
                    is_mobile=True,
                    has_touch=True,
                )
                page = await ctx.new_page()
                page_errors: list[str] = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))

                for route_path in ("/auth", "/login"):
                    await page.goto(base_url + route_path, wait_until="domcontentloaded")
                    link = page.locator('.mobile-nav a[href="/guest_guide"]')
                    await link.wait_for(state="visible", timeout=8000)
                    box = await link.bounding_box()
                    assert box is not None and box["width"] > 0 and box["height"] > 0
                    assert box["x"] >= 0 and (box["x"] + box["width"]) <= 390
                    dims = await page.evaluate(
                        "() => ({ iw: window.innerWidth, sw: document.documentElement.scrollWidth })"
                    )
                    assert dims["iw"] == 390 and dims["sw"] <= 390

                await page.locator('.mobile-nav a[href="/guest_guide"]').click()
                await page.wait_for_url("**/guest_guide", timeout=8000)
                guide_dims = await page.evaluate(
                    "() => ({ iw: window.innerWidth, sw: document.documentElement.scrollWidth, text: document.body.innerText })"
                )
                assert guide_dims["iw"] == 390 and guide_dims["sw"] <= 390
                assert "Khách" in guide_dims["text"]
                assert not page_errors
                await browser.close()

        asyncio.run(_run())
