"""Comprehensive Empirical QA Test Suite for Phase 2 (Live Flows & Specifications).

Validates on isolated uvicorn (or SMARTHOME_LIVE_BASE_URL):
1. Server Reachability and TestClient.
2. 3-Role Live User Flows with real X-Session-Token auth:
   - Chủ nhà (Tier 1): nep94121@gmail.com (Layer 1 + Layer 2 OTP, door/alarm & devices).
   - Gia đình (Tier 2): thanhviena.hust@gmail.com (Layer 1 direct login, door/alarm RBAC blocked).
   - Khách (Tier 3): PIN-signed QR invite `/api/guest/invites` -> `/api/guest/redeem` (single-use Tier 3 session) + `khachc.guest@gmail.com` login, legacy endpoints return 405/410.
3. Web Error Pages & Service Worker.
4. Mobile /app 5 Screens (M1 to M5 DOM and Behavior).
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
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import pytest
from starlette.testclient import TestClient
import uvicorn

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.auth.constants_and_crypto import ACCOUNTS_FILE, hash_password
from backend.auth.invite_and_gmail_mixin import AuthInviteGmailMixin
from backend.auth_3layer import get_auth_3layer_manager
from backend.server import _ACTIVE_BRIDGES, _REST_ENGINE, app

BASE_URL = os.environ.get("SMARTHOME_LIVE_BASE_URL", "").strip() or "http://127.0.0.1:8088"
_EPHEMERAL_PASSWORDS: dict[str, str] = {}


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module", autouse=True)
def live_qa_env():
    """Khởi chạy máy chủ kiểm thử cô lập (nếu chưa có SMARTHOME_LIVE_BASE_URL) và chặn gửi email thật."""
    global BASE_URL
    prev_url = BASE_URL
    prev_pytest = os.environ.get("PYTEST")
    prev_gmail = os.environ.get("GMAIL_APP_PASSWORD")
    prev_smtp = os.environ.get("SMTP_PASSWORD")
    orig_send = AuthInviteGmailMixin.send_real_gmail_otp
    os.environ["PYTEST"] = "1"
    os.environ["GMAIL_APP_PASSWORD"] = ""
    os.environ["SMTP_PASSWORD"] = ""
    AuthInviteGmailMixin.send_real_gmail_otp = lambda self, *a, **kw: {
        "sent_real_gmail": False,
        "blocked_by_allowlist": False,
        "status": "MOCKED_TEST",
    }

    mgr = get_auth_3layer_manager()
    orig_db_bytes = ACCOUNTS_FILE.read_bytes() if ACCOUNTS_FILE.exists() else None
    emails = ("nep94121@gmail.com", "thanhviena.hust@gmail.com", "khachc.guest@gmail.com")
    orig_hashes: dict[str, str] = {}
    _EPHEMERAL_PASSWORDS.clear()
    for em in emails:
        acc = mgr.find_account(em)
        assert acc is not None, f"Missing account {em}"
        orig_hashes[em] = str(acc.get("password_hash") or "")
        pw = f"EphemeralQa_{secrets.token_hex(6)}!"
        acc["password_hash"] = hash_password(pw)
        acc["permission_active"] = True
        acc["permission_status"] = "ACTIVE"
        _EPHEMERAL_PASSWORDS[em] = pw

    ext = os.environ.get("SMARTHOME_LIVE_BASE_URL", "").strip()
    server = None
    thread = None
    if ext:
        BASE_URL = ext.rstrip("/")
    else:
        port = _get_free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        BASE_URL = f"http://127.0.0.1:{port}"
        for _ in range(80):
            try:
                with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=0.5) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.1)

    try:
        yield {"base_url": BASE_URL, "passwords": dict(_EPHEMERAL_PASSWORDS)}
    finally:
        BASE_URL = prev_url
        _EPHEMERAL_PASSWORDS.clear()
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
        for em, h in orig_hashes.items():
            acc = mgr.find_account(em)
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
    """R1: Đảm bảo máy chủ kiểm thử hoạt động và truy cập được qua HTTP."""

    def test_live_server_root_accessible(self):
        code, body, _headers = _http_get("/")
        assert code == 200, f"Expected 200 OK from live server root, got {code}"
        assert b"Smart Home" in body or b"Ng\xc3\xb4i nh\xc3\xa0" in body
        assert b"house3dViewport" in body

    def test_live_server_state_api(self):
        unauth_code, _, _ = _http_get("/api/state")
        assert unauth_code == 401, f"Expected 401 for unauthenticated /api/state, got {unauth_code}"
        t1_headers = TestRequirement2ThreeUserRoles()._login_owner_headers()
        code, body, _headers = _http_get("/api/state", headers=t1_headers)
        assert code == 200
        data = json.loads(body.decode("utf-8"))
        assert "devices" in data
        assert isinstance(data["devices"], list)
        assert len(data["devices"]) == 6
        dev_ids = [d["id"] for d in data["devices"]]
        for req_id in ("main_door", "living_room_light", "bedroom_light", "garden_pump", "alarm_siren", "speaker_amp"):
            assert req_id in dev_ids
        assert "mqtt" in data
        assert "dht11_telemetry" in data["mqtt"]

    def test_testclient_sanity(self):
        client = TestClient(app)
        unauth = client.get("/api/state")
        assert unauth.status_code == 401
        res = client.get("/api/state", headers={"X-Session-Token": "sess_owner_t1_nep94121"})
        assert res.status_code == 200
        snap = res.json()
        assert "devices" in snap
        assert any(d["id"] == "main_door" for d in snap["devices"])


class TestRequirement2ThreeUserRoles:
    """R2: Kiểm thử luồng người dùng thực tế cho cả 3 vai trò (Chủ nhà, Gia đình, Khách) kèm session token."""

    def _login_owner_headers(self) -> dict[str, str]:
        code, res, _ = _http_post("/api/auth3/layer1_login", {
            "email": "nep94121@gmail.com",
            "password": _EPHEMERAL_PASSWORDS["nep94121@gmail.com"],
            "login_method": "password",
            "source": "QA_Test_Live",
            "send_gmail": False,
        })
        assert code == 200 and res.get("ok") is True and res.get("tier") == 1
        assert res.get("account", {}).get("account_id") == "tuan_anh"
        if res.get("session_token"):
            return {"X-Session-Token": str(res["session_token"])}
        otp = str(res.get("otp_code_for_test") or res.get("otp_code_for_test_table") or res.get("demo_otp_preview") or "")
        assert len(otp) == 6, f"Missing test OTP in response keys: {list(res.keys())}"
        vcode, vres, _ = _http_post("/api/auth3/layer2_verify_otp", {
            "email": "nep94121@gmail.com",
            "otp_code": otp,
            "source": "QA_Test_Live",
        })
        assert vcode == 200 and vres.get("ok") is True and vres.get("session_token")
        return {"X-Session-Token": str(vres["session_token"])}

    def test_role_chu_nha_tier1_full_access(self):
        """Chủ nhà Tier 1 ADMIN điều khiển cửa/còi và toàn bộ thiết bị rồi tắt sạch."""
        t1_headers = self._login_owner_headers()

        code, act_res, _ = _http_post("/api/device", {"device_id": "main_door", "action": "open", "source": "QA_Test_Live"}, headers=t1_headers)
        assert code == 200 and act_res.get("ok") is True and act_res.get("tier") == 1 and act_res.get("rbac_blocked") is False
        _http_post("/api/device", {"device_id": "main_door", "action": "close", "source": "QA_Test_Live"}, headers=t1_headers)

        code, alarm_res, _ = _http_post("/api/device", {"device_id": "alarm_siren", "action": "turn_on", "source": "QA_Test_Live"}, headers=t1_headers)
        assert code == 200 and alarm_res.get("ok") is True and alarm_res.get("tier") == 1 and alarm_res.get("rbac_blocked") is False
        _http_post("/api/device", {"device_id": "alarm_siren", "action": "turn_off", "source": "QA_Test_Live"}, headers=t1_headers)

        for dev in ("living_room_light", "bedroom_light", "garden_pump", "speaker_amp"):
            code, dev_res, _ = _http_post("/api/device", {"device_id": dev, "action": "turn_on", "source": "QA_Test_Live"}, headers=t1_headers)
            assert code == 200 and dev_res.get("ok") is True
            _http_post("/api/device", {"device_id": dev, "action": "turn_off", "source": "QA_Test_Live"}, headers=t1_headers)

        code, state_bytes, _ = _http_get("/api/state", headers=t1_headers)
        assert code == 200
        state = json.loads(state_bytes.decode("utf-8"))
        assert state["current_user_id"] == "tuan_anh"
        assert state["current_tier"] == 1

    def test_role_gia_dinh_tier2_restricted(self):
        """Gia đình Tier 2 MEMBER điều khiển đèn, BỊ CHẶN cửa/còi theo RBAC."""
        code, res, _ = _http_post("/api/auth3/layer1_login", {
            "email": "thanhviena.hust@gmail.com",
            "password": _EPHEMERAL_PASSWORDS["thanhviena.hust@gmail.com"],
            "login_method": "password",
            "source": "QA_Test_Live",
            "send_gmail": False,
        })
        assert code == 200 and res.get("ok") is True and res.get("tier") == 2
        assert res.get("account", {}).get("account_id") == "thanh_vien_a"
        assert res.get("session_token")
        t2_headers = {"X-Session-Token": str(res["session_token"])}

        code, dev_res, _ = _http_post("/api/device", {"device_id": "living_room_light", "action": "turn_on", "source": "QA_Test_Live"}, headers=t2_headers)
        assert code == 200 and dev_res.get("ok") is True and dev_res.get("tier") == 2
        _http_post("/api/device", {"device_id": "living_room_light", "action": "turn_off", "source": "QA_Test_Live"}, headers=t2_headers)

        code, door_res, _ = _http_post("/api/device", {"device_id": "main_door", "action": "open", "source": "QA_Test_Live"}, headers=t2_headers)
        assert code in (200, 403)
        assert door_res.get("ok") is False and door_res.get("rbac_blocked") is True

        code, alarm_res, _ = _http_post("/api/device", {"device_id": "alarm_siren", "action": "turn_on", "source": "QA_Test_Live"}, headers=t2_headers)
        assert code in (200, 403)
        assert alarm_res.get("ok") is False and alarm_res.get("rbac_blocked") is True

    def test_role_khach_tier3_dynamic_qr_totp_and_login(self):
        """Khách Tier 3: legacy QR voice/handshake trả 405/410; PIN-signed invite -> redeem 1 lần; bị chặn cửa & lịch."""
        ret_get_code, _, _ = _http_get("/api/auth3/guest_qr_current?duration=1d&host=localhost:8088")
        assert ret_get_code in (405, 410)
        ret_hs_code, _, _ = _http_post("/api/auth3/guest_qr_handshake", {"token": "legacy"})
        assert ret_hs_code == 410

        t1_headers = self._login_owner_headers()
        code, inv, _ = _http_post("/api/guest/invites", {
            "pin": "1357",
            "pin_confirm": "1357",
            "duration_code": "1d",
            "guest_name": "Khách QA",
        }, headers=t1_headers)
        assert code == 200 and inv.get("ok") is True and inv.get("duration_code") == "1d"
        assert "<svg" in inv.get("qr_svg", "") and "/guest?token=" in inv.get("url", "")
        token = inv["url"].split("token=", 1)[1].split("&", 1)[0]

        rcode, rdata, _ = _http_post("/api/guest/redeem", {"token": token})
        assert rcode == 200 and rdata.get("ok") is True and rdata.get("tier") == 3
        assert rdata.get("duration_code") == "1d" and rdata.get("session_token")
        g_headers = {"X-Session-Token": str(rdata["session_token"])}

        # Đăng nhập tài khoản Khách C cũng nhận session Cấp 3
        lcode, lres, _ = _http_post("/api/auth3/layer1_login", {
            "email": "khachc.guest@gmail.com",
            "password": _EPHEMERAL_PASSWORDS["khachc.guest@gmail.com"],
            "login_method": "password",
            "source": "QA_Test_Live",
            "send_gmail": False,
        })
        assert lcode == 200 and lres.get("ok") is True and lres.get("tier") == 3
        assert lres.get("account", {}).get("account_id") == "khach_c"

        # Khách QR bật đèn thành công, bị chặn mở cửa và tạo lịch
        code, light_res, _ = _http_post("/api/device", {"device_id": "living_room_light", "action": "turn_on", "source": "QA_Test_Live"}, headers=g_headers)
        assert code == 200 and light_res.get("ok") is True and light_res.get("tier") == 3
        _http_post("/api/device", {"device_id": "living_room_light", "action": "turn_off", "source": "QA_Test_Live"}, headers=g_headers)

        code, door_res, _ = _http_post("/api/device", {"device_id": "main_door", "action": "open", "source": "QA_Test_Live"}, headers=g_headers)
        assert code in (200, 403) and door_res.get("ok") is False and door_res.get("rbac_blocked") is True

        code, sched_res, _ = _http_post("/api/mobile/schedule", {
            "device_id": "living_room_light",
            "action": "turn_on",
            "seconds": 30,
        }, headers=g_headers)
        assert code in (200, 403) and sched_res.get("ok") is False
        assert "Khách" in sched_res.get("error", "") or "Từ chối" in sched_res.get("error", "") or "Cấp 3" in sched_res.get("error", "")

        try:
            _REST_ENGINE.set_device_state("living_room_light", "OFF", source="test_cleanup", tier=1)
        except Exception:
            pass



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
        """U3a/U3b: Đã gỡ #mobileOverviewBox & nút trùng #mobileBtnViewDevices, giữ cảm biến & an toàn."""
        assert 'id="mobileOverviewBox"' not in mobile_html
        assert 'id="mobileBtnViewDevices"' not in mobile_html
        assert 'id="mobileDisplayTemp"' in mobile_html
        assert 'id="mobileDisplaySoil"' in mobile_html
        assert 'id="mobileMainDoorStatus"' in mobile_html
        assert 'id="mobileAlarmSirenStatus"' in mobile_html
        assert 'id="mobileBtnVoiceSheet"' in mobile_html

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
