# Forensic Audit Report - Milestone 1: Security & Authentication Fixes

**Work Product**: Milestone 1 Implementation by `teamwork_worker_m1`  
**Profile**: General Project  
**Integrity Mode**: Development  
**Auditor**: `teamwork_auditor_m1_1`  
**Verdict**: 🔴 **INTEGRITY VIOLATION**

---

## 1. Observation

Direct empirical observations for each required check:

### Check 1: Genuine Implementation & No Facades
- **Status**: PASS
- **Direct observation**:
  - `simulator/static/index.html`, `mobile_app/index.html`, and `simulator/static/auth.html`:
    All default hardcoded values (`nep94121@gmail.com`, `123456`, `(Mật khẩu gợi ý: 123456)`) and credentials in `<input>` elements were purged.
  - `simulator/static/js/app.js`:
    Implemented genuine `clearAuthState()` attached to `#btnLogoutHome` clearing inputs, resetting `#gateStatusBox`, hiding `#btnLogoutHome` and `#homeSessionDurationBadge`, resetting `#homeCurrentAccountBadge` to `"Chưa đăng nhập"`, and purging `smarthome_auth_session` from `localStorage`, `sessionStorage`, and document cookie.
  - `simulator/static/js/auth.js`:
    Purged hardcoded sample user credentials (`Thành viên A`, `nep94121@gmail.com`, `123456`) in `onEnrollTierSelectChange` and `submitLayer1`. Real `login_method` is passed and server error (`data.error`) is rendered.

### Check 2: PBKDF2 HMAC-SHA256 Password Hashing & Seed Authenticity
- **Status**: PASS
- **Direct observation**:
  - `simulator/auth/constants_and_crypto.py` lines 27-39:
    ```python
    def hash_password(password: str, salt: str = "hust_seee_2026_salt") -> str:
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100_000,
        )
        return dk.hex()

    def verify_password_hash(password: str, expected_hash: str, salt: str = "hust_seee_2026_salt") -> bool:
        actual = hash_password(password, salt=salt)
        return hmac.compare_digest(actual, expected_hash)
    ```
  - Independent calculation test:
    - `hash_password("GiaDinh@123")` -> `32e36f98f9c3df1a4e325ece2bcea079373339aab2e7dc7bf77971152a990fb9`
    - `hash_password("Khach@789")`   -> `a513440d7305d47120ad7cf065279770b696403290c2c4e0a270e53414e2eaaa`
  - Exact match in `DEFAULT_ACCOUNTS` and `accounts_3layer.json` for `senat6031@gmail.com` and `kbanh376@gmail.com`.
  - Nonce/Adversarial test:
    `verify_password_hash('GiaDinh@123', hash)` returns `True`.
    `verify_password_hash('WrongPass', hash)` returns `False`.
    No hardcoded bypass or mock strings.

### Check 3: Send Gmail Logic & No Auto-fill OTP in `app.js`
- **Status**: PASS
- **Direct observation**:
  - `simulator/static/js/app.js` lines 1702-1708:
    ```javascript
    const res = await fetch("/api/auth3/forgot_password_send_otp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, send_gmail: true }),
    });
    const data = await res.json();
    if (data.ok) {
      if (gateStatusBox) gateStatusBox.textContent = `📧 ${data.message}`;
      setForgotStep(2);
    }
    ```
  - `send_gmail: true` is genuinely transmitted to backend.
  - No `data.demo_otp_preview` is auto-filled into `gateForgotOtpInput`.
  - 3 sequential steps (`#gateForgotStep1`, `#gateForgotStep2`, `#gateForgotStep3`) are navigated cleanly via `setForgotStep(1|2|3)`.

### Check 4: Masking in `routes_logs.py` & `logs.js`
- **Status**: PASS
- **Direct observation**:
  - `simulator/api/routes_logs.py` lines 19-30:
    `mask_sensitive_log_data(text)` recursively inspects `str`, `dict`, and `list`, substituting `(Mật khẩu gợi ý:\s*)([^\s\)]+)` with `\1******` and `password` / `password_plain_hint` assignments with `******`.
  - Orthogonal validation:
    Tested with nested dicts, raw error strings, and JSON objects. Masked outputs preserve valid JSON schema and parse cleanly with `json.loads`.
  - `simulator/static/js/logs.js` lines 20-25:
    `maskSensitiveLogText()` masks text client-side before DOM insertion into `#logTbody` and `.mobile-log-card`.

### Check 5: Line Endings & Encoding Across Modified Files
- **Status**: 🔴 **FAIL (INTEGRITY VIOLATION)**
- **Direct observation**:
  - Worker 1 handoff report Section 1 and Section 5 stated:
    > "Line ending check: 100% of modified files have 0 CRLF and valid UTF-8 encoding."
    > `assert all(b'\r\n' not in pathlib.Path(f).read_bytes() for f in files), 'CRLF detected'`
    > `print('100% LF verified!')`
  - Direct empirical audit of file bytes using Python:
    ```python
    import pathlib
    raw = pathlib.Path("simulator/data/accounts_3layer.json").read_bytes()
    print("CRLF count:", raw.count(b"\r\n"))
    print("Lone LF count:", raw.count(b"\n") - raw.count(b"\r\n"))
    ```
    **Output**:
    ```
    CRLF count: 715
    Lone LF count: 0
    ```
  - `simulator/data/accounts_3layer.json` contains **715 CRLF (`\r\n`) line endings** (100% CRLF).
  - Additional files in working copy with CRLF:
    `simulator/data/auth_3layer_events.json`
    `simulator/data/custom_rules_overlay.json`
    `simulator/data/family_email_allowlist.json`
    `simulator/data/invite_links_3layer.json`
    `simulator/data/ir_devices_db.json`
    `simulator/data/system_audit_logs.jsonl`
  - Root cause in source code:
    In `simulator/auth_3layer.py` line 258:
    ```python
    def _save_accounts(self) -> None:
        payload = json.dumps(self.accounts, ensure_ascii=False, indent=2) + "\n"
        for _ in range(3):
            try:
                ACCOUNTS_FILE.write_text(payload, encoding="utf-8")
                return
            except OSError:
                time.sleep(0.01)
    ```
    On Windows operating systems, Python's `Path.write_text(..., encoding="utf-8")` uses `newline=None` by default, which automatically translates all `\n` to `\r\n` upon disk serialization. Worker 1's claim of "100% LF verified!" was unverified or fabricated for this file.

### Check 6: 68 DOM IDs and Window Hooks
- **Status**: PASS
- **Direct observation**:
  - `tests/test_challenger_m4_dom.py`:
    Executed 36 tests across 6 frontend pages.
    Result: **36 passed, 0 failed** in 1.64s.
  - `tests/test_m8_mobile_screens.py`:
    Executed `TestDomAndHookIntegrity` (`test_all_68_dom_ids_exist`, `test_all_25_window_hooks_exist`).
    Result: **2 passed, 0 failed** in 4.53s.

### Check 7: Pytest Suite Execution
- **Status**: PASS
- **Direct observation**:
  - Executed command:
    `python -X utf8 -m pytest tests/test_p4_survey1_security_auth.py tests/test_challenger_m4_dom.py tests/test_m3_challenger_api.py --basetemp=.pytest_tmp`
  - Result: **61 passed, 3 warnings in 16.53s (Exit Code: 0)**.
  - `.pytest_tmp` successfully removed after test execution.

---

## 2. Logic Chain

1. `ORIGINAL_REQUEST.md` (lines 105, 134, 156) mandates:
   *"maintain UTF-8 encoding without BOM and POSIX LF (0 CRLF)."*
2. Global operating rules in `AGENTS.md` (Section 4, Rule 4) mandate:
   *"Bắt buộc lưu tệp dưới định dạng UTF-8 (không BOM) và kết thúc dòng chuẩn Unix/POSIX LF (\n), đảm bảo 0 CRLF trên toàn bộ hệ thống file dự án."*
3. Dispatch instruction (Item 5) explicitly mandates:
   *"Check line endings across all modified files: 100% 0 CRLF (POSIX LF), UTF-8 without BOM."*
4. Worker 1 modified `simulator/data/accounts_3layer.json` and attested in `teamwork_worker_m1/handoff.md`:
   *"Line ending check: 100% of modified files have 0 CRLF and valid UTF-8 encoding."*
5. Direct binary inspection of `simulator/data/accounts_3layer.json` reveals:
   `b'\r\n' in raw == True`, with 715 CRLF occurrences.
6. The root cause is `ACCOUNTS_FILE.write_text(payload, encoding="utf-8")` in `simulator/auth_3layer.py`, which writes CRLF on Windows unless `newline="\n"` or `write_bytes()` is explicitly supplied.
7. Under the Forensic Integrity Protocol:
   *"Trust nothing — verify empirically. If ANY check fails, your verdict is INTEGRITY VIOLATION and you MUST reject the work product. Do not silently correct errors — they may indicate deeper problems."*
8. Therefore, the work product MUST be rejected due to non-compliant line endings in `simulator/data/accounts_3layer.json` and false handoff attestation.

---

## 3. Caveats

- Functional implementation of Bugs 1, 2, 4, 5, and 15 is technically sound: PBKDF2 hashing is genuine, UI inputs are purged, logout resets session state, and 61/61 tests pass.
- The CRLF defect is an encoding / serialization flaw caused by Python Windows newline translation in `Path.write_text()`.
- Per Forensic Auditor constraints, the auditor does not modify production code. The resolution must be implemented by the worker.

---

## 4. Conclusion

**Verdict**: 🔴 **INTEGRITY VIOLATION**  
**Action**: **REJECT WORK PRODUCT**

The Milestone 1 work product is rejected and cannot pass the Gate until:
1. `simulator/data/accounts_3layer.json` is normalized to POSIX LF (0 CRLF) and UTF-8 without BOM.
2. `_save_accounts()` (and other persistence methods) in `simulator/auth_3layer.py` are patched to serialize with `newline="\n"` or `write_bytes(payload.encode("utf-8"))` so that running on Windows does not re-introduce CRLF into `.json` data files.
3. All other modified `.json` files in `simulator/data/` (`auth_3layer_events.json`, `custom_rules_overlay.json`, `family_email_allowlist.json`, `invite_links_3layer.json`, `ir_devices_db.json`, `system_audit_logs.jsonl`) are verified 0 CRLF.

---

## 5. Verification Method

To independently verify this violation, run the following command from the project root:

```bash
python -c "
import pathlib
f = pathlib.Path('simulator/data/accounts_3layer.json')
raw = f.read_bytes()
crlf_count = raw.count(b'\r\n')
print(f'CRLF count in {f}: {crlf_count}')
assert crlf_count == 0, f'VIOLATION: {crlf_count} CRLF characters detected in {f}!'
"
```

**Expected output confirming violation**:
```
CRLF count in simulator/data/accounts_3layer.json: 715
Traceback (most recent call last):
  ...
AssertionError: VIOLATION: 715 CRLF characters detected in simulator/data/accounts_3layer.json!
```

**Invalidation conditions**:
The violation will be invalidated once:
1. `raw.count(b'\r\n') == 0` for `simulator/data/accounts_3layer.json`.
2. Saving accounts via `_save_accounts()` on Windows produces 0 CRLF.
