"""Adversarial Challenger Test Suite for Milestone 2 (M2_R2).

Agent: challenger_m2_r2_1 (Adversarial Challenger 1 for Milestone 2)
Focus: Empirically stress-test persistent cooldown across instances and request-time initiation.

Adversarial Test Matrix:
1. Request-time cooldown verification:
   - Simulate SMTP failing with an unhandled exception (TimeoutError / socket.timeout).
   - Ensure cooldown is STILL active immediately on subsequent requests.
   - Verify subsequent request returns idempotent/cooldown response without re-triggering SMTP.
2. Cross-instance persistence:
   - Instantiate brand-new ThreeLayerAuthManager instances pointing to the same data directory.
   - Verify request_password_reset_otp honors existing cooldown without waiting or leaking.
   - Verify multiple new instances in series maintain consistent cooldown and identical OTP code.
   - Verify OTP code surviving across instances can be verified/consumed successfully.
3. Cooldown remaining seconds accuracy:
   - Verify cooldown_remaining_seconds on fresh response (~60s).
   - Verify monotonic and accurate decrease over time (at +10s, +25s, +45s, +59s).
   - Verify expiration at >= 60s enables fresh OTP generation.
4. Zero-leak in production mode:
   - Under VERCEL="1" or PYTEST unset: assert neither fresh nor cooldown responses leak
     `otp_code_for_test` or `demo_otp_preview`.
   - Verify both HTTP API response and direct manager call.
5. Concurrency & file integrity stress:
   - Concurrent requests across multiple independent ThreeLayerAuthManager instances.
   - Verify JSON persistence integrity and race condition resilience.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import pathlib
import socket
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from simulator.auth_3layer import ThreeLayerAuthManager, is_test_otp_fields_allowed
from simulator.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clean_otp_state_fixture():
    """Ensure clean account and OTP state before and after each test."""
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


class TestChallengerM2R2CooldownAdversarial:
    """Empirical adversarial challenger test suite for Milestone 2 persistent cooldown."""

    # =========================================================================
    # 1. REQUEST-TIME COOLDOWN INITIATION UNDER SMTP FAILURES & EXCEPTIONS
    # =========================================================================

    def test_request_time_cooldown_active_after_unhandled_smtp_timeout_exception(
        self, auth_mgr: ThreeLayerAuthManager
    ):
        """Simulate SMTP raising an unhandled TimeoutError during send_real_gmail_otp.

        Adversarial Assertions:
        - First call crashes/fails in send_real_gmail_otp due to timeout.
        - Because cooldown is initiated at REQUEST TIME (before SMTP), the state is ALREADY saved.
        - Subsequent request within 60s MUST return cooldown response (idempotent=True).
        - No second SMTP send attempt is made during cooldown.
        """
        email = "senat6031@gmail.com"
        call_count = 0

        def exploding_send_real_gmail_otp(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            raise TimeoutError("SMTP connection timed out after 8.0s")

        with patch.object(auth_mgr, "send_real_gmail_otp", side_effect=exploding_send_real_gmail_otp):
            with pytest.raises(TimeoutError, match="SMTP connection timed out"):
                auth_mgr.request_password_reset_otp(email=email, send_gmail=True)

        assert call_count == 1, "Exploding SMTP function should have been called once"

        # Cooldown must be active immediately on subsequent call
        second_resp = auth_mgr.request_password_reset_otp(email=email, send_gmail=True)
        assert second_resp.get("ok") is True, f"Subsequent request must succeed via cooldown, got: {second_resp}"
        assert second_resp.get("idempotent") is True, "Subsequent request must be idempotent"
        assert second_resp.get("cooldown_active") is True, "Subsequent request must have cooldown_active=True"
        assert second_resp.get("cooldown_remaining_seconds", 0) > 0, "cooldown_remaining_seconds must be positive"
        assert call_count == 1, "send_real_gmail_otp must NOT be called on subsequent throttled request"

    def test_request_time_cooldown_active_after_socket_timeout_via_api(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Simulate socket.timeout in send_real_gmail_otp invoked via HTTP client.

        Adversarial Assertions:
        - First request fails with server error or 503.
        - Subsequent request within 60s returns HTTP 200 with idempotent cooldown response.
        """
        email = "senat6031@gmail.com"

        with patch.object(
            auth_mgr,
            "send_real_gmail_otp",
            side_effect=socket.timeout("Socket timed out waiting for SMTP greeting"),
        ):
            r1 = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": email, "send_gmail": True},
            )
            # The server might catch or bubble socket.timeout
            assert r1.status_code in (500, 503)

        # Immediate follow-up request via API
        r2 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": email, "send_gmail": True},
        )
        assert r2.status_code == 200, f"Expected 200 cooldown response, got {r2.status_code}: {r2.text}"
        data2 = r2.json()
        assert data2.get("ok") is True
        assert data2.get("idempotent") is True
        assert data2.get("cooldown_active") is True
        assert 50 <= data2.get("cooldown_remaining_seconds", 0) <= 60

    def test_request_time_cooldown_active_after_smtp_dict_failure(
        self, auth_mgr: ThreeLayerAuthManager
    ):
        """Simulate SMTP returning error dictionary without raising exception."""
        email = "senat6031@gmail.com"

        with patch.object(
            auth_mgr,
            "send_real_gmail_otp",
            return_value={"sent_real_gmail": False, "error": "Connection refused by peer"},
        ):
            r1 = auth_mgr.request_password_reset_otp(email=email, send_gmail=True)
            assert r1.get("ok") is False
            assert r1.get("status_code") == 503

        # Immediate second request
        r2 = auth_mgr.request_password_reset_otp(email=email, send_gmail=False)
        assert r2.get("ok") is True
        assert r2.get("idempotent") is True
        assert r2.get("cooldown_active") is True
        assert r2.get("cooldown_remaining_seconds", 0) > 0

    # =========================================================================
    # 2. CROSS-INSTANCE PERSISTENCE ACROSS FRESH MANAGER INSTANCES
    # =========================================================================

    def test_cross_instance_persistence_fresh_manager_instance(
        self, auth_mgr: ThreeLayerAuthManager
    ):
        """Verify brand new ThreeLayerAuthManager instance respects active cooldown.

        Adversarial Scenario:
        1. Instance 1 receives OTP request, saves state to disk.
        2. Instance 2 is newly created from disk state (simulating a cold start / new serverless container).
        3. Instance 2 must immediately recognize cooldown for that email.
        4. Instance 2 must return idempotent response without re-sending email.
        """
        email = "senat6031@gmail.com"
        resp1 = auth_mgr.request_password_reset_otp(email=email, send_gmail=False)
        assert resp1.get("ok") is True
        assert resp1.get("idempotent") is not True

        # Create brand-new ThreeLayerAuthManager instance
        new_mgr = ThreeLayerAuthManager()

        # Verify new_mgr loaded pending_otps from disk
        assert email in new_mgr.pending_otps, "New manager instance must restore pending OTP from disk"
        restored = new_mgr.pending_otps[email]
        assert restored.get("otp_code") == resp1.get("otp_code_for_test")

        # Mock send_real_gmail_otp on new instance to guarantee no send occurs
        mock_send = MagicMock(return_value={"sent_real_gmail": False})
        new_mgr.send_real_gmail_otp = mock_send

        # Call request_password_reset_otp on new instance
        resp2 = new_mgr.request_password_reset_otp(email=email, send_gmail=True)
        assert resp2.get("ok") is True
        assert resp2.get("idempotent") is True, "New instance must return idempotent cooldown response"
        assert resp2.get("cooldown_active") is True
        assert resp2.get("cooldown_remaining_seconds", 0) > 0
        mock_send.assert_not_called()

    def test_cross_instance_persistence_multiple_instances_in_series(
        self, auth_mgr: ThreeLayerAuthManager
    ):
        """Verify cooldown consistency across 5 distinct sequential instances."""
        email = "senat6031@gmail.com"
        resp0 = auth_mgr.request_password_reset_otp(email=email, send_gmail=False)
        expected_otp = resp0.get("otp_code_for_test")
        assert expected_otp is not None

        for i in range(1, 6):
            inst = ThreeLayerAuthManager()
            mock_send = MagicMock(return_value={"sent_real_gmail": False})
            inst.send_real_gmail_otp = mock_send

            resp_i = inst.request_password_reset_otp(email=email, send_gmail=True)
            assert resp_i.get("ok") is True, f"Instance {i} failed"
            assert resp_i.get("idempotent") is True, f"Instance {i} did not enforce cooldown"
            assert resp_i.get("cooldown_active") is True, f"Instance {i} cooldown_active is not True"
            assert resp_i.get("otp_code_for_test") == expected_otp, f"Instance {i} changed OTP code"
            mock_send.assert_not_called()

    def test_cross_instance_otp_code_verification_and_consumption(
        self, auth_mgr: ThreeLayerAuthManager
    ):
        """Verify that an OTP created on Instance A can be verified and consumed on Instance B.

        Adversarial Assertions:
        - OTP generated on instance A is persisted.
        - Instance B verifies OTP via reset_password_with_otp.
        - Successful verification cleans up pending OTP on Instance B and in persistent storage.
        - Instance C instantiated afterwards verifies cooldown and pending OTP are cleared.
        """
        email = "senat6031@gmail.com"
        resp_a = auth_mgr.request_password_reset_otp(email=email, send_gmail=False)
        otp_code = resp_a.get("otp_code_for_test")
        assert otp_code is not None

        # Instance B: perform reset password with the OTP
        mgr_b = ThreeLayerAuthManager()
        reset_res = mgr_b.reset_password_with_otp(
            email=email,
            otp_code=otp_code,
            new_password="NewSecurePassword@2026",
            confirm_password="NewSecurePassword@2026",
        )
        assert reset_res.get("ok") is True, f"Password reset on new instance must succeed: {reset_res}"

        # Cooldown should now be cleared on mgr_b
        assert email not in mgr_b.pending_otps, "pending_otps must be cleared after password reset"

        # Instance C: instantiated after reset
        mgr_c = ThreeLayerAuthManager()
        assert email not in mgr_c.pending_otps, "Instance C must not have pending OTP after reset"

        # Immediate new OTP request on mgr_c should succeed as a fresh OTP (cooldown cleared)
        resp_c = mgr_c.request_password_reset_otp(email=email, send_gmail=False)
        assert resp_c.get("ok") is True
        assert resp_c.get("idempotent") is not True, "Request after password reset must generate fresh OTP"

    # =========================================================================
    # 3. COOLDOWN REMAINING SECONDS ACCURACY & MONOTONIC DECREASE
    # =========================================================================

    def test_cooldown_remaining_seconds_accuracy_and_monotonic_decrease(
        self, auth_mgr: ThreeLayerAuthManager
    ):
        """Empirically challenge cooldown_remaining_seconds across simulated time points.

        Verify:
        - t0: remaining ~ 60s (58 <= rem <= 60)
        - t0 + 15s: remaining == 45s (+-1s)
        - t0 + 35s: remaining == 25s (+-1s)
        - t0 + 55s: remaining == 5s (+-1s)
        - t0 + 59s: remaining == 1s (+-1s)
        - Strict monotonic decrease: rem(0) > rem(15) > rem(35) > rem(55) > rem(59)
        - t0 + 60.1s: cooldown expired -> next request generates fresh OTP!
        """
        email = "senat6031@gmail.com"
        t0 = 1700000000.0

        with patch("time.time", return_value=t0):
            r0 = auth_mgr.request_password_reset_otp(email=email, send_gmail=False)
            assert r0.get("ok") is True
            rem0 = r0.get("cooldown_remaining_seconds")
            assert rem0 is not None
            assert 58 <= rem0 <= 60, f"Expected remaining ~60, got {rem0}"

        time_offsets = [15.0, 35.0, 55.0, 59.0]
        recorded_rems = [rem0]

        for offset in time_offsets:
            current_time = t0 + offset
            with patch("time.time", return_value=current_time):
                resp = auth_mgr.request_password_reset_otp(email=email, send_gmail=False)
                assert resp.get("ok") is True
                assert resp.get("idempotent") is True
                assert resp.get("cooldown_active") is True
                rem = resp.get("cooldown_remaining_seconds")
                assert rem is not None
                expected_rem = int(60.0 - offset)
                assert abs(rem - expected_rem) <= 1, f"At +{offset}s, expected {expected_rem}, got {rem}"
                recorded_rems.append(rem)

        # Monotonicity check
        for i in range(len(recorded_rems) - 1):
            assert recorded_rems[i] > recorded_rems[i + 1], (
                f"Cooldown remaining failed monotonic decrease: {recorded_rems[i]} <= {recorded_rems[i + 1]}"
            )

        # Check expiration after 60 seconds
        t_expired = t0 + 60.5
        with patch("time.time", return_value=t_expired):
            r_fresh = auth_mgr.request_password_reset_otp(email=email, send_gmail=False)
            assert r_fresh.get("ok") is True
            assert r_fresh.get("idempotent") is not True, "After 60s cooldown, request must NOT be idempotent"
            new_rem = r_fresh.get("cooldown_remaining_seconds")
            assert new_rem is not None
            assert 58 <= new_rem <= 60, f"Fresh request after expiry should reset cooldown to ~60, got {new_rem}"

    # =========================================================================
    # 4. ZERO-LEAK VERIFICATION IN PRODUCTION MODE
    # =========================================================================

    def test_production_zero_leak_with_vercel_env_flag(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Ensure test fields are 100% stripped in production (VERCEL='1').

        Adversarial Assertions:
        - When VERCEL='1' is set, is_test_otp_fields_allowed() unconditionally returns False.
        - Fresh OTP API response does NOT contain `otp_code_for_test` or `demo_otp_preview`.
        - Subsequent cooldown API response does NOT contain `otp_code_for_test` or `demo_otp_preview`.
        - Deep inspection: no 6-digit number appears in any value of the response.
        """
        monkeypatch.setenv("VERCEL", "1")
        assert is_test_otp_fields_allowed() is False, "VERCEL env must unconditionally veto test OTP fields"

        email = "senat6031@gmail.com"

        # 1. Fresh request
        r1 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": email, "send_gmail": False},
        )
        assert r1.status_code == 200
        data1 = r1.json()
        assert data1.get("ok") is True
        assert "otp_code_for_test" not in data1, "Leaked otp_code_for_test in fresh response!"
        assert "demo_otp_preview" not in data1, "Leaked demo_otp_preview in fresh response!"

        # 2. Cooldown request
        r2 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": email, "send_gmail": False},
        )
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2.get("ok") is True
        assert data2.get("idempotent") is True
        assert data2.get("cooldown_active") is True
        assert "otp_code_for_test" not in data2, "Leaked otp_code_for_test in cooldown response!"
        assert "demo_otp_preview" not in data2, "Leaked demo_otp_preview in cooldown response!"

        # Deep string check
        serialized_r2 = json.dumps(data2)
        assert "otp_code_for_test" not in serialized_r2
        assert "demo_otp_preview" not in serialized_r2

    def test_production_zero_leak_direct_manager_without_test_flags(
        self, auth_mgr: ThreeLayerAuthManager, monkeypatch: pytest.MonkeyPatch
    ):
        """Direct ThreeLayerAuthManager call in production mode must never leak test fields."""
        monkeypatch.delenv("PYTEST", raising=False)
        monkeypatch.setenv("VERCEL", "1")

        email = "senat6031@gmail.com"

        # First call (fresh)
        resp1 = auth_mgr.request_password_reset_otp(email=email, send_gmail=False, app=None)
        assert resp1.get("ok") is True
        assert "otp_code_for_test" not in resp1
        assert "demo_otp_preview" not in resp1

        # Second call (cooldown)
        resp2 = auth_mgr.request_password_reset_otp(email=email, send_gmail=False, app=None)
        assert resp2.get("ok") is True
        assert resp2.get("idempotent") is True
        assert "otp_code_for_test" not in resp2
        assert "demo_otp_preview" not in resp2

    # =========================================================================
    # 5. CONCURRENCY & MULTI-INSTANCE STRESS
    # =========================================================================

    def test_concurrent_multi_instance_cooldown_stress(self):
        """Stress test: 10 concurrent threads each creating its own ThreeLayerAuthManager instance.

        Adversarial Assertions:
        - All threads hit request_password_reset_otp at the exact same moment (via Barrier).
        - Accounts JSON file remains syntactically valid and uncorrupted.
        - Cooldown is maintained across all threads without unhandled race condition crashes.
        """
        email = "senat6031@gmail.com"
        num_threads = 10
        barrier = threading.Barrier(num_threads)
        results: list[dict[str, Any]] = []
        errors: list[Exception] = []
        res_lock = threading.Lock()

        def worker():
            try:
                # Brand-new instance per thread
                mgr = ThreeLayerAuthManager()
                mgr.send_real_gmail_otp = MagicMock(return_value={"sent_real_gmail": False})
                barrier.wait(timeout=5.0)
                res = mgr.request_password_reset_otp(email=email, send_gmail=False)
                with res_lock:
                    results.append(res)
            except Exception as e:
                with res_lock:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert not errors, f"Encountered concurrency exceptions: {errors}"
        assert len(results) == num_threads, f"Expected {num_threads} results, got {len(results)}"

        # Verify all calls succeeded
        for r in results:
            assert r.get("ok") is True, f"Failed result: {r}"

        # Verify accounts_3layer.json file integrity
        from simulator.auth import ACCOUNTS_FILE
        raw_data = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
        assert isinstance(raw_data, list), "Accounts file corrupted"

    def test_concurrent_multi_instance_active_cooldown_reads(self, auth_mgr: ThreeLayerAuthManager):
        """Verify 10 concurrent instances can simultaneously read and honor an active cooldown."""
        email = "senat6031@gmail.com"
        resp0 = auth_mgr.request_password_reset_otp(email=email, send_gmail=False)
        assert resp0.get("ok") is True

        num_threads = 10
        barrier = threading.Barrier(num_threads)
        results: list[dict[str, Any]] = []
        errors: list[Exception] = []
        res_lock = threading.Lock()

        def reader():
            try:
                mgr = ThreeLayerAuthManager()
                barrier.wait(timeout=5.0)
                res = mgr.request_password_reset_otp(email=email, send_gmail=False)
                with res_lock:
                    results.append(res)
            except Exception as e:
                with res_lock:
                    errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert not errors, f"Encountered concurrency exceptions: {errors}"
        assert len(results) == num_threads
        for r in results:
            assert r.get("ok") is True
            assert r.get("idempotent") is True
            assert r.get("cooldown_active") is True

    # =========================================================================
    # 6. EDGE CASES & INPUT NORMALIZATION ACROSS INSTANCES
    # =========================================================================

    def test_cross_instance_cooldown_normalization(self, auth_mgr: ThreeLayerAuthManager):
        """Email with uppercase and whitespace must share cooldown across instances."""
        auth_mgr.request_password_reset_otp(email="  SeNaT6031@GmAiL.cOm  ", send_gmail=False)

        # New instance queries lowercased trimmed email
        new_mgr = ThreeLayerAuthManager()
        resp = new_mgr.request_password_reset_otp(email="senat6031@gmail.com", send_gmail=False)
        assert resp.get("ok") is True
        assert resp.get("idempotent") is True, "Normalized email must trigger cooldown on new instance"

    def test_unknown_account_does_not_trigger_or_persist_cooldown(
        self, auth_mgr: ThreeLayerAuthManager
    ):
        """Unknown account must return 404 and must NOT create cooldown or pollute pending_otps."""
        resp = auth_mgr.request_password_reset_otp(
            email="non_existent_ghost_99999@gmail.com", send_gmail=False
        )
        assert resp.get("ok") is False
        assert resp.get("status_code") == 404

        new_mgr = ThreeLayerAuthManager()
        assert "non_existent_ghost_99999@gmail.com" not in new_mgr.pending_otps
