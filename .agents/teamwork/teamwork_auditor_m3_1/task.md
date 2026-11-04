# Task: Forensic Auditor - Milestone 3 Integrity Audit
Role: teamwork_auditor
Scope: Forensic integrity audit of Milestone 3:
1. Verify genuine implementations (no facades, no fake 3D placeholders, no dummy pagination).
2. Verify 0 CRLF (POSIX LF) across all modified files and simulator/data/*.
3. Verify 68 DOM IDs and 25 window hooks intact.
4. Execute full test suite: `python -X utf8 -m pytest tests/test_p4_survey3_ui_layout.py tests/test_p4_survey2_realtime.py tests/test_p4_survey1_security_auth.py tests/test_challenger_m4_dom.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp`.
5. Re-check 0 CRLF invariance after running pytest on Windows.
6. Provide verdict: CLEAN or INTEGRITY VIOLATION.
