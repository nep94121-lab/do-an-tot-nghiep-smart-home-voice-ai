## 2026-11-05T06:19:30Z
You are Worker M2 (worker_m2), archetype teamwork_worker.
Your working directory is: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\worker_m2
You MUST read ORIGINAL_REQUEST.md at: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\ORIGINAL_REQUEST.md before starting work.
Read Explorer 2's detailed survey report and implementation recipes:
- Report: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\explorer_survey_2\survey_report.md
- Handoff: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\explorer_survey_2\handoff.md
Read SCOPE.md at: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\orchestrator\SCOPE.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

File Ownership:
You own exclusively for this milestone:
- simulator/auth_3layer.py
- simulator/api/routes_auth.py
- simulator/static/js/app.js
- simulator/static/index.html
- tests/test_phase6_r2_cooldown_triggers.py

Mission: Implement Milestone 2 (R2 Anti-Double-Send Cooldown & Trigger Fixes)
1. TDD First:
   Create tests/test_phase6_r2_cooldown_triggers.py verifying:
   - Subsequent OTP requests for the same recipient within 60s return idempotent status (idempotent=True, cooldown_active=True), do NOT dispatch duplicate emails, and preserve the active OTP code.
   - OTP requested after 60s or expired OTP generates a new OTP and dispatches.
   - Once reset_password_with_otp succeeds, the consumed OTP is destroyed and cannot be reused.
   - Concurrency: multiple simultaneous requests for the same recipient do not trigger multiple email dispatches (thread safety).
   - Frontend static checks: verify elimination of form submit -> button.click() double-triggers and presence of inFlight/disabled handling on submit and OTP buttons.
2. Backend Implementation:
   In simulator/auth_3layer.py:
   - Add thread-safe lock: self._otp_lock = threading.Lock() in ThreeLayerAuthManager.__init__.
   - In request_password_reset_otp(self, email: str, send_gmail: bool = True, source: str = "..."):
     Acquire self._otp_lock. Check if existing pending OTP exists for clean_email = email.strip().lower() and (time.time() - existing["created_at"]) < 60.0.
     If within 60s cooldown:
       Do NOT generate new OTP code, do NOT call send_real_gmail_otp.
       Return HTTP 200 payload with:
         ok=True,
         idempotent=True,
         cooldown_active=True,
         cooldown_remaining_seconds=int(60.0 - (time.time() - existing["created_at"])),
         email=clean_email,
         message="Mã OTP đã được gửi trước đó. Vui lòng kiểm tra hộp thư hoặc thử lại sau.",
         otp_code_for_test=existing["otp_code"],
         demo_otp_preview=existing["otp_code"],
         expires_in=int(existing["expires_at"] - time.time())
     If elapsed >= 60.0 or no existing pending OTP:
       Generate new OTP, dispatch email, record pending_otps.
   - In reset_password_with_otp:
     When password reset succeeds, destroy the consumed OTP: self.pending_otps.pop(clean_email, None).
3. Frontend Implementation:
   In simulator/static/js/app.js:
   - Lines 1711–1728: REMOVE the conflicting form submit listeners that call button.click() (`if (btnSubmitGateLogin) btnSubmitGateLogin.click();`, etc.).
   - Unify form submission logic directly into form `submit` event listeners for `#gatePanelLogin`, `#gatePanelRegister`, `#gatePanelForgot`.
   - On `#btnSubmitGateLogin`, `#btnSubmitGateRegister`, `#btnSubmitForgotReset`, `#btnSendForgotOtp`:
     Add inFlight flags and disabled state:
     `btn.disabled = true;`
     in try ... finally: `btn.disabled = false;`
   - On `#btnSendForgotOtp`:
     When OTP request succeeds, implement a 60-second visual countdown timer (`setInterval(..., 1000)`), disabling the button and displaying `Gửi lại sau (${remaining}s)`. Re-enable after 60 seconds.
   In simulator/static/index.html:
   - Ensure form tags `#gatePanelLogin`, `#gatePanelRegister`, `#gatePanelForgot`, `#lockdownForm` have proper submit behavior without inline event handlers calling button click.
4. Run Verification:
   - Run: pytest tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py tests/test_phase5_r3_otp_email.py -v
   - Ensure all tests pass with Exit Code 0.
   - DO NOT read, write, print, or log any SMTP secrets.

Write your handoff report to:
C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\worker_m2\handoff.md
Notify the orchestrator via send_message when complete.
