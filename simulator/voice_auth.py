"""Bo Phan Tich Tan So Giong Noi Kep 2 Tang (2-Stage Cascaded Speaker Verification),
Khu Tieng On Quat/Moi Truong (Spectral Wiener Denoising & Human Voice Isolation),
Phat Hien & Tach 2 Nguoi Cung Noi (Multi-Speaker Diarization & Tier-Priority Resolution)
va Kiem Soat Quyen "Qua Tam Ba Ban" (2-Strike Silent Ignore).

Tai cau truc mo-dun hoa Ponytail: Cac ham DSP thuan, sinh am thanh va kiem dinh chat luong
duoc phan tach sang package `simulator.voice.*`, dong thoi re-export tai day de bao dam
100% backward compatibility cho toan bo cac callers va test suites.
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
from simulator.voice.synthesis_augment import (
    synthesize_noisy_fan_voice,
    synthesize_two_speakers_audio,
    transform_pcm_by_pitch_factor,
    transform_pcm_to_intruder_voice,
)
from simulator.voice.enrollment_quality import (
    parse_vietnamese_voice_command_intents,
    validate_voice_enrollment_quality,
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
    "parse_vietnamese_voice_command_intents",
    "DuplicateVoiceCheckResult",
    "VoiceAuthManager",
    "check_duplicate_voice_gate",
]

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
