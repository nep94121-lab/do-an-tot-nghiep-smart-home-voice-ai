# BRIEFING — 2026-11-04T13:08:15Z

## Mission
Deliver Milestone M6: Implement 5 error pages, Service Worker (`sw.js`), FastAPI server routes/content negotiation in `simulator/server.py`, and `vercel.json` routing/headers, backed by test suite `tests/test_m6_web_error_sw.py`.

## 🔒 My Identity
- Archetype: worker
- Roles: implementer, qa
- Working directory: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m6
- Original parent: a6dd1e0f-b843-4477-96f4-146d5c9d3c58
- Milestone: M6 (Error Pages, Service Worker, Server Routes & Vercel Config)

## 🔒 Key Constraints
- Responsive styling, dark mode theme matching the design system, Lucide icons, accurate Vietnamese copy.
- SW scope covers `/` and `/app`, network-first for navigation with `/offline.html` fallback, bypass `/api/*` and `/ws`.
- FastAPI custom 404 with content-negotiation (browser vs JSON API).
- No regressions on test_challenger_m4_dom.py and test_phase1_bugfixes_20261104.py.
- Genuine implementation with no dummy/facade shortcuts.

## Current Parent
- Conversation ID: a6dd1e0f-b843-4477-96f4-146d5c9d3c58
- Updated: 2026-11-04T13:08:15Z

## Task Summary
- **What to build**: 5 error pages in `simulator/static/`, `simulator/static/sw.js`, FastAPI route updates in `simulator/server.py`, `vercel.json` additions, test suite in `tests/test_m6_web_error_sw.py`.
- **Success criteria**: All 5 pages match UI mockups; SW handles offline fallback; FastAPI handles 404 content negotiation; pytest passes 100%.

## Key Decisions Made
- Implemented `offline.html` with inline self-contained responsive CSS, Lucide SVG `wifi-off`, automatic `online` event listener, countdown retry timer, and local backup server check.
- Implemented `404.html`, `500.html`, `qr_expired.html`, `403.html` matching `DESIGN_NEW_PAGES.md` and mockups `np_01..05.html`.
- Implemented `simulator/static/sw.js` with network-first navigation handling, offline fallback, cache cleanup on activate, and strict bypass of `/api/*` and `/ws`.
- Registered Service Worker in `simulator/static/index.html` and `mobile_app/index.html` with safe feature detection (`typeof navigator !== "undefined" && "serviceWorker" in navigator`).
- Enhanced `simulator/server.py` with custom 404/Starlette exception handler implementing content negotiation (`text/html` browser navigation gets `404.html`, API and non-HTML get JSON `404`), plus serving `/sw.js` with `Service-Worker-Allowed: /`.
- Updated `vercel.json` with header for `/sw.js` and routes for `/sw.js` and all static error pages.
- Authored test suite `tests/test_m6_web_error_sw.py` with 17 tests covering static files, server routes, content negotiation, and vercel config (100% PASS).

## Change Tracker
- **Files modified**:
  - `simulator/static/offline.html`: Created offline fallback page
  - `simulator/static/404.html`: Created 404 error page
  - `simulator/static/500.html`: Created 500/503 error page
  - `simulator/static/qr_expired.html`: Created QR expired page
  - `simulator/static/403.html`: Created 403 forbidden page
  - `simulator/static/sw.js`: Created Service Worker
  - `simulator/server.py`: Added 404 content-negotiation handler, `/sw.js` and error routes
  - `vercel.json`: Added `/sw.js` header and routes for static error pages
  - `simulator/static/index.html`: Added SW registration script
  - `mobile_app/index.html`: Added SW registration script
  - `tests/test_m6_web_error_sw.py`: Test suite for M6
- **Build status**: PASS
- **Pending issues**: None

## Quality Status
- **Build/test result**: 59/59 tests PASS (36 DOM challenger + 6 Phase 1 bugfixes + 17 M6 web error & SW)
- **Lint status**: Clean (POSIX LF, 0 CRLF, valid JS syntax)
- **Tests added/modified**: 17 tests added in `tests/test_m6_web_error_sw.py`

## Artifact Index
- `.agents/teamwork/worker_m6/DISPATCH.md` — Assigned instructions
- `.agents/teamwork/worker_m6/progress.md` — Liveness & step tracking
- `.agents/teamwork/worker_m6/BRIEFING.md` — Agent working memory
- `.agents/teamwork/worker_m6/handoff.md` — Final handoff report
