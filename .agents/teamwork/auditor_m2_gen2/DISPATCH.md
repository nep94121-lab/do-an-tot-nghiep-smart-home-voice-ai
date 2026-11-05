## 2026-11-05T06:03:57Z
Bạn là Forensic Auditor độc lập (auditor_m2_gen2, role teamwork_auditor) thuộc đội Teamwork Phase 7 UI Overhaul.
Thư mục làm việc của bạn: C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\auditor_m2_gen2\
Mã hội thoại Parent: e7340628-f79a-4027-966a-f5d6b40bf426

Nhiệm vụ: Giám định pháp y tính toàn vẹn (Forensic Integrity Audit) đối với Milestone 2 (Phase 7 UI Overhaul Core: R1, R2, R3, R4).
Đọc kỹ các tài liệu sau trước khi thẩm định:
- C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\ORIGINAL_REQUEST.md
- C:\Users\LENOVO\datn-wt\ui\PROJECT.md
- C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\worker_m2_gen2\handoff.md
- C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\auditor_m1_1\handoff.md (tham khảo chuẩn báo cáo kiểm định pháp y)

Nhiệm vụ cụ thể:
1. Kiểm tra tính chân thực và phòng chống gian lận (Anti-Cheat & Authenticity):
   - Quét mã nguồn trong `simulator/static/index.html`, `simulator/static/css/style.css`, `simulator/static/house3d.js`, `mobile_app/index.html`, `simulator/static/js/mobile_app.js`, `simulator/static/auth.html`, `simulator/static/js/auth.js`.
   - Xác minh KHÔNG CÓ hardcode kết quả test, dummy/facade data, hay ngụy tạo số liệu đo đạc Playwright.
   - Xác minh thuật toán kẹp viền (`Math.max(pad+halfW, Math.min(w-pad-halfW, rawX))`) và va chạm 3 chu kỳ trong `house3d.js` là thuật toán toán học thực chất.
   - Xác minh cơ chế `pendingDeviceMutations` (Map, 2500ms) và In-Place DOM update trong `mobile_app.js` là logic thực chất, có rollback khi lỗi.
   - Xác minh script đo độ trễ `tests/benchmark_optimistic_latency.py` chạy Playwright trên trình duyệt thật (Chrome/Chromium), không ngụy tạo kết quả 1.14ms.
2. Kiểm tra bất biến hệ thống:
   - Ranh giới tệp cấm: `git status --porcelain simulator/voice/ simulator/voice_auth.py simulator/live/` phải trả về 0 thay đổi.
   - Purity HTML: 0 thẻ `<style>`, 0 thẻ `<script>` inline không có `src` trên toàn bộ 8 tệp HTML (`index.html`, `auth.html`, `wokwi.html`, `logs.html`, `guest_enroll.html`, `login.html`, `register.html`, `mobile_app/index.html`).
   - Định dạng ký tự: 100% POSIX LF (0 CRLF `\r\n`) và UTF-8 no BOM.
3. Chạy kiểm thử độc lập:
   - Chạy Pytest: `python -m pytest --basetemp=.pytest_tmp -q tests/test_milestone_m1_navigation_routing.py tests/test_phase5_r4_house3d_overlay.py tests/test_challenger_m3_stress_dom_raycaster.py tests/test_challenger_m4_dom.py tests/test_challenger_m2_gate_ux_empirical.py tests/test_p4_survey1_security_auth.py tests/test_p4_survey3_ui_layout.py`
   - Chạy script đo độ trễ: `python tests/benchmark_optimistic_latency.py`
4. Viết báo cáo kiểm định pháp y tại:
   `C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\auditor_m2_gen2\handoff.md` theo chuẩn Handoff Protocol (Observation, Logic Chain, Caveats, Conclusion, Verification Method).
   Phán quyết (Verdict): CLEAN hoặc INTEGRITY VIOLATION.
5. Gửi tin nhắn kết quả về cho Parent qua `send_message(Recipient="e7340628-f79a-4027-966a-f5d6b40bf426", Message=...)`.
