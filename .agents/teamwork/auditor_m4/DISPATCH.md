## 2026-11-04T08:08:12Z
Bạn là Forensic Integrity Auditor cho Milestone 4: "Kiểm thử Giọng nói thật của Sếp & Thiết bị Di động Samsung Galaxy S9 qua ADB".
Thư mục làm việc của bạn: c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\auditor_m4\
Tệp yêu cầu gốc: c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md
Tệp kiến trúc dự án: c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\PROJECT.md
Báo cáo của Worker: c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m4\handoff.md

NHIỆM VỤ KIỂM TOÁN PHÁP Y (FORENSIC AUDIT):
1. **Kiểm tra Gian Lận (Zero-Cheat / Zero-Illusion)**:
   - Kiểm tra mã nguồn `tests/test_sep_real_voice_commands.py` và `tests/test_live_sep_voice_actuation.py`: đảm bảo không hardcode kết quả, không tạo mock/facade che giấu lỗi, mọi hàm `verify_and_execute_voice_command` và `verify_pcm16k_and_apply_strikes` đều đọc âm thanh thật và tính toán thật.
   - Kiểm tra 4 ảnh chụp màn hình trong `.agents/teamwork/worker_m4/` (`step1_login_gate.png`, `step2_main_dashboard.png`, `step3_device_control.png`, `step4_qr_guest.png`):
     - Mở trực tiếp bằng `view_file`.
     - Xác nhận đây là ảnh PNG chuẩn nhị phân (kích thước > 100KB), không phải file rỗng, không phải text đổi đuôi.
     - Kiểm tra mã băm SHA-256 thực tế của từng ảnh có trùng khớp 100% với báo cáo bàn giao không.
2. **Kiểm tra Chuẩn Mã Hóa & Xuống Dòng (0 CRLF, UTF-8 no BOM)**:
   - Kiểm tra các file test mới tạo (`tests/test_live_sep_voice_actuation.py`, `tests/test_adb_samsung_galaxy_s9.py`): phải là UTF-8 không BOM, kết thúc dòng Unix LF (`\n`), không có ký tự `\r\n`.
3. **Phán quyết**:
   - Nếu phát hiện bất kỳ hành vi gian lận nào: Báo cáo ngay **INTEGRITY VIOLATION** (Veto Gate).
   - Nếu hoàn toàn trong sạch, trung thực, chất lượng thực chất: Báo cáo **CLEAN**.
   Ghi kết luận chi tiết vào `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\auditor_m4\handoff.md` và gửi `send_message` cho Orchestrator.
