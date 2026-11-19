"""Lệnh giọng nói theo phiên (session): không nhận dạng người nói, không vòng 'nói lại'."""

from __future__ import annotations

import base64
import binascii
import logging
from typing import Any

import numpy as np

from simulator.auth.session_store import UserSession
from simulator.live.echo_and_speech_guard import (
    ServerEchoGuard,
    sanitize_spoken_vietnamese_text,
)
from simulator.live.tts_rejection_vi import (
    build_aoede_http_audio_fields,
    synthesize_aoede_phrase_audio,
)
from simulator.voice.enrollment_quality import (
    parse_vietnamese_voice_command_intents,
    strip_vietnamese_diacritics,
)

LOG = logging.getLogger("simulator.voice.session_command")

_SESSION_ECHO_GUARDS: dict[str, ServerEchoGuard] = {}


def get_session_echo_guard(session: UserSession | None) -> ServerEchoGuard:
    key = str(
        getattr(session, "session_id", "") or getattr(session, "user_id", "") or "global"
    ).strip() or "global"
    guard = _SESSION_ECHO_GUARDS.get(key)
    if guard is None:
        if len(_SESSION_ECHO_GUARDS) >= 256:
            _SESSION_ECHO_GUARDS.pop(next(iter(_SESSION_ECHO_GUARDS)))
        guard = ServerEchoGuard()
        _SESSION_ECHO_GUARDS[key] = guard
    return guard


def reset_session_echo_guards() -> None:
    _SESSION_ECHO_GUARDS.clear()

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


def _extract_offline_wav_transcript(payload: dict[str, Any] | None) -> str:
    """Trích xuất khẩu lệnh từ audio WAV/PCM16 catalog offline (chỉ lấy transcript, KHÔNG bỏ qua RBAC)."""
    body = payload if isinstance(payload, dict) else {}
    b64_val = str(
        body.get("wav_b64") or body.get("audio_b64") or body.get("pcm16k_b64") or ""
    ).strip()
    if not b64_val:
        return ""
    if "," in b64_val:
        b64_val = b64_val.split(",", 1)[1].strip()
    if len(b64_val) < 64:
        return ""
    try:
        raw_bytes = base64.b64decode(b64_val, validate=False)
    except (binascii.Error, ValueError):
        return ""
    if not raw_bytes or len(raw_bytes) < 64:
        return ""
    try:
        from simulator.voice.stt_pipeline import (
            decode_audio_bytes_to_pcm16k,
            match_signature_from_catalog,
        )

        pcm16, decoded_raw = decode_audio_bytes_to_pcm16k(raw_bytes)
        if pcm16.size < 1600:
            return ""
        rms = float(np.sqrt(np.mean(pcm16.astype(np.float64) ** 2)))
        if not np.isfinite(rms) or rms < 40.0:
            return ""
        matched_sig, _score = match_signature_from_catalog(pcm16, decoded_raw)
        if matched_sig is not None:
            rec = str(matched_sig.get("recognized_text") or "").strip()
            canon = str(matched_sig.get("canonical_command") or "").strip()
            is_greeting = "xin chao" in strip_vietnamese_diacritics(rec.lower())
            if rec and (is_greeting or parse_vietnamese_voice_command_intents(rec)):
                return rec
            if canon:
                return canon
            if rec:
                return rec
    except Exception as exc:
        LOG.debug("offline wav transcript lookup skipped: %s", exc)
    return ""


def _strip_legacy_repeat_speech(result: dict[str, Any]) -> dict[str, Any]:
    """Đảm bảo đường lệnh session không phát lại cụm 'vui lòng nói lại'."""
    for key in ("exact_spoken_reply", "rejection_speech", "reply_text", "message", "tts_text", "reply"):
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
        result["pcm24k_b64"] = ""
        result["pcm_b64"] = ""
        result["audio_b64"] = ""
        result["audio_wav_b64"] = ""
    else:
        result["play_audio"] = bool(result.get("pcm24k_b64"))
    return result


def silent_echo_suppressed_response(*, session: UserSession | None = None) -> dict[str, Any]:
    """Transcript trùng câu AI vừa nói (acoustic echo): bỏ qua hoàn toàn, không chạy lệnh, không tạo lượt mới."""
    payload = silent_no_transcript_response(session=session)
    payload["reason"] = "echo_suppressed"
    payload["error"] = "echo_suppressed"
    payload["echo_suppressed"] = True
    return payload


async def execute_session_voice_intents(
    *,
    engine: Any,
    session: UserSession,
    transcript: str,
    source: str = "web_voice",
) -> dict[str, Any]:
    from simulator.automation_nlu import (
        _classify_confirmation_utterance,
        _resolve_session_key,
        process_automation_nlu_command,
        stage_device_intents_for_confirmation,
    )
    from simulator.automation_repo import PENDING_CONFIRM_TTL_SEC

    echo_guard = get_session_echo_guard(session)
    skey = _resolve_session_key(session, source)

    # Never echo-suppress an explicit short confirm/cancel reply ("ok", "đồng ý", "hủy", "không"...).
    conf_decision = _classify_confirmation_utterance(transcript)
    if conf_decision is None:
        is_echo, _score, _reason = echo_guard.check_echo_transcript(transcript)
        if is_echo:
            return silent_echo_suppressed_response(session=session)

    nlu_res = await process_automation_nlu_command(
        text=transcript,
        engine=engine,
        session=session,
        source=source,
    )
    if nlu_res is not None:
        nlu_payload = dict(nlu_res.get("payload") or {})
        raw_spoken_nlu = str(
            nlu_payload.get("exact_spoken_reply")
            or nlu_payload.get("reply")
            or nlu_payload.get("error")
            or ""
        ).strip()
        spoken_nlu = sanitize_spoken_vietnamese_text(raw_spoken_nlu) or raw_spoken_nlu
        if spoken_nlu:
            echo_guard.record_ai_utterance(spoken_nlu)
        aoede_fields_nlu: dict[str, Any] = {}
        if spoken_nlu and not any(marker in spoken_nlu.lower() for marker in _LEGACY_REPEAT_MARKERS):
            try:
                aoede_bundle = await synthesize_aoede_phrase_audio(spoken_nlu, interactive_budget_sec=1.8)
                aoede_fields_nlu = build_aoede_http_audio_fields(aoede_bundle)
                pcm_nlu_bytes = aoede_bundle.get("pcm24k_bytes") or b""
                if pcm_nlu_bytes:
                    echo_guard.note_ai_audio_chunk(len(pcm_nlu_bytes), sample_rate=24000)
            except Exception as exc:
                LOG.debug("aoede voice synthesis fallback skipped (nlu): %s", exc)
        is_ok_nlu = bool(nlu_payload.get("ok"))
        is_pending_nlu = bool(nlu_payload.get("requires_confirmation"))
        is_executed_nlu = is_ok_nlu and not is_pending_nlu
        is_blocked_nlu = bool(nlu_payload.get("rbac_blocked"))
        http_status_nlu = int(nlu_res.get("status_code") or (403 if is_blocked_nlu else 200))
        return _strip_legacy_repeat_speech({
            **nlu_payload,
            "ok": is_ok_nlu,
            "http_status": http_status_nlu,
            "executed": is_executed_nlu,
            "authorized": not is_blocked_nlu,
            "permission": "DENIED" if is_blocked_nlu else "ALLOWED",
            "silent": False,
            "should_reply": bool(spoken_nlu),
            "ask_repeat": False,
            "play_audio": bool(spoken_nlu and aoede_fields_nlu.get("pcm24k_b64")),
            "no_reprompt": True,
            "recognized_text": transcript,
            "transcript": transcript,
            "tier": int(session.tier),
            "role": session.role,
            "user_name": session.display_name,
            "reply": spoken_nlu,
            "exact_spoken_reply": spoken_nlu,
            "rejection_speech": spoken_nlu if is_blocked_nlu else "",
            "reply_text": spoken_nlu,
            **aoede_fields_nlu,
        })

    norm_transcript = strip_vietnamese_diacritics(transcript.lower())
    if any(k in norm_transcript for k in ("nhiet do", "do am", "cam bien")) and not any(
        w in norm_transcript for w in ("set ", "chinh ", "dat ", "len ", "xuong ", "dieu hoa", "may lanh")
    ):
        sensors = (
            engine.read_all_sensors()
            if hasattr(engine, "read_all_sensors")
            else {"temperature_c": 28.5, "humidity_pct": 65.0, "soil_moisture_pct": 62.0}
        )
        spoken_sensor = (
            f"Nhiệt độ phòng hiện tại là {sensors['temperature_c']:.1f} độ C, "
            f"độ ẩm không khí {sensors['humidity_pct']:.0f} phần trăm, "
            f"độ ẩm đất {sensors['soil_moisture_pct']:.0f} phần trăm."
        )
        echo_guard.record_ai_utterance(spoken_sensor)
        aoede_fields_s: dict[str, Any] = {}
        try:
            aoede_bundle = await synthesize_aoede_phrase_audio(spoken_sensor, interactive_budget_sec=1.8)
            aoede_fields_s = build_aoede_http_audio_fields(aoede_bundle)
            pcm_s = aoede_bundle.get("pcm24k_bytes") or b""
            if pcm_s:
                echo_guard.note_ai_audio_chunk(len(pcm_s), sample_rate=24000)
        except Exception as exc:
            LOG.debug("aoede voice synthesis fallback skipped (sensor): %s", exc)
        return _strip_legacy_repeat_speech({
            "ok": True,
            "http_status": 200,
            "executed": True,
            "authorized": True,
            "permission": "ALLOWED",
            "silent": False,
            "should_reply": True,
            "ask_repeat": False,
            "play_audio": bool(aoede_fields_s.get("pcm24k_b64")),
            "no_reprompt": True,
            "recognized_text": transcript,
            "transcript": transcript,
            "sensors": sensors,
            "tier": int(session.tier),
            "role": session.role,
            "user_name": session.display_name,
            "reply": spoken_sensor,
            "exact_spoken_reply": spoken_sensor,
            "rejection_speech": "",
            "reply_text": spoken_sensor,
            **aoede_fields_s,
            "snapshot": engine.get_snapshot(session=session) if hasattr(engine, "get_snapshot") else {},
        })

    raw_intents = parse_vietnamese_voice_command_intents(transcript)
    intents = _normalize_intents(raw_intents, transcript)
    if not intents:
        return _strip_legacy_repeat_speech(
            {
                "ok": False,
                "executed": False,
                "authorized": True,
                "permission": "ALLOWED",
                "silent": True,
                "should_reply": False,
                "ask_repeat": False,
                "play_audio": False,
                "no_reprompt": True,
                "reason": "no_intent",
                "error": "no_intent",
                "recognized_text": transcript,
                "transcript": transcript,
                "intents": [],
                "reply": "",
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

    staged = await stage_device_intents_for_confirmation(
        engine=engine,
        session=session,
        source=source,
        intents=intents,
        session_key=skey,
        ttl_sec=PENDING_CONFIRM_TTL_SEC,
    )
    staged_payload = dict(staged.get("payload") or {})
    is_ok_staged = bool(staged_payload.get("ok"))
    is_blocked_staged = bool(staged_payload.get("rbac_blocked"))
    http_status_staged = int(staged.get("status_code") or (403 if is_blocked_staged else 200))
    raw_spoken = str(
        staged_payload.get("exact_spoken_reply")
        or staged_payload.get("reply")
        or staged_payload.get("error")
        or ""
    ).strip()
    spoken = sanitize_spoken_vietnamese_text(raw_spoken) or raw_spoken
    if spoken:
        echo_guard.record_ai_utterance(spoken)
    aoede_fields: dict[str, Any] = {}
    if spoken and not any(marker in spoken.lower() for marker in _LEGACY_REPEAT_MARKERS):
        try:
            aoede_bundle = await synthesize_aoede_phrase_audio(spoken, interactive_budget_sec=1.8)
            aoede_fields = build_aoede_http_audio_fields(aoede_bundle)
            pcm_bytes_out = aoede_bundle.get("pcm24k_bytes") or b""
            if pcm_bytes_out:
                echo_guard.note_ai_audio_chunk(len(pcm_bytes_out), sample_rate=24000)
        except Exception as exc:
            LOG.debug("aoede voice synthesis fallback skipped: %s", exc)

    payload = {
        **staged_payload,
        "ok": is_ok_staged,
        "http_status": http_status_staged,
        "executed": False,
        "confirmed": False,
        "requires_confirmation": bool(staged_payload.get("requires_confirmation")) and is_ok_staged,
        "authorized": not is_blocked_staged,
        "permission": "DENIED" if is_blocked_staged else "ALLOWED",
        "silent": False,
        "should_reply": bool(spoken),
        "ask_repeat": False,
        "play_audio": bool(spoken and aoede_fields.get("pcm24k_b64")),
        "no_reprompt": True,
        "recognized_text": transcript,
        "transcript": transcript,
        "intents": staged_payload.get("intents") or intents,
        "results": staged_payload.get("results") or [],
        "tier": int(session.tier),
        "role": session.role,
        "user_name": session.display_name,
        "rbac_blocked": is_blocked_staged,
        "error": "" if is_ok_staged else str(staged_payload.get("error") or "command_failed"),
        "reply": spoken,
        "exact_spoken_reply": spoken,
        "rejection_speech": spoken if is_blocked_staged else "",
        "reply_text": spoken,
        **aoede_fields,
        "snapshot": engine.get_snapshot(session=session) if hasattr(engine, "get_snapshot") else {},
    }
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
    transcript = extract_command_transcript(payload) or _extract_offline_wav_transcript(payload)
    if not transcript:
        LOG.info("voice_command silent: empty transcript (no speaker check, no reprompt)")
        return silent_no_transcript_response(session=session), 200
    body = await execute_session_voice_intents(
        engine=engine,
        session=session,
        transcript=transcript,
        source=source,
    )
    status = int(body.get("http_status") or 200)
    if status == 200 and body.get("rbac_blocked") and not body.get("ok"):
        status = 403
    return body, status
