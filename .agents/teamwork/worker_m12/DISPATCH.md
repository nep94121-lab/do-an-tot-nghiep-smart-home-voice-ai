## 2026-11-04T15:26:15Z
[Message] timestamp=2026-11-04T15:26:15Z sender=39d935a1-0551-429d-ac45-c89f1e361ad0 priority=MESSAGE_PRIORITY_HIGH content=You are teamwork_worker assigned to Milestone M12: Session-based RBAC Security & Concurrent Session Tests (Requirement R2).

## Mandatory Reading
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md before beginning.
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\explorer_p3_routing_rbac\handoff.md (specifically Section 3.2 on RBAC Session Architecture and Concurrency Test Design).

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership
You exclusively own:
- `simulator/auth/session_store.py` (new)
- `simulator/api/routes_devices.py`
- `simulator/rule_engine.py`
- `simulator/api/routes_auth.py`
- `tests/test_p3_session_rbac_concurrency.py` (new)
DO NOT modify `vercel.json`, `server.py`, or Android files.

## Detailed Tasks
1. Create `simulator/auth/session_store.py`:
   - Thread-safe / async session manager holding session tokens mapped to `{ user_id, tier, role, expires_at }`.
   - Implement methods: `create_session`, `get_session`, `revoke_session`, `cleanup_expired`.
   - Backed by memory cache and SQLite `smarthome.db` (table `user_sessions`).
2. Request Session Resolver:
   - Function `resolve_request_session(request: Request, payload: dict = None) -> SessionContext`:
     - Checks `Authorization: Bearer <token>` header.
     - Checks `X-Session-Token: <token>` header.
     - Checks Cookie `sh_session_token=<token>` or `session_token=<token>`.
     - Checks query param `token` (for guest handshake tokens).
     - If valid token found, returns session context with `tier` and `user_id`.
     - If unauthenticated, defaults to Tier 3 (Guest) or public, with `is_authenticated=False`.
3. Parameterize `RuleEngine`:
   - In `simulator/rule_engine.py`:
     - Modify `execute_device_action(self, dev_id, action, source="api", bypass_rbac=False, request_tier=None, request_user_name=None)`:
       If `request_tier` is provided, use `effective_tier = request_tier`.
       Do NOT rely on or mutate `self.current_tier`.
     - Update `check_device_permission(self, device_id, action, actor_tier=None)`:
       Allow passing `actor_tier` directly.
4. Update `routes_devices.py`:
   - In `api_control_device`, `api_text_command`, `api_mobile_schedule`:
     Resolve session using `resolve_request_session(request, payload)`.
     Pass `request_tier = session.tier` and `request_user_name = session.user_name` to `execute_device_action`.
     Reject unauthorized requests with HTTP 403 (`ok: False, rbac_blocked: True`).
5. Update `routes_auth.py`:
   - When a user logs in (Layer 1 or Layer 2 OTP), generate a `session_token`, store it in `SessionStore`, and return it in JSON and in `Set-Cookie: sh_session_token=...; Path=/; HttpOnly; SameSite=Lax`.
   - Stop overwriting `_REST_ENGINE.set_active_user` globally on HTTP login requests!
6. Automated Concurrency Test:
   - Create `tests/test_p3_session_rbac_concurrency.py`:
     - Test concurrent requests across 3 roles: Owner (Tier 1), Member/Admin (Tier 2), Guest (Tier 3).
     - Run 120 interleaved requests in parallel threads/tasks simulating simultaneous users.
     - Assert that Owner can always control doors/alarms, Member cannot control doors/alarms but can control AC/lights, Guest cannot control doors or create schedules.
     - Assert ZERO permission leakage or state corruption between sessions.
7. Build & Test Verification:
   - Run `python -X utf8 -m pytest tests/test_p3_session_rbac_concurrency.py tests/test_phase1_bugfixes_20261104.py tests/test_challenger_m4_security.py --basetemp=.pytest_tmp`.
   - Delete `.pytest_tmp` after running.
   - Verify formatting: 0 CRLF, UTF-8 without BOM.
8. Produce structured handoff report at:
   `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m12\handoff.md`
   Send a completion message back when done.
