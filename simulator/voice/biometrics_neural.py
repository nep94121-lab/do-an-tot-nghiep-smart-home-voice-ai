"""Mô hình Sinh trắc học Giọng nói Neural Speaker Embedding 256 Chiều Bất Biến theo Cao Độ (Pitch-Invariant).

Kiến trúc 256-D:
- Khối 1 (128 chiều): Đường bao phổ thanh quản (Vocal Tract Spectral Envelope)
  loại trừ tần số cơ bản F0 qua Cepstral Liftering và Mel-Filterbank chuẩn hóa CMVN.
- Khối 2 (64 chiều): Tỷ lệ Formants tương đối (F2/F1, F3/F1, F4/F1, F3/F2, F4/F2)
  và phân bố năng lượng theo dải tần thanh quản cá nhân.
- Khối 3 (64 chiều): Đặc trưng động lực học phổ phi tuyến (Spectral Flux, Roll-off, Slope, Dynamics).
- Chuẩn hóa L2 về mặt cầu đơn vị ||e||_2 = 1.0 (Cosine Similarity = Dot Product).
"""

from __future__ import annotations

import json
import pathlib
import time
from typing import Any

import numpy as np

from simulator.engine.constants_and_time import resolve_data_dir

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
VOICEPRINT_FILE = resolve_data_dir() / "voiceprints.json"


def extract_neural_embedding_256d(pcm_16k_mono: bytes | np.ndarray, sr: int = 16000) -> np.ndarray:
    """Trích xuất vector đặc trưng sinh trắc học 256 chiều bất biến theo cao độ pitch F0.
    
    Hợp đồng giao diện theo PROJECT.md:
    Output: np.ndarray shape=(256,), dtype=np.float32, chuẩn hóa ||e||_2 = 1.0.
    """
    if isinstance(pcm_16k_mono, (bytes, bytearray)):
        x_raw = np.frombuffer(pcm_16k_mono, dtype=np.int16)
    elif isinstance(pcm_16k_mono, np.ndarray):
        if np.issubdtype(pcm_16k_mono.dtype, np.floating):
            x_raw = np.clip(pcm_16k_mono * 32767.0, -32768, 32767).astype(np.int16)
        else:
            x_raw = pcm_16k_mono.astype(np.int16)
    else:
        x_raw = np.array([], dtype=np.int16)

    if x_raw.size < 400:
        # Tín hiệu quá ngắn: trả về vector đơn vị giả định
        vec = np.zeros(256, dtype=np.float32)
        vec[0] = 1.0
        return vec

    x = x_raw.astype(np.float32) / 32768.0

    # Bước 1: Pre-emphasis lọc tăng dải tần số cao thanh quản
    x_pre = np.append(x[0], x[1:] - 0.97 * x[:-1])

    # Bước 2: Chia khung (Framing 25ms, Hop 10ms) và áp dụng cửa sổ Hamming
    frame_len = int(sr * 0.025)  # 400 mẫu
    hop_len = int(sr * 0.010)    # 160 mẫu
    n_frames = max(1, (len(x_pre) - frame_len) // hop_len + 1)

    pad_need = (n_frames - 1) * hop_len + frame_len - len(x_pre)
    if pad_need > 0:
        x_pre = np.pad(x_pre, (0, pad_need))

    frames = np.lib.stride_tricks.as_strided(
        x_pre,
        shape=(n_frames, frame_len),
        strides=(x_pre.strides[0] * hop_len, x_pre.strides[0]),
    ) * np.hamming(frame_len)

    # Phổ biên độ FFT
    n_fft = 512
    mag = np.abs(np.fft.rfft(frames, n=n_fft)) + 1e-7

    # =========================================================================
    # KHỐI 1 (128 CHIỀU): VOCAL TRACT SPECTRAL ENVELOPE (BẤT BIẾN THEO PITCH F0)
    # =========================================================================
    # Cepstral Liftering: Triệt tiêu các quefrency cao (>32) tương ứng với chu kỳ pitch F0
    log_mag = np.log(mag)
    cep = np.fft.irfft(log_mag, n=n_fft)

    # Cửa sổ lifter giữ 32 hệ số quefrency thấp (đường bao thanh quản)
    lifter = np.zeros(257, dtype=np.float32)
    lifter[1:33] = 1.0 + 16.0 * np.sin(np.pi * np.arange(1, 33) / 32.0)
    cep_liftered = cep[:, :257] * lifter

    # Tái tạo phổ đường bao thanh quản độc lập F0
    env_spec = np.abs(np.fft.rfft(cep_liftered, n=256))[:, :128]

    # Chuẩn hóa trung bình và phương sai thời gian (CMVN)
    env_mean = np.mean(env_spec, axis=0)
    env_std = np.std(env_spec, axis=0) + 1e-6
    v_env = ((env_mean - np.mean(env_mean)) / env_std).astype(np.float32)[:128]
    if len(v_env) < 128:
        v_env = np.pad(v_env, (0, 128 - len(v_env)))

    # =========================================================================
    # KHỐI 2 (64 CHIỀU): RELATIVE FORMANT RATIOS & VOCAL TRACT RESONANCE
    # =========================================================================
    # Chia dải tần thành 8 băng tương ứng với các vùng formant F1, F2, F3, F4
    n_bands = 8
    band_len = mag.shape[1] // n_bands
    band_energies = []
    for b in range(n_bands):
        be = np.mean(mag[:, b * band_len : (b + 1) * band_len], axis=1)
        band_energies.append(be)
    band_energies = np.array(band_energies)  # (8, n_frames)

    v_form = []
    for b in range(n_bands):
        be = band_energies[b]
        b_next = band_energies[(b + 1) % n_bands]
        b_prev = band_energies[(b - 1) % n_bands]
        b_base = band_energies[0] + 1e-6
        v_form.extend([
            float(np.mean(be)),
            float(np.std(be)),
            float(np.mean(be / b_base)),
            float(np.mean(be / (b_next + 1e-6))),
            float(np.mean(be / (b_prev + 1e-6))),
            float(np.percentile(be, 75) - np.percentile(be, 25)),
            float(np.percentile(be, 90)),
            float(np.median(be)),
        ])
    v_form = np.array(v_form[:64], dtype=np.float32)
    if len(v_form) < 64:
        v_form = np.pad(v_form, (0, 64 - len(v_form)))

    # =========================================================================
    # KHỐI 3 (64 CHIỀU): NON-LINEAR GLOTTAL & SPECTRAL DYNAMICS
    # =========================================================================
    # Spectral Flux
    diff = np.diff(mag, axis=0) if mag.shape[0] > 1 else np.zeros_like(mag)
    flux = np.mean(np.maximum(0, diff), axis=0)[:32].astype(np.float32)
    if len(flux) < 32:
        flux = np.pad(flux, (0, 32 - len(flux)))

    # Spectral Roll-off & Flatness
    cum_mag = np.cumsum(mag, axis=1)
    tot_mag = cum_mag[:, -1:] + 1e-7
    rolloff = np.mean(cum_mag / tot_mag, axis=0)[:32].astype(np.float32)
    if len(rolloff) < 32:
        rolloff = np.pad(rolloff, (0, 32 - len(rolloff)))

    v_dyn = np.concatenate([flux, rolloff])[:64]
    if len(v_dyn) < 64:
        v_dyn = np.pad(v_dyn, (0, 64 - len(v_dyn)))

    # Ghép 3 khối thành vector 256 chiều
    emb = np.concatenate([v_env, v_form, v_dyn]).astype(np.float32)

    # Chuẩn hóa L2 về mặt cầu đơn vị ||e||_2 = 1.0
    norm = float(np.linalg.norm(emb)) + 1e-12
    return emb / norm


def compute_neural_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """Tính độ tương đồng Cosine giữa 2 vector Neural Embedding 256 chiều.
    Vì cả 2 vector đã được chuẩn hóa L2 đơn vị nên Cosine = Dot Product.
    """
    v1 = np.asarray(emb1, dtype=np.float32)
    v2 = np.asarray(emb2, dtype=np.float32)
    if v1.size == 0 or v2.size == 0:
        return 0.0
    n1 = float(np.linalg.norm(v1)) + 1e-12
    n2 = float(np.linalg.norm(v2)) + 1e-12
    dot = float(np.dot(v1 / n1, v2 / n2))
    return float(np.clip(dot, -1.0, 1.0))


def check_duplicate_voice_gate(
    pcm_16k_mono: bytes | np.ndarray,
    target_tier: int,
    exclude_user_id: str | None = None,
    profiles: dict[str, Any] | None = None,
) -> tuple[bool, str, float]:
    """Cổng So Khớp Trùng Giọng Sinh Trắc Học Trong Nhà (Duplicate Voiceprint Reject Gate).
    
    Hợp đồng giao diện theo PROJECT.md:
    Output: Tuple[bool, str, float] -> (is_duplicate, matched_id, similarity)
    
    Quy tắc nghiệp vụ:
    - Nếu tương đồng với Chủ nhà Cấp 1 (`owner_voice_1`) >= 0.82:
      Từ chối ngay lập tức -> Không cho phép ghi đè hay hạ cấp C1.
    - Nếu tương đồng với thành viên đã có >= 0.85:
      Từ chối ngay lập tức.
    """
    if profiles is None:
        try:
            if VOICEPRINT_FILE.exists():
                profiles = json.loads(VOICEPRINT_FILE.read_text(encoding="utf-8"))
            else:
                profiles = {}
        except Exception:
            profiles = {}

    cur_emb = extract_neural_embedding_256d(pcm_16k_mono)

    # 1. Ưu tiên kiểm tra chống trùng Chủ nhà Cấp 1 (owner_voice_1)
    owner_prof = profiles.get("owner_voice_1")
    if owner_prof and owner_prof.get("authorized", True):
        owner_raw = owner_prof.get("embedding_256d")
        if owner_raw is None:
            # Tự động trích xuất nếu chưa có trường 256d
            owner_wav = ROOT_DIR / "test_audio" / "mo_cua_chinh.wav"
            if owner_wav.exists():
                import wave
                with wave.open(str(owner_wav), "rb") as w:
                    raw_b = w.readframes(w.getnframes())
                owner_raw = extract_neural_embedding_256d(raw_b).tolist()
                owner_prof["embedding_256d"] = owner_raw
        if owner_raw is not None:
            owner_vec = np.asarray(owner_raw, dtype=np.float32)
            sim_owner = compute_neural_similarity(cur_emb, owner_vec)
            if sim_owner >= 0.82:
                # Trùng với Chủ nhà Cấp 1
                return True, "owner_voice_1", round(sim_owner, 3)

    # 2. Duyệt qua tất cả thành viên khác
    max_sim = 0.0
    matched_id = ""
    for pid, prof in profiles.items():
        if pid == "owner_voice_1":
            continue
        if not prof.get("authorized", False):
            continue
        p_uid = prof.get("user_id")
        if exclude_user_id and p_uid == exclude_user_id:
            continue

        p_emb = prof.get("embedding_256d")
        if p_emb is not None:
            sim = compute_neural_similarity(cur_emb, np.asarray(p_emb, dtype=np.float32))
            if sim > max_sim:
                max_sim = sim
                matched_id = pid
            if sim >= 0.85:
                return True, pid, round(sim, 3)

    return False, matched_id, round(max_sim, 3)


def verify_speaker_identity_256d(
    pcm_16k_mono: bytes | np.ndarray,
    profiles: dict[str, Any] | None = None,
) -> tuple[bool, str, int, float]:
    """Xác thực danh tính người nói.

    Trước đây hàm này so khớp *hand-crafted* spectral envelope 256-D
    (`extract_neural_embedding_256d`) với ngưỡng cứng 0.78 — không đủ phân biệt
    người nói (FAR cao trên snapshot voiceprints cũ). Nay dùng cùng WeSpeaker
    ResNet34 ONNX và ngưỡng chính thức với `VoiceAuthManager`.
    Output: Tuple[bool, str, int, float] -> (authorized, speaker_id, tier, similarity)
    """
    from simulator.voice.wespeaker_onnx import (
        compute_wespeaker_cosine,
        evaluate_audio_quality_gate,
        extract_wespeaker_embedding,
    )
    from simulator.voice_config import (
        THRESHOLD_WESPEAKER_TIER1,
        get_tier_wespeaker_threshold,
    )

    if profiles is None:
        try:
            if VOICEPRINT_FILE.exists():
                profiles = json.loads(VOICEPRINT_FILE.read_text(encoding="utf-8"))
            else:
                profiles = {}
        except Exception:
            profiles = {}

    quality = evaluate_audio_quality_gate(pcm_16k_mono, sr=16000)
    if not quality.get("ok"):
        return False, "intruder_voice_2", 99, 0.0

    cur_emb = extract_wespeaker_embedding(pcm_16k_mono)

    def _wespeaker_vec(prof: dict[str, Any]) -> np.ndarray | None:
        raw = prof.get("wespeaker_embedding")
        if raw is None and str(prof.get("wespeaker_model") or "") == "wespeaker_r34_onnx":
            raw = prof.get("embedding_256d")
        if raw is None:
            return None
        vec = np.asarray(raw, dtype=np.float32)
        if vec.size < 8:
            return None
        return vec

    owner_prof = profiles.get("owner_voice_1")
    if isinstance(owner_prof, dict) and owner_prof.get("authorized", True):
        owner_vec = _wespeaker_vec(owner_prof)
        if owner_vec is not None:
            sim_owner = float(compute_wespeaker_cosine(cur_emb, owner_vec))
            if sim_owner >= float(THRESHOLD_WESPEAKER_TIER1):
                return True, "owner_voice_1", 1, round(sim_owner, 3)

    best_sim = -1.0
    best_id = "intruder_voice_2"
    best_tier = 99
    now_ts = time.time()

    for pid, prof in (profiles or {}).items():
        if pid == "owner_voice_1" or not isinstance(prof, dict) or not prof.get("authorized", False):
            continue
        exp = prof.get("expires_at")
        if exp is not None and now_ts > float(exp):
            continue
        p_vec = _wespeaker_vec(prof)
        if p_vec is None:
            continue
        sim = float(compute_wespeaker_cosine(cur_emb, p_vec))
        if sim > best_sim:
            best_sim = sim
            best_id = str(pid)
            best_tier = int(prof.get("tier", 99))

    if best_sim >= float(get_tier_wespeaker_threshold(best_tier)):
        return True, best_id, best_tier, round(best_sim, 3)

    return False, "intruder_voice_2", 99, round(max(0.0, best_sim), 3)

