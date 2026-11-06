"""Root pytest conftest: Test Isolation & Network Mocking for Smart Home Voice AI.

Provides autouse fixture mock_email_and_gws_network_isolation that intercepts
smtplib.SMTP, smtplib.SMTP_SSL, and subprocess.run(["gws", ...]) so no real
network sockets or CLI commands are executed during test runs.
"""
from __future__ import annotations

import atexit
import contextlib
import copy
import gc
import json
import os
import pathlib
import smtplib
import sqlite3
import subprocess
import sys
import tempfile
import threading
from typing import Any
from unittest.mock import MagicMock

import pytest

# Ensure workspace root is always in sys.path
ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "simulator" / "data"
_TRACKED_DATA_FILES = (
    "accounts_3layer.json",
    "auth_3layer_events.json",
    "custom_rules_overlay.json",
    "family_email_allowlist.json",
    "invite_links_3layer.json",
    "ir_devices_db.json",
    "knowledge_base.json",
    "smarthome.db",
    "system_audit_logs.jsonl",
    "voiceprints.json",
)
_INITIAL_DATA_BYTES: dict[str, bytes] = {
    fname: (DATA_DIR / fname).read_bytes()
    for fname in _TRACKED_DATA_FILES
    if (DATA_DIR / fname).exists()
}
_INITIAL_MGR_ACCOUNTS: list[dict[str, Any]] | None = None
_INITIAL_MGR_ALLOWLIST: dict[str, Any] | None = None


def _restore_sqlite_db_safely(raw_db_bytes: bytes, force_exact_bytes: bool = False) -> None:
    """Restore smarthome.db without ever overwriting the main DB file underneath an active WAL."""
    import simulator.database_sqlite as db_mod
    from simulator.auth.session_store import get_session_store

    db_path = DATA_DIR / "smarthome.db"
    wal_path = DATA_DIR / "smarthome.db-wal"
    shm_path = DATA_DIR / "smarthome.db-shm"
    store = get_session_store()

    with db_mod._DB_LOCK, store._lock:
        need_restore = (
            force_exact_bytes
            or not db_path.exists()
            or wal_path.exists()
            or shm_path.exists()
            or db_path.read_bytes() != raw_db_bytes
        )
        if not need_restore:
            return

        db_mod._SCHEMA_INITIALIZED = False
        db_mod._LAST_KB_MTIME = -1.0
        db_mod._LAST_VP_MTIME = -1.0
        db_mod._LAST_IR_MTIME = -1.0

        # 1. Try unlinking WAL/SHM first so we never overwrite smarthome.db while WAL exists
        for aux_path in (wal_path, shm_path):
            if aux_path.exists():
                try:
                    aux_path.unlink()
                except Exception:
                    pass

        if wal_path.exists() or shm_path.exists():
            gc.collect()
            for aux_path in (wal_path, shm_path):
                if aux_path.exists():
                    try:
                        aux_path.unlink()
                    except Exception:
                        pass

        # 2. If WAL and SHM are completely gone, a direct byte write is 100% safe and exact
        if not wal_path.exists() and not shm_path.exists():
            try:
                if not db_path.exists() or db_path.read_bytes() != raw_db_bytes:
                    db_path.write_bytes(raw_db_bytes)
                return
            except Exception:
                pass

        # 3. Fallback when a background server thread holds WAL/SHM open:
        #    use SQLite's online backup API so WAL and DB pages remain 100% consistent.
        tmp_clean_db = pathlib.Path(tempfile.gettempdir()) / f"smarthome_clean_template_{os.getpid()}.db"
        try:
            if not tmp_clean_db.exists() or tmp_clean_db.read_bytes() != raw_db_bytes:
                tmp_clean_db.write_bytes(raw_db_bytes)
            with (
                contextlib.closing(sqlite3.connect(str(tmp_clean_db), timeout=5.0)) as src_conn,
                contextlib.closing(sqlite3.connect(str(db_path), timeout=5.0)) as dst_conn,
            ):
                src_conn.backup(dst_conn)
                dst_conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                dst_conn.commit()
        except Exception:
            pass

        if force_exact_bytes:
            gc.collect()
            for aux_path in (wal_path, shm_path):
                if aux_path.exists():
                    try:
                        aux_path.unlink()
                    except Exception:
                        pass
            if not wal_path.exists() and not shm_path.exists():
                try:
                    db_path.write_bytes(raw_db_bytes)
                except Exception:
                    pass


def _restore_tracked_data_files(force_exact_bytes: bool = False) -> None:
    for fname, raw_bytes in _INITIAL_DATA_BYTES.items():
        if fname == "smarthome.db":
            continue
        fpath = DATA_DIR / fname
        try:
            if not fpath.exists() or fpath.read_bytes() != raw_bytes:
                fpath.write_bytes(raw_bytes)
        except Exception:
            pass
    if "smarthome.db" in _INITIAL_DATA_BYTES:
        _restore_sqlite_db_safely(_INITIAL_DATA_BYTES["smarthome.db"], force_exact_bytes=force_exact_bytes)


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
    """Ensure pending_otps and tracked data files do not leak state across tests."""
    global _INITIAL_MGR_ACCOUNTS, _INITIAL_MGR_ALLOWLIST
    from simulator.api.deps import _REST_ENGINE
    from simulator.api.routes_auth import get_auth_3layer_manager

    mgr = get_auth_3layer_manager()
    if _INITIAL_MGR_ACCOUNTS is None:
        _INITIAL_MGR_ACCOUNTS = copy.deepcopy(mgr.accounts)
    if _INITIAL_MGR_ALLOWLIST is None and hasattr(mgr, "family_email_allowlist"):
        _INITIAL_MGR_ALLOWLIST = copy.deepcopy(mgr.family_email_allowlist)
    lock = getattr(mgr, "_otp_lock", threading.Lock())
    with lock:
        dict.clear(mgr.pending_otps)
        if hasattr(mgr, "otp_failed_attempts"):
            mgr.otp_failed_attempts.clear()
        if hasattr(mgr, "pending_invite_registrations"):
            mgr.pending_invite_registrations.clear()
        mgr.accounts = copy.deepcopy(_INITIAL_MGR_ACCOUNTS)
        if _INITIAL_MGR_ALLOWLIST is not None and hasattr(mgr, "family_email_allowlist"):
            mgr.family_email_allowlist = copy.deepcopy(_INITIAL_MGR_ALLOWLIST)
    _REST_ENGINE._explicit_test_user_set = False
    _REST_ENGINE._current_role = "ADMIN"
    _REST_ENGINE._current_user_id = "tuan_anh"
    _restore_tracked_data_files()
    yield
    with lock:
        dict.clear(mgr.pending_otps)
        if hasattr(mgr, "otp_failed_attempts"):
            mgr.otp_failed_attempts.clear()
        if hasattr(mgr, "pending_invite_registrations"):
            mgr.pending_invite_registrations.clear()
        mgr.accounts = copy.deepcopy(_INITIAL_MGR_ACCOUNTS)
        if _INITIAL_MGR_ALLOWLIST is not None and hasattr(mgr, "family_email_allowlist"):
            mgr.family_email_allowlist = copy.deepcopy(_INITIAL_MGR_ALLOWLIST)
    _REST_ENGINE._explicit_test_user_set = False
    _REST_ENGINE._current_role = "ADMIN"
    _REST_ENGINE._current_user_id = "tuan_anh"
    _restore_tracked_data_files()


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Restore tracked data files at the end of the entire pytest session."""
    _restore_tracked_data_files(force_exact_bytes=True)


atexit.register(_restore_tracked_data_files, True)


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
