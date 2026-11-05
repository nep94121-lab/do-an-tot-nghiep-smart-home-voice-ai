# Plan: Phase 3 Orchestration

## Objective
Implement Phase 3 requirements:
1. Fix Vercel production routing (/mobile, /architecture, /offline, /404, /403, /500, /qr_expired, /sw.js, custom 404, redirect /mobile -> /app, verify via curl on real domain https://do-an-tot-nghiep-smart-home-voice-a.vercel.app).
2. Refactor RBAC from global engine state to session-based (cookie/token) for each request, preventing permission leaks between concurrent users, with tests for concurrent 3 roles (owner, admin, user/guest).
3. Android Native Compose: audit M1-M5 screens against ui_mockups/v2_new_pages (np_m1..np_m5), run assembleDebug successfully, install APK on connected S9 device (2223e8784b0c7ece) via ADB and capture screencaps into ui_mockups/android_phase3/.
4. Modularize & refactor whole project following skill ponytail principles: split thousand-line files (app.js, Python modules, MainScreen.kt...) without behavior changes, preserving 3D concept house3d.js, v1 light design, DOM IDs, window hooks, and test entry points.
5. Verification Gates: 100% pytest pass, Playwright/live user flows pass, assembleDebug SUCCESSFUL, reviewer approval, forensic auditor CLEAN (zero cheating/facades).
6. Git commit, push master, deploy Vercel prod, verify real URLs, and document line counts before/after in FIX_REPORT_20261104.md.

## Phase 3 Execution Steps
1. **Step 0: Survey (3 Parallel Explorers)**
   - `explorer_p3_routing_rbac`: Investigate Vercel routing configuration, `/mobile` redirect, static error pages, session-based RBAC architecture, FastAPI request state/cookies/tokens, concurrent test design.
   - `explorer_p3_android`: Investigate Android native Compose codebase, M1–M5 screens vs mockups, Gradle assembleDebug, S9 ADB connectivity & screencap automation.
   - `explorer_p3_refactor`: Search for ponytail skill, investigate large files (`app.js`, `mobile_app.js`, Python modules, `MainScreen.kt`), map DOM IDs/window hooks/test dependencies.
2. **Step 1: Merge Findings & Finalize PROJECT.md Milestones**
   - Synthesize explorer reports into PROJECT.md.
3. **Step 2: Milestone Execution & Gating**
   - Execute implementation through Worker -> Reviewer -> Challenger -> Auditor cycles.
   - Gate each milestone strictly.
4. **Step 3: Dual-track E2E Testing & Verification**
   - Verify 100% pytest pass, assembleDebug pass, ADB screencaps verified, curl verification on live Vercel.
5. **Step 4: Commit, Deploy & Final Delivery**
   - Push to master, deploy Vercel prod, update FIX_REPORT_20261104.md, notify Sentinel.
