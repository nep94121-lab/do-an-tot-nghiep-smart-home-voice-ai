# Task: Forensic Auditor - Milestone 2 Integrity Audit
Role: teamwork_auditor
Scope: Forensic integrity audit of Milestone 2:
1. Verify genuine implementations (no facades, no fake timers, no hardcoded test responses).
2. Verify favicon.ico is a genuine valid binary ICO file.
3. Verify 0 CRLF (POSIX LF) across all modified files and simulator/data/*.
4. Verify 68 DOM IDs and 25 window hooks intact.
5. Execute full test suite: `python -X utf8 -m pytest tests/test_p4_survey2_realtime.py tests/test_p4_survey1_security_auth.py tests/test_challenger_m4_dom.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp`.
6. Provide verdict: CLEAN or INTEGRITY VIOLATION.
