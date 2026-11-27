# Hướng Dẫn Nạp Firmware & Cấu Hình Wi-Fi ESP8266 Qua USB

Tài liệu này hướng dẫn nạp firmware cho bo mạch **NodeMCU ESP8266 v2 Amica (`nodemcuv2`)** và cấu hình Wi-Fi runtime an toàn trực tiếp từ máy Windows bằng **1 lệnh PowerShell duy nhất** ([`hardware/flash_and_setup.ps1`](../../hardware/flash_and_setup.ps1)).

> **Nguyên tắc bảo mật:** Tuyệt đối **không** ghi mật khẩu Wi-Fi hay `HARDWARE_API_KEY` vào mã nguồn `esp8266_smarthome.ino` hoặc đẩy lên Git. Cấu hình Wi-Fi được nạp lúc chạy qua cổng Serial và lưu trong bộ nhớ Flash LittleFS (`/wifi_config.json`) của ESP8266.

---

## 1. Công Cụ Biên Dịch & Trạng Thái Trên Máy LENOVO

- **Công cụ chuẩn (PlatformIO):** Đã cài sẵn `pio` tại `C:\Users\LENOVO\.local\bin\pio.exe` (PlatformIO Core 6.2.0), tích hợp sẵn `esptool.py` và tự quản lý 4 thư viện bắt buộc trong [`firmware/esp8266_smarthome/platformio.ini`](../../firmware/esp8266_smarthome/platformio.ini):
  - `PubSubClient`
  - `ArduinoJson`
  - `DHT sensor library`
  - `Adafruit Unified Sensor`
- **Trạng thái `arduino-cli` / `arduino-cli.yaml`:** Tệp `arduino-cli.yaml` có mặt ở thư mục checkout production trên LENOVO, nhưng nhị phân `arduino-cli` hiện **chưa có trên PATH**. Hãy dùng **PlatformIO qua script `hardware/flash_and_setup.ps1`** (đã cài sẵn, miễn phí, biên dịch ổn định).

---

## 2. Chuẩn Bị Trước Khi Cắm Mạch

1. **Cáp Micro-USB truyền dữ liệu:** Bắt buộc dùng cáp có 4 lõi (truyền dữ liệu + nguồn). Rất nhiều cáp sạc điện thoại chỉ có 2 dây nguồn nên máy tính sẽ không nhận cổng `COM`.
2. **Kiểm tra an toàn chân boot-strap:**
   - `D3 (GPIO0)` và `D4 (GPIO2)` phải ở mức **HIGH** khi khởi động (không bị kéo xuống `GND`).
   - `D8 (GPIO15)` phải ở mức **LOW** khi khởi động (không nối pull-up lên `3.3V`).
   - Nếu đang gắn bo lên mạch ngoài gặp lỗi không nạp được, hãy rút tạm dây tải ở `D3/D4/D8` hoặc giữ nút `FLASH` khi bắt đầu nạp.
3. **Mạng Wi-Fi 2.4 GHz:** Chip ESP8266 **chỉ hỗ trợ Wi-Fi 2.4 GHz** (không kết nối được mạng chỉ phát 5 GHz). Đảm bảo laptop chạy Backend và ESP8266 cùng mạng LAN 2.4 GHz.

---

## 3. Kiểm Tra & Cài Driver USB-Serial (CP2102 / CH340)

Script **không** tự ý sửa driver hệ thống Windows. Bạn kiểm tra driver ở chế độ chỉ đọc trước:

- **NodeMCU v2 Amica (chính hãng):** Dùng chip cầu USB-UART **CP2102** (Silicon Labs).
- **NodeMCU v3 / bản tương thích:** Thường dùng chip **CH340 / CH341** (WCH).

Cách kiểm tra nhanh:
1. Chạy kiểm tra khô (Bước 4 bên dưới) hoặc mở **Device Manager** → mục **Ports (COM & LPT)**.
2. Nếu cắm bo mà thấy thiết bị có dấu chấm than vàng (`CP2102 USB to UART Bridge Controller` hoặc `USB-SERIAL CH340`) hoặc chưa có cổng `COM`:
   - **Với CP2102:** Tải *CP210x Universal Windows Driver* miễn phí từ trang chủ Silicon Labs, giải nén, bấm chuột phải tệp `silabser.inf` → **Install**.
   - **Với CH340/CH341:** Tải *CH341SER.EXE* miễn phí từ trang chủ WCH (wch-ic.com) → chạy cài đặt.
3. Rút cáp và cắm lại để Windows nhận cổng `COMx` (ví dụ `COM3`, `COM4`).

---

## 4. Bước 1 — Chạy Kiểm Tra Khô (`-DryRun`) Trước Khi Nạp

Chạy lệnh sau tại thư mục gốc dự án để kiểm tra PlatformIO, trạng thái driver CP210x/CH340, liệt kê các cổng `COM` hiện có và biên dịch thử firmware **mà không nạp xuống mạch** (an toàn ngay cả khi đang cắm bo):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File hardware\flash_and_setup.ps1 -DryRun
```

Kết quả đạt yêu cầu khi dòng cuối hiển thị `RESULT: PASS` và mã thoát `0`.

---

## 5. Bước 2 — Nạp Firmware & Cấu Hình Wi-Fi Runtime An Toàn

Cắm bo NodeMCU ESP8266 vào cổng USB laptop, sau đó chọn **1 trong 2 cách**:

### Cách A — Nhập Wi-Fi trực tiếp khi chạy (Khuyên dùng)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File hardware\flash_and_setup.ps1
```

Script sẽ tự động:
1. Tự dò cổng `COM` của CP2102/CH340 (hoặc dùng `-Port COM3` nếu máy có nhiều cổng).
2. Biên dịch và nạp firmware bằng `pio run -t upload --upload-port <COMx>`.
3. Hỏi cấu hình Wi-Fi ngay trong terminal:
   - **Wi-Fi SSID (2.4 GHz)**
   - **Mật khẩu Wi-Fi** (nhập ẩn bằng `Read-Host -AsSecureString`, không hiển thị lên màn hình)
   - **IP máy chủ Laptop** (tự gợi ý IPv4 LAN hiện tại, nhấn `Enter` để dùng ngay)
   - **Cổng máy chủ** (mặc định `8088`)
   - **Hardware API Key** (tùy chọn, nhập ẩn, nhấn `Enter` để bỏ qua nếu chưa bật)
4. Gửi lệnh `WIFI_CONFIG` qua Serial `115200 baud` để lưu vào `/wifi_config.json` trên LittleFS và áp dụng ngay lập tức.
5. Chạy tự kiểm tra `SELF_TEST` + `WIFI_STATUS` và in `RESULT: PASS` hoặc `RESULT: FAIL`.

### Cách B — Dùng tệp cấu hình cục bộ `hardware/wifi_local.json` (đã bị `.gitignore`)

Tạo tệp `hardware/wifi_local.json` trên máy cá nhân (tệp này đã được chặn trong `.gitignore`, tuyệt đối không commit):

```json
{
  "ssid": "TEN_WIFI_2_4GHZ",
  "password": "MAT_KHAU_WIFI_CUA_BAN",
  "server_ip": "192.168.1.100",
  "server_port": 8088,
  "mqtt_server": "192.168.1.100",
  "mqtt_port": 1883,
  "hardware_api_key": ""
}
```

Sau đó chạy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File hardware\flash_and_setup.ps1 -ConfigFile hardware\wifi_local.json
```

### Các tham số tùy chọn hữu ích

| Tham số | Tác dụng |
| :--- | :--- |
| `-DryRun` | Kiểm tra toolchain, driver, cổng `COM` và biên dịch firmware; **không** nạp mạch. |
| `-CompileOnly` | Giống `-DryRun`, chỉ biên dịch kiểm tra mã nguồn. |
| `-Port COM3` | Chỉ định đích danh cổng `COM` cần nạp. |
| `-ConfigFile <đường_dẫn>` | Đọc cấu hình Wi-Fi từ tệp JSON cục bộ (nên dùng `hardware\wifi_local.json` đã git-ignore). |
| `-Baud 115200` | Tốc độ Serial cấu hình & tự kiểm tra (mặc định `115200`). |
| `-SkipWifiSetup` | Chỉ nạp firmware và chạy `SELF_TEST` + `WIFI_STATUS`, giữ nguyên cấu hình Wi-Fi cũ trên Flash. |

---

## 6. Đọc Kết Quả `PASS` / `FAIL` & Các Lệnh Serial Hỗ Trợ

Sau khi nạp, script xác nhận 3 phản hồi chuẩn từ firmware (không bao giờ in mật khẩu hay API key):

- `WIFI_CONFIG_OK ssid=<ssid> server=<ip>:<port>` — Firmware đã kiểm tra JSON, lưu `/wifi_config.json` vào LittleFS và kích hoạt kết nối Wi-Fi/MQTT mới.
- `SELF_TEST_PASS node=esp8266_node_01 fw_pins=10 offline_http=80 heap=<bytes> wifi=<0|1> online=<0|1>` — Firmware khởi động đúng 10 chân khóa cứng và HTTP ngoại tuyến cổng 80.
- `WIFI_STATUS_OK connected=<0|1> ip=<ip> rssi=<dBm> ssid=<ssid> server=<ip>:<port> online=<0|1> heap=<bytes>` — Trạng thái Wi-Fi hiện tại.
- Dòng kết luận cuối cùng:
  - **`RESULT: PASS` (exit `0`):** Nạp thành công, tự kiểm tra đạt. (Nếu `connected=0` ngay lúc mới nạp, chờ thêm vài giây rồi kiểm tra lại hoặc xem mục xử lý sự cố 2.4 GHz.)
  - **`RESULT: FAIL` (exit `1`):** Xem dòng `[ERROR]` ngay phía trên để khắc phục.

---

## 7. Bảng Xử Lý Sự Cố Thường Gặp

| Sự cố | Nguyên nhân phổ biến | Cách khắc phục |
| :--- | :--- | :--- |
| **Không thấy cổng `COM`** | Dùng cáp sạc không có dây dữ liệu; thiếu driver CP2102/CH340; cổng USB lỏng. | Đổi sang cáp Micro-USB truyền dữ liệu; cài driver CP210x hoặc CH341SER; thử cổng USB khác trên laptop và chạy lại `-DryRun`. |
| **Lỗi `Access is denied` / `Port busy`** | Arduino IDE Serial Monitor, PuTTY, PlatformIO Monitor hoặc cửa sổ khác đang chiếm cổng `COM`. | Đóng toàn bộ phần mềm Serial Monitor / terminal đang mở cổng `COM`, rút cắm lại USB rồi chạy lại script. |
| **Lỗi nạp `Failed to connect to ESP8266` / treo boot** | Xung đột chân boot-strap **`D3 (GPIO0)`**, **`D4 (GPIO2)`** hoặc **`D8 (GPIO15)`** đang nối tải kéo sai mức điện áp. | Tháo tạm mạch ngoài khỏi `D3/D4/D8` khi nạp; hoặc giữ nút **`FLASH`**, bấm nhả nút **`RST`** rồi thả **`FLASH`** ngay khi `esptool` bắt đầu kết nối. |
| **Nạp xong nhưng `connected=0` (không vào Wi-Fi)** | Router đang phát chỉ **5 GHz** (ESP8266 chỉ hỗ trợ **2.4 GHz**); gõ sai SSID/mật khẩu; ký tự đặc biệt. | Đảm bảo dùng đúng SSID băng tần **2.4 GHz**, kiểm tra lại mật khẩu rồi chạy lại script (hoặc gửi lại `WIFI_CONFIG`). |
| **`connected=1` nhưng `online=0`** | Backend laptop chưa chạy, sai `server_ip`, hoặc Windows Firewall chặn cổng `8088` / `1883`. | Khởi động Backend (`uvicorn backend.server:app --host 0.0.0.0 --port 8088`), xác nhận IPv4 laptop bằng `ipconfig`, mở tường lửa nội bộ (Private Network) cho cổng `8088` và `1883`. |
