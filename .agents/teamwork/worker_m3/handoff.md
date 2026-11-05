# Handoff Report: Milestone 3 (R3: Email RFC 5322 Standards & Deliverability)

**Worker:** `worker_m3` (Archetype: `teamwork_worker`, Roles: `implementer`, `qa`, `specialist`)  
**Parent Orchestrator:** `91485de0-7c6f-449a-ba3f-ed6820ebb01a`  
**Workspace:** `C:\Users\LENOVO\datn-wt\p6-otp`  
**Date:** 2026-11-05T07:30:00Z  
**Type:** Hard Handoff (Task Complete)

---

## 1. Observation

### 1.1. Pre-Fix Code State
1. **`simulator/auth/invite_and_gmail_mixin.py`**:
   - `From` header: Set as bare string `msg["From"] = smtp_user` or `msg["From"] = "nep94121@gmail.com"` without `email.utils.formataddr`.
   - `To` header: Set as bare email address string `msg["To"] = actual_to`.
   - `Date` header: Completely absent (violation of RFC 5322 §3.6.1).
   - `Message-ID` header: Completely absent (violation of RFC 5322 §3.6.4).
   - `Reply-To` header: Completely absent.
   - `Subject` lines: Contained OTP codes and ALL-CAPS words:
     - `msg["Subject"] = f"{subject_prefix} Mã xác nhận OTP: {otp_code} ({display_name})"`
     - `msg["Subject"] = f"[Smart Home Voice AI] Lời mời đăng ký tài khoản Cấp ..."`
   - MIME body: Initialized `MIMEMultipart("alternative")` but attached only a single `text/html` part, missing `text/plain` entirely. HTML used a dark `#0f172a` background with neon accents, multiple emojis, and deceptive "Google OAuth" branding (`🔐 XÁC NHẬN GOOGLE OAUTH & GMAIL OTP - SMART HOME AI`).
   - `read_latest_otp_from_gmail_inbox`: Used static search query `q: "Smart Home Mã xác nhận OTP"` with `maxResults: 1`, only searched `subject` and `snippet` with single-tier regex `\b(\d{6})\b`, completely failing to decode MIME parts from `payload["parts"]`.

### 1.2. TDD Red State (Pre-Implementation Verification)
Ran command:
`pytest tests/test_phase5_r3_otp_email.py tests/test_phase6_r3_rfc5322.py -v`
Result:
```
=========================== short test summary info ===========================
FAILED tests/test_phase5_r3_otp_email.py::TestPhase5R3PasswordResetOtpEmail::test_r3_successful_smtp_dispatch_when_secret_provided
FAILED tests/test_phase6_r3_rfc5322.py::TestRFC5322HeadersAndFormatting::test_send_real_gmail_otp_headers_rfc5322
FAILED tests/test_phase6_r3_rfc5322.py::TestRFC5322HeadersAndFormatting::test_send_invite_link_headers_rfc5322
FAILED tests/test_phase6_r3_rfc5322.py::TestSubjectLinesAntiSpam::test_otp_subject_has_no_digits_no_all_caps_no_emojis
FAILED tests/test_phase6_r3_rfc5322.py::TestMultipartAlternativeStructure::test_otp_email_multipart_structure_and_styling
FAILED tests/test_phase6_r3_rfc5322.py::TestResilientGmailInboxScraper::test_scraper_query_matches_new_subject_format
FAILED tests/test_phase6_r3_rfc5322.py::TestResilientGmailInboxScraper::test_scraper_decodes_nested_multipart_payload
FAILED tests/test_phase6_r3_rfc5322.py::TestResilientGmailInboxScraper::test_scraper_3tier_regex_precedence
=================== 8 failed, 4 passed, 3 warnings in 9.86s ===================
```

### 1.3. Post-Fix Verification (TDD Green & Full Regression)
Ran command:
`pytest tests/test_phase6_r3_rfc5322.py tests/test_phase5_r3_otp_email.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py -v`
Result:
```
======================= 59 passed, 3 warnings in 49.78s =======================
```
Ran command:
`pytest tests/test_challenger_phase5_r2_r3.py -v`
Result:
```
================== 24 passed, 3 warnings in 89.25s (0:01:29) ==================
```

### 1.4. Encoding and Line Endings Audit
Ran command:
`python -c "check BOM and CRLF"`
Result:
```
simulator/auth/invite_and_gmail_mixin.py: BOM=False, CRLF count=0
tests/test_phase5_r3_otp_email.py: BOM=False, CRLF count=0
tests/test_phase6_r3_rfc5322.py: BOM=False, CRLF count=0
.agents/teamwork/worker_m3/DISPATCH.md: BOM=False, CRLF count=0
.agents/teamwork/worker_m3/BRIEFING.md: BOM=False, CRLF count=0
.agents/teamwork/worker_m3/progress.md: BOM=False, CRLF count=0
```

---

## 2. Logic Chain

1. **RFC 5322 Compliance**:
   - `email.utils.formataddr(('Smart Home Voice AI', sender_addr))` formats the `From` and `Reply-To` headers into RFC 5322 compliant mailbox format `Smart Home Voice AI <address>`.
   - `email.utils.formatdate(localtime=True)` produces valid RFC 2822/5322 Date timestamps ensuring Gmail and SMTP relays do not flag messages for missing origination dates.
   - `email.utils.make_msgid(domain=domain)` produces a unique `Message-ID` enclosed in `<...>` with a valid domain portion, satisfying RFC 5322 §3.6.4.

2. **Spam & Anti-Phishing Deliverability Heuristics**:
   - Subjects formatted as `"Smart Home Voice - Mã xác thực tài khoản"` and `"Smart Home Voice - Lời mời đăng ký tài khoản Cấp ..."` remove raw OTP digits, ALL-CAPS words (`OTP`, `AI`, `OAUTH`), and emojis. This prevents spam filter penalties and protects OTP privacy on lockscreen notifications.
   - Using MIME `multipart/alternative` with `text/plain` attached first and `text/html` attached second complies with RFC 2046 and eliminates SpamAssassin `MIME_HTML_ONLY` triggers.
   - HTML template redesigned to clean light-background `#ffffff` / `#f8fafc`, clean typography, neutral borders, zero emojis, and zero misleading Google OAuth claims, preventing Google anti-spoofing flags.

3. **Resilient Inbox Scraper**:
   - Search query upgraded to `q: 'subject:"Smart Home" (xác thực OR OTP OR verification)'` with `maxResults: 5`, matching both old and new subjects.
   - Recursive Base64URL decoder `_extract_payload_text` traverses nested `payload["parts"]` and extracts all encoded body texts.
   - 3-tier regex logic ensures OTP is extracted reliably:
     1. Keyword context regex: `(?:OTP[:\s-]*|mã[:\s-]*|code[:\s-]*|xác thực[:\s-]*|xác nhận[:\s-]*)\s*(\d{6})\b`
     2. HTML container regex: `id=["\']otp-code-value["\'][^>]*>(?:OTP:)?\s*(\d{6})<`
     3. Fallback boundary regex: `\b(\d{6})\b`

---

## 3. Caveats

- **No Caveats.**
- Automated tests mock SMTP connections and CLI subprocess calls cleanly via standard test fixtures. Real network dispatches were not performed during M3 (single real verification email is explicitly reserved for Milestone 4).

---

## 4. Conclusion

Milestone 3 (R3: Email RFC 5322 Standards & Deliverability) has been fully implemented, verified, and documented following strict TDD. All acceptance criteria for R3 in `SCOPE.md` and `ORIGINAL_REQUEST.md` have been met. All tests pass with 100% green status.

---

## 5. Verification Method

To independently reproduce and verify this milestone:

1. **Run R3 Unit & RFC 5322 Test Suite**:
   ```powershell
   pytest tests/test_phase6_r3_rfc5322.py tests/test_phase5_r3_otp_email.py -v
   ```
   *Expected:* 12 passed.

2. **Run Full Milestone 1-3 Regression Suite**:
   ```powershell
   pytest tests/test_phase6_r3_rfc5322.py tests/test_phase5_r3_otp_email.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py -v
   ```
   *Expected:* 59 passed.

3. **Run Adversarial Challenger Suite**:
   ```powershell
   pytest tests/test_challenger_phase5_r2_r3.py -v
   ```
   *Expected:* 24 passed.

4. **Verify 0 CRLF and UTF-8 Without BOM**:
   ```powershell
   python -c "
   for p in ['simulator/auth/invite_and_gmail_mixin.py', 'tests/test_phase5_r3_otp_email.py', 'tests/test_phase6_r3_rfc5322.py']:
       raw = open(p, 'rb').read()
       assert not raw.startswith(b'\xef\xbb\xbf'), f'BOM in {p}'
       assert b'\r\n' not in raw, f'CRLF in {p}'
   print('ALL CLEAN POSIX LF UTF-8')
   "
   ```
   *Expected:* `ALL CLEAN POSIX LF UTF-8`.
