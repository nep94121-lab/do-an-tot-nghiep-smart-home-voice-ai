"""Adversarial Empirical Stress Test Suite for Milestone 2 (M2_R2):
OTP Verify Rate-Limiting Logic.

Author: challenger_m2_r2_2 (Adversarial Challenger 2 for Milestone 2)
Focus:
1. Dynamic stress testing of failed OTP verification rate limiting.
2. Boundary testing of the 3-attempt / 5-minute sliding window.
3. Lockout enforcement (HTTP 429) on 4th and subsequent attempts.
4. Correct OTP rejected when rate limit is active (brute-force lockout protection).
5. Cross-email isolation (User A rate-limited != User B affected).
6. Time-based sliding window rollover (gradual and complete expiration).
7. Success-driven counter reset.
8. Multithreaded concurrency stress testing (race condition probe on verify attempts).
9. Adversarial input variations (casing, whitespace, malformed strings).
10. Full coverage of both `/api/auth3/layer2_verify_otp` and `/api/auth3/forgot_password_reset`.
"""

from __future__ import annotations

import concurrent.futures
import pathlib
import threading
import time
from typing import Any
from unittest.mock import patch

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
    """Tự động dọn sạch pending_otps và otp_failed_attempts trước và sau mỗi test."""
    from simulator.api.routes_auth import get_auth_3layer_manager

    mgr = get_auth_3layer_manager()
    lock = getattr(mgr, "_otp_lock", threading.Lock())
    with lock:
        mgr.pending_otps.clear()
        if hasattr(mgr, "otp_failed_attempts"):
            mgr.otp_failed_attempts.clear()
        for acc in getattr(mgr, "accounts", []):
            acc.pop("pending_otp", None)
            acc.pop("otp_cooldown_started_at", None)
            acc.pop("otp_failed_verify_attempts", None)
        mgr._save_accounts()
    yield
    with lock:
        mgr.pending_otps.clear()
        if hasattr(mgr, "otp_failed_attempts"):
            mgr.otp_failed_attempts.clear()
        for acc in getattr(mgr, "accounts", []):
            acc.pop("pending_otp", None)
            acc.pop("otp_cooldown_started_at", None)
            acc.pop("otp_failed_verify_attempts", None)
        mgr._save_accounts()


@pytest.fixture
def auth_mgr() -> ThreeLayerAuthManager:
    from simulator.api.routes_auth import get_auth_3layer_manager

    return get_auth_3layer_manager()


class TestAdversarialFailedOtpVerifyRateLimit:
    """Empirical challenge suite for failed OTP verify rate-limiting logic."""

    def test_adv_1_three_failed_attempts_allowed_with_400(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Verify that exactly 3 failed OTP verify attempts in < 5 minutes return HTTP 400.

        They must NOT be blocked by rate limit yet (rate_limited != True, status_code == 400).
        """
        email = "senat6031@gmail.com"
        r_init = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": email, "send_gmail": False},
        )
        assert r_init.status_code == 200

        for attempt in range(1, 4):
            wrong_code = f"99999{attempt}"
            res = client.post(
                "/api/auth3/layer2_verify_otp",
                json={"email": email, "otp_code": wrong_code},
            )
            assert res.status_code == 400, (
                f"Attempt {attempt} should return 400, got {res.status_code}: {res.text}"
            )
            data = res.json()
            assert data.get("ok") is False
            assert data.get("status_code") == 400
            assert data.get("rate_limited") is not True
            assert f"Mã OTP '{wrong_code}' không chính xác" in data.get("error", "")

    def test_adv_2_fourth_fifth_and_subsequent_attempts_rejected_with_429(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Verify that 4th, 5th, and subsequent failed attempts within 5 minutes return HTTP 429.

        Also verify that even submitting the CORRECT OTP is blocked once 429 rate limit is triggered.
        """
        email = "senat6031@gmail.com"
        client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": email, "send_gmail": False},
        )
        real_otp = auth_mgr.pending_otps[email]["otp_code"]

        # Attempts 1, 2, 3 -> HTTP 400
        for i in range(1, 4):
            r = client.post(
                "/api/auth3/layer2_verify_otp",
                json={"email": email, "otp_code": f"11111{i}"},
            )
            assert r.status_code == 400

        # Attempt 4 -> MUST return HTTP 429
        r4 = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": email, "otp_code": "111114"},
        )
        assert r4.status_code == 429, f"Attempt 4 expected 429, got {r4.status_code}: {r4.text}"
        d4 = r4.json()
        assert d4.get("ok") is False
        assert d4.get("rate_limited") is True
        assert d4.get("status_code") == 429
        assert "quá 3 lần trong 5 phút" in d4.get("error", "")

        # Attempt 5 -> MUST return HTTP 429
        r5 = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": email, "otp_code": "111115"},
        )
        assert r5.status_code == 429
        assert r5.json().get("rate_limited") is True

        # Attempt 6 with CORRECT OTP -> MUST STILL BE BLOCKED with HTTP 429 (anti-brute force lockout)
        r6 = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": email, "otp_code": real_otp},
        )
        assert r6.status_code == 429, (
            "Security flaw: Submitting valid OTP bypassed active 429 rate limit lockout!"
        )
        assert r6.json().get("rate_limited") is True
        assert r6.json().get("ok") is False

    def test_adv_3_per_email_rate_limit_isolation(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Verify that rate limiting on User A does NOT affect User B (complete isolation)."""
        email_a = "senat6031@gmail.com"
        email_b = "nep94121@gmail.com"

        # Initialize OTPs for both
        client.post("/api/auth3/forgot_password_send_otp", json={"email": email_a, "send_gmail": False})
        client.post("/api/auth3/forgot_password_send_otp", json={"email": email_b, "send_gmail": False})

        otp_b = auth_mgr.pending_otps[email_b]["otp_code"]

        # Lock out User A with 4 failed attempts
        for i in range(1, 4):
            client.post("/api/auth3/layer2_verify_otp", json={"email": email_a, "otp_code": f"00000{i}"})
        r_a_lock = client.post("/api/auth3/layer2_verify_otp", json={"email": email_a, "otp_code": "000004"})
        assert r_a_lock.status_code == 429
        assert r_a_lock.json().get("rate_limited") is True

        # User B should NOT be locked out!
        # User B attempt 1 wrong -> HTTP 400 (not 429)
        r_b1 = client.post("/api/auth3/layer2_verify_otp", json={"email": email_b, "otp_code": "999999"})
        assert r_b1.status_code == 400
        assert r_b1.json().get("rate_limited") is not True

        # User B attempt 2 correct -> HTTP 200 (succeeds)
        r_b2 = client.post("/api/auth3/layer2_verify_otp", json={"email": email_b, "otp_code": otp_b})
        assert r_b2.status_code == 200
        assert r_b2.json().get("ok") is True

        # User A MUST still be locked out
        r_a_still = client.post("/api/auth3/layer2_verify_otp", json={"email": email_a, "otp_code": "000005"})
        assert r_a_still.status_code == 429
        assert r_a_still.json().get("rate_limited") is True

    def test_adv_4_sliding_window_rollover_after_5_minutes(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Verify that when 5 minutes expire, the rate limit window rolls over.

        Tests both complete expiration (> 300s) and true sliding window boundary (gradual expiration).
        """
        email = "senat6031@gmail.com"
        client.post("/api/auth3/forgot_password_send_otp", json={"email": email, "send_gmail": False})

        now = time.time()
        # Seed 3 failures:
        # Failure 1 at t - 310s (outside 300s window)
        # Failure 2 at t - 200s (inside window)
        # Failure 3 at t - 100s (inside window)
        with auth_mgr._otp_lock:
            auth_mgr.otp_failed_attempts[email] = [now - 310.0, now - 200.0, now - 100.0]
            acc = auth_mgr.find_account(email)
            if acc:
                acc["otp_failed_verify_attempts"] = [now - 310.0, now - 200.0, now - 100.0]
                auth_mgr._save_accounts()

        # At this point, only 2 failures are in the 300s sliding window.
        # Next attempt (the 3rd active failure) must be allowed and return HTTP 400, NOT 429!
        r_third = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": email, "otp_code": "000001"},
        )
        assert r_third.status_code == 400, (
            f"Sliding window rollover failed: older failure at -310s was not expired! Got {r_third.status_code}"
        )
        assert r_third.json().get("rate_limited") is not True

        # Now there are 3 active failures in the window (t-200s, t-100s, now).
        # Subsequent attempt MUST return 429!
        r_fourth = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": email, "otp_code": "000002"},
        )
        assert r_fourth.status_code == 429
        assert r_fourth.json().get("rate_limited") is True

        # Next: Advance time completely past 300s for all failures
        with auth_mgr._otp_lock:
            auth_mgr.otp_failed_attempts[email] = [now - 305.0, now - 304.0, now - 301.0]
            if acc:
                acc["otp_failed_verify_attempts"] = [now - 305.0, now - 304.0, now - 301.0]
                auth_mgr._save_accounts()

        # All 3 previous failures have rolled over (> 300s).
        # Attempt should now be allowed (HTTP 400)
        r_fresh = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": email, "otp_code": "000003"},
        )
        assert r_fresh.status_code == 400, f"Expected 400 after rollover, got {r_fresh.status_code}"
        assert r_fresh.json().get("rate_limited") is not True

    def test_adv_5_successful_verification_clears_failed_attempts(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Verify that successful verification clears failed attempts, allowing 3 fresh failures later."""
        email = "senat6031@gmail.com"
        client.post("/api/auth3/forgot_password_send_otp", json={"email": email, "send_gmail": False})
        otp = auth_mgr.pending_otps[email]["otp_code"]

        # 2 failures
        client.post("/api/auth3/layer2_verify_otp", json={"email": email, "otp_code": "000001"})
        client.post("/api/auth3/layer2_verify_otp", json={"email": email, "otp_code": "000002"})

        # Successful verification
        r_ok = client.post("/api/auth3/layer2_verify_otp", json={"email": email, "otp_code": otp})
        assert r_ok.status_code == 200
        assert r_ok.json().get("ok") is True

        # Check in-memory and account records are cleared
        assert len(auth_mgr.otp_failed_attempts.get(email, [])) == 0
        acc = auth_mgr.find_account(email)
        assert not acc.get("otp_failed_verify_attempts")

        # Simulate subsequent session: clear pending and issue fresh OTP
        with auth_mgr._otp_lock:
            auth_mgr.pending_otps.clear()
            if acc:
                acc.pop("pending_otp", None)
                acc.pop("otp_cooldown_started_at", None)

        client.post("/api/auth3/forgot_password_send_otp", json={"email": email, "send_gmail": False})

        # Should be able to fail 3 times again without hitting 429
        for i in range(1, 4):
            rf = client.post("/api/auth3/layer2_verify_otp", json={"email": email, "otp_code": f"22222{i}"})
            assert rf.status_code == 400, f"Attempt {i} after reset should be 400, got {rf.status_code}"
            assert rf.json().get("rate_limited") is not True

        # 4th failure triggers 429
        rf4 = client.post("/api/auth3/layer2_verify_otp", json={"email": email, "otp_code": "222224"})
        assert rf4.status_code == 429
        assert rf4.json().get("rate_limited") is True

    def test_adv_6_reset_password_with_otp_endpoint_rate_limits(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Verify that `/api/auth3/forgot_password_reset` also enforces the 429 rate limit."""
        email = "senat6031@gmail.com"
        client.post("/api/auth3/forgot_password_send_otp", json={"email": email, "send_gmail": False})

        # 3 wrong attempts via forgot_password_reset
        for i in range(1, 4):
            r = client.post(
                "/api/auth3/forgot_password_reset",
                json={
                    "email": email,
                    "otp_code": f"12345{i}",
                    "new_password": "NewPassword123!",
                    "confirm_password": "NewPassword123!",
                },
            )
            assert r.status_code == 400, f"Attempt {i} expected 400, got {r.status_code}"

        # 4th attempt via forgot_password_reset MUST return 429
        r4 = client.post(
            "/api/auth3/forgot_password_reset",
            json={
                "email": email,
                "otp_code": "123454",
                "new_password": "NewPassword123!",
                "confirm_password": "NewPassword123!",
            },
        )
        assert r4.status_code == 429, f"Expected 429 from forgot_password_reset, got {r4.status_code}: {r4.text}"
        data4 = r4.json()
        assert data4.get("ok") is False
        assert data4.get("rate_limited") is True
        assert data4.get("status_code") == 429

    def test_adv_7_adversarial_normalization_casing_and_whitespace(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Adversarial normalization: Attacker cannot bypass rate limit using case manipulation or whitespace."""
        client.post("/api/auth3/forgot_password_send_otp", json={"email": "senat6031@gmail.com", "send_gmail": False})

        # Attempt 1: Lowercase
        r1 = client.post("/api/auth3/layer2_verify_otp", json={"email": "senat6031@gmail.com", "otp_code": "000001"})
        assert r1.status_code == 400

        # Attempt 2: UPPERCASE
        r2 = client.post("/api/auth3/layer2_verify_otp", json={"email": "SENAT6031@GMAIL.COM", "otp_code": "000002"})
        assert r2.status_code == 400

        # Attempt 3: Mixed case with leading and trailing spaces
        r3 = client.post("/api/auth3/layer2_verify_otp", json={"email": "  Senat6031@Gmail.Com  ", "otp_code": "000003"})
        assert r3.status_code == 400

        # Attempt 4: Standard email -> MUST be blocked with 429!
        r4 = client.post("/api/auth3/layer2_verify_otp", json={"email": "senat6031@gmail.com", "otp_code": "000004"})
        assert r4.status_code == 429, f"Normalization bypass detected! Got {r4.status_code}"
        assert r4.json().get("rate_limited") is True

    def test_adv_8_multithreaded_concurrency_stress(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Concurrency stress test: 20 concurrent threads attempting wrong OTP verify simultaneously.

        Adversarial Assertions:
        1. All 20 threads complete without unhandled 500 exceptions.
        2. No thread is ever granted successful verification (all ok=False).
        3. At least (num_threads - 3) threads must receive HTTP 429 rate limit.
        4. No more than 3 attempts in total receive HTTP 400 (if strict rate-limiting holds).
        5. After all concurrent requests conclude, the user is solidly locked out with HTTP 429.
        """
        email = "senat6031@gmail.com"
        client.post("/api/auth3/forgot_password_send_otp", json={"email": email, "send_gmail": False})

        num_threads = 20
        barrier = threading.Barrier(num_threads)

        def worker(thread_idx: int):
            barrier.wait()
            resp = client.post(
                "/api/auth3/layer2_verify_otp",
                json={"email": email, "otp_code": f"888{thread_idx:03d}"},
            )
            return resp

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]
            responses = [f.result() for f in futures]

        status_codes = [r.status_code for r in responses]
        num_400 = status_codes.count(400)
        num_429 = status_codes.count(429)

        # 1. Zero 500s or unexpected errors
        assert set(status_codes).issubset({400, 429}), f"Unexpected status codes: {status_codes}"

        # 2. None succeeded
        for r in responses:
            assert r.json().get("ok") is False

        # 3. Post-concurrency verification: subsequent attempt MUST be strictly 429
        post_attempt = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": email, "otp_code": "999999"},
        )
        assert post_attempt.status_code == 429, (
            f"Expected post-concurrency lockout with 429, got {post_attempt.status_code}: {post_attempt.text}"
        )
        assert post_attempt.json().get("rate_limited") is True

        # 4. Strict concurrency rate limit enforcement:
        # At most 3 failed attempts are permitted in the 5-minute window;
        # all remaining concurrent threads (at least 17 of 20) MUST be throttled with HTTP 429.
        assert num_400 <= 3, (
            f"Concurrency rate limit bypass: expected at most 3 HTTP 400 attempts, but got {num_400}!"
        )
        assert num_429 >= num_threads - 3, (
            f"Expected at least {num_threads - 3} HTTP 429 responses, got {num_429}"
        )
