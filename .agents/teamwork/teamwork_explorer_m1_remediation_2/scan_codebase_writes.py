import ast
import pathlib
import re

def scan_file_writes():
    sim_dir = pathlib.Path("simulator")
    py_files = sorted(sim_dir.rglob("*.py"))
    
    write_patterns = [
        re.compile(r'\.write_text\s*\('),
        re.compile(r'\.write_bytes\s*\('),
        re.compile(r'open\s*\([^)]*[\'"][wa]'),
        re.compile(r'json\.dump\s*\('),
        re.compile(r'yaml\.dump\s*\('),
        re.compile(r'pickle\.dump\s*\('),
        re.compile(r'\.to_csv\s*\('),
        re.compile(r'\.to_json\s*\('),
    ]

    print(f"Scanning {len(py_files)} python files under simulator/...\n")
    
    findings = []
    for f in py_files:
        try:
            content = f.read_text(encoding="utf-8")
        except Exception as e:
            content = f.read_text(encoding="latin-1")
            
        lines = content.splitlines()
        for idx, line in enumerate(lines, 1):
            for pat in write_patterns:
                if pat.search(line):
                    findings.append({
                        "file": f.as_posix(),
                        "line": idx,
                        "text": line.strip(),
                        "pattern": pat.pattern
                    })
    
    return findings

if __name__ == "__main__":
    findings = scan_file_writes()
    for item in findings:
        print(f"{item['file']}:{item['line']} -> {item['text']}")
    print(f"\nTotal findings: {len(findings)}")
