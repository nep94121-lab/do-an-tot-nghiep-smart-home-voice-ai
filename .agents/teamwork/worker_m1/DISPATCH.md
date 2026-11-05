## 2026-11-05T05:44:46Z

You are Worker M1 (worker_m1), archetype teamwork_worker.
Your working directory is: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\worker_m1
You MUST read ORIGINAL_REQUEST.md at: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\ORIGINAL_REQUEST.md before starting work.
Read Explorer 1's detailed findings and implementation recipe:
- Report: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\explorer_survey_1\survey_report.md
- Handoff: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\explorer_survey_1\handoff.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

File Ownership:
You own exclusively for this milestone:
- simulator/auth/invite_and_gmail_mixin.py
- tests/conftest.py
- simulator/static/js/app.js
- simulator/data/accounts_3layer.json
- simulator/data/family_email_allowlist.json
- tests/test_phase6_r1_allowlist_isolation.py

Mission: Implement Milestone 1 (R1 Email Allowlist & Test Isolation)
1. TDD First: Create tests/test_phase6_r1_allowlist_isolation.py with unit and integration tests verifying:
   - Non-allowlisted emails (thanh_vien_chuan@gmail.com, hoc_sinh_moi@gmail.com, tan_binh_gia_dinh@gmail.com) are rejected immediately by send_real_gmail_otp and send_invite_link_via_gmail with sent_real_gmail=False and blocked_by_allowlist=True without calling SMTP or gws.
   - Allowlisted emails (nep94121@gmail.com, senat6031@gmail.com, kbanh376@gmail.com, or env REAL_EMAIL_ALLOWLIST) pass the allowlist check.
   - Autouse pytest fixture in tests/conftest.py successfully mocks smtplib.SMTP, smtplib.SMTP_SSL, and subprocess.run(["gws", ...]) so no real network sockets are opened during tests.
2. Implement Allowlist Engine in simulator/auth/invite_and_gmail_mixin.py:
   - Define HARDCODED_REAL_EMAIL_ALLOWLIST = {"nep94121@gmail.com", "senat6031@gmail.com", "kbanh376@gmail.com"}.
   - Helper function is_email_allowlisted_for_real_send(email: str) -> bool that parses env REAL_EMAIL_ALLOWLIST and combines with hardcoded set.
   - In send_real_gmail_otp and send_invite_link_via_gmail, gate dispatch: if not allowlisted, return safe blocked response immediately without bounce.
3. Implement tests/conftest.py:
   - Provide @pytest.fixture(autouse=True) mock_email_and_gws_network_isolation(monkeypatch) that intercepts smtplib.SMTP, smtplib.SMTP_SSL, and subprocess.run for "gws".
4. Update simulator/static/js/app.js:
   - In the event listener for #btnSubmitGateLogin (around line 1740-1756), add "send_gmail": false to the fetch body for /api/auth3/layer1_login.
5. Clean Data Fixtures:
   - Restore simulator/data/accounts_3layer.json to the 6 clean default accounts (tuan_anh, thanh_vien_a, thanh_vien_b, khach_c, senat6031, kbanh376) matching simulator/auth/constants_and_crypto.py.
   - Restore simulator/data/family_email_allowlist.json to {} (empty JSON object).
6. Run Verification:
   - Execute: pytest tests/test_phase6_r1_allowlist_isolation.py tests/test_phase5_r3_otp_email.py -v
   - Ensure all tests pass with Exit Code 0.
   - DO NOT read, write, print, or log any SMTP secret values.

Write your handoff report to:
C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\worker_m1\handoff.md
Notify the orchestrator via send_message when complete.
