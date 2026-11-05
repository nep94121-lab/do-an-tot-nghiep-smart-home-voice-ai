"""Test Suite for Requirement 1 (R1 Security):
Removal of OTP Test Fields from Production & Vercel API Responses.

Assertions:
1. In simulated production (PYTEST unset, VERCEL unset, app.testing=False), neither fresh nor
   cooldown/idempotent responses contain `otp_code_for_test` or `demo_otp_preview`.
2. When VERCEL env is set (e.g. VERCEL='1'), test fields are unconditionally excluded,
   even if PYTEST='1' or app.testing=True.
3. In local pytest environment (PYTEST='1', app.testing=True, VERCEL unset), test fields
   remain available for internal testing compatibility.
4. Unit tests verifying `is_test_otp_fields_allowed(app)` truth table.
"""
from __future__ import annotations

import os
import threading
from typing import Any
import pytest
from starlette.testclient import TestClient

from simulator.server import app

try:
    from simulator.auth_3layer import is_test_otp_fields_allowed
except ImportError:
    is_test_otp_fields_allowed = None  # type: ignore[assignment]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clean_pending_otps_state():
    from simulator.api.routes_auth import get_auth_3layer_manager

    mgr = get_auth_3layer_manager()
    lock = getattr(mgr, "_otp_lock", threading.Lock())
    with lock:
        mgr.pending_otps.clear()
    yield
    with lock:
        mgr.pending_otps.clear()


class TestR1SecurityOtpResponseFields:
    """Security tests enforcing zero OTP leakage in production & Vercel environments."""

    def test_r1_production_mode_fresh_otp_never_contains_test_fields(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fresh OTP request in production mode must NOT contain otp_code_for_test or demo_otp_preview."""
        monkeypatch.delenv("PYTEST", raising=False)
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.setattr(app, "testing", False, raising=False)

        resp = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": False},
        )
        assert resp.status_code == 200, f"Unexpected status: {resp.status_code}, body={resp.text}"
        data = resp.json()
        assert data.get("ok") is True

        # Assert no OTP test fields leaked
        assert "otp_code_for_test" not in data, f"Security Violation: otp_code_for_test leaked in prod response: {data}"
        assert "demo_otp_preview" not in data, f"Security Violation: demo_otp_preview leaked in prod response: {data}"

    def test_r1_production_mode_cooldown_idempotent_never_contains_test_fields(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cooldown/idempotent OTP request in production mode must NOT contain otp_code_for_test or demo_otp_preview."""
        monkeypatch.delenv("PYTEST", raising=False)
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.setattr(app, "testing", False, raising=False)

        # 1st request (fresh)
        resp1 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": True},
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1.get("ok") is True
        assert "otp_code_for_test" not in data1
        assert "demo_otp_preview" not in data1

        # 2nd request within cooldown period (idempotent)
        resp2 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": True},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2.get("ok") is True
        assert data2.get("idempotent") is True
        assert data2.get("cooldown_active") is True

        # Assert cooldown response does NOT leak existing OTP
        assert "otp_code_for_test" not in data2, f"Security Violation: cooldown leaked otp_code_for_test: {data2}"
        assert "demo_otp_preview" not in data2, f"Security Violation: cooldown leaked demo_otp_preview: {data2}"

    def test_r1_vercel_environment_unconditionally_forces_test_fields_off_even_with_pytest_flag(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """In Vercel environment, test fields are unconditionally blocked even if PYTEST=1 or app.testing=True."""
        monkeypatch.setenv("VERCEL", "1")
        monkeypatch.setenv("PYTEST", "1")
        monkeypatch.setattr(app, "testing", True, raising=False)

        # Fresh request
        resp1 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": False},
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert "otp_code_for_test" not in data1, f"Security Violation: Vercel leaked otp_code_for_test: {data1}"
        assert "demo_otp_preview" not in data1, f"Security Violation: Vercel leaked demo_otp_preview: {data1}"

        # Cooldown request
        resp2 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": False},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2.get("idempotent") is True
        assert "otp_code_for_test" not in data2, f"Security Violation: Vercel cooldown leaked otp_code_for_test: {data2}"
        assert "demo_otp_preview" not in data2, f"Security Violation: Vercel cooldown leaked demo_otp_preview: {data2}"

    def test_r1_local_pytest_mode_permits_test_fields_when_vercel_unset(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """In local pytest mode (VERCEL unset, PYTEST=1), test fields are included for legacy test suites."""
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.setenv("PYTEST", "1")
        monkeypatch.setattr(app, "testing", True, raising=False)

        # Fresh request with send_gmail=False
        resp1 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": False},
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert "otp_code_for_test" in data1, "Local pytest expected otp_code_for_test"
        assert "demo_otp_preview" in data1, "Local pytest expected demo_otp_preview"
        assert len(data1["otp_code_for_test"]) == 6
        assert data1["otp_code_for_test"].isdigit()

        # Cooldown request
        resp2 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": False},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2.get("idempotent") is True
        assert "otp_code_for_test" in data2
        assert "demo_otp_preview" in data2
        assert data2["otp_code_for_test"] == data1["otp_code_for_test"]

    def test_r1_is_test_otp_fields_allowed_unit_logic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unit test for is_test_otp_fields_allowed truth table."""
        assert is_test_otp_fields_allowed is not None, "is_test_otp_fields_allowed must be defined in simulator.auth_3layer"

        class DummyApp:
            testing = False

        dummy = DummyApp()

        # 1. Default production: all unset
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.delenv("PYTEST", raising=False)
        dummy.testing = False
        assert is_test_otp_fields_allowed(dummy) is False
        assert is_test_otp_fields_allowed(None) is False

        # 2. VERCEL environment: unconditional veto
        monkeypatch.setenv("VERCEL", "1")
        monkeypatch.setenv("PYTEST", "1")
        dummy.testing = True
        assert is_test_otp_fields_allowed(dummy) is False
        assert is_test_otp_fields_allowed(None) is False

        # 3. PYTEST='1' when VERCEL unset
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.setenv("PYTEST", "1")
        dummy.testing = False
        assert is_test_otp_fields_allowed(dummy) is True
        assert is_test_otp_fields_allowed(None) is True

        # 4. app.testing=True when VERCEL unset and PYTEST unset
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.delenv("PYTEST", raising=False)
        dummy.testing = True
        assert is_test_otp_fields_allowed(dummy) is True
