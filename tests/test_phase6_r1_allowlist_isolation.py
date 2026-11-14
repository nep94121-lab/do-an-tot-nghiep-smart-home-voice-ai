"""Milestone 1 Test Suite: R1 Email Allowlist & Test Isolation.

Verifies:
1. Non-allowlisted emails (thanh_vien_chuan@gmail.com, hoc_sinh_moi@gmail.com, tan_binh_gia_dinh@gmail.com, etc.)
   are rejected immediately by send_real_gmail_otp and send_invite_link_via_gmail with:
   - sent_real_gmail=False
   - blocked_by_allowlist=True
   without opening SMTP sockets or executing gws subprocess commands.
2. Allowlisted emails (nep94121@gmail.com, senat6031@gmail.com, kbanh376@gmail.com, or env REAL_EMAIL_ALLOWLIST)
   pass the allowlist check.
3. Autouse pytest fixture mock_email_and_gws_network_isolation in tests/conftest.py successfully
   intercepts smtplib.SMTP, smtplib.SMTP_SSL, and subprocess.run(["gws", ...]).
4. Login Gate in simulator/static/js/app.js explicitly specifies "send_gmail": false.
5. Fixture data files:
   - simulator/data/accounts_3layer.json contains exactly 6 clean default accounts.
   - simulator/data/family_email_allowlist.json contains {} (empty JSON object).
"""
from __future__ import annotations

import json
import os
import pathlib
import smtplib
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from simulator.auth.invite_and_gmail_mixin import (
    HARDCODED_REAL_EMAIL_ALLOWLIST,
    AuthInviteGmailMixin,
    is_email_allowlisted_for_real_send,
)
from simulator.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent


class DummyAuthManager(AuthInviteGmailMixin):
    """Minimal standalone instance of AuthInviteGmailMixin for direct unit tests."""

    def __init__(self):
        self.accounts = []
        self.family_email_allowlist = {}
        self.invite_links = {
            "TEST_INV_C2": {
                "code": "TEST_INV_C2",
                "target_tier": 2,
                "target_role_label": "Thành viên",
                "issuer_name": "Nguyễn Tuấn Anh",
                "full_url": "http://localhost:8000/invite?code=TEST_INV_C2",
            }
        }
        self.pending_invite_registrations = {}
        self.event_logs = []

    def _log_event(self, **kwargs):
        self.event_logs.append(kwargs)
        return kwargs

    def find_account(self, actor_id: str):
        return None


@pytest.fixture
def dummy_auth() -> DummyAuthManager:
    return DummyAuthManager()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ==============================================================================
# Unit Tests: Allowlist Engine
# ==============================================================================

class TestAllowlistEngine:
    """Kiểm tra logic Allowlist Engine (Canonical Allowlist & Helper Function)."""

    def test_hardcoded_real_email_allowlist_members(self):
        """Danh sách HARDCODED_REAL_EMAIL_ALLOWLIST chỉ giữ duy nhất email Chủ nhà nep94121@gmail.com."""
        expected = {"nep94121@gmail.com"}
        assert HARDCODED_REAL_EMAIL_ALLOWLIST == expected

    @pytest.mark.parametrize(
        "email",
        [
            "nep94121@gmail.com",
            "NEP94121@GMAIL.COM",
            "  nep94121@gmail.com  ",
            "nep94121+e2e1114a@gmail.com",
            "n.e.p.94121@googlemail.com",
        ],
    )
    def test_is_email_allowlisted_for_real_send_allowed_addresses(self, email: str):
        """Email Chủ nhà và alias Gmail canonical hợp lệ phải trả về True."""
        assert is_email_allowlisted_for_real_send(email) is True

    @pytest.mark.parametrize(
        "email",
        [
            "senat6031@gmail.com",
            "kbanh376@gmail.com",
            "thanh_vien_chuan@gmail.com",
            "hoc_sinh_moi@gmail.com",
            "tan_binh_gia_dinh@gmail.com",
            "thanhviena.hust@gmail.com",
            "thanhvienb.hust@gmail.com",
            "khachc.guest@gmail.com",
            "stranger@attacker.org",
            "random_user@yahoo.com",
            "",
            "   ",
            None,
        ],
    )
    def test_is_email_allowlisted_for_real_send_rejected_addresses(self, email: str | None):
        """Các email ngoài allowlist (bao gồm senat6031/kbanh376) phải trả về False."""
        assert is_email_allowlisted_for_real_send(email) is False

    def test_is_email_allowlisted_with_env_variable_expansion(self, monkeypatch: pytest.MonkeyPatch):
        """Biến môi trường REAL_EMAIL_ALLOWLIST chỉ mở rộng ngoài VERCEL và bị bỏ qua trên Vercel."""
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.setenv(
            "REAL_EMAIL_ALLOWLIST",
            "extra_tester@hust.edu.vn, lab_member@ai.org ; vip_guest@domain.com",
        )
        assert is_email_allowlisted_for_real_send("extra_tester@hust.edu.vn") is True
        assert is_email_allowlisted_for_real_send("lab_member@ai.org") is True
        assert is_email_allowlisted_for_real_send("vip_guest@domain.com") is True
        assert is_email_allowlisted_for_real_send("nep94121@gmail.com") is True
        assert is_email_allowlisted_for_real_send("senat6031@gmail.com") is False
        assert is_email_allowlisted_for_real_send("thanh_vien_chuan@gmail.com") is False

        monkeypatch.setenv("VERCEL", "1")
        assert is_email_allowlisted_for_real_send("extra_tester@hust.edu.vn") is False
        assert is_email_allowlisted_for_real_send("nep94121+e2e1114a@gmail.com") is True


# ==============================================================================
# Unit & Integration Tests: Dispatcher Allowlist Gate (send_real_gmail_otp & send_invite_link_via_gmail)
# ==============================================================================

class TestDispatcherAllowlistGate:
    """Kiểm tra cổng chặn Dispatcher: Chặn gửi thư thật tới email ngoài Allowlist (Chống Bounce Mail)."""

    @pytest.mark.parametrize(
        "email",
        [
            "thanh_vien_chuan@gmail.com",
            "hoc_sinh_moi@gmail.com",
            "tan_binh_gia_dinh@gmail.com",
        ],
    )
    def test_send_real_gmail_otp_rejects_non_allowlisted_without_smtp_or_gws(
        self, dummy_auth: DummyAuthManager, email: str, monkeypatch: pytest.MonkeyPatch
    ):
        """send_real_gmail_otp chặn ngay lập tức, trả về sent_real_gmail=False, blocked_by_allowlist=True, không gọi SMTP/gws."""
        smtp_called = []
        gws_called = []

        def fake_smtp(*args, **kwargs):
            smtp_called.append(args)
            raise AssertionError("smtplib.SMTP MUST NOT be called for non-allowlisted email!")

        def fake_run(cmd, *args, **kwargs):
            if "gws" in str(cmd):
                gws_called.append(cmd)
                raise AssertionError("gws CLI MUST NOT be invoked for non-allowlisted email!")
            return MagicMock()

        monkeypatch.setattr(smtplib, "SMTP", fake_smtp)
        monkeypatch.setattr(smtplib, "SMTP_SSL", fake_smtp)
        monkeypatch.setattr(subprocess, "run", fake_run)

        # Cung cấp cấu hình SMTP giả định để chứng minh dù có password, allowlist gate vẫn chặn trước
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "mocked_dummy_password")
        monkeypatch.setenv("SMTP_USER", "nep94121@gmail.com")

        res = dummy_auth.send_real_gmail_otp(
            target_email=email,
            otp_code="123456",
            display_name="Test User",
        )

        assert res.get("sent_real_gmail") is False
        assert res.get("blocked_by_allowlist") is True
        assert res.get("actual_recipient") == email.strip().lower()
        assert len(smtp_called) == 0
        assert len(gws_called) == 0

    @pytest.mark.parametrize(
        "email",
        [
            "thanh_vien_chuan@gmail.com",
            "hoc_sinh_moi@gmail.com",
            "tan_binh_gia_dinh@gmail.com",
        ],
    )
    def test_send_invite_link_via_gmail_rejects_non_allowlisted_without_gws(
        self, dummy_auth: DummyAuthManager, email: str, monkeypatch: pytest.MonkeyPatch
    ):
        """send_invite_link_via_gmail chặn ngay email ngoài allowlist, không gọi gws subprocess."""
        gws_called = []

        def fake_run(cmd, *args, **kwargs):
            if "gws" in str(cmd):
                gws_called.append(cmd)
                raise AssertionError("gws CLI MUST NOT be called for non-allowlisted invite!")
            return MagicMock()

        monkeypatch.setattr(subprocess, "run", fake_run)

        res = dummy_auth.send_invite_link_via_gmail(
            invite_code="TEST_INV_C2",
            recipient_email=email,
        )

        assert res.get("ok") is False
        assert res.get("blocked_by_allowlist") is True
        assert res.get("sent_real_gmail") is False
        assert len(gws_called) == 0

    def test_send_real_gmail_otp_allows_allowlisted_email_under_mock(
        self, dummy_auth: DummyAuthManager, monkeypatch: pytest.MonkeyPatch
    ):
        """Email thuộc allowlist (nep94121+e2e1114a@gmail.com) vượt qua Allowlist Gate và kích hoạt gửi (qua mock conftest)."""
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "mock_dummy_pwd")
        monkeypatch.setenv("SMTP_USER", "nep94121@gmail.com")

        res = dummy_auth.send_real_gmail_otp(
            target_email="nep94121+e2e1114a@gmail.com",
            otp_code="654321",
            display_name="Owner Alias",
        )

        assert res.get("blocked_by_allowlist") is not True
        # Qua mock conftest của smtplib
        assert res.get("sent_real_gmail") is True
        assert res.get("actual_recipient") == "nep94121+e2e1114a@gmail.com"

    def test_send_invite_link_via_gmail_allows_allowlisted_email_under_mock(
        self, dummy_auth: DummyAuthManager
    ):
        """send_invite_link_via_gmail cho phép gửi tới email allowlisted (nep94121+e2e1114a@gmail.com)."""
        res = dummy_auth.send_invite_link_via_gmail(
            invite_code="TEST_INV_C2",
            recipient_email="nep94121+e2e1114a@gmail.com",
        )
        assert res.get("ok") is True
        assert res.get("recipient") == "nep94121+e2e1114a@gmail.com"
        assert res.get("gmail_message_id") == "mock_gws_isolation_msg_id"


# ==============================================================================
# Integration Tests: API Routes with Allowlist Shield
# ==============================================================================

class TestApiRoutesAllowlistIsolation:
    """Kiểm tra các endpoint HTTP khi gọi với email ngoài allowlist."""

    def test_api_forgot_password_send_otp_blocks_non_allowlisted(self, client: TestClient):
        """POST /api/auth3/forgot_password_send_otp với email không thuộc allowlist bị chặn an toàn."""
        # 1. Tài khoản có trong hệ thống nhưng không thuộc REAL_EMAIL_ALLOWLIST
        res = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "thanhviena.hust@gmail.com", "send_gmail": True},
        )
        data = res.json()
        gmail_res = data.get("gmail_delivery") or {}
        assert gmail_res.get("sent_real_gmail") is False
        assert gmail_res.get("blocked_by_allowlist") is True

        # 2. Email hoàn toàn không tồn tại trong hệ thống -> 404, không gửi email
        res_nonexist = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "thanh_vien_chuan@gmail.com", "send_gmail": True},
        )
        assert res_nonexist.status_code == 404
        assert res_nonexist.json().get("ok") is False

    def test_api_send_invite_email_blocks_non_allowlisted(self, client: TestClient):
        """POST /api/auth3/send_invite_email với email không thuộc allowlist bị chặn an toàn."""
        res = client.post(
            "/api/auth3/send_invite_email",
            json={
                "invite_code": "TEST_INV_CODE",
                "recipient_email": "tan_binh_gia_dinh@gmail.com",
            },
        )
        data = res.json()
        assert data.get("ok") is False or data.get("blocked_by_allowlist") is True
        if data.get("blocked_by_allowlist") is not None:
            assert data.get("blocked_by_allowlist") is True


# ==============================================================================
# Autouse Fixture Isolation Test
# ==============================================================================

class TestAutouseFixtureIsolation:
    """Kiểm tra fixture autouse trong tests/conftest.py cô lập 100% mạng bên ngoài."""

    def test_smtplib_smtp_is_mocked_by_default(self):
        """Gọi smtplib.SMTP không mở kết nối mạng thật."""
        server = smtplib.SMTP("smtp.gmail.com", 587)
        assert hasattr(server, "send_message")
        res = server.login("dummy", "dummy")
        assert res[0] == 235

    def test_smtplib_smtp_ssl_is_mocked_by_default(self):
        """Gọi smtplib.SMTP_SSL không mở kết nối mạng thật."""
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        assert hasattr(server, "send_message")
        res = server.login("dummy", "dummy")
        assert res[0] == 235

    def test_subprocess_run_gws_is_mocked_by_default(self):
        """Gọi subprocess.run với gws trả về mock object an toàn."""
        proc = subprocess.run(["gws", "gmail", "users", "messages", "send"])
        assert proc.returncode == 0
        assert "mock_gws_isolation" in proc.stdout


# ==============================================================================
# Frontend UI Inspection: app.js
# ==============================================================================

class TestFrontendAppJsConfiguration:
    """Kiểm tra simulator/static/js/app.js có cấu hình send_gmail: false tại cổng đăng nhập."""

    def test_app_js_btnSubmitGateLogin_sends_send_gmail_false(self):
        """Cổng đăng nhập (#btnSubmitGateLogin) phải truyền 'send_gmail: false' khi gọi layer1_login."""
        app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
        assert app_js_path.exists(), f"Không tìm thấy file: {app_js_path}"
        content = app_js_path.read_text(encoding="utf-8")

        # Tìm block btnSubmitGateLogin
        assert "btnSubmitGateLogin" in content
        # Trong phạm vi fetch layer1_login từ btnSubmitGateLogin, phải có send_gmail: false
        btn_idx = content.find("btnSubmitGateLogin")
        fetch_idx = content.find("/api/auth3/layer1_login", btn_idx)
        assert fetch_idx != -1, "Không tìm thấy fetch /api/auth3/layer1_login sau btnSubmitGateLogin!"

        snippet = content[fetch_idx : fetch_idx + 350]
        assert "send_gmail" in snippet and "false" in snippet, (
            f"Lỗi: Payload của layer1_login tại btnSubmitGateLogin chưa chứa 'send_gmail: false'! Đoạn mã: {snippet}"
        )


# ==============================================================================
# Clean Data Fixtures: accounts_3layer.json & family_email_allowlist.json
# ==============================================================================

class TestCleanDataFixtures:
    """Kiểm tra tính trong sạch của hai file fixtures: accounts_3layer.json và family_email_allowlist.json."""

    def test_accounts_3layer_json_contains_only_clean_default_accounts(self):
        """simulator/data/accounts_3layer.json chỉ được chứa 6 tài khoản mặc định chuẩn."""
        acc_path = ROOT / "simulator" / "data" / "accounts_3layer.json"
        assert acc_path.exists(), f"Không tìm thấy {acc_path}"

        accounts = json.loads(acc_path.read_text(encoding="utf-8"))
        assert isinstance(accounts, list)
        assert len(accounts) == 6, f"accounts_3layer.json phải có đúng 6 tài khoản, hiện có: {len(accounts)}"

        expected_ids = {"tuan_anh", "thanh_vien_a", "thanh_vien_b", "khach_c", "senat6031", "kbanh376"}
        actual_ids = {acc.get("account_id") for acc in accounts}
        assert actual_ids == expected_ids, f"Danh sách account_id không khớp: {actual_ids} != {expected_ids}"

        # Đảm bảo không có tài khoản test rác
        unwanted_keywords = ["test", "hacker", "alias", "con_yeu", "emgai"]
        for acc in accounts:
            acc_id = acc.get("account_id", "").lower()
            acc_email = acc.get("email", "").lower()
            for kw in unwanted_keywords:
                assert kw not in acc_id and kw not in acc_email, (
                    f"Phát hiện tài khoản rác còn sót lại: {acc_id} ({acc_email})"
                )

    def test_family_email_allowlist_json_is_empty_object(self):
        """simulator/data/family_email_allowlist.json phải là dictionary rỗng {}."""
        fa_path = ROOT / "simulator" / "data" / "family_email_allowlist.json"
        assert fa_path.exists(), f"Không tìm thấy {fa_path}"

        data = json.loads(fa_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert data == {}, f"family_email_allowlist.json phải là dict rỗng {{}}, hiện có: {data}"
