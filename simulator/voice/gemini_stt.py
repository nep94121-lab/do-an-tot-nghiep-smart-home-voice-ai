"""Fast production Vietnamese STT using Gemini Flash-Lite with acoustic gate and Zipformer short-clip rescue."""

from __future__ import annotations

import collections
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
    enhance_white_noise_audio,
    is_broadband_white_noise,
    transcribe_short_zipformer30m_pcm16k,
    transcribe_vietnamese_offline_pcm16k,
)

LOG = logging.getLogger("simulator.voice.gemini_stt")

_CLIENT_LOCK = threading.Lock()
_CLIENTS_BY_KEY_HASH: dict[str, Any] = {}

_COOLDOWN_LOCK = threading.Lock()
_MODEL_COOLDOWN_UNTIL: dict[str, float] = {}
_MODEL_429_STREAK: dict[str, int] = {}

_PACE_LOCK = threading.Lock()
_GEMINI_CALL_TIMESTAMPS: collections.deque[float] = collections.deque()
_PACE_WINDOW_SEC: float = 60.5


def _pace_gemini_api_call() -> None:
    """Sliding-window RPM pacer: 0ms sleep until the 60s window actually nears the RPM budget."""
    if os.environ.get("PYTEST", "").strip() == "1":
        return
    rpm_raw = os.environ.get("SMARTHOME_GEMINI_PACE_RPM", "").strip()
    if not rpm_raw:
        return
    try:
        max_rpm = int(float(rpm_raw))
    except ValueError:
        return
    if max_rpm <= 0:
        return
    while True:
        sleep_s = 0.0
        with _PACE_LOCK:
            now = time.monotonic()
            cutoff = now - _PACE_WINDOW_SEC
            while _GEMINI_CALL_TIMESTAMPS and _GEMINI_CALL_TIMESTAMPS[0] <= cutoff:
                _GEMINI_CALL_TIMESTAMPS.popleft()
            if len(_GEMINI_CALL_TIMESTAMPS) < max_rpm:
                _GEMINI_CALL_TIMESTAMPS.append(now)
                return
            sleep_s = max(0.05, (_GEMINI_CALL_TIMESTAMPS[0] + _PACE_WINDOW_SEC) - now)
        time.sleep(min(sleep_s, 2.0))

_DEFAULT_MODEL_CHAIN: tuple[str, ...] = (
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview",
    "gemini-flash-lite-latest",
    "gemini-3-flash-preview",
    "gemini-3.5-flash-lite",
)
_DEFAULT_PRIMARY_MODEL = _DEFAULT_MODEL_CHAIN[0]
_FALLBACK_MODEL = _DEFAULT_MODEL_CHAIN[-1]

_ALNUM_GARBAGE_RE = re.compile(r"[A-Z0-9]{4,}")
_ALLOWED_ALNUM_CODES: frozenset[str] = frozenset({"KY037", "KY038", "DHT11"})

_DEVICE_CORROBORATION_CUES: dict[str, tuple[str, ...]] = {
    "main_door": ("cua", "chinh", "cong"),
    "living_room_light": ("den", "khach"),
    "bedroom_light": ("den", "ngu", "buong"),
    "garden_pump": ("bom", "tuoi", "cay", "vuon", "nuoc"),
    "alarm_siren": ("coi", "bao", "hu", "trom"),
    "speaker_amp": ("loa", "mach", "pam8403"),
}

_CORROBORATION_STOPWORDS: frozenset[str] = frozenset({
    "khong", "nhung", "trong", "cung", "dung", "luon", "nguon", "chong", "song", "long", "xong", "vong",
})

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
    "Bạn là bộ nhận dạng giọng nói (ASR) tiếng Việt chính xác cao cho nhà thông minh.\n"
    "Hãy lắng nghe kỹ giọng người nói chính (lớn nhất ở tiền cảnh) và chép lại CHÍNH XÁC NGUYÊN VĂN lời họ nói.\n"
    "Từ vựng tham khảo để chép đúng chính tả (CHỈ dùng khi thực sự nghe thấy âm thanh tương ứng, "
    "TUYỆT ĐỐI KHÔNG ép khớp hay thay từ khác sang danh sách này):\n"
    "- 6 thiết bị hỗ trợ: cửa chính (cửa/cổng), đèn phòng khách, đèn phòng ngủ (đèn buồng), tất cả đèn (hết đèn), "
    "máy bơm tưới cây (máy bơm/tưới vườn), còi báo động (còi/còi hú, ví dụ: bật còi, tắt còi), nguồn mạch loa (loa/âm ly).\n"
    "- Tự động hóa & cảm biến: tạo lệnh ... là ..., sửa lệnh ... thành ..., xóa lệnh ..., "
    "đặt lịch <số> giờ sáng/tối hằng ngày ..., sửa lịch ... thành ..., xóa lịch ..., hẹn giờ <số> giây/phút ..., "
    "khi ... thì ..., xóa liên kết ..., reset trạng thái thiết bị, reset liên kết, khôi phục cài đặt gốc, "
    "đất khô, tiếng động lớn, nhiệt độ, độ ẩm đất, cảm biến âm thanh.\n"
    "Quy tắc bắt buộc:\n"
    "- Chỉ xuất ra đúng lời nói nguyên văn, không giải thích, không thêm lời bình.\n"
    "- Chú ý thật kỹ âm đầu & cặp dễ nhầm: phân biệt rõ 'tắt' và 'bật', 'đóng' và 'mở', 'xóa liên kết' và 'tắt hết', "
    "'reset' và 'bật thiết bị'/'vệ sinh'/'save', 'tắt loa' và 'tắt hoa', 'bật hết đèn' và 'bật thiết đèn', "
    "'tưới cây' và 'từ tay', 'đất khô' và 'em cô', 'tiếng động lớn' và 'biến động lớn', 'hủy' và 'quý', 'tạm biệt' và 'tắt đèn'.\n"
    "- TUYỆT ĐỐI KHÔNG bỏ sót động từ đầu câu, giờ/số đếm, hoặc tiền tố tự động hóa ('tạo lệnh ... là ...', "
    "'đặt lịch ...', 'hẹn giờ ...', 'khi ... thì ...'). KHÔNG ĐƯỢC thay tiền tố nghe chưa rõ bằng 'Hãy ...' "
    "hay rút gọn thành lệnh bật/tắt trực tiếp.\n"
    "- CHỐNG BỊA LỆNH (tối quan trọng):\n"
    "  1. Câu thiếu/ngắn (1-2 âm tiết như 'tạm biệt', 'bật còi', 'tắt còi', 'cửa chính'): TUYỆT ĐỐI KHÔNG tự kéo dài "
    "hay bịa thêm thiết bị/động từ không có trong âm thanh. Chỉ nghe 'cửa chính' xuất 'cửa chính'; chỉ nghe 'tất cả đèn' "
    "xuất 'tất cả đèn'; chỉ nghe 'bật lên đi' xuất 'bật lên đi'.\n"
    "  2. Khi có tiếng ồn nền hoặc nhiều giọng nói: tập trung chép lời người nói chính to nhất ở tiền cảnh; "
    "KHÔNG đoán ngược cực bật/tắt hay mở/đóng; chỉ xuất `[NOISE]` khi hoàn toàn không nghe ra từ tiếng Việt rõ ràng nào.\n"
    "  3. Thiết bị ngoài danh sách: nếu nghe 'rèm cửa', 'cửa cuốn', 'quạt trần', 'điều hòa', 'tivi', 'máy giặt', "
    "'bình nóng lạnh' thì PHẢI chép đúng nguyên văn, TUYỆT ĐỐI KHÔNG đổi thành 'cửa chính' hay thiết bị khác.\n"
    "  4. Ngoại ngữ: nếu người nói dùng tiếng Anh, Pháp, Hàn, Tây Ban Nha, Đức... thì chép nguyên văn bằng ngoại ngữ đó, "
    "KHÔNG dịch sang tiếng Việt.\n"
    "  5. Nhiễu/từ đệm: chỉ có từ đệm ('ờ à ừm') thì chép 'ờ à ừm'; chỉ có tiếng ồn trắng, nhiễu tĩnh hoặc tạp âm nền "
    "không rõ lời người nói chính ở tiền cảnh thì chỉ xuất đúng `[NOISE]`."
)

_SHORT_PENDING_CONFIRM_PROMPT = (
    "Bạn là bộ nhận dạng giọng nói (ASR) tiếng Việt chính xác cao.\n"
    "Hệ thống đang chờ người dùng xác nhận. Hãy lắng nghe và chép lại CHÍNH XÁC NGUYÊN VĂN từ/câu ngắn người dùng nói "
    "(có thể chỉ là 1-2 âm tiết như: ok, được, có, ừ, đồng ý, không, thôi, hủy — chú ý phân biệt rõ 'hủy' và 'quý', hoặc một câu ngắn khác).\n"
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
        from google.genai import types

        try:
            client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=10500))
        except Exception:
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
        elif (
            code in (503, 504)
            or "503" in err_low
            or "504" in err_low
            or "unavailable" in err_low
            or "deadline_exceeded" in err_low
            or "timeout" in err_low
            or "timed out" in err_low
        ):
            _MODEL_COOLDOWN_UNTIL[model_name] = now + 25.0
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


def _estimate_active_speech_duration_sec(audio_f32: np.ndarray, sr: int = 16000) -> float:
    """Fast (<1ms) estimate of active foreground speech span (above noise floor + 25% dynamic range)."""
    if audio_f32 is None or audio_f32.size < int(sr * 0.1):
        return 0.0
    frame_len = max(1, int(sr * 0.02))
    n_frames = audio_f32.size // frame_len
    if n_frames < 4:
        return float(audio_f32.size) / float(max(1, sr))
    frames = audio_f32[: n_frames * frame_len].reshape(n_frames, frame_len)
    frame_rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    p15 = float(np.percentile(frame_rms, 15))
    p90 = float(np.percentile(frame_rms, 90))
    thr = p15 + 0.25 * max(0.0, p90 - p15)
    act_idx = np.where(frame_rms > thr)[0]
    if act_idx.size == 0:
        return 0.0
    return float((int(act_idx[-1]) - int(act_idx[0]) + 1) * 0.02)


def _device_group_for(dev_id: str) -> str:
    if dev_id in ("living_room_light", "bedroom_light"):
        return "lights"
    return dev_id


def _local_corroborates_single_device_group(
    local_tokens: list[str],
    local_phons: list[str],
    group_cues: set[str],
    _fuzzy_ratio: Any,
    _vi_phonetic_skeleton: Any,
) -> bool:
    for cue in group_cues:
        if cue in local_tokens:
            return True
        if len(cue) < 3:
            continue
        cue_phon = _vi_phonetic_skeleton(cue)
        if len(cue_phon) < 2:
            continue
        for tok, tok_phon in zip(local_tokens, local_phons):
            # 2-letter tokens match by exact equality only (prevents 'vệ'->'ze' falsely matching 'đèn'->'zen')
            if len(tok) < 3 or tok in _CORROBORATION_STOPWORDS:
                continue
            min_ratio = 80.0 if min(len(tok), len(cue)) <= 4 else 75.0
            if _fuzzy_ratio(tok, cue) >= min_ratio or _fuzzy_ratio(tok_phon, cue_phon) >= min_ratio:
                return True
    return False


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
    local_phons = [_vi_phonetic_skeleton(tok) for tok in local_tokens]

    target_cues: set[str] = set()
    for it in intents:
        dev_id = str(it.get("device_id") or "")
        for cue in _DEVICE_CORROBORATION_CUES.get(dev_id, ()):
            target_cues.add(cue)
    if not target_cues:
        return True

    return _local_corroborates_single_device_group(
        local_tokens, local_phons, target_cues, _fuzzy_ratio, _vi_phonetic_skeleton
    )


def _local_corroborates_all_device_groups(
    local_text: str,
    intents: list[dict[str, str]],
) -> bool:
    """Return True only if EVERY distinct device group in intents has corroboration in local_text."""
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
    local_phons = [_vi_phonetic_skeleton(tok) for tok in local_tokens]

    groups: dict[str, set[str]] = {}
    for it in intents:
        dev_id = str(it.get("device_id") or "")
        grp = _device_group_for(dev_id)
        groups.setdefault(grp, set()).update(_DEVICE_CORROBORATION_CUES.get(dev_id, ()))

    for grp, cues in groups.items():
        if not cues:
            continue
        if not _local_corroborates_single_device_group(
            local_tokens, local_phons, cues, _fuzzy_ratio, _vi_phonetic_skeleton
        ):
            return False
    return True


def _text_has_non_direct_intent_cue(text: str) -> bool:
    """Return True if text carries automation, timer, schedule, custom-command, or reset cues."""
    if not text:
        return False
    try:
        from simulator.automation_nlu import _normalize_vi_spoken_numbers
        from simulator.voice.vietnamese_policy import (
            _CONDITIONAL_THI_GUARD_RE,
            _COUNTDOWN_OR_CLOCK_GUARD_RE,
            _CUSTOM_COMMAND_DIRECT_GUARD_RE,
            _NON_DIRECT_INTENT_CUES,
            strip_vi_accents,
        )
    except Exception:
        return False
    raw_low = text.lower()
    raw_no_air = re.sub(r"\b(?:không\s+khí|khong\s+khi)\b", " khong_khi ", raw_low)
    norm_num = _normalize_vi_spoken_numbers(raw_no_air)
    norm_clean = " ".join(re.sub(r"[^a-z0-9_\s]+", " ", strip_vi_accents(norm_num.lower())).split())
    if not norm_clean:
        return False
    padded = f" {norm_clean} "
    has_contrastive_con_thi = bool(re.search(r"\bcòn\b.+\bthì\b|\bcon\b.+\bthi\b", raw_low))
    norm_for_thi = f" {re.sub(r'^(?:o|a|um|u)\s+thi\b', '', norm_clean).strip()} "
    return bool(
        any(k in padded for k in _NON_DIRECT_INTENT_CUES)
        or _COUNTDOWN_OR_CLOCK_GUARD_RE.search(padded)
        or (not has_contrastive_con_thi and _CONDITIONAL_THI_GUARD_RE.search(norm_for_thi))
        or _CUSTOM_COMMAND_DIRECT_GUARD_RE.search(padded)
    )


def _extract_explicit_polarity(text: str) -> str | None:
    """Return 'on' or 'off' if text contains unambiguous explicit verb polarity, else None."""
    if not text:
        return None
    try:
        from simulator.voice.vietnamese_policy import (
            _EXPLICIT_OFF_VERBS,
            _EXPLICIT_ON_VERBS,
            _strip_non_verb_phrases,
            strip_vi_accents,
        )
    except Exception:
        return None
    clean = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(text.lower())).split())
    if not clean:
        return None
    tokens = set(_strip_non_verb_phrases(clean, raw_clause=text).split())
    has_on = bool(tokens & _EXPLICIT_ON_VERBS)
    has_off = bool(tokens & _EXPLICIT_OFF_VERBS)
    if has_on == has_off:
        return None
    return "off" if has_off else "on"


def _intents_polarity(intents: list[dict[str, str]]) -> str | None:
    pols = {
        ("on" if str(it.get("action") or "") in ("open", "turn_on") else "off")
        for it in intents
        if it.get("action")
    }
    return next(iter(pols)) if len(pols) == 1 else None


def _run_high_noise_hallucination_gate(
    *,
    gemini_text: str,
    pcm16: np.ndarray,
    sr: int,
    duration_sec: float,
    noise_ratio: float,
    used_model: str,
    t0: float,
    muffled_babble: bool = False,
    active_speech_dur: float | None = None,
    offline_hint_text: str = "",
    offline_engine: str = "",
) -> dict[str, Any] | None:
    """Cross-check Gemini direct device commands against local STT & acoustic physics (0 false actions)."""
    if not gemini_text:
        return None
    if noise_ratio < 0.14 and not offline_hint_text:
        return None
    try:
        from simulator.voice.vietnamese_policy import (
            _NEGATED_OR_RHETORICAL_DIRECT_RE,
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

    # Reuse Step-1 cascade offline transcript when available (0ms extra CPU + stronger 70M/ChunkFormer text);
    # otherwise fall back to fast Zipformer-30M when noise is present.
    local_txt = str(offline_hint_text or "").strip()
    local_engine = str(offline_engine or "local")
    if not local_txt and noise_ratio >= 0.14:
        local_res = transcribe_short_zipformer30m_pcm16k(pcm16, sr=sr)
        local_txt = str(local_res.get("text") or "").strip()
        local_engine = str(local_res.get("stt_engine") or "local")

    # 1. Under background noise, if local clearly hears small talk (e.g. 'chào bạn', 'tạm biệt'), override Gemini hallucination.
    # Never override clean high-pitch child escalations (noise_ratio < 0.14) where offline misheard 'bật bơm' as 'bạn ơi'.
    if noise_ratio >= 0.14 and local_txt and classify_small_talk_vi(local_txt) is not None:
        return {
            "ok": True,
            "text": local_txt,
            "confidence": 0.85,
            "is_noise": False,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": f"gemini:{used_model}+noise_gate_smalltalk:{local_engine}",
        }

    # 2. Local clearly hears a negated/rhetorical phrase ('đừng bật đèn', 'không mở cửa') -> never execute
    if local_txt and _NEGATED_OR_RHETORICAL_DIRECT_RE.search(local_txt.lower()) and not parse_direct_device_intents_vi(local_txt):
        return {
            "ok": True,
            "text": local_txt,
            "confidence": 0.85,
            "is_noise": False,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": f"gemini:{used_model}+noise_gate_negated:{local_engine}",
        }

    local_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(local_txt.lower())).split())
    # 3. Local hears an unsupported device (e.g. 'cửa cuốn', 'rèm cửa', 'quạt') -> prevent false action
    if local_norm and _UNSUPPORTED_DEVICE_RE.search(f" {local_norm} "):
        return {
            "ok": True,
            "text": local_txt,
            "confidence": 0.85,
            "is_noise": False,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": f"gemini:{used_model}+noise_gate_unsupported:{local_engine}",
        }

    # R1. Non-Direct Cue Veto: if local heard automation/timer/schedule/custom/reset cues
    # (e.g. 'tạo lệnh đi làm', 'hai giây ...'), never let Gemini downgrade it into an immediate toggle!
    if local_txt and _text_has_non_direct_intent_cue(local_txt):
        return {
            "ok": True,
            "text": local_txt,
            "confidence": 0.84,
            "is_noise": False,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": f"gemini:{used_model}+noise_gate_nondirect:{local_engine}",
        }

    gemini_words = re.sub(r"[?!.,;:]+$", "", gemini_text.strip()).split()
    local_words = local_norm.split()

    # R2. Short-Clip Hallucination Expansion Guard (applies to ALL noise levels including clean & SNR10):
    # A 1-2 syllable clip (e.g. 'tạm biệt' / 'bật còi', active_speech < 0.85s) cannot become a 4-5 syllable
    # command ('tắt đèn phòng khách' / 'bật đèn phòng khách') with zero local device-cue corroboration.
    short_local_expansion = (
        duration_sec < 1.35
        and 1 <= len(local_words) <= 2
        and len(gemini_words) >= len(local_words) + 2
    )
    short_acoustic_expansion = (
        active_speech_dur is not None
        and 0.0 < active_speech_dur < 0.85
        and len(gemini_words) >= 4
    )
    if (short_local_expansion or short_acoustic_expansion) and not _local_corroborates_device_intents(
        local_txt, gemini_intents
    ):
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": True,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": f"gemini:{used_model}+gate_short_expand:{local_engine}",
        }

    # R3. Long Prefix-Drop Guard: local heard >= 6 words (e.g. custom command / schedule / timer)
    # and Gemini dropped >= 3 words into a bare direct command -> abstain instead of immediate execution.
    if len(local_words) >= 6 and (len(local_words) - len(gemini_words)) >= 3:
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": True,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": f"gemini:{used_model}+gate_prefix_drop:{local_engine}",
        }

    # R5. Explicit Polarity Conflict, Room-Qualifier Conflict, Short-Command Corroboration & Acoustic CTC Polarity Veto
    loc_pol = _extract_explicit_polarity(local_txt) if local_txt else None
    gem_pol = _intents_polarity(gemini_intents)
    gem_devs = {str(it.get("device_id") or "") for it in gemini_intents}
    gem_groups = {_device_group_for(d) for d in gem_devs if d}

    # Acoustic CTC 'đen' vs 'đèn' tone check on direct light commands (prevents T158 'tắt đen phòng khách' false actions)
    if re.search(r"\bđèn\b", gemini_text, flags=re.IGNORECASE):
        try:
            from simulator.voice.chunkformer_ctc import verify_light_den_tone_ctc

            audio_tone, _ = _analyze_and_preprocess_audio(pcm16, sr=sr)
            if audio_tone.size > 0:
                checked_txt, was_flipped = verify_light_den_tone_ctc(audio_tone, gemini_text, sr=16000)
                if was_flipped:
                    return {
                        "ok": True,
                        "text": checked_txt,
                        "confidence": 0.90,
                        "is_noise": False,
                        "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                        "stt_engine": f"gemini:{used_model}+gate_ctc_den_tone:{local_engine}",
                    }
        except Exception:
            pass

    # Universal acoustic CTC polarity verification whenever Gemini outputs a direct device command
    # whose polarity was NOT explicitly corroborated by local STT (catches clean/speed/noisy flips like 'tắt bơm'->'bật bơm').
    if gem_pol is not None and loc_pol != gem_pol:
        target_key = (
            "all_lights"
            if gem_devs == {"living_room_light", "bedroom_light"}
            else (next(iter(gem_devs)) if len(gem_devs) == 1 else "")
        )
        if target_key:
            try:
                from simulator.voice.chunkformer_ctc import verify_command_polarity_ctc

                audio_chk, _ = _analyze_and_preprocess_audio(pcm16, sr=sr)
                if audio_chk.size > 0 and not verify_command_polarity_ctc(
                    audio_chk,
                    target_key,
                    gem_pol,
                    sr=16000,
                    min_confirm_margin=(1.0 if noise_ratio >= 0.35 else None),
                ):
                    return {
                        "ok": False,
                        "text": "",
                        "confidence": 0.0,
                        "is_noise": True,
                        "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                        "stt_engine": f"gemini:{used_model}+gate_ctc_polarity_veto:{local_engine}",
                    }
            except Exception:
                pass

    # Universal 2-word direct command corroboration guard (e.g. speed_0.8x 'tạm biệt' -> local 'ờ biệt' vs gem 'tắt đèn').
    # Exempt clean high-pitch child voice (F0 >= 245 Hz, noise_ratio < 0.14) where offline mishears 'bật bơm' as 'bạn ơi'.
    if len(gemini_words) <= 2 and local_txt and not _local_corroborates_all_device_groups(local_txt, gemini_intents):
        allow_clean_child = False
        if noise_ratio < 0.14:
            try:
                from simulator.voice.chunkformer_ctc import estimate_pitch_f0_hz

                audio_f0, _ = _analyze_and_preprocess_audio(pcm16, sr=sr)
                if audio_f0.size > 0 and estimate_pitch_f0_hz(audio_f0, sr=16000) >= 245.0:
                    allow_clean_child = True
            except Exception:
                pass
        if not allow_clean_child:
            return {
                "ok": False,
                "text": "",
                "confidence": 0.0,
                "is_noise": True,
                "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                "stt_engine": f"gemini:{used_model}+gate_short_uncorrob:{local_engine}",
            }

    if noise_ratio >= 0.14 and local_txt:
        if loc_pol is not None and gem_pol is not None and loc_pol != gem_pol:
            return {
                "ok": False,
                "text": "",
                "confidence": 0.0,
                "is_noise": True,
                "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                "stt_engine": f"gemini:{used_model}+gate_polarity_conflict:{local_engine}",
            }
        loc_tok_set = set(local_words)
        has_ngu = bool(loc_tok_set & {"ngu", "buong"})
        has_khach = "khach" in loc_tok_set
        if (gem_devs == {"living_room_light"} and has_ngu and not has_khach) or (
            gem_devs == {"bedroom_light"} and has_khach and not has_ngu
        ):
            return {
                "ok": False,
                "text": "",
                "confidence": 0.0,
                "is_noise": True,
                "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                "stt_engine": f"gemini:{used_model}+gate_room_conflict:{local_engine}",
            }
        # Multi-group command OR SNR <= 10 dB short command expanding a <=2-word local decode must corroborate target device(s)
        if (
            len(gem_groups) >= 2
            or (noise_ratio >= 0.20 and len(gemini_words) <= 3 and len(local_words) <= 2)
        ) and not _local_corroborates_all_device_groups(local_txt, gemini_intents):
            return {
                "ok": False,
                "text": "",
                "confidence": 0.0,
                "is_noise": True,
                "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                "stt_engine": f"gemini:{used_model}+gate_snr10_corrob_reject:{local_engine}",
            }

    # R4. Noise Corroboration Gate (SNR <= 8-10 dB full device-group corroboration & exact bare-phrase checks)
    if noise_ratio >= 0.25:
        local_intents = parse_direct_device_intents_vi(local_txt) if local_txt else []
        if local_intents:
            return None

        if len(gemini_words) <= 5 and local_txt:
            from simulator.voice.vietnamese_stt import _classify_offline_transcript_kind

            loc_kind, _loc_bdev = _classify_offline_transcript_kind(local_txt)
            if loc_kind == "bare_verb":
                return {
                    "ok": True,
                    "text": local_txt,
                    "confidence": 0.82,
                    "is_noise": False,
                    "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                    "stt_engine": f"gemini:{used_model}+noise_gate_bare_verb:{local_engine}",
                }
            if loc_kind == "bare_device" and len(gemini_words) <= 4:
                return {
                    "ok": True,
                    "text": local_txt,
                    "confidence": 0.82,
                    "is_noise": False,
                    "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                    "stt_engine": f"gemini:{used_model}+noise_gate_bare_device:{local_engine}",
                }

        # Require EVERY distinct device group in Gemini's command to be corroborated by local STT at severe noise
        if not _local_corroborates_all_device_groups(local_txt, gemini_intents):
            if local_txt or len(gemini_words) <= 2 or muffled_babble or noise_ratio >= 0.45:
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
    offline_hint_text: str = "",
    offline_engine: str = "",
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
    active_speech_dur = _estimate_active_speech_duration_sec(audio_f32, sr=16000)

    # Send raw preprocessed 16kHz audio to Gemini: its multimodal encoder preserves Vietnamese tones
    # far better on raw SNR 5-10 dB speech than single-channel CPU denoisers (which smear formants).
    enh_tag = ""
    wav_bytes = _float32_to_wav16k_bytes(audio_f32, pad_short=True)

    if has_pending_confirmation and is_short_clip:
        prompt = _SHORT_PENDING_CONFIRM_PROMPT
    elif (
        noise_ratio >= 0.14
        and not is_short_clip
        and not muffled_babble
        and offline_hint_text
        and len(offline_hint_text.split()) >= 4
    ):
        # 2-stage noisy ASR rescoring: pass Step-1 local Zipformer/ChunkFormer draft (real audio output,
        # zero ground-truth hints) on long noisy clips so Gemini preserves automation/schedule/room structure.
        safe_draft = offline_hint_text.replace('"', "'").strip()[:160]
        prompt = (
            f"{_BASE_ASR_PROMPT}\n"
            f"Bản nháp thô từ ASR cục bộ (có thể sai từ do nhiễu, CHỈ dùng để nhận ra cấu trúc câu/tên phòng "
            f"nếu âm thanh thực sự khớp, TUYỆT ĐỐI KHÔNG bịa thêm lệnh): \"{safe_draft}\""
        )
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
            cfg_lite = types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=64,
            )
            try:
                cfg_flash_nothink = types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=64,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                )
            except Exception:
                cfg_flash_nothink = cfg_lite
            audio_part = types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav")

            for model_name in models_to_try:
                try:
                    _pace_gemini_api_call()
                    use_cfg = cfg_flash_nothink if ("lite" not in model_name.lower()) else cfg_lite
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=[prompt, audio_part],
                        config=use_cfg,
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
        if offline_hint_text:
            return {
                "ok": True,
                "text": offline_hint_text,
                "confidence": 0.80,
                "is_noise": False,
                "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                "stt_engine": f"offline_fallback:{offline_engine or 'offline'}",
            }
        fb = transcribe_vietnamese_offline_pcm16k(pcm16, sr=sr)
        fb["stt_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        fb["stt_engine"] = f"offline_fallback:{fb.get('stt_engine', 'offline')}"
        return fb

    # Reject random alphanumeric garbage tokens (e.g. 'FGH9A') and fall back to local offline STT.
    if gemini_text and _is_alnum_garbage(gemini_text):
        if offline_hint_text:
            return {
                "ok": True,
                "text": offline_hint_text,
                "confidence": 0.80,
                "is_noise": False,
                "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                "stt_engine": f"gemini:{used_model}{enh_tag}+offline_garbage_fallback:{offline_engine or 'offline'}",
            }
        fb = transcribe_vietnamese_offline_pcm16k(pcm16, sr=sr)
        fb["stt_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        fb["stt_engine"] = f"gemini:{used_model}{enh_tag}+offline_garbage_fallback:{fb.get('stt_engine', 'offline')}"
        return fb

    # Priority short-clip confirmation rescue (<1.25s with pending confirmation):
    if has_pending_confirmation and is_short_clip and _classify_confirm_safe(gemini_text) is None:
        if offline_hint_text and _classify_confirm_safe(offline_hint_text) is not None:
            return {
                "ok": True,
                "text": offline_hint_text,
                "confidence": 0.90,
                "is_noise": False,
                "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                "stt_engine": f"gemini:{used_model}{enh_tag}+local_confirm_rescue",
            }
        z30 = transcribe_short_zipformer30m_pcm16k(pcm16, sr=sr)
        z30_txt = str(z30.get("text") or "").strip()
        if z30_txt and _classify_confirm_safe(z30_txt) is not None:
            return {
                "ok": True,
                "text": z30_txt,
                "confidence": 0.90,
                "is_noise": False,
                "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                "stt_engine": f"gemini:{used_model}{enh_tag}+zipformer_30m_confirm_rescue",
            }

    # General short-utterance rescue (<1.25s):
    if is_short_clip and not muffled_babble and (not gemini_text or _is_likely_short_gibberish(gemini_text)):
        z30_txt = offline_hint_text
        if not z30_txt:
            z30 = transcribe_short_zipformer30m_pcm16k(pcm16, sr=sr)
            z30_txt = str(z30.get("text") or "").strip()
        if z30_txt:
            # Under high noise (SNR <= 10 dB), never promote an uncorroborated direct device command over Gemini [NOISE]
            from simulator.voice.vietnamese_policy import parse_direct_device_intents_vi

            if noise_ratio >= 0.25 and not gemini_text and parse_direct_device_intents_vi(z30_txt):
                z30_txt = ""
            elif not gemini_text or _is_plausible_short_reply_or_command(z30_txt):
                return {
                    "ok": True,
                    "text": z30_txt,
                    "confidence": 0.86,
                    "is_noise": False,
                    "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                    "stt_engine": f"gemini:{used_model}{enh_tag}+zipformer_30m_short_rescue",
                }
        elif not gemini_text and not offline_hint_text:
            fb = transcribe_vietnamese_offline_pcm16k(pcm16, sr=sr)
            fb_txt = str(fb.get("text") or "").strip()
            from simulator.voice.vietnamese_policy import parse_direct_device_intents_vi

            if fb.get("ok") and fb_txt and not (noise_ratio >= 0.25 and parse_direct_device_intents_vi(fb_txt)):
                fb["stt_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
                fb["stt_engine"] = f"gemini:{used_model}{enh_tag}+offline_short_rescue:{fb.get('stt_engine', 'offline')}"
                return fb

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    if not gemini_text:
        # Reuse Step-1 offline_hint_text when available (zero redundant compute!);
        # under high noise (noise_ratio >= 0.25), NEVER promote an uncorroborated direct device command over Gemini [NOISE].
        if not muffled_babble and not is_short_clip:
            from simulator.voice.vietnamese_policy import parse_direct_device_intents_vi

            if offline_hint_text:
                fb_txt = offline_hint_text
                fb_eng = offline_engine or "offline"
                fb_conf = 0.80
                fb_ok = True
            else:
                fb = transcribe_vietnamese_offline_pcm16k(pcm16, sr=sr)
                fb_txt = str(fb.get("text") or "").strip()
                fb_eng = str(fb.get("stt_engine") or "offline")
                fb_conf = float(fb.get("confidence") or 0.80)
                fb_ok = bool(fb.get("ok"))
            if fb_ok and fb_txt and not (noise_ratio >= 0.25 and parse_direct_device_intents_vi(fb_txt)) and (
                _is_plausible_short_reply_or_command(fb_txt) or len(fb_txt.split()) >= 2
            ):
                return {
                    "ok": True,
                    "text": fb_txt,
                    "confidence": fb_conf,
                    "is_noise": False,
                    "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                    "stt_engine": f"gemini:{used_model}{enh_tag}+offline_noise_rescue:{fb_eng}",
                }
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": True,
            "stt_ms": elapsed_ms,
            "stt_engine": f"gemini:{used_model}{enh_tag}",
        }

    # Protect against muffled babble-only audio returning random 1-2 nonsense words
    if muffled_babble and len(gemini_text.split()) <= 3 and not _is_plausible_short_reply_or_command(gemini_text):
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": True,
            "stt_ms": elapsed_ms,
            "stt_engine": f"gemini:{used_model}{enh_tag}:babble_guard",
        }

    # Cross-Engine & Acoustic-Length Hallucination Gate (0 false actions across clean, SNR10, and SNR5)
    gated = _run_high_noise_hallucination_gate(
        gemini_text=gemini_text,
        pcm16=pcm16,
        sr=sr,
        duration_sec=duration_sec,
        noise_ratio=noise_ratio,
        used_model=f"{used_model}{enh_tag}",
        t0=t0,
        muffled_babble=muffled_babble,
        active_speech_dur=active_speech_dur,
        offline_hint_text=offline_hint_text,
        offline_engine=offline_engine,
    )
    if gated is not None:
        return gated

    return {
        "ok": True,
        "text": gemini_text,
        "confidence": 0.94,
        "is_noise": False,
        "stt_ms": elapsed_ms,
        "stt_engine": f"gemini:{used_model}{enh_tag}",
    }


def _should_escalate_offline_to_gemini(
    off_res: dict[str, Any],
    audio_f32: np.ndarray,
    sr: int,
    *,
    has_pending_confirmation: bool,
) -> tuple[bool, str]:
    """Decide whether an offline STT result needs Gemini escalation in the quota-aware cascade."""
    from simulator.voice.vietnamese_policy import classify_small_talk_vi, parse_direct_device_intents_vi
    from simulator.voice.vietnamese_stt import _classify_offline_transcript_kind

    eng = str(off_res.get("stt_engine") or "")
    txt = str(off_res.get("text") or "").strip()
    noise_ratio = _compute_noise_ratio(audio_f32, sr=sr)

    # Pure silence / pure white noise already blocked at acoustic gate -> never spend Gemini quota
    if eng == "acoustic_gate":
        return False, "acoustic_gate"

    # Acoustic ChunkFormer-CTC already verified 'đen' (wrong diacritic) vs 'đèn' -> keep locally so Gemini LM cannot override it
    if "+ctc_den_tone" in eng:
        return False, "local_confident:ctc_den_tone"

    # Pure muffled babble without foreground speech (noise_ratio >= 0.30) -> keep safely rejected locally (0 false actions)
    if ":babble_guard" in eng or eng == "babble_guard":
        if _is_muffled_babble_only(audio_f32, sr=sr) and noise_ratio >= 0.30:
            return False, "pure_babble_local_reject"
        return True, "babble_guard"
    if not off_res.get("ok") or not txt:
        return True, "offline_empty"
    if "_fallback" in eng or eng in ("unavailable", "disabled", "whisper_error"):
        return True, "offline_fallback"

    kind, _bare_dev = _classify_offline_transcript_kind(txt)
    if kind == "unrecognized":
        return True, "unrecognized"
    if kind == "nonsense":
        return False, "local_confident:nonsense"

    # Under severe noise (SNR <= 5 dB, noise_ratio >= 0.31), never execute a local-only direct device toggle
    # without Gemini cross-verification (prevents noisy babble/small-talk false positives).
    if noise_ratio >= 0.31 and kind == "recognized" and parse_direct_device_intents_vi(txt):
        return True, "severe_noise_verify_direct"

    # Pending confirmation: if offline did not hear a confirmation/cancel word or direct command, escalate
    if has_pending_confirmation and _classify_confirm_safe(txt) is None and kind != "recognized":
        return True, "pending_confirm_uncertain"

    # Short high-pitch speaker (e.g. child F0 >= 245 Hz, dur <= 1.30s) decoded as 2-word small talk ('bạn ơi' for 'bật bơm')
    dur_s = float(audio_f32.size) / float(max(1, sr))
    if dur_s <= 1.30 and len(txt.split()) <= 2 and classify_small_talk_vi(txt) is not None:
        try:
            from simulator.voice.chunkformer_ctc import estimate_pitch_f0_hz

            if estimate_pitch_f0_hz(audio_f32, sr=sr) >= 245.0:
                return True, "high_pitch_short_smalltalk"
        except Exception:
            pass

    # High-confidence local match (recognized, bare_verified, bare_verb, unsupported, foreign) -> keep locally!
    return False, f"local_confident:{kind}"


def transcribe_vietnamese_cascade_pcm16k(
    pcm16: np.ndarray,
    sr: int = 16000,
    *,
    has_pending_confirmation: bool = False,
) -> dict[str, Any]:
    """Quota-aware production cascade: run fast local STT first, escalate to Gemini ONLY when confidence/grammar is low."""
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

    # Step 1: Fast local Zipformer + ChunkFormer-CTC offline pass
    off_res = transcribe_vietnamese_offline_pcm16k(pcm16, sr=sr)
    need_gemini, reason = _should_escalate_offline_to_gemini(
        off_res,
        audio_f32,
        sr=16000,
        has_pending_confirmation=has_pending_confirmation,
    )
    if not need_gemini:
        out = dict(off_res)
        orig_eng = str(out.get("stt_engine") or "offline")
        if orig_eng != "acoustic_gate":
            out["stt_engine"] = f"cascade_local:{orig_eng}"
        out["stt_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        return out

    # Step 2: Escalate only uncertain / noisy / unrecognized clips to Gemini STT (passing Step-1 offline transcript)
    api_key = (load_key() or os.environ.get("GEMINI_API_KEY", "")).strip()
    models_to_try = _get_candidate_models() if api_key else []
    if not api_key or not models_to_try:
        out = dict(off_res)
        orig_eng = str(out.get("stt_engine") or "offline")
        prefix = "offline_no_key" if not api_key else "offline_fallback"
        out["stt_engine"] = f"{prefix}:{orig_eng}"
        out["stt_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        return out

    gem_res = transcribe_vietnamese_gemini_pcm16k(
        pcm16,
        sr=sr,
        has_pending_confirmation=has_pending_confirmation,
        offline_hint_text=str(off_res.get("text") or "").strip(),
        offline_engine=str(off_res.get("stt_engine") or "offline"),
    )
    gem_res["stt_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    LOG.debug(
        "Cascade escalated (%s) -> engine=%s ms=%.1f",
        reason,
        gem_res.get("stt_engine"),
        gem_res["stt_ms"],
    )
    return gem_res
