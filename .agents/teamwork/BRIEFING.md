# BRIEFING — 2026-11-04T12:25:00Z

## Mission
Oversee Phase 2 execution: Implement exact Codex design (web error pages + sw.js, security modals/banners, mobile /app 5 screens, Android Compose, E2E tests, Vercel deploy).

## 🔒 My Identity
- Archetype: sentinel
- Working directory: c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\
- Orchestrator: cb4be64f-6f73-4e8f-b499-50863e4051dc (retired)
- Victory Auditor: 4e08a6e3-ca26-404c-99bf-e465e213844d (retired after confirmation)
- Interviewer: c599b515-014c-4856-b359-893848515866 (retired)
- Phase 2 Orchestrator: a6dd1e0f-b843-4477-96f4-146d5c9d3c58 (active)

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

## User Context
- **Last user request**: Approved Phase 2 task prompt.
- **Pending clarifications**: none
- **Delivered results**: Phase 1 completed 100%

## Project Status
- **Phase**: in progress (Orchestrator a6dd1e0f-b843-4477-96f4-146d5c9d3c58 active)

## Victory Audit Status
- **Triggered**: no
- **Verdict**: pending
- **Retry count**: 0

## Artifact Index
- ORIGINAL_REQUEST.md — Authoritative record of user intent
- FIX_REPORT_20261104.md — Bugfix and implementation report (Phase 1 + Phase 2)
- FIX_PLAN_20261104.md — Comprehensive fix and implementation plan
- ui_mockups/v2_new_pages/DESIGN_NEW_PAGES.md — Phase 2 Design Specification
- ui_mockups/v2_new_pages/np_*.html — HTML Mockups reference
