# BRIEFING — 2026-11-04T12:38:00Z

## Mission
Survey specifications and source files for Web error pages (offline + sw.js, 404, 500/503, QR expired, 403) and Modals/Banners (lockdown modal, mic permission modal, WebSocket reconnect banner).

## 🔒 My Identity
- Archetype: Specification Miner
- Roles: External domain expert / Specification probe
- Working directory: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\spec_miner_web_p2
- Original parent: a6dd1e0f-b843-4477-96f4-146d5c9d3c58
- Milestone: Web Error Pages, Modals, Banners & Service Worker Specification Survey

## 🔒 Key Constraints
- Read-only probe: Do NOT implement anything.
- Probe authoritative sources: UI mockups, DESIGN_NEW_PAGES.md, simulator/server.py, static assets.
- FastAPI 404 handler must return HTML only for browser navigations (Accept: text/html), while preserving JSON 404 for /api/*.
- Service worker (sw.js) caching strategy and offline fallback.
- Preserving existing DOM IDs and window.* hooks in simulator/static/index.html, simulator/static/guest_enroll.html, simulator/static/auth.html, mobile_app/index.html.
- Do NOT touch or break house3d.js or Toàn cảnh layout.
- Output report in C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\spec_miner_web_p2\survey_report.md
- Output handoff in C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\spec_miner_web_p2\handoff.md

## Current Parent
- Conversation ID: a6dd1e0f-b843-4477-96f4-146d5c9d3c58
- Updated: 2026-11-04T12:38:00Z

## Task Summary
- **What to build**: Specification discovery report and handoff for error pages, modals, banners, sw.js, and server routing.
- **Success criteria**: Full feature enumeration, inputs, outputs, error behaviors, edge cases, DOM/JS interface contracts, and layout preservation rules.
- **Interface contracts**: ui_mockups/v2_new_pages/DESIGN_NEW_PAGES.md, HTML mockups, simulator/server.py
- **Code layout**: simulator/server.py, simulator/static/

## Key Decisions Made
- Fully probed 8 HTML mockups in `ui_mockups/v2_new_pages/` (`np_01` to `np_08`) and `DESIGN_NEW_PAGES.md`.
- Empirically verified current FastAPI 404 behavior: returns `application/json` for browser navigations; demonstrated need for custom exception handler with Content Negotiation.
- Verified test suite pass rate: 36 passed in `test_challenger_m4_dom.py`, 20 passed in `test_challenger_m3_stress_dom_raycaster.py`, 6 passed in `test_phase1_bugfixes_20261104.py`.
- Catalogued complete DOM ID and `window.*` preservation registries to safeguard tests from regressions.
- Detailed sw.js precaching, network-first navigate strategy, and non-GET / API bypass rules.
- Wrote exhaustive `survey_report.md` and 5-component `handoff.md`.

## Artifact Index
- survey_report.md — Comprehensive specification survey
- handoff.md — 5-component handoff report
