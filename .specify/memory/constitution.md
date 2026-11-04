# 📜 HIẾN PHÁP HỆ THỐNG (PROJECT CONSTITUTION) — 3D SMART HOME VOICE AI
> **Chuẩn GitHub Spec Kit (`/speckit.constitution`)**
> Tệp này định nghĩa các **Quy Tắc Bất Biến (Non-Negotiable Invariants)** của dự án. Mọi tác vụ sửa lỗi (`/speckit.bug.fix`), thêm tính năng (`/speckit.implement`) hoặc chia nhóm Subagent Team đều bắt buộc phải đối chiếu với Hiến pháp này trước và sau khi chạm vào code (`/speckit.converge`).

---

## Điều 1. Quy Tắc 3 Lần Chặn Giọng Người Lạ (3-Strike Stranger Protocol)
- **File chịu trách nhiệm:** `simulator/voice_auth.py`, `simulator/server.py`, `simulator/static/app.js`
- **Bất biến bắt buộc:**
  1. **Lần 1 (`strike == 1`):** Hệ thống chặn lệnh, hiển thị và phát âm thanh đúng câu:
     `"Tôi không được phép nhận lệnh từ người lạ."` (`silent_ignore = False`, `should_reply = True`).
  2. **Lần 2 (`strike == 2`):** Hệ thống chặn lệnh, hiển thị và phát âm thanh đúng câu:
     `"Tôi sẽ không trả lời bạn lần nữa."` (`silent_ignore = False`, `should_reply = True`).
  3. **Lần 3 trở đi (`strike >= 3`):** Hệ thống vẫn nghe nhưng **IM LẶNG TUYỆT ĐỐI**:
     `rejection_speech = ""`, `silent_ignore = True`, `should_reply = False`, ngắt toàn bộ hàng đợi âm thanh (`clearAudioQueue()` + `speechSynthesis.cancel()`).

---

## Điều 2. Nhận Diện Giọng Thật Chủ Nhà & Khử Nhảy Nửa Quãng Tám (Voice DSP Integrity)
- **File chịu trách nhiệm:** `simulator/voice_auth.py`, `simulator/data/voiceprints.json`
- **Bất biến bắt buộc:**
  1. Hồ sơ `owner_voice_1` (Cấp 1 — Nguyễn Tuấn Anh) khi đã thu âm giọng thật (`custom_enrolled: True`) phải được bảo toàn qua mọi lần khởi động Server và giữ song song `embedding` giọng thật cùng `baseline_embedding`.
  2. Bộ trích xuất `extract_voice_features` phải có **Sub-harmonic Octave Guard** để không bắt nhầm hài âm trầm nửa quãng tám (`~80–105 Hz` như `87.4 Hz`) khi tần số cơ bản thực là `~135–175 Hz`.
  3. Bộ phân tách đa người nói `detect_multi_speaker_and_resolve_priority` không được để các hồ sơ mẫu giả lập chưa thu âm (`custom_enrolled: False`) chia cắt câu nói 1 mình của Chủ nhà thành `2 người`.

---

## Điều 3. Kết Nối Gemini 3.8 Live Bất Tử (Zero-Drop Live Bridge)
- **File chịu trách nhiệm:** `simulator/server.py` (`LiveBridgeSession`)
- **Bất biến bắt buộc:**
  1. Vòng lặp `gemini_receive_loop()` phải tự động kết nối lại ngầm với Gemini 3.8 Live nếu phiên upstream đóng, **tuyệt đối không làm ngắt kết nối WebSocket `/ws` của trình duyệt**.
  2. Mỗi câu nói qua Mic (`mic_chunk` / `mic_speech_ended`) chỉ được kiểm tra xác thực giọng nói **đúng 1 lần duy nhất** (`_ensure_current_mic_utterance_verified`) trước khi cho phép `tool_call` hoặc `audio_chunk` của Gemini phát ra.

---

## Điều 4. Phân Quyền 3 Cấp, Link Mời Phân Cấp & OAuth Gmail OTP (`/auth`)
- **File chịu trách nhiệm:** `simulator/auth_system.py`, `simulator/rule_engine.py`, `simulator/static/auth.html`
- **Bất biến bắt buộc:**
  1. **Cấp 1 (Admin tối cao — Nguyễn Tuấn Anh):** Toàn quyền 7 thiết bị, sửa mọi luật hệ thống bằng giọng nói, tạo được link mời **Cấp 2** và **Cấp 3**, khóa/mở lại quyền của bất kỳ ai bằng giọng nói (khi khóa thì tài khoản vẫn còn nhưng báo không có quyền).
  2. **Cấp 2 (Thành viên gia đình):** Có bể lệnh & hẹn giờ riêng biệt (cô lập với Cấp 1), chỉ tạo được link mời **Cấp 3**, không mở được Cửa chính (trừ khi Cấp 1 mở quyền).
  3. **Cấp 3 (Khách):** Không có quyền tạo link mời, chỉ điều khiển thiết bị cơ bản (Đèn, Quạt).
  4. Người nhận link mời phải đăng nhập Google OAuth + xác thực mã OTP 6 số gửi về Gmail thật + giữ nút thu âm câu mẫu trên Web/App để trích xuất vân giọng lưu lên Server.

---

## Điều 5. Trả Lời Ngắn Gọn, Bể 1 (Hẹn Giờ AM/PM) & Bể 2 (Xác Nhận Luật IF-ELSE)
- **File chịu trách nhiệm:** `simulator/rule_engine.py`
- **Bất biến bắt buộc:**
  1. Thiết bị đã ở sẵn trạng thái yêu cầu phải trả lời: `"<Tên thiết bị> đã mở/đóng/bật/tắt sẵn rồi."`
  2. Đặt luật IF-ELSE / Đổi khẩu lệnh phải hỏi xác nhận trước khi lưu vào Bể 2 (trừ khi Admin Cấp 1 tắt yêu cầu xác nhận).
  3. Hẹn giờ không nói rõ AM/PM phải tự động tạo 2 lịch (cả `AM` và `PM`); hẹn giờ 1 lần (`once`) chạy xong tự xóa khỏi Bể 1.

---

## Điều 6. Chế Độ Offline Mạch Độc Lập ESP8266 & CSDL 3NF
- **File chịu trách nhiệm:** `simulator/rule_engine.py`, `simulator/database.py`, `firmware/smart_home_esp8266/smart_home_esp8266.ino`
- **Bất biến bắt buộc:**
  1. Khi mất kết nối Server Laptop (`Offline`), mạch ESP8266 tự động **đóng và khóa cứng Cửa chính + Còi báo động**, vô hiệu hóa khẩu lệnh custom, và chỉ duyệt giọng Cấp 1 & Cấp 2 bằng Tiny-DSP.
  2. CSDL SQLite `smarthome.db` duy trì đủ 8 bảng chuẩn 3NF, bật `WAL` và `FOREIGN KEYS = ON`.
