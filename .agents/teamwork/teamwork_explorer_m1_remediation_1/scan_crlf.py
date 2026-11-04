import pathlib

targets = ["simulator", "mobile_app", "tests", "scripts"]
found = []
for t in targets:
    for p in pathlib.Path(t).rglob("*"):
        if p.is_file() and not p.name.endswith(".db") and not p.name.endswith(".wav") and not p.name.endswith(".pyc"):
            try:
                raw = p.read_bytes()
                if b"\r\n" in raw:
                    found.append((str(p), raw.count(b"\r\n")))
            except Exception:
                pass

print(f"Total non-binary files with CRLF in targets: {len(found)}")
for path, count in found:
    print(f"  {path}: {count} CRLF")
