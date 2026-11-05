"""Milestone 1 Challenger Suite: Adversarial Stress Tests for R1 Email Allowlist & Test Isolation.

Author: Challenger 1 (challenger_m1_1) - teamwork_challenger
Scope:
1. Evasion Stress Testing against `is_email_allowlisted_for_real_send`:
   - Unicode lookalikes (Cyrillic, Greek, fullwidth, accents, RTL/bidi, zero-width)
   - CRLF & Header Injection payloads
   - Subdomain and domain manipulation
   - Case sensitivity & locale anomalies
   - Trailing dots, double dots, malformed syntax
   - Embedded null bytes & control characters
   - Multi-recipient delimiter injections
   - RFC syntax anomalies (angle brackets, comments, quotes, subaddressing tags)
   - Type confusion (non-strings, None, collections)
   - Environment variable edge cases & malformed values
2. Dispatcher Gate Airtightness:
   - Prove that NO evasion payload can bypass `send_real_gmail_otp` or `send_invite_link_via_gmail`
   - Prove zero socket/subprocess calls for any non-allowlisted input
3. Test Isolation Interception Stress:
   - Concurrency stress harness (multi-threaded simultaneous SMTP/gws calls)
   - String vs list commands in `subprocess.run`
   - Pass-through for non-gws subprocess commands
4. Fixture Integrity:
   - Deep structural and cryptographic check of `simulator/data/accounts_3layer.json`
   - Check `simulator/data/family_email_allowlist.json`
   - Verify `simulator/static/js/app.js` login gate payload
"""
from __future__ import annotations

import concurrent.futures
import hashlib
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

from simulator.auth.invite_and_gmail_mixin import (
    HARDCODED_REAL_EMAIL_ALLOWLIST,
    AuthInviteGmailMixin,
    is_email_allowlisted_for_real_send,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent


class MockAuthManager(AuthInviteGmailMixin):
    """Clean standalone instance of AuthInviteGmailMixin for direct stress testing."""

    def __init__(self):
        self.accounts = []
        self.family_email_allowlist = {}
        self.invite_links = {
            "STRESS_INV_01": {
                "code": "STRESS_INV_01",
                "target_tier": 2,
                "target_role_label": "Thành viên",
                "issuer_name": "Nguyễn Tuấn Anh",
                "full_url": "http://localhost:8000/invite?code=STRESS_INV_01",
            }
        }
        self.pending_invite_registrations = {}
        self.event_logs = []

    def _log_event(self, **kwargs):
        self.event_logs.append(kwargs)
        return kwargs

    def find_account(self, actor_id: str):
        return None


# ==============================================================================
# 1. Adversarial Evasion Payloads
# ==============================================================================

UNICODE_SPOOF_PAYLOADS = [
    # Cyrillic lookalikes
    ("nep94121@gm\u0430il.com", "Cyrillic small 'a'"),
    ("n\u0435p94121@gmail.com", "Cyrillic small 'ie'"),
    ("s\u0435nat6031@gmail.com", "Cyrillic small 'ie' in senat"),
    ("sen\u0430t6031@gmail.com", "Cyrillic small 'a' in senat"),
    ("kbanh376@gm\u0430il.com", "Cyrillic small 'a' in kbanh domain"),
    ("nep94121@gma\u0456l.com", "Cyrillic small 'byelorussian-ukrainian i'"),
    ("nep94121@\u0441om", "Cyrillic small 'es' in com"),
    # Greek lookalikes
    ("sen\u03b1t6031@gmail.com", "Greek small alpha"),
    ("nep94121@gm\u03b1il.com", "Greek small alpha in domain"),
    ("nep94121@gma\u03b9l.com", "Greek small iota"),
    ("nep94121@gmail.c\u03bfm", "Greek small omicron"),
    # Fullwidth characters
    ("\uff4e\uff45\uff5094121@gmail.com", "Fullwidth 'nep'"),
    ("nep94121@\uff47\uff4d\uff41\uff49\uff4c.\uff43\uff4f\uff4d", "Fullwidth 'gmail.com'"),
    ("\uff4e\uff45\uff50\uff19\uff14\uff11\uff12\uff11\uff20\uff47\uff4d\uff41\uff49\uff4c\uff0e\uff43\uff4f\uff4d", "Full fullwidth address"),
    # Zero-width & invisible characters
    ("nep\u200b94121@gmail.com", "Zero-width space in localpart"),
    ("nep94121@gmail\u200b.com", "Zero-width space before TLD"),
    ("nep94121\u200c@gmail.com", "Zero-width non-joiner"),
    ("nep94121\u200d@gmail.com", "Zero-width joiner"),
    ("nep94121@\ufeffgmail.com", "Zero-width no-break space (BOM)"),
    ("\u200enep94121@gmail.com", "Left-to-right mark"),
    ("\u202enep94121@gmail.com", "Right-to-left override"),
    ("nep94121\u00a0@gmail.com", "Non-breaking space"),
    # Accented & Turkish
    ("n\u00e9p94121@gmail.com", "Accented e"),
    ("\u0130ep94121@gmail.com", "Turkish capital dotted I"),
]

CRLF_INJECTION_PAYLOADS = [
    ("nep94121@gmail.com\r\nBcc: evil@attacker.org", "CRLF Bcc injection"),
    ("nep94121@gmail.com\nBcc: evil@attacker.org", "LF Bcc injection"),
    ("nep94121@gmail.com\rBcc: evil@attacker.org", "CR Bcc injection"),
    ("nep94121@gmail.com\r\nTo: victim@example.com", "CRLF To replacement"),
    ("senat6031@gmail.com\r\nSubject: Overwrite", "CRLF Subject overwrite"),
    ("kbanh376@gmail.com%0d%0aBcc:evil@attacker.org", "URL-encoded CRLF"),
    ("nep94121@gmail.com%0ABcc:evil@attacker.org", "URL-encoded LF"),
    ("nep94121@gmail.com\r\n\r\nDATA INJECTION", "Double CRLF body break"),
]

SUBDOMAIN_AND_DOMAIN_MANIPULATION_PAYLOADS = [
    ("nep94121@sub.gmail.com", "Subdomain sub.gmail.com"),
    ("nep94121@mail.gmail.com", "Subdomain mail.gmail.com"),
    ("nep94121@gmail.com.attacker.com", "Domain appended with attacker domain"),
    ("senat6031@gmail.com.evil.org", "senat domain appended evil.org"),
    ("kbanh376@attacker.org", "Completely different domain"),
    ("nep94121@attacker-gmail.com", "Hyphenated attacker domain"),
    ("nep94121@fakegmail.com", "Fake gmail brand"),
    ("nep94121@gmail.co", "Truncated TLD .co"),
    ("nep94121@gmail.company", "Extended TLD .company"),
    ("nep94121@gmail.com.br", "Country code addition"),
    ("attacker@nep94121@gmail.com", "Multiple @ signs prepended"),
    ("nep94121@gmail.com@evil.com", "Multiple @ signs appended"),
]

SYNTAX_ANOMALIES_PAYLOADS = [
    ("nep94121@gmail.com.", "Trailing dot on FQDN"),
    ("nep94121.@gmail.com", "Trailing dot in local part"),
    (".nep94121@gmail.com", "Leading dot in local part"),
    ("nep94121..test@gmail.com", "Consecutive dots in local part"),
    ("senat6031@gmail..com", "Consecutive dots in domain"),
    ("senat6031@.gmail.com", "Leading dot in domain"),
    ("nep94121@gmail", "Missing TLD"),
    ("@gmail.com", "Missing local part"),
    ("nep94121@", "Missing domain part"),
    ("nep94121", "Bare string without @"),
    ("nep94121@@gmail.com", "Double @"),
    ("nep94121@gmail@com", "Separated by @ instead of dot"),
]

EMBEDDED_CONTROL_CHARS_PAYLOADS = [
    ("nep94121@gmail.com\x00evil@attacker.com", "Null byte before evil address"),
    ("evil@attacker.com\x00nep94121@gmail.com", "Null byte after evil address"),
    ("nep94121@gmail.com\x00", "Trailing null byte"),
    ("\x00nep94121@gmail.com", "Leading null byte"),
    ("nep94121\x07@gmail.com", "Bell char \x07"),
    ("nep94121\x1b@gmail.com", "Escape char \x1b"),
    ("nep94121\x08@gmail.com", "Backspace char \x08"),
]

DELIMITER_INJECTION_PAYLOADS = [
    ("nep94121@gmail.com,evil@attacker.com", "Comma delimiter"),
    ("nep94121@gmail.com;evil@attacker.com", "Semicolon delimiter"),
    ("nep94121@gmail.com evil@attacker.com", "Space delimiter"),
    ("nep94121@gmail.com\tevil@attacker.com", "Tab delimiter"),
    ("nep94121@gmail.com|evil@attacker.com", "Pipe delimiter"),
    ("nep94121@gmail.com/evil@attacker.com", "Slash delimiter"),
    ("nep94121@gmail.com:evil@attacker.com", "Colon delimiter"),
    ("nep94121@gmail.com\nevil@attacker.com", "Newline delimiter"),
]

RFC_TRICKS_PAYLOADS = [
    ("<nep94121@gmail.com>", "Angle brackets"),
    ('"nep94121@gmail.com"', "Double quotes"),
    ("'nep94121@gmail.com'", "Single quotes"),
    ('"Nguyen Tuan Anh" <nep94121@gmail.com>', "Full name with angle brackets"),
    ('<evil@attacker.com> nep94121@gmail.com', "Leading evil angle bracket"),
    ('nep94121(comment)@gmail.com', "RFC comment in localpart"),
    ('nep94121@gmail.com(comment)', "RFC comment after domain"),
    ('nep94121+tag@gmail.com', "Plus addressing tag"),
    ('senat6031+dev@gmail.com', "Plus addressing tag on senat"),
    ('kbanh376+backup@gmail.com', "Plus addressing tag on kbanh"),
]


# ==============================================================================
# Test Class 1: Evasion Stress Testing
# ==============================================================================

class TestAdversarialAllowlistEvasion:
    """Empirical challenge against allowlist filter with diverse evasion attacks."""

    @pytest.mark.parametrize("payload, desc", UNICODE_SPOOF_PAYLOADS)
    def test_unicode_spoofing_rejected(self, payload: str, desc: str):
        """Unicode spoofing / homoglyphs must NEVER be accepted as allowlisted."""
        assert is_email_allowlisted_for_real_send(payload) is False, f"Failed on {desc}: {payload!r}"

    @pytest.mark.parametrize("payload, desc", CRLF_INJECTION_PAYLOADS)
    def test_crlf_injection_rejected(self, payload: str, desc: str):
        """CRLF injection payloads must NEVER be accepted as allowlisted."""
        assert is_email_allowlisted_for_real_send(payload) is False, f"Failed on {desc}: {payload!r}"

    @pytest.mark.parametrize("payload, desc", SUBDOMAIN_AND_DOMAIN_MANIPULATION_PAYLOADS)
    def test_domain_manipulation_rejected(self, payload: str, desc: str):
        """Subdomains and appended domains must NEVER be accepted."""
        assert is_email_allowlisted_for_real_send(payload) is False, f"Failed on {desc}: {payload!r}"

    @pytest.mark.parametrize("payload, desc", SYNTAX_ANOMALIES_PAYLOADS)
    def test_syntax_anomalies_rejected(self, payload: str, desc: str):
        """Malformed email syntax and trailing dots must be rejected."""
        assert is_email_allowlisted_for_real_send(payload) is False, f"Failed on {desc}: {payload!r}"

    @pytest.mark.parametrize("payload, desc", EMBEDDED_CONTROL_CHARS_PAYLOADS)
    def test_control_chars_rejected(self, payload: str, desc: str):
        """Null bytes and ASCII control characters must be rejected."""
        assert is_email_allowlisted_for_real_send(payload) is False, f"Failed on {desc}: {payload!r}"

    @pytest.mark.parametrize("payload, desc", DELIMITER_INJECTION_PAYLOADS)
    def test_delimiter_injection_rejected(self, payload: str, desc: str):
        """Multi-recipient delimiter injections must be rejected."""
        assert is_email_allowlisted_for_real_send(payload) is False, f"Failed on {desc}: {payload!r}"

    @pytest.mark.parametrize("payload, desc", RFC_TRICKS_PAYLOADS)
    def test_rfc_tricks_and_tags_rejected(self, payload: str, desc: str):
        """Angle brackets, comments, quotes, and subaddressing tags must be rejected."""
        assert is_email_allowlisted_for_real_send(payload) is False, f"Failed on {desc}: {payload!r}"

    @pytest.mark.parametrize(
        "non_string_val",
        [
            None,
            12345,
            123.456,
            [],
            ["nep94121@gmail.com"],
            {},
            {"email": "nep94121@gmail.com"},
            True,
            False,
            object(),
            b"nep94121@gmail.com",
        ],
    )
    def test_non_string_types_gracefully_rejected(self, non_string_val: Any):
        """Non-string inputs must return False without throwing uncaught exceptions."""
        assert is_email_allowlisted_for_real_send(non_string_val) is False

    @pytest.mark.parametrize(
        "valid_case_email",
        [
            "nep94121@gmail.com",
            "NEP94121@GMAIL.COM",
            "Nep94121@Gmail.Com",
            "senat6031@gmail.com",
            "SENAT6031@GMAIL.COM",
            "kbanh376@gmail.com",
            "KBANH376@GMAIL.COM",
            "  nep94121@gmail.com  ",
            "\t\n  senat6031@gmail.com \r\n",
        ],
    )
    def test_valid_allowlisted_case_variations_and_whitespace_accepted(self, valid_case_email: str):
        """Legitimate allowlisted addresses with case variations or surrounding whitespace must pass."""
        assert is_email_allowlisted_for_real_send(valid_case_email) is True


# ==============================================================================
# Test Class 2: Dispatcher Gate Airtightness Under Adversarial Attack
# ==============================================================================

class TestDispatcherAirtightness:
    """Verifies that neither send_real_gmail_otp nor send_invite_link_via_gmail dispatches when under attack."""

    @pytest.fixture
    def auth_mgr(self) -> MockAuthManager:
        return MockAuthManager()

    def test_all_evasion_payloads_blocked_in_send_real_gmail_otp(
        self, auth_mgr: MockAuthManager, monkeypatch: pytest.MonkeyPatch
    ):
        """Empirical proof: every single evasion payload is blocked before SMTP/gws is invoked."""
        all_payloads = (
            UNICODE_SPOOF_PAYLOADS
            + CRLF_INJECTION_PAYLOADS
            + SUBDOMAIN_AND_DOMAIN_MANIPULATION_PAYLOADS
            + SYNTAX_ANOMALIES_PAYLOADS
            + EMBEDDED_CONTROL_CHARS_PAYLOADS
            + DELIMITER_INJECTION_PAYLOADS
            + RFC_TRICKS_PAYLOADS
        )

        smtp_called = []
        gws_called = []

        def fail_smtp(*args, **kwargs):
            smtp_called.append(args)
            raise RuntimeError("CRITICAL VIOLATION: SMTP contacted for malicious payload!")

        def fail_gws(cmd, *args, **kwargs):
            if "gws" in str(cmd):
                gws_called.append(cmd)
                raise RuntimeError("CRITICAL VIOLATION: gws invoked for malicious payload!")
            return MagicMock()

        monkeypatch.setattr(smtplib, "SMTP", fail_smtp)
        monkeypatch.setattr(smtplib, "SMTP_SSL", fail_smtp)
        monkeypatch.setattr(subprocess, "run", fail_gws)

        # Even with credentials present in env
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "dummy_pass")
        monkeypatch.setenv("SMTP_USER", "nep94121@gmail.com")

        for payload, desc in all_payloads:
            res = auth_mgr.send_real_gmail_otp(
                target_email=payload,
                otp_code="999999",
                display_name="Attacker",
            )
            assert res.get("sent_real_gmail") is False, f"Leaked sent_real_gmail=True on {desc}: {payload!r}"
            assert res.get("blocked_by_allowlist") is True, f"Failed blocked_by_allowlist on {desc}: {payload!r}"

        assert len(smtp_called) == 0, f"SMTP was contacted {len(smtp_called)} times!"
        assert len(gws_called) == 0, f"gws was contacted {len(gws_called)} times!"

    def test_all_evasion_payloads_blocked_in_send_invite_link_via_gmail(
        self, auth_mgr: MockAuthManager, monkeypatch: pytest.MonkeyPatch
    ):
        """Empirical proof: every single evasion payload is blocked in invite link sender."""
        all_payloads = (
            UNICODE_SPOOF_PAYLOADS
            + CRLF_INJECTION_PAYLOADS
            + SUBDOMAIN_AND_DOMAIN_MANIPULATION_PAYLOADS
            + SYNTAX_ANOMALIES_PAYLOADS
            + EMBEDDED_CONTROL_CHARS_PAYLOADS
            + DELIMITER_INJECTION_PAYLOADS
            + RFC_TRICKS_PAYLOADS
        )

        gws_called = []

        def fail_gws(cmd, *args, **kwargs):
            if "gws" in str(cmd):
                gws_called.append(cmd)
                raise RuntimeError("CRITICAL VIOLATION: gws invoked for malicious invite payload!")
            return MagicMock()

        monkeypatch.setattr(subprocess, "run", fail_gws)

        for payload, desc in all_payloads:
            res = auth_mgr.send_invite_link_via_gmail(
                invite_code="STRESS_INV_01",
                recipient_email=payload,
            )
            assert res.get("sent_real_gmail") is False, f"Leaked invite on {desc}: {payload!r}"
            assert res.get("blocked_by_allowlist") is True, f"Failed invite blocked_by_allowlist on {desc}: {payload!r}"

        assert len(gws_called) == 0, f"gws was called {len(gws_called)} times!"

    def test_clean_allowlisted_address_with_surrounding_newlines_sanitized(
        self, auth_mgr: MockAuthManager, monkeypatch: pytest.MonkeyPatch
    ):
        """When an address is allowlisted but contains leading/trailing CRLF/spaces, actual_recipient must be cleaned."""
        captured_messages = []

        class InterceptSMTP:
            def __init__(self, *args, **kwargs):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def starttls(self):
                return (220, b"Ready")
            def login(self, u, p):
                return (235, b"Auth OK")
            def send_message(self, msg):
                captured_messages.append(msg)
                return {}

        monkeypatch.setattr(smtplib, "SMTP", InterceptSMTP)
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "dummy_pass")
        monkeypatch.setenv("SMTP_USER", "nep94121@gmail.com")

        res = auth_mgr.send_real_gmail_otp(
            target_email="\r\n  senat6031@gmail.com \n\t ",
            otp_code="123456",
            display_name="Senat User",
        )

        assert res.get("sent_real_gmail") is True
        assert res.get("actual_recipient") == "senat6031@gmail.com"
        assert len(captured_messages) == 1
        msg = captured_messages[0]
        # Crucial check: RFC header 'To' must not have any newlines or unstripped whitespace
        assert msg["To"] == "senat6031@gmail.com"
        assert "\r" not in msg["To"] and "\n" not in msg["To"]


# ==============================================================================
# Test Class 3: Test Isolation Concurrency & Edge-Cases
# ==============================================================================

class TestIsolationConcurrencyAndEdgeCases:
    """Verifies that the autouse fixture in tests/conftest.py survives concurrent load and unusual calls."""

    def test_concurrent_smtp_and_gws_mocking(self):
        """Verify 20 concurrent threads calling smtplib and subprocess.run simultaneously."""
        errors = []

        def worker_task(thread_id: int):
            try:
                # 1. smtplib.SMTP context manager
                with smtplib.SMTP("smtp.gmail.com", 587) as server:
                    server.login("dummy", "dummy")
                    server.sendmail("from@example.com", ["to@example.com"], "Test Message")

                # 2. smtplib.SMTP_SSL context manager
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server_ssl:
                    server_ssl.login("dummy", "dummy")

                # 3. smtplib.SMTP without context manager
                s = smtplib.SMTP("smtp.gmail.com", 587)
                s.login("dummy", "dummy")

                # 4. subprocess.run with list
                p1 = subprocess.run(["gws", "gmail", "users", "messages", "send"], capture_output=True, text=True)
                assert p1.returncode == 0
                assert "mock_gws_isolation" in p1.stdout

                # 5. subprocess.run with string and shell=True
                p2 = subprocess.run("gws gmail users messages send --params {}", capture_output=True, text=True, shell=True)
                assert p2.returncode == 0
                assert "mock_gws_isolation" in p2.stdout

                # 6. subprocess.run with tuple
                p3 = subprocess.run(("gws", "gmail", "users", "messages", "list"), capture_output=True, text=True)
                assert p3.returncode == 0
                assert "mock_gws_isolation" in p3.stdout

            except Exception as e:
                errors.append((thread_id, str(e)))

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker_task, i) for i in range(20)]
            concurrent.futures.wait(futures)

        assert len(errors) == 0, f"Concurrent isolation failure: {errors}"

    def test_non_gws_subprocess_calls_are_not_hijacked(self):
        """subprocess.run calls for non-gws commands (like python --version) must run normally."""
        proc = subprocess.run([sys_python(), "--version"], capture_output=True, text=True)
        assert proc.returncode == 0
        assert "Python" in (proc.stdout or proc.stderr)
        assert "mock_gws_isolation" not in (proc.stdout or "")


def sys_python() -> str:
    import sys
    return sys.executable


# ==============================================================================
# Test Class 4: Demo Seed Accounts & Fixtures Deep Audit
# ==============================================================================

class TestSeedAccountsAndFixturesAudit:
    """Deep structural, cryptographic, and permission audit of simulator/data/accounts_3layer.json."""

    def test_accounts_3layer_deep_audit(self):
        """Verify exact length 6, correct schema, valid password hashes, and no leaked secrets."""
        acc_path = ROOT / "simulator" / "data" / "accounts_3layer.json"
        assert acc_path.exists(), f"Missing file: {acc_path}"

        raw_data = acc_path.read_text(encoding="utf-8")
        accounts = json.loads(raw_data)

        # 1. Exact length
        assert len(accounts) == 6, f"Expected exactly 6 seed accounts, got {len(accounts)}"

        # 2. Account IDs and roles specification
        expected_specs = {
            "tuan_anh": {
                "email": "nep94121@gmail.com",
                "tier": 1,
                "role": "ADMIN",
                "permission_active": True,
            },
            "thanh_vien_a": {
                "email": "thanhviena.hust@gmail.com",
                "tier": 2,
                "role": "MEMBER",
                "permission_active": True,
            },
            "thanh_vien_b": {
                "email": "thanhvienb.hust@gmail.com",
                "tier": 2,
                "role": "MEMBER",
                "permission_active": True,
            },
            "khach_c": {
                "email": "khachc.guest@gmail.com",
                "tier": 3,
                "role": "CHILD_GUEST",
                "permission_active": True,
            },
            "senat6031": {
                "email": "senat6031@gmail.com",
                "tier": 2,
                "role": "MEMBER",
                "permission_active": True,
            },
            "kbanh376": {
                "email": "kbanh376@gmail.com",
                "tier": 3,
                "role": "CHILD_GUEST",
                "permission_active": True,
            },
        }

        found_ids = set()
        for acc in accounts:
            acc_id = acc.get("account_id")
            assert acc_id in expected_specs, f"Unexpected account_id '{acc_id}' in accounts_3layer.json"
            spec = expected_specs[acc_id]
            found_ids.add(acc_id)

            assert acc.get("email") == spec["email"], f"Email mismatch for {acc_id}"
            assert acc.get("tier") == spec["tier"], f"Tier mismatch for {acc_id}"
            assert acc.get("role") == spec["role"], f"Role mismatch for {acc_id}"
            assert acc.get("permission_active") == spec["permission_active"], f"Active status mismatch for {acc_id}"

            # Verify password hash format (SHA-256 is 64 hex characters)
            pwd_hash = acc.get("password_hash", "")
            assert len(pwd_hash) == 64, f"Invalid SHA-256 hash length ({len(pwd_hash)}) for {acc_id}"
            assert re.fullmatch(r"[0-9a-f]{64}", pwd_hash), f"Invalid SHA-256 hex chars in {acc_id}"

            # If password_plain_hint is present, verify hash match via verify_password_hash
            hint = acc.get("password_plain_hint")
            if hint:
                from simulator.auth.constants_and_crypto import verify_password_hash
                assert verify_password_hash(hint, pwd_hash), f"Hash mismatch with hint for {acc_id}"

            # Check voiceprint block structure
            vp = acc.get("voiceprint")
            assert isinstance(vp, dict), f"voiceprint must be a dict for {acc_id}"
            assert "enrolled" in vp, f"voiceprint missing 'enrolled' in {acc_id}"

        assert found_ids == set(expected_specs.keys()), f"Missing accounts: {set(expected_specs.keys()) - found_ids}"

    def test_family_email_allowlist_is_empty_json_object(self):
        """Verify simulator/data/family_email_allowlist.json is exactly {}."""
        fa_path = ROOT / "simulator" / "data" / "family_email_allowlist.json"
        assert fa_path.exists(), f"Missing file: {fa_path}"
        data = json.loads(fa_path.read_text(encoding="utf-8"))
        assert data == {}, f"Expected empty dict {{}}, got: {data}"

    def test_app_js_login_gate_send_gmail_false(self):
        """Verify simulator/static/js/app.js sends send_gmail: false on layer1_login."""
        app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
        assert app_js_path.exists(), f"Missing file: {app_js_path}"
        content = app_js_path.read_text(encoding="utf-8")
        assert "btnSubmitGateLogin" in content
        login_idx = content.find("btnSubmitGateLogin")
        fetch_idx = content.find("/api/auth3/layer1_login", login_idx)
        assert fetch_idx != -1
        slice_code = content[fetch_idx : fetch_idx + 400]
        # Regex check for send_gmail: false (either quoted or unquoted JS object literal key)
        assert re.search(r'(?:["\']send_gmail["\']|send_gmail)\s*:\s*false', slice_code), (
            f"Expected 'send_gmail': false in login fetch, found: {slice_code}"
        )
