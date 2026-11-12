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

from simulator.auth.constants_and_crypto import DATA_DIR
from simulator.database_sqlite import _DB_LOCK as _SQLITE_GLOBAL_LOCK
from simulator.voice_config import (
    OWNER_EMAIL,
    OWNER_ID,
    ROLE_MAP,
    USER_ROLE_MAP,
    is_throwaway_qa_identity,
)

DB_PATH = DATA_DIR / "smarthome.db"
_LOCAL_SESSION_KEY = secrets.token_bytes(32)


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
        self._revoked_sids: set[str] = set()
        self._init_sqlite()
        if _test_sessions_allowed():
            self._seed_deterministic_test_sessions()
        self._load_durable_sessions()

    def _load_durable_sessions(self) -> None:
        try:
            from simulator.durable_store import load_state_file

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
            from simulator.durable_store import save_state_file

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

    def _init_sqlite(self) -> None:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with (
                self._lock,
                _SQLITE_GLOBAL_LOCK,
                contextlib.closing(sqlite3.connect(str(self.db_path), timeout=5.0)) as conn,
            ):
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        session_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        email TEXT,
                        display_name TEXT,
                        tier INTEGER NOT NULL,
                        role TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        source TEXT
                    )
                """)
                conn.commit()
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
            self._memory_cache[sid] = sess
            try:
                with (
                    _SQLITE_GLOBAL_LOCK,
                    contextlib.closing(sqlite3.connect(str(self.db_path), timeout=5.0)) as conn,
                ):
                    conn.execute("""
                        INSERT OR REPLACE INTO user_sessions
                        (session_id, user_id, email, display_name, tier, role, created_at, expires_at, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (sess.session_id, sess.user_id, sess.email, sess.display_name, sess.tier, sess.role, sess.created_at, sess.expires_at, sess.source))
                    conn.commit()
            except Exception:
                pass
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
            sess = self._memory_cache.get(sid)
            if sess:
                if sess.is_expired() or is_throwaway_qa_identity(sess.user_id) or is_throwaway_qa_identity(sess.email):
                    del self._memory_cache[sid]
                    self._delete_sqlite_session(sid)
                    return None
                return sess

            # SQLite fallback
            try:
                with (
                    _SQLITE_GLOBAL_LOCK,
                    contextlib.closing(sqlite3.connect(str(self.db_path), timeout=5.0)) as conn,
                ):
                    cur = conn.execute(
                        "SELECT session_id, user_id, email, display_name, tier, role, created_at, expires_at, source FROM user_sessions WHERE session_id = ?",
                        (sid,),
                    )
                    row = cur.fetchone()
                if row:
                    sess = UserSession(
                        session_id=row[0],
                        user_id=row[1],
                        email=row[2] or "",
                        display_name=row[3] or row[1],
                        tier=int(row[4]),
                        role=row[5],
                        created_at=float(row[6]),
                        expires_at=float(row[7]),
                        source=row[8] or "sqlite",
                        is_authenticated=True,
                    )
                    if sess.is_expired() or is_throwaway_qa_identity(sess.user_id) or is_throwaway_qa_identity(sess.email):
                        self._delete_sqlite_session(sid)
                        return None
                    self._memory_cache[sid] = sess
                    return sess
            except Exception:
                pass

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
            existed = sid in self._memory_cache
            if sid in self._memory_cache:
                del self._memory_cache[sid]
            db_deleted = self._delete_sqlite_session(sid)
            self._save_durable_sessions()
            return existed or db_deleted or self._decode_signed_token(sid) is not None

    def _delete_sqlite_session(self, session_id: str) -> bool:
        try:
            with (
                _SQLITE_GLOBAL_LOCK,
                contextlib.closing(sqlite3.connect(str(self.db_path), timeout=5.0)) as conn,
            ):
                cur = conn.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
                conn.commit()
                return cur.rowcount > 0
        except Exception:
            return False

    def cleanup_expired(self) -> int:
        now = time.time()
        count = 0
        with self._lock:
            expired_keys = [k for k, v in self._memory_cache.items() if v.expires_at <= now]
            for k in expired_keys:
                del self._memory_cache[k]
                count += 1
            try:
                with (
                    _SQLITE_GLOBAL_LOCK,
                    contextlib.closing(sqlite3.connect(str(self.db_path), timeout=5.0)) as conn,
                ):
                    cur = conn.execute("DELETE FROM user_sessions WHERE expires_at <= ?", (now,))
                    conn.commit()
                    count = max(count, cur.rowcount)
            except Exception:
                pass
        return count


_SESSION_STORE = SessionStore()


def get_session_store() -> SessionStore:
    return _SESSION_STORE


def session_is_current(sess: UserSession | None) -> bool:
    """Recheck revocation and invite lifetime on every HTTP/WS action."""
    if sess is None or not sess.is_authenticated or sess.is_expired():
        return False
    if sess.source.startswith("guest_invite:"):
        from simulator.auth.guest_invites import get_invite

        record = get_invite(sess.source.split(":", 1)[1])
        if not record or record.get("revoked") or float(record.get("expires_at") or 0) <= time.time():
            return False
    if sess.email and sess.source != "seed":
        from simulator.auth_3layer import get_auth_3layer_manager

        account = get_auth_3layer_manager().find_account(sess.email)
        if account and (not account.get("permission_active", True) or int(account.get("tier") or 99) != sess.tier):
            return False
    if sess.source != "seed":
        from simulator.api.deps import _REST_ENGINE

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
        from simulator.auth_3layer import get_auth_3layer_manager

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
            from simulator.engine.constants_and_time import DEFAULT_USERS

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

        # 4. Query param token
        if not token and hasattr(request, "query_params"):
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

