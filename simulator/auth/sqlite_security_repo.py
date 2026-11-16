"""Normalized SQLite WAL persistence helpers for PIN, invites, accounts, rate limits, OTP, and trusted devices."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import pathlib
import sqlite3
import sys
import threading
import time
from typing import Any

from simulator.database_sqlite import init_sqlite_database
from simulator.db_migrations import open_wal_connection, role_for_tier, run_write_transaction

_ACCOUNTS_CACHE_LOCK = threading.RLock()
_ACCOUNTS_CACHE_EPOCH = 0
_ACCOUNTS_SQLITE_CACHE: dict[str, tuple[int, float, bytes | None]] = {}
_ACCOUNTS_CACHE_TTL_SEC = 1.0


def _accounts_cache_allowed() -> bool:
    return not ("pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"))


def invalidate_accounts_sqlite_cache() -> None:
    global _ACCOUNTS_CACHE_EPOCH
    with _ACCOUNTS_CACHE_LOCK:
        _ACCOUNTS_CACHE_EPOCH += 1
        _ACCOUNTS_SQLITE_CACHE.clear()


def _conn_for_data_dir(data_dir: pathlib.Path | None, *, readonly: bool = False) -> sqlite3.Connection:
    target = init_sqlite_database((pathlib.Path(data_dir) / "smarthome.db") if data_dir else None)
    use_ro = bool(readonly and target.exists())
    return open_wal_connection(target, readonly=use_ro)


def _hash_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _sec_rev_key(doc_name: str) -> str:
    return f"sec_rev:{pathlib.Path(doc_name).name}"


def _get_sec_revision_in_tx(c: sqlite3.Connection, doc_name: str) -> int:
    row = c.execute(
        "SELECT meta_value_json FROM system_kv_meta WHERE meta_key = ?",
        (_sec_rev_key(doc_name),),
    ).fetchone()
    if row is None:
        return 0
    try:
        obj = json.loads(str(row["meta_value_json"] or "{}"))
        return int((obj or {}).get("rev") or 0)
    except Exception:
        return 0


def _bump_sec_revision_in_tx(
    c: sqlite3.Connection,
    doc_name: str,
    now_ts: float | None = None,
) -> int:
    new_rev = _get_sec_revision_in_tx(c, doc_name) + 1
    ts = float(now_ts if now_ts is not None else time.time())
    c.execute(
        """
        INSERT INTO system_kv_meta (meta_key, meta_value_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(meta_key) DO UPDATE SET
            meta_value_json = excluded.meta_value_json,
            updated_at = excluded.updated_at
        """,
        (_sec_rev_key(doc_name), json.dumps({"rev": new_rev}, separators=(",", ":")), ts),
    )
    return new_rev


def _derive_otp_challenge_id(email: str, p_otp: dict[str, Any]) -> str:
    explicit = str(p_otp.get("challenge_id") or "").strip()
    if explicit:
        return explicit
    purpose = str(p_otp.get("purpose") or "layer2_login").strip() or "layer2_login"
    salt = str(p_otp.get("otp_salt") or "").strip()
    digest = str(p_otp.get("otp_hash") or p_otp.get("otp_code") or "").strip()
    created = str(p_otp.get("created_at") or "").strip()
    raw = f"{email.strip().lower()}|{purpose}|{salt}|{digest}|{created}"
    return "otp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:28]


def _otp_challenge_in_tx(c: sqlite3.Connection, email: str, pending: dict[str, Any]) -> sqlite3.Row | None:
    if not pending.get("challenge_id"):
        c.execute(
            """
            INSERT OR IGNORE INTO otp_challenges (
                challenge_id, email, purpose, otp_salt, otp_hash,
                issued_at, expires_at, used, failed_attempts, meta_json
            ) SELECT ?, email, ?, otp_salt, otp_hash,
                     issued_at, expires_at, used, failed_attempts, meta_json
              FROM otp_challenges
              WHERE challenge_id = ? AND otp_hash = ? AND otp_salt = ?
            """,
            (
                _derive_otp_challenge_id(email, pending),
                str(pending.get("purpose") or "layer2_login"),
                f"login_{email}",
                str(pending.get("otp_hash") or ""),
                str(pending.get("otp_salt") or ""),
            ),
        )
    return c.execute(
        """
        SELECT used, failed_attempts FROM otp_challenges
        WHERE challenge_id = ? OR (
            ? AND challenge_id = ? AND otp_hash = ? AND otp_salt = ?
        )
        ORDER BY used DESC LIMIT 1
        """,
        (
            _derive_otp_challenge_id(email, pending),
            not bool(pending.get("challenge_id")),
            f"login_{email}",
            str(pending.get("otp_hash") or ""),
            str(pending.get("otp_salt") or ""),
        ),
    ).fetchone()


def _read_owner_pin_from_conn(conn: sqlite3.Connection) -> bytes | None:
    row = conn.execute("SELECT * FROM owner_pin_security WHERE id = 1").fetchone()
    if not row or (
        not row["pin_hash"]
        and not row["otp_hash"]
        and int(row["failed_attempts"] or 0) == 0
        and not row["locked"]
    ):
        return None
    doc = {
        "pin_salt": str(row["pin_salt"] or ""),
        "pin_hash": str(row["pin_hash"] or ""),
        "failed_attempts": int(row["failed_attempts"] or 0),
        "locked": bool(row["locked"]),
        "otp_salt": str(row["otp_salt"] or ""),
        "otp_hash": str(row["otp_hash"] or ""),
        "otp_expires_at": float(row["otp_expires_at"] or 0.0),
        "otp_used": bool(row["otp_used"]),
        "otp_failed_attempts": int(row["otp_failed_attempts"] or 0),
        "otp_issued_at": float(row["otp_issued_at"] or 0.0),
        "updated_at": float(row["updated_at"] or 0.0),
        "revision": int(row["revision"] or 0),
    }
    return json.dumps(doc, ensure_ascii=False).encode("utf-8")


def _save_owner_pin_in_tx(c: sqlite3.Connection, payload: bytes) -> None:
    doc = json.loads(payload.decode("utf-8")) if payload else {}
    if not isinstance(doc, dict):
        doc = {}
    if "revision" in doc:
        existing_revision = c.execute("SELECT revision FROM owner_pin_security WHERE id = 1").fetchone()
        if existing_revision is not None and int(existing_revision["revision"]) != int(doc["revision"]):
            from simulator.auth.security_state import StateConflict

            raise StateConflict("Owner PIN state changed; reload before saving")
    if not doc:
        c.execute(
            """
            INSERT INTO owner_pin_security (
                id, pin_salt, pin_hash, failed_attempts, locked,
                otp_salt, otp_hash, otp_expires_at, otp_used, otp_failed_attempts, otp_issued_at,
                revision, updated_at
            ) VALUES (1, '', '', 0, 0, '', '', 0.0, 0, 0, 0.0, 1, ?)
            ON CONFLICT(id) DO UPDATE SET
                pin_salt = '',
                pin_hash = '',
                failed_attempts = 0,
                locked = 0,
                otp_salt = '',
                otp_hash = '',
                otp_expires_at = 0.0,
                otp_used = 0,
                otp_failed_attempts = 0,
                otp_issued_at = 0.0,
                revision = owner_pin_security.revision + 1,
                updated_at = excluded.updated_at
            """,
            (time.time(),),
        )
        _bump_sec_revision_in_tx(c, "owner_pin.json")
        return
    in_otp_hash = str(doc.get("otp_hash") or "")
    in_otp_used = 1 if doc.get("otp_used") else 0
    existing = c.execute("SELECT otp_hash, otp_used FROM owner_pin_security WHERE id = 1").fetchone()
    if existing is not None and in_otp_hash and str(existing["otp_hash"] or "") == in_otp_hash:
        if int(existing["otp_used"] or 0) != 0:
            in_otp_used = 1
    now_ts = float(doc.get("updated_at") or time.time())
    c.execute(
        """
        INSERT INTO owner_pin_security (
            id, pin_salt, pin_hash, failed_attempts, locked,
            otp_salt, otp_hash, otp_expires_at, otp_used, otp_failed_attempts, otp_issued_at,
            revision, updated_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(id) DO UPDATE SET
            pin_salt = excluded.pin_salt,
            pin_hash = excluded.pin_hash,
            failed_attempts = excluded.failed_attempts,
            locked = excluded.locked,
            otp_salt = excluded.otp_salt,
            otp_hash = excluded.otp_hash,
            otp_expires_at = excluded.otp_expires_at,
            otp_used = excluded.otp_used,
            otp_failed_attempts = excluded.otp_failed_attempts,
            otp_issued_at = excluded.otp_issued_at,
            revision = owner_pin_security.revision + 1,
            updated_at = excluded.updated_at
        """,
        (
            str(doc.get("pin_salt") or ""),
            str(doc.get("pin_hash") or ""),
            int(doc.get("failed_attempts") or 0),
            1 if doc.get("locked") else 0,
            str(doc.get("otp_salt") or ""),
            in_otp_hash,
            float(doc.get("otp_expires_at") or 0.0),
            in_otp_used,
            int(doc.get("otp_failed_attempts") or 0),
            float(doc.get("otp_issued_at") or 0.0),
            now_ts,
        ),
    )
    _bump_sec_revision_in_tx(c, "owner_pin.json", now_ts)


def load_owner_pin_sqlite(data_dir: pathlib.Path | None) -> bytes | None:
    conn = _conn_for_data_dir(data_dir, readonly=True)
    try:
        return _read_owner_pin_from_conn(conn)
    finally:
        conn.close()


def save_owner_pin_sqlite(payload: bytes, data_dir: pathlib.Path | None) -> None:
    conn = _conn_for_data_dir(data_dir)
    try:
        run_write_transaction(conn, lambda c: _save_owner_pin_in_tx(c, payload))
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()

def _read_invites_from_conn(conn: sqlite3.Connection) -> bytes | None:
    rows = conn.execute(
        """
        SELECT jti, token_hash, owner_user_id, role_code, tier, label,
               created_at, expires_at, revoked, revoked_at, redeem_count, last_redeem_at, extra_json
        FROM invites
        ORDER BY created_at DESC
        """
    ).fetchall()
    if not rows:
        return None
    items = []
    for r in rows:
        try:
            extra = json.loads(str(r["extra_json"] or "{}"))
        except Exception:
            extra = {}
        rec = {
            **(extra if isinstance(extra, dict) else {}),
            "jti": str(r["jti"]),
            "token_hash": str(r["token_hash"]),
            "tier": int(r["tier"]),
            "role": str(r["role_code"]),
            "created_at": float(r["created_at"]),
            "expires_at": float(r["expires_at"]),
            "revoked": bool(r["revoked"]),
            "revoked_at": float(r["revoked_at"] or 0.0),
            "owner_user_id": str(r["owner_user_id"]),
            "redeem_count": int(r["redeem_count"] or 0),
        }
        rec.pop("token", None)
        if float(r["last_redeem_at"] or 0.0) > 0:
            rec["last_redeem_at"] = float(r["last_redeem_at"])
        items.append(rec)
    return json.dumps({"invites": items}, ensure_ascii=False).encode("utf-8")


def _save_invites_in_tx(c: sqlite3.Connection, payload: bytes) -> None:
    from simulator.db_migrations import _ensure_preserve_user_for_fk

    parsed = json.loads(payload.decode("utf-8")) if payload else {}
    raw_items = parsed.get("invites") if isinstance(parsed, dict) else parsed
    items = raw_items if isinstance(raw_items, list) else (list(raw_items.values()) if isinstance(raw_items, dict) else [])
    known = {
        "jti",
        "token",
        "token_hash",
        "tier",
        "role",
        "created_at",
        "expires_at",
        "revoked",
        "revoked_at",
        "owner_user_id",
        "redeem_count",
        "last_redeem_at",
        "label",
    }
    if isinstance(raw_items, list) and len(raw_items) == 0:
        c.execute("DELETE FROM invites")
        _bump_sec_revision_in_tx(c, "guest_invites.json")
        return

    for item in items:
        if not isinstance(item, dict) or not item.get("jti"):
            continue
        jti = str(item["jti"])
        tier = int(item.get("tier") or 3)
        if tier not in (2, 3):
            tier = 3
        role_code = role_for_tier(tier)
        owner_uid = str(item.get("owner_user_id") or "tuan_anh").strip() or "tuan_anh"
        _ensure_preserve_user_for_fk(
            c, owner_uid, tier=1, role_code="ADMIN", display_name=owner_uid, active=False
        )
        raw_token = str(item.get("token") or "").strip()
        existing_hash = str(item.get("token_hash") or "").strip()
        tok_hash = existing_hash or (_hash_token(raw_token) if raw_token else _hash_token(jti))
        extra = {k: v for k, v in item.items() if k not in known}
        c.execute(
            """
            INSERT INTO invites (
                jti, token_hash, owner_user_id, role_code, tier, label,
                created_at, expires_at, revoked, revoked_at, redeem_count, last_redeem_at, extra_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(jti) DO UPDATE SET
                token_hash = excluded.token_hash,
                owner_user_id = excluded.owner_user_id,
                role_code = excluded.role_code,
                tier = excluded.tier,
                label = excluded.label,
                expires_at = excluded.expires_at,
                revoked = MAX(invites.revoked, excluded.revoked),
                revoked_at = CASE WHEN invites.revoked != 0 THEN invites.revoked_at ELSE excluded.revoked_at END,
                redeem_count = MAX(invites.redeem_count, excluded.redeem_count),
                last_redeem_at = MAX(invites.last_redeem_at, excluded.last_redeem_at),
                extra_json = excluded.extra_json
            """,
            (
                jti,
                tok_hash,
                owner_uid,
                role_code,
                tier,
                str(item.get("label") or ""),
                float(item.get("created_at") or time.time()),
                float(item.get("expires_at") or time.time()),
                1 if item.get("revoked") else 0,
                float(item.get("revoked_at") or 0.0),
                int(item.get("redeem_count") or 0),
                float(item.get("last_redeem_at") or 0.0),
                json.dumps(extra, ensure_ascii=False),
            ),
        )
    _bump_sec_revision_in_tx(c, "guest_invites.json")


def load_invites_sqlite(data_dir: pathlib.Path | None) -> bytes | None:
    conn = _conn_for_data_dir(data_dir, readonly=True)
    try:
        return _read_invites_from_conn(conn)
    finally:
        conn.close()


def save_invites_sqlite(payload: bytes, data_dir: pathlib.Path | None) -> None:
    conn = _conn_for_data_dir(data_dir)
    try:
        run_write_transaction(conn, lambda c: _save_invites_in_tx(c, payload))
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()

def _read_rate_limits_from_conn(conn: sqlite3.Connection) -> bytes | None:
    rows = conn.execute("SELECT * FROM login_rate_limits").fetchall()
    if not rows:
        return None
    buckets: dict[str, Any] = {}
    latest_ts = 0.0
    for r in rows:
        try:
            raw_obj = json.loads(str(r["attempts_json"] or "{}"))
        except Exception:
            raw_obj = {}
        scope = str(r["scope_key"])
        if isinstance(raw_obj, dict) and raw_obj:
            buckets[scope] = raw_obj
        else:
            buckets[scope] = {
                "attempts": raw_obj if isinstance(raw_obj, list) else [],
                "locked_until": float(r["locked_until"] or 0.0),
            }
        latest_ts = max(latest_ts, float(r["updated_at"] or 0.0))
    return json.dumps({"buckets": buckets, "updated_at": latest_ts}, ensure_ascii=False).encode("utf-8")


def _save_rate_limits_in_tx(c: sqlite3.Connection, payload: bytes) -> None:
    parsed = json.loads(payload.decode("utf-8")) if payload else {}
    buckets = parsed.get("buckets") if isinstance(parsed, dict) else {}
    if not isinstance(buckets, dict):
        buckets = {}
    now = time.time()
    keys = [str(k) for k in buckets.keys()]
    for k, val in buckets.items():
        locked_until = float(val.get("locked_until") or 0.0) if isinstance(val, dict) else 0.0
        c.execute(
            """
            INSERT INTO login_rate_limits (scope_key, attempts_json, locked_until, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(scope_key) DO UPDATE SET
                attempts_json = excluded.attempts_json,
                locked_until = excluded.locked_until,
                updated_at = excluded.updated_at
            """,
            (str(k), json.dumps(val, ensure_ascii=False), locked_until, now),
        )
    if keys:
        placeholders = ",".join("?" for _ in keys)
        c.execute(f"DELETE FROM login_rate_limits WHERE scope_key NOT IN ({placeholders})", keys)
    else:
        c.execute("DELETE FROM login_rate_limits")
    _bump_sec_revision_in_tx(c, "login_rate_limit.json", now)


def load_rate_limits_sqlite(data_dir: pathlib.Path | None) -> bytes | None:
    conn = _conn_for_data_dir(data_dir, readonly=True)
    try:
        return _read_rate_limits_from_conn(conn)
    finally:
        conn.close()


def save_rate_limits_sqlite(payload: bytes, data_dir: pathlib.Path | None) -> None:
    conn = _conn_for_data_dir(data_dir)
    try:
        run_write_transaction(conn, lambda c: _save_rate_limits_in_tx(c, payload))
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()

def _read_accounts_from_conn(conn: sqlite3.Connection) -> bytes | None:
    rows = conn.execute(
        "SELECT * FROM users WHERE account_meta_json != '{}' AND account_meta_json != '' ORDER BY tier ASC, user_id ASC"
    ).fetchall()
    if not rows:
        return None
    accounts: list[dict[str, Any]] = []
    for r in rows:
        try:
            meta = json.loads(str(r["account_meta_json"] or "{}"))
        except Exception:
            meta = {}
        if not isinstance(meta, dict) or not meta:
            continue
        if r["password_hash"] and not meta.get("password_hash"):
            meta["password_hash"] = str(r["password_hash"])
        if r["password_salt"] and not meta.get("password_salt"):
            meta["password_salt"] = str(r["password_salt"])
        accounts.append(meta)
    if not accounts:
        return None
    return json.dumps({"accounts": accounts, "updated_at": time.time()}, ensure_ascii=False).encode("utf-8")


def load_accounts_sqlite(data_dir: pathlib.Path | None) -> bytes | None:
    cache_key = str((pathlib.Path(data_dir) / "smarthome.db").resolve()) if data_dir else "__default__"
    if _accounts_cache_allowed():
        with _ACCOUNTS_CACHE_LOCK:
            cached = _ACCOUNTS_SQLITE_CACHE.get(cache_key)
            if cached is not None:
                ep, ts_mono, payload = cached
                if ep == _ACCOUNTS_CACHE_EPOCH and (time.monotonic() - ts_mono) < _ACCOUNTS_CACHE_TTL_SEC:
                    return payload
    ep_before = _ACCOUNTS_CACHE_EPOCH
    conn = _conn_for_data_dir(data_dir, readonly=True)
    result: bytes | None = None
    try:
        result = _read_accounts_from_conn(conn)
    finally:
        conn.close()
    if _accounts_cache_allowed():
        with _ACCOUNTS_CACHE_LOCK:
            if ep_before == _ACCOUNTS_CACHE_EPOCH:
                _ACCOUNTS_SQLITE_CACHE[cache_key] = (_ACCOUNTS_CACHE_EPOCH, time.monotonic(), result)
    return result


def _save_accounts_in_tx(c: sqlite3.Connection, payload: bytes) -> None:
    import datetime as _dt

    parsed = json.loads(payload.decode("utf-8")) if payload else {}
    accounts = parsed.get("accounts") if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
    if not isinstance(accounts, list):
        return
    deleted_ids = (
        [str(x).strip() for x in (parsed.get("deleted_account_ids") or []) if str(x).strip()]
        if isinstance(parsed, dict)
        else []
    )
    cleared_otp_emails = (
        {str(x).strip().lower() for x in (parsed.get("cleared_otp_emails") or []) if str(x).strip()}
        if isinstance(parsed, dict)
        else set()
    )
    clear_all_otps = bool(parsed.get("clear_all_otps")) if isinstance(parsed, dict) else False
    factory_reset = bool(parsed.get("factory_reset")) if isinstance(parsed, dict) else False

    tz = _dt.timezone(_dt.timedelta(hours=7))
    now_iso = _dt.datetime.now(tz).isoformat()
    now_ts = time.time()

    if factory_reset:
        keep_uids = [
            str(a.get("account_id") or a.get("user_id") or a.get("id") or "").strip()
            for a in accounts
            if isinstance(a, dict)
        ]
        keep_uids = [u for u in keep_uids if u]
        if keep_uids:
            placeholders = ",".join("?" for _ in keep_uids)
            c.execute(
                f"DELETE FROM users WHERE tier != 1 AND user_id NOT IN ({placeholders})",
                tuple(keep_uids),
            )
        else:
            c.execute("DELETE FROM users WHERE tier != 1")

    for del_uid in deleted_ids:
        c.execute(
            "DELETE FROM users WHERE user_id = ? AND tier != 1 AND permission_active = 0",
            (del_uid,),
        )
    if clear_all_otps:
        c.execute("UPDATE otp_challenges SET used = 1 WHERE used = 0")

    for acc in accounts:
        if not isinstance(acc, dict):
            continue
        acc_copy = json.loads(json.dumps(acc, ensure_ascii=False))
        uid = str(acc_copy.get("account_id") or acc_copy.get("user_id") or acc_copy.get("id") or "").strip()
        if not uid:
            continue
        tier = int(acc_copy.get("tier") or 3)
        if tier not in (1, 2, 3):
            tier = 3
        rc = role_for_tier(tier)
        email = str(acc_copy.get("email") or "").strip().lower()
        pw_hash = str(acc_copy.get("password_hash") or "")
        pw_salt = str(acc_copy.get("password_salt") or "")
        pw_ts = float(acc_copy.get("password_updated_at") or now_ts)

        existing_row = c.execute(
            "SELECT password_salt, password_hash, password_updated_at, account_meta_json FROM users WHERE user_id = ?",
            (uid,),
        ).fetchone()
        existing_meta: dict[str, Any] = {}
        if existing_row is not None:
            try:
                parsed_meta = json.loads(str(existing_row["account_meta_json"] or "{}"))
                if isinstance(parsed_meta, dict):
                    existing_meta = parsed_meta
            except Exception:
                existing_meta = {}
            ex_pw_ts = float(existing_row["password_updated_at"] or 0.0)
            inc_pw_ts = float(acc_copy.get("password_updated_at") or 0.0)
            if existing_row["password_hash"] and ex_pw_ts > inc_pw_ts > 0.0:
                pw_hash = str(existing_row["password_hash"])
                pw_salt = str(existing_row["password_salt"] or "")
                pw_ts = ex_pw_ts
                acc_copy["password_hash"] = pw_hash
                if pw_salt:
                    acc_copy["password_salt"] = pw_salt
                acc_copy["password_updated_at"] = pw_ts

        db_otp_active: dict[str, Any] | None = None
        if email and isinstance(existing_meta.get("pending_otp"), dict):
            cand_db_otp = existing_meta["pending_otp"]
            if (cand_db_otp.get("otp_hash") or cand_db_otp.get("otp_code")) and not cand_db_otp.get("consumed") and not cand_db_otp.get("used"):
                db_chal_id = _derive_otp_challenge_id(email, cand_db_otp)
                db_ch_row = _otp_challenge_in_tx(c, email, cand_db_otp)
                if db_ch_row is None or int(db_ch_row["used"] or 0) == 0:
                    db_otp_active = dict(cand_db_otp)
                    db_otp_active["challenge_id"] = db_chal_id

        p_otp = acc_copy.get("pending_otp")
        if email and isinstance(p_otp, dict) and (p_otp.get("otp_hash") or p_otp.get("otp_code")):
            chal_id = _derive_otp_challenge_id(email, p_otp)
            otp_purpose = str(p_otp.get("purpose") or "layer2_login").strip() or "layer2_login"
            ch_row = _otp_challenge_in_tx(c, email, p_otp)
            incoming_used = bool(
                p_otp.get("consumed")
                or p_otp.get("used")
                or (ch_row is not None and int(ch_row["used"] or 0) != 0)
            )
            if incoming_used:
                if ch_row is not None and int(ch_row["used"] or 0) == 0:
                    c.execute("UPDATE otp_challenges SET used = 1 WHERE challenge_id = ?", (chal_id,))
                if db_otp_active is not None and db_otp_active.get("challenge_id") != chal_id:
                    acc_copy["pending_otp"] = db_otp_active
                else:
                    acc_copy.pop("pending_otp", None)
                    acc_copy.pop("otp_cooldown_started_at", None)
            else:
                if (
                    db_otp_active is not None
                    and db_otp_active.get("challenge_id") != chal_id
                    and float(db_otp_active.get("created_at") or 0.0) > float(p_otp.get("created_at") or 0.0)
                ):
                    acc_copy["pending_otp"] = db_otp_active
                    p_otp = db_otp_active
                    chal_id = str(db_otp_active["challenge_id"])
                    otp_purpose = str(p_otp.get("purpose") or "layer2_login").strip() or "layer2_login"
                else:
                    p_otp = dict(p_otp)
                    p_otp["challenge_id"] = chal_id
                    acc_copy["pending_otp"] = p_otp
                issued_ts = float(p_otp.get("created_at") or now_ts)
                c.execute(
                    """
                    INSERT INTO otp_challenges (
                        challenge_id, email, purpose, otp_salt, otp_hash,
                        issued_at, expires_at, used, failed_attempts, meta_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    ON CONFLICT(challenge_id) DO UPDATE SET
                        otp_salt = excluded.otp_salt,
                        otp_hash = excluded.otp_hash,
                        issued_at = excluded.issued_at,
                        expires_at = excluded.expires_at,
                        used = MAX(otp_challenges.used, excluded.used),
                        failed_attempts = MAX(otp_challenges.failed_attempts, excluded.failed_attempts),
                        meta_json = excluded.meta_json
                    """,
                    (
                        chal_id,
                        email,
                        otp_purpose,
                        str(p_otp.get("otp_salt") or ""),
                        str(p_otp.get("otp_hash") or ""),
                        issued_ts,
                        float(p_otp.get("expires_at") or now_ts + 300.0),
                        int(len(acc_copy.get("otp_failed_verify_attempts") or [])),
                        json.dumps({"account_id": uid}, ensure_ascii=False),
                    ),
                )
                if ch_row is None:
                    c.execute(
                        """
                        UPDATE otp_challenges
                        SET used = 1
                        WHERE lower(email) = ? AND challenge_id != ? AND issued_at <= ? AND used = 0
                        """,
                        (email, chal_id, issued_ts),
                    )
        elif email:
            if clear_all_otps or (email in cleared_otp_emails):
                c.execute(
                    "UPDATE otp_challenges SET used = 1 WHERE lower(email) = ? AND used = 0",
                    (email,),
                )
            elif db_otp_active is not None:
                acc_copy["pending_otp"] = db_otp_active

        c.execute(
            """
            INSERT INTO users (
                user_id, full_name, role, tier, offline_allowed, created_by, updated_at,
                email, role_code, password_salt, password_hash, password_updated_at,
                permission_active, permission_status, is_allowlisted, is_active, created_at, account_meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name = excluded.full_name,
                role = excluded.role,
                tier = excluded.tier,
                offline_allowed = excluded.offline_allowed,
                updated_at = excluded.updated_at,
                email = excluded.email,
                role_code = excluded.role_code,
                password_salt = excluded.password_salt,
                password_hash = excluded.password_hash,
                password_updated_at = excluded.password_updated_at,
                permission_active = excluded.permission_active,
                permission_status = excluded.permission_status,
                account_meta_json = excluded.account_meta_json
            """,
            (
                uid,
                str(acc_copy.get("display_name") or acc_copy.get("full_name") or uid),
                rc,
                tier,
                1 if tier in (1, 2) else 0,
                str(acc_copy.get("invited_by") or "SYSTEM"),
                now_iso,
                email,
                rc,
                pw_salt,
                pw_hash,
                pw_ts,
                1 if acc_copy.get("permission_active", True) else 0,
                str(
                    acc_copy.get("permission_status")
                    or ("ACTIVE" if acc_copy.get("permission_active", True) else "REVOKED")
                ),
                str(acc_copy.get("created_at") or now_iso),
                json.dumps(acc_copy, ensure_ascii=False),
            ),
        )
    _bump_sec_revision_in_tx(c, "auth3_accounts_state.json", now_ts)


def save_accounts_sqlite(payload: bytes, data_dir: pathlib.Path | None) -> None:
    conn = _conn_for_data_dir(data_dir)
    try:
        run_write_transaction(conn, lambda c: _save_accounts_in_tx(c, payload))
        if data_dir is not None:
            updated_bytes = _read_accounts_from_conn(conn)
            if updated_bytes:
                try:
                    doc = json.loads(updated_bytes.decode("utf-8"))
                    accounts = doc.get("accounts", [])
                    local_target = pathlib.Path(data_dir) / "accounts_3layer.json"
                    local_payload = (json.dumps(accounts, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                    tmp_target = local_target.with_suffix(".tmp")
                    tmp_target.write_bytes(local_payload)
                    tmp_target.replace(local_target)
                except Exception:
                    pass
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()


def read_security_state_with_revision_sqlite(
    doc_name: str,
    data_dir: pathlib.Path | None,
) -> tuple[bytes | None, int]:
    """Read security document payload and its monotonic SQLite revision inside one snapshot."""
    fname = pathlib.Path(doc_name).name
    conn = _conn_for_data_dir(data_dir, readonly=True)
    try:
        conn.execute("BEGIN")
        rev = _get_sec_revision_in_tx(conn, fname)
        if fname == "owner_pin.json":
            payload = _read_owner_pin_from_conn(conn)
        elif fname == "guest_invites.json":
            payload = _read_invites_from_conn(conn)
        elif fname == "auth3_accounts_state.json":
            payload = _read_accounts_from_conn(conn)
        elif fname == "login_rate_limit.json":
            payload = _read_rate_limits_from_conn(conn)
        else:
            payload = None
        return payload, rev
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()


def cas_save_security_state_sqlite(
    doc_name: str,
    payload: bytes,
    *,
    expected_revision: int | None,
    data_dir: pathlib.Path | None,
) -> int:
    """Atomically verify revision and apply per-record safe save inside SQLite BEGIN IMMEDIATE."""
    from simulator.auth.security_state import StateConflict

    fname = pathlib.Path(doc_name).name
    conn = _conn_for_data_dir(data_dir)
    new_rev = 0
    try:
        def _tx(c: sqlite3.Connection) -> None:
            nonlocal new_rev
            if expected_revision is not None:
                cur_rev = _get_sec_revision_in_tx(c, fname)
                if cur_rev != int(expected_revision):
                    raise StateConflict(f"{fname} revision changed: {cur_rev} != {expected_revision}")
            if fname == "owner_pin.json":
                _save_owner_pin_in_tx(c, payload)
            elif fname == "guest_invites.json":
                _save_invites_in_tx(c, payload)
            elif fname == "auth3_accounts_state.json":
                _save_accounts_in_tx(c, payload)
            elif fname == "login_rate_limit.json":
                _save_rate_limits_in_tx(c, payload)
            new_rev = _get_sec_revision_in_tx(c, fname)

        run_write_transaction(conn, _tx)
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()
    return new_rev

def record_trusted_device_sqlite(
    token: str,
    account_id: str,
    email: str,
    user_agent: str,
    created_at: float,
    expires_at: float,
    data_dir: pathlib.Path | None = None,
) -> None:
    conn = _conn_for_data_dir(data_dir)
    try:
        tok_hash = _hash_token(token)
        ua_hash = hashlib.sha256(str(user_agent or "").encode("utf-8")).hexdigest()[:32]

        def _tx(c: sqlite3.Connection) -> None:
            c.execute(
                """
                INSERT INTO trusted_devices (
                    device_token_hash, account_id, email, user_agent_hash, label,
                    created_at, expires_at, last_used_at, revoked
                ) VALUES (?, ?, ?, ?, 'web_browser', ?, ?, ?, 0)
                ON CONFLICT(device_token_hash) DO UPDATE SET
                    expires_at = excluded.expires_at,
                    last_used_at = excluded.last_used_at,
                    revoked = 0
                """,
                (tok_hash, account_id, email.lower().strip(), ua_hash, created_at, expires_at, created_at),
            )

        run_write_transaction(conn, _tx)
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()

def is_trusted_device_revoked_sqlite(token: str, data_dir: pathlib.Path | None = None) -> bool:
    conn = _conn_for_data_dir(data_dir, readonly=True)
    try:
        row = conn.execute(
            "SELECT revoked, expires_at FROM trusted_devices WHERE device_token_hash = ?",
            (_hash_token(token),),
        ).fetchone()
        if row is None:
            return False
        if int(row["revoked"] or 0) != 0:
            return True
        return float(row["expires_at"] or 0.0) <= time.time()
    finally:
        conn.close()


def revoke_trusted_device_sqlite(token: str, data_dir: pathlib.Path | None = None) -> None:
    if not token:
        return
    conn = _conn_for_data_dir(data_dir)
    try:
        run_write_transaction(
            conn,
            lambda c: c.execute(
                "UPDATE trusted_devices SET revoked = 1 WHERE device_token_hash = ?",
                (_hash_token(token),),
            ),
        )
    finally:
        conn.close()


def claim_invite_sqlite(
    *,
    jti: str,
    exp: float,
    now: float,
    data_dir: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Atomically claim a single-use guest invite inside SQLite BEGIN IMMEDIATE."""
    conn = _conn_for_data_dir(data_dir)
    out: dict[str, Any] = {}
    try:
        def _tx(c: sqlite3.Connection) -> None:
            nonlocal out
            row = c.execute(
                """
                SELECT jti, token_hash, owner_user_id, role_code, tier, label,
                       created_at, expires_at, revoked, revoked_at, redeem_count, last_redeem_at, extra_json
                FROM invites WHERE jti = ?
                """,
                (jti,),
            ).fetchone()
            if row is None:
                out = {"ok": False, "valid": False, "reason": "unknown", "error": "Mã mời không tồn tại hoặc đã hết hạn."}
                return
            if bool(row["revoked"]):
                out = {"ok": False, "valid": False, "reason": "revoked", "invite_id": jti, "error": "Mã mời đã bị thu hồi."}
                return
            expires_at = float(row["expires_at"] or exp)
            if expires_at <= now or exp <= now:
                out = {
                    "ok": False,
                    "valid": False,
                    "reason": "expired",
                    "invite_id": jti,
                    "expires_at": expires_at,
                    "error": "Mã mời đã hết hạn.",
                }
                return
            if int(row["redeem_count"] or 0) >= 1:
                out = {
                    "ok": False,
                    "valid": False,
                    "reason": "used",
                    "invite_id": jti,
                    "expires_at": expires_at,
                    "error": "Mã QR đã được sử dụng.",
                }
                return
            cur = c.execute(
                """
                UPDATE invites
                SET redeem_count = redeem_count + 1, last_redeem_at = ?
                WHERE jti = ? AND revoked = 0 AND redeem_count = 0 AND expires_at > ?
                """,
                (now, jti, now),
            )
            if cur.rowcount != 1:
                out = {
                    "ok": False,
                    "valid": False,
                    "reason": "used",
                    "invite_id": jti,
                    "expires_at": expires_at,
                    "error": "Mã QR đã được sử dụng.",
                }
                return
            _bump_sec_revision_in_tx(c, "guest_invites.json", now)
            try:
                extra = json.loads(str(row["extra_json"] or "{}"))
            except Exception:
                extra = {}
            extra_d = extra if isinstance(extra, dict) else {}
            out = {
                "ok": True,
                "valid": True,
                "reason": "ok",
                "invite_id": jti,
                "tier": int(row["tier"] or 3),
                "role": str(row["role_code"] or "CHILD_GUEST"),
                "created_at": float(row["created_at"] or now),
                "expires_at": expires_at,
                "duration_code": str(extra_d.get("duration_code") or "").strip(),
                "duration_label": str(extra_d.get("duration_label") or "").strip(),
                "duration_seconds": int(extra_d.get("duration_seconds") or extra_d.get("ttl_sec") or 0),
                "guest_name": str(extra_d.get("guest_name") or "").strip(),
            }

        run_write_transaction(conn, _tx)
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()
    return out


def rollback_invite_claim_sqlite(*, jti: str, data_dir: pathlib.Path | None = None) -> None:
    if not jti:
        return
    conn = _conn_for_data_dir(data_dir)
    try:
        def _tx(c: sqlite3.Connection) -> None:
            cur = c.execute(
                """
                UPDATE invites
                SET redeem_count = MAX(0, redeem_count - 1),
                    last_redeem_at = CASE WHEN redeem_count <= 1 THEN 0.0 ELSE last_redeem_at END
                WHERE jti = ? AND revoked = 0
                """,
                (jti,),
            )
            if cur.rowcount > 0:
                _bump_sec_revision_in_tx(c, "guest_invites.json")

        run_write_transaction(conn, _tx)
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()


def revoke_invite_sqlite(*, jti: str, revoked_at: float, data_dir: pathlib.Path | None = None) -> dict[str, Any]:
    if not jti:
        return {"ok": False, "error": "missing_invite_id"}
    conn = _conn_for_data_dir(data_dir)
    found = False
    try:
        def _tx(c: sqlite3.Connection) -> None:
            nonlocal found
            cur = c.execute(
                "UPDATE invites SET revoked = 1, revoked_at = ? WHERE jti = ?",
                (float(revoked_at), jti),
            )
            found = cur.rowcount > 0
            if found:
                _bump_sec_revision_in_tx(c, "guest_invites.json")

        run_write_transaction(conn, _tx)
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()
    if not found:
        return {"ok": False, "error": "not_found"}
    return {"ok": True, "invite_id": jti, "revoked": True}


def verify_and_consume_otp_sqlite(
    *,
    clean_email: str,
    canon_target: str,
    otp_input: str,
    expected_purpose: str | None,
    consume_on_success: bool | None,
    now: float,
    canonical_email_fn: Any,
    hash_otp_fn: Any,
    data_dir: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Atomically verify rate limit, expiry, purpose, digest, and consume OTP inside SQLite BEGIN IMMEDIATE."""
    conn = _conn_for_data_dir(data_dir)
    result: dict[str, Any] = {}
    try:
        def _tx(c: sqlite3.Connection) -> None:
            nonlocal result
            rows = c.execute(
                """
                SELECT user_id, email, tier, account_meta_json
                FROM users
                WHERE account_meta_json != '{}' AND account_meta_json != ''
                ORDER BY tier ASC, user_id ASC
                """
            ).fetchall()
            target_uid: str | None = None
            target_acc: dict[str, Any] | None = None
            fallback_match: tuple[str, dict[str, Any]] | None = None
            for r in rows:
                try:
                    meta = json.loads(str(r["account_meta_json"] or "{}"))
                except Exception:
                    continue
                if not isinstance(meta, dict):
                    continue
                acc_email = str(meta.get("email") or r["email"] or "").strip().lower()
                if acc_email == clean_email:
                    target_uid = str(r["user_id"])
                    target_acc = meta
                    break
                if fallback_match is None and canon_target and canonical_email_fn(acc_email) == canon_target:
                    fallback_match = (str(r["user_id"]), meta)
            if target_acc is None and fallback_match is not None:
                target_uid, target_acc = fallback_match
            if target_acc is None or not target_uid:
                result = {
                    "ok": False,
                    "layer": 2,
                    "status_code": 400,
                    "audit_action": "otp_verify",
                    "audit_email": clean_email,
                    "audit_detail": "Chưa có yêu cầu mã OTP hoặc phiên đã hết hạn.",
                    "error": "Chưa có mã OTP cho tài khoản này. Hãy đăng nhập Lớp 1 trước!",
                }
                return

            key = str(target_acc.get("email") or clean_email).strip().lower()
            raw_fails = list(target_acc.get("otp_failed_verify_attempts") or [])
            recent_fails = [float(t) for t in raw_fails if (now - float(t)) < 300.0]
            if len(recent_fails) >= 3:
                result = {
                    "ok": False,
                    "layer": 2,
                    "status_code": 429,
                    "rate_limited": True,
                    "audit_action": "otp_verify_rate_limited",
                    "audit_email": key,
                    "audit_detail": "Đã thử sai mã OTP quá 3 lần trong 5 phút. Tạm thời chặn xác thực.",
                    "error": "Đã thử sai mã OTP quá 3 lần trong 5 phút. Vui lòng đợi 5 phút trước khi thử lại.",
                }
                return

            pending = target_acc.get("pending_otp")
            if not isinstance(pending, dict) or pending.get("consumed", False):
                result = {
                    "ok": False,
                    "layer": 2,
                    "status_code": 400,
                    "audit_action": "otp_verify",
                    "audit_email": key,
                    "audit_detail": "Chưa có yêu cầu mã OTP hoặc phiên đã hết hạn.",
                    "error": "Chưa có mã OTP cho tài khoản này. Hãy đăng nhập Lớp 1 trước!",
                }
                return

            chal_id = _derive_otp_challenge_id(key, pending)
            ch_row = _otp_challenge_in_tx(c, key, pending)
            if ch_row is not None:
                if int(ch_row["used"] or 0) != 0:
                    result = {
                        "ok": False,
                        "layer": 2,
                        "status_code": 400,
                        "audit_action": "otp_verify",
                        "audit_email": key,
                        "audit_detail": "Mã OTP đã được sử dụng.",
                        "error": "Chưa có mã OTP cho tài khoản này. Hãy đăng nhập Lớp 1 trước!",
                    }
                    return
                if int(ch_row["failed_attempts"] or 0) >= 3:
                    result = {
                        "ok": False,
                        "layer": 2,
                        "status_code": 429,
                        "rate_limited": True,
                        "audit_action": "otp_verify_rate_limited",
                        "audit_email": key,
                        "audit_detail": "Đã thử sai mã OTP quá 3 lần trong 5 phút. Tạm thời chặn xác thực.",
                        "error": "Đã thử sai mã OTP quá 3 lần trong 5 phút. Vui lòng đợi 5 phút trước khi thử lại.",
                    }
                    return

            if now > float(pending.get("expires_at", 0) or 0):
                result = {
                    "ok": False,
                    "layer": 2,
                    "status_code": 400,
                    "audit_action": "otp_verify",
                    "audit_email": key,
                    "audit_detail": "Mã OTP đã hết hạn (> 5 phút).",
                    "error": "Mã OTP đã hết hạn!",
                }
                return

            pending_purpose = str(pending.get("purpose") or "").strip()
            pending_email = str(pending.get("email") or key)
            if expected_purpose is not None and pending_purpose and pending_purpose != expected_purpose:
                result = {
                    "ok": False,
                    "layer": 2,
                    "status_code": 400,
                    "audit_action": "otp_verify_wrong_purpose",
                    "audit_email": pending_email,
                    "audit_detail": "Mã OTP không đúng mục đích xác thực yêu cầu.",
                    "error": "Mã OTP này không dành cho thao tác hiện tại. Vui lòng yêu cầu mã OTP mới!",
                }
                return

            otp_clean = str(otp_input or "").strip()
            otp_match = False
            if pending.get("otp_hash") and pending.get("otp_salt"):
                _, cand_hash = hash_otp_fn(otp_clean, otp_salt=str(pending["otp_salt"]))
                otp_match = bool(otp_clean) and hmac.compare_digest(cand_hash, str(pending["otp_hash"]))
            elif pending.get("otp_code"):
                otp_match = bool(otp_clean) and hmac.compare_digest(otp_clean, str(pending["otp_code"]))

            if not otp_match:
                recent_fails.append(now)
                target_acc["otp_failed_verify_attempts"] = recent_fails
                c.execute(
                    "UPDATE users SET account_meta_json = ? WHERE user_id = ?",
                    (json.dumps(target_acc, ensure_ascii=False), target_uid),
                )
                pending_purpose_val = pending_purpose or expected_purpose or "layer2_login"
                issued_ts = float(pending.get("created_at") or now)
                expires_ts = float(pending.get("expires_at") or (now + 300.0))
                if ch_row is not None:
                    c.execute(
                        "UPDATE otp_challenges SET failed_attempts = MAX(failed_attempts, ?) WHERE challenge_id = ?",
                        (len(recent_fails), chal_id),
                    )
                else:
                    c.execute(
                        """
                        INSERT INTO otp_challenges (
                            challenge_id, email, purpose, otp_salt, otp_hash,
                            issued_at, expires_at, used, failed_attempts, meta_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                        ON CONFLICT(challenge_id) DO UPDATE SET
                            failed_attempts = MAX(otp_challenges.failed_attempts, excluded.failed_attempts)
                        """,
                        (
                            chal_id,
                            key,
                            pending_purpose_val,
                            str(pending.get("otp_salt") or ""),
                            str(pending.get("otp_hash") or ""),
                            issued_ts,
                            expires_ts,
                            len(recent_fails),
                            json.dumps({"account_id": target_uid}, ensure_ascii=False),
                        ),
                    )
                _bump_sec_revision_in_tx(c, "auth3_accounts_state.json", now)
                result = {
                    "ok": False,
                    "layer": 2,
                    "status_code": 400,
                    "recent_fails": recent_fails,
                    "audit_action": "otp_verify",
                    "audit_email": pending_email,
                    "audit_detail": f"Nhập sai mã OTP: mã xác nhận không chính xác. (Lần {len(recent_fails)}/3)",
                    "error": f"Mã OTP '{otp_input}' không chính xác!",
                }
                return

            verified_purpose = pending_purpose or expected_purpose or "layer2_login"
            should_consume = consume_on_success if consume_on_success is not None else (verified_purpose == "layer2_login")
            target_acc["otp_failed_verify_attempts"] = []
            pending["verified_layer2"] = True
            if should_consume:
                if ch_row is not None:
                    cur = c.execute(
                        "UPDATE otp_challenges SET used = 1, failed_attempts = 0 WHERE challenge_id = ? AND used = 0",
                        (chal_id,),
                    )
                    if cur.rowcount != 1:
                        result = {
                            "ok": False,
                            "layer": 2,
                            "status_code": 400,
                            "audit_action": "otp_verify",
                            "audit_email": pending_email,
                            "audit_detail": "Mã OTP đã được sử dụng.",
                            "error": "Chưa có mã OTP cho tài khoản này. Hãy đăng nhập Lớp 1 trước!",
                        }
                        return
                else:
                    issued_ts = float(pending.get("created_at") or now)
                    expires_ts = float(pending.get("expires_at") or (now + 300.0))
                    c.execute(
                        """
                        INSERT INTO otp_challenges (
                            challenge_id, email, purpose, otp_salt, otp_hash,
                            issued_at, expires_at, used, failed_attempts, meta_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?)
                        ON CONFLICT(challenge_id) DO UPDATE SET
                            used = 1,
                            failed_attempts = 0
                        """,
                        (
                            chal_id,
                            key,
                            verified_purpose,
                            str(pending.get("otp_salt") or ""),
                            str(pending.get("otp_hash") or ""),
                            issued_ts,
                            expires_ts,
                            json.dumps({"account_id": target_uid}, ensure_ascii=False),
                        ),
                    )
                c.execute(
                    "UPDATE otp_challenges SET used = 1 WHERE lower(email) = ? AND purpose = ? AND used = 0",
                    (key, verified_purpose),
                )
                pending["consumed"] = True
                target_acc.pop("pending_otp", None)
                target_acc.pop("otp_cooldown_started_at", None)
            else:
                if ch_row is not None:
                    c.execute(
                        "UPDATE otp_challenges SET failed_attempts = 0 WHERE challenge_id = ? AND used = 0",
                        (chal_id,),
                    )
                pending["challenge_id"] = chal_id
                target_acc["pending_otp"] = pending

            c.execute(
                "UPDATE users SET account_meta_json = ? WHERE user_id = ?",
                (json.dumps(target_acc, ensure_ascii=False), target_uid),
            )
            _bump_sec_revision_in_tx(c, "auth3_accounts_state.json", now)
            pending_display = str(pending.get("display_name") or target_acc.get("display_name") or pending_email)
            pending_tier = int(pending.get("tier") or target_acc.get("tier") or 1)
            pending_account_id = str(pending.get("account_id") or target_acc.get("account_id") or "")
            result = {
                "ok": True,
                "layer": 2,
                "next_layer": 3,
                "verified_purpose": verified_purpose,
                "consumed": bool(should_consume),
                "email": pending_email,
                "key_email": key,
                "account_id": pending_account_id,
                "display_name": pending_display,
                "tier": pending_tier,
                "voice_verified": bool(
                    target_acc.get("voice_verified", not target_acc.get("needs_first_page_voice_enroll", False))
                ),
                "needs_first_page_voice_enroll": bool(target_acc.get("needs_first_page_voice_enroll")),
                "reading_prompt": target_acc.get("reading_prompt", ""),
                "updated_account": target_acc,
                "message": "✅ Lớp 2 (Gmail OTP) thành công!",
            }

        run_write_transaction(conn, _tx)
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()
    return result


def verify_and_reset_owner_pin_with_otp_sqlite(
    *,
    otp: str,
    pin: str,
    now: float,
    max_failures: int,
    verify_secret_fn: Any,
    hash_secret_fn: Any,
    data_dir: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Atomically verify reset OTP and update Owner PIN inside SQLite BEGIN IMMEDIATE."""
    conn = _conn_for_data_dir(data_dir)
    out: dict[str, Any] = {}
    try:
        def _tx(c: sqlite3.Connection) -> None:
            nonlocal out
            row = c.execute("SELECT * FROM owner_pin_security WHERE id = 1").fetchone()
            if row is None:
                out = {"ok": False, "status_code": 400, "error": "Mã xác nhận đã được dùng."}
                return
            if int(row["otp_used"] or 0) != 0:
                out = {"ok": False, "status_code": 400, "error": "Mã xác nhận đã được dùng."}
                return
            otp_fails = int(row["otp_failed_attempts"] or 0)
            if otp_fails >= max_failures:
                out = {"ok": False, "status_code": 423, "error": "Mã xác nhận đã bị khóa. Hãy yêu cầu mã mới."}
                return
            if float(row["otp_expires_at"] or 0.0) <= now:
                out = {"ok": False, "status_code": 400, "error": "Mã xác nhận đã hết hạn. Hãy gửi lại mã mới."}
                return
            if not verify_secret_fn(otp, str(row["otp_salt"] or ""), str(row["otp_hash"] or "")):
                c.execute(
                    "UPDATE owner_pin_security SET otp_failed_attempts = otp_failed_attempts + 1, revision = revision + 1, updated_at = ? WHERE id = 1",
                    (now,),
                )
                _bump_sec_revision_in_tx(c, "owner_pin.json", now)
                out = {"ok": False, "status_code": 403, "error": "Mã xác nhận không đúng."}
                return
            pin_salt, pin_hash = hash_secret_fn(pin)
            cur = c.execute(
                """
                UPDATE owner_pin_security
                SET pin_salt = ?, pin_hash = ?, failed_attempts = 0, locked = 0,
                    otp_used = 1, otp_failed_attempts = 0, revision = revision + 1, updated_at = ?
                WHERE id = 1 AND otp_used = 0
                """,
                (pin_salt, pin_hash, now),
            )
            if cur.rowcount != 1:
                out = {"ok": False, "status_code": 400, "error": "Mã xác nhận đã được dùng."}
                return
            _bump_sec_revision_in_tx(c, "owner_pin.json", now)
            out = {"ok": True, "pin_set": True, "locked": False, "message": "Đã đặt lại mã PIN."}

        run_write_transaction(conn, _tx)
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()
    return out
