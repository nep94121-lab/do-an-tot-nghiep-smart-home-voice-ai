## 2026-11-04T15:35:05Z
You are teamwork_reviewer assigned to independently review Milestone M11: Vercel Production Routing & Redirection.

## Mandatory Reading
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md.
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m11\handoff.md.

## Working Directory
C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\reviewer_m11_2\

## Review Scope
- Independently examine `vercel.json` and `simulator/server.py`.
- Verify that Vercel routes don't shadow API routes (`/api/*`) or static routes.
- Verify that FastAPI routes in `simulator/server.py` match `vercel.json`.
- Test using FastAPI TestClient:
  `python -c "from fastapi.testclient import TestClient; from simulator.server import app; c = TestClient(app); r = c.get('/mobile', follow_redirects=False); assert r.status_code == 307 and r.headers['location'] == '/app'; r2 = c.get('/architecture'); assert r2.status_code == 200; print('M11 Independent Review PASS')"`
- Run tests: `python -X utf8 -m pytest tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp`. Clean up `.pytest_tmp`.
- Check formatting: 0 CRLF, UTF-8 no BOM.
- Explicitly state your verdict in `handoff.md`: APPROVE or REQUEST_CHANGES.
Send a completion message back when done.
