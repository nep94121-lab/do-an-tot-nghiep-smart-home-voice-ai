## 2026-11-05T05:30:37Z

Phase 6: Resolve OTP email deliverability and spam filtering issues, prevent unwanted emails to fake addresses with complete test isolation, implement anti-double-send cooldown, and verify end-to-end for the Smart Home Voice AI system.

Working directory: C:\Users\LENOVO\datn-wt\p6-otp
Integrity mode: development
The team must NOT: read, write, or print SMTP secret values; push to master; deploy to production (--prod); touch Admin bots or Desktop BA-SVD; send real emails to addresses outside REAL_EMAIL_ALLOWLIST.

## Requirements

### R1. Email Allowlist and Test Isolation
Implement a 3-tier protection system ensuring real emails are only ever sent to allowlisted addresses (`REAL_EMAIL_ALLOWLIST`: `nep94121@gmail.com`, `senat6031@gmail.com`, `kbanh376@gmail.com`, and any addresses defined in env `REAL_EMAIL_ALLOWLIST`). Enforce test isolation via an `autouse` pytest fixture in `tests/conftest.py` that mocks SMTP (`smtplib.SMTP`, `smtplib.SMTP_SSL`) and `gws` CLI subprocess dispatches. Configure the login gate on `/` and Playwright 3-roles test flows to use `send_gmail=False`. Real OTP dispatches are strictly restricted to password reset, layer-2 OTP, and user invites for allowlisted recipients; demo seed accounts and fake addresses must never receive real mail or trigger bounces.

### R2. Anti-Double-Send Cooldown and Trigger Fixes
Prevent rapid duplicate OTP dispatches. Implement a 60-second cooldown and idempotency mechanism on the backend per recipient, returning idempotent status without dispatching duplicate emails while preserving the active OTP. Fix the frontend form submit and button click double-trigger on login and OTP forms, and enforce `inFlight` / `disabled` states on submit and OTP buttons to prevent duplicate requests.

### R3. Email RFC 5322 Standards and Deliverability
Fix email formatting to comply with RFC 5322 and prevent Gmail spam filtering. Format `From` using `formataddr`, and include valid `Date`, `Message-ID`, and `Reply-To` headers. Ensure subjects do not contain OTP codes, ALL-CAPS text, or emojis. Send multipart messages containing both clean text/plain and light-background HTML (zero emojis, no deceptive Google OAuth branding). Update `read_latest_otp_from_gmail_inbox` query and extraction logic to match the new subject and message structure.

### R4. TDD Verification, Single Real Verification Email, and Deployment
Follow strict TDD: create or run reproducing tests for each issue before verifying the fix. All test suites (pytest and Playwright) must run with 100% mocked email dispatches and pass cleanly. Once all tests pass, send at most one real verification email to `senat6031@gmail.com`. Work exclusively on branch `p6-otp` in worktree `C:\Users\LENOVO\datn-wt\p6-otp`, push only `p6-otp`, deploy a Vercel preview (strictly no `--prod`), and record the preview URL and Phase 6 summary into `FIX_REPORT_20261104.md`.
