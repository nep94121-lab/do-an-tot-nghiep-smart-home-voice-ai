"""Adversarial Concurrency and Boundary Stress Test Suite for Milestone 1 (M1_R2).

Evaluates:
1. Concurrency safety under heavy bursts (20-50 concurrent calls to /api/auth3/forgot_password_send_otp).
2. Absolute zero leakage of `otp_code_for_test` and `demo_otp_preview` across all concurrent responses.
3. Deep payload inspection: verified OTP code does not leak into any key, value, message, or delivery metadata.
4. Boundary coverage:
   - Allowlisted existing users (Tier 2/3)
   - Non-allowlisted existing users (Tier 1 Owner & non-allowlisted accounts)
   - Non-existing users / strangers
   - Malformed / empty / boundary email formats
5. Simulated production mode and Vercel mode under concurrent thread load.
6. Thread-safety and absence of deadlocks in `ThreeLayerAuthManager._otp_lock`.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import threading
from typing import Any
import pytest
from starlette.testclient import TestClient

from simulator.api.routes_auth import get_auth_3layer_manager
from simulator.auth_3layer import is_test_otp_fields_allowed
from simulator.server import app


@pytest.fixture(autouse=True)
def ensure_test_accounts():
    mgr = get_auth_3layer_manager()
    test_emails = {
        "thanhvien_test_c2@gmail.com": 2,
        "khach_test_c3@gmail.com": 3,
        "con_yeu_family@gmail.com": 2,
    }
    existing_emails = {acc.get("email", "").lower() for acc in mgr.accounts}
    added = []
    for em, tier in test_emails.items():
        if em not in existing_emails:
            acc = {
                "account_id": em.split("@")[0],
                "email": em,
                "display_name": em.split("@")[0],
                "tier": tier,
                "role": "MEMBER" if tier == 2 else "CHILD_GUEST",
            }
            mgr.accounts.append(acc)
            added.append(acc)
    yield
    for acc in added:
        if acc in mgr.accounts:
            mgr.accounts.remove(acc)


@pytest.fixture
def clean_pending_otps():
    mgr = get_auth_3layer_manager()
    lock = getattr(mgr, "_otp_lock", threading.Lock())
    with lock:
        mgr.pending_otps.clear()
    yield
    with lock:
        mgr.pending_otps.clear()


def _recursively_find_leak(data: Any, sensitive_keys=("otp_code_for_test", "demo_otp_preview")) -> list[str]:
    """Recursively search for sensitive keys in any nested dict or list."""
    leaks = []
    if isinstance(data, dict):
        for k, v in data.items():
            if k in sensitive_keys:
                leaks.append(f"Found sensitive key '{k}': {v}")
            leaks.extend(_recursively_find_leak(v, sensitive_keys))
    elif isinstance(data, list):
        for item in data:
            leaks.extend(_recursively_find_leak(item, sensitive_keys))
    return leaks


class TestChallengerM1R2Concurrency:
    """Adversarial concurrency & boundary challenger for Milestone 1."""

    def test_m1_concurrency_30_burst_same_user_zero_leak(
        self, monkeypatch: pytest.MonkeyPatch, clean_pending_otps
    ) -> None:
        """30 concurrent calls hitting the same existing email in production mode.
        
        Tests race conditions between fresh generation and cooldown caching.
        Asserts 100% of responses contain zero OTP fields.
        """
        monkeypatch.delenv("PYTEST", raising=False)
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.setattr(app, "testing", False, raising=False)

        client = TestClient(app, raise_server_exceptions=False)
        email = "nep94121@gmail.com"
        num_requests = 30

        def send_request(idx: int) -> tuple[int, dict[str, Any], str]:
            resp = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": email, "send_gmail": False, "source": f"BurstWorker-{idx}"},
            )
            return resp.status_code, resp.json(), resp.text

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(send_request, i) for i in range(num_requests)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == num_requests
        idempotent_count = 0
        fresh_count = 0

        for status_code, body, raw_text in results:
            assert status_code == 200, f"Expected 200 OK, got {status_code}: {raw_text}"
            assert body.get("ok") is True

            # Assert zero leakage in dictionary keys
            leaks = _recursively_find_leak(body)
            assert not leaks, f"Leakage detected in response: {leaks}"

            # Assert zero leakage in raw JSON string
            assert "otp_code_for_test" not in raw_text, f"Raw text contains otp_code_for_test: {raw_text}"
            assert "demo_otp_preview" not in raw_text, f"Raw text contains demo_otp_preview: {raw_text}"

            if body.get("idempotent") is True:
                idempotent_count += 1
            else:
                fresh_count += 1

        # At least one request created the OTP, subsequent ones hit cooldown
        assert fresh_count >= 1, "Expected at least 1 fresh OTP creation"
        assert idempotent_count >= 1, "Expected concurrent requests to hit idempotent cooldown branch"
        assert fresh_count + idempotent_count == num_requests

    def test_m1_concurrency_50_mixed_matrix_zero_leak(
        self, monkeypatch: pytest.MonkeyPatch, clean_pending_otps
    ) -> None:
        """50 concurrent requests hitting a diverse matrix of user categories.
        
        Matrix includes:
        - Existing allowlisted users
        - Existing non-allowlisted users
        - Non-existing users
        - Boundary emails (spaces, case insensitivity, empty)
        """
        monkeypatch.delenv("PYTEST", raising=False)
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.setattr(app, "testing", False, raising=False)

        client = TestClient(app, raise_server_exceptions=False)

        target_pool = [
            ("nep94121@gmail.com", True),           # Existing, Owner (not in family_email_allowlist)
            ("thanhvien_test_c2@gmail.com", True),  # Existing, allowlisted C2
            ("khach_test_c3@gmail.com", True),      # Existing, allowlisted C3
            ("senat6031@gmail.com", True),          # Existing, non-allowlisted
            ("con_yeu_family@gmail.com", True),     # Existing, allowlisted
            ("random_stranger_404@evil.com", False),# Non-existent
            ("attacker_injection'--@bad.io", False),# Malformed / attack payload
            ("   nep94121@gmail.com   ", True),     # Whitespace around valid email
            ("NEP94121@GMAIL.COM", True),           # Uppercase valid email
            ("nobody_here_999@domain.vn", False),   # Non-existent
        ]

        # Build 50 requests repeating the 10 targets 5 times
        request_list = target_pool * 5
        assert len(request_list) == 50

        def fire_request(req_item: tuple[str, bool], req_id: int):
            target_email, should_exist = req_item
            resp = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": target_email, "send_gmail": False, "source": f"StressPool-{req_id}"},
            )
            return req_item, resp.status_code, resp.json(), resp.text

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            futures = [executor.submit(fire_request, item, i) for i, item in enumerate(request_list)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 50

        for (target_email, should_exist), status_code, body, raw_text in results:
            # 1. Strict leakage check on every response
            leaks = _recursively_find_leak(body)
            assert not leaks, f"Leakage detected for {target_email}: {leaks}"
            assert "otp_code_for_test" not in raw_text, f"otp_code_for_test found in raw text for {target_email}"
            assert "demo_otp_preview" not in raw_text, f"demo_otp_preview found in raw text for {target_email}"

            # 2. Status code logic check
            if should_exist:
                assert status_code == 200, f"Expected 200 for valid {target_email}, got {status_code}"
                assert body.get("ok") is True
            else:
                assert status_code == 404, f"Expected 404 for non-existent {target_email}, got {status_code}"
                assert body.get("ok") is False

    def test_m1_concurrency_vercel_environment_unconditional_zero_leak(
        self, monkeypatch: pytest.MonkeyPatch, clean_pending_otps
    ) -> None:
        """30 concurrent requests under VERCEL='1' and PYTEST='1' (veto stress test).
        
        Even when PYTEST='1' is set, VERCEL='1' must unconditionally veto any test fields.
        """
        monkeypatch.setenv("VERCEL", "1")
        monkeypatch.setenv("PYTEST", "1")
        monkeypatch.setattr(app, "testing", True, raising=False)

        client = TestClient(app, raise_server_exceptions=False)
        emails = [
            "nep94121@gmail.com",
            "thanhvien_test_c2@gmail.com",
            "khach_test_c3@gmail.com",
        ]
        num_requests = 30

        def send_vercel_call(idx: int):
            e = emails[idx % len(emails)]
            resp = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": e, "send_gmail": False, "source": f"VercelWorker-{idx}"},
            )
            return resp.status_code, resp.json(), resp.text

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(send_vercel_call, i) for i in range(num_requests)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == num_requests
        for status_code, body, raw_text in results:
            assert status_code == 200
            assert "otp_code_for_test" not in body, f"Vercel leaked otp_code_for_test: {body}"
            assert "demo_otp_preview" not in body, f"Vercel leaked demo_otp_preview: {body}"
            assert "otp_code_for_test" not in raw_text
            assert "demo_otp_preview" not in raw_text

    def test_m1_deep_payload_scan_otp_code_not_in_any_field(
        self, monkeypatch: pytest.MonkeyPatch, clean_pending_otps
    ) -> None:
        """Deep scan: ensure the actual generated 6-digit OTP never leaks in other fields.
        
        Even if `otp_code_for_test` key is stripped, the actual code must not appear
        in message, display_name, logs, or metadata returned to the HTTP client in production.
        """
        monkeypatch.delenv("PYTEST", raising=False)
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.setattr(app, "testing", False, raising=False)

        mgr = get_auth_3layer_manager()
        client = TestClient(app, raise_server_exceptions=False)
        email = "nep94121@gmail.com"

        resp = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": email, "send_gmail": False},
        )
        assert resp.status_code == 200
        body = resp.json()
        raw_text = resp.text

        # Retrieve the generated OTP directly from server memory
        with mgr._otp_lock:
            stored_otp = mgr.pending_otps[email]["otp_code"]
        assert len(stored_otp) == 6
        assert stored_otp.isdigit()

        # Check that the 6-digit OTP code does not appear anywhere in the HTTP response body
        assert stored_otp not in raw_text, (
            f"SECURITY BREACH: The active OTP {stored_otp} was found in the response body: {raw_text}"
        )

        # Re-verify on second request (idempotent cooldown response)
        resp2 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": email, "send_gmail": False},
        )
        assert resp2.status_code == 200
        assert stored_otp not in resp2.text, (
            f"SECURITY BREACH: The active OTP {stored_otp} was found in cooldown response body: {resp2.text}"
        )

    def test_m1_boundary_empty_and_invalid_email_handling(
        self, monkeypatch: pytest.MonkeyPatch, clean_pending_otps
    ) -> None:
        """Boundary handling for malformed, missing, and non-email inputs."""
        monkeypatch.delenv("PYTEST", raising=False)
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.setattr(app, "testing", False, raising=False)

        client = TestClient(app, raise_server_exceptions=False)

        cases = [
            {"email": ""},
            {"email": "   "},
            {"email": None},
            {},
            {"email": "not_an_email_at_all"},
            {"email": "@nodomain"},
            {"email": "test@" * 50},
        ]

        for payload in cases:
            resp = client.post("/api/auth3/forgot_password_send_otp", json=payload)
            data = resp.json()

            # When email key is completely omitted, backend defaults to nep94121@gmail.com (200 OK)
            # When email is invalid/empty/whitespace/None, backend cannot find account (404 Not Found)
            if payload == {}:
                assert resp.status_code == 200, f"Expected 200 for omitted email default, got {resp.status_code}: {data}"
                assert data.get("ok") is True
            else:
                assert resp.status_code in (400, 404), f"Unexpected status {resp.status_code} for {payload}"
                assert data.get("ok") is False

            # Absolute zero OTP leakage in ALL responses regardless of status
            assert "otp_code_for_test" not in data, f"Leaked in {payload}: {data}"
            assert "demo_otp_preview" not in data, f"Leaked in {payload}: {data}"
            assert "otp_code_for_test" not in resp.text, f"Leaked in raw text: {resp.text}"
            assert "demo_otp_preview" not in resp.text, f"Leaked in raw text: {resp.text}"

    def test_m1_concurrency_interleaved_gmail_flags_burst(
        self, monkeypatch: pytest.MonkeyPatch, clean_pending_otps
    ) -> None:
        """40 concurrent requests alternating send_gmail=True and send_gmail=False in production.
        
        Evaluates potential state bleed when send_gmail flag varies across simultaneous requests.
        """
        monkeypatch.delenv("PYTEST", raising=False)
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.setattr(app, "testing", False, raising=False)

        client = TestClient(app, raise_server_exceptions=False)
        email = "nep94121@gmail.com"
        num_requests = 40

        def send_interleaved(idx: int):
            send_gmail_flag = (idx % 2 == 0)
            resp = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": email, "send_gmail": send_gmail_flag, "source": f"Interleaved-{idx}"},
            )
            return resp.status_code, resp.json(), resp.text

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(send_interleaved, i) for i in range(num_requests)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == num_requests
        for status_code, body, raw_text in results:
            assert status_code == 200
            assert "otp_code_for_test" not in body
            assert "demo_otp_preview" not in body
            assert "otp_code_for_test" not in raw_text
            assert "demo_otp_preview" not in raw_text

    def test_m1_concurrency_tampered_headers_adversarial(
        self, monkeypatch: pytest.MonkeyPatch, clean_pending_otps
    ) -> None:
        """Adversarial requests attempting to spoof test mode via HTTP headers & query params.
        
        Asserts that client-controlled headers cannot flip the server into test mode.
        """
        monkeypatch.delenv("PYTEST", raising=False)
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.setattr(app, "testing", False, raising=False)

        client = TestClient(app, raise_server_exceptions=False)
        adversarial_headers = [
            {"X-Pytest": "1"},
            {"X-Testing": "true"},
            {"X-Vercel-Skip": "1"},
            {"User-Agent": "pytest/9.1.1"},
            {"Cookie": "test_mode=1; env=pytest"},
            {"X-Forwarded-Host": "localhost:8000"},
        ]

        def send_spoof(idx: int):
            hdr = adversarial_headers[idx % len(adversarial_headers)]
            resp = client.post(
                "/api/auth3/forgot_password_send_otp?pytest=1&testing=true",
                json={"email": "nep94121@gmail.com", "send_gmail": False},
                headers=hdr,
            )
            return resp.status_code, resp.json(), resp.text

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(send_spoof, i) for i in range(len(adversarial_headers) * 4)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        for status_code, body, raw_text in results:
            assert status_code == 200
            assert "otp_code_for_test" not in body, f"Spoofed header succeeded in leaking test field: {body}"
            assert "demo_otp_preview" not in body, f"Spoofed header succeeded in leaking demo preview: {body}"
            assert "otp_code_for_test" not in raw_text
            assert "demo_otp_preview" not in raw_text
