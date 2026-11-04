# Task: Worker Milestone 3 - Mobile App, UI Layout, 3D & Logs Usability (Bugs 6, 7, 8, 9, 12, 13)

## Objectives
1. Read Explorer 3's detailed handoff: `.agents/teamwork/teamwork_explorer_survey_3/handoff.md`.
2. Follow strict TDD:
   a. Write automated reproduction test `tests/test_p4_survey3_ui_layout.py` covering Bugs 6, 7, 8, 9, 12, 13.
   b. Run `python -X utf8 -m pytest tests/test_p4_survey3_ui_layout.py --basetemp=.pytest_tmp` and confirm FAIL before fix.
   c. Implement fixes:
      - Bug 6: In `mobile_app/index.html`, load `/static/vendor/three.min.js`, `/static/vendor/GLTFLoader.js`, and `/static/house3d.js`. In `simulator/static/js/mobile_app.js`, call `SmartHome3D.init("mobileOverviewBox", null, ...)` and sync `SmartHome3D.updateDevices` / `updateSensors` on render. Keep `#mobileOverviewBox` and class `preview-16-9`.
      - Bug 7: In `simulator/static/js/mobile_app.js` line 21, set `let showAllDevices = true;` so that `#devGrid` displays all 7 devices like desktop.
      - Bug 8: In `mobile_app/index.html` line 391, remove "Mỗi tab mở một màn riêng, không cuộn tới mục khác.". In `simulator/static/css/mobile_app.css` and `#tabViewAccount`, add padding-bottom $\ge 48\text{px}$ + safe-area for Samsung Internet toolbar and bottom nav. Format `#mobileQrCountdown` to `Đổi mã sau ${rem}s`.
      - Bug 9: In `simulator/static/index.html`, add compact `<section class="panel sensors" id="secSensors">` displaying indoor temp, humidity, and garden soil moisture. In `simulator/static/js/app.js`, implement clamp logic for temp [0, 60]°C, humidity [0, 100]%, soil [0, 100]%.
      - Bug 12: In `simulator/static/js/mobile_app.js` line 691 (`openQrScanner()`), remove `status.textContent = 'Đưa mã QR vào trong khung để quét'` to avoid duplicate instruction with `p.instruction`.
      - Bug 13: In `simulator/static/logs.html` and `simulator/static/js/logs.js`, implement client-side pagination (`pageSize = 20`) with pagination controls / load more button, and enable date range filtering (`#logDateRange`).
   d. Re-run `tests/test_p4_survey3_ui_layout.py` and confirm all tests PASS.
   e. Run full regression test suites (`test_p4_survey1_security_auth.py`, `test_p4_survey2_realtime.py`, `test_challenger_m4_dom.py`, `test_m8_mobile_screens.py`).
   f. Clean up `.pytest_tmp`.
3. Preserve all 68 DOM IDs, window hooks, 0 CRLF, UTF-8 LF, zero secrets logged.
4. Report results in `handoff.md`.
