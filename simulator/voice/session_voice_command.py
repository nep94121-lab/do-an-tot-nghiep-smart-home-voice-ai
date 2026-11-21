"""Lệnh giọng nói theo phiên (session): không nhận dạng người nói, không vòng 'nói lại'."""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import os
import time
from typing import Any

import numpy as np

from simulator.auth.session_store import UserSession
from simulator.live.echo_and_speech_guard import (
    ServerEchoGuard,
    sanitize_spoken_vietnamese_text,
)
from simulator.live.tts_rejection_vi import (
    build_aoede_http_audio_fields,
    schedule_aoede_background_warm,
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


def _decode_payload_audio_pcm16k(payload: dict[str, Any] | None) -> tuple[np.ndarray, bytes] | None:
    body = payload if isinstance(payload, dict) else {}
    b64_val = str(
        body.get("wav_b64") or body.get("audio_b64") or body.get("pcm16k_b64") or ""
    ).strip()
    if not b64_val:
        return None
    if "," in b64_val:
        b64_val = b64_val.split(",", 1)[1].strip()
    if len(b64_val) < 64:
        return None
    try:
        raw_bytes = base64.b64decode(b64_val, validate=False)
    except (binascii.Error, ValueError):
        return None
    if not raw_bytes or len(raw_bytes) < 64:
        return None
    from simulator.voice.stt_pipeline import decode_audio_bytes_to_pcm16k

    pcm16, decoded_raw = decode_audio_bytes_to_pcm16k(raw_bytes)
    return pcm16, decoded_raw


def _match_catalog_signature_text(pcm16: np.ndarray, decoded_raw: bytes) -> str:
    from simulator.voice.stt_pipeline import match_signature_from_catalog

    matched_sig, _score = match_signature_from_catalog(pcm16, decoded_raw)
    if matched_sig is None:
        return ""
    rec = str(matched_sig.get("recognized_text") or "").strip()
    canon = str(matched_sig.get("canonical_command") or "").strip()
    is_greeting = "xin chao" in strip_vietnamese_diacritics(rec.lower())
    if rec and (is_greeting or parse_vietnamese_voice_command_intents(rec)):
        return rec
    if canon:
        return canon
    if rec:
        return rec
    return ""


async def _extract_wav_transcript_async(
    payload: dict[str, Any] | None,
    *,
    has_pending_confirmation: bool = False,
) -> tuple[str, str, float]:
    """Trích xuất khẩu lệnh bất đồng bộ từ audio WAV/PCM16; trả về (text, stt_engine, stt_ms)."""
    t0 = time.perf_counter()
    try:
        decoded = _decode_payload_audio_pcm16k(payload)
        if decoded is None:
            return "", "", 0.0
        pcm16, decoded_raw = decoded
        if pcm16.size < 1600:
            return "", "acoustic_gate", round((time.perf_counter() - t0) * 1000.0, 1)
        rms = float(np.sqrt(np.mean(pcm16.astype(np.float64) ** 2)))
        if not np.isfinite(rms) or rms < 25.0:
            return "", "acoustic_gate", round((time.perf_counter() - t0) * 1000.0, 1)

        catalog_text = _match_catalog_signature_text(pcm16, decoded_raw)
        if catalog_text:
            return catalog_text, "catalog", round((time.perf_counter() - t0) * 1000.0, 1)

        from simulator.voice.vietnamese_stt import transcribe_vietnamese_audio

        stt_mode = os.environ.get("SMARTHOME_STT_MODE", "auto").strip().lower()
        stt_res = await asyncio.to_thread(
            transcribe_vietnamese_audio,
            pcm16,
            16000,
            stt_mode=stt_mode,
            has_pending_confirmation=has_pending_confirmation,
        )
        stt_engine = str(stt_res.get("stt_engine") or stt_mode or "auto")
        stt_ms = float(stt_res.get("stt_ms") or round((time.perf_counter() - t0) * 1000.0, 1))
        if stt_res.get("is_noise") and not stt_res.get("text"):
            return "", stt_engine, stt_ms
        return str(stt_res.get("text") or "").strip(), stt_engine, stt_ms
    except Exception as exc:
        LOG.debug("wav transcript lookup skipped: %s", exc)
    return "", "", 0.0


def _extract_offline_wav_transcript(payload: dict[str, Any] | None) -> str:
    """Trích xuất khẩu lệnh đồng bộ từ audio WAV/PCM16 (tương thích ngược)."""
    try:
        decoded = _decode_payload_audio_pcm16k(payload)
        if decoded is None:
            return ""
        pcm16, decoded_raw = decoded
        if pcm16.size < 1600:
            return ""
        rms = float(np.sqrt(np.mean(pcm16.astype(np.float64) ** 2)))
        if not np.isfinite(rms) or rms < 25.0:
            return ""
        catalog_text = _match_catalog_signature_text(pcm16, decoded_raw)
        if catalog_text:
            return catalog_text

        from simulator.voice.vietnamese_stt import transcribe_vietnamese_pcm16k

        stt_res = transcribe_vietnamese_pcm16k(pcm16, sr=16000)
        if stt_res.get("is_noise") and not stt_res.get("text"):
            return ""
        return str(stt_res.get("text") or "").strip()
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


async def _synthesize_voice_reply_fields(
    spoken: str,
    echo_guard: ServerEchoGuard,
) -> dict[str, Any]:
    if not spoken or any(marker in spoken.lower() for marker in _LEGACY_REPEAT_MARKERS):
        return {}
    echo_guard.record_ai_utterance(spoken)
    try:
        cache_only = os.environ.get("SMARTHOME_AOEDE_CACHE_ONLY", "").strip().lower() in ("1", "true", "yes")
        aoede_bundle = await synthesize_aoede_phrase_audio(spoken, allow_live_refresh=not cache_only)
        aoede_fields = build_aoede_http_audio_fields(aoede_bundle)
        pcm_bytes_out = aoede_bundle.get("pcm24k_bytes") or b""
        if pcm_bytes_out:
            echo_guard.note_ai_audio_chunk(len(pcm_bytes_out), sample_rate=24000)
        elif cache_only:
            schedule_aoede_background_warm(spoken)
        return aoede_fields
    except Exception as exc:
        LOG.debug("aoede voice synthesis fallback skipped: %s", exc)
        return {}


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
        handle_confirmation_reply,
        handle_pending_interruption_if_any,
        process_automation_nlu_command,
    )
    from simulator.automation_repo import find_custom_command_by_text
    from simulator.engine.voice_rbac_mixin import FIXED_REJECTION_PHRASE_VI
    from simulator.voice.vietnamese_policy import (
        classify_ambiguous_or_unsupported_vi,
        classify_small_talk_vi,
        ensure_vietnamese_reply,
        format_short_action_reply_vi,
        handle_sensor_or_status_query_vi,
        parse_direct_device_intents_vi,
    )

    echo_guard = get_session_echo_guard(session)
    skey = _resolve_session_key(session, source)
    user_id = str(getattr(session, "user_id", "") or "guest").strip()
    actor_tier = int(session.tier)

    # Never echo-suppress an explicit short confirm/cancel reply ("ok", "đồng ý", "hủy", "không"...).
    conf_decision = _classify_confirmation_utterance(transcript)
    if conf_decision is None:
        is_echo, _score, _reason = echo_guard.check_echo_transcript(transcript)
        if is_echo:
            return silent_echo_suppressed_response(session=session)
        # Confirmed non-echo user turn: clear stale prior-turn AI utterances so earlier prompts cannot suppress later commands.
        echo_guard.clear_recent_utterances()

    # 0. Active pending confirmation reply FIRST
    if conf_decision is not None:
        conf_res = await handle_confirmation_reply(
            raw_text=transcript,
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
        )
        if conf_res is not None:
            echo_guard.clear_recent_utterances()
            conf_payload = dict(conf_res.get("payload") or {})
            raw_spoken_c = str(
                conf_payload.get("exact_spoken_reply")
                or conf_payload.get("reply")
                or conf_payload.get("error")
                or ""
            ).strip()
            spoken_c = ensure_vietnamese_reply(sanitize_spoken_vietnamese_text(raw_spoken_c) or raw_spoken_c)
            aoede_c = await _synthesize_voice_reply_fields(spoken_c, echo_guard)
            is_ok_c = bool(conf_payload.get("ok"))
            is_blocked_c = bool(conf_payload.get("rbac_blocked"))
            http_status_c = int(conf_res.get("status_code") or (403 if is_blocked_c else 200))
            return _strip_legacy_repeat_speech({
                **conf_payload,
                "ok": is_ok_c,
                "http_status": http_status_c,
                "executed": bool(conf_payload.get("executed", is_ok_c and not conf_payload.get("requires_confirmation"))),
                "authorized": not is_blocked_c,
                "permission": "DENIED" if is_blocked_c else "ALLOWED",
                "silent": False,
                "should_reply": bool(spoken_c),
                "ask_repeat": False,
                "play_audio": bool(spoken_c and aoede_c.get("pcm24k_b64")),
                "no_reprompt": True,
                "recognized_text": transcript,
                "transcript": transcript,
                "tier": actor_tier,
                "role": session.role,
                "user_name": session.display_name,
                "reply": spoken_c,
                "exact_spoken_reply": spoken_c,
                "rejection_speech": spoken_c if is_blocked_c else "",
                "reply_text": spoken_c,
                **aoede_c,
            })

    # 1. Friendly Vietnamese small talk BEFORE any automation/permission checks (unless saved custom command)
    saved_custom = find_custom_command_by_text(transcript, owner_user_id=user_id) if actor_tier < 3 else None
    if saved_custom is None:
        small_talk = classify_small_talk_vi(transcript, user_name=str(session.display_name or ""))
        if small_talk is not None:
            await handle_pending_interruption_if_any(
                raw_text=transcript,
                engine=engine,
                session=session,
                source=source,
                session_key=skey,
                is_new_valid_intent=True,
            )
            spoken_st = ensure_vietnamese_reply(str(small_talk.get("reply") or ""))
            aoede_st = await _synthesize_voice_reply_fields(spoken_st, echo_guard)
            return _strip_legacy_repeat_speech({
                "ok": True,
                "http_status": 200,
                "kind": "small_talk",
                "subkind": small_talk.get("subkind", "greeting"),
                "executed": False,
                "requires_confirmation": False,
                "rbac_blocked": False,
                "authorized": True,
                "permission": "ALLOWED",
                "silent": False,
                "should_reply": True,
                "ask_repeat": False,
                "play_audio": bool(aoede_st.get("pcm24k_b64")),
                "no_reprompt": True,
                "recognized_text": transcript,
                "transcript": transcript,
                "intents": [],
                "tier": actor_tier,
                "role": session.role,
                "user_name": session.display_name,
                "reply": spoken_st,
                "exact_spoken_reply": spoken_st,
                "rejection_speech": "",
                "reply_text": spoken_st,
                **aoede_st,
                "snapshot": engine.get_snapshot(session=session) if hasattr(engine, "get_snapshot") else {},
            })

    # 2. Sensor & device status queries execute immediately with real values
    query_info = handle_sensor_or_status_query_vi(transcript, engine, session)
    if query_info is not None:
        await handle_pending_interruption_if_any(
            raw_text=transcript,
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            is_new_valid_intent=True,
        )
        is_q_blocked = bool(query_info.get("rbac_blocked"))
        q_status = int(query_info.get("status_code") or (403 if is_q_blocked else 200))
        spoken_q = ensure_vietnamese_reply(str(query_info.get("exact_spoken_reply") or query_info.get("reply") or ""))
        aoede_q = await _synthesize_voice_reply_fields(spoken_q, echo_guard)
        return _strip_legacy_repeat_speech({
            **query_info,
            "ok": bool(query_info.get("ok", not is_q_blocked)),
            "http_status": q_status,
            "executed": not is_q_blocked,
            "requires_confirmation": False,
            "rbac_blocked": is_q_blocked,
            "authorized": not is_q_blocked,
            "permission": "DENIED" if is_q_blocked else "ALLOWED",
            "silent": False,
            "should_reply": True,
            "ask_repeat": False,
            "play_audio": bool(aoede_q.get("pcm24k_b64")),
            "no_reprompt": True,
            "recognized_text": transcript,
            "transcript": transcript,
            "tier": actor_tier,
            "role": session.role,
            "user_name": session.display_name,
            "reply": spoken_q,
            "exact_spoken_reply": spoken_q,
            "rejection_speech": spoken_q if is_q_blocked else "",
            "reply_text": spoken_q,
            **aoede_q,
            "snapshot": engine.get_snapshot(session=session) if hasattr(engine, "get_snapshot") else {},
        })

    # 3. Automation NLU (custom commands create/use/edit/delete, schedules/timers, cross-rules, resets, pool queries)
    nlu_res = await process_automation_nlu_command(
        text=transcript,
        engine=engine,
        session=session,
        source=source,
        session_key=skey,
    )
    if nlu_res is not None:
        nlu_payload = dict(nlu_res.get("payload") or {})
        raw_spoken_nlu = str(
            nlu_payload.get("exact_spoken_reply")
            or nlu_payload.get("reply")
            or nlu_payload.get("error")
            or ""
        ).strip()
        spoken_nlu = ensure_vietnamese_reply(sanitize_spoken_vietnamese_text(raw_spoken_nlu) or raw_spoken_nlu)
        aoede_fields_nlu = await _synthesize_voice_reply_fields(spoken_nlu, echo_guard)
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
            "tier": actor_tier,
            "role": session.role,
            "user_name": session.display_name,
            "reply": spoken_nlu,
            "exact_spoken_reply": spoken_nlu,
            "rejection_speech": spoken_nlu if is_blocked_nlu else "",
            "reply_text": spoken_nlu,
            **aoede_fields_nlu,
        })

    # 4. Direct simple device commands -> RBAC check -> EXECUTE IMMEDIATELY -> short Vietnamese confirmation
    word_map = engine.get_word_mappings() if hasattr(engine, "get_word_mappings") else None
    intents = parse_direct_device_intents_vi(transcript, word_mappings=word_map)
    if intents:
        await handle_pending_interruption_if_any(
            raw_text=transcript,
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            is_new_valid_intent=True,
        )
        # Pre-check RBAC across all target devices before mutating any device
        for item in intents:
            dev_id = item["device_id"]
            allowed, _reason = engine.check_device_permission(dev_id, actor_tier=actor_tier)
            if not allowed:
                spoken_deny = ensure_vietnamese_reply(FIXED_REJECTION_PHRASE_VI)
                aoede_deny = await _synthesize_voice_reply_fields(spoken_deny, echo_guard)
                return _strip_legacy_repeat_speech({
                    "ok": False,
                    "http_status": 403,
                    "executed": False,
                    "requires_confirmation": False,
                    "rbac_blocked": True,
                    "authorized": False,
                    "permission": "DENIED",
                    "silent": False,
                    "should_reply": True,
                    "ask_repeat": False,
                    "play_audio": bool(aoede_deny.get("pcm24k_b64")),
                    "no_reprompt": True,
                    "recognized_text": transcript,
                    "transcript": transcript,
                    "intents": intents,
                    "results": [],
                    "tier": actor_tier,
                    "role": session.role,
                    "user_name": session.display_name,
                    "error": spoken_deny,
                    "reply": spoken_deny,
                    "exact_spoken_reply": spoken_deny,
                    "rejection_speech": spoken_deny,
                    "reply_text": spoken_deny,
                    **aoede_deny,
                    "snapshot": engine.get_snapshot(session=session) if hasattr(engine, "get_snapshot") else {},
                })

        exec_results: list[dict[str, Any]] = []
        exec_summary_items: list[dict[str, Any]] = []
        for item in intents:
            dev_id = item["device_id"]
            act = item["action"]
            prev_st = str((engine.devices.get(dev_id) or {}).get("state") or "")
            res = await engine.execute_device_action(
                dev_id,
                act,
                source=source,
                bypass_rbac=False,
                request_tier=actor_tier,
                request_user_name=session.display_name,
                request_role=session.role,
            )
            if not res.get("ok"):
                is_blk = bool(res.get("rbac_blocked"))
                err_txt = ensure_vietnamese_reply(
                    FIXED_REJECTION_PHRASE_VI if is_blk else str(res.get("exact_spoken_reply") or res.get("error") or "Không thực hiện được lệnh.")
                )
                aoede_err = await _synthesize_voice_reply_fields(err_txt, echo_guard)
                return _strip_legacy_repeat_speech({
                    "ok": False,
                    "http_status": 403 if is_blk else 400,
                    "executed": False,
                    "requires_confirmation": False,
                    "rbac_blocked": is_blk,
                    "authorized": not is_blk,
                    "permission": "DENIED" if is_blk else "ALLOWED",
                    "silent": False,
                    "should_reply": True,
                    "ask_repeat": False,
                    "play_audio": bool(aoede_err.get("pcm24k_b64")),
                    "no_reprompt": True,
                    "recognized_text": transcript,
                    "transcript": transcript,
                    "intents": intents,
                    "results": exec_results,
                    "tier": actor_tier,
                    "role": session.role,
                    "user_name": session.display_name,
                    "error": err_txt,
                    "reply": err_txt,
                    "exact_spoken_reply": err_txt,
                    "rejection_speech": err_txt if is_blk else "",
                    "reply_text": err_txt,
                    **aoede_err,
                    "snapshot": engine.get_snapshot(session=session) if hasattr(engine, "get_snapshot") else {},
                })
            exec_results.append(res)
            new_st = str((engine.devices.get(dev_id) or {}).get("state") or "")
            exec_summary_items.append({
                "device_id": dev_id,
                "action": act,
                "previous_state": prev_st,
                "state": new_st,
                "already_in_state": bool(prev_st and new_st and prev_st == new_st),
            })

        spoken_ok = ensure_vietnamese_reply(format_short_action_reply_vi(exec_summary_items, engine.devices))
        aoede_ok = await _synthesize_voice_reply_fields(spoken_ok, echo_guard)
        last_item = exec_summary_items[-1]
        return _strip_legacy_repeat_speech({
            "ok": True,
            "http_status": 200,
            "executed": True,
            "confirmed": True,
            "requires_confirmation": False,
            "rbac_blocked": False,
            "authorized": True,
            "permission": "ALLOWED",
            "silent": False,
            "should_reply": True,
            "ask_repeat": False,
            "play_audio": bool(aoede_ok.get("pcm24k_b64")),
            "no_reprompt": True,
            "recognized_text": transcript,
            "transcript": transcript,
            "device_id": last_item["device_id"],
            "state": last_item["state"],
            "intents": intents,
            "results": exec_results,
            "tier": actor_tier,
            "role": session.role,
            "user_name": session.display_name,
            "error": "",
            "reply": spoken_ok,
            "exact_spoken_reply": spoken_ok,
            "rejection_speech": "",
            "reply_text": spoken_ok,
            **aoede_ok,
            "snapshot": engine.get_snapshot(session=session) if hasattr(engine, "get_snapshot") else {},
        })

    # 5. Unrelated/ambiguous/unsupported/foreign/nonsense: check pending reminder first, else short Vietnamese clarification
    reminder = await handle_pending_interruption_if_any(
        raw_text=transcript,
        engine=engine,
        session=session,
        source=source,
        session_key=skey,
        is_new_valid_intent=False,
    )
    if reminder is not None:
        rem_payload = dict(reminder.get("payload") or {})
        spoken_rem = ensure_vietnamese_reply(str(rem_payload.get("exact_spoken_reply") or rem_payload.get("reply") or ""))
        aoede_rem = await _synthesize_voice_reply_fields(spoken_rem, echo_guard)
        return _strip_legacy_repeat_speech({
            **rem_payload,
            "ok": True,
            "http_status": 200,
            "executed": False,
            "rbac_blocked": False,
            "authorized": True,
            "permission": "ALLOWED",
            "silent": False,
            "should_reply": True,
            "ask_repeat": False,
            "play_audio": bool(aoede_rem.get("pcm24k_b64")),
            "no_reprompt": True,
            "recognized_text": transcript,
            "transcript": transcript,
            "tier": actor_tier,
            "role": session.role,
            "user_name": session.display_name,
            "reply": spoken_rem,
            "exact_spoken_reply": spoken_rem,
            "rejection_speech": "",
            "reply_text": spoken_rem,
            **aoede_rem,
        })

    clarification = ensure_vietnamese_reply(
        classify_ambiguous_or_unsupported_vi(transcript) or "Tôi chưa nghe rõ lệnh, bạn nói lại rõ hơn nhé."
    )
    aoede_cl = await _synthesize_voice_reply_fields(clarification, echo_guard)
    return _strip_legacy_repeat_speech({
        "ok": True,
        "http_status": 200,
        "executed": False,
        "requires_confirmation": False,
        "needs_clarification": True,
        "rbac_blocked": False,
        "authorized": True,
        "permission": "ALLOWED",
        "silent": False,
        "should_reply": True,
        "ask_repeat": False,
        "play_audio": bool(aoede_cl.get("pcm24k_b64")),
        "no_reprompt": True,
        "reason": "needs_clarification",
        "recognized_text": transcript,
        "transcript": transcript,
        "intents": [],
        "results": [],
        "tier": actor_tier,
        "role": session.role,
        "user_name": session.display_name,
        "reply": clarification,
        "exact_spoken_reply": clarification,
        "rejection_speech": "",
        "reply_text": clarification,
        **aoede_cl,
        "snapshot": engine.get_snapshot(session=session) if hasattr(engine, "get_snapshot") else {},
    })


def _peek_has_active_pending_confirmation(owner_user_id: str, session_key: str) -> bool:
    """Pure read-only check for an unexpired pending confirmation (never mutates expired rows)."""
    uid = str(owner_user_id or "").strip()
    if not uid:
        return False
    skey = str(session_key or "").strip()
    now_ts = time.time()
    try:
        from simulator.database_sqlite import _active_db_path
        from simulator.db_migrations import open_wal_connection

        db_path = _active_db_path()
        if not db_path.exists():
            return False
        conn = open_wal_connection(db_path, readonly=True)
        try:
            if skey:
                row = conn.execute(
                    """
                    SELECT 1 FROM pending_confirmations
                    WHERE owner_user_id = ? AND session_key = ? AND status = 'pending' AND expires_at > ?
                    LIMIT 1
                    """,
                    (uid, skey, now_ts),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT 1 FROM pending_confirmations
                    WHERE owner_user_id = ? AND status = 'pending' AND expires_at > ?
                    LIMIT 1
                    """,
                    (uid, now_ts),
                ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return False


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
    stt_engine = ""
    stt_ms = 0.0
    if not transcript:
        has_pending = False
        try:
            from simulator.automation_nlu import _resolve_session_key

            skey = _resolve_session_key(session, source)
            uid = str(getattr(session, "user_id", "") or "guest").strip()
            has_pending = _peek_has_active_pending_confirmation(uid, skey)
        except Exception:
            has_pending = False
        transcript, stt_engine, stt_ms = await _extract_wav_transcript_async(
            payload,
            has_pending_confirmation=has_pending,
        )
    if not transcript:
        LOG.info("voice_command silent: empty transcript (no speaker check, no reprompt)")
        silent_body = silent_no_transcript_response(session=session)
        if stt_engine:
            silent_body["stt_engine"] = stt_engine
            silent_body["stt_ms"] = round(stt_ms, 1)
        return silent_body, 200
    body = await execute_session_voice_intents(
        engine=engine,
        session=session,
        transcript=transcript,
        source=source,
    )
    if stt_engine:
        body["stt_engine"] = stt_engine
        body["stt_ms"] = round(stt_ms, 1)
    status = int(body.get("http_status") or 200)
    if status == 200 and body.get("rbac_blocked") and not body.get("ok"):
        status = 403
    return body, status
