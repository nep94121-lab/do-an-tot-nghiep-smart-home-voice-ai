## 2026-11-04T15:26:13Z
You are teamwork_worker assigned to Milestone M11: Vercel Production Routing & Redirection (Requirement R1).

## Mandatory Reading
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md before beginning.
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\explorer_p3_routing_rbac\handoff.md for technical analysis and exact route specifications.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership
You exclusively own:
- `vercel.json`
- `simulator/server.py`
DO NOT modify any other files.

## Detailed Tasks
1. Update `vercel.json`:
   - Add redirect for `/mobile`:
     `{ "src": "^/mobile/?$", "status": 307, "headers": { "Location": "/app" } }`
   - Add route for `/architecture`:
     `{ "src": "^/architecture/?$", "dest": "/docs/kien_truc/smart-home-voice-ai.architecture.html" }`
   - Ensure clean routing and appropriate status codes for error pages:
     `/offline` (200), `/404` (404), `/500` (500), `/403` (403), `/qr_expired` (200), `/sw.js` (headers: `Service-Worker-Allowed: /`, `Cache-Control: no-cache, no-store, must-revalidate`).
   - Add catch-all route at the very end of routes list in `vercel.json`:
     `{ "src": "^/(.*)$", "status": 404, "dest": "/simulator/static/404.html" }`
     so that any non-existent URL renders custom `404.html` instead of Vercel NOT_FOUND.
2. In `simulator/server.py`:
   - Add `@app.get("/mobile")` with `RedirectResponse(url="/app", status_code=307)`.
   - Add `@app.get("/architecture")` serving `docs/kien_truc/smart-home-voice-ai.architecture.html`.
3. Build & Test Verification:
   - Run `python -X utf8 -m pytest tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp`.
   - Delete `.pytest_tmp` after running.
   - Verify formatting: 0 CRLF, UTF-8 without BOM.
4. Produce structured handoff report at:
   `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m11\handoff.md`
   Send a completion message back when done.
