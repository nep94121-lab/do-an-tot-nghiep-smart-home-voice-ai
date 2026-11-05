"""Challenger 2 Empirical Verification Suite: Milestone 2 (Phase 6).

Adversarial Stress-Testing for:
1. Double-firing trigger inspection:
   - Form submit listeners do NOT call button.click().
   - Form submission handlers do NOT cause recursive calls or double submissions.
   - Elimination of duplicate inline onclick / onsubmit in HTML.
2. inFlight and disabled state verification:
   - Buttons #btnSubmitGateLogin, #btnSubmitGateRegister, #btnSubmitForgotReset, #btnSendForgotOtp
     set disabled=true during requests.
   - State and label restored in try...finally.
   - inFlight guards prevent concurrent re-entrancy.
3. Visual countdown on #btnSendForgotOtp:
   - setInterval logic, decrement per second, remaining seconds format, restoration after 60s.
   - Error and exception restoration without hanging timer.
4. Boundary tests for backend cooldown (exact boundaries via time.time patching):
   - t=0.0s, t=30.0s, t=59.0s, t=59.9s, t=60.0s, t=61.0s.
   - Chained multi-cycle cooldown transitions.
   - Case-insensitive email normalization cooldown mapping.
   - Concurrency stress harness.
"""

from __future__ import annotations

import concurrent.futures
import os
import pathlib
import re
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from simulator.auth_3layer import ThreeLayerAuthManager
from simulator.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clean_otp_state():
    from simulator.api.routes_auth import get_auth_3layer_manager

    mgr = get_auth_3layer_manager()
    lock = getattr(mgr, "_otp_lock", threading.Lock())
    with lock:
        mgr.pending_otps.clear()
    yield
    with lock:
        mgr.pending_otps.clear()


@pytest.fixture
def auth_mgr() -> ThreeLayerAuthManager:
    from simulator.api.routes_auth import get_auth_3layer_manager

    return get_auth_3layer_manager()


# =============================================================================
# 1. FRONTEND DOUBLE-FIRING & RECURSION ELIMINATION TESTS
# =============================================================================

class TestFrontendDoubleFiringAndTriggers:
    """Kiểm tra đối kháng hiện tượng kích hoạt kép (double-firing) và đệ quy (recursion)."""

    def test_app_js_no_button_click_in_submit_handlers(self):
        """Đảm bảo không có bất kỳ submit handler nào gọi button.click() trong app.js."""
        app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
        assert app_js_path.exists(), "app.js must exist"
        content = app_js_path.read_text(encoding="utf-8")

        # Loại bỏ comment trước khi phân tích để tránh false positive từ comment lịch sử
        code_without_comments = re.sub(r"//.*", "", content)
        code_without_comments = re.sub(r"/\*.*?\*/", "", code_without_comments, flags=re.DOTALL)

        # Kiểm tra không có lời gọi .click() cho các nút submit gate
        forbidden_calls = [
            "btnSubmitGateLogin.click()",
            "btnSubmitGateRegister.click()",
            "btnSubmitForgotReset.click()",
            "btnSendForgotOtp.click()",
        ]
        for call in forbidden_calls:
            assert call not in code_without_comments, f"Phát hiện lời gọi cấm {call} trong mã nguồn thực thi của app.js!"

        # Kiểm tra submit listeners không bọc button.click()
        submit_listener_matches = re.findall(
            r'addEventListener\(\s*["\']submit["\'],\s*(?:function|\(.*?\)\s*=>)\s*\{([^}]*)\}',
            code_without_comments,
        )
        for block in submit_listener_matches:
            assert ".click()" not in block, f"Submit listener chứa lời gọi .click(): {block}"

    def test_app_js_submit_handlers_call_prevent_default(self):
        """Các hàm xử lý submit form gate bắt buộc phải gọi preventDefault() để chặn reload trang."""
        app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
        content = app_js_path.read_text(encoding="utf-8")

        handlers = [
            ("handleGateLoginSubmit", content.find("function handleGateLoginSubmit")),
            ("handleGateRegisterSubmit", content.find("function handleGateRegisterSubmit")),
            ("handleForgotResetSubmit", content.find("function handleForgotResetSubmit")),
        ]

        for name, idx in handlers:
            assert idx != -1, f"Không tìm thấy hàm {name} trong app.js"
            fn_chunk = content[idx : idx + 300]
            assert "preventDefault" in fn_chunk, f"Hàm {name} không gọi preventDefault() ở đầu hàm!"

    def test_index_html_no_duplicate_inline_handlers(self):
        """Kiểm tra file index.html không chứa thuộc tính onclick trùng lặp với submit handler."""
        html_path = ROOT / "simulator" / "static" / "index.html"
        assert html_path.exists(), "index.html must exist"
        html = html_path.read_text(encoding="utf-8")

        # Nút #btnLockdownUnlock không được vừa có inline onclick vừa nằm trong form có onsubmit
        lockdown_btn_match = re.search(r'<button[^>]*id=["\']btnLockdownUnlock["\'][^>]*>', html)
        assert lockdown_btn_match is not None
        assert "onclick" not in lockdown_btn_match.group(0), (
            "#btnLockdownUnlock không được có inline onclick vì form cha lockdownForm đã có onsubmit!"
        )


# =============================================================================
# 2. INFLIGHT AND DISABLED STATE VERIFICATION TESTS
# =============================================================================

class TestInFlightAndDisabledState:
    """Kiểm tra đối kháng cơ chế khóa nút bấm (disabled) và cờ inFlight."""

    def test_all_auth_buttons_have_inflight_and_disabled_guarantees(self):
        """Mọi nút submit và OTP đều được bảo vệ bởi inFlight flag và try...finally disable."""
        app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
        content = app_js_path.read_text(encoding="utf-8")

        button_checks = [
            {
                "name": "btnSubmitGateLogin",
                "inflight_flag": "isGateLoginInFlight",
                "fn_name": "handleGateLoginSubmit",
            },
            {
                "name": "btnSubmitGateRegister",
                "inflight_flag": "isGateRegisterInFlight",
                "fn_name": "handleGateRegisterSubmit",
            },
            {
                "name": "btnSubmitForgotReset",
                "inflight_flag": "isGateForgotInFlight",
                "fn_name": "handleForgotResetSubmit",
            },
            {
                "name": "btnSendForgotOtp",
                "inflight_flag": "isSendingForgotOtp",
                "fn_name": "btnSendForgotOtp",
            },
        ]

        for check in button_checks:
            idx = content.find(check["fn_name"])
            assert idx != -1, f"Không tìm thấy {check['fn_name']} trong app.js"
            block = content[idx : idx + 3000]

            # 1. Kiểm tra guard early return nếu inFlight đang true
            guard_pattern = rf"if\s*\(\s*{check['inflight_flag']}\s*\)\s*return"
            assert re.search(guard_pattern, block) is not None, (
                f"{check['name']} thiếu guard 'if ({check['inflight_flag']}) return;'!"
            )

            # 2. Kiểm tra gán inFlight = true trước network request
            assert f"{check['inflight_flag']} = true" in block, (
                f"{check['name']} không gán {check['inflight_flag']} = true trước fetch!"
            )

            # 3. Kiểm tra disabled = true trước network request
            assert "disabled = true" in block, (
                f"{check['name']} không gán disabled = true khi bắt đầu request!"
            )

            # 4. Kiểm tra finally block khôi phục inFlight = false
            assert "finally" in block, f"{check['name']} thiếu khối finally!"
            finally_idx = block.find("finally")
            finally_block = block[finally_idx : finally_idx + 400]
            assert f"{check['inflight_flag']} = false" in finally_block, (
                f"{check['name']} không reset {check['inflight_flag']} = false trong finally!"
            )


# =============================================================================
# 3. VISUAL COUNTDOWN ON #btnSendForgotOtp TESTS
# =============================================================================

class TestVisualCountdownTimer:
    """Kiểm tra đối kháng bộ đếm ngược trực quan 60s trên nút Gửi OTP."""

    def test_countdown_timer_structure_and_recovery(self):
        """Kiểm tra chi tiết logic setInterval, đếm ngược giây, clearInterval và phục hồi nút."""
        app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
        content = app_js_path.read_text(encoding="utf-8")

        idx = content.find("btnSendForgotOtp")
        assert idx != -1
        otp_block = content[idx : idx + 2600]

        # 1. Biến timer và việc clear interval cũ trước khi tạo mới (tránh rò rỉ timer)
        assert "if (forgotOtpCooldownTimer) clearInterval(forgotOtpCooldownTimer)" in otp_block, (
            "Thiếu clear timer cũ trước khi khởi tạo interval mới!"
        )

        # 2. Sử dụng cooldown_remaining_seconds từ backend payload (fallback 60s)
        assert "cooldown_remaining_seconds" in otp_block, (
            "Countdown không đọc trường cooldown_remaining_seconds từ response của server!"
        )

        # 3. setInterval 1000ms
        assert "setInterval" in otp_block and "1000" in otp_block, (
            "Thiếu setInterval định kỳ 1000ms!"
        )

        # 4. Khi remaining <= 0: clearInterval, reset timer, mở khóa nút, text trở về 'Gửi OTP'
        assert "remaining <= 0" in otp_block or "remaining < 1" in otp_block, (
            "Thiếu điều kiện kết thúc đếm ngược (remaining <= 0)!"
        )
        assert "btnSendForgotOtp.disabled = false" in otp_block, (
            "Khi hết 60s, nút không được mở khóa (disabled = false)!"
        )
        assert '"Gửi OTP"' in otp_block or "'Gửi OTP'" in otp_block, (
            "Khi hết 60s, nhãn nút không được khôi phục về 'Gửi OTP'!"
        )

        # 5. Xử lý lỗi (error/catch): nếu gửi thất bại hoặc network error, nút phải mở lại ngay
        assert "catch" in otp_block, "Thiếu khối catch xử lý lỗi kết nối cho nút gửi OTP!"


# =============================================================================
# 4. BACKEND COOLDOWN EXACT BOUNDARY TESTS (t=0s, 30s, 59s, 59.9s, 60s, 61s)
# =============================================================================

class TestBackendCooldownExactBoundaries:
    """Kiểm định đối kháng biên thời gian chính xác của cơ chế Cooldown 60s."""

    def test_exact_boundaries_timeline(self, client: TestClient, auth_mgr: ThreeLayerAuthManager):
        """Kiểm thử tuần tự theo mốc thời gian chặt chẽ: t=0s, t=30s, t=59s, t=59.9s, t=60s, t=61s."""
        email = "senat6031@gmail.com"
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp

        t_base = 100000.0

        with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "mock password"}), patch(
            "smtplib.SMTP", return_value=mock_smtp
        ):
            # --- MỐC 1: t = t_base (Tạo OTP lần đầu) ---
            with patch("time.time", return_value=t_base):
                r1 = client.post("/api/auth3/forgot_password_send_otp", json={"email": email, "send_gmail": True})
                assert r1.status_code == 200
                d1 = r1.json()
                assert d1.get("ok") is True
                assert d1.get("idempotent") is not True
                assert d1.get("cooldown_active") is not True

                first_otp = auth_mgr.pending_otps[email]["otp_code"]
                assert len(first_otp) == 6
                assert (mock_smtp.send_message.call_count + mock_smtp.sendmail.call_count) == 1

            # --- MỐC 2: t = t_base + 0.0s (Ngay lập tức sau đó, elapsed = 0.0s < 60s) ---
            with patch("time.time", return_value=t_base):
                r2 = client.post("/api/auth3/forgot_password_send_otp", json={"email": email, "send_gmail": True})
                assert r2.status_code == 200
                d2 = r2.json()
                assert d2.get("ok") is True
                assert d2.get("idempotent") is True
                assert d2.get("cooldown_active") is True
                assert d2.get("cooldown_remaining_seconds") == 60
                assert d2.get("otp_code_for_test") == first_otp
                # Không gửi thêm email
                assert (mock_smtp.send_message.call_count + mock_smtp.sendmail.call_count) == 1

            # --- MỐC 3: t = t_base + 30.0s (Nửa chu kỳ, elapsed = 30.0s < 60s) ---
            with patch("time.time", return_value=t_base + 30.0):
                r3 = client.post("/api/auth3/forgot_password_send_otp", json={"email": email, "send_gmail": True})
                assert r3.status_code == 200
                d3 = r3.json()
                assert d3.get("ok") is True
                assert d3.get("idempotent") is True
                assert d3.get("cooldown_active") is True
                assert d3.get("cooldown_remaining_seconds") == 30
                assert d3.get("otp_code_for_test") == first_otp
                assert (mock_smtp.send_message.call_count + mock_smtp.sendmail.call_count) == 1

            # --- MỐC 4: t = t_base + 59.0s (1s trước khi hết cooldown, elapsed = 59.0s < 60s) ---
            with patch("time.time", return_value=t_base + 59.0):
                r4 = client.post("/api/auth3/forgot_password_send_otp", json={"email": email, "send_gmail": True})
                assert r4.status_code == 200
                d4 = r4.json()
                assert d4.get("ok") is True
                assert d4.get("idempotent") is True
                assert d4.get("cooldown_active") is True
                assert d4.get("cooldown_remaining_seconds") == 1
                assert d4.get("otp_code_for_test") == first_otp
                assert (mock_smtp.send_message.call_count + mock_smtp.sendmail.call_count) == 1

            # --- MỐC 5: t = t_base + 59.9s (Cận biên sát 60s, elapsed = 59.9s < 60s) ---
            with patch("time.time", return_value=t_base + 59.9):
                r5 = client.post("/api/auth3/forgot_password_send_otp", json={"email": email, "send_gmail": True})
                assert r5.status_code == 200
                d5 = r5.json()
                assert d5.get("ok") is True
                assert d5.get("idempotent") is True
                assert d5.get("cooldown_active") is True
                assert d5.get("cooldown_remaining_seconds") == 0
                assert d5.get("otp_code_for_test") == first_otp
                assert (mock_smtp.send_message.call_count + mock_smtp.sendmail.call_count) == 1

            # --- MỐC 6: t = t_base + 60.0s (ĐÚNG ĐIỂM BIÊN 60.0s, elapsed = 60.0s >= 60s) ---
            # elapsed < 60.0 là False -> Cooldown hết hạn, sinh mã OTP mới và gửi email mới!
            with patch("time.time", return_value=t_base + 60.0):
                r6 = client.post("/api/auth3/forgot_password_send_otp", json={"email": email, "send_gmail": True})
                assert r6.status_code == 200
                d6 = r6.json()
                assert d6.get("ok") is True
                assert d6.get("idempotent") is not True
                assert d6.get("cooldown_active") is not True

                second_otp = auth_mgr.pending_otps[email]["otp_code"]
                assert len(second_otp) == 6
                # Email thứ 2 được phát đi
                assert (mock_smtp.send_message.call_count + mock_smtp.sendmail.call_count) == 2

            # --- MỐC 7: t = t_base + 61.0s (1s sau khi tạo second_otp tại t_base+60.0s) ---
            # Đối với second_otp, elapsed = (t_base + 61.0) - (t_base + 60.0) = 1.0s < 60s!
            # Nên tại 61.0s, request BỊ COOLDOWN dưới chu kỳ mới (còn 59s), bảo toàn second_otp!
            with patch("time.time", return_value=t_base + 61.0):
                r7 = client.post("/api/auth3/forgot_password_send_otp", json={"email": email, "send_gmail": True})
                assert r7.status_code == 200
                d7 = r7.json()
                assert d7.get("ok") is True
                assert d7.get("idempotent") is True
                assert d7.get("cooldown_active") is True
                assert d7.get("cooldown_remaining_seconds") == 59
                assert d7.get("otp_code_for_test") == second_otp
                # Không gửi thêm email
                assert (mock_smtp.send_message.call_count + mock_smtp.sendmail.call_count) == 2

            # --- MỐC 8: t = t_base + 121.0s (Hết cooldown của chu kỳ 2, elapsed = 61.0s > 60s) ---
            with patch("time.time", return_value=t_base + 121.0):
                r8 = client.post("/api/auth3/forgot_password_send_otp", json={"email": email, "send_gmail": True})
                assert r8.status_code == 200
                d8 = r8.json()
                assert d8.get("ok") is True
                assert d8.get("idempotent") is not True
                assert d8.get("cooldown_active") is not True

                third_otp = auth_mgr.pending_otps[email]["otp_code"]
                assert (mock_smtp.send_message.call_count + mock_smtp.sendmail.call_count) == 3

    def test_case_insensitive_email_cooldown_binding(self, client: TestClient, auth_mgr: ThreeLayerAuthManager):
        """Email hoa thường (Upper/Lower case) được chuẩn hóa và dùng chung một bộ đếm cooldown."""
        with patch("time.time", return_value=50000.0):
            r1 = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "SENAT6031@GMAIL.COM", "send_gmail": False},
            )
            assert r1.status_code == 200
            otp1 = r1.json()["otp_code_for_test"]

        # Request với email chữ thường 10s sau
        with patch("time.time", return_value=50010.0):
            r2 = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "  senat6031@gmail.com  ", "send_gmail": False},
            )
            assert r2.status_code == 200
            d2 = r2.json()
            assert d2.get("idempotent") is True
            assert d2.get("cooldown_active") is True
            assert d2.get("cooldown_remaining_seconds") == 50
            assert d2.get("otp_code_for_test") == otp1

    def test_rapid_fire_stress_harness(self, client: TestClient, auth_mgr: ThreeLayerAuthManager):
        """Bắn liên tiếp 15 request trong 1 giây từ nhiều luồng chỉ tạo đúng 1 OTP."""
        email = "nep94121@gmail.com"
        num_threads = 15
        results = []

        with patch("time.time", return_value=70000.0):
            barrier = threading.Barrier(num_threads)

            def fire():
                barrier.wait()
                return client.post(
                    "/api/auth3/forgot_password_send_otp",
                    json={"email": email, "send_gmail": False},
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as pool:
                futures = [pool.submit(fire) for _ in range(num_threads)]
                results = [f.result() for f in futures]

        status_codes = [r.status_code for r in results]
        assert all(code == 200 for code in status_codes)

        idempotent_count = sum(1 for r in results if r.json().get("idempotent") is True)
        assert idempotent_count == num_threads - 1

        active_otp = auth_mgr.pending_otps[email]["otp_code"]
        for r in results:
            otp_val = r.json().get("otp_code_for_test") or r.json().get("demo_otp_preview")
            assert otp_val == active_otp
