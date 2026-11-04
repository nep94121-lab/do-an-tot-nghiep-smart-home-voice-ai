# BRIEFING — 2026-11-04T06:33:00Z

## Mission
Triển khai Milestone 2: Login Gate, Password UX & Mobile SVG Fix cho Smart Home Voice AI (Web Simulator và Mobile App).

## 🔒 My Identity
- Archetype: teamwork_worker
- Roles: implementer, qa
- Working directory: c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m2\
- Original parent: cb4be64f-6f73-4e8f-b499-50863e4051dc
- Milestone: Milestone 2 (Login Gate, Password UX & Mobile SVG Fix)

## 🔒 Key Constraints
- Quyền sở hữu tệp ĐỘC QUYỀN:
  1. `simulator/static/index.html`
  2. `simulator/static/js/app.js`
  3. `simulator/static/js/auth.js`
  4. `mobile_app/index.html`
  5. `simulator/static/js/mobile_app.js`
  TUYỆT ĐỐI KHÔNG sửa các file ngoài danh sách này.
- Integrity: Không hardcode kết quả test, không tạo dummy/facade.
- Định dạng UTF-8 không BOM, POSIX LF (`\n`), 0 CRLF.
- Ngôn ngữ: 100% Tiếng Việt, link clickable `[Tên File](file:///...)`.
- Phải đạt 36/36 tests pytest trong `tests/test_challenger_m4_dom.py`.

## Current Parent
- Conversation ID: cb4be64f-6f73-4e8f-b499-50863e4051dc
- Updated: 2026-11-04T06:33:00Z

## Task Summary
- **What to build**:
  1. Khóa cứng Login Gate (`#homeLoginGateModal`), ẩn nút đóng khi chưa đăng nhập, tự mở modal khi chưa có session `localStorage`, chặn bypass backdrop/ESC, xác thực `nep94121@gmail.com` / `123456`.
  2. Bỏ `readOnly = true` ở `auth.js` (dòng 56 & 60) cho phép sửa họ tên và email tự do khi chọn Cấp 1.
  3. Bọc input mật khẩu vào thẻ `<form onsubmit="event.preventDefault();">` hỗ trợ phím Enter.
  4. Nút 👁️ toggle type password/text bên cạnh các ô mật khẩu Web và Mobile.
  5. Bắt buộc 2 ô mật khẩu (xác nhận mật khẩu) khi tạo mới hoặc đổi mật khẩu.
  6. Sửa `mobile_app/index.html`: Di chuyển SVG sprite chứa `#i-home` ra ngoài `#mobileMainContent hidden` ngay sau thẻ `<body>`.
- **Success criteria**:
  - Không vỡ selector hay handler hiện có.
  - Test suite `tests/test_challenger_m4_dom.py` chạy 36/36 PASS.
  - Bàn giao đầy đủ theo mẫu 5 phần.

## Key Decisions Made
- [Khởi tạo kế hoạch]
- Khóa cứng `closeLoginGateModal` với hàm `hasValidLoginSession()`, chặn backdrop click và ESC key khi chưa có phiên đăng nhập hợp lệ.
- Nút `#btnCloseLoginGateModal` có thuộc tính `hidden` mặc định trong HTML và được mở khóa bằng JS chỉ sau khi đăng nhập thành công.
- Chuyển `gatePanelLogin`, `gatePanelRegister`, `gatePanelForgot` thành thẻ `<form onsubmit="event.preventDefault();">` với nút `type="submit"` và hỗ trợ phím Enter.
- Thêm nút 👁️ toggle type password/text cho cả 5 ô mật khẩu trên Web và 5 ô mật khẩu trên Mobile.
- Bỏ `readOnly = true` trong `auth.js`, đồng bộ họ tên giữa step 1 và step 2 thông suốt.
- Di chuyển thẻ `<svg>` sprite chứa `#i-home` ra ngay sau `<body>` trong `mobile_app/index.html` để icon luôn hiển thị đúng.
- Bổ sung Form Đặt/Đổi mật khẩu với 2 ô xác nhận trên Mobile Login Gate (`#mobileRegisterForm`) và trong mục Tài khoản (`#mobileChangePasswordForm`).

## Artifact Index
- `.agents/teamwork/worker_m2/DISPATCH.md` — Chỉ thị từ Orchestrator
- `.agents/teamwork/worker_m2/BRIEFING.md` — Bộ nhớ làm việc
- `.agents/teamwork/worker_m2/progress.md` — Tiến độ theo dõi
- `.agents/teamwork/worker_m2/handoff.md` — Báo cáo nghiệm thu bàn giao

## Change Tracker
- **Files modified**:
  - `simulator/static/index.html`: Thêm hidden cho nút X, bọc `<form>`, thêm nút 👁️ cho 5 ô mật khẩu Web.
  - `simulator/static/js/app.js`: Thêm `hasValidLoginSession()`, `togglePasswordVisibility`, chặn backdrop/ESC, bọc submit handlers.
  - `simulator/static/js/auth.js`: Bỏ `readOnly = true` ở dòng 56 & 60, cho phép sửa họ tên và email tự do khi chọn Cấp 1.
  - `mobile_app/index.html`: Chuyển `<svg>` sprite ra ngay sau `<body>`, thêm tabs, form đăng ký 2 ô mật khẩu và đổi mật khẩu kèm nút 👁️.
  - `simulator/static/js/mobile_app.js`: Thêm `togglePasswordVisibility`, `switchMobileLoginTab`, `onMobileRegTierChange`, `submitMobileRegister`, `submitMobileChangePassword` và export lên window.
- **Build status**: `tests/test_challenger_m4_dom.py` PASSED 36/36 (Exit Code 0).
- **Pending issues**: Không có

## Quality Status
- **Build/test result**: 36/36 tests PASSED; xác thực tự động 10 tiêu chí con đạt 100%.
- **Lint status**: 0 CRLF, 100% UTF-8 không BOM.
- **Tests added/modified**: Kiểm chứng tự động tích hợp 10 assert độc lập.

## Loaded Skills
- N/A
