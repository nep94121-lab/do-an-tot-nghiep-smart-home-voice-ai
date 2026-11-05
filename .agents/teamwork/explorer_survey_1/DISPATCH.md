## 2026-11-05T05:33:46Z
You are Explorer 1 (survey_exp1), a read-only exploration agent with archetype teamwork_explorer.
Your working directory is: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\explorer_survey_1
You MUST read ORIGINAL_REQUEST.md at: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\ORIGINAL_REQUEST.md before starting work.

Codebase Knowledge Graph Context (codebase-memory-mcp):
- Tier: Tier 2 (Verify)
- Project: C-Users-LENOVO-datn-wt-p6-otp
- Generation: 2026-11-05T03:54:00Z
- Relevant paths:
  * simulator/auth/invite_and_gmail_mixin.py (AuthInviteGmailMixin, email dispatch, SMTP/GWS calls)
  * simulator/api/routes_auth.py (auth routes, /api/auth3/*)
  * tests/conftest.py (pytest fixtures)
  * simulator/data/accounts_3layer.json (seed accounts)
  * simulator/data/family_email_allowlist.json (allowlist data)
  * tests/test_phase5_r3_otp_email.py, tests/test_challenger_phase5_r2_r3.py

Your Mission:
Investigate Requirement R1: Email Allowlist and Test Isolation.
1. Inspect how emails are dispatched in simulator/auth/invite_and_gmail_mixin.py and simulator/api/routes_auth.py.
2. Design a 3-tier protection system ensuring real emails are ONLY ever sent to allowlisted addresses (REAL_EMAIL_ALLOWLIST: nep94121@gmail.com, senat6031@gmail.com, kbanh376@gmail.com, and env REAL_EMAIL_ALLOWLIST). Any attempt to send real email to non-allowlisted addresses (e.g., thanh_vien_chuan@gmail.com, hoc_sinh_moi@gmail.com, tan_binh_gia_dinh@gmail.com) must be rejected or blocked cleanly without bouncing.
3. Inspect tests/conftest.py and design an autouse pytest fixture that mocks smtplib.SMTP, smtplib.SMTP_SSL, and gws subprocess dispatches during all pytest runs to guarantee complete test isolation.
4. Inspect the login gate on / (simulator/static/js/auth.js, simulator/static/js/app.js, simulator/static/index.html) and Playwright 3-roles test flows to ensure login gate dispatches login with send_gmail=False so Playwright tests do not trigger real emails.
5. Inspect simulator/data/accounts_3layer.json and simulator/data/family_email_allowlist.json to verify demo seed accounts and ensure only clean default accounts.
