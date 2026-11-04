import pathlib

data_dir = pathlib.Path("simulator/data")
print("=== POST-PYTEST SIMULATOR/DATA CRLF INVARIANCE AUDIT ===")
violations = []
data_files = [p for p in sorted(data_dir.glob("*")) if p.is_file() and p.suffix.lower() in (".json", ".jsonl")]

for p in data_files:
    raw = p.read_bytes()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    print(f"{p.name:32} | size: {len(raw):7} B | CRLF: {crlf:5} | Lone LF: {lf:5}")
    if crlf > 0:
        violations.append((p.name, crlf))

print(f"\nTotal JSON/JSONL data files checked: {len(data_files)}")
print(f"Total CRLF violations found: {len(violations)}")
assert len(violations) == 0, f"VIOLATION: Data files have CRLF after pytest run: {violations}"
print("100% 0 CRLF INVARIANCE CONFIRMED AFTER TEST SUITE RUN!")
