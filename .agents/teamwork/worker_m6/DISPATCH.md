## 2026-11-04T12:56:45Z
You are worker_m6. Your working directory is C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m6.
You MUST read:
1. C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md
2. C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\spec_miner_web_p2\survey_report.md
3. C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\PROJECT.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Scope & Tasks for Milestone M6:
1. Implement 5 error pages in `simulator/static/`:
   - `offline.html` (matching `ui_mockups/v2_new_pages/np_01_offline.html`)
   - `404.html` (matching `ui_mockups/v2_new_pages/np_02_404.html`)
   - `500.html` (matching `ui_mockups/v2_new_pages/np_03_500.html`)
   - `qr_expired.html` (matching `ui_mockups/v2_new_pages/np_04_qr_expired.html`)
   - `403.html` (matching `ui_mockups/v2_new_pages/np_05_403.html`)
   Ensure responsive styling, dark mode theme matching the design system, Lucide icons, and accurate Vietnamese copy.
2. Implement Service Worker in `simulator/static/sw.js`:
   - Scope covers `/` and `/app`
   - Cache static assets on install (offline.html, 404.html, 500.html, css, js)
   - Fetch event: handle navigation requests (`request.mode === 'navigate'`) with network-first and fallback to `/offline.html` on network failure.
   - Strictly ignore `/api/*`, `/ws`, and non-GET requests.
3. Update `simulator/server.py`:
   - Add custom 404 exception handler with Content-Negotiation: return `404.html` for browser navigations (`text/html` in Accept and not `/api/*`), while returning JSON 404 for `/api/*` and non-html requests.
   - Add `@app.get("/sw.js")` serving `simulator/static/sw.js` with header `Service-Worker-Allowed: /`.
   - Add routes `/offline`, `/404`, `/500`, `/qr_expired`, `/403` serving respective HTML files.
4. Update `vercel.json`:
   - Add routes and headers for `/sw.js` (`Service-Worker-Allowed: /`) and the static error pages.
5. Verification:
   - Run tests: `python -X utf8 -m pytest tests/test_challenger_m4_dom.py --basetemp=.pytest_tmp`
   - Run tests: `python -X utf8 -m pytest tests/test_phase1_bugfixes_20261104.py --basetemp=.pytest_tmp`
   - Write a dedicated test file `tests/test_m6_web_error_sw.py` verifying 404 content-negotiation (HTML for browser, JSON for /api), sw.js route and header, and error pages existence.
   - Run `python -X utf8 -m pytest tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp` and ensure all tests PASS.
6. Write full handoff report to C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m6\handoff.md with passing build/test evidence and send a message back when done.
