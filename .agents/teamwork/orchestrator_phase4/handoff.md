# Orchestrator Soft Handoff — Phase 4: Generation 1 -> Generation 2

## 1. Milestone State
| Milestone | Status | Key Deliverables & Verdicts |
|---|---|---|
| **Phase 0 (Survey)** | DONE | 3 parallel Explorers mapped all 15 bugs from `REAL_TEST_BUGS_20261105.md`. Handoffs in `teamwork_explorer_survey_1/`, `survey_2/`, `survey_3/`. |
| **Phase 1 (Decomposition)** | DONE | `PROJECT.md` created with 19 feature/task items organized into 5 milestones (M1–M5). |
| **Milestone 1 (Security & Auth)** | **DONE (Gate PASS)** | Bugs 1, 2, 4, 5, 15 resolved: UI credentials/hints purged, logout state fully reset, seed accounts (`senat6031@gmail.com` Tier 2, `kbanh376@gmail.com` Tier 3) added with PBKDF2 salt, real `send_gmail: true` & 3-step OTP UI, voice auth wizard cleaned, desktop header access duration badge added. Persistence hardened across 21 locations with `write_bytes` (0 CRLF guaranteed on Windows), .gitattributes created, log key masking enhanced. Gate 2 passed 100% (Auditor CLEAN, Reviewers APPROVE, Challengers APPROVE, 75 tests pass). |
| **Milestone 2 (Realtime & Simulation)** | **PLANNED (Next)** | Scope: Bugs 3, 10, 11, 14. Explorer 2 survey handoff in `teamwork_explorer_survey_2/handoff.md` contains exact line numbers, code locations, and TDD strategies. |
| **Milestone 3 (Mobile & UI Layout)** | PLANNED | Scope: Bugs 6, 7, 8, 9, 12, 13. Explorer 3 survey handoff in `teamwork_explorer_survey_3/handoff.md`. |
| **Milestone 4 (Full Test Gate)** | PLANNED | Pytest full suite, Playwright 3 roles, Android `assembleDebug`, Reviewer & Auditor gate. |
| **Milestone 5 (Production & Report)** | PLANNED | Vercel production deploy, live browser curl verification, FIX_REPORT Phase 4, git commit/push master. |

## 2. Active Subagents
- None currently active. All 16 dispatched subagents have completed and delivered reports.

## 3. Pending Decisions & Technical Constraints
- **M2 Next Step**: Spawn `teamwork_worker` for Milestone 2 following strict TDD:
  - Read `teamwork_explorer_survey_2/handoff.md`.
  - Write reproduction tests in `tests/test_p4_survey2_realtime.py` (Bugs 3, 10, 11, 14), confirm FAIL before fix.
  - Fix Bug 3: In `simulator/static/js/app.js` and `mobile_app.js`, when HTTP polling `/api/state` succeeds, hide `#wsReconnectBanner` and sync header pill. Add route `/favicon.ico` in `vercel.json` and create `simulator/static/favicon.ico`.
  - Fix Bug 10: Optimistic UI for device toggles in `app.js` and `mobile_app.js`; avoid `innerHTML=""` label flashing; ensure full subtitle ("Đã bật" / "Đã tắt").
  - Fix Bug 11: In `mobile_app.js`, add "Đang chờ quyền mic" state, only run timer/waveform after `getUserMedia` granted; add `#mobileMicPermissionModal` in `mobile_app/index.html`.
  - Fix Bug 14: Adjust Breadboard `.comp-tag` layout in `simulator/static/wokwi.html` (DHT11 vs Buzzer overlap); replace "Chưa có dữ liệu" in `#hoverHoleInfo` with live telemetry.
  - Verify all tests PASS, 0 CRLF, 68 DOM IDs preserved.
  - Reviewer & Auditor verification for M2.
- **Audit Rules**: Hard binary veto on Forensic Audit failure (never skip, never weigh against test scores).
- **Zero Credentials in Reports**: Never log, commit, or display passwords, OTPs, or secrets.
- **UTF-8 POSIX LF**: Maintain 0 CRLF across all files.

## 4. Remaining Work (Concrete Next Steps for Successor)
1. Initialize gen2 workspace in `.agents/teamwork/orchestrator_phase4/` (inherit BRIEFING.md and progress.md).
2. Start heartbeat cron: `schedule(CronExpression="*/10 * * * *", Prompt="Heartbeat check: check subagent progress and update progress.md")`.
3. Dispatch Milestone 2 Worker for Bugs 3, 10, 11, 14.
4. Run Reviewers and Forensic Auditor on M2.
5. Proceed to Milestone 3 (Bugs 6, 7, 8, 9, 12, 13), then Milestone 4, then Milestone 5.

## 5. Key Artifacts
- `PROJECT.md` at `.agents/teamwork/orchestrator_phase4/PROJECT.md`
- `BRIEFING.md` at `.agents/teamwork/orchestrator_phase4/BRIEFING.md`
- `progress.md` at `.agents/teamwork/orchestrator_phase4/progress.md`
- `GATE_STATUS.md` at `.agents/teamwork/orchestrator_phase4/GATE_STATUS.md`
- Survey handoffs: `teamwork_explorer_survey_1/`, `survey_2/`, `survey_3/`
- Milestone 1 handoff: `teamwork_worker_m1_remediation/handoff.md`
- Parent ID: `375b83e7-f9ec-42e0-9118-2bd1274a59c6`
