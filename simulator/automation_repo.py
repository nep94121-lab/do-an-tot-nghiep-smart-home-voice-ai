"""SQLite repository for timers, Asia/Saigon schedules, linked automation rules, and custom scenes."""

from __future__ import annotations

import datetime
import json
import pathlib
import sqlite3
import time
import unicodedata
import uuid
from typing import Any
from zoneinfo import ZoneInfo

from simulator.auth.tier_permissions import DEVICE_LABELS_VI, can_control_device
from simulator.database_sqlite import (
    _DB_LOCK,
    _active_db_path,
    get_connection,
    init_sqlite_database,
)
from simulator.db_migrations import role_for_tier, run_write_transaction
from simulator.engine.constants_and_time import (
    ACTION_TO_STATE,
    ACTION_VI_LABEL,
    DEFAULT_DEVICES,
    STATE_TO_OPPOSITE,
)

try:
    SAIGON_TZ = ZoneInfo("Asia/Saigon")
except Exception:  # pragma: no cover - Windows tzdata fallback
    SAIGON_TZ = datetime.timezone(datetime.timedelta(hours=7), name="Asia/Saigon")


def now_saigon() -> datetime.datetime:
    return datetime.datetime.now(SAIGON_TZ)


def now_saigon_iso() -> str:
    return now_saigon().isoformat()


TIER1_SCHEDULE_CONFLICT_MSG_VI = "Trùng lịch của chủ nhà, em không đặt được ạ."
GUEST_ONLY_TOGGLE_MSG_VI = "Khách chỉ được bật tắt thiết bị thôi ạ."
PENDING_CONFIRM_TTL_SEC = 20.0


def strip_accents(text: str) -> str:
    if not text:
        return ""
    s = str(text).replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in nfkd if unicodedata.category(ch) != "Mn")


def normalize_phrase(phrase: str) -> str:
    cleaned = strip_accents(str(phrase or "").strip().lower())
    out = []
    for ch in cleaned:
        if ch.isalnum() or ch.isspace():
            out.append(ch)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def format_device_action_vi(device_id: str, action: str) -> str:
    dname = DEVICE_LABELS_VI.get(device_id) or DEFAULT_DEVICES.get(device_id, {}).get("name") or device_id
    act = str(action or "").strip().lower()
    if device_id == "main_door":
        verb = "Mở" if act in ("open", "turn_on") else "Đóng"
    elif device_id == "ac":
        verb = "Mở" if act in ("open", "turn_on") else "Tắt"
    else:
        verb = ACTION_VI_LABEL.get(act, "Bật" if act in ("open", "turn_on") else "Tắt")
    return f"{verb} {dname.lower()}"


def _ensure_fk_parents(
    conn: sqlite3.Connection,
    *,
    owner_user_id: str,
    owner_tier: int,
    owner_name: str = "",
) -> str:
    """Ensure users and default devices rows exist before FK-constrained writes."""
    now_iso = now_saigon_iso()
    for did, dinfo in DEFAULT_DEVICES.items():
        min_t = 1 if did in ("main_door", "alarm_siren") else (2 if did in ("ac", "garden_pump") else 3)
        conn.execute(
            """
            INSERT OR IGNORE INTO devices (
                device_id, device_name, gpio_pin, state, min_tier_required,
                offline_controllable, updated_at, min_role, room, device_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                did,
                str(dinfo.get("name") or did),
                str(dinfo.get("gpio") or "GPIO").split(" ", 1)[0],
                str(dinfo.get("state") or "OFF"),
                min_t,
                0 if did in ("main_door", "alarm_siren") else 1,
                now_iso,
                role_for_tier(min_t),
                str(dinfo.get("room") or "home"),
                str(dinfo.get("type") or "switch"),
            ),
        )

    uid = str(owner_user_id or "").strip() or "tuan_anh"
    existing = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (uid,)).fetchone()
    if existing is None:
        safe_tier = int(owner_tier) if int(owner_tier or 1) in (1, 2, 3) else 1
        role_code = role_for_tier(safe_tier)
        if uid == "tuan_anh":
            conn.execute(
                """
                INSERT OR IGNORE INTO users (
                    user_id, full_name, role, tier, offline_allowed, created_by, updated_at, role_code
                ) VALUES ('tuan_anh', 'Nguyễn Tuấn Anh', 'ADMIN', 1, 1, 'SYSTEM', ?, 'ADMIN')
                """,
                (now_iso,),
            )
        else:
            conn.execute(
                """
                INSERT OR IGNORE INTO users (
                    user_id, full_name, role, tier, offline_allowed, created_by, updated_at, role_code
                ) VALUES (?, ?, ?, ?, ?, 'SYSTEM', ?, ?)
                """,
                (
                    uid,
                    owner_name or uid,
                    role_code,
                    safe_tier,
                    1 if safe_tier in (1, 2) else 0,
                    now_iso,
                    role_code,
                ),
            )
    return uid


def _resolve_db(db_path: pathlib.Path | None = None) -> pathlib.Path:
    target = pathlib.Path(db_path) if db_path is not None else _active_db_path()
    init_sqlite_database(target)
    return target


_AUTOMATION_CACHE_EPOCH = 0
_AUTOMATION_SNAPSHOT_CACHE: dict[
    str, tuple[int, float, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]
] = {}
_AUTOMATION_CACHE_TTL_SEC = 10.0


def invalidate_automation_cache(db_path: pathlib.Path | None = None) -> None:
    """Invalidate in-RAM automation snapshot bundle cache after writes/deletes."""
    global _AUTOMATION_CACHE_EPOCH
    with _DB_LOCK:
        _AUTOMATION_CACHE_EPOCH += 1
        _AUTOMATION_SNAPSHOT_CACHE.clear()


# =============================================================================
# TIMERS POOL (SQLite persistence for timers_pool)
# =============================================================================

def upsert_timer_row(
    *,
    timer_id: str,
    owner_user_id: str,
    owner_tier: int,
    device_id: str,
    action: str,
    fire_at_epoch: float,
    delay_seconds: float,
    repeat_rule: str = "once",
    schedule_mode: str = "countdown",
    target_time_vn: str = "",
    label: str = "",
    status: str = "pending",
    owner_name: str = "",
    db_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    now_ts = time.time()
    now_iso = now_saigon_iso()
    dev_fk = device_id if device_id in DEFAULT_DEVICES else "living_room_light"
    mode_val = schedule_mode if device_id == dev_fk else f"{schedule_mode}:{device_id}"
    clean_label = str(label or format_device_action_vi(dev_fk, action)).strip()

    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> None:
                uid = _ensure_fk_parents(
                    c, owner_user_id=owner_user_id, owner_tier=owner_tier, owner_name=owner_name
                )
                c.execute(
                    """
                    INSERT INTO timers_pool (
                        timer_id, owner_user_id, device_id, action, schedule_mode,
                        target_time_vn, repeat_rule, label_summary, updated_at,
                        fire_at_epoch, delay_seconds, status, owner_tier, label, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(timer_id) DO UPDATE SET
                        owner_user_id = excluded.owner_user_id,
                        device_id = excluded.device_id,
                        action = excluded.action,
                        schedule_mode = excluded.schedule_mode,
                        target_time_vn = excluded.target_time_vn,
                        repeat_rule = excluded.repeat_rule,
                        label_summary = excluded.label_summary,
                        updated_at = excluded.updated_at,
                        fire_at_epoch = excluded.fire_at_epoch,
                        delay_seconds = excluded.delay_seconds,
                        status = excluded.status,
                        owner_tier = excluded.owner_tier,
                        label = excluded.label
                    """,
                    (
                        str(timer_id),
                        uid,
                        dev_fk,
                        str(action),
                        mode_val,
                        str(target_time_vn or ""),
                        str(repeat_rule or "once"),
                        clean_label,
                        now_iso,
                        float(fire_at_epoch),
                        float(delay_seconds),
                        str(status or "pending"),
                        int(owner_tier if owner_tier in (1, 2, 3) else 1),
                        clean_label,
                        now_ts,
                    ),
                )

            run_write_transaction(conn, _tx)
        finally:
            conn.close()
    invalidate_automation_cache(db_path)
    return {
        "timer_id": timer_id,
        "device_id": dev_fk,
        "action": action,
        "fire_at_epoch": float(fire_at_epoch),
        "status": status,
        "label": clean_label,
    }


def update_timer_status(
    timer_id: str,
    status: str,
    *,
    fire_at_epoch: float | None = None,
    db_path: pathlib.Path | None = None,
) -> bool:
    now_iso = now_saigon_iso()
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> int:
                if fire_at_epoch is not None:
                    cur = c.execute(
                        "UPDATE timers_pool SET status = ?, fire_at_epoch = ?, updated_at = ? WHERE timer_id = ?",
                        (str(status), float(fire_at_epoch), now_iso, str(timer_id)),
                    )
                else:
                    cur = c.execute(
                        "UPDATE timers_pool SET status = ?, updated_at = ? WHERE timer_id = ?",
                        (str(status), now_iso, str(timer_id)),
                    )
                return int(cur.rowcount or 0)

            return run_write_transaction(conn, _tx) > 0
        finally:
            conn.close()


def delete_timer_row(timer_id: str, *, db_path: pathlib.Path | None = None) -> bool:
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> int:
                cur = c.execute("DELETE FROM timers_pool WHERE timer_id = ?", (str(timer_id),))
                return int(cur.rowcount or 0)

            return run_write_transaction(conn, _tx) > 0
        finally:
            conn.close()


def clear_all_timers_rows(*, db_path: pathlib.Path | None = None) -> None:
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            run_write_transaction(conn, lambda c: c.execute("DELETE FROM timers_pool"))
        finally:
            conn.close()


def list_pending_timers(
    *,
    owner_user_id: str | None = None,
    db_path: pathlib.Path | None = None,
) -> list[dict[str, Any]]:
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            sql = """
                SELECT tp.timer_id, tp.owner_user_id, COALESCE(u.full_name, tp.owner_user_id) AS owner_name,
                       tp.owner_tier, tp.device_id, tp.action, tp.schedule_mode,
                       tp.target_time_vn, tp.repeat_rule, tp.label_summary, tp.label,
                       tp.fire_at_epoch, tp.delay_seconds, tp.status, tp.created_at
                FROM timers_pool tp
                LEFT JOIN users u ON u.user_id = tp.owner_user_id
                WHERE LOWER(COALESCE(tp.status, 'pending')) = 'pending'
            """
            params: tuple[Any, ...] = ()
            if owner_user_id is not None and str(owner_user_id).strip():
                sql += " AND tp.owner_user_id = ? "
                params = (str(owner_user_id).strip(),)
            sql += " ORDER BY tp.fire_at_epoch ASC, tp.created_at ASC"
            rows = conn.execute(sql, params).fetchall()
            out: list[dict[str, Any]] = []
            for r in rows:
                smode = str(r["schedule_mode"] or "countdown")
                raw_target = smode.split(":", 1)[1] if ":" in smode else str(r["device_id"])
                out.append({
                    "id": str(r["timer_id"]),
                    "timer_id": str(r["timer_id"]),
                    "owner_id": str(r["owner_user_id"]),
                    "owner_user_id": str(r["owner_user_id"]),
                    "owner_name": str(r["owner_name"]),
                    "owner_tier": int(r["owner_tier"] or 1),
                    "device_id": str(r["device_id"]),
                    "raw_target": raw_target,
                    "action": str(r["action"]),
                    "target_vn_time": str(r["target_time_vn"] or ""),
                    "repeat": str(r["repeat_rule"] or "once"),
                    "label": str(r["label"] or r["label_summary"] or ""),
                    "fire_at": float(r["fire_at_epoch"] or 0.0),
                    "delay_seconds": float(r["delay_seconds"] or 0.0),
                    "status": str(r["status"] or "pending"),
                    "created_at": float(r["created_at"] or 0.0),
                })
            return out
        finally:
            conn.close()


# =============================================================================
# CLOCK SCHEDULES (Asia/Saigon, once / daily)
# =============================================================================

def _list_schedules_in_conn(conn: sqlite3.Connection, *, include_disabled: bool = True) -> list[dict[str, Any]]:
    sql = """
        SELECT s.schedule_id, s.owner_user_id, COALESCE(u.full_name, s.owner_user_id) AS owner_name,
               s.owner_tier, s.device_id, s.action, s.time_hhmm, s.schedule_type,
               s.run_date_vn, s.timezone, s.enabled, s.last_fired_date_vn,
               s.label, s.created_at, s.updated_at
        FROM schedules s
        LEFT JOIN users u ON u.user_id = s.owner_user_id
    """
    if not include_disabled:
        sql += " WHERE s.enabled = 1 "
    sql += " ORDER BY s.enabled DESC, s.time_hhmm ASC, s.created_at DESC"
    rows = conn.execute(sql).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        did = str(r["device_id"])
        dname = DEVICE_LABELS_VI.get(did) or DEFAULT_DEVICES.get(did, {}).get("name") or did
        act = str(r["action"])
        out.append({
            "id": str(r["schedule_id"]),
            "schedule_id": str(r["schedule_id"]),
            "owner_user_id": str(r["owner_user_id"]),
            "owner_name": str(r["owner_name"]),
            "owner_tier": int(r["owner_tier"] or 1),
            "device_id": did,
            "device_name": dname,
            "action": act,
            "action_vi": ACTION_VI_LABEL.get(act, act),
            "time_hhmm": str(r["time_hhmm"]),
            "schedule_type": str(r["schedule_type"] or "once"),
            "repeat": str(r["schedule_type"] or "once"),
            "run_date_vn": str(r["run_date_vn"] or ""),
            "timezone": str(r["timezone"] or "Asia/Saigon"),
            "enabled": bool(int(r["enabled"] or 0)),
            "last_fired_date_vn": str(r["last_fired_date_vn"] or ""),
            "label": str(r["label"] or f"{format_device_action_vi(did, act)} lúc {r['time_hhmm']}"),
            "created_at": float(r["created_at"] or 0.0),
            "updated_at": float(r["updated_at"] or 0.0),
        })
    return out


def list_schedules(
    *,
    include_disabled: bool = True,
    owner_user_id: str | None = None,
    db_path: pathlib.Path | None = None,
) -> list[dict[str, Any]]:
    scheds, _, _ = get_automation_snapshot_bundle(db_path=db_path)
    out = scheds if include_disabled else [s for s in scheds if s.get("enabled")]
    if owner_user_id is not None and str(owner_user_id).strip():
        uid = str(owner_user_id).strip()
        out = [s for s in out if str(s.get("owner_user_id") or "") == uid]
    return out


def create_schedule(
    *,
    owner_user_id: str,
    owner_tier: int,
    device_id: str,
    action: str,
    time_hhmm: str,
    schedule_type: str = "once",
    run_date_vn: str = "",
    label: str = "",
    enabled: bool = True,
    owner_name: str = "",
    schedule_id: str | None = None,
    db_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    if device_id not in DEFAULT_DEVICES:
        raise ValueError(f"Thiết bị '{device_id}' không hợp lệ.")
    if action not in ACTION_TO_STATE:
        raise ValueError(f"Hành động '{action}' không hợp lệ.")
    st_type = "daily" if str(schedule_type).strip().lower() == "daily" else "once"
    hh, mm = [int(p) for p in str(time_hhmm).strip().split(":", 1)]
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError("Giờ phải nằm trong 00:00 đến 23:59.")
    hhmm_norm = f"{hh:02d}:{mm:02d}"

    now_vn = now_saigon()
    date_vn = str(run_date_vn or "").strip()
    if st_type == "once" and not date_vn:
        target_today = now_vn.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target_today <= now_vn:
            target_today = target_today + datetime.timedelta(days=1)
        date_vn = target_today.strftime("%Y-%m-%d")

    sid = schedule_id or f"sched_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    now_ts = time.time()
    clean_label = str(label or f"{format_device_action_vi(device_id, action)} lúc {hhmm_norm}").strip()

    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> None:
                uid = _ensure_fk_parents(
                    c, owner_user_id=owner_user_id, owner_tier=owner_tier, owner_name=owner_name
                )
                c.execute(
                    """
                    INSERT INTO schedules (
                        schedule_id, owner_user_id, owner_tier, device_id, action,
                        time_hhmm, schedule_type, run_date_vn, timezone, enabled,
                        last_fired_date_vn, label, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Asia/Saigon', ?, '', ?, ?, ?)
                    """,
                    (
                        sid,
                        uid,
                        int(owner_tier if owner_tier in (1, 2, 3) else 1),
                        device_id,
                        action,
                        hhmm_norm,
                        st_type,
                        date_vn,
                        1 if enabled else 0,
                        clean_label,
                        now_ts,
                        now_ts,
                    ),
                )

            run_write_transaction(conn, _tx)
        finally:
            conn.close()
    invalidate_automation_cache(db_path)

    return {
        "id": sid,
        "schedule_id": sid,
        "owner_user_id": owner_user_id,
        "owner_tier": int(owner_tier if owner_tier in (1, 2, 3) else 1),
        "device_id": device_id,
        "device_name": DEVICE_LABELS_VI.get(device_id, device_id),
        "action": action,
        "action_vi": ACTION_VI_LABEL.get(action, action),
        "time_hhmm": hhmm_norm,
        "schedule_type": st_type,
        "repeat": st_type,
        "run_date_vn": date_vn,
        "timezone": "Asia/Saigon",
        "enabled": bool(enabled),
        "last_fired_date_vn": "",
        "label": clean_label,
    }


def update_schedule(
    schedule_id: str,
    *,
    time_hhmm: str | None = None,
    schedule_type: str | None = None,
    device_id: str | None = None,
    action: str | None = None,
    enabled: bool | None = None,
    label: str | None = None,
    db_path: pathlib.Path | None = None,
) -> dict[str, Any] | None:
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            row = conn.execute("SELECT * FROM schedules WHERE schedule_id = ?", (str(schedule_id),)).fetchone()
            if row is None:
                return None
            new_dev = str(device_id or row["device_id"])
            if new_dev not in DEFAULT_DEVICES:
                raise ValueError(f"Thiết bị '{new_dev}' không hợp lệ.")
            new_act = str(action or row["action"])
            if new_act not in ACTION_TO_STATE:
                raise ValueError(f"Hành động '{new_act}' không hợp lệ.")
            new_hhmm = str(row["time_hhmm"])
            if time_hhmm is not None:
                hh, mm = [int(p) for p in str(time_hhmm).strip().split(":", 1)]
                if not (0 <= hh <= 23 and 0 <= mm <= 59):
                    raise ValueError("Giờ phải nằm trong 00:00 đến 23:59.")
                new_hhmm = f"{hh:02d}:{mm:02d}"
            new_type = str(row["schedule_type"] or "once")
            if schedule_type is not None:
                new_type = "daily" if str(schedule_type).strip().lower() == "daily" else "once"
            new_enabled = int(row["enabled"] or 0) if enabled is None else (1 if enabled else 0)
            new_label = str(label) if label is not None else f"{format_device_action_vi(new_dev, new_act)} lúc {new_hhmm}"
            run_date = str(row["run_date_vn"] or "")
            if time_hhmm is not None and new_type == "once":
                now_vn = now_saigon()
                hh, mm = [int(p) for p in new_hhmm.split(":")]
                cand = now_vn.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if cand <= now_vn:
                    cand += datetime.timedelta(days=1)
                run_date = cand.strftime("%Y-%m-%d")

            now_ts = time.time()

            def _tx(c: sqlite3.Connection) -> None:
                c.execute(
                    """
                    UPDATE schedules
                    SET device_id = ?, action = ?, time_hhmm = ?, schedule_type = ?,
                        run_date_vn = ?, enabled = ?, label = ?, updated_at = ?,
                        last_fired_date_vn = CASE WHEN ? IS NOT NULL THEN '' ELSE last_fired_date_vn END
                    WHERE schedule_id = ?
                    """,
                    (
                        new_dev,
                        new_act,
                        new_hhmm,
                        new_type,
                        run_date,
                        new_enabled,
                        new_label,
                        now_ts,
                        time_hhmm,
                        str(schedule_id),
                    ),
                )

            run_write_transaction(conn, _tx)
        finally:
            conn.close()
    invalidate_automation_cache(db_path)
    items = [s for s in list_schedules(include_disabled=True, db_path=db_path) if s["schedule_id"] == schedule_id]
    return items[0] if items else None


def mark_schedule_fired(
    schedule_id: str,
    *,
    fired_date_vn: str,
    disable_after_once: bool,
    db_path: pathlib.Path | None = None,
) -> None:
    now_ts = time.time()
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> None:
                if disable_after_once:
                    c.execute(
                        "UPDATE schedules SET last_fired_date_vn = ?, enabled = 0, updated_at = ? WHERE schedule_id = ?",
                        (str(fired_date_vn), now_ts, str(schedule_id)),
                    )
                else:
                    c.execute(
                        "UPDATE schedules SET last_fired_date_vn = ?, updated_at = ? WHERE schedule_id = ?",
                        (str(fired_date_vn), now_ts, str(schedule_id)),
                    )

            run_write_transaction(conn, _tx)
        finally:
            conn.close()
    invalidate_automation_cache(db_path)


def delete_schedule(schedule_id: str, *, db_path: pathlib.Path | None = None) -> bool:
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> int:
                cur = c.execute("DELETE FROM schedules WHERE schedule_id = ?", (str(schedule_id),))
                return int(cur.rowcount or 0)

            deleted = run_write_transaction(conn, _tx) > 0
        finally:
            conn.close()
    if deleted:
        invalidate_automation_cache(db_path)
    return deleted


# =============================================================================
# LINKED AUTOMATION RULES (when devA=state -> then devB=action)
# =============================================================================

def _rules_have_cycle(edges: list[tuple[str, str]]) -> bool:
    adj: dict[str, set[str]] = {}
    for src, dst in edges:
        if src and dst:
            adj.setdefault(src, set()).add(dst)
    visited: set[str] = set()
    in_stack: set[str] = set()

    def _dfs(node: str) -> bool:
        visited.add(node)
        in_stack.add(node)
        for nxt in adj.get(node, ()):
            if nxt not in visited:
                if _dfs(nxt):
                    return True
            elif nxt in in_stack:
                return True
        in_stack.remove(node)
        return False

    return any(n not in visited and _dfs(n) for n in list(adj.keys()))


def _list_automation_rules_in_conn(conn: sqlite3.Connection, *, include_disabled: bool = False) -> list[dict[str, Any]]:
    sql = """
        SELECT r.rule_id, r.owner_user_id, COALESCE(u.full_name, r.owner_user_id) AS owner_name,
               r.owner_tier, r.when_device_id, r.when_state, r.then_device_id, r.then_action,
               r.else_device_id, r.else_action, r.delay_seconds, r.enabled, r.label,
               r.created_at, r.updated_at
        FROM automation_rules r
        LEFT JOIN users u ON u.user_id = r.owner_user_id
    """
    if not include_disabled:
        sql += " WHERE r.enabled = 1 "
    sql += " ORDER BY r.created_at DESC"
    rows = conn.execute(sql).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        wdev = str(r["when_device_id"])
        tdev = str(r["then_device_id"])
        edev = str(r["else_device_id"] or "")
        wname = DEVICE_LABELS_VI.get(wdev) or DEFAULT_DEVICES.get(wdev, {}).get("name") or wdev
        tname = DEVICE_LABELS_VI.get(tdev) or DEFAULT_DEVICES.get(tdev, {}).get("name") or tdev
        ename = DEVICE_LABELS_VI.get(edev) or DEFAULT_DEVICES.get(edev, {}).get("name") or edev if edev else ""
        out.append({
            "id": str(r["rule_id"]),
            "rule_id": str(r["rule_id"]),
            "owner_id": str(r["owner_user_id"]),
            "owner_user_id": str(r["owner_user_id"]),
            "owner_name": str(r["owner_name"]),
            "owner_tier": int(r["owner_tier"] or 1),
            "when_device_id": wdev,
            "when_device_name": wname,
            "when_state": str(r["when_state"]),
            "then_device_id": tdev,
            "then_device_name": tname,
            "then_action": str(r["then_action"]),
            "else_device_id": edev,
            "else_device_name": ename,
            "else_action": str(r["else_action"] or ""),
            "delay_seconds": float(r["delay_seconds"] or 0.0),
            "enabled": bool(int(r["enabled"] or 0)),
            "label": str(r["label"] or f"Khi {wname}={r['when_state']} thì {format_device_action_vi(tdev, str(r['then_action']))}"),
            "created_at": float(r["created_at"] or 0.0),
            "updated_at": float(r["updated_at"] or 0.0),
        })
    return out


def list_automation_rules(
    *,
    include_disabled: bool = False,
    owner_user_id: str | None = None,
    db_path: pathlib.Path | None = None,
) -> list[dict[str, Any]]:
    if not include_disabled:
        _, rules, _ = get_automation_snapshot_bundle(db_path=db_path)
        if owner_user_id is not None and str(owner_user_id).strip():
            uid = str(owner_user_id).strip()
            return [r for r in rules if str(r.get("owner_user_id") or "") == uid]
        return rules
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target, readonly=True)
        try:
            rules = _list_automation_rules_in_conn(conn, include_disabled=include_disabled)
            if owner_user_id is not None and str(owner_user_id).strip():
                uid = str(owner_user_id).strip()
                return [r for r in rules if str(r.get("owner_user_id") or "") == uid]
            return rules
        finally:
            conn.close()


def validate_automation_rule_input(
    *,
    when_device_id: str,
    when_state: str,
    then_device_id: str,
    then_action: str,
    else_device_id: str = "",
    else_action: str = "",
    db_path: pathlib.Path | None = None,
) -> tuple[str, str, str, str, str, str]:
    """Validate linked rule endpoints, actions, and acyclicity before staging or saving."""
    if when_device_id not in DEFAULT_DEVICES or then_device_id not in DEFAULT_DEVICES:
        raise ValueError("Thiết bị điều kiện hoặc thiết bị đích không tồn tại.")
    if when_device_id == then_device_id:
        raise ValueError("Không thể liên kết thiết bị với chính nó (tránh vòng lặp).")
    norm_when_state = ACTION_TO_STATE.get(str(when_state).lower(), str(when_state).upper())
    if norm_when_state not in ("ON", "OFF", "OPEN", "CLOSED"):
        raise ValueError(f"Trạng thái điều kiện '{when_state}' không hợp lệ.")
    if then_action not in ACTION_TO_STATE:
        raise ValueError(f"Hành động đích '{then_action}' không hợp lệ.")
    valid_else_dev = else_device_id if else_device_id in DEFAULT_DEVICES else ""
    valid_else_act = else_action if (valid_else_dev and else_action in ACTION_TO_STATE) else ""
    if not valid_else_act:
        valid_else_dev = ""

    existing = list_automation_rules(include_disabled=False, db_path=db_path)
    edges = [
        (r["when_device_id"], r["then_device_id"])
        for r in existing
        if not (
            r["when_device_id"] == when_device_id
            and r["when_state"] == norm_when_state
            and r["then_device_id"] == then_device_id
        )
    ]
    edges.append((when_device_id, then_device_id))
    if valid_else_dev:
        edges.append((when_device_id, valid_else_dev))
    if _rules_have_cycle(edges):
        raise ValueError("Từ chối tạo luật liên kết vì gây vòng lặp giữa các thiết bị.")
    return when_device_id, norm_when_state, then_device_id, then_action, valid_else_dev, valid_else_act


def create_automation_rule(
    *,
    owner_user_id: str,
    owner_tier: int,
    when_device_id: str,
    when_state: str,
    then_device_id: str,
    then_action: str,
    else_device_id: str = "",
    else_action: str = "",
    delay_seconds: float = 0.0,
    label: str = "",
    owner_name: str = "",
    rule_id: str | None = None,
    db_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    (
        when_device_id,
        norm_when_state,
        then_device_id,
        then_action,
        valid_else_dev_str,
        valid_else_act,
    ) = validate_automation_rule_input(
        when_device_id=when_device_id,
        when_state=when_state,
        then_device_id=then_device_id,
        then_action=then_action,
        else_device_id=else_device_id,
        else_action=else_action,
        db_path=db_path,
    )
    valid_else_dev: str | None = valid_else_dev_str or None

    rid = rule_id or f"rule_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    now_ts = time.time()
    when_name = DEVICE_LABELS_VI.get(when_device_id, when_device_id).lower()
    when_verb = "mở" if norm_when_state in ("OPEN", "ON") else ("đóng" if norm_when_state == "CLOSED" else "tắt")
    clean_label = str(
        label or f"Khi {when_verb} {when_name} thì {format_device_action_vi(then_device_id, then_action)}"
    ).strip()

    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> None:
                uid = _ensure_fk_parents(
                    c, owner_user_id=owner_user_id, owner_tier=owner_tier, owner_name=owner_name
                )
                c.execute(
                    """
                    DELETE FROM automation_rules
                    WHERE when_device_id = ? AND when_state = ? AND then_device_id = ?
                    """,
                    (when_device_id, norm_when_state, then_device_id),
                )
                c.execute(
                    """
                    INSERT INTO automation_rules (
                        rule_id, owner_user_id, owner_tier, when_device_id, when_state,
                        then_device_id, then_action, else_device_id, else_action,
                        delay_seconds, enabled, label, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                    """,
                    (
                        rid,
                        uid,
                        int(owner_tier if owner_tier in (1, 2, 3) else 1),
                        when_device_id,
                        norm_when_state,
                        then_device_id,
                        then_action,
                        valid_else_dev,
                        valid_else_act,
                        max(0.0, float(delay_seconds or 0.0)),
                        clean_label,
                        now_ts,
                        now_ts,
                    ),
                )

            run_write_transaction(conn, _tx)
        finally:
            conn.close()
    invalidate_automation_cache(db_path)

    return {
        "id": rid,
        "rule_id": rid,
        "owner_user_id": owner_user_id,
        "owner_tier": int(owner_tier if owner_tier in (1, 2, 3) else 1),
        "when_device_id": when_device_id,
        "when_device_name": DEVICE_LABELS_VI.get(when_device_id, when_device_id),
        "when_state": norm_when_state,
        "then_device_id": then_device_id,
        "then_device_name": DEVICE_LABELS_VI.get(then_device_id, then_device_id),
        "then_action": then_action,
        "else_device_id": valid_else_dev or "",
        "else_action": valid_else_act,
        "delay_seconds": max(0.0, float(delay_seconds or 0.0)),
        "enabled": True,
        "label": clean_label,
    }


def delete_automation_rule(rule_id: str, *, db_path: pathlib.Path | None = None) -> bool:
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> int:
                cur = c.execute("DELETE FROM automation_rules WHERE rule_id = ?", (str(rule_id),))
                return int(cur.rowcount or 0)

            deleted = run_write_transaction(conn, _tx) > 0
        finally:
            conn.close()
    if deleted:
        invalidate_automation_cache(db_path)
    return deleted


# =============================================================================
# CUSTOM COMMANDS / MULTI-STEP SCENES
# =============================================================================

def _normalize_steps(steps: list[dict[str, Any]]) -> list[dict[str, str]]:
    clean: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        did = str(step.get("device_id") or "").strip()
        act = str(step.get("action") or "").strip().lower()
        if act not in ACTION_TO_STATE:
            continue
        if did == "all_lights":
            expanded_act = "turn_on" if act in ("open", "turn_on") else "turn_off"
            pairs = [("living_room_light", expanded_act), ("bedroom_light", expanded_act)]
        elif did == "all_devices":
            if act in ("close", "turn_off"):
                pairs = [
                    ("living_room_light", "turn_off"),
                    ("bedroom_light", "turn_off"),
                    ("fan", "turn_off"),
                    ("ac", "turn_off"),
                    ("alarm_siren", "turn_off"),
                    ("garden_pump", "turn_off"),
                    ("main_door", "close"),
                ]
            else:
                pairs = [
                    ("living_room_light", "turn_on"),
                    ("bedroom_light", "turn_on"),
                    ("fan", "turn_on"),
                    ("ac", "open"),
                ]
        elif did in DEFAULT_DEVICES:
            fixed_act = (
                ("open" if act in ("open", "turn_on") else "close")
                if did == "main_door"
                else ("turn_on" if act in ("open", "turn_on") else "turn_off")
            )
            pairs = [(did, fixed_act)]
        else:
            continue
        for pd, pa in pairs:
            if (pd, pa) not in seen:
                seen.add((pd, pa))
                clean.append({"device_id": pd, "action": pa})
    return clean


def _list_custom_commands_in_conn(conn: sqlite3.Connection, *, include_disabled: bool = False) -> list[dict[str, Any]]:
    sql = """
        SELECT c.command_id, c.phrase, c.phrase_norm, c.owner_user_id,
               COALESCE(u.full_name, c.owner_user_id) AS owner_name,
               c.owner_tier, c.steps_json, c.enabled, c.created_at, c.updated_at
        FROM custom_commands c
        LEFT JOIN users u ON u.user_id = c.owner_user_id
    """
    if not include_disabled:
        sql += " WHERE c.enabled = 1 "
    sql += " ORDER BY c.updated_at DESC, c.created_at DESC"
    rows = conn.execute(sql).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            steps = json.loads(str(r["steps_json"] or "[]"))
        except Exception:
            steps = []
        if not isinstance(steps, list):
            steps = []
        summary = ", ".join(format_device_action_vi(s.get("device_id", ""), s.get("action", "")) for s in steps)
        out.append({
            "id": str(r["command_id"]),
            "command_id": str(r["command_id"]),
            "phrase": str(r["phrase"]),
            "phrase_norm": str(r["phrase_norm"]),
            "owner_user_id": str(r["owner_user_id"]),
            "owner_name": str(r["owner_name"]),
            "owner_tier": int(r["owner_tier"] or 1),
            "steps": steps,
            "steps_summary": summary,
            "enabled": bool(int(r["enabled"] or 0)),
            "created_at": float(r["created_at"] or 0.0),
            "updated_at": float(r["updated_at"] or 0.0),
        })
    return out


def list_custom_commands(
    *,
    include_disabled: bool = False,
    owner_user_id: str | None = None,
    db_path: pathlib.Path | None = None,
) -> list[dict[str, Any]]:
    if not include_disabled:
        _, _, cmds = get_automation_snapshot_bundle(db_path=db_path)
        if owner_user_id is not None and str(owner_user_id).strip():
            uid = str(owner_user_id).strip()
            return [c for c in cmds if str(c.get("owner_user_id") or "") == uid]
        return cmds
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target, readonly=True)
        try:
            cmds = _list_custom_commands_in_conn(conn, include_disabled=include_disabled)
            if owner_user_id is not None and str(owner_user_id).strip():
                uid = str(owner_user_id).strip()
                return [c for c in cmds if str(c.get("owner_user_id") or "") == uid]
            return cmds
        finally:
            conn.close()


def get_automation_snapshot_bundle(
    *, db_path: pathlib.Path | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Read schedules, active rules, and custom commands via short-lived RAM cache or single read-only SQLite connection."""
    now_mono = time.monotonic()
    raw_target = pathlib.Path(db_path) if db_path is not None else _active_db_path()
    fast_key = str(raw_target.resolve())
    cached = _AUTOMATION_SNAPSHOT_CACHE.get(fast_key)
    if cached is not None:
        ep, ts_mono, c_sched, c_rules, c_cmds = cached
        if ep == _AUTOMATION_CACHE_EPOCH and (now_mono - ts_mono) < _AUTOMATION_CACHE_TTL_SEC:
            return list(c_sched), list(c_rules), list(c_cmds)
    target = _resolve_db(db_path)
    key = str(target.resolve())
    ep_before = _AUTOMATION_CACHE_EPOCH
    conn = get_connection(target, readonly=True)
    try:
        scheds = _list_schedules_in_conn(conn, include_disabled=True)
        rules = _list_automation_rules_in_conn(conn, include_disabled=False)
        cmds = _list_custom_commands_in_conn(conn, include_disabled=False)
    finally:
        conn.close()
    with _DB_LOCK:
        if ep_before == _AUTOMATION_CACHE_EPOCH:
            _AUTOMATION_SNAPSHOT_CACHE[key] = (_AUTOMATION_CACHE_EPOCH, time.monotonic(), scheds, rules, cmds)
    return list(scheds), list(rules), list(cmds)


def upsert_custom_command(
    *,
    phrase: str,
    steps: list[dict[str, Any]],
    owner_user_id: str,
    owner_tier: int,
    enabled: bool = True,
    owner_name: str = "",
    command_id: str | None = None,
    db_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    clean_phrase = " ".join(str(phrase or "").strip().split())
    norm = normalize_phrase(clean_phrase)
    if not norm:
        raise ValueError("Tên lệnh tùy chỉnh không được để trống.")
    clean_steps = _normalize_steps(steps)
    if not clean_steps:
        raise ValueError("Lệnh tùy chỉnh phải có ít nhất 1 bước thiết bị hợp lệ.")

    cid = command_id or f"scene_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    now_ts = time.time()
    steps_json = json.dumps(clean_steps, ensure_ascii=False)

    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> str:
                uid = _ensure_fk_parents(
                    c, owner_user_id=owner_user_id, owner_tier=owner_tier, owner_name=owner_name
                )
                existing_by_id = c.execute(
                    "SELECT command_id FROM custom_commands WHERE command_id = ?", (cid,)
                ).fetchone()
                existing_by_norm = c.execute(
                    "SELECT command_id FROM custom_commands WHERE owner_user_id = ? AND phrase_norm = ?",
                    (uid, norm),
                ).fetchone()
                if existing_by_id is not None:
                    if existing_by_norm is not None and str(existing_by_norm["command_id"]) != cid:
                        c.execute("DELETE FROM custom_commands WHERE command_id = ?", (str(existing_by_norm["command_id"]),))
                    c.execute(
                        """
                        UPDATE custom_commands
                        SET phrase = ?, phrase_norm = ?, owner_user_id = ?, owner_tier = ?,
                            steps_json = ?, enabled = ?, updated_at = ?
                        WHERE command_id = ?
                        """,
                        (
                            clean_phrase,
                            norm,
                            uid,
                            int(owner_tier if owner_tier in (1, 2, 3) else 1),
                            steps_json,
                            1 if enabled else 0,
                            now_ts,
                            cid,
                        ),
                    )
                    return cid

                target_cid = str(existing_by_norm["command_id"]) if existing_by_norm is not None else cid
                if existing_by_norm is not None:
                    c.execute(
                        """
                        UPDATE custom_commands
                        SET phrase = ?, owner_user_id = ?, owner_tier = ?,
                            steps_json = ?, enabled = ?, updated_at = ?
                        WHERE command_id = ?
                        """,
                        (
                            clean_phrase,
                            uid,
                            int(owner_tier if owner_tier in (1, 2, 3) else 1),
                            steps_json,
                            1 if enabled else 0,
                            now_ts,
                            target_cid,
                        ),
                    )
                else:
                    c.execute(
                        """
                        INSERT INTO custom_commands (
                            command_id, phrase, phrase_norm, owner_user_id, owner_tier,
                            steps_json, enabled, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            target_cid,
                            clean_phrase,
                            norm,
                            uid,
                            int(owner_tier if owner_tier in (1, 2, 3) else 1),
                            steps_json,
                            1 if enabled else 0,
                            now_ts,
                            now_ts,
                        ),
                    )
                return target_cid

            final_cid = run_write_transaction(conn, _tx)
        finally:
            conn.close()
    invalidate_automation_cache(db_path)

    items = [c for c in list_custom_commands(include_disabled=True, owner_user_id=owner_user_id, db_path=db_path) if c["command_id"] == final_cid]
    if not items:
        items = [c for c in list_custom_commands(include_disabled=True, db_path=db_path) if c["command_id"] == final_cid]
    return items[0]


def delete_custom_command(command_id: str, *, db_path: pathlib.Path | None = None) -> bool:
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> int:
                cur = c.execute("DELETE FROM custom_commands WHERE command_id = ?", (str(command_id),))
                return int(cur.rowcount or 0)

            deleted = run_write_transaction(conn, _tx) > 0
        finally:
            conn.close()
    if deleted:
        invalidate_automation_cache(db_path)
    return deleted


def find_custom_command_by_text(
    text: str,
    *,
    owner_user_id: str | None = None,
    db_path: pathlib.Path | None = None,
) -> dict[str, Any] | None:
    norm_text = normalize_phrase(text)
    if not norm_text:
        return None
    commands = list_custom_commands(include_disabled=False, owner_user_id=owner_user_id, db_path=db_path)
    for cmd in commands:
        if cmd["phrase_norm"] == norm_text:
            return cmd
    stripped = norm_text
    for prefix in ("kich hoat ", "chay lenh ", "chay ", "bat ", "mo ", "thuc hien ", "dung "):
        if stripped.startswith(prefix):
            cand = stripped[len(prefix):].strip()
            for cmd in commands:
                if cmd["phrase_norm"] == cand:
                    return cmd
    # Fallback: longer phrase contained as whole words
    best: dict[str, Any] | None = None
    best_len = 0
    padded = f" {norm_text} "
    for cmd in commands:
        pn = cmd["phrase_norm"]
        if len(pn) >= 3 and f" {pn} " in padded and len(pn) > best_len:
            best = cmd
            best_len = len(pn)
    return best


def clear_all_rules_and_commands(*, db_path: pathlib.Path | None = None) -> None:
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> None:
                c.execute("DELETE FROM schedules")
                c.execute("DELETE FROM automation_rules")
                c.execute("DELETE FROM custom_commands")

            run_write_transaction(conn, _tx)
        finally:
            conn.close()
    invalidate_automation_cache(db_path)


def check_steps_rbac(steps: list[dict[str, Any]], actor_tier: int) -> tuple[bool, str]:
    for step in steps or []:
        did = str(step.get("device_id") or "")
        act = str(step.get("action") or "turn_on").lower()
        if not did:
            continue
        if did == "all_lights":
            expanded = ["living_room_light", "bedroom_light"]
        elif did == "all_devices":
            expanded = list(DEFAULT_DEVICES.keys()) if act in ("close", "turn_off") else [
                "living_room_light", "bedroom_light", "fan", "ac"
            ]
        else:
            expanded = [did]
        for target_dev in expanded:
            if not can_control_device(actor_tier, target_dev):
                dname = DEVICE_LABELS_VI.get(target_dev, target_dev)
                return False, f"Từ chối: Cấp {actor_tier} không có quyền điều khiển {dname} trong ngữ cảnh này."
    return True, ""


# =============================================================================
# HOUSEHOLD MEMBERS, PERMISSIONS, ±60s CONFLICT, SCOPED RESETS & 4-STEP CONFIRM
# =============================================================================

def list_household_members(
    *,
    include_inactive: bool = False,
    db_path: pathlib.Path | None = None,
) -> list[dict[str, Any]]:
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target, readonly=True)
        try:
            sql = """
                SELECT user_id, full_name, role, tier, role_code, email,
                       permission_active, permission_status, is_active,
                       COALESCE(can_create_links, 0) AS can_create_links, updated_at
                FROM users
                WHERE tier IN (1, 2, 3)
            """
            if not include_inactive:
                sql += " AND COALESCE(is_active, 1) = 1 AND COALESCE(permission_active, 1) = 1 "
            sql += " ORDER BY tier ASC, full_name ASC, user_id ASC"
            rows = conn.execute(sql).fetchall()
            out: list[dict[str, Any]] = []
            for r in rows:
                uid = str(r["user_id"] or "")
                if uid in ("anonymous", "expired_or_invalid", "ws_unauthenticated"):
                    continue
                t_val = int(r["tier"] or 3)
                full_name_s = str(r["full_name"] or uid)
                out.append({
                    "user_id": uid,
                    "full_name": full_name_s,
                    "display_name": full_name_s,
                    "role": str(r["role"] or role_for_tier(t_val)),
                    "role_code": str(r["role_code"] or role_for_tier(t_val)),
                    "tier": t_val,
                    "email": str(r["email"] or ""),
                    "permission_active": bool(int(r["permission_active"] or 0)),
                    "permission_status": str(r["permission_status"] or "ACTIVE"),
                    "is_active": bool(int(r["is_active"] or 0)),
                    "can_create_links": True if t_val <= 1 else (bool(int(r["can_create_links"] or 0)) if t_val == 2 else False),
                    "updated_at": str(r["updated_at"] or ""),
                })
            return out
        finally:
            conn.close()


def resolve_target_user_by_query(
    query: str,
    *,
    db_path: pathlib.Path | None = None,
) -> dict[str, Any] | None:
    norm_q = normalize_phrase(query)
    if not norm_q:
        return None
    members = list_household_members(include_inactive=True, db_path=db_path)
    for m in members:
        if norm_q in (
            normalize_phrase(m.get("full_name") or ""),
            normalize_phrase(m.get("user_id") or ""),
            normalize_phrase((m.get("email") or "").split("@")[0]),
        ):
            return m
    matches = []
    for m in members:
        hay = " ".join([
            normalize_phrase(m.get("full_name") or ""),
            normalize_phrase(m.get("user_id") or ""),
            normalize_phrase((m.get("email") or "").split("@")[0]),
        ])
        if norm_q in hay or hay in norm_q:
            matches.append(m)
    if len(matches) == 1:
        return matches[0]
    if matches:
        # Prefer token match on name words
        toks = set(norm_q.split())
        best = max(matches, key=lambda item: len(toks & set(normalize_phrase(item.get("full_name") or "").split())))
        return best
    return None


def can_user_create_links(
    user_id: str,
    tier: int,
    *,
    engine: Any = None,
    db_path: pathlib.Path | None = None,
) -> bool:
    t_val = int(tier or 3)
    if t_val <= 1:
        return True
    if t_val >= 3:
        return False
    uid = str(user_id or "").strip()
    if not uid:
        return False
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target, readonly=True)
        try:
            row = conn.execute(
                "SELECT COALESCE(can_create_links, 0) AS allowed FROM users WHERE user_id = ?",
                (uid,),
            ).fetchone()
            if row is not None:
                return bool(int(row["allowed"] or 0))
        finally:
            conn.close()
    return False


def set_user_can_create_links(
    user_id: str,
    allowed: bool,
    *,
    owner_tier: int = 2,
    display_name: str = "",
    db_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    now_iso = now_saigon_iso()
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> str:
                uid = _ensure_fk_parents(
                    c, owner_user_id=user_id, owner_tier=owner_tier, owner_name=display_name
                )
                c.execute(
                    "UPDATE users SET can_create_links = ?, updated_at = ? WHERE user_id = ?",
                    (1 if allowed else 0, now_iso, uid),
                )
                return uid

            uid = run_write_transaction(conn, _tx)
        finally:
            conn.close()
    return {"user_id": uid, "can_create_links": bool(allowed)}


def _tod_diff_sec(sec_a: float, sec_b: float) -> float:
    d = abs(float(sec_a) - float(sec_b)) % 86400.0
    return min(d, 86400.0 - d)


def _schedule_epoch_and_tod(
    *,
    time_hhmm: str,
    run_date_vn: str = "",
    now_vn: datetime.datetime | None = None,
) -> tuple[float, float]:
    hh, mm = [int(p) for p in str(time_hhmm).strip().split(":", 1)]
    tod = float(hh * 3600 + mm * 60)
    ref_now = now_vn or now_saigon()
    date_str = str(run_date_vn or "").strip()
    if date_str:
        try:
            dt_d = datetime.date.fromisoformat(date_str)
            dt = datetime.datetime(dt_d.year, dt_d.month, dt_d.day, hh, mm, 0, tzinfo=SAIGON_TZ)
            return dt.timestamp(), tod
        except Exception:
            pass
    target_dt = ref_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target_dt <= ref_now:
        target_dt = target_dt + datetime.timedelta(days=1)
    return target_dt.timestamp(), tod


def check_tier1_schedule_conflict(
    *,
    actor_tier: int,
    fire_epoch: float | None = None,
    time_hhmm: str | None = None,
    schedule_type: str = "once",
    run_date_vn: str = "",
    exclude_timer_id: str | None = None,
    exclude_schedule_id: str | None = None,
    engine: Any = None,
    db_path: pathlib.Path | None = None,
) -> str | None:
    """ADDENDUM D: Cấp 2 không được đặt hẹn giờ/lịch trùng khung giờ (±60s, mọi thiết bị) với Cấp 1."""
    if int(actor_tier or 3) <= 1:
        return None
    if engine is not None and (getattr(engine, "system_policies", {}) or {}).get("tier2_can_override_tier1", False):
        return None

    now_vn = now_saigon()
    now_ts = time.time()
    cand_epoch: float | None = None
    cand_tod: float | None = None
    cand_is_daily = str(schedule_type or "once").strip().lower() == "daily"

    if fire_epoch is not None:
        cand_epoch = float(fire_epoch)
        cand_dt = datetime.datetime.fromtimestamp(cand_epoch, tz=SAIGON_TZ)
        cand_tod = float(cand_dt.hour * 3600 + cand_dt.minute * 60 + cand_dt.second)
    elif time_hhmm:
        cand_epoch, cand_tod = _schedule_epoch_and_tod(
            time_hhmm=time_hhmm,
            run_date_vn=run_date_vn,
            now_vn=now_vn,
        )
    if cand_tod is None and cand_epoch is None:
        return None

    # 1. Check all pending Tier 1 timers (SQLite + active in-memory engine timers across ALL devices)
    t1_timers: dict[str, dict[str, Any]] = {}
    for row in list_pending_timers(db_path=db_path):
        tid = str(row.get("timer_id") or row.get("id") or "")
        if tid:
            t1_timers[tid] = row
    if engine is not None:
        for tid, info in (getattr(engine, "active_timers", {}) or {}).items():
            t1_timers.setdefault(str(tid), info)

    for tid, tinfo in t1_timers.items():
        if exclude_timer_id and tid == str(exclude_timer_id):
            continue
        if int(tinfo.get("owner_tier") or 1) != 1:
            continue
        t1_epoch = float(tinfo.get("fire_at") or 0.0)
        if t1_epoch <= now_ts - 2.0:
            continue
        t1_dt = datetime.datetime.fromtimestamp(t1_epoch, tz=SAIGON_TZ)
        t1_tod = float(t1_dt.hour * 3600 + t1_dt.minute * 60 + t1_dt.second)
        if cand_is_daily and cand_tod is not None:
            if _tod_diff_sec(cand_tod, t1_tod) <= 60.0:
                return TIER1_SCHEDULE_CONFLICT_MSG_VI
        elif cand_epoch is not None and abs(cand_epoch - t1_epoch) <= 60.0:
            return TIER1_SCHEDULE_CONFLICT_MSG_VI

    # 2. Check all enabled Tier 1 schedules (SQLite `schedules`, once & daily across ALL devices)
    for sc in list_schedules(include_disabled=False, db_path=db_path):
        sid = str(sc.get("schedule_id") or sc.get("id") or "")
        if exclude_schedule_id and sid == str(exclude_schedule_id):
            continue
        if int(sc.get("owner_tier") or 1) != 1 or not sc.get("enabled", True):
            continue
        sc_hhmm = str(sc.get("time_hhmm") or "").strip()
        if ":" not in sc_hhmm:
            continue
        sc_epoch, sc_tod = _schedule_epoch_and_tod(
            time_hhmm=sc_hhmm,
            run_date_vn=str(sc.get("run_date_vn") or ""),
            now_vn=now_vn,
        )
        sc_is_daily = str(sc.get("schedule_type") or "once").strip().lower() == "daily"
        if cand_is_daily or sc_is_daily:
            if cand_tod is not None and _tod_diff_sec(cand_tod, sc_tod) <= 60.0:
                return TIER1_SCHEDULE_CONFLICT_MSG_VI
        elif cand_epoch is not None and abs(cand_epoch - sc_epoch) <= 60.0:
            return TIER1_SCHEDULE_CONFLICT_MSG_VI

    return None


def reset_custom_commands_scoped(
    *,
    target_owner_id: str | None = None,
    clear_all: bool = False,
    engine: Any = None,
    db_path: pathlib.Path | None = None,
) -> int:
    uid = str(target_owner_id or "").strip()
    if not clear_all and not uid:
        return 0
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> int:
                if clear_all:
                    cur1 = c.execute("DELETE FROM custom_commands")
                    c.execute("DELETE FROM rules_pool WHERE rule_category IN ('custom', 'alias', 'word_mapping', 'scene')")
                    return int(cur1.rowcount or 0)
                cur1 = c.execute("DELETE FROM custom_commands WHERE owner_user_id = ?", (uid,))
                c.execute(
                    "DELETE FROM rules_pool WHERE owner_user_id = ? AND rule_category IN ('custom', 'alias', 'word_mapping', 'scene')",
                    (uid,),
                )
                return int(cur1.rowcount or 0)

            removed = run_write_transaction(conn, _tx)
        finally:
            conn.close()

    invalidate_automation_cache(db_path)
    if engine is not None:
        try:
            ov = getattr(engine, "overlay_rules", None)
            if isinstance(ov, dict):
                if clear_all:
                    ov["user_pools"] = {}
                    ov["aliases"] = {}
                    ov["word_mappings"] = {}
                else:
                    up = ov.setdefault("user_pools", {}).setdefault(uid, {})
                    up["aliases"] = {}
                    up["word_mappings"] = {}
                if hasattr(engine, "_save_overlay"):
                    engine._save_overlay()
        except Exception:
            pass
    return removed


def reset_links_scoped(
    *,
    target_owner_id: str | None = None,
    clear_all: bool = False,
    engine: Any = None,
    db_path: pathlib.Path | None = None,
) -> int:
    uid = str(target_owner_id or "").strip()
    if not clear_all and not uid:
        return 0
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> int:
                if clear_all:
                    cur1 = c.execute("DELETE FROM automation_rules")
                    c.execute("DELETE FROM rules_pool WHERE rule_category IN ('if_else', 'link')")
                    return int(cur1.rowcount or 0)
                cur1 = c.execute("DELETE FROM automation_rules WHERE owner_user_id = ?", (uid,))
                c.execute(
                    "DELETE FROM rules_pool WHERE owner_user_id = ? AND rule_category IN ('if_else', 'link')",
                    (uid,),
                )
                return int(cur1.rowcount or 0)

            removed = run_write_transaction(conn, _tx)
        finally:
            conn.close()

    invalidate_automation_cache(db_path)
    if engine is not None:
        try:
            ov = getattr(engine, "overlay_rules", None)
            if isinstance(ov, dict):
                if clear_all:
                    ov["if_else_rules"] = []
                    for u_data in (ov.get("user_pools") or {}).values():
                        if isinstance(u_data, dict):
                            u_data["if_else_rules"] = []
                else:
                    up = ov.setdefault("user_pools", {}).setdefault(uid, {})
                    up["if_else_rules"] = []
                if hasattr(engine, "_save_overlay"):
                    engine._save_overlay()
        except Exception:
            pass
    return removed


def reset_timers_and_schedules_scoped(
    *,
    target_owner_id: str | None = None,
    clear_all: bool = False,
    engine: Any = None,
    db_path: pathlib.Path | None = None,
) -> int:
    uid = str(target_owner_id or "").strip()
    if not clear_all and not uid:
        return 0
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> int:
                if clear_all:
                    c1 = c.execute("DELETE FROM timers_pool")
                    c2 = c.execute("DELETE FROM schedules")
                    return int(c1.rowcount or 0) + int(c2.rowcount or 0)
                c1 = c.execute("DELETE FROM timers_pool WHERE owner_user_id = ?", (uid,))
                c2 = c.execute("DELETE FROM schedules WHERE owner_user_id = ?", (uid,))
                return int(c1.rowcount or 0) + int(c2.rowcount or 0)

            removed = run_write_transaction(conn, _tx)
        finally:
            conn.close()

    invalidate_automation_cache(db_path)
    if engine is not None:
        try:
            tasks = getattr(engine, "_timer_tasks", {}) or {}
            active = getattr(engine, "active_timers", {}) or {}
            target_tids = [
                tid for tid, info in list(active.items())
                if clear_all or str(info.get("owner_id") or info.get("owner_user_id") or "") == uid
            ]
            for tid in target_tids:
                t = tasks.pop(tid, None)
                if t is not None and not t.done():
                    t.cancel()
                active.pop(tid, None)
                removed = max(removed, 1)
        except Exception:
            pass
    return removed


def create_pending_confirmation(
    *,
    owner_user_id: str,
    owner_tier: int,
    session_key: str,
    action_kind: str,
    payload: dict[str, Any],
    prompt_question: str,
    owner_name: str = "",
    ttl_sec: float = PENDING_CONFIRM_TTL_SEC,
    db_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    now_ts = time.time()
    exp_ts = now_ts + max(1.0, float(ttl_sec or PENDING_CONFIRM_TTL_SEC))
    pid = f"pconf_{int(now_ts * 1000)}_{uuid.uuid4().hex[:6]}"
    skey = str(session_key or owner_user_id).strip() or str(owner_user_id)
    payload_str = json.dumps(payload or {}, ensure_ascii=False)

    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> str:
                uid = _ensure_fk_parents(
                    c, owner_user_id=owner_user_id, owner_tier=owner_tier, owner_name=owner_name
                )
                c.execute(
                    """
                    UPDATE pending_confirmations
                    SET status = 'expired'
                    WHERE status = 'pending' AND expires_at <= ?
                    """,
                    (now_ts,),
                )
                c.execute(
                    """
                    UPDATE pending_confirmations
                    SET status = 'superseded'
                    WHERE owner_user_id = ? AND session_key = ? AND status = 'pending'
                    """,
                    (uid, skey),
                )
                c.execute(
                    """
                    INSERT INTO pending_confirmations (
                        pending_id, session_key, owner_user_id, owner_tier,
                        action_kind, payload_json, prompt_question,
                        created_at, expires_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (
                        pid,
                        skey,
                        uid,
                        int(owner_tier if owner_tier in (1, 2, 3) else 1),
                        str(action_kind),
                        payload_str,
                        str(prompt_question or ""),
                        now_ts,
                        exp_ts,
                    ),
                )
                return uid

            resolved_uid = run_write_transaction(conn, _tx)
        finally:
            conn.close()

    return {
        "pending_id": pid,
        "session_key": skey,
        "owner_user_id": resolved_uid,
        "owner_tier": int(owner_tier if owner_tier in (1, 2, 3) else 1),
        "action_kind": str(action_kind),
        "payload": payload or {},
        "prompt_question": str(prompt_question or ""),
        "created_at": now_ts,
        "expires_at": exp_ts,
        "status": "pending",
    }


def _row_to_pending_dict(r: sqlite3.Row) -> dict[str, Any]:
    try:
        payload_obj = json.loads(str(r["payload_json"] or "{}"))
    except Exception:
        payload_obj = {}
    return {
        "pending_id": str(r["pending_id"]),
        "session_key": str(r["session_key"]),
        "owner_user_id": str(r["owner_user_id"]),
        "owner_tier": int(r["owner_tier"] or 1),
        "action_kind": str(r["action_kind"]),
        "payload": payload_obj if isinstance(payload_obj, dict) else {},
        "prompt_question": str(r["prompt_question"] or ""),
        "created_at": float(r["created_at"] or 0.0),
        "expires_at": float(r["expires_at"] or 0.0),
        "status": str(r["status"] or "pending"),
    }


def get_pending_confirmation(
    *,
    owner_user_id: str,
    session_key: str = "",
    db_path: pathlib.Path | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    """Return (active_pending_or_None, was_expired_recently_for_user)."""
    uid = str(owner_user_id or "").strip()
    if not uid:
        return None, False
    skey = str(session_key or "").strip()
    now_ts = time.time()

    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> tuple[dict[str, Any] | None, bool]:
                cur_exp = c.execute(
                    """
                    UPDATE pending_confirmations
                    SET status = 'expired'
                    WHERE owner_user_id = ? AND status = 'pending' AND expires_at <= ?
                    """,
                    (uid, now_ts),
                )
                was_exp = int(cur_exp.rowcount or 0) > 0
                row = None
                if skey:
                    row = c.execute(
                        """
                        SELECT * FROM pending_confirmations
                        WHERE owner_user_id = ? AND session_key = ? AND status = 'pending' AND expires_at > ?
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (uid, skey, now_ts),
                    ).fetchone()
                if row is None:
                    row = c.execute(
                        """
                        SELECT * FROM pending_confirmations
                        WHERE owner_user_id = ? AND status = 'pending' AND expires_at > ?
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (uid, now_ts),
                    ).fetchone()
                if row is not None:
                    return _row_to_pending_dict(row), False
                return None, was_exp

            return run_write_transaction(conn, _tx)
        finally:
            conn.close()


def inspect_and_consume_pending_confirmation(
    pending_id: str,
    *,
    owner_user_id: str,
    new_status: str = "confirmed",
    expected_action_kind: str | None = None,
    expected_payload_match: dict[str, Any] | None = None,
    db_path: pathlib.Path | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Atomically inspect and consume/cancel a pending confirmation bound to owner_user_id."""
    pid = str(pending_id or "").strip()
    uid = str(owner_user_id or "").strip()
    if not pid or not uid:
        return "not_found", None
    status_val = "cancelled" if str(new_status).lower() == "cancelled" else "confirmed"
    now_ts = time.time()

    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            def _tx(c: sqlite3.Connection) -> tuple[str, dict[str, Any] | None]:
                c.execute(
                    "UPDATE pending_confirmations SET status = 'expired' WHERE status = 'pending' AND expires_at <= ?",
                    (now_ts,),
                )
                row = c.execute(
                    "SELECT * FROM pending_confirmations WHERE pending_id = ?",
                    (pid,),
                ).fetchone()
                if row is None:
                    return "not_found", None
                row_dict = _row_to_pending_dict(row)
                if str(row["owner_user_id"]) != uid:
                    return "wrong_owner", row_dict
                if str(row["status"]) == "expired" or float(row["expires_at"] or 0.0) <= now_ts:
                    if str(row["status"]) == "pending":
                        c.execute(
                            "UPDATE pending_confirmations SET status = 'expired' WHERE pending_id = ?",
                            (pid,),
                        )
                    row_dict["status"] = "expired"
                    return "expired", row_dict
                if str(row["status"]) != "pending":
                    return "already_used", row_dict
                if expected_action_kind is not None and str(row["action_kind"]) != str(expected_action_kind):
                    return "wrong_action", row_dict
                if expected_payload_match:
                    row_payload = row_dict.get("payload") or {}
                    for k, expected_v in expected_payload_match.items():
                        if str(row_payload.get(k) or "") != str(expected_v or ""):
                            return "wrong_action", row_dict
                cur = c.execute(
                    """
                    UPDATE pending_confirmations
                    SET status = ?
                    WHERE pending_id = ? AND owner_user_id = ? AND status = 'pending' AND expires_at > ?
                    """,
                    (status_val, pid, uid, now_ts),
                )
                if int(cur.rowcount or 0) != 1:
                    return "already_used", row_dict
                row_dict["status"] = status_val
                return "ok", row_dict

            return run_write_transaction(conn, _tx)
        finally:
            conn.close()


def consume_or_cancel_pending_confirmation(
    pending_id: str,
    *,
    owner_user_id: str,
    new_status: str = "confirmed",
    expected_action_kind: str | None = None,
    expected_payload_match: dict[str, Any] | None = None,
    db_path: pathlib.Path | None = None,
) -> dict[str, Any] | None:
    reason, row_dict = inspect_and_consume_pending_confirmation(
        pending_id,
        owner_user_id=owner_user_id,
        new_status=new_status,
        expected_action_kind=expected_action_kind,
        expected_payload_match=expected_payload_match,
        db_path=db_path,
    )
    return row_dict if reason == "ok" else None
