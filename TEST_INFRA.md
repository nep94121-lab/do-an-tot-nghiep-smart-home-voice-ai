# E2E Test Infra: Smart Home Voice AI — Phase 7 UI Overhaul

## Test Philosophy
- Opaque-box, requirement-driven. No dependency on implementation design.
- Methodology: Category-Partition + BVA + Pairwise + Workload Testing.
- Viewports verified: Desktop (1280x800), Mobile small (360x780), Mobile standard (390x844), Mobile large (430x932).

## Feature Inventory
| # | Feature | Source (requirement) | Tier 1 | Tier 2 | Tier 3 |
|---|---------|---------------------|:------:|:------:|:------:|
| 1 | Dedicated GET `/login` | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 2 | Dedicated GET `/register` | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 3 | Minimalist Login Gate on `/` & `/app` | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 4 | Mobile 360-460px Header 2 Rows & Ellipsis | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 5 | 3D Overlay Chips Collision & Clamping | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 6 | Optimistic UI on `/app` Device Toggles | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 7 | Streamlined Voice Auth Setup on `/auth` | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ |
| 8 | Shared 8-Destination Navigation | ORIGINAL_REQUEST §R5 | 5 | 5 | ✓ |

## Test Architecture
- Test runner: `pytest`
- Security challenger: `tests/test_challenger_m4_security.py`
- Browser automation: Playwright Chromium (`test_phase7_ui_e2e_playwright.py`)
- Purity invariants: 0 `<style>`, 0 inline `<script>`, 0 CRLF (100% POSIX LF)

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Mobile login at 360px -> Navigate to Overview -> Check header 2 rows and 3D chips | F1, F3, F4, F5, F8 | High |
| 2 | Mobile PWA `/app` -> Fast device toggle -> Verify optimistic DOM update & pending guard | F6 | High |
| 3 | Voice Auth `/auth` -> 3-field setup -> Proceed to Voice Recording Step 2 | F7, F8 | Medium |
| 4 | Shared Nav loop across all 8 routes on desktop and mobile without console errors | F1, F2, F8 | Medium |
| 5 | Registration on `/register` -> Direct transition to `/login` | F1, F2 | Medium |
