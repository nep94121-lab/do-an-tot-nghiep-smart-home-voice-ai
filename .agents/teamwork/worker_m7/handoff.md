# BÁO CÁO BÀN GIAO TIỂU DỰ ÁN M7 (HANDOFF REPORT)

**Người thực hiện**: `worker_m7` (Implementer / QA Agent)  
**Mục tiêu**: Hiện thực hóa Security Lockdown Modal, Microphone Permission Modal, WebSocket Reconnect Banner trong `simulator/static/index.html`, `simulator/static/js/app.js`, và `simulator/static/css/style.css` theo đúng đặc tả `ui_mockups/v2_new_pages/np_06_lockdown.html`, `np_07_mic_permission.html`, `np_08_ws_banner.html`, và `DESIGN_NEW_PAGES.md` (06, 07, 08).  
**Ngày thực hiện**: 2026-11-04  
**Trạng thái**: Hard Handoff (Hoàn tất 100%, 72/72 tests pass, 0 CRLF, 0 Regression)

---

## 1. Observation (Quan sát thực nghiệm)

1. **Khảo sát mã nguồn và mockup ban đầu**:
   - Tệp mockup `ui_mockups/v2_new_pages/np_06_lockdown.html`: Chứa cấu trúc `role="alertdialog"`, `aria-modal="true"`, icon Lucide `shield-alert` (`M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z M12 7v6 M12 17h.01`), tiêu đề `#locktitle` "Cảnh báo an ninh", thông báo 3 lần thất bại, ô nhập mật khẩu với eye toggle, nút "Xác minh và mở khóa", nút "Dùng mã OTP Gmail", tuyệt đối không có nút đóng 'X'.
   - Tệp mockup `ui_mockups/v2_new_pages/np_07_mic_permission.html`: Chứa cấu trúc `role="dialog"`, `aria-modal="true"`, icon Lucide `mic-off` (`M9 5a3 3 0 0 1 6 0v6 M5 10a7 7 0 0 0 9 6 M12 17v5 M8 22h8 M3 3l18 18`), tiêu đề `#mictitle` "Chưa thể dùng micro", nút "Thử lại", "Mở bản HTTPS", "Đóng".
   - Tệp mockup `ui_mockups/v2_new_pages/np_08_ws_banner.html`: Chứa cấu trúc `role="status"`, `aria-live="polite"`, icon `wifi-off`, nhãn "Mất kết nối thời gian thực tới ngôi nhà. Đang kết nối lại (lần 1/5)…", nút "Kết nối ngay", trạng thái phục hồi chuyển màu xanh trong 2 giây rồi trượt ẩn.
   - Tệp hiện hữu `simulator/static/index.html`: Chứa 105 phần tử DOM quan trọng (sidebar, house3d, voice actions, login gate, v.v.).
   - Tệp hiện hữu `simulator/static/house3d.js`: Chứa Three.js viewport, không được phép chỉnh sửa.
   - Tệp hiện hữu `simulator/static/js/app.js`: Quản lý WebSocket tại dòng 512 (`function connectWebSocket()`), xử lý mic tại dòng 738 (`startMic()`), voice lockout notice tại dòng 604.

2. **Các lệnh kiểm thử và kết quả quan sát**:
   - `python -X utf8 -m pytest tests/test_challenger_m4_dom.py --basetemp=.pytest_tmp`
     ```
     ============================= 36 passed in 2.16s ==============================
     ```
   - `python -X utf8 -m pytest tests/test_challenger_m3_stress_dom_raycaster.py --basetemp=.pytest_tmp`
     ```
     ============================= 20 passed in 0.66s ==============================
     ```
   - `python -X utf8 -m pytest tests/test_m7_security_modals_banner.py --basetemp=.pytest_tmp`
     ```
     ============================= 16 passed in 0.42s ==============================
     ```
   - `python tests/test_challenger_m4_dom.py` (Script trực tiếp):
     ```
     =================================================================
     TỔNG CỘNG SỰ KIỆN INLINE QUÉT ĐƯỢC: 193
     TỔNG SỐ HÀM EXPORT TRÊN WINDOW.*: 158
     TỔNG SỐ CHAINED EVENT LISTENERS: 0
     KẾT LUẬN TOÀN DIỆN: CONFIRMED (100% AN TOÀN & HỢP LỆ)
     =================================================================
     ```
   - Kiểm tra định dạng ký tự kết thúc dòng (Line Endings) và mã hóa:
     ```
     simulator/static/index.html: bytes=30200, CRLF=0, lone_CR=0, has_BOM=False
     simulator/static/js/app.js: bytes=72880, CRLF=0, lone_CR=0, has_BOM=False
     simulator/static/css/style.css: bytes=19118, CRLF=0, lone_CR=0, has_BOM=False
     tests/test_m7_security_modals_banner.py: bytes=15275, CRLF=0, lone_CR=0, has_BOM=False
     ```

---

## 2. Logic Chain (Chuỗi suy luận logic)

1. **Từ yêu cầu M7 & Mockup np_06 đến `#securityLockdownModal`**:
   - Yêu cầu đặt ra: Modal khóa an ninh khi số lần nhận diện giọng nói sai đạt 3 lần (`unauthorized_strikes >= 3`).
   - Khóa an ninh là tình huống nghiêm trọng, nên mockup quy định thẻ `<section role="alertdialog" aria-modal="true">` với nền che mờ `rgba(15,34,38,0.85)` và z-index 9999.
   - Để ngăn người lạ bỏ qua cảnh báo, modal KHÔNG có nút close 'X', sự kiện click ra backdrop (`securityLockdownEl.addEventListener("click", ...)`) bị chặn `stopPropagation()`, và sự kiện phím Escape bị `preventDefault()`.
   - Về cơ chế mở khóa: Hỗ trợ 2 phương thức (Mật khẩu Chủ nhà hoặc OTP Gmail nep94121@gmail.com). Khi bấm nút toggle, form chuyển đổi linh hoạt. Khi người dùng nhập và bấm Enter hoặc click "Xác minh và mở khóa", hàm `unlockSecurityLockdown()` gọi API backend thực tế (`/api/auth3/layer1_login` hoặc `/api/auth3/layer2_verify_otp`). Khi xác thực thành công (200 OK), client gửi `{ type: "reset_voice_strikes" }` qua WebSocket để server bridge reset strikes, gọi `POST /api/device/alarm_siren` tắt còi báo động, ẩn modal và xóa nhãn khóa.

2. **Từ yêu cầu M7 & Mockup np_07 đến `#micPermissionModal`**:
   - Yêu cầu đặt ra: Khi người dùng bấm mic nhưng bị trình duyệt chặn (`getUserMedia` ném lỗi `NotAllowedError`) hoặc truy cập qua ngữ cảnh không an toàn HTTP từ xa (`!window.isSecureContext`), hiển thị modal giải thích và hướng dẫn.
   - Thẻ `<div id="micPermissionModal" class="modal hidden" role="dialog" aria-modal="true" aria-labelledby="mictitle">` chứa icon Lucide `mic-off`.
   - Cung cấp nút "Thử lại" gọi `retryMicPermission()` (đóng modal và gọi lại `startMic()`), liên kết "Mở bản HTTPS" tự động điều hướng sang URL HTTPS tương ứng nếu đang ở HTTP, và nút "Đóng" gọi `closeMicPermissionModal()`.

3. **Từ yêu cầu M7 & Mockup np_08 đến `#wsReconnectBanner`**:
   - Yêu cầu đặt ra: Khi WebSocket ngắt kết nối (`ws.onclose`), hiển thị thanh banner màu cam ở đầu layout: "Mất kết nối thời gian thực tới ngôi nhà. Đang kết nối lại (lần X/5)…".
   - Thuộc tính `role="status"` và `aria-live="polite"` thông báo nhẹ nhàng cho công nghệ hỗ trợ tiếp cận (a11y).
   - Nút "Kết nối ngay" gọi `window.retryWsConnection()` để kết nối lại ngay lập tức mà không phải chờ timer.
   - Khi kết nối thành công trở lại (`ws.onopen` sau khi đã từng đứt mạng): Banner chuyển sang class `.banner-restored` (nền xanh lá, icon checkmark, chữ "Đã khôi phục kết nối thời gian thực"), hiển thị trong đúng 2000ms (`setTimeout`), sau đó thêm class `.banner-sliding-out` để trượt mượt mà lên trên rồi ẩn hoàn toàn.

4. **Bảo toàn tính tương thích ngược và toàn vẹn DOM**:
   - 100% ID cũ trong `index.html` được giữ nguyên.
   - `house3d.js` hoàn toàn không bị chỉnh sửa.
   - Mọi hàm inline gọi từ HTML (`window.retryWsConnection`, `window.unlockSecurityLockdown`, `window.toggleLockdownMode`, `window.sendLockdownOtp`, `window.retryMicPermission`, `window.closeMicPermissionModal`) đều được export tường minh lên `window.*`, giúp vượt qua bài kiểm tra `test_challenger_m4_dom.py` với điểm số tuyệt đối 36/36.

---

## 3. Caveats (Lưu ý)

- Không có caveat nào làm ảnh hưởng đến chức năng hoặc độ an toàn của hệ thống.
- Khi kiểm thử trên môi trường không có microphone phần cứng thật (headless/CI), hàm `getUserMedia` sẽ nhảy vào catch block và kích hoạt mở `#micPermissionModal` đúng như thiết kế.
- Mở bản HTTPS chỉ hoạt động khi máy chủ hoặc tunnel HTTPS (Vercel, Cloudflare, localhost.run) đã được kích hoạt. Nếu mở trực tiếp trên localhost qua HTTP, trình duyệt tự coi localhost là Secure Context nên không bị chặn microphone.

---

## 4. Conclusion (Kết luận)

Milestone M7 đã được triển khai hoàn chỉnh, trung thực 100% theo đúng mockup và tài liệu thiết kế:
1. `#securityLockdownModal`: alertdialog, aria-modal, red alert theme, Lucide shield-alert, backdrop & Escape click disabled, form Password / Gmail OTP đầy đủ, kết nối API xác thực và reset strikes thực tế.
2. `#micPermissionModal`: dialog, aria-modal, Lucide mic-off, các nút Thử lại, Mở bản HTTPS, Đóng, gắn hook tự động trong `startMic()`.
3. `#wsReconnectBanner`: status, aria-live polite, amber bar đếm số lần kết nối lại, nút Kết nối ngay, chuyển xanh lá 2s khi kết nối khôi phục rồi trượt ẩn.
4. CSS styling trong `simulator/static/css/style.css` đáp ứng chuẩn Design System v1 Revision 2.
5. Toàn bộ 72 test suites (`test_challenger_m4_dom.py`, `test_challenger_m3_stress_dom_raycaster.py`, `test_m7_security_modals_banner.py`) đạt 100% PASS, 0 CRLF.

---

## 5. Verification Method (Phương pháp kiểm chứng độc lập)

Để kiểm chứng độc lập, chạy các lệnh sau trong terminal:

1. **Kiểm tra bộ test đối kháng DOM M4 (36 test)**:
   ```powershell
   python -X utf8 -m pytest tests/test_challenger_m4_dom.py --basetemp=.pytest_tmp
   ```
   *Kỳ vọng*: 36 passed in ~2s.

2. **Kiểm tra bộ test Three.js & Raycaster M3 (20 test)**:
   ```powershell
   python -X utf8 -m pytest tests/test_challenger_m3_stress_dom_raycaster.py --basetemp=.pytest_tmp
   ```
   *Kỳ vọng*: 20 passed in ~0.6s.

3. **Kiểm tra bộ test chuyên biệt M7 (16 test)**:
   ```powershell
   python -X utf8 -m pytest tests/test_m7_security_modals_banner.py --basetemp=.pytest_tmp
   ```
   *Kỳ vọng*: 16 passed in ~0.5s.

4. **Kiểm tra định dạng UTF-8 và 0 CRLF**:
   ```powershell
   python -c "files=['simulator/static/index.html','simulator/static/js/app.js','simulator/static/css/style.css','tests/test_m7_security_modals_banner.py']; [print(f, open(f,'rb').read().count(b'\r\n')) for f in files]"
   ```
   *Kỳ vọng*: Toàn bộ 4 file in ra số `0` CRLF.
