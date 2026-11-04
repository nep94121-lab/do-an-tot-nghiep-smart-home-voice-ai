# Project: Smart Home Voice AI (Đồ Án Tốt Nghiệp)

## Architecture
- **Web Frontend**: HTML5/CSS3/Vanilla JS + Three.js r128 (3D House Model) served by FastAPI & deployed to Vercel (`simulator/static/`, `mobile_app/`).
- **Mobile PWA / View**: Dedicated lightweight mobile web interface (`/app` in `mobile_app/index.html`) optimized for touch, tab navigation, and ADB mobile testing.
- **Android Native App**: Jetpack Compose (`android_app/`) with modules `:app` and `:app-core`, supporting M1–M5 screens, voice capture, and QR scanner.
- **Backend Core**: FastAPI (`0.0.0.0:8088`), WebSocket `/ws`, SQLite WAL database (`simulator/data/smarthome.db`), Session-based RBAC with `SessionStore`, TOTP Guest Handshake (`simulator/auth/qr_totp_mixin.py`).
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
| 26 | Vercel Routing & Error Page Fallback | 307 redirect `/mobile -> /app`, `/architecture`, status codes, catch-all `404.html` on Vercel | M11 | Phase 3 R1 |
| 27 | Session-based Request RBAC Store | Parameterize RBAC per session/token in `SessionStore`, remove global engine mutation | M12 | Phase 3 R2 |
| 28 | 3-Role Concurrent Execution Tests | Automated concurrent multi-role test (120 requests) proving zero permission bleed | M12 | Phase 3 R2 |
| 29 | Android Native Compose M1–M5 UI | Implement M1 Home/Sensors, M2 Account/Tabs, M3 Forgot OTP, M4 Voice Sheet, M5 QR Scanner | M13 | Phase 3 R3 |
| 30 | Android Gradle assembleDebug | Fix `android.overridePathCheck=true` in `.lightbuild/gradle/gradle.properties`, assembleDebug SUCCESS | M13 | Phase 3 R3 |
| 31 | Samsung S9 ADB Flow & Screencaps | Install APK, launch app, capture screencaps to `ui_mockups/android_phase3/` if device connected | M13 | Phase 3 R3 |
| 32 | Ponytail Modularization & Dead Code Purge | Purge legacy `static/app.js` & `style.css` (2001L dead code), modularize `app.js`, `mobile_app.js`, `voice_auth.py`, `MainScreen.kt` | M14 | Phase 3 R4 |
| 33 | Test Contract & DOM ID Preservation | Preserve 100% of 68 DOM IDs, 25 mobile window hooks, 13 security hooks, 3D house3d.js v1 light design | M14 | Phase 3 R4 |
| 34 | Full Gating, Deploy & Phase 3 Delivery | 100% pytest pass, assembleDebug pass, auditor clean, git commit/push, deploy Vercel prod, verify real URLs | M15 | Phase 3 R5, R6 |

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
| M11 | Vercel Production Routing & Redirection (R1) | 307 redirect `/mobile -> /app`, `/architecture`, error pages, catch-all `404.html`, server routes | M10 | DONE |
| M12 | Session-based RBAC Security & Concurrent Tests (R2) | `SessionStore`, `resolve_request_session`, parameterize engine, remove global mutation, 120-test concurrency suite | M10 | DONE |
| M13 | Android Native Compose M1–M5 & assembleDebug (R3) | M1-M5 screens, `android.overridePathCheck=true`, `assembleDebug` SUCCESSFUL, ADB S9 screencaps | M10 | DONE |
| M14 | Ponytail Modularization & Dead Code Purge (R4) | Dead code purge (2001L), modularize `app.js`, `mobile_app.js`, `voice_auth.py`, `MainScreen.kt`, preserve DOM IDs & hooks | M11, M12, M13 | DONE |
| M15 | Full Gating, Vercel Deploy & Phase 3 Delivery (R5, R6) | 100% pytest PASS, assembleDebug SUCCESSFUL, auditor CLEAN, git commit & push master, deploy Vercel prod, verify real URLs | M11, M12, M13, M14 | IN_PROGRESS |

## Interface Contracts
### Vercel Routing Contract (M11)
- `GET /mobile` -> HTTP 307 Redirect to `/app`.
- `GET /architecture` -> Serves `/docs/kien_truc/smart-home-voice-ai.architecture.html`.
- `GET /offline`, `/404`, `/403`, `/500`, `/qr_expired`, `/sw.js` -> Serves corresponding static shell asset with HTTP 200/404/403/500 status codes.
- `GET /<non_existent_path>` -> Serves `/simulator/static/404.html` with HTTP 404 status code (no Vercel raw NOT_FOUND).

### Session-based RBAC Contract (M12)
- Session Token resolution:
  1. Header `Authorization: Bearer <session_token>`
  2. Header `X-Session-Token: <session_token>`
  3. Cookie `sh_session_token=<session_token>`
  4. Query param `token=<token>` (for guest handshake)
  5. Fallback: Default to unauthenticated Guest Tier 3.
- `execute_device_action(device_id, action, source="api", request_tier=tier, request_user_name=user_name)`:
  - Takes `request_tier` explicitly per-request.
  - Does NOT mutate or rely on global singleton `current_tier`.
  - Tier 1 (Chủ nhà): Full access (Door, Alarm, Lights, Fan, AC, Pump, Schedule).
  - Tier 2 (Gia đình): Limited access (Lights, Fan, AC, Pump). Cannot open Door or trigger/reset Alarm.
  - Tier 3 (Khách): Temporary access (Lights, Fan). Cannot open Door, Alarm, or create Schedule.

### Android Native Compose UI Contract (M13)
- Navigation: 4 tabs (Home, Devices, Voice, Account).
- M1 Home & Sensors: 2-grid sensor card (Temp 28.5°C, Soil 62%), Safety card (Door & Siren), CTA buttons ("Nói lệnh", "Xem thiết bị").
- M2 Account & Tabs: 3-line Profile card (Role, Email, Duration), Management menu, Logout button.
- M3 Forgot Password: 3-step OTP flow (Email -> 6-digit OTP -> Reset).
- M4 Voice Bottom Sheet: Scrim overlay, 12-bar waveform, timer 00:03/00:05, sample phrase `"Mở cửa chính cho tôi."`.
- M5 QR Camera Scanner: 215x215dp 4-corner viewfinder, camera toggle, manual code entry.

### Ponytail Modularization & Preservation Contract (M14)
- Web Frontend: `simulator/static/js/app.js` remains coordinating entry point / barrel re-export; submodules live in `simulator/static/js/modules/`. Preserves 13 window hooks and all literal string regex anchors tested by Node VM runners.
- Mobile PWA: `simulator/static/js/mobile_app.js` preserves 68 DOM IDs and 25 window hooks.
- Android: `MainScreen.kt` decomposed into `model/`, `audio/`, `components/`, and `screens/` sub-composables.
- Backend: `simulator/voice_auth.py` separates DSP filters to `simulator/voice/dsp.py` and re-exports symbols.
- 3D Model: `simulator/static/house3d.js` remains 100% untouched.

## Code Layout
- `simulator/static/`: Web frontend.
- `mobile_app/`: Mobile PWA frontend.
- `android_app/`: Android native Compose application (`app`, `app-core`).
- `simulator/api/`: FastAPI route handlers.
- `simulator/auth/`: SessionStore & auth mixins.
- `simulator/engine/`: Rule engine and device control logic.
- `simulator/voice/`: Modularized DSP and voice processing.
- `ui_mockups/v2_new_pages/`: Authoritative design mockups.
- `tests/`: Automated test suites (pytest).
- `vercel.json`: Vercel routing configuration.
