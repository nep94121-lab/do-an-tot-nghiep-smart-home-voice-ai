# Task: Remediation Explorer 2 - Serialization & Python Persistence Audit (Milestone 1)
Role: teamwork_explorer
Mission: Inspect all serialization and file write methods in the entire codebase (especially `simulator/auth_3layer.py`, `simulator/`, `simulator/api/`) to ensure every write operation specifies POSIX LF (`write_bytes(payload.encode('utf-8'))` or `newline='\n'`) to guarantee 0 CRLF even when running on Windows.
