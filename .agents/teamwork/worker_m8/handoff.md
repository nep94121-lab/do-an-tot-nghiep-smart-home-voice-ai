# BÁO CÁO NGHIỆM THU BÀN GIAO MILESTONE M8 — 5 MÀN HÌNH MOBILE PWA (/APP)

**Agent thực hiện**: `worker_m8` (Role: implementer, qa, specialist)  
**Parent Agent**: `a6dd1e0f-b843-4477-96f4-146d5c9d3c58`  
**Ngày bàn giao**: 2026-11-04  
**Trạng thái**: HARD HANDOFF — 100% HOÀN TẤT & ĐÃ XÁC THỰC THỰC NGHIỆM  

---

## 1. Observation (Quan Sát Trực Tiếp)

1. **Khảo sát mã nguồn hiện hữu**:
   - `mobile_app/index.html`: Chứa 68 DOM IDs và phụ thuộc liên kết tới `/static/css/mobile_app.css` và `/static/js/mobile_app.js`.
   - `simulator/static/js/mobile_app.js`: Chứa 25 `window.*` hooks xuất khẩu toàn cục phục vụ các trình xử lý inline và headless VM.
   - Các mockups thiết kế từ Codex: `ui_mockups/v2_new_pages/np_m1_home_sensors.html` đến `np_m5_qr_scanner.html` và đặc tả Phần 2 tại `ui_mockups/v2_new_pages/DESIGN_NEW_PAGES.md`.
2. **Triển khai 5 màn hình Mobile**:
   - **M1 (Trang Chủ: Nhà & Cảm biến)**:
     - Thẻ "Ngôi nhà" với nhãn "Toàn cảnh", viewport preview tỉ lệ 16:9 (`.preview-16-9`, `#mobileOverviewBox`), không điều hướng về desktop.
     - Thẻ "Cảm biến" 2 ô Grid: Nhiệt độ (`#mobileDisplayTemp`) và Độ ẩm đất (`#mobileDisplaySoil`), đồng bộ giá trị với telemetry `#tempVal` và `#soilVal`. Đúng chuẩn v1: Không hiển thị ô thứ 3 ở màn Home.
     - Thẻ "Trạng thái an toàn": Cửa chính (`#mobileMainDoorStatus`) và Còi báo động (`#mobileAlarmSirenStatus`), đồng bộ dữ liệu thời gian thực từ snapshot thiết bị server.
     - Cặp nút hành động nhanh: Nút primary full-width "Nói lệnh" (`#mobileBtnVoiceSheet`) mở Voice Bottom Sheet; Nút secondary full-width "Xem thiết bị" (`#mobileBtnViewDevices`) chuyển tab Thiết bị.
   - **M2 (Chuyển đổi 4 Tab Độc lập & Màn Tài khoản)**:
     - 4 Tab views độc lập: `#tabViewHome`, `#tabViewDevices`, `#tabViewVoice`, `#tabViewAccount`.
     - Thanh điều hướng đáy `#mobileBottomNav` với 4 tab: `#mobileNavTabHome`, `#mobileNavTabDevices`, `#mobileNavTabVoice`, `#mobileNavTabAccount`.
     - Màn Tài khoản: Hồ sơ phân cấp (`#mobileProfileRole`, `#mobileProfileEmail`, `#mobileProfileDuration`), Menu Quản lý ("Xác thực giọng nói ›", "Lời mời thành viên ›", "Quét mã QR ›", "Cài đặt & Đổi mật khẩu ›"), và nút Đăng xuất secondary full-width (`#mobileBtnLogout`).
     - Hàm `window.scrollToSection(sectionId)` được giữ nguyên và ánh xạ hoàn hảo sang `switchMobileTab(tabKey)` (`secHome` -> `home`, `secDevices` -> `devices`, `secVoice` -> `voice`, `secAuth` -> `account`).
   - **M3 (Quên mật khẩu & Gmail OTP 3 bước)**:
     - Thêm nút "Quên mật khẩu?" (`#btnMobileForgotPassword`) trên `#mobileLoginForm`.
     - Bảng điều khiển Quên mật khẩu `#mobileForgotPasswordPanel` với 3 bước độc lập:
       - Bước 1: Email (`#mobileForgotEmail`), nút gửi mã (`#mobileBtnForgotSendOtp`), tích hợp gọi `POST /api/auth3/forgot_password_send_otp`.
       - Bước 2: Nhập OTP 6 số (`#mobileForgotOtp`) có `inputmode="numeric"`, `autocomplete="one-time-code"`, `maxlength="6"`, `pattern="[0-9]{6}"`, đếm ngược gửi lại 60s (`#mobileBtnForgotResendOtp`), nút xác nhận (`#mobileBtnForgotVerifyOtp`).
       - Bước 3: Đặt lại mật khẩu mới (`#mobileForgotNewPassword`, `#mobileForgotConfirmPassword`) với 2 nút toggle 👁️, nút xác nhận (`#mobileBtnForgotSubmitReset`), tích hợp gọi `POST /api/auth3/forgot_password_reset`.
   - **M4 (Bottom Sheet Giọng nói)**:
     - Lớp phủ scrim `#mobileVoiceSheetScrim` làm mờ nhẹ nền phía sau.
     - Bottom sheet `#mobileVoiceBottomSheet` bo góc trên 20px, có thanh kéo `.handle`, nút đóng SVG `x` (`#mobileBtnCloseVoiceSheet`, `aria-label="Đóng"`).
     - Vòng tròn sóng trung tâm `.wavecircle`.
     - Dải sóng âm `#mobileVoiceVolumeBars` gồm đúng 12 thanh `<i>` với hiệu ứng animation mức âm lượng thời gian thực.
     - Bộ đếm thời gian `#mobileVoiceTimer` hiển thị `00:03 / 00:05` (`#mobileVoiceTimerCur`, `#mobileVoiceTimerTotal`).
     - Khung câu đọc mẫu `#mobileVoicePhrase` ("Mở cửa chính cho tôi.").
     - Các nút điều khiển tương ứng trạng thái: Đang thu ("Dừng thu" `#mobileBtnVoiceSheetStop`, "Hủy" `#mobileBtnVoiceSheetCancel`); Đạt ("Tiếp tục" `#mobileBtnVoiceSheetContinue`); Chưa đạt ("Thu lại" `#mobileBtnVoiceSheetRetry`, "Đóng" `#mobileBtnVoiceSheetClose`).
     - Dòng hiển thị kết quả `#mobileVoiceSheetResult` theo tiêu chuẩn Codex (không để lộ điểm số hay confidence).
   - **M5 (Camera Quét QR & Handshake)**:
     - Modal quét mã `#mobileQrScannerModal` với nút đóng SVG `x` (`#mobileBtnCloseScanner`).
     - Khung ngắm Camera `#mobileScannerCameraView` với video live `#mobileQrVideo` (`playsinline`).
     - Khung ngắm kẻ viền 4 góc `#mobileScanFrame` gồm 4 góc `.tl`, `.tr`, `.bl`, `.br`.
     - Nút "Bật camera" (`#mobileBtnStartCamera`) kích hoạt camera sau (`facingMode: "environment"`) và nút "Nhập mã" (`#mobileBtnManualCodeInput`).
     - Tích hợp bắt tay gọi API backend `POST /api/auth3/guest_handshake` (kèm alias trong `simulator/api/routes_qr.py`).
     - Cơ chế dọn dẹp sạch sẽ: Tự động gọi `track.stop()` giải phóng camera stream khi đóng modal hoặc rời màn hình.
3. **Android Scope (Requirement R3)**:
   - File `android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/MainScreen.kt` được giữ nguyên trạng thái đóng băng (frozen), không can thiệp, tập trung 100% trên Mobile Web PWA `/app`.
4. **Kết quả Kiểm thử Thực nghiệm**:
   - `python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_challenger_m2_gate_ux_empirical.py tests/test_phase1_bugfixes_20261104.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp -v`:
     - `test_challenger_m4_dom.py`: **36/36 PASSED**
     - `test_challenger_m2_gate_ux_empirical.py`: **33/33 PASSED**
     - `test_phase1_bugfixes_20261104.py`: **6/6 PASSED**
     - `tests/test_m8_mobile_screens.py`: **22/22 PASSED**
     - **TỔNG CỘNG: 97/97 PASSED (100% PASS, 0 FAIL)** trong 20.79s.

---

## 2. Logic Chain (Chuỗi Lập Luận Suy Biến)

1. **Từ Quan sát 1 & 2 $\rightarrow$ Thiết kế Cấu trúc Tab Độc lập Không Phá Vỡ Test**:
   - Để chuyển từ chế độ cuộn đơn (single-scroll) sang 4 màn hình tab độc lập theo đặc tả M2 mà không làm gãy các test challenger cũ, 4 tab view (`#tabViewHome`, `#tabViewDevices`, `#tabViewVoice`, `#tabViewAccount`) được quản lý bằng thuộc tính `hidden`.
   - Hàm `scrollToSection(id)` được định tuyến để kích hoạt `switchMobileTab(tabKey)` tương ứng. Do đó, bất kỳ mã kiểm thử nào gọi `scrollToSection('secDevices')` hay click vào thanh điều hướng đều kích hoạt hiển thị đúng màn hình mong muốn mà không gây ngoại lệ DOM.
2. **Từ Quan sát 2 (M1) $\rightarrow$ Khớp Thiết kế Codex**:
   - Thẻ Ngôi nhà sử dụng `.preview-16-9` với tỷ lệ khung hình CSS `aspect-ratio: 16 / 9`, thay thế thẻ điều hướng cũ tránh redirect người dùng về desktop.
   - Thẻ cảm biến giữ đúng 2 ô grid Nhiệt độ & Độ ẩm đất. Dữ liệu `#mobileDisplayTemp` và `#mobileDisplaySoil` được cập nhật đồng thời với `#tempVal` và `#soilVal` khi có telemetry, bảo đảm tính nhất quán dữ liệu.
3. **Từ Quan sát 2 (M3, M4, M5) $\rightarrow$ Tích hợp API Thực Chất & Bảo Toàn An Toàn**:
   - M3 tích hợp trực tiếp với 2 endpoints `/api/auth3/forgot_password_send_otp` và `/api/auth3/forgot_password_reset`. Các trường mật khẩu tuân thủ yêu cầu bắt buộc 2 ô xác nhận và có nút 👁️ toggle.
   - M4 thiết lập đúng 12 vạch sóng âm `<i>`, thanh kéo `.handle`, bộ đếm 5s và phân loại kết quả chuẩn theo vai trò (Chủ nhà, Gia đình, Khách) mà không hiển thị thông số nội bộ.
   - M5 tích hợp `/api/auth3/guest_handshake`, tự động stop camera tracks khi đóng modal để ngăn rò rỉ tài nguyên phần cứng.
4. **Từ Quan sát 4 $\rightarrow$ Kết Luận Đạt Chuẩn Nghiệm Thu**:
   - Cả 97 bài kiểm thử đối kháng và kiểm thử tính năng M8 đều chạy thành công 100% trên Python 3.14 / Node.js VM headless runner, chứng minh tính toàn vẹn và không có hồi quy (zero regression).

---

## 3. Caveats (Điểm Giới Hạn & Giả Định)

- **Trình duyệt không hỗ trợ MediaDevices trong môi trường kiểm thử không đầu (Headless CI)**: Mã nguồn đã được trang bị cơ chế kiểm tra `typeof navigator !== 'undefined' && navigator.mediaDevices` để tránh ném ngoại lệ khi chạy trong môi trường Node.js DOM mock hoặc CI headless không có webcam/mic vật lý.
- **Android Gradle Build trên Windows**: Tiếp tục tuân thủ nghiêm ngặt chỉ thị Requirement R3: không chỉnh sửa mã nguồn Compose trong thư mục `android_app/` nhằm bảo vệ trạng thái ổn định cho toàn bộ dự án.

---

## 4. Conclusion (Kết Luận)

Milestone M8 đã hoàn thành xuất sắc 100% các yêu cầu:
- 5 màn hình mobile PWA (`/app`) theo đúng Phần 2 của `DESIGN_NEW_PAGES.md` và các mockups `np_m1` – `np_m5`.
- Bảo toàn 100% 68 DOM IDs và 25 `window.*` hooks hiện hữu.
- Toàn bộ 97 bài kiểm thử liên quan (`test_challenger_m4_dom.py`, `test_challenger_m2_gate_ux_empirical.py`, `test_phase1_bugfixes_20261104.py`, `test_m8_mobile_screens.py`) đạt **100% PASS**.

---

## 5. Verification Method (Phương Pháp Xác Minh Độc Lập)

Người thẩm định (Auditor) hoặc Parent Agent có thể chạy các lệnh sau từ thư mục gốc dự án:

1. **Chạy kiểm thử chuyên biệt 5 màn hình Mobile M8**:
   ```powershell
   python -X utf8 -m pytest tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp -v
   ```
   *Kỳ vọng*: 22 passed trong ~6s.

2. **Chạy toàn bộ bộ kiểm thử tích hợp Milestone M8 (97 tests)**:
   ```powershell
   python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_challenger_m2_gate_ux_empirical.py tests/test_phase1_bugfixes_20261104.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp -v
   ```
   *Kỳ vọng*: 97 passed trong ~20s.

3. **Kiểm tra trực tiếp các file thay đổi**:
   - `mobile_app/index.html`
   - `simulator/static/css/mobile_app.css`
   - `simulator/static/js/mobile_app.js`
   - `simulator/api/routes_qr.py`
   - `tests/test_m8_mobile_screens.py`
