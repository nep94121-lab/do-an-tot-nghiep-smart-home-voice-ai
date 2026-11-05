"""Bộ Kiểm Thử TDD: Milestone M3 — Yêu Cầu R3 (RFC 5322 Standards & Deliverability).

Kiểm định toàn diện:
1. RFC 5322 Email Headers:
   - From formatted via email.utils.formataddr(('Smart Home Voice AI', sender_addr))
   - To formatted via email.utils.formataddr(...)
   - Date header present and compliant with RFC 5322 / RFC 2822
   - Message-ID header present and compliant (RFC 5322 §3.6.4)
   - Reply-To header formatted via email.utils.formataddr(('Smart Home Voice AI', sender_addr))
2. Clean Subject Lines:
   - For OTP: strictly Title Case 'Smart Home Voice - Mã xác thực tài khoản'
   - Strictly NO OTP 6 digits in Subject
   - Strictly NO ALL-CAPS words (e.g. 'OTP', 'AI', 'OAUTH')
   - Strictly zero emojis
   - For Invite: 'Smart Home Voice - Lời mời đăng ký tài khoản Cấp ...' (no emojis, no ALL-CAPS)
3. MIME Multipart Alternative:
   - First part: text/plain; charset=utf-8 (clean, zero emojis)
   - Second part: text/html; charset=utf-8 (light background #ffffff / #f8fafc, zero emojis, no deceptive Google OAuth)
4. Resilient Gmail Inbox Scraper (`read_latest_otp_from_gmail_inbox`):
   - Query 'q' updated to 'subject:"Smart Home" (xác thực OR OTP OR verification)'
   - Base64URL recursive part decoding for nested MIME payloads
   - 3-tier OTP regex extraction (keyword context, HTML container id="otp-code-value", boundary fallback)
"""

from __future__ import annotations

import base64
import email.utils
import json
import os
import re
from unittest.mock import MagicMock, patch

import pytest

from simulator.auth.invite_and_gmail_mixin import AuthInviteGmailMixin


class DummyAuthManager(AuthInviteGmailMixin):
    """Test harness dummy inheriting AuthInviteGmailMixin with minimal required state."""

    def __init__(self):
        self.invite_links = {
            "INV-TEST-T2": {
                "invite_code": "INV-TEST-T2",
                "issuer_email": "senat6031@gmail.com",
                "issuer_name": "Nguyễn Tuấn Anh",
                "issuer_tier": 1,
                "target_tier": 2,
                "target_role_label": "Thành viên Thường",
                "url_path": "/auth?invite=INV-TEST-T2",
                "full_url": "http://localhost:8088/auth?invite=INV-TEST-T2",
            }
        }
        self.audit_logs = []

    def _log_event(self, **kwargs):
        self.audit_logs.append(kwargs)

    def _save_invite_links(self):
        pass


@pytest.fixture
def auth_mgr() -> DummyAuthManager:
    return DummyAuthManager()


class TestRFC5322HeadersAndFormatting:
    """Kiểm tra tuân thủ RFC 5322 và chuẩn hóa Email Headers."""

    def test_send_real_gmail_otp_headers_rfc5322(self, auth_mgr: DummyAuthManager):
        """Kiểm tra RFC 5322 headers của send_real_gmail_otp."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "fake-app-password-test", "SMTP_USER": "nep94121@gmail.com"}), \
             patch("smtplib.SMTP", return_value=mock_smtp), \
             patch("smtplib.SMTP_SSL", return_value=mock_smtp):
            
            res = auth_mgr.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="849201",
                display_name="Senat Test",
            )
            assert res.get("sent_real_gmail") is True

            # Lấy đối tượng MIME message được gửi
            assert mock_smtp.send_message.called, "server.send_message() chưa được gọi!"
            msg = mock_smtp.send_message.call_args[0][0]

            # 1. From header: "Smart Home Voice AI" <nep94121@gmail.com>
            from_hdr = msg["From"]
            real_name, addr = email.utils.parseaddr(from_hdr)
            assert real_name == "Smart Home Voice AI", f"From display name không đúng: '{real_name}'"
            assert addr == "nep94121@gmail.com", f"From address không đúng: '{addr}'"

            # 2. To header: formatted with display name
            to_hdr = msg["To"]
            to_name, to_addr = email.utils.parseaddr(to_hdr)
            assert to_addr == "senat6031@gmail.com"
            assert to_name == "Senat Test"

            # 3. Date header: RFC 5322 formatted
            date_hdr = msg["Date"]
            assert date_hdr is not None, "Thiếu trường Date header (RFC 5322 §3.6.1)!"
            parsed_date = email.utils.parsedate_to_datetime(date_hdr)
            assert parsed_date is not None, f"Date header không đúng chuẩn RFC 2822/5322: '{date_hdr}'"

            # 4. Message-ID header: <id@domain>
            msg_id_hdr = msg["Message-ID"]
            assert msg_id_hdr is not None, "Thiếu trường Message-ID header (RFC 5322 §3.6.4)!"
            assert msg_id_hdr.startswith("<") and msg_id_hdr.endswith(">"), f"Message-ID không hợp lệ: '{msg_id_hdr}'"
            assert "@" in msg_id_hdr, f"Message-ID thiếu @domain: '{msg_id_hdr}'"

            # 5. Reply-To header: "Smart Home Voice AI" <nep94121@gmail.com>
            reply_to = msg["Reply-To"]
            assert reply_to is not None, "Thiếu Reply-To header!"
            r_name, r_addr = email.utils.parseaddr(reply_to)
            assert r_name == "Smart Home Voice AI"
            assert r_addr == "nep94121@gmail.com"

    def test_send_invite_link_headers_rfc5322(self, auth_mgr: DummyAuthManager):
        """Kiểm tra RFC 5322 headers của send_invite_link_via_gmail."""
        captured_messages = []

        def fake_subprocess_run(cmd, *args, **kwargs):
            if cmd and cmd[0] == "gws" and "send" in cmd:
                # Trích xuất raw message từ --json
                for i, arg in enumerate(cmd):
                    if arg == "--json" and i + 1 < len(cmd):
                        payload_data = json.loads(cmd[i + 1])
                        raw_bytes = base64.urlsafe_b64decode(payload_data["raw"])
                        import email
                        captured_messages.append(email.message_from_bytes(raw_bytes))
                return MagicMock(returncode=0, stdout='{"id": "msg-invite-12345"}', stderr="")
            return MagicMock(returncode=1, stdout="", stderr="command not found")

        with patch.dict(os.environ, {"SMTP_USER": "nep94121@gmail.com"}), \
             patch("subprocess.run", side_effect=fake_subprocess_run):
            
            res = auth_mgr.send_invite_link_via_gmail(
                invite_code="INV-TEST-T2",
                recipient_email="senat6031@gmail.com",
            )
            assert res.get("ok") is True
            assert res.get("sent_real_gmail") is True
            assert len(captured_messages) == 1

            msg = captured_messages[0]

            # 1. From header: "Smart Home Voice AI" <nep94121@gmail.com>
            real_name, addr = email.utils.parseaddr(msg["From"])
            assert real_name == "Smart Home Voice AI"
            assert addr == "nep94121@gmail.com"

            # 2. To header: formatted address
            _, to_addr = email.utils.parseaddr(msg["To"])
            assert to_addr == "senat6031@gmail.com"

            # 3. Date header: RFC 5322
            date_hdr = msg["Date"]
            assert date_hdr is not None
            assert email.utils.parsedate_to_datetime(date_hdr) is not None

            # 4. Message-ID header: <id@domain>
            msg_id = msg["Message-ID"]
            assert msg_id is not None and msg_id.startswith("<") and msg_id.endswith(">")

            # 5. Reply-To header
            assert msg["Reply-To"] is not None


class TestSubjectLinesAntiSpam:
    """Kiểm định tiêu đề thư (Subject) chống spam: Không chứa OTP, không ALL-CAPS, không emoji."""

    def test_otp_subject_has_no_digits_no_all_caps_no_emojis(self, auth_mgr: DummyAuthManager):
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "fake-app-password-test"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):
            
            auth_mgr.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="931052",
                display_name="Senat User",
            )
            msg = mock_smtp.send_message.call_args[0][0]
            subject = msg["Subject"]

            # Bắt buộc: "Smart Home Voice - Mã xác thực tài khoản"
            assert "931052" not in subject, f"Subject chứa mã OTP: '{subject}'"
            assert not re.search(r"\b\d{6}\b", subject), f"Subject chứa chuỗi số 6 chữ số: '{subject}'"

            # Không có từ ALL-CAPS (như OTP, AI, OAUTH)
            all_caps_words = re.findall(r"\b[A-Z]{2,}\b", subject)
            assert not all_caps_words, f"Subject chứa từ viết hoa toàn bộ: {all_caps_words} in '{subject}'"

            # Không có emoji
            assert not re.search(r"[\U00010000-\U0010ffff]", subject), f"Subject chứa emoji: '{subject}'"

            # Khớp tiêu đề chuẩn
            assert subject == "Smart Home Voice - Mã xác thực tài khoản"

    def test_invite_subject_has_no_all_caps_no_emojis(self, auth_mgr: DummyAuthManager):
        captured_messages = []

        def fake_subprocess_run(cmd, *args, **kwargs):
            if cmd and cmd[0] == "gws":
                for i, arg in enumerate(cmd):
                    if arg == "--json" and i + 1 < len(cmd):
                        payload_data = json.loads(cmd[i + 1])
                        raw_bytes = base64.urlsafe_b64decode(payload_data["raw"])
                        import email
                        captured_messages.append(email.message_from_bytes(raw_bytes))
                return MagicMock(returncode=0, stdout='{"id": "msg-inv-test"}', stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch.dict(os.environ, {"SMTP_USER": "nep94121@gmail.com"}), \
             patch("subprocess.run", side_effect=fake_subprocess_run):
            
            auth_mgr.send_invite_link_via_gmail(
                invite_code="INV-TEST-T2",
                recipient_email="senat6031@gmail.com",
            )
            assert len(captured_messages) == 1
            subject = captured_messages[0]["Subject"]

            # Không chứa từ ALL-CAPS (như AI, OAUTH, SMART)
            all_caps_words = re.findall(r"\b[A-Z]{2,}\b", subject)
            assert not all_caps_words, f"Invite subject chứa từ ALL-CAPS: {all_caps_words} in '{subject}'"

            # Không có emoji (như 🔗, 🏷️)
            assert not re.search(r"[\U00010000-\U0010ffff]", subject), f"Invite subject chứa emoji: '{subject}'"


class TestMultipartAlternativeStructure:
    """Kiểm tra cấu trúc MIME Multipart Alternative (text/plain + text/html, zero emojis, light background)."""

    def test_otp_email_multipart_structure_and_styling(self, auth_mgr: DummyAuthManager):
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "fake-app-password-test"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):
            
            auth_mgr.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="582194",
                display_name="Senat User",
            )
            msg = mock_smtp.send_message.call_args[0][0]

            assert msg.is_multipart(), "Thư phải là MIME multipart!"
            assert msg.get_content_type() == "multipart/alternative", "Content-Type phải là multipart/alternative"

            parts = msg.get_payload()
            assert len(parts) >= 2, f"Thư phải có ít nhất 2 part (plain text và HTML), hiện có {len(parts)}"

            # Part 1: text/plain
            part_plain = parts[0]
            assert part_plain.get_content_type() == "text/plain", f"Part 1 phải là text/plain, nhưng là {part_plain.get_content_type()}"
            plain_body = part_plain.get_payload(decode=True).decode("utf-8")
            assert "582194" in plain_body, "Part plain text phải chứa mã OTP!"
            assert not re.search(r"[\U00010000-\U0010ffff]", plain_body), f"Part plain text chứa emoji: {plain_body}"

            # Part 2: text/html
            part_html = parts[1]
            assert part_html.get_content_type() == "text/html", f"Part 2 phải là text/html, nhưng là {part_html.get_content_type()}"
            html_body = part_html.get_payload(decode=True).decode("utf-8")
            assert "582194" in html_body, "Part HTML phải chứa mã OTP!"
            assert not re.search(r"[\U00010000-\U0010ffff]", html_body), f"Part HTML chứa emoji: {html_body}"

            # Check: Không có thương hiệu Google OAuth giả mạo
            assert "Google OAuth" not in html_body, "HTML chứa thương hiệu lừa đảo 'Google OAuth'!"
            assert "XÁC NHẬN GOOGLE OAUTH" not in html_body

            # Check: Giao diện nền sáng (#ffffff hoặc #f8fafc), không dùng nền tối đen #0f172a làm nền chính
            assert "#f8fafc" in html_body or "#ffffff" in html_body, "HTML body không dùng tông nền sáng!"
            assert '<body style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;margin:0;padding:24px;background-color:#f8fafc;color:#1e293b;">' in html_body or "background-color:#f8fafc" in html_body or "background:#f8fafc" in html_body or "background-color:#ffffff" in html_body

            # Check: Có container chứa OTP với id="otp-code-value"
            assert 'id="otp-code-value"' in html_body


class TestResilientGmailInboxScraper:
    """Kiểm tra hàm cào hộp thư read_latest_otp_from_gmail_inbox với query q mới, Base64URL decoding, 3-tier regex."""

    def test_scraper_query_matches_new_subject_format(self, auth_mgr: DummyAuthManager):
        """Query q phải bao quát: 'subject:\"Smart Home\" (xác thực OR OTP OR verification)'."""
        captured_cmd = []

        def fake_subprocess_run(cmd, *args, **kwargs):
            captured_cmd.append(cmd)
            # Giả lập trả về message_id
            if "messages" in cmd and "list" in cmd:
                return MagicMock(returncode=0, stdout='{"messages": [{"id": "msg-new-001"}]}', stderr="")
            if "messages" in cmd and "get" in cmd:
                # Trả về message với HTML payload mã hóa base64url
                html_snippet = '<div id="otp-code-value">491823</div>'
                b64_html = base64.urlsafe_b64encode(html_snippet.encode("utf-8")).decode("ascii")
                payload_obj = {
                    "snippet": "Mã xác thực của bạn là: 491823",
                    "payload": {
                        "headers": [{"name": "Subject", "value": "Smart Home Voice - Mã xác thực tài khoản"}],
                        "parts": [
                            {"mimeType": "text/html", "body": {"data": b64_html}},
                        ],
                    },
                }
                return MagicMock(returncode=0, stdout=json.dumps(payload_obj), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            res = auth_mgr.read_latest_otp_from_gmail_inbox()
            assert res.get("ok") is True
            assert res.get("extracted_otp") == "491823"

            # Kiểm tra query q
            list_cmd = captured_cmd[0]
            params_idx = list_cmd.index("--params") + 1
            params = json.loads(list_cmd[params_idx])
            q_str = params.get("q", "")
            assert 'subject:"Smart Home"' in q_str
            assert "xác thực" in q_str

    def test_scraper_decodes_nested_multipart_payload(self, auth_mgr: DummyAuthManager):
        """Trích xuất mã OTP thành công ngay cả khi snippet bị rỗng hoặc không chứa mã, mã nằm sâu trong part Base64URL."""
        def fake_subprocess_run(cmd, *args, **kwargs):
            if "messages" in cmd and "get" in cmd:
                # Snippet không có mã OTP, Subject không có mã OTP
                plain_text = "Xin chào người dùng,\nMã xác thực tài khoản của bạn: 735109\nHiệu lực 5 phút."
                b64_plain = base64.urlsafe_b64encode(plain_text.encode("utf-8")).decode("ascii")

                html_text = '<html><body><div>Mã của bạn: <span id="otp-code-value">735109</span></div></body></html>'
                b64_html = base64.urlsafe_b64encode(html_text.encode("utf-8")).decode("ascii")

                msg_obj = {
                    "snippet": "Xin chào người dùng, Hệ thống Smart Home Voice...",
                    "payload": {
                        "headers": [{"name": "Subject", "value": "Smart Home Voice - Mã xác thực tài khoản"}],
                        "parts": [
                            {
                                "mimeType": "multipart/alternative",
                                "parts": [
                                    {"mimeType": "text/plain", "body": {"data": b64_plain}},
                                    {"mimeType": "text/html", "body": {"data": b64_html}},
                                ],
                            }
                        ],
                    },
                }
                return MagicMock(returncode=0, stdout=json.dumps(msg_obj), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            res = auth_mgr.read_latest_otp_from_gmail_inbox(message_id="msg-nested-999")
            assert res.get("ok") is True, f"Trích xuất thất bại: {res}"
            assert res.get("extracted_otp") == "735109"

    def test_scraper_3tier_regex_precedence(self, auth_mgr: DummyAuthManager):
        """Kiểm tra độ ưu tiên 3 tầng của Regex trích xuất OTP."""
        # Tier 1: keyword context ưu tiên hơn số ngẫu nhiên khác
        def fake_subprocess_run(cmd, *args, **kwargs):
            if "messages" in cmd and "get" in cmd:
                # Có năm 2026 và số hiệu khác 123456, nhưng context 'Mã xác thực: 881290'
                text = "Hệ thống năm 2026 phiên bản 999999. Mã xác thực: 881290. Cảm ơn."
                b64 = base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")
                msg_obj = {
                    "snippet": "Hệ thống năm 2026...",
                    "payload": {
                        "headers": [{"name": "Subject", "value": "Smart Home Voice - Mã xác thực tài khoản"}],
                        "parts": [{"mimeType": "text/plain", "body": {"data": b64}}],
                    },
                }
                return MagicMock(returncode=0, stdout=json.dumps(msg_obj), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            res = auth_mgr.read_latest_otp_from_gmail_inbox(message_id="msg-tier1")
            assert res.get("ok") is True
            assert res.get("extracted_otp") == "881290"
