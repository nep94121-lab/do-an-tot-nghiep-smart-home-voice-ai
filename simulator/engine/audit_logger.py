"""Module simulator.engine.audit_logger: Ghi và đọc nhật ký hệ thống bền vững (JSONL + SQLite)."""

from __future__ import annotations

import json
from typing import Any

from simulator.engine.constants_and_time import AUDIT_LOG_FILE, get_vn_now
from simulator.voice_config import (
    redact_otp_and_secrets_in_text,
    sanitize_overview_and_logs_payload,
)

_AUDIT_JSONL_REDACTED_ON_BOOT = False


def redact_stored_audit_logs_jsonl() -> int:
    """Quét và làm sạch toàn bộ mã OTP / mật khẩu / voiceprint cũ trong system_audit_logs.jsonl."""
    global _AUDIT_JSONL_REDACTED_ON_BOOT
    _AUDIT_JSONL_REDACTED_ON_BOOT = True
    if not AUDIT_LOG_FILE.exists():
        return 0
    try:
        raw_text = AUDIT_LOG_FILE.read_text(encoding="utf-8")
        lines = raw_text.splitlines()
        cleaned_lines: list[str] = []
        changed = 0
        for ln in lines:
            ln_s = ln.strip()
            if not ln_s:
                continue
            try:
                obj = json.loads(ln_s)
                sanitized_obj = sanitize_overview_and_logs_payload(obj)
                new_ln = json.dumps(sanitized_obj, ensure_ascii=False)
                if new_ln != ln_s:
                    changed += 1
                cleaned_lines.append(new_ln)
            except Exception:
                redacted_ln = redact_otp_and_secrets_in_text(ln_s)
                if redacted_ln != ln_s:
                    changed += 1
                cleaned_lines.append(redacted_ln)
        if changed > 0:
            new_content = ("\n".join(cleaned_lines) + "\n") if cleaned_lines else ""
            AUDIT_LOG_FILE.write_bytes(new_content.encode("utf-8"))
        return changed
    except Exception:
        return 0


def append_audit_log(
    category: str,
    event_type: str,
    summary: str,
    user_name: str = "Hệ thống",
    tier: int = 1,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ghi nhật ký bền vững (Persistent Audit Log) xuống đĩa tại simulator/data/system_audit_logs.jsonl."""
    if not _AUDIT_JSONL_REDACTED_ON_BOOT:
        redact_stored_audit_logs_jsonl()
    now_dt = get_vn_now()
    safe_summary = redact_otp_and_secrets_in_text(str(summary or ""))
    safe_details = sanitize_overview_and_logs_payload(details or {})
    entry = {
        "ts_iso": now_dt.isoformat(),
        "time_vn": now_dt.strftime("%d/%m/%Y %I:%M:%S %p"),
        "category": category,
        "event_type": event_type,
        "user": user_name,
        "tier": tier,
        "summary": safe_summary,
        "details": safe_details if isinstance(safe_details, dict) else {},
    }
    try:
        from simulator.database_sqlite import insert_audit_log_sqlite
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with AUDIT_LOG_FILE.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line)
        insert_audit_log_sqlite(entry)
    except Exception:
        pass
    return entry


def read_audit_logs(limit: int = 250) -> list[dict[str, Any]]:
    """Đọc danh sách log mới nhất từ simulator/data/system_audit_logs.jsonl."""
    if not _AUDIT_JSONL_REDACTED_ON_BOOT:
        redact_stored_audit_logs_jsonl()
    if not AUDIT_LOG_FILE.exists():
        return []
    try:
        lines = AUDIT_LOG_FILE.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        for ln in reversed(lines[-limit:]):
            ln_s = ln.strip()
            if ln_s:
                try:
                    parsed = json.loads(ln_s)
                    out.append(sanitize_overview_and_logs_payload(parsed))
                except Exception:
                    pass
        return out
    except Exception:
        return []


def clear_audit_logs() -> None:
    """Xóa toàn bộ log trong simulator/data/system_audit_logs.jsonl."""
    try:
        AUDIT_LOG_FILE.write_bytes(b"")
    except Exception:
        pass
