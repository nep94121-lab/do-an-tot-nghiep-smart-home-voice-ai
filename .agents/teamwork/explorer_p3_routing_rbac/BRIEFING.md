# BRIEFING — 2026-11-04T15:17:45Z

## Mission
Investigate Phase 3 Requirements R1 (Vercel Production Routing) and R2 (Session-based RBAC Security) and provide concrete implementation designs and test strategies in a self-contained handoff report.

## 🔒 My Identity
- Archetype: teamwork_explorer
- Roles: explorer, analyst, investigator
- Working directory: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\explorer_p3_routing_rbac\
- Original parent: 39d935a1-0551-429d-ac45-c89f1e361ad0
- Milestone: Phase 3 Investigation R1 & R2

## 🔒 Key Constraints
- Read-only investigation — do NOT implement or modify source code.
- Report all findings and proposals strictly in `.agents/teamwork/explorer_p3_routing_rbac/handoff.md`.
- Communicate completion and updates back to parent using `send_message`.

## Current Parent
- Conversation ID: 39d935a1-0551-429d-ac45-c89f1e361ad0
- Updated: 2026-11-04T15:15:57Z

## Investigation State
- **Explored paths**:
  - `vercel.json` (route tables, rewrite rules, headers)
  - `api/index.py` (serverless entrypoint)
  - `simulator/server.py` (FastAPI route definitions, static mounts, 404/500 content negotiation)
  - `simulator/api/routes_devices.py` (`api_control_device`, `api_mobile_schedule`, `api_text_command`, `api_set_session_role`)
  - `simulator/rule_engine.py` (`execute_device_action`, `emit`, `check_device_permission`)
  - `simulator/engine/voice_rbac_mixin.py` (`current_tier`, `_current_user_id`, `check_device_permission`, `check_permission`)
  - `simulator/api/routes_auth.py` (`layer1_login`, `layer2_verify_otp`, `layer3_voice`, cookie setting)
  - `simulator/auth/` (`ThreeLayerAuthManager`, `sessions`, `constants_and_crypto.py`, `qr_totp_mixin.py`)
  - Live production endpoints on `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`
- **Key findings**:
  1. Live curl probe proved: `/mobile`, `/architecture`, `/offline`, `/404`, `/403`, `/500`, `/qr_expired`, `/sw.js` all return Vercel raw 404 NOT_FOUND. The production deployment is 4 hours stale (before commit `26e7afa`), and `vercel.json` lacked `/mobile` redirect, `/architecture` route, and custom 404 fallback catch-all.
  2. RBAC concurrency vulnerability: `_REST_ENGINE` is a global singleton. When any user logs in, `set_active_user` overwrites `_current_user_id` globally. Concurrent requests from different sessions read `_REST_ENGINE.current_tier`, causing permission leakage (guests opening doors) or denial of service (owner blocked).
  3. Cookies `sh_session_tier` and `sh_session_user` are generated in `routes_auth.py` but never read in `routes_devices.py`.
- **Unexplored areas**: None within the R1/R2 investigation scope.

## Key Decisions Made
- Formulate exact `vercel.json` rewrites and redirects for R1, as well as FastAPI routes in `simulator/server.py`.
- Formulate session store architecture and parameterization of `RuleEngine.execute_device_action(..., request_tier=...)` to decouple execution from singleton state.
- Formulate 4-part concurrent test suite verifying zero cross-session permission leakage across 3 roles.

## Artifact Index
- `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\explorer_p3_routing_rbac\handoff.md` — Technical handoff report for R1 & R2
- `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\explorer_p3_routing_rbac\progress.md` — Liveness & progress tracking
- `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\explorer_p3_routing_rbac\DISPATCH.md` — Inbound instructions log
