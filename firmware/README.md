# Firmware Vi Điều Khiển NodeMCU ESP8266 v2 Amica (ESP-12E/F)

> **Hướng dẫn nạp USB & cài đặt Wi-Fi Runtime (1 lệnh PowerShell, không lưu mật khẩu vào mã nguồn):**
> Xem tài liệu thống nhất tại **[`docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md`](../docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md)** và script thực thi [`hardware/flash_and_setup.ps1`](../hardware/flash_and_setup.ps1).

Thư mục này chứa mã nguồn C++ (`.ino` + các tệp header thuần C++ `.h`) nạp xuống bo mạch **NodeMCU ESP8266 v2 Amica (`ESP-12E/F`, chip USB `CP2102`, `48.26 × 25.40 mm`)** cho Đồ án Tốt nghiệp Điện tử – Viễn thông, đồng bộ 100% theo hợp đồng **6 thiết bị chấp hành + 3 cảm biến thực tế** trên mạch **PCB Hub DIY v3** (không dùng breadboard trắng).

---

## 1. Nạp Firmware & Cài Đặt Wi-Fi Runtime Qua USB (LittleFS)

Tuyệt đối **không** ghi mật khẩu Wi-Fi hay `HARDWARE_API_KEY` vào mã nguồn `esp8266_smarthome.ino`. Thông số mạng được gửi qua Serial (`115200 baud`) bằng lệnh `WIFI_CONFIG` và lưu cục bộ trong Flash **LittleFS** tại `/wifi_config.json`:

```powershell
# Kiểm tra toolchain PlatformIO, driver CP210x/CH340, cổng COM và biên dịch khô (không nạp)
powershell -NoProfile -ExecutionPolicy Bypass -File hardware\flash_and_setup.ps1 -DryRun

# Nạp firmware qua USB + nhập Wi-Fi runtime an toàn (ẩn mật khẩu) + chạy SELF_TEST & WIFI_STATUS
powershell -NoProfile -ExecutionPolicy Bypass -File hardware\flash_and_setup.ps1
```

---

## 2. Sơ Đồ 10 Chân Chuẩn Không Xung Đột Boot (`D0..D8`, `A0`)

| Thiết bị / Cảm biến | Chân NodeMCU | GPIO | Vai trò & Quy tắc an toàn Boot |
| :--- | :---: | :---: | :--- |
| **1. Đèn phòng khách (`living_room_light`)** | **`D0`** | `GPIO 16` | LED 5mm + trở hạn dòng `R1 220Ω`, kiêm nháy `enroll_blink` và nháy kép chỉ báo ngoại tuyến. Không xung đột boot. |
| **2. Cửa chính (`main_door` — Servo SG90)** | **`D1`** | `GPIO 5` | Xung PWM `0°` (đóng) / `90°` (mở). Nguồn `5V` + tụ `C1 470µF 16V`. **Khóa cứng không cho mở khi ngoại tuyến (A3).** |
| **3. Cảm biến Nhiệt độ & Độ ẩm (`DHT11`)** | **`D2`** | `GPIO 4` | Giao tiếp 1-Wire đọc `°C` & `%RH` (module 3 chân cấp `3.3V`, kéo lên `R3 10kΩ` trên PCB). |
| **4. Ngõ ra âm thanh PWM (`PAM8403` + Loa 28mm)** | **`D3`** | `GPIO 0` | Phát chuông/âm báo qua **`R4 10kΩ`** kéo lên `+3.3V`, **tụ chặn DC `C4 10µF 16V`**, cầu phân áp **`R5/R6 2.2kΩ`** và tụ lọc **`C5 10nF`**. **Chân strapping (phải HIGH khi boot):** ở trạng thái nghỉ gọi `noTone()` và trả về `INPUT` (high-Z). |
| **5. Đèn phòng ngủ (`bedroom_light`)** | **`D4`** | `GPIO 2` | LED 5mm nối **Active-LOW (`+3.3V -> R2 220Ω -> LED -> D4`, kèm `R7 10kΩ` pull-up)** (`BEDROOM_LED_ACTIVE_LOW = true`). **Chân strapping (phải HIGH khi boot):** ghi `HIGH` trước khi `pinMode(..., OUTPUT)`. |
| **6. Cảm biến âm thanh (`KY-037/038 DO`)** | **`D5`** | `GPIO 14` | Cấp nguồn **`3.3V`**, đọc sườn xung `DO` bằng ngắt + chống dội `>= 400ms` $\rightarrow$ MQTT `smarthome/telemetry/sound` / `POST /api/sound_sensor`. |
| **7. Máy bơm tưới cây (`garden_pump` — Relay 1 xanh)** | **`D6`** | `GPIO 12` | Kích Relay 1 xanh 5V đóng/ngắt bơm `3–6V` + Diode `D1 1N4007` + tụ `C2 470µF 16V`. Tự động bật khi đất `< 40%`, tắt khi `>= 70%`, **tự ngắt an toàn sau tối đa `120 giây` chạy liên tục**. |
| **8. Nguồn mạch loa (`speaker_amp` — Relay 2 đỏ opto)** | **`D7`** | `GPIO 13` | Kích Relay 2 đỏ opto (đặt jumper **`H`**, `COM/NO -> +5V`) cấp nguồn `5V` (lọc bởi `C6 100nF + C9 100µF 16V` trên PCB) cho `PAM8403` + loa 28mm. Tự bật khi phát chuông và tự ngắt sau `1.5s` nghỉ. |
| **9. Còi báo động (`alarm_siren` — Buzzer 5V)** | **`D8`** | `GPIO 15` | Lái low-side qua **`R10 1kΩ` $\rightarrow$ `Q1 S8050` (NPN)** (`E -> GND`, `Buzzer(+) -> +5V`, `Buzzer(-) -> Q1.C`), kèm diode **`D2 1N4007`** và trở kéo xuống **`R9 10kΩ`** giữ `GPIO15` ở mức `LOW` khi boot. **Tự tắt sau `30 giây` khi ngoại tuyến.** |
| **10. Cảm biến độ ẩm đất (`soil_moisture` — LM393)** | **`A0`** | `ADC0` | Cấp **`3.3V`** cho module `LM393` (lọc `C7/C8 100nF` trên PCB), đọc chân `AO` (`0–100%`). |

## 3. Phân Biệt Micro Voice AI và Cảm Biến Âm Thanh KY-037
- **Giọng nói thông minh Gemini Voice AI (`gemini-3.8-live`, giọng `Aoede`):** Thu âm trực tiếp bằng **micro và loa của trình duyệt Web / ứng dụng Android**, không thu âm giọng nói qua UART `RX` của ESP8266.
- **Cảm biến KY-037/038 (`D5/GPIO14`):** Chỉ dùng chân `DO` để phát hiện **tiếng vỗ tay / tiếng động lớn** cục bộ trên phần cứng.
- **Cổng `RX/TX` (`GPIO3/1`):** Dành riêng cho Serial Debug & cấu hình Wi-Fi runtime `115200 baud` qua CP2102.

---

## 4. Cơ Chế Hoạt Động Ngoại Tuyến & Mất Kết Nối (Offline Fail-Safe — Addendum A1–A4)

Toàn bộ cấu hình an toàn, bộ phân tích lệnh và máy trạng thái ngoại tuyến được tách ra 3 tệp header thuần C++ (không phụ thuộc Arduino để kiểm thử đơn vị độc lập trên máy tính):
- `esp8266_smarthome/offline_safety_config.h`: Nguồn cấu hình đơn nhất (SSOT) cho 6 thiết bị, thời gian backoff, ngưỡng an toàn bơm/còi/loa, chu kỳ LED/bíp ngoại tuyến và câu trả lời tiếng Việt.
- `esp8266_smarthome/offline_command_grammar.h`: Bộ chuẩn hóa tiếng Việt UTF-8 không dấu và phân tích cú pháp lệnh cố định (0 cấp phát heap).
- `esp8266_smarthome/offline_fsm.h`: Máy trạng thái `OfflineFsm`, `ExponentialBackoff`, `OfflineLedPattern`, `OfflineDisconnectBeeper` và hàng đợi vòng `OfflineEventRing`.

### 4.1. Kết nối lại theo hàm mũ không chặn (An toàn Watchdog)
- **Wi-Fi STA, MQTT & HTTP Server:** Thử kết nối lại theo lịch `millis()` tăng dần `1s -> 2s -> 4s -> 8s -> 16s -> 30s` (tối đa `30.000 ms`), lập tức đặt lại về `1.000 ms` ngay khi kết nối thành công.
- **Không treo Watchdog:** Loại bỏ vòng lặp `while` chặn và `delay()` kéo dài trong `loop()`; âm báo chuông, `enroll_blink` và bíp mất kết nối đều chạy không chặn kèm `yield()`.
- **Heartbeat định kỳ:** Gửi `POST /api/hardware/heartbeat` mỗi **`3 giây`** kèm MQTT birth/LWT (`smarthome/status/esp8266`).

### 4.2. Trạng thái mặc định an toàn & bộ hẹn giờ bảo vệ cục bộ
| Thiết bị | Hành vi khi mất kết nối / chạy ngoại tuyến | Tham số trong `offline_safety_config.h` |
| :--- | :--- | :--- |
| **Cửa chính (`main_door`, D1)** | Tự động **đóng khóa về `0°`** ngay khi chuyển `ONLINE -> OFFLINE` và **cấm mở tuyệt đối** suốt thời gian ngoại tuyến. | `OFFLINE_MAIN_DOOR_OPEN_ALLOWED = false` |
| **Máy bơm (`garden_pump`, D6)** | Giữ logic độ ẩm đất `<40%` bật / `>=70%` tắt, nhưng **tự ngắt bắt buộc sau `120 giây`** chạy liên tục. | `PUMP_MAX_CONTINUOUS_RUN_MS = 120000UL` |
| **Còi báo động (`alarm_siren`, D8)** | Cho phép bật/tắt cơ bản ngoại tuyến nhưng **tự tắt sau `30 giây`** để tránh kêu kẹt vô hạn. | `SIREN_MAX_OFFLINE_RUN_MS = 30000UL` |
| **Nguồn loa (`speaker_amp`, D7)** | Tự ngắt nguồn khuếch đại sau `1.5 giây` nhàn rỗi. | `SPEAKER_AMP_IDLE_TAIL_DEFAULT_MS = 1500UL` |

### 4.3. Chỉ báo ngoại tuyến cục bộ (LED & Buzzer)
- **LED chỉ báo (`D0`):** Nháy kép **`2 xung × 120 ms`** (cách nhau `160 ms`) lặp mỗi **`4 giây`**, sau đó khôi phục trạng thái đèn của người dùng.
- **Âm báo mất kết nối (`D8`):** Khi chuyển `ONLINE -> OFFLINE`, phát **2 tiếng bíp ngắn `80 ms`** (cách `100 ms`) đúng **1 lần duy nhất**.

### 4.4. Điều khiển LAN khẩn cấp & Tự đồng bộ lại (Addendum A1–A4)
- **Addendum A1 (HTTP LAN `:80` & SoftAP dự phòng):** Chạy `ESP8266WebServer` cổng `80` (`POST /offline/cmd`, `GET /offline/status`) qua mDNS `http://smarthome-esp8266.local/offline/cmd`. Nếu mất Wi-Fi STA quá `15 giây`, mạch phát SoftAP dự phòng `SmartHome-Offline-AP` (`192.168.4.1`) đồng thời vẫn thử nối lại Wi-Fi chính ở nền.
- **Addendum A2 (Tập lệnh cố định):** Chỉ hỗ trợ bật/tắt 5 thiết bị cơ bản, đóng `main_door` và hỏi trạng thái; từ chối lệnh tùy chỉnh/lịch/luật với mã `CUSTOM_OR_ADVANCED_FORBIDDEN_OFFLINE` (HTTP `400`).
- **Addendum A3 (Cấm mở cửa chính):** Chặn cứng ở cả `OfflineFsm` và `setMainDoorState`, trả HTTP `403` (`DOOR_OPEN_FORBIDDEN_OFFLINE`).
- **Addendum A4 (Auto-Resync):** Khi khôi phục kết nối, mạch ưu tiên gửi `POST /api/hardware/resync` (kèm `X-Hardware-Key`) và MQTT `smarthome/state/report` trước khi kéo trạng thái từ máy chủ.

---

## 5. Biên Dịch Trực Tiếp Với PlatformIO

```powershell
pio run -d firmware/esp8266_smarthome
```

Các macro biên dịch tùy chọn trong [`esp8266_smarthome/platformio.ini`](esp8266_smarthome/platformio.ini):
- `SMARTHOME_SERVER_PORT` (mặc định `8088`)
- `SMARTHOME_HARDWARE_API_KEY` (khóa gửi qua header `X-Hardware-Key`, không hardcode giá trị thật vào Git)
- `SMARTHOME_OFFLINE_AP_PASSWORD` (mật khẩu SoftAP dự phòng, có thể cấu hình `>= 8` ký tự khi biên dịch)
