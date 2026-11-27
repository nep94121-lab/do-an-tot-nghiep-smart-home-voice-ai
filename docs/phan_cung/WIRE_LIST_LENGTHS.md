# Danh Sách 40 Dây Nối & Chiều Dài Thực Tế 3D (PCB Trực Tiếp — Không Breadboard)

> **Nguồn tính tự động:** `scripts/compute_wire_lengths.py` tính từ tọa độ chân thực trên `smarthome_hub.kicad_pcb` (`J1–J15`) và vị trí giá đỡ module thực trong nhà in 3D v2 (`hardware/mica/mica_design.py` + `hardware/in 3 d/`), đã cộng **+18% độ chùng & bán kính uốn `R >= 8 mm`**.

- **Tổng số dây:** **40 dây** (36 dây từ PCB Hub `J1–J15` + 4 dây nối giữa module `PAM8403→Loa` và `LM393→Đầu dò đất`).
- **Chiều dài tính toán (đã cộng 18% độ chùng):** Ngắn nhất **`3.84 cm`**, Dài nhất **`27.48 cm`**, Tổng cộng **`654.99 cm`** (`6.55 m`).
- **Kiểm tra giới hạn dây Dupont chuẩn `<= 30 cm`:** **ĐẠT 40/40 (0 dây vượt 30 cm)**.

## 1. Bảng Chi Tiết 40 Dây Nối & Chiều Dài (cm)

| ID | Đầu PCB (`J#`) | Mô-đun & Chân | Tín hiệu | Màu | Loại đầu nối | Thẳng (cm) | Đi dây 3D (cm) | Kèm 18% chùng (cm) | Mua chuẩn (cm) | Đạt <=30cm |
| :---: | :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | :---: |
| `W01` | `J1.1` | 5V 2A External Supply (`+5V`) | `+5V` | Red | Screw Terminal 22AWG | 7.63 | 8.12 | **9.58** | **10 cm** | PASS |
| `W02` | `J1.2` | 5V 2A External Supply (`GND`) | `GND` | Black | Screw Terminal 22AWG | 7.27 | 7.71 | **9.10** | **10 cm** | PASS |
| `W03` | `J3.1` | SG90 Micro Servo (`PWM (Orange)`) | `D1_SERVO` | Orange | Dupont 1x3 F-M | 13.12 | 15.45 | **18.24** | **20 cm** | PASS |
| `W04` | `J3.2` | SG90 Micro Servo (`VCC (Red)`) | `+5V` | Red | Dupont 1x3 F-M | 13.32 | 15.49 | **18.28** | **20 cm** | PASS |
| `W05` | `J3.3` | SG90 Micro Servo (`GND (Brown)`) | `GND` | Black | Dupont 1x3 F-M | 13.53 | 15.55 | **18.35** | **20 cm** | PASS |
| `W06` | `J4.1` | 5mm LED (Living Room) (`Anode (+)`) | `LED_LR_A` | Yellow | Dupont 1x2 F-F | 15.85 | 17.93 | **21.16** | **30 cm** | PASS |
| `W07` | `J4.2` | 5mm LED (Living Room) (`Cathode (-)`) | `GND` | Black | Dupont 1x2 F-F | 15.57 | 17.56 | **20.72** | **30 cm** | PASS |
| `W08` | `J5.1` | 5mm LED (Bedroom) (`Anode (+)`) | `LED_BR_A` | Purple | Dupont 1x2 F-F | 16.62 | 23.29 | **27.48** | **30 cm** | PASS |
| `W09` | `J5.2` | 5mm LED (Bedroom) (`Cathode (-)`) | `D4_LED_BR` | White | Dupont 1x2 F-F | 16.68 | 23.27 | **27.45** | **30 cm** | PASS |
| `W10` | `J7.1` | Relay 1 (Blue 5V 1-ch) (`VCC`) | `+5V` | Red | Dupont 1x3 F-F | 6.13 | 6.68 | **7.89** | **10 cm** | PASS |
| `W11` | `J7.2` | Relay 1 (Blue 5V 1-ch) (`GND`) | `GND` | Black | Dupont 1x3 F-F | 6.13 | 6.68 | **7.89** | **10 cm** | PASS |
| `W12` | `J7.3` | Relay 1 (Blue 5V 1-ch) (`IN`) | `D6_RLY1_PUMP` | Green | Dupont 1x3 F-F | 6.13 | 6.68 | **7.89** | **10 cm** | PASS |
| `W13` | `J8.1` | Relay 1 (Blue 5V 1-ch) (`COM (Screw)`) | `+5V` | Red | Dupont F-Pin (22AWG) | 14.98 | 15.18 | **17.91** | **20 cm** | PASS |
| `W14` | `J8.2` | Relay 1 (Blue 5V 1-ch) (`NO (Screw)`) | `PUMP_5V` | Yellow | Dupont F-Pin (22AWG) | 15.00 | 15.20 | **17.94** | **20 cm** | PASS |
| `W15` | `J2.1` | Mini Submersible Pump (3-6V) (`Pump + (Red)`) | `PUMP_5V` | Red | Screw Terminal 22AWG | 20.86 | 22.42 | **26.45** | **30 cm** | PASS |
| `W16` | `J2.2` | Mini Submersible Pump (3-6V) (`Pump - (Black)`) | `GND` | Black | Screw Terminal 22AWG | 20.72 | 22.22 | **26.22** | **30 cm** | PASS |
| `W17` | `J6.1` | Active 5V Buzzer (TMB12A05) (`Buzzer (+)`) | `+5V` | Red | Dupont 1x2 F-F | 16.19 | 21.53 | **25.41** | **30 cm** | PASS |
| `W18` | `J6.2` | Active 5V Buzzer (TMB12A05) (`Buzzer (-)`) | `BUZZ_K` | Orange | Dupont 1x2 F-F | 16.47 | 21.87 | **25.81** | **30 cm** | PASS |
| `W19` | `J9.1` | Relay 2 (Red Opto 5V, Jmp=H) (`DC+`) | `+5V` | Red | Dupont 1x3 F-F | 4.66 | 5.30 | **6.26** | **10 cm** | PASS |
| `W20` | `J9.2` | Relay 2 (Red Opto 5V, Jmp=H) (`DC-`) | `GND` | Black | Dupont 1x3 F-F | 4.66 | 5.30 | **6.26** | **10 cm** | PASS |
| `W21` | `J9.3` | Relay 2 (Red Opto 5V, Jmp=H) (`IN`) | `D7_RLY2_AMP` | Cyan | Dupont 1x3 F-F | 4.66 | 5.30 | **6.26** | **10 cm** | PASS |
| `W22` | `J10.1` | Relay 2 (Red Opto 5V, Jmp=H) (`COM (Screw)`) | `+5V` | Red | Dupont F-Pin | 15.70 | 15.89 | **18.75** | **20 cm** | PASS |
| `W23` | `J10.2` | Relay 2 (Red Opto 5V, Jmp=H) (`NO (Screw)`) | `AMP_5V` | Orange | Dupont F-Pin | 15.51 | 15.71 | **18.53** | **20 cm** | PASS |
| `W24` | `J11.1` | PAM8403 Audio Amplifier (`5V+`) | `AMP_5V` | Red | Dupont 1x2 F-F | 11.93 | 13.31 | **15.71** | **20 cm** | PASS |
| `W25` | `J11.2` | PAM8403 Audio Amplifier (`5V-`) | `GND` | Black | Dupont 1x2 F-F | 11.97 | 13.36 | **15.76** | **20 cm** | PASS |
| `W26` | `J12.1` | PAM8403 Audio Amplifier (`L (Audio In)`) | `AUD_OUT` | White | Dupont 1x2 F-F | 9.92 | 11.08 | **13.08** | **20 cm** | PASS |
| `W27` | `J12.2` | PAM8403 Audio Amplifier (`GND (Audio ⊥)`) | `GND` | Black | Dupont 1x2 F-F | 9.97 | 11.13 | **13.13** | **20 cm** | PASS |
| `W28` | `PAM8403.L_OUT+` | Mini Speaker (28mm 8Ω 0.5W) (`SPK +`) | `SPK_BTL_P` | Yellow | 2-Wire Pair | 3.32 | 3.42 | **4.04** | **10 cm** | PASS |
| `W29` | `PAM8403.L_OUT-` | Mini Speaker (28mm 8Ω 0.5W) (`SPK -`) | `SPK_BTL_N` | Brown | 2-Wire Pair | 3.21 | 3.26 | **3.84** | **10 cm** | PASS |
| `W30` | `J13.1` | DHT11 3-Pin Breakout (`VCC (+)`) | `+3V3` | Red | Dupont 1x3 F-F | 15.93 | 16.23 | **19.15** | **20 cm** | PASS |
| `W31` | `J13.2` | DHT11 3-Pin Breakout (`DATA (OUT)`) | `D2_DHT11` | Blue | Dupont 1x3 F-F | 16.23 | 16.60 | **19.59** | **20 cm** | PASS |
| `W32` | `J13.3` | DHT11 3-Pin Breakout (`GND (-)`) | `GND` | Black | Dupont 1x3 F-F | 16.53 | 16.99 | **20.05** | **30 cm** | PASS |
| `W33` | `J14.1` | Soil LM393 Comparator Module (`VCC`) | `+3V3` | Red | Dupont 1x3 F-F | 20.23 | 22.34 | **26.36** | **30 cm** | PASS |
| `W34` | `J14.2` | Soil LM393 Comparator Module (`GND`) | `GND` | Black | Dupont 1x3 F-F | 20.23 | 22.34 | **26.36** | **30 cm** | PASS |
| `W35` | `J14.3` | Soil LM393 Comparator Module (`AO`) | `A0_SOIL` | Green | Dupont 1x3 F-F | 20.23 | 22.34 | **26.36** | **30 cm** | PASS |
| `W36` | `LM393.P1` | YL-69 Soil Fork Probe (`Prong A`) | `SOIL_PROBE_A` | Yellow | Dupont 1x2 F-F | 9.68 | 11.71 | **13.82** | **20 cm** | PASS |
| `W37` | `LM393.P2` | YL-69 Soil Fork Probe (`Prong B`) | `SOIL_PROBE_B` | Orange | Dupont 1x2 F-F | 9.33 | 11.36 | **13.40** | **20 cm** | PASS |
| `W38` | `J15.1` | KY-037 / KY-038 Sound Module (`+ (VCC)`) | `+3V3` | Red | Dupont 1x3 F-F | 9.45 | 9.51 | **11.22** | **20 cm** | PASS |
| `W39` | `J15.2` | KY-037 / KY-038 Sound Module (`G (GND)`) | `GND` | Black | Dupont 1x3 F-F | 9.72 | 9.74 | **11.49** | **20 cm** | PASS |
| `W40` | `J15.3` | KY-037 / KY-038 Sound Module (`DO`) | `D5_MIC_DO` | Yellow | Dupont 1x3 F-F | 9.98 | 10.00 | **11.80** | **20 cm** | PASS |

## 2. Tổng Hợp Mua Dây Theo Cỡ Tiêu Chuẩn (`10 / 20 / 30 cm`)

| Cỡ dây chuẩn | Loại đầu nối | Số sợi cần | Ghi chú mua sắm |
| :---: | :--- | ---: | :--- |
| **10 cm** | 2-Wire Pair | **2** | Mua theo bó 10/20/40 sợi cùng cỡ |
| **10 cm** | Dupont 1x3 F-F | **6** | Mua theo bó 10/20/40 sợi cùng cỡ |
| **10 cm** | Screw Terminal 22AWG | **2** | Mua theo bó 10/20/40 sợi cùng cỡ |
| **20 cm** | Dupont 1x2 F-F | **6** | Mua theo bó 10/20/40 sợi cùng cỡ |
| **20 cm** | Dupont 1x3 F-F | **5** | Mua theo bó 10/20/40 sợi cùng cỡ |
| **20 cm** | Dupont 1x3 F-M | **3** | Mua theo bó 10/20/40 sợi cùng cỡ |
| **20 cm** | Dupont F-Pin | **2** | Mua theo bó 10/20/40 sợi cùng cỡ |
| **20 cm** | Dupont F-Pin (22AWG) | **2** | Mua theo bó 10/20/40 sợi cùng cỡ |
| **30 cm** | Dupont 1x2 F-F | **6** | Mua theo bó 10/20/40 sợi cùng cỡ |
| **30 cm** | Dupont 1x3 F-F | **4** | Mua theo bó 10/20/40 sợi cùng cỡ |
| **30 cm** | Screw Terminal 22AWG | **2** | Mua theo bó 10/20/40 sợi cùng cỡ |

