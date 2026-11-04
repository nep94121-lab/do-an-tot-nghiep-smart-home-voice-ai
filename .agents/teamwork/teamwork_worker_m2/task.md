# Task: Worker Milestone 2 - Realtime, State Synchronization & Simulation (Bugs 3, 10, 11, 14)

## Objectives
1. Read Explorer 2's detailed handoff: `.agents/teamwork/teamwork_explorer_survey_2/handoff.md`.
2. Follow strict TDD:
   a. Write automated reproduction test `tests/test_p4_survey2_realtime.py` covering Bugs 3, 10, 11, 14.
   b. Run `python -X utf8 -m pytest tests/test_p4_survey2_realtime.py --basetemp=.pytest_tmp` and confirm FAIL before fix.
   c. Implement fixes:
      - Bug 3: In `simulator/static/js/app.js` and `mobile_app.js`, when HTTP polling `/api/state` succeeds, call `hideWsReconnectBanner()` and update `#connText` to "Đã kết nối". Create `simulator/static/favicon.ico` and add route `/favicon.ico` in `vercel.json` before catch-all 404.
      - Bug 10: Implement Optimistic UI for `toggleDeviceById()` in `simulator/static/js/app.js` and `mobile_app.js`. Update DOM in-place without `innerHTML = ""`. Fix subtitle to full text ("Đã bật" / "Đã tắt").
      - Bug 11: In `mobile_app/index.html` and `mobile_app.js`, set initial title of voice sheet to "Đang chờ quyền mic", keep timer at 00:00 and waveform frozen until `getUserMedia` resolves. Add `#mobileMicPermissionModal` in `mobile_app/index.html` and open it if mic is denied.
      - Bug 14: In `simulator/static/wokwi.html`, adjust `.comp-tag` layout to eliminate overlap between DHT11 and Buzzer. In `simulator/static/js/wokwi.js` and `wokwi.html`, replace "Chưa có dữ liệu" with live telemetry.
   d. Re-run `tests/test_p4_survey2_realtime.py` and confirm all tests PASS.
   e. Run regression test suites (`test_p4_survey1_security_auth.py`, `test_challenger_m4_dom.py`, etc.).
   f. Clean up `.pytest_tmp`.
3. Preserve all 68 DOM IDs, window hooks, 0 CRLF, UTF-8.
4. Report results in `handoff.md`.
