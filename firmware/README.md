# 🔌 Firmware Vi Điều Khiển NodeMCU ESP8266 v2 Amica (ESP-12E/F)

Thư mục này chứa mã nguồn C++ (`.ino` + các tệp header thuần C++ `.h`) nạp xuống mạch phần cứng **NodeMCU ESP8266 v2 Amica (ESP-12E/F, CP2102)** cho Đồ án Tốt nghiệp Điện tử – Viễn thông, đồng bộ 100% theo hợp đồng **6 thiết bị chấp hành + 3 cảm biến thực tế**.

## Sơ đồ 10 chân chuẩn không xung đột boot (`D0..D8`, `A0`)

| Thiết bị / Cảm biến | Chân NodeMCU | GPIO | Vai trò & Quy tắc an toàn Boot |
| :--- | :---: | :---: | :--- |
| **1. Đèn phòng khách (`living_room_light`)** | **`D0`** | `GPIO 16` | LED 5mm + trở hạn dòng `220Ω–470Ω`, kiêm nháy `enroll_blink` và nháy kép chỉ báo ngoại tuyến. Không xung đột boot. |
| **2. Cửa chính (`main_door` - Servo SG90)** | **`D1`** | `GPIO 5` | Xung PWM `0°` (đóng) / `90°` (mở). Nguồn `5V` + tụ `470µF 16V`. **Khóa cứng không cho mở khi ngoại tuyến (A3).** |
| **3. Cảm biến Nhiệt độ & Độ ẩm (`DHT11`)** | **`D2`** | `GPIO 4` | Giao tiếp 1-Wire đọc `°C` & `%RH` (module xanh 3 chân cấp `3.3V`). |
| **4. Ngõ ra âm thanh PWM (`PAM8403` + Loa bạc)** | **`D3`** | `GPIO 0` | Phát chuông/âm báo qua **`R4 10kΩ`** kéo lên `+3.3V`, **tụ chặn DC `C4 10µF 16V`**, cầu phân áp **`R5/R6 2.2kΩ`** và tụ lọc **`C5 10nF`**. **Chân strapping (phải HIGH khi boot):** ở trạng thái nghỉ gọi `noTone()` và trả về `INPUT` (high-Z). |
| **5. Đèn phòng ngủ (`bedroom_light`)** | **`D4`** | `GPIO 2` | LED 5mm + trở nối kiểu **Active-LOW (`3.3V -> R2 220Ω -> LED -> D4`, kèm `R7 10kΩ` pull-up)** (`BEDROOM_LED_ACTIVE_LOW = true`). **Chân strapping (phải HIGH khi boot):** ghi `HIGH` trước khi `pinMode(..., OUTPUT)` để đèn tắt và không kéo `GPIO2` xuống `LOW` khi reset. |
| **6. Cảm biến âm thanh (`KY-037/038 DO`)** | **`D5`** | `GPIO 14` | Cấp nguồn `3.3V`, đọc sườn xung `DO` bằng ngắt + chống dội `>= 400ms` $\rightarrow$ MQTT `smarthome/telemetry/sound` / `POST /api/sound_sensor`. |
| **7. Máy bơm tưới cây (`garden_pump` - Relay 1 xanh)** | **`D6`** | `GPIO 12` | Kích Relay 1 xanh 5V đóng/ngắt bơm trắng `3–6V` + Diode `D1 1N4007` chống xung ngược + tụ `C2 470µF 16V` lọc rail `5V`. Tự động bật khi đất `< 40%`, tắt khi `>= 70%`, **tự ngắt an toàn sau tối đa `120 giây` chạy liên tục**. |
| **8. Nguồn mạch loa (`speaker_amp` - Relay 2 đỏ opto)** | **`D7`** | `GPIO 13` | Kích Relay 2 đỏ opto (đặt jumper **`H`**, `COM/NO -> +5V`) cấp nguồn `5V` (lọc bởi `C6 100nF`) cho mạch xanh `PAM8403` + loa tròn bạc. Tự bật khi phát chuông và tự ngắt sau `1.5s` nghỉ (hoặc bật/tắt tay qua Dashboard/Voice). |
| **9. Còi báo động (`alarm_siren` - Buzzer 5V)** | **`D8`** | `GPIO 15` | Lái low-side qua **`R10 1kΩ` → `Q1 S8050` (NPN)** (`E -> GND`, `Buzzer(+) -> +5V`, `Buzzer(-) -> Q1.C`), kèm diode dập xung **`D2 1N4007`** song song còi và trở kéo xuống **`R9 10kΩ`** từ `D8 -> GND` giữ `GPIO15` ở mức `LOW` khi boot. **Tự tắt sau `30 giây` khi ngoại tuyến.** Tuyệt đối không gắn pull-up lên `3.3V`. |
| **10. Cảm biến độ ẩm đất (`soil_moisture` - LM393)** | **`A0`** | `ADC0` | Cấp `3.3V` cho module `LM393` (bảo vệ `A0 <= 3.3V`), đọc chân `AO` (`0–100%`). |

## Phân biệt Micro Voice AI và Cảm biến Âm thanh KY-037
- **Giọng nói thông minh Gemini Voice AI (`gemini-3.8-live`, giọng `Aoede`):** Thu âm trực tiếp bằng **micro và loa của trình duyệt Web / ứng dụng di động** (`Web/Mobile mic + speaker`), không thu âm giọng nói qua UART `RX` của ESP8266.
- **Cảm biến KY-037/038 (`D5/GPIO14`):** Chỉ dùng chân `DO` để phát hiện **tiếng vỗ tay / tiếng động lớn** cục bộ trên mạch phần cứng.
- **Cổng `RX/TX` (`GPIO3/1`):** Dành riêng cho Serial Debug `115200 baud` qua CP2102.

---

## Cơ chế Hoạt động Ngoại tuyến & Mất kết nối (Offline Fail-Safe — Addendum A1–A4)

Toàn bộ cấu hình an toàn, bộ phân tích lệnh và máy trạng thái ngoại tuyến được tách ra 3 tệp header thuần C++ (không phụ thuộc Arduino để kiểm thử đơn vị độc lập trên máy tính):
- `esp8266_smarthome/offline_safety_config.h`: Nguồn cấu hình đơn nhất (SSOT) cho 6 thiết bị, thời gian backoff, ngưỡng an toàn bơm/còi/loa, chu kỳ LED/bíp ngoại tuyến và câu trả lời tiếng Việt.
- `esp8266_smarthome/offline_command_grammar.h`: Bộ chuẩn hóa tiếng Việt UTF-8 không dấu và phân tích cú pháp lệnh cố định (0 cấp phát heap).
- `esp8266_smarthome/offline_fsm.h`: Máy trạng thái `OfflineFsm`, `ExponentialBackoff`, `OfflineLedPattern`, `OfflineDisconnectBeeper` và hàng đợi vòng `OfflineEventRing`.

### 1. Kết nối lại theo hàm mũ không chặn (An toàn Watchdog)
- **Wi-Fi STA, MQTT & HTTP Server:** Thử kết nối lại theo lịch `millis()` tăng dần `1s -> 2s -> 4s -> 8s -> 16s -> 30s` (tối đa `30.000 ms`), lập tức đặt lại về `1.000 ms` ngay khi kết nối thành công.
- **Không bao giờ treo Watchdog hay lặp reboot:** Loại bỏ hoàn toàn vòng lặp `while` chặn và `delay()` kéo dài trong `loop()`; âm báo chuông, `enroll_blink` và bíp mất kết nối đều chạy không chặn kèm `yield()`.
- **Heartbeat định kỳ:** Khi kết nối được máy chủ, mạch gửi `POST /api/hardware/heartbeat` mỗi **`3 giây`** kèm MQTT birth/LWT (`smarthome/status/esp8266`).

### 2. Trạng thái mặc định an toàn & bộ hẹn giờ bảo vệ cục bộ
| Thiết bị | Hành vi khi mất kết nối / chạy ngoại tuyến | Tham số trong `offline_safety_config.h` |
| :--- | :--- | :--- |
| **Cửa chính (`main_door`, D1)** | Tự động **đóng khóa về `0°`** ngay khi chuyển `ONLINE -> OFFLINE` và **cấm mở tuyệt đối** suốt thời gian ngoại tuyến. | `OFFLINE_MAIN_DOOR_OPEN_ALLOWED = false` |
| **Máy bơm (`garden_pump`, D6)** | Giữ logic độ ẩm đất `<40%` bật / `>=70%` tắt, nhưng **tự ngắt bắt buộc sau `120 giây`** chạy liên tục (khóa tự kích lại cho tới khi đất `>=70%` hoặc có lệnh điều khiển mới). | `PUMP_MAX_CONTINUOUS_RUN_MS = 120000UL` |
| **Còi báo động (`alarm_siren`, D8)** | Cho phép bật/tắt cơ bản ngoại tuyến nhưng **tự tắt sau `30 giây`** để không bao giờ bị kẹt kêu vô hạn. | `SIREN_MAX_OFFLINE_RUN_MS = 30000UL` |
| **Nguồn loa (`speaker_amp`, D7)** | Đuôi tự ngắt sau phát chuông vẫn chạy liên tục ngoại tuyến (`1.5 giây`). | `SPEAKER_AMP_IDLE_TAIL_DEFAULT_MS = 1500UL` |

### 3. Chỉ báo ngoại tuyến cục bộ (LED & Buzzer)
- **LED chỉ báo (`D0` - Đèn phòng khách):** Khi ngoại tuyến, nháy kép **`2 xung × 120 ms`** (cách nhau `160 ms`) lặp lại mỗi **`4 giây`**, sau đó khôi phục nguyên trạng thái bật/tắt của người dùng (không làm mất trạng thái đèn).
- **Âm báo mất kết nối (`D8` - Còi 5V):** Khi chuyển từ `ONLINE -> OFFLINE`, phát **2 tiếng bíp ngắn `80 ms`** (cách `100 ms`) **đúng 1 lần duy nhất**, không lặp vô hạn và không can thiệp nếu còi báo động đang được bật chủ động.

### 4. Addendum A1 — Điều khiển giọng nói ngoại tuyến qua mạng LAN cục bộ (không cần Server / Internet)
- ESP8266 chạy sẵn `ESP8266WebServer` trên **cổng `80`** với 2 endpoint JSON:
  - `POST /offline/cmd`: Nhận `{"text": "bật đèn phòng khách"}` hoặc `{"device_id": "living_room_light", "action": "turn_on"}`.
  - `GET /offline/status`: Trả về trạng thái vật lý thực tế của 6 thiết bị, 3 cảm biến và danh sách thiết bị thay đổi ngoại tuyến.
- Hỗ trợ mDNS tại **`http://smarthome-esp8266.local/offline/cmd`** khi còn Wi-Fi nội bộ.
- **SoftAP dự phòng (`WIFI_AP_STA`):** Nếu mất Wi-Fi STA quá **`15 giây`** (`WIFI_AP_FALLBACK_AFTER_MS`), mạch tự phát Wi-Fi **`SmartHome-Offline-AP`** (IP mặc định `192.168.4.1`) trong khi vẫn tiếp tục thử nối lại Wi-Fi chính ở nền.

### 5. Addendum A2 — Tập lệnh cơ bản cố định, không phân quyền ngoại tuyến
- **Chỉ hỗ trợ lệnh cơ bản cố định:** Bật/tắt 5 thiết bị (`living_room_light`, `bedroom_light`, `garden_pump`, `alarm_siren`, `speaker_amp`), **đóng** `main_door`, và hỏi trạng thái thiết bị.
- **Không phân biệt Cấp 1/2/3 ngoại tuyến** (`OFFLINE_ROLE_CHECK_ENABLED = false`): Không từ chối người dùng theo nhãn vai trò khi mất máy chủ.
- **Từ chối lệnh nâng cao:** Mọi khẩu lệnh tùy chỉnh (như *"vừng ơi"*), đặt lịch/hẹn giờ (*"hẹn giờ"*, *"sau 5 phút"*), luật tự động `IF-ELSE` hoặc thiết bị ngoài danh mục 6 thiết bị đều bị từ chối với mã `CUSTOM_OR_ADVANCED_FORBIDDEN_OFFLINE` (HTTP `400`).

### 6. Addendum A3 — Tuyệt đối cấm mở cửa chính khi ngoại tuyến (Khóa cứng trong Firmware)
- Mọi yêu cầu mở `main_door` (`90°`) từ bất kỳ nguồn nào (`POST /offline/cmd`, Serial UART hay hàm phần cứng `setMainDoorState(true)`) khi chưa có kết nối máy chủ đều bị **chặn ở cả hai lớp (`OfflineFsm` và `setMainDoorState`)**:
  - Giữ servo ở góc `0°`, phát âm báo từ chối (mode `3`), trả HTTP `403`, mã `DOOR_OPEN_FORBIDDEN_OFFLINE`.
  - Câu phản hồi tiếng Việt cố định: *"Đang mất kết nối máy chủ, tuyệt đối không được phép mở cửa chính."*

### 7. Addendum A4 — Tự động đồng bộ lại khi kết nối trở lại (Auto-Resync)
- Mọi thay đổi vật lý ngoại tuyến (lệnh giọng nói LAN, Serial, đóng cửa an toàn, tự ngắt bơm 120s, tự tắt còi 30s) đều được đánh dấu vào `offlineDirtyMask` và lưu vào hàng đợi vòng `OfflineEventRing` (16 sự kiện gần nhất).
- Khi chuyển `OFFLINE -> ONLINE`, mạch **ưu tiên gửi `POST /api/hardware/resync`** (kèm header `X-Hardware-Key`) và **MQTT `smarthome/state/report`** chứa đầy đủ trạng thái vật lý của cả 6 thiết bị, danh sách `offline_changed_devices`, `offline_events` và cảm biến mới nhất **TRƯỚC KHI** kéo `/api/state` từ Server — bảo đảm Server, Web và App cập nhật đúng những gì đã xảy ra ngoài thực tế.

---

## Biên dịch với PlatformIO & Cấu hình HTTP Auth/Port

```bash
pio run -d firmware/esp8266_smarthome
```

Firmware hỗ trợ macro biên dịch tùy chọn (và giữ nguyên biến `WIFI_SSID`, `WIFI_PASSWORD`, `SERVER_IP`, `MQTT_SERVER` cho trang `/wokwi`):
- `SMARTHOME_SERVER_PORT` (mặc định `8088`, có thể đổi khi kiểm thử E2E)
- `SMARTHOME_HARDWARE_API_KEY` (gửi tự động qua header `X-Hardware-Key` tới `/api/hardware/heartbeat`, `/api/hardware/resync`, `/api/state`, `/api/dht11`, `/api/soil_moisture`, `/api/sound_sensor`, `/api/text_command`)
- `SMARTHOME_OFFLINE_AP_PASSWORD` (mặc định mở `""` để điện thoại kết nối nhanh khi khẩn cấp; có thể đặt chuỗi `>= 8` ký tự khi biên dịch)
