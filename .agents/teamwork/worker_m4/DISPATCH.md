# Dispatch — worker_m4: Milestone 4 (Full Verification, Single Real Verification Email & Vercel Preview Deploy)

**Worker:** `worker_m4` (Archetype: `teamwork_worker`)  
**Assigned Scope:** Milestone 4 (R4: E2E Automated Test Pass, Single Real Verification Email, Git Commit/Push to origin/p6-otp, Vercel Preview Deploy, and FIX_REPORT_20261104.md)  
**Parent:** Project Orchestrator (`91485de0-7c6f-449a-ba3f-ed6820ebb01a`)  
**Workspace:** `C:\Users\LENOVO\datn-wt\p6-otp` (Branch: `p6-otp`)  
**Working Directory:** `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\worker_m4`  
**Date:** 2026-11-05T07:47:00Z  

## Mandatory Reading Before Execution:
1. `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\ORIGINAL_REQUEST.md` (Authoritative User Request)
2. `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\orchestrator\SCOPE.md` (Milestone 4 Contract)
3. Handover reports of M1, M2, M3 in `.agents/teamwork/`

## Constraints:
- Zero-Leak: NEVER read, write, print, or log real SMTP passwords or tokens.
- Push ONLY to `origin/p6-otp` (NEVER push to master).
- Deploy ONLY preview (`vercel --yes`, strictly NO `--prod`).
- At most ONE real verification email to `senat6031@gmail.com` after all automated tests pass.
- UTF-8 without BOM, 0 CRLF.

## 2026-11-05T07:47:29Z

Received Dispatch Message from Orchestrator:
- Worker: worker_m4
- Working directory: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\worker_m4
- Parent: 91485de0-7c6f-449a-ba3f-ed6820ebb01a
- Objective: Execute Milestone 4 (R4: E2E Verification, Single Real Verification Email, Git Branch Push & Vercel Preview Deploy)
- Tasks:
  1. Automated Tests Verification:
     `pytest tests/test_phase6_r3_rfc5322.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py tests/test_phase5_r3_otp_email.py tests/test_challenger_m3_rfc5322.py tests/test_challenger_phase6_m3_2.py tests/test_challenger_phase5_r2_r3.py -v` (100% pass)
  2. Single Real Verification Email:
     Dispatch at most ONE real verification email to senat6031@gmail.com.
     Verify non-allowlisted emails rejected cleanly without bounce.
     Record dispatch result.
  3. Git Branch Management & Push:
     Verify branch is p6-otp.
     Stage all Phase 6 changes.
     Commit on branch p6-otp.
     Push ONLY to origin/p6-otp (NEVER master).
  4. Vercel Preview Deployment:
     Deploy preview using Vercel CLI: vercel --yes (STRICTLY NO --prod).
     Capture preview URL.
  5. Report Documentation (FIX_REPORT_20261104.md):
     Executive Summary of Phase 6 fixes.
     Vercel Preview URL.
     Git commit hash on branch p6-otp.
     Real email dispatch record to senat6031@gmail.com.
     Comprehensive test suite results.
     Zero-Leak attestation.
