# Investigation & Remediation Report — Codebase-wide File Persistence & Windows CRLF Elimination

**Agent**: `teamwork_explorer_m1_remediation_2`  
**Mission**: Codebase-wide scan for all file persistence operations in `simulator/` to eliminate Windows CRLF regressions  
**Scope**: `simulator/auth_3layer.py`, `simulator/auth/`, `simulator/api/`, backend engine/services, `simulator/data/`, and test teardowns  
**Project Root**: `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp`  
**Date**: 2026-11-04T20:20:00Z  

---

## 1. Observation

### 1.1. Empirical Audit of `simulator/data/` (All 13 Files)
A complete byte-level audit was executed across all files in `simulator/data/`:
```bash
python .agents/teamwork/teamwork_explorer_m1_remediation_2/scan_data_dir.py
```
**Exact empirical findings**:
| File Path | Size (Bytes) | CRLF (`\r\n`) Count | LF (`\n`) Count | BOM Present | Status |
|---|---|---|---|---|---|
| `simulator/data/accounts_3layer.json` | 27,363 | 716 | 0 | False | 🔴 100% CRLF (Violation) |
| `simulator/data/auth_3layer_events.json` | 32,180 | 975 | 0 | False | 🔴 100% CRLF (Violation) |
| `simulator/data/custom_rules_overlay.json` | 2,887 | 111 | 0 | False | 🔴 100% CRLF (Violation) |
| `simulator/data/factory_default_rules.json` | 238 | 6 | 0 | False | 🔴 100% CRLF (Violation) |
| `simulator/data/family_email_allowlist.json` | 2,771 | 83 | 0 | False | 🔴 100% CRLF (Violation) |
| `simulator/data/invite_links_3layer.json` | 1,595 | 38 | 0 | False | 🔴 100% CRLF (Violation) |
| `simulator/data/ir_devices_db.json` | 3,811 | 183 | 0 | False | 🔴 100% CRLF (Violation) |
| `simulator/data/knowledge_base.json` | 84,713 | 2,209 | 0 | False | 🔴 100% CRLF (Violation) |
| `simulator/data/voiceprints.json` | 28,173 | 1,101 | 0 | False | 🔴 100% CRLF (Violation) |
| `simulator/data/system_audit_logs.jsonl` | 1,808 | 5 | 0 | False | 🔴 100% CRLF (Violation) |
| `simulator/data/esp8266_flash_replica.json` | 1,326 | 0 | 59 | False | 🟢 Pure LF (At Risk) |
| `simulator/data/knowledge_embeddings_cache.json` | 3,989,833 | 0 | 0 | False | 🟢 Single-line JSON |
| `simulator/data/smarthome.db` | 39,579,648 | N/A | N/A | False | 🟢 Binary SQLite DB |

**Summary**: Exactly **10 files** under `simulator/data/` currently suffer from CRLF line endings, totaling **5,427 CRLF occurrences**.

---

### 1.2. AST & Call-Graph Scan of All File Persistence Operations in `simulator/`
An AST parse across all 38 Python files in `simulator/` detected 21 exact file write/persistence operations:

#### A. `simulator/auth_3layer.py`
- Line 186:
  `ACCOUNTS_FILE.write_text(payload, encoding="utf-8")`
  -> Target: `simulator/data/accounts_3layer.json`
- Line 195:
  `FAMILY_ALLOWLIST_FILE.write_text(payload, encoding="utf-8")`
  -> Target: `simulator/data/family_email_allowlist.json`
- Line 204:
  `INVITE_LINKS_FILE.write_text(payload, encoding="utf-8")`
  -> Target: `simulator/data/invite_links_3layer.json`
- Line 233-236:
  `AUTH_EVENTS_FILE.write_text(json.dumps(self.verification_logs[:70], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")`
  -> Target: `simulator/data/auth_3layer_events.json`

#### B. `simulator/engine/audit_logger.py`
- Line 34-35:
  ```python
  line = json.dumps(entry, ensure_ascii=False) + "\n"
  with AUDIT_LOG_FILE.open("a", encoding="utf-8") as f:
      f.write(line)
  ```
  -> Target: `simulator/data/system_audit_logs.jsonl`
- Line 64:
  `AUDIT_LOG_FILE.write_text("", encoding="utf-8")`

#### C. `simulator/engine/constants_and_time.py`
- Line 476:
  `FACTORY_FILE.write_text(json.dumps(factory_data, ensure_ascii=False, indent=2), encoding="utf-8")`
  -> Target: `simulator/data/factory_default_rules.json`

#### D. `simulator/knowledge_rag.py`
- Line 121:
  `KB_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")`
  -> Target: `simulator/data/knowledge_base.json`
- Line 164-175:
  `CACHE_FILE.write_text(json.dumps(...), encoding="utf-8")`
  -> Target: `simulator/data/knowledge_embeddings_cache.json`
- Line 308-311:
  `KB_FILE.write_text(json.dumps({"version": KB_VERSION, "items": self.items}, ensure_ascii=False, indent=2), encoding="utf-8")`
  -> Target: `simulator/data/knowledge_base.json`
- Line 335:
  `KB_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")`
  -> Target: `simulator/data/knowledge_base.json`

#### E. `simulator/mqtt_bridge.py`
- Line 143:
  `IR_DB_FILE.write_text(json.dumps(default_db, ensure_ascii=False, indent=2), encoding="utf-8")`
  -> Target: `simulator/data/ir_devices_db.json`
- Line 153:
  `IR_DB_FILE.write_text(payload, encoding="utf-8")`
  -> Target: `simulator/data/ir_devices_db.json`
- Line 331:
  `EDGE_REPLICA_FILE.write_text(json.dumps(replica_payload, ensure_ascii=False, indent=2), encoding="utf-8")`
  -> Target: `simulator/data/esp8266_flash_replica.json`

#### F. `simulator/rule_engine.py`
- Line 130:
  `OVERLAY_FILE.write_text(json.dumps(default_ov, ensure_ascii=False, indent=2), encoding="utf-8")`
  -> Target: `simulator/data/custom_rules_overlay.json`
- Line 149:
  `OVERLAY_FILE.write_text(json.dumps(self.overlay_rules, ensure_ascii=False, indent=2), encoding="utf-8")`
  -> Target: `simulator/data/custom_rules_overlay.json`

#### G. `simulator/voice_auth.py`
- Line 416:
  `VOICEPRINT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")`
  -> Target: `simulator/data/voiceprints.json`
- Line 529:
  `VOICEPRINT_FILE.write_text(json.dumps(self.profiles, ensure_ascii=False, indent=2), encoding="utf-8")`
  -> Target: `simulator/data/voiceprints.json`
- Line 600:
  `VOICEPRINT_FILE.write_text(json.dumps(self.profiles, ensure_ascii=False, indent=2), encoding="utf-8")`
  -> Target: `simulator/data/voiceprints.json`
- Line 635:
  `VOICEPRINT_FILE.write_text(json.dumps(self.profiles, ensure_ascii=False, indent=2), encoding="utf-8")`
  -> Target: `simulator/data/voiceprints.json`
- Line 1288:
  `VOICEPRINT_FILE.write_text(json.dumps(self.profiles, ensure_ascii=False, indent=2), encoding="utf-8")`
  -> Target: `simulator/data/voiceprints.json`
- Line 421:
  `wave.open(str(path), "wb")` (Binary WAV audio write — already safe from text newline translation).

---

### 1.3. Audit of `simulator/auth/` and `simulator/api/`
- `simulator/auth/invite_and_gmail_mixin.py`: Delegates all data mutations to `self._save_accounts()`, `self._save_family_allowlist()`, and `self._save_invite_links()`. Contains no direct file `open()` or `write()`.
- `simulator/auth/session_store.py`: In-memory dictionary store (`self.sessions = {}`), no disk persistence.
- `simulator/auth/qr_totp_mixin.py` & `test_suite_mixin.py`: Pure cryptographic and helper routines.
- `simulator/api/routes_auth.py`: Line 753 uses `wave.open(str(wav_path), "rb")` (read-only binary). Delegates persistence to `Auth3LayerEngine` and `VoiceAuthManager`.
- `simulator/api/routes_devices.py`, `routes_logs.py`, `routes_qr.py`: All delegate persistence to backend services; no direct text file writes.

---

### 1.4. Regression Vector in Test Teardown / Test Code
A codebase scan of `tests/` revealed that test teardown routines also write back to `VOICEPRINT_FILE` using unconstrained `write_text()`:
- `tests/e2e/conftest.py:103`:
  `VOICEPRINT_FILE.write_text(orig_voiceprints, encoding="utf-8")`
- `tests/test_challenger_m1_adversarial.py:325`:
  `VOICEPRINT_FILE.write_text(json.dumps(orig_profiles, ensure_ascii=False, indent=2), encoding="utf-8")`
- `tests/test_challenger_m1_reverify_direct.py:154, 174, 193`:
  `VOICEPRINT_FILE.write_text(json.dumps(orig_profiles, ensure_ascii=False, indent=2), encoding="utf-8")`
Whenever these tests run on Windows, they restore `simulator/data/voiceprints.json` with CRLF unless updated.

---

### 1.5. Root Cause Demonstration on Windows Python 3.14
Running empirical serialization tests on Windows AMD64 Python 3.14.7 produced the following output:
```python
# 1. Path.write_text('line1\nline2\n', encoding='utf-8')
# Result raw bytes: b'line1\r\nline2\r\n'  <-- AUTOMATIC CRLF CONVERSION

# 2. Path.write_text('line1\nline2\n', encoding='utf-8', newline='\n')
# Result raw bytes: b'line1\nline2\n'      <-- CLEAN LF

# 3. Path.write_bytes('line1\nline2\n'.encode('utf-8'))
# Result raw bytes: b'line1\nline2\n'      <-- CLEAN LF (Zero conversion possible)

# 4. Path.open('a', encoding='utf-8')
# Result raw bytes: b'line1\r\nline2\r\n'  <-- AUTOMATIC CRLF CONVERSION

# 5. Path.open('a', encoding='utf-8', newline='\n')
# Result raw bytes: b'line1\nline2\n'      <-- CLEAN LF
```

---

## 2. Logic Chain

1. **Observation 1.1** reveals that 10 JSON/JSONL files in `simulator/data/` currently contain 5,427 CRLF occurrences.
2. **Observation 1.2** identifies that all 21 write operations in `simulator/` use `Path.write_text(..., encoding="utf-8")` without `newline="\n"`, or `open("a", encoding="utf-8")` without `newline="\n"`.
3. **Observation 1.5** proves that Python's default text mode on Windows translates `\n` to `\r\n` whenever `newline` is not explicitly set to `\n` or when binary mode is not used.
4. **Observation 1.4** demonstrates that running the test suite triggers write methods (`_save_accounts()`, `_log_event()`, `test_demote_*` teardowns) that continuously re-generate CRLF in `simulator/data/` even if normalized once manually.
5. Therefore, fixing CRLF in `simulator/data/accounts_3layer.json` alone is insufficient and doomed to regress. All persistence call sites in `simulator/` and affected `tests/` teardowns must be hardened with bulletproof serialization methods, followed by a simultaneous normalization of all 10 data files.

---

## 3. Caveats

- `simulator/data/smarthome.db` is an active SQLite database file. It contains arbitrary binary data (including raw `b'\r\n'` bytes). It must NOT be treated as a text file or modified with string newline replacements.
- `simulator/data/knowledge_embeddings_cache.json` is a single-line 3.9MB JSON file without newlines. While currently 0 CRLF, its writer (`simulator/knowledge_rag.py:164`) must be patched to prevent future multiline regression.
- Local developer git settings (`core.autocrlf=false`) do not prevent Python from writing CRLFs. A `.gitattributes` file is recommended to enforce LF across all git operations.

---

## 4. Conclusion & Bulletproof Remediation Guidelines

### 4.1. Bulletproof Serialization Standard

#### Rule 1: JSON Data Files Persistence (Full Rewrite)
Enforce `write_bytes(payload.encode("utf-8"))` or `write_text(payload, encoding="utf-8", newline="\n")`.
The **recommended standard** across the project is:
```python
# Format JSON with trailing LF, then serialize as pure UTF-8 bytes:
payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
target_file.write_bytes(payload.encode("utf-8"))
```
*Rationale*: `write_bytes()` completely bypasses Python's Windows text-mode C-runtime translation layers. It is 100% immune to OS newline defaults across Windows, Linux, and macOS.

#### Rule 2: Append-Only Logging (e.g. `system_audit_logs.jsonl`)
Enforce explicit `newline="\n"` or `"ab"` mode:
```python
# In simulator/engine/audit_logger.py:
line = json.dumps(entry, ensure_ascii=False) + "\n"
with AUDIT_LOG_FILE.open("a", encoding="utf-8", newline="\n") as f:
    f.write(line)
```

---

### 4.2. Actionable File-by-File Remediation Plan

#### [Target 1] `simulator/auth_3layer.py`
Replace lines 186, 195, 204, and 233-236:
```python
# Line 186 in _save_accounts():
ACCOUNTS_FILE.write_bytes(payload.encode("utf-8"))

# Line 195 in _save_family_allowlist():
FAMILY_ALLOWLIST_FILE.write_bytes(payload.encode("utf-8"))

# Line 204 in _save_invite_links():
INVITE_LINKS_FILE.write_bytes(payload.encode("utf-8"))

# Line 233-236 in _log_event():
AUTH_EVENTS_FILE.write_bytes(
    (json.dumps(self.verification_logs[:70], ensure_ascii=False, indent=2) + "\n").encode("utf-8")
)
```

#### [Target 2] `simulator/engine/audit_logger.py`
Replace line 34 and line 64:
```python
# Line 34:
with AUDIT_LOG_FILE.open("a", encoding="utf-8", newline="\n") as f:
    f.write(line)

# Line 64:
AUDIT_LOG_FILE.write_bytes(b"")
```

#### [Target 3] `simulator/engine/constants_and_time.py`
Replace line 476:
```python
# Line 476 in ensure_factory_file():
FACTORY_FILE.write_bytes((json.dumps(factory_data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
```

#### [Target 4] `simulator/knowledge_rag.py`
Replace lines 121, 164, 308, and 335:
```python
# Line 121:
KB_FILE.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

# Line 164:
CACHE_FILE.write_bytes(json.dumps({...}, ensure_ascii=False).encode("utf-8"))

# Line 308:
KB_FILE.write_bytes((json.dumps({"version": KB_VERSION, "items": self.items}, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

# Line 335:
KB_FILE.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
```

#### [Target 5] `simulator/mqtt_bridge.py`
Replace lines 143, 153, and 331:
```python
# Line 143:
IR_DB_FILE.write_bytes((json.dumps(default_db, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

# Line 153:
IR_DB_FILE.write_bytes((payload + ("\n" if not payload.endswith("\n") else "")).encode("utf-8"))

# Line 331:
EDGE_REPLICA_FILE.write_bytes((json.dumps(replica_payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
```

#### [Target 6] `simulator/rule_engine.py`
Replace lines 130 and 149:
```python
# Line 130:
OVERLAY_FILE.write_bytes((json.dumps(default_ov, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

# Line 149:
OVERLAY_FILE.write_bytes((json.dumps(self.overlay_rules, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
```

#### [Target 7] `simulator/voice_auth.py`
Replace lines 416, 529, 600, 635, and 1288:
```python
# Line 416, 529, 600, 635, 1288:
VOICEPRINT_FILE.write_bytes((json.dumps(self.profiles, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
```

#### [Target 8] `tests/` Teardown Routines
Update test teardowns to prevent test runs from dirtying files with CRLF:
- `tests/e2e/conftest.py:103`:
  `VOICEPRINT_FILE.write_bytes(orig_voiceprints.encode("utf-8"))`
- `tests/test_challenger_m1_adversarial.py:325`:
  `VOICEPRINT_FILE.write_bytes((json.dumps(orig_profiles, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))`
- `tests/test_challenger_m1_reverify_direct.py:154, 174, 193`:
  `VOICEPRINT_FILE.write_bytes((json.dumps(orig_profiles, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))`

#### [Target 9] Simultaneous Normalization of All 10 Existing `simulator/data/` Files
Execute the following one-line cleanup command to normalize all 10 existing CRLF files in `simulator/data/` in a single pass:
```python
python -c "
import pathlib
for f in pathlib.Path('simulator/data').glob('*'):
    if f.is_file() and not f.name.endswith('.db'):
        raw = f.read_bytes()
        if b'\r\n' in raw:
            f.write_bytes(raw.replace(b'\r\n', b'\n'))
            print('Normalized to LF:', f.name)
"
```

#### [Target 10] Git-Level Defense (`.gitattributes`)
Create `.gitattributes` at project root:
```gitattributes
* text=auto eol=lf
*.json text eol=lf
*.jsonl text eol=lf
*.py text eol=lf
*.js text eol=lf
*.html text eol=lf
*.css text eol=lf
*.md text eol=lf
```

---

## 5. Verification Method

### 5.1. Codebase-wide Line Ending Verification Command
Run this command from the project root to verify that 100% of data files and source files have 0 CRLF:
```bash
python -c "
import pathlib

data_files = [f for f in pathlib.Path('simulator/data').glob('*') if f.is_file() and not f.name.endswith('.db')]
crlf_detected = []
for f in data_files:
    raw = f.read_bytes()
    count = raw.count(b'\r\n')
    if count > 0:
        crlf_detected.append((f.as_posix(), count))

if crlf_detected:
    for path, cnt in crlf_detected:
        print(f'FAIL: {path} contains {cnt} CRLF lines!')
    raise SystemExit(1)
else:
    print(f'SUCCESS: All {len(data_files)} data files verified 100% POSIX LF (0 CRLF)!')
"
```

### 5.2. Post-Test Execution Invariance Check
To prove that running tests on Windows does NOT cause CRLF regressions:
```bash
# 1. Run full M1 test suite
python -X utf8 -m pytest tests/test_p4_survey1_security_auth.py tests/test_challenger_m4_dom.py tests/test_m3_challenger_api.py tests/test_p3_session_rbac_concurrency.py --basetemp=.pytest_tmp

# 2. Immediately verify 0 CRLF in simulator/data/
python -c "
import pathlib
for f in pathlib.Path('simulator/data').glob('*'):
    if f.is_file() and not f.name.endswith('.db'):
        assert b'\r\n' not in f.read_bytes(), f'REGRESSION: {f.name} was dirtied with CRLF!'
print('PASS: No regression after test execution!')
"

# 3. Clean temporary pytest directory
python -c "import shutil; shutil.rmtree('.pytest_tmp', ignore_errors=True)"
```

### 5.3. Invalidation Conditions
This investigation report will be invalidated if:
1. Any write operation in `simulator/` continues to call `write_text(..., encoding="utf-8")` without `newline="\n"`.
2. Any data file in `simulator/data/` has `raw.count(b"\r\n") > 0` after test execution on Windows.
