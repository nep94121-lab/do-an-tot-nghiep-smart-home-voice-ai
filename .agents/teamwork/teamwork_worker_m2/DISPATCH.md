## 2026-11-04T20:42:21Z
You are teamwork_worker_m2.
Your working directory is: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_worker_m2\
Project root: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY FIRST STEP:
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\orchestrator_phase4\PROJECT.md
Read the detailed survey report from Explorer 2:
C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_explorer_survey_2\handoff.md

Your mission is Milestone 2 (Bugs 3, 10, 11, 14 from REAL_TEST_BUGS_20261105.md):
- Bug 3: WebSocket fallback on Vercel: in simulator/static/js/app.js (lines 811-841) and mobile_app.js, when HTTP polling /api/state succeeds, call hideWsReconnectBanner(), sync header connection pill to "Đã kết nối". Only show reconnect banner if both WS and polling fail. Add route /favicon.ico in vercel.json and ensure simulator/static/favicon.ico exists on disk.
- Bug 10: Toggle device slow: implement Optimistic UI for toggleDeviceById() in app.js and mobile_app.js (immediately flip toggle, update badge/counters, rollback on error). In renderDevices(), update DOM elements in-place instead of innerHTML = "". In getDeviceRoomLabel(), provide full subtitle ("Đã bật" / "Đã tắt") without truncation/typo.
- Bug 11: Recording sheet mic waiting state: in mobile_app/index.html (line 597) and mobile_app.js (lines 559, 602-628), set initial title to "Đang chờ quyền mic", keep timer at 00:00 and volume bars frozen until navigator.mediaDevices.getUserMedia resolves. If denied/rejected, close sheet and display #mobileMicPermissionModal (add this modal in mobile_app/index.html matching desktop #micPermissionModal).
- Bug 14: /wokwi label layout and telemetry: in simulator/static/wokwi.html (lines 58, 163-175), adjust .comp-tag layout to eliminate overlap between DHT11 (left: 500px) and Buzzer (left: 632px) (e.g. adjust left or top so no tags overlap). In simulator/static/js/wokwi.js and wokwi.html, replace "Chưa có dữ liệu" with live simulation telemetry (temp, humidity, soil moisture).

Strict TDD Cycle:
1. Write automated reproduction test suite: tests/test_p4_survey2_realtime.py covering Bugs 3, 10, 11, 14.
2. Execute: python -X utf8 -m pytest tests/test_p4_survey2_realtime.py --basetemp=.pytest_tmp and record evidence that tests FAIL before fix.
3. Implement genuine code fixes in owned files:
   - simulator/static/js/app.js
   - simulator/static/js/mobile_app.js
   - mobile_app/index.html
   - simulator/static/wokwi.html
   - simulator/static/js/wokwi.js
   - simulator/static/favicon.ico
   - vercel.json
4. Execute: python -X utf8 -m pytest tests/test_p4_survey2_realtime.py --basetemp=.pytest_tmp and verify all tests PASS.
5. Regression test: python -X utf8 -m pytest tests/test_p4_survey1_security_auth.py tests/test_challenger_m4_dom.py tests/test_m3_challenger_api.py --basetemp=.pytest_tmp.
6. Clean up .pytest_tmp.
7. Constraints: preserve all 68 DOM IDs, window hooks, re-exports, zero secrets logged, UTF-8 LF (0 CRLF).
8. Write comprehensive handoff to C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_worker_m2\handoff.md and send message to caller.
