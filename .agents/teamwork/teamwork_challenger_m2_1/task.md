# Task: Challenger - Milestone 2 Empirical Verification
Role: teamwork_challenger
Scope: Empirically challenge Milestone 2 changes (Bugs 3, 10, 11, 14):
1. Stress test WebSocket fallback & banner state synchronization.
2. Stress test optimistic UI and rollback under error conditions.
3. Verify mic permission waiting state & `#mobileMicPermissionModal` opening on rejection.
4. Verify Wokwi label coordinates to ensure 0 geometric overlap between DHT11 and Buzzer.
5. Run test suite: `python -X utf8 -m pytest tests/test_p4_survey2_realtime.py --basetemp=.pytest_tmp`.
6. Provide verdict: APPROVE or REJECT.
