# -*- coding: utf-8 -*-
"""Adversarial Stress Test Suite for Phase 7 Guest Fix Round 2.
Empirically challenges:
1. Audio edge cases (0B, >15MB, fake text .wav, valid .wav)
2. Button spamming / race conditions
3. Mic denied handling & fake sine wave detection (including #btnRetryGuestVoice)
4. Responsive viewports (320x568, 360x740, 390x844) & bounding box overlap
"""

import os
import sys
import time
import socket
import threading
import pathlib
import pytest
import numpy as np
import soundfile as sf
import uvicorn
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from simulator.server import app, _ACTIVE_BRIDGES, _BOOT_VOICE_AUTH
from simulator.auth_3layer import get_auth_3layer_manager


@pytest.fixture(autouse=True)
def reset_adversarial_stress_state():
    _ACTIVE_BRIDGES.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    yield
    _ACTIVE_BRIDGES.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    mgr = get_auth_3layer_manager()
    mgr.accounts = [
        acc for acc in mgr.accounts
        if str(acc.get("email", "")) not in (
            "test0b@gmail.com",
            "testfake@gmail.com",
            "test16mb@gmail.com",
            "testchuan@gmail.com",
            "spamclick@gmail.com",
            "sinewave@gmail.com",
        )
    ]
    mgr._save_accounts()


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server_url():
    port = _get_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)

    yield base_url

    server.should_exit = True
    thread.join(timeout=3)
    for br in list(_ACTIVE_BRIDGES):
        try:
            br._closed = True
        except Exception:
            pass
    _ACTIVE_BRIDGES.clear()


def _make_wav_file(path: pathlib.Path, f0: float = 165.0):
    sr = 16000
    rng = np.random.default_rng(42)
    t2 = np.linspace(0, 2.6, int(sr * 2.6), endpoint=False)
    f0_var = f0 + 25.0 * np.sin(2 * np.pi * 1.7 * t2) + 8.0 * np.cos(2 * np.pi * 4.3 * t2)
    phase = 2 * np.pi * np.cumsum(f0_var) / sr
    harm = sum((1.0 / k) * np.sin(k * phase) for k in range(1, 14))
    env = np.clip(np.sin(np.pi * ((t2 * 2.2) % 1.0)), 0.0, 1.0) ** 0.6
    env[:int(0.25 * sr)] = 0.0
    env[-int(0.25 * sr):] = 0.0
    sig = 0.35 * (harm / np.max(np.abs(harm))) * env + 0.008 * env * rng.standard_normal(len(t2))
    sf.write(str(path), sig.astype(np.float32), sr, format="WAV", subtype="PCM_16")


@pytest.fixture(scope="module")
def sample_audio_files(tmp_path_factory):
    tmp_dir = tmp_path_factory.mktemp("adversarial_audio")

    empty_wav = tmp_dir / "empty.wav"
    empty_wav.write_bytes(b"")

    fake_wav = tmp_dir / "fake.wav"
    fake_wav.write_text("RIFFfakeWAVEfmt not real audio data dummy text payload", encoding="utf-8")

    valid_wav = tmp_dir / "valid_voice.wav"
    _make_wav_file(valid_wav, 165.0)

    large_wav = tmp_dir / "large_16mb.wav"
    large_wav.write_bytes(b"RIFF" + b"\x00" * (16 * 1024 * 1024))

    return {
        "dir": tmp_dir,
        "empty": empty_wav,
        "fake": fake_wav,
        "valid": valid_wav,
        "large": large_wav,
    }


def _launch_browser(p):
    try:
        return p.chromium.launch(channel="msedge", headless=True)
    except Exception:
        return p.chromium.launch(headless=True)


def _create_qr_invite(base_url: str, duration_code: str = "1d", guest_name: str = "Khách Stress") -> str:
    import json as _json
    import urllib.request as _req

    body = _json.dumps({
        "pin": "1357",
        "pin_confirm": "1357",
        "duration_code": duration_code,
        "guest_name": guest_name,
    }).encode("utf-8")
    r = _req.Request(
        f"{base_url}/api/guest/invites",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Session-Token": "sess_owner_t1_nep94121",
        },
        method="POST",
    )
    with _req.urlopen(r, timeout=10) as resp:
        data = _json.loads(resp.read().decode("utf-8"))
    url = str(data.get("url") or "")
    return url.split("token=", 1)[1].split("&", 1)[0]


def test_adversarial_audio_empty_file(live_server_url, sample_audio_files):
    """Tệp PCM rỗng 0B bị chất lượng âm học từ chối, /guest không token trả 403, endpoint cũ trả 410."""
    import httpx
    from simulator.voice_auth import evaluate_audio_quality_gate

    _BOOT_VOICE_AUTH.reset_to_owner_only()
    empty_bytes = sample_audio_files["empty"].read_bytes()
    q_res = evaluate_audio_quality_gate(empty_bytes, sr=16000)
    assert q_res["ok"] is False

    r_unauth = httpx.get(f"{live_server_url}/guest", timeout=10)
    assert r_unauth.status_code == 403

    r_gone = httpx.post(
        f"{live_server_url}/api/auth3/guest_qr_complete_voice",
        json={"guest_name": "Khách 0B", "duration": "1d", "audio_pcm_b64": ""},
        timeout=10,
    )
    assert r_gone.status_code == 410 and r_gone.json().get("gone") is True


def test_adversarial_audio_fake_wav_file(live_server_url, sample_audio_files):
    """Tệp text giả .wav bị từ chối và token mời giả trên /api/guest/redeem bị chặn 403."""
    import httpx
    from simulator.voice_auth import evaluate_audio_quality_gate

    _BOOT_VOICE_AUTH.reset_to_owner_only()
    fake_bytes = sample_audio_files["fake"].read_bytes()
    q_res = evaluate_audio_quality_gate(fake_bytes, sr=16000)
    assert q_res["ok"] is False

    r_bad_tok = httpx.post(
        f"{live_server_url}/api/guest/redeem",
        json={"token": "inv_fake_not_real_token_123"},
        timeout=10,
    )
    assert r_bad_tok.status_code == 403


def test_adversarial_audio_large_16mb_file(live_server_url, sample_audio_files):
    """Tệp > 15MB toàn byte 0 bị cổng chất lượng âm học từ chối và /guest_enroll đã gỡ trả 410."""
    import httpx
    from simulator.voice_auth import evaluate_audio_quality_gate

    _BOOT_VOICE_AUTH.reset_to_owner_only()
    large_bytes = sample_audio_files["large"].read_bytes()
    assert len(large_bytes) > 15 * 1024 * 1024
    q_res = evaluate_audio_quality_gate(large_bytes[:320000], sr=16000)
    assert q_res["ok"] is False

    r_gone = httpx.get(f"{live_server_url}/guest_enroll", timeout=10)
    assert r_gone.status_code == 410


def test_adversarial_audio_valid_wav_file(live_server_url, sample_audio_files):
    """Tệp .wav harmonic chuẩn 16kHz đạt chất lượng âm học và tạo invite 1d hợp lệ."""
    import soundfile as sf_read
    from simulator.voice_auth import evaluate_audio_quality_gate

    _BOOT_VOICE_AUTH.reset_to_owner_only()
    samples, sr = sf_read.read(str(sample_audio_files["valid"]), dtype="int16")
    assert sr == 16000
    q_res = evaluate_audio_quality_gate(samples.tobytes(), sr=16000)
    assert q_res["ok"] is True

    tok = _create_qr_invite(live_server_url, duration_code="1d", guest_name="Khách Hợp Lệ")
    assert tok.startswith("inv_")


def test_adversarial_button_spamming_race_condition(live_server_url, sample_audio_files):
    """Race condition & spam redeem: cùng một token single-use chỉ đổi được đúng 1 phiên 200, mọi lần sau 403 used."""
    from concurrent.futures import ThreadPoolExecutor
    import httpx

    _BOOT_VOICE_AUTH.reset_to_owner_only()
    tok = _create_qr_invite(live_server_url, duration_code="1d", guest_name="Khách Spam Redeem")

    def _redeem_once(_idx: int) -> tuple[int, dict]:
        r = httpx.post(f"{live_server_url}/api/guest/redeem", json={"token": tok}, timeout=10)
        return r.status_code, r.json()

    with ThreadPoolExecutor(max_workers=5) as pool:
        outcomes = list(pool.map(_redeem_once, range(5)))

    ok_200 = [o for o in outcomes if o[0] == 200 and o[1].get("ok") is True]
    blk_403 = [o for o in outcomes if o[0] == 403 and o[1].get("reason") == "used"]
    assert len(ok_200) == 1, f"Single-use QR phải chỉ cấp đúng 1 phiên, nhưng được: {outcomes}"
    assert len(blk_403) == 4, f"4 lần race redeem còn lại phải bị chặn used: {outcomes}"


def test_adversarial_sine_wave_existence_and_retry_button_vulnerability(live_server_url):
    """Xác minh không còn window.generateSynthetic16kPcmB64 trên trang chủ hay /guest?token và endpoint enroll cũ trả 410."""
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    tok = _create_qr_invite(live_server_url, duration_code="1d", guest_name="Khách Kiểm Tra JS")

    with sync_playwright() as p:
        browser = _launch_browser(p)
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        ctx.route("**/*fonts*", lambda route: route.fulfill(status=200, body=""))
        page = ctx.new_page()

        page.goto(f"{live_server_url}/guest?token={tok}", wait_until="domcontentloaded")
        page.wait_for_selector("#guestApp:not([hidden])", timeout=15000)

        has_synthetic_guest = page.evaluate("() => typeof window.generateSynthetic16kPcmB64 === 'function'")
        has_retry_btn = page.locator("#btnRetryGuestVoice").count()
        assert not has_synthetic_guest, "Hàm generateSynthetic16kPcmB64 không được phép tồn tại!"
        assert has_retry_btn == 0, "Nút legacy #btnRetryGuestVoice không được phép tồn tại!"

        ctx.add_cookies([{"name": "sh_session_token", "value": "sess_owner_t1_nep94121", "url": live_server_url}])
        page.goto(f"{live_server_url}/", wait_until="domcontentloaded")
        page.wait_for_selector("#ownerGuestQrPanel", timeout=15000)
        has_synthetic_home = page.evaluate("() => typeof window.generateSynthetic16kPcmB64 === 'function'")
        assert not has_synthetic_home, "Trang chủ không được phép có generateSynthetic16kPcmB64!"

        browser.close()


@pytest.mark.parametrize("vp_name,w,h", [
    ("320x568", 320, 568),
    ("360x740", 360, 740),
    ("390x844", 390, 844),
])
def test_adversarial_viewport_overflow_and_bounding_boxes(live_server_url, tmp_path, vp_name, w, h):
    """Thử thách Responsive Viewports 320x568, 360x740, 390x844 trên /guest?token=... và Dashboard (/):
    1. scrollWidth <= clientWidth (0 horizontal overflow)
    2. Bounding boxes không bị tràn ngoài viewport (x >= 0, x + width <= w + 2)
    """
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    tok = _create_qr_invite(live_server_url, duration_code="1w", guest_name=f"Khách {vp_name}")

    with sync_playwright() as p:
        browser = _launch_browser(p)

        # --- A. /guest?token=... ---
        guest_ctx = browser.new_context(viewport={"width": w, "height": h})
        guest_ctx.route("**/*fonts*", lambda route: route.fulfill(status=200, body=""))
        page = guest_ctx.new_page()
        page.goto(f"{live_server_url}/guest?token={tok}", wait_until="domcontentloaded")
        page.wait_for_selector("#guestApp:not([hidden])", timeout=15000)

        scroll_w = page.evaluate("() => document.documentElement.scrollWidth")
        client_w = page.evaluate("() => document.documentElement.clientWidth")
        assert scroll_w <= client_w, f"/guest bị tràn ngang trên {vp_name}: scrollWidth={scroll_w} > clientWidth={client_w}"

        shell = page.locator("#guestApp")
        box = shell.bounding_box()
        assert box is not None, "Không tìm thấy #guestApp trên /guest"
        assert box["x"] >= 0, f"#guestApp tràn lề trái trên {vp_name}: {box['x']}"
        assert box["x"] + box["width"] <= w + 2, f"#guestApp tràn lề phải trên {vp_name}: {box['x'] + box['width']} > {w}"

        mic_box = page.locator("#guestMicBtn").bounding_box()
        if mic_box:
            assert mic_box["x"] >= 0, f"Nút #guestMicBtn tràn lề trái trên {vp_name}"
            assert mic_box["x"] + mic_box["width"] <= w + 2, f"Nút #guestMicBtn tràn lề phải trên {vp_name}"

        page.screenshot(path=str(tmp_path / f"challenger_guest_{vp_name}.png"), full_page=True)
        guest_ctx.close()

        # --- B. Dashboard (/) ---
        dash_ctx = browser.new_context(viewport={"width": w, "height": h})
        dash_ctx.route("**/*fonts*", lambda route: route.fulfill(status=200, body=""))
        dash_ctx.add_cookies([{"name": "sh_session_token", "value": "sess_owner_t1_nep94121", "url": live_server_url}])
        dash_page = dash_ctx.new_page()
        dash_page.goto(f"{live_server_url}/", wait_until="domcontentloaded")
        dash_page.wait_for_selector("#ownerGuestQrPanel", timeout=15000)

        d_scroll_w = dash_page.evaluate("() => document.documentElement.scrollWidth")
        d_client_w = dash_page.evaluate("() => document.documentElement.clientWidth")
        assert d_scroll_w <= d_client_w, f"Dashboard bị tràn ngang trên {vp_name}: scrollWidth={d_scroll_w} > clientWidth={d_client_w}"

        qr_panel = dash_page.locator("#ownerGuestQrPanel")
        p_box = qr_panel.bounding_box()
        assert p_box is not None, "Không tìm thấy #ownerGuestQrPanel"
        assert p_box["x"] >= 0, f"Panel QR tràn lề trái trên {vp_name}"
        assert p_box["x"] + p_box["width"] <= w + 2, f"Panel QR tràn lề phải trên {vp_name}: {p_box['x'] + p_box['width']} > {w}"

        dash_page.screenshot(path=str(tmp_path / f"challenger_dashboard_{vp_name}.png"), full_page=True)
        dash_ctx.close()

        browser.close()
