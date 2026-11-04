# BÁO CÁO GIÁM ĐỊNH TÍNH TOÀN VẸN (FORENSIC INTEGRITY AUDIT)
## MILESTONE M11: VERCEL PRODUCTION ROUTING & REDIRECTION

- **Auditor**: `teamwork_auditor` (auditor_m11)
- **Parent Conversation ID**: `39d935a1-0551-429d-ac45-c89f1e361ad0`
- **Thời gian hoàn thành**: 2026-11-04T15:43:00Z
- **Work Product**: Thay đổi mã nguồn cho Milestone M11 trên `vercel.json` và `simulator/server.py`
- **Integrity Mode**: `development` (theo `ORIGINAL_REQUEST.md`)
- **VERDICT: CLEAN**

---

## 1. Observation (Quan sát & Bằng chứng Thực nghiệm)

### 1.1. Phạm vi thay đổi mã nguồn (Git Diff Analysis)
Lệnh `git diff` trên các file liên quan đến Milestone M11:
- `vercel.json`:
  ```diff
  @@ -13,12 +13,13 @@
     ],
     "routes": [
       { "src": "^/api/(.*)$", "dest": "/api/index.py" },
  -    { "src": "^/sw\\.js$", "dest": "/simulator/static/sw.js", "headers": { "Service-Worker-Allowed": "/" } },
  -    { "src": "^/offline(\\.(html))?$", "dest": "/simulator/static/offline.html" },
  -    { "src": "^/404(\\.(html))?$", "dest": "/simulator/static/404.html" },
  -    { "src": "^/500(\\.(html))?$", "dest": "/simulator/static/500.html" },
  -    { "src": "^/(qr_expired|qr-expired)(\\.(html))?$", "dest": "/simulator/static/qr_expired.html" },
  -    { "src": "^/403(\\.(html))?$", "dest": "/simulator/static/403.html" },
  +    { "src": "^/mobile/?$", "status": 307, "headers": { "Location": "/app" } },
  +    { "src": "^/sw\\.js$", "dest": "/simulator/static/sw.js", "headers": { "Service-Worker-Allowed": "/", "Cache-Control": "no-cache, no-store, must-revalidate" } },
  +    { "src": "^/offline(\\.(html))?$", "status": 200, "dest": "/simulator/static/offline.html" },
  +    { "src": "^/404(\\.(html))?$", "status": 404, "dest": "/simulator/static/404.html" },
  +    { "src": "^/500(\\.(html))?$", "status": 500, "dest": "/simulator/static/500.html" },
  +    { "src": "^/(qr_expired|qr-expired)(\\.(html))?$", "status": 200, "dest": "/simulator/static/qr_expired.html" },
  +    { "src": "^/403(\\.(html))?$", "status": 403, "dest": "/simulator/static/403.html" },
       { "src": "^/static/(.*)$", "dest": "/simulator/static/$1" },
       { "src": "^/test_audio/(.*)$", "dest": "/test_audio/$1" },
       { "src": "^/app/?$", "dest": "/mobile_app/index.html" },
  @@ -28,7 +29,10 @@
       { "src": "^/logs/?$", "dest": "/simulator/static/logs.html" },
       { "src": "^/wokwi/?$", "dest": "/simulator/static/wokwi.html" },
       { "src": "^/archify/devops/?$", "dest": "/docs/kien_truc/devops-cicd-pipeline.workflow.html" },
  +    { "src": "^/archify/erd/?$", "dest": "/docs/kien_truc/smarthome-database.erd.html" },
       { "src": "^/archify/?$", "dest": "/docs/kien_truc/smart-home-voice-ai.architecture.html" },
  -    { "src": "^/$", "dest": "/simulator/static/index.html" }
  +    { "src": "^/architecture/?$", "dest": "/docs/kien_truc/smart-home-voice-ai.architecture.html" },
  +    { "src": "^/$", "dest": "/simulator/static/index.html" },
  +    { "src": "^/(.*)$", "status": 404, "dest": "/simulator/static/404.html" }
     ]
   }
  ```
- `simulator/server.py`:
  ```diff
  @@ -24,7 +24,7 @@ from typing import Any
   import uvicorn
   from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
   from fastapi.middleware.cors import CORSMiddleware
  -from fastapi.responses import FileResponse, JSONResponse
  +from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
   from fastapi.staticfiles import StaticFiles
   from starlette.exceptions import HTTPException as StarletteHTTPException
  @@ -144,6 +144,12 @@ async def mobile_app_index() -> FileResponse:
       return FileResponse(MOBILE_APP_DIR / "index.html")
  +@app.get("/mobile")
  +async def mobile_redirect() -> RedirectResponse:
  +    """Chuyển hướng 307 từ /mobile về ứng dụng /app."""
  +    return RedirectResponse(url="/app", status_code=307)
  +
  @@ -170,6 +176,12 @@ async def archify_architecture_page() -> FileResponse:
       return FileResponse(DOCS_ARCH_DIR / "smart-home-voice-ai.architecture.html")
  +@app.get("/architecture")
  +async def architecture_page() -> FileResponse:
  +    """Trang Sơ đồ Kiến trúc Hệ thống tương tác (Archify)."""
  +    return FileResponse(DOCS_ARCH_DIR / "smart-home-voice-ai.architecture.html")
  +
  ```

### 1.2. Kiểm tra tính toàn vẹn của tệp test (Test Tampering Check)
- Lệnh: `git diff tests/`
- Kết quả: Không có bất kỳ thay đổi nào trong thư mục `tests/` do worker_m11 thực hiện. File test gốc `tests/test_m6_web_error_sw.py` nguyên vẹn 100%.

### 1.3. Định dạng mã hóa & Ký tự ngắt dòng (Formatting & CRLF Check)
- Lệnh: Python binary check trên `vercel.json` và `simulator/server.py`.
- Kết quả:
  - `vercel.json`: size=2175B, CRLF=0, isolated_CR=0, LF=38, BOM=False.
  - `simulator/server.py`: size=8822B, CRLF=0, isolated_CR=0, LF=261, BOM=False.
  - Cả 2 tệp tuân thủ nghiêm ngặt chuẩn Unix LF (`\n`) và UTF-8 không BOM.

### 1.4. Kiểm tra sự tồn tại của các tệp đích trên đĩa (Target Files Integrity)
- Lệnh: Quét toàn bộ giá trị `dest` trong `vercel.json` đối chiếu với hệ thống tệp cục bộ.
- Kết quả: 100% các tệp đích tĩnh (`/simulator/static/*.html`, `/mobile_app/index.html`, `/docs/kien_truc/*.html`, `/api/index.py`) đều tồn tại thực tế trên đĩa.

### 1.5. Thực nghiệm kiểm thử độc lập (Independent Test Execution)
- Chạy độc lập `pytest tests/test_m6_web_error_sw.py`:
  - `17 passed, 3 warnings in 10.49s` (Exit code: 0).
- Chạy độc lập kịch bản hành vi `verify_behavior.py`:
  - `/mobile` trả về HTTP 307 với `location: /app`.
  - Follow redirect `/mobile` trả về HTTP 200 HTML.
  - `/architecture` trả về HTTP 200 HTML sơ đồ kiến trúc.
  - Tất cả route lỗi (`/offline`, `/404`, `/500`, `/403`, `/qr_expired`, `/sw.js`) trả về đúng status code.
  - Content negotiation: Client gửi `Accept: text/html` nhận HTML 404; client gửi `Accept: application/json` nhận JSON 404.
  - Vercel simulation: Mô phỏng toàn bộ URL paths trên cấu hình regex của `vercel.json` đều khớp chính xác route dự kiến và catch-all 404 ở cuối.
- Chạy độc lập bộ stress-test của Challenger `tests/test_challenger_m11_vercel_routing.py`:
  - `17 passed, 3 warnings in 19.77s` (Exit code: 0).

---

## 2. Logic Chain (Chuỗi Suy luận Giám định)

1. **Từ Quan sát 1.1 & 1.2**:
   - `worker_m11` chỉ sửa đúng 2 tệp được chỉ định (`vercel.json` và `simulator/server.py`).
   - Không có file test nào bị sửa đổi hoặc làm yếu điều kiện kiểm tra (zero tampering).
2. **Từ Quan sát 1.1 & 1.4**:
   - Đoạn mã trong `simulator/server.py` sử dụng trực tiếp các lớp phản hồi chuẩn của FastAPI/Starlette (`RedirectResponse`, `FileResponse`), không có hàm dummy trả về hằng số rỗng, không có facade hay stub giả lập.
   - Các đường dẫn định tuyến trong `vercel.json` trỏ trực tiếp đến các file vật lý đang tồn tại trong dự án.
3. **Từ Quan sát 1.3**:
   - Hai tệp sửa đổi đạt tỷ lệ 0 CRLF và UTF-8 không BOM, bảo đảm tính toàn vẹn cross-platform trên cả Vercel Linux builder và môi trường cục bộ.
4. **Từ Quan sát 1.5**:
   - Các bài kiểm thử độc lập (cả suite chuẩn M6 lẫn suite đối kháng do Challenger viết) đều PASS 100% khi chạy thực tế.
   - Thư mục `.pytest_tmp` được dọn dẹp sạch sẽ sau mỗi lần chạy theo đúng chỉ thị trong `ORIGINAL_REQUEST.md`.

---

## 3. Caveats (Lưu ý & Giới hạn Kiểm tra)

- **Kiểm tra trên Production Domain thật**: Theo phân công của `ORIGINAL_REQUEST.md` (mục R6), việc chạy `git push master` và `vercel deploy --prod` cùng kiểm tra curl trên domain thật (`https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`) sẽ được thực hiện tại Giai đoạn R6 sau khi tất cả các milestone hội tụ. Trong phạm vi Milestone M11, cấu hình định tuyến Vercel và backend simulator đã được chứng minh đồng nhất và chính xác.

---

## 4. Conclusion (Kết luận Giám định)

**VERDICT: CLEAN**

- Công việc Milestone M11 hoàn toàn chân thực, không có mã giả lập (facade), không có kết quả kiểm thử cố định (hardcoded test results), không có gian lận test.
- Định dạng mã nguồn đạt chuẩn 100% (0 CRLF, UTF-8 không BOM).
- Phê duyệt bàn giao Milestone M11 sang bước tiếp theo của quy trình.

---

## 5. Verification Method (Cách thức Tái lập Kiểm chứng)

Người kiểm định độc lập có thể tái lập toàn bộ quy trình kiểm toán bằng các lệnh sau:

1. **Kiểm tra mã hóa và CRLF**:
   ```powershell
   python -c "for f in ['vercel.json', 'simulator/server.py']: d = open(f, 'rb').read(); assert b'\r\n' not in d; assert not d.startswith(b'\xef\xbb\xbf'); print(f, 'OK')"
   ```
2. **Kiểm tra bộ test M6**:
   ```powershell
   python -X utf8 -m pytest tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp
   powershell -Command "if (Test-Path '.pytest_tmp') { Remove-Item -Recurse -Force '.pytest_tmp' }"
   ```
3. **Kiểm tra bộ test Challenger M11**:
   ```powershell
   python -X utf8 -m pytest tests/test_challenger_m11_vercel_routing.py --basetemp=.pytest_tmp
   powershell -Command "if (Test-Path '.pytest_tmp') { Remove-Item -Recurse -Force '.pytest_tmp' }"
   ```
