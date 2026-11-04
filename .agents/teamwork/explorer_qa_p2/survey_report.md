# BÁO CÁO KHẢO SÁT QA & CHIẾN LƯỢC KIỂM THỬ GIAI ĐOẠN 2 (PHASE 2)
**Dự án:** Smart Home Voice AI — Khảo sát Kiểm thử, Fixtures, Tài khoản 3 Vai & Yêu cầu Triển khai  
**Người thực hiện:** `explorer_qa_p2` (Teamwork Explorer QA)  
**Thời điểm hoàn thành:** 2026-11-04T12:36:00Z  

---

## 1. Đánh giá Bộ Kiểm thử Hiện hữu & Số lượng PASS Cơ sở (Baseline)

### 1.1. Kết quả chạy Pytest toàn bộ
Lệnh thực thi cơ sở:
```powershell
python -X utf8 -m pytest tests/ --basetemp=.pytest_tmp -q
```
- **Tổng số tests:** 684
- **Đạt (Passed):** 673 tests
- **Thất bại (Failed):** 11 tests
- **Cảnh báo (Warnings):** 3 (Deprecation warnings từ thư viện bên ngoài)
- **Thời gian thực thi:** 206.43 giây (~3 phút 26 giây)

### 1.2. Phân tích chi tiết 11 bài test thất bại
Qua phân tích sâu log và chạy cô lập từng module, toàn bộ 11 test fail thuộc về 2 nhóm nguyên nhân cốt lõi:

1. **Nhóm 1: Server trên cổng 8088 chưa chạy trong lúc chạy pytest offline (7 tests):**
   - `tests/e2e/test_tier1_feature_coverage.py::TestTier1FeatureCoverage::test_feat13_constitution_convergence` (1 test):
     - Gọi `scripts/speckit_converge.py`. Phần 3 của kịch bản thực hiện kiểm thử tự động trên máy chủ thương mại sống (`http://127.0.0.1:8088` và `ws://127.0.0.1:8088/ws`).
     - Do server FastAPI chưa bật trước khi chạy toàn bộ test, 10 route HTTP (`/`, `/auth`, `/wokwi`, `/logs`, `/archify`, `/archify/erd`, `/archify/devops`, `/api/voice_auth/profiles`, `/api/auth3/overview`, `/api/server_logs_and_db`) và WebSocket `/ws` bị từ chối kết nối (`WinError 10061: No connection could be made because the target machine actively refused it`).
     - Script ghi nhận 11 điểm lệch so với Spec Kit và fail.
   - `tests/test_challenger_m5_devtools.py` (6 tests):
     - Kiểm thử Playwright Chromium/Edge headless đối với 6 route: `/`, `/auth`, `/guest_enroll`, `/wokwi`, `/logs`, `/app`.
     - Nhận lỗi `playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:8088/...`.

2. **Nhóm 2: Ô nhiễm trạng thái Singleton `_REST_ENGINE` khi chạy hàng loạt (4 tests):**
   - `tests/test_phase1_bugfixes_20261104.py`:
     - Khi chạy độc lập (`python -X utf8 -m pytest tests/test_phase1_bugfixes_20261104.py -v`), **toàn bộ 6/6 tests đều PASS 100%**!
     - Khi chạy trong chuỗi 684 tests, các bài test âm thanh và đối kháng phía trước đã thay đổi trạng thái của `_REST_ENGINE.devices` và `mqtt_bridge` mà fixture của module chưa làm sạch triệt để trước lượt chạy đầu tiên.

### 1.3. Khuyến nghị cho CI/CD & Đội Thực thi (Implementer)
- Thêm fixture auto-reset toàn diện trong `tests/conftest.py` để mọi test chạy độc lập và không phụ thuộc thứ tự.
- Đối với các bài test live server (`test_challenger_m5_devtools.py`, `speckit_converge.py`), tích hợp fixture tự động khởi động server uvicorn nền hoặc kiểm tra cờ live-server để đạt **100% PASS (684/684)** khi chạy lệnh kiểm thử chính thức.

---

## 2. Thông tin Xác thực (Credentials), Fixtures & Luồng 3 Vai

Dữ liệu được trích xuất trực tiếp từ mã nguồn thực tế tại [simulator/auth/constants_and_crypto.py](file:///C:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/auth/constants_and_crypto.py), [simulator/auth/qr_totp_mixin.py](file:///C:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/auth/qr_totp_mixin.py) và cơ sở dữ liệu SQLite:

### 2.1. Cấp 1: Chủ nhà (Owner / Admin)
- **Tài khoản đăng nhập:** `nep94121@gmail.com`
- **Mật khẩu mặc định:** `123456` (lưu mã băm PBKDF2 HMAC-SHA256 trong hệ thống)
- **Mã tài khoản (Account ID):** `tuan_anh`
- **Tên hiển thị:** `Nguyễn Tuấn Anh`
- **Cấp bậc (Tier):** `1` | **Vai trò:** `ADMIN`
- **Quyền hạn:**
  - Mở/Khóa Cửa chính (D1) & Còi báo động (D8).
  - Điều khiển toàn bộ Đèn khách (D2), Đèn ngủ (D7), Máy bơm (D3), Điều hòa (IR), Quạt (D6).
  - Tạo 2 đường link mời (cho Cấp 2 và Cấp 3).
  - Sinh mã QR động cho khách với các mốc thời hạn.
  - Cấu hình luật tự động và giải phóng Khóa An Ninh khi sai giọng 3 lần.
- **Biểu diễn Session:**
  ```json
  {
    "email": "nep94121@gmail.com",
    "tier": 1,
    "display_name": "Nguyễn Tuấn Anh",
    "role": "ADMIN",
    "account_id": "tuan_anh"
  }
  ```

### 2.2. Cấp 2: Thành viên Gia đình (Family Member)
- **Tài khoản mẫu A:**
  - **Email:** `thanhviena.hust@gmail.com`
  - **Mật khẩu:** `GiaDinh@123`
  - **Mã tài khoản:** `thanh_vien_a`
  - **Tên hiển thị:** `Thành viên A (Người nhà)`
  - **Cấp bậc (Tier):** `2` | **Vai trò:** `MEMBER`
- **Tài khoản mẫu B:**
  - **Email:** `thanhvienb.hust@gmail.com`
  - **Mật khẩu:** `GiaDinh@456`
  - **Mã tài khoản:** `thanh_vien_b`
  - **Tên hiển thị:** `Thành viên B (Người nhà)`
  - **Cấp bậc (Tier):** `2` | **Vai trò:** `MEMBER`
- **Quyền hạn:**
  - Bật/Tắt thiết bị sinh hoạt: Đèn khách (D2), Đèn ngủ (D7), Máy bơm (D3), Quạt (D6), Điều hòa.
  - Chỉ tạo được 1 đường link mời xuống Cấp 3 (Khách).
  - **BỊ CHẶN TUYỆT ĐỐI:** Mở Cửa chính (D1) và Còi báo động (D8) — vi phạm sẽ trả về RBAC Blocked / 403.

### 2.3. Cấp 3: Khách (Guest) & Luồng Bắt tay QR Handshake
- **Tài khoản mẫu có sẵn:**
  - **Email:** `khachc.guest@gmail.com`
  - **Mật khẩu:** `Khach@789`
  - **Mã tài khoản:** `khach_c`
  - **Tên hiển thị:** `Khách C (Tầng 3)`
  - **Cấp bậc (Tier):** `3` | **Vai trò:** `CHILD_GUEST`
  - **Quyền hạn:** Chỉ bật/tắt đèn và quạt cơ bản; bị chặn Cửa chính, Còi, hẹn giờ và luật tự động.
- **Luồng Bắt tay Mã QR Động (Dynamic QR TOTP Handshake Flow):**
  1. **Sinh mã QR:**
     - Chủ nhà (C1) hoặc Người nhà (C2) gọi `GET /api/auth3/guest_qr_current?duration=1d&host=localhost:8088`.
     - Hệ thống tính mã TOTP 16 ký tự hex qua `hmac-sha256` với khóa bí mật `"bk_smarthome_totp_salt_2026"` theo cửa sổ thời gian 10 giây (`window = int(now // 10)`).
     - Hỗ trợ 5 mốc thời hạn: `1d` (24h), `2d` (48h), `1w` (7 ngày), `1m` (30 ngày), `1y` (365 ngày).
  2. **Quét mã & Bắt tay (Handshake):**
     - Khách mở `/guest_enroll?token={token}&window={window}&dur=1d` hoặc app điện thoại quét mã.
     - Gọi `POST /api/auth3/guest_qr_handshake` với payload `{"token": token, "window": window, "duration_type": "1d"}`.
     - Cửa sổ chấp nhận token rộng 180 giây (18 chu kỳ lùi, 2 chu kỳ tiến) chống trễ mạng.
     - Token sau khi bắt tay được đưa vào `used_qr_tokens` (Single-Use Token, không cho phép dùng lại).
  3. **Phiên khách tạm thời (Guest Session):**
     - Sinh `guest_session_id = f"guest_sess_{int(now)}_{token[:6]}"`.
     - Có hiệu lực 15 phút (`session_expires_at = now + 900s`) để hoàn tất thu âm giọng nói hoặc xác minh OTP Gmail (`POST /api/auth3/guest_qr_complete_voice`, `POST /api/auth3/guest_qr_send_otp`, `POST /api/auth3/guest_qr_verify_otp`).
     - Sau khi hoàn tất, phiên khách có hiệu lực theo thời hạn đã chọn (`duration_seconds`), hiển thị huy hiệu `Khách · Cấp 3` và thời hạn còn lại.

---

## 3. Chiến lược Kiểm thử Thực tế trên Trình duyệt & HTTP (http://localhost:8088)

Áp dụng cho toàn bộ 13 trang, modal và màn hình mới theo đặc tả `DESIGN_NEW_PAGES.md`:

### 3.1. Danh mục các màn hình cần kiểm thử
| Mã Mockup | Tên màn hình / Trạng thái | Đường dẫn / Surface | Vai trò kiểm thử |
|---|---|---|---|
| `np_01` | Mất kết nối (Offline) + `sw.js` | `/offline`, Cache SW | Cả 3 vai |
| `np_02` | Lỗi 404 không tìm thấy trang | `/404`, mọi URL lạ | Cả 3 vai |
| `np_03` | Lỗi 500/503 hệ thống bận | `/500`, `/503` | Cả 3 vai |
| `np_04` | Lỗi QR hết hạn / Đã dùng | `/qr_expired`, `/guest_enroll` lỗi | Khách C3 |
| `np_05` | Lỗi 403 không đủ quyền / hết hạn | `/403`, thao tác vượt quyền | Gia đình C2, Khách C3 |
| `np_06` | Modal Khóa an ninh (Lockdown) | `#securityLockdownModal` trên `/`, `/app` | Khi sai giọng 3 lần |
| `np_07` | Popup Quyền Micro / Lỗi HTTPS | `#micPermissionModal` trên `/`, `/app` | Cả 3 vai khi mic bị chặn |
| `np_08` | Banner Mất kết nối WebSocket | `#wsReconnectBanner` đầu trang `/`, `/app` | Cả 3 vai khi đứt WS |
| `np_m1` | M1: Nhà & Cảm biến thực tế | `/app` (Tab Nhà) | Cả 3 vai |
| `np_m2` | M2: 4 Tab độc lập & Tài khoản | `/app` (Tab Tài khoản + Đăng xuất) | Chủ nhà, Gia đình, Khách |
| `np_m3` | M3: Quên mật khẩu OTP Gmail | `/app` (Form Quên MK 3 bước) | Chủ nhà, Gia đình |
| `np_m4` | M4: Bottom-sheet thu âm giọng | `/app` (Sheet sóng âm + đếm giây) | Cả 3 vai |
| `np_m5` | M5: Camera quét QR trong App | `/app` (Viewfinder quét mã QR) | Khách C3 |

### 3.2. Phương pháp Kiểm thử Tự động qua Playwright (Headless Browser)
1. **Thiết lập Môi trường:**
   - Sử dụng thư viện `playwright.async_api` (đã cài đặt sẵn trên máy LENOVO).
   - Trình duyệt: Chromium hoặc Microsoft Edge (`channel="msedge"`).
   - Viewport:
     - Desktop: `1280 x 720` (cho `/`, `/auth`, `/logs`, `/wokwi`, `/offline`, `/404`, `/500`, `/403`).
     - Mobile App: `390 x 844` với `device_scale_factor=3` (cho `/app`).
2. **Cơ chế Tiêm Session (Session Injection) cho 3 Vai:**
   ```python
   # Chủ nhà (Tier 1)
   await page.evaluate("""() => {
       localStorage.setItem('smarthome_auth_session', JSON.stringify({
           email: 'nep94121@gmail.com',
           tier: 1,
           display_name: 'Nguyễn Tuấn Anh',
           role: 'ADMIN'
       }));
   }""")
   
   # Gia đình (Tier 2)
   await page.evaluate("""() => {
       localStorage.setItem('smarthome_auth_session', JSON.stringify({
           email: 'thanhviena.hust@gmail.com',
           tier: 2,
           display_name: 'Thành viên A',
           role: 'MEMBER'
       }));
   }""")
   
   # Khách (Tier 3)
   await page.evaluate("""() => {
       localStorage.setItem('smarthome_auth_session', JSON.stringify({
           email: 'khachc.guest@gmail.com',
           tier: 3,
           display_name: 'Khách C',
           role: 'CHILD_GUEST',
           expires_at: Date.now() + 86400000
       }));
   }""")
   ```
3. **Tiêu chuẩn Nghiệm thu Trình duyệt (Zero Error Invariants):**
   - 0 Uncaught JavaScript Page Errors (`pageerror`).
   - 0 Console Errors (`console.error`).
   - 0 HTTP 404/500 trên các file tài nguyên tĩnh (`.js`, `.css`, `.svg`, `.json`).

---

## 4. Đánh giá DOM Tests Hiện tại & Các Bài Test Cần Bổ Sung Cho Phase 2

### 4.1. Đánh giá Bộ Test DOM Hiện hữu (`tests/test_challenger_m4_dom.py`)
- **Trạng thái hiện tại:** 36/36 tests PASSED 100% trong 1.98 giây.
- **Cơ chế kiểm soát cực kỳ nghiêm ngặt:**
  1. Quét toàn bộ inline events (`onclick`, `onsubmit`, `onchange`...) và bắt buộc 100% hàm phải có mặt trên `window.*`.
  2. Quét mọi ID gọi qua `document.getElementById` hoặc `#querySelector` trong JS; nếu thiếu trong HTML mà không có null guard sẽ bị đánh FAIL.
  3. Quét mọi lệnh chained `.addEventListener` trực tiếp không qua biến kiểm tra null.
  4. Nạp file JS vào Node.js VM headless runner để xác nhận không lỗi cú pháp hoặc runtime.
- **Ràng buộc an toàn cốt lõi:**
  - Phải **bảo toàn nguyên vẹn 103 DOM IDs** trong `mobile_app/index.html` và **81 DOM IDs** trong `simulator/static/index.html`. Không được xóa hoặc đổi tên bất kỳ ID hiện có nào để không làm gãy các test E2E/Challenger!

### 4.2. Danh mục Test Mới Cần Viết Cho Phase 2 (`tests/test_phase2_dom_and_pages.py`)
Cần bổ sung một file test chuyên biệt cho Phase 2 gồm các nhóm kiểm thử sau:
1. **Kiểm thử 5 trang tĩnh lỗi (`offline.html`, `404.html`, `500.html`, `qr_expired.html`, `403.html`):**
   - Kiểm tra HTML hợp lệ, charset UTF-8, viewport responsive.
   - Kiểm tra chuẩn màu sắc DESIGN_SYSTEM: primary `#087d85`, background `#f5f7f7`, card `#fff`, line `#e5ebec`.
   - Kiểm tra các liên kết điều hướng tĩnh (`href="/"`, `href="/app"`) hoạt động bình thường không cần JavaScript.
2. **Kiểm thử Modal An Ninh, Mic & WS Banner trong DOM:**
   - Kiểm tra sự hiện diện của `#securityLockdownModal`, `#micPermissionModal`, `#wsReconnectBanner` trong `index.html` và `mobile_app/index.html`.
   - Kiểm tra `aria-modal="true"`, `role="alertdialog"` hoặc `role="status"`, nhãn đóng `aria-label="Đóng"`.
3. **Kiểm thử 5 Màn hình Mobile Part 2 trong `/app`:**
   - M1: Hiển thị đúng 2 ô cảm biến Nhiệt độ (28.5°C), Độ ẩm đất (62%), trạng thái Cửa chính/Còi báo động, placeholder 3D 16:9.
   - M2: Tách biệt 4 tab độc lập `#tabHomeSection`, `#tabDevicesSection`, `#tabVoiceSection`, `#tabAccountSection`. Nút `#btnMobileLogout` tồn tại và gọi đúng hàm đăng xuất.
   - M3: Form quên mật khẩu gồm 3 bước với ô OTP 6 số (`inputmode="numeric"`, `autocomplete="one-time-code"`).
   - M4: Bottom-sheet thu âm `#mobileVoiceSheet` có sóng âm, đồng hồ đếm `00:03 / 00:05`, câu mẫu và trạng thái kết quả.
   - M5: Scanner view `#mobileQrScannerView` có khung quét 4 góc (`tl`, `tr`, `bl`, `br`), nút Bật camera và Nhập mã.
4. **Kiểm thử FastAPI 404 Content-Negotiation:**
   - Request HTTP thường (Accept: `text/html`) tới URL không tồn tại -> Trả về `404.html` (Content-Type: `text/html; charset=utf-8`).
   - Request API (Accept: `application/json` hoặc URL `/api/*`) -> Giữ nguyên JSON `{"detail": "Not Found"}`.
5. **Kiểm thử Service Worker (`sw.js`):**
   - File `sw.js` được phục vụ tại `/sw.js` với header `Service-Worker-Allowed: /`.
   - Precache offline HTML và font fallback.
   - Chiến lược fetch `network-first` cho navigation request; khi offline trả về trang `offline.html` từ cache.

---

## 5. Đánh giá Cấu hình Vercel (`vercel.json`) & Yêu cầu Bổ sung

### 5.1. Hiện trạng `vercel.json`
```json
{
  "version": 2,
  "framework": null,
  "cleanUrls": false,
  "routes": [
    { "src": "^/api/(.*)$", "dest": "/api/index.py" },
    { "src": "^/static/(.*)$", "dest": "/simulator/static/$1" },
    { "src": "^/test_audio/(.*)$", "dest": "/test_audio/$1" },
    { "src": "^/app/?$", "dest": "/mobile_app/index.html" },
    { "src": "^/auth/?$", "dest": "/simulator/static/auth.html" },
    { "src": "^/guest_enroll/?$", "dest": "/simulator/static/guest_enroll.html" },
    { "src": "^/guest-qr/?$", "dest": "/simulator/static/guest_enroll.html" },
    { "src": "^/logs/?$", "dest": "/simulator/static/logs.html" },
    { "src": "^/wokwi/?$", "dest": "/simulator/static/wokwi.html" },
    { "src": "^/archify/devops/?$", "dest": "/docs/kien_truc/devops-cicd-pipeline.workflow.html" },
    { "src": "^/archify/?$", "dest": "/docs/kien_truc/smart-home-voice-ai.architecture.html" },
    { "src": "^/$", "dest": "/simulator/static/index.html" }
  ]
}
```

### 5.2. Các điểm thiếu sót và điều chỉnh bắt buộc cho Phase 2
1. **Service Worker Root Scope (`/sw.js`):**
   - Service Worker bắt buộc phải nằm ở root URL `/sw.js` để có phạm vi (scope) toàn bộ website. Nếu để ở `/static/sw.js`, phạm vi chỉ giới hạn trong `/static/`.
   - Cần bổ sung route:
     ```json
     {
       "src": "^/sw\\.js$",
       "dest": "/simulator/static/sw.js",
       "headers": {
         "Service-Worker-Allowed": "/",
         "Cache-Control": "no-cache, no-store, must-revalidate"
       }
     }
     ```
2. **Định tuyến cho các trang lỗi tĩnh mới:**
   ```json
   { "src": "^/offline/?$", "dest": "/simulator/static/offline.html" },
   { "src": "^/404/?$", "dest": "/simulator/static/404.html" },
   { "src": "^/500/?$", "dest": "/simulator/static/500.html" },
   { "src": "^/qr_expired/?$", "dest": "/simulator/static/qr_expired.html" },
   { "src": "^/403/?$", "dest": "/simulator/static/403.html" }
   ```
3. **Cấu hình Fallback 404 tại tầng Vercel CDN:**
   - Để các URL không khớp trên Vercel không bị hiển thị trang 404 mặc định của Vercel, đặt rule fallback ở cuối danh sách routes:
     ```json
     { "src": "/(.*)", "status": 404, "dest": "/simulator/static/404.html" }
     ```

---

## 6. Kế hoạch Phối hợp Thực thi (Execution Matrix)

| Nhóm việc | Nội dung chính | Yêu cầu QA tương ứng |
|---|---|---|
| **(a) Web Error Pages + sw.js** | Tạo `offline.html`, `404.html`, `500.html`, `qr_expired.html`, `403.html` và `sw.js` trong `simulator/static/`. Thêm exception handler trong `simulator/server.py`. | Kiểm tra mã HTTP, Content-Type, CSS layout, Service Worker offline cache. |
| **(b) Security Banner/Modal** | Tích hợp `#securityLockdownModal`, `#micPermissionModal`, `#wsReconnectBanner` vào `index.html` và `mobile_app/index.html`. | Kiểm tra không phá vỡ DOM IDs cũ, kiểm tra null safety trong `app.js` và `mobile_app.js`. |
| **(c) Mobile /app 5 Màn** | Tách 4 tab độc lập, thêm Home Sensors M1, Account card M2, Forgot OTP M3, Voice sheet M4, QR scanner M5. | Kiểm tra chuyển tab mượt mà, kiểm tra responsive `390x844`, Samsung Internet safe area. |
| **(d) Vercel Config** | Cập nhật `vercel.json` phục vụ `/sw.js` và các route lỗi. | Xác minh router Vercel và build artifact. |
| **(e) QA & Pytest** | Viết `tests/test_phase2_dom_and_pages.py`, thiết lập fixture cô lập `_REST_ENGINE`, chạy lại toàn bộ test đạt 100% PASS. | Chạy toàn bộ 684+ pytest đạt Exit Code 0. |

Báo cáo này cung cấp đầy đủ dữ kiện kỹ thuật chính xác 100% để đội ngũ triển khai bắt tay thực hiện ngay mà không cần suy đoán.
