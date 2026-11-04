## 2026-11-04T17:00:17Z
Bạn là `auditor_m14` (teamwork_auditor) phụ trách kiểm toán liêm chính tư pháp (Forensic Integrity Audit) cho Milestone M14: Tái cấu trúc mô-đun hóa Ponytail (Requirement R4).

Thư mục làm việc: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\auditor_m14\
Tệp yêu cầu gốc: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md
Tệp bàn giao của Worker: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m14\handoff.md
Integrity mode: development

Nhiệm vụ trọng tâm (Forensic Integrity Verification):
1. Đọc kỹ `worker_m14/handoff.md` và `ORIGINAL_REQUEST.md`.
2. Rà soát liêm chính mã nguồn (Zero-Cheat / Zero-Facade):
   - Xác nhận các mô-đun mới trong `simulator/voice/` và `android_app/.../tabs/`, `components/`, `models/` là mã nguồn thật, có logic xử lý thực thụ, không phải dummy hay facade.
   - Xác nhận không có bất kỳ bài test nào trong `tests/` bị xóa, làm yếu hay sửa assertion để pass gian lận (`git diff tests/`).
3. Xác minh số dòng trước và sau tái cấu trúc:
   - `simulator/static/style.css` (970L -> 2L)
   - `simulator/static/app.js` (1031L -> 10L)
   - `simulator/voice_auth.py` (2551L -> 1440L)
   - `android_app/.../MainScreen.kt` (2710L -> 850L)
4. Kiểm toán định dạng 100% tệp dự án mới và sửa đổi:
   - Quét kiểm tra nhị phân: 100% phải là **UTF-8 không BOM** và **0 CRLF** (100% chuẩn POSIX LF `\n`).
5. Chạy kiểm toán thực thi:
   Chạy lệnh kiểm thử độc lập:
   `python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_challenger_m4_security.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py tests/test_p3_session_rbac_concurrency.py tests/test_p3_challenger_m12_adversarial.py --basetemp=.pytest_tmp`
   (Phải PASS 100%, xóa sạch `.pytest_tmp`).
6. Đưa ra phán quyết nhị phân dứt khoát trong `handoff.md`: **`VERDICT: CLEAN`** hoặc **`VERDICT: INTEGRITY VIOLATION`**. Báo cáo lại cho Orchestrator qua `send_message`.
