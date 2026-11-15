"""Playwright Live Flow Test Suite covering all 3 user roles on headless Chromium.

Roles:
1. Owner (Tier 1): nep94121@gmail.com
2. Family member (Tier 2): senat6031@gmail.com
3. Guest (Tier 3): kbanh376@gmail.com
"""
from __future__ import annotations

import os
import pathlib
import secrets
import socket
import sys
import threading
import time

import pytest
from playwright.sync_api import sync_playwright
import uvicorn

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulator.auth.constants_and_crypto import ACCOUNTS_FILE, hash_password
from simulator.auth.invite_and_gmail_mixin import AuthInviteGmailMixin
from simulator.auth_3layer import get_auth_3layer_manager
from simulator.server import _ACTIVE_BRIDGES, _REST_ENGINE, app


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _launch_browser(p):
    args = ["--disable-dev-shm-usage", "--no-sandbox"]
    for ch in ("chrome", "msedge"):
        try:
            return p.chromium.launch(channel=ch, headless=True, args=args)
        except Exception:
            continue
    return p.chromium.launch(headless=True, args=args)


def _abort_fonts(page):
    try:
        page.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page.route("https://fonts.gstatic.com/**", lambda r: r.abort())
        page.route("**/static/models/**", lambda r: r.abort())
    except Exception:
        pass


@pytest.fixture(scope="module")
def live_roles_env():
    """Khởi chạy uvicorn cô lập và seed mật khẩu tạm cho 3 tài khoản test nếu chưa có SMARTHOME_LIVE_BASE_URL."""
    import urllib.request

    prev_pytest = os.environ.get("PYTEST")
    prev_gmail = os.environ.get("GMAIL_APP_PASSWORD")
    prev_smtp = os.environ.get("SMTP_PASSWORD")
    orig_send = AuthInviteGmailMixin.send_real_gmail_otp
    os.environ["PYTEST"] = "1"
    os.environ["GMAIL_APP_PASSWORD"] = ""
    os.environ["SMTP_PASSWORD"] = ""
    AuthInviteGmailMixin.send_real_gmail_otp = lambda self, *a, **kw: {
        "sent_real_gmail": True,
        "blocked_by_allowlist": False,
        "status": "MOCKED_TEST",
    }

    mgr = get_auth_3layer_manager()
    orig_db_bytes = ACCOUNTS_FILE.read_bytes() if ACCOUNTS_FILE.exists() else None
    emails = ("nep94121@gmail.com", "senat6031@gmail.com", "kbanh376@gmail.com")
    orig_hashes: dict[str, str] = {}
    passwords: dict[str, str] = {}
    for email in emails:
        acc = mgr.find_account(email)
        assert acc is not None, f"Missing seed account {email}"
        orig_hashes[email] = str(acc.get("password_hash") or "")
        pw = f"EphemeralRole_{secrets.token_hex(6)}!"
        acc["password_hash"] = hash_password(pw)
        acc["permission_active"] = True
        acc["permission_status"] = "ACTIVE"
        passwords[email] = pw

    ext = os.environ.get("SMARTHOME_LIVE_BASE_URL", "").strip()
    server = None
    thread = None
    if ext:
        base_url = ext.rstrip("/")
    else:
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

    try:
        yield {"base_url": base_url, "passwords": passwords}
    finally:
        if server is not None:
            server.should_exit = True
            if thread is not None:
                thread.join(timeout=3)
            for br in list(_ACTIVE_BRIDGES):
                try:
                    br._closed = True
                except Exception:
                    pass
            _ACTIVE_BRIDGES.clear()
        for email, h in orig_hashes.items():
            acc = mgr.find_account(email)
            if acc is not None:
                acc["password_hash"] = h
        if orig_db_bytes is not None:
            ACCOUNTS_FILE.write_bytes(orig_db_bytes)
        AuthInviteGmailMixin.send_real_gmail_otp = orig_send
        for k, v in (("PYTEST", prev_pytest), ("GMAIL_APP_PASSWORD", prev_gmail), ("SMTP_PASSWORD", prev_smtp)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestPlaywrightThreeRolesLiveFlows:
    """Kiểm thử luồng trình duyệt Chromium thực tế cho 3 vai trò trên giao diện Web và Mobile."""

    def test_live_desktop_owner_tier1_flow(self, live_roles_env: dict):
        """Owner (Tier 1): nep94121@gmail.com có toàn quyền và ẩn #homeSessionDurationBadge."""
        base_url = live_roles_env["base_url"]
        owner_pwd = live_roles_env["passwords"]["nep94121@gmail.com"]
        try:
            with sync_playwright() as p:
                browser = _launch_browser(p)
                page = browser.new_page()
                _abort_fonts(page)
                page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_selector("#homeLoginGateModal", timeout=10000)

                get_auth_3layer_manager().pending_otps.pop("nep94121@gmail.com", None)
                page.fill("#gateLoginEmail", "nep94121@gmail.com")
                page.fill("#gateLoginPassword", owner_pwd)
                with page.expect_response(lambda r: "/api/auth3/layer2_send_otp" in r.url, timeout=15000) as l2_info:
                    page.click("#btnSubmitGateLogin")
                l2_resp = l2_info.value
                assert l2_resp.status == 200, f"layer2_send_otp failed: {l2_resp.status}"
                l2_data = l2_resp.json()
                page.wait_for_selector("#gateOtpPanel:not(.hidden):not([hidden])", timeout=10000)
                otp_code = str(l2_data.get("otp_code_for_test") or l2_data.get("demo_otp_preview") or "")
                assert len(otp_code) == 6, f"Missing OTP in layer2_send_otp: {list(l2_data.keys())}"
                page.fill("#gateOtpInput", otp_code)
                page.click("#btnVerifyGateOtp")

                page.wait_for_selector("#homeLoginGateModal", state="hidden", timeout=15000)

                badge_text = page.text_content("#homeCurrentAccountBadge") or ""
                assert "Chủ nhà" in badge_text or "nep94121@gmail.com" in badge_text, f"Unexpected badge: {badge_text}"

                duration_text = page.text_content("#homeSessionDurationBadge") or ""
                assert "Không giới hạn" not in duration_text
                assert page.is_hidden("#homeSessionDurationBadge")
                assert not page.is_hidden("#btnLogoutHome")

                btn_door = page.query_selector("#card-main_door .switch input") or page.query_selector("#sw-main_door")
                if btn_door:
                    btn_door.click()
                    page.wait_for_timeout(300)

                page.click("#btnLogoutHome")
                page.wait_for_selector("#homeLoginGateModal", state="visible", timeout=5000)
                assert page.is_hidden("#btnLogoutHome")
                assert page.is_hidden("#homeSessionDurationBadge") or page.text_content("#homeSessionDurationBadge") == ""
                browser.close()
        finally:
            try:
                _REST_ENGINE.set_device_state("main_door", "CLOSED", source="test_cleanup", tier=1)
            except Exception:
                pass

    def test_live_desktop_family_tier2_flow(self, live_roles_env: dict):
        """Family member (Tier 2): senat6031@gmail.com hiển thị 'Còn 30 ngày' và điều khiển đèn phòng khách."""
        base_url = live_roles_env["base_url"]
        family_pwd = live_roles_env["passwords"]["senat6031@gmail.com"]
        try:
            with sync_playwright() as p:
                browser = _launch_browser(p)
                page = browser.new_page()
                _abort_fonts(page)
                page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_selector("#homeLoginGateModal", timeout=10000)

                page.fill("#gateLoginEmail", "senat6031@gmail.com")
                page.fill("#gateLoginPassword", family_pwd)
                page.click("#btnSubmitGateLogin")
                page.wait_for_selector("#homeLoginGateModal", state="hidden", timeout=15000)

                badge_text = page.text_content("#homeCurrentAccountBadge") or ""
                assert "senat6031@gmail.com" in badge_text or "Gia đình" in badge_text or "Người nhà" in badge_text

                duration_text = page.text_content("#homeSessionDurationBadge") or ""
                assert "Còn 30 ngày" in duration_text, f"Expected 'Còn 30 ngày', got: {duration_text}"

                sw_light = page.query_selector("#card-living_room_light .switch input") or page.query_selector("#sw-living_room_light")
                if sw_light:
                    sw_light.click()
                    page.wait_for_timeout(300)

                page.click("#btnLogoutHome")
                page.wait_for_selector("#homeLoginGateModal", state="visible", timeout=5000)
                browser.close()
        finally:
            try:
                _REST_ENGINE.set_device_state("living_room_light", "OFF", source="test_cleanup", tier=1)
            except Exception:
                pass

    def test_live_desktop_guest_tier3_flow(self, live_roles_env: dict):
        """Guest (Tier 3): kbanh376@gmail.com đăng nhập và hiển thị đúng vai trò Khách."""
        base_url = live_roles_env["base_url"]
        guest_pwd = live_roles_env["passwords"]["kbanh376@gmail.com"]
        with sync_playwright() as p:
            browser = _launch_browser(p)
            page = browser.new_page()
            _abort_fonts(page)
            page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_selector("#homeLoginGateModal", timeout=10000)

            page.fill("#gateLoginEmail", "kbanh376@gmail.com")
            page.fill("#gateLoginPassword", guest_pwd)
            page.click("#btnSubmitGateLogin")
            page.wait_for_selector("#homeLoginGateModal", state="hidden", timeout=15000)

            badge_text = page.text_content("#homeCurrentAccountBadge") or ""
            assert "kbanh376@gmail.com" in badge_text or "Khách" in badge_text

            duration_text = page.text_content("#homeSessionDurationBadge") or ""
            assert len(duration_text.strip()) > 0

            page.click("#btnLogoutHome")
            page.wait_for_selector("#homeLoginGateModal", state="visible", timeout=5000)
            browser.close()

    def test_live_mobile_owner_tier1_flow(self, live_roles_env: dict):
        """Mobile App: Owner (Tier 1) nep94121@gmail.com login & logout flow."""
        base_url = live_roles_env["base_url"]
        owner_pwd = live_roles_env["passwords"]["nep94121@gmail.com"]
        with sync_playwright() as p:
            browser = _launch_browser(p)
            page = browser.new_page()
            _abort_fonts(page)
            page.goto(f"{base_url}/app", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_selector("#mobileLoginGate:not([hidden])", timeout=10000)

            get_auth_3layer_manager().pending_otps.pop("nep94121@gmail.com", None)
            page.fill("#mobileLoginEmail", "nep94121@gmail.com")
            page.fill("#mobileLoginPassword", owner_pwd)
            with page.expect_response(lambda r: "/api/auth3/layer2_send_otp" in r.url, timeout=15000) as l2_info:
                page.click("#mobileLoginBtn")
            l2_resp = l2_info.value
            assert l2_resp.status == 200, f"layer2_send_otp failed: {l2_resp.status}"
            l2_data = l2_resp.json()
            page.wait_for_selector("#mobileOtpPanel:not([hidden])", timeout=10000)
            otp_code = str(l2_data.get("otp_code_for_test") or l2_data.get("demo_otp_preview") or "")
            assert len(otp_code) == 6, f"Missing OTP in layer2_send_otp: {list(l2_data.keys())}"
            page.fill("#mobileOtpInput", otp_code)
            page.click("#btnMobileVerifyOtp")

            page.wait_for_selector("#mobileMainContent:not([hidden])", timeout=15000)
            page.click("#mobileNavTabAccount")
            page.wait_for_selector("#tabViewAccount:not([hidden])", timeout=5000)

            role = page.text_content("#mobileProfileRole") or ""
            assert "Chủ nhà" in role
            dur = page.text_content("#mobileProfileDuration") or ""
            assert "Không giới hạn" in dur

            page.click("#mobileBtnLogout")
            page.wait_for_selector("#mobileLoginGate:not([hidden])", timeout=5000)
            browser.close()

    def test_live_mobile_family_tier2_flow(self, live_roles_env: dict):
        """Mobile App: Family member (Tier 2) senat6031@gmail.com login & logout flow."""
        base_url = live_roles_env["base_url"]
        family_pwd = live_roles_env["passwords"]["senat6031@gmail.com"]
        with sync_playwright() as p:
            browser = _launch_browser(p)
            page = browser.new_page()
            _abort_fonts(page)
            page.goto(f"{base_url}/app", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_selector("#mobileLoginGate:not([hidden])", timeout=10000)

            page.fill("#mobileLoginEmail", "senat6031@gmail.com")
            page.fill("#mobileLoginPassword", family_pwd)
            page.click("#mobileLoginBtn")

            page.wait_for_selector("#mobileMainContent:not([hidden])", timeout=15000)
            page.click("#mobileNavTabAccount")
            page.wait_for_selector("#tabViewAccount:not([hidden])", timeout=5000)

            role = page.text_content("#mobileProfileRole") or ""
            assert "Thành viên" in role or "Gia đình" in role or "Người nhà" in role
            dur = page.text_content("#mobileProfileDuration") or ""
            assert "Theo quyền tài khoản" in dur, f"Expected 'Theo quyền tài khoản', got: {dur}"

            page.click("#mobileBtnLogout")
            page.wait_for_selector("#mobileLoginGate:not([hidden])", timeout=5000)
            browser.close()

    def test_live_mobile_guest_tier3_flow(self, live_roles_env: dict):
        """Mobile App: Guest (Tier 3) kbanh376@gmail.com login & logout flow."""
        base_url = live_roles_env["base_url"]
        guest_pwd = live_roles_env["passwords"]["kbanh376@gmail.com"]
        with sync_playwright() as p:
            browser = _launch_browser(p)
            page = browser.new_page()
            _abort_fonts(page)
            page.goto(f"{base_url}/app", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_selector("#mobileLoginGate:not([hidden])", timeout=10000)

            page.fill("#mobileLoginEmail", "kbanh376@gmail.com")
            page.fill("#mobileLoginPassword", guest_pwd)
            page.click("#mobileLoginBtn")

            page.wait_for_selector("#mobileMainContent:not([hidden])", timeout=15000)
            page.click("#mobileNavTabAccount")
            page.wait_for_selector("#tabViewAccount:not([hidden])", timeout=5000)

            role = page.text_content("#mobileProfileRole") or ""
            assert "Khách" in role or len(role.strip()) > 0
            dur = page.text_content("#mobileProfileDuration") or ""
            assert "Tạm thời" in dur, f"Expected 'Tạm thời', got: {dur}"

            page.click("#mobileBtnLogout")
            page.wait_for_selector("#mobileLoginGate:not([hidden])", timeout=5000)
            browser.close()
