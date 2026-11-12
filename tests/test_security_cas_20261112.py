"""Concurrent clients must preserve PIN failures, OTP single use and invite revocation."""
from __future__ import annotations

import base64
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from simulator.auth import guest_invites, owner_pin, security_state


class RemoteDocuments:
    def __init__(self):
        self.lock = threading.Lock()
        self.documents = {"owner_pin.json": (b"{}", 0), "guest_invites.json": (b'{"invites": []}', 0)}
        self.conflicts = 0
        self.first_reads: threading.Barrier | None = None
        self.read_count = 0

    def read(self, filename):
        with self.lock:
            payload, revision = self.documents[filename]
            self.read_count += 1
            wait = self.first_reads is not None and self.read_count <= self.first_reads.parties
        if wait:
            self.first_reads.wait(timeout=10)
        return payload, str(revision), revision

    def compare_and_swap(self, filename, payload, sha, revision):
        with self.lock:
            if str(self.documents[filename][1]) != sha:
                self.conflicts += 1
                raise security_state.StateConflict()
            self.documents[filename] = (payload, revision + 1)

    def state(self, filename):
        return json.loads(self.documents[filename][0])


@pytest.fixture
def remote(monkeypatch, tmp_path):
    backend = RemoteDocuments()
    monkeypatch.setenv("SMARTHOME_SECURITY_BACKEND", "github")
    monkeypatch.setattr(security_state, "get_security_backend", lambda: backend)
    monkeypatch.setattr(owner_pin, "_data_dir", lambda: tmp_path)
    monkeypatch.setattr(guest_invites, "_data_dir", lambda: tmp_path)
    return backend


def test_two_stale_clients_recompute_pin_failure_after_conflict(remote):
    assert owner_pin.setup_or_replace_pin("2468", "2468")["ok"]
    remote.first_reads = threading.Barrier(2)
    remote.read_count = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(owner_pin.verify_pin, ["0000", "1111"]))
    assert all(not result["ok"] for result in results)
    assert remote.state("owner_pin.json")["failed_attempts"] == 2
    assert remote.conflicts >= 1


def test_five_concurrent_wrong_attempts_lock_for_all_clients(remote):
    owner_pin.setup_or_replace_pin("2468", "2468")
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(owner_pin.verify_pin, ["0000"] * 5))
    assert remote.state("owner_pin.json")["failed_attempts"] == 5
    assert owner_pin.verify_pin("2468")["status_code"] == 423


def test_concurrent_reset_only_consumes_code_once(remote):
    _, code = owner_pin.issue_reset_otp()
    remote.first_reads = threading.Barrier(2)
    remote.read_count = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pin: owner_pin.reset_pin_with_otp(code, pin, pin), ["2468", "1357"]))
    assert sum(bool(result["ok"]) for result in results) == 1


def test_concurrent_otp_issue_keeps_single_cooldown(remote):
    remote.first_reads = threading.Barrier(2)
    remote.read_count = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: owner_pin.issue_reset_otp(), range(2)))
    assert sum(bool(result[0]["ok"]) for result in results) == 1
    assert sum(result[0].get("status_code") == 429 for result in results) == 1


def test_redeem_retry_cannot_overwrite_revocation(remote):
    invite = guest_invites.create_invite(owner_user_id="tuan_anh", tier=3)
    first = True
    original = remote.compare_and_swap
    def revoke_before_redemption_commit(filename, payload, sha, revision):
        nonlocal first
        if first:
            first = False
            data = remote.state(filename)
            data["invites"][0]["revoked"] = True
            original(filename, json.dumps(data).encode(), sha, revision)
        return original(filename, payload, sha, revision)
    remote.compare_and_swap = revoke_before_redemption_commit
    result = guest_invites.redeem_token(invite["token"])
    assert not result["ok"]
    assert result["reason"] == "revoked"
    assert remote.state("guest_invites.json")["invites"][0]["revoked"]


def test_github_document_updates_include_expected_sha_and_revision(monkeypatch):
    backend = security_state.GitHubSecurityState("owner/private-state", "test-only-token")
    requests = []
    content = base64.b64encode(json.dumps({"revision": 7, "payload": "e30="}).encode()).decode()
    def request(method, path, body=None):
        requests.append((method, path, copy.deepcopy(body)))
        if path == "": return {"private": True}
        if method == "GET": return {"sha": "current-version", "content": content}
        return {}
    monkeypatch.setattr(backend, "_request", request)
    payload, sha, revision = backend.read("owner_pin.json")
    backend.compare_and_swap("owner_pin.json", payload, sha, revision)
    body = requests[-1][2]
    assert body["sha"] == "current-version"
    assert json.loads(base64.b64decode(body["content"]))["revision"] == 8


def test_cloud_never_falls_back_to_old_kv_or_gmail(monkeypatch, tmp_path):
    monkeypatch.setenv("SMARTHOME_SECURITY_BACKEND", "github")
    class Unavailable:
        def read(self, filename):
            raise security_state.SecurityStateUnavailable("network unavailable")
    monkeypatch.setattr(security_state, "get_security_backend", lambda: Unavailable())
    with pytest.raises(security_state.SecurityStateUnavailable):
        security_state.load_security_state("owner_pin.json", tmp_path)


def test_public_repository_is_rejected(monkeypatch):
    backend = security_state.GitHubSecurityState("owner/public", "test-only-token")
    monkeypatch.setattr(backend, "_request", lambda *args: {"private": False})
    with pytest.raises(security_state.SecurityStateUnavailable):
        backend.read("owner_pin.json")
