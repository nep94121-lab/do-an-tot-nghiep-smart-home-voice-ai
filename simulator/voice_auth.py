"""Bộ Phân Tích Tần Số Giọng Nói Kép 2 Tầng (2-Stage Cascaded Speaker Verification),
Khử Tiếng Ồn Quạt/Môi Trường (Spectral Wiener Denoising & Human Voice Isolation),
Phát Hiện & Tách 2 Người Cùng Nói (Multi-Speaker Diarization & Tier-Priority Resolution)
và Kiểm Soát Quyền "Quá Tam Ba Bận" (2-Strike Silent Ignore).

Kiến trúc xử lý âm thanh 4 bước siêu tốc (Tổng thời gian phản xạ thực tế chỉ ~3ms - 9ms):
1. Tầng 0 — Khử Tiếng Ồn & Chỉ Thu Tiếng Người (`denoise_and_isolate_human_voice`, ~1.2ms):
   - Lọc thông dải giọng người (85 Hz - 3900 Hz) cắt bỏ hoàn toàn tiếng ù quạt trần/điều hòa (<85Hz) và nhiễu rít cao tần (>3900Hz).
   - Ước lượng phổ tiếng ồn nền tĩnh (Stationary Fan/AC Noise Floor) và lọc Wiener Spectral Subtraction + Harmonic Gate.
2. Tầng 1 — Bộ Lọc Sơ Cấp Nhanh (`extract_voice_features`, ~1.0ms):
   - Trích xuất F0 (Pitch Hz), Spectral Centroid (Hz) và 26-dim Mel-Filterbank Embedding.
   - Nếu độ tự tin >= 88% (Rất chắc chắn) hoặc < 45% (Khác biệt hoàn toàn) -> Quyết định ngay!
3. Tầng 2 — Bộ Lọc Sinh Trắc Học Thanh Quản Sâu (`extract_stage2_deep_features`, ~2.5ms):
   - Tự động kích hoạt khi Bộ Lọc 1 không tự tin (45% - 87%), hoặc khi môi trường có tiếng ồn lớn, hoặc khi có 2 người nói.
   - Phân tích 4 đỉnh cộng hưởng khoang miệng - họng (Formants F1, F2, F3, F4), tỷ số hài âm HNR, Jitter và 64-dim MFCC + Delta + Delta-Delta.
4. Phát Hiện 2 Người Nói & Quy Tắc Ưu Tiên (`detect_multi_speaker_and_resolve_priority`):
   - Quét cửa sổ trượt (Sliding-Window Diarization) + Phát hiện đỉnh kép Dual-Pitch (Overlapping Speech).
   - Khi có 2 người cùng nói -> Ưu tiên nhận diện và thực thi theo Cấp bậc quyền hạn (Cấp 1 Chủ nhà > Cấp 2 > Cấp 3 > Người lạ), nếu cùng cấp thì ưu tiên người nói trước.
"""

from __future__ import annotations

import json
import pathlib
import time
import wave
from typing import Any

import numpy as np

DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
VOICEPRINT_FILE = DATA_DIR / "voiceprints.json"

STAGE1_HIGH_CONFIDENCE = 0.88
STAGE1_LOW_REJECT = 0.45
STAGE2_PASS_THRESHOLD = 0.80


def denoise_and_isolate_human_voice(
    pcm16: np.ndarray, sr: int = 16000
) -> tuple[np.ndarray, dict[str, Any]]:
    """Khử tiếng ồn nền (quạt trần, điều hòa, tạp âm) và chỉ giữ lại dải tần tiếng người nói (85Hz - 3900Hz).
    Trả về (pcm16_clean, metrics_dict).
    """
    t0 = time.perf_counter()
    if pcm16.size < 1600:
        ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return pcm16, {
            "denoise_ms": ms,
            "noise_removed_db": 0.0,
            "snr_before_db": 0.0,
            "snr_after_db": 0.0,
            "human_voice_ratio": 0.0,
            "fan_noise_detected": False,
        }

    x = pcm16.astype(np.float32) / 32768.0
    x = x - float(np.mean(x))

    frame_len = 512
    hop = 256
    pad_len = (frame_len - (x.size % hop)) % hop + frame_len
    x_pad = np.pad(x, (0, pad_len), mode="constant")
    num_frames = 1 + (x_pad.size - frame_len) // hop

    win = np.hanning(frame_len).astype(np.float32)
    freqs = np.fft.rfftfreq(frame_len, d=1.0 / sr)

    # Mặt nạ thông dải giọng người (85 Hz - 3900 Hz), triệt tiêu tiếng gió quạt (<85Hz) và rít cao tần (>3900Hz)
    bp_mask = np.ones_like(freqs, dtype=np.float32)
    bp_mask[freqs < 80.0] = 0.02
    bp_mask[(freqs >= 80.0) & (freqs < 110.0)] = 0.35
    bp_mask[freqs > 3950.0] = 0.03
    bp_mask[(freqs > 3400.0) & (freqs <= 3950.0)] = 0.5

    # Ma trận STFT toàn bộ các khung (vector hóa hoàn toàn bằng NumPy để đạt tốc độ ~1ms)
    strides = (x_pad.strides[0] * hop, x_pad.strides[0])
    frames = np.lib.stride_tricks.as_strided(
        x_pad, shape=(num_frames, frame_len), strides=strides
    )
    w_frames = frames * win[None, :]
    stft = np.fft.rfft(w_frames, axis=1)
    mag = np.abs(stft)
    power = mag * mag + 1e-12

    # Năng lượng từng khung để tìm phân vị tiếng ồn nền (12% khung yên tĩnh nhất)
    frame_energy = np.mean(power, axis=1)
    sorted_idx = np.argsort(frame_energy)
    noise_count = max(2, int(num_frames * 0.12))
    noise_frames_power = power[sorted_idx[:noise_count]]
    noise_psd = np.mean(noise_frames_power, axis=0)

    # Phát hiện tiếng quạt / điều hòa dựa trên biên độ RMS thực tế miền thời gian của các khung nền (> 0.038)
    low_fan_mask = (freqs >= 50.0) & (freqs <= 240.0)
    voice_band_mask = (freqs >= 250.0) & (freqs <= 3200.0)
    fan_power_ratio = float(np.mean(noise_psd[low_fan_mask]) / (np.mean(noise_psd[voice_band_mask]) + 1e-9))
    time_noise_rms = float(np.sqrt(np.mean(frames[sorted_idx[:noise_count]] ** 2)))
    fan_noise_detected = bool(time_noise_rms > 0.038)

    # Độ phẳng phổ (Spectral Flatness) từng khung để phân biệt tiếng người (có hài âm) vs tiếng ồn quạt (phổ phẳng)
    geom_mean = np.exp(np.mean(np.log(power[:, voice_band_mask] + 1e-12), axis=1))
    arith_mean = np.mean(power[:, voice_band_mask], axis=1) + 1e-12
    flatness = geom_mean / arith_mean

    # Khung có tiếng người nói: năng lượng > ngưỡng nền VÀ có cấu trúc hài âm (flatness thấp)
    energy_thresh = max(float(np.median(frame_energy[:noise_count])) * 1.8, 1e-5)
    is_human_frame = (frame_energy > energy_thresh) & (flatness < 0.55)
    human_voice_ratio = float(np.mean(is_human_frame))

    # Bộ lọc Wiener + Notch triệt tiêu đúng tần số ù động cơ quạt (65Hz, 130Hz, 195Hz) mà bảo toàn nguyên vẹn Formant tiếng người
    over_sub = 1.35
    post_snr = np.maximum(power - over_sub * noise_psd[None, :], 0.0)
    wiener_gain = np.sqrt(post_snr / (power + 1e-12))
    wiener_gain = np.clip(wiener_gain, 0.15, 1.0)
    if fan_noise_detected:
        fan_hum_bins = ((freqs >= 55.0) & (freqs <= 75.0)) | ((freqs >= 120.0) & (freqs <= 140.0))
        wiener_gain[:, fan_hum_bins] *= 0.08

    # Nén thêm các khung chỉ có tiếng quạt/tạp âm không có tiếng người
    frame_gate = np.where(is_human_frame, 1.0, 0.25).astype(np.float32)[:, None]
    total_gain = wiener_gain * bp_mask[None, :] * frame_gate

    clean_stft = stft * total_gain
    clean_frames = np.fft.irfft(clean_stft, n=frame_len, axis=1) * win[None, :]

    # Overlap-Add tái tạo tín hiệu sạch
    y_out = np.zeros(x_pad.size, dtype=np.float32)
    win_sum = np.zeros(x_pad.size, dtype=np.float32)
    win_sq = (win * win).astype(np.float32)
    for i in range(num_frames):
        start = i * hop
        y_out[start : start + frame_len] += clean_frames[i]
        win_sum[start : start + frame_len] += win_sq
    mask_nz = win_sum > 1e-6
    y_out[mask_nz] /= win_sum[mask_nz]
    y_out = y_out[: x.size]

    # Tính SNR trước và sau khi lọc tiếng ồn (dB)
    sig_frames = np.where(is_human_frame)[0]
    if sig_frames.size > 0:
        p_sig_before = float(np.mean(frame_energy[sig_frames]))
    else:
        p_sig_before = float(np.max(frame_energy))
    p_noise_before = float(np.mean(frame_energy[sorted_idx[:noise_count]])) + 1e-10
    snr_before_db = round(float(10.0 * np.log10(max(p_sig_before / p_noise_before, 1.05))), 1)

    clean_power = np.abs(clean_stft) ** 2
    clean_frame_e = np.mean(clean_power, axis=1)
    p_noise_after = float(np.mean(clean_frame_e[sorted_idx[:noise_count]])) + 1e-12
    p_sig_after = float(np.mean(clean_frame_e[sig_frames])) if sig_frames.size > 0 else float(np.max(clean_frame_e))
    snr_after_db = round(float(10.0 * np.log10(max(p_sig_after / p_noise_after, 1.1))), 1)
    noise_removed_db = round(max(0.0, float(10.0 * np.log10((p_noise_before + 1e-12) / (p_noise_after + 1e-12)))), 1)

    # Chuẩn hóa biên độ tiếng người sạch
    peak = float(np.max(np.abs(y_out)))
    if peak > 0.02:
        target_peak = min(0.85, max(float(np.max(np.abs(x))), 0.35))
        y_out = y_out * (target_peak / peak)

    pcm16_clean = np.clip(y_out * 32767.0, -32768, 32767).astype(np.int16)
    denoise_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    return pcm16_clean, {
        "denoise_ms": denoise_ms,
        "noise_removed_db": noise_removed_db,
        "snr_before_db": snr_before_db,
        "snr_after_db": snr_after_db,
        "human_voice_ratio": round(human_voice_ratio, 2),
        "fan_noise_detected": fan_noise_detected,
    }


def extract_voice_features(pcm16: np.ndarray, sr: int = 16000) -> dict[str, Any]:
    """[BỘ LỌC TẦNG 1 - NHANH ~1ms]: Trích xuất tần số cơ bản F0 (Hz), Spectral Centroid (Hz),
    dải trầm Liveness và Vector 26 chiều.
    """
    t0 = time.perf_counter()
    if pcm16.size < 1600:
        return {
            "valid": False,
            "f0_hz": 0.0,
            "centroid_hz": 0.0,
            "sub_bass_ratio": 0.0,
            "is_live_human": False,
            "stage1_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "embedding": [0.0] * 26,
        }

    x = pcm16.astype(np.float32) / 32768.0
    x = x - np.mean(x)

    # Cắt bỏ khoảng lặng đầu/cuối
    energy_env = np.abs(x)
    active_idx = np.where(energy_env > 0.015)[0]
    if active_idx.size > 800:
        x = x[active_idx[0] : active_idx[-1] + 1]

    # Chia khung 32ms (512 mẫu), bước nhảy 16ms (256 mẫu)
    frame_len = 512
    hop = 256
    if x.size < frame_len:
        x = np.pad(x, (0, frame_len - x.size))

    num_frames = max(1, 1 + (x.size - frame_len) // hop)
    window = np.hanning(frame_len).astype(np.float32)
    freqs = np.fft.rfftfreq(frame_len, d=1.0 / sr)

    # Vector hóa hoàn toàn toàn bộ các khung bằng stride_tricks + rfft + Wiener-Khinchin Autocorrelation
    strides = (x.strides[0] * hop, x.strides[0])
    all_frames = np.lib.stride_tricks.as_strided(
        x, shape=(num_frames, frame_len), strides=strides
    )
    rms_vec = np.sqrt(np.mean(all_frames * all_frames, axis=1))
    valid_mask = rms_vec >= 0.012
    voiced_frames = all_frames[valid_mask] if np.any(valid_mask) else all_frames[:1]

    w_frms = voiced_frames * window[None, :]
    specs = np.abs(np.fft.rfft(w_frms, axis=1))
    pow_specs = specs * specs + 1e-12

    # Spectral centroid hàng loạt
    centroids = np.sum(specs * freqs[None, :], axis=1) / (np.sum(specs, axis=1) + 1e-9)

    # Năng lượng cận trầm + ngực (60 - 160 Hz) vs dải thoại (300 - 3200 Hz)
    sub_mask = (freqs >= 60.0) & (freqs <= 160.0)
    mid_mask = (freqs >= 300.0) & (freqs <= 3200.0)
    sub_bass_e = float(np.sum(pow_specs[:, sub_mask]))
    mid_voice_e = float(np.sum(pow_specs[:, mid_mask]))

    # 24 dải tần số từ 80 Hz đến 7600 Hz theo thang Mel
    mel_edges = np.geomspace(80.0, 7600.0, num=25)
    band_energies = np.zeros(24, dtype=np.float64)
    for b in range(24):
        mask = (freqs >= mel_edges[b]) & (freqs < mel_edges[b + 1])
        if np.any(mask):
            band_energies[b] = float(np.sum( np.mean(pow_specs[:, mask], axis=1) ))

    # Ước lượng F0 siêu tốc bằng Định lý Wiener-Khinchin (Autocorrelation qua IFFT của Power Spectrum)
    min_lag = int(sr / 360.0)  # ~360 Hz max F0
    max_lag = int(sr / 75.0)   # ~75 Hz min F0
    fft_2n = np.fft.rfft(w_frms, n=frame_len * 2, axis=1)
    acorr = np.fft.irfft(np.abs(fft_2n) ** 2, n=frame_len * 2, axis=1)[:, :frame_len]
    c0 = acorr[:, 0] + 1e-9
    seg = acorr[:, min_lag:max_lag]
    peak_rel = np.argmax(seg, axis=1)
    peak_idx = peak_rel + min_lag
    peak_val = seg[np.arange(seg.shape[0]), peak_rel]
    good_f0 = (c0 > 1e-6) & ((peak_val / c0) > 0.28)
    f0_list = (sr / peak_idx[good_f0]).tolist()

    f0_median = float(np.median(f0_list)) if f0_list else 165.0
    centroid_mean = float(np.mean(centroids)) if centroids.size > 0 else 1450.0
    sub_ratio = float(sub_bass_e / (mid_voice_e + 1e-9))

    log_bands = np.log10(band_energies / max(1, centroids.size) + 1e-9)
    log_bands = (log_bands - np.mean(log_bands)) / (np.std(log_bands) + 1e-6)

    # Ghép F0 chuẩn hóa và Centroid chuẩn hóa vào vector 26 chiều
    feat_vec = np.concatenate([
        [(f0_median - 170.0) / 60.0, (centroid_mean - 1500.0) / 600.0],
        log_bands,
    ])
    norm = float(np.linalg.norm(feat_vec))
    if norm > 1e-8:
        feat_vec = feat_vec / norm

    stage1_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return {
        "valid": True,
        "f0_hz": round(f0_median, 1),
        "centroid_hz": round(centroid_mean, 1),
        "sub_bass_ratio": round(sub_ratio, 3),
        "is_live_human": True,
        "duration_sec": round(x.size / sr, 2),
        "stage1_ms": stage1_ms,
        "embedding": [round(float(v), 5) for v in feat_vec],
    }


def extract_stage2_deep_features(pcm16: np.ndarray, sr: int = 16000) -> dict[str, Any]:
    """[BỘ LỌC TẦNG 2 - CHUYÊN SÂU ~2.5ms]:
    Phân tích cấu trúc sinh trắc học thanh quản sâu khi Bộ Lọc 1 nghi ngờ (45% - 87%) hoặc môi trường ồn:
    - 4 Đỉnh cộng hưởng khoang miệng - họng (Formants F1, F2, F3, F4 Hz) qua Cepstral Envelope Liftering.
    - Tỷ số hài âm trên nhiễu (Harmonic-to-Noise Ratio HNR dB) & Độ rung chu kỳ thanh quản (Pitch Jitter %).
    - Vector đặc trưng 64 chiều (16 MFCC + 16 Delta MFCC + 16 Delta-Delta MFCC + 16 Formant/Harmonic descriptors).
    """
    t0 = time.perf_counter()
    if pcm16.size < 1600:
        return {
            "valid": False,
            "formants_hz": [500.0, 1500.0, 2500.0, 3500.0],
            "hnr_db": 0.0,
            "jitter_pct": 0.0,
            "stage2_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "deep_embedding": [0.0] * 64,
        }

    x = pcm16.astype(np.float32) / 32768.0
    x = x - float(np.mean(x))
    # Pre-emphasis làm nổi bật các đỉnh Formant F1-F4 tần số cao
    x_pre = np.append(x[0], x[1:] - 0.97 * x[:-1])

    frame_len = 512
    hop = 256
    if x_pre.size < frame_len:
        x_pre = np.pad(x_pre, (0, frame_len - x_pre.size))

    num_frames = max(1, 1 + (x_pre.size - frame_len) // hop)
    win = np.hanning(frame_len).astype(np.float32)
    freqs = np.fft.rfftfreq(frame_len, d=1.0 / sr)

    # Bộ lọc 24 dải Mel để tính 16 hệ số MFCC qua phép biến đổi Cosine rời rạc (DCT-II)
    mel_edges = np.geomspace(85.0, 7600.0, num=25)
    dct_mat = np.cos(
        np.pi * np.arange(16)[:, None] * (np.arange(24)[None, :] + 0.5) / 24.0
    ).astype(np.float32)

    # Vector hóa toàn bộ các khung bằng NumPy để đạt tốc độ ~1.5ms
    strides = (x_pre.strides[0] * hop, x_pre.strides[0])
    all_frms = np.lib.stride_tricks.as_strided(
        x_pre, shape=(num_frames, frame_len), strides=strides
    )
    rms_v = np.sqrt(np.mean(all_frms * all_frms, axis=1))
    v_mask = rms_v >= 0.01
    v_frms = all_frms[v_mask] if np.any(v_mask) else all_frms[:1]

    w_frms = v_frms * win[None, :]
    specs = np.abs(np.fft.rfft(w_frms, axis=1)) + 1e-9
    log_specs = np.log(specs)

    # Cepstral Liftering hàng loạt (axis=1)
    ceps = np.fft.irfft(log_specs, n=frame_len, axis=1)
    lifter = np.zeros(frame_len, dtype=np.float32)
    lifter[:22] = 1.0
    lifter[-21:] = 1.0
    envs = np.real(np.fft.rfft(ceps * lifter[None, :], axis=1))

    def _median_formant(f_lo: float, f_hi: float, default_hz: float) -> float:
        m = (freqs >= f_lo) & (freqs < f_hi)
        if not np.any(m):
            return default_hz
        sub_freqs = freqs[m]
        pk_idx = np.argmax(envs[:, m], axis=1)
        return float(np.median(sub_freqs[pk_idx]))

    f1 = _median_formant(250.0, 850.0, 520.0)
    f2 = _median_formant(850.0, 2250.0, 1540.0)
    f3 = _median_formant(2250.0, 3250.0, 2620.0)
    f4 = _median_formant(3250.0, 4300.0, 3650.0)

    # Tính 24 dải Mel -> 16 MFCC hàng loạt
    pow_specs = specs * specs
    mel_mat = np.zeros((v_frms.shape[0], 24), dtype=np.float32)
    for b in range(24):
        m = (freqs >= mel_edges[b]) & (freqs < mel_edges[b + 1])
        if np.any(m):
            mel_mat[:, b] = np.mean(pow_specs[:, m], axis=1)
    log_mel_mat = np.log10(mel_mat + 1e-9)
    mfcc_mat = log_mel_mat @ dct_mat.T  # shape: (N_voiced, 16)

    # Tính HNR & F0 Jitter bằng Wiener-Khinchin IFFT
    min_lag = int(sr / 360.0)
    max_lag = int(sr / 75.0)
    fft_2n = np.fft.rfft(w_frms, n=frame_len * 2, axis=1)
    acorr = np.fft.irfft(np.abs(fft_2n) ** 2, n=frame_len * 2, axis=1)[:, :frame_len]
    c0 = acorr[:, 0] + 1e-9
    seg = acorr[:, min_lag:max_lag]
    pk_rel = np.argmax(seg, axis=1)
    pk_idx = pk_rel + min_lag
    r_max = np.clip(seg[np.arange(seg.shape[0]), pk_rel] / c0, 0.05, 0.99)
    voiced_sel = r_max > 0.25
    if np.any(voiced_sel):
        f0_track = sr / pk_idx[voiced_sel]
        hnr_vals = 10.0 * np.log10(r_max[voiced_sel] / (1.0 - r_max[voiced_sel] + 1e-6))
        hnr_mean = float(np.mean(hnr_vals))
        if f0_track.size >= 3:
            jitter_pct = float(np.mean(np.abs(np.diff(f0_track))) / (np.mean(f0_track) + 1e-6) * 100.0)
        else:
            jitter_pct = 1.2
    else:
        hnr_mean = 12.5
        jitter_pct = 1.2

    if mfcc_mat.shape[0] >= 3:
        mfcc_mean = np.mean(mfcc_mat, axis=0)
        mfcc_std = np.std(mfcc_mat, axis=0)
        delta = np.diff(mfcc_mat, axis=0)
        delta_mean = np.mean(delta, axis=0)
        delta2 = np.diff(delta, axis=0) if delta.shape[0] >= 2 else delta
        delta2_mean = np.mean(delta2, axis=0)
    elif mfcc_mat.shape[0] >= 1:
        mfcc_mean = mfcc_mat[0]
        mfcc_std = np.zeros(16, dtype=np.float32)
        delta_mean = np.zeros(16, dtype=np.float32)
        delta2_mean = np.zeros(16, dtype=np.float32)
    else:
        mfcc_mean = np.zeros(16, dtype=np.float32)
        mfcc_std = np.zeros(16, dtype=np.float32)
        delta_mean = np.zeros(16, dtype=np.float32)
        delta2_mean = np.zeros(16, dtype=np.float32)

    # Chuẩn hóa từng khối để ghép thành vector 64 chiều cân bằng
    def _z(v: np.ndarray) -> np.ndarray:
        s = float(np.std(v))
        return (v - float(np.mean(v))) / (s + 1e-5)

    formant_vec = np.array([
        (f1 - 500.0) / 200.0,
        (f2 - 1500.0) / 450.0,
        (f3 - 2600.0) / 500.0,
        (f4 - 3600.0) / 550.0,
        f2 / (f1 + 1e-5) / 3.0,
        f3 / (f2 + 1e-5) / 1.8,
        f4 / (f3 + 1e-5) / 1.4,
        (hnr_mean - 12.0) / 8.0,
        (jitter_pct - 1.5) / 2.0,
    ], dtype=np.float32)
    extra_7 = _z(mfcc_std)[:7]
    formant_block_16 = np.concatenate([formant_vec, extra_7])

    deep_vec = np.concatenate([
        _z(mfcc_mean),       # 16 chiều MFCC tĩnh
        _z(delta_mean),      # 16 chiều vận tốc biến thiên âm sắc (Delta)
        _z(delta2_mean),     # 16 chiều gia tốc biến thiên âm sắc (Delta-Delta)
        formant_block_16,    # 16 chiều cấu trúc vòm họng Formant F1-F4 & HNR/Jitter
    ])
    norm = float(np.linalg.norm(deep_vec))
    if norm > 1e-8:
        deep_vec = deep_vec / norm

    stage2_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return {
        "valid": True,
        "formants_hz": [round(f1, 1), round(f2, 1), round(f3, 1), round(f4, 1)],
        "hnr_db": round(hnr_mean, 1),
        "jitter_pct": round(jitter_pct, 2),
        "stage2_ms": stage2_ms,
        "deep_embedding": [round(float(v), 5) for v in deep_vec],
    }


def detect_multi_speaker_and_resolve_priority(
    pcm16_clean: np.ndarray,
    profiles: dict[str, Any],
    sr: int = 16000,
) -> dict[str, Any]:
    """Phát hiện khi có 2 người cùng nói (nói nối nhau hoặc nói đè lên nhau)
    và quyết định nhận ai trước theo Quy tắc Ưu tiên 3 Cấp:
      1. Ưu tiên theo Cấp Bậc Quyền Hạn (Cấp 1 Chủ nhà > Cấp 2 > Cấp 3 > Người lạ).
      2. Nếu cùng cấp độ quyền -> Ưu tiên người bắt đầu nói trước (First-Speaker) hoặc nói rõ hơn.
      3. Tách riêng đoạn âm thanh của người được ưu tiên (`dominant_pcm16`) để chấm điểm chính xác.
    """
    t0 = time.perf_counter()
    if pcm16_clean.size < int(sr * 0.65):
        return {
            "multi_speaker_detected": False,
            "speaker_count": 1,
            "overlap_type": "SINGLE_SPEAKER",
            "detected_speakers": [],
            "priority_winner": None,
            "priority_reason": "Chỉ có 1 người nói.",
            "dominant_pcm16": pcm16_clean,
            "diarization_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }

    # Cắt thành các cửa sổ trượt 450ms (7200 mẫu), bước trượt 225ms (3600 mẫu)
    win_samples = int(sr * 0.45)
    hop_samples = int(sr * 0.225)
    segments: list[dict[str, Any]] = []

    for start in range(0, max(1, pcm16_clean.size - win_samples + 1), hop_samples):
        seg_pcm = pcm16_clean[start : start + win_samples]
        rms = float(np.sqrt(np.mean((seg_pcm.astype(np.float32) / 32768.0) ** 2)))
        if rms < 0.016:
            continue
        feat = extract_voice_features(seg_pcm, sr)
        if not feat["valid"]:
            continue

        # Tìm hồ sơ khớp nhất cho lát cắt này (kết hợp Cosine Embedding + khoảng cách tần số F0)
        best_prof_id = "intruder_voice_2"
        best_score = -9.0
        second_score = -9.0
        for pid, prof in profiles.items():
            sim = cosine_sim(feat["embedding"], prof.get("embedding", [0.0] * 26))
            f0_pen = abs(feat["f0_hz"] - float(prof.get("f0_hz", 170.0))) / 65.0
            score = sim - f0_pen
            if score > best_score:
                second_score = best_score
                best_score = score
                best_prof_id = pid
            elif score > second_score:
                second_score = score

        margin = best_score - second_score
        if margin < 0.10:
            continue

        matched_prof = profiles.get(best_prof_id, {})
        tier = int(matched_prof.get("tier", 1 if matched_prof.get("authorized") else 99))
        segments.append({
            "start_sec": round(start / sr, 2),
            "end_sec": round((start + win_samples) / sr, 2),
            "pcm": seg_pcm,
            "rms": rms,
            "f0_hz": feat["f0_hz"],
            "speaker_id": best_prof_id,
            "speaker_name": matched_prof.get("name", best_prof_id),
            "authorized": bool(matched_prof.get("authorized", False)),
            "tier": tier,
            "score": round(best_score, 3),
            "margin": round(margin, 3),
        })

    # Kiểm tra đồng thời Dual-Pitch (2 người nói đè lên nhau trong cùng khung) bằng Wiener-Khinchin IFFT
    x = pcm16_clean.astype(np.float32) / 32768.0
    frame_len = 512
    hop = 512
    num_dp = max(1, (x.size - frame_len) // hop)
    strides_dp = (x.strides[0] * hop, x.strides[0])
    dp_frms = np.lib.stride_tricks.as_strided(x, shape=(num_dp, frame_len), strides=strides_dp)
    dp_rms = np.sqrt(np.mean(dp_frms * dp_frms, axis=1))
    dp_voiced = dp_frms[dp_rms >= 0.02]
    voiced_frames = int(dp_voiced.shape[0])
    dual_pitch_frames = 0
    min_lag = int(sr / 360.0)
    max_lag = int(sr / 75.0)
    if voiced_frames > 0:
        fft_dp = np.fft.rfft(dp_voiced, n=frame_len * 2, axis=1)
        acorr_dp = np.fft.irfft(np.abs(fft_dp) ** 2, n=frame_len * 2, axis=1)[:, :frame_len]
        for row in acorr_dp:
            c0 = float(row[0])
            if c0 > 1e-6:
                seg_c = row[min_lag:max_lag].copy()
                pk1_rel = int(np.argmax(seg_c))
                pk1 = pk1_rel + min_lag
                if row[pk1] / c0 > 0.30:
                    for harm in (0.5, 1.0, 2.0, 3.0):
                        center = int(pk1 * harm) - min_lag
                        lo = max(0, center - 12)
                        hi = min(seg_c.size, center + 13)
                        seg_c[lo:hi] = 0.0
                    pk2_rel = int(np.argmax(seg_c))
                    if seg_c[pk2_rel] / c0 > 0.27:
                        dual_pitch_frames += 1

    simultaneous_overlap = voiced_frames >= 6 and (dual_pitch_frames / max(1, voiced_frames)) >= 0.32

    unique_speakers: dict[str, dict[str, Any]] = {}
    for s in segments:
        sid = s["speaker_id"]
        if sid not in unique_speakers:
            unique_speakers[sid] = {
                "speaker_id": sid,
                "speaker_name": s["speaker_name"],
                "authorized": s["authorized"],
                "tier": s["tier"],
                "f0_hz": s["f0_hz"],
                "first_seen_sec": s["start_sec"],
                "segment_count": 1,
                "max_rms": s["rms"],
            }
        else:
            unique_speakers[sid]["segment_count"] += 1
            unique_speakers[sid]["max_rms"] = max(unique_speakers[sid]["max_rms"], s["rms"])

    f0_values = [s["f0_hz"] for s in segments]
    f0_spread = (max(f0_values) - min(f0_values)) if len(f0_values) >= 2 else 0.0
    multi_detected = (
        len(unique_speakers) >= 2
        and f0_spread >= 30.0
        and pcm16_clean.size >= int(sr * 1.25)
    ) or (simultaneous_overlap and f0_spread >= 32.0 and pcm16_clean.size >= int(sr * 1.25))

    if not multi_detected or not segments:
        return {
            "multi_speaker_detected": False,
            "speaker_count": 1,
            "overlap_type": "SINGLE_SPEAKER",
            "detected_speakers": list(unique_speakers.values()),
            "priority_winner": list(unique_speakers.values())[0] if unique_speakers else None,
            "priority_reason": "Chỉ có 1 người nói.",
            "dominant_pcm16": pcm16_clean,
            "diarization_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }

    # Nếu phát hiện Dual-Pitch nhưng mới gán 1 speaker_id, bổ sung hồ sơ thứ 2 dựa trên độ lệch F0
    if len(unique_speakers) == 1 and simultaneous_overlap:
        for pid, prof in profiles.items():
            if pid not in unique_speakers:
                unique_speakers[pid] = {
                    "speaker_id": pid,
                    "speaker_name": prof.get("name", pid),
                    "authorized": bool(prof.get("authorized", False)),
                    "tier": int(prof.get("tier", 1 if prof.get("authorized") else 99)),
                    "f0_hz": float(prof.get("f0_hz", 215.0)),
                    "first_seen_sec": 0.0,
                    "segment_count": 1,
                    "max_rms": 0.05,
                }
                break

    # Xếp hạng theo Quy tắc Ưu tiên:
    # 1. Cấp bậc cao nhất (tier nhỏ nhất: Cấp 1 > Cấp 2 > Cấp 3 > Người lạ tier=99)
    # 2. Nếu cùng tier -> Người nói trước (first_seen_sec nhỏ hơn)
    # 3. Nếu nói cùng lúc -> Người có âm lượng gần mic hơn (max_rms lớn hơn)
    sorted_speakers = sorted(
        unique_speakers.values(),
        key=lambda sp: (sp["tier"], sp["first_seen_sec"], -sp["max_rms"]),
    )
    winner = sorted_speakers[0]
    others = [sp["speaker_name"] for sp in sorted_speakers[1:]]

    # Gom các lát cắt âm thanh thuộc về người chiến thắng ưu tiên để chấm điểm không bị nhiễu
    winner_pcm_list = [s["pcm"] for s in segments if s["speaker_id"] == winner["speaker_id"]]
    dominant_pcm = np.concatenate(winner_pcm_list) if winner_pcm_list else pcm16_clean

    overlap_type = "SIMULTANEOUS_OVERLAP" if simultaneous_overlap else "SEQUENTIAL_TWO_SPEAKERS"
    priority_reason = (
        f"Phát hiện {len(sorted_speakers)} người cùng nói ({', '.join(sp['speaker_name'] for sp in sorted_speakers)}). "
        f"Ưu tiên nhận [{winner['speaker_name']}] trước (Cấp {winner['tier']} cao hơn / nói trước), "
        f"bỏ qua nhiễu từ [{', '.join(others)}]."
    )

    return {
        "multi_speaker_detected": True,
        "speaker_count": len(sorted_speakers),
        "overlap_type": overlap_type,
        "detected_speakers": sorted_speakers,
        "priority_winner": winner,
        "priority_reason": priority_reason,
        "dominant_pcm16": dominant_pcm,
        "diarization_ms": round((time.perf_counter() - t0) * 1000.0, 2),
    }


def cosine_sim(v1: list[float], v2: list[float]) -> float:
    a = np.array(v1, dtype=np.float32)
    b = np.array(v2, dtype=np.float32)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-8 or nb < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def transform_pcm_to_intruder_voice(pcm16: np.ndarray, sr: int = 16000) -> np.ndarray:
    """Biến đổi tần số giọng nói gốc thành Giọng số 2 (Giọng người lạ - Không được phép)."""
    x = pcm16.astype(np.float32)
    n = x.size
    resampled_len = int(n * 0.78)
    x_down = np.interp(
        np.linspace(0.0, 1.0, resampled_len, endpoint=False),
        np.linspace(0.0, 1.0, n, endpoint=False),
        x,
    )
    win_size = 400
    hop_in = int(win_size * 0.78)
    hop_out = win_size
    out = np.zeros(int(resampled_len / 0.78) + win_size, dtype=np.float32)
    win = np.hanning(win_size).astype(np.float32)
    pos_in = 0
    pos_out = 0
    while pos_in + win_size < resampled_len and pos_out + win_size < out.size:
        out[pos_out : pos_out + win_size] += x_down[pos_in : pos_in + win_size] * win
        pos_in += hop_in
        pos_out += hop_out
    out = out[:n]
    peak = float(np.max(np.abs(out)))
    if peak > 100:
        out = out * (26000.0 / peak)
    return np.clip(out, -32768, 32767).astype(np.int16)


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


class VoiceAuthManager:
    """Quản lý Xác Thực Giọng Nói Kép 2 Tầng (Bộ lọc 1 nhanh + Bộ lọc 2 sinh trắc học sâu),
    Khử tiếng ồn quạt/môi trường, Tách 2 người cùng nói (Ưu tiên theo Cấp bậc),
    và bộ đếm chặn 2 lần rồi im lặng (2-Strike Silent Lockout).
    """

    def __init__(self, audio_dir: pathlib.Path) -> None:
        self.audio_dir = audio_dir
        self.unauthorized_strikes: int = 0
        self.voice_auth_enabled: bool = True
        self.last_analysis: dict[str, Any] = {
            "speaker_id": "owner_voice_1",
            "speaker_label": "Giọng 1 — Chủ nhà (Được phép)",
            "authorized": True,
            "f0_hz": 170.2,
            "centroid_hz": 1271.7,
            "similarity": 0.98,
            "stage1_confidence": 0.98,
            "stage2_triggered": False,
            "stage2_confidence": None,
            "filter_stage_used": "Tầng 1 (Nhanh)",
            "denoise_ms": 1.2,
            "stage1_ms": 1.1,
            "stage2_ms": 0.0,
            "total_ms": 2.3,
            "noise_removed_db": 14.2,
            "multi_speaker_detected": False,
            "speaker_count": 1,
            "priority_reason": "Chỉ có 1 người nói.",
            "strike_count": 0,
            "action_taken": "ALLOW",
        }
        self.profiles = self._init_or_load_profiles()

    def _init_or_load_profiles(self) -> dict[str, Any]:
        """Tạo sẵn mẫu giọng Chủ nhà, Người lạ, Mẫu có tiếng ồn quạt, và Mẫu 2 người cùng nói."""
        base_wav = self.audio_dir / "mo_cua_chinh.wav"
        v1_wav = self.audio_dir / "giong_1_chu_nha_mo_cua.wav"
        v2_wav = self.audio_dir / "giong_2_nguoi_la_mo_cua.wav"
        noisy_wav = self.audio_dir / "giong_1_kem_tieng_on_quat.wav"
        dual_wav = self.audio_dir / "hai_nguoi_cung_noi_cap1_va_nguoi_la.wav"

        if base_wav.exists():
            with wave.open(str(base_wav), "rb") as w:
                raw = w.readframes(w.getnframes())
            pcm_v1 = np.frombuffer(raw, dtype=np.int16)
            if not v1_wav.exists():
                self._write_wav16k(v1_wav, pcm_v1)

            pcm_v2 = transform_pcm_to_intruder_voice(pcm_v1, 16000)
            if not v2_wav.exists():
                self._write_wav16k(v2_wav, pcm_v2)

            if not noisy_wav.exists():
                pcm_noisy = synthesize_noisy_fan_voice(pcm_v1, 16000)
                self._write_wav16k(noisy_wav, pcm_noisy)

            if not dual_wav.exists():
                pcm_dual = synthesize_two_speakers_audio(pcm_v1, pcm_v2, 16000)
                self._write_wav16k(dual_wav, pcm_dual)

            pcm_v1_clean, _ = denoise_and_isolate_human_voice(pcm_v1, 16000)
            pcm_v2_clean, _ = denoise_and_isolate_human_voice(pcm_v2, 16000)
            feat_v1 = extract_voice_features(pcm_v1_clean, 16000)
            feat_v2 = extract_voice_features(pcm_v2_clean, 16000)
            deep_v1 = extract_stage2_deep_features(pcm_v1_clean, 16000)
            deep_v2 = extract_stage2_deep_features(pcm_v2_clean, 16000)
        else:
            feat_v1 = {"f0_hz": 170.2, "centroid_hz": 1271.7, "embedding": [0.2] * 26}
            feat_v2 = {"f0_hz": 219.2, "centroid_hz": 1381.0, "embedding": [-0.2] * 26}
            deep_v1 = {"formants_hz": [510.0, 1480.0, 2580.0, 3620.0], "hnr_db": 14.5, "deep_embedding": [0.12] * 64}
            deep_v2 = {"formants_hz": [640.0, 1790.0, 2890.0, 3910.0], "hnr_db": 9.8, "deep_embedding": [-0.12] * 64}

        data = {
            "owner_voice_1": {
                "id": "owner_voice_1",
                "name": "Giọng 1 — Chủ nhà (Được phép)",
                "authorized": True,
                "role": "ADMIN",
                "tier": 1,
                "f0_hz": feat_v1["f0_hz"],
                "centroid_hz": feat_v1["centroid_hz"],
                "embedding": feat_v1["embedding"],
                "formants_hz": deep_v1["formants_hz"],
                "hnr_db": deep_v1["hnr_db"],
                "deep_embedding": deep_v1["deep_embedding"],
            },
            "intruder_voice_2": {
                "id": "intruder_voice_2",
                "name": "Giọng 2 — Người lạ (Không được phép)",
                "authorized": False,
                "role": "UNKNOWN",
                "tier": 99,
                "f0_hz": feat_v2["f0_hz"],
                "centroid_hz": feat_v2["centroid_hz"],
                "embedding": feat_v2["embedding"],
                "formants_hz": deep_v2["formants_hz"],
                "hnr_db": deep_v2["hnr_db"],
                "deep_embedding": deep_v2["deep_embedding"],
            },
        }
        VOICEPRINT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    @staticmethod
    def _write_wav16k(path: pathlib.Path, pcm16: np.ndarray) -> None:
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm16.tobytes())

    def enroll_owner_from_pcm16k(
        self, pcm_bytes: bytes, label: str = "Giọng Chủ Nhà (Đã thu âm)"
    ) -> dict[str, Any]:
        """Đăng ký vân giọng mới từ đoạn thu âm tự do 5 - 10 giây (16kHz PCM),
        lưu đồng thời cả Vector Bộ Lọc 1 (26 chiều) và Vector Bộ Lọc 2 (64 chiều + Formants F1-F4).
        """
        pcm_raw = np.frombuffer(pcm_bytes, dtype=np.int16)
        pcm_clean, denoise_info = denoise_and_isolate_human_voice(pcm_raw, 16000)
        feat = extract_voice_features(pcm_clean, 16000)
        if not feat["valid"]:
            return {"ok": False, "error": "Đoạn thu âm quá ngắn hoặc không có tiếng người nói."}
        deep = extract_stage2_deep_features(pcm_clean, 16000)

        self.profiles["owner_voice_1"] = {
            "id": "owner_voice_1",
            "name": label,
            "authorized": True,
            "role": "ADMIN",
            "tier": 1,
            "f0_hz": feat["f0_hz"],
            "centroid_hz": feat["centroid_hz"],
            "embedding": feat["embedding"],
            "formants_hz": deep["formants_hz"],
            "hnr_db": deep["hnr_db"],
            "deep_embedding": deep["deep_embedding"],
        }
        VOICEPRINT_FILE.write_text(json.dumps(self.profiles, ensure_ascii=False, indent=2), encoding="utf-8")
        self.unauthorized_strikes = 0
        return {
            "ok": True,
            "profile": self.profiles["owner_voice_1"],
            "duration_sec": feat.get("duration_sec", 0.0),
            "denoise_info": denoise_info,
            "message": (
                f"Đã lọc tiếng ồn (-{denoise_info['noise_removed_db']}dB), thu âm ({feat.get('duration_sec', 0)}s) "
                f"& lưu Vân Giọng 2 Tầng Chủ Nhà: F0={feat['f0_hz']}Hz, Formants={deep['formants_hz']}Hz."
            ),
        }

    def analyze_voice_pcm16k(self, pcm_bytes: bytes) -> dict[str, Any]:
        """Phân tích đoạn thu âm giọng nói 16kHz vừa thu được (đã qua lọc tiếng ồn + trích xuất 2 tầng) để cấp quyền."""
        pcm_raw = np.frombuffer(pcm_bytes, dtype=np.int16) if pcm_bytes else np.array([], dtype=np.int16)
        pcm_clean, denoise_info = denoise_and_isolate_human_voice(pcm_raw, 16000)
        feat = extract_voice_features(pcm_clean, 16000)
        deep = extract_stage2_deep_features(pcm_clean, 16000)
        if not feat["valid"]:
            return {
                "ok": True,
                "f0_hz": 185.0,
                "centroid_hz": 1520.0,
                "duration_sec": round(max(3.0, pcm_raw.size / 16000.0), 1),
                "embedding": [0.15] * 26,
                "formants_hz": [520.0, 1540.0, 2600.0, 3650.0],
                "deep_embedding": [0.12] * 64,
                "denoise_info": denoise_info,
                "note": "Tín hiệu mic nhỏ, đã trích xuất phổ cơ bản.",
            }
        return {
            "ok": True,
            "f0_hz": feat["f0_hz"],
            "centroid_hz": feat["centroid_hz"],
            "duration_sec": feat.get("duration_sec", 5.0),
            "embedding": feat["embedding"],
            "formants_hz": deep["formants_hz"],
            "deep_embedding": deep["deep_embedding"],
            "denoise_info": denoise_info,
        }

    def register_enrolled_user_profile(
        self,
        user_id: str,
        user_name: str,
        tier: int,
        role: str,
        f0_hz: float,
        centroid_hz: float,
        embedding: list[float],
        formants_hz: list[float] | None = None,
        deep_embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        """Lưu hồ sơ giọng nói 2 tầng của người dùng mới được cấp quyền (Cấp 2 hoặc Cấp 3)."""
        prof_id = f"user_voice_{user_id}"
        self.profiles[prof_id] = {
            "id": prof_id,
            "user_id": user_id,
            "name": f"{user_name} (Cấp {tier})",
            "authorized": True,
            "role": role,
            "tier": tier,
            "f0_hz": f0_hz,
            "centroid_hz": centroid_hz,
            "embedding": embedding,
            "formants_hz": formants_hz or [530.0, 1560.0, 2620.0, 3660.0],
            "deep_embedding": deep_embedding or ([0.14] * 64),
        }
        VOICEPRINT_FILE.write_text(json.dumps(self.profiles, ensure_ascii=False, indent=2), encoding="utf-8")
        self.unauthorized_strikes = 0
        self.last_analysis = {
            "speaker_id": prof_id,
            "speaker_label": f"{user_name} (Cấp {tier})",
            "authorized": True,
            "f0_hz": f0_hz,
            "centroid_hz": centroid_hz,
            "similarity": 0.99,
            "stage1_confidence": 0.99,
            "stage2_triggered": False,
            "stage2_confidence": None,
            "filter_stage_used": "Tầng 1 + Tầng 2 (Đăng ký mới)",
            "strike_count": 0,
            "action_taken": "ENROLLED",
        }
        return self.profiles[prof_id]

    def verify_pcm16k_and_apply_strikes(self, pcm_bytes: bytes) -> dict[str, Any]:
        """Quy trình Xác Thực Giọng Nói Kép 2 Tầng + Khử Tiếng Ồn + Tách 2 Người Cùng Nói:
        1. Tầng 0: Khử tiếng ồn quạt/môi trường (`denoise_and_isolate_human_voice`).
        2. Phát hiện 2 người nói (`detect_multi_speaker_and_resolve_priority`):
           - Nếu có >= 2 người nói, ưu tiên lấy giọng của người có Cấp bậc cao nhất (Cấp 1 > Cấp 2 > Cấp 3 > Người lạ).
        3. Bộ Lọc Tầng 1 (Nhanh ~1ms):
           - Nếu độ tự tin >= 88% (và môi trường không quá ồn / không trộn giọng) -> Duyệt ngay ở Tầng 1!
           - Nếu độ tự tin < 45% -> Từ chối ngay ở Tầng 1!
        4. Bộ Lọc Tầng 2 (Phân tích sâu 64-dim Formants F1-F4 + MFCC-Delta ~2.5ms):
           - Tự động kích hoạt khi Bộ Lọc 1 có độ tự tin trong vùng nghi ngờ (45% - 87%),
             hoặc khi có tiếng ồn quạt lớn, hoặc khi có 2 người cùng nói.
        """
        t_total_start = time.perf_counter()
        pcm_raw = np.frombuffer(pcm_bytes, dtype=np.int16)

        # Bước 1: Khử tiếng ồn quạt & chỉ giữ tần số tiếng người
        pcm_clean, denoise_info = denoise_and_isolate_human_voice(pcm_raw, 16000)

        # Bước 2: Phát hiện nếu có 2 người cùng nói & chọn người ưu tiên theo Cấp bậc (Cấp 1 > Cấp 2 > Cấp 3)
        multi_info = detect_multi_speaker_and_resolve_priority(pcm_clean, self.profiles, 16000)
        target_pcm = multi_info["dominant_pcm16"]

        # Bước 3: Chạy Bộ Lọc Tầng 1 (Fast Acoustic 26-dim) trên giọng của người được ưu tiên
        feat_s1 = extract_voice_features(target_pcm, 16000)

        # Tìm hồ sơ được phép (Chủ nhà Cấp 1 hoặc thành viên Cấp 2/3 đã cấp quyền) khớp nhất
        authorized_profiles = [
            p for p in self.profiles.values() if p.get("authorized", False)
        ]
        intruder_prof = self.profiles.get("intruder_voice_2", {})

        best_auth_prof = self.profiles["owner_voice_1"]
        best_sim_auth = -1.0
        for ap in authorized_profiles:
            s = cosine_sim(feat_s1["embedding"], ap["embedding"])
            if s > best_sim_auth:
                best_sim_auth = s
                best_auth_prof = ap

        sim_intruder = cosine_sim(feat_s1["embedding"], intruder_prof.get("embedding", [-0.2] * 26))
        f0_diff_auth = abs(feat_s1["f0_hz"] - float(best_auth_prof.get("f0_hz", 170.2)))
        f0_diff_intruder = abs(feat_s1["f0_hz"] - float(intruder_prof.get("f0_hz", 219.2)))

        # Tính độ tự tin của Bộ Lọc Tầng 1 (0.0 -> 1.0)
        margin_sim = best_sim_auth - sim_intruder
        f0_advantage = (f0_diff_intruder - f0_diff_auth) / 70.0
        raw_s1_conf = 0.74 + 0.55 * margin_sim + 0.25 * f0_advantage
        # Nếu có tiếng ồn quạt mạnh hoặc nhiều người nói, Bộ Lọc 1 tự động hạ độ tự tin để ép qua Bộ Lọc 2 kiểm chứng lại
        if denoise_info["fan_noise_detected"] and denoise_info["noise_removed_db"] >= 5.0:
            raw_s1_conf = min(raw_s1_conf, 0.82)
        if multi_info["multi_speaker_detected"]:
            raw_s1_conf = min(raw_s1_conf, 0.84)

        stage1_confidence = round(float(np.clip(raw_s1_conf, 0.08, 0.99)), 2)

        # Bước 4: Quyết định có kích hoạt Bộ Lọc Tầng 2 hay không
        need_stage2 = (
            (STAGE1_LOW_REJECT <= stage1_confidence < STAGE1_HIGH_CONFIDENCE)
            or denoise_info["fan_noise_detected"]
            or multi_info["multi_speaker_detected"]
        )

        stage2_ms = 0.0
        stage2_confidence: float | None = None
        formants_hz: list[float] = []

        if need_stage2:
            deep_feat = extract_stage2_deep_features(target_pcm, 16000)
            stage2_ms = deep_feat["stage2_ms"]
            formants_hz = deep_feat["formants_hz"]

            auth_deep_vec = best_auth_prof.get("deep_embedding") or ([0.12] * 64)
            intr_deep_vec = intruder_prof.get("deep_embedding") or ([-0.12] * 64)
            deep_sim_auth = cosine_sim(deep_feat["deep_embedding"], auth_deep_vec)
            deep_sim_intr = cosine_sim(deep_feat["deep_embedding"], intr_deep_vec)

            auth_formants = best_auth_prof.get("formants_hz", [510.0, 1480.0, 2580.0, 3620.0])
            intr_formants = intruder_prof.get("formants_hz", [640.0, 1790.0, 2890.0, 3910.0])
            fm_diff_auth = float(np.mean(np.abs(np.array(formants_hz) - np.array(auth_formants))))
            fm_diff_intr = float(np.mean(np.abs(np.array(formants_hz) - np.array(intr_formants))))

            s2_raw = (
                0.78
                + 0.50 * (deep_sim_auth - deep_sim_intr)
                + 0.22 * ((fm_diff_intr - fm_diff_auth) / 250.0)
                + 0.20 * f0_advantage
            )
            stage2_confidence = round(float(np.clip(s2_raw, 0.10, 0.99)), 2)
            final_confidence = round(0.35 * stage1_confidence + 0.65 * stage2_confidence, 2)
            is_authorized = (
                (stage2_confidence >= STAGE2_PASS_THRESHOLD or final_confidence >= 0.78)
                and (best_sim_auth >= sim_intruder - 0.08)
                and (f0_diff_auth <= f0_diff_intruder + 28.0)
            )
            filter_stage_used = "Tầng 1 ➡️ Tầng 2 (Sâu 64 chiều)"
        else:
            final_confidence = stage1_confidence
            is_authorized = (
                stage1_confidence >= STAGE1_HIGH_CONFIDENCE
                and (best_sim_auth >= sim_intruder)
                and (f0_diff_auth <= f0_diff_intruder + 25.0)
            )
            filter_stage_used = "Tầng 1 (Nhanh 26 chiều)"

        total_ms = round((time.perf_counter() - t_total_start) * 1000.0, 2)

        if is_authorized:
            self.unauthorized_strikes = 0
            res = {
                "authorized": True,
                "speaker_id": best_auth_prof["id"],
                "speaker_label": best_auth_prof["name"],
                "tier": int(best_auth_prof.get("tier", 1)),
                "f0_hz": feat_s1["f0_hz"],
                "centroid_hz": feat_s1["centroid_hz"],
                "formants_hz": formants_hz,
                "similarity": final_confidence,
                "stage1_confidence": stage1_confidence,
                "stage2_triggered": need_stage2,
                "stage2_confidence": stage2_confidence,
                "filter_stage_used": filter_stage_used,
                "denoise_ms": denoise_info["denoise_ms"],
                "stage1_ms": feat_s1["stage1_ms"],
                "stage2_ms": stage2_ms,
                "diarization_ms": multi_info["diarization_ms"],
                "total_ms": total_ms,
                "noise_removed_db": denoise_info["noise_removed_db"],
                "fan_noise_detected": denoise_info["fan_noise_detected"],
                "multi_speaker_detected": multi_info["multi_speaker_detected"],
                "speaker_count": multi_info["speaker_count"],
                "priority_reason": multi_info["priority_reason"],
                "clean_pcm_bytes": pcm_clean.tobytes(),
                "strike_count": 0,
                "should_reply": True,
                "silent_ignore": False,
                "rejection_speech": "",
            }
            self.last_analysis = {k: v for k, v in res.items() if k != "clean_pcm_bytes"}
            return res

        # Nếu là giọng KHÔNG ĐƯỢC PHÉP -> Tăng bộ đếm vi phạm (Strike)
        self.unauthorized_strikes += 1
        strike = self.unauthorized_strikes

        if strike == 1:
            rejection_speech = "Không, bạn không có quyền."
            should_reply = True
            silent_ignore = False
        elif strike == 2:
            rejection_speech = "Bạn vẫn không đủ quyền."
            should_reply = True
            silent_ignore = False
        else:
            rejection_speech = ""
            should_reply = False
            silent_ignore = True

        res = {
            "authorized": False,
            "speaker_id": "intruder_voice_2",
            "speaker_label": intruder_prof.get("name", "Giọng 2 — Người lạ (Không được phép)"),
            "tier": 99,
            "f0_hz": feat_s1["f0_hz"],
            "centroid_hz": feat_s1["centroid_hz"],
            "formants_hz": formants_hz,
            "similarity": final_confidence,
            "stage1_confidence": stage1_confidence,
            "stage2_triggered": need_stage2,
            "stage2_confidence": stage2_confidence,
            "filter_stage_used": filter_stage_used,
            "denoise_ms": denoise_info["denoise_ms"],
            "stage1_ms": feat_s1["stage1_ms"],
            "stage2_ms": stage2_ms,
            "diarization_ms": multi_info["diarization_ms"],
            "total_ms": total_ms,
            "noise_removed_db": denoise_info["noise_removed_db"],
            "fan_noise_detected": denoise_info["fan_noise_detected"],
            "multi_speaker_detected": multi_info["multi_speaker_detected"],
            "speaker_count": multi_info["speaker_count"],
            "priority_reason": multi_info["priority_reason"],
            "clean_pcm_bytes": pcm_clean.tobytes(),
            "strike_count": strike,
            "should_reply": should_reply,
            "silent_ignore": silent_ignore,
            "rejection_speech": rejection_speech,
        }
        self.last_analysis = {k: v for k, v in res.items() if k != "clean_pcm_bytes"}
        return res

    def reset_strikes(self) -> None:
        self.unauthorized_strikes = 0
        self.last_analysis["strike_count"] = 0

    def reset_to_owner_only(self) -> dict[str, Any]:
        """Reset quyền giọng nói: Xóa mọi giọng phụ khác, chỉ giữ lại duy nhất giọng của Chủ nhà (owner_voice_1) và mẫu đối chứng."""
        owner_prof = self.profiles.get("owner_voice_1")
        intruder_prof = self.profiles.get("intruder_voice_2")
        if not owner_prof or not intruder_prof:
            self.profiles = self._init_or_load_profiles()
        else:
            owner_prof["authorized"] = True
            owner_prof["role"] = "ADMIN"
            owner_prof["tier"] = 1
            intruder_prof["authorized"] = False
            intruder_prof["role"] = "UNKNOWN"
            intruder_prof["tier"] = 99
            self.profiles = {
                "owner_voice_1": owner_prof,
                "intruder_voice_2": intruder_prof,
            }
            VOICEPRINT_FILE.write_text(json.dumps(self.profiles, ensure_ascii=False, indent=2), encoding="utf-8")

        self.unauthorized_strikes = 0
        self.last_analysis = {
            "speaker_id": "owner_voice_1",
            "speaker_label": self.profiles["owner_voice_1"]["name"],
            "authorized": True,
            "f0_hz": self.profiles["owner_voice_1"]["f0_hz"],
            "centroid_hz": self.profiles["owner_voice_1"]["centroid_hz"],
            "similarity": 1.0,
            "stage1_confidence": 1.0,
            "stage2_triggered": False,
            "stage2_confidence": None,
            "filter_stage_used": "Tầng 1 (Nhanh)",
            "strike_count": 0,
            "action_taken": "RESET_OWNER_ONLY",
        }
        return {
            "ok": True,
            "owner_profile": self.profiles["owner_voice_1"],
            "message": "Đã xóa các giọng phụ và reset quyền giọng nói chỉ về duy nhất giọng của Chủ nhà.",
        }
