# BRIEFING — 2026-11-04T19:27:00Z

## Mission
Survey and deep-dive investigate bugs: Bug 1 (credentials/hints cleanup), Bug 2 (logout state reset), Bug 4 (forgot password OTP & seeds), Bug 5 (/auth wizard mock removal & real auth check), Bug 15 (desktop header access time countdown/indicator).

## 🔒 My Identity
- Archetype: explorer
- Roles: survey, analysis, synthesis
- Working directory: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_explorer_survey_1
- Original parent: 4fbd627a-a119-4a5e-84ba-b07fb631efd7
- Milestone: survey_phase_1

## 🔒 Key Constraints
- Read-only investigation — do NOT implement changes in application source code
- Maintain all 68 DOM IDs, window hooks, re-exports
- Zero secrets/passwords exposed in reports or logs
- Line endings UTF-8 LF (0 CRLF)
- Comprehensive root cause tracing with file paths and line numbers
- TDD reproduction test strategies formulated for implementer/tester agents

## Current Parent
- Conversation ID: 4fbd627a-a119-4a5e-84ba-b07fb631efd7
- Updated: 2026-11-04T19:27:00Z

## Investigation State
- **Explored paths**:
  - `simulator/static/index.html`, `simulator/static/js/app.js` (Bugs 1, 2, 4, 15)
  - `mobile_app/index.html`, `simulator/static/js/mobile_app.js` (Bugs 1, 2, 4)
  - `simulator/static/auth.html`, `simulator/static/js/auth.js` (Bugs 1, 5)
  - `simulator/static/logs.html`, `simulator/static/js/logs.js`, `simulator/api/routes_logs.py` (Bug 1)
  - `simulator/auth_3layer.py`, `simulator/auth/constants_and_crypto.py`, `simulator/data/accounts_3layer.json` (Bugs 1, 4, 5)
  - `simulator/api/routes_auth.py`, `simulator/auth/invite_and_gmail_mixin.py` (Bugs 4, 5)
- **Key findings**:
  - Bug 1: Hardcoded `value="..."` in `index.html`, `mobile_app/index.html`, `auth.html`; backend `auth_3layer.py:355` leakes plain password in error; `/logs` returns unsanitized plain password hints.
  - Bug 2: `btnLogoutHome` in `app.js` and `submitMobileLogout` in `mobile_app.js` fail to clear input fields and status messages; desktop header retains visible logout button.
  - Bug 4: Accounts `senat6031@gmail.com` and `kbanh376@gmail.com` missing from `DEFAULT_ACCOUNTS` and `accounts_3layer.json`; `app.js:1612` had `send_gmail: false` and auto-filled OTP; 3-step wizard missing on `/`.
  - Bug 5: `/auth` hardcoded with mock name "Thành viên A" and email overrides; `auth.js` sent `method` instead of `login_method`.
  - Bug 15: Header in `index.html` lacks session duration badge; `app.js` lacked render logic for remaining access time.
- **Unexplored areas**: None for survey subset 1, 2, 4, 5, 15.

## Key Decisions Made
- All root causes confirmed with exact line numbers and code snippets.
- TDD test reproduction strategies established for all 5 bugs without leaking secrets or breaking any DOM IDs.

## Artifact Index
- DISPATCH.md — Initial dispatch log
- progress.md — Liveness heartbeat and step tracking
- BRIEFING.md — Situational awareness
- handoff.md — Comprehensive survey report
