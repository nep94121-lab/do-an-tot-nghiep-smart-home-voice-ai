# BÁO CÁO KHẢO SÁT ĐẶC TẢ CHI TIẾT — MOBILE /APP (PHẦN 2 DESIGN_NEW_PAGES.MD) & ANDROID COMPOSE

**Người thực hiện**: spec_miner_mobile_p2  
**Thư mục làm việc**: `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\spec_miner_mobile_p2`  
**Ngày thực hiện**: 2026-11-04  
**Tài liệu đặc tả nguồn**:
- `ORIGINAL_REQUEST.md` (R3: 5 màn mobile Part 2 & Android Scope)
- `ui_mockups/v2_new_pages/DESIGN_NEW_PAGES.md` (Phần 2: M1 – M5)
- Mockups: `ui_mockups/v2_new_pages/np_m1_home_sensors.html` đến `np_m5_qr_scanner.html`
- Source code hiện tại: `mobile_app/index.html`, `simulator/static/js/mobile_app.js`, `simulator/static/css/mobile_app.css`, `simulator/server.py`
- Android source & build: `android_app/` (`app/`, `app-core/`, `.lightbuild/`)
- Test suites: `tests/test_challenger_m4_dom.py`, `tests/test_challenger_m2_gate_ux_empirical.py`, `tests/test_adb_samsung_galaxy_s9.py`

---

## 1. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | M1: Home | Header & Dot Trạng Thái | Hiển thị tiêu đề "Nhà của tôi", chấm tròn trạng thái 7px + chữ "Đã kết nối" / "Mất kết nối", mô tả "Theo dõi trạng thái trong nhà" | WebSocket snapshot hoặc `/api/state` | Header text, `#espBadge` dot xanh/cam | Khi mất kết nối: đổi chữ "Mất kết nối", dot đổi màu vàng cam | `DESIGN_NEW_PAGES.md` §M1, `np_m1_home_sensors.html` |
| 2 | M1: Home | Thẻ Ngôi nhà & Viewport Toàn cảnh | Thẻ hiển thị nhãn "Toàn cảnh", placeholder/viewport mô hình 3D tỉ lệ 16:9, không điều hướng desktop | Click vào viewport | Điều khiển xoay/xem mô hình | Nếu WebGL lỗi hoặc chưa tải: hiển thị fallback placeholder | `DESIGN_NEW_PAGES.md` §M1, `np_m1_home_sensors.html` |
| 3 | M1: Home | Thẻ Cảm biến 2 Ô Grid | Grid 2 cột: Cột 1 Nhiệt độ (`28.5°C`, nhãn "Trong nhà"), Cột 2 Độ ẩm đất (`62%`, nhãn "Sân vườn") | Telemetry từ MQTT (`dht11_telemetry`, `soil_moisture_telemetry`) | `#tempVal`, `#soilVal` hiển thị dạng số lớn nổi bật | Nếu mất dữ liệu/chưa có: hiển thị "Chưa có dữ liệu" hoặc giữ cache kèm nhãn "Cập nhật lần cuối..." | `DESIGN_NEW_PAGES.md` §M1, `np_m1_home_sensors.html` |
| 4 | M1: Home | Thẻ Trạng thái an toàn | Hiển thị trạng thái Cửa chính (Đang khóa / Đang mở) và Còi báo động (Tắt / Bật), ngăn cách bởi đường line divider | Server state (`main_door`, `alarm_siren`) | Chữ trạng thái bold | Chỉ hiển thị dữ liệu server trả về, tuyệt đối không tự client suy đoán | `DESIGN_NEW_PAGES.md` §M1, `np_m1_home_sensors.html` |
| 5 | M1: Home | Cặp nút Thao tác nhanh | Nút primary "Nói lệnh" (kèm icon mic), nút secondary "Xem thiết bị" full-width | Click button | Primary: kích hoạt mic/bottom sheet giọng nói; Secondary: chuyển tab Thiết bị | Mic bị chặn: hiển thị popup quyền mic | `DESIGN_NEW_PAGES.md` §M1, `np_m1_home_sensors.html` |
| 6 | M2: Shell | Hệ thống 4 Tab Độc lập | Shell dùng chung: header ~64px, main `overflow-y:auto`, bottom nav 64px + safe-area. 4 tab: "Nhà", "Thiết bị", "Giọng nói", "Tài khoản". Chọn tab thay toàn bộ nội dung main, KHÔNG scroll | Click tab icon ở bottom nav | Chuyển đổi nội dung `main` sang view tab tương ứng, cập nhật active tab | Giữ scroll position độc lập từng tab nếu có thể | `DESIGN_NEW_PAGES.md` §M2, `np_m2_tabs_account.html` |
| 7 | M2: Account | Hồ sơ Tài khoản & Quyền | Thẻ Hồ sơ hiển thị: Vai trò (Chủ nhà / Gia đình / Khách), Email đã che (vd: `t***@gmail.com`), Thời hạn truy cập ("Không giới hạn" với Chủ nhà, "Còn..." với Khách) | Session user / `/api/auth3/overview` | Dòng thông tin hồ sơ | Thiếu email: ẩn dòng email; chưa có thời hạn: "Chưa có thông tin thời hạn" | `DESIGN_NEW_PAGES.md` §M2, `np_m2_tabs_account.html` |
| 8 | M2: Account | Menu Quản lý & Đăng xuất | Thẻ Quản lý với các hàng link có chevron: "Xác thực ›", "Lời mời ›", "Cài đặt ›" và nút "Đăng xuất" secondary tách riêng ở cuối | Click row hoặc nút Đăng xuất | Mở chi tiết chức năng; Đăng xuất: xóa session và quay về Login Gate | Thất bại logout: báo lỗi, giữ phiên an toàn | `DESIGN_NEW_PAGES.md` §M2, `np_m2_tabs_account.html` |
| 9 | M3: Forgot | Quên mật khẩu Gmail OTP (Bước 1-3) | Luồng 3 bước: B1 Email -> B2 Nhập mã OTP 6 số từ Gmail -> B3 Mật khẩu mới & xác nhận lại. Header có nút quay lại (`arrow-left`), chỉ số tiến trình "Bước 2/3" | Email, OTP 6 số, Mật khẩu mới + Xác nhận | OTP input với `inputmode="numeric"`, `autocomplete="one-time-code"`, `maxlength="6"` | Mã sai/hết hạn: thông báo lỗi ngay dưới ô nhập; hỗ trợ đếm ngược gửi lại mã | `DESIGN_NEW_PAGES.md` §M3, `np_m3_forgot_otp.html` |
| 10 | M4: Voice | Bottom Sheet Thu âm Giọng nói | Bottom sheet trượt từ đáy (chiếm 50-65% màn hình), bo góc 20px, overlay scrim mờ tab Giọng nói phía sau. Có nút đóng `x`, vòng sóng tròn `wavecircle`, thanh 12 bars âm lượng CSS, bộ đếm thời gian `00:03 / 00:05` | Giọng nói micro qua AudioContext/Stream | Animation sóng, đếm giây, hiển thị câu đọc mẫu "Mở cửa chính cho tôi." | Đạt: "Đạt — đã xác thực · Chủ nhà"; Chưa đạt: "Chưa đạt — âm thanh quá ngắn / Nhiều tiếng ồn / Chưa khớp" (không lộ confidence số) | `DESIGN_NEW_PAGES.md` §M4, `np_m4_voice_sheet.html` |
| 11 | M4: Voice | Trạng thái Nút bấm Bottom Sheet | Đang thu: nút primary "Dừng thu", secondary "Hủy"; Đạt: primary "Tiếp tục"; Chưa đạt: primary "Thu lại", secondary "Đóng" | Click thao tác người dùng | Chuyển đổi trạng thái thu âm, gửi audio hoặc đóng sheet | Micro bị khóa/lỗi: kích hoạt popup xin quyền micro | `DESIGN_NEW_PAGES.md` §M4, `np_m4_voice_sheet.html` |
| 12 | M5: QR | Camera Quét Mã QR Lời Mời | Màn hình riêng trong `/app`, header có nút đóng/quay lại, viewport camera tối góc bo 16px, khung ngắm 215x215px với 4 góc kẻ line (`.tl`, `.tr`, `.bl`, `.br`) | Luồng camera sau (`facingMode: "environment"`) | Khung camera live hoặc placeholder nền tối | Chưa cấp quyền: nút primary "Bật camera"; đã bật: nút secondary "Nhập mã"; không dùng camera trước | `DESIGN_NEW_PAGES.md` §M5, `np_m5_qr_scanner.html` |
| 13 | M5: QR | Xử lý Mã QR & Handshake | Quét mã thành công hiển thị "Đang kiểm tra mã...", gọi API kiểm tra handshake và chuyển luồng đăng nhập Khách | Dữ liệu QR token | Chuyển trang hoặc kích hoạt quyền Khách | Mã hết hạn/đã dùng: chuyển hướng trang báo lỗi QR expired (`np_04_qr_expired.html`); lỗi mờ: báo "Di chuyển gần hơn hoặc tăng ánh sáng" | `DESIGN_NEW_PAGES.md` §M5, `np_m5_qr_scanner.html` |
| 14 | Architecture | Phục vụ Web Mobile (`/app`) | FastAPI endpoint `@app.get("/app")` trả về `mobile_app/index.html`, nạp tài nguyên tĩnh qua `/static/css/mobile_app.css` và `/static/js/mobile_app.js` | Request HTTP GET `/app` | FileResponse HTML | Tự động gắn header chống cache (`no-cache, no-store`) | `simulator/server.py` |
| 15 | Android | Phân tích Ứng dụng Android Compose | Thư mục `android_app/` gồm `app/` và `app-core/`, cấu hình hệ thống Lightbuild CLI 0.0.30 (`project.lightbuild.yaml`). `MainScreen.kt` có 2570 dòng Compose | Build qua `lightbuild` hoặc `gradlew.bat` | APK debug | Hiện tại `./gradlew assembleDebug` thất bại vì Windows thiếu biến `JAVA_HOME`; `lightbuild build //app` thất bại vì đường dẫn chứa ký tự tiếng Việt có dấu (`đồ án tốt nghiệp`) | `android_app/`, `MainScreen.kt` |
| 16 | DOM Hooks | Tương thích ngược DOM & Test Hooks | Bảo toàn 100% 68 DOM IDs và 37 inline event handlers để các bài test E2E, Challenger DOM, UX Gate và kịch bản ADB Samsung Galaxy S9 không bị gãy | DOM events & queries từ pytest/ADB | Trả về phần tử hợp lệ | Thiếu ID hoặc dereference null gây rớt test ngay lập tức | `tests/test_challenger_m4_dom.py`, `tests/test_adb_samsung_galaxy_s9.py` |

---

## 2. Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | M1: Cảm biến | Mất kết nối telemetry hoặc sensor chưa trả giá trị | Hiển thị "Chưa có dữ liệu" hoặc giữ nguyên số đo cuối cùng kèm nhãn "Cập nhật lần cuối...". Tuyệt đối không hiển thị ô độ ẩm không khí thứ 3 ở màn Home M1 (chỉ 2 ô Nhiệt độ & Độ ẩm đất). |
| 2 | M1: 3D Toàn cảnh | WebGL không khả dụng hoặc thiết bị di động yếu | Giữ nguyên thẻ "Toàn cảnh" với placeholder tỷ lệ 16:9, không bị xóa thẻ nhãn hoặc điều hướng ép về Desktop. |
| 3 | M2: Đổi tab | Người dùng bấm tab khác nhau hoặc cuộn dài | Màn hình thay đổi nội dung `main` độc lập, không cuộn dọc (scroll) tới section của trang khác. Vị trí cuộn của từng tab được lưu độc lập. |
| 4 | M2: Bàn phím ảo | Mở bàn phím ảo trên mobile khi nhập form | Shell dùng `min-height: 100dvh` (fallback `100vh`) và `viewport-fit=cover`. Form cuộn được bên trong `main`, không để thanh tab hoặc bàn phím che khuất nút hành động (CTA). |
| 5 | M3: OTP Gmail | Nhập OTP sai hoặc hết hạn 60s | Thông báo lỗi màu đỏ xuất hiện ngay bên dưới ô nhập OTP. Nút "Gửi lại mã" hiển thị bộ đếm lùi thời gian thực trước khi cho phép gửi lại. Hỗ trợ dán (paste) 6 chữ số và `autocomplete="one-time-code"`. |
| 6 | M4: Thu âm giọng nói | Người dùng giữ im lặng hoặc thu âm quá ngắn (< 1.5s) | Kết quả trả về `CHUA_DAT`: "Chưa đạt — âm thanh quá ngắn" hoặc "Nhiều tiếng ồn". Nút bấm đổi thành "Thu lại" (primary) và "Đóng" (secondary). Không bao giờ hiển thị chỉ số F0, SNR hay confidence thô cho người dùng cuối. |
| 7 | M4: Thu âm giọng nói | Micro bị từ chối cấp quyền | Kích hoạt modal/popup quyền micro (`np_07_mic_permission.html`), dừng tiến trình ghi âm. |
| 8 | M5: Quét QR | Mã QR bị lóa sáng hoặc camera không lấy nét | Thông báo hướng dẫn: "Di chuyển gần hơn hoặc tăng ánh sáng". Khi người dùng rời màn hình hoặc ẩn ứng dụng, camera track phải được giải phóng (`track.stop()`) ngay lập tức để tiết kiệm pin. |
| 9 | M5: Quét QR | Mã QR đã được sử dụng 1 lần hoặc hết hạn TOTP 10s | Điều hướng người dùng sang trang thông báo lỗi QR hết hạn (`np_04_qr_expired.html`), không hiển thị token hoặc thông tin bí mật lên giao diện. |
| 10 | Tương thích ADB | Kịch bản kiểm thử tự động ADB chạm vào tọa độ nút Đăng nhập / Tab Tài khoản | Cấu trúc vị trí thẻ và nút bấm phải ổn định, không làm thay đổi các nút mấu chốt: Form login `#mobileLoginForm`, nút submit `#mobileLoginBtn`, nút chuyển tab, và thẻ `#mobileDynamicQrCard`. |

---

## 3. Khảo sát Chi tiết 5 Màn hình Mobile (Part 2 DESIGN_NEW_PAGES.md)

### 3.1. Màn M1: Nhà và cảm biến (`np_m1_home_sensors.html`)
- **Tiêu đề trang**: `Nhà và cảm biến · Nhà thông minh`
- **Header Shell**:
  - Dòng 1: H1 "Nhà của tôi" + Pill bo tròn hiển thị dot xanh 7px + "Đã kết nối" (hoặc dot cam + "Mất kết nối").
  - Dòng 2: Subtitle phụ màu muted `Theo dõi trạng thái trong nhà`.
- **Thẻ 1 — Ngôi nhà**:
  - Tiêu đề H2 "Ngôi nhà" + Pill góc phải "Toàn cảnh".
  - Vùng Viewport: Khung tỷ lệ 16:9 (`placeholder` bo góc 12px, viền nét đứt `#b9ccce`, nền `#f4f9f9`), nhúng trực tiếp hoặc làm cổng gắn Viewport 3D Toàn cảnh hiện hữu.
  - Khác biệt so với hiện tại: Hiện tại `mobile_app/index.html` dùng thẻ `<a href="/" class="overview-box">` click nhảy về trang web Desktop! Mockup yêu cầu thẻ Toàn cảnh xem ngay trên Mobile shell, không redirect ra ngoài.
- **Thẻ 2 — Cảm biến**:
  - Tiêu đề H2 "Cảm biến".
  - Grid 2 cột:
    - Cột 1: `Nhiệt độ` -> Giá trị lớn **28.5°C**, phụ đề "Trong nhà".
    - Cột 2: `Độ ẩm đất` -> Giá trị lớn **62%**, phụ đề "Sân vườn".
  - Ghi chú cốt lõi từ đặc tả: Không hiển thị ô độ ẩm không khí thứ 3 ở màn Home M1 vì bản v1 Home chỉ chốt 2 cảm biến vật lý trên mạch (Nhiệt độ phòng và Độ ẩm đất sân vườn).
- **Thẻ 3 — Trạng thái an toàn**:
  - Tiêu đề H2 "Trạng thái an toàn".
  - Hàng 1: "Cửa chính" — **Đang khóa** (hoặc **Đang mở**).
  - Đường line phân cách `hr.divider`.
  - Hàng 2: "Còi báo động" — **Tắt** (hoặc **Bật**).
- **Cụm nút Hành động (Actions)**:
  - Nút Primary full-width: Icon SVG Mic + chữ "Nói lệnh".
  - Nút Secondary full-width: "Xem thiết bị" (dẫn sang tab Thiết bị).
- **Thanh Bottom Navigation**:
  - 4 nút: `Nhà` (active), `Thiết bị`, `Giọng nói`, `Tài khoản`.

---

### 3.2. Màn M2: Bốn tab độc lập và Tài khoản (`np_m2_tabs_account.html`)
- **Kiến trúc Shell chung**:
  - Header cao khoảng 64px, cố định.
  - Vùng `main` chiếm toàn bộ chiều cao còn lại, `overflow-y: auto`.
  - Bottom nav cao 64px + `env(safe-area-inset-bottom)`.
  - **Quy tắc chuyển Tab bắt buộc**: Bấm tab thay đổi hoàn toàn nội dung hiển thị trong thẻ `main`, **KHÔNG dùng cuộn trang `scrollIntoView`** như phiên bản cũ!
- **Nội dung Tab 4 — Tài khoản (Account View)**:
  - Header: H1 "Tài khoản" + Pill "Đã kết nối", phụ đề "Hồ sơ và quyền truy cập".
  - **Thẻ 1 — Hồ sơ**:
    - Hàng 1: Vai trò — **Chủ nhà** (Cấp 1) / **Gia đình** (Cấp 2) / **Khách** (Cấp 3).
    - Phân cách `hr.divider`.
    - Hàng 2: Email — **t***@gmail.com** (email đã che từ phiên đăng nhập thực).
    - Phân cách `hr.divider`.
    - Hàng 3: Thời hạn — **Không giới hạn** (Chủ nhà) hoặc **Còn X ngày/giờ** (Khách).
  - **Thẻ 2 — Quản lý**:
    - Hàng link 1: "Xác thực" kèm ký tự `›`.
    - Phân cách `hr.divider`.
    - Hàng link 2: "Lời mời" kèm ký tự `›`.
    - Phân cách `hr.divider`.
    - Hàng link 3: "Cài đặt" kèm ký tự `›`.
  - Chú thích: "Mỗi tab mở một màn riêng, không cuộn tới mục khác."
  - **Nút Đăng xuất**: Nút secondary full-width tách biệt ở cuối nội dung. Bấm vào thực hiện xóa session và đưa người dùng về `#mobileLoginGate`.

---

### 3.3. Màn M3: Quên mật khẩu Gmail OTP (`np_m3_forgot_otp.html`)
- **Bố cục & Định vị**:
  - Màn hình form độc lập trước khi đăng nhập, header có nút quay lại (icon `arrow-left`), chỉ báo bước: `Bước 2/3`.
  - H1: "Quên mật khẩu", mô tả: `Nhập mã 6 số đã gửi tới Gmail của bạn.`
- **Thẻ Form Nhập**:
  - Dòng thông tin email đã gửi: `Đã gửi tới t***@gmail.com`
  - Nhãn: `Mã xác nhận` gắn với `<input id="otp">`.
  - Thuộc tính ô nhập: `class="field"`, `inputmode="numeric"`, `autocomplete="one-time-code"`, `maxlength="6"`, `pattern="[0-9]{6}"`, `placeholder="Nhập 6 chữ số"`.
  - Phụ đề trợ giúp: `Mã có hiệu lực theo thời hạn hệ thống.`
  - Cụm nút:
    - Primary wide: "Xác nhận mã"
    - Secondary wide: "Gửi lại mã" (kèm countdown)
    - Tertiary wide: "Đổi email"
- **Xử lý lỗi**: Thông báo lỗi sai mã / hết hạn xuất hiện trực tiếp ngay dưới ô nhập, focus trở lại ô nhập.
- **Tích hợp API Backend**:
  - Gửi mã: `POST /api/auth3/forgot_password_send_otp` (`{ email, send_gmail }`)
  - Xác nhận & đặt lại: `POST /api/auth3/forgot_password_reset` (`{ email, otp, new_password, confirm_password }`)

---

### 3.4. Màn M4: Bottom Sheet Giọng nói (`np_m4_voice_sheet.html`)
- **Cấu trúc Giao diện**:
  - Nền sau: Tab Giọng nói bị làm mờ nhẹ (`filter: blur(1px)`).
  - Lớp phủ: `.scrim` nền tối bán trong suốt (`#0f22267a`).
  - Hộp thoại đáy: `.sheet` bo tròn góc trên 20px, kéo lên từ đáy chiếm khoảng 50–65% màn hình, hỗ trợ thanh kéo `.handle`.
  - Tiêu đề: H2 "Đang thu âm" + nút đóng tertiary có icon `x` (`aria-label="Đóng"`).
  - Chỉ báo âm lượng:
    - Vòng sóng trung tâm: `.wavecircle` (chứa icon mic).
    - Dải sóng âm: `.bars` gồm 12 vạch `<i>` chiều cao co giãn mô phỏng mức âm lượng thời gian thực.
  - Bộ đếm thời gian: `.timer` hiển thị `00:03 <span>/ 00:05</span>`.
  - Nhãn chỉ dẫn: `Đọc câu mẫu để xác nhận giọng nói`.
  - Khung câu đọc mẫu: `.phrase` hiển thị câu mẫu (ví dụ: *"Mở cửa chính cho tôi."* hoặc câu lưu giọng từ server).
  - Cụm nút bấm tương ứng trạng thái:
    - Trạng thái đang thu: Nút primary "Dừng thu" + nút secondary "Hủy".
    - Trạng thái đạt: Nút primary "Tiếp tục".
    - Trạng thái chưa đạt: Nút primary "Thu lại" + nút secondary "Đóng".
  - Dòng kết quả `.result`:
    - Đạt: `✓ Đạt — đã xác thực · Chủ nhà` (xanh lá).
    - Chưa đạt: `✗ Chưa đạt — âm thanh quá ngắn · Thu lại` (đỏ). Tuyệt đối không để lộ điểm số hay phần trăm confidence.

---

### 3.5. Màn M5: Camera Quét QR (`np_m5_qr_scanner.html`)
- **Bố cục & Vùng quét**:
  - Tiêu đề header: H1 "Quét mã QR" + nút đóng `x`, phụ đề `Quét lời mời từ Chủ nhà`.
  - Khung ngắm Camera: `.camera` nền tối bo góc 16px.
  - Khung line 4 góc: `.scanframe` 215x215px gồm 4 góc kẻ viền `.tl`, `.tr`, `.bl`, `.br` nổi bật trên nền camera.
  - Lời chỉ dẫn: `Đưa mã QR vào trong khung để quét`, phụ đề `Quét mã đang hiển thị trên màn hình Chủ nhà.`
  - Nút bấm:
    - Khi chưa cấp quyền: Nút primary "Bật camera".
    - Khi camera đang mở: Nút secondary "Nhập mã" (nếu có luồng nhập mã thủ công).
  - Phản hồi trạng thái: `Khi quét được mã: Đang kiểm tra mã…`
  - Quản lý thiết bị:
    - Bắt buộc dùng camera sau (`facingMode: "environment"`).
    - Giải phóng camera stream (`track.stop()`) ngay khi đóng hoặc chuyển tab.
    - Không lưu ảnh hoặc token vào UI/localStorage/log.
    - Token hợp lệ -> gọi handshake / chuyển sang `/guest_enroll?token=...`. Token hết hạn -> chuyển trang 404/expired (`np_04_qr_expired.html`).

---

## 4. Khảo sát Mã Nguồn Android Compose & Đánh giá `./gradlew assembleDebug`

### 4.1. Cấu trúc Thư mục Android
Mã nguồn ứng dụng Android nằm trong thư mục `android_app/`:
```
android_app/
├── .lightbuild/
│   └── gradle/               # Dự án Gradle do Lightbuild sinh ra
│       ├── gradlew
│       ├── gradlew.bat       # Wrapper Gradle
│       ├── build.gradle
│       ├── gradle.properties
│       └── local.properties  # Trỏ sdk.dir tới C:\Users\LENOVO\AppData\Local\Android\Sdk
├── app/
│   └── lightbuild.yaml       # Định nghĩa ứng dụng com.android.application (apiLevel 36, minSdk 26)
├── app-core/
│   ├── lightbuild.yaml
│   └── src/main/kotlin/vn/edu/hust/seee/smarthome/
│       ├── MainActivity.kt   # ComponentActivity nhúng Jetpack Compose
│       ├── Navigation.kt     # Jetpack Navigation3
│       └── ui/main/MainScreen.kt  # Màn hình Compose nguyên khối 2570 dòng code!
├── project.lightbuild.yaml   # Cấu hình gốc Lightbuild (version: 0.0.30, kotlin: 2.3.20, java: 17)
└── gradle.properties         # Chứa android.overridePathCheck=true
```

### 4.2. Khảo sát Tính Khả Thi của Lệnh Build (`./gradlew assembleDebug` & `lightbuild`)
Đã thực hiện kiểm chứng thực tế bằng lệnh trên máy trạm:
1. **Kiểm tra file thực thi `gradlew.bat`**:
   - Ở thư mục gốc dự án và `android_app/`: **KHÔNG có file `gradlew.bat` trực tiếp**.
   - `gradlew.bat` chỉ tồn tại bên trong thư mục con `android_app\.lightbuild\gradle\gradlew.bat`.
2. **Kiểm tra thực thi `gradlew.bat assembleDebug` trực tiếp**:
   - Kết quả: **THẤT BẠI (Exit Code 1)**.
   - Nguyên nhân chính xác: `ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.` Máy trạm chưa cấu hình biến môi trường `JAVA_HOME` toàn cục trong PowerShell/CMD.
3. **Kiểm tra thực thi qua công cụ quản lý chính thức `lightbuild build //app`**:
   - Lightbuild CLI phiên bản `0.0.1` đã cài đặt và nhận diện dự án.
   - Quá trình chạy: Khởi tạo tiến trình nested build và tải/phân giải dependency lên đến 100%.
   - Kết quả cuối cùng: **THẤT BẠI (Exit Code 1)** với thông báo lỗi cụ thể từ Android Gradle Plugin:
     ```
     An exception occurred applying plugin request [id: 'com.android.application']
     > Failed to apply plugin 'com.android.internal.application'.
        > Your project path contains non-ASCII characters. This will most likely cause the build to fail on Windows.
          Please move your project to a different directory.
     ```
   - Thư mục làm việc `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp` chứa ký tự có dấu (`đồ án tốt nghiệp`), làm Android Gradle Plugin trên Windows từ chối biên dịch trừ khi có `android.overridePathCheck=true`. Mặc dù file `android_app/gradle.properties` đã có dòng này, nhưng file sinh tự động `android_app/.lightbuild/gradle/gradle.properties` lại bị ghi đè thiếu cấu hình này.

### 4.3. Kết luận về Phạm vi Android (Android Scope)
1. Theo chỉ thị tại **Requirement R3** (`ORIGINAL_REQUEST.md`):
   > *"Ưu tiên hoàn thiện toàn bộ trên Web và Mobile Web (`mobile_app/` / `/app`); chỉ chỉnh sửa Android Compose nếu có phần liên quan trực tiếp và đảm bảo assembleDebug PASS nếu đụng tới."*
2. **Khuyến nghị đặc tả tuyệt đối**:
   - **Mục tiêu ưu tiên số 1**: Hoàn thiện toàn bộ 5 màn hình M1 – M5 trên giao diện Mobile Web (`mobile_app/index.html`, `simulator/static/js/mobile_app.js`, `simulator/static/css/mobile_app.css`), phục vụ trực tiếp cho trình duyệt điện thoại Samsung Galaxy S9 qua đường dẫn `http://localhost:8088/app`.
   - **Tuyệt đối KHÔNG can thiệp vào mã nguồn Android Compose (`MainScreen.kt`)** trong Phase 2 để tránh làm gãy điều kiện `assembleDebug PASS`, bởi vì môi trường hiện tại đang bị lỗi non-ASCII path check và thiếu biến môi trường Java. Mọi tính năng kiểm thử của người dùng trên điện thoại (đăng nhập, quét QR, điều khiển thiết bị) đều đang chạy trên trình duyệt di động truy cập `/app`.

---

## 5. Khảo sát Tương thích Ngược DOM IDs, Inline Event Handlers & Hooks

### 5.1. Danh mục 68 DOM IDs Bắt buộc Bảo toàn trong `mobile_app/index.html`
Các ID sau được truy vấn trực tiếp trong `simulator/static/js/mobile_app.js` và được kiểm định nghiêm ngặt bởi `tests/test_challenger_m4_dom.py`:

```
1.  aiReply                    24. mobileLoginBtn             47. mobileTargetEmail
2.  btnLearnIr                 25. mobileLoginEmail           48. mobileTargetTierSelect
3.  btnMobileMicLabel          26. mobileLoginForm            49. mobileVoiceF0
4.  btnMobileTabLogin          27. mobileLoginGate            50. mobileVoiceMetrics
5.  btnMobileTabRegister       28. mobileLoginMsg             51. mobileVoiceRegName
6.  btnTestDrySoil             29. mobileLoginPassword        52. mobileVoiceRes
7.  btnToggleShowAllDevices    30. mobileMainContent          53. mobileVoiceRetryBtn
8.  cmdForm                    31. mobileQrCountdown          54. mobileVoiceSNR
9.  cmdInput                   32. mobileQrDots               55. mobileVoiceStepLabel
10. devGrid                    33. mobileQrInviteTierSelect   56. mobileVoiceTierInfo
11. espBadge                   34. mobileQrOpenLink           57. mqttLog
12. humVal                     35. mobileQrSvgContainer       58. pwaSchedAction
13. mobileActorBadge           36. mobileQrTokenText          59. pwaSchedDevice
14. mobileActorSelect          37. mobileQrUrlText            60. pwaSchedTime
15. mobileAddEmailForm         38. mobileRegConfirmPassword   61. pwaScheduleForm
16. mobileAllowlistMsg         39. mobileRegEmail             62. pwaVoiceEmpty
17. mobileBottomNav            40. mobileRegMsg               63. pwaVoiceResults
18. mobileChangeConfirmPassword 41. mobileRegName             64. soilVal
19. mobileChangeEmail          42. mobileRegPassword          65. tempVal
20. mobileChangeNewPassword    43. mobileRegTier              66. upcomingScheduleInline
21. mobileChangePasswordBtn    44. mobileRegisterBtn          67. userSaidText
22. mobileChangePasswordMsg    45. mobileRegisterForm         68. voiceStateBadge
23. mobileGuestDurSelect       46. mobileStrikeBadge
```

### 5.2. Danh mục 25 `window.*` Hooks Export Toàn cục trong `mobile_app.js`
Được export lên đối tượng `window` để phục vụ các inline handlers và kiểm thử:
1. `window.addLog`
2. `window.copyMobileGuestLink`
3. `window.executeMobileCommand`
4. `window.fetchInitial`
5. `window.filterDevicesByRoom`
6. `window.filterMobileHistory`
7. `window.onMobileActorChange`
8. `window.onMobileQrInviteTierChange`
9. `window.onMobileRegTierChange`
10. `window.pollMobileSecurityAndTimers`
11. `window.refreshMobileQr10s`
12. `window.renderMobileHistory`
13. `window.renderState`
14. `window.scrollToSection`
15. `window.showPwaVoiceResults`
16. `window.submitMobileAddEmail`
17. `window.submitMobileChangePassword`
18. `window.submitMobileLogin`
19. `window.submitMobileRegister`
20. `window.submitMobileVoiceSample`
21. `window.submitPwaSchedule`
22. `window.switchMobileLoginTab`
23. `window.toggleMobileVoiceListen`
24. `window.togglePasswordVisibility`
25. `window.toggleShowAllDevices`

### 5.3. Ràng buộc Nghiêm ngặt từ các Test Suite (Tránh Hồi Quy)
1. **Kiểm thử Form & Submit (`test_challenger_m2_gate_ux_empirical.py`)**:
   - Ba form `#mobileLoginForm`, `#mobileRegisterForm`, `#mobileChangePasswordForm` bắt buộc phải là thẻ `<form>` có thuộc tính `onsubmit` và nút con có `type="submit"`.
   - Tất cả 5 ô mật khẩu: `#mobileLoginPassword`, `#mobileRegPassword`, `#mobileRegConfirmPassword`, `#mobileChangeNewPassword`, `#mobileChangeConfirmPassword` bắt buộc phải có nút `.btn-toggle-pw` bên cạnh chứa icon `👁️` gọi hàm `togglePasswordVisibility`.
   - Trong `mobile_app.js`, bắt buộc có kiểm tra đối soát mật khẩu không khớp: `password !== confirmPassword` và `pw1 !== pw2`.
2. **Kiểm thử SVG Sprite Scope (`test_challenger_m2_gate_ux_empirical.py`)**:
   - Khối `<svg>` sprite chứa các `<symbol id="i-home">...` bắt buộc phải nằm trực tiếp dưới `<body>`, **bên ngoài** `<div id="mobileMainContent" hidden>` để icon trên `#mobileLoginGate` luôn hiển thị được ngay cả khi chưa đăng nhập.
3. **Kịch bản ADB Samsung Galaxy S9 (`test_adb_samsung_galaxy_s9.py`)**:
   - Bước 1: Mở `http://localhost:8088/app`, nhận diện `#mobileLoginGate`.
   - Bước 2: Bấm Đăng nhập vào `#mobileMainContent`.
   - Bước 3: Thao tác điều khiển trên `#devGrid`.
   - Bước 4: Chuyển sang Tab Tài khoản (`#secAuth`) và mở thẻ `#mobileDynamicQrCard`.

---

## 6. Kế hoạch Hiện thực hóa Kiến trúc Mobile Part 2 (Gợi ý cho Đội Implement)

1. **Chuyển đổi Kiến trúc từ Cuộn Trang (Single Scroll) sang Tab Độc lập (Tab View Switcher)**:
   - Thay vì cuộn trang bằng `scrollIntoView`, tạo hàm `switchMobileTab(tabKey)` hiển thị view của tab được chọn (`home`, `devices`, `voice`, `account`) và ẩn các view còn lại.
   - Để giữ nguyên tương thích ngược với các test cũ gọi `scrollToSection(id)`, hàm `scrollToSection` sẽ ánh xạ:
     - `secHome` $\rightarrow$ gọi `switchMobileTab('home')`
     - `secDevices` $\rightarrow$ gọi `switchMobileTab('devices')`
     - `secVoice` $\rightarrow$ gọi `switchMobileTab('voice')`
     - `secAuth` $\rightarrow$ gọi `switchMobileTab('account')`
     Đồng thời giữ nguyên các phần tử có `id="secHome"`, `id="secDevices"`, `id="secVoice"`, `id="secAuth"` trong cây DOM.
2. **Tích hợp M1 (Nhà và Cảm biến)**:
   - Thêm thẻ hiển thị mô hình Toàn cảnh (preview placeholder).
   - Thêm thẻ 2 ô Grid Cảm biến hiển thị Nhiệt độ & Độ ẩm đất trực quan, đồng bộ với `#tempVal` và `#soilVal`.
   - Thêm thẻ Trạng thái an toàn (Cửa chính & Còi báo động) đồng bộ từ snapshot thiết bị.
3. **Tích hợp M3 (Quên mật khẩu Gmail OTP)**:
   - Bổ sung nút "Quên mật khẩu?" trên `#mobileLoginForm`.
   - Bổ sung panel M3 Quên mật khẩu 3 bước, tích hợp với API `/api/auth3/forgot_password_send_otp` và `/api/auth3/forgot_password_reset`.
4. **Tích hợp M4 (Bottom Sheet Giọng nói)**:
   - Xây dựng overlay `.scrim` và bottom sheet `.sheet` theo mockup `np_m4_voice_sheet.html`.
   - Khi bấm "Nói lệnh" ở tab Home hoặc "Bắt đầu nói" ở tab Giọng nói, mở bottom sheet, hiển thị animation dải sóng 12 bars và timer `00:03 / 00:05`.
5. **Tích hợp M5 (Camera Quét QR)**:
   - Bổ sung modal / màn hình quét QR theo mockup `np_m5_qr_scanner.html`.
   - Tích hợp HTML5 getUserMedia với camera sau, khung ngắm góc line 4 góc.
   - Khi quét hoặc nhập token, gọi API `/api/auth3/guest_qr_handshake` hoặc điều hướng `/guest_enroll`.
