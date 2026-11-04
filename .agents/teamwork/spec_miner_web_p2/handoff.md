# BÁO CÁO BÀN GIAO ĐẶC TẢ (5-COMPONENT HANDOFF REPORT)
**Từ Subagent**: `spec_miner_web_p2` (Specification Miner - Web Error Pages, Modals, Banners & SW)
**Tới**: Parent Orchestrator (`a6dd1e0f-b843-4477-96f4-146d5c9d3c58`)
**Ngày hoàn tất**: 2026-11-04
**Loại bàn giao**: Hard Handoff (Hoàn tất 100% nhiệm vụ khảo sát đặc tả)

---

### 1. Observation (Những gì quan sát được trực tiếp từ hệ thống)

1. **Về các tệp UI Mockup và Thiết kế Codex**:
   - Thư mục `ui_mockups/v2_new_pages/` chứa 8 tệp HTML tĩnh và 1 tệp tài liệu đặc tả:
     - `ui_mockups/v2_new_pages/DESIGN_NEW_PAGES.md` (107 dòng, 20.799 bytes) quy chuẩn chi tiết cho từng trang từ mục 01 đến 08 và M1 đến M5.
     - `np_01_offline.html` (3.789 bytes): Giao diện Mất kết nối, icon `wifi-off`, nhãn "KẾT NỐI", thẻ trạng thái mạch, nút "Thử kết nối lại" và "Chuyển sang Server Dự phòng".
     - `np_02_404.html` (3.392 bytes): Lỗi 404, icon `file-question`, nhãn "LỖI 404", tiêu đề "Không tìm thấy trang", link "Về Trang chủ" (`/`) và "Mở Ứng dụng Điện thoại" (`/app`).
     - `np_03_500.html` (3.605 bytes): Lỗi 500/503, icon `server-off`, nhãn "LỖI 500 / 503", tiêu đề "Hệ thống đang bận", nút "Tải lại trang" (`location.reload()`) và "Điều khiển cơ bản".
     - `np_04_qr_expired.html` (3.477 bytes): Mã QR hết hạn, icon `qr-code`, nhãn "LỜI MỜI KHÔNG CÒN HIỆU LỰC", tiêu đề "Mã QR đã hết hạn", nút "Quét mã mới" và "Nhập mã mới" (tuyệt đối không có "Tạo mã mới" cho khách).
     - `np_05_403.html` (3.602 bytes): Lỗi 403, icon `shield-off`, nhãn "LỖI 403", tiêu đề "Không đủ quyền truy cập", role pill `Khách · Cấp 3`, link "Quay về Nhà" (`/app`) và "Đăng nhập tài khoản khác".
     - `np_06_lockdown.html` (4.261 bytes): Hộp thoại Khóa an ninh, `role="alertdialog" aria-modal="true"`, icon `shield-alert`, viền đỏ, ô nhập Mật khẩu Chủ nhà / OTP Gmail, KHÔNG CÓ nút đóng 'X'.
     - `np_07_mic_permission.html` (4.071 bytes): Hộp thoại Quyền micro, `role="dialog" aria-modal="true"`, icon `mic-off`, phân nhánh lỗi từ chối quyền và lỗi HTTP không an toàn, nút "Thử lại", "Mở bản HTTPS", "Đóng".
     - `np_08_ws_banner.html` (4.602 bytes): Thanh thông báo WebSocket, `role="status" aria-live="polite"`, màu cam cảnh báo khi mất kết nối ("Mất kết nối thời gian thực tới ngôi nhà. Đang kết nối lại (lần 1/5)…"), nút "Kết nối ngay", đổi sang màu xanh "Đã khôi phục kết nối" trong 2 giây rồi ẩn.

2. **Về hành vi hiện tại của FastAPI Server (`simulator/server.py`)**:
   - Chạy lệnh thăm dò thực tế qua Python TestClient:
     `python -c "from fastapi.testclient import TestClient; from simulator.server import app; client = TestClient(app); print('Status browser:', client.get('/nonexistent_page', headers={'Accept': 'text/html'}).status_code, client.get('/nonexistent_page', headers={'Accept': 'text/html'}).headers.get('content-type')); print('Status api:', client.get('/api/nonexistent', headers={'Accept': '*/*'}).status_code, client.get('/api/nonexistent').json())"`
   - Kết quả xuất ra nguyên văn:
     ```
     Status browser: 404 application/json
     Status api: 404 {'detail': 'Not Found'}
     ```
   - Trình duyệt điều hướng vào đường dẫn không tồn tại hiện bị trả về JSON 404 thay vì HTML! Chưa có custom exception handler cho 404 trong `server.py`.
   - Trong `simulator/static/` hiện CHƯA CÓ tệp `sw.js` hay các tệp lỗi `offline.html`, `404.html`, `500.html`, `qr_expired.html`, `403.html`.
   - Chưa có route `@app.get("/sw.js")` để cấp quyền `Service-Worker-Allowed: /`.

3. **Về tính toàn vẹn DOM và bộ test đối kháng**:
   - Chạy `python -X utf8 -m pytest tests/test_challenger_m4_dom.py --basetemp=.pytest_tmp`:
     `============================= 36 passed in 2.34s ==============================`
   - Chạy `python -X utf8 -m pytest tests/test_challenger_m3_stress_dom_raycaster.py --basetemp=.pytest_tmp`:
     `============================= 20 passed in 0.91s ==============================`
   - Chạy `python -X utf8 -m pytest tests/test_phase1_bugfixes_20261104.py --basetemp=.pytest_tmp`:
     `======================== 6 passed, 3 warnings in 8.59s ========================`
   - Cả 62 bài kiểm thử đối kháng cấp cao đều đang ở trạng thái PASS 100%.
   - `test_challenger_m4_dom.py` duyệt quét toàn bộ inline events và đối chiếu với khai báo `window.*` hoặc khai báo hàm, quét null-safe trên toàn bộ ID được truy vấn bằng JS.
   - `test_challenger_m3_stress_dom_raycaster.py` cấm tuyệt đối xóa `container.innerHTML = ""` trong `house3d.js` và cấm ẩn `.pin-3d .pin-icon` trong `style.css`.

4. **Về Cơ chế An ninh 3-Strike và Khóa còi báo động**:
   - Trong `simulator/voice_auth.py` dòng 2293-2309:
     - Strike 1: "Tôi không được phép nhận lệnh từ người lạ."
     - Strike 2: "Tôi sẽ không trả lời bạn lần nữa."
     - Strike 3+: `silent_ignore = True`, khóa điều khiển giọng nói.
     - Hàm `reset_strikes()` (dòng 2344) đặt lại `unauthorized_strikes = 0`.
   - Trong `simulator/static/js/app.js` dòng 847-849:
     ```javascript
     } catch (err) {
       liveAiTranscript.textContent = "Không thể mở microphone. Vui lòng kiểm tra quyền truy cập.";
     }
     ```
     Hiện tại mới chỉ gán dòng text vào `liveAiTranscript` chứ chưa bật dialog `np_07_mic_permission.html`.

---

### 2. Logic Chain (Chuỗi suy luận từng bước từ quan sát đến kết luận)

1. Từ **Quan sát 2**, ta thấy trình duyệt gửi `Accept: text/html` khi vào một route 404 bất kỳ đang nhận về JSON `{"detail": "Not Found"}`. Theo yêu cầu R1 trong `ORIGINAL_REQUEST.md`: "FastAPI 404 handler chỉ trả HTML cho điều hướng trình duyệt, giữ nguyên JSON 404 cho /api/*". Do đó, việc bổ sung `@app.exception_handler(404)` và `@app.exception_handler(StarletteHTTPException)` trong `simulator/server.py` là chuẩn xác và bắt buộc, đồng thời kiểm tra điều kiện `request.url.path.startswith("/api/")` hoặc `text/html not in accept` để trả JSON, ngược lại trả `FileResponse(STATIC_DIR / "404.html", status_code=404)`.
2. Từ **Quan sát 1 và 2**, Service Worker theo chuẩn W3C cần có phạm vi (scope) bao trùm cả `/` (Web desktop) và `/app` (Mobile PWA). Nếu đặt file tại `simulator/static/sw.js` mà chỉ gọi `navigator.serviceWorker.register('/static/sw.js')` thì mặc định scope sẽ chỉ là `/static/`. Do đó, server cần mở route `@app.get("/sw.js")` trả về tệp `STATIC_DIR / "sw.js"` kèm header HTTP `Service-Worker-Allowed: /`.
3. Từ **Quan sát 1** trong `DESIGN_NEW_PAGES.md` §01, chiến lược bộ nhớ đệm của `sw.js` phải là network-first cho điều hướng (`request.mode === 'navigate'`), khi offline mới trả cache `offline.html` với `Content-Type: text/html`. Tuyệt đối không cache `/api/*` và không chặn các phương thức ghi dữ liệu (`POST`, `PUT`, `DELETE`). Điều này đảm bảo trạng thái các thiết bị phần cứng Wokwi / ESP8266 luôn nhận dữ liệu sống khi có mạng và không bị lỗi parse JSON khi mất mạng.
4. Từ **Quan sát 3**, 62 bài kiểm thử đối kháng `test_challenger_m3_stress_dom_raycaster.py` và `test_challenger_m4_dom.py` đang bảo vệ rất nghiêm ngặt cấu trúc DOM của `simulator/static/index.html`, `guest_enroll.html`, `auth.html`, và `mobile_app/index.html`. Do đó, khi tích hợp các modal (`#securityLockdownModal`, `#micPermissionModal`) và banner (`#wsReconnectBanner`) vào các trang này:
   - Phải chèn thêm các khối thẻ độc lập, không làm thay đổi, không di chuyển, không xóa bất kỳ ID nào hiện hữu.
   - Mọi hàm JavaScript xử lý modal/banner nếu gọi inline từ HTML bắt buộc phải được xuất lên `window.*` (như `window.toggleLockdownModal`, `window.retryWsConnection`, v.v.) hoặc gán bằng `addEventListener` có điều kiện null-safe guard.
   - Không được chạm vào `house3d.js` hay bố cục Toàn cảnh.
5. Từ **Quan sát 4**, hộp thoại Khóa an ninh (`np_06_lockdown.html`) kích hoạt khi `voice_auth` đạt 3 gậy (`strike_count >= 3`). Khác với các modal thông thường, modal này theo đúng đặc tả an ninh là KHÔNG CÓ nút đóng 'X' và không cho đóng khi click backdrop. Người dùng bắt buộc phải xác thực bằng Mật khẩu Chủ nhà (qua `/api/auth3/layer1_login`) hoặc OTP Gmail (qua `/api/auth3/forgot_password_send_otp` & `/api/auth3/layer2_verify_otp`). Khi xác thực thành công, client gọi mở khóa, đặt lại `reset_strikes()` và tắt modal.

---

### 3. Caveats (Các điểm cần lưu ý & Giả định)

1. **Giả định về Service Worker trong môi trường kiểm thử**:
   Môi trường headless / test client không thực thi Service Worker tự động như trình duyệt thật. Vì vậy, việc kiểm thử `sw.js` và `offline.html` cần kết hợp giữa kiểm tra cú pháp JS, kiểm tra file tồn tại, kiểm tra route trả về từ server, và kiểm thử trình duyệt thực tế.
2. **Quyền Microphone trên IP mạng LAN**:
   Khi truy cập ứng dụng qua IP LAN (ví dụ: `http://192.168.2.39:8088`), các trình duyệt hiện đại (Chrome, Samsung Internet) sẽ chặn `navigator.mediaDevices.getUserMedia` vì context không phải là Secure Context (`isSecureContext === false`). Khi đó, `np_07_mic_permission.html` sẽ hiển thị thông báo "Trình duyệt cần kết nối an toàn để dùng micro. Mở ứng dụng qua HTTPS" và cung cấp liên kết tới đường hầm HTTPS đã mở (như OpenSSH localhost.run).
3. **Không ghi nhận thêm caveats nào khác**.

---

### 4. Conclusion (Kết luận đánh giá cuối cùng)

1. Toàn bộ thông số kỹ thuật, layout, màu sắc, icon Lucide và copy tiếng Việt của 5 trang lỗi web (`offline.html`, `404.html`, `500.html`, `qr_expired.html`, `403.html`), 2 modals (`lockdown`, `mic_permission`), 1 banner (`ws_reconnect`) và Service Worker (`sw.js`) đã được khảo sát chi tiết và ghi nhận đầy đủ tại:
   `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\spec_miner_web_p2\survey_report.md`
2. Danh mục 100% các DOM ID và `window.*` hooks cần bảo toàn đã được lập chỉ mục đầy đủ, sẵn sàng cho các Subagent developer triển khai mà không gây hồi quy (Zero-Regression) đối với các bài test đối kháng M2, M3, M4.

---

### 5. Verification Method (Phương pháp kiểm chứng độc lập)

Để độc lập kiểm chứng các kết luận trong báo cáo này, thực hiện các bước sau:
1. **Kiểm tra định dạng và tệp báo cáo**:
   - Xem tệp đặc tả chi tiết:
     `view_file C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\spec_miner_web_p2\survey_report.md`
2. **Kiểm tra các bài test đối kháng hiện tại**:
   - Chạy lệnh:
     `python -X utf8 -m pytest tests/test_challenger_m4_dom.py --basetemp=.pytest_tmp` (kết quả mong đợi: 36 passed)
   - Chạy lệnh:
     `python -X utf8 -m pytest tests/test_challenger_m3_stress_dom_raycaster.py --basetemp=.pytest_tmp` (kết quả mong đợi: 20 passed)
   - Chạy lệnh:
     `python -X utf8 -m pytest tests/test_phase1_bugfixes_20261104.py --basetemp=.pytest_tmp` (kết quả mong đợi: 6 passed)
3. **Kiểm tra sự tồn tại của 8 tệp mockup**:
   - Chạy lệnh PowerShell:
     `Get-ChildItem -Path "ui_mockups\v2_new_pages\np_*.html" | Select-Object Name, Length`
     (kết quả: 8 tệp mockup từ `np_01` đến `np_08` đều tồn tại và có kích thước từ 3.3KB đến 4.6KB).
4. **Kiểm tra hành vi 404 hiện tại của FastAPI**:
   - Chạy lệnh:
     `python -c "from fastapi.testclient import TestClient; from simulator.server import app; client = TestClient(app); print(client.get('/404_test', headers={'Accept': 'text/html'}).status_code, client.get('/404_test', headers={'Accept': 'text/html'}).headers.get('content-type'))"`
     (kết quả hiện tại trả về `404 application/json`, chứng minh chưa có HTML fallback cho trình duyệt và cần triển khai theo R1).
