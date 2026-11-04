"""Comprehensive Empirical QA Test Suite for Phase 2 (Live Flows & Specifications).

Validates:
1. Server Reachability on http://localhost:8088 and TestClient.
2. 3-Role Live User Flows:
   - Chủ nhà (Tier 1): nep94121@gmail.com / 123456 (Full access, door/alarm control, 3D labels, telemetry).
   - Gia đình (Tier 2): thanhviena.hust@gmail.com / GiaDinh@123 (Standard control, door/alarm RBAC blocked).
   - Khách (Tier 3): khachc.guest@gmail.com / Khach@789 + Dynamic QR TOTP handshake (Guest access, limited duration, RBAC blocked).
3. Web Error Pages & Service Worker:
   - GET /offline.html
   - GET /404.html (Browser HTML 404 vs API JSON 404 content negotiation)
   - GET /500.html
   - GET /qr_expired.html
   - GET /403.html
   - GET /sw.js with Service-Worker-Allowed: / header
4. Mobile /app 5 Screens (M1 to M5 DOM and Behavior).
"""

from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import pytest
from starlette.testclient import TestClient

from simulator.server import app

BASE_URL = "http://127.0.0.1:8088"
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _http_get(path: str, headers: dict[str, str] | None = None) -> tuple[int, bytes, dict[str, str]]:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def _http_post(path: str, data: dict[str, Any], headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any], dict[str, str]]:
    url = f"{BASE_URL}{path}"
    post_data = json.dumps(data).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=post_data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}, dict(response.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}
        return e.code, parsed, dict(e.headers)


class TestRequirement1ServerReachable:
    """R1: Đảm bảo máy chủ hoạt động và truy cập được tại http://localhost:8088."""

    def test_live_server_root_accessible(self):
        code, body, headers = _http_get("/")
        assert code == 200, f"Expected 200 OK from live server root, got {code}"
        assert b"Smart Home" in body or b"Ng\xc3\xb4i nh\xc3\xa0" in body
        assert b"house3dViewport" in body

    def test_live_server_state_api(self):
        code, body, headers = _http_get("/api/state")
        assert code == 200
        data = json.loads(body.decode("utf-8"))
        assert "devices" in data
        assert isinstance(data["devices"], list)
        assert len(data["devices"]) >= 7
        dev_ids = [d["id"] for d in data["devices"]]
        assert "main_door" in dev_ids
        assert "living_room_light" in dev_ids
        assert "bedroom_light" in dev_ids
        assert "fan" in dev_ids
        assert "ac" in dev_ids
        assert "alarm_siren" in dev_ids
        assert "garden_pump" in dev_ids
        assert "mqtt" in data
        assert "dht11_telemetry" in data["mqtt"]

    def test_testclient_sanity(self):
        client = TestClient(app)
        res = client.get("/api/state")
        assert res.status_code == 200
        snap = res.json()
        assert "devices" in snap
        assert any(d["id"] == "main_door" for d in snap["devices"])


class TestRequirement2ThreeUserRoles:
    """R2: Kiểm thử luồng người dùng thực tế cho cả 3 vai trò (Chủ nhà, Gia đình, Khách)."""

    def test_role_chu_nha_tier1_full_access(self):
        """Chủ nhà: nep94121@gmail.com / 123456 -> Tier 1 ADMIN, điều khiển cửa/còi và toàn bộ thiết bị."""
        # 1. Đăng nhập Lớp 1
        code, res, _ = _http_post("/api/auth3/layer1_login", {
            "email": "nep94121@gmail.com",
            "password": "123456",
            "login_method": "password",
            "source": "QA_Test_Live",
            "send_gmail": False,
        })
        assert code == 200
        assert res.get("ok") is True
        assert res.get("tier") == 1
        assert res.get("account", {}).get("account_id") == "tuan_anh"
        assert "Chủ nhà" in res.get("account", {}).get("role_label", "")

        # 2. Điều khiển Cửa chính (D1) -> Chủ nhà mở được
        code, act_res, _ = _http_post("/api/device", {
            "device_id": "main_door",
            "action": "open",
            "source": "QA_Test_Live",
        })
        assert code == 200
        assert act_res.get("ok") is True
        assert act_res.get("tier") == 1
        assert act_res.get("rbac_blocked") is False

        # Đóng lại cửa
        _http_post("/api/device", {"device_id": "main_door", "action": "close", "source": "QA_Test_Live"})

        # 3. Điều khiển Còi báo động (D8) -> Chủ nhà bật/tắt được
        code, alarm_res, _ = _http_post("/api/device", {
            "device_id": "alarm_siren",
            "action": "turn_on",
            "source": "QA_Test_Live",
        })
        assert code == 200
        assert alarm_res.get("ok") is True
        assert alarm_res.get("tier") == 1
        assert alarm_res.get("rbac_blocked") is False

        # Tắt còi
        _http_post("/api/device", {"device_id": "alarm_siren", "action": "turn_off", "source": "QA_Test_Live"})

        # 4. Điều khiển các thiết bị sinh hoạt: Đèn khách, Đèn ngủ, Quạt, Bơm
        for dev in ["living_room_light", "bedroom_light", "fan", "garden_pump"]:
            code, dev_res, _ = _http_post("/api/device", {
                "device_id": dev,
                "action": "turn_on",
                "source": "QA_Test_Live",
            })
            assert code == 200
            assert dev_res.get("ok") is True

        # 5. Kiểm tra Telemetry và 3D House Labels
        code, state_bytes, _ = _http_get("/api/state")
        assert code == 200
        state = json.loads(state_bytes.decode("utf-8"))
        assert state["current_user_id"] == "tuan_anh"
        assert state["current_tier"] == 1

    def test_role_gia_dinh_tier2_restricted(self):
        """Gia đình: thanhviena.hust@gmail.com / GiaDinh@123 -> Tier 2 MEMBER, điều khiển sinh hoạt, BỊ CHẶN cửa/còi."""
        # 1. Đăng nhập Lớp 1
        code, res, _ = _http_post("/api/auth3/layer1_login", {
            "email": "thanhviena.hust@gmail.com",
            "password": "GiaDinh@123",
            "login_method": "password",
            "source": "QA_Test_Live",
            "send_gmail": False,
        })
        assert code == 200
        assert res.get("ok") is True
        assert res.get("tier") == 2
        assert res.get("account", {}).get("account_id") == "thanh_vien_a"
        assert "Người nhà" in res.get("account", {}).get("role_label", "")

        # 2. Điều khiển thiết bị tiêu chuẩn: Đèn phòng khách, Quạt -> Thành công
        code, dev_res, _ = _http_post("/api/device", {
            "device_id": "living_room_light",
            "action": "turn_on",
            "source": "QA_Test_Live",
        })
        assert code == 200
        assert dev_res.get("ok") is True
        assert dev_res.get("tier") == 2

        # 3. Thao tác Cửa chính (D1) -> BỊ CHẶN BỞI PHÂN QUYỀN RBAC
        code, door_res, _ = _http_post("/api/device", {
            "device_id": "main_door",
            "action": "open",
            "source": "QA_Test_Live",
        })
        assert code == 200
        assert door_res.get("ok") is False
        assert door_res.get("rbac_blocked") is True
        assert "Bị chặn" in door_res.get("error", "") or "Cấp 1" in door_res.get("error", "") or "không có quyền" in door_res.get("error", "")

        # 4. Thao tác Còi báo động (D8) -> BỊ CHẶN BỞI PHÂN QUYỀN RBAC
        code, alarm_res, _ = _http_post("/api/device", {
            "device_id": "alarm_siren",
            "action": "turn_on",
            "source": "QA_Test_Live",
        })
        assert code == 200
        assert alarm_res.get("ok") is False
        assert alarm_res.get("rbac_blocked") is True

    def test_role_khach_tier3_dynamic_qr_totp_and_login(self):
        """Khách: Dynamic QR TOTP handshake token + login khachc.guest@gmail.com / Khach@789 -> Tier 3 CHILD_GUEST."""
        # 1. Sinh mã QR TOTP động với thời hạn 1 ngày
        code, qr_res, _ = _http_get("/api/auth3/guest_qr_current?duration=1d&host=localhost:8088")
        assert code == 200
        assert qr_res.get("ok") is True if isinstance(qr_res, dict) else True
        if not isinstance(qr_res, dict):
            qr_res = json.loads(qr_res.decode("utf-8"))
        assert "token" in qr_res
        assert "window" in qr_res
        assert "qr_svg" in qr_res
        token = qr_res["token"]
        window = qr_res["window"]

        # 2. Khách thực hiện bắt tay (Handshake)
        code, hs_res, _ = _http_post("/api/auth3/guest_qr_handshake", {
            "token": token,
            "window": window,
            "duration": "1d",
        })
        assert code == 200
        assert hs_res.get("ok") is True
        assert hs_res.get("duration_code") == "1d"
        assert "guest_sess" in hs_res.get("guest_session_id", "")

        # 3. Đăng nhập với tài khoản Khách C
        code, res, _ = _http_post("/api/auth3/layer1_login", {
            "email": "khachc.guest@gmail.com",
            "password": "Khach@789",
            "login_method": "password",
            "source": "QA_Test_Live",
            "send_gmail": False,
        })
        assert code == 200
        assert res.get("ok") is True
        assert res.get("tier") == 3
        assert res.get("account", {}).get("account_id") == "khach_c"
        assert "Khách" in res.get("account", {}).get("role_label", "")

        # 4. Khách điều khiển đèn cơ bản -> Thành công
        code, light_res, _ = _http_post("/api/device", {
            "device_id": "living_room_light",
            "action": "turn_on",
            "source": "QA_Test_Live",
        })
        assert code == 200
        assert light_res.get("ok") is True
        assert light_res.get("tier") == 3

        # 5. Khách thử mở cửa -> BỊ CHẶN
        code, door_res, _ = _http_post("/api/device", {
            "device_id": "main_door",
            "action": "open",
            "source": "QA_Test_Live",
        })
        assert code == 200
        assert door_res.get("ok") is False
        assert door_res.get("rbac_blocked") is True

        # 6. Khách thử tạo lịch hẹn giờ -> BỊ CHẶN THEO RBAC (HTTP 403 Forbidden hoặc ok: False)
        code, sched_res, _ = _http_post("/api/mobile/schedule", {
            "device_id": "living_room_light",
            "action": "turn_on",
            "seconds": 30,
            "tier": 3,
            "user_name": "Khách C",
        })
        assert code in (200, 403)
        assert sched_res.get("ok") is False
        assert "Khách (Cấp 3)" in sched_res.get("error", "") or "Từ chối" in sched_res.get("error", "")

        # Trả lại phiên Chủ nhà sau bài test
        _http_post("/api/session/role", {"role": "tuan_anh"})


class TestRequirement3WebErrorPages:
    """R3: Kiểm thử toàn bộ các trang lỗi mới, Content-Negotiation và Service Worker."""

    def test_offline_page(self):
        code, body, _ = _http_get("/offline.html")
        assert code == 200
        html = body.decode("utf-8")
        assert "Mất kết nối" in html
        assert "wifi-off" in html or "M3 3l18 18" in html
        assert "btnRetryNow" in html
        assert "checkConnection" in html

    def test_404_page_direct(self):
        code, body, _ = _http_get("/404.html")
        assert code == 404
        html = body.decode("utf-8")
        assert "Không tìm thấy trang" in html
        assert "Về Trang chủ" in html
        assert "Mở Ứng dụng Điện thoại" in html

    def test_content_negotiation_browser_navigation_404(self):
        """Điều hướng ngẫu nhiên với Accept: text/html -> Trả về HTML 404."""
        code, body, headers = _http_get("/random_browser_page_does_not_exist_404", headers={"Accept": "text/html,application/xhtml+xml"})
        assert code == 404
        content_type = headers.get("content-type", "")
        assert "text/html" in content_type
        html = body.decode("utf-8")
        assert "doctype html" in html.lower()
        assert "Không tìm thấy trang" in html

    def test_content_negotiation_api_404(self):
        """Yêu cầu tới /api/some_random -> Giữ nguyên JSON 404."""
        code, body, headers = _http_get("/api/some_random_endpoint_that_does_not_exist_404")
        assert code == 404
        content_type = headers.get("content-type", "")
        assert "application/json" in content_type
        data = json.loads(body.decode("utf-8"))
        assert "detail" in data
        assert data["detail"] == "Not Found"

    def test_content_negotiation_json_client_404(self):
        """Yêu cầu tới URL lạ với Accept: application/json -> Trả về JSON 404."""
        code, body, headers = _http_get("/unknown_endpoint_from_api_client", headers={"Accept": "application/json"})
        assert code == 404
        content_type = headers.get("content-type", "")
        assert "application/json" in content_type
        data = json.loads(body.decode("utf-8"))
        assert data.get("detail") == "Not Found"

    def test_500_page(self):
        code, body, _ = _http_get("/500.html")
        assert code == 500
        html = body.decode("utf-8")
        assert "Hệ thống đang bận" in html or "500" in html
        assert "Tải lại trang" in html
        assert "Về Trang chủ" in html

    def test_qr_expired_page(self):
        code, body, _ = _http_get("/qr_expired.html")
        assert code == 200
        html = body.decode("utf-8")
        assert "Mã QR đã hết hạn" in html
        assert "Quét mã mới" in html
        assert "Nhập mã mới" in html

    def test_403_page(self):
        code, body, _ = _http_get("/403.html")
        assert code == 403
        html = body.decode("utf-8")
        assert "Không đủ quyền truy cập" in html
        assert "Khách · Cấp 3" in html
        assert "Quay về Nhà" in html
        assert "Đăng nhập tài khoản khác" in html

    def test_service_worker_file_and_header(self):
        code, body, headers = _http_get("/sw.js")
        assert code == 200
        assert headers.get("service-worker-allowed") == "/"
        content = body.decode("utf-8")
        assert "CACHE_NAME" in content
        assert "offline.html" in content
        assert "navigate" in content


class TestRequirement4MobileAppFiveScreens:
    """R4: Kiểm thử 5 màn hình Mobile /app và các phần tử giao diện theo đúng đặc tả."""

    @pytest.fixture
    def mobile_html(self) -> str:
        code, body, _ = _http_get("/app")
        assert code == 200
        return body.decode("utf-8")

    def test_m1_home_screen_elements(self, mobile_html: str):
        """M1: Home preview 16:9, dual sensors (temp & soil moisture), door/alarm status, quick action buttons."""
        assert 'id="mobileOverviewBox"' in mobile_html
        assert "preview-16-9" in mobile_html
        assert 'id="mobileDisplayTemp"' in mobile_html
        assert 'id="mobileDisplaySoil"' in mobile_html
        assert 'id="mobileMainDoorStatus"' in mobile_html
        assert 'id="mobileAlarmSirenStatus"' in mobile_html
        assert 'id="mobileBtnVoiceSheet"' in mobile_html
        assert 'id="mobileBtnViewDevices"' in mobile_html

    def test_m2_four_tabs_and_account_hierarchy(self, mobile_html: str):
        """M2: 4-tab switcher (Home, Devices, Voice, Account) & Account profile hierarchy."""
        # 4 tab navigation buttons
        assert 'id="mobileNavTabHome"' in mobile_html
        assert 'id="mobileNavTabDevices"' in mobile_html
        assert 'id="mobileNavTabVoice"' in mobile_html
        assert 'id="mobileNavTabAccount"' in mobile_html

        # 4 separate tab views
        assert 'id="tabViewHome"' in mobile_html
        assert 'id="tabViewDevices"' in mobile_html
        assert 'id="tabViewVoice"' in mobile_html
        assert 'id="tabViewAccount"' in mobile_html

        # Account hierarchy
        assert 'id="mobileProfileRole"' in mobile_html
        assert 'id="mobileProfileEmail"' in mobile_html
        assert 'id="mobileProfileDuration"' in mobile_html
        assert 'id="mobileBtnLogout"' in mobile_html

    def test_m3_forgot_password_three_steps(self, mobile_html: str):
        """M3: Forgot password 3-step OTP flow."""
        assert 'id="mobileForgotPasswordPanel"' in mobile_html
        assert 'id="mobileForgotEmail"' in mobile_html
        assert 'id="mobileBtnForgotSendOtp"' in mobile_html
        assert 'id="mobileForgotOtp"' in mobile_html
        assert 'pattern="[0-9]{6}"' in mobile_html
        assert 'inputmode="numeric"' in mobile_html
        assert 'id="mobileForgotNewPassword"' in mobile_html
        assert 'id="mobileForgotConfirmPassword"' in mobile_html
        assert 'id="mobileBtnForgotSubmitReset"' in mobile_html

    def test_m4_voice_bottom_sheet_wavecircle_bars(self, mobile_html: str):
        """M4: Voice bottom sheet with wavecircle, 12 volume bars, 5s timer."""
        assert 'id="mobileVoiceBottomSheet"' in mobile_html
        assert 'id="mobileVoiceSheetScrim"' in mobile_html
        assert "wavecircle" in mobile_html
        assert 'id="mobileVoiceVolumeBars"' in mobile_html
        # Verify exactly 12 <i> tags inside bars
        bars_section = mobile_html.split('id="mobileVoiceVolumeBars"')[1].split('</div>')[0]
        i_count = bars_section.count("<i ")
        assert i_count == 12, f"Expected exactly 12 volume bars, found {i_count}"
        assert 'id="mobileVoiceTimer"' in mobile_html
        assert 'id="mobileVoicePhrase"' in mobile_html
        assert 'id="mobileVoiceSheetResult"' in mobile_html

    def test_m5_camera_qr_scanner_viewfinder(self, mobile_html: str):
        """M5: Camera QR scanner viewfinder with 4-corner styling."""
        assert 'id="mobileQrScannerModal"' in mobile_html
        assert 'id="mobileQrVideo"' in mobile_html
        assert 'id="mobileScanFrame"' in mobile_html
        assert 'class="tl"' in mobile_html
        assert 'class="tr"' in mobile_html
        assert 'class="bl"' in mobile_html
        assert 'class="br"' in mobile_html
        assert 'id="mobileBtnStartCamera"' in mobile_html
        assert 'id="mobileBtnManualCodeInput"' in mobile_html
