# BÁO CÁO BÀN GIAO: ADVERSARIAL CHALLENGE — MILESTONE M11 (VERCEL PRODUCTION ROUTING & REDIRECTION)

- **Agent thực hiện**: `teamwork_challenger` (challenger_m11_1 - Critic / Empirical Challenger)
- **Parent Agent ID**: `39d935a1-0551-429d-ac45-c89f1e361ad0`
- **Thời gian hoàn tất**: 2026-11-04T15:40:00Z
- **Loại bàn giao**: Hard Handoff (Kiểm thử thực nghiệm độc lập hoàn tất, có bằng chứng số liệu và bộ test code)
- **Phán quyết (Verdict)**: **APPROVE** (Chấp thuận nghiệm thu Milestone M11)

---

## 1. Observation (Quan sát & Thực nghiệm Trực tiếp)

1. **Khảo sát cấu hình `vercel.json`**:
   - Tệp `vercel.json` (39 dòng, 2175 bytes, UTF-8 không BOM, 0 CRLF).
   - `version: 2`, `framework: null`, `cleanUrls: false`.
   - Danh sách `routes` gồm 22 phần tử, tất cả các regex đều biên dịch hợp lệ qua `re.compile()`.
   - Vị trí các route trọng yếu:
     - Dòng 15 (`routes[0]`): `{ "src": "^/api/(.*)$", "dest": "/api/index.py" }`
     - Dòng 16 (`routes[1]`): `{ "src": "^/mobile/?$", "status": 307, "headers": { "Location": "/app" } }`
     - Dòng 23 (`routes[8]`): `{ "src": "^/static/(.*)$", "dest": "/simulator/static/$1" }`
     - Dòng 34 (`routes[19]`): `{ "src": "^/architecture/?$", "dest": "/docs/kien_truc/smart-home-voice-ai.architecture.html" }`
     - Dòng 35 (`routes[20]`): `{ "src": "^/$", "dest": "/simulator/static/index.html" }`
     - Dòng 36 (`routes[21]`): `{ "src": "^/(.*)$", "status": 404, "dest": "/simulator/static/404.html" }`
   - Tất cả 16 tệp đích tĩnh không chứa biến (`dest`) được tham chiếu trong `vercel.json` đều tồn tại thực tế trên ổ đĩa.

2. **Khảo sát định tuyến backend FastAPI (`simulator/server.py`)**:
   - Dòng 27: `from fastapi.responses import FileResponse, JSONResponse, RedirectResponse`
   - Dòng 101-122: Bộ xử lý ngoại lệ `custom_http_exception_handler` phân tách rõ:
     - Request có `Accept: text/html` (điều hướng trình duyệt): trả `FileResponse(STATIC_DIR / "404.html", status_code=404)`.
     - Request bắt đầu bằng `/api/` hoặc client không yêu cầu HTML: trả `JSONResponse({"detail": detail}, status_code=404)`.
   - Dòng 147-150: `@app.get("/mobile")` trả `RedirectResponse(url="/app", status_code=307)`.
   - Dòng 179-182: `@app.get("/architecture")` trả `FileResponse(DOCS_ARCH_DIR / "smart-home-voice-ai.architecture.html")`.

3. **Thực thi bộ thăm dò đối nghịch độc lập (`tests/test_challenger_m11_vercel_routing.py`)**:
   - Lệnh: `python -X utf8 -m pytest tests/test_challenger_m11_vercel_routing.py --basetemp=.pytest_tmp -v`
   - Kết quả: **17 passed, 0 failed, 3 warnings trong 9.42s** (Exit code: 0).
   - Chi tiết:
     - `test_json_load_and_version`: PASSED
     - `test_all_route_regexes_compile`: PASSED
     - `test_destination_files_exist_on_disk`: PASSED
     - `test_catchall_is_strictly_last_route`: PASSED
     - `test_mobile_exact_and_trailing_slash`: PASSED
     - `test_architecture_exact_and_trailing_slash`: PASSED
     - `test_adversarial_prefix_hijack_prevention`: PASSED
     - `test_api_routes_precede_catchall`: PASSED
     - `test_static_routes_precede_catchall`: PASSED
     - `test_error_pages_preserve_correct_statuses`: PASSED
     - `test_arbitrary_random_urls_hit_catchall_404`: PASSED
     - `test_fastapi_mobile_redirect`: PASSED
     - `test_fastapi_mobile_trailing_slash`: PASSED
     - `test_fastapi_architecture_page`: PASSED
     - `test_fastapi_architecture_trailing_slash`: PASSED
     - `test_fastapi_non_existent_browser_navigation`: PASSED
     - `test_fastapi_non_existent_api_call`: PASSED

4. **Thực thi kiểm tra hồi quy suite M6 (`tests/test_m6_web_error_sw.py`)**:
   - Lệnh: `python -X utf8 -m pytest tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp`
   - Kết quả: **17 passed, 0 failed trong 10.33s** (Exit code: 0).

---

## 2. Logic Chain (Chuỗi Suy luận & Phân tích Đối nghịch)

Dựa trên các quan sát thực nghiệm, chuỗi suy luận giải quyết trọn vẹn 5 câu hỏi thách thức của Orchestrator:

1. **Tính hợp lệ cú pháp của `vercel.json`**:
   - Tệp JSON được phân tích thành công bởi bộ parser chuẩn RFC 8259 (`json.loads`), không có lỗi cú pháp hoặc trailing comma.
   - Toàn bộ các chuỗi regex trong thuộc tính `"src"` được kiểm chứng biên dịch thành công mà không gây `re.error`.

2. **Khả năng bắt cả `/mobile` và `/mobile/`**:
   - Biểu thức chính quy: `^/mobile/?$` sử dụng toán tử định lượng `/?` (khớp 0 hoặc 1 ký tự gạch chéo cuối) cùng cặp neo đầu/cuối chuỗi `^` và `$`.
   - Với chuỗi vào `/mobile`: khớp hoàn toàn, trả HTTP 307 kèm header `Location: /app`.
   - Với chuỗi vào `/mobile/`: khớp hoàn toàn, trả HTTP 307 kèm header `Location: /app`.
   - Trên backend FastAPI, `@app.get("/mobile")` trả 307 về `/app`. Đối với `/mobile/`, cơ chế tự động xử lý slash của Starlette redirect sang `/mobile` và sau đó redirect sang `/app` (cả 2 đều chuyển hướng an toàn tới `/app`).

3. **Khả năng bắt cả `/architecture` và `/architecture/`**:
   - Biểu thức chính quy: `^/architecture/?$` khớp cả `/architecture` và `/architecture/`.
   - Cả 2 trường hợp đều định tuyến (rewrite) tới `/docs/kien_truc/smart-home-voice-ai.architecture.html`.
   - Trên backend FastAPI, cả 2 endpoint đều trả về mã HTTP 200 kèm nội dung sơ đồ kiến trúc Archify.

4. **Nguy cơ xung đột giữa Catch-all `^/(.*)$` và `/api/(.*)$` hoặc `/static/(.*)$`**:
   - Quy chuẩn định tuyến của Vercel Engine tuân theo thứ tự tuần tự trong mảng `"routes"` (First-Match-Wins).
   - `/api/(.*)$` được đặt tại vị trí đầu tiên (`routes[0]`). Mọi yêu cầu bắt đầu bằng `/api/` sẽ khớp ngay lập tức với `routes[0]` và được chuyển hướng tới `/api/index.py`, hoàn toàn không thể chạm tới rule catch-all ở cuối mảng.
   - `/static/(.*)$` được đặt tại vị trí `routes[8]`. Mọi yêu cầu tài nguyên tĩnh `/static/*` sẽ khớp tại rule này và chuyển hướng tới `/simulator/static/$1`.
   - Catch-all `^/(.*)$` được đặt tại vị trí cuối cùng (`routes[21]`). Phân tích thứ tự chứng minh không có nguy cơ xung đột hay shadowing đối với các API và Static files.

5. **Hành vi khi người dùng truy cập URL không tồn tại (`/non_existent_random_page_12345`)**:
   - Không khớp với bất kỳ rule cụ thể nào từ index 0 đến 20.
   - Rơi vào rule cuối cùng (index 21) `^/(.*)$`.
   - Vercel trả về HTTP Status Code `404` và phục vụ nội dung trang tùy biến `/simulator/static/404.html` (thay vì trang lỗi 404 mặc định 79 bytes của Vercel Edge).
   - Trên backend FastAPI, cơ chế Content Negotiation phân biệt: browser navigation nhận file HTML 404 tùy biến, trong khi API request nhận JSON 404 chuẩn.

6. **Chống tấn công leo thang tiền tố (Prefix Hijacking Protection)**:
   - Các biểu thức chính quy đều có neo kết thúc chuỗi `$`: `^/mobile/?$` và `^/architecture/?$`.
   - Các URL có tiền tố tương tự nhưng không hợp lệ (ví dụ: `/mobile_extra`, `/mobile/malicious`, `/architecture_fake`) sẽ không bị khớp nhầm vào rule chuyển hướng/nội dung, mà tự động rơi vào catch-all 404.html.

---

## 3. Caveats (Lưu ý)

- Bài kiểm thử này mô phỏng độc lập hành vi định tuyến cạnh (Edge routing engine) của Vercel trên môi trường local và kiểm tra trực tiếp backend FastAPI.
- Việc kiểm thử live curl trên domain production thật `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app` sẽ được tiến hành sau khi hoàn tất commit, push git và kích hoạt pipeline deploy ở bước hội tụ cuối cùng (Requirement R6).

---

## 4. Conclusion (Kết luận)

- **Phán quyết chính thức**: **APPROVE** (Chấp thuận hoàn toàn).
- Cấu hình định tuyến trong `vercel.json` và triển khai trong `simulator/server.py` đạt 100% tính chính xác, chặt chẽ về mặt biểu thức chính quy, an toàn về thứ tự ưu tiên (không xung đột API/Static), và xử lý tối ưu trang lỗi 404 tùy biến theo đúng yêu cầu R1 của đề tài.

---

## 5. Verification Method (Cách Thức Tự Kiểm Chứng Độc Lập)

Bất kỳ reviewer/auditor nào cũng có thể kiểm chứng lại kết quả bằng các lệnh sau:

1. **Chạy bộ kiểm thử thăm dò đối nghịch M11**:
   ```powershell
   python -X utf8 -m pytest tests/test_challenger_m11_vercel_routing.py --basetemp=.pytest_tmp -v
   ```
   *Kỳ vọng*: 17/17 tests PASSED trong <10s.

2. **Chạy bộ kiểm thử tích hợp M6**:
   ```powershell
   python -X utf8 -m pytest tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp
   ```
   *Kỳ vọng*: 17/17 tests PASSED trong <11s.

3. **Kiểm tra chuẩn định dạng (0 CRLF, UTF-8 no BOM)**:
   ```powershell
   python -c "for f in ['vercel.json', 'tests/test_challenger_m11_vercel_routing.py']: raw=open(f, 'rb').read(); assert raw.count(b'\r\n') == 0; assert not raw.startswith(b'\xef\xbb\xbf'); print(f, '0 CRLF & UTF-8 no BOM: PASSED')"
   ```
