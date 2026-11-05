"""Mo-dun sinh am thanh thu nghiem va bien doi am giong (Pitch shift, noise injection, multi-speaker overlay)."""

from __future__ import annotations

import numpy as np


def transform_pcm_by_pitch_factor(
    pcm16: np.ndarray, factor: float = 0.78, sr: int = 16000
) -> np.ndarray:
    """Biến đổi cao độ (Pitch Shift) bảo toàn cấu trúc Formant (vocal-tract envelope).

    factor < 1.0 -> giọng cao hơn (F0 tăng), factor > 1.0 -> giọng trầm/khàn hơn (F0 giảm)
    nhưng vẫn giữ nguyên đặc trưng âm học tuyến thanh quản (formants F1-F4) của người nói.
    """
    if abs(factor - 1.0) < 1e-4:
        return pcm16.copy()

    x = pcm16.astype(np.float32)
    n = x.size
    if n < 512:
        return pcm16.copy()

    # Bước 1: Resample + OLA time-stretch để dịch tần số cơ bản F0 theo factor
    resampled_len = max(400, int(n * factor))
    x_rs = np.interp(
        np.linspace(0.0, 1.0, resampled_len, endpoint=False),
        np.linspace(0.0, 1.0, n, endpoint=False),
        x,
    ).astype(np.float32)

    win_size = 512
    hop_out = 128
    hop_in = max(1, int(round(hop_out * factor)))
    win = np.hanning(win_size).astype(np.float32)
    out_ola = np.zeros(n + win_size * 2, dtype=np.float32)
    wsum = np.zeros(n + win_size * 2, dtype=np.float32)
    pos_in = 0
    pos_out = 0
    while pos_in + win_size <= resampled_len and pos_out + win_size <= out_ola.size:
        out_ola[pos_out : pos_out + win_size] += x_rs[pos_in : pos_in + win_size] * win
        wsum[pos_out : pos_out + win_size] += win**2
        pos_in += hop_in
        pos_out += hop_out
    mask = wsum > 1e-6
    out_ola[mask] /= wsum[mask]
    y_shifted = out_ola[:n]

    # Bước 2: Khôi phục bao hình phổ Formant (Cepstral Liftering Spectral Envelope)
    stft_n = 512
    stft_hop = 128
    stft_win = np.hanning(stft_n).astype(np.float32)
    out = np.zeros(n + stft_n, dtype=np.float32)
    ow = np.zeros(n + stft_n, dtype=np.float32)
    lifter_cut = 48
    nbins = stft_n // 2 + 1
    bins = np.arange(nbins, dtype=np.float32)

    for start in range(0, max(1, n - stft_n), stft_hop):
        f_orig = x[start : start + stft_n]
        f_shft = y_shifted[start : start + stft_n]
        if f_orig.size < stft_n:
            f_orig = np.pad(f_orig, (0, stft_n - f_orig.size))
            f_shft = np.pad(f_shft, (0, stft_n - f_shft.size))

        S_orig = np.fft.rfft(f_orig * stft_win)
        S_shft = np.fft.rfft(f_shft * stft_win)

        log_orig = np.log(np.abs(S_orig) + 1e-6)
        cep_orig = np.fft.irfft(log_orig)
        cep_orig[lifter_cut : stft_n - lifter_cut + 1] = 0.0
        env_orig = np.exp(np.fft.rfft(cep_orig).real)

        log_shft = np.log(np.abs(S_shft) + 1e-6)
        cep_shft = np.fft.irfft(log_shft)
        cep_shft[lifter_cut : stft_n - lifter_cut + 1] = 0.0
        env_shft = np.exp(np.fft.rfft(cep_shft).real)

        fine_shft = np.abs(S_shft) / (env_shft + 1e-6)
        warped_env = env_orig
        S_new = fine_shft * warped_env * np.exp(1j * np.angle(S_shft))
        frame_out = np.fft.irfft(S_new).astype(np.float32) * stft_win
        out[start : start + stft_n] += frame_out
        ow[start : start + stft_n] += stft_win**2

    m2 = ow > 1e-6
    out[m2] /= ow[m2]
    out = out[:n]
    peak = float(np.max(np.abs(out)))
    orig_peak = max(12000.0, float(np.max(np.abs(x))))
    if peak > 100.0:
        out = out * (min(26000.0, orig_peak) / peak)
    return np.clip(out, -32768, 32767).astype(np.int16)


def transform_pcm_to_intruder_voice(pcm16: np.ndarray, sr: int = 16000) -> np.ndarray:
    """Biến đổi tần số giọng nói gốc thành Giọng số 2 (Giọng người lạ - Không được phép)."""
    return transform_pcm_by_pitch_factor(pcm16, factor=0.78, sr=sr)


def synthesize_noisy_fan_voice(pcm16_owner: np.ndarray, sr: int = 16000) -> np.ndarray:
    """Tạo mẫu kiểm thử: Giọng Chủ nhà nói trong môi trường có tiếng quạt trần ù mạnh + tiếng gió nền."""
    rng = np.random.default_rng(42)
    x_owner = pcm16_owner.astype(np.float32)
    peak = float(np.max(np.abs(x_owner))) if x_owner.size > 0 else 0.0
    if peak > 100.0 and peak < 24000.0:
        x_owner = x_owner * (26000.0 / peak)
    n = x_owner.size
    t = np.arange(n, dtype=np.float32) / sr
    # Tiếng động cơ quạt 65Hz + hài âm 130Hz, 195Hz + tiếng gió rào rào
    fan_hum = (
        0.11 * np.sin(2.0 * np.pi * 65.0 * t)
        + 0.07 * np.sin(2.0 * np.pi * 130.0 * t)
        + 0.04 * np.sin(2.0 * np.pi * 195.0 * t)
    )
    wind_noise = rng.normal(0.0, 0.045, size=n).astype(np.float32)
    mixed = x_owner + (fan_hum + wind_noise) * 32768.0
    return np.clip(mixed, -32768, 32767).astype(np.int16)


def synthesize_two_speakers_audio(
    pcm16_owner: np.ndarray, pcm16_intruder: np.ndarray, sr: int = 16000
) -> np.ndarray:
    """Tạo mẫu kiểm thử: 2 người cùng nói trong 1 lượt (Người lạ nói chèn khúc đầu + Chủ nhà Cấp 1 nói chính)."""
    x_own = pcm16_owner.astype(np.float32)
    peak_own = float(np.max(np.abs(x_own))) if x_own.size > 0 else 0.0
    if peak_own > 100.0 and peak_own < 24000.0:
        x_own = x_own * (26000.0 / peak_own)
    pcm16_owner_norm = np.clip(x_own, -32768, 32767).astype(np.int16)

    half = min(pcm16_intruder.size, int(sr * 0.75))
    intro_intruder = (pcm16_intruder[:half].astype(np.float32) * 0.75).astype(np.int16)
    # Khúc giữa có 0.35s nói đè lên nhau, sau đó Chủ nhà nói rõ câu lệnh
    overlap_len = min(int(sr * 0.35), pcm16_owner_norm.size, pcm16_intruder.size - half)
    overlap_part = np.clip(
        pcm16_owner_norm[:overlap_len].astype(np.float32) * 0.95
        + pcm16_intruder[half : half + overlap_len].astype(np.float32) * 0.50,
        -32768,
        32767,
    ).astype(np.int16)
    rest_owner = pcm16_owner_norm[overlap_len:]
    return np.concatenate([intro_intruder, overlap_part, rest_owner])
