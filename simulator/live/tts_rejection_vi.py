"""Module Tổng Hợp Âm Thanh Từ Chối Tiếng Việt 24kHz Từ Server (Server-Side VI Rejection TTS).

Chức năng:
1. `synthesize_vi_rejection_audio_24k(reason_code: str) -> bytes`:
   Tạo mảng byte âm thanh 24kHz Mono 16-bit PCM tiếng Việt thực tế (edge-tts vi-VN-HoaiMyNeural).
2. Bộ nhớ đệm (Pre-cache) toàn bộ câu từ chối và phản hồi chuẩn khi nạp module -> Đáp ứng độ trễ < 5ms,
   có fallback an toàn để cold-start không bao giờ treo khi mất mạng.
"""

from __future__ import annotations

import asyncio
import base64
import io
import pathlib
import re
import threading
from typing import Any

import numpy as np

SAMPLE_RATE = 24000  # 24kHz chuẩn của Gemini Live và Web Audio API
DEFAULT_EDGE_VOICE = "vi-VN-HoaiMyNeural"
_PRECACHE_NPZ_PATH = pathlib.Path(__file__).resolve().parent / "tts_rejection_precache_24k.npz"

REJECTION_SCRIPTS: dict[str, str] = {
    "STRANGER_BLOCKED": "Tôi không được phép nhận lệnh từ người lạ.",
    "STRANGER_BLOCKED_2": "Tôi sẽ không trả lời bạn lần nữa.",
    "DUPLICATE_VOICE": "Trùng giọng người đã có trong nhà - Từ chối lưu.",
    "VOICE_EXPIRED": "Quyền truy cập của bạn đã hết hạn.",
    "RATE_LIMITED": "Thao tác quá nhanh, vui lòng thử lại sau.",
    "TIER3_PERMISSION_DENIED": "Khách chỉ được điều khiển đèn và quạt.",
    "TIER2_PERMISSION_DENIED": "Chỉ chủ nhà mới có quyền mở cửa chính và còi báo động.",
    "VAD_BLOCKED": "Hệ thống chỉ tiếp nhận khẩu lệnh tiếng Việt.",
}

EXTENDED_TTS_SCRIPTS: dict[str, str] = {
    **REJECTION_SCRIPTS,
    "REST_STRANGER_BLOCKED": "Từ chối: Giọng nói người lạ không có quyền điều khiển ngôi nhà.",
    "VAD_NOISE_BLOCKED": "Phát hiện tiếng ồn hoặc âm thanh không hợp lệ, vui lòng nói lại bằng tiếng Việt.",
    "OPEN_MAIN_DOOR": "Cửa chính đã mở.",
    "CLOSE_MAIN_DOOR": "Cửa chính đã đóng.",
    "TURN_ON_LIVING_ROOM_LIGHT": "Đèn phòng khách đã bật.",
    "TURN_OFF_LIVING_ROOM_LIGHT": "Đèn phòng khách đã tắt.",
    "TURN_ON_BEDROOM_LIGHT": "Đèn phòng ngủ đã bật.",
    "TURN_OFF_BEDROOM_LIGHT": "Đèn phòng ngủ đã tắt.",
    "TURN_ON_FAN": "Quạt trần đã bật.",
    "TURN_OFF_FAN": "Quạt trần đã tắt.",
    "TURN_ON_AC": "Điều hòa đã bật.",
    "TURN_OFF_AC": "Điều hòa đã tắt.",
}

# Bộ đệm âm thanh 24kHz PCM được render sẵn
_PRECACHED_AUDIO_PCM: dict[str, bytes] = {}
_PRECACHED_AUDIO_B64: dict[str, str] = {}
_TEXT_TO_KEY_MAP: dict[str, str] = {}


def _normalize_script_text(text: str) -> str:
    cleaned = re.sub(r"[^\w\sàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _decode_mp3_to_pcm24k_bytes(mp3_bytes: bytes, sr: int = SAMPLE_RATE) -> bytes:
    import av  # PyAV

    container = av.open(io.BytesIO(mp3_bytes), format="mp3")
    resampler = av.AudioResampler(format="s16", layout="mono", rate=sr)
    chunks: list[bytes] = []
    for frame in container.decode(audio=0):
        for rframe in resampler.resample(frame):
            chunks.append(bytes(rframe.planes[0]))
    for rframe in resampler.resample(None):
        chunks.append(bytes(rframe.planes[0]))
    raw = b"".join(chunks)
    arr = np.frombuffer(raw, dtype=np.int16)
    nz = np.where(np.abs(arr) > 150)[0]
    if nz.size > 0:
        pad = int(sr * 0.04)
        arr = arr[max(0, int(nz[0]) - pad) : min(arr.size, int(nz[-1]) + pad)]
    return arr.astype(np.int16).tobytes()


def _synthesize_edge_tts_live_pcm24k(text: str, sr: int = SAMPLE_RATE, timeout_sec: float = 3.2) -> bytes:
    """Tổng hợp giọng đọc tiếng Việt thực tế qua edge-tts (vi-VN-HoaiMyNeural) với giới hạn thời gian ngắn."""
    import edge_tts

    clean_txt = re.sub(r"[.!?;:]+$", "", text.strip()).replace(" - ", ", ").replace(":", ",")
    if not clean_txt:
        return b""

    result_holder: list[bytes] = []

    def _worker() -> None:
        async def _run() -> bytes:
            comm = edge_tts.Communicate(clean_txt, voice=DEFAULT_EDGE_VOICE)
            buf = io.BytesIO()
            async for chunk in comm.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    buf.write(chunk["data"])
            if buf.tell() > 400:
                return _decode_mp3_to_pcm24k_bytes(buf.getvalue(), sr=sr)
            return b""

        try:
            pcm = asyncio.run(_run())
            if pcm:
                result_holder.append(pcm)
        except Exception:
            pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)
    return result_holder[0] if result_holder else b""


def _fallback_syllabic_speech_pcm24k(text: str, sr: int = SAMPLE_RATE) -> bytes:
    """Fallback khẩn cấp chỉ khi cả file precache NPZ lẫn edge-tts đều không khả dụng."""
    if "STRANGER_BLOCKED" in _PRECACHED_AUDIO_PCM:
        return _PRECACHED_AUDIO_PCM["STRANGER_BLOCKED"]
    rng = np.random.default_rng(abs(hash(text)) % (2**32))
    words = [w for w in text.split() if w.strip()] or ["tu", "choi"]
    segments: list[np.ndarray] = []
    for idx, w in enumerate(words):
        # Phụ âm đầu vô thanh (unvoiced consonant burst 35ms)
        n_uv = int(sr * 0.035)
        uv = rng.normal(0.0, 0.22, size=n_uv).astype(np.float32)
        uv *= np.hanning(n_uv).astype(np.float32)
        # Nguyên âm hữu thanh biến thiên F0 & formant theo từng từ
        dur_v = 0.14 + 0.02 * (len(w) % 4)
        n_v = int(sr * dur_v)
        t = np.arange(n_v, dtype=np.float32) / sr
        f0 = 195.0 + 28.0 * ((idx * 37 + len(w) * 13) % 5 - 2)
        f0_contour = f0 + 18.0 * np.sin(2.0 * np.pi * 3.0 * t)
        phase = 2.0 * np.pi * np.cumsum(f0_contour) / sr
        f1 = 500.0 + 140.0 * (idx % 4)
        f2 = 1400.0 + 320.0 * ((idx + 1) % 4)
        voiced = (
            0.50 * np.sin(phase)
            + 0.30 * np.sin(2.0 * np.pi * f1 * t)
            + 0.20 * np.sin(2.0 * np.pi * f2 * t)
        ).astype(np.float32)
        voiced *= np.hanning(n_v).astype(np.float32)
        # Khoảng nghỉ ngắn giữa các từ (45ms)
        pause = np.zeros(int(sr * 0.045), dtype=np.float32)
        segments.extend([uv, voiced, pause])
    sig = np.concatenate(segments) if segments else np.zeros(sr, dtype=np.float32)
    peak = float(np.max(np.abs(sig))) + 1e-9
    sig = sig * (0.85 / peak)
    return (sig * 32767.0).astype(np.int16).tobytes()


def _generate_vietnamese_speech_pcm24k(text: str, sr: int = SAMPLE_RATE) -> bytes:
    """Trả về âm thanh giọng nói tiếng Việt 24kHz 16-bit Mono PCM thực tế (edge-tts vi-VN precached + fallback)."""
    raw_txt = (text or "").strip()
    if raw_txt in _PRECACHED_AUDIO_PCM:
        return _PRECACHED_AUDIO_PCM[raw_txt]
    norm_txt = _normalize_script_text(raw_txt)
    if norm_txt in _TEXT_TO_KEY_MAP:
        mapped_key = _TEXT_TO_KEY_MAP[norm_txt]
        if mapped_key in _PRECACHED_AUDIO_PCM:
            return _PRECACHED_AUDIO_PCM[mapped_key]

    live_pcm = _synthesize_edge_tts_live_pcm24k(raw_txt, sr=sr)
    if live_pcm:
        return live_pcm

    return _fallback_syllabic_speech_pcm24k(raw_txt, sr=sr)


def _register_precache_entry(key: str, text: str, pcm_bytes: bytes) -> None:
    _PRECACHED_AUDIO_PCM[key] = pcm_bytes
    _PRECACHED_AUDIO_B64[key] = base64.b64encode(pcm_bytes).decode("ascii")
    if text:
        _TEXT_TO_KEY_MAP[text.strip()] = key
        _TEXT_TO_KEY_MAP[text.strip().lower()] = key
        _TEXT_TO_KEY_MAP[_normalize_script_text(text)] = key


def _init_precache() -> None:
    """Khởi tạo toàn bộ các câu từ chối và phản hồi chuẩn từ file pre-baked edge-tts NPZ vào RAM (< 5ms)."""
    loaded_from_npz: set[str] = set()
    if _PRECACHE_NPZ_PATH.exists():
        try:
            with np.load(_PRECACHE_NPZ_PATH, allow_pickle=False) as npz_data:
                for key in npz_data.files:
                    arr = np.asarray(npz_data[key], dtype=np.int16)
                    pcm = arr.tobytes()
                    if pcm:
                        script_txt = EXTENDED_TTS_SCRIPTS.get(key, "")
                        _register_precache_entry(key, script_txt, pcm)
                        loaded_from_npz.add(key)
        except Exception:
            pass

    for key, text in EXTENDED_TTS_SCRIPTS.items():
        if key not in loaded_from_npz or key not in _PRECACHED_AUDIO_PCM:
            pcm = _generate_vietnamese_speech_pcm24k(text)
            _register_precache_entry(key, text, pcm)


# Nạp sẵn bộ đệm ngay khi import
_init_precache()


def _resolve_rejection_key(reason_code_or_text: str) -> str:
    raw = (reason_code_or_text or "").strip()
    if not raw:
        return "STRANGER_BLOCKED"
    if raw in _PRECACHED_AUDIO_PCM:
        return raw
    norm = _normalize_script_text(raw)
    if norm in _TEXT_TO_KEY_MAP:
        return _TEXT_TO_KEY_MAP[norm]

    low = raw.lower()
    if "lần nữa" in low or "stranger_blocked_2" in low:
        return "STRANGER_BLOCKED_2"
    if "không có quyền điều khiển ngôi nhà" in low or "rest_stranger_blocked" in low:
        return "REST_STRANGER_BLOCKED" if "REST_STRANGER_BLOCKED" in _PRECACHED_AUDIO_PCM else "STRANGER_BLOCKED"
    if "tiếng ồn" in low or "âm thanh không hợp lệ" in low or "vad_noise_blocked" in low:
        return "VAD_NOISE_BLOCKED" if "VAD_NOISE_BLOCKED" in _PRECACHED_AUDIO_PCM else "VAD_BLOCKED"
    if "khách chỉ được" in low or "tier3" in low:
        return "TIER3_PERMISSION_DENIED"
    if "chỉ chủ nhà" in low or "cửa chính và còi" in low or "tier2" in low:
        return "TIER2_PERMISSION_DENIED"
    if "trùng giọng" in low or "duplicate" in low:
        return "DUPLICATE_VOICE"
    if "hết hạn" in low or "expired" in low or "xóa cấp quyền" in low:
        return "VOICE_EXPIRED"
    if "quá nhanh" in low or "rate_limited" in low:
        return "RATE_LIMITED"
    if "tiếng việt" in low or "vad_blocked" in low:
        return "VAD_BLOCKED"

    for k in REJECTION_SCRIPTS:
        if k in raw or raw in k:
            return k

    return "STRANGER_BLOCKED"


def synthesize_vi_rejection_audio_24k(reason_code: str) -> bytes:
    """Trả về dữ liệu âm thanh 24kHz Mono 16-bit PCM cho mã lý do từ chối.

    Hợp đồng giao diện theo PROJECT.md:
    Output: bytes (24kHz Mono 16-bit PCM).
    Độ trễ phản hồi: < 5ms (sử dụng pre-cached buffer).
    """
    resolved = _resolve_rejection_key(reason_code)
    return _PRECACHED_AUDIO_PCM.get(resolved) or _PRECACHED_AUDIO_PCM.get("STRANGER_BLOCKED", b"")


def get_rejection_audio_b64(reason_code: str) -> str:
    """Trả về chuỗi base64 của âm thanh từ chối 24kHz PCM để gửi qua WebSocket hoặc REST API."""
    resolved = _resolve_rejection_key(reason_code)
    return _PRECACHED_AUDIO_B64.get(resolved) or _PRECACHED_AUDIO_B64.get("STRANGER_BLOCKED", "")


def get_cached_speech_audio_b64(text: str, fallback_reason_code: str = "") -> str:
    """Trả về chuỗi base64 24kHz PCM nếu câu trả lời khớp với kho âm thanh đã được cache sẵn (dùng cho lệnh hợp lệ hoặc fallback từ chối)."""
    raw = (text or "").strip()
    if raw:
        if raw in _PRECACHED_AUDIO_B64:
            return _PRECACHED_AUDIO_B64[raw]
        norm = _normalize_script_text(raw)
        if norm in _TEXT_TO_KEY_MAP:
            return _PRECACHED_AUDIO_B64.get(_TEXT_TO_KEY_MAP[norm], "")
    if fallback_reason_code:
        return get_rejection_audio_b64(fallback_reason_code)
    return ""


def get_rejection_speech_text(reason_code: str) -> str:
    """Trả về nội dung văn bản tiếng Việt của câu từ chối."""
    return EXTENDED_TTS_SCRIPTS.get(
        reason_code,
        REJECTION_SCRIPTS.get(reason_code, "Tôi không được phép nhận lệnh từ người lạ."),
    )
