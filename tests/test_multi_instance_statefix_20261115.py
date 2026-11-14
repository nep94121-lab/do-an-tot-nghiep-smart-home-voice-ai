"""Tests for production bugs S1-S5 (multi-instance CAS, Gemini Live Aoede, <=3s sync, zero audit emojis)."""
from __future__ import annotations

import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import http.server
import itertools
import json
import os
import pathlib
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from typing import Any
import urllib.error
import urllib.request

from fastapi.testclient import TestClient
import pytest

from tests.live_auth_helpers import login_live_owner, prepare_live_auth

ROOT = pathlib.Path(__file__).resolve().parent.parent

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001F9FF"
    "\U0001FA70-\U0001FAFF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "\u2B00-\u2BFF"
    "\u231A-\u23FF"
    "\u2794"
    "]",
    flags=re.UNICODE,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str = "",
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    if token:
        headers["X-Session-Token"] = token
        headers["Cookie"] = f"sh_session_token={token}; session_token={token}"
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw}
        return int(err.code), body


class MockGitHubCasServer:
    """In-memory GitHub Contents API with strict SHA Compare-And-Swap (409 Conflict)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._files: dict[str, tuple[bytes, str]] = {}
        self._seq = 0
        self.puts_count = 0
        self.conflicts_count = 0
        self.gets_count = 0
        self._barrier_lock = threading.Lock()
        self._race_barrier: threading.Barrier | None = None
        self._race_target_suffix: str = ""

        server_ref = self

        class _Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _send_json(self, code: int, obj: dict[str, Any]) -> None:
                raw = json.dumps(obj).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:
                path_only = self.path.split("?", 1)[0]
                parts = path_only.strip("/").split("/")
                # /repos/{owner}/{repo}
                if len(parts) == 3 and parts[0] == "repos":
                    self._send_json(200, {"private": True, "full_name": f"{parts[1]}/{parts[2]}"})
                    return
                # /repos/{owner}/{repo}/contents/{file...}
                if len(parts) >= 5 and parts[0] == "repos" and parts[3] == "contents":
                    rel = "/".join(parts[4:])
                    barrier: threading.Barrier | None = None
                    with server_ref._barrier_lock:
                        if server_ref._race_barrier is not None and (
                            not server_ref._race_target_suffix or rel.endswith(server_ref._race_target_suffix)
                        ):
                            barrier = server_ref._race_barrier
                    if barrier is not None:
                        try:
                            idx = barrier.wait()
                            if idx == 0:
                                with server_ref._barrier_lock:
                                    server_ref._race_barrier = None
                        except Exception:
                            with server_ref._barrier_lock:
                                server_ref._race_barrier = None
                    with server_ref._lock:
                        server_ref.gets_count += 1
                        entry = server_ref._files.get(rel)
                    if entry is None:
                        self._send_json(404, {"message": "Not Found"})
                        return
                    content_bytes, sha = entry
                    self._send_json(
                        200,
                        {
                            "name": rel.rsplit("/", 1)[-1],
                            "path": rel,
                            "sha": sha,
                            "encoding": "base64",
                            "content": base64.b64encode(content_bytes).decode("ascii"),
                        },
                    )
                    return
                self._send_json(404, {"message": "Unknown route"})

            def do_PUT(self) -> None:
                path_only = self.path.split("?", 1)[0]
                parts = path_only.strip("/").split("/")
                length = int(self.headers.get("Content-Length") or "0")
                raw_body = self.rfile.read(length) if length > 0 else b"{}"
                body = json.loads(raw_body.decode("utf-8"))
                if len(parts) >= 5 and parts[0] == "repos" and parts[3] == "contents":
                    rel = "/".join(parts[4:])
                    expected_sha = body.get("sha")
                    new_bytes = base64.b64decode(body.get("content", ""))
                    with server_ref._lock:
                        existing = server_ref._files.get(rel)
                        if existing is None:
                            if expected_sha:
                                server_ref.conflicts_count += 1
                                self._send_json(409, {"message": "sha provided for missing file"})
                                return
                        else:
                            if existing[1] != expected_sha:
                                server_ref.conflicts_count += 1
                                self._send_json(
                                    409,
                                    {
                                        "message": f"sha mismatch: expected {existing[1]}, got {expected_sha}",
                                    },
                                )
                                return
                        server_ref._seq += 1
                        server_ref.puts_count += 1
                        new_sha = hashlib.sha1(
                            new_bytes + f":{server_ref._seq}".encode("utf-8")
                        ).hexdigest()
                        server_ref._files[rel] = (new_bytes, new_sha)
                    self._send_json(200 if existing is not None else 201, {"content": {"sha": new_sha}})
                    return
                self._send_json(404, {"message": "Unknown route"})

        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.port = int(self._httpd.server_address[1])
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def arm_one_shot_get_barrier(self, parties: int = 2, target_suffix: str = "shared_device_state.json") -> None:
        with self._barrier_lock:
            self._race_target_suffix = target_suffix
            self._race_barrier = threading.Barrier(parties, timeout=4.0)

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


class MockSuspendedBlobServer:
    """Simulates Vercel Blob HTTP 403 store_suspended responses."""

    def __init__(self) -> None:
        self.request_count = 0
        self._lock = threading.Lock()
        server_ref = self

        class _Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _reply_403(self) -> None:
                with server_ref._lock:
                    server_ref.request_count += 1
                raw = json.dumps(
                    {"error": {"code": "store_suspended", "message": "This store has been suspended"}}
                ).encode("utf-8")
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:
                self._reply_403()

            def do_PUT(self) -> None:
                length = int(self.headers.get("Content-Length") or "0")
                if length > 0:
                    self.rfile.read(length)
                self._reply_403()

            def do_DELETE(self) -> None:
                self._reply_403()

        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.port = int(self._httpd.server_address[1])
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


class RoundRobinLoadBalancer:
    """HTTP reverse proxy distributing every request round-robin across uvicorn instances."""

    def __init__(self, backends: list[tuple[str, int]]) -> None:
        self.backends = backends
        self.hits = [0 for _ in backends]
        self._idx_iter = itertools.cycle(range(len(backends)))
        self._lock = threading.Lock()
        self._open_socks: list[socket.socket] = []
        lb_ref = self

        class _ProxyHandler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _tunnel_ws(self, host: str, port: int) -> None:
                self.close_connection = True
                upstream = socket.create_connection((host, port), timeout=10.0)
                upstream.settimeout(None)
                client_sock = self.connection
                client_sock.settimeout(None)
                with lb_ref._lock:
                    lb_ref._open_socks.extend((upstream, client_sock))
                req_lines = [f"{self.command} {self.path} HTTP/1.1"]
                for k, v in self.headers.items():
                    if k.lower() == "host":
                        req_lines.append(f"Host: {host}:{port}")
                    else:
                        req_lines.append(f"{k}: {v}")
                raw_head = ("\r\n".join(req_lines) + "\r\n\r\n").encode("latin-1")
                upstream.sendall(raw_head)

                def _pump(src: socket.socket, dst: socket.socket) -> None:
                    try:
                        while True:
                            chunk = src.recv(4096)
                            if not chunk:
                                break
                            dst.sendall(chunk)
                    except OSError:
                        pass
                    finally:
                        for s in (src, dst):
                            try:
                                s.shutdown(socket.SHUT_RDWR)
                            except OSError:
                                pass
                            try:
                                s.close()
                            except OSError:
                                pass

                t_rev = threading.Thread(target=_pump, args=(upstream, client_sock), daemon=True)
                t_rev.start()
                _pump(client_sock, upstream)
                t_rev.join(timeout=1.0)

            def _forward(self) -> None:
                with lb_ref._lock:
                    idx = next(lb_ref._idx_iter)
                    lb_ref.hits[idx] += 1
                host, port = lb_ref.backends[idx]
                if str(self.headers.get("Upgrade") or "").strip().lower() == "websocket":
                    self._tunnel_ws(host, port)
                    return
                length = int(self.headers.get("Content-Length") or "0")
                body = self.rfile.read(length) if length > 0 else None
                fwd_headers = {}
                for k, v in self.headers.items():
                    kl = k.lower()
                    if kl in ("host", "connection", "content-length", "transfer-encoding"):
                        continue
                    fwd_headers[k] = v
                fwd_headers["Connection"] = "close"
                conn = http.client.HTTPConnection(host, port, timeout=15)
                try:
                    conn.request(self.command, self.path, body=body, headers=fwd_headers)
                    resp = conn.getresponse()
                    resp_bytes = resp.read()
                    self.send_response(resp.status)
                    set_cookies = resp.msg.get_all("Set-Cookie") or []
                    for k, v in resp.getheaders():
                        kl = k.lower()
                        if kl in ("transfer-encoding", "connection", "content-length", "set-cookie"):
                            continue
                        self.send_header(k, v)
                    for sc in set_cookies:
                        self.send_header("Set-Cookie", sc)
                    self.send_header("Content-Length", str(len(resp_bytes)))
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(resp_bytes)
                finally:
                    conn.close()

            def do_GET(self) -> None:
                self._forward()

            def do_POST(self) -> None:
                self._forward()

            def do_PUT(self) -> None:
                self._forward()

            def do_DELETE(self) -> None:
                self._forward()

            def do_OPTIONS(self) -> None:
                self._forward()

        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ProxyHandler)
        self._httpd.daemon_threads = True
        self._httpd.block_on_close = False
        self.port = int(self._httpd.server_address[1])
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        with self._lock:
            socks = list(self._open_socks)
            self._open_socks.clear()
        for s in socks:
            try:
                s.close()
            except OSError:
                pass
        self._httpd.shutdown()
        self._httpd.server_close()


def _wait_server_ready(
    base_url: str,
    proc: subprocess.Popen[bytes],
    log_path: pathlib.Path | None = None,
    timeout_sec: float = 15.0,
) -> None:
    deadline = time.monotonic() + timeout_sec
    last_err = ""
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            out = ""
            if log_path is not None and log_path.exists():
                out = log_path.read_text(encoding="utf-8", errors="replace")
            elif proc.stdout:
                out = proc.stdout.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"uvicorn exited early ({proc.returncode}): {out}")
        try:
            code, body = _http_json(f"{base_url}/api/version", timeout=1.5)
            if code == 200 and body.get("ok"):
                return
        except Exception as exc:
            last_err = str(exc)
        time.sleep(0.15)
    raise RuntimeError(f"uvicorn at {base_url} did not become ready within {timeout_sec}s: {last_err}")


def _terminate_proc(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=4)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass


@pytest.fixture
def multi_instance_cluster(tmp_path: pathlib.Path) -> Any:
    """Spawn 2 independent uvicorn instances (distinct TMP/TEMP/DATA_DIR) behind a Round-Robin LB."""
    cas_server = MockGitHubCasServer()
    shared_auth_root = tmp_path / "shared_auth"
    shared_auth_root.mkdir()
    base_env: dict[str, str] = {}
    password = prepare_live_auth(base_env, str(shared_auth_root))

    session_secret = f"multi-inst-secret-{secrets.token_hex(16)}"
    procs: list[subprocess.Popen[bytes]] = []
    log_fps: list[Any] = []
    log_paths: list[pathlib.Path] = []
    ports = [_free_port(), _free_port()]
    urls = [f"http://127.0.0.1:{p}" for p in ports]
    lb: RoundRobinLoadBalancer | None = None

    try:
        for idx, port in enumerate(ports):
            inst_root = tmp_path / f"inst_{idx}"
            inst_data = inst_root / "data"
            inst_vault = inst_root / "vault"
            inst_tmp = inst_root / "tmp"
            inst_data.mkdir(parents=True)
            inst_vault.mkdir(parents=True)
            inst_tmp.mkdir(parents=True)
            shutil.copy2(
                shared_auth_root / "data" / "accounts_3layer.json",
                inst_data / "accounts_3layer.json",
            )

            env = os.environ.copy()
            for drop_k in (
                "PYTEST_CURRENT_TEST",
                "VERCEL",
                "VERCEL_GIT_COMMIT_SHA",
                "BLOB_READ_WRITE_TOKEN",
                "SMARTHOME_FORCE_BLOB_STORE",
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "SMARTHOME_STATE_FILE",
                "SMARTHOME_STATE_BACKEND",
            ):
                env.pop(drop_k, None)

            env["PYTHONPATH"] = str(ROOT)
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTEST"] = "1"
            env["SIMULATOR_OFFLINE_SANDBOX"] = "1"
            env["TMP"] = str(inst_tmp)
            env["TEMP"] = str(inst_tmp)
            env["TMPDIR"] = str(inst_tmp)
            env["SMARTHOME_DATA_DIR"] = str(inst_data)
            env["SMARTHOME_DURABLE_DIR"] = str(inst_vault)
            env["SIMULATOR_SECURITY_STATE_DIR"] = str(shared_auth_root / "data")
            env["SMARTHOME_SESSION_SECRET"] = session_secret
            env["SMARTHOME_SECURITY_REPO"] = "tuananh/smarthome-cas-test"
            env["SMARTHOME_SECURITY_TOKEN"] = "ghp_cas_test_20261115"
            env["SMARTHOME_SECURITY_API_BASE"] = cas_server.base_url
            env["SMARTHOME_FORCE_GITHUB_CAS"] = "1"

            log_path = inst_root / "uvicorn.log"
            log_fp = log_path.open("wb")
            log_fps.append(log_fp)
            log_paths.append(log_path)

            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "simulator.server:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "warning",
                ],
                cwd=str(ROOT),
                env=env,
                stdout=log_fp,
                stderr=subprocess.STDOUT,
            )
            procs.append(proc)

        for url, proc, log_path in zip(urls, procs, log_paths):
            _wait_server_ready(url, proc, log_path=log_path, timeout_sec=18.0)

        owner_token = login_live_owner(urls[0], password)
        lb = RoundRobinLoadBalancer([("127.0.0.1", p) for p in ports])

        yield {
            "inst_a": urls[0],
            "inst_b": urls[1],
            "lb_url": lb.base_url,
            "lb": lb,
            "cas": cas_server,
            "owner_token": owner_token,
            "tmp_path": tmp_path,
        }
    finally:
        if lb is not None:
            lb.close()
        for proc in procs:
            _terminate_proc(proc)
        for fp in log_fps:
            try:
                fp.close()
            except Exception:
                pass
        cas_server.close()


def _dev_states(dev: dict[str, Any]) -> tuple[str, str]:
    dtype = str(dev.get("type") or "").lower()
    if dtype in ("door", "curtain", "gate") or dev.get("id") == "main_door":
        return "OPEN", "CLOSED"
    return "ON", "OFF"


def test_s1a_multi_instance_all_7_devices_toggle_and_monotonic_revision(
    multi_instance_cluster: dict[str, Any],
) -> None:
    """Write on Instance A -> read immediately on Instance B (and reverse) across all 7 devices."""
    inst_a = multi_instance_cluster["inst_a"]
    inst_b = multi_instance_cluster["inst_b"]
    token = multi_instance_cluster["owner_token"]

    st, snap0 = _http_json(f"{inst_a}/api/state", token=token)
    assert st == 200
    devices = snap0["devices"]
    assert len(devices) == 7

    prev_rev = int(snap0.get("state_revision") or snap0.get("revision_seq") or 0)
    for idx, dev in enumerate(devices):
        dev_id = dev["id"]
        on_state, off_state = _dev_states(dev)

        # Write ON on Instance A -> verify immediately on Instance B
        code_a, res_a = _http_json(
            f"{inst_a}/api/device",
            method="POST",
            payload={
                "device_id": dev_id,
                "target_state": on_state,
                "client_id": f"s1a_{idx}",
                "client_seq": idx * 2 + 1,
                "client_ts_ms": int(time.time() * 1000),
            },
            token=token,
        )
        assert code_a == 200 and res_a.get("ok") is True, res_a

        code_rb, snap_b = _http_json(f"{inst_b}/api/state", token=token)
        assert code_rb == 200
        dev_b = next(d for d in snap_b["devices"] if d["id"] == dev_id)
        assert dev_b["state"] == on_state, (
            f"S1 Split-brain: {dev_id} set {on_state} on Instance A but Instance B sees {dev_b['state']}"
        )
        rev_b = int(snap_b.get("state_revision") or snap_b.get("revision_seq") or 0)
        assert rev_b > prev_rev, f"Expected monotonic revision > {prev_rev}, got {rev_b}"
        prev_rev = rev_b

        # Write OFF on Instance B -> verify immediately on Instance A
        code_b, res_b = _http_json(
            f"{inst_b}/api/device",
            method="POST",
            payload={
                "device_id": dev_id,
                "target_state": off_state,
                "client_id": f"s1a_{idx}",
                "client_seq": idx * 2 + 2,
                "client_ts_ms": int(time.time() * 1000),
            },
            token=token,
        )
        assert code_b == 200 and res_b.get("ok") is True, res_b

        code_ra, snap_a = _http_json(f"{inst_a}/api/state", token=token)
        assert code_ra == 200
        dev_a = next(d for d in snap_a["devices"] if d["id"] == dev_id)
        assert dev_a["state"] == off_state, (
            f"S1 Split-brain: {dev_id} set {off_state} on Instance B but Instance A sees {dev_a['state']}"
        )
        rev_a = int(snap_a.get("state_revision") or snap_a.get("revision_seq") or 0)
        assert rev_a > prev_rev, f"Expected monotonic revision > {prev_rev}, got {rev_a}"
        prev_rev = rev_a


def test_s1b_concurrent_cas_conflict_no_lost_update_and_stale_rejection(
    multi_instance_cluster: dict[str, Any],
) -> None:
    """Concurrent mutations across 2 instances trigger CAS 409 conflict & retry without losing either update."""
    inst_a = multi_instance_cluster["inst_a"]
    inst_b = multi_instance_cluster["inst_b"]
    token = multi_instance_cluster["owner_token"]
    cas: MockGitHubCasServer = multi_instance_cluster["cas"]

    # Reset both target devices cleanly first
    for dev_id in ("living_room_light", "bedroom_light"):
        _http_json(
            f"{inst_a}/api/device",
            method="POST",
            payload={"device_id": dev_id, "target_state": "OFF", "client_id": "s1b_init", "client_seq": 1},
            token=token,
        )

    conflicts_before = cas.conflicts_count
    cas.arm_one_shot_get_barrier(parties=2, target_suffix="shared_device_state.json")

    def _toggle_a() -> tuple[int, dict[str, Any]]:
        return _http_json(
            f"{inst_a}/api/device",
            method="POST",
            payload={"device_id": "living_room_light", "target_state": "ON", "client_id": "s1b_a", "client_seq": 10},
            token=token,
        )

    def _toggle_b() -> tuple[int, dict[str, Any]]:
        return _http_json(
            f"{inst_b}/api/device",
            method="POST",
            payload={"device_id": "bedroom_light", "target_state": "ON", "client_id": "s1b_b", "client_seq": 10},
            token=token,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        fa = pool.submit(_toggle_a)
        fb = pool.submit(_toggle_b)
        res_a = fa.result(timeout=15)
        res_b = fb.result(timeout=15)

    assert res_a[0] == 200 and res_a[1].get("ok") is True, res_a
    assert res_b[0] == 200 and res_b[1].get("ok") is True, res_b
    assert cas.conflicts_count > conflicts_before, "Expected real CAS 409 conflict during concurrent writes!"

    _, snap_a = _http_json(f"{inst_a}/api/state", token=token)
    _, snap_b = _http_json(f"{inst_b}/api/state", token=token)
    for snap in (snap_a, snap_b):
        by_id = {d["id"]: d["state"] for d in snap["devices"]}
        assert by_id["living_room_light"] == "ON", f"Lost update on living_room_light: {by_id}"
        assert by_id["bedroom_light"] == "ON", f"Lost update on bedroom_light: {by_id}"

    # Direct CAS stale-revision rejection check on backend class
    from simulator.engine.state_store import FileStateBackend, StateConflictError

    fb = FileStateBackend(multi_instance_cluster["tmp_path"] / "cas_stale_check.json")
    s1 = fb.save_state({"revision_seq": 1, "revision_ts_ns": 100, "devices": {"living_room_light": {"state": "ON", "version": 1}}})
    s2, rev2, token2 = fb.read_cas()
    assert rev2 >= 1
    ok_save, _ = fb.compare_and_swap(
        {**s2, "devices": {"living_room_light": {"state": "OFF", "version": 2}}},
        expected_revision=rev2,
        expected_token=token2,
    )
    assert ok_save is True
    # Attempting stale CAS with rev2/token2 must NOT overwrite newer write
    ok_stale, latest = fb.compare_and_swap(
        {**s1, "devices": {"living_room_light": {"state": "ON", "version": 1}}},
        expected_revision=rev2,
        expected_token=token2,
    )
    assert ok_stale is False
    assert latest["devices"]["living_room_light"]["state"] == "OFF"
    assert isinstance(StateConflictError(), Exception)


def test_s1c_voice_and_text_open_door_cross_instance_truth(
    multi_instance_cluster: dict[str, Any],
) -> None:
    """Close main_door on Instance A -> text & voice 'mở cửa' on Instance B opens door cleanly."""
    inst_a = multi_instance_cluster["inst_a"]
    inst_b = multi_instance_cluster["inst_b"]
    token = multi_instance_cluster["owner_token"]

    # 1) Close door on Instance A -> open via /api/text_command on Instance B
    _http_json(
        f"{inst_a}/api/device",
        method="POST",
        payload={"device_id": "main_door", "target_state": "CLOSED", "client_id": "s1c_1", "client_seq": 1},
        token=token,
    )
    code_txt, body_txt = _http_json(
        f"{inst_b}/api/text_command",
        method="POST",
        payload={"text": "mở cửa"},
        token=token,
    )
    assert code_txt == 200 and body_txt.get("ok") is True, body_txt
    reply_txt = str(body_txt.get("exact_spoken_reply") or body_txt.get("reply") or "")
    assert "mở sẵn rồi" not in reply_txt.lower(), f"Stale false reply from Instance B: {reply_txt}"

    _, snap_a = _http_json(f"{inst_a}/api/state", token=token)
    assert next(d for d in snap_a["devices"] if d["id"] == "main_door")["state"] == "OPEN"

    # 2) Close door on Instance B -> open via /api/voice_command on Instance A
    _http_json(
        f"{inst_b}/api/device",
        method="POST",
        payload={"device_id": "main_door", "target_state": "CLOSED", "client_id": "s1c_2", "client_seq": 2},
        token=token,
    )
    code_vc, body_vc = _http_json(
        f"{inst_a}/api/voice_command",
        method="POST",
        payload={"transcript": "mở cửa", "source": "s1c_voice"},
        token=token,
    )
    assert code_vc == 200 and body_vc.get("ok") is True, body_vc
    reply_vc = str(body_vc.get("exact_spoken_reply") or body_vc.get("reply") or "")
    assert "mở sẵn rồi" not in reply_vc.lower(), f"Stale false reply on voice_command: {reply_vc}"

    _, snap_b = _http_json(f"{inst_b}/api/state", token=token)
    assert next(d for d in snap_b["devices"] if d["id"] == "main_door")["state"] == "OPEN"


def test_s1d_suspended_blob_bypassed_in_favor_of_github_cas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When SMARTHOME_SECURITY_REPO/TOKEN exist alongside 403 store_suspended BLOB_TOKEN, GitHub CAS wins."""
    from simulator.engine.state_store import VercelBlobStateBackend, create_state_backend_from_env

    blob_srv = MockSuspendedBlobServer()
    cas_srv = MockGitHubCasServer()
    try:
        monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_suspended_test_20261115")
        monkeypatch.setenv("SMARTHOME_FORCE_BLOB_STORE", "1")
        monkeypatch.setenv("SMARTHOME_BLOB_API_BASE", blob_srv.base_url)
        monkeypatch.setenv("SMARTHOME_SECURITY_REPO", "tuananh/smarthome-cas-test")
        monkeypatch.setenv("SMARTHOME_SECURITY_TOKEN", "ghp_cas_test_20261115")
        monkeypatch.setenv("SMARTHOME_SECURITY_API_BASE", cas_srv.base_url)
        monkeypatch.setenv("SMARTHOME_FORCE_GITHUB_CAS", "1")
        monkeypatch.delenv("SMARTHOME_STATE_BACKEND", raising=False)

        backend = create_state_backend_from_env()
        assert not isinstance(backend, VercelBlobStateBackend)
        saved = backend.save_state(
            {
                "revision_seq": 1,
                "revision_ts_ns": 1000,
                "devices": {"main_door": {"id": "main_door", "state": "OPEN", "version": 2}},
            }
        )
        assert int(saved.get("revision_seq", 0)) >= 1
        loaded = backend.load_state()
        assert loaded is not None
        assert loaded["devices"]["main_door"]["state"] == "OPEN"
        assert blob_srv.request_count == 0, "Should NOT hit suspended Blob server when GitHub CAS is configured!"
        assert cas_srv.puts_count >= 1
    finally:
        blob_srv.close()
        cas_srv.close()


def test_s2_gemini_live_aoede_audio_config_and_http_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S2: Verify Aoede config drops language_code='vi-VN', multi-turn Live works, and all HTTP branches emit PCM/WAV."""
    from simulator.live import prompt_builder, tts_rejection_vi
    from simulator.rule_engine import SmartHomeEngine
    from simulator.server import app

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    live_cfg = prompt_builder.make_live_config(SmartHomeEngine())
    assert getattr(live_cfg.speech_config, "language_code", None) in (None, "")
    assert live_cfg.speech_config.voice_config.prebuilt_voice_config.voice_name == "Aoede"

    captured_configs: list[Any] = []
    sent_messages: list[str] = []
    pcm_chunk_a = b"\x11\x00" * 1600
    pcm_chunk_b = b"\x22\x00" * 1600

    class _FakeAudioPart:
        def __init__(self, data: bytes) -> None:
            self.inline_data = type("InlineData", (), {"data": data, "mime_type": "audio/pcm;rate=24000"})()

    class _FakeLiveSession:
        async def __aenter__(self) -> _FakeLiveSession:
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        async def send_realtime_input(self, **kwargs: Any) -> None:
            sent_messages.append(f"realtime:{kwargs.get('text', '')}")

        async def send_client_content(self, **kwargs: Any) -> None:
            sent_messages.append("client_content")

        async def receive(self) -> Any:
            sc_a = type("SC", (), {"model_turn": type("MT", (), {"parts": [_FakeAudioPart(pcm_chunk_a)]})(), "turn_complete": False})()
            sc_b = type("SC", (), {"model_turn": type("MT", (), {"parts": [_FakeAudioPart(pcm_chunk_b)]})(), "turn_complete": True})()
            yield type("Msg", (), {"server_content": sc_a, "data": None})()
            yield type("Msg", (), {"server_content": sc_b, "data": None})()

    class _FakeAioLive:
        def connect(self, *, model: str, config: Any) -> _FakeLiveSession:
            captured_configs.append((model, config))
            return _FakeLiveSession()

    class _FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            self.aio = type("Aio", (), {"live": _FakeAioLive()})()

    import google.genai as real_genai

    tts_rejection_vi._LIVE_AOEDE_SESSION_CACHE.clear()
    monkeypatch.setattr(real_genai, "Client", _FakeClient)
    monkeypatch.setenv("GEMINI_API_KEY", "test-fake-gemini-key")
    monkeypatch.delenv("SIMULATOR_OFFLINE_SANDBOX", raising=False)
    monkeypatch.delenv("SMARTHOME_OFFLINE", raising=False)
    monkeypatch.setenv("SMARTHOME_ALLOW_LOCALHOST_BYPASS", "1")

    client = TestClient(app, raise_server_exceptions=False)

    # 1) Public allowlist on /api/voice/aoede_phrase must support ALL fixed EXTENDED_TTS_SCRIPTS phrases
    for phrase in tts_rejection_vi.EXTENDED_TTS_SCRIPTS.values():
        resp = client.post("/api/voice/aoede_phrase", json={"phrase": phrase})
        assert resp.status_code == 200, f"{phrase} -> {resp.status_code} {resp.text}"
        body = resp.json()
        assert body.get("ok") is True
        assert body.get("play_audio") is True
        assert body.get("voice_name") == "Aoede"
        assert body.get("audio_source") == "gemini_live_aoede"
        for key in ("pcm24k_b64", "pcm_b64", "audio_b64", "audio_wav_b64"):
            assert len(str(body.get(key) or "")) > 20, f"Missing {key} for {phrase}"

    assert len(captured_configs) >= 1
    first_model, first_cfg = captured_configs[0]
    assert first_model == "gemini-3.8-live"
    assert getattr(first_cfg.speech_config, "language_code", None) in (None, "")
    assert first_cfg.speech_config.voice_config.prebuilt_voice_config.voice_name == "Aoede"
    assert any(m.startswith("realtime:") for m in sent_messages)

    # 2) ALL /api/text_command branches must return Aoede audio fields cleanly
    auth_headers = {"X-Session-Token": "sess_owner_t1_nep94121"}
    for cmd in ("mở cửa", "nhiệt độ phòng", "độ ẩm đất", "lệnh không tồn tại đâu"):
        r_tc = client.post("/api/text_command", json={"text": cmd}, headers=auth_headers)
        assert r_tc.status_code == 200, r_tc.text
        b_tc = r_tc.json()
        assert b_tc.get("play_audio") is True, f"No play_audio on branch '{cmd}': {b_tc}"
        assert len(str(b_tc.get("pcm24k_b64") or "")) > 20, f"Empty pcm24k_b64 on branch '{cmd}': {b_tc}"
        assert len(str(b_tc.get("audio_wav_b64") or "")) > 20, f"Empty audio_wav_b64 on branch '{cmd}': {b_tc}"


def test_s3_playwright_web_mobile_bidirectional_sync_under_3s(
    multi_instance_cluster: dict[str, Any],
) -> None:
    """S3: 14/14 toggles across 7 devices between Web / (1366) & Mobile /app (390) behind LB in <= 3s."""
    from playwright.sync_api import sync_playwright

    lb_url = multi_instance_cluster["lb_url"]
    lb: RoundRobinLoadBalancer = multi_instance_cluster["lb"]
    token = multi_instance_cluster["owner_token"]

    st, snap0 = _http_json(f"{lb_url}/api/state", token=token)
    assert st == 200
    devices = snap0["devices"]
    assert len(devices) == 7

    for dev in devices:
        _, off_state = _dev_states(dev)
        c_rst, _ = _http_json(
            f"{lb_url}/api/device",
            method="POST",
            payload={"device_id": dev["id"], "target_state": off_state, "client_id": "s3_init", "client_seq": 1},
            token=token,
        )
        assert c_rst == 200

    console_errors: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        cookies = [{"name": n, "value": token, "url": lb_url} for n in ("sh_session_token", "session_token")]
        ctx_web = browser.new_context(viewport={"width": 1366, "height": 768})
        ctx_mob = browser.new_context(viewport={"width": 390, "height": 844})
        ctx_web.add_cookies(cookies)
        ctx_mob.add_cookies(cookies)

        page_web = ctx_web.new_page()
        page_mob = ctx_mob.new_page()

        for pg, label in ((page_web, "web"), (page_mob, "app")):
            pg.on("pageerror", lambda err, lbl=label: page_errors.append(f"{lbl}: {err}"))
            pg.on(
                "console",
                lambda msg, lbl=label: (
                    console_errors.append(f"{lbl}: {msg.text}") if msg.type == "error" else None
                ),
            )

        page_web.goto(f"{lb_url}/", wait_until="domcontentloaded")
        page_mob.goto(f"{lb_url}/app", wait_until="domcontentloaded")

        page_web.wait_for_selector("#dev-card-living_room_light", timeout=15000)
        page_mob.wait_for_selector("#mobileNavTabDevices", timeout=15000)
        page_mob.click("#mobileNavTabDevices")
        page_mob.wait_for_selector("#devGrid [data-device-id='garden_pump']", state="attached", timeout=15000)

        assert page_web.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert page_mob.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        # Wait until initial clean OFF state is visible on both UIs
        for dev in devices:
            did = dev["id"]
            page_web.wait_for_selector(f'#dev-card-{did}[data-state="off"]', timeout=5000)
            page_mob.wait_for_selector(f'#devGrid [data-device-id="{did}"][data-state="off"]', state="attached", timeout=5000)

        max_sync_sec = 0.0
        for dev in devices:
            did = dev["id"]
            t0 = time.monotonic()
            page_web.click(f"#dev-card-{did} .switch")
            page_mob.wait_for_selector(
                f'#devGrid [data-device-id="{did}"][data-state="on"]',
                state="attached",
                timeout=3000,
            )
            dt1 = time.monotonic() - t0
            max_sync_sec = max(max_sync_sec, dt1)
            assert dt1 <= 3.0, f"Web->App sync for {did} took {dt1:.2f}s (> 3.0s)"

            t1 = time.monotonic()
            page_mob.click(f'#devGrid [data-device-id="{did}"]')
            page_web.wait_for_selector(f'#dev-card-{did}[data-state="off"]', timeout=3000)
            dt2 = time.monotonic() - t1
            max_sync_sec = max(max_sync_sec, dt2)
            assert dt2 <= 3.0, f"App->Web sync for {did} took {dt2:.2f}s (> 3.0s)"

        assert lb.hits[0] > 0 and lb.hits[1] > 0, f"Load balancer must hit both backends: {lb.hits}"
        assert not console_errors, f"Console errors: {console_errors}"
        assert not page_errors, f"Page errors: {page_errors}"
        ctx_web.close()
        ctx_mob.close()
        browser.close()


def test_s4_audit_logs_zero_decorative_emojis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S4: Both newly emitted audit logs and legacy emoji logs returned by API contain 0 decorative emojis."""
    from simulator.api import routes_logs
    from simulator.server import app

    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")

    client = TestClient(app, raise_server_exceptions=False)
    auth_headers = {"X-Session-Token": "sess_owner_t1_nep94121"}

    # Trigger fresh device toggle audit log and assert emitted summary has zero emojis
    r_dev = client.post(
        "/api/device",
        json={"device_id": "living_room_light", "target_state": "ON", "client_id": "s4_test", "client_seq": 1},
        headers=auth_headers,
    )
    assert r_dev.status_code == 200

    # Verify legacy decorative emoji log entries are stripped on read via routes_logs
    legacy_rows = [
        {
            "log_id": 999999,
            "timestamp": "2026-11-15 00:00:00",
            "category": "DEVICE_IO",
            "event_type": "mobile_device_toggle",
            "user_name": "Nguyễn Tuấn Anh",
            "tier": 1,
            "summary": "📱 [App/Web] Legacy toggle 🎉 ✅ 🚫 ⏰ 🤖 ➔ 👤 ⚙️ 🎙️ 🧪 🎫 📧",
            "details": {"note": "📱 Legacy emoji payload 🚀"},
        }
    ]
    orig_read_audit_logs = routes_logs.read_audit_logs
    monkeypatch.setattr(routes_logs, "read_audit_logs", lambda limit=500: legacy_rows + orig_read_audit_logs(limit=limit))

    r_dash = client.get("/api/logs/dashboard?limit=50", headers=auth_headers)
    assert r_dash.status_code == 200, r_dash.text
    logs = (
        r_dash.json().get("audit_logs")
        or r_dash.json().get("logs")
        or r_dash.json().get("entries")
        or []
    )
    assert len(logs) >= 2
    summaries = [str(row.get("summary") or "") for row in logs]
    assert any("[App/Web] Legacy toggle" in s for s in summaries)
    for s in summaries:
        assert EMOJI_PATTERN.search(s) is None, f"Emoji leaked in /api/logs/dashboard summary: {s!r}"

    r_sql = client.post(
        "/api/logs/sql_query",
        json={"sql": "SELECT log_id, category, event_type, summary FROM audit_logs ORDER BY log_id DESC LIMIT 20;"},
        headers=auth_headers,
    )
    assert r_sql.status_code == 200, r_sql.text
    sql_rows = r_sql.json().get("rows") or []
    for row in sql_rows:
        summary = str(row.get("summary") or "")
        assert EMOJI_PATTERN.search(summary) is None, f"Emoji leaked in /api/logs/sql_query summary: {summary!r}"

