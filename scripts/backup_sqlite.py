"""Online SQLite WAL backup utility with integrity check and 14-day retention."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import sqlite3
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.db_migrations import resolve_sqlite_db_path, table_row_counts  # noqa: E402

DEFAULT_PROD_DB = pathlib.Path(r"C:\Users\LENOVO\.smarthome_server\data\smarthome.db")
DEFAULT_BACKUP_DIR = pathlib.Path(r"C:\Users\LENOVO\.smarthome_server\backups")


def run_online_backup(
    source_db: pathlib.Path | None = None,
    backup_dir: pathlib.Path | None = None,
    *,
    retention_days: int = 14,
) -> dict[str, Any]:
    src = pathlib.Path(source_db) if source_db is not None else (
        DEFAULT_PROD_DB if DEFAULT_PROD_DB.exists() else resolve_sqlite_db_path()
    )
    if not src.exists():
        return {"ok": False, "error": f"Source DB not found: {src}"}

    bdir = pathlib.Path(backup_dir) if backup_dir is not None else pathlib.Path(
        os.environ.get("SMARTHOME_BACKUP_DIR") or DEFAULT_BACKUP_DIR
    )
    bdir.mkdir(parents=True, exist_ok=True)

    tz = datetime.timezone(datetime.timedelta(hours=7))
    stamp = datetime.datetime.now(tz).strftime("%Y%m%d_%H%M%S")
    dst = bdir / f"smarthome_{stamp}.db"

    src_conn = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True, timeout=10.0)
    dst_conn = sqlite3.connect(str(dst), timeout=10.0)
    dst_conn.row_factory = sqlite3.Row
    try:
        src_conn.backup(dst_conn)
        integrity = str(dst_conn.execute("PRAGMA integrity_check;").fetchone()[0])
        counts = table_row_counts(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    pruned: list[str] = []
    if retention_days > 0 and integrity.lower() == "ok":
        cutoff = time.time() - (retention_days * 86400)
        for cand in sorted(bdir.glob("smarthome_*.db")):
            if cand.resolve() == dst.resolve():
                continue
            try:
                if cand.stat().st_mtime < cutoff:
                    cand.unlink()
                    pruned.append(cand.name)
            except OSError:
                pass

    return {
        "ok": integrity.lower() == "ok",
        "source_db": str(src),
        "backup_file": str(dst),
        "size_bytes": dst.stat().st_size if dst.exists() else 0,
        "integrity_check": integrity,
        "table_counts": counts,
        "pruned_old_backups": pruned,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create verified online SQLite backup.")
    parser.add_argument("--source-db", type=pathlib.Path, default=None)
    parser.add_argument("--backup-dir", type=pathlib.Path, default=None)
    parser.add_argument("--retention-days", type=int, default=14)
    args = parser.parse_args()

    res = run_online_backup(args.source_db, args.backup_dir, retention_days=args.retention_days)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
