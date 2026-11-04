# Task: Forensic Auditor - Milestone 1 Re-audit
Role: teamwork_auditor
Scope: Forensic re-audit of Milestone 1 integrity:
1. Empirically verify 0 CRLF in `simulator/data/accounts_3layer.json` and all 10 data files.
2. Verify that `_save_accounts()` and all persistence methods write 100% pure POSIX LF on Windows.
3. Verify that `mask_sensitive_log_data()` masks all dictionary keys and strings with 0 data leaks.
4. Verify genuine PBKDF2 hashing, 68 DOM IDs, 25 window hooks, 0 plaintext passwords in logs/code.
5. Execute full pytest suite and verify exit code 0.
6. Provide final verdict: CLEAN or INTEGRITY VIOLATION.
