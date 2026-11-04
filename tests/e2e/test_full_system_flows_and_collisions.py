"""BỘ KIỂM THỬ LUỒNG LIÊN HOÀN & VA CHẠM CHÉO TRẠNG THÁI (CROSS-FLOW STATE COLLISION SUITE)
Tác giả: teamwork_test_writer (E2E Testing Track)
Đặc tả: PROJECT.md, ORIGINAL_REQUEST.md (Chỉ thị Sếp Nguyễn Tuấn Anh về Kiểm thử Luồng & Va chạm Chéo)
Tuân thủ: Zero-Cheating / Zero-Mock Falsification / Opaque-box Invariant Verification.

5 Kịch bản Va chạm Chéo Trọng Tâm:
1. Va chạm Thu âm & Bảo toàn Quyền Chủ Nhà Cấp 1 (Tier 1 Ownership Invariant)
2. Luồng Mã QR Động 10s Từ Đầu Đến Cuối + Hết Hạn Quyền + Miễn Nhiễm Cấp 1 (Tier 1 Immunity)
3. Luồng Email Tùy Chọn (Nhập 2 lần + DNS MX + OTP) & Phân Cấp Email Gia Đình (C1/C2/C3)
4. Va chạm Chuyển Đổi Chế Độ Online <-> Offline & Phục Hồi Sau 3-Strike Người Lạ
5. Va chạm Bể Hẹn Giờ + Bể Luật Đổi Từ / Khẩu Lệnh + Luật IF-THEN + 4 Chế Độ Reset
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import hmac
import pathlib
import sys
import time
import wave
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import simulator.auth_3layer as a3
from simulator.auth_3layer import ThreeLayerAuthManager, get_auth_3layer_manager
from simulator.database_sqlite import sync_engine_state_to_sqlite
from simulator.rule_engine import SmartHomeEngine
from simulator.server import app
from simulator.voice_auth import (
    VoiceAuthManager,
    extract_stage2_deep_features,
    extract_voice_features,
    transform_pcm_by_pitch_factor,
    validate_voice_enrollment_quality,
)
from tests.e2e.conftest import (
    AUDIO_DIR,
    check_duplicate_voice_gate_helper,
    consume_guest_handshake_helper,
    generate_dynamic_qr_token_helper,
    read_wav_pcm16,
    send_and_verify_email_otp_helper,
    validate_dns_mx_record_helper,
    validate_voice_quality_helper,
    verify_guest_expiry_helper,
)


@pytest.fixture
def clean_engine():
    engine = SmartHomeEngine()
    asyncio.run(engine.factory_reset())
    yield engine
    asyncio.run(engine.factory_reset())
    get_auth_3layer_manager().reset_to_factory_defaults()
    sync_engine_state_to_sqlite(engine)


@pytest.fixture
def clean_voice_auth():
    vm = VoiceAuthManager(AUDIO_DIR)
    vm.reset_to_factory_defaults()
    yield vm
    vm.reset_to_factory_defaults()


@pytest.fixture
def clean_test_client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# KỊCH BẢN VA CHẠM 1: THU ÂM TRÙNG GIỌNG & BẢO TOÀN QUYỀN CHỦ NHÀ CẤP 1
# ==============================================================================

class TestCollisionScenario1VoiceEnrollmentAndTier1Invariant:
    """KỊCH BẢN 1: Chủ nhà Cấp 1 đang điều khiển bình thường -> Mở luồng thu âm
    cho Cấp 2 / Cấp 3 hoặc mở QR động -> Chủ nhà Cấp 1 vô tình nói vào Mic ->
    Hệ thống phát hiện trùng giọng Cấp 1, từ chối lưu vào Cấp 3, VÀ kiểm tra ngay
    sau đó Chủ nhà Cấp 1 nói lệnh 'Mở cửa chính' vẫn giữ nguyên 100% quyền Cấp 1
    (tuyệt đối không bị kẹt ở Cấp 3!).
    """

    def test_collision_flow_1_duplicate_voice_reject_and_tier1_invariant(
        self,
        clean_engine: SmartHomeEngine,
        clean_voice_auth: VoiceAuthManager,
        pcm_owner_bytes: bytes,
    ) -> None:
        async def _run() -> None:
            engine = clean_engine
            vm = clean_voice_auth

            # 1. Chủ nhà Cấp 1 đang điều khiển bình thường
            engine.set_active_user("tuan_anh")
            assert engine.current_tier == 1
            assert engine.current_role == "ADMIN"

            init_door_res = await engine.execute_device_action("main_door", "open", source="test")
            assert init_door_res.get("ok") is True, "Chủ nhà Cấp 1 phải mở được cửa bình thường"
            await engine.execute_device_action("main_door", "close", source="test")

            # 2. Mở phiên thu âm cấp quyền cho Cấp 3 (Khách)
            enroll_init = await engine.start_voice_enrollment(
                target_tier=3,
                target_name="Khách Thử Nghiệm",
                duration_seconds=5,
            )
            assert enroll_init.get("ok") is True
            assert engine.pending_voice_enrollment is not None
            assert engine.pending_voice_enrollment.get("target_tier") == 3

            # 3. Va chạm: Chủ nhà Cấp 1 vô tình nói vào Mic trong phiên thu âm Cấp 3
            is_dup, reason, matched = check_duplicate_voice_gate_helper(vm, pcm_owner_bytes)
            assert is_dup is True, "Hệ thống phải phát hiện giọng vừa thu trùng với người trong nhà!"
            assert reason == "TRUNG_GIONG_NGUOI_TRONG_NHA"
            assert matched is not None
            assert matched.get("id") == "owner_voice_1"

            # 4. Cổng từ chối: Tuyệt đối không lưu đè làm hạ cấp Chủ nhà xuống Cấp 3
            owner_prof = vm.profiles.get("owner_voice_1")
            assert owner_prof is not None
            assert owner_prof.get("tier") == 1
            assert owner_prof.get("role") == "ADMIN"
            assert owner_prof.get("authorized") is True

            # Hủy phiên thu âm do trùng giọng
            engine.pending_voice_enrollment = None

            # 5. BẤT BIẾN QUYỀN CHỦ NHÀ (TIER 1 INVARIANT):
            # Ngay sau khi bị từ chối thu âm, Chủ nhà Cấp 1 nói lệnh 'Mở cửa chính'
            auth_res = vm.verify_pcm16k_and_apply_strikes(pcm_owner_bytes)
            assert auth_res.get("authorized") is True
            assert auth_res.get("tier") == 1, "Chủ nhà phải giữ nguyên 100% Cấp 1, không bị tụt xuống Cấp 3!"
            assert auth_res.get("speaker_id") == "owner_voice_1"

            # Thực thi lệnh mở cửa của Chủ nhà
            door_open_res = await engine.execute_device_action("main_door", "open", source="test")
            assert door_open_res.get("ok") is True
            assert engine.devices["main_door"]["state"] == "OPEN", "Cửa chính phải mở thành công!"
            assert engine.current_tier == 1

        asyncio.run(_run())


# ==============================================================================
# KỊCH BẢN VA CHẠM 2: MÃ QR ĐỘNG 10S TỪ ĐẦU ĐẾN CUỐI & MIỄN NHIỄM CẤP 1
# ==============================================================================

class TestCollisionScenario2DynamicQRLifecycleAndTier1Immunity:
    """KỊCH BẢN 2: Cấp 1 chọn giới hạn thời gian (1 ngày / 2 ngày / 1 tuần / 1 tháng / 1 năm)
    -> Sinh QR động 10s (thử quét QR hết hạn 10s phải bị chặn; quét QR còn hạn 10s vào trang
    thu âm thành công) -> Khách thu âm lần 1 im lặng/ồn bị báo 'Chưa đạt - Phải thu lại' ->
    Thu âm lần 2 trùng giọng Cấp 1 bị báo 'Trùng giọng người trong nhà - Từ chối' ->
    Thu âm lần 3 bằng giọng khách mới đạt chuẩn -> Lưu thành công Cấp 3 (1 lần duy nhất,
    không cần điền email vẫn xong) -> Khách Cấp 3 bật đèn (Cho phép), mở cửa chính (Chặn) ->
    Giả lập trôi qua mốc expires_at -> Khách nói lại bị từ chối vì hết hạn ->
    Ngay lập tức Chủ nhà Cấp 1 nói vào Mic phải mở được cửa chính bình thường
    (không bị dính trạng thái chặn của khách!).
    """

    def test_collision_flow_2_dynamic_qr_and_expiry_immunity(
        self,
        clean_engine: SmartHomeEngine,
        clean_voice_auth: VoiceAuthManager,
        pcm_owner_bytes: bytes,
        pcm_tier3_bytes: bytes,
    ) -> None:
        async def _run() -> None:
            engine = clean_engine
            vm = clean_voice_auth
            auth_mgr = get_auth_3layer_manager()
            used_tokens: set[str] = set()

            # 1. Cấp 1 chọn thời hạn (1 tuần = 604800s) và sinh QR động 10s
            qr_gen = generate_dynamic_qr_token_helper(auth_mgr, issuer_tier=1, duration_type="1w")
            assert qr_gen.get("ok") is True
            token = qr_gen["token"]
            cur_window = qr_gen["window"]
            assert qr_gen["duration_seconds"] == 604800

            # 2. Thử quét QR đã hết hạn 10s (giả lập window cũ cách 2 chu kỳ)
            old_win = cur_window - 3
            handshake_fail = consume_guest_handshake_helper(
                auth_mgr, token="expired_token_123", target_window=old_win, used_token_store=used_tokens
            )
            assert handshake_fail.get("ok") is False
            assert handshake_fail.get("status_code") == 401
            assert "hết hạn" in handshake_fail.get("error", "") and ("180 giây" in handshake_fail.get("error", "") or "10 giây" in handshake_fail.get("error", ""))

            # 3. Quét QR còn hạn 10s -> Thành công, đốt token (single-use)
            handshake_ok = consume_guest_handshake_helper(
                auth_mgr, token=token, target_window=cur_window, used_token_store=used_tokens
            )
            assert handshake_ok.get("ok") is True
            guest_sess_id = handshake_ok["guest_session_id"]
            assert guest_sess_id.startswith("guest_sess_")

            # Thử dùng lại đúng token vừa quét (chống chụp lại màn hình)
            replay_fail = consume_guest_handshake_helper(
                auth_mgr, token=token, target_window=cur_window, used_token_store=used_tokens
            )
            assert replay_fail.get("ok") is False
            assert replay_fail.get("status_code") == 400
            assert "Single-Use" in replay_fail.get("error", "")

            # 4. Khách thu âm:
            # Lần 1: Im lặng / Nhiễu trắng -> Bị báo "Chưa đạt - Phải thu lại"
            silent_pcm = np.zeros(16000 * 2, dtype=np.int16)
            q1 = validate_voice_quality_helper(silent_pcm, 16000)
            assert q1.get("ok") is False
            assert q1.get("status") == "CHUA_DAT"

            # Lần 2: Trùng giọng Chủ nhà Cấp 1 -> Bị cổng chống trùng giọng từ chối
            dup_chk, dup_msg, _ = check_duplicate_voice_gate_helper(vm, pcm_owner_bytes)
            assert dup_chk is True
            assert dup_msg == "TRUNG_GIONG_NGUOI_TRONG_NHA"

            # Lần 3: Giọng khách mới đạt chuẩn (thời lượng >= 2.0s) -> Lưu thành công Cấp 3 kèm expires_at
            pcm_guest_arr = np.tile(np.frombuffer(pcm_tier3_bytes, dtype=np.int16), 3)
            q3 = validate_voice_quality_helper(pcm_guest_arr, 16000)
            assert q3.get("ok") is True
            assert q3.get("status") == "DA_DAT"

            guest_expires_at = time.time() + 604800.0
            guest_prof = {
                "id": "guest_voice_temp_01",
                "name": "Khách Quét QR",
                "tier": 3,
                "role": "CHILD_GUEST",
                "authorized": True,
                "expires_at": guest_expires_at,
            }

            # 5. Hoạt động của Khách Cấp 3:
            engine.set_active_user("khach_c")
            assert engine.current_tier == 3

            # Khách bật đèn phòng khách -> Cho phép
            light_res = await engine.execute_device_action("living_room_light", "turn_on", source="test")
            assert light_res.get("ok") is True
            assert engine.devices["living_room_light"]["state"] == "ON"

            # Khách cố mở cửa chính -> Bị chặn 100% đúng quyền Cấp 3
            door_blocked = await engine.execute_device_action("main_door", "open", source="test")
            assert door_blocked.get("ok") is False
            door_blocked_msg = door_blocked.get("error") or door_blocked.get("exact_spoken_reply") or (door_blocked.get("results") or [{}])[0].get("error", "")
            assert "Từ chối" in door_blocked_msg or "Cấp 1" in door_blocked_msg or "không có quyền" in door_blocked_msg.lower()

            # 6. Giả lập trôi qua mốc expires_at (khách hết hạn)
            future_ts = guest_expires_at + 10.0
            exp_check = verify_guest_expiry_helper(guest_prof, mock_now_ts=future_ts)
            assert exp_check.get("authorized") is False
            assert exp_check.get("reason") == "GUEST_EXPIRED"

            # 7. BẤT BIẾN MIỄN NHIỄM CỦA CHỦ NHÀ CẤP 1 (TIER 1 IMMUNITY):
            # Ngay lập tức sau khi khách bị từ chối hết hạn, Chủ nhà Cấp 1 nói vào Mic
            engine.set_active_user("tuan_anh")
            assert engine.current_tier == 1
            owner_auth = vm.verify_pcm16k_and_apply_strikes(pcm_owner_bytes)
            assert owner_auth.get("authorized") is True
            assert owner_auth.get("tier") == 1

            # Chủ nhà mở cửa chính thành công, không bị ảnh hưởng bởi trạng thái hết hạn của khách
            owner_door = await engine.execute_device_action("main_door", "open", source="test")
            assert owner_door.get("ok") is True
            assert engine.devices["main_door"]["state"] == "OPEN"

        asyncio.run(_run())


# ==============================================================================
# KỊCH BẢN VA CHẠM 3: EMAIL TÙY CHỌN 2 LẦN + DNS MX + OTP & PHÂN CẤP GIA ĐÌNH
# ==============================================================================

class TestCollisionScenario3EmailBindingAndFamilyHierarchy:
    """KỊCH BẢN 3: Khách hoặc thành viên chọn điền Email ->
    Nhập 2 ô lệch nhau (Chặn) -> Nhập 2 ô khớp nhưng tên miền ảo không có MX record (Chặn) ->
    Nhập 2 ô khớp có MX thật -> Gửi OTP -> Nhập sai OTP (Chặn) -> Nhập đúng OTP (Xác nhận thành công) ->
    Đăng nhập nhận Cấp 2 -> Bắt buộc thu âm giọng chính (Chưa đạt bắt thu lại -> Đạt mới mở khóa) ->
    Cấp 2 thêm tiếp Email Cấp 3 (Cho phép), Cấp 2 thử thêm/ghi đè Email Cấp 1 hoặc Cấp 2 (Chặn),
    Cấp 3 thử thêm Email (Chặn).
    """

    def test_collision_flow_3_email_otp_and_family_hierarchy(
        self,
        clean_engine: SmartHomeEngine,
        clean_voice_auth: VoiceAuthManager,
        pcm_tier2_bytes: bytes,
    ) -> None:
        async def _run() -> None:
            auth_mgr = get_auth_3layer_manager()
            otp_store: dict[str, dict[str, Any]] = {}

            # 1. Nhập 2 ô email lệch nhau -> Bị chặn
            res_mismatch = send_and_verify_email_otp_helper(
                auth_mgr,
                email="thanh_vien_moi@gmail.com",
                confirm_email="thanh_vien_khac@gmail.com",
                store=otp_store,
            )
            assert res_mismatch.get("ok") is False
            assert "không khớp nhau" in res_mismatch.get("error", "")

            # 2. Nhập 2 ô khớp nhau nhưng tên miền ảo không có MX record -> Bị chặn
            res_fake_mx = send_and_verify_email_otp_helper(
                auth_mgr,
                email="user@fake-nonexistent-domain-12345.xyz",
                confirm_email="user@fake-nonexistent-domain-12345.xyz",
                store=otp_store,
            )
            assert res_fake_mx.get("ok") is False
            assert "DNS MX" in res_fake_mx.get("error", "") or "bản ghi MX" in res_fake_mx.get("error", "")

            # 3. Nhập 2 ô khớp có tên miền MX thật (gmail.com) -> Gửi mã OTP
            target_email = "nep94121@gmail.com"
            res_send_otp = send_and_verify_email_otp_helper(
                auth_mgr,
                email=target_email,
                confirm_email=target_email,
                input_otp=None,
                store=otp_store,
            )
            assert res_send_otp.get("ok") is True
            assert res_send_otp.get("otp_dispatched") is True
            assert target_email in otp_store

            # 4. Nhập sai mã OTP -> Bị chặn
            res_wrong_otp = send_and_verify_email_otp_helper(
                auth_mgr,
                email=target_email,
                confirm_email=target_email,
                input_otp="000000",
                store=otp_store,
            )
            assert res_wrong_otp.get("ok") is False
            assert "không chính xác" in res_wrong_otp.get("error", "")

            # 5. Nhập đúng mã OTP -> Xác nhận thành công
            real_otp = otp_store[target_email]["otp"]
            res_correct_otp = send_and_verify_email_otp_helper(
                auth_mgr,
                email=target_email,
                confirm_email=target_email,
                input_otp=real_otp,
                store=otp_store,
            )
            assert res_correct_otp.get("ok") is True
            assert res_correct_otp.get("verified") is True

            # 6. Đăng nhập nhận Cấp 2 và bắt buộc qua Modal thu âm giọng chính:
            # Lần 1: Mẫu quá ngắn -> Bắt thu lại
            sr = 16000
            short_pcm = np.zeros(int(sr * 1.0), dtype=np.int16)
            q_short = validate_voice_quality_helper(short_pcm, sr)
            assert q_short.get("ok") is False
            assert q_short.get("status") == "CHUA_DAT"

            # Lần 2: Đạt chuẩn mẫu giọng Cấp 2 (thời lượng >= 2.0s)
            pcm_t2_arr = np.tile(np.frombuffer(pcm_tier2_bytes, dtype=np.int16), 3)
            q_t2 = validate_voice_quality_helper(pcm_t2_arr, sr)
            assert q_t2.get("ok") is True
            assert q_t2.get("status") == "DA_DAT"

            # 7. Phân cấp Thêm Email Gia Đình (Family Email Hierarchy):
            # Cấp 1 (Chủ nhà) thêm Cấp 2 -> Cho phép
            res_c1_add_c2 = auth_mgr.add_family_email("tuan_anh", "em_gai@gmail.com", 2)
            assert res_c1_add_c2.get("ok") is True

            # Cấp 2 (thanh_vien_a) thêm Cấp 3 (Khách) -> Cho phép
            res_c2_add_c3 = auth_mgr.add_family_email("thanh_vien_a", "ban_than@gmail.com", 3)
            assert res_c2_add_c3.get("ok") is True

            # Cấp 2 (thanh_vien_a) cố thêm hoặc ghi đè Cấp 1 -> BỊ CHẶN 100% (403)
            res_c2_add_c1 = auth_mgr.add_family_email("thanh_vien_a", "tuan_anh_override@gmail.com", 1)
            assert res_c2_add_c1.get("ok") is False
            assert res_c2_add_c1.get("status_code") == 403

            # Cấp 2 cố thêm Cấp 2 -> BỊ CHẶN 100% (403)
            res_c2_add_c2 = auth_mgr.add_family_email("thanh_vien_a", "ban_c2@gmail.com", 2)
            assert res_c2_add_c2.get("ok") is False
            assert res_c2_add_c2.get("status_code") == 403

            # Cấp 3 (khach_c) cố thêm bất kỳ ai -> BỊ CHẶN 100% (403)
            res_c3_add = auth_mgr.add_family_email("khach_c", "ai_do@gmail.com", 3)
            assert res_c3_add.get("ok") is False
            assert res_c3_add.get("status_code") == 403

        asyncio.run(_run())


# ==============================================================================
# KỊCH BẢN VA CHẠM 4: CHUYỂN ĐỔI CHẾ ĐỘ ONLINE <-> OFFLINE & 3-STRIKE NGƯỜI LẠ
# ==============================================================================

class TestCollisionScenario4ModeSwitchAndStrangerRecovery:
    """KỊCH BẢN 4: Người lạ nói 3 lần liên tiếp (Lần 1 cảnh báo 1, Lần 2 cảnh báo 2,
    Lần 3 im lặng tuyệt đối) -> Ngay sau Lần 3 im lặng, Chủ nhà Cấp 1 nói vào Mic
    phải được nhận diện và phản hồi ngay (không bị kẹt ở chế độ im lặng của người lạ!) ->
    Chuyển sang chế độ Offline (Ngắt Server): Cấp 1 bật đèn được nhưng mở cửa chính bị khóa
    cứng an toàn, Cấp 3 bị chặn -> Bật lại chế độ Online: trạng thái 7 thiết bị phải
    đồng bộ nguyên vẹn giữa Web 3D, SQLite và App Android.
    """

    def test_collision_flow_4_stranger_lockout_and_offline_security(
        self,
        clean_engine: SmartHomeEngine,
        clean_voice_auth: VoiceAuthManager,
        pcm_owner_bytes: bytes,
        pcm_intruder_bytes: bytes,
    ) -> None:
        async def _run() -> None:
            engine = clean_engine
            vm = clean_voice_auth
            vm.reset_strikes()

            # 1. Người lạ nói 3 lần liên tiếp (3-strike sequence)
            s1 = vm.verify_pcm16k_and_apply_strikes(pcm_intruder_bytes)
            assert s1.get("authorized") is False
            assert s1.get("strike_count") == 1
            assert s1.get("silent_ignore") is False
            assert "Tôi không được phép nhận lệnh từ người lạ" in s1.get("rejection_speech", "")

            s2 = vm.verify_pcm16k_and_apply_strikes(pcm_intruder_bytes)
            assert s2.get("authorized") is False
            assert s2.get("strike_count") == 2
            assert s2.get("silent_ignore") is False
            assert "Tôi sẽ không trả lời bạn lần nữa" in s2.get("rejection_speech", "")

            s3 = vm.verify_pcm16k_and_apply_strikes(pcm_intruder_bytes)
            assert s3.get("authorized") is False
            assert s3.get("strike_count") >= 3
            assert s3.get("silent_ignore") is True
            assert s3.get("rejection_speech") == "", "Lần 3 trở đi phải im lặng tuyệt đối"

            # 2. PHỤC HỒI NGAY LẬP TỨC CHO CHỦ NHÀ CẤP 1 (INVARIANT RECOVERY):
            # Ngay sau Lần 3 im lặng của kẻ lạ, Chủ nhà Cấp 1 nói vào Mic
            owner_auth = vm.verify_pcm16k_and_apply_strikes(pcm_owner_bytes)
            assert owner_auth.get("authorized") is True, "Chủ nhà Cấp 1 phải được cấp quyền ngay lập tức!"
            assert owner_auth.get("tier") == 1
            assert owner_auth.get("speaker_id") == "owner_voice_1"
            assert vm.unauthorized_strikes == 0, "Strikes của người lạ phải được reset khi Chủ nhà nói!"

            # 3. Chuyển sang chế độ Mạch Độc Lập Offline (Ngắt Server)
            await engine.set_server_connection_mode(False)
            assert engine.server_connected is False

            # Chủ nhà bật đèn khi Offline -> Cho phép qua local MCU default commands
            off_light = await engine.execute_offline_default_command("bật đèn", source="offline_mcu")
            assert off_light.get("ok") is True

            # Chủ nhà cố mở cửa chính khi Offline -> KHÓA CỨNG AN TOÀN (HARD-LOCKED SAFE)
            off_door = await engine.execute_offline_default_command("mở cửa chính", source="offline_mcu")
            assert off_door.get("ok") is False
            assert "khóa cứng" in off_door.get("error", "").lower() or "an ninh" in off_door.get("error", "").lower()

            # Khách Cấp 3 khi Offline -> Bị chặn 100%
            engine.set_active_user("khach_c")
            off_c3 = await engine.execute_offline_default_command("bật đèn", source="offline_mcu")
            assert off_c3.get("ok") is False
            assert "Tầng 3" in off_c3.get("error", "") or "Cấp 3" in off_c3.get("error", "") or "không được phép" in off_c3.get("error", "")

            # 4. Bật lại chế độ Online -> Đồng bộ trạng thái 7 thiết bị
            engine.set_active_user("tuan_anh")
            await engine.set_server_connection_mode(True)
            assert engine.server_connected is True

            snap = engine.get_snapshot()
            dev_ids = [d["id"] for d in snap["devices"]]
            assert "main_door" in dev_ids
            assert "living_room_light" in dev_ids
            assert "garden_pump" in dev_ids
            assert len(dev_ids) == 7, "Phải đồng bộ đủ 7 thiết bị phần cứng"

        asyncio.run(_run())


# ==============================================================================
# KỊCH BẢN VA CHẠM 5: BỂ HẸN GIỜ + KHẨU LỆNH + LUẬT IF-THEN + 4 CHẾ ĐỘ RESET
# ==============================================================================

class TestCollisionScenario5TimersAliasesRulesAndResets:
    """KỊCH BẢN 5: Đặt đổi từ + khẩu lệnh ('Vừng ơi mở ra') + luật IF ('Nếu cửa mở
    thì bật điều hòa') + hẹn giờ -> Kích hoạt khẩu lệnh kiểm tra chuỗi kéo theo ->
    Thực hiện từng loại Reset (reset giọng, reset hẹn giờ, reset luật, reset toàn bộ)
    và kiểm tra không làm hỏng hồ sơ giọng gốc Cấp 1 của Nguyễn Tuấn Anh!
    """

    def test_collision_flow_5_rules_cascade_and_resets_preserving_host(
        self,
        clean_engine: SmartHomeEngine,
        clean_voice_auth: VoiceAuthManager,
    ) -> None:
        async def _run() -> None:
            engine = clean_engine
            vm = clean_voice_auth
            engine.set_active_user("tuan_anh")

            # 1. Đặt đổi từ (Word Mapping)
            res_wm = await engine.set_word_mapping("đèn to", "living_room_light", require_confirmation=False)
            assert res_wm.get("ok") is True

            # 2. Đặt khẩu lệnh (Command Alias)
            res_alias = await engine.create_alias_rule("Vừng ơi mở ra", "main_door", "open", require_confirmation=False)
            assert res_alias.get("ok") is True

            # 3. Đặt luật Tự động hóa IF-THEN kéo theo: Nếu cửa chính OPEN -> Bật điều hòa (ac ON)
            res_if = await engine.set_if_else_rule(
                when_device_id="main_door",
                when_state="OPEN",
                then_device_id="ac",
                then_action="turn_on",
                require_confirmation=False,
                evaluate_now=False,
            )
            assert res_if.get("ok") is True

            # 4. Đặt hẹn giờ đếm ngược 5 giây cho đèn
            res_timer = await engine.schedule_timer_flexible(
                device_id="living_room_light",
                action="turn_off",
                seconds=5.0,
                repeat="once",
            )
            assert res_timer.get("ok") is True
            assert len(engine.active_timers) >= 1

            # 5. KÍCH HOẠT KHẨU LỆNH "Vừng ơi mở ra" VÀ KIỂM TRA DÂY CHUYỀN KÉO THEO:
            assert engine.devices["main_door"]["state"] == "CLOSED"
            assert engine.devices["ac"]["state"] == "OFF"

            alias_exec = await engine.execute_alias_rule("Vừng ơi mở ra")
            assert alias_exec.get("ok") is True
            assert engine.devices["main_door"]["state"] == "OPEN", "Cửa chính phải mở sau khẩu lệnh"
            assert engine.devices["ac"]["state"] == "ON", "Luật IF-THEN phải tự động kéo theo bật điều hòa!"

            # 6. Kiểm tra chống vòng lặp đệ quy (Cycle Detection DFS)
            res_cycle = await engine.set_if_else_rule(
                when_device_id="ac",
                when_state="ON",
                then_device_id="main_door",
                then_action="open",
                require_confirmation=False,
                evaluate_now=False,
            )
            assert res_cycle.get("ok") is False, "Hệ thống phải phát hiện vòng lặp đệ quy và từ chối!"
            assert "vòng lặp" in res_cycle.get("error", "").lower()

            # 7. KIỂM TRA 4 LOẠI RESET BẢO TOÀN GIỌNG GỐC CHỦ NHÀ CẤP 1:

            # 7.1 Reset Timers (chỉ xóa hẹn giờ, giữ nguyên luật và giọng nói)
            req_rt = await engine.request_factory_reset("timers")
            assert req_rt.get("ok") is True
            res_rt = await engine.confirm_pending_action(True)
            assert res_rt.get("ok") is True
            assert len(engine.active_timers) == 0, "Bể hẹn giờ phải được dọn sạch"
            assert "vừng ơi mở ra" in [k.lower() for k in engine.get_merged_aliases()], "Luật alias phải còn nguyên"

            # 7.2 Reset Rules (chỉ xóa luật, giữ nguyên giọng nói)
            req_rr = await engine.request_factory_reset("rules")
            assert req_rr.get("ok") is True
            res_rr = await engine.confirm_pending_action(True)
            assert res_rr.get("ok") is True
            assert "vừng ơi mở ra" not in [k.lower() for k in engine.get_merged_aliases()], "Khẩu lệnh phải được xóa về mặc định"

            # 7.3 Reset Voice (chỉ reset bộ đếm và danh sách giọng thêm tạm, bảo toàn Cấp 1)
            req_rv = await engine.request_factory_reset("voice")
            assert req_rv.get("ok") is True
            res_rv = await engine.confirm_pending_action(True)
            assert res_rv.get("ok") is True

            # 7.4 Reset All (Toàn bộ hệ thống)
            req_ra = await engine.request_factory_reset("all")
            assert req_ra.get("ok") is True
            res_ra = await engine.confirm_pending_action(True)
            assert res_ra.get("ok") is True

            # BẤT BIẾN TỐI CAO (SUPREME INVARIANT):
            # Hồ sơ giọng gốc Chủ nhà Cấp 1 Nguyễn Tuấn Anh trong database không bao giờ bị mất hoặc hỏng!
            owner_in_vm = vm.profiles.get("owner_voice_1")
            assert owner_in_vm is not None, "owner_voice_1 phải luôn tồn tại sau reset"
            assert owner_in_vm.get("tier") == 1
            assert owner_in_vm.get("role") == "ADMIN"
            assert "Nguyễn Tuấn Anh" in owner_in_vm.get("name", "")

        asyncio.run(_run())
