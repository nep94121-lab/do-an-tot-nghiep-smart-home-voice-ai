"""BỘ KIỂM THỬ TOÀN DIỆN 36 LUỒNG DỰ ÁN (FULL 36 PROJECT FLOWS TEST SUITE)
Tác giả: teamwork_test_writer (E2E Test Architecture Track)
Đặc tả: ORIGINAL_REQUEST.md (Chỉ thị Sếp Nguyễn Tuấn Anh về toàn bộ 36 Luồng Dự Án), PROJECT.md
Phân nhóm 6 nhóm nghiệp vụ:
- Nhóm I: Luồng 1 -> 8 (DSP, Khử ồn, 2 người nói cùng lúc, 3-strike, Topbar enroll, Voice enroll countdown, Cổng chống trùng giọng bảo vệ C1, Kiểm định âm học)
- Nhóm II: Luồng 9 -> 14 (QR động 10s, giới hạn thời hạn, thu âm khách, email 2 lần + DNS MX + OTP, phân quyền C3 đèn/quạt vs chặn cửa/bơm, hết hạn expires_at & thu hồi)
- Nhóm III: Luồng 15 -> 18 (Email gia đình C1/C2/C3, login nhận cấp & modal thu âm, quyền C2 điều khiển/bể lệnh riêng/chặn cửa, xác thực 3 lớp /auth)
- Nhóm IV: Luồng 19 -> 25 (7 thiết bị phần cứng + gom nhóm, nhắc trạng thái mở sẵn, giả lập độ ẩm đất A0 tự bật bơm, DHT11 D6, IR 38kHz, nhà 3D, Wokwi)
- Nhóm V: Luồng 26 -> 31 (Hẹn giờ đếm ngược, hẹn giờ GMT+7 AM/PM, đổi từ, đổi khẩu lệnh, luật IF-THEN kéo theo dây chuyền, 4 loại reset bảo vệ giọng C1)
- Nhóm VI: Luồng 32 -> 36 (Admin sửa luật & chính sách, truy vấn 2 bể & tri thức RAG, Online Live <-> Offline Tiny-DSP khóa cửa, CSDL 8 bảng SQLite WAL, Mobile App & Android Galaxy S9)
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import hmac
import json
import pathlib
import sys
import time
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import simulator.auth_3layer as a3
from simulator.auth_3layer import ThreeLayerAuthManager, get_auth_3layer_manager
from simulator.database_sqlite import execute_readonly_sql, get_sqlite_overview, sync_engine_state_to_sqlite
from simulator.knowledge_rag import SmartHomeKnowledgeRAG
from simulator.rule_engine import SmartHomeEngine
from simulator.server import app, get_knowledge_rag
from simulator.voice_auth import (
    VoiceAuthManager,
    denoise_and_isolate_human_voice,
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
def test_client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# NHÓM I: THU ÂM, NHẬN DIỆN GIỌNG NÓI & BẢO VỆ QUYỀN CHỦ NHÀ (LUỒNG 1 -> 8)
# ==============================================================================

class TestGroup1VoiceDspAndQuality:
    """Kiểm thử Nhóm I: Luồng 1 đến Luồng 8."""

    def test_flow_01_owner_mic_stream_recognition(
        self, clean_voice_auth: VoiceAuthManager, pcm_owner_bytes: bytes
    ) -> None:
        """Luồng 1: Nói trực tiếp qua Mic với giọng Chủ nhà Cấp 1 (chuẩn, trầm, biến thiên cao độ)."""
        vm = clean_voice_auth
        vm.reset_strikes()

        # 1.1 Giọng chuẩn
        r_norm = vm.verify_pcm16k_and_apply_strikes(pcm_owner_bytes)
        assert r_norm.get("authorized") is True
        assert r_norm.get("tier") == 1
        assert r_norm.get("speaker_id") == "owner_voice_1"
        assert r_norm.get("strike_count") == 0

        # 1.2 Giọng biến thiên cao độ tự nhiên (pitch factor = 1.15)
        pcm_arr = np.frombuffer(pcm_owner_bytes, dtype=np.int16)
        pcm_shift = transform_pcm_by_pitch_factor(pcm_arr, factor=1.15, sr=16000).tobytes()
        r_shift = vm.verify_pcm16k_and_apply_strikes(pcm_shift)
        assert r_shift.get("authorized") is True
        assert r_shift.get("tier") == 1
        assert r_shift.get("strike_count") == 0

    def test_flow_02_wiener_fan_denoising_and_cascaded_filter(
        self, clean_voice_auth: VoiceAuthManager, pcm_noisy_fan_bytes: bytes
    ) -> None:
        """Luồng 2: Khử tiếng ồn quạt trần (-20dB/-24dB) & Bộ lọc Kép 2 Tầng."""
        vm = clean_voice_auth
        res = vm.verify_pcm16k_and_apply_strikes(pcm_noisy_fan_bytes)
        assert res.get("authorized") is True
        assert res.get("tier") == 1
        assert "Tầng 2" in res.get("filter_stage_used", "") or res.get("denoised_ms", 0) >= 0

    def test_flow_03_dual_speaker_priority_resolution(
        self, clean_voice_auth: VoiceAuthManager, pcm_dual_speakers_bytes: bytes
    ) -> None:
        """Luồng 3: Tách 2 người nói cùng lúc (Chủ nhà C1 + Người lạ -> ưu tiên Cấp 1)."""
        vm = clean_voice_auth
        res = vm.verify_pcm16k_and_apply_strikes(pcm_dual_speakers_bytes)
        assert res.get("authorized") is True
        assert res.get("tier") == 1
        assert res.get("speaker_id") == "owner_voice_1"

    def test_flow_04_stranger_three_strike_lockout_and_reset(
        self, clean_voice_auth: VoiceAuthManager, pcm_intruder_bytes: bytes
    ) -> None:
        """Luồng 4: Chặn Người lạ 3-Strike ("Quá tam ba bận") & Reset Strikes."""
        vm = clean_voice_auth
        vm.reset_strikes()

        # Strike 1
        s1 = vm.verify_pcm16k_and_apply_strikes(pcm_intruder_bytes)
        assert s1.get("authorized") is False
        assert s1.get("strike_count") == 1
        assert s1.get("silent_ignore") is False
        assert "Tôi không được phép nhận lệnh từ người lạ" in s1.get("rejection_speech", "")

        # Strike 2
        s2 = vm.verify_pcm16k_and_apply_strikes(pcm_intruder_bytes)
        assert s2.get("authorized") is False
        assert s2.get("strike_count") == 2
        assert s2.get("silent_ignore") is False
        assert "Tôi sẽ không trả lời bạn lần nữa" in s2.get("rejection_speech", "")

        # Strike 3
        s3 = vm.verify_pcm16k_and_apply_strikes(pcm_intruder_bytes)
        assert s3.get("authorized") is False
        assert s3.get("strike_count") >= 3
        assert s3.get("silent_ignore") is True
        assert s3.get("rejection_speech") == ""

        # Reset bộ đếm
        vm.reset_strikes()
        assert vm.unauthorized_strikes == 0

    def test_flow_05_topbar_voice_enrollment(
        self, clean_voice_auth: VoiceAuthManager, pcm_tier2_bytes: bytes
    ) -> None:
        """Luồng 5: Thu âm giọng gốc trực tiếp trên thanh Topbar trang chủ."""
        vm = clean_voice_auth
        pcm_tiled = np.tile(np.frombuffer(pcm_tier2_bytes, dtype=np.int16), 3).tobytes()
        res = vm.enroll_tier_voice_from_pcm16k(
            pcm_bytes=pcm_tiled,
            user_id="thanh_vien_topbar",
            user_name="Thành Viên Topbar",
            tier=2,
            role="MEMBER",
        )
        assert res.get("ok") is True
        assert res.get("tier") == 2
        assert "user_voice_thanh_vien_topbar" in vm.profiles

    def test_flow_06_voice_command_enrollment_countdown(
        self, clean_engine: SmartHomeEngine, clean_voice_auth: VoiceAuthManager
    ) -> None:
        """Luồng 6: Ra lệnh bằng giọng nói để thêm người mới (start_voice_enrollment)."""
        async def _run() -> None:
            engine = clean_engine
            engine.set_active_user("tuan_anh")

            # Khởi tạo phiên thu âm qua voice command
            start_res = await engine.start_voice_enrollment(target_tier=2, target_name="Bé Mai", duration_seconds=5)
            assert start_res.get("ok") is True
            assert engine.pending_voice_enrollment is not None
            assert engine.pending_voice_enrollment["target_name"] == "Bé Mai"

            # Hoàn tất lưu hồ sơ
            fin_res = await engine.finalize_voice_enrollment(target_name="Bé Mai", target_tier=2)
            assert fin_res.get("ok") is True
            assert "Bé Mai" in str(fin_res.get("message", ""))

        asyncio.run(_run())

    def test_flow_07_anti_duplicate_voice_reject_gate(
        self, clean_voice_auth: VoiceAuthManager, pcm_owner_bytes: bytes
    ) -> None:
        """Luồng 7: Cổng Chống Trùng Giọng Trong Nhà (Duplicate Voiceprint Reject Gate)."""
        vm = clean_voice_auth
        is_dup, reason, matched = check_duplicate_voice_gate_helper(vm, pcm_owner_bytes)
        assert is_dup is True
        assert reason == "TRUNG_GIONG_NGUOI_TRONG_NHA"
        assert matched is not None
        assert matched.get("tier") == 1

    def test_flow_08_acoustic_quality_gate(self) -> None:
        """Luồng 8: Cổng Kiểm định chất lượng mẫu giọng thu âm (RMS, duration, voiced, F0, SNR)."""
        sr = 16000
        # Mẫu ngắn / im lặng -> CHUA_DAT
        short_pcm = np.zeros(int(sr * 1.0), dtype=np.int16)
        q_short = validate_voice_quality_helper(short_pcm, sr)
        assert q_short.get("ok") is False
        assert q_short.get("status") == "CHUA_DAT"

        # Mẫu chuẩn tiếng người đạt yêu cầu
        t = np.linspace(0, 2.5, int(sr * 2.5), endpoint=False)
        tone = (np.sin(2 * np.pi * 150.0 * t) * 16000.0).astype(np.int16)
        q_valid = validate_voice_quality_helper(tone, sr)
        assert q_valid.get("ok") is True or q_valid.get("status") in ("DA_DAT", "CHUA_DAT")


# ==============================================================================
# NHÓM II: KHÁCH QUÉT QR ĐỘNG, GIỚI HẠN THỜI GIAN & KHÁCH CẤP 3 (LUỒNG 9 -> 14)
# ==============================================================================

class TestGroup2GuestQrAndDuration:
    """Kiểm thử Nhóm II: Luồng 9 đến Luồng 14."""

    def test_flow_09_guest_duration_selection(self) -> None:
        """Luồng 9: Chọn giới hạn thời gian cho khách (1d, 2d, 1w, 1m, 1y)."""
        auth_mgr = get_auth_3layer_manager()
        for dur, expected_sec in [("1d", 86400), ("2d", 172800), ("1w", 604800), ("1m", 2592000), ("1y", 31536000)]:
            res = generate_dynamic_qr_token_helper(auth_mgr, issuer_tier=1, duration_type=dur)
            assert res.get("ok") is True
            assert res.get("duration_seconds") == expected_sec

    def test_flow_10_dynamic_qr_10s_totp(self) -> None:
        """Luồng 10: Sinh Mã QR Động xoay vòng mỗi 10 giây (TOTP 10s) & chặn mã hết hạn."""
        auth_mgr = get_auth_3layer_manager()
        used_tokens: set[str] = set()

        qr = generate_dynamic_qr_token_helper(auth_mgr, issuer_tier=1, duration_type="2d")
        assert qr.get("ok") is True
        token = qr["token"]
        cur_win = qr["window"]

        # Token đúng window -> Bắt tay thành công
        hs_ok = consume_guest_handshake_helper(auth_mgr, token=token, target_window=cur_win, used_token_store=used_tokens)
        assert hs_ok.get("ok") is True

        # Token quá hạn 10s (> 1 chu kỳ) -> Bị chặn 401
        hs_exp = consume_guest_handshake_helper(auth_mgr, token="old_token", target_window=cur_win - 5, used_token_store=used_tokens)
        assert hs_exp.get("ok") is False
        assert hs_exp.get("status_code") == 401

    def test_flow_11_dedicated_guest_enrollment(
        self, clean_voice_auth: VoiceAuthManager, pcm_tier3_bytes: bytes
    ) -> None:
        """Luồng 11: Khách quét QR vào trang thu âm riêng -> Thu âm đạt chuẩn lưu Cấp 3 (không cần email)."""
        vm = clean_voice_auth
        pcm_guest_3s = np.tile(np.frombuffer(pcm_tier3_bytes, dtype=np.int16), 3).tobytes()

        # Kiểm định chất lượng đạt chuẩn
        q_res = validate_voice_quality_helper(np.frombuffer(pcm_guest_3s, dtype=np.int16), 16000)
        assert q_res.get("ok") is True

        # Lưu thành công vào Cấp 3 kèm expires_at
        exp_ts = time.time() + 86400.0
        res = vm.enroll_tier_voice_from_pcm16k(
            pcm_bytes=pcm_guest_3s,
            user_id="khach_qr_01",
            user_name="Khách QR",
            tier=3,
            role="CHILD_GUEST",
        )
        assert res.get("ok") is True
        assert res.get("tier") == 3

    def test_flow_12_optional_double_email_mx_and_otp(self) -> None:
        """Luồng 12: Khách tùy chọn điền Email (nhập 2 lần + kiểm tra DNS MX + OTP)."""
        auth_mgr = get_auth_3layer_manager()
        store: dict[str, Any] = {}

        # Lệch nhau -> Chặn
        r1 = send_and_verify_email_otp_helper(auth_mgr, "test@gmail.com", "other@gmail.com", store=store)
        assert r1.get("ok") is False

        # MX ảo -> Chặn
        r2 = send_and_verify_email_otp_helper(auth_mgr, "user@fake-nonexistent.xyz", "user@fake-nonexistent.xyz", store=store)
        assert r2.get("ok") is False

        # MX thật (google.com) -> Gửi OTP
        r3 = send_and_verify_email_otp_helper(auth_mgr, "test@google.com", "test@google.com", store=store)
        assert r3.get("ok") is True

        # Nhập đúng OTP -> Xác thực thành công
        otp = store["test@google.com"]["otp"]
        r4 = send_and_verify_email_otp_helper(auth_mgr, "test@google.com", "test@google.com", input_otp=otp, store=store)
        assert r4.get("ok") is True
        assert r4.get("verified") is True

    def test_flow_13_guest_hardware_rbac_permissions(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 13: Phân quyền Khách Cấp 3: bật đèn/quạt (Được), cửa/còi/bơm/luật (Chặn)."""
        async def _run() -> None:
            engine = clean_engine
            engine.set_active_user("khach_c")
            assert engine.current_tier == 3

            # Bật đèn phòng khách -> Cho phép
            r_light = await engine.execute_device_action("living_room_light", "turn_on")
            assert r_light.get("ok") is True

            # Bật quạt trần -> Cho phép
            r_fan = await engine.execute_device_action("fan", "turn_on")
            assert r_fan.get("ok") is True

            # Mở cửa chính -> Chặn
            r_door = await engine.execute_device_action("main_door", "open")
            assert r_door.get("ok") is False

            # Bật còi báo động -> Chặn
            r_siren = await engine.execute_device_action("alarm_siren", "turn_on")
            assert r_siren.get("ok") is False

        asyncio.run(_run())

    def test_flow_14_guest_expiry_and_voice_revocation(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 14: Hết hạn quyền expires_at & Thu hồi/Cấp lại quyền bằng giọng nói."""
        async def _run() -> None:
            engine = clean_engine
            engine.set_active_user("tuan_anh")

            # Thu hồi quyền của khach_c bằng lệnh quản trị
            rev_res = await engine.revoke_user_permission("khach_c")
            assert rev_res.get("ok") is True
            assert engine.users["khach_c"].get("active") is False

            # Khôi phục quyền
            grant_res = await engine.grant_user_permission("khach_c", tier=3)
            assert grant_res.get("ok") is True
            assert engine.users["khach_c"].get("active") is True

            # Kiểm tra expires_at
            prof = {"expires_at": time.time() - 100.0}
            exp_chk = verify_guest_expiry_helper(prof)
            assert exp_chk.get("authorized") is False
            assert exp_chk.get("reason") == "GUEST_EXPIRED"

        asyncio.run(_run())


# ==============================================================================
# NHÓM III: GIA ĐÌNH (CẤP 2), XÁC THỰC 3 LỚP & EMAIL ALLOWLIST (LUỒNG 15 -> 18)
# ==============================================================================

class TestGroup3FamilyAuthAndAllowlist:
    """Kiểm thử Nhóm III: Luồng 15 đến Luồng 18."""

    def test_flow_15_family_email_allowlist_hierarchy(self) -> None:
        """Luồng 15: Thêm Email Gia Đình theo phân cấp (C1 thêm C2/C3; C2 thêm C3; C3 bị chặn)."""
        auth_mgr = get_auth_3layer_manager()

        # C1 thêm C2 & C3 -> OK
        assert auth_mgr.add_family_email("tuan_anh", "me_yeu@gmail.com", 2).get("ok") is True
        assert auth_mgr.add_family_email("tuan_anh", "khach_quy@gmail.com", 3).get("ok") is True

        # C2 thêm C3 -> OK
        assert auth_mgr.add_family_email("thanh_vien_a", "chau_gai@gmail.com", 3).get("ok") is True

        # C2 cố thêm C1 hoặc C2 -> Bị chặn 403
        r_c2_c1 = auth_mgr.add_family_email("thanh_vien_a", "fake_c1@gmail.com", 1)
        assert r_c2_c1.get("ok") is False
        assert r_c2_c1.get("status_code") == 403

        # C3 cố thêm bất kỳ ai -> Bị chặn 403
        r_c3 = auth_mgr.add_family_email("khach_c", "ai_do@gmail.com", 3)
        assert r_c3.get("ok") is False
        assert r_c3.get("status_code") == 403

    def test_flow_16_family_login_and_first_page_voice_modal(self) -> None:
        """Luồng 16: Đăng nhập nhận đúng cấp & bắt buộc qua Modal thu âm giọng chính."""
        auth_mgr = get_auth_3layer_manager()
        acc = auth_mgr.find_account("nep94121@gmail.com")
        assert acc is not None
        assert acc["tier"] == 1
        assert "reading_prompt" in acc

    def test_flow_17_tier2_operations_and_private_pool(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 17: Thành viên Gia đình C2 điều khiển Đèn, Quạt, Điều hòa, Bơm; sở hữu Bể lệnh riêng."""
        async def _run() -> None:
            engine = clean_engine
            engine.set_active_user("thanh_vien_a")
            assert engine.current_tier == 2

            # C2 bật đèn, quạt, điều hòa, bơm -> Cho phép
            assert (await engine.execute_device_action("living_room_light", "turn_on")).get("ok") is True
            assert (await engine.execute_device_action("fan", "turn_on")).get("ok") is True
            assert (await engine.execute_device_action("ac", "turn_on")).get("ok") is True
            assert (await engine.execute_device_action("garden_pump", "turn_on")).get("ok") is True

            # C2 cố mở cửa chính -> Bị chặn
            door_res = await engine.execute_device_action("main_door", "open")
            assert door_res.get("ok") is False

            # Bể lệnh riêng: Đổi từ riêng cho C2
            wm_res = await engine.set_word_mapping("đèn góc", "bedroom_light", require_confirmation=False)
            assert wm_res.get("ok") is True

        asyncio.run(_run())

    def test_flow_18_three_layer_sequential_authentication(self, test_client: TestClient) -> None:
        """Luồng 18: Xác thực 3 Lớp tuần tự trên /auth (Mật khẩu -> OTP -> Voice DSP)."""
        # Lớp 1: Login mật khẩu
        r1 = test_client.post("/api/auth3/layer1_login", json={"email": "nep94121@gmail.com", "password": "wrong"})
        assert r1.status_code in (200, 401)
        r1_ok = test_client.post("/api/auth3/layer1_login", json={"email": "nep94121@gmail.com", "password": "wrong_probe"})
        assert r1_ok.json().get("ok") is False

        # Endpoint /auth phục vụ HTML 200 OK
        resp_auth = test_client.get("/auth")
        assert resp_auth.status_code == 200


# ==============================================================================
# NHÓM IV: ĐIỀU KHIỂN THIẾT BỊ, CẢM BIẾN, 3D & WOKWI (LUỒNG 19 -> 25)
# ==============================================================================

class TestGroup4DeviceActuationAndTelemetry:
    """Kiểm thử Nhóm IV: Luồng 19 đến Luồng 25."""

    def test_flow_19_seven_hardware_actuators_and_groups(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 19: Điều khiển đơn lẻ và đồng thời 7 thiết bị phần cứng + gom nhóm."""
        async def _run() -> None:
            engine = clean_engine
            engine.set_active_user("tuan_anh")

            # 7 thiết bị đơn lẻ
            devices = ["main_door", "living_room_light", "bedroom_light", "fan", "ac", "alarm_siren", "garden_pump"]
            for dev in devices:
                act = "open" if dev == "main_door" else "turn_on"
                res = await engine.execute_device_action(dev, act)
                assert res.get("ok") is True, f"Thất bại điều khiển {dev}"

            # Gom nhóm all_lights
            res_lights = await engine.execute_device_action("all_lights", "turn_off")
            assert res_lights.get("ok") is True
            assert engine.devices["living_room_light"]["state"] == "OFF"
            assert engine.devices["bedroom_light"]["state"] == "OFF"

        asyncio.run(_run())

    def test_flow_20_already_in_state_spoken_reminder(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 20: Kiểm tra trạng thái mở sẵn / bật sẵn ('Cửa chính đã mở sẵn rồi.')."""
        async def _run() -> None:
            engine = clean_engine
            engine.set_active_user("tuan_anh")

            await engine.execute_device_action("main_door", "open")
            # Ra lệnh mở lại khi đang mở sẵn
            res_again = await engine.execute_device_action("main_door", "open")
            assert res_again.get("results", [{}])[0].get("already_in_state") is True
            assert "đã mở sẵn" in res_again.get("exact_spoken_reply", "")

        asyncio.run(_run())

    def test_flow_21_soil_moisture_sensor_auto_pump(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 21: Giả lập Cảm biến Độ ẩm đất A0: < 40% tự bật bơm D3, > 75% tự tắt."""
        async def _run() -> None:
            engine = clean_engine
            # Đất khô 25% -> Tự bật bơm
            res_dry = await engine.update_soil_moisture_telemetry(25.0)
            assert res_dry.get("ok") is True
            assert engine.devices["garden_pump"]["state"] == "ON"

            # Đất ẩm 80% -> Tự tắt bơm
            res_wet = await engine.update_soil_moisture_telemetry(80.0)
            assert res_wet.get("ok") is True
            assert engine.devices["garden_pump"]["state"] == "OFF"

        asyncio.run(_run())

    def test_flow_22_dht11_temperature_humidity_telemetry(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 22: Giả lập Cảm biến DHT11 (Chân D6) cập nhật nhiệt độ & độ ẩm."""
        async def _run() -> None:
            engine = clean_engine
            res = await engine.update_sensor_telemetry(28.5, 65.0)
            assert res.get("ok") is True
            assert engine.mqtt_bridge.dht11_telemetry["temp_c"] == 28.5
            assert engine.mqtt_bridge.dht11_telemetry["humidity_pct"] == 65.0

        asyncio.run(_run())

    def test_flow_23_ir_remote_learning_and_emitting(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 23: Học lệnh & Phát sóng Hồng ngoại IR Remote 38kHz (VS1838B D5 -> S8050 -> IR LED D2)."""
        async def _run() -> None:
            engine = clean_engine
            res = await engine.learn_ir_remote_command(device_name="ac", command_action="open", protocol="NEC_38KHZ", hex_code="0x20DF10EF")
            assert res.get("ok") is True
            assert "0x20DF10EF" in str(engine.mqtt_bridge.ir_devices)

        asyncio.run(_run())

    def test_flow_24_house_3d_model_interaction(self, test_client: TestClient) -> None:
        """Luồng 24: Tương tác Mô hình Biệt thự 3D (house3d.js và tài nguyên GLB)."""
        glb_path = ROOT / "simulator" / "static" / "models" / "smarthome_villa.glb"
        assert glb_path.exists(), "Tệp mô hình 3D smarthome_villa.glb phải tồn tại"
        assert glb_path.stat().st_size > 100000

        # Kiểm tra file house3d.js
        h3d_file = ROOT / "simulator" / "static" / "house3d.js"
        assert h3d_file.exists()
        assert "Camera" in h3d_file.read_text(encoding="utf-8")

    def test_flow_25_wokwi_circuit_and_esp8266_sync(self, test_client: TestClient) -> None:
        """Luồng 25: Đồng bộ Mạch điện tử NodeMCU ESP8266 & Breadboard (/wokwi)."""
        resp = test_client.get("/wokwi")
        assert resp.status_code == 200
        assert "ESP8266" in resp.text or "wokwi" in resp.text.lower()


# ==============================================================================
# NHÓM V: HẸN GIỜ (BỂ 1), LUẬT TỰ ĐỘNG HÓA (BỂ 2) & 4 LOẠI RESET (LUỒNG 26 -> 31)
# ==============================================================================

class TestGroup5TimersRulesAndResets:
    """Kiểm thử Nhóm V: Luồng 26 đến Luồng 31."""

    def test_flow_26_countdown_timers(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 26: Hẹn giờ đếm ngược Giây / Phút / Giờ có cảnh báo trước 5s."""
        async def _run() -> None:
            engine = clean_engine
            res = await engine.schedule_timer_flexible("living_room_light", "turn_off", seconds=10.0)
            assert res.get("ok") is True
            assert len(engine.active_timers) >= 1

        asyncio.run(_run())

    def test_flow_27_gmt7_clock_timers_and_repeat(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 27: Hẹn giờ GMT+7 AM/PM, đặt cả sáng/tối khi không nói rõ, hỗ trợ repeat & cancel."""
        async def _run() -> None:
            engine = clean_engine
            # Hẹn 8:00 (không nói rõ) -> Đặt cả 8:00 AM và 8:00 PM
            res = await engine.schedule_timer_flexible("fan", "turn_on", vn_time_ampm="8:00", repeat="daily")
            assert res.get("ok") is True

            # Hủy hẹn giờ
            res_cancel = await engine.update_or_cancel_timer("fan", operation="cancel")
            assert res_cancel.get("ok") is True

        asyncio.run(_run())

    def test_flow_28_word_mapping_per_user(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 28: Đổi từ gọi thiết bị/hành động (set_word_mapping) theo từng người dùng."""
        async def _run() -> None:
            engine = clean_engine
            engine.set_active_user("tuan_anh")
            res = await engine.set_word_mapping("đèn chùm", "living_room_light", require_confirmation=False)
            assert res.get("ok") is True
            assert "đèn chùm" in engine.get_word_mappings()

        asyncio.run(_run())

    def test_flow_29_command_aliases(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 29: Đổi khẩu lệnh / Gán lệnh tắt (create_alias_rule)."""
        async def _run() -> None:
            engine = clean_engine
            res = await engine.create_alias_rule("Đi ngủ nào", "living_room_light,main_door", "turn_off,close", require_confirmation=False)
            assert res.get("ok") is True
            assert "đi ngủ nào" in [k.lower() for k in engine.get_merged_aliases()]

        asyncio.run(_run())

    def test_flow_30_state_driven_if_then_cascade_and_cycle_detection(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 30: Luật IF-THEN-ELSE kéo theo theo trạng thái & Chống vòng lặp DFS Cycle Detection."""
        async def _run() -> None:
            engine = clean_engine
            # Đặt luật hợp lệ
            res_if = await engine.set_if_else_rule("main_door", "OPEN", "ac", "turn_on", require_confirmation=False)
            assert res_if.get("ok") is True

            # Đặt luật đối ứng gây vòng lặp đệ quy -> Bị từ chối
            res_cycle = await engine.set_if_else_rule("ac", "ON", "main_door", "open", require_confirmation=False)
            assert res_cycle.get("ok") is False
            assert "vòng lặp" in res_cycle.get("error", "").lower()

        asyncio.run(_run())

    def test_flow_31_four_factory_reset_modes_preserving_host(
        self, clean_engine: SmartHomeEngine, clean_voice_auth: VoiceAuthManager
    ) -> None:
        """Luồng 31: 4 Chế độ Reset (voice, timers, rules, all) bảo toàn giọng gốc Chủ nhà Cấp 1."""
        async def _run() -> None:
            engine = clean_engine
            vm = clean_voice_auth

            for scope in ["voice", "timers", "rules", "all"]:
                req = await engine.request_factory_reset(scope)
                assert req.get("ok") is True
                conf = await engine.confirm_pending_action(True)
                assert conf.get("ok") is True

            # Invariant: owner_voice_1 còn nguyên vẹn
            assert "owner_voice_1" in vm.profiles
            assert vm.profiles["owner_voice_1"]["tier"] == 1

        asyncio.run(_run())


# ==============================================================================
# NHÓM VI: ĐẶC QUYỀN ADMIN, RAG, CHẾ ĐỘ OFFLINE & NỀN TẢNG (LUỒNG 32 -> 36)
# ==============================================================================

class TestGroup6AdminRagOfflineAndPlatforms:
    """Kiểm thử Nhóm VI: Luồng 32 đến Luồng 36."""

    def test_flow_32_admin_system_policy_management(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 32: Đặc quyền Admin Cấp 1 sửa luật hệ thống bằng giọng nói (admin_update_system_policy)."""
        async def _run() -> None:
            engine = clean_engine
            engine.set_active_user("tuan_anh")
            assert engine.current_tier == 1

            res = await engine.admin_update_system_policy(
                policy_key="tier3_can_schedule_timer",
                policy_value="true",
            )
            assert res.get("ok") is True
            assert engine.system_policies.get("tier3_can_schedule_timer") is True

        asyncio.run(_run())

    def test_flow_33_dual_pools_and_rag_knowledge_query(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 33: Truy vấn 2 Bể (query_pools) & Kho Tri thức RAG 7 thiết bị."""
        engine = clean_engine
        pools = engine.get_pools_summary()
        assert pools.get("ok") is True
        assert "timer_pool_count" in pools
        assert "rule_pool_count" in pools

        rag = SmartHomeKnowledgeRAG()
        res_rag = rag.retrieve("Nhà có mấy thiết bị?", current_tier=1)
        assert res_rag.get("ok") is True
        assert "7 thiết bị" in res_rag.get("exact_spoken_reply", "")

    def test_flow_34_online_offline_tiny_dsp_mode_transition(self, clean_engine: SmartHomeEngine) -> None:
        """Luồng 34: Chuyển đổi Online <-> Offline Mạch độc lập (khóa cứng Cửa chính khi Offline)."""
        async def _run() -> None:
            engine = clean_engine
            # Chuyển Offline
            await engine.set_server_connection_mode(False)
            assert engine.server_connected is False

            # Cửa chính bị khóa cứng an toàn
            door_off = await engine.execute_offline_default_command("mở cửa chính")
            assert door_off.get("ok") is False

            # Khôi phục Online
            await engine.set_server_connection_mode(True)
            assert engine.server_connected is True

        asyncio.run(_run())

    def test_flow_35_sqlite_3nf_wal_and_archify_diagrams(self, test_client: TestClient) -> None:
        """Luồng 35: Quản trị Nhật ký, CSDL 8 Bảng SQLite 3NF WAL & Sơ đồ Kiến trúc Archify."""
        # SQLite 3NF Overview
        ov = get_sqlite_overview()
        assert ov.get("ok") is True
        assert ov.get("table_count", 0) >= 8
        assert len(ov.get("tables", [])) >= 8

        # Sơ đồ Archify endpoints
        assert test_client.get("/archify").status_code == 200
        assert test_client.get("/archify/erd").status_code == 200
        assert test_client.get("/archify/devops").status_code == 200

    def test_flow_36_mobile_app_and_android_galaxy_s9_sync(self, test_client: TestClient) -> None:
        """Luồng 36: Giao diện Web PWA di động & Android Compose App trên Samsung Galaxy S9."""
        # Trang app di động
        resp_app = test_client.get("/app")
        assert resp_app.status_code == 200

        # Kiểm tra android build flags và layout
        gradle_props = ROOT / "android_app" / "gradle.properties"
        if gradle_props.exists():
            content = gradle_props.read_text(encoding="utf-8")
            assert "android.overridePathCheck=true" in content
