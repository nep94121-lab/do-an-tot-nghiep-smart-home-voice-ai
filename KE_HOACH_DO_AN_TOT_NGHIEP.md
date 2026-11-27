# 📋 HỒ SƠ & LỘ TRÌNH ĐỒ ÁN TỐT NGHIỆP (CỬ NHÂN ĐIỆN TỬ – VIỄN THÔNG)

**Đề tài:** Hệ thống Nhà thông minh điều khiển bằng Giọng nói AI thời gian thực, Phân quyền 3 tầng (RBAC), Tự động hóa 2 Bể (Hẹn giờ & Luật liên động) kết hợp Bản sao số 3D (Digital Twin) trên mạch **PCB Hub DIY v3 (`100 × 80 mm`, không dùng breadboard)** và Vi điều khiển **NodeMCU ESP8266 v2 Amica (`48.26 × 25.40 mm`, CP2102)**.
**Tác giả / Admin Cấp 1:** Nguyễn Tuấn Anh

> **Chốt kiến trúc phần cứng cuối cùng (PCB-Direct SSOT):**
> - **6 thiết bị chấp hành + 3 cảm biến khóa cứng** trên 10 chân NodeMCU ESP8266 v2 Amica (`D0–D8`, `A0`): Cửa chính Servo SG90 (`D1`), Đèn phòng khách (`D0`), Đèn phòng ngủ Active-LOW (`D4`), Bơm tưới cây Relay 1 (`D6`), Còi báo động 5V qua `Q1 S8050` (`D8`), Loa phản hồi PAM8403 + Relay 2 (`D7`/`D3`), Cảm biến `DHT11` (`D2`), Độ ẩm đất `LM393 + YL-69` (`A0`), Âm thanh `KY-037` (`D5`).
> - **100% PCB-Direct (KHÔNG dùng Breadboard trắng):** Toàn bộ **`C1–C9` (kể cả `C8 100 nF` & `C9 100 µF 16V`) và `D1–D2 (1N4007)` được hàn trực tiếp trên PCB Hub DIY v3 (`100 × 80 × 1.6 mm`, `51 footprints`, `0 ERC / 0 DRC`)** — xem [`docs/phan_cung/diy_pcb/`](docs/phan_cung/diy_pcb/).
> - **40/40 dây nối thực tế `<= 30 cm` (`3.84 – 27.48 cm`)** — xem [`docs/phan_cung/WIRE_LIST_LENGTHS.md`](docs/phan_cung/WIRE_LIST_LENGTHS.md), [`docs/phan_cung/WIRING_TABLE.md`](docs/phan_cung/WIRING_TABLE.md) và [`docs/phan_cung/DIMENSIONS_AUDIT.md`](docs/phan_cung/DIMENSIONS_AUDIT.md).
> - **Các ý tưởng ban đầu đã loại bỏ (`legacy — không dùng`):** Bảng cắm Breadboard trắng, Quạt trần (`fan`), Điều hòa 220V (`ac`), Mắt thu/phát hồng ngoại (`IR / VS1838B`).

---

## PHẦN 1: NHỮNG GÌ ĐÃ LÀM XONG 100% (ĐÃ CÓ & CHẠY ỔN ĐỊNH)

### 1.1. Lõi Điều Khiển & Phân Quyền 3 Tầng (`backend/`)
- [x] **Kiến trúc Phân quyền 3 Tầng (RBAC):**
  - **Tầng 1 (Admin tối cao — Nguyễn Tuấn Anh):** Toàn quyền điều khiển, luật IF-ELSE áp dụng toàn nhà, không ai được hủy quyền người do Tầng 1 cấp, không ai được đè/xóa/vướng khung giờ hẹn giờ của Tầng 1.
  - **Tầng 2 (Thành viên gia đình):** Có **Bể lệnh riêng** và **Lịch hẹn giờ riêng** cho từng người; được cấp/hủy quyền cho Tầng 3 (trừ người do Tầng 1 cấp); không được hủy cùng cấp; khi gọi Reset chỉ xóa bể riêng của chính mình.
  - **Tầng 3 (Khách):** Mặc định chỉ được gọi lệnh đóng/mở cố định cơ bản (đèn phòng khách, đèn phòng ngủ), mời qua mã QR dùng một lần, không được đổi lệnh, không được đặt luật IF-ELSE, không được hẹn giờ.
- [x] **Bể 1 — Bể Hẹn Giờ & Lịch Tuần (`active_timers`):**
  - Mặc định hẹn giờ **1 lần rồi tự dừng** (`repeat='once'`). Tự hiểu khi nói *"hàng ngày"*, *"hàng tuần"*, *"hàng giờ"*, *"hàng tháng"*.
- [x] **Bể 2 — Bể Luật Động & Ngôn Ngữ (`user_pools`):**
  - Đổi từ (`word_mappings`), Đổi khẩu lệnh (`aliases`), Luật liên động `IF - THEN - ELSE` tổ hợp `AND`/`OR` kèm phát hiện chu trình DFS.

### 1.2. Giọng Nói AI Tiếng Việt, RAG & Bản Sao Số 3D (`web/`)
- [x] **Trợ lý Giọng nói Gemini Live Tiếng Việt (`Aoede`):** Xử lý giọng nói thời gian thực qua Web/Android + Echo Guard + STT/NLU cục bộ.
- [x] **Mô hình Ngôi nhà 3D Digital Twin (`web/house3d.js`, `web/models/smarthome_villa.glb`):**
  - Hiển thị trực quan **6 thiết bị + 3 cảm biến khóa cứng** cùng **40 tuyến dây nối 3D thực tế** (đồng bộ từ `wiring_contract.json`, không breadboard) và đồng bộ thời gian thực qua WebSocket/SSE.
- [x] **Trang Hướng dẫn Đấu nối Phần cứng (`/wokwi`):**
  - Mặc định hiển thị **Sơ đồ PCB 2D trực tiếp** (zero breadboard), chế độ hướng dẫn từng bước `Bước 1/40 .. 40/40`, bảng 40 dây tìm kiếm/sắp xếp theo chiều dài `cm` và bảng linh kiện bảo vệ `C1–C9`, `D1–D2`.

---

## PHẦN 2: PHẦN CỨNG — BẢN CHỐT PCB-DIRECT (`Hub DIY v3`) & LINH KIỆN

### 2.1. Phần cứng Chính thức (Đang sử dụng 100%)
- [x] **01 Mạch vi điều khiển `NodeMCU ESP8266 v2 Amica` (ESP-12E, CP2102, `48.26 × 25.40 mm`, hàng chân 0.9")** — cắm trực tiếp vào đế `U1/U2` trên PCB Hub.
- [x] **01 Mạch `PCB Hub Trung Tâm DIY v3` (`100 × 80 × 1.6 mm`, 1 lớp B.Cu, `51 footprints`, `0 ERC / 0 DRC`)** — hàn sẵn **`R1–R10`, `Q1 (S8050)`, `C1–C9` (kể cả `C8 100 nF` & `C9 100 µF 16V`), `D1–D2 (1N4007)`, `D3`, `J1–J15`, `U1–U2`, `JP1–JP7`**. Xem hồ sơ gia công tại [`docs/phan_cung/diy_pcb/`](docs/phan_cung/diy_pcb/).
- [x] **6 Thiết bị chấp hành:** Servo `SG90` (`D1`), 2 LED 5mm (`D0`, `D4` Active-LOW), Relay 1 xanh + Máy bơm mini 3–6V (`D6`), Còi 5V `TMB12A05` (`D8` qua `Q1`), Relay 2 đỏ opto + `PAM8403` + Loa tròn mini 28mm (`D7`/`D3`).
- [x] **3 Cảm biến:** `DHT11` (`D2`), Độ ẩm đất `LM393 + YL-69` (`A0`, nguồn `3.3V`), Cảm biến âm thanh `KY-037/038` (`D5`, nguồn `3.3V`).
- [x] **Bộ 40 dây nối chuẩn (`10 / 20 / 30 cm`, 40/40 `<= 30 cm`)** & nguồn ngoài `5V 2A` (`J1`): xem [`docs/phan_cung/WIRE_LIST_LENGTHS.md`](docs/phan_cung/WIRE_LIST_LENGTHS.md) và [`docs/phan_cung/DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md`](docs/phan_cung/DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md).
- [x] **Vỏ nhà Mica 3mm cắt Laser & Vỏ nhà In 3D v2 lắp mộng không vít/keo (`180×200×250 mm`):** xem [`docs/HARDWARE_BUILD_GUIDE.md`](docs/HARDWARE_BUILD_GUIDE.md) và [`hardware/in 3 d/README.md`](hardware/in%203%20d/README.md).

### 2.2. Ghi chú Lịch sử — Hạng mục đã loại bỏ (`legacy — không dùng`)
- **Bảng cắm Breadboard 400 lỗ màu trắng:** `legacy (không dùng)` — đã thay thế hoàn toàn bằng mạch **PCB Hub DIY v3 (`100 × 80 mm`)**.
- **Bộ thu/phát Hồng ngoại (`VS1838B`, `IR LED 940nm`), Quạt (`fan`), Điều hòa (`ac`):** `legacy (không dùng)` — không có trong hợp đồng khóa cứng 6 thiết bị + 3 cảm biến, firmware, PCB hay mô hình 3D.

---

## PHẦN 3: PHẦN MỀM & HỆ THỐNG — TRẠNG THÁI HOÀN THIỆN

- [x] **Backend Server (`backend/server.py`):** FastAPI + SQLite WAL + MQTT + SSE/WebSocket + Auth RBAC 3 tầng + OTP Gmail + QR khách.
- [x] **Web Dashboard (`/`), Tự động hóa (`/automation`), Xác thực (`/auth`), Nhật ký (`/logs`), Phần cứng PCB-Direct (`/wokwi`), Mobile PWA (`/app`).**
- [x] **Ứng dụng Android gốc (`app/`):** Jetpack Compose (Kotlin) đồng bộ 6 thiết bị + 3 cảm biến + giọng nói tiếng Việt.
- [x] **Firmware ESP8266 (`firmware/esp8266_smarthome/esp8266_smarthome.ino`) & Script nạp USB 1 lệnh (`hardware/flash_and_setup.ps1`):** Hỗ trợ cấu hình Wi-Fi runtime an toàn qua USB (xem [`docs/phan_cung/HUONG_DAN_NAP_FIRMWARE_USB.md`](docs/phan_cung/HUONG_DAN_NAP_FIRMWARE_USB.md)), hoạt động độc lập an toàn khi mất kết nối máy chủ (`main_door` tự đóng, `alarm_siren` tự tắt).
