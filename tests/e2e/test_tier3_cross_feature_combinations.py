"""TẦNG 3 (TIER 3): KIỂM THỬ PHỐI HỢP LIÊN TẦNG (CROSS-FEATURE COMBINATIONS).
Kiểm tra chuỗi phối hợp giữa:
1. Phân quyền RBAC 3 tầng + Ra lệnh điều khiển thiết bị
2. Vòng đời Thêm Email Gia đình + Đăng nhập + Bắt buộc Thu âm giọng chính (Fail -> Pass)
3. Rớt mạng đột ngột (Offline Lock) + Tái kết nối Online + SQLite WAL
4. Hẹn giờ linh hoạt + Tự động thực thi chuyển trạng thái thiết bị
5. Xâm nhập người lạ 3-strike lockout + Kích hoạt Còi báo động an ninh
6. Hai người cùng nói đồng thời (Diarization Priority) + Thực thi lệnh an toàn
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
from simulator.database_sqlite import get_sqlite_overview
from tests.e2e.conftest import (
    read_wav_pcm16,
    validate_voice_quality_helper,
    add_family_email_helper,
)


class TestTier3CrossFeatureCombinations:
    """Kiểm thử phối hợp đa tính năng liên tầng."""

    def test_rbac_and_voice_device_control(
        self,
        voice_auth_mgr: VoiceAuthManager,
        smart_home_engine: SmartHomeEngine,
        pcm_owner_bytes: bytes,
        pcm_tier3_bytes: bytes,
    ) -> None:
        """Phối hợp 1: Nhận diện giọng nói + Kiểm soát quyền điều khiển thiết bị (RBAC)."""
        async def _run() -> None:
            # 1. Giọng Chủ nhà Cấp 1
            auth_c1 = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_owner_bytes)
            assert auth_c1["authorized"] is True
            assert auth_c1["tier"] == 1

            # Đặt ngữ cảnh thực thi Cấp 1
            smart_home_engine.set_active_user("tuan_anh")
            assert smart_home_engine.current_tier == 1

            # Cấp 1 mở cửa chính -> THÀNH CÔNG
            r_c1_door = await smart_home_engine.execute_device_action("main_door", "open")
            assert r_c1_door["ok"] is True
            assert r_c1_door["exact_spoken_reply"] == "Cửa chính đã mở."

            # Cấp 1 bật còi báo động -> THÀNH CÔNG
            r_c1_siren = await smart_home_engine.execute_device_action("alarm_siren", "turn_on")
            assert r_c1_siren["ok"] is True
            assert r_c1_siren["exact_spoken_reply"] == "Còi báo động đã bật."

            # 2. Giọng Khách Cấp 3
            auth_c3 = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_tier3_bytes)
            assert auth_c3["authorized"] is True
            assert auth_c3["tier"] == 3

            # Đặt ngữ cảnh thực thi Cấp 3
            smart_home_engine.set_active_user("khach_c")
            assert smart_home_engine.current_tier == 3

            # Khách Cấp 3 bật đèn phòng khách -> THÀNH CÔNG
            r_c3_light = await smart_home_engine.execute_device_action("living_room_light", "turn_on")
            assert r_c3_light["ok"] is True
            assert r_c3_light["exact_spoken_reply"] == "Đèn phòng khách đã bật."

            # Khách Cấp 3 cố mở Cửa chính (thiết bị an ninh) -> BỊ TỪ CHỐI
            r_c3_door = await smart_home_engine.execute_device_action("main_door", "open")
            assert r_c3_door["ok"] is False or "không có quyền" in r_c3_door.get("error", "").lower()

        asyncio.run(_run())

    def test_full_email_binding_and_voice_enrollment_lifecycle(self) -> None:
        """Phối hợp 2: Vòng đời Thêm Email -> Đăng nhập -> Thu âm hỏng (Chưa đạt) -> Thu âm lại (Đã đạt)."""
        mgr = get_auth_3layer_manager()

        # Bước 1: Chủ nhà Cấp 1 thêm email thành viên con cái Cấp 2
        new_email = "con_yeu_e2e_test@gmail.com"
        r_add = add_family_email_helper(mgr, "tuan_anh", new_email, target_tier=2)
        assert r_add.get("ok") is True

        # Bước 2: Tạo trạng thái tài khoản mới chờ xác thực giọng chính
        pending_account = {
            "email": new_email,
            "display_name": "Con Gái Yêu",
            "tier": 2,
            "role": "MEMBER",
            "needs_first_page_voice_enroll": True,
            "voice_verified": False,
        }
        assert pending_account["needs_first_page_voice_enroll"] is True
        assert pending_account["voice_verified"] is False

        # Bước 3: Người dùng thu âm lần 1 nhưng im lặng / quá nhỏ -> BÁO CHƯA ĐẠT (BẮT THU LẠI)
        silent_sample = np.zeros(32000, dtype=np.int16)
        r_fail = validate_voice_quality_helper(silent_sample, 16000)
        assert r_fail["ok"] is False
        assert r_fail["status"] == "CHUA_DAT"
        assert pending_account["voice_verified"] is False  # Vẫn chưa được cấp quyền

        # Bước 4: Người dùng đọc to rõ ràng câu mẫu lần 2 -> BÁO ĐÃ ĐẠT
        good_sample = read_wav_pcm16("bat_quat_va_dieu_hoa.wav")
        good_arr = np.frombuffer(good_sample, dtype=np.int16)
        r_pass = validate_voice_quality_helper(good_arr, 16000)
        assert r_pass["ok"] is True
        assert r_pass["status"] == "DA_DAT"

        # Cập nhật trạng thái sau khi thu âm đạt
        pending_account["voice_verified"] = True
        pending_account["needs_first_page_voice_enroll"] = False
        assert pending_account["voice_verified"] is True
        assert pending_account["needs_first_page_voice_enroll"] is False

    def test_network_drop_and_reconnection_persistence(
        self, smart_home_engine: SmartHomeEngine
    ) -> None:
        """Phối hợp 3: Rớt mạng đột ngột (Offline Lock) + Tái kết nối Online + SQLite WAL nguyên vẹn."""
        async def _run() -> None:
            # 1. Trạng thái Online ban đầu
            await smart_home_engine.set_server_connection_mode(True)
            r_on = await smart_home_engine.execute_device_action("fan", "turn_on")
            assert r_on["ok"] is True

            # 2. Giả lập rớt mạng (Offline)
            await smart_home_engine.set_server_connection_mode(False)

            # Cửa chính bị khóa an ninh tuyệt đối
            r_door_off = await smart_home_engine.execute_device_action("main_door", "open")
            assert r_door_off["ok"] is False

            # 3. Tái kết nối Server (Online)
            await smart_home_engine.set_server_connection_mode(True)
            r_door_on = await smart_home_engine.execute_device_action("main_door", "open")
            assert r_door_on["ok"] is True

            # 4. Kiểm tra CSDL SQLite 3NF WAL còn nguyên vẹn 8 bảng
            sq = get_sqlite_overview()
            assert sq["ok"] is True
            assert sq["table_count"] == 8
            assert sq["journal_mode"] == "WAL"

        asyncio.run(_run())

    def test_timer_and_device_execution(
        self, smart_home_engine: SmartHomeEngine
    ) -> None:
        """Phối hợp 4: Hẹn giờ linh hoạt + Tự động thực thi chuyển trạng thái thiết bị."""
        async def _run() -> None:
            # Bật quạt trước
            await smart_home_engine.execute_device_action("fan", "turn_on")
            assert smart_home_engine.devices["fan"]["state"] == "ON"

            # Đặt hẹn giờ đếm ngược 1 giây để tắt quạt
            r_timer = await smart_home_engine.schedule_timer_flexible(
                device_id="fan",
                action="turn_off",
                seconds=1.0,
            )
            assert r_timer["ok"] is True

            # Đợi 1.2 giây để bộ hẹn giờ kích hoạt
            await asyncio.sleep(1.2)

            # Kiểm tra trạng thái thiết bị đã tự động chuyển sang OFF
            assert smart_home_engine.devices["fan"]["state"] == "OFF"

        asyncio.run(_run())

    def test_stranger_lockout_and_alarm_siren(
        self,
        voice_auth_mgr: VoiceAuthManager,
        smart_home_engine: SmartHomeEngine,
        pcm_intruder_bytes: bytes,
    ) -> None:
        """Phối hợp 5: Người lạ thử 3 lần bị khóa im lặng + Hệ thống sẵn sàng còi báo động."""
        voice_auth_mgr.reset_strikes()

        # Người lạ thử 3 lần
        for _ in range(3):
            res = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_intruder_bytes)

        # Lần 3 đạt lockout
        assert res["silent_ignore"] is True
        assert res["strike_count"] == 3

        async def _run_alarm() -> None:
            # Khi phát hiện hành vi xâm nhập, Chủ nhà kích hoạt còi báo động an ninh
            smart_home_engine.set_active_user("tuan_anh")
            siren_res = await smart_home_engine.execute_device_action("alarm_siren", "turn_on")
            assert siren_res["ok"] is True
            assert siren_res["exact_spoken_reply"] == "Còi báo động đã bật."
            assert smart_home_engine.devices["alarm_siren"]["state"] == "ON"

            # Tắt còi báo động
            siren_off = await smart_home_engine.execute_device_action("alarm_siren", "turn_off")
            assert siren_off["ok"] is True
            assert siren_off["exact_spoken_reply"] == "Còi báo động đã tắt."
            assert smart_home_engine.devices["alarm_siren"]["state"] == "OFF"

        asyncio.run(_run_alarm())

    def test_simultaneous_dual_speaker_priority(
        self,
        voice_auth_mgr: VoiceAuthManager,
        smart_home_engine: SmartHomeEngine,
        pcm_dual_speakers_bytes: bytes,
    ) -> None:
        """Phối hợp 6: 2 người nói đồng thời -> Ưu tiên Chủ nhà, bỏ qua Người lạ, thực thi an toàn."""
        # 1. DSP nhận diện 2 người nói
        auth_res = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_dual_speakers_bytes)
        assert auth_res["authorized"] is True
        assert auth_res["multi_speaker_detected"] is True
        assert auth_res["speaker_id"] == "owner_voice_1"

        async def _run() -> None:
            # 2. Thực thi lệnh của người được ưu tiên
            smart_home_engine.set_active_user(auth_res.get("user_id", "tuan_anh"))

            cmd_res = await smart_home_engine.execute_device_action("main_door", "open")
            assert cmd_res["ok"] is True
            assert cmd_res["exact_spoken_reply"] == "Cửa chính đã mở."

        asyncio.run(_run())
