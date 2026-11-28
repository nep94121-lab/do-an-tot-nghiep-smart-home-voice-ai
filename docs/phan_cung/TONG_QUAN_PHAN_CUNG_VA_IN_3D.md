# Tổng Quan Phần Cứng PCB-Direct, Ánh Xạ 14 Module & Bộ In 3D (`TONG_QUAN_PHAN_CUNG_VA_IN_3D.md`)

Tài liệu này là bản tổng hợp chuẩn hóa (SSOT) cho toàn bộ thiết kế phần cứng điện tử và cơ khí vỏ nhà của hệ thống **Smart Home Voice AI**, đối chiếu trực tiếp 100% từ:
- [`hardware/wiring_contract.py`](../../hardware/wiring_contract.py) & [`hardware/wire_lengths.json`](../../hardware/wire_lengths.json)
- [`hardware/component_dimensions_ssot.py`](../../hardware/component_dimensions_ssot.py)
- [`hardware/kicad/smarthome_hub/bom.csv`](../../hardware/kicad/smarthome_hub/bom.csv)
- [`docs/phan_cung/WIRING_TABLE.md`](WIRING_TABLE.md) & [`docs/phan_cung/DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md`](DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md)
- [`hardware/in 3 d/README.md`](../../hardware/in%203%20d/README.md) (bản giảm nhựa `agyhw14`)

> **Chính sách kiến trúc phần cứng chốt (100% PCB-Direct — KHÔNG dùng breadboard trắng):**
> - Toàn bộ hệ thống gồm **14 khối/module vật lý ngoài bo** kết nối trực tiếp vào **02 bo trung tâm** (`NodeMCU ESP8266 v2 Amica` cắm lên `PCB Hub DIY v3` kích thước `100 × 80 × 1.6 mm`, `51 footprints`, `0 ERC / 0 DRC`).
> - **Đã loại bỏ hoàn toàn các hạng mục cũ (`legacy — không dùng`):** **Không dùng breadboard trắng**, **không có quạt (`fan`)**, **không có điều hòa 220V (`ac`)**, **không có hồng ngoại (`IR` / `VS1838B` / `IR LED 940nm`)**. Toàn bộ hệ thống hoạt động an toàn ở điện áp một chiều thấp `5V DC` và `3.3V DC`.

---

## 1. Bảng Ánh Xạ Từ 14 Khối/Module Vật Lý + 2 Bo Trung Tâm Sang 6 Thiết Bị Chấp Hành & 3 Cảm Biến

Mặc dù trên bàn thực tế có **14 khối/module ngoài bo** (cộng thêm **NodeMCU ESP8266 v2 Amica** và **PCB Hub DIY v3** thành **16 đối tượng vật lý** trong mô hình 3D), phần mềm điều khiển gom gọn theo đúng hợp đồng **6 thiết bị chấp hành + 3 cảm biến** vì một số thiết bị chấp hành cần nhiều module phối hợp (ví dụ: *Bơm tưới cây* gồm Relay 1 + Động cơ bơm; *Loa phản hồi* gồm Relay 2 + Mạch khuếch đại PAM8403 + Loa 28mm; *Cảm biến độ ẩm đất* gồm mạch so sánh LM393 + Đầu dò YL-69; và khối cấp nguồn 5V 2A cấp điện cho toàn mạch):

| STT | Mã Module (`component_dimensions_ssot`) | Khối/Module Vật Lý Thực Tế | Nhóm Logic Trong Phần Mềm (6 Thiết bị / 3 Cảm biến / Hạ tầng) | Cổng PCB Hub | Chân NodeMCU (GPIO) | Ngàm In 3D Không Vít/Keo |
| :---: | :--- | :--- | :--- | :---: | :---: | :--- |
| **1** | `sg90_servo` | Động cơ Servo SG90 9g (`22.8×12.2×22.5 mm`) | **Thiết bị 1:** `main_door` (Cửa chính · Cấp 1) | `J3` | `D1` (`GPIO5`) | `P07_SERVO_SHELF`, `SUP11`, `SUP10`, `SUP10B` |
| **2** | `led_living` | Bóng đèn LED 5mm phòng khách | **Thiết bị 2:** `living_room_light` (Đèn phòng khách · Cấp 3) | `J4` | `D0` (`GPIO16`) | `P06_WALL_MID`, `SUP17` |
| **3** | `led_bedroom` | Bóng đèn LED 5mm phòng ngủ (Active-LOW) | **Thiết bị 3:** `bedroom_light` (Đèn phòng ngủ · Cấp 3) | `J5` | `D4` (`GPIO2`) | `P06_WALL_MID`, `SUP17` |
| **4** | `relay1_pump` | Module Relay 1 kênh 5V xanh (Songle SRD-05VDC) | **Thiết bị 4 (tầng đóng cắt):** `garden_pump` (Bơm tưới cây · Cấp 2) | `J7`, `J8` | `D6` (`GPIO12`) | `SUP07_RELAY_SNAP_CADDY`, `P01A` |
| **5** | `pump_unit` | Máy bơm chìm mini 3–6V DC + ống silicon | **Thiết bị 4 (tải chấp hành):** `garden_pump` (Bơm tưới cây · Cấp 2) | `J2` | `PUMP_5V` *(qua Relay 1)* | `SUP15_WATER_TANK_LINER`, `P10` |
| **6** | `buzzer_alarm` | Còi báo động chủ động 5V (`TMB12A05`) | **Thiết bị 5:** `alarm_siren` (Còi báo động · Cấp 1) | `J6` | `D8` (`GPIO15`, qua `Q1 S8050`) | `P05_WALL_FRONT`, `SUP18` |
| **7** | `relay2_speaker` | Module Relay 1 kênh 5V opto đỏ (jumper `H`) | **Thiết bị 6 (đóng cắt nguồn):** `speaker_amp` (Loa phản hồi · Cấp 2) | `J9`, `J10` | `D7` (`GPIO13`) | `SUP07_RELAY_SNAP_CADDY`, `P01A` |
| **8** | `pam8403_amp` | Mạch khuếch đại âm thanh Class-D `PAM8403` (3W) | **Thiết bị 6 (tầng khuếch đại):** `speaker_amp` (Loa phản hồi · Cấp 2) | `J11`, `J12` | `D3` (`GPIO0` PWM) + `AMP_5V` | `SUP08_PAM8403_SNAP_TRAY`, `P01A` |
| **9** | `speaker_mini` | Loa tròn mini `Ø28 mm, 8 Ω, 0.5 W` | **Thiết bị 6 (loa phát âm BTL):** `speaker_amp` (Loa phản hồi · Cấp 2) | `PAM8403 L_OUT±` | Vi sai BTL *(không nối GND)* | `SUP09_SPEAKER_SNAP_RETAINER`, `P15` |
| **10** | `dht11_sensor` | Cảm biến Nhiệt độ & Độ ẩm `DHT11` (3 chân) | **Cảm biến 1:** `dht11` (Nhiệt độ °C & Độ ẩm %) | `J13` | `D2` (`GPIO4`) | `SUP12_DHT11_SNAP_CRADLE`, `P06` |
| **11** | `soil_lm393` | Mạch so sánh độ ẩm đất `LM393` (cấp `3.3V`) | **Cảm biến 2 (xử lý tín hiệu):** `soil_moisture` (Độ ẩm đất %) | `J14` | `A0` (`ADC0`) | `SUP14_LM393_SNAP_CRADLE`, `P13` |
| **12** | `soil_probe` | Đầu dò độ ẩm đất 2 nhánh `YL-69` | **Cảm biến 2 (đầu dò vật lý):** `soil_moisture` (Độ ẩm đất %) | `LM393 P1/P2` | Nối `LM393` | `P14_SOIL_BRIDGE` |
| **13** | `ky037_sound` | Cảm biến âm thanh `KY-037 / KY-038` (cấp `3.3V`, `DO`) | **Cảm biến 3:** `ky037` (Phát hiện vỗ tay / tiếng động lớn) | `J15` | `D5` (`GPIO14`) | `SUP13_KY037_SNAP_CRADLE`, `P05` |
| **14** | `psu_5v` | Nguồn ngoài `5V 2A` + giắc `DC-022` (`5.5×2.1 mm`) | **Hạ tầng cấp nguồn hệ thống** (`+5V` & `GND` chung) | `J1` | `VIN` (`U1.15`) & `GND` | `P15_TECH_FASCIA`, `SUP16` |
| *Bo lõi 1* | `nodemcu` | **NodeMCU ESP8266 v2 Amica** (`48.26×25.40 mm`, CP2102) | **Vi điều khiển trung tâm** (Wi-Fi 2.4 GHz, 10 chân khóa cứng) | `U1`, `U2` | Toàn bộ `D0–D8`, `A0` | Cắm trực tiếp đế `U1/U2` trên PCB |
| *Bo lõi 2* | `hub_pcb` | **PCB Hub DIY v3** (`100×80×1.6 mm`, 1 lớp B.Cu) | **Bo mạch trung tâm tích hợp bảo vệ** (`51 footprints`, 0 breadboard) | `J1–J15`, `U1–U2` | Toàn mạch | `SUP06_HUB_PCB_SNAP_CARRIER`, `P16`, `SUP05` |

---

## 2. Tóm Tắt Mạch PCB Hub DIY v3 (`hardware/kicad/smarthome_hub/`)

- **Thông số chế tạo:** Mạch in 1 lớp mặt đáy (`B.Cu`) chuyên dụng cho tự gia công Toner Transfer (ủi mạch) hoặc đặt xưởng, kích thước **`100.0 × 80.0 × 1.6 mm`**, khoảng cách đồng tối thiểu `>= 0.60 mm`.
- **Kiểm định KiCad 10.0.6:** **`0 lỗi ERC`**, **`0 cảnh báo ERC`**, **`0 lỗi DRC`**, **`0 cảnh báo DRC`**, `0` chân hở mạch (xem [`diy_pcb/erc_report.txt`](diy_pcb/erc_report.txt) và [`diy_pcb/drc_report.txt`](diy_pcb/drc_report.txt)).
- **Tổng số linh kiện BOM (`51 footprints` = `47` linh kiện hàn + `4` lỗ bắt M3 `H1–H4`):**
  - **2 đế cắm NodeMCU (`U1`, `U2`):** `PinSocket 1×15` bước `2.54 mm`, khoảng cách hàng chân chuẩn **`0.9"` (`22.86 mm`)** dành riêng cho **NodeMCU v2 Amica** (không dùng v3 LoLin rộng `31 mm`).
  - **15 đầu nối ngoại vi (`J1–J15`):** `2` domino vít `5.08 mm` (`J1` nguồn `5V 2A`, `J2` ngõ ra bơm) và `13` rào cắm `2.54 mm` (`J3–J15`).
  - **9 tụ lọc & chặn DC hàn trực tiếp trên PCB (`C1–C9`):**
    - `C1`, `C2`: `470 µF 16V` lọc xung khởi động cho Servo SG90 và Máy bơm trên rail `+5V`.
    - `C3`, `C6`, `C7`, **`C8`**: `100 nF 50V` gốm lọc nhiễu cao tần cho `+5V`, `AMP_5V`, `A0_SOIL` và rail **`+3V3`** (cạnh `J14`).
    - `C4`: `10 µF 16V` chặn DC cho chân boot-strap `D3 (GPIO0)` vào mạch loa; `C5`: `10 nF 50V` lọc thông thấp RC (`fc ≈ 14.5 kHz`).
    - **`C9`**: `100 µF 16V` dự trữ năng lượng hàn ngay cạnh `J11` song song `C6` cho mạch khuếch đại Class-D `PAM8403`.
  - **2 diode dập xung ngược (`D1`, `D2` — `1N4007`)** bảo vệ tải cảm ứng bơm (`J2`) và còi (`J6`), cùng **`D3`** LED xanh 3 mm báo nguồn `+5V`.
  - **1 transistor lái (`Q1` — `S8050` NPN)** + **10 điện trở 1/4W (`R1–R10`)** đảm bảo an toàn tuyệt đối 3 chân boot-strap `D3/D4/D8` + **7 dây nhảy mặt trên (`JP1–JP7`)**.

---

## 3. Hợp Đồng 40 Dây Nối Thực Tế (`<= 30 cm`)

Toàn bộ 40 dây nối vật lý (`W01`–`W40`) gồm **36 dây từ PCB Hub `J1–J15`** và **4 dây liên kết ngoài bo** (`PAM8403 → Loa ×2`, `LM393 → YL-69 ×2`) đã được tính đường đi 3D thực tế trong vỏ nhà cộng `+18%` độ chùng:
- **Ngắn nhất:** **`3.84 cm`** (`W29`: `PAM8403 L_OUT- → Loa -`)
- **Dài nhất:** **`27.48 cm`** (`W08`: `J5.1 → LED phòng ngủ +`)
- **Tổng chiều dài dây:** **`654.99 cm`** (`6.55 m`) — đạt **`40/40` dây `<= 30 cm`**.
- **Tổng hợp mua dây theo cỡ chuẩn:** `10 cm` (**10 sợi**) · `20 cm` (**18 sợi**) · `30 cm` (**12 sợi**).
- Xem bảng chi tiết từng dây tại [`WIRING_TABLE.md`](WIRING_TABLE.md), [`WIRE_LIST_LENGTHS.md`](WIRE_LIST_LENGTHS.md) và sơ đồ vector 2D tại [`wiring_diagram_2d.svg`](wiring_diagram_2d.svg).

---

## 4. Bộ Vỏ Nhà In 3D v2 Giảm Nhựa (`agyhw14` — `hardware/in 3 d/`)

Ngoài phương án cắt laser Mica 3 mm truyền thống ([`docs/phan_cung/mica/`](mica/ASSEMBLY_GUIDE.md)), phiên bản hoàn thiện nhất là bộ tệp **In 3D FDM v2 lắp mộng tự khóa 100% (0 vít, 0 keo, 0 support)** tối ưu giảm nhựa `agyhw14`:

| Chỉ tiêu kiểm định | Giá trị đo thực tế (`PrusaSlicer 2.9.7 CLI` & `FreeCAD 1.1.4`) |
| :--- | :--- |
| **Khổ máy in mục tiêu** | **`180 × 200 × 250 mm`** (vùng in khả dụng `170 × 190 × 245 mm`) |
| **Tổng số bàn in (`.3mf` nhúng sẵn cấu hình)** | **`16` bàn in** (`PLATE01`–`PLATE16`, `16/16` đạt `manifold = yes`) |
| **Quy mô chi tiết** | **`51` chi tiết duy nhất / `83` bản thể vật lý** (`30` mảnh vỏ `P01A`–`P17` + `21` kẹp/giá đỡ `SUP01`–`SUP18`; đã bỏ toàn bộ `9` mã đồ trang trí `FUR01`–`FUR09`) |
| **Khối lượng nhựa PLA tiêu thụ** | **`660.64 g`** (`221.50 m` sợi `1.75 mm`) — giảm **`384.22 g` (`-36.77%`)** so với bản trước (`1044.86 g` / `17` bàn) |
| **Tổng thời gian in ước tính** | **`73g 23p 49s`** (`73.40 giờ`) |
| **Cấu hình cắt lớp nhúng sẵn trong `.3mf`** | Lớp `0.20 mm`, **`9% Gyroid`**, **`2` thành** (riêng `23` chi tiết mộng/ngàm/cửa Servo giữ **`3` thành**), **`3` lớp đỉnh / `3` lớp đáy** (riêng bể nước `SUP15` dùng `4` lớp đáy `0.8 mm` chống thấm), **`0% support`** |
| **Thiết kế nhẹ hóa kết cấu** | Vách/sàn làm mỏng cục bộ `2.2 mm` kèm gân cứng `3.0 mm` và `288` ô tổ ong `28 mm` ở vùng không chịu lực; giữ kín `100%` khoang điện Relay/PSU và bể nước; độ võng cực đại dưới tải `250 g` = **`0.0801 mm`** (`<= 0.50 mm`) |
| **Cơ cấu cửa Servo SG90 đồng trục (`agyhw13`)** | Dẫn động trực tiếp đồng tâm trục bản lề (`P07`, `SUP11`, `SUP10`, `SUP10B`), cữ chặn `-2°..+92°`, quét `0°–90°` đạt **`0.0000 mm³`** va chạm, hệ số dự trữ mô-men **`14.56×`** (mốc worst-case `14.16× >= 5×`) |
| **Kiểm định lắp ghép ảo 3D BRep & Fit Table** | Sai số tái ghép mảnh chia **`0.0000 mm`**, **`0` va chạm** toàn hệ thống, **`16/16` PASS** lắp khít PCB & 14 module |

---

## 5. Tài Liệu Phần Cứng Chi Tiết

- [Chỉ mục chế tạo & đấu nối phần cứng (`docs/HARDWARE_BUILD_GUIDE.md`)](../HARDWARE_BUILD_GUIDE.md)
- [Bảng đấu nối 40 dây & 10 chân ESP8266 (`WIRING_TABLE.md`)](WIRING_TABLE.md)
- [Danh sách chiều dài 40 dây & mua sắm (`WIRE_LIST_LENGTHS.md`)](WIRE_LIST_LENGTHS.md)
- [Kiểm kê linh kiện & checklist an toàn (`DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md`)](DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md)
- [Kiểm định kích thước Datasheet 26 linh kiện (`DIMENSIONS_AUDIT.md`)](DIMENSIONS_AUDIT.md)
- [Hồ sơ gia công PCB Hub DIY v3 (`diy_pcb/DIY_GUIDE.md`)](diy_pcb/DIY_GUIDE.md)
- [Hướng dẫn in & lắp ráp bộ vỏ 3D 16 bàn (`hardware/in 3 d/README.md`)](../../hardware/in%203%20d/README.md)
- [Hướng dẫn nạp firmware USB & cài Wi-Fi runtime (`CAI_DAT_WIFI_VA_NAP_USB.md`)](../huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md)
