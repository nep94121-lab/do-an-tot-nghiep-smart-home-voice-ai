# 📋 KIỂM KÊ LINH KIỆN THỰC TẾ TRÊN BÀN & SƠ ĐỒ ĐẤU NỐI PHẦN CỨNG

> **Cập nhật ngày `20/11/2026` — Đối chiếu trực tiếp từ 2 ảnh chụp thực tế của Nguyễn Tuấn Anh (`components_overview.png` & `pam8403_ky037_closeup.png`) và Hợp đồng Phần cứng Khóa cứng (`6 thiết bị chấp hành + 3 cảm biến`).**

---

## 1. TOÀN BỘ LINH KIỆN ĐANG CÓ SẴN TRÊN BÀN (ĐÃ ĐỦ 100% CHO BỘ 6 THIẾT BỊ + 3 CẢM BIẾN)

Đối chiếu từ `components_overview.png` và `pam8403_ky037_closeup.png`, toàn bộ linh kiện cốt lõi đã **có sẵn trên bàn**:

| STT | Linh kiện thực tế quan sát trên ảnh | Số lượng | Vai trò & Chân kết nối trên `NodeMCU ESP8266 v2 Amica` |
| :---: | :--- | :---: | :--- |
| **1** | **Mạch `NodeMCU ESP8266 v2 Amica` (ESP-12E/F, CP2102, hàng chân hẹp 0.9" / 22.86mm `2×15`)** | **01 mạch** | Bộ vi điều khiển trung tâm Wi-Fi 2.4GHz, chạy MQTT + HTTP sync và lưu bản sao 2 Bể vào Flash `LittleFS`. |
| **2** | **Bảng cắm `Breadboard 400 lỗ` màu trắng** | **01 cái** | Cắm trực tiếp NodeMCU qua rãnh giữa, chia nguồn `3.3V` / `5V` / `GND` và cắm LED, trở, tụ, diode. |
| **3** | **Module Relay 1 kênh 5V màu xanh dương** *(trên giữa ảnh)* | **01 cái** | **Relay 1 (`D6 / GPIO12` — `garden_pump`):** Đóng/ngắt nguồn `5V` ngoài cho **Máy bơm nước mini trắng**. |
| **4** | **Module Relay 1 kênh 5V opto cách ly màu đỏ** *(góc dưới phải, có jumper vàng `H/L` và 3 dây cắm)* | **01 cái** | **Relay 2 (`D7 / GPIO13` — `speaker_amp`):** Đặt jumper ở mức **`H`**, đóng/ngắt nguồn `5V` cho mạch khuếch đại loa **PAM8403**. |
| **5** | **Mạch khuếch đại âm thanh `PAM8403` PCB xanh lá** *(bản không chiết áp, pad hàn `L OUT R`, `L ⊥ R`, `5V + -`)* | **01 mạch** | Khuếch đại tín hiệu âm thanh PWM từ chân **`D3 (GPIO0)`** (qua tụ chặn DC + cầu phân áp RC) phát ra loa tròn bạc. |
| **6** | **Loa tròn mini màu bạc** *(bọc nilon kèm dây đỏ/đen và bó dây Dupont 4 sợi)* | **01 cái** | Loa phản hồi phần cứng đấu vào 2 pad **`L OUT +`** và **`L OUT -`** của `PAM8403`. |
| **7** | **Cảm biến Nhiệt độ & Độ ẩm `DHT11` module 3 chân PCB xanh dương** | **01 cái** | Cảm biến **`DHT11`** gắn chân **`D2 (GPIO4)`**, cấp nguồn `3.3V`. |
| **8** | **Cảm biến Độ ẩm Đất** *(đầu dò 2 nhánh + dây vàng nối mạch so sánh **`LM393` xanh dương**)* | **01 bộ** | Cấp nguồn **`3.3V`** cho `LM393`, nối **`AO`** vào **`A0 (ADC0)`**. Tự động bật bơm `< 40%`, tắt bơm `>= 70%`. |
| **9** | **Cảm biến Âm thanh `KY-037 / KY-038` PCB đỏ** *(header `DO \| G \| + \| AO`, biến trở xanh `W104`, IC `LM393`, micro tụ điện)* | **01 cái** | Cấp nguồn **`3.3V`**, nối chân **`DO`** vào **`D5 (GPIO14)`** để phát hiện tiếng vỗ tay / tiếng động lớn. |
| **10** | **Động cơ `Servo SG90 9g` màu xanh dương** *(kèm tay đòn trắng + cáp 3 dây cam/đỏ/nâu)* | **01 cái** | Điều khiển **`main_door` (Cửa chính)** tại chân **`D1 (GPIO5)`**, góc `0°` đóng / `90°` mở. |
| **11** | **Túi bóng đèn `LED 5mm`** *(cùng 1 LED đỏ rời cạnh bó dây loa)* | **01 túi + 1 lẻ** | Dùng 2 bóng làm **`living_room_light` (`D0 / GPIO16`)** và **`bedroom_light` (`D4 / GPIO2`, đấu Active-LOW)**. |
| **12** | **Còi `Buzzer 5V` trụ đen nhỏ** *(trong túi zip góc trên trái)* | **01 cái** | Làm **`alarm_siren` (Còi báo động)** tại chân **`D8 (GPIO15)`**, đấu Active-HIGH (im lặng khi boot). |
| **13** | **Máy bơm nước chìm mini màu trắng `3V–6V DC`** *(góc dưới trái, kèm dây đen tách đầu đỏ/đen)* | **01 cái** | Chạy nguồn `5V` ngoài qua tiếp điểm **`COM–NO`** của Relay 1 (`D6`). |
| **14** | **Dải `3× Diode 1N4007`** + **Túi tụ `WEIDILY 470µF 16V 8×12`** | **3 diode + 1 túi tụ** | `D1 1N4007` mắc ngược song song cực bơm (`K→PUMP_5V`, `A→GND`) & `D2 1N4007` song song còi 5V (`K→+5V`, `A→Q1.C`); tụ `C1/C2 470µF 16V` lọc nguồn `5V` cho bơm/servo/relay. |
| **15** | **Túi điện trở `WEIDILY 1/4W 2.2kΩ 1%`** + **2 dải điện trở cắm 1/4W** + **Dây Dupont** | **Đầy đủ** | Hạn dòng LED (`220Ω–1kΩ` hoặc `2.2kΩ`) và làm cầu phân áp RC bảo vệ ngõ vào `PAM8403` từ `D3`. |

> **Ghi chú linh kiện phụ:** Trên ảnh `components_overview.png` có 1 linh kiện 3 chân vỏ đen kiểu TO-220 nằm ngay dưới mạch `PAM8403` — linh kiện này **không bắt buộc dùng trong mạch chính** của hợp đồng 6 thiết bị + 3 cảm biến. Toàn bộ hệ thống chỉ sử dụng đúng 6 thiết bị chấp hành và 3 cảm biến nêu trên.

---

## 2. KIẾN TRÚC ÂM THANH: PHÂN BIỆT RÕ MICRO VOICE AI & CẢM BIẾN KY-037

Để tránh nhầm lẫn khi bảo vệ đồ án, hệ thống tách bạch 3 khối âm thanh như sau:

1. **Micro & Loa cho Trợ lý Giọng nói Gemini Voice AI (`gemini-3.8-live`, giọng `Aoede`):**
   - Sử dụng trực tiếp **micro và loa của thiết bị Web Dashboard / Mobile App** của người dùng.
   - ESP8266 **không** truyền luồng giọng nói thô qua chân `RX` hay `A0`. Cổng `RX/TX` chỉ dùng để debug Serial `115200 baud` qua USB CP2102.
2. **Cảm biến Âm thanh `KY-037/038` (`D5 / GPIO14`):**
   - Đọc ngõ ra số **`DO`** để phát hiện **tiếng vỗ tay hoặc âm thanh đột ngột** vượt ngưỡng chỉnh trên biến trở xanh `W104`.
   - Khi có xung kích hợp lệ (debounce `>= 400ms`), ESP8266 gửi telemetry `smarthome/telemetry/sound` (hoặc `POST /api/sound_sensor`) về Dashboard.
3. **Mạch Loa Phản hồi `PAM8403` + Loa tròn bạc (`D7` + `D3`):**
   - **Relay 2 (`D7 / GPIO13`)** đóng/ngắt nguồn `5V` cho `PAM8403` để mạch loa hoàn toàn im lặng (không sôi nhiễu) khi nghỉ.
   - **Chân `D3 (GPIO0)`** phát xung `tone()` qua **`R4 10kΩ`** kéo lên `+3.3V`, **tụ chặn DC `C4 10µF 16V`**, cầu phân áp **`R5/R6 2.2kΩ`** và tụ lọc **`C5 10nF`** tới ngõ vào `L` của `PAM8403` khi phát chuông xác nhận, sau đó tự tắt Relay 2 sau `1.5 giây` nếu không bật giữ tay.

---

## 3. DANH SÁCH TÙY CHỌN / MUA THÊM SAU (CHỈ PHẦN BỔ SUNG, KHÔNG CẦN MUA LINH KIỆN CỐT LÕI)

**0 linh kiện chấp hành hay cảm biến cốt lõi nào phải mua thêm** để chạy đủ 6 thiết bị + 3 cảm biến trên Breadboard. Dưới đây chỉ là các món **tùy chọn / mua bổ sung về sau** (khi lắp sa bàn hoặc chuyển sang hàn PCB):

1. **Tụ hóa `C4 10µF 16V`, `C9 100µF 16V`, tụ gốm `C5 10nF` / `C3, C6, C7, C8 100nF (104) 50V` + rào cắm `Header 2.54mm`:**
   - Dùng `C4 10µF 16V` làm tụ chặn DC nối tiếp + `C5 10nF` làm tụ lọc RC trên đường tín hiệu âm thanh `D3 -> PAM8403`; dùng `C8 100nF 50V` lọc nhiễu cao tần trên rail `+3.3V` (`U1.11/U2.6` & `J13/J14/J15`, bổ sung cho tụ tantalum `10µF` của AMS1117-3.3 trên NodeMCU v2 Amica) và `C9 100µF 16V` gắn sát `J11` / pad `5V+/5V-` của `PAM8403` (song song `C6 100nF`) đúng khuyến nghị datasheet; đồng thời hàn chân cắm lên 2 hàng lỗ trống của mạch `PAM8403` (`pam8403_ky037_closeup.png`).
2. **Ống nhựa silicon mềm đường kính trong `6mm–8mm` (`~1m`):**
   - Nối đầu xả của máy bơm nước mini trắng vào chậu cây trên sa bàn (nếu chưa cắt sẵn).
3. **Dây cắm Dupont `20cm` (`M-M`, `M-F`, `F-F`) dự phòng:**
   - Mua thêm nếu số sợi dây hiện có trên bàn không đủ đi gọn trong vỏ mô hình nhà.
4. **Củ nguồn ngoài `5V - 2A` + dây cáp `Micro-USB` truyền dữ liệu:**
   - Rất nên dùng khi demo thực tế để tránh sụt áp cổng USB Laptop khi `Servo SG90`, `Máy bơm` và `PAM8403` chạy đồng thời (nối chung `GND` với NodeMCU).
5. **Vật tư cho giai đoạn tự làm mạch PCB 1 lớp tại nhà (Toner Transfer + Khoan tay — `SmartHome Hub DIY v3.0`, `100 × 80 × 1.6 mm`):**
   - Xem bảng BOM mua sắm đầy đủ và kích thước mũi khoan tại [`diy_pcb/BOM_DIY_SHOPPING.md`](diy_pcb/BOM_DIY_SHOPPING.md), hướng dẫn ủi/ăn mòn/khoan/hàn tại [`diy_pcb/DIY_GUIDE.md`](diy_pcb/DIY_GUIDE.md), danh sách 7 dây nhảy mặt trên tại [`diy_pcb/jumper_list.md`](diy_pcb/jumper_list.md) và bản in 1:1 lật gương tại [`diy_pcb/toner_B.Cu_MIRRORED_1to1.pdf`](diy_pcb/toner_B.Cu_MIRRORED_1to1.pdf).
   - Danh mục cần chuẩn bị thêm: 1 tấm phíp đồng 1 mặt `FR-4` `1.6 mm` (`>= 100 × 80 mm`), 2 thanh rào cái `1×15P 2.54 mm` (đế NodeMCU), rào đực `1×40P 2.54 mm` (cắt cho `J3..J15`), 2 domino vít `Phoenix MKDS / KF301 2P 5.08 mm` (`J1, J2`), 1 transistor NPN `S8050` (hoặc `2N2222A`, vỏ `TO-92` chân `E-B-C` cho `Q1` lái còi 5V), tụ hóa `10 µF 16V` (`C4`) + `100 µF 16V` (`C9` gắn ngoài tại `J11`/PAM8403) + `470 µF 16V` (`C1, C2`), tụ gốm `100 nF 50V` (`C3, C6, C7` trên bo + `C8` ngoài bo trên `+3V3`) + `10 nF 50V` (`C5`), LED xanh 3 mm (`D3`), trở 1/4W (`220 Ω`, `1 kΩ` gồm `R8` & `R10`, `2.2 kΩ`, `10 kΩ`), dây lõi đặc `22 AWG` (làm 7 dây nhảy `JP1..JP7`), 4 bộ ốc trụ `M3`, và đúng 4 mũi khoan `0.9 / 1.1 / 1.3 / 3.2 mm`.

---

## 4. BẢNG SƠ ĐỒ 10 CHÂN KHÓA CỨNG & QUY TẮC AN TOÀN BOOT

Sơ đồ chân dưới đây đồng bộ 100% với Firmware [`esp8266_smarthome.ino`](../../firmware_esp8266/esp8266_smarthome/esp8266_smarthome.ino):

| Chân NodeMCU | GPIO | Thiết bị / Cảm biến | Cách đấu dây chuẩn & Linh kiện đi kèm |
| :---: | :---: | :--- | :--- |
| **`D0`** | `GPIO16` | `living_room_light` (Đèn phòng khách) | `D0 -> Trở 220Ω–470Ω -> LED(+) -> LED(-) -> GND` (Active-HIGH, kiêm nháy `enroll_blink`). |
| **`D1`** | `GPIO5` | `main_door` (Servo SG90 Cửa chính) | Dây tín hiệu (cam/vàng) vào `D1`; dây đỏ vào `+5V` (kèm tụ `470µF 16V` lọc nguồn); dây nâu vào `GND`. |
| **`D2`** | `GPIO4` | `dht11` (Cảm biến Nhiệt độ & Độ ẩm) | `VCC -> 3V3`, `GND -> GND`, `DATA -> D2` (module xanh đã có sẵn điện trở kéo lên). |
| **`D3`** | `GPIO0` | Ngõ ra âm thanh PWM tới `PAM8403` | `R4 10kΩ` kéo `D3` lên `+3.3V`; `D3 -> Tụ chặn DC C4 10µF 16V -> R5 2.2kΩ -> [AUD_OUT] -> R6 2.2kΩ & C5 10nF -> GND`; nối `[AUD_OUT]` vào chân `L` và `GND` vào pad `⊥` của `PAM8403`. |
| **`D4`** | `GPIO2` | `bedroom_light` (Đèn phòng ngủ) | **Đấu Active-LOW:** `3V3 -> Trở 220Ω–1kΩ -> LED(+) -> LED(-) -> D4` (khớp `BEDROOM_LED_ACTIVE_LOW = true`). |
| **`D5`** | `GPIO14` | `ky037` (Cảm biến âm thanh `DO`) | Theo thứ tự chân trên PCB đỏ (`DO \| G \| + \| AO`): `+ -> 3V3`, `G -> GND`, `DO -> D5`, bỏ trống `AO`. |
| **`D6`** | `GPIO12` | `garden_pump` (Relay 1 xanh + Bơm trắng) | `VCC -> 5V`, `GND -> GND`, `IN -> D6`; `COM -> +5V ngoài`, `NO -> Bơm(+)`, `Bơm(-) -> GND`; kẹp **`1N4007`** (vạch bạc về phía `Bơm(+)`) và tụ **`470µF 16V`** trên rail `5V`. |
| **`D7`** | `GPIO13` | `speaker_amp` (Relay 2 đỏ opto -> `PAM8403`) | Đặt jumper vàng về **`H`**; `DC+ -> 5V`, `DC- -> GND`, `IN -> D7`; `COM -> +5V`, `NO -> chân 5V+ của PAM8403`; pad `5V-` của `PAM8403 -> GND`. |
| **`D8`** | `GPIO15` | `alarm_siren` (Còi Buzzer 5V) | Đấu **Active-HIGH** qua mạch lái low-side NPN trên PCB (`D8 -> R9 10k -> GND` giữ LOW khi boot; `D8 -> R10 1k -> Q1 S8050 Base`, `E -> GND`, `Buzzer(+) -> +5V`, `Buzzer(-) -> Q1 Collector`, kẹp `D2 1N4007` song song còi). Tuyệt đối không gắn pull-up lên `3.3V`. |
| **`A0`** | `ADC0` | `soil_moisture` (Độ ẩm đất + `LM393`) | Cấp nguồn **`LM393 VCC -> 3V3`**, `GND -> GND`, `AO -> A0` (bỏ trống `DO`). |
| **`VIN / 3V3 / GND`** | `Power` | Nguồn hệ thống | Nguồn công suất `5V` vào `VIN` + Servo + 2 Relay + Bơm; `3V3` nuôi `DHT11`, `KY-037`, `LM393`, `D4 LED`; nối chung `GND` toàn mạch. |

### Checklist An toàn Boot & Bảo vệ Điện tử (Bắt buộc kiểm tra trước khi cấp nguồn)

- [ ] **`D3 (GPIO0)` dùng đúng tụ chặn DC `C4 10µF 16V` kèm `R4 10kΩ` pull-up + `R5/R6 2.2kΩ` + `C5 10nF`:** Giữ đúng giá trị trên PCB Hub để tách DC và tránh kéo `GPIO0` xuống `LOW` khi reset; luôn trả `D3` về trạng thái `INPUT` khi không phát âm.
- [ ] **`PAM8403` ngõ ra loa là mạch cầu BTL (`L OUT + / -`):** Chỉ nối 2 dây loa tròn bạc vào `L OUT +` và `L OUT -`, **tuyệt đối không nối một đầu loa xuống `GND`** để tránh chập IC `PAM8403`.
- [ ] **`D4 (GPIO2)` đấu Active-LOW khớp Firmware:** Dây `3.3V -> Trở -> LED(+) -> LED(-) -> D4` giúp `GPIO2` luôn được kéo lên `HIGH` khi boot và đèn ngủ tắt hoàn toàn khi mới bật nguồn (`BEDROOM_LED_ACTIVE_LOW = true`).
- [ ] **`D8 (GPIO15)` giữ mức `LOW` khi boot:** Chỉ đấu tải xuống `GND` (Active-HIGH), không mắc bất kỳ điện trở kéo lên `3.3V` nào trên chân `D8`.
- [ ] **`A0` & `D5` chỉ cấp `3.3V` cho `LM393` và `KY-037`:** Không cấp `5V` vào `LM393` hay `KY-037` vì ngõ ra `AO` / `DO` vượt `3.3V` sẽ gây sai số hoặc hỏng chân `A0` / `GPIO14` của ESP8266.
- [ ] **Bảo vệ tải cảm ứng & Lọc nguồn đầy đủ (`D1, D2`, `C1`–`C9`):** Gắn đúng chiều **Diode `D1 1N4007`** (vạch bạc `K` nối `PUMP_5V`, `A` nối `GND`) và **`D2 1N4007`** (vạch bạc `K` nối `+5V`, `A` nối `Q1.C`/`BUZZ_K`); đặt tụ hóa **`C1/C2 470µF 16V`** + tụ gốm **`C3 100nF 50V`** trên rail `+5V`, tụ **`C8 100nF 50V`** trên rail `+3.3V` (bổ sung cho tụ `10µF` AMS1117 trên NodeMCU), tụ **`C6 100nF 50V` + `C9 100µF 16V`** trên `AMP_5V` (PAM8403), và **`C7 100nF 50V`** lọc chân `A0` cảm biến đất.
- [ ] **Kiểm tra cực tính Relay 1 (`D6`) & Relay 2 (`D7`):** Trên Relay 2 đỏ opto, gạt jumper vàng sang **`H`** (kích mức `HIGH`). Với Relay 1 xanh dương (không có jumper lộ ngoài), test nhanh `5V/GND/IN` trước khi lắp tải; nếu module kích mức `LOW`, đổi `#define PUMP_RELAY_ACTIVE_LOW true` trong `esp8266_smarthome.ino`.
