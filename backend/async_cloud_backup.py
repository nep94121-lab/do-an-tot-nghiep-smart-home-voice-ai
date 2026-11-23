"""Non-blocking background backup queue to private GitHub CAS repository."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_PENDING_DOCS: dict[str, bytes] = {}
_WORKER_STARTED = False
_WAKE_EVENT = threading.Event()


def async_github_backup_enabled() -> bool:
    """Return True only on the live server when background backup is explicitly enabled."""
    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    if os.environ.get("SIMULATOR_OFFLINE_SANDBOX") == "1":
        return False
    if os.environ.get("SMARTHOME_ASYNC_GITHUB_BACKUP", "0").strip() != "1":
        return False
    return bool(
        os.environ.get("SMARTHOME_SECURITY_REPO", "").strip()
        and os.environ.get("SMARTHOME_SECURITY_TOKEN", "").strip()
    )


def schedule_github_backup(filename: str, payload_obj: Any) -> None:
    """Enqueue a non-blocking JSON backup snapshot to GitHub without blocking the request path."""
    if not async_github_backup_enabled():
        return
    try:
        raw = json.dumps(payload_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except Exception:
        return
    with _LOCK:
        _PENDING_DOCS[filename] = raw
        _ensure_worker_locked()
    _WAKE_EVENT.set()


def _ensure_worker_locked() -> None:
    global _WORKER_STARTED
    if _WORKER_STARTED:
        return
    t = threading.Thread(target=_backup_worker_loop, name="smarthome-gh-backup", daemon=True)
    t.start()
    _WORKER_STARTED = True


def _push_doc_to_github(filename: str, payload: bytes) -> None:
    from backend.auth.security_state import StateConflict, get_security_backend

    backend = get_security_backend()
    for _attempt in range(3):
        try:
            _old_payload, sha, rev = backend.read(filename)
            backend.compare_and_swap(filename, payload, sha, rev)
            return
        except StateConflict:
            time.sleep(0.15)
        except Exception as exc:
            logger.debug("Async GitHub backup skipped for %s: %s", filename, exc)
            return


def _backup_worker_loop() -> None:
    while True:
        _WAKE_EVENT.wait(timeout=30.0)
        _WAKE_EVENT.clear()
        # Debounce rapid device toggles so bursts coalesce into one commit
        time.sleep(3.0)
        while True:
            with _LOCK:
                if not _PENDING_DOCS:
                    break
                fname, payload = _PENDING_DOCS.popitem()
            _push_doc_to_github(fname, payload)
