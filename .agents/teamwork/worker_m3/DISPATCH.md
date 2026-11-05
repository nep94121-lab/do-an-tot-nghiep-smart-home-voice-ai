# Dispatch — worker_m3: Milestone 3 (Email RFC 5322 Standards & Deliverability)

**Worker:** `worker_m3` (Archetype: `teamwork_worker`)  
**Assigned Scope:** Milestone 3 (R3: Email RFC 5322 Standards & Deliverability)  
**Parent:** Project Orchestrator (`91485de0-7c6f-449a-ba3f-ed6820ebb01a`)  
**Workspace:** `C:\Users\LENOVO\datn-wt\p6-otp` (Branch: `p6-otp`)  
**Working Directory:** `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\worker_m3`  
**Date:** 2026-11-05T07:16:00Z  

## Mandatory Reading Before Implementation:
1. `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\ORIGINAL_REQUEST.md` (Authoritative User Request)
2. `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\orchestrator\SCOPE.md` (Features 8..11 and M3 Contract)
3. `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\explorer_survey_3\survey_report.md` (Detailed Technical Survey)

## Exclusively Owned Files:
- `simulator/auth/invite_and_gmail_mixin.py`
- `tests/test_phase5_r3_otp_email.py`
- `tests/test_phase6_r3_rfc5322.py`
- `.agents/teamwork/worker_m3/`


## 2026-11-05T07:16:36Z
You are worker_m3 (teamwork_worker).
Your working directory is: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\worker_m3
Your parent orchestrator is: 91485de0-7c6f-449a-ba3f-ed6820ebb01a

MANDATORY READING BEFORE STARTING WORK:
1. C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\ORIGINAL_REQUEST.md
2. C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\orchestrator\SCOPE.md
3. C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\explorer_survey_3\survey_report.md
4. C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\worker_m3\DISPATCH.md

EXCLUSIVE FILE OWNERSHIP:
- simulator/auth/invite_and_gmail_mixin.py
- tests/test_phase5_r3_otp_email.py
- tests/test_phase6_r3_rfc5322.py (new)
- .agents/teamwork/worker_m3/

OBJECTIVE:
Implement Milestone 3 (R3: Email RFC 5322 Standards & Deliverability) following strict TDD:

1. In simulator/auth/invite_and_gmail_mixin.py:
   - Import `email.utils` (formataddr, formatdate, make_msgid).
   - In `send_real_gmail_otp` & `send_invite_link_via_gmail`:
     * Format `From` using `formataddr(('Smart Home Voice AI', sender_addr))`.
     * Format `To` using `formataddr((display_name or actual_to.split('@')[0], actual_to))`.
     * Add `Date` header using `formatdate(localtime=True)` (RFC 5322 §3.6.1).
     * Add `Message-ID` header using `make_msgid(domain=domain)` (RFC 5322 §3.6.4).
     * Add `Reply-To` header using `formataddr(('Smart Home Voice AI', sender_addr))`.
     * Subject lines:
       - For OTP: "Smart Home Voice - Mã xác thực tài khoản" (Title Case, strictly NO OTP digits, NO ALL-CAPS words like 'OTP', 'AI', 'OAUTH', NO emojis).
       - For Invite: "Smart Home Voice - Lời mời đăng ký tài khoản Cấp ..." (strictly NO emojis, NO ALL-CAPS words).
     * MIME Multipart (`alternative`):
       - Attach `text/plain; charset=utf-8` part FIRST (zero emojis, clean plain text).
       - Attach `text/html; charset=utf-8` part SECOND (clean light-background `#ffffff` / `#f8fafc`, clean typography, zero emojis, strictly NO deceptive Google OAuth branding).
   - In `read_latest_otp_from_gmail_inbox`:
     * Update search query `q` to: `'subject:"Smart Home" (xác thực OR OTP OR verification)'`
     * Implement recursive Base64URL payload decoding for nested multipart messages (`payload["parts"]`).
     * Implement 3-tier regex OTP extraction:
       1) Keyword context regex: `(?:OTP[:\s-]*|mã[:\s-]*|code[:\s-]*|xác thực[:\s-]*|xác nhận[:\s-]*)\s*(\d{6})\b`
       2) HTML container regex: `id=["\']otp-code-value["\'][^>]*>(?:OTP:)?\s*(\d{6})<`
       3) Fallback boundary regex: `\b(\d{6})\b`

2. In tests/test_phase6_r3_rfc5322.py and tests/test_phase5_r3_otp_email.py:
   - Follow strict TDD: verify that tests check for RFC 5322 headers, clean Subject, MIME multipart alternative with plain text + light HTML, zero emojis, no deceptive Google OAuth, and robust inbox scraping.

3. CONSTRAINTS & INTEGRITY WARNING:
   > DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
   - ZERO-LEAK: NEVER read, write, print, or log real SMTP secrets (GMAIL_APP_PASSWORD, etc.).
   - All files must be saved as UTF-8 without BOM, 0 CRLF (100% POSIX LF).

4. VERIFICATION:
   - Run tests:
     `pytest tests/test_phase6_r3_rfc5322.py tests/test_phase5_r3_otp_email.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py -v`
     And regression suites.
   - Write comprehensive report to `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\worker_m3\handoff.md`.
   - Send completion message to parent orchestrator via `send_message`.
