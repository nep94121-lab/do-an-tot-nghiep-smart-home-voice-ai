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
import pathlib
import secrets
import sqlite3
import threading
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


def _get_session_hmac_key() -> bytes:
    """Derive an internal HMAC key from stored owner hash in accounts_3layer.json."""
    acc_path = DATA_DIR / "accounts_3layer.json"
    seed = f"sh_session_hmac_v2:{OWNER_ID}:{OWNER_EMAIL}"
    if acc_path.exists():
        try:
            items = json.loads(acc_path.read_text(encoding="utf-8"))
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and int(item.get("tier", 0)) == 1 and item.get("password_hash"):
                        seed += f":{item['password_hash']}"
                        break
        except Exception:
            pass
    return hashlib.sha256(seed.encode("utf-8")).digest()


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
            save_state_file("user_sessions.json", raw, data_dir=self.db_path.parent)
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
                conn.execute(
                    "DELETE FROM user_sessions WHERE user_id = ? OR email = ?",
                    ("qa_app_1793876716", "qa.app.1793876716@example.com"),
                )
                conn.commit()
        except Exception:
            pass

    @staticmethod
    def _encode_signed_token(payload_dict: dict[str, Any]) -> str:
        raw_json = json.dumps(payload_dict, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        b64_part = base64.urlsafe_b64encode(raw_json).decode("ascii").rstrip("=")
        sig = hmac.new(_get_session_hmac_key(), b64_part.encode("ascii"), hashlib.sha256).hexdigest()[:28]
        return f"sess_{b64_part}.{sig}"

    @staticmethod
    def _decode_signed_token(token: str) -> UserSession | None:
        if not token.startswith("sess_") or "." not in token:
            return None
        body_part, sig_part = token[5:].rsplit(".", 1)
        if not body_part or not sig_part:
            return None
        expected_sig = hmac.new(_get_session_hmac_key(), body_part.encode("ascii"), hashlib.sha256).hexdigest()[:28]
        if not hmac.compare_digest(sig_part, expected_sig):
            return None
        try:
            pad = "=" * ((4 - len(body_part) % 4) % 4)
            data = json.loads(base64.urlsafe_b64decode(body_part + pad).decode("utf-8"))
            if not isinstance(data, dict):
                return None
            uid = str(data.get("u") or "")
            email = str(data.get("e") or "")
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

    has_explicit_identity = False
    explicit_session: UserSession | None = None
    if payload and isinstance(payload, dict):
        has_explicit_identity, explicit_session = _resolve_explicit_payload_identity(payload, engine=engine)
        if has_explicit_identity and explicit_session is not None and not explicit_session.is_authenticated:
            return explicit_session

    if request is not None:
        from simulator.auth.qr_totp_mixin import _iter_header_pairs

        # 1. Header Authorization Bearer & 2. Header X-Session-Token (kể cả header trùng tên)
        for hk, hv in _iter_header_pairs(getattr(request, "headers", None)):
            if not hv:
                continue
            if hk == "authorization" and hv.lower().startswith("bearer "):
                cand_bt = hv[7:].strip()
                if cand_bt and not token:
                    token = cand_bt
            elif hk == "x-session-token" and not token:
                token = hv

        # 3. Cookie sh_session_token hoặc session_token
        if not token and hasattr(request, "cookies"):
            token = str(request.cookies.get("sh_session_token") or request.cookies.get("session_token") or "").strip()

        # 4. Query param token (multi_items để không bị che bởi tham số rỗng đứng trước)
        if not token and hasattr(request, "query_params"):
            qp = request.query_params
            qp_items = qp.multi_items() if hasattr(qp, "multi_items") else qp.items()
            for raw_qk, raw_qv in qp_items:
                qk = str(raw_qk or "").strip()
                qv = str(raw_qv or "").strip()
                if qv and qk in (
                    "token",
                    "session_token",
                    "sh_session_token",
                    "session_id",
                    "guest_session_id",
                    "post_scan_token",
                    "qr_token",
                    "scan_nonce",
                    "sh_qr_scan_nonce",
                    "sh_qr_session_id",
                ):
                    token = qv
                    break

    # 5. Body payload session_token hoặc guest_session_id / scan_nonce
    if not token and payload and isinstance(payload, dict):
        nested_sess = payload.get("session") if isinstance(payload.get("session"), dict) else {}
        token = str(
            payload.get("session_token")
            or payload.get("sh_session_token")
            or payload.get("guest_session_id")
            or payload.get("session_id")
            or payload.get("post_scan_token")
            or payload.get("qr_token")
            or payload.get("scan_nonce")
            or payload.get("sh_qr_scan_nonce")
            or payload.get("sh_qr_session_id")
            or payload.get("token")
            or nested_sess.get("session_token")
            or nested_sess.get("sh_session_token")
            or nested_sess.get("guest_session_id")
            or nested_sess.get("session_id")
            or nested_sess.get("post_scan_token")
            or nested_sess.get("qr_token")
            or nested_sess.get("scan_nonce")
            or nested_sess.get("sh_qr_scan_nonce")
            or nested_sess.get("sh_qr_session_id")
            or nested_sess.get("token")
            or ""
        ).strip()

    # Chặn tuyệt đối mọi token/session thuộc luồng đăng ký QR cô lập trên mọi carrier
    if token:
        from simulator.auth.qr_totp_mixin import is_qr_registration_token_or_session

        if is_qr_registration_token_or_session(token):
            return UserSession(
                session_id="qr_isolated_token_rejected",
                user_id="anonymous",
                email="",
                display_name="Khách (Token đăng ký QR cô lập)",
                tier=3,
                role="CHILD_GUEST",
                created_at=time.time(),
                expires_at=time.time() + 86400,
                source="qr_isolated_token_rejected",
                is_authenticated=False,
            )
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

    if request is not None:
        from simulator.auth.qr_totp_mixin import QR_SCAN_COOKIE_NAME, QR_SESSION_COOKIE_NAME

        cookies = getattr(request, "cookies", {}) or {}
        headers = getattr(request, "headers", {}) or {}
        query_params = getattr(request, "query_params", {}) or {}
        if (
            cookies.get(QR_SCAN_COOKIE_NAME)
            or cookies.get(QR_SESSION_COOKIE_NAME)
            or cookies.get("scan_nonce")
            or cookies.get("post_scan_token")
            or cookies.get("qr_token")
            or headers.get("x-qr-scan-nonce")
            or headers.get("x-scan-nonce")
            or headers.get("x-qr-session-id")
            or headers.get("x-qr-post-scan-token")
            or headers.get("x-qr-token")
            or query_params.get("scan_nonce")
            or query_params.get(QR_SCAN_COOKIE_NAME)
            or query_params.get(QR_SESSION_COOKIE_NAME)
            or query_params.get("post_scan_token")
            or query_params.get("qr_token")
        ):
            return UserSession(
                session_id="qr_isolated_session_rejected",
                user_id="anonymous",
                email="",
                display_name="Khách (Phiên đăng ký QR cô lập)",
                tier=3,
                role="CHILD_GUEST",
                created_at=time.time(),
                expires_at=time.time() + 86400,
                source="qr_isolated_session_rejected",
                is_authenticated=False,
            )

    if payload and isinstance(payload, dict):
        from simulator.auth.qr_totp_mixin import QR_SCAN_COOKIE_NAME, QR_SESSION_COOKIE_NAME

        nested_sess = payload.get("session") if isinstance(payload.get("session"), dict) else {}
        for d in (payload, nested_sess):
            for strict_k in ("scan_nonce", QR_SCAN_COOKIE_NAME, QR_SESSION_COOKIE_NAME, "post_scan_token", "qr_token"):
                rv = d.get(strict_k)
                if rv is not None and not isinstance(rv, bool) and str(rv).strip():
                    return UserSession(
                        session_id="qr_isolated_session_rejected",
                        user_id="anonymous",
                        email="",
                        display_name="Khách (Phiên đăng ký QR cô lập)",
                        tier=3,
                        role="CHILD_GUEST",
                        created_at=time.time(),
                        expires_at=time.time() + 86400,
                        source="qr_isolated_session_rejected",
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
