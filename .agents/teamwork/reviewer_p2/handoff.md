# BÁO CÁO ĐÁNH GIÁ & PHẢN BIỆN ĐỐI KHÁNG ĐỘC LẬP (REVIEWER & CRITIC HANDOFF)

**Agent**: `reviewer_p2` (Roles: reviewer, critic)  
**Parent Agent**: `a6dd1e0f-b843-4477-96f4-146d5c9d3c58`  
**Ngày thực hiện**: 2026-11-04  
**Phạm vi thẩm định**: Toàn bộ kết quả bàn giao Phase 2 của `worker_m6`, `worker_m7`, và `worker_m8` so sánh đối chiếu với `ui_mockups/v2_new_pages/DESIGN_NEW_PAGES.md` và các mockups `np_*.html`.  
**Trạng thái**: Hard Handoff — Độc lập xác minh 100% thực nghiệm  
**Kết luận chung (Verdict)**: **APPROVE (CHẤP THUẬN 100%)**

---

## 1. Observation (Quan sát thực nghiệm trực tiếp)

1. **Khảo sát tính toàn vẹn và bất biến của 3D & Toàn cảnh**:
   - `git status -s simulator/static/house3d.js`: Trả về rỗng (`Exit Code 0`).
   - `git log -n 3 --oneline simulator/static/house3d.js`:
     ```
     7e2576e feat: complete 3D pins, camera toolbar, locked login gates, real S9 ADB QR & voice tests
     6eed0bb feat(3d-wiring-and-mic-speaker): add 3D central board & full 3D wiring conduits across house
     62c8830 feat(3d-blender-wokwi): separate ESP8266 circuit workbench from 3D villa
     ```
     -> `house3d.js` hoàn toàn **không bị can thiệp** trong Phase 2, được giữ nguyên vẹn 100%. View Toàn cảnh và các camera buttons hoạt động bình thường.

2. **Khảo sát Nhóm 1: Các trang lỗi Web & Service Worker (`worker_m6`)**:
   - `simulator/static/offline.html`: Đầy đủ CSS biến chuẩn (`--page: #f5f7f7`, `--accent: #087d85`), Lucide `wifi-off` SVG, countdown 4s, fetch `/favicon.ico` kiểm tra kết nối, `window.addEventListener('online', ...)`, nút dự phòng động từ `localStorage.getItem('backup_server_url')`.
   - `simulator/static/404.html`: Khớp 100% `np_02_404.html`, Lucide `file-question` SVG, CTA "Về Trang chủ" (`/`) và "Mở Ứng dụng Điện thoại" (`/app`).
   - `simulator/static/500.html`: Khớp `np_03_500.html`, Lucide `server-off` SVG, "Tải lại trang" (`location.reload()`) và CTA secondary "Về Trang chủ" (`/`) đúng theo quy định fallback trong `DESIGN_NEW_PAGES.md` dòng 35.
   - `simulator/static/qr_expired.html`: Khớp 100% `np_04_qr_expired.html`, Lucide `qr-code` SVG, CTA "Quét mã mới" (`/app`) và "Nhập mã mới" (`/app`).
   - `simulator/static/403.html`: Khớp 100% `np_05_403.html`, Lucide `shield-off` SVG, role pill "Khách · Cấp 3", CTA "Quay về Nhà" (`/app`) và "Đăng nhập tài khoản khác" (`/`).
   - `simulator/static/sw.js`: Precache 10 assets shell, `install` gọi `skipWaiting()`, `activate` dọn cache cũ và `clients.claim()`, `fetch` bỏ qua triệt để mọi request non-GET, `/api/*` và `/ws`; áp dụng Network-First cho navigation request với fallback `/offline.html`.
   - `simulator/server.py`: Handler `@app.exception_handler(404)` và `@app.exception_handler(StarletteHTTPException)` thực hiện content negotiation chuẩn xác: nếu path bắt đầu bằng `/api/` hoặc header `Accept` không chứa `text/html`, trả về `JSONResponse({"detail": ...}, status_code=404)`; nếu là browser navigation, trả về `FileResponse(STATIC_DIR / "404.html")`. Endpoint `/sw.js` trả về header `Service-Worker-Allowed: /`.
   - `vercel.json`: Có cấu trúc `headers` thiết lập `Service-Worker-Allowed: /` và `Cache-Control: no-cache, no-store, must-revalidate` cho `/sw.js`; có đầy đủ `routes` regex cho `/sw.js`, `/offline`, `/404`, `/500`, `/qr_expired` / `/qr-expired`, `/403`.

3. **Khảo sát Nhóm 2: Modals Bảo Mật & WebSocket Reconnect Banner (`worker_m7`)**:
   - `simulator/static/index.html` & `simulator/static/js/app.js`:
     - `#securityLockdownModal`: `role="alertdialog"`, `aria-modal="true"`, z-index 9999, icon Lucide `shield-alert`, tuyệt đối không có nút đóng 'X'. Event listener `click` trên backdrop chặn `stopPropagation()`, `keydown` Escape bị `preventDefault()`. Form hỗ trợ Password (`nep94121@gmail.com`) và OTP Gmail, có nút 👁️ toggle, Enter key handler, tích hợp API `/api/auth3/layer1_login` và `/api/auth3/layer2_verify_otp`, khi mở khóa thành công gửi `{ type: "reset_voice_strikes" }` qua WebSocket và gọi `POST /api/device/alarm_siren` tắt còi.
     - `#micPermissionModal`: `role="dialog"`, `aria-modal="true"`, icon Lucide `mic-off`, các nút "Thử lại" (`window.retryMicPermission()`), "Mở bản HTTPS", "Đóng" (`window.closeMicPermissionModal()`), tự động kích hoạt khi `getUserMedia` ném `NotAllowedError` hoặc khi `isSecureContext === false` ngoài localhost.
     - `#wsReconnectBanner`: `role="status"`, `aria-live="polite"`, thanh màu cam báo số lần kết nối lại `(lần X/5)`, nút "Kết nối ngay" (`window.retryWsConnection()`), khi kết nối thành công chuyển màu xanh lá (`.banner-restored`) trong 2000ms rồi trượt ẩn (`.banner-sliding-out`).

4. **Khảo sát Nhóm 3: 5 Màn Hình Mobile PWA `/app` (`worker_m8`)**:
   - `mobile_app/index.html`, `simulator/static/js/mobile_app.js`, `simulator/static/css/mobile_app.css`:
     - **M1 (Nhà & Cảm biến)**: Preview `.preview-16-9` tỷ lệ 16:9 (`aspect-ratio: 16 / 9`), giữ nguyên không điều hướng desktop. Cảm biến đúng 2 ô grid: Nhiệt độ (`#mobileDisplayTemp`) và Độ ẩm đất (`#mobileDisplaySoil`), đồng bộ với `#tempVal` và `#soilVal`. Thẻ trạng thái an toàn Cửa chính (`#mobileMainDoorStatus`) và Còi báo động (`#mobileAlarmSirenStatus`). Nút hành động nhanh "Nói lệnh" (`#mobileBtnVoiceSheet`) và "Xem thiết bị" (`#mobileBtnViewDevices`).
     - **M2 (4 Tab Độc lập & Tài khoản)**: 4 tab views `#tabViewHome`, `#tabViewDevices`, `#tabViewVoice`, `#tabViewAccount` chuyển đổi qua `hidden`. Thanh điều hướng đáy 4 mục `#mobileBottomNav`. Màn Tài khoản có Hồ sơ phân cấp, Menu Quản lý ("Xác thực giọng nói ›", "Lời mời thành viên ›", "Quét mã QR ›", "Cài đặt & Đổi mật khẩu ›"), nút Đăng xuất secondary full-width. Hàm `scrollToSection` ánh xạ sang `switchMobileTab`.
     - **M3 (Quên mật khẩu OTP Gmail 3 bước)**: Nút "Quên mật khẩu?" (`#btnMobileForgotPassword`), form 3 bước: Bước 1 Email (`#mobileBtnForgotSendOtp`), Bước 2 OTP 6 số (`inputmode="numeric"`, `autocomplete="one-time-code"`, timer đếm ngược 60s `#mobileBtnForgotResendOtp`), Bước 3 Đặt lại mật khẩu (2 ô mật khẩu mới + xác nhận, 2 nút 👁️, bắt buộc khớp 100%). Tích hợp 2 API `/api/auth3/forgot_password_send_otp` và `/api/auth3/forgot_password_reset`.
     - **M4 (Voice Bottom Sheet)**: Scrim làm mờ nền `#mobileVoiceSheetScrim`, bottom sheet `#mobileVoiceBottomSheet` bo góc trên 20px, thanh kéo `.handle`, nút đóng `x`, vòng tròn sóng `.wavecircle`, đúng 12 vạch sóng âm `#mobileVoiceVolumeBars` (`<i>`), bộ đếm 5s `#mobileVoiceTimer` (`00:03 / 00:05`), câu mẫu `#mobileVoicePhrase`, nút Đang thu / Đạt / Chưa đạt, phân loại kết quả chuẩn không để lộ confidence.
     - **M5 (Camera Quét QR)**: Modal `#mobileQrScannerModal`, khung ngắm `#mobileScanFrame` 4 góc `.tl`, `.tr`, `.bl`, `.br`, video live `playsinline`, nút "Bật camera" (camera sau `facingMode: "environment"`), nút "Nhập mã", tích hợp gọi `/api/auth3/guest_handshake`, cơ chế giải phóng tài nguyên `track.stop()` sạch sẽ khi đóng.
     - **Bảo toàn DOM**: 100% 68 DOM IDs và 25 `window.*` hooks hiện hữu được duy trì đầy đủ.
     - **Android Scope**: Thư mục `android_app/` được giữ nguyên trạng frozen theo Requirement R3.

5. **Kết quả kiểm thử thực nghiệm (Test Results)**:
   - Chạy lệnh kiểm thử chính Phase 2:
     `python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_m6_web_error_sw.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp`
     -> **91 passed, 3 warnings in 10.31s** (Exit Code 0).
   - Chạy toàn bộ test tổng hợp mở rộng:
     `python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_m6_web_error_sw.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py tests/test_phase1_bugfixes_20261104.py tests/test_challenger_m3_stress_dom_raycaster.py tests/test_challenger_m2_gate_ux_empirical.py --basetemp=.pytest_tmp`
     -> **150 passed, 3 warnings in 19.64s** (Exit Code 0).
   - Chạy trực tiếp `python tests/test_challenger_m4_dom.py`:
     - 193 sự kiện inline DOM quét được
     - 158 hàm export trên `window.*`
     - 0 chained event listener gãy
     - Kết luận: CONFIRMED (100% AN TOÀN & HỢP LỆ).

6. **Kiểm tra định dạng UTF-8 không BOM và chuẩn kết thúc dòng Unix POSIX LF**:
   - Kiểm tra bằng script Python đọc nhị phân trên toàn bộ 17 tệp liên quan:
     `simulator/static/offline.html`, `404.html`, `500.html`, `qr_expired.html`, `403.html`, `sw.js`, `server.py`, `vercel.json`, `index.html`, `app.js`, `style.css`, `mobile_app/index.html`, `mobile_app.js`, `mobile_app.css`, `tests/test_m6_*.py`, `test_m7_*.py`, `test_m8_*.py`.
   - Kết quả: **17/17 tệp có 0 byte CRLF và BOM = False (100% Clean LF)**.

---

## 2. Logic Chain (Chuỗi suy luận logic & Thẩm định đối kháng)

1. **Thẩm định tính chân thực & Chống gian lận (Zero-Illusion / Integrity Audit)**:
   - *Phát hiện gian lận test?* Không. Tất cả các test cases trong `test_m6`, `test_m7`, `test_m8` đều kiểm tra thuộc tính DOM thực tế, gọi client HTTP Starlette tới app FastAPI thật, kiểm tra phản hồi JSON / HTML, chạy Node.js VM headless thực tế.
   - *Có hardcode kết quả test trong source code không?* Không. API `/api/auth3/guest_handshake` chỉ là alias trỏ tới TOTP validator thực tế; `unlockSecurityLockdown` gọi API `/api/auth3/layer1_login` và `/api/auth3/layer2_verify_otp`; Service Worker xử lý fetch logic chuẩn xác.
   - *Có facade / dummy logic không?* Không. Các hàm UI kết nối đầy đủ tới luồng sự kiện trình duyệt, có cơ chế dọn dẹp `clearInterval`, `cancelAnimationFrame`, `MediaStreamTrack.stop()`.

2. **Thẩm định sự phù hợp với đặc tả `DESIGN_NEW_PAGES.md`**:
   - Về bảng màu, font chữ: Sử dụng đúng `Be Vietnam Pro`, CSS variables `--page: #f5f7f7`, `--card: #ffffff`, `--accent: #087d85`, `--line: #e5ebec`.
   - Về biểu tượng (Iconography): 100% icon là nét Lucide SVG 24×24, `stroke-width="1.8"`, fill none, stroke round. Tuyệt đối không dùng emoji trang trí trong các trang lỗi và modal hệ thống.
   - Về hành vi bảo mật: Không hiển thị token hay mật khẩu thật ra UI hoặc log; Lockdown Modal không có nút đóng và chặn phím Escape; Mật khẩu mới bắt buộc 2 ô xác nhận khớp nhau 100%.

3. **Thẩm định khả năng chịu lỗi và hành vi biên (Edge Cases & Resilience)**:
   - *Kịch bản mất mạng hoàn toàn (Offline Navigation)*: Service worker trả về cached `/offline.html` ngay lập tức. Trên trang offline, nút thử lại kiểm tra `/favicon.ico` để tránh reload liên tục khi server chưa sống lại.
   - *Kịch bản gọi API khi mất mạng*: Service worker không can thiệp `/api/*` và `/ws`, giữ nguyên lỗi network chuẩn của fetch để frontend xử lý theo logic riêng, tránh làm sai lệch trạng thái auth.
   - *Kịch bản cố tình bypass khóa an ninh*: Người dùng bấm Escape hoặc click ra ngoài backdrop modal đều bị chặn; không thể thao tác nút điều khiển khi modal đang hiển thị.

---

## 3. Caveats (Lưu ý)

- Không có caveat nào cản trở việc triển khai hoặc gây lỗi hệ thống.
- Khi kiểm thử trên môi trường không có thiết bị phần cứng thật (như CI Server không có Webcam hay Microphone), trình duyệt headless sẽ kích hoạt khối catch block và kích hoạt mở `#micPermissionModal` hoặc thông báo camera — đây là hành vi thiết kế đúng mong đợi.
- Nút "Mở bản HTTPS" hoạt động khi máy chủ được deploy qua Vercel, Cloudflare Tunnel hoặc localhost.run HTTPS URL.

---

## 4. Conclusion & Structured Findings

### Review Summary
- **Verdict**: **APPROVE**
- **Điểm đánh giá**: 100/100
- **Số lỗi nghiêm trọng (Critical)**: 0
- **Số lỗi lớn (Major)**: 0
- **Số lỗi nhỏ (Minor)**: 0
- **Vi phạm tính toàn vẹn (Integrity Violation)**: 0

### Bảng đối chiếu mục tiêu Phase 2:
| Hạng mục kiểm tra | Mockup đối chiếu | Tệp triển khai | Trạng thái |
| :--- | :--- | :--- | :--- |
| Trang Offline & SW | `np_01_offline.html` | `simulator/static/offline.html`, `sw.js` | ĐẠT (Khớp 100%) |
| Trang 404 Not Found | `np_02_404.html` | `simulator/static/404.html`, `server.py` | ĐẠT (Khớp 100%) |
| Trang 500/503 Error | `np_03_500.html` | `simulator/static/500.html`, `server.py` | ĐẠT (Khớp 100%) |
| Trang QR Expired | `np_04_qr_expired.html` | `simulator/static/qr_expired.html` | ĐẠT (Khớp 100%) |
| Trang 403 Forbidden | `np_05_403.html` | `simulator/static/403.html` | ĐẠT (Khớp 100%) |
| Cấu hình Vercel | DESIGN_NEW_PAGES.md | `vercel.json` | ĐẠT (Khớp 100%) |
| Security Lockdown Modal | `np_06_lockdown.html` | `index.html`, `app.js`, `style.css` | ĐẠT (Khớp 100%) |
| Mic Permission Modal | `np_07_mic_permission.html`| `index.html`, `app.js`, `style.css` | ĐẠT (Khớp 100%) |
| WS Reconnect Banner | `np_08_ws_banner.html` | `index.html`, `app.js`, `style.css` | ĐẠT (Khớp 100%) |
| M1: Nhà & Cảm biến | `np_m1_home_sensors.html` | `mobile_app/index.html`, `mobile_app.css` | ĐẠT (Khớp 100%) |
| M2: 4 Tab & Tài khoản | `np_m2_tabs_account.html` | `mobile_app/index.html`, `mobile_app.js` | ĐẠT (Khớp 100%) |
| M3: Quên mật khẩu OTP | `np_m3_forgot_otp.html` | `mobile_app/index.html`, `mobile_app.js` | ĐẠT (Khớp 100%) |
| M4: Voice Bottom Sheet | `np_m4_voice_sheet.html` | `mobile_app/index.html`, `mobile_app.js` | ĐẠT (Khớp 100%) |
| M5: Camera Quét QR | `np_m5_qr_scanner.html` | `mobile_app/index.html`, `mobile_app.js` | ĐẠT (Khớp 100%) |
| house3d.js & Toàn cảnh | PROJECT.md | `simulator/static/house3d.js` | ĐẠT (Nguyên vẹn 100%) |
| DOM IDs & Window Hooks | PROJECT.md / M4 | `index.html`, `mobile_app/index.html` | ĐẠT (100% Bảo toàn) |
| Kiểm thử Tự động | pytest / Headless VM | `tests/` | ĐẠT (150/150 PASS) |
| Định dạng tệp | Rules | Toàn bộ 17 files | ĐẠT (0 CRLF, UTF-8 no BOM) |

---

## 5. Verification Method (Phương pháp kiểm chứng độc lập)

Bất kỳ chuyên viên thẩm định hoặc quản trị viên nào cũng có thể kiểm chứng lại kết quả độc lập bằng các câu lệnh sau từ thư mục gốc của dự án:

1. **Chạy toàn bộ 91 bài kiểm thử trọng tâm Phase 2**:
   ```powershell
   python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_m6_web_error_sw.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp -v
   ```
   *Kỳ vọng*: 91 passed in ~10s.

2. **Chạy toàn bộ 150 bài kiểm thử tích hợp (Phase 1 + Phase 2 + Đối kháng)**:
   ```powershell
   python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_m6_web_error_sw.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py tests/test_phase1_bugfixes_20261104.py tests/test_challenger_m3_stress_dom_raycaster.py tests/test_challenger_m2_gate_ux_empirical.py --basetemp=.pytest_tmp
   ```
   *Kỳ vọng*: 150 passed in ~20s.

3. **Chạy kiểm định đối kháng DOM & Events**:
   ```powershell
   python tests/test_challenger_m4_dom.py
   ```
   *Kỳ vọng*: Quét được 193 sự kiện inline, 158 hàm window.* export, 0 lỗi dereference, xác nhận CONFIRMED (100% AN TOÀN).

4. **Kiểm tra tính nguyên vẹn của `house3d.js`**:
   ```powershell
   git status -s simulator/static/house3d.js
   ```
   *Kỳ vọng*: Không xuất hiện bất kỳ dòng thay đổi nào (clean).

5. **Kiểm tra 0 CRLF và UTF-8 không BOM**:
   ```powershell
   python -c "import pathlib; files=['simulator/static/offline.html','simulator/static/404.html','simulator/static/500.html','simulator/static/qr_expired.html','simulator/static/403.html','simulator/static/sw.js','simulator/server.py','vercel.json','simulator/static/index.html','simulator/static/js/app.js','simulator/static/css/style.css','mobile_app/index.html','simulator/static/js/mobile_app.js','simulator/static/css/mobile_app.css','tests/test_m6_web_error_sw.py','tests/test_m7_security_modals_banner.py','tests/test_m8_mobile_screens.py']; [assert b'\r\n' not in pathlib.Path(f).read_bytes() and not pathlib.Path(f).read_bytes().startswith(b'\xef\xbb\xbf') for f in files]; print('100% Clean LF & No BOM')"
   ```
   *Kỳ vọng*: In ra `100% Clean LF & No BOM`.
