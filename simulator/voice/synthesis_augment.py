"""Mo-dun sinh am thanh thu nghiem va bien doi am giong (Pitch shift, noise injection, multi-speaker overlay)."""

from __future__ import annotations

import numpy as np

def transform_pcm_by_pitch_factor(pcm16: np.ndarray, factor: float = 0.78, sr: int = 16000) -> np.ndarray:
    """Biến đổi cao độ (Pitch Shift) đoạn âm thanh theo hệ số `factor` (factor < 1.0 -> giọng cao hơn, factor > 1.0 -> giọng trầm hơn)."""
    x = pcm16.astype(np.float32)
    n = x.size
    resampled_len = max(400, int(n * factor))
    x_down = np.interp(
        np.linspace(0.0, 1.0, resampled_len, endpoint=False),
        np.linspace(0.0, 1.0, n, endpoint=False),
        x,
    )
    if factor > 1.0:
        peak = float(np.max(np.abs(x_down)))
        if peak > 100:
            x_down = x_down * (26000.0 / peak)
        return np.clip(x_down, -32768, 32767).astype(np.int16)
    win_size = 400
    hop_in = max(1, int(win_size * factor))
    hop_out = win_size
    out = np.zeros(int(resampled_len / factor) + win_size * 2, dtype=np.float32)
    win = np.hanning(win_size).astype(np.float32)
    pos_in = 0
    pos_out = 0
    while pos_in + win_size < resampled_len and pos_out + win_size < out.size:
        out[pos_out : pos_out + win_size] += x_down[pos_in : pos_in + win_size] * win
        pos_in += hop_in
        pos_out += hop_out
    if out.size < n:
        out = np.pad(out, (0, n - out.size))
    out = out[:n]
    peak = float(np.max(np.abs(out)))
    if peak > 100:
        out = out * (26000.0 / peak)
    return np.clip(out, -32768, 32767).astype(np.int16)


def transform_pcm_to_intruder_voice(pcm16: np.ndarray, sr: int = 16000) -> np.ndarray:
    """Biến đổi tần số giọng nói gốc thành Giọng số 2 (Giọng người lạ - Không được phép)."""
    return transform_pcm_by_pitch_factor(pcm16, factor=0.78, sr=sr)


def synthesize_noisy_fan_voice(pcm16_owner: np.ndarray, sr: int = 16000) -> np.ndarray:
    """Tạo mẫu kiểm thử: Giọng Chủ nhà nói trong môi trường có tiếng quạt trần ù mạnh + tiếng gió nền."""
    rng = np.random.default_rng(42)
    n = pcm16_owner.size
    t = np.arange(n, dtype=np.float32) / sr
    # Tiếng động cơ quạt 60Hz + hài âm 120Hz, 180Hz + tiếng gió rào rào
    fan_hum = (
        0.11 * np.sin(2.0 * np.pi * 65.0 * t)
        + 0.07 * np.sin(2.0 * np.pi * 130.0 * t)
        + 0.04 * np.sin(2.0 * np.pi * 195.0 * t)
    )
    wind_noise = rng.normal(0.0, 0.045, size=n).astype(np.float32)
    mixed = pcm16_owner.astype(np.float32) + (fan_hum + wind_noise) * 32768.0
    return np.clip(mixed, -32768, 32767).astype(np.int16)


def synthesize_two_speakers_audio(
    pcm16_owner: np.ndarray, pcm16_intruder: np.ndarray, sr: int = 16000
) -> np.ndarray:
    """Tạo mẫu kiểm thử: 2 người cùng nói trong 1 lượt (Người lạ nói chèn khúc đầu + Chủ nhà Cấp 1 nói chính)."""
    half = min(pcm16_intruder.size, int(sr * 0.75))
    intro_intruder = (pcm16_intruder[:half].astype(np.float32) * 0.75).astype(np.int16)
    # Khúc giữa có 0.35s nói đè lên nhau, sau đó Chủ nhà nói rõ câu lệnh
    overlap_len = min(int(sr * 0.35), pcm16_owner.size, pcm16_intruder.size - half)
    overlap_part = np.clip(
        pcm16_owner[:overlap_len].astype(np.float32) * 0.95
        + pcm16_intruder[half : half + overlap_len].astype(np.float32) * 0.50,
        -32768,
        32767,
    ).astype(np.int16)
    rest_owner = pcm16_owner[overlap_len:]
    return np.concatenate([intro_intruder, overlap_part, rest_owner])

