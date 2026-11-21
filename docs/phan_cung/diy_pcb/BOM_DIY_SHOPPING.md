# Danh Sách Linh Kiện Mua Sắm Cho Bo Hub PCB DIY 1 Lớp (BOM v3.0)

- **Phíp đồng**: 1 tấm phíp đồng **1 mặt FR-4** dày `1.6 mm`, kích thước tối thiểu `110 × 90 mm` (cắt hoàn thiện đúng `100.0 × 80.0 mm`, đồng 1 oz / 35 µm).
- **Mũi khoan PCB hợp kim/HSS**: đúng 4 cỡ `0.9 mm`, `1.1 mm`, `1.3 mm`, và `3.2 mm` (hoặc mũi khoan 3.0–3.2 mm cho lỗ ốc M3).
- **Ốc & trụ đồng M3**: 4 bộ ốc M3 × 10 mm + trụ đồng/nylon M3 (pattern lỗ `90.0 × 70.0 mm`).

## 1. Linh kiện hàn trực tiếp lên PCB (45 linh kiện + 4 lỗ M3 = 49 footprints)

| STT | Ký hiệu (Refs) | Giá trị / Tên linh kiện | Số lượng | Kiểu chân (Footprint DIY) | Mũi khoan | Nguồn chuẩn kích thước (Datasheet) |
| ---: | :--- | :--- | :---: | :--- | :---: | :--- |
| 1 | C1, C2 | `470uF 16V` | **2** | `CP_Radial_D8.0mm_P3.50mm_DIY` | 0.9 mm | 470 µF 16V Radial Electrolytic (D=8.0 mm, H=11.5 mm, P=3.50 mm, lead 0.6 mm) — Nichicon UVR/UHE |
| 2 | C3, C7, C6 | `100nF` | **3** | `C_Disc_D5.0mm_P5.00mm_DIY` | 0.9 mm | Ceramic Disc / MLCC 50V (D=5.0 mm, P=5.00 mm, lead 0.5 mm) — Murata RDE / Vishay K-series |
| 3 | C4 | `10uF 16V` | **1** | `CP_Radial_D5.0mm_P3.50mm_DIY` | 0.9 mm | 10 uF 16V Radial Electrolytic (D=5.0 mm, P=3.50 mm formed; use low-profile H<=7mm or lay flat sideways to clear NodeMCU Micro-USB plug) |
| 4 | C5 | `10nF` | **1** | `C_Disc_D5.0mm_P5.00mm_DIY` | 0.9 mm | Ceramic Disc / MLCC 50V (D=5.0 mm, P=5.00 mm, lead 0.5 mm) — Murata RDE / Vishay K-series |
| 5 | D1, D2 | `1N4007` | **2** | `D_DO41_P10.16mm_DIY` | 1.1 mm | 1N4007 DO-41 / SOD-81 (L=5.2 mm, D=2.7 mm, lead 0.86 mm max, P=10.16 mm) — Vishay 1N4007 |
| 6 | D3 | `LED_PWR_GRN` | **1** | `LED_D3.0mm_P5.08mm_DIY` | 0.9 mm | 3 mm Green Indicator LED (D=3.0 mm, leads formed to P=5.08 mm for forgiving 2.8 mm DIY pads) |
| 7 | J1 | `PWR_5V_IN` | **1** | `TerminalBlock_MKDS_1x02_P5.08mm_DIY` | 1.3 mm | Phoenix Contact MKDS 1,5/2-5,08 (pitch 5.08 mm, 0.9×0.9 mm pin, drill 1.3 mm) |
| 8 | J10 | `RLY2_SW` | **1** | `PinHeader_1x02_P2.54mm_DIY` | 1.1 mm | Standard 2.54 mm male pin header, 0.64 mm sq pin (0.905 mm diag) — Würth 61300211121 / Samtec TSW |
| 9 | J11 | `PAM8403_PWR` | **1** | `PinHeader_1x02_P2.54mm_DIY` | 1.1 mm | Standard 2.54 mm male pin header, 0.64 mm sq pin (0.905 mm diag) — Würth 61300211121 / Samtec TSW |
| 10 | J12 | `AUDIO_D3` | **1** | `PinHeader_1x02_P2.54mm_DIY` | 1.1 mm | Standard 2.54 mm male pin header, 0.64 mm sq pin (0.905 mm diag) — Würth 61300211121 / Samtec TSW |
| 11 | J13 | `DHT11_D2` | **1** | `PinHeader_1x03_P2.54mm_DIY` | 1.1 mm | Standard 2.54 mm male pin header, 0.64 mm sq pin (0.905 mm diag) — Würth 61300311121 / Samtec TSW |
| 12 | J14 | `SOIL_A0` | **1** | `PinHeader_1x03_P2.54mm_DIY` | 1.1 mm | Standard 2.54 mm male pin header, 0.64 mm sq pin (0.905 mm diag) — Würth 61300311121 / Samtec TSW |
| 13 | J15 | `KY037_D5` | **1** | `PinHeader_1x03_P2.54mm_DIY` | 1.1 mm | Standard 2.54 mm male pin header, 0.64 mm sq pin (0.905 mm diag) — Würth 61300311121 / Samtec TSW |
| 14 | J2 | `PUMP_OUT` | **1** | `TerminalBlock_MKDS_1x02_P5.08mm_DIY` | 1.3 mm | Phoenix Contact MKDS 1,5/2-5,08 (pitch 5.08 mm, 0.9×0.9 mm pin, drill 1.3 mm) |
| 15 | J3 | `SERVO_D1` | **1** | `PinHeader_1x03_P2.54mm_DIY` | 1.1 mm | Standard 2.54 mm male pin header, 0.64 mm sq pin (0.905 mm diag) — Würth 61300311121 / Samtec TSW |
| 16 | J4 | `LED_LR_D0` | **1** | `PinHeader_1x02_P2.54mm_DIY` | 1.1 mm | Standard 2.54 mm male pin header, 0.64 mm sq pin (0.905 mm diag) — Würth 61300211121 / Samtec TSW |
| 17 | J5 | `LED_BR_D4` | **1** | `PinHeader_1x02_P2.54mm_DIY` | 1.1 mm | Standard 2.54 mm male pin header, 0.64 mm sq pin (0.905 mm diag) — Würth 61300211121 / Samtec TSW |
| 18 | J6 | `BUZZ_D8` | **1** | `PinHeader_1x02_P2.54mm_DIY` | 1.1 mm | Standard 2.54 mm male pin header, 0.64 mm sq pin (0.905 mm diag) — Würth 61300211121 / Samtec TSW |
| 19 | J7 | `RLY1_PUMP_D6` | **1** | `PinHeader_1x03_P2.54mm_DIY` | 1.1 mm | Standard 2.54 mm male pin header, 0.64 mm sq pin (0.905 mm diag) — Würth 61300311121 / Samtec TSW |
| 20 | J8 | `RLY1_SW` | **1** | `PinHeader_1x02_P2.54mm_DIY` | 1.1 mm | Standard 2.54 mm male pin header, 0.64 mm sq pin (0.905 mm diag) — Würth 61300211121 / Samtec TSW |
| 21 | J9 | `RLY2_AMP_D7` | **1** | `PinHeader_1x03_P2.54mm_DIY` | 1.1 mm | Standard 2.54 mm male pin header, 0.64 mm sq pin (0.905 mm diag) — Würth 61300311121 / Samtec TSW |
| 22 | Q1 | `S8050` | **1** | `TO-92_Wide_DIY` | 0.9 mm | NPN BJT S8050 (hoặc 2N2222A, E-B-C, 0.7A/20V, TO-92 wide-formed leads, 0.9 mm drill, 2.60 mm round pads) — Unisonic S8050 |
| 23 | R1, R2 | `220R` | **2** | `R_Axial_P10.16mm_DIY` | 0.9 mm | 1/4W (0.25W) Metal/Carbon Film DIN 0207 (L=6.3 mm, D=2.5 mm, lead 0.6 mm, P=10.16 mm) |
| 24 | R3, R7, R4, R9 | `10k` | **4** | `R_Axial_P10.16mm_DIY` | 0.9 mm | 1/4W (0.25W) Metal/Carbon Film DIN 0207 (L=6.3 mm, D=2.5 mm, lead 0.6 mm, P=10.16 mm) |
| 25 | R5, R6 | `2.2k` | **2** | `R_Axial_P10.16mm_DIY` | 0.9 mm | 1/4W (0.25W) Metal/Carbon Film DIN 0207 (L=6.3 mm, D=2.5 mm, lead 0.6 mm, P=10.16 mm) |
| 26 | R8, R10 | `1k` | **2** | `R_Axial_P10.16mm_DIY` | 0.9 mm | 1/4W (0.25W) Metal/Carbon Film DIN 0207 (L=6.3 mm, D=2.5 mm, lead 0.6 mm, P=10.16 mm) |
| 27 | U1 | `NodeMCU_Left_1x15` | **1** | `PinSocket_1x15_P2.54mm_DIY` | 1.1 mm | 2.54 mm pitch, row spacing 22.86 mm (0.9 in), height 8.5 mm — NodeMCU v2 Amica (48.26 × 25.40 mm) |
| 28 | U2 | `NodeMCU_Right_1x15` | **1** | `PinSocket_1x15_P2.54mm_DIY` | 1.1 mm | 2.54 mm pitch, row spacing 22.86 mm (0.9 in), height 8.5 mm — NodeMCU v2 Amica (48.26 × 25.40 mm) |
| 29 | JP1, JP5 | `JUMPER_12.70mm` | **2** | `WireJumper_P12.70mm_DIY` | 0.9 mm | 22 AWG solid insulated hook-up wire jumper (0.64 mm core, 0.9 mm drill, 2.8 mm pads) |
| 30 | JP2 | `JUMPER_17.78mm` | **1** | `WireJumper_P17.78mm_DIY` | 0.9 mm | 22 AWG solid insulated hook-up wire jumper (0.64 mm core, 0.9 mm drill, 2.8 mm pads) |
| 31 | JP3 | `JUMPER_7.62mm` | **1** | `WireJumper_P7.62mm_DIY` | 0.9 mm | 22 AWG solid insulated hook-up wire jumper (0.64 mm core, 0.9 mm drill, 2.8 mm pads) |
| 32 | JP4 | `JUMPER_35.56mm` | **1** | `WireJumper_P35.56mm_DIY` | 0.9 mm | 22 AWG solid insulated hook-up wire jumper (0.64 mm core, 0.9 mm drill, 2.8 mm pads) |
| 33 | JP6 | `JUMPER_20.32mm` | **1** | `WireJumper_P20.32mm_DIY` | 0.9 mm | 22 AWG solid insulated hook-up wire jumper (0.64 mm core, 0.9 mm drill, 2.8 mm pads) |
| 34 | JP7 | `JUMPER_25.40mm` | **1** | `WireJumper_P25.40mm_DIY` | 0.9 mm | 22 AWG solid insulated hook-up wire jumper (0.64 mm core, 0.9 mm drill, 2.8 mm pads) |

## 2. 14 Module / Ngoại vi cắm ngoài (kết nối vào các header trên bo, giữ nguyên pin map)

| Module | Header trên bo | Chân NodeMCU | Ghi chú dây cắm |
| :--- | :---: | :---: | :--- |
| ESP8266 NodeMCU v2 Amica (CP2102) | `U1`, `U2` | 2×15 pin (22.86 mm) | Cắm vào 2 thanh cái 15 pin (`USB` hướng xuống cạnh dưới) |
| Nguồn DC 5V 2A (Adapter + jack domino) | `J1` (`PWR_5V_IN`) | `+5V`, `GND` | Vặn vít domino 5.08 mm (`+` chân 1 trên, `-` chân 2 dưới) |
| Servo SG90 (cửa chính) | `J3` (`SERVO_D1`) | `D1 / GPIO5` | 3 dây Dupont: SIG / +5V / GND |
| LED 5 mm Phòng khách | `J4` (`LED_LR_D0`) | `D0 / GPIO16` | Qua `R1` 220 Ω trên bo (`+` / GND) |
| LED 5 mm Phòng ngủ | `J5` (`LED_BR_D4`) | `D4 / GPIO2` | Active-LOW safe-boot qua `R2` 220 Ω + `R7` 10k |
| Còi Buzzer chủ động 5V (TMB12A05) | `J6` (`BUZZ_D8`) | `D8 / GPIO15` | Lái low-side qua `Q1` NPN `S8050` + `R10` 1k, `R9` 10k pull-down an toàn boot, `D2` 1N4007 dập xung (`+5V` / `BUZZ_K`) |
| Module Relay 1 (Xanh 5V SRD-05VDC — Bơm) | `J7` (điều khiển) + `J8` (tiếp điểm) | `D6 / GPIO12` | `J7`: 5V/GND/D6; `J8`: COM=`+5V`, NO=`PUMP_5V` |
| Bơm chìm mini DC 5V | `J2` (`PUMP_OUT`) | Qua Relay 1 | Vặn vít domino 5.08 mm, có `D1` 1N4007 dập xung |
| Module Relay 2 (Đỏ Opto 5V — Cấp nguồn Amp) | `J9` (điều khiển) + `J10` (tiếp điểm) | `D7 / GPIO13` | `J9`: 5V/GND/D7; `J10`: COM=`+5V`, NO=`AMP_5V` |
| Module khuếch đại PAM8403 + Loa 28 mm 8 Ω | `J11` (nguồn) + `J12` (tín hiệu) | `D3 / GPIO0` | `J11`: AMP_5V/GND; `J12`: AUD_OUT/GND (qua `C4,R5,R6,C5`) |
| Cảm biến nhiệt độ & độ ẩm DHT11 | `J13` (`DHT11_D2`) | `D2 / GPIO4` | 3.3V / D2 (có `R3` 10k pull-up) / GND |
| Cảm biến độ ẩm đất YL-69 + mạch LM393 | `J14` (`SOIL_A0`) | `A0` | 3.3V / GND / AO→A0 (có `C7` 100nF lọc nhiễu) |
| Cảm biến âm thanh KY-037 / KY-038 | `J15` (`KY037_D5`) | `D5 / GPIO14` | 3.3V / GND / DO→D5 |
