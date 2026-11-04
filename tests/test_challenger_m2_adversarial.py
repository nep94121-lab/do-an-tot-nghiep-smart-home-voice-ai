"""Bộ Kiểm Thử Đối Kháng Thực Nghiệm (Adversarial Empirical Stress-Test) cho Cổng Gate Milestone M2.

Thực hiện bởi: Challenger 1 (challenger_m2_1)
Nhiệm vụ:
1. Thực nghiệm đối kháng TOTP 10s: token hợp lệ vs token quá hạn >20s (chặn 100%), Replay attack (chặn 100%).
2. Khai thác & kiểm chứng lỗ hổng Target Window Forgery / Token Bypass.
3. Thực nghiệm đối kháng Duplicate Voice Attack: khách mạo danh Chủ nhà / Thành viên gia đình (chặn 100% DUPLICATE_VOICE_REJECTED), bảo toàn 100% quyền Cấp 1 ADMIN cho Chủ nhà ngay sau tấn công.
4. Thực nghiệm phân quyền Cấp 3 (Tier 3 Boundary): Khách Cấp 3 chỉ điều khiển Đèn, Quạt; bị chặn 100% khi đòi Mở cửa chính hay Còi báo động.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
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
from simulator.rule_engine import SmartHomeEngine


@pytest.fixture(autouse=True)
def clean_adversarial_state():
    """Làm sạch trạng thái token và voice auth trước mỗi test."""
    mgr = get_auth_3layer_manager()
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    if hasattr(mgr, "active_qr_tokens"):
        mgr.active_qr_tokens.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    yield
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    if hasattr(mgr, "active_qr_tokens"):
        mgr.active_qr_tokens.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _load_wav_pcm16k(filename: str) -> bytes:
    wav_path = ROOT / "test_audio" / filename
    assert wav_path.exists(), f"Không tìm thấy file audio: {wav_path}"
    with wave.open(str(wav_path), "rb") as wf:
        return wf.readframes(wf.getnframes())


def _create_synthetic_guest_pcm(duration_sec: float = 2.8, f0: float = 235.0, silence_sec: float = 0.35) -> bytes:
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
# 1. THỰC NGHIỆM ĐỐI KHÁNG TOTP 10S: HẾT HẠN & REPLAY ATTACK
# =============================================================================

class TestTOTPAdversarial:
    """Kiểm thử đối kháng tính nghiêm ngặt của TOTP 10s và phòng chống tấn công Replay."""

    def test_totp_10s_valid_and_expiration_boundary(self, client: TestClient) -> None:
        """1. Token trong slot 10s -> Thành công (200).
        2. Token quá hạn > 20s (slot diff >= 2) -> Bị từ chối 100% (401).
        3. Token quá hạn 100s -> Bị từ chối 100% (401).
        """
        # Sinh token hợp lệ hiện tại
        cur_res = client.get("/api/auth3/guest_qr_current?duration=1d")
        assert cur_res.status_code == 200
        valid_tok = cur_res.json()["token"]

        # Handshake token hợp lệ -> Thành công
        hs_ok = client.post("/api/auth3/guest_qr_handshake", json={"token": valid_tok, "duration": "1d"})
        assert hs_ok.status_code == 200
        assert hs_ok.json()["ok"] is True
        assert hs_ok.json()["session"]["session_id"].startswith("guest_sess_")

        # Thử nghiệm Token quá hạn > 180 giây (lệch 20 slot TOTP = 200s)
        now_ts = time.time()
        expired_win_200s = int((now_ts - 200) // 10)
        secret = "bk_smarthome_totp_salt_2026"
        raw_p_200s = f"{expired_win_200s}:1:1d:86400"
        expired_token_200s = hmac.new(secret.encode(), raw_p_200s.encode(), hashlib.sha256).hexdigest()[:16]

        hs_exp_200s = client.post("/api/auth3/guest_qr_handshake", json={"token": expired_token_200s, "duration": "1d"})
        assert hs_exp_200s.status_code == 401
        assert hs_exp_200s.json()["ok"] is False
        assert "hết hạn 180 giây" in hs_exp_200s.json()["error"]

        # Thử nghiệm Token quá hạn 300 giây (lệch 30 slot TOTP)
        expired_win_300s = int((now_ts - 300) // 10)
        raw_p_300s = f"{expired_win_300s}:1:1d:86400"
        expired_token_300s = hmac.new(secret.encode(), raw_p_300s.encode(), hashlib.sha256).hexdigest()[:16]

        hs_exp_300s = client.post("/api/auth3/guest_qr_handshake", json={"token": expired_token_300s, "duration": "1d"})
        assert hs_exp_300s.status_code == 401
        assert hs_exp_300s.json()["ok"] is False
        assert "hết hạn 180 giây" in hs_exp_300s.json()["error"]

    def test_totp_single_use_and_replay_attack(self, client: TestClient) -> None:
        """Tấn công Replay: Dùng lại token đã handshake thành công -> Bắt buộc bị từ chối 100% (400)."""
        cur_res = client.get("/api/auth3/guest_qr_current?duration=2d")
        token = cur_res.json()["token"]

        # Lần 1: Bắt tay hợp lệ
        res1 = client.post("/api/auth3/guest_qr_handshake", json={"token": token, "duration": "2d"})
        assert res1.status_code == 200
        assert res1.json()["ok"] is True

        # Tấn công Replay Lần 2: Dùng lại cùng token
        res_replay = client.post("/api/auth3/guest_qr_handshake", json={"token": token, "duration": "2d"})
        assert res_replay.status_code == 400
        assert res_replay.json()["ok"] is False
        assert "Single-Use" in res_replay.json()["error"] or "đã được sử dụng" in res_replay.json()["error"]

        # Tấn công Replay Lần 3: Thay đổi duration
        res_replay3 = client.post("/api/auth3/guest_qr_handshake", json={"token": token, "duration": "1y"})
        assert res_replay3.status_code == 400
        assert res_replay3.json()["ok"] is False

    def test_adversarial_vulnerability_target_window_forgery(self, client: TestClient) -> None:
        """Kiểm chứng đòn tấn công Target Window Forgery:
        Khi kẻ tấn công gửi token bịa đặt kèm window hiện tại, backend BẮT BUỘC từ chối 100% với HTTP 401.
        """
        cur_win = int(time.time() // 10)
        bogus_token = "adversarial_hack"

        # Kẻ tấn công gửi token hoàn toàn bịa đặt kèm window hiện tại
        exploit_res = client.post("/api/auth3/guest_qr_handshake", json={
            "token": bogus_token,
            "window": cur_win,
            "duration": "1y",
        })

        assert exploit_res.status_code == 401
        assert exploit_res.json()["ok"] is False
        assert "không hợp lệ hoặc đã hết hạn" in exploit_res.json()["error"]



# =============================================================================
# 2. THỰC NGHIỆM ĐỐI KHÁNG DUPLICATE VOICE ATTACK
# =============================================================================

class TestDuplicateVoiceAdversarial:
    """Kiểm thử đối kháng Cổng Chống Trùng Giọng (Duplicate Voiceprint Reject Gate)."""

    def test_guest_enroll_with_owner_voice_strictly_rejected(self, client: TestClient) -> None:
        """Khách cố tình gửi audio của Chủ nhà giong_1_chu_nha_mo_cua.wav -> Bắt buộc từ chối 100% (DUPLICATE_VOICE_REJECTED)."""
        owner_pcm = _load_wav_pcm16k("giong_1_chu_nha_mo_cua.wav")
        long_pcm = owner_pcm * 3
        b64_audio = base64.b64encode(long_pcm).decode("utf-8")

        # Lấy token & handshake hợp lệ
        cur = client.get("/api/auth3/guest_qr_current?duration=1d").json()
        hs = client.post("/api/auth3/guest_qr_handshake", json={"token": cur["token"], "duration": "1d"}).json()
        sess_id = hs["session"]["session_id"]

        # Gửi giọng Chủ nhà lên cổng đăng ký khách Cấp 3
        comp = client.post("/api/auth3/guest_qr_complete_voice", json={
            "session_id": sess_id,
            "guest_name": "Kẻ Đánh Tráo Giọng Chủ Nhà",
            "duration": "1d",
            "audio_pcm_b64": b64_audio,
        })
        assert comp.status_code == 400
        data = comp.json()
        assert data["ok"] is False
        assert data["status"] == "DUPLICATE_VOICE_REJECTED"
        assert data["reason"] == "TRUNG_GIONG_NGUOI_TRONG_NHA"
        assert data["matched_tier"] == 1
        assert "Nguyễn Tuấn Anh" in data["matched_name"]

    def test_owner_voice_auth_retains_tier_1_admin_after_duplicate_attack(self, client: TestClient) -> None:
        """Sau khi kẻ xấu bị từ chối đòn tấn công trùng giọng, Chủ nhà nói lệnh mở cửa:
        Vẫn nhận diện Cấp 1 ADMIN 100%, tuyệt đối không bị hạ cấp hoặc kẹt quyền Cấp 3.
        """
        owner_pcm = _load_wav_pcm16k("giong_1_chu_nha_mo_cua.wav")

        # Bước 1: Giả lập đòn tấn công mạo danh trước
        cur = client.get("/api/auth3/guest_qr_current?duration=1w").json()
        hs = client.post("/api/auth3/guest_qr_handshake", json={"token": cur["token"], "duration": "1w"}).json()
        sess_id = hs["session"]["session_id"]
        client.post("/api/auth3/guest_qr_complete_voice", json={
            "session_id": sess_id,
            "guest_name": "Kẻ Tấn Công Giọng",
            "duration": "1w",
            "audio_pcm_b64": base64.b64encode(owner_pcm * 3).decode("utf-8"),
        })

        # Bước 2: Ngay lập tức Chủ nhà nói vào Mic
        verify_res = _BOOT_VOICE_AUTH.verify_pcm16k_and_apply_strikes(owner_pcm)
        assert verify_res.get("tier") == 1, f"LỖI: Chủ nhà bị tụt xuống Cấp {verify_res.get('tier')}!"
        assert verify_res.get("role") == "ADMIN", f"LỖI: Role của Chủ nhà bị đổi thành {verify_res.get('role')}!"
        assert verify_res.get("speaker_id") == "owner_voice_1", "LỖI: Speaker ID không phải owner_voice_1!"

    def test_guest_enroll_with_family_member_voice_strictly_rejected(self, client: TestClient) -> None:
        """Khách gửi audio của Thành viên gia đình Cấp 2 -> Bị từ chối 100% (DUPLICATE_VOICE_REJECTED)."""
        family_pcm = _load_wav_pcm16k("giong_cap2_thanh_vien_a.wav")
        long_fam = family_pcm * 3

        # Đăng ký baseline Thành viên A vào hệ thống
        _BOOT_VOICE_AUTH.enroll_tier_voice_from_pcm16k(
            pcm_bytes=long_fam,
            user_id="thanh_vien_a_base",
            user_name="Thành viên A",
            tier=2,
            role="FAMILY_MEMBER",
            check_duplicate=False,
        )

        cur = client.get("/api/auth3/guest_qr_current?duration=1d").json()
        hs = client.post("/api/auth3/guest_qr_handshake", json={"token": cur["token"], "duration": "1d"}).json()
        sess_id = hs["session"]["session_id"]

        comp = client.post("/api/auth3/guest_qr_complete_voice", json={
            "session_id": sess_id,
            "guest_name": "Kẻ Mạo Danh Thành Viên Gia Đình",
            "duration": "1d",
            "audio_pcm_b64": base64.b64encode(long_fam).decode("utf-8"),
        })
        assert comp.status_code == 400
        data = comp.json()
        assert data["ok"] is False
        assert data["status"] == "DUPLICATE_VOICE_REJECTED"
        assert data["matched_tier"] in (1, 2)


# =============================================================================
# 3. THỰC NGHIỆM RANH GIỚI PHÂN QUYỀN CẤP 3 (TIER 3 PRIVILEGE BOUNDARY)
# =============================================================================

class TestTier3PrivilegeBoundary:
    """Kiểm thử ranh giới phân quyền Cấp 3 đối với 7 thiết bị phần cứng & các lệnh quản trị."""

    def test_guest_tier3_hardware_permissions_matrix(self) -> None:
        """Khách Cấp 3:
        - Bật/tắt Đèn khách (D2), Đèn ngủ (D7), Quạt trần (D6) -> CHO PHÉP (ok=True).
        - Mở/đóng Cửa chính (D1), Còi báo động (D8), Điều hòa Casper, Máy bơm -> TỪ CHỐI 100% (ok=False).
        """
        async def _run() -> None:
            engine = SmartHomeEngine()
            engine.set_active_user("khach_c")
            assert engine.current_tier == 3
            assert engine.current_role == "CHILD_GUEST"

            # 1. Các hành động ĐƯỢC PHÉP đối với Khách Cấp 3
            allowed_actions = [
                ("living_room_light", "turn_on"),
                ("living_room_light", "turn_off"),
                ("bedroom_light", "turn_on"),
                ("bedroom_light", "turn_off"),
                ("fan", "turn_on"),
                ("fan", "turn_off"),
            ]
            for dev_id, act in allowed_actions:
                res = await engine.execute_device_action(dev_id, act)
                assert res.get("ok") is True, f"Khách Cấp 3 bị chặn trái phép đối với {dev_id} ({act}): {res}"

            # 2. Các hành động BẮT BUỘC BỊ CHẶN đối với Khách Cấp 3
            blocked_actions = [
                ("main_door", "open"),
                ("main_door", "close"),
                ("alarm_siren", "turn_on"),
                ("alarm_siren", "turn_off"),
                ("ac", "turn_on"),
                ("ac", "turn_off"),
                ("garden_pump", "turn_on"),
                ("garden_pump", "turn_off"),
            ]
            for dev_id, act in blocked_actions:
                res = await engine.execute_device_action(dev_id, act)
                assert res.get("ok") is False, f"LỖ HỔNG: Khách Cấp 3 điều khiển trái phép {dev_id} ({act})!"
                err_msg = res.get("error") or res.get("exact_spoken_reply") or (res.get("results", [{}])[0].get("error", ""))
                assert "Từ chối truy cập" in err_msg, f"Không có thông báo 'Từ chối truy cập': {res}"

        asyncio.run(_run())

    def test_guest_tier3_admin_bypass_strictly_blocked(self) -> None:
        """Khách Cấp 3 tuyệt đối không được sửa luật hệ thống, không được cấp quyền hay hủy quyền bất kỳ ai."""
        async def _run() -> None:
            engine = SmartHomeEngine()
            engine.set_active_user("khach_c")

            # Thử sửa quy tắc hệ thống
            pol_res = await engine.admin_update_system_policy("guest_allow_timers", True)
            assert pol_res.get("ok") is False
            assert "Chỉ Admin Cấp 1" in pol_res.get("error", "")

            # Thử cấp quyền người dùng khác
            grant_res = await engine.grant_user_permission("hacker_alias", tier=1)
            assert grant_res.get("ok") is False
            assert "không có quyền cấp quyền" in grant_res.get("error", "")

            # Thử hủy quyền Chủ nhà Cấp 1
            rev_res = await engine.revoke_user_permission("tuan_anh")
            assert rev_res.get("ok") is False
            assert "không có quyền hủy quyền" in rev_res.get("error", "")

        asyncio.run(_run())

    def test_genuine_guest_enrollment_with_expiration(self, client: TestClient) -> None:
        """Đăng ký giọng khách mới hợp lệ 2.8s (F0 ~ 235Hz):
        - Đạt chuẩn âm học -> Kích hoạt quyền Cấp 3.
        - Có trường expires_at tương ứng với thời hạn đã chọn (1w = 604800s).
        """
        guest_pcm = _create_synthetic_guest_pcm(duration_sec=2.8, f0=235.0)
        b64_pcm = base64.b64encode(guest_pcm).decode("utf-8")

        cur = client.get("/api/auth3/guest_qr_current?duration=1w").json()
        hs = client.post("/api/auth3/guest_qr_handshake", json={"token": cur["token"], "duration": "1w"}).json()
        sess_id = hs["session"]["session_id"]

        comp = client.post("/api/auth3/guest_qr_complete_voice", json={
            "session_id": sess_id,
            "guest_name": "Khách Đại Học Bách Khoa",
            "duration": "1w",
            "audio_pcm_b64": b64_pcm,
        })
        assert comp.status_code == 200
        data = comp.json()
        assert data["ok"] is True
        assert data["status"] == "DA_DAT"
        assert data["tier"] == 3
        assert data["duration_code"] == "1w"
        assert data["duration_seconds"] == 604800
        assert data["expires_at"] > time.time() + 600000.0
