# Forensic Audit Report — Milestone M15 & Entire Phase 3

- **Auditor**: `auditor_m15` (`teamwork_auditor`)
- **Profile**: General Project (Development Mode per `ORIGINAL_REQUEST.md`)
- **Target**: Milestone M15 & Entire Phase 3
- **Verdict**: **`VERDICT: CLEAN`**

---

## 1. Observation

### 1.1. GitHub Remote & Commit Authenticity Audit
Command executed:
`git rev-parse 02a715e ; git rev-parse 9cf67dc ; git log -2 --pretty=fuller origin/master ; git ls-remote origin refs/heads/master`

Verbatim Output:
```
02a715ec2d12ec7247540a42b4d989cff6d37361
9cf67dc88a016a947675939d4f65ebfac0fa14e4
commit 9cf67dc88a016a947675939d4f65ebfac0fa14e4
Author:     Nguyen Tuan Anh <tuananh@smarthome.local>
AuthorDate: Thu Nov 5 01:07:37 2026 +0700
Commit:     Nguyen Tuan Anh <tuananh@smarthome.local>
CommitDate: Thu Nov 5 01:07:37 2026 +0700

    docs(report): finalize Phase 3 acceptance metrics, curl verification, and production release sign-off

commit 02a715ec2d12ec7247540a42b4d989cff6d37361
Author:     Nguyen Tuan Anh <tuananh@smarthome.local>
AuthorDate: Thu Nov 5 00:59:46 2026 +0700
Commit:     Nguyen Tuan Anh <tuananh@smarthome.local>
CommitDate: Thu Nov 5 00:59:46 2026 +0700

    feat(phase3): vercel routing, session rbac, android compose, ponytail modularization
9cf67dc88a016a947675939d4f65ebfac0fa14e4	refs/heads/master
```
- Both commits `02a715e` and `9cf67dc` exist genuinely in the commit graph.
- Commit `9cf67dc` is verified directly on GitHub remote `https://github.com/nep94121-lab/do-an-tot-nghiep-smart-home-voice-ai.git` at `refs/heads/master`.

### 1.2. Vercel Production Deployment & Live curl Audit
Direct empirical queries were executed against `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`:
1. `/mobile`: `HTTP/1.1 307 Temporary Redirect`, `Location: /app`, `Server: Vercel`, `X-Vercel-Id: hkg1::8t9th-1793815864120-ad2deedd925b`
2. `/architecture`: `HTTP/1.1 200 OK`, `filename="smart-home-voice-ai.architecture.html"`, `Server: Vercel`
3. `/offline`: `HTTP/1.1 200 OK`, `filename="offline.html"`, `Server: Vercel`
4. `/404`: `HTTP/1.1 404 Not Found`, `filename="404.html"`, `Server: Vercel`
5. `/403`: `HTTP/1.1 403 Forbidden`, `filename="403.html"`, `Server: Vercel`
6. `/500`: `HTTP/1.1 500 Internal Server Error`, `filename="500.html"`, `Server: Vercel`
7. `/qr_expired`: `HTTP/1.1 200 OK`, `filename="qr_expired.html"`, `Server: Vercel`
8. `/sw.js`: `HTTP/1.1 200 OK`, `Content-Type: application/javascript; charset=utf-8`, `filename="sw.js"`, `Server: Vercel`
9. `/duong-dan-khong-ton-tai-xyz-404`: `HTTP/1.1 404 Not Found`, `filename="404.html"`, custom design system error page rendered without Vercel raw error.
10. `/`: `HTTP/1.1 200 OK`, `filename="index.html"`, `Server: Vercel`
11. `/app`: `HTTP/1.1 200 OK`, `filename="index.html"`, `Server: Vercel`

All edge responses originate from genuine Vercel infrastructure (`Server: Vercel`, `X-Vercel-Id: hkg1::...`).

### 1.3. Core Deliverables (R1–R4) Implementation Integrity
1. **R1 Vercel Routing**:
   - `vercel.json`: Valid JSON with 18 routes, strict regex anchoring, clean precedence (`/api/`, `/sw.js`, error pages, static, catch-all 404).
   - All static targets exist on disk and serve valid content.
2. **R2 Session-Based RBAC**:
   - `simulator/auth/session_store.py`: Genuine thread-safe `SessionStore` backed by memory cache and SQLite table `user_sessions`.
   - `simulator/api/deps.py` & `simulator/api/routes_devices.py`: Stateless token resolution via `resolve_request_session` across Authorization Bearer, X-Session-Token, cookies, query params, and body payload.
   - Zero global-state contamination between concurrent user sessions.
3. **R3 Android Jetpack Compose**:
   - Modularized into `android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/`:
     - `HomeScreenTab.kt` (324L), `DevicesScreenTab.kt` (164L), `VoiceScreenTab.kt` (273L), `AccountScreenTab.kt` (760L), `ForgotPasswordScreen.kt` (455L), `VoiceBottomSheet.kt` (346L), `QrScannerScreen.kt` (331L), `MainComponents.kt` (194L), `MainScreenModels.kt` (41L).
   - Independent build command:
     `& "C:\Users\LENOVO\.gradle\jdks\eclipse_adoptium-17-amd64-windows.2\bin\java.exe" "-Dorg.gradle.appname=gradlew" -classpath "gradle\wrapper\gradle-wrapper.jar" org.gradle.wrapper.GradleWrapperMain assembleDebug`
   - Result: **`BUILD SUCCESSFUL in 3m 21s`** (71 actionable tasks: 8 executed, 63 up-to-date), generated valid debug APK (`android_app/app/build/outputs/apk/debug/app-debug.apk`, 12,037,214 bytes).
4. **R4 Ponytail Modularization**:
   - Monoliths decomposed:
     - `simulator/static/style.css`: 970L -> 2L (imports modular CSS).
     - `simulator/static/app.js`: 1,031L -> 10L (forwarding stub).
     - `simulator/voice_auth.py`: 2,551L -> 1,440L with clean sub-modules `simulator/voice/dsp_features.py` (789L), `synthesis_augment.py` (79L), `enrollment_quality.py` (304L).
     - `MainScreen.kt`: 2,710L -> 850L.
   - Zero facade: genuine logic implemented throughout; all contracts, DOM IDs, and window hooks preserved.
   - `simulator/static/house3d.js` intact (0 edits, 58,359 bytes).
   - `ui_mockups/` preserved intact (0 deletions).

### 1.4. Code Encoding & Line Ending Audit
- Automated binary scan across all tracked files:
  - 100% of source code, test, documentation, spec, and configuration files (.py, .kt, .js, .html, .css, .md, .sh, .yaml) strictly adhere to **UTF-8 without BOM** and **0 CRLF** (POSIX LF `\n`).
  - `FIX_REPORT_20261104.md`: Confirmed 0 CRLF and no BOM.
  - Runtime JSON files in `simulator/data/` (7 files) generated during execution have CRLF from default Windows Python file write, which is harmless runtime state rather than source code tampering.

### 1.5. Test Suite Anti-Weakening / Anti-Tampering Audit
- Evaluated `git diff origin/master~2..origin/master tests/`:
  - `tests/test_challenger_m3_security_live.py`: Added offline mode teardown reset (`server_connected: True`).
  - `tests/test_challenger_m5_orthogonal_stress.py`: Targeted event counting `WHERE event_type = 'ev1'` without altering rollback assertion.
  - `tests/test_m8_mobile_screens.py`: Passed `window` parameter required by time-windowed QR API contract.
  - `tests/test_phase1_bugfixes_20261104.py`: Added device state reset in fixture to ensure test isolation.
  - 3 major new test suites added:
    - `tests/test_challenger_m11_vercel_routing.py` (307 lines)
    - `tests/test_p3_session_rbac_concurrency.py` (457 lines)
    - `tests/test_p3_challenger_m12_adversarial.py` (332 lines)
  - Zero assertions were deleted or weakened.

### 1.6. Independent Execution of Test Suites
1. **Pytest Core Suites**:
   - Command: `python -X utf8 -m pytest tests/test_challenger_m11_vercel_routing.py tests/test_p3_session_rbac_concurrency.py tests/test_p3_challenger_m12_adversarial.py tests/test_phase1_bugfixes_20261104.py tests/test_m6_web_error_sw.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp`
   - Result: **94 passed in 67.60s** (100% PASS, Exit Code 0).
2. **GitHub Spec Kit Convergence**:
   - Command: `python scripts/speckit_converge.py`
   - Result: **CONVERGED 100%** across all 6 Constitution articles, 10 live HTTP endpoints, WS 3-strike, and live mic stream.

---

## 2. Logic Chain

1. From `ORIGINAL_REQUEST.md`, the integrity mode is `development` with strict requirements to verify authentic commits, genuine Vercel edge deployment, R1-R4 deliverables, encoding/line-endings, and zero test tampering.
2. Direct inspection of git commits revealed `02a715e` and `9cf67dc` are present, verified by `git rev-parse` and live `git ls-remote` on GitHub master.
3. Direct HTTP probing of `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app` with `curl.exe` proved the production site is live on Vercel's global CDN (`hkg1`), returning exact required status codes and headers for all 11 audited paths.
4. Source code inspection of `session_store.py`, `vercel.json`, `MainScreen.kt`, and `voice/` confirmed genuine, substantive implementations without dummy facades or hardcoded bypasses.
5. Android Gradle compilation ran to completion independently with `BUILD SUCCESSFUL`, producing a 12MB debug APK.
6. Test diff inspection showed zero weakened assertions and extensive addition of concurrency and adversarial test suites.
7. Independent test execution confirmed 94/94 tests passing and 100% Spec Kit convergence.
8. Therefore, the work product fully satisfies all integrity criteria and contains zero fraud or facade.

---

## 3. Caveats

1. The Samsung Galaxy S9 hardware device (`2223e8784b0c7ece`) is currently physically disconnected via USB (`Present: False` in Windows PnP query), so live on-device APK installation and adb screencap was omitted as specified in `ORIGINAL_REQUEST.md` ("Nếu thiết bị S9 ... đang kết nối").
2. In the working tree, `simulator/database_sqlite.py` has an uncommitted modification relating to connection closing (`_WAL_ANCHOR_CONN = None`), while the repository committed on GitHub `origin/master` (`9cf67dc`) is immutable and clean.
3. No other caveats.

---

## 4. Conclusion

**`VERDICT: CLEAN`**

Milestone M15 and the entire Phase 3 deliverable have been executed with complete forensic integrity. Commits `02a715e` and `9cf67dc` are verified on GitHub `origin/master`, the Vercel production deployment is authentic and passing all live routing checks, Android Compose compiles cleanly (`BUILD SUCCESSFUL`), and the test suite has not been tampered with or weakened.

The work product is **ACCEPTED**.

---

## 5. Verification Method

1. **Verify GitHub Commits**:
   ```bash
   git ls-remote origin refs/heads/master
   git log -2 --oneline origin/master
   ```
2. **Verify Live Vercel Routing**:
   ```powershell
   curl.exe -s -o NUL -w "%{http_code}`n" https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/mobile
   curl.exe -s -o NUL -w "%{http_code}`n" https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/architecture
   curl.exe -s -o NUL -w "%{http_code}`n" https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/duong-dan-khong-ton-tai-xyz-404
   ```
3. **Verify Android Compose Build**:
   ```powershell
   Set-Location 'android_app\.lightbuild\gradle'
   & 'C:\Users\LENOVO\.gradle\jdks\eclipse_adoptium-17-amd64-windows.2\bin\java.exe' '-Dorg.gradle.appname=gradlew' -classpath 'gradle\wrapper\gradle-wrapper.jar' org.gradle.wrapper.GradleWrapperMain assembleDebug
   ```
4. **Verify Pytest Suite**:
   ```bash
   python -X utf8 -m pytest tests/test_challenger_m11_vercel_routing.py tests/test_p3_session_rbac_concurrency.py tests/test_p3_challenger_m12_adversarial.py tests/test_phase1_bugfixes_20261104.py tests/test_m6_web_error_sw.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp
   ```
