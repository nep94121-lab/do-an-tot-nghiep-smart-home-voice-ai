# Project: Smart Home Voice AI (Đồ Án Tốt Nghiệp)

## Architecture
- **Web Frontend**: HTML5/CSS3/Vanilla JS + Three.js r128 (3D House Model) served by FastAPI & deployed to Vercel (`simulator/static/`, `mobile_app/`).
- **Mobile PWA / View**: Dedicated lightweight mobile web interface (`/app` in `mobile_app/index.html`) optimized for touch, tab navigation, and ADB mobile testing.
- **Backend Core**: FastAPI (`0.0.0.0:8088`), WebSocket `/ws`, SQLite WAL database (`simulator/data/smarthome.db`), TOTP Guest Handshake (`simulator/auth/qr_totp_mixin.py`).
- **Voice Intelligence**: 3-tier Biometric Voice Verification (Wiener filter, Mel filterbank, deep formant & acoustic embeddings), Vietnamese intent parsing (`simulator/voice_auth.py`), real voice audio samples of Sếp Nguyễn Tuấn Anh (`test_audio/`).
- **Multi-channel Connectivity**:
  1. ADB Reverse (`localhost:8088`) via USB to Samsung Galaxy S9 (`2223e8784b0c7ece`).
  2. Local LAN IP (`192.168.2.39:8088`) for Wi-Fi devices.
  3. HTTPS Tunnel (OpenSSH `localhost.run`) providing SSL/TLS public domain for mobile microphone access.
  4. Vercel Cloud Frontend (`vercel --prod --yes` via `nep94121-lab/do-an-tot-nghiep-smart-home-voice-ai`).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Vercel Deployment & Routing | Config `vercel.json` with 6 static pages, push GitHub, deploy `vercel --prod --yes` | M1 | Survey 1 |
| 2 | HTTPS Tunnel & LAN & ADB Reverse | OpenSSH `localhost.run` HTTPS tunnel + LAN IP auto-detection + ADB reverse port 8088 | M1 | Survey 1 |
| 3 | Dynamic QR Guest Link | QR code generation with HTTPS/LAN host parameter, QR channel selector | M1 | Survey 1 |
| 4 | QR TOTP Window Extension | Extend `consume_guest_handshake` window from 10s to 180s, preserve single-use replay protection | M1 | Survey 1 |
| 5 | Guest Enroll URL Token Match | Read `token` query param in `guest_enroll.js` for instant handshake | M1 | Survey 1 |
| 6 | Hardened Login Gate | Remove/hide `#btnCloseLoginGateModal` when unauthenticated, block backdrop bypass | M2 | Survey 2 |
| 7 | Unlock Input Fields | Remove `readOnly = true` in `simulator/static/js/auth.js` lines 56 & 60 | M2 | Survey 2 |
| 8 | Form Enter & Eye Password Toggle | Wrap `<form>` for Enter submit, add 👁️ toggle password on Web & Mobile | M2 | Survey 2 |
| 9 | Mobile SVG Symbol Scope Fix | Move `<svg>` sprite outside `#mobileMainContent hidden` to body in `mobile_app/index.html` | M2 | Survey 2 |
| 10 | Double Password Confirmation | Enforce 2 password fields for create/reset on Web and Mobile | M2 | Survey 2 |
| 11 | Preserve 3D DOM Labels & Note | Fix `house3d.js` line 179 to only remove canvas, keeping `#house3dLabels` & `.viewport-note` | M3 | Survey 2 |
| 12 | Display 7 Floating Pin Buttons | Remove `.pin-3d .pin-icon` display:none in `style.css`, display icon + name + ON/OFF | M3 | Survey 2 |
| 13 | 3D Camera Viewpoint Toolbar | Add 7 camera buttons (Overview, Living, Bed, Door, Garden, ESP Board, Rotate) on panel header | M3 | Survey 2 |
| 14 | THREE.Raycaster Click Actuation | Integrate Raycaster with drag vs click threshold (<=6px) to toggle devices by clicking 3D mesh | M3 | Survey 2 |
| 15 | Real Voice Biometric Execution | Verify 7 real voice commands of Sếp Tuấn Anh triggering 5 devices (door, 2 lights, fan, AC) | M4 | Survey 3 |
| 16 | ADB Mobile Testing & Screencap | Execute mobile flows on Samsung S9 via ADB, capture binary screenshots via `cmd /c`, visually verify | M4 | Survey 3 |
| 17 | Test Suite 100% Pass & E2E Verification | Fix 9 modularization/fixture tests to achieve 570/570 tests PASS (100%) and DOM challenger pass | M5 | Survey 3 |
| 18 | Web Error Pages & Offline Service Worker | Create `sw.js` (network-first, offline cache), `offline.html`, `404.html`, `500.html`, `qr_expired.html`, `403.html` matching Codex mockups | M6 | Survey P2 Web |
| 19 | FastAPI Content-Negotiation 404 Handler | Route 404: return `404.html` for browser navigations (`text/html`), retain JSON 404 for `/api/*`, serve `/sw.js` with `Service-Worker-Allowed: /` | M6 | Survey P2 Web |
| 20 | Security Lockdown Modal | Modal `#securityLockdownModal` on 3-strike voice violation, admin pass/OTP recovery, backdrop unskippable | M7 | Survey P2 Web |
| 21 | Mic Permission & WS Reconnect Banner | Modal `#micPermissionModal` (retry, HTTPS guidance) & Banner `#wsReconnectBanner` (reconnecting status, retry button, restored toast) | M7 | Survey P2 Web |
| 22 | Mobile /app 5 Screens & Tab Switcher | 5 screens (M1 Home & Sensors, M2 Account & Tabs, M3 Forgot Pass OTP, M4 Voice Bottom Sheet, M5 QR Camera Scanner) preserving DOM IDs | M8 | Survey P2 Mobile |
| 23 | Android Compose Freeze Policy | Maintain existing Android Compose code frozen per R3; focus primary mobile testing on Mobile Web PWA | M8 | Survey P2 Mobile |
| 24 | 3-Role QA Live Test & 100% Pytest Pass | Test live on `http://localhost:8088` for Chủ nhà, Gia đình, Khách (QR handshake); ensure 100% pytest PASS | M9 | Survey P2 QA |
| 25 | Delivery, Git Push & Vercel Production | Consolidate Phase 1 + 2 in `FIX_REPORT_20261104.md`, git commit & push master, deploy Vercel prod | M10 | Survey P2 QA |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Deployment, Tunnel & QR Handshake | Vercel config, OpenSSH tunnel, routes_qr, TOTP 180s window, guest_enroll token | none | DONE |
| M2 | Login Gate, Password UX & Mobile SVG | #homeLoginGateModal lockdown, auth.js readOnly removal, <form> enter, 👁️ toggle, mobile SVG | none | DONE |
| M3 | 3D Model DOM, Controls & Raycaster | house3d.js label preserve, style.css pin icons, camera toolbar, THREE.Raycaster | M2 | DONE |
| M4 | Real Voice & ADB Mobile Verification | 7 real voice commands to 5 devices, Samsung S9 ADB test flows with visual screenshots | M1, M2, M3 | DONE |
| M5 | E2E Test Suite & Integrity Audits | 678/678 pytest PASS, DOM challenger 36/36, forensic integrity audit CLEAN | M1, M2, M3, M4 | DONE |
| M6 | Web Error Pages & Service Worker (Group a) | `sw.js`, `offline.html`, `404.html`, `500.html`, `qr_expired.html`, `403.html`, FastAPI 404 content-negotiation handler, vercel.json | M5 | DONE |
| M7 | Security Banner & Modals (Group b) | Lockdown modal (`#securityLockdownModal`), mic modal (`#micPermissionModal`), WS reconnect banner (`#wsReconnectBanner`), DOM preservation | M6 | DONE |
| M8 | Mobile /app 5 Screens (Group c + d) | M1-M5 screens, tab switcher navigation, DOM backward compatibility, Android Compose status | M6, M7 | DONE |
| M9 | 3-Role QA Live Flow & 100% Pytest (Group e + f) | 3-role live browser testing (Chủ nhà, Gia đình, Khách), 100% pytest PASS, review against DESIGN_NEW_PAGES.md | M6, M7, M8 | DONE |
| M10 | Delivery, Git Push & Vercel Prod | FIX_REPORT_20261104.md complete, master git commit & push, Vercel deploy | M9 | DONE |

## Interface Contracts
### Web / Mobile ↔ Backend QR TOTP
- `GET /api/auth3/guest_qr_current?host=<chosen_host>` -> `{ ok: true, qr_svg: "<svg...", full_url: "...", token: "..." }`
- `POST /api/auth3/guest_handshake` -> payload `{ token: string, duration: string, tier: 3 }` -> response `{ ok: true, session: {...} }` or `{ ok: false, error: string }` (HTTP 200/400/401). Window tolerance: 180s (18 windows).

### Web Error Pages & Service Worker
- `GET /sw.js`: returns `simulator/static/sw.js` with header `Service-Worker-Allowed: /`.
- Service Worker handles `request.mode === 'navigate'`, network-first, fallback to `/offline.html` on network failure. Ignores `/api/*` and non-GET requests.
- `GET /nonexistent_page`:
  - If `Accept: text/html` -> HTTP 404 with HTML body `404.html`.
  - If `/api/*` or `application/json` -> HTTP 404 with JSON body `{"detail": "Not Found"}`.
- Static error pages: `/offline.html`, `/404.html`, `/500.html`, `/qr_expired.html`, `/403.html` styled with Tailwind-like CSS matching `ui_mockups/v2_new_pages/np_*.html`.

### Modals & Banners Contract
- Lockdown Modal: `#securityLockdownModal`, triggered when unauthorized strike count >= 3 or security lockdown event received. Unlock via Admin Password (`/api/auth3/layer1_login`) or Gmail OTP (`/api/auth3/forgot_password_send_otp`). Calls `reset_strikes()` on success.
- Mic Permission Modal: `#micPermissionModal`, displayed when `getUserMedia` throws NotAllowedError or when context is not secure (`isSecureContext === false`).
- WebSocket Reconnect Banner: `#wsReconnectBanner`, displayed when WS connection is lost/reconnecting. Retry count 1..5. Calls `window.retryWsConnection()` on button click. On reconnect, shows green badge for 2s then slides out.

### Mobile /app Navigation & Screen Contracts
- 4-tab Navigation bar: `#mobileNavTabHome`, `#mobileNavTabDevices`, `#mobileNavTabVoice`, `#mobileNavTabAccount`.
- Function `window.switchMobileTab(tabName)` changes active screen and updates tab active indicator.
- Function `window.scrollToSection(sectionId)` mapped to appropriate tab to maintain 100% backward compatibility with `test_challenger_m4_dom.py`.
- Forgot password screen accessible from Account / Login Gate modal via `#mobileBtnForgotPassword`.
- Voice bottom sheet opened via `#mobileBtnVoiceSheet` or mic icon.

## Code Layout
- `simulator/static/`: Web frontend (index.html, auth.html, guest_enroll.html, house3d.js, css/style.css, js/app.js, js/auth.js, sw.js, offline.html, 404.html, 500.html, qr_expired.html, 403.html).
- `mobile_app/`: Mobile PWA frontend (index.html, mobile_app.js, style.css).
- `simulator/api/`: FastAPI route handlers (routes_qr.py, routes_device.py, routes_auth.py, etc.).
- `simulator/auth/`: Auth & TOTP mixins (qr_totp_mixin.py, auth_3layer.py).
- `simulator/`: Server core (server.py, voice_auth.py, state_engine.py).
- `ui_mockups/v2_new_pages/`: Authoritative design mockups (np_*.html, DESIGN_NEW_PAGES.md).
- `tests/`: Automated test suites (pytest, tests/test_challenger_*.py, tests/e2e/).
- `vercel.json`: Vercel routing configuration.
