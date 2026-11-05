import pathlib
import re
import json

ROOT = pathlib.Path(".")

# 1. CRLF and BOM check on all modified and new files
files_to_check = [
    "simulator/server.py",
    "vercel.json",
    "simulator/static/login.html",
    "simulator/static/register.html",
    "simulator/static/js/auth_pages.js",
    "simulator/static/css/style.css",
    "simulator/static/css/guest_enroll.css",
    "simulator/static/index.html",
    "simulator/static/auth.html",
    "simulator/static/wokwi.html",
    "simulator/static/logs.html",
    "simulator/static/guest_enroll.html",
    "mobile_app/index.html",
    "tests/test_milestone_m1_navigation_routing.py",
]

print("=== 1. CRLF & BOM CHECK ===")
for f in files_to_check:
    p = ROOT / f
    assert p.exists(), f"Missing {f}"
    data = p.read_bytes()
    crlf_count = data.count(b"\r\n")
    has_bom = data.startswith(b"\xef\xbb\xbf")
    assert crlf_count == 0, f"{f} has {crlf_count} CRLF!"
    assert not has_bom, f"{f} has UTF-8 BOM!"
    print(f"PASS: {f} (size={len(data)}B, 0 CRLF, 0 BOM)")

# 2. HTML PURITY CHECK
print("\n=== 2. HTML PURITY CHECK ===")
html_files = [
    "simulator/static/index.html",
    "simulator/static/auth.html",
    "simulator/static/wokwi.html",
    "simulator/static/logs.html",
    "simulator/static/guest_enroll.html",
    "simulator/static/login.html",
    "simulator/static/register.html",
    "mobile_app/index.html",
]
for h in html_files:
    content = (ROOT / h).read_text(encoding="utf-8")
    style_matches = re.findall(r"<style\b", content, re.IGNORECASE)
    assert len(style_matches) == 0, f"{h} contains {len(style_matches)} <style> tags!"
    script_matches = re.findall(r"<script\b([^>]*)>", content, re.IGNORECASE)
    inline_scripts = [s for s in script_matches if "src=" not in s.lower()]
    assert len(inline_scripts) == 0, f"{h} contains {len(inline_scripts)} inline <script> tags!"
    print(f"PASS: {h} (0 <style>, 0 inline <script>)")

# 3. VERCEL ROUTING ADVERSARIAL REGEX CHECK
print("\n=== 3. VERCEL ROUTING ADVERSARIAL REGEX CHECK ===")
v = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
routes = v["routes"]

def simulate(path):
    for r in routes:
        if re.search(r["src"], path):
            return r
    return None

login_r = simulate("/login")
assert login_r["dest"] == "/simulator/static/login.html", f"Expected /login -> login.html, got {login_r}"
login_slash_r = simulate("/login/")
assert login_slash_r["dest"] == "/simulator/static/login.html", f"Expected /login/ -> login.html, got {login_slash_r}"

reg_r = simulate("/register")
assert reg_r["dest"] == "/simulator/static/register.html", f"Expected /register -> register.html, got {reg_r}"
reg_slash_r = simulate("/register/")
assert reg_slash_r["dest"] == "/simulator/static/register.html", f"Expected /register/ -> register.html, got {reg_slash_r}"

# Adversarial attempts
hijack_login = simulate("/login_attacker")
assert hijack_login["status"] == 404, f"/login_attacker was hijacked! Matched: {hijack_login}"
hijack_reg = simulate("/register_attacker")
assert hijack_reg["status"] == 404, f"/register_attacker was hijacked! Matched: {hijack_reg}"
hijack_sub = simulate("/login/evil/path")
assert hijack_sub["status"] == 404, f"/login/evil/path was hijacked! Matched: {hijack_sub}"
print("PASS: Vercel routing regexes ^/login/?$ and ^/register/?$ are strictly anchored and resist hijacking!")

# 4. CREDENTIAL VALUE SANITY
print("\n=== 4. CREDENTIAL VALUE INVARIANT CHECK ===")
for page in ["simulator/static/login.html", "simulator/static/register.html"]:
    c = (ROOT / page).read_text(encoding="utf-8")
    inputs = re.findall(r"<input\b([^>]*)>", c, re.IGNORECASE)
    for inp in inputs:
        val_match = re.search(r'value="([^"]*)"', inp)
        if val_match:
            assert val_match.group(1) == "", f"Input in {page} has non-empty hardcoded value: {val_match.group(1)}"
    print(f"PASS: {page} inputs have strictly empty value=\"\"")

# 5. VOICE BACKEND IMMUTABILITY
print("\n=== 5. VOICE BACKEND IMMUTABILITY CHECK ===")
import subprocess
diff_out = subprocess.check_output(["git", "diff", "--stat", "HEAD", "--", "simulator/voice/", "simulator/voice_auth.py", "simulator/live/"]).decode("utf-8").strip()
assert diff_out == "", f"Voice backend was touched! Diff: {diff_out}"
print("PASS: Voice backend files strictly untouched (0 bytes modified)")

print("\n=== ALL ORTHOGONAL AUDIT CHECKS PASSED SUCCESSFULLY ===")
