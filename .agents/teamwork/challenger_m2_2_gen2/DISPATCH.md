## 2026-11-05T06:03:55Z
Bạn là Challenger độc lập (challenger_m2_2_gen2, role teamwork_challenger) thuộc đội Teamwork Phase 7 UI Overhaul.
Thư mục làm việc của bạn: C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\challenger_m2_2_gen2\
Mã hội thoại Parent: e7340628-f79a-4027-966a-f5d6b40bf426

Nhiệm vụ: Thẩm định thực nghiệm đối kháng (Adversarial Stress Testing) Milestone 2 (Phase 7 UI Overhaul Core: R1, R2, R3, R4).
Đọc kỹ các tài liệu sau trước khi thực hiện:
- C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\ORIGINAL_REQUEST.md
- C:\Users\LENOVO\datn-wt\ui\PROJECT.md
- C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\worker_m2_gen2\handoff.md

Nhiệm vụ cụ thể:
1. Soạn và chạy kịch bản kiểm thử đối kháng thực nghiệm:
   - Stress test 3D boundary clamping và collision repulsion trên các màn hình cực hẹp (360px, 375px, 390px, 412px, 430px), kiểm tra không chip nào bị tràn ra ngoài hoặc đè trùng tọa độ.
   - Stress test Optimistic UI toggling: gửi toggle liên tiếp, mô phỏng network delay và snapshot polling từ server trong cửa sổ 2500ms `pendingDeviceMutations`, đo thời gian cập nhật DOM < 16ms và cơ chế rollback.
   - Stress test Login Gate: kiểm tra không thể bypass bằng Escape key, click backdrop, hoặc script injection khi chưa có session, kiểm tra 2 text links và empty static `value=""`.
   - Stress test Voice Auth: kiểm tra Step 1 chỉ có 3 trường hiển thị, password ẩn có fallback '123456'.
2. Chạy toàn bộ test suites hiện có:
   `python -m pytest --basetemp=.pytest_tmp -q tests/test_milestone_m1_navigation_routing.py tests/test_phase5_r4_house3d_overlay.py tests/test_challenger_m3_stress_dom_raycaster.py tests/test_challenger_m4_dom.py tests/test_challenger_m2_gate_ux_empirical.py tests/test_p4_survey1_security_auth.py tests/test_p4_survey3_ui_layout.py`
   Và `python tests/benchmark_optimistic_latency.py`.
3. Kiểm tra các bất biến bảo mật & kỹ thuật: 0 CRLF, 0 `<style>`, 0 script inline, 0 thay đổi tệp voice backend.
4. Viết báo cáo thực nghiệm đối kháng tại:
   `C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\challenger_m2_2_gen2\handoff.md` theo chuẩn Handoff Protocol (Observation, Logic Chain, Caveats, Conclusion, Verification Method).
   Phán quyết (Verdict): APPROVE hoặc REJECT.
5. Gửi tin nhắn kết quả về cho Parent qua `send_message(Recipient="e7340628-f79a-4027-966a-f5d6b40bf426", Message=...)`.
