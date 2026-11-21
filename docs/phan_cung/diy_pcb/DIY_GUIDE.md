# Hướng Dẫn Tự Làm Mạch PCB Một Lớp Tại Nhà (Toner Transfer + Khoan Tay)

**Dự án**: SmartHome Hub DIY v3.0 — Bo 1 lớp đồng mặt dưới (`B.Cu`), kích thước **100.0 × 80.0 × 1.6 mm**, 4 lỗ ốc M3 (`90 × 70 mm`), chỉ 4 cỡ mũi khoan và 7 dây nhảy mặt trên.

---

## 1. Chuẩn bị vật tư & dụng cụ

- **Phíp đồng**: 1 tấm phíp đồng **1 mặt FR-4** dày `1.6 mm`, cắt kích thước `100 × 80 mm` (hoặc để dư 5 mm mỗi cạnh rồi cắt sau khi ăn mòn).
- **In & ủi mạch**: Máy in **laser mực đen** (tuyệt đối KHÔNG dùng máy in phun), giấy in ảnh bóng mỏng / giấy decal vàng / giấy tạp chí bóng (`120–150 gsm`), bàn ủi gia đình, giấy nhám mịn P800–P1200, cồn isopropyl hoặc acetone.
- **Ăn mòn đồng** (chọn 1 trong 2 cách ở Mục 4): Bột sắt(III) clorua **FeCl₃**, HOẶC hỗn hợp **Oxy già (H₂O₂ 3–6%) + Axit clohydric (HCl 10–30%)**, khay nhựa (không dùng kim loại), găng tay cao su, kính bảo hộ.
- **Khoan & hàn**: Khoan tay/khoan bàn mini, đúng **4 mũi khoan**: `0.9 mm`, `1.1 mm`, `1.3 mm`, `3.2 mm`; mỏ hàn, thiếc hàn có lõi nhựa thông, dây nhảy lõi đặc **22 AWG** (đỏ + cam), đồng hồ vạn năng.

---

## 2. In mạch đúng tỉ lệ 1:1 & Kiểm tra thanh chuẩn 50 mm

1. Mở file **`toner_B.Cu_MIRRORED_1to1.pdf`** bằng Adobe Acrobat Reader hoặc trình đọc PDF chuẩn.
2. Trong hộp thoại Print:
   - Chọn **Actual Size / Scale 100%** (TẮT hoàn toàn *Fit to page* / *Shrink to printable area*).
   - Chọn giấy **A4**, chế độ mực **đậm nhất / Toner Density Max**, tắt *Toner Save / Eco Mode*.
3. **Kiểm tra chiều lật gương (Mirror Check)**:
   - Trên bản **`toner_B.Cu_MIRRORED_1to1.pdf`**, dòng chữ tiêu đề và dòng chữ dưới thanh đo phải **đọc ngược (như soi gương)** — khi úp mặt mực xuống tấm đồng để ủi, đường đồng trên phíp sẽ quay đúng chiều nhìn từ mặt dưới!
   - Đối chiếu với **`toner_B.Cu_check_NOT_mirrored_1to1.pdf`** (bản này chữ đọc xuôi bình thường, chỉ dùng để kiểm tra, KHÔNG dùng để ủi).
4. **Kiểm tra thanh chuẩn 50 mm (BẮT BUỘC trước khi ủi)**:
   - Dùng thước kẹp hoặc thước kẻ chính xác đo thanh kẻ ngay dưới bo mạch có dòng chữ **`IN DUNG TI LE 1:1 - THANH NAY PHAI DO DUOC 50 mm`**.
   - Thanh đo phải đạt **đúng `50.0 mm` (sai số ≤ ±0.2 mm)**. Nếu lệch, kiểm tra lại cài đặt 100% Scale của máy in rồi in lại — nếu không, 2 thanh chân NodeMCU (30 chân, dài 35.56 mm) sẽ không cắm vừa!
5. In thêm 1 bản **`placement_top_silk_1to1.pdf`** (tỉ lệ 1:1, không lật) và **`drill_map.pdf`** lên giấy A4 thường để làm hướng dẫn khoan và cắm linh kiện.

---

## 3. Làm sạch phíp đồng & Ủi mạch (Toner Transfer)

1. Đánh sạch lớp oxit trên mặt đồng bằng giấy nhám mịn P800–P1200 (chà nhẹ đều tay theo vòng tròn tới khi đồng sáng hồng), rửa nước xà phòng, lau khô bằng cồn/acetone và **không chạm ngón tay** vào mặt đồng.
2. Cắt bản in **`toner_B.Cu_MIRRORED_1to1.pdf`** chừa viền 10 mm, **úp mặt có mực laser xuống mặt đồng**, cố định 2 cạnh bằng băng keo giấy chịu nhiệt.
3. Chỉnh bàn ủi ở mức nhiệt cao nhất (chế độ *Cotton/Linen*, khoảng `180–200 °C`, **TẮT chế độ phun hơi nước**).
4. Ép mạnh và di chuyển đều tay khắp mặt giấy trong **3–5 phút**, nhấn kỹ bằng đầu mũi bàn ủi vào 4 góc và các cụm chân header 2.54 mm.
5. Chờ tấm đồng nguội tự nhiên (2 phút), sau đó **ngâm vào nước ấm có pha vài giọt nước rửa chén trong 10–15 phút** cho giấy mềm hoàn toàn.
6. Bóc nhẹ giấy từ từ và dùng ngón tay chà nhẹ dưới vòi nước để trôi hết lớp bột giấy, để lại toàn bộ mực đen bám chắc trên đồng.
7. Soi kỹ mạch: nếu có vệt mực bị đứt hoặc rỗ nhỏ, dùng **bút lông dầu không trôi (Sharpie / bút vẽ mạch PCB)** tô dặm lại rồi để khô 5 phút.

---

## 4. Ăn mòn đồng (Etching) & An toàn hóa chất

> **CẢNH BÁO AN TOÀN**: Thực hiện nơi **thông thoáng / ngoài trời**. Bắt buộc đeo **găng tay cao su, kính bảo hộ, khẩu trang**. KHÔNG đổ trực tiếp dung dịch đồng đã ăn mòn xuống cống sinh hoạt — thu vào chai nhựa có nắp, trung hòa bằng baking soda (NaHCO₃) và xử lý theo quy định rác thải hóa chất.

### Cách A — Sắt(III) Clorua FeCl₃ (Khuyên dùng cho người mới — an toàn nhất)
1. Pha khoảng `100 g` bột FeCl₃ vào `250 ml` nước ấm (`40–50 °C`) trong khay nhựa (luôn đổ hóa chất vào nước).
2. Thả tấm mạch mặt đồng hướng lên trên, lắc nhẹ khay liên tục. Đồng sẽ tan hết sau **15–25 phút**.
3. Khi thấy toàn bộ vùng đồng thừa biến mất sạch (chỉ còn lại nền phíp trắng/vàng và đường mực đen), gắp mạch ra bằng kẹp nhựa, rửa sạch kỹ dưới vòi nước.

### Cách B — Oxy già H₂O₂ + Axit HCl (Nhanh, dung dịch trong suốt dễ quan sát)
1. **Quy tắc pha bắt buộc**: Luôn đổ **Oxy già (H₂O₂ 3–6%) trước**, sau đó mới rót từ từ **HCl (10–20%)** theo tỉ lệ thể tích khoảng **2 phần H₂O₂ : 1 phần HCl** (tuyệt đối không đổ nước/H₂O₂ vào axit đặc; tránh hít hơi clo).
2. Thả mạch vào khay nhựa, lắc nhẹ. Mạch ăn mòn rất nhanh trong **5–10 phút** (dung dịch chuyển dần sang màu xanh lục đồng clorua CuCl₂).
3. Lấy mạch ra ngay khi đồng thừa vừa sạch hoàn toàn (tránh ngâm quá lâu gây ăn lẹm dưới chân mực), rửa sạch nhiều lần với nước.

### Tẩy mực & Hoàn thiện mặt đồng
1. Dùng bông thấm **acetone hoặc xăng thơm** lau sạch lớp mực laser đen, lộ ra toàn bộ đường mạch đồng sáng bóng (`1.0 mm` tín hiệu, `2.0 mm` nguồn/GND).
2. Soi dưới ánh sáng mạnh hoặc dùng đồng hồ vạn năng kiểm tra xem còn mảnh đồng thừa nào nối tắt giữa 2 chân 2.54 mm không; nếu có, dùng mũi dao rọc giấy cạo nhẹ tách ra.
3. Cắt gọn bo theo đường viền `Edge.Cuts` (`100.0 × 80.0 mm`, có thể bo nhẹ 4 góc bán kính 3 mm bằng giũa).

---

## 5. Khoan lỗ từng bước (Đúng 4 cỡ mũi khoan)

Trong file toner đã có sẵn **dấu tâm lỗ khoan nhỏ** giữa mỗi pad đồng để tự định tâm mũi khoan. Ngoài ra, có thể dán tờ **`drill_map.pdf`** (tỉ lệ 1:1) lên mặt trên phíp (căn khít 4 góc `Edge.Cuts` và 4 tâm lỗ M3) để kiểm tra chéo cỡ mũi từng cụm lỗ theo bảng **`drill_table.md`**.

**Thứ tự khoan từ nhỏ đến lớn (tổng 122 lỗ)**:

| Bước | Cỡ mũi khoan | Số lỗ | Nhóm linh kiện cần khoan |
| :---: | :---: | :---: | :--- |
| **1** | **0.9 mm** | **48 lỗ** | Tất cả điện trở (`R1..R9`), tụ điện (`C1..C7`), LED nguồn (`D3`), và 7 dây nhảy (`JP1..JP7`) |
| **2** | **1.1 mm** | **66 lỗ** | 2 đế cái NodeMCU (`U1, U2`), tất cả header cắm module (`J3..J15`), và 2 diode 1N4007 (`D1, D2`) |
| **3** | **1.3 mm** | **4 lỗ** | 2 domino bắt vít 5.08 mm (`J1` nguồn 5V vào, `J2` đầu ra bơm) |
| **4** | **3.2 mm** | **4 lỗ** | 4 lỗ bắt ốc M3 ở 4 góc bo (`H1..H4`, tâm cách mép bo đúng `5.0 mm`) |

*Mẹo khoan tay*: Đặt 1 miếng gỗ phẳng bên dưới phíp, giữ mũi khoan vuông góc 90°, tốc độ cao và lực ấn nhẹ để không làm bong vòng đồng `B.Cu`. Sau khi khoan xong, dùng giấy nhám mịn P1200 chà nhẹ mặt đồng để sạch ba-via rồi phủ một lớp mỏng nhựa thông pha cồn (flux) chống oxy hóa.

---

## 6. Thứ tự hàn linh kiện & Dây nhảy mặt trên

Đặt tờ **`placement_top_silk_1to1.pdf`** ngay bên cạnh (hoặc dán nhẹ mặt giấy mỏng lên mặt trên rồi chọc chân xuyên qua) để cắm đúng vị trí và đúng cực tính. **Hàn từ linh kiện thấp nhất đến cao nhất**:

1. **7 dây nhảy mặt trên (`JP1..JP7` / `J-1..J-7`) — HÀN ĐẦU TIÊN**:
   - Dùng dây đồng lõi đặc **22 AWG** có vỏ cách điện (gợi ý: **Cam** cho `J-1, J-2, J-3` là `+3.3V`; **Đỏ** cho `J-4, J-5, J-6, J-7` là `+5V`).
   - Tra chiều dài từng dây trong **`jumper_list.md`** (`7.62 mm` đến `35.56 mm`), cắt dư `+12 mm`, tuốt 2 đầu, bẻ góc 90° cắm từ mặt trên xuống mặt đồng `B.Cu` và hàn chặt.
   - Đảm bảo **`J-1`** (và `R4`) nằm sát mặt phíp để không cấn đáy NodeMCU.
2. **Điện trở 1/4W (`R1..R9`)**: `R1, R2 = 220 Ω`; `R8 = 1 kΩ`; `R5, R6 = 2.2 kΩ`; `R3, R4, R7, R9 = 10 kΩ`.
3. **Diode 1N4007 (`D1, D2`)**: Kiểm tra kỹ **vạch bạc cực âm (Cathode = chân 1)** hướng về phía `+PUMP_5V` (ở `D1`) và `+D8_BUZZER` (ở `D2`), đúng theo vạch dày trên bản `placement_top_silk_1to1.pdf`.
4. **Tụ gốm (`C3, C5, C6, C7`)** và **LED nguồn 3 mm (`D3`)**: `C3, C6, C7 = 100 nF`, `C5 = 10 nF` (không phân cực); LED `D3` chân dài hơn (Anode `+`) vào chân 2 nối `R8`, chân ngắn / cạnh vát phẳng (Cathode `-`) vào chân 1 nối `GND`.
5. **Tất cả header 2.54 mm (`J3..J15`) & 2 thanh đế cái 1×15 (`U1, U2`)**:
   - *Mẹo căn thẳng `U1` và `U2`*: Cắm tạm 1 mạch NodeMCU (hoặc 2 header đực) vào 2 thanh cái `U1, U2` để cố định chuẩn khoảng cách `22.86 mm`, hàn trước 2 chân ngoài cùng mỗi thanh rồi kiểm tra vuông góc trước khi hàn hết 30 chân.
6. **Tụ hóa phân cực (`C1, C2 = 470 µF 16V`, `C4 = 10 µF 16V`)**: Kiểm tra kỹ **chân dương `+` (chân dài)** vào lỗ pad vuông (chân 1), **vạch sọc trắng `-`** vào lỗ pad bầu dục (chân 2).
   - *Lưu ý riêng cho `C4` (`10 µF 16V`)*: `C4` nằm ngay phía trước hành lang cắm cáp Micro-USB của NodeMCU; nên dùng tụ lùn (`H ≤ 7 mm`) hoặc **bẻ gập thân tụ `C4` nằm ngang sát mặt bo về phía dưới/trái** trước khi hàn để không cấn đầu nhựa to của cáp Micro-USB.
7. **2 Domino bắt vít 5.08 mm (`J1, J2`)**: Miệng đưa dây hướng ra cạnh trái bo mạch, hàn đủ thiếc dày vì chịu dòng nguồn 5V và bơm nước.

---

## 7. Kiểm tra thông mạch bằng đồng hồ vạn năng (BẮT BUỘC trước khi cắm NodeMCU)

Chuyển đồng hồ về thang đo **thông mạch (Buzzer / Ω)**, **CHƯA cắm NodeMCU và CHƯA cấp nguồn**:

1. **Kiểm tra KHÔNG chạm chập (Short Check)**:
   - Đo giữa `+5V` (`J1.1`) và `GND` (`J1.2`): **KHÔNG kêu bíp** (điện trở tăng dần do tụ 470 µF nạp, sau vài giây > vài kΩ).
   - Đo giữa `+3.3V` (`U1.11`) và `GND` (`U1.10`): **KHÔNG kêu bíp**.
   - Đo giữa `+5V` (`J1.1`) và `+3.3V` (`U1.11`): **KHÔNG kêu bíp**.
2. **Kiểm tra thông mạch đường nguồn & 7 dây nhảy**:
   - `GND` (`J1.2`) phải thông mạch tới: `U1.10`, `U1.14`, `U2.7`, `U2.14`, `J2.2`, `J3.3`, `J4.2`, `J6.2`, `J7.2`, `J9.2`, `J11.2`, `J12.2`, `J13.3`, `J14.2`, `J15.2`.
   - `+5V` (`J1.1`) phải thông mạch tới: `U1.15`, `J8.1`, `J10.1`, và qua `J-4..J-7` tới `J9.1`, `J7.1`, `J3.2`.
   - `+3.3V` (`U1.11`) phải thông mạch qua `J-1, J-2, J-3` tới: `U2.6`, `U2.15`, `J14.1`, `J15.1`, `J13.1`.
3. **Thử cấp nguồn nguội (Smoke Test)**:
   - Cấp nguồn **5V 2A** vào `J1` (chưa cắm NodeMCU): LED nguồn xanh `D3` phải sáng ngay; dùng đồng hồ đo DC xác nhận `J1.1`, `U1.15`, `J3.2`, `J7.1`, `J9.1` đều đúng `5.0 V ± 0.2 V`.
   - Ngắt nguồn, cắm **NodeMCU v2 Amica** đúng chiều (**cổng Micro-USB quay xuống cạnh dưới**, hướng về `J12`), cấp nguồn lại và đo `U1.11` / `J13.1` xác nhận đúng `3.3 V ± 0.1 V`, sau đó mới cắm lần lượt các module ngoại vi.
