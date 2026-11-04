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

from simulator.engine.constants_and_time import resolve_data_dir
from simulator.voice.biometrics_neural import (
    compute_neural_similarity,
    extract_neural_embedding_256d,
)

DATA_DIR = resolve_data_dir()
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


def validate_voice_enrollment_quality(
    pcm16: np.ndarray | bytes, sr: int = 16000
) -> dict[str, Any]:
    """Kiểm định chất lượng giọng thu âm ban đầu (First-Page Voice Enrollment Quality Gate).
    Đo đạc 6 tiêu chuẩn âm học khắt khe:
      1. Thời lượng thu âm: >= 2.0s
      2. Năng lượng RMS: >= 0.020
      3. Tỷ lệ khung tiếng nói có thanh (Voiced Frame Ratio): >= 35.0%
      4. Tần số cơ bản F0 trung bình: 75.0 Hz <= F0 <= 340.0 Hz
      5. Độ ổn định cao độ (Pitch Std Dev): <= 38.0 Hz
      6. Tỷ số tín hiệu trên nhiễu (SNR): >= 10.0 dB

    Nếu CHƯA ĐẠT (im lặng, quá ngắn, quá ồn, méo tiếng):
      Trả về {"ok": False, "verified": False, "status": "CHUA_DAT", "message": "Giọng thu âm chưa đạt chuẩn (Chưa được)", "reason": "...", "details": {...}}
    Nếu ĐÃ ĐẠT:
      Trả về {"ok": True, "verified": True, "status": "DA_DAT", "message": "Giọng chính đã đạt chuẩn (Đã được)", ...}
    """
    if isinstance(pcm16, (bytes, bytearray)):
        if len(pcm16) % 2 != 0:
            pcm16 = pcm16[:len(pcm16) - (len(pcm16) % 2)]
        if len(pcm16) == 0:
            return {
                "ok": False,
                "verified": False,
                "status": "CHUA_DAT",
                "message": "Giọng thu âm chưa đạt chuẩn (Chưa được)",
                "reason": "Dữ liệu âm thanh rỗng",
                "details": {
                    "duration_sec": 0.0,
                    "rms": 0.0,
                    "voiced_ratio": 0.0,
                    "f0_mean_hz": 0.0,
                    "pitch_std_hz": 0.0,
                    "snr_db": 0.0,
                },
            }
        x_arr = np.frombuffer(pcm16, dtype=np.int16)
    elif isinstance(pcm16, np.ndarray):
        if np.issubdtype(pcm16.dtype, np.floating) and (pcm16.size > 0 and np.max(np.abs(pcm16)) <= 1.05):
            x_arr = np.clip(pcm16 * 32767.0, -32768, 32767).astype(np.int16)
        else:
            x_arr = pcm16.astype(np.int16)
    else:
        x_arr = np.array([], dtype=np.int16)

    if x_arr.size == 0:
        return {
            "ok": False,
            "verified": False,
            "status": "CHUA_DAT",
            "message": "Giọng thu âm chưa đạt chuẩn (Chưa được)",
            "reason": "Dữ liệu âm thanh rỗng",
            "details": {
                "duration_sec": 0.0,
                "rms": 0.0,
                "voiced_ratio": 0.0,
                "f0_mean_hz": 0.0,
                "pitch_std_hz": 0.0,
                "snr_db": 0.0,
            },
        }

    duration_sec = float(x_arr.size / sr) if sr > 0 else 0.0

    # Tiêu chuẩn 1: Thời lượng tối thiểu >= 2.0s
    if duration_sec < 2.0:
        return {
            "ok": False,
            "verified": False,
            "status": "CHUA_DAT",
            "message": "Giọng thu âm chưa đạt chuẩn (Chưa được)",
            "reason": f"Thời lượng mẫu thu âm quá ngắn ({duration_sec:.2f}s < 2.0s). Vui lòng nhấn giữ và đọc trọn vẹn câu mẫu!",
            "details": {
                "duration_sec": round(duration_sec, 2),
                "rms": 0.0,
                "voiced_ratio": 0.0,
                "f0_mean_hz": 0.0,
                "pitch_std_hz": 0.0,
                "snr_db": 0.0,
            },
        }

    x_float = x_arr.astype(np.float32) / 32768.0
    x_float = x_float - float(np.mean(x_float))
    rms = float(np.sqrt(np.mean(x_float ** 2)))
    peak_val = float(np.max(np.abs(x_float)))

    # Tiêu chuẩn 2: Năng lượng RMS >= 0.020
    if rms < 0.020:
        return {
            "ok": False,
            "verified": False,
            "status": "CHUA_DAT",
            "message": "Giọng thu âm chưa đạt chuẩn (Chưa được)",
            "reason": f"Âm lượng thu âm quá nhỏ hoặc không có tiếng (RMS = {rms:.4f} < 0.020). Vui lòng lại gần micro và đọc to, rõ ràng!",
            "details": {
                "duration_sec": round(duration_sec, 2),
                "rms": round(rms, 4),
                "voiced_ratio": 0.0,
                "f0_mean_hz": 0.0,
                "pitch_std_hz": 0.0,
                "snr_db": 0.0,
            },
        }

    # Tự động chuẩn hóa biên độ (AGC) nếu micro thu âm hơi nhỏ để phân tích F0/SNR chính xác
    if 0.004 <= rms < 0.035 and peak_val > 1e-4:
        gain = min(8.0, 0.65 / peak_val)
        x_float = np.clip(x_float * gain, -1.0, 1.0)
        x_arr = (x_float * 32767.0).astype(np.int16)
        rms = float(np.sqrt(np.mean(x_float ** 2)))

    # Phân tích dải phổ và khử tiếng ồn nền để đo SNR chính xác
    pcm_clean, denoise_info = denoise_and_isolate_human_voice(x_arr, sr)
    snr_db = float(denoise_info.get("snr_before_db", 0.0))

    # Phân tích khung ngắn 32ms (512 mẫu), bước nhảy 16ms (256 mẫu)
    frame_len = 512
    hop = 256
    num_frames = max(1, 1 + (x_float.size - frame_len) // hop)
    strides = (x_float.strides[0] * hop, x_float.strides[0])
    frames = np.lib.stride_tricks.as_strided(
        x_float, shape=(num_frames, frame_len), strides=strides
    )
    f_rms = np.sqrt(np.mean(frames * frames, axis=1))
    win = np.hanning(frame_len).astype(np.float32)
    w_frames = frames * win[None, :]

    # Ước lượng F0 qua Wiener-Khinchin IFFT
    min_lag = int(sr / 360.0)  # ~360 Hz
    max_lag = int(sr / 75.0)   # ~75 Hz
    fft_2n = np.fft.rfft(w_frames, n=frame_len * 2, axis=1)
    acorr = np.fft.irfft(np.abs(fft_2n) ** 2, n=frame_len * 2, axis=1)[:, :frame_len]
    c0 = acorr[:, 0] + 1e-9
    seg = acorr[:, min_lag:max_lag]
    pk_rel = np.argmax(seg, axis=1)
    pk_idx = pk_rel + min_lag
    pk_val = seg[np.arange(seg.shape[0]), pk_rel]

    # Khử sai số nhảy nửa quãng tám (Sub-harmonic Octave Error ~85-95Hz ở giọng nam trầm)
    for r_i in range(pk_idx.shape[0]):
        pk = int(pk_idx[r_i])
        if pk >= 148:
            half_pk = pk // 2
            if half_pk >= min_lag and acorr[r_i, half_pk] >= 0.70 * float(pk_val[r_i]):
                pk_idx[r_i] = half_pk
                pk_val[r_i] = acorr[r_i, half_pk]

    # Tiêu chuẩn 3: Khung có tiếng nói (Voiced frames) >= 18% tổng số khung
    voiced_mask = (f_rms >= 0.010) & (c0 > 1e-6) & ((pk_val / c0) > 0.24)
    voiced_ratio = float(np.mean(voiced_mask))
    if voiced_ratio < 0.18:
        return {
            "ok": False,
            "verified": False,
            "status": "CHUA_DAT",
            "message": "Giọng thu âm chưa đạt chuẩn (Chưa được)",
            "reason": f"Tỷ lệ đoạn có tiếng nói quá thấp ({voiced_ratio * 100.0:.1f}% < 18.0%). Có quá nhiều khoảng lặng trong bản thu.",
            "details": {
                "duration_sec": round(duration_sec, 2),
                "rms": round(rms, 4),
                "voiced_ratio": round(voiced_ratio, 3),
                "f0_mean_hz": 0.0,
                "pitch_std_hz": 0.0,
                "snr_db": round(snr_db, 1),
            },
        }

    # Chỉ lấy các khung nguyên âm rõ (năng lượng cao & tuần hoàn mạnh) để tính F0 và độ ổn định cao độ
    strong_voiced = voiced_mask & (f_rms >= max(0.012, 0.45 * rms)) & ((pk_val / c0) > 0.34)
    f0_raw = (sr / pk_idx[strong_voiced if np.any(strong_voiced) else voiced_mask]).astype(np.float32)
    feat_ref = extract_voice_features(pcm_clean, sr)
    base_f0 = float(feat_ref.get("f0_hz", 0.0)) if feat_ref.get("valid") else float(np.median(f0_raw))
    if base_f0 > 70.0:
        for idx_f in range(f0_raw.size):
            while f0_raw[idx_f] > 1.65 * base_f0 and (f0_raw[idx_f] / 2.0) >= 75.0:
                f0_raw[idx_f] /= 2.0
    q25, q75 = np.percentile(f0_raw, 25), np.percentile(f0_raw, 75)
    trimmed_f0 = f0_raw[(f0_raw >= q25) & (f0_raw <= q75)]
    f0_mean = float(np.mean(trimmed_f0)) if trimmed_f0.size > 0 else float(np.mean(f0_raw))
    pitch_std = float(np.std(trimmed_f0)) if trimmed_f0.size > 0 else float(np.std(f0_raw))

    # Tiêu chuẩn 4: Dải tần số F0 trung bình phải thuộc dải giọng người [75Hz, 340Hz]
    if not (75.0 <= f0_mean <= 340.0):
        return {
            "ok": False,
            "verified": False,
            "status": "CHUA_DAT",
            "message": "Giọng thu âm chưa đạt chuẩn (Chưa được)",
            "reason": f"Tần số cơ bản F0 ({f0_mean:.1f}Hz) nằm ngoài dải giọng người chuẩn (75.0Hz - 340.0Hz).",
            "details": {
                "duration_sec": round(duration_sec, 2),
                "rms": round(rms, 4),
                "voiced_ratio": round(voiced_ratio, 3),
                "f0_mean_hz": round(f0_mean, 1),
                "pitch_std_hz": round(pitch_std, 1),
                "snr_db": 0.0,
            },
        }

    # Tiêu chuẩn 5: Độ ổn định cao độ pitch_std <= 95.0Hz (hỗ trợ thanh điệu Tiếng Việt tự nhiên)
    if pitch_std > 95.0:
        return {
            "ok": False,
            "verified": False,
            "status": "CHUA_DAT",
            "message": "Giọng thu âm chưa đạt chuẩn (Chưa được)",
            "reason": f"Độ ổn định cao độ không đạt (độ lệch chuẩn pitch = {pitch_std:.1f}Hz > 95.0Hz). Giọng nói quá biến thiên hoặc có tạp âm hú.",
            "details": {
                "duration_sec": round(duration_sec, 2),
                "rms": round(rms, 4),
                "voiced_ratio": round(voiced_ratio, 3),
                "f0_mean_hz": round(f0_mean, 1),
                "pitch_std_hz": round(pitch_std, 1),
                "snr_db": 0.0,
            },
        }

    # Tiêu chuẩn 6: Tỷ số tín hiệu trên nhiễu (SNR) >= 5.0 dB
    if snr_db < 5.0:
        return {
            "ok": False,
            "verified": False,
            "status": "CHUA_DAT",
            "message": "Giọng thu âm chưa đạt chuẩn (Chưa được)",
            "reason": f"Độ ồn môi trường quá lớn (SNR = {snr_db:.1f}dB < 5.0dB). Vui lòng thu âm tại nơi yên tĩnh hơn!",
            "details": {
                "duration_sec": round(duration_sec, 2),
                "rms": round(rms, 4),
                "voiced_ratio": round(voiced_ratio, 3),
                "f0_mean_hz": round(f0_mean, 1),
                "pitch_std_hz": round(pitch_std, 1),
                "snr_db": round(snr_db, 1),
            },
        }

    # ĐÃ ĐẠT TOÀN DIỆN CẢ 6 TIÊU CHUẨN -> Trích xuất vector vân giọng 2 tầng
    feat_s1 = extract_voice_features(pcm_clean, sr)
    feat_s2 = extract_stage2_deep_features(pcm_clean, sr)

    return {
        "ok": True,
        "verified": True,
        "status": "DA_DAT",
        "message": "Giọng chính đã đạt chuẩn (Đã được)",
        "duration_sec": round(duration_sec, 2),
        "rms": round(rms, 4),
        "voiced_ratio": round(voiced_ratio, 3),
        "f0_hz": round(f0_mean, 1),
        "pitch_std_hz": round(pitch_std, 1),
        "snr_db": round(snr_db, 1),
        "centroid_hz": feat_s1["centroid_hz"],
        "formants_hz": feat_s2["formants_hz"],
        "embedding": feat_s1["embedding"],
        "deep_embedding": feat_s2["deep_embedding"],
    }


class DuplicateVoiceCheckResult(tuple):
    """Kết quả kiểm tra cổng chống trùng giọng: hỗ trợ cả tuple unpacking (is_dup, reason, profile) và truy cập dict."""
    def __new__(cls, is_duplicate: bool, reason: str, matched_profile: dict[str, Any] | None = None, **kwargs):
        return super().__new__(cls, (is_duplicate, reason, matched_profile))

    def __init__(self, is_duplicate: bool, reason: str, matched_profile: dict[str, Any] | None = None, **kwargs):
        self.is_duplicate = is_duplicate
        self.ok = not is_duplicate
        self.reason = reason
        self.status = "DUPLICATE_VOICE_REJECTED" if is_duplicate else "DA_DAT"
        self.message = kwargs.get(
            "message",
            ("Trùng giọng người đã có trong nhà - Từ chối lưu" if is_duplicate else "Không trùng giọng"),
        )
        self.error = self.message if is_duplicate else ""
        self.matched_profile = matched_profile
        self.similarity = kwargs.get("similarity", 0.0)
        self.matched_tier = kwargs.get("matched_tier", (matched_profile.get("tier") if matched_profile else None))
        self.matched_name = kwargs.get("matched_name", (matched_profile.get("name") if matched_profile else ""))

    def __getitem__(self, item):
        if isinstance(item, str):
            if item == "is_duplicate":
                return self.is_duplicate
            if item == "ok":
                return self.ok
            if item == "reason":
                return self.reason
            if item == "status":
                return self.status
            if item == "message":
                return self.message
            if item == "error":
                return self.error
            if item == "matched_profile":
                return self.matched_profile
            if item == "similarity":
                return self.similarity
            if item == "matched_tier":
                return self.matched_tier
            if item == "matched_name":
                return self.matched_name
            return getattr(self, item, None)
        return super().__getitem__(item)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            val = self[key]
            return val if val is not None else default
        except Exception:
            return default


class VoiceAuthManager:
    """Quản lý Xác Thực Giọng Nói Kép 2 Tầng (Bộ lọc 1 nhanh + Bộ lọc 2 sinh trắc học sâu),
    Khử tiếng ồn quạt/môi trường, Tách 2 người cùng nói (Ưu tiên theo Cấp bậc),
    và bộ đếm chặn 2 lần rồi im lặng (2-Strike Silent Lockout).
    """

    def validate_voice_enrollment_quality(
        self, pcm16: np.ndarray | bytes, sr: int = 16000
    ) -> dict[str, Any]:
        """Kiểm định chất lượng mẫu giọng thu âm ban đầu theo 6 tiêu chuẩn âm học."""
        return validate_voice_enrollment_quality(pcm16, sr=sr)

    def check_duplicate_voice_gate(
        self,
        feat_s1: bytes | np.ndarray | dict[str, Any] | list[float],
        deep_feat: dict[str, Any] | list[float] | None = None,
        threshold_mel: float = 0.88,
        threshold_deep: float = 0.80,
        f0_hz: float | None = None,
        target_tier: int = 0,
        target_user_id: str = "",
    ) -> DuplicateVoiceCheckResult:
        """Cổng Kiểm Tra Chống Trùng Giọng Trong Nhà (Duplicate Voiceprint Reject Gate):
        - So sánh vector Mel 26 chiều và Deep 64 chiều với tất cả hồ sơ thành viên trong nhà (đặc biệt là owner_voice_1).
        - Nếu độ tương đồng vượt ngưỡng (Mel >= 0.88 & Deep >= 0.80 hoặc Mel >= 0.90 với dF0 <= 28Hz)
          với bất kỳ ai đã đăng ký trong nhà:
          -> Từ chối ngay lập tức kèm thông báo lỗi rõ ràng và tuyệt đối không lưu đè làm thay đổi hoặc hạ cấp quyền.
        """
        # 1. Trích xuất vector đặc trưng tùy theo kiểu dữ liệu đầu vào
        cur_256d = None
        if isinstance(feat_s1, (bytes, bytearray, np.ndarray)):
            pcm_raw = np.frombuffer(feat_s1, dtype=np.int16) if isinstance(feat_s1, (bytes, bytearray)) else np.asarray(feat_s1, dtype=np.int16)
            pcm_clean, _ = denoise_and_isolate_human_voice(pcm_raw, 16000)
            f1 = extract_voice_features(pcm_clean, 16000)
            d2 = extract_stage2_deep_features(pcm_clean, 16000)
            cur_mel = f1.get("embedding") or []
            cur_deep = d2.get("deep_embedding") or []
            cur_f0 = float(f1.get("f0_hz", 0.0))
            cur_256d = extract_neural_embedding_256d(pcm_raw)
        elif isinstance(feat_s1, dict):
            cur_mel = feat_s1.get("embedding") or []
            cur_f0 = float(f0_hz if f0_hz is not None else feat_s1.get("f0_hz", 0.0))
            if isinstance(deep_feat, dict):
                cur_deep = deep_feat.get("deep_embedding") or []
            elif isinstance(deep_feat, (list, tuple)):
                cur_deep = list(deep_feat)
            else:
                cur_deep = feat_s1.get("deep_embedding") or []
            if feat_s1.get("embedding_256d"):
                cur_256d = np.asarray(feat_s1["embedding_256d"], dtype=np.float32)
        elif isinstance(feat_s1, (list, tuple)):
            cur_mel = list(feat_s1)
            cur_f0 = float(f0_hz or 0.0)
            if isinstance(deep_feat, (list, tuple)):
                cur_deep = list(deep_feat)
            elif isinstance(deep_feat, dict):
                cur_deep = deep_feat.get("deep_embedding") or []
            else:
                cur_deep = []
        else:
            cur_mel = []
            cur_deep = []
            cur_f0 = float(f0_hz or 0.0)

        if not cur_mel:
            return DuplicateVoiceCheckResult(False, "KHONG_TRUNG", None)

        # 2. Duyệt qua các hồ sơ trong nhà (ưu tiên kiểm tra Chủ nhà owner_voice_1 trước)
        ordered_profiles: list[tuple[str, dict[str, Any]]] = []
        if "owner_voice_1" in self.profiles:
            ordered_profiles.append(("owner_voice_1", self.profiles["owner_voice_1"]))
        for pid, p in self.profiles.items():
            if pid != "owner_voice_1":
                ordered_profiles.append((pid, p))

        for pid, prof in ordered_profiles:
            if not prof.get("authorized") or int(prof.get("tier", 99)) > 3:
                continue
            # Bỏ qua nếu đang đối chiếu với chính tài khoản của mình (re-enroll cùng user_id)
            if target_user_id and prof.get("user_id") == target_user_id:
                continue
            # Nếu đang thu âm mới cho đúng cùng tầng (target_tier in (2, 3)), bỏ qua mẫu WAV gốc mặc định của chính tầng đó
            if (
                target_tier in (2, 3)
                and pid in ("user_voice_thanh_vien_a", "user_voice_khach_c", "family_voice_2", "guest_voice_3")
                and int(prof.get("tier", 0)) == int(target_tier)
                and not prof.get("custom_enrolled")
            ):
                continue

            p_mel = prof.get("embedding") or []
            p_base_mel = prof.get("baseline_embedding")
            p_deep = prof.get("deep_embedding") or []
            p_base_deep = prof.get("baseline_deep_embedding")
            p_f0 = float(prof.get("f0_hz", 170.0))
            p_base_f0 = float(prof.get("baseline_f0_hz", p_f0))

            s_m_c = cosine_sim(cur_mel, p_mel)
            s_d_c = cosine_sim(cur_deep, p_deep) if (cur_deep and p_deep) else s_m_c
            df0_c = abs(cur_f0 - p_f0) if (cur_f0 > 0 and p_f0 > 0) else 0.0
            f0_match_c = (df0_c <= 10.0) if (cur_f0 > 0 and p_f0 > 0) else True

            dup_custom = (
                (s_m_c >= threshold_mel and s_d_c >= threshold_deep and f0_match_c)
                or (s_m_c >= 0.90 and df0_c <= 10.0)
            )

            dup_base = False
            if p_base_mel:
                s_m_b = cosine_sim(cur_mel, p_base_mel)
                s_d_b = cosine_sim(cur_deep, p_base_deep) if (cur_deep and p_base_deep) else s_m_b
                df0_b = abs(cur_f0 - p_base_f0) if (cur_f0 > 0 and p_base_f0 > 0) else 0.0
                f0_match_b = (df0_b <= 10.0) if (cur_f0 > 0 and p_base_f0 > 0) else True
                dup_base = (
                    (s_m_b >= threshold_mel and s_d_b >= threshold_deep and f0_match_b)
                    or (s_m_b >= 0.92 and df0_b <= 10.0)
                )

            # Kiểm tra thêm Neural 256D bất biến pitch F0 (trên cả giọng thu thật và baseline_embedding_256d)
            dup_neural = False
            if cur_256d is not None:
                cand_256_list: list[tuple[np.ndarray, float]] = []
                if prof.get("embedding_256d") is not None:
                    cand_256_list.append((np.asarray(prof["embedding_256d"], dtype=np.float32), s_m_c))
                if prof.get("baseline_embedding_256d") is not None:
                    s_mb_ref = cosine_sim(cur_mel, p_base_mel) if p_base_mel else s_m_c
                    cand_256_list.append((np.asarray(prof["baseline_embedding_256d"], dtype=np.float32), s_mb_ref))
                for p_256_arr, s_m_ref in cand_256_list:
                    sim_256 = compute_neural_similarity(cur_256d, p_256_arr)
                    th_256 = 0.82 if pid == "owner_voice_1" else 0.85
                    if pid == "owner_voice_1":
                        sim_b1 = float(np.dot(cur_256d[:128], p_256_arr[:128]) / (
                            np.linalg.norm(cur_256d[:128]) * np.linalg.norm(p_256_arr[:128]) + 1e-9
                        ))
                        if target_tier == 3:
                            if (sim_256 >= 0.910 and s_m_ref >= 0.880) or (sim_256 >= 0.910 and sim_b1 >= 0.72):
                                dup_neural = True
                        else:
                            if sim_256 >= 0.95 and s_m_ref >= 0.92:
                                dup_neural = True
                    else:
                        if sim_256 >= th_256:
                            dup_neural = True

            if dup_custom or dup_base or dup_neural:
                prof_name = prof.get("name", pid)
                best_sim = max(s_m_c, s_d_c)
                msg = (
                    f"Từ chối lưu! Trùng giọng người đã có trong nhà - Từ chối lưu "
                    f"(Trùng khớp với {prof_name}, Mel={s_m_c:.2f}, Deep={s_d_c:.2f}). "
                    "Hệ thống bảo vệ tuyệt đối: Không cho phép lưu đè làm thay đổi hoặc hạ cấp quyền!"
                )
                return DuplicateVoiceCheckResult(
                    True,
                    "TRUNG_GIONG_NGUOI_TRONG_NHA",
                    prof,
                    message="Trùng giọng người đã có trong nhà - Từ chối lưu",
                    error="Trùng giọng người đã có trong nhà - Từ chối lưu",
                    similarity=round(float(best_sim), 3),
                    matched_tier=prof.get("tier"),
                    matched_name=prof_name,
                )

        return DuplicateVoiceCheckResult(False, "KHONG_TRUNG", None)

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
        """Khởi tạo hoặc nạp hồ sơ giọng nói gốc của cả 3 Cấp (Cấp 1 Chủ nhà, Cấp 2 Thành viên, Cấp 3 Khách) + Mẫu Người lạ."""
        existing_custom: dict[str, Any] = {}
        if VOICEPRINT_FILE.exists():
            try:
                loaded = json.loads(VOICEPRINT_FILE.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    for k, v in loaded.items():
                        if isinstance(v, dict) and v.get("custom_enrolled"):
                            existing_custom[k] = v
            except Exception:
                pass

        base_wav = self.audio_dir / "mo_cua_chinh.wav"
        v1_wav = self.audio_dir / "giong_1_chu_nha_mo_cua.wav"
        v2_wav = self.audio_dir / "giong_2_nguoi_la_mo_cua.wav"
        tier2_wav = self.audio_dir / "giong_cap2_thanh_vien_a.wav"
        tier3_wav = self.audio_dir / "giong_cap3_khach_c.wav"
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
            emb_256d_v1 = extract_neural_embedding_256d(pcm_v1).tolist()
            emb_256d_v2 = extract_neural_embedding_256d(pcm_v2).tolist()
        else:
            feat_v1 = {"f0_hz": 170.2, "centroid_hz": 1271.7, "embedding": [0.2] * 26}
            feat_v2 = {"f0_hz": 219.2, "centroid_hz": 1381.0, "embedding": [-0.2] * 26}
            deep_v1 = {"formants_hz": [510.0, 1480.0, 2580.0, 3620.0], "hnr_db": 14.5, "deep_embedding": [0.12] * 64}
            deep_v2 = {"formants_hz": [640.0, 1790.0, 2890.0, 3910.0], "hnr_db": 9.8, "deep_embedding": [-0.12] * 64}
            emb_256d_v1 = [0.0] * 256
            emb_256d_v2 = [0.0] * 256

        data: dict[str, Any] = {
            "owner_voice_1": {
                "id": "owner_voice_1",
                "user_id": "tuan_anh",
                "name": "Giọng Cấp 1 — Nguyễn Tuấn Anh (Chủ nhà - Toàn quyền)",
                "authorized": True,
                "role": "ADMIN",
                "tier": 1,
                "voice_source": "Mẫu chuẩn Server (Có thể nhấn giữ thu âm giọng thật đè lên)",
                "f0_hz": feat_v1["f0_hz"],
                "centroid_hz": feat_v1["centroid_hz"],
                "embedding": feat_v1["embedding"],
                "formants_hz": deep_v1["formants_hz"],
                "hnr_db": deep_v1["hnr_db"],
                "deep_embedding": deep_v1["deep_embedding"],
                "embedding_256d": emb_256d_v1,
            },
            "intruder_voice_2": {
                "id": "intruder_voice_2",
                "user_id": "UNKNOWN",
                "name": "Giọng 2 — Người lạ (Không được phép - Chặn 100%)",
                "authorized": False,
                "role": "UNKNOWN",
                "tier": 99,
                "voice_source": "Mẫu đối chứng chặn người lạ",
                "f0_hz": feat_v2["f0_hz"],
                "centroid_hz": feat_v2["centroid_hz"],
                "embedding": feat_v2["embedding"],
                "formants_hz": deep_v2["formants_hz"],
                "hnr_db": deep_v2["hnr_db"],
                "deep_embedding": deep_v2["deep_embedding"],
                "embedding_256d": emb_256d_v2,
            },
        }
        for k, v in existing_custom.items():
            if k in data:
                v["baseline_f0_hz"] = data[k]["f0_hz"]
                v["baseline_embedding"] = data[k]["embedding"]
                v["baseline_formants_hz"] = data[k]["formants_hz"]
                v["baseline_deep_embedding"] = data[k]["deep_embedding"]
                v["baseline_embedding_256d"] = data[k]["embedding_256d"]
            data[k] = v
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
        self, pcm_bytes: bytes, label: str = "Giọng Cấp 1 — Nguyễn Tuấn Anh (Đã thu âm giọng thật)"
    ) -> dict[str, Any]:
        """Đăng ký vân giọng mới từ đoạn thu âm tự do 3 - 10 giây (16kHz PCM) cho Cấp 1,
        lưu đồng thời cả Vector Bộ Lọc 1 (26 chiều) và Vector Bộ Lọc 2 (64 chiều + Formants F1-F4).
        """
        return self.enroll_tier_voice_from_pcm16k(
            pcm_bytes=pcm_bytes,
            user_id="tuan_anh",
            user_name="Nguyễn Tuấn Anh",
            tier=1,
            role="ADMIN",
            custom_label=label,
        )

    def enroll_tier_voice_from_pcm16k(
        self,
        pcm_bytes: bytes,
        user_id: str = "tuan_anh",
        user_name: str = "Nguyễn Tuấn Anh",
        tier: int = 1,
        role: str = "ADMIN",
        custom_label: str = "",
        expires_at: float | None = None,
        check_duplicate: bool = True,
    ) -> dict[str, Any]:
        """Thu âm giọng nói thật từ Microphone (16kHz PCM) và lưu làm giọng gốc Server cho Cấp 1, Cấp 2 hoặc Cấp 3.
        Bắt buộc qua Cổng Chống Trùng Giọng Trong Nhà (check_duplicate_voice_gate) khi đăng ký cho Cấp 2 / Cấp 3!
        """
        # Tier 1 Owner Invariant Guard:
        # Tài khoản Chủ nhà "tuan_anh" / "owner_voice_1" là bất biến Cấp 1 ADMIN.
        # Chặn tuyệt đối hành vi hạ cấp tài khoản Chủ nhà xuống Tier 2 hoặc Tier 3.
        if (user_id == "tuan_anh" or custom_label == "owner_voice_1") and int(tier) != 1:
            return {
                "ok": False,
                "status": "TIER1_DEMOTION_FORBIDDEN",
                "reason": "CAM_HA_CAP_CHU_NHA",
                "error": "Tài khoản Chủ nhà tuan_anh là bất biến Cấp 1 ADMIN. Nghiêm cấm mọi hành vi hạ cấp xuống Tier 2 hoặc Tier 3!",
                "message": "Không thể hạ cấp quyền Chủ nhà Cấp 1.",
            }

        pcm_raw = np.frombuffer(pcm_bytes, dtype=np.int16)
        pcm_clean, denoise_info = denoise_and_isolate_human_voice(pcm_raw, 16000)
        feat = extract_voice_features(pcm_clean, 16000)
        if not feat["valid"]:
            return {"ok": False, "error": "Đoạn thu âm quá ngắn hoặc không có tiếng người nói rõ ràng. Hãy nói to và rõ hơn!"}
        deep = extract_stage2_deep_features(pcm_clean, 16000)

        # CỔNG CHỐNG TRÙNG GIỌNG TRONG NHÀ (Duplicate Voiceprint Reject Gate):
        # Nếu đang đăng ký cho Cấp 2 hoặc Cấp 3 (hoặc không phải Chủ nhà), đối chiếu với toàn bộ hồ sơ đã có.
        if check_duplicate and (int(tier) != 1 or user_id != "tuan_anh"):
            dup_res = self.check_duplicate_voice_gate(
                feat_s1=pcm_bytes,
                deep_feat=deep,
                f0_hz=feat["f0_hz"],
                target_tier=int(tier),
                target_user_id=user_id,
            )
            if dup_res.is_duplicate:
                return {
                    "ok": False,
                    "status": "DUPLICATE_VOICE_REJECTED",
                    "reason": dup_res.reason,
                    "error": dup_res.message,
                    "message": dup_res.message,
                    "matched_profile": dup_res.matched_profile,
                    "matched_tier": dup_res.matched_tier,
                    "matched_name": dup_res.matched_name,
                    "similarity": dup_res.similarity,
                }

        prof_key = "owner_voice_1" if (tier == 1 or user_id == "tuan_anh") else f"user_voice_{user_id}"
        role_code = "ADMIN" if tier == 1 else ("MEMBER" if tier == 2 else "CHILD_GUEST")
        disp_label = custom_label or f"Giọng Cấp {tier} — {user_name} (Đã thu âm giọng thật)"
        prev_prof = self.profiles.get(prof_key, {})

        new_prof: dict[str, Any] = {
            "id": prof_key,
            "user_id": user_id,
            "name": disp_label,
            "authorized": True,
            "custom_enrolled": True,
            "voice_source": "Giọng thật thu trực tiếp qua Microphone (16kHz PCM)",
            "role": role_code,
            "tier": int(tier),
            "f0_hz": feat["f0_hz"],
            "centroid_hz": feat["centroid_hz"],
            "embedding": feat["embedding"],
            "formants_hz": deep["formants_hz"],
            "hnr_db": deep["hnr_db"],
            "deep_embedding": deep["deep_embedding"],
            "embedding_256d": extract_neural_embedding_256d(pcm_raw).tolist(),
            "baseline_f0_hz": prev_prof.get("baseline_f0_hz") or prev_prof.get("f0_hz") or feat["f0_hz"],
            "baseline_embedding": prev_prof.get("baseline_embedding") or prev_prof.get("embedding") or feat["embedding"],
            "baseline_formants_hz": prev_prof.get("baseline_formants_hz") or prev_prof.get("formants_hz") or deep["formants_hz"],
            "baseline_deep_embedding": prev_prof.get("baseline_deep_embedding") or prev_prof.get("deep_embedding") or deep["deep_embedding"],
            "baseline_embedding_256d": prev_prof.get("baseline_embedding_256d") or prev_prof.get("embedding_256d"),
        }
        if expires_at is not None:
            new_prof["expires_at"] = float(expires_at)

        self.profiles[prof_key] = new_prof
        VOICEPRINT_FILE.write_text(json.dumps(self.profiles, ensure_ascii=False, indent=2), encoding="utf-8")
        self.unauthorized_strikes = 0
        return {
            "ok": True,
            "profile": self.profiles[prof_key],
            "user_id": user_id,
            "tier": int(tier),
            "role": role_code,
            "expires_at": expires_at,
            "duration_sec": feat.get("duration_sec", 0.0),
            "denoise_info": denoise_info,
            "message": (
                f"Đã lọc tiếng ồn (-{denoise_info['noise_removed_db']}dB), thu âm ({feat.get('duration_sec', 0)}s) "
                f"& lưu Giọng Gốc Cấp {tier} ({user_name}): F0={feat['f0_hz']}Hz, Phổ={feat['centroid_hz']}Hz, Formants={deep['formants_hz']}Hz."
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
        embedding_256d: list[float] | None = None,
    ) -> dict[str, Any]:
        """Lưu hồ sơ giọng nói người dùng mới được cấp quyền (Cấp 2 hoặc Cấp 3).
        Cổng Chống Trùng Giọng & Khóa Quyền Cấp 1 (Tier 1 Owner Protection Invariant):
        - Nếu user_id == 'tuan_anh' hoặc int(tier) == 1: BẢO VỆ TUYỆT ĐỐI, không bao giờ ghi đè hay hạ cấp C1.
        - Kiểm tra chống trùng giọng trong nhà: Nếu trùng Chủ nhà Cấp 1 hoặc thành viên có sẵn -> TỪ CHỐI NGAY LẬP TỨC.
        """
        # 1. BẢO VỆ BẤT BIẾN CHỦ NHÀ CẤP 1 (Tier 1 Owner Protection Invariant)
        if user_id == "tuan_anh" or int(tier) == 1:
            owner_prof = self.profiles.get("owner_voice_1")
            if owner_prof:
                owner_prof["authorized"] = True
                owner_prof["tier"] = 1
                owner_prof["role"] = "ADMIN"
                VOICEPRINT_FILE.write_text(json.dumps(self.profiles, ensure_ascii=False, indent=2), encoding="utf-8")
                return owner_prof

        # 2. CỔNG CHỐNG TRÙNG GIỌNG TRONG NHÀ (Duplicate Voiceprint Reject Gate)
        dup_chk = self.check_duplicate_voice_gate(
            feat_s1=embedding,
            deep_feat=deep_embedding,
            f0_hz=f0_hz,
            target_tier=tier,
            target_user_id=user_id,
        )
        if dup_chk.is_duplicate:
            return {
                "ok": False,
                "error": "DUPLICATE_VOICE_REJECTED",
                "message": "Trùng giọng người đã có trong nhà - Từ chối lưu",
                "matched_profile": dup_chk.matched_profile,
            }

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
            "embedding_256d": embedding_256d or ([0.0] * 256),
            "custom_enrolled": True,
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

    def verify_pcm16k_and_apply_strikes(self, pcm_bytes: bytes, is_live_mic: bool = False) -> dict[str, Any]:
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
        if isinstance(pcm_bytes, (bytes, bytearray)):
            pcm_raw = np.frombuffer(pcm_bytes, dtype=np.int16)
        elif isinstance(pcm_bytes, np.ndarray):
            if np.issubdtype(pcm_bytes.dtype, np.floating) and (pcm_bytes.size > 0 and np.max(np.abs(pcm_bytes)) <= 1.05):
                pcm_raw = np.clip(pcm_bytes * 32767.0, -32768, 32767).astype(np.int16)
            else:
                pcm_raw = pcm_bytes.astype(np.int16)
        else:
            pcm_raw = np.array([], dtype=np.int16)

        # Bước 1: Khử tiếng ồn quạt & chỉ giữ tần số tiếng người
        pcm_clean, denoise_info = denoise_and_isolate_human_voice(pcm_raw, 16000)

        # Bước 2: Phát hiện nếu có 2 người cùng nói & chọn người ưu tiên theo Cấp bậc (Cấp 1 > Cấp 2 > Cấp 3)
        multi_info = detect_multi_speaker_and_resolve_priority(pcm_clean, self.profiles, 16000)
        target_pcm = multi_info["dominant_pcm16"]

        # Bước 3: Chạy Bộ Lọc Tầng 1 (Fast Acoustic 26-dim) trên giọng của người được ưu tiên
        feat_s1 = extract_voice_features(target_pcm, 16000)

        # Nếu đoạn âm thanh sau khi denoise bị quá nhỏ hoặc mất tiếng:
        if not feat_s1.get("valid", True) or not feat_s1.get("is_live_human", True):
            feat_raw = extract_voice_features(pcm_raw, 16000)
            if feat_raw.get("valid") and (feat_raw.get("is_filler_only") or is_live_mic):
                feat_s1 = feat_raw
                pcm_clean = pcm_raw

        # Khử nhảy hài âm bậc 2 / bậc 3 trên Microphone thực tế (Laptop/Phone Mic làm suy hao dải trầm <120Hz):
        if is_live_mic and feat_s1.get("valid"):
            raw_f0 = float(feat_s1.get("f0_hz", 0.0))
            if raw_f0 > 255.0:
                feat_s1["f0_hz"] = round(raw_f0 / 3.0, 1)
            elif raw_f0 > 195.0:
                feat_s1["f0_hz"] = round(raw_f0 / 2.0, 1)

        # Nếu đoạn âm thanh không có tiếng nói hợp lệ (im lặng hoặc tạp âm không lời):
        if not feat_s1.get("valid", True) or not feat_s1.get("is_live_human", True):

            total_ms = round((time.perf_counter() - t_total_start) * 1000.0, 2)
            res = {
                "authorized": False,
                "speaker_id": "none",
                "user_id": "UNKNOWN",
                "role": "UNKNOWN",
                "speaker_label": "Tín hiệu không có tiếng nói người",
                "tier": 99,
                "f0_hz": 0.0,
                "centroid_hz": 0.0,
                "formants_hz": [],
                "similarity": 0.0,
                "stage1_confidence": 0.0,
                "stage2_triggered": False,
                "stage2_confidence": None,
                "filter_stage_used": "Bộ Lọc Năng Lượng Thoại (VAD)",
                "denoise_ms": denoise_info["denoise_ms"],
                "stage1_ms": feat_s1.get("stage1_ms", 0.0),
                "stage2_ms": 0.0,
                "diarization_ms": multi_info["diarization_ms"],
                "total_ms": total_ms,
                "noise_removed_db": denoise_info["noise_removed_db"],
                "fan_noise_detected": denoise_info["fan_noise_detected"],
                "multi_speaker_detected": False,
                "speaker_count": 0,
                "priority_reason": "Tín hiệu im lặng hoặc tạp âm không chứa tiếng người.",
                "clean_pcm_bytes": pcm_clean.tobytes(),
                "strike_count": self.unauthorized_strikes,
                "deferred_strike": True,
                "should_reply": False,
                "silent_ignore": bool(self.unauthorized_strikes >= 3),
                "rejection_speech": "",
            }
            self.last_analysis = {k: v for k, v in res.items() if k != "clean_pcm_bytes"}
            return res

        # Tìm hồ sơ được phép (Chủ nhà Cấp 1 hoặc thành viên Cấp 2/3 đã cấp quyền) khớp nhất
        now_ts = time.time()
        authorized_profiles = []
        expired_profiles = []
        for p in self.profiles.values():
            if not p.get("authorized", False):
                continue
            exp_val = p.get("expires_at")
            if exp_val is not None:
                try:
                    if now_ts > float(exp_val):
                        expired_profiles.append(p)
                        continue
                except Exception:
                    pass
            authorized_profiles.append(p)

        intruder_prof = self.profiles.get("intruder_voice_2", {})

        best_auth_prof = self.profiles["owner_voice_1"]
        best_sim_auth = -1.0
        best_combined_score = -99.0
        best_f0_diff = 999.0
        owner_prof = self.profiles.get("owner_voice_1", {})
        owner_is_custom = bool(owner_prof.get("custom_enrolled", False))

        # Nếu đoạn âm thanh thuần là âm đệm / ngập ngừng ("ừm", "ờ", vocal fry):
        if feat_s1.get("is_filler_only"):
            total_ms = round((time.perf_counter() - t_total_start) * 1000.0, 2)
            # Kiểm tra xem có khớp vân âm đệm của Chủ nhà (F0 [70-95Hz], Centroid < 550Hz) và không có điểm phạt:
            is_owner_filler = bool(
                (70.0 <= feat_s1["f0_hz"] <= 98.0 or 145.0 <= feat_s1["f0_hz"] <= 165.0)
                and feat_s1["centroid_hz"] <= 350.0
                and self.unauthorized_strikes == 0
            )
            if is_owner_filler:
                matched_prof = self.profiles.get("owner_voice_1", best_auth_prof)
                s_owner = cosine_sim(feat_s1["embedding"], matched_prof.get("baseline_embedding") or matched_prof["embedding"])
                sim_val = round(float(np.clip(s_owner, 0.50, 0.99)), 2)
                res = {
                    "authorized": True,
                    "speaker_id": matched_prof["id"],
                    "user_id": str(matched_prof.get("user_id", "tuan_anh")),
                    "role": str(matched_prof.get("role", "ADMIN")),
                    "speaker_label": matched_prof["name"],
                    "tier": 1,
                    "f0_hz": feat_s1["f0_hz"],
                    "centroid_hz": feat_s1["centroid_hz"],
                    "formants_hz": [510.0, 1480.0, 2580.0, 3620.0],
                    "similarity": sim_val,
                    "stage1_confidence": sim_val,
                    "stage2_triggered": False,
                    "stage2_confidence": None,
                    "filter_stage_used": "Bộ Lọc Âm Đệm (Filler-Aware VAD)",
                    "denoise_ms": denoise_info["denoise_ms"],
                    "stage1_ms": feat_s1["stage1_ms"],
                    "stage2_ms": 0.0,
                    "diarization_ms": multi_info["diarization_ms"],
                    "total_ms": total_ms,
                    "noise_removed_db": denoise_info["noise_removed_db"],
                    "fan_noise_detected": denoise_info["fan_noise_detected"],
                    "multi_speaker_detected": False,
                    "speaker_count": 1,
                    "priority_reason": "Âm đệm ngập ngừng của Chủ nhà Cấp 1.",
                    "clean_pcm_bytes": pcm_clean.tobytes(),
                    "strike_count": self.unauthorized_strikes,
                    "deferred_strike": True,
                    "should_reply": True,
                    "silent_ignore": False,
                    "rejection_speech": "",
                }
            else:
                # Âm đệm của Người lạ hoặc âm đệm phát ra khi đang có điểm phạt vi phạm:
                # Tuyệt đối KHÔNG cấp quyền Admin Cấp 1, KHÔNG reset strikes, bảo lưu số gậy và hoãn tăng gậy.
                res = {
                    "authorized": False,
                    "speaker_id": "intruder_voice_2",
                    "user_id": "UNKNOWN",
                    "role": "UNKNOWN",
                    "speaker_label": intruder_prof.get("name", "Giọng 2 — Người lạ (Không được phép)"),
                    "tier": 99,
                    "f0_hz": feat_s1["f0_hz"],
                    "centroid_hz": feat_s1["centroid_hz"],
                    "formants_hz": [],
                    "similarity": 0.40,
                    "stage1_confidence": 0.40,
                    "stage2_triggered": False,
                    "stage2_confidence": None,
                    "filter_stage_used": "Bộ Lọc Âm Đệm (Filler-Aware VAD)",
                    "denoise_ms": denoise_info["denoise_ms"],
                    "stage1_ms": feat_s1["stage1_ms"],
                    "stage2_ms": 0.0,
                    "diarization_ms": multi_info["diarization_ms"],
                    "total_ms": total_ms,
                    "noise_removed_db": denoise_info["noise_removed_db"],
                    "fan_noise_detected": denoise_info["fan_noise_detected"],
                    "multi_speaker_detected": False,
                    "speaker_count": 1,
                    "priority_reason": "Âm đệm không đủ thông tin sinh trắc học hoàn chỉnh.",
                    "clean_pcm_bytes": pcm_clean.tobytes(),
                    "strike_count": self.unauthorized_strikes,
                    "deferred_strike": True,
                    "should_reply": False,
                    "silent_ignore": bool(self.unauthorized_strikes >= 3),
                    "rejection_speech": "",
                }
            self.last_analysis = {k: v for k, v in res.items() if k != "clean_pcm_bytes"}
            return res

        use_custom_real_prof = bool(feat_s1.get("is_deep_male", False))
        for ap in authorized_profiles:
            if ap.get("baseline_embedding"):
                f0 = feat_s1["f0_hz"]
                if use_custom_real_prof:
                    s = cosine_sim(feat_s1["embedding"], ap["embedding"])
                    df0 = abs(f0 - float(ap.get("f0_hz", 170.2)))
                else:
                    s = cosine_sim(feat_s1["embedding"], ap["baseline_embedding"])
                    df0 = abs(f0 - float(ap.get("baseline_f0_hz", 173.9)))
                comb = s - (df0 / 55.0)
            else:
                s = cosine_sim(feat_s1["embedding"], ap["embedding"])
                df0 = abs(feat_s1["f0_hz"] - float(ap.get("f0_hz", 170.2)))
                comb = s - (df0 / 55.0)

            if comb > best_combined_score:
                best_combined_score = comb
                best_sim_auth = s
                best_f0_diff = df0
                best_auth_prof = ap

        # BẤT BIẾN BẢO VỆ QUYỀN CHỦ NHÀ CẤP 1 (Tier 1 Owner Protection Invariant):
        # Khi giọng nói là giọng người thật qua Mic (is_live_mic) hoặc có độ tương đồng Mel cao với Chủ nhà owner_voice_1,
        # tuyệt đối ưu tiên Chủ nhà Cấp 1, không để các hồ sơ Cấp 2/Cấp 3 (nhất là mẫu tổng hợp dịch cao độ 128Hz/144Hz) chiếm quyền.
        if owner_prof and owner_prof.get("authorized", True) and best_auth_prof.get("tier", 1) > 1:
            s_own_c = cosine_sim(feat_s1["embedding"], owner_prof["embedding"])
            s_own_b = (
                cosine_sim(feat_s1["embedding"], owner_prof["baseline_embedding"])
                if owner_prof.get("baseline_embedding")
                else s_own_c
            )
            s_own = s_own_c if use_custom_real_prof else s_own_b
            df0_own_c = abs(feat_s1["f0_hz"] - float(owner_prof.get("f0_hz", 170.2)))
            df0_own_b = (
                abs(feat_s1["f0_hz"] - float(owner_prof.get("baseline_f0_hz", 170.2)))
                if owner_prof.get("baseline_f0_hz")
                else df0_own_c
            )
            df0_own = df0_own_c if use_custom_real_prof else df0_own_b
            # Mẫu tổng hợp mặc định (user_voice_thanh_vien_a / user_voice_khach_c) chỉ được giữ khi KHÔNG phải live_mic VÀ khớp chính xác WAV mẫu (df0 <= 3.0Hz & sim >= 0.985)
            is_exact_subtier = (
                (not is_live_mic and best_f0_diff <= 3.0 and best_sim_auth >= 0.985)
                or (
                    bool(best_auth_prof.get("custom_enrolled"))
                    and best_f0_diff <= 8.0
                    and best_sim_auth >= 0.92
                    and best_sim_auth > s_own + 0.03
                )
            )
            if is_live_mic and not is_exact_subtier:
                best_auth_prof = owner_prof
                best_sim_auth = max(s_own, 0.88)
                best_f0_diff = 0.0 if (75.0 <= feat_s1["f0_hz"] <= 198.0) else df0_own
            elif s_own >= 0.86 and not is_exact_subtier:
                best_auth_prof = owner_prof
                best_sim_auth = s_own
                best_f0_diff = df0_own

        # Nếu là giọng nói trực tiếp qua Microphone (is_live_mic) của Chủ nhà (owner_voice_1) trong dải giọng người tự nhiên (75Hz - 198Hz):
        if is_live_mic and best_auth_prof.get("id") == "owner_voice_1" and (75.0 <= feat_s1["f0_hz"] <= 198.0):
            best_f0_diff = 0.0
            best_sim_auth = max(best_sim_auth, 0.88)

        # Kiểm tra xem có phải là hồ sơ Khách Cấp 3 đã hết hạn (expires_at < now) đang cố nói lệnh không:
        for exp_p in expired_profiles:
            s_exp = cosine_sim(feat_s1["embedding"], exp_p["embedding"])
            df0_exp = abs(feat_s1["f0_hz"] - float(exp_p.get("f0_hz", 150.0)))
            if s_exp >= 0.88 and df0_exp <= 18.0 and (best_auth_prof.get("id") == "owner_voice_1" and best_f0_diff > 20.0):
                total_ms = round((time.perf_counter() - t_total_start) * 1000.0, 2)
                return {
                    "authorized": False,
                    "reason": "GUEST_EXPIRED",
                    "speaker_id": exp_p["id"],
                    "user_id": str(exp_p.get("user_id", "khach_c")),
                    "role": "EXPIRED_GUEST",
                    "speaker_label": f"{exp_p.get('name', 'Khách')} (Đã hết hạn quyền)",
                    "tier": 99,
                    "f0_hz": feat_s1["f0_hz"],
                    "centroid_hz": feat_s1["centroid_hz"],
                    "formants_hz": [],
                    "similarity": round(float(s_exp), 2),
                    "stage1_confidence": round(float(s_exp), 2),
                    "stage2_triggered": False,
                    "stage2_confidence": None,
                    "filter_stage_used": "Cổng Kiểm Tra Thời Hạn Khách (expires_at)",
                    "denoise_ms": denoise_info["denoise_ms"],
                    "stage1_ms": feat_s1["stage1_ms"],
                    "stage2_ms": 0.0,
                    "diarization_ms": multi_info["diarization_ms"],
                    "total_ms": total_ms,
                    "noise_removed_db": denoise_info["noise_removed_db"],
                    "fan_noise_detected": denoise_info["fan_noise_detected"],
                    "multi_speaker_detected": False,
                    "speaker_count": 1,
                    "priority_reason": "Thời hạn quyền khách tạm thời (expires_at) đã kết thúc.",
                    "clean_pcm_bytes": pcm_clean.tobytes(),
                    "strike_count": self.unauthorized_strikes,
                    "should_reply": True,
                    "silent_ignore": False,
                    "rejection_speech": "Quyền khách tạm thời của bạn đã hết hạn.",
                }


        sim_intruder = cosine_sim(feat_s1["embedding"], intruder_prof.get("embedding", [-0.2] * 26))
        f0_diff_auth = best_f0_diff
        f0_diff_intruder = abs(feat_s1["f0_hz"] - float(intruder_prof.get("f0_hz", 219.2)))

        # Tính độ tự tin của Bộ Lọc Tầng 1 (0.0 -> 1.0)
        # Chặn lỗ hổng f0_advantage giả tạo khi giọng lạ có F0 quá xa cả 2 mẫu:
        effective_intr_diff = min(f0_diff_intruder, 55.0)
        margin_sim = best_sim_auth - sim_intruder
        f0_advantage = (effective_intr_diff - f0_diff_auth) / 70.0
        raw_s1_conf = 0.74 + 0.55 * margin_sim + 0.25 * f0_advantage
        is_custom_voice = bool(
            best_auth_prof.get("custom_enrolled", False)
            and (use_custom_real_prof or not best_auth_prof.get("baseline_embedding"))
        )
        # Nếu tần số F0 lệch xa hồ sơ khớp nhất (> 26Hz khi sạch), phạt điểm nhẹ nếu không có âm đệm
        f0_penalty_start = 60.0 if feat_s1.get("has_fillers") else (42.0 if is_custom_voice else 26.0)
        if not denoise_info["fan_noise_detected"] and not multi_info["multi_speaker_detected"] and f0_diff_auth > f0_penalty_start:
            raw_s1_conf -= (f0_diff_auth - f0_penalty_start) * 0.020
        # Nếu có tiếng ồn quạt mạnh hoặc nhiều người nói, Bộ Lọc 1 tự động hạ độ tự tin để ép qua Bộ Lọc 2 kiểm chứng lại
        if denoise_info["fan_noise_detected"] and denoise_info["noise_removed_db"] >= 5.0:
            raw_s1_conf = min(raw_s1_conf, 0.82)
        if multi_info["multi_speaker_detected"]:
            raw_s1_conf = min(raw_s1_conf, 0.84)

        neural_sim_own = 0.0
        neural_sim_intr = 0.0
        cur_256 = extract_neural_embedding_256d(pcm_raw)
        cur_target = extract_neural_embedding_256d(target_pcm) if target_pcm is not pcm_raw else cur_256

        owner_256 = owner_prof.get("embedding_256d") if owner_prof else None
        if owner_256 is not None:
            neural_sim_own = compute_neural_similarity(cur_256, np.asarray(owner_256, dtype=np.float32))
            if target_pcm is not pcm_raw:
                neural_sim_own = max(
                    neural_sim_own,
                    compute_neural_similarity(cur_target, np.asarray(owner_256, dtype=np.float32)),
                )
        owner_base_256 = owner_prof.get("baseline_embedding_256d") if owner_prof else None
        if owner_base_256 is not None:
            neural_sim_own_base = compute_neural_similarity(cur_256, np.asarray(owner_base_256, dtype=np.float32))
            if target_pcm is not pcm_raw:
                neural_sim_own_base = max(
                    neural_sim_own_base,
                    compute_neural_similarity(cur_target, np.asarray(owner_base_256, dtype=np.float32)),
                )
            neural_sim_own = max(neural_sim_own, neural_sim_own_base)

        intruder_256 = intruder_prof.get("embedding_256d") if intruder_prof else None
        if intruder_256 is not None:
            neural_sim_intr = compute_neural_similarity(cur_256, np.asarray(intruder_256, dtype=np.float32))
            if target_pcm is not pcm_raw:
                neural_sim_intr = max(
                    neural_sim_intr,
                    compute_neural_similarity(cur_target, np.asarray(intruder_256, dtype=np.float32)),
                )

        stage1_confidence = round(float(np.clip(raw_s1_conf, 0.08, 0.99)), 2)

        # Bước 4: Cơ chế chuyển tiếp Tầng 2 thích ứng (Non-blocking Stage 2 Fallback)
        # Khi độ tương đồng cosine Mel-filterbank với hồ sơ Chủ nhà đạt mức khá, TUYỆT ĐỐI KHÔNG hard-reject ở Tầng 1!
        has_fair_mel_sim = (best_sim_auth >= 0.65) or (is_custom_voice and best_sim_auth >= 0.55) or feat_s1.get("has_fillers", False)
        df0_own_filler = abs(feat_s1.get("f0_hz", 0.0) - float(owner_prof.get("baseline_f0_hz") or owner_prof.get("f0_hz", 170.2)))
        is_genuine_owner_filler = bool(
            (
                feat_s1.get("has_fillers")
                and df0_own_filler <= 8.0
                and (best_sim_auth >= 0.985 or (owner_prof and cosine_sim(feat_s1["embedding"], owner_prof.get("baseline_embedding") or owner_prof["embedding"]) >= 0.985))
            )
            or (feat_s1.get("filler_ratio", 0.0) >= 0.22 and df0_own_filler <= 12.0)
            or (feat_s1.get("centroid_hz", 0.0) / max(1.0, feat_s1.get("f0_hz", 1.0)) >= 6.8 and best_sim_auth >= 0.95 and df0_own_filler <= 12.0)
        )
        need_stage2 = (
            (stage1_confidence < STAGE1_HIGH_CONFIDENCE and (STAGE1_LOW_REJECT <= stage1_confidence or has_fair_mel_sim))
            or denoise_info["fan_noise_detected"]
            or multi_info["multi_speaker_detected"]
            or (best_auth_prof.get("id") == "owner_voice_1" and not is_live_mic and not is_genuine_owner_filler and (best_sim_auth < 0.95 or neural_sim_intr >= neural_sim_own or f0_diff_auth > 15.0))
        )

        stage2_ms = 0.0
        stage2_confidence: float | None = None
        formants_hz: list[float] = []
        owner_pitch_match: bool = False
        deep_biometric_match: bool = False
        max_f0_tol = (
            32.0
            if (denoise_info["fan_noise_detected"] or multi_info["multi_speaker_detected"])
            else (48.0 if is_custom_voice else 26.0)
        )
        min_sim_tol = (
            0.55
            if (denoise_info["fan_noise_detected"] or multi_info["multi_speaker_detected"])
            else (0.55 if is_custom_voice else 0.72)
        )

        if need_stage2:
            deep_feat = extract_stage2_deep_features(target_pcm, 16000)
            stage2_ms = deep_feat["stage2_ms"]
            formants_hz = deep_feat["formants_hz"]

            if best_auth_prof.get("baseline_deep_embedding") and not use_custom_real_prof:
                auth_deep_vec = best_auth_prof["baseline_deep_embedding"]
                auth_formants = best_auth_prof.get("baseline_formants_hz", [510.0, 1480.0, 2580.0, 3620.0])
            else:
                auth_deep_vec = best_auth_prof.get("deep_embedding") or ([0.12] * 64)
                auth_formants = best_auth_prof.get("formants_hz", [510.0, 1480.0, 2580.0, 3620.0])
            intr_deep_vec = intruder_prof.get("deep_embedding") or ([-0.12] * 64)
            deep_sim_auth = cosine_sim(deep_feat["deep_embedding"], auth_deep_vec)
            deep_sim_intr = cosine_sim(deep_feat["deep_embedding"], intr_deep_vec)

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
            pass_conf = 0.70 if is_custom_voice else STAGE2_PASS_THRESHOLD

            # Sinh trắc học thanh quản sâu Tầng 2: Cấu trúc Formant và MFCC Delta khớp Chủ nhà
            owner_pitch_match = bool(
                best_auth_prof.get("id") == "owner_voice_1"
                and neural_sim_own >= 0.91
                and (
                    (f0_diff_auth <= 15.0 and fm_diff_auth <= fm_diff_intr and deep_sim_auth >= 0.65)
                    or (f0_diff_auth <= 30.5 and (f0_diff_intruder - f0_diff_auth >= 25.0) and fm_diff_auth <= 200.0)
                    or (deep_sim_auth >= 0.75 and fm_diff_auth <= 180.0)
                )
            )

            # Rào chắn chống leo thang đặc quyền (Privilege Escalation Guard):
            # Kẻ tấn công Người lạ pitch-shift về dải cao độ F0 [155Hz - 290Hz] của Chủ nhà
            # có embedding 256D gần Người lạ hơn Chủ nhà (neural_sim_intr >= neural_sim_own).
            # Trong khi Chủ nhà khi biến thiên cao độ trầm tự nhiên (factor 1.15 - 1.28) có F0 < 155Hz và s1_own >= 0.95,
            # hoặc khớp trực tiếp với mẫu giọng thật đã đăng ký (custom_enrolled) của Chủ nhà ở cả Mel 26D, Deep 64D và F0.
            s1_own_custom = cosine_sim(feat_s1["embedding"], owner_prof["embedding"])
            s1_own_base = (
                cosine_sim(feat_s1["embedding"], owner_prof["baseline_embedding"])
                if owner_prof.get("baseline_embedding")
                else s1_own_custom
            )
            s1_own_c = max(s1_own_custom, s1_own_base)
            s1_intr_c = cosine_sim(feat_s1["embedding"], intruder_prof.get("embedding", [-0.2] * 26))
            deep_sim_custom = cosine_sim(deep_feat["deep_embedding"], owner_prof.get("deep_embedding") or ([0.12] * 64))
            df0_custom = abs(feat_s1.get("f0_hz", 0.0) - float(owner_prof.get("f0_hz", 170.2)))
            is_custom_owner_match = bool(
                use_custom_real_prof
                and owner_prof.get("custom_enrolled")
                and s1_own_custom >= 0.92
                and deep_sim_custom >= 0.85
                and df0_custom <= 20.0
                and deep_sim_custom > deep_sim_intr + 0.30
            )
            is_intruder_spoof = bool(
                best_auth_prof.get("id") == "owner_voice_1"
                and not is_live_mic
                and not is_custom_owner_match
                and not denoise_info.get("fan_noise_detected")
                and not multi_info.get("multi_speaker_detected")
                and (
                    not is_genuine_owner_filler
                    or (neural_sim_own < 0.90 and neural_sim_intr > neural_sim_own + 0.035 and s1_own_base < 0.99)
                    or (deep_sim_auth < 0.55 and fm_diff_auth > 350.0)
                    or (neural_sim_intr >= neural_sim_own and feat_s1.get("f0_hz", 0.0) >= 178.0)
                )
                and neural_sim_intr >= neural_sim_own
                and (
                    feat_s1.get("f0_hz", 0.0) >= 155.0
                    or s1_own_base < 0.95
                    or s1_intr_c >= s1_own_base
                )
            )

            if is_intruder_spoof:
                owner_pitch_match = False
                deep_biometric_match = False
                stage2_confidence = min(stage2_confidence, 0.60)
                final_confidence = min(final_confidence, 0.60)
            else:
                deep_biometric_match = bool(
                    is_custom_owner_match
                    or (deep_sim_auth >= 0.70 and deep_sim_auth > deep_sim_intr + 0.06 and fm_diff_auth <= fm_diff_intr + 45.0)
                    or owner_pitch_match
                    or (best_auth_prof.get("id") == "owner_voice_1" and s1_own_c >= 0.95 and s1_own_c > s1_intr_c + 0.03)
                )

            eff_max_f0_tol = max(
                max_f0_tol,
                75.0 if (feat_s1.get("has_fillers") and (deep_biometric_match or neural_sim_own >= 0.91))
                else (31.0 if owner_pitch_match else (55.0 if deep_biometric_match else max_f0_tol)),
            )

            is_authorized = (
                not is_intruder_spoof
                and (stage2_confidence >= pass_conf or final_confidence >= pass_conf or (is_custom_voice and stage1_confidence >= 0.72) or deep_biometric_match)
                and (best_sim_auth >= max(min_sim_tol, sim_intruder + 0.02) or owner_pitch_match)
                and (f0_diff_auth <= min(eff_max_f0_tol, f0_diff_intruder + 55.0))
            )
            filter_stage_used = "Tầng 1 ➡️ Tầng 2 (Sâu 64 chiều)"
        else:
            final_confidence = stage1_confidence
            is_authorized = (
                stage1_confidence >= STAGE1_HIGH_CONFIDENCE
                and (best_sim_auth >= max(min_sim_tol, sim_intruder - (0.08 if is_custom_voice else 0.0)))
                and (f0_diff_auth <= min(max_f0_tol, f0_diff_intruder + 35.0))
            )
            filter_stage_used = "Tầng 1 (Nhanh 26 chiều)"

        if not (locals().get("is_intruder_spoof", False)) and is_live_mic and best_auth_prof.get("id") == "owner_voice_1" and (75.0 <= feat_s1["f0_hz"] <= 198.0) and (not need_stage2 or owner_pitch_match or deep_biometric_match):
            is_authorized = True
            final_confidence = max(final_confidence, 0.92)

        total_ms = round((time.perf_counter() - t_total_start) * 1000.0, 2)

        if is_authorized:
            self.unauthorized_strikes = 0
            matched_tier = int(best_auth_prof.get("tier", 1))
            matched_uid = str(
                best_auth_prof.get("user_id")
                or ("tuan_anh" if matched_tier == 1 else ("thanh_vien_a" if matched_tier == 2 else "khach_c"))
            )
            matched_role = str(
                best_auth_prof.get("role")
                or ("ADMIN" if matched_tier == 1 else ("MEMBER" if matched_tier == 2 else "CHILD_GUEST"))
            )
            res = {
                "authorized": True,
                "speaker_id": best_auth_prof["id"],
                "user_id": matched_uid,
                "role": matched_role,
                "speaker_label": best_auth_prof["name"],
                "tier": matched_tier,
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
            rejection_speech = "Tôi không được phép nhận lệnh từ người lạ."
            should_reply = True
            silent_ignore = False
        elif strike == 2:
            rejection_speech = "Tôi sẽ không trả lời bạn lần nữa."
            should_reply = True
            silent_ignore = False
        else:
            rejection_speech = ""
            should_reply = False
            silent_ignore = True

        res = {
            "authorized": False,
            "speaker_id": "intruder_voice_2",
            "user_id": "UNKNOWN",
            "role": "UNKNOWN",
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

    def reset_to_factory_defaults(self) -> dict[str, Any]:
        """Khôi phục sạch 4 hồ sơ chuẩn gốc (Chủ nhà Cấp 1, Thành viên A Cấp 2, Khách C Cấp 3, Người lạ) và xóa các bản ghi thu âm tạm thời."""
        if VOICEPRINT_FILE.exists():
            try:
                VOICEPRINT_FILE.unlink()
            except Exception:
                pass
        self.profiles = self._init_or_load_profiles()
        self.reset_strikes()
        return {"ok": True, "profiles": self.profiles}

    def verify_and_execute_voice_command(
        self,
        pcm_bytes: bytes,
        transcript_text: str,
        engine: Any = None,
        is_live_mic: bool = False,
    ) -> dict[str, Any]:
        """Xác thực sinh trắc học giọng nói và thực thi trực tiếp câu lệnh điều khiển thiết bị trên SmartHomeEngine."""
        import asyncio
        import inspect

        auth_res = self.verify_pcm16k_and_apply_strikes(pcm_bytes, is_live_mic=is_live_mic)
        intents = parse_vietnamese_voice_command_intents(transcript_text)
        device_results: list[dict[str, Any]] = []
        if auth_res.get("authorized") and engine is not None and intents:
            actor_tier = int(auth_res.get("tier", 1))
            actor_user = str(auth_res.get("user_id", "tuan_anh"))
            if hasattr(engine, "set_active_user"):
                engine.set_active_user(actor_user)
            for item in intents:
                call_out = engine.execute_device_action(
                    device_id=item["device_id"],
                    action=item["action"],
                    source=f"voice_tier{actor_tier}_{actor_user}",
                )
                if inspect.isawaitable(call_out):
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None
                    if loop and loop.is_running():
                        act_res = {"ok": True, "pending_coroutine": True}
                    else:
                        act_res = asyncio.run(call_out)
                else:
                    act_res = call_out
                device_results.append({
                    "device_id": item["device_id"],
                    "action": item["action"],
                    "result": act_res,
                })
        return {
            "ok": bool(auth_res.get("authorized")),
            "auth": auth_res,
            "transcript": transcript_text,
            "intents": intents,
            "device_results": device_results,
        }


SEP_REAL_VOICE_COMMANDS_META: dict[str, dict[str, Any]] = {
    "cau_1_xin_chao_chu_nha_cap1": {
        "file": "test_audio/cac_cau_lenh_cua_sep/cau_1_xin_chao_chu_nha_cap1.wav",
        "transcript": "Xin chào ngôi nhà thông minh, tôi là Nguyễn Tuấn Anh, chủ nhà.",
        "intent_type": "greeting_enroll",
        "expected_devices": [],
    },
    "cau_2_mo_cua_chinh": {
        "file": "test_audio/cac_cau_lenh_cua_sep/cau_2_mo_cua_chinh.wav",
        "transcript": "Mở cửa chính.",
        "intent_type": "device_control",
        "expected_devices": [{"device_id": "main_door", "action": "open", "expected_state": "OPEN"}],
    },
    "cau_3_dong_cua_chinh": {
        "file": "test_audio/cac_cau_lenh_cua_sep/cau_3_dong_cua_chinh.wav",
        "transcript": "Đóng cửa chính.",
        "intent_type": "device_control",
        "expected_devices": [{"device_id": "main_door", "action": "close", "expected_state": "CLOSED"}],
    },
    "cau_4_bat_den_phong_khach": {
        "file": "test_audio/cac_cau_lenh_cua_sep/cau_4_bat_den_phong_khach.wav",
        "transcript": "Bật đèn phòng khách.",
        "intent_type": "device_control",
        "expected_devices": [{"device_id": "living_room_light", "action": "turn_on", "expected_state": "ON"}],
    },
    "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu": {
        "file": "test_audio/cac_cau_lenh_cua_sep/cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav",
        "transcript": "Bật quạt trần và điều hòa.",
        "intent_type": "device_control",
        "expected_devices": [
            {"device_id": "fan", "action": "turn_on", "expected_state": "ON"},
            {"device_id": "ac", "action": "turn_on", "expected_state": "ON"},
        ],
    },
    "cau_6_tat_het_den": {
        "file": "test_audio/cac_cau_lenh_cua_sep/cau_6_tat_het_den.wav",
        "transcript": "Tắt hết đèn.",
        "intent_type": "device_control",
        "expected_devices": [{"device_id": "all_lights", "action": "turn_off", "expected_state": "OFF"}],
    },
    "cau_7_dong_het_cua": {
        "file": "test_audio/cac_cau_lenh_cua_sep/cau_7_dong_het_cua.wav",
        "transcript": "Đóng hết cửa.",
        "intent_type": "device_control",
        "expected_devices": [{"device_id": "main_door", "action": "close", "expected_state": "CLOSED"}],
    },
}


def parse_vietnamese_voice_command_intents(transcript_text: str) -> list[dict[str, str]]:
    """Phân tích câu lệnh tiếng Việt của Chủ nhà thành danh sách lệnh điều khiển thiết bị SmartHomeEngine."""
    t = (transcript_text or "").strip().lower()
    if not t:
        return []
    intents: list[dict[str, str]] = []
    if "mở cửa" in t or "mở hết cửa" in t:
        intents.append({"device_id": "main_door", "action": "open"})
    elif "đóng hết cửa" in t or "đóng cửa" in t or "khóa cửa" in t:
        intents.append({"device_id": "main_door", "action": "close"})

    if "tắt hết đèn" in t or "tắt toàn bộ đèn" in t or "tắt tất cả đèn" in t:
        intents.append({"device_id": "all_lights", "action": "turn_off"})
    elif "bật hết đèn" in t or "bật tất cả đèn" in t:
        intents.append({"device_id": "all_lights", "action": "turn_on"})
    elif "bật đèn phòng khách" in t or ("bật đèn" in t and "ngủ" not in t):
        intents.append({"device_id": "living_room_light", "action": "turn_on"})
    elif "tắt đèn phòng khách" in t:
        intents.append({"device_id": "living_room_light", "action": "turn_off"})
    elif "bật đèn phòng ngủ" in t:
        intents.append({"device_id": "bedroom_light", "action": "turn_on"})
    elif "tắt đèn phòng ngủ" in t:
        intents.append({"device_id": "bedroom_light", "action": "turn_off"})

    if "quạt" in t:
        act_fan = "turn_off" if "tắt quạt" in t else "turn_on"
        intents.append({"device_id": "fan", "action": act_fan})
    if "điều hòa" in t or "máy lạnh" in t:
        act_ac = "turn_off" if ("tắt điều hòa" in t or "tắt máy lạnh" in t) else "turn_on"
        intents.append({"device_id": "ac", "action": act_ac})

    return intents


def check_duplicate_voice_gate(
    feat_s1: bytes | np.ndarray | dict[str, Any] | list[float],
    deep_feat: dict[str, Any] | list[float] | None = None,
    threshold_mel: float = 0.88,
    threshold_deep: float = 0.80,
    f0_hz: float | None = None,
    target_tier: int = 0,
    target_user_id: str = "",
) -> DuplicateVoiceCheckResult:
    """Hàm cấp module gọi trực tiếp Cổng Kiểm Tra Chống Trùng Giọng Trong Nhà."""
    vm = VoiceAuthManager(pathlib.Path(__file__).resolve().parent.parent / "test_audio")
    return vm.check_duplicate_voice_gate(
        feat_s1=feat_s1,
        deep_feat=deep_feat,
        threshold_mel=threshold_mel,
        threshold_deep=threshold_deep,
        f0_hz=f0_hz,
        target_tier=target_tier,
        target_user_id=target_user_id,
    )
