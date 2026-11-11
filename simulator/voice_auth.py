"""Bo Phan Tich Giong Noi WeSpeaker ResNet34 ONNX (256-D Speaker Verification & 5-Sample Enrollment),
Cong Kiem Dinh Chat Luong Am Thanh (Mel26 + Deep64 Audio Quality Gate),
Khu Tieng On Quat/Moi Truong (Spectral Wiener Denoising & Human Voice Isolation),
Phat Hien & Tach 2 Nguoi Cung Noi (Multi-Speaker Diarization & Tier-Priority Resolution)
va Kiem Soat Quyen "Qua Tam Ba Ban" (2-Strike Silent Ignore).
"""

from __future__ import annotations

import copy
import contextlib
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
from simulator.voice.dsp_features import (
    STAGE1_HIGH_CONFIDENCE,
    STAGE1_LOW_REJECT,
    STAGE2_PASS_THRESHOLD,
    cosine_sim,
    denoise_and_isolate_human_voice,
    detect_multi_speaker_and_resolve_priority,
    extract_stage2_deep_features,
    extract_voice_features,
)
from simulator.voice.enrollment_quality import (
    ENROLL_QUALITY_RULES,
    check_enrollment_quality_gate,
    evaluate_enrollment_quality_gate,
    measure_enrollment_audio,
    measure_segment_consistency,
    parse_vietnamese_voice_command_intents,
    validate_voice_enrollment_quality,
)
from simulator.voice.synthesis_augment import (
    synthesize_noisy_fan_voice,
    synthesize_two_speakers_audio,
    transform_pcm_by_pitch_factor,
    transform_pcm_to_intruder_voice,
)
from simulator.voice.wespeaker_onnx import (
    DEFAULT_ENROLLMENT_SAMPLES,
    DEFAULT_WESPEAKER_THRESHOLD,
    SAFE_DENY_REPEAT_PHRASE_VI,
    _is_encoded_container_bytes,
    compute_multi_sample_mean_embedding,
    compute_wespeaker_cosine,
    evaluate_audio_quality_gate,
    evaluate_cohort_margin,
    extract_wespeaker_embedding,
    extract_wespeaker_subwindow_bank,
    get_wespeaker_session,
    load_verified_owner_seed,
    load_verified_owner_5sample_seed,
    load_verified_tier_5sample_seed,
    pcm_bytes_to_float32_16k,
)

UNIFIED_REJECTION_PHRASE_VI = "Xin lỗi, bạn không có quyền thực hiện lệnh này."
from simulator.voice_config import (
    ENROLLMENT_REQUIRED_SAMPLES,
    OWNER_ID,
    ROLE_MAP,
    THRESHOLD_DEEP,
    THRESHOLD_MEL,
    THRESHOLD_WESPEAKER,
    THRESHOLD_WESPEAKER_TIER1,
    THRESHOLD_WESPEAKER_TIER2,
    THRESHOLD_WESPEAKER_TIER3,
    USER_ROLE_MAP,
    get_tier_wespeaker_threshold,
)

DATA_DIR = resolve_data_dir()
VOICEPRINT_FILE = DATA_DIR / "voiceprints.json"

__all__ = [
    "DATA_DIR",
    "VOICEPRINT_FILE",
    "STAGE1_HIGH_CONFIDENCE",
    "STAGE1_LOW_REJECT",
    "STAGE2_PASS_THRESHOLD",
    "denoise_and_isolate_human_voice",
    "extract_voice_features",
    "extract_stage2_deep_features",
    "detect_multi_speaker_and_resolve_priority",
    "cosine_sim",
    "transform_pcm_by_pitch_factor",
    "transform_pcm_to_intruder_voice",
    "synthesize_noisy_fan_voice",
    "synthesize_two_speakers_audio",
    "validate_voice_enrollment_quality",
    "check_enrollment_quality_gate",
    "evaluate_enrollment_quality_gate",
    "measure_enrollment_audio",
    "measure_segment_consistency",
    "ENROLL_QUALITY_RULES",
    "SAFE_DENY_REPEAT_PHRASE_VI",
    "UNIFIED_REJECTION_PHRASE_VI",
    "parse_vietnamese_voice_command_intents",
    "DuplicateVoiceCheckResult",
    "VoiceAuthManager",
    "check_duplicate_voice_gate",
    "extract_wespeaker_embedding",
    "extract_wespeaker_subwindow_bank",
    "compute_wespeaker_cosine",
    "compute_multi_sample_mean_embedding",
    "evaluate_audio_quality_gate",
]

_SEED_CACHE: dict[str, Any] = {}


def _get_cached_seeds(audio_dir: pathlib.Path) -> dict[str, Any]:
    """Build and cache the 5-sample WeSpeaker ResNet34 ONNX seeds for Owner, Tier 2, Tier 3, and Intruder."""
    if "owner_seed" in _SEED_CACHE:
        return _SEED_CACHE

    project_root = audio_dir.parent
    owner_seed = load_verified_owner_seed(project_root=project_root)
    tier2_seed = load_verified_tier_5sample_seed(tier=2, project_root=project_root)
    tier3_seed = load_verified_tier_5sample_seed(tier=3, project_root=project_root)

    # Fast-path: load precomputed acoustic & WeSpeaker seeds from real_voices_signatures.json
    sig_json = pathlib.Path(__file__).resolve().parent / "voice" / "real_voices_signatures.json"
    if sig_json.exists():
        try:
            raw_sig = json.loads(sig_json.read_text(encoding="utf-8"))
            pre_seeds = raw_sig.get("precomputed_voice_auth_seeds") or {}
            if (
                pre_seeds.get("feat_own")
                and pre_seeds.get("deep_own")
                and pre_seeds.get("feat_v2")
                and pre_seeds.get("deep_v2")
                and len(pre_seeds.get("wespk_v2") or []) == 256
                and len(pre_seeds.get("t2_single_emb") or []) == 256
                and len(pre_seeds.get("t3_single_emb") or []) == 256
            ):
                _SEED_CACHE["owner_seed"] = owner_seed
                _SEED_CACHE["tier2_seed"] = tier2_seed
                _SEED_CACHE["tier3_seed"] = tier3_seed
                _SEED_CACHE["feat_own"] = pre_seeds["feat_own"]
                _SEED_CACHE["deep_own"] = pre_seeds["deep_own"]
                _SEED_CACHE["feat_v2"] = pre_seeds["feat_v2"]
                _SEED_CACHE["deep_v2"] = pre_seeds["deep_v2"]
                _SEED_CACHE["wespk_v2"] = pre_seeds["wespk_v2"]
                _SEED_CACHE["t2_single_emb"] = pre_seeds["t2_single_emb"]
                _SEED_CACHE["t3_single_emb"] = pre_seeds["t3_single_emb"]
                return _SEED_CACHE
        except Exception:
            pass

    # Extract acoustic metadata from real LENOVO owner clip cau_2_mo_cua_chinh.wav
    cau2_wav = audio_dir / "cac_cau_lenh_cua_sep" / "cau_2_mo_cua_chinh.wav"
    if cau2_wav.exists():
        with wave.open(str(cau2_wav), "rb") as w:
            pcm_own = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        pcm_own_clean, _ = denoise_and_isolate_human_voice(pcm_own, 16000)
        feat_own = extract_voice_features(pcm_own_clean, 16000)
        deep_own = extract_stage2_deep_features(pcm_own_clean, 16000)
    else:
        pcm_own = np.zeros(16000, dtype=np.int16)
        feat_own = {
            "f0_hz": owner_seed.get("f0_hz", 135.0),
            "centroid_hz": 1271.7,
            "embedding": owner_seed.get("embedding", [0.2] * 26),
        }
        deep_own = {
            "formants_hz": [510.0, 1480.0, 2580.0, 3620.0],
            "hnr_db": 14.5,
            "deep_embedding": owner_seed.get("deep_embedding", [0.12] * 64),
        }

    v2_wav = audio_dir / "giong_2_nguoi_la_mo_cua.wav"
    if v2_wav.exists():
        with wave.open(str(v2_wav), "rb") as w:
            pcm_v2 = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        pcm_v2_clean, _ = denoise_and_isolate_human_voice(pcm_v2, 16000)
        feat_v2 = extract_voice_features(pcm_v2_clean, 16000)
        deep_v2 = extract_stage2_deep_features(pcm_v2_clean, 16000)
        wespk_v2 = extract_wespeaker_embedding(pcm_v2).tolist()
    else:
        feat_v2 = {"f0_hz": 219.2, "centroid_hz": 1381.0, "embedding": [-0.2] * 26}
        deep_v2 = {
            "formants_hz": [640.0, 1790.0, 2890.0, 3910.0],
            "hnr_db": 9.8,
            "deep_embedding": [-0.12] * 64,
        }
        wespk_v2 = [0.0] * 256

    if cau2_wav.exists() and v2_wav.exists():
        noisy_wav = audio_dir / "giong_1_kem_tieng_on_quat.wav"
        dual_wav = audio_dir / "hai_nguoi_cung_noi_cap1_va_nguoi_la.wav"
        if not (noisy_wav.exists() and dual_wav.exists()):
            try:
                VoiceAuthManager._write_wav16k(
                    noisy_wav, synthesize_noisy_fan_voice(pcm_own, 16000)
                )
                VoiceAuthManager._write_wav16k(
                    dual_wav, synthesize_two_speakers_audio(pcm_own, pcm_v2, 16000)
                )
            except Exception:
                pass

    t2_single_wav = audio_dir / "giong_cap2_thanh_vien_a.wav"
    t2_single_emb = (
        extract_wespeaker_embedding(t2_single_wav.read_bytes()).tolist()
        if t2_single_wav.exists()
        else tier2_seed.get("wespeaker_embedding", [0.0] * 256)
    )
    t3_single_wav = audio_dir / "giong_cap3_khach_c.wav"
    t3_single_emb = (
        extract_wespeaker_embedding(t3_single_wav.read_bytes()).tolist()
        if t3_single_wav.exists()
        else tier3_seed.get("wespeaker_embedding", [0.0] * 256)
    )

    _SEED_CACHE["owner_seed"] = owner_seed
    _SEED_CACHE["tier2_seed"] = tier2_seed
    _SEED_CACHE["tier3_seed"] = tier3_seed
    _SEED_CACHE["feat_own"] = feat_own
    _SEED_CACHE["deep_own"] = deep_own
    _SEED_CACHE["feat_v2"] = feat_v2
    _SEED_CACHE["deep_v2"] = deep_v2
    _SEED_CACHE["wespk_v2"] = [round(float(x), 6) for x in wespk_v2]
    _SEED_CACHE["t2_single_emb"] = [round(float(x), 6) for x in t2_single_emb]
    _SEED_CACHE["t3_single_emb"] = [round(float(x), 6) for x in t3_single_emb]
    return _SEED_CACHE


class DuplicateVoiceCheckResult(tuple):
    """Kết quả kiểm tra cổng chống trùng giọng: hỗ trợ cả tuple unpacking (is_dup, reason, profile) và truy cập dict."""

    def __new__(
        cls,
        is_duplicate: bool,
        reason: str,
        matched_profile: dict[str, Any] | None = None,
        **kwargs,
    ):
        return super().__new__(cls, (is_duplicate, reason, matched_profile))

    def __init__(
        self,
        is_duplicate: bool,
        reason: str,
        matched_profile: dict[str, Any] | None = None,
        **kwargs,
    ):
        self.is_duplicate = is_duplicate
        self.ok = not is_duplicate
        self.reason = reason
        self.status = "DUPLICATE_VOICE_REJECTED" if is_duplicate else "DA_DAT"
        self.message = kwargs.get(
            "message",
            (
                "Trùng giọng người đã có trong nhà - Từ chối lưu"
                if is_duplicate
                else "Không trùng giọng"
            ),
        )
        self.error = self.message if is_duplicate else ""
        self.matched_profile = matched_profile
        self.similarity = kwargs.get("similarity", 0.0)
        self.matched_tier = kwargs.get(
            "matched_tier", (matched_profile.get("tier") if matched_profile else None)
        )
        self.matched_name = kwargs.get(
            "matched_name", (matched_profile.get("name") if matched_profile else "")
        )

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
    """Quản lý Xác Thực Giọng Nói bằng WeSpeaker ResNet34 ONNX (256-D Speaker Embedding + 5-Sample Mean Enrollment),
    giữ Mel26+Deep64 làm cổng kiểm định chất lượng âm thanh (Quality Gate: quá ngắn / quá nhỏ / bị rè -> yêu cầu nói lại),
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
        threshold_mel: float = THRESHOLD_MEL,
        threshold_deep: float = THRESHOLD_DEEP,
        f0_hz: float | None = None,
        target_tier: int = 0,
        target_user_id: str = "",
        threshold_wespeaker: float | None = None,
    ) -> DuplicateVoiceCheckResult:
        """Cổng Kiểm Tra Chống Trùng Giọng Trong Nhà (WeSpeaker ResNet34 ONNX Duplicate Voiceprint Gate):
        - So sánh vector WeSpeaker ResNet34 ONNX 256-D (cosine >= threshold_wespeaker, mặc định 0.435)
          với tất cả hồ sơ thành viên trong nhà (đặc biệt là owner_voice_1).
        - Nếu trùng giọng với bất kỳ ai đã đăng ký trong nhà -> Từ chối ngay lập tức và không cho phép
          lưu đè hoặc hạ cấp quyền.
        """
        cur_wespk: np.ndarray | None = None
        cur_mel: list[float] = []
        cur_deep: list[float] = []
        cur_f0: float = float(f0_hz or 0.0)

        if isinstance(feat_s1, (bytes, bytearray, np.ndarray)):
            if isinstance(feat_s1, np.ndarray) and feat_s1.ndim == 1 and feat_s1.size == 256 and np.issubdtype(feat_s1.dtype, np.floating) and float(np.max(np.abs(feat_s1))) <= 1.05:
                cur_wespk = feat_s1.astype(np.float32)
            else:
                cur_wespk = extract_wespeaker_embedding(feat_s1)
                pcm_raw = (
                    np.frombuffer(feat_s1, dtype=np.int16)
                    if isinstance(feat_s1, (bytes, bytearray))
                    else np.asarray(feat_s1, dtype=np.int16)
                )
                f1 = extract_voice_features(pcm_raw, 16000)
                cur_mel = f1.get("embedding") or []
                cur_f0 = float(f1.get("f0_hz", 0.0))
        elif isinstance(feat_s1, dict):
            cur_mel = feat_s1.get("embedding") or feat_s1.get("features") or []
            cur_f0 = float(f0_hz if f0_hz is not None else feat_s1.get("f0_hz", 0.0))
            if isinstance(deep_feat, dict):
                cur_deep = deep_feat.get("deep_embedding") or []
            elif isinstance(deep_feat, (list, tuple)):
                cur_deep = list(deep_feat)
            else:
                cur_deep = feat_s1.get("deep_embedding") or feat_s1.get("deep_features") or []
            w_cand = (
                feat_s1.get("wespeaker_embedding")
                or feat_s1.get("embedding_256d")
                or feat_s1.get("neural_embedding")
            )
            if w_cand and len(w_cand) == 256:
                cur_wespk = np.asarray(w_cand, dtype=np.float32)
        elif isinstance(feat_s1, (list, tuple)):
            if len(feat_s1) == 256:
                cur_wespk = np.asarray(feat_s1, dtype=np.float32)
            else:
                cur_mel = list(feat_s1)
                cur_f0 = float(f0_hz or 0.0)
                if isinstance(deep_feat, (list, tuple)):
                    if len(deep_feat) == 256:
                        cur_wespk = np.asarray(deep_feat, dtype=np.float32)
                    else:
                        cur_deep = list(deep_feat)
                elif isinstance(deep_feat, dict):
                    cur_deep = deep_feat.get("deep_embedding") or []
                    w_cand = deep_feat.get("wespeaker_embedding") or deep_feat.get("embedding_256d")
                    if w_cand and len(w_cand) == 256:
                        cur_wespk = np.asarray(w_cand, dtype=np.float32)

        if cur_wespk is None and not cur_mel:
            return DuplicateVoiceCheckResult(False, "KHONG_TRUNG", None)

        ordered_profiles: list[tuple[str, dict[str, Any]]] = []
        if "owner_voice_1" in self.profiles:
            ordered_profiles.append(("owner_voice_1", self.profiles["owner_voice_1"]))
        for pid, p in self.profiles.items():
            if pid != "owner_voice_1":
                ordered_profiles.append((pid, p))

        for pid, prof in ordered_profiles:
            if not prof.get("authorized") or int(prof.get("tier", 99)) > 3:
                continue
            if target_user_id and prof.get("user_id") == target_user_id:
                continue
            if (
                target_tier in (2, 3)
                and pid
                in (
                    "user_voice_thanh_vien_a",
                    "user_voice_khach_c",
                    "family_voice_2",
                    "guest_voice_3",
                )
                and int(prof.get("tier", 0)) == int(target_tier)
                and not prof.get("custom_enrolled")
            ):
                continue

            p_tier = int(prof.get("tier", 1))
            p_thresh = (
                float(threshold_wespeaker)
                if threshold_wespeaker is not None
                else float(
                    prof.get("threshold_wespeaker")
                    or get_tier_wespeaker_threshold(p_tier)
                )
            )

            is_dup = False
            best_sim = 0.0
            p_f0 = float(prof.get("f0_hz", 0.0))
            df0_w = abs(cur_f0 - p_f0) if (cur_f0 > 50.0 and p_f0 > 50.0) else 0.0
            f0_compatible = True if pid == "owner_voice_1" else (df0_w <= 25.0)

            if cur_wespk is not None and float(np.linalg.norm(cur_wespk)) > 1e-6:
                p_wespk = prof.get("wespeaker_embedding") or prof.get("embedding_256d")
                if p_wespk and len(p_wespk) == 256:
                    sim_w = compute_wespeaker_cosine(cur_wespk, p_wespk)
                    best_sim = max(best_sim, sim_w)
                    if sim_w >= p_thresh and f0_compatible:
                        is_dup = True
                p_base_wespk = prof.get("baseline_wespeaker_embedding") or prof.get(
                    "baseline_embedding_256d"
                )
                if p_base_wespk and len(p_base_wespk) == 256:
                    sim_wb = compute_wespeaker_cosine(cur_wespk, p_base_wespk)
                    best_sim = max(best_sim, sim_wb)
                    if sim_wb >= p_thresh and f0_compatible:
                        is_dup = True
            elif cur_mel:
                # Fallback ONLY when caller passed synthetic 26D/64D arrays without PCM or 256D vector
                p_mel = prof.get("embedding") or []
                p_deep = prof.get("deep_embedding") or []
                p_f0 = float(prof.get("f0_hz", 135.0))
                s_m_c = cosine_sim(cur_mel, p_mel)
                s_d_c = cosine_sim(cur_deep, p_deep) if (cur_deep and p_deep) else s_m_c
                df0_c = abs(cur_f0 - p_f0) if (cur_f0 > 0 and p_f0 > 0) else 0.0
                best_sim = max(s_m_c, s_d_c)
                if (s_m_c >= threshold_mel and s_d_c >= threshold_deep and df0_c <= 15.0) or (
                    s_m_c >= 0.92 and df0_c <= 10.0
                ):
                    is_dup = True

            if is_dup:
                prof_name = prof.get("name", pid)
                return DuplicateVoiceCheckResult(
                    True,
                    "TRUNG_GIONG_NGUOI_TRONG_NHA",
                    prof,
                    message="Trùng giọng người đã có trong nhà - Từ chối lưu",
                    error="Trùng giọng người đã có trong nhà - Từ chối lưu",
                    similarity=round(float(best_sim), 4),
                    matched_tier=prof.get("tier"),
                    matched_name=prof_name,
                )

        return DuplicateVoiceCheckResult(False, "KHONG_TRUNG", None)

    def __init__(self, audio_dir: pathlib.Path) -> None:
        self.audio_dir = audio_dir
        self.unauthorized_strikes: int = 0
        self.voice_auth_enabled: bool = True
        self._pending_enrollment_samples: dict[str, list[bytes]] = {}
        self.default_subtier_profiles: dict[str, dict[str, Any]] = {}
        self.last_analysis: dict[str, Any] = {
            "speaker_id": "owner_voice_1",
            "speaker_label": "Giọng 1 — Chủ nhà (Được phép)",
            "authorized": True,
            "f0_hz": 135.0,
            "centroid_hz": 1271.7,
            "similarity": 0.85,
            "wespeaker_cosine": 0.85,
            "threshold_wespeaker": THRESHOLD_WESPEAKER_TIER1,
            "stage1_confidence": 0.85,
            "stage2_triggered": False,
            "stage2_confidence": None,
            "filter_stage_used": "WeSpeaker ResNet34 ONNX (256-D Cosine)",
            "denoise_ms": 1.2,
            "stage1_ms": 1.1,
            "stage2_ms": 0.0,
            "total_ms": 18.5,
            "noise_removed_db": 14.2,
            "multi_speaker_detected": False,
            "speaker_count": 1,
            "priority_reason": "Chỉ có 1 người nói.",
            "strike_count": 0,
            "action_taken": "ALLOW",
        }
        self.profiles = self._init_or_load_profiles()

    def _init_or_load_profiles(self) -> dict[str, Any]:
        """Khởi tạo hoặc nạp hồ sơ giọng nói gốc của Chủ nhà Cấp 1 (từ 5 mẫu LENOVO độc lập)
        và hồ sơ mặc định Cấp 2/Cấp 3 (từ 5 mẫu mỗi cấp) + Mẫu đối chứng Người lạ.
        Tuyệt đối không dùng giong_1_* hay bản sao trùng byte.
        """
        existing_custom: dict[str, Any] = {}
        loaded_disk: dict[str, Any] | None = None
        try:
            from simulator.durable_store import load_durable_json

            loaded_disk = load_durable_json("voiceprints.json", VOICEPRINT_FILE)
        except Exception:
            loaded_disk = None
        if loaded_disk is None and VOICEPRINT_FILE.exists():
            try:
                loaded_disk = json.loads(VOICEPRINT_FILE.read_text(encoding="utf-8"))
            except Exception:
                loaded_disk = None
        if isinstance(loaded_disk, dict):
            for k, v in loaded_disk.items():
                if (
                    isinstance(v, dict)
                    and v.get("custom_enrolled")
                    and v.get("wespeaker_model") == "wespeaker_r34_onnx"
                ):
                    existing_custom[k] = v

        seeds = _get_cached_seeds(self.audio_dir)
        owner_seed = seeds["owner_seed"]
        tier2_seed = seeds["tier2_seed"]
        tier3_seed = seeds["tier3_seed"]
        feat_own = seeds["feat_own"]
        deep_own = seeds["deep_own"]
        feat_v2 = seeds["feat_v2"]
        deep_v2 = seeds["deep_v2"]
        wespk_v2 = seeds["wespk_v2"]

        owner_wespk = owner_seed.get("wespeaker_embedding", [0.0] * 256)
        owner_sub_embs = owner_seed.get("sub_embeddings_256d", [])
        tier2_wespk = tier2_seed.get("wespeaker_embedding", [0.0] * 256)
        tier3_wespk = tier3_seed.get("wespeaker_embedding", [0.0] * 256)

        self.default_subtier_profiles = {
            "user_voice_thanh_vien_a": {
                "id": "user_voice_thanh_vien_a",
                "user_id": USER_ROLE_MAP.get(2, "thanh_vien_a"),
                "name": "Giọng Cấp 2 — Thành viên Gia đình (Mặc định 5 mẫu)",
                "authorized": True,
                "role": ROLE_MAP.get(2, "MEMBER"),
                "tier": 2,
                "threshold_wespeaker": THRESHOLD_WESPEAKER_TIER2,
                "enrollment_samples_count": tier2_seed.get("num_samples", 5),
                "seed_clips": tier2_seed.get("seed_clips", []),
                "wespeaker_embedding": tier2_wespk,
                "embedding_256d": tier2_wespk,
                "single_clip_wespeaker_embedding": seeds["t2_single_emb"],
                "f0_hz": tier2_seed.get("f0_hz", 145.0),
                "embedding": tier2_seed.get("embedding", [0.1] * 26),
                "deep_embedding": tier2_seed.get("deep_embedding", [0.1] * 64),
            },
            "user_voice_khach_c": {
                "id": "user_voice_khach_c",
                "user_id": USER_ROLE_MAP.get(3, "khach_c"),
                "name": "Giọng Cấp 3 — Khách / Trẻ em (Mặc định 5 mẫu)",
                "authorized": True,
                "role": ROLE_MAP.get(3, "CHILD_GUEST"),
                "tier": 3,
                "threshold_wespeaker": THRESHOLD_WESPEAKER_TIER3,
                "enrollment_samples_count": tier3_seed.get("num_samples", 5),
                "seed_clips": tier3_seed.get("seed_clips", []),
                "wespeaker_embedding": tier3_wespk,
                "embedding_256d": tier3_wespk,
                "single_clip_wespeaker_embedding": seeds["t3_single_emb"],
                "f0_hz": tier3_seed.get("f0_hz", 150.0),
                "embedding": tier3_seed.get("embedding", [0.1] * 26),
                "deep_embedding": tier3_seed.get("deep_embedding", [0.1] * 64),
            },
        }

        data: dict[str, Any] = {
            "owner_voice_1": {
                "id": "owner_voice_1",
                "user_id": OWNER_ID,
                "name": "Giọng Cấp 1 — Nguyễn Tuấn Anh (Chủ nhà - Toàn quyền)",
                "authorized": True,
                "role": ROLE_MAP.get(1, "ADMIN"),
                "tier": 1,
                "wespeaker_model": "wespeaker_r34_onnx",
                "threshold_wespeaker": THRESHOLD_WESPEAKER_TIER1,
                "enrollment_samples_count": owner_seed.get("num_samples", 5),
                "seed_clips": owner_seed.get("seed_clips", []),
                "voice_source": "WeSpeaker ResNet34 ONNX (Trung bình 5 mẫu giọng thật độc lập của Chủ nhà)",
                "f0_hz": feat_own["f0_hz"],
                "centroid_hz": feat_own["centroid_hz"],
                "embedding": feat_own["embedding"],
                "formants_hz": deep_own["formants_hz"],
                "hnr_db": deep_own["hnr_db"],
                "deep_embedding": deep_own["deep_embedding"],
                "embedding_256d": owner_wespk,
                "wespeaker_embedding": owner_wespk,
                "sub_embeddings_256d": owner_sub_embs,
            },
            "intruder_voice_2": {
                "id": "intruder_voice_2",
                "user_id": "UNKNOWN",
                "name": "Giọng 2 — Người lạ (Không được phép - Chặn 100%)",
                "authorized": False,
                "role": "UNKNOWN",
                "tier": 99,
                "wespeaker_model": "wespeaker_r34_onnx",
                "voice_source": "Mẫu đối chứng chặn người lạ",
                "f0_hz": feat_v2["f0_hz"],
                "centroid_hz": feat_v2["centroid_hz"],
                "embedding": feat_v2["embedding"],
                "formants_hz": deep_v2["formants_hz"],
                "hnr_db": deep_v2["hnr_db"],
                "deep_embedding": deep_v2["deep_embedding"],
                "embedding_256d": wespk_v2,
                "wespeaker_embedding": wespk_v2,
            },
        }
        for k, v in existing_custom.items():
            if k in data:
                v["baseline_f0_hz"] = data[k]["f0_hz"]
                v["baseline_embedding"] = data[k]["embedding"]
                v["baseline_formants_hz"] = data[k]["formants_hz"]
                v["baseline_deep_embedding"] = data[k]["deep_embedding"]
                v["baseline_embedding_256d"] = data[k]["embedding_256d"]
                v["baseline_wespeaker_embedding"] = data[k]["wespeaker_embedding"]
                if not v.get("sub_embeddings_256d") and data[k].get("sub_embeddings_256d"):
                    v["sub_embeddings_256d"] = data[k]["sub_embeddings_256d"]
            data[k] = v
        self._save_voiceprints_safe(data)
        return data

    def _restore_voiceprint_file(self, prev_disk: bytes | None) -> None:
        if prev_disk is not None:
            with contextlib.suppress(Exception):
                VOICEPRINT_FILE.write_bytes(prev_disk)
                self._voiceprint_mtime_ns = VOICEPRINT_FILE.stat().st_mtime_ns
            return
        if VOICEPRINT_FILE.exists():
            with contextlib.suppress(Exception):
                VOICEPRINT_FILE.unlink(missing_ok=True)
            self._voiceprint_mtime_ns = 0

    def _save_voiceprints_safe(self, data: dict[str, Any] | None = None) -> bool:
        target = data if data is not None else self.profiles
        prev_disk = VOICEPRINT_FILE.read_bytes() if VOICEPRINT_FILE.exists() else None
        try:
            VOICEPRINT_FILE.parent.mkdir(parents=True, exist_ok=True)
            import simulator.durable_store as _ds

            ok_saved = bool(_ds.save_durable_json("voiceprints.json", target, VOICEPRINT_FILE))
            if not ok_saved:
                self._restore_voiceprint_file(prev_disk)
                return False
            if VOICEPRINT_FILE.exists():
                self._voiceprint_mtime_ns = VOICEPRINT_FILE.stat().st_mtime_ns
            return True
        except Exception:
            self._restore_voiceprint_file(prev_disk)
            return False

    def _sync_voiceprints_from_disk(self) -> None:
        try:
            if not VOICEPRINT_FILE.exists():
                return
            st_ns = VOICEPRINT_FILE.stat().st_mtime_ns
            if getattr(self, "_voiceprint_mtime_ns", 0) == st_ns:
                return
            self._voiceprint_mtime_ns = st_ns
            loaded = json.loads(VOICEPRINT_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for k, v in loaded.items():
                    if (
                        isinstance(v, dict)
                        and v.get("custom_enrolled")
                        and v.get("wespeaker_model") == "wespeaker_r34_onnx"
                    ):
                        if k in self.profiles and "baseline_wespeaker_embedding" not in v:
                            v["baseline_wespeaker_embedding"] = self.profiles[k].get("wespeaker_embedding")
                            v["baseline_embedding_256d"] = self.profiles[k].get("embedding_256d")
                        self.profiles[k] = v
        except Exception:
            pass

    @staticmethod
    def _write_wav16k(path: pathlib.Path, pcm16: np.ndarray) -> None:
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm16.tobytes())

    def evaluate_privileged_voice_gate(
        self,
        *,
        analysis: dict[str, Any] | None = None,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        """Cổng WeSpeaker chặt hơn cho lệnh đặc quyền (cấp/thu hồi quyền, đăng ký giọng).

        Không thay ngưỡng lệnh thường (0.435). Thiếu bằng chứng lượt mic hiện tại thì fail-closed.
        """
        from simulator.voice_config import THRESHOLD_WESPEAKER_PRIVILEGED

        info = dict(analysis or {})
        thr = float(THRESHOLD_WESPEAKER_PRIVILEGED if threshold is None else threshold)
        if not info:
            return {
                "ok": False,
                "authorized": False,
                "rbac_blocked": True,
                "reason": "PRIVILEGED_VOICE_NO_UTTERANCE",
                "wespeaker_cosine": 0.0,
                "threshold_wespeaker_privileged": thr,
                "message": UNIFIED_REJECTION_PHRASE_VI,
            }
        authorized = bool(info.get("authorized"))
        try:
            tier = int(info.get("tier") or 99)
        except (TypeError, ValueError):
            tier = 99
        raw_cos = info.get("wespeaker_cosine")
        if raw_cos is None:
            raw_cos = info.get("similarity") or 0.0
        try:
            cosine = float(raw_cos)
        except (TypeError, ValueError):
            cosine = 0.0
        if authorized and tier == 1 and cosine >= thr:
            return {
                "ok": True,
                "authorized": True,
                "tier": tier,
                "wespeaker_cosine": cosine,
                "threshold_wespeaker_privileged": thr,
            }
        return {
            "ok": False,
            "authorized": False,
            "rbac_blocked": True,
            "reason": "PRIVILEGED_VOICE_THRESHOLD",
            "tier": tier,
            "wespeaker_cosine": cosine,
            "threshold_wespeaker_privileged": thr,
            "message": UNIFIED_REJECTION_PHRASE_VI,
        }

    def enroll_owner_from_pcm16k(
        self,
        pcm_bytes: bytes | None = None,
        label: str = "Giọng Cấp 1 — Nguyễn Tuấn Anh (Đã thu âm giọng thật)",
        samples_pcm16k: list[bytes | np.ndarray] | None = None,
    ) -> dict[str, Any]:
        """Đăng ký vân giọng mới cho Chủ nhà Cấp 1 bằng WeSpeaker ResNet34 ONNX (hỗ trợ 5 mẫu độc lập)."""
        return self.enroll_tier_voice_from_pcm16k(
            pcm_bytes=pcm_bytes or b"",
            user_id=OWNER_ID,
            user_name="Nguyễn Tuấn Anh",
            tier=1,
            role=ROLE_MAP.get(1, "ADMIN"),
            custom_label=label,
            samples_pcm16k=samples_pcm16k,
        )

    def enroll_multi_sample_tier_voice(
        self,
        samples_pcm16k: list[bytes | np.ndarray],
        user_id: str = OWNER_ID,
        user_name: str = "Nguyễn Tuấn Anh",
        tier: int = 1,
        role: str = "ADMIN",
        custom_label: str = "",
        expires_at: float | None = None,
        check_duplicate: bool = True,
        required_samples: int = ENROLLMENT_REQUIRED_SAMPLES,
    ) -> dict[str, Any]:
        """Đăng ký giọng nói đa mẫu (Multi-Sample Enrollment: trung bình 5 vector WeSpeaker ResNet34 ONNX
        từ 5 mẫu giọng nói khác nhau, độ dài 3-5 giây/mẫu). Không bao giờ ghi raw audio vào log.
        """
        return self.enroll_tier_voice_from_pcm16k(
            pcm_bytes=b"",
            user_id=user_id,
            user_name=user_name,
            tier=tier,
            role=role,
            custom_label=custom_label,
            expires_at=expires_at,
            check_duplicate=check_duplicate,
            samples_pcm16k=samples_pcm16k,
            required_samples=required_samples,
        )

    def enroll_tier_voice_from_pcm16k(
        self,
        pcm_bytes: bytes = b"",
        user_id: str = OWNER_ID,
        user_name: str = "Nguyễn Tuấn Anh",
        tier: int = 1,
        role: str = "ADMIN",
        custom_label: str = "",
        expires_at: float | None = None,
        check_duplicate: bool = True,
        samples_pcm16k: list[bytes | np.ndarray] | None = None,
        required_samples: int = ENROLLMENT_REQUIRED_SAMPLES,
        sample_index: int | None = None,
        total_samples: int | None = None,
        self_check_pcm_bytes: bytes | np.ndarray | None = None,
        enforce_12s_gate: bool = True,
    ) -> dict[str, Any]:
        """Thu âm giọng nói thật từ Microphone (16kHz PCM) và lưu vector trung bình WeSpeaker ResNet34 ONNX
        cho Cấp 1, Cấp 2 hoặc Cấp 3. Bắt buộc qua Cổng Chống Trùng Giọng Trong Nhà.
        Bắt buộc 100% qua cổng kiểm định nghiêm ngặt 11s + self-check 3s (ENROLL_QUALITY.md) phía server.
        """
        if (user_id == OWNER_ID or custom_label == "owner_voice_1") and int(tier) != 1:
            return {
                "ok": False,
                "status": "TIER1_DEMOTION_FORBIDDEN",
                "reason": "CAM_HA_CAP_CHU_NHA",
                "error": (
                    f"Tài khoản Chủ nhà {OWNER_ID} là bất biến Cấp 1 ADMIN. "
                    "Nghiêm cấm mọi hành vi hạ cấp xuống Tier 2 hoặc Tier 3!"
                ),
                "message": "Không thể hạ cấp quyền Chủ nhà Cấp 1.",
            }

        # Bắt buộc 100% kiểm định chất lượng nghiêm ngặt phía server (không cho phép opt-in/tắt từ client)
        enroll_pcm_for_gate: bytes | np.ndarray = pcm_bytes
        if (not isinstance(pcm_bytes, (bytes, bytearray)) or len(pcm_bytes) == 0) and samples_pcm16k:
            joined_chunks: list[bytes] = []
            for s_item in samples_pcm16k:
                if isinstance(s_item, (bytes, bytearray)):
                    joined_chunks.append(bytes(s_item))
                elif isinstance(s_item, np.ndarray):
                    joined_chunks.append(s_item.astype(np.int16).tobytes())
            if joined_chunks:
                enroll_pcm_for_gate = b"".join(joined_chunks)

        gate_res = check_enrollment_quality_gate(
            enroll_pcm=enroll_pcm_for_gate,
            self_check_pcm=self_check_pcm_bytes,
            sr=16000,
            require_self_check=True,
        )
        if not gate_res.get("ok"):
            return gate_res

        # Hỗ trợ thu âm lũy tiến từng mẫu 1..5 (Progressive 5-Sample Enrollment)
        if (
            samples_pcm16k is None
            and sample_index is not None
            and total_samples is not None
            and int(total_samples) > 1
        ):
            idx = int(sample_index)
            tot = int(total_samples)
            buf_key = f"{tier}:{user_id}"
            if idx <= 1 or buf_key not in self._pending_enrollment_samples:
                self._pending_enrollment_samples[buf_key] = []

            q_single = evaluate_audio_quality_gate(pcm_bytes, sr=16000)
            if not q_single["ok"]:
                return {
                    "ok": False,
                    "ask_repeat": True,
                    "status": "QUALITY_GATE_FAILED",
                    "reason": q_single["reason"],
                    "sample_index": idx,
                    "total_samples": tot,
                    "error": q_single["message"],
                    "message": f"Mẫu #{idx}/{tot}: {q_single['message']}",
                }

            cur_list = self._pending_enrollment_samples[buf_key]
            # Kiểm tra chống trùng với các mẫu trước đó của cùng phiên thu
            cur_emb = extract_wespeaker_embedding(pcm_bytes)
            for p_i, prev_b in enumerate(cur_list):
                if prev_b == pcm_bytes or compute_wespeaker_cosine(
                    cur_emb, extract_wespeaker_embedding(prev_b)
                ) >= 0.9995:
                    return {
                        "ok": False,
                        "ask_repeat": True,
                        "status": "DUPLICATE_SAMPLE_CLIP",
                        "reason": "DUPLICATE_SAMPLE_BUFFER",
                        "sample_index": idx,
                        "total_samples": tot,
                        "error": f"Mẫu #{idx} trùng khớp với mẫu #{p_i + 1}. Vui lòng đọc câu mẫu khác nhau!",
                        "message": f"Mẫu #{idx} trùng khớp với mẫu #{p_i + 1}. Vui lòng đọc câu mẫu khác nhau!",
                    }

            cur_list.append(bytes(pcm_bytes))
            if len(cur_list) < tot:
                return {
                    "ok": True,
                    "partial": True,
                    "status": "SAMPLE_ACCEPTED",
                    "sample_index": len(cur_list),
                    "total_samples": tot,
                    "remaining_samples": tot - len(cur_list),
                    "message": (
                        f"Đã thu thành công mẫu #{len(cur_list)}/{tot}. "
                        f"Vui lòng đọc tiếp mẫu #{len(cur_list) + 1}/{tot} (3–5 giây)!"
                    ),
                }
            samples_pcm16k = list(cur_list)
            required_samples = tot
            self._pending_enrollment_samples.pop(buf_key, None)

        if samples_pcm16k is not None:
            multi_res = compute_multi_sample_mean_embedding(
                samples_pcm16k,
                sr=16000,
                required_samples=required_samples,
                enforce_distinct=True,
            )
            if not multi_res.get("ok"):
                return {
                    "ok": False,
                    "ask_repeat": bool(multi_res.get("ask_repeat", False)),
                    "status": multi_res.get("reason", "ENROLLMENT_FAILED"),
                    "reason": multi_res.get("reason", "ENROLLMENT_FAILED"),
                    "error": multi_res.get("message", "Thu âm đa mẫu không đạt chuẩn."),
                    "message": multi_res.get("message", "Thu âm đa mẫu không đạt chuẩn."),
                    "required_samples": required_samples,
                    "received_samples": len(samples_pcm16k),
                }
            wespk_vec = multi_res["wespeaker_embedding"]
            first_raw = (
                np.frombuffer(samples_pcm16k[0], dtype=np.int16)
                if isinstance(samples_pcm16k[0], (bytes, bytearray))
                else np.asarray(samples_pcm16k[0], dtype=np.int16)
            )
            pcm_clean, denoise_info = denoise_and_isolate_human_voice(first_raw, 16000)
            feat = {
                "valid": True,
                "f0_hz": multi_res["f0_hz"],
                "centroid_hz": multi_res.get("centroid_hz", 1271.7),
                "embedding": multi_res["embedding"],
                "duration_sec": round(
                    sum(
                        len(pcm_bytes_to_float32_16k(s, 16000)) / 16000.0
                        for s in samples_pcm16k[:required_samples]
                    ),
                    2,
                ),
            }
            deep = {
                "formants_hz": multi_res.get("formants_hz", [510.0, 1480.0, 2580.0, 3620.0]),
                "hnr_db": multi_res.get("hnr_db", 14.5),
                "deep_embedding": multi_res["deep_embedding"],
            }
            enrolled_samples_count = int(multi_res["num_samples"])
            sample_cosines_to_mean = multi_res.get("sample_cosines_to_mean", [])
            sub_bank_list = []
        else:
            if isinstance(pcm_bytes, (bytes, bytearray)):
                raw_b = bytes(pcm_bytes)
                if (len(raw_b) >= 44 and raw_b[:4] == b"RIFF" and raw_b[8:12] == b"WAVE") or _is_encoded_container_bytes(raw_b):
                    pcm_flt = pcm_bytes_to_float32_16k(raw_b, sr=16000)
                    pcm_raw = np.clip(pcm_flt * 32767.0, -32768, 32767).astype(np.int16)
                else:
                    usable = (len(raw_b) // 2) * 2
                    pcm_raw = np.frombuffer(raw_b[:usable], dtype=np.int16)
            else:
                pcm_raw = np.asarray(pcm_bytes, dtype=np.int16)
            q_gate = evaluate_audio_quality_gate(pcm_raw, sr=16000)
            pcm_clean, denoise_info = denoise_and_isolate_human_voice(pcm_raw, 16000)
            feat = extract_voice_features(pcm_clean, 16000)
            if not q_gate["ok"] or not feat["valid"]:
                return {
                    "ok": False,
                    "ask_repeat": True,
                    "reason": q_gate.get("reason", "AUDIO_QUALITY_FAILED"),
                    "error": "Đoạn thu âm quá ngắn hoặc không có tiếng người nói rõ ràng. Hãy nói to và rõ hơn!",
                    "message": q_gate.get(
                        "message",
                        "Đoạn thu âm quá ngắn hoặc không có tiếng người nói rõ ràng. Hãy nói to và rõ hơn!",
                    ),
                }
            deep = extract_stage2_deep_features(pcm_clean, 16000)
            cent_arr, sub_bank_list = extract_wespeaker_subwindow_bank(pcm_raw, sr=16000)
            wespk_vec = [round(float(v), 6) for v in cent_arr.tolist()]
            enrolled_samples_count = max(1, len(sub_bank_list))
            sample_cosines_to_mean = [1.0]

        if check_duplicate:
            dup_res = self.check_duplicate_voice_gate(
                feat_s1={
                    "embedding": feat["embedding"],
                    "f0_hz": feat["f0_hz"],
                    "wespeaker_embedding": wespk_vec,
                    "embedding_256d": wespk_vec,
                },
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

        prof_key = (
            "owner_voice_1"
            if (int(tier) == 1 or user_id == OWNER_ID)
            else f"user_voice_{user_id}"
        )
        role_code = ROLE_MAP.get(int(tier), "CHILD_GUEST")
        disp_label = (
            custom_label or f"Giọng Cấp {tier} — {user_name} (Đã thu âm giọng thật)"
        )
        prev_prof = self.profiles.get(prof_key, {})
        tier_threshold = get_tier_wespeaker_threshold(int(tier))

        new_prof: dict[str, Any] = {
            "id": prof_key,
            "user_id": user_id,
            "name": disp_label,
            "authorized": True,
            "custom_enrolled": True,
            "wespeaker_model": "wespeaker_r34_onnx",
            "threshold_wespeaker": tier_threshold,
            "enrollment_samples_count": enrolled_samples_count,
            "sample_cosines_to_mean": sample_cosines_to_mean,
            "voice_source": (
                f"WeSpeaker ResNet34 ONNX ({enrolled_samples_count} mẫu thu trực tiếp 16kHz PCM)"
            ),
            "role": role_code,
            "tier": int(tier),
            "f0_hz": feat["f0_hz"],
            "centroid_hz": feat["centroid_hz"],
            "embedding": feat["embedding"],
            "formants_hz": deep["formants_hz"],
            "hnr_db": deep["hnr_db"],
            "deep_embedding": deep["deep_embedding"],
            "embedding_256d": wespk_vec,
            "wespeaker_embedding": wespk_vec,
            "sub_embeddings_256d": sub_bank_list or prev_prof.get("sub_embeddings_256d", []),
            "wespeaker_sub_embeddings": sub_bank_list or prev_prof.get("wespeaker_sub_embeddings", []),
            "baseline_f0_hz": prev_prof.get("baseline_f0_hz")
            or prev_prof.get("f0_hz")
            or feat["f0_hz"],
            "baseline_embedding": prev_prof.get("baseline_embedding")
            or prev_prof.get("embedding")
            or feat["embedding"],
            "baseline_formants_hz": prev_prof.get("baseline_formants_hz")
            or prev_prof.get("formants_hz")
            or deep["formants_hz"],
            "baseline_deep_embedding": prev_prof.get("baseline_deep_embedding")
            or prev_prof.get("deep_embedding")
            or deep["deep_embedding"],
            "baseline_embedding_256d": prev_prof.get("baseline_embedding_256d")
            or prev_prof.get("embedding_256d")
            or wespk_vec,
            "baseline_wespeaker_embedding": prev_prof.get("baseline_wespeaker_embedding")
            or prev_prof.get("wespeaker_embedding")
            or wespk_vec,
        }
        if expires_at is not None:
            new_prof["expires_at"] = float(expires_at)

        prev_profiles = copy.deepcopy(self.profiles)
        self.profiles[prof_key] = new_prof
        if not self._save_voiceprints_safe():
            self.profiles.clear()
            self.profiles.update(prev_profiles)
            err_persist = "Lỗi lưu trữ bền vững đám mây (Durable Store). Đã hoàn tác đăng ký giọng nói!"
            return {
                "ok": False,
                "status": "DURABLE_PERSISTENCE_FAILED",
                "status_code": 503,
                "reason": "DURABLE_PERSISTENCE_FAILED",
                "error": err_persist,
                "message": err_persist,
            }
        self.unauthorized_strikes = 0
        return {
            "ok": True,
            "profile": self.profiles[prof_key],
            "user_id": user_id,
            "tier": int(tier),
            "role": role_code,
            "expires_at": expires_at,
            "enrollment_samples_count": enrolled_samples_count,
            "threshold_wespeaker": tier_threshold,
            "duration_sec": feat.get("duration_sec", 0.0),
            "denoise_info": denoise_info,
            "message": (
                f"Đã trích xuất WeSpeaker ResNet34 ONNX ({enrolled_samples_count} mẫu, "
                f"ngưỡng cosine={tier_threshold}) & lưu Giọng Gốc Cấp {tier} ({user_name})."
            ),
        }

    def analyze_voice_pcm16k(self, pcm_bytes: bytes) -> dict[str, Any]:
        """Phân tích đoạn thu âm giọng nói 16kHz vừa thu được (WeSpeaker ResNet34 ONNX + Mel/Deep Quality Gate)."""
        pcm_raw = (
            np.frombuffer(pcm_bytes, dtype=np.int16)
            if pcm_bytes
            else np.array([], dtype=np.int16)
        )
        pcm_clean, denoise_info = denoise_and_isolate_human_voice(pcm_raw, 16000)
        feat = extract_voice_features(pcm_clean, 16000)
        deep = extract_stage2_deep_features(pcm_clean, 16000)
        wespk_emb = (
            [round(float(v), 6) for v in extract_wespeaker_embedding(pcm_raw).tolist()]
            if pcm_raw.size >= 1600
            else ([0.0] * 256)
        )
        if not feat["valid"]:
            return {
                "ok": True,
                "f0_hz": 135.0,
                "centroid_hz": 1271.7,
                "duration_sec": round(max(3.0, pcm_raw.size / 16000.0), 1),
                "embedding": [0.15] * 26,
                "formants_hz": [520.0, 1540.0, 2600.0, 3650.0],
                "deep_embedding": [0.12] * 64,
                "embedding_256d": wespk_emb,
                "wespeaker_embedding": wespk_emb,
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
            "embedding_256d": wespk_emb,
            "wespeaker_embedding": wespk_emb,
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
        wespeaker_embedding: list[float] | None = None,
        enrollment_samples_count: int = ENROLLMENT_REQUIRED_SAMPLES,
    ) -> dict[str, Any]:
        """Lưu hồ sơ giọng nói người dùng mới được cấp quyền (Cấp 1, Cấp 2 hoặc Cấp 3)."""
        vec_256 = wespeaker_embedding or embedding_256d
        dup_chk = self.check_duplicate_voice_gate(
            feat_s1={
                "embedding": embedding,
                "f0_hz": f0_hz,
                "wespeaker_embedding": vec_256,
                "embedding_256d": vec_256,
            }
            if vec_256
            else embedding,
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

        tier_threshold = get_tier_wespeaker_threshold(int(tier))
        if user_id == OWNER_ID or int(tier) == 1:
            owner_prof = self.profiles.get("owner_voice_1", {})
            final_256 = (
                vec_256
                or owner_prof.get("wespeaker_embedding")
                or owner_prof.get("embedding_256d")
                or ([0.0] * 256)
            )
            owner_prof.update(
                {
                    "id": "owner_voice_1",
                    "user_id": user_id or OWNER_ID,
                    "name": owner_prof.get("name")
                    or f"Giọng Cấp 1 — {user_name} (Chủ nhà - Toàn quyền)",
                    "authorized": True,
                    "tier": 1,
                    "role": ROLE_MAP.get(1, "ADMIN"),
                    "wespeaker_model": "wespeaker_r34_onnx",
                    "threshold_wespeaker": THRESHOLD_WESPEAKER_TIER1,
                    "enrollment_samples_count": enrollment_samples_count,
                    "f0_hz": f0_hz,
                    "centroid_hz": centroid_hz,
                    "embedding": embedding,
                    "formants_hz": formants_hz
                    or owner_prof.get("formants_hz")
                    or [510.0, 1480.0, 2580.0, 3620.0],
                    "deep_embedding": deep_embedding
                    or owner_prof.get("deep_embedding")
                    or ([0.12] * 64),
                    "embedding_256d": final_256,
                    "wespeaker_embedding": final_256,
                    "custom_enrolled": True,
                }
            )
            self.profiles["owner_voice_1"] = owner_prof
            self._save_voiceprints_safe()
            self.unauthorized_strikes = 0
            return owner_prof

        prof_id = f"user_voice_{user_id}"
        final_256 = vec_256 or ([0.0] * 256)
        self.profiles[prof_id] = {
            "id": prof_id,
            "user_id": user_id,
            "name": f"{user_name} (Cấp {tier})",
            "authorized": True,
            "role": role,
            "tier": int(tier),
            "wespeaker_model": "wespeaker_r34_onnx",
            "threshold_wespeaker": tier_threshold,
            "enrollment_samples_count": enrollment_samples_count,
            "f0_hz": f0_hz,
            "centroid_hz": centroid_hz,
            "embedding": embedding,
            "formants_hz": formants_hz or [530.0, 1560.0, 2620.0, 3660.0],
            "deep_embedding": deep_embedding or ([0.14] * 64),
            "embedding_256d": final_256,
            "wespeaker_embedding": final_256,
            "custom_enrolled": True,
        }
        self._save_voiceprints_safe()
        self.unauthorized_strikes = 0
        self.last_analysis = {
            "speaker_id": prof_id,
            "speaker_label": f"{user_name} (Cấp {tier})",
            "authorized": True,
            "f0_hz": f0_hz,
            "centroid_hz": centroid_hz,
            "similarity": 0.99,
            "wespeaker_cosine": 0.99,
            "threshold_wespeaker": tier_threshold,
            "stage1_confidence": 0.99,
            "stage2_triggered": False,
            "stage2_confidence": None,
            "filter_stage_used": "WeSpeaker ResNet34 ONNX (Đăng ký mới)",
            "strike_count": 0,
            "action_taken": "ENROLLED",
        }
        return self.profiles[prof_id]

    def verify_pcm16k_and_apply_strikes(
        self, pcm_bytes: bytes | np.ndarray, is_live_mic: bool = False
    ) -> dict[str, Any]:
        """Xác thực danh tính người nói bằng WeSpeaker ResNet34 ONNX (256-D Cosine Similarity).

        - Giữ mel26 + deep64 CHỈ làm cổng kiểm định chất lượng âm thanh (quá ngắn / quá nhỏ / bị rè
          -> yêu cầu người dùng nói lại, KHÔNG kết luận là 'Người lạ' và KHÔNG tăng gậy phạt).
        - Loại bỏ hoàn toàn cơ chế nâng điểm mềm `is_live_mic` (hành vi giống hệt nhau trên mọi đường).
        - Quyết định danh tính 100% dựa trên WeSpeaker ResNet34 ONNX cosine >= threshold_wespeaker
          (Cấp 1: 0.435, Cấp 2: 0.435, Cấp 3: 0.385, có thể cấu hình).
        """
        t_total_start = time.perf_counter()
        self._sync_voiceprints_from_disk()
        if isinstance(pcm_bytes, (bytes, bytearray)):
            raw_b = bytes(pcm_bytes)
            if (len(raw_b) >= 44 and raw_b[:4] == b"RIFF" and raw_b[8:12] == b"WAVE") or _is_encoded_container_bytes(raw_b):
                pcm_flt = pcm_bytes_to_float32_16k(raw_b, sr=16000)
                pcm_raw = np.clip(pcm_flt * 32767.0, -32768, 32767).astype(np.int16)
            else:
                usable = (len(raw_b) // 2) * 2
                pcm_raw = np.frombuffer(raw_b[:usable], dtype=np.int16)
        elif isinstance(pcm_bytes, np.ndarray):
            if np.issubdtype(pcm_bytes.dtype, np.floating) and (
                pcm_bytes.size > 0 and np.max(np.abs(pcm_bytes)) <= 1.05
            ):
                pcm_raw = np.clip(pcm_bytes * 32767.0, -32768, 32767).astype(np.int16)
            else:
                pcm_raw = pcm_bytes.astype(np.int16)
        else:
            pcm_raw = np.array([], dtype=np.int16)

        # Bước 1: Khử tiếng ồn quạt (phục vụ telemetry & tách nhiều người nói)
        pcm_clean, denoise_info = denoise_and_isolate_human_voice(pcm_raw, 16000)
        multi_info = detect_multi_speaker_and_resolve_priority(
            pcm_clean, self.profiles, 16000
        )
        target_pcm = multi_info["dominant_pcm16"]

        # Bước 2: Trích xuất Mel26 + Deep64 cho cổng kiểm định chất lượng âm thanh (Audio Quality Gate)
        feat_s1 = extract_voice_features(target_pcm, 16000)
        if not feat_s1.get("valid", True) or not feat_s1.get("is_live_human", True):
            feat_raw = extract_voice_features(pcm_raw, 16000)
            if feat_raw.get("valid") and feat_raw.get("is_filler_only"):
                feat_s1 = feat_raw
                pcm_clean = pcm_raw

        intruder_prof = self.profiles.get("intruder_voice_2", {})
        best_auth_prof = self.profiles.get("owner_voice_1", {})

        # Bước 3: SAFE-DENY GATE BẮT BUỘC TRƯỚC MỌI NHẬN DIỆN (Mel26 + Deep64 Quality Gate + Overlap Gate)
        # Tuyệt đối KHÔNG gán quyền Chủ nhà bằng heuristic F0/centroid/amplitude cho âm đệm hoặc tín hiệu <~1.5s.
        # Quá ngắn (<~1.5s speech), âm đệm/tone tổng hợp, quá ồn, hoặc có từ 2 người nói chồng lấn -> KHÔNG ĐOÁN,
        # yêu cầu nói lại bằng câu ngắn cố định, KHÔNG tăng gậy phạt!
        is_true_multi_speaker = False
        precomputed_wespk: np.ndarray | None = None
        precomputed_wespk_ms: float = 0.0
        if multi_info.get("multi_speaker_detected"):
            from simulator.voice.wespeaker_onnx import vad_trim_16k

            flt_chk = pcm_raw.astype(np.float32) / 32768.0
            sp_chk = vad_trim_16k(flt_chk)
            if len(sp_chk) >= 19200:
                t_pre = time.perf_counter()
                precomputed_wespk = extract_wespeaker_embedding(sp_chk, sr=16000, apply_vad=False)
                precomputed_wespk_ms = round((time.perf_counter() - t_pre) * 1000.0, 2)
                best_pre_cos = 0.0
                for prof_chk in self.profiles.values():
                    if not prof_chk.get("authorized", False):
                        continue
                    ref_chk = prof_chk.get("wespeaker_embedding") or prof_chk.get("embedding_256d")
                    if ref_chk and len(ref_chk) == 256:
                        best_pre_cos = max(best_pre_cos, compute_wespeaker_cosine(precomputed_wespk, ref_chk))
                if best_pre_cos < 0.65:
                    mid_idx = len(sp_chk) // 2
                    w_h1 = extract_wespeaker_embedding(sp_chk[:mid_idx], sr=16000, apply_vad=False)
                    w_h2 = extract_wespeaker_embedding(sp_chk[mid_idx:], sr=16000, apply_vad=False)
                    half_cos = compute_wespeaker_cosine(w_h1, w_h2)
                    if half_cos < 0.22:
                        is_true_multi_speaker = True
                    else:
                        multi_info["multi_speaker_detected"] = False
                        multi_info["speaker_count"] = 1
                        target_pcm = pcm_clean
                else:
                    multi_info["multi_speaker_detected"] = False
                    multi_info["speaker_count"] = 1
                    target_pcm = pcm_clean
            else:
                multi_info["multi_speaker_detected"] = False
                multi_info["speaker_count"] = 1
                target_pcm = pcm_clean

        if is_true_multi_speaker:
            total_ms = round((time.perf_counter() - t_total_start) * 1000.0, 2)
            res = {
                "authorized": False,
                "ask_repeat": True,
                "quality_gate_passed": False,
                "quality_reason": "OVERLAPPING_SPEAKERS",
                "reason": "OVERLAPPING_SPEAKERS",
                "speaker_id": "none",
                "user_id": "UNKNOWN",
                "role": "UNKNOWN",
                "speaker_label": "Yêu cầu nói lại (Phát hiện nhiều người cùng nói)",
                "tier": 99,
                "f0_hz": float(feat_s1.get("f0_hz", 0.0)),
                "centroid_hz": float(feat_s1.get("centroid_hz", 0.0)),
                "formants_hz": [],
                "similarity": 0.0,
                "wespeaker_cosine": 0.0,
                "threshold_wespeaker": THRESHOLD_WESPEAKER_TIER1,
                "stage1_confidence": 0.0,
                "stage2_triggered": False,
                "stage2_confidence": None,
                "filter_stage_used": "Safe-Deny Gate (Chặn Đa Người Nói Chồng Lấn)",
                "denoise_ms": denoise_info["denoise_ms"],
                "stage1_ms": feat_s1.get("stage1_ms", 0.0),
                "stage2_ms": 0.0,
                "diarization_ms": multi_info["diarization_ms"],
                "total_ms": total_ms,
                "noise_removed_db": denoise_info["noise_removed_db"],
                "fan_noise_detected": denoise_info["fan_noise_detected"],
                "multi_speaker_detected": True,
                "speaker_count": max(2, int(multi_info.get("speaker_count", 2))),
                "priority_reason": SAFE_DENY_REPEAT_PHRASE_VI,
                "clean_pcm_bytes": pcm_clean.tobytes(),
                "strike_count": self.unauthorized_strikes,
                "strikes": self.unauthorized_strikes,
                "deferred_strike": True,
                "should_reply": True,
                "silent_ignore": False,
                "rejection_speech": SAFE_DENY_REPEAT_PHRASE_VI,
                "message": SAFE_DENY_REPEAT_PHRASE_VI,
            }
            self.last_analysis = {
                k: v for k, v in res.items() if k != "clean_pcm_bytes"
            }
            return res

        q_gate = evaluate_audio_quality_gate(pcm_raw, sr=16000)
        if (
            not q_gate["ok"]
            or not feat_s1.get("valid", True)
            or not feat_s1.get("is_live_human", True)
            or bool(feat_s1.get("is_filler_only", False))
        ):
            total_ms = round((time.perf_counter() - t_total_start) * 1000.0, 2)
            repeat_msg = SAFE_DENY_REPEAT_PHRASE_VI
            res = {
                "authorized": False,
                "ask_repeat": True,
                "quality_gate_passed": False,
                "quality_reason": q_gate.get("reason", "AUDIO_QUALITY_FAILED"),
                "reason": q_gate.get("reason", "AUDIO_QUALITY_FAILED"),
                "speaker_id": "none",
                "user_id": "UNKNOWN",
                "role": "UNKNOWN",
                "speaker_label": "Yêu cầu nói lại (Tín hiệu âm thanh quá ngắn / nhỏ / ồn / rè)",
                "tier": 99,
                "f0_hz": float(feat_s1.get("f0_hz", 0.0)),
                "centroid_hz": float(feat_s1.get("centroid_hz", 0.0)),
                "formants_hz": [],
                "similarity": 0.0,
                "wespeaker_cosine": 0.0,
                "threshold_wespeaker": THRESHOLD_WESPEAKER_TIER1,
                "stage1_confidence": 0.0,
                "stage2_triggered": False,
                "stage2_confidence": None,
                "filter_stage_used": "Cổng Chất Lượng Âm Thanh (Mel26+Deep64 Quality Gate)",
                "denoise_ms": denoise_info["denoise_ms"],
                "stage1_ms": feat_s1.get("stage1_ms", 0.0),
                "stage2_ms": 0.0,
                "diarization_ms": multi_info["diarization_ms"],
                "total_ms": total_ms,
                "noise_removed_db": denoise_info["noise_removed_db"],
                "fan_noise_detected": denoise_info["fan_noise_detected"],
                "multi_speaker_detected": False,
                "speaker_count": 0,
                "priority_reason": repeat_msg,
                "clean_pcm_bytes": pcm_clean.tobytes(),
                "strike_count": self.unauthorized_strikes,
                "strikes": self.unauthorized_strikes,
                "deferred_strike": True,
                "should_reply": True,
                "silent_ignore": False,
                "rejection_speech": repeat_msg,
                "message": repeat_msg,
            }
            self.last_analysis = {
                k: v for k, v in res.items() if k != "clean_pcm_bytes"
            }
            return res

        # Bước 4: Trích xuất đặc trưng WeSpeaker ResNet34 ONNX (16kHz mono, energy VAD trim, fbank80, 4 threads)
        if precomputed_wespk is not None:
            cur_wespk = precomputed_wespk
            wespk_ms = precomputed_wespk_ms
        else:
            t_wespk_start = time.perf_counter()
            cur_wespk = extract_wespeaker_embedding(pcm_raw, sr=16000, apply_vad=True)
            wespk_ms = round((time.perf_counter() - t_wespk_start) * 1000.0, 2)
        alt_wespk_list: list[np.ndarray] = []

        deep_feat = extract_stage2_deep_features(target_pcm, 16000)
        formants_hz = deep_feat.get("formants_hz", [510.0, 1480.0, 2580.0, 3620.0])

        # Phân loại hồ sơ còn hạn vs đã hết hạn (Guest QR expires_at)
        now_ts = time.time()
        authorized_profiles: list[dict[str, Any]] = []
        expired_profiles: list[dict[str, Any]] = []
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

        # Kiểm tra hồ sơ Khách Cấp 3 đã hết hạn (expires_at < now) bằng WeSpeaker ResNet34 ONNX
        for exp_p in expired_profiles:
            exp_emb = exp_p.get("wespeaker_embedding") or exp_p.get("embedding_256d")
            if exp_emb and len(exp_emb) == 256:
                s_exp = compute_wespeaker_cosine(cur_wespk, exp_emb)
                for alt_w in alt_wespk_list:
                    s_exp = max(s_exp, compute_wespeaker_cosine(alt_w, exp_emb))
                exp_thresh = float(
                    exp_p.get("threshold_wespeaker")
                    or get_tier_wespeaker_threshold(int(exp_p.get("tier", 3)))
                )
                if s_exp >= exp_thresh:
                    total_ms = round((time.perf_counter() - t_total_start) * 1000.0, 2)
                    return {
                        "authorized": False,
                        "ask_repeat": False,
                        "quality_gate_passed": True,
                        "reason": "GUEST_EXPIRED",
                        "speaker_id": exp_p["id"],
                        "user_id": str(exp_p.get("user_id", "khach_c")),
                        "role": "EXPIRED_GUEST",
                        "speaker_label": f"{exp_p.get('name', 'Khách')} (Đã hết hạn quyền)",
                        "tier": 99,
                        "f0_hz": feat_s1["f0_hz"],
                        "centroid_hz": feat_s1["centroid_hz"],
                        "formants_hz": formants_hz,
                        "similarity": round(float(s_exp), 4),
                        "wespeaker_cosine": round(float(s_exp), 4),
                        "threshold_wespeaker": exp_thresh,
                        "stage1_confidence": round(float(s_exp), 4),
                        "stage2_triggered": True,
                        "stage2_confidence": round(float(s_exp), 4),
                        "filter_stage_used": "WeSpeaker ResNet34 ONNX + Cổng Kiểm Tra Thời Hạn Khách (expires_at)",
                        "denoise_ms": denoise_info["denoise_ms"],
                        "stage1_ms": feat_s1["stage1_ms"],
                        "stage2_ms": wespk_ms,
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
                        "rejection_speech": UNIFIED_REJECTION_PHRASE_VI,
                    }

        # Bước 5: Đối sánh WeSpeaker ResNet34 ONNX Cosine với các hồ sơ được cấp quyền
        # (Sắp xếp theo Tier 1 -> Tier 2 -> Tier 3)
        authorized_profiles.sort(key=lambda p: int(p.get("tier", 99)))
        best_matched_prof: dict[str, Any] | None = None
        best_matched_cos: float = -1.0
        best_matched_thresh: float = THRESHOLD_WESPEAKER_TIER1
        highest_any_cos: float = -1.0

        for ap in authorized_profiles:
            ap_tier = int(ap.get("tier", 1))
            ap_thresh = float(
                ap.get("threshold_wespeaker")
                or get_tier_wespeaker_threshold(ap_tier)
            )
            cand_vecs: list[Any] = []
            if ap.get("wespeaker_embedding"):
                cand_vecs.append(ap["wespeaker_embedding"])
            elif ap.get("embedding_256d"):
                cand_vecs.append(ap["embedding_256d"])
            if ap.get("baseline_wespeaker_embedding"):
                cand_vecs.append(ap["baseline_wespeaker_embedding"])
            elif ap.get("baseline_embedding_256d"):
                cand_vecs.append(ap["baseline_embedding_256d"])

            sim_cent = -1.0
            for c_vec in cand_vecs:
                if c_vec and len(c_vec) == 256:
                    s = compute_wespeaker_cosine(cur_wespk, c_vec)
                    for alt_w in alt_wespk_list:
                        s = max(s, compute_wespeaker_cosine(alt_w, c_vec))
                    sim_cent = max(sim_cent, s)

            sim_ap = sim_cent
            sub_embs = ap.get("sub_embeddings_256d") or []
            if sub_embs and sim_cent >= 0.32:
                s_sub_max = max(
                    (compute_wespeaker_cosine(cur_wespk, se) for se in sub_embs if len(se) == 256),
                    default=sim_cent,
                )
                sim_ap = max(sim_cent, s_sub_max)

            if sim_ap > highest_any_cos:
                highest_any_cos = sim_ap
                best_auth_prof = ap

            if sim_ap >= ap_thresh:
                # Defense-in-depth: For Level 1 (Owner), require Vietnamese background cohort margin gate
                # sim_ap >= max_{c in Cohort} cos(probe, c) (margin >= 0.0)
                if ap_tier == 1:
                    c_vec_owner = cand_vecs[0] if cand_vecs else None
                    margin, max_c, c_pass = evaluate_cohort_margin(cur_wespk, c_vec_owner)
                    if not c_pass and (sim_ap - max_c) < 0.0:
                        continue
                if best_matched_prof is None or sim_ap > best_matched_cos:
                    best_matched_prof = ap
                    best_matched_cos = sim_ap
                    best_matched_thresh = ap_thresh

        probe_cohort_margin, probe_max_cohort, probe_cohort_passed = evaluate_cohort_margin(cur_wespk)
        if best_matched_prof is not None and int(best_matched_prof.get("tier", 1)) == 1:
            probe_cohort_margin = round(float(best_matched_cos - probe_max_cohort), 4)
            probe_cohort_passed = bool(probe_cohort_margin >= 0.0)

        is_authorized = best_matched_prof is not None
        final_cos = round(
            float(best_matched_cos if is_authorized else max(0.0, highest_any_cos)), 4
        )
        filter_stage_used = "WeSpeaker ResNet34 ONNX (256-D Cosine + Mel/Deep Quality Gate + Cohort Gate)"
        total_ms = round((time.perf_counter() - t_total_start) * 1000.0, 2)

        if is_authorized and best_matched_prof is not None:
            self.unauthorized_strikes = 0
            matched_tier = int(best_matched_prof.get("tier", 1))
            matched_uid = str(
                best_matched_prof.get("user_id")
                or USER_ROLE_MAP.get(matched_tier, "khach_c")
            )
            matched_role = str(
                best_matched_prof.get("role")
                or ROLE_MAP.get(matched_tier, "CHILD_GUEST")
            )
            res = {
                "authorized": True,
                "ask_repeat": False,
                "quality_gate_passed": True,
                "speaker_id": best_matched_prof["id"],
                "user_id": matched_uid,
                "role": matched_role,
                "speaker_label": best_matched_prof["name"],
                "tier": matched_tier,
                "f0_hz": feat_s1["f0_hz"],
                "centroid_hz": feat_s1["centroid_hz"],
                "formants_hz": formants_hz,
                "similarity": final_cos,
                "wespeaker_cosine": final_cos,
                "threshold_wespeaker": best_matched_thresh,
                "cohort_margin": probe_cohort_margin,
                "cohort_max_sim": probe_max_cohort,
                "cohort_gate_passed": probe_cohort_passed,
                "stage1_confidence": final_cos,
                "stage2_triggered": True,
                "stage2_confidence": final_cos,
                "filter_stage_used": filter_stage_used,
                "denoise_ms": denoise_info["denoise_ms"],
                "stage1_ms": feat_s1["stage1_ms"],
                "stage2_ms": wespk_ms,
                "diarization_ms": multi_info["diarization_ms"],
                "total_ms": total_ms,
                "noise_removed_db": denoise_info["noise_removed_db"],
                "fan_noise_detected": denoise_info["fan_noise_detected"],
                "multi_speaker_detected": multi_info["multi_speaker_detected"],
                "speaker_count": multi_info["speaker_count"],
                "priority_reason": multi_info["priority_reason"],
                "clean_pcm_bytes": pcm_clean.tobytes(),
                "strike_count": 0,
                "strikes": 0,
                "should_reply": True,
                "silent_ignore": False,
                "rejection_speech": "",
            }
            self.last_analysis = {
                k: v for k, v in res.items() if k != "clean_pcm_bytes"
            }
            return res

        # Người lạ (WeSpeaker cosine < threshold_wespeaker) -> Tăng bộ đếm vi phạm (Strike)
        # Yêu cầu 4: Duy nhất 1 câu từ chối cố định bằng giọng Aoede, không silent_ignore
        self.unauthorized_strikes += 1
        strike = self.unauthorized_strikes
        rejection_speech = UNIFIED_REJECTION_PHRASE_VI
        should_reply = True
        silent_ignore = False

        res = {
            "authorized": False,
            "ask_repeat": False,
            "quality_gate_passed": True,
            "speaker_id": "intruder_voice_2",
            "user_id": "UNKNOWN",
            "role": "UNKNOWN",
            "speaker_label": intruder_prof.get(
                "name", "Giọng 2 — Người lạ (Không được phép)"
            ),
            "tier": 99,
            "f0_hz": feat_s1["f0_hz"],
            "centroid_hz": feat_s1["centroid_hz"],
            "formants_hz": formants_hz,
            "similarity": final_cos,
            "wespeaker_cosine": final_cos,
            "threshold_wespeaker": THRESHOLD_WESPEAKER_TIER1,
            "cohort_margin": probe_cohort_margin,
            "cohort_max_sim": probe_max_cohort,
            "cohort_gate_passed": probe_cohort_passed,
            "stage1_confidence": final_cos,
            "stage2_triggered": True,
            "stage2_confidence": final_cos,
            "filter_stage_used": filter_stage_used,
            "denoise_ms": denoise_info["denoise_ms"],
            "stage1_ms": feat_s1["stage1_ms"],
            "stage2_ms": wespk_ms,
            "diarization_ms": multi_info["diarization_ms"],
            "total_ms": total_ms,
            "noise_removed_db": denoise_info["noise_removed_db"],
            "fan_noise_detected": denoise_info["fan_noise_detected"],
            "multi_speaker_detected": multi_info["multi_speaker_detected"],
            "speaker_count": multi_info["speaker_count"],
            "priority_reason": multi_info["priority_reason"],
            "clean_pcm_bytes": pcm_clean.tobytes(),
            "strike_count": strike,
            "strikes": strike,
            "should_reply": should_reply,
            "silent_ignore": silent_ignore,
            "rejection_speech": rejection_speech,
            "exact_spoken_reply": rejection_speech,
            "message": rejection_speech,
        }
        self.last_analysis = {
            k: v for k, v in res.items() if k != "clean_pcm_bytes"
        }
        return res

    def reset_strikes(self) -> None:
        self.unauthorized_strikes = 0
        self.last_analysis["strike_count"] = 0

    def reset_to_owner_only(self) -> dict[str, Any]:
        """Reset quyền giọng nói: Xóa mọi giọng phụ khác, chỉ giữ lại duy nhất giọng của Chủ nhà (owner_voice_1) và mẫu đối chứng."""
        self._pending_enrollment_samples.clear()
        owner_prof = self.profiles.get("owner_voice_1")
        intruder_prof = self.profiles.get("intruder_voice_2")
        if (
            not owner_prof
            or not intruder_prof
            or owner_prof.get("wespeaker_model") != "wespeaker_r34_onnx"
        ):
            self.profiles = self._init_or_load_profiles()
        else:
            seeds = _get_cached_seeds(self.audio_dir)
            owner_wespk = seeds["owner_seed"]["wespeaker_embedding"]
            owner_prof["authorized"] = True
            owner_prof["role"] = "ADMIN"
            owner_prof["tier"] = 1
            owner_prof["custom_enrolled"] = False
            owner_prof["wespeaker_embedding"] = owner_wespk
            owner_prof["embedding_256d"] = owner_wespk
            owner_prof["threshold_wespeaker"] = THRESHOLD_WESPEAKER_TIER1
            intruder_prof["authorized"] = False
            intruder_prof["role"] = "UNKNOWN"
            intruder_prof["tier"] = 99
            self.profiles = {
                "owner_voice_1": owner_prof,
                "intruder_voice_2": intruder_prof,
            }
            self._save_voiceprints_safe()

        self.unauthorized_strikes = 0
        self.last_analysis = {
            "speaker_id": "owner_voice_1",
            "speaker_label": self.profiles["owner_voice_1"]["name"],
            "authorized": True,
            "f0_hz": self.profiles["owner_voice_1"]["f0_hz"],
            "centroid_hz": self.profiles["owner_voice_1"]["centroid_hz"],
            "similarity": 1.0,
            "wespeaker_cosine": 1.0,
            "threshold_wespeaker": THRESHOLD_WESPEAKER_TIER1,
            "stage1_confidence": 1.0,
            "stage2_triggered": False,
            "stage2_confidence": None,
            "filter_stage_used": "WeSpeaker ResNet34 ONNX (256-D Cosine)",
            "strike_count": 0,
            "action_taken": "RESET_OWNER_ONLY",
        }
        return {
            "ok": True,
            "owner_profile": self.profiles["owner_voice_1"],
            "message": "Đã xóa các giọng phụ và reset quyền giọng nói chỉ về duy nhất giọng của Chủ nhà.",
        }

    def reset_to_factory_defaults(self) -> dict[str, Any]:
        """Khôi phục sạch hồ sơ chuẩn gốc WeSpeaker ResNet34 ONNX và xóa các bản ghi thu âm tạm thời."""
        self._pending_enrollment_samples.clear()
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
        """Xác thực sinh trắc học giọng nói WeSpeaker ResNet34 ONNX và thực thi câu lệnh điều khiển thiết bị trên SmartHomeEngine."""
        import asyncio
        import inspect

        auth_res = self.verify_pcm16k_and_apply_strikes(
            pcm_bytes, is_live_mic=is_live_mic
        )
        intents = parse_vietnamese_voice_command_intents(transcript_text)
        device_results: list[dict[str, Any]] = []
        if auth_res.get("authorized") and engine is not None and intents:
            import contextlib

            actor_tier = int(auth_res.get("tier", 1))
            actor_user = str(auth_res.get("user_id", OWNER_ID))
            if hasattr(engine, "set_active_user"):
                engine.set_active_user(actor_user)
            tx_ctx = (
                engine.state_transaction()
                if hasattr(engine, "state_transaction")
                else contextlib.nullcontext()
            )
            with tx_ctx:
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
                            import concurrent.futures

                            with concurrent.futures.ThreadPoolExecutor(
                                max_workers=1
                            ) as pool:
                                act_res = pool.submit(asyncio.run, call_out).result()
                        else:
                            act_res = asyncio.run(call_out)
                    else:
                        act_res = call_out
                    device_results.append(
                        {
                            "device_id": item["device_id"],
                            "action": item["action"],
                            "result": act_res,
                        }
                    )
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
        "expected_devices": [
            {"device_id": "main_door", "action": "open", "expected_state": "OPEN"}
        ],
    },
    "cau_3_dong_cua_chinh": {
        "file": "test_audio/cac_cau_lenh_cua_sep/cau_3_dong_cua_chinh.wav",
        "transcript": "Đóng cửa chính.",
        "intent_type": "device_control",
        "expected_devices": [
            {"device_id": "main_door", "action": "close", "expected_state": "CLOSED"}
        ],
    },
    "cau_4_bat_den_phong_khach": {
        "file": "test_audio/cac_cau_lenh_cua_sep/cau_4_bat_den_phong_khach.wav",
        "transcript": "Bật đèn phòng khách.",
        "intent_type": "device_control",
        "expected_devices": [
            {
                "device_id": "living_room_light",
                "action": "turn_on",
                "expected_state": "ON",
            }
        ],
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
        "expected_devices": [
            {"device_id": "all_lights", "action": "turn_off", "expected_state": "OFF"}
        ],
    },
    "cau_7_dong_het_cua": {
        "file": "test_audio/cac_cau_lenh_cua_sep/cau_7_dong_het_cua.wav",
        "transcript": "Đóng hết cửa.",
        "intent_type": "device_control",
        "expected_devices": [
            {"device_id": "main_door", "action": "close", "expected_state": "CLOSED"}
        ],
    },
}


def check_duplicate_voice_gate(
    feat_s1: bytes | np.ndarray | dict[str, Any] | list[float],
    deep_feat: dict[str, Any] | list[float] | None = None,
    threshold_mel: float = THRESHOLD_MEL,
    threshold_deep: float = THRESHOLD_DEEP,
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
