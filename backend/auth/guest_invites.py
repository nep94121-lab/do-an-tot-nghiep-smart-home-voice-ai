"""Kho mã mời khách có chữ ký HMAC: tạo, hết hạn, thu hồi, đổi lấy phiên (cấp 2/3)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from typing import Any

from backend.auth.security_state import (
    SecurityStateUnavailable,
    _sqlite_security_enabled,
    atomic_security,
    cloud_required,
    load_security_state,
    save_security_state,
)

from backend.auth.session_store import (
    SessionStore,
    UserSession,
    _get_session_hmac_key,
    get_session_store,
    session_is_current,
)

INVITE_TTL_DEFAULT_SEC = 600
INVITE_TTL_MIN_SEC = 60
INVITE_TTL_MAX_SEC = 31536000
INVITE_DURATION_PRESETS: dict[str, tuple[int, str]] = {
    "10m": (600, "10 phút"),
    "1h": (3600, "1 giờ"),
    "1d": (86400, "1 ngày"),
    "2d": (172800, "2 ngày"),
    "3d": (259200, "3 ngày"),
    "1w": (604800, "1 tuần"),
    "7d": (604800, "7 ngày"),
    "1m": (2592000, "1 tháng"),
    "30d": (2592000, "30 ngày"),
    "1y": (31536000, "1 năm"),
    "365d": (31536000, "1 năm"),
}
_TTL_TO_CODE_LABEL: dict[int, tuple[str, str]] = {
    600: ("10m", "10 phút"),
    3600: ("1h", "1 giờ"),
    86400: ("1d", "1 ngày"),
    172800: ("2d", "2 ngày"),
    259200: ("3d", "3 ngày"),
    604800: ("1w", "1 tuần"),
    2592000: ("1m", "1 tháng"),
    31536000: ("1y", "1 năm"),
}
_INVITE_PREFIX = "inv_"
_LOCK = threading.RLock()
_CACHE: dict[str, dict[str, Any]] | None = None
_CACHE_DIR: str | None = None
_ROLES = {2: "MEMBER", 3: "CHILD_GUEST"}


def resolve_invite_duration(
    duration_code: str | None = None,
    ttl_sec: int | None = None,
) -> tuple[str, str, int]:
    """Chuẩn hóa duration_code (1d/2d/1w/1m/1y/10m/1h/3d/7d/30d/365d) và ttl_sec."""
    code_raw = str(duration_code or "").strip().lower()
    if code_raw:
        if code_raw not in INVITE_DURATION_PRESETS:
            raise ValueError(
                "Thời hạn mã mời không hợp lệ (hỗ trợ: 10m, 1h, 1d, 2d, 1w, 1m, 1y)."
            )
        preset_ttl, label = INVITE_DURATION_PRESETS[code_raw]
        ttl = int(ttl_sec) if ttl_sec is not None else preset_ttl
        ttl = max(INVITE_TTL_MIN_SEC, min(INVITE_TTL_MAX_SEC, ttl))
        canonical_code = {"7d": "1w", "30d": "1m", "365d": "1y"}.get(code_raw, code_raw)
        return canonical_code, label, ttl

    raw_ttl = int(INVITE_TTL_DEFAULT_SEC if ttl_sec is None else ttl_sec)
    ttl = max(INVITE_TTL_MIN_SEC, min(INVITE_TTL_MAX_SEC, raw_ttl))
    if ttl in _TTL_TO_CODE_LABEL:
        return _TTL_TO_CODE_LABEL[ttl][0], _TTL_TO_CODE_LABEL[ttl][1], ttl
    if ttl % 86400 == 0:
        days = ttl // 86400
        return f"{days}d", f"{days} ngày", ttl
    if ttl % 3600 == 0:
        hours = ttl // 3600
        return f"{hours}h", f"{hours} giờ", ttl
    mins = max(1, ttl // 60)
    return f"{mins}m", f"{mins} phút", ttl


def _data_dir():
    store = get_session_store()
    return store.db_path.parent


def _load() -> dict[str, dict[str, Any]]:
    global _CACHE, _CACHE_DIR
    ddir = _data_dir()
    ddir_key = str(ddir)
    bypass_mem_cache = (
        cloud_required()
        or _sqlite_security_enabled()
        or bool(os.environ.get("SIMULATOR_SECURITY_STATE_DIR", "").strip())
    )
    if _CACHE is not None and _CACHE_DIR == ddir_key and not bypass_mem_cache:
        return {key: dict(value) for key, value in _CACHE.items()}
    data: dict[str, dict[str, Any]] = {}
    try:
        raw = load_security_state("guest_invites.json", ddir)
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
    _CACHE_DIR = ddir_key
    return data


def _save(data: dict[str, dict[str, Any]]) -> None:
    global _CACHE, _CACHE_DIR
    ddir = _data_dir()
    safe_items: list[dict[str, Any]] = []
    for item in data.values():
        if isinstance(item, dict):
            cleaned = dict(item)
            cleaned.pop("token", None)
            safe_items.append(cleaned)
    payload = json.dumps({"invites": safe_items}, ensure_ascii=False).encode("utf-8")
    save_security_state("guest_invites.json", payload, ddir)
    if (
        not cloud_required()
        and not os.environ.get("SIMULATOR_SECURITY_STATE_DIR", "").strip()
        and not _sqlite_security_enabled()
    ):
        try:
            from backend.auth.sqlite_security_repo import save_invites_sqlite

            save_invites_sqlite(payload, ddir)
        except Exception:
            pass
    _CACHE = data
    _CACHE_DIR = str(ddir)


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
    ttl_sec: int | None = None,
    duration_code: str | None = None,
    guest_name: str = "",
    host_origin: str = "",
) -> dict[str, Any]:
    guest_tier = normalize_guest_tier(tier)
    if guest_tier is None:
        raise ValueError("Cấp khách chỉ được phép là 2 hoặc 3.")
    dur_code, dur_label, ttl = resolve_invite_duration(duration_code=duration_code, ttl_sec=ttl_sec)
    clean_guest_name = str(guest_name or "").strip()[:80]
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
            "d": dur_code,
        }
    )
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    record = {
        "jti": jti,
        "token_hash": token_hash,
        "tier": guest_tier,
        "role": _ROLES[guest_tier],
        "duration_code": dur_code,
        "duration_label": dur_label,
        "duration_seconds": ttl,
        "ttl_sec": ttl,
        "guest_name": clean_guest_name,
        "label": clean_guest_name or dur_label,
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
        "duration_code": dur_code,
        "duration_label": dur_label,
        "duration_seconds": ttl,
        "ttl_sec": ttl,
        "guest_name": clean_guest_name,
        "created_at": now,
        "expires_at": expires_at,
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
    now = time.time()
    if _sqlite_security_enabled():
        from backend.auth.sqlite_security_repo import revoke_invite_sqlite

        with _LOCK:
            res = revoke_invite_sqlite(jti=key, revoked_at=now, data_dir=_data_dir())
            if _CACHE is not None and key in _CACHE and res.get("ok"):
                _CACHE[key]["revoked"] = True
                _CACHE[key]["revoked_at"] = now
            return res
    with _LOCK:
        data = _load()
        record = data.get(key)
        if record is None:
            return {"ok": False, "error": "not_found"}
        record["revoked"] = True
        record["revoked_at"] = now
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


def is_session_bound_to_invite(sess: Any, jti: str) -> bool:
    if sess is None or not jti:
        return False
    if not bool(getattr(sess, "is_authenticated", False)):
        return False
    if str(getattr(sess, "source", "") or "") != f"guest_invite:{jti}":
        return False
    return bool(session_is_current(sess))


def inspect_token(token: str, *, existing_session: Any | None = None) -> dict[str, Any]:
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
    if int(record.get("redeem_count") or 0) >= 1 and not is_session_bound_to_invite(existing_session, jti):
        return {
            "ok": False,
            "valid": False,
            "reason": "used",
            "invite_id": jti,
            "expires_at": expires_at,
            "error": "Mã QR đã được sử dụng.",
        }
    tier = int(record.get("tier") or payload.get("t") or 3)
    dur_code = str(record.get("duration_code") or payload.get("d") or "").strip()
    dur_label = str(record.get("duration_label") or "").strip()
    dur_sec = int(record.get("duration_seconds") or record.get("ttl_sec") or 0) or max(
        60, int(expires_at - float(record.get("created_at") or now))
    )
    if not dur_code or not dur_label:
        c2, l2, _ = resolve_invite_duration(duration_code=dur_code or None, ttl_sec=dur_sec)
        dur_code = dur_code or c2
        dur_label = dur_label or l2
    return {
        "ok": True,
        "valid": True,
        "reason": "ok",
        "invite_id": jti,
        "tier": tier,
        "role": str(record.get("role") or _ROLES.get(tier, "CHILD_GUEST")),
        "duration_code": dur_code,
        "duration_label": dur_label,
        "duration_seconds": dur_sec,
        "guest_name": str(record.get("guest_name") or "").strip(),
        "expires_at": expires_at,
        "ttl_remaining_sec": max(0, int(expires_at - now)),
    }


@atomic_security("guest_invites.json")
def _claim_invite_redemption(token: str) -> dict[str, Any]:
    payload = _decode_token(token)
    if payload is None:
        return {"ok": False, "valid": False, "reason": "invalid", "error": "Mã mời không hợp lệ."}
    jti = str(payload.get("jti") or "")
    exp = float(payload.get("x") or 0.0)
    if not jti:
        return {"ok": False, "valid": False, "reason": "invalid", "error": "Mã mời không hợp lệ."}
    now = time.time()
    if _sqlite_security_enabled():
        from backend.auth.sqlite_security_repo import claim_invite_sqlite

        with _LOCK:
            record = claim_invite_sqlite(jti=jti, exp=exp, now=now, data_dir=_data_dir())
            if not record.get("ok"):
                return record
            if _CACHE is not None and jti in _CACHE:
                _CACHE[jti]["redeem_count"] = 1
                _CACHE[jti]["last_redeem_at"] = now
            expires_at = float(record.get("expires_at") or exp)
            tier = int(record.get("tier") or payload.get("t") or 3)
            dur_code = str(record.get("duration_code") or payload.get("d") or "").strip()
            dur_label = str(record.get("duration_label") or "").strip()
            dur_sec = int(record.get("duration_seconds") or 0) or max(
                60, int(expires_at - float(record.get("created_at") or now))
            )
            if not dur_code or not dur_label:
                c2, l2, _ = resolve_invite_duration(duration_code=dur_code or None, ttl_sec=dur_sec)
                dur_code = dur_code or c2
                dur_label = dur_label or l2
            return {
                "ok": True,
                "valid": True,
                "reason": "ok",
                "invite_id": jti,
                "tier": tier,
                "role": str(record.get("role") or _ROLES.get(tier, "CHILD_GUEST")),
                "duration_code": dur_code,
                "duration_label": dur_label,
                "duration_seconds": dur_sec,
                "guest_name": str(record.get("guest_name") or "").strip(),
                "expires_at": expires_at,
                "ttl_remaining_sec": max(0, int(expires_at - now)),
            }

    with _LOCK:
        data = _load()
        record = data.get(jti)
        if record is None:
            return {"ok": False, "valid": False, "reason": "unknown", "error": "Mã mời không tồn tại hoặc đã hết hạn."}
        if record.get("revoked"):
            return {"ok": False, "valid": False, "reason": "revoked", "invite_id": jti, "error": "Mã mời đã bị thu hồi."}
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
        if int(record.get("redeem_count") or 0) >= 1:
            return {
                "ok": False,
                "valid": False,
                "reason": "used",
                "invite_id": jti,
                "expires_at": expires_at,
                "error": "Mã QR đã được sử dụng.",
            }
        record["redeem_count"] = 1
        record["last_redeem_at"] = now
        data[jti] = record
        _save(data)
    tier = int(record.get("tier") or payload.get("t") or 3)
    dur_code = str(record.get("duration_code") or payload.get("d") or "").strip()
    dur_label = str(record.get("duration_label") or "").strip()
    dur_sec = int(record.get("duration_seconds") or record.get("ttl_sec") or 0) or max(
        60, int(expires_at - float(record.get("created_at") or now))
    )
    if not dur_code or not dur_label:
        c2, l2, _ = resolve_invite_duration(duration_code=dur_code or None, ttl_sec=dur_sec)
        dur_code = dur_code or c2
        dur_label = dur_label or l2
    return {
        "ok": True,
        "valid": True,
        "reason": "ok",
        "invite_id": jti,
        "tier": tier,
        "role": str(record.get("role") or _ROLES.get(tier, "CHILD_GUEST")),
        "duration_code": dur_code,
        "duration_label": dur_label,
        "duration_seconds": dur_sec,
        "guest_name": str(record.get("guest_name") or "").strip(),
        "expires_at": expires_at,
        "ttl_remaining_sec": max(0, int(expires_at - now)),
    }


@atomic_security("guest_invites.json")
def _rollback_invite_redemption(jti: str) -> None:
    key = str(jti or "").strip()
    if not key:
        return
    if _sqlite_security_enabled():
        from backend.auth.sqlite_security_repo import rollback_invite_claim_sqlite

        with _LOCK:
            rollback_invite_claim_sqlite(jti=key, data_dir=_data_dir())
            if _CACHE is not None and key in _CACHE:
                _CACHE[key]["redeem_count"] = max(0, int(_CACHE[key].get("redeem_count") or 0) - 1)
                if _CACHE[key]["redeem_count"] == 0:
                    _CACHE[key].pop("last_redeem_at", None)
        return
    with _LOCK:
        data = _load()
        record = data.get(key)
        if record is None or record.get("revoked"):
            return
        record["redeem_count"] = max(0, int(record.get("redeem_count") or 0) - 1)
        if record["redeem_count"] == 0:
            record.pop("last_redeem_at", None)
        data[key] = record
        _save(data)


def redeem_token(
    token: str,
    store: SessionStore | None = None,
    *,
    existing_session: Any | None = None,
) -> dict[str, Any]:
    if existing_session is not None:
        checked_existing = inspect_token(token, existing_session=existing_session)
        if not checked_existing.get("valid"):
            return checked_existing
        jti_existing = str(checked_existing["invite_id"])
        rec_existing = get_invite(jti_existing)
        if rec_existing is not None and int(rec_existing.get("redeem_count") or 0) >= 1 and is_session_bound_to_invite(existing_session, jti_existing):
            return {**checked_existing, "reused": True, "session": existing_session}

    checked = _claim_invite_redemption(token)
    if not checked.get("valid"):
        return checked
    jti = str(checked["invite_id"])
    guest_display = str(checked.get("guest_name") or "").strip() or f"Guest tier {checked['tier']}"
    try:
        session = (store or get_session_store()).create_session(
            user_id=f"guest_{jti[:12]}", email="", display_name=guest_display,
            tier=int(checked["tier"]), role=str(checked["role"]),
            ttl_sec=max(1, int(checked["expires_at"] - time.time())), source=f"guest_invite:{jti}",
        )
    except Exception:
        _rollback_invite_redemption(jti)
        raise
    return {**checked, "session": session}


def reset_invite_store_for_tests() -> None:
    global _CACHE, _CACHE_DIR
    with _LOCK:
        _CACHE = {}
        _CACHE_DIR = str(_data_dir())
        try:
            from backend.auth.sqlite_security_repo import reset_invites_sqlite

            reset_invites_sqlite(_data_dir())
        except Exception:
            pass
        _save({})
