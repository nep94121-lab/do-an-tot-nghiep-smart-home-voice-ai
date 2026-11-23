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


import http.client as _http_client
import threading as _threading

_ORIG_URLOPEN = urllib.request.urlopen


def cloud_required() -> bool:
    backend = os.environ.get("SMARTHOME_SECURITY_BACKEND", "").strip().lower()
    if backend == "sqlite":
        return False
    return bool(os.environ.get("VERCEL")) or backend == "github"


def _sqlite_security_enabled() -> bool:
    import sys as _sys

    backend = os.environ.get("SMARTHOME_SECURITY_BACKEND", "").strip().lower()
    if backend == "sqlite":
        return True
    if cloud_required() or os.environ.get("SIMULATOR_SECURITY_STATE_DIR", "").strip():
        return False
    if backend == "file":
        return False
    return not ("pytest" in _sys.modules or os.environ.get("PYTEST_CURRENT_TEST"))


class GitHubSecurityState:
    def __init__(self, repository: str, token: str, api_base: str | None = None):
        if len(repository.split("/")) != 2 or not token:
            raise SecurityStateUnavailable("Security store is not configured")
        self.repository = repository
        self._token = token
        base = api_base if api_base is not None else os.environ.get("SMARTHOME_SECURITY_API_BASE", "")
        self.api_base = (base.strip() or "https://api.github.com").rstrip("/")
        self._private_checked = False
        self._local = _threading.local()

    class _DocumentNotFound(Exception):
        pass

    def _get_connection(self, scheme: str, host: str, port: int | None) -> _http_client.HTTPConnection:
        key = (scheme, host, port)
        conn = getattr(self._local, "conn", None)
        conn_key = getattr(self._local, "conn_key", None)
        if conn is not None and conn_key == key:
            return conn
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        if scheme == "https":
            conn = _http_client.HTTPSConnection(host, port=port, timeout=8)
        else:
            conn = _http_client.HTTPConnection(host, port=port, timeout=8)
        self._local.conn = conn
        self._local.conn_key = key
        return conn

    def _close_connection(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        self._local.conn = None
        self._local.conn_key = None

    def _request_keepalive(self, method: str, url: str, headers: dict[str, str], payload_bytes: bytes | None) -> dict:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname or ""
        if not host:
            raise SecurityStateUnavailable("Invalid security endpoint URL")
        port = parsed.port
        req_path = parsed.path or "/"
        if parsed.query:
            req_path = f"{req_path}?{parsed.query}"

        last_exc: Exception | None = None
        for attempt in range(2):
            conn = self._get_connection(parsed.scheme, host, port)
            try:
                conn.request(method, req_path, body=payload_bytes, headers=headers)
                resp = conn.getresponse()
                raw = resp.read()
                conn_hdr = (resp.getheader("Connection") or "").lower()
                if "close" in conn_hdr or resp.status >= 500:
                    self._close_connection()
                if resp.status == 404 and method == "GET" and "/contents/" in req_path:
                    raise self._DocumentNotFound()
                if resp.status in (409, 422) and method == "PUT":
                    raise StateConflict()
                if resp.status >= 400:
                    raise SecurityStateUnavailable("Security storage request failed")
                return json.loads(raw.decode("utf-8"))
            except (self._DocumentNotFound, StateConflict, SecurityStateUnavailable):
                raise
            except (_http_client.HTTPException, OSError) as exc:
                last_exc = exc
                self._close_connection()
                if attempt == 0:
                    continue
                raise SecurityStateUnavailable("Security storage request failed") from None
            except Exception:
                self._close_connection()
                raise SecurityStateUnavailable("Security storage request failed") from None
        raise SecurityStateUnavailable("Security storage request failed") from last_exc

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.api_base}/repos/{self.repository}{path}"
        if method == "GET":
            url += ("&" if "?" in url else "?") + "_fresh=" + secrets.token_hex(8)
        payload_bytes = json.dumps(body).encode() if body is not None else None
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Cache-Control": "no-cache, no-store",
            "Content-Type": "application/json",
            "User-Agent": "smart-home-security-state",
        }
        if urllib.request.urlopen is _ORIG_URLOPEN:
            return self._request_keepalive(method, url, headers, payload_bytes)
        request = urllib.request.Request(
            url,
            method=method,
            data=payload_bytes,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404 and method == "GET" and path.startswith("/contents/"):
                raise self._DocumentNotFound() from None
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
        try:
            row = self._request("GET", "/contents/" + urllib.parse.quote(filename, safe=""))
        except self._DocumentNotFound:
            return b"{}", "", 0
        try:
            document = json.loads(base64.b64decode(row["content"]))
            return base64.b64decode(document["payload"]), str(row["sha"]), int(document["revision"])
        except Exception:
            raise SecurityStateUnavailable("Invalid security document") from None

    def compare_and_swap(self, filename: str, payload: bytes, expected_sha: str, revision: int) -> None:
        document = {"revision": revision + 1, "payload": base64.b64encode(payload).decode("ascii")}
        body = {
            "message": "Update security document",
            "content": base64.b64encode(json.dumps(document, separators=(",", ":")).encode()).decode("ascii"),
        }
        if expected_sha:
            body["sha"] = expected_sha
        self._request("PUT", "/contents/" + urllib.parse.quote(filename, safe=""), body)


@functools.lru_cache(maxsize=4)
def _configured_backend(repository: str, token: str, api_base: str = "") -> GitHubSecurityState:
    return GitHubSecurityState(repository, token, api_base=api_base or None)


def get_security_backend() -> GitHubSecurityState:
    return _configured_backend(
        os.environ.get("SMARTHOME_SECURITY_REPO", ""),
        os.environ.get("SMARTHOME_SECURITY_TOKEN", ""),
        os.environ.get("SMARTHOME_SECURITY_API_BASE", ""),
    )


@dataclass
class _Transaction:
    filename: str
    payload: bytes
    staged: bytes | None = None


@dataclass
class _SqliteTransaction:
    filename: str
    data_dir: Path | None = None
    payload: bytes | None = None
    revision: int | None = None
    loaded: bool = False
    staged: bytes | None = None
    working_payload: bytes | None = None
    staged_data_dir: Path | None = None


_TRANSACTION: contextvars.ContextVar[_Transaction | None] = contextvars.ContextVar("security_transaction", default=None)
_SQLITE_TRANSACTION: contextvars.ContextVar[_SqliteTransaction | None] = contextvars.ContextVar(
    "security_sqlite_transaction", default=None
)
_ACTIVE_TX_LOCKS: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar(
    "security_tx_file_locks", default=frozenset()
)


def atomic_security(filename: str):
    """Retry the complete transition, never a value computed from a stale snapshot."""
    def decorate(operation: Callable):
        @functools.wraps(operation)
        def run(*args, **kwargs):
            if not cloud_required():
                if _sqlite_security_enabled():
                    key = Path(filename).name
                    active_sq_tx = _SQLITE_TRANSACTION.get()
                    if active_sq_tx is not None and active_sq_tx.filename == key:
                        return operation(*args, **kwargs)
                    from backend.async_cloud_backup import schedule_github_backup
                    from backend.auth import sqlite_security_repo as _sq

                    deadline = time.monotonic() + 30
                    for attempt in range(12):
                        sq_tx = _SqliteTransaction(filename=key)
                        context_token = _SQLITE_TRANSACTION.set(sq_tx)
                        try:
                            result = operation(*args, **kwargs)
                        finally:
                            _SQLITE_TRANSACTION.reset(context_token)
                        if sq_tx.staged is None:
                            return result
                        eff_dir = sq_tx.staged_data_dir or sq_tx.data_dir
                        try:
                            _sq.cas_save_security_state_sqlite(
                                key,
                                sq_tx.staged,
                                expected_revision=sq_tx.revision if sq_tx.loaded else None,
                                data_dir=eff_dir,
                            )
                            backup_doc = json.loads(sq_tx.staged.decode("utf-8"))
                            if key == "auth3_accounts_state.json" and isinstance(backup_doc, dict) and backup_doc.get("partial"):
                                full_raw = _sq.load_accounts_sqlite(eff_dir) or sq_tx.working_payload
                                if full_raw:
                                    backup_doc = json.loads(full_raw.decode("utf-8"))
                            schedule_github_backup(key, backup_doc)
                            return result
                        except StateConflict:
                            if time.monotonic() >= deadline:
                                break
                            time.sleep(secrets.randbelow(20) / 1000 + 0.01 * attempt)
                        except SecurityStateUnavailable:
                            raise
                        except Exception as exc:
                            raise SecurityStateUnavailable("Security state could not be saved") from exc
                    raise SecurityStateUnavailable("Security state changed too often; retry later")
                key = Path(filename).name
                held = _ACTIVE_TX_LOCKS.get()
                if key in held:
                    return operation(*args, **kwargs)
                from backend.auth.session_store import get_session_store
                from backend.engine.state_store import _interprocess_file_lock

                local_cas_dir = os.environ.get("SIMULATOR_SECURITY_STATE_DIR", "").strip()
                base_dir = Path(local_cas_dir) if local_cas_dir else get_session_store().db_path.parent
                lock_path = base_dir / f".tx_{key}.lock"
                tok = _ACTIVE_TX_LOCKS.set(held | {key})
                try:
                    with _interprocess_file_lock(lock_path):
                        return operation(*args, **kwargs)
                finally:
                    _ACTIVE_TX_LOCKS.reset(tok)
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
    sq_tx = _SQLITE_TRANSACTION.get()
    fname = Path(filename).name
    if sq_tx is not None and sq_tx.filename == fname:
        if sq_tx.working_payload is not None:
            return sq_tx.working_payload
        if sq_tx.staged is not None:
            return sq_tx.staged
        if not sq_tx.loaded:
            from backend.auth import sqlite_security_repo as _sq

            payload, rev = _sq.read_security_state_with_revision_sqlite(fname, data_dir)
            sq_tx.payload = payload
            sq_tx.revision = rev
            sq_tx.data_dir = data_dir
            sq_tx.loaded = True
        return sq_tx.payload
    if cloud_required():
        return get_security_backend().read(filename)[0]
    local_cas_dir = os.environ.get("SIMULATOR_SECURITY_STATE_DIR", "").strip()
    if local_cas_dir:
        from backend.engine.state_store import _interprocess_file_lock

        target = Path(local_cas_dir) / Path(filename).name
        lock_path = target.with_suffix(target.suffix + ".lock")
        with _interprocess_file_lock(lock_path):
            return target.read_bytes() if target.exists() else None
    if _sqlite_security_enabled():
        from backend.auth import sqlite_security_repo as _sq

        fname = Path(filename).name
        if fname == "owner_pin.json":
            return _sq.load_owner_pin_sqlite(data_dir)
        if fname == "guest_invites.json":
            return _sq.load_invites_sqlite(data_dir)
        if fname == "auth3_accounts_state.json":
            return _sq.load_accounts_sqlite(data_dir)
        if fname == "login_rate_limit.json":
            return _sq.load_rate_limits_sqlite(data_dir)
    from backend.durable_store import load_state_file
    return load_state_file(filename, data_dir=data_dir)


def save_security_state(filename: str, payload: bytes, data_dir: Path) -> None:
    transaction = _TRANSACTION.get()
    if transaction is not None and transaction.filename == filename:
        transaction.staged = payload
        return
    sq_tx = _SQLITE_TRANSACTION.get()
    fname = Path(filename).name
    if sq_tx is not None and sq_tx.filename == fname:
        if fname == "auth3_accounts_state.json" and sq_tx.staged is not None:
            previous = json.loads(sq_tx.staged)
            incoming = json.loads(payload)
            if previous.get("partial") and incoming.get("partial"):
                def account_id(account):
                    return str(account.get("account_id") or account.get("user_id") or account.get("id") or "")

                accounts = {account_id(account): account for account in previous["accounts"]}
                accounts.update({account_id(account): account for account in incoming["accounts"]})
                deleted = set(previous.get("deleted_account_ids", []))
                deleted.difference_update(account_id(account) for account in incoming["accounts"])
                deleted.update(incoming.get("deleted_account_ids", []))
                incoming["accounts"] = [account for uid, account in accounts.items() if uid not in deleted]
                incoming["deleted_account_ids"] = sorted(deleted)
                incoming["cleared_otp_emails"] = sorted(
                    set(previous.get("cleared_otp_emails", [])) | set(incoming.get("cleared_otp_emails", []))
                )
                incoming["clear_all_otps"] = bool(previous.get("clear_all_otps") or incoming.get("clear_all_otps"))
                payload = json.dumps(incoming, ensure_ascii=False).encode("utf-8")
        sq_tx.staged = payload
        sq_tx.staged_data_dir = data_dir
        if fname != "auth3_accounts_state.json":
            sq_tx.working_payload = payload
        return
    if cloud_required():
        raise SecurityStateUnavailable("Security writes require an atomic transition")
    local_cas_dir = os.environ.get("SIMULATOR_SECURITY_STATE_DIR", "").strip()
    if local_cas_dir:
        from backend.engine.state_store import _interprocess_file_lock

        target = Path(local_cas_dir) / Path(filename).name
        lock_path = target.with_suffix(target.suffix + ".lock")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_name(f"{target.name}.tmp.{os.getpid()}_{secrets.token_hex(6)}")
        try:
            with _interprocess_file_lock(lock_path):
                tmp_path.write_bytes(payload)
                os.replace(tmp_path, target)
            return
        except Exception as exc:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass
            raise SecurityStateUnavailable("Security state could not be saved") from exc
    if _sqlite_security_enabled():
        from backend.async_cloud_backup import schedule_github_backup
        from backend.auth import sqlite_security_repo as _sq

        fname = Path(filename).name
        try:
            if fname == "owner_pin.json":
                _sq.save_owner_pin_sqlite(payload, data_dir)
                schedule_github_backup(fname, json.loads(payload.decode("utf-8")))
                return
            if fname == "guest_invites.json":
                _sq.save_invites_sqlite(payload, data_dir)
                schedule_github_backup(fname, json.loads(payload.decode("utf-8")))
                return
            if fname == "auth3_accounts_state.json":
                _sq.save_accounts_sqlite(payload, data_dir)
                doc = json.loads(payload.decode("utf-8"))
                if isinstance(doc, dict) and doc.get("partial"):
                    full_raw = _sq.load_accounts_sqlite(data_dir)
                    if full_raw:
                        doc = json.loads(full_raw.decode("utf-8"))
                schedule_github_backup(fname, doc)
                return
            if fname == "login_rate_limit.json":
                _sq.save_rate_limits_sqlite(payload, data_dir)
                schedule_github_backup(fname, json.loads(payload.decode("utf-8")))
                return
        except Exception as exc:
            raise SecurityStateUnavailable("Security state could not be saved") from exc
    from backend.durable_store import save_state_file
    if not save_state_file(filename, payload, sync_cloud=False, data_dir=data_dir):
        raise SecurityStateUnavailable("Security state could not be saved")
