# Dispatch Log

## 2026-11-05T04:16:10Z

Phase 7 UI overhaul for Smart Home Voice AI capstone project, implementing a 6-point plan covering login redesign, mobile 360-460px responsiveness, optimistic UI with latency tracking, simplified voice auth setup, shared navigation, and automated verification.

Working directory: C:\Users\LENOVO\datn-wt\ui
Integrity mode: development
The team must NOT:
- Push to master branch (push ONLY branch p7-ui)
- Deploy to production (use vercel preview without --prod)
- Touch voice backend files (simulator/voice/**, simulator/voice_auth.py, simulator/live/**)
- Print secrets or send real emails
- Run Admin PC bots or Desktop BA-SVD

## Requirements

### R1. Login & Register Flow Redesign
Implement GET `/login` and GET `/register` following mockup-1 light minimalist design. On `/login`, Login Gate `/`, and `/app`, display only email, password, login button, and small "Quên mật khẩu?" and "Đăng ký" links. Hide legacy tab bar while keeping DOM IDs hidden to maintain test compatibility.

### R2. Mobile Responsive Layout (360-460px)
Apply collision repulsion and boundary clamping to 3D overlay chips on `/` with reduced font size. Reorganize `.top` header into two rows (Row 1: Overview and connection status; Row 2: badge, duration/quota, Logout) with email ellipsis truncation to eliminate overlaps shown in `C:\Users\LENOVO\datn-wt\mobile_home_3d_overlap.jpg`.

### R3. Optimistic UI & Latency Optimization
Implement optimistic DOM updates (<16ms frame) on device toggle buttons with in-place updates by `data-device-id` on `/app`. Protect mutations with a 2500ms `pendingDeviceMutations` guard. Measure before/after latency in milliseconds via Playwright and record the metrics in `FIX_REPORT_20261104.md`.

### R4. Voice Auth Setup Simplification
Streamline `/auth` setup to exactly 3 input fields: fixed permission level, full name, and email. Remove username, password, and microphone options from the interface, keeping legacy DOM elements hidden if necessary for backward test compatibility.

### R5. Shared Navigation & Route Mapping
Add a shared simple navigation bar across all static pages linking: Overview (`/`), Voice Auth (`/auth`), Hardware (`/wokwi`), Logs (`/logs`), App (`/app`), Guest (`/guest_enroll`), Login (`/login`), and Register (`/register`). Update routing configuration (`simulator/server.py` and `vercel.json`) and document the complete route map in `FIX_REPORT_20261104.md`.

### R6. Worktree, File Boundaries & Deployment
Work exclusively in worktree `C:\Users\LENOVO\datn-wt\ui` on branch `p7-ui`. Do not push to master; push only `p7-ui`. Deploy exclusively via Vercel preview (no `--prod`). Maintain 100% POSIX LF line endings (`\n`, 0 CRLF) and zero inline scripts in `simulator/static/index.html`. Record the Vercel preview URL in `FIX_REPORT_20261104.md` and `.agents/teamwork/cli_fix_p7_ui_20261105.log`. When finished, report END with the Vercel preview URL.
