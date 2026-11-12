"""Owner 4-digit PIN for creating guest invites. Hashed at rest, lock after 5 failures."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from typing import Any

from simulator.auth.security_state import cloud_required, load_security_state, save_security_state, SecurityStateUnavailable, atomic_security

OWNER_PIN_FILE = "owner_pin.json"
MAX_FAILURES = 5
OTP_TTL_SEC = 300
OTP_DIGITS = 6
OWNER_RESET_EMAIL = "nep94121@gmail.com"

_LOCK = threading.RLock()
_CACHE: dict[str, Any] | None = None


def _data_dir():
    from simulator.auth.session_store import get_session_store

    return get_session_store().db_path.parent


def _load() -> dict[str, Any]:
    global _CACHE
    if _CACHE is not None and not cloud_required():
        return dict(_CACHE)
    data: dict[str, Any] = {}
    try:
        raw = load_security_state(OWNER_PIN_FILE, _data_dir())
        if raw:
            parsed = json.loads(raw.decode("utf-8"))
            if isinstance(parsed, dict):
                data = parsed
    except SecurityStateUnavailable:
        raise
    except Exception as exc:
        raise SecurityStateUnavailable("Invalid security state") from exc
    _CACHE = dict(data)
    return data


def _save(data: dict[str, Any]) -> None:
    global _CACHE
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    save_security_state(OWNER_PIN_FILE, payload, _data_dir())
    _CACHE = dict(data)


def normalize_pin(value: Any) -> str | None:
    text = str(value or "").strip()
    if len(text) == 4 and text.isascii() and text.isdigit():
        return text
    return None


def _hash_secret(secret: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 120_000)
    return salt.hex(), digest.hex()


def _verify_secret(secret: str, salt_hex: str, hash_hex: str) -> bool:
    if not secret or not salt_hex or not hash_hex:
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(digest, expected)


def pin_status() -> dict[str, Any]:
    with _LOCK:
        data = _load()
    failed = int(data.get("failed_attempts") or 0)
    locked = bool(data.get("locked")) or failed >= MAX_FAILURES
    return {
        "ok": True,
        "pin_set": bool(data.get("pin_hash")),
        "locked": locked,
        "failed_attempts": failed,
        "max_failures": MAX_FAILURES,
    }


def _set_pin_record(data: dict[str, Any], pin: str) -> dict[str, Any]:
    salt, hashed = _hash_secret(pin)
    data["pin_salt"] = salt
    data["pin_hash"] = hashed
    data["failed_attempts"] = 0
    data["locked"] = False
    data["updated_at"] = time.time()
    data.pop("otp_hash", None)
    data.pop("otp_salt", None)
    data.pop("otp_expires_at", None)
    data.pop("otp_used", None)
    return data


@atomic_security("owner_pin.json")
def setup_or_replace_pin(pin: str, pin_confirm: str, *, allow_replace: bool = False) -> dict[str, Any]:
    p1 = normalize_pin(pin)
    p2 = normalize_pin(pin_confirm)
    if not p1 or not p2:
        return {"ok": False, "status_code": 400, "error": "Mã PIN phải gồm đúng 4 chữ số."}
    if p1 != p2:
        return {"ok": False, "status_code": 400, "error": "Hai lần nhập PIN không khớp nhau."}
    with _LOCK:
        data = _load()
        if data.get("pin_hash") and not allow_replace:
            return {"ok": False, "status_code": 409, "error": "PIN đã được đặt. Hãy nhập PIN hiện tại, hoặc dùng Quên PIN."}
        _set_pin_record(data, p1)
        _save(data)
    return {"ok": True, "pin_set": True, "locked": False, "message": "Đã lưu mã PIN."}


@atomic_security("owner_pin.json")
def verify_pin(pin: str) -> dict[str, Any]:
    p = normalize_pin(pin)
    with _LOCK:
        data = _load()
        if not data.get("pin_hash"):
            return {"ok": False, "status_code": 400, "needs_pin_setup": True, "error": "Hãy đặt mã PIN 4 số lần đầu trước khi tạo mã mời."}
        failed = int(data.get("failed_attempts") or 0)
        if data.get("locked") or failed >= MAX_FAILURES:
            data["locked"] = True
            _save(data)
            return {
                "ok": False,
                "status_code": 423,
                "locked": True,
                "failed_attempts": max(failed, MAX_FAILURES),
                "error": "PIN đã bị khóa sau 5 lần nhập sai. Hãy dùng Quên PIN để nhận mã xác nhận qua Gmail.",
            }
        if not p or not _verify_secret(p, str(data.get("pin_salt") or ""), str(data.get("pin_hash") or "")):
            failed += 1
            data["failed_attempts"] = failed
            if failed >= MAX_FAILURES:
                data["locked"] = True
            _save(data)
            left = max(0, MAX_FAILURES - failed)
            locked_now = bool(data.get("locked"))
            return {
                "ok": False,
                "status_code": 423 if locked_now else 403,
                "locked": locked_now,
                "failed_attempts": failed,
                "error": "PIN không đúng." + (" PIN đã bị khóa." if locked_now else f" Còn {left} lần thử."),
            }
        data["failed_attempts"] = 0
        data["locked"] = False
        _save(data)
    return {"ok": True, "locked": False}


@atomic_security("owner_pin.json")
def issue_reset_otp() -> tuple[dict[str, Any], str]:
    code = f"{secrets.randbelow(1_000_000):06d}"
    salt, hashed = _hash_secret(code)
    expires = time.time() + OTP_TTL_SEC
    with _LOCK:
        data = _load()
        if time.time() - float(data.get("otp_issued_at") or 0) < 60:
            return {"ok": False, "status_code": 429, "error": "Hãy chờ 60 giây trước khi gửi lại mã."}, ""
        data["otp_salt"] = salt
        data["otp_hash"] = hashed
        data["otp_expires_at"] = expires
        data["otp_used"] = False
        data["otp_failed_attempts"] = 0
        data["otp_issued_at"] = time.time()
        _save(data)
    result: dict[str, Any] = {
        "ok": True,
        "sent_to": OWNER_RESET_EMAIL,
        "expires_in_sec": OTP_TTL_SEC,
        "message": f"Đã gửi mã xác nhận một lần tới {OWNER_RESET_EMAIL}. Mã hết hạn sau 5 phút.",
    }
    if os.environ.get("SIMULATOR_OFFLINE_SANDBOX") == "1" and not os.environ.get("VERCEL"):
        result["otp_code_for_test"] = code
    return result, code


def allowed_reset_recipient(email: str) -> bool:
    return str(email or "").strip().lower() == OWNER_RESET_EMAIL


def send_reset_email(otp_code: str) -> dict[str, Any]:
    """Send the PIN-reset code only to the owner Gmail allowlist address."""
    if os.environ.get("SIMULATOR_OFFLINE_SANDBOX") == "1" and not os.environ.get("VERCEL"):
        return {"ok": True, "method": "sandbox", "sent": False}
    try:
        from simulator.auth_3layer import get_auth_3layer_manager

        delivery = get_auth_3layer_manager().send_real_gmail_otp(
            target_email=OWNER_RESET_EMAIL,
            otp_code=otp_code,
            display_name="Chủ nhà",
        )
        return {"ok": bool(delivery.get("sent_real_gmail")), "sent": bool(delivery.get("sent_real_gmail"))}
    except Exception:
        return {"ok": False, "error": "Không gửi được email xác nhận."}


@atomic_security("owner_pin.json")
def reset_pin_with_otp(otp: str, pin: str, pin_confirm: str) -> dict[str, Any]:
    code = str(otp or "").strip()
    if not (len(code) == OTP_DIGITS and code.isdigit()):
        return {"ok": False, "status_code": 400, "error": "Mã xác nhận không hợp lệ."}
    p1 = normalize_pin(pin)
    p2 = normalize_pin(pin_confirm)
    if not p1 or not p2:
        return {"ok": False, "status_code": 400, "error": "Mã PIN mới phải gồm đúng 4 chữ số."}
    if p1 != p2:
        return {"ok": False, "status_code": 400, "error": "Hai lần nhập PIN mới không khớp nhau."}
    with _LOCK:
        data = _load()
        if data.get("otp_used"):
            return {"ok": False, "status_code": 400, "error": "Mã xác nhận đã được dùng."}
        expires = float(data.get("otp_expires_at") or 0)
        if int(data.get("otp_failed_attempts") or 0) >= MAX_FAILURES:
            return {"ok": False, "status_code": 423, "error": "Mã xác nhận đã bị khóa. Hãy yêu cầu mã mới."}
        if expires <= time.time():
            return {"ok": False, "status_code": 400, "error": "Mã xác nhận đã hết hạn. Hãy gửi lại mã mới."}
        if not _verify_secret(code, str(data.get("otp_salt") or ""), str(data.get("otp_hash") or "")):
            data["otp_failed_attempts"] = int(data.get("otp_failed_attempts") or 0) + 1
            _save(data)
            return {"ok": False, "status_code": 403, "error": "Mã xác nhận không đúng."}
        data["otp_used"] = True
        _set_pin_record(data, p1)
        _save(data)
    return {"ok": True, "pin_set": True, "locked": False, "message": "Đã đặt lại mã PIN."}


def reset_owner_pin_store_for_tests() -> None:
    global _CACHE
    with _LOCK:
        _CACHE = {}
        _save({})
