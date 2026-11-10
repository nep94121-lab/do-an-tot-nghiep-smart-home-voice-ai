"""Bộ Kiểm Thử Đối Kháng Thực Nghiệm (Adversarial Empirical Stress-Test) Milestone M3.

Người thực hiện: challenger_m3_2 (Role: M3 Security & Live Challenger)
Mục tiêu kiểm định:
1. Tấn công đối kháng TOTP Handshake (Window Forgery, Garbage Token, Random Nonce, Replay Attack).
2. Kiểm thử WebSocket /ws, In-Flight Buffer & Reconnect Resilience.
"""

from __future__ import annotations

import base64
import os
import pathlib
import sys
import time
import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.server import _BOOT_VOICE_AUTH, _ACTIVE_BRIDGES, app
from simulator.auth_3layer import get_auth_3layer_manager


@pytest.fixture(autouse=True)
def clean_state():
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
    return TestClient(app, raise_server_exceptions=False)


# =============================================================================
# 1. KIỂM THỬ ĐỐI KHÁNG TOTP HANDSHAKE
# =============================================================================

class TestTOTPHandshakeAdversarial:
    """Tấn công đối kháng TOTP Handshake:
    - Thử nghiệm vượt mặt qua target_window bịa đặt với các vector: window hiện tại, quá khứ, tương lai, âm, chuỗi chữ.
    - Thử nghiệm gửi token rác, nonce ngẫu nhiên, token đã bị burn (Replay).
    """

    def test_valid_handshake_succeeds(self, client: TestClient) -> None:
        """Token hợp lệ sinh ra từ server phải handshake thành công (HTTP 200)."""
        cur = client.get(
            "/api/auth3/guest_qr_current?duration=1d",
            headers={"Authorization": "Bearer sess_owner_t1_nep94121"},
        )
        assert cur.status_code == 200
        tok = cur.json()["token"]
        win = cur.json()["window"]

        # Handshake với token hợp lệ và window đúng
        hs = client.post("/api/auth3/guest_qr_handshake", json={
            "token": tok,
            "target_window": win,
            "duration": "1d",
        })
        assert hs.status_code == 200
        data = hs.json()
        assert data["ok"] is True
        assert "guest_session_id" in data
        assert data["session"]["lock_ttl_sec"] == 180

    def test_forged_target_window_with_bogus_token_rejected_401(self, client: TestClient) -> None:
        """Kẻ tấn công gửi token bịa đặt kèm các vector target_window:
        - window hiện tại
        - window quá khứ (-1000)
        - window tương lai (+1000)
        - window âm (-1, -99999)
        Tất cả BẮT BUỘC bị từ chối 100% với HTTP 401.
        """
        cur_win = int(time.time() // 10)
        test_windows = [
            ("cur_window", cur_win),
            ("past_window_1000", cur_win - 1000),
            ("future_window_1000", cur_win + 1000),
            ("negative_window_minus_1", -1),
            ("negative_window_minus_99999", -99999),
        ]

        for label, w_val in test_windows:
            res = client.post("/api/auth3/guest_qr_handshake", json={
                "token": f"forged_token_{label}",
                "target_window": w_val,
                "duration": "1d",
            })
            assert res.status_code == 401, f"Thất bại tại vector {label}: status={res.status_code}"
            assert res.json()["ok"] is False
            assert "không hợp lệ hoặc đã hết hạn" in res.json()["error"]

    def test_genuine_token_with_mismatched_target_window_rejected_401(self, client: TestClient) -> None:
        """Token thật nhưng bị gửi kèm target_window bịa đặt/sai lệch -> Bị từ chối với HTTP 401."""
        cur = client.get(
            "/api/auth3/guest_qr_current?duration=1d",
            headers={"Authorization": "Bearer sess_owner_t1_nep94121"},
        ).json()
        tok = cur["token"]
        real_win = cur["window"]

        res = client.post("/api/auth3/guest_qr_handshake", json={
            "token": tok,
            "target_window": real_win + 5,
            "duration": "1d",
        })
        assert res.status_code == 401
        assert res.json()["ok"] is False
        assert "không khớp thông số cửa sổ thời gian" in res.json()["error"]

    def test_garbage_tokens_and_random_nonces_rejected_401(self, client: TestClient) -> None:
        """Token rác, SQL injection string, và nonce ngẫu nhiên -> Bị từ chối với HTTP 401."""
        garbage_vectors = [
            "trash_token_xyz",
            "0000000000000000",
            "'; DROP TABLE smarthome;--",
            "<script>alert(1)</script>",
            os.urandom(8).hex(),
            os.urandom(16).hex(),
        ]

        for g_tok in garbage_vectors:
            res = client.post("/api/auth3/guest_qr_handshake", json={
                "token": g_tok,
                "duration": "1d",
            })
            assert res.status_code == 401
            assert res.json()["ok"] is False
            assert "không hợp lệ hoặc đã hết hạn" in res.json()["error"]

    def test_replay_attack_burnt_token_rejected_400(self, client: TestClient) -> None:
        """Tấn công Replay: Token đã bị đốt (burned) sau lần handshake đầu tiên.
        Lần 2, 3 bắt buộc bị từ chối với HTTP 400 (Single-Use Token).
        """
        cur = client.get(
            "/api/auth3/guest_qr_current?duration=1d",
            headers={"Authorization": "Bearer sess_owner_t1_nep94121"},
        ).json()
        tok = cur["token"]

        # Lần 1: Thành công
        r1 = client.post("/api/auth3/guest_qr_handshake", json={"token": tok, "duration": "1d"})
        assert r1.status_code == 200
        assert r1.json()["ok"] is True

        # Lần 2 (Replay cùng tham số): Bị từ chối 400
        r2 = client.post("/api/auth3/guest_qr_handshake", json={"token": tok, "duration": "1d"})
        assert r2.status_code == 400
        assert r2.json()["ok"] is False
        assert "Single-Use" in r2.json()["error"] or "đã được sử dụng" in r2.json()["error"]

        # Lần 3 (Replay kèm target_window bịa đặt): Bị từ chối 400
        r3 = client.post("/api/auth3/guest_qr_handshake", json={
            "token": tok,
            "target_window": int(time.time() // 10) + 10,
            "duration": "1y",
        })
        assert r3.status_code == 400
        assert r3.json()["ok"] is False

    def test_empty_token_rejected_400(self, client: TestClient) -> None:
        """Token rỗng bị từ chối ngay với HTTP 400."""
        r = client.post("/api/auth3/guest_qr_handshake", json={"token": "", "duration": "1d"})
        assert r.status_code == 400
        assert r.json()["ok"] is False
        assert "Thiếu mã token" in r.json()["error"]

    def test_string_target_window_vulnerability_finding(self, client: TestClient) -> None:
        """CHALLENGER DEFECT FINDING:
        Khi client gửi target_window là chuỗi ký tự ('abc', 'invalid_win', '12.34', '{}'),
        hàm api_auth3_guest_qr_handshake (routes_qr.py:150) thực hiện int(target_window)
        mà không bắt ngoại lệ ValueError -> Gây ra HTTP 500 Internal Server Error (crash endpoint)
        thay vì chặn bằng HTTP 400 Bad Request hoặc HTTP 401.
        """
        for malformed_win in ["abc", "invalid_win", "12.34"]:
            res = client.post("/api/auth3/guest_qr_handshake", json={
                "token": "test_token",
                "target_window": malformed_win,
            })
            # Xác nhận Defect 1 đã được vá: trả về 400 Bad Request thay vì crash 500
            assert res.status_code == 400, f"Expected 400 Bad Request due to sanitized ValueError in routes_qr.py:150, got {res.status_code}"


# =============================================================================
# 2. KIỂM THỬ WEBSOCKET /WS & IN-FLIGHT BUFFER
# =============================================================================

class TestWebSocketLiveAndBuffer:
    """Kiểm thử WebSocket /ws & In-Flight Buffer:
    - Tiếp nhận chunk PCM 16kHz ngắn, chunk im lặng, câu thoại tiếng Việt hợp lệ.
    - Kiểm tra cơ chế hàng đợi In-Flight buffer khi upstream ngắt kết nối.
    - Kiểm tra chu trình kết nối / ngắt kết nối và cơ chế giải phóng session.
    """

    def test_websocket_initial_handshake_protocol(self, client: TestClient) -> None:
        """Kết nối WebSocket tới /ws nhận đủ 3 thông điệp khởi tạo:
        1. state_snapshot
        2. system_prompt_updated
        3. gemini_status
        """
        with client.websocket_connect("/ws") as ws:
            m1 = ws.receive_json()
            assert m1.get("type") == "state_snapshot"
            assert "devices" in m1.get("snapshot", {})

            m2 = ws.receive_json()
            assert m2.get("type") == "system_prompt_updated"
            assert len(m2.get("system_prompt", "")) > 100

            m3 = ws.receive_json()
            assert m3.get("type") == "gemini_status"

    def test_websocket_silence_and_short_pcm_chunks(self, client: TestClient) -> None:
        """Gửi chunk im lặng và chunk âm thanh PCM 16kHz ngắn (20ms = 320 samples) qua WebSocket."""
        with client.websocket_connect("/ws") as ws:
            # Drain initial msgs
            ws.receive_json()
            ws.receive_json()
            ws.receive_json()

            # Gửi chunk im lặng (is_speech = False)
            silence_bytes = b"\x00\x00" * 320
            ws.send_json({
                "type": "mic_chunk",
                "pcm16k_b64": base64.b64encode(silence_bytes).decode("ascii"),
                "is_speech": False,
            })

            # Gửi chunk giọng nói ngắn 20ms (is_speech = True)
            t = np.linspace(0, 0.02, 320, endpoint=False)
            voice_bytes = (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16).tobytes()
            ws.send_json({
                "type": "mic_chunk",
                "pcm16k_b64": base64.b64encode(voice_bytes).decode("ascii"),
                "is_speech": True,
            })

            # Gửi mic_speech_ended
            ws.send_json({"type": "mic_speech_ended"})
            resp = ws.receive_json()
            assert resp.get("type") in ("speech_ended_marker", "voice_auth_rejected", "voice_auth_result")

    def test_websocket_valid_vietnamese_command_offline_mode(self, client: TestClient) -> None:
        """Gửi lệnh thoại tiếng Việt hợp lệ qua WebSocket (chế độ offline để test toàn vẹn Actuate-First)."""
        with client.websocket_connect("/ws") as ws:
            # Drain initial msgs
            ws.receive_json()
            ws.receive_json()
            ws.receive_json()

            # Chuyển sang chế độ offline
            ws.send_json({"type": "set_server_mode", "server_connected": False})

            # Gửi lệnh tiếng Việt "Bật đèn phòng khách"
            ws.send_json({"type": "send_text", "text": "Bật đèn phòng khách"})

            # Lắng nghe phản hồi cho đến khi hoàn thành lượt turn_complete
            events = []
            while True:
                msg = ws.receive_json()
                events.append(msg.get("type"))
                if msg.get("type") == "turn_complete":
                    assert "Bật đèn phòng khách" in msg.get("heard", "")
                    assert "đèn phòng khách" in msg.get("said", "").lower()
                    break

            assert "tool_call_executed" in events
            assert "output_transcription" in events
            assert "turn_complete" in events

            # Khôi phục lại chế độ online cho các bài test tiếp theo
            ws.send_json({"type": "set_server_mode", "server_connected": True})

    def test_in_flight_buffer_queuing_and_capacity(self, client: TestClient) -> None:
        """Kiểm tra hàng đợi In-Flight buffer:
        - Khi gemini_session = None (upstream chưa kết nối hoặc đang reconnect), các chunk được đệm vào _mic_in_flight_queue.
        - Sức chứa maxsize=100 được duy trì an toàn, không bị tràn bộ nhớ hoặc treo tiến trình.
        """
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.receive_json()
            ws.receive_json()

            # Lấy đối tượng session từ _ACTIVE_BRIDGES
            session = _ACTIVE_BRIDGES[-1]
            session.gemini_session = None  # Giả lập trạng thái upstream disconnect

            chunk = base64.b64encode(b"\x05\x00" * 320).decode("ascii")

            # Gửi 10 chunks
            for _ in range(10):
                ws.send_json({"type": "mic_chunk", "pcm16k_b64": chunk, "is_speech": True})

            time.sleep(0.15)
            assert session._mic_in_flight_queue.qsize() == 10

            # Gửi thêm 120 chunks để test vượt trần maxsize (100)
            for _ in range(120):
                ws.send_json({"type": "mic_chunk", "pcm16k_b64": chunk, "is_speech": True})

            time.sleep(0.15)
            # Hàng đợi phải đạt trần 100 và không làm treo kết nối
            assert session._mic_in_flight_queue.qsize() == 100

    def test_websocket_disconnect_double_registration_leak_finding(self, client: TestClient) -> None:
        """CHALLENGER DEFECT FINDING:
        Khi client kết nối WebSocket tới /ws:
        - LiveBridgeSession.__init__ gọi _ACTIVE_BRIDGES.append(self) (gemini_bridge.py:176)
        - websocket_endpoint gọi tiếp _ACTIVE_BRIDGES.append(session) (server.py:171)
        Do đó mỗi kết nối bị đăng ký 2 lần vào danh sách _ACTIVE_BRIDGES.
        Khi ngắt kết nối, khối finally chỉ remove 1 lần:
        _ACTIVE_BRIDGES.remove(session) -> Vẫn còn 1 phiên ma (ghost session) tồn đọng vĩnh viễn!
        """
        _ACTIVE_BRIDGES.clear()
        assert len(_ACTIVE_BRIDGES) == 0

        # Chu kỳ 1: Kết nối và ngắt - xác nhận chỉ đăng ký 1 lần duy nhất
        with client.websocket_connect("/ws") as ws:
            assert len(_ACTIVE_BRIDGES) == 1, f"Expected 1 registration (fixed double append), got {len(_ACTIVE_BRIDGES)}"

        # Sau khi ngắt: Dọn sạch hoàn toàn 100%, không còn phiên ma
        assert len(_ACTIVE_BRIDGES) == 0, f"Expected 0 ghost sessions, got {len(_ACTIVE_BRIDGES)}"

        # Chu kỳ 2: Kết nối và ngắt lần 2
        with client.websocket_connect("/ws") as ws:
            assert len(_ACTIVE_BRIDGES) == 1, f"Expected 1 registration, got {len(_ACTIVE_BRIDGES)}"

        # Sau chu kỳ 2: Tiếp tục dọn sạch
        assert len(_ACTIVE_BRIDGES) == 0, f"Expected 0 ghost sessions, got {len(_ACTIVE_BRIDGES)}"
