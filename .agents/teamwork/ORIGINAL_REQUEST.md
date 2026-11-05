# Original User Request

## Initial Request — 2026-11-05T04:14:57Z

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

## Acceptance Criteria

### Email Allowlist & Test Mocking
- [ ] Any attempt to send real email to non-allowlisted addresses (such as `thanh_vien_chuan@gmail.com`, `hoc_sinh_moi@gmail.com`, `tan_binh_gia_dinh@gmail.com`) is rejected or blocked without bounce.
- [ ] An `autouse` fixture in `tests/conftest.py` mocks `smtplib.SMTP`, `smtplib.SMTP_SSL`, and `gws` dispatches during all pytest runs.
- [ ] Login gate (`/`) dispatches login with `send_gmail: false`, and Playwright 3-roles tests run without triggering real email dispatches.
- [ ] Demo seed accounts and test fixtures in `simulator/data/accounts_3layer.json` and `simulator/data/family_email_allowlist.json` contain only clean default accounts.

### Anti-Double-Send & Idempotency
- [ ] Subsequent OTP requests for the same recipient within 60 seconds do not trigger a second email dispatch and return idempotent/cooldown status.
- [ ] Double-firing event listeners on `#btnSubmitGateLogin` and related forms (`gatePanelLogin`, `gatePanelRegister`, `gatePanelForgot`) are eliminated.
- [ ] Frontend buttons for login and OTP request show `disabled` / `inFlight` state during active network requests.

### Deliverability & RFC 5322 Compliance
- [ ] Outgoing emails have RFC 5322 compliant `From` (via `formataddr`), `Date`, `Message-ID`, and `Reply-To` headers.
- [ ] Email subject contains no OTP codes, no ALL-CAPS words, and no emojis.
- [ ] Outgoing emails are MIME multipart (`alternative`) with both `text/plain` and light-background HTML containing zero emojis and no Google OAuth branding.
- [ ] `read_latest_otp_from_gmail_inbox` successfully finds and extracts OTP codes matching the new subject format and multipart body.

### Verification & Delivery
- [ ] Pytest suite and Playwright tests pass 100% with all mocks active.
- [ ] Exactly zero or at most one real verification email is dispatched to `senat6031@gmail.com` after automated tests are green.
- [ ] No SMTP secrets or credentials are read, written, logged, or printed.
- [ ] Changes are committed on branch `p6-otp`, pushed only to `origin/p6-otp` (no master push), and deployed to Vercel preview without `--prod`.
- [ ] Vercel preview URL and Phase 6 completion details are documented in `FIX_REPORT_20261104.md`.
