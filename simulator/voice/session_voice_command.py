"""Lệnh giọng nói theo phiên (session): không nhận dạng người nói, không vòng 'nói lại'."""

from __future__ import annotations

import logging
from typing import Any

from simulator.auth.session_store import UserSession
from simulator.voice.enrollment_quality import parse_vietnamese_voice_command_intents

LOG = logging.getLogger("simulator.voice.session_command")

# Các câu từ chối kiểu nhận dạng người nói / yêu cầu nói lại — không còn được phát trên đường lệnh.
_LEGACY_REPEAT_MARKERS = (
    "vui lòng nói lại",
    "âm thanh chưa rõ",
    "không nhận ra giọng",
    "giọng nói chưa được đăng ký",
)


def is_authenticated_control_session(session: UserSession | None) -> bool:
    if session is None:
        return False
    if not bool(getattr(session, "is_authenticated", False)):
        return False
    if str(getattr(session, "role", "") or "").upper() == "UNKNOWN":
        return False
    if int(getattr(session, "tier", 99) or 99) not in (1, 2, 3):
        return False
    if str(getattr(session, "user_id", "") or "").strip().lower() in ("", "unknown", "anonymous"):
        return False
    return True


def extract_command_transcript(payload: dict[str, Any] | None) -> str:
    body = payload if isinstance(payload, dict) else {}
    keys = (
        "transcript",
        "transcript_hint",
        "transcriptHint",
        "text",
        "command_text",
        "command",
        "final_transcript",
        "speech_text",
    )
    for key in keys:
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    alternatives = body.get("alternatives") or body.get("transcripts")
    if isinstance(alternatives, list):
        for item in alternatives:
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, dict):
                text = item.get("transcript") or item.get("text") or ""
                if str(text).strip():
                    return str(text).strip()
    return ""


def silent_no_transcript_response(*, session: UserSession | None = None) -> dict[str, Any]:
    """Không có lời nói để thực thi: im lặng, không TTS, không hỏi nói lại."""
    payload = {
        "ok": False,
        "executed": False,
        "silent": True,
        "should_reply": False,
        "ask_repeat": False,
        "play_audio": False,
        "no_reprompt": True,
        "reason": "empty_transcript",
        "error": "empty_transcript",
        "exact_spoken_reply": "",
        "rejection_speech": "",
        "reply_text": "",
        "pcm24k_b64": "",
        "audio_b64": "",
        "intents": [],
    }
    if session is not None and is_authenticated_control_session(session):
        payload["tier"] = int(session.tier)
        payload["role"] = session.role
        payload["user_name"] = session.display_name
    return payload


def unauthenticated_voice_response() -> tuple[dict[str, Any], int]:
    body = {
        "ok": False,
        "executed": False,
        "silent": True,
        "should_reply": False,
        "ask_repeat": False,
        "play_audio": False,
        "no_reprompt": True,
        "rbac_blocked": True,
        "tier": 99,
        "role": "UNKNOWN",
        "error": "Yêu cầu đăng nhập hoặc mã mời khách hợp lệ.",
        "exact_spoken_reply": "",
        "rejection_speech": "",
        "reply_text": "",
        "pcm24k_b64": "",
        "audio_b64": "",
    }
    return body, 401


def _normalize_intents(raw: Any, transcript: str) -> list[dict[str, Any]]:
    items: list[Any]
    if raw is None:
        items = []
    elif isinstance(raw, dict):
        items = raw.get("intents") or raw.get("commands") or ([raw] if raw.get("device_id") or raw.get("device") else [])
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            continue
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            item = {"device_id": item[0], "action": item[1]}
        if not isinstance(item, dict):
            continue
        device_id = str(item.get("device_id") or item.get("device") or item.get("id") or "").strip()
        action = str(item.get("action") or item.get("target_state") or item.get("state") or "").strip()
        if not device_id:
            continue
        entry = dict(item)
        entry["device_id"] = device_id
        if action:
            entry["action"] = action
        out.append(entry)
    return out


def _first_spoken(result: dict[str, Any]) -> str:
    for key in ("exact_spoken_reply", "reply_text", "message", "error", "rejection_speech"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _strip_legacy_repeat_speech(result: dict[str, Any]) -> dict[str, Any]:
    """Đảm bảo đường lệnh session không phát lại cụm 'vui lòng nói lại'."""
    for key in ("exact_spoken_reply", "rejection_speech", "reply_text", "message", "tts_text"):
        value = result.get(key)
        if isinstance(value, str) and any(marker in value.lower() for marker in _LEGACY_REPEAT_MARKERS):
            result[key] = ""
    if any(marker in str(result.get("error") or "").lower() for marker in _LEGACY_REPEAT_MARKERS):
        if not result.get("error") or "vui lòng nói lại" in str(result.get("error") or "").lower():
            result["error"] = result.get("rbac_blocked") and result.get("error") or result.get("error")
    result["ask_repeat"] = False
    result["should_reply"] = bool(result.get("should_reply")) and bool(
        str(result.get("exact_spoken_reply") or result.get("reply_text") or "").strip()
    )
    if not result.get("should_reply"):
        result["play_audio"] = False
        result["pcm24k_b64"] = result.get("pcm24k_b64") if result.get("ok") else ""
        if not result.get("ok"):
            result["pcm24k_b64"] = ""
            result["audio_b64"] = ""
    return result


async def execute_session_voice_intents(
    *,
    engine: Any,
    session: UserSession,
    transcript: str,
    source: str = "web_voice",
) -> dict[str, Any]:
    raw_intents = parse_vietnamese_voice_command_intents(transcript)
    intents = _normalize_intents(raw_intents, transcript)
    if not intents:
        return _strip_legacy_repeat_speech(
            {
                "ok": False,
                "executed": False,
                "silent": True,
                "should_reply": False,
                "ask_repeat": False,
                "play_audio": False,
                "no_reprompt": True,
                "reason": "no_intent",
                "error": "no_intent",
                "transcript": transcript,
                "intents": [],
                "exact_spoken_reply": "",
                "rejection_speech": "",
                "reply_text": "",
                "pcm24k_b64": "",
                "audio_b64": "",
                "tier": int(session.tier),
                "role": session.role,
                "user_name": session.display_name,
            }
        )

    results: list[dict[str, Any]] = []
    all_ok = True
    any_blocked = False
    last: dict[str, Any] = {}
    for intent in intents:
        device_id = str(intent.get("device_id") or "").strip()
        action = str(intent.get("action") or intent.get("target_state") or "toggle").strip() or "toggle"
        last = await engine.execute_device_action(
            device_id,
            action,
            source=source,
            bypass_rbac=False,
            request_tier=int(session.tier),
            request_user_name=session.display_name,
            request_role=session.role,
            target_state=intent.get("target_state", intent.get("state")),
        )
        last = last if isinstance(last, dict) else {"ok": False, "error": "engine_error"}
        last["device_id"] = device_id
        last["action"] = action
        if not last.get("ok"):
            all_ok = False
            if last.get("rbac_blocked") or "quyền" in str(last.get("error") or "").lower():
                any_blocked = True
        results.append(last)

    spoken = _first_spoken(last)
    payload = {
        "ok": all_ok,
        "executed": all_ok,
        "silent": False,
        "should_reply": bool(spoken),
        "ask_repeat": False,
        "play_audio": False,
        "no_reprompt": True,
        "transcript": transcript,
        "intents": intents,
        "results": results,
        "tier": int(session.tier),
        "role": session.role,
        "user_name": session.display_name,
        "rbac_blocked": any_blocked and not all_ok,
        "error": "" if all_ok else (last.get("error") or "command_failed"),
        "exact_spoken_reply": spoken if all_ok or any_blocked else spoken,
        "rejection_speech": spoken if any_blocked else "",
        "reply_text": spoken,
        "pcm24k_b64": "",
        "audio_b64": "",
        "snapshot": engine.get_snapshot(session=session) if hasattr(engine, "get_snapshot") else {},
    }
    # Chỉ phát TTS khi engine đã cung cấp lời (từ chối quyền / xác nhận). Không tự sinh 'nói lại'.
    return _strip_legacy_repeat_speech(payload)


async def process_session_voice_command(
    *,
    engine: Any,
    session: UserSession | None,
    payload: dict[str, Any] | None,
    source: str = "web_voice",
) -> tuple[dict[str, Any], int]:
    if not is_authenticated_control_session(session):
        return unauthenticated_voice_response()
    assert session is not None
    transcript = extract_command_transcript(payload)
    if not transcript:
        LOG.info("voice_command silent: empty transcript (no speaker check, no reprompt)")
        return silent_no_transcript_response(session=session), 200
    body = await execute_session_voice_intents(
        engine=engine,
        session=session,
        transcript=transcript,
        source=source,
    )
    status = 200
    if body.get("rbac_blocked") and not body.get("ok"):
        status = 403
    return body, status
