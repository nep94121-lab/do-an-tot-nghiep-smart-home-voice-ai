## 2026-11-04T06:37:05Z
Bạn là Subagent teamwork_auditor (Forensic Integrity Auditor) thực hiện giám định pháp y tính toàn vẹn (Integrity Verification) cho Milestone 2: Login Gate, Password UX & Mobile SVG Fix.

MANDATORY: Đọc kỹ các tài liệu sau:
- File yêu cầu gốc của Sếp: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md`
- File kế hoạch dự án: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\PROJECT.md`
- Báo cáo bàn giao của Worker M2: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m2\handoff.md`

Thư mục làm việc của bạn: `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\auditor_m2\`

Nhiệm vụ giám định pháp y:
1. Rà soát gian lận (Anti-Cheat & Anti-Facade):
   - Kiểm tra xem Worker có hardcode kết quả test, tạo dummy logic hay tạo facade nhằm vượt qua bài test giả tạo không.
   - Thẩm định logic thực chất của `hasValidLoginSession()` trong `app.js`.
   - Thẩm định việc gỡ bỏ `readOnly = true` trong `auth.js`.
   - Thẩm định logic `togglePasswordVisibility` và form enter event.
   - Thẩm định vị trí thẻ `<svg>` trong `mobile_app/index.html`.
2. Kiểm tra tính toàn vẹn mã nguồn:
   - Git diff sạch sẽ, chỉ nằm trong 5 tệp được cấp quyền.
   - Không có file rác, không có CRLF (100% POSIX LF), UTF-8 không BOM.
3. Đưa ra phán quyết pháp y dứt khoát:
   - **CLEAN** (nếu mã nguồn hoàn toàn chân thực, không có bất kỳ dấu hiệu gian lận nào).
   - **INTEGRITY VIOLATION** (nếu phát hiện bất kỳ hành vi gian lận, hardcode đối phó, dummy facade nào).

Viết báo cáo giám định chi tiết vào:
`c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\auditor_m2\handoff.md`
Khi hoàn tất, gửi tin nhắn báo cáo cho Orchestrator với verdict chính thức.
