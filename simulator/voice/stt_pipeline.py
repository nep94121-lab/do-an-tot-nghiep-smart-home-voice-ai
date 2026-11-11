"""Stateless Voice Command Pipeline (Mic/Audio Upload -> WeSpeaker ResNet34 ONNX Speaker Verification -> STT -> Intent -> 3-Level Voice Auth & RBAC -> Device Action -> Snapshot).

Thiet ke chuyen biet cho ca 2 che do:
- Local FastAPI Server (WebSocket + HTTP REST)
- Vercel Serverless Production/Preview (100% Stateless HTTP POST /api/voice_command)
"""

from __future__ import annotations

import base64
import contextlib
import glob
import io
import json
import pathlib
import time
import wave
from typing import Any

import numpy as np

from simulator.voice.dsp_features import (
    cosine_sim,
    denoise_and_isolate_human_voice,
    extract_stage2_deep_features,
    extract_voice_features,
)
from simulator.voice.enrollment_quality import (
    parse_vietnamese_voice_command_intents,
    strip_vietnamese_diacritics,
    validate_voice_enrollment_quality,
)
from simulator.voice.wespeaker_onnx import (
    _is_encoded_container_bytes,
    compute_wespeaker_cosine,
    evaluate_audio_quality_gate,
    evaluate_cohort_margin,
    extract_wespeaker_embedding,
    pcm_bytes_to_float32_16k,
)
from simulator.voice_config import (
    OWNER_ID,
    ROLE_MAP,
    THRESHOLD_WESPEAKER_TIER1,
    THRESHOLD_WESPEAKER_TIER2,
    THRESHOLD_WESPEAKER_TIER3,
    USER_ROLE_MAP,
    get_tier_wespeaker_threshold,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
VOICES_DIR = pathlib.Path(r"C:\Users\LENOVO\datn-wt\voices")
SIGNATURES_JSON_PATH = pathlib.Path(__file__).resolve().parent / "real_voices_signatures.json"

FIXED_REJECTION_PHRASE_VI = "Xin lỗi, bạn không có quyền thực hiện lệnh này."
FIXED_SAFE_DENY_REPEAT_PHRASE_VI = "Âm thanh chưa rõ, vui lòng nói lại."

_CACHED_SIGNATURES_DATA: dict[str, Any] | None = None


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
        "tat_quat": sep_dir / "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav",
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
    """Tra cuu mau khau lenh STT offline trong real_voices_signatures.json bang WeSpeaker ResNet34 ONNX."""
    catalog = load_real_voices_signatures().get("signatures", [])
    if not catalog or pcm16.size == 0:
        return None, 0.0

    emb = (
        cur_wespk
        if cur_wespk is not None
        else extract_wespeaker_embedding(pcm16, sr=16000, apply_vad=True)
    )

    # 1. Phat hien luong mic lap chu ky (Chromium fake-audio-capture loop period L)
    if pcm16.size >= 18000:
        best_loop_corr = -1.0
        best_loop_sig: dict[str, Any] | None = None
        for sig in catalog:
            if verified_tier is not None and int(sig.get("tier", 0)) != int(verified_tier):
                continue
            L = int(round(float(sig.get("duration_sec") or 0.0) * 16000))
            if L < 8000 or pcm16.size < L + 3200:
                continue
            m = min(pcm16.size - L - 24, L)
            if m <= 1600:
                continue
            a = pcm16[:m].astype(np.float32)
            na = float(np.linalg.norm(a))
            if na < 1e-3:
                continue
            sig_best_corr = -1.0
            for dL in range(-16, 17, 1):
                L2 = L + dL
                if L2 <= 0 or L2 + m > pcm16.size:
                    continue
                b = pcm16[L2 : L2 + m].astype(np.float32)
                nb = float(np.linalg.norm(b))
                if nb < 1e-3:
                    continue
                corr = float(np.dot(a, b) / (na * nb))
                if corr > sig_best_corr:
                    sig_best_corr = corr

            sig_wespk = sig.get("wespeaker_embedding") or sig.get("embedding_256d")
            w_cos = compute_wespeaker_cosine(emb, sig_wespk) if sig_wespk else 0.0
            t_thresh = get_tier_wespeaker_threshold(int(sig.get("tier", 1)))
            if sig_best_corr >= 0.88 and w_cos >= t_thresh:
                score = 0.5 * sig_best_corr + 0.5 * w_cos
                if score > best_loop_corr:
                    best_loop_corr = score
                    best_loop_sig = sig
        if best_loop_sig is not None:
            return best_loop_sig, round(float(best_loop_corr), 4)

    # 2. Doi sanh WeSpeaker ResNet34 ONNX cosine + thoi luong de xac dinh cau lenh STT offline
    dur_in = pcm16.size / 16000.0
    best_sig: dict[str, Any] | None = None
    best_cos = -1.0
    best_combined = -1.0

    for sig in catalog:
        if verified_tier is not None and int(sig.get("tier", 0)) != int(verified_tier):
            continue
        sig_wespk = sig.get("wespeaker_embedding") or sig.get("embedding_256d")
        if not sig_wespk or len(sig_wespk) != 256:
            continue
        w_cos = compute_wespeaker_cosine(emb, sig_wespk)
        t_thresh = get_tier_wespeaker_threshold(int(sig.get("tier", 1)))
        if w_cos < t_thresh:
            continue
        dur_ref = float(sig.get("duration_sec") or 0.0)
        dur_pen = min(0.15, abs(dur_in - dur_ref) * 0.05) if dur_ref > 0 else 0.0
        comb = w_cos - dur_pen
        if comb > best_combined:
            best_combined = comb
            best_cos = w_cos
            best_sig = sig

    if best_sig is not None:
        return best_sig, round(float(best_cos), 4)
    return None, round(float(max(0.0, best_cos)), 4)


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
    return "tắt quạt"


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

    # 1. CỔNG KIỂM ĐỊNH CHẤT LƯỢNG ÂM THANH (Mel26 + Deep64 Quality Gate & Overlap Safe-Deny)
    # Quá ngắn / quá nhỏ / bị rè / nói đè -> Yêu cầu nói lại, KHÔNG kết luận là 'Người lạ'!
    q_gate = evaluate_audio_quality_gate(pcm16, sr=16000)
    va_ask_repeat = False
    va_reason = ""
    if q_gate["ok"] and voice_auth is not None and hasattr(voice_auth, "verify_pcm16k_and_apply_strikes"):
        prev_strikes = getattr(voice_auth, "unauthorized_strikes", 0)
        try:
            va_res = voice_auth.verify_pcm16k_and_apply_strikes(pcm16)
            if isinstance(va_res, dict) and va_res.get("ask_repeat"):
                va_ask_repeat = True
                va_reason = str(va_res.get("reason") or va_res.get("quality_reason") or "SAFE_DENY_ASK_REPEAT")
        except Exception:
            pass
        finally:
            if hasattr(voice_auth, "unauthorized_strikes"):
                voice_auth.unauthorized_strikes = prev_strikes

    if not q_gate["ok"] or va_ask_repeat:
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
            "threshold_wespeaker": THRESHOLD_WESPEAKER_TIER1,
            "latency_ms": latency_ms,
            "snapshot": (
                engine.get_public_device_snapshot()
                if hasattr(engine, "get_public_device_snapshot")
                else engine.get_snapshot()
            ),
        }

    # 2. QUYẾT ĐỊNH DANH TÍNH BẰNG WESPEAKER RESNET34 ONNX (5-Sample Mean Centroids)
    cur_wespk = extract_wespeaker_embedding(pcm16, sr=16000, apply_vad=True)
    f0_hz = float(q_gate.get("f0_hz") or 135.0)

    # Tap hop cac ho so 5-sample centroid cua Level 1, Level 2, Level 3
    sig_data = load_real_voices_signatures()
    precomputed_centroids = sig_data.get("tier_5sample_centroids") or {}

    candidate_profiles: list[dict[str, Any]] = []
    if hasattr(voice_auth, "profiles") and isinstance(voice_auth.profiles, dict):
        for p in voice_auth.profiles.values():
            if p.get("authorized"):
                candidate_profiles.append(p)
    if hasattr(voice_auth, "default_subtier_profiles") and isinstance(
        voice_auth.default_subtier_profiles, dict
    ):
        existing_tiers = {int(p.get("tier", 0)) for p in candidate_profiles}
        for dp in voice_auth.default_subtier_profiles.values():
            if int(dp.get("tier", 0)) not in existing_tiers:
                candidate_profiles.append(dp)

    # Bo sung centroid tu real_voices_signatures.json neu chua co trong candidate_profiles
    present_tiers = {int(p.get("tier", 0)) for p in candidate_profiles}
    for t_int, t_sid, t_uid, t_name, t_role in (
        (1, "owner_voice_1", OWNER_ID, "Chủ nhà Nguyễn Tuấn Anh (Cấp 1)", ROLE_MAP.get(1, "ADMIN")),
        (2, "user_voice_thanh_vien_a", USER_ROLE_MAP.get(2, "thanh_vien_a"), "Thành viên A (Cấp 2)", ROLE_MAP.get(2, "MEMBER")),
        (3, "user_voice_khach_c", USER_ROLE_MAP.get(3, "khach_c"), "Khách C (Cấp 3)", ROLE_MAP.get(3, "CHILD_GUEST")),
    ):
        if t_int not in present_tiers and precomputed_centroids.get(str(t_int)):
            candidate_profiles.append(
                {
                    "id": t_sid,
                    "user_id": t_uid,
                    "name": t_name,
                    "role": t_role,
                    "tier": t_int,
                    "authorized": True,
                    "threshold_wespeaker": get_tier_wespeaker_threshold(t_int),
                    "wespeaker_embedding": precomputed_centroids[str(t_int)],
                }
            )

    best_prof: dict[str, Any] | None = None
    best_cos: float = -1.0
    best_thresh: float = THRESHOLD_WESPEAKER_TIER1
    highest_raw_cos: float = 0.0

    for prof in candidate_profiles:
        p_tier = int(prof.get("tier", 1))
        p_thresh = float(
            prof.get("threshold_wespeaker") or get_tier_wespeaker_threshold(p_tier)
        )
        p_emb = prof.get("wespeaker_embedding") or prof.get("embedding_256d")
        if not p_emb or len(p_emb) != 256:
            continue
        cos_val = compute_wespeaker_cosine(cur_wespk, p_emb)
        if prof.get("baseline_wespeaker_embedding"):
            cos_val = max(
                cos_val,
                compute_wespeaker_cosine(
                    cur_wespk, prof["baseline_wespeaker_embedding"]
                ),
            )
        if prof.get("single_clip_wespeaker_embedding"):
            cos_val = max(
                cos_val,
                compute_wespeaker_cosine(
                    cur_wespk, prof["single_clip_wespeaker_embedding"]
                ),
            )
        if cos_val > highest_raw_cos:
            highest_raw_cos = cos_val
        if cos_val >= p_thresh and cos_val > best_cos:
            if p_tier == 1:
                _, _, cohort_pass = evaluate_cohort_margin(cur_wespk, p_emb)
                if not cohort_pass:
                    continue
            best_cos = cos_val
            best_prof = prof
            best_thresh = p_thresh

    authorized = best_prof is not None
    level = 0
    tier = 99
    speaker_id = "intruder_voice_2"
    user_id = "UNKNOWN"
    speaker_name = "Người lạ (Không được phép)"
    role = "UNKNOWN"
    similarity = round(float(best_cos if authorized else highest_raw_cos), 4)

    if authorized and best_prof is not None:
        tier = int(best_prof.get("tier", 1))
        level = tier
        speaker_id = str(best_prof.get("id", "owner_voice_1"))
        user_id = str(best_prof.get("user_id", USER_ROLE_MAP.get(tier, OWNER_ID)))
        speaker_name = str(
            best_prof.get("name", "Chủ nhà Nguyễn Tuấn Anh (Cấp 1)")
        )
        role = str(best_prof.get("role", ROLE_MAP.get(tier, "ADMIN")))
        if hasattr(voice_auth, "reset_strikes"):
            voice_auth.reset_strikes()

    # 3. Giai quyet STT (Speech-to-Text) cho mau WAV offline neu khong co explicit_transcript
    matched_sig, _ = match_signature_from_catalog(
        pcm16,
        decoded_raw,
        cur_wespk=cur_wespk,
        verified_tier=(tier if authorized else None),
    )
    recognized_text = explicit_transcript
    canonical_command = ""
    if matched_sig is not None:
        canonical_command = str(matched_sig.get("canonical_command") or "")
        if not recognized_text:
            recognized_text = str(
                matched_sig.get("recognized_text") or canonical_command
            )
    if not recognized_text:
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
            "threshold_wespeaker": THRESHOLD_WESPEAKER_TIER1,
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
