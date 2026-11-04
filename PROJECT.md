# Project: Smart Home Voice AI (Đồ Án Tốt Nghiệp)

## Architecture
- **Web Frontend**: HTML5/CSS3/Vanilla JS + Three.js r128 (3D House Model) served by FastAPI & deployed to Vercel (`simulator/static/`, `mobile_app/`).
- **Mobile PWA / View**: Dedicated lightweight mobile web interface (`/app` in `mobile_app/index.html`) optimized for touch and ADB mobile testing.
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

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Deployment, Tunnel & QR Handshake | Vercel config, OpenSSH tunnel, routes_qr, TOTP 180s window, guest_enroll token | none | DONE |
| M2 | Login Gate, Password UX & Mobile SVG | #homeLoginGateModal lockdown, auth.js readOnly removal, <form> enter, 👁️ toggle, mobile SVG | none | DONE |
| M3 | 3D Model DOM, Controls & Raycaster | house3d.js label preserve, style.css pin icons, camera toolbar, THREE.Raycaster | M2 | DONE |
| M4 | Real Voice & ADB Mobile Verification | 7 real voice commands to 5 devices, Samsung S9 ADB test flows with visual screenshots | M1, M2, M3 | DONE |
| M5 | E2E Test Suite & Integrity Audits | 678/678 pytest PASS, DOM challenger 36/36, forensic integrity audit CLEAN | M1, M2, M3, M4 | DONE |

## Interface Contracts
### Web / Mobile ↔ Backend QR TOTP
- `GET /api/auth3/guest_qr_current?host=<chosen_host>` -> `{ ok: true, qr_svg: "<svg...", full_url: "...", token: "..." }`
- `POST /api/auth3/guest_handshake` -> payload `{ token: string, duration: string, tier: 3 }` -> response `{ ok: true, session: {...} }` or `{ ok: false, error: string }` (HTTP 200/400/401). Window tolerance: 180s (18 windows).

### Frontend 3D ↔ Device Actuator
- `SmartHome3D.setCameraView(preset)`: preset in `['overview', 'living', 'bedroom', 'door', 'garden', 'board', 'rotate']`
- `SmartHome3D.init(canvasContainerId, overlayLabelsId, onToggleDevice)`: `onToggleDevice(deviceId)` invoked either by clicking `.pin-3d` or Raycaster click on 3D meshes.

### Voice Engine ↔ State Engine
- `SmartHomeVoiceAuth.verify_voice_command(wav_bytes)` -> `{ verified: bool, tier: int, speaker: str, intents: [{ device: str, action: str }] }`
- `SmartHomeEngine.execute_device_action(device_id, action)` -> updates device state, SQLite WAL, broadcasts to WebSocket `/ws`.

## Code Layout
- `simulator/static/`: Web frontend (index.html, auth.html, guest_enroll.html, house3d.js, css/style.css, js/app.js, js/auth.js).
- `mobile_app/`: Mobile PWA frontend (index.html, mobile_app.js).
- `simulator/api/`: FastAPI route handlers (routes_qr.py, routes_device.py, etc.).
- `simulator/auth/`: Auth & TOTP mixins (qr_totp_mixin.py, auth_3layer.py).
- `simulator/`: Server core (server.py, voice_auth.py, state_engine.py).
- `test_audio/`: Real voice audio assets and manifests.
- `tests/`: Automated test suites (pytest, tests/test_challenger_m4_dom.py, tests/e2e/).
- `vercel.json`: Vercel routing configuration.
