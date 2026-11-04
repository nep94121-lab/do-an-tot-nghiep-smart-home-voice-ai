"""Module simulator.engine.audit_logger: Ghi và đọc nhật ký hệ thống bền vững (JSONL + SQLite)."""

from __future__ import annotations

import json
from typing import Any

from simulator.database_sqlite import insert_audit_log_sqlite
from simulator.engine.constants_and_time import AUDIT_LOG_FILE, get_vn_now


def append_audit_log(
    category: str,
    event_type: str,
    summary: str,
    user_name: str = "Hệ thống",
    tier: int = 1,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ghi nhật ký bền vững (Persistent Audit Log) xuống đĩa tại simulator/data/system_audit_logs.jsonl."""
    now_dt = get_vn_now()
    entry = {
        "ts_iso": now_dt.isoformat(),
        "time_vn": now_dt.strftime("%d/%m/%Y %I:%M:%S %p"),
        "category": category,
        "event_type": event_type,
        "user": user_name,
        "tier": tier,
        "summary": summary,
        "details": details or {},
    }
    try:
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with AUDIT_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
        insert_audit_log_sqlite(entry)
    except Exception:
        pass
    return entry


def read_audit_logs(limit: int = 250) -> list[dict[str, Any]]:
    """Đọc danh sách log mới nhất từ simulator/data/system_audit_logs.jsonl."""
    if not AUDIT_LOG_FILE.exists():
        return []
    try:
        lines = AUDIT_LOG_FILE.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        for ln in reversed(lines[-limit:]):
            ln_s = ln.strip()
            if ln_s:
                try:
                    out.append(json.loads(ln_s))
                except Exception:
                    pass
        return out
    except Exception:
        return []


def clear_audit_logs() -> None:
    """Xóa toàn bộ log trong simulator/data/system_audit_logs.jsonl."""
    try:
        AUDIT_LOG_FILE.write_text("", encoding="utf-8")
    except Exception:
        pass
