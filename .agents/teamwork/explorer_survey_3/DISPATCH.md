## 2026-11-05T05:34:08Z
[Message] sender=91485de0-7c6f-449a-ba3f-ed6820ebb01a priority=MESSAGE_PRIORITY_HIGH
You are Explorer 3 (survey_exp3), a read-only exploration agent with archetype teamwork_explorer.
Your working directory is: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\explorer_survey_3
You MUST read ORIGINAL_REQUEST.md at: C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\ORIGINAL_REQUEST.md before starting work.

Codebase Knowledge Graph Context (codebase-memory-mcp):
- Tier: Tier 2 (Verify)
- Project: C-Users-LENOVO-datn-wt-p6-otp
- Generation: 2026-11-05T03:54:00Z
- Relevant paths:
  * simulator/auth/invite_and_gmail_mixin.py (email formatting, MIME message construction, read_latest_otp_from_gmail_inbox)
  * simulator/api/routes_auth.py (/api/auth3/read_gmail_otp, forgot_password_send_otp)
  * tests/test_phase5_r3_otp_email.py, tests/test_challenger_phase5_r2_r3.py (existing tests for email formatting & OTP extraction)

Your Mission:
Investigate Requirement R3: Email RFC 5322 Standards and Deliverability.
1. Inspect outgoing email MIME construction in simulator/auth/invite_and_gmail_mixin.py:
   - Check headers: From, Date, Message-ID, Reply-To, To, Subject.
   - Ensure From is formatted with email.utils.formataddr(('Smart Home Voice AI', sender_addr)).
   - Ensure Date header uses email.utils.formatdate(localtime=True).
   - Ensure Message-ID uses email.utils.make_msgid(domain=...).
   - Ensure Reply-To header is properly set.
   - Inspect Subject formatting: MUST NOT contain OTP codes, ALL-CAPS words, or emojis.
   - Inspect Message body: MUST be MIME multipart/alternative containing both clean text/plain and light-background HTML (zero emojis, clean styling, no deceptive Google OAuth branding).
2. Inspect read_latest_otp_from_gmail_inbox in simulator/auth/invite_and_gmail_mixin.py and routes_auth.py:
   - How does it query Gmail (IMAP or API or gws)?
   - What subject pattern and body regex does it search for?
   - Update recommendations for search query and extraction logic so it reliably finds and parses OTP codes with the new subject and multipart structure without failing.
3. Review existing test cases in tests/test_phase5_r3_otp_email.py and tests/test_challenger_phase5_r2_r3.py to identify any test assertions that assume the old subject format or single-part body, and provide recommended updates.

Constraints:
- You are read-only. DO NOT edit or create any production code or test files.
- DO NOT read, write, or print SMTP secret values.
- Write your findings, exact line references, call traces, and concrete implementation recommendations to:
  C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\explorer_survey_3\survey_report.md
- Write your final soft handoff report to:
  C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\explorer_survey_3\handoff.md
- Update your progress.md regularly for heartbeat liveness.
- Once finished, send a message to the orchestrator with the path to your handoff.md.
