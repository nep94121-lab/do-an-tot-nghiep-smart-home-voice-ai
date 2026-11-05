# Review & Adversarial Challenge Report: Milestone 3 (R3: Email RFC 5322 Standards & Deliverability)

**Reviewer & Critic:** `reviewer_m3_1` (Archetype: `teamwork_reviewer`, Roles: `reviewer`, `critic`)  
**Parent Orchestrator:** `91485de0-7c6f-449a-ba3f-ed6820ebb01a`  
**Target Codebase:** `C:\Users\LENOVO\datn-wt\p6-otp`  
**Date:** 2026-11-05T07:38:00Z  
**Type:** Hard Handoff (Review Complete)  
**Verdict:** **APPROVE**

---

## 1. Observation

### 1.1. Code Inspection Findings (`simulator/auth/invite_and_gmail_mixin.py`)
- **RFC 5322 Headers Compliance**:
  - `From`: Built via `email.utils.formataddr((sender_name, sender_addr))` producing RFC 5322 mailbox format `"Smart Home Voice AI" <nep94121@gmail.com>`. Vietnamese diacritics are properly RFC 2047 encoded (`=?utf-8?b?...?=`).
  - `To`: Built via `email.utils.formataddr((to_name, actual_to))`.
  - `Date`: Generated via `email.utils.formatdate(localtime=True)` ensuring compliance with RFC 5322 §3.6.1 / RFC 2822.
  - `Message-ID`: Generated via `email.utils.make_msgid(domain=domain)` producing a unique identifier enclosed in angle brackets `<...>` compliant with RFC 5322 §3.6.4.
  - `Reply-To`: Built via `email.utils.formataddr((sender_name, sender_addr))`.
- **Subject Anti-Spam Heuristics**:
  - OTP Subject: strictly `"Smart Home Voice - Mã xác thực tài khoản"` — contains 0 digits, NO ALL-CAPS words (`OTP`, `AI`, `OAUTH`), and 0 emojis.
  - Invite Subject: strictly `f"Smart Home Voice - Lời mời đăng ký tài khoản Cấp {inv['target_tier']} ({inv['target_role_label']})"` — 0 ALL-CAPS words, 0 emojis.
- **MIME Multipart/Alternative Structure**:
  - Container initialized as `MIMEMultipart("alternative")`.
  - Part 1: `MIMEText(plain_text, "plain", "utf-8")` attached first. Zero emojis.
  - Part 2: `MIMEText(html_body, "html", "utf-8")` attached second (standard RFC 2046 preference order).
  - HTML styling: Light background (`#f8fafc` outer, `#ffffff` container card), clean sans-serif typography, zero emojis, OTP prominently rendered in container `#otp-code-value`, and strictly NO deceptive Google OAuth branding or logo spoofing.
- **Resilient Gmail Scraper (`read_latest_otp_from_gmail_inbox`)**:
  - Query parameter `q` upgraded to `'subject:"Smart Home" (xác thực OR OTP OR verification)'` with `maxResults: 5`.
  - Recursive Base64URL decoder `_extract_payload_text` handles stripped padding (`len(data) % 4`) and safely traverses nested MIME parts.
  - 3-tier OTP regex extraction:
    1. Keyword context regex: `(?:OTP[:\s-]*|mã[:\s-]*|code[:\s-]*|xác thực[:\s-]*|xác nhận[:\s-]*)\s*(\d{6})\b`
    2. HTML container regex: `id=["\']otp-code-value["\'][^>]*>(?:OTP:)?\s*(\d{6})<`
    3. Boundary fallback regex: `\b(\d{6})\b`

### 1.2. Integrity Violation & Zero-Leak Audit
- **Integrity Check**:
  - 0 hardcoded test results, mock shortcuts, or bypassed logic in `simulator/auth/invite_and_gmail_mixin.py`.
  - Real MIME construction, real regex parsing, and genuine Base64URL recursive decoders are implemented.
  - When credentials are missing and `gws` CLI is unavailable, system explicitly returns `ok: False`, `missing_secret: "GMAIL_APP_PASSWORD"` without fake success.
- **Zero-Leak Security Constraint**:
  - 0 SMTP secrets, passwords, or tokens are logged, printed, or exposed in return payloads or exception handlers.
- **Encoding & Line Endings Audit**:
  - `simulator/auth/invite_and_gmail_mixin.py`: BOM=False, CRLF=0 (POSIX LF)
  - `tests/test_phase5_r3_otp_email.py`: BOM=False, CRLF=0 (POSIX LF)
  - `tests/test_phase6_r3_rfc5322.py`: BOM=False, CRLF=0 (POSIX LF)
  - All agent review files: BOM=False, CRLF=0 (POSIX LF)

### 1.3. Independent Test Execution Results
1. **Milestones 1–3 Regression Suite**:
   Command: `pytest tests/test_phase6_r3_rfc5322.py tests/test_phase5_r3_otp_email.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py -v`
   Result: **59 passed, 3 warnings in 13.12s** (Exit Code: 0).
2. **Challenger Phase 5 R2/R3 Suite**:
   Command: `pytest tests/test_challenger_phase5_r2_r3.py -v`
   Result: **24 passed, 3 warnings in 57.47s** (Exit Code: 0).
3. **Challenger Phase 6 M3_2 Adversarial Suite**:
   Command: `pytest tests/test_challenger_phase6_m3_2.py -v`
   Result: **16 passed in 0.63s** (Exit Code: 0).

---

## 2. Logic Chain

1. **RFC 5322 Compliance**:
   - Mail headers without `Date` or `Message-ID` violate RFC 5322 §3.6 and trigger high spam scores in modern MTAs. By formatting `From` and `Reply-To` via `email.utils.formataddr`, adding RFC 2822/5322 `Date` via `email.utils.formatdate`, and generating unique `Message-ID` with domain spec via `email.utils.make_msgid`, outgoing messages satisfy strict deliverability filters.
2. **Anti-Spam Deliverability Heuristics**:
   - Spambots and security gateways flag emails whose subjects contain OTP digits (privacy leak on lockscreen notifications) or ALL-CAPS text (`OTP`, `AI`, `OAUTH`). Replacing them with Title Case `"Smart Home Voice - Mã xác thực tài khoản"` neutralizes SpamAssassin Bayesian triggers.
   - Using multipart/alternative with `text/plain` first and light-background `#ffffff`/`#f8fafc` `text/html` second avoids `MIME_HTML_ONLY` spam penalties and renders cleanly across mobile and desktop clients without deceptive Google OAuth branding flags.
3. **Resilient Scraper Architecture**:
   - The Gmail API search query `q` encompasses multi-language predicates (`xác thực OR OTP OR verification`), preventing missed messages.
   - Base64URL traversal decodes payload text regardless of MIME nesting depth.
   - 3-tier regex ensures that OTP surrounded by context (`Mã xác thực: 123456`) or within `<div id="otp-code-value">` takes strict priority over extraneous 6-digit numbers in the body.

---

## 3. Caveats

- **No live network email dispatch during M3**: All automated test runs verified 100% isolation using mocked SMTP/gws fixtures. Dispatching at most one real verification email to `senat6031@gmail.com` is strictly reserved for Milestone 4 (M4 Acceptance Gate).
- **External CLI dependency**: `read_latest_otp_from_gmail_inbox` relies on `gws` CLI when inspecting real Gmail inbox during manual integration tests; when `gws` is absent in CI/testing, mock isolation gracefully handles inbox responses.

---

## 4. Conclusion

The implementation of Milestone 3 (R3: Email RFC 5322 Standards & Deliverability) in `simulator/auth/invite_and_gmail_mixin.py` and its test suites `tests/test_phase6_r3_rfc5322.py`, `tests/test_phase5_r3_otp_email.py`, and `tests/test_challenger_phase6_m3_2.py`:
- Fully satisfies all requirements in `ORIGINAL_REQUEST.md` and `SCOPE.md`.
- Conforms to RFC 5322, RFC 2046, and RFC 2047 standards.
- Has 0 integrity violations, 0 hardcoded test bypasses, and 0 secret leaks.
- Preserves 100% green test passes across all 99 combined test cases.

**Final Verdict:** **APPROVE**

---

## 5. Verification Method

To independently reproduce this verification:

1. **Verify RFC 5322 & Milestone 1–3 Tests**:
   ```powershell
   pytest tests/test_phase6_r3_rfc5322.py tests/test_phase5_r3_otp_email.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py -v
   ```
   *Expected:* 59 passed.

2. **Verify Adversarial Challenger Suites**:
   ```powershell
   pytest tests/test_challenger_phase5_r2_r3.py -v
   pytest tests/test_challenger_phase6_m3_2.py -v
   ```
   *Expected:* 24 passed and 16 passed.

3. **Verify Line Endings and Encoding**:
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
