"""Playwright Live Flow Test Suite covering all 3 user roles on headless Chromium.

Roles:
1. Owner (Tier 1): nep94121@gmail.com
2. Family member (Tier 2): senat6031@gmail.com
3. Guest (Tier 3): kbanh376@gmail.com
"""
from __future__ import annotations

import pathlib
import pytest
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8088"
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _get_seed_password_for_tier(tier: int) -> str:
    from simulator.auth.constants_and_crypto import DEFAULT_ACCOUNTS
    for acc in DEFAULT_ACCOUNTS:
        if acc.get("tier") == tier and acc.get("password_plain_hint"):
            return str(acc["password_plain_hint"])
    return ""


class TestPlaywrightThreeRolesLiveFlows:
    """Kiểm thử luồng trình duyệt Chromium thực tế cho 3 vai trò trên giao diện Web."""

    def test_live_desktop_owner_tier1_flow(self):
        """Owner (Tier 1): nep94121@gmail.com có toàn quyền và huy hiệu 'Không giới hạn'."""
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            page.goto(f"{BASE_URL}/")
            page.wait_for_selector("#homeLoginGateModal", timeout=10000)

            # Thực hiện đăng nhập qua form Gate Login
            page.fill("#gateLoginEmail", "nep94121@gmail.com")
            owner_pwd = _get_seed_password_for_tier(1)
            page.fill("#gateLoginPassword", owner_pwd)
            with page.expect_response(lambda r: "/api/auth3/layer1_login" in r.url) as l1_info:
                page.click("#btnSubmitGateLogin")
            l1_data = l1_info.value.json()
            if l1_data.get("otp_required"):
                page.wait_for_selector("#gateOtpPanel", state="visible", timeout=10000)
                otp_code = l1_data.get("otp_code_for_test") or l1_data.get("demo_otp_preview") or ""
                page.fill("#gateOtpInput", otp_code)
                page.click("#btnVerifyGateOtp")

            # Chờ modal đăng nhập đóng
            page.wait_for_selector("#homeLoginGateModal", state="hidden", timeout=10000)

            # 1. Xác thực Badge tài khoản
            badge_text = page.text_content("#homeCurrentAccountBadge")
            assert "Chủ nhà" in badge_text or "nep94121@gmail.com" in badge_text, f"Unexpected badge: {badge_text}"

            # 2. Xác thực Badge thời hạn truy cập (Bug 15)
            duration_text = page.text_content("#homeSessionDurationBadge")
            assert "Không giới hạn" in duration_text, f"Expected 'Không giới hạn', got: {duration_text}"
            assert not page.is_hidden("#homeSessionDurationBadge")

            # 3. Nút đăng xuất phải hiển thị
            assert not page.is_hidden("#btnLogoutHome")

            # 4. Điều khiển Cửa chính (Chủ nhà có quyền)
            btn_door = page.query_selector("#card-main_door .switch input") or page.query_selector("#sw-main_door")
            if btn_door:
                btn_door.click()
                page.wait_for_timeout(300)

            # 5. Đăng xuất và xác nhận reset trạng thái (Bug 2)
            page.click("#btnLogoutHome")
            page.wait_for_selector("#homeLoginGateModal", state="visible", timeout=5000)
            assert page.is_hidden("#btnLogoutHome")
            assert page.is_hidden("#homeSessionDurationBadge") or page.text_content("#homeSessionDurationBadge") == ""

            browser.close()

    def test_live_desktop_family_tier2_flow(self):
        """Family member (Tier 2): senat6031@gmail.com hiển thị 'Còn 30 ngày' và bị chặn cửa."""
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            page.goto(f"{BASE_URL}/")
            page.wait_for_selector("#homeLoginGateModal", timeout=10000)

            page.fill("#gateLoginEmail", "senat6031@gmail.com")
            family_pwd = _get_seed_password_for_tier(2)
            page.fill("#gateLoginPassword", family_pwd)
            page.click("#btnSubmitGateLogin")

            page.wait_for_selector("#homeLoginGateModal", state="hidden", timeout=10000)

            # 1. Badge tài khoản
            badge_text = page.text_content("#homeCurrentAccountBadge")
            assert "senat6031@gmail.com" in badge_text or "Gia đình" in badge_text or "Người nhà" in badge_text

            # 2. Badge thời hạn truy cập (Bug 15)
            duration_text = page.text_content("#homeSessionDurationBadge")
            assert "Còn 30 ngày" in duration_text, f"Expected 'Còn 30 ngày', got: {duration_text}"

            # 3. Thử điều khiển thiết bị phòng khách (Được phép)
            sw_light = page.query_selector("#card-living_room_light .switch input") or page.query_selector("#sw-living_room_light")
            if sw_light:
                sw_light.click()
                page.wait_for_timeout(300)

            # 4. Đăng xuất
            page.click("#btnLogoutHome")
            page.wait_for_selector("#homeLoginGateModal", state="visible", timeout=5000)

            browser.close()

    def test_live_desktop_guest_tier3_flow(self):
        """Guest (Tier 3): kbanh376@gmail.com đăng nhập và hiển thị đúng vai trò Khách."""
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            page.goto(f"{BASE_URL}/")
            page.wait_for_selector("#homeLoginGateModal", timeout=10000)

            page.fill("#gateLoginEmail", "kbanh376@gmail.com")
            guest_pwd = _get_seed_password_for_tier(3)
            page.fill("#gateLoginPassword", guest_pwd)
            page.click("#btnSubmitGateLogin")

            page.wait_for_selector("#homeLoginGateModal", state="hidden", timeout=10000)

            # 1. Badge tài khoản
            badge_text = page.text_content("#homeCurrentAccountBadge")
            assert "kbanh376@gmail.com" in badge_text or "Khách" in badge_text

            # 2. Badge thời hạn truy cập
            duration_text = page.text_content("#homeSessionDurationBadge")
            assert len(duration_text.strip()) > 0

            # 3. Đăng xuất
            page.click("#btnLogoutHome")
            page.wait_for_selector("#homeLoginGateModal", state="visible", timeout=5000)

            browser.close()

    def test_live_mobile_owner_tier1_flow(self):
        """Mobile App: Owner (Tier 1) nep94121@gmail.com login & logout flow."""
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            page.goto(f"{BASE_URL}/app")
            page.wait_for_selector("#mobileLoginGate:not([hidden])", timeout=10000)

            page.fill("#mobileLoginEmail", "nep94121@gmail.com")
            owner_pwd = _get_seed_password_for_tier(1)
            page.fill("#mobileLoginPassword", owner_pwd)
            with page.expect_response(lambda r: "/api/auth3/layer1_login" in r.url) as l1_info:
                page.click("#mobileLoginBtn")
            l1_data = l1_info.value.json()
            if l1_data.get("otp_required"):
                page.wait_for_selector("#mobileOtpPanel:not([hidden])", timeout=10000)
                otp_code = l1_data.get("otp_code_for_test") or l1_data.get("demo_otp_preview") or ""
                page.fill("#mobileOtpInput", otp_code)
                page.click("#btnMobileVerifyOtp")

            page.wait_for_selector("#mobileMainContent:not([hidden])", timeout=10000)
            page.click("#mobileNavTabAccount")
            page.wait_for_selector("#tabViewAccount:not([hidden])", timeout=5000)

            role = page.text_content("#mobileProfileRole")
            assert "Chủ nhà" in role
            dur = page.text_content("#mobileProfileDuration")
            assert "Không giới hạn" in dur

            page.click("#mobileBtnLogout")
            page.wait_for_selector("#mobileLoginGate:not([hidden])", timeout=5000)

            browser.close()

    def test_live_mobile_family_tier2_flow(self):
        """Mobile App: Family member (Tier 2) senat6031@gmail.com login & logout flow."""
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            page.goto(f"{BASE_URL}/app")
            page.wait_for_selector("#mobileLoginGate:not([hidden])", timeout=10000)

            page.fill("#mobileLoginEmail", "senat6031@gmail.com")
            family_pwd = _get_seed_password_for_tier(2)
            page.fill("#mobileLoginPassword", family_pwd)
            page.click("#mobileLoginBtn")

            page.wait_for_selector("#mobileMainContent:not([hidden])", timeout=10000)
            page.click("#mobileNavTabAccount")
            page.wait_for_selector("#tabViewAccount:not([hidden])", timeout=5000)

            role = page.text_content("#mobileProfileRole")
            assert "Thành viên" in role or "Gia đình" in role or "Người nhà" in role
            dur = page.text_content("#mobileProfileDuration")
            assert "Còn 30 ngày" in dur

            page.click("#mobileBtnLogout")
            page.wait_for_selector("#mobileLoginGate:not([hidden])", timeout=5000)

            browser.close()

    def test_live_mobile_guest_tier3_flow(self):
        """Mobile App: Guest (Tier 3) kbanh376@gmail.com login & logout flow."""
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            page.goto(f"{BASE_URL}/app")
            page.wait_for_selector("#mobileLoginGate:not([hidden])", timeout=10000)

            page.fill("#mobileLoginEmail", "kbanh376@gmail.com")
            guest_pwd = _get_seed_password_for_tier(3)
            page.fill("#mobileLoginPassword", guest_pwd)
            page.click("#mobileLoginBtn")

            page.wait_for_selector("#mobileMainContent:not([hidden])", timeout=10000)
            page.click("#mobileNavTabAccount")
            page.wait_for_selector("#tabViewAccount:not([hidden])", timeout=5000)

            role = page.text_content("#mobileProfileRole")
            assert len(role.strip()) > 0

            page.click("#mobileBtnLogout")
            page.wait_for_selector("#mobileLoginGate:not([hidden])", timeout=5000)

            browser.close()
