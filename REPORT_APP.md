# Báo Cáo Kiểm Thử & Hoàn Thiện Ứng Dụng Android (`p7-app`)

## 1. Tổng Quan Môi Trường & Thiết Bị Kiểm Thử
- **Nhánh làm việc:** `p7-app` (Worktree: `C:\Users\LENOVO\datn-wt\app`)
- **Backend Production:** `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`
- **Hệ thống Build:** Lightbuild `0.0.30` (`app:app-debug.apk`, `app-core:hostTest`)
- **Thiết bị vật lý kết nối qua ADB:** Samsung Galaxy S9 (`SM_G960F`, serial `2223e8784b0c7ece`, Android 10 / API 29, độ phân giải `1080x2220`, mật độ `480 dpi`)
- **Gói ứng dụng (Application ID):** `vn.edu.hust.seee.smarthome`

---

## 2. Các Hạng Mục Sửa Lỗi & Nâng Cấp Mã Nguồn

1. **Chuyển Mặc Định Sang Production URL & Đồng Bộ Trạng Thái Thực (`MainScreen.kt`):**
   - Cập nhật hàm `callServerHttp` trong [`MainScreen.kt`](file:///C:/Users/LENOVO/datn-wt/app/android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/MainScreen.kt) sử dụng `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app` làm địa chỉ máy chủ mặc định (`allowLocalDebugFallback = false`). Các địa chỉ cục bộ (`http://10.0.2.2:8088`, `http://127.0.0.1:8088`, `http://localhost:8088`) chỉ được giữ làm tùy chọn dự phòng khi bật cờ debug.
   - Bổ sung hàm `syncServerState()` gọi `GET /api/state` ngay khi khởi chạy ứng dụng để đồng bộ trạng thái 7 thiết bị, nhiệt độ (`28.5°C`), độ ẩm (`62%`), độ ẩm đất (`48%`) và cập nhật huy hiệu trạng thái `Đã kết nối`.
   - Loại bỏ toàn bộ thông tin tài khoản/mật khẩu/token mẫu cứng trong mã nguồn; lưu `activeSessionToken` động trong bộ nhớ RAM sau khi đăng nhập và gửi qua header `X-Session-Token`.

2. **Đăng Ký & Đăng Nhập Tài Khoản Thực Trên Production (`MainScreen.kt`, `AccountScreenTab.kt`):**
   - Bổ sung hàm `performRegisterAccount()` gọi `POST /api/auth3/register_or_set_password` và nâng cấp `performLayer1Login()` gọi `POST /api/auth3/layer1_login` trong [`MainScreen.kt`](file:///C:/Users/LENOVO/datn-wt/app/android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/MainScreen.kt).
   - Cập nhật [`AccountScreenTab.kt`](file:///C:/Users/LENOVO/datn-wt/app/android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/tabs/AccountScreenTab.kt): bổ sung nút `Đăng ký` và `Đăng nhập` tại Bước 1 (`1. Tài khoản`), ẩn ký tự mật khẩu bằng `PasswordVisualTransformation()`, và hiển thị email tài khoản đang đăng nhập trong thẻ `Hồ sơ`.

3. **Yêu Cầu Cấp Quyền Micro (`RECORD_AUDIO`) Khi Mở Màn Hình Giọng Nói (`MainScreen.kt`):**
   - Khởi tạo `rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission())` cho `Manifest.permission.RECORD_AUDIO` trong [`MainScreen.kt`](file:///C:/Users/LENOVO/datn-wt/app/android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/MainScreen.kt).
   - Tự động kiểm tra và hiển thị hộp thoại xin quyền ghi âm hệ thống Android (`Allow Smart Home Voice AI to record audio?`) ngay khi người dùng chuyển sang tab `Giọng nói` hoặc bấm nút micro (`Nói lệnh` / `Bắt đầu nói`).

4. **Tối Ưu Bố Cục Không Bị Cắt Khuất Hay Chồng Lấp Trên Màn Hình `1080x2220` (`HomeScreenTab.kt`, `DevicesScreenTab.kt`, `AccountScreenTab.kt`, `MainComponents.kt`):**
   - Tinh chỉnh chiều cao thẻ và khoảng cách dọc trong [`HomeScreenTab.kt`](file:///C:/Users/LENOVO/datn-wt/app/android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/tabs/HomeScreenTab.kt), [`DevicesScreenTab.kt`](file:///C:/Users/LENOVO/datn-wt/app/android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/tabs/DevicesScreenTab.kt), [`AccountScreenTab.kt`](file:///C:/Users/LENOVO/datn-wt/app/android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/tabs/AccountScreenTab.kt) và [`MainComponents.kt`](file:///C:/Users/LENOVO/datn-wt/app/android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/components/MainComponents.kt).
   - Đặt 2 nút hành động chính trên trang chủ (`Nói lệnh` kèm icon micro và `Xem thiết bị`) nằm ngang cùng hàng, hiển thị trọn vẹn 100% trong khung nhìn mà không cần cuộn.
   - Hiển thị trọn vẹn cả 7 công tắc thiết bị cùng thẻ `Lịch` trên tab `Thiết bị`, và toàn bộ mục `Hồ sơ`, `Quản lý`, nút `Đăng xuất` trên tab `Tài khoản`.

---

## 3. Kết Quả Build, Cài Đặt & Kiểm Thử E2E Trên Thiết Bị Thật Qua ADB

### 3.1. Build & Unit Test
- **Unit Test (`app-core:hostTest`):** `lightbuild --plain test app-core:hostTest` -> `BUILD SUCCESS`.
- **Debug APK (`app:app-debug.apk`):** `lightbuild --plain build app:app-debug.apk` -> `BUILD SUCCESS` (`app/build/outputs/apk/debug/app-debug.apk`).
- **Cài đặt qua ADB:** `adb -s 2223e8784b0c7ece install -r app/build/outputs/apk/debug/app-debug.apk` -> `Success`.

### 3.2. Đăng Ký & Đăng Nhập Tài Khoản Thử Nghiệm (`Throwaway Account`)
- **Email thử nghiệm:** `qa.app.1793875502@example.com` (mật khẩu ngẫu nhiên chỉ giữ trong RAM của phiên kiểm thử, tuyệt đối không in ra log hay lưu xuống đĩa; hiển thị trên UI dưới dạng `••••••••••••••••`).
- **Kết quả Đăng ký (`POST /api/auth3/register_or_set_password`):** Thành công, hiển thị thông báo `Đã đăng ký tài khoản: qa.app.1793875502@example.com` (ảnh [`04_auth_registered.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/04_auth_registered.png)).
- **Kết quả Đăng nhập (`POST /api/auth3/layer1_login`):** Thành công, hiển thị thông báo `Đăng nhập thành công: qa.app.1793875502@example.com` (ảnh [`05_auth_logged_in.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/05_auth_logged_in.png)) và cập nhật mục `Hồ sơ -> Email` trên tab `Tài khoản` (ảnh [`06_account_logged_in.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/06_account_logged_in.png)).

### 3.3. Đo Thời Gian Phản Hồi Bật/Tắt 3 Thiết Bị (Tọa Độ Từ `uiautomator dump`)
| STT | Thiết bị (`key`) | Bounds Switch (`uiautomator`) | Tọa độ Tap `(x, y)` | Trạng thái chuyển đổi | Thời gian phản hồi ADB Tap | Thời gian tổng kèm Dump xác nhận UI | Ảnh chụp màn hình |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Đèn phòng khách (`living_room_light`) | `[816,510][972,654]` | `(894, 582)` | `Đang bật` -> `Đang tắt` | **443 ms** | 2598 ms | [`09_device_toggle_1.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/09_device_toggle_1.png) |
| 2 | Đèn phòng ngủ (`bedroom_light`) | `[816,669][972,813]` | `(894, 741)` | `Đang tắt` -> `Đang bật` | **466 ms** | 2526 ms | [`10_device_toggle_2.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/10_device_toggle_2.png) |
| 3 | Điều hòa (`ac`) | `[816,828][972,972]` | `(894, 900)` | `Đang bật · 24°C` -> `Đang tắt` | **482 ms** | 2473 ms | [`11_device_toggle_3.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/11_device_toggle_3.png) |

### 3.4. Kiểm Tra Màn Hình Giọng Nói & Hộp Thoại Quyền Micro
- Khi mở tab `Giọng nói` (`(670, 1974)`), hệ thống Android hiển thị hộp thoại xin quyền chuẩn: `Allow Smart Home Voice AI to record audio?` với hai nút `Allow` (`[72,1704][1008,1812]`) và `Deny` (`[72,1860][1008,1968]`) (ảnh [`12_voice_mic_permission_prompt.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/12_voice_mic_permission_prompt.png)).
- Sau khi chạm `Allow` tại `(540, 1758)`, màn hình `Giọng nói` hiển thị đầy đủ nút micro `Bắt đầu nói`, ô `Nhập lệnh`, nút `Gửi`, công tắc `Đọc phản hồi` và liên kết `Đăng ký giọng nói` không bị cắt khuất (ảnh [`13_voice_screen_ready.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/13_voice_screen_ready.png)).

### 3.5. Kiểm Tra Logcat (`adb logcat -d`)
- **Số lỗi `FATAL EXCEPTION`:** `0`
- **Số lỗi `ANR in vn.edu.hust.seee.smarthome`:** `0`

---

## 4. Danh Mục Ảnh Chụp Màn Hình Thực Tế (`screenshots_app/`)
1. [`01_dashboard_home.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/01_dashboard_home.png) — Trang chủ (`Nhà`) sau khi khởi chạy và đồng bộ Production (`Đã kết nối`, nút micro `Nói lệnh` và `Xem thiết bị` hiển thị rõ).
2. [`02_account_menu.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/02_account_menu.png) — Tab `Tài khoản` trước khi đăng nhập.
3. [`03_auth_form.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/03_auth_form.png) — Màn hình `Xác thực giọng nói` (Bước 1/3: biểu mẫu Email, Mật khẩu, nút `Đăng ký` & `Đăng nhập`).
4. [`04_auth_registered.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/04_auth_registered.png) — Đăng ký thành công tài khoản `qa.app.1793875502@example.com` trên Production (mật khẩu được che kín).
5. [`05_auth_logged_in.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/05_auth_logged_in.png) — Đăng nhập thành công tài khoản `qa.app.1793875502@example.com` trên Production.
6. [`06_account_logged_in.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/06_account_logged_in.png) — Tab `Tài khoản` sau khi đăng nhập hiển thị đúng email `qa.app.1793875502@example.com`.
7. [`07_dashboard_after_login.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/07_dashboard_after_login.png) — Trang chủ (`Nhà`) sau khi đăng nhập.
8. [`08_devices_before.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/08_devices_before.png) — Tab `Thiết bị` hiển thị đầy đủ 7 thiết bị và thẻ `Lịch` trước khi bật/tắt.
9. [`09_device_toggle_1.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/09_device_toggle_1.png) — Sau khi chạm công tắc 1 (`Đèn phòng khách` chuyển sang `Đang tắt`).
10. [`10_device_toggle_2.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/10_device_toggle_2.png) — Sau khi chạm công tắc 2 (`Đèn phòng ngủ` chuyển sang `Đang bật`).
11. [`11_device_toggle_3.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/11_device_toggle_3.png) — Sau khi chạm công tắc 3 (`Điều hòa` chuyển sang `Đang tắt`).
12. [`12_voice_mic_permission_prompt.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/12_voice_mic_permission_prompt.png) — Hộp thoại xin quyền ghi âm hệ thống Android khi mở màn hình `Giọng nói`.
13. [`13_voice_screen_ready.png`](file:///C:/Users/LENOVO/datn-wt/app/screenshots_app/13_voice_screen_ready.png) — Màn hình `Giọng nói` sau khi cấp quyền micro, sẵn sàng nhận lệnh giọng nói.
