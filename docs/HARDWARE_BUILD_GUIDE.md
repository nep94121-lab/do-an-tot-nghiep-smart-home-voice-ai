# Hướng Dẫn Chế Tạo & Đấu Nối Phần Cứng — Smart Home Voice AI `v1.0` (PCB Trực Tiếp — Không Breadboard)

Tài liệu này là **chỉ mục trung tâm** dẫn tới toàn bộ hồ sơ thiết kế mạch in (KiCad PCB Hub DIY v3), cắt laser vỏ nhà Mica / in 3D v2 lắp mộng (FreeCAD), bảng kích thước kiểm định datasheet, bảng chiều dài 40 dây nối thực tế (`<= 30 cm`), danh mục linh kiện (BOM) và firmware ESP8266.

> **Nguồn sự thật duy nhất (SSOT):** Mọi chân cắm, màu dây, kích thước linh kiện, chiều dài dây 3D, sơ đồ mạch và firmware đều đồng bộ 100% từ [`hardware/wiring_contract.py`](../hardware/wiring_contract.py), [`hardware/component_dimensions_ssot.py`](../hardware/component_dimensions_ssot.py), [`hardware/wire_lengths.json`](../hardware/wire_lengths.json) và [`firmware/esp8266_smarthome/esp8266_smarthome.ino`](../firmware/esp8266_smarthome/esp8266_smarthome.ino).
> **Kiến trúc PCB-Direct (KHÔNG dùng Breadboard trắng):** Toàn bộ **6 thiết bị chấp hành + 3 cảm biến** cắm trực tiếp vào 15 cổng `J1–J15` trên mạch **PCB Hub DIY v3 (`100 × 80 × 1.6 mm`, `51 footprints`, `0 ERC / 0 DRC`)** sử dụng **NodeMCU ESP8266 v2 Amica (`48.26 × 25.40 mm`, CP2102, hàng chân `0.9"` / `22.86 mm` — KHÔNG dùng v3 LoLin)**. Toàn bộ **9 tụ điện `C1–C9` (kể cả `C8 100 nF` & `C9 100 µF 16V`) và 2 diode `D1–D2 (1N4007)` đều hàn trực tiếp trên PCB**. **40/40 dây nối `<= 30 cm` (`3.84 – 27.48 cm`)**. **Không** có breadboard trắng, quạt (`fan`), điều hòa (`ac`) hay hồng ngoại (`IR`).

---

## 1. Bảng Chỉ Mục Hồ Sơ Thiết Kế

| Hạng mục | Thư mục / Tệp nguồn | Tài liệu & Bản xuất sẵn sàng gia công |
| :--- | :--- | :--- |
| **Bảng đấu nối 40 dây & Chiều dài 3D (`<= 30 cm`)** | [`hardware/wiring_contract.py`](../hardware/wiring_contract.py) · [`hardware/wire_lengths.json`](../hardware/wire_lengths.json) | [`WIRING_TABLE.md`](phan_cung/WIRING_TABLE.md) · [`WIRE_LIST_LENGTHS.md`](phan_cung/WIRE_LIST_LENGTHS.md) · [`wire_lengths.csv`](phan_cung/wire_lengths.csv) · [`wiring_diagram_2d.svg`](phan_cung/wiring_diagram_2d.svg) · [`wiring_diagram_2d.pdf`](phan_cung/wiring_diagram_2d.pdf) · [`wiring_diagram_2d.png`](phan_cung/wiring_diagram_2d.png) |
| **Kiểm kê linh kiện, BOM & Kích thước Datasheet** | [`hardware/component_dimensions_ssot.py`](../hardware/component_dimensions_ssot.py) · [`docs/phan_cung/diy_pcb/bom.csv`](phan_cung/diy_pcb/bom.csv) | [`DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md`](phan_cung/DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md) · [`BOM_DIY_SHOPPING.md`](phan_cung/diy_pcb/BOM_DIY_SHOPPING.md) · [`DIMENSIONS_AUDIT.md`](phan_cung/DIMENSIONS_AUDIT.md) |
| **Mạch PCB Hub DIY v3 1 lớp (`100 × 80 mm`, `51 footprints`, `C1–C9` trên bo)** | [`hardware/kicad/smarthome_hub/`](../hardware/kicad/smarthome_hub/) ([`smarthome_hub.kicad_pcb`](../hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb)) | [`diy_pcb/`](phan_cung/diy_pcb/) · [`DIY_GUIDE.md`](phan_cung/diy_pcb/DIY_GUIDE.md) · [`toner_B.Cu_MIRRORED_1to1.pdf`](phan_cung/diy_pcb/toner_B.Cu_MIRRORED_1to1.pdf) · [`toner_B.Cu_check_NOT_mirrored_1to1.pdf`](phan_cung/diy_pcb/toner_B.Cu_check_NOT_mirrored_1to1.pdf) · [`drill_map.pdf`](phan_cung/diy_pcb/drill_map.pdf) · [`jumper_list.md`](phan_cung/diy_pcb/jumper_list.md) · [`gerbers/`](phan_cung/diy_pcb/gerbers/) |
| **Bản lắp ghép 3D KiCad & Blender** | [`hardware/kicad/smarthome_assembly/`](../hardware/kicad/smarthome_assembly/) · [`hardware/blender/`](../hardware/blender/) | [`ASM_REPORT.md`](phan_cung/assembly/ASM_REPORT.md) |
| **Vỏ nhà Mica 3mm cắt Laser (FreeCAD)** | [`hardware/mica/`](../hardware/mica/) ([`smarthome_mica_house.FCStd`](../hardware/mica/smarthome_mica_house.FCStd)) | [`ASSEMBLY_GUIDE.md`](phan_cung/mica/ASSEMBLY_GUIDE.md) · [`MICA_PANELS.md`](phan_cung/mica/MICA_PANELS.md) · [`sheet_layout_A3_1to1.pdf`](phan_cung/mica/sheet_layout_A3_1to1.pdf) · [`sheet_layout_A4_1to1.pdf`](phan_cung/mica/sheet_layout_A4_1to1.pdf) · [`sheet_layout_A3.dxf`](phan_cung/mica/sheet_layout_A3.dxf) · [`sheet_layout_A4.dxf`](phan_cung/mica/sheet_layout_A4.dxf) · [`holes_table.csv`](phan_cung/mica/holes_table.csv) |
| **Vỏ nhà In 3D v2 lắp mộng không vít/keo + Nội thất (`180×200×250 mm`)** | [`hardware/in 3 d/`](../hardware/in%203%20d/) ([`scripts/build_all_v2.py`](../hardware/in%203%20d/scripts/build_all_v2.py)) | [`README.md`](../hardware/in%203%20d/README.md) · [`plates/`](../hardware/in%203%20d/plates/) · [`parts/`](../hardware/in%203%20d/parts/) · [`drawings/`](../hardware/in%203%20d/drawings/) · [`previews/`](../hardware/in%203%20d/previews/) · [`manifest.json`](../hardware/in%203%20d/manifest.json) |
| **Firmware & Sơ đồ Wokwi** | [`firmware/esp8266_smarthome/esp8266_smarthome.ino`](../firmware/esp8266_smarthome/esp8266_smarthome.ino) · [`hardware/flash_and_setup.ps1`](../hardware/flash_and_setup.ps1) | [`HUONG_DAN_NAP_FIRMWARE_USB.md`](phan_cung/HUONG_DAN_NAP_FIRMWARE_USB.md) · [`firmware/wokwi/diagram.json`](../firmware/wokwi/diagram.json) |

---

## 2. Sơ Đồ 10 Chân ESP8266 Khóa Cứng & Quy Tắc An Toàn Boot

| Chân NodeMCU | GPIO | Vai trò | Cổng trên PCB Hub | Quy tắc phần cứng bắt buộc (100% hàn trên PCB Hub DIY v3) |
| :---: | :---: | :--- | :---: | :--- |
| **`D0`** | `GPIO16` | Đèn phòng khách (`living_room_light`) | `J4` | Active-HIGH qua điện trở hạn dòng `R1 220 Ω` |
| **`D1`** | `GPIO5` | Servo SG90 cửa chính (`main_door`) | `J3` | PWM 50Hz (`0°` đóng / `90°` mở vào trong); lắp **đồng tâm trên đỉnh bản lề** (`P07_SERVO_SHELF` + đai gài `SUP11` + khớp ngàm `SUP10B` + bản lề mộng `SUP10`, 0 vít/keo); cấp `+5V` lọc `C1 470 µF 16V` |
| **`D2`** | `GPIO4` | Cảm biến Nhiệt độ & Độ ẩm `DHT11` | `J13` | Cấp `+3.3V` (lọc `C8 100 nF` trên PCB), có điện trở kéo lên `R3 10 kΩ` |
| **`D3`** | `GPIO0` | Ngõ ra âm thanh PWM tới `PAM8403` | `J12` | **Boot-strap HIGH:** có `R4 10 kΩ` pull-up, tụ chặn DC `C4 10 µF 16V`, cầu phân áp `R5/R6 2.2 kΩ` & `C5 10 nF`; firmware giữ `INPUT` khi nghỉ |
| **`D4`** | `GPIO2` | Đèn phòng ngủ (`bedroom_light`) | `J5` | **Boot-strap HIGH:** đấu **Active-LOW** (`+3.3V -> R2 220 Ω -> LED -> D4`) + `R7 10 kΩ` pull-up |
| **`D5`** | `GPIO14` | Cảm biến âm thanh `KY-037/038` (`DO`) | `J15` | **Chỉ cấp `+3.3V`** (lọc `C8 100 nF` trên PCB, tuyệt đối không cấp `5V`), bỏ trống `AO`, debounce `>= 400 ms` |
| **`D6`** | `GPIO12` | Relay 1 Bơm tưới cây (`garden_pump`) | `J7`, `J8`, `J2` | Active-HIGH; mắc ngược diode chống dội `D1 1N4007` song song bơm + tụ `C2 470 µF 16V` |
| **`D7`** | `GPIO13` | Relay 2 nguồn loa `PAM8403` (`speaker_amp`) | `J9`, `J10`, `J11` | Relay opto đặt jumper **`H`**; nguồn `AMP_5V` lọc bởi **`C6 100 nF + C9 100 µF 16V` hàn trên PCB cạnh `J11`**; ngõ loa BTL (`L OUT + / -`) không nối `GND` |
| **`D8`** | `GPIO15` | Còi báo động 5V (`alarm_siren`) | `J6` | **Boot-strap LOW:** lái low-side qua `R10 1 kΩ -> Q1 S8050`, kéo xuống `R9 10 kΩ` & diode `D2 1N4007` |
| **`A0`** | `ADC0` | Cảm biến độ ẩm đất (`LM393` + `YL-69`) | `J14` | **Chỉ cấp `+3.3V`** cho `LM393`, lọc tụ `C7 100 nF` & `C8 100 nF` trên PCB, bỏ trống `DO` |

---

## 3. Quy Trình Gia Công & Lắp Ráp Đề Xuất

### Bước 1 — Gia công mạch PCB Hub DIY v3 1 lớp (`100 × 80 × 1.6 mm`, 0 Breadboard)
- Mạch chính [`smarthome_hub.kicad_pcb`](../hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb) gồm **51 footprints** (đã tích hợp trọn vẹn **`C1–C9`** gồm cả **`C8 100 nF`** cạnh `J14` và **`C9 100 µF 16V`** cạnh `J11`, cùng **`D1–D2 1N4007`**, `Q1 S8050`, `R1–R10`, `J1–J15`, `U1–U2`, `JP1–JP7`), đạt **0 lỗi DRC, 0 cảnh báo DRC và 0 lỗi ERC** (xem [`diy_pcb/`](phan_cung/diy_pcb/), [`drc_report.txt`](phan_cung/diy_pcb/drc_report.txt) và [`erc_report.txt`](phan_cung/diy_pcb/erc_report.txt)).
- In đúng tỷ lệ **100% (1:1, không scale)** tệp [`toner_B.Cu_MIRRORED_1to1.pdf`](phan_cung/diy_pcb/toner_B.Cu_MIRRORED_1to1.pdf) để ủi chuyển mực; đối chiếu mặt đồng không lật bằng [`toner_B.Cu_check_NOT_mirrored_1to1.pdf`](phan_cung/diy_pcb/toner_B.Cu_check_NOT_mirrored_1to1.pdf).
- Khoan lỗ theo [`drill_map.pdf`](phan_cung/diy_pcb/drill_map.pdf) & [`drill_table.md`](phan_cung/diy_pcb/drill_table.md) (4 mũi khoan `0.9 / 1.1 / 1.3 / 3.2 mm`), hàn toàn bộ linh kiện trên bo (gồm `C1–C9`, `D1–D3`, `Q1`, `R1–R10`), đế `U1/U2` cho **NodeMCU v2 Amica (`48.26 × 25.40 mm`)**, rào cắm `J1..J15` và **7 dây nhảy mặt trên (`JP1..JP7`)** theo [`jumper_list.md`](phan_cung/diy_pcb/jumper_list.md) và [`DIY_GUIDE.md`](phan_cung/diy_pcb/DIY_GUIDE.md).

### Bước 2 — Cắt Laser Mica 3mm hoặc In 3D Vỏ Nhà v2 + Phụ Kiện Supot
- **Phương án A (Cắt Laser / Thủ công Mica 3mm):** Sử dụng tệp DXF sẵn cắt [`sheet_layout_A3.dxf`](phan_cung/mica/sheet_layout_A3.dxf) (hoặc [`sheet_layout_A4.dxf`](phan_cung/mica/sheet_layout_A4.dxf) / bản in kiểm tra 1:1 [`sheet_layout_A3_1to1.pdf`](phan_cung/mica/sheet_layout_A3_1to1.pdf)) xuất từ FreeCAD [`smarthome_mica_house.FCStd`](../hardware/mica/smarthome_mica_house.FCStd). Kiểm tra 19 tấm tại [`MICA_PANELS.md`](phan_cung/mica/MICA_PANELS.md) & [`holes_table.csv`](phan_cung/mica/holes_table.csv), ghép khung theo [`ASSEMBLY_GUIDE.md`](phan_cung/mica/ASSEMBLY_GUIDE.md).
- **Phương án B (In 3D FDM `180 × 200 × 250 mm` — 100% lắp mộng không vít/keo cho đủ 14 mô-đun + NodeMCU + Hub PCB):** Mở thư mục [`hardware/in 3 d/`](../hardware/in%203%20d/) và làm theo hướng dẫn tiếng Việt đầy đủ tại [`hardware/in 3 d/README.md`](../hardware/in%203%20d/README.md): đã tích hợp cơ cấu **cửa chính truyền động trực tiếp đồng tâm Servo SG90** (`P07_SERVO_SHELF`, `SUP11_SG90_SNAP_SADDLE`, `SUP10_DOOR_MORTISE_HINGE`, `SUP10B_DOOR_HORN_COUPLER`, cữ chặn `-2°/+92°`) cùng đầy đủ ngàm giữ không vít/keo (`SUP16` giắc DC-022 nguồn 5V → `J1`, `SUP17` ×2 vòng giữ LED 5mm phòng khách/phòng ngủ, `SUP18` cốc giữ còi 5V), giúp **40/40 dây nối `<= 30 cm`**, kiểm định 0 va chạm 3D BRep (kể cả quét cánh cửa `0..90°`) và cắt lớp không cần support trên PrusaSlicer.

### Bước 3 — Đấu 40 Dây Trực Tiếp (PCB-Direct) & Nạp Firmware ESP8266
1. Cắm từng bước 40 dây nối theo [`WIRING_TABLE.md`](phan_cung/WIRING_TABLE.md), bảng chiều dài chuẩn [`WIRE_LIST_LENGTHS.md`](phan_cung/WIRE_LIST_LENGTHS.md) hoặc giao diện hướng dẫn từng bước `/wokwi` (mặc định Sơ đồ PCB 2D trực tiếp — không breadboard), và kiểm tra lại danh mục an toàn nguồn/boot trong [`DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md`](phan_cung/DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md).
2. Thực hiện nạp firmware và cấu hình Wi-Fi runtime an toàn qua USB bằng 1 script duy nhất theo [`HUONG_DAN_NAP_FIRMWARE_USB.md`](phan_cung/HUONG_DAN_NAP_FIRMWARE_USB.md) (không lưu mật khẩu Wi-Fi vào mã nguồn):
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File hardware\flash_and_setup.ps1 -DryRun
   powershell -NoProfile -ExecutionPolicy Bypass -File hardware\flash_and_setup.ps1
   ```
3. Mở trang `/wokwi` hoặc `/` trên máy chủ để xác nhận telemetry `DHT11`, `soil_moisture`, `ky037` và điều khiển 6 thiết bị hoạt động đồng bộ.
