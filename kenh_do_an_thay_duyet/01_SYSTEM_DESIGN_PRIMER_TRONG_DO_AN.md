# 🏛️ ÁP DỤNG CHUẨN KIẾN TRÚC "THE SYSTEM DESIGN PRIMER" VÀO ĐỒ ÁN TỐT NGHIỆP

Tài liệu này đối chiếu trực tiếp các nguyên lý thiết kế hệ thống cốt lõi từ kho tài liệu **[The System Design Primer](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/tai_lieu_tham_khao/system-design-primer/README.md)** (đã tải đầy đủ về máy tại `docs/tai_lieu_tham_khao/system-design-primer/`) vào kiến trúc **Hệ thống Nhà thông minh Giọng nói AI – Phân quyền 3 tầng – MQTT – ESP8266** của bạn.

Khi bảo vệ trước Hội đồng hoặc giải thích Chương 2 (Phân tích & Thiết kế) và Chương 3 (Triển khai MQTT & Giao diện), bạn có thể dùng đúng khung **4 Bước System Design Primer** dưới đây để trả lời mọi câu hỏi xoáy của các thầy:

---

## BƯỚC 1: XÁC ĐỊNH USE CASES, RÀNG BUỘC & THÔNG SỐ ĐỊNH LƯỢNG (CONSTRAINTS & BACK-OF-THE-ENVELOPE ESTIMATES)

Theo *System Design Primer*, mọi thiết kế tốt đều bắt đầu từ việc định lượng rõ đầu vào, đầu ra và ràng buộc độ trễ:
1. **Băng thông luồng âm thanh thời gian thực (Audio Streaming Bandwidth):**
   - Tín hiệu thu âm chuẩn PCM 16-bit, đơn kênh (Mono), tần số lấy mẫu $f_s = 16000\text{ Hz}$:
     $$\text{Bitrate} = 16000\text{ mẫu/s} \times 16\text{ bit} = 256\text{ kbps} = 32\text{ KB/s}$$
   - Chia theo từng khung (Chunk) $20\text{ ms}$ ($320\text{ mẫu} = 640\text{ bytes/gói}$) truyền qua WebSocket, đảm bảo không gây nghẽn bộ đệm mạng.
2. **Tỷ lệ Đọc / Ghi (Read-to-Write Ratio):**
   - **Luồng đọc trạng thái & kiểm tra quyền (Read-heavy $\approx 90\%$):** Mỗi khi có giọng nói hoặc sự kiện cảm biến, hệ thống phải kiểm tra quyền 3 tầng, đọc Bể 1 (Hẹn giờ), Bể 2 (Luật IF-ELSE) và truy vấn Vector RAG $3072$ chiều.
   - **Luồng ghi cấu hình (Write $\approx 10\%$):** Chỉ xảy ra khi đặt lịch mới, xét luật mới, thu âm cấp quyền mới hoặc khi Admin Cấp 1 sửa quy tắc hệ thống.

---

## BƯỚC 2: CÁC ĐÁNH ĐỔI KIẾN TRÚC CỐT LÕI (ARCHITECTURAL TRADE-OFFS THEO SYSTEM DESIGN PRIMER)

### 2.1. Định lý CAP (CAP Theorem: Consistency vs Availability khi đứt mạng)
Trong *System Design Primer* (Mục *Availability vs Consistency – CAP Theorem*), một hệ thống phân tán giữa **Server Trung tâm** và **Trạm vi điều khiển biên (ESP8266)** khi xảy ra phân mảnh mạng (**P – Network Partition**, ví dụ mất kết nối Server hoặc tắt Laptop) phải lựa chọn giữa `CP` và `AP`:
- **Khi kết nối Wi-Fi/MQTT bình thường:** Hệ thống vận hành ở chế độ **Strong Consistency** — mọi thay đổi trên Server, Web 3D, Mobile App và mạch ESP8266 được đồng bộ tức thì ($< 30\text{ ms}$).
- **Khi mất kết nối tới Server (Network Partition):** Hệ thống thiết kế theo mô hình **AP (Availability + Partition Tolerance)** kết hợp **Active-Passive Failover tại biên**:
  - Nhờ Topic MQTT `smarthome/sync/pools` (`Retain = True`), mạch **NodeMCU ESP8266** luôn giữ một bản sao (**Replica**) của Bể 1 (Hẹn giờ) và Bể 2 (Luật IF-ELSE) trong bộ nhớ Flash `LittleFS`.
  - Ngay khi mất kết nối Server, ESP8266 tự động chuyển sang chế độ **Edge Autonomous (Tự trị tại biên)**, tiếp tục chạy đúng các lịch hẹn giờ (nhờ đồng hồ NTP nội bộ) và các luật liên động `IF - ELSE` mà không bị tê liệt (**Loại bỏ hoàn toàn Single Point of Failure – SPOF**).

### 2.2. Chiến lược Bộ nhớ đệm: In-Memory Cache kết hợp Write-Through (`simulator/rule_engine.py` & `knowledge_rag.py`)
Theo *System Design Primer* (Mục *Cache – Write-through vs Cache-aside*):
- Nếu mỗi lần người dùng ra lệnh giọng nói mà Server phải đọc file từ ổ cứng SSD/HDD ($\approx 1\text{--}10\text{ ms}$) hoặc gọi API tính lại Vector Embedding ($\approx 300\text{ ms}$) thì tổng độ trễ sẽ rất cao.
- **Giải pháp đã cài đặt trong dự án:**
  1. **Application In-Memory Cache (RAM $\approx 100\text{ ns}$):** Toàn bộ trạng thái 6 thiết bị (`self.devices`), Bể 1 (`self.active_timers`), Bể 2 (`self.overlay_rules`) và ma trận Vector RAG $3072$ chiều (`self.embeddings`) đều được nạp sẵn trên RAM. Việc kiểm tra quyền 3 tầng và duyệt đồ thị `DFS Cycle Detection` chỉ mất **$< 0.5\text{ ms}$**.
  2. **Chiến lược Write-Through Cache:** Ngay khi có lệnh cập nhật luật mới hoặc cấp quyền mới, `SmartHomeEngine` cập nhật ngay trên RAM và **ghi xuyên suốt (Write-Through)** xuống đĩa (`custom_rules_overlay.json`, `voiceprints.json`, `knowledge_embeddings_cache.json`), đảm bảo dữ liệu luôn bền vững 100% khi tắt nguồn.

### 2.3. Xử lý Bất đồng bộ & Hàng đợi Thông điệp (Asynchronism, Message Queues & Back Pressure)
Theo *System Design Primer* (Mục *Asynchronism – Message Queues & Task Queues*):
- **Message Queue (MQTT Pub/Sub):** Tách rời hoàn toàn (**Decoupling**) giữa tầng xử lý AI (`server.py`) và tầng phần cứng (`ESP8266`). Server không bị treo chờ phần cứng phản hồi mà phát hành bản tin bất đồng bộ qua MQTT Broker.
- **Task Queue (`asyncio` Event Loop):** Các bộ hẹn giờ trong **Bể 1** (`_timer_tasks`) và hiệu ứng nháy đèn thu âm `3-2-1` (`blink_signal_light`) chạy trên các Coroutine độc lập, không bao giờ làm nghẽn (`block`) luồng nhận giọng nói.
- **Chống quá tải (Back Pressure & Rate Limiting):** Cơ chế **2-Strike Silent Ignore** trong `voice_auth.py` chính là một bộ **Rate Limiter / Circuit Breaker** ở tầng sinh trắc học: Khi phát hiện giọng người lạ cố tình spam lệnh quá 2 lần, hệ thống ngắt phản hồi âm thanh từ lần thứ 3 (`silent_ignore = True`), bảo vệ tài nguyên xử lý AI và loa thông báo.

### 2.4. Phối hợp Đa giao thức Truyền thông (HTTP REST vs WebSocket vs MQTT)
Đúng theo bảng so sánh giao thức trong *System Design Primer* (Mục *Communication*):

| Giao thức trong Đồ án | Tầng vận chuyển | Đặc tính kỹ thuật | Lý do lựa chọn theo System Design Primer |
| :--- | :---: | :--- | :--- |
| **1. HTTP REST (`/api/state`, `/api/voice_samples`)** | TCP | Stateless, Request-Response, Cacheable | Dùng khi trình duyệt/App mới mở trang lần đầu để lấy danh sách mẫu âm thanh và cấu hình khởi tạo. |
| **2. WebSocket (`/ws`)** | TCP | Full-Duplex (Song công toàn phần), Kết nối giữ sống (Persistent) | Truyền luồng âm thanh PCM 16kHz thời gian thực và đẩy sự kiện cập nhật mô hình Nhà 3D tức thì không tốn header HTTP thừa. |
| **3. MQTT (`smarthome/#`)** | TCP | Publish/Subscribe, Header tối giản chỉ `2 bytes`, có `QoS 0/1` & `LWT` | Tối ưu tuyệt đối cho vi điều khiển nhúng RAM nhỏ như **NodeMCU ESP8266** hoạt động qua mạng không dây Wi-Fi. |

### 2.5. Bảo mật theo Nguyên tắc Đặc quyền Tối thiểu (Security – Principle of Least Privilege)
Trong *System Design Primer* (Mục *Security*), nguyên tắc quan trọng nhất là **Principle of Least Privilege** (Mỗi tác nhân chỉ được cấp đúng quyền tối thiểu cần thiết để thực hiện nhiệm vụ):
- **Tầng 3 (Khách):** Chỉ có quyền gọi lệnh đóng/mở cố định, bị cô lập hoàn toàn khỏi Bể 1 (Hẹn giờ), Bể 2 (Luật động) và thông tin riêng tư trong RAG.
- **Tầng 2 (Thành viên gia đình):** Được cấp không gian tên riêng (**Namespace Isolation / Sharding theo `user_id` trong `user_pools`**), chỉ sửa/xóa được lịch hẹn và bể lệnh của chính mình, không thể xâm phạm lịch hẹn hay quyền của Tầng 1.
- **Tầng 1 (Admin – Nguyễn Tuấn Anh):** Nắm quyền điều phối chính sách toàn cục (`system_policies`).
