# BRIEFING — 2026-11-05T06:45:00Z

## Mission
Thực hiện Milestone 3: Playwright Multi-Viewport E2E Audit, Full Pytest verification, Invariant Checks (0 CRLF, HTML purity, forbidden files), Git Commit & Push branch `p7-ui`, và Vercel Preview Deployment.

## 🔒 My Identity
- Archetype: worker
- Roles: implementer, qa, specialist
- Working directory: C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\worker_m3_gen3\
- Original parent: e7340628-f79a-4027-966a-f5d6b40bf426
- Milestone: Milestone 3 (Validation, Audit, Commit, Push, Vercel Preview Deploy)

## 🔒 Key Constraints
- Branch hoạt động: `p7-ui`.
- TUYỆT ĐỐI KHÔNG push lên branch `master`.
- TUYỆT ĐỐI KHÔNG thêm cờ `--prod` khi chạy Vercel preview.
- Không sửa tệp cấm: `simulator/voice/`, `simulator/voice_auth.py`, `simulator/live/`.
- 100% POSIX LF (0 CRLF), 0 inline style/script không có src trên 8 file HTML.
- 100% Pytest pass (Exit Code 0).

## Current Parent
- Conversation ID: e7340628-f79a-4027-966a-f5d6b40bf426
- Updated: 2026-11-05T06:45:00Z

## Task Summary
- **What to build**: Playwright multi-viewport audit test script, run tests, verify invariants, commit & push to p7-ui, deploy Vercel preview, independently test 8 preview routes, log & handoff.
- **Success criteria**: 0 console error, no mobile overflow, 100% pytest pass, 0 CRLF, commit pushed to `p7-ui`, preview URL deployed and verified HTTP 200 on 8 routes.
- **Interface contracts**: PROJECT.md, TEST_INFRA.md, FIX_REPORT_20261104.md
- **Code layout**: C:\Users\LENOVO\datn-wt\ui

## Change Tracker
- **Files modified**: [TBD]
- **Build status**: [TBD]
- **Pending issues**: None

## Quality Status
- **Build/test result**: [TBD]
- **Lint status**: [TBD]
- **Tests added/modified**: [TBD]

## Loaded Skills
- None requested specifically

## Key Decisions Made
- Sẽ sử dụng Python Playwright với channel="chrome" để chụp ảnh và kiểm tra 8 routes x 4 viewports.

## Artifact Index
- DISPATCH.md
- BRIEFING.md
- progress.md
- handoff.md
