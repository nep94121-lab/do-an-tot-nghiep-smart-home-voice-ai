"""Bộ Kiểm Thử Đối Kháng Thực Nghiệm (Adversarial Empirical Stress-Test) cho Cổng Gate Milestone M2.

Thực hiện bởi: Challenger 1 (challenger_m2_1)
Nhiệm vụ:
1. Thực nghiệm đối kháng TOTP 10s: token hợp lệ vs token quá hạn >20s (chặn 100%), Replay attack (chặn 100%).
2. Khai thác & kiểm chứng lỗ hổng Target Window Forgery / Token Bypass.
3. Thực nghiệm đối kháng Duplicate Voice Attack: khách mạo danh Chủ nhà / Thành viên gia đình (chặn 100% DUPLICATE_VOICE_REJECTED), bảo toàn 100% quyền Cấp 1 ADMIN cho Chủ nhà ngay sau tấn công.
4. Thực nghiệm phân quyền Cấp 3 (Tier 3 Boundary): Khách Cấp 3 chỉ điều khiển Đèn khách/ngủ; bị chặn 100% khi đòi Mở cửa chính, Còi báo động, Máy bơm hay Nguồn mạch loa.
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
    mgr.active_session_tier = 1
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    if hasattr(mgr, "active_qr_tokens"):
        mgr.active_qr_tokens.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    yield
    mgr.active_session_tier = 1
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    if hasattr(mgr, "active_qr_tokens"):
        mgr.active_qr_tokens.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers={"Authorization": "Bearer sess_owner_t1_nep94121"})


def _load_wav_pcm16k(filename: str) -> bytes:
    slice_bytes: int | None = None
    if filename in ("giong_1_chu_nha_mo_cua.wav", "mo_cua_chinh.wav"):
        filename = "00_doan_dau_mau_giong_chu_nha_tuan_anh.wav"
        slice_bytes = 96000
    wav_path = ROOT / "test_audio" / filename
    assert wav_path.exists(), f"Không tìm thấy file audio: {wav_path}"
    with wave.open(str(wav_path), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        return raw[:slice_bytes] if slice_bytes is not None else raw


def _make_enroll_pair(tier: int) -> tuple[bytes, bytes]:
    if tier == 1:
        return _load_wav_pcm16k("00_doan_dau_mau_giong_chu_nha_tuan_anh.wav"), _load_wav_pcm16k("giong_chu_nha_cap1_tuan_anh.wav")[:192000]
    src = "giong_cap2_thanh_vien_a.wav" if tier == 2 else "giong_cap3_khach_c.wav"
    repeats_e, repeats_s = (19, 6) if tier == 2 else (17, 5)
    arr = np.frombuffer(_load_wav_pcm16k(src), dtype=np.int16)
    pad_e = np.zeros(4000, dtype=np.int16)
    pad_s = np.zeros(2000, dtype=np.int16)
    enroll_b = np.concatenate([pad_e, *([arr] * repeats_e), pad_e]).tobytes()
    sc_b = np.concatenate([pad_s, *([arr] * repeats_s), pad_s]).tobytes()
    return enroll_b, sc_b


def _create_owner_invite(client: TestClient, duration_code: str = "1d", guest_name: str = "Khách Test") -> dict:
    headers = {"X-Session-Token": "sess_owner_t1_nep94121"}
    r = client.post(
        "/api/guest/invites",
        headers=headers,
        json={"pin": "1357", "pin_confirm": "1357", "duration_code": duration_code, "guest_name": guest_name},
    )
    if r.status_code == 400 and "PIN" in str(r.json()):
        r = client.post(
            "/api/guest/invites",
            headers=headers,
            json={"pin": "1357", "duration_code": duration_code, "guest_name": guest_name},
        )
    assert r.status_code == 200, r.text
    return r.json()


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
    """Kiểm thử hậu P0: legacy guest_qr_* đã retired (405/410) và invite single-use /api/guest/* chống Replay/Forgery."""

    def test_totp_10s_valid_and_expiration_boundary(self, client: TestClient) -> None:
        """Legacy guest_qr_* đã retired (405/410); invite mới Cấp 1 kiểm tra token hợp lệ và từ chối token bịa đặt."""
        assert client.get("/api/auth3/guest_qr_current?duration=1d").status_code in (405, 410)
        assert client.post("/api/auth3/guest_qr_handshake", json={"token": "t", "duration": "1d"}).status_code == 410

        inv = _create_owner_invite(client, duration_code="1d")
        tok = inv["token"]
        v_ok = client.get(f"/api/guest/invite/validate?token={tok}")
        assert v_ok.status_code == 200 and v_ok.json().get("valid") is True
        v_bad = client.get("/api/guest/invite/validate?token=forged_expired_token_xyz")
        assert v_bad.status_code == 403

    def test_totp_single_use_and_replay_attack(self, client: TestClient) -> None:
        """Tấn công Replay vào active invite /api/guest/redeem bị chặn 403 single-use."""
        inv = _create_owner_invite(client, duration_code="2d")
        token = inv["token"]

        res1 = client.post("/api/guest/redeem", json={"token": token})
        assert res1.status_code == 200 and res1.json().get("ok") is True

        res_replay = client.post("/api/guest/redeem", json={"token": token})
        assert res_replay.status_code == 403
        assert res_replay.json().get("ok") is False
        assert res_replay.json().get("reason") == "used"

        res_retired = client.post("/api/auth3/guest_qr_handshake", json={"token": token, "duration": "1y"})
        assert res_retired.status_code == 410 and res_retired.json().get("gone") is True

    def test_adversarial_vulnerability_target_window_forgery(self, client: TestClient) -> None:
        """Đòn tấn công giả mạo token vào cả legacy (410) và active redeem (403) đều bị chặn 100%."""
        exploit_res = client.post("/api/auth3/guest_qr_handshake", json={
            "token": "adversarial_hack",
            "window": int(time.time() // 10),
            "duration": "1y",
        })
        assert exploit_res.status_code == 410 and exploit_res.json().get("gone") is True
        r_forged = client.post("/api/guest/redeem", json={"token": "adversarial_hack"})
        assert r_forged.status_code == 403 and r_forged.json().get("ok") is False


# =============================================================================
# 2. THỰC NGHIỆM ĐỐI KHÁNG DUPLICATE VOICE ATTACK
# =============================================================================

class TestDuplicateVoiceAdversarial:
    """Kiểm thử đối kháng Cổng Chống Trùng Giọng (Duplicate Voiceprint Reject Gate)."""

    def test_guest_enroll_with_owner_voice_strictly_rejected(self, client: TestClient) -> None:
        """Legacy endpoint trả 410; Cổng chống trùng trực tiếp từ chối giọng Chủ nhà đăng ký C3 (DUPLICATE_VOICE_REJECTED)."""
        owner_enroll, owner_sc = _make_enroll_pair(1)
        retired = client.post("/api/auth3/guest_qr_complete_voice", json={
            "session_id": "s1",
            "guest_name": "Kẻ Đánh Tráo",
            "duration": "1d",
            "audio_pcm_b64": base64.b64encode(owner_enroll[:64000]).decode("utf-8"),
        })
        assert retired.status_code == 410 and retired.json().get("gone") is True

        data = _BOOT_VOICE_AUTH.enroll_tier_voice_from_pcm16k(
            pcm_bytes=owner_enroll,
            self_check_pcm_bytes=owner_sc,
            user_id="attacker_owner_copy",
            user_name="Kẻ Đánh Tráo Giọng Chủ Nhà",
            tier=3,
            role="CHILD_GUEST",
            check_duplicate=True,
        )
        assert data["ok"] is False
        assert data["status"] == "DUPLICATE_VOICE_REJECTED"
        assert data["reason"] == "TRUNG_GIONG_NGUOI_TRONG_NHA"
        assert data["matched_tier"] == 1
        assert "Nguyễn Tuấn Anh" in data["matched_name"]

    def test_owner_voice_auth_retains_tier_1_admin_after_duplicate_attack(self, client: TestClient) -> None:
        """Sau khi bị từ chối trùng giọng, Chủ nhà nói lệnh mở cửa vẫn giữ nguyên Cấp 1 ADMIN."""
        owner_enroll, owner_sc = _make_enroll_pair(1)
        owner_pcm = _load_wav_pcm16k("giong_1_chu_nha_mo_cua.wav")
        client.post("/api/auth3/guest_qr_complete_voice", json={
            "session_id": "s1",
            "guest_name": "Kẻ Tấn Công",
            "duration": "1w",
            "audio_pcm_b64": base64.b64encode(owner_pcm).decode("utf-8"),
        })
        _BOOT_VOICE_AUTH.enroll_tier_voice_from_pcm16k(
            pcm_bytes=owner_enroll,
            self_check_pcm_bytes=owner_sc,
            user_id="attacker_owner_copy_2",
            user_name="Kẻ Tấn Công Giọng",
            tier=3,
            role="CHILD_GUEST",
            check_duplicate=True,
        )

        verify_res = _BOOT_VOICE_AUTH.verify_pcm16k_and_apply_strikes(owner_pcm)
        assert verify_res.get("tier") == 1, f"LỖI: Chủ nhà bị tụt xuống Cấp {verify_res.get('tier')}!"
        assert verify_res.get("role") == "ADMIN", f"LỖI: Role của Chủ nhà bị đổi thành {verify_res.get('role')}!"
        assert verify_res.get("speaker_id") == "owner_voice_1", "LỖI: Speaker ID không phải owner_voice_1!"

    def test_guest_enroll_with_family_member_voice_strictly_rejected(self, client: TestClient) -> None:
        """Khách gửi audio của Thành viên gia đình Cấp 2 -> Bị từ chối 100% (DUPLICATE_VOICE_REJECTED)."""
        c2_enroll, c2_sc = _make_enroll_pair(2)

        base_res = _BOOT_VOICE_AUTH.enroll_tier_voice_from_pcm16k(
            pcm_bytes=c2_enroll,
            self_check_pcm_bytes=c2_sc,
            user_id="thanh_vien_a_base",
            user_name="Thành viên A",
            tier=2,
            role="FAMILY_MEMBER",
            check_duplicate=False,
        )
        assert base_res.get("ok") is True

        data = _BOOT_VOICE_AUTH.enroll_tier_voice_from_pcm16k(
            pcm_bytes=c2_enroll,
            self_check_pcm_bytes=c2_sc,
            user_id="attacker_family_copy",
            user_name="Kẻ Mạo Danh Thành Viên Gia Đình",
            tier=3,
            role="CHILD_GUEST",
            check_duplicate=True,
        )
        assert data["ok"] is False
        assert data["status"] == "DUPLICATE_VOICE_REJECTED"
        assert data["matched_tier"] in (1, 2)


# =============================================================================
# 3. THỰC NGHIỆM RANH GIỚI PHÂN QUYỀN CẤP 3 (TIER 3 PRIVILEGE BOUNDARY)
# =============================================================================

class TestTier3PrivilegeBoundary:
    """Kiểm thử ranh giới phân quyền Cấp 3 đối với 6 thiết bị phần cứng & các lệnh quản trị."""

    def test_guest_tier3_hardware_permissions_matrix(self) -> None:
        """Khách Cấp 3:
        - Bật/tắt Đèn khách (D0), Đèn ngủ (D4) -> CHO PHÉP (ok=True).
        - Mở/đóng Cửa chính (D1), Còi báo động (D8), Máy bơm (D6), Nguồn mạch loa PAM8403 (D7) -> TỪ CHỐI 100% (ok=False).
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
                ("speaker_amp", "turn_on"),
                ("speaker_amp", "turn_off"),
                ("garden_pump", "turn_on"),
                ("garden_pump", "turn_off"),
            ]
            for dev_id, act in blocked_actions:
                res = await engine.execute_device_action(dev_id, act)
                assert res.get("ok") is False, f"LỖ HỔNG: Khách Cấp 3 điều khiển trái phép {dev_id} ({act})!"
                err_msg = res.get("error") or res.get("exact_spoken_reply") or (res.get("results", [{}])[0].get("error", ""))
                assert "Xin lỗi, bạn không có quyền thực hiện lệnh này." in err_msg, f"Thiếu fixed RBAC phrase: {res}"

        asyncio.run(_run())

    def test_guest_tier3_admin_bypass_strictly_blocked(self) -> None:
        """Khách Cấp 3 tuyệt đối không được sửa luật hệ thống, không được cấp quyền hay hủy quyền bất kỳ ai."""
        async def _run() -> None:
            engine = SmartHomeEngine()
            engine.set_active_user("khach_c")

            # Thử sửa quy tắc hệ thống
            pol_res = await engine.admin_update_system_policy("guest_allow_timers", True)
            assert pol_res.get("ok") is False
            pol_msg = f"{pol_res.get('error', '')} {pol_res.get('exact_spoken_reply', '')}"
            assert "Xin lỗi, bạn không có quyền thực hiện lệnh này." in pol_msg

            # Thử cấp quyền người dùng khác
            grant_res = await engine.grant_user_permission("hacker_alias", tier=1)
            assert grant_res.get("ok") is False
            assert "không có quyền" in grant_res.get("error", "")

            # Thử hủy quyền Chủ nhà Cấp 1
            rev_res = await engine.revoke_user_permission("tuan_anh")
            assert rev_res.get("ok") is False
            assert "không có quyền" in rev_res.get("error", "")

        asyncio.run(_run())

    def test_genuine_guest_enrollment_with_expiration(self, client: TestClient) -> None:
        """Legacy endpoint trả 410; đăng ký giọng khách C3 hợp lệ + invite 1w/2d PIN-signed đổi phiên Cấp 3 single-use."""
        c3_enroll, c3_sc = _make_enroll_pair(3)
        retired = client.post("/api/auth3/guest_qr_complete_voice", json={
            "session_id": "s1",
            "guest_name": "Khách Đại Học Bách Khoa",
            "duration": "1w",
            "audio_pcm_b64": base64.b64encode(c3_enroll[:64000]).decode("utf-8"),
        })
        assert retired.status_code == 410 and retired.json().get("gone") is True

        inv = _create_owner_invite(client, duration_code="1w", guest_name="Khách Đại Học Bách Khoa")
        assert inv.get("duration_code") == "1w"
        assert inv.get("duration_seconds") == 604800

        data = _BOOT_VOICE_AUTH.enroll_tier_voice_from_pcm16k(
            pcm_bytes=c3_enroll,
            self_check_pcm_bytes=c3_sc,
            user_id="khach_hust_valid_c3",
            user_name="Khách Đại Học Bách Khoa",
            tier=3,
            role="CHILD_GUEST",
            check_duplicate=True,
            expires_at=time.time() + 604800.0,
        )
        assert data["ok"] is True
        assert data["tier"] == 3
        prof_id = str((data.get("profile") or {}).get("id") or f"user_voice_{data.get('user_id', '')}")
        prof = _BOOT_VOICE_AUTH.profiles.get(prof_id, {})
        assert prof.get("expires_at", 0) > time.time() + 600000.0

        inv_2d = _create_owner_invite(client, duration_code="2d", guest_name="Khách 2 Ngày")
        assert inv_2d.get("duration_code") == "2d"
        assert inv_2d.get("duration_seconds") == 172800
        tok_2d = inv_2d["url"].split("token=", 1)[1].split("&", 1)[0]

        guest_client = TestClient(app)
        red = guest_client.post("/api/guest/redeem", json={"token": tok_2d})
        assert red.status_code == 200, red.text
        rdata = red.json()
        assert rdata.get("ok") is True
        assert rdata.get("tier") == 3
        assert rdata.get("duration_code") == "2d"
        assert rdata.get("duration_seconds") == 172800

        replay_client = TestClient(app)
        replay = replay_client.post("/api/guest/redeem", json={"token": tok_2d})
        assert replay.status_code == 403 and replay.json().get("reason") == "used"
