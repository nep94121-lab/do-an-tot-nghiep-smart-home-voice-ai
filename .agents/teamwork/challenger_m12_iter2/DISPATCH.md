## 2026-11-04T16:21:22Z
Bạn là `challenger_m12_iter2` (teamwork_challenger) thuộc đội ngũ phát triển Phase 3 Smart Home Voice AI.
Thư mục làm việc của bạn: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\challenger_m12_iter2\
Tệp yêu cầu gốc: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md

Nhiệm vụ:
Kiểm thử đối kháng thực nghiệm (Empirical Adversarial Verification) cho Milestone M12 Iteration 2:
1. Đọc tệp báo cáo bàn giao: `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m12_iter2\handoff.md` và báo cáo từ chối trước đó tại `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\challenger_m12_1\handoff.md`.
2. Kiểm tra PoC đối kháng tấn công giả mạo cookie:
   `python -c "from fastapi.testclient import TestClient; from simulator.server import app; c = TestClient(app); r = c.post('/api/device', json={'device_id': 'main_door', 'action': 'open'}, cookies={'sh_session_tier': '1'}); assert r.status_code == 403, f'VULNERABLE: {r.status_code} {r.json()}'; print('SECURE')"`
3. Chạy các bài test đối kháng trong `tests/test_p3_challenger_m12_adversarial.py` và `tests/test_p3_session_rbac_concurrency.py`:
   `python -X utf8 -m pytest tests/test_p3_session_rbac_concurrency.py tests/test_p3_challenger_m12_adversarial.py tests/test_phase1_bugfixes_20261104.py tests/test_challenger_m4_security.py --basetemp=.pytest_tmp`
   Xóa sạch `.pytest_tmp` sau khi kiểm tra.
4. Thử nghiệm thêm các biến thể đối kháng khác:
   - Gửi cookie giả mạo `sh_session_tier=0` (Owner tier), `sh_session_tier=1`, `sh_session_tier=2`, `sh_session_user=admin` tới `/api/device`, `/api/devices`, `/api/settings` mà không có token hợp lệ.
   - Xác nhận tất cả đều bị chặn HTTP 403 Forbidden hoặc rơi về Tầng 3.
5. Ghi báo cáo chi tiết `handoff.md` với phán quyết rõ ràng: `VERDICT: APPROVE` hoặc `VERDICT: REJECT`. Báo cáo lại cho Orchestrator qua `send_message`.
