# Smart Home Voice AI (`v3.8.0` / `v1.0`) — Trợ Lý Nhà Thông Minh Giọng Nói Tiếng Việt

> **TRẠNG THÁI HOÀN THIỆN HỆ THỐNG — SẴN SÀNG CẮM PHẦN CỨNG LÀ CHẠY:**
> Toàn bộ **máy chủ Backend FastAPI (`backend/`)**, **giao diện Web 3D Digital Twin & Mobile PWA (`web/`)**, **ứng dụng Android gốc (`app/`)** và **firmware ESP8266 (`firmware/`)** đã **hoàn thiện 100%** và được kiểm thử đầy đủ.
> **Chỉ còn duy nhất bước cuối cùng ở hiện trường:** cắm bo mạch **NodeMCU ESP8266 v2 Amica** thật qua cáp Micro-USB, chạy **1 lệnh PowerShell** nạp firmware & nhập Wi-Fi lúc chạy (runtime, lưu vào LittleFS, không bao giờ lưu mật khẩu trong mã nguồn), gắn lên mạch **PCB Hub DIY v3** và cấp nguồn `5V 2A` là hệ thống hoạt động hoàn chỉnh.
>
> **Hướng dẫn nạp USB & cài Wi-Fi runtime thống nhất (Đọc ngay tại đây):**
> [`docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md`](docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md)

Trợ lý AI điều khiển nhà thông minh phản hồi tức thì bằng **100% tiếng Việt** (giọng `Aoede` duy nhất trên `gemini-3.8-live`), tích hợp **FastAPI Backend (`v3.8.0`) + SQLite WAL (25 bảng)**, **Web 3D Digital Twin (Three.js `r128`)**, **ứng dụng Android gốc (Kotlin + Jetpack Compose)**, **phần cứng PCB-Direct Hub DIY v3 (`100 × 80 × 1.6 mm`, không dùng breadboard trắng)** cùng **NodeMCU ESP8266 v2 Amica (`48.26 × 25.40 mm`, CP2102)** và **bộ vỏ nhà in 3D lắp mộng `agyhw14` (`16` bàn in, `660.64 g` PLA)**.

---

## 1. Hợp Đồng Phần Cứng Khóa Cứng (14 Module Vật Lý $\rightarrow$ 6 Thiết Bị + 3 Cảm Biến)

Hệ thống gồm **14 khối/module vật lý ngoài bo** (cộng `NodeMCU v2 Amica` và `PCB Hub DIY v3` thành `16` thành phần trong mô hình 3D) ánh xạ sang đúng **6 thiết bị chấp hành + 3 cảm biến** trên 10 chân **NodeMCU ESP8266 v2 Amica (`48.26 × 25.40 mm`, hàng chân `0.9"` — không dùng v3 LoLin)** cắm trực tiếp lên mạch **PCB Hub DIY v3 (`100 × 80 × 1.6 mm`, `51 footprints`, `0 ERC / 0 DRC`)** với **toàn bộ `C1–C9` (gồm `C8 100 nF` & `C9 100 µF 16V`) và `D1–D2 (1N4007)` hàn trực tiếp trên PCB**, cùng **40/40 dây nối `<= 30 cm` (`3.84 – 27.48 cm`)**.
**Chính sách phạm vi chốt:** **Không dùng breadboard trắng; không hỗ trợ quạt (`fan`), điều hòa (`ac`) hay hồng ngoại (`IR` / `VS1838B`).** Xem bảng ánh xạ chi tiết 14 module tại [`docs/phan_cung/TONG_QUAN_PHAN_CUNG_VA_IN_3D.md`](docs/phan_cung/TONG_QUAN_PHAN_CUNG_VA_IN_3D.md).

| Loại | Mã định danh | Tên hiển thị & Khối vật lý đi kèm | Chân ESP8266 | Quyền tối thiểu |
| :--- | :--- | :--- | :---: | :--- |
| Thiết bị | `main_door` | Cửa chính (Servo SG90 đồng trục không vít/keo) | `D1` (`GPIO5`) | Cấp 1 (Chủ nhà) |
| Thiết bị | `alarm_siren` | Còi báo động (Buzzer 5V `TMB12A05` + `Q1 S8050` + `D2`) | `D8` (`GPIO15`) | Cấp 1 (Chủ nhà) |
| Thiết bị | `garden_pump` | Bơm tưới cây (Relay 1 xanh 5V + Bơm chìm 3–6V + `D1`) | `D6` (`GPIO12`) | Cấp 2 (Thành viên) |
| Thiết bị | `speaker_amp` | Loa phản hồi (Relay 2 opto đỏ + `PAM8403` + Loa `28mm` + PWM `D3`) | `D7` (`GPIO13`) | Cấp 2 (Thành viên) |
| Thiết bị | `living_room_light` | Đèn phòng khách (LED 5mm + `R1 220Ω`) | `D0` (`GPIO16`) | Cấp 3 (Khách) |
| Thiết bị | `bedroom_light` | Đèn phòng ngủ (LED 5mm Active-LOW + `R2 220Ω` + `R7 10kΩ`) | `D4` (`GPIO2`) | Cấp 3 (Khách) |
| Cảm biến | `dht11` | Nhiệt độ (°C) & Độ ẩm không khí (%) (`DHT11` 3 chân) | `D2` (`GPIO4`) | Mọi cấp đã đăng nhập |
| Cảm biến | `soil_moisture` | Độ ẩm đất (`LM393` cấp `3.3V` + đầu dò `YL-69`) | `A0` (`ADC0`) | Mọi cấp đã đăng nhập |
| Cảm biến | `ky037` | Cảm biến âm thanh / tiếng vỗ tay (`KY-037/038 DO`, `3.3V`) | `D5` (`GPIO14`) | Mọi cấp đã đăng nhập |

---

## 2. Cấu Trúc Thư Mục Dự Án

Giữ nguyên toàn bộ các thư mục mã nguồn cốt lõi và tổ chức gọn tầng tài liệu theo nhóm chức năng rõ ràng:

```text
.
├── backend/                     # FastAPI v3.8.0, SQLite WAL (25 bảng), MQTT, SSE/WS, RBAC 3 tầng, Gemini Live Voice AI
├── web/                         # Web Dashboard 3D Digital Twin (Three.js r128), Mobile PWA (/app), /wokwi, /automation, /auth, /logs
├── app/                         # Ứng dụng Android gốc (Kotlin 2.3.20 + Jetpack Compose 1.10.4, minSdk 26, Lightbuild)
├── firmware/                    # Firmware NodeMCU ESP8266 v2 Amica (LittleFS Wi-Fi runtime + Offline FSM A1–A4) & Wokwi
├── hardware/
│   ├── flash_and_setup.ps1      # Script 1 lệnh nạp USB + nhập Wi-Fi runtime an toàn (ẩn mật khẩu) + SELF_TEST
│   ├── wiring_contract.py       # SSOT 40 dây nối, 15 đầu nối PCB J1–J15 & linh kiện bảo vệ C1–C9, D1–D2
│   ├── component_dimensions_ssot.py # SSOT kích thước datasheet 14 module + 2 bo lõi & thông số Servo SG90
│   ├── wire_lengths.json        # Chiều dài 3D thực tế 40/40 dây <= 30 cm (3.84–27.48 cm)
│   ├── kicad/                   # PCB Hub DIY v3 (100×80×1.6 mm, 51 footprints, 0 ERC / 0 DRC) & lắp ghép 3D
│   ├── mica/                    # Thiết kế vỏ nhà Mica 3mm cắt laser (FreeCAD 1.1.4)
│   ├── in 3 d/                  # Bộ in 3D v2 nhẹ hóa agyhw14: 16 bàn .3mf nhúng sẵn cấu hình, 660.64 g PLA, 0 support
│   └── blender/                 # Cảnh 3D tổng thể & 40 tuyến dây nối (Blender 5.2.2 LTS)
├── docs/
│   ├── kien_truc/               # Kiến trúc hệ thống (Mermaid), Công nghệ & Phiên bản thực đo, ERD SQLite 25 bảng, Repo Map
│   ├── huong_dan/               # Hướng dẫn thống nhất nạp USB & Wi-Fi runtime, Vận hành & Triển khai Production
│   ├── phan_cung/               # Tổng quan phần cứng & In 3D, WIRING_TABLE, WIRE_LIST_LENGTHS, DIMENSIONS_AUDIT, diy_pcb/, mica/
│   ├── bao_cao/                 # Hồ sơ Báo cáo Đồ án Tốt nghiệp (.docx / .pdf / script sinh / LOGO_SOURCES.md)
│   ├── luu_tru/                 # Tài liệu khảo sát & lịch sử giai đoạn đầu (chỉ lưu trữ, không dùng vận hành)
│   ├── screenshots/             # 13 ảnh chụp màn hình kiểm chứng Web, Mobile PWA, Android & Sơ đồ 2D
│   ├── HARDWARE_BUILD_GUIDE.md  # Chỉ mục chế tạo PCB-direct, cắt Mica / In 3D & đấu nối
│   └── TIER_PERMISSIONS.md      # Bảng phân quyền 3 tầng khóa cứng cho 6 thiết bị
├── tests/                       # Bộ kiểm thử tự động pytest (Backend, RBAC, Voice agyfix11, PCB/In 3D agyhw12–14)
├── scripts/                     # Tiện ích sinh tài liệu dây nối, kiểm định kích thước & công cụ bảo trì
├── specs/                       # Đặc tả kỹ thuật tham chiếu
├── test_audio/                  # Bộ mẫu âm thanh tiếng Việt kiểm thử giọng nói
├── USER_GUIDE.md                # Hướng dẫn sử dụng chi tiết cho người dùng cuối
├── KE_HOACH_DO_AN_TOT_NGHIEP.md # Hồ sơ tiến độ & trạng thái hoàn thiện đồ án
├── KNOWN_ISSUES.md              # Danh mục vấn đề nhỏ đã biết & giải pháp tạm thời
└── CHANGELOG.md                 # Nhật ký phát hành các phiên bản
```

---

## 3. Chỉ Mục Toàn Bộ Tài Liệu Dự Án

| Nhóm tài liệu | Tài liệu | Nội dung chính |
| :--- | :--- | :--- |
| **Cắm phần cứng & Wi-Fi** | [**Hướng dẫn nạp Firmware USB & Cài Wi-Fi Runtime**](docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md) | Quy trình 3 bước cắm USB $\rightarrow$ chạy `hardware/flash_and_setup.ps1` nhập Wi-Fi lưu LittleFS `/wifi_config.json` $\rightarrow$ cấp nguồn chạy, driver CP2102/CH340, chân boot-strap `D3/D4/D8`, xử lý sự cố |
| **Người dùng cuối** | [Hướng dẫn sử dụng (`USER_GUIDE.md`)](USER_GUIDE.md) | Phân quyền 3 cấp, mã mời QR dùng 1 lần, Web 3D `/`, Mobile `/app`, Tự động hóa `/automation`, giọng nói tiếng Việt, ứng dụng Android, `/wokwi` & chế độ ngoại tuyến |
| **Kiến trúc & Phiên bản** | [Kiến trúc hệ thống chi tiết (`KIEN_TRUC_HE_THONG.md`)](docs/kien_truc/KIEN_TRUC_HE_THONG.md) | Kiến trúc toàn bộ phân hệ Backend, SQLite WAL, MQTT, SSE/WS, Web 3D, Android, ESP8266, Gemini Live `agyfix11`, RBAC & 4 sơ đồ tuần tự Mermaid |
| **Kiến trúc & Phiên bản** | [Công nghệ & Phiên bản phần mềm (`CONG_NGHE_VA_PHIEN_BAN.md`)](docs/kien_truc/CONG_NGHE_VA_PHIEN_BAN.md) | Bảng phiên bản thực đo đầy đủ của Python, FastAPI, SQLite, Three.js, Kotlin/Compose, PlatformIO, KiCad, FreeCAD, Blender, PrusaSlicer, Playwright, Tailscale, Vercel |
| **Kiến trúc & Phiên bản** | [Sơ đồ CSDL SQLite 25 bảng (`DATABASE_SCHEMA_ERD.md`)](docs/kien_truc/DATABASE_SCHEMA_ERD.md) | Sơ đồ thực thể kết hợp (ERD Mermaid) đủ 25 bảng 3NF và cơ chế cách ly 2 bể tự động hóa |
| **Kiến trúc & Phiên bản** | [Bảng phân quyền 3 tầng (`docs/TIER_PERMISSIONS.md`)](docs/TIER_PERMISSIONS.md) · [Bản đồ mã nguồn (`REPO_MAP.md`)](docs/kien_truc/REPO_MAP.md) | Ma trận quyền 3 cấp khóa cứng 6 thiết bị & chỉ mục cấu trúc mã nguồn hiện hành |
| **Vận hành & Triển khai** | [Hướng dẫn vận hành & triển khai (`VAN_HANH_VA_TRIEN_KHAI.md`)](docs/huong_dan/VAN_HANH_VA_TRIEN_KHAI.md) | Biến môi trường `.env` (chỉ tên biến), chạy cổng `8088`, Tailscale Funnel, Vercel redirect, backup/restore SQLite WAL, `DEPLOY.lock`, quy trình `pytest` + Playwright + Android APK |
| **Phần cứng & In 3D** | [Tổng quan phần cứng 14 module & In 3D (`TONG_QUAN_PHAN_CUNG_VA_IN_3D.md`)](docs/phan_cung/TONG_QUAN_PHAN_CUNG_VA_IN_3D.md) | Bảng ánh xạ SSOT 14 module vật lý + 2 bo lõi sang 6 thiết bị + 3 cảm biến, PCB Hub DIY v3, 40 dây `<= 30 cm`, bộ in 3D 16 bàn `660.64 g` |
| **Phần cứng & In 3D** | [Chỉ mục chế tạo phần cứng (`docs/HARDWARE_BUILD_GUIDE.md`)](docs/HARDWARE_BUILD_GUIDE.md) · [Bảng 40 dây (`WIRING_TABLE.md`)](docs/phan_cung/WIRING_TABLE.md) · [Chiều dài dây (`WIRE_LIST_LENGTHS.md`)](docs/phan_cung/WIRE_LIST_LENGTHS.md) | Hồ sơ gia công KiCad [`diy_pcb/`](docs/phan_cung/diy_pcb/), kiểm định kích thước [`DIMENSIONS_AUDIT.md`](docs/phan_cung/DIMENSIONS_AUDIT.md), linh kiện [`DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md`](docs/phan_cung/DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md), bộ in 3D [`hardware/in 3 d/README.md`](hardware/in%203%20d/README.md) |
| **Firmware ESP8266** | [Tài liệu Firmware (`firmware/README.md`)](firmware/README.md) · [Bản nạp USB cho `/wokwi`](docs/phan_cung/HUONG_DAN_NAP_FIRMWARE_USB.md) | Chi tiết sơ đồ 10 chân boot-safe và cơ chế dự phòng ngoại tuyến Addendum A1–A4 |
| **Quản trị & Lịch sử** | [Hồ sơ Đồ án (`KE_HOACH_DO_AN_TOT_NGHIEP.md`)](KE_HOACH_DO_AN_TOT_NGHIEP.md) · [Vấn đề đã biết (`KNOWN_ISSUES.md`)](KNOWN_ISSUES.md) · [Nhật ký (`CHANGELOG.md`)](CHANGELOG.md) · [Kho lưu trữ cũ (`docs/luu_tru/`)](docs/luu_tru/README.md) | Trạng thái hoàn thiện tổng thể, danh mục giới hạn nhỏ fail-closed, lịch sử phát hành và tài liệu khảo sát giai đoạn đầu |

---

## 4. Khởi Chạy Nhanh (Quick Start)

### 4.1. Cài đặt phụ thuộc & khởi động máy chủ Backend (`:8088`)
```powershell
pip install -r requirements.txt
# Tạo tệp .env ở thư mục gốc (không commit Git) với GEMINI_API_KEY (xem VAN_HANH_VA_TRIEN_KHAI.md)
python -X utf8 -m uvicorn backend.server:app --host 0.0.0.0 --port 8088
```
Truy cập trình duyệt tại `http://127.0.0.1:8088/` (máy tính) hoặc `http://127.0.0.1:8088/app` (di động).

### 4.2. Nạp Firmware ESP8266 & cấu hình Wi-Fi Runtime qua USB (1 lệnh)
```powershell
# Kiểm tra toolchain PlatformIO, driver CP210x/CH340, cổng COM và biên dịch khô (không nạp)
powershell -NoProfile -ExecutionPolicy Bypass -File hardware\flash_and_setup.ps1 -DryRun

# Cắm NodeMCU ESP8266 qua cáp Micro-USB, nạp firmware + nhập Wi-Fi runtime ẩn mật khẩu + SELF_TEST
powershell -NoProfile -ExecutionPolicy Bypass -File hardware\flash_and_setup.ps1
```
Xem chi tiết từng bước và bảng khắc phục sự cố tại [`docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md`](docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md).

### 4.3. Biên dịch ứng dụng Android (`app/`) & chạy kiểm thử (`pytest`)
```powershell
# Biên dịch ứng dụng Android gốc (Kotlin 2.3.20 + Jetpack Compose, minSdk 26)
Set-Location app
lightbuild --plain build app

# Kiểm thử hồi quy phần cứng, PCB-Direct, Servo và In 3D (chạy tại thư mục gốc)
python -m pytest -q --timeout=120 \
  tests/test_hw_contract_6devices_20261120.py \
  tests/test_pcbdirect_agyhw12.py \
  tests/test_servodoor_agyhw13.py \
  tests/test_lessplastic_agyhw14.py
```

### 4.4. Tóm tắt Phần cứng PCB-Direct & Bộ In 3D `agyhw14`
- **PCB Hub DIY v3 (`100 × 80 × 1.6 mm`, 1 lớp `B.Cu`, không dùng breadboard trắng):** `51 footprints`, `0 ERC / 0 DRC`, toàn bộ `C1–C9` & `D1–D2` hàn trực tiếp trên bo.
- **Hệ thống dây nối (`40/40 <= 30 cm`):** Ngắn nhất `3.84 cm`, dài nhất `27.48 cm`, tổng `654.99 cm` (`10` sợi 10 cm, `18` sợi 20 cm, `12` sợi 30 cm).
- **Vỏ nhà In 3D v2 (`agyhw14`, `180×200×250 mm`):** **`16` bàn in `.3mf`** nhúng sẵn thông số (`9% Gyroid`, `2/3` thành, `0% support`), **`51` chi tiết / `83` bản thể**, **`660.64 g` PLA** (`-36.77%` so với `1044.86 g`), thời gian in `73g 23p 49s`, `0` va chạm 3D BRep, cơ cấu cửa Servo SG90 đồng trục dự trữ mô-men `14.56×`.

---

## 5. Thư Viện Ảnh Chụp Kiểm Chứng (`docs/screenshots/`)

| Ảnh chụp (`docs/screenshots/`) | Nội dung minh họa |
| :--- | :--- |
| [`01_dashboard_3d_desktop_1440x900.png`](docs/screenshots/01_dashboard_3d_desktop_1440x900.png) | Giao diện Web Dashboard 3D Digital Twin & 6 thiết bị (`1440×900`) |
| [`02_dashboard_3d_desktop_1366x768.png`](docs/screenshots/02_dashboard_3d_desktop_1366x768.png) | Giao diện Web Dashboard 3D Digital Twin trên màn hình laptop (`1366×768`) |
| [`03_dashboard_3d_mobile_390x844.png`](docs/screenshots/03_dashboard_3d_mobile_390x844.png) | Giao diện Web Dashboard đáp ứng di động (`390×844`) |
| [`04_automation_panel_1440x900.png`](docs/screenshots/04_automation_panel_1440x900.png) | Trang Tự động hóa (`/automation`): luật tổ hợp `AND`/`OR`, lịch tuần & hẹn giờ |
| [`05_wokwi_circuit_1440x900.png`](docs/screenshots/05_wokwi_circuit_1440x900.png) | Trang Hướng dẫn Đấu nối PCB-Direct 10 chân ESP8266 & PCB Hub `100×80 mm` (`/wokwi`) |
| [`06_auth_rbac_1440x900.png`](docs/screenshots/06_auth_rbac_1440x900.png) | Trang Quản lý Phiên & Phân quyền 3 tầng (`/auth`) |
| [`07_logs_audit_1440x900.png`](docs/screenshots/07_logs_audit_1440x900.png) | Trang Nhật ký Hệ thống dành riêng cho Chủ nhà Cấp 1 (`/logs`) |
| [`08_mobile_pwa_390x844.png`](docs/screenshots/08_mobile_pwa_390x844.png) | Giao diện Ứng dụng Web Di động PWA (`/app`, `390×844`) |
| [`09_android_auth_gate.png`](docs/screenshots/09_android_auth_gate.png) | Ứng dụng Android gốc: cổng xác thực khi chưa đăng nhập & nút Quét mã QR |
| [`10_android_home_live.png`](docs/screenshots/10_android_home_live.png) | Ứng dụng Android gốc: màn hình chính & thẻ thông số cảm biến thời gian thực |
| [`11_android_devices_6locked.png`](docs/screenshots/11_android_devices_6locked.png) | Ứng dụng Android gốc: danh sách 6 thiết bị chấp hành theo hợp đồng khóa cứng |
| [`12_android_voice_vi.png`](docs/screenshots/12_android_voice_vi.png) | Ứng dụng Android gốc: trợ lý giọng nói tiếng Việt đồng bộ máy chủ |
| [`13_hardware_wiring_2d.png`](docs/screenshots/13_hardware_wiring_2d.png) | Sơ đồ đấu nối tổng thể 2D PCB-Direct 40 dây & 15 đầu nối PCB Hub DIY v3 (`100×80 mm`) |
