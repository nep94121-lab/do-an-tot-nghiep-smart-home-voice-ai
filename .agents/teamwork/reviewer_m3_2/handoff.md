# Handoff Report: Milestone 3 Independent Quality & Adversarial Review

**Reviewer & Critic:** `reviewer_m3_2` (Archetype: `reviewer_and_adversarial_critic`, Roles: `reviewer`, `critic`)  
**Parent Orchestrator:** `91485de0-7c6f-449a-ba3f-ed6820ebb01a`  
**Workspace:** `C:\Users\LENOVO\datn-wt\p6-otp`  
**Date:** 2026-11-05T07:38:00Z  
**Type:** Hard Handoff (Review Complete)  
**Verdict:** **APPROVE**

---

## 1. Observation

### 1.1. Code Inspection: `simulator/auth/invite_and_gmail_mixin.py`
1. **RFC 5322 Headers Construction**:
   - Lines 568-575 (`send_invite_link_via_gmail`) & Lines 712-719 (`send_real_gmail_otp`):
     ```python
     msg = MIMEMultipart("alternative")
     msg["From"] = email.utils.formataddr((sender_name, sender_addr))
     msg["To"] = email.utils.formataddr((to_name, to_addr))
     msg["Date"] = email.utils.formatdate(localtime=True)
     msg["Message-ID"] = email.utils.make_msgid(domain=domain)
     msg["Reply-To"] = email.utils.formataddr((sender_name, sender_addr))
     ```
     `From`, `To`, and `Reply-To` are properly wrapped with `email.utils.formataddr`. `Date` is formatted according to RFC 2822 / RFC 5322 §3.6.1. `Message-ID` is generated via `email.utils.make_msgid(domain=domain)` enclosed in `<...>` with a valid domain.

2. **Subject Anti-Spam Heuristics**:
   - `send_real_gmail_otp` (Line 718):
     `msg["Subject"] = "Smart Home Voice - Mã xác thực tài khoản"`
     Constant string: strictly Title Case, zero OTP digits, zero ALL-CAPS acronyms ('OTP', 'AI', 'OAUTH'), zero emojis.
   - `send_invite_link_via_gmail` (Line 574):
     `msg["Subject"] = f"Smart Home Voice - Lời mời đăng ký tài khoản Cấp {inv['target_tier']} ({inv['target_role_label']})"`
     Clean Title Case format without ALL-CAPS words or emojis.

3. **Multipart Alternative Structure**:
   - `send_real_gmail_otp` (Lines 785-786):
     ```python
     msg.attach(MIMEText(plain_text, "plain", "utf-8"))
     msg.attach(MIMEText(html_body, "html", "utf-8"))
     ```
     RFC 2046 compliant order (`text/plain` first, `text/html` second). Eliminates SpamAssassin `MIME_HTML_ONLY`.
   - HTML template (Lines 751-784):
     Light background `#f8fafc` and `#ffffff`, neutral borders `#e2e8f0`, dark text `#1e293b`.
     Zero emojis throughout body text.
     Zero deceptive Google OAuth branding (`Google OAuth` removed; replaced with `Smart Home Voice - Xác thực tài khoản người dùng`).
     Contains dedicated container: `<div id="otp-code-value" ...>{otp_code}</div>`.

4. **Resilient Inbox Scraper**:
   - Lines 875-879:
     ```python
     list_params = json.dumps({
         "userId": "me",
         "maxResults": 5,
         "q": 'subject:"Smart Home" (xác thực OR OTP OR verification)',
     })
     ```
   - Lines 920-938: `_extract_payload_text` recursively traverses `msg_obj["payload"]`, pads Base64URL string (`pad = len(data) % 4`), decodes via `base64.urlsafe_b64decode`, handles charset decoding with `errors="replace"`.
   - Lines 942-952: 3-tier regex cascade:
     1. Context regex: `(?:OTP[:\s-]*|mã[:\s-]*|code[:\s-]*|xác thực[:\s-]*|xác nhận[:\s-]*)\s*(\d{6})\b`
     2. HTML container regex: `id=["\']otp-code-value["\'][^>]*>(?:OTP:)?\s*(\d{6})<`
     3. Boundary fallback regex: `\b(\d{6})\b`

### 1.2. Zero-Leak Constraint Verification
- Inspection of `simulator/auth/invite_and_gmail_mixin.py` Lines 788-823, 860-869:
  `smtp_pass` is read from `os.environ` and passed directly to `server.login`.
  Neither `smtp_pass` nor any credentials are ever printed or written to logs.
  On exception (Line 820), only generic error message is logged: `f"Lỗi gửi email qua SMTP: {str(exc)[:150]}"`.
  When environment variables are missing (Lines 861-868), the response returns `"missing_secret": "GMAIL_APP_PASSWORD"` without exposing any existing secret values or mock passwords.

### 1.3. Integrity Audit (Anti-Cheating Verification)
- **Hardcoded test results**: None. `send_real_gmail_otp` dynamically formats arbitrary OTP codes and recipient addresses. `read_latest_otp_from_gmail_inbox` dynamically parses subprocess JSON outputs.
- **Dummy/Facade implementations**: None. Real `email.mime` objects, real Base64URL decoders, real regex parsers.
- **Shortcuts/Bypasses**: None. Both SMTP and `gws` dispatches are fully implemented with graceful fallback.
- **Fabricated verification outputs**: None. All test outputs reproduced and verified directly via local CLI execution.
- **Self-certifying work**: None. Challenger and independent test suites run with independent fixtures and headless browser assertions.

### 1.4. Test Execution Results
1. **R3 Unit and RFC 5322 Tests**:
   - Command: `pytest tests/test_phase6_r3_rfc5322.py tests/test_phase5_r3_otp_email.py -v`
   - Result: `12 passed, 3 warnings in 7.00s` (Exit Code: 0).
2. **Phase 6 Milestones 1-3 Full Regression**:
   - Command: `pytest tests/test_phase6_r3_rfc5322.py tests/test_phase5_r3_otp_email.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py -v`
   - Result: `59 passed, 3 warnings in 7.28s` (Exit Code: 0).
3. **Adversarial Challenger Suite**:
   - Command: `pytest tests/test_challenger_phase5_r2_r3.py -v`
   - Result: `24 passed, 3 warnings in 74.11s` (Exit Code: 0).

### 1.5. Encoding & Line Endings Audit
- Command:
  ```python
  python -c "
  files = [
      'simulator/auth/invite_and_gmail_mixin.py',
      'tests/test_phase5_r3_otp_email.py',
      'tests/test_phase6_r3_rfc5322.py',
      '.agents/teamwork/worker_m3/handoff.md',
  ]
  for f in files:
      raw = open(f, 'rb').read()
      assert not raw.startswith(b'\xef\xbb\xbf'), f'BOM in {f}'
      assert b'\r\n' not in raw, f'CRLF in {f}'
  print('PASS: All files are UTF-8 without BOM and 0 CRLF')
  "
  ```
- Result: `PASS: All files are UTF-8 without BOM and 0 CRLF`.

---

## 2. Logic Chain

1. **RFC 5322 Headers (Observation 1.1.1)**:
   - Observation shows `From`, `To`, and `Reply-To` are generated by `email.utils.formataddr`. This guarantees syntactic compliance with RFC 5322 §3.4 mailbox specifications.
   - `email.utils.formatdate(localtime=True)` generates a valid RFC 2822/5322 timestamp, preventing mail relays from rejecting or deprioritizing dateless messages (RFC 5322 §3.6.1).
   - `email.utils.make_msgid(domain=domain)` produces a globally unique identifier formatted as `<unique_string@domain>`, resolving RFC 5322 §3.6.4 requirements.

2. **Spam & Reputation Deliverability (Observation 1.1.2 & 1.1.3)**:
   - Setting `Subject: Smart Home Voice - Mã xác thực tài khoản` removes raw OTP digits (preventing exposure on lock screens and heuristic spam scoring for unsolicited OTPs), removes ALL-CAPS words (`OTP`, `AI`, `OAUTH`), and removes emojis.
   - Employing `MIMEMultipart("alternative")` with `text/plain` attached first and `text/html` attached second adheres to RFC 2046 §5.1.4 and completely eliminates the SpamAssassin `MIME_HTML_ONLY` penalty (+1.1 to +2.5 spam score).
   - Replacing the dark theme and deceptive "Google OAuth" phrasing with neutral `#ffffff`/`#f8fafc` styling and accurate "Smart Home Voice" identity prevents automated Gmail anti-phishing / anti-spoofing flags.

3. **Scraper Resilience (Observation 1.1.4)**:
   - Updating query `q` to `'subject:"Smart Home" (xác thực OR OTP OR verification)'` matches both historical and RFC 5322 compliant subjects.
   - Recursive Base64URL traversal decodes nested parts regardless of MIME depth or multipart container hierarchy.
   - The 3-tier regex hierarchy ensures OTPs accompanied by contextual keywords or within `<div id="otp-code-value">` are matched before falling back to generic 6-digit boundaries, avoiding collisions with 6-digit numbers in body text.

4. **Security & Integrity (Observation 1.2, 1.3, 1.5)**:
   - Zero SMTP secrets are logged, exposed in error responses, or embedded in tests.
   - All 59 unit/regression tests and 24 adversarial tests pass with exit code 0.
   - All files comply with 0 CRLF and UTF-8 without BOM.

---

## 3. Caveats

- **No Caveats.**
- Automated tests mock network dispatches (SMTP/gws) cleanly as required by Milestone 3 test isolation. The single real verification email is explicitly reserved for Milestone 4.

---

## 4. Conclusion

The implementation of Milestone 3 (R3: Email RFC 5322 Standards & Deliverability) by `worker_m3` is completely verified, rigorous, free of integrity violations, and meets 100% of the acceptance criteria defined in `SCOPE.md` and `ORIGINAL_REQUEST.md`.

**Verdict: APPROVE**

---

## 5. Verification Method

To independently reproduce this verification:

1. **Verify RFC 5322 Unit & Delivery Tests**:
   ```powershell
   pytest tests/test_phase6_r3_rfc5322.py tests/test_phase5_r3_otp_email.py -v
   ```
   *Expected:* 12 passed.

2. **Verify Full Milestone 1-3 Regression Suite**:
   ```powershell
   pytest tests/test_phase6_r3_rfc5322.py tests/test_phase5_r3_otp_email.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py -v
   ```
   *Expected:* 59 passed.

3. **Verify Adversarial Challenger Suite**:
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
