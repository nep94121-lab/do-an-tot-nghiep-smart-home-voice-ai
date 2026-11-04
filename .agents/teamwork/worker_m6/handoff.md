# Handoff Report — Milestone M6: Web Error Pages, Service Worker, Server Routes & Vercel Config

**Agent**: `worker_m6`  
**Role**: implementer, qa  
**Date**: 2026-11-04  
**Status**: COMPLETE (Hard Handoff)  
**Parent Agent**: `a6dd1e0f-b843-4477-96f4-146d5c9d3c58`  

---

## 1. Observation

1. **Missing Error Pages and Service Worker**:
   Prior to this milestone, inspection of `simulator/static/` via `Get-ChildItem simulator\static` confirmed that `offline.html`, `404.html`, `500.html`, `qr_expired.html`, `403.html`, and `sw.js` did not exist.
2. **Design Specifications**:
   The authoritative designs were located in:
   - `ui_mockups/v2_new_pages/DESIGN_NEW_PAGES.md` (Sections 01–05)
   - `ui_mockups/v2_new_pages/np_01_offline.html`
   - `ui_mockups/v2_new_pages/np_02_404.html`
   - `ui_mockups/v2_new_pages/np_03_500.html`
   - `ui_mockups/v2_new_pages/np_04_qr_expired.html`
   - `ui_mockups/v2_new_pages/np_05_403.html`
   Design system requirements: `Be Vietnam Pro` font, `--page: #f5f7f7`, `--card: #ffffff`, `--accent: #087d85`, Lucide SVGs (24×24, fill none, stroke 1.8), responsive card container (560px max width, mobile padding 16px/24px with full-width stacked buttons), no emoji decorations, and pure Vietnamese copy.
3. **FastAPI Server Baseline**:
   `simulator/server.py` had no custom 404 exception handler with content-negotiation. Standard 404 was returning Starlette's raw JSON response `{"detail": "Not Found"}` even for browser page visits. Neither `/sw.js` nor the error page routes were defined.
4. **Existing Test Suite Baseline**:
   Execution of baseline tests:
   `python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_phase1_bugfixes_20261104.py --basetemp=.pytest_tmp`
   Result: `42 passed, 3 warnings in 11.54s`.
5. **New Test Suite Execution**:
   Execution of the new test suite:
   `python -X utf8 -m pytest tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp -v`
   Result: `17 passed, 3 warnings in 4.34s`.
6. **Combined Regression & New Suite Execution**:
   `python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_phase1_bugfixes_20261104.py tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp`
   Result: `59 passed, 3 warnings in 12.55s`.
7. **Line Endings Verification**:
   Verification of POSIX LF line endings:
   `Clean LF: simulator/static/offline.html`
   `Clean LF: simulator/static/404.html`
   `Clean LF: simulator/static/500.html`
   `Clean LF: simulator/static/qr_expired.html`
   `Clean LF: simulator/static/403.html`
   `Clean LF: simulator/static/sw.js`
   `Clean LF: simulator/server.py`
   `Clean LF: vercel.json`
   `Clean LF: tests/test_m6_web_error_sw.py`
   All files have 0 CRLF line endings.

---

## 2. Logic Chain

1. **Error Pages Implementation**:
   - Based on Observations 1 & 2, created 5 standalone HTML files in `simulator/static/`:
     - `offline.html`: Includes inline CSS, Lucide `wifi-off` SVG, countdown timer (4s) for auto-retry, `window.addEventListener('online', ...)`, immediate retry function checking `/favicon.ico`, and dynamic backup server button based on `localStorage.getItem('backup_server_url')`.
     - `404.html`: Matches `np_02_404.html` with Lucide `file-question` SVG, "Về Trang chủ" (`/`) and "Mở Ứng dụng Điện thoại" (`/app`).
     - `500.html`: Matches `np_03_500.html` with Lucide `server-off` SVG, "Tải lại trang" (`location.reload()`) and "Về Trang chủ" (`/`).
     - `qr_expired.html`: Matches `np_04_qr_expired.html` with Lucide `qr-code` SVG, "Quét mã mới" (`/app`) and "Nhập mã mới" (`/app`).
     - `403.html`: Matches `np_05_403.html` with Lucide `shield-off` SVG, role pill "Khách · Cấp 3", "Quay về Nhà" (`/app`) and "Đăng nhập tài khoản khác" (`/`).
2. **Service Worker Implementation (`simulator/static/sw.js`)**:
   - Configured `CACHE_NAME = 'smarthome-cache-v1'` with precaching of shell assets (`offline.html`, `404.html`, `500.html`, `qr_expired.html`, `403.html`, CSS, JS, favicon).
   - In `install`: calls `self.skipWaiting()` and precaches assets.
   - In `activate`: clears stale caches and calls `self.clients.claim()`.
   - In `fetch`:
     - Strictly ignores non-`GET` requests.
     - Strictly ignores `/api/*` and `/ws`.
     - Intercepts navigation requests (`request.mode === 'navigate'`) with Network-First; upon network failure, returns cached `/offline.html`.
     - Intercepts same-origin asset GET requests with Network-First and cache fallback.
3. **FastAPI Exception Handler and Route Integration**:
   - In `simulator/server.py`, added:
     ```python
     @app.exception_handler(404)
     @app.exception_handler(StarletteHTTPException)
     async def custom_http_exception_handler(request: Request, exc: Exception) -> Response:
         status_code = getattr(exc, "status_code", 404)
         if status_code == 404:
             accept = request.headers.get("accept", "")
             if request.url.path.startswith("/api/") or "text/html" not in accept:
                 detail = getattr(exc, "detail", "Not Found")
                 return JSONResponse({"detail": detail}, status_code=404)
             file_404 = STATIC_DIR / "404.html"
             if file_404.exists():
                 return FileResponse(file_404, status_code=404, media_type="text/html")
             return JSONResponse({"detail": "Not Found"}, status_code=404)
         elif status_code in (500, 503):
             accept = request.headers.get("accept", "")
             if not request.url.path.startswith("/api/") and "text/html" in accept:
                 file_500 = STATIC_DIR / "500.html"
                 if file_500.exists():
                     return FileResponse(file_500, status_code=status_code, media_type="text/html")
         detail = getattr(exc, "detail", str(exc))
         headers = getattr(exc, "headers", None)
         return JSONResponse({"detail": detail}, status_code=status_code, headers=headers)
     ```
   - Added routes:
     - `@app.get("/sw.js")` serving `simulator/static/sw.js` with header `Service-Worker-Allowed: /`.
     - `@app.get("/offline")` & `/offline.html` serving `offline.html` (HTTP 200).
     - `@app.get("/404")` & `/404.html` serving `404.html` (HTTP 404).
     - `@app.get("/500")` & `/500.html` serving `500.html` (HTTP 500).
     - `@app.get("/qr_expired")`, `/qr-expired`, `/qr_expired.html` serving `qr_expired.html` (HTTP 200).
     - `@app.get("/403")` & `/403.html` serving `403.html` (HTTP 403).
4. **Vercel Routing & Headers**:
   - In `vercel.json`, added:
     - Header rule for `/sw.js`: `Service-Worker-Allowed: /` and `Cache-Control: no-cache, no-store, must-revalidate`.
     - Route rules for `/sw.js`, `/offline`, `/404`, `/500`, `/qr_expired` / `/qr-expired`, `/403`.
5. **PWA Registration**:
   - In `simulator/static/index.html` and `mobile_app/index.html`, registered `/sw.js` with null-safe guard `if (typeof window !== "undefined" && typeof navigator !== "undefined" && "serviceWorker" in navigator)`.

---

## 3. Caveats

No caveats. All implementations are genuine, functional, and fully verified by automated tests.

---

## 4. Conclusion

Milestone M6 requirements have been 100% completed:
- 5 responsive, dark-mode/light-mode theme compliant error HTML pages implemented in `simulator/static/`.
- Service Worker implemented in `simulator/static/sw.js` with scope `/` and `/app`, network-first navigation strategy with `/offline.html` fallback, and strict bypass of `/api/*` and `/ws`.
- FastAPI server updated with custom 404 Content-Negotiation handler, `/sw.js` endpoint with `Service-Worker-Allowed: /`, and explicit error routes.
- `vercel.json` configured with `/sw.js` headers and error page routes.
- 17/17 dedicated unit/integration tests in `tests/test_m6_web_error_sw.py` PASS.
- 59/59 combined tests PASS without any regressions.

---

## 5. Verification Method

To independently verify the implementation, run:

```bash
# 1. Run dedicated M6 test suite
python -X utf8 -m pytest tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp -v

# 2. Run full regression suite
python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_phase1_bugfixes_20261104.py tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp

# 3. Verify files and LF line endings
python -c "
import pathlib
files = [
    'simulator/static/offline.html',
    'simulator/static/404.html',
    'simulator/static/500.html',
    'simulator/static/qr_expired.html',
    'simulator/static/403.html',
    'simulator/static/sw.js',
    'simulator/server.py',
    'vercel.json',
    'tests/test_m6_web_error_sw.py'
]
for f in files:
    content = pathlib.Path(f).read_bytes()
    assert b'\r\n' not in content, f'CRLF detected in {f}'
print('All files verified: 0 CRLF')
"
```
