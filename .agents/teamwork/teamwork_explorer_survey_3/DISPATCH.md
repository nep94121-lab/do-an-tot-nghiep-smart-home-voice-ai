## 2026-11-04T19:15:02Z
You are teamwork_explorer_survey_3.
Your working directory is: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_explorer_survey_3\
Project root: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp

MANDATORY FIRST STEP:
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md
Also read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\REAL_TEST_BUGS_20261105.md

Your mission in this Survey phase is to investigate and analyze the authoritative codebase for the following subset of bugs:
- Bug 6: /app 3D thu gọn chỉ hiện placeholder nét đứt "Mô hình Toàn cảnh 3D", không render. Render house3d thu gọn thật (giữ concept, chỉ Toàn cảnh).
- Bug 7: Tab Thiết bị /app chỉ có 4 thiết bị (cửa, 2 đèn, quạt); thiếu điều hoà, còi, bơm — phải đủ 7 như desktop.
- Bug 8: Tab Hồ sơ /app: nút "Đăng xuất" bị bottom nav che (cần padding/safe-area, kể cả toolbar Samsung Internet). Xoá dòng "Mỗi tab mở một màn riêng...". Hàng "Mời khách" hiện đếm ngược "Còn Ns" nhảy liên tục như giá trị list → làm rõ ràng hơn.
- Bug 9: Desktop `/`: không có panel cảm biến nhiệt độ/độ ẩm/độ ẩm đất. Thêm panel cảm biến gọn; giá trị được clamp, hợp lý.
- Bug 12: QR scanner: dòng "Đưa mã QR vào trong khung để quét" hiện 2 lần → bỏ bản trùng.
- Bug 13: /logs render ~300 dòng trên một trang dài → thêm phân trang hoặc nút "xem thêm" + bộ lọc.

Scope of investigation:
1. Examine code locations in frontend `/app` (mobile view templates, 3D container & house3d.js initialization, device tab device list rendering, profile tab safe-area padding & text styling & guest countdown format), desktop index `/` (sensor panel widget, sensor reading update logic), QR scanner modal (HTML/template text duplicate), and `/logs` view (table rendering, pagination / infinite load / load more controls, filtering controls).
2. Trace exact root causes with file paths, functions, and line numbers.
3. Formulate precise TDD reproduction test strategies (how to write automated pytest or Playwright tests that fail BEFORE fix and pass AFTER fix).
4. Verify all constraints: maintain all 68 DOM IDs, window hooks, re-exports, the 3D model house3d.js, zero secrets/passwords logged, UTF-8 LF without BOM (0 CRLF).
5. Write your comprehensive survey report to C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_explorer_survey_3\handoff.md.
6. When done, send a message to caller with a brief summary of findings and the path to handoff.md.
