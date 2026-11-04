# Task: Worker Milestone 1 Remediation (CRLF & Recursive Log Key Masking)
Role: teamwork_worker
Scope:
1. Apply bulletproof persistence standard across `simulator/`:
   - Replace all `write_text` calls in `simulator/auth_3layer.py`, `simulator/engine/audit_logger.py`, `simulator/engine/constants_and_time.py`, `simulator/knowledge_rag.py`, `simulator/mqtt_bridge.py`, `simulator/rule_engine.py`, `simulator/voice_auth.py` with `write_bytes(payload.encode("utf-8"))` or `open(..., newline="\n")`.
   - Update `tests/e2e/conftest.py`, `tests/test_challenger_m1_adversarial.py`, and `tests/test_challenger_m1_reverify_direct.py` teardowns.
   - Normalize all 10 `.json`/`.jsonl` files in `simulator/data/` to 100% 0 CRLF (POSIX LF).
   - Create `.gitattributes` enforcing LF across all repository files.
2. Enhance `mask_sensitive_log_data()` in `simulator/api/routes_logs.py`:
   - Add recursive dictionary key check: if `re.search(r"(password|hint|secret|token|otp|mat_khau)", str(k), re.I)`, mask value as `"******"`.
3. Add 3 automated tests to `tests/test_p4_survey1_security_auth.py`:
   - `test_save_accounts_produces_zero_crlf_on_windows`
   - `test_bug1_logs_api_masks_nested_dictionary_sensitive_keys`
   - `test_all_simulator_data_and_modified_code_have_zero_crlf`
4. Run full verification suite (pytest and CRLF invariance check), confirm 0 CRLF and 100% PASS.
