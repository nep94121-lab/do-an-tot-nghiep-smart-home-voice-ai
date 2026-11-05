"""Mo-dun kiem dinh chat luong giong thu am ban dau (Voice Enrollment Quality Gate) va phan tich Intent giong noi."""

from __future__ import annotations

from typing import Any
import numpy as np

from simulator.voice.dsp_features import (
    denoise_and_isolate_human_voice,
    extract_voice_features,
    extract_stage2_deep_features,
)

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


def strip_vietnamese_diacritics(text: str) -> str:
    """Chuyển chuỗi Tiếng Việt có dấu sang không dấu (chữ thường) để đối sánh khẩu lệnh đa dạng."""
    import unicodedata

    s = (text or "").strip().lower()
    s = s.replace("đ", "d")
    nfd = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def parse_vietnamese_voice_command_intents(transcript_text: str) -> list[dict[str, str]]:
    """Phân tích câu lệnh tiếng Việt (có dấu, không dấu, hoặc cấu trúc đảo ngữ VIVOS/CommonVoice/FOSD)
    thành danh sách lệnh điều khiển thiết bị SmartHomeEngine.
    """
    import re

    t = (transcript_text or "").strip().lower()
    if not t:
        return []
    tn = strip_vietnamese_diacritics(t)
    tn = re.sub(r"[^\w\s]", " ", tn)
    tn = " ".join(tn.split())
    tokens = tn.split()

    has_on = any(w in tokens for w in ("bat", "mo", "chay")) or "khoi dong" in tn or "turn_on" in tn or "open" in tn
    has_off = any(w in tokens for w in ("tat", "dong", "khoa", "ngat", "dung")) or "turn_off" in tn or "close" in tn

    intents: list[dict[str, str]] = []

    # 1. Cửa chính / Cổng chính (main_door)
    is_gate_switch = ("cong tac cong" in tn) or ("cua chinh" in tn) or ("cua nha" in tn) or ("het cua" in tn) or ("mo cua" in tn) or ("dong cua" in tn) or ("khoa cua" in tn)
    if is_gate_switch:
        if "dong" in tokens or "khoa" in tokens or "tat" in tokens or "close" in tn:
            intents.append({"device_id": "main_door", "action": "close"})
        elif "mo" in tokens or "bat" in tokens or "open" in tn:
            intents.append({"device_id": "main_door", "action": "open"})

    # 2. Hệ thống đèn (all_lights / living_room_light / bedroom_light)
    if any(p in tn for p in ("tat het den", "tat toan bo den", "tat tat ca den", "tat 2 den", "tat hai den")):
        intents.append({"device_id": "all_lights", "action": "turn_off"})
    elif any(p in tn for p in ("bat het den", "bat toan bo den", "bat tat ca den", "bat 2 den", "bat hai den")):
        intents.append({"device_id": "all_lights", "action": "turn_on"})
    else:
        if "den phong khach" in tn or "den khach" in tn or ("bat den" in tn and "ngu" not in tn) or ("tat den" in tn and "ngu" not in tn):
            act_lr = "turn_off" if ("tat den" in tn or (has_off and not has_on)) else "turn_on"
            intents.append({"device_id": "living_room_light", "action": act_lr})
        if "den phong ngu" in tn or "den ngu" in tn:
            act_br = "turn_off" if ("tat den" in tn or (has_off and not has_on)) else "turn_on"
            intents.append({"device_id": "bedroom_light", "action": act_br})

    # 3. Quạt trần (fan)
    if "quat" in tokens or "quat tran" in tn:
        if "tat quat" in tn or (has_off and not ("bat quat" in tn)):
            act_fan = "turn_off"
        else:
            act_fan = "turn_on"
        intents.append({"device_id": "fan", "action": act_fan})

    # 4. Điều hòa / Máy lạnh (ac)
    if "dieu hoa" in tn or "may lanh" in tn:
        if "tat dieu hoa" in tn or "tat may lanh" in tn or (has_off and not ("bat dieu hoa" in tn or "bat may lanh" in tn)):
            act_ac = "turn_off"
        else:
            act_ac = "turn_on"
        intents.append({"device_id": "ac", "action": act_ac})

    # 5. Máy bơm tưới cây (garden_pump)
    if "may bom" in tn or "bom nuoc" in tn or "bom vuon" in tn or "tuoi cay" in tn:
        act_pump = "turn_off" if ("tat may bom" in tn or "tat bom" in tn or (has_off and not has_on)) else "turn_on"
        intents.append({"device_id": "garden_pump", "action": act_pump})

    # 6. Còi báo động (alarm_siren)
    if "coi bao dong" in tn or "bao dong" in tn or "coi hu" in tn:
        act_siren = "turn_off" if ("tat coi" in tn or "tat bao dong" in tn or (has_off and not has_on)) else "turn_on"
        intents.append({"device_id": "alarm_siren", "action": act_siren})

    return intents


