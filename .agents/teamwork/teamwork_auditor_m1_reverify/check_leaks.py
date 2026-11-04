import subprocess
import pathlib
import re

res = subprocess.run(["git", "status", "--short"], capture_output=True, text=True)
print("Git status summary:")
for line in res.stdout.splitlines()[:25]:
    print(" ", line)

sensitive_pattern = re.compile(r'(password\s*=\s*["\'](?!["\']|\*\*\*)[a-zA-Z0-9@_#]+["\'])', re.IGNORECASE)
found_leaks = []

for p in pathlib.Path("simulator").rglob("*.py"):
    text = p.read_text(encoding="utf-8", errors="ignore")
    for idx, l in enumerate(text.splitlines(), 1):
        if "hash" in l.lower() or "field" in l.lower() or "placeholder" in l.lower() or "param" in l.lower():
            continue
        m = sensitive_pattern.search(l)
        if m and not l.strip().startswith("#"):
            found_leaks.append(f"{p}:{idx}: {l.strip()}")

print(f"Plaintext password leaks in simulator python code: {len(found_leaks)}")
for leak in found_leaks:
    print(" ", leak)
assert len(found_leaks) == 0, f"Found plaintext password leak: {found_leaks}"
print("Zero plaintext password leaks verified!")
