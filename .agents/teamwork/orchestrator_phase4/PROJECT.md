# Project: Phase 4 Real Test Bugfix & Production Release

## Architecture
- **Backend**: FastAPI / Python modular server (`simulator/`, `simulator/api/`, `simulator/auth/`)
- **Frontend Web**: Desktop Dashboard (`simulator/static/index.html`, `app.js`, `style.css`), Logs (`logs.html`, `logs.js`), Voice Auth (`auth.html`, `auth.js`), Wokwi (`wokwi.html`, `wokwi.js`), 3D Viewport (`house3d.js`)
- **Mobile PWA**: Mobile App (`mobile_app/index.html`, `mobile_app.js`, `mobile_app.css`)
- **Android Native**: Jetpack Compose (`android_app/`)
- **Deployment**: Vercel Serverless (`vercel.json`)

## Feature Inventory
| # | Bug / Feature | Description | Milestone | Source |
|---|---------------|-------------|-----------|--------|
| 1 | Bug 1 (Security Credential Cleanup) | Remove prefilled email/password, hints on /, /app, /auth, mask passwords in /logs | M1 | REAL_TEST_BUGS_20261105.md |
| 2 | Bug 2 (Logout State Reset) | Reset form, gateStatusBox, clear session, hide logout button on / and /app | M1 | REAL_TEST_BUGS_20261105.md |
| 3 | Bug 4 (Forgot Password OTP & Seed) | Add senat6031 & kbanh376 to seed; 3-step OTP flow; send real Gmail/SMTP | M1 | REAL_TEST_BUGS_20261105.md |
| 4 | Bug 5 (Voice Auth Clean & Check Login) | Remove mock member data from wizard; fix login check for real accounts | M1 | REAL_TEST_BUGS_20261105.md |
| 5 | Bug 15 (Desktop Header Access Time) | Display access duration (#homeSessionDurationBadge): owner "Không giới hạn", family "Còn 30 ngày" | M1 | REAL_TEST_BUGS_20261105.md |
| 6 | Bug 3 (WebSocket Fallback & Banner) | Fallback to HTTP polling /api/state on Vercel; sync banner & header; add favicon.ico route | M2 | REAL_TEST_BUGS_20261105.md |
| 7 | Bug 10 (Optimistic UI & No Clip) | Optimistic toggle for devices; avoid innerHTML="" label flash; full text "Đã bật" | M2 | REAL_TEST_BUGS_20261105.md |
| 8 | Bug 11 (Mic Permission Flow & Modal) | Recording sheet waiting state; trigger timer/bars only when granted; show modal when denied | M2 | REAL_TEST_BUGS_20261105.md |
| 9 | Bug 14 (Wokwi Label Layout & Telemetry) | Fix DHT11 label overlap with buzzer; replace "Chưa có dữ liệu" with live telemetry | M2 | REAL_TEST_BUGS_20261105.md |
| 10| Bug 6 (Mobile 3D house3d Render) | Mount Three.js house3d in #mobileOverviewBox (preview-16-9) on /app | M3 | REAL_TEST_BUGS_20261105.md |
| 11| Bug 7 (Mobile 7 Devices Display) | Set showAllDevices=true to show all 7 devices on mobile Devices tab | M3 | REAL_TEST_BUGS_20261105.md |
| 12| Bug 8 (Profile Safe-Area & Countdown) | Safe-area padding for Samsung Internet / bottom nav; clear QR refresh countdown | M3 | REAL_TEST_BUGS_20261105.md |
| 13| Bug 9 (Desktop Sensor Panel & Clamp) | Add #secSensors panel on desktop /; clamp temp [0,60], humidity [0,100], soil [0,100] | M3 | REAL_TEST_BUGS_20261105.md |
| 14| Bug 12 (QR Scanner Text Deduplication) | Remove duplicate instruction text in #mobileScannerStatus | M3 | REAL_TEST_BUGS_20261105.md |
| 15| Bug 13 (Logs Pagination & Filters) | Client-side pagination (pageSize=20), date filter, load more controls in /logs | M3 | REAL_TEST_BUGS_20261105.md |
| 16| Full Suite Pytest & Playwright | Full pytest pass (0 failures), Playwright live flow tests 3 roles | M4 | ORIGINAL_REQUEST.md |
| 17| Android assembleDebug | Gradle assembleDebug with exit code 0 | M4 | ORIGINAL_REQUEST.md |
| 18| Vercel Production Deployment | Git commit/push master, Vercel deploy, live browser curl verification | M5 | ORIGINAL_REQUEST.md |
| 19| FIX_REPORT_20261104.md Phase 4 | Append Phase 4 documentation with root causes, fixes, tests, and live evidence | M5 | ORIGINAL_REQUEST.md |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Security, Auth & Session Lifecycle | Bugs 1, 2, 4, 5, 15: Credential cleanup, logout reset, OTP seed/SMTP, wizard cleanup, header duration, write_bytes LF | none | **DONE** (Gate Passed) |
| M2 | Realtime, State Synchronization & Simulation | Bugs 3, 10, 11, 14: WebSocket polling fallback, optimistic UI, mic permission flow, Wokwi layout, favicon | M1 | **DONE** (Gate Passed) |
| M3 | Mobile App, UI Layout, 3D & Logs Usability | Bugs 6, 7, 8, 9, 12, 13: 3D house3d, 7 devices, safe-area, desktop sensors, QR dedup, logs pagination | M2 | **DONE** (Gate Passed) |
| M4 | Comprehensive Multi-Role & Cross-Platform Gate | Full pytest suite, Playwright 3-roles, Android assembleDebug, Reviewer/Auditor Gate | M1, M2, M3 | **DONE** (Gate Passed) |
| M5 | Production Deployment, Live Verification & Report | Vercel deploy, live curl verification, FIX_REPORT Phase 4, Git push master | M4 | **IN_PROGRESS** |

## Interface Contracts
### Auth & Session ↔ UI
- `#homeCurrentAccountBadge` displays `👑 Cấp 1 · Chủ nhà: ...` or `Chưa đăng nhập`.
- `#homeSessionDurationBadge` displays `Không giới hạn` (Tier 1), `Còn 30 ngày` (Tier 2), or remaining validity (Tier 3); hidden on logout.
- `#gateStatusBox` cleared on logout; `#btnLogoutHome` hidden on logout when unauthenticated.
- Seed accounts: `senat6031@gmail.com` (Tier 2 family), `kbanh376@gmail.com` (Tier 3 guest) in `DEFAULT_ACCOUNTS` and `accounts_3layer.json`.
- All persistence methods use `write_bytes((payload + "\n").encode("utf-8"))` and append logs use `newline="\n"`.

### WebSocket ↔ Polling Fallback
- `fetch("/api/state")` on `ws.onclose` and periodic `pollRestStateFallback`:
  - When successful: `updateConnectionUI(true)` and `hideWsReconnectBanner()`.
  - Only when both WS and Polling fail: `updateConnectionUI(false)` and `showWsReconnectBanner()`.
- Route `/favicon.ico` mapped to `/simulator/static/favicon.ico` in `vercel.json` (valid binary ICO).
- Optimistic UI on device toggle with automatic rollback on error.
- Mic permission flow: voice sheet opens at "Đang chờ quyền mic", opens `#mobileMicPermissionModal` on rejection.
- Wokwi: DHT11 and Buzzer tags have zero overlap; `#hoverHoleInfo` renders live telemetry.

### Mobile App ↔ 3D & Devices
- `#mobileOverviewBox` contains rendered Three.js canvas using `SmartHome3D.init("mobileOverviewBox", null, ...)`.
- `#devGrid` displays all 7 devices (`main_door`, `living_room_light`, `bedroom_light`, `fan`, `ac`, `alarm_siren`, `garden_pump`).
- `#secSensors` in `index.html` displays clamped telemetry.

## Code Layout
- `simulator/static/index.html`, `simulator/static/js/app.js`, `simulator/static/css/style.css`
- `mobile_app/index.html`, `simulator/static/js/mobile_app.js`, `simulator/static/css/mobile_app.css`
- `simulator/static/auth.html`, `simulator/static/js/auth.js`
- `simulator/static/logs.html`, `simulator/static/js/logs.js`
- `simulator/static/wokwi.html`, `simulator/static/js/wokwi.js`
- `simulator/auth/constants_and_crypto.py`, `simulator/auth_3layer.py`, `simulator/data/accounts_3layer.json`
- `simulator/api/routes_auth.py`, `simulator/api/routes_logs.py`
- `vercel.json`, `simulator/static/favicon.ico`, `.gitattributes`
- `tests/test_p4_survey1_security_auth.py`, `tests/test_p4_survey2_realtime.py`, `tests/test_p4_survey3_ui_layout.py`
