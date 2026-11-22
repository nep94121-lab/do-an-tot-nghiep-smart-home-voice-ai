"""Vietnamese speech synthesis (gTTS + PyAV), 6 user personas, and 11 audio degradations.

Caches base TTS and persona-transformed WAVs outside git in the run directory
(default: C:\\Users\\LENOVO\\datn-wt\\agyvoicefix1_20261120\\voice_tests\\audio_cache)
so repeated QA runs are fast and reproducible without committing binary audio.
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import pathlib
import warnings
import wave
from typing import Any

warnings.filterwarnings("ignore", category=FutureWarning, module="librosa")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="numba")

import av
import librosa
import numpy as np
from gtts import gTTS
from scipy import signal

DEFAULT_CACHE_DIR = pathlib.Path(
    os.environ.get(
        "VOICE_QA_CACHE_DIR",
        r"C:\Users\LENOVO\datn-wt\agyvoicefix1_20261120\voice_tests\audio_cache",
    )
)

TARGET_SR = 16000

PERSONAS: tuple[str, ...] = (
    "bac_male",
    "nam_female",
    "trung_adult",
    "elderly",
    "kid_fast",
    "mumbler_guest",
)

DEGRADATIONS: tuple[str, ...] = (
    "clean",
    "white_snr20",
    "white_snr10",
    "white_snr5",
    "babble_snr20",
    "babble_snr10",
    "babble_snr5",
    "reverb_echo",
    "low_gain_m20db",
    "clipping",
    "speed_0.8x",
    "speed_1.2x",
)

_BABBLE_SEED_PHRASES: tuple[str, ...] = (
    "Hôm nay trời nắng nhẹ, mọi người đang nói chuyện trong phòng khách.",
    "Tiếng tivi và tiếng người nói chuyện ở phòng bên cạnh hơi ồn một chút.",
    "Anh ơi pha giúp em ấm trà nóng rồi ra ngoài sân ngồi chơi nhé.",
    "Ngoài đường có tiếng xe máy chạy qua lại khá đông vào buổi chiều.",
)

_BABBLE_BED_CACHE: np.ndarray | None = None


def _ensure_cache_dir(cache_dir: pathlib.Path | None = None) -> pathlib.Path:
    cdir = cache_dir or DEFAULT_CACHE_DIR
    cdir.mkdir(parents=True, exist_ok=True)
    return cdir


def _sha256_key(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()[:24]


def _read_wav_pcm16(path: pathlib.Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    return np.frombuffer(raw, dtype=np.int16).copy()


def _write_wav_pcm16(path: pathlib.Path, pcm16: np.ndarray, sr: int = TARGET_SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.wav")
    arr = np.asarray(pcm16, dtype=np.int16)
    with wave.open(str(tmp), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(arr.tobytes())
    tmp.replace(path)


def pcm16_to_wav_bytes(pcm16: np.ndarray, sr: int = TARGET_SR) -> bytes:
    buf = io.BytesIO()
    arr = np.asarray(pcm16, dtype=np.int16)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(arr.tobytes())
    return buf.getvalue()


def pcm16_to_wav_b64(pcm16: np.ndarray, sr: int = TARGET_SR) -> str:
    return base64.b64encode(pcm16_to_wav_bytes(pcm16, sr=sr)).decode("ascii")


def _float_to_pcm16(x: np.ndarray) -> np.ndarray:
    x_clean = np.nan_to_num(x, nan=0.0, posinf=1.0, neginf=-1.0)
    return np.clip(np.round(x_clean * 32767.0), -32767, 32767).astype(np.int16)


def _pcm16_to_float(pcm16: np.ndarray) -> np.ndarray:
    return np.asarray(pcm16, dtype=np.float32) / 32768.0


def _decode_mp3_bytes_to_pcm16(mp3_bytes: bytes, target_sr: int = TARGET_SR) -> np.ndarray:
    buf = io.BytesIO(mp3_bytes)
    container = av.open(buf, format="mp3")
    resampler = av.AudioResampler(format="s16", layout="mono", rate=target_sr)
    chunks: list[np.ndarray] = []
    for frame in container.decode(audio=0):
        for rf in resampler.resample(frame):
            chunks.append(rf.to_ndarray().reshape(-1))
    container.close()
    if not chunks:
        return np.zeros(int(target_sr * 0.5), dtype=np.int16)
    return np.concatenate(chunks).astype(np.int16)


def synthesize_base_tts(
    text: str,
    *,
    lang: str = "vi",
    slow: bool = False,
    cache_dir: pathlib.Path | None = None,
) -> np.ndarray:
    """Synthesize clean 16kHz mono PCM16 via gTTS + PyAV, cached by SHA-256."""
    cdir = _ensure_cache_dir(cache_dir)
    key = _sha256_key("gtts_v1", lang, int(bool(slow)), text.strip())
    wav_path = cdir / f"base_{lang}_{key}.wav"
    if wav_path.is_file() and wav_path.stat().st_size > 44:
        return _read_wav_pcm16(wav_path)

    buf = io.BytesIO()
    tts = gTTS(text=text.strip(), lang=lang, slow=slow, timeout=15)
    tts.write_to_fp(buf)
    pcm = _decode_mp3_bytes_to_pcm16(buf.getvalue(), target_sr=TARGET_SR)
    # Pad 120ms silence at start/end so Whisper VAD does not clip edges
    pad = np.zeros(int(TARGET_SR * 0.12), dtype=np.int16)
    pcm = np.concatenate([pad, pcm, pad])
    _write_wav_pcm16(wav_path, pcm, sr=TARGET_SR)
    return pcm


def _resample_speed(x: np.ndarray, speed: float) -> np.ndarray:
    """Change playback speed (tempo + slight formant shift) cleanly via librosa time_stretch."""
    if abs(speed - 1.0) < 1e-3 or x.size < 512:
        return x
    try:
        return librosa.effects.time_stretch(y=x.astype(np.float32), rate=float(speed))
    except Exception:
        new_len = max(256, int(round(x.size / float(speed))))
        return signal.resample(x, new_len).astype(np.float32)


def _apply_lowpass(x: np.ndarray, cutoff_hz: float = 2400.0, sr: int = TARGET_SR) -> np.ndarray:
    sos = signal.butter(4, cutoff_hz / (0.5 * sr), btype="lowpass", output="sos")
    return signal.sosfilt(sos, x).astype(np.float32)


def apply_persona_transform(
    pcm16: np.ndarray,
    persona: str,
    sr: int = TARGET_SR,
) -> np.ndarray:
    """Transform base TTS into one of 6 diverse Vietnamese speaker personas."""
    if persona in ("", "neutral", "clean"):
        return pcm16.copy()
    x = _pcm16_to_float(pcm16)
    if x.size < 512:
        return pcm16.copy()

    if persona == "bac_male":
        y = librosa.effects.pitch_shift(y=x, sr=sr, n_steps=-3.0)
    elif persona == "nam_female":
        y = librosa.effects.pitch_shift(y=x, sr=sr, n_steps=1.0)
    elif persona == "trung_adult":
        y = librosa.effects.pitch_shift(y=x, sr=sr, n_steps=-1.5)
        y = _resample_speed(y, 0.95)
    elif persona == "elderly":
        y = librosa.effects.pitch_shift(y=x, sr=sr, n_steps=-2.0)
        y = _resample_speed(y, 0.85)
    elif persona == "kid_fast":
        y = librosa.effects.pitch_shift(y=x, sr=sr, n_steps=3.5)
        y = _resample_speed(y, 1.15)
    elif persona == "mumbler_guest":
        y = _apply_lowpass(x, cutoff_hz=2400.0, sr=sr) * 0.45
    else:
        y = x

    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 0.92:
        y = y * (0.90 / peak)
    return _float_to_pcm16(y)


def synthesize_persona_speech(
    text: str,
    *,
    persona: str = "bac_male",
    lang: str = "vi",
    cache_dir: pathlib.Path | None = None,
) -> np.ndarray:
    """Synthesize and cache persona-transformed 16kHz mono PCM16 speech."""
    cdir = _ensure_cache_dir(cache_dir)
    use_slow = (persona == "elderly" and lang == "vi")
    key = _sha256_key("persona_v1", lang, persona, int(use_slow), text.strip())
    wav_path = cdir / f"persona_{persona}_{lang}_{key}.wav"
    if wav_path.is_file() and wav_path.stat().st_size > 44:
        return _read_wav_pcm16(wav_path)

    base = synthesize_base_tts(text, lang=lang, slow=use_slow, cache_dir=cdir)
    if persona == "elderly" and use_slow:
        # gTTS slow=True already slows pace; only apply gentle pitch shift -2.0 semitones
        x = _pcm16_to_float(base)
        y = librosa.effects.pitch_shift(y=x, sr=TARGET_SR, n_steps=-2.0)
        peak = float(np.max(np.abs(y))) if y.size else 0.0
        if peak > 0.92:
            y = y * (0.90 / peak)
        out = _float_to_pcm16(y)
    else:
        out = apply_persona_transform(base, persona=persona, sr=TARGET_SR)

    _write_wav_pcm16(wav_path, out, sr=TARGET_SR)
    return out


def _get_babble_bed(cache_dir: pathlib.Path | None = None) -> np.ndarray:
    """Build and cache a continuous multi-speaker Vietnamese babble noise bed."""
    global _BABBLE_BED_CACHE
    if _BABBLE_BED_CACHE is not None:
        return _BABBLE_BED_CACHE
    cdir = _ensure_cache_dir(cache_dir)
    bed_path = cdir / "babble_bed_v1.wav"
    if bed_path.is_file() and bed_path.stat().st_size > 44:
        _BABBLE_BED_CACHE = _pcm16_to_float(_read_wav_pcm16(bed_path))
        return _BABBLE_BED_CACHE

    tracks: list[np.ndarray] = []
    shifts = (-3.0, 1.5, -1.0, 2.5)
    for phrase, st in zip(_BABBLE_SEED_PHRASES, shifts):
        base = synthesize_base_tts(phrase, lang="vi", slow=False, cache_dir=cdir)
        x = _pcm16_to_float(base)
        y = librosa.effects.pitch_shift(y=x, sr=TARGET_SR, n_steps=st)
        tracks.append(y)

    target_len = TARGET_SR * 10  # 10 seconds continuous bed
    mix = np.zeros(target_len, dtype=np.float32)
    offsets = (0, 17000, 39000, 61000)
    for tr, off in zip(tracks, offsets):
        if tr.size == 0:
            continue
        tiled = np.tile(tr, int(np.ceil((target_len + off) / tr.size)) + 1)
        mix += tiled[off : off + target_len] * 0.35

    rms = float(np.sqrt(np.mean(mix * mix) + 1e-12))
    if rms > 1e-6:
        mix = mix * (0.18 / rms)
    mix = np.clip(mix, -0.95, 0.95)
    _write_wav_pcm16(bed_path, _float_to_pcm16(mix), sr=TARGET_SR)
    _BABBLE_BED_CACHE = mix
    return _BABBLE_BED_CACHE


def _mix_at_snr(sig: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    """Add noise to signal at exact active-speech SNR in dB."""
    # Compute active signal RMS (above -30 dB of peak) so silence padding doesn't distort SNR
    abs_s = np.abs(sig)
    peak = float(np.max(abs_s)) if sig.size else 0.0
    active = sig[abs_s >= max(peak * 0.05, 1e-4)]
    sig_pow = float(np.mean(active * active)) if active.size > 64 else float(np.mean(sig * sig) + 1e-12)
    noise_pow = float(np.mean(noise * noise) + 1e-12)
    target_noise_pow = sig_pow / (10.0 ** (snr_db / 10.0))
    scale = float(np.sqrt(target_noise_pow / noise_pow))
    mixed = sig + noise * scale
    mx = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    if mx > 0.98:
        mixed = mixed * (0.98 / mx)
    return mixed.astype(np.float32)


def _apply_room_reverb_echo(x: np.ndarray, sr: int = TARGET_SR) -> np.ndarray:
    """Synthetic multi-tap room impulse response (RT60 ~ 0.35s) + early reflection echo."""
    ir_len = int(sr * 0.42)
    t = np.arange(ir_len, dtype=np.float32) / float(sr)
    rng = np.random.default_rng(20261120)
    # Exponentially decaying diffuse tail (RT60 ~ 0.35s => tau = 0.35 / 6.91 = 0.0506s)
    decay = np.exp(-t / 0.052)
    ir = rng.standard_normal(ir_len).astype(np.float32) * decay * 0.08
    # Direct path + distinct room early reflections
    ir[0] = 1.0
    for delay_ms, gain in ((22, 0.42), (47, 0.31), (83, 0.22), (125, 0.14), (175, 0.08)):
        idx = int(sr * delay_ms / 1000.0)
        if idx < ir_len:
            ir[idx] += gain
    ir = ir / np.sqrt(np.sum(ir * ir) + 1e-12)
    y = signal.fftconvolve(x, ir, mode="full")[: x.size + int(sr * 0.20)]
    mx = float(np.max(np.abs(y))) if y.size else 0.0
    if mx > 0.95:
        y = y * (0.95 / mx)
    return y.astype(np.float32)


def apply_degradation(
    pcm16: np.ndarray,
    degradation: str,
    *,
    seed: int = 42,
    sr: int = TARGET_SR,
    cache_dir: pathlib.Path | None = None,
) -> np.ndarray:
    """Apply one of the 12 required audio conditions ('clean' + 11 degradations)."""
    deg = str(degradation or "clean").strip()
    if deg == "clean":
        return pcm16.copy()

    x = _pcm16_to_float(pcm16)
    rng = np.random.default_rng(seed)

    if deg in ("white_snr20", "white_snr10", "white_snr5"):
        snr_db = float(deg.split("snr")[1])
        noise = rng.standard_normal(x.size).astype(np.float32)
        y = _mix_at_snr(x, noise, snr_db=snr_db)
        return _float_to_pcm16(y)

    if deg in ("babble_snr20", "babble_snr10", "babble_snr5"):
        snr_db = float(deg.split("snr")[1])
        bed = _get_babble_bed(cache_dir=cache_dir)
        start = int(rng.integers(0, max(1, bed.size - 1)))
        tiled = np.tile(bed, int(np.ceil((x.size + start) / bed.size)) + 1)
        babble = tiled[start : start + x.size].astype(np.float32)
        y = _mix_at_snr(x, babble, snr_db=snr_db)
        return _float_to_pcm16(y)

    if deg == "reverb_echo":
        y = _apply_room_reverb_echo(x, sr=sr)
        return _float_to_pcm16(y)

    if deg == "low_gain_m20db":
        # -20 dB = amplitude factor 0.10
        y = x * 0.10
        return _float_to_pcm16(y)

    if deg == "clipping":
        # Hard clipping at 3.5x overdrive
        y = np.clip(x * 3.5, -1.0, 1.0)
        return _float_to_pcm16(y)

    if deg == "speed_0.8x":
        y = _resample_speed(x, 0.8)
        return _float_to_pcm16(y)

    if deg == "speed_1.2x":
        y = _resample_speed(x, 1.2)
        return _float_to_pcm16(y)

    raise ValueError(f"Unknown audio degradation: {deg!r}")


def synth_pure_white_noise(duration_sec: float = 2.0, seed: int = 101, rms: float = 0.18) -> np.ndarray:
    """Pure stationary broadband white noise (should NEVER trigger a device action)."""
    rng = np.random.default_rng(seed)
    n = int(TARGET_SR * duration_sec)
    x = rng.standard_normal(n).astype(np.float32)
    cur_rms = float(np.sqrt(np.mean(x * x) + 1e-12))
    x = np.clip(x * (rms / cur_rms), -0.95, 0.95)
    return _float_to_pcm16(x)


def synth_babble_only(
    duration_sec: float = 2.5,
    seed: int = 202,
    cache_dir: pathlib.Path | None = None,
) -> np.ndarray:
    """Overlapping low-intelligibility room babble with white floor (NO command intent)."""
    rng = np.random.default_rng(seed)
    bed = _get_babble_bed(cache_dir=cache_dir)
    n = int(TARGET_SR * duration_sec)
    start = int(rng.integers(0, max(1, bed.size - 1)))
    tiled = np.tile(bed, int(np.ceil((n + start) / bed.size)) + 1)
    seg = tiled[start : start + n].copy()
    # Mix reversed babble + broadband room noise so no intelligible smart-home command exists
    seg = 0.45 * seg + 0.45 * seg[::-1] + rng.standard_normal(n).astype(np.float32) * 0.08
    seg = _apply_lowpass(seg, cutoff_hz=1800.0, sr=TARGET_SR) * 0.55
    return _float_to_pcm16(np.clip(seg, -0.95, 0.95))


def synth_foreign_audio(
    text: str,
    *,
    lang: str = "en",
    persona: str = "neutral",
    cache_dir: pathlib.Path | None = None,
) -> np.ndarray:
    """Synthesize non-Vietnamese speech (English, French, Korean, Spanish, German)."""
    return synthesize_persona_speech(text, persona=persona, lang=lang, cache_dir=cache_dir)


async def _edge_tts_to_mp3_bytes(text: str, *, voice: str, rate: str, pitch: str) -> bytes:
    import edge_tts

    comm = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    chunks: list[bytes] = []
    async for chunk in comm.stream():
        if chunk.get("type") == "audio" and chunk.get("data"):
            chunks.append(chunk["data"])
    return b"".join(chunks)


def _run_async_coro(coro: Any) -> Any:
    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


def synthesize_edge_tts_speech(
    text: str,
    *,
    voice: str = "vi-VN-HoaiMyNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz",
    cache_dir: pathlib.Path | None = None,
) -> np.ndarray:
    """Synthesize neural speech via edge-tts + PyAV (16kHz mono PCM16), cached to disk.

    Falls back cleanly to synthesize_base_tts if edge-tts network synthesis fails.
    """
    cdir = _ensure_cache_dir(cache_dir)
    clean_txt = text.strip()
    safe_voice = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(voice))
    key = _sha256_key("edge_tts_v1", voice, rate, pitch, clean_txt)
    wav_path = cdir / f"edge_{safe_voice}_{key}.wav"
    if wav_path.is_file() and wav_path.stat().st_size > 44:
        return _read_wav_pcm16(wav_path)

    try:
        mp3_bytes = _run_async_coro(
            _edge_tts_to_mp3_bytes(clean_txt, voice=voice, rate=rate, pitch=pitch)
        )
        if not mp3_bytes or len(mp3_bytes) < 64:
            raise RuntimeError("edge-tts returned empty audio")
        pcm = _decode_mp3_bytes_to_pcm16(mp3_bytes, target_sr=TARGET_SR)
        pad = np.zeros(int(TARGET_SR * 0.12), dtype=np.int16)
        pcm = np.concatenate([pad, pcm, pad])
        _write_wav_pcm16(wav_path, pcm, sr=TARGET_SR)
        return pcm
    except Exception:
        fallback_lang = "en" if str(voice).lower().startswith("en-") else "vi"
        fallback_slow = str(rate).strip().startswith("-")
        return synthesize_base_tts(clean_txt, lang=fallback_lang, slow=fallback_slow, cache_dir=cdir)
