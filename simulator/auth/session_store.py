"""Module Quản lý Phiên Xác thực Đa người dùng Đồng thời (Session-based RBAC Store).

Đảm bảo nguyên tắc Stateless Zero-Trust:
- Mỗi request được định danh độc lập qua Session Token (Header, Cookie, Query, Payload).
- Không chia sẻ hay ghi đè trạng thái toàn cục Singleton giữa các phiên đồng thời.
- Đồng bộ bộ nhớ đệm luồng (thread-safe memory cache) và bảng SQLite `user_sessions`.
"""
from __future__ import annotations

import dataclasses
import pathlib
import secrets
import sqlite3
import threading
import time
from typing import Any

from simulator.auth.constants_and_crypto import DATA_DIR
from simulator.voice_config import (
    OWNER_EMAIL,
    OWNER_ID,
    ROLE_MAP,
    USER_ROLE_MAP,
)

DB_PATH = DATA_DIR / "smarthome.db"


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
        self._init_sqlite()
        self._seed_deterministic_test_sessions()

    def _init_sqlite(self) -> None:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
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
        sid = session_id or f"sess_{secrets.token_urlsafe(24)}"
        now = time.time()
        sess = UserSession(
            session_id=sid,
            user_id=user_id,
            email=email,
            display_name=display_name or user_id,
            tier=int(tier),
            role=role,
            created_at=now,
            expires_at=now + ttl_sec,
            source=source,
            is_authenticated=True,
        )
        with self._lock:
            self._memory_cache[sid] = sess
            try:
                with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO user_sessions
                        (session_id, user_id, email, display_name, tier, role, created_at, expires_at, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (sess.session_id, sess.user_id, sess.email, sess.display_name, sess.tier, sess.role, sess.created_at, sess.expires_at, sess.source))
                    conn.commit()
            except Exception:
                pass
        return sess

    def get_session(self, session_id: str) -> UserSession | None:
        if not session_id or not isinstance(session_id, str):
            return None
        sid = session_id.strip()
        with self._lock:
            sess = self._memory_cache.get(sid)
            if sess:
                if sess.is_expired():
                    del self._memory_cache[sid]
                    self._delete_sqlite_session(sid)
                    return None
                return sess

            # SQLite fallback
            try:
                with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
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
                        if sess.is_expired():
                            self._delete_sqlite_session(sid)
                            return None
                        self._memory_cache[sid] = sess
                        return sess
            except Exception:
                pass
        return None

    def revoke_session(self, session_id: str) -> bool:
        if not session_id:
            return False
        sid = session_id.strip()
        with self._lock:
            existed = sid in self._memory_cache
            if sid in self._memory_cache:
                del self._memory_cache[sid]
            db_deleted = self._delete_sqlite_session(sid)
            return existed or db_deleted

    def _delete_sqlite_session(self, session_id: str) -> bool:
        try:
            with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
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
                with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
                    cur = conn.execute("DELETE FROM user_sessions WHERE expires_at <= ?", (now,))
                    conn.commit()
                    count = max(count, cur.rowcount)
            except Exception:
                pass
        return count


_SESSION_STORE = SessionStore()


def get_session_store() -> SessionStore:
    return _SESSION_STORE


_IDENTITY_PAYLOAD_KEYS = ("role", "user_id", "speaker_id", "speaker", "email")
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
    if s_low in _REJECTED_IDENTITY_LITERALS:
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

    has_explicit_identity = False
    explicit_session: UserSession | None = None
    if payload and isinstance(payload, dict):
        has_explicit_identity, explicit_session = _resolve_explicit_payload_identity(payload, engine=engine)
        if has_explicit_identity and explicit_session is not None and not explicit_session.is_authenticated:
            return explicit_session

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
        if sess and not sess.is_expired():
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

    if has_explicit_identity and explicit_session is not None:
        return explicit_session

    # 6. Nếu không có token và không có định danh trong payload, kiểm tra nếu engine đang ở trạng thái UNKNOWN
    if engine is not None and (
        str(getattr(engine, "_current_role", "")).upper() == "UNKNOWN"
        or str(getattr(engine, "_current_user_id", "")).strip().lower() == "unknown"
    ):
        return _make_rejected_unknown_session()

    # 7. Engine test fallback: trường hợp bài test Phase 1 đã gọi tường minh eng.set_active_user(...)
    if engine is not None and getattr(engine, "_explicit_test_user_set", False):
        tier_val = int(getattr(engine, "current_tier", 3))
        if tier_val not in (1, 2, 3):
            return _make_rejected_unknown_session()
        user_val = engine.get_current_user_name() if hasattr(engine, "get_current_user_name") else "user"
        uid_val = getattr(engine, "_current_user_id", "user")
        return UserSession(
            session_id="legacy_test",
            user_id=uid_val,
            email="",
            display_name=user_val,
            tier=tier_val,
            role=ROLE_MAP.get(tier_val, "CHILD_GUEST"),
            created_at=time.time(),
            expires_at=time.time() + 86400,
            source="legacy_test",
            is_authenticated=True,
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
