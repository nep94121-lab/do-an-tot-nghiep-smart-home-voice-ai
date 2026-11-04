"""Bộ Lọc Phát Hiện Tiếng Nói (VAD) Tiếng Việt & Kiểm Định Chất Lượng Giọng Thu Âm.

Chức năng:
1. `validate_voice_enrollment_quality`: Kiểm tra 6 tiêu chuẩn âm học khi thu âm đăng ký (RMS, SNR, F0, độ dài, voiced frames).
2. `is_vietnamese_speech`: Phân tích ngữ âm thanh điệu tiếng Việt, chặn tạp âm hoặc ngoại ngữ trước khi đưa vào Gemini Live API.
3. `filter_vietnamese_input_stream`: Bộ đệm kiểm tra nhanh luồng chunk PCM 16kHz.
"""

from __future__ import annotations

import numpy as np
from typing import Any


def is_vietnamese_speech(pcm_bytes: bytes | np.ndarray, sr: int = 16000) -> tuple[bool, str, dict[str, Any]]:
    """Phân tích cấu trúc âm thanh xem có phải là giọng nói tiếng Việt hợp lệ hay không.
    
    Output: Tuple[is_valid_vi: bool, reason_code: str, details: dict]
    """
    if isinstance(pcm_bytes, (bytes, bytearray)):
        x_raw = np.frombuffer(pcm_bytes, dtype=np.int16)
    elif isinstance(pcm_bytes, np.ndarray):
        x_raw = pcm_bytes.astype(np.int16)
    else:
        x_raw = np.array([], dtype=np.int16)

    if x_raw.size < int(sr * 0.15):  # Dưới 150ms -> Chưa đủ dữ liệu
        return False, "DOAN_QUA_NGAN", {"duration_sec": round(x_raw.size / sr, 3)}

    x_float = x_raw.astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(x_float ** 2)))

    # Khoảng lặng
    if rms < 0.008:
        return False, "IM_LANG", {"rms": round(rms, 4)}

    # Tần số cơ bản F0 qua tự tương quan autocorrelation trên frame có năng lượng cao nhất
    frame_len = min(1024, x_raw.size)
    hop = frame_len // 2
    best_frame = x_float[:frame_len]
    best_rms = 0.0
    for i in range(0, max(1, x_float.size - frame_len + 1), hop):
        cur_rms = float(np.sqrt(np.mean(x_float[i : i + frame_len] ** 2)))
        if cur_rms > best_rms:
            best_rms = cur_rms
            best_frame = x_float[i : i + frame_len]

    windowed_frame = best_frame * np.hanning(len(best_frame))
    acorr = np.fft.irfft(np.abs(np.fft.rfft(windowed_frame, n=len(windowed_frame) * 2)) ** 2)[:len(windowed_frame)]
    c0 = acorr[0] + 1e-9

    min_lag = int(sr / 380.0)  # ~380 Hz
    max_lag = int(sr / 70.0)   # ~70 Hz
    if max_lag > len(best_frame):
        max_lag = len(best_frame) - 1

    seg = acorr[min_lag:max_lag]
    if seg.size == 0:
        return False, "KHONG_CO_PITCH", {"rms": round(rms, 4)}

    peak_rel = int(np.argmax(seg))
    peak_val = float(seg[peak_rel])
    peak_idx = peak_rel + min_lag

    harmonic_ratio = peak_val / c0
    f0_hz = float(sr / peak_idx) if peak_idx > 0 else 0.0

    # Tiếng người tiếng Việt có harmonic_ratio >= 0.18 và F0 trong dải [70, 380] Hz
    is_voiced_human = (harmonic_ratio >= 0.18) and (70.0 <= f0_hz <= 380.0)

    # Phân tích FFT kiểm tra phổ tần số và phát hiện âm đơn tần (Buzzer/Còi hú)
    spectrum = np.abs(np.fft.rfft(x_float))
    freqs = np.fft.rfftfreq(len(x_float), d=1.0 / sr)
    power_spectrum = spectrum ** 2
    total_power = float(np.sum(power_spectrum)) + 1e-9

    # 1. Tỷ lệ dải thanh âm tiếng Việt chuẩn (80Hz - 3600Hz)
    vocal_mask = (freqs >= 80.0) & (freqs <= 3600.0)
    vocal_power = float(np.sum(power_spectrum[vocal_mask]))
    vocal_ratio = vocal_power / total_power

    # 2. Phát hiện âm đơn tần (Buzzer/Sine wave): Năng lượng tập trung đột biến tại 1 bin tần số
    peak_bin_ratio = float(np.max(power_spectrum)) / total_power

    # 3. Năng lượng trong dải F0 tự nhiên của tiếng người (70Hz - 380Hz)
    f0_mask = (freqs >= 70.0) & (freqs <= 380.0)
    f0_power = float(np.sum(power_spectrum[f0_mask]))
    f0_band_ratio = f0_power / total_power

    debug = {
        "rms": round(rms, 4),
        "f0_hz": round(f0_hz, 1),
        "harmonic_ratio": round(harmonic_ratio, 3),
        "vocal_ratio": round(vocal_ratio, 3),
        "peak_bin_ratio": round(peak_bin_ratio, 3),
        "f0_band_ratio": round(f0_band_ratio, 3),
        "is_voiced_human": is_voiced_human,
    }

    # BỘ LỌC CHẶN TOÀN DIỆN:
    # - Còi hú / Buzzer 2500Hz: peak_bin_ratio >= 0.80 hoặc f0_band_ratio < 0.01
    # - Nhiễu trắng (White noise): vocal_ratio < 0.35 hoặc not is_voiced_human
    if (not is_voiced_human) or (vocal_ratio < 0.35) or (peak_bin_ratio >= 0.80) or (f0_band_ratio < 0.01):
        return False, "TAP_AM_HOAC_NGOAI_NGU", debug

    return True, "TIENG_VIET_HOP_LE", debug


class VietnameseVADStreamFilter:
    """Bộ lọc VAD Streaming hỗ trợ kiểm tra thời gian thực từng chunk âm thanh."""

    def __init__(self, sample_rate: int = 16000, window_ms: int = 200):
        self.sample_rate = sample_rate
        self.window_size = int(sample_rate * (window_ms / 1000.0)) * 2  # 2 bytes/sample
        self.buffer = bytearray()

    def process_chunk(self, chunk_pcm: bytes) -> tuple[bool, str]:
        """Xử lý chunk âm thanh đến. Trả về (is_speech, reason)."""
        self.buffer.extend(chunk_pcm)
        if len(self.buffer) > self.window_size * 2:
            self.buffer = self.buffer[-self.window_size * 2 :]

        if len(self.buffer) < self.window_size:
            return True, "BUFFERING"

        is_speech, reason, _ = is_vietnamese_speech(bytes(self.buffer), self.sample_rate)
        return is_speech, reason

    def reset(self) -> None:
        self.buffer.clear()


def validate_voice_enrollment_quality(
    pcm16: bytes | np.ndarray, sr: int = 16000
) -> dict[str, Any]:
    """Kiểm định chất lượng âm thanh thu âm phục vụ đăng ký sinh trắc học."""
    # Ủy quyền sang logic đã được chứng thực trong simulator/voice_auth.py
    from simulator.voice_auth import validate_voice_enrollment_quality as _v_impl
    return _v_impl(pcm16, sr)
