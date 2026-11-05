# Handoff Report: Milestone 3 Empirical Challenge (R3: Email RFC 5322 Standards & Deliverability)

**Agent:** `challenger_m3_1` (Archetype: `teamwork_challenger`, Roles: `critic`, `specialist`)  
**Parent Orchestrator:** `91485de0-7c6f-449a-ba3f-ed6820ebb01a`  
**Workspace:** `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\challenger_m3_1`  
**Test Suite Created:** `tests/test_challenger_m3_rfc5322.py` (35 adversarial test cases)  
**Date:** 2026-11-05T07:45:00Z  
**Type:** Hard Handoff (Empirical Challenge Complete)  
**Final Verdict:** **APPROVE**

---

## 1. Observation

### 1.1. Pre-Challenge Review Scope
- **Source Code Under Review**: `simulator/auth/invite_and_gmail_mixin.py` (Lines 530–677: `send_invite_link_via_gmail`, Lines 678–869: `send_real_gmail_otp`, Lines 870–971: `read_latest_otp_from_gmail_inbox`).
- **Milestone Scope**: `SCOPE.md` (M3 Contract: RFC 5322 headers, anti-spam subjects with 0 OTP / 0 ALL-CAPS / 0 emojis, multipart alternative with text/plain + light-background text/html, resilient Gmail inbox scraper).
- **Worker Handoff**: `worker_m3/handoff.md` claiming 59/59 green regression tests.

### 1.2. Adversarial Empirical Test Suite Execution
Created independent challenge suite `tests/test_challenger_m3_rfc5322.py` covering 5 hostile attack dimensions:
1. **RFC 5322 Header Fuzzing**:
   - Tested unicode display names across Vietnamese diacritics (`Nguyễn Tuấn Anh`), East Asian Kanji (`山田 太郎`), Arabic (`أحمد بن علي`), Cyrillic (`Иван Иванович`), and special characters (quotes `"`, commas `,`, brackets `<>`, long 150-char strings).
   - Tested CRLF header injection attempts (`Senat Admin\r\nBcc: evil_stealer@attacker.org\r\nX-Spam: No\r\n`).
   - Tested `SMTP_USER` domain resolution (punycode `xn--h-4ia.vn`, multi-level subdomains, missing `@` fallback).
   - Tested RFC 2822/5322 Date header conformance with timezone offsets.
2. **Subject Anti-Spam Fuzzing**:
   - Fuzzed `send_real_gmail_otp` with user-supplied ALL-CAPS words (`USER ALL CAPS 123456 🔥 🚨`) and OTP codes (`999888`).
   - Verified strict absence of ANY digits (0-9), ANY ALL-CAPS words (2+ uppercase characters), and ANY emojis in both OTP and invite subjects.
3. **MIME Multipart Alternative Fuzzing**:
   - Verified strict `multipart/alternative` structure with 2 parts: `text/plain` and `text/html`.
   - Verified plain text part has 0 emojis, valid UTF-8, and contains OTP.
   - Verified HTML part uses light background (`#ffffff` / `#f8fafc`), isolates OTP in `<div id="otp-code-value">`, has 0 emojis, and has zero deceptive Google OAuth claims.
   - Verified resilience against XSS / HTML script tag injection in `display_name` and `issued_password`.
4. **Gmail Inbox Scraper Fuzzing (`read_latest_otp_from_gmail_inbox`)**:
   - 4-level nested multipart hierarchy (`multipart/mixed` -> `multipart/related` -> `multipart/alternative` -> `text/html`).
   - Malformed Base64URL padding (`len % 4 == 1`) and corrupted non-base64 characters.
   - Single-part direct payload where data is directly in `payload["body"]["data"]`.
   - HTML container precedence over distractor 6-digit numbers in snippet.
   - Preservation of leading zeros (`"001234"`, `"000000"`).
   - Whitespace and newline resilience inside `<div id="otp-code-value">\n 847291 \n</div>`.
5. **Zero-Leak Security Audit**:
   - Verified `GMAIL_APP_PASSWORD` and `SMTP_PASSWORD` are never returned in response dicts or stored in `audit_logs`.
   - Verified error reporting identifies `missing_secret: "GMAIL_APP_PASSWORD"` without leaking system memory or secrets.

### 1.3. Empirical Test Command Results
1. **Challenger Suite (`tests/test_challenger_m3_rfc5322.py`)**:
   Command:
   `pytest tests/test_challenger_m3_rfc5322.py -v`
   Result:
   ```
   ============================= 35 passed in 1.28s ==============================
   ```
2. **Combined Regression & Challenge Suite (Milestones 1–3)**:
   Command:
   `pytest tests/test_challenger_m3_rfc5322.py tests/test_phase6_r3_rfc5322.py tests/test_phase5_r3_otp_email.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py -v`
   Result:
   ```
   ======================= 94 passed, 3 warnings in 15.39s =======================
   ```
3. **Phase 5 Challenger Regression Suite**:
   Command:
   `pytest tests/test_challenger_phase5_r2_r3.py -v`
   Result:
   ```
   ================= 24 passed, 3 warnings in 125.90s (0:02:05) ==================
   ```

### 1.4. Encoding & POSIX LF Verification
Command:
```python
python -c "
import os
for f in ['tests/test_challenger_m3_rfc5322.py', '.agents/teamwork/challenger_m3_1/DISPATCH.md', '.agents/teamwork/challenger_m3_1/BRIEFING.md', '.agents/teamwork/challenger_m3_1/progress.md']:
    raw = open(f, 'rb').read()
    print(f, 'BOM:', raw.startswith(b'\xef\xbb\xbf'), 'CRLF:', raw.count(b'\r\n'))
"
```
Result:
```
tests/test_challenger_m3_rfc5322.py BOM: False CRLF: 0
.agents/teamwork/challenger_m3_1/DISPATCH.md BOM: False CRLF: 0
.agents/teamwork/challenger_m3_1/BRIEFING.md BOM: False CRLF: 0
.agents/teamwork/challenger_m3_1/progress.md BOM: False CRLF: 0
```

---

## 2. Logic Chain

1. **RFC 5322 Headers & Injection Immunity**:
   - `email.utils.formataddr(('Smart Home Voice AI', sender_addr))` formats mailbox headers compliant with RFC 5322 §3.4.
   - When CRLF injection is attempted in `display_name` (`Senat Admin\r\nBcc: evil@attacker.com`), Python's `email.header.Header.encode` detects embedded linebreaks and actively raises `HeaderParseError: header value appears to contain an embedded header`.
   - In `send_real_gmail_otp` (Line 815), `try...except Exception as exc:` safely catches the exception and returns `sent_real_gmail: False, error: ...`, ensuring that CRLF injection cannot hijack SMTP headers or leak blind carbon copies.
   - International Unicode display names are converted into RFC 2047 encoded words (`=?utf-8?b?...?=`) and round-trip cleanly via `email.utils.parseaddr`.
   - `Date` header format conforms to RFC 2822/5322 with local timezone offset, and `Message-ID` adheres to `<unique_id@domain>`.

2. **Subject Anti-Spam Deliverability Standards**:
   - OTP subject is fixed to `"Smart Home Voice - Mã xác thực tài khoản"` regardless of caller parameters (`display_name`, `otp_code`), guaranteeing 0 digits (protecting lockscreen privacy), 0 ALL-CAPS words (preventing SpamAssassin penalty), and 0 emojis.
   - Invite subject is `"Smart Home Voice - Lời mời đăng ký tài khoản Cấp {target_tier} ({target_role_label})"`, eliminating legacy `[Smart Home Voice AI]` (`AI` being ALL-CAPS) and emoji prefixes.

3. **MIME Multipart Alternative & Anti-Deceptive Layout**:
   - Message structure is strictly `multipart/alternative` with `text/plain` as part 0 and `text/html` as part 1.
   - Plain text payload is clean, UTF-8 encoded, contains OTP, zero emojis, and zero Google OAuth claims.
   - HTML payload features light-background styling (`#f8fafc` / `#ffffff`), isolating OTP inside `<div id="otp-code-value">`, with 0 emojis and zero misleading Google OAuth claims.
   - Script and markup tags passed in user fields (`display_name`, `issued_password`) do not break MIME boundary or message serialization.

4. **Resilient Inbox Scraper**:
   - In `read_latest_otp_from_gmail_inbox`, query `q: 'subject:"Smart Home" (xác thực OR OTP OR verification)'` and `maxResults: 5` properly discover new OTP emails.
   - Recursive Base64URL decoder `_walk` traverses 4+ levels of nested multipart structures.
   - Corrupted Base64 parts with invalid padding (`len % 4 == 1`) or invalid characters are caught and skipped without aborting.
   - When distractor 6-digit numbers appear in snippet, Tier 2 HTML container regex `id=["']otp-code-value["']` successfully extracts the true OTP.
   - Leading zeros (`"001234"`, `"000000"`) are preserved as 6-digit strings.

5. **Zero-Leak Security Compliance**:
   - `GMAIL_APP_PASSWORD` and `SMTP_PASSWORD` are never logged in `audit_logs` or exposed in return dictionaries.
   - Missing secret handling cleanly identifies `missing_secret: "GMAIL_APP_PASSWORD"` without exposing memory or other environment variables.

---

## 3. Caveats

- **No Caveats.**
- Automated tests mock SMTP connections and CLI subprocess calls cleanly via standard test fixtures. Real network dispatches were not performed during M3 (single real verification email is explicitly reserved for Milestone 4 under the project protocol).

---

## 4. Conclusion

The Milestone 3 (R3: Email RFC 5322 Standards & Deliverability) implementation has been empirically challenged across 35 adversarial test scenarios. All 35 adversarial tests passed cleanly. The combined regression suite of 94 tests (Milestones 1–3) passed with 100% green status. The implementation satisfies all acceptance criteria in `SCOPE.md` and `ORIGINAL_REQUEST.md` with zero regressions and zero security leaks.

**VERDICT: APPROVE**

---

## 5. Verification Method

To independently reproduce and verify this empirical challenge:

1. **Run Challenger Adversarial Suite (35 tests)**:
   ```powershell
   pytest tests/test_challenger_m3_rfc5322.py -v
   ```
   *Expected:* 35 passed.

2. **Run Combined Milestone 1–3 Regression Suite (94 tests)**:
   ```powershell
   pytest tests/test_challenger_m3_rfc5322.py tests/test_phase6_r3_rfc5322.py tests/test_phase5_r3_otp_email.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py -v
   ```
   *Expected:* 94 passed.

3. **Run Phase 5 Challenger Suite (24 tests)**:
   ```powershell
   pytest tests/test_challenger_phase5_r2_r3.py -v
   ```
   *Expected:* 24 passed.

4. **Verify UTF-8 and 0 CRLF**:
   ```powershell
   python -c "
   import os
   for f in ['tests/test_challenger_m3_rfc5322.py', '.agents/teamwork/challenger_m3_1/handoff.md']:
       raw = open(f, 'rb').read()
       assert not raw.startswith(b'\xef\xbb\xbf'), f'BOM in {f}'
       assert b'\r\n' not in raw, f'CRLF in {f}'
   print('ALL CLEAN POSIX LF UTF-8')
   "
   ```
   *Expected:* `ALL CLEAN POSIX LF UTF-8`.
