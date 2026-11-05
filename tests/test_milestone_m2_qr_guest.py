"""Bộ Kiểm Thử Milestone M2 (Dynamic QR 10s, 5 Guest APIs, Guest Mic 16kHz & Email OTP).

Kiểm thử toàn diện:
1. 5 API khách với các status code và payload hợp lệ:
   - GET /api/auth3/guest_qr_current (5 mốc: 1d, 2d, 1w, 1m, 1y, slot TOTP 10s, SVG QR thực tế).
   - POST /api/auth3/guest_qr_handshake (xác thực token TOTP, lock_ttl_sec 180s, session lồng).
   - POST /api/auth3/guest_qr_complete_voice (Cổng chống trùng giọng check_duplicate_voice_gate, lưu expires_at).
   - POST /api/auth3/guest_qr_send_otp (so sánh 2 ô email, kiểm tra DNS MX qua nslookup/resolver, sinh OTP 6 số).
   - POST /api/auth3/guest_qr_verify_otp (xác thực OTP đúng/sai, cấp quyền khách theo hạn).
2. Token TOTP 10s đổi mới sau 10 giây & Single-Use Token.
3. Chống trùng giọng khi khách gửi audio của Chủ nhà hoặc Thành viên A.
4. Đăng ký thành công giọng khách mới đạt chuẩn âm học 16kHz PCM.
5. Tinh chỉnh âm học is_genuine_owner_filler chặn tuyệt đối kẻ xâm nhập pitch-shift dải [1.18x - 1.28x].
"""

from __future__ import annotations

import base64
import io
import pathlib
import sys
import time
import wave
import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.server import _BOOT_VOICE_AUTH, app
from simulator.auth_3layer import (
    DURATION_MAP_SECONDS,
    get_auth_3layer_manager,
)
from simulator.voice_auth import (
    VoiceAuthManager,
    transform_pcm_by_pitch_factor,
)


@pytest.fixture(autouse=True)
def clean_test_state():
    """Dọn dẹp token đã dùng và khôi phục trạng thái voice auth sạch trước mỗi test."""
    mgr = get_auth_3layer_manager()
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    yield
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers={"Authorization": "Bearer sess_owner_t1_nep94121"})


def _load_wav_as_pcm16k(filename: str) -> bytes:
    if filename in ("giong_1_chu_nha_mo_cua.wav", "mo_cua_chinh.wav"):
        filename = "cac_cau_lenh_cua_sep/cau_2_mo_cua_chinh.wav"
    wav_path = ROOT / "test_audio" / filename
    assert wav_path.exists(), f"Không tìm thấy file audio: {wav_path}"
    with wave.open(str(wav_path), "rb") as wf:
        return wf.readframes(wf.getnframes())


def _generate_synthetic_guest_pcm(
    duration_sec: float = 2.8,
    f0: float = 215.0,
    silence_sec: float = 0.3,
) -> bytes:
    """Sinh tín hiệu PCM 16kHz mono có khoảng lặng đầu và sóng hài rõ nét để đạt chuẩn âm học."""
    sr = 16000
    n_silence = int(sr * silence_sec)
    n_voice = int(sr * max(0.1, duration_sec - silence_sec))
    silence = np.zeros(n_silence, dtype=np.float32)
    t = np.linspace(0, max(0.1, duration_sec - silence_sec), n_voice, endpoint=False)
    voice = (
        0.40 * np.sin(2 * np.pi * f0 * t)
        + 0.20 * np.sin(2 * np.pi * (f0 * 2) * t)
        + 0.10 * np.sin(2 * np.pi * (f0 * 3) * t)
    )
    sig = np.concatenate([silence, voice])
    pcm16 = (sig * 32767).astype(np.int16)
    return pcm16.tobytes()


# =============================================================================
# 1. KIỂM THỬ GET /api/auth3/guest_qr_current
# =============================================================================

@pytest.mark.parametrize("dur", ["1d", "2d", "1w", "1m", "1y", "invalid_dur"])
def test_guest_qr_current_durations(client: TestClient, dur: str) -> None:
    res = client.get(f"/api/auth3/guest_qr_current?duration={dur}&host=localhost:8088")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "token" in data and len(data["token"]) == 16
    expected_dur = dur if dur in DURATION_MAP_SECONDS else "1d"
    assert data["duration"] == expected_dur
    assert data["duration_seconds"] == DURATION_MAP_SECONDS[expected_dur]
    assert 1 <= data["remaining_slot_sec"] <= 10
    assert "remaining_Slot_sec" not in data
    assert "qr_svg" in data
    assert "<svg" in data["qr_svg"] and "</svg>" in data["qr_svg"]
    assert "/guest_enroll?token=" in data["qr_url"]


# =============================================================================
# 2. KIỂM THỬ POST /api/auth3/guest_qr_handshake & TOKEN TOTP 10s
# =============================================================================

def test_guest_qr_handshake_flow_and_single_use(client: TestClient) -> None:
    # 1. Lấy token hợp lệ
    cur_res = client.get("/api/auth3/guest_qr_current?duration=2d")
    assert cur_res.status_code == 200
    token = cur_res.json()["token"]

    # 2. Handshake lần 1 -> Thành công
    hs_res = client.post("/api/auth3/guest_qr_handshake", json={"token": token, "duration": "2d"})
    assert hs_res.status_code == 200
    hs_data = hs_res.json()
    assert hs_data["ok"] is True
    assert "session" in hs_data
    assert hs_data["session"]["session_id"].startswith("guest_sess_")
    assert hs_data["session"]["duration_code"] == "2d"
    assert hs_data["session"]["lock_ttl_sec"] == 180

    # 3. Handshake lần 2 với cùng token -> Single-Use Token từ chối (400)
    hs2_res = client.post("/api/auth3/guest_qr_handshake", json={"token": token, "duration": "2d"})
    assert hs2_res.status_code == 400
    assert hs2_res.json()["ok"] is False
    assert "Single-Use" in hs2_res.json()["error"] or "đã được sử dụng" in hs2_res.json()["error"]


def test_guest_qr_handshake_expired_or_fake_token(client: TestClient) -> None:
    # Token giả mạo hoặc hết hạn
    fake_token = "0123456789abcdef"
    res = client.post("/api/auth3/guest_qr_handshake", json={"token": fake_token, "duration": "1d"})
    assert res.status_code in (400, 401)
    assert res.json()["ok"] is False


# =============================================================================
# 3. KIỂM THỬ POST /api/auth3/guest_qr_complete_voice (CỔNG CHỐNG TRÙNG GIỌNG)
# =============================================================================

def test_complete_voice_short_or_empty_rejected(client: TestClient) -> None:
    # 1. Audio rỗng
    res_empty = client.post("/api/auth3/guest_qr_complete_voice", json={
        "session_id": "test_sess_empty",
        "guest_name": "Khách Rỗng",
        "duration": "1d",
        "audio_pcm_b64": "",
    })
    assert res_empty.status_code == 400
    assert res_empty.json()["status"] == "CHUA_DAT"

    # 2. Audio quá ngắn (< 0.5s)
    short_pcm = np.zeros(2000, dtype=np.int16).tobytes()
    b64_short = base64.b64encode(short_pcm).decode("utf-8")
    res_short = client.post("/api/auth3/guest_qr_complete_voice", json={
        "session_id": "test_sess_short",
        "guest_name": "Khách Ngắn",
        "duration": "1d",
        "audio_pcm_b64": b64_short,
    })
    assert res_short.status_code == 400
    assert res_short.json()["status"] == "CHUA_DAT"


def test_complete_voice_duplicate_owner_rejected(client: TestClient) -> None:
    owner_pcm = _load_wav_as_pcm16k("giong_1_chu_nha_mo_cua.wav")
    # Lặp lại để đạt thời lượng > 2.0s
    long_owner_pcm = owner_pcm * 3
    b64_pcm = base64.b64encode(long_owner_pcm).decode("utf-8")

    # Lấy token & handshake
    cur_res = client.get("/api/auth3/guest_qr_current?duration=1d")
    token = cur_res.json()["token"]
    hs_res = client.post("/api/auth3/guest_qr_handshake", json={"token": token, "duration": "1d"})
    assert hs_res.status_code == 200
    sess_id = hs_res.json()["session"]["session_id"]

    # Gửi giọng Chủ nhà lên cổng đăng ký khách
    res = client.post("/api/auth3/guest_qr_complete_voice", json={
        "session_id": sess_id,
        "guest_name": "Kẻ Đánh Tráo Giọng Chủ Nhà",
        "duration": "1d",
        "audio_pcm_b64": b64_pcm,
    })
    assert res.status_code == 400
    data = res.json()
    assert data["ok"] is False
    assert data["status"] == "DUPLICATE_VOICE_REJECTED"
    assert data["reason"] == "TRUNG_GIONG_NGUOI_TRONG_NHA"
    assert data["matched_tier"] == 1


def test_complete_voice_duplicate_family_rejected(client: TestClient) -> None:
    # 1. Đăng ký Thành viên A vào hệ thống trước để Cổng Chống Trùng Giọng có mẫu đối chiếu
    family_pcm = _load_wav_as_pcm16k("giong_cap2_thanh_vien_a.wav")
    long_family_pcm = family_pcm * 3
    _BOOT_VOICE_AUTH.enroll_tier_voice_from_pcm16k(
        pcm_bytes=long_family_pcm,
        user_id="thanh_vien_a_baseline",
        user_name="Thành viên A",
        tier=2,
        role="FAMILY_MEMBER",
        check_duplicate=False,
    )

    b64_pcm = base64.b64encode(long_family_pcm).decode("utf-8")

    cur_res = client.get("/api/auth3/guest_qr_current?duration=1d")
    token = cur_res.json()["token"]
    hs_res = client.post("/api/auth3/guest_qr_handshake", json={"token": token, "duration": "1d"})
    assert hs_res.status_code == 200
    sess_id = hs_res.json()["session"]["session_id"]

    # Khách gửi lại chính giọng Thành viên A để đăng ký khách C3
    res = client.post("/api/auth3/guest_qr_complete_voice", json={
        "session_id": sess_id,
        "guest_name": "Kẻ Đánh Tráo Giọng Thành Viên A",
        "duration": "1d",
        "audio_pcm_b64": b64_pcm,
    })
    assert res.status_code == 400
    data = res.json()
    assert data["ok"] is False
    assert data["status"] == "DUPLICATE_VOICE_REJECTED"
    assert data["matched_tier"] in (1, 2)


def test_complete_voice_valid_guest_enrolls_successfully(client: TestClient) -> None:
    # Sinh giọng khách mới hợp lệ 2.8s (F0 = 245.0Hz khác biệt rõ nét)
    guest_pcm = _generate_synthetic_guest_pcm(duration_sec=2.8, f0=245.0)
    b64_pcm = base64.b64encode(guest_pcm).decode("utf-8")

    cur_res = client.get("/api/auth3/guest_qr_current?duration=1w")
    token = cur_res.json()["token"]
    hs_res = client.post("/api/auth3/guest_qr_handshake", json={"token": token, "duration": "1w"})
    assert hs_res.status_code == 200
    sess_id = hs_res.json()["session"]["session_id"]

    res = client.post("/api/auth3/guest_qr_complete_voice", json={
        "session_id": sess_id,
        "guest_name": "Bạn Đại Học HUST",
        "duration": "1w",
        "audio_pcm_b64": b64_pcm,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["status"] == "DA_DAT"
    assert data["tier"] == 3
    assert data["duration_code"] == "1w"
    assert data["duration_seconds"] == 604800
    assert data["expires_at"] > time.time() + 600000.0


# =============================================================================
# 4. KIỂM THỬ POST /api/auth3/guest_qr_send_otp & DNS MX
# =============================================================================

def test_send_otp_mismatched_emails_rejected(client: TestClient) -> None:
    res = client.post("/api/auth3/guest_qr_send_otp", json={
        "session_id": "test_sess_otp",
        "guest_name": "Khách Test",
        "email_1": "khach1@gmail.com",
        "email_2": "khach2@gmail.com",
        "duration": "1d",
    })
    assert res.status_code == 400
    data = res.json()
    assert data["ok"] is False
    assert "không khớp" in data["error"]


def test_send_otp_nonexistent_domain_rejected(client: TestClient) -> None:
    # Tên miền ảo không có bản ghi MX
    res = client.post("/api/auth3/guest_qr_send_otp", json={
        "session_id": "test_sess_otp",
        "guest_name": "Khách Test",
        "email_1": "user@fake-nonexistent-domain-test999.local",
        "email_2": "user@fake-nonexistent-domain-test999.local",
        "duration": "1d",
    })
    assert res.status_code == 400
    data = res.json()
    assert data["ok"] is False
    assert "MX" in data["error"] or "không có bản ghi" in data["error"]


def test_send_otp_valid_mx_domain_success(client: TestClient) -> None:
    res = client.post("/api/auth3/guest_qr_send_otp", json={
        "session_id": "test_sess_otp",
        "guest_name": "Khách Test",
        "email_1": "khach_moi.hust@gmail.com",
        "email_2": "khach_moi.hust@gmail.com",
        "duration": "1d",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["otp_dispatched"] is True
    assert len(data["demo_otp_preview"]) == 6
    assert data["demo_otp_preview"].isdigit()


# =============================================================================
# 5. KIỂM THỬ POST /api/auth3/guest_qr_verify_otp
# =============================================================================

def test_verify_otp_wrong_and_correct_flow(client: TestClient) -> None:
    target_email = "khach_otp_verify@gmail.com"
    # Gửi OTP
    send_res = client.post("/api/auth3/guest_qr_send_otp", json={
        "session_id": "test_sess_verify",
        "guest_name": "Khách OTP Verify",
        "email_1": target_email,
        "email_2": target_email,
        "duration": "2d",
    })
    assert send_res.status_code == 200
    valid_otp = send_res.json()["demo_otp_preview"]

    # 1. Thử mã OTP sai
    wrong_res = client.post("/api/auth3/guest_qr_verify_otp", json={
        "email": target_email,
        "otp": "000000" if valid_otp != "000000" else "111111",
    })
    assert wrong_res.status_code == 400
    assert wrong_res.json()["ok"] is False
    assert "chưa đúng" in wrong_res.json()["error"] or "không chính xác" in wrong_res.json()["error"]

    # 2. Nhập mã OTP đúng
    correct_res = client.post("/api/auth3/guest_qr_verify_otp", json={
        "email": target_email,
        "otp": valid_otp,
    })
    assert correct_res.status_code == 200
    c_data = correct_res.json()
    assert c_data["ok"] is True
    assert c_data["verified"] is True
    assert c_data["expires_at"] > time.time() + 100000.0


# =============================================================================
# 6. KIỂM THỬ TINH CHỈNH ÂM HỌC is_genuine_owner_filler VỚI PITCH SHIFT
# =============================================================================

def test_acoustic_filler_tuning_blocks_pitch_shifted_intruder() -> None:
    """Kiểm tra điều kiện is_genuine_owner_filler có neural_sim_own >= 0.90 và neural_sim_own > neural_sim_intr,

    đảm bảo Người lạ và Khách C pitch-shift dải [1.18x - 1.28x] tuyệt đối không nhận quyền Chủ nhà C1.
    """
    va = VoiceAuthManager(ROOT / "test_audio")
    intruder_pcm = _load_wav_as_pcm16k("giong_2_nguoi_la_mo_cua.wav")
    intruder_arr = np.frombuffer(intruder_pcm, dtype=np.int16)

    # Thử các hệ số pitch shift trong dải hẹp [1.18, 1.28]
    for factor in [1.18, 1.20, 1.22, 1.24, 1.25, 1.28]:
        shifted = transform_pcm_by_pitch_factor(intruder_arr, factor=factor, sr=16000)
        va.reset_strikes()
        res = va.verify_pcm16k_and_apply_strikes(shifted.tobytes())
        # Người lạ không bao giờ được cấp quyền Chủ nhà (Tier 1)
        assert res.get("tier") != 1, f"LỖ HỔNG: Người lạ pitch-shift {factor}x bị nhận nhầm thành Chủ nhà Cấp 1!"
        assert res.get("speaker_id") != "owner_voice_1", f"LỖ HỔNG: Speaker ID là Chủ nhà عند {factor}x!"
        assert res.get("role") != "ADMIN", f"LỖ HỔNG: Role là ADMIN tại factor={factor}x!"
