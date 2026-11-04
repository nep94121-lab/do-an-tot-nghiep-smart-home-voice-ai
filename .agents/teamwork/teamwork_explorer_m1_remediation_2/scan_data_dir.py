import pathlib

def scan_data_dir():
    data_dir = pathlib.Path("simulator/data")
    print("=== SIMULATOR/DATA SCAN ===")
    results = []
    for f in sorted(data_dir.rglob("*")):
        if f.is_file():
            raw = f.read_bytes()
            crlf = raw.count(b"\r\n")
            lf = raw.count(b"\n") - crlf
            has_bom = raw.startswith(b"\xef\xbb\xbf")
            results.append((f.as_posix(), len(raw), crlf, lf, has_bom))
            print(f"{f.as_posix()} | size={len(raw)} | CRLF={crlf} | LF={lf} | BOM={has_bom}")
    return results

if __name__ == "__main__":
    scan_data_dir()
