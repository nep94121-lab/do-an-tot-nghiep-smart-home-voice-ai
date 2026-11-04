## 2026-11-04T06:36:47Z
Bạn là Subagent teamwork_challenger (Challenger 1) thực hiện kiểm thử thực nghiệm đối kháng Milestone 2: Login Gate, Password UX & Mobile SVG Fix.

MANDATORY: Đọc kỹ các tài liệu sau:
- File yêu cầu gốc của Sếp: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md`
- File kế hoạch dự án: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\PROJECT.md`
- Báo cáo bàn giao của Worker M2: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m2\handoff.md`

Thư mục làm việc của bạn: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\challenger_m2_1\`

Nhiệm vụ cụ thể:
1. Viết và thực thi một kịch bản kiểm thử đối kháng (adversarial test harness / script) trong thư mục làm việc của bạn để thử phá vỡ (stress-test / break) các tính năng vừa làm:
   - Thử bypass modal đăng nhập khi chưa có session (Escape key, backdrop click, gọi hàm đóng trực tiếp).
   - Thử nhập mật khẩu không khớp ở 2 ô xác nhận trên Web và Mobile xem có bị chặn không.
   - Thử toggle nút 👁️ trên các ô mật khẩu để kiểm tra trạng thái type `password` <-> `text`.
   - Kiểm tra ô Họ tên và Email trên `simulator/static/js/auth.js` có thật sự cho phép người dùng click sửa tự do không (`readOnly === false`).
   - Kiểm tra biểu tượng `#i-home` trên `mobile_app/index.html` có nằm ngoài `#mobileMainContent hidden` không.
2. Chạy `python -m pytest tests/test_challenger_m4_dom.py -v --basetemp=.pytest_temp_chal_m2_1`.
3. Đưa ra kết luận thực nghiệm đối kháng rõ ràng: APPROVE hoặc REQUEST_CHANGES.

Viết báo cáo bàn giao chi tiết vào:
`c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\challenger_m2_1\handoff.md`
Khi hoàn tất, gửi tin nhắn báo cáo cho Orchestrator với verdict chính thức.
