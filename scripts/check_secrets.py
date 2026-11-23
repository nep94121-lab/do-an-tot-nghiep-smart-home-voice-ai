"""Repository secret scanner for release hygiene verification."""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Google API key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("GitHub classic PAT", re.compile(r"ghp_[0-9A-Za-z]{36}")),
    ("GitHub fine-grained PAT", re.compile(r"github_pat_[0-9A-Za-z_]{20,}")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("Slack token", re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}")),
)

TEXT_EXTS = {
    ".py", ".js", ".html", ".css", ".json", ".md", ".ps1",
    ".txt", ".yml", ".yaml", ".toml", ".ini", ".sh", ".sql",
    ".kt", ".kts", ".gradle", ".properties", ".ino", ".h", ".c", ".cpp",
}


def main() -> int:
    tracked = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files"], text=True
    ).splitlines()
    hits: list[str] = []
    for rel in tracked:
        p = ROOT / rel
        if not p.is_file() or p.suffix.lower() not in TEXT_EXTS:
            continue
        raw = p.read_bytes()
        if b"\x00" in raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        for label, pat in SECRET_PATTERNS:
            for m in pat.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                hits.append(f"{rel}:{line_no}: {label}")
    if hits:
        for h in hits:
            print(f"ALERT: {h}", file=sys.stderr)
        return 1
    print(f"Security audit scan complete ({len(tracked)} tracked files). Zero secrets confirmed!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
