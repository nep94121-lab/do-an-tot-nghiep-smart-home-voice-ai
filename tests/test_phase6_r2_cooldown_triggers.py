"""Milestone 2 Test Suite: R2 Anti-Double-Send Cooldown & Trigger Fixes.

Verifies:
1. Subsequent OTP requests for the same recipient within 60s return idempotent status
   (idempotent=True, cooldown_active=True), do NOT dispatch duplicate emails, and preserve active OTP.
2. OTP requested after 60s or expired OTP generates a new OTP and dispatches.
3. Once reset_password_with_otp succeeds, the consumed OTP is destroyed and cannot be reused (anti-replay).
4. Concurrency: multiple simultaneous requests for the same recipient do not trigger multiple email
   dispatches (thread-safe synchronization via self._otp_lock).
5. Frontend static checks: verify elimination of form submit -> button.click() double-triggers,
   presence of inFlight/disabled handling on submit and OTP buttons, and 60-second countdown timer.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import pathlib
import re
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from simulator.auth_3layer import ThreeLayerAuthManager
from simulator.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clean_pending_otps_state(monkeypatch: pytest.MonkeyPatch):
    from simulator.api.routes_auth import get_auth_3layer_manager

    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("REAL_EMAIL_ALLOWLIST", "senat6031@gmail.com")
    mgr = get_auth_3layer_manager()
    lock = getattr(mgr, "_otp_lock", threading.Lock())
    with lock:
        mgr.pending_otps.clear()
    yield
    with lock:
        mgr.pending_otps.clear()


@pytest.fixture
def auth_mgr() -> ThreeLayerAuthManager:
    from simulator.api.routes_auth import get_auth_3layer_manager

    return get_auth_3layer_manager()


class TestPhase6R2BackendCooldownAndIdempotency:
    """Kiểm thử tính năng Cooldown 60s và Idempotency phía Backend."""

    def test_r2_first_otp_request_succeeds_and_dispatches_email(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Yêu cầu OTP lần đầu tạo OTP mới và chuyển phát email."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "mock app password"}), patch(
            "smtplib.SMTP", return_value=mock_smtp
        ):
            res = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "senat6031@gmail.com", "send_gmail": True},
            )
            data = res.json()
            assert res.status_code == 200
            assert data.get("ok") is True
            assert data.get("idempotent") is not True
            assert data.get("cooldown_active") is not True

            # Kiểm tra OTP đã được ghi nhận trong pending_otps
            pending = auth_mgr.pending_otps.get("senat6031@gmail.com")
            assert pending is not None
            assert len(pending.get("otp_code", "")) == 6

    def test_r2_subsequent_request_within_60s_returns_idempotent_and_preserves_otp(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Yêu cầu OTP lần 2 trong vòng 60 giây trả về idempotent, cooldown_active, không gửi email mới."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "mock app password"}), patch(
            "smtplib.SMTP", return_value=mock_smtp
        ) as mock_smtp_cls:
            # Gửi lần 1
            res1 = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "senat6031@gmail.com", "send_gmail": True},
            )
            assert res1.status_code == 200
            data1 = res1.json()
            pending1 = auth_mgr.pending_otps.get("senat6031@gmail.com")
            assert pending1 is not None
            otp1 = pending1["otp_code"]

            smtp_send_count_after_first = mock_smtp.send_message.call_count + mock_smtp.sendmail.call_count

            # Gửi lần 2 ngay sau đó (elapsed < 60s)
            res2 = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "senat6031@gmail.com", "send_gmail": True},
            )
            assert res2.status_code == 200
            data2 = res2.json()

            # Phải có cờ idempotent và cooldown_active
            assert data2.get("ok") is True
            assert data2.get("idempotent") is True
            assert data2.get("cooldown_active") is True
            assert "cooldown_remaining_seconds" in data2
            assert 0 <= data2["cooldown_remaining_seconds"] <= 60

            # Mã OTP phải được BẢO TOÀN, không được tạo mới hay thay đổi
            assert data2.get("otp_code_for_test") == otp1
            assert data2.get("demo_otp_preview") == otp1
            pending2 = auth_mgr.pending_otps.get("senat6031@gmail.com")
            assert pending2["otp_code"] == otp1

            # KHÔNG được gọi SMTP send thêm lần nào
            current_send_count = mock_smtp.send_message.call_count + mock_smtp.sendmail.call_count
            assert current_send_count == smtp_send_count_after_first

    def test_r2_cooldown_works_in_test_mode_send_gmail_false(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Cơ chế cooldown cũng hoạt động chính xác khi send_gmail=False (chế độ test/demo)."""
        res1 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "senat6031@gmail.com", "send_gmail": False},
        )
        data1 = res1.json()
        assert res1.status_code == 200
        otp1 = data1.get("otp_code_for_test") or data1.get("demo_otp_preview")
        assert otp1 is not None

        # Lần 2 trong 60s
        res2 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "senat6031@gmail.com", "send_gmail": False},
        )
        data2 = res2.json()
        assert res2.status_code == 200
        assert data2.get("idempotent") is True
        assert data2.get("cooldown_active") is True
        assert data2.get("otp_code_for_test") == otp1
        assert data2.get("demo_otp_preview") == otp1

    def test_r2_request_after_60s_generates_new_otp_and_dispatches(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Khi đã trôi qua hơn 60 giây, yêu cầu OTP tiếp theo sinh mã mới và gửi email mới."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "mock app password"}), patch(
            "smtplib.SMTP", return_value=mock_smtp
        ):
            # Lần 1
            res1 = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "senat6031@gmail.com", "send_gmail": True},
            )
            assert res1.status_code == 200
            otp1 = auth_mgr.pending_otps["senat6031@gmail.com"]["otp_code"]

            # Giả lập thời gian trôi qua 61 giây
            auth_mgr.pending_otps["senat6031@gmail.com"]["created_at"] = time.time() - 61.0

            # Lần 2 sau 61 giây
            res2 = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "senat6031@gmail.com", "send_gmail": True},
            )
            assert res2.status_code == 200
            data2 = res2.json()

            # Không còn cooldown
            assert data2.get("idempotent") is not True
            assert data2.get("cooldown_active") is not True

            # Mã OTP mới được cập nhật
            otp2 = auth_mgr.pending_otps["senat6031@gmail.com"]["otp_code"]
            assert otp2 is not None
            # Email thứ 2 được gửi
            assert (mock_smtp.send_message.call_count + mock_smtp.sendmail.call_count) >= 2

    def test_r2_expired_otp_over_300s_generates_new_otp(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Mã OTP đã quá hạn (>300s) cho phép tạo mã OTP mới."""
        # Giả lập mã OTP đã hết hạn
        auth_mgr.pending_otps["senat6031@gmail.com"] = {
            "email": "senat6031@gmail.com",
            "account_id": "senat6031",
            "display_name": "Người dùng Senat",
            "tier": 2,
            "otp_code": "111111",
            "created_at": time.time() - 305.0,
            "expires_at": time.time() - 5.0,
            "verified_layer2": False,
            "verified_layer3": False,
            "gmail_delivery": {"sent_real_gmail": False},
            "source": "Test",
        }

        res = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "senat6031@gmail.com", "send_gmail": False},
        )
        assert res.status_code == 200
        data = res.json()
        assert data.get("idempotent") is not True
        assert data.get("cooldown_active") is not True
        assert data.get("otp_code_for_test") != "111111"

    def test_r2_different_recipients_have_independent_cooldowns(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Cooldown áp dụng riêng biệt cho từng recipient; người A không chặn người B."""
        res_a1 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": False},
        )
        assert res_a1.status_code == 200

        # Người B gửi OTP ngay sau đó -> Vẫn thành công và không bị cooldown của người A
        res_b1 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "senat6031@gmail.com", "send_gmail": False},
        )
        assert res_b1.status_code == 200
        assert res_b1.json().get("idempotent") is not True
        assert res_b1.json().get("cooldown_active") is not True

        # Nhưng người A gửi lại thì bị cooldown
        res_a2 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": False},
        )
        assert res_a2.status_code == 200
        assert res_a2.json().get("idempotent") is True


class TestPhase6R2OtpConsumptionAndDestruction:
    """Kiểm thử tiêu hủy mã OTP sau khi đổi mật khẩu thành công (Anti-Replay)."""

    def test_r2_reset_password_success_destroys_consumed_otp(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Sau khi đặt lại mật khẩu thành công, OTP bị tiêu hủy khỏi pending_otps."""
        # 1. Yêu cầu OTP
        res_otp = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "senat6031@gmail.com", "send_gmail": False},
        )
        assert res_otp.status_code == 200
        otp_code = res_otp.json()["otp_code_for_test"]

        assert "senat6031@gmail.com" in auth_mgr.pending_otps

        target_acc = auth_mgr.find_account("senat6031@gmail.com")
        assert target_acc is not None
        orig_hash = target_acc.get("password_hash", "")
        try:
            # 2. Đặt lại mật khẩu với đúng OTP
            res_reset = client.post(
                "/api/auth3/forgot_password_reset",
                json={
                    "email": "senat6031@gmail.com",
                    "otp_code": otp_code,
                    "new_password": "NewSecretPassword@123",
                    "confirm_password": "NewSecretPassword@123",
                },
            )
            assert res_reset.status_code == 200
            assert res_reset.json().get("ok") is True

            # 3. OTP phải bị tiêu hủy hoàn toàn khỏi pending_otps
            assert "senat6031@gmail.com" not in auth_mgr.pending_otps

            # 4. Thử dùng lại mã OTP vừa rồi (Replay attack) -> Phải thất bại!
            res_replay = client.post(
                "/api/auth3/forgot_password_reset",
                json={
                    "email": "senat6031@gmail.com",
                    "otp_code": otp_code,
                    "new_password": "AnotherPassword@456",
                    "confirm_password": "AnotherPassword@456",
                },
            )
            assert res_replay.json().get("ok") is False
        finally:
            target_acc["password_hash"] = orig_hash
            auth_mgr._save_accounts()


class TestPhase6R2ThreadSafetyAndConcurrency:
    """Kiểm định an toàn đa luồng (Thread-safety): đồng thời gửi request không sinh trùng email."""

    def test_r2_concurrent_requests_trigger_single_email_dispatch(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Nhiều request đồng thời cho cùng 1 email chỉ phát sinh đúng 1 lần gửi mail duy nhất."""
        assert hasattr(auth_mgr, "_otp_lock"), "ThreeLayerAuthManager must have _otp_lock attribute!"

        send_count = 0
        counter_lock = threading.Lock()

        original_send_real_gmail_otp = auth_mgr.send_real_gmail_otp

        def slow_mock_send_real_gmail_otp(email, otp_code, display_name):
            nonlocal send_count
            time.sleep(0.05)  # Giả lập độ trễ mạng để tạo race condition nếu thiếu lock
            with counter_lock:
                send_count += 1
            return {
                "sent_real_gmail": True,
                "actual_recipient": email,
                "gmail_message_id": f"msg_{otp_code}",
            }

        with patch.object(auth_mgr, "send_real_gmail_otp", side_effect=slow_mock_send_real_gmail_otp):
            num_workers = 8
            barrier = threading.Barrier(num_workers)

            def worker_req():
                barrier.wait()
                return client.post(
                    "/api/auth3/forgot_password_send_otp",
                    json={"email": "senat6031@gmail.com", "send_gmail": True},
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(worker_req) for _ in range(num_workers)]
                responses = [f.result() for f in futures]

            # Toàn bộ request đều thành công (HTTP 200)
            for r in responses:
                assert r.status_code == 200
                assert r.json().get("ok") is True

            # Email CHỈ được gửi DUY NHẤT 1 LẦN!
            assert send_count == 1, f"Concurrency failure: send_real_gmail_otp was called {send_count} times!"

            # Trong num_workers responses: có đúng 1 response tạo mới và (num_workers - 1) response là idempotent
            idempotent_count = sum(1 for r in responses if r.json().get("idempotent") is True)
            assert idempotent_count == num_workers - 1

            # Tất cả các response đều mang cùng 1 mã OTP
            active_otp = auth_mgr.pending_otps["senat6031@gmail.com"]["otp_code"]
            for r in responses:
                res_otp = r.json().get("otp_code_for_test") or r.json().get("demo_otp_preview")
                if res_otp:
                    assert res_otp == active_otp


class TestPhase6R2FrontendStaticChecks:
    """Kiểm tra tĩnh cấu trúc frontend: loại bỏ kích hoạt kép và quản lý inFlight/disabled."""

    def test_r2_app_js_removes_form_submit_button_click_recursion(self):
        """simulator/static/js/app.js không còn đoạn submit event listener gọi trực tiếp .click() của nút submit."""
        app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
        assert app_js_path.exists()
        code = app_js_path.read_text(encoding="utf-8")

        # Kiểm tra không có code submit gọi button.click() trong submit listener
        pattern_login = re.search(
            r'gatePanelLogin\.addEventListener\(\s*["\']submit["\'].*?btnSubmitGateLogin\.click\(\)',
            code,
            re.DOTALL,
        )
        assert pattern_login is None, (
            "app.js vẫn còn đoạn gatePanelLogin submit gọi btnSubmitGateLogin.click() gây kích hoạt kép!"
        )

        pattern_reg = re.search(
            r'gatePanelRegister\.addEventListener\(\s*["\']submit["\'].*?btnSubmitGateRegister\.click\(\)',
            code,
            re.DOTALL,
        )
        assert pattern_reg is None, (
            "app.js vẫn còn đoạn gatePanelRegister submit gọi btnSubmitGateRegister.click() gây kích hoạt kép!"
        )

        pattern_forgot = re.search(
            r'gatePanelForgot\.addEventListener\(\s*["\']submit["\'].*?btnSubmitForgotReset\.click\(\)',
            code,
            re.DOTALL,
        )
        assert pattern_forgot is None, (
            "app.js vẫn còn đoạn gatePanelForgot submit gọi btnSubmitForgotReset.click() gây kích hoạt kép!"
        )

    def test_r2_app_js_has_inflight_and_disabled_on_buttons(self):
        """app.js quản lý inFlight và disabled=true trong quá trình fetch cho các nút auth."""
        app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
        code = app_js_path.read_text(encoding="utf-8")

        # Kiểm tra cờ inFlight
        assert "isGateLoginInFlight" in code, "Thiếu cờ isGateLoginInFlight trong app.js"
        assert "isGateRegisterInFlight" in code, "Thiếu cờ isGateRegisterInFlight trong app.js"
        assert "isGateForgotInFlight" in code, "Thiếu cờ isGateForgotInFlight trong app.js"
        assert "isSendingForgotOtp" in code, "Thiếu cờ isSendingForgotOtp trong app.js"

        # Kiểm tra disabled state
        assert ".disabled = true" in code, "Thiếu gán .disabled = true khi gửi request"
        assert ".disabled = false" in code, "Thiếu khôi phục .disabled = false khi hoàn tất request"

    def test_r2_app_js_has_60s_countdown_timer_on_forgot_otp_button(self):
        """app.js có bộ đếm ngược 60 giây (setInterval) cho nút #btnSendForgotOtp."""
        app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
        code = app_js_path.read_text(encoding="utf-8")

        # Tìm block btnSendForgotOtp
        btn_idx = code.find("btnSendForgotOtp")
        assert btn_idx != -1
        otp_block = code[btn_idx : btn_idx + 2500]

        assert "setInterval" in otp_block, "Nút #btnSendForgotOtp thiếu setInterval đếm ngược 60s"
        assert "clearInterval" in otp_block, "Nút #btnSendForgotOtp thiếu clearInterval khi đếm ngược kết thúc"
        assert "Gửi lại" in otp_block, "Nút #btnSendForgotOtp thiếu văn bản đếm ngược 'Gửi lại sau' hoặc 'Gửi lại'"

    def test_r2_index_html_forms_and_lockdown_single_firing(self):
        """simulator/static/index.html không có inline event handler trùng lặp gây gọi đúp."""
        html_path = ROOT / "simulator" / "static" / "index.html"
        assert html_path.exists()
        html = html_path.read_text(encoding="utf-8")

        # Nút #btnLockdownUnlock không được vừa có onclick unlock vừa nằm trong form onsubmit unlock
        btn_match = re.search(r'<button[^>]*id=["\']btnLockdownUnlock["\'][^>]*>', html)
        assert btn_match is not None
        btn_tag = btn_match.group(0)
        assert 'onclick="window.unlockSecurityLockdown()"' not in btn_tag, (
            "#btnLockdownUnlock không được chứa inline onclick='window.unlockSecurityLockdown()' "
            "vì form cha đã có onsubmit='window.unlockSecurityLockdown()'!"
        )
