"""BỘ KIỂM THỬ ĐỐI KHÁNG ĐỘC LẬP — ADVERSARIAL DSP VERIFIER (MILESTONE M1)
Tác giả: Teamwork Challenger 1 (Adversarial DSP Verifier)
Phạm vi kiểm định: `simulator/voice_auth.py`

Mục tiêu đối kháng:
1. Stress-test Âm đệm & Ngập ngừng ("ừm", "ờ", vocal fry):
   - Quét lưới tần số F0 [75, 80, 85, 90] Hz
   - Thời lượng âm đệm [0.2s, 0.5s, 1.0s, 2.0s]
   - Khoảng lặng ghép [100ms, 500ms, 1000ms]
   - Ghép với câu lệnh mở cửa của Chủ nhà
   -> Xác nhận: authorized == True, strike_count == 0 (100% không false strike).
2. Stress-test Người lạ đột nhập & 3-Strike Silent Lockout:
   - Người lạ nói ngập ngừng ("ừm" + pause + intruder command) -> Chặn, tăng strike
   - Người lạ giả giọng (Pitch Shift Attack ép F0 về 170Hz giống Chủ nhà) -> Chặn, tăng strike
   - Chuỗi 3-strike lockout: Lần 1 (cảnh báo 1), Lần 2 (cảnh báo 2), Lần 3+ (im lặng tuyệt đối silent_ignore=True)
   - Phục hồi: Chủ nhà nói sau đó -> Mở khóa ngay lập tức, strike reset về 0
3. Stress-test Cổng kiểm định chất lượng giọng thu âm (validate_voice_enrollment_quality):
   - Mẫu quá ngắn (< 2.0s)
   - Mẫu im lặng tuyệt đối (zeros)
   - Mẫu âm lượng quá nhỏ (RMS < 0.02)
   - Mẫu nhiễu trắng ngẫu nhiên (Gaussian noise)
   - Mẫu tiếng gió thổi micro (turbulent low-frequency pop)
   - Mẫu tần số F0 bất thường (< 75Hz hoặc > 340Hz)
   - Mẫu pitch biến thiên cực mạnh (pitch_std > 38Hz)
   - Mẫu nói quá ngắn trong khoảng lặng dài (voiced_ratio < 35%)
   -> Xác nhận: Tất cả trả về status: "CHUA_DAT" ("Chưa được - bắt thu lại")
   - Mẫu giọng chuẩn -> status: "DA_DAT" ("Đã được")
"""

from __future__ import annotations

import pathlib
import sys
import wave
from typing import Generator

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.voice_auth import (
    VoiceAuthManager,
    detect_multi_speaker_and_resolve_priority,
    extract_stage2_deep_features,
    extract_voice_features,
    transform_pcm_by_pitch_factor,
    validate_voice_enrollment_quality,
)

AUDIO_DIR = ROOT / "test_audio"


def load_wav(name: str) -> np.ndarray:
    path = AUDIO_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing test audio file: {path}")
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def synthesize_vocal_fry_filler(f0_hz: float, duration_sec: float, sr: int = 16000) -> np.ndarray:
    """Tạo mẫu âm đệm tự nhiên ("ừm", "ờ", vocal fry) có phổ tập trung dải trầm <250Hz."""
    n_samples = int(sr * duration_sec)
    t = np.arange(n_samples, dtype=np.float32) / sr
    # Hài âm trầm (f0, 2*f0, 3*f0) suy giảm nhanh
    sig = (
        0.32 * np.sin(2.0 * np.pi * f0_hz * t)
        + 0.12 * np.sin(2.0 * np.pi * 2.0 * f0_hz * t)
        + 0.04 * np.sin(2.0 * np.pi * 3.0 * f0_hz * t)
    )
    # Cửa sổ Hanning làm mượt đầu/cuối tránh tiếng click
    env = np.sin(np.pi * np.linspace(0.0, 1.0, n_samples, endpoint=False)) ** 2
    out = sig * env * 32767.0
    return np.clip(out, -32768, 32767).astype(np.int16)


@pytest.fixture
def vm() -> Generator[VoiceAuthManager, None, None]:
    manager = VoiceAuthManager(AUDIO_DIR)
    manager.reset_strikes()
    yield manager
    manager.reset_strikes()


@pytest.fixture
def pcm_owner() -> np.ndarray:
    return load_wav("giong_1_chu_nha_mo_cua.wav")


@pytest.fixture
def pcm_intruder() -> np.ndarray:
    return load_wav("giong_2_nguoi_la_mo_cua.wav")


# ==============================================================================
# NHÓM 1: STRESS-TEST ÂM ĐỆM & NGẬP NGỪNG (48 KỊCH BẢN LƯỚI F0 x DURATION x PAUSE)
# ==============================================================================

@pytest.mark.parametrize("f0_hz", [75.0, 80.0, 85.0, 90.0])
@pytest.mark.parametrize("dur_sec", [0.2, 0.5, 1.0, 2.0])
@pytest.mark.parametrize("pause_ms", [100, 500, 1000])
def test_hesitation_grid_zero_false_strikes(
    vm: VoiceAuthManager,
    pcm_owner: np.ndarray,
    f0_hz: float,
    dur_sec: float,
    pause_ms: int,
) -> None:
    """Stress-test 48 kịch bản kết hợp: F0 [75-90Hz] x Độ dài [0.2s-2.0s] x Khoảng lặng [100-1000ms]
    ghép trước câu lệnh mở cửa của Chủ nhà.
    Yêu cầu: 100% authorized == True, strike_count == 0, không nhận nhầm người lạ.
    """
    sr = 16000
    filler = synthesize_vocal_fry_filler(f0_hz=f0_hz, duration_sec=dur_sec, sr=sr)
    pause = np.zeros(int(sr * (pause_ms / 1000.0)), dtype=np.int16)
    audio = np.concatenate([filler, pause, pcm_owner])

    vm.reset_strikes()
    res = vm.verify_pcm16k_and_apply_strikes(audio.tobytes())

    assert res["authorized"] is True, (
        f"FALSE REJECTION at F0={f0_hz}Hz, dur={dur_sec}s, pause={pause_ms}ms: "
        f"authorized={res['authorized']}, strike={res['strike_count']}, label={res.get('speaker_label')}"
    )
    assert res["strike_count"] == 0, (
        f"FALSE STRIKE: strike_count={res['strike_count']} (expected 0)"
    )
    assert res["speaker_id"] == "owner_voice_1", (
        f"WRONG SPEAKER ID: {res['speaker_id']}"
    )
    assert res["silent_ignore"] is False
    assert res["should_reply"] is True


@pytest.mark.parametrize("f0_hz", [75.0, 80.0, 85.0, 90.0])
@pytest.mark.parametrize("dur_sec", [0.2, 0.5, 1.0, 2.0])
def test_standalone_filler_zero_false_strikes(
    vm: VoiceAuthManager,
    f0_hz: float,
    dur_sec: float,
) -> None:
    """Stress-test âm đệm đơn lẻ ('ừm', 'ờ') không kèm câu lệnh:
    Xác nhận hệ thống nhận diện là âm đệm của Chủ nhà, authorized == True, strike_count == 0.
    """
    sr = 16000
    filler = synthesize_vocal_fry_filler(f0_hz=f0_hz, duration_sec=dur_sec, sr=sr)

    vm.reset_strikes()
    res = vm.verify_pcm16k_and_apply_strikes(filler.tobytes())

    assert res["authorized"] is True
    assert res["strike_count"] == 0
    assert res["speaker_id"] == "owner_voice_1"
    assert res["filter_stage_used"] == "Bộ Lọc Âm Đệm (Filler-Aware VAD)"


def test_multiple_chained_hesitations(vm: VoiceAuthManager, pcm_owner: np.ndarray) -> None:
    """Stress-test chuỗi ngập ngừng liên tiếp: 'ừm...' (0.5s) + pause (0.3s) + 'ờ...' (0.8s) + pause (0.5s) + lệnh."""
    sr = 16000
    filler1 = synthesize_vocal_fry_filler(f0_hz=82.0, duration_sec=0.5, sr=sr)
    pause1 = np.zeros(int(sr * 0.3), dtype=np.int16)
    filler2 = synthesize_vocal_fry_filler(f0_hz=88.0, duration_sec=0.8, sr=sr)
    pause2 = np.zeros(int(sr * 0.5), dtype=np.int16)
    audio = np.concatenate([filler1, pause1, filler2, pause2, pcm_owner])

    vm.reset_strikes()
    res = vm.verify_pcm16k_and_apply_strikes(audio.tobytes())

    assert res["authorized"] is True
    assert res["strike_count"] == 0
    assert res["speaker_id"] == "owner_voice_1"


def test_hesitation_in_noisy_environment(vm: VoiceAuthManager, pcm_owner: np.ndarray) -> None:
    """Stress-test ngập ngừng trong môi trường có tiếng quạt trần ù mạnh + tiếng gió."""
    sr = 16000
    filler = synthesize_vocal_fry_filler(f0_hz=84.0, duration_sec=0.6, sr=sr)
    pause = np.zeros(int(sr * 0.3), dtype=np.int16)
    clean_audio = np.concatenate([filler, pause, pcm_owner])

    # Bơm tiếng ồn quạt trần 65Hz + 130Hz
    t = np.arange(clean_audio.size, dtype=np.float32) / sr
    fan_noise = 0.08 * np.sin(2 * np.pi * 65.0 * t) + 0.04 * np.sin(2 * np.pi * 130.0 * t)
    noisy_audio = np.clip(clean_audio.astype(np.float32) + fan_noise * 32768.0, -32768, 32767).astype(np.int16)

    vm.reset_strikes()
    res = vm.verify_pcm16k_and_apply_strikes(noisy_audio.tobytes())

    assert res["authorized"] is True
    assert res["strike_count"] == 0
    assert res["speaker_id"] == "owner_voice_1"


# ==============================================================================
# NHÓM 2: STRESS-TEST NGƯỜI LẠ ĐỘT NHẬP & 3-STRIKE SILENT LOCKOUT
# ==============================================================================

def test_intruder_with_hesitation_is_strictly_rejected(
    vm: VoiceAuthManager,
    pcm_intruder: np.ndarray,
) -> None:
    """Stress-test: Người lạ cố ý phát âm đệm 'ừm' trước khi đọc câu lệnh mở cửa.
    Hệ thống KHÔNG được bỏ qua, phải nhận diện đúng đây là Người lạ và tăng điểm phạt.
    """
    sr = 16000
    filler = synthesize_vocal_fry_filler(f0_hz=85.0, duration_sec=0.5, sr=sr)
    pause = np.zeros(int(sr * 0.25), dtype=np.int16)
    audio = np.concatenate([filler, pause, pcm_intruder])

    vm.reset_strikes()
    res = vm.verify_pcm16k_and_apply_strikes(audio.tobytes())

    assert res["authorized"] is False, "SECURITY BREACH: Intruder with hesitation was authorized!"
    assert res["strike_count"] == 1
    assert res["speaker_id"] == "intruder_voice_2"
    assert res["silent_ignore"] is False
    assert res["rejection_speech"] == "Tôi không được phép nhận lệnh từ người lạ."


@pytest.mark.parametrize("pitch_factor", [0.75, 0.78, 0.82, 0.88, 1.0, 1.15])
def test_intruder_pitch_shift_spoofing_attack(
    vm: VoiceAuthManager,
    pcm_intruder: np.ndarray,
    pitch_factor: float,
) -> None:
    """Tấn công giả mạo cao độ (Pitch-Shift Spoofing Attack):
    Người lạ dùng thuật toán DSP biến đổi F0 của mình để trùng với F0 của Chủ nhà (~170Hz).
    Bộ lọc sinh trắc học sâu Tầng 2 (Formants F1-F4, MFCC, Delta) phải chặn đứng 100%.
    """
    shifted_intruder = transform_pcm_by_pitch_factor(pcm_intruder, factor=pitch_factor, sr=16000)

    vm.reset_strikes()
    res = vm.verify_pcm16k_and_apply_strikes(shifted_intruder.tobytes())

    assert res["authorized"] is False, (
        f"SECURITY BREACH: Pitch-shifted intruder (factor={pitch_factor}) bypassed authentication!"
    )
    assert res["strike_count"] == 1


def test_three_strike_lockout_strict_sequence_and_recovery(
    vm: VoiceAuthManager,
    pcm_intruder: np.ndarray,
    pcm_owner: np.ndarray,
) -> None:
    """Stress-test chuỗi 3-Strike Lockout đối kháng:
    - Lần 1: Từ chối, strike=1, cảnh báo câu 1, should_reply=True, silent_ignore=False
    - Lần 2: Từ chối, strike=2, cảnh báo câu 2, should_reply=True, silent_ignore=False
    - Lần 3: Từ chối, strike=3, im lặng tuyệt đối, should_reply=False, silent_ignore=True, rejection_speech=""
    - Lần 4: Tiếp tục im lặng tuyệt đối (strike=4, silent_ignore=True)
    - Lần 5: Tiếp tục im lặng tuyệt đối (strike=5, silent_ignore=True)
    - Phục hồi: Chủ nhà nói câu lệnh -> Mở khóa ngay lập tức, strike=0, authorized=True
    """
    vm.reset_strikes()

    # Strike 1
    r1 = vm.verify_pcm16k_and_apply_strikes(pcm_intruder.tobytes())
    assert r1["authorized"] is False
    assert r1["strike_count"] == 1
    assert r1["silent_ignore"] is False
    assert r1["should_reply"] is True
    assert r1["rejection_speech"] == "Tôi không được phép nhận lệnh từ người lạ."

    # Strike 2
    r2 = vm.verify_pcm16k_and_apply_strikes(pcm_intruder.tobytes())
    assert r2["authorized"] is False
    assert r2["strike_count"] == 2
    assert r2["silent_ignore"] is False
    assert r2["should_reply"] is True
    assert r2["rejection_speech"] == "Tôi sẽ không trả lời bạn lần nữa."

    # Strike 3 (Lockout)
    r3 = vm.verify_pcm16k_and_apply_strikes(pcm_intruder.tobytes())
    assert r3["authorized"] is False
    assert r3["strike_count"] == 3
    assert r3["silent_ignore"] is True
    assert r3["should_reply"] is False
    assert r3["rejection_speech"] == ""

    # Strike 4 (Vẫn Lockout)
    r4 = vm.verify_pcm16k_and_apply_strikes(pcm_intruder.tobytes())
    assert r4["authorized"] is False
    assert r4["strike_count"] >= 3
    assert r4["silent_ignore"] is True
    assert r4["should_reply"] is False
    assert r4["rejection_speech"] == ""

    # Strike 5 (Vẫn Lockout)
    r5 = vm.verify_pcm16k_and_apply_strikes(pcm_intruder.tobytes())
    assert r5["authorized"] is False
    assert r5["strike_count"] >= 3
    assert r5["silent_ignore"] is True
    assert r5["should_reply"] is False
    assert r5["rejection_speech"] == ""

    # Chủ nhà nói sau chuỗi 5 lần tấn công -> Phải mở khóa ngay lập tức
    r_owner = vm.verify_pcm16k_and_apply_strikes(pcm_owner.tobytes())
    assert r_owner["authorized"] is True
    assert r_owner["strike_count"] == 0
    assert r_owner["silent_ignore"] is False
    assert r_owner["should_reply"] is True
    assert r_owner["speaker_id"] == "owner_voice_1"


# ==============================================================================
# NHÓM 3: STRESS-TEST CỔNG KIỂM ĐỊNH CHẤT LƯỢNG GIỌNG THU ÂM (QUALITY GATE)
# ==============================================================================

@pytest.mark.parametrize("duration_sec", [0.1, 0.5, 0.9, 1.2, 1.5, 1.95])
def test_quality_gate_rejects_short_audio(duration_sec: float) -> None:
    """Stress-test: Đoạn thu âm ngắn hơn 2.0s phải bị từ chối với status == 'CHUA_DAT'."""
    sr = 16000
    pcm = np.ones(int(sr * duration_sec), dtype=np.int16) * 1000
    res = validate_voice_enrollment_quality(pcm, sr)

    assert res["ok"] is False
    assert res["verified"] is False
    assert res["status"] == "CHUA_DAT"
    assert "quá ngắn" in res["reason"]


def test_quality_gate_rejects_absolute_silence() -> None:
    """Stress-test: Đoạn thu âm toàn số 0 (im lặng tuyệt đối) dài 2.5s."""
    sr = 16000
    silence = np.zeros(int(sr * 2.5), dtype=np.int16)
    res = validate_voice_enrollment_quality(silence, sr)

    assert res["ok"] is False
    assert res["verified"] is False
    assert res["status"] == "CHUA_DAT"
    assert "RMS" in res["reason"] or "nhỏ" in res["reason"] or "im lặng" in res["reason"]


def test_quality_gate_rejects_sub_threshold_volume() -> None:
    """Stress-test: Đoạn thu âm có âm lượng cực nhỏ (RMS < 0.020, ví dụ micro để quá xa)."""
    sr = 16000
    # Biên độ tối đa 400 (~ RMS 0.008)
    t = np.arange(int(sr * 2.5)) / sr
    low_sig = (400 * np.sin(2 * np.pi * 150.0 * t)).astype(np.int16)
    res = validate_voice_enrollment_quality(low_sig, sr)

    assert res["ok"] is False
    assert res["verified"] is False
    assert res["status"] == "CHUA_DAT"
    assert "RMS" in res["reason"] or "nhỏ" in res["reason"]


def test_quality_gate_rejects_white_gaussian_noise() -> None:
    """Stress-test: Nhiễu trắng Gauss ngẫu nhiên (nhiễu kênh truyền / mic hỏng)."""
    sr = 16000
    rng = np.random.default_rng(2026)
    noise = (rng.normal(0, 0.08, size=int(sr * 2.5)) * 32767.0).astype(np.int16)
    res = validate_voice_enrollment_quality(noise, sr)

    assert res["ok"] is False
    assert res["verified"] is False
    assert res["status"] == "CHUA_DAT"


def test_quality_gate_rejects_microphone_wind_puff() -> None:
    """Stress-test: Tiếng gió thổi micro hoặc tiếng thở phù (năng lượng tập trung siêu trầm <40Hz, không có tiếng người)."""
    sr = 16000
    t = np.arange(int(sr * 2.5)) / sr
    wind = (0.25 * np.sin(2 * np.pi * 28.0 * t) + 0.15 * np.sin(2 * np.pi * 38.0 * t)) * 32767.0
    res = validate_voice_enrollment_quality(wind.astype(np.int16), sr)

    assert res["ok"] is False
    assert res["verified"] is False
    assert res["status"] == "CHUA_DAT"


@pytest.mark.parametrize("freq_hz", [55.0, 65.0, 420.0, 850.0])
def test_quality_gate_rejects_abnormal_pitch_out_of_bounds(freq_hz: float) -> None:
    """Stress-test: Tần số F0 nằm ngoài dải giọng người [75.0Hz - 340.0Hz] (tiếng hú còi, tiếng ù điện áp 50Hz)."""
    sr = 16000
    t = np.arange(int(sr * 2.5)) / sr
    sig = (0.25 * np.sin(2 * np.pi * freq_hz * t) * 32767.0).astype(np.int16)
    res = validate_voice_enrollment_quality(sig, sr)

    assert res["ok"] is False
    assert res["verified"] is False
    assert res["status"] == "CHUA_DAT"


def test_quality_gate_rejects_pitch_instability_chirp() -> None:
    """Stress-test: Cao độ biến thiên quá mạnh (Pitch Std Dev > 38.0Hz) do tiếng hú tần số biến thiên."""
    sr = 16000
    dur = 2.5
    t = np.arange(int(sr * dur)) / sr
    # Tần số quét từ 90Hz lên 320Hz liên tục
    f_t = np.linspace(90.0, 320.0, t.size)
    phase = 2.0 * np.pi * np.cumsum(f_t) / sr
    chirp = (0.30 * np.sin(phase) * 32767.0).astype(np.int16)

    res = validate_voice_enrollment_quality(chirp, sr)
    assert res["ok"] is False
    assert res["verified"] is False
    assert res["status"] == "CHUA_DAT"


def test_quality_gate_rejects_mostly_silence_with_tiny_speech(pcm_owner: np.ndarray) -> None:
    """Stress-test: Nói quá nhanh hoặc chỉ có 1 từ ngắn trong khoảng lặng dài (Voiced Ratio < 35%)."""
    sr = 16000
    silence_2s = np.zeros(int(sr * 2.2), dtype=np.int16)
    short_word = pcm_owner[: int(sr * 0.3)]
    audio = np.concatenate([short_word, silence_2s])

    res = validate_voice_enrollment_quality(audio, sr)
    assert res["ok"] is False
    assert res["verified"] is False
    assert res["status"] == "CHUA_DAT"
    assert "Tỷ lệ đoạn có tiếng nói quá thấp" in res["reason"] or "khoảng lặng" in res["reason"]


def test_quality_gate_accepts_valid_enrollment(pcm_owner: np.ndarray) -> None:
    """Xác nhận mẫu giọng chuẩn đạt đầy đủ 6 tiêu chuẩn âm học:
    Duration >= 2.0s, RMS >= 0.02, Voiced >= 35%, F0 trong [75, 340]Hz, Pitch Std <= 38Hz, SNR >= 10dB.
    """
    sr = 16000
    # Ghép lặp mẫu giọng Chủ nhà để đạt độ dài 2.25s
    enrolled_pcm = np.concatenate([pcm_owner, pcm_owner, pcm_owner])
    res = validate_voice_enrollment_quality(enrolled_pcm, sr)

    assert res["ok"] is True
    assert res["verified"] is True
    assert res["status"] == "DA_DAT"
    assert res["message"] == "Giọng chính đã đạt chuẩn (Đã được)"
    assert res["duration_sec"] >= 2.0
    assert res["rms"] >= 0.020
    assert res["voiced_ratio"] >= 0.35
    assert 75.0 <= res["f0_hz"] <= 340.0
    assert res["pitch_std_hz"] <= 38.0
    assert res["snr_db"] >= 10.0
    assert len(res["embedding"]) == 26
    assert len(res["deep_embedding"]) == 64
    assert len(res["formants_hz"]) == 4


def test_quality_gate_accepts_tier2_and_tier3_valid_enrollment() -> None:
    """Kiểm tra mẫu giọng hợp lệ của Thành viên Cấp 2 và Khách Cấp 3 khi thu âm đạt chuẩn."""
    sr = 16000
    t2 = load_wav("giong_cap2_thanh_vien_a.wav")
    t3 = load_wav("giong_cap3_khach_c.wav")

    t2_long = np.concatenate([t2, t2, t2])
    t3_long = np.concatenate([t3, t3, t3])

    r2 = validate_voice_enrollment_quality(t2_long, sr)
    assert r2["ok"] is True and r2["status"] == "DA_DAT"

    r3 = validate_voice_enrollment_quality(t3_long, sr)
    assert r3["ok"] is True and r3["status"] == "DA_DAT"


def test_filler_sound_must_not_reset_intruder_strikes(
    vm: VoiceAuthManager,
    pcm_intruder: np.ndarray,
) -> None:
    """Lỗ hổng Strike Reset Exploit:
    Người lạ đã bị 2 gậy phạt vi phạm (strike=2).
    Nếu Người lạ hoặc tạp âm phát ra âm đệm ('ừm' 84Hz 0.5s), hệ thống KHÔNG được tự ý reset
    bộ đếm vi phạm về 0, vì điều này cho phép Người lạ vĩnh viễn né tránh 3-strike silent lockout.
    """
    sr = 16000
    filler = synthesize_vocal_fry_filler(f0_hz=84.0, duration_sec=0.5, sr=sr)

    vm.reset_strikes()
    r1 = vm.verify_pcm16k_and_apply_strikes(pcm_intruder.tobytes())
    assert r1["strike_count"] == 1

    r2 = vm.verify_pcm16k_and_apply_strikes(pcm_intruder.tobytes())
    assert r2["strike_count"] == 2

    # Gửi âm đệm đơn lẻ
    _ = vm.verify_pcm16k_and_apply_strikes(filler.tobytes())

    # Bộ đếm phạt không được bị xóa sạch về 0
    assert vm.unauthorized_strikes == 2, (
        f"SECURITY FLAW: Intruder strikes reset to {vm.unauthorized_strikes} after filler sound!"
    )

    # Lần nói tiếp theo của Người lạ phải đạt mốc 3 (Lockout)
    r3 = vm.verify_pcm16k_and_apply_strikes(pcm_intruder.tobytes())
    assert r3["strike_count"] >= 3
    assert r3["silent_ignore"] is True


def test_guest_must_not_escalate_to_owner_tier1_on_slight_acoustic_variation(
    vm: VoiceAuthManager,
) -> None:
    """Lỗ hổng Privilege Escalation (Leo thang đặc quyền):
    Khách C (Tier 3) phát âm câu lệnh nhưng có độ biến thiên âm học nhẹ (ví dụ resampling factor=1.001 hoặc micro khác).
    Hệ thống KHÔNG được tự động nâng cấp Khách C lên Chủ nhà Cấp 1 (tier=1, owner_voice_1, role=ADMIN).
    """
    t3 = load_wav("giong_cap3_khach_c.wav")
    # Thay đổi âm học siêu nhỏ (hệ số pitch 1.001 hoặc truyền qua codec)
    t3_varied = transform_pcm_by_pitch_factor(t3, factor=1.001, sr=16000)

    vm.reset_strikes()
    res = vm.verify_pcm16k_and_apply_strikes(t3_varied.tobytes())

    assert res.get("tier") != 1, (
        f"PRIVILEGE ESCALATION: Tier 3 Guest was elevated to Tier 1 Owner! Speaker={res.get('speaker_id')}"
    )
    assert res.get("speaker_id") != "owner_voice_1"

