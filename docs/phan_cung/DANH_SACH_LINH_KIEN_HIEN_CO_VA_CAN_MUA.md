# 📋 KIỂM KÊ LINH KIỆN THỰC TẾ TRÊN BÀN & DANH SÁCH CẦN MUA THÊM

> **Đối chiếu trực tiếp từ ảnh chụp thực tế của Nguyễn Tuấn Anh (Ngày 26/10/2026)**

---

## 1. CÁC LINH KIỆN ĐANG CÓ SẴN TRÊN BÀN (8 MÓN — ĐÃ TÍCH HỢP HẾT VÀO CODE & FIRMWARE)

Nhìn từ trái sang phải trên mặt bàn của bạn, hiện tại bạn đang có **8 nhóm linh kiện vật lý** sau đây:

| STT | Linh kiện đang có trên bàn (Từ trái sang phải) | Số lượng | Đã gán vào Thiết bị & Chân nào trên `NodeMCU ESP8266` |
| :---: | :--- | :---: | :--- |
| **1** | **Module Relay 1 kênh 5V** *(1 mạch xanh dương + 1 mạch đỏ kèm 3 dây)* | **02 cái** | - **Relay 1 (`Chân D3 / GPIO0`):** Đóng/ngắt **Máy bơm nước mini tưới cây (`garden_pump`)**.<br>- **Relay 2 (`Chân D6 / GPIO12`):** Đóng/ngắt **Quạt trần (`fan`)**. |
| **2** | **Mạch vi điều khiển `NodeMCU ESP8266 (ESP-12E, CP2102)`** | **01 mạch** | Bộ não trung tâm thu/phát Wi-Fi 2.4GHz, chạy giao thức MQTT (10 Topics) và lưu bản sao 2 Bể vào Flash `LittleFS`. |
| **3** | **Bảng cắm mạch `Breadboard 400 lỗ` (màu trắng)** | **01 cái** | Chia nguồn chung `5V (VIN)` / `3.3V` / `GND` và cắm LED, Điện trở, Transistor, Diode. |
| **4** | **Máy bơm nước mini 3V–5V DC (màu trắng nằm dưới)** *(Linh kiện MỚI thêm)* | **01 cái** | **Thiết bị thứ 7 mới thiết kế thêm:** **Máy bơm tưới cây (`garden_pump` — Chân `D3`)**. Hỗ trợ khẩu lệnh *"Bật máy bơm"*, *"Tưới cây"*, *"Tắt máy bơm"* và tự động bật khi đất khô! |
| **5** | **Dải Điện trở cắm (`Resistors`) + 3 con `Diode 1N4007` (đen)** | **2 dải + 3 con** | - **Điện trở (220Ω – 1kΩ):** Hạn dòng bảo vệ Đèn LED đỏ và cực Base của Transistor.<br>- **Diode `1N4007`:** Đấu ngược song song 2 cực của Máy bơm nước (**Flyback Diode**) để triệt tiêu xung điện cảm ngược khi tắt bơm, chống treo/reset mạch ESP8266! |
| **6** | **Bóng `Đèn LED đỏ 5mm` + `Transistor TO-92` (đen 3 chân)** | **1 LED + 1 Tran** | - **LED đỏ 5mm:** Làm **Đèn phòng khách (`living_room_light` — Chân `D2`)** (kiêm đèn nháy tín hiệu đếm 3-2-1 khi thu âm cấp quyền!).<br>- **Transistor:** Khuếch đại dòng kích cho LED hồng ngoại hoặc còi. |
| **7** | **Động cơ `Servo SG90` (xanh dương, góc quay 0°–180°)** | **01 cái** | Điều khiển đóng/mở cơ khí **Cửa chính (`main_door` — Chân `D1 / GPIO5`)**. |
| **8** | **Cảm biến Độ ẩm Đất `YL-69 / FC-28` + Mạch so sánh `LM393` (dây vàng bên phải)** *(Linh kiện MỚI thêm)* | **01 bộ** | **Cảm biến mới thiết kế thêm (`Chân A0 / ADC0`):** Đọc độ ẩm đất thực tế (`0% – 100%`), gửi gói tin MQTT `smarthome/telemetry/soil_moisture`.<br>- **Tự động hóa khép kín:** Khi độ ẩm đất `< 40%` (đất khô) $\rightarrow$ Tự động bật **Máy bơm (`D3`)**; khi độ ẩm đất `>= 70%` (đủ ẩm) $\rightarrow$ Tự động tắt **Máy bơm**! |

---

## 2. GIẢI ĐÁP VỀ "LOA VÀ MIC" (CÓ CẦN MUA KHÔNG?)

Bạn có **2 lựa chọn** rất rõ ràng cho phần Loa & Mic:

### Phương án 1: Dùng luôn Mic & Loa của Điện thoại (`Mobile App /app`) và Laptop (`Web Dashboard`) — **TỐN 0 ĐỒNG**
- **Cách hoạt động:** Bạn nói trực tiếp vào **Điện thoại** hoặc **Laptop**, luồng âm thanh 16kHz được gửi tới Server xử lý giọng nói (`F0 + MFCC + Gemini 3.8 Live`), AI trả lời bằng giọng nói qua loa Điện thoại/Laptop đồng thời bắn gói tin **MQTT qua Wi-Fi** xuống mạch `NodeMCU ESP8266` để đóng/mở Cửa Servo, bật Máy bơm, bật Đèn!
- **Ưu điểm:** Không phải mua thêm mạch âm thanh, thu âm cực nét, không lo ESP8266 bị thiếu chân hay thiếu RAM (vì ESP8266 chỉ có 80KB RAM và 1 chân `A0` đã dùng cho cảm biến độ ẩm đất).

### Phương án 2: Nếu bạn muốn có **Loa & Mic rời đặt trên bàn mô hình** (để nói thẳng vào mô hình nhà)
Nếu thầy hướng dẫn muốn nhìn thấy 1 cụm Mic + Loa rời trên mô hình phần cứng, bạn mua 1 trong 2 combo sau:
1. **Cách dễ nhất & thu âm nhạy nhất (~90.000đ):** Mua **1 chiếc Mic kèm Loa hội nghị USB mini (hoặc Mic cài áo không dây cắm USB vào Laptop/Server)** đặt ngay trong ngôi nhà mô hình $\rightarrow$ Cắm phát ăn ngay 100%, không tốn bất kỳ chân GPIO nào của ESP8266!
2. **Cách nhúng I2S (~80.000đ):**
   - `01x Module Mic số INMP441 (I2S MEMS)` (~35.000đ)
   - `01x Mạch khuếch đại âm thanh MAX98357A I2S 3W` + `01x Loa 4Ω 3W` (~45.000đ)

---

## 3. DANH SÁCH LINH KIỆN CẦN MUA THÊM ĐỂ ĐỦ 100% BỘ ĐỒ ÁN (TỔNG CHỈ ~85.000Đ)

Dưới đây là bảng mua hàng chính xác những món đang thiếu trên bàn của bạn (có thể mua tại cửa hàng linh kiện điện tử Bách Khoa ở phố Lê Thanh Nghị / Tạ Quang Bửu hoặc Shopee):

| STT | Tên linh kiện cần mua thêm | Số lượng | Giá tham khảo | Dùng để làm gì trong Đồ án? |
| :---: | :--- | :---: | :---: | :--- |
| **1** | **Bộ dây cắm `Jumper 20cm` (3 loại: Đực-Đực, Đực-Cái, Cái-Cái)** | **1 bó (40 sợi/loại)** | ~25.000đ | **Bắt buộc số 1:** Trên bàn bạn mới có 3 sợi dây ở Relay đỏ, cần dây để nối ESP8266 ra Breadboard, Servo, Cảm biến đất, Máy bơm. |
| **2** | **Cáp `Micro-USB` có truyền dữ liệu (Data Cable) + Củ nguồn 5V-2A** | **01 sợi** | ~15.000đ | Để nạp code lần đầu từ máy tính vào `NodeMCU ESP8266` và cấp nguồn độc lập 5V (lưu ý: tránh dùng cáp sạc chỉ có 2 lõi nguồn không nhận cổng COM). |
| **3** | **Còi báo động `Buzzer 5V Active` (Loại có sẵn mạch tạo dao động, cấp 5V là kêu)** | **01 cái** | ~5.000đ | Cho thiết bị **Còi báo động (`alarm_siren` — Chân `D8`)** khi có người lạ đột nhập hoặc sai giọng nói. |
| **4** | **Mắt thu hồng ngoại `VS1838B (38kHz)` + Bóng LED phát hồng ngoại `IR LED 5mm 940nm`** | **1 cặp (1 thu + 2 phát)** | ~8.000đ | Để thực hiện tính năng **Học lệnh & Chiếm quyền điều khiển Remote Điều hòa / Quạt / TV** (chân `D5` thu sóng, chân `D2` phát sóng). |
| **5** | **Cảm biến Nhiệt độ & Độ ẩm không khí `DHT11` (loại 3 chân có sẵn mạch PCB)** | **01 cái** | ~18.000đ | Đo nhiệt độ (°C) và độ ẩm không khí (%) trong phòng tại **Chân `D6`** (khác với cảm biến độ ẩm đất YL-69 đang có trên bàn). |
| **6** | **Bóng `Đèn LED 5mm` (Màu Vàng / Trắng / Xanh lá)** | **5 bóng** | ~3.000đ | Trên bàn mới có **1 bóng LED đỏ** (Đèn phòng khách `D2`), mua thêm để làm **Đèn phòng ngủ (`bedroom_light` — Chân `D7`)** và đèn báo dự phòng. |
| **7** | **Ống nhựa silicon mềm trong suốt (đường kính trong 6mm - 8mm, dài 0.5m)** | **0.5 mét** | ~8.000đ | Cắm vào đầu ra của **Máy bơm nước mini trắng** trên bàn để bơm nước từ cốc sang chậu cây thật khi thuyết trình trước hội đồng! |
| **8** | *(Tùy chọn)* **Mic + Loa USB mini** *(hoặc `INMP441` + `MAX98357A`)* | **01 bộ** | ~80.000đ | Chỉ cần mua nếu bạn muốn đặt Mic & Loa rời ngay trong mô hình nhà thay vì nói qua Mic Điện thoại/Laptop. |

---

## 4. TRỌN BỘ LINH KIỆN ĐỂ THIẾT KẾ & HÀN MẠCH IN PCB HOÀN CHỈNH (FULL PCB BOM)

Khi chuyển từ cắm thử trên Breadboard sang **hàn thành 1 bo mạch in PCB hoàn chỉnh** (vẽ trên **Altium Designer / EasyEDA / KiCad** để tự ủi mạch hoặc đặt in PCB 2 lớp phủ xanh), bạn cần mua **trọn bộ linh kiện hàn mạch (BOM — Bill of Materials)** dưới đây.

> **Nguyên tắc vàng khi thiết kế PCB cho Đồ án:**
> - **Không hàn chết `NodeMCU ESP8266` hay cảm biến xuống PCB:** Dùng **Rào cắm cái (`Female Header`)** hàn lên PCB để có thể tháo/cắm `ESP8266`, `DHT11`, `LM393` bất cứ lúc nào.
> - **Dùng Domino vặn vít (`KF301`) cho tải công suất:** Máy bơm nước, Quạt và Nguồn 5V được bắt vít chặt vào Domino trên mép bo PCB, vừa thẩm mỹ như mạch công nghiệp vừa không bao giờ bị lỏng dây khi mang đi bảo vệ đồ án.

### 4.1. Nhóm Linh Kiện Hàn Trực Tiếp Lên Bo PCB (Đầu nối, Rào cắm, Lọc nguồn & Công suất)

| STT | Tên linh kiện PCB (Chuẩn Footprint khi vẽ mạch) | Thông số / Kiểu chân (Package) | Số lượng cần mua | Giá tham khảo | Công dụng trên bo mạch in PCB |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **1** | **Rào cắm cái `Female Header 1x15P`** *(hoặc 1x40P về cắt)* | Pitch `2.54mm` (Xuyên lỗ `THT`) | **02 thanh** | ~6.000đ | Hàn thành 2 hàng song song trên PCB làm **đế cắm rút cho `NodeMCU ESP8266`** (30 chân). |
| **2** | **Rào cắm đực `Male Pin Header 1x40P`** | Pitch `2.54mm` (`THT`) | **02 thanh** | ~4.000đ | Bẻ thành cụm **3 chân (`1x3P`)** để cắm giắc cái của **`Servo SG90`**, và cụm **4 chân (`1x4P`)** nối ra mạch độ ẩm đất `YL-69`. |
| **3** | **Rào cắm cái `Female Header 1x4P` & `1x3P`** | Pitch `2.54mm` (`THT`) | **04 cái** | ~4.000đ | Làm đế cắm trực tiếp trên PCB cho **`DHT11` (3P/4P)**, mắt thu **`VS1838B` (3P)** và màn hình I2C dự phòng (4P). |
| **4** | **Domino vặn vít 2 cực `KF301-2P` (Xanh dương)** | Pitch `5.08mm` (`THT`) | **04 cái** | ~8.000đ | Hàn ở mép PCB để vặn vít dây **Máy bơm nước 5V**, **Quạt trần**, và **Nguồn 5V vào** chắc chắn 100%. |
| **5** | **Domino vặn vít 3 cực `KF301-3P` (Xanh dương)** | Pitch `5.08mm` (`THT`) | **02 cái** | ~6.000đ | Đưa 3 tiếp điểm `NO - COM - NC` của 2 kênh Relay ra mép bo PCB. |
| **6** | **Giắc nguồn DC cái hàn mạch `DC-005`** + **Củ nguồn Adapter `5V - 2A`** | Chân tròn `5.5 x 2.1mm` (`THT`) | **01 bộ** | ~35.000đ | Cấp nguồn `5V - 2A` ổn định cho toàn bộ bo PCB (nuôi cả ESP8266, Servo SG90 và Máy bơm chạy cùng lúc không sụt áp). |
| **7** | **Công tắc gạt nguồn `SS12D00` (hoặc công tắc bập bênh mini)** | 3 chân `THT` | **02 cái** | ~3.000đ | Làm công tắc **Bật/Tắt nguồn tổng (`ON/OFF`)** ngay trên góc bo mạch PCB. |
| **8** | **Tụ hóa lọc nguồn chống sụt áp `470µF/16V` (hoặc `1000µF/16V`)** | Đường kính `8mm`, pitch `3.5mm` | **03 con** | ~4.000đ | **Cực kỳ quan trọng trên PCB:** Hàn sát đường 5V của `Servo SG90` và `Máy bơm` để chống sụt áp làm khởi động lại ESP8266 khi bơm/cửa hoạt động! |
| **9** | **Tụ gốm lọc nhiễu cao tần `100nF (mã 104)`** | Pitch `2.54mm` / `5.08mm` (`THT`) | **10 con** | ~3.000đ | Hàn sát chân `VCC - GND` của `ESP8266`, `DHT11`, `VS1838B` để triệt nhiễu cao tần. |
| **10** | **Rơ-le 5V 5 chân rời `SRD-05VDC-SL-C (10A)`** + **Opto `PC817`** | Relay `5Pin THT` + `DIP-4` | **02 bộ** | ~16.000đ | Hàn trực tiếp 2 kênh Relay (Bơm `D3` + Quạt `D6`) lên mặt bo PCB thay vì phải để 2 module Relay rời lơ lửng bên ngoài. |
| **11** | **Transistor NPN `S8050` hoặc `2N2222A`** | Kiểu vỏ `TO-92` (3 chân cắm) | **05 con** | ~3.000đ | *(Đã có 1 con trên bàn)* Khuếch đại dòng cho **LED phát hồng ngoại `IR 940nm`**, kích cuộn hút **2 Relay** và **Còi `Buzzer 5V`** trên PCB. |
| **12** | **Diode chỉnh lưu chống dòng ngược `1N4007`** | Kiểu vỏ `DO-41` (chân cắm) | **05 con** | ~2.000đ | *(Đã có 3 con trên bàn)* Hàn song song ngược cực với 2 cuộn hút Relay và Domino Máy bơm (**Flyback Diode**). |
| **13** | **Bộ Điện trở cắm `1/4W 1%` (`100Ω`, `220Ω`, `1kΩ`, `4.7kΩ`, `10kΩ`)** | Kiểu `Axial 0207` (`THT`) | **10 con/trị số** | ~10.000đ | - `100Ω`: Hạn dòng LED Hồng ngoại `IR TX`.<br>- `220Ω`: Hạn dòng các bóng LED 5mm.<br>- `1kΩ`: Kích cực Base Transistor.<br>- `4.7kΩ / 10kΩ`: Pull-up chân Data `DHT11` & nút nhấn. |
| **14** | **Nút nhấn 4 chân `Tactile Switch 6x6x5mm`** | `6x6mm THT` | **03 cái** | ~3.000đ | Làm nút `RESET` mạch và nút nhấn khẩn cấp trên bo PCB. |
| **15** | **Phíp đồng `FR-4` (10x15cm) + Bột sắt `FeCl3`** *(hoặc đặt in PCB JLCPCB)* + **4 Trụ đồng `M3x10mm`** | Bo mạch `100 x 80 mm` | **01 bộ** | ~25.000đ – 80.000đ | Làm tấm nền PCB hoàn chỉnh và bắt 4 chân đế đồng cố định lên sa bàn ngôi nhà thông minh. |

---

### 4.2. Bảng Tổng Hợp Chi Tiết Sơ Đồ Chân (Pinout Map) Để Vẽ Mạch Nguyên Lý (Schematic & PCB Layout)

Khi bạn vẽ sơ đồ nguyên lý (Schematic) trên **EasyEDA / Altium / KiCad**, hãy nối chính xác từng chân của đế cắm **`NodeMCU ESP8266`** trên PCB theo bảng chuẩn đã đồng bộ 100% với Firmware [`esp8266_smarthome.ino`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/firmware_esp8266/esp8266_smarthome/esp8266_smarthome.ino) dưới đây:

| Chân trên `NodeMCU ESP8266` | GPIO | Kết nối tới linh kiện nào trên bản vẽ PCB (Schematic Net) | Linh kiện đệm trên đường mạch PCB |
| :---: | :---: | :--- | :--- |
| **`A0`** | `ADC0` | Chân **`AO` (Analog Out)** của Header 4P cắm mạch độ ẩm đất **`YL-69 / LM393`** | Nối trực tiếp (kèm tụ lọc `100nF` xuống `GND`). |
| **`D1`** | `GPIO5` | Chân **`PWM` (Dây Cam/Vàng)** của Header 3P cắm **`Servo SG90` (Cửa chính)** | Đường nguồn `5V` của Header Servo có tụ hóa **`470µF/16V`** sát chân. |
| **`D2`** | `GPIO4` | **Đèn Phòng Khách (`LED Đỏ 5mm`)** + **Mạch phát Hồng ngoại (`IR LED 940nm`)** | Qua điện trở `220Ω` tới LED Đỏ; qua trở `1kΩ` kích Base Transistor `S8050` kéo `IR LED 940nm` (trở hạn dòng `100Ω` lên `5V`). |
| **`D3`** | `GPIO0` | Kênh **Relay 1 — Máy bơm nước tưới cây (`garden_pump`)** | Qua trở `1kΩ` *(lưu ý không kéo xuống GND lúc khởi động để ESP8266 boot bình thường)* kích Transistor `S8050` + Diode `1N4007` + Relay 5V $\rightarrow$ Domino `KF301-2P` (Máy bơm). |
| **`D5`** | `GPIO14` | Chân **`OUT`** của mắt thu hồng ngoại **`VS1838B (38kHz)`** | Điện trở kéo lên `10kΩ` lên `3.3V` + Tụ lọc nguồn `100nF` sát chân `VCC (3.3V)` của mắt thu. |
| **`D6`** | `GPIO12` | Chân **`DATA`** của cảm biến **`DHT11`** *(hoặc Kênh Relay 2 — Quạt trần)* | Điện trở kéo lên (`Pull-up`) `4.7kΩ` nối lên `3.3V`. |
| **`D7`** | `GPIO13` | **Đèn Phòng Ngủ (`LED Vàng/Trắng 5mm`)** | Nối tiếp qua điện trở hạn dòng `220Ω` xuống `GND`. |
| **`D8`** | `GPIO15` | **Còi Báo Động (`Buzzer 5V Active`)** | Qua điện trở `1kΩ` vào cực Base Transistor `S8050` kích Còi `Buzzer 5V` *(tuyệt đối không dùng điện trở Pull-up trên chân D8 vì GPIO15 cần mức LOW khi boot)*. |
| **`VIN (5V)`** | `5V Bus` | Đường nguồn công suất **`+5V_PWR`** từ Giắc `DC-005 (5V-2A)` qua Công tắc nguồn | Nuôi `Servo SG90`, cuộn hút `2 Relay 5V`, `Máy bơm nước 5V`, `Còi Buzzer 5V` và cấp ngược vào chân `VIN` của `NodeMCU`. |
| **`3V3`** | `3.3V Bus` | Đường nguồn logic **`+3V3`** | Nuôi `DHT11`, mắt thu `VS1838B` và mạch so sánh `LM393 (YL-69)`. |
| **`GND`** | `GND Plane` | **Phủ đồng toàn bộ mặt dưới/mặt trên (`GND Copper Pour`)** | Nối chung Mass (`GND`) của toàn bộ Nguồn 5V, ESP8266, Cảm biến và Chấp hành. |

