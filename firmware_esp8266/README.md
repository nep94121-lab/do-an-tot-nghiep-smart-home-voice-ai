# 🔌 Firmware Vi Điều Khiển NodeMCU ESP8266 (ESP-12E)

Thư mục này chứa mã nguồn C++ (`.ino`) nạp xuống mạch phần cứng **NodeMCU ESP8266 (ESP-12E, CP2102)** cho Đồ án Tốt nghiệp Điện tử – Viễn thông.

## Sơ đồ đấu nối chân chuẩn trên NodeMCU ESP8266
| Thiết bị / Linh kiện | Ký hiệu trên mạch ESP8266 | Mã GPIO | Giao thức / Chức năng |
| :--- | :---: | :---: | :--- |
| **1. Cửa chính (`main_door` - Servo SG90)** | **`D1`** | `GPIO 5` | Xung PWM đóng/mở cửa |
| **2. Đèn phòng khách / Phát Hồng ngoại (`IR Blaster`)** | **`D2`** | `GPIO 4` | Điều khiển đèn / Phát sóng IR 38kHz |
| **3. Thu sóng Hồng ngoại (`VS1838B` - IR Learning)** | **`D5`** | `GPIO 14` | Giải mã sóng Remote 38kHz |
| **4. Cảm biến Nhiệt độ & Độ ẩm (`DHT11`/`DHT22`)** | **`D6`** | `GPIO 12` | Giao tiếp 1-Wire đọc °C & %RH |
| **5. Đèn phòng ngủ / Quạt (`bedroom_light` / `fan`)** | **`D7`** | `GPIO 13` | Xuất mức logic GPIO / Relay |
| **6. Còi báo động (`alarm_siren` - Buzzer 5V)** | **`D8`** / **`D0`** | `GPIO 15` / `16` | Báo động an ninh / Nháy tín hiệu |
