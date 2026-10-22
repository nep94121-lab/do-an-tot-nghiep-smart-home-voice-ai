# 📐 QUY CHUẨN ĐỊNH DẠNG BÁO CÁO ĐỒ ÁN TỐT NGHIỆP — TRƯỜNG ĐIỆN - ĐIỆN TỬ (SEEE), ĐẠI HỌC BÁCH KHOA HÀ NỘI (HUST)

Tài liệu này tổng hợp quy định trình bày chuẩn của **Trường Điện – Điện tử (School of Electrical and Electronic Engineering - SEEE), Đại học Bách khoa Hà Nội (HUST)** kết hợp đúng 100% khung yêu cầu duyệt tiến độ **Chương 1 – Chương 2 – Chương 3** của Giảng viên hướng dẫn.

---

## 1. BỐ CỤC 3 CHƯƠNG THEO ĐÚNG YÊU CẦU CỦA GIẢNG VIÊN HƯỚNG DẪN (CHUẨN SEEE - HUST)

Trong biểu mẫu Đồ án Cử nhân định hướng Thiết kế – Triển khai Hệ thống Nhúng & IoT của Trường Điện – Điện tử (ĐHBK Hà Nội), toàn bộ nội dung cốt lõi được gói gọn trong **3 Chương chuẩn**:

| Chương | Tên Chương Chuẩn (Viết Hoa, 16pt, Đậm) | Nội dung bắt buộc theo yêu cầu của Thầy hướng dẫn | File tương ứng trong thư mục này |
| :---: | :--- | :--- | :--- |
| **CHƯƠNG 1** | **CHƯƠNG 1. TỔNG QUAN HỆ THỐNG** | 1. Đặt vấn đề & bối cảnh thực tế.<br>2. **Đối tượng theo dõi và điều khiển là gì?** (6 thiết bị chấp hành, thông số vi khí hậu Nhiệt độ/Độ ẩm, ngoại vi Hồng ngoại IR).<br>3. **Dùng công nghệ nào?** (Vi điều khiển NodeMCU ESP8266, Giao thức MQTT/WebSocket, Xử lý tín hiệu DSP giọng nói $F_0$ Hz + Phân quyền 3 tầng, AI Gemini Live + RAG Vector 3072 chiều, Sóng hồng ngoại 38kHz, Digital Twin 3D). | [CHUONG_1_TONG_QUAN_HE_THONG.md](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/kenh_do_an_thay_duyet/CHUONG_1_TONG_QUAN_HE_THONG.md) |
| **CHƯƠNG 2** | **CHƯƠNG 2. PHÂN TÍCH VÀ THIẾT KẾ HỆ THỐNG** | 1. **Hệ thống có những chức năng gì?** (Bảng đặc tả chức năng theo 3 tầng Admin / Gia đình / Khách, Bể 1 Hẹn giờ, Bể 2 Luật IF-ELSE & Đổi lệnh, Học lệnh Remote IR, Cảm biến DHT11, 4 chế độ Reset).<br>2. **Làm việc theo quy trình như thế nào?** (Sơ đồ khối tổng thể, Lưu đồ thuật toán xử lý giọng nói, Lưu đồ thu âm cấp quyền `3-2-1` nháy đèn, Lưu đồ xử lý 2 Bể & chống vòng lặp DFS).<br>3. **Xác định quy trình thiết kế** (Quy trình thiết kế Phần cứng ESP8266 + cảm biến + IR & Quy trình thiết kế Phần mềm 3 phân hệ tự xây dựng). | [CHUONG_2_PHAN_TICH_VA_THIET_KE_HE_THONG.md](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/kenh_do_an_thay_duyet/CHUONG_2_PHAN_TICH_VA_THIET_KE_HE_THONG.md) |
| **CHƯƠNG 3** | **CHƯƠNG 3. TRIỂN KHAI VÀ KẾT QUẢ THỰC NGHIỆM** | 1. **Hình thức truyền thông MQTT như thế nào?** (Kiến trúc MQTT Broker - Publisher - Subscriber, Bảng quy hoạch Topic MQTT chuẩn, Cấu trúc gói tin JSON Payload, QoS, Last Will & Retain, Đồng bộ Flash).<br>2. **Thiết kế chức năng giao diện & Kết quả triển khai giao diện** (Web Dashboard trung tâm & Nhà 3D Digital Twin, Giao diện Bể 1 & Bể 2, Giao diện Phân quyền giọng nói $F_0$ Hz, Giao diện Mobile App & Học lệnh Remote IR).<br>3. **Kết quả kiểm thử thực nghiệm** (Bảng đo độ trễ ms, độ chính xác nhận diện giọng nói và kiểm thử E2E). | [CHUONG_3_TRIEN_KHAI_VA_KET_QUA_GIAO_DIEN_MQTT.md](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/kenh_do_an_thay_duyet/CHUONG_3_TRIEN_KHAI_VA_KET_QUA_GIAO_DIEN_MQTT.md) |

---

## 2. QUY ĐỊNH HÌNH THỨC TRÌNH BÀY VĂN BẢN (CHUẨN TRƯỜNG ĐIỆN - ĐIỆN TỬ, ĐHBK HÀ NỘI)

Khi xuất sang file Word (`.docx`) nộp cho Giảng viên hướng dẫn và Hội đồng Trường Điện – Điện tử (HUST), văn bản tuân thủ nghiêm ngặt các thông số sau:

1. **Khổ giấy & Căn lề (Page Setup):**
   - **Khổ giấy:** A4 (`210 mm × 297 mm`), in một mặt.
   - **Lề trái (Left):** `3.0 cm` (30 mm — chừa gáy đóng quyển).
   - **Lề phải (Right):** `2.0 cm` (20 mm).
   - **Lề trên (Top):** `2.0 cm` – `2.5 cm` (chuẩn 20 mm).
   - **Lề dưới (Bottom):** `2.0 cm` – `2.5 cm` (chuẩn 20 mm).

2. **Phông chữ & Cỡ chữ (Font & Typography):**
   - **Font chữ duy nhất:** `Times New Roman` (Bảng mã Unicode).
   - **Văn bản nội dung (Normal):** Cỡ chữ `13 pt`, kiểu thường (Regular), căn đều 2 bên (`Justified`), giãn dòng `1.3 lines` (hoặc `1.5 lines`), khoảng cách sau đoạn (`After`) `6 pt`, thụt đầu dòng đoạn văn `1.0 cm`.
   - **Tên Chương (Heading 1):** Cỡ chữ `16 pt`, **IN HOA ĐẬM** (VD: `CHƯƠNG 1. TỔNG QUAN HỆ THỐNG`), ngắt sang trang mới (`Page Break`) ở đầu mỗi chương.
   - **Mục cấp 1 (Heading 2 — VD: `1.1. Đối tượng theo dõi và điều khiển`):** Cỡ chữ `14 pt`, **In đậm**, viết hoa chữ cái đầu.
   - **Mục cấp 2 (Heading 3 — VD: `1.1.1. Nhóm thiết bị chấp hành trong nhà`):** Cỡ chữ `13 pt`, **In đậm**, viết hoa chữ cái đầu.
   - **Mục cấp 3 (Heading 4 — VD: `a) Khối điều khiển cửa chính`):** Cỡ chữ `13 pt`, *In nghiêng đậm*.

3. **Quy tắc đánh số Hình vẽ, Bảng biểu và Công thức toán học:**
   - **Hình vẽ:** Đánh số theo chương (`Hình 1.1`, `Hình 2.1`, `Hình 3.1`...). Chú thích hình đặt ở **BÊN DƯỚI** hình, căn giữa, cỡ chữ `12 pt` *in nghiêng*.
   - **Bảng biểu:** Đánh số theo chương (`Bảng 1.1`, `Bảng 2.1`, `Bảng 3.1`...). Tên bảng đặt ở **BÊN TRÊN** bảng, căn trái hoặc căn giữa, cỡ chữ `12 pt` **in đậm**.
   - **Công thức toán học:** Đánh số theo chương đặt sát lề phải, ví dụ `(1.1)`, `(2.1)`.

4. **Quy tắc Trích dẫn Tài liệu tham khảo:**
   - Trích dẫn theo chuẩn **IEEE** dùng ngoặc vuông `[1]`, `[2]`, `[3]` sắp xếp theo thứ tự xuất hiện hoặc theo chuẩn hướng dẫn của Bộ môn.
