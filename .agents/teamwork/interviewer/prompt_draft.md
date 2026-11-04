Triển khai Giai đoạn 3 (Phase 3) cho đồ án tốt nghiệp: sửa lỗi routing Vercel production, chuyển RBAC sang quản lý theo từng session/request, kiểm tra và build Android native Compose (M1–M5), refactor mô-đun hóa toàn dự án theo nguyên tắc skill ponytail, vượt qua toàn bộ gating kiểm thử và deploy Vercel production.

Working directory: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp
Integrity mode: development

## Reference Material
- FIX_REPORT_20261104.md
- FIX_PLAN_20261104.md
- UI Mockups: ui_mockups/v2_new_pages (np_m1..np_m5)
- Production Domain: https://do-an-tot-nghiep-smart-home-voice-a.vercel.app

## Requirements

### R1. Sửa routing Vercel production
Sửa lỗi routing trên https://do-an-tot-nghiep-smart-home-voice-a.vercel.app: các đường dẫn /mobile, /architecture, /offline, /404, /403, /500, /qr_expired, /sw.js phải hoạt động và không trả về Vercel NOT_FOUND. URL không tồn tại phải hiện trang 404 tùy biến. /mobile chuyển hướng về /app nếu đó là trang dự định. Sau deploy phải kiểm tra bằng curl trên production domain thật (...voice-a.vercel.app).

### R2. Bảo mật RBAC theo session
Đổi tier RBAC từ lấy state global của engine (user đăng nhập cuối) sang quản lý theo từng session (cookie/token) cho mỗi request để 2 người dùng đồng thời không bao giờ lẫn quyền. Bổ sung test kiểm thử cho các session đồng thời của 3 vai trò (owner, admin, user/guest).

### R3. Android native Compose
Kiểm tra các màn M1–M5 đúng theo ui_mockups/v2_new_pages (np_m1..np_m5). Lệnh assembleDebug phải hoàn thành với kết quả SUCCESSFUL. Nếu thiết bị S9 (adb serial 2223e8784b0c7ece, adb tại %LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe) đang kết nối thì cài APK, mở app, lưu screencap vào ui_mockups/android_phase3/.

### R4. Quét dự án và refactor mô-đun hóa
Tải/cài skill ponytail (tìm qua agy plugin/skills, GitHub...; cài nếu tìm thấy). Dùng skill này hoặc tuân theo nguyên tắc của nó để quét toàn dự án và refactor: tách các file dài hàng nghìn dòng (app.js, các module Python, MainScreen.kt...) thành module rõ ràng, xóa dead code và code trùng lặp, sắp xếp thư mục gọn gàng. Tuyệt đối KHÔNG thay đổi hành vi. Giữ concept 3D house3d.js và thiết kế v1 sáng. Không xóa file thiết kế trong ui_mockups. Giữ đầy đủ các re-export/entry-point/DOM IDs/window hooks mà các bài test E2E và Challenger đang kiểm tra.

### R5. Verification Gates
Toàn bộ pytest PASS 100% (chạy với python -X utf8 -m pytest tests/ --basetemp=.pytest_tmp và xóa .pytest_tmp sau khi chạy). Playwright/luồng thật cho 3 vai trò PASS. assembleDebug SUCCESSFUL. Reviewer xác nhận không đổi hành vi; auditor xác nhận không có facade hay test gian lận. Không dừng khi còn bất kỳ FAIL nào. Dùng mật khẩu mặc định của tài khoản owner trong seed của dự án (không ghi vào báo cáo).

### R6. Git Commit, Vercel Deploy và Báo cáo
Chỉ làm trong thư mục dự án, không đụng Desktop BA-SVD hay vị trí khác ngoài dự án. Commit, push lên master, deploy Vercel production, kiểm tra lại mọi URL production. Thêm mục Phase 3 vào FIX_REPORT_20261104.md với số dòng trước/sau của các file lớn.

## Verification Resources
- Test suite hiện có trong thư mục `tests/`:
  - `tests/test_m3_challenger_api.py`
  - `tests/test_challenger_m4_dom.py`
  - `tests/test_challenger_m4_security.py`
  - `tests/test_challenger_m5_devtools.py`
  - `tests/test_m6_web_error_sw.py`
  - `tests/test_m7_security_modals_banner.py`
  - `tests/test_m8_mobile_screens.py`
  - `tests/test_qa_p2_live_user_flows.py`
  - Các bài test mới bổ sung cho kịch bản đồng thời của 3 vai trò và Vercel routing
- Script hội tụ và kiểm tra: `scripts/speckit_converge.py`
- Lệnh chạy test chuẩn: `python -X utf8 -m pytest tests/ --basetemp=.pytest_tmp`
- Báo cáo và kế hoạch giai đoạn trước: `FIX_REPORT_20261104.md`, `FIX_PLAN_20261104.md`
- Tài liệu mockups UI: `ui_mockups/v2_new_pages/` (np_m1..np_m5)
- Kiểm tra thiết bị: `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`

## Acceptance Criteria

### Production Routing
- [ ] Các URL /mobile, /architecture, /offline, /404, /403, /500, /qr_expired, /sw.js truy cập thành công trên https://do-an-tot-nghiep-smart-home-voice-a.vercel.app không bị lỗi Vercel NOT_FOUND.
- [ ] URL không tồn tại hiển thị trang 404 tùy biến.
- [ ] /mobile chuyển hướng về /app.
- [ ] curl kiểm tra tất cả các endpoint production trả về mã trạng thái hợp lệ.

### RBAC Security
- [ ] Quyền RBAC được xác thực độc lập theo session (cookie/token) của từng request, 2 session đồng thời không bao giờ bị lẫn quyền.
- [ ] Test tự động xác thực thành công kịch bản đồng thời của 3 vai trò (owner, admin, user/guest).

### Android Native Compose
- [ ] Gradle assembleDebug hoàn thành với kết quả SUCCESSFUL.
- [ ] Các màn hình M1–M5 đối chiếu đúng với ui_mockups/v2_new_pages (np_m1..np_m5).
- [ ] Nếu thiết bị S9 (serial 2223e8784b0c7ece) kết nối qua adb, APK được cài đặt, mở app và ảnh chụp màn hình được lưu vào ui_mockups/android_phase3/.

### Refactoring & Code Quality
- [ ] Các file lớn (app.js, Python modules, MainScreen.kt...) được tách nhỏ thành các module rõ ràng mà không làm thay đổi hành vi.
- [ ] Dead code và duplicate code được dọn dẹp; các file thiết kế trong ui_mockups và concept 3D house3d.js được giữ nguyên.
- [ ] Tất cả re-export, entry-point, DOM ID, window hook cho test E2E/Challenger được giữ trọn vẹn.
- [ ] FIX_REPORT_20261104.md có mục Phase 3 ghi nhận số dòng trước/sau của các file lớn.

### Gating
- [ ] pytest PASS 100%.
- [ ] Playwright E2E cho 3 vai trò PASS 100%.
- [ ] assembleDebug SUCCESSFUL.
- [ ] Reviewer xác nhận không đổi hành vi và auditor xác nhận không có test gian lận hay facade.
- [ ] Code được commit, push master và deploy Vercel production thành công.
