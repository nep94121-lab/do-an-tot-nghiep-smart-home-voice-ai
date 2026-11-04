## 2026-11-04T13:08:45Z
You are worker_m7. Your working directory is C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m7.
You MUST read:
1. C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md
2. C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\spec_miner_web_p2\survey_report.md
3. C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\PROJECT.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Scope & Tasks for Milestone M7:
Implement the security modals and banner in `simulator/static/index.html`, `simulator/static/js/app.js`, and `simulator/static/css/style.css`:
1. Security Lockdown Modal (`#securityLockdownModal`):
   - Design matches `ui_mockups/v2_new_pages/np_06_lockdown.html`.
   - Role `alertdialog`, aria-modal `true`. Red alert theme with Lucide `shield-alert`.
   - Triggered when voice authentication strike count reaches 3 (`unauthorized_strikes >= 3`) or via security lockdown trigger.
   - Strictly NO 'X' close button and backdrop click disabled.
   - Unlock form: Password / Gmail OTP input with eye toggle and Enter key support, calling `/api/auth3/layer1_login` or OTP verification, and resetting strikes.
2. Microphone Permission Modal (`#micPermissionModal`):
   - Design matches `ui_mockups/v2_new_pages/np_07_mic_permission.html`.
   - Role `dialog`, aria-modal `true`. Lucide `mic-off` icon.
   - Triggered when microphone access fails (`getUserMedia` catch block) or when insecure context (`!window.isSecureContext`).
   - Includes 'Thử lại' button, 'Mở bản HTTPS' link (if on HTTP), and 'Đóng' button.
3. WebSocket Reconnect Banner (`#wsReconnectBanner`):
   - Design matches `ui_mockups/v2_new_pages/np_08_ws_banner.html`.
   - Role `status`, aria-live `polite`. Amber warning bar fixed at top of screen.
   - Shows: 'Mất kết nối thời gian thực tới ngôi nhà. Đang kết nối lại (lần X/5)…'
   - Button 'Kết nối ngay' calling `window.retryWsConnection()`.
   - When connection is restored: turns green 'Đã khôi phục kết nối thời gian thực', stays for 2 seconds, then smoothly slides out.
4. Backward Compatibility & DOM Integrity:
   - Preserve 100% of all existing DOM IDs and `window.*` hooks in `simulator/static/index.html` and `simulator/static/js/app.js`.
   - Do NOT touch or alter `house3d.js` or the 3D viewport canvas/labels!
5. Verification:
   - Run `python -X utf8 -m pytest tests/test_challenger_m4_dom.py --basetemp=.pytest_tmp` (MUST pass 36/36)
   - Run `python -X utf8 -m pytest tests/test_challenger_m3_stress_dom_raycaster.py --basetemp=.pytest_tmp` (MUST pass 20/20)
   - Write a dedicated test file `tests/test_m7_security_modals_banner.py` testing the presence of all modal/banner elements, triggers, and classes.
   - Run `python -X utf8 -m pytest tests/test_m7_security_modals_banner.py --basetemp=.pytest_tmp`
6. Write full handoff report to C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m7\handoff.md with passing build/test evidence and send a message back when done.
