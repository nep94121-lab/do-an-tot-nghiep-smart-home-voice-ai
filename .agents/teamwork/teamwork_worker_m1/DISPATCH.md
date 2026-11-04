## 2026-11-04T19:29:16Z
Caller: 4fbd627a-a119-4a5e-84ba-b07fb631efd7
Working directory: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_worker_m1\
Project root: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY FIRST STEP:
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md
Also read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\orchestrator_phase4\PROJECT.md
Read the detailed survey report: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_explorer_survey_1\handoff.md

Your mission is Milestone 1 (Bugs 1, 2, 4, 5, 15 from REAL_TEST_BUGS_20261105.md):
- Bug 1: Remove prefilled credentials and password hints from UI (/, /app, /auth), mask passwords in /logs display and error messages.
- Bug 2: Proper logout reset on / and /app (clear input fields, clear gateStatusBox, clear session cookie/storage, hide logout button, reset badge).
- Bug 4: Forgot password via OTP: add senat6031@gmail.com (tier 2 family) and kbanh376@gmail.com (tier 3 guest) to seed accounts (hash PBKDF2), send real Gmail/SMTP (send_gmail: true, stop auto-fill OTP), split UI into 3 steps (Email -> OTP -> New password).
- Bug 5: Clean voice auth wizard (/auth): remove sample member data, fix login check with real accounts (login_method parameter & error handling).
- Bug 15: Desktop header: add #homeSessionDurationBadge displaying remaining access duration ("Không giới hạn" for owner, "Còn 30 ngày" for family, actual validity for guest; hide on logout).

Strict TDD Cycle:
1. Write automated reproduction test suite: tests/test_p4_survey1_security_auth.py covering all 5 bugs.
2. Execute: python -X utf8 -m pytest tests/test_p4_survey1_security_auth.py --basetemp=.pytest_tmp and record evidence that tests FAIL before fix.
3. Implement genuine code fixes in owned files:
   - simulator/static/index.html
   - mobile_app/index.html
   - simulator/static/auth.html
   - simulator/static/js/auth.js
   - simulator/static/js/app.js
   - simulator/static/js/mobile_app.js
   - simulator/auth/constants_and_crypto.py
   - simulator/data/accounts_3layer.json
   - simulator/auth_3layer.py
   - simulator/api/routes_logs.py
   - simulator/static/js/logs.js
4. Execute: python -X utf8 -m pytest tests/test_p4_survey1_security_auth.py --basetemp=.pytest_tmp and verify all tests PASS.
5. Regression test: python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_m3_challenger_api.py tests/test_p3_session_rbac_concurrency.py --basetemp=.pytest_tmp.
6. Clean up .pytest_tmp.
7. Constraints: preserve all 68 DOM IDs, window hooks, re-exports, zero plaintext passwords in logs or code, UTF-8 LF (0 CRLF).
8. Write comprehensive handoff to C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_worker_m1\handoff.md and send message to caller.

## 2026-11-04T19:54:12Z
Caller: 4fbd627a-a119-4a5e-84ba-b07fb631efd7
**Context**: Milestone 1 Bugfix (Bugs 1, 2, 4, 5, 15)
**Content**: Heartbeat status check: How is the implementation and verification progress? Have you finished applying fixes and running the test suite?
**Action**: Please update progress.md or send your status/handoff report.
