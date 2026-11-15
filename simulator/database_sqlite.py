"""Hệ Quản Trị Cơ Sở Dữ Liệu Quan Hệ SQLite 3 (ACID + WAL Mode + Foreign Keys)
Dành cho Đồ Án Tốt Nghiệp: Smart Home Voice AI & NodeMCU ESP8266.

Kiến trúc Lưu trữ Lai 2 Tầng (Hybrid Storage Architecture):
1. Trên Server (`simulator/data/smarthome.db`):
   - Cơ sở dữ liệu quan hệ SQLite 3 chuẩn 3NF với 8 bảng SQL chính thức:
     (1) `users`           : Người dùng & Phân quyền 3 tầng (Tầng 1 Chủ nhà, Tầng 2 Gia đình, Tầng 3 Khách)
     (2) `voiceprints`     : Hồ sơ Sinh trắc Giọng nói Kép (Vector 26 chiều Nhanh & 64 chiều Formants Sâu)
     (3) `devices`         : Thiết bị Phần cứng, Trạng thái & Sơ đồ chân GPIO NodeMCU ESP8266
     (4) `timers_pool`     : Bể 1 — Lịch Hẹn Giờ Đa Tầng (Đếm ngược & Giờ Việt Nam AM/PM)
     (5) `rules_pool`      : Bể 2 — Luật Tự Động IF-THEN-ELSE, Đổi Từ & Khẩu Lệnh Tùy Chỉnh
     (6) `ir_remote_codes` : Kho Mã Hồng Ngoại 38kHz (Thu từ VS1838B D5 -> Phát qua LED IR D2)
     (7) `knowledge_rag`   : Kho Tri Thức Gia Đình & Vector Embeddings RAG
     (8) `audit_logs`      : Nhật Ký Sự Kiện, Câu Lệnh Giọng Nói & Truy Vết An Ninh
2. Dưới Mạch Vi Điều Khiển (`simulator/data/esp8266_flash_replica.json` -> LittleFS `/rules_replica.json`):
   - Tự động trích xuất (serialize) bản rút gọn siêu nhẹ (~1.4 KB) truyền qua MQTT Retain xuống bộ nhớ
     4MB Flash LittleFS của chip ESP8266 (vốn chỉ có 50KB RAM nên không chạy được SQL Engine).
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
import sqlite3
import threading
import time
from typing import Any

from simulator.db_migrations import (
    NORMALIZED_TABLE_ORDER,
    SENSITIVE_SQLITE_TABLES,
    apply_schema_migrations,
    bootstrap_device_state_from_devices,
    open_wal_connection,
    resolve_sqlite_db_path,
    role_for_tier,
    run_write_transaction,
)
from simulator.engine.constants_and_time import resolve_data_dir
from simulator.voice_config import (
    is_throwaway_qa_identity,
    redact_otp_and_secrets_in_text,
    sanitize_overview_and_logs_payload,
)

DATA_DIR = resolve_data_dir()

SQLITE_DB_PATH = resolve_sqlite_db_path()
_DB_LOCK = threading.RLock()
_INITIALIZED_DB_PATHS: set[str] = set()

DDL_SCHEMA_SQL = ""


def _active_db_path(data_dir: pathlib.Path | None = None) -> pathlib.Path:
    if data_dir is not None:
        return pathlib.Path(data_dir) / "smarthome.db"
    env_dir = __import__("os").environ.get("SMARTHOME_DATA_DIR", "").strip()
    env_file = __import__("os").environ.get("SMARTHOME_SQLITE_PATH", "").strip()
    if env_dir or env_file:
        return resolve_sqlite_db_path()
    return SQLITE_DB_PATH


def _now_iso() -> str:
    tz = datetime.timezone(datetime.timedelta(hours=7))
    return datetime.datetime.now(tz).isoformat()


_AUDIT_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002600-\U000027BF"
    "\U00002300-\U000023FF"
    "\U00002B00-\U00002BFF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "\U000020E3"
    "\U000025AA-\U000025FE"
    "]+",
    flags=re.UNICODE,
)


def strip_emojis_for_audit(text: str) -> str:
    """Loại bỏ toàn bộ emoji/ký hiệu pictograph khỏi log để đảm bảo /logs 0 emoji."""
    cleaned = _AUDIT_EMOJI_RE.sub("", str(text or ""))
    return re.sub(r" {2,}", " ", cleaned).strip()


def _strip_emojis_in_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return strip_emojis_for_audit(obj)
    if isinstance(obj, list):
        return [_strip_emojis_in_obj(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _strip_emojis_in_obj(v) for k, v in obj.items()}
    return obj


def get_connection(
    db_path: pathlib.Path | None = None,
    *,
    readonly: bool = False,
) -> sqlite3.Connection:
    target = pathlib.Path(db_path) if db_path is not None else _active_db_path()
    if readonly and not target.exists():
        return open_wal_connection(target, readonly=False)
    return open_wal_connection(target, readonly=bool(readonly))


_SCHEMA_INITIALIZED = False
_WAL_ANCHOR_CONN: sqlite3.Connection | None = None
_LAST_KB_MTIME: float = -1.0
_LAST_VP_MTIME: float = -1.0
_LAST_IR_MTIME: float = -1.0


def _redact_sqlite_audit_logs_in_conn(conn: sqlite3.Connection) -> int:
    """Làm sạch toàn bộ mã OTP / mật khẩu / voiceprint trong bảng audit_logs của SQLite."""
    changed = 0
    try:
        rows = conn.execute("SELECT log_id, summary, details_json FROM audit_logs").fetchall()
        for r in rows:
            lid = r["log_id"]
            orig_sum = str(r["summary"] or "")
            orig_det = str(r["details_json"] or "{}")
            new_sum = strip_emojis_for_audit(redact_otp_and_secrets_in_text(orig_sum))
            try:
                parsed_det = json.loads(orig_det)
                sanitized_det = _strip_emojis_in_obj(sanitize_overview_and_logs_payload(parsed_det))
                new_det = json.dumps(sanitized_det, ensure_ascii=False)
            except Exception:
                new_det = strip_emojis_for_audit(redact_otp_and_secrets_in_text(orig_det))
            if new_sum != orig_sum or new_det != orig_det:
                conn.execute(
                    "UPDATE audit_logs SET summary = ?, details_json = ? WHERE log_id = ?",
                    (new_sum, new_det, lid),
                )
                changed += 1
    except Exception:
        pass
    return changed


def init_sqlite_database(db_path: pathlib.Path | None = None) -> pathlib.Path:
    """Khởi tạo cấu trúc các bảng SQLite chuẩn 3NF + WAL + Foreign Keys + Indexes."""
    global _SCHEMA_INITIALIZED, _WAL_ANCHOR_CONN
    target = pathlib.Path(db_path) if db_path is not None else _active_db_path()
    with _DB_LOCK:
        key = str(target.resolve())
        if (
            target.exists()
            and key in _INITIALIZED_DB_PATHS
            and (_SCHEMA_INITIALIZED or target != SQLITE_DB_PATH)
        ):
            return target
        conn = get_connection(target)
        try:
            apply_schema_migrations(conn)
            _redact_sqlite_audit_logs_in_conn(conn)
            conn.commit()
        finally:
            conn.close()
        _INITIALIZED_DB_PATHS.add(key)
        if target == SQLITE_DB_PATH:
            _WAL_ANCHOR_CONN = None
            _SCHEMA_INITIALIZED = True
        return target


def insert_audit_log_sqlite(
    entry: dict[str, Any],
    user_id: str | None = None,
    db_path: pathlib.Path | None = None,
) -> int | None:
    """Ghi trực tiếp 1 bản ghi nhật ký vào bảng `audit_logs` trong SQLite (ACID BEGIN IMMEDIATE -> COMMIT)."""
    with _DB_LOCK:
        target = init_sqlite_database(db_path)
        conn = get_connection(target)
        try:
            def _write(c: sqlite3.Connection) -> int | None:
                uid = user_id or entry.get("user_id")
                if uid:
                    row = c.execute("SELECT user_id FROM users WHERE user_id = ?", (str(uid),)).fetchone()
                    if not row:
                        uid = None
                safe_summary = strip_emojis_for_audit(redact_otp_and_secrets_in_text(str(entry.get("summary") or "")))
                safe_details = _strip_emojis_in_obj(sanitize_overview_and_logs_payload(entry.get("details") or {}))
                cur = c.execute(
                    """
                    INSERT INTO audit_logs (
                        ts_iso, time_vn, category, event_type, user_id, user_name, tier, summary, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(entry.get("ts_iso") or _now_iso()),
                        str(entry.get("time_vn") or ""),
                        strip_emojis_for_audit(str(entry.get("category") or "SYSTEM")),
                        strip_emojis_for_audit(str(entry.get("event_type") or "event")),
                        str(uid) if uid else None,
                        strip_emojis_for_audit(str(entry.get("user") or entry.get("user_name") or "Hệ thống")),
                        int(entry.get("tier") or 1),
                        safe_summary,
                        json.dumps(safe_details if isinstance(safe_details, dict) else {}, ensure_ascii=False),
                    ),
                )
                return int(cur.lastrowid) if cur.lastrowid else None

            return run_write_transaction(conn, _write)
        except Exception:
            return None
        finally:
            conn.close()


def read_audit_logs_sqlite(
    limit: int = 250,
    db_path: pathlib.Path | None = None,
) -> list[dict[str, Any]]:
    """Đọc trực tiếp danh sách nhật ký mới nhất từ bảng `audit_logs` trong SQLite WAL."""
    with _DB_LOCK:
        target = init_sqlite_database(db_path)
        conn = open_wal_connection(target, readonly=True)
        try:
            rows = conn.execute(
                """
                SELECT log_id, ts_iso, time_vn, category, event_type, user_id, user_name, tier, summary, details_json
                FROM audit_logs
                ORDER BY log_id DESC
                LIMIT ?
                """,
                (max(1, min(int(limit or 250), 2000)),),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for r in rows:
                try:
                    details_obj = json.loads(str(r["details_json"] or "{}"))
                except Exception:
                    details_obj = {}
                out.append(
                    _strip_emojis_in_obj(
                        sanitize_overview_and_logs_payload(
                            {
                                "log_id": int(r["log_id"]),
                                "ts_iso": str(r["ts_iso"] or ""),
                                "time_vn": str(r["time_vn"] or ""),
                                "category": str(r["category"] or "SYSTEM"),
                                "event_type": str(r["event_type"] or "event"),
                                "user_id": r["user_id"],
                                "user": str(r["user_name"] or "Hệ thống"),
                                "user_name": str(r["user_name"] or "Hệ thống"),
                                "tier": int(r["tier"] or 1),
                                "summary": str(r["summary"] or ""),
                                "details": details_obj if isinstance(details_obj, dict) else {},
                            }
                        )
                    )
                )
            return out
        except Exception:
            return []
        finally:
            conn.close()


def clear_audit_logs_sqlite() -> None:
    """Xóa sạch bảng audit_logs trong SQLite và chèn lại 1 bản ghi logs_cleared."""
    with _DB_LOCK:
        init_sqlite_database()
        conn = get_connection()
        tz = datetime.timezone(datetime.timedelta(hours=7))
        now_dt = datetime.datetime.now(tz)
        now_str = now_dt.isoformat()
        time_vn_str = now_dt.strftime("%H:%M:%S %d/%m/%Y")
        try:
            def _clear_tx(c: sqlite3.Connection) -> None:
                c.execute("DELETE FROM audit_logs")
                c.execute(
                    """
                    INSERT INTO audit_logs (
                        ts_iso, time_vn, category, event_type, user_id, user_name, tier, summary, details_json
                    ) VALUES (?, ?, 'SYSTEM_EVENT', 'logs_cleared', NULL, 'Chủ nhà', 1, 'Đã dọn sạch toàn bộ nhật ký hệ thống', ?)
                    """,
                    (
                        now_str,
                        time_vn_str,
                        json.dumps({"action": "clear_audit_logs_sqlite"}, ensure_ascii=False),
                    ),
                )

            run_write_transaction(conn, _clear_tx)
        except Exception:
            pass
        finally:
            conn.close()


def sync_engine_state_to_sqlite(engine: Any) -> dict[str, int]:
    """Đồng bộ toàn bộ trạng thái từ SmartHomeEngine + Voiceprints + Knowledge RAG + IR DB vào 8 bảng SQLite."""
    with _DB_LOCK:
        init_sqlite_database()
        now_str = _now_iso()
        conn = get_connection()
        counts: dict[str, int] = {}
        try:
            def _sync_tx(c: sqlite3.Connection) -> None:
                # 1. Bảng `users` (không bao giờ xóa tài khoản thật có email/password đã đăng ký)
                users_dict = getattr(engine, "users", {}) or {}
                existing_rows = c.execute("SELECT user_id, email FROM users").fetchall()
                for er in existing_rows:
                    euid = str(er["user_id"] or "")
                    eemail = str(er["email"] or "")
                    if is_throwaway_qa_identity(euid) or is_throwaway_qa_identity(eemail):
                        c.execute("DELETE FROM users WHERE user_id = ?", (euid,))
                for uid, uinfo in users_dict.items():
                    tier_val = int(uinfo.get("tier", 3))
                    if tier_val not in (1, 2, 3) or is_throwaway_qa_identity(uid):
                        continue
                    c.execute(
                        """
                        INSERT INTO users (
                            user_id, full_name, role, tier, offline_allowed, created_by, updated_at, role_code
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET
                            full_name = excluded.full_name,
                            role = excluded.role,
                            tier = excluded.tier,
                            offline_allowed = excluded.offline_allowed,
                            role_code = excluded.role_code,
                            updated_at = excluded.updated_at
                        """,
                        (
                            str(uid),
                            str(uinfo.get("name") or uid),
                            str(uinfo.get("role") or "GUEST"),
                            tier_val,
                            1 if tier_val in (1, 2) else 0,
                            str(uinfo.get("created_by") or "SYSTEM"),
                            now_str,
                            role_for_tier(tier_val),
                        ),
                    )

                # 2. Bảng `devices` + `device_state`
                PIN_MAP = {
                    "main_door": "D1",
                    "living_room_light": "D2",
                    "ac": "D2",
                    "garden_pump": "D3",
                    "fan": "D6",
                    "bedroom_light": "D7",
                    "alarm_siren": "D8",
                }
                devs_dict = getattr(engine, "devices", {}) or {}
                dev_min_tiers = getattr(engine, "device_min_tiers", {}) or {}
                bootstrap_device_state_from_devices(c, devs_dict)
                for did, dinfo in devs_dict.items():
                    offline_ok = 0 if did in ("main_door", "alarm_siren") else 1
                    min_t = int(dev_min_tiers.get(did, 3))
                    c.execute(
                        """
                        INSERT INTO devices (
                            device_id, device_name, gpio_pin, state, min_tier_required,
                            offline_controllable, updated_at, min_role, room, device_type
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(device_id) DO UPDATE SET
                            device_name = excluded.device_name,
                            gpio_pin = excluded.gpio_pin,
                            state = excluded.state,
                            min_tier_required = excluded.min_tier_required,
                            offline_controllable = excluded.offline_controllable,
                            min_role = excluded.min_role,
                            updated_at = excluded.updated_at
                        """,
                        (
                            str(did),
                            str(dinfo.get("name") or did),
                            PIN_MAP.get(str(did), "GPIO"),
                            str(dinfo.get("state") or "OFF"),
                            min_t,
                            offline_ok,
                            now_str,
                            role_for_tier(min_t),
                            str(dinfo.get("room") or "home"),
                            str(dinfo.get("type") or "switch"),
                        ),
                    )

                # 3. Bảng `timers_pool` (Bể 1 - Hẹn giờ, upsert an toàn giữ nguyên fire_at_epoch & status)
                if getattr(engine, "_root_engine", engine) is engine:
                    db_user_ids = {str(r[0]) for r in c.execute("SELECT user_id FROM users").fetchall()}
                    db_dev_ids = {str(r[0]) for r in c.execute("SELECT device_id FROM devices").fetchall()}
                    active_timers = getattr(engine, "active_timers", {}) or {}
                    now_epoch = time.time()
                    for tid, tinfo in active_timers.items():
                        owner_id = str(tinfo.get("owner_id") or "tuan_anh")
                        if owner_id not in db_user_ids:
                            owner_id = "tuan_anh" if "tuan_anh" in db_user_ids else next(iter(db_user_ids), "tuan_anh")
                        dev_id = str(tinfo.get("device_id") or "living_room_light")
                        if dev_id not in db_dev_ids:
                            continue
                        raw_target = str(tinfo.get("raw_target") or dev_id)
                        smode = str(tinfo.get("mode") or "countdown")
                        if raw_target != dev_id and ":" not in smode:
                            smode = f"{smode}:{raw_target}"
                        fire_at_val = float(tinfo.get("fire_at") or (now_epoch + float(tinfo.get("delay_seconds") or 0.0)))
                        delay_val = float(tinfo.get("delay_seconds") or 0.0)
                        lbl_val = str(tinfo.get("label") or tinfo.get("reason") or tid)
                        c.execute(
                            """
                            INSERT INTO timers_pool (
                                timer_id, owner_user_id, device_id, action, schedule_mode,
                                target_time_vn, repeat_rule, label_summary, updated_at,
                                fire_at_epoch, delay_seconds, status, owner_tier, label, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
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
                                owner_tier = excluded.owner_tier,
                                label = excluded.label
                            """,
                            (
                                str(tid),
                                owner_id,
                                dev_id,
                                str(tinfo.get("action") or "turn_on"),
                                smode,
                                str(tinfo.get("target_vn_time") or tinfo.get("target_clock_str") or f"{int(delay_val)}s"),
                                str(tinfo.get("repeat") or "once"),
                                lbl_val,
                                now_str,
                                fire_at_val,
                                delay_val,
                                int(tinfo.get("owner_tier") or 1),
                                lbl_val,
                                float(tinfo.get("created_at") or now_epoch),
                            ),
                        )

                # 4. Bảng `rules_pool` (Bể 2 - Luật IF-ELSE, Khẩu lệnh & Từ vựng)
                c.execute("DELETE FROM rules_pool")
                overlay_rules = getattr(engine, "overlay_rules", {}) or {}
                user_pools = overlay_rules.get("user_pools", {}) or {}
                rule_idx = 1
                for uid, pool in user_pools.items():
                    if not isinstance(pool, dict):
                        continue
                    owner_id = str(uid) if str(uid) in users_dict else "tuan_anh"
                    for r in pool.get("if_else_rules", []) or []:
                        if not isinstance(r, dict):
                            continue
                        rid = str(r.get("id") or f"chain_{rule_idx}")
                        rule_idx += 1
                        w_dev = str(r.get("when_device_id") or r.get("trigger_device") or "")
                        w_st = str(r.get("when_state") or r.get("trigger_state") or "OPEN")
                        t_dev = str(r.get("then_device_id") or r.get("target_device") or "")
                        if t_dev not in devs_dict:
                            t_dev = None
                        c.execute(
                            """
                            INSERT OR REPLACE INTO rules_pool (
                                rule_id, owner_user_id, rule_category, trigger_expr,
                                target_device_id, target_action, bidirectional, else_action, updated_at
                            ) VALUES (?, ?, 'STATE_CHAIN', ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                f"{owner_id}_{rid}",
                                owner_id,
                                f"{w_dev} == {w_st}",
                                t_dev,
                                str(r.get("then_action") or r.get("target_action") or "turn_on"),
                                1 if r.get("bidirectional") else 0,
                                str(r.get("else_action") or ""),
                                now_str,
                            ),
                        )
                    for phrase, ainfo in (pool.get("aliases", {}) or {}).items():
                        rid = f"{owner_id}_alias_{rule_idx}"
                        rule_idx += 1
                        first_step = ainfo[0] if isinstance(ainfo, list) and ainfo else (ainfo if isinstance(ainfo, dict) else {})
                        t_dev = str(first_step.get("device_id") or "")
                        if t_dev not in devs_dict:
                            t_dev = None
                        c.execute(
                            """
                            INSERT OR REPLACE INTO rules_pool (
                                rule_id, owner_user_id, rule_category, trigger_expr,
                                target_device_id, target_action, bidirectional, else_action, updated_at
                            ) VALUES (?, ?, 'ALIAS_PHRASE', ?, ?, ?, 0, '', ?)
                            """,
                            (
                                rid,
                                owner_id,
                                str(phrase),
                                t_dev,
                                str(first_step.get("action") or "turn_on"),
                                now_str,
                            ),
                        )
                    for src_word, dst_word in (pool.get("word_mappings", {}) or {}).items():
                        rid = f"{owner_id}_vocab_{rule_idx}"
                        rule_idx += 1
                        c.execute(
                            """
                            INSERT OR REPLACE INTO rules_pool (
                                rule_id, owner_user_id, rule_category, trigger_expr,
                                target_device_id, target_action, bidirectional, else_action, updated_at
                            ) VALUES (?, ?, 'VOCAB_MAP', ?, NULL, ?, 0, '', ?)
                            """,
                            (rid, owner_id, str(src_word), str(dst_word), now_str),
                        )

                # 5. Bảng `voiceprints` (từ DATA_DIR/voiceprints.json)
                global _LAST_VP_MTIME, _LAST_IR_MTIME
                vp_file = _active_db_path().parent / "voiceprints.json"
                if not vp_file.exists():
                    vp_file = DATA_DIR / "voiceprints.json"
                if vp_file.exists():
                    try:
                        vp_mtime = vp_file.stat().st_mtime
                        cur_vp = c.execute("SELECT COUNT(*) FROM voiceprints").fetchone()[0]
                        if cur_vp == 0 or vp_mtime != _LAST_VP_MTIME:
                            c.execute("DELETE FROM voiceprints")
                            vp_data = json.loads(vp_file.read_text(encoding="utf-8"))
                            profiles = vp_data.get("profiles", vp_data) if isinstance(vp_data, dict) else {}
                            for vkey, vinfo in profiles.items():
                                if not isinstance(vinfo, dict) or not vinfo.get("authorized", True):
                                    continue
                                v_tier = int(vinfo.get("tier", 3))
                                if v_tier not in (1, 2, 3):
                                    continue
                                uid = str(vinfo.get("user_id") or vkey)
                                if uid == "chu_nha_1":
                                    uid = "tuan_anh"
                                if uid == "UNKNOWN":
                                    continue
                                if uid not in users_dict:
                                    v_role = role_for_tier(v_tier)
                                    c.execute(
                                        """
                                        INSERT OR IGNORE INTO users (
                                            user_id, full_name, role, tier, offline_allowed, created_by, updated_at, role_code
                                        ) VALUES (?, ?, ?, ?, ?, 'SYSTEM', ?, ?)
                                        """,
                                        (
                                            uid,
                                            str(vinfo.get("name") or uid),
                                            v_role,
                                            v_tier,
                                            1 if v_tier in (1, 2) else 0,
                                            now_str,
                                            v_role,
                                        ),
                                    )
                                emb26 = vinfo.get("embedding") or []
                                emb64 = vinfo.get("deep_embedding") or vinfo.get("deep_embedding_64d") or emb26
                                c.execute(
                                    """
                                    INSERT OR REPLACE INTO voiceprints (
                                        voiceprint_id, user_id, f0_hz, centroid_hz,
                                        embedding_26d_json, embedding_64d_json, sample_duration_sec, updated_at
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        str(vkey),
                                        uid,
                                        float(vinfo.get("f0_hz") or 175.0),
                                        float(vinfo.get("centroid_hz") or 1450.0),
                                        json.dumps(emb26),
                                        json.dumps(emb64),
                                        float(vinfo.get("sample_duration_sec") or 5.0),
                                        now_str,
                                    ),
                                )
                            _LAST_VP_MTIME = vp_mtime
                    except Exception:
                        pass

                # 6. Bảng `ir_remote_codes`
                ir_file = _active_db_path().parent / "ir_devices_db.json"
                if not ir_file.exists():
                    ir_file = DATA_DIR / "ir_devices_db.json"
                if ir_file.exists():
                    try:
                        ir_mtime = ir_file.stat().st_mtime
                        cur_ir = c.execute("SELECT COUNT(*) FROM ir_remote_codes").fetchone()[0]
                        if cur_ir == 0 or ir_mtime != _LAST_IR_MTIME:
                            ir_data = json.loads(ir_file.read_text(encoding="utf-8"))
                            appliances = ir_data.get("appliances", {}) if isinstance(ir_data, dict) else {}
                            for app_key, app_info in appliances.items():
                                app_name = str(app_info.get("name") or app_key)
                                proto = str(app_info.get("protocol") or "NEC_38KHZ")
                                dev_ref = "ac" if "ac" in app_key or "dieu_hoa" in app_key else ("fan" if "fan" in app_key or "quat" in app_key else None)
                                for cmd_act, hex_val in (app_info.get("commands", {}) or {}).items():
                                    ir_id = f"{app_key}_{cmd_act}"
                                    c.execute(
                                        """
                                        INSERT OR REPLACE INTO ir_remote_codes (
                                            ir_code_id, device_id, appliance_name, command_action,
                                            protocol, hex_code, freq_khz, learned_at
                                        ) VALUES (?, ?, ?, ?, ?, ?, 38, ?)
                                        """,
                                        (ir_id, dev_ref, app_name, str(cmd_act), proto, str(hex_val), now_str),
                                    )
                            _LAST_IR_MTIME = ir_mtime
                    except Exception:
                        pass

                # 7. Bảng `knowledge_rag`
                global _LAST_KB_MTIME
                kb_file = _active_db_path().parent / "knowledge_base.json"
                if not kb_file.exists():
                    kb_file = DATA_DIR / "knowledge_base.json"
                if kb_file.exists():
                    try:
                        kb_mtime = kb_file.stat().st_mtime
                        cur_kb = c.execute("SELECT COUNT(*) FROM knowledge_rag").fetchone()[0]
                        if cur_kb == 0 or kb_mtime != _LAST_KB_MTIME:
                            kb_raw = json.loads(kb_file.read_text(encoding="utf-8"))
                            kb_list = kb_raw.get("items", []) if isinstance(kb_raw, dict) else (kb_raw if isinstance(kb_raw, list) else [])
                            for idx_kb, item in enumerate(kb_list, 1):
                                if not isinstance(item, dict):
                                    continue
                                title_val = str(item.get("topic") or item.get("title") or f"kb_{idx_kb}")
                                doc_id = str(item.get("id") or f"kb_{idx_kb}")
                                kw_val = item.get("keywords") or []
                                if isinstance(kw_val, str):
                                    kw_val = [k.strip() for k in kw_val.split(",") if k.strip()]
                                c.execute(
                                    """
                                    INSERT OR REPLACE INTO knowledge_rag (
                                        doc_id, category, title, content, keywords_json, updated_by_user_id, updated_at
                                    ) VALUES (?, ?, ?, ?, ?, 'tuan_anh', ?)
                                    """,
                                    (
                                        doc_id,
                                        f"tier_le_{item.get('min_tier', 3)}",
                                        title_val,
                                        str(item.get("content") or ""),
                                        json.dumps(kw_val, ensure_ascii=False),
                                        now_str,
                                    ),
                                )
                            _LAST_KB_MTIME = kb_mtime
                    except Exception:
                        pass

                # 8. Bảng `audit_logs`: Nếu bảng đang trống thì nạp tối đa 150 dòng mới nhất từ system_audit_logs.jsonl
                cur_logs = c.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
                jsonl_file = _active_db_path().parent / "system_audit_logs.jsonl"
                if not jsonl_file.exists():
                    jsonl_file = DATA_DIR / "system_audit_logs.jsonl"
                if cur_logs == 0 and jsonl_file.exists():
                    try:
                        lines = jsonl_file.read_text(encoding="utf-8").splitlines()[-150:]
                        for ln in lines:
                            ln_s = ln.strip()
                            if not ln_s:
                                continue
                            entry = sanitize_overview_and_logs_payload(json.loads(ln_s))
                            c.execute(
                                """
                                INSERT INTO audit_logs (
                                    ts_iso, time_vn, category, event_type, user_id, user_name, tier, summary, details_json
                                ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?)
                                """,
                                (
                                    str(entry.get("ts_iso") or now_str),
                                    str(entry.get("time_vn") or ""),
                                    str(entry.get("category") or "SYSTEM"),
                                    str(entry.get("event_type") or "event"),
                                    str(entry.get("user") or "Hệ thống"),
                                    int(entry.get("tier") or 1),
                                    strip_emojis_for_audit(redact_otp_and_secrets_in_text(str(entry.get("summary") or ""))),
                                    json.dumps(_strip_emojis_in_obj(sanitize_overview_and_logs_payload(entry.get("details") or {})), ensure_ascii=False),
                                ),
                            )
                    except Exception:
                        pass

            run_write_transaction(conn, _sync_tx)
            for tbl in NORMALIZED_TABLE_ORDER:
                counts[tbl] = int(conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0])
        finally:
            conn.close()
        return counts


def _safe_sample_rows_for_table(conn: sqlite3.Connection, tname: str) -> list[dict[str, Any]]:
    if tname in SENSITIVE_SQLITE_TABLES:
        if tname == "users":
            rows = conn.execute(
                "SELECT user_id, full_name, role, tier, role_code, permission_active, permission_status, offline_allowed, updated_at FROM users LIMIT 15"
            ).fetchall()
            return [sanitize_overview_and_logs_payload(dict(r)) for r in rows]
        return []
    order_clause = "ORDER BY log_id DESC" if tname == "audit_logs" else ""
    rows = conn.execute(f"SELECT * FROM {tname} {order_clause} LIMIT 15").fetchall()
    cleaned_rows = [sanitize_overview_and_logs_payload(dict(r)) for r in rows]
    if tname == "audit_logs":
        return [_strip_emojis_in_obj(r) for r in cleaned_rows]
    return cleaned_rows


def get_sqlite_overview() -> dict[str, Any]:
    """Trả về thông tin chi tiết toàn bộ bảng SQLite chuẩn hoá 3NF, WAL/FK/SYNC/Timeout, indexes và số dòng."""
    with _DB_LOCK:
        target = init_sqlite_database()
        conn = get_connection(target)
        try:
            journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            fk_enabled = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            sync_mode = conn.execute("PRAGMA synchronous;").fetchone()[0]
            busy_ms = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
            existing_tables = {
                str(r["name"])
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            }
            tables_meta: list[dict[str, Any]] = []
            for tname in NORMALIZED_TABLE_ORDER:
                if tname not in existing_tables:
                    continue
                row_count = int(conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0])
                cols_info = [
                    {
                        "name": r["name"],
                        "type": r["type"],
                        "notnull": bool(r["notnull"]),
                        "pk": bool(r["pk"]),
                    }
                    for r in conn.execute(f"PRAGMA table_info({tname})").fetchall()
                ]
                fks_info = [
                    {
                        "from": r["from"],
                        "table": r["table"],
                        "to": r["to"],
                    }
                    for r in conn.execute(f"PRAGMA foreign_key_list({tname})").fetchall()
                ]
                idx_info = [
                    {"name": str(r["name"]), "unique": bool(r["unique"])}
                    for r in conn.execute(f"PRAGMA index_list({tname})").fetchall()
                ]
                tables_meta.append(
                    {
                        "table_name": tname,
                        "row_count": row_count,
                        "columns": cols_info,
                        "foreign_keys": fks_info,
                        "indexes": idx_info,
                        "sample_rows": _safe_sample_rows_for_table(conn, tname),
                    }
                )

            db_size = target.stat().st_size if target.exists() else 0
            return {
                "ok": True,
                "engine": "SQLite 3 Relational Database (ACID + WAL Mode)",
                "sqlite_version": sqlite3.sqlite_version,
                "db_file": str(target),
                "db_size_bytes": db_size,
                "journal_mode": str(journal_mode).upper(),
                "foreign_keys_enforced": bool(fk_enabled),
                "synchronous_mode": int(sync_mode),
                "busy_timeout_ms": int(busy_ms),
                "table_count": len(tables_meta),
                "tables": tables_meta,
            }
        finally:
            conn.close()


_FORBIDDEN_SQL_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|VACUUM|REINDEX)\b",
    re.IGNORECASE,
)


def execute_readonly_sql(sql_query: str, limit: int = 100) -> dict[str, Any]:
    """Thực thi truy vấn SQL chỉ đọc (SELECT / PRAGMA / EXPLAIN) an toàn trên `smarthome.db`."""
    q = (sql_query or "").strip()
    if not q:
        return {"ok": False, "error": "Câu lệnh SQL không được để trống."}
    if _FORBIDDEN_SQL_RE.search(q):
        return {
            "ok": False,
            "error": "Chế độ bảo vệ CSDL: Chỉ cho phép truy vấn đọc (SELECT / PRAGMA / EXPLAIN).",
        }
    first_word = q.split()[0].upper()
    if first_word not in ("SELECT", "PRAGMA", "EXPLAIN", "WITH"):
        return {
            "ok": False,
            "error": "Câu lệnh phải bắt đầu bằng SELECT, WITH, PRAGMA hoặc EXPLAIN.",
        }

    with _DB_LOCK:
        target = init_sqlite_database()
        conn = open_wal_connection(target, readonly=True)
        try:
            cur = conn.execute(q)
            rows = [dict(r) for r in cur.fetchmany(limit)]
            columns = [desc[0] for desc in (cur.description or [])]
            return {
                "ok": True,
                "sql": q,
                "columns": columns,
                "row_count": len(rows),
                "rows": rows,
            }
        except Exception as exc:
            return {"ok": False, "sql": q, "error": str(exc)}
        finally:
            conn.close()
