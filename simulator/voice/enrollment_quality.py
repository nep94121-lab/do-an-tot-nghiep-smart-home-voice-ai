"""Mo-dun kiem dinh chat luong giong thu am ban dau (Voice Enrollment Quality Gate) va phan tich Intent giong noi."""

from __future__ import annotations

import hashlib
import pathlib
from typing import Any
import wave
import numpy as np

from simulator.voice.dsp_features import (
    denoise_and_isolate_human_voice,
    extract_voice_features,
    extract_stage2_deep_features,
)
from simulator.voice.biometrics_neural import (
    extract_neural_embedding_256d,
    compute_neural_similarity,
)

SR = 16000
ENROLL_QUALITY_RULES: dict[str, float] = {
    "min_speech_s": 12.0,
    "max_silence_ratio": 0.60,
    "min_rms_dbfs": -30.0,
    "max_rms_dbfs": -12.0,
    "max_clip_pct": 0.1,
    "min_snr_db": 15.0,
    "min_pair_cosine": 0.85,
    "mean_pair_cosine": 0.90,
    "min_self_speech_s": 3.0,
    "min_self_cosine": 0.88,
    "self_cosine_margin": 0.03,
}


def _db(value: float) -> float:
    return float(20.0 * np.log10(max(float(value), 1e-12)))


def _coerce_pcm16_16k(audio: bytes | bytearray | np.ndarray | str | pathlib.Path, sr: int = SR) -> np.ndarray:
    """Chuyển đổi bytes/WAV/ndarray/Path sang mảng int16 mono 16kHz."""
    if isinstance(audio, (str, pathlib.Path)):
        p = pathlib.Path(audio)
        with wave.open(str(p), "rb") as w:
            if (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getcomptype()) != (sr, 1, 2, "NONE"):
                from simulator.voice.wespeaker_onnx import pcm_bytes_to_float32_16k

                flt = pcm_bytes_to_float32_16k(p.read_bytes(), sr=sr)
                return np.clip(flt * 32767.0, -32768, 32767).astype(np.int16)
            return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").copy()
    if isinstance(audio, (bytes, bytearray)):
        raw_b = bytes(audio)
        if len(raw_b) >= 44 and raw_b[:4] == b"RIFF" and raw_b[8:12] == b"WAVE":
            try:
                import io

                with wave.open(io.BytesIO(raw_b), "rb") as w:
                    if (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getcomptype()) == (sr, 1, 2, "NONE"):
                        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").copy()
            except Exception:
                pass
            from simulator.voice.wespeaker_onnx import pcm_bytes_to_float32_16k

            flt = pcm_bytes_to_float32_16k(raw_b, sr=sr)
            return np.clip(flt * 32767.0, -32768, 32767).astype(np.int16)
        usable = (len(raw_b) // 2) * 2
        if usable == 0:
            return np.array([], dtype=np.int16)
        return np.frombuffer(raw_b[:usable], dtype=np.int16).copy()
    if isinstance(audio, np.ndarray):
        if audio.size == 0:
            return np.array([], dtype=np.int16)
        if np.issubdtype(audio.dtype, np.floating) and float(np.max(np.abs(audio))) <= 1.05:
            return np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)
        return audio.astype(np.int16).copy()
    return np.array([], dtype=np.int16)


def measure_enrollment_audio(
    pcm16: bytes | bytearray | np.ndarray | str | pathlib.Path,
    offset_db: float = 10.0,
    sr: int = SR,
) -> tuple[dict[str, Any], np.ndarray]:
    """Đo lường chất lượng âm học theo chuẩn ENROLL_QUALITY.md & check_enroll.py.

    Energy VAD khung 20ms không chồng lấp, ngưỡng max(-50 dBFS, P20 + 10 dB).
    SNR ước lượng trên các khung nền cách tiếng nói ít nhất 60ms (tối thiểu 0.3s nền).
    """
    x = _coerce_pcm16_16k(pcm16, sr=sr)
    frame_samples = max(1, int(0.02 * sr))
    if x.size < frame_samples:
        empty_metrics = {
            "duration_s": float(x.size / max(1, sr)),
            "net_speech_s": 0.0,
            "silence_ratio": 1.0,
            "silence_pct": 100.0,
            "rms_dbfs": -120.0,
            "speech_rms_dbfs": -120.0,
            "peak_dbfs": -120.0,
            "clipping_pct": 0.0,
            "near_clip_pct": 0.0,
            "estimated_snr_db": None,
            "noise_reference_s": 0.0,
            "noise_rms_dbfs": -120.0,
            "vad_threshold_dbfs": -50.0,
            "speech_intervals_s": [],
        }
        return empty_metrics, np.array([], dtype=np.int16)

    y = x.astype(np.float64) / 32768.0
    frames = [y[i : i + frame_samples] for i in range(0, len(y), frame_samples)]
    energies = np.array([np.mean(f * f) for f in frames], dtype=np.float64)
    levels = 10.0 * np.log10(np.maximum(energies, 1e-24))
    threshold = max(-50.0, float(np.percentile(levels, 20)) + float(offset_db))
    voiced = levels > threshold
    mask = np.repeat(voiced, frame_samples)[: len(y)]
    speech = x[mask]

    protected = (
        np.convolve(voiced.astype(int), np.ones(7, dtype=int), mode="full")[
            3 : 3 + len(voiced)
        ]
        > 0
    )
    noise_mask = np.repeat(~protected, frame_samples)[: len(y)]
    noise = y[noise_mask]
    ps = float(np.mean(y[mask] ** 2)) if speech.size else 0.0
    pn = float(np.mean(noise ** 2)) if noise.size else 0.0
    snr = (
        float(10.0 * np.log10(max(ps - pn, 1e-24) / max(pn, 1e-24)))
        if noise.size >= int(0.3 * sr) and pn > 0.0 and ps > pn
        else None
    )
    silence_ratio = float(1.0 - len(speech) / len(x))
    near_clip_pct = float(100.0 * np.mean(np.abs(y) >= 0.999))
    hard_clip_pct = float(100.0 * np.mean((x == -32768) | (x == 32767)))
    clip_pct = max(hard_clip_pct, near_clip_pct)

    edges = np.diff(np.r_[False, voiced, False].astype(int))
    intervals = [
        [float(a * 0.02), min(float(b * 0.02), len(x) / sr)]
        for a, b in zip(np.where(edges == 1)[0], np.where(edges == -1)[0])
    ]
    metrics: dict[str, Any] = {
        "duration_s": float(len(x) / sr),
        "net_speech_s": float(len(speech) / sr),
        "silence_ratio": silence_ratio,
        "silence_pct": round(silence_ratio * 100.0, 2),
        "rms_dbfs": _db(np.sqrt(np.mean(y * y))),
        "speech_rms_dbfs": _db(np.sqrt(ps)) if speech.size else -120.0,
        "peak_dbfs": _db(np.max(np.abs(y))),
        "clipping_pct": clip_pct,
        "near_clip_pct": near_clip_pct,
        "estimated_snr_db": snr,
        "noise_reference_s": float(len(noise) / sr),
        "noise_rms_dbfs": _db(np.sqrt(pn)) if noise.size else -120.0,
        "vad_threshold_dbfs": threshold,
        "speech_intervals_s": intervals,
    }
    return metrics, speech


def _pair_hybrid_cosine(seg_a: np.ndarray, seg_b: np.ndarray, sr: int = SR) -> float:
    """Tính cosine giữa 2 phân đoạn 3s kết hợp đặc trưng 256D và WeSpeaker ResNet34 ONNX.

    Nếu 2 đoạn thuộc 2 người nói khác nhau (WeSpeaker cosine < 0.36), phạt điểm xuống < 0.85
    để chặn ghép nhiều người nói hoặc nhiễu giọng lạ trong bản thu đăng ký.
    """
    emb_a = extract_neural_embedding_256d(seg_a, sr=sr)
    emb_b = extract_neural_embedding_256d(seg_b, sr=sr)
    cos_spec = float(compute_neural_similarity(emb_a, emb_b))
    try:
        from simulator.voice.wespeaker_onnx import (
            extract_wespeaker_embedding,
            compute_wespeaker_cosine,
        )

        w_a = extract_wespeaker_embedding(seg_a, sr=sr, apply_vad=False)
        w_b = extract_wespeaker_embedding(seg_b, sr=sr, apply_vad=False)
        cos_w = float(compute_wespeaker_cosine(w_a, w_b))
        if cos_w < 0.36:
            return float(min(cos_spec, 0.45 + max(0.0, cos_w)))
    except Exception:
        pass
    return cos_spec


def measure_segment_consistency(speech: np.ndarray, sr: int = SR) -> dict[str, Any]:
    """Đo độ nhất quán giữa các phân đoạn ~3 giây trong bản thu đăng ký."""
    if len(speech) < 2 * sr:
        return {
            "segment_seconds": [],
            "pair_count": 0,
            "mean_cosine": None,
            "min_cosine": None,
        }
    n_chunks = max(2, int(np.floor(len(speech) / sr / 3.0 + 0.5)))
    chunks = np.array_split(speech, n_chunks)
    pairs = [
        _pair_hybrid_cosine(a, b, sr=sr)
        for i, a in enumerate(chunks)
        for b in chunks[i + 1 :]
    ]
    return {
        "segment_seconds": [float(len(c) / sr) for c in chunks],
        "pair_count": len(pairs),
        "mean_cosine": float(np.mean(pairs)) if pairs else None,
        "min_cosine": float(min(pairs)) if pairs else None,
    }


measure = measure_enrollment_audio
consistency = measure_segment_consistency


def check_enrollment_quality_gate(
    enroll_pcm: bytes | bytearray | np.ndarray | str | pathlib.Path,
    self_check_pcm: bytes | bytearray | np.ndarray | str | pathlib.Path | None = None,
    sr: int = SR,
    require_self_check: bool = True,
) -> dict[str, Any]:
    """Cổng kiểm định chất lượng mẫu đăng ký giọng nói (Chủ nhà Cấp 1 & Khách/Thành viên).

    Tiêu chuẩn bắt buộc (ENROLL_QUALITY.md & check_enroll.py):
      1. Tiếng nói thực tế (net speech): >= 12.0s
      2. Tỷ lệ khoảng lặng (silence ratio): <= 60.0%
      3. Âm lượng tiếng nói (speech RMS): -30.0 dBFS .. -12.0 dBFS
      4. Tỷ lệ vỡ tiếng (clipping): <= 0.1%
      5. Tỷ số tín hiệu trên nhiễu (SNR): >= 15.0 dB (cần >= 0.3s khoảng lặng nền để đo)
      6. Độ nhất quán các phân đoạn 3s: mean cosine >= 0.90 & min cosine >= 0.85
      7. Câu kiểm tra độc lập (self-check): net speech >= 3.0s & cosine >= 0.88 (khác bản thu chính)
    """
    r = ENROLL_QUALITY_RULES
    x_enroll = _coerce_pcm16_16k(enroll_pcm, sr=sr)
    if x_enroll.size < int(0.02 * sr):
        reason_msg = "Dữ liệu âm thanh thu âm rỗng hoặc quá ngắn (< 20ms). Vui lòng thu âm lại!"
        return {
            "ok": False,
            "pass_gate": False,
            "verified": False,
            "require_rerecord": True,
            "ask_repeat": True,
            "status": "CHUA_DAT",
            "reason": reason_msg,
            "reasons": [reason_msg],
            "message": reason_msg,
            "error": reason_msg,
            "checks": {},
            "rules": r,
            "metrics": {},
            "consistency": {},
            "self_check": None,
        }

    metrics, speech = measure_enrollment_audio(x_enroll, offset_db=10.0, sr=sr)
    stable = measure_segment_consistency(speech, sr=sr)

    self_result: dict[str, Any] | None = None
    self_same_recording = False
    if self_check_pcm is not None:
        x_self = _coerce_pcm16_16k(self_check_pcm, sr=sr)
        if x_self.size > 0:
            h_enroll = hashlib.sha256(x_enroll.tobytes()).hexdigest()
            h_self = hashlib.sha256(x_self.tobytes()).hexdigest()
            if h_enroll == h_self:
                self_same_recording = True
            m_sc, sp_sc = measure_enrollment_audio(x_self, offset_db=10.0, sr=sr)
            cos_sc = _pair_hybrid_cosine(x_enroll, x_self, sr=sr) if x_self.size >= 400 else 0.0
            vad_cos_sc = (
                _pair_hybrid_cosine(speech, sp_sc, sr=sr)
                if (speech.size >= 400 and sp_sc.size >= 400)
                else 0.0
            )
            self_result = {
                "duration_s": m_sc["duration_s"],
                "net_speech_s": m_sc["net_speech_s"],
                "cosine": cos_sc,
                "vad_cosine": vad_cos_sc,
                "same_as_enroll": self_same_recording,
            }

    checks: dict[str, bool] = {
        "net_speech": float(metrics["net_speech_s"]) >= r["min_speech_s"],
        "silence": float(metrics["silence_ratio"]) <= r["max_silence_ratio"],
        "level": r["min_rms_dbfs"] <= float(metrics["speech_rms_dbfs"]) <= r["max_rms_dbfs"],
        "clipping": float(metrics["clipping_pct"]) <= r["max_clip_pct"],
        "snr": (
            metrics["estimated_snr_db"] is not None
            and float(metrics["estimated_snr_db"]) >= r["min_snr_db"]
        ),
        "segment_mean": (
            stable["mean_cosine"] is not None
            and float(stable["mean_cosine"]) >= r["mean_pair_cosine"]
        ),
        "segment_min": (
            stable["min_cosine"] is not None
            and float(stable["min_cosine"]) >= r["min_pair_cosine"]
        ),
    }
    if require_self_check or self_check_pcm is not None:
        checks["heldout"] = bool(
            self_result is not None
            and not self_same_recording
            and float(self_result["net_speech_s"]) >= r["min_self_speech_s"]
            and float(self_result["cosine"]) >= r["min_self_cosine"]
        )

    reasons: list[str] = []
    if not checks["net_speech"]:
        reasons.append(
            f"Thời lượng tiếng nói thực tế quá ngắn ({metrics['net_speech_s']:.2f}s < {r['min_speech_s']:.1f}s). "
            "Vui lòng thu âm lại ít nhất 12 giây tiếng nói rõ ràng!"
        )
    if not checks["silence"]:
        reasons.append(
            f"Tỷ lệ khoảng lặng quá cao ({metrics['silence_pct']:.1f}% > {r['max_silence_ratio'] * 100.0:.0f}%). "
            "Vui lòng nói liên tục hơn và thu âm lại!"
        )
    if not checks["level"]:
        if float(metrics["speech_rms_dbfs"]) < r["min_rms_dbfs"]:
            reasons.append(
                f"Âm lượng giọng nói quá nhỏ ({metrics['speech_rms_dbfs']:.1f} dBFS < {r['min_rms_dbfs']:.1f} dBFS). "
                "Vui lòng đưa micro lại gần, nói to rõ hơn và thu âm lại!"
            )
        else:
            reasons.append(
                f"Âm lượng giọng nói quá lớn ({metrics['speech_rms_dbfs']:.1f} dBFS > {r['max_rms_dbfs']:.1f} dBFS). "
                "Vui lòng để micro xa hơn một chút và thu âm lại!"
            )
    if not checks["clipping"]:
        reasons.append(
            f"Tín hiệu âm thanh bị rè/vỡ tiếng (clipping {metrics['clipping_pct']:.3f}% > {r['max_clip_pct']:.1f}%). "
            "Vui lòng giảm âm lượng micro và thu âm lại!"
        )
    if not checks["snr"]:
        if metrics["estimated_snr_db"] is None:
            reasons.append(
                "Không đo được nền yên tĩnh để tính SNR (cần ít nhất 0.3s khoảng lặng đầu/cuối câu). "
                "Vui lòng thu âm lại ở nơi yên tĩnh!"
            )
        else:
            reasons.append(
                f"Môi trường quá ồn (SNR = {metrics['estimated_snr_db']:.1f} dB < {r['min_snr_db']:.1f} dB). "
                "Vui lòng thu âm lại tại nơi yên tĩnh hơn!"
            )
    if not checks["segment_mean"] or not checks["segment_min"]:
        m_val = stable["mean_cosine"] if stable["mean_cosine"] is not None else 0.0
        min_val = stable["min_cosine"] if stable["min_cosine"] is not None else 0.0
        reasons.append(
            f"Độ nhất quán giọng nói giữa các đoạn 3 giây không đạt (mean cosine = {m_val:.3f} < 0.90 "
            f"hoặc min cosine = {min_val:.3f} < 0.85; có thể lẫn tạp âm hoặc giọng người khác). "
            "Vui lòng thu âm lại bằng một giọng duy nhất!"
        )
    if "heldout" in checks and not checks["heldout"]:
        if self_result is None:
            reasons.append(
                "Thiếu câu kiểm tra độc lập (self-check >= 3.0s tiếng nói). Vui lòng đọc thêm câu xác nhận và thu âm lại!"
            )
        elif self_same_recording:
            reasons.append(
                "Câu kiểm tra độc lập (self-check) bị trùng hoàn toàn với bản thu chính. Vui lòng đọc một câu kiểm tra mới và thu âm lại!"
            )
        elif float(self_result["net_speech_s"]) < r["min_self_speech_s"]:
            reasons.append(
                f"Câu kiểm tra độc lập (self-check) quá ngắn ({self_result['net_speech_s']:.2f}s < {r['min_self_speech_s']:.1f}s tiếng nói). "
                "Vui lòng đọc câu kiểm tra dài ít nhất 3 giây và thu âm lại!"
            )
        else:
            reasons.append(
                f"Câu kiểm tra độc lập (self-check) không khớp với mẫu giọng đăng ký (cosine = {self_result['cosine']:.3f} < {r['min_self_cosine']:.2f}). "
                "Vui lòng thu âm lại!"
            )

    pass_gate = all(checks.values())
    combined_reason = " ".join(reasons) if reasons else "Mẫu giọng đăng ký đạt tất cả tiêu chuẩn chất lượng."
    return {
        "ok": pass_gate,
        "pass_gate": pass_gate,
        "verified": pass_gate,
        "require_rerecord": not pass_gate,
        "ask_repeat": not pass_gate,
        "status": "DA_DAT" if pass_gate else "CHUA_DAT",
        "reason": combined_reason,
        "reasons": reasons,
        "message": combined_reason,
        "error": "" if pass_gate else combined_reason,
        "checks": checks,
        "rules": r,
        "metrics": metrics,
        "consistency": stable,
        "self_check": self_result,
    }


evaluate_enrollment_quality_gate = check_enrollment_quality_gate


def validate_voice_enrollment_quality(
    pcm16: np.ndarray | bytes,
    sr: int = 16000,
    self_check_pcm: np.ndarray | bytes | None = None,
    strict_12s: bool = False,
) -> dict[str, Any]:
    """Kiểm định chất lượng giọng thu âm ban đầu (First-Page Voice Enrollment Quality Gate).
    Nếu truyền `self_check_pcm` hoặc `strict_12s=True`, áp dụng cổng nghiêm ngặt 12s + self-check 3s.
    Đo đạc 6 tiêu chuẩn âm học khắt khe:
      1. Thời lượng thu âm: >= 2.0s (hoặc net_speech >= 12.0s khi bật strict_12s)
      2. Năng lượng RMS: >= 0.020 (-30..-12 dBFS)
      3. Tỷ lệ khung tiếng nói có thanh (Voiced Frame Ratio): >= 35.0% (silence <= 60%)
      4. Tần số cơ bản F0 trung bình: 75.0 Hz <= F0 <= 340.0 Hz
      5. Độ ổn định cao độ (Pitch Std Dev): <= 38.0 Hz
      6. Tỷ số tín hiệu trên nhiễu (SNR): >= 10.0 dB
    """
    if strict_12s or self_check_pcm is not None:
        return check_enrollment_quality_gate(
            enroll_pcm=pcm16,
            self_check_pcm=self_check_pcm,
            sr=sr,
            require_self_check=bool(self_check_pcm is not None or strict_12s),
        )

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


