"""Bộ Kiểm Thử Milestone M8: 5 Màn Hình Mobile PWA & DOM Integrity.

Người thực hiện: worker_m8 (Role: implementer, qa, specialist)
Mục tiêu kiểm định:
1. M1: Trang Chủ (Nhà & Cảm biến): Toàn cảnh 16:9, Cảm biến 2 ô Grid, Trạng thái an toàn, Nút hành động nhanh.
2. M2: Chuyển đổi 4 Tab độc lập & Màn Tài khoản: 4 tabs, Hồ sơ phân cấp, Menu quản lý, Đăng xuất, scrollToSection mapping.
3. M3: Quên mật khẩu & OTP Gmail: Form 3 bước (Email -> OTP numeric 6 số -> Reset 2 ô), tích hợp API backend.
4. M4: Bottom Sheet Giọng nói: Scrim, handle, wavecircle, 12 thanh volume bar, bộ đếm thời gian, câu mẫu, kết quả.
5. M5: Camera Quét QR & Handshake: Modal camera, khung 4 góc line, tích hợp /api/auth3/guest_handshake.
6. Bảo toàn 100% 68 DOM IDs và 25 window.* hooks hiện có.
7. Đảm bảo chính sách Android Scope frozen theo Requirement R3.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
from bs4 import BeautifulSoup
import pytest
from starlette.testclient import TestClient
from simulator.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOBILE_HTML_PATH = ROOT / "mobile_app" / "index.html"
MOBILE_JS_PATH = ROOT / "simulator" / "static" / "js" / "mobile_app.js"
MOBILE_CSS_PATH = ROOT / "simulator" / "static" / "css" / "mobile_app.css"

REQUIRED_68_DOM_IDS = [
    "aiReply", "btnLearnIr", "btnMobileMicLabel", "btnMobileTabLogin",
    "btnMobileTabRegister", "btnTestDrySoil", "btnToggleShowAllDevices", "cmdForm",
    "cmdInput", "devGrid", "espBadge", "humVal",
    "mobileActorBadge", "mobileActorSelect", "mobileAddEmailForm", "mobileAllowlistMsg",
    "mobileBottomNav", "mobileChangeConfirmPassword", "mobileChangeEmail", "mobileChangeNewPassword",
    "mobileChangePasswordBtn", "mobileChangePasswordMsg", "mobileGuestDurSelect", "mobileLoginBtn",
    "mobileLoginEmail", "mobileLoginForm", "mobileLoginGate", "mobileLoginMsg",
    "mobileLoginPassword", "mobileMainContent", "mobileQrCountdown", "mobileQrDots",
    "mobileQrInviteTierSelect", "mobileQrOpenLink", "mobileQrSvgContainer", "mobileQrTokenText",
    "mobileQrUrlText", "mobileRegConfirmPassword", "mobileRegEmail", "mobileRegMsg",
    "mobileRegName", "mobileRegPassword", "mobileRegTier", "mobileRegisterBtn",
    "mobileRegisterForm", "mobileStrikeBadge", "mobileTargetEmail", "mobileTargetTierSelect",
    "mobileVoiceF0", "mobileVoiceMetrics", "mobileVoiceRegName", "mobileVoiceRes",
    "mobileVoiceRetryBtn", "mobileVoiceSNR", "mobileVoiceStepLabel", "mobileVoiceTierInfo",
    "mqttLog", "pwaSchedAction", "pwaSchedDevice", "pwaSchedTime",
    "pwaScheduleForm", "pwaVoiceEmpty", "pwaVoiceResults", "soilVal",
    "tempVal", "upcomingScheduleInline", "userSaidText", "voiceStateBadge"
]

REQUIRED_25_WINDOW_HOOKS = [
    "window.addLog", "window.copyMobileGuestLink", "window.executeMobileCommand",
    "window.fetchInitial", "window.filterDevicesByRoom", "window.filterMobileHistory",
    "window.onMobileActorChange", "window.onMobileQrInviteTierChange", "window.onMobileRegTierChange",
    "window.pollMobileSecurityAndTimers", "window.refreshMobileQr10s", "window.renderMobileHistory",
    "window.renderState", "window.scrollToSection", "window.showPwaVoiceResults",
    "window.submitMobileAddEmail", "window.submitMobileChangePassword", "window.submitMobileLogin",
    "window.submitMobileRegister", "window.submitMobileVoiceSample", "window.submitPwaSchedule",
    "window.switchMobileLoginTab", "window.toggleMobileVoiceListen", "window.togglePasswordVisibility",
    "window.toggleShowAllDevices"
]


@pytest.fixture(scope="module")
def html_soup() -> BeautifulSoup:
    html_content = MOBILE_HTML_PATH.read_text(encoding="utf-8")
    return BeautifulSoup(html_content, "html.parser")


@pytest.fixture(scope="module")
def js_content() -> str:
    return MOBILE_JS_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def css_content() -> str:
    return MOBILE_CSS_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# =============================================================================
# 1. KIỂM THỬ TÍNH TOÀN VẸN 68 DOM IDS & 25 WINDOW HOOKS
# =============================================================================
class TestDomAndHookIntegrity:
    """Kiểm tra sự tồn tại đầy đủ của 68 DOM IDs và 25 window.* hooks bắt buộc."""

    def test_all_68_dom_ids_exist(self, html_soup: BeautifulSoup):
        missing_ids = []
        for dom_id in REQUIRED_68_DOM_IDS:
            if not html_soup.find(id=dom_id):
                missing_ids.append(dom_id)
        assert not missing_ids, f"Bị thiếu {len(missing_ids)} DOM IDs trong mobile_app/index.html: {missing_ids}"

    def test_all_25_window_hooks_exported(self, js_content: str):
        missing_hooks = []
        for hook in REQUIRED_25_WINDOW_HOOKS:
            if hook not in js_content:
                missing_hooks.append(hook)
        assert not missing_hooks, f"Bị thiếu {len(missing_hooks)} window.* exports trong mobile_app.js: {missing_hooks}"


# =============================================================================
# 2. KIỂM THỬ M1: TRANG CHỦ (NHÀ & CẢM BIẾN)
# =============================================================================
class TestM1HomeScreen:
    """Kiểm thử màn hình M1: Thẻ Toàn cảnh 16:9, Cảm biến 2 ô Grid, Trạng thái an toàn, Nút hành động."""

    def test_m1_overview_card_16_9(self, html_soup: BeautifulSoup, css_content: str):
        box = html_soup.find(id="mobileOverviewBox")
        assert box is not None, "Không tìm thấy #mobileOverviewBox cho thẻ Toàn cảnh"
        assert "preview-16-9" in box.get("class", []), "#mobileOverviewBox phải có class 'preview-16-9'"
        assert "aspect-ratio: 16 / 9" in css_content, "CSS phải có quy tắc aspect-ratio: 16 / 9 cho preview-16-9"

    def test_m1_sensor_grid_two_cells_only(self, html_soup: BeautifulSoup):
        card = html_soup.find(id="home-sensors-title").find_parent("section")
        assert card is not None, "Không tìm thấy thẻ Cảm biến trong M1"
        sensorgrid = card.find(class_="sensorgrid")
        assert sensorgrid is not None, "Thẻ Cảm biến phải có container class 'sensorgrid'"
        sensors = sensorgrid.find_all(class_="sensor")
        assert len(sensors) == 2, f"Màn Home M1 chỉ được có đúng 2 ô cảm biến (Nhiệt độ & Độ ẩm đất), tìm thấy: {len(sensors)}"
        assert html_soup.find(id="mobileDisplayTemp") is not None, "Thiếu #mobileDisplayTemp trong ô Nhiệt độ"
        assert html_soup.find(id="mobileDisplaySoil") is not None, "Thiếu #mobileDisplaySoil trong ô Độ ẩm đất"

    def test_m1_safety_status_card(self, html_soup: BeautifulSoup):
        door_status = html_soup.find(id="mobileMainDoorStatus")
        assert door_status is not None, "Thiếu #mobileMainDoorStatus trong thẻ Trạng thái an toàn"
        siren_status = html_soup.find(id="mobileAlarmSirenStatus")
        assert siren_status is not None, "Thiếu #mobileAlarmSirenStatus trong thẻ Trạng thái an toàn"

    def test_m1_quick_action_buttons(self, html_soup: BeautifulSoup):
        btn_voice = html_soup.find(id="mobileBtnVoiceSheet")
        assert btn_voice is not None, "Thiếu nút Nói lệnh #mobileBtnVoiceSheet"
        assert "openVoiceBottomSheet()" in btn_voice.get("onclick", ""), "#mobileBtnVoiceSheet phải gọi openVoiceBottomSheet()"
        btn_dev = html_soup.find(id="mobileBtnViewDevices")
        assert btn_dev is not None, "Thiếu nút Xem thiết bị #mobileBtnViewDevices"
        assert "switchMobileTab('devices')" in btn_dev.get("onclick", ""), "#mobileBtnViewDevices phải gọi switchMobileTab('devices')"


# =============================================================================
# 3. KIỂM THỬ M2: 4 TAB ĐỘC LẬP & MÀN TÀI KHOẢN
# =============================================================================
class TestM2TabsAndAccount:
    """Kiểm thử M2: 4 Tab độc lập, Hồ sơ tài khoản, Menu quản lý, Nút đăng xuất, tương thích scrollToSection."""

    def test_m2_four_tab_views_exist(self, html_soup: BeautifulSoup):
        tabs = ["tabViewHome", "tabViewDevices", "tabViewVoice", "tabViewAccount"]
        for tab_id in tabs:
            tab_div = html_soup.find(id=tab_id)
            assert tab_div is not None, f"Không tìm thấy tab view #{tab_id}"
            assert "tab-view" in tab_div.get("class", []), f"#{tab_id} phải có class 'tab-view'"

    def test_m2_bottom_navigation_four_tabs(self, html_soup: BeautifulSoup):
        nav_tabs = ["mobileNavTabHome", "mobileNavTabDevices", "mobileNavTabVoice", "mobileNavTabAccount"]
        for nav_id in nav_tabs:
            tab_btn = html_soup.find(id=nav_id)
            assert tab_btn is not None, f"Không tìm thấy nút điều hướng #{nav_id} trong bottom nav"

    def test_m2_account_profile_and_management(self, html_soup: BeautifulSoup):
        assert html_soup.find(id="mobileProfileRole") is not None, "Thiếu #mobileProfileRole trong hồ sơ tài khoản"
        assert html_soup.find(id="mobileProfileEmail") is not None, "Thiếu #mobileProfileEmail trong hồ sơ tài khoản"
        assert html_soup.find(id="mobileProfileDuration") is not None, "Thiếu #mobileProfileDuration trong hồ sơ tài khoản"
        btn_logout = html_soup.find(id="mobileBtnLogout")
        assert btn_logout is not None, "Thiếu nút Đăng xuất #mobileBtnLogout"
        assert "submitMobileLogout()" in btn_logout.get("onclick", ""), "#mobileBtnLogout phải gọi submitMobileLogout()"

    def test_m2_scroll_to_section_compatibility(self, js_content: str):
        assert "function switchMobileTab" in js_content, "mobile_app.js phải chứa hàm switchMobileTab"
        assert "switchMobileTab('home'" in js_content, "scrollToSection phải ánh xạ secHome sang tab home"
        assert "switchMobileTab('devices'" in js_content, "scrollToSection phải ánh xạ secDevices sang tab devices"
        assert "switchMobileTab('voice'" in js_content, "scrollToSection phải ánh xạ secVoice sang tab voice"
        assert "switchMobileTab('account'" in js_content, "scrollToSection phải ánh xạ secAuth sang tab account"


# =============================================================================
# 4. KIỂM THỬ M3: QUÊN MẬT KHẨU & GMAIL OTP
# =============================================================================
class TestM3ForgotPassword:
    """Kiểm thử M3: Giao diện 3 bước, thuộc tính input OTP và tích hợp API."""

    def test_m3_forgot_panel_and_trigger_button(self, html_soup: BeautifulSoup):
        btn_forgot = html_soup.find(id="btnMobileForgotPassword")
        assert btn_forgot is not None, "Thiếu nút #btnMobileForgotPassword trên màn đăng nhập"
        assert "openForgotPassword()" in btn_forgot.get("onclick", "")
        panel = html_soup.find(id="mobileForgotPasswordPanel")
        assert panel is not None, "Thiếu panel #mobileForgotPasswordPanel"

    def test_m3_otp_field_attributes(self, html_soup: BeautifulSoup):
        otp_input = html_soup.find(id="mobileForgotOtp")
        assert otp_input is not None, "Thiếu ô nhập OTP #mobileForgotOtp"
        assert otp_input.get("inputmode") == "numeric", "#mobileForgotOtp phải có inputmode='numeric'"
        assert otp_input.get("autocomplete") == "one-time-code", "#mobileForgotOtp phải có autocomplete='one-time-code'"
        assert otp_input.get("maxlength") == "6", "#mobileForgotOtp phải có maxlength='6'"

    def test_m3_reset_passwords_have_toggle_buttons(self, html_soup: BeautifulSoup):
        form_reset = html_soup.find(id="mobileForgotStepReset")
        assert form_reset is not None, "Thiếu form bước 3 #mobileForgotStepReset"
        assert html_soup.find(id="mobileForgotNewPassword") is not None
        assert html_soup.find(id="mobileForgotConfirmPassword") is not None
        btn_submit = html_soup.find(id="mobileBtnForgotSubmitReset")
        assert btn_submit is not None
        assert btn_submit.get("type") == "submit"

    def test_m3_backend_api_endpoints_exist(self, client: TestClient):
        # 1. Gửi OTP
        res_send = client.post("/api/auth3/forgot_password_send_otp", json={"email": "nep94121@gmail.com", "send_gmail": False})
        assert res_send.status_code in [200, 400], f"Endpoint /api/auth3/forgot_password_send_otp phản hồi bất thường: {res_send.status_code}"
        # 2. Reset mật khẩu
        res_reset = client.post("/api/auth3/forgot_password_reset", json={
            "email": "nep94121@gmail.com", "otp": "999999", "new_password": "new_password_123", "confirm_password": "new_password_123"
        })
        assert res_reset.status_code in [200, 400], f"Endpoint /api/auth3/forgot_password_reset phản hồi bất thường: {res_reset.status_code}"


# =============================================================================
# 5. KIỂM THỬ M4: BOTTOM SHEET GIỌNG NÓI
# =============================================================================
class TestM4VoiceBottomSheet:
    """Kiểm thử M4: Scrim, Bottom sheet, wavecircle, 12 thanh bars, timer, câu mẫu, kết quả."""

    def test_m4_bottom_sheet_structure(self, html_soup: BeautifulSoup, css_content: str):
        scrim = html_soup.find(id="mobileVoiceSheetScrim")
        assert scrim is not None, "Thiếu lớp nền mờ #mobileVoiceSheetScrim"
        sheet = html_soup.find(id="mobileVoiceBottomSheet")
        assert sheet is not None, "Thiếu bottom sheet #mobileVoiceBottomSheet"
        assert sheet.find(class_="handle") is not None, "Bottom sheet phải có thanh kéo .handle"
        assert sheet.find(class_="wavecircle") is not None, "Bottom sheet phải có vòng tròn sóng .wavecircle"

    def test_m4_volume_bars_exactly_twelve(self, html_soup: BeautifulSoup):
        bars_container = html_soup.find(id="mobileVoiceVolumeBars")
        assert bars_container is not None, "Thiếu #mobileVoiceVolumeBars trong bottom sheet"
        bars = bars_container.find_all("i")
        assert len(bars) == 12, f"Thanh sóng âm phải gồm đúng 12 vạch <i>, tìm thấy: {len(bars)}"

    def test_m4_timer_and_phrase(self, html_soup: BeautifulSoup):
        assert html_soup.find(id="mobileVoiceTimerCur") is not None, "Thiếu bộ đếm thời gian hiện tại #mobileVoiceTimerCur"
        assert html_soup.find(id="mobileVoiceTimerTotal") is not None, "Thiếu mốc thời gian tổng #mobileVoiceTimerTotal"
        phrase = html_soup.find(id="mobileVoicePhrase")
        assert phrase is not None, "Thiếu khung câu mẫu #mobileVoicePhrase"
        assert "cửa" in phrase.text.lower(), "Câu mẫu phải chứa nội dung điều khiển ngôi nhà"

    def test_m4_sheet_actions_and_result(self, html_soup: BeautifulSoup):
        assert html_soup.find(id="mobileBtnVoiceSheetStop") is not None
        assert html_soup.find(id="mobileBtnVoiceSheetCancel") is not None
        assert html_soup.find(id="mobileVoiceSheetResult") is not None


# =============================================================================
# 6. KIỂM THỬ M5: CAMERA QUÉT QR & BẮT TAY KHÁCH
# =============================================================================
class TestM5QrScanner:
    """Kiểm thử M5: Modal quét camera, khung ngắm 4 góc viền và API handshake."""

    def test_m5_scanner_modal_and_scanframe(self, html_soup: BeautifulSoup, css_content: str):
        modal = html_soup.find(id="mobileQrScannerModal")
        assert modal is not None, "Thiếu modal quét mã QR #mobileQrScannerModal"
        scanframe = modal.find(id="mobileScanFrame")
        assert scanframe is not None, "Thiếu khung ngắm #mobileScanFrame"
        for corner in ["tl", "tr", "bl", "br"]:
            assert scanframe.find("i", class_=corner) is not None, f"Khung ngắm thiếu góc .{corner}"

    def test_m5_camera_elements_and_buttons(self, html_soup: BeautifulSoup):
        video = html_soup.find(id="mobileQrVideo")
        assert video is not None, "Thiếu thẻ video #mobileQrVideo cho camera stream"
        assert video.has_attr("playsinline"), "#mobileQrVideo phải có playsinline"
        assert html_soup.find(id="mobileBtnStartCamera") is not None, "Thiếu nút #mobileBtnStartCamera"
        assert html_soup.find(id="mobileBtnManualCodeInput") is not None, "Thiếu nút #mobileBtnManualCodeInput"

    def test_m5_backend_handshake_endpoint(self, client: TestClient):
        # 1. Kiểm tra gọi endpoint /api/auth3/guest_handshake với token không hợp lệ -> 401
        res_invalid = client.post("/api/auth3/guest_handshake", json={"token": "test_invalid_token", "duration": "1d"})
        assert res_invalid.status_code in [200, 400, 401], f"Endpoint /api/auth3/guest_handshake phản hồi bất thường: {res_invalid.status_code}"
        assert res_invalid.json().get("ok") is False

        # 2. Kiểm tra gọi với token hợp lệ sinh từ /api/auth3/guest_qr_current -> 200 ok
        res_gen = client.get("/api/auth3/guest_qr_current?duration=1d&host=localhost:8088&tier=3")
        assert res_gen.status_code == 200
        token = res_gen.json().get("token")
        window = res_gen.json().get("window")
        assert token, "Không lấy được token từ /api/auth3/guest_qr_current"
        from simulator.auth_3layer import get_auth_3layer_manager
        mgr3 = get_auth_3layer_manager()
        if hasattr(mgr3, "used_qr_tokens"):
            mgr3.used_qr_tokens.discard(token)
        res_valid = client.post("/api/auth3/guest_handshake", json={"token": token, "duration": "1d", "window": window})
        assert res_valid.status_code == 200
        data = res_valid.json()
        assert data.get("ok") is True, f"Bắt tay token hợp lệ thất bại: {data}"
        assert "session" in data or "session_id" in data


# =============================================================================
# 7. KIỂM THỬ CHÍNH SÁCH ANDROID SCOPE FROZEN (REQUIREMENT R3)
# =============================================================================
class TestAndroidScopePolicy:
    """Kiểm tra chính sách Requirement R3: Mã nguồn Android Compose được giữ nguyên trạng."""

    def test_android_main_screen_frozen_and_valid(self):
        main_screen_path = ROOT / "android_app" / "app-core" / "src" / "main" / "kotlin" / "vn" / "edu" / "hust" / "seee" / "smarthome" / "ui" / "main" / "MainScreen.kt"
        assert main_screen_path.exists(), f"Không tìm thấy file {main_screen_path}"
        content = main_screen_path.read_text(encoding="utf-8")
        assert "package vn.edu.hust.seee.smarthome.ui.main" in content
        assert "@Composable" in content
        assert "fun MainScreen" in content
