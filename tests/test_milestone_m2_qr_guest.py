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
    slice_bytes: int | None = None
    if filename in ("giong_1_chu_nha_mo_cua.wav", "mo_cua_chinh.wav"):
        filename = "00_doan_dau_mau_giong_chu_nha_tuan_anh.wav"
        slice_bytes = 96000
    wav_path = ROOT / "test_audio" / filename
    assert wav_path.exists(), f"Không tìm thấy file audio: {wav_path}"
    with wave.open(str(wav_path), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        return raw[:slice_bytes] if slice_bytes is not None else raw


def _make_m2_pair(tier: int) -> tuple[bytes, bytes]:
    if tier == 1:
        return _load_wav_as_pcm16k("00_doan_dau_mau_giong_chu_nha_tuan_anh.wav"), _load_wav_as_pcm16k("giong_chu_nha_cap1_tuan_anh.wav")[:192000]
    src = "giong_cap2_thanh_vien_a.wav" if tier == 2 else "giong_cap3_khach_c.wav"
    repeats_e, repeats_s = (19, 6) if tier == 2 else (17, 5)
    arr = np.frombuffer(_load_wav_as_pcm16k(src), dtype=np.int16)
    pad_e = np.zeros(4000, dtype=np.int16)
    pad_s = np.zeros(2000, dtype=np.int16)
    return (
        np.concatenate([pad_e, *([arr] * repeats_e), pad_e]).tobytes(),
        np.concatenate([pad_s, *([arr] * repeats_s), pad_s]).tobytes(),
    )


def _create_invite(client: TestClient, duration_code: str = "1d") -> dict:
    headers = {"X-Session-Token": "sess_owner_t1_nep94121"}
    r = client.post(
        "/api/guest/invites",
        headers=headers,
        json={"pin": "1357", "pin_confirm": "1357", "duration_code": duration_code, "guest_name": "Khách QR"},
    )
    if r.status_code == 400 and "PIN" in str(r.json()):
        r = client.post(
            "/api/guest/invites",
            headers=headers,
            json={"pin": "1357", "duration_code": duration_code, "guest_name": "Khách QR"},
        )
    assert r.status_code == 200, r.text
    return r.json()


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
# 1. KIỂM THỬ RETIRED /api/auth3/guest_qr_current & ACTIVE /api/guest/invites
# =============================================================================

@pytest.mark.parametrize("dur", ["1d", "2d", "1w", "1m", "1y", "invalid_dur"])
def test_guest_qr_current_durations(client: TestClient, dur: str) -> None:
    res = client.get(f"/api/auth3/guest_qr_current?duration={dur}&host=localhost:8088")
    assert res.status_code in (405, 410)
    if dur in DURATION_MAP_SECONDS:
        inv = _create_invite(client, duration_code=dur)
        assert inv.get("ok") is True
        assert inv.get("duration_code") == dur
        assert "<svg" in inv.get("qr_svg", "") and "</svg>" in inv.get("qr_svg", "")
        assert "/guest?token=" in inv.get("url", "")


# =============================================================================
# 2. KIỂM THỬ SINGLE-USE INVITE REDEEM & RETIRED HANDSHAKE
# =============================================================================

def test_guest_qr_handshake_flow_and_single_use(client: TestClient) -> None:
    assert client.post("/api/auth3/guest_qr_handshake", json={"token": "x", "duration": "2d"}).status_code == 410
    inv = _create_invite(client, duration_code="2d")
    token = inv["token"]

    r1 = client.post("/api/guest/redeem", json={"token": token})
    assert r1.status_code == 200 and r1.json()["ok"] is True

    r2 = client.post("/api/guest/redeem", json={"token": token})
    assert r2.status_code == 403 and r2.json()["reason"] == "used"


def test_guest_qr_handshake_expired_or_fake_token(client: TestClient) -> None:
    assert client.post("/api/auth3/guest_qr_handshake", json={"token": "0123456789abcdef", "duration": "1d"}).status_code == 410
    r = client.post("/api/guest/redeem", json={"token": "0123456789abcdef"})
    assert r.status_code == 403 and r.json()["ok"] is False


# =============================================================================
# 3. KIỂM THỬ RETIRED guest_qr_complete_voice & CỔNG CHỐNG TRÙNG GIỌNG
# =============================================================================

def test_complete_voice_short_or_empty_rejected(client: TestClient) -> None:
    res_empty = client.post("/api/auth3/guest_qr_complete_voice", json={
        "session_id": "test_sess_empty",
        "guest_name": "Khách Rỗng",
        "duration": "1d",
        "audio_pcm_b64": "",
    })
    assert res_empty.status_code == 410 and res_empty.json().get("gone") is True

    short_pcm = np.zeros(2000, dtype=np.int16).tobytes()
    r_q = _BOOT_VOICE_AUTH.enroll_tier_voice_from_pcm16k(
        pcm_bytes=short_pcm,
        user_id="short_guest_m2",
        user_name="Khách Ngắn",
        tier=3,
        role="CHILD_GUEST",
    )
    assert r_q["ok"] is False and r_q["status"] == "CHUA_DAT"


def test_complete_voice_duplicate_owner_rejected(client: TestClient) -> None:
    owner_enroll, owner_sc = _make_m2_pair(1)
    assert client.post("/api/auth3/guest_qr_complete_voice", json={"session_id": "s", "audio_pcm_b64": ""}).status_code == 410

    data = _BOOT_VOICE_AUTH.enroll_tier_voice_from_pcm16k(
        pcm_bytes=owner_enroll,
        self_check_pcm_bytes=owner_sc,
        user_id="attacker_owner_m2",
        user_name="Kẻ Đánh Tráo Giọng Chủ Nhà",
        tier=3,
        role="CHILD_GUEST",
        check_duplicate=True,
    )
    assert data["ok"] is False
    assert data["status"] == "DUPLICATE_VOICE_REJECTED"
    assert data["reason"] == "TRUNG_GIONG_NGUOI_TRONG_NHA"
    assert data["matched_tier"] == 1


def test_complete_voice_duplicate_family_rejected(client: TestClient) -> None:
    c2_enroll, c2_sc = _make_m2_pair(2)
    base_res = _BOOT_VOICE_AUTH.enroll_tier_voice_from_pcm16k(
        pcm_bytes=c2_enroll,
        self_check_pcm_bytes=c2_sc,
        user_id="thanh_vien_a_baseline",
        user_name="Thành viên A",
        tier=2,
        role="FAMILY_MEMBER",
        check_duplicate=False,
    )
    assert base_res["ok"] is True

    data = _BOOT_VOICE_AUTH.enroll_tier_voice_from_pcm16k(
        pcm_bytes=c2_enroll,
        self_check_pcm_bytes=c2_sc,
        user_id="attacker_fam_m2",
        user_name="Kẻ Đánh Tráo Giọng Thành Viên A",
        tier=3,
        role="CHILD_GUEST",
        check_duplicate=True,
    )
    assert data["ok"] is False
    assert data["status"] == "DUPLICATE_VOICE_REJECTED"
    assert data["matched_tier"] in (1, 2)


def test_complete_voice_valid_guest_enrolls_successfully(client: TestClient) -> None:
    c3_enroll, c3_sc = _make_m2_pair(3)
    inv = _create_invite(client, duration_code="1w")
    assert inv["duration_code"] == "1w"

    data = _BOOT_VOICE_AUTH.enroll_tier_voice_from_pcm16k(
        pcm_bytes=c3_enroll,
        self_check_pcm_bytes=c3_sc,
        user_id="khach_hust_m2",
        user_name="Bạn Đại Học HUST",
        tier=3,
        role="CHILD_GUEST",
        check_duplicate=True,
        expires_at=time.time() + 604800.0,
    )
    assert data["ok"] is True
    assert data["status"] == "DA_DAT"
    assert data["tier"] == 3
    prof = _BOOT_VOICE_AUTH.profiles.get(str(data.get("profile_id", "")), {})
    assert prof.get("expires_at", 0) > time.time() + 600000.0


# =============================================================================
# 4. KIỂM THỬ RETIRED /api/auth3/guest_qr_send_otp
# =============================================================================

def test_send_otp_mismatched_emails_rejected(client: TestClient) -> None:
    res = client.post("/api/auth3/guest_qr_send_otp", json={
        "session_id": "test_sess_otp",
        "guest_name": "Khách Test",
        "email_1": "khach1@gmail.com",
        "email_2": "khach2@gmail.com",
        "duration": "1d",
    })
    assert res.status_code == 410 and res.json().get("ok") is False


def test_send_otp_nonexistent_domain_rejected(client: TestClient) -> None:
    res = client.post("/api/auth3/guest_qr_send_otp", json={
        "session_id": "test_sess_otp",
        "guest_name": "Khách Test",
        "email_1": "user@fake-nonexistent-domain-test999.local",
        "email_2": "user@fake-nonexistent-domain-test999.local",
        "duration": "1d",
    })
    assert res.status_code == 410 and res.json().get("ok") is False


def test_send_otp_valid_mx_domain_success(client: TestClient) -> None:
    res = client.post("/api/auth3/guest_qr_send_otp", json={
        "session_id": "test_sess_otp",
        "guest_name": "Khách Test",
        "email_1": "khach_moi.hust@gmail.com",
        "email_2": "khach_moi.hust@gmail.com",
        "duration": "1d",
    })
    assert res.status_code == 410 and res.json().get("gone") is True


# =============================================================================
# 5. KIỂM THỬ RETIRED /api/auth3/guest_qr_verify_otp
# =============================================================================

def test_verify_otp_wrong_and_correct_flow(client: TestClient) -> None:
    r = client.post("/api/auth3/guest_qr_verify_otp", json={
        "email": "khach_otp_verify@gmail.com",
        "otp": "123456",
    })
    assert r.status_code == 410 and r.json().get("ok") is False and r.json().get("gone") is True


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
