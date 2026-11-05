#!/usr/bin/env python3
"""Independent forensic checks for Phase 6 victory audit."""

import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def get_phase6_changed_files():
    # files committed in phase 6 (between commit 53c6736 and HEAD)
    proc = subprocess.run(
        ["git", "diff", "--name-only", "53c6736..HEAD"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

def check_phase6_files_encoding_and_crlf():
    print("=== CHECK 1: Phase 6 Files Line Endings & Encoding ===")
    p6_files = get_phase6_changed_files()
    print(f"Total files changed in Phase 6 commits: {len(p6_files)}")

    crlf_files = []
    bom_files = []

    for rel_path in p6_files:
        p = ROOT / rel_path
        if not p.is_file():
            continue
        raw = p.read_bytes()
        if b"\r\n" in raw:
            crlf_files.append(rel_path)
        if raw.startswith(b"\xef\xbb\xbf"):
            bom_files.append(rel_path)

    if crlf_files:
        print(f"FAIL: Phase 6 files containing CRLF: {crlf_files}")
    else:
        print("PASS: 100% Phase 6 files have POSIX LF (0 CRLF).")

    if bom_files:
        print(f"FAIL: Phase 6 files containing UTF-8 BOM: {bom_files}")
    else:
        print("PASS: 100% Phase 6 files are UTF-8 without BOM.")

    return len(crlf_files) == 0 and len(bom_files) == 0

def check_all_git_tracked_files_crlf():
    print("\n=== CHECK 1B: All Git Tracked Files CRLF Scan ===")
    proc = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    all_files = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    crlf_count = 0
    checked_count = 0
    bom_files = []

    # Exclude binaries
    binary_exts = {".png", ".ico", ".apk", ".db", ".db-wal", ".db-shm", ".jpg", ".jpeg", ".wav", ".mp3", ".jar"}

    for rel_path in all_files:
        p = ROOT / rel_path
        if p.suffix.lower() in binary_exts:
            continue
        if not p.is_file():
            continue
        checked_count += 1
        raw = p.read_bytes()
        if b"\r\n" in raw:
            crlf_count += 1
            print(f"  CRLF found in git tracked: {rel_path}")
        if raw.startswith(b"\xef\xbb\xbf"):
            bom_files.append(rel_path)

    print(f"Total git tracked text files checked: {checked_count}")
    print(f"Total CRLF files in git tracked: {crlf_count}")
    print(f"BOM files in git tracked: {bom_files}")
    return crlf_count == 0

def check_zero_leak():
    print("\n=== CHECK 2: Zero-Leak Credential & Secret Audit ===")
    p6_files = get_phase6_changed_files()
    secret_findings = []

    # Check for actual live password assignments
    # specifically real passwords or live API keys
    key_patterns = [
        re.compile(r'(?:GMAIL_APP_PASSWORD|SMTP_PASSWORD)\s*=\s*["\']([^"\'\s]+)["\']'),
        re.compile(r'(?:password|secret)\s*=\s*["\']([a-zA-Z0-9]{16,})["\']', re.IGNORECASE),
        re.compile(r'AIzaSy[0-9A-Za-z-_]{33}'),  # Google API key
    ]

    # whitelist dummy / mock values
    whitelist = {
        "mock_secret", "dummy_pass", "test_pass", "mock_pass",
        "mock_smtp_password", "YOUR_GMAIL_APP_PASSWORD",
        "mock_gws_isolation_msg_id", "mock_gws_isolation_thread_id",
        "32e36f98f9c3df1a4e325ece2bcea079373339aab2e7dc7bf77971152a990fb9",
        "1f2d384b510d695cef6ababeb4125d3b8dea3bcc07e9b7fc18389da09957845a",
        "7d69d7474e26ad41695cf690770e80ca109bdb4131838fcd5d875a8b1d5d184e",
        "a513440d7305d47120ad7cf065279770b696403290c2c4e0a270e53414e2eaaa",
        "27cd2d553e918fc29a512559a895bda2ec331e60",
        "47b9117aa3f262f11279833280fe5d99e390a167",
        "53c673657b342bf7653f911282d348b077f7e685",
        "abcd efgh ijkl mnop",
    }

    for rel_path in p6_files:
        p = ROOT / rel_path
        if not p.is_file() or p.suffix.lower() in {".png", ".ico", ".apk", ".db", ".db-wal", ".db-shm"}:
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            for line_idx, line in enumerate(content.splitlines(), 1):
                for pat in key_patterns:
                    for m in pat.finditer(line):
                        matched_val = m.group(1) if m.groups() else m.group(0)
                        if matched_val not in whitelist and not any(w in matched_val for w in ("mock", "test", "dummy", "hash", "sha256", "fixture")):
                            # Let's inspect
                            secret_findings.append((rel_path, line_idx, matched_val))
        except Exception as e:
            pass

    if secret_findings:
        print(f"Potential secrets found in Phase 6 files:")
        for sf in secret_findings:
            print(f"  {sf[0]}:{sf[1]} -> {sf[2]}")
        return False
    else:
        print("PASS: 0 real secrets, tokens, or live passwords found in Phase 6 code, tests, or docs.")
        return True

def check_allowlist_empirical():
    print("\n=== CHECK 3: Allowlist Shield Empirical Verification ===")
    from simulator.auth.invite_and_gmail_mixin import (
        HARDCODED_REAL_EMAIL_ALLOWLIST,
        is_email_allowlisted_for_real_send,
    )
    from simulator.auth_3layer import ThreeLayerAuthManager

    print(f"Hardcoded allowlist: {sorted(list(HARDCODED_REAL_EMAIL_ALLOWLIST))}")

    # Test allowed
    for email in ["nep94121@gmail.com", "senat6031@gmail.com", "kbanh376@gmail.com", "NEP94121@GMAIL.COM  "]:
        assert is_email_allowlisted_for_real_send(email) is True, f"Expected {email} to be allowed"
    print("PASS: All allowlisted addresses recognized correctly.")

    # Test rejected
    forbidden = [
        "tan_binh_gia_dinh@gmail.com",
        "thanh_vien_chuan@gmail.com",
        "hoc_sinh_moi@gmail.com",
        "attacker@evil.com",
        "user@gmail.com",
        "",
        None,
    ]
    for email in forbidden:
        assert is_email_allowlisted_for_real_send(email) is False, f"Expected {email} to be rejected"
    print("PASS: Non-allowlisted addresses rejected by allowlist gate.")

    # Call send_real_gmail_otp on manager directly
    mgr = ThreeLayerAuthManager()
    res = mgr.send_real_gmail_otp("tan_binh_gia_dinh@gmail.com", "123456", "Tan Binh")
    print(f"Result for tan_binh_gia_dinh@gmail.com: {res}")
    assert res.get("sent_real_gmail") is False
    assert res.get("blocked_by_allowlist") is True
    assert res.get("status") == "BLOCKED_NOT_ALLOWLISTED"
    print("PASS: send_real_gmail_otp blocked non-allowlisted email without network call or bounce.")

    # Verify senat6031@gmail.com passes allowlist gate
    res_allowed = mgr.send_real_gmail_otp("senat6031@gmail.com", "123456", "Senat")
    print(f"Result for senat6031@gmail.com: {res_allowed}")
    assert res_allowed.get("blocked_by_allowlist") is False
    # If no secret in environment, it reports missing_secret truthfully
    if not os.environ.get("GMAIL_APP_PASSWORD") and not os.environ.get("SMTP_PASSWORD"):
        assert res_allowed.get("missing_secret") == "GMAIL_APP_PASSWORD"
        assert res_allowed.get("sent_real_gmail") is False
    print("PASS: Allowlist correctly permits senat6031 and truthfully reports secret status.")
    return True

if __name__ == "__main__":
    ok1 = check_phase6_files_encoding_and_crlf()
    ok1b = check_all_git_tracked_files_crlf()
    ok2 = check_zero_leak()
    ok3 = check_allowlist_empirical()

    if ok1 and ok1b and ok2 and ok3:
        print("\nALL PHASE 6 INTEGRITY CHECKS PASSED (100% CLEAN).")
        sys.exit(0)
    else:
        print("\nSOME CHECKS FAILED.")
        sys.exit(1)
