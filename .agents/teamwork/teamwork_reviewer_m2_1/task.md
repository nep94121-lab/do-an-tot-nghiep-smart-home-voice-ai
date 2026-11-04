# Task: Reviewer - Milestone 2 Verification (Realtime & Simulation)
Role: teamwork_reviewer
Scope: Review code changes in Milestone 2 (Bugs 3, 10, 11, 14):
1. Review `simulator/static/js/app.js`, `simulator/static/js/mobile_app.js`, `mobile_app/index.html`, `simulator/static/wokwi.html`, `simulator/static/js/wokwi.js`, `simulator/static/favicon.ico`, `vercel.json`.
2. Verify WebSocket fallback, banner consistency, optimistic UI, mic permission waiting state & modal, Wokwi label layout & telemetry.
3. Execute test suite: `python -X utf8 -m pytest tests/test_p4_survey2_realtime.py tests/test_challenger_m4_dom.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp`.
4. Verify 68 DOM IDs, window hooks, 0 CRLF.
5. Provide verdict: APPROVE or REQUEST_CHANGES.
