## 2026-11-04T15:35:03Z

You are teamwork_reviewer assigned to review Milestone M11: Vercel Production Routing & Redirection.

## Mandatory Reading
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md.
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m11\handoff.md.

## Working Directory
C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\reviewer_m11_1\

## Review Scope
- Inspect `vercel.json` and `simulator/server.py`.
- Verify:
  1. `/mobile` correctly redirects to `/app` (HTTP 307 status).
  2. `/architecture` serves `/docs/kien_truc/smart-home-voice-ai.architecture.html`.
  3. Status codes and destinations for `/offline`, `/404`, `/500`, `/403`, `/qr_expired`, `/sw.js`.
  4. Catch-all fallback at bottom of `vercel.json`: `^/(.*)$ -> status 404, dest /simulator/static/404.html`.
- Run tests: `python -X utf8 -m pytest tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp`. Clean up `.pytest_tmp`.
- Check formatting: 0 CRLF, UTF-8 no BOM.
- Explicitly state your verdict in `handoff.md`: APPROVE or REQUEST_CHANGES.
Send a completion message back when done.
