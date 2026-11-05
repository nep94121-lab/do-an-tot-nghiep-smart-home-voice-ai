"""Root pytest conftest: Test Isolation & Network Mocking for Smart Home Voice AI.

Provides autouse fixture mock_email_and_gws_network_isolation that intercepts
smtplib.SMTP, smtplib.SMTP_SSL, and subprocess.run(["gws", ...]) so no real
network sockets or CLI commands are executed during test runs.
"""
from __future__ import annotations

import json
import os
import pathlib
import smtplib
import subprocess
import sys
import threading
from typing import Any
from unittest.mock import MagicMock

import pytest

# Ensure workspace root is always in sys.path
ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def enable_test_otp_mode_in_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure legacy test suites receive test OTP fields during local pytest runs."""
    monkeypatch.setenv("PYTEST", "1")
    try:
        from simulator.server import app

        monkeypatch.setattr(app, "testing", True, raising=False)
    except Exception:
        pass
    if "VERCEL" in os.environ:
        monkeypatch.delenv("VERCEL", raising=False)


@pytest.fixture(autouse=True)
def clean_auth_pending_otps() -> None:
    """Ensure pending_otps does not leak state across tests."""
    from simulator.api.routes_auth import get_auth_3layer_manager

    mgr = get_auth_3layer_manager()
    lock = getattr(mgr, "_otp_lock", threading.Lock())
    with lock:
        mgr.pending_otps.clear()
    yield
    with lock:
        mgr.pending_otps.clear()


@pytest.fixture(autouse=True)
def mock_email_and_gws_network_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Autouse fixture providing complete email and gws network isolation across all tests.
    
    1. Intercepts smtplib.SMTP and smtplib.SMTP_SSL to prevent opening real network sockets.
    2. Intercepts subprocess.run for "gws" CLI invocations.
    3. Retains compatibility with individual tests that use unittest.mock.patch.
    """
    # 1. Mock SMTP and SMTP_SSL instances
    mock_smtp_inst = MagicMock()
    mock_smtp_inst.__enter__.return_value = mock_smtp_inst
    mock_smtp_inst.send_message.return_value = {}
    mock_smtp_inst.sendmail.return_value = {}
    mock_smtp_inst.login.return_value = (235, b"2.7.0 Authentication successful")
    mock_smtp_inst.starttls.return_value = (220, b"2.0.0 Ready to start TLS")

    monkeypatch.setattr(smtplib, "SMTP", MagicMock(return_value=mock_smtp_inst))
    monkeypatch.setattr(smtplib, "SMTP_SSL", MagicMock(return_value=mock_smtp_inst))

    # 2. Intercept subprocess.run for "gws" commands
    orig_subprocess_run = subprocess.run

    def safe_subprocess_run(cmd: Any, *args: Any, **kwargs: Any) -> Any:
        cmd_str = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "gws" in cmd_str:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            if "messages" in cmd_str and "send" in cmd_str:
                mock_proc.stdout = json.dumps({
                    "id": "mock_gws_isolation_msg_id",
                    "threadId": "mock_gws_isolation_thread_id",
                })
                mock_proc.stderr = ""
            elif "messages" in cmd_str and "list" in cmd_str:
                mock_proc.stdout = json.dumps({
                    "messages": [{"id": "mock_gws_isolation_msg_id"}]
                })
                mock_proc.stderr = ""
            elif "messages" in cmd_str and "get" in cmd_str:
                mock_proc.stdout = json.dumps({
                    "id": "mock_gws_isolation_msg_id",
                    "snippet": "Mã xác nhận OTP: 654321",
                    "payload": {
                        "headers": [{"name": "Subject", "value": "Mã xác nhận OTP: 654321"}]
                    },
                })
                mock_proc.stderr = ""
            else:
                mock_proc.stdout = "{}"
                mock_proc.stderr = ""
            return mock_proc
        return orig_subprocess_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", safe_subprocess_run)
