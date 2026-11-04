## 2026-11-04T12:26:57Z
You are spec_miner_web_p2. Your working directory is C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\spec_miner_web_p2.
You MUST first read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md.
Your task is to thoroughly survey all specifications and source files for:
1. Web error pages: offline + sw.js, 404, 500/503, QR expired, 403.
2. Modals and banners: lockdown modal, mic permission modal, and WebSocket reconnect banner.
Authoritative references to inspect:
- ui_mockups/v2_new_pages/DESIGN_NEW_PAGES.md (Part 1 and all related sections)
- ui_mockups/v2_new_pages/np_offline.html
- ui_mockups/v2_new_pages/np_404.html
- ui_mockups/v2_new_pages/np_500.html
- ui_mockups/v2_new_pages/np_qr_expired.html
- ui_mockups/v2_new_pages/np_403.html
- ui_mockups/v2_new_pages/np_modal_lockdown.html
- ui_mockups/v2_new_pages/np_modal_mic.html
- ui_mockups/v2_new_pages/np_ws_reconnect.html
- Existing codebase: simulator/server.py (FastAPI 404 handler, static mounts), simulator/static/ (existing html/js/css, sw.js if any, index.html, house3d.js), simulator/static/guest_enroll.html, simulator/static/auth.html.
Key constraints to verify:
- FastAPI 404 handler must return HTML only for browser navigations (Accept: text/html), while preserving JSON 404 for /api/*.
- Service worker (sw.js) caching strategy and offline fallback.
- Preserving existing DOM IDs and window.* hooks in simulator/static/index.html, simulator/static/guest_enroll.html, simulator/static/auth.html, mobile_app/index.html.
- Do NOT touch or break house3d.js or Toàn cảnh layout.
Write your comprehensive specification report to C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\spec_miner_web_p2\survey_report.md and your handoff to C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\spec_miner_web_p2\handoff.md.
Send a message back to parent when done.
