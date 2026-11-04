"""Bộ Kiểm Thử Đối Kháng Thực Nghiệm (Empirical Adversarial Test Suite) Milestone M4.

Người thực hiện: challenger_m4_2 (Role: M4 Security Challenger)
Mục tiêu kiểm định độc lập:
1. Fuzzing đầu vào target_window tại endpoint /api/auth3/guest_qr_handshake:
   - Các vector dị biệt: "abc", "{}", "-1", "null", "NaN", "1e99", "", ký tự đặc biệt, 10**100, float, structures.
   - Xác nhận HTTP 400 Bad Request hoặc HTTP 401 Unauthorized theo chuẩn, 0 unhandled crash HTTP 500.
2. Kiểm thử đối kháng vòng đời kết nối WebSocket /ws:
   - Mô phỏng 10 kết nối tuần tự và 10 kết nối song song, sau đó ngắt kết nối đột ngột (abrupt drop).
   - Kiểm tra rò rỉ phiên ma (ghost sessions): len(_ACTIVE_BRIDGES) trở về 0 khi tất cả socket đóng.
3. Kiểm thử phục vụ tài nguyên tĩnh:
   - Kiểm tra 18 routes (6 HTML, 6 CSS, 6 JS) trả về HTTP 200 OK với đúng Content-Type.
   - Kiểm tra tính thuần khiết của 6 tệp HTML: 0 thẻ <style> và 0 inline <script>.
"""

from __future__ import annotations

import base64
import concurrent.futures
import pathlib
import re
import sys
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.auth_3layer import get_auth_3layer_manager
from simulator.server import _ACTIVE_BRIDGES, _BOOT_VOICE_AUTH, app


@pytest.fixture(autouse=True)
def clean_system_state():
    """Làm sạch bộ nhớ đệm token, phiên ma active bridges và reset voice auth."""
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
# 1. KIỂM THỬ ĐỐI KHÁNG FUZZING ĐẦU VÀO TARGET_WINDOW (ENDPOINT /api/auth3/guest_qr_handshake)
# =============================================================================


class TestTargetWindowFuzzingAdversarial:
    """Kiểm thử Fuzzing đối kháng đầu vào target_window nhằm kích nổ các lỗi ép kiểu unhandled ValueError/TypeError."""

    @pytest.mark.parametrize(
        "malformed_input",
        [
            "abc",
            "{}",
            "null",
            "NaN",
            "NAN",
            "Infinity",
            "-Infinity",
            "1e99",
            "1e+100",
            "0x10",
            "\x00",
            "' OR 1=1; --",
            "!@#$%^&*()_+-=[]{}|;:,.<>?/",
            "invalid_window_string",
            "12.345",
            [1, 2, 3],
            {"nested": "object"},
            "9" * 5000,  # Vượt trần giới hạn chuyển đổi số nguyên trong Python 3.11+
        ],
    )
    def test_target_window_malformed_string_types_rejected_400(
        self, client: TestClient, malformed_input: Any
    ) -> None:
        """Gửi các giá trị chuỗi/cấu trúc dị biệt vào target_window:

        BẮT BUỘC nhận HTTP 400 Bad Request, TUYỆT ĐỐI KHÔNG phát sinh crash HTTP 500.
        """
        resp = client.post(
            "/api/auth3/guest_qr_handshake",
            json={
                "token": "simulated_token_fuzzing",
                "target_window": malformed_input,
                "duration": "1d",
            },
        )
        assert resp.status_code == 400, (
            f"Fuzz vector '{malformed_input}' trả về {resp.status_code} thay vì 400 Bad Request!"
        )
        data = resp.json()
        assert data.get("ok") is False
        assert "không hợp lệ" in data.get("error", "")

    @pytest.mark.parametrize(
        "out_of_bounds_input",
        [
            "-1",
            -1,
            "-999999",
            str(10**100),
            10**100,
        ],
    )
    def test_target_window_out_of_bounds_rejected_401(
        self, client: TestClient, out_of_bounds_input: Any
    ) -> None:
        """Gửi các giá trị số nguyên âm hoặc siêu lớn (out of bounds) vào target_window:

        BẮT BUỘC nhận HTTP 401 Unauthorized (do lệch cửa sổ TOTP hoặc token không hợp lệ),
        TUYỆT ĐỐI KHÔNG crash HTTP 500.
        """
        resp = client.post(
            "/api/auth3/guest_qr_handshake",
            json={
                "token": "simulated_token_bounds",
                "target_window": out_of_bounds_input,
                "duration": "1d",
            },
        )
        assert resp.status_code == 401, (
            f"Bounds vector '{out_of_bounds_input}' trả về {resp.status_code} thay vì 401 Unauthorized!"
        )
        data = resp.json()
        assert data.get("ok") is False

    def test_target_window_empty_and_none_graceful_handling(
        self, client: TestClient
    ) -> None:
        """Gửi target_window là chuỗi rỗng '' hoặc None:

        Hệ thống phân giải thành None an toàn, không phát sinh ngoại lệ HTTP 500.
        """
        for empty_val in ("", "   ", None):
            resp = client.post(
                "/api/auth3/guest_qr_handshake",
                json={
                    "token": "bogus_token",
                    "target_window": empty_val,
                    "duration": "1d",
                },
            )
            # Với token giả, trả về 401 hợp lệ
            assert resp.status_code == 401
            assert resp.json().get("ok") is False

    def test_fuzzing_against_valid_server_generated_token(
        self, client: TestClient
    ) -> None:
        """Kiểm thử tương tác đối kháng giữa một mã token THẬT (do server vừa sinh) và các vector target_window dị biệt."""
        cur = client.get("/api/auth3/guest_qr_current?duration=1d").json()
        assert cur.get("ok") is True
        real_tok = cur["token"]
        real_win = cur["window"]

        # 1. Thử gửi target_window chuỗi dị thường với token thật -> 400 Bad Request
        for bad_str in ["abc", "{}", "null", "NaN", "1e99"]:
            r = client.post(
                "/api/auth3/guest_qr_handshake",
                json={
                    "token": real_tok,
                    "target_window": bad_str,
                    "duration": "1d",
                },
            )
            assert r.status_code == 400, (
                f"Expected 400 for bad string '{bad_str}', got {r.status_code}"
            )
            assert "không hợp lệ" in r.json().get("error", "")

        # 2. Thử gửi target_window số âm hoặc sai lệch với token thật -> 401 Unauthorized
        for bad_win in [-1, real_win + 5, real_win - 5, str(10**100)]:
            r = client.post(
                "/api/auth3/guest_qr_handshake",
                json={
                    "token": real_tok,
                    "target_window": bad_win,
                    "duration": "1d",
                },
            )
            assert r.status_code == 401, (
                f"Expected 401 for mismatched window '{bad_win}', got {r.status_code}"
            )
            assert "không khớp" in r.json().get("error", "")

        # 3. Thử bắt tay chuẩn với window chính xác -> 200 OK
        r_ok = client.post(
            "/api/auth3/guest_qr_handshake",
            json={
                "token": real_tok,
                "target_window": real_win,
                "duration": "1d",
            },
        )
        assert r_ok.status_code == 200
        data_ok = r_ok.json()
        assert data_ok.get("ok") is True
        assert "guest_session_id" in data_ok

        # 4. Thử replay lại token vừa đốt -> 400 Bad Request (Single-Use Token)
        r_replay = client.post(
            "/api/auth3/guest_qr_handshake",
            json={
                "token": real_tok,
                "target_window": real_win,
                "duration": "1d",
            },
        )
        assert r_replay.status_code == 400
        assert "Single-Use" in r_replay.json().get("error", "") or "đã được sử dụng" in r_replay.json().get("error", "")


# =============================================================================
# 2. KIỂM THỬ ĐỐI KHÁNG VÒNG ĐỜI KẾT NỐI WEBSOCKET /WS & RÒ RỈ PHIÊN MA
# =============================================================================


class TestWebSocketLifecycleAndGhostSessionLeaks:
    """Kiểm thử vòng đời kết nối WebSocket, chống rò rỉ phiên ma (Ghost Sessions) và chống nhân đôi đăng ký."""

    def test_websocket_sequential_10_connections_abrupt_disconnect(
        self, client: TestClient
    ) -> None:
        """Mô phỏng 10 kết nối WebSocket tuần tự:

        - Mỗi kết nối mở ra chỉ được đăng ký đúng 1 lần (len = 1).
        - Ngắt kết nối đột ngột (drop socket không qua close frame).
        - Xác nhận dọn sạch 100%, len(_ACTIVE_BRIDGES) trở về 0 sau mỗi lần ngắt.
        """
        assert len(_ACTIVE_BRIDGES) == 0

        for cycle in range(10):
            with client.websocket_connect("/ws") as ws:
                # Xác nhận mỗi kết nối chỉ xuất hiện duy nhất 1 lần trong _ACTIVE_BRIDGES
                assert len(_ACTIVE_BRIDGES) == 1, (
                    f"Chu kỳ {cycle}: Phát hiện nhân đôi đăng ký! len={len(_ACTIVE_BRIDGES)}"
                )
                init_msg = ws.receive_json()
                assert init_msg.get("type") == "state_snapshot"

            # Ngay sau khi khối with kết thúc (abrupt drop), session phải bị xóa hoàn toàn
            assert len(_ACTIVE_BRIDGES) == 0, (
                f"Chu kỳ {cycle}: Rò rỉ phiên ma! len={len(_ACTIVE_BRIDGES)}"
            )

    def test_websocket_parallel_10_connections_abrupt_disconnect(
        self, client: TestClient
    ) -> None:
        """Mô phỏng 10 kết nối WebSocket mở song song đồng thời:

        - 10 kết nối đồng thời -> len(_ACTIVE_BRIDGES) == 10.
        - Toàn bộ 10 socket bị ngắt kết nối đột ngột.
        - Xác nhận len(_ACTIVE_BRIDGES) trở về đúng 0, không còn bất kỳ phiên ma nào.
        """
        assert len(_ACTIVE_BRIDGES) == 0
        open_sockets = []

        try:
            for i in range(10):
                ctx = client.websocket_connect("/ws")
                ws = ctx.__enter__()
                open_sockets.append((ctx, ws))
                assert len(_ACTIVE_BRIDGES) == i + 1

            assert len(_ACTIVE_BRIDGES) == 10, (
                f"Kỳ vọng 10 active bridges song song, nhận {len(_ACTIVE_BRIDGES)}"
            )
        finally:
            # Ngắt đột ngột toàn bộ 10 kết nối
            for ctx, ws in open_sockets:
                try:
                    ctx.__exit__(None, None, None)
                except Exception:
                    pass

        # Kiểm định sau khi ngắt kết nối
        assert len(_ACTIVE_BRIDGES) == 0, (
            f"Phát hiện rò rỉ phiên ma sau khi đóng 10 socket song song! len={len(_ACTIVE_BRIDGES)}"
        )

    def test_websocket_concurrent_threadpool_abrupt_disconnects(
        self, client: TestClient
    ) -> None:
        """Kiểm thử đa luồng (Multi-Threaded Concurrency):

        - 20 tác vụ kết nối và ngắt đột ngột chạy song song trên ThreadPoolExecutor (10 workers).
        - Kiểm tra tính an toàn ren (Thread Safety) và cơ chế xóa triệt để vòng lặp while trong finally.
        """
        assert len(_ACTIVE_BRIDGES) == 0

        def thread_task(task_id: int) -> None:
            with client.websocket_connect("/ws") as ws:
                msg = ws.receive_json()
                assert msg.get("type") == "state_snapshot"
                # Đột ngột thoát không đợi close frame

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(thread_task, i) for i in range(20)]
            for fut in concurrent.futures.as_completed(futures):
                fut.result()

        assert len(_ACTIVE_BRIDGES) == 0, (
            f"Phát hiện rò rỉ phiên ma trong kiểm thử ThreadPool! len={len(_ACTIVE_BRIDGES)}"
        )

    def test_websocket_abrupt_disconnect_during_in_flight_streaming(
        self, client: TestClient
    ) -> None:
        """Mô phỏng client gửi dữ liệu âm thanh vào hàng đợi In-Flight buffer rồi ngắt socket đột ngột:

        - Kiểm tra session._closed được bật thành True.
        - Hàng đợi buffer và bridge bị giải phóng sạch sẽ khỏi _ACTIVE_BRIDGES.
        """
        assert len(_ACTIVE_BRIDGES) == 0
        silence_chunk = base64.b64encode(b"\x00\x00" * 320).decode("ascii")

        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # state_snapshot
            ws.receive_json()  # system_prompt_updated
            ws.receive_json()  # gemini_status

            session = _ACTIVE_BRIDGES[-1]
            assert session._closed is False

            # Bơm 20 chunks
            for _ in range(20):
                ws.send_json({
                    "type": "mic_chunk",
                    "pcm16k_b64": silence_chunk,
                    "is_speech": True,
                })

            time.sleep(0.05)
            # Socket bị ngắt đột ngột ngay tại đây

        assert session._closed is True
        assert len(_ACTIVE_BRIDGES) == 0


# =============================================================================
# 3. KIỂM THỬ PHỤC VỤ TÀI NGUYÊN TĨNH (18 ROUTES: 6 HTML, 6 CSS, 6 JS)
# =============================================================================


class TestStaticResourceServingAndContentTypes:
    """Kiểm thử phục vụ 18 routes tài nguyên tĩnh (6 HTML, 6 CSS, 6 JS) trả về HTTP 200 OK kèm đúng Content-Type."""

    ROUTES_SPEC = [
        # 6 Trang HTML
        ("/", "text/html"),
        ("/auth", "text/html"),
        ("/guest_enroll", "text/html"),
        ("/wokwi", "text/html"),
        ("/logs", "text/html"),
        ("/app", "text/html"),
        # 6 Tệp CSS độc lập
        ("/static/css/style.css", "text/css"),
        ("/static/css/auth.css", "text/css"),
        ("/static/css/guest_enroll.css", "text/css"),
        ("/static/css/wokwi.css", "text/css"),
        ("/static/css/logs.css", "text/css"),
        ("/static/css/mobile_app.css", "text/css"),
        # 6 Tệp JavaScript độc lập
        ("/static/js/app.js", ("application/javascript", "text/javascript")),
        ("/static/js/auth.js", ("application/javascript", "text/javascript")),
        ("/static/js/guest_enroll.js", ("application/javascript", "text/javascript")),
        ("/static/js/wokwi.js", ("application/javascript", "text/javascript")),
        ("/static/js/logs.js", ("application/javascript", "text/javascript")),
        ("/static/js/mobile_app.js", ("application/javascript", "text/javascript")),
    ]

    @pytest.mark.parametrize("route_path,expected_mime", ROUTES_SPEC)
    def test_static_route_returns_200_and_correct_content_type(
        self, client: TestClient, route_path: str, expected_mime: Any
    ) -> None:
        """Kiểm tra từng route trả về HTTP 200 OK và Content-Type phù hợp."""
        resp = client.get(route_path)
        assert resp.status_code == 200, (
            f"Route '{route_path}' trả về HTTP {resp.status_code} thay vì 200 OK!"
        )

        content_type = resp.headers.get("content-type", "").lower()
        if isinstance(expected_mime, tuple):
            assert any(m in content_type for m in expected_mime), (
                f"Route '{route_path}' có Content-Type '{content_type}' không khớp các định dạng {expected_mime}"
            )
        else:
            assert expected_mime in content_type, (
                f"Route '{route_path}' có Content-Type '{content_type}' không chứa '{expected_mime}'"
            )

        # Xác nhận nội dung phản hồi không rỗng
        assert len(resp.content) > 100, f"Route '{route_path}' trả về nội dung rỗng hoặc quá ngắn!"

    def test_html_files_cleanliness_zero_inline_styles_and_scripts(self) -> None:
        """Kiểm định tĩnh trực tiếp trên đĩa:

        6 tệp HTML bắt buộc không chứa bất kỳ thẻ <style> hoặc inline <script> nào (100% bóc tách).
        """
        html_files = [
            ROOT / "simulator" / "static" / "index.html",
            ROOT / "simulator" / "static" / "auth.html",
            ROOT / "simulator" / "static" / "guest_enroll.html",
            ROOT / "simulator" / "static" / "wokwi.html",
            ROOT / "simulator" / "static" / "logs.html",
            ROOT / "mobile_app" / "index.html",
        ]

        for file_path in html_files:
            assert file_path.exists(), f"File {file_path} không tồn tại trên đĩa!"
            raw_content = file_path.read_text(encoding="utf-8")

            # 1. Quét thẻ <style>
            style_matches = re.findall(r"<style\b", raw_content, re.IGNORECASE)
            assert len(style_matches) == 0, (
                f"Tệp {file_path.name} vẫn còn {len(style_matches)} thẻ <style> inline!"
            )

            # 2. Quét các thẻ <script> không có thuộc tính src
            script_tags = re.findall(r"<script\b([^>]*)>", raw_content, re.IGNORECASE)
            inline_scripts = [s for s in script_tags if "src=" not in s.lower()]
            assert len(inline_scripts) == 0, (
                f"Tệp {file_path.name} vẫn còn {len(inline_scripts)} khối inline <script>!"
            )
