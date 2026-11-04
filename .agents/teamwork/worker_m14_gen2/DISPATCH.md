## 2026-11-04T16:56:50Z
Bạn là `worker_m14_gen2` (teamwork_worker) tiếp quản Milestone M14: Tái cấu trúc mô-đun hóa dự án theo nguyên tắc Ponytail (Requirement R4).

Thư mục làm việc: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m14_gen2\
Tệp yêu cầu gốc: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md
Tệp kế hoạch tổng thể: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\orchestrator\PROJECT.md
Tệp điều tra: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\explorer_p3_refactor\handoff.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

HIỆN TRẠNG MÃ NGUỒN ĐÃ HOÀN THÀNH BỞI TIỀN NHIỆM (KHÔNG LÀM LẠI):
1. Bước 1 (Dead code purge): ĐÃ HOÀN TẤT. `simulator/static/style.css` (3L) và `simulator/static/app.js` (11L) đã được chuyển đổi thành stub chuyển tiếp gọn nhẹ (xóa 1,987 dòng rác thừa).
2. Bước 2 (Python voice refactor): ĐÃ HOÀN TẤT. `simulator/voice/dsp_features.py` (790L), `simulator/voice/synthesis_augment.py` (80L), `simulator/voice/enrollment_quality.py` (305L) đã được tạo và re-export đầy đủ trong `simulator/voice_auth.py` (giảm từ 2,551L xuống 1,441L).

NHIỆM VỤ TIẾP QUẢN CỦA BẠN (TẬP TRUNG HOÀN THÀNH NGAY):

Bước 3: Tái cấu trúc Android Compose (`MainScreen.kt`):
- `android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/MainScreen.kt` hiện đang có 2,710 dòng.
- Hãy tách các composable thành các tệp độc lập trong cùng package `vn.edu.hust.seee.smarthome.ui.main`:
  - `HomeScreenContent.kt`: M1 Home view (Card ngôi nhà 16:9, Card 2 cảm biến, Card an toàn cửa/còi, 2 nút CTA "Nói lệnh" & "Xem thiết bị").
  - `DevicesScreenContent.kt`: M2 Tab thiết bị & bộ lọc phòng.
  - `VoiceScreenContent.kt`: M4 Tab giọng nói & điều khiển.
  - `AccountScreenContent.kt`: M2/M3/M5 Tab tài khoản (Hồ sơ, danh mục quản lý, chuyển màn con OTP / QR, nút Đăng xuất).
  - `MainScreenComponents.kt`: Các composable bổ trợ (`DeviceRowCard`, `BottomNav`, `TierBadge`, `StatusPill`).
- Giữ `MainScreen.kt` là composable điều phối tinh gọn, quản lý state và scaffold (~200 dòng).
- Biên dịch Gradle kiểm thử: Chạy lệnh sau tại `android_app/.lightbuild/gradle/`:
  `& "C:\Users\LENOVO\.gradle\jdks\eclipse_adoptium-17-amd64-windows.2\bin\java.exe" "-Dorg.gradle.appname=gradlew" -classpath "gradle\wrapper\gradle-wrapper.jar" org.gradle.wrapper.GradleWrapperMain assembleDebug`
  -> Phải đạt `BUILD SUCCESSFUL`.

Bước 4: Tinh gọn Web & Mobile JS:
- Rà soát `simulator/static/js/app.js` và `simulator/static/js/mobile_app.js`, dọn dẹp các đoạn code thừa mà không làm thay đổi hành vi.
- CÁC ĐIỀU KIỆN BẤT BIẾN (STRICT PRESERVATION):
  - TUYỆT ĐỐI KHÔNG SỬA `simulator/static/house3d.js` (Three.js 3D concept và giao diện sáng v1 phải nguyên vẹn 100%).
  - TUYỆT ĐỐI KHÔNG SỬA / KHÔNG XÓA bất kỳ tệp nào trong `ui_mockups/`.
  - Giữ nguyên 100% 68 DOM IDs trong `mobile_app/index.html`.
  - Giữ nguyên 100% 25 Window hooks trong `simulator/static/js/mobile_app.js`.
  - Giữ nguyên 100% 13 Window hooks và chuỗi ký tự neo trong `simulator/static/js/app.js`:
    `function initCameraToolbar()`, `initCameraToolbar();`, `SmartHome3D.init('house3dViewport', 'house3dLabels', toggleDeviceById)`, `strike_count >= 3`, `isSecureContext`, `NotAllowedError`, `showWsRestoredBanner`.
  - Lưu ý: Các bài test đọc `app.js` và `mobile_app.js` bằng `fs.readFileSync` chạy trong Node VM thuần. KHÔNG dùng cú pháp ES module `import/export` trần trong các entry point này!

Bước 5: Chạy kiểm thử xác thực:
- Chạy toàn bộ các test suite liên tầng:
  `python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_challenger_m4_security.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py tests/test_qa_p2_live_user_flows.py tests/test_p3_session_rbac_concurrency.py tests/test_p3_challenger_m12_adversarial.py --basetemp=.pytest_tmp`
  (Phải PASS 100%, dọn dẹp sạch `.pytest_tmp` sau khi chạy).
- Kiểm tra 100% tệp đạt chuẩn UTF-8 không BOM, 0 CRLF (100% POSIX LF `\n`).
- Lập bảng số dòng trước/sau tái cấu trúc của các tệp lớn.

Ghi báo cáo bàn giao chi tiết vào `handoff.md` và gửi tin nhắn hoàn thành qua `send_message`.
