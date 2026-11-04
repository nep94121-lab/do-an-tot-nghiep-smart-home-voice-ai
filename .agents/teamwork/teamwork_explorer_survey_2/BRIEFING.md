# BRIEFING — 2026-11-04T19:27:30Z

## Mission
Investigate and analyze the authoritative codebase for Bug 3, Bug 10, Bug 11, and Bug 14, formulating root causes and TDD reproduction test strategies.

## 🔒 My Identity
- Archetype: explorer
- Roles: Teamwork explorer survey
- Working directory: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_explorer_survey_2\
- Original parent: 4fbd627a-a119-4a5e-84ba-b07fb631efd7
- Milestone: Survey Phase 4 Real Test Bugs (Bugs 3, 10, 11, 14)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement in production source code during survey
- Maintain all 68 DOM IDs, window hooks, re-exports
- Zero secrets/passwords logged or outputted
- UTF-8 LF without BOM (0 CRLF)
- Write output to handoff.md in working directory
- Communicate via send_message to parent (4fbd627a-a119-4a5e-84ba-b07fb631efd7)

## Current Parent
- Conversation ID: 4fbd627a-a119-4a5e-84ba-b07fb631efd7
- Updated: 2026-11-04T19:27:30Z

## Investigation State
- **Explored paths**:
  - `simulator/static/js/app.js` (lines 515–640, 811–860, 240–350)
  - `simulator/static/index.html` (lines 1–60, 380–444)
  - `simulator/static/css/style.css` (lines 540–650)
  - `mobile_app/index.html` (lines 1–70, 580–640, 645–669)
  - `simulator/static/js/mobile_app.js` (lines 550–650, 825–885, 1285–1345)
  - `simulator/static/wokwi.html` (lines 30–90, 110–220, 240–320, 355–395)
  - `simulator/static/js/wokwi.js` (lines 80–90, 415–480, 500–565)
  - `simulator/static/css/wokwi.css` (lines 50–110, 140–220, 260–300)
  - `simulator/static/sw.js` (lines 1–60)
  - `simulator/server.py` (lines 190–205)
  - `vercel.json` (lines 1–39)
- **Key findings**:
  - Bug 3: `ws.onclose` unconditionally calls `showWsReconnectBanner` even when `fetch('/api/state')` succeeds; `pollRestStateFallback` never hides banner; `favicon.ico` missing from disk and `vercel.json` routes, causing 404 in console.
  - Bug 10: `toggleDeviceById` and mobile `onclick` lack optimistic UI; `innerHTML = ""` clears device grid during update; `.device-room` text is too wide for 2-column cards causing wrapping and Vietnamese diacritics clipping ("Đã bột").
  - Bug 11: `openVoiceBottomSheet` immediately sets title to "Đang thu âm" before mic permission prompt resolves; `startVoiceSheetRecording` ignores rejection and starts waveform/timer anyway; mobile lacks mic permission modal.
  - Bug 14: `#hoverHoleInfo` defaults to "Chưa có dữ liệu" and is only updated on hover; DHT11 tag at `left: 500px; top: 360px;` is occluded by Buzzer tag at `left: 632px; top: 360px;` causing visual cutoff to "Cảm biến DHT11 (Chân D…".
- **Unexplored areas**: None for Bug 3, 10, 11, 14.

## Key Decisions Made
- Fully documented root causes, file locations, line numbers, and formulated precise TDD reproduction test strategies in `handoff.md`.

## Artifact Index
- DISPATCH.md — Initial dispatch instructions
- BRIEFING.md — Working memory and context
- progress.md — Liveness heartbeat and progress tracking
- handoff.md — Comprehensive Survey Report (5-component structure)
