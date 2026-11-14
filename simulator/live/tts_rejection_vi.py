"""Module Hằng Số Câu Thoại Từ Chối Tiếng Việt Chuẩn Cho Giọng Aoede (Gemini Live).

Mọi câu từ chối (Người lạ & Vượt quyền) và yêu cầu nói lại (Safe-Deny) chỉ được phát
thông qua duy nhất giọng đọc tích hợp `Aoede` của Gemini Live (tuyệt đối không dùng
TTS riêng bên ngoài hay Web Speech API).
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import pathlib
import wave
from typing import Any

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)

SAMPLE_RATE = 24000
AOEDE_VOICE_NAME = "Aoede"
AOEDE_LIVE_MODEL = "gemini-3.8-live"
_AOEDE_FALLBACK_LIVE_MODELS: tuple[str, ...] = (
    "gemini-3.1-flash-live-preview",
    "gemini-2.5-flash-native-audio-preview-12-2025",
    "gemini-2.0-flash-live-001",
)
_WORKING_AOEDE_LIVE_MODEL: str = ""
_WORKING_AOEDE_USE_CLIENT_CONTENT: bool = False

FIXED_REJECTION_PHRASE_VI = "Xin lỗi, bạn không có quyền thực hiện lệnh này."
FIXED_SAFE_DENY_REPEAT_PHRASE_VI = "Âm thanh chưa rõ, vui lòng nói lại."
UNIFIED_REJECTION_PHRASE_VI = FIXED_REJECTION_PHRASE_VI
SAFE_DENY_REPEAT_PHRASE_VI = FIXED_SAFE_DENY_REPEAT_PHRASE_VI

_DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
_AOEDE_REJECTION_WAV_FILE = _DATA_DIR / "aoede_rejection_24k.wav"
_AOEDE_REPEAT_WAV_FILE = _DATA_DIR / "aoede_repeat_24k.wav"
_LIVE_AOEDE_SESSION_CACHE: dict[str, bytes] = {}
_LIVE_AOEDE_SOURCE_CACHE: dict[str, str] = {}

REJECTION_SCRIPTS: dict[str, str] = {
    "STRANGER_BLOCKED": FIXED_REJECTION_PHRASE_VI,
    "STRANGER_BLOCKED_2": FIXED_REJECTION_PHRASE_VI,
    "DUPLICATE_VOICE": "Trùng giọng người đã có trong nhà - Từ chối lưu.",
    "VOICE_EXPIRED": FIXED_REJECTION_PHRASE_VI,
    "RATE_LIMITED": "Thao tác quá nhanh, vui lòng thử lại sau.",
    "TIER3_PERMISSION_DENIED": FIXED_REJECTION_PHRASE_VI,
    "TIER2_PERMISSION_DENIED": FIXED_REJECTION_PHRASE_VI,
    "OVER_PERMISSION_DENIED": FIXED_REJECTION_PHRASE_VI,
    "SAFE_DENY_REPEAT": FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
    "VAD_BLOCKED": FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
}

EXTENDED_TTS_SCRIPTS: dict[str, str] = {
    **REJECTION_SCRIPTS,
    "REST_STRANGER_BLOCKED": FIXED_REJECTION_PHRASE_VI,
    "VAD_NOISE_BLOCKED": FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
    "ASK_REPEAT_AUDIO_QUALITY": FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
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


def get_rejection_speech_text(reason_code: str) -> str:
    """Trả về nội dung văn bản tiếng Việt của câu từ chối cố định dành cho giọng Aoede."""
    code = (reason_code or "").strip()
    if code in EXTENDED_TTS_SCRIPTS:
        return EXTENDED_TTS_SCRIPTS[code]
    if code in REJECTION_SCRIPTS:
        return REJECTION_SCRIPTS[code]
    low = code.lower()
    if any(
        k in low
        for k in (
            "safe_deny",
            "ask_repeat",
            "vad",
            "noise",
            "chưa rõ",
            "nói lại",
            "quá ngắn",
            "nói đè",
        )
    ):
        return FIXED_SAFE_DENY_REPEAT_PHRASE_VI
    return FIXED_REJECTION_PHRASE_VI


def _wrap_pcm24k_to_wav(pcm24k: bytes) -> bytes:
    """Đóng gói luồng PCM 24kHz 16-bit mono thành định dạng RIFF WAVE chuẩn."""
    aligned = pcm24k if len(pcm24k) % 2 == 0 else pcm24k[:-1]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(aligned)
    return buf.getvalue()


def _load_bundled_aoede_pcm24k(phrase: str) -> bytes:
    """Đọc bản thu âm chuẩn 24kHz của giọng Aoede (gemini-3.8-live) lưu trong simulator/data/."""
    if phrase == FIXED_SAFE_DENY_REPEAT_PHRASE_VI:
        wav_file = _AOEDE_REPEAT_WAV_FILE
    elif phrase == FIXED_REJECTION_PHRASE_VI:
        wav_file = _AOEDE_REJECTION_WAV_FILE
    else:
        return b""
    if wav_file.exists():
        raw = wav_file.read_bytes()
        with wave.open(io.BytesIO(raw), "rb") as wf:
            return wf.readframes(wf.getnframes())
    return b""


async def _fetch_live_aoede_pcm24k(phrase: str, api_key: str) -> bytes:
    """Gọi trực tiếp Gemini Live (gemini-3.8-live / fallback Live cùng giọng 'Aoede') tạo PCM 24kHz."""
    global _WORKING_AOEDE_LIVE_MODEL, _WORKING_AOEDE_USE_CLIENT_CONTENT
    if genai is None or types is None:
        raise RuntimeError("google-genai SDK is not installed")

    clean_key = (api_key or "").strip().strip('"').strip("'").strip()
    if not clean_key:
        raise RuntimeError("GEMINI_API_KEY is empty")

    client = genai.Client(api_key=clean_key)
    cfg_kwargs: dict[str, Any] = {
        "response_modalities": [types.Modality.AUDIO],
        "speech_config": types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=AOEDE_VOICE_NAME)
            ),
        ),
        "system_instruction": types.Content(
            parts=[
                types.Part(
                    text=(
                        "Bạn là giọng đọc Aoede của hệ thống Nhà thông minh. "
                        "Chỉ đọc to, rõ ràng, tự nhiên ĐÚNG NGUYÊN VĂN câu tiếng Việt được yêu cầu, "
                        "không thêm bất kỳ từ nào trước hoặc sau."
                    )
                )
            ]
        ),
    }
    cfg = types.LiveConnectConfig(**cfg_kwargs)
    prompt_text = f'Hãy đọc đúng nguyên văn câu này: "{phrase}"'

    async def _attempt_one_model(cand_model: str, *, use_client_content: bool = False) -> bytes:
        chunks: list[bytes] = []
        async with client.aio.live.connect(model=cand_model, config=cfg) as session:
            if use_client_content:
                try:
                    await session.send_client_content(
                        turns=[
                            types.Content(
                                role="user",
                                parts=[types.Part(text=prompt_text)],
                            )
                        ],
                        turn_complete=True,
                    )
                except (TypeError, AttributeError):
                    await session.send_realtime_input(text=prompt_text)
            else:
                try:
                    await session.send_realtime_input(text=prompt_text)
                except (TypeError, AttributeError):
                    await session.send_client_content(
                        turns=[
                            types.Content(
                                role="user",
                                parts=[types.Part(text=prompt_text)],
                            )
                        ],
                        turn_complete=True,
                    )
            while True:
                saw_msg = False
                turn_done = False
                turn = session.receive()
                async for msg in turn:
                    saw_msg = True
                    got_inline_audio = False
                    sc = getattr(msg, "server_content", None)
                    if sc is not None:
                        mt = getattr(sc, "model_turn", None)
                        if mt and getattr(mt, "parts", None):
                            for part in mt.parts:
                                inl = getattr(part, "inline_data", None)
                                if inl and getattr(inl, "data", None):
                                    chunks.append(bytes(inl.data))
                                    got_inline_audio = True
                        if getattr(sc, "turn_complete", False):
                            turn_done = True
                            break
                    msg_data = getattr(msg, "data", None)
                    if msg_data and not got_inline_audio:
                        chunks.append(bytes(msg_data))
                if turn_done or not saw_msg or chunks:
                    break
        pcm = b"".join(chunks)
        if len(pcm) % 2 != 0:
            pcm = pcm[:-1]
        if len(pcm) < 2400:
            raise RuntimeError(f"Live model {cand_model} returned insufficient audio ({len(pcm)} bytes)")
        return pcm

    attempts: list[tuple[str, bool]] = []
    if _WORKING_AOEDE_LIVE_MODEL:
        attempts.append((_WORKING_AOEDE_LIVE_MODEL, _WORKING_AOEDE_USE_CLIENT_CONTENT))
    if (AOEDE_LIVE_MODEL, False) not in attempts:
        attempts.append((AOEDE_LIVE_MODEL, False))
    for fb_model in _AOEDE_FALLBACK_LIVE_MODELS:
        pair = (fb_model, True)
        if pair not in attempts:
            attempts.append(pair)

    tried: set[tuple[str, bool]] = set()
    last_exc: Exception | None = None
    idx = 0
    while idx < len(attempts):
        cand_model, use_cc = attempts[idx]
        idx += 1
        if (cand_model, use_cc) in tried:
            continue
        tried.add((cand_model, use_cc))
        try:
            pcm = await asyncio.wait_for(
                _attempt_one_model(cand_model, use_client_content=use_cc),
                timeout=6.0,
            )
            _WORKING_AOEDE_LIVE_MODEL = cand_model
            _WORKING_AOEDE_USE_CLIENT_CONTENT = use_cc
            return pcm
        except Exception as exc:
            last_exc = exc
            err_msg = str(exc).replace(clean_key, "***")
            _LOGGER.warning(
                "Aoede live attempt failed on %s (cc=%s, %s): %s",
                cand_model,
                use_cc,
                type(exc).__name__,
                err_msg[:180],
            )
            is_model_rejected = any(
                tok in err_msg.lower()
                for tok in ("404", "1007", "1008", "not found", "not_found", "unsupported", "invalid argument")
            )
            is_timeout_or_short = (
                isinstance(exc, (TimeoutError, asyncio.TimeoutError))
                or "insufficient audio" in err_msg.lower()
            )
            if (
                cand_model == AOEDE_LIVE_MODEL
                and not use_cc
                and is_timeout_or_short
                and not is_model_rejected
                and (AOEDE_LIVE_MODEL, True) not in tried
            ):
                attempts.insert(idx, (AOEDE_LIVE_MODEL, True))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("No Aoede live model candidates configured")


async def synthesize_aoede_phrase_audio(
    phrase: str, *, allow_live_refresh: bool = True
) -> dict[str, Any]:
    """Trả về gói âm thanh PCM16 24kHz & WAV chuẩn của duy nhất giọng Aoede (Gemini Live)."""
    clean_phrase = (phrase or "").strip()
    target_phrase = clean_phrase or FIXED_REJECTION_PHRASE_VI
    pcm24k = _LIVE_AOEDE_SESSION_CACHE.get(target_phrase, b"")
    audio_source = _LIVE_AOEDE_SOURCE_CACHE.get(target_phrase, "") if pcm24k else ""

    is_offline = (
        os.environ.get("SIMULATOR_OFFLINE_SANDBOX", "").strip() == "1"
        or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    )
    raw_api_key = (
        os.environ.get("GEMINI_API_KEY", "")
        or os.environ.get("GOOGLE_API_KEY", "")
    )
    api_key = raw_api_key.strip().strip('"').strip("'").strip()
    if not pcm24k and allow_live_refresh and api_key and not is_offline:
        try:
            live_pcm = await asyncio.wait_for(
                _fetch_live_aoede_pcm24k(target_phrase, api_key), timeout=20.0
            )
            if len(live_pcm) >= 2400:
                pcm24k = live_pcm
                audio_source = "gemini_live_aoede"
                _LIVE_AOEDE_SESSION_CACHE[target_phrase] = pcm24k
                _LIVE_AOEDE_SOURCE_CACHE[target_phrase] = audio_source
        except Exception as exc:
            err_msg = str(exc)
            if api_key:
                err_msg = err_msg.replace(api_key, "***")
            _LOGGER.warning("Aoede live audio synthesis failed (%s): %s", type(exc).__name__, err_msg[:180])
            pcm24k = b""

    if not pcm24k:
        pcm24k = _load_bundled_aoede_pcm24k(target_phrase)
        if pcm24k:
            audio_source = "bundled_aoede_wav"
            if target_phrase in (
                FIXED_REJECTION_PHRASE_VI,
                FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
            ):
                _LIVE_AOEDE_SESSION_CACHE[target_phrase] = pcm24k
                _LIVE_AOEDE_SOURCE_CACHE[target_phrase] = audio_source
        else:
            audio_source = "none"

    wav24k = _wrap_pcm24k_to_wav(pcm24k) if pcm24k else b""
    pcm_b64 = base64.b64encode(pcm24k).decode("ascii") if pcm24k else ""
    wav_b64 = base64.b64encode(wav24k).decode("ascii") if wav24k else ""
    return {
        "pcm24k_bytes": pcm24k,
        "wav24k_bytes": wav24k,
        "pcm24k_b64": pcm_b64,
        "pcm_b64": pcm_b64,
        "audio_wav_b64": wav_b64,
        "audio_b64": wav_b64,
        "audio_sample_rate": SAMPLE_RATE,
        "audio_voice": AOEDE_VOICE_NAME,
        "voice_name": AOEDE_VOICE_NAME,
        "audio_source": audio_source or "none",
        "play_audio": bool(pcm_b64),
        "audio_mime_type": "audio/wav",
    }


def build_aoede_http_audio_fields(bundle: dict[str, Any]) -> dict[str, Any]:
    """Trích xuất các trường JSON an toàn từ kết quả synthesize_aoede_phrase_audio cho phản hồi HTTP."""
    pcm_b64 = str(bundle.get("pcm_b64") or "")
    return {
        "pcm24k_b64": str(bundle.get("pcm24k_b64") or ""),
        "pcm_b64": pcm_b64,
        "audio_wav_b64": str(bundle.get("audio_wav_b64") or ""),
        "audio_b64": str(bundle.get("audio_b64") or ""),
        "audio_sample_rate": int(bundle.get("audio_sample_rate") or SAMPLE_RATE),
        "audio_voice": str(bundle.get("audio_voice") or AOEDE_VOICE_NAME),
        "voice_name": str(bundle.get("voice_name") or AOEDE_VOICE_NAME),
        "audio_source": str(bundle.get("audio_source") or ("gemini_live_aoede" if pcm_b64 else "none")),
        "play_audio": bool(bundle.get("play_audio", bool(pcm_b64))),
        "audio_mime_type": str(bundle.get("audio_mime_type") or "audio/wav"),
    }
