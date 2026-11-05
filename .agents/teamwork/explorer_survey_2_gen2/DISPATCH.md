# Task Assignment: Explorer Survey 2 Replacement (Mobile Responsive & 3D Chips)

You are teamwork_spec_miner / explorer_survey_2_gen2.
Working directory: C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\explorer_survey_2_gen2\
Original Request path: C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\ORIGINAL_REQUEST.md

Your task is to thoroughly survey the codebase for requirement R2:
- Mobile Responsive Layout (360-460px).
  - Collision repulsion and boundary clamping to 3D overlay chips on `/` with reduced font size.
  - Reorganize `.top` header into two rows:
    - Row 1: Overview and connection status
    - Row 2: badge, duration/quota, Logout
  - Email ellipsis truncation to eliminate overlaps shown in `C:\Users\LENOVO\datn-wt\mobile_home_3d_overlap.jpg`.
- Review:
  - `ui_mockups/DESIGN_SYSTEM.md`
  - `simulator/static/index.html` (the 3D canvas and overlay chips structure, `.top` header, IDs and classes)
  - `simulator/static/css/` (styles for `.top`, chips, badges, overlay, responsive breakpoints)
  - `simulator/static/js/` (3D scene scripts, chip positioning/physics, collision logic)
  - Note hard constraint: zero inline scripts in `simulator/static/index.html` and 0 CRLF.

Produce a comprehensive survey report in your working directory at:
`C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\explorer_survey_2_gen2\handoff.md`

When done, send a message to parent with summary and file path.
