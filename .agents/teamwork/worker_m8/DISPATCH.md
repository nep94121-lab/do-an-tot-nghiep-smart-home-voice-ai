## 2026-11-04T12:57:15Z
You are worker_m8. Your working directory is C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m8.
You MUST read:
1. C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md
2. C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\spec_miner_mobile_p2\survey_report.md
3. C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\PROJECT.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Scope & Tasks for Milestone M8:
Implement the 5 mobile screens in `mobile_app/` according to Part 2 of DESIGN_NEW_PAGES.md:
1. M1: Trang Chủ (Nhà & Cảm biến):
   - Thẻ preview Toàn cảnh 16:9 với snapshot mô hình 3D
   - Thẻ Cảm biến 2 ô Grid (Nhiệt độ 28.5°C + Độ ẩm đất 62%)
   - Thẻ Trạng thái an toàn (Cửa chính + Còi báo động)
   - Cặp nút hành động nhanh: Nói lệnh (`#mobileBtnVoiceSheet`) / Xem thiết bị (`#mobileBtnViewDevices`)
2. M2: Chuyển đổi 4 Tab độc lập & Màn Tài khoản:
   - 4 Tabs: Nhà (`tabHome`), Thiết bị (`tabDevices`), Giọng nói (`tabVoice`), Tài khoản (`tabAccount`)
   - Màn Tài khoản: Hồ sơ phân cấp (Chủ nhà / Gia đình / Khách), Menu Quản lý ('Xác thực ›', 'Lời mời ›', 'Cài đặt ›'), và nút Đăng xuất
   - Lưu ý: Giữ hàm `window.scrollToSection(sectionId)` và ánh xạ sang chuyển tab để bảo toàn 100% tương thích ngược với các test.
3. M3: Quên mật khẩu & OTP Gmail:
   - Form 3 bước (Email -> OTP 6 số `inputmode="numeric"` -> Đặt lại mật khẩu)
   - Tích hợp với API backend: `/api/auth3/forgot_password_send_otp` và `/api/auth3/forgot_password_reset`
4. M4: Bottom Sheet Giọng nói:
   - Bottom sheet kéo từ đáy (50-65%), scrim làm mờ nền
   - Vòng sóng tròn `wavecircle`, dải 12 thanh volume bar
   - Bộ đếm thời gian `00:03 / 00:05`, câu lệnh mẫu hướng dẫn và hiển thị kết quả
5. M5: Camera Quét QR & Handshake:
   - Khung ngắm quét mã QR bo góc 16px, 4 góc viền
   - Tích hợp gọi `/api/auth3/guest_handshake`
   - Giải phóng media track sạch sẽ khi đóng/rời màn hình.
6. Android Scope per Requirement R3:
   - Giữ nguyên trạng (frozen) mã nguồn Android Compose, tập trung 100% hoàn thiện trên Mobile Web PWA `/app`.
7. DOM ID & Backward Compatibility:
   - Bảo toàn TOÀN BỘ 68 DOM IDs và 25 `window.*` hooks hiện có trong `mobile_app/index.html` và `mobile_app.js`.
8. Verification:
   - Run `python -X utf8 -m pytest tests/test_challenger_m4_dom.py --basetemp=.pytest_tmp` (MUST pass 36/36)
   - Run `python -X utf8 -m pytest tests/test_challenger_m2_gate_ux_empirical.py --basetemp=.pytest_tmp` (MUST pass 33/33)
   - Run `python -X utf8 -m pytest tests/test_phase1_bugfixes_20261104.py --basetemp=.pytest_tmp`
   - Write a dedicated test file `tests/test_m8_mobile_screens.py` verifying the 5 screens, tab switching, and DOM integrity.
   - Run `python -X utf8 -m pytest tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp`
9. Write handoff report to C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m8\handoff.md with passing test evidence and send a message back when done.
