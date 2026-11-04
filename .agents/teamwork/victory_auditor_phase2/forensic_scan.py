import os
import re
import subprocess

def run():
    print("=== FORENSIC SCAN ===")
    # 1. Non-agent log files tracked in git
    tracked = subprocess.check_output(["git", "ls-files"], text=True, encoding="utf-8").splitlines()
    non_agent_logs = [f for f in tracked if f.endswith('.log') and not f.startswith('.agents/')]
    print(f"Tracked log files outside .agents: {non_agent_logs}")

    # 2. Check commit 26e7afa diff for sensitive patterns
    diff = subprocess.check_output(["git", "show", "26e7afa"], text=True, encoding="utf-8")
    
    # Check for hardcoded OTPs in production code lines added (+)
    added_lines = [l for l in diff.splitlines() if l.startswith('+') and not l.startswith('+++')]
    suspicious = []
    for l in added_lines:
        if any(w in l.lower() for w in ["secret_key =", "private_key", "password =", "bearer "]):
            # Filter out test fixtures or documentation
            if not any(f in l for f in ["test", "fixture", "dummy", "example", "mock"]):
                suspicious.append(l.strip())
                
    print(f"Suspicious sensitive lines added: {len(suspicious)}")
    for s in suspicious[:10]:
        print("  - ", s)

    # 3. Check for CRLF line endings across project files
    crlf_files = []
    critical_files = [
        "simulator/server.py",
        "simulator/static/sw.js",
        "simulator/static/offline.html",
        "simulator/static/404.html",
        "simulator/static/500.html",
        "simulator/static/qr_expired.html",
        "simulator/static/403.html",
        "simulator/static/index.html",
        "simulator/static/js/app.js",
        "simulator/static/css/style.css",
        "mobile_app/index.html",
        "simulator/static/js/mobile_app.js",
        "simulator/static/css/mobile_app.css",
        "FIX_REPORT_20261104.md"
    ]
    for cf in critical_files:
        if os.path.exists(cf):
            with open(cf, 'rb') as f:
                content = f.read()
                if b'\r\n' in content:
                    crlf_files.append(cf)
    print(f"CRLF files found in critical deliverables: {crlf_files}")

    # 4. Check for inline scripts in HTML files
    inline_script_issues = []
    html_files = [
        "simulator/static/offline.html",
        "simulator/static/404.html",
        "simulator/static/500.html",
        "simulator/static/qr_expired.html",
        "simulator/static/403.html",
        "simulator/static/index.html",
        "mobile_app/index.html"
    ]
    for hf in html_files:
        if os.path.exists(hf):
            with open(hf, 'r', encoding='utf-8') as f:
                content = f.read()
                # Check for inline <script> that is not a src link
                matches = re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', content, re.DOTALL | re.IGNORECASE)
                # Filter out permissible bootstrap scripts if any
                if matches and hf in ["simulator/static/index.html"]:
                    inline_script_issues.append((hf, len(matches)))
    print(f"Inline script issues in index.html: {inline_script_issues}")

if __name__ == "__main__":
    run()
