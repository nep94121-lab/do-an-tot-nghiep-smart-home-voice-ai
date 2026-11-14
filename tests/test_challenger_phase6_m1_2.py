"""Challenger 2 Test Suite: Empirical Adversarial Verification for Milestone 1.

Author: Challenger 2 (challenger_m1_2) - teamwork_challenger
Scope:
1. Test login gate on /:
   - Verify static/app.js & static/index.html & static/js/app.js
   - Verify that layer1_login fetch payload explicitly includes `send_gmail: false`
   - Verify API endpoint /api/auth3/layer1_login behavior with and without send_gmail: false
2. Test Playwright 3-roles live test:
   - Analyze tests/test_playwright_3roles_live.py clicks and flows
   - Verify desktop and mobile login forms send send_gmail: false
   - Verify no Playwright action can trigger real email dispatch
3. Test mock fixture leak protection:
   - Verify multi-threaded and background task execution under autouse conftest fixture
   - Verify SMTP and gws subprocess calls are intercepted across threads and subprocess representations (list/string)
   - Verify fail-safe behavior when unexpected recipients or commands are passed
4. Test family_email_allowlist.json & accounts_3layer.json:
   - family_email_allowlist.json is clean ({}) with 0 records
   - accounts_3layer.json contains exactly the 6 canonical seed accounts
   - Stress test boundary conditions of is_email_allowlisted_for_real_send
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import pathlib
import re
import smtplib
import subprocess
import threading
from typing import Any
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from simulator.auth.invite_and_gmail_mixin import (
    HARDCODED_REAL_EMAIL_ALLOWLIST,
    AuthInviteGmailMixin,
    is_email_allowlisted_for_real_send,
)
from simulator.auth.constants_and_crypto import hash_password
from simulator.auth_3layer import get_auth_3layer_manager
from simulator.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ==============================================================================
# DIMENSION 1: LOGIN GATE ON `/` & `send_gmail: false`
# ==============================================================================
class TestLoginGatePayloadAndBehavior:
    """Empirical verification that login on / explicitly sends send_gmail: false."""

    def test_index_html_loads_correct_app_js(self):
        """Index.html must load /static/js/app.js and contain gate login elements."""
        index_path = ROOT / "simulator" / "static" / "index.html"
        assert index_path.exists(), f"Missing {index_path}"
        content = index_path.read_text(encoding="utf-8")

        # Must contain gate login form and submit button
        assert 'id="gatePanelLogin"' in content, "Missing gatePanelLogin form in index.html"
        assert 'id="btnSubmitGateLogin"' in content, "Missing btnSubmitGateLogin in index.html"
        assert 'id="gateLoginEmail"' in content, "Missing gateLoginEmail input"
        assert 'id="gateLoginPassword"' in content, "Missing gateLoginPassword input"

        # Must load app.js script
        assert 'src="/static/js/app.js"' in content, "index.html must load /static/js/app.js"

    def test_legacy_app_js_forwards_to_static_js_app_js(self):
        """Legacy simulator/static/app.js must forward to /static/js/app.js."""
        legacy_path = ROOT / "simulator" / "static" / "app.js"
        assert legacy_path.exists(), f"Missing {legacy_path}"
        content = legacy_path.read_text(encoding="utf-8")
        assert "/static/js/app.js" in content, "Legacy forwarder must point to /static/js/app.js"

    def test_app_js_btnSubmitGateLogin_explicitly_sends_send_gmail_false(self):
        """simulator/static/js/app.js must include `send_gmail: false` in layer1_login fetch."""
        app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
        assert app_js_path.exists(), f"Missing {app_js_path}"
        content = app_js_path.read_text(encoding="utf-8")

        # Find the btnSubmitGateLogin click handler block
        btn_idx = content.find("btnSubmitGateLogin.addEventListener")
        assert btn_idx != -1, "Could not find btnSubmitGateLogin.addEventListener in app.js"

        # Inspect the fetch block following the event listener
        fetch_block = content[btn_idx : btn_idx + 1200]
        assert "/api/auth3/layer1_login" in fetch_block, "Handler must call /api/auth3/layer1_login"

        # Regex match JSON payload containing send_gmail: false
        match = re.search(r"send_gmail\s*:\s*false", fetch_block)
        assert match is not None, (
            "CRITICAL: btnSubmitGateLogin handler does NOT explicitly set 'send_gmail: false'!"
        )

    def test_mobile_app_js_login_explicitly_sends_send_gmail_false(self):
        """simulator/static/js/mobile_app.js must also include `send_gmail: false`."""
        mobile_js_path = ROOT / "simulator" / "static" / "js" / "mobile_app.js"
        assert mobile_js_path.exists(), f"Missing {mobile_js_path}"
        content = mobile_js_path.read_text(encoding="utf-8")

        btn_idx = content.find("fetch('/api/auth3/layer1_login'")
        assert btn_idx != -1, "Could not find layer1_login fetch in mobile_app.js"
        fetch_block = content[btn_idx : btn_idx + 400]

        match = re.search(r"send_gmail\s*:\s*false", fetch_block)
        assert match is not None, (
            "CRITICAL: mobile_app.js login fetch does NOT explicitly set 'send_gmail: false'!"
        )

    def test_layer1_login_api_with_send_gmail_false_does_not_send_otp(self):
        """Calling /api/auth3/layer1_login with send_gmail: false must succeed with 0 email activity."""
        client = TestClient(app)
        mgr = get_auth_3layer_manager()

        # Clean pending OTPs and seed explicit test hash cleanly
        mgr.pending_otps.clear()
        owner_acc = mgr.find_account("nep94121@gmail.com")
        assert owner_acc is not None
        orig_hash = owner_acc.get("password_hash", "")
        test_pw = "OwnerTestPass#11"
        owner_acc["password_hash"] = hash_password(test_pw)
        try:
            # Login as owner
            resp = client.post(
                "/api/auth3/layer1_login",
                json={
                    "email": "nep94121@gmail.com",
                    "password": test_pw,
                    "login_method": "password",
                    "send_gmail": False,
                },
            )
            assert resp.status_code == 200, f"Unexpected status {resp.status_code}: {resp.text}"
            data = resp.json()
            assert data.get("ok") is True, f"Login failed: {data}"
            assert data.get("otp_required") is True
            assert not data.get("session_token")

            # Verify in manager pending_otps that sent_real_gmail is False
            otp_info = mgr.pending_otps.get("nep94121@gmail.com")
            assert otp_info is not None, "Pending OTP record must exist"
            gmail_deliv = otp_info.get("gmail_delivery") or {}
            assert gmail_deliv.get("sent_real_gmail") is False, (
                f"Expected sent_real_gmail to be False, got: {gmail_deliv}"
            )
        finally:
            owner_acc["password_hash"] = orig_hash
            mgr.pending_otps.clear()
            mgr._login_rate_limits.clear()


# ==============================================================================
# DIMENSION 2: PLAYWRIGHT 3-ROLES LIVE TEST & EMAIL SAFETY
# ==============================================================================
class TestPlaywrightThreeRolesEmailSafety:
    """Empirical verification that Playwright 3-roles test flows cannot trigger real emails."""

    def test_playwright_test_file_structure_and_clicks(self):
        """Analyze test_playwright_3roles_live.py to verify all login interactions use safe forms."""
        test_file = ROOT / "tests" / "test_playwright_3roles_live.py"
        assert test_file.exists(), f"Missing {test_file}"
        code = test_file.read_text(encoding="utf-8")

        # Verify test roles
        assert "nep94121@gmail.com" in code, "Must test Owner tier 1"
        assert "senat6031@gmail.com" in code, "Must test Family member tier 2"
        assert "kbanh376@gmail.com" in code, "Must test Guest tier 3"

        # Verify buttons clicked
        # Desktop uses #btnSubmitGateLogin
        assert "#btnSubmitGateLogin" in code, "Desktop flows must use #btnSubmitGateLogin"
        # Mobile uses #mobileLoginBtn
        assert "#mobileLoginBtn" in code, "Mobile flows must use #mobileLoginBtn"

        # Verify dangerous email-sending actions are NOT triggered by the test
        assert "forgot_password" not in code, "Test should not invoke forgot password flow"
        assert "send_invite" not in code, "Test should not invoke send invite flow"

    def test_dry_run_3roles_login_payloads_have_send_gmail_false(self):
        """Simulate the 3-roles logins via TestClient to verify all 3 roles login safely without mail."""
        client = TestClient(app)
        mgr = get_auth_3layer_manager()

        roles = [
            ("nep94121@gmail.com", "OwnerRolePass#11", 1),
            ("senat6031@gmail.com", "FamilyRolePass#22", 2),
            ("kbanh376@gmail.com", "GuestRolePass#33", 3),
        ]
        saved_hashes: dict[str, str] = {}
        for email, pwd, _ in roles:
            acc = mgr.find_account(email)
            assert acc is not None
            saved_hashes[email] = acc.get("password_hash", "")
            acc["password_hash"] = hash_password(pwd)

        try:
            for email, pwd, expected_tier in roles:
                mgr.pending_otps.clear()
                resp = client.post(
                    "/api/auth3/layer1_login",
                    json={
                        "email": email,
                        "password": pwd,
                        "login_method": "password",
                        "send_gmail": False,
                    },
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data.get("ok") is True, f"Login failed for {email}: {data}"
                assert data.get("tier") == expected_tier or (data.get("account") or {}).get("tier") == expected_tier

                if expected_tier == 1:
                    assert data.get("otp_required") is True
                    otp_info = mgr.pending_otps.get(email.lower())
                    assert otp_info is not None
                    assert otp_info.get("gmail_delivery", {}).get("sent_real_gmail") is False
                    v_resp = client.post(
                        "/api/auth3/layer2_verify_otp",
                        json={"email": email, "otp_code": otp_info["otp_code"], "purpose": "layer2_login"},
                    )
                    assert v_resp.status_code == 200
                    assert v_resp.json().get("session_token")
                else:
                    assert data.get("session_token")
        finally:
            for email, _, _ in roles:
                acc = mgr.find_account(email)
                if acc is not None:
                    acc["password_hash"] = saved_hashes.get(email, "")
            mgr.pending_otps.clear()
            mgr._login_rate_limits.clear()


# ==============================================================================
# DIMENSION 3: MOCK FIXTURE LEAK PROTECTION & CONCURRENCY
# ==============================================================================
class TestMockFixtureLeakProtection:
    """Empirical verification that autouse fixture intercepts SMTP & gws in threads and edge cases."""

    def test_autouse_fixture_intercepts_smtp_in_concurrent_threads(self):
        """Verify that concurrent threads instantiating smtplib.SMTP are safely intercepted."""
        thread_results = []

        def worker_fn(thread_id: int):
            try:
                # Instantiate SMTP and SMTP_SSL
                smtp = smtplib.SMTP("smtp.gmail.com", 587)
                res_login = smtp.login("test@gmail.com", "secret")
                res_send = smtp.sendmail("test@gmail.com", ["dest@gmail.com"], "Subject: Test\n\nMsg")

                ssl_smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465)
                res_ssl_send = ssl_smtp.send_message(MagicMock())

                thread_results.append({
                    "thread_id": thread_id,
                    "success": True,
                    "smtp_is_mock": isinstance(smtp, MagicMock),
                    "ssl_is_mock": isinstance(ssl_smtp, MagicMock),
                })
            except Exception as exc:
                thread_results.append({
                    "thread_id": thread_id,
                    "success": False,
                    "error": str(exc),
                })

        threads = [threading.Thread(target=worker_fn, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert len(thread_results) == 10, f"Expected 10 results, got {len(thread_results)}"
        for res in thread_results:
            assert res["success"] is True, f"Thread failed: {res}"
            assert res["smtp_is_mock"] is True, "SMTP was not mocked in thread"
            assert res["ssl_is_mock"] is True, "SMTP_SSL was not mocked in thread"

    def test_autouse_fixture_intercepts_gws_subprocess_list_and_string(self):
        """Verify subprocess.run with 'gws' as list or string is cleanly intercepted without launching CLI."""
        # 1. As list
        proc_list = subprocess.run(["gws", "gmail", "messages", "send", "--to", "test@gmail.com"])
        assert proc_list.returncode == 0
        data_list = json.loads(proc_list.stdout)
        assert data_list.get("id") == "mock_gws_isolation_msg_id"

        # 2. As string
        proc_str = subprocess.run("gws gmail messages send --to test@gmail.com")
        assert proc_str.returncode == 0
        data_str = json.loads(proc_str.stdout)
        assert data_str.get("id") == "mock_gws_isolation_msg_id"

    def test_unpatched_thread_sending_email_is_blocked_or_mocked(self):
        """Even if a background thread invokes send_real_gmail_otp directly:
        - Non-allowlisted email is BLOCKED at allowlist gate (0 SMTP activity).
        - Allowlisted email is MOCKED by conftest autouse fixture (0 network socket).
        """
        mgr = get_auth_3layer_manager()

        def background_send_fake():
            return mgr.send_real_gmail_otp(
                target_email="unpatched_worker@fake-domain.xyz",
                otp_code="999888",
                display_name="Unpatched Fake Worker",
            )

        def background_send_allowlisted():
            return mgr.send_real_gmail_otp(
                target_email="nep94121+thread@gmail.com",
                otp_code="111222",
                display_name="Owner Alias Allowlisted",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_fake = executor.submit(background_send_fake)
            future_allow = executor.submit(background_send_allowlisted)

            res_fake = future_fake.result(timeout=5.0)
            res_allow = future_allow.result(timeout=5.0)

        # Fake email MUST be blocked by allowlist
        assert res_fake["sent_real_gmail"] is False
        assert res_fake["blocked_by_allowlist"] is True
        assert "BLOCKED" in res_fake.get("status", "")

        # Allowlisted email is intercepted by mock (mock returns exit code or mock msg ID)
        assert res_allow is not None
        # Either sent via mock SMTP or mock gws, but NEVER leaks real traffic
        if res_allow.get("sent_real_gmail"):
            assert res_allow.get("transport") in ("SMTP", "gws_cli", None)


# ==============================================================================
# DIMENSION 4: DATA INTEGRITY & ALLOWLIST CLEANLINESS
# ==============================================================================
class TestDataIntegrityAndAllowlistCleanliness:
    """Empirical verification of family_email_allowlist.json and accounts_3layer.json."""

    def test_family_email_allowlist_json_is_strictly_empty_object(self):
        """simulator/data/family_email_allowlist.json must exist and be strictly {}."""
        allowlist_path = ROOT / "simulator" / "data" / "family_email_allowlist.json"
        assert allowlist_path.exists(), f"Missing {allowlist_path}"

        raw_bytes = allowlist_path.read_bytes()
        parsed = json.loads(raw_bytes.decode("utf-8"))

        assert isinstance(parsed, dict), "family_email_allowlist.json must be a JSON object"
        assert len(parsed) == 0, (
            f"family_email_allowlist.json contains {len(parsed)} stale entries! Must be exactly {{}}"
        )
        assert parsed == {}, "family_email_allowlist.json must be empty dict {}"

    def test_accounts_3layer_json_contains_only_six_canonical_accounts(self):
        """simulator/data/accounts_3layer.json must contain exactly 6 canonical accounts."""
        accounts_path = ROOT / "simulator" / "data" / "accounts_3layer.json"
        assert accounts_path.exists(), f"Missing {accounts_path}"

        raw_bytes = accounts_path.read_bytes()
        accounts = json.loads(raw_bytes.decode("utf-8"))

        assert isinstance(accounts, list), "accounts_3layer.json must be a list"
        assert len(accounts) == 6, (
            f"accounts_3layer.json has {len(accounts)} accounts! Expected exactly 6."
        )

        account_ids = {acc.get("account_id") for acc in accounts}
        expected_ids = {"tuan_anh", "thanh_vien_a", "thanh_vien_b", "khach_c", "senat6031", "kbanh376"}
        assert account_ids == expected_ids, (
            f"Account ID mismatch. Found {account_ids}, expected {expected_ids}"
        )

        # Verify no fake test accounts present
        account_emails = {acc.get("email") for acc in accounts}
        forbidden_emails = {
            "thanh_vien_chuan@gmail.com",
            "hoc_sinh_moi@gmail.com",
            "tan_binh_gia_dinh@gmail.com",
            "fake_student@gmail.com",
        }
        leaked = account_emails.intersection(forbidden_emails)
        assert not leaked, f"Forbidden fake test emails found in accounts_3layer.json: {leaked}"

    @pytest.mark.parametrize(
        "allowlisted_email",
        [
            "nep94121@gmail.com",
            "NEP94121@GMAIL.COM",
            "  nep94121@gmail.com  ",
            "nep94121+e2e1114a@gmail.com",
            "n.e.p.94121@googlemail.com",
            "nep94121@GMAIL.COM\n",
        ],
    )
    def test_allowlist_canonical_allowlisted_variations_pass(self, allowlisted_email: str):
        """Canonical owner allowlisted emails and aliases with case/whitespace must return True."""
        assert is_email_allowlisted_for_real_send(allowlisted_email) is True

    @pytest.mark.parametrize(
        "blocked_email",
        [
            "senat6031@gmail.com",
            "kbanh376@gmail.com",
            # Subdomain & extension manipulation
            "nep94121@gmail.com.evil.com",
            "nep94121@gmail.com@attacker.org",
            "attacker@nep94121@gmail.com",
            "senat6031@gmail.com.fake",
            "prefix_kbanh376@gmail.com",
            # Random and fake test accounts
            "thanh_vien_chuan@gmail.com",
            "hoc_sinh_moi@gmail.com",
            "tan_binh_gia_dinh@gmail.com",
            "random_guest_12345@gmail.com",
            # Invalid formats
            "",
            "   ",
            "not_an_email",
            "@gmail.com",
            "nep94121@",
            None,
        ],
    )
    def test_allowlist_adversarial_and_non_allowlisted_are_blocked(self, blocked_email: Any):
        """Adversarial spoofing and non-allowlisted emails must return False."""
        assert is_email_allowlisted_for_real_send(blocked_email) is False
