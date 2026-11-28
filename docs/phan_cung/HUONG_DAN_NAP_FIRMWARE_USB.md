# Hướng Dẫn Nạp Firmware & Cấu Hình Wi-Fi ESP8266 Qua USB

> **Tài liệu đầy đủ thống nhất:** Bản hướng dẫn chi tiết toàn bộ quy trình cắm USB, sơ đồ luồng cấu hình LittleFS `/wifi_config.json`, chế độ an toàn ngoại tuyến (Addendum A1–A4) và bảng xử lý sự cố đầy đủ được duy trì tại **[`docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md`](../huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md)**.
>
> Tệp này được giữ đồng bộ tại đường dẫn `/docs/phan_cung/HUONG_DAN_NAP_FIRMWARE_USB.md` để phục vụ trực tiếp nút mở tài liệu trên trang hướng dẫn đấu nối `/wokwi` và script [`hardware/flash_and_setup.ps1`](../../hardware/flash_and_setup.ps1).

---

## 1. Nguyên Tắc Bảo Mật & Môi Trường Nạp

- **Không bao giờ ghi mật khẩu Wi-Fi hay `HARDWARE_API_KEY` vào mã nguồn `esp8266_smarthome.ino` hoặc đẩy lên Git.** Thông số Wi-Fi được nạp runtime qua cổng Serial USB và lưu trong bộ nhớ Flash **LittleFS** (`/wifi_config.json`).
- **Toolchain chuẩn:** **PlatformIO Core (`6.2.0`)** tích hợp `esptool.py`, tự quản lý 4 thư viện trong [`firmware/esp8266_smarthome/platformio.ini`](../../firmware/esp8266_smarthome/platformio.ini) (`PubSubClient`, `ArduinoJson`, `DHT sensor library`, `Adafruit Unified Sensor`).
- **Driver USB-Serial (`CP210x` / `CH340`):**
  - **NodeMCU ESP8266 v2 Amica (chuẩn hệ thống):** Dùng chip cầu **CP2102** $\rightarrow$ cài *Silicon Labs CP210x Universal Windows Driver* nếu Windows chưa nhận cổng `COM`.
  - **Bo tương thích chip CH340/CH341:** Cài *WCH CH341SER* nếu Windows chưa nhận cổng `COM`.
- **Kiểm tra trước khi cắm mạch:** Cáp Micro-USB truyền dữ liệu 4 lõi, mạng Wi-Fi băng tần **2.4 GHz**, và đảm bảo an toàn chân boot-strap **`D3 (GPIO0) = HIGH`**, **`D4 (GPIO2) = HIGH`**, **`D8 (GPIO15) = LOW`**.

---

## 2. Lệnh Chạy Nhanh (1 Lệnh PowerShell Duy Nhất)

```powershell
# Bước 1: Kiểm tra khô (toolchain, driver CP210x/CH340, cổng COM, biên dịch — KHÔNG nạp xuống mạch)
powershell -NoProfile -ExecutionPolicy Bypass -File hardware\flash_and_setup.ps1 -DryRun

# Bước 2: Cắm NodeMCU ESP8266 qua USB -> nạp firmware + nhập Wi-Fi runtime ẩn mật khẩu + SELF_TEST
powershell -NoProfile -ExecutionPolicy Bypass -File hardware\flash_and_setup.ps1

# Hoặc đọc từ tệp JSON cục bộ không commit Git (hardware/wifi_local.json):
powershell -NoProfile -ExecutionPolicy Bypass -File hardware\flash_and_setup.ps1 -ConfigFile hardware\wifi_local.json
```

### Kết quả đạt yêu cầu
Sau khi nạp, script gửi `WIFI_CONFIG`, `SELF_TEST` và `WIFI_STATUS` qua Serial `115200 baud` và xác nhận:
- `WIFI_CONFIG_OK ssid=<ssid> server=<ip>:<port>`
- `SELF_TEST_PASS node=esp8266_node_01 fw_pins=10 offline_http=80 ...`
- `WIFI_STATUS_OK connected=1 ...`
- Dòng kết luận cuối: **`RESULT: PASS`** (mã thoát `0`).

---

## 3. Xem Hướng Dẫn Đầy Đủ & Xử Lý Sự Cố

- **[Hướng dẫn thống nhất Nạp Firmware USB & Cài Đặt Wi-Fi Runtime (`docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md`)](../huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md)** — Chi tiết từng bước, sơ đồ tuần tự, tùy chọn dòng lệnh (`-Port`, `-SkipWifiSetup`, `-Baud`), chế độ dự phòng ngoại tuyến và bảng khắc phục sự cố.
- **[Tài liệu Firmware ESP8266 (`firmware/README.md`)](../../firmware/README.md)** — Chi tiết sơ đồ 10 chân khóa cứng và máy trạng thái an toàn ngoại tuyến.
- **[Bảng đấu nối 40 dây PCB-Direct (`WIRING_TABLE.md`)](WIRING_TABLE.md)** — Kiểm tra nối dây trước khi cấp nguồn `5V 2A`.
