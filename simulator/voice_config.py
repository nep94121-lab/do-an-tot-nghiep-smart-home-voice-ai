"""Centralized voice authentication and owner identity configuration."""

from __future__ import annotations

import json
import os
import pathlib
import re
from typing import Any

_CONFIG_PATH = pathlib.Path(__file__).resolve().parent / "config" / "voice_auth.json"

_FORBIDDEN_RESPONSE_KEYS = frozenset(
    {
        "voiceprint",
        "voiceprints",
        "voiceprint_json",
        "embedding",
        "embeddings",
        "deep_embedding",
        "deep_embedding_64d",
        "embedding_26d_json",
        "embedding_64d_json",
        "embedding_256d",
        "wespeaker_embedding",
        "wespeaker_samples",
        "sample_embeddings_256d",
        "neural_embedding",
        "baseline_embedding",
        "baseline_deep_embedding",
        "baseline_embedding_256d",
        "baseline_wespeaker_embedding",
        "formants_hz",
        "password",
        "passwords",
        "new_password",
        "confirm_password",
        "custom_password",
        "issued_password",
        "password_hash",
        "password_salt",
        "pin_hash",
        "password_plain_hint",
        "password_hint",
        "otp",
        "otp_code",
        "otp_input",
        "input_otp",
        "extracted_otp",
        "active_otp",
        "pending_otp",
        "pending_otps",
        "pending_guest_email_otps",
        "pending_invite_registrations",
        "active_sessions",
        "last_session",
    }
)

_FORBIDDEN_OVERVIEW_AND_LOG_KEYS = _FORBIDDEN_RESPONSE_KEYS | frozenset(
    {
        "code",
        "auth_otp",
        "otp_code_for_test",
        "otp_code_for_test_table",
        "demo_otp_preview",
        "issued_password_for_test",
        "mat_khau",
        "mat_khau_tam",
        "passwd",
        "passcode",
        "secret",
        "client_secret",
        "user_token",
    }
)

_SAFE_OVERVIEW_KEYS = frozenset(
    {
        "invite_code",
        "status_code",
        "duration_code",
        "role_code",
        "hex_code",
        "ir_code_id",
        "ir_remote_codes",
        "error_code",
        "otp_dispatched",
        "otp_verified",
    }
)

_OVERVIEW_SENSITIVE_KEY_RE = re.compile(
    r"(?:^|_)(?:otp|password|passwd|passcode|mat_khau|voiceprint|embedding|formant|pin_hash|password_hash|password_hint)(?:$|_)",
    re.IGNORECASE,
)

_THROWAWAY_QA_IDENTITIES = frozenset(
    {
        "qa_app_1793876716",
        "qa.app.1793876716@example.com",
    }
)


def is_throwaway_qa_identity(value: Any) -> bool:
    """Return True if value matches the throwaway QA account id/email that must be purged."""
    if value is None:
        return False
    s = str(value).strip().lower()
    if not s:
        return False
    return s in _THROWAWAY_QA_IDENTITIES


def load_voice_auth_config() -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if _CONFIG_PATH.exists():
        try:
            raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            raw = {}

    owner_id = os.environ.get("VOICE_AUTH_OWNER_ID", raw.get("owner_id", "tuan_anh")).strip()
    owner_email = os.environ.get("VOICE_AUTH_OWNER_EMAIL", raw.get("owner_email", "nep94121@gmail.com")).strip()
    owner_display_name = os.environ.get(
        "VOICE_AUTH_OWNER_DISPLAY_NAME",
        raw.get("owner_display_name", "Nguyễn Tuấn Anh"),
    ).strip()

    raw_role_map = raw.get("role_map") or {"1": "ADMIN", "2": "MEMBER", "3": "CHILD_GUEST"}
    role_map_int: dict[int, str] = {int(k): str(v) for k, v in raw_role_map.items()}

    raw_user_role_map = raw.get("user_role_map") or {
        "1": owner_id,
        "2": "thanh_vien_a",
        "3": "khach_c",
    }
    user_role_map_int: dict[int, str] = {int(k): str(v) for k, v in raw_user_role_map.items()}

    threshold_mel = float(os.environ.get("VOICE_AUTH_THRESHOLD_MEL", raw.get("threshold_mel", 0.88)))
    threshold_deep = float(os.environ.get("VOICE_AUTH_THRESHOLD_DEEP", raw.get("threshold_deep", 0.80)))
    threshold_wespeaker = float(
        os.environ.get("VOICE_AUTH_THRESHOLD_WESPEAKER", raw.get("threshold_wespeaker", 0.435))
    )
    threshold_wespeaker_tier1 = float(
        os.environ.get(
            "VOICE_AUTH_THRESHOLD_WESPEAKER_TIER1",
            raw.get("threshold_wespeaker_tier1", threshold_wespeaker),
        )
    )
    threshold_wespeaker_tier2 = float(
        os.environ.get(
            "VOICE_AUTH_THRESHOLD_WESPEAKER_TIER2",
            raw.get("threshold_wespeaker_tier2", 0.435),
        )
    )
    threshold_wespeaker_tier3 = float(
        os.environ.get(
            "VOICE_AUTH_THRESHOLD_WESPEAKER_TIER3",
            raw.get("threshold_wespeaker_tier3", 0.385),
        )
    )
    # Grant/revoke/enroll by voice need a higher score than ordinary commands (door/lights).
    # Tuned on held-out owner 08/09 (~0.72) vs stranger max official cosine (~0.41).
    threshold_wespeaker_privileged = float(
        os.environ.get(
            "VOICE_AUTH_THRESHOLD_WESPEAKER_PRIVILEGED",
            raw.get("threshold_wespeaker_privileged", 0.60),
        )
    )
    enrollment_required_samples = int(
        os.environ.get(
            "VOICE_AUTH_ENROLLMENT_SAMPLES",
            raw.get("enrollment_required_samples", 5),
        )
    )

    return {
        "owner_id": owner_id,
        "owner_email": owner_email,
        "owner_display_name": owner_display_name,
        "role_map": role_map_int,
        "role_map_str": {str(k): v for k, v in role_map_int.items()},
        "user_role_map": user_role_map_int,
        "threshold_mel": threshold_mel,
        "threshold_deep": threshold_deep,
        "threshold_wespeaker": threshold_wespeaker,
        "threshold_wespeaker_tier1": threshold_wespeaker_tier1,
        "threshold_wespeaker_tier2": threshold_wespeaker_tier2,
        "threshold_wespeaker_tier3": threshold_wespeaker_tier3,
        "threshold_wespeaker_privileged": threshold_wespeaker_privileged,
        "enrollment_required_samples": enrollment_required_samples,
    }


_CFG = load_voice_auth_config()

OWNER_ID: str = _CFG["owner_id"]
OWNER_EMAIL: str = _CFG["owner_email"]
OWNER_DISPLAY_NAME: str = _CFG["owner_display_name"]
ROLE_MAP: dict[int, str] = _CFG["role_map"]
USER_ROLE_MAP: dict[int, str] = _CFG["user_role_map"]
THRESHOLD_MEL: float = _CFG["threshold_mel"]
THRESHOLD_DEEP: float = _CFG["threshold_deep"]
THRESHOLD_WESPEAKER: float = _CFG["threshold_wespeaker"]
THRESHOLD_WESPEAKER_TIER1: float = _CFG["threshold_wespeaker_tier1"]
THRESHOLD_WESPEAKER_TIER2: float = _CFG["threshold_wespeaker_tier2"]
THRESHOLD_WESPEAKER_TIER3: float = _CFG["threshold_wespeaker_tier3"]
THRESHOLD_WESPEAKER_PRIVILEGED: float = _CFG["threshold_wespeaker_privileged"]
ENROLLMENT_REQUIRED_SAMPLES: int = _CFG["enrollment_required_samples"]


def get_tier_wespeaker_threshold(tier: int) -> float:
    """Return configurable WeSpeaker ResNet34 ONNX cosine threshold for a given permission tier."""
    t = int(tier)
    if t <= 1:
        return THRESHOLD_WESPEAKER_TIER1
    if t == 2:
        return THRESHOLD_WESPEAKER_TIER2
    return THRESHOLD_WESPEAKER_TIER3


def get_privileged_wespeaker_threshold() -> float:
    """Stricter WeSpeaker cosine required for voice grant/revoke/enroll."""
    return THRESHOLD_WESPEAKER_PRIVILEGED


def sanitize_api_payload(obj: Any) -> Any:
    """Recursively strip server-side voiceprints, embeddings, and password hashes
    before returning any payload in an HTTP response."""
    if isinstance(obj, dict):
        cleaned: dict[str, Any] = {}
        if "voiceprint" in obj and isinstance(obj.get("voiceprint"), dict):
            vp = obj["voiceprint"]
            cleaned.setdefault("voice_enrolled", bool(vp.get("enrolled", False)))
        for k, v in obj.items():
            k_str = str(k)
            if k_str == "password_hint":
                continue
            if k_str == "password_plain_hint":
                if v == "******":
                    cleaned[k] = v
                continue
            if k_str in _FORBIDDEN_RESPONSE_KEYS:
                continue
            cleaned[k] = sanitize_api_payload(v)
        return cleaned
    if isinstance(obj, list):
        return [sanitize_api_payload(item) for item in obj]
    return obj


def is_forbidden_overview_or_log_key(key: Any) -> bool:
    """Return True if a dictionary key is a sensitive OTP/code/password/voiceprint key
    that must be stripped from overview and log payloads."""
    k_low = str(key).strip().lower()
    if not k_low:
        return False
    if k_low in _SAFE_OVERVIEW_KEYS:
        return False
    if k_low in _FORBIDDEN_OVERVIEW_AND_LOG_KEYS:
        return True
    if _OVERVIEW_SENSITIVE_KEY_RE.search(k_low):
        return True
    if any(
        tok in k_low
        for tok in (
            "otp",
            "password",
            "passwd",
            "passcode",
            "mat_khau",
            "voiceprint",
            "embedding",
            "formant",
            "pin_hash",
        )
    ):
        return True
    if k_low == "code" or k_low.endswith("_code"):
        return True
    return False


def redact_otp_and_secrets_in_text(text: str) -> str:
    """Redact plaintext 6-digit OTP codes and password hints/values embedded in log or overview strings."""
    if not text or not isinstance(text, str):
        return text
    t = text
    # Redact password hints and inline quoted passwords
    t = re.sub(r"(Mật khẩu gợi ý:\s*)([^\s\)]+)", r"\1******", t, flags=re.IGNORECASE)
    t = re.sub(r"(mật khẩu\s+['\"])([^'\"]+)(['\"])", r"\1******\3", t, flags=re.IGNORECASE)
    t = re.sub(
        r"(\(Mã trong Gmail là:\s*\d{6}\))",
        "",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"(Mã trong Gmail là:\s*)\d{6}",
        r"\1[REDACTED]",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"((?:password|password_plain_hint|hint|secret|token|otp|otp_code|mat_khau)['\"]?\s*[:=]\s*['\"]?)(\d{6}|[^'\"\s,}]+)(['\"]?)",
        r"\1******\3",
        t,
        flags=re.IGNORECASE,
    )
    # Redact any 6-digit OTP inside strings mentioning OTP / verification codes
    t_low = t.lower()
    if any(
        kw in t_low
        for kw in (
            "otp",
            "mã xác thực",
            "mã xác nhận",
            "bảng test",
            "đặt lại mật khẩu",
            "quên mật khẩu",
            "lớp 1",
            "lớp 2",
        )
    ):
        t = re.sub(r"\(\d{6}\)", "([REDACTED])", t)
        t = re.sub(r"'\d{6}'", "'[REDACTED]'", t)
        t = re.sub(r"\b\d{6}\b", "[REDACTED]", t)
    return t.strip()


def sanitize_overview_and_logs_payload(obj: Any) -> Any:
    """Recursively strip otp/code/password/voiceprint keys and redact embedded OTP/password
    patterns from overview and logs payloads (including JSON-encoded details_json strings)."""
    if isinstance(obj, dict):
        cleaned: dict[str, Any] = {}
        if "account_id" in obj and "voiceprint" in obj and isinstance(obj.get("voiceprint"), dict):
            vp = obj["voiceprint"]
            cleaned.setdefault("voice_enrolled", bool(vp.get("enrolled", False)))
        for k, v in obj.items():
            k_str = str(k)
            if is_forbidden_overview_or_log_key(k_str):
                continue
            if k_str == "details_json" and isinstance(v, str):
                try:
                    parsed = json.loads(v)
                    sanitized_parsed = sanitize_overview_and_logs_payload(parsed)
                    cleaned[k] = json.dumps(sanitized_parsed, ensure_ascii=False)
                    continue
                except Exception:
                    cleaned[k] = redact_otp_and_secrets_in_text(v)
                    continue
            cleaned[k] = sanitize_overview_and_logs_payload(v)
        return cleaned
    if isinstance(obj, list):
        return [sanitize_overview_and_logs_payload(item) for item in obj]
    if isinstance(obj, str):
        return redact_otp_and_secrets_in_text(obj)
    return obj
