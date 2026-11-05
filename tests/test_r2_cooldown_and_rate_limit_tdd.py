"""TDD Test Suite for Milestone 2 (R2): Persistent Cooldown and Rate-Limiting.

Requirements tested:
1. Cooldown starts at request time: even if sending fails or is mocked, subsequent requests
   within 60s return cooldown/idempotent response.
2. Fresh OTP response includes `cooldown_remaining_seconds` (e.g. 59 or 60).
3. Cooldown persistence: simulates state reloading (ThreeLayerAuthManager._load_state() or
   a fresh manager instance) demonstrating cooldown is preserved across instances for an email.
4. Failed OTP verify attempts are rate-limited: sending 3 incorrect OTPs within 5 minutes
   succeeds in returning 400 (invalid OTP), but the 4th attempt returns HTTP 429
   ("status_code": 429, "rate_limited": True).
5. Successful verification resets failed attempts counter.
6. Rate limit state persists across manager instances.
7. Frontend static verification: mobile_app.js and auth.js use cooldown_remaining_seconds.
"""

from __future__ import annotations

import os
import pathlib
import re
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


class TestR2PersistentCooldownAndRateLimitingTDD:
    """TDD Test cases for Requirement 2."""

    def test_r2_fresh_otp_response_includes_cooldown_remaining_seconds(
        self, client: TestClient
    ):
        """Fresh OTP response must include cooldown_remaining_seconds (58-60)."""
        res = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "senat6031@gmail.com", "send_gmail": False},
        )
        assert res.status_code == 200
        data = res.json()
        assert data.get("ok") is True
        assert data.get("idempotent") is not True
        assert "cooldown_remaining_seconds" in data, "Fresh OTP response must include cooldown_remaining_seconds"
        rem = data["cooldown_remaining_seconds"]
        assert isinstance(rem, (int, float))
        assert 50 <= rem <= 60, f"cooldown_remaining_seconds expected ~60, got {rem}"

    def test_r2_cooldown_starts_at_request_time_even_on_smtp_failure(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Cooldown starts at request time: even if sending fails, subsequent requests within 60s return cooldown/idempotent."""
        email = "senat6031@gmail.com"

        # Mock send_real_gmail_otp to simulate SMTP failure
        with patch.object(
            auth_mgr,
            "send_real_gmail_otp",
            return_value={"sent_real_gmail": False, "error": "SMTP server connection failed"},
        ):
            # First request: fails due to mocked SMTP error
            r1 = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": email, "send_gmail": True},
            )
            assert r1.status_code == 503
            assert r1.json().get("ok") is False

        # Second request: within 60s of request time -> should be throttled by cooldown!
        r2 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": email, "send_gmail": False},
        )
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2.get("ok") is True
        assert data2.get("idempotent") is True, "Subsequent request within 60s must be idempotent"
        assert data2.get("cooldown_active") is True, "Cooldown must be active after request time initiation"
        assert "cooldown_remaining_seconds" in data2
        assert 50 <= data2["cooldown_remaining_seconds"] <= 60

    def test_r2_cooldown_persists_across_manager_instances(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Cooldown persists across instances (simulated via fresh ThreeLayerAuthManager instance)."""
        email = "senat6031@gmail.com"

        # First request on current manager
        r1 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": email, "send_gmail": False},
        )
        assert r1.status_code == 200
        data1 = r1.json()
        assert data1.get("ok") is True

        # Simulate a new serverless function cold-start / instance
        fresh_mgr = ThreeLayerAuthManager()
        # Fresh manager must have restored the pending OTP and active cooldown
        res = fresh_mgr.request_password_reset_otp(email, send_gmail=False)
        assert res.get("ok") is True
        assert res.get("idempotent") is True, "Fresh instance must detect persistent active cooldown"
        assert res.get("cooldown_active") is True
        assert "cooldown_remaining_seconds" in res
        assert 50 <= res["cooldown_remaining_seconds"] <= 60

    def test_r2_failed_otp_verify_rate_limited_to_3_attempts_per_5_minutes(
        self, client: TestClient
    ):
        """Failed OTP verify attempts are rate-limited: 3 incorrect OTPs return 400, 4th returns 429."""
        email = "senat6031@gmail.com"

        # Request OTP first
        r_init = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": email, "send_gmail": False},
        )
        assert r_init.status_code == 200

        # Attempt 1: incorrect OTP -> 400
        r_fail1 = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": email, "otp_code": "000001"},
        )
        assert r_fail1.status_code == 400
        assert r_fail1.json().get("ok") is False
        assert r_fail1.json().get("rate_limited") is not True

        # Attempt 2: incorrect OTP -> 400
        r_fail2 = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": email, "otp_code": "000002"},
        )
        assert r_fail2.status_code == 400
        assert r_fail2.json().get("ok") is False
        assert r_fail2.json().get("rate_limited") is not True

        # Attempt 3: incorrect OTP -> 400
        r_fail3 = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": email, "otp_code": "000003"},
        )
        assert r_fail3.status_code == 400
        assert r_fail3.json().get("ok") is False
        assert r_fail3.json().get("rate_limited") is not True

        # Attempt 4: 4th attempt within 5 minutes -> MUST return 429 Too Many Requests
        r_fail4 = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": email, "otp_code": "000004"},
        )
        assert r_fail4.status_code == 429, f"Expected 429, got {r_fail4.status_code}: {r_fail4.text}"
        data4 = r_fail4.json()
        assert data4.get("ok") is False
        assert data4.get("rate_limited") is True
        assert data4.get("status_code") == 429
        assert "quá 3 lần" in data4.get("error", "")

    def test_r2_rate_limit_resets_on_successful_verification(
        self, client: TestClient, auth_mgr: ThreeLayerAuthManager
    ):
        """Successful OTP verification clears failed attempts."""
        email = "senat6031@gmail.com"

        # Request OTP
        r_init = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": email, "send_gmail": False},
        )
        assert r_init.status_code == 200

        # Attempt 1 and 2: incorrect OTP
        client.post("/api/auth3/layer2_verify_otp", json={"email": email, "otp_code": "000001"})
        client.post("/api/auth3/layer2_verify_otp", json={"email": email, "otp_code": "000002"})

        # Get the real OTP code from pending_otps
        real_otp = auth_mgr.pending_otps[email]["otp_code"]

        # Attempt 3: correct OTP -> succeeds
        r_succ = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": email, "otp_code": real_otp},
        )
        assert r_succ.status_code == 200
        assert r_succ.json().get("ok") is True

        # Verify failed attempts counter was reset
        acc = auth_mgr.find_account(email)
        assert not acc.get("otp_failed_verify_attempts")
        if hasattr(auth_mgr, "otp_failed_attempts"):
            assert len(auth_mgr.otp_failed_attempts.get(email, [])) == 0

    def test_r2_rate_limit_persists_across_manager_instances(
        self, client: TestClient
    ):
        """Rate limit on failed attempts persists across instances."""
        email = "senat6031@gmail.com"

        # Request OTP
        client.post("/api/auth3/forgot_password_send_otp", json={"email": email, "send_gmail": False})

        # 3 failed attempts
        for i in range(1, 4):
            client.post("/api/auth3/layer2_verify_otp", json={"email": email, "otp_code": f"00000{i}"})

        # Fresh manager instance
        fresh_mgr = ThreeLayerAuthManager()
        res = fresh_mgr.layer2_verify_otp(email, "000004")
        assert res.get("status_code") == 429, f"Fresh instance must enforce 429 rate limit, got {res}"
        assert res.get("rate_limited") is True

    def test_r2_frontend_countdown_uses_cooldown_remaining_seconds(self):
        """Frontend files must use cooldown_remaining_seconds instead of hardcoded 60s."""
        mobile_js = (ROOT / "simulator" / "static" / "js" / "mobile_app.js").read_text(encoding="utf-8")
        assert "cooldown_remaining_seconds" in mobile_js, "mobile_app.js must reference cooldown_remaining_seconds"
        assert not re.search(r"let\s+countdown\s*=\s*60\s*;", mobile_js), "mobile_app.js must not hardcode countdown to 60"

        auth_js = (ROOT / "simulator" / "static" / "js" / "auth.js").read_text(encoding="utf-8")
        assert "cooldown_remaining_seconds" in auth_js, "auth.js must reference cooldown_remaining_seconds"
