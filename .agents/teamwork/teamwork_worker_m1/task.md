# Task: Worker Milestone 1 - Security, Auth & Session Lifecycle (Bugs 1, 2, 4, 5, 15)

## Objectives
1. Read Explorer 1's detailed handoff: `.agents/teamwork/teamwork_explorer_survey_1/handoff.md`.
2. Follow strict TDD:
   a. Write automated reproduction test `tests/test_p4_survey1_security_auth.py` covering Bugs 1, 2, 4, 5, 15.
   b. Run `python -X utf8 -m pytest tests/test_p4_survey1_security_auth.py --basetemp=.pytest_tmp` and confirm FAIL.
   c. Implement fixes for Bugs 1, 2, 4, 5, 15.
   d. Re-run pytest and confirm PASS.
   e. Clean up `.pytest_tmp`.
3. Preserve all 68 DOM IDs, window hooks, zero secret leaks, UTF-8 LF (0 CRLF).
4. Report results in `handoff.md`.
