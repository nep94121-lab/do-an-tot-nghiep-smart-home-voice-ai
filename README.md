# Smart Home Voice AI `v1.0` — Trợ lý Nhà Thông Minh Giọng Nói Tiếng Việt

Trợ lý AI điều khiển nhà thông minh phản hồi tức thì bằng **100% tiếng Việt** (đầu vào và đầu ra chỉ sử dụng tiếng Việt), tích hợp **FastAPI Backend**, **Web 3D Digital Twin (Three.js)**, **ứng dụng Android gốc (Jetpack Compose)** và phần cứng **PCB-Direct Hub DIY v3 (`100 × 80 × 1.6 mm`, không dùng breadboard trắng)** cùng **NodeMCU ESP8266 v2 Amica (`48.26 × 25.40 mm`, CP2102)** theo hợp đồng khóa cứng **6 thiết bị chấp hành + 3 cảm biến**.

---

## 1. Phạm vi Phần cứng Khóa cứng (6 Thiết bị + 3 Cảm biến · PCB-Direct)

Hệ thống khóa cứng đúng 6 thiết bị chấp hành và 3 cảm biến trên 10 chân **NodeMCU ESP8266 v2 Amica (`48.26 × 25.40 mm`, hàng chân 0.9" — không phải v3 LoLin)** cắm trực tiếp trên mạch **PCB Hub DIY v3 (`100 × 80 × 1.6 mm`, `51 footprints`, `0 ERC / 0 DRC`)** với **toàn bộ `C1–C9` (kể cả `C8 100 nF` & `C9 100 µF 16V`) và `D1–D2 (1N4007)` hàn trực tiếp trên PCB**, và **40/40 dây nối `<= 30 cm` (`3.84 – 27.48 cm`)**. **Không dùng breadboard trắng; không hỗ trợ quạt (`fan`), điều hòa (`ac`) hay hồng ngoại (`IR` / `VS1838B`).**

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
- **Web Dashboard & Mobile Web (`web/`):** Mô hình ngôi nhà 3D tương tác (Three.js + `web/models/smarthome_villa.glb` + 40 tuyến dây nối 3D thực tế từ `wiring_contract.json`), bảng điều khiển thiết bị/cảm biến, trang Tự động hóa (`/automation`), Quản lý xác thực (`/auth`), Nhật ký hệ thống (`/logs`), Hướng dẫn đấu nối PCB-Direct từng bước (`/wokwi`, mặc định Sơ đồ PCB 2D không breadboard) và giao diện Mobile Web (`/app`).
- **Ứng dụng Android (`app/`):** Jetpack Compose (Kotlin) với cổng đăng nhập bắt buộc, quét mã QR khách, điều khiển 6 thiết bị, thẻ cảm biến DHT11 / độ ẩm đất / KY-037 và trợ lý giọng nói tiếng Việt.
- **Firmware & Phần cứng (`firmware/`, `hardware/`):** Mã nguồn Arduino C++ cho ESP8266 (`firmware/esp8266_smarthome/esp8266_smarthome.ino`), mạch PCB 1 lớp DIY v3 KiCad (`100 × 80 mm`, `51 footprints`, `C1–C9` & `D1–D2` trên bo, 0 lỗi DRC/ERC), mô hình nhà Mica / In 3D v2 FreeCAD (0 va chạm 3D) và hợp đồng đấu nối 40 dây `<= 30 cm` (`hardware/wiring_contract.py`, `hardware/wire_lengths.json`, `hardware/component_dimensions_ssot.py`).

---

## 3. Cấu trúc Thư mục

```text
.
├── backend/                # FastAPI server, API routers, Auth RBAC, Voice STT/NLU, Automation engine, SQLite data
├── web/                    # Web 3D Digital Twin UI, CSS/JS, mô hình 3D (.glb), Mobile Web (web/mobile/), redirect (web/public/)
├── app/                    # Ứng dụng Android gốc (Kotlin + Jetpack Compose, cấu hình Lightbuild)
├── firmware/               # Firmware ESP8266 NodeMCU v2 Amica (esp8266_smarthome/) và sơ đồ Wokwi (wokwi/)
├── hardware/
│   ├── kicad/              # Thiết kế PCB Hub 1 lớp DIY v3 (smarthome_hub/, 51 footprints, C8/C9 trên bo) & bản lắp ghép 3D
│   ├── mica/               # Mô hình vỏ nhà Mica 3mm tham số hóa trên FreeCAD (.FCStd + script kiểm định)
│   ├── in 3 d/             # Bộ tệp In 3D v2 nhẹ hóa lắp mộng không vít/keo/support (.3mf cài sẵn 9% gyroid, 0 đồ trang trí)
│   ├── blender/            # Cảnh lắp ghép 3D dây nối (system_wired_assembly.glb)
│   ├── component_dimensions_ssot.py # SSOT kích thước datasheet (NodeMCU v2 Amica 48.26x25.40 mm + 25 linh kiện)
│   ├── wire_lengths.json   # Tọa độ đi dây 3D & chiều dài 40 dây (3.84–27.48 cm, 40/40 <= 30 cm)
│   └── wiring_contract.py  # Nguồn sự thật duy nhất (SSOT) cho 40 dây nối & 10 chân ESP8266
├── docs/
│   ├── HARDWARE_BUILD_GUIDE.md  # Chỉ mục chế tạo PCB-direct, cắt Mica / In 3D & đấu nối phần cứng
│   ├── phan_cung/          # Bản in 1:1 Toner Transfer (diy_pcb/), DXF/PDF A3/A4, WIRING_TABLE, WIRE_LIST_LENGTHS, DIMENSIONS_AUDIT
│   ├── kien_truc/          # Sơ đồ kiến trúc tương tác HTML (/architecture, /archify)
│   └── screenshots/        # Thư mục ảnh chụp màn hình phát hành v1.0
├── tests/                  # Bộ kiểm thử tự động pytest, E2E & kiểm thử chính sách giọng nói
├── scripts/                # Tiện ích di trú SQLite, sao lưu, xuất wiring_contract.json & sinh sơ đồ 2D
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
  tests/test_wiring_guide_contract_parity.py \
  tests/test_wiring_guide_ui.py \
  tests/test_challenger_m11_vercel_routing.py \
  tests/test_permanent_server_20261115.py \
  tests/test_autotool_20261122.py \
  tests/test_role_permissions_v8.py \
  tests/test_m2_vietnamese_live_rag.py
```

### Biên dịch & Nạp Firmware ESP8266 qua USB
```powershell
# Kiểm tra toolchain, driver CP210x/CH340, cổng COM và biên dịch khô (không nạp)
powershell -NoProfile -ExecutionPolicy Bypass -File hardware\flash_and_setup.ps1 -DryRun

# Nạp firmware qua USB + cấu hình Wi-Fi runtime an toàn (ẩn mật khẩu) + tự kiểm tra
powershell -NoProfile -ExecutionPolicy Bypass -File hardware\flash_and_setup.ps1
```
Xem hướng dẫn chi tiết từng bước và bảng xử lý sự cố tại [Hướng dẫn nạp Firmware & cài Wi-Fi ESP8266 qua USB](docs/phan_cung/HUONG_DAN_NAP_FIRMWARE_USB.md).

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

## 6. Tài liệu Phát hành `v1.0` & Hồ sơ Phần cứng PCB-Direct

- [Hướng dẫn sử dụng (Tiếng Việt)](USER_GUIDE.md) — Tài khoản 3 cấp, mời QR, Web 3D, Tự động hóa, lệnh giọng nói, Android & Wokwi.
- [Hướng dẫn chế tạo & đấu nối phần cứng](docs/HARDWARE_BUILD_GUIDE.md) — Chỉ mục KiCad PCB DIY v3 (không breadboard), cắt laser Mica / In 3D v2, BOM linh kiện & sơ đồ 40 dây nối.
- [Hồ sơ Mạch PCB Hub DIY v3 (`docs/phan_cung/diy_pcb/`)](docs/phan_cung/diy_pcb/) — Ảnh render 2D/3D KiCad (`51 footprints`, `C1–C9` gồm `C8`/`C9` & `D1–D2` trên bo, `0 ERC / 0 DRC`), bản in 1:1 Toner Transfer, `bom.csv`, `DIY_GUIDE.md`.
- [Danh sách 40 dây nối & chiều dài thực tế 3D (`WIRE_LIST_LENGTHS.md`)](docs/phan_cung/WIRE_LIST_LENGTHS.md) — 40/40 dây `<= 30 cm` (`3.84 – 27.48 cm`) và tổng hợp mua dây chuẩn `10 / 20 / 30 cm`.
- [Kiểm định kích thước Datasheet (`DIMENSIONS_AUDIT.md`)](docs/phan_cung/DIMENSIONS_AUDIT.md) — Kích thước thực tế NodeMCU v2 Amica (`48.26 × 25.40 mm`) và 25 linh kiện phần cứng.
- [Hướng dẫn nạp Firmware & cấu hình Wi-Fi ESP8266 qua USB](docs/phan_cung/HUONG_DAN_NAP_FIRMWARE_USB.md) — Nạp 1 lệnh bằng `hardware/flash_and_setup.ps1`, kiểm tra driver CP2102/CH340, cấu hình Wi-Fi runtime không lộ mật khẩu & xử lý sự cố.
- [Bộ tệp In 3D Vỏ Nhà v2 Nhẹ Hóa & Phụ Kiện Ngàm (`hardware/in 3 d/`)](hardware/in%203%20d/README.md) — Vỏ nhà lắp mộng không vít/keo/support tối ưu nhẹ hóa (cài sẵn trong `.3mf`: `9% gyroid`, `2 perimeters` / `3 perimeters` cho ngàm nối & cụm Servo, `3 lớp đỉnh/đáy`, vách coffered `2.2 mm` khoét tổ ong, giữ kín vùng relay/PSU, 0 đồ trang trí; xem số bàn in & khối lượng PLA thực tế tại `hardware/in 3 d/README.md` & `manifest.json`).
- [Các vấn đề đã biết (`KNOWN_ISSUES.md`)](KNOWN_ISSUES.md) — Danh mục giới hạn nhỏ không ảnh hưởng vận hành lõi, hoãn sang sau `v1.0`.
- [Nhật ký phát hành (`CHANGELOG.md`)](CHANGELOG.md) — Tổng hợp các nhánh tích hợp, bản vá và tái cấu trúc `v1.0`.

---

## 7. Thư viện Ảnh chụp Màn hình Phát hành

Thư mục ảnh chụp tuyển chọn cho bản phát hành `v1.0` được lưu tại [`docs/screenshots/`](docs/screenshots/) với đầy đủ 13 ảnh minh họa thực tế:

| Ảnh chụp (`docs/screenshots/`) | Nội dung minh họa |
| :--- | :--- |
| [`01_dashboard_3d_desktop_1440x900.png`](docs/screenshots/01_dashboard_3d_desktop_1440x900.png) | Giao diện Web Dashboard 3D Digital Twin & 6 thiết bị (`1440x900`) |
| [`02_dashboard_3d_desktop_1366x768.png`](docs/screenshots/02_dashboard_3d_desktop_1366x768.png) | Giao diện Web Dashboard 3D Digital Twin trên màn hình laptop (`1366x768`) |
| [`03_dashboard_3d_mobile_390x844.png`](docs/screenshots/03_dashboard_3d_mobile_390x844.png) | Giao diện Web Dashboard đáp ứng di động (`390x844`) |
| [`04_automation_panel_1440x900.png`](docs/screenshots/04_automation_panel_1440x900.png) | Trang Tự động hóa (`/automation`): luật `AND`/`OR`, lịch tuần & hẹn giờ |
| [`05_wokwi_circuit_1440x900.png`](docs/screenshots/05_wokwi_circuit_1440x900.png) | Trang Hướng dẫn Đấu nối PCB-Direct 10 chân ESP8266 & PCB Hub 100×80mm (`/wokwi`) |
| [`06_auth_rbac_1440x900.png`](docs/screenshots/06_auth_rbac_1440x900.png) | Trang Quản lý Phiên & Phân quyền 3 cấp (`/auth`) |
| [`07_logs_audit_1440x900.png`](docs/screenshots/07_logs_audit_1440x900.png) | Trang Nhật ký Hệ thống dành riêng cho Chủ nhà (`/logs`) |
| [`08_mobile_pwa_390x844.png`](docs/screenshots/08_mobile_pwa_390x844.png) | Giao diện Ứng dụng Web Di động PWA (`/app`, `390x844`) |
| [`09_android_auth_gate.png`](docs/screenshots/09_android_auth_gate.png) | Ứng dụng Android gốc: cổng xác thực khi chưa đăng nhập & nút Quét mã QR |
| [`10_android_home_live.png`](docs/screenshots/10_android_home_live.png) | Ứng dụng Android gốc: màn hình chính & lưới 4 thông số cảm biến thực |
| [`11_android_devices_6locked.png`](docs/screenshots/11_android_devices_6locked.png) | Ứng dụng Android gốc: danh sách thiết bị theo hợp đồng khóa cứng 6 thiết bị |
| [`12_android_voice_vi.png`](docs/screenshots/12_android_voice_vi.png) | Ứng dụng Android gốc: trợ lý giọng nói tiếng Việt đồng bộ trực tiếp máy chủ |
| [`13_hardware_wiring_2d.png`](docs/screenshots/13_hardware_wiring_2d.png) | Sơ đồ đấu nối tổng thể 2D PCB-Direct 40 dây & 15 đầu nối PCB Hub DIY v3 (`100×80 mm`) |
| `08_hardware_pcb_mica.png` | Bố trí mạch PCB DIY `100 × 80 mm` & mô hình lắp ghép Mica |
