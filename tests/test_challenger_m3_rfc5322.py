"""Empirical Adversarial Stress-Testing Suite for Milestone 3 (R3: Email RFC 5322 Standards & Deliverability).

Author: challenger_m3_1 (teamwork_challenger)
Roles: critic, specialist
Target: simulator/auth/invite_and_gmail_mixin.py & smart_home email dispatches

Challenge Dimensions:
1. RFC 5322 Header Fuzzing:
   - Unicode display names (Vietnamese, East Asian, Cyrillic, Arabic, special chars, quotes, commas)
   - CRLF Header Injection Defense (\r\nBcc:, \r\nSubject:)
   - SMTP domain variations (punycode, subdomains, missing @ fallback)
   - Date header RFC 2822/5322 timezone and parseability
   - Message-ID uniqueness and <id@domain> format
   - Reply-To header parseability and match with From

2. Subject Anti-Spam Fuzzing:
   - Strict absence of ANY digits (0-9) in OTP subjects
   - Strict absence of ANY ALL-CAPS words (2+ uppercase letters: OTP, AI, OAUTH, SMS)
   - Strict absence of ANY emojis across Unicode planes
   - Adversarial arguments in display_name, otp_code, invite_info

3. MIME Multipart Alternative Fuzzing:
   - Strict multipart/alternative structure with 2 parts (text/plain, text/html)
   - Plain text hygiene: zero emojis, OTP present, valid UTF-8
   - HTML hygiene: light background (#ffffff / #f8fafc), zero emojis, zero deceptive Google OAuth branding
   - Container id="otp-code-value" verification
   - Adversarial XSS / markup injection resilience

4. Gmail Inbox Scraper Fuzzing:
   - 4-level deeply nested multipart MIME payloads
   - Corrupted Base64URL and malformed padding resilience
   - Missing parts, single-part payloads, None body/parts edge cases
   - OTP precedence: HTML container vs snippet false-positive 6-digit numbers
   - Leading zeros preservation ("001234", "000000")
   - Whitespace and line breaks inside container

5. Zero-Leak Security Audit:
   - Verification that no SMTP secret values are exposed in return dictionaries or audit logs
"""

from __future__ import annotations

import base64
import email
import email.utils
import json
import os
import re
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from simulator.auth.invite_and_gmail_mixin import AuthInviteGmailMixin


# ==============================================================================
# TEST HARNESS & FIXTURES
# ==============================================================================

class ChallengerTestAuthManager(AuthInviteGmailMixin):
    """Minimal test harness for AuthInviteGmailMixin with event capture."""

    def __init__(self):
        self.invite_links = {
            "INV-CHALLENGE-T2": {
                "invite_code": "INV-CHALLENGE-T2",
                "issuer_email": "senat6031@gmail.com",
                "issuer_name": "Nguyễn Tuấn Anh (Cấp 1)",
                "issuer_tier": 1,
                "target_tier": 2,
                "target_role_label": "Người nhà (Tầng 2)",
                "url_path": "/auth?invite=INV-CHALLENGE-T2",
                "full_url": "http://localhost:8088/auth?invite=INV-CHALLENGE-T2",
            }
        }
        self.audit_logs: list[dict[str, Any]] = []

    def _log_event(self, **kwargs):
        self.audit_logs.append(kwargs)

    def _save_invite_links(self):
        pass


@pytest.fixture
def auth_mgr() -> ChallengerTestAuthManager:
    return ChallengerTestAuthManager()


# Regex helpers for emoji detection
EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff]|[\u2600-\u26ff]|[\u2700-\u27bf]|[\u2300-\u23ff]|[\u2b50]|[\u3030]"
)
ALL_CAPS_WORD_PATTERN = re.compile(r"\b[A-Z]{2,}\b")


# ==============================================================================
# SECTION 1: RFC 5322 HEADER FUZZING & INJECTION DEFENSE
# ==============================================================================

class TestRFC5322HeaderFuzzingAndInjection:
    """Stress-test RFC 5322 header generation with adversarial inputs."""

    @pytest.mark.parametrize("adversarial_name,expected_addr", [
        ("Nguyễn Tuấn Anh", "senat6031@gmail.com"),
        ("山田 太郎", "senat6031@gmail.com"),
        ("أحمد بن علي", "senat6031@gmail.com"),
        ("Иван Иванович Иванов", "senat6031@gmail.com"),
        ("Jane (Administrator) Doe", "senat6031@gmail.com"),
        ("Doe, Jane", "senat6031@gmail.com"),
        ("Test \"Quoted\" Name", "senat6031@gmail.com"),
        ("Angle <bracket> Name", "senat6031@gmail.com"),
        ("A" * 150, "senat6031@gmail.com"),
    ])
    def test_rfc5322_fuzz_unicode_and_special_display_names(
        self, auth_mgr: ChallengerTestAuthManager, adversarial_name: str, expected_addr: str
    ):
        """Stress-test formataddr with international unicode, quotes, brackets, long names."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "mock-app-password"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            res = auth_mgr.send_real_gmail_otp(
                target_email=expected_addr,
                otp_code="384912",
                display_name=adversarial_name,
            )
            assert res.get("sent_real_gmail") is True
            msg = mock_smtp.send_message.call_args[0][0]

            # 1. Message must serialize cleanly to bytes without UnicodeEncodeError
            raw_bytes = msg.as_bytes()
            assert len(raw_bytes) > 0

            # 2. To header must be parseable and preserve destination email
            to_hdr = msg["To"]
            parsed_name, parsed_addr = email.utils.parseaddr(to_hdr)
            assert parsed_addr == expected_addr

            # 3. From header must be valid RFC 5322 mailbox
            from_hdr = msg["From"]
            from_name, from_addr = email.utils.parseaddr(from_hdr)
            assert from_name == "Smart Home Voice AI"
            assert "@" in from_addr

            # 4. Message-ID must exist and be enclosed in angle brackets
            msg_id = msg["Message-ID"]
            assert msg_id.startswith("<") and msg_id.endswith(">")

    def test_rfc5322_crlf_header_injection_defense(self, auth_mgr: ChallengerTestAuthManager):
        """Verify that attempted CRLF header injection in display_name cannot inject arbitrary headers."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "mock-app-password"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            malicious_name = "Senat Admin\r\nBcc: evil_stealer@attacker.org\r\nX-Spam: No\r\n"
            auth_mgr.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="948123",
                display_name=malicious_name,
            )

            msg = mock_smtp.send_message.call_args[0][0]

            # 1. Injected headers must NOT exist as top-level headers in MIME message
            assert "Bcc" not in msg
            assert "X-Spam" not in msg

            # 2. When serialized, Python's email library must actively detect the embedded header
            # and raise HeaderParseError, preventing transmission of malicious headers
            with pytest.raises(email.errors.HeaderParseError) as exc_info:
                msg.as_bytes()
            assert "embedded header" in str(exc_info.value).lower()

    @pytest.mark.parametrize("sender_env,expected_domain", [
        ("nep94121@gmail.com", "gmail.com"),
        ("alerts@sub.iot.smarthome.vn", "sub.iot.smarthome.vn"),
        ("admin@xn--h-4ia.vn", "xn--h-4ia.vn"),
        ("plain-user-without-at", "gmail.com"),
        ("", "gmail.com"),
    ])
    def test_rfc5322_smtp_user_domain_variations(
        self, auth_mgr: ChallengerTestAuthManager, sender_env: str, expected_domain: str
    ):
        """Verify Message-ID domain resolution under various SMTP_USER environment configurations."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        env_patch = {"GMAIL_APP_PASSWORD": "mock-app-password"}
        if sender_env:
            env_patch["SMTP_USER"] = sender_env
        else:
            env_patch.pop("SMTP_USER", None)

        with patch.dict(os.environ, env_patch), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            auth_mgr.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="102938",
                display_name="Domain Test",
            )
            msg = mock_smtp.send_message.call_args[0][0]

            msg_id = msg["Message-ID"]
            assert msg_id.startswith("<") and msg_id.endswith(">")
            assert f"@{expected_domain}>" in msg_id

    def test_rfc5322_date_header_conformance_and_timezone(self, auth_mgr: ChallengerTestAuthManager):
        """Verify that Date header conforms to RFC 2822/5322 and can be parsed into a datetime."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "mock-app-password"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            auth_mgr.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="628194",
                display_name="Date Test",
            )
            msg = mock_smtp.send_message.call_args[0][0]

            date_str = msg["Date"]
            assert date_str is not None
            parsed_dt = email.utils.parsedate_to_datetime(date_str)
            assert parsed_dt is not None
            # Must have timezone info (tzinfo is not None)
            assert parsed_dt.tzinfo is not None


# ==============================================================================
# SECTION 2: SUBJECT ANTI-SPAM HEURISTICS FUZZING
# ==============================================================================

class TestSubjectAntiSpamFuzzing:
    """Stress-test email subjects to ensure strict deliverability & anti-spam compliance."""

    def test_otp_subject_strictly_zero_digits_zero_all_caps_zero_emojis(
        self, auth_mgr: ChallengerTestAuthManager
    ):
        """Verify that under any user-supplied parameters, OTP email Subject remains strictly compliant."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        adversarial_inputs = [
            {"display_name": "USER ALL CAPS 123456 🔥 🚨", "otp": "999888"},
            {"display_name": "ADMIN-VIP 000000 🚀", "otp": "000000"},
            {"display_name": "x" * 100, "otp": "111222"},
        ]

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "mock-app-password"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            for item in adversarial_inputs:
                auth_mgr.send_real_gmail_otp(
                    target_email="senat6031@gmail.com",
                    otp_code=item["otp"],
                    display_name=item["display_name"],
                )
                msg = mock_smtp.send_message.call_args[0][0]
                subj = msg["Subject"]

                # 1. Strictly NO digits of any kind
                digits_found = re.findall(r"\d", subj)
                assert not digits_found, f"Subject contains digits: {digits_found} in '{subj}'"

                # 2. Strictly NO ALL-CAPS words (e.g. OTP, AI, OAUTH, SMS, VIP)
                all_caps = ALL_CAPS_WORD_PATTERN.findall(subj)
                assert not all_caps, f"Subject contains ALL-CAPS words: {all_caps} in '{subj}'"

                # 3. Strictly NO emojis
                emojis = EMOJI_PATTERN.findall(subj)
                assert not emojis, f"Subject contains emojis: {emojis} in '{subj}'"

                # 4. Matches exact clean subject
                assert subj == "Smart Home Voice - Mã xác thực tài khoản"

    def test_invite_subject_strictly_no_all_caps_no_emojis(self, auth_mgr: ChallengerTestAuthManager):
        """Verify that invite email Subject contains zero ALL-CAPS words and zero emojis."""
        captured_messages = []

        def fake_subprocess_run(cmd, *args, **kwargs):
            if cmd and cmd[0] == "gws":
                for i, arg in enumerate(cmd):
                    if arg == "--json" and i + 1 < len(cmd):
                        data = json.loads(cmd[i + 1])
                        raw = base64.urlsafe_b64decode(data["raw"])
                        captured_messages.append(email.message_from_bytes(raw))
                return MagicMock(returncode=0, stdout='{"id": "msg-inv-fuzz"}', stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch.dict(os.environ, {"SMTP_USER": "nep94121@gmail.com"}), \
             patch("subprocess.run", side_effect=fake_subprocess_run):

            auth_mgr.send_invite_link_via_gmail(
                invite_code="INV-CHALLENGE-T2",
                recipient_email="senat6031@gmail.com",
            )
            assert len(captured_messages) == 1
            subj = captured_messages[0]["Subject"]

            # Must not contain ALL-CAPS (e.g. 'AI' was in old subject '[Smart Home Voice AI]')
            all_caps = ALL_CAPS_WORD_PATTERN.findall(subj)
            assert not all_caps, f"Invite Subject contains ALL-CAPS words: {all_caps} in '{subj}'"

            # Must not contain emojis
            emojis = EMOJI_PATTERN.findall(subj)
            assert not emojis, f"Invite Subject contains emojis: {emojis} in '{subj}'"


# ==============================================================================
# SECTION 3: MIME MULTIPART ALTERNATIVE PAYLOAD HYGIENE
# ==============================================================================

class TestMIMEMultipartPayloadHygiene:
    """Stress-test MIME multipart construction, HTML styles, and deceptive branding checks."""

    def test_mime_structure_and_dual_part_presence(self, auth_mgr: ChallengerTestAuthManager):
        """Verify message is multipart/alternative with exactly text/plain and text/html."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "mock-app-password"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            auth_mgr.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="718293",
                display_name="Senat Recipient",
            )
            msg = mock_smtp.send_message.call_args[0][0]

            assert msg.is_multipart() is True
            assert msg.get_content_type() == "multipart/alternative"

            parts = msg.get_payload()
            assert len(parts) == 2, f"Expected exactly 2 parts (plain + html), found {len(parts)}"

            content_types = [p.get_content_type() for p in parts]
            assert content_types == ["text/plain", "text/html"], f"Wrong part types: {content_types}"

    def test_mime_plain_text_hygiene(self, auth_mgr: ChallengerTestAuthManager):
        """Verify plain text part contains OTP, clean linebreaks, and zero emojis."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "mock-app-password"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            auth_mgr.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="839102",
                display_name="Senat Recipient",
            )
            msg = mock_smtp.send_message.call_args[0][0]
            plain_part = msg.get_payload()[0]
            plain_text = plain_part.get_payload(decode=True).decode("utf-8")

            # Contains OTP code
            assert "839102" in plain_text
            # Zero emojis
            assert not EMOJI_PATTERN.search(plain_text)
            # Zero deceptive Google OAuth references
            assert "Google OAuth" not in plain_text
            assert "XÁC NHẬN GOOGLE" not in plain_text

    def test_mime_html_hygiene_and_light_theme(self, auth_mgr: ChallengerTestAuthManager):
        """Verify HTML part uses light background, zero emojis, zero fake Google OAuth, and valid container."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "mock-app-password"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            auth_mgr.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="918273",
                display_name="Senat Recipient",
            )
            msg = mock_smtp.send_message.call_args[0][0]
            html_part = msg.get_payload()[1]
            html_text = html_part.get_payload(decode=True).decode("utf-8")

            # Must contain OTP inside id="otp-code-value"
            assert 'id="otp-code-value"' in html_text
            assert "918273" in html_text

            # Zero emojis
            assert not EMOJI_PATTERN.search(html_text)

            # Zero deceptive branding
            assert "Google OAuth" not in html_text
            assert "XÁC NHẬN GOOGLE OAUTH" not in html_text

            # Light background (#ffffff or #f8fafc)
            assert "#f8fafc" in html_text or "#ffffff" in html_text
            # Ensure dark background #0f172a is NOT applied to body background
            assert '<body style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;margin:0;padding:24px;background-color:#f8fafc;color:#1e293b;">' in html_text

    def test_mime_html_xss_injection_resilience(self, auth_mgr: ChallengerTestAuthManager):
        """Verify that passing HTML/script tags in display_name or password does not break MIME formatting."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        xss_name = "<script>alert('XSS')</script><b>Injected</b>"
        xss_pass = "<img src=x onerror=alert(1)>"

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "mock-app-password"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            res = auth_mgr.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="472910",
                display_name=xss_name,
                issued_password=xss_pass,
            )
            assert res.get("sent_real_gmail") is True
            msg = mock_smtp.send_message.call_args[0][0]

            # Message must remain valid multipart
            assert msg.is_multipart() is True
            raw_bytes = msg.as_bytes()
            assert len(raw_bytes) > 0


# ==============================================================================
# SECTION 4: RESILIENT GMAIL INBOX SCRAPER FUZZING
# ==============================================================================

class TestGmailInboxScraperFuzzing:
    """Stress-test read_latest_otp_from_gmail_inbox with deep hierarchies and adversarial payloads."""

    def test_scraper_deeply_nested_4levels_multipart(self, auth_mgr: ChallengerTestAuthManager):
        """Extract OTP from a 4-level nested multipart hierarchy (mixed -> related -> alternative -> html)."""
        html_content = '<div class="wrapper"><div id="otp-code-value">394817</div></div>'
        b64_html = base64.urlsafe_b64encode(html_content.encode("utf-8")).decode("ascii")

        nested_payload = {
            "snippet": "No OTP in snippet...",
            "payload": {
                "headers": [{"name": "Subject", "value": "Smart Home Voice - Mã xác thực tài khoản"}],
                "parts": [
                    {
                        "mimeType": "multipart/mixed",
                        "parts": [
                            {
                                "mimeType": "multipart/related",
                                "parts": [
                                    {
                                        "mimeType": "multipart/alternative",
                                        "parts": [
                                            {"mimeType": "text/html", "body": {"data": b64_html}}
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        }

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "messages" in cmd and "get" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps(nested_payload), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            res = auth_mgr.read_latest_otp_from_gmail_inbox(message_id="msg-deep-4level")
            assert res.get("ok") is True
            assert res.get("extracted_otp") == "394817"

    def test_scraper_corrupted_base64_and_malformed_padding_resilience(
        self, auth_mgr: ChallengerTestAuthManager
    ):
        """Scraper must gracefully skip corrupted/invalid Base64 parts without crashing."""
        valid_html = '<div id="otp-code-value">712938</div>'
        b64_valid = base64.urlsafe_b64encode(valid_html.encode("utf-8")).decode("ascii")

        # Part 1 has corrupted base64 (invalid characters & invalid padding)
        corrupted_payload = {
            "snippet": "Corrupted part test",
            "payload": {
                "headers": [{"name": "Subject", "value": "Smart Home Voice - Mã xác thực tài khoản"}],
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": "!!!INVALID_BASE64_CHARACTERS!!!"}},
                    {"mimeType": "text/plain", "body": {"data": "A"}},  # len % 4 == 1 malformed padding
                    {"mimeType": "text/html", "body": {"data": b64_valid}},
                ],
            },
        }

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "messages" in cmd and "get" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps(corrupted_payload), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            res = auth_mgr.read_latest_otp_from_gmail_inbox(message_id="msg-corrupted")
            assert res.get("ok") is True
            assert res.get("extracted_otp") == "712938"

    def test_scraper_single_part_direct_payload_body(self, auth_mgr: ChallengerTestAuthManager):
        """Scraper must handle single-part messages where data is directly in payload['body']['data']."""
        plain = "Mã xác thực: 849201"
        b64 = base64.urlsafe_b64encode(plain.encode("utf-8")).decode("ascii")

        single_part_payload = {
            "snippet": "Single part snippet",
            "payload": {
                "headers": [{"name": "Subject", "value": "Smart Home Voice - Mã xác thực tài khoản"}],
                "body": {"data": b64},
            },
        }

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "messages" in cmd and "get" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps(single_part_payload), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            res = auth_mgr.read_latest_otp_from_gmail_inbox(message_id="msg-single-part")
            assert res.get("ok") is True
            assert res.get("extracted_otp") == "849201"

    def test_scraper_precedence_html_container_over_snippet_distractor_number(
        self, auth_mgr: ChallengerTestAuthManager
    ):
        """When snippet contains a distractor 6-digit number (e.g. order 999999), HTML container OTP must take precedence."""
        # Note: In Gmail, snippet often contains header or previous thread text with 6 digits
        html = '<div>Thông tin tài khoản:</div><div id="otp-code-value">582914</div>'
        b64_html = base64.urlsafe_b64encode(html.encode("utf-8")).decode("ascii")

        payload = {
            "snippet": "Mã đơn hàng trước đó: 999999. Cảm ơn bạn.",
            "payload": {
                "headers": [{"name": "Subject", "value": "Smart Home Voice - Mã xác thực tài khoản"}],
                "parts": [{"mimeType": "text/html", "body": {"data": b64_html}}],
            },
        }

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "messages" in cmd and "get" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps(payload), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            res = auth_mgr.read_latest_otp_from_gmail_inbox(message_id="msg-distractor")
            assert res.get("ok") is True
            # Even if snippet had "Mã đơn hàng...", does it extract 582914 or 999999?
            # In tier 1: (?:OTP|mã|code|xác thực)\s*(\d{6}) -> "Mã đơn hàng: 999999" has "mã đơn hàng"
            # In tier 2: id="otp-code-value">582914<
            assert res.get("extracted_otp") == "582914"

    @pytest.mark.parametrize("leading_zero_otp", ["001234", "000000", "012345"])
    def test_scraper_preserves_leading_zeros_as_strings(
        self, auth_mgr: ChallengerTestAuthManager, leading_zero_otp: str
    ):
        """Verify that OTP codes with leading zeros (e.g. '001234') are preserved as 6-digit strings."""
        html = f'<div id="otp-code-value">{leading_zero_otp}</div>'
        b64 = base64.urlsafe_b64encode(html.encode("utf-8")).decode("ascii")

        payload = {
            "snippet": f"OTP: {leading_zero_otp}",
            "payload": {
                "headers": [{"name": "Subject", "value": "Smart Home Voice - Mã xác thực tài khoản"}],
                "parts": [{"mimeType": "text/html", "body": {"data": b64}}],
            },
        }

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "messages" in cmd and "get" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps(payload), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            res = auth_mgr.read_latest_otp_from_gmail_inbox(message_id=f"msg-{leading_zero_otp}")
            assert res.get("ok") is True
            assert res.get("extracted_otp") == leading_zero_otp
            assert len(res.get("extracted_otp")) == 6

    def test_scraper_handles_whitespace_and_newlines_in_otp_container(
        self, auth_mgr: ChallengerTestAuthManager
    ):
        """Verify that regex handles whitespace or newlines inside the otp container."""
        html = '<div id="otp-code-value">\n   847291   \n</div>'
        b64 = base64.urlsafe_b64encode(html.encode("utf-8")).decode("ascii")

        payload = {
            "snippet": "Mã xác thực",
            "payload": {
                "headers": [{"name": "Subject", "value": "Smart Home Voice - Mã xác thực tài khoản"}],
                "parts": [{"mimeType": "text/html", "body": {"data": b64}}],
            },
        }

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "messages" in cmd and "get" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps(payload), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            res = auth_mgr.read_latest_otp_from_gmail_inbox(message_id="msg-whitespace")
            assert res.get("ok") is True
            assert res.get("extracted_otp") == "847291"

    def test_scraper_clean_failure_when_no_otp_found(self, auth_mgr: ChallengerTestAuthManager):
        """Verify clean error return when message exists but contains no 6-digit OTP."""
        payload = {
            "snippet": "Thư chào mừng không có mã số nào cả.",
            "payload": {
                "headers": [{"name": "Subject", "value": "Smart Home Voice - Chào mừng"}],
                "parts": [{"mimeType": "text/plain", "body": {"data": ""}}],
            },
        }

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "messages" in cmd and "get" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps(payload), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            res = auth_mgr.read_latest_otp_from_gmail_inbox(message_id="msg-no-otp")
            assert res.get("ok") is False
            assert "không tìm thấy chuỗi 6 số OTP" in res.get("error", "")

    def test_scraper_payload_with_none_body_or_none_parts_behavior(
        self, auth_mgr: ChallengerTestAuthManager
    ):
        """Empirical challenge: Gmail API sometimes returns parts where body is None or parts is None.
        
        Demonstrate that the outer try/except in read_latest_otp_from_gmail_inbox gracefully catches
        the AttributeError instead of raising an unhandled exception that crashes the process.
        """
        payload_with_none = {
            "snippet": "Mã xác thực: 667788",
            "payload": {
                "headers": [{"name": "Subject", "value": "Smart Home Voice - Mã xác thực tài khoản"}],
                "parts": [
                    {"mimeType": "text/plain", "body": None, "parts": None},
                ],
            },
        }

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "messages" in cmd and "get" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps(payload_with_none), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            res = auth_mgr.read_latest_otp_from_gmail_inbox(message_id="msg-none-body")
            # Outer try/except catches AttributeError and returns ok: False with safe error string
            assert res.get("ok") is False
            assert "error" in res

    def test_scraper_extracts_from_plain_text_with_keyword(
        self, auth_mgr: ChallengerTestAuthManager
    ):
        """Verify that when only plain text part exists with 'Mã xác thực: 951357', it is successfully extracted."""
        plain_text = "Xin chào bạn,\nMã xác thực: 951357\nHiệu lực trong 5 phút."
        b64 = base64.urlsafe_b64encode(plain_text.encode("utf-8")).decode("ascii")

        payload = {
            "snippet": "Xin chào bạn, Mã xác thực...",
            "payload": {
                "headers": [{"name": "Subject", "value": "Smart Home Voice - Mã xác thực tài khoản"}],
                "parts": [{"mimeType": "text/plain", "body": {"data": b64}}],
            },
        }

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "messages" in cmd and "get" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps(payload), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            res = auth_mgr.read_latest_otp_from_gmail_inbox(message_id="msg-plain-keyword")
            assert res.get("ok") is True
            assert res.get("extracted_otp") == "951357"



# ==============================================================================
# SECTION 5: ZERO-LEAK SECURITY AUDIT
# ==============================================================================

class TestZeroLeakSecurityAudit:
    """Audit for Zero-Leak guarantee: no secrets leaked in logs, returns, or traces."""

    def test_zero_leak_smtp_secrets_in_responses_and_audit_logs(
        self, auth_mgr: ChallengerTestAuthManager
    ):
        """Verify that GMAIL_APP_PASSWORD and SMTP_PASSWORD values are never leaked in response dicts or audit logs."""
        super_secret_password = "super_secret_smtp_token_xyz999"

        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": super_secret_password}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            res = auth_mgr.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="529103",
                display_name="Senat User",
            )
            assert res.get("sent_real_gmail") is True

            # 1. Secret cannot appear in response dict
            res_str = json.dumps(res)
            assert super_secret_password not in res_str, f"Secret leaked in return dict: {res}"

            # 2. Secret cannot appear in audit logs
            for log in auth_mgr.audit_logs:
                log_str = json.dumps(log, default=str)
                assert super_secret_password not in log_str, f"Secret leaked in audit log: {log}"

    def test_zero_leak_error_reporting_when_secret_absent(
        self, auth_mgr: ChallengerTestAuthManager
    ):
        """Verify that when secrets are absent, the system identifies the missing variable name without leaking memory."""
        env_without_secrets = {
            k: v for k, v in os.environ.items()
            if k not in ("GMAIL_APP_PASSWORD", "SMTP_PASSWORD")
        }

        with patch.dict(os.environ, env_without_secrets, clear=True), \
             patch("subprocess.run", side_effect=FileNotFoundError("gws command not found")):

            res = auth_mgr.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="529103",
                display_name="Senat User",
            )
            assert res.get("sent_real_gmail") is False
            assert res.get("missing_secret") == "GMAIL_APP_PASSWORD"
            assert "GMAIL_APP_PASSWORD" in res.get("error", "")
