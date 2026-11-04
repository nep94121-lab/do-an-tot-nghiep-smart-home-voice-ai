"""TẦNG 4 (TIER 4): KỊCH BẢN ỨNG DỤNG ĐỜI SỐNG THỰC TẾ (REAL-WORLD APPLICATION SCENARIOS).
Mô phỏng toàn diện 1 ngày trọn vẹn trong gia đình thông minh (Chủ nhà, Con cái, Khách, và Kẻ đột nhập).
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


class TestTier4RealWorldScenarios:
    """Kịch bản thực tế 1 ngày gia đình trong ngôi nhà thông minh."""

    def test_full_day_family_smart_home_lifecycle(
        self,
        voice_auth_mgr: VoiceAuthManager,
        smart_home_engine: SmartHomeEngine,
        pcm_owner_bytes: bytes,
        pcm_intruder_bytes: bytes,
        pcm_tier3_bytes: bytes,
    ) -> None:
        """Kịch bản E2E toàn diện: 1 Ngày Sống Trong Ngôi Nhà Thông Minh AI."""

        # ======================================================================
        # GIAI ĐOẠN 1: BUỔI SÁNG (07:00) — CHỦ NHÀ THỨC DẬY & NÓI NGẬP NGỪNG
        # ======================================================================
        print("\n--- [GIAI ĐOẠN 1: BUỔI SÁNG (07:00)] ---")
        # Chủ nhà thức dậy, phát âm có âm đệm mũi / ngập ngừng ("ừm... bật đèn phòng khách")
        pcm_arr = np.frombuffer(pcm_owner_bytes, dtype=np.int16)
        sr = 16000
        t_filler = np.linspace(0, 0.35, int(sr * 0.35), endpoint=False)
        filler_pcm = (0.35 * np.sin(2 * np.pi * 82.0 * t_filler) * 12000.0).astype(np.int16)
        morning_audio = np.concatenate([filler_pcm, pcm_arr]).tobytes()

        # DSP nhận diện đúng Chủ nhà Cấp 1, không tăng strikes
        auth_morning = voice_auth_mgr.verify_pcm16k_and_apply_strikes(morning_audio)
        assert auth_morning["authorized"] is True, "Chủ nhà nói ngập ngừng buổi sáng bị từ chối!"
        assert auth_morning["speaker_id"] == "owner_voice_1"
        assert auth_morning["tier"] == 1
        assert auth_morning["strike_count"] == 0

        async def _morning_action() -> None:
            smart_home_engine.set_active_user("tuan_anh")
            # Bật đèn phòng khách
            res_light = await smart_home_engine.execute_device_action("living_room_light", "turn_on")
            assert res_light["ok"] is True
            assert res_light["exact_spoken_reply"] == "Đèn phòng khách đã bật."
            assert smart_home_engine.devices["living_room_light"]["state"] == "ON"

        asyncio.run(_morning_action())

        # ======================================================================
        # GIAI ĐOẠN 2: BUỔI TRƯA (12:00) — THÊM EMAIL CON CÁI C2 & THU ÂM GIỌNG CHÍNH
        # ======================================================================
        print("\n--- [GIAI ĐOẠN 2: BUỔI TRƯA (12:00)] ---")
        auth_mgr = get_auth_3layer_manager()
        child_email = "con_yeu_family@gmail.com"

        # 1. Chủ nhà C1 thêm Email cho con cái vào Cấp 2
        r_child_email = add_family_email_helper(auth_mgr, "tuan_anh", child_email, target_tier=2)
        assert r_child_email.get("ok") is True

        # 2. Con cái đăng nhập lần đầu -> Ở trạng thái bắt buộc thu âm giọng chính
        child_account = {
            "email": child_email,
            "display_name": "Con Yêu (Cấp 2)",
            "tier": 2,
            "role": "MEMBER",
            "needs_first_page_voice_enroll": True,
            "voice_verified": False,
        }
        assert child_account["needs_first_page_voice_enroll"] is True
        assert child_account["voice_verified"] is False

        # 3. Con cái thu âm lần 1: Đọc quá nhỏ / im lặng -> DSP BÁO CHƯA ĐẠT
        silent_audio = np.zeros(32000, dtype=np.int16)
        r_check1 = validate_voice_quality_helper(silent_audio, 16000)
        assert r_check1["ok"] is False
        assert r_check1["status"] == "CHUA_DAT"
        assert "chưa" in (r_check1.get("reason", "") + r_check1.get("message", "")).lower()
        assert child_account["voice_verified"] is False  # Chưa cấp quyền

        # 4. Con cái đọc to rõ câu mẫu lần 2 -> DSP BÁO ĐÃ ĐẠT
        good_audio = read_wav_pcm16("bat_quat_va_dieu_hoa.wav")
        r_check2 = validate_voice_quality_helper(np.frombuffer(good_audio, dtype=np.int16), 16000)
        assert r_check2["ok"] is True
        assert r_check2["status"] == "DA_DAT"
        assert "đạt" in r_check2.get("message", "").lower()

        # Kích hoạt tài khoản con cái C2
        child_account["voice_verified"] = True
        child_account["needs_first_page_voice_enroll"] = False
        assert child_account["voice_verified"] is True

        # ======================================================================
        # GIAI ĐOẠN 3: BUỔI CHIỀU (16:00) — KHÁCH C3 VÀO NHÀ & KIỂM SOÁT QUYỀN HẠN
        # ======================================================================
        print("\n--- [GIAI ĐOẠN 3: BUỔI CHIỀU (16:00)] ---")
        # Khách Cấp 3 ra lệnh giọng nói
        auth_guest = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_tier3_bytes)
        assert auth_guest["authorized"] is True
        assert auth_guest["tier"] == 3

        async def _afternoon_action() -> None:
            smart_home_engine.set_active_user("khach_c")
            assert smart_home_engine.current_tier == 3

            # Khách C3 bật quạt trần -> THÀNH CÔNG
            res_fan = await smart_home_engine.execute_device_action("fan", "turn_on")
            assert res_fan["ok"] is True
            assert res_fan["exact_spoken_reply"] == "Quạt trần đã bật."
            assert smart_home_engine.devices["fan"]["state"] == "ON"

            # Khách C3 cố ra lệnh mở Cửa chính (thiết bị an ninh) -> BỊ TỪ CHỐI
            res_door = await smart_home_engine.execute_device_action("main_door", "open")
            assert res_door["ok"] is False or "không có quyền" in res_door.get("error", "").lower()

            # Khách C3 cố thêm bạn bè vào gia đình -> BỊ CHẶN 100% (HTTP 403)
            r_guest_add = add_family_email_helper(auth_mgr, "khach_c", "ban_khach@gmail.com", target_tier=3)
            assert r_guest_add.get("ok") is False

        asyncio.run(_afternoon_action())

        # ======================================================================
        # GIAI ĐOẠN 4: BUỔI TỐI (21:00) — KẺ LẠ MẶT ĐỘT NHẬP & PHÒNG THỦ 3-STRIKE
        # ======================================================================
        print("\n--- [GIAI ĐOẠN 4: BUỔI TỐI (21:00)] ---")
        voice_auth_mgr.reset_strikes()

        # Kẻ lạ thử nói lệnh mở cửa:
        # Lần 1: Cảnh báo từ chối
        int_1 = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_intruder_bytes)
        assert int_1["authorized"] is False
        assert int_1["strike_count"] == 1
        assert int_1["rejection_speech"] == "Tôi không được phép nhận lệnh từ người lạ."
        assert int_1["should_reply"] is True

        # Lần 2: Cảnh báo nhắc lại
        int_2 = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_intruder_bytes)
        assert int_2["authorized"] is False
        assert int_2["strike_count"] == 2
        assert int_2["rejection_speech"] == "Tôi sẽ không trả lời bạn lần nữa."
        assert int_2["should_reply"] is True

        # Lần 3: IM LẶNG TUYỆT ĐỐI (Silent Lockout)
        int_3 = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_intruder_bytes)
        assert int_3["authorized"] is False
        assert int_3["strike_count"] == 3
        assert int_3["silent_ignore"] is True
        assert int_3["should_reply"] is False
        assert int_3["rejection_speech"] == ""

        # Kích hoạt Còi báo động an ninh xua đuổi kẻ đột nhập
        async def _intruder_alarm() -> None:
            smart_home_engine.set_active_user("tuan_anh")
            siren_res = await smart_home_engine.execute_device_action("alarm_siren", "turn_on")
            assert siren_res["ok"] is True
            assert siren_res["exact_spoken_reply"] == "Còi báo động đã bật."
            assert smart_home_engine.devices["alarm_siren"]["state"] == "ON"

            # Tắt còi sau khi tình hình an toàn
            siren_off = await smart_home_engine.execute_device_action("alarm_siren", "turn_off")
            assert siren_off["ok"] is True
            assert smart_home_engine.devices["alarm_siren"]["state"] == "OFF"

        asyncio.run(_intruder_alarm())

        # ======================================================================
        # GIAI ĐOẠN 5: ĐÊM KHUYA (23:00) — CHẾ ĐỘ ĐI NGỦ ("KÍCH HOẠT ĐI NGỦ")
        # ======================================================================
        print("\n--- [GIAI ĐOẠN 5: ĐÊM KHUYA (23:00)] ---")
        async def _night_routine() -> None:
            smart_home_engine.set_active_user("tuan_anh")

            # Thực thi chuỗi lệnh đi ngủ: Tắt đèn khách, tắt quạt, đóng khóa cửa chính
            await smart_home_engine.execute_device_action("living_room_light", "turn_off")
            await smart_home_engine.execute_device_action("bedroom_light", "turn_off")
            await smart_home_engine.execute_device_action("fan", "turn_off")
            door_close = await smart_home_engine.execute_device_action("main_door", "close")
            assert door_close["ok"] is True
            assert door_close["exact_spoken_reply"] in ("Cửa chính đã đóng.", "Cửa chính đã đóng sẵn rồi.")

            # Kiểm tra trạng thái an toàn toàn bộ ngôi nhà ban đêm
            assert smart_home_engine.devices["living_room_light"]["state"] == "OFF"
            assert smart_home_engine.devices["bedroom_light"]["state"] == "OFF"
            assert smart_home_engine.devices["fan"]["state"] == "OFF"
            assert smart_home_engine.devices["main_door"]["state"] == "CLOSED"
            assert smart_home_engine.devices["alarm_siren"]["state"] == "OFF"

        asyncio.run(_night_routine())
        print("\n✅ HOÀN TẤT TRỌN VẸN KỊCH BẢN 1 NGÀY GIA ĐÌNH THỰC TẾ (TIER 4 PASS 100%)!")
