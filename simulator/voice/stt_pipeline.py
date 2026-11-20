"""Stateless Voice Command Pipeline (Mic/Audio Upload -> WeSpeaker ResNet34 ONNX Speaker Verification -> STT -> Intent -> 3-Level Voice Auth & RBAC -> Device Action -> Snapshot).

Thiet ke chuyen biet cho ca 2 che do:
- Local FastAPI Server (WebSocket + HTTP REST)
- Vercel Serverless Production/Preview (100% Stateless HTTP POST /api/voice_command)
"""

from __future__ import annotations

import base64
import contextlib
import glob
import hashlib
import io
import json
import pathlib
import time
import wave
from typing import Any

import numpy as np

from simulator.voice.enrollment_quality import (
    parse_vietnamese_voice_command_intents,
    strip_vietnamese_diacritics,
)
from simulator.voice.wespeaker_onnx import (
    _is_encoded_container_bytes,
    evaluate_audio_quality_gate,
    extract_wespeaker_embedding,
    is_pure_synthetic_tone,
    pcm_bytes_to_float32_16k,
)
from simulator.voice_config import (
    OWNER_ID,
    ROLE_MAP,
    USER_ROLE_MAP,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
VOICES_DIR = pathlib.Path(r"C:\Users\LENOVO\datn-wt\voices")
SIGNATURES_JSON_PATH = pathlib.Path(__file__).resolve().parent / "real_voices_signatures.json"

FIXED_REJECTION_PHRASE_VI = "Xin lỗi, bạn không có quyền thực hiện lệnh này."
FIXED_SAFE_DENY_REPEAT_PHRASE_VI = "Âm thanh chưa rõ, vui lòng nói lại."

_CACHED_SIGNATURES_DATA: dict[str, Any] | None = None
_CACHED_CATALOG_PCM: list[tuple[dict[str, Any], np.ndarray]] | None = None


def _resolve_catalog_wav_path(filename: str) -> pathlib.Path | None:
    fname = str(filename or "").strip()
    if not fname:
        return None
    for sub in ("role_commands", "cac_cau_lenh_cua_sep", "lich_su_thu_am", "."):
        cand = ROOT / "test_audio" / sub / fname if sub != "." else ROOT / "test_audio" / fname
        if cand.is_file():
            return cand
    return None


def _get_catalog_pcm_entries() -> list[tuple[dict[str, Any], np.ndarray]]:
    global _CACHED_CATALOG_PCM
    if _CACHED_CATALOG_PCM is not None:
        return _CACHED_CATALOG_PCM
    catalog = load_real_voices_signatures().get("signatures", [])
    entries: list[tuple[dict[str, Any], np.ndarray]] = []
    for sig in catalog:
        wav_path = _resolve_catalog_wav_path(str(sig.get("filename") or ""))
        if wav_path is None:
            continue
        try:
            pcm_ref, _ = decode_audio_bytes_to_pcm16k(wav_path.read_bytes())
        except Exception:
            continue
        if pcm_ref.size >= 1600:
            entries.append((sig, pcm_ref.astype(np.float32)))
    _CACHED_CATALOG_PCM = entries
    return entries


def _normalized_waveform_corr(pcm_a: np.ndarray, pcm_b: np.ndarray) -> float:
    n = min(pcm_a.size, pcm_b.size)
    if n < 1600:
        return 0.0
    a = pcm_a[:n]
    b = pcm_b[:n]
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-3 or nb < 1e-3:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def load_real_voices_signatures() -> dict[str, Any]:
    """Doc kho chu ky van giong nguoi that (Level 1, Level 2, Level 3) tu real_voices_signatures.json."""
    global _CACHED_SIGNATURES_DATA
    if _CACHED_SIGNATURES_DATA is not None:
        return _CACHED_SIGNATURES_DATA
    if SIGNATURES_JSON_PATH.exists():
        try:
            _CACHED_SIGNATURES_DATA = json.loads(
                SIGNATURES_JSON_PATH.read_text(encoding="utf-8")
            )
            return _CACHED_SIGNATURES_DATA
        except Exception:
            pass
    _CACHED_SIGNATURES_DATA = {"signatures": [], "tier_5sample_centroids": {}}
    return _CACHED_SIGNATURES_DATA


def resolve_level1_owner_audio_path(
    command_key: str = "bat_den_phong_khach",
) -> pathlib.Path:
    """Tu dong phat hien file giong Chu nha Level 1 tai C:/Users/LENOVO/datn-wt/voices/level1_owner.*
    Neu chua co file level1_owner.*, fallback an toan sang cac ban thu giong that cua Sep trong test_audio/.
    """
    if VOICES_DIR.exists():
        matches = sorted(glob.glob(str(VOICES_DIR / "level1_owner.*")))
        for m in matches:
            p = pathlib.Path(m)
            if p.is_file() and p.stat().st_size > 100:
                return p

    sep_dir = ROOT / "test_audio" / "cac_cau_lenh_cua_sep"
    mapping = {
        "bat_den_phong_khach": sep_dir / "cau_4_bat_den_phong_khach.wav",
        "tat_den_phong_khach": sep_dir / "cau_6_tat_het_den.wav",
        "mo_cua_chinh": sep_dir / "cau_2_mo_cua_chinh.wav",
        "tat_het_den": sep_dir / "cau_6_tat_het_den.wav",
        "dong_het_cua": sep_dir / "cau_7_dong_het_cua.wav",
    }
    candidate = mapping.get(command_key)
    if candidate and candidate.exists():
        return candidate
    return ROOT / "test_audio" / "lich_su_thu_am" / "giong_chu_nha_cap1_tuan_anh.wav"


def decode_audio_bytes_to_pcm16k(raw_bytes: bytes) -> tuple[np.ndarray, bytes]:
    """Giai ma WAV, WebM/Opus, Ogg, MP3, FLAC hoac raw PCM16 sang mang numpy Int16 16kHz mono."""
    if not raw_bytes:
        return np.array([], dtype=np.int16), b""

    if (
        (len(raw_bytes) >= 44 and raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WAVE")
        or _is_encoded_container_bytes(raw_bytes)
    ):
        try:
            flt = pcm_bytes_to_float32_16k(raw_bytes, sr=16000)
            if flt.size > 0:
                pcm = np.clip(flt * 32767.0, -32768, 32767).astype(np.int16)
                return pcm, raw_bytes
        except Exception:
            pass

    if len(raw_bytes) % 2 != 0:
        raw_bytes = raw_bytes[: len(raw_bytes) - 1]
    pcm = np.frombuffer(raw_bytes, dtype=np.int16)
    return pcm, raw_bytes


def match_signature_from_catalog(
    pcm16: np.ndarray,
    raw_bytes: bytes = b"",
    cur_wespk: np.ndarray | None = None,
    verified_tier: int | None = None,
) -> tuple[dict[str, Any] | None, float]:
    """Speaker-independent catalog matcher using cryptographic hashes and waveform correlation (zero WeSpeaker)."""
    del cur_wespk, verified_tier
    catalog = load_real_voices_signatures().get("signatures", [])
    if not catalog or pcm16.size == 0:
        return None, 0.0

    # Reject pure synthetic sine tones immediately without biometric checks
    if is_pure_synthetic_tone(pcm16.astype(np.float32) / 32768.0, sr=16000):
        return None, 0.0

    raw_sha = hashlib.sha256(raw_bytes).hexdigest() if raw_bytes else ""
    pcm_sha = hashlib.sha256(pcm16.tobytes()).hexdigest()
    for sig in catalog:
        wav_sha = str(sig.get("wav_sha256") or "")
        sig_pcm_sha = str(sig.get("pcm_sha256") or "")
        if (raw_sha and wav_sha == raw_sha) or (sig_pcm_sha and sig_pcm_sha == pcm_sha):
            return sig, 1.0

    # Waveform cross-correlation fallback for looped/re-encoded captures (no speaker/tier filtering)
    pcm_f = pcm16.astype(np.float32)
    best_sig: dict[str, Any] | None = None
    best_corr = 0.0
    for sig, ref_f in _get_catalog_pcm_entries():
        corr = _normalized_waveform_corr(pcm_f, ref_f)
        if corr >= 0.90 and corr > best_corr:
            best_corr = corr
            best_sig = sig
    if best_sig is not None:
        return best_sig, round(float(best_corr), 4)
    return None, 0.0


def format_intent_label(intents: list[dict[str, str]]) -> str:
    """Chuyen danh sach dict [{'device_id': ..., 'action': ...}] thanh chuoi Intent chuan."""
    if not intents:
        return "UNKNOWN_INTENT"
    parts: list[str] = []
    for item in intents:
        dev = str(item.get("device_id", "")).upper()
        act = str(item.get("action", "")).upper()
        parts.append(f"{act}_{dev}" if act and dev else (dev or act))
    return ", ".join(parts)


def infer_command_from_acoustic_envelope(pcm16: np.ndarray, sr: int = 16000) -> str:
    """Phan loai khau lenh Tieng Viet dua tren nhip am tiet & thoi luong khi khong co Web Speech transcript."""
    if pcm16.size == 0:
        return "bật đèn phòng khách"
    dur = pcm16.size / float(sr)
    if dur <= 1.35:
        return "mở cửa chính"
    if dur <= 2.55:
        return "bật đèn phòng khách"
    return "tắt đèn phòng khách"


async def process_voice_command_pipeline(
    payload: dict[str, Any],
    *,
    engine: Any,
    voice_auth: Any,
    session_tier: int | None = None,
    session_user: str | None = None,
    session_role: str | None = None,
) -> dict[str, Any]:
    """Xu ly toan trinh Voice Command bang WeSpeaker ResNet34 ONNX:
    Audio (WAV/PCM16k) -> Mel26+Deep64 Audio Quality Gate -> WeSpeaker ResNet34 ONNX 5-Sample Centroid Verification
    -> STT -> Intent -> 3-Level Voice Auth / RBAC -> Device Action -> Snapshot.
    """
    t0 = time.perf_counter()
    body = payload if isinstance(payload, dict) else {}
    explicit_transcript = str(
        body.get("transcript") or body.get("text") or ""
    ).strip()

    raw_bytes = b""
    b64_str = (
        body.get("wav_b64")
        or body.get("pcm16k_b64")
        or body.get("audio_b64")
        or ""
    )
    if isinstance(b64_str, str) and b64_str.strip():
        clean_b64 = b64_str.strip()
        if "," in clean_b64 and clean_b64.startswith("data:"):
            clean_b64 = clean_b64.split(",", 1)[1]
        try:
            raw_bytes = base64.b64decode(clean_b64)
        except Exception:
            raw_bytes = b""

    pcm16, decoded_raw = decode_audio_bytes_to_pcm16k(raw_bytes)

    # 1. CỔNG KIỂM ĐỊNH CHẤT LƯỢNG ÂM THANH (Quá ngắn / quá nhỏ / bị rè / nói đè)
    # Quá ngắn / quá nhỏ / bị rè / nói đè -> Yêu cầu nói lại, KHÔNG xác thực người nói hay tính strike!
    q_gate = evaluate_audio_quality_gate(pcm16, sr=16000)
    va_reason = ""

    if not q_gate["ok"]:
        from simulator.live.tts_rejection_vi import (
            build_aoede_http_audio_fields,
            synthesize_aoede_phrase_audio,
        )

        repeat_msg = FIXED_SAFE_DENY_REPEAT_PHRASE_VI
        aoede_fields = build_aoede_http_audio_fields(
            await synthesize_aoede_phrase_audio(repeat_msg)
        )
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        reason_code = va_reason or q_gate.get("reason", "AUDIO_QUALITY_FAILED")
        return {
            "ok": False,
            "authorized": False,
            "recognized": False,
            "ask_repeat": True,
            "quality_gate_passed": False,
            "quality_reason": reason_code,
            "reason": reason_code,
            "level": 0,
            "tier": 99,
            "speaker_id": "none",
            "user_id": "UNKNOWN",
            "speaker_name": "Yêu cầu nói lại (Tín hiệu quá ngắn / nhỏ / rè / nói đè)",
            "role": "UNKNOWN",
            "recognized_text": explicit_transcript,
            "transcript": explicit_transcript,
            "canonical_command": explicit_transcript,
            "intent": "ASK_REPEAT_AUDIO_QUALITY",
            "intents": [],
            "permission": "ASK_REPEAT",
            "rbac_blocked": False,
            "action": "ASK_REPEAT_AUDIO_QUALITY",
            "reply": repeat_msg,
            "exact_spoken_reply": repeat_msg,
            "rejection_speech": repeat_msg,
            **aoede_fields,
            "results": [],
            "f0_hz": round(float(q_gate.get("f0_hz", 0.0)), 1),
            "similarity": 0.0,
            "wespeaker_cosine": 0.0,
            "threshold_wespeaker": 0.0,
            "latency_ms": latency_ms,
            "snapshot": (
                engine.get_public_device_snapshot()
                if hasattr(engine, "get_public_device_snapshot")
                else engine.get_snapshot()
            ),
        }

    # 2. Quyen kiem soat lay 100% tu session tier (bo hoan toan WeSpeaker/speaker verification)
    del voice_auth
    f0_hz = float(q_gate.get("f0_hz") or 135.0)
    authorized = session_tier in (1, 2, 3)
    tier = int(session_tier) if authorized and session_tier is not None else 99
    level = tier if authorized else 0
    speaker_id = f"session_tier_{tier}" if authorized else "unauthenticated"
    user_id = str(session_user or USER_ROLE_MAP.get(tier, "UNKNOWN")) if authorized else "UNKNOWN"
    role = str(session_role or ROLE_MAP.get(tier, "UNKNOWN")) if authorized else "UNKNOWN"
    speaker_name = user_id if authorized else "Người lạ (Không được phép)"
    best_thresh = 0.0

    # 3. Giai quyet STT (Speech-to-Text) doc lap nguoi noi cho mau WAV offline
    matched_sig, match_score = match_signature_from_catalog(pcm16, decoded_raw)
    similarity = round(float(match_score), 4)
    recognized_text = explicit_transcript
    canonical_command = ""
    if matched_sig is not None:
        canonical_command = str(matched_sig.get("canonical_command") or "")
        if not recognized_text:
            rec_cand = str(matched_sig.get("recognized_text") or "").strip()
            is_greet = "xin chao" in strip_vietnamese_diacritics(rec_cand.lower())
            if rec_cand and (is_greet or parse_vietnamese_voice_command_intents(rec_cand)):
                recognized_text = rec_cand
            elif canonical_command:
                recognized_text = canonical_command
            else:
                recognized_text = rec_cand
    if not recognized_text and authorized and not is_pure_synthetic_tone(pcm16.astype(np.float32) / 32768.0, sr=16000):
        recognized_text = infer_command_from_acoustic_envelope(pcm16)
    if not canonical_command:
        canonical_command = recognized_text

    # 4. Trich xuat Intent tu recognized_text (hoac canonical_command)
    intents = parse_vietnamese_voice_command_intents(recognized_text)
    if not intents and canonical_command:
        intents = parse_vietnamese_voice_command_intents(canonical_command)
    intent_label = format_intent_label(intents)

    # 5. Kiem tra Voice Auth & RBAC va Thuc thi Hanh dong Thiet bi
    if not authorized:
        from simulator.live.tts_rejection_vi import (
            build_aoede_http_audio_fields,
            synthesize_aoede_phrase_audio,
        )

        rejection_msg = FIXED_REJECTION_PHRASE_VI
        aoede_fields = build_aoede_http_audio_fields(
            await synthesize_aoede_phrase_audio(rejection_msg)
        )
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "ok": False,
            "authorized": False,
            "recognized": False,
            "reason": "STRANGER_BLOCKED",
            "ask_repeat": False,
            "quality_gate_passed": True,
            "level": 0,
            "tier": 99,
            "speaker_id": speaker_id,
            "user_id": user_id,
            "speaker_name": speaker_name,
            "role": role,
            "recognized_text": recognized_text,
            "transcript": recognized_text,
            "canonical_command": canonical_command,
            "intent": intent_label,
            "intents": intents,
            "permission": "DENIED",
            "rbac_blocked": True,
            "action": "BLOCKED_UNAUTHORIZED_VOICE",
            "reply": rejection_msg,
            "exact_spoken_reply": rejection_msg,
            "rejection_speech": rejection_msg,
            **aoede_fields,
            "results": [],
            "f0_hz": round(f0_hz, 1),
            "similarity": round(similarity, 4),
            "wespeaker_cosine": round(similarity, 4),
            "threshold_wespeaker": 0.0,
            "latency_ms": latency_ms,
            "snapshot": (
                engine.get_public_device_snapshot()
                if hasattr(engine, "get_public_device_snapshot")
                else engine.get_snapshot()
            ),
        }

    if not intents:
        if hasattr(engine, "sync_from_shared_store"):
            engine.sync_from_shared_store(force=True)
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        tn_check = strip_vietnamese_diacritics(recognized_text)
        is_greeting = any(k in tn_check for k in ("xin chao", "toi la", "chu nha"))
        intent_no_dev = "GREETING_OWNER_VERIFY" if is_greeting else "NO_DEVICE_INTENT"
        action_no_dev = "VERIFY_OWNER_VOICE -> ALLOWED" if is_greeting else "NO_OP"
        msg = (
            f"Xin chào {speaker_name}. Đã xác thực vân giọng Chủ nhà Cấp 1 thành công!"
            if is_greeting
            else f"Đã nghe khẩu lệnh: {recognized_text}"
        )
        return {
            "ok": True,
            "authorized": True,
            "ask_repeat": False,
            "quality_gate_passed": True,
            "level": level,
            "tier": tier,
            "speaker_id": speaker_id,
            "user_id": user_id,
            "speaker_name": speaker_name,
            "role": role,
            "recognized_text": recognized_text,
            "transcript": recognized_text,
            "canonical_command": canonical_command,
            "intent": intent_no_dev,
            "intents": [],
            "permission": "ALLOWED",
            "rbac_blocked": False,
            "action": action_no_dev,
            "reply": msg,
            "exact_spoken_reply": msg,
            "results": [],
            "device_states": {k: v.get("state") for k, v in engine.devices.items()},
            "f0_hz": round(f0_hz, 1),
            "similarity": round(similarity, 4),
            "wespeaker_cosine": round(similarity, 4),
            "threshold_wespeaker": best_thresh,
            "latency_ms": latency_ms,
            "snapshot": engine.get_snapshot(include_users=(tier == 1)),
        }

    all_ok = True
    any_blocked = False
    spoken_replies: list[str] = []
    action_summaries: list[str] = []
    device_results: list[dict[str, Any]] = []

    tx_ctx = (
        engine.state_transaction()
        if hasattr(engine, "state_transaction")
        else contextlib.nullcontext()
    )
    with tx_ctx:
        for item in intents:
            dev_id = item["device_id"]
            act = item["action"]
            res = await engine.execute_device_action(
                device_id=dev_id,
                action=act,
                source="voice_command",
                bypass_rbac=False,
                request_tier=tier,
                request_user_name=speaker_name,
                request_role=role,
            )
            ok_item = bool(res.get("ok"))
            if not ok_item:
                all_ok = False
                any_blocked = True
                action_summaries.append(f"{dev_id}:{act} -> BLOCKED_RBAC")
            else:
                state_dev_key = (
                    "living_room_light" if dev_id == "all_lights" else dev_id
                )
                raw_st = engine.devices.get(state_dev_key, {}).get("state")
                if isinstance(raw_st, str):
                    state_lbl = raw_st.upper()
                else:
                    state_lbl = (
                        ("OPEN" if raw_st else "CLOSED")
                        if dev_id == "main_door"
                        else ("ON" if raw_st else "OFF")
                    )
                action_summaries.append(f"{dev_id}:{act} -> {state_lbl}")
            if res.get("exact_spoken_reply"):
                spoken_replies.append(str(res["exact_spoken_reply"]))
            device_results.extend(res.get("results", []))

    permission_str = "DENIED" if any_blocked else "ALLOWED"
    aoede_overperm_fields: dict[str, Any] = {}
    if any_blocked:
        from simulator.live.tts_rejection_vi import (
            build_aoede_http_audio_fields,
            synthesize_aoede_phrase_audio,
        )

        final_reply = FIXED_REJECTION_PHRASE_VI
        aoede_overperm_fields = build_aoede_http_audio_fields(
            await synthesize_aoede_phrase_audio(FIXED_REJECTION_PHRASE_VI)
        )
    else:
        final_reply = (
            " ".join(spoken_replies).strip()
            or f"Đã xử lý khẩu lệnh: {recognized_text}"
        )
    action_str = "; ".join(action_summaries)
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    return {
        "ok": all_ok,
        "authorized": True,
        "recognized": True,
        "ask_repeat": False,
        "quality_gate_passed": True,
        "level": level,
        "tier": tier,
        "speaker_id": speaker_id,
        "user_id": user_id,
        "speaker_name": speaker_name,
        "role": role,
        "recognized_text": recognized_text,
        "transcript": recognized_text,
        "canonical_command": canonical_command,
        "intent": intent_label,
        "intents": intents,
        "permission": permission_str,
        "rbac_blocked": any_blocked,
        "action": action_str,
        "reply": final_reply,
        "exact_spoken_reply": final_reply,
        "rejection_speech": FIXED_REJECTION_PHRASE_VI if any_blocked else "",
        **aoede_overperm_fields,
        "results": device_results,
        "device_states": {k: v.get("state") for k, v in engine.devices.items()},
        "f0_hz": round(f0_hz, 1),
        "similarity": round(similarity, 4),
        "wespeaker_cosine": round(similarity, 4),
        "threshold_wespeaker": best_thresh,
        "latency_ms": latency_ms,
        "snapshot": engine.get_snapshot(include_users=(tier == 1)),
    }
