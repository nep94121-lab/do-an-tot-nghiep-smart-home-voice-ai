"""Bộ Kiểm Tra Độc Lập Bổ Sung (Orthogonal Verification) Milestone M4 Iteration 2.

Người thực hiện: challenger_m4_reverify_sec (Role: Empirical Adversarial Challenger)
Mục tiêu kiểm định độc lập:
1. Thử gửi payload bất thường, nonce ngẫu nhiên (UUID4, hex, bytes, large ints, unicode) vào:
   - Toàn bộ các route tĩnh (6 trang HTML, 6 tệp CSS, 6 tệp JS)
   - Các route REST API xác thực khách, điều khiển, nhật ký
2. Thử nghiệm các vector tấn công biên (Boundary Attacks):
   - Path traversal trên static files
   - SQLi read-only bypass trên /api/logs/sql_query
   - Malformed base64 / audio fuzzing trên /api/auth3/guest_qr_complete_voice
   - Rate/brute-force OTP fuzzing trên /api/auth3/guest_qr_verify_otp
3. Kiểm tra WebSocket /ws với payload bất thường và xác nhận zero ghost session leak sau khi ngắt kết nối.
"""

from __future__ import annotations

import base64
import concurrent.futures
import os
import pathlib
import sqlite3
import sys
import uuid
import wave
import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.server import app, _ACTIVE_BRIDGES, _BOOT_VOICE_AUTH
from simulator.auth_3layer import get_auth_3layer_manager
from simulator.rule_engine import SmartHomeEngine
from simulator.voice_auth import (
    SEP_REAL_VOICE_COMMANDS_META,
    VoiceAuthManager,
    synthesize_noisy_fan_voice,
    transform_pcm_by_pitch_factor,
    transform_pcm_to_intruder_voice,
)


@pytest.fixture(autouse=True)
def clean_system_state():
    """Làm sạch bộ nhớ đệm token, active bridges và reset voice auth."""
    mgr = get_auth_3layer_manager()
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    if hasattr(mgr, "active_qr_tokens"):
        mgr.active_qr_tokens.clear()
    if hasattr(mgr, "guest_qr_sessions"):
        mgr.guest_qr_sessions.clear()
    _ACTIVE_BRIDGES.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    yield
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    if hasattr(mgr, "active_qr_tokens"):
        mgr.active_qr_tokens.clear()
    if hasattr(mgr, "guest_qr_sessions"):
        mgr.guest_qr_sessions.clear()
    _ACTIVE_BRIDGES.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# =============================================================================
# A. ORTHOGONAL TEST: RANDOM NONCES & MALFORMED INPUTS TRÊN STATIC ROUTES
# =============================================================================

STATIC_ROUTES = [
    "/",
    "/auth",
    "/guest_enroll",
    "/wokwi",
    "/logs",
    "/app",
    "/static/css/style.css",
    "/static/css/auth.css",
    "/static/css/guest_enroll.css",
    "/static/css/wokwi.css",
    "/static/css/logs.css",
    "/static/css/mobile_app.css",
    "/static/js/app.js",
    "/static/js/auth.js",
    "/static/js/guest_enroll.js",
    "/static/js/wokwi.js",
    "/static/js/logs.js",
    "/static/js/mobile_app.js",
]


class TestOrthogonalStaticRoutes:
    """Kiểm thử route tĩnh với nonce ngẫu nhiên và các tham số biến dị."""

    @pytest.mark.parametrize("route", STATIC_ROUTES)
    def test_static_route_with_random_nonces_and_query_parameters(
        self, client: TestClient, route: str
    ) -> None:
        """Gửi các nonce ngẫu nhiên (UUID4, timestamp, random hex) và query params lạ."""
        nonce = uuid.uuid4().hex
        resp = client.get(
            f"{route}?v={nonce}&nonce={nonce}&cache_bust={os.urandom(8).hex()}&test_param=orthogonal_check"
        )
        assert resp.status_code == 200, (
            f"Route {route} sập khi truyền query nonce: {resp.status_code}"
        )
        assert len(resp.content) > 50

    @pytest.mark.parametrize("route", STATIC_ROUTES)
    def test_static_route_with_abnormal_headers(
        self, client: TestClient, route: str
    ) -> None:
        """Gửi các header tùy biến, ký tự đặc biệt, nonce trong header."""
        nonce = uuid.uuid4().hex
        headers = {
            "X-Random-Nonce": nonce,
            "X-Forwarded-For": "192.168.1.254, 10.0.0.1",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": f"Adversarial-Challenger-Bot/{nonce}",
        }
        resp = client.get(route, headers=headers)
        assert resp.status_code == 200, (
            f"Route {route} sập khi gửi abnormal headers: {resp.status_code}"
        )

    def test_static_path_traversal_attempts_blocked_or_safe(
        self, client: TestClient
    ) -> None:
        """Thử các vector path traversal vào static files mount."""
        traversal_paths = [
            "/static/../server.py",
            "/static/%2e%2e/server.py",
            "/static/..%2f..%2fpackage.json",
            "/static/css/../../server.py",
            "/static/js/../../PROJECT.md",
        ]
        for p in traversal_paths:
            resp = client.get(p)
            # Phải là 404 Not Found hoặc 400 Bad Request, tuyệt đối không được 200 leak file bí mật hay 500 crash
            assert resp.status_code in (404, 400), (
                f"Path traversal '{p}' trả về {resp.status_code} không an toàn!"
            )


# =============================================================================
# B. ORTHOGONAL TEST: RANDOM NONCES & MALFORMED PAYLOADS TRÊN REST APIS
# =============================================================================


class TestOrthogonalApiRoutes:
    """Kiểm thử các API routes với payload bất thường và nonce ngẫu nhiên."""

    def test_guest_qr_current_with_random_nonces_and_unusual_durations(
        self, client: TestClient
    ) -> None:
        """Thử các giá trị duration hợp lệ lẫn dị biệt kèm nonce ngẫu nhiên."""
        # 1. Hợp lệ với nonce ngẫu nhiên
        for valid_dur in ["1d", "2d", "1w", "1m", "1y"]:
            nonce = uuid.uuid4().hex
            resp = client.get(f"/api/auth3/guest_qr_current?duration={valid_dur}&nonce={nonce}")
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("ok") is True
            assert "token" in data
            assert data.get("duration") == valid_dur

        # 2. Bất thường: duration dị biệt
        for weird_dur in ["999y", "invalid", "<script>", "1000000d", ""]:
            nonce = uuid.uuid4().hex
            resp = client.get(f"/api/auth3/guest_qr_current?duration={weird_dur}&nonce={nonce}")
            # Server có thể fallback về default "1d" hoặc trả 400, tuyệt đối không được 500
            assert resp.status_code in (200, 400), (
                f"Unexpected status {resp.status_code} for duration {weird_dur}"
            )
            assert resp.status_code != 500

    def test_guest_qr_handshake_random_nonces_and_malformed_structures(
        self, client: TestClient
    ) -> None:
        """Thử gửi các cấu trúc payload bất thường vào /api/auth3/guest_qr_handshake."""
        malformed_payloads = [
            {},  # Empty object
            {"token": ""},  # Empty token
            {"token": uuid.uuid4().hex},  # Nonce token not in memory
            {"token": uuid.uuid4().hex, "duration": "100y", "extra": {"nested": 123}},
            {"token": None, "target_window": None},
            {"token": True, "target_window": False},
            {"token": ["array", "of", "tokens"]},
        ]
        for p in malformed_payloads:
            resp = client.post("/api/auth3/guest_qr_handshake", json=p)
            assert resp.status_code in (400, 401, 422), (
                f"Payload {p} gây status {resp.status_code} thay vì 400/401/422!"
            )
            assert resp.status_code != 500

    def test_guest_qr_send_otp_validation_and_fuzzing(
        self, client: TestClient
    ) -> None:
        """Fuzzing endpoint /api/auth3/guest_qr_send_otp."""
        # 1. Email lệch nhau -> Phải bị từ chối (400 hoặc ok=False), tuyệt đối không 500
        resp1 = client.post(
            "/api/auth3/guest_qr_send_otp",
            json={
                "session_id": "simulated_session",
                "email_1": "test@gmail.com",
                "email_2": "different@gmail.com",
                "guest_name": "Test Guest",
            },
        )
        assert resp1.status_code in (400, 422)
        assert resp1.status_code != 500
        assert resp1.json().get("ok") is False

        # 2. Email domain ảo không có DNS MX -> Bị chặn từ chối
        resp2 = client.post(
            "/api/auth3/guest_qr_send_otp",
            json={
                "session_id": "simulated_session",
                "email_1": "fake_user@domain-khong-ton-tai-xyz-987654321.fake",
                "email_2": "fake_user@domain-khong-ton-tai-xyz-987654321.fake",
                "guest_name": "Test Guest",
            },
        )
        assert resp2.status_code in (400, 422)
        assert resp2.status_code != 500
        assert resp2.json().get("ok") is False

        # 3. Payload dị thường (chuỗi cực dài với domain không tồn tại) -> Bị chặn, không crash 500
        resp3 = client.post(
            "/api/auth3/guest_qr_send_otp",
            json={
                "session_id": uuid.uuid4().hex,
                "email_1": "a" * 200 + "@nonexistent.invalid",
                "email_2": "a" * 200 + "@nonexistent.invalid",
                "guest_name": "\x00\x01\x02\xff",
            },
        )
        assert resp3.status_code in (400, 422)
        assert resp3.status_code != 500
        assert resp3.json().get("ok") is False

    def test_guest_qr_verify_otp_fuzzing_and_brute_force(
        self, client: TestClient
    ) -> None:
        """Fuzzing mã OTP ngẫu nhiên trên /api/auth3/guest_qr_verify_otp."""
        # 1. Thử brute-force các mã OTP sai khi chưa có session
        random_otps = [
            "000000",
            "999999",
            "123456",
            "abcdef",
            "1234567890",
            "-1",
            "null",
            "' OR 1=1; --",
        ]
        for otp_code in random_otps:
            resp = client.post(
                "/api/auth3/guest_qr_verify_otp",
                json={
                    "email": f"test_user_{uuid.uuid4().hex[:6]}@gmail.com",
                    "otp": otp_code,
                },
            )
            # Hệ thống xử lý an toàn: không crash 500, và báo lỗi không xác thực
            assert resp.status_code != 500
            data = resp.json()
            assert data.get("ok") is False or resp.status_code in (400, 401, 422)

    def test_guest_qr_complete_voice_audio_fuzzing(
        self, client: TestClient
    ) -> None:
        """Fuzzing payload âm thanh vào /api/auth3/guest_qr_complete_voice."""
        corrupted_payloads = [
            # Base64 hỏng
            {"session_id": "ses1", "guest_name": "Khách", "audio_pcm_b64": "!!!NOT_BASE64!!!"},
            # Base64 của dữ liệu rác (không phải 16kHz PCM audio)
            {"session_id": "ses2", "guest_name": "Khách", "audio_pcm_b64": base64.b64encode(b"random_junk_data_here").decode("ascii")},
            # Chuỗi rỗng
            {"session_id": "ses3", "guest_name": "Khách", "audio_pcm_b64": ""},
            # None
            {"session_id": "ses4", "guest_name": "Khách", "audio_pcm_b64": None},
        ]
        for p in corrupted_payloads:
            resp = client.post("/api/auth3/guest_qr_complete_voice", json=p)
            # Hệ thống phải từ chối lịch sự (400 hoặc 422), không được unhandled crash 500
            assert resp.status_code in (400, 422), (
                f"Audio fuzzing payload gây {resp.status_code}!"
            )
            assert resp.status_code != 500

    def test_sql_query_read_only_wal_protection_against_injection(
        self, client: TestClient
    ) -> None:
        """Kiểm thử route /api/logs/sql_query chống lại các truy vấn ghi (DROP, INSERT, UPDATE, DELETE)."""
        malicious_queries = [
            "DROP TABLE system_audit_logs;",
            "INSERT INTO system_audit_logs (action) VALUES ('hacked');",
            "UPDATE system_audit_logs SET action = 'tampered';",
            "DELETE FROM system_audit_logs;",
            "ALTER TABLE system_audit_logs ADD COLUMN hack TEXT;",
            "ATTACH DATABASE ':memory:' AS hack_db;",
        ]
        for sql in malicious_queries:
            resp = client.post(
                "/api/logs/sql_query",
                json={"sql": sql, "limit": 10},
            )
            # Route này tuyệt đối không được crash 500, và BẮT BUỘC trả ok: False với thông báo bảo vệ CSDL
            assert resp.status_code != 500, f"SQL '{sql}' gây crash HTTP 500!"
            data = resp.json()
            assert data.get("ok") is False, (
                f"SQL query nguy hại '{sql}' không bị chặn: {data}"
            )
            assert "Chế độ bảo vệ CSDL" in data.get("error", "") or "Chỉ cho phép" in data.get("error", "")

    def test_sql_query_read_only_valid_select_with_nonce(
        self, client: TestClient
    ) -> None:
        """Kiểm thử SELECT hợp lệ trả về dữ liệu an toàn."""
        resp = client.post(
            "/api/logs/sql_query",
            json={"sql": "SELECT 1 AS test_val, 'orthogonal_ok' AS note", "limit": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("ok") is True
        assert len(data.get("rows", [])) >= 1


# =============================================================================
# C. ORTHOGONAL TEST: WEBSOCKET /WS MALFORMED FRAMES & NONCE PACKETS
# =============================================================================


class TestOrthogonalWebSocketInteractions:
    """Kiểm thử đối kháng tương tác WebSocket với frame dị dạng và dữ liệu ngẫu nhiên."""

    def test_websocket_malformed_json_and_unknown_types(
        self, client: TestClient
    ) -> None:
        """Gửi các frame JSON với type dị thường hoặc cấu trúc lạ vào WebSocket."""
        assert len(_ACTIVE_BRIDGES) == 0

        with client.websocket_connect("/ws") as ws:
            # Nhận 3 frames khởi động
            ws.receive_json()  # state_snapshot
            ws.receive_json()  # system_prompt_updated
            ws.receive_json()  # gemini_status

            assert len(_ACTIVE_BRIDGES) == 1

            # Gửi 10 gói tin với type dị thường và nonce ngẫu nhiên
            for i in range(10):
                ws.send_json({
                    "type": f"orthogonal_nonce_type_{uuid.uuid4().hex[:8]}",
                    "nonce": uuid.uuid4().hex,
                    "payload": {"random_val": i * 123},
                })

            # Gửi tin nhắn mic_chunk với pcm16k_b64 dị thường
            ws.send_json({
                "type": "mic_chunk",
                "pcm16k_b64": "NOT_A_VALID_BASE64_DATA",
                "is_speech": False,
            })

            # Ngắt socket đột ngột
        
        # Sau khi ngắt, _ACTIVE_BRIDGES phải sạch 100%
        assert len(_ACTIVE_BRIDGES) == 0, (
            f"Rò rỉ active bridges sau WS fuzzing! len={len(_ACTIVE_BRIDGES)}"
        )

    def test_websocket_rapid_connect_disconnect_stress(
        self, client: TestClient
    ) -> None:
        """Mô phỏng 15 lần kết nối và ngắt tức thì trong thời gian siêu ngắn (<1ms)."""
        assert len(_ACTIVE_BRIDGES) == 0

        for idx in range(15):
            ctx = client.websocket_connect("/ws")
            ws = ctx.__enter__()
            assert len(_ACTIVE_BRIDGES) == 1
            # Thoát ngay lập tức không nhận message
            ctx.__exit__(None, None, None)
            assert len(_ACTIVE_BRIDGES) == 0

        assert len(_ACTIVE_BRIDGES) == 0


# =============================================================================
# D. ORTHOGONAL TEST: SINH TRẮC HỌC GIỌNG NÓI ĐỐI KHÁNG VỚI NHIỄU & GIỌNG LẠ
# =============================================================================

AUDIO_DIR = ROOT / "test_audio"
SLICED_DIR = AUDIO_DIR / "cac_cau_lenh_cua_sep"
DB_PATH = ROOT / "simulator" / "data" / "smarthome.db"


def _read_wav_pcm(path: pathlib.Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes())


class TestVoiceBiometricsAdversarialNoiseAndIntruders:
    """Kiểm thử đối kháng sinh trắc học giọng nói với nhiễu giả lập, người lạ và cổng bảo vệ quyền."""

    @pytest.fixture
    def enrolled_vm(self) -> VoiceAuthManager:
        vm = VoiceAuthManager(AUDIO_DIR)
        owner_wav = AUDIO_DIR / "giong_chu_nha_cap1_tuan_anh.wav"
        assert owner_wav.exists(), "Thiếu file mẫu gốc của Sếp"
        pcm_owner = _read_wav_pcm(owner_wav)
        vm.enroll_tier_voice_from_pcm16k(
            pcm_bytes=pcm_owner,
            user_id="tuan_anh",
            user_name="Nguyễn Tuấn Anh",
            tier=1,
            role="ADMIN",
            custom_label="Giọng Cấp 1 — Nguyễn Tuấn Anh (Chủ nhà)",
        )
        vm.reset_strikes()
        return vm

    def test_sep_real_voice_with_synthetic_fan_noise_authorized_tier1(
        self, enrolled_vm: VoiceAuthManager
    ) -> None:
        """Giọng thật của Sếp trong môi trường có tiếng quạt ù mạnh vẫn qua bộ lọc Wiener và xác thực đúng Cấp 1 ADMIN."""
        cmd_wav = SLICED_DIR / "cau_2_mo_cua_chinh.wav"
        pcm_cmd = np.frombuffer(_read_wav_pcm(cmd_wav), dtype=np.int16)
        noisy_pcm = synthesize_noisy_fan_voice(pcm_cmd, 16000)

        auth_res = enrolled_vm.verify_pcm16k_and_apply_strikes(noisy_pcm.tobytes(), is_live_mic=True)
        assert auth_res["authorized"] is True, f"Giọng Sếp kèm ồn bị từ chối: {auth_res}"
        assert auth_res["tier"] == 1
        assert auth_res["user_id"] == "tuan_anh"
        assert auth_res["role"] == "ADMIN"
        assert auth_res.get("fan_noise_detected") is True or auth_res.get("noise_removed_db", 0) > 0

    def test_intruder_voices_with_pitch_variations_blocked(
        self, enrolled_vm: VoiceAuthManager
    ) -> None:
        """Các mẫu giọng lạ (giong_2_nguoi_la_mo_cua, giong_cap3_khach_c và biến thể pitch) bị chặn tuyệt đối, không được cấp Cấp 1."""
        intruder_wav = AUDIO_DIR / "giong_2_nguoi_la_mo_cua.wav"
        guest_wav = AUDIO_DIR / "giong_cap3_khach_c.wav"
        assert intruder_wav.exists(), "Thiếu file giong_2_nguoi_la_mo_cua.wav"
        assert guest_wav.exists(), "Thiếu file giong_cap3_khach_c.wav"

        pcm_intruder_raw = np.frombuffer(_read_wav_pcm(intruder_wav), dtype=np.int16)
        pcm_guest_raw = np.frombuffer(_read_wav_pcm(guest_wav), dtype=np.int16)

        # 1. Giọng người lạ trực tiếp bị từ chối
        r_intruder = enrolled_vm.verify_pcm16k_and_apply_strikes(pcm_intruder_raw.tobytes(), is_live_mic=False)
        assert r_intruder["authorized"] is False
        assert r_intruder["tier"] != 1
        assert r_intruder["speaker_id"] == "intruder_voice_2"

        # 2. Giọng khách Cấp 3 khi chưa có quyền Admin Cấp 1 bị từ chối Cấp 1
        r_guest = enrolled_vm.verify_pcm16k_and_apply_strikes(pcm_guest_raw.tobytes(), is_live_mic=False)
        assert r_guest["authorized"] is False or r_guest["tier"] != 1

        # 3. Các biến thể pitch-shifted của giọng người lạ (0.85, 1.15) đều bị chặn
        for pitch_factor in [0.85, 1.15]:
            shifted_pcm = transform_pcm_by_pitch_factor(pcm_intruder_raw, factor=pitch_factor, sr=16000)
            auth_res = enrolled_vm.verify_pcm16k_and_apply_strikes(shifted_pcm.tobytes(), is_live_mic=False)
            assert auth_res["authorized"] is False, f"Giọng lạ pitch={pitch_factor} không bị chặn! {auth_res}"
            assert auth_res["tier"] != 1

    def test_three_consecutive_intruder_strikes_lockout(
        self, enrolled_vm: VoiceAuthManager
    ) -> None:
        """Cơ chế 3-strike lockout: Sau 3 lần người lạ nói sai liên tiếp -> Im lặng hoàn toàn (silent_ignore=True)."""
        intruder_wav = AUDIO_DIR / "giong_2_nguoi_la_mo_cua.wav"
        pcm_intruder = _read_wav_pcm(intruder_wav)

        enrolled_vm.reset_strikes()
        r1 = enrolled_vm.verify_pcm16k_and_apply_strikes(pcm_intruder, is_live_mic=False)
        assert r1["authorized"] is False

        r2 = enrolled_vm.verify_pcm16k_and_apply_strikes(pcm_intruder, is_live_mic=False)
        assert r2["authorized"] is False

        r3 = enrolled_vm.verify_pcm16k_and_apply_strikes(pcm_intruder, is_live_mic=False)
        assert r3["authorized"] is False
        assert enrolled_vm.unauthorized_strikes >= 3
        assert r3["silent_ignore"] is True

    def test_duplicate_voice_gate_blocks_tier2_tier3_registration_with_sep_voice(
        self, enrolled_vm: VoiceAuthManager
    ) -> None:
        """Cổng chống trùng giọng: Ngăn chặn kẻ mạo danh dùng giọng Sếp để đăng ký tài khoản Khách Cấp 3 hoặc Thành viên Cấp 2."""
        owner_wav = AUDIO_DIR / "giong_chu_nha_cap1_tuan_anh.wav"
        pcm_owner = _read_wav_pcm(owner_wav)

        dup_check = enrolled_vm.check_duplicate_voice_gate(
            feat_s1=pcm_owner,
            target_tier=3,
            target_user_id="attacker_guest",
        )
        assert dup_check.is_duplicate is True
        assert dup_check.matched_tier == 1

        enroll_res = enrolled_vm.enroll_tier_voice_from_pcm16k(
            pcm_bytes=pcm_owner,
            user_id="attacker_guest",
            user_name="Kẻ Giả Mạo",
            tier=3,
            role="CHILD_GUEST",
        )
        assert enroll_res["ok"] is False
        assert enroll_res["status"] == "DUPLICATE_VOICE_REJECTED"

    def test_invariant_guard_blocks_owner_demotion(
        self, enrolled_vm: VoiceAuthManager
    ) -> None:
        """Bất biến bảo vệ Chủ nhà: Cấm tuyệt đối hạ cấp tài khoản tuan_anh xuống Cấp 2 hoặc Cấp 3."""
        owner_wav = AUDIO_DIR / "giong_chu_nha_cap1_tuan_anh.wav"
        pcm_owner = _read_wav_pcm(owner_wav)

        demote_res = enrolled_vm.enroll_tier_voice_from_pcm16k(
            pcm_bytes=pcm_owner,
            user_id="tuan_anh",
            tier=2,
            role="MEMBER",
        )
        assert demote_res["ok"] is False
        assert demote_res["status"] == "TIER1_DEMOTION_FORBIDDEN"

    def test_intruder_voice_cannot_actuate_device_via_engine(
        self, enrolled_vm: VoiceAuthManager
    ) -> None:
        """Giọng người lạ tuyệt đối không thể kích hoạt thay đổi trạng thái thiết bị phần cứng."""
        engine = SmartHomeEngine()
        engine.devices["main_door"]["state"] = "CLOSED"

        intruder_wav = AUDIO_DIR / "giong_2_nguoi_la_mo_cua.wav"
        pcm_intruder = _read_wav_pcm(intruder_wav)

        exec_res = enrolled_vm.verify_and_execute_voice_command(
            pcm_intruder,
            "Mở cửa chính.",
            engine=engine,
        )
        assert exec_res["ok"] is False
        assert exec_res["auth"]["authorized"] is False
        assert engine.devices["main_door"]["state"] == "CLOSED"
        assert len(exec_res["device_results"]) == 0


# =============================================================================
# E. ORTHOGONAL TEST: TÍNH NHẤT QUÁN CSDL SQLITE KHI CẬP NHẬT TRẠNG THÁI LIÊN TỤC
# =============================================================================


class TestSqliteDatabaseStateConsistencyUnderConcurrency:
    """Kiểm thử tính nhất quán CSDL SQLite WAL dưới tải cập nhật liên tục và đa luồng đồng thời."""

    def test_sqlite_wal_mode_and_schema_integrity(self) -> None:
        """Kiểm tra SQLite ở chế độ toàn vẹn (integrity_check = ok) và hỗ trợ WAL / journaling."""
        assert DB_PATH.exists(), f"Không tìm thấy CSDL SQLite tại {DB_PATH}"
        conn = sqlite3.connect(str(DB_PATH))
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check")
            row = cur.fetchone()
            assert row is not None and row[0] == "ok", f"CSDL SQLite bị lỗi toàn vẹn: {row}"

            cur.execute("PRAGMA journal_mode")
            jrow = cur.fetchone()
            assert jrow is not None and jrow[0].lower() in ("wal", "delete", "memory")
        finally:
            conn.close()

    def test_rapid_device_state_toggles_sqlite_consistency(self) -> None:
        """5 thiết bị mục tiêu được bật/tắt liên tục 5 chu kỳ, CSDL SQLite đồng bộ chính xác 100%."""
        import asyncio
        engine = SmartHomeEngine()
        devices = ["main_door", "living_room_light", "bedroom_light", "fan", "ac"]

        for cycle in range(5):
            for dev in devices:
                act_on = "open" if dev == "main_door" else "turn_on"
                exp_on = "OPEN" if dev == "main_door" else "ON"
                asyncio.run(engine.execute_device_action(dev, act_on, source=f"test_rapid_toggle_cycle_{cycle}"))
                conn = sqlite3.connect(str(DB_PATH))
                try:
                    row = conn.execute("SELECT state FROM devices WHERE device_id = ?", (dev,)).fetchone()
                    assert row is not None and row[0] == exp_on, (
                        f"SQLite lệch trạng thái {dev}: mong đợi {exp_on}, nhận {row}"
                    )
                finally:
                    conn.close()

                act_off = "close" if dev == "main_door" else "turn_off"
                exp_off = "CLOSED" if dev == "main_door" else "OFF"
                asyncio.run(engine.execute_device_action(dev, act_off, source=f"test_rapid_toggle_cycle_{cycle}"))
                conn = sqlite3.connect(str(DB_PATH))
                try:
                    row = conn.execute("SELECT state FROM devices WHERE device_id = ?", (dev,)).fetchone()
                    assert row is not None and row[0] == exp_off, (
                        f"SQLite lệch trạng thái {dev}: mong đợi {exp_off}, nhận {row}"
                    )
                finally:
                    conn.close()

    def test_concurrent_multithreaded_device_actuation_zero_db_lock(self) -> None:
        """Mô phỏng 5 luồng worker đồng thời gửi 50 lệnh điều khiển, đảm bảo 0 lỗi database is locked."""
        import asyncio
        engine = SmartHomeEngine()
        devices = ["main_door", "living_room_light", "bedroom_light", "fan", "ac"]
        errors: list[Exception] = []

        def worker_task(tid: int) -> None:
            try:
                for step in range(10):
                    dev = devices[(tid + step) % len(devices)]
                    if dev == "main_door":
                        act = "open" if step % 2 == 0 else "close"
                    else:
                        act = "turn_on" if step % 2 == 0 else "turn_off"
                    asyncio.run(engine.execute_device_action(dev, act, source=f"thread_{tid}_step_{step}"))
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker_task, i) for i in range(5)]
            concurrent.futures.wait(futures)

        assert len(errors) == 0, f"Có lỗi xảy ra khi cập nhật đa luồng: {errors}"

        # Kiểm tra tính toàn vẹn CSDL sau stress test
        conn = sqlite3.connect(str(DB_PATH))
        try:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            for dev in devices:
                row = conn.execute("SELECT state FROM devices WHERE device_id = ?", (dev,)).fetchone()
                assert row is not None
                assert row[0] == engine.devices[dev]["state"], (
                    f"SQLite không đồng bộ với Engine cho {dev}: DB={row[0]}, Engine={engine.devices[dev]['state']}"
                )
        finally:
            conn.close()
