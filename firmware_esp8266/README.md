# 🔌 Firmware Vi Điều Khiển NodeMCU ESP8266 v2 Amica (ESP-12E/F)

Thư mục này chứa mã nguồn C++ (`.ino`) nạp xuống mạch phần cứng **NodeMCU ESP8266 v2 Amica (ESP-12E/F, CP2102)** cho Đồ án Tốt nghiệp Điện tử – Viễn thông, đồng bộ 100% theo hợp đồng **6 thiết bị chấp hành + 3 cảm biến thực tế**.

## Sơ đồ 10 chân chuẩn không xung đột boot (`D0..D8`, `A0`)

| Thiết bị / Cảm biến | Chân NodeMCU | GPIO | Vai trò & Quy tắc an toàn Boot |
| :--- | :---: | :---: | :--- |
| **1. Đèn phòng khách (`living_room_light`)** | **`D0`** | `GPIO 16` | LED 5mm + trở hạn dòng `220Ω–470Ω`, kiêm nháy báo `enroll_blink`. Không xung đột boot. |
| **2. Cửa chính (`main_door` - Servo SG90)** | **`D1`** | `GPIO 5` | Xung PWM `0°` (đóng) / `90°` (mở). Nguồn `5V` + tụ `470µF 16V`. Chân GPIO an toàn nhất. |
| **3. Cảm biến Nhiệt độ & Độ ẩm (`DHT11`)** | **`D2`** | `GPIO 4` | Giao tiếp 1-Wire đọc `°C` & `%RH` (module xanh 3 chân cấp `3.3V`). |
| **4. Ngõ ra âm thanh PWM (`PAM8403` + Loa bạc)** | **`D3`** | `GPIO 0` | Phát chuông/âm báo qua **tụ chặn DC `100nF–1µF`** (tuyệt đối không dùng `470µF`) + cầu phân áp RC. **Chân strapping (phải HIGH khi boot):** ở trạng thái nghỉ gọi `noTone()` và trả về `INPUT` (high-Z). |
| **5. Đèn phòng ngủ (`bedroom_light`)** | **`D4`** | `GPIO 2` | LED 5mm + trở nối kiểu **Active-LOW (`3.3V -> R -> LED -> D4`)** (`BEDROOM_LED_ACTIVE_LOW = true`). **Chân strapping (phải HIGH khi boot):** ghi `HIGH` trước khi `pinMode(..., OUTPUT)` để đèn tắt và không kéo `GPIO2` xuống `LOW` khi reset. |
| **6. Cảm biến âm thanh (`KY-037/038 DO`)** | **`D5`** | `GPIO 14` | Cấp nguồn `3.3V`, đọc sườn xung `DO` bằng ngắt + chống dội `>= 400ms` $\rightarrow$ MQTT `smarthome/telemetry/sound` / `POST /api/sound_sensor`. |
| **7. Máy bơm tưới cây (`garden_pump` - Relay 1 xanh)** | **`D6`** | `GPIO 12` | Kích Relay 1 xanh 5V đóng/ngắt bơm trắng `3–6V` + Diode `1N4007` chống xung ngược + tụ `470µF 16V` lọc rail `5V`. Tự động bật khi đất `< 40%`, tắt khi `>= 70%`. |
| **8. Nguồn mạch loa (`speaker_amp` - Relay 2 đỏ opto)** | **`D7`** | `GPIO 13` | Kích Relay 2 đỏ opto (đặt jumper **`H`**) cấp nguồn `5V` cho mạch xanh `PAM8403` + loa tròn bạc. Tự bật khi phát chuông và tự ngắt sau `1.5s` nghỉ (hoặc bật/tắt tay qua Dashboard/Voice). |
| **9. Còi báo động (`alarm_siren` - Buzzer 5V)** | **`D8`** | `GPIO 15` | Kích mức **Active-HIGH** (im lặng khi boot nhờ trở kéo xuống nội mạch trên `GPIO15`). Tuyệt đối không gắn pull-up lên `3.3V`. |
| **10. Cảm biến độ ẩm đất (`soil_moisture` - LM393)** | **`A0`** | `ADC0` | Cấp `3.3V` cho module `LM393` (bảo vệ `A0 <= 3.3V`), đọc chân `AO` (`0–100%`). |

## Phân biệt Micro Voice AI và Cảm biến Âm thanh KY-037
- **Giọng nói thông minh Gemini Voice AI (`gemini-3.8-live`, giọng `Aoede`):** Thu âm trực tiếp bằng **micro và loa của trình duyệt Web / ứng dụng di động** (`Web/Mobile mic + speaker`), không thu âm giọng nói qua UART `RX` của ESP8266.
- **Cảm biến KY-037/038 (`D5/GPIO14`):** Chỉ dùng chân `DO` để phát hiện **tiếng vỗ tay / tiếng động lớn** cục bộ trên mạch phần cứng.
- **Cổng `RX/TX` (`GPIO3/1`):** Dành riêng cho Serial Debug `115200 baud` qua CP2102.

## Cấu hình HTTP Auth & Port khi biên dịch
Firmware hỗ trợ macro biên dịch tùy chọn (và giữ nguyên biến `WIFI_SSID`, `WIFI_PASSWORD`, `SERVER_IP`, `MQTT_SERVER` cho trang `/wokwi`):
- `SMARTHOME_SERVER_PORT` (mặc định `8088`, có thể đổi thành `8097` khi test E2E)
- `SMARTHOME_HARDWARE_API_KEY` (gửi tự động qua header `X-Hardware-Key` tới `/api/state`, `/api/dht11`, `/api/soil_moisture`, `/api/sound_sensor`, `/api/text_command`)
