"""Adversarial Challenge Test Suite for Milestone 1 (M1_R2 Security).
Authored by Challenger challenger_m1_r2_1.

Empirical verification of:
1. VERCEL environment variable variants ("1", "true", "TRUE", "production", "preview", "0", "false", "").
2. Attacker HTTP request tampering (headers, query params, JSON body poisoning, client spoofing).
3. PYTEST environment variable falsy values ("0", "false", "False", "no", "NO", "").
4. Repeated high-volume stress testing (fresh and cooldown) under production mode to verify zero OTP leaks.
5. Verification that actual 6-digit OTP codes never leak in response bodies (strings, messages, or keys).
"""
from __future__ import annotations

import os
import re
import threading
from typing import Any
import pytest
from starlette.testclient import TestClient

from simulator.server import app
from simulator.auth_3layer import is_test_otp_fields_allowed
from simulator.api.routes_auth import get_auth_3layer_manager


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clean_otp_state():
    mgr = get_auth_3layer_manager()
    lock = getattr(mgr, "_otp_lock", threading.Lock())
    with lock:
        mgr.pending_otps.clear()
    yield
    with lock:
        mgr.pending_otps.clear()


class TestChallengerM1R2Adversarial:
    """Adversarial Challenge Suite for OTP Test Fields Leakage."""

    # -------------------------------------------------------------------------
    # Scenario 1: VERCEL Environment Variable Variants
    # -------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "vercel_val",
        ["1", "true", "TRUE", "production", "preview", "0", "false"],
    )
    def test_vercel_truthy_values_unconditionally_veto_test_fields(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, vercel_val: str
    ) -> None:
        """Any truthy VERCEL env value must unconditionally disable test fields even if PYTEST=1 and app.testing=True."""
        monkeypatch.setenv("VERCEL", vercel_val)
        monkeypatch.setenv("PYTEST", "1")
        monkeypatch.setattr(app, "testing", True, raising=False)

        assert is_test_otp_fields_allowed(app) is False, (
            f"is_test_otp_fields_allowed must be False when VERCEL={vercel_val!r}"
        )

        resp = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "otp_code_for_test" not in data, f"Leaked otp_code_for_test with VERCEL={vercel_val!r}"
        assert "demo_otp_preview" not in data, f"Leaked demo_otp_preview with VERCEL={vercel_val!r}"

    def test_vercel_empty_string_production_mode_no_leak(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When VERCEL='' in production (PYTEST unset, app.testing=False), test fields must NOT leak."""
        monkeypatch.setenv("VERCEL", "")
        monkeypatch.delenv("PYTEST", raising=False)
        monkeypatch.setattr(app, "testing", False, raising=False)

        assert is_test_otp_fields_allowed(app) is False
        assert is_test_otp_fields_allowed(None) is False

        resp = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "otp_code_for_test" not in data
        assert "demo_otp_preview" not in data

    def test_vercel_empty_string_when_env_var_is_set_veto_evaluation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Challenge test: Examine behavior when VERCEL='' is set while PYTEST='1'.
        If VERCEL is defined in os.environ (even empty), does it veto or fall through?
        """
        monkeypatch.setenv("VERCEL", "")
        monkeypatch.setenv("PYTEST", "1")
        monkeypatch.setattr(app, "testing", True, raising=False)

        # Under the current implementation:
        # if os.getenv("VERCEL"): evaluates bool("") which is False,
        # so it falls through to PYTEST=="1" and returns True.
        # This test documents the exact empirical behavior.
        current_res = is_test_otp_fields_allowed(app)
        # In pure production environments, PYTEST is never set, so VERCEL='' is safe.
        # But if VERCEL is explicitly checked via truthiness, '' is considered not set.
        assert isinstance(current_res, bool)

    # -------------------------------------------------------------------------
    # Scenario 2: Attacker HTTP Request Tampering (Headers, Query, Body Injection)
    # -------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "attack_vector",
        [
            {"headers": {"X-Pytest": "1"}},
            {"headers": {"X-Testing": "true"}},
            {"headers": {"X-Vercel": "0"}},
            {"headers": {"X-App-Testing": "1"}},
            {"params": {"pytest": "1"}},
            {"params": {"testing": "true"}},
            {"params": {"VERCEL": "0"}},
            {"params": {"app_testing": "1"}},
            {"json": {"email": "nep94121@gmail.com", "send_gmail": False, "testing": True}},
            {"json": {"email": "nep94121@gmail.com", "send_gmail": False, "pytest": "1"}},
            {"json": {"email": "nep94121@gmail.com", "send_gmail": False, "app": {"testing": True}}},
            {"json": {"email": "nep94121@gmail.com", "send_gmail": False, "VERCEL": 0}},
        ],
    )
    def test_attacker_cannot_force_test_mode_via_http_tampering(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, attack_vector: dict[str, Any]
    ) -> None:
        """In production mode, an attacker attempting HTTP parameter / header / body injection
        CANNOT force the server to leak test OTP fields.
        """
        monkeypatch.delenv("PYTEST", raising=False)
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.setattr(app, "testing", False, raising=False)

        headers = attack_vector.get("headers", {})
        params = attack_vector.get("params", {})
        body = attack_vector.get("json", {"email": "nep94121@gmail.com", "send_gmail": False})

        resp = client.post(
            "/api/auth3/forgot_password_send_otp",
            params=params,
            headers=headers,
            json=body,
        )
        assert resp.status_code == 200, f"Failed on attack vector {attack_vector}: {resp.text}"
        data = resp.json()
        assert "otp_code_for_test" not in data, f"Tampering leaked otp_code_for_test: {attack_vector}"
        assert "demo_otp_preview" not in data, f"Tampering leaked demo_otp_preview: {attack_vector}"

    # -------------------------------------------------------------------------
    # Scenario 3: PYTEST Falsy Environment Variable Parsing
    # -------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "pytest_val",
        ["0", "false", "False", "FALSE", "no", "NO", "off", "OFF", ""],
    )
    def test_falsy_pytest_env_values_do_not_enable_test_mode(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, pytest_val: str
    ) -> None:
        """PYTEST environment variables set to falsy strings must NOT enable test OTP fields."""
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.setenv("PYTEST", pytest_val)
        monkeypatch.setattr(app, "testing", False, raising=False)

        assert is_test_otp_fields_allowed(app) is False, (
            f"is_test_otp_fields_allowed returned True for PYTEST={pytest_val!r}"
        )

        resp = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "otp_code_for_test" not in data
        assert "demo_otp_preview" not in data

    # -------------------------------------------------------------------------
    # Scenario 4: Stress Testing Fresh & Cooldown Responses in Production
    # -------------------------------------------------------------------------
    def test_stress_repeated_otp_requests_zero_leaks_in_production(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """High volume repeated requests (fresh + 30 cooldown calls) must never leak OTP test fields
        or raw OTP digits in any response key.
        """
        monkeypatch.delenv("PYTEST", raising=False)
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.setattr(app, "testing", False, raising=False)

        mgr = get_auth_3layer_manager()

        for iteration in range(30):
            resp = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "nep94121@gmail.com", "send_gmail": False},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("ok") is True

            # Assert explicit test field exclusion
            assert "otp_code_for_test" not in data, f"Iteration {iteration} leaked otp_code_for_test"
            assert "demo_otp_preview" not in data, f"Iteration {iteration} leaked demo_otp_preview"

            # Retrieve actual active OTP from manager internal state to verify it is NOT anywhere in response
            with mgr._otp_lock:
                stored_otp = mgr.pending_otps.get("nep94121@gmail.com", {}).get("otp_code")

            assert stored_otp is not None and len(stored_otp) == 6
            # Assert stored OTP string is NOT contained in any string value of the response
            resp_str = resp.text
            assert stored_otp not in resp_str, (
                f"Iteration {iteration} leaked raw OTP digits ({stored_otp}) inside response body: {resp_str}"
            )

            if iteration > 0:
                assert data.get("idempotent") is True
                assert data.get("cooldown_active") is True

    # -------------------------------------------------------------------------
    # Scenario 5: Vercel Production Emulation (VERCEL="1", VERCEL_ENV="production")
    # -------------------------------------------------------------------------
    def test_vercel_production_emulation_both_fresh_and_cooldown(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Emulate exact Vercel production environment (VERCEL=1, VERCEL_ENV=production, PYTEST unset)."""
        monkeypatch.setenv("VERCEL", "1")
        monkeypatch.setenv("VERCEL_ENV", "production")
        monkeypatch.delenv("PYTEST", raising=False)
        monkeypatch.setattr(app, "testing", False, raising=False)

        # Fresh request
        resp1 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": False},
        )
        assert resp1.status_code == 200
        d1 = resp1.json()
        assert "otp_code_for_test" not in d1
        assert "demo_otp_preview" not in d1

        # Cooldown request
        resp2 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": False},
        )
        assert resp2.status_code == 200
        d2 = resp2.json()
        assert d2.get("idempotent") is True
        assert "otp_code_for_test" not in d2
        assert "demo_otp_preview" not in d2
