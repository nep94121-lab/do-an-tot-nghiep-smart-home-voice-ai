Fix all 15 bugs identified during real testing as documented in REAL_TEST_BUGS_20261105.md for the Smart Home Voice AI system, verified with reviewer and auditor checks across web, Android, and production deployment.

Working directory: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp
Integrity mode: development

## Requirements

### R1. Reproduce and Fix All 15 Real Test Bugs
Read `REAL_TEST_BUGS_20261105.md` at the project root and fix all 15 identified bugs. For each bug, follow a strict test-driven bugfix cycle: write an automated reproduction test first (pytest or Playwright), confirm that the test fails before any fix, and then modify the codebase until the test passes.

### R2. Comprehensive Multi-Role and Cross-Platform Verification
Execute full test validation suites:
- Full pytest test suite (executed on Windows with `python -X utf8 -m pytest tests/ --basetemp=.pytest_tmp` and clean up `.pytest_tmp` afterward).
- Playwright live flow tests covering all 3 user roles: owner, family member (tier 2), and guest (tier 3).
- Android build verification via Gradle `assembleDebug` (with `android.overridePathCheck=true`).
- Independent reviewer and auditor verification ensuring no fabricated/mocked tests and zero data leaks. The process must not stop while any test is failing.

### R3. Production Deployment and Live Verification
Commit and push all changes to the `master` branch, deploy to Vercel production, and verify each bug fix against https://do-an-tot-nghiep-smart-home-voice-a.vercel.app using real browser interaction flows.

### R4. Documentation and Security Guardrails
Append a Phase 4 section to `FIX_REPORT_20261104.md` documenting for each bug: the bug description, root cause, resolution approach, verification tests, and production verification results. Operate strictly within the project directory without interacting with other external processes or bots. Use the default owner password from the project seed for testing; do NOT log, commit, or display any passwords, OTPs, or secrets in reports, logs, commits, or UI. Preserve all 68 DOM IDs, window hooks, re-exports, the 3D model `house3d.js`, and maintain UTF-8 encoding without BOM and POSIX LF (0 CRLF).

## Acceptance Criteria

### Bug Fixes and TDD Verification
- [ ] All 15 bugs listed in `REAL_TEST_BUGS_20261105.md` have corresponding automated reproduction tests written and verified failing prior to fixes.
- [ ] All 15 reproduction tests pass after code fixes.

### Test Suite Execution
- [ ] Full pytest suite passes with 0 failures (`python -X utf8 -m pytest tests/ --basetemp=.pytest_tmp`).
- [ ] Full Playwright live flow tests pass for owner, tier-2 family member, and tier-3 guest roles.
- [ ] Android `assembleDebug` succeeds with exit code 0.
- [ ] Independent reviewer and auditor checks confirm no mocked/fake tests and no sensitive credentials leaked.

### Production and Deployment
- [ ] All changes are committed and pushed to `master`.
- [ ] Production deployment to Vercel completes successfully.
- [ ] Live browser verification on `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app` confirms resolution of each bug.

### Documentation and Integrity
- [ ] `FIX_REPORT_20261104.md` contains the complete Phase 4 section with root causes, fixes, tests, and production verification evidence.
- [ ] Zero secrets, passwords, or OTPs are recorded in reports, logs, commits, or UI.
- [ ] All 68 DOM IDs, window hooks, re-exports, `house3d.js`, and UTF-8 LF formatting remain intact.
