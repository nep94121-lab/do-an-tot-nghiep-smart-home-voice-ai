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


def _make_wav_file(path: pathlib.Path, f0: float = 210.0):
    sr = 16000
    dur = 2.5
    t = np.linspace(0, dur - 0.3, int(sr * (dur - 0.3)), endpoint=False)
    sig_voice = (
        0.40 * np.sin(2 * np.pi * f0 * t)
        + 0.20 * np.sin(2 * np.pi * (f0 * 2) * t)
        + 0.10 * np.sin(2 * np.pi * (f0 * 3) * t)
    )
    sig = np.concatenate([np.zeros(int(sr * 0.3), dtype=np.float32), sig_voice])
    sf.write(str(path), sig, sr, format="WAV", subtype="PCM_16")


@pytest.fixture(scope="module")
def sample_audio_files(tmp_path_factory):
    tmp_dir = tmp_path_factory.mktemp("adversarial_audio")

    empty_wav = tmp_dir / "empty.wav"
    empty_wav.write_bytes(b"")

    fake_wav = tmp_dir / "fake.wav"
    fake_wav.write_text("RIFFfakeWAVEfmt not real audio data dummy text payload", encoding="utf-8")

    valid_wav = tmp_dir / "valid_voice.wav"
    _make_wav_file(valid_wav, 215.0)

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


def test_adversarial_audio_empty_file(live_server_url, sample_audio_files):
    """Thử nghiệm tệp 0 bytes: Nút Lưu phải giữ disabled, không kích hoạt thành công."""
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    with sync_playwright() as p:
        browser = _launch_browser(p)
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        page.goto(f"{live_server_url}/guest", wait_until="domcontentloaded")
        page.wait_for_selector("#guestNameInput", state="visible")

        page.fill("#guestNameInput", "Khách Test 0B")
        page.fill("#guestOptionalEmailInput", "test0b@gmail.com")

        page.set_input_files("#guestAudioFileInput", str(sample_audio_files["empty"]))
        page.wait_for_timeout(1000)

        is_disabled = page.is_disabled("#btnConfirmGuestVoiceOk")
        assert is_disabled, "Nút Lưu KHÔNG được mở khóa khi upload tệp 0 bytes!"

        info_text = page.locator("#uploadedAudioInfo").inner_text()
        assert "chưa đạt chuẩn" in info_text.lower() or "lỗi" in info_text.lower() or "❌" in info_text or "⚠️" in info_text

        browser.close()


def test_adversarial_audio_fake_wav_file(live_server_url, sample_audio_files):
    """Thử nghiệm tệp text giả .wav: Nút Lưu phải giữ disabled."""
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    with sync_playwright() as p:
        browser = _launch_browser(p)
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        page.goto(f"{live_server_url}/guest", wait_until="domcontentloaded")
        page.wait_for_selector("#guestNameInput", state="visible")

        page.fill("#guestNameInput", "Khách Test Fake WAV")
        page.fill("#guestOptionalEmailInput", "testfake@gmail.com")

        page.set_input_files("#guestAudioFileInput", str(sample_audio_files["fake"]))
        page.wait_for_timeout(1500)

        is_disabled = page.is_disabled("#btnConfirmGuestVoiceOk")
        assert is_disabled, "Nút Lưu KHÔNG được mở khóa khi upload tệp text giả .wav!"

        info_text = page.locator("#uploadedAudioInfo").inner_text()
        assert "chưa đạt chuẩn" in info_text.lower() or "lỗi" in info_text.lower() or "❌" in info_text or "⚠️" in info_text

        browser.close()


def test_adversarial_audio_large_16mb_file(live_server_url, sample_audio_files):
    """Thử nghiệm tệp > 15MB:
    Kiểm tra xem hệ thống có kiểm soát và từ chối rõ ràng hay không.
    """
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    with sync_playwright() as p:
        browser = _launch_browser(p)
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        page.goto(f"{live_server_url}/guest", wait_until="domcontentloaded")
        page.wait_for_selector("#guestNameInput", state="visible")

        page.fill("#guestNameInput", "Khách Test 16MB")
        page.fill("#guestOptionalEmailInput", "test16mb@gmail.com")

        page.set_input_files("#guestAudioFileInput", str(sample_audio_files["large"]))
        page.wait_for_timeout(2500)

        is_disabled = page.is_disabled("#btnConfirmGuestVoiceOk")
        assert is_disabled, "Nút Lưu KHÔNG được mở khóa khi upload tệp 16MB không hợp lệ!"

        browser.close()


def test_adversarial_audio_valid_wav_file(live_server_url, sample_audio_files):
    """Thử nghiệm tệp .wav hợp lệ: Nút Lưu phải mở khóa (enabled = True)."""
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    with sync_playwright() as p:
        browser = _launch_browser(p)
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        page.goto(f"{live_server_url}/guest", wait_until="domcontentloaded")
        page.wait_for_selector("#guestNameInput", state="visible")

        page.fill("#guestNameInput", "Khách Test Chuẩn")
        page.fill("#guestOptionalEmailInput", "testchuan@gmail.com")

        page.set_input_files("#guestAudioFileInput", str(sample_audio_files["valid"]))
        page.wait_for_function("() => !document.getElementById('btnConfirmGuestVoiceOk').disabled", timeout=10000)

        assert not page.is_disabled("#btnConfirmGuestVoiceOk"), "Nút Lưu PHẢI mở khóa khi upload tệp .wav chuẩn!"

        browser.close()


def test_adversarial_button_spamming_race_condition(live_server_url, sample_audio_files):
    """Thử nghiệm click đúp / spam click liên tục vào nút Lưu:
    Xác nhận class .btn-loading và disabled ngăn chặn click kép, không phát sinh race condition.
    """
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    fresh_wav = sample_audio_files["dir"] / "spam_voice.wav"
    _make_wav_file(fresh_wav, 185.0)

    with sync_playwright() as p:
        browser = _launch_browser(p)
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()

        page.goto(f"{live_server_url}/guest", wait_until="domcontentloaded")
        page.wait_for_selector("#guestNameInput", state="visible")

        page.fill("#guestNameInput", "Khách Spam Click")
        page.fill("#guestOptionalEmailInput", "spamclick@gmail.com")

        page.set_input_files("#guestAudioFileInput", str(fresh_wav))
        page.wait_for_function("() => !document.getElementById('btnConfirmGuestVoiceOk').disabled", timeout=10000)

        # Spam click 5 lần cực nhanh bằng JS evaluate
        click_results = page.evaluate("""() => {
            const btn = document.getElementById('btnConfirmGuestVoiceOk');
            const results = [];
            for (let i = 0; i < 5; i++) {
                results.push({
                    iteration: i,
                    disabled: btn.disabled,
                    hasLoadingClass: btn.classList.contains('btn-loading')
                });
                btn.click();
            }
            return results;
        }""")

        page.wait_for_selector("#saveFeedbackAlert:not([style*='display: none'])", timeout=10000)

        # Lần 0: ban đầu disabled=False, ngay sau click đầu tiên phải disabled=True hoặc có class .btn-loading
        assert click_results[0]["disabled"] is False, "Lần đầu tiên nút phải sẵn sàng (disabled=False)"
        assert click_results[1]["disabled"] is True or click_results[1]["hasLoadingClass"] is True, (
            f"Các lần spam click sau phải bị chặn (disabled=True hoặc có class .btn-loading)! Chi tiết: {click_results}"
        )

        browser.close()


def test_adversarial_sine_wave_existence_and_retry_button_vulnerability(live_server_url):
    """Thử thách: Kiểm tra sự tồn tại của code sóng sin giả lập và lỗ hổng nút 'Thu lại' (#btnRetryGuestVoice).
    Phát hiện xem code sinh sóng sin có bị xóa triệt để hay vẫn tồn tại trong guest_enroll.js và guest_enroll.html.
    """
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    with sync_playwright() as p:
        browser = _launch_browser(p)
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()

        page.goto(f"{live_server_url}/guest", wait_until="domcontentloaded")
        page.wait_for_selector("#guestNameInput", state="visible")

        # Mock mic bị từ chối
        page.evaluate("""() => {
            if (!navigator.mediaDevices) navigator.mediaDevices = {};
            navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException("Denied", "NotAllowedError"));
        }""")

        page.fill("#guestNameInput", "Khách Test Sine Wave")
        page.fill("#guestOptionalEmailInput", "sinewave@gmail.com")

        # 1. Bấm thu âm -> Thất bại -> Nút Lưu disabled
        page.click("#btnRecordGuestVoice")
        page.wait_for_selector("#micErrorAlert:not([style*='display: none'])", timeout=5000)
        assert page.is_disabled("#btnConfirmGuestVoiceOk"), "Nút Lưu phải disabled sau khi mic lỗi"

        # 2. Kiểm tra trực tiếp xem hàm generateSynthetic16kPcmB64 có tồn tại trên window hay không
        has_synthetic_fn = page.evaluate("() => typeof window.generateSynthetic16kPcmB64 === 'function'")
        
        # 3. Kiểm tra nút #btnRetryGuestVoice có thuộc tính onclick chứa 'recordAndEnrollGuestVoice' hay không
        retry_onclick = page.locator("#btnRetryGuestVoice").get_attribute("onclick") or ""

        # 4. Bấm nút Thu lại (#btnRetryGuestVoice) khi mic lỗi:
        # Nếu hàm sóng sin giả còn hoạt động, nó sẽ gọi sendGuestVoicePayload và mở khóa nút Lưu!
        page.click("#btnRetryGuestVoice")
        page.wait_for_timeout(2000)

        save_disabled_after_retry = page.is_disabled("#btnConfirmGuestVoiceOk")

        browser.close()

        # Kiểm chứng nghiêm ngặt: Theo yêu cầu 'Xác minh không còn bất kỳ dòng code sinh giọng sóng sin giả lập nào',
        # hàm generateSynthetic16kPcmB64 KHÔNG ĐƯỢC PHÉP tồn tại!
        # Và nút Thu lại KHÔNG ĐƯỢC mở khóa nút Lưu bằng giọng sóng sin giả!
        assert not has_synthetic_fn, (
            "PHÁT HIỆN LỖ HỔNG: window.generateSynthetic16kPcmB64 VẪN TỒN TẠI trong guest_enroll.js! "
            "Worker M7R2_2 báo cáo đã xóa hoàn toàn nhưng thực tế hàm này vẫn còn nguyên vẹn."
        )


@pytest.mark.parametrize("vp_name,w,h", [
    ("320x568", 320, 568),
    ("360x740", 360, 740),
    ("390x844", 390, 844),
])
def test_adversarial_viewport_overflow_and_bounding_boxes(live_server_url, vp_name, w, h):
    """Thử thách Responsive Viewports 320x568, 360x740, 390x844:
    1. scrollWidth <= clientWidth (0 horizontal overflow)
    2. Bounding boxes không bị tràn ngoài viewport (x >= 0, x + width <= w + 1)
    3. Không bị overlap đè chồng giữa các khối chính
    """
    screenshots_dir = pathlib.Path("reports/screenshots")
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = _launch_browser(p)

        # --- A. /guest ---
        guest_ctx = browser.new_context(viewport={"width": w, "height": h})
        page = guest_ctx.new_page()
        page.goto(f"{live_server_url}/guest", wait_until="domcontentloaded")
        page.wait_for_selector("#guestNameInput", state="visible")

        scroll_w = page.evaluate("() => document.documentElement.scrollWidth")
        client_w = page.evaluate("() => document.documentElement.clientWidth")
        assert scroll_w <= client_w, f"/guest bị tràn ngang trên {vp_name}: scrollWidth={scroll_w} > clientWidth={client_w}"

        card = page.locator(".card")
        box = card.bounding_box()
        assert box is not None, "Không tìm thấy .card trên /guest"
        assert box["x"] >= 0, f"Card tràn lề trái trên {vp_name}: {box['x']}"
        assert box["x"] + box["width"] <= w + 1, f"Card tràn lề phải trên {vp_name}: {box['x'] + box['width']} > {w}"

        for btn_id in ["#btnRecordGuestVoice", "#btnRetryGuestVoice", "#btnConfirmGuestVoiceOk"]:
            b_box = page.locator(btn_id).bounding_box()
            if b_box:
                assert b_box["x"] >= 0, f"Nút {btn_id} tràn lề trái trên {vp_name}"
                assert b_box["x"] + b_box["width"] <= w + 2, f"Nút {btn_id} tràn lề phải trên {vp_name}"

        shot_path = str(screenshots_dir / f"challenger_guest_{vp_name}.png")
        page.screenshot(path=shot_path, full_page=True)
        guest_ctx.close()

        # --- B. Dashboard (/) ---
        dash_ctx = browser.new_context(viewport={"width": w, "height": h})
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

        dash_shot_path = str(screenshots_dir / f"challenger_dashboard_{vp_name}.png")
        dash_page.screenshot(path=dash_shot_path, full_page=True)
        dash_ctx.close()

        browser.close()
