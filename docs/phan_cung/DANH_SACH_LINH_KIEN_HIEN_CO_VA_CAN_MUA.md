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
| **14** | **Dải `3× Diode 1N4007`** + **Túi tụ `WEIDILY 470µF 16V 8×12`** | **3 diode + 1 túi tụ** | `1N4007` mắc ngược song song cực bơm (Flyback Diode); tụ `470µF 16V` lọc nguồn `5V` cho bơm/servo/relay. |
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
   - **Chân `D3 (GPIO0)`** phát xung `tone()` qua **tụ chặn DC (`100nF–1µF`) + cầu phân áp RC** tới ngõ vào `L` của `PAM8403` khi phát chuông xác nhận, sau đó tự tắt Relay 2 sau `1.5 giây` nếu không bật giữ tay.

---

## 3. DANH SÁCH TÙY CHỌN / MUA THÊM SAU (CHỈ PHẦN BỔ SUNG, KHÔNG CẦN MUA LINH KIỆN CỐT LÕI)

**0 linh kiện chấp hành hay cảm biến cốt lõi nào phải mua thêm** để chạy đủ 6 thiết bị + 3 cảm biến trên Breadboard. Dưới đây chỉ là các món **tùy chọn / mua bổ sung về sau** (khi lắp sa bàn hoặc chuyển sang hàn PCB):

1. **Tụ gốm / tụ màng mỏng giá trị nhỏ `100nF (104)` hoặc `1µF` (`1–2 con`) + rào cắm `Header 2.54mm`:**
   - Dùng làm tụ chặn DC nối tiếp trên đường tín hiệu âm thanh `D3 -> PAM8403` (nếu trong túi linh kiện phụ chưa có sẵn tụ nhỏ hơn `470µF`) và hàn chân cắm lên 2 hàng lỗ trống của mạch `PAM8403` (`pam8403_ky037_closeup.png`).
2. **Ống nhựa silicon mềm đường kính trong `6mm–8mm` (`~1m`):**
   - Nối đầu xả của máy bơm nước mini trắng vào chậu cây trên sa bàn (nếu chưa cắt sẵn).
3. **Dây cắm Dupont `20cm` (`M-M`, `M-F`, `F-F`) dự phòng:**
   - Mua thêm nếu số sợi dây hiện có trên bàn không đủ đi gọn trong vỏ mô hình nhà.
4. **Củ nguồn ngoài `5V - 2A` + dây cáp `Micro-USB` truyền dữ liệu:**
   - Rất nên dùng khi demo thực tế để tránh sụt áp cổng USB Laptop khi `Servo SG90`, `Máy bơm` và `PAM8403` chạy đồng thời (nối chung `GND` với NodeMCU).
5. **Vật tư cho giai đoạn hàn mạch PCB cố định (nếu chuyển từ Breadboard sang PCB):**
   - Rào cắm cái `Female Header 1x15P` (`2 thanh` cho NodeMCU), `Male Header 1x40P`, Domino `KF301-2P/3P`, giắc nguồn `DC-005`, công tắc nguồn `SS12D00`, nút nhấn `Tactile Switch 6x6mm`, tụ lọc `100nF`, phíp đồng `FR-4` và trụ đồng `M3`.

---

## 4. BẢNG SƠ ĐỒ 10 CHÂN KHÓA CỨNG & QUY TẮC AN TOÀN BOOT

Sơ đồ chân dưới đây đồng bộ 100% với Firmware [`esp8266_smarthome.ino`](../../firmware_esp8266/esp8266_smarthome/esp8266_smarthome.ino):

| Chân NodeMCU | GPIO | Thiết bị / Cảm biến | Cách đấu dây chuẩn & Linh kiện đi kèm |
| :---: | :---: | :--- | :--- |
| **`D0`** | `GPIO16` | `living_room_light` (Đèn phòng khách) | `D0 -> Trở 220Ω–470Ω -> LED(+) -> LED(-) -> GND` (Active-HIGH, kiêm nháy `enroll_blink`). |
| **`D1`** | `GPIO5` | `main_door` (Servo SG90 Cửa chính) | Dây tín hiệu (cam/vàng) vào `D1`; dây đỏ vào `+5V` (kèm tụ `470µF 16V` lọc nguồn); dây nâu vào `GND`. |
| **`D2`** | `GPIO4` | `dht11` (Cảm biến Nhiệt độ & Độ ẩm) | `VCC -> 3V3`, `GND -> GND`, `DATA -> D2` (module xanh đã có sẵn điện trở kéo lên). |
| **`D3`** | `GPIO0` | Ngõ ra âm thanh PWM tới `PAM8403` | `D3 -> Tụ chặn DC 100nF–1µF -> Trở 2.2kΩ -> [Nút Audio] -> Trở 1kΩ–2.2kΩ -> GND`; nối `[Nút Audio]` vào chân `L` và `GND` vào pad `⊥` của `PAM8403`. |
| **`D4`** | `GPIO2` | `bedroom_light` (Đèn phòng ngủ) | **Đấu Active-LOW:** `3V3 -> Trở 220Ω–1kΩ -> LED(+) -> LED(-) -> D4` (khớp `BEDROOM_LED_ACTIVE_LOW = true`). |
| **`D5`** | `GPIO14` | `ky037` (Cảm biến âm thanh `DO`) | Theo thứ tự chân trên PCB đỏ (`DO \| G \| + \| AO`): `+ -> 3V3`, `G -> GND`, `DO -> D5`, bỏ trống `AO`. |
| **`D6`** | `GPIO12` | `garden_pump` (Relay 1 xanh + Bơm trắng) | `VCC -> 5V`, `GND -> GND`, `IN -> D6`; `COM -> +5V ngoài`, `NO -> Bơm(+)`, `Bơm(-) -> GND`; kẹp **`1N4007`** (vạch bạc về phía `Bơm(+)`) và tụ **`470µF 16V`** trên rail `5V`. |
| **`D7`** | `GPIO13` | `speaker_amp` (Relay 2 đỏ opto -> `PAM8403`) | Đặt jumper vàng về **`H`**; `DC+ -> 5V`, `DC- -> GND`, `IN -> D7`; `COM -> +5V`, `NO -> chân 5V+ của PAM8403`; pad `5V-` của `PAM8403 -> GND`. |
| **`D8`** | `GPIO15` | `alarm_siren` (Còi Buzzer 5V) | Đấu **Active-HIGH**: `D8 -> Buzzer(+)`, `Buzzer(-) -> GND` (hoặc qua NPN + trở `1kΩ–2.2kΩ` nếu dùng nguồn `5V` riêng). Tuyệt đối không gắn pull-up lên `3.3V`. |
| **`A0`** | `ADC0` | `soil_moisture` (Độ ẩm đất + `LM393`) | Cấp nguồn **`LM393 VCC -> 3V3`**, `GND -> GND`, `AO -> A0` (bỏ trống `DO`). |
| **`VIN / 3V3 / GND`** | `Power` | Nguồn hệ thống | Nguồn công suất `5V` vào `VIN` + Servo + 2 Relay + Bơm; `3V3` nuôi `DHT11`, `KY-037`, `LM393`, `D4 LED`; nối chung `GND` toàn mạch. |

### Checklist An toàn Boot & Bảo vệ Điện tử (Bắt buộc kiểm tra trước khi cấp nguồn)

- [ ] **`D3 (GPIO0)` tuyệt đối KHÔNG dùng tụ `470µF` nối tiếp làm tụ chặn DC:** Hằng số thời gian `(10kΩ + 2.2kΩ) × 470µF ≈ 5.7 giây` sẽ kéo `GPIO0` xuống `LOW` khi reset và làm ESP8266 kẹt ở chế độ nạp UART. Luôn dùng tụ nhỏ **`100nF–1µF`** trước cầu phân áp RC `2.2kΩ / 1kΩ–2.2kΩ`, và giữ `D3` ở trạng thái `INPUT` khi không phát âm.
- [ ] **`PAM8403` ngõ ra loa là mạch cầu BTL (`L OUT + / -`):** Chỉ nối 2 dây loa tròn bạc vào `L OUT +` và `L OUT -`, **tuyệt đối không nối một đầu loa xuống `GND`** để tránh chập IC `PAM8403`.
- [ ] **`D4 (GPIO2)` đấu Active-LOW khớp Firmware:** Dây `3.3V -> Trở -> LED(+) -> LED(-) -> D4` giúp `GPIO2` luôn được kéo lên `HIGH` khi boot và đèn ngủ tắt hoàn toàn khi mới bật nguồn (`BEDROOM_LED_ACTIVE_LOW = true`).
- [ ] **`D8 (GPIO15)` giữ mức `LOW` khi boot:** Chỉ đấu tải xuống `GND` (Active-HIGH), không mắc bất kỳ điện trở kéo lên `3.3V` nào trên chân `D8`.
- [ ] **`A0` & `D5` chỉ cấp `3.3V` cho `LM393` và `KY-037`:** Không cấp `5V` vào `LM393` hay `KY-037` vì ngõ ra `AO` / `DO` vượt `3.3V` sẽ gây sai số hoặc hỏng chân `A0` / `GPIO14` của ESP8266.
- [ ] **Bảo vệ tải cảm ứng (Bơm & Servo):** Gắn đúng chiều **Diode `1N4007`** (vạch bạc nối về cực dương `+` của máy bơm) và đặt tụ **`470µF 16V`** sát đường nguồn `5V` cấp cho bơm và servo.
- [ ] **Kiểm tra cực tính Relay 1 (`D6`) & Relay 2 (`D7`):** Trên Relay 2 đỏ opto, gạt jumper vàng sang **`H`** (kích mức `HIGH`). Với Relay 1 xanh dương (không có jumper lộ ngoài), test nhanh `5V/GND/IN` trước khi lắp tải; nếu module kích mức `LOW`, đổi `#define PUMP_RELAY_ACTIVE_LOW true` trong `esp8266_smarthome.ino`.
