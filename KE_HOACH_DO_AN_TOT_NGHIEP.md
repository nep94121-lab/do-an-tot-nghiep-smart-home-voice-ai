# Hồ Sơ & Lộ Trình Đồ Án Tốt Nghiệp (Cử Nhân Điện Tử – Viễn Thông)

**Đề tài:** Hệ thống Nhà thông minh điều khiển bằng Giọng nói AI thời gian thực, Phân quyền 3 tầng (RBAC), Tự động hóa 2 Bể (Hẹn giờ & Luật liên động) kết hợp Bản sao số 3D (Digital Twin) trên mạch **PCB Hub DIY v3 (`100 × 80 mm`, không dùng breadboard trắng)** và Vi điều khiển **NodeMCU ESP8266 v2 Amica (`48.26 × 25.40 mm`, CP2102)**.
**Tác giả / Admin Cấp 1:** Nguyễn Tuấn Anh
**Phiên bản hiện hành:** Backend API `v3.8.0` / Bản phát hành `v1.0` (`agyhw14` · `agyclean15`)

> **Trạng thái hoàn thiện 100% phần mềm & thiết kế (chỉ còn bước cắm phần cứng thật):**
> Toàn bộ máy chủ Backend (`backend/`), giao diện Web 3D Digital Twin & Mobile PWA (`web/`), ứng dụng Android gốc (`app/`), firmware ESP8266 (`firmware/`), hồ sơ mạch PCB Hub DIY v3 và bộ vỏ in 3D lắp mộng 16 bàn (`660.64 g` PLA) đã hoàn thiện và kiểm thử đầy đủ. Bước cuối cùng ngoài thực tế chỉ là cắm **NodeMCU ESP8266 v2 Amica** qua USB, chạy 1 lệnh nạp firmware & nhập Wi-Fi runtime theo [`docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md`](docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md), gắn lên PCB Hub và cấp nguồn `5V 2A`.

> **Chốt kiến trúc phần cứng cuối cùng (PCB-Direct SSOT — 14 Module Vật Lý $\rightarrow$ 6 Thiết Bị + 3 Cảm Biến):**
> - **6 thiết bị chấp hành + 3 cảm biến khóa cứng** trên 10 chân NodeMCU ESP8266 v2 Amica (`D0–D8`, `A0`): Cửa chính Servo SG90 (`D1`), Đèn phòng khách (`D0`), Đèn phòng ngủ Active-LOW (`D4`), Bơm tưới cây Relay 1 (`D6`), Còi báo động 5V qua `Q1 S8050` (`D8`), Loa phản hồi PAM8403 + Relay 2 (`D7`/`D3`), Cảm biến `DHT11` (`D2`), Độ ẩm đất `LM393 + YL-69` (`A0`), Âm thanh `KY-037` (`D5`).
> - **100% PCB-Direct (KHÔNG dùng breadboard trắng):** Toàn bộ **`C1–C9` (kể cả `C8 100 nF` & `C9 100 µF 16V`) và `D1–D2 (1N4007)` được hàn trực tiếp trên PCB Hub DIY v3 (`100 × 80 × 1.6 mm`, `51 footprints`, `0 ERC / 0 DRC`)** — xem [`docs/phan_cung/TONG_QUAN_PHAN_CUNG_VA_IN_3D.md`](docs/phan_cung/TONG_QUAN_PHAN_CUNG_VA_IN_3D.md) và [`docs/phan_cung/diy_pcb/`](docs/phan_cung/diy_pcb/).
> - **40/40 dây nối thực tế `<= 30 cm` (`3.84 – 27.48 cm`)** — xem [`docs/phan_cung/WIRE_LIST_LENGTHS.md`](docs/phan_cung/WIRE_LIST_LENGTHS.md), [`docs/phan_cung/WIRING_TABLE.md`](docs/phan_cung/WIRING_TABLE.md) và [`docs/phan_cung/DIMENSIONS_AUDIT.md`](docs/phan_cung/DIMENSIONS_AUDIT.md).
> - **Các hạng mục lịch sử đã loại bỏ (`legacy — không dùng`):** Bảng cắm breadboard trắng, Quạt trần (`fan`), Điều hòa 220V (`ac`), Mắt thu/phát hồng ngoại (`IR / VS1838B`).

---

## Phần 1: Các Phân Hệ Đã Hoàn Thiện 100%

### 1.1. Lõi Điều Khiển, SQLite WAL & Phân Quyền 3 Tầng (`backend/`)
- [x] **Backend FastAPI `v3.8.0` + SQLite 3.53.2 WAL (25 bảng 3NF):** Phục vụ đồng bộ thời gian thực `SSE` (`/api/events`), WebSocket (`/ws`), cầu nối MQTT (8 topic chuẩn) và nhật ký kiểm toán (`/logs`). Xem [`docs/kien_truc/KIEN_TRUC_HE_THONG.md`](docs/kien_truc/KIEN_TRUC_HE_THONG.md) và [`docs/kien_truc/DATABASE_SCHEMA_ERD.md`](docs/kien_truc/DATABASE_SCHEMA_ERD.md).
- [x] **Kiến trúc Phân quyền 3 Tầng (RBAC — [`docs/TIER_PERMISSIONS.md`](docs/TIER_PERMISSIONS.md)):**
  - **Cấp 1 (Chủ nhà — `ADMIN`):** Toàn quyền 6/6 thiết bị, luật/lịch toàn nhà, tạo/thu hồi mã mời QR dùng một lần bảo vệ bằng PIN PBKDF2-SHA256, xem `/logs` và `/wokwi`.
  - **Cấp 2 (Thành viên gia đình — `MEMBER`):** Điều khiển 4/6 thiết bị (khóa Cửa chính & Còi báo động), sở hữu Bể lệnh và Lịch hẹn giờ riêng, không đè lịch Cấp 1, không truy cập `/logs`.
  - **Cấp 3 (Khách — `CHILD_GUEST`):** Điều khiển 2 đèn (phòng khách, phòng ngủ), mời qua QR dùng một lần, chỉ xem trên `/automation`, bị chặn `HTTP 403` trên `/logs` và `/wokwi`.
- [x] **Tự động hóa 2 Bể:** Bể 1 (Hẹn giờ đếm ngược `repeat='once'` & lịch lặp tuần `Asia/Saigon`) và Bể 2 (Luật liên động `IF-THEN-ELSE`, luật tổ hợp đa cảm biến `AND`/`OR` + phát hiện chu trình DFS, lệnh tùy chỉnh cách ly theo `owner_user_id`).

### 1.2. Giọng Nói AI Tiếng Việt (`agyfix11`), Bản Sao Số 3D & Mobile (`web/`, `app/`)
- [x] **Trợ lý Giọng nói Gemini Live Tiếng Việt (`gemini-3.8-live`, giọng `Aoede` duy nhất):** Hỗ trợ lệnh tùy chỉnh xác nhận 1 lần (`pending_confirmations` TTL 20s), phản hồi ngắn gọn chính xác đúng chuẩn `agyfix11`, chống vọng tiếng Echo Guard và Fail-Closed an toàn.
- [x] **Mô hình Ngôi nhà 3D Digital Twin (`web/house3d.js`, `Three.js r128`, `web/models/smarthome_villa.glb`):** Hiển thị đầy đủ 14 module vật lý + PCB Hub DIY v3 + NodeMCU + 40 tuyến dây 3D thực tế, đồng bộ trạng thái `< 1 giây`, hỗ trợ chế độ Sáng/Tối.
- [x] **Trang Hướng dẫn Đấu nối Phần cứng (`/wokwi`):** Mặc định Sơ đồ PCB 2D trực tiếp (không breadboard), hướng dẫn 40 bước, bảng tìm kiếm/lọc 40 dây theo `cm` và bảng bảo vệ `C1–C9`, `D1–D2`.
- [x] **Ứng dụng Android gốc (`app/`):** Kotlin `2.3.20` + Jetpack Compose `1.10.4` (`minSdk 26`), cổng đăng nhập bắt buộc, quét mã QR khách, điều khiển 6 thiết bị, hiển thị 3 cảm biến và giọng nói tiếng Việt trực tuyến + ngoại tuyến LAN.

---

## Phần 2: Phần Cứng PCB-Direct (`Hub DIY v3`) & Bộ Vỏ In 3D (`agyhw14`)

- [x] **01 Mạch vi điều khiển `NodeMCU ESP8266 v2 Amica` (`48.26 × 25.40 mm`, CP2102, hàng chân `0.9"`):** Cắm trực tiếp vào đế `U1/U2` trên PCB Hub.
- [x] **01 Mạch `PCB Hub Trung Tâm DIY v3` (`100 × 80 × 1.6 mm`, 1 lớp `B.Cu`, `51 footprints`, `0 ERC / 0 DRC`):** Hàn trọn vẹn `R1–R10`, `Q1 (S8050)`, `C1–C9` (kể cả `C8 100 nF` & `C9 100 µF 16V`), `D1–D2 (1N4007)`, `D3`, `J1–J15`, `U1–U2`, `JP1–JP7`.
- [x] **14 Module ngoài bo ánh xạ sang 6 thiết bị chấp hành + 3 cảm biến + Nguồn `5V 2A`:** Đủ 40 dây nối `<= 30 cm` (`3.84 – 27.48 cm`).
- [x] **Bộ vỏ nhà In 3D v2 nhẹ hóa `agyhw14` (`hardware/in 3 d/`):** **`16` bàn in `.3mf`** nhúng sẵn thông số (`9% Gyroid`, `2/3` thành, `0% support`), **`51` chi tiết / `83` bản thể**, **`660.64 g` PLA** (giảm `-36.77%`), `73g 23p 49s`, `0` va chạm BRep, cơ cấu cửa Servo SG90 đồng trục dự trữ mô-men `14.56×` (không vít, không keo). Đồng thời giữ phương án cắt laser Mica 3 mm ([`docs/phan_cung/mica/ASSEMBLY_GUIDE.md`](docs/phan_cung/mica/ASSEMBLY_GUIDE.md)).

---

## Phần 3: Nạp Firmware, Triển Khai & Bàn Giao

- [x] **Firmware ESP8266 & Nạp USB 1 lệnh (`hardware/flash_and_setup.ps1`):** Nạp qua USB và nhập Wi-Fi runtime lưu LittleFS `/wifi_config.json` (tuyệt đối không lưu mật khẩu vào mã nguồn), kèm chế độ an toàn ngoại tuyến Addendum A1–A4 (`main_door` khóa đóng, bơm tự ngắt 120s, còi tự tắt 30s). Xem [`docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md`](docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md).
- [x] **Triển khai & Vận hành Production:** Máy chủ cổng `8088` + Tailscale Funnel HTTPS + Vercel redirect + quy trình backup SQLite WAL và `DEPLOY.lock`. Xem [`docs/huong_dan/VAN_HANH_VA_TRIEN_KHAI.md`](docs/huong_dan/VAN_HANH_VA_TRIEN_KHAI.md).
- [x] **Bộ tài liệu kỹ thuật & Công nghệ phiên bản thực đo:** Xem [`docs/kien_truc/CONG_NGHE_VA_PHIEN_BAN.md`](docs/kien_truc/CONG_NGHE_VA_PHIEN_BAN.md) và [`README.md`](README.md).
