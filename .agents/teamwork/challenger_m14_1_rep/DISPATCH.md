## 2026-11-04T17:11:06Z
Bạn là `challenger_m14_1_rep` (teamwork_challenger) phụ trách kiểm thử đối kháng thực nghiệm các bất biến cho Milestone M14: Tái cấu trúc mô-đun hóa Ponytail (Requirement R4).

Thư mục làm việc: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\challenger_m14_1_rep\
Tệp yêu cầu gốc: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md
Tệp bàn giao của Worker: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m14\handoff.md

Nhiệm vụ trọng tâm (Adversarial Verification of Invariants):
1. Đọc `worker_m14/handoff.md` và `ORIGINAL_REQUEST.md`.
2. Kiểm tra bất biến 100%:
   - `simulator/static/house3d.js`: Xác nhận `git diff simulator/static/house3d.js` rỗng (0 lần sửa đổi, 3D concept và v1 light design nguyên vẹn).
   - `ui_mockups/`: Xác nhận không tệp nào bị xóa hay thay đổi (`git status ui_mockups/`).
   - Kiểm tra 68 DOM IDs trong `mobile_app/index.html`.
   - Kiểm tra 25 Window hooks trong `simulator/static/js/mobile_app.js`.
   - Kiểm tra 13 Window hooks và text anchors trong `simulator/static/js/app.js`:
     `function initCameraToolbar()`, `initCameraToolbar();`, `SmartHome3D.init('house3dViewport', 'house3dLabels', toggleDeviceById)`, `strike_count >= 3`, `isSecureContext`, `NotAllowedError`, `showWsRestoredBanner`.
3. Chạy các bài test đối kháng Node VM:
   `python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_challenger_m4_security.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py tests/test_challenger_m3_stress_dom_raycaster.py tests/test_challenger_m5_interactions.py --basetemp=.pytest_tmp`
   (Phải PASS 100%, dọn dẹp sạch `.pytest_tmp`).
4. Kiểm tra cú pháp JavaScript:
   `node --check simulator/static/app.js`
   `node --check simulator/static/js/app.js`
   `node --check simulator/static/js/mobile_app.js`
   `node --check simulator/static/house3d.js`
5. Ghi báo cáo chi tiết vào `handoff.md` với phán quyết rõ ràng: `VERDICT: APPROVE` hoặc `VERDICT: REJECT`. Báo cáo lại cho Orchestrator qua `send_message`.
