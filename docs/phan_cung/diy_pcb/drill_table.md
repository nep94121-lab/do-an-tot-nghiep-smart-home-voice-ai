# Bảng Lỗ Khoan PCB Một Lớp DIY (SmartHome Hub v3.0 — 100 × 80 mm)

- **Gốc tọa độ `(0.00, 0.00)`**: Góc **dưới-trái (lower-left)** của bo mạch khi nhìn từ mặt trên (mặt cắm linh kiện `F.SilkS`), trục `+X` sang phải (`0..100 mm`), trục `+Y` hướng lên (`0..80 mm`).
- **Tổng số lỗ khoan**: **127 lỗ**, gom gọn đúng **4 cỡ mũi khoan** (`0.9 mm`, `1.1 mm`, `1.3 mm`, `3.2 mm`).
- **File Excellon chuẩn**: [`smarthome_hub.drl`](smarthome_hub.drl) | **Bản đồ khoan 1:1**: [`drill_map.pdf`](drill_map.pdf) / [`drill_map.png`](drill_map.png).

## 1. Tổng hợp theo cỡ mũi khoan (4 cỡ duy nhất)

| Bước khoan | Mũi khoan (mm) | Loại | Số lỗ | Linh kiện sử dụng | Ghi chú kỹ thuật |
| :---: | :---: | :---: | :---: | :--- | :--- |
| 1 | **0.9 mm** | PTH (B.Cu) | **53** | C1, C2, C3, C4, C5, C6, C7, D3, JP1, JP2, JP3, JP4, JP5, JP6, JP7, Q1, R1, R2, R3, R4, R5, R6, R7, R8, R9, R10 | Resistors (R1-R10), NPN Transistor (Q1 S8050), Ceramic & Electrolytic Capacitors (C1-C7), Power LED (D3), Top-Side 22AWG Wire Jumpers (JP1-JP7) |
| 2 | **1.1 mm** | PTH (B.Cu) | **66** | D1, D2, J3, J4, J5, J6, J7, J8, J9, J10, J11, J12, J13, J14, J15, U1, U2 | NodeMCU Female Sockets (U1, U2), All 2.54mm Module Pin Headers (J3-J15), DO-41 Diodes (D1, D2) |
| 3 | **1.3 mm** | PTH (B.Cu) | **4** | J1, J2 | 5.08mm Phoenix MKDS Screw Terminal Blocks (J1 Power 5V In, J2 Pump Output) |
| 4 | **3.2 mm** | NPTH | **4** | H1, H2, H3, H4 | 4x Corner M3 Mounting Holes (H1-H4, NPTH, 90x70 mm pattern, 5 mm inset from corners) |
| **Tổng** | **4 cỡ** | — | **127** | **49 footprints** | **Đạt chuẩn `.kicad_dru` (0 lỗi mũi khoan)** |

## 2. Tọa độ chi tiết từng lỗ khoan (so với góc dưới-trái bo 100 × 80 mm)

| # | Mũi (mm) | Loại | X (mm) | Y (mm) | Linh kiện | Chân | Giá trị | Net |
| ---: | :---: | :---: | ---: | ---: | :---: | :---: | :--- | :--- |
| 1 | 0.9 | PTH | 23.50 | 42.50 | C1 | 1 | 470uF 16V | `+5V` |
| 2 | 0.9 | PTH | 20.00 | 42.50 | C1 | 2 | 470uF 16V | `GND` |
| 3 | 0.9 | PTH | 23.50 | 32.50 | C2 | 1 | 470uF 16V | `+5V` |
| 4 | 0.9 | PTH | 20.00 | 32.50 | C2 | 2 | 470uF 16V | `GND` |
| 5 | 0.9 | PTH | 29.00 | 23.44 | C3 | 1 | 100nF | `+5V` |
| 6 | 0.9 | PTH | 29.00 | 28.44 | C3 | 2 | 100nF | `GND` |
| 7 | 0.9 | PTH | 43.50 | 14.50 | C4 | 1 | 10uF 16V | `/D3_AUDIO_PWM` |
| 8 | 0.9 | PTH | 47.00 | 14.50 | C4 | 2 | 10uF 16V | `Net-(C4-Pad2)` |
| 9 | 0.9 | PTH | 60.00 | 8.50 | C5 | 1 | 10nF | `/AUD_OUT` |
| 10 | 0.9 | PTH | 65.00 | 8.50 | C5 | 2 | 10nF | `GND` |
| 11 | 0.9 | PTH | 33.50 | 14.50 | C6 | 1 | 100nF | `/AMP_5V` |
| 12 | 0.9 | PTH | 38.50 | 14.50 | C6 | 2 | 100nF | `GND` |
| 13 | 0.9 | PTH | 26.50 | 66.50 | C7 | 1 | 100nF | `/A0_SOIL` |
| 14 | 0.9 | PTH | 31.50 | 66.50 | C7 | 2 | 100nF | `GND` |
| 15 | 0.9 | PTH | 7.50 | 12.50 | D3 | 1 | LED_PWR_GRN | `GND` |
| 16 | 0.9 | PTH | 12.58 | 12.50 | D3 | 2 | LED_PWR_GRN | `Net-(D3-A)` |
| 17 | 0.9 | PTH | 43.00 | 46.30 | JP1 | 1 | JUMPER_12.70mm | `+3V3` |
| 18 | 0.9 | PTH | 55.70 | 46.30 | JP1 | 2 | JUMPER_12.70mm | `/+3V3_R` |
| 19 | 0.9 | PTH | 40.50 | 62.00 | JP2 | 1 | JUMPER_17.78mm | `+3V3` |
| 20 | 0.9 | PTH | 22.72 | 62.00 | JP2 | 2 | JUMPER_17.78mm | `/+3V3_SOIL` |
| 21 | 0.9 | PTH | 76.00 | 46.70 | JP3 | 1 | JUMPER_7.62mm | `/+3V3_R` |
| 22 | 0.9 | PTH | 76.00 | 54.32 | JP3 | 2 | JUMPER_7.62mm | `/+3V3_TOP` |
| 23 | 0.9 | PTH | 36.50 | 20.00 | JP4 | 1 | JUMPER_35.56mm | `+5V` |
| 24 | 0.9 | PTH | 72.06 | 20.00 | JP4 | 2 | JUMPER_35.56mm | `/+5V_RLY2` |
| 25 | 0.9 | PTH | 85.50 | 15.72 | JP5 | 1 | JUMPER_12.70mm | `/+5V_RLY2` |
| 26 | 0.9 | PTH | 85.50 | 28.42 | JP5 | 2 | JUMPER_12.70mm | `/+5V_RLY1` |
| 27 | 0.9 | PTH | 85.50 | 33.00 | JP6 | 1 | JUMPER_20.32mm | `/+5V_RLY1` |
| 28 | 0.9 | PTH | 85.50 | 53.32 | JP6 | 2 | JUMPER_20.32mm | `/+5V_TOP` |
| 29 | 0.9 | PTH | 85.50 | 67.30 | JP7 | 1 | JUMPER_25.40mm | `/+5V_TOP` |
| 30 | 0.9 | PTH | 60.10 | 67.30 | JP7 | 2 | JUMPER_25.40mm | `/+5V_SERVO` |
| 31 | 0.9 | PTH | 69.00 | 10.50 | Q1 | 1 | S8050 | `GND` |
| 32 | 0.9 | PTH | 71.54 | 13.04 | Q1 | 2 | S8050 | `/BUZZ_BASE` |
| 33 | 0.9 | PTH | 74.08 | 10.50 | Q1 | 3 | S8050 | `/BUZZ_K` |
| 34 | 0.9 | PTH | 54.00 | 65.50 | R1 | 1 | 220R | `/D0_LED_LR` |
| 35 | 0.9 | PTH | 43.84 | 65.50 | R1 | 2 | 220R | `Net-(J4-Pin_1)` |
| 36 | 0.9 | PTH | 75.50 | 26.50 | R10 | 1 | 1k | `/D8_BUZZER` |
| 37 | 0.9 | PTH | 75.50 | 16.34 | R10 | 2 | 1k | `/BUZZ_BASE` |
| 38 | 0.9 | PTH | 76.00 | 60.80 | R2 | 1 | 220R | `/+3V3_TOP` |
| 39 | 0.9 | PTH | 86.16 | 60.80 | R2 | 2 | 220R | `Net-(J5-Pin_1)` |
| 40 | 0.9 | PTH | 76.00 | 64.10 | R3 | 1 | 10k | `/+3V3_TOP` |
| 41 | 0.9 | PTH | 65.84 | 64.10 | R3 | 2 | 10k | `/D2_DHT11` |
| 42 | 0.9 | PTH | 43.00 | 51.38 | R4 | 1 | 10k | `+3V3` |
| 43 | 0.9 | PTH | 53.16 | 51.38 | R4 | 2 | 10k | `/D3_AUDIO_PWM` |
| 44 | 0.9 | PTH | 50.00 | 16.50 | R5 | 1 | 2.2k | `Net-(C4-Pad2)` |
| 45 | 0.9 | PTH | 60.16 | 16.50 | R5 | 2 | 2.2k | `/AUD_OUT` |
| 46 | 0.9 | PTH | 60.16 | 12.80 | R6 | 1 | 2.2k | `/AUD_OUT` |
| 47 | 0.9 | PTH | 50.00 | 12.80 | R6 | 2 | 2.2k | `GND` |
| 48 | 0.9 | PTH | 76.00 | 57.50 | R7 | 1 | 10k | `/+3V3_TOP` |
| 49 | 0.9 | PTH | 86.16 | 57.50 | R7 | 2 | 10k | `/D4_LED_BR` |
| 50 | 0.9 | PTH | 22.00 | 17.00 | R8 | 1 | 1k | `+5V` |
| 51 | 0.9 | PTH | 11.84 | 17.00 | R8 | 2 | 1k | `Net-(D3-A)` |
| 52 | 0.9 | PTH | 75.50 | 30.20 | R9 | 1 | 10k | `/D8_BUZZER` |
| 53 | 0.9 | PTH | 65.34 | 30.20 | R9 | 2 | 10k | `GND` |
| 54 | 1.1 | PTH | 16.50 | 58.00 | D1 | 1 | 1N4007 | `/PUMP_5V` |
| 55 | 1.1 | PTH | 16.50 | 47.84 | D1 | 2 | 1N4007 | `GND` |
| 56 | 1.1 | PTH | 80.50 | 22.10 | D2 | 1 | 1N4007 | `/+5V_RLY2` |
| 57 | 1.1 | PTH | 80.50 | 11.94 | D2 | 2 | 1N4007 | `/BUZZ_K` |
| 58 | 1.1 | PTH | 16.50 | 8.50 | J10 | 1 | RLY2_SW | `+5V` |
| 59 | 1.1 | PTH | 19.04 | 8.50 | J10 | 2 | RLY2_SW | `/AMP_5V` |
| 60 | 1.1 | PTH | 29.00 | 8.50 | J11 | 1 | PAM8403_PWR | `/AMP_5V` |
| 61 | 1.1 | PTH | 31.54 | 8.50 | J11 | 2 | PAM8403_PWR | `GND` |
| 62 | 1.1 | PTH | 53.50 | 8.50 | J12 | 1 | AUDIO_D3 | `/AUD_OUT` |
| 63 | 1.1 | PTH | 56.04 | 8.50 | J12 | 2 | AUDIO_D3 | `GND` |
| 64 | 1.1 | PTH | 81.58 | 72.50 | J13 | 1 | DHT11_D2 | `/+3V3_TOP` |
| 65 | 1.1 | PTH | 79.04 | 72.50 | J13 | 2 | DHT11_D2 | `/D2_DHT11` |
| 66 | 1.1 | PTH | 76.50 | 72.50 | J13 | 3 | DHT11_D2 | `GND` |
| 67 | 1.1 | PTH | 16.50 | 71.00 | J14 | 1 | SOIL_A0 | `/+3V3_SOIL` |
| 68 | 1.1 | PTH | 19.04 | 71.00 | J14 | 2 | SOIL_A0 | `GND` |
| 69 | 1.1 | PTH | 21.58 | 71.00 | J14 | 3 | SOIL_A0 | `/A0_SOIL` |
| 70 | 1.1 | PTH | 91.00 | 47.00 | J15 | 1 | KY037_D5 | `/+3V3_R` |
| 71 | 1.1 | PTH | 91.00 | 44.46 | J15 | 2 | KY037_D5 | `GND` |
| 72 | 1.1 | PTH | 91.00 | 41.92 | J15 | 3 | KY037_D5 | `/D5_MIC_DO` |
| 73 | 1.1 | PTH | 58.00 | 71.00 | J3 | 1 | SERVO_D1 | `/D1_SERVO` |
| 74 | 1.1 | PTH | 60.54 | 71.00 | J3 | 2 | SERVO_D1 | `/+5V_SERVO` |
| 75 | 1.1 | PTH | 63.08 | 71.00 | J3 | 3 | SERVO_D1 | `GND` |
| 76 | 1.1 | PTH | 40.50 | 71.00 | J4 | 1 | LED_LR_D0 | `Net-(J4-Pin_1)` |
| 77 | 1.1 | PTH | 43.04 | 71.00 | J4 | 2 | LED_LR_D0 | `GND` |
| 78 | 1.1 | PTH | 91.00 | 62.00 | J5 | 1 | LED_BR_D4 | `Net-(J5-Pin_1)` |
| 79 | 1.1 | PTH | 91.00 | 59.46 | J5 | 2 | LED_BR_D4 | `/D4_LED_BR` |
| 80 | 1.1 | PTH | 85.00 | 8.00 | J6 | 1 | BUZZ_D8 | `/+5V_RLY2` |
| 81 | 1.1 | PTH | 82.46 | 8.00 | J6 | 2 | BUZZ_D8 | `/BUZZ_K` |
| 82 | 1.1 | PTH | 91.00 | 28.42 | J7 | 1 | RLY1_PUMP_D6 | `/+5V_RLY1` |
| 83 | 1.1 | PTH | 91.00 | 30.96 | J7 | 2 | RLY1_PUMP_D6 | `GND` |
| 84 | 1.1 | PTH | 91.00 | 33.50 | J7 | 3 | RLY1_PUMP_D6 | `/D6_RLY1_PUMP` |
| 85 | 1.1 | PTH | 23.50 | 55.46 | J8 | 1 | RLY1_SW | `+5V` |
| 86 | 1.1 | PTH | 23.50 | 58.00 | J8 | 2 | RLY1_SW | `/PUMP_5V` |
| 87 | 1.1 | PTH | 91.00 | 15.42 | J9 | 1 | RLY2_AMP_D7 | `/+5V_RLY2` |
| 88 | 1.1 | PTH | 91.00 | 17.96 | J9 | 2 | RLY2_AMP_D7 | `GND` |
| 89 | 1.1 | PTH | 91.00 | 20.50 | J9 | 3 | RLY2_AMP_D7 | `/D7_RLY2_AMP` |
| 90 | 1.1 | PTH | 37.00 | 59.00 | U1 | 1 | NodeMCU_Left_1x15 | `/A0_SOIL` |
| 91 | 1.1 | PTH | 37.00 | 56.46 | U1 | 2 | NodeMCU_Left_1x15 | `unconnected-(U1-Pin_2-Pad2)` |
| 92 | 1.1 | PTH | 37.00 | 53.92 | U1 | 3 | NodeMCU_Left_1x15 | `unconnected-(U1-Pin_3-Pad3)` |
| 93 | 1.1 | PTH | 37.00 | 51.38 | U1 | 4 | NodeMCU_Left_1x15 | `unconnected-(U1-Pin_4-Pad4)` |
| 94 | 1.1 | PTH | 37.00 | 48.84 | U1 | 5 | NodeMCU_Left_1x15 | `unconnected-(U1-Pin_5-Pad5)` |
| 95 | 1.1 | PTH | 37.00 | 46.30 | U1 | 6 | NodeMCU_Left_1x15 | `unconnected-(U1-Pin_6-Pad6)` |
| 96 | 1.1 | PTH | 37.00 | 43.76 | U1 | 7 | NodeMCU_Left_1x15 | `unconnected-(U1-Pin_7-Pad7)` |
| 97 | 1.1 | PTH | 37.00 | 41.22 | U1 | 8 | NodeMCU_Left_1x15 | `unconnected-(U1-Pin_8-Pad8)` |
| 98 | 1.1 | PTH | 37.00 | 38.68 | U1 | 9 | NodeMCU_Left_1x15 | `unconnected-(U1-Pin_9-Pad9)` |
| 99 | 1.1 | PTH | 37.00 | 36.14 | U1 | 10 | NodeMCU_Left_1x15 | `GND` |
| 100 | 1.1 | PTH | 37.00 | 33.60 | U1 | 11 | NodeMCU_Left_1x15 | `+3V3` |
| 101 | 1.1 | PTH | 37.00 | 31.06 | U1 | 12 | NodeMCU_Left_1x15 | `unconnected-(U1-Pin_12-Pad12)` |
| 102 | 1.1 | PTH | 37.00 | 28.52 | U1 | 13 | NodeMCU_Left_1x15 | `unconnected-(U1-Pin_13-Pad13)` |
| 103 | 1.1 | PTH | 37.00 | 25.98 | U1 | 14 | NodeMCU_Left_1x15 | `GND` |
| 104 | 1.1 | PTH | 37.00 | 23.44 | U1 | 15 | NodeMCU_Left_1x15 | `+5V` |
| 105 | 1.1 | PTH | 59.86 | 59.00 | U2 | 1 | NodeMCU_Right_1x15 | `/D0_LED_LR` |
| 106 | 1.1 | PTH | 59.86 | 56.46 | U2 | 2 | NodeMCU_Right_1x15 | `/D1_SERVO` |
| 107 | 1.1 | PTH | 59.86 | 53.92 | U2 | 3 | NodeMCU_Right_1x15 | `/D2_DHT11` |
| 108 | 1.1 | PTH | 59.86 | 51.38 | U2 | 4 | NodeMCU_Right_1x15 | `/D3_AUDIO_PWM` |
| 109 | 1.1 | PTH | 59.86 | 48.84 | U2 | 5 | NodeMCU_Right_1x15 | `/D4_LED_BR` |
| 110 | 1.1 | PTH | 59.86 | 46.30 | U2 | 6 | NodeMCU_Right_1x15 | `/+3V3_R` |
| 111 | 1.1 | PTH | 59.86 | 43.76 | U2 | 7 | NodeMCU_Right_1x15 | `GND` |
| 112 | 1.1 | PTH | 59.86 | 41.22 | U2 | 8 | NodeMCU_Right_1x15 | `/D5_MIC_DO` |
| 113 | 1.1 | PTH | 59.86 | 38.68 | U2 | 9 | NodeMCU_Right_1x15 | `/D6_RLY1_PUMP` |
| 114 | 1.1 | PTH | 59.86 | 36.14 | U2 | 10 | NodeMCU_Right_1x15 | `/D7_RLY2_AMP` |
| 115 | 1.1 | PTH | 59.86 | 33.60 | U2 | 11 | NodeMCU_Right_1x15 | `/D8_BUZZER` |
| 116 | 1.1 | PTH | 59.86 | 31.06 | U2 | 12 | NodeMCU_Right_1x15 | `unconnected-(U2-Pin_12-Pad12)` |
| 117 | 1.1 | PTH | 59.86 | 28.52 | U2 | 13 | NodeMCU_Right_1x15 | `unconnected-(U2-Pin_13-Pad13)` |
| 118 | 1.1 | PTH | 59.86 | 25.98 | U2 | 14 | NodeMCU_Right_1x15 | `GND` |
| 119 | 1.1 | PTH | 59.86 | 23.44 | U2 | 15 | NodeMCU_Right_1x15 | `/+3V3_R` |
| 120 | 1.3 | PTH | 9.00 | 26.50 | J1 | 1 | PWR_5V_IN | `+5V` |
| 121 | 1.3 | PTH | 9.00 | 21.42 | J1 | 2 | PWR_5V_IN | `GND` |
| 122 | 1.3 | PTH | 9.00 | 58.00 | J2 | 1 | PUMP_OUT | `/PUMP_5V` |
| 123 | 1.3 | PTH | 9.00 | 52.92 | J2 | 2 | PUMP_OUT | `GND` |
| 124 | 3.2 | NPTH | 5.00 | 75.00 | H1 | M3 | M3_3.2mm | `NPTH` |
| 125 | 3.2 | NPTH | 95.00 | 75.00 | H2 | M3 | M3_3.2mm | `NPTH` |
| 126 | 3.2 | NPTH | 5.00 | 5.00 | H3 | M3 | M3_3.2mm | `NPTH` |
| 127 | 3.2 | NPTH | 95.00 | 5.00 | H4 | M3 | M3_3.2mm | `NPTH` |
