# Task: Challenger - Milestone 3 Empirical Verification
Role: teamwork_challenger
Scope: Empirically challenge Milestone 3 changes (Bugs 6, 7, 8, 9, 12, 13):
1. Adversarial test:
   - Check that Three.js canvas is mounted into `#mobileOverviewBox` with preview-16-9.
   - Check that all 7 devices are visible in mobile Devices tab.
   - Check that safe-area padding prevents logout button occlusion on Samsung Internet.
   - Send extreme sensor data (-999, 999) to verify clamping on desktop `#secSensors`.
   - Verify that QR scanner modal has only 1 instruction string.
   - Verify that `/logs` displays $\le 20$ rows initially and paginates/loads more.
2. Execute tests: `python -X utf8 -m pytest tests/test_p4_survey3_ui_layout.py --basetemp=.pytest_tmp`.
3. Provide verdict: APPROVE or REJECT.
