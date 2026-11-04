# BRIEFING — 2026-11-04T13:14:00Z

## Mission
Triển khai 5 màn hình mobile app PWA theo Phần 2 của DESIGN_NEW_PAGES.md, bảo toàn 100% 68 DOM IDs & 25 window.* hooks hiện có, vượt qua toàn bộ test suite.

## 🔒 My Identity
- Archetype: worker
- Roles: implementer, qa, specialist
- Working directory: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m8
- Original parent: a6dd1e0f-b843-4477-96f4-146d5c9d3c58
- Milestone: M8 (Mobile Web Screens 5-in-1 PWA)

## 🔒 Key Constraints
- Giữ nguyên trạng (frozen) mã nguồn Android Compose, tập trung 100% hoàn thiện trên Mobile Web PWA `/app`.
- Bảo toàn TOÀN BỘ 68 DOM IDs và 25 `window.*` hooks hiện có trong `mobile_app/index.html` và `mobile_app.js`.
- Giữ hàm `window.scrollToSection(sectionId)` và ánh xạ sang chuyển tab để bảo toàn 100% tương thích ngược với các test.
- Tích hợp API backend: `/api/auth3/forgot_password_send_otp`, `/api/auth3/forgot_password_reset`, `/api/auth3/guest_handshake`.
- Verification tests bắt buộc pass:
  - `tests/test_challenger_m4_dom.py` (36/36)
  - `tests/test_challenger_m2_gate_ux_empirical.py` (33/33)
  - `tests/test_phase1_bugfixes_20261104.py` (6/6)
  - `tests/test_m8_mobile_screens.py` (22/22)
- Không cheat, không hardcode test results.

## Current Parent
- Conversation ID: a6dd1e0f-b843-4477-96f4-146d5c9d3c58
- Updated: 2026-11-04T13:14:00Z

## Task Summary
- **What to build**: 5 mobile screens (M1 Trang Chủ & Cảm biến, M2 Hệ thống 4 Tab & Màn Tài khoản, M3 Quên mật khẩu & OTP Gmail, M4 Bottom Sheet Giọng nói, M5 Camera Quét QR & Handshake) trong `mobile_app/`.
- **Success criteria**: 100% test PASS, bảo toàn 68 DOM IDs, 25 window hooks, giao diện khớp mockup Codex `np_m1` - `np_m5`.

## Key Decisions Made
- Thiết kế 4 tab view độc lập (`tabViewHome`, `tabViewDevices`, `tabViewVoice`, `tabViewAccount`) với thanh điều hướng 4 nút `#mobileBottomNav`.
- Hàm `scrollToSection(id)` ánh xạ tự động sang `switchMobileTab(tabKey)` để tương thích ngược 100% với các test cũ mà không gây scroll giật trên mobile.
- Thẻ preview Toàn cảnh 16:9 với class `.preview-16-9`, aspect-ratio 16/9, không điều hướng desktop.
- Thẻ cảm biến 2 ô Grid: Nhiệt độ 28.5°C & Độ ẩm đất 62%, loại bỏ ô thứ 3 ở màn Home theo đúng đặc tả v1.
- Tích hợp form Quên mật khẩu 3 bước với API `/api/auth3/forgot_password_send_otp` và `/api/auth3/forgot_password_reset`.
- Bottom sheet giọng nói kéo từ đáy 50-65% với vòng tròn sóng, 12 vạch volume bars animation, bộ đếm 5s, và câu mẫu.
- Camera quét QR với khung 4 góc line viền, tích hợp gọi `/api/auth3/guest_handshake` và giải phóng media track khi đóng.
- Giữ nguyên trạng (frozen) mã nguồn Android Compose theo Requirement R3.

## Artifact Index
- `.agents/teamwork/worker_m8/DISPATCH.md` — Nhiệm vụ được giao
- `.agents/teamwork/worker_m8/progress.md` — Nhật ký tiến độ và heartbeat
- `.agents/teamwork/worker_m8/handoff.md` — Báo cáo nghiệm thu bàn giao

## Change Tracker
- **Files modified**:
  - `mobile_app/index.html`: Cập nhật cấu trúc 5 màn hình M1-M5, giữ nguyên 68 DOM IDs và SVG sprite.
  - `simulator/static/css/mobile_app.css`: Bổ sung styles cho 16:9 preview, sensorgrid, scrim, bottom sheet, wavecircle, volume bars, scanner.
  - `simulator/static/js/mobile_app.js`: Thêm `switchMobileTab`, `updateAccountProfile`, OTP reset, Voice bottom sheet, QR scanner camera, đồng bộ trạng thái cửa & còi an toàn.
  - `simulator/api/routes_qr.py`: Thêm alias route `@router.post("/api/auth3/guest_handshake")`.
  - `tests/test_m8_mobile_screens.py`: Bộ kiểm thử mới cho 5 màn hình M8 (22 test cases).
- **Build status**: 97/97 passed (test_challenger_m4_dom, test_challenger_m2_gate_ux_empirical, test_phase1_bugfixes_20261104, test_m8_mobile_screens)
- **Pending issues**: Không có

## Quality Status
- **Build/test result**: 97 passed, 0 failed
- **Lint status**: Clean
- **Tests added/modified**: `tests/test_m8_mobile_screens.py` (+22 tests)
