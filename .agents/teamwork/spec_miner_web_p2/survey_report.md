# BÁO CÁO ĐẶC TẢ CHI TIẾT (SPECIFICATION SURVEY REPORT)
**Đối tượng**: Các trang lỗi Web (Offline, 404, 500/503, QR Expired, 403), Modals & Banners (Lockdown, Mic Permission, WS Reconnect), Service Worker (sw.js) và Cơ chế Định tuyến FastAPI.
**Người thực hiện**: `spec_miner_web_p2` (Teamwork Specification Miner)
**Ngày khảo sát**: 2026-11-04
**Trạng thái**: Hoàn tất khảo sát độc lập (Read-Only Specification Probe)

---

## 1. TỔNG QUAN & NGUỒN TÀI LIỆU QUY CHUẨN (AUTHORITATIVE SOURCES)

Báo cáo khảo sát này được tổng hợp từ việc đối soát trực tiếp mã nguồn, bản thiết kế giao diện Codex và các tệp mockup HTML thực tế:
1. **Đặc tả thiết kế UX/UI**: `ui_mockups/v2_new_pages/DESIGN_NEW_PAGES.md` (Phần 1: Quy chuẩn chung, Mục 01 đến 08; Phần 2: Mobile M1 đến M5).
2. **Các tệp HTML Mockup chuẩn**:
   - `ui_mockups/v2_new_pages/np_01_offline.html` (Mất kết nối & Ngoại tuyến)
   - `ui_mockups/v2_new_pages/np_02_404.html` (Lỗi 404 Không tìm thấy trang)
   - `ui_mockups/v2_new_pages/np_03_500.html` (Lỗi 500/503 Hệ thống đang bận)
   - `ui_mockups/v2_new_pages/np_04_qr_expired.html` (Mã QR hết hạn / Đã dùng)
   - `ui_mockups/v2_new_pages/np_05_403.html` (Lỗi 403 Không đủ quyền truy cập)
   - `ui_mockups/v2_new_pages/np_06_lockdown.html` (Hộp thoại Khóa an ninh)
   - `ui_mockups/v2_new_pages/np_07_mic_permission.html` (Hộp thoại Quyền Microphone / HTTPS)
   - `ui_mockups/v2_new_pages/np_08_ws_banner.html` (Thanh thông báo Kết nối lại WebSocket)
3. **Mã nguồn Server & Frontend hiện hữu**:
   - `simulator/server.py` (FastAPI app, middleware, mounts, router includes)
   - `simulator/static/index.html` & `simulator/static/js/app.js` (Web Dashboard & 3D Twin)
   - `simulator/static/house3d.js` (Mô hình 3D Three.js 1821 dòng, Raycaster, camera toolbar)
   - `simulator/static/guest_enroll.html` & `simulator/static/js/guest_enroll.js` (Luồng quét QR Khách)
   - `simulator/static/auth.html` & `simulator/static/js/auth.js` (Xác thực 3 tầng & Allowlist)
   - `mobile_app/index.html` & `simulator/static/js/mobile_app.js` (Giao diện Mobile PWA 5 tab)
   - `simulator/voice_auth.py` (Cơ chế 3-Strike Silent Lockout & DSP)
   - `simulator/api/routes_devices.py`, `routes_auth.py`, `routes_qr.py` (FastAPI Endpoints)
4. **Bộ kiểm thử đối kháng (Test Suites)**:
   - `tests/test_challenger_m4_dom.py` (36 test kiểm tra toàn vẹn ID và window.*)
   - `tests/test_challenger_m3_stress_dom_raycaster.py` (20 test Three.js & house3d.js)
   - `tests/test_challenger_m2_gate_ux_empirical.py` (Kiểm thử khóa Login Gate)
   - `tests/test_phase1_bugfixes_20261104.py` (6 test hồi quy Phase 1)

---

## 2. QUY CHUẨN THIẾT KẾ & THƯƠNG HIỆU HỆ THỐNG (DESIGN SYSTEM CONTRACT)

Toàn bộ các trang lỗi, modal và banner bắt buộc phải tuân thủ nghiêm ngặt bảng thông số thiết kế từ `DESIGN_NEW_PAGES.md`:

| Thuộc tính | Giá trị chuẩn | Ghi chú áp dụng |
|---|---|---|
| **Font chữ** | `'Be Vietnam Pro', sans-serif;` | Import từ Google Fonts (weights: 400, 500, 600) |
| **Màu nền trang (`--page`)** | `#f5f7f7` | Nền mềm dịu mắt, đồng bộ toàn hệ sinh thái |
| **Màu thẻ trắng (`--card`)** | `#ffffff` | Thẻ nội dung chính, bo tròn 16px, viền 1px `#e5ebec` |
| **Màu chữ chính (`--ink`)** | `#172b31` | Độ tương phản cao, chuẩn a11y WCAG AAA |
| **Màu chữ phụ (`--muted`)** | `#687a80` | Dùng cho nhãn phụ, mô tả, đếm ngược |
| **Màu nhấn chính (`--accent`)** | `#087d85` | Màu xanh mòng két (Teal) đặc trưng thương hiệu |
| **Màu nền mềm (`--soft`)** | `#e6f3f2` | Nền icon badge, thẻ active |
| **Nguy hiểm / Báo động (`--red`)**| `#c0392b` / nền mềm `#fdecea` | Dùng cho Khóa an ninh, lỗi nghiêm trọng, còi báo |
| **Cảnh báo (`--orange`)** | `#d97706` / nền mềm `#fff7ed` | Dùng cho Mất kết nối WebSocket, đếm ngược |
| **Thành công (`--green`)** | `#15803d` / nền mềm `#ecfdf5` | Dùng cho Đã khôi phục kết nối, xác thực ĐẠT |
| **Độ bo góc (Border Radius)** | 16px (Card), 10px-12px (Button/Note), 99px (Pill) | Thống nhất trên tất cả màn hình |
| **Đổ bóng (Box Shadow)** | `0 6px 24px rgba(31,58,62,.045)` | Bóng đổ thanh thoát, không gắt |
| **Kích thước Card Desktop** | `width: min(560px, 100%); padding: 36px;` | Đặt giữa viewport (`place-items: center`) |
| **Kích thước Mobile** | `padding: 24px 16px; min-height: 100dvh;` | Nút chuyển sang dạng xếp dọc (`width: 100%`) |
| **Quy chuẩn Icon** | SVG Lucide 24×24, `fill="none"`, `stroke-width="1.8"`, `stroke-linecap="round"`, `stroke-linejoin="round"` | Tuyệt đối KHÔNG dùng emoji, glyph trang trí |

---

## 3. DANH MỤC TÍNH NĂNG ĐÃ KHẢO SÁT (FEATURES DISCOVERED)

```
## Features Discovered
| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Web Error Page | Offline Fallback Page (`offline.html`) | Hiển thị thông báo mất kết nối mạng/máy chủ khi không thể tải ứng dụng, cung cấp nút Thử lại và Chuyển server dự phòng | Sự kiện mạng mất kết nối, fetch same-origin thất bại, offline event | Giao diện cảnh báo wifi-off, thẻ trạng thái mạch (dữ liệu cuối/chưa xác nhận), đếm ngược thử lại 3-5s | Không lặp reload vô hạn; ẩn nút dự phòng nếu chưa cấu hình URL tin cậy | `DESIGN_NEW_PAGES.md` §01, `np_01_offline.html` |
| 2 | Service Worker | PWA Service Worker (`sw.js`) | Quản lý bộ nhớ đệm ngoại tuyến: precache offline.html, tài sản shell; điều hướng network-first; trả cache khi mất mạng | Navigation request (`request.mode === 'navigate'`) | HTTP Response 200 từ network hoặc Cache Response `offline.html` (`Content-Type: text/html`) | Bỏ qua không cache `/api/*`, POST/PUT/DELETE; tự động claim/dọn cache cũ khi activate | `DESIGN_NEW_PAGES.md` §01, HTML5 Service Worker W3C Spec |
| 3 | Web Error Page | 404 Not Found Page (`404.html`) | Trang báo lỗi 404 chuẩn giao diện cho trình duyệt khi truy cập URL không tồn tại | HTTP GET tới đường dẫn không tồn tại từ trình duyệt (`Accept: text/html`) | HTTP Status 404 HTML với icon `file-question`, nút "Về Trang chủ" (`/`) và "Mở Ứng dụng Điện thoại" (`/app`) | Không in param/path của user ra HTML để chống rò rỉ token và XSS | `DESIGN_NEW_PAGES.md` §02, `np_02_404.html`, `server.py` |
| 4 | Backend Routing | FastAPI 404 Content-Negotiation Handler | Bộ xử lý ngoại lệ 404 thông minh phân biệt yêu cầu duyệt web và gọi API | HTTP Request không khớp route | `404.html` cho navigation (`Accept: text/html`); `{"detail": "Not Found"}` cho API (`/api/*`) hoặc client json | Trả đúng HTTP Status Code 404, không nuốt mã lỗi | `ORIGINAL_REQUEST.md` R1, `simulator/server.py` |
| 5 | Web Error Page | 500/503 Server Busy Page (`500.html`) | Trang báo lỗi máy chủ quá tải hoặc gặp sự cố nội bộ | HTTP 500/503 hoặc unhandled server exception | HTTP Status 500/503 HTML với icon `server-off`, nút "Tải lại trang", "Điều khiển cơ bản" / "Về Trang chủ" | Không reload liên tục tự động nếu lỗi lặp lại | `DESIGN_NEW_PAGES.md` §03, `np_03_500.html` |
| 6 | Web Error Page | QR Code Expired / Used Page (`qr_expired.html`) | Trang thông báo mã QR mời khách đã hết hạn TOTP (10s) hoặc handshake (180s) hoặc đã sử dụng | URL `/guest_enroll` chứa token hết hạn/đã dùng, hoặc quét QR không hợp lệ | HTML với icon `qr-code`, tiêu đề phản ánh nguyên nhân ("Mã QR đã hết hạn" / "Mã QR này đã được sử dụng"), nút "Quét mã mới" | Tuyệt đối KHÔNG hiển thị nút "Tạo mã mới" cho Khách; không làm lộ token ra UI/log | `DESIGN_NEW_PAGES.md` §04, `np_04_qr_expired.html`, `routes_qr.py` |
| 7 | Web Error Page | 403 Forbidden Page (`403.html`) | Trang báo lỗi không đủ quyền thực thi thao tác hoặc phiên Khách Cấp 3 đã kết thúc | HTTP 403 hoặc truy cập trang bị cấm | HTML với icon `shield-off`, badge "Khách · Cấp 3", nút "Quay về Nhà" (`/app`), "Đăng nhập tài khoản khác" | Không cấp quyền Chủ nhà qua client; nếu phiên không có vai trò thì chỉ hiện "Không đủ quyền truy cập" | `DESIGN_NEW_PAGES.md` §05, `np_05_403.html`, `routes_devices.py` |
| 8 | Modal Dialog | Security Lockdown Modal (`np_06_lockdown.html`) | Hộp thoại phong tỏa an ninh khẩn cấp khi phát hiện 3 lần nhận diện giọng nói thất bại | Sự kiện `voice_auth` có `strike_count >= 3` hoặc cờ `silent_ignore = true` | Alertdialog overlay che toàn màn hình, viền đỏ, icon `shield-alert`, ô nhập Mật khẩu Chủ nhà / OTP Gmail | KHÔNG có nút đóng 'X'; không cho click ngoài hủy; chỉ mở khóa khi server xác thực 200 OK | `DESIGN_NEW_PAGES.md` §06, `np_06_lockdown.html`, `voice_auth.py` |
| 9 | Modal Dialog | Mic Permission / HTTPS Modal (`np_07_mic_permission.html`) | Hộp thoại thông báo khi trình duyệt bị chặn quyền microphone hoặc truy cập qua HTTP không an toàn | Lỗi `NotAllowedError`, `NotFoundError` từ `getUserMedia`, hoặc `location.protocol !== 'https:'` trên remote IP | Dialog với icon `mic-off`, hướng dẫn cấp quyền Micro, nút "Thử lại", "Mở bản HTTPS", "Đóng" | Tự động phân nhánh: nếu HTTP không an toàn hiện "Mở bản HTTPS"; nếu đã chặn hiện hướng dẫn cài đặt | `DESIGN_NEW_PAGES.md` §07, `np_07_mic_permission.html`, `app.js` |
| 10 | Banner Component | WebSocket Reconnect Banner (`np_08_ws_banner.html`) | Thanh trạng thái nổi trên cùng vùng nội dung báo mất kết nối thời gian thực và tự kết nối lại | `ws.onclose`, `ws.onerror`, mất mạng | Banner cảnh báo màu cam với số lần thử (lần 1/5), nút "Kết nối ngay"; khi phục hồi chuyển sang màu xanh 2s rồi ẩn | Không đếm số lần WebSocket nếu toàn bộ mạng thiết bị offline; disable nút khi đang kết nối dở | `DESIGN_NEW_PAGES.md` §08, `np_08_ws_banner.html`, `app.js` |
```

---

## 4. BẢNG TRƯỜNG HỢP BIÊN & HÀNH VI QUAN SÁT THỰC NGHIỆM (EDGE CASES)

```
## Edge Cases
| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | FastAPI 404 Routing | `GET /nonexistent_url` với header `Accept: text/html` | Trả về 404 Not Found kèm nội dung tệp `404.html` (Content-Type: text/html; charset=utf-8) |
| 2 | FastAPI 404 Routing | `GET /api/nonexistent_route` với header `Accept: */*` hoặc `application/json` | Trả về HTTP Status 404 với JSON Body `{"detail": "Not Found"}` (Content-Type: application/json) |
| 3 | FastAPI 404 Routing | `GET /api/devices/xyz` khi ID không tồn tại | Trả về JSON 404, bảo lưu nguyên vẹn các test API của backend |
| 4 | sw.js Caching | Người dùng truy cập lần đầu khi server chưa bật | Browser hiển thị lỗi mạng gốc (Native Network Error) do SW chưa kịp cài đặt (đúng theo giới hạn W3C) |
| 5 | sw.js Caching | Người dùng điều hướng trang sau khi đã cài SW nhưng mạng bị ngắt | SW bắt `FetchEvent`, nhận thấy network thất bại, trả về `offline.html` từ CacheStorage với HTTP 200 |
| 6 | sw.js Caching | Ứng dụng gọi `POST /api/device` khi đang offline | SW bỏ qua (không can thiệp non-GET), fetch API ném TypeError, ứng dụng bắt lỗi hiển thị offline UI |
| 7 | sw.js Caching | Cập nhật phiên bản code/asset mới (`CACHE_VERSION = 'v2'`) | Sự kiện `activate` duyệt qua `caches.keys()`, xóa toàn bộ cache cũ khác version, gọi `clients.claim()` |
| 8 | Offline Page (`offline.html`) | Thiết bị kết nối mạng trở lại (`window.ononline`) | Tự động kích hoạt kiểm tra kết nối nhẹ tới same-origin (`/favicon.ico`), nếu thành công chuyển về URL gốc |
| 9 | Offline Page (`offline.html`) | Chưa cấu hình URL server dự phòng | Nút "Chuyển sang Server Dự phòng" bị ẩn hoặc hiển thị dòng chú thích "Chỉ hiện nút dự phòng khi có máy chủ tin cậy" |
| 10 | 404 Page (`404.html`) | Người dùng gõ URL chứa mã độc hoặc token (`/admin?token=xyz<script>`) | Trang 404 tuyệt đối KHÔNG in tham số query hoặc pathname ra DOM, chống XSS và chống lộ token |
| 11 | 404 Page (`404.html`) | Người dùng tắt JavaScript hoàn toàn | Các liên kết "Về Trang chủ" (`/`) và "Mở Ứng dụng Điện thoại" (`/app`) vẫn điều hướng bình thường (thẻ `<a>` thuần) |
| 12 | 500 Page (`500.html`) | Máy chủ trả mã 503 Service Unavailable | Tiêu đề giữ "Hệ thống đang bận", nhãn chi tiết hiển thị "Dịch vụ tạm gián đoạn", có nút Tải lại trang |
| 13 | QR Expired (`qr_expired.html`) | Token TOTP hết hạn sau 10s hoặc phiên handshake hết hạn 180s | Hiển thị H1 "Mã QR đã hết hạn", giải thích "Vui lòng nhờ Chủ nhà tạo mã mời mới rồi quét lại" |
| 14 | QR Expired (`qr_expired.html`) | Token đã được sử dụng 1 lần trước đó (`consumed_at is not None`) | Hiển thị H1 "Mã QR này đã được sử dụng", chuyển sang trạng thái đã dùng |
| 15 | QR Expired (`qr_expired.html`) | Khách truy cập không có mạng khi xác thực token | Không kết luận là mã đã dùng; chuyển sang hiển thị trạng thái mất kết nối mạng |
| 16 | 403 Forbidden (`403.html`) | Khách Cấp 3 truy cập bật Còi báo động hoặc xem Nhật ký bí mật | Hiển thị "Không đủ quyền truy cập", kèm role pill "Khách · Cấp 3", nút Quay về Nhà và Đổi tài khoản |
| 17 | 403 Forbidden (`403.html`) | Khách hết hạn thời gian truy cập (`expires_at < now`) | Hiển thị "Thời hạn truy cập dành cho Khách của bạn đã kết thúc", hướng dẫn liên hệ Chủ nhà gia hạn |
| 18 | Lockdown Modal (`np_06_lockdown.html`) | Người lạ thử giọng nói 3 lần liên tiếp thất bại (`strike_count >= 3`) | Modal phong tỏa hiện lên với lớp phủ che mờ; kiểm tra còi: nếu `alarm_siren=ON` thông báo rõ còi đang hú |
| 19 | Lockdown Modal (`np_06_lockdown.html`) | Người dùng bấm phím Escape hoặc click vào vùng tối bên ngoài modal | Modal KHÔNG ĐÓNG, không có nút X, bắt buộc phải nhập Mật khẩu Chủ nhà hoặc OTP Gmail hợp lệ |
| 20 | Lockdown Modal (`np_06_lockdown.html`) | Chủ nhà chọn phương thức "Dùng mã OTP Gmail" | Form chuyển sang ô nhập 6 số, kích hoạt gửi OTP qua `/api/auth3/forgot_password_send_otp` |
| 21 | Lockdown Modal (`np_06_lockdown.html`) | Chủ nhà nhập đúng mật khẩu (`123456`) và xác minh thành công | Server trả về 200 OK, reset strikes về 0, tắt còi báo động (nếu chọn), modal ẩn và khôi phục điều khiển |
| 22 | Mic Permission (`np_07_mic_permission.html`) | Người dùng bấm "Block" khi trình duyệt hỏi quyền micro | Bắt lỗi `NotAllowedError`, hiện popup "Bạn đã chặn quyền micro. Mở cài đặt trang trong trình duyệt..." |
| 23 | Mic Permission (`np_07_mic_permission.html`) | Truy cập ứng dụng qua `http://192.168.2.39:8088` (HTTP không an toàn) | Phát hiện `isSecureContext === false`, hiện "Trình duyệt cần kết nối an toàn...", nút "Mở bản HTTPS" dẫn tới link HTTPS |
| 24 | WS Reconnect (`np_08_ws_banner.html`) | Mạng đứt, WebSocket bị đóng bất ngờ (`ws.onclose`) | Banner cam hiện ở đầu nội dung: "Mất kết nối thời gian thực tới ngôi nhà. Đang kết nối lại (lần 1/5)…" |
| 25 | WS Reconnect (`np_08_ws_banner.html`) | Đang trong lúc gọi `new WebSocket(...)` để thử lại | Nút "Kết nối ngay" bị disable, ghi rõ lý do "Đang thử kết nối..." để tránh spam kết nối |
| 26 | WS Reconnect (`np_08_ws_banner.html`) | Kết nối WebSocket thành công trở lại (`ws.onopen`) | Banner chuyển màu xanh lá với thông điệp "Đã khôi phục kết nối", hiển thị trong 2 giây rồi tự ẩn |
| 27 | WS Reconnect (`np_08_ws_banner.html`) | Toàn bộ thiết bị bị ngắt mạng Internet (`navigator.onLine === false`) | Banner hiển thị "Mất kết nối mạng", dừng tăng bộ đếm số lần WebSocket sai lệch |
```

---

## 5. BẢO TOÀN DANH MỤC DOM ID & WINDOW.* HOOKS (TEST INTEGRITY REGISTRY)

Hệ thống có 2 bộ test đối kháng cực kỳ nhạy cảm là `tests/test_challenger_m4_dom.py` (36 test) và `tests/test_challenger_m3_stress_dom_raycaster.py` (20 test). Nếu bất kỳ DOM ID nào bị xóa, đổi tên hoặc gán lại làm mất tính null-safe, test suite sẽ lập tức báo FAIL.

### 5.1. Danh mục DOM ID bắt buộc bảo toàn 100% trong `simulator/static/index.html`
- **Header & Trạng thái**: `#homeCurrentAccountBadge`, `#btnLogoutHome`, `#btnToggleServer`, `#connDot`, `#connText`, `#selActiveSpeaker`, `#btnReset`.
- **Mô hình 3D Toàn cảnh**: `#house-title`, `#lblCurrentCameraView`, `.camera-toolbar`, 7 nút camera preset `button[data-cam="..."]` (`overview`, `living`, `bedroom`, `door`, `garden`, `board`, `rotate`), `#house3dViewport`, `#house3dLabels`, `.viewport-note`, `.note-desktop`, `.note-mobile`.
- **Thiết bị & Điều khiển**: `#device-title`, `#deviceGrid`, `#btnOpenFirstVoiceModal`, `#deviceActiveSummary`.
- **Giọng nói & Hội thoại**: `#voice-title`, `#voiceLockoutNotice`, `#btnMicLive`, `#micBtnLabel`, `#btnMicCommit`, `#chkSpeakReply`, `#emptyVoice`, `#voiceResults`, `#liveTranscript`, `#liveAiReply`, `#textCmdForm`, `#txtCommand`, `#btnSendText`.
- **Lịch hẹn giờ & Luật**: `#schedule-title`, `#scheduleEmptyText`, `#timerList`, `#ruleList`.
- **Modal Giọng nói Trang 1**: `#firstPageVoiceModal`, `#firstVoiceEmailInput`, `#firstVoiceTierBadge`, `#btnCloseFirstVoiceModal`, `#firstVoiceTierSelect`, `#firstVoiceSpeakerNameInput`, `#firstVoicePhraseList`, `#firstVoiceSamplePhrase`, `#btnHoldRecordVoice`, `#btnRetryFirstVoiceModal`, `#btnConfirmFirstVoiceModal`, `#btnCancelFirstVoiceModal`, `#firstVoiceResultBox`.
- **Login Gate Modal**: `#homeLoginGateModal`, `#btnCloseLoginGateModal` (BẮT BUỘC có thuộc tính `hidden`), `#btnTabGateLogin`, `#btnTabGateRegister`, `#btnTabGateForgot`, `#gatePanelLogin`, `#gateLoginEmail`, `#gateLoginPassword`, `#btnSubmitGateLogin`, `#gatePanelRegister`, `#gateRegTier`, `#gateRegName`, `#gateRegEmail`, `#gateRegPassword`, `#gateRegConfirmPassword`, `#btnSubmitGateRegister`, `#gatePanelForgot`, `#gateForgotEmail`, `#btnSendForgotOtp`, `#gateForgotOtpInput`, `#gateForgotNewPassword`, `#gateForgotConfirmPassword`, `#btnSubmitForgotReset`, `#gateStatusBox`.

### 5.2. Danh mục DOM ID bắt buộc bảo toàn trong `mobile_app/index.html`
- **Login Gate Mobile**: `#mobileLoginGate`, `#btnMobileTabLogin`, `#btnMobileTabRegister`, `#mobileLoginForm`, `#mobileLoginEmail`, `#mobileLoginPassword`, `#mobileLoginMsg`, `#mobileLoginBtn`, `#mobileRegisterForm`, `#mobileRegTier`, `#mobileRegName`, `#mobileRegEmail`, `#mobileRegPassword`, `#mobileRegConfirmPassword`, `#mobileRegMsg`, `#mobileRegisterBtn`.
- **Nội dung chính**: `#mobileMainContent` (bắt đầu bằng `hidden`), `#secHome`, `#espBadge`, `#tempVal`, `#humVal`, `#soilVal`, `#rssiText`, `#mobileStrikeBadge`, `#mobileCountdownBadge`, `#pwa-house-title`.
- **Thiết bị & Lọc phòng**: `#secDevices`, `#devices-title`, `#btnToggleShowAllDevices`, `#roomFilterPills`, `#devGrid`.
- **Lịch hẹn giờ Mobile**: `#secSchedule`, `#schedule-title`, `#upcomingScheduleInline`, `#pwaScheduleForm`, `#pwaSchedTime`, `#pwaSchedDevice`, `#pwaSchedAction`.
- **Giọng nói Mobile**: `#secVoice`, `#voice-title`, `#voiceStateBadge`, `#pwaVoiceEmpty`, `#pwaVoiceResults`, `#userSaidText`, `#aiReply`, `#btnMobileMic`, `#btnMobileMicLabel`, `#cmdForm`, `#cmdInput`, `#ttsSpeakToggle`.
- **Tài khoản & QR Mobile**: `#secAuth`, `#auth-title`, `#mobileActorBadge`, `#mobileVoiceModal`, `#mobileVoiceStepLabel`, `#mobileActorSelect`, `#mobileVoiceTierInfo`, `#mobileVoiceRegisterInfo`, `#mobileVoiceRegName`, `#mobileReadingPrompt`, `#mobileVoiceRetryBtn`, `#mobileVoiceRes`, `#mobileVoiceMetrics`, `#mobileVoiceF0`, `#mobileVoiceSNR`, `#mobileFamilyCard`, `#mobileTargetTierSelect`, `#mobileTargetEmail`, `#mobileBtnAddEmail`, `#mobileAllowlistMsg`, `#mobileDynamicQrCard`, `#mobileQrCountdown`, `#mobileQrInviteTierSelect`, `#mobileQrSvgContainer`, `#mobileDynamicQrSvg`, `#mobileGuestDurSelect`, `#mobileQrTokenText`, `#mobileQrUrlText`, `#mobileQrOpenLink`, `#secHistory`, `#mqttLog`, `#mobileChangePasswordCard`, `#mobileChangePasswordForm`, `#mobileChangeEmail`, `#mobileChangeNewPassword`, `#mobileChangeConfirmPassword`, `#mobileChangePasswordMsg`, `#mobileChangePasswordBtn`.
- **Bottom Navigation**: `#mobileBottomNav` (4 tab: Nhà, Thiết bị, Giọng nói, Tài khoản).

### 5.3. Danh mục `window.*` Hooks toàn cầu bắt buộc duy trì
- **Mô hình 3D**: `window.SmartHome3D` (cung cấp `.setCameraView()`, `.updateDevices()`, v.v.).
- **Trạng thái kết nối & Thiết bị**: `window._serverConnected`, `window._latestMqtt`, `window._lastGeminiAudioChunkTs`, `window.togglePasswordVisibility`.
- **Xác thực Web (`auth.js`)**: `window.submitLayer1`, `window.submitLayer2Otp`, `window.submitLayer3Voice`, `window.completeStep1AndGoToVoice`, `window.openStepPanel`, `window.quickRecordFirstPage`, `window.startHoldRecordingFirstPage`, `window.stopHoldRecordingFirstPage`, `window.applyPresetAccount`, `window.testWrongOtp`, `window.requestForgotPasswordOtpAuthPage`.
- **Khách quét QR (`guest_enroll.js`)**: `window.initQrHandshake`, `window.doGuestHandshake`, `window.confirmAndActivateGuestVoice`, `window.recordAndEnrollGuestVoice`, `window.toggleGuestMicRecording`, `window.onGuestTierChange`, `window.onDurationChange`.
- **Ứng dụng di động (`mobile_app.js`)**: `window.submitMobileLogin`, `window.submitMobileRegister`, `window.switchMobileLoginTab`, `window.scrollToSection`, `window.filterDevicesByRoom`, `window.filterMobileHistory`, `window.toggleMobileVoiceListen`, `window.submitMobileVoiceSample`, `window.refreshMobileQr10s`, `window.copyMobileGuestLink`.

---

## 6. QUY TẮC BẢO VỆ MÔ HÌNH 3D VÀ BỐ CỤC TOÀN CẢNH (HOUSE3D & LAYOUT PRESERVATION)

Từ các phát hiện trong `test_challenger_m3_stress_dom_raycaster.py`:
1. **Tuyệt đối không xóa innerHTML của viewport 3D**:
   Mọi hành vi `container.innerHTML = ""` hoặc `container.innerHTML = ''` bị cấm hoàn toàn trong `house3d.js` vì sẽ làm bay màu `#house3dLabels` và `.viewport-note`. Phải luôn giữ cú pháp chèn an toàn:
   ```javascript
   const oldCanvas = container.querySelector('canvas');
   if (oldCanvas) oldCanvas.remove();
   container.insertBefore(renderer.domElement, container.firstChild);
   ```
2. **Không ẩn pin nhãn thiết bị**:
   Không được có rule CSS `.pin-3d .pin-icon { display: none !important; }` trong `style.css`.
3. **Thanh Toolbar 7 góc nhìn Camera**:
   Bắt buộc duy trì 7 nút camera (`overview`, `living`, `bedroom`, `door`, `garden`, `board`, `rotate`) cùng nhãn `#lblCurrentCameraView` để người dùng và bài test tương tác chuyển đổi mượt mà.
4. **Cơ chế Raycaster 3D**:
   Nhấp chuột / chạm tay trực tiếp vào 7 thiết bị 3D trên mô hình (cửa chính, đèn khách, quạt trần, điều hòa, đèn ngủ, còi báo động, máy bơm sân vườn) phải kích hoạt đúng thiết bị qua `SmartHome3D.onDeviceClick`.

---

## 7. ĐẶC TẢ CHI TIẾT CÁC TỆP CẦN TRIỂN KHAI CHO DEVELOPER AGENTS

### 7.1. Tệp Ngoại tuyến & Service Worker
1. **`simulator/static/offline.html`**:
   - Được đóng gói từ `ui_mockups/v2_new_pages/np_01_offline.html`.
   - Chứa CSS nội tuyến hoàn chỉnh để có thể hiển thị đẹp mắt ngay cả khi không tải được `style.css` từ mạng.
   - Script tự động lắng nghe sự kiện `window.addEventListener('online', ...)` và kiểm tra kết nối để tự khôi phục sau 3–5 giây.
   - Nút "Thử kết nối lại" gọi hàm kiểm tra kết nối ngay lập tức.
   - Nút "Chuyển sang Server Dự phòng": mặc định ẩn, chỉ hiện khi trong `localStorage.getItem('backup_server_url')` hoặc biến cấu hình có URL dự phòng.
2. **`simulator/static/sw.js`**:
   - Cung cấp tại route `/sw.js` (hoặc mount với header `Service-Worker-Allowed: /`).
   - `CACHE_NAME = 'smarthome-v1'`.
   - `PRECACHE_URLS = ['/offline.html', '/favicon.ico']`.
   - Chiến lược:
     - Với `request.mode === 'navigate'`: Gọi `fetch(event.request)`. Nếu lỗi mạng (catch error), trả về `caches.match('/offline.html')`.
     - Với các request khác (đặc biệt là `/api/*` hoặc phương thức không phải `GET`): Cho qua mạng bình thường, KHÔNG trả về `offline.html` để tránh làm vỡ JSON parse ở client.
   - Đăng ký trong `simulator/static/index.html` và `mobile_app/index.html`:
     ```javascript
     if ('serviceWorker' in navigator) {
       window.addEventListener('load', () => {
         navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
       });
     }
     ```

### 7.2. Tệp Lỗi HTTP (404, 500, QR Expired, 403)
1. **`simulator/static/404.html`**:
   - Từ `np_02_404.html`.
   - Giữ nguyên cấu trúc thẻ card 560px, icon `file-question`, link tĩnh `<a class="btn primary" href="/">Về Trang chủ</a>` và `<a class="btn secondary" href="/app">Mở Ứng dụng Điện thoại</a>`.
2. **`simulator/static/500.html`**:
   - Từ `np_03_500.html`.
   - Hỗ trợ cả 500 (Lỗi hệ thống) và 503 (Dịch vụ tạm gián đoạn).
   - Nút `onclick="location.reload()"` để tải lại trang.
3. **`simulator/static/qr_expired.html`**:
   - Từ `np_04_qr_expired.html`.
   - Icon `qr-code`. Nút "Quét mã mới" dẫn về `/app` (hoặc mở scanner).
   - Tuyệt đối không hiển thị "Tạo mã mới" cho người dùng quét mã.
4. **`simulator/static/403.html`**:
   - Từ `np_05_403.html`.
   - Icon `shield-off`. Hiển thị role pill "Khách · Cấp 3" nếu có phiên.
   - Nút "Quay về Nhà" (`/app` hoặc `/`) và "Đăng nhập tài khoản khác".

### 7.3. Cập nhật `simulator/server.py`
1. **Xử lý Exception Handler 404 Thông Minh**:
   ```python
   from starlette.exceptions import HTTPException as StarletteHTTPException

   @app.exception_handler(404)
   @app.exception_handler(StarletteHTTPException)
   async def custom_http_exception_handler(request: Request, exc: Exception) -> Response:
       status_code = getattr(exc, "status_code", 404)
       if status_code == 404:
           # Nếu là gọi API hoặc client không yêu cầu HTML: trả JSON chuẩn
           accept = request.headers.get("accept", "")
           if request.url.path.startswith("/api/") or "text/html" not in accept:
               detail = getattr(exc, "detail", "Not Found")
               return JSONResponse({"detail": detail}, status_code=404)
           # Nếu là điều hướng trình duyệt (browser navigation): trả HTML trang 404
           file_404 = STATIC_DIR / "404.html"
           if file_404.exists():
               return FileResponse(file_404, status_code=404)
           return JSONResponse({"detail": "Not Found"}, status_code=404)
       elif status_code in (500, 503):
           accept = request.headers.get("accept", "")
           if not request.url.path.startswith("/api/") and "text/html" in accept:
               file_500 = STATIC_DIR / "500.html"
               if file_500.exists():
                   return FileResponse(file_500, status_code=status_code)
       detail = getattr(exc, "detail", str(exc))
       return JSONResponse({"detail": detail}, status_code=status_code)
   ```
2. **Mount Route `/sw.js` và các trang lỗi tĩnh**:
   ```python
   @app.get("/sw.js")
   async def service_worker_file() -> FileResponse:
       response = FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")
       response.headers["Service-Worker-Allowed"] = "/"
       return response

   @app.get("/offline")
   @app.get("/offline.html")
   async def offline_page() -> FileResponse:
       return FileResponse(STATIC_DIR / "offline.html")

   @app.get("/404")
   @app.get("/404.html")
   async def page_404() -> FileResponse:
       return FileResponse(STATIC_DIR / "404.html", status_code=404)

   @app.get("/500")
   @app.get("/500.html")
   async def page_500() -> FileResponse:
       return FileResponse(STATIC_DIR / "500.html", status_code=500)

   @app.get("/qr-expired")
   @app.get("/qr_expired.html")
   async def page_qr_expired() -> FileResponse:
       return FileResponse(STATIC_DIR / "qr_expired.html")

   @app.get("/403")
   @app.get("/403.html")
   async def page_403() -> FileResponse:
       return FileResponse(STATIC_DIR / "403.html", status_code=403)
   ```

### 7.4. Modals & Banners trên Frontend (`index.html` và `mobile_app/index.html`)
1. **Lockdown Modal (`np_06_lockdown.html`)**:
   - Thêm khối modal `<div id="securityLockdownModal" class="modal hidden" style="z-index:9999;">` với cấu trúc `role="alertdialog" aria-modal="true"`.
   - Tuyệt đối không có nút đóng 'X'.
   - Hỗ trợ chuyển đổi giữa nhập Mật khẩu Chủ nhà (`#lockdownPasswordInput`) và nhận mã OTP qua Gmail (`#lockdownOtpInput`).
   - Khi `voice_auth` kích hoạt `strike_count >= 3`: Tự động hiện modal, đồng thời phát âm thanh cảnh báo hoặc hiển thị trạng thái còi nếu `alarm_siren == 'ON'`.
2. **Mic Permission Modal (`np_07_mic_permission.html`)**:
   - Thêm khối modal `<div id="micPermissionModal" class="modal hidden" style="z-index:9000;">`.
   - Trong `startMic()` (`app.js` và `mobile_app.js`): khi gặp lỗi quyền truy cập hoặc phát hiện HTTP không an toàn, gọi `showMicPermissionModal(reason)`.
   - Cung cấp nút "Thử lại", "Mở bản HTTPS" (nếu có biến cấu hình), và "Đóng".
3. **WebSocket Reconnect Banner (`np_08_ws_banner.html`)**:
   - Thêm `<div id="wsReconnectBanner" class="banner hidden" role="status" aria-live="polite">` ngay đầu thẻ `<main class="layout">` (Web) và `<div id="mobileMainContent">` (Mobile).
   - Trong hàm kết nối WebSocket:
     - Khi `ws.onclose` / reconnect: Hiện banner màu cam với số lần thử `Đang kết nối lại (lần ${retryCount}/5)…`.
     - Khi `retryCount >= 5`: Hiển thị "Chưa khôi phục kết nối. Thử lại để cập nhật trạng thái.", nút "Kết nối ngay" mở lại trạng thái nhấn.
     - Khi `ws.onopen`: Banner đổi sang màu xanh lá "Đã khôi phục kết nối", ẩn sau 2 giây.

---

## 8. KẾT LUẬN & KIẾN NGHỊ BÀN GIAO CHO CÁC SUBAGENTS THỰC THI

1. **Tính khả thi**: 100% các yêu cầu trong `ORIGINAL_REQUEST.md` (R1, R2) đã có tài liệu mockup đầy đủ trong `ui_mockups/v2_new_pages/`, không cần phải tự phát minh hay thiết kế lại bất kỳ chi tiết nào.
2. **Nguy cơ tiềm ẩn & Cách phòng ngừa**:
   - *Nguy cơ*: Sửa `index.html` làm gãy test Three.js / raycaster trong `test_challenger_m3_stress_dom_raycaster.py`.
   - *Biện pháp*: Tuyệt đối không can thiệp vào bên trong `#house3dViewport`, không sửa `house3d.js`, bảo lưu toàn bộ 7 nút camera preset.
   - *Nguy cơ*: Thêm modal / sự kiện JS inline làm gãy `test_challenger_m4_dom.py`.
   - *Biện pháp*: Mọi hàm được gọi trong `onclick` hay sự kiện inline trên HTML mới phải được export rõ ràng lên `window.*` hoặc được gắn qua `addEventListener` có null-safe guard (`const el = document.getElementById(...); if (el) el.addEventListener(...)`).
   - *Nguy cơ*: Lỗi ký tự ngắt dòng CRLF trên Windows làm gãy các test kiểm tra định dạng tệp.
   - *Biện pháp*: Lưu toàn bộ tệp mới và tệp sửa đổi dưới định dạng **UTF-8 (không BOM)** và **POSIX LF (`\n`)**, đảm bảo 0 byte `\r\n`.

Báo cáo này được lập đầy đủ để chuyển giao cho các Subagents thuộc nhóm triển khai Frontend và Backend.
