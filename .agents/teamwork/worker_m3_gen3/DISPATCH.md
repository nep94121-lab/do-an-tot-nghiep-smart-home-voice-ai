## 2026-11-05T06:44:50Z

Bạn là Worker triển khai Milestone 3 (worker_m3_gen3, role teamwork_worker) thuộc đội Teamwork Phase 7 UI Overhaul.
Thư mục làm việc của bạn: C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\worker_m3_gen3\
Mã hội thoại Parent: e7340628-f79a-4027-966a-f5d6b40bf426
Thư mục dự án: C:\Users\LENOVO\datn-wt\ui
Branch hoạt động: p7-ui

Đọc kỹ các tài liệu sau trước khi thực hiện:
- C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\ORIGINAL_REQUEST.md
- C:\Users\LENOVO\datn-wt\ui\PROJECT.md
- C:\Users\LENOVO\datn-wt\ui\TEST_INFRA.md
- C:\Users\LENOVO\datn-wt\ui\FIX_REPORT_20261104.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Nhiệm vụ cụ thể của bạn:
1. **Khởi tạo & Cập nhật `PROJECT.md` tại thư mục gốc**:
   - Mở `PROJECT.md` ở thư mục gốc `C:\Users\LENOVO\datn-wt\ui\PROJECT.md`.
   - Cập nhật dòng bảng Milestone: M2 thành `DONE`, M3 thành `IN_PROGRESS`.
2. **Thực thi Playwright Multi-Viewport E2E Audit**:
   - Viết hoặc chạy kịch bản Playwright audit trên Google Chrome headless (`channel="chrome"`).
   - Kiểm tra toàn bộ 8 routes (`/`, `/app`, `/auth`, `/wokwi`, `/logs`, `/guest_enroll`, `/login`, `/register`) trên 4 viewports: Desktop (1280x800), Mobile 360px (360x780), Mobile 390px (390x844), Mobile 430px (430x932).
   - Xác nhận 0 console errors, 0 unhandled exceptions, không có horizontal scroll overflow trên mobile.
   - Lưu ảnh chụp màn hình kiểm chứng vào thư mục `tests/artifacts/screenshots/` hoặc tương đương.
3. **Chạy Toàn Bộ Test Suite Dự Án (Pytest Full Suite)**:
   - Chạy lệnh: `python -m pytest --basetemp=.pytest_tmp -v` (khi chạy, gán `$env:GEMINI_API_KEY="test_dummy_key_12345"` hoặc truyền qua `os.environ`).
   - Đảm bảo 100% test cases (bao gồm các bộ challenger, security, routing, layout) vượt qua với `Exit Code: 0`.
4. **Kiểm tra Invariants & Ranh giới an toàn**:
   - 0 CRLF: chạy `git diff --check` và quét nhị phân `\r\n` đảm bảo 100% POSIX LF (`\n`).
   - HTML Purity: 0 thẻ `<style>`, 0 thẻ `<script>` inline không có `src` trên tất cả 8 tệp HTML.
   - Tệp cấm: `git diff --stat HEAD -- simulator/voice/ simulator/voice_auth.py simulator/live/` phải trả về rỗng 100%.
5. **Git Commit & Git Push Remote**:
   - Đảm bảo đang ở branch `p7-ui` (`git branch --show-current`).
   - Rebase trên `origin/master` nếu có commit mới từ master.
   - Commit toàn bộ các thay đổi hợp lệ với message chuẩn conventional commit:
     `feat(p7-ui): Phase 7 UI overhaul complete - minimalist auth, responsive 3d layout, optimistic UI, shared nav`
   - Push DUY NHẤT lên branch remote `p7-ui` (`git push origin p7-ui`).
   - TUYỆT ĐỐI KHÔNG push lên branch `master`.
6. **Triển Khai Vercel Preview**:
   - Chạy lệnh `npx --yes vercel --yes` (hoặc `vercel --yes`). TUYỆT ĐỐI KHÔNG thêm cờ `--prod`.
   - Trích xuất URL preview từ output của Vercel CLI (dạng `https://do-an-tot-nghiep-smart-home-voice-ai-xxx.vercel.app` hoặc tương tự).
   - Kiểm tra độc lập qua script Python: gọi HTTP GET tới tất cả 8 routes trên URL preview đó, xác nhận đều trả về `HTTP 200 OK`.
   - Ghi nhận URL Vercel preview vào `FIX_REPORT_20261104.md` (mục Deployment Preview) và ghi log vào `.agents/teamwork/cli_fix_p7_ui_20261105.log`.
7. **Bàn giao kết quả**:
   - Viết báo cáo bàn giao chi tiết tại `C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\worker_m3_gen3\handoff.md` theo chuẩn Handoff Protocol.
   - Gửi tin nhắn kết quả về cho Parent qua `send_message(Recipient="e7340628-f79a-4027-966a-f5d6b40bf426", Message=...)` bao gồm chuỗi `END <preview_url>`.
