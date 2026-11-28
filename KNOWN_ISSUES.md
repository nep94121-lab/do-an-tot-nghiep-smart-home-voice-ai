# Các Vấn Đề Đã Biết (`KNOWN_ISSUES.md`) — Phiên bản `v3.8.0` / `v1.0`

Tài liệu tổng hợp toàn bộ các giới hạn và vấn đề mức độ nhỏ/trung bình đã được kiểm chứng (cập nhật tới mốc `agyhw14` / `agyclean15`), **không ảnh hưởng đến an toàn vận hành lõi** (0 đảo ngược hành động, 0 thao tác giả ngoài ý muốn) và được chủ động ghi nhận minh bạch.

---

## Bảng Tổng Hợp

| Mã | Mức độ | Phân hệ | Mô tả & Tác động | Cách khắc phục tạm thời (Workaround) |
| :---: | :---: | :--- | :--- | :--- |
| **`KI-01`** | Thấp | Voice NLU (Vòng 8) | **6 ca bỏ lỡ bước dàn cảnh xác nhận (confirm-staging misses)** với các cách diễn đạt xác nhận/tạo quy tắc ít phổ biến (vòng benchmark r8). Toàn bộ 6 ca đều từ chối an toàn, **0 thao tác vật lý giả**. | Diễn đạt lại lệnh theo mẫu tiếng Việt rõ ràng (ví dụ *"Hẹn 5 phút nữa tắt đèn phòng khách"*, rồi trả lời *"Có"* / *"Đồng ý"*). |
| **`KI-02`** | Thấp | Voice NLU (Vòng 8) | **10 ca bỏ lỡ an toàn trên tập câu chưa từng thấy (unseen safe misses)** trong bộ đánh giá r8. Tất cả đều fail-closed an toàn, **0 đảo ngược lệnh, 0 kích hoạt nhầm**. | Nói rõ tên thiết bị chuẩn (cửa chính, đèn phòng khách, đèn phòng ngủ, bơm tưới cây, còi báo động, loa) hoặc thao tác qua bảng điều khiển Web/Android. |
| **`KI-03`** | Thông tin | Voice ASR Nhiễu (Vòng 8) | Bộ kiểm thử âm thanh nhiễu mạnh đạt **`233/275`** (chỉ báo cáo theo dõi — report-only; **0 đảo ngược lệnh, 0 hành động giả**). | Nói gần micro hơn, giảm tạp âm nền lớn hoặc nhập lệnh văn bản trên Web/App khi môi trường quá ồn. |
| **`KI-04`** | Trung bình | Voice STT Cục bộ (Offline) | Mô hình `ChunkFormer-CTC` không có sẵn trong bộ nhớ đệm cục bộ (`cf snap: None`), ảnh hưởng tới độ chính xác chế độ chỉ chạy offline với giọng cao/nhanh (`kid_fast` VTLN) và tín hiệu nhiễu nặng SNR 5–10 dB (`161/275` offline noisy; vẫn đảm bảo **0 đảo ngược lệnh** và **`0/66` hành động giả** trên tập đối kháng). | Chạy ở chế độ có kết nối Gemini Live / nạp sẵn snapshot `ChunkFormer-CTC` vào cache HuggingFace cục bộ khi cần vận hành hoàn toàn offline trong môi trường nhiễu nặng. |
| **`KI-05`** | Thấp | Voice NLU (Unseen QA) | Một số cách nói khẩu ngữ mới chưa xuất hiện trong tập huấn luyện ở phiên kiểm thử mở rộng `voice-unseen` gây **18 ca bỏ lỡ an toàn + 6 ca bỏ lỡ xác nhận an toàn** (**0 thay đổi trạng thái thiết bị vật lý**). | Dùng động từ/cụm từ tiếng Việt trực tiếp hơn hoặc định nghĩa câu lệnh tùy chỉnh (custom command) cho khẩu ngữ quen thuộc. |
| **`KI-06`** | Thông tin | KiCad 3D Assembly | Tệp lắp ghép trực quan 3D [`hardware/kicad/smarthome_assembly/smarthome_assembly.kicad_pcb`](hardware/kicad/smarthome_assembly/smarthome_assembly.kicad_pcb) khi chạy DRC báo 111 cảnh báo chồng lớp trục Z có chủ đích giữa khối 3D `M_NODEMCU` cắm trên đế `U1`/`U2` và 28 cảnh báo chữ in ngoài biên (0 chân hở mạch). **Lưu ý:** Mạch PCB chế tạo chính [`hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb`](hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb) đạt **0 lỗi DRC, 0 cảnh báo DRC và 0 lỗi ERC**. | Luôn xuất Gerber / in Toner Transfer từ mạch chế tạo chính `hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb` (không dùng tệp assembly 3D để gia công mạch). |
| **`KI-07`** | Thấp | Backend / Firmware Serial | Endpoint `POST /api/text_command` chưa áp dụng nhánh bỏ qua xác thực `_has_valid_hardware_key()` vốn đang dùng cho cơ chế chuyển tiếp Serial-to-HTTP của `.ino`. | Gửi lệnh điều khiển từ phần cứng qua MQTT (`smarthome/cmd/...`) hoặc truyền tiêu đề phiên đăng nhập hợp lệ (`X-Session-Token`) khi gọi `/api/text_command`. |
| **`KI-08`** | Trung bình | Firmware ESP8266 Offline | Bản sao `LittleFS` `/pools_replica.json` đồng bộ qua topic `smarthome/sync/pools` hiện mới chỉ lưu ghi (write-only), chưa tự đánh giá lịch/luật hoàn toàn độc lập khi mất kết nối server; cơ chế tự đóng cửa chính an toàn khi `/api/server_mode=false` phụ thuộc vào ngắt kết nối broker hoặc chế độ HTTP-only. | Giữ máy chủ cục bộ chạy thường trú (kèm watchdog tự khởi động lại) khi cần thực thi lịch hẹn giờ và luật tổ hợp liên tục; đảm bảo ESP8266 cấu hình đúng chế độ failover khi mất kết nối mạng. |

---

## Chính Sách Bảo Toàn An Toàn (`v3.8.0` / `v1.0`)

Toàn bộ các mục trên đều tuân thủ nguyên tắc **Fail-Closed**: trong mọi trường hợp không nhận diện chắc chắn khẩu lệnh hoặc thiếu quyền, hệ thống giữ nguyên trạng thái thiết bị vật lý và phản hồi ngắn gọn bằng tiếng Việt.

Xem thêm [Nhật ký phát hành (`CHANGELOG.md`)](CHANGELOG.md), [Hướng dẫn sử dụng (`USER_GUIDE.md`)](USER_GUIDE.md), [Hướng dẫn nạp USB & Wi-Fi runtime](docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md) và [Tổng quan phần cứng & In 3D](docs/phan_cung/TONG_QUAN_PHAN_CUNG_VA_IN_3D.md).
