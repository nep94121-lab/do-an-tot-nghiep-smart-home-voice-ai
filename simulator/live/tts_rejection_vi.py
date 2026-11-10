"""Module Hằng Số Câu Thoại Từ Chối Tiếng Việt Chuẩn Cho Giọng Aoede (Gemini Live).

Mọi câu từ chối (Người lạ & Vượt quyền) và yêu cầu nói lại (Safe-Deny) chỉ được phát
thông qua duy nhất giọng đọc tích hợp `Aoede` của Gemini Live (tuyệt đối không dùng
TTS riêng bên ngoài hay Web Speech API).
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import pathlib
import wave
from typing import Any

SAMPLE_RATE = 24000
AOEDE_VOICE_NAME = "Aoede"
AOEDE_LIVE_MODEL = "gemini-3.8-live"

FIXED_REJECTION_PHRASE_VI = "Xin lỗi, bạn không có quyền thực hiện lệnh này."
FIXED_SAFE_DENY_REPEAT_PHRASE_VI = "Âm thanh chưa rõ, vui lòng nói lại."
UNIFIED_REJECTION_PHRASE_VI = FIXED_REJECTION_PHRASE_VI
SAFE_DENY_REPEAT_PHRASE_VI = FIXED_SAFE_DENY_REPEAT_PHRASE_VI

_DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
_AOEDE_REJECTION_WAV_FILE = _DATA_DIR / "aoede_rejection_24k.wav"
_AOEDE_REPEAT_WAV_FILE = _DATA_DIR / "aoede_repeat_24k.wav"
_LIVE_AOEDE_SESSION_CACHE: dict[str, bytes] = {}

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
    wav_file = (
        _AOEDE_REPEAT_WAV_FILE
        if phrase == FIXED_SAFE_DENY_REPEAT_PHRASE_VI
        else _AOEDE_REJECTION_WAV_FILE
    )
    if wav_file.exists():
        raw = wav_file.read_bytes()
        with wave.open(io.BytesIO(raw), "rb") as wf:
            return wf.readframes(wf.getnframes())
    return b""


async def _fetch_live_aoede_pcm24k(phrase: str, api_key: str) -> bytes:
    """Gọi trực tiếp Gemini Live (gemini-3.8-live, voice_name='Aoede') tạo PCM 24kHz cho câu cố định."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    cfg = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        speech_config=types.SpeechConfig(
            language_code="vi-VN",
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=AOEDE_VOICE_NAME)
            ),
        ),
        system_instruction=types.Content(
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
    )
    chunks: list[bytes] = []
    async with client.aio.live.connect(model=AOEDE_LIVE_MODEL, config=cfg) as session:
        await session.send_client_content(
            turns=[
                types.Content(
                    role="user",
                    parts=[types.Part(text=f'Hãy đọc đúng nguyên văn câu này: "{phrase}"')],
                )
            ],
            turn_complete=True,
        )
        async for msg in session.receive():
            sc = getattr(msg, "server_content", None)
            if sc is not None:
                mt = getattr(sc, "model_turn", None)
                if mt and getattr(mt, "parts", None):
                    for part in mt.parts:
                        inl = getattr(part, "inline_data", None)
                        if inl and getattr(inl, "data", None):
                            chunks.append(bytes(inl.data))
                if getattr(sc, "turn_complete", False):
                    break
    pcm = b"".join(chunks)
    return pcm if len(pcm) % 2 == 0 else pcm[:-1]


async def synthesize_aoede_phrase_audio(
    phrase: str, *, allow_live_refresh: bool = True
) -> dict[str, Any]:
    """Trả về gói âm thanh PCM16 24kHz & WAV chuẩn của duy nhất giọng Aoede (Gemini Live)."""
    target_phrase = (
        FIXED_SAFE_DENY_REPEAT_PHRASE_VI
        if (phrase or "").strip() == FIXED_SAFE_DENY_REPEAT_PHRASE_VI
        else FIXED_REJECTION_PHRASE_VI
    )
    pcm24k = _LIVE_AOEDE_SESSION_CACHE.get(target_phrase, b"")

    is_offline = (
        os.environ.get("SIMULATOR_OFFLINE_SANDBOX", "").strip() == "1"
        or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    )
    api_key = (
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GOOGLE_API_KEY", "").strip()
    )
    if not pcm24k and allow_live_refresh and api_key and not is_offline:
        try:
            live_pcm = await asyncio.wait_for(
                _fetch_live_aoede_pcm24k(target_phrase, api_key), timeout=5.5
            )
            if len(live_pcm) >= SAMPLE_RATE * 2:
                pcm24k = live_pcm
                _LIVE_AOEDE_SESSION_CACHE[target_phrase] = pcm24k
        except Exception:
            pcm24k = b""

    if not pcm24k:
        pcm24k = _load_bundled_aoede_pcm24k(target_phrase)
        if pcm24k:
            _LIVE_AOEDE_SESSION_CACHE[target_phrase] = pcm24k

    wav24k = _wrap_pcm24k_to_wav(pcm24k)
    pcm_b64 = base64.b64encode(pcm24k).decode("ascii")
    wav_b64 = base64.b64encode(wav24k).decode("ascii")
    return {
        "pcm24k_bytes": pcm24k,
        "wav24k_bytes": wav24k,
        "pcm24k_b64": pcm_b64,
        "pcm_b64": pcm_b64,
        "audio_wav_b64": wav_b64,
        "audio_b64": wav_b64,
        "audio_sample_rate": SAMPLE_RATE,
        "audio_voice": AOEDE_VOICE_NAME,
        "audio_mime_type": "audio/wav",
    }


def build_aoede_http_audio_fields(bundle: dict[str, Any]) -> dict[str, Any]:
    """Trích xuất các trường JSON an toàn từ kết quả synthesize_aoede_phrase_audio cho phản hồi HTTP."""
    return {
        "pcm24k_b64": str(bundle.get("pcm24k_b64") or ""),
        "pcm_b64": str(bundle.get("pcm_b64") or ""),
        "audio_wav_b64": str(bundle.get("audio_wav_b64") or ""),
        "audio_b64": str(bundle.get("audio_b64") or ""),
        "audio_sample_rate": int(bundle.get("audio_sample_rate") or SAMPLE_RATE),
        "audio_voice": str(bundle.get("audio_voice") or AOEDE_VOICE_NAME),
        "audio_mime_type": str(bundle.get("audio_mime_type") or "audio/wav"),
    }
