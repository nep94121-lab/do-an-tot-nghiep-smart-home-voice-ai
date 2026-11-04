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
from typing import Any

from simulator.engine.constants_and_time import resolve_data_dir

DATA_DIR = resolve_data_dir()

SQLITE_DB_PATH = DATA_DIR / "smarthome.db"
_DB_LOCK = threading.RLock()

DDL_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL,
    tier INTEGER NOT NULL CHECK (tier IN (1, 2, 3)),
    offline_allowed INTEGER NOT NULL DEFAULT 0,
    created_by TEXT DEFAULT 'SYSTEM',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS voiceprints (
    voiceprint_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    f0_hz REAL NOT NULL,
    centroid_hz REAL NOT NULL,
    embedding_26d_json TEXT NOT NULL,
    embedding_64d_json TEXT NOT NULL,
    sample_duration_sec REAL NOT NULL DEFAULT 5.0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    device_name TEXT NOT NULL,
    gpio_pin TEXT NOT NULL,
    state TEXT NOT NULL,
    min_tier_required INTEGER NOT NULL DEFAULT 3,
    offline_controllable INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS timers_pool (
    timer_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    schedule_mode TEXT NOT NULL,
    target_time_vn TEXT NOT NULL,
    repeat_rule TEXT NOT NULL DEFAULT 'once',
    label_summary TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rules_pool (
    rule_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    rule_category TEXT NOT NULL,
    trigger_expr TEXT NOT NULL,
    target_device_id TEXT REFERENCES devices(device_id) ON DELETE SET NULL,
    target_action TEXT NOT NULL,
    bidirectional INTEGER NOT NULL DEFAULT 0,
    else_action TEXT DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ir_remote_codes (
    ir_code_id TEXT PRIMARY KEY,
    device_id TEXT REFERENCES devices(device_id) ON DELETE SET NULL,
    appliance_name TEXT NOT NULL,
    command_action TEXT NOT NULL,
    protocol TEXT NOT NULL,
    hex_code TEXT NOT NULL,
    freq_khz INTEGER NOT NULL DEFAULT 38,
    learned_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_rag (
    doc_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    keywords_json TEXT NOT NULL DEFAULT '[]',
    updated_by_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_iso TEXT NOT NULL,
    time_vn TEXT NOT NULL,
    category TEXT NOT NULL,
    event_type TEXT NOT NULL,
    user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    user_name TEXT NOT NULL,
    tier INTEGER NOT NULL,
    summary TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_ts ON audit_logs(ts_iso DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_cat_tier ON audit_logs(category, tier);
CREATE INDEX IF NOT EXISTS idx_timers_owner ON timers_pool(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_rules_owner_cat ON rules_pool(owner_user_id, rule_category);
CREATE INDEX IF NOT EXISTS idx_voiceprints_user ON voiceprints(user_id);
"""


def _now_iso() -> str:
    tz = datetime.timezone(datetime.timedelta(hours=7))
    return datetime.datetime.now(tz).isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(SQLITE_DB_PATH), timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA synchronous = OFF;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


_SCHEMA_INITIALIZED = False
_WAL_ANCHOR_CONN: sqlite3.Connection | None = None
_LAST_KB_MTIME: float = -1.0
_LAST_VP_MTIME: float = -1.0
_LAST_IR_MTIME: float = -1.0


def init_sqlite_database() -> None:
    """Khởi tạo cấu trúc 8 bảng SQL chuẩn 3NF + Indexes và nạp dữ liệu ban đầu nếu bảng rỗng."""
    global _SCHEMA_INITIALIZED, _WAL_ANCHOR_CONN
    with _DB_LOCK:
        if _SCHEMA_INITIALIZED and _WAL_ANCHOR_CONN is not None and SQLITE_DB_PATH.exists():
            return
        conn = get_connection()
        conn.executescript(DDL_SCHEMA_SQL)
        conn.commit()
        _WAL_ANCHOR_CONN = conn
        _SCHEMA_INITIALIZED = True


def insert_audit_log_sqlite(entry: dict[str, Any], user_id: str | None = None) -> None:
    """Ghi trực tiếp 1 bản ghi nhật ký vào bảng `audit_logs` trong SQLite (ACID Transaction)."""
    with _DB_LOCK:
        init_sqlite_database()
        conn = get_connection()
        try:
            uid = user_id
            if uid:
                row = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (uid,)).fetchone()
                if not row:
                    uid = None
            conn.execute(
                """
                INSERT INTO audit_logs (
                    ts_iso, time_vn, category, event_type, user_id, user_name, tier, summary, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(entry.get("ts_iso") or _now_iso()),
                    str(entry.get("time_vn") or ""),
                    str(entry.get("category") or "SYSTEM"),
                    str(entry.get("event_type") or "event"),
                    uid,
                    str(entry.get("user") or "Hệ thống"),
                    int(entry.get("tier") or 1),
                    str(entry.get("summary") or ""),
                    json.dumps(entry.get("details") or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        except Exception:
            pass
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
            with conn:
                conn.execute("DELETE FROM audit_logs")
                conn.execute(
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
            with conn:
                # 1. Bảng `users`
                users_dict = getattr(engine, "users", {}) or {}
                valid_uids = [str(u) for u, inf in users_dict.items() if int(inf.get("tier", 3)) in (1, 2, 3)]
                if valid_uids:
                    placeholders = ",".join("?" for _ in valid_uids)
                    conn.execute(f"DELETE FROM users WHERE user_id NOT IN ({placeholders})", valid_uids)
                for uid, uinfo in users_dict.items():
                    tier_val = int(uinfo.get("tier", 3))
                    if tier_val not in (1, 2, 3):
                        continue
                    conn.execute(
                        """
                        INSERT INTO users (user_id, full_name, role, tier, offline_allowed, created_by, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET
                            full_name = excluded.full_name,
                            role = excluded.role,
                            tier = excluded.tier,
                            offline_allowed = excluded.offline_allowed,
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
                        ),
                    )

                # 2. Bảng `devices`
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
                for did, dinfo in devs_dict.items():
                    offline_ok = 0 if did in ("main_door", "alarm_siren") else 1
                    conn.execute(
                        """
                        INSERT INTO devices (device_id, device_name, gpio_pin, state, min_tier_required, offline_controllable, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(device_id) DO UPDATE SET
                            device_name = excluded.device_name,
                            gpio_pin = excluded.gpio_pin,
                            state = excluded.state,
                            min_tier_required = excluded.min_tier_required,
                            offline_controllable = excluded.offline_controllable,
                            updated_at = excluded.updated_at
                        """,
                        (
                            str(did),
                            str(dinfo.get("name") or did),
                            PIN_MAP.get(str(did), "GPIO"),
                            str(dinfo.get("state") or "OFF"),
                            int(dev_min_tiers.get(did, 3)),
                            offline_ok,
                            now_str,
                        ),
                    )

                # 3. Bảng `timers_pool` (Bể 1 - Hẹn giờ)
                conn.execute("DELETE FROM timers_pool")
                active_timers = getattr(engine, "active_timers", {}) or {}
                for tid, tinfo in active_timers.items():
                    owner_id = str(tinfo.get("owner_id") or "tuan_anh")
                    if owner_id not in users_dict:
                        owner_id = "tuan_anh"
                    dev_id = str(tinfo.get("device_id") or "living_room_light")
                    if dev_id not in devs_dict:
                        continue
                    conn.execute(
                        """
                        INSERT INTO timers_pool (
                            timer_id, owner_user_id, device_id, action, schedule_mode,
                            target_time_vn, repeat_rule, label_summary, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(tid),
                            owner_id,
                            dev_id,
                            str(tinfo.get("action") or "turn_on"),
                            str(tinfo.get("mode") or "countdown"),
                            str(tinfo.get("target_clock_str") or f"{tinfo.get('seconds', 0)}s"),
                            str(tinfo.get("repeat") or "once"),
                            str(tinfo.get("label") or tid),
                            now_str,
                        ),
                    )

                # 4. Bảng `rules_pool` (Bể 2 - Luật IF-ELSE, Khẩu lệnh & Từ vựng)
                conn.execute("DELETE FROM rules_pool")
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
                        conn.execute(
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
                        conn.execute(
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
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO rules_pool (
                                rule_id, owner_user_id, rule_category, trigger_expr,
                                target_device_id, target_action, bidirectional, else_action, updated_at
                            ) VALUES (?, ?, 'VOCAB_MAP', ?, NULL, ?, 0, '', ?)
                            """,
                            (rid, owner_id, str(src_word), str(dst_word), now_str),
                        )

                # 5. Bảng `voiceprints` (từ simulator/data/voiceprints.json)
                global _LAST_VP_MTIME, _LAST_IR_MTIME
                vp_file = DATA_DIR / "voiceprints.json"
                if vp_file.exists():
                    try:
                        vp_mtime = vp_file.stat().st_mtime
                        cur_vp = conn.execute("SELECT COUNT(*) FROM voiceprints").fetchone()[0]
                        if cur_vp == 0 or vp_mtime != _LAST_VP_MTIME:
                            conn.execute("DELETE FROM voiceprints")
                            vp_data = json.loads(vp_file.read_text(encoding="utf-8"))
                            profiles = vp_data.get("profiles", vp_data) if isinstance(vp_data, dict) else {}
                            for vkey, vinfo in profiles.items():
                                if not isinstance(vinfo, dict):
                                    continue
                                if not vinfo.get("authorized", True):
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
                                    v_role = "ADMIN" if v_tier == 1 else ("MEMBER" if v_tier == 2 else "CHILD_GUEST")
                                    conn.execute(
                                        """
                                        INSERT OR IGNORE INTO users (user_id, full_name, role, tier, offline_allowed, created_by, updated_at)
                                        VALUES (?, ?, ?, ?, ?, 'SYSTEM', ?)
                                        """,
                                        (
                                            uid,
                                            str(vinfo.get("name") or uid),
                                            v_role,
                                            v_tier,
                                            1 if v_tier in (1, 2) else 0,
                                            now_str,
                                        ),
                                    )
                                emb26 = vinfo.get("embedding") or []
                                emb64 = vinfo.get("deep_embedding") or vinfo.get("deep_embedding_64d") or emb26
                                conn.execute(
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

                # 6. Bảng `ir_remote_codes` (từ simulator/data/ir_devices_db.json)
                ir_file = DATA_DIR / "ir_devices_db.json"
                if ir_file.exists():
                    try:
                        ir_mtime = ir_file.stat().st_mtime
                        cur_ir = conn.execute("SELECT COUNT(*) FROM ir_remote_codes").fetchone()[0]
                        if cur_ir == 0 or ir_mtime != _LAST_IR_MTIME:
                            ir_data = json.loads(ir_file.read_text(encoding="utf-8"))
                            appliances = ir_data.get("appliances", {}) if isinstance(ir_data, dict) else {}
                            for app_key, app_info in appliances.items():
                                app_name = str(app_info.get("name") or app_key)
                                proto = str(app_info.get("protocol") or "NEC_38KHZ")
                                dev_ref = "ac" if "ac" in app_key or "dieu_hoa" in app_key else ("fan" if "fan" in app_key or "quat" in app_key else None)
                                for cmd_act, hex_val in (app_info.get("commands", {}) or {}).items():
                                    ir_id = f"{app_key}_{cmd_act}"
                                    conn.execute(
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

                # 7. Bảng `knowledge_rag` (từ simulator/data/knowledge_base.json)
                global _LAST_KB_MTIME
                kb_file = DATA_DIR / "knowledge_base.json"
                if kb_file.exists():
                    try:
                        kb_mtime = kb_file.stat().st_mtime
                        cur_kb = conn.execute("SELECT COUNT(*) FROM knowledge_rag").fetchone()[0]
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
                                conn.execute(
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
                cur_logs = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
                jsonl_file = DATA_DIR / "system_audit_logs.jsonl"
                if cur_logs == 0 and jsonl_file.exists():
                    try:
                        lines = jsonl_file.read_text(encoding="utf-8").splitlines()[-150:]
                        for ln in lines:
                            ln_s = ln.strip()
                            if not ln_s:
                                continue
                            entry = json.loads(ln_s)
                            conn.execute(
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
                                    str(entry.get("summary") or ""),
                                    json.dumps(entry.get("details") or {}, ensure_ascii=False),
                                ),
                            )
                    except Exception:
                        pass

                for tbl in (
                    "users",
                    "voiceprints",
                    "devices",
                    "timers_pool",
                    "rules_pool",
                    "ir_remote_codes",
                    "knowledge_rag",
                    "audit_logs",
                ):
                    counts[tbl] = int(conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0])
        finally:
            conn.close()
        return counts


def get_sqlite_overview() -> dict[str, Any]:
    """Trả về thông tin chi tiết 8 bảng SQLite (`smarthome.db`), cấu hình WAL/FK, số dòng và dữ liệu mẫu."""
    with _DB_LOCK:
        init_sqlite_database()
        conn = get_connection()
        try:
            journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            fk_enabled = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            tables_meta: list[dict[str, Any]] = []
            table_names = [
                "users",
                "voiceprints",
                "devices",
                "timers_pool",
                "rules_pool",
                "ir_remote_codes",
                "knowledge_rag",
                "audit_logs",
            ]
            for tname in table_names:
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
                order_clause = "ORDER BY log_id DESC" if tname == "audit_logs" else ""
                sample_rows = [
                    dict(r)
                    for r in conn.execute(f"SELECT * FROM {tname} {order_clause} LIMIT 15").fetchall()
                ]
                tables_meta.append(
                    {
                        "table_name": tname,
                        "row_count": row_count,
                        "columns": cols_info,
                        "foreign_keys": fks_info,
                        "sample_rows": sample_rows,
                    }
                )

            db_size = SQLITE_DB_PATH.stat().st_size if SQLITE_DB_PATH.exists() else 0
            return {
                "ok": True,
                "engine": "SQLite 3 Relational Database (ACID + WAL Mode)",
                "sqlite_version": sqlite3.sqlite_version,
                "db_file": "simulator/data/smarthome.db",
                "db_size_bytes": db_size,
                "journal_mode": str(journal_mode).upper(),
                "foreign_keys_enforced": bool(fk_enabled),
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
        init_sqlite_database()
        db_uri = f"file:{SQLITE_DB_PATH.as_posix()}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
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
