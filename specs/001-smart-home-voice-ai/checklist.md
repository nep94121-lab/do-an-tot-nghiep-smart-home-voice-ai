# Verification Checklist (`/speckit.checklist`)

- [x] **CHK-01 (Constitution Điều 1):** Người lạ nói Lần 1 $\rightarrow$ `"Tôi không được phép nhận lệnh từ người lạ."`
- [x] **CHK-02 (Constitution Điều 1):** Người lạ nói Lần 2 $\rightarrow$ `"Tôi sẽ không trả lời bạn lần nữa."`
- [x] **CHK-03 (Constitution Điều 1):** Người lạ nói Lần 3+ $\rightarrow$ Im lặng tuyệt đối (`silent_ignore = True`, `rejection_speech = ""`).
- [x] **CHK-04 (Constitution Điều 2):** Giọng thật Chủ nhà Cấp 1 (`owner_voice_1`, `custom_enrolled: True`) được bảo toàn và khử sai số nhảy nửa quãng tám (`87.4 Hz`), không bị báo nhầm là Người lạ hay `2 người`.
- [x] **CHK-05 (Constitution Điều 3):** `gemini_receive_loop` tự kết nối lại ngầm, giữ WebSocket `/ws` ổn định và chỉ xác thực giọng 1 lần/câu qua `_ensure_current_mic_utterance_verified`.
- [x] **CHK-06 (Constitution Điều 4):** Link mời phân cấp (`Cấp 1 -> Cấp 2, 3`, `Cấp 2 -> Cấp 3`, `Cấp 3 -> Không có`), Google OAuth Gmail OTP và khóa/mở quyền bằng giọng nói hoạt động 100%.
- [x] **CHK-07 (Constitution Điều 5 & 6):** Toàn bộ bài kiểm thử `scripts/test_simulator_e2e.py` đạt `Exit Code: 0`.
