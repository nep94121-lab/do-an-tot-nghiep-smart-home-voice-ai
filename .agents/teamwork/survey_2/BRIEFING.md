# BRIEFING — 2026-11-04T06:14:00Z

## Mission
Khảo sát Kỹ thuật (Survey Phase 0) - Mảng 2: Login Gate & Password UX & 3D Model DOM/Raycaster.

## 🔒 My Identity
- Archetype: explorer
- Roles: Teamwork explorer (read-only investigation, analysis, structured synthesis)
- Working directory: c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\survey_2
- Original parent: cb4be64f-6f73-4e8f-b499-50863e4051dc
- Milestone: Phase 0 Technical Survey

## 🔒 Key Constraints
- Read-only investigation — do NOT modify system source code during survey
- Write only to .agents/teamwork/survey_2/
- Output 100% Tiếng Việt, súc tích, bằng chứng xác thực (file paths, line numbers, snippets, tests)
- Produce self-contained handoff.md with 5 components (Observation, Logic Chain, Caveats, Conclusion, Verification Method)

## Current Parent
- Conversation ID: cb4be64f-6f73-4e8f-b499-50863e4051dc
- Updated: 2026-11-04T06:14:00Z

## Investigation State
- **Explored paths**:
  - `simulator/static/index.html` (lines 80-92, 223-317)
  - `simulator/static/js/app.js` (lines 1200-1454)
  - `simulator/static/js/auth.js` (lines 1-180)
  - `mobile_app/index.html` (lines 1-331)
  - `simulator/static/js/mobile_app.js` (lines 1-110)
  - `simulator/static/house3d.js` (lines 130-220, 461-750, 1180-1310, 1640-1652)
  - `simulator/static/css/style.css` (lines 405-465)
  - `simulator/auth_3layer.py` (lines 435-480, 577-605)
  - `simulator/api/routes_auth.py` (lines 565-605)
  - `simulator/data/accounts_3layer.json` (lines 1-35)
  - `tests/test_challenger_m4_dom.py` (36 passed)
  - `tests/e2e/test_all_36_project_flows.py` (36 passed)
- **Key findings**:
  1. `#homeLoginGateModal`: Close button `#btnCloseLoginGateModal` is active even when unauthenticated; user can bypass gate. Panels are `<div>` instead of `<form>` (no Enter submit); eye toggle 👁️ missing.
  2. `auth.js` lines 56 & 60: `readOnly = true` locks name/email when tier 1 is chosen.
  3. `mobile_app/index.html`: SVG `<symbol>` sprite at line 39 is trapped inside `<div id="mobileMainContent" hidden>`, making `#i-home` in `#mobileLoginGate` invisible before login.
  4. `house3d.js` line 179: `container.innerHTML = ""` destroys `#house3dLabels` and `.viewport-note`, detaching `.pin-3d` buttons from live DOM.
  5. `style.css` line 441: `.pin-3d .pin-icon { display: none !important; }` hides emojis/icons, line 445 hides sensor pins.
  6. Camera presets: `house3d.js` has `setCameraView` with 7 presets implemented and exported, but `index.html` lacks UI buttons and `app.js` lacks listeners.
  7. `THREE.Raycaster`: completely missing; needs mouse drag vs click discrimination (threshold 6px) to toggle 7 devices on click.
- **Unexplored areas**: None for Phase 0 Survey Mảng 2.

## Key Decisions Made
- Formulated precise code diff proposals and exact architectural designs for all 7 issues.
- Proceeding to write comprehensive `handoff.md`.

## Artifact Index
- DISPATCH.md — Parent task dispatch record
- BRIEFING.md — Persistent context & state
- progress.md — Liveness heartbeat
- handoff.md — Final 5-component technical survey report
