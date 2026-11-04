import pathlib
import sys

root = pathlib.Path(r"C:\Users\LENOVO\Desktop\đồ án tốt nghiệp")

extensions = {".py", ".kt", ".js", ".html", ".css", ".md", ".sh", ".json", ".yaml", ".yml"}
exclude_dirs = {".git", ".pytest_tmp", "node_modules", ".gradle", "build", ".idea", "__pycache__"}

crlf_files = []
bom_files = []
total_checked = 0

for p in root.rglob("*"):
    if not p.is_file():
        continue
    if any(ex in p.parts for ex in exclude_dirs):
        continue
    if p.suffix.lower() not in extensions:
        continue
    
    total_checked += 1
    try:
        content = p.read_bytes()
    except Exception:
        continue
    
    if content.startswith(b"\xef\xbb\xbf"):
        bom_files.append(str(p.relative_to(root)))
    
    # Check CRLF
    if b"\r\n" in content:
        crlf_files.append(str(p.relative_to(root)))

print(f"Total files checked: {total_checked}")
print(f"BOM files: {len(bom_files)}")
if bom_files:
    print("BOM:", bom_files[:10])
print(f"CRLF files: {len(crlf_files)}")
if crlf_files:
    print("CRLF:", crlf_files[:10])
