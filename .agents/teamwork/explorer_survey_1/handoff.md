# HANDOFF REPORT — EXPLORER SURVEY 1 (R1, R4, R5)

**Date**: 2026-11-05T04:27:00Z
**Agent**: teamwork_spec_miner / explorer_survey_1
**Working Directory**: `C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\explorer_survey_1\`
**Target File**: `C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\explorer_survey_1\handoff.md`
**Parent Agent**: `e7340628-f79a-4027-966a-f5d6b40bf426`

---

## 1. Observation

### 1.1. Codebase Layout & Routing Configuration
- **Server Entrypoint**: [`simulator/server.py`](file:///C:/Users/LENOVO/datn-wt/ui/simulator/server.py)
  - Lines 137–173 serve static HTML endpoints:
    - Line 137: `@app.get("/") -> FileResponse(STATIC_DIR / "index.html")`
    - Line 142: `@app.get("/app") -> FileResponse(MOBILE_APP_DIR / "index.html")`
    - Line 147: `@app.get("/mobile") -> RedirectResponse(url="/app", status_code=307)`
    - Line 153: `@app.get("/wokwi") -> FileResponse(STATIC_DIR / "wokwi.html")`
    - Line 158: `@app.get("/logs") -> FileResponse(STATIC_DIR / "logs.html")`
    - Line 163: `@app.get("/auth") -> FileResponse(STATIC_DIR / "auth.html")`
    - Line 168: `@app.get("/guest_enroll")` and `@app.get("/guest-qr") -> FileResponse(STATIC_DIR / "guest_enroll.html")`
  - **Absence**: There are currently **NO** `@app.get("/login")` and **NO** `@app.get("/register")` route handlers. Any browser request to `/login` or `/register` triggers the custom 404 handler (lines 101–113) returning `404.html`.
- **Vercel Routing**: [`vercel.json`](file:///C:/Users/LENOVO/datn-wt/ui/vercel.json)
  - Lines 15–38 define routing rules:
    - Line 26: `{ "src": "^/app/?$", "dest": "/mobile_app/index.html" }`
    - Line 27: `{ "src": "^/auth/?$", "dest": "/simulator/static/auth.html" }`
    - Line 28: `{ "src": "^/guest_enroll/?$", "dest": "/simulator/static/guest_enroll.html" }`
    - Line 30: `{ "src": "^/logs/?$", "dest": "/simulator/static/logs.html" }`
    - Line 31: `{ "src": "^/wokwi/?$", "dest": "/simulator/static/wokwi.html" }`
    - Line 36: `{ "src": "^/$", "dest": "/simulator/static/index.html" }`
    - Line 37: `{ "src": "^/(.*)$", "status": 404, "dest": "/simulator/static/404.html" }` (Catch-all)
  - **Absence**: Currently **NO** rule exists for `/login` or `/register`. Any request to `/login` falls through to line 37 returning HTTP 404.

### 1.2. Requirement R1: Login & Register Flow
- **Web Desktop Login Gate**: [`simulator/static/index.html`](file:///C:/Users/LENOVO/datn-wt/ui/simulator/static/index.html)
  - Lines 276–405 contain `#homeLoginGateModal`:
    - Lines 289–293: Tab buttons:
      - `#btnTabGateLogin` ("1. Đăng nhập")
      - `#btnTabGateRegister` ("2. Đặt / Đổi mật khẩu")
      - `#btnTabGateForgot` ("3. Quên mật khẩu (OTP)")
    - Lines 295–311: Form `#gatePanelLogin`:
      - `#gateLoginEmail`
      - `#gateLoginPassword`
      - `#btnSubmitGateLogin`
    - Lines 313–348: Form `#gatePanelRegister`:
      - `#gateRegTier`, `#gateRegName`, `#gateRegEmail`, `#gateRegPassword`, `#gateRegConfirmPassword`, `#btnSubmitGateRegister`
    - Lines 350–399: Form `#gatePanelForgot`:
      - `#gateForgotStep1`, `#gateForgotEmail`, `#btnSendForgotOtp`, `#btnGoForgotStep2`
      - `#gateForgotStep2`, `#gateForgotOtpInput`, `#btnBackForgotStep1`, `#btnGoForgotStep3`
      - `#gateForgotStep3`, `#gateForgotNewPassword`, `#gateForgotConfirmPassword`, `#btnBackForgotStep2`, `#btnSubmitForgotReset`
    - Line 401: `#gateStatusBox`
  - JavaScript controller: [`simulator/static/js/app.js`](file:///C:/Users/LENOVO/datn-wt/ui/simulator/static/js/app.js)
    - Lines 1524–1735 manage `#homeLoginGateModal`, `switchLoginGateTab`, session validation in `localStorage['smarthome_auth_session']`, and submit handlers.
- **Mobile PWA Login Gate**: [`mobile_app/index.html`](file:///C:/Users/LENOVO/datn-wt/ui/mobile_app/index.html)
  - Lines 31–159 contain `#mobileLoginGate`:
    - Lines 40–43: Tab buttons: `#btnMobileTabLogin`, `#btnMobileTabRegister`
    - Lines 45–63: Form `#mobileLoginForm` with `#mobileLoginEmail`, `#mobileLoginPassword`, `#btnMobileForgotPassword`, `#mobileLoginBtn`
    - Lines 65–99: Form `#mobileRegisterForm` with `#mobileRegTier`, `#mobileRegName`, `#mobileRegEmail`, `#mobileRegPassword`, `#mobileRegConfirmPassword`, `#mobileRegisterBtn`
    - Lines 101–157: Panel `#mobileForgotPasswordPanel`
  - JavaScript controller: [`simulator/static/js/mobile_app.js`](file:///C:/Users/LENOVO/datn-wt/ui/simulator/static/js/mobile_app.js)
    - Lines 38–140 manage `submitMobileLogin`, `switchMobileLoginTab`, `onMobileRegTierChange`, `submitMobileRegister`.
- **Backend Authentication Endpoints**: [`simulator/api/routes_auth.py`](file:///C:/Users/LENOVO/datn-wt/ui/simulator/api/routes_auth.py)
  - Line 527: `POST /api/auth3/layer1_login` (Accepts `email`, `password`, `login_method`, `source`, `send_gmail`. Returns session object, sets `sh_session_token` cookie).
  - Line 626: `POST /api/auth3/register_or_set_password` (Accepts `email`, `password`, `confirm_password`, `display_name`, `target_tier`, `source`. Validates 100% password confirmation).
  - Line 653: `POST /api/auth3/forgot_password_send_otp`
  - Line 667: `POST /api/auth3/forgot_password_reset`

### 1.3. Requirement R4: Voice Auth Setup Simplification
- **Current Page Structure**: [`simulator/static/auth.html`](file:///C:/Users/LENOVO/datn-wt/ui/simulator/static/auth.html)
  - Lines 94–161: Step 1 panel (`#stepPanel1`):
    - Line 106: `<select id="enrollTierSelect">` (Cấp 1, Cấp 2, Cấp 3) — **Field 1: Fixed permission level**
    - Line 115: `<input id="enrollSpeakerNameInput">` — **Field 2: Full name**
    - Line 121: `<input id="loginEmail">` — **Field 3: Email**
    - Lines 124–126: `<input id="loginPassword">`, `<input id="loginPasswordConfirm">` — **Must be hidden from interface**
    - Lines 134–159: `<details>` with `#accountPresetSelect`, `#otpInput`, OTP buttons — **Must be hidden from setup interface**
  - Lines 163–230: Step 2 panel (`#stepPanel2`):
    - Microphone recording: `#btnHoldToRecordFirstPage`, `#btnRetryVoiceStep2`, `#firstPageAccountSelect`, `#step2SpeakerNameInput`
  - Lines 232–323: Step 3 panel (`#stepPanel3`):
    - Confirmation: `#step3SummaryName`, `#step3SummaryTier`, `#step3SummaryEmail`, `#step3SummaryVoiceStatus`, `#btnConfirmStep3Voice`
- **JavaScript Behavior**: [`simulator/static/js/auth.js`](file:///C:/Users/LENOVO/datn-wt/ui/simulator/static/js/auth.js)
  - Lines 109–170 (`completeStep1AndGoToVoice`):
    - Lines 116–118:
      ```javascript
      const email = emailEl ? emailEl.value.trim() : 'nep94121@gmail.com';
      const password = pwEl ? pwEl.value : '123456';
      const confirmPassword = pwConfirmEl ? pwConfirmEl.value : password;
      ```
    - Password already has a reliable fallback to `'123456'` if elements are empty or default. Hiding password inputs in HTML does not break functionality when default/preserved values are maintained.

### 1.4. Requirement R5: Shared Navigation Across All Static Pages
- **Current Sidebar Navigation**:
  - [`simulator/static/index.html`](file:///C:/Users/LENOVO/datn-wt/ui/simulator/static/index.html#L30-L46)
  - [`simulator/static/auth.html`](file:///C:/Users/LENOVO/datn-wt/ui/simulator/static/auth.html#L46-L62)
  - [`simulator/static/wokwi.html`](file:///C:/Users/LENOVO/datn-wt/ui/simulator/static/wokwi.html#L22-L37)
  - [`simulator/static/logs.html`](file:///C:/Users/LENOVO/datn-wt/ui/simulator/static/logs.html#L21-L39)
  - [`simulator/static/guest_enroll.html`](file:///C:/Users/LENOVO/datn-wt/ui/simulator/static/guest_enroll.html#L17-L23) (currently only top header links to `/auth` and `/`)
- **Required Link Set**:
  1. Overview: `/`
  2. Voice Auth: `/auth`
  3. Hardware: `/wokwi`
  4. Logs: `/logs`
  5. App: `/app`
  6. Guest: `/guest_enroll`
  7. Login: `/login`
  8. Register: `/register`

### 1.5. Verification Suite & Invariant Tests
- **DOM & Security Verification**:
  - [`tests/test_challenger_m4_security.py`](file:///C:/Users/LENOVO/datn-wt/ui/tests/test_challenger_m4_security.py):
    - Lines 371–417: Verifies HTTP 200 and Content-Type across all 18 static routes.
    - Lines 418–448: **STRICT PURITY**: Asserts that all 6 HTML files (`index.html`, `auth.html`, `guest_enroll.html`, `wokwi.html`, `logs.html`, `mobile_app/index.html`) contain **0 `<style>` tags** and **0 inline `<script>` tags** (scripts must use `<script src="...">`).
    - Verified: `test_challenger_m4_security.py` passes 48/48 tests when `GEMINI_API_KEY` is present.
  - [`tests/test_challenger_m2_gate_ux_empirical.py`](file:///C:/Users/LENOVO/datn-wt/ui/tests/test_challenger_m2_gate_ux_empirical.py):
    - Lines 40–69: Enforces 100% POSIX LF line endings (`\n`, 0 CRLF) and UTF-8 without BOM across all frontend files.
    - Lines 98–104: Requires `#btnCloseLoginGateModal` to have the static `hidden` attribute in `index.html`.
    - Lines 164–172: Verifies presence of DOM IDs in Node VM: `#btnTabGateLogin`, `#btnTabGateRegister`, `#btnTabGateForgot`, `#btnSubmitGateLogin`, `#btnSubmitGateRegister`, `#btnSubmitForgotReset`, `#gateLoginEmail`, `#gateLoginPassword`, `#gateRegTier`, `#gateRegName`, `#gateRegEmail`, `#gateRegPassword`, `#gateRegConfirmPassword`, `#gateForgotEmail`, `#gateForgotOtpInput`, `#gateForgotNewPassword`, `#gateForgotConfirmPassword`.
  - [`tests/test_p4_survey1_security_auth.py`](file:///C:/Users/LENOVO/datn-wt/ui/tests/test_p4_survey1_security_auth.py):
    - Lines 68–73: Asserts all `input[type="password"]` have an empty string `value=""` in static HTML (no hardcoded password in HTML).
    - Lines 75–91: Asserts all credential inputs have empty `value=""`.
    - Lines 93–95: Asserts no prohibited password hint strings appear in HTML.
    - Lines 388–400: Asserts `#enrollSpeakerNameInput` has empty `value=""` in `auth.html`.
  - [`tests/test_challenger_m11_vercel_routing.py`](file:///C:/Users/LENOVO/datn-wt/ui/tests/test_challenger_m11_vercel_routing.py):
    - Validates `vercel.json` schema, regexes, route precedence, trailing slashes, and catch-all 404 behavior.

---

## 2. Logic Chain

1. **R1 Analysis & Logic**:
   - *Premise*: User requests dedicated `/login` and `/register` pages with minimalist design, and simplifying Login Gate on `/` and `/app` to show only email, password, login button, and small "Quên mật khẩu?" and "Đăng ký" links.
   - *Observation*: Multiple existing adversarial tests (`test_challenger_m2_gate_ux_empirical.py`, `test_adversarial_m1_challenger.py`, `test_p4_survey1_security_auth.py`) parse the HTML AST or execute Node.js VM scripts querying `#btnTabGateLogin`, `#btnTabGateRegister`, `#btnTabGateForgot`, `#gateRegPassword`, `#gateRegConfirmPassword`, etc.
   - *Deduction*: Deleting these elements from HTML would break backward test compatibility and fail the test suite. Therefore, the legacy tabs and registration/forgot form panels on `/` and `/app` must remain physically present in the DOM with their exact IDs, but wrapped in a container hidden via `display: none;` or `hidden` attribute. The visible interface on `/login`, `/`, and `/app` will display exclusively: email input, password input, login button, and small text links for "Quên mật khẩu?" and "Đăng ký".
   - *Dedicated Pages*: `simulator/static/login.html` and `simulator/static/register.html` must be created following `DESIGN_SYSTEM.md` (Be Vietnam Pro, `--page: #f5f7f7`, `--card: #fff`, `--accent: #087d85`), using external CSS and JS with 0 inline styles and 0 inline scripts.

2. **R4 Analysis & Logic**:
   - *Premise*: User requests streamlining `/auth` setup to exactly 3 input fields: fixed permission level, full name, and email; removing username, password, and microphone options from the interface while preserving DOM IDs for backward test compatibility.
   - *Observation*: In `simulator/static/auth.html` Step 1 (`#stepPanel1`), there are currently: `enrollTierSelect` (fixed permission level), `enrollSpeakerNameInput` (full name), `loginEmail` (email), `loginPassword`, `loginPasswordConfirm`, and details for presets/OTP. In `auth.js`, `completeStep1AndGoToVoice` checks `password` and falls back to `'123456'`. In `test_p4_survey1_security_auth.py`, `input[type="password"]` must have empty `value=""` in static HTML.
   - *Deduction*: By hiding the password container (`#loginPassword`, `#loginPasswordConfirm`) and preset/OTP options with `style="display:none;"` while leaving `value=""` intact on static HTML, the visible interface is reduced to exactly 3 input fields (`enrollTierSelect`, `enrollSpeakerNameInput`, `loginEmail`). If the user submits, `auth.js` can supply `'123456'` if the password inputs are left blank, ensuring `POST /api/auth3/register_or_set_password` succeeds seamlessly without prompt friction.

3. **R5 Analysis & Logic**:
   - *Premise*: User requests a shared simple navigation bar across all static pages linking 8 routes: Overview (`/`), Voice Auth (`/auth`), Hardware (`/wokwi`), Logs (`/logs`), App (`/app`), Guest (`/guest_enroll`), Login (`/login`), Register (`/register`).
   - *Observation*: `simulator/server.py` and `vercel.json` currently do not map `/login` and `/register`. In addition, `guest_enroll.html` lacks full sidebar navigation, while `index.html`, `auth.html`, `wokwi.html`, `logs.html` have sidebar links that do not yet include `/login` and `/register`.
   - *Deduction*:
     a. Routes for `/login` and `/register` must be registered in `simulator/server.py` (`@app.get("/login")`, `@app.get("/register")`) and in `vercel.json` (placed before the catch-all `^/(.*)$`).
     b. A unified shared navigation structure containing all 8 destinations must be standardized across all static pages (`index.html`, `auth.html`, `wokwi.html`, `logs.html`, `guest_enroll.html`, `login.html`, `register.html`, and `mobile_app/index.html`).
     c. Each page marks its own link with `class="active"` and `aria-current="page"`.

---

## 3. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Routing (R1, R5) | GET `/login` | Serves dedicated minimalist login page | HTTP GET `/login` | `FileResponse("simulator/static/login.html")` | 404 if missing in `server.py` / `vercel.json` | `ORIGINAL_REQUEST.md`, `server.py:137-173` |
| 2 | Routing (R1, R5) | GET `/register` | Serves dedicated minimalist register page | HTTP GET `/register` | `FileResponse("simulator/static/register.html")` | 404 if missing in `server.py` / `vercel.json` | `ORIGINAL_REQUEST.md`, `server.py:137-173` |
| 3 | Auth UI (R1) | Minimalist Login Interface | Displays only email, password, login button, "Quên mật khẩu?", "Đăng ký" | `email`, `password` | Authentication session & cookie | Error message in status box; credentials cleared on retry | `ORIGINAL_REQUEST.md`, `index.html:276-405`, `mobile_app/index.html:31-63` |
| 4 | Backward Comp (R1) | Legacy Gate Tabs Preservation | Legacy tabs (`btnTabGateLogin`, `btnTabGateRegister`, `btnTabGateForgot`, `btnMobileTabLogin`, `btnMobileTabRegister`) preserved in DOM with hidden container | Click or test dispatch | Switched form panel | No error, transparent to user, accessible to test scripts | `test_challenger_m2_gate_ux_empirical.py:165-172` |
| 5 | Voice Setup (R4) | Streamlined 3-Field Auth Setup | `/auth` Step 1 displays exactly 3 fields: permission tier, full name, email | `enrollTierSelect`, `enrollSpeakerNameInput`, `loginEmail` | Advanced to Step 2 (voice recording) | Validation error if name or email empty | `ORIGINAL_REQUEST.md`, `auth.html:94-161` |
| 6 | Backward Comp (R4) | Hidden Credential Inputs in `/auth` | Password inputs (`loginPassword`, `loginPasswordConfirm`) hidden in DOM with empty static `value=""` | None required from user | Handled gracefully in `auth.js` | Validation errors masked from user | `test_p4_survey1_security_auth.py:68-91` |
| 7 | Navigation (R5) | 8-Destination Shared Navigation | Unified nav linking `/`, `/auth`, `/wokwi`, `/logs`, `/app`, `/guest_enroll`, `/login`, `/register` across all static pages | User navigation click | Direct page transition | Trailing slash normalized, active state styled | `ORIGINAL_REQUEST.md`, `vercel.json:15-38` |
| 8 | Security (Global) | Zero Inline Styles & Scripts | Enforces 100% external CSS and JS files for all HTML pages | Static HTML inspection | 0 `<style>`, 0 inline `<script>` | `test_challenger_m4_security.py` assertion failure | `test_challenger_m4_security.py:418-448` |
| 9 | Formatting (Global) | 0 CRLF & UTF-8 without BOM | Enforces strict POSIX LF line endings and standard UTF-8 across all repository files | Byte sequence inspection | `\n` only, 0 `\r\n` | `test_challenger_m2_gate_ux_empirical.py` failure | `test_challenger_m2_gate_ux_empirical.py:43-69` |

---

## 4. Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | Vercel Routing | Trailing slashes `/login/` and `/register/` | Without regex anchors `/?$`, trailing slashes will fail or mismatch. Must use `^/login/?$` and `^/register/?$` in `vercel.json`. |
| 2 | Static Password Value | Non-empty `value="123456"` on password inputs | Triggers immediate assertion failure in `test_p4_survey1_security_auth.py:72` (`assert not val`). Static HTML `value` attribute MUST be empty string `""`. |
| 3 | Login Gate Close Button | `#btnCloseLoginGateModal` without static `hidden` attribute | Triggers assertion failure in `test_challenger_m2_gate_ux_empirical.py:98-103`. The `hidden` attribute MUST be present on the button element in static HTML. |
| 4 | Mobile Navigation Safe Area | Mobile viewport with bottom toolbar (Samsung Internet / Safari) | Bottom nav bar can overlap or get covered. Must maintain `min-height: 100dvh`, `padding-bottom: max(6px, env(safe-area-inset-bottom))`. |
| 5 | Dual Password Confirmation | Mismatched password and confirm password on `/register` | Handled by `POST /api/auth3/register_or_set_password` returning HTTP 400 with `"Hai ô mật khẩu không khớp nhau"`. |
| 6 | Inline Scripts in HTML | Any `<script>` tag without `src` attribute | Triggers failure in `test_challenger_m4_security.py:445` (`assert len(inline_scripts) == 0`). All JS functions must be housed in `.js` files. |

---

## 5. Caveats

1. **Read-Only Investigation**: As instructed by the Specification Miner role and mission constraints, no code modifications were made during this turn.
2. **External DevTools Tests**: `tests/test_challenger_m5_devtools.py` requires an active live server process on port 8088. This test is intended for full live orchestration and does not impact static routing/DOM audits.
3. **Gemini API Key in Background Tests**: WebSocket tests in `test_challenger_m4_security.py` require `GEMINI_API_KEY` in the environment to avoid Google GenAI client initialization exceptions. Verified: when `GEMINI_API_KEY` is provided, 48/48 tests pass cleanly.

---

## 6. Conclusion & Implementation Recommendations

1. **For R1 (Login & Register Redesign)**:
   - Create `simulator/static/login.html` and `simulator/static/register.html` adhering to `DESIGN_SYSTEM.md` tokens (teal `--accent: #087d85`, background `--page: #f5f7f7`, card `--card: #fff`, Be Vietnam Pro typography).
   - In `simulator/static/index.html` (`#homeLoginGateModal`) and `mobile_app/index.html` (`#mobileLoginGate`):
     - Wrap legacy tab button containers in a `style="display:none;"` wrapper, preserving all original DOM IDs (`#btnTabGateLogin`, `#btnTabGateRegister`, `#btnTabGateForgot`, `#btnMobileTabLogin`, `#btnMobileTabRegister`).
     - Present only the email input, password input, primary login button, and small text links for "Quên mật khẩu?" and "Đăng ký".
     - Keep legacy form fields (`#gateRegPassword`, `#gateRegConfirmPassword`, etc.) in hidden DOM panels with empty initial `value=""`.
   - Register GET `/login` and GET `/register` in `simulator/server.py` and `vercel.json`.

2. **For R4 (Voice Auth Setup Simplification)**:
   - In `simulator/static/auth.html` Step 1 (`#stepPanel1`):
     - Visually expose exactly 3 fields: `<select id="enrollTierSelect">`, `<input id="enrollSpeakerNameInput">`, `<input id="loginEmail">`.
     - Move `#loginPassword`, `#loginPasswordConfirm`, and details for presets/OTP into a hidden wrapper (`<div style="display:none;" hidden>`), keeping empty `value=""` in static HTML.
     - Ensure `simulator/static/js/auth.js` (`completeStep1AndGoToVoice`) uses `'123456'` as fallback if hidden password inputs are empty, allowing seamless enrollment.
     - Retain all existing step indicators, buttons, and summary elements for 100% backward test compatibility.

3. **For R5 (Shared Navigation Across All Pages)**:
   - Standardize a shared navigation component containing all 8 links (`/`, `/auth`, `/wokwi`, `/logs`, `/app`, `/guest_enroll`, `/login`, `/register`) across:
     - `simulator/static/index.html`
     - `simulator/static/auth.html`
     - `simulator/static/wokwi.html`
     - `simulator/static/logs.html`
     - `simulator/static/guest_enroll.html`
     - `simulator/static/login.html`
     - `simulator/static/register.html`
     - `mobile_app/index.html`
   - In `simulator/server.py`: Add `@app.get("/login")` and `@app.get("/register")` returning `FileResponse`.
   - In `vercel.json`: Add regex route rules for `/login` and `/register` immediately preceding the catch-all rule.
   - Maintain 0 CRLF and 0 inline scripts on all modified and newly created files.

---

## 7. Verification Method

To verify the implementation once applied:
```powershell
# 1. Verify static file cleanliness (0 inline styles, 0 inline scripts, 18 routes)
pytest tests/test_challenger_m4_security.py -v

# 2. Verify DOM and event integrity across all pages
pytest tests/test_challenger_m4_dom.py -v

# 3. Verify Vercel routing, regexes, and file existence
pytest tests/test_challenger_m11_vercel_routing.py -v

# 4. Verify Login Gate UX, bypass resistance, and 0 CRLF
pytest tests/test_challenger_m2_gate_ux_empirical.py -v

# 5. Verify security rules, password hint masking, and credential cleanliness
pytest tests/test_p4_survey1_security_auth.py -v

# 6. Verify line endings strictly 0 CRLF across git worktree
git status
git diff --check
```
