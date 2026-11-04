## 2026-11-04T21:16:38Z
You are teamwork_worker_m3.
Your working directory is: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_worker_m3\
Project root: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY FIRST STEP:
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\orchestrator_phase4\PROJECT.md
Read the detailed survey report from Explorer 3:
C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_explorer_survey_3\handoff.md

Your mission is Milestone 3 (Bugs 6, 7, 8, 9, 12, 13 from REAL_TEST_BUGS_20261105.md):
- Bug 6: /app 3D collapse render: in mobile_app/index.html, include /static/vendor/three.min.js, /static/vendor/GLTFLoader.js, and /static/house3d.js. In simulator/static/js/mobile_app.js, initialize SmartHome3D.init("mobileOverviewBox", null, ...) and call updateDevices and updateSensors in renderState. Keep DOM ID #mobileOverviewBox and class preview-16-9.
- Bug 7: /app Devices tab show all 7 devices: in simulator/static/js/mobile_app.js line 21, set showAllDevices = true (or remove 4-device truncation in tabDevices), so that #devGrid renders all 7 devices (main_door, living_room_light, bedroom_light, fan, ac, alarm_siren, garden_pump) like desktop.
- Bug 8: /app Profile tab safe-area and countdown: in mobile_app/index.html line 391, delete "Mỗi tab mở một màn riêng, không cuộn tới mục khác.". In simulator/static/css/mobile_app.css and #tabViewAccount, add safe-area padding-bottom for Samsung Internet bottom toolbar and bottom-nav so #mobileBtnLogout is never obscured. In mobile_app.js line 1348, format #mobileQrCountdown to "Đổi mã sau ${rem}s" (or clear refresh countdown label).
- Bug 9: Desktop / sensor panel: in simulator/static/index.html, add <section class="panel sensors" id="secSensors"> with temp, humidity, and soil moisture meters. In simulator/static/js/app.js lines 461-471, update sensor values and clamp temp [0, 60]°C, humidity [0, 100]%, soil [0, 100]%.
- Bug 12: QR scanner duplicate text: in simulator/static/js/mobile_app.js line 691 (openQrScanner()), remove status.textContent = 'Đưa mã QR vào trong khung để quét'; so it does not duplicate with p.instruction.
- Bug 13: /logs pagination and filter: in simulator/static/logs.html and simulator/static/js/logs.js, implement client-side pagination (pageSize = 20) with pagination controls or load more button (#btnLogsLoadMore, #logsPaginationInfo), connect #logDateRange filter, and ensure sensitive password suggestions are masked in log detail.

Strict TDD Cycle:
1. Write automated reproduction test suite: tests/test_p4_survey3_ui_layout.py covering Bugs 6, 7, 8, 9, 12, 13.
2. Execute: python -X utf8 -m pytest tests/test_p4_survey3_ui_layout.py --basetemp=.pytest_tmp and record evidence that tests FAIL before fix.
3. Implement genuine code fixes in owned files:
   - mobile_app/index.html
   - simulator/static/js/mobile_app.js
   - simulator/static/css/mobile_app.css
   - simulator/static/index.html
   - simulator/static/js/app.js
   - simulator/static/logs.html
   - simulator/static/js/logs.js
4. Execute: python -X utf8 -m pytest tests/test_p4_survey3_ui_layout.py --basetemp=.pytest_tmp and verify all tests PASS.
5. Regression test: python -X utf8 -m pytest tests/test_p4_survey1_security_auth.py tests/test_p4_survey2_realtime.py tests/test_challenger_m4_dom.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp.
6. Clean up .pytest_tmp.
7. Constraints: preserve all 68 DOM IDs, window hooks, re-exports, the 3D model house3d.js, zero secrets logged, UTF-8 LF (0 CRLF).
8. Write comprehensive handoff to C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_worker_m3\handoff.md and send message to caller.
