import sys
from pathlib import Path

report_path = Path("FIX_REPORT_20261104.md")
raw = report_path.read_bytes()

has_bom = raw.startswith(b"\xef\xbb\xbf")
has_crlf = b"\r\n" in raw
has_cr = b"\r" in raw

try:
    decoded = raw.decode("utf-8")
    valid_utf8 = True
except UnicodeDecodeError as e:
    valid_utf8 = False
    decoded = ""

print(f"BOM: {has_bom}")
print(f"CRLF: {has_crlf}")
print(f"CR alone: {has_cr and not has_crlf}")
print(f"Valid UTF-8: {valid_utf8}")
print(f"Byte count: {len(raw)}")
print(f"Line count: {len(raw.split(b'\n'))}")

if has_bom or has_crlf or not valid_utf8:
    print("VERIFICATION FAILED: encoding or CRLF issue found.")
    sys.exit(1)
else:
    print("VERIFICATION SUCCESSFUL: 0 CRLF and UTF-8 without BOM.")
    sys.exit(0)
