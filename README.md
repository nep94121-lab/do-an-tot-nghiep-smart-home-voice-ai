# Smart Home Voice AI `v1.0` — Trợ lý Nhà Thông Minh Giọng Nói Tiếng Việt

Trợ lý AI điều khiển nhà thông minh phản hồi tức thì bằng **100% tiếng Việt** (đầu vào và đầu ra chỉ sử dụng tiếng Việt), tích hợp **FastAPI Backend**, **Web 3D Digital Twin (Three.js)**, **ứng dụng Android gốc (Jetpack Compose)** và phần cứng **NodeMCU ESP8266 v2 Amica** theo hợp đồng khóa cứng **6 thiết bị chấp hành + 3 cảm biến**.

---

## 1. Phạm vi Phần cứng Khóa cứng (6 Thiết bị + 3 Cảm biến)

Hệ thống khóa cứng đúng 6 thiết bị chấp hành và 3 cảm biến trên 10 chân NodeMCU ESP8266 (`D0`–`D8`, `A0`). **Không hỗ trợ quạt (`fan`), điều hòa (`ac`) hay hồng ngoại (`IR` / `VS1838B`).**

| Loại | Mã định danh | Tên hiển thị | Chân ESP8266 | Quyền truy cập tối thiểu |
| :--- | :--- | :--- | :---: | :--- |
| Thiết bị | `main_door` | Cửa chính (Servo SG90) | `D1` (`GPIO5`) | Cấp 1 (Chủ nhà) |
| Thiết bị | `alarm_siren` | Còi báo động (Buzzer 5V + Q1 S8050) | `D8` (`GPIO15`) | Cấp 1 (Chủ nhà) |
| Thiết bị | `garden_pump` | Bơm tưới cây (Relay 1 5V + 1N4007) | `D6` (`GPIO12`) | Cấp 2 (Thành viên) |
| Thiết bị | `speaker_amp` | Loa phản hồi PAM8403 (Relay 2 5V + PWM `D3`) | `D7` (`GPIO13`) | Cấp 2 (Thành viên) |
| Thiết bị | `living_room_light` | Đèn phòng khách (LED 5mm) | `D0` (`GPIO16`) | Cấp 3 (Khách) |
| Thiết bị | `bedroom_light` | Đèn phòng ngủ (LED 5mm Active-LOW) | `D4` (`GPIO2`) | Cấp 3 (Khách) |
| Cảm biến | `dht11` | Nhiệt độ (°C) & Độ ẩm không khí (%) | `D2` (`GPIO4`) | Mọi cấp đã đăng nhập |
| Cảm biến | `soil_moisture` | Độ ẩm đất (LM393 + YL-69, nguồn 3.3V) | `A0` (`ADC0`) | Mọi cấp đã đăng nhập |
| Cảm biến | `ky037` | Cảm biến âm thanh / tiếng vỗ tay (`DO`) | `D5` (`GPIO14`) | Mọi cấp đã đăng nhập |

---

## 2. Kiến trúc Tổng quan

- **Backend (`backend/`):** FastAPI + SQLite 3NF (chế độ `WAL`) + bộ đồng bộ thời gian thực `SSE` (`/api/events`) & `WebSocket` (`/ws/live`), cầu nối MQTT tới ESP8266, phân quyền phiên 3 tầng (RBAC + OTP Gmail + mã mời QR dùng một lần), bộ xử lý giọng nói tiếng Việt (Gemini Live `Aoede` + STT/NLU cục bộ + Echo Guard), và bộ máy Tự động hóa (luật đơn, luật tổ hợp `AND`/`OR`, lịch lặp theo thứ, bộ hẹn giờ đếm ngược).
- **Web Dashboard & Mobile Web (`web/`):** Mô hình ngôi nhà 3D tương tác (Three.js + `web/models/smarthome_villa.glb`), bảng điều khiển thiết bị/cảm biến, trang Tự động hóa (`/automation`), Quản lý xác thực (`/auth`), Nhật ký hệ thống (`/logs`), Mô phỏng phần cứng (`/wokwi`) và giao diện Mobile Web (`/app`).
- **Ứng dụng Android (`app/`):** Jetpack Compose (Kotlin) với cổng đăng nhập bắt buộc, quét mã QR khách, điều khiển 6 thiết bị, thẻ cảm biến DHT11 / độ ẩm đất / KY-037 và trợ lý giọng nói tiếng Việt.
- **Firmware & Phần cứng (`firmware/`, `hardware/`):** Mã nguồn Arduino C++ cho ESP8266 (`firmware/esp8266_smarthome/esp8266_smarthome.ino`), mạch PCB 1 lớp DIY KiCad (`100 × 80 mm`, 0 lỗi DRC/ERC), mô hình nhà Mica cắt laser FreeCAD (19 mảnh, 0 va chạm 3D) và hợp đồng đấu nối 40 dây chuẩn hóa (`hardware/wiring_contract.py`).

---

## 3. Cấu trúc Thư mục

```text
.
├── backend/                # FastAPI server, API routers, Auth RBAC, Voice STT/NLU, Automation engine, SQLite data
├── web/                    # Web 3D Digital Twin UI, CSS/JS, mô hình 3D (.glb), Mobile Web (web/mobile/), redirect (web/public/)
├── app/                    # Ứng dụng Android gốc (Kotlin + Jetpack Compose, cấu hình Lightbuild)
├── firmware/               # Firmware ESP8266 NodeMCU v2 (esp8266_smarthome/) và sơ đồ Wokwi (wokwi/)
├── hardware/
│   ├── kicad/              # Thiết kế PCB Hub 1 lớp DIY (smarthome_hub/) & bản lắp ghép 3D (smarthome_assembly/)
│   ├── mica/               # Mô hình vỏ nhà Mica 3mm tham số hóa trên FreeCAD (.FCStd + script kiểm định)
│   ├── blender/            # Cảnh lắp ghép 3D dây nối (system_wired_assembly.glb)
│   └── wiring_contract.py  # Nguồn sự thật duy nhất (SSOT) cho 40 dây nối & 10 chân ESP8266
├── docs/
│   ├── HARDWARE_BUILD_GUIDE.md  # Chỉ mục chế tạo PCB, cắt Mica & đấu nối phần cứng
│   ├── phan_cung/          # Bản in 1:1 Toner Transfer, bản vẽ DXF/PDF A3/A4, bảng đấu nối, BOM
│   ├── kien_truc/          # Sơ đồ kiến trúc tương tác HTML (/architecture, /archify)
│   └── screenshots/        # Thư mục ảnh chụp màn hình phát hành v1.0
├── tests/                  # Bộ kiểm thử tự động pytest, E2E & kiểm thử chính sách giọng nói
├── scripts/                # Tiện ích di trú SQLite, sao lưu, dịch vụ chạy nền & kiểm tra phần cứng
├── test_audio/             # Mẫu âm thanh tiếng Việt phục vụ kiểm thử giọng nói
├── USER_GUIDE.md           # Hướng dẫn sử dụng tiếng Việt đầy đủ
├── KNOWN_ISSUES.md         # Danh mục các vấn đề nhỏ đã biết (hoãn sau v1.0)
└── CHANGELOG.md            # Nhật ký phát hành phiên bản v1.0
```

---

## 4. Yêu cầu Hệ thống & Cài đặt

### Yêu cầu tối thiểu
- **Python 3.11+** (khuyến nghị môi trường Conda/venv có sẵn `pip`).
- **Biến môi trường:** Tạo tệp `.env` ở thư mục gốc (không commit lên Git) với `GEMINI_API_KEY` (tùy chọn cấu hình `SMTP_USER`, `GMAIL_APP_PASSWORD` cho OTP Gmail và `MQTT_BROKER_HOST` cho ESP8266).
- **Tùy chọn biên dịch phần cứng / Android:**
  - `arduino-cli` với lõi `esp8266:esp8266:nodemcuv2` và thư viện `PubSubClient`, `ArduinoJson`, `DHT sensor library`.
  - `lightbuild` (JDK 17, Android SDK) cho `app/`.

### Cài đặt phụ thuộc Python
```bash
pip install -r requirements.txt
```

---

## 5. Lệnh Chạy, Biên dịch và Kiểm thử

### Khởi động máy chủ Backend + Web Dashboard
```bash
python -X utf8 -m uvicorn backend.server:app --host 127.0.0.1 --port 8088
```
Truy cập trình duyệt tại `http://127.0.0.1:8088/` (máy tính) hoặc `http://127.0.0.1:8088/app` (giao diện di động).

### Chạy kiểm thử tự động (`pytest`)
```bash
python -m pytest -q --timeout=90 \
  tests/test_release_v1_fixes_20261123.py \
  tests/test_hw_contract_6devices_20261120.py \
  tests/test_challenger_m11_vercel_routing.py \
  tests/test_permanent_server_20261115.py \
  tests/test_autotool_20261122.py \
  tests/test_role_permissions_v8.py \
  tests/test_m2_vietnamese_live_rag.py
```

### Biên dịch Firmware ESP8266
```bash
arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 firmware/esp8266_smarthome/esp8266_smarthome.ino
```

### Biên dịch Ứng dụng Android (`app/`)
```bash
cd app
lightbuild --plain build app
```

### Đóng gói Docker
```bash
docker compose up --build -d
```

---

## 6. Tài liệu Phát hành `v1.0`

- [Hướng dẫn sử dụng (Tiếng Việt)](USER_GUIDE.md) — Tài khoản 3 cấp, mời QR, Web 3D, Tự động hóa, lệnh giọng nói, Android & Wokwi.
- [Hướng dẫn chế tạo & đấu nối phần cứng](docs/HARDWARE_BUILD_GUIDE.md) — Chỉ mục KiCad PCB, cắt laser Mica, BOM linh kiện & sơ đồ 40 dây nối.
- [Các vấn đề đã biết (`KNOWN_ISSUES.md`)](KNOWN_ISSUES.md) — Danh mục giới hạn nhỏ không ảnh hưởng vận hành lõi, hoãn sang sau `v1.0`.
- [Nhật ký phát hành (`CHANGELOG.md`)](CHANGELOG.md) — Tổng hợp các nhánh tích hợp, bản vá và tái cấu trúc `v1.0`.

---

## 7. Thư viện Ảnh chụp Màn hình Phát hành

Thư mục ảnh chụp tuyển chọn cho bản phát hành `v1.0` được lưu tại [`docs/screenshots/`](docs/screenshots/) với bộ ảnh minh họa chuẩn:

| Tệp dự kiến trong `docs/screenshots/` | Nội dung minh họa |
| :--- | :--- |
| `01_web_dashboard_3d.png` | Giao diện Web Dashboard 3D Digital Twin & 6 thiết bị |
| `02_web_automation.png` | Trang Tự động hóa (`/automation`): luật `AND`/`OR`, lịch tuần & hẹn giờ |
| `03_web_auth_rbac.png` | Trang Quản lý Phiên & Phân quyền 3 cấp (`/auth`) |
| `04_web_wokwi_hardware.png` | Trang Mô phỏng Phần cứng 10 chân ESP8266 (`/wokwi`) |
| `05_web_logs_owner.png` | Trang Nhật ký Hệ thống dành riêng cho Chủ nhà (`/logs`) |
| `06_android_home_devices.png` | Ứng dụng Android gốc: màn hình chính, cảm biến & 6 thiết bị |
| `07_android_voice_qr.png` | Ứng dụng Android gốc: trợ lý giọng nói tiếng Việt & quét mã QR |
| `08_hardware_pcb_mica.png` | Bố trí mạch PCB DIY `100 × 80 mm` & mô hình lắp ghép Mica |
