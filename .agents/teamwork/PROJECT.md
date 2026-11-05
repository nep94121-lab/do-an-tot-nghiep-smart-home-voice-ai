# Project: Smart Home Voice AI — Phase 7 UI Overhaul

## Architecture
- **Web Frontend**: Fast HTML5/CSS/JavaScript with Three.js 3D house model visualization (`simulator/static/`).
- **Mobile PWA**: Responsive PWA interface (`mobile_app/index.html`, `simulator/static/js/mobile_app.js`).
- **Backend Server**: FastAPI HTTP/WebSocket application (`simulator/server.py`, `simulator/api/routes_auth.py`).
- **Deployment Platform**: Vercel Static & Serverless (`vercel.json`).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Dedicated GET `/login` | Serves light minimalist login page (`simulator/static/login.html`) | M1 | Survey 1, ORIGINAL_REQUEST §R1 |
| 2 | Dedicated GET `/register` | Serves light minimalist register page (`simulator/static/register.html`) | M1 | Survey 1, ORIGINAL_REQUEST §R1 |
| 3 | Shared 8-Route Navigation | Standardized navigation linking `/`, `/auth`, `/wokwi`, `/logs`, `/app`, `/guest_enroll`, `/login`, `/register` across all pages | M1 | Survey 1, ORIGINAL_REQUEST §R5 |
| 4 | Routing Config in Server & Vercel | Add `/login` and `/register` route handlers in `simulator/server.py` and regex rules in `vercel.json` | M1 | Survey 1, ORIGINAL_REQUEST §R5 |
| 5 | Minimalist Login Gate Redesign | Show only email, password, login button, small "Quên mật khẩu?" and "Đăng ký" on `/` and `/app` | M2 | Survey 1, ORIGINAL_REQUEST §R1 |
| 6 | Backward Test Compatibility for Gate | Hide legacy tab bar and form panels in DOM wrappers while preserving all DOM IDs and empty static `value=""` | M2 | Survey 1, ORIGINAL_REQUEST §R1 |
| 7 | Streamlined Voice Auth Setup | Simplify `/auth` Step 1 to exactly 3 visible fields (tier, full name, email); hide passwords and mic options | M2 | Survey 1, ORIGINAL_REQUEST §R4 |
| 8 | Mobile Header 2-Row Layout | Reorganize `.top` header into Row 1 (Overview + status) and Row 2 (Badge + Quota + Logout) | M2 | Survey 2, ORIGINAL_REQUEST §R2 |
| 9 | Email Ellipsis Truncation | Truncate account email on `#homeCurrentAccountBadge` with ellipsis to eliminate overlaps | M2 | Survey 2, ORIGINAL_REQUEST §R2 |
| 10 | 3D Chips Collision Repulsion | Multi-pass relaxation algorithm to repel overlapping 3D device labels in Three.js | M2 | Survey 2, ORIGINAL_REQUEST §R2 |
| 11 | 3D Chips Boundary Clamping | Clamp 3D label projection coordinates within viewport boundaries with safe margins | M2 | Survey 2, ORIGINAL_REQUEST §R2 |
| 12 | Reduced Font Size on Mobile 3D | Compact 3D label font and padding for 360-460px mobile viewports | M2 | Survey 2, ORIGINAL_REQUEST §R2 |
| 13 | Optimistic UI on `/app` | Instant in-place DOM updates (<16ms) on device toggle buttons using `data-device-id` | M2 | Survey 3, ORIGINAL_REQUEST §R3 |
| 14 | Pending Mutations Guard Window | 2500ms guard window (`pendingDeviceMutations`) preventing background poll flicker | M2 | Survey 3, ORIGINAL_REQUEST §R3 |
| 15 | Latency Benchmarking Script | Playwright Chromium script measuring before/after DOM latency in ms recorded in `FIX_REPORT_20261104.md` | M2 | Survey 3, ORIGINAL_REQUEST §R3 |
| 16 | E2E Testing Suite (Tiers 1-4) | Comprehensive opaque-box test suite verifying all routes, viewports, and interactions | M3 | E2E Track, ORIGINAL_REQUEST §Verification |
| 17 | Adversarial Hardening (Tier 5) | White-box stress testing, zero inline scripts/styles check, 0 CRLF validation | M3 | Challenger / Security Suite |
| 18 | Git Rebase & Remote Push | Rebase `p7-ui` on `origin/master`, push ONLY to remote `p7-ui` (master untouched) | M3 | ORIGINAL_REQUEST §R6 |
| 19 | Vercel Preview Deployment | Deploy preview via `npx vercel` (no `--prod`), record URL in fix report and log | M3 | ORIGINAL_REQUEST §R6 |

## Milestones
| # | Name | Scope | Dependencies | Status | Outputs |
|---|------|-------|-------------|--------|---------|
| M1 | Navigation, Routing & Dedicated Login/Register | Features 1, 2, 3, 4 | none | DONE | `simulator/server.py`, `vercel.json`, `login.html`, `register.html`, `auth_pages.js`, shared nav in 8 HTML files; 222 tests pass |
| M2 | UI Overhaul Core (Gate, Mobile 3D, Optimistic UI, Voice Setup) | Features 5 through 15 | M1 | DONE | `index.html` 2-row header, gate modal; `style.css` responsive ellipsis; `house3d.js` 3D clamping & relaxation; `mobile_app.js` optimistic UI; `auth.html` 3-field voice auth; latency 1.14ms verified; 188 tests pass |
| M3 | E2E Testing Track, Deployment & Final Audit | Features 16 through 19 | M1, M2 | IN_PROGRESS | |

## Code Layout & File Boundaries
- `simulator/server.py`: Route definitions for static HTML files.
- `vercel.json`: Static routing configuration.
- `simulator/static/login.html`: Dedicated minimalist login page.
- `simulator/static/register.html`: Dedicated minimalist register page.
- `simulator/static/js/auth_pages.js`: Client controller for dedicated login/register pages.
- `simulator/static/index.html`: Web overview, 2-row header, 3D house viewport, login gate modal.
- `simulator/static/css/style.css`: Styles for desktop and mobile responsive layout.
- `simulator/static/js/house3d.js`: Three.js 3D model, boundary clamping, collision repulsion.
- `simulator/static/auth.html` & `simulator/static/js/auth.js`: Streamlined voice auth page.
- `mobile_app/index.html` & `simulator/static/js/mobile_app.js`: Mobile PWA optimistic device toggling.
- `FIX_REPORT_20261104.md`: Performance latency measurements and deployment logs.
- **FORBIDDEN FILES**: Do NOT touch `simulator/voice/**`, `simulator/voice_auth.py`, `simulator/live/**`.
- **ENCODING**: 100% POSIX LF line endings (`\n`, 0 CRLF) and standard UTF-8 without BOM.
- **PURITY**: Zero inline `<script>` tags and zero `<style>` tags in all HTML files.
