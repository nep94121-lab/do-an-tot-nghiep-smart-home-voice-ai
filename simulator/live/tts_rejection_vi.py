"""Module Hằng Số Câu Thoại Từ Chối Tiếng Việt Chuẩn Cho Giọng Aoede (Gemini Live).

Mọi câu từ chối (Người lạ & Vượt quyền) và yêu cầu nói lại (Safe-Deny) chỉ được phát
thông qua duy nhất giọng đọc tích hợp `Aoede` của Gemini Live (tuyệt đối không dùng
TTS riêng bên ngoài hay Web Speech API).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import inspect
import io
import logging
import os
import pathlib
import time
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
    "gemini-2.5-flash-native-audio-preview-12-2025",
    "gemini-2.0-flash-live-001",
    "gemini-3.1-flash-live-preview",
)
_WORKING_AOEDE_LIVE_MODEL: str = ""
_WORKING_AOEDE_API_VERSION: str = ""
_WORKING_AOEDE_USE_CLIENT_CONTENT: bool = False
_WARMING_PHRASES: set[str] = set()
_REJECTED_AOEDE_MODELS: set[tuple[str, str]] = set()

FIXED_REJECTION_PHRASE_VI = "Xin lỗi, bạn không có quyền thực hiện lệnh này."
FIXED_SAFE_DENY_REPEAT_PHRASE_VI = "Âm thanh chưa rõ, vui lòng nói lại."
UNIFIED_REJECTION_PHRASE_VI = FIXED_REJECTION_PHRASE_VI
SAFE_DENY_REPEAT_PHRASE_VI = FIXED_SAFE_DENY_REPEAT_PHRASE_VI

_DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
_AOEDE_REJECTION_WAV_FILE = _DATA_DIR / "aoede_rejection_24k.wav"
_AOEDE_REPEAT_WAV_FILE = _DATA_DIR / "aoede_repeat_24k.wav"
_LIVE_AOEDE_SESSION_CACHE: dict[str, bytes] = {}
_LIVE_AOEDE_SOURCE_CACHE: dict[str, str] = {}
_LIVE_AOEDE_MODEL_CACHE: dict[str, str] = {}

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


def _create_live_client(clean_key: str, api_version: str = "v1beta") -> Any:
    """Khởi tạo GenAI Client với api_version='v1beta'/'v1alpha' (google-genai>=3.0 mặc định 'v1' gây 404 Live WS)."""
    try:
        return genai.Client(
            api_key=clean_key,
            http_options=types.HttpOptions(api_version=api_version),
        )
    except TypeError:
        return genai.Client(api_key=clean_key)


def _normalize_aoede_phrase(phrase: str) -> str:
    return " ".join((phrase or "").strip().split())


def _aoede_cache_key(phrase_norm: str) -> str:
    return hashlib.sha256(f"{AOEDE_VOICE_NAME}:{phrase_norm}".encode("utf-8")).hexdigest()


def _resolve_aoede_db_path() -> pathlib.Path | None:
    if os.environ.get("SMARTHOME_DISABLE_SQLITE", "").strip() == "1":
        return None
    if os.environ.get("VERCEL", "").strip() == "1":
        return None
    if (
        os.environ.get("SMARTHOME_STATE_BACKEND", "").strip().lower() == "file"
        and not os.environ.get("SMARTHOME_SQLITE_PATH", "").strip()
    ):
        return None
    try:
        from simulator.db_migrations import resolve_sqlite_db_path

        return resolve_sqlite_db_path()
    except Exception:
        return None


def _read_sqlite_aoede_cache(phrase: str) -> tuple[bytes, str]:
    db_path = _resolve_aoede_db_path()
    if db_path is None or not db_path.exists():
        return b"", ""
    norm = _normalize_aoede_phrase(phrase)
    if not norm:
        return b"", ""
    key = _aoede_cache_key(norm)
    conn = None
    try:
        from simulator.db_migrations import open_wal_connection

        conn = open_wal_connection(db_path, readonly=True)
        row = conn.execute(
            """
            SELECT pcm_bytes, model_id FROM aoede_audio_cache
            WHERE cache_key = ? OR (phrase_norm = ? AND voice_name = ?)
            ORDER BY created_at DESC LIMIT 1
            """,
            (key, norm, AOEDE_VOICE_NAME),
        ).fetchone()
        if row is not None and row["pcm_bytes"]:
            raw = bytes(row["pcm_bytes"])
            if len(raw) >= 2400:
                return raw, str(row["model_id"] or "")
    except Exception:
        pass
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()
    return b"", ""


def _write_sqlite_aoede_cache(phrase: str, pcm_bytes: bytes, model_id: str) -> None:
    if len(pcm_bytes) < 2400:
        return
    db_path = _resolve_aoede_db_path()
    if db_path is None or not db_path.exists():
        return
    norm = _normalize_aoede_phrase(phrase)
    if not norm:
        return
    key = _aoede_cache_key(norm)
    conn = None
    try:
        from simulator.db_migrations import (
            apply_schema_migrations,
            open_wal_connection,
            run_write_transaction,
        )

        conn = open_wal_connection(db_path, readonly=False)

        def _upsert(c: Any) -> None:
            c.execute(
                """
                INSERT INTO aoede_audio_cache (
                    cache_key, phrase_norm, voice_name, model_id, sample_rate, pcm_bytes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    phrase_norm = excluded.phrase_norm,
                    voice_name = excluded.voice_name,
                    model_id = excluded.model_id,
                    sample_rate = excluded.sample_rate,
                    pcm_bytes = excluded.pcm_bytes,
                    created_at = excluded.created_at
                """,
                (key, norm, AOEDE_VOICE_NAME, str(model_id or ""), SAMPLE_RATE, pcm_bytes, time.time()),
            )

        try:
            run_write_transaction(conn, _upsert)
        except Exception:
            apply_schema_migrations(conn)
            run_write_transaction(conn, _upsert)
    except Exception as exc:
        _LOGGER.debug("Skipping SQLite aoede_audio_cache write: %s", exc)
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()


def _load_last_working_aoede_model() -> str:
    db_path = _resolve_aoede_db_path()
    if db_path is None or not db_path.exists():
        return ""
    conn = None
    try:
        from simulator.db_migrations import open_wal_connection

        conn = open_wal_connection(db_path, readonly=True)
        row = conn.execute(
            "SELECT model_id FROM aoede_audio_cache WHERE model_id != '' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row and row["model_id"]:
            return str(row["model_id"])
    except Exception:
        pass
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()
    return ""


async def _fetch_live_aoede_pcm24k(
    phrase: str,
    api_key: str,
    *,
    per_attempt_timeout: float = 2.2,
) -> bytes:
    """Gọi trực tiếp Gemini Live (gemini-3.8-live / fallback Live cùng giọng 'Aoede') tạo PCM 24kHz."""
    global _WORKING_AOEDE_LIVE_MODEL, _WORKING_AOEDE_API_VERSION, _WORKING_AOEDE_USE_CLIENT_CONTENT
    if genai is None or types is None:
        raise RuntimeError("google-genai SDK is not installed")

    clean_key = (api_key or "").strip().strip('"').strip("'").strip()
    if not clean_key:
        raise RuntimeError("GEMINI_API_KEY is empty")

    clients_by_ver: dict[str, Any] = {}

    def _client_for(api_version: str) -> Any:
        c = clients_by_ver.get(api_version)
        if c is None:
            c = _create_live_client(clean_key, api_version=api_version)
            clients_by_ver[api_version] = c
        return c

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

    async def _attempt_one_model(
        cand_model: str, *, api_version: str = "v1beta", use_client_content: bool = False
    ) -> bytes:
        chunks: list[bytes] = []
        client = _client_for(api_version)
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
                if turn_done or not saw_msg:
                    break
        pcm = b"".join(chunks)
        if len(pcm) % 2 != 0:
            pcm = pcm[:-1]
        if len(pcm) < 2400:
            raise RuntimeError(
                f"Live model {cand_model} ({api_version}) returned insufficient audio ({len(pcm)} bytes)"
            )
        return pcm

    attempts: list[tuple[str, str, bool]] = []
    cached_model = _WORKING_AOEDE_LIVE_MODEL or _load_last_working_aoede_model()
    if cached_model:
        attempts.append(
            (
                cached_model,
                _WORKING_AOEDE_API_VERSION or "v1beta",
                _WORKING_AOEDE_USE_CLIENT_CONTENT if _WORKING_AOEDE_LIVE_MODEL else (not cached_model.startswith("gemini-3.")),
            )
        )
    if (AOEDE_LIVE_MODEL, "v1beta", False) not in attempts:
        attempts.append((AOEDE_LIVE_MODEL, "v1beta", False))
    for fb_model in _AOEDE_FALLBACK_LIVE_MODELS:
        default_cc = not fb_model.startswith("gemini-3.")
        pair = (fb_model, "v1beta", default_cc)
        if pair not in attempts:
            attempts.append(pair)

    tried: set[tuple[str, str, bool]] = set()
    last_exc: Exception | None = None
    idx = 0
    while idx < len(attempts):
        cand_model, api_ver, use_cc = attempts[idx]
        idx += 1
        if (cand_model, api_ver, use_cc) in tried or (cand_model, api_ver) in _REJECTED_AOEDE_MODELS:
            continue
        tried.add((cand_model, api_ver, use_cc))
        attempt_timeout = max(0.5, float(per_attempt_timeout))
        if cand_model == AOEDE_LIVE_MODEL and not cached_model and len(attempts) > 1:
            attempt_timeout = min(0.65, attempt_timeout)
        try:
            pcm = await asyncio.wait_for(
                _attempt_one_model(cand_model, api_version=api_ver, use_client_content=use_cc),
                timeout=attempt_timeout,
            )
            _WORKING_AOEDE_LIVE_MODEL = cand_model
            _WORKING_AOEDE_API_VERSION = api_ver
            _WORKING_AOEDE_USE_CLIENT_CONTENT = use_cc
            return pcm
        except Exception as exc:
            last_exc = exc
            err_msg = str(exc).replace(clean_key, "***")
            _LOGGER.warning(
                "Aoede live attempt failed on %s (%s, cc=%s, %s): %s",
                cand_model,
                api_ver,
                use_cc,
                type(exc).__name__,
                err_msg[:180],
            )
            is_model_rejected = any(
                tok in err_msg.lower()
                for tok in ("404", "1007", "1008", "not found", "not_found", "unsupported", "invalid argument")
            )
            if is_model_rejected:
                _REJECTED_AOEDE_MODELS.add((cand_model, api_ver))
            is_timeout_or_short = (
                isinstance(exc, (TimeoutError, asyncio.TimeoutError))
                or "insufficient audio" in err_msg.lower()
            )
            if (
                cand_model.startswith("gemini-3.")
                and not use_cc
                and (is_timeout_or_short or "1007" in err_msg.lower() or "invalid argument" in err_msg.lower())
                and "404" not in err_msg.lower()
                and "1008" not in err_msg.lower()
                and (cand_model, api_ver, True) not in tried
            ):
                attempts.insert(idx, (cand_model, api_ver, True))
            if api_ver == "v1beta" and is_model_rejected and (cand_model, "v1alpha", use_cc) not in tried:
                attempts.append((cand_model, "v1alpha", use_cc))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("No Aoede live model candidates configured")


async def _invoke_live_aoede_fetch(
    phrase: str,
    api_key: str,
    *,
    per_attempt_timeout: float,
) -> bytes:
    """Invoke _fetch_live_aoede_pcm24k while preserving compatibility with 2-arg monkeypatch fakes."""
    fn = _fetch_live_aoede_pcm24k
    try:
        params = inspect.signature(fn).parameters
        accepts_timeout = (
            "per_attempt_timeout" in params
            or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        )
    except (TypeError, ValueError):
        accepts_timeout = False
    if accepts_timeout:
        return await fn(phrase, api_key, per_attempt_timeout=per_attempt_timeout)
    return await fn(phrase, api_key)


async def _background_warm_phrase(phrase: str, api_key: str) -> None:
    norm = _normalize_aoede_phrase(phrase)
    if not norm or norm in _WARMING_PHRASES:
        return
    _WARMING_PHRASES.add(norm)
    try:
        live_pcm = await asyncio.wait_for(
            _invoke_live_aoede_fetch(norm, api_key, per_attempt_timeout=8.0),
            timeout=10.0,
        )
        if len(live_pcm) >= 2400:
            model_id = _WORKING_AOEDE_LIVE_MODEL or AOEDE_LIVE_MODEL
            _LIVE_AOEDE_SESSION_CACHE[norm] = live_pcm
            _LIVE_AOEDE_SOURCE_CACHE[norm] = "gemini_live_aoede"
            _LIVE_AOEDE_MODEL_CACHE[norm] = model_id
            _write_sqlite_aoede_cache(norm, live_pcm, model_id)
    except Exception:
        pass
    finally:
        _WARMING_PHRASES.discard(norm)


async def synthesize_aoede_phrase_audio(
    phrase: str,
    *,
    allow_live_refresh: bool = True,
    interactive_budget_sec: float = 2.4,
) -> dict[str, Any]:
    """Trả về gói âm thanh PCM16 24kHz & WAV chuẩn của duy nhất giọng Aoede (Gemini Live) kèm SQLite cache."""
    clean_phrase = (phrase or "").strip()
    target_phrase = clean_phrase or FIXED_REJECTION_PHRASE_VI
    norm_phrase = _normalize_aoede_phrase(target_phrase)

    pcm24k = _LIVE_AOEDE_SESSION_CACHE.get(target_phrase) or _LIVE_AOEDE_SESSION_CACHE.get(norm_phrase, b"")
    audio_source = (
        _LIVE_AOEDE_SOURCE_CACHE.get(target_phrase)
        or _LIVE_AOEDE_SOURCE_CACHE.get(norm_phrase, "")
    ) if pcm24k else ""
    audio_model = (
        _LIVE_AOEDE_MODEL_CACHE.get(target_phrase)
        or _LIVE_AOEDE_MODEL_CACHE.get(norm_phrase, "")
    ) if pcm24k else ""

    if not pcm24k:
        db_pcm, db_model = _read_sqlite_aoede_cache(norm_phrase)
        if len(db_pcm) >= 2400:
            pcm24k = db_pcm
            audio_model = db_model or _WORKING_AOEDE_LIVE_MODEL or "gemini-2.5-flash-native-audio-preview-12-2025"
            audio_source = "gemini_live_aoede" if audio_model != "bundled_aoede" else "bundled_aoede_wav"
            _LIVE_AOEDE_SESSION_CACHE[target_phrase] = pcm24k
            _LIVE_AOEDE_SOURCE_CACHE[target_phrase] = audio_source
            _LIVE_AOEDE_MODEL_CACHE[target_phrase] = audio_model
            _LIVE_AOEDE_SESSION_CACHE[norm_phrase] = pcm24k
            _LIVE_AOEDE_SOURCE_CACHE[norm_phrase] = audio_source
            _LIVE_AOEDE_MODEL_CACHE[norm_phrase] = audio_model

    is_offline = (
        os.environ.get("SIMULATOR_OFFLINE_SANDBOX", "").strip() == "1"
        or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    )
    raw_api_key = (
        os.environ.get("GEMINI_API_KEY", "")
        or os.environ.get("GOOGLE_API_KEY", "")
    )
    if not raw_api_key and not is_offline:
        with contextlib.suppress(Exception):
            from simulator.api.deps import load_key

            raw_api_key = load_key()
    api_key = raw_api_key.strip().strip('"').strip("'").strip()
    if not pcm24k and allow_live_refresh and api_key and not is_offline:
        try:
            budget = max(0.8, float(interactive_budget_sec))
            live_pcm = await asyncio.wait_for(
                _invoke_live_aoede_fetch(
                    target_phrase,
                    api_key,
                    per_attempt_timeout=min(2.2, budget),
                ),
                timeout=budget,
            )
            if len(live_pcm) >= 2400:
                pcm24k = live_pcm
                audio_source = "gemini_live_aoede"
                audio_model = _WORKING_AOEDE_LIVE_MODEL or AOEDE_LIVE_MODEL
                _LIVE_AOEDE_SESSION_CACHE[target_phrase] = pcm24k
                _LIVE_AOEDE_SOURCE_CACHE[target_phrase] = audio_source
                _LIVE_AOEDE_MODEL_CACHE[target_phrase] = audio_model
                _LIVE_AOEDE_SESSION_CACHE[norm_phrase] = pcm24k
                _LIVE_AOEDE_SOURCE_CACHE[norm_phrase] = audio_source
                _LIVE_AOEDE_MODEL_CACHE[norm_phrase] = audio_model
                _write_sqlite_aoede_cache(norm_phrase, pcm24k, audio_model)
        except Exception as exc:
            err_msg = str(exc)
            if api_key:
                err_msg = err_msg.replace(api_key, "***")
            _LOGGER.warning("Aoede live audio synthesis failed (%s): %s", type(exc).__name__, err_msg[:180])
            if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
                with contextlib.suppress(RuntimeError):
                    asyncio.create_task(_background_warm_phrase(target_phrase, api_key))
            pcm24k = b""

    if not pcm24k:
        pcm24k = _load_bundled_aoede_pcm24k(target_phrase)
        if pcm24k:
            audio_source = "bundled_aoede_wav"
            audio_model = ""
            if target_phrase in (
                FIXED_REJECTION_PHRASE_VI,
                FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
            ):
                _LIVE_AOEDE_SESSION_CACHE[target_phrase] = pcm24k
                _LIVE_AOEDE_SOURCE_CACHE[target_phrase] = audio_source
                _LIVE_AOEDE_MODEL_CACHE[target_phrase] = ""
        else:
            audio_source = "none"
            audio_model = ""

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
        "audio_model": audio_model or None,
        "play_audio": bool(pcm_b64),
        "audio_mime_type": "audio/wav",
    }


def build_aoede_http_audio_fields(bundle: dict[str, Any]) -> dict[str, Any]:
    """Trích xuất các trường JSON an toàn từ kết quả synthesize_aoede_phrase_audio cho phản hồi HTTP."""
    pcm_b64 = str(bundle.get("pcm_b64") or "")
    fields: dict[str, Any] = {
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
    if bundle.get("audio_model"):
        fields["audio_model"] = str(bundle["audio_model"])
    return fields


async def prewarm_aoede_common_phrases() -> int:
    """Làm ấm trước bộ câu thoại Aoede phổ biến vào SQLite WAL cache khi server khởi động."""
    if (
        os.environ.get("PYTEST_CURRENT_TEST")
        or os.environ.get("SIMULATOR_OFFLINE_SANDBOX", "").strip() == "1"
        or os.environ.get("SMARTHOME_SKIP_PREWARM", "").strip() == "1"
    ):
        return 0
    phrases: list[str] = [
        FIXED_REJECTION_PHRASE_VI,
        FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
        "Đã bật đèn phòng khách.",
        "Đã tắt đèn phòng khách.",
        "Đã bật Đèn phòng khách.",
        "Đã tắt Đèn phòng khách.",
        "Đã bật đèn phòng ngủ.",
        "Đã tắt đèn phòng ngủ.",
        "Đã bật quạt trần.",
        "Đã tắt quạt trần.",
        "Đã bật điều hòa.",
        "Đã tắt điều hòa.",
        "Đã mở cửa chính.",
        "Đã khóa cửa chính.",
        "Đã đóng cửa chính.",
        "Đã bật bơm tưới sân vườn.",
        "Đã tắt bơm tưới sân vườn.",
        "Đã bật còi báo động.",
        "Đã tắt còi báo động.",
        "Cửa chính đã mở.",
        "Cửa chính đã đóng.",
        "Đèn phòng khách đã bật.",
        "Đèn phòng khách đã tắt.",
    ]
    for p in EXTENDED_TTS_SCRIPTS.values():
        if p not in phrases:
            phrases.append(p)
    warmed = 0
    for phrase in phrases:
        for _ in range(30):
            active_mic = False
            with contextlib.suppress(Exception):
                from simulator.api.deps import _ACTIVE_BRIDGES

                active_mic = any(
                    getattr(br, "mic_utterance_active", False)
                    for br in list(_ACTIVE_BRIDGES)
                    if not getattr(br, "_closed", False)
                )
            if not active_mic:
                break
            await asyncio.sleep(1.0)
        norm = _normalize_aoede_phrase(phrase)
        if not norm:
            continue
        existing, _ = _read_sqlite_aoede_cache(norm)
        if len(existing) >= 2400:
            _LIVE_AOEDE_SESSION_CACHE[norm] = existing
            _LIVE_AOEDE_SOURCE_CACHE[norm] = "gemini_live_aoede"
            continue
        try:
            res = await synthesize_aoede_phrase_audio(norm, allow_live_refresh=True, interactive_budget_sec=9.0)
            if res.get("pcm24k_b64") and res.get("audio_source") == "gemini_live_aoede":
                warmed += 1
        except Exception:
            pass
    return warmed
