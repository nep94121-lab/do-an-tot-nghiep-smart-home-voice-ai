# BRIEFING — 2026-11-05T08:23:00Z

## Mission
Phase 7 UI overhaul for Smart Home Voice AI capstone project on branch `p7-ui` in worktree `C:\Users\LENOVO\datn-wt\ui`. Execute the locked 6-point plan via TDD: GET /login and /register light minimalist, mobile 360-460px 3D pin collision repulsion and 2-row header, optimistic UI (<16ms, 2500ms mutation guard), voice auth setup (3 fields only), shared 8-route nav bar, E2E multi-viewport Playwright audit, full pytest regression, git rebase & push strictly to `p7-ui`, Vercel preview deploy (no --prod), and independent Victory Audit.

## 🔒 My Identity
- Archetype: sentinel
- Working directory: c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\
- Orchestrator: a9c97bf8-f7ac-4d06-bdf4-dcf1d0cecae3
- Victory Auditor: [auditor conversation ID, or to be spawned on victory claim]
- Working directory (Phase 7 UI): C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\
- Active Orchestrator (Phase 7 UI): e7340628-f79a-4027-966a-f5d6b40bf426
- Active Worker: a1ac8914-5b78-4bff-81ee-4354ba056b37 (worker_m3_gen3)

## 🔒 Key Constraints
- No technical decisions — relay only
- Victory Audit is MANDATORY before reporting completion
- Keep context ultra-light
- Zero-illusion, verify independently
- Never report project completion without VICTORY CONFIRMED verdict
- Implement exact Codex design in ui_mockups/v2_new_pages/DESIGN_NEW_PAGES.md, KHÔNG thiết kế lại
- Giữ nguyên cấu trúc house3d.js / Toàn cảnh
- FastAPI 404 handler chỉ trả HTML cho browser navigation, JSON 404 cho /api/*
- Bảo toàn DOM IDs và window.* hooks hiện có (mobile_app/index.html, simulator/static/index.html, guest_enroll.html, auth.html)
- Không ghi mật khẩu, secret, OTP vào file/log mới; không tự login Gmail
- Chạy pytest bằng `python -X utf8 -m pytest tests/ --basetemp=.pytest_tmp` (xóa .pytest_tmp sau khi chạy)
- Nếu chỉnh sửa Android Compose: `./gradlew assembleDebug` phải thành công
- Commit + push master; deploy Vercel production nếu CLI login
- Phase 7 UI: Work ONLY in worktree C:\Users\LENOVO\datn-wt\ui on branch p7-ui
- Do NOT push to master; push ONLY p7-ui
- Vercel preview KHONG --prod
- Ghi preview URL vao log va FIX_REPORT Phase 7 UI
- Khong dung voice backend (simulator/voice/**, simulator/voice_auth.py, live/**)
- Khi xong bao END voi preview URL sau khi Victory Auditor xac nhan

## User Context
- **Last user request**: Phase 7 UI. Ke hoach da aligned qua grill-me. Thuc thi TDD theo 6 diem da chot tren nhanh p7-ui worktree C:\Users\LENOVO\datn-wt\ui. Push CHI p7-ui. vercel preview KHONG --prod. Ghi preview URL vao log va FIX_REPORT Phase 7 UI. Khong push master. Khong dung voice backend. Khi xong bao END voi preview URL.
- **Pending clarifications**: none
- **Delivered results**:
  - M1 (Navigation, Routing & Dedicated Login/Register): Gate Passed
  - M2 (UI Overhaul Core: Gate, Mobile 3D, Optimistic UI, Voice Setup): Gate Passed
  - M3 (E2E Multi-Viewport Audit, Full Pytest, Git Push & Vercel Deploy): in progress by worker_m3_gen3 (1094/1098 tests passed)

## Project Status
- **Phase**: in progress (Milestone 3 final stabilization & deploy)

## Victory Audit Status
- **Triggered**: no
- **Verdict**: pending
- **Retry count**: 0

## Artifact Index
- ORIGINAL_REQUEST.md — Authoritative record of user intent
- FIX_REPORT_20261104.md — Comprehensive Bugfix & Implementation Report
- orchestrator/progress.md — Orchestrator progress tracking
- orchestrator/PROJECT.md — Master project architecture and scope
- .agents/teamwork/cli_fix_p7_ui_20261105.log — CLI execution log
