# Scope: Phase 6 - OTP Deliverability, Test Isolation, Cooldown & RFC 5322 Standards

## Architecture
- **Email Allowlist & Isolation Layer**:
  - `simulator/auth/invite_and_gmail_mixin.py`: Canonical 3-tier allowlist engine. Hardcoded `HARDCODED_REAL_EMAIL_ALLOWLIST` (`nep94121@gmail.com`, `senat6031@gmail.com`, `kbanh376@gmail.com`) + `os.environ.get("REAL_EMAIL_ALLOWLIST")`. Immediate rejection for non-allowlisted emails returning `sent_real_gmail: False, blocked_by_allowlist: True` without network calls or bounces.
  - `tests/conftest.py`: Global `autouse=True` fixture mocking `smtplib.SMTP`, `smtplib.SMTP_SSL`, and `subprocess.run(["gws", ...])` across all pytest executions.
  - `simulator/static/js/app.js`: Login gate `#btnSubmitGateLogin` explicitly sets `send_gmail: false`.
  - Clean state: `simulator/data/accounts_3layer.json` (6 default accounts) & `simulator/data/family_email_allowlist.json` (`{}`).
- **Anti-Double-Send Cooldown & Idempotency Layer**:
  - `simulator/auth_3layer.py`: `ThreeLayerAuthManager` with `threading.Lock()` tracking 60s cooldown per recipient. When `elapsed < 60`, returns HTTP 200 idempotent (`idempotent: True, cooldown_active: True`), preserves existing valid `otp_code`, prevents duplicate emails. Destroys OTP on password reset success.
  - `simulator/static/js/app.js` & `index.html`: Eliminates `submit` -> `button.click()` recursion. Unifies into single form submit handler. Manages `inFlight` / `disabled` states and 60s cooldown countdown on `#btnSendForgotOtp`.
- **RFC 5322 Compliance & Deliverability Layer**:
  - `simulator/auth/invite_and_gmail_mixin.py`: Full RFC 5322 headers (`From` formatted via `formataddr`, `Date`, `Message-ID`, `Reply-To`). Clean Title Case subjects without OTP codes, ALL-CAPS, or emojis. MIME multipart alternative (`text/plain` + light-background HTML with zero emojis and no deceptive Google OAuth branding).
  - `read_latest_otp_from_gmail_inbox`: Resilient search query `q`, Base64URL recursive part decoding, 3-tier OTP regex extraction.
- **Verification, Delivery & Preview Deployment Layer**:
  - 100% mocked automated tests (pytest & Playwright).
  - Single real verification email to `senat6031@gmail.com`.
  - Git commit & push strictly to `origin/p6-otp`.
  - Vercel preview deployment (no `--prod`).
  - Comprehensive report in `FIX_REPORT_20261104.md`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Canonical Real Email Allowlist Engine | 3-tier allowlist checking (nep94121@gmail.com, senat6031@gmail.com, kbanh376@gmail.com, env REAL_EMAIL_ALLOWLIST); reject non-allowlist cleanly without bounce | M1 | Survey Exp 1 (VERIFIED DONE) |
| 2 | Global Pytest Test Isolation Fixture | Autouse fixture in tests/conftest.py mocking smtplib.SMTP, smtplib.SMTP_SSL, and gws CLI | M1 | Survey Exp 1 (VERIFIED DONE) |
| 3 | Login Gate send_gmail=False & Playwright Isolation | Update app.js #btnSubmitGateLogin payload with send_gmail: false to prevent real email during tests | M1 | Survey Exp 1 (VERIFIED DONE) |
| 4 | Clean Seed Accounts & Family Allowlist Fixtures | Restore accounts_3layer.json to 6 default accounts and family_email_allowlist.json to empty dict | M1 | Survey Exp 1 (VERIFIED DONE) |
| 5 | Backend 60-Second Cooldown & Idempotency | Atomic 60s cooldown per recipient preserving active OTP and returning idempotent response without duplicate email dispatch | M2 | Survey Exp 2 |
| 6 | Frontend Event Listener Deduplication | Eliminate double-firing triggers from form submit -> button.click() in app.js and index.html | M2 | Survey Exp 2 |
| 7 | Frontend Button inFlight & Disabled State | Enforce inFlight flags, disabled attributes, and 60s countdown timer on submit & OTP buttons | M2 | Survey Exp 2 |
| 8 | RFC 5322 Email Headers | Include formataddr From, Date, make_msgid Message-ID, and Reply-To headers | M3 | Survey Exp 3 |
| 9 | Clean Subject Lines (No OTP, No ALL-CAPS, No Emojis) | Format subjects with Title Case, no OTP digits, no uppercase acronyms, no emoji symbols | M3 | Survey Exp 3 |
| 10 | MIME Multipart Alternative (Plain Text + Light HTML) | 2-part MIME alternative: clean text/plain + light-background HTML (0 emojis, no fake Google OAuth) | M3 | Survey Exp 3 |
| 11 | Resilient Gmail Inbox Scraper | Query q update, Base64URL parts decoding, 3-tier regex for read_latest_otp_from_gmail_inbox | M3 | Survey Exp 3 |
| 12 | 100% Mocked Pytest & Playwright Verification | Complete automated test pass with all network mocks active | M4 | Survey Exp 1-3 |
| 13 | Single Real Verification Email | Dispatch at most 1 real verification email to senat6031@gmail.com after green tests | M4 | Survey Exp 3 |
| 14 | Git Branch p6-otp & Vercel Preview Deploy | Push to origin/p6-otp only (no master push), deploy preview (no --prod), write FIX_REPORT_20261104.md | M4 | Survey Exp 1-3 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Email Allowlist & Test Isolation | Allowlist engine, tests/conftest.py autouse fixture, login gate send_gmail: false, clean seed JSON | none | DONE |
| M2 | Anti-Double-Send Cooldown & Trigger Fixes | 60s backend cooldown & idempotency preserving OTP, frontend listener deduplication, inFlight/disabled states | M1 | DONE |
| M3 | Email RFC 5322 Standards & Deliverability | RFC 5322 headers, clean subjects, multipart plain+HTML, inbox scraper upgrade, TDD assertions | M1 | DONE |
| M4 | Full Verification, Single Verification Email & Preview Deploy | Complete test pass, 1 real email to senat6031@gmail.com, zero-leak check, push origin/p6-otp, Vercel preview, FIX_REPORT_20261104.md | M1, M2, M3 | DONE |

## Interface Contracts

### M1 Contract: Email Allowlist & Test Isolation [VERIFIED DONE]
- `is_email_allowlisted_for_real_send(email: str) -> bool`:
  Returns True iff normalized email is in `HARDCODED_REAL_EMAIL_ALLOWLIST` or `REAL_EMAIL_ALLOWLIST` env var.
- `send_real_gmail_otp(...)` / `send_invite_link_via_gmail(...)`:
  If not allowlisted, return `{"sent_real_gmail": False, "blocked_by_allowlist": True, "reason": "Recipient not in REAL_EMAIL_ALLOWLIST"}` without calling SMTP/gws.
- `tests/conftest.py`:
  `@pytest.fixture(autouse=True)` intercepts `smtplib.SMTP`, `smtplib.SMTP_SSL`, and `subprocess.run` where cmd starts with `["gws", ...]`.

### M2 Contract: Cooldown & Idempotency [IN PROGRESS]
- `request_password_reset_otp(email: str, send_gmail: bool = True, source: str = "...") -> dict`:
  If `elapsed < 60.0`:
  Returns:
  ```json
  {
    "ok": true,
    "message": "Mã OTP đã được gửi trước đó. Vui lòng kiểm tra hộp thư hoặc thử lại sau 60 giây.",
    "idempotent": true,
    "cooldown_active": true,
    "cooldown_remaining_seconds": 45,
    "email": "senat6031@gmail.com",
    "otp_code_for_test": "<preserved_existing_otp>",
    "demo_otp_preview": "<preserved_existing_otp>"
  }
  ```
  Existing `otp_code` in `self.pending_otps[email]` is NOT overwritten.
- Form submit contracts:
  `gatePanelLogin`, `gatePanelRegister`, `gatePanelForgot` handlers attach ONLY to `submit` event; button `click` handlers only trigger submit if form validation passes, without calling `button.click()` recursively.

### M3 Contract: RFC 5322 & Multipart [PLANNED]
- Outgoing MIME message headers:
  - `From: "Smart Home Voice AI" <sender@domain>`
  - `Date: <RFC 2822/5322 date>`
  - `Message-ID: <<random_id>@<domain>>`
  - `Reply-To: "Smart Home Voice AI" <sender@domain>`
  - `Subject: Smart Home Voice - Mã xác thực tài khoản` (no OTP code, no ALL-CAPS words, no emojis)
- Multipart body:
  - First part: `text/plain; charset=utf-8` (zero emojis)
  - Second part: `text/html; charset=utf-8` (light background `#ffffff`/`#f8fafc`, 0 emojis, no Google OAuth branding)
- Inbox scraper:
  - `q: 'subject:"Smart Home" (xác thực OR OTP OR verification)'`
  - Base64URL recursive part decoder
  - 3-tier regex for OTP extraction

## Code Layout
- `simulator/auth/invite_and_gmail_mixin.py`: Email formatting, RFC 5322 headers, multipart construction, allowlist gate, inbox scraper.
- `simulator/auth_3layer.py`: 3-layer auth manager, 60s cooldown & idempotency logic.
- `simulator/api/routes_auth.py`: Auth endpoint routes.
- `simulator/static/index.html`: Web gate modal forms and button definitions.
- `simulator/static/js/app.js`: Web frontend form submission and button state management.
- `simulator/data/accounts_3layer.json`: 3-layer default accounts fixture (6 default accounts).
- `simulator/data/family_email_allowlist.json`: Family allowlist fixture (empty dict default).
- `tests/conftest.py`: Global autouse test isolation fixtures.
- `tests/test_phase6_r1_allowlist_isolation.py`: M1 unit and integration test suite.
- `tests/test_challenger_phase6_m1.py`: Challenger 1 evasion test suite (109 tests).
- `tests/test_challenger_phase6_m1_2.py`: Challenger 2 boundary & concurrency test suite (33 tests).
- `tests/test_phase5_r3_otp_email.py`: OTP email tests & RFC 5322 assertions.
- `tests/test_challenger_phase5_r2_r3.py`: Adversarial test suite.
- `FIX_REPORT_20261104.md`: Phase 6 completion report and Vercel preview details.
