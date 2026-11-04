# BRIEFING — 2026-11-04T19:56:00Z

## Mission
Milestone 1: Fix security & auth bugs (Bugs 1, 2, 4, 5, 15) using strict TDD cycle, genuine implementations, zero cheating.

## 🔒 My Identity
- Archetype: implementer / qa
- Roles: implementer, qa
- Working directory: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_worker_m1\
- Original parent: 4fbd627a-a119-4a5e-84ba-b07fb631efd7
- Milestone: Milestone 1 (Bugs 1, 2, 4, 5, 15)

## 🔒 Key Constraints
- Preserve all 68 DOM IDs, window hooks, re-exports.
- Zero plaintext passwords in logs or code.
- UTF-8 LF line endings (0 CRLF).
- Strict TDD: reproduction tests FAIL first, then PASS after genuine fix.
- No dummy/facade implementations, no hardcoded test expectations.
- Regression tests must pass: test_challenger_m4_dom.py, test_m3_challenger_api.py, test_p3_session_rbac_concurrency.py.

## Current Parent
- Conversation ID: 4fbd627a-a119-4a5e-84ba-b07fb631efd7
- Updated: 2026-11-04T19:56:00Z

## Task Summary
- **What to build**:
  - Bug 1: Remove prefilled credentials and password hints from UI (/, /app, /auth), mask passwords in /logs and error messages.
  - Bug 2: Proper logout reset on / and /app (inputs, gateStatusBox, session cookie/storage, logout button hidden, badge reset).
  - Bug 4: Forgot password via OTP: seed accounts senat6031@gmail.com (family) & kbanh376@gmail.com (guest) with PBKDF2 hash, real SMTP email (send_gmail: true, stop auto-fill OTP), split UI into 3 steps (Email -> OTP -> New password).
  - Bug 5: Clean voice auth wizard (/auth): remove sample member data, fix login check with real accounts (login_method parameter & error handling).
  - Bug 15: Desktop header: add #homeSessionDurationBadge displaying remaining access duration ("Không giới hạn" for owner, "Còn 30 ngày" for family, actual validity for guest; hide on logout).
- **Success criteria**: All tests in `tests/test_p4_survey1_security_auth.py` (14/14) and regression test suites pass cleanly.
- **Interface contracts**: PROJECT.md, survey report handoff.md
- **Code layout**: Simulator & mobile app frontends + backend auth/logs routes.

## Change Tracker
- **Files modified**:
  - `simulator/static/index.html`: added `#homeSessionDurationBadge`, removed prefilled inputs, split forgot password into 3 step containers.
  - `mobile_app/index.html`: removed prefilled inputs.
  - `simulator/static/auth.html`: removed sample member data and hints while preserving DOM IDs.
  - `simulator/static/js/auth.js`: cleaned member selection, added login_method, removed OTP preview auto-fill.
  - `simulator/static/js/app.js`: added duration badge logic, clearAuthState on logout, 3-step navigation, send_gmail: true.
  - `simulator/static/js/mobile_app.js`: input cleanup on mobile logout.
  - `simulator/auth/constants_and_crypto.py`: added seed accounts with PBKDF2 hash.
  - `simulator/data/accounts_3layer.json`: added seed accounts with PBKDF2 hash.
  - `simulator/auth_3layer.py`: removed password hints from layer1_login failure.
  - `simulator/api/routes_logs.py`: added mask_sensitive_log_data() for password hint masking.
  - `simulator/static/js/logs.js`: added maskSensitiveLogText() for password hint masking.
  - `tests/test_p4_survey1_security_auth.py`: new 14-test TDD suite covering all 5 bugs.
  - `tests/test_p3_session_rbac_concurrency.py`: reset _explicit_test_user_set in autouse fixture.
- **Build status**: 14/14 TDD tests PASS, 58/58 regression tests PASS (Total: 72/72 PASS).
- **Pending issues**: None

## Quality Status
- **Build/test result**: PASS (72 passed in 19.91s)
- **Lint status**: 0 violations, 100% LF (0 CRLF), UTF-8 without BOM.
- **Tests added/modified**: `tests/test_p4_survey1_security_auth.py` (14 tests added)

## Loaded Skills
- None explicitly requested to load locally.
