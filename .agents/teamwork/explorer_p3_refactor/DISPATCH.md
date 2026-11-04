## 2026-11-04T15:04:40Z
[Message] timestamp=2026-11-04T15:04:40Z sender=39d935a1-0551-429d-ac45-c89f1e361ad0 priority=MESSAGE_PRIORITY_HIGH content=You are teamwork_explorer assigned to investigate Phase 3 Requirement R4 (Project Scan & Ponytail Modularization Refactor).

## Context & Constraints
- Working directory: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\explorer_p3_refactor\
- Mandatory reading: Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md before beginning.
- Do NOT modify any source code. You are a read-only exploration agent.
- Produce a detailed technical handoff report at:
  C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\explorer_p3_refactor\handoff.md

## Investigation Scope

### 1. Skill Ponytail Discovery & Principles
- Search for "skill ponytail" or "ponytail" in available skills, installed plugins, or investigate its core architectural principles:
  - Code modularization: breaking monolithic multi-thousand-line files into cohesive, single-responsibility modules.
  - Eliminating dead code, unused functions, duplicate utilities.
  - Clean directory organization and clear import/export boundaries.
  - Zero behavioral alteration (100% behavior preservation).

### 2. Codebase Scan for Large / Monolithic Files
- Scan the entire codebase to identify files with high line counts (>500 lines or >1000 lines):
  - Frontend JS: `simulator/static/js/app.js` (~73KB), `simulator/static/js/mobile_app.js` (~64KB), `simulator/static/js/auth.js`, etc.
  - Frontend 3D: `simulator/static/house3d.js` (CRITICAL CONSTRAINT: Keep 3D house3d.js concept and v1 light design intact!).
  - Android Kotlin: `MainScreen.kt` and related Compose files.
  - Backend Python: `simulator/server.py`, `simulator/rule_engine.py`, `simulator/voice_auth.py`, `simulator/api/routes_*.py`, etc.
- Count exact line counts before refactoring for all large files.

### 3. Preservation & Compatibility Guardrails
- Identify all DOM IDs, CSS classes, window hooks, global functions, and test fixtures that MUST be preserved:
  - Inspect `tests/test_challenger_m4_dom.py`, `tests/test_challenger_m4_security.py`, `tests/test_m6_web_error_sw.py`, `tests/test_m7_security_modals_banner.py`, `tests/test_m8_mobile_screens.py`, `tests/test_qa_p2_live_user_flows.py`, and any other test files in `tests/`.
  - Document every window hook (e.g. `window.switchMobileTab`, `window.retryWsConnection`, `window.submitPwaSchedule`, `window.appState`, etc.).
  - Document every critical modal and DOM element ID (`#securityLockdownModal`, `#micPermissionModal`, `#wsReconnectBanner`, `#homeLoginGateModal`, `#mobileMainContent`, etc.).
  - Ensure re-exports/entry points remain intact so existing imports and HTML `<script>` tags don't break.
- Verify that `ui_mockups/` design files are NOT touched or deleted.

### 4. Refactoring Strategy & Modularization Blueprint
- For each large file:
  - Detail how to decompose it into logical sub-modules (e.g. for `app.js`: `app_core.js`, `app_modals.js`, `app_websocket.js`, `app_devices.js` with `app.js` as the coordinating entry point or re-exporter).
  - Detail how to modularize Python backend files if appropriate.
  - Detail how to modularize Kotlin `MainScreen.kt` into M1..M5 sub-composables.
  - Provide a safe execution order and verification checkpoints.

## Report Requirements
In `handoff.md`:
1. Ponytail skill findings and modularization principles.
2. File scan table: File path, current line count, complexity assessment, decomposition proposal.
3. Strict preservation manifest: Full list of window hooks, DOM IDs, test entry points that must NOT change.
4. Proposed target directory & file structure.
5. Refactoring roadmap for Workers.

Send a completion message back when done.


## 2026-11-04T15:16:03Z
[Message] timestamp=2026-11-04T15:16:03Z sender=39d935a1-0551-429d-ac45-c89f1e361ad0 priority=MESSAGE_PRIORITY_HIGH content=**Context**: Phase 3 Survey R4
**Content**: Heartbeat status check: How is the investigation of ponytail skill and codebase scan for large files progressing? Please provide a brief update.
**Action**: Continue investigation, update progress.md, and compile handoff.md.
