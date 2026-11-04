## 2026-11-04T15:26:17Z
You are teamwork_worker assigned to Milestone M13: Android Native Compose (M1–M5) & assembleDebug (Requirement R3).

## Mandatory Reading
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md before beginning.
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\explorer_p3_android\handoff.md for exact build commands, JDK paths, and M1–M5 gap analysis.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership
You exclusively own:
- `android_app/` directory (all build files and Kotlin sources)
- `ui_mockups/android_phase3/` (for screenshots)
DO NOT modify any backend Python files or `vercel.json`.

## Detailed Tasks
1. Fix Gradle build configuration:
   - Add `android.overridePathCheck=true` to `android_app/.lightbuild/gradle/gradle.properties`.
2. Implement / Refine M1–M5 screens in Jetpack Compose:
   - In `android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/`:
     - M1 Home & Sensors: TopBar "Nhà của tôi", Card Ngôi nhà 16:9, Card Cảm biến 2-ô grid (Nhiệt độ 28.5°C, Độ ẩm đất 62%), Card Trạng thái an toàn (Cửa chính, Còi báo động), Bottom CTA ("Nói lệnh", "Xem thiết bị"). Remove redundant 4-device card from Home.
     - M2 Account & Tabs: Card Hồ sơ 3 dòng (Vai trò, Email, Thời hạn), Card Quản lý, Nút Đăng xuất.
     - M3 Forgot Password OTP: Composable with 3 steps (Email -> 6-digit OTP -> Reset password).
     - M4 Voice Bottom Sheet: Modal bottom sheet with scrim, 12-bar animated waveform, timer 00:03/00:05, sample phrase "Mở cửa chính cho tôi.".
     - M5 QR Scanner: Viewfinder 215x215dp 4-corner frame, "Bật camera", "Nhập mã".
3. Build verification:
   - Run `assembleDebug` using JDK 17:
     `& "C:\Users\LENOVO\.gradle\jdks\eclipse_adoptium-17-amd64-windows.2\bin\java.exe" -Dorg.gradle.appname=gradlew -classpath gradle\wrapper\gradle-wrapper.jar org.gradle.wrapper.GradleWrapperMain assembleDebug` inside `android_app/.lightbuild/gradle/` (or via gradle wrapper).
   - Must achieve BUILD SUCCESSFUL.
4. Check ADB S9 device:
   - Run `& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" devices`.
   - If device serial `2223e8784b0c7ece` is online:
     - Set `$env:ADB_LIBUSB="1"` and `adb -s 2223e8784b0c7ece reverse tcp:8088 tcp:8088`.
     - Install APK via `adb -s 2223e8784b0c7ece install -r app/build/outputs/apk/debug/app-debug.apk`.
     - Launch `MainActivity`.
     - Capture screenshots into `ui_mockups/android_phase3/` and verify images.
     If device is not physically connected, document device connection status clearly in handoff.md.
5. Produce structured handoff report at:
   `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m13\handoff.md`
   Send a completion message back when done.
