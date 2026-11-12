"""Authoritative security documents with optimistic concurrency across server instances."""
from __future__ import annotations

import base64
import contextvars
import functools
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class SecurityStateUnavailable(RuntimeError):
    pass


class StateConflict(Exception):
    pass


def cloud_required() -> bool:
    return bool(os.environ.get("VERCEL")) or os.environ.get("SMARTHOME_SECURITY_BACKEND") == "github"


class GitHubSecurityState:
    def __init__(self, repository: str, token: str):
        if len(repository.split("/")) != 2 or not token:
            raise SecurityStateUnavailable("Security store is not configured")
        self.repository = repository
        self._token = token
        self._private_checked = False

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"https://api.github.com/repos/{self.repository}{path}"
        if method == "GET":
            url += ("&" if "?" in url else "?") + "_fresh=" + secrets.token_hex(8)
        request = urllib.request.Request(
            url, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self._token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "Cache-Control": "no-cache, no-store",
                     "Content-Type": "application/json", "User-Agent": "smart-home-security-state"},
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code in (409, 422) and method == "PUT":
                raise StateConflict() from None
            raise SecurityStateUnavailable("Security storage request failed") from None
        except Exception:
            raise SecurityStateUnavailable("Security storage request failed") from None

    def _check_private(self) -> None:
        if not self._private_checked:
            if self._request("GET", "").get("private") is not True:
                raise SecurityStateUnavailable("Security repository must be private")
            self._private_checked = True

    def read(self, filename: str) -> tuple[bytes, str, int]:
        self._check_private()
        row = self._request("GET", "/contents/" + urllib.parse.quote(filename, safe=""))
        try:
            document = json.loads(base64.b64decode(row["content"]))
            return base64.b64decode(document["payload"]), str(row["sha"]), int(document["revision"])
        except Exception:
            raise SecurityStateUnavailable("Invalid security document") from None

    def compare_and_swap(self, filename: str, payload: bytes, expected_sha: str, revision: int) -> None:
        document = {"revision": revision + 1, "payload": base64.b64encode(payload).decode("ascii")}
        self._request("PUT", "/contents/" + urllib.parse.quote(filename, safe=""), {
            "message": "Update security document", "sha": expected_sha,
            "content": base64.b64encode(json.dumps(document, separators=(",", ":")).encode()).decode("ascii"),
        })


@functools.lru_cache(maxsize=1)
def _configured_backend(repository: str, token: str) -> GitHubSecurityState:
    return GitHubSecurityState(repository, token)


def get_security_backend() -> GitHubSecurityState:
    return _configured_backend(os.environ.get("SMARTHOME_SECURITY_REPO", ""), os.environ.get("SMARTHOME_SECURITY_TOKEN", ""))


@dataclass
class _Transaction:
    filename: str
    payload: bytes
    staged: bytes | None = None


_TRANSACTION: contextvars.ContextVar[_Transaction | None] = contextvars.ContextVar("security_transaction", default=None)


def atomic_security(filename: str):
    """Retry the complete transition, never a value computed from a stale snapshot."""
    def decorate(operation: Callable):
        @functools.wraps(operation)
        def run(*args, **kwargs):
            if not cloud_required():
                return operation(*args, **kwargs)
            backend = get_security_backend()
            deadline = time.monotonic() + 30
            for attempt in range(12):
                payload, sha, revision = backend.read(filename)
                transaction = _Transaction(filename, payload)
                context_token = _TRANSACTION.set(transaction)
                try:
                    result = operation(*args, **kwargs)
                finally:
                    _TRANSACTION.reset(context_token)
                if transaction.staged is None:
                    return result
                try:
                    backend.compare_and_swap(filename, transaction.staged, sha, revision)
                    return result
                except StateConflict:
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(secrets.randbelow(20) / 1000 + 0.01 * attempt)
            raise SecurityStateUnavailable("Security state changed too often; retry later")
        return run
    return decorate


def load_security_state(filename: str, data_dir: Path) -> bytes | None:
    transaction = _TRANSACTION.get()
    if transaction is not None and transaction.filename == filename:
        return transaction.staged if transaction.staged is not None else transaction.payload
    if cloud_required():
        return get_security_backend().read(filename)[0]
    from simulator.durable_store import load_state_file
    return load_state_file(filename, data_dir=data_dir)


def save_security_state(filename: str, payload: bytes, data_dir: Path) -> None:
    transaction = _TRANSACTION.get()
    if transaction is not None and transaction.filename == filename:
        transaction.staged = payload
        return
    if cloud_required():
        raise SecurityStateUnavailable("Security writes require an atomic transition")
    from simulator.durable_store import save_state_file
    if not save_state_file(filename, payload, sync_cloud=False, data_dir=data_dir):
        raise SecurityStateUnavailable("Security state could not be saved")
