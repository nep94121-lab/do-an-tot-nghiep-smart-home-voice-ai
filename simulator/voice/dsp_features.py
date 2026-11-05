"""Mo-dun DSP xu ly tin hieu thuan, Wiener Spectral Filter, Mel-Filterbank va MFCC Formants Extraction."""

from __future__ import annotations

import time
from typing import Any
import numpy as np

from simulator.voice.biometrics_neural import (
    compute_neural_similarity,
    extract_neural_embedding_256d,
)
from simulator.voice_config import (
    OWNER_ID,
    ROLE_MAP,
    THRESHOLD_DEEP,
    THRESHOLD_MEL,
    USER_ROLE_MAP,
)

STAGE1_HIGH_CONFIDENCE = THRESHOLD_MEL
STAGE1_LOW_REJECT = 0.45
STAGE2_PASS_THRESHOLD = THRESHOLD_DEEP


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
    if isinstance(pcm16, np.ndarray) and np.issubdtype(pcm16.dtype, np.floating) and (pcm16.size > 0 and np.max(np.abs(pcm16)) <= 1.05):
        pcm16 = np.clip(pcm16 * 32767.0, -32768, 32767).astype(np.int16)

    if pcm16.size < 1600:
        return {
            "valid": False,
            "f0_hz": 0.0,
            "centroid_hz": 0.0,
            "sub_bass_ratio": 0.0,
            "is_live_human": False,
            "stage1_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "embedding": [0.0] * 26,
            "is_filler_only": False,
            "has_fillers": False,
            "filler_ratio": 0.0,
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
    if np.sum(valid_mask) < 3:
        stage1_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "valid": False,
            "f0_hz": 0.0,
            "centroid_hz": 0.0,
            "sub_bass_ratio": 0.0,
            "is_live_human": False,
            "duration_sec": round(x.size / sr, 2),
            "stage1_ms": stage1_ms,
            "embedding": [0.0] * 26,
            "is_filler_only": False,
            "has_fillers": False,
            "filler_ratio": 0.0,
        }

    voiced_frames = all_frames[valid_mask]

    w_frms = voiced_frames * window[None, :]
    specs = np.abs(np.fft.rfft(w_frms, axis=1))
    pow_specs = specs * specs + 1e-12

    # Spectral centroid hàng loạt
    centroids = np.sum(specs * freqs[None, :], axis=1) / (np.sum(specs, axis=1) + 1e-9)

    # Năng lượng cận trầm + ngực (60 - 160 Hz) vs dải thoại (300 - 3200 Hz)
    sub_mask = (freqs >= 60.0) & (freqs <= 160.0)
    mid_mask = (freqs >= 300.0) & (freqs <= 3200.0)

    # Bộ lọc nhận diện âm đệm / ngập ngừng (Filler-Aware VAD & Vocal Fry Filter):
    # Khung âm đệm ("ừm", "ờ", vocal fry): Centroid < 550Hz, năng lượng trầm <250Hz >75%, formants cao bị triệt tiêu
    low_band_mask = freqs < 250.0
    tot_frame_p = np.sum(pow_specs, axis=1) + 1e-9
    low_band_ratio = np.sum(pow_specs[:, low_band_mask], axis=1) / tot_frame_p
    hi_formant_m = (freqs >= 1200.0) & (freqs <= 3800.0)
    mid_vocal_m = (freqs >= 100.0) & (freqs <= 800.0)
    hi_formant_r = np.sum(pow_specs[:, hi_formant_m], axis=1) / (np.sum(pow_specs[:, mid_vocal_m], axis=1) + 1e-9)

    is_filler_frame = (
        ((centroids < 550.0) & (low_band_ratio > 0.75))
        | (low_band_ratio > 0.85)
        | ((centroids < 600.0) & (hi_formant_r < 0.08) & (low_band_ratio > 0.70))
    )
    is_modal_frame = ~is_filler_frame
    has_modal_speech = bool(np.sum(is_modal_frame) >= 3)
    has_filler_speech = bool(np.sum(is_filler_frame) >= 3)

    if has_modal_speech:
        active_pow_specs = pow_specs[is_modal_frame]
        active_centroids = centroids[is_modal_frame]
        is_filler_only = False
        has_fillers = bool(np.any(is_filler_frame))
    elif has_filler_speech:
        active_pow_specs = pow_specs[is_filler_frame]
        active_centroids = centroids[is_filler_frame]
        is_filler_only = True
        has_fillers = True
    else:
        stage1_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "valid": False,
            "f0_hz": 0.0,
            "centroid_hz": 0.0,
            "sub_bass_ratio": 0.0,
            "is_live_human": False,
            "duration_sec": round(x.size / sr, 2),
            "stage1_ms": stage1_ms,
            "embedding": [0.0] * 26,
            "is_filler_only": False,
            "has_fillers": False,
            "filler_ratio": 0.0,
        }

    sub_bass_e = float(np.sum(active_pow_specs[:, sub_mask]))
    mid_voice_e = float(np.sum(active_pow_specs[:, mid_mask]))

    # 24 dải tần số từ 80 Hz đến 7600 Hz theo thang Mel (tính từ active_pow_specs để không bị âm đệm làm méo phổ)
    mel_edges = np.geomspace(80.0, 7600.0, num=25)
    band_energies = np.zeros(24, dtype=np.float64)
    for b in range(24):
        mask = (freqs >= mel_edges[b]) & (freqs < mel_edges[b + 1])
        if np.any(mask):
            band_energies[b] = float(np.sum( np.mean(active_pow_specs[:, mask], axis=1) ))

    # Ước lượng F0 siêu tốc bằng Định lý Wiener-Khinchin (Autocorrelation qua IFFT của Power Spectrum)
    min_lag = int(sr / 360.0)  # ~360 Hz max F0
    max_lag = int(sr / 75.0)   # ~75 Hz min F0
    fft_2n = np.fft.rfft(w_frms, n=frame_len * 2, axis=1)
    freqs_2n = np.fft.rfftfreq(frame_len * 2, d=1.0 / sr)
    pow_2n = np.abs(fft_2n) ** 2
    # Bù suy hao dải trầm 80-115Hz cho giọng nam trầm thật qua micro (tránh nhảy quãng tám lên hài bậc 2/3)
    deep_male_band = (freqs_2n >= 80.0) & (freqs_2n <= 120.0)
    mid_pitch_band = (freqs_2n > 145.0) & (freqs_2n <= 260.0)
    pow_2n_ref = pow_2n[is_modal_frame] if has_modal_speech else pow_2n
    e_deep = float(np.mean(pow_2n_ref[:, deep_male_band]) * 8.0)
    e_mid = float(np.mean(pow_2n_ref[:, mid_pitch_band]))
    is_deep_male = bool(e_deep >= 3.5 * e_mid and float(np.mean(is_filler_frame)) < 0.15)
    if is_deep_male:
        f0_weight = np.ones_like(freqs_2n, dtype=np.float32)
        f0_weight[(freqs_2n >= 80.0) & (freqs_2n < 115.0)] = 2.85
        f0_weight[freqs_2n > 380.0] = 0.25
        acorr = np.fft.irfft((np.abs(fft_2n) * f0_weight[None, :]) ** 2, n=frame_len * 2, axis=1)[:, :frame_len]
        half_pk_thresh = 0.82
    else:
        acorr = np.fft.irfft(pow_2n, n=frame_len * 2, axis=1)[:, :frame_len]
        half_pk_thresh = 0.70
    c0 = acorr[:, 0] + 1e-9
    seg = acorr[:, min_lag:max_lag]
    peak_rel = np.argmax(seg, axis=1)
    peak_idx = peak_rel + min_lag
    peak_val = seg[np.arange(seg.shape[0]), peak_rel]
    # Khử sai số nhảy nửa quãng tám (Sub-harmonic Octave Error ~85-95Hz ở giọng nam trầm):
    for r_i in range(peak_idx.shape[0]):
        pk = int(peak_idx[r_i])
        if pk >= 148:
            half_pk = pk // 2
            if half_pk >= min_lag and acorr[r_i, half_pk] >= half_pk_thresh * float(peak_val[r_i]):
                peak_idx[r_i] = half_pk
                peak_val[r_i] = acorr[r_i, half_pk]
    good_f0 = (c0 > 1e-6) & ((peak_val / c0) > 0.28)

    # Ưu tiên lấy F0 từ modal_speech_frames để không bị kéo tụt xuống dải vocal fry 78-90Hz hoặc nhảy quãng tám
    if has_modal_speech:
        modal_good_f0 = is_modal_frame & good_f0
        if np.any(modal_good_f0):
            f0_list = (sr / peak_idx[modal_good_f0]).tolist()
        else:
            f0_list = (sr / peak_idx[good_f0]).tolist()
    else:
        f0_list = (sr / peak_idx[good_f0]).tolist()

    f0_median = float(np.median(f0_list)) if f0_list else 165.0
    centroid_mean = float(np.mean(active_centroids)) if active_centroids.size > 0 else 1450.0
    sub_ratio = float(sub_bass_e / (mid_voice_e + 1e-9))

    log_bands = np.log10(band_energies / max(1, active_centroids.size) + 1e-9)
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
        "is_filler_only": is_filler_only,
        "has_fillers": has_fillers,
        "filler_ratio": round(float(np.mean(is_filler_frame)), 3),
        "is_deep_male": is_deep_male,
    }


def extract_stage2_deep_features(pcm16: np.ndarray, sr: int = 16000) -> dict[str, Any]:
    """[BỘ LỌC TẦNG 2 - CHUYÊN SÂU ~2.5ms]:
    Phân tích cấu trúc sinh trắc học thanh quản sâu khi Bộ Lọc 1 nghi ngờ (45% - 87%) hoặc môi trường ồn:
    - 4 Đỉnh cộng hưởng khoang miệng - họng (Formants F1, F2, F3, F4 Hz) qua Cepstral Envelope Liftering.
    - Tỷ số hài âm trên nhiễu (Harmonic-to-Noise Ratio HNR dB) & Độ rung chu kỳ thanh quản (Pitch Jitter %).
    - Vector đặc trưng 64 chiều (16 MFCC + 16 Delta MFCC + 16 Delta-Delta MFCC + 16 Formant/Harmonic descriptors).
    """
    t0 = time.perf_counter()
    if isinstance(pcm16, np.ndarray) and np.issubdtype(pcm16.dtype, np.floating) and (pcm16.size > 0 and np.max(np.abs(pcm16)) <= 1.05):
        pcm16 = np.clip(pcm16 * 32767.0, -32768, 32767).astype(np.int16)

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
    pow_specs = specs * specs

    # Tách biệt khung thể thức (modal frames) và khung âm đệm trong Tầng 2 để Formants F1-F4 không bị lệch
    cents_s2 = np.sum(specs * freqs[None, :], axis=1) / (np.sum(specs, axis=1) + 1e-9)
    low_p_s2 = np.sum(pow_specs[:, freqs < 250.0], axis=1)
    tot_p_s2 = np.sum(pow_specs, axis=1) + 1e-9
    low_r_s2 = low_p_s2 / tot_p_s2
    is_filler_s2 = ((cents_s2 < 550.0) & (low_r_s2 > 0.75)) | (low_r_s2 > 0.85)
    is_modal_s2 = ~is_filler_s2
    if np.sum(is_modal_s2) >= 3:
        v_frms = v_frms[is_modal_s2]
        w_frms = w_frms[is_modal_s2]
        specs = specs[is_modal_s2]
        pow_specs = pow_specs[is_modal_s2]

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

        # Không gán khung âm đệm ("ừm", "ờ", vocal fry) thành intruder_voice_2 gây báo động giả tách người nói
        if feat.get("is_filler_only") or (feat["centroid_hz"] < 550.0 and feat.get("sub_bass_ratio", 0) > 0.70) or feat.get("filler_ratio", 0) > 0.60:
            continue

        # Tìm hồ sơ khớp nhất cho lát cắt này (phân tách giữa Chủ nhà/Thành viên được phép và Người lạ)
        best_auth_id = "owner_voice_1"
        best_auth_score = -9.0
        intruder_score = -9.0
        for pid, prof in profiles.items():
            if pid not in ("owner_voice_1", "intruder_voice_2") and not prof.get("custom_enrolled"):
                continue
            sim = cosine_sim(feat["embedding"], prof.get("embedding", [0.0] * 26))
            f0_pen = abs(feat["f0_hz"] - float(prof.get("f0_hz", 170.0))) / 65.0
            score = sim - f0_pen
            if prof.get("baseline_embedding"):
                sim_b = cosine_sim(feat["embedding"], prof["baseline_embedding"])
                f0_pen_b = abs(feat["f0_hz"] - float(prof.get("baseline_f0_hz", 173.9))) / 65.0
                score = max(score, sim_b - f0_pen_b)
            if pid == "intruder_voice_2" or not prof.get("authorized", False):
                if score > intruder_score:
                    intruder_score = score
            else:
                if score > best_auth_score:
                    best_auth_score = score
                    best_auth_id = pid

        if best_auth_score >= intruder_score:
            best_prof_id = best_auth_id
            best_score = best_auth_score
            margin = best_auth_score - intruder_score
        else:
            best_prof_id = "intruder_voice_2"
            best_score = intruder_score
            margin = intruder_score - best_auth_score

        if margin < 0.08:
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

    # Chỉ kích hoạt multi_speaker_detected khi có >= 2 phân đoạn giọng nói thể thức (modal speech) ổn định và cấu trúc formants khác biệt thực sự
    stable_speakers = [sp for sp in unique_speakers.values() if sp["segment_count"] >= 2]
    formants_distinct = False
    if len(stable_speakers) >= 2:
        sp1_id = stable_speakers[0]["speaker_id"]
        sp2_id = stable_speakers[1]["speaker_id"]
        fm1 = np.array(profiles.get(sp1_id, {}).get("formants_hz", [500.0, 1500.0, 2500.0, 3500.0]))
        fm2 = np.array(profiles.get(sp2_id, {}).get("formants_hz", [640.0, 1790.0, 2890.0, 3910.0]))
        fm_diff = float(np.mean(np.abs(fm1 - fm2)))
        formants_distinct = bool(fm_diff >= 110.0 or sp1_id != sp2_id)

    multi_detected = bool(
        len(stable_speakers) >= 2
        and formants_distinct
        and f0_spread >= 30.0
        and pcm16_clean.size >= int(sr * 1.25)
    )

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
    # Nếu có các lát cắt giao thoa tạo ra > 2 cụm tạm thời, giữ lại 2 người nói có thời lượng/năng lượng rõ nhất
    top_candidates = sorted(
        unique_speakers.values(),
        key=lambda sp: (-sp["segment_count"], -sp["max_rms"], sp["tier"]),
    )[:2]
    # 1. Cấp bậc cao nhất (tier nhỏ nhất: Cấp 1 > Cấp 2 > Cấp 3 > Người lạ tier=99)
    # 2. Nếu cùng tier -> Người nói trước (first_seen_sec nhỏ hơn)
    # 3. Nếu nói cùng lúc -> Người có âm lượng gần mic hơn (max_rms lớn hơn)
    sorted_speakers = sorted(
        top_candidates,
        key=lambda sp: (sp["tier"], sp["first_seen_sec"], -sp["max_rms"]),
    )
    winner = sorted_speakers[0]
    others = [sp["speaker_name"] for sp in sorted_speakers[1:]]

    # Gom các lát cắt âm thanh thuộc về người chiến thắng ưu tiên để chấm điểm không bị nhiễu
    winner_pcm_list = [
        s["pcm"]
        for s in segments
        if s["speaker_id"] == winner["speaker_id"] or abs(s["f0_hz"] - winner["f0_hz"]) <= 14.0
    ]
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

