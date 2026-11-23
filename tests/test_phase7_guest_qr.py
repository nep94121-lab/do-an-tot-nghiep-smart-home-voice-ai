"""Bộ Kiểm Thử TDD Phase 7 — Guest QR Public Link (/guest?token=...), PIN-Signed Invites & Owner Dashboard QR.

Kiểm thử toàn diện theo luồng mới:
1. Route `/guest`, `/guest_enroll`, `/guest-qr` bắt buộc token hợp lệ (trả 403 nếu thiếu token) + `vercel.json`.
2. API tạo mã mời khách PIN-signed (`/api/guest/invites`), validate (`/api/guest/invite/validate`), redeem (`/api/guest/redeem`)
   với 5 mốc thời hạn `1d`, `2d`, `1w`, `1m`, `1y`, cơ chế dùng 1 lần (single-use -> 403 / 302 `/qr_expired?reason=used`),
   và trả 405/410 cho các endpoint thu âm giọng khách cũ đã gỡ.
3. Auth guard 401/200 trên các API điều khiển thiết bị và tạo mã mời.
4. Hiển thị chọn thời hạn (`#ownerGuestInviteDuration`), PIN xác nhận và QR trên Owner Dashboard (`/`).
5. Kiểm thử E2E Playwright trên viewport di động (`390x844`, `360x740`) và Desktop (`1280x800`).
"""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import socket
import sys
import threading
import time

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pytest
import uvicorn

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.auth.constants_and_crypto import ACCOUNTS_FILE, hash_password
from backend.auth.guest_invites import INVITE_DURATION_PRESETS
from backend.auth.invite_and_gmail_mixin import AuthInviteGmailMixin
from backend.auth_3layer import get_auth_3layer_manager
from backend.server import _ACTIVE_BRIDGES, _BOOT_VOICE_AUTH, _REST_ENGINE, app


@pytest.fixture(autouse=True)
def reset_guest_test_state(monkeypatch: pytest.MonkeyPatch):
    """Khôi phục trạng thái sạch, ép PYTEST=1 và chặn gửi Gmail/SMTP thật trong toàn bộ test Phase 7."""
    prev_pytest = os.environ.get("PYTEST")
    monkeypatch.setenv("PYTEST", "1")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")
    monkeypatch.setenv("SMTP_PASSWORD", "")
    monkeypatch.setattr(
        AuthInviteGmailMixin,
        "send_real_gmail_otp",
        lambda self, *args, **kwargs: {
            "sent_real_gmail": True,
            "blocked_by_allowlist": False,
            "status": "MOCKED_TEST",
        },
    )

    _ACTIVE_BRIDGES.clear()
    _REST_ENGINE._explicit_test_user_set = False
    _REST_ENGINE._current_role = "ADMIN"
    _REST_ENGINE._current_user_id = "tuan_anh"
    _REST_ENGINE._current_tier = 1
    mgr = get_auth_3layer_manager()
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    if hasattr(mgr, "pending_otps"):
        mgr.pending_otps.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    yield
    _ACTIVE_BRIDGES.clear()
    _REST_ENGINE._explicit_test_user_set = False
    _REST_ENGINE._current_role = "ADMIN"
    _REST_ENGINE._current_user_id = "tuan_anh"
    _REST_ENGINE._current_tier = 1
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    if prev_pytest is None:
        os.environ.pop("PYTEST", None)
    else:
        os.environ["PYTEST"] = prev_pytest


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _owner_headers() -> dict[str, str]:
    return {"X-Session-Token": "sess_owner_t1_nep94121"}


def _create_owner_invite(client: TestClient, duration_code: str = "1d", guest_name: str = "Khách Test P7") -> dict:
    res = client.post(
        "/api/guest/invites",
        headers=_owner_headers(),
        json={
            "pin": "1357",
            "pin_confirm": "1357",
            "duration_code": duration_code,
            "guest_name": guest_name,
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


def _extract_token(invite_url: str) -> str:
    return invite_url.split("token=", 1)[1].split("&", 1)[0]


# ==============================================================================
# 1. ROUTE /guest TOKEN GATE & VERCEL.JSON
# ==============================================================================

def test_route_guest_and_vercel_rewrite_configured(client: TestClient) -> None:
    """/guest, /guest-qr không có token trả 403; /guest_enroll trả 410; có token hợp lệ trả 200 HTML; vercel.json hợp lệ."""
    for path in ("/guest", "/guest-qr"):
        res_no_tok = client.get(path, headers={"Accept": "text/html"})
        assert res_no_tok.status_code == 403, f"Expected 403 for {path} without token, got {res_no_tok.status_code}"
    res_enroll = client.get("/guest_enroll", headers={"Accept": "text/html"})
    assert res_enroll.status_code == 410, f"Expected 410 for /guest_enroll, got {res_enroll.status_code}"

    inv = _create_owner_invite(client, duration_code="1d", guest_name="Khách Hợp Lệ")
    token = _extract_token(inv["url"])
    res_ok = client.get(f"/guest?token={token}", headers={"Accept": "text/html"})
    assert res_ok.status_code == 200, res_ok.text
    assert "text/html" in res_ok.headers.get("content-type", "")

    soup = BeautifulSoup(res_ok.text, "html.parser")
    for elem_id in ("guestApp", "guestTierBadge", "guestMicBtn", "guestDeviceGrid", "guestInvalid"):
        assert soup.find(id=elem_id) is not None, f"Trang /guest thiếu #{elem_id}"

    vercel_cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    redirects = vercel_cfg.get("redirects", [])
    assert any(
        r.get("source") == "/:path*"
        and r.get("permanent") is True
        and "https://laptop-6i654f8c.tail3020d6.ts.net/:path*" == r.get("destination")
        for r in redirects
    ), "vercel.json chưa cấu hình Edge 308 redirect tới máy chủ LENOVO!"


# ==============================================================================
# 2. PIN-SIGNED INVITE DURATIONS (1d/2d/1w/1m/1y), SINGLE-USE & RETIRED APIS
# ==============================================================================

@pytest.mark.parametrize("dur", ["1d", "2d", "1w", "1m", "1y"])
def test_guest_invite_all_durations_and_single_use(client: TestClient, dur: str) -> None:
    """Tất cả mốc 1d/2d/1w/1m/1y tạo QR + validate đúng thời hạn, redeem tạo phiên Cấp 3, single-use chặn lần 2."""
    expected_sec, expected_label = INVITE_DURATION_PRESETS[dur]
    inv = _create_owner_invite(client, duration_code=dur, guest_name=f"Khách {dur}")
    assert inv.get("ok") is True
    assert inv.get("duration_code") == dur
    assert inv.get("duration_seconds") == expected_sec
    assert inv.get("ttl_sec") == expected_sec
    assert inv.get("duration_label") == expected_label
    assert "<svg" in inv.get("qr_svg", "") and "</svg>" in inv.get("qr_svg", "")
    assert "/guest?token=" in inv.get("url", "")

    token = _extract_token(inv["url"])
    val = client.get(f"/api/guest/invite/validate?token={token}")
    assert val.status_code == 200, val.text
    vdata = val.json()
    assert vdata.get("valid") is True
    assert vdata.get("duration_code") == dur
    assert vdata.get("duration_seconds") == expected_sec

    # Khách mở lần đầu đổi token lấy phiên Cấp 3
    first_guest = TestClient(app)
    red = first_guest.post("/api/guest/redeem", json={"token": token})
    assert red.status_code == 200, red.text
    rdata = red.json()
    assert rdata.get("ok") is True
    assert rdata.get("tier") == 3
    assert rdata.get("duration_code") == dur
    assert rdata.get("duration_seconds") == expected_sec
    g_headers = {"X-Session-Token": str(rdata["session_token"])}

    # Khách bật đèn phòng khách được phép, mở cửa chính bị chặn
    ok_light = first_guest.post("/api/device", headers=g_headers, json={"device_id": "living_room_light", "action": "turn_on"})
    assert ok_light.status_code == 200 and ok_light.json().get("ok") is True
    first_guest.post("/api/device", headers=g_headers, json={"device_id": "living_room_light", "action": "turn_off"})

    blk_door = first_guest.post("/api/device", headers=g_headers, json={"device_id": "main_door", "action": "open"})
    assert blk_door.status_code == 403 or (blk_door.json().get("ok") is False and blk_door.json().get("rbac_blocked") is True)

    # Thiết bị thứ 2 dùng lại cùng token -> /guest redirect /qr_expired?reason=used & redeem trả 403 reason=used
    second_guest = TestClient(app)
    res_used_page = second_guest.get(f"/guest?token={token}", headers={"Accept": "text/html"}, follow_redirects=False)
    assert res_used_page.status_code == 302
    assert "/qr_expired?reason=used" in str(res_used_page.headers.get("location", ""))

    replay = second_guest.post("/api/guest/redeem", json={"token": token})
    assert replay.status_code == 403 and replay.json().get("reason") == "used"


def test_retired_legacy_guest_voice_endpoints_return_405_or_410(client: TestClient) -> None:
    """Các endpoint thu âm/bắt tay QR khách cũ trả 405 hoặc 410."""
    assert client.get("/api/auth3/guest_qr_current?duration=1d", headers=_owner_headers()).status_code in (405, 410)
    assert client.post("/api/auth3/guest_qr_complete_voice", json={"guest_name": "X", "audio_pcm_b64": ""}).status_code == 410
    assert client.post("/api/auth3/guest_qr_handshake", json={"token": "x"}).status_code == 410


# ==============================================================================
# 3. BẢO VỆ 401/200 CHO API THIẾT BỊ & TẠO MÃ MỜI KHÁCH
# ==============================================================================

def test_unauthenticated_requests_return_401(client: TestClient) -> None:
    """Gửi request không có session tới các API thiết bị và /api/guest/invites phải trả 401."""
    assert client.post("/api/device", json={"device_id": "living_room_light", "action": "turn_on"}).status_code == 401
    assert client.post("/api/device_control", json={"device_id": "bedroom_light", "action": "turn_on"}).status_code == 401
    assert client.post("/api/devices/speaker_amp/control", json={"action": "turn_on"}).status_code == 401
    assert client.post("/api/mobile/schedule", json={"device_id": "living_room_light", "seconds": 30, "action": "turn_on"}).status_code == 401
    assert client.post("/api/ir_learn", json={"device_name": "Điều hòa", "command_action": "open"}).status_code == 401
    assert client.post("/api/text_command", json={"text": "bật đèn phòng khách"}).status_code == 401
    assert client.post("/api/guest/invites", json={"pin": "1357", "pin_confirm": "1357", "duration_code": "1d"}).status_code == 401


def test_authenticated_requests_return_200(client: TestClient) -> None:
    """Với X-Session-Token của Chủ nhà Cấp 1, các API thiết bị và tạo mã mời khách trả 200 OK (và /api/ir_learn trả 410 Gone)."""
    headers = _owner_headers()
    assert client.post("/api/device", json={"device_id": "living_room_light", "action": "turn_on"}, headers=headers).status_code == 200
    assert client.post("/api/device_control", json={"device_id": "living_room_light", "action": "turn_off"}, headers=headers).status_code == 200
    assert client.post("/api/devices/speaker_amp/control", json={"action": "turn_on"}, headers=headers).status_code == 200
    assert client.post("/api/devices/speaker_amp/control", json={"action": "turn_off"}, headers=headers).status_code == 200
    assert client.post("/api/mobile/schedule", json={"device_id": "bedroom_light", "seconds": 30, "action": "turn_on"}, headers=headers).status_code == 200
    assert client.post("/api/ir_learn", json={"device_name": "Điều hòa Casper", "command_action": "open"}, headers=headers).status_code == 410
    r_txt = client.post("/api/text_command", json={"text": "bật đèn phòng ngủ"}, headers=headers)
    assert r_txt.status_code == 200 and r_txt.json().get("ok") is True
    if r_txt.json().get("requires_confirmation"):
        r_ok = client.post("/api/text_command", json={"text": "ok"}, headers=headers)
        assert r_ok.status_code == 200 and r_ok.json().get("ok") is True
    client.post("/api/device", json={"device_id": "bedroom_light", "action": "turn_off"}, headers=headers)

    inv = _create_owner_invite(client, duration_code="1d")
    assert inv.get("ok") is True and "<svg" in inv.get("qr_svg", "")


# ==============================================================================
# 4. HIỂN THỊ PANEL QR & CHỌN THỜI HẠN TRÊN OWNER DASHBOARD (/)
# ==============================================================================

def test_owner_dashboard_shows_guest_qr_panel(client: TestClient) -> None:
    """Trang chủ (/) phải có #ownerGuestQrPanel, #ownerGuestInviteDuration (1d/2d/1w/1m/1y) và liên kết /guest."""
    res = client.get("/", headers={"Accept": "text/html"})
    assert res.status_code == 200
    soup = BeautifulSoup(res.text, "html.parser")

    assert soup.find(id="ownerGuestQrPanel") is not None
    assert soup.find(id="ownerDashboardQrBox") is not None
    assert soup.find(id="ownerGuestLinkText") is not None
    open_link = soup.find(id="ownerGuestOpenLink")
    assert open_link is not None and "/guest" in (open_link.get("href") or "")

    dur_sel = soup.find(id="ownerGuestInviteDuration")
    assert dur_sel is not None, "Trang chủ (/) thiếu select #ownerGuestInviteDuration"
    opt_vals = {opt.get("value") for opt in dur_sel.find_all("option")}
    for expected_dur in ("1d", "2d", "1w", "1m", "1y"):
        assert expected_dur in opt_vals, f"Thiếu mốc {expected_dur} trong #ownerGuestInviteDuration"


# ==============================================================================
# 5. KIỂM THỬ E2E PLAYWRIGHT (OWNER DASHBOARD QR + MOBILE /guest?token=...)
# ==============================================================================

def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def live_server_url():
    """Khởi tạo phiên uvicorn cục bộ phạm vi module với healthcheck /api/health."""
    import urllib.request

    port = _get_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=0.5) as resp:
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
    for ch in ("chrome", "msedge"):
        try:
            return p.chromium.launch(channel=ch, headless=True, args=args)
        except Exception:
            continue
    return p.chromium.launch(headless=True, args=args)


def _abort_external_fonts(page):
    try:
        page.route("https://fonts.googleapis.com/**", lambda route: route.abort())
        page.route("https://fonts.gstatic.com/**", lambda route: route.abort())
        page.route("**/static/models/**", lambda route: route.abort())
        page.route("**/house3d.js", lambda route: route.fulfill(
            status=200,
            content_type="application/javascript",
            body="window.SmartHome3D = new Proxy({}, { get: () => () => {} });",
        ))
    except Exception:
        pass


def test_playwright_e2e_guest_mobile_and_owner_dashboard_qr(live_server_url: str) -> None:
    """Owner tạo QR 1w trên (/), Khách mở /guest?token=... trên 390x844 điều khiển được thiết bị, lần 2 bị chặn."""
    from playwright.sync_api import sync_playwright

    base_url = live_server_url
    with sync_playwright() as p:
        browser = _launch_browser(p)

        # A. Owner tạo QR thời hạn 1 tuần bằng PIN xác nhận
        owner_ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        owner_ctx.add_cookies([
            {"name": "sh_session_token", "value": "sess_owner_t1_nep94121", "url": base_url},
            {"name": "session_token", "value": "sess_owner_t1_nep94121", "url": base_url},
        ])
        owner_page = owner_ctx.new_page()
        _abort_external_fonts(owner_page)
        owner_page.add_init_script("""
            window.localStorage.setItem('session_token', 'sess_owner_t1_nep94121');
            window.localStorage.setItem('smarthome_auth_session', JSON.stringify({
                email: 'nep94121@gmail.com',
                display_name: 'Nguyễn Tuấn Anh (Chủ nhà)',
                tier: 1,
                session_token: 'sess_owner_t1_nep94121'
            }));
        """)
        owner_errors: list[str] = []
        owner_page.on("pageerror", lambda err: owner_errors.append(str(err)))

        owner_page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=30000)
        owner_page.wait_for_selector("#ownerGuestQrPanel", timeout=20000)
        owner_page.wait_for_function(
            "() => (document.getElementById('homeCurrentAccountBadge')?.textContent || '').includes('Cấp 1')",
            timeout=15000,
        )
        owner_page.wait_for_timeout(400)
        owner_page.fill("#ownerGuestQrPin", "1357")
        if owner_page.is_visible("#ownerGuestQrPinConfirm"):
            owner_page.fill("#ownerGuestQrPinConfirm", "1357")
        owner_page.select_option("#ownerGuestInviteDuration", "1w")
        with owner_page.expect_response(
            lambda r: ("/api/auth3/guest_invites" in r.url or "/api/guest/invites" in r.url) and r.request.method == "POST",
            timeout=15000,
        ):
            owner_page.click("#ownerGuestQrGenerateBtn")

        owner_page.wait_for_selector("#ownerGuestQrSvg svg", timeout=15000)
        expiry_label = owner_page.locator("#ownerGuestExpiryLabel").inner_text()
        assert "1 tuần" in expiry_label, f"Expected '1 tuần' in {expiry_label}"
        invite_href = owner_page.locator("#ownerGuestOpenLink").get_attribute("href") or ""
        assert "/guest?token=" in invite_href, f"Unexpected href: {invite_href}"
        guest_url = invite_href if invite_href.startswith("http") else f"{base_url}{invite_href}"
        assert not owner_errors, f"Lỗi JS trên trang chủ (/): {owner_errors}"
        owner_ctx.close()

        # B. Khách mở link mời trên màn hình di động 390x844
        guest_ctx = browser.new_context(viewport={"width": 390, "height": 844})
        guest_page = guest_ctx.new_page()
        _abort_external_fonts(guest_page)
        guest_errors: list[str] = []
        guest_page.on("pageerror", lambda err: guest_errors.append(str(err)))

        guest_page.goto(guest_url, wait_until="domcontentloaded", timeout=30000)
        guest_page.wait_for_selector("#guestApp:not([hidden])", timeout=20000)
        overflow_x = guest_page.evaluate(
            "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        assert overflow_x is False, "Trang /guest bị tràn ngang trên mobile 390x844!"

        badge_text = guest_page.locator("#guestTierBadge").inner_text()
        assert "1 tuần" in badge_text, f"Expected '1 tuần' in #guestTierBadge, got: {badge_text}"

        guest_page.wait_for_selector("#guestDeviceGrid button", timeout=10000)
        with guest_page.expect_response(lambda r: "/api/device" in r.url and r.status == 200, timeout=10000):
            guest_page.locator("#guestDeviceGrid button").first.click()
        assert not guest_errors, f"Lỗi pageerror trên /guest: {guest_errors}"
        guest_ctx.close()

        # C. Thiết bị thứ 2 mở cùng URL -> phải chuyển hướng /qr_expired?reason=used
        second_ctx = browser.new_context(viewport={"width": 390, "height": 844})
        second_page = second_ctx.new_page()
        _abort_external_fonts(second_page)
        second_page.goto(guest_url, wait_until="domcontentloaded", timeout=20000)
        assert "/qr_expired" in second_page.url and "reason=used" in second_page.url, f"Expected used redirect, got: {second_page.url}"
        second_ctx.close()
        browser.close()


def test_playwright_dashboard_logged_out_device_blur_and_login_unlock(live_server_url: str) -> None:
    """Kiểm thử trạng thái logged-out gỡ dashboard (#homeAppShell === null) và mở khóa #secDevices sau khi đăng nhập Lớp 1 + Lớp 2 OTP."""
    from playwright.sync_api import sync_playwright

    mgr = get_auth_3layer_manager()
    owner_acc = mgr.find_account("nep94121@gmail.com")
    assert owner_acc is not None
    orig_hash = owner_acc.get("password_hash", "")
    orig_db_bytes = ACCOUNTS_FILE.read_bytes() if ACCOUNTS_FILE.exists() else None
    temp_pw = f"EphemeralTestPw_{secrets.token_hex(6)}!"
    owner_acc["password_hash"] = hash_password(temp_pw)
    if hasattr(mgr, "pending_otps"):
        mgr.pending_otps.pop("nep94121@gmail.com", None)

    base_url = live_server_url
    try:
        with sync_playwright() as p:
            browser = _launch_browser(p)
            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            page = ctx.new_page()
            _abort_external_fonts(page)

            page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector("#homeLoginGateModal:not(.hidden)", timeout=30000)
            unmounted = page.evaluate(
                "() => document.getElementById('homeAppShell') === null && document.getElementById('secDevices') === null"
            )
            assert unmounted is True, "Dashboard DOM phải bị gỡ khi chưa đăng nhập"

            page.fill("#gateLoginEmail", "nep94121@gmail.com")
            page.fill("#gateLoginPassword", temp_pw)
            with page.expect_response(lambda r: "/api/auth3/layer2_send_otp" in r.url, timeout=25000) as l2_info:
                page.click("#btnSubmitGateLogin")
            l2_resp = l2_info.value
            assert l2_resp.status == 200, f"layer2_send_otp failed: {l2_resp.status}"
            l2_data = l2_resp.json()
            page.wait_for_selector("#gateOtpPanel:not(.hidden):not([hidden])", timeout=15000)
            otp_code = str(l2_data.get("otp_code_for_test") or l2_data.get("demo_otp_preview") or "")
            assert len(otp_code) == 6, f"Missing test OTP in layer2 response: {list(l2_data.keys())}"
            page.fill("#gateOtpInput", otp_code)
            page.click("#btnVerifyGateOtp")

            page.wait_for_selector("#homeLoginGateModal", state="hidden", timeout=25000)
            sec_devices = page.locator("#secDevices")
            page.wait_for_selector("#secDevices", timeout=10000)
            classes_unlocked = sec_devices.get_attribute("class") or ""
            assert "devices-logged-out" not in classes_unlocked
            assert sec_devices.get_attribute("aria-hidden") != "true"

            style_unlocked = page.evaluate("""() => {
                const cs = window.getComputedStyle(document.getElementById('secDevices'));
                return { pointerEvents: cs.pointerEvents };
            }""")
            assert style_unlocked["pointerEvents"] != "none"

            ctx.close()
            browser.close()
    finally:
        owner_acc["password_hash"] = orig_hash
        if orig_db_bytes is not None:
            ACCOUNTS_FILE.write_bytes(orig_db_bytes)


@pytest.mark.parametrize("vp_name,w,h", [
    ("390x844", 390, 844),
    ("360x740", 360, 740),
])
def test_playwright_mobile_viewports_no_overflow_no_overlap_and_screenshots(
    vp_name: str,
    w: int,
    h: int,
    tmp_path: pathlib.Path,
    live_server_url: str,
) -> None:
    """Kiểm tra mobile 390x844 & 360x740 trên `/guest?token=...` và `/` không tràn ngang hay cắt panel."""
    from playwright.sync_api import sync_playwright

    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    api_client = TestClient(app)
    inv = _create_owner_invite(api_client, duration_code="2d", guest_name=f"Khách {vp_name}")
    token = _extract_token(inv["url"])

    base_url = live_server_url
    with sync_playwright() as p:
        browser = _launch_browser(p)

        # A. Trang /guest?token=...
        guest_ctx = browser.new_context(viewport={"width": w, "height": h})
        guest_page = guest_ctx.new_page()
        _abort_external_fonts(guest_page)
        guest_page.goto(f"{base_url}/guest?token={token}", wait_until="domcontentloaded", timeout=30000)
        guest_page.wait_for_selector("#guestApp:not([hidden])", timeout=20000)

        guest_scroll_w = guest_page.evaluate("() => document.documentElement.scrollWidth")
        guest_client_w = guest_page.evaluate("() => document.documentElement.clientWidth")
        assert guest_scroll_w <= guest_client_w, (
            f"Trang /guest bị tràn ngang trên {vp_name}: {guest_scroll_w} > {guest_client_w}"
        )
        shell_box = guest_page.locator("#guestApp").bounding_box()
        assert shell_box is not None and shell_box["x"] >= 0 and shell_box["x"] + shell_box["width"] <= w + 1
        guest_shot = screenshots_dir / f"guest_{vp_name}.png"
        guest_page.screenshot(path=str(guest_shot), full_page=True)
        assert guest_shot.exists() and guest_shot.stat().st_size > 0
        guest_ctx.close()

        # B. Trang chủ Dashboard (/)
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
        dash_page.wait_for_selector("#ownerGuestQrPanel", timeout=20000)

        dash_scroll_w = dash_page.evaluate("() => document.documentElement.scrollWidth")
        dash_client_w = dash_page.evaluate("() => document.documentElement.clientWidth")
        assert dash_scroll_w <= dash_client_w, (
            f"Dashboard (/) bị tràn ngang trên {vp_name}: {dash_scroll_w} > {dash_client_w}"
        )
        panel_box = dash_page.locator("#ownerGuestQrPanel").bounding_box()
        assert panel_box is not None and panel_box["x"] >= 0 and panel_box["x"] + panel_box["width"] <= w + 1
        dash_shot = screenshots_dir / f"dashboard_{vp_name}.png"
        dash_page.screenshot(path=str(dash_shot), full_page=True)
        assert dash_shot.exists() and dash_shot.stat().st_size > 0
        dash_ctx.close()

        browser.close()
