# BRIEFING — 2026-11-04T13:30:00Z

## Mission
Implement security modals and banner in index.html, app.js, and style.css for Milestone M7.

## 🔒 My Identity
- Archetype: implementer
- Roles: implementer, qa
- Working directory: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m7
- Original parent: a6dd1e0f-b843-4477-96f4-146d5c9d3c58
- Milestone: M7

## 🔒 Key Constraints
- Preserve 100% of all existing DOM IDs and `window.*` hooks in `simulator/static/index.html` and `simulator/static/js/app.js`.
- Do NOT touch or alter `house3d.js` or the 3D viewport canvas/labels!
- Security Lockdown Modal (`#securityLockdownModal`): role alertdialog, aria-modal true, strictly NO 'X' button, backdrop click disabled, unlock form calling `/api/auth3/layer1_login` or OTP verification, resetting strikes.
- Microphone Permission Modal (`#micPermissionModal`): role dialog, aria-modal true, mic-off icon, retry button, open HTTPS link, close button.
- WebSocket Reconnect Banner (`#wsReconnectBanner`): role status, aria-live polite, amber warning bar fixed top, retry button calling window.retryWsConnection(), restored green state for 2s then slide out.
- Pass challenger tests (m4_dom 36/36, m3_stress 20/20) and new dedicated test file `tests/test_m7_security_modals_banner.py`.
- Integrity Mandate: real logic, no cheating/hardcoding.

## Current Parent
- Conversation ID: a6dd1e0f-b843-4477-96f4-146d5c9d3c58
- Updated: 2026-11-04T13:30:00Z

## Task Summary
- **What to build**: Security Lockdown Modal, Microphone Permission Modal, WebSocket Reconnect Banner with interactive JS logic and CSS styling in the simulator frontend.
- **Success criteria**: All modals/banners render matching mockups, state handling works properly, existing tests pass, dedicated m7 tests pass.
- **Interface contracts**: PROJECT.md
- **Code layout**: simulator/static/

## Key Decisions Made
- Added #securityLockdownModal matching np_06_lockdown.html: role alertdialog, aria-modal=true, Lucide shield-alert, no close X button, backdrop click and Escape prevention, supports Password and OTP Gmail toggle with Enter key and eye toggle, calling /api/auth3/layer1_login or /api/auth3/layer2_verify_otp, resets strikes via sendWs and turns off siren.
- Added #micPermissionModal matching np_07_mic_permission.html: role dialog, aria-modal=true, Lucide mic-off, retry button, HTTPS link button, close button. Triggered on getUserMedia error or !window.isSecureContext.
- Added #wsReconnectBanner matching np_08_ws_banner.html: role status, aria-live=polite, amber warning bar with retry counter, calls window.retryWsConnection(), restores with green banner for 2s then slides out.
- Preserved 100% of DOM IDs and window.* hooks, untouched house3d.js.
- Verified 0 CRLF (POSIX LF) and UTF-8 encoding across all modified/new files.

## Artifact Index
- DISPATCH.md
- BRIEFING.md
- progress.md
- handoff.md

## Change Tracker
- **Files modified**:
  - `simulator/static/css/style.css`: Added M7 design tokens (--redsoft, --orangesoft, --greensoft, --orange, --green) and CSS classes (.banner, .banner-restored, .banner-sliding-out, .mark.red, .eyebrow, .note.red).
  - `simulator/static/index.html`: Added #wsReconnectBanner in layout, #securityLockdownModal and #micPermissionModal.
  - `simulator/static/js/app.js`: Added WS reconnect banner state, auto-reconnect logic, triggerSecurityLockdown, showMicPermissionModal, unlock logic, window.* exports.
  - `tests/test_m7_security_modals_banner.py`: Dedicated 16 unit tests covering all components.
- **Build status**: PASS (72/72 tests pass)
- **Pending issues**: None

## Quality Status
- **Build/test result**:
  - `tests/test_challenger_m4_dom.py`: 36/36 PASS
  - `tests/test_challenger_m3_stress_dom_raycaster.py`: 20/20 PASS
  - `tests/test_m7_security_modals_banner.py`: 16/16 PASS
  - Node.js syntax & Headless VM execution: PASS
- **Lint status**: Clean, 0 CRLF
- **Tests added/modified**: `tests/test_m7_security_modals_banner.py` (16 tests)

## Loaded Skills
- None requested specifically
