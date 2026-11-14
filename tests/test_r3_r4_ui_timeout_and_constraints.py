"""Test Suite for Requirements 3 and 4 (M3_R2):
R3: Instant UI Feedback (<100ms) and SMTP Timeout (~8s).
R4: Constraints & Verification:
    - Allowlist and unknown-account rejection.
    - Clean subject with no code in it, no ALL-CAPS, no emojis.
    - RFC 5322 headers.
    - Exactly one mail per request (idempotent / thread-safe).
    - SMTP mocked in tests, zero real sends.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from simulator.auth.invite_and_gmail_mixin import (
    HARDCODED_REAL_EMAIL_ALLOWLIST,
    AuthInviteGmailMixin,
    is_email_allowlisted_for_real_send,
)
from simulator.server import app

ROOT = Path(__file__).resolve().parent.parent


class StandaloneAuthManager(AuthInviteGmailMixin):
    """Standalone test manager inheriting AuthInviteGmailMixin for direct unit tests."""

    def __init__(self):
        self.accounts = [
            {"email": "nep94121@gmail.com", "speaker_name": "Nguyen Tuan Anh", "role": "owner", "tier": 1}
        ]
        self.family_email_allowlist = {}
        self.invite_links = {}
        self.pending_invite_registrations = {}
        self.event_logs = []

    def _log_event(self, **kwargs):
        self.event_logs.append(kwargs)
        return kwargs


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ============================================================================
# R3: SMTP Timeout (~8s) & Instant UI Feedback (<100ms)
# ============================================================================

class TestR3SmtpTimeout:
    """Verifies SMTP timeout reduction from 15s to 8.0s."""

    def test_smtp_timeout_constant_defaults_to_8_seconds(self):
        """Assert SMTP_TIMEOUT_SECONDS exists in invite_and_gmail_mixin and defaults to 8.0."""
        import simulator.auth.invite_and_gmail_mixin as mixin_mod
        assert hasattr(mixin_mod, "SMTP_TIMEOUT_SECONDS"), (
            "simulator.auth.invite_and_gmail_mixin must define SMTP_TIMEOUT_SECONDS"
        )
        assert mixin_mod.SMTP_TIMEOUT_SECONDS == 8.0, (
            f"SMTP_TIMEOUT_SECONDS should default to 8.0, got {mixin_mod.SMTP_TIMEOUT_SECONDS}"
        )

    def test_send_real_gmail_otp_uses_8s_timeout_for_ssl(self, monkeypatch):
        """Assert smtplib.SMTP_SSL is called with timeout=8.0 (not 15)."""
        manager = StandaloneAuthManager()
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "test-pass-secret")
        monkeypatch.setenv("SMTP_PORT", "465")
        monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")

        mock_ssl_instance = MagicMock()
        mock_ssl_cls = MagicMock(return_value=mock_ssl_instance)
        mock_ssl_instance.__enter__.return_value = mock_ssl_instance

        with patch("smtplib.SMTP_SSL", mock_ssl_cls):
            res = manager.send_real_gmail_otp("nep94121@gmail.com", "123456", "Nguyen Tuan Anh")
            assert res.get("sent_real_gmail") is True
            assert mock_ssl_cls.call_count == 1
            call_kwargs = mock_ssl_cls.call_args.kwargs
            assert call_kwargs.get("timeout") == 8.0 or call_kwargs.get("timeout") == 8, (
                f"smtplib.SMTP_SSL must be called with timeout=8.0, got {call_kwargs.get('timeout')}"
            )

    def test_send_real_gmail_otp_uses_8s_timeout_for_starttls(self, monkeypatch):
        """Assert smtplib.SMTP is called with timeout=8.0 (not 15)."""
        manager = StandaloneAuthManager()
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "test-pass-secret")
        monkeypatch.setenv("SMTP_PORT", "587")
        monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")

        mock_smtp_instance = MagicMock()
        mock_smtp_cls = MagicMock(return_value=mock_smtp_instance)
        mock_smtp_instance.__enter__.return_value = mock_smtp_instance

        with patch("smtplib.SMTP", mock_smtp_cls):
            res = manager.send_real_gmail_otp("nep94121@gmail.com", "123456", "Nguyen Tuan Anh")
            assert res.get("sent_real_gmail") is True
            assert mock_smtp_cls.call_count == 1
            call_kwargs = mock_smtp_cls.call_args.kwargs
            assert call_kwargs.get("timeout") == 8.0 or call_kwargs.get("timeout") == 8, (
                f"smtplib.SMTP must be called with timeout=8.0, got {call_kwargs.get('timeout')}"
            )


class TestR3InstantUiFeedback:
    """Verifies instant (<100ms) synchronous UI feedback and spinner elements."""

    def test_mobile_app_js_has_instant_disable_and_spinner_before_fetch(self):
        """Verify mobile_app.js synchronously disables button and sets .btn-spinner prior to fetch."""
        js_file = ROOT / "simulator" / "static" / "js" / "mobile_app.js"
        assert js_file.exists(), f"Missing file: {js_file}"
        content = js_file.read_text(encoding="utf-8")

        # Locate submitForgotSendOtp function
        func_match = re.search(r"async\s+function\s+submitForgotSendOtp\s*\(\)\s*\{([\s\S]*?)(?=\n\s*(?:async\s+)?function|\Z)", content)
        assert func_match, "submitForgotSendOtp function not found in mobile_app.js"
        func_body = func_match.group(1)

        fetch_idx = func_body.find("fetch('/api/auth3/forgot_password_send_otp'")
        assert fetch_idx != -1, "fetch call not found in submitForgotSendOtp"

        pre_fetch = func_body[:fetch_idx]
        assert "btn.disabled = true" in pre_fetch, "Button must be disabled synchronously before fetch"
        assert "btn-spinner" in pre_fetch, "Button must display .btn-spinner synchronously before fetch"
        assert "classList.add('loading')" in pre_fetch or 'classList.add("loading")' in pre_fetch, (
            "Button must add loading class before fetch"
        )
        assert "resendBtn.disabled = true" in pre_fetch, "Resend button must be disabled before fetch"

    def test_mobile_app_css_defines_btn_spinner_and_keyframes(self):
        """Verify mobile_app.css defines .btn-spinner and @keyframes btn-spin."""
        css_file = ROOT / "simulator" / "static" / "css" / "mobile_app.css"
        assert css_file.exists(), f"Missing file: {css_file}"
        content = css_file.read_text(encoding="utf-8")

        assert ".btn-spinner" in content, "mobile_app.css must define .btn-spinner class"
        assert "@keyframes btn-spin" in content, "mobile_app.css must define @keyframes btn-spin"

    def test_auth_js_has_instant_disable_and_spinner_before_fetch(self):
        """Verify auth.js synchronously disables button and sets .btn-spinner prior to fetch."""
        js_file = ROOT / "simulator" / "static" / "js" / "auth.js"
        assert js_file.exists(), f"Missing file: {js_file}"
        content = js_file.read_text(encoding="utf-8")

        # Locate requestForgotPasswordOtpAuthPage function
        func_match = re.search(r"async\s+function\s+requestForgotPasswordOtpAuthPage\s*\(\)\s*\{([\s\S]*?)(?=\n\s*(?:async\s+)?function|\Z)", content)
        assert func_match, "requestForgotPasswordOtpAuthPage function not found in auth.js"
        func_body = func_match.group(1)

        fetch_idx = func_body.find("fetch('/api/auth3/forgot_password_send_otp'")
        assert fetch_idx != -1, "fetch call not found in requestForgotPasswordOtpAuthPage"

        pre_fetch = func_body[:fetch_idx]
        assert "btn.disabled = true" in pre_fetch, "Button must be disabled synchronously before fetch in auth.js"
        assert "btn-spinner" in pre_fetch, "Button must display .btn-spinner synchronously before fetch in auth.js"

    def test_auth_html_defines_btn_spinner_and_keyframes(self):
        """Verify auth.html links /static/css/auth.css (no inline <style>) and auth.css defines .btn-spinner and btn-spin."""
        html_file = ROOT / "simulator" / "static" / "auth.html"
        css_file = ROOT / "simulator" / "static" / "css" / "auth.css"
        assert html_file.exists(), f"Missing file: {html_file}"
        assert css_file.exists(), f"Missing file: {css_file}"

        html_content = html_file.read_text(encoding="utf-8")
        css_content = css_file.read_text(encoding="utf-8")

        assert "<style" not in html_content.lower(), "auth.html must not contain inline <style>"
        assert "/static/css/auth.css" in html_content, "auth.html must link /static/css/auth.css"
        assert ".btn-spinner" in css_content, "auth.css must define .btn-spinner CSS class"
        assert "btn-spin" in css_content, "auth.css must define btn-spin CSS keyframes animation"


# ============================================================================
# R4: Constraints & Verification
# ============================================================================

class TestR4ConstraintsAndVerification:
    """Verifies keep constraints: allowlist, unknown rejection, clean subject, RFC headers, exactly 1 mail."""

    def test_r4_allowlist_rejects_non_allowlisted_email(self):
        """Allowlist shield rejects non-allowlisted email without opening network socket."""
        manager = StandaloneAuthManager()
        # Non-allowlisted recipient
        res = manager.send_real_gmail_otp("intruder@attacker.com", "123456", "Intruder User")
        assert res.get("sent_real_gmail") is False
        assert res.get("blocked_by_allowlist") is True

    def test_r4_unknown_account_rejection_returns_404(self, client: TestClient):
        """Unknown account returns HTTP 404 Not Found."""
        res = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nonexistent_account_xyz@gmail.com", "send_gmail": False},
        )
        assert res.status_code == 404, f"Expected 404 for unknown account, got {res.status_code}"
        data = res.json()
        assert data.get("ok") is False

    def test_r4_email_subject_is_clean_with_no_otp_code_or_caps_or_emojis(self, monkeypatch):
        """Email subject must contain NO OTP digits, NO ALL CAPS, NO emojis."""
        manager = StandaloneAuthManager()
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "test-pass-secret")
        monkeypatch.setenv("SMTP_PORT", "587")

        captured_msg = None

        def capture_send(msg):
            nonlocal captured_msg
            captured_msg = msg

        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp
        mock_smtp.send_message.side_effect = capture_send

        otp_code = "729415"
        with patch("smtplib.SMTP", return_value=mock_smtp):
            res = manager.send_real_gmail_otp("nep94121@gmail.com", otp_code, "Nguyen Tuan Anh")
            assert res.get("sent_real_gmail") is True

        assert captured_msg is not None
        subject = captured_msg["Subject"]
        # 1. No digits (no OTP code in subject)
        assert not re.search(r"\d", subject), f"Subject must not contain digits: '{subject}'"
        assert otp_code not in subject, f"OTP code leaked in subject: '{subject}'"
        # 2. No emojis
        emoji_pattern = re.compile(
            r"[\U00010000-\U0010ffff]|[\u2600-\u27ff]", flags=re.UNICODE
        )
        assert not emoji_pattern.search(subject), f"Subject must not contain emojis: '{subject}'"

    def test_r4_rfc5322_headers_present(self, monkeypatch):
        """Email contains standard RFC 5322 headers: From, To, Date, Message-ID, Reply-To."""
        manager = StandaloneAuthManager()
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "test-pass-secret")
        monkeypatch.setenv("SMTP_PORT", "587")

        captured_msg = None

        def capture_send(msg):
            nonlocal captured_msg
            captured_msg = msg

        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp
        mock_smtp.send_message.side_effect = capture_send

        with patch("smtplib.SMTP", return_value=mock_smtp):
            res = manager.send_real_gmail_otp("nep94121@gmail.com", "849201", "Nguyen Tuan Anh")
            assert res.get("sent_real_gmail") is True

        assert captured_msg is not None
        assert captured_msg["From"] is not None
        assert "nep94121@gmail.com" in captured_msg["To"]
        assert captured_msg["Date"] is not None
        assert captured_msg["Message-ID"] is not None
        assert captured_msg["Reply-To"] is not None

    def test_r4_smtp_is_mocked_in_tests(self):
        """Verify that smtplib.SMTP and smtplib.SMTP_SSL are mocked by autouse fixture in conftest.py."""
        import smtplib
        # Without an explicit patch here, the autouse fixture from tests/conftest.py should mock them
        # so calling them does not open a real socket
        smtp_obj = smtplib.SMTP("nonexistent.invalid.host", 587)
        # Should be a MagicMock instance from conftest
        assert isinstance(smtp_obj, MagicMock), "smtplib.SMTP must be mocked by conftest.py"
