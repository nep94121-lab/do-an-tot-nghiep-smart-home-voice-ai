"""Centralized voice authentication and owner identity configuration."""

from __future__ import annotations

import json
import os
import pathlib
from typing import Any

_CONFIG_PATH = pathlib.Path(__file__).resolve().parent / "config" / "voice_auth.json"

_FORBIDDEN_RESPONSE_KEYS = frozenset(
    {
        "voiceprint",
        "voiceprints",
        "embedding",
        "deep_embedding",
        "embedding_256d",
        "baseline_embedding",
        "baseline_deep_embedding",
        "baseline_embedding_256d",
        "formants_hz",
        "password_hash",
        "password_plain_hint",
        "password_hint",
    }
)


def load_voice_auth_config() -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if _CONFIG_PATH.exists():
        try:
            raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            raw = {}

    owner_id = os.environ.get("VOICE_AUTH_OWNER_ID", raw.get("owner_id", "")).strip()
    owner_email = os.environ.get("VOICE_AUTH_OWNER_EMAIL", raw.get("owner_email", "")).strip()
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

    return {
        "owner_id": owner_id,
        "owner_email": owner_email,
        "owner_display_name": owner_display_name,
        "role_map": role_map_int,
        "role_map_str": {str(k): v for k, v in role_map_int.items()},
        "user_role_map": user_role_map_int,
        "threshold_mel": threshold_mel,
        "threshold_deep": threshold_deep,
    }


_CFG = load_voice_auth_config()

OWNER_ID: str = _CFG["owner_id"]
OWNER_EMAIL: str = _CFG["owner_email"]
OWNER_DISPLAY_NAME: str = _CFG["owner_display_name"]
ROLE_MAP: dict[int, str] = _CFG["role_map"]
USER_ROLE_MAP: dict[int, str] = _CFG["user_role_map"]
THRESHOLD_MEL: float = _CFG["threshold_mel"]
THRESHOLD_DEEP: float = _CFG["threshold_deep"]


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
            if k_str in ("password_plain_hint", "password_hint"):
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
