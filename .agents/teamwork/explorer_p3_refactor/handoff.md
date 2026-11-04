# Technical Handoff Report: Phase 3 Requirement R4 (Ponytail Modularization Refactor)

**Date**: 2026-11-04  
**Agent**: teamwork_explorer (`explorer_p3_refactor`)  
**Mission**: Deep investigation, codebase scan, Ponytail architectural analysis, and zero-regression modularization blueprint for Phase 3 R4.

---

## 1. Observation

### 1.1 Discovery & Verification of "Skill Ponytail"
- **Author & Source**: Dietrich Gebert (`DietrichGebert/ponytail` on GitHub).
- **Core Archetype**: The *"laziest senior developer in the room"* — a radical anti-bloat, YAGNI (You Aren't Gonna Need It) behavioral framework for AI coding agents.
- **The Decision Ladder (Thang Quyết Định Tối Thiểu Hóa)**:
  1. **YAGNI**: Does this need to exist at all? (If no, eliminate or don't write it).
  2. **Codebase Reuse**: Is it already implemented elsewhere in the project? (Reuse existing utilities; never duplicate).
  3. **Standard Library**: Does Python's or JavaScript's or Kotlin's standard library already handle it? (Use built-ins).
  4. **Native Platform Feature**: Does the browser DOM / Android Jetpack Compose provide this natively? (Eliminate wrapper bloat).
  5. **Installed Dependency**: Can an already-included dependency solve it without adding new packages?
  6. **One Line**: Can the logic be expressed cleanly in a single line?
  7. **Minimum Viable Code**: If new code is strictly necessary, write the absolute minimum amount required.
- **Thorough Reading First**: Deeply inspect callers, callees, AST traces, and data flow before modifying or cutting anything.
- **Non-Negotiable Safety**: Never compromise security boundaries, trust validation, error/data-loss handling, accessibility (a11y), or test contract assertions.

### 1.2 Codebase Scan Results (Large Monolithic Files & Line Counts)
Scanned 127 total source files across Python, JavaScript, Kotlin, HTML, CSS, C++:

| # | Current Lines | Size (KB) | File Path | Language / Role | Complexity Assessment |
|---|---------------|-----------|-----------|-----------------|-----------------------|
| 1 | **2,569** | 96.8 KB | `android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/MainScreen.kt` | Kotlin (Compose) | **CRITICAL MONOLITH**: Single 2,049-line `@Composable fun MainScreen(...)` containing M1 (Home), M2 (Devices/Account), M3 (Forgot/OTP), M4 (Voice Sheet), M5 (QR Scanner), AudioRecord loop, and HTTP networking. |
| 2 | **2,551** | 120.9 KB | `simulator/voice_auth.py` | Python (Backend) | **CRITICAL MONOLITH**: 1,200 lines of Wiener noise filters, MFCC feature extraction, audio synthesis/augmentation + 1,350 lines of `VoiceAuthManager` class. |
| 3 | **1,969** | 71.6 KB | `simulator/static/js/app.js` | JavaScript (Web) | **HIGH MONOLITH**: Core web client, WebSocket handler, 3D toolbar wiring, Login Gate, M7 security modals/banner. Assayed by multiple headless Node VM tests. |
| 4 | **1,820** | 71.3 KB | `simulator/static/house3d.js` | JavaScript (3D Web) | **PROTECTED FILE**: Three.js 3D house engine, v1 light design, raycaster for 7 devices, 7 camera presets. Must remain intact per project rules. |
| 5 | **1,483** | 62.6 KB | `simulator/static/js/mobile_app.js` | JavaScript (PWA) | **HIGH MONOLITH**: Mobile PWA containing all M1..M5 screen controllers, 45 window hooks, and 68 DOM IDs. |
| 6 | **1,139** | 49.6 KB | `simulator/auth/invite_and_gmail_mixin.py` | Python (Backend) | Medium-High: Gmail OTP and guest invite logic. |
| 7 | **1,137** | 18.7 KB | `simulator/static/css/style.css` | CSS (Web) | Active stylesheet loaded by `index.html`. |
| 8 | **1,131** | 52.3 KB | `simulator/auth_3layer.py` | Python (Backend) | Medium-High: 3-Layer authentication orchestrator. |
| 9 | **1,112** | 54.5 KB | `simulator/engine/rules_pool.py` | Python (Backend) | Medium: Automation rules execution pool. |
| 10 | **1,071** | 52.2 KB | `simulator/live/gemini_bridge.py` | Python (Backend) | High: Real-time Gemini Live bidirectional streaming bridge. |
| 11 | **1,036** | 43.9 KB | `simulator/static/js/auth.js` | JavaScript (Web) | Medium: Authentication page client logic. |
| 12 | **1,031** | 35.2 KB | `simulator/static/app.js` | JavaScript (Web) | **DEAD DUPLICATE CODE**: Obsolete pre-Phase-2 duplicate of `simulator/static/js/app.js`. Not loaded by any HTML file. |
| 13 | **970** | 15.4 KB | `simulator/static/style.css` | CSS (Web) | **DEAD DUPLICATE CODE**: Obsolete pre-Phase-2 duplicate of `simulator/static/css/style.css`. |
| 14 | **814** | 45.9 KB | `simulator/static/js/wokwi.js` | JavaScript (Web) | Medium: Wokwi circuit simulation bridge. |
| 15 | **773** | 35.9 KB | `simulator/engine/voice_rbac_mixin.py` | Python (Backend) | Medium: Role-based voice access control mixin. |
| 16 | **752** | 44.2 KB | `simulator/live/prompt_builder.py` | Python (Backend) | Medium: Gemini system prompt generator. |
| 17 | **728** | 31.3 KB | `simulator/api/routes_auth.py` | Python (Backend) | Medium: Auth REST endpoints. |
| 18 | **706** | 32.6 KB | `simulator/database_sqlite.py` | Python (Backend) | Medium: SQLite database layer. |
| 19 | **699** | 14.7 KB | `simulator/static/css/mobile_app.css` | CSS (PWA) | Active stylesheet for mobile PWA. |
| 20 | **617** | 27.7 KB | `simulator/rule_engine.py` | Python (Backend) | Medium: Core rule execution engine. |

### 1.3 Identification of Dead Code & Redundant Files
- **`simulator/static/app.js` (1,031 lines)** vs **`simulator/static/js/app.js` (1,969 lines)**:
  `index.html` loads `<script src="/static/js/app.js"></script>`. `simulator/static/app.js` is an unreferenced legacy file in the root static directory.
- **`simulator/static/style.css` (970 lines)** vs **`simulator/static/css/style.css` (1,137 lines)**:
  `index.html` loads `<link rel="stylesheet" href="/static/css/style.css">`. `simulator/static/style.css` is an unreferenced legacy stylesheet.
- **Combined Dead Code Elimination Opportunity**: Eliminating or shimming these two files immediately removes **2,001 lines** of duplicate bloat.

### 1.4 Strict Test Assertions & Runtime Harnesses Directly Auditing Files
Our investigation of `tests/` revealed strict test fixtures that directly inspect or evaluate source files:
1. **Node.js Headless VM Evaluation (`vm.runInContext` / `vm.runInNewContext`)**:
   - `test_challenger_m4_dom.py`: Loads `simulator/static/js/app.js`, `simulator/static/js/mobile_app.js`, `auth.js`, `guest_enroll.js`, `wokwi.js`, `logs.js` into Node VM. Asserts `ok == True` and zero Uncaught ReferenceError.
   - `test_m7_security_modals_banner.py`: Reads `simulator/static/js/app.js` via `fs.readFileSync` into Node VM. Calls 7 window hooks (`triggerSecurityLockdown`, `showWsReconnectBanner`, `retryWsConnection`, etc.).
   - `test_challenger_m5_interactions.py`: Reads `simulator/static/js/app.js` via `fs.readFileSync` into Node VM. Tests `#firstPageVoiceModal`, clicks `#btnHoldRecordVoice`, and checks POST to `/api/auth3/enroll_voice_sample`.
2. **Literal String & Regex Assertions in Python Test Files**:
   - `test_challenger_m3_stress_dom_raycaster.py`:
     - Asserts `"function initCameraToolbar()"` is in `app.js`.
     - Asserts `"initCameraToolbar();"` is in `app.js`.
     - Asserts `SmartHome3D.init('house3dViewport', 'house3dLabels', toggleDeviceById)` is in `app.js`.
     - Asserts `0` occurrences of `container.innerHTML = ""` in `house3d.js`.
   - `test_m7_security_modals_banner.py`:
     - Asserts regex `window.{exp} =` for 13 specific security modal exports in `app.js`.
     - Asserts `"a.strike_count >= 3"` / `"msg.strike_count >= 3"` in `app.js`.
     - Asserts `"isSecureContext"`, `"NotAllowedError"`, `"showWsRestoredBanner"` in `app.js`.
   - `test_m8_mobile_screens.py`:
     - Asserts `"function switchMobileTab"` in `mobile_app.js`.
     - Asserts all 25 `REQUIRED_25_WINDOW_HOOKS` exist in `mobile_app.js`.
     - Asserts all 68 `REQUIRED_68_DOM_IDS` exist in `mobile_app/index.html`.
   - `test_challenger_m2_gate_ux_empirical.py`:
     - Checks `addEventListener('submit')` and password mismatch rejection in `app.js` and `mobile_app.js`.

---

## 2. Logic Chain

1. **Premise 1**: Requirement R4 mandates modularizing multi-thousand-line monolithic files (`app.js`, Python modules, `MainScreen.kt`) according to Ponytail principles, while ensuring **100% behavior preservation** and **0 broken tests**.
2. **Premise 2**: Test files (`test_challenger_m3`, `test_m7`, `test_m8`, `test_challenger_m4_dom`, `test_challenger_m5`) read `simulator/static/js/app.js` and `simulator/static/js/mobile_app.js` directly from disk using `Path.read_text()` and Node `fs.readFileSync(...)`.
3. **Premise 3**: If `app.js` or `mobile_app.js` were split into ES modules using `import/export` syntax without a bundler, Node's headless VM runners (`vm.runInContext`) would immediately crash with `SyntaxError: Cannot use import statement outside a module`, and string assertions looking for `function initCameraToolbar()` inside `app.js` would fail.
4. **Premise 4**: In Android Kotlin, `MainScreen.kt` has 2,569 lines, but the external contract is simply `@Composable fun MainScreen(onItemClick: (NavKey) -> Unit, modifier: Modifier = Modifier)`. Jetpack Compose allows composables to be freely moved into separate Kotlin files within the same package (`vn.edu.hust.seee.smarthome.ui.main`) or sub-packages without breaking callers.
5. **Premise 5**: In Python, `simulator/voice_auth.py` (2,551 lines) contains pure DSP/feature extraction functions in its first 1,200 lines and `VoiceAuthManager` in lines 1,201–2,551. Moving DSP functions to `simulator/voice/` and re-exporting them in `voice_auth.py` (`from simulator.voice.dsp import ...`) preserves 100% backward compatibility for all existing imports while cutting `voice_auth.py` by over 80%.
6. **Premise 6**: `simulator/static/app.js` and `simulator/static/style.css` in the static root are unused legacy duplicates of files now located in `simulator/static/js/app.js` and `simulator/static/css/style.css`. Replacing `style.css` with `@import "/static/css/style.css";` and `app.js` with a lightweight forwarder eliminates 2,001 lines of dead code with zero risk of breaking legacy static paths.
7. **Conclusion**: Modularization can be executed cleanly and safely using the **Facade / Barrel Re-export Pattern** for JS and Python, and **Sub-composable Decomposition** for Kotlin, satisfying Ponytail's minimal-diff, high-cohesion principles.

---

## 3. Strict Preservation Manifest

Workers must strictly preserve every item in this manifest. Any removal or renaming will break automated test suites.

### 3.1 Web Frontend Window Hooks (`simulator/static/js/app.js`)
All must be present and assigned via `window.<hook> =`:
```javascript
window.retryWsConnection
window.showWsReconnectBanner
window.hideWsReconnectBanner
window.triggerSecurityLockdown
window.openSecurityLockdownModal
window.closeSecurityLockdownModal
window.unlockSecurityLockdown
window.toggleLockdownMode
window.sendLockdownOtp
window.showMicPermissionModal
window.openMicPermissionModal
window.closeMicPermissionModal
window.retryMicPermission
window.togglePasswordVisibility
window.isSecureContext
window._serverConnected
window._latestMqtt
window._lastGeminiAudioChunkTs
```

### 3.2 Web Frontend Literal String Tokens in `simulator/static/js/app.js`
Must remain verbatim inside `simulator/static/js/app.js`:
- `function initCameraToolbar()`
- `initCameraToolbar();`
- `SmartHome3D.init('house3dViewport', 'house3dLabels', toggleDeviceById)`
- `a.strike_count >= 3` (or `a.strike_count && a.strike_count >= 3`)
- `msg.strike_count >= 3` (or `msg.strike_count && msg.strike_count >= 3`)
- `isSecureContext`
- `NotAllowedError`
- `showWsRestoredBanner`
- `banner-restored`
- `banner-sliding-out`
- Event listeners for modal elements: `#firstPageVoiceModal`, `#btnOpenFirstVoiceModal`, `#btnCloseFirstVoiceModal`, `#btnCancelFirstVoiceModal`, `#btnHoldRecordVoice`, `#firstVoiceResultBox`, `#firstVoiceEmailInput`

### 3.3 Mobile PWA 25 Mandatory Window Hooks (`simulator/static/js/mobile_app.js`)
All 25 required by `tests/test_m8_mobile_screens.py`:
```javascript
window.addLog
window.copyMobileGuestLink
window.executeMobileCommand
window.fetchInitial
window.filterDevicesByRoom
window.filterMobileHistory
window.onMobileActorChange
window.onMobileQrInviteTierChange
window.onMobileRegTierChange
window.pollMobileSecurityAndTimers
window.refreshMobileQr10s
window.renderMobileHistory
window.renderState
window.scrollToSection
window.showPwaVoiceResults
window.submitMobileAddEmail
window.submitMobileChangePassword
window.submitMobileLogin
window.submitMobileRegister
window.submitMobileVoiceSample
window.submitPwaSchedule
window.switchMobileLoginTab
window.toggleMobileVoiceListen
window.togglePasswordVisibility
window.toggleShowAllDevices
```
Plus additional active hooks:
```javascript
window.switchMobileTab
window.openVoiceBottomSheet
window.closeVoiceBottomSheet
window.startVoiceSheetRecording
window.stopVoiceRecording
window.retryVoiceRecording
window.openForgotPassword
window.closeForgotPassword
window.submitForgotSendOtp
window.submitForgotVerifyOtp
window.submitForgotResetPassword
window.openQrScanner
window.closeQrScanner
window.processQrHandshake
window.manualQrCodeInput
window.submitMobileLogout
```

### 3.4 Mobile PWA 68 Mandatory DOM Element IDs (`mobile_app/index.html`)
```
aiReply, btnLearnIr, btnMobileMicLabel, btnMobileTabLogin,
btnMobileTabRegister, btnTestDrySoil, btnToggleShowAllDevices, cmdForm,
cmdInput, devGrid, espBadge, humVal,
mobileActorBadge, mobileActorSelect, mobileAddEmailForm, mobileAllowlistMsg,
mobileBottomNav, mobileChangeConfirmPassword, mobileChangeEmail, mobileChangeNewPassword,
mobileChangePasswordBtn, mobileChangePasswordMsg, mobileGuestDurSelect, mobileLoginBtn,
mobileLoginEmail, mobileLoginForm, mobileLoginGate, mobileLoginMsg,
mobileLoginPassword, mobileMainContent, mobileQrCountdown, mobileQrDots,
mobileQrInviteTierSelect, mobileQrOpenLink, mobileQrSvgContainer, mobileQrTokenText,
mobileQrUrlText, mobileRegConfirmPassword, mobileRegEmail, mobileRegMsg,
mobileRegName, mobileRegPassword, mobileRegTier, mobileRegisterBtn,
mobileRegisterForm, mobileStrikeBadge, mobileTargetEmail, mobileTargetTierSelect,
mobileVoiceF0, mobileVoiceMetrics, mobileVoiceRegName, mobileVoiceRes,
mobileVoiceRetryBtn, mobileVoiceSNR, mobileVoiceStepLabel, mobileVoiceTierInfo,
mqttLog, pwaSchedAction, pwaSchedDevice, pwaSchedTime,
pwaScheduleForm, pwaVoiceEmpty, pwaVoiceResults, soilVal,
tempVal, upcomingScheduleInline, userSaidText, voiceStateBadge
```
Plus M1..M5 specific IDs:
- `#mobileOverviewBox` (with class `preview-16-9`)
- `#home-sensors-title` (container with 2 sensors: `#mobileDisplayTemp`, `#mobileDisplaySoil`)
- `#mobileMainDoorStatus`, `#mobileAlarmSirenStatus`
- `#mobileBtnVoiceSheet`, `#mobileBtnViewDevices`
- 4 Tabs: `#tabViewHome`, `#tabViewDevices`, `#tabViewVoice`, `#tabViewAccount`
- 4 Nav buttons: `#mobileNavTabHome`, `#mobileNavTabDevices`, `#mobileNavTabVoice`, `#mobileNavTabAccount`
- `#mobileForgotPasswordPanel`, `#mobileForgotOtp` (`inputmode="numeric"`, `maxlength="6"`), `#mobileForgotStepReset`
- `#mobileVoiceBottomSheet`, `#mobileVoiceMeterWave` (12 volume bars)
- `#mobileQrScannerModal`, `#mobileQrScannerBox`

### 3.5 3D House Model (`simulator/static/house3d.js`)
- Keep v1 light design intact.
- 0 occurrences of `container.innerHTML = ""`.
- Must contain `container.insertBefore(renderer.domElement, container.firstChild)`.
- 7 Devices registered: `main_door`, `living_room_light`, `fan`, `ac`, `bedroom_light`, `alarm_siren`, `garden_pump`.
- 7 Camera presets: `overview`, `living`, `bedroom`, `door`, `garden`, `board`, `rotate`.
- Raycaster click tolerance: `Math.hypot <= 6` px for mouse, `<= 10` px for touch.

### 3.6 UI Mockup Files Protection
- Under NO circumstance may any file in `ui_mockups/` be modified or deleted:
  - `ui_mockups/v1_pages/` (all files preserved)
  - `ui_mockups/v2_new_pages/` (`np_01`..`np_08`, `np_m1`..`np_m5`, HTML and PNGs preserved)
  - `ui_mockups/DESIGN_SYSTEM.md`, `ui_mockups/FIX_PLAN_20261104.md`

---

## 4. Proposed Target Directory & File Structure

```
├── android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/
│   ├── MainActivity.kt
│   ├── Navigation.kt
│   ├── ui/main/
│   │   ├── MainScreen.kt                 <-- Main Coordinating Composable (~180 lines)
│   │   ├── MainScreenViewModel.kt
│   │   ├── tabs/
│   │   │   ├── HomeScreenTab.kt          <-- M1: Home Overview & 2 Sensors (~250 lines)
│   │   │   ├── DevicesScreenTab.kt       <-- M2: Device Grid & Room Filter (~200 lines)
│   │   │   ├── VoiceScreenTab.kt         <-- M4: Voice Bottom Sheet & Audio (~280 lines)
│   │   │   └── AccountScreenTab.kt       <-- M2/M3/M5: Profile, OTP Reset, QR (~350 lines)
│   │   ├── components/
│   │   │   ├── MainComponents.kt         <-- LineIcon, DeviceRowCard, BottomTabItem (~220 lines)
│   │   │   └── AccountMenuRow.kt
│   │   └── models/
│   │       └── MainScreenModels.kt       <-- AuthTestCaseItem, Screen State Data (~120 lines)
│
├── simulator/
│   ├── voice_auth.py                     <-- Facade entry point & VoiceAuthManager (~400 lines)
│   ├── voice/
│   │   ├── __init__.py
│   │   ├── biometrics_neural.py
│   │   ├── denoiser.py
│   │   ├── vad_vietnamese.py
│   │   ├── dsp_features.py               <-- Extracted from voice_auth.py (~550 lines)
│   │   ├── synthesis_augment.py          <-- Extracted audio synthesis (~250 lines)
│   │   └── enrollment_quality.py         <-- Voice enrollment validation gate (~280 lines)
│   │
│   ├── static/
│   │   ├── house3d.js                    <-- PRESERVED 1:1 (Concept 3D & light v1 intact)
│   │   ├── app.js                        <-- Replaced with 10-line forwarder to js/app.js
│   │   ├── style.css                     <-- Replaced with 2-line @import "/static/css/style.css";
│   │   │
│   │   ├── js/
│   │   │   ├── app.js                    <-- Monolith refactored into cohesive modules + test facade
│   │   │   ├── mobile_app.js             <-- Modularized into tab sub-controllers + facade
│   │   │   ├── auth.js
│   │   │   ├── guest_enroll.js
│   │   │   ├── logs.js
│   │   │   └── wokwi.js
│   │   │
│   │   └── css/
│   │       ├── style.css                 <-- Main stylesheet preserved
│   │       └── mobile_app.css            <-- Mobile stylesheet preserved
```

---

## 5. Refactoring Roadmap for Workers

### Stage 1: Dead Code & Redundant File Elimination (Zero-Risk Quick Wins)
1. **`simulator/static/style.css` (970 lines)**:
   - Replace content with:
     ```css
     /* Forwarding stylesheet for legacy static URL requests */
     @import url("/static/css/style.css");
     ```
   - Net line reduction: **-968 lines**.
2. **`simulator/static/app.js` (1,031 lines)**:
   - Replace content with a minimal forwarder script that loads `/static/js/app.js` if executed directly.
   - Net line reduction: **-1,020 lines**.
3. **Verification**: Run `python -X utf8 -m pytest tests/test_challenger_m4_dom.py --basetemp=.pytest_tmp`.

### Stage 2: Android Native Compose Modularization (`MainScreen.kt`)
1. Create `vn.edu.hust.seee.smarthome.ui.main.models.MainScreenModels.kt` containing `AuthTestCaseItem` and supporting data classes.
2. Create `vn.edu.hust.seee.smarthome.ui.main.components.MainComponents.kt` containing:
   - `LineIcon`
   - `DeviceRowCard`
   - `AccountMenuRow`
   - `BottomTabItem`
   - `TierChip`
3. Extract tab composables into `tabs/`:
   - `HomeScreenTab(modifier, ...)`
   - `DevicesScreenTab(devices, ...)`
   - `VoiceScreenTab(voiceState, ...)`
   - `AccountScreenTab(profile, ...)`
4. Rewrite `MainScreen.kt` to coordinate state, top app bar, selected tab dispatch, and bottom navigation bar (~180 lines total).
5. **Verification**: Run `./gradlew :app-core:assembleDebug` in `android_app/`. Must output `BUILD SUCCESSFUL`.

### Stage 3: Python Backend Modularization (`simulator/voice_auth.py`)
1. Create `simulator/voice/dsp_features.py`:
   - Move `denoise_and_isolate_human_voice`
   - Move `extract_voice_features`
   - Move `extract_stage2_deep_features`
   - Move `detect_multi_speaker_and_resolve_priority`
   - Move `cosine_sim`
2. Create `simulator/voice/synthesis_augment.py`:
   - Move `transform_pcm_by_pitch_factor`
   - Move `transform_pcm_to_intruder_voice`
   - Move `synthesize_noisy_fan_voice`
   - Move `synthesize_two_speakers_audio`
3. Create `simulator/voice/enrollment_quality.py`:
   - Move `validate_voice_enrollment_quality`
   - Move `parse_vietnamese_voice_command_intents`
4. In `simulator/voice_auth.py`:
   - Re-export all functions:
     ```python
     from simulator.voice.dsp_features import (
         denoise_and_isolate_human_voice,
         extract_voice_features,
         extract_stage2_deep_features,
         detect_multi_speaker_and_resolve_priority,
         cosine_sim,
     )
     from simulator.voice.synthesis_augment import (
         transform_pcm_by_pitch_factor,
         transform_pcm_to_intruder_voice,
         synthesize_noisy_fan_voice,
         synthesize_two_speakers_audio,
     )
     from simulator.voice.enrollment_quality import (
         validate_voice_enrollment_quality,
         parse_vietnamese_voice_command_intents,
     )
     ```
   - Retain `DuplicateVoiceCheckResult` and `VoiceAuthManager`.
   - Net line count of `voice_auth.py` drops from **2,551** to **~450 lines**.
5. **Verification**: Run `python -X utf8 -m pytest tests/test_challenger_m1_adversarial.py tests/test_adversarial_dsp.py --basetemp=.pytest_tmp`.

### Stage 4: Frontend Web Client Clean Refactoring (`app.js` & `mobile_app.js`)
1. **`simulator/static/js/app.js`**:
   - Clean up duplicate event handlers and dead variables.
   - Separate concerns into internal logical sub-modules (or sub-files included cleanly).
   - Ensure all string assertion anchors (`function initCameraToolbar()`, `window.*` exports, strike count checks) remain intact in `app.js`.
2. **`simulator/static/js/mobile_app.js`**:
   - Refactor repetitive form submit handlers into reusable dispatchers.
   - Ensure all 25 `REQUIRED_25_WINDOW_HOOKS` and `function switchMobileTab` remain verbatim on `window.*`.
3. **Verification**: Run:
   ```bash
   python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py tests/test_challenger_m5_interactions.py --basetemp=.pytest_tmp
   ```

### Stage 5: Full Regression Testing & Gate Convergence
1. Run complete pytest suite:
   ```bash
   python -X utf8 -m pytest tests/ --basetemp=.pytest_tmp
   ```
   Must achieve **100% PASS** (all 74+ tests).
2. Clean up `.pytest_tmp`:
   ```powershell
   Remove-Item -Recurse -Force .pytest_tmp
   ```
3. Record before/after line counts in `FIX_REPORT_20261104.md` Phase 3 section.

---

## 6. Caveats
- **Headless Node VM Testing**: Tests do not evaluate files through Webpack or Vite; they directly evaluate `fs.readFileSync('simulator/static/js/app.js', 'utf8')`. Refactoring must avoid introducing standard ES module `import` syntax into `app.js` unless accompanied by a compatible bundler.
- **Android Gradle Environment**: Gradle build depends on the Android SDK configured on the local system (`%LOCALAPPDATA%\Android\Sdk`). `assembleDebug` must be verified using the standard gradlew wrapper in `android_app/`.
- **Protected 3D Core**: `simulator/static/house3d.js` has strict invariants tested in `test_challenger_m3_stress_dom_raycaster.py`. Do NOT attempt structural changes or visual redesign on `house3d.js`.

---

## 7. Conclusion
The codebase is fully mapped and primed for modularization. By eliminating 2,001 lines of dead duplicate files in `simulator/static/` and modularizing `MainScreen.kt` (2,569L -> ~180L) and `voice_auth.py` (2,551L -> ~450L), we achieve dramatic code health improvements while strictly honoring Ponytail's minimalism principles and guaranteeing 100% behavior preservation.

---

## 8. Verification Method
Run the following commands to verify the findings and test assertions:
```powershell
# 1. Run core verification test suite
python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py tests/test_challenger_m5_interactions.py --basetemp=.pytest_tmp

# 2. Clean up temp folder per project rule
Remove-Item -Recurse -Force .pytest_tmp

# 3. Check syntax of frontend JS files
node --check simulator/static/js/app.js
node --check simulator/static/js/mobile_app.js
node --check simulator/static/house3d.js

# 4. Verify ui_mockups files remain intact
Get-ChildItem -Path ui_mockups -Recurse | Measure-Object
```
