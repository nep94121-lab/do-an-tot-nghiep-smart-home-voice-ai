## 2026-11-04T15:55:39Z
You are teamwork_challenger assigned to adversarially challenge Milestone M12: Session-based RBAC Security & Concurrent Session Tests (Requirement R2).

## Mandatory Reading
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md.
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m12\handoff.md.

## Working Directory
C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\challenger_m12_1\

## Challenge Scope
- Adversarially stress-test session-based RBAC concurrency:
  - Run the concurrency test suite: `python -X utf8 -m pytest tests/test_p3_session_rbac_concurrency.py -v --basetemp=.pytest_tmp`.
  - Write an independent stress script with high concurrency (simulate race conditions: e.g. Guest hammering door unlock requests while Owner sends living room light commands, ensure Guest is ALWAYS blocked with 403 and Owner is NEVER blocked).
  - Test edge cases: invalid tokens, expired tokens, malformed headers, cookie tampering.
- Clean up `.pytest_tmp` after running tests.
- Explicitly state your verdict in `handoff.md`: APPROVE or REJECT.
Send a completion message back when done.
