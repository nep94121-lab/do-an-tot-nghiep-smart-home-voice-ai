## 2026-11-04T16:31:34Z

Bạn là `worker_m14` (teamwork_worker) chịu trách nhiệm triển khai Milestone M14: Tái cấu trúc mô-đun hóa dự án theo nguyên tắc Ponytail (Requirement R4).

Thư mục làm việc: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m14\
Tệp yêu cầu gốc: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md
Tệp thiết kế & điều tra: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\explorer_p3_refactor\handoff.md
Tệp kế hoạch tổng thể: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\orchestrator\PROJECT.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

QUYỀN SỞ HỮU GHI MÃ NGUỒN (WRITE OWNERSHIP):
Bạn có toàn quyền ghi vào các tệp sau để tái cấu trúc:
1. `simulator/static/style.css` và `simulator/static/app.js` (loại bỏ dead duplicate code).
2. `simulator/voice_auth.py` và thư mục `simulator/voice/`.
3. `android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/` và các thư mục con `tabs/`, `components/`, `models/`.
4. `simulator/static/js/app.js` và `simulator/static/js/mobile_app.js`.

CÁC ĐIỀU KIỆN BẤT BIẾN BẮT BUỘC (STRICT PRESERVATION MANIFEST):
1. TUYỆT ĐỐI GIỮ NGUYÊN `simulator/static/house3d.js` (Three.js 3D concept và giao diện sáng v1 phải nguyên vẹn 100%, 0 lần sửa đổi).
2. TUYỆT ĐỐI KHÔNG SỬA / KHÔNG XÓA bất kỳ tệp nào trong `ui_mockups/`.
3. GIỮ TRỌN VẸN 68 DOM IDs trong `mobile_app/index.html`.
4. GIỮ TRỌN VẸN 25 Window hooks trong `simulator/static/js/mobile_app.js`.
5. GIỮ TRỌN VẸN 13 Window hooks và các chuỗi ký tự neo mà test Node VM đang tìm kiếm trong `simulator/static/js/app.js`:
   - `function initCameraToolbar()`
   - `initCameraToolbar();`
   - `SmartHome3D.init('house3dViewport', 'house3dLabels', toggleDeviceById)`
   - `a.strike_count >= 3` hoặc `msg.strike_count >= 3`
   - `isSecureContext`, `NotAllowedError`, `showWsRestoredBanner`
   - Lưu ý quan trọng: Các bài test đọc `app.js` và `mobile_app.js` qua `fs.readFileSync` vào Node `vm.runInContext`. Tuyệt đối KHÔNG dùng cú pháp ES module `import/export` trần trong các entry point này vì sẽ làm crash Node VM runtime! Sử dụng Facade / Re-export pattern tương thích Vanilla JS.

CHI TIẾT 4 BƯỚC THỰC HIỆN THEO NGUYÊN TẮC PONYTAIL:

Bước 1: Loại bỏ Dead Code & Duplicate Files (Giảm ngay ~2,000 dòng rác):
- `simulator/static/style.css` (970L rác): Thay thế bằng `@import url("/static/css/style.css");`
- `simulator/static/app.js` (1031L rác): Thay thế bằng script chuyển hướng gọn nhẹ tới `/static/js/app.js`.

Bước 2: Tái cấu trúc Backend Python (`simulator/voice_auth.py` từ 2,551L xuống ~450L):
- Tách các hàm DSP xử lý tín hiệu thuần, Wiener filter, MFCC sang `simulator/voice/dsp_features.py`.
- Tách các hàm sinh âm thanh / biến đổi âm giọng sang `simulator/voice/synthesis_augment.py`.
- Tách hàm kiểm tra chất lượng mẫu giọng nói sang `simulator/voice/enrollment_quality.py`.
- Trong `simulator/voice_auth.py`: Re-export toàn bộ các hàm này (`from simulator.voice.dsp_features import ...`, etc.) để bảo đảm 100% backward compatibility cho mọi caller và test suite. Giữ lại `DuplicateVoiceCheckResult` và `VoiceAuthManager`.

Bước 3: Tái cấu trúc Android Compose (`MainScreen.kt` từ 2,569L xuống ~180L):
- Tạo `tabs/HomeScreenTab.kt` (M1: Home & 2 cảm biến nhiệt độ / độ ẩm đất).
- Tạo `tabs/DevicesScreenTab.kt` (M2: Thiết bị & bộ lọc phòng).
- Tạo `tabs/VoiceScreenTab.kt` (M4: BottomSheet & ghi âm giọng nói).
- Tạo `tabs/AccountScreenTab.kt` (M2/M3/M5: Hồ sơ, OTP, Quét QR).
- Tạo `models/MainScreenModels.kt` và `components/MainComponents.kt`.
- `MainScreen.kt` trở thành composable điều phối tinh gọn (~180L).
- Kiểm tra biên dịch Android: Chạy Gradle `assembleDebug` độc lập:
  `& "C:\Users\LENOVO\.gradle\jdks\eclipse_adoptium-17-amd64-windows.2\bin\java.exe" "-Dorg.gradle.appname=gradlew" -classpath "gradle\wrapper\gradle-wrapper.jar" org.gradle.wrapper.GradleWrapperMain assembleDebug` (tại `android_app/.lightbuild/gradle/`) -> Phải đạt `BUILD SUCCESSFUL`.

Bước 4: Tinh gọn Web/Mobile JS (`app.js` & `mobile_app.js`):
- Dọn dẹp dead handlers, giữ nguyên tất cả hooks và test anchors.

KIỂM THỬ XÁC THỰC (BẮT BUỘC):
1. Chạy suite kiểm thử tích hợp:
   `python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_challenger_m4_security.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py tests/test_qa_p2_live_user_flows.py tests/test_p3_session_rbac_concurrency.py tests/test_p3_challenger_m12_adversarial.py --basetemp=.pytest_tmp`
   (Phải PASS 100%, dọn dẹp sạch `.pytest_tmp` sau khi chạy).
2. Kiểm tra định dạng: Tất cả file tạo mới / sửa đổi phải đạt 100% UTF-8 không BOM, 0 CRLF.
3. Đo đếm số dòng trước và sau tái cấu trúc của các file lớn.

Ghi báo cáo bàn giao chi tiết vào `handoff.md` và thông báo hoàn thành qua `send_message`.


## 2026-11-04T16:48:48Z
**Context**: Milestone M14 Ponytail Modularization Progress Check
**Content**: Orchestrator nhận thấy bạn đã hoàn tất Bước 1 (xóa dead code style.css, app.js) và Bước 2 (tách mô-đun Python voice). Bạn đang thực hiện Bước 3 (Android Compose MainScreen.kt) và Bước 4/5 đến đâu rồi? Vui lòng cập nhật trạng thái tiến độ vào progress.md hoặc báo cáo lại qua send_message.
**Action**: Cập nhật tiến độ hoặc hoàn tất handoff.md.
