# Independent Re-verification & Adversarial Challenge Report — Milestone 1 Remediation

## Review Summary

**Verdict**: APPROVE  
**Milestone**: Milestone 1 Remediation (Security, Auth & Persistence Hardening — Bugs 1, 2, 4, 5, 15)  
**Reviewer Role**: `teamwork_reviewer_m1_reverify_1` (reviewer, critic)  
**Project Root**: `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp`  
**Date**: 2026-11-04T20:38:00Z  

---

## 1. Observation

### 1.1. Resolution of Previous Finding 1 (CRLF in `simulator/data/accounts_3layer.json` & Persistence)
- **Previous Violation**: `simulator/data/accounts_3layer.json` had 715 CRLF lines generated on Windows because `simulator/auth_3layer.py` used `Path.write_text(payload, encoding="utf-8")` without `newline="\n"`.
- **Observed Remediation**:
  1. `simulator/auth_3layer.py`:
     - Line 186 (`_save_accounts`): `ACCOUNTS_FILE.write_bytes(payload.encode("utf-8"))`
     - Line 195 (`_save_family_allowlist`): `FAMILY_ALLOWLIST_FILE.write_bytes(payload.encode("utf-8"))`
     - Line 204 (`_save_invite_links`): `INVITE_LINKS_FILE.write_bytes(payload.encode("utf-8"))`
     - Line 234 (`_log_event`): `AUTH_EVENTS_FILE.write_bytes(payload.encode("utf-8"))`
  2. Subsystem persistence updates to `write_bytes` / `newline="\n"`:
     - `simulator/engine/audit_logger.py` (Lines 34, 64)
     - `simulator/engine/constants_and_time.py` (Line 476)
     - `simulator/knowledge_rag.py` (Lines 121, 164, 308, 335)
     - `simulator/mqtt_bridge.py` (Lines 143, 153, 331)
     - `simulator/rule_engine.py` (Lines 130, 149)
     - `simulator/voice_auth.py` (Lines 416, 529, 600, 635, 1288)
     - `tests/e2e/conftest.py`, `tests/test_challenger_m1_adversarial.py`, `tests/test_challenger_m1_reverify_direct.py`
  3. Git newline enforcement: `.gitattributes` added at project root enforcing `* text=auto eol=lf`.
- **Pre-Test Binary Line Ending Verification**:
  - `simulator/data/accounts_3layer.json`: CRLF=0, LF=716 (100% LF)
  - All 12 text/JSON files in `simulator/data/`: CRLF=0
  - All 74 modified workspace files: CRLF=0 (100% LF)
- **Post-Test Binary Line Ending Verification**:
  - Executed 75 full tests (which repeatedly modified `auth_3layer_events.json` and `system_audit_logs.jsonl`).
  - `simulator/data/accounts_3layer.json`: CRLF=0, LF=716
  - `simulator/data/auth_3layer_events.json`: CRLF=0, LF=985
  - `simulator/data/system_audit_logs.jsonl`: CRLF=0, LF=260
  - All files in `simulator/data/` preserved **0 CRLF**.

### 1.2. Resolution of Previous Finding 2 (Dictionary Key Masking in `simulator/api/routes_logs.py`)
- **Previous Violation**: Structured dictionary logs with keys like `password` or `password_plain_hint` leaked raw values in `item["details"]` because `mask_sensitive_log_data()` only recursed on dictionary values and missed key examination.
- **Observed Remediation**:
  In `simulator/api/routes_logs.py` (Lines 20-45):
  ```python
  SENSITIVE_KEY_PATTERN = re.compile(r"(password|hint|secret|token|otp|mat_khau)", re.IGNORECASE)

  def mask_sensitive_log_data(text: Any) -> Any:
      """Che gợi ý mật khẩu và thông tin xác thực nhạy cảm trong log hiển thị (hỗ trợ cả chuỗi và dictionary keys)."""
      if isinstance(text, str):
          t = re.sub(r"(Mật khẩu gợi ý:\s*)([^\s\)]+)", r"\1******", text, flags=re.IGNORECASE)
          t = re.sub(
              r"((?:password|password_plain_hint|hint|secret|token|otp|mat_khau)['\"]?\s*[:=]\s*['\"])([^'\"]+)(['\"])",
              r"\1******\3",
              t,
              flags=re.IGNORECASE,
          )
          return t
      if isinstance(text, dict):
          return {
              k: (
                  "******"
                  if SENSITIVE_KEY_PATTERN.search(str(k))
                  else mask_sensitive_log_data(v)
              )
              for k, v in text.items()
          }
      if isinstance(text, list):
          return [mask_sensitive_log_data(item) for item in text]
      return text
  ```
- **Adversarial & Dynamic Verification**:
  - Executed 50 dynamic randomized test cases generating random prefixes, suffixes, and permutations of sensitive key names (`password`, `hint`, `secret`, `token`, `otp`, `mat_khau` across random casings).
  - Result: 50/50 PASSED.
  - Verified deep nesting, lists of dictionaries, and API endpoint `/api/logs/dashboard`. All sensitive values masked to `"******"`, while non-sensitive keys and values (`"normal_data": "public_info"`) remain intact.

### 1.3. Test Suite Execution & Teardown Cleanliness
- **Command executed**:
  `python -X utf8 -m pytest tests/test_p4_survey1_security_auth.py tests/test_challenger_m4_dom.py tests/test_m3_challenger_api.py tests/test_p3_session_rbac_concurrency.py --basetemp=.pytest_tmp`
- **Result**: `75 passed, 46 warnings in 18.96s (Exit Code: 0)`.
- **Adversarial challenger test execution**:
  `python -X utf8 -m pytest tests/test_challenger_m1_2_adversarial.py tests/test_adversarial_m1_challenger.py --basetemp=.pytest_tmp`
- **Result**: `13 passed, 3 warnings in 7.21s (Exit Code: 0)`.
- **Teardown Cleanliness**:
  - `python -c "import shutil, pathlib; shutil.rmtree('.pytest_tmp', ignore_errors=True)"`
  - Confirmed `.pytest_tmp` does not exist (`pytest_tmp exists? False`).

### 1.4. DOM IDs and Window Hooks Verification
- **Observed in `mobile_app/index.html`**:
  - Checked 68/68 required DOM IDs from `REQUIRED_68_DOM_IDS` (including `mobileOverviewBox`, `devGrid`, `btnMobileMicLabel`, `mobileQrSvgContainer`, `mobileVoiceMetrics`, `mqttLog`, `humVal`, `tempVal`, `soilVal`).
  - Result: **68/68 present (0 missing)**.
- **Observed in `simulator/static/js/mobile_app.js`**:
  - Checked 25/25 required `window.*` hooks from `REQUIRED_25_WINDOW_HOOKS` (including `window.submitMobileLogin`, `window.toggleMobileVoiceListen`, `window.refreshMobileQr10s`, `window.filterDevicesByRoom`, `window.scrollToSection`).
  - Result: **25/25 exported (0 missing)**.
- **Observed in `simulator/static/index.html` & `simulator/static/js/app.js`**:
  - `#homeCurrentAccountBadge`: present and toggled dynamically.
  - `#homeSessionDurationBadge`: present, displays "Không giới hạn" (Tier 1 Owner) and "Còn 30 ngày" (Tier 2 Family), hidden on logout.
  - `#btnLogoutHome`, `#gateStatusBox`: present and reset on logout.

### 1.5. Anti-Integrity Violation & Cryptographic Audit
- Checked for hardcoded test results, facade logic, and fake implementations:
  - Seed accounts in `simulator/data/accounts_3layer.json` and `DEFAULT_ACCOUNTS` in `simulator/auth/constants_and_crypto.py`:
    - `senat6031@gmail.com`: Tier 2 family account, PBKDF2 SHA-256 hash verified against password `GiaDinh@123` with 100,000 iterations.
    - `kbanh376@gmail.com`: Tier 3 guest account, PBKDF2 SHA-256 hash verified against password `Khach@789` with 100,000 iterations.
    - No plaintext password hints present for seed accounts.
  - `mask_sensitive_log_data()`: genuine recursive pattern traversal, not hardcoded to specific test keys.
  - No dummy or facade code detected.

---

## 2. Logic Chain

1. **CRLF Remediation Soundness**:
   - The root cause of Windows CRLF generation was Python's `Path.write_text()` translating `\n` to `\r\n`.
   - By converting all data and state persistence to `.write_bytes(payload.encode("utf-8"))` and explicit `newline="\n"` in file open handles, C-runtime translation is bypassed.
   - Empirical proof: executing 75 test cases triggered real file writes and left 0 CRLF across `simulator/data/`.
2. **Log Masking Soundness**:
   - `SENSITIVE_KEY_PATTERN = re.compile(r"(password|hint|secret|token|otp|mat_khau)", re.IGNORECASE)` captures all variants of sensitive key names.
   - Dictionary key checking masks the value immediately if the key matches, preventing credential leakage in structured JSON logs.
3. **No Regressions**:
   - All 75 test cases in the verification suite and all 13 adversarial challenger tests pass with exit code 0.
   - All 68 DOM IDs and 25 window hooks remain intact.

---

## 3. Caveats

- Live SMTP email dispatch (`send_gmail: true`) in `/api/auth3/forgot_password_send_otp` was tested with mocked SMTP transport because `GMAIL_APP_PASSWORD` was not provided in this local testing environment. The code handles network/SMTP failures gracefully with clean fallback.
- Full Playwright 3-roles live browser verification across the web interface is part of Milestone M4 gating.

---

## 4. Conclusion

All findings from the previous review and forensic audit have been **GENUINELY and THOROUGHLY RESOLVED**:
- **0 CRLF** across all files in `simulator/data/` and all modified codebase files.
- **Robust dictionary key masking** in `routes_logs.py` protecting sensitive credentials.
- **75/75 pytest cases PASS** with exit code 0; `.pytest_tmp` cleanly purged.
- **68 DOM IDs and 25 window hooks** 100% intact.
- **Zero integrity violations**.

**Final Verdict**: **APPROVE**. Milestone 1 is ready to be closed and proceed to Milestone 2.

---

## 5. Verification Method

To independently reproduce the verification:

```bash
# 1. Verify 0 CRLF across simulator/data/
python -c "
import pathlib
data_dir = pathlib.Path('simulator/data')
for f in sorted(data_dir.iterdir()):
    if f.is_file() and f.suffix.lower() in ('.json', '.jsonl'):
        raw = f.read_bytes()
        crlf = raw.count(b'\r\n')
        assert crlf == 0, f'VIOLATION: {f.name} contains {crlf} CRLF'
print('VERIFIED: 100% of data files have 0 CRLF!')
"

# 2. Verify dictionary key log masking
python -c "
from simulator.api.routes_logs import mask_sensitive_log_data
sample = {'details': {'user_token': 'secret123', 'otp_code': '999888', 'password_plain_hint': '123456', 'safe': 'val'}}
masked = mask_sensitive_log_data(sample)
assert masked['details']['user_token'] == '******'
assert masked['details']['otp_code'] == '******'
assert masked['details']['password_plain_hint'] == '******'
assert masked['details']['safe'] == 'val'
print('VERIFIED: Sensitive dictionary keys properly masked!')
"

# 3. Run full test suite and clean up
python -X utf8 -m pytest tests/test_p4_survey1_security_auth.py tests/test_challenger_m4_dom.py tests/test_m3_challenger_api.py tests/test_p3_session_rbac_concurrency.py --basetemp=.pytest_tmp
python -c "import shutil, pathlib; shutil.rmtree('.pytest_tmp', ignore_errors=True)"

# 4. Invalidation conditions
# - Any CRLF (b'\r\n') appearing in simulator/data/*.json or *.jsonl
# - Any unmasked credential key in /api/logs/dashboard
# - Any failure in the test suite
```
