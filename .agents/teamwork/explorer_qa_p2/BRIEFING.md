# BRIEFING — 2026-11-04T12:37:45Z

## Mission
Survey test suites, fixtures, user accounts, and deployment requirements for Phase 2 UI/UX completion, and produce survey_report.md and handoff.md.

## 🔒 My Identity
- Archetype: explorer
- Roles: QA & Testing Explorer
- Working directory: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\explorer_qa_p2
- Original parent: a6dd1e0f-b843-4477-96f4-146d5c9d3c58
- Milestone: Phase 2 - UI/UX Error Pages, Modals, Mobile App & Role Matrix QA

## 🔒 Key Constraints
- Read-only investigation — do NOT implement source code
- Files for content delivery, Messages for coordination
- Follow Handoff Protocol (Observation, Logic Chain, Caveats, Conclusion, Verification Method)

## Current Parent
- Conversation ID: a6dd1e0f-b843-4477-96f4-146d5c9d3c58
- Updated: 2026-11-04T12:37:45Z

## Investigation State
- **Explored paths**:
  - `tests/` directory (684 tests baseline, DOM tests, devtools tests, bugfix tests)
  - `simulator/auth/constants_and_crypto.py` & `simulator/auth/qr_totp_mixin.py` (3-tier credentials & QR handshake)
  - `simulator/server.py` & `api/index.py` (routes, static mount, 404 handler)
  - `ui_mockups/v2_new_pages/` (13 mockups np_01..08, np_m1..m5)
  - `vercel.json` (routing and error pages configuration)
- **Key findings**:
  - Pytest baseline: 673 passed, 11 failed out of 684. 7 fails due to server on :8088 not running; 4 fails due to engine state pollution in batch run (pass 6/6 in isolation).
  - Credentials & Fixtures: Chủ nhà (`nep94121@gmail.com` / `123456`), Gia đình (`thanhviena.hust@gmail.com` / `GiaDinh@123`), Khách (`khachc.guest@gmail.com` / `Khach@789` + TOTP 10s QR handshake with 180s grace window).
  - DOM tests: 36/36 PASS. Must strictly preserve 103 DOM IDs in `mobile_app/index.html` and 81 DOM IDs in `simulator/static/index.html`.
  - Vercel: Missing `/sw.js` root route, error page routes, and 404 fallback.
- **Unexplored areas**: None for QA survey scope.

## Key Decisions Made
- Authored comprehensive survey_report.md and handoff.md in working directory.

## Artifact Index
- DISPATCH.md — Initial dispatch instructions
- BRIEFING.md — Persistent context & state
- progress.md — Heartbeat and progress log
- survey_report.md — Detailed QA findings & test strategy
- handoff.md — Standard 5-component handoff report
