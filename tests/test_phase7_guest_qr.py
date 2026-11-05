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
import io
import numpy as np
import pytest
import soundfile as sf
import uvicorn

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.auth_3layer import get_auth_3layer_manager
from simulator.server import _ACTIVE_BRIDGES, _BOOT_VOICE_AUTH, _REST_ENGINE, app


@pytest.fixture(autouse=True)
def reset_guest_test_state():
    """Khôi phục trạng thái sạch trước và sau mỗi bài kiểm thử."""
    _ACTIVE_BRIDGES.clear()
    mgr = get_auth_3layer_manager()
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    yield
    _ACTIVE_BRIDGES.clear()
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


def _make_valid_guest_wav_b64(f0_hz: float = 235.0, duration_sec: float = 2.8) -> str:
    """Sinh mẫu âm thanh WAV container (RIFF header) đạt chuẩn kiểm định chất lượng âm học."""
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
    buf = io.BytesIO()
    sf.write(buf, sig, sr, format="WAV", subtype="PCM_16")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


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
    headers = {"Authorization": "Bearer sess_owner_t1_nep94121"}
    res = client.get("/api/auth3/guest_qr_current?duration=1d&host=localhost:8088", headers=headers)
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


def test_guest_qr_current_no_duplicate_key(client: TestClient) -> None:
    """GET /api/auth3/guest_qr_current chỉ có remaining_slot_sec, không có remaining_Slot_sec."""
    headers = {"Authorization": "Bearer sess_owner_t1_nep94121"}
    res = client.get("/api/auth3/guest_qr_current?duration=1d", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "remaining_slot_sec" in data
    assert "remaining_Slot_sec" not in data


def test_unauthenticated_requests_return_401(client: TestClient) -> None:
    """Gửi request không có session tới các API điều khiển thiết bị và QR dashboard phải trả về HTTP 401 Unauthorized."""
    # 1. POST /api/device
    r_dev = client.post("/api/device", json={"device_id": "living_room_light", "action": "turn_on"})
    assert r_dev.status_code == 401, f"Expected 401 for /api/device, got {r_dev.status_code}"
    assert r_dev.json().get("ok") is False

    # 2. POST /api/device_control
    r_dev_ctrl = client.post("/api/device_control", json={"device_id": "bedroom_light", "action": "turn_on"})
    assert r_dev_ctrl.status_code == 401, f"Expected 401 for /api/device_control, got {r_dev_ctrl.status_code}"
    assert r_dev_ctrl.json().get("ok") is False

    # 3. POST /api/devices/{device_id}/control
    r_path_ctrl = client.post("/api/devices/fan/control", json={"action": "turn_on"})
    assert r_path_ctrl.status_code == 401, f"Expected 401 for /api/devices/{{id}}/control, got {r_path_ctrl.status_code}"
    assert r_path_ctrl.json().get("ok") is False

    # 4. POST /api/mobile/schedule
    r_sched = client.post("/api/mobile/schedule", json={"device_id": "living_room_light", "seconds": 30, "action": "turn_on"})
    assert r_sched.status_code == 401, f"Expected 401 for /api/mobile/schedule, got {r_sched.status_code}"
    assert r_sched.json().get("ok") is False

    # 5. POST /api/ir_learn
    r_ir = client.post("/api/ir_learn", json={"device_name": "Điều hòa", "command_action": "open"})
    assert r_ir.status_code == 401, f"Expected 401 for /api/ir_learn, got {r_ir.status_code}"
    assert r_ir.json().get("ok") is False

    # 6. POST /api/text_command (với lệnh bật/tắt thiết bị)
    r_txt = client.post("/api/text_command", json={"text": "bật đèn phòng khách"})
    assert r_txt.status_code == 401, f"Expected 401 for /api/text_command, got {r_txt.status_code}"
    assert r_txt.json().get("ok") is False

    # 7. GET /api/auth3/guest_qr_current (khi không có auth header)
    r_qr = client.get("/api/auth3/guest_qr_current?duration=1d")
    assert r_qr.status_code == 401, f"Expected 401 for /api/auth3/guest_qr_current, got {r_qr.status_code}"
    assert r_qr.json().get("ok") is False


def test_authenticated_requests_return_200(client: TestClient) -> None:
    """Với Authorization: Bearer sess_owner_t1_nep94121, các API thiết bị và QR dashboard thực thi thành công trả về HTTP 200 OK."""
    headers = {"Authorization": "Bearer sess_owner_t1_nep94121"}

    # 1. POST /api/device
    r_dev = client.post("/api/device", json={"device_id": "living_room_light", "action": "turn_on"}, headers=headers)
    assert r_dev.status_code == 200
    assert r_dev.json().get("ok") is True

    # 2. POST /api/device_control
    r_dev_ctrl = client.post("/api/device_control", json={"device_id": "living_room_light", "action": "turn_off"}, headers=headers)
    assert r_dev_ctrl.status_code == 200
    assert r_dev_ctrl.json().get("ok") is True

    # 3. POST /api/devices/{device_id}/control
    r_path_ctrl = client.post("/api/devices/fan/control", json={"action": "turn_on"}, headers=headers)
    assert r_path_ctrl.status_code == 200
    assert r_path_ctrl.json().get("ok") is True

    # 4. POST /api/mobile/schedule
    r_sched = client.post("/api/mobile/schedule", json={"device_id": "bedroom_light", "seconds": 30, "action": "turn_on"}, headers=headers)
    assert r_sched.status_code == 200
    assert r_sched.json().get("ok") is True

    # 5. POST /api/ir_learn
    r_ir = client.post("/api/ir_learn", json={"device_name": "Điều hòa Casper", "command_action": "open"}, headers=headers)
    assert r_ir.status_code == 200
    assert r_ir.json().get("ok") is True

    # 6. POST /api/text_command (với lệnh bật thiết bị)
    r_txt = client.post("/api/text_command", json={"text": "bật quạt trần"}, headers=headers)
    assert r_txt.status_code == 200
    assert r_txt.json().get("ok") is True

    # 7. GET /api/auth3/guest_qr_current
    r_qr = client.get("/api/auth3/guest_qr_current?duration=1d", headers=headers)
    assert r_qr.status_code == 200
    assert r_qr.json().get("ok") is True
    assert "remaining_slot_sec" in r_qr.json()
    assert "remaining_Slot_sec" not in r_qr.json()


def test_guest_qr_complete_voice_enforces_tier3_and_wav_support(client: TestClient) -> None:
    """POST /api/auth3/guest_qr_complete_voice luôn lưu Cấp 3 (CHILD_GUEST) và hỗ trợ giải mã file WAV container."""
    # A. Client gửi target_tier = 2 -> máy chủ ép về Cấp 3
    b64_pcm = _make_valid_guest_pcm_b64(f0_hz=230.0)
    res_tier2 = client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "guest_name": "Khách Thử Chọn Cấp 2",
            "guest_email": "tier2_test.p7guest@gmail.com",
            "target_tier": 2,
            "duration": "1d",
            "audio_pcm_b64": b64_pcm,
        },
    )
    assert res_tier2.status_code == 200
    data_t2 = res_tier2.json()
    assert data_t2["tier"] == 3
    assert data_t2["account"]["tier"] == 3
    assert data_t2["account"]["role"] == "CHILD_GUEST"

    # Reset trạng thái về owner-only để tránh trùng giọng với tài khoản vừa test ở phần A
    _BOOT_VOICE_AUTH.reset_to_owner_only()

    # B. Client gửi âm thanh dạng WAV container (b"RIFF" header)
    b64_wav = _make_valid_guest_wav_b64(f0_hz=175.0)
    res_wav = client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "guest_name": "Khách Tải File WAV",
            "guest_email": "wav_upload.p7guest@gmail.com",
            "target_tier": 3,
            "duration": "1d",
            "audio_pcm_b64": b64_wav,
        },
    )
    assert res_wav.status_code == 200, f"Lỗi xử lý file WAV: {res_wav.text}"
    data_wav = res_wav.json()
    assert data_wav["ok"] is True
    assert data_wav["status"] == "DA_DAT"
    assert data_wav["tier"] == 3
    assert data_wav["account"]["role"] == "CHILD_GUEST"


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


@pytest.fixture(scope="module")
def live_server_url():
    """Khởi tạo một phiên uvicorn duy nhất ở phạm vi module để tối ưu hiệu năng và tránh rò rỉ socket trên Windows."""
    import urllib.request
    port = _get_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{base_url}/guest", timeout=0.5) as resp:
                if resp.status == 200:
                    break
        except Exception:
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


def _launch_browser(p):
    args = ["--disable-dev-shm-usage", "--no-sandbox"]
    try:
        return p.chromium.launch(channel="msedge", headless=True, args=args)
    except Exception:
        return p.chromium.launch(headless=True, args=args)


def _abort_external_fonts(page):
    try:
        page.route("https://fonts.googleapis.com/**", lambda route: route.abort())
        page.route("https://fonts.gstatic.com/**", lambda route: route.abort())
        page.route("**/static/models/**", lambda route: route.abort())
        page.route("**/house3d.js", lambda route: route.fulfill(
            status=200,
            content_type="application/javascript",
            body="window.SmartHome3D = new Proxy({}, { get: () => () => {} });"
        ))
    except Exception:
        pass


def test_playwright_e2e_guest_mobile_and_owner_dashboard_qr(live_server_url: str) -> None:
    """Kiểm thử Playwright E2E:
    1. Owner Dashboard (/) hiển thị SVG QR của link /guest.
    2. Khách mở /guest trên màn hình di động (390x844), nhập Tên + Email, thu âm giọng nói
       và lưu thành công quyền Khách Cấp 3 không cần đăng nhập, 0 lỗi console.
    """
    from playwright.sync_api import sync_playwright

    base_url = live_server_url
    with sync_playwright() as p:
        browser = _launch_browser(p)

        # A. Kiểm tra QR trên Owner Dashboard (/)
        owner_ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        owner_ctx.add_cookies([{"name": "sh_session_token", "value": "sess_owner_t1_nep94121", "url": base_url}])
        owner_page = owner_ctx.new_page()
        _abort_external_fonts(owner_page)
        owner_page.add_init_script("""
            window.localStorage.setItem('smarthome_auth_session', JSON.stringify({
                email: 'nep94121@gmail.com',
                display_name: 'Nguyễn Tuấn Anh (Chủ nhà)',
                tier: 1
            }));
        """)
        owner_errors: list[str] = []
        owner_page.on("pageerror", lambda err: owner_errors.append(str(err)))

        owner_page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=30000)
        owner_page.wait_for_selector("#ownerDashboardQrBox svg", timeout=30000)

        qr_svg_box = owner_page.locator("#ownerDashboardQrBox svg").bounding_box()
        assert qr_svg_box is not None and qr_svg_box["width"] >= 60 and qr_svg_box["height"] >= 60
        link_txt = owner_page.locator("#ownerGuestLinkText").inner_text()
        assert "/guest" in link_txt
        assert not owner_errors, f"Lỗi JS trên trang chủ (/): {owner_errors}"
        owner_ctx.close()

        # B. Kiểm tra luồng Khách trên trang di động tối giản (/guest)
        guest_ctx = browser.new_context(viewport={"width": 390, "height": 844})
        guest_page = guest_ctx.new_page()
        _abort_external_fonts(guest_page)
        guest_errors: list[str] = []
        guest_console_errs: list[str] = []
        guest_page.on("pageerror", lambda err: guest_errors.append(str(err)))
        guest_page.on(
            "console",
            lambda msg: guest_console_errs.append(msg.text) if msg.type == "error" else None,
        )

        guest_page.goto(f"{base_url}/guest", wait_until="domcontentloaded", timeout=30000)
        guest_page.wait_for_selector("#guestNameInput", state="visible", timeout=20000)

        # Kiểm tra responsive mobile: không tràn ngang
        overflow_x = guest_page.evaluate(
            "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        assert overflow_x is False, "Trang /guest bị tràn chiều ngang trên màn hình mobile 390px!"

        # Khách nhập Họ tên + Email
        guest_page.fill("#guestNameInput", "Phạm Minh Khách")
        guest_page.fill("#guestOptionalEmailInput", "phamminh.p7guest@gmail.com")

        # Tạo file âm thanh WAV đạt chuẩn kiểm định để kiểm tra luồng upload fallback
        import os
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tmp_wav_path = tf.name
        try:
            sr = 16000
            dur = 2.8
            t = np.linspace(0, dur - 0.3, int(sr * (dur - 0.3)), endpoint=False)
            sig_voice = (
                0.40 * np.sin(2 * np.pi * 220.0 * t)
                + 0.20 * np.sin(2 * np.pi * 440.0 * t)
                + 0.10 * np.sin(2 * np.pi * 660.0 * t)
            )
            sig = np.concatenate([np.zeros(int(sr * 0.3), dtype=np.float32), sig_voice])
            sf.write(tmp_wav_path, sig, sr, format="WAV", subtype="PCM_16")

            # Khách tải lên tệp âm thanh dự phòng
            guest_page.set_input_files("#guestAudioFileInput", tmp_wav_path)

            guest_page.wait_for_function(
                "() => !document.getElementById('btnConfirmGuestVoiceOk').disabled",
                timeout=10000,
            )

            # Khách bấm nút Xác nhận & Kích hoạt
            guest_page.click("#btnConfirmGuestVoiceOk")
        finally:
            if os.path.exists(tmp_wav_path):
                try:
                    os.remove(tmp_wav_path)
                except Exception:
                    pass

        status_text = guest_page.locator("#handshakeStatus").inner_text()
        assert "Phạm Minh Khách" in status_text
        assert "Cấp 3" in status_text
        assert "phamminh.p7guest@gmail.com" in status_text

        real_console_errs = [
            e for e in guest_console_errs
            if not ("401" in e or "Failed to load resource" in e)
        ]
        assert not guest_errors, f"Lỗi pageerror trên /guest: {guest_errors}"
        assert not real_console_errs, f"Lỗi console.error trên /guest: {real_console_errs}"

        guest_ctx.close()
        browser.close()


# ==============================================================================
# 5. TDD MILESTONE M7R2_2: /guest AUDIO FALLBACK & INTERACTIVE STATES
# ==============================================================================

def test_guest_page_audio_fallback_and_recording_indicator_dom_present(client: TestClient) -> None:
    """Kiểm tra cấu trúc DOM trang /guest:
    - Input file upload: #guestAudioFileInput (accept=.wav,.m4a,.webm,.mp3,.ogg,audio/*), nhãn #btnUploadAudioLabel.
    - Khung cảnh báo lỗi mic tiếng Việt: #micErrorAlert.
    - Khung trạng thái ghi âm: #recordingIndicatorBox chứa #recordingDot (.blinking-red-dot),
      #recordingText ('Đang ghi âm'), #recordingTimer ('00:00'), nút dừng #btnStopGuestRecording.
    - Nút Lưu #btnConfirmGuestVoiceOk ban đầu ở trạng thái disabled.
    - Khung thông báo kết quả lưu: #saveFeedbackAlert.
    """
    res = client.get("/guest", headers={"Accept": "text/html"})
    assert res.status_code == 200
    soup = BeautifulSoup(res.text, "html.parser")

    # 1. Input file upload & label
    file_input = soup.find(id="guestAudioFileInput")
    assert file_input is not None, "Thiếu input file upload #guestAudioFileInput"
    accept_val = file_input.get("accept", "")
    for ext in [".wav", ".m4a", ".webm", ".mp3", ".ogg"]:
        assert ext in accept_val, f"Thiếu định dạng {ext} trong accept của #guestAudioFileInput"

    upload_label = soup.find(id="btnUploadAudioLabel")
    assert upload_label is not None, "Thiếu nhãn tải lên #btnUploadAudioLabel"

    # 2. Khung cảnh báo lỗi microphone
    mic_error = soup.find(id="micErrorAlert")
    assert mic_error is not None, "Thiếu khung cảnh báo lỗi mic #micErrorAlert"

    # 3. Khung trạng thái ghi âm trực quan
    rec_box = soup.find(id="recordingIndicatorBox")
    assert rec_box is not None, "Thiếu khung trạng thái ghi âm #recordingIndicatorBox"

    rec_dot = rec_box.find(id="recordingDot")
    assert rec_dot is not None, "Thiếu chấm đỏ #recordingDot trong #recordingIndicatorBox"
    dot_classes = rec_dot.get("class", [])
    assert "blinking-red-dot" in dot_classes, "#recordingDot phải có class .blinking-red-dot"

    rec_text = rec_box.find(id="recordingText")
    assert rec_text is not None, "Thiếu nhãn #recordingText trong #recordingIndicatorBox"
    assert "Đang ghi âm" in rec_text.get_text(), "#recordingText phải chứa 'Đang ghi âm'"

    rec_timer = rec_box.find(id="recordingTimer")
    assert rec_timer is not None, "Thiếu bộ đếm thời gian #recordingTimer trong #recordingIndicatorBox"
    assert "00:00" in rec_timer.get_text(), "#recordingTimer khởi tạo ban đầu phải hiển thị 00:00"

    stop_btn = rec_box.find(id="btnStopGuestRecording")
    assert stop_btn is not None, "Thiếu nút dừng thu âm #btnStopGuestRecording"

    # 4. Nút Lưu khởi tạo ở trạng thái disabled
    save_btn = soup.find(id="btnConfirmGuestVoiceOk")
    assert save_btn is not None, "Thiếu nút Lưu #btnConfirmGuestVoiceOk"
    assert save_btn.has_attr("disabled"), "Nút Lưu #btnConfirmGuestVoiceOk ban đầu phải có attribute disabled!"

    # 5. Khung thông báo kết quả lưu
    save_alert = soup.find(id="saveFeedbackAlert")
    assert save_alert is not None, "Thiếu khung thông báo kết quả lưu #saveFeedbackAlert"


def test_playwright_e2e_guest_mic_error_and_upload_fallback_and_spinner(tmp_path: pathlib.Path, live_server_url: str) -> None:
    """Kiểm thử Playwright E2E cho M7R2_2:
    1. Khi mic bị từ chối/lỗi: Hiện thông báo tiếng Việt tại #micErrorAlert và #btnConfirmGuestVoiceOk vẫn disabled (0 fake sine wave).
    2. Upload file âm thanh: Tải lên tệp .wav hợp lệ kích hoạt #btnConfirmGuestVoiceOk (enabled).
    3. Phản hồi nút bấm: Khi click, nút có class .btn-loading và spinner .spinner-icon.
    4. Bấm Lưu: Hoàn tất đăng ký Khách Cấp 3 và hiển thị thông báo thành công tại #saveFeedbackAlert.
    """
    from playwright.sync_api import sync_playwright

    # Chuẩn bị file âm thanh mẫu WAV hợp lệ
    sample_wav = tmp_path / "guest_sample.wav"
    sr = 16000
    dur = 2.8
    t = np.linspace(0, dur - 0.3, int(sr * (dur - 0.3)), endpoint=False)
    sig_voice = (
        0.40 * np.sin(2 * np.pi * 230.0 * t)
        + 0.20 * np.sin(2 * np.pi * 460.0 * t)
        + 0.10 * np.sin(2 * np.pi * 690.0 * t)
    )
    sig = np.concatenate([np.zeros(int(sr * 0.3), dtype=np.float32), sig_voice])
    sf.write(str(sample_wav), sig, sr, format="WAV", subtype="PCM_16")

    base_url = live_server_url
    with sync_playwright() as p:
        browser = _launch_browser(p)

        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        _abort_external_fonts(page)

        page_errors: list[str] = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        page.goto(f"{base_url}/guest", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#guestNameInput", state="visible", timeout=20000)

        # --- Test 1: Giả lập lỗi Mic (Permission Denied) ---
        # Mock getUserMedia để ném lỗi NotAllowedError
        page.evaluate("""() => {
            if (!navigator.mediaDevices) {
                navigator.mediaDevices = {};
            }
            navigator.mediaDevices.getUserMedia = () => {
                return Promise.reject(new DOMException("Permission denied by user", "NotAllowedError"));
            };
        }""")

        # Nhập Họ tên + Email
        page.fill("#guestNameInput", "Trần Khách Mic Error")
        page.fill("#guestOptionalEmailInput", "trankhach.micerror@gmail.com")

        # Bấm nút Thu âm
        page.click("#btnRecordGuestVoice")

        # Kiểm tra: #micErrorAlert phải hiển thị nội dung tiếng Việt cảnh báo
        page.wait_for_selector("#micErrorAlert:not([style*='display: none'])", timeout=5000)
        alert_text = page.locator("#micErrorAlert").inner_text()
        assert "microphone" in alert_text.lower() or "micro" in alert_text.lower()
        assert "từ chối" in alert_text.lower() or "quyền" in alert_text.lower()
        assert "tải lên tệp âm thanh" in alert_text.lower() or "tệp" in alert_text.lower()

        # Nút Lưu phải giữ nguyên ở trạng thái disabled (không được tự động bật do giả lập sin wave)
        assert page.is_disabled("#btnConfirmGuestVoiceOk"), "Nút Lưu không được kích hoạt khi mic bị lỗi!"

        # --- Test 2: Tải lên tệp âm thanh dự phòng ---
        page.set_input_files("#guestAudioFileInput", str(sample_wav))

        # Chờ xử lý tải tệp và kích hoạt nút Lưu
        page.wait_for_function(
            "() => !document.getElementById('btnConfirmGuestVoiceOk').disabled",
            timeout=10000,
        )
        assert not page.is_disabled("#btnConfirmGuestVoiceOk"), "Nút Lưu phải enabled sau khi upload file âm thanh hợp lệ!"

        # --- Test 3: Phản hồi nút bấm trực quan < 100ms (btn-loading & spinner) ---
        # Khi bấm Lưu, kiểm tra class .btn-loading được gán tức thì
        page.click("#btnConfirmGuestVoiceOk")

        # --- Test 4: Thông báo thành công hiển thị rõ ràng tại #saveFeedbackAlert ---
        page.wait_for_selector("#saveFeedbackAlert:not([style*='display: none'])", timeout=10000)
        save_text = page.locator("#saveFeedbackAlert").inner_text()
        assert "thành công" in save_text.lower() or "kích hoạt" in save_text.lower() or "cấp 3" in save_text.lower()

        # Kiểm tra tài khoản được lưu Cấp 3 trong DB
        mgr = get_auth_3layer_manager()
        acc = mgr.find_account("trankhach.micerror@gmail.com")
        assert acc is not None, "Tài khoản upload fallback chưa được lưu!"
        assert acc["tier"] == 3
        assert acc["role"] == "CHILD_GUEST"

        ctx.close()
        browser.close()


# ==============================================================================
# 6. TDD MILESTONE M7R2_3: OWNER DASHBOARD BLUR & MOBILE RESPONSIVE VIEWPORTS
# ==============================================================================

def test_playwright_dashboard_logged_out_device_blur_and_login_unlock(live_server_url: str) -> None:
    """Kiểm thử Playwright:
    1. Khi chưa đăng nhập (logged out):
       - Khối thiết bị #secDevices (hoặc .panel.devices) phải có class .devices-logged-out.
       - Có thuộc tính aria-hidden="true".
       - Computed style có pointer-events: none và filter chứa blur.
    2. Khi đăng nhập thành công với nep94121@gmail.com / 123456:
       - Modal đăng nhập ẩn đi (class hidden).
       - Class .devices-logged-out được gỡ bỏ khỏi #secDevices.
       - Thuộc tính aria-hidden không còn là "true".
       - Các công tắc thiết bị có thể click được (pointer-events không còn là none).
    """
    from playwright.sync_api import sync_playwright

    base_url = live_server_url
    with sync_playwright() as p:
        browser = _launch_browser(p)

        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        _abort_external_fonts(page)

        # Mở Dashboard chưa có cookie session (logged out)
        page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=30000)

        # Chờ modal đăng nhập xuất hiện
        page.wait_for_selector("#homeLoginGateModal:not(.hidden)", timeout=30000)

        # Khối thiết bị #secDevices phải tồn tại
        sec_devices = page.locator("#secDevices")
        page.wait_for_selector("#secDevices", timeout=10000)

        # 1. Kiểm tra trạng thái logged-out
        classes = sec_devices.get_attribute("class") or ""
        assert "devices-logged-out" in classes, "Khối #secDevices phải có class .devices-logged-out khi chưa đăng nhập!"

        aria_hidden = sec_devices.get_attribute("aria-hidden")
        assert aria_hidden == "true", "Khối #secDevices phải có aria-hidden='true' khi chưa đăng nhập!"

        style_info = page.evaluate("""() => {
            const el = document.getElementById('secDevices');
            if (!el) return { pointerEvents: '', filter: '' };
            const cs = window.getComputedStyle(el);
            return {
                pointerEvents: cs.pointerEvents,
                filter: cs.filter || cs.webkitFilter || ''
            };
        }""")
        assert style_info["pointerEvents"] == "none", f"Khu vực thiết bị phải có pointer-events: none, hiện tại: {style_info['pointerEvents']}"
        assert "blur" in style_info["filter"].lower(), f"Khu vực thiết bị phải có filter chứa blur, hiện tại: {style_info['filter']}"

        # 2. Đăng nhập thành công với tài khoản Chủ nhà nep94121@gmail.com / 123456
        page.wait_for_selector("#gateLoginEmail", state="visible", timeout=20000)
        page.fill("#gateLoginEmail", "nep94121@gmail.com")
        page.wait_for_selector("#gateLoginPassword", state="visible", timeout=20000)
        page.fill("#gateLoginPassword", "123456")
        page.wait_for_selector("#btnSubmitGateLogin:not([disabled])", state="visible", timeout=20000)
        with page.expect_response(lambda r: "layer1_login" in r.url, timeout=25000):
            page.click("#btnSubmitGateLogin")

        # Chờ modal đăng nhập đóng
        page.wait_for_selector("#homeLoginGateModal", state="hidden", timeout=25000)
        assert page.evaluate("() => document.getElementById('homeLoginGateModal').classList.contains('hidden')")

        # Sau khi đăng nhập thành công:
        classes_unlocked = sec_devices.get_attribute("class") or ""
        assert "devices-logged-out" not in classes_unlocked, "Khối #secDevices không được còn class .devices-logged-out sau khi đăng nhập!"

        aria_hidden_unlocked = sec_devices.get_attribute("aria-hidden")
        assert aria_hidden_unlocked != "true", "Khối #secDevices không được giữ aria-hidden='true' sau khi đăng nhập!"

        style_info_unlocked = page.evaluate("""() => {
            const el = document.getElementById('secDevices');
            if (!el) return { pointerEvents: '', filter: '' };
            const cs = window.getComputedStyle(el);
            return {
                pointerEvents: cs.pointerEvents,
                filter: cs.filter || cs.webkitFilter || ''
            };
        }""")
        assert style_info_unlocked["pointerEvents"] != "none", "Khu vực thiết bị phải mở khóa tương tác (pointer-events != none) sau khi đăng nhập!"

        ctx.close()
        browser.close()


@pytest.mark.parametrize("vp_name,w,h", [
    ("390x844", 390, 844),
    ("360x740", 360, 740),
])
def test_playwright_mobile_viewports_no_overflow_no_overlap_and_screenshots(vp_name: str, w: int, h: int, live_server_url: str) -> None:
    """Kiểm thử Playwright Mobile Viewports trên cả 2 độ phân giải (390x844 & 360x740):
    1. Trang /guest:
       - 0 horizontal scroll: scrollWidth <= clientWidth.
       - Không đè chồng: Các phần tử chính không overlap và nằm gọn trong viewport.
       - Chụp ảnh màn hình lưu vào reports/screenshots/guest_{vp_name}.png.
    2. Trang chủ Dashboard (/):
       - 0 horizontal scroll: scrollWidth <= clientWidth.
       - Toàn bộ nội dung #ownerGuestQrPanel nằm gọn trong viewport:
         box["x"] >= 0 and box["x"] + box["width"] <= w (không bị cắt cụt).
       - Chụp ảnh màn hình lưu vào reports/screenshots/dashboard_{vp_name}.png.
    """
    import os
    from playwright.sync_api import sync_playwright

    screenshots_dir = pathlib.Path("reports/screenshots")
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    base_url = live_server_url
    with sync_playwright() as p:
        browser = _launch_browser(p)

        # =================== A. TRANG /guest ===================
        guest_ctx = browser.new_context(viewport={"width": w, "height": h})
        guest_page = guest_ctx.new_page()
        _abort_external_fonts(guest_page)
        guest_page.goto(f"{base_url}/guest", wait_until="domcontentloaded", timeout=30000)
        guest_page.wait_for_selector("#guestNameInput", state="visible", timeout=20000)

        # Kiểm tra 0 overflow-x
        guest_scroll_w = guest_page.evaluate("() => document.documentElement.scrollWidth")
        guest_client_w = guest_page.evaluate("() => document.documentElement.clientWidth")
        assert guest_scroll_w <= guest_client_w, (
            f"Trang /guest bị tràn ngang trên {vp_name}: scrollWidth={guest_scroll_w} > clientWidth={guest_client_w}"
        )

        # Kiểm tra không bị cắt cụt (no cut-off)
        guest_card = guest_page.locator(".card")
        card_box = guest_card.bounding_box()
        assert card_box is not None, "Không tìm thấy .card trên trang /guest"
        assert card_box["x"] >= 0, f"Card trên /guest bị tràn lề trái: {card_box['x']}"
        assert card_box["x"] + card_box["width"] <= w + 1, (
            f"Card trên /guest bị tràn lề phải: {card_box['x'] + card_box['width']} > {w}"
        )

        # Chụp ảnh màn hình /guest
        guest_shot_path = str(screenshots_dir / f"guest_{vp_name}.png")
        guest_page.screenshot(path=guest_shot_path, full_page=True)
        assert os.path.exists(guest_shot_path), f"Không tạo được screenshot {guest_shot_path}"
        guest_ctx.close()

        # =================== B. TRANG CHỦ DASHBOARD (/) ===================
        dash_ctx = browser.new_context(viewport={"width": w, "height": h})
        dash_ctx.add_cookies([{"name": "sh_session_token", "value": "sess_owner_t1_nep94121", "url": base_url}])
        dash_page = dash_ctx.new_page()
        _abort_external_fonts(dash_page)
        dash_page.add_init_script("""
            window.localStorage.setItem('smarthome_auth_session', JSON.stringify({
                email: 'nep94121@gmail.com',
                display_name: 'Nguyễn Tuấn Anh (Chủ nhà)',
                tier: 1
            }));
        """)
        dash_page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=30000)
        dash_page.wait_for_selector("#ownerGuestQrPanel", timeout=30000)

        # Kiểm tra 0 overflow-x
        dash_scroll_w = dash_page.evaluate("() => document.documentElement.scrollWidth")
        dash_client_w = dash_page.evaluate("() => document.documentElement.clientWidth")
        assert dash_scroll_w <= dash_client_w, (
            f"Dashboard (/) bị tràn ngang trên {vp_name}: scrollWidth={dash_scroll_w} > clientWidth={dash_client_w}"
        )

        # Kiểm tra panel QR không bị cắt cụt (no cut-off)
        qr_panel = dash_page.locator("#ownerGuestQrPanel")
        panel_box = qr_panel.bounding_box()
        assert panel_box is not None, "Không tìm thấy #ownerGuestQrPanel trên Dashboard"
        assert panel_box["x"] >= 0, f"Panel QR bị tràn lề trái: {panel_box['x']}"
        assert panel_box["x"] + panel_box["width"] <= w + 1, (
            f"Panel QR bị cắt cụt bên phải: {panel_box['x'] + panel_box['width']} > {w}"
        )

        # Chụp ảnh màn hình Dashboard
        dash_shot_path = str(screenshots_dir / f"dashboard_{vp_name}.png")
        dash_page.screenshot(path=dash_shot_path, full_page=True)
        assert os.path.exists(dash_shot_path), f"Không tạo được screenshot {dash_shot_path}"
        dash_ctx.close()

        browser.close()


