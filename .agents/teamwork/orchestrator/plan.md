# Orchestration Plan - Phase 6: OTP Email Deliverability & System Hardening

## Overview
Phase 6 focuses on resolving OTP deliverability issues, spam filtering, test isolation, anti-double-send cooldown, and end-to-end verification for the Smart Home Voice AI system on branch `p6-otp`.

## Pattern
Project Pattern with Survey Phase, Decomposition, and Iteration Loops (Explorer -> Worker -> Reviewer -> Challenger -> Forensic Auditor).

## Phases & Milestones

### Phase 0: Parallel Survey (Exploration & Requirement Mapping)
- **Explorer 1**: R1 Email Allowlist & Test Isolation mapping (`tests/conftest.py`, SMTP/GWS mocks, login gate `send_gmail=False`, test fixtures `accounts_3layer.json`, `family_email_allowlist.json`).
- **Explorer 2**: R2 Anti-Double-Send Cooldown & Trigger Fixes (`simulator/api/routes_auth.py`, 60s cooldown & idempotency, frontend form listeners `#btnSubmitGateLogin`, `gatePanel*`, button `inFlight`/`disabled` states).
- **Explorer 3**: R3 RFC 5322 Compliance & Deliverability (`formataddr`, Date, Message-ID, Reply-To, subject sanitization, multipart text+HTML, zero emojis, update `read_latest_otp_from_gmail_inbox`).
- **Synthesis**: Consolidate findings into `PROJECT.md § Feature Inventory` and define milestone interface contracts.

### Phase 1: M1 - Email Allowlist and Test Isolation
- Strict 3-tier protection for `REAL_EMAIL_ALLOWLIST` (`nep94121@gmail.com`, `senat6031@gmail.com`, `kbanh376@gmail.com`).
- Autouse pytest fixture mocking SMTP and GWS subprocess calls.
- Login gate `/` and Playwright 3-roles test flows set to `send_gmail=False`.
- Clean seed accounts in test fixtures.

### Phase 2: M2 - Anti-Double-Send Cooldown and Trigger Fixes
- 60s backend cooldown and idempotency preserving active OTP.
- Frontend event listener deduplication for form submit & button clicks.
- `inFlight` and `disabled` state management for submit buttons.

### Phase 3: M3 - Email RFC 5322 Standards & Deliverability
- Full RFC 5322 email headers (`From`, `Date`, `Message-ID`, `Reply-To`).
- Clean subject line (no OTP, no ALL-CAPS, no emojis).
- MIME multipart alternative (text/plain + clean HTML, no Google OAuth branding, no emojis).
- Update inbox scraper `read_latest_otp_from_gmail_inbox`.

### Phase 4: M4 - TDD Verification, Single Real Verification Email, and Deployment
- Complete pytest & Playwright test run with 100% mocked isolation.
- Exactly zero or at most one real verification email to `senat6031@gmail.com`.
- No secret leak check.
- Git commit on branch `p6-otp`, push to `origin/p6-otp` (NO master push).
- Vercel preview deployment (strictly NO `--prod`).
- Document report in `FIX_REPORT_20261104.md`.
