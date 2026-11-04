# BRIEFING — 2026-11-04T06:37:45Z

## Mission
Milestone 1: Deployment & Connectivity (Vercel, HTTPS Tunnel, LAN IP & QR TOTP Extension)

## 🔒 My Identity
- Archetype: teamwork_worker
- Roles: implementer, qa
- Working directory: c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m1
- Original parent: cb4be64f-6f73-4e8f-b499-50863e4051dc
- Milestone: Milestone 1 - Deployment & Connectivity

## 🔒 Key Constraints
- File Ownership ĐỘC QUYỀN:
  1. vercel.json
  2. simulator/auth/qr_totp_mixin.py
  3. simulator/api/routes_qr.py
  4. simulator/static/js/guest_enroll.js
- TUYỆT ĐỐI KHÔNG sửa các file ngoài danh sách này.
- Integrity Mandate: Không cheat, không hardcode kết quả test.
- 100% tiếng Việt trong báo cáo/tin nhắn.

## Current Parent
- Conversation ID: cb4be64f-6f73-4e8f-b499-50863e4051dc
- Updated: 2026-11-04T06:37:45Z

## Task Summary
- **What to build**:
  1. Tạo `vercel.json` định tuyến 6 trang static frontend (`/`, `/app`, `/auth`, `/guest_enroll`, `/logs`, `/wokwi`), static assets (`/static/`), test audio (`/test_audio/`), và tài liệu archify (`/archify`). Push repo GitHub và deploy Vercel prod.
  2. Sửa `simulator/auth/qr_totp_mixin.py` hàm `consume_guest_handshake`: nới rộng cửa sổ window lên 180s (18 chu kỳ), giữ Single-Use Token replay protection.
  3. Sửa `simulator/api/routes_qr.py`: hỗ trợ `host` / `host_url`, tự động nhận diện tiền tố `https://` cho domain tunnel (như `*.lhr.life`).
  4. Sửa `simulator/static/js/guest_enroll.js`: đọc `token` từ URL params để handshake tức thì.
- **Success criteria**:
  - `python -m pytest tests/test_milestone_m2_qr_guest.py -v --basetemp=.pytest_temp_m1` PASS 100% (17/17 passed).
  - GitHub repo cập nhật: commit `5d99581`.
  - Vercel prod deployment thành công: `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app` (9/9 routes đạt HTTP 200 OK).

## Key Decisions Made
- Cấu hình `vercel.json` với `"framework": null`, `"cleanUrls": false` và regex routes chính xác `^/.../?$` để tránh việc Vercel auto-detect FastAPI serverless gây lỗi build và đảm bảo phục vụ 100% các trang static HTML/CSS/JS.
- Nới rộng cửa sổ `consume_guest_handshake` lên 180s (18 chu kỳ window x 10s) cả ở thuật toán quét HMAC fallback và điều kiện kiểm tra `cur_window - token_win > 18 or token_win - cur_window > 2`, bảo toàn nghiêm ngặt Single-Use Token chống Replay Attack (`store.add(clean_tok)`).
- Nhận diện thông minh tiền tố `https://` cho domain tunnel (`*.lhr.life`, `.vercel.app`, `ngrok`, `trycloudflare.com`, cổng 443).
- Cập nhật `guest_enroll.js` đọc `token` và `window` từ URL params, gọi `doGuestHandshake` ngay khi mở trang bằng mã QR.

## Artifact Index
- .agents/teamwork/worker_m1/DISPATCH.md
- .agents/teamwork/worker_m1/BRIEFING.md
- .agents/teamwork/worker_m1/progress.md
- .agents/teamwork/worker_m1/handoff.md

## Change Tracker
- **Files modified**:
  1. `vercel.json` — Tạo mới, cấu hình 11 routes tĩnh và archify docs.
  2. `simulator/auth/qr_totp_mixin.py` — Nới rộng cửa sổ thời gian 180s (18 windows), duy trì Single-Use Token.
  3. `simulator/api/routes_qr.py` — Hỗ trợ host/host_url, tự động nhận diện prefix https:// cho domain tunnel.
  4. `simulator/static/js/guest_enroll.js` — Nhận diện urlToken và urlWindow từ URL param để handshake tức thì.
- **Build status**: PASS (Vercel Prod READY, 9/9 routes 200 OK)
- **Pending issues**: Không có

## Quality Status
- **Build/test result**: 17/17 pytest tests PASSED (100%), Orthogonal verification PASSED (100%).
- **Lint status**: Clean (Python & JS syntax validated).
- **Tests added/modified**: tests/test_milestone_m2_qr_guest.py (chạy xác thực 100% PASS).
