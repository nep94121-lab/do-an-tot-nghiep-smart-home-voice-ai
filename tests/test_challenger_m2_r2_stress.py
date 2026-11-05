"""Milestone 2 Empirical Challenger Test Suite (challenger_m2_1).

Mission: Empirically Challenge Milestone 2 (R2 Anti-Double-Send Cooldown & Trigger Fixes)
Adversarial Verification:
1. Concurrency stress: 30 concurrent threads sending OTP requests for the same recipient
   simultaneously using threading.Barrier synchronization.
   Verify:
   - Exactly ONE email dispatch occurs.
   - All 30 threads receive HTTP 200.
   - Preserved OTP is identical across all 30 responses.
   - Exactly 1 non-idempotent response and 29 idempotent/cooldown responses.
2. Rapid-fire sequential requests:
   - Send 10 rapid OTP requests within 5 seconds for the same recipient.
   - Verify only 1 email sent, 9 marked idempotent/cooldown, OTP code unchanged.
3. Different recipients isolation:
   - Ensure cooldown for recipient A does NOT block or affect recipient B or C.
   - Independent cooldown timers and distinct OTP dispatches.
4. Consumed OTP reuse (Anti-Replay):
   - Once OTP is used in reset_password_with_otp, calling it again with the same OTP
     fails with HTTP 400.
   - Direct manager call also returns ok=False.
5. Adversarial input normalization:
   - Case insensitivity and whitespace trim: 'SENAT6031@GMAIL.COM' and ' senat6031@gmail.com '
     share the same cooldown bucket as 'senat6031@gmail.com'.
6. Boundary timing test:
   - Request within 60s (<60s) -> throttled/idempotent.
   - Request after 60s (>=60s) -> new OTP generated and dispatched.
"""

from __future__ import annotations

import concurrent.futures
import os
import pathlib
import threading
import time
from typing import Any
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
def clean_otp_state_fixture():
    """Tự động dọn sạch pending_otps trước và sau mỗi test case."""
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


class TestMilestone2EmpiricalChallenge:
    """Bộ kiểm thử đối kháng thực nghiệm cho Milestone 2 (R2 Cooldown & Idempotency)."""

    def test_challenge_1_concurrency_stress_30_threads(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Concurrency stress: 30 concurrent threads sending OTP requests simultaneously.

        Verify:
        - Exactly ONE email dispatch occurs.
        - All 30 threads receive HTTP 200.
        - Preserved OTP is identical across all responses.
        - Exactly 1 new dispatch response and 29 idempotent responses.
        """
        assert hasattr(auth_mgr, "_otp_lock"), "Backend must have _otp_lock attribute"

        num_threads = 30
        barrier = threading.Barrier(num_threads)
        email_dispatch_counter = 0
        counter_lock = threading.Lock()

        def mock_send_real_gmail_otp(recipient_email: str, otp_code: str, display_name: str) -> dict[str, Any]:
            nonlocal email_dispatch_counter
            # Thêm độ trễ giả lập mạng thực tế để kích thích race condition nếu thiếu lock
            time.sleep(0.03)
            with counter_lock:
                email_dispatch_counter += 1
            return {
                "sent_real_gmail": True,
                "actual_recipient": recipient_email,
                "gmail_message_id": f"msg_{otp_code}",
            }

        target_recipient = "senat6031@gmail.com"

        with patch.object(auth_mgr, "send_real_gmail_otp", side_effect=mock_send_real_gmail_otp):
            def worker():
                # Chờ tất cả 30 thread sẵn sàng trước khi đồng loạt gửi request
                barrier.wait()
                resp = client.post(
                    "/api/auth3/forgot_password_send_otp",
                    json={"email": target_recipient, "send_gmail": True},
                )
                return resp

            with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = [executor.submit(worker) for _ in range(num_threads)]
                responses = [f.result() for f in futures]

        # 1. Toàn bộ 30 threads đều nhận HTTP 200 và ok=True
        assert len(responses) == num_threads
        for idx, r in enumerate(responses):
            assert r.status_code == 200, f"Thread {idx} received status {r.status_code}"
            assert r.json().get("ok") is True, f"Thread {idx} payload error: {r.json()}"

        # 2. Email dispatch DUY NHẤT 1 LẦN
        assert email_dispatch_counter == 1, (
            f"Adversarial Failure: Expected exactly 1 email dispatch, got {email_dispatch_counter}"
        )

        # 3. Phân bổ responses: Đúng 1 response ban đầu và 29 responses idempotent
        idempotent_responses = [r for r in responses if r.json().get("idempotent") is True]
        fresh_responses = [r for r in responses if not r.json().get("idempotent")]
        assert len(fresh_responses) == 1, f"Expected 1 fresh response, got {len(fresh_responses)}"
        assert len(idempotent_responses) == num_threads - 1, (
            f"Expected {num_threads - 1} idempotent responses, got {len(idempotent_responses)}"
        )

        # 4. Mã OTP được bảo toàn đồng nhất 100% trên cả 30 responses
        target_otp = auth_mgr.pending_otps[target_recipient]["otp_code"]
        assert len(target_otp) == 6
        assert target_otp.isdigit()

        for idx, r in enumerate(responses):
            body = r.json()
            code = body.get("otp_code_for_test") or body.get("demo_otp_preview")
            # For idempotent responses, otp_code_for_test / demo_otp_preview is returned
            if body.get("idempotent"):
                assert code == target_otp, (
                    f"Thread {idx} returned differing OTP: {code} != {target_otp}"
                )

    def test_challenge_2_rapid_fire_10_sequential_requests_within_5_seconds(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Rapid-fire sequential requests: Send 10 rapid OTP requests within 5 seconds for the same recipient.

        Verify:
        - Exactly 1 email is sent.
        - 9 are marked idempotent/cooldown.
        - OTP code does not change.
        """
        target_recipient = "senat6031@gmail.com"
        email_dispatch_counter = 0

        def mock_send_real_gmail_otp(recipient_email: str, otp_code: str, display_name: str) -> dict[str, Any]:
            nonlocal email_dispatch_counter
            email_dispatch_counter += 1
            return {
                "sent_real_gmail": True,
                "actual_recipient": recipient_email,
                "gmail_message_id": f"msg_rapid_{otp_code}",
            }

        start_time = time.time()
        responses = []

        with patch.object(auth_mgr, "send_real_gmail_otp", side_effect=mock_send_real_gmail_otp):
            for i in range(10):
                resp = client.post(
                    "/api/auth3/forgot_password_send_otp",
                    json={"email": target_recipient, "send_gmail": True},
                )
                responses.append(resp)
                time.sleep(0.05)  # tổng 10 * 0.05s = 0.5s << 5s

        total_elapsed = time.time() - start_time
        assert total_elapsed < 5.0, f"Rapid-fire took too long: {total_elapsed:.2f}s"

        # 1. Kiểm tra HTTP 200 cho tất cả 10 requests
        assert len(responses) == 10
        for idx, r in enumerate(responses):
            assert r.status_code == 200
            assert r.json().get("ok") is True

        # 2. Chỉ có duy nhất 1 email được gửi
        assert email_dispatch_counter == 1, (
            f"Expected exactly 1 email dispatch for rapid-fire, got {email_dispatch_counter}"
        )

        # 3. Request đầu tiên là fresh
        r1_body = responses[0].json()
        assert r1_body.get("idempotent") is not True
        assert r1_body.get("cooldown_active") is not True

        # 4. 9 requests tiếp theo đều mang idempotent=True và cooldown_active=True
        for idx in range(1, 10):
            r_body = responses[idx].json()
            assert r_body.get("idempotent") is True, f"Request {idx} failed idempotent check"
            assert r_body.get("cooldown_active") is True, f"Request {idx} failed cooldown_active check"
            assert "cooldown_remaining_seconds" in r_body
            assert 0 <= r_body["cooldown_remaining_seconds"] <= 60

        # 5. Mã OTP không hề bị thay đổi qua cả 10 lần gửi
        stored_otp = auth_mgr.pending_otps[target_recipient]["otp_code"]
        for idx in range(1, 10):
            assert responses[idx].json().get("otp_code_for_test") == stored_otp

    def test_challenge_3_different_recipients_independent_cooldown(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Different recipients: Ensure cooldown for recipient A does NOT block or affect recipient B.

        Verify:
        - Recipient A gets OTP and email dispatch.
        - Recipient B immediately gets OTP and email dispatch without cooldown blocking.
        - Recipient C immediately gets OTP and email dispatch.
        - Subsequent request for A gets cooldown throttled.
        - Subsequent request for B gets cooldown throttled.
        """
        dispatch_log = []

        def mock_send_real_gmail_otp(recipient_email: str, otp_code: str, display_name: str) -> dict[str, Any]:
            dispatch_log.append((recipient_email, otp_code))
            return {
                "sent_real_gmail": True,
                "actual_recipient": recipient_email,
                "gmail_message_id": f"msg_{recipient_email}_{otp_code}",
            }

        with patch.object(auth_mgr, "send_real_gmail_otp", side_effect=mock_send_real_gmail_otp):
            # 1. Recipient A
            res_a1 = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "senat6031@gmail.com", "send_gmail": True},
            )
            assert res_a1.status_code == 200
            assert res_a1.json().get("idempotent") is not True

            # 2. Recipient B (ngay sau A, không bị A cooldown)
            res_b1 = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "nep94121@gmail.com", "send_gmail": True},
            )
            assert res_b1.status_code == 200
            assert res_b1.json().get("idempotent") is not True

            # 3. Recipient C (ngay sau B)
            res_c1 = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "kbanh376@gmail.com", "send_gmail": True},
            )
            assert res_c1.status_code == 200
            assert res_c1.json().get("idempotent") is not True

            # Kiểm tra 3 email đã được gửi độc lập
            assert len(dispatch_log) == 3
            assert {d[0] for d in dispatch_log} == {
                "senat6031@gmail.com",
                "nep94121@gmail.com",
                "kbanh376@gmail.com",
            }

            # 4. Gửi lại cho A -> Phải bị cooldown
            res_a2 = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "senat6031@gmail.com", "send_gmail": True},
            )
            assert res_a2.status_code == 200
            assert res_a2.json().get("idempotent") is True
            assert res_a2.json().get("cooldown_active") is True

            # 5. Gửi lại cho B -> Phải bị cooldown
            res_b2 = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "nep94121@gmail.com", "send_gmail": True},
            )
            assert res_b2.status_code == 200
            assert res_b2.json().get("idempotent") is True

            # Tổng số email vẫn là 3, không phát sinh email thứ 4
            assert len(dispatch_log) == 3

    def test_challenge_4_consumed_otp_reuse_fails_with_400(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Consumed OTP reuse: Verify that once an OTP is used in reset_password_with_otp,
        calling it again with the same OTP fails with HTTP 400.
        """
        target_email = "senat6031@gmail.com"
        original_password = "GiaDinh@123"

        # 1. Phát hành OTP
        res_otp = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": target_email, "send_gmail": False},
        )
        assert res_otp.status_code == 200
        otp_code = res_otp.json().get("otp_code_for_test") or res_otp.json().get("demo_otp_preview")
        assert otp_code is not None
        assert target_email in auth_mgr.pending_otps

        try:
            # 2. Sử dụng OTP thành công lần đầu
            res_reset1 = client.post(
                "/api/auth3/forgot_password_reset",
                json={
                    "email": target_email,
                    "otp_code": otp_code,
                    "new_password": "EmpiricalPassword#1",
                    "confirm_password": "EmpiricalPassword#1",
                },
            )
            assert res_reset1.status_code == 200
            assert res_reset1.json().get("ok") is True

            # OTP phải bị xóa khỏi pending_otps
            assert target_email not in auth_mgr.pending_otps

            # 3. Tái sử dụng cùng mã OTP lần 2 (Replay attack qua API) -> Phải thất bại với HTTP 400
            res_reset2 = client.post(
                "/api/auth3/forgot_password_reset",
                json={
                    "email": target_email,
                    "otp_code": otp_code,
                    "new_password": "EmpiricalPassword#2",
                    "confirm_password": "EmpiricalPassword#2",
                },
            )
            assert res_reset2.status_code == 400, (
                f"Expected HTTP 400 on consumed OTP reuse, got {res_reset2.status_code}"
            )
            assert res_reset2.json().get("ok") is False

            # 4. Kiểm tra trực tiếp trên ThreeLayerAuthManager.reset_password_with_otp
            mgr_direct_res = auth_mgr.reset_password_with_otp(
                email=target_email,
                otp_code=otp_code,
                new_password="EmpiricalPassword#3",
                confirm_password="EmpiricalPassword#3",
            )
            assert mgr_direct_res.get("ok") is False
            assert mgr_direct_res.get("status_code", 400) == 400
        finally:
            # Khôi phục mật khẩu gốc để bảo đảm không ảnh hưởng các test suite khác
            auth_mgr.register_or_update_password(
                email=target_email,
                password=original_password,
                confirm_password=original_password,
                source="ChallengeTeardown",
            )

    def test_challenge_5_adversarial_email_casing_and_whitespace_isolation(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Adversarial normalization: Thử nghiệm vượt rào cooldown bằng ký tự hoa hoặc khoảng trắng thừa.

        'SENAT6031@GMAIL.COM' và '  senat6031@gmail.com  ' phải chia sẻ cùng bộ đếm cooldown.
        """
        # Request 1: Chữ thường
        r1 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "senat6031@gmail.com", "send_gmail": False},
        )
        assert r1.status_code == 200
        otp1 = r1.json()["otp_code_for_test"]

        # Request 2: Viết HOA toàn bộ -> Vẫn phải bị cooldown
        r2 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "SENAT6031@GMAIL.COM", "send_gmail": False},
        )
        assert r2.status_code == 200
        assert r2.json().get("idempotent") is True
        assert r2.json().get("cooldown_active") is True
        assert r2.json().get("otp_code_for_test") == otp1

        # Request 3: Thêm khoảng trắng đầu/cuối -> Vẫn phải bị cooldown
        r3 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "   senat6031@gmail.com   ", "send_gmail": False},
        )
        assert r3.status_code == 200
        assert r3.json().get("idempotent") is True
        assert r3.json().get("otp_code_for_test") == otp1

    def test_challenge_6_timing_boundary_under_and_over_60s(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Timing boundary:
        - elapsed = 59.5s -> cooldown active (idempotent=True).
        - elapsed = 60.5s -> cooldown expired, generates new OTP.
        """
        email = "senat6031@gmail.com"

        # Lần 1
        r1 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": email, "send_gmail": False},
        )
        assert r1.status_code == 200
        otp1 = r1.json()["otp_code_for_test"]

        # Giả lập elapsed = 59.5 giây
        auth_mgr.pending_otps[email]["created_at"] = time.time() - 59.5
        r_boundary_under = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": email, "send_gmail": False},
        )
        assert r_boundary_under.json().get("idempotent") is True
        assert r_boundary_under.json().get("otp_code_for_test") == otp1

        # Giả lập elapsed = 60.5 giây
        auth_mgr.pending_otps[email]["created_at"] = time.time() - 60.5
        r_boundary_over = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": email, "send_gmail": False},
        )
        assert r_boundary_over.json().get("idempotent") is not True
        assert r_boundary_over.json().get("cooldown_active") is not True
        assert r_boundary_over.json()["otp_code_for_test"] != otp1
