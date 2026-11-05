"""Bộ Kiểm Thử TDD Phase 7 — Guest QR Public Link (/guest), Minimal Mobile Page & Owner Dashboard QR.

Kiểm thử toàn diện theo phương pháp TDD:
1. Route công khai `/guest` (kèm tương thích ngược `/guest_enroll`, `/guest-qr` và `vercel.json`).
2. Trang di động độc lập tối giản `/guest`: Khách nhập Họ tên + Email và thu âm giọng nói,
   lưu quyền Khách Cấp 3 (Level 3 / CHILD_GUEST), không cần đăng nhập.
3. Chống leo quyền lên Cấp 1 và chống giả mạo email Chủ nhà (`nep94121@gmail.com`) từ trang khách.
4. Hiển thị mã QR và liên kết `/guest` trực tiếp trên Bảng điều khiển Chủ nhà (`/`).
5. Kiểm thử E2E Playwright trên viewport di động (390x844) cho `/guest` và Desktop (1280x800) cho `/`.
"""

from __future__ import annotations

import base64
import json
import pathlib
import socket
import sys
import threading
import time

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import numpy as np
import pytest
import uvicorn

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.auth_3layer import get_auth_3layer_manager
from simulator.server import _ACTIVE_BRIDGES, _BOOT_VOICE_AUTH, _REST_ENGINE, app


@pytest.fixture(autouse=True)
def reset_guest_test_state():
    """Khôi phục trạng thái sạch trước và sau mỗi bài kiểm thử."""
    mgr = get_auth_3layer_manager()
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    yield
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    # Dọn các tài khoản khách thử nghiệm để không làm bẩn file accounts_3layer.json
    mgr.accounts = [
        acc for acc in mgr.accounts
        if not str(acc.get("email", "")).endswith(".p7guest@gmail.com")
    ]
    mgr._save_accounts()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _make_valid_guest_pcm_b64(f0_hz: float = 235.0, duration_sec: float = 2.8) -> str:
    """Sinh mẫu âm thanh PCM 16kHz đạt chuẩn kiểm định chất lượng âm học."""
    sr = 16000
    n_silence = int(sr * 0.3)
    n_voice = int(sr * (duration_sec - 0.3))
    silence = np.zeros(n_silence, dtype=np.float32)
    t = np.linspace(0, duration_sec - 0.3, n_voice, endpoint=False)
    voice = (
        0.40 * np.sin(2 * np.pi * f0_hz * t)
        + 0.20 * np.sin(2 * np.pi * (f0_hz * 2) * t)
        + 0.10 * np.sin(2 * np.pi * (f0_hz * 3) * t)
    )
    sig = np.concatenate([silence, voice])
    pcm16 = (sig * 32767).astype(np.int16)
    return base64.b64encode(pcm16.tobytes()).decode("utf-8")


# ==============================================================================
# 1. ROUTE /guest, VERCEL.JSON & GIAO DIỆN MOBILE TỐI GIẢN ĐỘC LẬP
# ==============================================================================

def test_route_guest_and_vercel_rewrite_configured(client: TestClient) -> None:
    """Route /guest phải trả về HTTP 200 HTML và được khai báo trong vercel.json."""
    res_guest = client.get("/guest", headers={"Accept": "text/html"})
    assert res_guest.status_code == 200
    assert "text/html" in res_guest.headers.get("content-type", "")

    # Đảm bảo tương thích ngược cho /guest_enroll và /guest-qr
    assert client.get("/guest_enroll", headers={"Accept": "text/html"}).status_code == 200
    assert client.get("/guest-qr", headers={"Accept": "text/html"}).status_code == 200

    vercel_cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    route_srcs = [r.get("src", "") for r in vercel_cfg.get("routes", [])]
    assert any("/guest" in src and "guest_enroll" not in src for src in route_srcs), (
        "vercel.json chưa có route rewrite cho /guest!"
    )


def test_guest_page_is_clean_minimal_mobile_without_login(client: TestClient) -> None:
    """Trang /guest phải tối giản: chỉ hiển thị ô Họ tên, Email, nút Thu âm và nút Xác nhận Cấp 3."""
    res = client.get("/guest", headers={"Accept": "text/html"})
    assert res.status_code == 200
    soup = BeautifulSoup(res.text, "html.parser")

    name_input = soup.find(id="guestNameInput")
    email_input = soup.find(id="guestOptionalEmailInput")
    rec_btn = soup.find(id="btnRecordGuestVoice")
    confirm_btn = soup.find(id="btnConfirmGuestVoiceOk")

    assert name_input is not None, "Thiếu ô nhập tên #guestNameInput"
    assert email_input is not None, "Thiếu ô nhập email #guestOptionalEmailInput"
    assert rec_btn is not None, "Thiếu nút thu âm #btnRecordGuestVoice"
    assert confirm_btn is not None, "Thiếu nút lưu kích hoạt #btnConfirmGuestVoiceOk"

    # Không điền sẵn tên/email mẫu trong ô nhập của khách
    assert (name_input.get("value") or "").strip() == "", "Ô tên khách không được điền sẵn giá trị cứng!"
    assert (email_input.get("value") or "").strip() == "", "Ô email khách không được điền sẵn giá trị cứng!"

    # Các phần tử quản trị/rườm rà (chọn cấp 2, danh sách thu hồi, QR trên trang khách) phải được ẩn
    for legacy_id in ("guestTierSelect", "guestListContainer"):
        el = soup.find(id=legacy_id)
        if el is not None:
            is_hidden = el.has_attr("hidden") or any(p.has_attr("hidden") for p in el.parents)
            assert is_hidden, f"Phần tử #{legacy_id} phải được ẩn trên trang /guest tối giản!"


# ==============================================================================
# 2. API QR SINH LINK /guest & LƯU KHÁCH CẤP 3 (TÊN + EMAIL + GIỌNG NÓI)
# ==============================================================================

def test_guest_qr_current_returns_public_guest_link(client: TestClient) -> None:
    """API /api/auth3/guest_qr_current trả về public_guest_url (/guest) và SVG QR hợp lệ."""
    res = client.get("/api/auth3/guest_qr_current?duration=1d&host=localhost:8088")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data.get("public_guest_path") == "/guest"
    assert str(data.get("public_guest_url", "")).endswith("/guest")
    assert str(data.get("guest_url", "")).startswith("/guest?token=")
    # Bảo toàn qr_url cho các bài test M2 cũ
    assert "/guest_enroll?token=" in data["qr_url"]
    assert "<svg" in data["qr_svg"] and "</svg>" in data["qr_svg"]


def test_guest_enroll_name_email_and_voice_saved_as_level3_no_login(client: TestClient) -> None:
    """Khách nhập Họ tên + Email và thu âm giọng nói trên /guest được lưu thành công ở Cấp 3, không cần login."""
    b64_pcm = _make_valid_guest_pcm_b64(f0_hz=238.0)
    guest_name = "Lê Hoàng Khách P7"
    guest_email = "lehoang.p7guest@gmail.com"

    res = client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "guest_name": guest_name,
            "guest_email": guest_email,
            "target_tier": 3,
            "duration": "1d",
            "audio_pcm_b64": b64_pcm,
        },
    )
    assert res.status_code == 200, f"Lỗi lưu giọng khách kèm email: {res.text}"
    data = res.json()
    assert data["ok"] is True
    assert data["status"] == "DA_DAT"
    assert data["tier"] == 3
    assert data["guest_name"] == guest_name
    assert data["guest_email"] == guest_email
    assert data["account"]["tier"] == 3
    assert data["account"]["role"] == "CHILD_GUEST"
    assert data["account"]["email"] == guest_email
    assert data["account"]["name"] == guest_name

    # Kiểm tra tài khoản đã được lưu vào Auth3LayerManager ở Cấp 3
    mgr = get_auth_3layer_manager()
    saved_acc = mgr.find_account(guest_email)
    assert saved_acc is not None, "Tài khoản khách chưa được lưu vào Auth3LayerManager!"
    assert saved_acc["tier"] == 3
    assert saved_acc["role"] == "CHILD_GUEST"
    assert saved_acc["display_name"] == guest_name
    assert saved_acc.get("voice_verified") is True
    assert saved_acc.get("voiceprint", {}).get("enrolled") is True

    # Kiểm tra quyền thiết bị trên _REST_ENGINE cho khách Cấp 3
    user_key = next((k for k, u in _REST_ENGINE.users.items() if u.get("name") == guest_name), None)
    assert user_key is not None, "Khách chưa được cấp quyền trong _REST_ENGINE!"
    assert _REST_ENGINE.users[user_key]["tier"] == 3
    assert _REST_ENGINE.users[user_key]["active"] is True


def test_guest_cannot_spoof_owner_email_or_escalate_to_tier1(client: TestClient) -> None:
    """Chặn khách dùng email Chủ nhà (nep94121@gmail.com) hoặc tự nâng quyền lên Cấp 1."""
    b64_pcm = _make_valid_guest_pcm_b64(f0_hz=242.0)

    # 1. Cố tình gửi email Chủ nhà
    res_owner_email = client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "guest_name": "Kẻ Giả Mạo",
            "guest_email": "nep94121@gmail.com",
            "target_tier": 3,
            "audio_pcm_b64": b64_pcm,
        },
    )
    assert res_owner_email.status_code == 400
    assert res_owner_email.json()["ok"] is False

    # 2. Cố tình gửi target_tier=1 với email khách -> Hệ thống phải ép về Cấp 3
    res_tier1 = client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "guest_name": "Khách Thử Leo Quyền",
            "guest_email": "escalate.p7guest@gmail.com",
            "target_tier": 1,
            "audio_pcm_b64": b64_pcm,
        },
    )
    assert res_tier1.status_code == 200
    assert res_tier1.json()["tier"] == 3
    assert res_tier1.json()["account"]["tier"] == 3


# ==============================================================================
# 3. HIỂN THỊ MÃ QR CỦA LINK /guest TRÊN OWNER DASHBOARD (/)
# ==============================================================================

def test_owner_dashboard_shows_guest_qr_panel(client: TestClient) -> None:
    """Trang Bảng điều khiển Chủ nhà (/) phải hiển thị khung Mã QR dẫn tới /guest."""
    res = client.get("/", headers={"Accept": "text/html"})
    assert res.status_code == 200
    soup = BeautifulSoup(res.text, "html.parser")

    qr_panel = soup.find(id="ownerGuestQrPanel")
    qr_box = soup.find(id="ownerDashboardQrBox")
    link_text = soup.find(id="ownerGuestLinkText")
    open_link = soup.find(id="ownerGuestOpenLink")

    assert qr_panel is not None, "Trang chủ (/) thiếu #ownerGuestQrPanel"
    assert qr_box is not None, "Trang chủ (/) thiếu #ownerDashboardQrBox"
    assert link_text is not None, "Trang chủ (/) thiếu #ownerGuestLinkText"
    assert open_link is not None, "Trang chủ (/) thiếu #ownerGuestOpenLink"
    assert "/guest" in (open_link.get("href") or ""), "#ownerGuestOpenLink phải trỏ tới /guest"


# ==============================================================================
# 4. KIỂM THỬ E2E PLAYWRIGHT TRÊN TRÌNH DUYỆT THẬT (MOBILE /guest & DESKTOP /)
# ==============================================================================

def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_playwright_e2e_guest_mobile_and_owner_dashboard_qr() -> None:
    """Kiểm thử Playwright E2E:
    1. Owner Dashboard (/) hiển thị SVG QR của link /guest.
    2. Khách mở /guest trên màn hình di động (390x844), nhập Tên + Email, thu âm giọng nói
       và lưu thành công quyền Khách Cấp 3 không cần đăng nhập, 0 lỗi console.
    """
    from playwright.sync_api import sync_playwright

    port = _get_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(40):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="msedge", headless=True)
            except Exception:
                browser = p.chromium.launch(headless=True)

            # A. Kiểm tra QR trên Owner Dashboard (/)
            owner_ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            owner_page = owner_ctx.new_page()
            owner_errors: list[str] = []
            owner_page.on("pageerror", lambda err: owner_errors.append(str(err)))

            owner_page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=15000)
            owner_page.wait_for_selector("#ownerDashboardQrBox svg", timeout=10000)

            qr_svg_box = owner_page.locator("#ownerDashboardQrBox svg").bounding_box()
            assert qr_svg_box is not None and qr_svg_box["width"] >= 60 and qr_svg_box["height"] >= 60
            link_txt = owner_page.locator("#ownerGuestLinkText").inner_text()
            assert "/guest" in link_txt
            assert not owner_errors, f"Lỗi JS trên trang chủ (/): {owner_errors}"
            owner_ctx.close()

            # B. Kiểm tra luồng Khách trên trang di động tối giản (/guest)
            guest_ctx = browser.new_context(viewport={"width": 390, "height": 844})
            guest_page = guest_ctx.new_page()
            guest_errors: list[str] = []
            guest_console_errs: list[str] = []
            guest_page.on("pageerror", lambda err: guest_errors.append(str(err)))
            guest_page.on(
                "console",
                lambda msg: guest_console_errs.append(msg.text) if msg.type == "error" else None,
            )

            guest_page.goto(f"{base_url}/guest", wait_until="domcontentloaded", timeout=15000)
            guest_page.wait_for_selector("#guestNameInput", state="visible", timeout=10000)

            # Kiểm tra responsive mobile: không tràn ngang
            overflow_x = guest_page.evaluate(
                "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
            )
            assert overflow_x is False, "Trang /guest bị tràn chiều ngang trên màn hình mobile 390px!"

            # Khách nhập Họ tên + Email
            guest_page.fill("#guestNameInput", "Phạm Minh Khách")
            guest_page.fill("#guestOptionalEmailInput", "phamminh.p7guest@gmail.com")

            # Khách bấm nút thu âm giọng nói
            guest_page.click("#btnRecordGuestVoice")
            guest_page.wait_for_function(
                "() => !document.getElementById('btnConfirmGuestVoiceOk').disabled",
                timeout=10000,
            )

            # Khách bấm nút Xác nhận & Kích hoạt
            guest_page.click("#btnConfirmGuestVoiceOk")

            status_text = guest_page.locator("#handshakeStatus").inner_text()
            assert "Phạm Minh Khách" in status_text
            assert "Cấp 3" in status_text
            assert "phamminh.p7guest@gmail.com" in status_text

            assert not guest_errors, f"Lỗi pageerror trên /guest: {guest_errors}"
            assert not guest_console_errs, f"Lỗi console.error trên /guest: {guest_console_errs}"

            guest_ctx.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=3)
        for br in list(_ACTIVE_BRIDGES):
            try:
                br._closed = True
            except Exception:
                pass
        _ACTIVE_BRIDGES.clear()
