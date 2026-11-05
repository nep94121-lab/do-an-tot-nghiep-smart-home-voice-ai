"""Bộ Kiểm Thử TDD: Milestone M18 — Bug R3 (Password Reset OTP Email Delivery and Error Handling).

Kiểm định:
1. Missing secret scenario: Khi thiếu GMAIL_APP_PASSWORD / SMTP_PASSWORD và gws không khả dụng,
   API PHẢI trả về ok: False, status 400 hoặc 503, nêu rõ tên secret bị thiếu (GMAIL_APP_PASSWORD),
   tuyệt đối không giả mạo thành công (fake success), không trả về demo_otp_preview / otp_code_for_test.
2. Valid SMTP configuration scenario: Khi cấu hình GMAIL_APP_PASSWORD hợp lệ, email được chuyển
   phát thật qua giao thức SMTP tới senat6031@gmail.com, trả về ok: True và sent_real_gmail: True.
3. Frontend JS guards: Kiểm tra app.js và mobile_app.js có guard kiểm tra sent_real_gmail trước
   khi chuyển sang bước 2, đảm bảo không lừa người dùng đã gửi mã khi gửi mail thất bại.
4. Zero leak on wrong OTP: Khi người dùng nhập sai mã OTP tại forgot_password_reset, câu thông
   báo lỗi không được làm lộ mã OTP đúng.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from simulator.server import app

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


class TestPhase5R3PasswordResetOtpEmail:
    """Tập kiểm thử TDD cho Bug R3: Gmail OTP delivery và xử lý lỗi thiếu secret."""

    def test_r3_missing_secret_fails_with_explicit_error_and_no_fake_success(self, client: TestClient):
        """Kịch bản 1: Thiếu GMAIL_APP_PASSWORD/SMTP_PASSWORD và gws không chạy được.
        
        Kỳ vọng:
        - HTTP status 400 hoặc 503 (không được trả về 200).
        - ok: False.
        - error hoặc missing_secret chỉ rõ 'GMAIL_APP_PASSWORD' hoặc 'SMTP_PASSWORD'.
        - Tuyệt đối không trả về demo_otp_preview hay otp_code_for_test.
        - sent_real_gmail là False.
        """
        env_without_secrets = {
            k: v for k, v in os.environ.items()
            if k not in ("GMAIL_APP_PASSWORD", "SMTP_PASSWORD")
        }

        with patch.dict(os.environ, env_without_secrets, clear=True), \
             patch("subprocess.run", side_effect=FileNotFoundError("gws command not found")):
            res = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "senat6031@gmail.com", "send_gmail": True},
            )
            data = res.json()

            # Phải thất bại, không fake success
            assert res.status_code in (400, 500, 503), (
                f"Lỗi R3: Status code {res.status_code} không phù hợp khi gửi email thất bại! Response: {data}"
            )
            assert data.get("ok") is False, (
                f"Lỗi R3: Hệ thống vẫn trả về ok: True khi gửi email thất bại! Response: {data}"
            )

            # Báo rõ secret bị thiếu
            err_text = f"{data.get('error', '')} {data.get('missing_secret', '')} {data.get('gmail_delivery', {})}"
            assert "GMAIL_APP_PASSWORD" in err_text or "SMTP_PASSWORD" in err_text, (
                f"Lỗi R3: Không nêu rõ biến môi trường mật khẩu ứng dụng bị thiếu: {err_text}"
            )

            # Không trả về OTP dự phòng/preview ra ngoài khi gửi thất bại
            assert not data.get("demo_otp_preview"), (
                f"Lỗi bảo mật: Vẫn trả về demo_otp_preview khi gửi email thất bại! {data}"
            )
            assert not data.get("otp_code_for_test"), (
                f"Lỗi bảo mật: Vẫn trả về otp_code_for_test khi gửi email thất bại! {data}"
            )
            assert data.get("gmail_delivery", {}).get("sent_real_gmail") is False

    def test_r3_successful_smtp_dispatch_when_secret_provided(self, client: TestClient):
        """Kịch bản 2: Khi GMAIL_APP_PASSWORD được cung cấp, email được chuyển phát qua SMTP thật."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "abcd efgh ijkl mnop"}), \
             patch("smtplib.SMTP", return_value=mock_smtp) as mock_smtp_cls, \
             patch("subprocess.run", side_effect=FileNotFoundError("gws not called")):
            res = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "senat6031@gmail.com", "send_gmail": True},
            )
            data = res.json()

            assert res.status_code == 200, f"Request thất bại: {data}"
            assert data.get("ok") is True, f"ok không phải True: {data}"
            assert data.get("gmail_delivery", {}).get("sent_real_gmail") is True, (
                f"sent_real_gmail không phải True: {data}"
            )
            assert data.get("gmail_delivery", {}).get("actual_recipient") == "senat6031@gmail.com"

            # Đảm bảo smtplib.SMTP được gọi
            assert mock_smtp_cls.called, "smtplib.SMTP chưa được gọi để gửi mail!"

    def test_r3_frontend_js_guards_against_fake_step_transition(self):
        """Kịch bản 3: Mã JS trên frontend phải kiểm tra sent_real_gmail trước khi chuyển bước 2."""
        app_js = (ROOT / "simulator" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        mobile_app_js = (ROOT / "simulator" / "static" / "js" / "mobile_app.js").read_text(encoding="utf-8")

        # app.js phải kiểm tra sent_real_gmail
        assert "sent_real_gmail" in app_js, (
            "Lỗi R3 UI: simulator/static/js/app.js chưa kiểm tra sent_real_gmail trong forgot password / lockdown!"
        )

        # mobile_app.js phải kiểm tra sent_real_gmail
        assert "sent_real_gmail" in mobile_app_js, (
            "Lỗi R3 UI: simulator/static/js/mobile_app.js chưa kiểm tra sent_real_gmail trước khi chuyển bước OTP!"
        )

    def test_r3_no_otp_leak_on_wrong_otp_verification(self, client: TestClient):
        """Kịch bản 4: Khi nhập sai OTP, không được in lộ mã OTP đúng trong câu báo lỗi."""
        # Yêu cầu cấp OTP (test mode send_gmail: False)
        res_req = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "senat6031@gmail.com", "send_gmail": False},
        )
        assert res_req.status_code == 200
        req_data = res_req.json()
        assert req_data.get("ok") is True

        # Nhập sai mã OTP
        res_verify = client.post(
            "/api/auth3/forgot_password_reset",
            json={
                "email": "senat6031@gmail.com",
                "otp_code": "000000",
                "new_password": "NewSecretPassword@2026",
                "confirm_password": "NewSecretPassword@2026",
            },
        )
        data = res_verify.json()
        assert data.get("ok") is False, "Nhập sai OTP nhưng hệ thống vẫn cho qua!"

        err_text = str(data.get("error", ""))
        assert "Mã đúng trong Gmail" not in err_text, (
            f"Lỗi bảo mật nghiêm trọng: Câu báo lỗi để lộ mã OTP đúng: {err_text}"
        )
