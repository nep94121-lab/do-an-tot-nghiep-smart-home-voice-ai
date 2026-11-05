"""API Router for System Logs, SQLite WAL Database and Knowledge Base Management.

Phục vụ giao diện Quản Trị Hệ Thống (simulator/static/logs.html - Feature 17)
và các công cụ thanh tra DevOps CI/CD.
Hỗ trợ cơ chế Dual-Key response schema và 100% route aliases chống 404.
"""

from __future__ import annotations

import json
import pathlib
import re
import time
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse


SENSITIVE_KEY_PATTERN = re.compile(r"(password|hint|secret|token|otp|mat_khau)", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")


def mask_email_address(text: str) -> str:
    """Che địa chỉ email theo chuẩn ký tự đầu + '***@domain' (ví dụ: n***@gmail.com)."""
    if not text:
        return text

    def _repl(match: re.Match[str]) -> str:
        local_part = match.group(1)
        domain_part = match.group(2)
        first_char = local_part[0] if local_part else "*"
        return f"{first_char}***@{domain_part}"

    return EMAIL_PATTERN.sub(_repl, text)


def _mask_string_secrets_and_emails(raw_str: str) -> str:
    t = mask_email_address(raw_str)
    t = re.sub(
        r"((?:Mật khẩu gợi ý|Gợi ý mật khẩu|Mật khẩu)\s*:\s*)([^\s\)]+)",
        r"\1******",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"(Mã\s*OTP(?:\s*[^:\d\n]{0,30})?[:=]\s*)(\d{4,8})",
        r"\1******",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"(\bOTP\s*[:=]\s*)(\d{4,8})",
        r"\1******",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"(Bảng\s*Test\s*\()(\d{4,8})(\))",
        r"\1******\3",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"((?:password|password_plain_hint|password_hint|hint|secret|token|otp|otp_code|otp_code_for_test|otp_code_for_test_table|demo_otp_preview|mat_khau|mk)['\"]?\s*[:=]\s*['\"])([^'\"]+)(['\"])",
        r"\1******\3",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"(\b(?:password|password_plain_hint|password_hint|hint|secret|token|otp|otp_code|otp_code_for_test|otp_code_for_test_table|demo_otp_preview|mat_khau|mk)\b['\"]?\s*[:=]\s*)(?!['\"])([^\s,;}\]\)\"']+)",
        r"\1******",
        t,
        flags=re.IGNORECASE,
    )
    return t


def mask_sensitive_log_data(text: Any) -> Any:
    """Che email, mã OTP, mật khẩu, gợi ý mật khẩu và thông tin xác thực nhạy cảm trong log hiển thị."""
    if isinstance(text, str):
        stripped = text.strip()
        if (stripped.startswith("{") and stripped.endswith("}")) or (
            stripped.startswith("[") and stripped.endswith("]")
        ):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, (dict, list)):
                    masked_parsed = mask_sensitive_log_data(parsed)
                    dumped = json.dumps(masked_parsed, ensure_ascii=False)
                    return _mask_string_secrets_and_emails(dumped)
            except Exception:
                pass
        return _mask_string_secrets_and_emails(text)
    if isinstance(text, dict):
        return {
            (mask_email_address(k) if isinstance(k, str) and "@" in k else k): (
                "******"
                if SENSITIVE_KEY_PATTERN.search(str(k))
                else mask_sensitive_log_data(v)
            )
            for k, v in text.items()
        }
    if isinstance(text, list):
        return [mask_sensitive_log_data(item) for item in text]
    return text

from simulator.api.deps import (
    ROOT,
    _ACTIVE_BRIDGES,
    _REST_ENGINE,
    get_knowledge_rag,
)
from simulator.auth.session_store import resolve_request_session
from simulator.database_sqlite import (
    DATA_DIR,
    clear_audit_logs_sqlite,
    execute_readonly_sql,
    get_sqlite_overview,
    insert_audit_log_sqlite,
    sync_engine_state_to_sqlite,
)
from simulator.rule_engine import (
    append_audit_log,
    clear_audit_logs,
    format_vn_time_ampm,
    read_audit_logs,
)
from simulator.voice_config import sanitize_api_payload

router = APIRouter()

CATEGORY_GROUPS: dict[str, set[str]] = {
    "DEVICE": {"DEVICE", "DEVICE_IO", "DEVICE_GPIO", "HARDWARE_QUERY"},
    "VOICE": {"VOICE", "VOICE_CMD", "VOICE_AUTH", "VOICE_ENROLL", "AUTOMATION"},
    "SECURITY": {"SECURITY", "AUTH_3LAYER", "AUTH_3_LAYER", "RBAC", "SYSTEM", "SYSTEM_EVENT"},
}

PURPOSE_MAP: dict[str, str] = {
    "smarthome.db": "CSDL 8 bảng SQLite 3NF WAL (Thiết bị, Log, Phân quyền, Bể luật)",
    "system_audit_logs.jsonl": "Nhật ký kiểm toán hệ thống Append-Only lưu trữ vĩnh viễn",
    "accounts_3layer.json": "Cơ sở dữ liệu tài khoản xác thực 3 tầng & mã băm bảo mật",
    "voiceprints.json": "Kho vector đặc trưng giọng nói Neural Biometrics 256 chiều",
    "knowledge_base.json": "Kho dữ liệu tri thức hỗ trợ RAG & hỏi đáp nhà thông minh",
    "ir_devices_db.json": "Cơ sở dữ liệu mã lệnh hồng ngoại 38kHz cho thiết bị",
    "esp8266_flash_replica.json": "Bản sao luật và trạng thái nén cho Flash LittleFS ESP8266",
}


def _safe_json(filename: str) -> Any:
    fp = DATA_DIR / filename
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _require_admin_session(request: Request) -> tuple[Any, JSONResponse | None]:
    """Bắt buộc phiên đăng nhập Chủ nhà (Tier 1 ADMIN) cho toàn bộ endpoint nhật ký và CSDL.

    - Chưa đăng nhập / token không hợp lệ -> HTTP 401.
    - Đã đăng nhập nhưng không phải Tier 1 ADMIN (Tier 2 MEMBER, Tier 3 CHILD_GUEST) -> HTTP 403.
    """
    sess = resolve_request_session(request, payload=None, engine=None)
    if not sess.is_authenticated:
        return None, JSONResponse(
            {
                "ok": False,
                "authenticated": False,
                "error": "Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống.",
            },
            status_code=401,
        )
    if sess.tier != 1 or sess.role != "ADMIN":
        return None, JSONResponse(
            {
                "ok": False,
                "authenticated": True,
                "rbac_blocked": True,
                "tier": sess.tier,
                "role": sess.role,
                "error": "Từ chối truy cập! Chỉ Chủ nhà (Admin Cấp 1) mới có quyền truy cập nhật ký và cơ sở dữ liệu hệ thống.",
            },
            status_code=403,
        )
    return sess, None


@router.get("/api/logs/dashboard")
@router.get("/api/server_logs_and_db")
async def api_logs_dashboard(
    request: Request,
    category: str | None = None,
    q: str | None = None,
) -> JSONResponse:
    """Cung cấp dữ liệu toàn diện cho trang Quản trị Nhật ký (/logs) và Mobile Dashboard."""
    sess, err_resp = _require_admin_session(request)
    if err_resp is not None:
        return err_resp

    active_eng = _ACTIVE_BRIDGES[-1].engine if _ACTIVE_BRIDGES else _REST_ENGINE
    is_admin = True
    snap = active_eng.get_snapshot(session=sess)

    storage_files: list[dict[str, Any]] = []
    for fp in sorted(DATA_DIR.glob("*")):
        if fp.is_file():
            st = fp.stat()
            storage_files.append(
                {
                    "name": fp.name,
                    "path": f"simulator/data/{fp.name}",
                    "purpose": PURPOSE_MAP.get(fp.name, "Tệp dữ liệu hệ thống mô phỏng"),
                    "size_bytes": st.st_size,
                    "size_kb": round(st.st_size / 1024.0, 2),
                    "modified_vn": time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(st.st_mtime)),
                }
            )

    kb_data = _safe_json("knowledge_base.json")
    kb_items = kb_data.get("items", []) if isinstance(kb_data, dict) else []

    try:
        sync_engine_state_to_sqlite(active_eng)
        sqlite_ov = get_sqlite_overview()
        if not is_admin:
            for tbl_item in sqlite_ov.get("tables", []):
                if isinstance(tbl_item, dict) and tbl_item.get("table_name") in ("users", "voiceprints"):
                    tbl_item["sample_rows"] = []
    except Exception as exc:
        sqlite_ov = {"ok": False, "error": str(exc), "tables": []}

    table_counts: dict[str, int] = {}
    for t in sqlite_ov.get("tables", []):
        table_counts[str(t.get("table_name"))] = int(t.get("row_count", 0))

    sqlite_wal_info = {
        "journal_mode": sqlite_ov.get("journal_mode", "WAL"),
        "size_kb": round(float(sqlite_ov.get("db_size_bytes", 0)) / 1024.0, 2),
        "tables": table_counts,
    }

    raw_logs = read_audit_logs(limit=300)
    standardized_logs: list[dict[str, Any]] = []
    for raw in raw_logs:
        ts_str = str(raw.get("time_vn") or raw.get("time") or raw.get("ts_iso") or "")
        ev_str = str(raw.get("event") or raw.get("summary") or raw.get("event_type") or "Sự kiện")
        user_str = str(raw.get("actor") or raw.get("user") or raw.get("user_name") or "Hệ thống")
        detail_str = str(raw.get("detail") or raw.get("summary") or "")
        lvl = str(raw.get("level") or ("ERROR" if "lỗi" in ev_str.lower() or "chặn" in ev_str.lower() else "INFO"))
        cat = str(raw.get("category") or "SYSTEM")

        if category and category.strip() and category.strip().upper() != "ALL":
            cat_filter = category.strip().upper()
            allowed_cats = CATEGORY_GROUPS.get(cat_filter, {cat_filter})
            if cat.upper() not in allowed_cats and not any(c in cat.upper() for c in allowed_cats):
                continue

        if q and q.strip():
            q_low = q.strip().lower()
            if (
                q_low not in ev_str.lower()
                and q_low not in user_str.lower()
                and q_low not in detail_str.lower()
            ):
                continue

        masked_ev = mask_sensitive_log_data(ev_str)
        masked_user = mask_sensitive_log_data(user_str)
        masked_detail = mask_sensitive_log_data(detail_str)
        masked_details = mask_sensitive_log_data(raw.get("details") or {})

        item = {
            "time": ts_str,
            "time_vn": ts_str,
            "event": masked_ev,
            "event_type": raw.get("event_type") or "event",
            "actor": masked_user,
            "user": masked_user,
            "user_name": masked_user,
            "detail": masked_detail,
            "summary": masked_detail,
            "level": lvl,
            "category": cat,
            "tier": int(raw.get("tier", 1) or 1),
            "details": masked_details,
        }
        standardized_logs.append(item)

    dht = snap.get("dht11", {}) if isinstance(snap, dict) else {}
    soil = snap.get("soil_moisture", {}) if isinstance(snap, dict) else {}
    hardware_database = {
        "server_connected": active_eng.server_connected,
        "devices": snap.get("devices", {}) if isinstance(snap, dict) else {},
        "dht11": {"temp_c": dht.get("temp_c", 28.5), "humidity_pct": dht.get("humidity_pct", 65.0)},
        "soil_moisture": {"pct": soil.get("soil_moisture_pct", 62.0)},
    }

    user_pools = active_eng.overlay_rules.get("user_pools", {}) or {}
    total_word_maps = sum(len(p.get("word_mappings", {})) for p in user_pools.values() if isinstance(p, dict))
    total_aliases = sum(len(p.get("aliases", {})) for p in user_pools.values() if isinstance(p, dict))
    total_if_else = sum(len(p.get("if_else_rules", [])) for p in user_pools.values() if isinstance(p, dict))
    total_directives = len(active_eng.overlay_rules.get("directives", []))
    automation_database = {
        "active_timers_count": len(getattr(active_eng, "active_timers", {}) or {}),
        "word_mappings_count": total_word_maps,
        "custom_aliases_count": total_aliases,
        "if_else_rules_count": total_if_else,
        "system_directives_count": total_directives,
    }

    connection_pools = [
        {"pool_name": "SQLite WAL Engine (smarthome.db)", "status": "CONNECTED", "latency_ms": 0.4},
        {"pool_name": "ESP8266 MQTT Bridge", "status": "ACTIVE" if active_eng.server_connected else "STANDBY", "latency_ms": 1.2},
        {"pool_name": "Gemini 3.8 Live WebSocket Bridge", "status": "ACTIVE" if _ACTIVE_BRIDGES else "READY", "latency_ms": 8.5},
    ]

    return JSONResponse(
        sanitize_api_payload(
            mask_sensitive_log_data(
                {
                    "ok": True,
                    "server_time_vn": format_vn_time_ampm(),
                    "hardware_database": hardware_database,
                    "automation_database": automation_database,
                    "knowledge_base": kb_items,
                    "total_logs": len(standardized_logs),
                    "sqlite_Wal": sqlite_wal_info,
                    "sqlite_overview": sqlite_ov,
                    "audit_logs": standardized_logs,
                    "storage_files": storage_files,
                    "connection_pools": connection_pools,
                    "snapshot": snap,
                    "all_user_pools": active_eng.overlay_rules.get("user_pools", {}) if is_admin else {},
                    "accounts_3layer": (
                        sanitize_api_payload(mask_sensitive_log_data(_safe_json("accounts_3layer.json")))
                        if is_admin
                        else []
                    ),
                    "ir_devices_db": _safe_json("ir_devices_db.json"),
                    "esp8266_flash_replica": _safe_json("esp8266_flash_replica.json"),
                }
            )
        )
    )


_FORBIDDEN_SQL_KEYWORDS = (
    "accounts_3layer",
    "user_sessions",
    "voiceprint",
    "password",
    "embedding",
    "otp",
    "secret",
    "token",
)


@router.post("/api/logs/sql_query")
@router.post("/api/sqlite/query")
async def api_logs_sql_query(
    request: Request,
    payload: dict[str, Any] = Body(default={}),
) -> JSONResponse:
    """Thực thi câu lệnh SQL chỉ đọc (SELECT, PRAGMA, EXPLAIN) an toàn trên smarthome.db."""
    _, err_resp = _require_admin_session(request)
    if err_resp is not None:
        return err_resp

    sql = str(payload.get("sql", "")).strip()
    sql_low = sql.lower()
    if any(kw in sql_low for kw in _FORBIDDEN_SQL_KEYWORDS):
        return JSONResponse(
            {"ok": False, "error": "Truy vấn bảng hoặc cột nhạy cảm bị từ chối vì lý do bảo mật!"},
            status_code=403,
        )
    try:
        limit = int(payload.get("limit", 100) or 100)
    except (ValueError, TypeError):
        limit = 100
    res = execute_readonly_sql(sql, limit=limit)
    if isinstance(res, dict) and "rows" in res:
        res["rows"] = sanitize_api_payload(mask_sensitive_log_data(res["rows"]))
    return JSONResponse(sanitize_api_payload(mask_sensitive_log_data(res)))


@router.post("/api/logs/knowledge/add")
@router.post("/api/kb_upsert")
async def api_logs_knowledge_add(
    request: Request,
    payload: dict[str, Any] = Body(default={}),
) -> JSONResponse:
    """Thêm hoặc cập nhật tri thức RAG vào knowledge_base.json và bảng knowledge_rag của SQLite."""
    _, err_resp = _require_admin_session(request)
    if err_resp is not None:
        return err_resp

    topic = str(payload.get("topic", "")).strip()
    content = str(payload.get("content", "")).strip()
    keywords = str(payload.get("keywords", "")).strip()
    try:
        min_tier = int(payload.get("min_tier", 3) or 3)
    except (ValueError, TypeError):
        min_tier = 3
    res = get_knowledge_rag().upsert_knowledge_item(
        topic=topic,
        content=content,
        keywords=keywords,
        min_tier=min_tier,
        current_tier=1,
    )
    if res.get("ok"):
        append_audit_log(
            category="KNOWLEDGE_BASE",
            event_type="kb_upserted",
            summary=f"Đã lưu mục KB '{topic}': {content}",
            user_name="Nguyễn Tuấn Anh (Admin Cấp 1)",
            tier=1,
            details=res.get("item", {}),
        )
    return JSONResponse(sanitize_api_payload(mask_sensitive_log_data(res)))


@router.post("/api/logs/append")
async def api_logs_append(
    request: Request,
    payload: dict[str, Any] = Body(default={}),
) -> JSONResponse:
    """Tiếp nhận bản ghi log thủ công từ client hoặc demo event ghi bền vững."""
    _, err_resp = _require_admin_session(request)
    if err_resp is not None:
        return err_resp

    cat = str(payload.get("category", "SYSTEM"))
    ev = str(payload.get("event", "Client Event"))
    actor = str(payload.get("actor", "Hệ thống"))
    detail = str(payload.get("detail", ""))
    lvl = str(payload.get("level", "INFO"))
    append_audit_log(
        category=cat,
        event_type="client_manual_log",
        summary=f"[{lvl}] {ev} - {detail}".strip(),
        user_name=actor,
        tier=1,
        details={"detail": detail, "level": lvl},
    )
    return JSONResponse({"ok": True})


@router.post("/api/logs/clear")
@router.post("/api/clear_audit_logs")
async def api_logs_clear(request: Request) -> JSONResponse:
    """Làm sạch nhật ký kiểm toán hệ thống theo lệnh của Quản trị viên Cấp 1."""
    _, err_resp = _require_admin_session(request)
    if err_resp is not None:
        return err_resp

    clear_audit_logs()
    clear_audit_logs_sqlite()
    append_audit_log(
        category="SYSTEM_EVENT",
        event_type="logs_cleared",
        summary="Đã làm sạch nhật ký hệ thống theo yêu cầu của Admin.",
        user_name="Nguyễn Tuấn Anh (Admin Cấp 1)",
        tier=1,
    )
    return JSONResponse({"ok": True, "message": "Đã dọn sạch nhật ký kiểm toán."})


@router.get("/api/sqlite/overview")
async def api_sqlite_overview(request: Request) -> JSONResponse:
    """Trả về tổng quan 8 bảng CSDL SQLite smarthome.db."""
    _, err_resp = _require_admin_session(request)
    if err_resp is not None:
        return err_resp

    ov = get_sqlite_overview()
    return JSONResponse(sanitize_api_payload(mask_sensitive_log_data(ov)))


@router.get("/api/devops/status")
async def api_devops_status(request: Request) -> JSONResponse:
    """Trả về biên lai DevOps 5 cổng và trạng thái CI/CD."""
    _, err_resp = _require_admin_session(request)
    if err_resp is not None:
        return err_resp

    receipt_path = ROOT / "docs" / "kien_truc" / "DEVOPS_RELEASE_RECEIPT.json"
    if receipt_path.exists():
        try:
            return JSONResponse(
                sanitize_api_payload(
                    mask_sensitive_log_data(json.loads(receipt_path.read_text(encoding="utf-8")))
                )
            )
        except Exception as exc:
            return JSONResponse({"ok": False, "error": f"Lỗi đọc biên lai DevOps: {exc}"}, status_code=500)
    return JSONResponse({"ok": False, "error": "Chưa tìm thấy tệp biên lai DevOps Release Receipt."}, status_code=404)
