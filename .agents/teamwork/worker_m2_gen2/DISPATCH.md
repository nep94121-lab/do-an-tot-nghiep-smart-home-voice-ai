# Task Assignment: Worker Milestone 2 Replacement (UI Overhaul Core)

You are teamwork_worker / worker_m2_gen2.
Working directory: C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\worker_m2_gen2\
Project Scope: C:\Users\LENOVO\datn-wt\ui\PROJECT.md
Original Request: C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\ORIGINAL_REQUEST.md
Survey 1 Handoff: C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\explorer_survey_1\handoff.md
Survey 2 Handoff: C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\explorer_survey_2_gen2\handoff.md
Survey 3 Handoff: C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\explorer_survey_3_gen2\handoff.md

## Scope & File Ownership
You exclusively own and may edit/create:
1. `simulator/static/index.html`:
   - Login Gate modal (`#homeLoginGateModal`): Show only email, password, login button, small "Quên mật khẩu?" and "Đăng ký" links. Wrap legacy tab bars (`#btnTabGateLogin`, `#btnTabGateRegister`, `#btnTabGateForgot`) and legacy panels in hidden wrappers (`style="display:none;" hidden`), preserving all DOM IDs and empty static `value=""`. Keep `#btnCloseLoginGateModal` with static `hidden` attribute.
   - Reorganize `.top` header into 2 distinct rows:
     - Row 1: `<h1>Tổng quan</h1>` and connection status (`#btnToggleServer`, `#connDot`, `#connText`, `#homeServerStatusBadge`, `<details class="menu">`).
     - Row 2: `#homeCurrentAccountBadge`, `#homeSessionDurationBadge`, and Logout (`#btnLogoutHome`).
2. `simulator/static/css/style.css`:
   - Two-row layout for `.top` header.
   - Account email ellipsis truncation on `#homeCurrentAccountBadge` (`max-width: 165px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;`).
   - Mobile responsive styles for 360px-460px viewports (`@media (max-width: 700px)` and `@media (max-width: 480px)`).
   - Compact 3D chips (`.pin-3d`: font-size 10px, padding 2.5px 7px, gap 3px on mobile).
3. `simulator/static/js/house3d.js`:
   - Enhance `updatePinPositions()`:
     1. Boundary clamping: Clamp raw coordinates within `[pad + halfW, w - pad - halfW]` and `[pad + halfH, h - pad - halfH]`.
     2. Multi-pass collision relaxation (3 passes) repelling overlapping visible pins along Y/X axes.
     3. Maintain all static code invariants: `el.dataset.hasValue = "false";`, `el.style.display = "none";`, `<strong class="pin-state"></strong>`, `stateVal`, `pin.dataset.hasValue = "false"`, `pin.dataset.hasValue = "true"`, `hasValue`, `stSpan`.
4. `mobile_app/index.html` & `simulator/static/js/mobile_app.js`:
   - Minimalist login gate: Wrap legacy tabs (`#btnMobileTabLogin`, `#btnMobileTabRegister`) in hidden wrapper, displaying only email, password, login button, and links.
   - In `simulator/static/js/mobile_app.js`:
     - In `renderState(snap)`: Attach `data-device-id="${d.id}"` to device cards and update DOM in-place without wiping (`grid.innerHTML = ''`).
     - Implement 2500ms `pendingDeviceMutations` guard window: Ignore stale polling snapshots for devices toggled within 2500ms.
     - Implement optimistic instant toggle (<16ms frame) in `toggleDev(devId)`.
5. `simulator/static/auth.html` & `simulator/static/js/auth.js`:
   - Streamline `/auth` Step 1 (`#stepPanel1`) to exactly 3 visible input fields: `<select id="enrollTierSelect">`, `<input id="enrollSpeakerNameInput">`, `<input id="loginEmail">`.
   - Wrap password inputs (`#loginPassword`, `#loginPasswordConfirm`) and presets/OTP in hidden wrapper (`style="display:none;" hidden`) with empty static `value=""`.
   - In `simulator/static/js/auth.js`: Ensure fallback password `'123456'` allows advancing smoothly.
6. `FIX_REPORT_20261104.md`:
   - Create Playwright latency measurement script measuring before/after DOM toggle latency in milliseconds and record results in `FIX_REPORT_20261104.md`.

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Constraints
- Forbidden files: NEVER touch `simulator/voice/**`, `simulator/voice_auth.py`, `simulator/live/**`.
- 100% POSIX LF line endings (0 CRLF) and UTF-8 without BOM.
- Purity: 0 `<style>` tags, 0 inline `<script>` tags across all HTML files.
- Run tests (`pytest tests/test_milestone_m1_navigation_routing.py`, `pytest tests/test_phase5_r4_house3d_overlay.py`, `pytest tests/test_challenger_m3_stress_dom_raycaster.py`, `pytest tests/test_challenger_m4_dom.py`, `pytest tests/test_challenger_m2_gate_ux_empirical.py`, `pytest tests/test_challenger_m4_security.py`) and verify Exit Code 0.

Document your changes, verification commands, and test results in:
`C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\worker_m2_gen2\handoff.md`
When done, send a message to parent.
