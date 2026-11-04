# BÁO CÁO THẨM ĐỊNH ĐỘC LẬP: MILESTONE M11 — VERCEL PRODUCTION ROUTING & REDIRECTION

- **Reviewer**: `teamwork_reviewer` (reviewer_m11_2 - Reviewer & Adversarial Critic)
- **Parent Agent ID**: `39d935a1-0551-429d-ac45-c89f1e361ad0`
- **Thời gian hoàn thành**: 2026-11-04T15:39:45Z
- **Loại bàn giao**: Hard Handoff
- **Phán quyết (Verdict)**: **APPROVE**

---

## 1. Observation (Quan sát & Thực nghiệm Độc lập)

1. **Khảo sát cấu hình `vercel.json`**:
   - `vercel.json:15`: Quy tắc `{ "src": "^/api/(.*)$", "dest": "/api/index.py" }` nằm ở đầu mảng `routes`, đảm bảo không có route tĩnh hoặc route chuyển hướng nào che khuất (shadow) các API endpoints.
   - `vercel.json:16`: Route `{ "src": "^/mobile/?$", "status": 307, "headers": { "Location": "/app" } }` chuyển hướng chuẩn 307 về `/app`.
   - `vercel.json:17`: Route Service Worker `/sw.js` có header `Service-Worker-Allowed: /` và `Cache-Control: no-cache, no-store, must-revalidate`.
   - `vercel.json:18-22`: Bổ sung status code tường minh:
     - `/offline`: status 200 -> `/simulator/static/offline.html`
     - `/404`: status 404 -> `/simulator/static/404.html`
     - `/500`: status 500 -> `/simulator/static/500.html`
     - `/qr_expired` & `/qr-expired`: status 200 -> `/simulator/static/qr_expired.html`
     - `/403`: status 403 -> `/simulator/static/403.html`
   - `vercel.json:34`: Route `{ "src": "^/architecture/?$", "dest": "/docs/kien_truc/smart-home-voice-ai.architecture.html" }` trả về trang sơ đồ kiến trúc Archify.
   - `vercel.json:36`: Catch-all fallback `{ "src": "^/(.*)$", "status": 404, "dest": "/simulator/static/404.html" }` đặt ở vị trí cuối cùng trong danh sách, giải quyết triệt để lỗi NOT_FOUND thô của Vercel Edge.

2. **Khảo sát mã nguồn backend `simulator/server.py`**:
   - `simulator/server.py:27`: Import `RedirectResponse` từ `fastapi.responses`.
   - `simulator/server.py:148-151`: Khai báo route `@app.get("/mobile")` trả về `RedirectResponse(url="/app", status_code=307)`.
   - `simulator/server.py:180-183`: Khai báo route `@app.get("/architecture")` trả về `FileResponse(DOCS_ARCH_DIR / "smart-home-voice-ai.architecture.html")`.
   - Router modules (`devices_router`, `auth_router`, `qr_router`, `logs_router`) được mount trước các route trang tĩnh.

3. **Kiểm tra định dạng tệp & chuẩn mã hóa**:
   - `vercel.json`: CRLF=0, LF=38, BOM=False (100% Unix LF, UTF-8 no BOM).
   - `simulator/server.py`: CRLF=0, LF=262, BOM=False (100% Unix LF, UTF-8 no BOM).

4. **Kết quả thực thi TestClient theo chỉ thị**:
   - Lệnh: `python -c "from fastapi.testclient import TestClient; from simulator.server import app; c = TestClient(app); r = c.get('/mobile', follow_redirects=False); assert r.status_code == 307 and r.headers['location'] == '/app'; r2 = c.get('/architecture'); assert r2.status_code == 200; print('M11 Independent Review PASS')"`
   - Kết quả: `Exit Code 0`, in ra `M11 Independent Review PASS`.

5. **Kết quả kiểm thử pytest suite**:
   - Lệnh: `python -X utf8 -m pytest tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp`
   - Kết quả: 17/17 tests PASSED trong 8.40s.
   - Thư mục `.pytest_tmp` đã được dọn dẹp sạch sẽ sau kiểm thử.

---

## 2. Logic Chain (Chuỗi suy luận & Thẩm định Độc lập)

1. **Thẩm định nguy cơ Route Shadowing (API & Static)**:
   - Trong `vercel.json`, `/api/(.*)$` đặt tại vị trí index 0. Mọi request có tiền tố `/api/` đều được Vercel định tuyến tới `/api/index.py` trước khi xét tới các quy tắc sau. Do đó, `/mobile`, `/architecture` hay catch-all `/(.*)$` tuyệt đối không thể che khuất các API routes.
   - Các route tĩnh `/static/(.*)$` và `/test_audio/(.*)$` đều đứng trước catch-all `/(.*)$`.
   - Catch-all fallback đứng cuối cùng (index 21 trong routes), nên chỉ bắt các request không khớp với bất kỳ endpoint/route nào trước đó.

2. **Thẩm định tính đồng nhất giữa Vercel Edge và FastAPI Server**:
   - `vercel.json` định nghĩa routing ở tầng CDN/Edge của Vercel.
   - `simulator/server.py` định nghĩa routing ở tầng ứng dụng Python (dùng cho local development, test client, và runtime serverless qua `api/index.py`).
   - Cả hai tầng đều cung cấp hành vi giống nhau:
     - `/mobile` -> chuyển hướng 307 về `/app`.
     - `/architecture` -> phục vụ sơ đồ tương tác `smart-home-voice-ai.architecture.html` (200 OK).
     - Route không tồn tại với client trình duyệt (`Accept: text/html`) -> hiển thị `404.html` (status 404).
     - Route API không tồn tại (`/api/*`) -> trả về JSON `{"detail": "Not Found"}` (status 404).

3. **Kiểm tra tính toàn vẹn (Integrity Audit) & Chống gian lận**:
   - Không phát hiện hardcoded test answers trong mã nguồn.
   - Không có facade/dummy logic: các hàm trả về trực tiếp `RedirectResponse` và `FileResponse` trỏ tới file thật trên đĩa.
   - Không có hành vi cắt xén (shortcuts): cả hai tệp `vercel.json` và `simulator/server.py` đều được bổ sung chuẩn chỉnh.

---

## 3. Caveats (Lưu ý)

- M11 tập trung vào cấu hình routing tại `vercel.json` và backend `simulator/server.py`.
- Việc kiểm thử curl thực tế trên domain production `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app` sẽ được thực hiện sau khi deploy code lên Vercel ở Milestone R6 (Release/Deploy).

---

## 4. Conclusion & Phán quyết (Verdict)

**Verdict**: **APPROVE**

Milestone M11 đã hoàn thành đầy đủ, chính xác, sạch sẽ, không có tác dụng phụ (no regressions), không che khuất API/static routes, vượt qua 100% các bài kiểm thử tự động và thủ công độc lập.

---

## 5. Verification Method (Phương pháp Tái Kiểm tra Độc lập)

```powershell
# 1. Kiểm tra TestClient FastAPI
python -c "from fastapi.testclient import TestClient; from simulator.server import app; c = TestClient(app); r = c.get('/mobile', follow_redirects=False); assert r.status_code == 307 and r.headers['location'] == '/app'; r2 = c.get('/architecture'); assert r2.status_code == 200; print('M11 Independent Review PASS')"

# 2. Chạy test suite pytest M6
python -X utf8 -m pytest tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp
powershell -Command "if (Test-Path '.pytest_tmp') { Remove-Item -Recurse -Force '.pytest_tmp' }"

# 3. Kiểm tra định dạng chuẩn Unix LF và UTF-8 không BOM
python -c "for f in ['vercel.json', 'simulator/server.py']: raw = open(f, 'rb').read(); assert raw.count(b'\r\n') == 0; assert not raw.startswith(b'\xef\xbb\xbf'); print(f, '0 CRLF & UTF-8 no BOM: PASSED')"
```
