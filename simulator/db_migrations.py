"""Normalized 3NF SQLite WAL schema, idempotent migrations, and hot indexes."""

from __future__ import annotations

import atexit
import contextlib
import datetime
import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import threading
from typing import Any, Callable, TypeVar

from simulator.engine.constants_and_time import resolve_data_dir

_T = TypeVar("_T")

DEFAULT_ROLES: tuple[tuple[str, int, str, str], ...] = (
    ("ADMIN", 1, "Chủ nhà (Tầng 1)", "Toàn quyền điều khiển, quản trị người dùng, mời khách, PIN và nhật ký"),
    ("MEMBER", 2, "Gia đình (Tầng 2)", "Điều khiển thiết bị sinh hoạt trừ cửa chính và còi báo động"),
    ("CHILD_GUEST", 3, "Khách (Tầng 3)", "Chỉ điều khiển đèn và quạt cơ bản"),
    ("UNKNOWN", 4, "Chưa định danh", "Không có quyền điều khiển thiết bị"),
)

NORMALIZED_TABLE_ORDER: tuple[str, ...] = (
    "schema_migrations",
    "roles",
    "users",
    "devices",
    "device_state",
    "system_state_meta",
    "invites",
    "sessions",
    "user_sessions",
    "otp_challenges",
    "trusted_devices",
    "owner_pin_security",
    "login_rate_limits",
    "aoede_audio_cache",
    "system_kv_meta",
    "voiceprints",
    "timers_pool",
    "schedules",
    "automation_rules",
    "custom_commands",
    "rules_pool",
    "ir_remote_codes",
    "knowledge_rag",
    "audit_logs",
)

SENSITIVE_SQLITE_TABLES: frozenset[str] = frozenset(
    {
        "users",
        "voiceprints",
        "sessions",
        "user_sessions",
        "invites",
        "otp_challenges",
        "trusted_devices",
        "owner_pin_security",
        "login_rate_limits",
        "aoede_audio_cache",
    }
)

_CORE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roles (
    role_code TEXT PRIMARY KEY,
    tier INTEGER NOT NULL UNIQUE CHECK (tier IN (1, 2, 3, 4)),
    display_name_vi TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL,
    tier INTEGER NOT NULL CHECK (tier IN (1, 2, 3)),
    offline_allowed INTEGER NOT NULL DEFAULT 0,
    created_by TEXT DEFAULT 'SYSTEM',
    updated_at TEXT NOT NULL,
    email TEXT DEFAULT '',
    role_code TEXT REFERENCES roles(role_code),
    password_salt TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL DEFAULT '',
    password_updated_at REAL NOT NULL DEFAULT 0,
    permission_active INTEGER NOT NULL DEFAULT 1,
    permission_status TEXT NOT NULL DEFAULT 'ACTIVE',
    is_allowlisted INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT '',
    account_meta_json TEXT NOT NULL DEFAULT '{}'
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
    updated_at TEXT NOT NULL,
    min_role TEXT REFERENCES roles(role_code),
    room TEXT NOT NULL DEFAULT '',
    device_type TEXT NOT NULL DEFAULT 'switch'
);

CREATE TABLE IF NOT EXISTS device_state (
    device_id TEXT PRIMARY KEY REFERENCES devices(device_id) ON DELETE CASCADE,
    state TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at REAL NOT NULL,
    last_client_id TEXT NOT NULL DEFAULT '',
    last_client_seq INTEGER NOT NULL DEFAULT 0,
    last_client_ts_ms INTEGER NOT NULL DEFAULT 0,
    last_request_id TEXT NOT NULL DEFAULT '',
    last_requested_state TEXT NOT NULL DEFAULT '',
    client_seqs_json TEXT NOT NULL DEFAULT '{}',
    extra_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS system_state_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    revision_seq INTEGER NOT NULL DEFAULT 0,
    revision_ts_ns INTEGER NOT NULL DEFAULT 0,
    server_connected INTEGER NOT NULL DEFAULT 1,
    pump_manual_override_off INTEGER NOT NULL DEFAULT 0,
    dht_temp_c REAL,
    dht_hum_pct REAL,
    soil_moisture_pct REAL,
    dht11_json TEXT NOT NULL DEFAULT '{}',
    soil_moisture_json TEXT NOT NULL DEFAULT '{}',
    updated_at REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS invites (
    jti TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL,
    owner_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role_code TEXT NOT NULL REFERENCES roles(role_code),
    tier INTEGER NOT NULL CHECK (tier IN (2, 3)),
    label TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    revoked_at REAL NOT NULL DEFAULT 0,
    redeem_count INTEGER NOT NULL DEFAULT 0,
    last_redeem_at REAL NOT NULL DEFAULT 0,
    extra_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL,
    user_id TEXT REFERENCES users(user_id) ON DELETE CASCADE,
    role_code TEXT NOT NULL REFERENCES roles(role_code),
    tier INTEGER NOT NULL CHECK (tier IN (1, 2, 3, 4)),
    source TEXT NOT NULL DEFAULT 'web',
    invite_jti TEXT REFERENCES invites(jti) ON DELETE SET NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    revoked_at REAL
);

CREATE TABLE IF NOT EXISTS user_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(user_id) ON DELETE CASCADE,
    tier INTEGER NOT NULL,
    role TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    source TEXT
);

CREATE TABLE IF NOT EXISTS otp_challenges (
    challenge_id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT 'login',
    otp_salt TEXT NOT NULL,
    otp_hash TEXT NOT NULL,
    issued_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    meta_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS trusted_devices (
    device_token_hash TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    user_agent_hash TEXT NOT NULL DEFAULT '',
    label TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    last_used_at REAL NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS owner_pin_security (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    pin_salt TEXT NOT NULL DEFAULT '',
    pin_hash TEXT NOT NULL DEFAULT '',
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked INTEGER NOT NULL DEFAULT 0,
    otp_salt TEXT NOT NULL DEFAULT '',
    otp_hash TEXT NOT NULL DEFAULT '',
    otp_expires_at REAL NOT NULL DEFAULT 0,
    otp_used INTEGER NOT NULL DEFAULT 0,
    otp_failed_attempts INTEGER NOT NULL DEFAULT 0,
    otp_issued_at REAL NOT NULL DEFAULT 0,
    revision INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS login_rate_limits (
    scope_key TEXT PRIMARY KEY,
    attempts_json TEXT NOT NULL DEFAULT '[]',
    locked_until REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS aoede_audio_cache (
    cache_key TEXT PRIMARY KEY,
    phrase_norm TEXT NOT NULL,
    voice_name TEXT NOT NULL DEFAULT 'Aoede',
    model_id TEXT NOT NULL DEFAULT '',
    sample_rate INTEGER NOT NULL DEFAULT 24000,
    pcm_bytes BLOB NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS system_kv_meta (
    meta_key TEXT PRIMARY KEY,
    meta_value_json TEXT NOT NULL DEFAULT '{}',
    updated_at REAL NOT NULL DEFAULT 0
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
    updated_at TEXT NOT NULL,
    fire_at_epoch REAL NOT NULL DEFAULT 0,
    delay_seconds REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    owner_tier INTEGER NOT NULL DEFAULT 1,
    label TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS schedules (
    schedule_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    owner_tier INTEGER NOT NULL DEFAULT 1,
    device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    time_hhmm TEXT NOT NULL,
    schedule_type TEXT NOT NULL DEFAULT 'once' CHECK (schedule_type IN ('once', 'daily')),
    run_date_vn TEXT NOT NULL DEFAULT '',
    timezone TEXT NOT NULL DEFAULT 'Asia/Saigon',
    enabled INTEGER NOT NULL DEFAULT 1,
    last_fired_date_vn TEXT NOT NULL DEFAULT '',
    label TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS automation_rules (
    rule_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    owner_tier INTEGER NOT NULL DEFAULT 1,
    when_device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    when_state TEXT NOT NULL,
    then_device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    then_action TEXT NOT NULL,
    else_device_id TEXT REFERENCES devices(device_id) ON DELETE SET NULL,
    else_action TEXT NOT NULL DEFAULT '',
    delay_seconds REAL NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    label TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS custom_commands (
    command_id TEXT PRIMARY KEY,
    phrase TEXT NOT NULL,
    phrase_norm TEXT NOT NULL UNIQUE,
    owner_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    owner_tier INTEGER NOT NULL DEFAULT 1,
    steps_json TEXT NOT NULL DEFAULT '[]',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0
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
"""

_HOT_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_audit_logs_ts ON audit_logs(ts_iso DESC, log_id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_ts ON audit_logs(user_name, ts_iso DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_cat_tier ON audit_logs(category, tier, log_id DESC);
CREATE INDEX IF NOT EXISTS idx_timers_owner ON timers_pool(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_timers_status_fire ON timers_pool(status, fire_at_epoch);
CREATE INDEX IF NOT EXISTS idx_schedules_enabled_time ON schedules(enabled, time_hhmm);
CREATE INDEX IF NOT EXISTS idx_schedules_owner ON schedules(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_automation_rules_trigger ON automation_rules(enabled, when_device_id, when_state);
CREATE INDEX IF NOT EXISTS idx_automation_rules_owner ON automation_rules(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_custom_commands_enabled ON custom_commands(enabled, phrase_norm);
CREATE INDEX IF NOT EXISTS idx_rules_owner_cat ON rules_pool(owner_user_id, rule_category);
CREATE INDEX IF NOT EXISTS idx_voiceprints_user ON voiceprints(user_id);
CREATE INDEX IF NOT EXISTS idx_users_role_tier ON users(role_code, tier);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(lower(email)) WHERE email IS NOT NULL AND email != '';
CREATE INDEX IF NOT EXISTS idx_device_state_updated ON device_state(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_user_exp ON sessions(user_id, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_invite ON sessions(invite_jti);
CREATE INDEX IF NOT EXISTS idx_sessions_exp ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_exp ON user_sessions(user_id, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_invites_token_hash ON invites(token_hash);
CREATE INDEX IF NOT EXISTS idx_invites_owner_exp ON invites(owner_user_id, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_invites_revoked_exp ON invites(revoked, expires_at);
CREATE INDEX IF NOT EXISTS idx_otp_email_purpose_exp ON otp_challenges(lower(email), purpose, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_trusted_account_exp ON trusted_devices(account_id, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_aoede_phrase_voice ON aoede_audio_cache(phrase_norm, voice_name);
"""


def _now_iso() -> str:
    tz = datetime.timezone(datetime.timedelta(hours=7))
    return datetime.datetime.now(tz).isoformat()


def role_for_tier(tier: int | str | None) -> str:
    try:
        t = int(tier or 3)
    except (TypeError, ValueError):
        t = 3
    if t == 1:
        return "ADMIN"
    if t == 2:
        return "MEMBER"
    if t == 3:
        return "CHILD_GUEST"
    return "UNKNOWN"


def resolve_sqlite_db_path(data_dir: pathlib.Path | None = None) -> pathlib.Path:
    """Resolve the active SQLite database path dynamically without static caching."""
    if data_dir is not None:
        return pathlib.Path(data_dir) / "smarthome.db"
    explicit_db = os.environ.get("SMARTHOME_SQLITE_PATH", "").strip()
    if explicit_db:
        return pathlib.Path(explicit_db)
    explicit_dir = os.environ.get("SMARTHOME_DATA_DIR", "").strip()
    if explicit_dir and not os.environ.get("VERCEL"):
        return pathlib.Path(explicit_dir) / "smarthome.db"
    return resolve_data_dir() / "smarthome.db"


_WAL_LOCK = threading.Lock()
_WAL_ANCHOR_CONNS: dict[str, sqlite3.Connection] = {}
_WAL_READY_PATHS: set[str] = set()


def _should_keep_wal_anchor(target: pathlib.Path) -> bool:
    """Keep a lightweight WAL anchor connection for long-lived DBs so Windows does not drop -shm on every close."""
    if (
        "pytest" in sys.modules
        or os.environ.get("PYTEST", "").strip()
        or os.environ.get("PYTEST_CURRENT_TEST", "").strip()
    ):
        return False
    try:
        resolved = str(target.resolve()).lower()
    except OSError:
        resolved = str(target).lower()
    if resolved == ":memory:":
        return False
    return True


def close_wal_anchors() -> None:
    """Close any persistent WAL anchor connections and clear cached WAL path flags."""
    with _WAL_LOCK:
        for conn in list(_WAL_ANCHOR_CONNS.values()):
            with contextlib.suppress(Exception):
                conn.close()
        _WAL_ANCHOR_CONNS.clear()
        _WAL_READY_PATHS.clear()


atexit.register(close_wal_anchors)


def configure_wal_pragmas(
    conn: sqlite3.Connection,
    *,
    readonly: bool = False,
    set_wal_mode: bool = True,
) -> None:
    """Apply consistent WAL, foreign-key, synchronous, and busy-timeout PRAGMAs."""
    conn.execute("PRAGMA busy_timeout = 10000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    if not readonly:
        if set_wal_mode:
            with contextlib.suppress(sqlite3.DatabaseError):
                conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")


def open_wal_connection(
    db_path: pathlib.Path | None = None,
    *,
    readonly: bool = False,
) -> sqlite3.Connection:
    """Open a configured SQLite connection with WAL and foreign keys enabled."""
    target = pathlib.Path(db_path) if db_path is not None else resolve_sqlite_db_path()
    if readonly:
        db_uri = f"file:{target.as_posix()}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        configure_wal_pragmas(conn, readonly=True, set_wal_mode=False)
        return conn

    key = str(target.resolve())
    with _WAL_LOCK:
        if not target.exists():
            stale = _WAL_ANCHOR_CONNS.pop(key, None)
            if stale is not None:
                with contextlib.suppress(Exception):
                    stale.close()
            _WAL_READY_PATHS.discard(key)

        need_setup = key not in _WAL_READY_PATHS
        if need_setup:
            target.parent.mkdir(parents=True, exist_ok=True)
        if _should_keep_wal_anchor(target) and key not in _WAL_ANCHOR_CONNS:
            anchor = sqlite3.connect(
                str(target),
                timeout=10.0,
                isolation_level=None,
                check_same_thread=False,
            )
            configure_wal_pragmas(anchor, readonly=False, set_wal_mode=True)
            _WAL_ANCHOR_CONNS[key] = anchor
            _WAL_READY_PATHS.add(key)
            need_wal_mode = False
        else:
            need_wal_mode = need_setup

    conn = sqlite3.connect(
        str(target),
        timeout=10.0,
        isolation_level=None,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    configure_wal_pragmas(conn, readonly=False, set_wal_mode=need_wal_mode)
    if need_wal_mode:
        with _WAL_LOCK:
            _WAL_READY_PATHS.add(key)
    return conn


def run_write_transaction(
    conn: sqlite3.Connection,
    fn: Callable[[sqlite3.Connection], _T],
) -> _T:
    """Run fn inside an explicit BEGIN IMMEDIATE transaction with clean rollback on failure."""
    conn.execute("BEGIN IMMEDIATE;")
    try:
        result = fn(conn)
        conn.execute("COMMIT;")
        return result
    except Exception:
        with contextlib.suppress(sqlite3.DatabaseError):
            conn.execute("ROLLBACK;")
        raise


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(r["name"]) for r in rows}


def _ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    col_name: str,
    col_def_sql: str,
) -> None:
    if col_name not in _table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def_sql};")


def _table_fk_targets(conn: sqlite3.Connection, table_name: str) -> set[tuple[str, str, str]]:
    rows = conn.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
    return {(str(r["table"]), str(r["from"]), str(r["to"])) for r in rows}


def _is_guest_or_anon_user_id(user_id: str | None, source: str = "", invite_jti: str = "") -> bool:
    uid = str(user_id or "").strip().lower()
    src = str(source or "").strip().lower()
    if not uid or uid in ("anonymous", "unknown", "stranger", "guest"):
        return True
    if uid.startswith("guest_") or src.startswith("guest_invite:"):
        return True
    if invite_jti and uid.startswith("guest"):
        return True
    return False


def _ensure_preserve_user_for_fk(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    tier: int = 3,
    role_code: str = "",
    display_name: str = "",
    email: str = "",
    active: bool = False,
) -> None:
    uid = str(user_id or "").strip()
    if not uid:
        return
    safe_email = str(email or "").strip().lower()
    if safe_email:
        conflict = conn.execute(
            "SELECT 1 FROM users WHERE lower(email) = ? AND user_id != ?",
            (safe_email, uid),
        ).fetchone()
        if conflict:
            safe_email = ""
    existing = conn.execute("SELECT email, full_name FROM users WHERE user_id = ?", (uid,)).fetchone()
    if existing is not None:
        if active and safe_email and not str(existing["email"] or "").strip():
            conn.execute(
                "UPDATE users SET email = ? WHERE user_id = ?",
                (safe_email, uid),
            )
        if active and display_name and not str(existing["full_name"] or "").strip():
            conn.execute(
                "UPDATE users SET full_name = ? WHERE user_id = ?",
                (str(display_name), uid),
            )
        return
    safe_tier = int(tier) if int(tier or 3) in (1, 2, 3) else 3
    safe_rc = role_code if role_code in ("ADMIN", "MEMBER", "CHILD_GUEST") else role_for_tier(safe_tier)
    now_iso = _now_iso()
    conn.execute(
        """
        INSERT OR IGNORE INTO users (
            user_id, full_name, role, tier, offline_allowed, created_by, updated_at,
            email, role_code, permission_active, permission_status, is_allowlisted, is_active, created_at, account_meta_json
        ) VALUES (?, ?, ?, ?, ?, 'MIGRATION_V3', ?, ?, ?, ?, ?, ?, ?, ?, '{}')
        """,
        (
            uid,
            str(display_name or uid),
            safe_rc,
            safe_tier,
            1 if (active and safe_tier in (1, 2)) else 0,
            now_iso,
            safe_email,
            safe_rc,
            1 if active else 0,
            "ACTIVE" if active else "PRESERVED_LEGACY",
            1 if active else 0,
            1 if active else 0,
            now_iso,
        ),
    )


def _migrate_schema_v3(conn: sqlite3.Connection) -> None:
    """Lossless idempotent v3 rebuild: invites hash-only + FK, sessions/user_sessions FK to users, P1 columns."""
    _ensure_column(conn, "timers_pool", "fire_at_epoch", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "timers_pool", "delay_seconds", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "timers_pool", "status", "TEXT NOT NULL DEFAULT 'pending'")
    _ensure_column(conn, "timers_pool", "owner_tier", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "timers_pool", "label", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "timers_pool", "created_at", "REAL NOT NULL DEFAULT 0")

    inv_cols = _table_columns(conn, "invites")
    inv_fks = _table_fk_targets(conn, "invites")
    need_invites_rebuild = (
        "token" in inv_cols
        or ("users", "owner_user_id", "user_id") not in inv_fks
    )

    sess_cols = _table_columns(conn, "sessions")
    sess_fks = _table_fk_targets(conn, "sessions")
    need_sessions_rebuild = (
        "email" in sess_cols
        or "display_name" in sess_cols
        or ("users", "user_id", "user_id") not in sess_fks
        or ("invites", "invite_jti", "jti") not in sess_fks
    )

    usess_cols = _table_columns(conn, "user_sessions")
    usess_fks = _table_fk_targets(conn, "user_sessions")
    need_usess_rebuild = (
        "email" in usess_cols
        or "display_name" in usess_cols
        or ("users", "user_id", "user_id") not in usess_fks
    )

    if not (need_invites_rebuild or need_sessions_rebuild or need_usess_rebuild):
        return

    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        def _rebuild_tx(c: sqlite3.Connection) -> None:
            if need_invites_rebuild:
                c.execute(
                    """
                    CREATE TABLE invites_v3 (
                        jti TEXT PRIMARY KEY,
                        token_hash TEXT NOT NULL,
                        owner_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                        role_code TEXT NOT NULL REFERENCES roles(role_code),
                        tier INTEGER NOT NULL CHECK (tier IN (2, 3)),
                        label TEXT NOT NULL DEFAULT '',
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        revoked INTEGER NOT NULL DEFAULT 0,
                        revoked_at REAL NOT NULL DEFAULT 0,
                        redeem_count INTEGER NOT NULL DEFAULT 0,
                        last_redeem_at REAL NOT NULL DEFAULT 0,
                        extra_json TEXT NOT NULL DEFAULT '{}'
                    )
                    """
                )
                has_raw_tok = "token" in inv_cols
                for r in c.execute("SELECT * FROM invites").fetchall():
                    rd = dict(r)
                    jti = str(rd.get("jti") or "").strip()
                    if not jti:
                        continue
                    owner_id = str(rd.get("owner_user_id") or "").strip() or "tuan_anh"
                    _ensure_preserve_user_for_fk(
                        c, owner_id, tier=1, role_code="ADMIN", display_name=owner_id, active=False
                    )
                    raw_tok = str(rd.get("token") or "").strip() if has_raw_tok else ""
                    tok_hash = str(rd.get("token_hash") or "").strip()
                    if not tok_hash or (raw_tok and tok_hash == hashlib.sha256(jti.encode("utf-8")).hexdigest()):
                        tok_hash = hashlib.sha256((raw_tok or jti).encode("utf-8")).hexdigest()
                    tier = int(rd.get("tier") or 3)
                    if tier not in (2, 3):
                        tier = 3
                    rc = str(rd.get("role_code") or role_for_tier(tier))
                    if rc not in ("MEMBER", "CHILD_GUEST"):
                        rc = role_for_tier(tier)
                    try:
                        extra_obj = json.loads(str(rd.get("extra_json") or "{}"))
                    except Exception:
                        extra_obj = {}
                    if isinstance(extra_obj, dict):
                        extra_obj.pop("token", None)
                        extra_obj["token_hash"] = tok_hash
                        extra_str = json.dumps(extra_obj, ensure_ascii=False)
                    else:
                        extra_str = "{}"
                    c.execute(
                        """
                        INSERT INTO invites_v3 (
                            jti, token_hash, owner_user_id, role_code, tier, label,
                            created_at, expires_at, revoked, revoked_at, redeem_count, last_redeem_at, extra_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            jti,
                            tok_hash,
                            owner_id,
                            rc,
                            tier,
                            str(rd.get("label") or ""),
                            float(rd.get("created_at") or 0.0),
                            float(rd.get("expires_at") or 0.0),
                            int(rd.get("revoked") or 0),
                            float(rd.get("revoked_at") or 0.0),
                            int(rd.get("redeem_count") or 0),
                            float(rd.get("last_redeem_at") or 0.0),
                            extra_str,
                        ),
                    )
                c.execute("DROP TABLE invites")
                c.execute("ALTER TABLE invites_v3 RENAME TO invites")

            valid_jtis = {str(r[0]) for r in c.execute("SELECT jti FROM invites").fetchall()}

            if need_sessions_rebuild:
                c.execute(
                    """
                    CREATE TABLE sessions_v3 (
                        session_id TEXT PRIMARY KEY,
                        token_hash TEXT NOT NULL,
                        user_id TEXT REFERENCES users(user_id) ON DELETE CASCADE,
                        role_code TEXT NOT NULL REFERENCES roles(role_code),
                        tier INTEGER NOT NULL CHECK (tier IN (1, 2, 3, 4)),
                        source TEXT NOT NULL DEFAULT 'web',
                        invite_jti TEXT REFERENCES invites(jti) ON DELETE SET NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        revoked_at REAL
                    )
                    """
                )
                for r in c.execute("SELECT * FROM sessions").fetchall():
                    rd = dict(r)
                    sid = str(rd.get("session_id") or "").strip()
                    if not sid:
                        continue
                    uid = str(rd.get("user_id") or "").strip()
                    src = str(rd.get("source") or "web")
                    jti = str(rd.get("invite_jti") or "").strip()
                    tier = int(rd.get("tier") or 3)
                    if tier not in (1, 2, 3, 4):
                        tier = 3
                    rc = str(rd.get("role_code") or role_for_tier(tier))
                    if rc not in ("ADMIN", "MEMBER", "CHILD_GUEST", "UNKNOWN"):
                        rc = role_for_tier(tier)
                    if _is_guest_or_anon_user_id(uid, src, jti):
                        new_uid: str | None = None
                    else:
                        new_uid = uid
                        _ensure_preserve_user_for_fk(
                            c,
                            new_uid,
                            tier=tier if tier in (1, 2, 3) else 3,
                            role_code=rc if rc in ("ADMIN", "MEMBER", "CHILD_GUEST") else role_for_tier(tier),
                            display_name=str(rd.get("display_name") or new_uid),
                            email=str(rd.get("email") or ""),
                            active=False,
                        )
                    if not jti and src.startswith("guest_invite:"):
                        jti = src.split(":", 1)[1].strip()
                    new_jti: str | None = jti if (jti and jti in valid_jtis) else None
                    c.execute(
                        """
                        INSERT INTO sessions_v3 (
                            session_id, token_hash, user_id, role_code, tier, source,
                            invite_jti, created_at, expires_at, revoked_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            sid,
                            str(rd.get("token_hash") or hashlib.sha256(sid.encode("utf-8")).hexdigest()),
                            new_uid,
                            rc,
                            tier,
                            src,
                            new_jti,
                            float(rd.get("created_at") or 0.0),
                            float(rd.get("expires_at") or 0.0),
                            rd.get("revoked_at"),
                        ),
                    )
                c.execute("DROP TABLE sessions")
                c.execute("ALTER TABLE sessions_v3 RENAME TO sessions")

            if need_usess_rebuild:
                c.execute(
                    """
                    CREATE TABLE user_sessions_v3 (
                        session_id TEXT PRIMARY KEY,
                        user_id TEXT REFERENCES users(user_id) ON DELETE CASCADE,
                        tier INTEGER NOT NULL,
                        role TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        source TEXT
                    )
                    """
                )
                for r in c.execute("SELECT * FROM user_sessions").fetchall():
                    rd = dict(r)
                    sid = str(rd.get("session_id") or "").strip()
                    if not sid:
                        continue
                    uid = str(rd.get("user_id") or "").strip()
                    src = str(rd.get("source") or "web")
                    tier = int(rd.get("tier") or 3)
                    role_val = str(rd.get("role") or role_for_tier(tier))
                    if _is_guest_or_anon_user_id(uid, src, ""):
                        new_uid = None
                    else:
                        new_uid = uid
                        _ensure_preserve_user_for_fk(
                            c,
                            new_uid,
                            tier=tier if tier in (1, 2, 3) else 3,
                            role_code=role_for_tier(tier),
                            display_name=str(rd.get("display_name") or new_uid),
                            email=str(rd.get("email") or ""),
                            active=False,
                        )
                    c.execute(
                        """
                        INSERT INTO user_sessions_v3 (
                            session_id, user_id, tier, role, created_at, expires_at, source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            sid,
                            new_uid,
                            tier,
                            role_val,
                            float(rd.get("created_at") or 0.0),
                            float(rd.get("expires_at") or 0.0),
                            src,
                        ),
                    )
                c.execute("DROP TABLE user_sessions")
                c.execute("ALTER TABLE user_sessions_v3 RENAME TO user_sessions")

        run_write_transaction(conn, _rebuild_tx)
    finally:
        conn.execute("PRAGMA foreign_keys = ON;")


def apply_schema_migrations(conn: sqlite3.Connection) -> int:
    """Apply idempotent 3NF schema creation, column upgrades, role seeds, and hot indexes."""
    configure_wal_pragmas(conn, readonly=False)
    conn.executescript(_CORE_SCHEMA_SQL)

    # Upgrade legacy 8-table databases cleanly via additive ALTER TABLE
    _ensure_column(conn, "users", "email", "TEXT DEFAULT ''")
    _ensure_column(conn, "users", "role_code", "TEXT REFERENCES roles(role_code)")
    _ensure_column(conn, "users", "password_salt", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "users", "password_hash", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "users", "password_updated_at", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "users", "permission_active", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "users", "permission_status", "TEXT NOT NULL DEFAULT 'ACTIVE'")
    _ensure_column(conn, "users", "is_allowlisted", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "users", "is_active", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "users", "created_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "users", "account_meta_json", "TEXT NOT NULL DEFAULT '{}'")

    _ensure_column(conn, "devices", "min_role", "TEXT REFERENCES roles(role_code)")
    _ensure_column(conn, "devices", "room", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "devices", "device_type", "TEXT NOT NULL DEFAULT 'switch'")

    _migrate_schema_v3(conn)

    def _seed_and_migrate(c: sqlite3.Connection) -> int:
        for role_code, tier, name_vi, desc in DEFAULT_ROLES:
            c.execute(
                """
                INSERT INTO roles (role_code, tier, display_name_vi, description)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(role_code) DO UPDATE SET
                    tier = excluded.tier,
                    display_name_vi = excluded.display_name_vi,
                    description = excluded.description
                """,
                (role_code, tier, name_vi, desc),
            )

        # Backfill users.role_code and devices.min_role for legacy rows
        c.execute(
            """
            UPDATE users SET role_code = CASE
                WHEN tier = 1 THEN 'ADMIN'
                WHEN tier = 2 THEN 'MEMBER'
                ELSE 'CHILD_GUEST'
            END
            WHERE role_code IS NULL OR role_code = ''
            """
        )
        c.execute(
            """
            UPDATE devices SET min_role = CASE
                WHEN min_tier_required = 1 THEN 'ADMIN'
                WHEN min_tier_required = 2 THEN 'MEMBER'
                ELSE 'CHILD_GUEST'
            END
            WHERE min_role IS NULL OR min_role = ''
            """
        )

        # Ensure any active non-orphan rows from user_sessions exist in sessions (v3 columns)
        with contextlib.suppress(sqlite3.DatabaseError):
            c.execute(
                """
                INSERT OR IGNORE INTO sessions (
                    session_id, token_hash, user_id,
                    role_code, tier, source, invite_jti, created_at, expires_at, revoked_at
                )
                SELECT
                    us.session_id,
                    lower(hex(randomblob(16))),
                    CASE WHEN us.user_id IS NOT NULL AND EXISTS (SELECT 1 FROM users u WHERE u.user_id = us.user_id) THEN us.user_id ELSE NULL END,
                    CASE WHEN us.tier = 1 THEN 'ADMIN' WHEN us.tier = 2 THEN 'MEMBER' ELSE 'CHILD_GUEST' END,
                    CASE WHEN us.tier IN (1, 2, 3) THEN us.tier ELSE 3 END,
                    COALESCE(us.source, 'legacy'),
                    NULL,
                    us.created_at,
                    us.expires_at,
                    NULL
                FROM user_sessions us
                """
            )

        now_iso = _now_iso()
        migrations = (
            (1, "initial_8_table_schema"),
            (2, "normalized_3nf_wal_sessions_invites_otp_trusted_pin_ratelimit_state"),
            (3, "schema_v3_fk_hash_only_and_p1_automation"),
        )
        for ver, mname in migrations:
            c.execute(
                """
                INSERT OR IGNORE INTO schema_migrations (version, name, applied_at)
                VALUES (?, ?, ?)
                """,
                (ver, mname, now_iso),
            )
        row = c.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations").fetchone()
        return int(row["v"] if row else 3)

    version = run_write_transaction(conn, _seed_and_migrate)
    conn.executescript(_HOT_INDEXES_SQL)
    return version


def bootstrap_device_state_from_devices(conn: sqlite3.Connection, default_devices: dict[str, dict[str, Any]]) -> None:
    """Ensure every canonical device has rows in both devices and device_state and system_state_meta exists."""
    now_iso = _now_iso()
    import time as _time

    now_ts = _time.time()
    pin_map = {
        "main_door": "D1",
        "living_room_light": "D2",
        "ac": "D2",
        "garden_pump": "D3",
        "fan": "D6",
        "bedroom_light": "D7",
        "alarm_siren": "D8",
    }
    tier_map = {
        "main_door": 1,
        "alarm_siren": 1,
        "ac": 2,
        "garden_pump": 2,
        "living_room_light": 3,
        "bedroom_light": 3,
        "fan": 3,
    }
    for did, dinfo in default_devices.items():
        min_tier = tier_map.get(did, 3)
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
                pin_map.get(did, "GPIO"),
                str(dinfo.get("state") or "OFF"),
                min_tier,
                0 if did in ("main_door", "alarm_siren") else 1,
                now_iso,
                role_for_tier(min_tier),
                str(dinfo.get("room") or "home"),
                str(dinfo.get("type") or "switch"),
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO device_state (
                device_id, state, version, updated_at
            ) VALUES (?, ?, 1, ?)
            """,
            (did, str(dinfo.get("state") or "OFF"), now_ts),
        )
    conn.execute(
        """
        INSERT OR IGNORE INTO system_state_meta (
            id, revision_seq, revision_ts_ns, server_connected, pump_manual_override_off, updated_at
        ) VALUES (1, 0, 0, 1, 0, ?)
        """,
        (now_ts,),
    )


def table_row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Return exact row counts for all application tables in sqlite_master."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    counts: dict[str, int] = {}
    for r in rows:
        tname = str(r["name"])
        counts[tname] = int(conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0])
    return counts


def dump_meta_json(conn: sqlite3.Connection, key: str, value: Any) -> None:
    import time as _time

    payload = json.dumps(value, ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO system_kv_meta (meta_key, meta_value_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(meta_key) DO UPDATE SET
            meta_value_json = excluded.meta_value_json,
            updated_at = excluded.updated_at
        """,
        (key, payload, _time.time()),
    )
