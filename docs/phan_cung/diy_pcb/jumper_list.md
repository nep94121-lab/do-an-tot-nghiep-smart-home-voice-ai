# Danh Sách Dây Nhảy Mặt Trên (Top-Side Wire Jumpers — SmartHome Hub DIY v3.0)

- **Tổng số dây nhảy**: **7 dây (`JP1..JP7` / ký hiệu silkscreen `J-1..J-7`)**.
- **Đặc điểm tối ưu hóa mạch 1 lớp**: **0 dây nhảy trên GND** (vòng GND khép kín hoàn toàn trên `B.Cu`) và **0 dây nhảy trên toàn bộ 15 đường tín hiệu GPIO/Audio/Sensor**. Cả 7 dây nhảy đều nằm trên 2 đường nguồn `+3.3V` (3 dây) và `+5V` (4 dây), giúp kiểm tra thông mạch nguồn cực nhanh và chống nhiễu tín hiệu.
- **Quy cách dây**: Dây đồng lõi đặc **22 AWG** (đường kính lõi ~0.64 mm, lỗ khoan `0.9 mm`, pad tròn `2.8 mm`) có vỏ bọc cách điện PVC; uốn chân vuông góc và **hàn đầu tiên trước khi cắm các linh kiện cao**.
- **Lưu ý chiều cao**: `JP1` nằm phẳng dưới bụng NodeMCU (cùng `R4` thấp 2.5 mm), nằm gọn hoàn toàn dưới đế cắm cái cao 8.5 mm.

| ID | Nhãn Silk | Đường nguồn | Từ Pad / Net (X, Y mm) | Đến Pad / Net (X, Y mm) | Chiều dài (mm) | Màu dây gợi ý | Chức năng cầu nối |
| :---: | :---: | :---: | :--- | :--- | ---: | :--- | :--- |
| **JP1** | `J-1` | `+3.3V` | `JP1.1` `+3V3` (43.00, 46.30) | `JP1.2` `/+3V3_R` (55.70, 46.30) | **12.70** | Orange (+3.3V) | Bridges +3V3 from NodeMCU belly (U1.11/R4.1) across D3_AUDIO_PWM to +3V3 right bus (U2.6/U2.15/J15) |
| **JP2** | `J-2` | `+3.3V` | `JP2.1` `+3V3` (40.50, 62.00) | `JP2.2` `/+3V3_SOIL` (22.72, 62.00) | **17.78** | Orange (+3.3V) | Bridges +3V3 from NodeMCU belly across A0_SOIL to J14.1 (SOIL_A0 +3.3V) |
| **JP3** | `J-3` | `+3.3V` | `JP3.1` `/+3V3_R` (76.00, 46.70) | `JP3.2` `/+3V3_TOP` (76.00, 54.32) | **7.62** | Orange (+3.3V) | Bridges +3V3 vertically across D4_LED_BR from U2.6/J15 bus up to R7/R2/R3/J13 pull-ups |
| **JP4** | `J-4` | `+5V` | `JP4.1` `+5V` (36.50, 20.00) | `JP4.2` `/+5V_RLY2` (72.06, 20.00) | **35.56** | Red (+5V) | Bridges +5V from U1.15 across belly GND/D3/+3V3, U2.14 GND, and D8_BUZZER to right-side Relay 2 +5V bus |
| **JP5** | `J-5` | `+5V` | `JP5.1` `/+5V_RLY2` (85.50, 15.72) | `JP5.2` `/+5V_RLY1` (85.50, 28.42) | **12.70** | Red (+5V) | Bridges +5V vertically from J9.1 (Relay 2) across D7_RLY2_AMP to J7.1 (Relay 1) |
| **JP6** | `J-6` | `+5V` | `JP6.1` `/+5V_RLY1` (85.50, 33.00) | `JP6.2` `/+5V_TOP` (85.50, 53.32) | **20.32** | Red (+5V) | Bridges +5V vertically from Relay 1 across D6, D5, GND, +3V3_R, and D4 into open tunnel under R7 & R2 |
| **JP7** | `J-7` | `+5V` | `JP7.1` `/+5V_TOP` (85.50, 67.30) | `JP7.2` `/+5V_SERVO` (60.10, 67.30) | **25.40** | Red (+5V) | Bridges +5V horizontally across +3V3_TOP and D2_DHT11 into J3.2 (SERVO_D1 +5V) |

## Mẹo thi công dây nhảy nhanh & đẹp

1. Cắt dây dài hơn cột **Chiều dài (mm)** khoảng `+12 mm` (mỗi bên `+6 mm` để tuốt vỏ 4 mm, bẻ gập 90° xuyên qua lỗ `0.9 mm` và cắt gọn sau khi hàn).
2. Hàn toàn bộ `J-1..J-7` **ngay bước đầu tiên** (khi mặt bo còn phẳng) để dễ úp mạch xuống bàn hàn.
3. Dùng đồng hồ vạn năng thang thông mạch (Buzzer) đo từ `J1.1 (+5V)` tới `J3.2`, `J7.1`, `J9.1` và từ `U1.11 (+3V3)` tới `U2.6`, `J13.1`, `J14.1`, `J15.1` để xác nhận cả 7 dây nhảy thông suốt trước khi cắm NodeMCU.
