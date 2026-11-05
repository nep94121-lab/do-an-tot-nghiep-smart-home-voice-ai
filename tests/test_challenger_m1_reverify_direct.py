"""BỘ KIỂM THỬ ĐỐI KHÁNG THỰC NGHIỆM ĐỘC LẬP — CHALLENGER M1 RE-VERIFICATION
Milestone: M1 Iteration 2 (Re-Verification Gate)
Tác giả: Empirical Challenger

Kiểm chứng thực nghiệm 4 kịch bản trọng yếu:
1. Kịch bản Người lạ pitch shift factor 1.25x: bị từ chối 100%, không bị leo thang đặc quyền lên C1.
2. Kịch bản Chủ nhà thay đổi cao độ (factor 1.0 - 1.28x): nhận diện đúng C1 và không bị lọt đăng ký làm Khách C3.
3. Kịch bản thử hạ cấp Chủ nhà tuan_anh xuống Tier 2/3: bị từ chối theo đúng bất biến C1.
4. Thử nghiệm bơm White Noise và Buzzer vào VAD: bị chặn 100%.
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys
import wave
import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.voice.vad_vietnamese import is_vietnamese_speech, VietnameseVADStreamFilter
from simulator.voice_auth import (
    VoiceAuthManager,
    transform_pcm_by_pitch_factor,
)

AUDIO_DIR = ROOT / "test_audio"
VOICEPRINT_FILE = ROOT / "simulator" / "data" / "voiceprints.json"


def load_wav(name: str) -> np.ndarray:
    if name in ("giong_1_chu_nha_mo_cua.wav", "mo_cua_chinh.wav"):
        name = "cac_cau_lenh_cua_sep/cau_2_mo_cua_chinh.wav"
    path = AUDIO_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing audio file: {path}")
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


@pytest.fixture
def vm() -> VoiceAuthManager:
    manager = VoiceAuthManager(AUDIO_DIR)
    manager.reset_strikes()
    return manager


# ==============================================================================
# KỊCH BẢN 1: NGƯỜI LẠ PITCH SHIFT FACTOR 1.25X
# ==============================================================================

class TestScenario1IntruderPitchShift:
    """Xác nhận Người lạ pitch shift 1.25x bị từ chối 100%, không leo thang lên C1."""

    def test_intruder_pitch_shift_125_rejected(self, vm: VoiceAuthManager) -> None:
        intruder_pcm = load_wav("giong_2_nguoi_la_mo_cua.wav")
        shifted = transform_pcm_by_pitch_factor(intruder_pcm, factor=1.25, sr=16000)

        vm.reset_strikes()
        res = vm.verify_pcm16k_and_apply_strikes(shifted.tobytes())

        assert res["authorized"] is False, f"LỖ HỔNG LEO THANG: authorized={res['authorized']}"
        assert res.get("tier") != 1, f"LỖ HỔNG LEO THANG: tier={res.get('tier')}"
        assert res.get("speaker_id") != "owner_voice_1", f"LỖ HỔNG LEO THANG: speaker_id={res.get('speaker_id')}"
        assert res.get("role") != "ADMIN", f"LỖ HỔNG LEO THANG: role={res.get('role')}"

    @pytest.mark.parametrize("pitch_factor", [0.70, 0.75, 0.78, 0.82, 0.88, 0.95, 1.00, 1.10, 1.15, 1.20, 1.22, 1.25, 1.28])
    def test_intruder_standard_pitch_shifts_sweep(self, vm: VoiceAuthManager, pitch_factor: float) -> None:
        intruder_pcm = load_wav("giong_2_nguoi_la_mo_cua.wav")
        shifted = intruder_pcm if pitch_factor == 1.0 else transform_pcm_by_pitch_factor(intruder_pcm, factor=pitch_factor, sr=16000)

        vm.reset_strikes()
        res = vm.verify_pcm16k_and_apply_strikes(shifted.tobytes())

        assert res["authorized"] is False, f"Leo thang tại factor={pitch_factor}: {res}"
        assert res.get("tier") != 1
        assert res.get("speaker_id") != "owner_voice_1"


# ==============================================================================
# KỊCH BẢN 2: CHỦ NHÀ THAY ĐỔI CAO ĐỘ (FACTOR 1.0 - 1.28X)
# ==============================================================================

class TestScenario2HomeownerPitchShift:
    """Xác nhận Chủ nhà đổi cao độ (factor 1.0 - 1.28x) được nhận diện đúng C1 và không bị lọt đăng ký làm Khách C3."""

    @pytest.mark.parametrize("pitch_factor", [1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.28])
    def test_owner_recognized_as_c1(self, vm: VoiceAuthManager, pitch_factor: float) -> None:
        owner_pcm = load_wav("mo_cua_chinh.wav")
        shifted = owner_pcm if pitch_factor == 1.0 else transform_pcm_by_pitch_factor(owner_pcm, factor=pitch_factor, sr=16000)

        vm.reset_strikes()
        res = vm.verify_pcm16k_and_apply_strikes(shifted.tobytes(), is_live_mic=True)

        assert res["authorized"] is True, f"Chủ nhà factor={pitch_factor} bị từ chối!"
        assert res.get("tier") == 1, f"Chủ nhà factor={pitch_factor} không phải Tier 1: {res.get('tier')}"
        assert res.get("speaker_id") == "owner_voice_1", f"Chủ nhà factor={pitch_factor} sai speaker_id: {res.get('speaker_id')}"
        assert res.get("role") == "ADMIN", f"Chủ nhà factor={pitch_factor} sai role: {res.get('role')}"

    @pytest.mark.parametrize("pitch_factor", [1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.28])
    def test_owner_pitch_shift_rejected_as_guest_tier3(self, vm: VoiceAuthManager, pitch_factor: float) -> None:
        owner_pcm = load_wav("mo_cua_chinh.wav")
        shifted = owner_pcm if pitch_factor == 1.0 else transform_pcm_by_pitch_factor(owner_pcm, factor=pitch_factor, sr=16000)

        # 1. Kiểm tra trực tiếp qua cổng duplicate check
        dup_res = vm.check_duplicate_voice_gate(
            feat_s1=shifted.tobytes(),
            target_tier=3,
            target_user_id=f"guest_shifted_{pitch_factor}",
        )
        assert dup_res.is_duplicate is True, f"LỌT CỔNG CHỐNG TRÙNG: factor={pitch_factor}"

        # 2. Kiểm tra qua hàm enroll_tier_voice_from_pcm16k
        enroll_res = vm.enroll_tier_voice_from_pcm16k(
            pcm_bytes=shifted.tobytes(),
            user_id=f"guest_shifted_{pitch_factor}",
            user_name="Khách Thử Nghiệm",
            tier=3,
            role="CHILD_GUEST",
            check_duplicate=True,
        )
        assert enroll_res.get("ok") is False, f"Đăng ký khách thành công trái phép tại factor={pitch_factor}!"
        assert enroll_res.get("status") == "DUPLICATE_VOICE_REJECTED"


# ==============================================================================
# KỊCH BẢN 3: HẠ CẤP CHỦ NHÀ TUAN_ANH XUỐNG TIER 2/3
# ==============================================================================

class TestScenario3HomeownerDemotionInvariant:
    """Xác nhận nỗ lực hạ cấp Chủ nhà tuan_anh xuống Tier 2 hoặc Tier 3 bị từ chối 100%."""

    def test_demote_tuan_anh_to_tier2_rejected(self, vm: VoiceAuthManager) -> None:
        owner_pcm = load_wav("mo_cua_chinh.wav")
        orig_profiles = copy.deepcopy(vm.profiles)
        try:
            res = vm.enroll_tier_voice_from_pcm16k(
                pcm_bytes=owner_pcm.tobytes(),
                user_id="tuan_anh",
                user_name="Nguyễn Tuấn Anh",
                tier=2,
                role="MEMBER",
            )
            assert res.get("ok") is False, "Hạ cấp tuan_anh xuống Tier 2 không bị chặn!"
            assert res.get("status") == "TIER1_DEMOTION_FORBIDDEN"
            assert res.get("reason") == "CAM_HA_CAP_CHU_NHA"
            assert vm.profiles["owner_voice_1"]["tier"] == 1
            assert vm.profiles["owner_voice_1"]["role"] == "ADMIN"
        finally:
            vm.profiles = orig_profiles
            VOICEPRINT_FILE.write_bytes((json.dumps(orig_profiles, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    def test_demote_tuan_anh_to_tier3_rejected(self, vm: VoiceAuthManager) -> None:
        owner_pcm = load_wav("mo_cua_chinh.wav")
        orig_profiles = copy.deepcopy(vm.profiles)
        try:
            res = vm.enroll_tier_voice_from_pcm16k(
                pcm_bytes=owner_pcm.tobytes(),
                user_id="tuan_anh",
                user_name="Nguyễn Tuấn Anh",
                tier=3,
                role="CHILD_GUEST",
            )
            assert res.get("ok") is False, "Hạ cấp tuan_anh xuống Tier 3 không bị chặn!"
            assert res.get("status") == "TIER1_DEMOTION_FORBIDDEN"
            assert res.get("reason") == "CAM_HA_CAP_CHU_NHA"
            assert vm.profiles["owner_voice_1"]["tier"] == 1
            assert vm.profiles["owner_voice_1"]["role"] == "ADMIN"
        finally:
            vm.profiles = orig_profiles
            VOICEPRINT_FILE.write_bytes((json.dumps(orig_profiles, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    def test_demote_by_custom_label_owner_voice_1_rejected(self, vm: VoiceAuthManager) -> None:
        owner_pcm = load_wav("mo_cua_chinh.wav")
        orig_profiles = copy.deepcopy(vm.profiles)
        try:
            res = vm.enroll_tier_voice_from_pcm16k(
                pcm_bytes=owner_pcm.tobytes(),
                user_id="fake_hacker",
                user_name="Kẻ Tấn Công",
                tier=2,
                role="MEMBER",
                custom_label="owner_voice_1",
            )
            assert res.get("ok") is False
            assert res.get("status") == "TIER1_DEMOTION_FORBIDDEN"
            assert vm.profiles["owner_voice_1"]["tier"] == 1
        finally:
            vm.profiles = orig_profiles
            VOICEPRINT_FILE.write_bytes((json.dumps(orig_profiles, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


# ==============================================================================
# KỊCH BẢN 4: BƠM WHITE NOISE VÀ BUZZER VÀO VAD
# ==============================================================================

class TestScenario4VADNoiseAndBuzzerRejection:
    """Xác nhận bộ lọc VAD tiếng Việt chặn 100% White Noise và âm đơn tần Buzzer."""

    @pytest.mark.parametrize("amplitude", [0.03, 0.08, 0.15, 0.30])
    @pytest.mark.parametrize("duration_sec", [0.5, 1.0, 2.0])
    def test_white_noise_blocked(self, amplitude: float, duration_sec: float) -> None:
        sr = 16000
        n_samples = int(sr * duration_sec)
        rng = np.random.default_rng(seed=int(amplitude * 1000 + duration_sec * 10))
        noise = rng.uniform(-amplitude, amplitude, size=n_samples).astype(np.float32)
        pcm_noise = (noise * 32767.0).astype(np.int16)

        is_speech, reason, debug = is_vietnamese_speech(pcm_noise, sr=sr)
        assert is_speech is False, f"White noise amp={amplitude}, dur={duration_sec} lọt VAD! debug={debug}"
        assert reason in ("TAP_AM_HOAC_NGOAI_NGU", "IM_LANG", "KHONG_CO_PITCH")

    @pytest.mark.parametrize("freq_hz", [500.0, 1000.0, 1500.0, 2000.0, 2500.0, 3000.0, 4000.0])
    @pytest.mark.parametrize("amplitude", [0.1, 0.3, 0.7])
    def test_pure_tone_buzzer_blocked(self, freq_hz: float, amplitude: float) -> None:
        sr = 16000
        duration_sec = 1.0
        t = np.linspace(0.0, duration_sec, int(sr * duration_sec), endpoint=False)
        sine = amplitude * np.sin(2.0 * np.pi * freq_hz * t).astype(np.float32)
        pcm_sine = (sine * 32767.0).astype(np.int16)

        is_speech, reason, debug = is_vietnamese_speech(pcm_sine, sr=sr)
        assert is_speech is False, f"Buzzer {freq_hz}Hz amp={amplitude} lọt VAD! debug={debug}"
        assert reason in ("TAP_AM_HOAC_NGOAI_NGU", "KHONG_CO_PITCH")

    def test_streaming_vad_filter_rejects_noise_and_passes_speech(self) -> None:
        sr = 16000
        vad_filter = VietnameseVADStreamFilter(sample_rate=sr, window_ms=200)

        # 1. Feed white noise chunks (20ms mỗi chunk = 320 samples = 640 bytes)
        rng = np.random.default_rng(2026)
        chunk_size = 320
        noise_chunk = (rng.uniform(-0.15, 0.15, size=chunk_size) * 32767.0).astype(np.int16).tobytes()

        # Trong 9 chunk đầu (180ms < 200ms): filter ở trạng thái BUFFERING
        for i in range(9):
            is_speech, reason = vad_filter.process_chunk(noise_chunk)
            assert reason == "BUFFERING"

        # Từ chunk thứ 10 trở đi (>= 200ms): filter bắt buộc phải phát hiện và CHẶN tạp âm 100%
        for i in range(9, 15):
            is_speech, reason = vad_filter.process_chunk(noise_chunk)
            assert is_speech is False, f"Chunk {i+1} lọt VAD filter!"
            assert reason == "TAP_AM_HOAC_NGOAI_NGU"

        # 2. Reset and feed valid Vietnamese speech chunks
        vad_filter.reset()
        speech_pcm = load_wav("mo_cua_chinh.wav")
        mid = len(speech_pcm) // 2
        active_segment = speech_pcm[mid : mid + 3200]  # 200ms
        is_speech, reason = vad_filter.process_chunk(active_segment.tobytes())
        assert is_speech is True, f"Speech chunk bị từ chối: reason={reason}"
        assert reason == "TIENG_VIET_HOP_LE"

    def test_valid_vietnamese_audio_passes_vad(self) -> None:
        for fname in ["mo_cua_chinh.wav", "kich_hoat_di_ngu.wav"]:
            pcm = load_wav(fname)
            is_speech, reason, debug = is_vietnamese_speech(pcm, sr=16000)
            assert is_speech is True, f"{fname} bị VAD từ chối: {reason}, debug={debug}"
            assert reason == "TIENG_VIET_HOP_LE"
