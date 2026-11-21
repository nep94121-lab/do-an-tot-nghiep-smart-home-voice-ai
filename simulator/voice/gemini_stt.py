"""Fast production Vietnamese STT using Gemini Flash-Lite with acoustic gate and Zipformer short-clip rescue."""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import threading
import time
import wave
from typing import Any

import numpy as np

from simulator.api.deps import load_key, safe_str
from simulator.voice.vietnamese_stt import (
    _analyze_and_preprocess_audio,
    _clean_whisper_text,
    _is_muffled_babble_only,
    _is_plausible_short_reply_or_command,
    transcribe_short_zipformer30m_pcm16k,
    transcribe_vietnamese_offline_pcm16k,
)

LOG = logging.getLogger("simulator.voice.gemini_stt")

_CLIENT_LOCK = threading.Lock()
_CLIENTS_BY_KEY_HASH: dict[str, Any] = {}

_COOLDOWN_LOCK = threading.Lock()
_MODEL_COOLDOWN_UNTIL: dict[str, float] = {}
_MODEL_429_STREAK: dict[str, int] = {}

_DEFAULT_MODEL_CHAIN: tuple[str, ...] = (
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
)
_DEFAULT_PRIMARY_MODEL = _DEFAULT_MODEL_CHAIN[0]
_FALLBACK_MODEL = _DEFAULT_MODEL_CHAIN[-1]

_ALNUM_GARBAGE_RE = re.compile(r"[A-Z0-9]{4,}")
_ALLOWED_ALNUM_CODES: frozenset[str] = frozenset({"KY037", "KY038", "DHT11"})

_DEVICE_CORROBORATION_CUES: dict[str, tuple[str, ...]] = {
    "main_door": ("cua", "chinh", "cong", "nha"),
    "living_room_light": ("den", "khach", "phong", "bong"),
    "bedroom_light": ("den", "ngu", "buong", "phong", "bong"),
    "garden_pump": ("bom", "tuoi", "cay", "vuon", "may", "nuoc"),
    "alarm_siren": ("coi", "bao", "dong", "hu", "trom"),
    "speaker_amp": ("loa", "nguon", "mach", "am", "ly", "pam8403"),
}

_NOISE_TOKEN_RE = re.compile(
    r"^(?:"
    r"\[?\s*noise\s*\]?|<\s*noise\s*>|\(\s*noise\s*\)|"
    r"\[?\s*silence\s*\]?|<\s*silence\s*>|\(\s*silence\s*\)|"
    r"\[?\s*inaudible\s*\]?|\[?\s*blank_audio\s*\]?|"
    r"\[?\s*tiếng\s*ồn\s*\]?|\[?\s*im\s*lặng\s*\]?|"
    r"[\s.,!?;:\-–—…'\"`~*#\[\]()<>]+"
    r")$",
    re.IGNORECASE,
)

_BASE_ASR_PROMPT = (
    "Bạn là bộ nhận dạng giọng nói (ASR) tiếng Việt chính xác cao.\n"
    "Hãy lắng nghe kỹ giọng người nói chính (lớn nhất ở tiền cảnh) và chép lại CHÍNH XÁC NGUYÊN VĂN lời họ nói.\n"
    "Quy tắc bắt buộc:\n"
    "- Chỉ xuất ra đúng lời nói nguyên văn, không giải thích, không thêm lời bình.\n"
    "- Chú ý thật kỹ âm tiết đầu tiên: phân biệt rõ 'tắt' và 'bật', 'đóng' và 'mở', 'xóa' và 'tạo', "
    "'còi' và 'tới'/'rồi'; tuyệt đối không bỏ sót động từ đầu câu.\n"
    "- TUYỆT ĐỐI KHÔNG tự bịa hoặc tự hoàn chỉnh từ không được nói: nếu chỉ nghe thấy 'cửa chính' "
    "thì chỉ xuất 'cửa chính' (không thêm 'mở'); nếu chỉ nghe thấy 'bật lên đi' thì chỉ xuất 'bật lên đi' "
    "(không thêm 'đèn').\n"
    "- Giữ nguyên văn các từ khóa phổ biến nếu thực sự nghe thấy trong câu (như 'reset', 'liên kết', 'đặt lịch', "
    "'xóa liên kết', 'tạo lệnh', 'khôi phục cài đặt gốc', 'đất khô', 'tiếng động lớn'), không thay bằng từ đồng âm khác.\n"
    "- Giữ nguyên các câu trả lời ngắn 1-2 âm tiết như: ok, được, có, ừ, không, thôi, hủy, đồng ý.\n"
    "- Nếu người nói dùng ngoại ngữ (Anh, Pháp, Hàn, Tây Ban Nha, Đức...), chép lại nguyên văn bằng ngôn ngữ đó, "
    "KHÔNG dịch sang tiếng Việt.\n"
    "- Nếu chỉ có tiếng ồn, nhiễu tĩnh hoặc tiếng nói nền hỗn tạp không rõ lời người nói chính ở tiền cảnh, "
    "chỉ xuất đúng `[NOISE]`."
)

_SHORT_PENDING_CONFIRM_PROMPT = (
    "Bạn là bộ nhận dạng giọng nói (ASR) tiếng Việt chính xác cao.\n"
    "Hệ thống đang chờ người dùng xác nhận. Hãy lắng nghe và chép lại CHÍNH XÁC NGUYÊN VĂN từ/câu ngắn người dùng nói "
    "(có thể chỉ là 1-2 âm tiết như: ok, được, có, ừ, đồng ý, không, thôi, hủy, hoặc một câu ngắn khác).\n"
    "- Chỉ xuất đúng lời nói nguyên văn, KHÔNG tự thêm hay bịa câu lệnh dài.\n"
    "- Nếu là ngoại ngữ, chép lại nguyên văn bằng ngôn ngữ đó.\n"
    "- CHỈ xuất đúng `[NOISE]` nếu hoàn toàn không có tiếng người nói."
)


def _get_genai_client(api_key: str) -> Any:
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:24]
    cached = _CLIENTS_BY_KEY_HASH.get(key_hash)
    if cached is not None:
        return cached
    with _CLIENT_LOCK:
        cached = _CLIENTS_BY_KEY_HASH.get(key_hash)
        if cached is not None:
            return cached
        from google import genai

        client = genai.Client(api_key=api_key)
        _CLIENTS_BY_KEY_HASH[key_hash] = client
        return client


def _get_candidate_models() -> list[str]:
    env_model = os.environ.get("SMARTHOME_GEMINI_STT_MODEL", "").strip()
    ordered: list[str] = []
    for name in ([env_model] if env_model else []) + list(_DEFAULT_MODEL_CHAIN):
        if name and name not in ordered:
            ordered.append(name)
    now = time.monotonic()
    with _COOLDOWN_LOCK:
        return [m for m in ordered if _MODEL_COOLDOWN_UNTIL.get(m, 0.0) <= now]


def _record_model_success(model_name: str) -> None:
    with _COOLDOWN_LOCK:
        _MODEL_429_STREAK[model_name] = 0
        _MODEL_COOLDOWN_UNTIL.pop(model_name, None)


def _record_model_error(model_name: str, exc: Exception) -> None:
    err_low = safe_str(exc).lower()
    code = getattr(exc, "code", None)
    now = time.monotonic()
    with _COOLDOWN_LOCK:
        if code == 429 or "429" in err_low or "resource_exhausted" in err_low:
            streak = _MODEL_429_STREAK.get(model_name, 0) + 1
            _MODEL_429_STREAK[model_name] = streak
            is_daily = (
                "perday" in err_low
                or "per_day" in err_low
                or "per day" in err_low
                or ("quota" in err_low and "day" in err_low)
            )
            if is_daily:
                cooldown = 3600.0
            else:
                cooldown = 35.0 if streak >= 3 else 15.0
            _MODEL_COOLDOWN_UNTIL[model_name] = now + cooldown
        elif code == 404 or "404" in err_low or "not_found" in err_low:
            _MODEL_COOLDOWN_UNTIL[model_name] = now + 600.0


def _float32_to_wav16k_bytes(audio_f32: np.ndarray, *, pad_short: bool = True) -> bytes:
    samples = audio_f32
    if pad_short:
        lead_pad = np.zeros(int(16000 * 0.30), dtype=np.float32)
        trail_pad = np.zeros(int(16000 * 0.40), dtype=np.float32)
        samples = np.concatenate([lead_pad, samples, trail_pad])
    pcm16 = np.clip(np.round(samples * 32767.0), -32767, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(pcm16.tobytes())
    return buf.getvalue()


def _compute_noise_ratio(audio_f32: np.ndarray, sr: int = 16000) -> float:
    """Fast (<1ms) frame-level background floor to speech peak ratio (p15_rms / p90_rms)."""
    frame_len = max(1, int(sr * 0.02))
    n_frames = audio_f32.size // frame_len
    if n_frames < 6:
        return 0.0
    frames = audio_f32[: n_frames * frame_len].reshape(n_frames, frame_len)
    frame_rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    p15 = float(np.percentile(frame_rms, 15))
    p90 = float(np.percentile(frame_rms, 90))
    return p15 / max(p90, 1e-6)


def _is_alnum_garbage(text: str) -> bool:
    cleaned = re.sub(r"[.!?,\s]+$", "", str(text or "").strip())
    if not cleaned or cleaned.upper() in _ALLOWED_ALNUM_CODES:
        return False
    return bool(_ALNUM_GARBAGE_RE.fullmatch(cleaned))


def _local_corroborates_device_intents(
    local_text: str,
    intents: list[dict[str, str]],
) -> bool:
    """Return True if local_text shares or phonetically matches at least one target device cue."""
    if not local_text or not intents:
        return False
    try:
        from simulator.voice.vietnamese_policy import (
            _fuzzy_ratio,
            _vi_phonetic_skeleton,
            strip_vi_accents,
        )
    except Exception:
        return True

    norm_local = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(local_text.lower())).split())
    local_tokens = norm_local.split()
    if not local_tokens:
        return False
    local_phons = [_vi_phonetic_skeleton(tok) for tok in local_tokens if len(tok) >= 2]

    target_cues: set[str] = set()
    for it in intents:
        dev_id = str(it.get("device_id") or "")
        for cue in _DEVICE_CORROBORATION_CUES.get(dev_id, ()):
            target_cues.add(cue)
    if not target_cues:
        return True

    for cue in target_cues:
        if cue in local_tokens:
            return True
        cue_phon = _vi_phonetic_skeleton(cue)
        if len(cue_phon) < 2:
            continue
        for tok, tok_phon in zip(local_tokens, local_phons):
            if len(tok) < 2:
                continue
            if _fuzzy_ratio(tok, cue) >= 75.0 or _fuzzy_ratio(tok_phon, cue_phon) >= 75.0:
                return True
    return False


def _run_high_noise_hallucination_gate(
    *,
    gemini_text: str,
    pcm16: np.ndarray,
    sr: int,
    duration_sec: float,
    noise_ratio: float,
    used_model: str,
    t0: float,
) -> dict[str, Any] | None:
    """Cross-check Gemini direct device commands against local STT on high background noise (SNR <= 10 dB)."""
    if noise_ratio < 0.14 or not gemini_text:
        return None
    try:
        from simulator.voice.vietnamese_policy import (
            _UNSUPPORTED_DEVICE_RE,
            _extract_clause_action,
            _extract_clause_device,
            classify_small_talk_vi,
            normalize_vietnamese_utterance,
            parse_direct_device_intents_vi,
            strip_vi_accents,
        )
    except Exception:
        return None

    gemini_intents = parse_direct_device_intents_vi(gemini_text)
    if not gemini_intents:
        return None

    # Always use fast Zipformer-30M (~250ms) for high-noise corroboration: faster than 70M
    # and markedly more sensitive at SNR 5-10 dB (e.g. recovers 'đèn' when 70M drops it).
    local_res = transcribe_short_zipformer30m_pcm16k(pcm16, sr=sr)
    local_txt = str(local_res.get("text") or "").strip()
    local_engine = str(local_res.get("stt_engine") or "local")

    # 1. Local clearly hears small talk (e.g. 'chào bạn', 'bạn là ai') -> override Gemini hallucination
    if local_txt and classify_small_talk_vi(local_txt) is not None:
        return {
            "ok": True,
            "text": local_txt,
            "confidence": 0.85,
            "is_noise": False,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": f"gemini:{used_model}+noise_gate_smalltalk:{local_engine}",
        }

    local_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(local_txt.lower())).split())
    # 2. Local hears an unsupported device (e.g. 'cửa cuốn', 'rèm cửa', 'quạt') -> prevent false action
    if local_norm and _UNSUPPORTED_DEVICE_RE.search(f" {local_norm} "):
        return {
            "ok": True,
            "text": local_txt,
            "confidence": 0.85,
            "is_noise": False,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": f"gemini:{used_model}+noise_gate_unsupported:{local_engine}",
        }

    # 3. Severe noise guard (strictly SNR <= 5 dB, noise_ratio >= 0.31; SNR 10 dB stays <= 0.287)
    gemini_words = re.sub(r"[?!.,;:]+$", "", gemini_text.strip()).split()
    if noise_ratio >= 0.31 and len(gemini_words) <= 5:
        local_intents = parse_direct_device_intents_vi(local_txt) if local_txt else []
        if local_intents:
            return None

        local_clean = normalize_vietnamese_utterance(local_txt) if local_txt else ""
        local_clean_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(local_clean.lower())).split())
        local_dev = _extract_clause_device(local_clean_norm) if local_clean_norm else None
        local_act = _extract_clause_action(local_clean_norm, local_dev) if local_clean_norm else None

        # Local heard concise bare action verb (<=3 words) with NO device noun (e.g. 'bật lên đi') -> clarify
        if local_act is not None and local_dev is None and len(local_clean_norm.split()) <= 3:
            return {
                "ok": True,
                "text": local_txt,
                "confidence": 0.82,
                "is_noise": False,
                "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                "stt_engine": f"gemini:{used_model}+noise_gate_bare_verb:{local_engine}",
            }

        # Local heard a concise bare device noun (<=3 words) with NO action verb (e.g. 'cửa chính')
        # on a short command -> return local so NLU clarifies instead of guessing an action.
        if (
            local_dev is not None
            and local_act is None
            and len(local_clean_norm.split()) <= 3
            and len(gemini_words) <= 4
        ):
            return {
                "ok": True,
                "text": local_txt,
                "confidence": 0.82,
                "is_noise": False,
                "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                "stt_engine": f"gemini:{used_model}+noise_gate_bare_device:{local_engine}",
            }

        # Zero device-cue corroboration from local STT on severe noise -> reject hallucinated command.
        # If local abstained completely (empty string), still reject ultra-short <=2-word commands
        # (e.g. 'Bật đèn.', 'Tắt loa.') while allowing 3+ word specific commands to preserve SNR 5 recall.
        if not _local_corroborates_device_intents(local_txt, gemini_intents):
            if local_txt or len(gemini_words) <= 2:
                return {
                    "ok": False,
                    "text": "",
                    "confidence": 0.0,
                    "is_noise": True,
                    "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                    "stt_engine": f"gemini:{used_model}+noise_gate_reject:{local_engine}",
                }

    return None


def _clean_gemini_transcript(raw_text: str) -> str:
    txt = str(raw_text or "").strip()
    if not txt:
        return ""
    # Remove wrapping quotes or code fences if model emits them
    txt = re.sub(r"^```[^\n]*\n?|\n?```$", "", txt).strip()
    txt = txt.strip('"\'`').strip()
    txt = re.sub(r"\s+", " ", txt).strip()
    if not txt or _NOISE_TOKEN_RE.match(txt):
        return ""
    # Strip embedded [NOISE] / <noise> tags
    txt = re.sub(r"\[(?:noise|silence|inaudible)\]|<(?:noise|silence)>|\((?:noise|silence)\)", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\s+", " ", txt).strip()
    if not txt or _NOISE_TOKEN_RE.match(txt):
        return ""
    return _clean_whisper_text(txt)


def _classify_confirm_safe(text: str) -> str | None:
    if not text:
        return None
    try:
        from simulator.automation_nlu import _classify_confirmation_utterance

        return _classify_confirmation_utterance(text)
    except Exception:
        return None


def _is_likely_short_gibberish(text: str) -> bool:
    """Detect single-word mismatched output on a <0.95s clip (e.g. 'được' -> 'lịch')."""
    if not text:
        return True
    tokens = re.sub(r"[?!.,;:]+$", "", text.strip().lower()).split()
    if len(tokens) > 2:
        return False
    return not _is_plausible_short_reply_or_command(text)


def transcribe_vietnamese_gemini_pcm16k(
    pcm16: np.ndarray,
    sr: int = 16000,
    *,
    has_pending_confirmation: bool = False,
) -> dict[str, Any]:
    """Transcribe 16kHz mono PCM16 Vietnamese speech via Gemini Flash-Lite with fast local rescue."""
    t0 = time.perf_counter()
    audio_f32, is_noise = _analyze_and_preprocess_audio(pcm16, sr=sr)
    if is_noise or audio_f32.size == 0:
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": True,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": "acoustic_gate",
        }

    api_key = load_key()
    if not api_key:
        res = transcribe_vietnamese_offline_pcm16k(pcm16, sr=sr)
        res["stt_engine"] = f"offline_no_key:{res.get('stt_engine', 'offline')}"
        return res

    duration_sec = float(audio_f32.size) / 16000.0
    is_short_clip = duration_sec < 1.25
    muffled_babble = _is_muffled_babble_only(audio_f32, sr=16000)
    noise_ratio = _compute_noise_ratio(audio_f32, sr=16000)
    wav_bytes = _float32_to_wav16k_bytes(audio_f32, pad_short=True)

    if has_pending_confirmation and is_short_clip:
        prompt = _SHORT_PENDING_CONFIRM_PROMPT
    else:
        prompt = _BASE_ASR_PROMPT

    models_to_try = _get_candidate_models()

    gemini_text = ""
    used_model = ""
    api_failed_all = True

    if models_to_try:
        try:
            from google.genai import types

            client = _get_genai_client(api_key)
            cfg = types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=64,
            )
            audio_part = types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav")

            for model_name in models_to_try:
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=[prompt, audio_part],
                        config=cfg,
                    )
                    raw_out = getattr(resp, "text", None) or ""
                    gemini_text = _clean_gemini_transcript(raw_out)
                    used_model = model_name
                    _record_model_success(model_name)
                    api_failed_all = False
                    break
                except Exception as exc:
                    _record_model_error(model_name, exc)
                    LOG.warning(
                        "Gemini STT attempt failed on %s (%s): %s",
                        model_name,
                        type(exc).__name__,
                        safe_str(exc)[:180],
                    )
        except Exception as exc:
            LOG.warning("Gemini STT client init failed (%s): %s", type(exc).__name__, safe_str(exc)[:180])

    if api_failed_all:
        fb = transcribe_vietnamese_offline_pcm16k(pcm16, sr=sr)
        fb["stt_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        fb["stt_engine"] = f"offline_fallback:{fb.get('stt_engine', 'offline')}"
        return fb

    # Reject random alphanumeric garbage tokens (e.g. 'FGH9A') and fall back to local offline STT.
    if gemini_text and _is_alnum_garbage(gemini_text):
        fb = transcribe_vietnamese_offline_pcm16k(pcm16, sr=sr)
        fb["stt_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        fb["stt_engine"] = f"gemini:{used_model}+offline_garbage_fallback:{fb.get('stt_engine', 'offline')}"
        return fb

    # Priority short-clip confirmation rescue (<1.25s with pending confirmation):
    # If Gemini didn't return a recognized confirmation/cancel word, check Zipformer-30M (~300ms).
    if has_pending_confirmation and is_short_clip and _classify_confirm_safe(gemini_text) is None:
        z30 = transcribe_short_zipformer30m_pcm16k(pcm16, sr=sr)
        z30_txt = str(z30.get("text") or "").strip()
        if z30_txt and _classify_confirm_safe(z30_txt) is not None:
            return {
                "ok": True,
                "text": z30_txt,
                "confidence": 0.90,
                "is_noise": False,
                "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                "stt_engine": f"gemini:{used_model}+zipformer_30m_confirm_rescue",
            }

    # General short-utterance rescue (<1.25s):
    # Rescue empty/noise or single-word gibberish (e.g. 'được' -> 'lịch') using fast local Zipformer-30M.
    if is_short_clip and not muffled_babble and (not gemini_text or _is_likely_short_gibberish(gemini_text)):
        z30 = transcribe_short_zipformer30m_pcm16k(pcm16, sr=sr)
        z30_txt = str(z30.get("text") or "").strip()
        if z30_txt:
            if not gemini_text or _is_plausible_short_reply_or_command(z30_txt):
                return {
                    "ok": True,
                    "text": z30_txt,
                    "confidence": 0.86,
                    "is_noise": False,
                    "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                    "stt_engine": f"gemini:{used_model}+zipformer_30m_short_rescue",
                }
        elif not gemini_text:
            fb = transcribe_vietnamese_offline_pcm16k(pcm16, sr=sr)
            if fb.get("ok") and fb.get("text"):
                fb["stt_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
                fb["stt_engine"] = f"gemini:{used_model}+offline_short_rescue:{fb.get('stt_engine', 'offline')}"
                return fb

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    if not gemini_text:
        # If Gemini returned [NOISE] on a non-babble, non-white-noise clip (e.g. low-gain mumbler or SNR10 white),
        # give fast local Zipformer one rescue pass and accept only plausible replies/multi-word speech.
        if not muffled_babble and not is_short_clip:
            fb = transcribe_vietnamese_offline_pcm16k(pcm16, sr=sr)
            fb_txt = str(fb.get("text") or "").strip()
            if fb.get("ok") and fb_txt and (
                _is_plausible_short_reply_or_command(fb_txt) or len(fb_txt.split()) >= 2
            ):
                return {
                    "ok": True,
                    "text": fb_txt,
                    "confidence": float(fb.get("confidence") or 0.80),
                    "is_noise": False,
                    "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                    "stt_engine": f"gemini:{used_model}+offline_noise_rescue:{fb.get('stt_engine', 'offline')}",
                }
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": True,
            "stt_ms": elapsed_ms,
            "stt_engine": f"gemini:{used_model}",
        }

    # Protect against muffled babble-only audio returning random 1-2 nonsense words
    if muffled_babble and len(gemini_text.split()) <= 3 and not _is_plausible_short_reply_or_command(gemini_text):
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": True,
            "stt_ms": elapsed_ms,
            "stt_engine": f"gemini:{used_model}:babble_guard",
        }

    # High-Noise Dual-Engine Hallucination Gate (bypasses clean/SNR20/reverb/low_gain/clipping/speed where noise_ratio < 0.14)
    gated = _run_high_noise_hallucination_gate(
        gemini_text=gemini_text,
        pcm16=pcm16,
        sr=sr,
        duration_sec=duration_sec,
        noise_ratio=noise_ratio,
        used_model=used_model,
        t0=t0,
    )
    if gated is not None:
        return gated

    return {
        "ok": True,
        "text": gemini_text,
        "confidence": 0.94,
        "is_noise": False,
        "stt_ms": elapsed_ms,
        "stt_engine": f"gemini:{used_model}",
    }
