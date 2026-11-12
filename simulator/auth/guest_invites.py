"""Kho mã mời khách có chữ ký HMAC: tạo, hết hạn, thu hồi, đổi lấy phiên (cấp 2/3)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from typing import Any

from simulator.auth.security_state import cloud_required, load_security_state, save_security_state, SecurityStateUnavailable, atomic_security

from simulator.auth.session_store import (
    SessionStore,
    UserSession,
    _get_session_hmac_key,
    get_session_store,
)

INVITE_TTL_DEFAULT_SEC = 600
INVITE_TTL_MIN_SEC = 60
INVITE_TTL_MAX_SEC = 86400
_INVITE_PREFIX = "inv_"
_LOCK = threading.RLock()
_CACHE: dict[str, dict[str, Any]] | None = None
_ROLES = {2: "MEMBER", 3: "CHILD_GUEST"}


def _data_dir():
    store = get_session_store()
    return store.db_path.parent


def _load() -> dict[str, dict[str, Any]]:
    global _CACHE
    if _CACHE is not None and not cloud_required():
        return {key: dict(value) for key, value in _CACHE.items()}
    data: dict[str, dict[str, Any]] = {}
    try:
        raw = load_security_state("guest_invites.json", _data_dir())
        if raw:
            parsed = json.loads(raw.decode("utf-8"))
            items = parsed.get("invites") if isinstance(parsed, dict) else parsed
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get("jti"):
                        data[str(item["jti"])] = item
            elif isinstance(items, dict):
                for key, item in items.items():
                    if isinstance(item, dict):
                        data[str(item.get("jti") or key)] = item
    except SecurityStateUnavailable:
        raise
    except Exception as exc:
        raise SecurityStateUnavailable("Invalid security state") from exc
    _CACHE = data
    return data


def _save(data: dict[str, dict[str, Any]]) -> None:
    global _CACHE
    items = list(data.values())
    payload = json.dumps({"invites": items}, ensure_ascii=False).encode("utf-8")
    save_security_state("guest_invites.json", payload, _data_dir())
    _CACHE = data


def _encode_token(payload: dict[str, Any]) -> str:
    raw_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    b64_part = base64.urlsafe_b64encode(raw_json).decode("ascii").rstrip("=")
    sig = hmac.new(_get_session_hmac_key(), b"invite:" + b64_part.encode("ascii"), hashlib.sha256).hexdigest()[:28]
    return f"{_INVITE_PREFIX}{b64_part}.{sig}"


def _decode_token(token: str) -> dict[str, Any] | None:
    text = str(token or "").strip()
    if not text.startswith(_INVITE_PREFIX) or "." not in text:
        return None
    body_part, sig_part = text[len(_INVITE_PREFIX) :].rsplit(".", 1)
    if not body_part or not sig_part:
        return None
    expected = hmac.new(_get_session_hmac_key(), b"invite:" + body_part.encode("ascii"), hashlib.sha256).hexdigest()[:28]
    if not hmac.compare_digest(sig_part, expected):
        return None
    try:
        pad = "=" * ((4 - len(body_part) % 4) % 4)
        data = json.loads(base64.urlsafe_b64decode(body_part + pad).decode("utf-8"))
        if not isinstance(data, dict):
            return None
        if str(data.get("typ") or "") not in ("guest", "g"):
            return None
        return data
    except Exception:
        return None


def normalize_guest_tier(value: Any) -> int | None:
    try:
        tier = int(value)
    except (TypeError, ValueError):
        return None
    if tier in (2, 3):
        return tier
    return None


@atomic_security("guest_invites.json")
def create_invite(
    *,
    owner_user_id: str,
    tier: int,
    ttl_sec: int = INVITE_TTL_DEFAULT_SEC,
    host_origin: str = "",
) -> dict[str, Any]:
    guest_tier = normalize_guest_tier(tier)
    if guest_tier is None:
        raise ValueError("Cấp khách chỉ được phép là 2 hoặc 3.")
    ttl = int(ttl_sec or INVITE_TTL_DEFAULT_SEC)
    ttl = max(INVITE_TTL_MIN_SEC, min(INVITE_TTL_MAX_SEC, ttl))
    now = time.time()
    jti = secrets.token_hex(12)
    expires_at = now + ttl
    token = _encode_token(
        {
            "typ": "guest",
            "jti": jti,
            "t": guest_tier,
            "c": round(now, 3),
            "x": round(expires_at, 3),
            "o": str(owner_user_id or ""),
        }
    )
    record = {
        "jti": jti,
        "token": token,
        "tier": guest_tier,
        "role": _ROLES[guest_tier],
        "created_at": now,
        "expires_at": expires_at,
        "revoked": False,
        "revoked_at": 0.0,
        "owner_user_id": str(owner_user_id or ""),
        "redeem_count": 0,
    }
    with _LOCK:
        data = _load()
        data[jti] = record
        _save(data)
    path = f"/guest?token={token}"
    origin = str(host_origin or "").rstrip("/")
    url = f"{origin}{path}" if origin else path
    return {
        "ok": True,
        "invite_id": jti,
        "token": token,
        "tier": guest_tier,
        "role": _ROLES[guest_tier],
        "created_at": now,
        "expires_at": expires_at,
        "ttl_sec": ttl,
        "path": path,
        "url": url,
        "revoked": False,
    }


def get_invite(jti: str) -> dict[str, Any] | None:
    if not jti:
        return None
    with _LOCK:
        return _load().get(str(jti))


def list_invites(*, include_expired: bool = False) -> list[dict[str, Any]]:
    now = time.time()
    with _LOCK:
        items = list(_load().values())
    out = []
    for item in items:
        if not include_expired and float(item.get("expires_at") or 0) <= now and not item.get("revoked"):
            continue
        out.append(dict(item))
    out.sort(key=lambda row: float(row.get("created_at") or 0), reverse=True)
    return out


@atomic_security("guest_invites.json")
def _mark_invite_revoked(jti: str) -> dict[str, Any]:
    key = str(jti or "").strip()
    if not key:
        return {"ok": False, "error": "missing_invite_id"}
    with _LOCK:
        data = _load()
        record = data.get(key)
        if record is None:
            return {"ok": False, "error": "not_found"}
        record["revoked"] = True
        record["revoked_at"] = time.time()
        data[key] = record
        _save(data)
    return {"ok": True, "invite_id": key, "revoked": True}


def revoke_invite(jti: str, store: SessionStore | None = None) -> dict[str, Any]:
    result = _mark_invite_revoked(jti)
    if result.get("ok"):
        result["revoked_sessions"] = _revoke_bound_sessions(jti, store or get_session_store())
    return result


def _revoke_bound_sessions(jti: str, store: SessionStore) -> int:
    marker = f"guest_invite:{jti}"
    count = 0
    try:
        with store._lock:
            sids = [sid for sid, sess in store._memory_cache.items() if str(getattr(sess, "source", "")) == marker]
        for sid in sids:
            if store.revoke_session(sid):
                count += 1
    except Exception:
        return count
    return count


def inspect_token(token: str) -> dict[str, Any]:
    payload = _decode_token(token)
    if payload is None:
        return {"ok": False, "valid": False, "reason": "invalid", "error": "Mã mời không hợp lệ."}
    jti = str(payload.get("jti") or "")
    exp = float(payload.get("x") or 0.0)
    now = time.time()
    if not jti:
        return {"ok": False, "valid": False, "reason": "invalid", "error": "Mã mời không hợp lệ."}
    record = get_invite(jti)
    if record is None:
        return {"ok": False, "valid": False, "reason": "unknown", "error": "Mã mời không tồn tại hoặc đã hết hạn."}
    if record.get("revoked"):
        return {
            "ok": False,
            "valid": False,
            "reason": "revoked",
            "invite_id": jti,
            "error": "Mã mời đã bị thu hồi.",
        }
    expires_at = float(record.get("expires_at") or exp)
    if expires_at <= now or exp <= now:
        return {
            "ok": False,
            "valid": False,
            "reason": "expired",
            "invite_id": jti,
            "expires_at": expires_at,
            "error": "Mã mời đã hết hạn.",
        }
    tier = int(record.get("tier") or payload.get("t") or 3)
    return {
        "ok": True,
        "valid": True,
        "reason": "ok",
        "invite_id": jti,
        "tier": tier,
        "role": str(record.get("role") or _ROLES.get(tier, "CHILD_GUEST")),
        "expires_at": expires_at,
        "ttl_remaining_sec": max(0, int(expires_at - now)),
    }


@atomic_security("guest_invites.json")
def _claim_invite_redemption(token: str) -> dict[str, Any]:
    checked = inspect_token(token)
    if not checked.get("valid"):
        return checked
    with _LOCK:
        data = _load()
        record = data[checked["invite_id"]]
        record["redeem_count"] = int(record.get("redeem_count") or 0) + 1
        record["last_redeem_at"] = time.time()
        _save(data)
    return checked


def redeem_token(token: str, store: SessionStore | None = None) -> dict[str, Any]:
    checked = _claim_invite_redemption(token)
    if not checked.get("valid"):
        return checked
    jti = str(checked["invite_id"])
    session = (store or get_session_store()).create_session(
        user_id=f"guest_{jti[:12]}", email="", display_name=f"Guest tier {checked['tier']}",
        tier=int(checked["tier"]), role=str(checked["role"]),
        ttl_sec=max(1, int(checked["expires_at"] - time.time())), source=f"guest_invite:{jti}",
    )
    return {**checked, "session": session}


def reset_invite_store_for_tests() -> None:
    global _CACHE
    with _LOCK:
        _CACHE = {}
        _save({})
