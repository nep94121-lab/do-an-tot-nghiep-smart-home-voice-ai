# BÁO CÁO BÀN GIAO THỰC NGHIỆM QA GIAI ĐOẠN 2 (HANDOFF REPORT)

**Người thực hiện**: `qa_tester_p2` (Archetype: Challenger / Role: Critic, Specialist)  
**Parent Agent**: `a6dd1e0f-b843-4477-96f4-146d5c9d3c58`  
**Ngày bàn giao**: 2026-11-04  
**Trạng thái**: Hard Handoff (Hoàn tất 100% nhiệm vụ thực nghiệm, có bằng chứng tái hiện độc lập)  

---

## 1. Observation (Quan sát thực nghiệm trực tiếp)

1. **Khả năng kết nối máy chủ sống trên cổng 8088:**
   - Lệnh thực thi: `Get-NetTCPConnection -LocalPort 8088`
     ```
     LocalAddress LocalPort RemoteAddress RemotePort State
     0.0.0.0      8088      0.0.0.0       0          Listen
     ```
   - Lệnh thực thi: `python -c "import urllib.request, json; resp = urllib.request.urlopen('http://127.0.0.1:8088/api/state'); print('Status:', resp.status)"`
     ```
     Status: 200
     ```

2. **Kiểm thử bộ Playwright DevTools trên máy chủ sống:**
   - Lệnh thực thi: `python -X utf8 -m pytest tests/test_challenger_m5_devtools.py --basetemp=.pytest_tmp -v`
     ```
     tests/test_challenger_m5_devtools.py::test_page_zero_console_errors_and_zero_http_failures[/-Trang chủ 3D] PASSED [ 16%]
     tests/test_challenger_m5_devtools.py::test_page_zero_console_errors_and_zero_http_failures[/auth-Trang Xác thực 3 Lớp] PASSED [ 33%]
     tests/test_challenger_m5_devtools.py::test_page_zero_console_errors_and_zero_http_failures[/guest_enroll-Trang Thu âm Khách QR] PASSED [ 50%]
     tests/test_challenger_m5_devtools.py::test_page_zero_console_errors_and_zero_http_failures[/wokwi-Trang Phần cứng Wokwi] PASSED [ 66%]
     tests/test_challenger_m5_devtools.py::test_page_zero_console_errors_and_zero_http_failures[/logs-Trang Nhật ký & CSDL] PASSED [ 83%]
     tests/test_challenger_m5_devtools.py::test_page_zero_console_errors_and_zero_http_failures[/app-Giao diện Di động] PASSED [100%]
     ============================= 6 passed in 23.74s ==============================
     ```

3. **Kiểm thử bộ test Phase 2 của các Worker M6, M7, M8:**
   - Lệnh thực thi: `python -X utf8 -m pytest tests/test_m6_web_error_sw.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp -v`
     ```
     ======================= 55 passed, 3 warnings in 6.72s ========================
     ```

4. **Kiểm thử luồng thực tế 3 vai, trang lỗi và 5 màn hình mobile (`tests/test_qa_p2_live_user_flows.py`):**
   - Lệnh thực thi: `python -X utf8 -m pytest tests/test_qa_p2_live_user_flows.py --basetemp=.pytest_tmp -v`
     ```
     ======================= 20 passed, 3 warnings in 6.80s ========================
     ```
   - Chi tiết:
     - R1: Kết nối server live và TestClient đạt 3/3 passed.
     - R2: Luồng 3 vai (Chủ nhà nep94121@gmail.com toàn quyền D1/D8, Gia đình thanhviena.hust@gmail.com bị chặn D1/D8, Khách khachc.guest@gmail.com với dynamic QR TOTP handshake bị chặn D1/D8/schedule) đạt 3/3 passed.
     - R3: Toàn bộ trang lỗi `offline.html`, `404.html`, Content-Negotiation (HTML cho trình duyệt vs JSON cho API), `500.html`, `qr_expired.html`, `403.html`, và `sw.js` (header `Service-Worker-Allowed: /`) đạt 9/9 passed.
     - R4: 5 màn hình mobile /app (M1 overview 16:9 + 2 ô cảm biến, M2 4-tab switcher + hồ sơ, M3 quên mật khẩu 3 bước + OTP 6 số, M4 voice bottom sheet 12 bars, M5 camera QR scanner 4 góc) đạt 5/5 passed.

5. **Kết quả chạy toàn bộ test suite dự án (Full Pytest Suite):**
   - Lệnh thực thi: `python -X utf8 -m pytest tests/ --basetemp=.pytest_tmp -q`
     ```
     753 passed, 6 failed, 3 warnings in 196.41s (0:03:16)
     ```
   - 6 bài test thất bại:
     - `tests/test_challenger_m4_security.py::TestStaticResourceServingAndContentTypes::test_html_files_cleanliness_zero_inline_styles_and_scripts` (FAIL):
       `AssertionError: Tệp index.html vẫn còn 1 khối inline <script>! assert 1 == 0`
       Quan sát trực tiếp tại `simulator/static/index.html` dòng 441-446:
       ```html
       <script>
         if ('serviceWorker' in navigator) {
           window.addEventListener('load', function() {
             navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function() {});
           });
         }
       </script>
       ```
     - `tests/test_m8_mobile_screens.py::TestM5QrScanner::test_m5_backend_handshake_endpoint` (FAIL khi chạy chuỗi; PASS 100% khi chạy lẻ):
       Bị đụng độ mã TOTP dùng một lần (Single-Use Token collision) do chạy trong cùng cửa sổ 10 giây với bài test QR phía trước.
     - `tests/test_phase1_bugfixes_20261104.py` (4 bài fail khi chạy chuỗi; PASS 100% khi chạy lẻ):
       Bị ô nhiễm trạng thái singleton `_REST_ENGINE` từ các bài test phía trước (đèn bật/tắt, độ ẩm đất 62% thay vì 55%).

---

## 2. Logic Chain (Chuỗi suy luận logic)

1. **Từ Quan sát 1, 2, 3, 4 $\rightarrow$ Toàn bộ tính năng mới của Phase 2 hoạt động chính xác:**
   - Việc kiểm thử trực tiếp trên cổng 8088 xác nhận máy chủ FastAPI đang chạy ổn định, tiếp nhận các yêu cầu HTTP và WebSocket.
   - Luồng phân quyền RBAC phân cấp 3 tầng hoạt động chính xác: Chủ nhà được phép thao tác toàn bộ thiết bị (bao gồm Servo cửa D1 và Còi hú D8); Gia đình và Khách bị từ chối mở cửa và còi báo động với cờ `rbac_blocked: True`. Khách bị chặn tạo lịch hẹn giờ với HTTP 403.
   - Luồng mã QR động TOTP 10s: Hàm `generate_dynamic_qr_token` tạo mã HMAC-SHA256 hợp lệ; `consume_guest_handshake` chấp nhận độ lệch 180s và tạo phiên khách 15 phút an toàn.
   - Cơ chế đàm phán nội dung (Content-Negotiation) tại ngoại lệ 404 hoạt động xuất sắc: Trả về trang HTML đẹp mắt cho trình duyệt (`Accept: text/html`) và giữ nguyên JSON chuẩn cho API client (`/api/*`).
   - 5 màn hình mobile /app giữ trọn vẹn 100% DOM IDs và hooks, vượt qua toàn bộ các kiểm thử cấu trúc và hành vi.

2. **Từ Quan sát 5 $\rightarrow$ Xác định chính xác 1 lỗi mã nguồn và 2 vấn đề kiểm thử:**
   - **Lỗi mã nguồn (Bug Finding 1):** `worker_m6` khi tích hợp đăng ký Service Worker đã chèn thẻ inline `<script>` trực tiếp vào cuối `simulator/static/index.html`. Điều này vi phạm kiểm thử an ninh `test_challenger_m4_security.py` (yêu cầu zero inline scripts trong 6 file HTML). Giải pháp là di dời đoạn mã đăng ký này vào `simulator/static/js/app.js`.
   - **Vấn đề kiểm thử (Bug Finding 2 & 3):** Không phải lỗi tính năng hệ thống, mà là do hiệu ứng phụ khi chạy dồn 759 bài test liên tục:
     - Đụng độ TOTP token trong cùng 10 giây: Do 2 bài test cùng sinh token `1d` trong cùng chu kỳ 10 giây và bài test thứ nhất đã consume token đó.
     - Ô nhiễm singleton `_REST_ENGINE`: Do các bài test phía trước thay đổi trạng thái thiết bị mà `test_phase1_bugfixes_20261104.py` không có teardown/setup tự reset.

---

## 3. Caveats (Lưu ý)

- **Quy tắc Agent Critic:** Tuân thủ triệt để chỉ thị vai trò Challenger/Critic: Không tự ý sửa đổi mã nguồn ứng dụng (`simulator/static/index.html`), mà ghi nhận đầy đủ hiện tượng, nguyên nhân và vị trí dòng để đội implementer hoặc parent agent áp dụng bản vá chuẩn xác.
- **Microphone thật:** Trình duyệt headless trong môi trường CI/CD không có micro vật lý, do đó các luồng micro tự động kích hoạt `#micPermissionModal` đúng như thiết kế dự phòng.

---

## 4. Conclusion (Kết luận)

1. **Nghiệm thu Đạt yêu cầu cốt lõi:**
   - Server `http://localhost:8088` hoạt động tốt.
   - Luồng 3 vai trò (Chủ nhà, Gia đình, Khách) chạy thực tế thông suốt, chuẩn RBAC.
   - Các trang lỗi Web (`offline`, `404`, `500`, `qr_expired`, `403`) và `sw.js` hoạt động chuẩn xác theo spec Codex.
   - 5 màn hình Mobile /app hoàn thiện đầy đủ.
   - Bài test thực nghiệm mới `tests/test_qa_p2_live_user_flows.py` đạt **20/20 PASSED (100%)**.
   - Bộ Playwright live server đạt **6/6 PASSED (100%)**.

2. **Khuyến nghị hành động tiếp theo:**
   - Chuyển 6 dòng inline `<script>` đăng ký Service Worker trong `simulator/static/index.html` (dòng 441-446) sang `simulator/static/js/app.js` để bộ an ninh `test_challenger_m4_security.py` đạt 48/48 PASS tuyệt đối.

---

## 5. Verification Method (Phương pháp kiểm chứng độc lập)

Để kiểm chứng lại toàn bộ các kết quả trên, chạy các lệnh sau từ thư mục gốc dự án:

1. **Kiểm tra luồng người dùng thực tế 3 vai và trang mới:**
   ```powershell
   python -X utf8 -m pytest tests/test_qa_p2_live_user_flows.py --basetemp=.pytest_tmp -v
   ```
   *Kết quả mong đợi:* `20 passed in ~6.8s`.

2. **Kiểm tra các màn hình Mobile /app và các trang Web mới:**
   ```powershell
   python -X utf8 -m pytest tests/test_m6_web_error_sw.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp -v
   ```
   *Kết quả mong đợi:* `55 passed in ~6.7s`.

3. **Kiểm tra Playwright DevTools trên server sống:**
   ```powershell
   python -X utf8 -m pytest tests/test_challenger_m5_devtools.py --basetemp=.pytest_tmp -v
   ```
   *Kết quả mong đợi:* `6 passed in ~23s`.

4. **Kiểm tra lỗi inline script trong index.html:**
   ```powershell
   python -X utf8 -m pytest tests/test_challenger_m4_security.py::TestStaticResourceServingAndContentTypes::test_html_files_cleanliness_zero_inline_styles_and_scripts --basetemp=.pytest_tmp -v
   ```
   *Kết quả mong đợi:* Tái hiện chính xác lỗi `assert 1 == 0` do inline script tại dòng 441-446 trong `simulator/static/index.html`.
