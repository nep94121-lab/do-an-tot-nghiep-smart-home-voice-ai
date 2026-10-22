# 📋 HỒ SƠ & LỘ TRÌNH ĐỒ ÁN TỐT NGHIỆP (CỬ NHÂN ĐIỆN TỬ – VIỄN THÔNG)

**Đề tài:** Hệ thống Nhà thông minh điều khiển bằng Giọng nói AI thời gian thực, Phân quyền Sinh trắc học 3 tầng, Tự động hóa 2 Bể (Hẹn giờ & Luật liên động) kết hợp Bản sao số 3D (Digital Twin) và Học lệnh Hồng ngoại trên Vi điều khiển ESP8266.
**Tác giả / Admin Cấp 1:** Nguyễn Tuấn Anh

---

## PHẦN 1: NHỮNG GÌ ĐÃ LÀM XONG 100% (ĐÃ CÓ & CHẠY ỔN ĐỊNH)

### 1.1. Lõi Điều Khiển & Phân Quyền 3 Tầng (`simulator/rule_engine.py`)
- [x] **Kiến trúc Phân quyền 3 Tầng (RBAC):**
  - **Tầng 1 (Admin tối cao — Nguyễn Tuấn Anh):** Toàn quyền điều khiển, luật IF-ELSE áp dụng toàn nhà, không ai được hủy quyền người do Tầng 1 cấp, không ai được đè/xóa/vướng khung giờ hẹn giờ của Tầng 1.
  - **Tầng 2 (Thành viên gia đình):** Có **Bể lệnh riêng** và **Lịch hẹn giờ riêng** cho từng người; được cấp/hủy quyền cho Tầng 3 (trừ người do Tầng 1 cấp); không được hủy cùng cấp; khi gọi Reset chỉ xóa bể riêng của chính mình.
  - **Tầng 3 (Khách):** Mặc định chỉ được gọi lệnh đóng/mở cố định cơ bản, không được đổi lệnh, không được đặt luật IF-ELSE, không được hẹn giờ, không được cấp/hủy quyền.
- [x] **Đặc quyền Tối cao của Admin Cấp 1 sửa mọi luật bằng Giọng nói (`admin_update_system_policy`):**
  - Cấp 1 chỉ cần nói tự nhiên để mở/khóa quyền hẹn giờ hoặc custom luật cho Cấp 3, chỉnh quyền từng thiết bị, bật/tắt bước hỏi xác nhận, đổi đèn nháy tín hiệu thu âm, hoặc đặt quy định khóa thiết bị theo khung giờ (VD: cấm mở cửa chính sau 11 giờ đêm).
- [x] **Bể 1 — Bể Hẹn Giờ (`active_timers`):**
  - Mặc định hẹn giờ **1 lần rồi tự dừng** (`repeat='once'`). Tự hiểu khi nói *"hàng ngày"*, *"hàng tuần"*, *"hàng giờ"*, *"hàng tháng"*.
  - Hỗ trợ cả 4 quy tắc: Đếm ngược giây/phút/giờ, hẹn giờ có AM/PM, hẹn giờ không nói AM/PM (tự đặt cả AM & PM), và hẹn giờ kèm ngày/tháng.
- [x] **Bể 2 — Bể Luật Động & Ngôn Ngữ (`user_pools`):**
  - Đổi từ (`word_mappings`), Đổi khẩu lệnh (`aliases` - VD: *"vừng ơi mở ra"*), Luật liên động `IF - THEN - ELSE` 1 chiều và 2 chiều.
  - Thuật toán đồ thị **DFS Cycle Detection** chống vòng lặp vô hạn giữa các thiết bị.
  - Cơ chế hỏi xác nhận 2 bước trước khi lưu luật.
- [x] **4 Loại Reset có xác nhận 2 bước (`voice`, `timers`, `rules`, `all`):**
  - Cô lập theo tầng (Cấp 1 reset toàn hệ thống; Cấp 2 chỉ reset bể riêng của mình).

### 1.2. Sinh Trắc Học Giọng Nói, AI Thời Gian Thực & Kho Tri Thức RAG
- [x] **Quy trình Thu âm Cấp quyền Giọng nói (`start_voice_enrollment` & `finalize_voice_enrollment`):**
  - Đếm ngược `3, 2, 1` -> **Nháy đèn 1 phát** làm tín hiệu bắt đầu -> Thu âm giọng nói trong 5 giây -> Báo *"Đã thu âm đủ"* -> Phân tích tần số cơ bản $F_0$ (Hz), RMS, ZCR (`simulator/voice_biometrics.py`) -> Hỏi tên người mới và lưu cấp quyền.
  - Cơ chế **2-Strike** với giọng lạ chưa cấp quyền (Lần 1 nhắc không có quyền, Lần 2 nhắc vẫn không đủ quyền, từ Lần 3 im lặng tuyệt đối).
- [x] **Kho Tri thức Vector RAG (`simulator/knowledge_rag.py`):**
  - Sử dụng `gemini-embedding-001` (3072 chiều) trả lời cực kỳ ngắn gọn, hỏi gì đáp nấy, không lễ nghi rườm rà.
  - Phân quyền trả lời câu hỏi theo từng tầng (`tier_restricted` hoặc `open_all`), và cho phép Admin Cấp 1 dạy thêm kiến thức RAG trực tiếp bằng giọng nói (`admin_upsert_knowledge_rag`).
- [x] **Mô phỏng Ngôi nhà 3D Digital Twin (`simulator/static/house3d.js`, `app.js`):**
  - Hiển thị trực quan 6 thiết bị 3D (Cửa chính, Đèn phòng khách, Đèn phòng ngủ, Quạt trần, Điều hòa, Còi báo động) đồng bộ thời gian thực qua WebSocket.

---

## PHẦN 2: PHẦN CỨNG — NHỮNG GÌ ĐÃ CÓ & LINH KIỆN CẦN BỔ SUNG

### 2.1. Linh kiện ĐÃ CÓ SẴN
- [x] **1 Mạch vi điều khiển NodeMCU ESP8266 (ESP-12E, chip nạp CP2102)** có Wi-Fi 2.4GHz (`IEEE 802.11 b/g/n`) và 4MB Flash.
- [x] **1 Breadboard (Bảng cắm mạch thử nghiệm)** + **Dây cắm Jump**.

### 2.2. Linh kiện CẦN MUA BỔ SUNG (Nhẹ, rẻ, dễ cắm nhưng nâng tầm Đồ án Điện tử – Viễn thông)
1. [ ] **Cảm biến Nhiệt độ & Độ ẩm `DHT11` (hoặc `DHT22`):**
   - Dùng để đo nhiệt độ (°C) và độ ẩm (%) thực tế trong phòng, gửi về Server/App và kích hoạt luật IF-ELSE theo ngưỡng nhiệt độ/độ ẩm.
2. [ ] **Bộ Thu – Phát Sóng Hồng Ngoại (Chiếm quyền Remote Điều hòa / Quạt / TV & Thêm thiết bị mới không cần dây):**
   - **01 Mắt thu hồng ngoại `VS1838B` (hoặc module thu IR `KY-022` - tần số 38kHz):** Để thu và sao chép mã sóng từ bất kỳ chiếc Remote thật nào bấm chĩa vào mạch.
   - **01 Đèn LED phát hồng ngoại `IR LED 940nm` + 01 Transistor `2N2222` / `S8050` (hoặc module phát IR `KY-005`):** Để phát lại sóng hồng ngoại 38kHz bật/tắt Điều hòa, Quạt, TV thật mà không cần đấu dây.
3. [ ] **Cơ cấu chấp hành minh họa trên mô hình:**
   - **01 Động cơ `Servo SG90`:** Đóng/mở Cửa chính.
   - **03–04 Đèn LED (kèm trở 220Ω) + 01 Còi chip `Buzzer 5V`:** Làm Đèn phòng khách, Đèn phòng ngủ, báo trạng thái và Còi báo động.
4. [ ] **Nguồn cấp độc lập khi rút khỏi Laptop:**
   - **Củ sạc điện thoại 5V / Sạc dự phòng (Powerbank)** cắm vào cổng Micro-USB của ESP8266 (hoặc nguồn 5V cắm chân `Vin` & `GND`).

---

## PHẦN 3: PHẦN MỀM & HỆ THỐNG — CÁC HẠNG MỤC CẦN LÀM TIẾP (KHÔNG DÙNG FIREBASE/SUPABASE)

### 3.1. Hạng mục 1: Nâng cấp Backend Server Tự Xây Dựng (`simulator/server.py`)
- [ ] **Giao thức kết nối Phần cứng ESP8266 qua Wi-Fi (WebSocket / HTTP REST 2 chiều):**
  - Nhận gói tin Telemetry (Nhiệt độ, Độ ẩm, mã sóng hồng ngoại IR vừa thu được, trạng thái chân GPIO) từ mạch ESP8266 gửi lên.
  - Đẩy lệnh đóng/mở GPIO, lệnh nháy đèn thu âm (`3, 2, 1`), và lệnh phát sóng hồng ngoại (IR Blast) từ Server xuống thẳng IP của ESP8266.
- [ ] **Đồng bộ 2 Bể xuống bộ nhớ Flash của ESP8266 (Edge Sync):**
  - Để khi tắt hẳn Server/Laptop, con ESP8266 vẫn tự chạy được lịch hẹn giờ (Bể 1) và luật IF-ELSE (Bể 2).
- [ ] **Cơ sở dữ liệu Thiết bị Mới & Mã Hồng Ngoại (`ir_devices_db.json` / SQLite nội bộ):**
  - Tự quản lý 100% trên Server riêng (không dùng Firebase/Supabase): Lưu danh sách thiết bị mới do người dùng thêm bằng giọng nói và chuỗi mã xung hồng ngoại (Raw Timings / Hex) đã học từ Remote.
- [ ] **Mở rộng Luật IF-ELSE theo Cảm biến (`rule_engine.py`):**
  - Hỗ trợ đặt luật bằng giọng nói theo nhiệt độ/độ ẩm (VD: *"Nếu nhiệt độ trên 30 độ thì mở điều hòa"*).

### 3.2. Hạng mục 2: Nâng cấp Web Dashboard Quản Trị Riêng (`/dashboard`)
- [ ] Hiển thị **Trạng thái kết nối Mạch ESP8266** (Online/Offline, Địa chỉ IP, Cường độ sóng Wi-Fi RSSI dBm).
- [ ] Hiển thị **Đồng hồ & Đồ thị Nhiệt độ (°C) – Độ ẩm (%)** thời gian thực từ cảm biến `DHT11`.
- [ ] Bảng **Quản lý Thiết bị Hồng ngoại & Thêm thiết bị mới (IR Remote Cloning):** Hiển thị các lệnh Remote đã chiếm quyền và nút kiểm tra phát sóng thử.

### 3.3. Hạng mục 3: Xây dựng App Điện Thoại Riêng (`/app` - Mobile Web App / PWA)
- [ ] Giao diện thiết kế riêng chuẩn App di động (cài thẳng lên màn hình chính điện thoại Android/iPhone, dùng khi đã rút/tắt Laptop).
- [ ] Nút **Mic Giọng Nói AI** cỡ lớn ở trung tâm + Hiển thị sóng âm & tần số giọng nói $F_0$ (Hz).
- [ ] Thẻ hiển thị nhanh **Nhiệt độ & Độ ẩm phòng** + Bảng nút bấm nhanh 6 thiết bị & các thiết bị Hồng ngoại mới thêm.
- [ ] Chức năng **"Thêm thiết bị / Học lệnh Remote bằng giọng nói"** ngay trên điện thoại.

### 3.4. Hạng mục 4: Viết Firmware nạp cho Mạch NodeMCU ESP8266 (`firmware/esp8266_smarthome/esp8266_smarthome.ino`)
- [ ] Kết nối Wi-Fi tự động + Đồng bộ giờ thực tế Việt Nam qua giao thức **NTP (`UTC+7`)** + Hỗ trợ nạp code không dây **OTA**.
- [ ] Đọc cảm biến `DHT11/DHT22` định kỳ gửi về Server.
- [ ] Tích hợp thư viện `IRremoteESP8266`: Chế độ **IR Learning** (thu sóng 38kHz từ Remote thật) và **IR Blaster** (phát sóng điều khiển Điều hòa/Quạt/TV).
- [ ] Điều khiển 6 chân phần cứng (`D1, D2, D5, D6, D7, D8`) + Lưu trữ lịch hẹn & luật IF vào bộ nhớ Flash (`LittleFS`) để chạy độc lập khi mất kết nối Server.
