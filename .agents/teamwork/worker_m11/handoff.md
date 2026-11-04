# BÁO CÁO BÀN GIAO: MILESTONE M11 — VERCEL PRODUCTION ROUTING & REDIRECTION (REQUIREMENT R1)

- **Người thực hiện**: `teamwork_worker` (worker_m11 - Implementer / QA)
- **Parent Agent ID**: `39d935a1-0551-429d-ac45-c89f1e361ad0`
- **Thời gian hoàn thành**: 2026-11-04T15:33:00Z
- **Loại bàn giao**: Hard Handoff (Hoàn tất 100% Milestone M11, đã kiểm chứng độc lập)

---

## 1. Observation (Quan sát & Thực nghiệm)

1. **Khảo sát hiện trạng trước khi sửa**:
   - `vercel.json` thiếu route cho `/mobile` (dẫn tới 404 NOT_FOUND trên Vercel Edge).
   - `vercel.json` thiếu route cho `/architecture` (chỉ có `/archify`).
   - `vercel.json` thiếu cấu hình status code chuẩn (`status: 404`, `status: 500`, `status: 403`) và thiếu catch-all route `^/(.*)$ -> /simulator/static/404.html` ở cuối, khiến URL không tồn tại bị trả về HTML 404 thô của Vercel (`len=79 bytes`) thay vì trang `404.html` tùy biến.
   - `simulator/server.py` thiếu endpoint `@app.get("/mobile")` và `@app.get("/architecture")`.
2. **Quyền sở hữu tệp (Write Ownership)**:
   - Chỉ chỉnh sửa đúng 2 tệp được phân công:
     - `vercel.json`
     - `simulator/server.py`
   - Các tệp báo cáo/tiến độ được ghi trong thư mục độc quyền `.agents/teamwork/worker_m11/`.
3. **Kết quả kiểm tra định dạng và chuẩn mã hóa**:
   - `vercel.json`: CRLF=0, LF=38, BOM=False (Chuẩn Unix LF, UTF-8 không BOM).
   - `simulator/server.py`: CRLF=0, LF=261, BOM=False (Chuẩn Unix LF, UTF-8 không BOM).
4. **Kết quả kiểm thử pytest `tests/test_m6_web_error_sw.py`**:
   - 17/17 tests passed 100% trong 8.78s.
   - Thư mục `.pytest_tmp` đã được dọn dẹp sạch sẽ sau khi chạy.

---

## 2. Logic Chain (Chuỗi suy luận & Các bước triển khai)

1. **Bước 1 — Cập nhật cấu hình định tuyến Vercel (`vercel.json`)**:
   - Bổ sung quy tắc chuyển hướng 307 cho `/mobile`:
     `{ "src": "^/mobile/?$", "status": 307, "headers": { "Location": "/app" } }`
   - Bổ sung route cho `/architecture`:
     `{ "src": "^/architecture/?$", "dest": "/docs/kien_truc/smart-home-voice-ai.architecture.html" }`
   - Chuẩn hóa header cho Service Worker `/sw.js`:
     `"headers": { "Service-Worker-Allowed": "/", "Cache-Control": "no-cache, no-store, must-revalidate" }`
   - Chuẩn hóa HTTP status codes cho các trang lỗi:
     - `/offline`: 200 OK (`dest: /simulator/static/offline.html`, status 200)
     - `/404`: 404 Not Found (`dest: /simulator/static/404.html`, status 404)
     - `/500`: 500 Internal Server Error (`dest: /simulator/static/500.html`, status 500)
     - `/403`: 403 Forbidden (`dest: /simulator/static/403.html`, status 403)
     - `/qr_expired`: 200 OK (`dest: /simulator/static/qr_expired.html`, status 200)
   - Bổ sung quy tắc bắt cuối (catch-all) ở cuối danh sách routes:
     `{ "src": "^/(.*)$", "status": 404, "dest": "/simulator/static/404.html" }`
     đảm bảo mọi URL không tồn tại đều được định tuyến về `404.html` tùy biến với HTTP status code 404 thay vì màn hình lỗi Vercel mặc định.

2. **Bước 2 — Cập nhật backend FastAPI (`simulator/server.py`)**:
   - Import `RedirectResponse` từ `fastapi.responses`.
   - Thêm route `@app.get("/mobile")`:
     ```python
     @app.get("/mobile")
     async def mobile_redirect() -> RedirectResponse:
         """Chuyển hướng 307 từ /mobile về ứng dụng /app."""
         return RedirectResponse(url="/app", status_code=307)
     ```
   - Thêm route `@app.get("/architecture")`:
     ```python
     @app.get("/architecture")
     async def architecture_page() -> FileResponse:
         """Trang Sơ đồ Kiến trúc Hệ thống tương tác (Archify)."""
         return FileResponse(DOCS_ARCH_DIR / "smart-home-voice-ai.architecture.html")
     ```

3. **Bước 3 — Kiểm chứng đa góc độ (Orthogonal Verification)**:
   - Chạy TestClient độc lập kiểm tra:
     - `GET /mobile` trả về `307 Temporary Redirect` với `location: /app`.
     - `GET /mobile` (follow redirect) trả về `200 OK` (nội dung `mobile_app/index.html`).
     - `GET /architecture` trả về `200 OK` với nội dung sơ đồ kiến trúc Archify.
   - Chạy toàn bộ test suite M6 `tests/test_m6_web_error_sw.py`: 17 passed.

---

## 3. Caveats (Lưu ý)

- Khi Vercel build và deploy, thay đổi trong `vercel.json` sẽ có hiệu lực trực tiếp trên domain production `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`.
- Lệnh deploy Vercel và kiểm tra curl trên production thuộc phạm vi nhiệm vụ R6 (giai đoạn sau khi toàn bộ workers hội tụ).

---

## 4. Conclusion (Kết luận)

- Yêu cầu R1 (Vercel Production Routing & Redirection) thuộc Milestone M11 đã được hoàn thành 100%, tuân thủ nghiêm ngặt nguyên tắc thay đổi tối thiểu, không có code giả lập (facade), không vi phạm quyền sở hữu tệp.
- Tất cả các URL `/mobile`, `/architecture`, `/offline`, `/404`, `/500`, `/403`, `/qr_expired`, `/sw.js` và catch-all fallback 404 đều đã được định tuyến chính xác trong `vercel.json` và `simulator/server.py`.

---

## 5. Verification Method (Phương pháp Kiểm chứng Độc lập)

Các lệnh thực thi kiểm chứng độc lập:

1. **Kiểm tra cú pháp JSON và các route trong `vercel.json`**:
   ```powershell
   python -c "import json; d = json.load(open('vercel.json', encoding='utf-8')); assert any(r.get('status') == 307 and r.get('src') == '^/mobile/?$' for r in d['routes']); assert any(r.get('dest') == '/docs/kien_truc/smart-home-voice-ai.architecture.html' and r.get('src') == '^/architecture/?$' for r in d['routes']); assert d['routes'][-1]['src'] == '^/(.*)$' and d['routes'][-1]['status'] == 404; print('vercel.json verification PASSED')"
   ```

2. **Kiểm tra TestClient FastAPI đối với `/mobile` và `/architecture`**:
   ```powershell
   python -c "from starlette.testclient import TestClient; from simulator.server import app; c = TestClient(app); r = c.get('/mobile', follow_redirects=False); assert r.status_code == 307 and r.headers['location'] == '/app'; r2 = c.get('/architecture'); assert r2.status_code == 200 and 'archify' in r2.text; print('FastAPI endpoints verification PASSED')"
   ```

3. **Chạy bộ kiểm thử M6**:
   ```powershell
   python -X utf8 -m pytest tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp
   powershell -Command "if (Test-Path '.pytest_tmp') { Remove-Item -Recurse -Force '.pytest_tmp' }"
   ```

4. **Kiểm tra chuẩn định dạng (0 CRLF, UTF-8 không BOM)**:
   ```powershell
   python -c "for f in ['vercel.json', 'simulator/server.py']: raw = open(f, 'rb').read(); assert raw.count(b'\r\n') == 0; assert not raw.startswith(b'\xef\xbb\xbf'); print(f, '0 CRLF & UTF-8 no BOM: PASSED')"
   ```
