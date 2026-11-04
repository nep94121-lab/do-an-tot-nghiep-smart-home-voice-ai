## 2026-11-04T16:09:51Z
You are teamwork_worker assigned to Milestone M12 Iteration 2 (Remediation of Privilege Escalation Vulnerability).

## Mandatory Reading
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md.
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\challenger_m12_1\handoff.md (contains exact vulnerability PoC and reproduction commands).

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Vulnerability to Remediate
`challenger_m12_1` reported a CRITICAL privilege escalation vulnerability (CWE-565 / CWE-287):
In `simulator/auth/session_store.py` (lines 286–295), `resolve_request_session` accepted an unsigned legacy cookie `sh_session_tier`. An attacker could send `Cookie: sh_session_tier=1` without logging in, opening the front door and creating schedules as Admin.

## Detailed Tasks
1. In `simulator/auth/session_store.py`:
   - Remove lines 286–295 (the fallback to unsigned cookie `sh_session_tier`).
   - Require that session resolution ONLY authenticates callers with cryptographically secure random `session_token` (from `Authorization: Bearer <token>`, `X-Session-Token: <token>`, or cookie `sh_session_token=<token>`).
   - If an unauthenticated request sends `Cookie: sh_session_tier=1`, it must be ignored completely and fall back to anonymous Tier 3 (Guest).
2. In `tests/test_p3_session_rbac_concurrency.py`:
   - Verify that test assertions align with this secure behavior.
3. Test Verification:
   - Run: `python -X utf8 -m pytest tests/test_p3_session_rbac_concurrency.py tests/test_p3_challenger_m12_adversarial.py tests/test_phase1_bugfixes_20261104.py tests/test_challenger_m4_security.py --basetemp=.pytest_tmp`.
   - All tests must pass 100%!
   - Clean up `.pytest_tmp` after running.
   - Verify 0 CRLF and UTF-8 no BOM.
4. Deliver handoff report at:
   `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m12_iter2\handoff.md`.
Send a completion message back when done.
