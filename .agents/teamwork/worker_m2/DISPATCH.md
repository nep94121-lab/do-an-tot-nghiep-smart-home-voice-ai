## 2026-11-04T06:20:37Z
Bạn là Subagent teamwork_worker thực hiện Milestone 2: Login Gate, Password UX & Mobile SVG Fix.

MANDATORY: Đọc kỹ các tài liệu sau trước khi thực hiện:
- File yêu cầu gốc của Sếp: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md`
- File kế hoạch dự án: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\PROJECT.md`
- Báo cáo khảo sát chi tiết của Explorer 2: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\survey_2\handoff.md`

Thư mục làm việc của bạn: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m2\`

Quyền sở hữu tệp (Write Ownership) ĐỘC QUYỀN của bạn:
1. `simulator/static/index.html` (các khu vực liên quan Login Gate `#homeLoginGateModal`, form, nút eye toggle)
2. `simulator/static/js/app.js` (logic kiểm tra đăng nhập cứng, ẩn nút `#btnCloseLoginGateModal` khi chưa có session)
3. `simulator/static/js/auth.js` (bỏ `readOnly = true` ở dòng 56 & 60 khi chọn Cấp 1)
4. `mobile_app/index.html` (chuyển khối `<svg>` sprite chứa `<symbol id="i-home">` ra ngoài `<div id="mobileMainContent" hidden>` đặt ngay sau `<body>`, thêm form enter, eye toggle, 2 ô xác nhận mật khẩu)
5. `simulator/static/js/mobile_app.js` (hỗ trợ toggle eye và 2 ô mật khẩu trên Mobile)
(TUYỆT ĐỐI KHÔNG sửa các file ngoài danh sách này).

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Nhiệm vụ cụ thể:
1. Khóa cứng Login Gate (`#homeLoginGateModal` trong `simulator/static/index.html` và `simulator/static/js/app.js`):
   - Ẩn/bỏ hoàn toàn nút `X` (`#btnCloseLoginGateModal`) khi người dùng chưa đăng nhập hợp lệ. Chặn bypass đóng ngoài lề (backdrop click / ESC).
   - Tự động mở modal khi chưa có session đăng nhập hợp lệ trong `localStorage`. Bắt buộc đăng nhập Email (`nep94121@gmail.com`) + Mật khẩu (`123456`).
2. Mở khóa mọi ô input trong `simulator/static/js/auth.js`: bỏ `readOnly = true` ở dòng 56 & 60 để người dùng bấm sửa họ tên và email tự do.
3. Chuyển đổi các khối nhập mật khẩu trên Web thành thẻ `<form onsubmit="event.preventDefault();">` để hỗ trợ phím Enter.
4. Bổ sung nút 👁️ toggle type password/text bên cạnh các ô mật khẩu trên cả Web (`gateLoginPassword`, `gateRegPassword`, `gateRegConfirmPassword`, `gateForgotNewPassword`, `gateForgotConfirmPassword`) và Mobile (`mobileLoginPassword`, v.v.).
5. Đảm bảo bắt buộc 2 ô xác nhận mật khẩu khi tạo hoặc đổi mật khẩu trên cả Web và Mobile.
6. Sửa file `mobile_app/index.html`: Di chuyển khối `<svg>` chứa các `<symbol>` (đặc biệt là `#i-home`) ra ngay sau thẻ `<body>` (bên ngoài `#mobileMainContent hidden`) để icon trên `#mobileLoginGate` luôn hiển thị đúng 100%.
7. Chạy kiểm thử xác thực:
   - `python -m pytest tests/test_challenger_m4_dom.py -v --basetemp=.pytest_temp_m2` (phải đạt 36/36 PASS, không được làm vỡ bất kỳ selector hay handler nào).

Viết báo cáo bàn giao chi tiết (bao gồm lệnh đã chạy, kết quả, file đã sửa, diff cụ thể) vào:
`c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m2\handoff.md`
Khi hoàn tất, gửi tin nhắn báo cáo cho Orchestrator kèm đường dẫn file bàn giao.
