# HANDOFF REPORT — SPEC MINER MOBILE (PART 2)

**Agent ID**: spec_miner_mobile_p2  
**Parent Agent ID**: a6dd1e0f-b843-4477-96f4-146d5c9d3c58  
**Working Directory**: `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\spec_miner_mobile_p2`  
**Handoff Type**: Hard (Task Complete)  

---

## 1. Observation

1. **Đặc tả 5 màn Mobile Part 2 trong `ui_mockups/v2_new_pages/DESIGN_NEW_PAGES.md`**:
   - Dòng 73–78: **M1 · Nhà và cảm biến** (`np_m1_home_sensors.html`): Header "Nhà của tôi" + dot kết nối, thẻ "Ngôi nhà" nhãn "Toàn cảnh" với placeholder tỷ lệ 16:9 (dùng viewport/preview tài sản hiện hữu, không redirect desktop), thẻ "Cảm biến" 2 ô Grid (Nhiệt độ 28.5°C, Độ ẩm đất 62%), thẻ "Trạng thái an toàn" (Cửa chính: Đang khóa, Còi báo động: Tắt), 2 nút hành động ("Nói lệnh" primary có icon mic, "Xem thiết bị" secondary).
   - Dòng 80–86: **M2 · Bốn tab độc lập và Tài khoản** (`np_m2_tabs_account.html`): Shell dùng chung (Header ~64px, `main` `overflow-y:auto`, bottom nav 64px + safe-area). 4 đích độc lập: "Nhà", "Thiết bị", "Giọng nói", "Tài khoản". Đặc tả quy định: *"Chọn tab thay toàn bộ nội dung `main`, không scroll tới section của trang khác."* Thẻ Tài khoản gồm: Hồ sơ (Vai trò, Email che `t***@gmail.com`, Thời hạn), Quản lý ("Xác thực ›", "Lời mời ›", "Cài đặt ›"), nút "Đăng xuất" secondary tách riêng ở cuối.
   - Dòng 87–93: **M3 · Quên mật khẩu Gmail OTP** (`np_m3_forgot_otp.html`): Màn login riêng, header có quay lại, 3 bước (B1 email, B2 OTP 6 số, B3 mật khẩu mới). Mockup Bước 2: "Bước 2/3", H1 "Quên mật khẩu", ô nhập OTP `<input class="field" id="otp" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}">`, 3 nút ("Xác nhận mã", "Gửi lại mã", "Đổi email").
   - Dòng 94–100: **M4 · Bottom sheet giọng nói** (`np_m4_voice_sheet.html`): Tab Giọng nói mờ phía sau, overlay `.scrim` và `.sheet` từ đáy (50–65% màn hình), bo góc 20px, nút đóng `x`, vòng sóng `.wavecircle`, 12 vạch sóng âm `.bars`, timer `00:03 / 00:05`, khung câu mẫu `.phrase` ("Mở cửa chính cho tôi."), nút hành động tương ứng trạng thái ("Dừng thu" / "Hủy" hoặc "Thu lại" / "Đóng"), kết quả text `.result` ("Đạt — đã xác thực" hoặc "Chưa đạt...").
   - Dòng 101–107: **M5 · Camera quét QR** (`np_m5_qr_scanner.html`): Màn riêng trong `/app`, header "Quét mã QR" + đóng, vùng camera lớn `.camera` nền tối, khung quét `.scanframe` 215x215px kẻ 4 góc `.tl, .tr, .bl, .br`, chỉ dẫn "Đưa mã QR vào trong khung để quét", nút "Bật camera" / "Nhập mã". Bắt buộc dùng camera sau, giải phóng camera track khi rời màn hình.

2. **Cách `/app` được phục vụ trong `simulator/server.py`**:
   - Dòng 70: `MOBILE_APP_DIR = ROOT / "mobile_app"`
   - Dòng 101–103:
     ```python
     @app.get("/app")
     async def mobile_app_index() -> FileResponse:
         return FileResponse(MOBILE_APP_DIR / "index.html")
     ```
   - Dòng 107–108: `app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")`
   - File `mobile_app/index.html` dòng 11 và 410 nạp:
     - `<link rel="stylesheet" href="/static/css/mobile_app.css" />` trỏ tới `simulator/static/css/mobile_app.css`
     - `<script src="/static/js/mobile_app.js"></script>` trỏ tới `simulator/static/js/mobile_app.js`

3. **Khảo sát Android Compose trong `android_app/`**:
   - `android_app/` được cấu hình bằng hệ thống Google Lightbuild (`project.lightbuild.yaml`, pinned version `0.0.30`, Kotlin `2.3.20`, Java 17).
   - Mã Compose chính nằm tại `android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/MainScreen.kt` (gồm 2570 dòng code).
   - Kiểm tra `gradlew.bat`: Không có ở root hay `android_app/`, chỉ tồn tại tại `android_app\.lightbuild\gradle\gradlew.bat`.
   - Thực thi `cmd /c gradlew.bat assembleDebug` thất bại:
     `ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.`
   - Thực thi `lightbuild build //app` thất bại sau khi resolve dependencies 100%:
     `Build file '...\android_app\.lightbuild\gradle\app\build.gradle' line: 2`
     `Failed to apply plugin 'com.android.internal.application'. Your project path contains non-ASCII characters. This will most likely cause the build to fail on Windows. Please move your project to a different directory. See http://b.android.com/95744 for details. This warning can be disabled by adding the line 'android.overridePathCheck=true' to gradle.properties file in the project directory.`
     `✗ BUILD FAILED in 110843ms`

4. **DOM IDs và Hooks Compatibility**:
   - `simulator/static/js/mobile_app.js` truy vấn chính xác **68 DOM IDs** (được kiểm chứng bởi `extract_info.py`), và toàn bộ 68 IDs này đều đang tồn tại đầy đủ trong `mobile_app/index.html`.
   - File `mobile_app/index.html` có **37 inline event handlers**; tất cả đều gọi các hàm được khai báo hoặc export toàn cục vào `window.*` (gồm **25 window exports** trong `mobile_app.js`).
   - `tests/test_challenger_m2_gate_ux_empirical.py` kiểm định:
     - Thẻ `<form>`: `#mobileLoginForm`, `#mobileRegisterForm`, `#mobileChangePasswordForm`.
     - Nút submit: `#mobileLoginBtn`, `#mobileRegisterBtn`, `#mobileChangePasswordBtn`.
     - 5 ô mật khẩu đều có nút `.btn-toggle-pw` (`👁️`) gọi `togglePasswordVisibility`.
     - Khối `<svg>` sprite chứa 9 symbols (`i-home`, `i-grid`, `i-mic`, `i-user`, `i-lamp`, `i-fan`, `i-snow`, `i-door`, `i-bell`) phải nằm trực tiếp dưới `<body>` bên ngoài `#mobileMainContent` có thuộc tính `hidden`.
     - Logic kiểm tra mật khẩu không khớp: `password !== confirmPassword` và `pw1 !== pw2`.
   - `tests/test_adb_samsung_galaxy_s9.py` thao tác kịch bản thật trên Samsung Galaxy S9:
     - Mở URL `http://localhost:8088/app` -> Login Gate (`#mobileLoginGate`).
     - Bấm nút Đăng nhập -> Vào `#mobileMainContent`.
     - Điều khiển thiết bị trên `#devGrid`.
     - Bấm Tab 4 "Tài khoản" -> Mở thẻ `#mobileDynamicQrCard`.

---

## 2. Logic Chain

1. Từ **Quan sát 1 & 2**:
   - Mục tiêu của Phase 2 là triển khai 5 màn hình M1 – M5 cho Mobile `/app`.
   - `/app` được phục vụ thông qua FastAPI đọc `mobile_app/index.html` và nạp CSS/JS tại `simulator/static/css/mobile_app.css` và `simulator/static/js/mobile_app.js`.
   - Hiện tại giao diện mobile đang là một trang cuộn dài (single scroll view) với `scrollToSection()`, trong khi đặc tả M2 yêu cầu chuyển đổi tab độc lập (tab switching view).

2. Từ **Quan sát 3**:
   - Lệnh `./gradlew assembleDebug` trực tiếp thất bại do thiếu `JAVA_HOME`.
   - Lệnh `lightbuild build //app` thất bại do đường dẫn dự án chứa tiếng Việt có dấu (`đồ án tốt nghiệp`) kích hoạt lỗi của Android Gradle Plugin trên Windows.
   - Chỉ thị R3 trong `ORIGINAL_REQUEST.md` quy định rõ ràng: *"Ưu tiên hoàn thiện toàn bộ trên Web và Mobile Web (`mobile_app/` / `/app`); chỉ chỉnh sửa Android Compose nếu có phần liên quan trực tiếp và đảm bảo assembleDebug PASS nếu đụng tới."*
   - Suy ra: **Mobile Web (`mobile_app/` / `/app`) là mục tiêu chính thức và duy nhất cần tập trung triển khai trong Phase 2.** Tuyệt đối không can thiệp hay sửa mã Kotlin Compose (`MainScreen.kt`) để tránh rủi ro vi phạm điều kiện bàn giao.

3. Từ **Quan sát 4**:
   - Bộ test `test_challenger_m4_dom.py` và `test_challenger_m2_gate_ux_empirical.py` đã PASS 69/69 bài test đối soát nghiêm ngặt từng DOM ID, inline handler, toggle button, và cấu trúc SVG sprite.
   - Khi tái cấu trúc sang tab switcher M2 và bổ sung các màn M1, M3, M4, M5, đội implement bắt buộc phải duy trì 100% 68 DOM IDs và 25 `window.*` exports, đồng thời bọc hàm `scrollToSection(id)` để vừa chuyển tab vừa không phá vỡ bất kỳ test hook nào.

---

## 3. Caveats

1. **Android Build Environment**: Không sửa cấu hình hệ thống máy trạm (không tự ý cài JDK hay đổi tên thư mục gốc workspace `đồ án tốt nghiệp`) vì việc đổi tên thư mục gốc sẽ làm gãy đường dẫn workspace của người dùng và toàn bộ git repository.
2. **Backend API Endpoints**: Các API `/api/auth3/forgot_password_send_otp`, `/api/auth3/forgot_password_reset`, `/api/auth3/guest_qr_handshake`, `/api/auth3/enroll_voice_sample` đã có sẵn đầy đủ trong `routes_auth.py` và `routes_qr.py`. Đội implement chỉ cần tích hợp giao diện frontend vào các endpoint này, không cần viết lại API mới.

---

## 4. Conclusion

1. **Phạm vi triển khai Mobile Part 2 gồm 5 màn hình**:
   - **M1**: Cập nhật thẻ Toàn cảnh (preview inline), thẻ Cảm biến 2 ô Grid (Nhiệt độ + Độ ẩm đất), thẻ Trạng thái an toàn, cặp nút Nói lệnh / Xem thiết bị.
   - **M2**: Chuyển đổi kiến trúc sang Tab Switcher độc lập (Nhà, Thiết bị, Giọng nói, Tài khoản). Cập nhật tab Tài khoản với Hồ sơ phân cấp, Menu Quản lý, và nút Đăng xuất.
   - **M3**: Tích hợp màn Quên mật khẩu 3 bước với OTP Gmail, liên kết với API có sẵn.
   - **M4**: Tích hợp Bottom Sheet thu âm giọng nói với animation 12 vạch sóng âm, timer và câu mẫu.
   - **M5**: Tích hợp màn Camera quét QR với khung ngắm 4 góc line, camera sau và xử lý handshake.
2. **Phạm vi Android**: Khóa nguyên trạng (frozen). Không sửa đổi mã Kotlin Compose trong `android_app/`.
3. **Bảo toàn tương thích**: Giữ nguyên toàn bộ 68 DOM IDs, 37 inline event handlers, 25 window exports, 3 thẻ `<form>` có `onsubmit`, và các nút `.btn-toggle-pw`.

---

## 5. Verification Method

1. **Kiểm tra báo cáo khảo sát**:
   - Đọc file `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\spec_miner_mobile_p2\survey_report.md`
2. **Kiểm tra tương thích DOM và Gate UX**:
   ```powershell
   python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_challenger_m2_gate_ux_empirical.py --basetemp=.pytest_tmp
   ```
   *Điều kiện PASS*: 69 passed trong < 3 giây.
3. **Kiểm tra phân tích ID và Handlers**:
   ```powershell
   python ".agents\teamwork\spec_miner_mobile_p2\extract_info.py"
   ```
   *Điều kiện PASS*: `Total inline event handlers in index.html: 37`, 0 missing functions.
