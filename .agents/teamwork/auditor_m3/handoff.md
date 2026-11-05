# Forensic Integrity Audit Report: Milestone 3 (R3: Email RFC 5322 Standards & Deliverability)

**Auditor:** `auditor_m3` (Archetype: `forensic_auditor`, Roles: `critic`, `specialist`, `auditor`)  
**Parent Orchestrator:** `91485de0-7c6f-449a-ba3f-ed6820ebb01a`  
**Workspace:** `C:\Users\LENOVO\datn-wt\p6-otp`  
**Target:** Milestone 3 (R3: Email RFC 5322 Standards & Deliverability)  
**Profile:** General Project Forensic Integrity Check (Development Mode)  
**Verdict:** **CLEAN**

---

## 1. Observation

### 1.1. Anti-Cheat & Anti-Facade AST Inspection
- **Target File:** `simulator/auth/invite_and_gmail_mixin.py`
- Executed AST inspection script scanning for test-name reflection, test environment evasion (`pytest`, `PYTEST_CURRENT_TEST`, `unittest`, `_pytest`, `mock`), and hardcoded return values.
- Result: **0 suspicious nodes or reflection branches found**.
- Function `send_real_gmail_otp` (lines 678–868):
  - `msg["From"] = email.utils.formataddr((sender_name, smtp_user))`
  - `msg["To"] = email.utils.formataddr((to_name, actual_to))`
  - `msg["Date"] = email.utils.formatdate(localtime=True)`
  - `msg["Message-ID"] = email.utils.make_msgid(domain=domain)`
  - `msg["Reply-To"] = email.utils.formataddr((sender_name, smtp_user))`
  - `msg["Subject"] = "Smart Home Voice - Mã xác thực tài khoản"`
  - Attachments:
    - `msg.attach(MIMEText(plain_text, "plain", "utf-8"))`
    - `msg.attach(MIMEText(html_body, "html", "utf-8"))`
- Function `send_invite_link_via_gmail` (lines 530–676):
  - Sets RFC 5322 headers via `formataddr`, `formatdate`, `make_msgid`.
  - Attaches plain text and HTML parts with clean styling and 0 emojis.
- Function `read_latest_otp_from_gmail_inbox` (lines 870–970):
  - Search query `q: 'subject:"Smart Home" (xác thực OR OTP OR verification)'`.
  - Recursive Base64URL decoder `_extract_payload_text` with padding handling: `pad = len(data) % 4; padded_data = data + ("=" * (4 - pad) if pad else "")`.
  - 3-tier regex cascade for OTP extraction:
    1. Keyword context regex: `(?:OTP[:\s-]*|mã[:\s-]*|code[:\s-]*|xác thực[:\s-]*|xác nhận[:\s-]*)\s*(\d{6})\b`
    2. HTML container regex: `id=["\']otp-code-value["\'][^>]*>(?:OTP:)?\s*(\d{6})<`
    3. Fallback boundary regex: `\b(\d{6})\b`
- Checked for emojis in email bodies/subjects: **0 emojis found**.
- Checked for deceptive Google OAuth branding: **0 deceptive strings found**.

### 1.2. Zero-Leak Credential Audit
- Scanned all files across the repository for `GMAIL_APP_PASSWORD`, `SMTP_PASSWORD`, Google API keys (`AIza...`), and 16-character app password patterns.
- Findings: **0 real credentials leaked**. All occurrences in test suites are explicit test mock values (e.g., `"dummy_pass"`, `"abcd efgh ijkl mnop"` in `tests/test_phase5_r3_otp_email.py`).
- No `.env` files with secret values exist in repository.

### 1.3. Clean State Verification
- `simulator/data/accounts_3layer.json`: Exactly 6 default seed accounts:
  `['nep94121@gmail.com', 'thanhviena.hust@gmail.com', 'thanhvienb.hust@gmail.com', 'khachc.guest@gmail.com', 'senat6031@gmail.com', 'kbanh376@gmail.com']`.
- `simulator/data/family_email_allowlist.json`: Exactly empty dictionary `{}`.

### 1.4. Formatting & Encoding Audit
- Verified 68 python, markdown, and config files across the workspace.
- Result: **100% UTF-8 without BOM, 0 CRLF (100% POSIX LF)**.
- Specific Milestone 3 targets verified:
  - `simulator/auth/invite_and_gmail_mixin.py`: BOM=False, CRLF=0 (62,726 bytes)
  - `tests/test_phase6_r3_rfc5322.py`: BOM=False, CRLF=0 (19,363 bytes)
  - `tests/test_phase5_r3_otp_email.py`: BOM=False, CRLF=0 (9,500 bytes)
  - `tests/test_challenger_phase6_m3_2.py`: BOM=False, CRLF=0 (31,913 bytes)
  - `.agents/teamwork/worker_m3/handoff.md`: BOM=False, CRLF=0 (7,562 bytes)

### 1.5. Independent Test Execution
- **Command:** `pytest tests/test_phase6_r3_rfc5322.py tests/test_phase5_r3_otp_email.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py -v`
  - Result: `59 passed, 3 warnings in 12.60s` (Exit Code: 0).
- **Command:** `pytest tests/test_challenger_phase5_r2_r3.py -v`
  - Result: `24 passed, 3 warnings in 58.04s` (Exit Code: 0).
- **Command:** `pytest tests/test_challenger_phase6_m3_2.py -v`
  - Result: `20 passed in 1.52s` (Exit Code: 0).
- **Command:** `pytest tests/test_challenger_phase6_m1.py tests/test_challenger_phase6_m1_2.py tests/test_challenger_phase6_m2_empirical.py -v`
  - Result: `149 passed, 1 failed in 24.70s`.
  - Note on the 1 failure: `tests/test_challenger_phase6_m1.py:400` asserted `assert msg["To"] == "senat6031@gmail.com"` expecting a bare string, which was written in Milestone 1 before Milestone 3 introduced RFC 5322 `formataddr` (`'Senat User <senat6031@gmail.com>'`). This is a historical challenger test expectation drift, not an implementation defect.

### 1.6. Orthogonal Independent Verification with Random Nonces
- Executed dedicated orthogonal test script testing from a third-party MTA perspective:
  - **Step 1 (Allowlist Nonce Boundary):** 50 dynamic random string nonces verified against allowlist rejection and environment expansion.
  - **Step 2 (MIME MTA Deserialization):** 25 randomized dispatches serialized to raw bytes and deserialized using Python's standard `email.message_from_bytes`. Verified RFC 5322 headers (`From`, `To`, `Date`, `Message-ID`, `Reply-To`), Subject without OTP/ALL-CAPS/emojis, and multipart/alternative plain+light HTML containing genuine OTP nonces.
  - **Step 3 (Scraper Fuzzing with Nested Payloads):** 30 iterations of multi-level nested payloads with unpadded/padded Base64URL data and decoy phone numbers (`09xxxxxxxx`) / order IDs (`ORD-xxxxxx`). Inbox scraper accurately extracted the genuine OTP nonce in all 30 runs without false positives.
  - Result: **ALL ORTHOGONAL INDEPENDENT CHECKS PASSED (Exit Code: 0)**.

---

## 2. Logic Chain

1. **Anti-Facade Authenticity**:
   - The AST analysis confirmed that `simulator/auth/invite_and_gmail_mixin.py` contains genuine logic for RFC 5322 message creation, Base64URL decoding, and 3-tier regex extraction.
   - No conditional branches or dummy returns bypass computation during tests.
2. **Deliverability & Anti-Spam Heuristics**:
   - RFC 5322 compliance was confirmed by serializing outgoing messages to raw bytes and parsing them via an independent parser. The `Date` header parses to valid datetimes, `Message-ID` conforms to `<id@domain>`, and `From`/`To`/`Reply-To` use `formataddr`.
   - Spam score risks are mitigated: subjects contain no OTP codes, no ALL-CAPS words, and zero emojis.
   - MIME structure is strictly `multipart/alternative` with `text/plain` followed by `text/html` on light background (`#ffffff` / `#f8fafc`), eliminating SpamAssassin `MIME_HTML_ONLY` triggers.
3. **Scraper Robustness**:
   - Fuzzing with random nested payloads, unpadded Base64URL, and decoy 6-digit substrings proved that the scraper reliably prioritizes context keywords and HTML container markers over bare numbers.
4. **Security & Clean State**:
   - 0 secrets leaked across workspace.
   - Clean seed state (`accounts_3layer.json` with 6 accounts, `family_email_allowlist.json` with `{}`) remains intact.
   - 100% POSIX LF and UTF-8 without BOM confirmed.

---

## 3. Caveats

- In `tests/test_challenger_phase6_m1.py` line 400, a test case written during Milestone 1 specifically asserted `assert msg["To"] == "senat6031@gmail.com"` expecting a bare email string. Milestone 3's implementation upgraded `msg["To"]` to RFC 5322 `formataddr((to_name, actual_to))` (`'Senat User <senat6031@gmail.com>'`), causing that single historical assertion to fail. The test assertion in `test_challenger_phase6_m1.py` should be updated to `assert "senat6031@gmail.com" in msg["To"]` or `assert email.utils.parseaddr(msg["To"])[1] == "senat6031@gmail.com"`.
- Real network SMTP dispatch to external email providers was not performed during Milestone 3 (reserved for Milestone 4 verification email).

---

## 4. Conclusion

**Verdict: CLEAN**

Milestone 3 (R3: Email RFC 5322 Standards & Deliverability) satisfies all integrity requirements, acceptance criteria, and quality standards. The implementation is authentic, robust, zero-leak, and fully verified through both automated test suites and independent orthogonal verification.

---

## 5. Verification Method

To independently reproduce this forensic audit:

1. **Run Primary Test Suite**:
   ```powershell
   pytest tests/test_phase6_r3_rfc5322.py tests/test_phase5_r3_otp_email.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py -v
   ```
   *Expected:* 59 passed.

2. **Run Milestone 3 Challenger Suite**:
   ```powershell
   pytest tests/test_challenger_phase6_m3_2.py tests/test_challenger_phase5_r2_r3.py -v
   ```
   *Expected:* 44 passed.

3. **Verify Zero-Leak & Encoding**:
   ```powershell
   python -c "
   import glob
   files = ['simulator/auth/invite_and_gmail_mixin.py', 'tests/test_phase6_r3_rfc5322.py', 'tests/test_phase5_r3_otp_email.py']
   for f in files:
       raw = open(f, 'rb').read()
       assert not raw.startswith(b'\xef\xbb\xbf'), f'BOM in {f}'
       assert b'\r\n' not in raw, f'CRLF in {f}'
   print('ENCODING CLEAN')
   "
   ```
   *Expected:* `ENCODING CLEAN`.
