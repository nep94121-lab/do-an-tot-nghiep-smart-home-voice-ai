# Nhật Ký Phát Hành (`CHANGELOG.md`)

Tài liệu ghi nhận toàn bộ các mốc tích hợp, bản sửa lỗi và tái cấu trúc của **Smart Home Voice AI**.

---

## `v1.0` — 2026-11-23

Phiên bản phát hành hoàn chỉnh đầu tiên của trợ lý nhà thông minh giọng nói tiếng Việt theo hợp đồng phần cứng khóa cứng **6 thiết bị + 3 cảm biến**.

### 1. Các Nhánh & Mốc Phát Triển Đã Tích Hợp
- **`master` (`d46c1dd`):** Nền tảng máy chủ thường trú FastAPI + SQLite 3NF WAL, đồng bộ `SSE`/`WebSocket` `< 1s`, phân quyền phiên 3 tầng, Web 3D Digital Twin, ứng dụng Android Compose và bộ thiết kế PCB/Mica.
- **`wokwifix-20261122` (`27b3383`):** Đồng bộ tuyệt đối trình mô phỏng `/wokwi`, `firmware/wokwi/diagram.json` và `docs/phan_cung/WIRING_TABLE.md` với mạch PCB Hub DIY `100 × 80 mm` (10 chân NodeMCU ESP8266, 40 dây nối).
- **`autotool-20261122` (`7247444`):** Chuẩn hóa bộ đăng ký công cụ AI thống nhất (`backend/ai_tool_registry.py`), bộ máy luật tổ hợp `AND`/`OR` đa cảm biến (`backend/automation_engine.py`, `backend/compound_nlu.py`), lịch lặp theo thứ trong tuần và giao diện Tự động hóa trực tiếp (`/automation`).
- **`voicefix8-20261122` (`2604041`):** Gỡ bỏ hardcode benchmark, tái thiết kế bộ NLU/ASR tiếng Việt tổng quát (bảo toàn 0 hành động giả trên tập đối kháng) và củng cố phân quyền giọng nói Cấp 1 (tích hợp cùng `autotool-20261122` tại `07b6e94`, hợp nhất nhánh phát hành tại `565ad1d`).

### 2. Hợp Đồng Phần Cứng Khóa Cứng (`6 Thiết bị + 3 Cảm biến`)
- Khóa cứng 6 thiết bị chấp hành: `main_door` (`D1`), `living_room_light` (`D0`), `bedroom_light` (`D4` Active-LOW), `garden_pump` (`D6`), `alarm_siren` (`D8` qua NPN `Q1 S8050`), `speaker_amp` (`D7` + PWM `D3`).
- Khóa cứng 3 cảm biến: `DHT11` (`D2`), độ ẩm đất `LM393/YL-69` (`A0`), cảm biến âm thanh `KY-037/038` (`D5`).
- Loại bỏ hoàn toàn thiết bị cũ không còn trong phạm vi phần cứng (`fan`, `ac`, `IR` / `VS1838B`) trên Backend, Web, Android, Firmware và Tài liệu; lưu trữ an toàn `ir_devices_db.json` và 4 tệp TTS cũ của Android sang kho lưu trữ ngoài repo.

### 3. Bản Vá Lỗi Nghiêm Trọng & Hoàn Thiện (`Phase 3` — `5e74f0d`, `7efb4d5`)
- **Backend, Voice & Web (`5e74f0d`):**
  - `CRIT-01`: Giải quyết triệt để deadlock trên `/api/health` khi khởi động lạnh (~89s) do khóa `_WARM_LOCK` lúc nạp trước mô hình STT cục bộ (`backend/voice/vietnamese_stt.py`).
  - `CRIT-02`: Sửa lỗi tài khoản Cấp 2 đăng ký qua link mời mất `user_id` và `link_permission` (HTTP 403) sau khi hết TTL bộ đệm phiên (`backend/api/routes_auth.py`, `backend/auth/session_store.py`).
  - `CRIT-03`: Xử lý tổng quát cụm động từ dừng/nghỉ (`nghỉ|ngừng|dừng|thôi` + động từ hoạt động, ví dụ *"cho cái bơm vườn nghỉ chạy đi em"*) ưu tiên sang `turn_off` trước khi khớp động từ bật (`backend/voice/vietnamese_policy.py`).
  - `CRIT-04`: Chặn lỗi nhận diện nhầm `echo_suppressed` ngay sau phản hồi từ chối `"Xin lỗi..."` (`backend/live/echo_and_speech_guard.py`).
  - `TRIV-01`..`TRIV-06`: Bổ sung endpoint `GET /api/timers`, chuẩn hóa lỗi HTTP 404/405 100% tiếng Việt, dọn trạng thái luật giữa các kịch bản kiểm thử giọng nói, bảo vệ truy vấn trạng thái thiết bị và hoàn thiện ẩn/hiện RBAC trên giao diện Web (`/logs`, `/automation`, `/wokwi`, khung mã mời QR).
- **Ứng dụng Android gốc (`7efb4d5`):**
  - `CRIT-05`: Đồng bộ chuẩn 6 thiết bị (gỡ bỏ điều hòa/quạt trần, bổ sung `speaker_amp`, lưu trữ 4 tệp mp3 TTS cũ).
  - `CRIT-06`: Bắt buộc cổng đăng nhập khi khởi động lạnh (không hiển thị sẵn trạng thái Chủ nhà giả định) và lọc thiết bị theo đúng phân quyền Cấp 1/2/3.
  - `CRIT-07`: Kết nối máy quét mã QR thực tế với `POST /api/guest/redeem`.
  - `CRIT-08`: Gỡ bỏ giao diện đăng ký giọng nói 3 bước cũ vốn gọi endpoint đã bị loại bỏ (`HTTP 410`).
  - `CRIT-09` & `TRIV-07`: Chuyển sang xử lý lỗi mạng fail-closed (không báo thành công giả khi phản hồi `null`), loại bỏ hardcode `actor_id`, gọi `POST /api/auth/logout` khi đăng xuất, hỗ trợ dự phòng `127.0.0.1:8088` và bổ sung thẻ cảm biến độ ẩm DHT11 + âm thanh KY-037.

### 4. Dọn Dẹp, Lưu Trữ & Tái Cấu Trúc Kho Mã Nguồn (`Phase 4` — `1dc8a3b`)
- Di chuyển toàn bộ 126 tệp báo cáo lịch sử, ảnh chụp cũ, mockup và dữ liệu IR không còn dùng ra kho lưu trữ ngoài repo (kèm bản kê SHA-256 đầy đủ).
- Tái cấu trúc thư mục gốc gọn gàng, rõ tầng:
  - `simulator/` -> `backend/` (gộp proxy Vercel từ `api/index.py` -> `backend/vercel_proxy.py`)
  - `simulator/static/` + `mobile_app/` + `public/` -> `web/` (`web/mobile/`, `web/public/`, bảo toàn nguyên vẹn `web/models/smarthome_villa.glb` 4,060,888 bytes)
  - `android_app/` -> `app/` (gỡ bỏ nhánh dư thừa `"đèn và quạt"` trong `MainScreen.kt`)
  - `firmware_esp8266/` -> `firmware/`
  - `hardware/freecad/mica/` -> `hardware/mica/`
  - Khởi tạo thư mục sạch `docs/screenshots/` và bổ sung `data-max-tier="2"` cho liên kết `/wokwi` trên `web/auth.html`.
- Bảo toàn 100% mã băm SHA-256 cho toàn bộ `48/48` tệp âm thanh `.wav` chuẩn.

### 5. Bộ Tài Liệu Phát Hành `v1.0` (`Phase 5`)
- Hoàn thiện và kiểm chứng liên kết 5 tài liệu phát hành: [`README.md`](README.md), [`USER_GUIDE.md`](USER_GUIDE.md), [`docs/HARDWARE_BUILD_GUIDE.md`](docs/HARDWARE_BUILD_GUIDE.md), [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) và [`CHANGELOG.md`](CHANGELOG.md).
