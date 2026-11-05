# BRIEFING — 2026-11-05T05:43:00Z

## Mission
Investigate Requirement R1: Email Allowlist and Test Isolation in p6-otp workspace.

## 🔒 My Identity
- Archetype: teamwork_explorer
- Roles: Explorer 1 (survey_exp1)
- Working directory: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\explorer_survey_1
- Original parent: 91485de0-7c6f-449a-ba3f-ed6820ebb01a
- Milestone: Phase 6 R1 Investigation

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- DO NOT edit or create any production code or test files
- DO NOT read, write, or print SMTP secret values
- DO NOT send real emails to addresses outside REAL_EMAIL_ALLOWLIST
- Use codebase-memory-mcp where applicable
- Produce survey_report.md and handoff.md, heartbeat via progress.md

## Current Parent
- Conversation ID: 91485de0-7c6f-449a-ba3f-ed6820ebb01a
- Updated: 2026-11-05T05:43:00Z

## Investigation State
- **Explored paths**:
  * simulator/auth/invite_and_gmail_mixin.py (lines 503-773: send_invite_link_via_gmail, send_real_gmail_otp, read_latest_otp_from_gmail_inbox)
  * simulator/api/routes_auth.py (lines 48-58, 528-579, 653-664: send_invite_email, layer1_login, forgot_password_send_otp)
  * simulator/auth_3layer.py (lines 264-449, 545-615: layer1_login, request_password_reset_otp)
  * tests/conftest.py (verified non-existent, designed autouse fixture)
  * simulator/static/js/app.js (lines 1739-1781: btnSubmitGateLogin missing send_gmail: false)
  * simulator/static/js/auth.js (lines 675-700: submitLayer1 missing send_gmail: false)
  * simulator/static/index.html (lines 277-312: gatePanelLogin modal and form structure)
  * tests/test_playwright_3roles_live.py (lines 38-42, 80-84, 122-126: clicks btnSubmitGateLogin triggering real email)
  * simulator/data/accounts_3layer.json & simulator/data/family_email_allowlist.json (found 12 and 10 polluted test records)
  * simulator/auth/constants_and_crypto.py (lines 50-248: 6 clean default seed accounts)
- **Key findings**:
  1. `send_real_gmail_otp` lacks canonical allowlist verification; sends real mail to unapproved test addresses.
  2. `send_invite_link_via_gmail` has zero allowlist check; calls `gws` directly.
  3. No root `tests/conftest.py` exists; an `autouse=True` fixture is needed to mock `smtplib` and `gws` across all tests.
  4. Login gate on `/` doesn't pass `send_gmail: false`, triggering real emails during Playwright test runs.
  5. Seed account data files are polluted from previous tests; need cleanup to standard 6 default accounts and empty allowlist `{}`.
- **Unexplored areas**: None for R1 scope.

## Key Decisions Made
- Designed comprehensive 3-tier protection system (Tier 1: Canonical Allowlist, Tier 2: Non-bounce Dispatch Gate, Tier 3: Test & UI Isolation).
- Compiled exhaustive survey report in survey_report.md and 5-component handoff report in handoff.md.

## Artifact Index
- [ORIGINAL_REQUEST.md](file:///C:/Users/LENOVO/datn-wt/p6-otp/.agents/teamwork/ORIGINAL_REQUEST.md) — Requirement details
- [DISPATCH.md](file:///C:/Users/LENOVO/datn-wt/p6-otp/.agents/teamwork/explorer_survey_1/DISPATCH.md) — Dispatch message log
- [progress.md](file:///C:/Users/LENOVO/datn-wt/p6-otp/.agents/teamwork/explorer_survey_1/progress.md) — Heartbeat liveness
- [BRIEFING.md](file:///C:/Users/LENOVO/datn-wt/p6-otp/.agents/teamwork/explorer_survey_1/BRIEFING.md) — Persistent memory
- [survey_report.md](file:///C:/Users/LENOVO/datn-wt/p6-otp/.agents/teamwork/explorer_survey_1/survey_report.md) — Comprehensive R1 survey report
- [handoff.md](file:///C:/Users/LENOVO/datn-wt/p6-otp/.agents/teamwork/explorer_survey_1/handoff.md) — 5-component handoff report
