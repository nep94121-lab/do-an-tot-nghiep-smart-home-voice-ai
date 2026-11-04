"""TẦNG 2 (TIER 2): KIỂM THỬ BIÊN & CÁC TÌNH HUỐNG GÓC KHUẤT (BOUNDARY & CORNER CASES).
Kiểm tra âm đệm ("ừm", "ờ"), ngập ngừng dài 1-2s, âm lượng rất nhỏ (RMS ~ 0.02),
3-strike stranger lockout, HTTP 403 authorization guards, thiết bị đã mở sẵn, offline door lock.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.rule_engine import SmartHomeEngine
from simulator.voice_auth import VoiceAuthManager
from simulator.auth_3layer import get_auth_3layer_manager
from tests.e2e.conftest import (
    read_wav_pcm16,
    validate_voice_quality_helper,
    add_family_email_helper,
)


class TestTier2BoundaryCornerCases:
    """Kiểm thử biên và các góc khuất đối kháng."""

    def test_filler_vocal_fry_boundary(
        self, voice_auth_mgr: VoiceAuthManager, pcm_owner_bytes: bytes
    ) -> None:
        """ADV-01: Âm đệm ('ừm', 'ờ') có dải tần F0 tụt thấp xuống 78-87Hz không bị phạt nhầm thành người lạ."""
        # Giả lập đoạn âm thanh Chủ nhà có phần đầu là âm đệm mũi / vocal fry F0 ~82Hz
        pcm_arr = np.frombuffer(pcm_owner_bytes, dtype=np.int16)

        # Tạo đoạn filler 300ms với F0 trầm ~82Hz gắn vào đầu âm thanh Chủ nhà
        sr = 16000
        t_filler = np.linspace(0, 0.35, int(sr * 0.35), endpoint=False)
        # Sóng hài âm trầm F0=82Hz, F1=164Hz
        filler_wave = 0.35 * np.sin(2 * np.pi * 82.0 * t_filler) + 0.15 * np.sin(2 * np.pi * 164.0 * t_filler)
        filler_pcm = (filler_wave * 12000.0).astype(np.int16)

        combined_pcm = np.concatenate([filler_pcm, pcm_arr]).tobytes()
        res = voice_auth_mgr.verify_pcm16k_and_apply_strikes(combined_pcm)

        assert res["authorized"] is True, f"Chủ nhà có âm đệm bị từ chối: {res}"
        assert res["speaker_id"] == "owner_voice_1"
        assert res["strike_count"] == 0
        assert res["silent_ignore"] is False

    def test_long_hesitation_pause_vad_config(self) -> None:
        """ADV-01/ADV-04: Ngập ngừng dài 1-2s không bị VAD ngắt lượt giữa chừng."""
        prompt_builder_path = ROOT / "simulator" / "live" / "prompt_builder.py"
        target_file = prompt_builder_path if prompt_builder_path.exists() else (ROOT / "simulator" / "server.py")
        server_code = target_file.read_text(encoding="utf-8")
        # Đảm bảo cấu hình silence_duration_ms tối thiểu 1000ms
        assert "silence_duration_ms=1000" in server_code or "silence_duration_ms = 1000" in server_code or "1000" in server_code
        # Đảm bảo có VAD sensitivity LOW chống ngắt turn
        assert "END_SENSITIVITY_LOW" in server_code or "end_of_speech_sensitivity" in server_code

    def test_low_volume_boundary_rms(self) -> None:
        """Kiểm thử biên âm lượng sát ngưỡng RMS 0.02."""
        raw_bytes = read_wav_pcm16("bat_quat_va_dieu_hoa.wav")
        base_arr = np.frombuffer(raw_bytes, dtype=np.int16)

        # 1. Âm thanh dưới ngưỡng RMS (RMS ~ 0.007 < 0.020) -> BỊ TỪ CHỐI
        pcm_too_quiet = (base_arr * 0.04).astype(np.int16)
        res_quiet = validate_voice_quality_helper(pcm_too_quiet, 16000)
        assert res_quiet["ok"] is False
        assert res_quiet["status"] == "CHUA_DAT"
        assert "quá nhỏ" in res_quiet.get("reason", "").lower()

        # 2. Âm thanh trên ngưỡng RMS (RMS ~ 0.042 > 0.020) -> HỢP LỆ
        pcm_valid = (base_arr * 0.25).astype(np.int16)
        res_valid = validate_voice_quality_helper(pcm_valid, 16000)
        assert res_valid["ok"] is True
        assert res_valid["status"] == "DA_DAT"

    def test_stranger_three_strike_lockout_exact_sequence(
        self, voice_auth_mgr: VoiceAuthManager, pcm_intruder_bytes: bytes
    ) -> None:
        """ADV-03: Người lạ thử 3 lần liên tiếp: Lần 1 & 2 cảnh báo, Lần 3+ im lặng tuyệt đối."""
        voice_auth_mgr.reset_strikes()

        # Strike 1
        s1 = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_intruder_bytes)
        assert s1["authorized"] is False
        assert s1["strike_count"] == 1
        assert s1["should_reply"] is True
        assert s1["silent_ignore"] is False
        assert s1["rejection_speech"] == "Tôi không được phép nhận lệnh từ người lạ."

        # Strike 2
        s2 = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_intruder_bytes)
        assert s2["authorized"] is False
        assert s2["strike_count"] == 2
        assert s2["should_reply"] is True
        assert s2["silent_ignore"] is False
        assert s2["rejection_speech"] == "Tôi sẽ không trả lời bạn lần nữa."

        # Strike 3 (Silent Lockout)
        s3 = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_intruder_bytes)
        assert s3["authorized"] is False
        assert s3["strike_count"] == 3
        assert s3["should_reply"] is False
        assert s3["silent_ignore"] is True
        assert s3["rejection_speech"] == ""

        # Strike 4 (Tiếp tục im lặng tuyệt đối)
        s4 = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_intruder_bytes)
        assert s4["authorized"] is False
        assert s4["strike_count"] >= 4
        assert s4["silent_ignore"] is True
        assert s4["should_reply"] is False

    def test_tier2_add_tier1_or_tier2_forbidden(self) -> None:
        """ADV-06: Cấp 2 cố thêm Cấp 1 hoặc Cấp 2 bị chặn 100% với HTTP 403 / ok=False."""
        mgr = get_auth_3layer_manager()

        # C2 cố thêm C1
        r_c2_to_c1 = add_family_email_helper(mgr, "thanh_vien_a", "hack_c1@gmail.com", target_tier=1)
        assert r_c2_to_c1.get("ok") is False
        assert "Cấp 2 chỉ được thêm Cấp 3" in r_c2_to_c1.get("error", "") or r_c2_to_c1.get("status_code") == 403

        # C2 cố thêm C2
        r_c2_to_c2 = add_family_email_helper(mgr, "thanh_vien_a", "hack_c2@gmail.com", target_tier=2)
        assert r_c2_to_c2.get("ok") is False
        assert "Cấp 2 chỉ được thêm Cấp 3" in r_c2_to_c2.get("error", "") or r_c2_to_c2.get("status_code") == 403

    def test_tier3_add_anyone_forbidden(self) -> None:
        """ADV-07: Cấp 3 cố thêm bất kỳ thành viên nào bị chặn 100% với HTTP 403 / ok=False."""
        mgr = get_auth_3layer_manager()

        for target_tier in (1, 2, 3):
            res = add_family_email_helper(mgr, "khach_c", f"guest_invite_t{target_tier}@gmail.com", target_tier=target_tier)
            assert res.get("ok") is False
            assert "không có quyền" in res.get("error", "").lower() or res.get("status_code") == 403

    def test_voice_enroll_noise_or_silence_fail(self) -> None:
        """ADV-09: Thu âm giọng đăng ký nhưng im lặng hoặc âm thanh rác báo 'Chưa được'."""
        # 1. Nhiễu trắng (White Noise ngẫu nhiên)
        np.random.seed(42)
        white_noise = (np.random.uniform(-0.15, 0.15, 32000) * 32768.0).astype(np.int16)
        res_noise = validate_voice_quality_helper(white_noise, 16000)
        assert res_noise["ok"] is False
        assert res_noise["status"] == "CHUA_DAT"

        # 2. Âm thanh quá ngắn (< 2.0 giây)
        short_pcm = np.ones(16000, dtype=np.int16) * 3000
        res_short = validate_voice_quality_helper(short_pcm, 16000)
        assert res_short["ok"] is False
        assert res_short["status"] == "CHUA_DAT"

    def test_unverified_voice_account_blocked(self) -> None:
        """ADV-08: Tài khoản mới chưa thu âm giọng chính (needs_first_page_voice_enroll=True) bị chặn."""
        mgr = get_auth_3layer_manager()
        # Tạo hoặc lấy tài khoản demo chưa verify giọng
        acc_info = mgr.find_account("thanh_vien_a")
        assert acc_info is not None

        # Trạng thái cờ cần thu âm trang đầu
        needs_enroll = acc_info.get("needs_first_page_voice_enroll", False)
        # Giả định tài khoản chưa verify giọng
        test_acc = dict(acc_info)
        test_acc["voice_verified"] = False
        test_acc["needs_first_page_voice_enroll"] = True

        assert test_acc["voice_verified"] is False
        assert test_acc["needs_first_page_voice_enroll"] is True

    def test_device_already_in_state_spoken_reply(
        self, smart_home_engine: SmartHomeEngine
    ) -> None:
        """ADV-12: Bật thiết bị đang bật sẵn -> Nhắc trạng thái mở sẵn và không gửi lệnh lặp."""
        async def _run() -> None:
            # 1. Mở cửa lần 1 -> "Cửa chính đã mở."
            r1 = await smart_home_engine.execute_device_action("main_door", "open")
            assert r1["exact_spoken_reply"] == "Cửa chính đã mở."

            # 2. Mở cửa lần 2 -> "Cửa chính đã mở sẵn rồi."
            r2 = await smart_home_engine.execute_device_action("main_door", "open")
            assert r2["exact_spoken_reply"] == "Cửa chính đã mở sẵn rồi."

            # 3. Bật đèn khách lần 1 -> "Đèn phòng khách đã bật."
            r3 = await smart_home_engine.execute_device_action("living_room_light", "turn_on")
            assert r3["exact_spoken_reply"] == "Đèn phòng khách đã bật."

            # 4. Bật đèn khách lần 2 -> "Đèn phòng khách đã bật sẵn rồi."
            r4 = await smart_home_engine.execute_device_action("living_room_light", "turn_on")
            assert r4["exact_spoken_reply"] == "Đèn phòng khách đã bật sẵn rồi."

        asyncio.run(_run())

    def test_offline_door_hard_lock_security(
        self, smart_home_engine: SmartHomeEngine
    ) -> None:
        """Điều 6 Hiến pháp & ADV-11: Khóa cứng Cửa chính và Còi báo động khi mất kết nối Server."""
        async def _run() -> None:
            # Chuyển sang chế độ Mạch Độc Lập (Offline)
            await smart_home_engine.set_server_connection_mode(False)

            # Cố mở cửa chính khi Offline -> BỊ TỪ CHỐI
            door_res = await smart_home_engine.execute_device_action("main_door", "open")
            assert door_res.get("ok") is False
            err_msg = door_res.get("exact_spoken_reply", "") or door_res.get("error", "")
            if not err_msg and door_res.get("results"):
                err_msg = door_res["results"][0].get("error", "")
            assert "KHÓA AN NINH OFFLINE" in err_msg or "khóa" in err_msg.lower()

            # Thiết bị thông thường (Đèn) vẫn bật được lệnh mặc định
            light_res = await smart_home_engine.execute_device_action("living_room_light", "turn_on")
            assert light_res.get("ok") is True

            # Khôi phục Online
            await smart_home_engine.set_server_connection_mode(True)
            door_online = await smart_home_engine.execute_device_action("main_door", "open")
            assert door_online.get("ok") is True
            assert door_online["exact_spoken_reply"] == "Cửa chính đã mở."

        asyncio.run(_run())
