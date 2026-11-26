# Hướng Dẫn Chế Tạo & Đấu Nối Phần Cứng — Smart Home Voice AI `v1.0`

Tài liệu này là **chỉ mục trung tâm** dẫn tới toàn bộ hồ sơ thiết kế mạch in (KiCad), cắt laser vỏ nhà Mica (FreeCAD), danh mục linh kiện (BOM), sơ đồ 40 dây nối chuẩn hóa và firmware ESP8266.

> **Nguồn sự thật duy nhất (SSOT):** Mọi chân cắm, màu dây, sơ đồ mạch và firmware đều đồng bộ 100% từ [`hardware/wiring_contract.py`](../hardware/wiring_contract.py) và [`firmware/esp8266_smarthome/esp8266_smarthome.ino`](../firmware/esp8266_smarthome/esp8266_smarthome.ino).
> **Hợp đồng phần cứng khóa cứng:** Đúng **6 thiết bị chấp hành + 3 cảm biến** trên **10 chân** NodeMCU ESP8266 v2 Amica. **Không** có quạt (`fan`), điều hòa (`ac`) hay mắt thu/phát hồng ngoại (`IR`).

---

## 1. Bảng Chỉ Mục Hồ Sơ Thiết Kế

| Hạng mục | Thư mục / Tệp nguồn | Tài liệu & Bản xuất sẵn sàng gia công |
| :--- | :--- | :--- |
| **Bảng đấu nối 40 dây & 10 chân** | [`hardware/wiring_contract.py`](../hardware/wiring_contract.py) | [`WIRING_TABLE.md`](phan_cung/WIRING_TABLE.md) · [`wiring_diagram_2d.svg`](phan_cung/wiring_diagram_2d.svg) · [`wiring_diagram_2d.pdf`](phan_cung/wiring_diagram_2d.pdf) · [`wiring_diagram_2d.png`](phan_cung/wiring_diagram_2d.png) |
| **Kiểm kê linh kiện & mua sắm** | [`hardware/kicad/smarthome_hub/bom.csv`](../hardware/kicad/smarthome_hub/bom.csv) | [`DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md`](phan_cung/DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md) · [`BOM_DIY_SHOPPING.md`](phan_cung/diy_pcb/BOM_DIY_SHOPPING.md) · [`DIMENSIONS_AUDIT.md`](phan_cung/DIMENSIONS_AUDIT.md) |
| **Mạch PCB Hub DIY 1 lớp (`100 × 80 mm`)** | [`hardware/kicad/smarthome_hub/`](../hardware/kicad/smarthome_hub/) ([`smarthome_hub.kicad_pcb`](../hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb)) | [`DIY_GUIDE.md`](phan_cung/diy_pcb/DIY_GUIDE.md) · [`toner_B.Cu_MIRRORED_1to1.pdf`](phan_cung/diy_pcb/toner_B.Cu_MIRRORED_1to1.pdf) · [`toner_B.Cu_check_NOT_mirrored_1to1.pdf`](phan_cung/diy_pcb/toner_B.Cu_check_NOT_mirrored_1to1.pdf) · [`drill_map.pdf`](phan_cung/diy_pcb/drill_map.pdf) · [`jumper_list.md`](phan_cung/diy_pcb/jumper_list.md) · [`gerbers/`](phan_cung/diy_pcb/gerbers/) |
| **Bản lắp ghép 3D KiCad & Blender** | [`hardware/kicad/smarthome_assembly/`](../hardware/kicad/smarthome_assembly/) · [`hardware/blender/`](../hardware/blender/) | [`ASM_REPORT.md`](phan_cung/assembly/ASM_REPORT.md) |
| **Vỏ nhà Mica 3mm cắt Laser (FreeCAD)** | [`hardware/mica/`](../hardware/mica/) ([`smarthome_mica_house.FCStd`](../hardware/mica/smarthome_mica_house.FCStd)) | [`ASSEMBLY_GUIDE.md`](phan_cung/mica/ASSEMBLY_GUIDE.md) · [`MICA_PANELS.md`](phan_cung/mica/MICA_PANELS.md) · [`sheet_layout_A3_1to1.pdf`](phan_cung/mica/sheet_layout_A3_1to1.pdf) · [`sheet_layout_A4_1to1.pdf`](phan_cung/mica/sheet_layout_A4_1to1.pdf) · [`sheet_layout_A3.dxf`](phan_cung/mica/sheet_layout_A3.dxf) · [`sheet_layout_A4.dxf`](phan_cung/mica/sheet_layout_A4.dxf) · [`holes_table.csv`](phan_cung/mica/holes_table.csv) |
| **Vỏ nhà In 3D v2 lắp mộng không vít/keo + Nội thất (`180×200×250 mm`)** | [`hardware/in 3 d/`](../hardware/in%203%20d/) ([`scripts/build_all_v2.py`](../hardware/in%203%20d/scripts/build_all_v2.py)) | [`README.md`](../hardware/in%203%20d/README.md) · [`plates/`](../hardware/in%203%20d/plates/) · [`parts/`](../hardware/in%203%20d/parts/) · [`drawings/`](../hardware/in%203%20d/drawings/) · [`previews/`](../hardware/in%203%20d/previews/) · [`manifest.json`](../hardware/in%203%20d/manifest.json) |
| **Firmware & Sơ đồ Wokwi** | [`firmware/esp8266_smarthome/esp8266_smarthome.ino`](../firmware/esp8266_smarthome/esp8266_smarthome.ino) | [`firmware/wokwi/diagram.json`](../firmware/wokwi/diagram.json) |

---

## 2. Sơ Đồ 10 Chân ESP8266 Khóa Cứng & Quy Tắc An Toàn Boot

| Chân NodeMCU | GPIO | Vai trò | Cổng trên PCB Hub | Quy tắc phần cứng bắt buộc |
| :---: | :---: | :--- | :---: | :--- |
| **`D0`** | `GPIO16` | Đèn phòng khách (`living_room_light`) | `J4` | Active-HIGH qua điện trở hạn dòng `R1 220 Ω` |
| **`D1`** | `GPIO5` | Servo SG90 cửa chính (`main_door`) | `J3` | PWM 50Hz (`0°` đóng / `90°` mở); cấp `+5V` có tụ lọc `C1 470 µF 16V` |
| **`D2`** | `GPIO4` | Cảm biến Nhiệt độ & Độ ẩm `DHT11` | `J13` | Cấp `+3.3V`, có điện trở kéo lên `R3 10 kΩ` |
| **`D3`** | `GPIO0` | Ngõ ra âm thanh PWM tới `PAM8403` | `J12` | **Boot-strap HIGH:** có `R4 10 kΩ` pull-up, tụ chặn DC `C4 10 µF 16V`, cầu phân áp `R5/R6 2.2 kΩ` & `C5 10 nF`; firmware giữ `INPUT` khi nghỉ |
| **`D4`** | `GPIO2` | Đèn phòng ngủ (`bedroom_light`) | `J5` | **Boot-strap HIGH:** đấu **Active-LOW** (`+3.3V -> R2 220 Ω -> LED -> D4`) + `R7 10 kΩ` pull-up |
| **`D5`** | `GPIO14` | Cảm biến âm thanh `KY-037/038` (`DO`) | `J15` | **Chỉ cấp `+3.3V`** (tuyệt đối không cấp `5V`), bỏ trống `AO`, debounce `>= 400 ms` |
| **`D6`** | `GPIO12` | Relay 1 Bơm tưới cây (`garden_pump`) | `J7`, `J8`, `J2` | Active-HIGH; mắc ngược diode chống dội `D1 1N4007` song song bơm + tụ `C2 470 µF 16V` |
| **`D7`** | `GPIO13` | Relay 2 nguồn loa `PAM8403` (`speaker_amp`) | `J9`, `J10`, `J11` | Relay opto đặt jumper **`H`**; ngõ loa `PAM8403` là cầu **BTL (`L OUT + / -`) — không nối xuống `GND`** |
| **`D8`** | `GPIO15` | Còi báo động 5V (`alarm_siren`) | `J6` | **Boot-strap LOW:** lái low-side qua `R10 1 kΩ -> Q1 S8050`, kéo xuống `R9 10 kΩ` & diode `D2 1N4007` |
| **`A0`** | `ADC0` | Cảm biến độ ẩm đất (`LM393` + `YL-69`) | `J14` | **Chỉ cấp `+3.3V`** cho `LM393`, lọc tụ `C7 100 nF`, bỏ trống `DO` |

---

## 3. Quy Trình Gia Công & Lắp Ráp Đề Xuất

### Bước 1 — Gia công mạch PCB Hub 1 lớp DIY (`100 × 80 × 1.6 mm`)
- Mạch chính [`smarthome_hub.kicad_pcb`](../hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb) đã vượt qua kiểm định với **0 lỗi DRC, 0 cảnh báo DRC và 0 lỗi ERC** (xem [`drc_report.txt`](phan_cung/diy_pcb/drc_report.txt) và [`erc_report.txt`](phan_cung/diy_pcb/erc_report.txt)).
- In đúng tỷ lệ **100% (1:1, không scale)** tệp [`toner_B.Cu_MIRRORED_1to1.pdf`](phan_cung/diy_pcb/toner_B.Cu_MIRRORED_1to1.pdf) để ủi chuyển mực; đối chiếu mặt đồng không lật bằng [`toner_B.Cu_check_NOT_mirrored_1to1.pdf`](phan_cung/diy_pcb/toner_B.Cu_check_NOT_mirrored_1to1.pdf).
- Khoan lỗ theo [`drill_map.pdf`](phan_cung/diy_pcb/drill_map.pdf) & [`drill_table.md`](phan_cung/diy_pcb/drill_table.md) (4 mũi khoan `0.9 / 1.1 / 1.3 / 3.2 mm`), hàn linh kiện thụ động, đế `U1/U2`, rào cắm `J1..J15` và **7 dây nhảy mặt trên (`JP1..JP7`)** theo [`jumper_list.md`](phan_cung/diy_pcb/jumper_list.md) và hướng dẫn chi tiết [`DIY_GUIDE.md`](phan_cung/diy_pcb/DIY_GUIDE.md).

### Bước 2 — Cắt Laser Mica 3mm hoặc In 3D Vỏ Nhà + Phụ Kiện Supot
- **Phương án A (Cắt Laser / Thủ công Mica 3mm):** Sử dụng tệp DXF sẵn cắt [`sheet_layout_A3.dxf`](phan_cung/mica/sheet_layout_A3.dxf) (hoặc [`sheet_layout_A4.dxf`](phan_cung/mica/sheet_layout_A4.dxf) / bản in kiểm tra 1:1 [`sheet_layout_A3_1to1.pdf`](phan_cung/mica/sheet_layout_A3_1to1.pdf)) được xuất từ mô hình tham số FreeCAD [`smarthome_mica_house.FCStd`](../hardware/mica/smarthome_mica_house.FCStd). Kiểm tra toàn bộ 19 tấm và danh mục lỗ khoan tại [`MICA_PANELS.md`](phan_cung/mica/MICA_PANELS.md) & [`holes_table.csv`](phan_cung/mica/holes_table.csv), sau đó ghép khung theo [`ASSEMBLY_GUIDE.md`](phan_cung/mica/ASSEMBLY_GUIDE.md) và sơ đồ phân rã [`assembly_exploded.pdf`](phan_cung/mica/assembly_exploded.pdf).
- **Phương án B (In 3D FDM `180 × 200 × 250 mm` — 100% lắp mộng không vít/keo):** Mở thư mục [`hardware/in 3 d/`](../hardware/in%203%20d/) và làm theo hướng dẫn tiếng Việt đầy đủ tại [`hardware/in 3 d/README.md`](../hardware/in%203%20d/README.md) gồm **57 chi tiết (`99` bản thể: `30` mảnh vỏ nhà, `18` bộ kẹp/giá đỡ mạch chốt đàn hồi & lòng bể nước liền khối, `9` nhóm nội thất tỷ lệ nhà)** đã đóng gói sẵn vào **17 bàn in** (`plates/PLATEnn_*.3mf` + `.stl`), kiểm định lắp khít với mạch KiCad PCB thực, 0 va chạm 3D BRep và cắt lớp sạch không cần support trên PrusaSlicer.

### Bước 3 — Đấu Dây & Nạp Firmware ESP8266
1. Cắm hoàn chỉnh 40 dây nối theo [`WIRING_TABLE.md`](phan_cung/WIRING_TABLE.md) và kiểm tra lại danh mục an toàn nguồn/boot trong [`DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md`](phan_cung/DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md).
2. Cấu hình Wi-Fi & địa chỉ MQTT/Server trong [`firmware/esp8266_smarthome/esp8266_smarthome.ino`](../firmware/esp8266_smarthome/esp8266_smarthome.ino), sau đó biên dịch và nạp:
   ```bash
   arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 firmware/esp8266_smarthome/esp8266_smarthome.ino
   arduino-cli upload -p COM3 --fqbn esp8266:esp8266:nodemcuv2 firmware/esp8266_smarthome/esp8266_smarthome.ino
   ```
3. Mở trang `/wokwi` hoặc `/` trên máy chủ để xác nhận telemetry `DHT11`, `soil_moisture`, `ky037` và điều khiển 6 thiết bị hoạt động đồng bộ.
