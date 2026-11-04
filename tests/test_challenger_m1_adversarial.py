"""BỘ KIỂM THỬ ĐỐI KHÁNG THỰC NGHIỆM ĐỘC LẬP — CHALLENGER 1 (MILESTONE M1)
Tác giả: Teamwork Challenger 1 (Empirical Adversarial Verifier)
Milestone: M1 (Biometrics 256D & Audio Security)
Đối tượng thẩm định:
- simulator/voice/biometrics_neural.py
- simulator/voice_auth.py
- simulator/rule_engine.py

Mục tiêu kiểm định đối kháng thực nghiệm:
1. Neural Speaker Embedding 256 chiều:
   - Kiểm tra chuẩn hóa L2 norm ||e||_2 == 1.0, shape (256,), dtype float32.
   - Đo đạc phân bố năng lượng 3 khối: Block 1 (Envelope 128D), Block 2 (Formant Ratios 64D), Block 3 (Dynamics 64D).
   - Đo đạc độ tương đồng nội lớp (Intra-speaker) và liên lớp (Inter-speaker) giữa Chủ nhà, Người lạ, Cấp 2 và Cấp 3.
   - Thử nghiệm biến thiên cao độ F0 (factor 0.70 đến 1.50), Jitter và Shimmer.
2. Cổng Chống Trùng Giọng Trong Nhà (Duplicate Voiceprint Reject Gate):
   - Thử nghiệm gửi dữ liệu âm thanh trùng Cấp 1 để đăng ký Cấp 2 và Cấp 3 (mẫu chuẩn sạch).
   - Thử nghiệm gửi âm thanh Chủ nhà có biến thiên cao độ (factor 1.05, 1.15, 1.25, 1.28) để kích hoạt cổng chống trùng.
   - Kiểm tra bảo vệ bất biến Chủ nhà C1: không ghi đè, không làm mất quyền C1 trên RAM và đĩa.
   - Thử nghiệm lỗ hổng hạ cấp tài khoản Chủ nhà (Demotion attack) qua tham số user_id="tuan_anh", tier=2/3.
   - Xác nhận Chủ nhà nói lệnh nhạy cảm ("Mở cửa chính") ngay sau khi có nỗ lực đăng ký trùng bị từ chối.
3. Chống Leo Thang Đặc Quyền (Privilege Escalation Prevention):
   - Quét tấn công giả mạo cao độ (Pitch-Shift Spoofing Attack) của Người lạ từ factor 0.70 đến 1.30.
   - Thử nghiệm điểm biên F0 = 190.6Hz (factor 1.25) khai thác điều kiện `owner_pitch_match (neural_sim >= 0.91 & f0_diff <= 30.5Hz)`.
   - Khách Cấp 3 biến thiên âm học nhẹ (factor 0.90 -> 1.10) kiểm tra khả năng nhảy cấp lên C1.
   - Kiểm tra ma trận phân quyền phần cứng RBAC (Cửa chính, Còi báo động, Điều hòa, Đèn, Quạt).
   - Khách Cấp 3 đã hết hạn (expires_at < now) dù đổi cao độ vẫn bị chặn 100%.
"""

from __future__ import annotations

import asyncio
import copy
import json
import pathlib
import sys
import time
import wave
from typing import Generator

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.rule_engine import SmartHomeEngine
from simulator.voice.biometrics_neural import (
    compute_neural_similarity,
    extract_neural_embedding_256d,
)
from simulator.voice_auth import (
    VoiceAuthManager,
    transform_pcm_by_pitch_factor,
)

AUDIO_DIR = ROOT / "test_audio"
VOICEPRINT_FILE = ROOT / "simulator" / "data" / "voiceprints.json"


def load_wav_pcm(name: str) -> np.ndarray:
    path = AUDIO_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing audio file: {path}")
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def inject_jitter_and_shimmer(
    pcm16: np.ndarray,
    jitter_ratio: float = 0.03,
    shimmer_ratio: float = 0.05,
    seed: int = 42,
) -> np.ndarray:
    """Bơm biến thiên Jitter (thời gian/chu kỳ pitch) và Shimmer (biên độ) vào tín hiệu PCM."""
    rng = np.random.default_rng(seed)
    x = pcm16.astype(np.float32)
    n = x.size

    # 1. Jitter: biến dạng trục thời gian vi mô ngẫu nhiên
    grid_orig = np.linspace(0.0, 1.0, n, endpoint=False)
    time_noise = rng.normal(0.0, jitter_ratio / 100.0, size=n)
    time_noise_smooth = np.convolve(time_noise, np.ones(32) / 32.0, mode="same")
    grid_warped = np.clip(grid_orig + time_noise_smooth, 0.0, 1.0)
    grid_warped = np.sort(grid_warped)
    x_jittered = np.interp(grid_orig, grid_warped, x)

    # 2. Shimmer: biến thiên biên độ theo từng khung
    frame_size = 160  # 10ms ở 16kHz
    num_frames = max(1, n // frame_size)
    amp_factors = 1.0 + rng.uniform(-shimmer_ratio, shimmer_ratio, size=num_frames)
    amp_envelope = np.repeat(amp_factors, frame_size)
    if amp_envelope.size < n:
        amp_envelope = np.pad(amp_envelope, (0, n - amp_envelope.size), mode="edge")
    else:
        amp_envelope = amp_envelope[:n]

    x_shimmered = x_jittered * amp_envelope
    return np.clip(x_shimmered, -32768, 32767).astype(np.int16)


@pytest.fixture
def vm() -> Generator[VoiceAuthManager, None, None]:
    manager = VoiceAuthManager(AUDIO_DIR)
    manager.reset_strikes()
    yield manager
    manager.reset_strikes()


@pytest.fixture
def pcm_owner() -> np.ndarray:
    return load_wav_pcm("mo_cua_chinh.wav")


@pytest.fixture
def pcm_intruder() -> np.ndarray:
    return load_wav_pcm("giong_2_nguoi_la_mo_cua.wav")


@pytest.fixture
def pcm_guest() -> np.ndarray:
    return load_wav_pcm("giong_cap3_khach_c.wav")


@pytest.fixture
def pcm_member() -> np.ndarray:
    return load_wav_pcm("giong_cap2_thanh_vien_a.wav")


# ==============================================================================
# PHẦN 1: ĐỐI KIỂM BỘ TRÍCH XUẤT NEURAL SPEAKER EMBEDDING 256-D
# ==============================================================================

class TestNeuralEmbedding256DVerification:
    """Kiểm chứng thực nghiệm tính bất biến và các đặc tính toán học của vector 256D."""

    def test_embedding_contract_and_l2_normalization(self, pcm_owner: np.ndarray) -> None:
        """Xác nhận hợp đồng giao diện: shape=(256,), float32, chuẩn hóa mặt cầu đơn vị ||e||_2 == 1.0."""
        emb = extract_neural_embedding_256d(pcm_owner)
        assert isinstance(emb, np.ndarray)
        assert emb.shape == (256,), f"Kỳ vọng shape (256,), nhận {emb.shape}"
        assert emb.dtype == np.float32, f"Kỳ vọng dtype float32, nhận {emb.dtype}"
        l2_norm = float(np.linalg.norm(emb))
        assert abs(l2_norm - 1.0) < 1e-4, f"Kỳ vọng chuẩn L2 == 1.0, nhận {l2_norm}"

    def test_block_energy_distribution_measurement(
        self, pcm_owner: np.ndarray, pcm_intruder: np.ndarray
    ) -> None:
        """Thực nghiệm đo đạc phân bố năng lượng 3 khối cấu thành vector 256D:
        - Khối 1: Đường bao thanh quản (128D)
        - Khối 2: Tỷ lệ Formant tương đối & năng lượng băng tần (64D)
        - Khối 3: Động lực học phổ (64D)
        Phát hiện: Khối 2 chiếm tới >87% tổng năng lượng chuẩn của vector đơn vị,
        khiến độ tương đồng cosine bị kéo cao giả tạo giữa mọi người nói.
        """
        eo = extract_neural_embedding_256d(pcm_owner)
        ei = extract_neural_embedding_256d(pcm_intruder)

        norm_b1_o = float(np.linalg.norm(eo[:128]))
        norm_b2_o = float(np.linalg.norm(eo[128:192]))
        norm_b3_o = float(np.linalg.norm(eo[192:256]))

        # Khối 2 chiếm tỷ trọng năng lượng áp đảo (> 0.85)
        assert norm_b2_o > 0.85, f"Norm Khối 2 đo được: {norm_b2_o:.4f}"
        assert norm_b1_o < 0.45, f"Norm Khối 1 đo được: {norm_b1_o:.4f}"
        assert norm_b3_o < 0.15, f"Norm Khối 3 đo được: {norm_b3_o:.4f}"

        # Đo độ tương đồng liên cá nhân trên từng khối
        sim_b1 = float(np.dot(eo[:128], ei[:128]) / (norm_b1_o * float(np.linalg.norm(ei[:128]))))
        sim_b2 = float(np.dot(eo[128:192], ei[128:192]) / (norm_b2_o * float(np.linalg.norm(ei[128:192]))))
        sim_b3 = float(np.dot(eo[192:256], ei[192:256]) / (norm_b3_o * float(np.linalg.norm(ei[192:256]))))

        # Khối 1 (đường bao CMVN) có độ phân tách tốt nhất (sim ~0.84), nhưng Khối 2 kéo lên ~0.96!
        assert sim_b1 < sim_b2, f"Khối 1 sim={sim_b1:.4f} phải có độ phân tách tốt hơn Khối 2 sim={sim_b2:.4f}"

    def test_inter_speaker_baseline_similarity_elevation(
        self, pcm_owner: np.ndarray, pcm_intruder: np.ndarray, pcm_member: np.ndarray, pcm_guest: np.ndarray
    ) -> None:
        """Đo độ tương đồng cosine gốc (chưa qua pitch shift) giữa các cá nhân khác nhau:
        Xác nhận thực tế: Độ tương đồng giữa Chủ nhà và Người lạ đạt tới 0.9466!
        """
        eo = extract_neural_embedding_256d(pcm_owner)
        ei = extract_neural_embedding_256d(pcm_intruder)
        e2 = extract_neural_embedding_256d(pcm_member)
        e3 = extract_neural_embedding_256d(pcm_guest)

        sim_owner_intruder = compute_neural_similarity(eo, ei)
        sim_owner_member = compute_neural_similarity(eo, e2)
        sim_owner_guest = compute_neural_similarity(eo, e3)

        assert sim_owner_intruder > 0.90, f"Độ tương đồng Chủ nhà vs Người lạ: {sim_owner_intruder:.4f}"
        assert sim_owner_member > 0.88, f"Độ tương đồng Chủ nhà vs Cấp 2: {sim_owner_member:.4f}"
        assert sim_owner_guest > 0.88, f"Độ tương đồng Chủ nhà vs Khách C: {sim_owner_guest:.4f}"

    @pytest.mark.parametrize("pitch_factor", [0.90, 0.95, 1.00, 1.05, 1.15, 1.28])
    def test_owner_intra_speaker_pitch_tolerance(
        self, pcm_owner: np.ndarray, pitch_factor: float
    ) -> None:
        """Xác nhận độ tương đồng nội lớp của Chủ nhà khi đổi cao độ tự nhiên (factor 0.90 - 1.28) luôn đạt >= 0.91."""
        emb_base = extract_neural_embedding_256d(pcm_owner)
        shifted = (
            pcm_owner
            if pitch_factor == 1.0
            else transform_pcm_by_pitch_factor(pcm_owner, factor=pitch_factor, sr=16000)
        )
        sim = compute_neural_similarity(extract_neural_embedding_256d(shifted), emb_base)
        assert sim >= 0.91, f"Chủ nhà đổi factor={pitch_factor} bị tụt độ tương đồng: {sim:.4f} < 0.91"

    def test_jitter_and_shimmer_acoustic_resilience(self, pcm_owner: np.ndarray) -> None:
        """Xác nhận mô hình 256D chống chịu tốt trước Jitter vi mô (3%) và Shimmer (5%)."""
        emb_base = extract_neural_embedding_256d(pcm_owner)
        perturbed = inject_jitter_and_shimmer(pcm_owner, jitter_ratio=0.03, shimmer_ratio=0.05, seed=2026)
        sim = compute_neural_similarity(extract_neural_embedding_256d(perturbed), emb_base)
        assert sim >= 0.88, f"Độ tương đồng sau jitter/shimmer: {sim:.4f} < 0.88"


# ==============================================================================
# PHẦN 2: ĐỐI KIỂM CỔNG CHỐNG TRÙNG GIỌNG TRONG NHÀ (COLLISION GATE)
# ==============================================================================

class TestAntiCollisionGateVerification:
    """Kiểm chứng thực nghiệm Cổng Chống Trùng Giọng và Bảo Toàn Quyền Cấp 1."""

    def test_clean_owner_voice_collision_rejected_for_tier2(
        self, vm: VoiceAuthManager, pcm_owner: np.ndarray
    ) -> None:
        """Mẫu giọng sạch của Chủ nhà C1 gửi đăng ký Cấp 2:
        Hệ thống từ chối ngay lập tức (is_duplicate is True, TRUNG_GIONG_NGUOI_TRONG_NHA).
        """
        dup_res = vm.check_duplicate_voice_gate(
            feat_s1=pcm_owner.tobytes(),
            target_tier=2,
            target_user_id="thanh_vien_moi",
        )
        assert dup_res.is_duplicate is True
        assert dup_res.reason == "TRUNG_GIONG_NGUOI_TRONG_NHA"
        assert dup_res.matched_tier == 1

    def test_clean_owner_voice_collision_rejected_for_tier3(
        self, vm: VoiceAuthManager, pcm_owner: np.ndarray
    ) -> None:
        """Mẫu giọng sạch của Chủ nhà C1 gửi đăng ký Cấp 3:
        Hệ thống từ chối ngay lập tức.
        """
        dup_res = vm.check_duplicate_voice_gate(
            feat_s1=pcm_owner.tobytes(),
            target_tier=3,
            target_user_id="khach_moi",
        )
        assert dup_res.is_duplicate is True
        assert dup_res.reason == "TRUNG_GIONG_NGUOI_TRONG_NHA"
        assert dup_res.matched_tier == 1

    @pytest.mark.parametrize("pitch_factor", [1.05, 1.15, 1.25, 1.28])
    def test_pitch_shifted_owner_collision_must_be_rejected(
        self, vm: VoiceAuthManager, pcm_owner: np.ndarray, pitch_factor: float
    ) -> None:
        """CHALLENGE VULNERABILITY: Chủ nhà nói với cao độ tự nhiên thay đổi (factor 1.05 -> 1.28)
        khi mở thu âm cho khách. Cổng chống trùng giọng hiện tại bị lọt (False Negative).
        """
        shifted_owner = transform_pcm_by_pitch_factor(pcm_owner, factor=pitch_factor, sr=16000)
        dup_res = vm.check_duplicate_voice_gate(
            feat_s1=shifted_owner.tobytes(),
            target_tier=3,
            target_user_id=f"guest_shifted_{pitch_factor}",
        )
        assert dup_res.is_duplicate is True, (
            f"LỌT CỔNG CHỐNG TRÙNG: Chủ nhà đổi pitch (factor={pitch_factor}) không bị phát hiện trùng! "
            f"dup_res: is_duplicate={dup_res.is_duplicate}, reason={dup_res.reason}"
        )

    def test_enrollment_does_not_overwrite_or_demote_owner(
        self, vm: VoiceAuthManager, pcm_owner: np.ndarray
    ) -> None:
        """Xác nhận khi đăng ký trùng bị từ chối, hồ sơ owner_voice_1 trong RAM và trên đĩa (voiceprints.json)
        giữ nguyên 100% (tier=1, role=ADMIN, user_id=tuan_anh).
        """
        orig_tier = vm.profiles["owner_voice_1"]["tier"]
        orig_role = vm.profiles["owner_voice_1"]["role"]
        assert orig_tier == 1 and orig_role == "ADMIN"

        res = vm.enroll_tier_voice_from_pcm16k(
            pcm_bytes=pcm_owner.tobytes(),
            user_id="fake_guest",
            user_name="Khách Mạo Danh",
            tier=3,
            role="CHILD_GUEST",
            check_duplicate=True,
        )
        assert res.get("ok") is False
        assert res.get("status") == "DUPLICATE_VOICE_REJECTED"

        # Kiểm tra bất biến trên RAM
        assert vm.profiles["owner_voice_1"]["tier"] == 1
        assert vm.profiles["owner_voice_1"]["role"] == "ADMIN"

        # Kiểm tra bất biến trên đĩa
        disk_data = json.loads(VOICEPRINT_FILE.read_text(encoding="utf-8"))
        assert disk_data["owner_voice_1"]["tier"] == 1
        assert disk_data["owner_voice_1"]["role"] == "ADMIN"

    def test_direct_demotion_exploit_must_be_blocked(
        self, vm: VoiceAuthManager, pcm_owner: np.ndarray
    ) -> None:
        """CHALLENGE VULNERABILITY: Kẻ tấn công gọi enroll_tier_voice_from_pcm16k truyền user_id='tuan_anh', tier=2.
        Hệ thống hiện tại ghi đè owner_voice_1 và hạ tier xuống 2!
        Yêu cầu bảo mật: Phải từ chối và cấm hạ cấp C1.
        """
        orig_profiles = copy.deepcopy(vm.profiles)
        try:
            res = vm.enroll_tier_voice_from_pcm16k(
                pcm_bytes=pcm_owner.tobytes(),
                user_id="tuan_anh",
                user_name="Nguyễn Tuấn Anh",
                tier=2,
                role="MEMBER",
            )
            # Nếu hệ thống bảo mật đúng chuẩn, res["ok"] phải False hoặc tier giữ nguyên 1
            assert vm.profiles["owner_voice_1"]["tier"] == 1, (
                f"LỖ HỔNG HẠ CẤP: owner_voice_1 bị hạ xuống Tier {vm.profiles['owner_voice_1']['tier']}!"
            )
        finally:
            # Khôi phục trạng thái chuẩn
            vm.profiles = orig_profiles
            VOICEPRINT_FILE.write_bytes((json.dumps(orig_profiles, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    def test_owner_immediate_command_after_collision_rejection(
        self, vm: VoiceAuthManager, pcm_owner: np.ndarray
    ) -> None:
        """Sau khi luồng đăng ký khách bị từ chối do trùng giọng C1:
        Chủ nhà lập tức ra lệnh bằng giọng nói -> Được phê duyệt 100% Cấp 1, 0 strike, không bị kẹt quyền.
        """
        # Kích hoạt từ chối trùng
        _ = vm.enroll_tier_voice_from_pcm16k(
            pcm_bytes=pcm_owner.tobytes(),
            user_id="temp_guest_probe",
            tier=3,
            check_duplicate=True,
        )

        # Chủ nhà ra lệnh
        cmd_res = vm.verify_pcm16k_and_apply_strikes(pcm_owner.tobytes(), is_live_mic=True)
        assert cmd_res["authorized"] is True
        assert cmd_res["tier"] == 1
        assert cmd_res["speaker_id"] == "owner_voice_1"
        assert cmd_res["role"] == "ADMIN"
        assert cmd_res["strike_count"] == 0
        assert cmd_res["silent_ignore"] is False


# ==============================================================================
# PHẦN 3: ĐỐI KIỂM CHỐNG LEO THANG ĐẶC QUYỀN (PRIVILEGE ESCALATION PREVENTION)
# ==============================================================================

class TestAntiPrivilegeEscalationVerification:
    """Kiểm chứng thực nghiệm chống leo thang đặc quyền từ Khách/Thành viên/Người lạ lên C1."""

    @pytest.mark.parametrize(
        "pitch_factor",
        [0.70, 0.75, 0.78, 0.82, 0.88, 0.95, 1.00, 1.15, 1.20, 1.25, 1.30, 1.35, 1.40, 1.45, 1.50],
    )
    def test_intruder_standard_pitch_shifts_blocked(
        self, vm: VoiceAuthManager, pcm_intruder: np.ndarray, pitch_factor: float
    ) -> None:
        """Người lạ dùng pitch shift trong toàn dải [0.70 - 1.50]:
        Hệ thống chặn 100% (authorized == False, tier != 1, speaker_id != owner_voice_1).
        """
        shifted = (
            pcm_intruder
            if pitch_factor == 1.0
            else transform_pcm_by_pitch_factor(pcm_intruder, factor=pitch_factor, sr=16000)
        )
        vm.reset_strikes()
        res = vm.verify_pcm16k_and_apply_strikes(shifted.tobytes())
        assert res["authorized"] is False
        assert res.get("tier") != 1
        assert res.get("speaker_id") != "owner_voice_1"

    def test_intruder_factor_125_pitch_shift_exploit(
        self, vm: VoiceAuthManager, pcm_intruder: np.ndarray
    ) -> None:
        """CHALLENGE CRITICAL FLAW: Người lạ biến đổi cao độ với factor=1.25.
        F0 của Người lạ bị kéo về 190.6Hz (cách F0 Chủ nhà 20.4Hz <= 30.5Hz).
        Vì vector 256D có độ tương đồng 0.9382 (>= 0.91), điều kiện owner_pitch_match bị kích hoạt
        và hệ thống cấp quyền ADMIN Cấp 1 cho Người lạ!
        """
        shifted = transform_pcm_by_pitch_factor(pcm_intruder, factor=1.25, sr=16000)
        vm.reset_strikes()
        res = vm.verify_pcm16k_and_apply_strikes(shifted.tobytes())
        assert res["authorized"] is False, (
            f"SECURITY BREACH THỰC TẾ: Người lạ factor 1.25 đã vượt qua xác thực! "
            f"authorized={res['authorized']}, speaker_id={res['speaker_id']}, tier={res['tier']}, role={res['role']}"
        )

    @pytest.mark.parametrize("pitch_factor", [0.90, 0.95, 1.001, 1.05, 1.10])
    def test_guest_cannot_escalate_to_owner_tier1(
        self, vm: VoiceAuthManager, pcm_guest: np.ndarray, pitch_factor: float
    ) -> None:
        """Khách C phát âm biến thiên: Tuyệt đối không bao giờ được nâng cấp lên Tier 1."""
        varied = transform_pcm_by_pitch_factor(pcm_guest, factor=pitch_factor, sr=16000)
        vm.reset_strikes()
        res = vm.verify_pcm16k_and_apply_strikes(varied.tobytes())
        assert res.get("tier") != 1
        assert res.get("speaker_id") != "owner_voice_1"

    def test_hardware_permission_matrix_enforcement(self) -> None:
        """Xác nhận ma trận phân quyền phần cứng RBAC chặn đứng C2/C3 truy cập thiết bị C1."""
        engine = SmartHomeEngine()

        async def _run() -> None:
            # 1. Cấp 1: Toàn quyền
            engine.set_active_user("tuan_anh")
            assert engine.current_tier == 1
            assert (await engine.execute_device_action("main_door", "open")).get("ok") is True
            assert (await engine.execute_device_action("alarm_siren", "turn_on")).get("ok") is True

            # 2. Cấp 2: Bị chặn Cửa chính và Còi báo động
            engine.set_active_user("thanh_vien_a")
            assert engine.current_tier == 2
            assert (await engine.execute_device_action("main_door", "open")).get("ok") is False
            assert (await engine.execute_device_action("alarm_siren", "turn_on")).get("ok") is False
            assert (await engine.execute_device_action("fan", "turn_on")).get("ok") is True

            # 3. Cấp 3: Bị chặn Cửa chính, Còi báo động, Điều hòa
            engine.set_active_user("khach_c")
            assert engine.current_tier == 3
            assert (await engine.execute_device_action("main_door", "open")).get("ok") is False
            assert (await engine.execute_device_action("alarm_siren", "turn_on")).get("ok") is False
            assert (await engine.execute_device_action("ac", "turn_on")).get("ok") is False
            assert (await engine.execute_device_action("living_room_light", "turn_on")).get("ok") is True

        asyncio.run(_run())

    def test_expired_guest_cannot_bypass_expiration(
        self, vm: VoiceAuthManager, pcm_guest: np.ndarray
    ) -> None:
        """Khách đã hết hạn (expires_at trong quá khứ) bị chặn 100%, không thể leo thang đặc quyền."""
        exp_prof = {
            "id": "guest_voice_expired_challenger",
            "user_id": "khach_expired_challenger",
            "name": "Khách Đã Hết Hạn Thử Nghiệm",
            "authorized": True,
            "role": "CHILD_GUEST",
            "tier": 3,
            "f0_hz": 150.0,
            "centroid_hz": 1200.0,
            "embedding": [0.1] * 26,
            "expires_at": time.time() - 3600.0,
        }
        vm.profiles["guest_voice_expired_challenger"] = exp_prof
        try:
            res = vm.verify_pcm16k_and_apply_strikes(pcm_guest.tobytes())
            assert res["authorized"] is False
            assert res.get("tier") != 1
            assert res.get("speaker_id") != "owner_voice_1"
        finally:
            del vm.profiles["guest_voice_expired_challenger"]
