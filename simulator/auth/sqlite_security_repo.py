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


def load_owner_pin_sqlite(data_dir: pathlib.Path | None) -> bytes | None:
    conn = _conn_for_data_dir(data_dir, readonly=True)
    try:
        row = conn.execute("SELECT * FROM owner_pin_security WHERE id = 1").fetchone()
        if not row or (not row["pin_hash"] and not row["otp_hash"] and int(row["failed_attempts"] or 0) == 0 and not row["locked"]):
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
        }
        return json.dumps(doc, ensure_ascii=False).encode("utf-8")
    finally:
        conn.close()


def save_owner_pin_sqlite(payload: bytes, data_dir: pathlib.Path | None) -> None:
    doc = json.loads(payload.decode("utf-8")) if payload else {}
    if not isinstance(doc, dict):
        doc = {}
    conn = _conn_for_data_dir(data_dir)
    try:
        def _tx(c: sqlite3.Connection) -> None:
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
                    str(doc.get("otp_hash") or ""),
                    float(doc.get("otp_expires_at") or 0.0),
                    1 if doc.get("otp_used") else 0,
                    int(doc.get("otp_failed_attempts") or 0),
                    float(doc.get("otp_issued_at") or 0.0),
                    float(doc.get("updated_at") or time.time()),
                ),
            )

        run_write_transaction(conn, _tx)
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()

def load_invites_sqlite(data_dir: pathlib.Path | None) -> bytes | None:
    conn = _conn_for_data_dir(data_dir, readonly=True)
    try:
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
    finally:
        conn.close()


def save_invites_sqlite(payload: bytes, data_dir: pathlib.Path | None) -> None:
    parsed = json.loads(payload.decode("utf-8")) if payload else {}
    raw_items = parsed.get("invites") if isinstance(parsed, dict) else parsed
    items = raw_items if isinstance(raw_items, list) else (list(raw_items.values()) if isinstance(raw_items, dict) else [])
    conn = _conn_for_data_dir(data_dir)
    try:
        from simulator.db_migrations import _ensure_preserve_user_for_fk

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

        def _tx(c: sqlite3.Connection) -> None:
            jti_list: list[str] = []
            for item in items:
                if not isinstance(item, dict) or not item.get("jti"):
                    continue
                jti = str(item["jti"])
                jti_list.append(jti)
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
                        revoked = excluded.revoked,
                        revoked_at = excluded.revoked_at,
                        redeem_count = excluded.redeem_count,
                        last_redeem_at = excluded.last_redeem_at,
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
            if jti_list:
                placeholders = ",".join("?" for _ in jti_list)
                c.execute(f"DELETE FROM invites WHERE jti NOT IN ({placeholders})", jti_list)

        run_write_transaction(conn, _tx)
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()

def load_rate_limits_sqlite(data_dir: pathlib.Path | None) -> bytes | None:
    conn = _conn_for_data_dir(data_dir, readonly=True)
    try:
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
    finally:
        conn.close()


def save_rate_limits_sqlite(payload: bytes, data_dir: pathlib.Path | None) -> None:
    parsed = json.loads(payload.decode("utf-8")) if payload else {}
    buckets = parsed.get("buckets") if isinstance(parsed, dict) else {}
    if not isinstance(buckets, dict):
        buckets = {}
    conn = _conn_for_data_dir(data_dir)
    try:
        now = time.time()

        def _tx(c: sqlite3.Connection) -> None:
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

        run_write_transaction(conn, _tx)
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()

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
        rows = conn.execute(
            "SELECT * FROM users WHERE account_meta_json != '{}' AND account_meta_json != '' ORDER BY tier ASC, user_id ASC"
        ).fetchall()
        if rows:
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
            if accounts:
                result = json.dumps({"accounts": accounts, "updated_at": time.time()}, ensure_ascii=False).encode("utf-8")
    finally:
        conn.close()
    if _accounts_cache_allowed():
        with _ACCOUNTS_CACHE_LOCK:
            if ep_before == _ACCOUNTS_CACHE_EPOCH:
                _ACCOUNTS_SQLITE_CACHE[cache_key] = (_ACCOUNTS_CACHE_EPOCH, time.monotonic(), result)
    return result


def save_accounts_sqlite(payload: bytes, data_dir: pathlib.Path | None) -> None:
    parsed = json.loads(payload.decode("utf-8")) if payload else {}
    accounts = parsed.get("accounts") if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
    if not isinstance(accounts, list):
        return
    import datetime as _dt

    tz = _dt.timezone(_dt.timedelta(hours=7))
    now_iso = _dt.datetime.now(tz).isoformat()
    now_ts = time.time()
    conn = _conn_for_data_dir(data_dir)
    try:
        def _tx(c: sqlite3.Connection) -> None:
            for acc in accounts:
                if not isinstance(acc, dict):
                    continue
                uid = str(acc.get("account_id") or acc.get("user_id") or acc.get("id") or "").strip()
                if not uid:
                    continue
                tier = int(acc.get("tier") or 3)
                if tier not in (1, 2, 3):
                    tier = 3
                rc = role_for_tier(tier)
                email = str(acc.get("email") or "").strip().lower()
                pw_hash = str(acc.get("password_hash") or "")
                pw_salt = str(acc.get("password_salt") or "")
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
                        str(acc.get("display_name") or acc.get("full_name") or uid),
                        rc,
                        tier,
                        1 if tier in (1, 2) else 0,
                        str(acc.get("invited_by") or "SYSTEM"),
                        now_iso,
                        email,
                        rc,
                        pw_salt,
                        pw_hash,
                        float(acc.get("password_updated_at") or now_ts),
                        1 if acc.get("permission_active", True) else 0,
                        str(acc.get("permission_status") or ("ACTIVE" if acc.get("permission_active", True) else "REVOKED")),
                        str(acc.get("created_at") or now_iso),
                        json.dumps(acc, ensure_ascii=False),
                    ),
                )
                # Sync normalized OTP challenges row if pending_otp exists; mark active challenge used otherwise
                p_otp = acc.get("pending_otp")
                if email and isinstance(p_otp, dict) and p_otp.get("otp_hash"):
                    chal_id = str(p_otp.get("challenge_id") or f"login_{email}")
                    c.execute(
                        """
                        INSERT INTO otp_challenges (
                            challenge_id, email, purpose, otp_salt, otp_hash,
                            issued_at, expires_at, used, failed_attempts, meta_json
                        ) VALUES (?, ?, 'login', ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(challenge_id) DO UPDATE SET
                            otp_salt = excluded.otp_salt,
                            otp_hash = excluded.otp_hash,
                            issued_at = excluded.issued_at,
                            expires_at = excluded.expires_at,
                            used = excluded.used,
                            failed_attempts = excluded.failed_attempts,
                            meta_json = excluded.meta_json
                        """,
                        (
                            chal_id,
                            email,
                            str(p_otp.get("otp_salt") or ""),
                            str(p_otp.get("otp_hash") or ""),
                            float(p_otp.get("created_at") or now_ts),
                            float(p_otp.get("expires_at") or now_ts + 300.0),
                            1 if p_otp.get("used") else 0,
                            int(len(acc.get("otp_failed_verify_attempts") or [])),
                            json.dumps({"account_id": uid}, ensure_ascii=False),
                        ),
                    )
                elif email:
                    c.execute(
                        "UPDATE otp_challenges SET used = 1 WHERE lower(email) = ? AND purpose = 'login' AND used = 0",
                        (email,),
                    )

        run_write_transaction(conn, _tx)
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()

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
        run_write_transaction(
            conn,
            lambda c: c.execute(
                """
                UPDATE invites
                SET redeem_count = MAX(0, redeem_count - 1),
                    last_redeem_at = CASE WHEN redeem_count <= 1 THEN 0.0 ELSE last_redeem_at END
                WHERE jti = ? AND revoked = 0
                """,
                (jti,),
            ),
        )
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

            chal_id = str(pending.get("challenge_id") or "").strip()
            if chal_id:
                ch_row = c.execute(
                    "SELECT used FROM otp_challenges WHERE challenge_id = ?",
                    (chal_id,),
                ).fetchone()
                if ch_row is not None and int(ch_row["used"] or 0) != 0:
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
                c.execute(
                    "UPDATE otp_challenges SET failed_attempts = ? WHERE lower(email) = ? AND used = 0",
                    (len(recent_fails), key),
                )
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
                if chal_id:
                    cur = c.execute(
                        "UPDATE otp_challenges SET used = 1, failed_attempts = 0 WHERE challenge_id = ? AND used = 0",
                        (chal_id,),
                    )
                    if cur.rowcount == 0:
                        existing_ch = c.execute(
                            "SELECT used FROM otp_challenges WHERE challenge_id = ?",
                            (chal_id,),
                        ).fetchone()
                        if existing_ch is not None:
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
                    c.execute(
                        "UPDATE otp_challenges SET used = 1, failed_attempts = 0 WHERE lower(email) = ? AND used = 0",
                        (pending_email.strip().lower(),),
                    )
                pending["consumed"] = True
                target_acc.pop("pending_otp", None)
                target_acc.pop("otp_cooldown_started_at", None)
            else:
                target_acc["pending_otp"] = pending

            c.execute(
                "UPDATE users SET account_meta_json = ? WHERE user_id = ?",
                (json.dumps(target_acc, ensure_ascii=False), target_uid),
            )
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
                    "UPDATE owner_pin_security SET otp_failed_attempts = otp_failed_attempts + 1, updated_at = ? WHERE id = 1",
                    (now,),
                )
                out = {"ok": False, "status_code": 403, "error": "Mã xác nhận không đúng."}
                return
            pin_salt, pin_hash = hash_secret_fn(pin)
            cur = c.execute(
                """
                UPDATE owner_pin_security
                SET pin_salt = ?, pin_hash = ?, failed_attempts = 0, locked = 0,
                    otp_used = 1, otp_failed_attempts = 0, updated_at = ?
                WHERE id = 1 AND otp_used = 0
                """,
                (pin_salt, pin_hash, now),
            )
            if cur.rowcount != 1:
                out = {"ok": False, "status_code": 400, "error": "Mã xác nhận đã được dùng."}
                return
            out = {"ok": True, "pin_set": True, "locked": False, "message": "Đã đặt lại mã PIN."}

        run_write_transaction(conn, _tx)
    finally:
        conn.close()
        invalidate_accounts_sqlite_cache()
    return out
