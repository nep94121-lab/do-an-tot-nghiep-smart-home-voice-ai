# Hướng Dẫn Sử Dụng — Smart Home Voice AI (`v3.8.0` / `v1.0`)

Tài liệu hướng dẫn sử dụng đầy đủ cho người dùng cuối bằng **tiếng Việt** trên Web Dashboard, Mobile Web, Ứng dụng Android và trang hướng dẫn phần cứng `/wokwi`.

> **Nguyên tắc ngôn ngữ & phạm vi phần cứng:** Hệ thống chỉ tiếp nhận và phản hồi bằng **tiếng Việt** (giọng đọc `Aoede`). Hệ thống điều khiển đúng **6 thiết bị chấp hành** (`Cửa chính`, `Đèn phòng khách`, `Đèn phòng ngủ`, `Bơm tưới cây`, `Còi báo động`, `Loa phản hồi PAM8403`) và đọc **3 cảm biến** (`Nhiệt độ & Độ ẩm DHT11`, `Độ ẩm đất LM393/YL-69`, `Cảm biến âm thanh KY-037`).
> **Cắm phần cứng ESP8266 lần đầu?** Xem ngay hướng dẫn 1 lệnh nạp USB & nhập Wi-Fi runtime tại [`docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md`](docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md).

---

## 1. Hệ thống Tài khoản & Phân quyền 3 Cấp (RBAC)

Mọi yêu cầu điều khiển thiết bị, tự động hóa và truy cập trang quản trị đều được máy chủ kiểm tra phiên đăng nhập (cookie `HttpOnly` hoặc tiêu đề `X-Session-Token`).

| Cấp quyền | Vai trò | Thiết bị được phép điều khiển | Quyền truy cập trang & chức năng |
| :---: | :--- | :--- | :--- |
| **Cấp 1** | **Chủ nhà** (`ADMIN`) | Cả **6/6 thiết bị**: Cửa chính, Còi báo động, Bơm tưới cây, Loa PAM8403, Đèn phòng khách, Đèn phòng ngủ | Toàn quyền: Tổng quan (`/`), Tự động hóa (`/automation`), Xác thực & quản trị thành viên/mã mời QR (`/auth`), Phần cứng (`/wokwi`), Nhật ký hệ thống (`/logs`), Reset hệ thống |
| **Cấp 2** | **Thành viên gia đình** (`MEMBER`) | **4/6 thiết bị**: Đèn phòng khách, Đèn phòng ngủ, Bơm tưới cây, Loa PAM8403 *(không điều khiển Cửa chính & Còi báo động)* | Xem và dùng `/`, tạo/quản lý tự động hóa cá nhân trên `/automation`, xem `/wokwi`, xem thông tin phiên trên `/auth`. **Không** truy cập `/logs` và **không** tạo mã mời QR |
| **Cấp 3** | **Khách** (`CHILD_GUEST`) | **2/6 thiết bị**: Đèn phòng khách, Đèn phòng ngủ | Điều khiển 2 đèn trên `/` hoặc `/app`, **chỉ xem** trên `/automation` (ẩn nút tạo/sửa/xóa). **Bị chặn (HTTP 403)** khi truy cập `/wokwi` và `/logs` |

### Đăng nhập & Khôi phục mật khẩu
1. Truy cập `/login` (hoặc mở ứng dụng Android — màn hình đăng nhập sẽ hiển thị bắt buộc khi chưa có phiên hợp lệ).
2. Nhập email và mật khẩu để hoàn tất bước 1, sau đó nhập **mã OTP 6 chữ số** gửi qua Gmail để kích hoạt phiên.
3. Nếu quên mật khẩu, mở mục **Quên mật khẩu · Đặt lại qua OTP Gmail** tại `/auth` hoặc trên ứng dụng Android để nhận mã OTP và đặt mật khẩu mới.

---

## 2. Mời Thành viên & Khách bằng Link / Mã QR Dùng Một Lần

Chỉ **Chủ nhà (Cấp 1)** mới có quyền tạo và thu hồi mã mời:

1. **Phê duyệt email trước (tùy chọn):** Mở trang `/auth`, chọn vai trò (`Gia đình - Cấp 2` hoặc `Khách - Cấp 3`), nhập email vào danh sách cho phép (`allowlist`).
2. **Tạo mã mời QR / đường dẫn mời:**
   - Mở khung **Mã QR mời Khách & Gia đình** ngay trên trang Tổng quan (`/`).
   - Chọn cấp quyền (`Cấp 2` hoặc `Cấp 3`), thời hạn hiệu lực và xác nhận mã PIN Chủ nhà.
   - Hệ thống sinh **mã QR và liên kết mời dùng một lần** (sau khi kích hoạt trên thiết bị đầu tiên, liên kết/QR sẽ tự hết hiệu lực).
3. **Kích hoạt lời mời phía người nhận:**
   - **Trên trình duyệt:** Quét mã QR hoặc mở liên kết mời -> hệ thống gọi `POST /api/guest/redeem` (hoặc dẫn qua `/guest_guide`) để cấp phiên tức thì (đối với Khách Cấp 3) hoặc hoàn tất đăng ký tài khoản Thành viên Cấp 2.
   - **Trên ứng dụng Android:** Nhấn nút **Quét mã QR** tại màn hình đăng nhập/tài khoản, hướng camera vào mã QR của Chủ nhà. Ứng dụng tự động gửi mã lên `POST /api/guest/redeem` và đăng nhập đúng cấp quyền.
4. **Thu hồi khẩn cấp:** Chủ nhà có thể thu hồi mã mời chưa dùng hoặc đăng xuất phiên khách bất cứ lúc nào từ bảng quản trị.

---

## 3. Web 3D Digital Twin (`/`) & Giao diện Di động (`/app`)

### Trang Tổng quan 3D (`/`)
- **Mô hình ngôi nhà 3D tương tác:** Xoay, thu phóng trực tiếp mô hình biệt thự 3D (`Three.js`). Khi bật/tắt đèn, mở/đóng cửa chính, chạy bơm vườn hay kích hoạt còi báo động, hiệu ứng ánh sáng, cánh cửa và trạng thái thiết bị trên mô hình 3D đồng bộ trong vòng `< 1 giây` qua `SSE` & `WebSocket`.
- **Thẻ cảm biến thời gian thực:** Hiển thị liên tục **Nhiệt độ (°C)**, **Độ ẩm không khí (%)** từ `DHT11`, **Độ ẩm đất (%)** từ `A0` và trạng thái **Cảm biến âm thanh `KY-037`** (`D5`).
- **Bảng điều khiển 6 thiết bị:** Nút gạt tức thì (Optimistic UI) chỉ hiển thị đúng các thiết bị thuộc quyền của tài khoản đang đăng nhập.
- **Khung Trợ lý Giọng nói & Nhập lệnh văn bản:** Nhấn nút Micro để nói tiếng Việt trực tiếp hoặc gõ lệnh vào ô văn bản để kiểm tra phản hồi ngay lập tức.

### Giao diện Mobile Web (`/app`)
- Truy cập `/app` (hoặc `/mobile` sẽ tự chuyển hướng sang `/app`) trên điện thoại để dùng giao diện tối ưu màn hình dọc, chuyển nhanh giữa tab **Nhà**, **Thiết bị**, **Giọng nói** và **Tài khoản**.

---

## 4. Trang Tự Động Hóa (`/automation`)

Trang `/automation` cho phép xem và quản lý tập trung toàn bộ kịch bản tự động của ngôi nhà:

1. **Luật đơn giản (1 điều kiện IF -> THEN):**
   - Ví dụ: *Khi độ ẩm đất dưới 40% thì bật bơm tưới cây*, hoặc *Khi mở cửa chính thì bật đèn phòng khách*.
2. **Luật tổ hợp nhiều điều kiện (`AND` / `OR`):**
   - Kết hợp nhiều cảm biến trong cùng một luật, ví dụ: *Nếu nhiệt độ > 32°C `AND` độ ẩm < 50% thì bật bơm tưới cây*, hoặc *Nếu độ ẩm đất < 35% `OR` phát hiện tiếng vỗ tay KY-037 thì bật đèn phòng khách*.
   - Luật được bộ máy nền (`evaluate_compound_rules`) đánh giá liên tục theo telemetry mới nhất và hỗ trợ bật/tắt hoặc xóa trực tiếp trên giao diện.
3. **Lịch lặp lại theo thứ trong tuần:**
   - Đặt giờ cố định theo từng ngày (`Thứ 2` đến `Chủ nhật`, ví dụ: *Bật đèn phòng khách lúc 18:00 hằng ngày* hoặc *Tắt toàn bộ đèn lúc 23:00 từ Thứ 2 đến Thứ 6*).
4. **Bộ hẹn giờ đếm ngược (`Timers`):**
   - Xem danh sách toàn bộ bộ đếm ngược đang hoạt động (đồng bộ qua `GET /api/timers`), thời gian còn lại theo giây và nút hủy ngay lập tức.

> **Lưu ý phân quyền:** Tài khoản **Cấp 3 (Khách)** chỉ có quyền xem trên `/automation`; các nút tạo/sửa/xóa luật, lịch và hẹn giờ được ẩn tự động.

---

## 5. Lệnh Giọng Nói Tiếng Việt & Chính Sách Xác Nhận

Trợ lý giọng nói chỉ xử lý **khẩu lệnh tiếng Việt** và phản hồi bằng giọng nói tiếng Việt (`Aoede`). Chính sách thực thi chia thành **2 mức an toàn**:

### Mức 1 — Thực thi tức thì + phản hồi ngắn gọn
Áp dụng cho các lệnh điều khiển thiết bị trực tiếp và truy vấn trạng thái/cảm biến:
- *"Mở cửa chính"* / *"Đóng cửa chính"* *(chỉ Cấp 1)*
- *"Bật đèn phòng khách"* / *"Tắt đèn phòng ngủ"* / *"Tắt hết đèn"*
- *"Bật bơm tưới cây"* / *"Cho bơm vườn nghỉ chạy đi em"* *(Cấp 1 & Cấp 2)*
- *"Bật còi báo động"* / *"Tắt còi báo động"* *(chỉ Cấp 1)*
- *"Bật loa"* / *"Tắt loa phản hồi"* *(Cấp 1 & Cấp 2)*
- *"Nhiệt độ phòng hiện tại bao nhiêu?"*, *"Kiểm tra độ ẩm đất"*, *"Trạng thái các thiết bị"*

> Nếu bạn gọi thiết bị không nằm trong hợp đồng 6 thiết bị (như quạt trần, điều hòa, TV/IR), hệ thống sẽ **từ chối an toàn bằng tiếng Việt** và không làm thay đổi trạng thái bất kỳ thiết bị nào.

### Mức 2 — Yêu cầu xác nhận 2 bước (Confirm-Only)
Để tránh thao tác nhầm làm thay đổi cấu hình bền vững, hệ thống sẽ **tạm giữ (stage) và hỏi xác nhận bằng tiếng Việt** (bạn trả lời *"Có"*, *"Đồng ý"*, *"Xác nhận"* để chạy hoặc *"Hủy"*, *"Không"* để bỏ) đối với:
1. **Tạo / sửa / xóa lệnh tùy chỉnh (custom commands):** Ví dụ *"Dạy câu 'vừng ơi mở ra' là mở cửa chính và bật đèn phòng khách"*.
2. **Tạo / hủy lịch lặp hoặc hẹn giờ:** Ví dụ *"Hẹn 10 phút nữa tắt đèn phòng ngủ"*, *"Đặt lịch 6 giờ sáng mỗi ngày bật bơm tưới cây"*.
3. **Liên kết chéo giữa các thiết bị (cross-device rules):** Ví dụ *"Khi mở cửa chính thì tự động bật đèn phòng khách"*.
4. **Khôi phục cài đặt gốc (Reset hệ thống):** Ví dụ *"Reset hệ thống về mặc định"* *(chỉ Cấp 1)*.

---

## 6. Ứng dụng Android Gốc (`app/`)

- **Cài đặt & Kết nối:** Sau khi biên dịch từ thư mục `app/` (`lightbuild --plain build app`), cài tệp APK lên thiết bị Android. Ứng dụng hỗ trợ kết nối tới máy chủ từ xa (Tailscale/HTTPS) và tự động dự phòng `127.0.0.1:8088` khi chạy qua `adb reverse tcp:8088 tcp:8088`.
- **Luồng sử dụng chính:**
  1. **Màn hình Đăng nhập / Quét QR:** Bắt buộc xác thực trước khi hiển thị thiết bị (không bỏ qua đăng nhập, không báo thành công giả khi mất mạng).
  2. **Tab Trang chủ:** Hiển thị thẻ cảm biến thời gian thực (Nhiệt độ, Độ ẩm không khí DHT11, Độ ẩm đất, Âm thanh KY-037) và lối tắt điều khiển nhanh.
  3. **Tab Thiết bị:** Hiển thị đúng danh sách thiết bị được phép theo cấp quyền (tối đa 6 thiết bị chuẩn, bao gồm `speaker_amp`, không còn quạt/điều hòa).
  4. **Tab Giọng nói:** Nhấn giữ hoặc chạm nút Micro để gửi khẩu lệnh tiếng Việt và nghe phản hồi âm thanh.
  5. **Tab Tài khoản:** Xem thông tin phiên, quản trị danh sách thành viên (Cấp 1), quét QR mời và đăng xuất (tự động thu hồi phiên phía máy chủ qua `POST /api/auth/logout`).

---

## 7. Trình Mô Phỏng Phần Cứng (`/wokwi`)

Trang `/wokwi` (dành cho **Cấp 1 Chủ nhà** và **Cấp 2 Thành viên**) giúp trực quan hóa và kiểm chứng phần cứng ngay trên trình duyệt:
- Hiển thị sơ đồ đấu nối 10 chân của `NodeMCU ESP8266 v2 Amica` khớp 100% với mạch PCB DIY `100 × 80 mm` và tệp `firmware/wokwi/diagram.json`.
- Cho phép xem trực tiếp mã nguồn `firmware/esp8266_smarthome/esp8266_smarthome.ino` đang đồng bộ với backend.
- Phản ánh tức thì trạng thái bật/tắt của 6 thiết bị chấp hành và giá trị 3 cảm biến khi bạn thao tác từ Web Dashboard, Android hoặc giọng nói.

---

## 8. Hành vi Khi Mạch ESP8266 Mất Mạng / Mất Kết Nối Máy Chủ

Hệ thống được thiết kế theo nguyên tắc **an toàn trước tiên (fail-safe)** khi mạch phần cứng `ESP8266` mất kết nối Wi-Fi, mất kết nối máy chủ trung tâm hoặc Internet bị gián đoạn:

### 8.1. Dấu hiệu nhận biết cục bộ & trên giao diện
- **Đèn LED báo mất kết nối (không chặn vòng lặp):** Mạch ESP8266 thực hiện nhịp **nháy đôi ngắn** (`2 xung 120 ms` cách nhau `160 ms`, lặp lại mỗi chu kỳ `4 giây`), sau đó tự trả về đúng trạng thái đèn mà người dùng đang bật/tắt.
- **Tín hiệu còi / loa báo ngắt kết nối:** Khi chuyển trạng thái từ đang kết nối sang mất kết nối, mạch phát đúng **2 tiếng bíp ngắn (`80 ms`)** một lần duy nhất (không kêu kéo dài hay lặp lại vô hạn).
- **Hiển thị trên Web (`/`), Mobile Web (`/app`) & Ứng dụng Android:**
  - Nếu máy chủ không nhận được nhịp tim (`heartbeat`) từ mạch quá ngưỡng cấu hình (`30 giây` mặc định) hoặc nhận tín hiệu mất kết nối `MQTT LWT`, toàn bộ thẻ thiết bị tự động hiển thị nhãn **`Mất kết nối`** kèm mốc thời gian **`Lần cuối: HH:MM:SS dd/MM/yyyy`**.
  - Các công tắc điều khiển qua máy chủ được khóa/cảnh báo để **tuyệt đối không báo thành công giả**.
  - Trợ lý Giọng nói và API trả về HTTP `503` cùng câu phản hồi tiếng Việt nêu rõ thiết bị đang mất kết nối và thời điểm nhìn thấy gần nhất, thay vì nói *"Đã bật/tắt..."*.

### 8.2. Trạng thái an toàn mặc định khi ngoại tuyến (Safe Defaults)
1. **Cửa chính (`main_door`):** Tự động đóng/khóa ngay khi phát hiện mất kết nối máy chủ và **tuyệt đối cấm mở cửa ở chế độ ngoại tuyến** ở tầng firmware.
2. **Bơm tưới cây (`garden_pump`):** Vẫn duy trì tự động bảo vệ độ ẩm đất cục bộ (`< 40%` bật, `≥ 70%` tắt), đồng thời áp dụng **giới hạn thời gian chạy liên tục tối đa `120 giây`** để tự ngắt an toàn (chống cháy bơm hoặc tràn nước nếu cảm biến lỗi).
3. **Còi báo động (`alarm_siren`):** Áp dụng **giới hạn thời gian kêu tối đa `30 giây`** ở chế độ ngoại tuyến để tránh còi kêu kẹt vô hạn.
4. **Loa phản hồi (`speaker_amp`):** Tự động ngắt nguồn khuếch đại sau thời gian trễ nhàn rỗi (`1,5 giây`).

### 8.3. Điều khiển giọng nói ngoại tuyến qua mạng LAN (A1, A2, A3)
- **Không cần máy chủ trung tâm hay Internet (A1):** Khi mất kết nối máy chủ, ứng dụng Android sử dụng bộ nhận dạng giọng nói tiếng Việt ngoại tuyến trên thiết bị (`vi-VN`, `EXTRA_PREFER_OFFLINE`) kết hợp bộ đọc giọng nói tiếng Việt cục bộ (`TextToSpeech`) và gửi lệnh trực tiếp tới mạch ESP8266 trong cùng mạng LAN qua `POST http://<địa-chỉ-LAN-mạch>/offline/cmd` (mặc định `smarthome-esp8266.local`, dự phòng SoftAP `192.168.4.1`).
- **Tập lệnh cơ bản cố định, không phân biệt cấp (A2):**
  - Chỉ hỗ trợ nhóm lệnh bật/tắt cơ bản cố định cho: `Đèn phòng khách`, `Đèn phòng ngủ`, `Bơm tưới cây`, `Còi báo động`, `Loa phản hồi`, `Đóng/khóa cửa chính` và hỏi trạng thái.
  - Ở chế độ ngoại tuyến **không phân biệt Cấp 1 / Cấp 2 / Cấp 3** và **không hỗ trợ** lệnh tùy chỉnh (custom commands), ngữ cảnh nhiều bước, luật tự động hóa hay đặt lịch/hẹn giờ.
- **Cấm mở cửa chính tuyệt đối (A3):** Mọi yêu cầu mở cửa chính khi đang mất kết nối đều bị chặn cứng ngay tại firmware lẫn ứng dụng và phản hồi ngắn gọn: *"Đang mất kết nối máy chủ, tuyệt đối không được phép mở cửa chính."*

### 8.4. Tự động kết nối lại & đồng bộ ngược trạng thái thực tế (A4)
- **Kết nối lại theo thời gian chờ tăng dần (Exponential Backoff):** Mạch ESP8266 tự động thử kết nối lại Wi-Fi và máy chủ theo chu kỳ tăng dần `1s → 2s → 4s → 8s → 16s → tối đa 30s`, hoàn toàn không làm treo cảm biến hay bộ hẹn giờ an toàn.
- **Tự động đồng bộ trạng thái thực tế về máy chủ, Web & Android:** Khi kết nối khôi phục, mạch chủ động gửi trạng thái vật lý hiện tại của các thiết bị đã thay đổi trong thời gian ngoại tuyến lên `POST /api/hardware/resync`. Máy chủ tiếp nhận làm trạng thái chuẩn, ghi nhật ký `board_offline_resync` và phát sóng `SSE` / `WebSocket` tức thì để Web Dashboard (`/`), `/app` và Ứng dụng Android tự động bỏ nhãn **`Mất kết nối`** và hiển thị đúng trạng thái thực tế mà không cần tải lại trang thủ công.

---

## 9. Tài liệu Liên quan

- [Tổng quan dự án & khởi chạy nhanh (`README.md`)](README.md)
- [Hướng dẫn nạp Firmware USB & cài Wi-Fi runtime (`docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md`)](docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md)
- [Kiến trúc hệ thống chi tiết (`docs/kien_truc/KIEN_TRUC_HE_THONG.md`)](docs/kien_truc/KIEN_TRUC_HE_THONG.md)
- [Tổng quan phần cứng 14 module & In 3D (`docs/phan_cung/TONG_QUAN_PHAN_CUNG_VA_IN_3D.md`)](docs/phan_cung/TONG_QUAN_PHAN_CUNG_VA_IN_3D.md)
- [Hướng dẫn chế tạo PCB, cắt Mica / In 3D & đấu nối (`docs/HARDWARE_BUILD_GUIDE.md`)](docs/HARDWARE_BUILD_GUIDE.md)
- [Hướng dẫn vận hành & triển khai (`docs/huong_dan/VAN_HANH_VA_TRIEN_KHAI.md`)](docs/huong_dan/VAN_HANH_VA_TRIEN_KHAI.md)
- [Các vấn đề đã biết (`KNOWN_ISSUES.md`)](KNOWN_ISSUES.md)
- [Nhật ký phát hành (`CHANGELOG.md`)](CHANGELOG.md)
