## 2026-11-05T06:03:52Z
Bạn là Reviewer độc lập (reviewer_m2_2_gen2, role teamwork_reviewer) thuộc đội Teamwork Phase 7 UI Overhaul.
Thư mục làm việc của bạn: C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\reviewer_m2_2_gen2\
Mã hội thoại Parent: e7340628-f79a-4027-966a-f5d6b40bf426

Nhiệm vụ: Thẩm định độc lập mã nguồn và kiểm thử Milestone 2 (Phase 7 UI Overhaul Core: R1, R2, R3, R4).
Đọc kỹ các tài liệu sau trước khi thẩm định:
- C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\ORIGINAL_REQUEST.md
- C:\Users\LENOVO\datn-wt\ui\PROJECT.md
- C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\worker_m2_gen2\handoff.md
- C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\reviewer_m1_1\handoff.md (tham khảo tiêu chuẩn review)

Nhiệm vụ cụ thể:
1. Thẩm định các tệp mã nguồn Milestone 2:
   - `simulator/static/index.html` và `simulator/static/css/style.css`:
     + R1 Login Gate: Legacy tabs bọc trong hidden container (`style="display:none;" hidden`), chỉ hiển thị email, password, toggle xem mk, 2 text link "Quên mật khẩu?" (/login) và "Đăng ký" (/register), nút login. DOM IDs và static empty `value=""` giữ nguyên. Nút đóng có static `hidden`.
     + R2 Header: `.top` chia 2 hàng (.top-row-main và .top-row-account). `#homeCurrentAccountBadge` max-width 165px, ellipsis.
   - `simulator/static/house3d.js`:
     + Boundary clamping (`[pad + halfW, w - pad - halfW]`), 3-pass collision relaxation, compact typography trên mobile (`w < 500`).
     + Invariant strings: `hasValue`, `stSpan`, `pin-state`.
   - `mobile_app/index.html` và `simulator/static/js/mobile_app.js`:
     + R3 Optimistic UI: Map `pendingDeviceMutations`, guard window 2500ms, In-Place DOM update theo `[data-device-id="${d.id}"]`, không `grid.innerHTML = ''`, rollback on error.
   - `simulator/static/auth.html` và `simulator/static/js/auth.js`:
     + R4 Streamlined: Step 1 hiển thị đúng 3 trường (tier, speaker name, email). Password ẩn với default fallback '123456'.
2. Chạy kiểm thử tự động độc lập:
   - Pytest suite: `python -m pytest --basetemp=.pytest_tmp -q tests/test_milestone_m1_navigation_routing.py tests/test_phase5_r4_house3d_overlay.py tests/test_challenger_m3_stress_dom_raycaster.py tests/test_challenger_m4_dom.py tests/test_challenger_m2_gate_ux_empirical.py tests/test_p4_survey1_security_auth.py tests/test_p4_survey3_ui_layout.py`
   - Playwright latency script: `python tests/benchmark_optimistic_latency.py` (xác nhận <16ms).
   - Kiểm tra invariants: 0 CRLF (100% POSIX LF), 0 thẻ `<style>`, 0 script inline không có src, 0 sửa đổi `simulator/voice/**`, `simulator/voice_auth.py`, `simulator/live/**`.
3. Viết báo cáo bàn giao độc lập đầy đủ tại:
   `C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\reviewer_m2_2_gen2\handoff.md` theo chuẩn Handoff Protocol (Observation, Logic Chain, Caveats, Conclusion, Verification Method).
   Phán quyết cuối cùng (Verdict): APPROVE hoặc REQUEST_CHANGES.
4. Gửi tin nhắn kết quả về cho Parent qua `send_message(Recipient="e7340628-f79a-4027-966a-f5d6b40bf426", Message=...)`.
