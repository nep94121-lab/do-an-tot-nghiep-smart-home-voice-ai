"""Module Quản lý Phiên Xác thực Đa người dùng Đồng thời (Session-based RBAC Store).

Đảm bảo nguyên tắc Stateless Zero-Trust:
- Mỗi request được định danh độc lập qua Session Token (Header, Cookie, Query, Payload).
- Không chia sẻ hay ghi đè trạng thái toàn cục Singleton giữa các phiên đồng thời.
- Đồng bộ bộ nhớ đệm luồng (thread-safe memory cache) và bảng SQLite `user_sessions`.
"""
from __future__ import annotations

import base64
import contextlib
import dataclasses
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import sqlite3
import threading
import sys
import time
from typing import Any

from backend.auth.constants_and_crypto import DATA_DIR
from backend.database_sqlite import _DB_LOCK as _SQLITE_GLOBAL_LOCK
from backend.voice_config import (
    OWNER_EMAIL,
    OWNER_ID,
    ROLE_MAP,
    USER_ROLE_MAP,
    is_throwaway_qa_identity,
)

DB_PATH = DATA_DIR / "smarthome.db"
_LOCAL_SESSION_KEY = secrets.token_bytes(32)
TRUSTED_DEVICE_COOKIE_NAME = "sh_trusted_device"
TRUSTED_DEVICE_TTL_SECONDS = 30 * 86400


def _test_sessions_allowed() -> bool:
    return "pytest" in sys.modules and not os.environ.get("VERCEL")


def _get_session_hmac_key() -> bytes:
    """Use a deployment secret; repository contents must never allow token forgery."""
    secret = os.environ.get("SMARTHOME_SESSION_SECRET") or os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("SMTP_PASSWORD")
    if secret:
        return hashlib.sha256(b"smarthome-session-v3:" + secret.encode("utf-8")).digest()
    if os.environ.get("VERCEL"):
        raise RuntimeError("Session signing secret is not configured")
    return _LOCAL_SESSION_KEY


@dataclasses.dataclass
class UserSession:
    session_id: str
    user_id: str
    email: str
    display_name: str
    tier: int
    role: str
    created_at: float
    expires_at: float
    source: str = "web"
    is_authenticated: bool = True

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class SessionStore:
    """Kho lưu trữ phiên xác thực thread-safe hỗ trợ cache bộ nhớ và SQLite bền vững."""

    def __init__(self, db_path: pathlib.Path | None = None) -> None:
        self.db_path = db_path or DB_PATH
        self._lock = threading.RLock()
        self._memory_cache: dict[str, UserSession] = {}
        self._sqlite_verified_mono: dict[str, float] = {}
        self._revoked_sids: set[str] = set()
        self._init_sqlite()
        if _test_sessions_allowed():
            self._seed_deterministic_test_sessions()
        self._load_durable_sessions()

    def _load_durable_sessions(self) -> None:
        try:
            from backend.durable_store import load_state_file

            raw = load_state_file("user_sessions.json", data_dir=self.db_path.parent)
            if not raw:
                return
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                return
            revoked = data.get("revoked_sids")
            if isinstance(revoked, list):
                self._revoked_sids.update(str(s) for s in revoked if s)
            sessions = data.get("sessions")
            now = time.time()
            if isinstance(sessions, list):
                for item in sessions:
                    if not isinstance(item, dict):
                        continue
                    sid = str(item.get("session_id") or "").strip()
                    exp = float(item.get("expires_at") or 0.0)
                    if not sid or sid in self._revoked_sids or exp <= now:
                        continue
                    sess = UserSession(
                        session_id=sid,
                        user_id=str(item.get("user_id") or ""),
                        email=str(item.get("email") or ""),
                        display_name=str(item.get("display_name") or ""),
                        tier=int(item.get("tier") or 3),
                        role=str(item.get("role") or "CHILD_GUEST"),
                        created_at=float(item.get("created_at") or now),
                        expires_at=exp,
                        source=str(item.get("source") or "durable"),
                        is_authenticated=bool(item.get("is_authenticated", True)),
                    )
                    self._memory_cache[sid] = sess
        except Exception:
            pass

    def _save_durable_sessions(self) -> None:
        try:
            from backend.durable_store import save_state_file

            now = time.time()
            active_list = [
                s.to_dict()
                for s in self._memory_cache.values()
                if s.source != "seed" and not s.is_expired() and s.expires_at > now
            ]
            payload_obj = {
                "revoked_sids": sorted(list(self._revoked_sids))[-200:],
                "sessions": active_list[-100:],
            }
            raw = (json.dumps(payload_obj, ensure_ascii=False) + "\n").encode("utf-8")
            save_state_file("user_sessions.json", raw, sync_cloud=False, data_dir=self.db_path.parent)
        except Exception:
            pass

    def _open_conn(self) -> sqlite3.Connection:
        from backend.database_sqlite import init_sqlite_database
        from backend.db_migrations import open_wal_connection

        target = init_sqlite_database(self.db_path)
        return open_wal_connection(target, readonly=False)

    def _init_sqlite(self) -> None:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, _SQLITE_GLOBAL_LOCK:
                conn = self._open_conn()
                try:
                    # Also ensure valid active rows from user_sessions exist in sessions
                    conn.execute(
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
                        WHERE us.expires_at > ?
                        """,
                        (time.time(),),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception:
            pass

    @staticmethod
    def _encode_signed_token(payload_dict: dict[str, Any]) -> str:
        payload_dict = {**payload_dict, "typ": "session"}
        raw_json = json.dumps(payload_dict, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        b64_part = base64.urlsafe_b64encode(raw_json).decode("ascii").rstrip("=")
        sig = hmac.new(_get_session_hmac_key(), b"session:" + b64_part.encode("ascii"), hashlib.sha256).hexdigest()[:28]
        return f"sess_{b64_part}.{sig}"

    @staticmethod
    def _decode_signed_token(token: str) -> UserSession | None:
        if not token.startswith("sess_") or "." not in token:
            return None
        body_part, sig_part = token[5:].rsplit(".", 1)
        if not body_part or not sig_part:
            return None
        expected_sig = hmac.new(_get_session_hmac_key(), b"session:" + body_part.encode("ascii"), hashlib.sha256).hexdigest()[:28]
        if not hmac.compare_digest(sig_part, expected_sig):
            return None
        try:
            pad = "=" * ((4 - len(body_part) % 4) % 4)
            data = json.loads(base64.urlsafe_b64decode(body_part + pad).decode("utf-8"))
            if not isinstance(data, dict):
                return None
            uid = str(data.get("u") or "")
            email = str(data.get("e") or "")
            tier = int(data.get("t") or 99)
            if data.get("typ") != "session" or not uid or uid.lower() in ("unknown", "anonymous", "stranger"):
                return None
            if tier not in (1, 2, 3) or data.get("r") != ROLE_MAP[tier]:
                return None
            if is_throwaway_qa_identity(uid) or is_throwaway_qa_identity(email):
                return None
            sess = UserSession(
                session_id=token,
                user_id=uid,
                email=email,
                display_name=str(data.get("d") or uid),
                tier=int(data.get("t") or 3),
                role=str(data.get("r") or "CHILD_GUEST"),
                created_at=float(data.get("c") or 0.0),
                expires_at=float(data.get("x") or 0.0),
                source=str(data.get("s") or "signed"),
                is_authenticated=True,
            )
            if sess.is_expired():
                return None
            return sess
        except Exception:
            return None

    def _seed_deterministic_test_sessions(self) -> None:
        """Tạo sẵn 3 phiên chuẩn định danh phục vụ test suite đồng thời 3 vai trò."""
        far_future = 86400 * 30
        self.create_session(
            user_id=OWNER_ID,
            email=OWNER_EMAIL,
            display_name="Nguyễn Tuấn Anh (Chủ nhà)",
            tier=1,
            role="ADMIN",
            session_id="sess_owner_t1_nep94121",
            ttl_sec=far_future,
            source="seed",
        )
        self.create_session(
            user_id="thanh_vien_a",
            email="thanhvien.a@gmail.com",
            display_name="Thành viên A (Gia đình)",
            tier=2,
            role="MEMBER",
            session_id="sess_family_t2_member_a",
            ttl_sec=far_future,
            source="seed",
        )
        self.create_session(
            user_id="khach_c",
            email="khach.c@gmail.com",
            display_name="Khách C (Khách viếng thăm)",
            tier=3,
            role="CHILD_GUEST",
            session_id="sess_guest_t3_visitor_c",
            ttl_sec=far_future,
            source="seed",
        )

    def create_session(
        self,
        user_id: str,
        tier: int,
        role: str,
        display_name: str = "",
        email: str = "",
        session_id: str | None = None,
        ttl_sec: int = 86400,
        source: str = "web",
    ) -> UserSession:
        now = time.time()
        norm_uid = str(user_id or "").strip()
        if int(tier) == 1 and norm_uid in ("owner_root_t1", OWNER_EMAIL, ""):
            norm_uid = OWNER_ID
        elif norm_uid == "family_member_a":
            norm_uid = "thanh_vien_a"
        elif norm_uid == "family_member_b":
            norm_uid = "thanh_vien_b"
        elif norm_uid == "guest_temp_c":
            norm_uid = "khach_c"

        if is_throwaway_qa_identity(norm_uid) or is_throwaway_qa_identity(email):
            return UserSession(
                session_id="rejected_qa_throwaway",
                user_id="anonymous",
                email="",
                display_name="Khách (Chưa đăng nhập)",
                tier=3,
                role="CHILD_GUEST",
                created_at=now,
                expires_at=now,
                source="rejected_unknown",
                is_authenticated=False,
            )

        exp = now + ttl_sec
        if session_id:
            sid = session_id
        else:
            sid = self._encode_signed_token(
                {
                    "u": norm_uid,
                    "e": email,
                    "d": display_name or norm_uid,
                    "t": int(tier),
                    "r": role,
                    "c": round(now, 3),
                    "x": round(exp, 3),
                    "s": source,
                    "n": secrets.token_hex(4),
                }
            )
        sess = UserSession(
            session_id=sid,
            user_id=norm_uid,
            email=email,
            display_name=display_name or norm_uid,
            tier=int(tier),
            role=role,
            created_at=now,
            expires_at=exp,
            source=source,
            is_authenticated=True,
        )
        with self._lock:
            self._revoked_sids.discard(sid)
            try:
                from backend.db_migrations import role_for_tier, run_write_transaction

                with _SQLITE_GLOBAL_LOCK:
                    conn = self._open_conn()
                    try:
                        from backend.db_migrations import _ensure_preserve_user_for_fk, _is_guest_or_anon_user_id

                        tok_hash = hashlib.sha256(sess.session_id.encode("utf-8")).hexdigest()
                        raw_jti = sess.source.split(":", 1)[1].strip() if str(sess.source).startswith("guest_invite:") else ""
                        rc = role_for_tier(sess.tier)
                        is_guest = _is_guest_or_anon_user_id(sess.user_id, sess.source, raw_jti)
                        db_uid: str | None = None if is_guest else sess.user_id

                        def _tx(c: sqlite3.Connection) -> None:
                            if db_uid is not None:
                                _ensure_preserve_user_for_fk(
                                    c,
                                    db_uid,
                                    tier=sess.tier if sess.tier in (1, 2, 3) else 3,
                                    role_code=rc if rc in ("ADMIN", "MEMBER", "CHILD_GUEST") else role_for_tier(sess.tier),
                                    display_name=sess.display_name or db_uid,
                                    email=sess.email or "",
                                    active=True,
                                )
                            db_jti: str | None = None
                            if raw_jti:
                                inv_row = c.execute("SELECT 1 FROM invites WHERE jti = ?", (raw_jti,)).fetchone()
                                if inv_row is not None:
                                    db_jti = raw_jti
                            c.execute(
                                """
                                INSERT INTO sessions (
                                    session_id, token_hash, user_id,
                                    role_code, tier, source, invite_jti, created_at, expires_at, revoked_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                                ON CONFLICT(session_id) DO UPDATE SET
                                    token_hash = excluded.token_hash,
                                    user_id = excluded.user_id,
                                    role_code = excluded.role_code,
                                    tier = excluded.tier,
                                    source = excluded.source,
                                    invite_jti = excluded.invite_jti,
                                    expires_at = excluded.expires_at,
                                    revoked_at = NULL
                                """,
                                (
                                    sess.session_id,
                                    tok_hash,
                                    db_uid,
                                    rc,
                                    sess.tier,
                                    sess.source,
                                    db_jti,
                                    sess.created_at,
                                    sess.expires_at,
                                ),
                            )
                            c.execute(
                                """
                                INSERT OR REPLACE INTO user_sessions
                                (session_id, user_id, tier, role, created_at, expires_at, source)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    sess.session_id,
                                    db_uid,
                                    sess.tier,
                                    sess.role,
                                    sess.created_at,
                                    sess.expires_at,
                                    sess.source,
                                ),
                            )

                        run_write_transaction(conn, _tx)
                    finally:
                        conn.close()
            except Exception:
                pass
            self._memory_cache[sid] = sess
            self._sqlite_verified_mono[sid] = time.monotonic()
            if source != "seed":
                self._save_durable_sessions()
        return sess

    def get_session(self, session_id: str) -> UserSession | None:
        if not session_id or not isinstance(session_id, str):
            return None
        sid = session_id.strip()
        # Never accept predictable fixtures, including old persisted rows, outside pytest.
        if sid in {"sess_owner_t1_nep94121", "sess_family_t2_member_a", "sess_guest_t3_visitor_c"} and not _test_sessions_allowed():
            return None
        if os.environ.get("VERCEL") and self._decode_signed_token(sid) is None:
            # Existing rows minted by the old unauthenticated role endpoint are invalid too.
            return None
        with self._lock:
            if sid in self._revoked_sids:
                return None

            if not ("pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST")):
                cached_fast = self._memory_cache.get(sid)
                if (
                    cached_fast is not None
                    and (time.monotonic() - self._sqlite_verified_mono.get(sid, 0.0)) < 1.5
                ):
                    if (
                        cached_fast.is_expired()
                        or is_throwaway_qa_identity(cached_fast.user_id)
                        or is_throwaway_qa_identity(cached_fast.email)
                    ):
                        self._memory_cache.pop(sid, None)
                        self._sqlite_verified_mono.pop(sid, None)
                        self._delete_sqlite_session(sid)
                        return None
                    return cached_fast

            # SQLite single source of truth check when row exists (catches revocation or restart persistence)
            try:
                from backend.db_migrations import open_wal_connection

                with _SQLITE_GLOBAL_LOCK:
                    conn = (
                        open_wal_connection(self.db_path, readonly=True)
                        if self.db_path.exists()
                        else self._open_conn()
                    )
                    try:
                        cur = conn.execute(
                            """
                            SELECT s.session_id, s.user_id,
                                   COALESCE(u.email, '') AS email,
                                   COALESCE(u.full_name, '') AS display_name,
                                   s.tier, s.role_code, s.created_at, s.expires_at,
                                   s.source, s.invite_jti, s.revoked_at
                            FROM sessions s
                            LEFT JOIN users u ON s.user_id = u.user_id
                            WHERE s.session_id = ?
                            """,
                            (sid,),
                        )
                        row = cur.fetchone()
                        if row is None:
                            cur2 = conn.execute(
                                """
                                SELECT us.session_id, us.user_id,
                                       COALESCE(u.email, '') AS email,
                                       COALESCE(u.full_name, '') AS display_name,
                                       us.tier, us.role, us.created_at, us.expires_at, us.source
                                FROM user_sessions us
                                LEFT JOIN users u ON us.user_id = u.user_id
                                WHERE us.session_id = ?
                                """,
                                (sid,),
                            )
                            row2 = cur2.fetchone()
                        else:
                            row2 = None
                    finally:
                        conn.close()
                if row is not None:
                    if row["revoked_at"] is not None:
                        self._revoked_sids.add(sid)
                        self._memory_cache.pop(sid, None)
                        self._sqlite_verified_mono.pop(sid, None)
                        return None
                    r_jti = str(row["invite_jti"] or "")
                    if not r_jti and str(row["source"] or "").startswith("guest_invite:"):
                        r_jti = str(row["source"]).split(":", 1)[1].strip()
                    tok_meta = self._decode_signed_token(sid)
                    raw_row_uid = str(row["user_id"] or "").strip()
                    if not raw_row_uid and tok_meta is not None:
                        tok_uid = str(tok_meta.user_id or "").strip()
                        if tok_uid and not tok_uid.lower().startswith("guest_") and tok_uid.lower() not in ("anonymous", "unknown", "stranger", "guest"):
                            raw_row_uid = tok_uid
                    resolved_uid = raw_row_uid or (f"guest_{r_jti[:12]}" if r_jti else "anonymous")
                    resolved_dname = str(row["display_name"] or "").strip()
                    if not resolved_dname and tok_meta is not None and tok_meta.display_name:
                        resolved_dname = tok_meta.display_name
                    if not resolved_dname:
                        resolved_dname = f"Guest tier {int(row['tier'])}" if (r_jti and not raw_row_uid) else resolved_uid
                    resolved_email = str(row["email"] or "").strip()
                    if not resolved_email and tok_meta is not None and tok_meta.email:
                        resolved_email = tok_meta.email
                    sess = UserSession(
                        session_id=row["session_id"],
                        user_id=resolved_uid,
                        email=resolved_email,
                        display_name=resolved_dname,
                        tier=int(row["tier"]),
                        role=row["role_code"],
                        created_at=float(row["created_at"]),
                        expires_at=float(row["expires_at"]),
                        source=row["source"] or "sqlite",
                        is_authenticated=True,
                    )
                    if sess.is_expired() or is_throwaway_qa_identity(sess.user_id) or is_throwaway_qa_identity(sess.email):
                        self._memory_cache.pop(sid, None)
                        self._delete_sqlite_session(sid)
                        return None
                    self._memory_cache[sid] = sess
                    self._sqlite_verified_mono[sid] = time.monotonic()
                    return sess
                if row2 is not None:
                    r2_src = str(row2["source"] or "sqlite")
                    r2_jti = r2_src.split(":", 1)[1].strip() if r2_src.startswith("guest_invite:") else ""
                    resolved_uid2 = str(row2["user_id"] or "") or (f"guest_{r2_jti[:12]}" if r2_jti else "anonymous")
                    resolved_dname2 = str(row2["display_name"] or "") or (
                        f"Guest tier {int(row2['tier'])}" if r2_jti else resolved_uid2
                    )
                    sess = UserSession(
                        session_id=row2["session_id"],
                        user_id=resolved_uid2,
                        email=row2["email"] or "",
                        display_name=resolved_dname2,
                        tier=int(row2["tier"]),
                        role=row2["role"],
                        created_at=float(row2["created_at"]),
                        expires_at=float(row2["expires_at"]),
                        source=r2_src,
                        is_authenticated=True,
                    )
                    if sess.is_expired() or is_throwaway_qa_identity(sess.user_id) or is_throwaway_qa_identity(sess.email):
                        self._memory_cache.pop(sid, None)
                        self._delete_sqlite_session(sid)
                        return None
                    self._memory_cache[sid] = sess
                    self._sqlite_verified_mono[sid] = time.monotonic()
                    return sess
            except Exception:
                pass

            sess = self._memory_cache.get(sid)
            if sess:
                if sess.is_expired() or is_throwaway_qa_identity(sess.user_id) or is_throwaway_qa_identity(sess.email):
                    del self._memory_cache[sid]
                    self._delete_sqlite_session(sid)
                    return None
                return sess

            # Stateless HMAC-signed token fallback (serverless cross-instance consistency)
            signed_sess = self._decode_signed_token(sid)
            if signed_sess is not None:
                self._memory_cache[sid] = signed_sess
                return signed_sess
        return None

    def revoke_session(self, session_id: str) -> bool:
        if not session_id:
            return False
        sid = session_id.strip()
        with self._lock:
            self._revoked_sids.add(sid)
            self._sqlite_verified_mono.pop(sid, None)
            existed = sid in self._memory_cache
            if sid in self._memory_cache:
                del self._memory_cache[sid]
            db_deleted = self._delete_sqlite_session(sid)
            self._save_durable_sessions()
            return existed or db_deleted or self._decode_signed_token(sid) is not None

    def _delete_sqlite_session(self, session_id: str) -> bool:
        try:
            from backend.db_migrations import run_write_transaction

            with _SQLITE_GLOBAL_LOCK:
                conn = self._open_conn()
                try:
                    def _tx(c: sqlite3.Connection) -> bool:
                        c1 = c.execute(
                            "UPDATE sessions SET revoked_at = ? WHERE session_id = ? AND revoked_at IS NULL",
                            (time.time(), session_id),
                        )
                        c2 = c.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
                        return (c1.rowcount or 0) > 0 or (c2.rowcount or 0) > 0

                    return run_write_transaction(conn, _tx)
                finally:
                    conn.close()
        except Exception:
            return False

    def cleanup_expired(self) -> int:
        now = time.time()
        count = 0
        with self._lock:
            expired_keys = [k for k, v in self._memory_cache.items() if v.expires_at <= now]
            for k in expired_keys:
                del self._memory_cache[k]
                self._sqlite_verified_mono.pop(k, None)
                count += 1
            try:
                from backend.db_migrations import run_write_transaction

                with _SQLITE_GLOBAL_LOCK:
                    conn = self._open_conn()
                    try:
                        def _tx(c: sqlite3.Connection) -> int:
                            c1 = c.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
                            c2 = c.execute("DELETE FROM user_sessions WHERE expires_at <= ?", (now,))
                            return max(int(c1.rowcount or 0), int(c2.rowcount or 0))

                        count = max(count, run_write_transaction(conn, _tx))
                    finally:
                        conn.close()
            except Exception:
                pass
        return count


_SESSION_STORE = SessionStore()
_DEFAULT_SESSION_STORE = _SESSION_STORE


def get_session_store() -> SessionStore:
    if _SESSION_STORE is _DEFAULT_SESSION_STORE:
        from backend.db_migrations import resolve_sqlite_db_path

        live_path = resolve_sqlite_db_path()
        if _SESSION_STORE.db_path != live_path:
            _SESSION_STORE.db_path = live_path
    return _SESSION_STORE


def session_is_current(sess: UserSession | None) -> bool:
    """Recheck revocation and invite lifetime on every HTTP/WS action."""
    if sess is None or not sess.is_authenticated or sess.is_expired():
        return False
    if sess.source.startswith("guest_invite:"):
        from backend.auth.guest_invites import get_invite

        record = get_invite(sess.source.split(":", 1)[1])
        if not record or record.get("revoked") or float(record.get("expires_at") or 0) <= time.time():
            return False
    if sess.email and sess.source != "seed":
        from backend.auth_3layer import get_auth_3layer_manager

        mgr = get_auth_3layer_manager()
        account = mgr.find_exact_account(sess.email) if hasattr(mgr, "find_exact_account") else mgr.find_account(sess.email)
        if account and (not account.get("permission_active", True) or int(account.get("tier") or 99) != sess.tier):
            return False
    if sess.source != "seed" and int(sess.tier) != 1:
        from backend.api.deps import _REST_ENGINE

        user = _REST_ENGINE.users.get(sess.user_id)
        if user and not user.get("active", True):
            return False
    return True


_IDENTITY_PAYLOAD_KEYS = ("role", "user_id", "email")
_REJECTED_IDENTITY_LITERALS = frozenset(
    {
        "",
        "unknown",
        "stranger",
        "stranger_1",
        "intruder",
        "intruder_voice_2",
        "none",
        "null",
        "anonymous",
        "unauthorized",
    }
)


def _make_rejected_unknown_session() -> UserSession:
    now = time.time()
    return UserSession(
        session_id="rejected_unknown",
        user_id="unknown",
        email="",
        display_name="Người lạ chưa xác thực",
        tier=99,
        role="UNKNOWN",
        created_at=now,
        expires_at=now + 86400,
        source="rejected_unknown",
        is_authenticated=False,
    )


def _match_single_identity_value(
    raw_val: Any,
    engine: Any | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Kiểm tra 1 giá trị định danh/vai trò tường minh trong payload có hợp lệ không."""
    if raw_val is None or isinstance(raw_val, bool) or not isinstance(raw_val, (str, int)):
        return False, {}
    s = str(raw_val).strip()
    s_low = s.lower()
    s_up = s.upper()
    if s_low in _REJECTED_IDENTITY_LITERALS or is_throwaway_qa_identity(s_low):
        return False, {}

    # 1. Known roles: ADMIN, MEMBER, CHILD_GUEST
    if s_up in ("ADMIN", "MEMBER", "CHILD_GUEST"):
        tier_by_role = {"ADMIN": 1, "MEMBER": 2, "CHILD_GUEST": 3}
        t_val = tier_by_role[s_up]
        uid = USER_ROLE_MAP.get(t_val, OWNER_ID if t_val == 1 else "khach_c")
        return True, {
            "user_id": uid,
            "email": OWNER_EMAIL if t_val == 1 else "",
            "display_name": uid,
            "tier": t_val,
            "role": s_up,
        }

    # 2. Tier strings: "1", "2", "3", "tier1", "tier2", "tier3"
    if s_low in ("1", "2", "3", "tier1", "tier2", "tier3", "tier_1", "tier_2", "tier_3"):
        t_val = int(s_low[-1])
        r_val = ROLE_MAP.get(t_val, "CHILD_GUEST")
        uid = USER_ROLE_MAP.get(t_val, OWNER_ID if t_val == 1 else "khach_c")
        return True, {
            "user_id": uid,
            "email": OWNER_EMAIL if t_val == 1 else "",
            "display_name": uid,
            "tier": t_val,
            "role": r_val,
        }

    alias_map = {
        "owner_voice_1": OWNER_ID,
        "user_voice_thanh_vien_a": USER_ROLE_MAP.get(2, "thanh_vien_a"),
        "user_voice_khach_c": USER_ROLE_MAP.get(3, "khach_c"),
        "member_1": USER_ROLE_MAP.get(2, "thanh_vien_a"),
        "member_2": "thanh_vien_b",
        "guest_1": USER_ROLE_MAP.get(3, "khach_c"),
        "guest_2": "khach_d",
    }
    lookup_id = alias_map.get(s_low, s_low)

    # 3. Known users in engine.users (if engine provided)
    eng_users = getattr(engine, "users", None) if engine is not None else None
    if isinstance(eng_users, dict):
        u_obj = eng_users.get(lookup_id)
        if u_obj is None:
            for uid_k, u_cand in eng_users.items():
                if isinstance(u_cand, dict) and str(u_cand.get("name", "")).strip().lower() == s_low:
                    u_obj = u_cand
                    lookup_id = uid_k
                    break
        if isinstance(u_obj, dict):
            if not u_obj.get("active", True):
                return False, {}
            t_val = int(u_obj.get("tier", 99))
            r_val = str(u_obj.get("role") or ROLE_MAP.get(t_val, "UNKNOWN")).upper()
            if t_val not in (1, 2, 3) or r_val == "UNKNOWN":
                return False, {}
            return True, {
                "user_id": str(u_obj.get("id") or lookup_id),
                "email": str(u_obj.get("email") or ""),
                "display_name": str(u_obj.get("name") or lookup_id),
                "tier": t_val,
                "role": r_val,
            }

    # 4. Known account in get_auth_3layer_manager().find_account(...) or active guest_sessions
    try:
        from backend.auth_3layer import get_auth_3layer_manager

        mgr = get_auth_3layer_manager()
    except Exception:
        mgr = None

    if mgr is not None:
        acc = mgr.find_account(s)
        if isinstance(acc, dict):
            acc_email = str(acc.get("email") or "").strip().lower()
            acc_id = str(acc.get("account_id") or "").strip().lower()
            acc_name = str(acc.get("display_name") or "").strip().lower()
            known_aliases = {"khach.hust@gmail.com", "khach_hust", "guest_1", "member_1"}
            is_exact_match = (
                s_low in (acc_email, acc_id, acc_name)
                or lookup_id in (acc_email, acc_id, acc_name)
                or s_low.replace(" ", "_") == acc_id
                or s_low in known_aliases
            )
            if is_exact_match:
                if not acc.get("permission_active", True):
                    return False, {}
                t_val = int(acc.get("tier", 99))
                r_val = str(acc.get("role") or ROLE_MAP.get(t_val, "UNKNOWN")).upper()
                if t_val not in (1, 2, 3) or r_val == "UNKNOWN":
                    return False, {}
                return True, {
                    "user_id": str(acc.get("account_id") or lookup_id),
                    "email": str(acc.get("email") or ""),
                    "display_name": str(acc.get("display_name") or lookup_id),
                    "tier": t_val,
                    "role": r_val,
                }

        now_ts = time.time()
        for gs_attr in ("guest_sessions", "guest_qr_sessions"):
            gs_map = getattr(mgr, gs_attr, None)
            if isinstance(gs_map, dict):
                gs_item = gs_map.get(s) or gs_map.get(s_low)
                if gs_item is None:
                    for gs_v in gs_map.values():
                        if isinstance(gs_v, dict) and s_low in (
                            str(gs_v.get("guest_id") or "").strip().lower(),
                            str(gs_v.get("session_id") or "").strip().lower(),
                            str(gs_v.get("email") or "").strip().lower(),
                        ):
                            gs_item = gs_v
                            break
                if isinstance(gs_item, dict):
                    if not gs_item.get("active", True) or gs_item.get("revoked", False):
                        return False, {}
                    exp_ts = float(gs_item.get("expires_at_ts") or gs_item.get("expires_at") or (now_ts + 60))
                    if exp_ts <= now_ts:
                        return False, {}
                    gid = str(gs_item.get("guest_id") or gs_item.get("session_id") or s)
                    return True, {
                        "user_id": gid,
                        "email": str(gs_item.get("email") or ""),
                        "display_name": str(gs_item.get("display_name") or "Khách tạm thời"),
                        "tier": 3,
                        "role": "CHILD_GUEST",
                    }

    # 5. Fallback to DEFAULT_USERS if engine was not provided
    if engine is None:
        try:
            from backend.engine.constants_and_time import DEFAULT_USERS

            if lookup_id in DEFAULT_USERS:
                u_def = DEFAULT_USERS[lookup_id]
                t_val = int(u_def.get("tier", 3))
                return True, {
                    "user_id": str(u_def.get("id") or lookup_id),
                    "email": str(u_def.get("email") or ""),
                    "display_name": str(u_def.get("name") or lookup_id),
                    "tier": t_val,
                    "role": str(u_def.get("role") or ROLE_MAP.get(t_val, "CHILD_GUEST")),
                }
        except Exception:
            pass

    return False, {}


def _resolve_explicit_payload_identity(
    payload: dict[str, Any],
    engine: Any | None = None,
) -> tuple[bool, UserSession | None]:
    """Kiểm tra nếu payload có chứa bất kỳ trường định danh/vai trò tường minh nào.
    Trả về (has_explicit_field, UserSession)."""
    present_keys = [k for k in _IDENTITY_PAYLOAD_KEYS if k in payload]
    if not present_keys:
        return False, None

    resolved_info: dict[str, Any] = {}
    for k in present_keys:
        ok, info = _match_single_identity_value(payload.get(k), engine=engine)
        if not ok:
            return True, _make_rejected_unknown_session()
        if not resolved_info:
            resolved_info = info

    now = time.time()
    return True, UserSession(
        session_id=f"explicit_{resolved_info['user_id']}",
        user_id=resolved_info["user_id"],
        email=resolved_info.get("email", ""),
        display_name=resolved_info.get("display_name") or resolved_info["user_id"],
        tier=int(resolved_info["tier"]),
        role=str(resolved_info["role"]),
        created_at=now,
        expires_at=now + 86400,
        source="explicit_payload",
        is_authenticated=True,
    )


def _password_fingerprint(password_hash: str) -> str:
    """Rút trích dấu vân tay mật khẩu một chiều (đổi mật khẩu sẽ tự vô hiệu hóa token cũ)."""
    return hashlib.sha256(b"tdev-pwf-v1:" + str(password_hash or "").encode("utf-8")).hexdigest()[:16]


def _ua_fingerprint(user_agent: str) -> str:
    """Rút trích dấu vân tay User-Agent tách miền (chặn copy cookie sang thiết bị/trình duyệt khác)."""
    norm_ua = str(user_agent or "").strip().lower()[:256]
    return hashlib.sha256(b"tdev-uaf-v1:" + norm_ua.encode("utf-8")).hexdigest()[:16]


def mint_trusted_device_token(
    account_id: str,
    email: str,
    password_hash: str,
    user_agent: str = "",
    *,
    ttl_seconds: int = TRUSTED_DEVICE_TTL_SECONDS,
    now: float | None = None,
) -> str:
    """Sinh token thiết bị tin cậy 30 ngày ký HMAC-SHA256 tách miền riêng (tdev_)."""
    issued_at = float(now if now is not None else time.time())
    ttl = max(60, min(int(ttl_seconds), TRUSTED_DEVICE_TTL_SECONDS))
    payload = {
        "typ": "trusted_device",
        "u": str(account_id or "").strip(),
        "e": str(email or "").strip().lower(),
        "pwf": _password_fingerprint(password_hash),
        "uaf": _ua_fingerprint(user_agent),
        "c": round(issued_at, 3),
        "x": round(issued_at + ttl, 3),
        "n": secrets.token_hex(8),
    }
    raw_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    b64_part = base64.urlsafe_b64encode(raw_json).decode("ascii").rstrip("=")
    sig = hmac.new(_get_session_hmac_key(), b"trusted_device:" + b64_part.encode("ascii"), hashlib.sha256).hexdigest()[:28]
    tok = f"tdev_{b64_part}.{sig}"
    if not os.environ.get("VERCEL") and ("pytest" not in sys.modules or os.environ.get("SMARTHOME_SECURITY_BACKEND") == "sqlite"):
        try:
            from backend.auth.sqlite_security_repo import record_trusted_device_sqlite

            record_trusted_device_sqlite(
                tok,
                str(account_id or "").strip(),
                str(email or "").strip().lower(),
                user_agent,
                issued_at,
                issued_at + ttl,
                data_dir=get_session_store().db_path.parent,
            )
        except Exception:
            pass
    return tok


def verify_trusted_device_token(
    token: str | None,
    *,
    expected_account_id: str,
    expected_email: str,
    expected_password_hash: str,
    expected_user_agent: str = "",
    now: float | None = None,
) -> bool:
    """Xác thực token thiết bị tin cậy tdev_ đúng tài khoản, mật khẩu, User-Agent và chưa quá 30 ngày."""
    raw = str(token or "").strip()
    if not raw.startswith("tdev_") or "." not in raw:
        return False
    body_part, sig_part = raw[5:].rsplit(".", 1)
    if not body_part or not sig_part:
        return False
    expected_sig = hmac.new(
        _get_session_hmac_key(), b"trusted_device:" + body_part.encode("ascii"), hashlib.sha256
    ).hexdigest()[:28]
    if not hmac.compare_digest(sig_part, expected_sig):
        return False
    try:
        pad = "=" * ((4 - len(body_part) % 4) % 4)
        data = json.loads(base64.urlsafe_b64decode(body_part + pad).decode("utf-8"))
        if not isinstance(data, dict) or data.get("typ") != "trusted_device":
            return False
        check_now = float(now if now is not None else time.time())
        created_at = float(data.get("c") or 0.0)
        expires_at = float(data.get("x") or 0.0)
        if created_at <= 0.0 or expires_at <= 0.0:
            return False
        if created_at > check_now + 60.0 or expires_at <= check_now:
            return False
        if (expires_at - created_at) > TRUSTED_DEVICE_TTL_SECONDS + 60.0:
            return False
        if str(data.get("u") or "").strip() != str(expected_account_id or "").strip():
            return False
        if str(data.get("e") or "").strip().lower() != str(expected_email or "").strip().lower():
            return False
        if not hmac.compare_digest(str(data.get("pwf") or ""), _password_fingerprint(expected_password_hash)):
            return False
        if not hmac.compare_digest(str(data.get("uaf") or ""), _ua_fingerprint(expected_user_agent)):
            return False
        if not os.environ.get("VERCEL") and ("pytest" not in sys.modules or os.environ.get("SMARTHOME_SECURITY_BACKEND") == "sqlite"):
            try:
                from backend.auth.sqlite_security_repo import is_trusted_device_revoked_sqlite

                if is_trusted_device_revoked_sqlite(raw, data_dir=get_session_store().db_path.parent):
                    return False
            except Exception:
                pass
        return True
    except Exception:
        return False


def revoke_trusted_device(token: str | None) -> None:
    """Revoke a trusted-device token in SQLite when logging out with device revocation."""
    raw = str(token or "").strip()
    if not raw:
        return
    if not os.environ.get("VERCEL") and ("pytest" not in sys.modules or os.environ.get("SMARTHOME_SECURITY_BACKEND") == "sqlite"):
        try:
            from backend.auth.sqlite_security_repo import revoke_trusted_device_sqlite

            revoke_trusted_device_sqlite(raw, data_dir=get_session_store().db_path.parent)
        except Exception:
            pass


def resolve_request_session(
    request: Any | None = None,
    payload: dict[str, Any] | None = None,
    engine: Any | None = None,
) -> UserSession:
    """Xác định phiên người dùng một cách stateless từ Header / Cookie / Query / Payload / Fallback."""
    store = get_session_store()
    token = ""

    # Quyền chỉ đến từ cookie/header phiên (hoặc mã mời đã đổi lấy phiên).
    # user_id/role/tier/speaker_id trong JSON không được cấp quyền và không được phủ quyết phiên hợp lệ.
    if request is not None:
        # 1. Header Authorization Bearer
        auth_header = str(request.headers.get("authorization", "") or "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()

        # 2. Header X-Session-Token
        if not token:
            token = str(request.headers.get("x-session-token", "") or "").strip()

        # 3. Cookie sh_session_token hoặc session_token
        if not token and hasattr(request, "cookies"):
            token = str(request.cookies.get("sh_session_token") or request.cookies.get("session_token") or "").strip()

        # 4. Query param token or short-lived HMAC realtime ticket
        if not token and hasattr(request, "query_params"):
            ticket = str(request.query_params.get("ticket") or "").strip()
            if ticket:
                from backend.realtime_hub import verify_realtime_ticket

                t_sess = verify_realtime_ticket(ticket)
                if t_sess is not None:
                    return t_sess
            token = str(request.query_params.get("token") or "").strip()

    # 5. Body payload session_token hoặc guest_session_id
    if not token and payload and isinstance(payload, dict):
        token = str(payload.get("session_token") or payload.get("guest_session_id") or payload.get("token") or "").strip()

    if token:
        sess = store.get_session(token)
        if session_is_current(sess):
            return sess
        # Token provided but expired, revoked, or invalid -> strictly Tier 3 unauthenticated
        return UserSession(
            session_id="expired_or_invalid",
            user_id="anonymous",
            email="",
            display_name="Khách (Phiên hết hạn/không hợp lệ)",
            tier=3,
            role="CHILD_GUEST",
            created_at=time.time(),
            expires_at=time.time() + 86400,
            source="invalid_token",
            is_authenticated=False,
        )

    # 8. Fallback mặc định cho client chưa đăng nhập: Tầng 3 (Khách)
    return UserSession(
        session_id="anonymous",
        user_id="anonymous",
        email="",
        display_name="Khách (Chưa đăng nhập)",
        tier=3,
        role="CHILD_GUEST",
        created_at=time.time(),
        expires_at=time.time() + 86400,
        source="unauthenticated",
        is_authenticated=False,
    )


def resolve_strict_ws_session(
    ws: Any | None = None,
    msg: dict[str, Any] | None = None,
) -> UserSession:
    """Xác thực nghiêm ngặt phiên WebSocket từ Header / Cookie / Query / Token trong message.
    Tuyệt đối KHÔNG tin tưởng `role`, `tier`, `user_id` tự khai từ phía client hay trạng thái engine toàn cục.
    """
    store = get_session_store()
    token = ""

    if ws is not None:
        headers = getattr(ws, "headers", None)
        if headers is not None and hasattr(headers, "get"):
            auth_header = str(headers.get("authorization", "") or "")
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:].strip()
            if not token:
                token = str(headers.get("x-session-token", "") or "").strip()

        cookies = getattr(ws, "cookies", None)
        if not token and cookies is not None and hasattr(cookies, "get"):
            token = str(
                cookies.get("sh_session_token") or cookies.get("session_token") or ""
            ).strip()

        query_params = getattr(ws, "query_params", None)
        if not token and query_params is not None and hasattr(query_params, "get"):
            ticket = str(query_params.get("ticket") or "").strip()
            if ticket:
                from backend.realtime_hub import verify_realtime_ticket

                t_sess = verify_realtime_ticket(ticket)
                if t_sess is not None:
                    return t_sess
            token = str(
                query_params.get("token") or query_params.get("session_token") or ""
            ).strip()

    if not token and isinstance(msg, dict):
        token = str(msg.get("session_token") or msg.get("token") or "").strip()

    if token:
        sess = store.get_session(token)
        if session_is_current(sess):
            return sess

    now = time.time()
    return UserSession(
        session_id="ws_unauthenticated",
        user_id="anonymous",
        email="",
        display_name="Khách (Chưa xác thực phiên WebSocket)",
        tier=3,
        role="CHILD_GUEST",
        created_at=now,
        expires_at=now + 3600,
        source="ws_unauthenticated",
        is_authenticated=False,
    )

