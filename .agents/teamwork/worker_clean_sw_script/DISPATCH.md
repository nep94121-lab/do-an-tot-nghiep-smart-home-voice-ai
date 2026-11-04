## 2026-11-04T13:53:26Z
You are worker_clean_sw_script. Your working directory is C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_clean_sw_script.
You MUST read:
1. C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md
2. C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\auditor_p2\handoff.md
3. C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\qa_tester_p2\handoff.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Scope & Task:
Both the Forensic Auditor and QA Tester identified an architectural cleanliness violation in `simulator/static/index.html`:
Lines 441-446 contain an inline `<script>` block that registers the Service Worker:
```html
<script>
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch(console.error);
    });
  }
</script>
```
This violates the zero-inline-scripts rule in `tests/test_challenger_m4_security.py` line 445 (`test_html_files_cleanliness_zero_inline_styles_and_scripts`).

Your task:
1. Remove the inline `<script>` block from `simulator/static/index.html`.
2. Move the Service Worker registration code cleanly into `simulator/static/js/app.js` (e.g. inside the window load or init lifecycle).
3. Ensure both `simulator/static/index.html` and `simulator/static/js/app.js` maintain 0 CRLF (POSIX LF) and UTF-8 without BOM.
4. Run verification tests:
   `python -X utf8 -m pytest tests/test_challenger_m4_security.py --basetemp=.pytest_tmp -v`
   `python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_m6_web_error_sw.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py tests/test_qa_p2_live_user_flows.py --basetemp=.pytest_tmp`
5. Write your handoff report to C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_clean_sw_script\handoff.md with passing test evidence and send a message back when done.
