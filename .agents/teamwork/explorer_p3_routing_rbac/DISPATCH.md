## 2026-11-04T15:04:37Z
**Sender**: 39d935a1-0551-429d-ac45-c89f1e361ad0
**Priority**: MESSAGE_PRIORITY_HIGH
**Task**: Investigate Phase 3 Requirements R1 (Vercel Production Routing) and R2 (Session-based RBAC Security).

### Scope
1. Vercel Production Routing (R1)
- Examine `vercel.json` and static routing.
- Domain: `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`.
- URLs `/mobile`, `/architecture`, `/offline`, `/404`, `/403`, `/500`, `/qr_expired`, `/sw.js` must work without Vercel NOT_FOUND.
- URL non-existent -> custom 404 (`404.html`).
- `/mobile` -> 307/308 redirect to `/app`.
- Formulate exact edits for `vercel.json` and server route configs.

2. Session-based RBAC Security (R2)
- Inspect existing RBAC in `simulator/api/routes_devices.py`, `simulator/rule_engine.py`, `simulator/api/routes_auth.py`, `simulator/server.py`, `simulator/auth/`.
- Analyze global state vulnerability (`_REST_ENGINE.current_tier`, overwrite on login, race conditions between concurrent sessions).
- Design robust session-based RBAC architecture (session token, memory/sqlite store, passing request_tier to rule engine / device execution, unauthenticated fallback).
- Design concurrent multi-role test cases (Owner Tier 1, Admin Tier 2, Guest Tier 3).


## 2026-11-04T15:15:57Z
**Sender**: 39d935a1-0551-429d-ac45-c89f1e361ad0
**Content**: Heartbeat status check: How is the investigation of vercel.json and session-based RBAC progressing? Please provide a brief update or let me know if you need any guidance.
**Action**: Continue investigation, update progress.md, and compile handoff.md.
