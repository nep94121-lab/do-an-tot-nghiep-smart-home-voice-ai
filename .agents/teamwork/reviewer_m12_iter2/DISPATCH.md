## 2026-11-04T16:21:16Z
Bạn là `reviewer_m12_iter2` (teamwork_reviewer) thuộc đội ngũ phát triển Phase 3 Smart Home Voice AI.
Thư mục làm việc của bạn: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\reviewer_m12_iter2\
Tệp yêu cầu gốc: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md

Nhiệm vụ:
Kiểm tra đánh giá chất lượng (Code Review) bản sửa lỗi trong Milestone M12 Iteration 2 (Khắc phục lỗ hổng leo thang đặc quyền cookie CWE-565 / CWE-287):
1. Đọc tệp báo cáo bàn giao của Worker: `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m12_iter2\handoff.md`.
2. Kiểm tra các thay đổi trong:
   - `simulator/auth/session_store.py`: xác nhận đã loại bỏ hoàn toàn fallback cookie `sh_session_tier` và xóa `synthesize_legacy_session`.
   - `simulator/api/routes_auth.py`: xác nhận không ghi cookie unauthenticated/insecure `sh_session_tier` và `sh_session_user`.
   - `tests/test_p3_session_rbac_concurrency.py`: xác nhận bài test `test_unsigned_cookie_tampering_ignored_and_defaults_to_tier3` kiểm thử đúng logic.
3. Chạy kiểm thử xác thực:
   - PoC: `python -c "from fastapi.testclient import TestClient; from simulator.server import app; c = TestClient(app); r = c.post('/api/device', json={'device_id': 'main_door', 'action': 'open'}, cookies={'sh_session_tier': '1'}); assert r.status_code == 403, f'VULNERABLE: {r.status_code} {r.json()}'; print('SECURE')"`
   - Pytest suite: `python -X utf8 -m pytest tests/test_p3_session_rbac_concurrency.py tests/test_p3_challenger_m12_adversarial.py tests/test_phase1_bugfixes_20261104.py tests/test_challenger_m4_security.py --basetemp=.pytest_tmp` (phải PASS 100%, dọn dẹp sạch `.pytest_tmp` sau khi chạy).
4. Kiểm tra mã hóa UTF-8 không BOM, 0 CRLF.
5. Ghi báo cáo `handoff.md` với phán quyết rõ ràng: `VERDICT: APPROVE` hoặc `VERDICT: REQUEST_CHANGES`. Gửi thông điệp hoàn thành về cho Orchestrator qua `send_message`.
