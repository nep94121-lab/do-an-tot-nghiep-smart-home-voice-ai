# Feature Specification: 3D Smart Home Voice AI — Gemini 3.8 Live, 3-Tier Voice Auth & NodeMCU ESP8266

**Feature Branch**: `001-smart-home-voice-ai`
**Created**: 2026-11-03
**Status**: Active & Enforced via `.specify/memory/constitution.md`

---

## 1. User Scenarios & Acceptance Criteria (`/speckit.specify`)

### US-01 — Xác Thực Giọng Nói Chủ Nhà & Chặn Người Lạ 3 Mức (Priority: P0)
- **Khi** Chủ nhà Cấp 1 (`Nguyễn Tuấn Anh`) đã bấm thu âm giọng thật lên Server (`custom_enrolled: True` trong `simulator/data/voiceprints.json`),
- **Thì** khi nói qua Microphone ở tần số giọng nam tự nhiên (kể cả khi xuống giọng trầm cuối câu bị hài âm nửa quãng tám `87.4 Hz`), hệ thống bắt buộc nhận diện đúng là **Cấp 1 — Nguyễn Tuấn Anh**, hiển thị `1 người (Rõ)` và thực thi lệnh ngay.
- **Khi** phát hiện giọng Người lạ (Cấp 99):
  - **Lần 1 (`strike == 1`):** Chặn lệnh, hiển thị và phát tiếng nói: `"Tôi không được phép nhận lệnh từ người lạ."`
  - **Lần 2 (`strike == 2`):** Chặn lệnh, hiển thị và phát tiếng nói: `"Tôi sẽ không trả lời bạn lần nữa."`
  - **Lần 3 trở đi (`strike >= 3`):** **Im lặng tuyệt đối** (`silent_ignore = True`, không trả lời câu nào).

### US-02 — Kết Nối Gemini 3.8 Live Liên Tục Không Rớt Mạng (Priority: P0)
- **Khi** người dùng bật Mic nói chuyện nhiều câu liên tiếp trên trang chủ `http://localhost:8088`,
- **Thì** kết nối WebSocket `/ws` giữ nguyên trạng thái `🟢 Đã kết nối gemini-3.8-live`, tự động khôi phục ngầm phiên upstream nếu mạng gián đoạn mà không bao giờ báo `🔴 Mất kết nối — Đang kết nối lại...`.

### US-03 — Phân Quyền 3 Cấp, Gửi Link Mời Đăng Ký OAuth Gmail OTP & Thu Âm (`/auth`) (Priority: P1)
- **Khi** Cấp 1 gửi link mời: Được tạo 2 loại link (**Cấp 2** hoặc **Cấp 3**).
- **Khi** Cấp 2 gửi link mời: Chỉ được tạo link **Cấp 3**.
- **Khi** Cấp 3 đăng nhập: Không có mục tạo link mời.
- **Khi** người nhận bấm vào link mời: Đăng nhập Google OAuth -> Nhận mã OTP 6 số qua Gmail -> Nhập mật khẩu -> Vào màn hình giữ nút thu âm câu mẫu để lưu vân giọng lên Server.
- **Khi** Cấp 1 ra lệnh bằng giọng nói tại nhà để khóa/mở lại quyền của một người: Tài khoản người đó vẫn còn nhưng trạng thái chuyển sang bị khóa (`revoked`) hoặc được mở lại ngay lập tức.

### US-04 — Điều Khiển 7 Thiết Bị, Hẹn Giờ AM/PM (Bể 1) & Luật Động IF-ELSE (Bể 2) (Priority: P1)
- Nhắc thiết bị đã mở/bật sẵn: `"<Thiết bị> đã mở/bật sẵn rồi."`
- Đặt luật IF-ELSE hoặc đổi khẩu lệnh phải hỏi xác nhận trước khi lưu vào Bể 2.
- Hẹn giờ thiếu AM/PM tự động đặt cả 2 mốc `AM` và `PM`; hẹn giờ 1 lần chạy xong tự xóa.
