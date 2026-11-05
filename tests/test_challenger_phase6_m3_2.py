"""Bộ Kiểm Định Thực Nghiệm Đối Kháng Độc Lập (Challenger M3-2).

Milestone 3: R3 — Email RFC 5322 Standards & Deliverability.

Kiểm thử đối kháng chuyên sâu:
1. RFC 5322 Strict Formatting & Headers (Date RFC 5322, Message-ID, formataddr From/To/Reply-To, RFC 2047 encoding).
2. SpamAssassin Heuristics (NO ALL_CAPS, NO digits in OTP Subject, ZERO emojis, text/HTML ratio, NO phishing keywords).
3. Resilient Inbox Scraper Edge Cases (7-digit neighbors, multiple 6-digit numbers, id="otp-code-value", Base64URL padding, corrupted data).
4. Security & Zero-Leak (0 SMTP credentials/passwords leaked into headers, bodies, or logs).
"""

from __future__ import annotations

import base64
import email
import email.header
import email.utils
import json
import os
import re
from unittest.mock import MagicMock, patch

import pytest

from simulator.auth.invite_and_gmail_mixin import AuthInviteGmailMixin


class ChallengerM3Dummy(AuthInviteGmailMixin):
    """Test harness dummy inheriting AuthInviteGmailMixin."""

    def __init__(self):
        self.invite_links = {
            "INV-CHALLENGER-T2": {
                "invite_code": "INV-CHALLENGER-T2",
                "issuer_email": "senat6031@gmail.com",
                "issuer_name": "Nguyễn Tuấn Anh",
                "issuer_tier": 1,
                "target_tier": 2,
                "target_role_label": "Thành viên Thường",
                "url_path": "/auth?invite=INV-CHALLENGER-T2",
                "full_url": "http://localhost:8088/auth?invite=INV-CHALLENGER-T2",
            },
            "INV-CHALLENGER-T3": {
                "invite_code": "INV-CHALLENGER-T3",
                "issuer_email": "nep94121@gmail.com",
                "issuer_name": "Trần Văn Chủ",
                "issuer_tier": 1,
                "target_tier": 3,
                "target_role_label": "Khách Vãng Lai",
                "url_path": "/auth?invite=INV-CHALLENGER-T3",
                "full_url": "http://localhost:8088/auth?invite=INV-CHALLENGER-T3",
            },
        }
        self.audit_logs: list[dict] = []

    def _log_event(self, **kwargs):
        self.audit_logs.append(kwargs)

    def _save_invite_links(self):
        pass


@pytest.fixture
def challenger_dummy() -> ChallengerM3Dummy:
    return ChallengerM3Dummy()


class TestRFC5322StrictAdversarial:
    """Kiểm tra đối kháng nghiêm ngặt chuẩn RFC 5322 về Headers."""

    def test_rfc5322_date_format_and_parsing(self, challenger_dummy: ChallengerM3Dummy):
        """Date header phải tuân thủ RFC 2822/5322 và phân tích được bằng email.utils.parsedate_to_datetime."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "adversarial-pass", "SMTP_USER": "senat6031@gmail.com"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            res = challenger_dummy.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="629148",
                display_name="Senat Tester",
            )
            assert res.get("sent_real_gmail") is True

            msg = mock_smtp.send_message.call_args[0][0]
            date_str = msg["Date"]
            assert date_str is not None, "Date header bị thiếu!"

            # Kiểm tra phân tích ngày giờ qua parsedate_to_datetime
            dt = email.utils.parsedate_to_datetime(date_str)
            assert dt is not None, f"Không thể parse Date header '{date_str}'!"
            assert dt.tzinfo is not None, f"Date header thiếu timezone info: '{date_str}'"

            # Kiểm tra định dạng chuỗi theo regex RFC 2822
            rfc2822_date_pattern = r"^(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+)?\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s+\d{2}:\d{2}:\d{2}\s+[+-]\d{4}$"
            assert re.match(rfc2822_date_pattern, date_str), f"Date header không khớp RFC 2822 pattern: '{date_str}'"

    def test_message_id_strict_angle_brackets_and_domain(self, challenger_dummy: ChallengerM3Dummy):
        """Message-ID header phải nằm trong cặp ngoặc nhọn <id@domain> và đúng domain."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "adversarial-pass", "SMTP_USER": "nep94121@gmail.com"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            challenger_dummy.send_real_gmail_otp(
                target_email="nep94121@gmail.com",
                otp_code="184920",
                display_name="Nep Owner",
            )
            msg = mock_smtp.send_message.call_args[0][0]
            msg_id = msg["Message-ID"]

            assert msg_id is not None
            # Regex chuẩn RFC 5322 Message-ID
            msg_id_regex = r"^<[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}>$"
            assert re.match(msg_id_regex, msg_id), f"Message-ID '{msg_id}' không hợp lệ theo regex chuẩn!"
            assert msg_id.endswith("@gmail.com>"), f"Domain trong Message-ID phải khớp sender domain: '{msg_id}'"

    def test_message_id_uniqueness_back_to_back(self, challenger_dummy: ChallengerM3Dummy):
        """Tạo liên tiếp 30 tin nhắn phải sinh ra 30 Message-ID hoàn toàn duy nhất (chống trùng lặp)."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        msg_ids: set[str] = set()
        count = 30

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "adversarial-pass", "SMTP_USER": "senat6031@gmail.com"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            for i in range(count):
                challenger_dummy.send_real_gmail_otp(
                    target_email="senat6031@gmail.com",
                    otp_code=f"{100000 + i}",
                    display_name=f"User {i}",
                )
                msg = mock_smtp.send_message.call_args[0][0]
                msg_ids.add(msg["Message-ID"])

        assert len(msg_ids) == count, f"Message-ID bị trùng lặp! Sinh {count} nhưng chỉ có {len(msg_ids)} giá trị duy nhất."

    def test_from_and_reply_to_formataddr_integrity(self, challenger_dummy: ChallengerM3Dummy):
        """From và Reply-To phải được format qua email.utils.formataddr với tên hiển thị đầy đủ."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "adversarial-pass", "SMTP_USER": "nep94121@gmail.com"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            challenger_dummy.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="392817",
                display_name="Senat Verify",
            )
            msg = mock_smtp.send_message.call_args[0][0]

            for header_name in ["From", "Reply-To"]:
                val = msg[header_name]
                assert val is not None, f"Thiếu {header_name} header!"
                realname, email_addr = email.utils.parseaddr(val)
                assert realname == "Smart Home Voice AI", f"{header_name} display name sai: '{realname}'"
                assert email_addr == "nep94121@gmail.com", f"{header_name} address sai: '{email_addr}'"
                assert "<nep94121@gmail.com>" in val

    def test_vietnamese_accented_display_name_rfc2047(self, challenger_dummy: ChallengerM3Dummy):
        """Display name tiếng Việt có dấu phải được mã hóa RFC 2047 và phân tích chính xác qua parseaddr/decode_header."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "adversarial-pass", "SMTP_USER": "senat6031@gmail.com"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            challenger_dummy.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="889900",
                display_name="Nguyễn Tuấn Anh",
            )
            msg = mock_smtp.send_message.call_args[0][0]
            to_hdr = msg["To"]
            raw_name, addr = email.utils.parseaddr(to_hdr)
            assert addr == "senat6031@gmail.com"

            # Giải mã RFC 2047 encoded-word
            decoded_parts = email.header.decode_header(raw_name)
            decoded_name = "".join(
                b.decode(enc or "utf-8") if isinstance(b, bytes) else str(b)
                for b, enc in decoded_parts
            )
            assert decoded_name == "Nguyễn Tuấn Anh", f"Tên hiển thị tiếng Việt bị lỗi mã hóa: '{decoded_name}'"

    def test_send_invite_link_rfc5322_comprehensive(self, challenger_dummy: ChallengerM3Dummy):
        """send_invite_link_via_gmail phải tuân thủ toàn diện RFC 5322 và deliverability."""
        captured_messages = []

        def fake_subprocess_run(cmd, *args, **kwargs):
            if cmd and cmd[0] == "gws" and "send" in cmd:
                for i, arg in enumerate(cmd):
                    if arg == "--json" and i + 1 < len(cmd):
                        payload_data = json.loads(cmd[i + 1])
                        raw_bytes = base64.urlsafe_b64decode(payload_data["raw"])
                        captured_messages.append(email.message_from_bytes(raw_bytes))
                return MagicMock(returncode=0, stdout='{"id": "msg-inv-full-rfc"}', stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch.dict(os.environ, {"SMTP_USER": "nep94121@gmail.com"}), \
             patch("subprocess.run", side_effect=fake_subprocess_run):

            res = challenger_dummy.send_invite_link_via_gmail(
                invite_code="INV-CHALLENGER-T2",
                recipient_email="senat6031@gmail.com",
            )
            assert res.get("ok") is True
            assert res.get("sent_real_gmail") is True
            assert len(captured_messages) == 1

            msg = captured_messages[0]

            # 1. Date header RFC 5322
            dt = email.utils.parsedate_to_datetime(msg["Date"])
            assert dt is not None and dt.tzinfo is not None

            # 2. Message-ID RFC 5322
            msg_id = msg["Message-ID"]
            assert re.match(r"^<[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}>$", msg_id)
            assert msg_id.endswith("@gmail.com>")

            # 3. From & Reply-To
            for h in ["From", "Reply-To"]:
                rname, raddr = email.utils.parseaddr(msg[h])
                assert rname == "Smart Home Voice AI"
                assert raddr == "nep94121@gmail.com"

            # 4. Subject: no ALL_CAPS, no emojis
            subj = msg["Subject"]
            assert not re.search(r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf]", subj)
            all_caps = re.findall(r"\b[A-Z]{2,}\b", subj)
            assert not all_caps, f"Invite subject chứa ALL-CAPS: {all_caps} in '{subj}'"

            # 5. Multipart Alternative & zero emojis in body
            assert msg.is_multipart()
            parts = msg.get_payload()
            assert len(parts) >= 2
            plain = parts[0].get_payload(decode=True).decode("utf-8")
            html = parts[1].get_payload(decode=True).decode("utf-8")

            emoji_regex = r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf]"
            assert not re.search(emoji_regex, plain)
            assert not re.search(emoji_regex, html)
            assert "INV-CHALLENGER-T2" in plain
            assert "INV-CHALLENGER-T2" in html


class TestSpamAssassinHeuristicsAdversarial:
    """Kiểm tra đối kháng các tiêu chuẩn chống lọc thư rác (SpamAssassin-like heuristics)."""

    def test_otp_subject_no_all_caps_no_digits_no_emojis(self, challenger_dummy: ChallengerM3Dummy):
        """Subject của email OTP: Không ALL-CAPS, không bất kỳ chữ số nào, không emoji."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "adversarial-pass", "SMTP_USER": "senat6031@gmail.com"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            challenger_dummy.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="982341",
                display_name="Test User",
            )
            msg = mock_smtp.send_message.call_args[0][0]
            subject = msg["Subject"]

            # 1. Tuyệt đối không chứa số
            assert not re.search(r"\d", subject), f"Subject chứa chữ số: '{subject}'"

            # 2. Tuyệt đối không chứa từ ALL-CAPS (như OTP, AI, OAUTH, SMART)
            all_caps = re.findall(r"\b[A-Z]{2,}\b", subject)
            assert not all_caps, f"Subject chứa từ ALL-CAPS: {all_caps} in '{subject}'"

            # 3. Tuyệt đối không chứa emoji
            emoji_regex = r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf]"
            assert not re.search(emoji_regex, subject), f"Subject chứa emoji: '{subject}'"

            # 4. Tiêu đề chuẩn Title Case không dấu hiệu spam
            assert subject == "Smart Home Voice - Mã xác thực tài khoản"

    def test_zero_emojis_across_entire_email_plain_and_html(self, challenger_dummy: ChallengerM3Dummy):
        """Toàn bộ nội dung email (Subject, Plain text, HTML) tuyệt đối không có emoji nào."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        test_cases = [
            {"otp_code": "112233", "display_name": "User Normal", "issued_password": "", "invite_info": None},
            {"otp_code": "445566", "display_name": "User Pass", "issued_password": "NewSecretPass123@", "invite_info": None},
            {"otp_code": "778899", "display_name": "User Invite", "issued_password": "InvitePass!#$", "invite_info": {"issuer_name": "Chủ Nhà", "target_tier": 2}},
        ]

        emoji_pattern = re.compile(r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf]")

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "adversarial-pass", "SMTP_USER": "senat6031@gmail.com"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            for tc in test_cases:
                challenger_dummy.send_real_gmail_otp(
                    target_email="senat6031@gmail.com",
                    otp_code=tc["otp_code"],
                    display_name=tc["display_name"],
                    issued_password=tc["issued_password"],
                    invite_info=tc["invite_info"],
                )
                msg = mock_smtp.send_message.call_args[0][0]

                # Check Subject
                assert not emoji_pattern.search(msg["Subject"]), f"Subject chứa emoji: {msg['Subject']}"

                # Check Parts
                parts = msg.get_payload()
                for p in parts:
                    content = p.get_payload(decode=True).decode("utf-8")
                    found = emoji_pattern.findall(content)
                    assert not found, f"Phát hiện emoji trong {p.get_content_type()}: {found}"

    def test_ratio_of_plain_text_to_html_content(self, challenger_dummy: ChallengerM3Dummy):
        """Tỷ lệ plain text so với HTML content phải đạt chuẩn chống SpamAssassin MIME_HTML_ONLY / RATIO_TEXT_HTML_LOW."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "adversarial-pass", "SMTP_USER": "senat6031@gmail.com"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            challenger_dummy.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="528104",
                display_name="Senat Ratio",
            )
            msg = mock_smtp.send_message.call_args[0][0]
            parts = msg.get_payload()

            assert len(parts) == 2, f"Phải có đúng 2 parts (plain và html), nhận được {len(parts)}"
            part_plain, part_html = parts[0], parts[1]

            plain_body = part_plain.get_payload(decode=True).decode("utf-8")
            html_body = part_html.get_payload(decode=True).decode("utf-8")

            # 1. Plain text phải có nội dung đầy đủ (ít nhất 100 ký tự)
            assert len(plain_body.strip()) >= 100, f"Plain text quá ngắn ({len(plain_body)} chars) -> nguy cơ bị SpamAssassin đánh điểm thấp"

            # 2. Tỷ lệ độ dài plain / html không được quá bé (phải > 0.08)
            ratio = len(plain_body) / len(html_body)
            assert ratio >= 0.08, f"Tỷ lệ Plain/HTML quá thấp ({ratio:.3f})!"

            # 3. Plain text phải chứa đầy đủ thông tin cốt lõi
            assert "528104" in plain_body
            assert "Smart Home Voice" in plain_body
            assert "5 phút" in plain_body

    def test_absence_of_deceptive_phishing_keywords(self, challenger_dummy: ChallengerM3Dummy):
        """Tuyệt đối không chứa các từ khóa giả mạo nhãn hiệu lừa đảo như 'Google OAuth', 'Tài khoản Google'."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "adversarial-pass", "SMTP_USER": "senat6031@gmail.com"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            challenger_dummy.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="384912",
                display_name="Phishing Check",
            )
            msg = mock_smtp.send_message.call_args[0][0]
            raw_email_str = msg.as_string()

            phishing_blacklist = [
                "Google OAuth",
                "GOOGLE OAUTH",
                "Google Security",
                "Tài khoản Google",
                "Google Account",
                "Xác nhận Google",
            ]
            for kw in phishing_blacklist:
                assert kw.lower() not in raw_email_str.lower(), f"Phát hiện từ khóa lừa đảo/mạo danh '{kw}' trong email!"

    def test_html_light_background_and_semantic_structure(self, challenger_dummy: ChallengerM3Dummy):
        """Giao diện HTML phải có nền sáng (#ffffff / #f8fafc), semantic table layout, doctype chuẩn."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "adversarial-pass", "SMTP_USER": "senat6031@gmail.com"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            challenger_dummy.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="749281",
                display_name="UI Inspector",
            )
            msg = mock_smtp.send_message.call_args[0][0]
            html_body = msg.get_payload()[1].get_payload(decode=True).decode("utf-8")

            # Check Doctype & Meta
            assert "<!DOCTYPE html>" in html_body
            assert '<meta charset="utf-8">' in html_body

            # Check Light Background
            assert "background-color:#f8fafc" in html_body or "background-color:#ffffff" in html_body
            assert '<body style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;margin:0;padding:24px;background-color:#f8fafc;' in html_body

            # Thẻ hiển thị mã OTP có id chuẩn
            assert '<div id="otp-code-value"' in html_body
            assert "749281</div>" in html_body


class TestInboxScraperAdversarialEdgeCases:
    """Kiểm tra hàm cào hộp thư read_latest_otp_from_gmail_inbox với các trường hợp biên đối kháng."""

    def test_edge_case_7_digit_and_phone_numbers_nearby(self, challenger_dummy: ChallengerM3Dummy):
        """Trường hợp biên: Có số điện thoại 10 số (0912345678) hoặc mã đơn 7 số (1234567) nằm sát mã OTP."""
        def fake_subprocess_run(cmd, *args, **kwargs):
            if "messages" in cmd and "get" in cmd:
                body_text = """
                Kính gửi khách hàng có số điện thoại: 0987654321
                Mã vận đơn bưu chính: 7654321
                Mã xác thực tài khoản Smart Home Voice của bạn: 839201
                Nếu cần trợ giúp hãy gọi tổng đài 190056789.
                """
                b64 = base64.urlsafe_b64encode(body_text.encode("utf-8")).decode("ascii")
                msg_obj = {
                    "snippet": "Kính gửi khách hàng có số điện thoại: 0987654321...",
                    "payload": {
                        "headers": [{"name": "Subject", "value": "Smart Home Voice - Mã xác thực tài khoản"}],
                        "parts": [{"mimeType": "text/plain", "body": {"data": b64}}],
                    },
                }
                return MagicMock(returncode=0, stdout=json.dumps(msg_obj), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            res = challenger_dummy.read_latest_otp_from_gmail_inbox(message_id="msg-phone-edge")
            assert res.get("ok") is True
            assert res.get("extracted_otp") == "839201"

    def test_edge_case_multiple_6_digit_numbers_context_precedence(self, challenger_dummy: ChallengerM3Dummy):
        """Trường hợp biên: Xuất hiện nhiều số 6 chữ số (mã bưu điện 100000, năm tháng 202611), regex keyword context phải thắng."""
        def fake_subprocess_run(cmd, *args, **kwargs):
            if "messages" in cmd and "get" in cmd:
                body_text = """
                Báo cáo lưu trữ số 999111 ngày phát hành 202611.
                Mã bưu cục Hà Nội: 100000.
                Mã OTP xác nhận: 456789
                Cảm ơn quý khách.
                """
                b64 = base64.urlsafe_b64encode(body_text.encode("utf-8")).decode("ascii")
                msg_obj = {
                    "snippet": "Báo cáo lưu trữ số 999111...",
                    "payload": {
                        "headers": [{"name": "Subject", "value": "Smart Home Voice - Mã xác thực tài khoản"}],
                        "parts": [{"mimeType": "text/plain", "body": {"data": b64}}],
                    },
                }
                return MagicMock(returncode=0, stdout=json.dumps(msg_obj), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            res = challenger_dummy.read_latest_otp_from_gmail_inbox(message_id="msg-multi-6digit")
            assert res.get("ok") is True
            assert res.get("extracted_otp") == "456789"

    def test_edge_case_html_container_otp_code_value_fallback(self, challenger_dummy: ChallengerM3Dummy):
        """Trường hợp biên: Trong plain text không có keyword rõ, nhưng trong HTML có thẻ id='otp-code-value'."""
        def fake_subprocess_run(cmd, *args, **kwargs):
            if "messages" in cmd and "get" in cmd:
                html_body = """
                <html>
                <body>
                  <p>Xin chào bạn, vui lòng nhập mã bên dưới:</p>
                  <div id="otp-code-value" style="font-size:32px;">712390</div>
                </body>
                </html>
                """
                b64_html = base64.urlsafe_b64encode(html_body.encode("utf-8")).decode("ascii")
                msg_obj = {
                    "snippet": "Xin chào bạn, vui lòng nhập mã bên dưới...",
                    "payload": {
                        "headers": [{"name": "Subject", "value": "Smart Home Voice - Xác thực"}],
                        "parts": [{"mimeType": "text/html", "body": {"data": b64_html}}],
                    },
                }
                return MagicMock(returncode=0, stdout=json.dumps(msg_obj), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            res = challenger_dummy.read_latest_otp_from_gmail_inbox(message_id="msg-html-id")
            assert res.get("ok") is True
            assert res.get("extracted_otp") == "712390"

    def test_edge_case_base64url_padding_variations(self, challenger_dummy: ChallengerM3Dummy):
        """Trường hợp biên: Base64URL không có đệm '=' với các độ dài khác nhau (len % 4 = 1, 2, 3)."""
        test_strings = [
            "Mã xác thực: 111222.",
            "Mã xác nhận OTP: 333444!",
            "Code OTP của bạn: 555666!!!",
        ]
        for idx, text in enumerate(test_strings):
            raw_b64_unpadded = base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")

            def make_fake_run(b64_data):
                def fake_run(cmd, *args, **kwargs):
                    if "messages" in cmd and "get" in cmd:
                        msg_obj = {
                            "snippet": "",
                            "payload": {
                                "headers": [],
                                "parts": [{"body": {"data": b64_data}}],
                            },
                        }
                        return MagicMock(returncode=0, stdout=json.dumps(msg_obj), stderr="")
                    return MagicMock(returncode=1, stdout="", stderr="error")
                return fake_run

            with patch("subprocess.run", side_effect=make_fake_run(raw_b64_unpadded)):
                res = challenger_dummy.read_latest_otp_from_gmail_inbox(message_id=f"msg-b64-pad-{idx}")
                assert res.get("ok") is True
                expected_otp = re.search(r"\d{6}", text).group(0)
                assert res.get("extracted_otp") == expected_otp

    def test_search_query_contains_required_predicates(self, challenger_dummy: ChallengerM3Dummy):
        """Query tìm kiếm thư gws gmail list phải chứa predicate chuẩn."""
        captured_cmd = []

        def fake_subprocess_run(cmd, *args, **kwargs):
            captured_cmd.append(cmd)
            if "list" in cmd:
                return MagicMock(returncode=0, stdout='{"messages": [{"id": "found-123"}]}', stderr="")
            if "get" in cmd:
                text = "Mã xác thực: 991122"
                b64 = base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")
                return MagicMock(returncode=0, stdout=json.dumps({"payload": {"parts": [{"body": {"data": b64}}]}}), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            challenger_dummy.read_latest_otp_from_gmail_inbox(message_id="")
            assert len(captured_cmd) >= 1
            list_cmd = captured_cmd[0]
            assert "--params" in list_cmd
            params_str = list_cmd[list_cmd.index("--params") + 1]
            params = json.loads(params_str)

            q = params.get("q", "")
            assert 'subject:"Smart Home"' in q, f"Query thiếu subject:\"Smart Home\": '{q}'"
            assert "xác thực" in q or "OTP" in q, f"Query thiếu từ khóa xác thực: '{q}'"
            assert params.get("maxResults") >= 5

    def test_scraper_empty_inbox_and_error_handling(self, challenger_dummy: ChallengerM3Dummy):
        """Khi danh sách thư rỗng hoặc subprocess lỗi, hàm trả về kết quả lỗi nhẹ nhàng không throw exception."""
        def fake_empty_list(cmd, *args, **kwargs):
            if "list" in cmd:
                return MagicMock(returncode=0, stdout='{"messages": []}', stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_empty_list):
            res = challenger_dummy.read_latest_otp_from_gmail_inbox()
            assert res.get("ok") is False
            assert "Không tìm thấy" in res.get("error", "")

        def fake_crash_proc(cmd, *args, **kwargs):
            raise RuntimeError("Network timeout simulation")

        with patch("subprocess.run", side_effect=fake_crash_proc):
            res_crash = challenger_dummy.read_latest_otp_from_gmail_inbox()
            assert res_crash.get("ok") is False
            assert "Network timeout" in res_crash.get("error", "")

    def test_scraper_corrupted_payload_data_handled_cleanly(self, challenger_dummy: ChallengerM3Dummy):
        """Khi body data chứa chuỗi base64 bị hỏng hoặc payload không có số 6 chữ số, hàm xử lý an toàn."""
        def fake_corrupt_get(cmd, *args, **kwargs):
            if "get" in cmd:
                msg_obj = {
                    "snippet": "Tin nhắn rác không có số",
                    "payload": {
                        "headers": [{"name": "Subject", "value": "Thư thông báo"}],
                        "parts": [{"body": {"data": "!!!@@@###INVALID_BASE64$$$"}}],
                    },
                }
                return MagicMock(returncode=0, stdout=json.dumps(msg_obj), stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        with patch("subprocess.run", side_effect=fake_corrupt_get):
            res = challenger_dummy.read_latest_otp_from_gmail_inbox(message_id="msg-corrupt")
            assert res.get("ok") is False
            assert "không tìm thấy chuỗi 6 số OTP" in res.get("error", "")


class TestSecurityZeroLeakAdversarial:
    """Kiểm tra đối kháng về an toàn bảo mật và Zero-Leak."""

    def test_zero_leak_smtp_password_in_headers_or_bodies(self, challenger_dummy: ChallengerM3Dummy):
        """Tuyệt đối không rò rỉ SMTP secret hoặc app password vào bất kỳ header hay body nào."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        canary_secret = "CANARY_SMTP_SUPER_SECRET_TOKEN_999!"

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": canary_secret, "SMTP_USER": "senat6031@gmail.com"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):

            challenger_dummy.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="294815",
                display_name="Security Canary",
            )
            msg = mock_smtp.send_message.call_args[0][0]
            raw_msg = msg.as_string()

            assert canary_secret not in raw_msg, "CRITICAL: Secret SMTP bị rò rỉ vào nội dung email!"

            # Kiểm tra audit logs
            for log in challenger_dummy.audit_logs:
                log_str = json.dumps(log, default=str)
                assert canary_secret not in log_str, "CRITICAL: Secret SMTP bị rò rỉ vào audit logs!"

    def test_missing_secret_safe_error_response_no_traceback_leak(self, challenger_dummy: ChallengerM3Dummy):
        """Khi thiếu secret, hàm trả về kết quả an toàn với mã lỗi rõ ràng, không throw unhandled exception."""
        with patch.dict(os.environ, {}, clear=True), \
             patch("subprocess.run", side_effect=Exception("No gws installed")):

            res = challenger_dummy.send_real_gmail_otp(
                target_email="senat6031@gmail.com",
                otp_code="123456",
                display_name="No Secret User",
            )
            assert res.get("sent_real_gmail") is False
            assert res.get("missing_secret") == "GMAIL_APP_PASSWORD"
            assert "GMAIL_APP_PASSWORD" in res.get("error", "")
