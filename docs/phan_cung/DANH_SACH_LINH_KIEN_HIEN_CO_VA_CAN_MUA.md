# 📋 KIỂM KÊ LINH KIỆN THỰC TẾ & SƠ ĐỒ ĐẤU NỐI PHẦN CỨNG (PCB TRỰC TIẾP — KHÔNG BREADBOARD)

> **Cập nhật kiến trúc PCB-Direct (`Hub DIY v3`, `100 × 80 × 1.6 mm`, `51 footprints`, `0 ERC / 0 DRC`) — Hợp đồng Phần cứng Khóa cứng (`6 thiết bị chấp hành + 3 cảm biến`) trên `NodeMCU ESP8266 v2 Amica (48.26 × 25.40 mm)`.**
> **Chính sách không dùng Breadboard:** Toàn bộ hệ thống cắm **trực tiếp** lên **PCB Hub trung tâm DIY v3 (`J1–J15`, `U1–U2`)** với **đầy đủ `C1–C9` (kể cả `C8 100nF` & `C9 100µF 16V`) và `D1–D2 (1N4007)` hàn trực tiếp trên PCB**. Bảng cắm Breadboard trắng chỉ còn là phụ kiện **legacy (không dùng)** trong bản lắp ráp hoàn chỉnh.
> **Tài liệu liên quan:** [`WIRING_TABLE.md`](WIRING_TABLE.md) · [`WIRE_LIST_LENGTHS.md`](WIRE_LIST_LENGTHS.md) *(40/40 dây `<= 30 cm`, `3.84–27.48 cm`)* · [`DIMENSIONS_AUDIT.md`](DIMENSIONS_AUDIT.md) · [`diy_pcb/`](diy_pcb/)

---

## 1. TOÀN BỘ LINH KIỆN ĐANG CÓ SẴN TRÊN BÀN (ĐÃ ĐỦ 100% CHO BỘ 6 THIẾT BỊ + 3 CẢM BIẾN)

Đối chiếu từ `components_overview.png` và `pam8403_ky037_closeup.png`, toàn bộ linh kiện cốt lõi đã **có sẵn trên bàn**:

| STT | Linh kiện thực tế | Số lượng | Vai trò & Chân kết nối trên `NodeMCU ESP8266 v2 Amica` & PCB Hub v3 |
| :---: | :--- | :---: | :--- |
| **1** | **Mạch `NodeMCU ESP8266 v2 Amica` (ESP-12E/F, CP2102, `48.26 × 25.40 mm`, hàng chân hẹp `0.9"` / `22.86 mm` `2×15`)** | **01 mạch** | Bộ vi điều khiển trung tâm Wi-Fi 2.4GHz (**chỉ dùng v2 Amica**, không dùng v3 LoLin `58×31 mm`); cắm thẳng vào đế `U1/U2` trên PCB Hub DIY v3. |
| **2** | **Mạch `PCB Hub Trung Tâm DIY v3` (`100 × 80 × 1.6 mm`, 1 lớp B.Cu, `51 footprints`)** | **01 mạch** | Thay thế hoàn toàn bảng cắm thử nghiệm: tích hợp đế `U1/U2`, 15 đầu nối `J1–J15`, `R1–R10`, `Q1 (S8050)`, **`C1–C9`** *(bao gồm `C8 100nF` & `C9 100µF 16V` hàn trực tiếp trên PCB)*, **`D1–D2 (1N4007)`**, `D3`, `JP1–JP7`. *(Ghi chú: Breadboard 400 lỗ màu trắng trên ảnh cũ là **legacy — không dùng** trong bản lắp ráp hoàn chỉnh.)* |
| **3** | **Module Relay 1 kênh 5V màu xanh dương** *(trên giữa ảnh)* | **01 cái** | **Relay 1 (`D6 / GPIO12` — `garden_pump`, `J7/J8`):** Đóng/ngắt nguồn `5V` ngoài cho **Máy bơm nước mini trắng**. |
| **4** | **Module Relay 1 kênh 5V opto cách ly màu đỏ** *(góc dưới phải, có jumper vàng `H/L`)* | **01 cái** | **Relay 2 (`D7 / GPIO13` — `speaker_amp`, `J9/J10`):** Đặt jumper ở mức **`H`**, đóng/ngắt nguồn `5V` cho mạch khuếch đại loa **PAM8403**. |
| **5** | **Mạch khuếch đại âm thanh `PAM8403` PCB xanh lá** *(pad `L OUT R`, `L ⊥ R`, `5V + -`)* | **01 mạch** | Khuếch đại tín hiệu âm thanh PWM từ chân **`D3 (GPIO0)`** qua mạch RC trên PCB Hub (`J11/J12`) phát ra loa tròn bạc. |
| **6** | **Loa tròn mini màu bạc (`28 mm, 8 Ω, 0.5 W`)** | **01 cái** | Loa phản hồi phần cứng đấu vào 2 pad **`L OUT +`** và **`L OUT -`** của `PAM8403` (cầu vi sai BTL, không nối GND). |
| **7** | **Cảm biến Nhiệt độ & Độ ẩm `DHT11` module 3 chân PCB xanh dương** | **01 cái** | Cảm biến **`DHT11`** gắn cổng **`J13` (`D2 / GPIO4`)**, cấp nguồn `3.3V` (điện trở kéo lên `R3 10kΩ` hàn trên PCB Hub). |
| **8** | **Cảm biến Độ ẩm Đất** *(đầu dò 2 nhánh `YL-69` + mạch so sánh **`LM393` xanh dương**)* | **01 bộ** | Cấp nguồn **`3.3V`** từ **`J14`** cho `LM393`, nối **`AO`** vào **`A0 (ADC0)`** (lọc tụ `C7 100nF` trên PCB). Tự động bật bơm `< 40%`, tắt bơm `>= 70%`. |
| **9** | **Cảm biến Âm thanh `KY-037 / KY-038` PCB đỏ** *(header `DO \| G \| + \| AO`, biến trở `W104`)* | **01 cái** | Cấp nguồn **`3.3V`** từ **`J15`**, nối chân **`DO`** vào **`D5 (GPIO14)`** để phát hiện tiếng vỗ tay / tiếng động lớn. |
| **10** | **Động cơ `Servo SG90 9g` màu xanh dương** *(kèm tay đòn trắng + cáp 3 dây cam/đỏ/nâu)* | **01 cái** | Điều khiển **`main_door` (Cửa chính)** tại cổng **`J3` (`D1 / GPIO5`)**, góc `0°` đóng / `90°` mở. |
| **11** | **Bóng đèn `LED 5mm`** | **02 bóng** | Làm **`living_room_light` (`J4` — `D0 / GPIO16`)** và **`bedroom_light` (`J5` — `D4 / GPIO2`, đấu Active-LOW)**. |
| **12** | **Còi `Buzzer 5V` trụ đen `TMB12A05`** | **01 cái** | Làm **`alarm_siren` (Còi báo động)** tại cổng **`J6` (`D8 / GPIO15`)**, lái low-side qua `Q1 S8050` + `D2 1N4007` trên PCB Hub. |
| **13** | **Máy bơm nước chìm mini màu trắng `3V–6V DC`** | **01 cái** | Cấp nguồn `5V` đóng cắt qua domino vít **`J2`** (được bảo vệ bởi `D1 1N4007` & `C2 470µF 16V` trên PCB Hub). |
| **14** | **Diode `1N4007` (`D1, D2`) + Tụ lọc (`C1–C9`)** | **2 diode + 9 tụ** | **`D1 1N4007`** (bơm `J2`), **`D2 1N4007`** (còi `J6`), **`C1/C2 470µF 16V`** (`+5V`), **`C3/C6/C7/C8 100nF 50V`**, **`C4 10µF 16V`**, **`C5 10nF 50V`**, **`C9 100µF 16V`** — **tất cả hàn trực tiếp trên PCB Hub DIY v3**. |
| **15** | **Điện trở `1/4W` (`R1–R10`) + Transistor `Q1 (S8050)` + Dây nối Dupont (`10 / 20 / 30 cm`)** | **Đầy đủ** | Tất cả 40 dây nối đều `<= 30 cm` (`3.84–27.48 cm`); xem bảng mua bó dây tiêu chuẩn tại [`WIRE_LIST_LENGTHS.md`](WIRE_LIST_LENGTHS.md). |

> **Ghi chú linh kiện phụ & chính sách khóa phạm vi:** Toàn bộ hệ thống chỉ sử dụng đúng **6 thiết bị chấp hành + 3 cảm biến** trên **PCB Hub DIY v3** (**không dùng breadboard trắng, không có quạt, không có điều hòa 220V, không có hồng ngoại IR**).

---

## 2. KIẾN TRÚC ÂM THANH: PHÂN BIỆT RÕ MICRO VOICE AI & CẢM BIẾN KY-037

Để tránh nhầm lẫn khi bảo vệ đồ án, hệ thống tách bạch 3 khối âm thanh như sau:

1. **Micro & Loa cho Trợ lý Giọng nói Gemini Voice AI (`gemini-3.8-live`, giọng `Aoede`):**
   - Sử dụng trực tiếp **micro và loa của thiết bị Web Dashboard / Mobile App** của người dùng.
   - ESP8266 **không** truyền luồng giọng nói thô qua chân `RX` hay `A0`. Cổng `RX/TX` chỉ dùng để debug Serial `115200 baud` qua USB CP2102.
2. **Cảm biến Âm thanh `KY-037/038` (`D5 / GPIO14` — `J15`):**
   - Đọc ngõ ra số **`DO`** để phát hiện **tiếng vỗ tay hoặc âm thanh đột ngột** vượt ngưỡng chỉnh trên biến trở xanh `W104`.
   - Khi có xung kích hợp lệ (debounce `>= 400ms`), ESP8266 gửi telemetry `smarthome/telemetry/sound` (hoặc `POST /api/sound_sensor`) về Dashboard.
3. **Mạch Loa Phản hồi `PAM8403` + Loa tròn bạc (`D7` + `D3` — `J9/J10/J11/J12`):**
   - **Relay 2 (`D7 / GPIO13`)** đóng/ngắt nguồn `5V` cho `PAM8403` để mạch loa hoàn toàn im lặng (không sôi nhiễu) khi nghỉ; nguồn `AMP_5V` được lọc ngay trên PCB Hub bằng **`C6 100nF 50V` song song `C9 100µF 16V`**.
   - **Chân `D3 (GPIO0)`** phát xung `tone()` qua **`R4 10kΩ`** kéo lên `+3.3V`, **tụ chặn DC `C4 10µF 16V`**, cầu phân áp **`R5/R6 2.2kΩ`** và tụ lọc **`C5 10nF`** tới ngõ vào `L` của `PAM8403` khi phát chuông xác nhận, sau đó tự tắt Relay 2 sau `1.5 giây` nếu không bật giữ tay.

---

## 3. VẬT TƯ GIA CÔNG PCB HUB DIY v3 & DÂY NỐI CHUẨN (`<= 30 cm`)

1. **Bộ linh kiện hàn trên PCB Hub DIY v3 (`100 × 80 × 1.6 mm`, `51 footprints`, `0 ERC / 0 DRC`):**
   - Xem đầy đủ tại [`diy_pcb/BOM_DIY_SHOPPING.md`](diy_pcb/BOM_DIY_SHOPPING.md), hướng dẫn ủi/ăn mòn/khoan/hàn tại [`diy_pcb/DIY_GUIDE.md`](diy_pcb/DIY_GUIDE.md), danh sách 7 dây nhảy mặt trên tại [`diy_pcb/jumper_list.md`](diy_pcb/jumper_list.md), ảnh render 3D/2D tại [`diy_pcb/`](diy_pcb/) và bản in 1:1 lật gương tại [`diy_pcb/toner_B.Cu_MIRRORED_1to1.pdf`](diy_pcb/toner_B.Cu_MIRRORED_1to1.pdf).
   - **Toàn bộ 9 tụ điện & 2 diode bảo vệ đều hàn trực tiếp trên PCB Hub:** `C1/C2 470µF 16V`, `C3 100nF 50V`, `C4 10µF 16V`, `C5 10nF 50V`, `C6 100nF 50V`, `C7 100nF 50V`, **`C8 100nF 50V` (cạnh `J14`, lọc `+3V3` cùng tụ 10µF AMS1117 trên NodeMCU v2 Amica)**, **`C9 100µF 16V` (cạnh `J11`, lọc nguồn loa `AMP_5V` song song `C6`)**, **`D1 1N4007`** (bơm `J2`), **`D2 1N4007`** (còi `J6`), cùng `D3` LED nguồn xanh 3 mm, `Q1` NPN `S8050`, `R1–R10`, `U1/U2` (`1×15P 2.54 mm`), `J1–J2` (`Phoenix MKDS 5.08 mm`), `J3–J15` (`Header 2.54 mm`), và `JP1–JP7`.
2. **Dây cắm Dupont & dây nguồn 22AWG (`40/40 dây <= 30 cm`):**
   - Kiểm tra chi tiết từng dây (`3.84 – 27.48 cm`) và bảng tổng hợp mua theo cỡ chuẩn **`10 cm` (10 sợi) · `20 cm` (18 sợi) · `30 cm` (12 sợi)** tại [`WIRE_LIST_LENGTHS.md`](WIRE_LIST_LENGTHS.md).
3. **Ống nhựa silicon mềm đường kính trong `6mm–8mm` (`~1m`):**
   - Nối đầu xả (`OD 7.5 mm`) của máy bơm nước mini trắng vào chậu cây trên sa bàn.
4. **Củ nguồn ngoài `5V - 2A` + Giắc `DC-022` + cáp `Micro-USB` truyền dữ liệu:**
   - Cấp nguồn qua cổng `J1` (`PWR_5V_IN`), tránh sụt áp USB Laptop khi `Servo SG90`, `Máy bơm` và `PAM8403` chạy đồng thời.

---

## 4. BẢNG SƠ ĐỒ 10 CHÂN KHÓA CỨNG & QUY TẮC AN TOÀN BOOT

Sơ đồ chân dưới đây đồng bộ 100% với Firmware [`esp8266_smarthome.ino`](../../firmware/esp8266_smarthome/esp8266_smarthome.ino) và [`WIRING_TABLE.md`](WIRING_TABLE.md):

| Chân NodeMCU | GPIO | Thiết bị / Cảm biến | Cổng PCB Hub | Cách đấu dây chuẩn & Linh kiện hàn trên PCB |
| :---: | :---: | :--- | :---: | :--- |
| **`D0`** | `GPIO16` | `living_room_light` (Đèn phòng khách) | `J4` | `D0 -> R1 220Ω -> J4.1 -> LED(+) -> LED(-) -> J4.2 (GND)` (Active-HIGH, kiêm nháy `enroll_blink`). |
| **`D1`** | `GPIO5` | `main_door` (Servo SG90 Cửa chính) | `J3` | `J3.1` tín hiệu cam (`D1`), `J3.2` `+5V` (lọc `C1 470µF 16V`), `J3.3` `GND`. |
| **`D2`** | `GPIO4` | `dht11` (Cảm biến Nhiệt độ & Độ ẩm) | `J13` | `J13.1` `+3V3`, `J13.2` `DATA -> D2` (kéo lên `R3 10kΩ` trên PCB), `J13.3` `GND`. |
| **`D3`** | `GPIO0` | Ngõ ra âm thanh PWM tới `PAM8403` | `J12` | `R4 10kΩ` kéo `D3` lên `+3.3V`; `D3 -> C4 10µF 16V -> R5 2.2kΩ -> [AUD_OUT] -> R6 2.2kΩ & C5 10nF -> GND`; nối `J12` vào `L` và `⊥` của `PAM8403`. |
| **`D4`** | `GPIO2` | `bedroom_light` (Đèn phòng ngủ) | `J5` | **Đấu Active-LOW:** `+3V3 -> R2 220Ω -> J5.1 -> LED(+) -> LED(-) -> J5.2 -> D4` + `R7 10kΩ` pull-up (`BEDROOM_LED_ACTIVE_LOW = true`). |
| **`D5`** | `GPIO14` | `ky037` (Cảm biến âm thanh `DO`) | `J15` | `J15.1` `+3V3`, `J15.2` `GND`, `J15.3` `DO -> D5`, bỏ trống `AO`. |
| **`D6`** | `GPIO12` | `garden_pump` (Relay 1 xanh + Bơm trắng) | `J7`, `J8`, `J2` | `J7` điều khiển cuộn hút (`+5V/GND/D6`); `J8` nối tiếp điểm `COM/NO`; `J2` ra bơm có **`D1 1N4007`** & **`C2 470µF 16V`** trên PCB. |
| **`D7`** | `GPIO13` | `speaker_amp` (Relay 2 đỏ opto -> `PAM8403`) | `J9`, `J10`, `J11` | Đặt jumper vàng về **`H`**; `J9` điều khiển cuộn hút; `J10` nối `COM/NO`; `J11` cấp `AMP_5V` (đã lọc **`C6 100nF + C9 100µF 16V`** trên PCB) vào `PAM8403 5V+/5V-`. |
| **`D8`** | `GPIO15` | `alarm_siren` (Còi Buzzer 5V) | `J6` | **Active-HIGH** qua mạch lái low-side NPN trên PCB (`R9 10kΩ` kéo xuống `GND`; `R10 1kΩ -> Q1 S8050`; `J6.1 +5V`, `J6.2 Q1.C`; kẹp **`D2 1N4007`** trên PCB). |
| **`A0`** | `ADC0` | `soil_moisture` (Độ ẩm đất + `LM393`) | `J14` | Cấp nguồn **`LM393 VCC -> J14.1 (+3V3)`**, `GND -> J14.2`, `AO -> J14.3 (A0)` (lọc `C7 100nF` & `C8 100nF` trên PCB; bỏ trống `DO`). |
| **`VIN / 3V3 / GND`** | `Power` | Nguồn hệ thống | `J1` | Nguồn `5V 2A` vào `J1` nuôi `VIN` + Servo + 2 Relay + Bơm; `3V3` nuôi `DHT11`, `KY-037`, `LM393`, `D4 LED`; nối chung `GND` toàn mạch. |

### Checklist An toàn Boot & Bảo vệ Điện tử (Bắt buộc kiểm tra trước khi cấp nguồn)

- [ ] **`D3 (GPIO0)` dùng đúng tụ chặn DC `C4 10µF 16V` kèm `R4 10kΩ` pull-up + `R5/R6 2.2kΩ` + `C5 10nF`:** Hàn đầy đủ trên PCB Hub để tách DC và tránh kéo `GPIO0` xuống `LOW` khi reset; luôn trả `D3` về trạng thái `INPUT` khi không phát âm.
- [ ] **`PAM8403` ngõ ra loa là mạch cầu BTL (`L OUT + / -`):** Chỉ nối 2 dây loa tròn bạc vào `L OUT +` và `L OUT -`, **tuyệt đối không nối một đầu loa xuống `GND`** để tránh chập IC `PAM8403`.
- [ ] **`D4 (GPIO2)` đấu Active-LOW khớp Firmware:** `+3.3V -> R2 220Ω -> LED(+) -> LED(-) -> D4` giúp `GPIO2` luôn được kéo lên `HIGH` khi boot và đèn ngủ tắt hoàn toàn khi mới bật nguồn (`BEDROOM_LED_ACTIVE_LOW = true`).
- [ ] **`D8 (GPIO15)` giữ mức `LOW` khi boot:** Mạch lái `R9 10kΩ -> GND`, `R10 1kΩ -> Q1 S8050` hàn trên PCB đảm bảo `GPIO15` luôn LOW lúc khởi động, không kêu còi giả.
- [ ] **`A0` & `D5` chỉ cấp `3.3V` cho `LM393` và `KY-037`:** Không cấp `5V` vào `LM393` hay `KY-037` vì ngõ ra `AO` / `DO` vượt `3.3V` sẽ gây sai số hoặc hỏng chân `A0` / `GPIO14` của ESP8266.
- [ ] **Bảo vệ tải cảm ứng & Lọc nguồn đầy đủ trên PCB (`D1, D2`, `C1`–`C9`):** Kiểm tra đúng chiều **Diode `D1 1N4007`** (`K→PUMP_5V`, `A→GND`) và **`D2 1N4007`** (`K→+5V`, `A→Q1.C`/`BUZZ_K`); kiểm tra cực tính tụ hóa **`C1/C2 470µF 16V`**, **`C4 10µF 16V`**, **`C9 100µF 16V`** và tụ gốm **`C3, C5, C6, C7, C8`** đã hàn đủ trực tiếp trên PCB Hub DIY v3.
- [ ] **Kiểm tra cực tính Relay 1 (`D6`) & Relay 2 (`D7`):** Trên Relay 2 đỏ opto, gạt jumper vàng sang **`H`** (kích mức `HIGH`). Với Relay 1 xanh dương, xác nhận kích mức `HIGH` khớp `PUMP_RELAY_ACTIVE_LOW = false`.
