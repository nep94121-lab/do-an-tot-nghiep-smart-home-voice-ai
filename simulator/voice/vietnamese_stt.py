"""Local offline Vietnamese Whisper STT with noise/hallucination guards."""

from __future__ import annotations

import logging
import math
import os
import pathlib
import re
import threading
import time
from typing import Any

import numpy as np

LOG = logging.getLogger("simulator.voice.vietnamese_stt")

_MODEL_LOCK = threading.Lock()
_CACHED_MODEL: Any = None
_CACHED_MODEL_NAME: str = ""
_LOAD_FAILED: bool = False

_SMART_HOME_VI_PROMPT = (
    "Mở cửa chính, đóng cửa chính, bật đèn phòng khách, tắt đèn phòng khách, "
    "bật đèn phòng ngủ, tắt đèn phòng ngủ, bật tất cả đèn, tắt hết đèn, "
    "bật máy bơm tưới cây, tắt máy bơm, bật còi báo động, tắt còi báo động, "
    "bật nguồn mạch loa, tắt nguồn mạch loa, nhiệt độ, độ ẩm không khí, độ ẩm đất, "
    "cảm biến âm thanh KY-037, hẹn giờ, đặt lịch, tạo lệnh, liên kết, reset, "
    "chào bạn, cảm ơn, ok, đồng ý, hủy."
)

_HALLUCINATION_RE = re.compile(
    r"(?:"
    r"hãy\s+subscribe|subscribe\s+cho\s+kênh|đăng\s+ký\s+kênh|bấm\s+chuông|"
    r"cảm\s+ơn\s+(?:các\s+bạn\s+)?đã\s+(?:xem|theo\s+dõi)|"
    r"hẹn\s+gặp\s+lại\s+các\s+bạn|video\s+tiếp\s+theo|like\s+và\s+share|"
    r"chào\s+mừng\s+các\s+bạn\s+đến\s+với\s+kênh|theo\s+dõi\s+kênh|"
    r"người\s+dịch|phụ\s+đề\s+bởi|amara\.org|ghiền\s+mì\s+gõ"
    r")",
    re.IGNORECASE,
)


def _find_local_whisper_snapshot(model_size: str) -> str | None:
    """Resolve local HuggingFace cache snapshot for faster-whisper-<size> even if HOME is overridden."""
    repo_folder = f"models--Systran--faster-whisper-{model_size}"
    candidate_hubs: list[pathlib.Path] = []
    hf_home = os.environ.get("HF_HOME", "").strip()
    if hf_home:
        candidate_hubs.append(pathlib.Path(hf_home) / "hub")
    candidate_hubs.append(pathlib.Path.home() / ".cache" / "huggingface" / "hub")
    # Fallback to Windows user profile parent when running under an isolated HOME (e.g. agyhome4)
    home_parent = pathlib.Path.home().parent
    candidate_hubs.append(home_parent / ".cache" / "huggingface" / "hub")
    win_user = os.environ.get("USERNAME", "").strip()
    if win_user:
        candidate_hubs.append(pathlib.Path("C:/Users") / win_user / ".cache" / "huggingface" / "hub")

    seen: set[str] = set()
    for hub in candidate_hubs:
        key = str(hub)
        if key in seen:
            continue
        seen.add(key)
        snap_root = hub / repo_folder / "snapshots"
        if not snap_root.is_dir():
            continue
        for snap in sorted(snap_root.iterdir(), reverse=True):
            if snap.is_dir() and (snap / "model.bin").is_file():
                return str(snap)
    return None


def _get_whisper_model() -> Any:
    global _CACHED_MODEL, _CACHED_MODEL_NAME, _LOAD_FAILED
    if os.environ.get("SMARTHOME_DISABLE_LOCAL_STT", "0").strip() == "1":
        return None
    if _CACHED_MODEL is not None:
        return _CACHED_MODEL
    if _LOAD_FAILED:
        return None

    with _MODEL_LOCK:
        if _CACHED_MODEL is not None:
            return _CACHED_MODEL
        if _LOAD_FAILED:
            return None
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            LOG.warning("faster_whisper unavailable: %s", exc)
            _LOAD_FAILED = True
            return None

        preferred = os.environ.get("SMARTHOME_WHISPER_MODEL", "small").strip() or "small"
        candidates = [preferred]
        if preferred != "tiny":
            candidates.append("tiny")

        for size in candidates:
            snap_path = _find_local_whisper_snapshot(size)
            model_arg = snap_path or size
            try:
                model = WhisperModel(
                    model_arg,
                    device="cpu",
                    compute_type="int8",
                    local_files_only=True,
                )
                _CACHED_MODEL = model
                _CACHED_MODEL_NAME = size
                LOG.info("Loaded local Vietnamese Whisper model: %s (%s)", size, model_arg)
                return _CACHED_MODEL
            except Exception as exc:
                LOG.debug("Failed loading faster-whisper model %s: %s", size, exc)

        _LOAD_FAILED = True
        return None


def _analyze_and_preprocess_audio(pcm16: np.ndarray, sr: int = 16000) -> tuple[np.ndarray, bool]:
    """Return (float32_16k_audio, is_noise_or_silence)."""
    if pcm16 is None or pcm16.size < int(sr * 0.15):
        return np.array([], dtype=np.float32), True

    if np.issubdtype(pcm16.dtype, np.floating):
        x = pcm16.astype(np.float64)
        if float(np.max(np.abs(x))) > 1.5:
            x = x / 32768.0
    else:
        x = pcm16.astype(np.float64) / 32768.0

    # Resample linearly if sample rate differs from 16kHz
    if sr != 16000 and sr > 0:
        target_len = max(1, int(round(x.size * 16000.0 / float(sr))))
        idx = np.linspace(0.0, float(x.size - 1), target_len)
        x = np.interp(idx, np.arange(x.size, dtype=np.float64), x)
        sr = 16000

    # DC removal
    x = x - float(np.mean(x))
    if not np.all(np.isfinite(x)):
        x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)

    rms = float(np.sqrt(np.mean(x * x)))
    peak = float(np.max(np.abs(x)))
    if rms < 0.0012 or peak < 0.004:
        return np.array([], dtype=np.float32), True

    # Frame-level energy modulation & spectral flatness check to reject flat white noise / steady tones
    frame_len = 320  # 20ms at 16kHz
    n_frames = x.size // frame_len
    if n_frames >= 8:
        frames = x[: n_frames * frame_len].reshape(n_frames, frame_len)
        frame_rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
        rms_mean = float(np.mean(frame_rms))
        rms_cv = float(np.std(frame_rms) / max(rms_mean, 1e-9))

        # Spectral flatness on FFT of active signal
        win_n = min(x.size, 16384)
        spec = np.abs(np.fft.rfft(x[:win_n] * np.hanning(win_n))) ** 2 + 1e-18
        geo_mean = float(np.exp(np.mean(np.log(spec))))
        arith_mean = float(np.mean(spec))
        flatness = geo_mean / max(arith_mean, 1e-18)

        # Stationary broadband white noise: high spectral flatness AND low temporal modulation
        if flatness > 0.55 and rms_cv < 0.18:
            return np.array([], dtype=np.float32), True

        # Pure steady synthetic sine tone: >92% of energy in top 3 bins AND flat envelope
        top3_ratio = float(np.sum(np.sort(spec)[-3:]) / max(float(np.sum(spec)), 1e-18))
        if top3_ratio > 0.92 and rms_cv < 0.15:
            return np.array([], dtype=np.float32), True

    # Simple first-order high-pass filter (~75 Hz) to strip DC/hum rumble
    if x.size > 2:
        hp = np.empty_like(x)
        hp[0] = x[0]
        alpha = 0.97
        # Vectorized approximation via difference + decay is slower in pure Python; use lightweight IIR via scipy if available or single-pass
        try:
            from scipy.signal import lfilter

            hp = lfilter([1.0, -1.0], [1.0, -alpha], x)
        except Exception:
            hp = x
        x = hp

    # Soft de-clipping when input is heavily clipped
    clipped_ratio = float(np.mean(np.abs(x) >= 0.985))
    if clipped_ratio > 0.01:
        x = np.tanh(x * 0.92) / math.tanh(0.92)

    # Gentle gain normalization for low-volume speech (boost up to peak 0.75, max gain 20x)
    new_peak = float(np.max(np.abs(x)))
    if 0.004 <= new_peak < 0.55:
        gain = min(20.0, 0.75 / new_peak)
        x = np.clip(x * gain, -0.98, 0.98)

    return x.astype(np.float32), False


def _clean_whisper_text(raw_text: str) -> str:
    txt = re.sub(r"\s+", " ", str(raw_text or "")).strip()
    if not txt:
        return ""
    if _HALLUCINATION_RE.search(txt):
        cleaned = _HALLUCINATION_RE.sub("", txt)
        cleaned = re.sub(r"^[\s.,!?;:\-]+|[\s.,!?;:\-]+$", "", cleaned).strip()
        txt = cleaned
    if len(txt) <= 1 and not txt.isalnum():
        return ""
    return txt


def transcribe_vietnamese_pcm16k(
    pcm16: np.ndarray,
    sr: int = 16000,
) -> dict[str, Any]:
    """Transcribe 16kHz mono PCM16 Vietnamese speech locally using faster-whisper."""
    t0 = time.perf_counter()
    audio_f32, is_noise = _analyze_and_preprocess_audio(pcm16, sr=sr)
    if is_noise or audio_f32.size == 0:
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": True,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
        }

    model = _get_whisper_model()
    if model is None:
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": False,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
        }

    try:
        segments, _info = model.transcribe(
            audio_f32,
            language="vi",
            task="transcribe",
            beam_size=1,
            best_of=1,
            temperature=0.0,
            max_new_tokens=64,
            without_timestamps=True,
            vad_filter=True,
            condition_on_previous_text=False,
            no_speech_threshold=0.65,
            initial_prompt=_SMART_HOME_VI_PROMPT,
        )
        kept_texts: list[str] = []
        confidences: list[float] = []
        for seg in segments:
            no_speech_prob = float(getattr(seg, "no_speech_prob", 0.0) or 0.0)
            avg_logprob = float(getattr(seg, "avg_logprob", 0.0) or 0.0)
            if no_speech_prob > 0.78 or avg_logprob < -1.35:
                continue
            seg_txt = _clean_whisper_text(getattr(seg, "text", ""))
            if not seg_txt:
                continue
            kept_texts.append(seg_txt)
            conf = max(0.0, min(1.0, math.exp(max(-5.0, avg_logprob)) * (1.0 - no_speech_prob)))
            confidences.append(conf)

        final_text = _clean_whisper_text(" ".join(kept_texts))
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        if not final_text:
            return {
                "ok": False,
                "text": "",
                "confidence": 0.0,
                "is_noise": True,
                "stt_ms": elapsed_ms,
            }
        avg_conf = round(float(sum(confidences) / max(1, len(confidences))), 4)
        return {
            "ok": True,
            "text": final_text,
            "confidence": avg_conf,
            "is_noise": False,
            "stt_ms": elapsed_ms,
        }
    except Exception as exc:
        LOG.warning("Local Vietnamese Whisper STT failed: %s", exc)
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": False,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
        }
