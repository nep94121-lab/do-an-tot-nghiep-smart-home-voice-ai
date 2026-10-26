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
