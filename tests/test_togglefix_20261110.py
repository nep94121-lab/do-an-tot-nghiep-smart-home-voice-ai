"""Regression tests for device toggle oscillation fix (togglefix-20261110, Round 4).

Covers:
1. Idempotent set-state API across all 7 default devices and all 4 REST aliases (/api/device, /api/device_control, /api/devices/{id}/control, /api/device/{id}).
2. Per-device sequencing, multi-client/epoch switching, late out-of-order request rejection, and equal-seq conflict rejection (F3).
3. Sequence-based per-client guard rejecting lower-seq and >24h (>48h, >30d) stale requests without any clock-reset bypass (F8).
4. Single listener binding verified via EventTarget.prototype.addEventListener instrumentation + direct native checkbox click & Spacebar activation parity (F6).
5. Stale HTTP poll (GET /api/state) and push snapshot protection with 10s (102 samples @ 100ms) zero oscillation.
6. Mobile raw WebSocket `device_updated` stale version / pending intent filtering with 10s zero oscillation (F1).
7. Wokwi fresh client bootstrap after high server seq, authoritative rollback on `stale_ignored`, and stale `revision_seq`/`version` rejection with 10s zero oscillation (F2, F4).
8. Main UI WebSocket `manual_toggle` pending tracking >4.3s against zero-revision/zero-seq echo until ACK, with 10s zero oscillation (F5).
9. Stale WebSocket `manual_toggle_ack` and stale HTTP `POST /api/device` responses arriving after a newer accepted snapshot never overwrite newer state, with 10s zero oscillation (F7).
10. Rapid double-click and rapid triple-click with slow/out-of-order backend responses on `/` and `/app`, each verified over a full 10s (102 samples @ 100ms) window.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from simulator.engine.state_store import FileStateBackend, VercelBlobStateBackend
from simulator.rule_engine import SmartHomeEngine
from simulator.server import app


def _create_admin_session_cookies(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/api/session/role",
        json={"role": "chu_nha", "email": "nep94121@gmail.com"},
    )
    if resp.status_code != 200:
        resp = client.post(
            "/api/session/role",
            json={"role": "thanh_vien_a", "email": "thanhviena.hust@gmail.com"},
        )
    assert resp.status_code == 200
    tok = resp.json().get("session_token", "")
    client.cookies.set("sh_session_token", tok)
    client.cookies.set("session_token", tok)
    return {"X-Session-Token": tok}


def test_idempotent_set_state_and_device_versioning() -> None:
    client = TestClient(app)
    headers = _create_admin_session_cookies(client)
    base_ts = int(time.time() * 1000) - 2000
    cid = f"pytest_idemp_{base_ts}"
    seq_counter = 10
    ts_cursor = base_ts

    # Verify all 4 REST aliases on living_room_light
    r0 = client.post(
        "/api/device",
        json={
            "device_id": "living_room_light",
            "action": "turn_off",
            "target_state": "OFF",
            "client_id": cid,
            "client_seq": seq_counter,
            "client_ts_ms": ts_cursor,
        },
        headers=headers,
    )
    assert r0.status_code == 200
    d0 = r0.json()
    assert d0["ok"] is True
    assert d0["state"] == "OFF"
    assert "snapshot" in d0
    assert d0["snapshot"]["revision_seq"] >= 1
    v0 = d0["device_version"]

    seq_counter += 1
    ts_cursor += 20
    r1 = client.post(
        "/api/device_control",
        json={
            "device_id": "living_room_light",
            "action": "toggle",
            "target_state": "ON",
            "client_id": cid,
            "client_seq": seq_counter,
            "client_ts_ms": ts_cursor,
        },
        headers=headers,
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["ok"] is True
    assert d1["state"] == "ON"
    assert d1["device_version"] == v0 + 1

    seq_counter += 1
    ts_cursor += 20
    r2 = client.post(
        "/api/devices/living_room_light/control",
        json={
            "action": "toggle",
            "target_state": "ON",
            "client_id": cid,
            "client_seq": seq_counter,
            "client_ts_ms": ts_cursor,
        },
        headers=headers,
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["ok"] is True
    assert d2["state"] == "ON"
    assert d2["device_version"] == d1["device_version"]

    seq_counter += 1
    ts_cursor += 20
    r3 = client.post(
        "/api/device/living_room_light",
        json={
            "target_state": "OFF",
            "client_id": cid,
            "client_seq": seq_counter,
            "client_ts_ms": ts_cursor,
        },
        headers=headers,
    )
    assert r3.status_code == 200
    assert r3.json()["state"] == "OFF"

    # Verify idempotent set-state + monotonic version stability across all 5 Tier-2 REST devices via HTTP
    tier2_devices = [
        ("living_room_light", "ON", "OFF"),
        ("bedroom_light", "ON", "OFF"),
        ("fan", "ON", "OFF"),
        ("ac", "ON", "OFF"),
        ("garden_pump", "ON", "OFF"),
    ]
    for dev_id, active_st, inactive_st in tier2_devices:
        seq_counter += 1
        ts_cursor += 20
        ra = client.post(
            "/api/device",
            json={
                "device_id": dev_id,
                "target_state": active_st,
                "client_id": cid,
                "client_seq": seq_counter,
                "client_ts_ms": ts_cursor,
            },
            headers=headers,
        ).json()
        assert ra["ok"] is True and ra["state"] == active_st

        seq_counter += 1
        ts_cursor += 20
        rb = client.post(
            "/api/device",
            json={
                "device_id": dev_id,
                "target_state": active_st,
                "client_id": cid,
                "client_seq": seq_counter,
                "client_ts_ms": ts_cursor,
            },
            headers=headers,
        ).json()
        assert rb["ok"] is True and rb["state"] == active_st
        assert rb["device_version"] == ra["device_version"], f"Idempotent repeat incremented version for {dev_id}"

        seq_counter += 1
        ts_cursor += 20
        rc = client.post(
            "/api/device",
            json={
                "device_id": dev_id,
                "target_state": inactive_st,
                "client_id": cid,
                "client_seq": seq_counter,
                "client_ts_ms": ts_cursor,
            },
            headers=headers,
        ).json()
        assert rc["ok"] is True and rc["state"] == inactive_st
        assert rc["device_version"] == ra["device_version"] + 1

    # Also verify all 7 default devices (including Tier-1 main_door OPEN/CLOSED & alarm_siren) on SmartHomeEngine
    async def _verify_all_7_engine() -> None:
        with tempfile.TemporaryDirectory() as td:
            eng = SmartHomeEngine(state_backend=FileStateBackend(Path(td) / "idemp7.json"))
            eng.server_connected = True
            for dev_id, active_st, inactive_st in [
                ("main_door", "OPEN", "CLOSED"),
                ("living_room_light", "ON", "OFF"),
                ("bedroom_light", "ON", "OFF"),
                ("fan", "ON", "OFF"),
                ("ac", "ON", "OFF"),
                ("alarm_siren", "ON", "OFF"),
                ("garden_pump", "ON", "OFF"),
            ]:
                ea = await eng.execute_device_action(
                    dev_id, target_state=active_st, bypass_rbac=True, trigger_chains=False
                )
                eb = await eng.execute_device_action(
                    dev_id, target_state=active_st, bypass_rbac=True, trigger_chains=False
                )
                ec = await eng.execute_device_action(
                    dev_id, target_state=inactive_st, bypass_rbac=True, trigger_chains=False
                )
                assert ea["state"] == active_st and eb["state"] == active_st and ec["state"] == inactive_st
                assert eb["device_version"] == ea["device_version"]
                assert ec["device_version"] == ea["device_version"] + 1

    asyncio.run(_verify_all_7_engine())


def test_out_of_order_stale_sequence_and_timestamp_ignored_by_server() -> None:
    client = TestClient(app)
    headers = _create_admin_session_cookies(client)
    base_ts = int(time.time() * 1000) - 300
    cid = f"pytest_ooo_{base_ts}"

    r_new = client.post(
        "/api/device",
        json={
            "device_id": "fan",
            "action": "turn_off",
            "target_state": "OFF",
            "client_id": cid,
            "client_seq": 50,
            "client_ts_ms": base_ts + 200,
        },
        headers=headers,
    )
    assert r_new.status_code == 200
    d_new = r_new.json()
    assert d_new["ok"] is True
    assert d_new["state"] == "OFF"
    assert d_new["stale_ignored"] is False

    r_old = client.post(
        "/api/device",
        json={
            "device_id": "fan",
            "action": "turn_on",
            "target_state": "ON",
            "client_id": cid,
            "client_seq": 49,
            "client_ts_ms": base_ts + 100,
        },
        headers=headers,
    )
    assert r_old.status_code == 200
    d_old = r_old.json()
    assert d_old["ok"] is True
    assert d_old["stale_ignored"] is True
    assert d_old["state"] == "OFF"

    r_old_ts = client.post(
        "/api/device",
        json={
            "device_id": "fan",
            "action": "turn_on",
            "target_state": "ON",
            "client_ts_ms": base_ts + 50,
        },
        headers=headers,
    )
    assert r_old_ts.status_code == 200
    d_old_ts = r_old_ts.json()
    assert d_old_ts["stale_ignored"] is True
    assert d_old_ts["state"] == "OFF"

    snap = client.get("/api/state", headers=headers).json()
    fan_dev = next(d for d in snap["devices"] if d["id"] == "fan")
    assert fan_dev["state"] == "OFF"


def test_f3_client_switch_epoch_reset_and_conflict_ordering() -> None:
    """Covers Codex F3 counterexamples:
    1. Multi-client switch (client A seq=500 -> client B seq=1 at t+50ms) succeeds immediately.
    2. Anonymous/legacy client_seq reset (seq=100 at t -> seq=1 at t+100ms) succeeds.
    3. Conflicting target_state with identical (seq, ts) is rejected as stale/conflict.
    4. Late request from an older epoch (seq=99 at t+250ms arriving after seq=1 at t+4000ms) is ignored.
    5. Shared FileStateBackend sync preserves client sequence state across engine instances.
    """

    async def _run() -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "shared_state.json"
            backend = FileStateBackend(state_file)
            e1 = SmartHomeEngine(state_backend=backend)
            e2 = SmartHomeEngine(state_backend=backend)
            e1.server_connected = True
            e2.server_connected = True

            t = int(time.time() * 1000)

            # 1. Explicit client_id switch within 50ms
            r_a = await e1.execute_device_action(
                "fan",
                action="turn_off",
                target_state="OFF",
                client_id="web_client_A",
                client_seq=500,
                client_ts_ms=t,
                bypass_rbac=True,
                trigger_chains=False,
            )
            assert r_a["state"] == "OFF"
            assert r_a["stale_ignored"] is False

            # Second engine syncs from shared store and receives fresh Wokwi client_id with seq=1 at t+50ms
            r_b = await e2.execute_device_action(
                "fan",
                action="turn_on",
                target_state="ON",
                client_id="wokwi_client_B",
                client_seq=1,
                client_ts_ms=t + 50,
                bypass_rbac=True,
                trigger_chains=False,
            )
            assert r_b["stale_ignored"] is False
            assert r_b["state"] == "ON"

            # Late packet from client A (seq=501, but older timestamp t+10 < t+50) must not overwrite client B
            r_a_late = await e1.execute_device_action(
                "fan",
                action="turn_off",
                target_state="OFF",
                client_id="web_client_A",
                client_seq=501,
                client_ts_ms=t + 10,
                bypass_rbac=True,
                trigger_chains=False,
            )
            assert r_a_late["stale_ignored"] is True
            assert r_a_late["state"] == "ON"

            # 2. Legacy / client_id-omitted sequence counterexamples from independent_verify.py
            e3 = SmartHomeEngine(state_backend=FileStateBackend(Path(tmpdir) / "legacy_state.json"))
            e3.server_connected = True
            t2 = t + 100_000

            a = await e3.execute_device_action(
                "fan", action="turn_off", target_state="OFF", client_seq=100, client_ts_ms=t2, bypass_rbac=True, trigger_chains=False
            )
            assert a["state"] == "OFF" and a["stale_ignored"] is False

            # Fresh client without client_id sends seq=1 at t2+100 -> MUST be accepted
            b = await e3.execute_device_action(
                "fan", action="turn_on", target_state="ON", client_seq=1, client_ts_ms=t2 + 100, bypass_rbac=True, trigger_chains=False
            )
            assert b["stale_ignored"] is False
            assert b["state"] == "ON"

            # Equal (seq=101, ts=t2+200) with conflicting target_state -> second conflicting one MUST be ignored
            c = await e3.execute_device_action(
                "fan", action="turn_on", target_state="ON", client_seq=101, client_ts_ms=t2 + 200, bypass_rbac=True, trigger_chains=False
            )
            assert c["stale_ignored"] is False and c["state"] == "ON"

            d_conflict = await e3.execute_device_action(
                "fan", action="turn_off", target_state="OFF", client_seq=101, client_ts_ms=t2 + 200, bypass_rbac=True, trigger_chains=False
            )
            assert d_conflict["stale_ignored"] is True
            assert d_conflict["state"] == "ON"

            # Idempotent repeat of SAME state at (seq=101, ts=t2+200) remains valid/idempotent
            d_repeat = await e3.execute_device_action(
                "fan", action="turn_on", target_state="ON", client_seq=101, client_ts_ms=t2 + 200, bypass_rbac=True, trigger_chains=False
            )
            assert d_repeat["state"] == "ON"

            # Epoch reset seq=1 OFF at t2+4000, followed by late older request seq=99 ON from t2+250
            f = await e3.execute_device_action(
                "fan", action="turn_off", target_state="OFF", client_seq=1, client_ts_ms=t2 + 4000, bypass_rbac=True, trigger_chains=False
            )
            assert f["stale_ignored"] is False and f["state"] == "OFF"

            g = await e3.execute_device_action(
                "fan", action="turn_on", target_state="ON", client_seq=99, client_ts_ms=t2 + 250, bypass_rbac=True, trigger_chains=False
            )
            assert g["stale_ignored"] is True
            assert g["state"] == "OFF"

    asyncio.run(_run())


def test_f8_sequence_based_guard_rejects_requests_older_than_24h_and_clock_skew() -> None:
    """Covers Codex F8 counterexample and sequence-based ordering invariants:
    1. Exact F8 counterexample: same `client_id='same-tab'` sends OFF (seq=10, ts=t) then a delayed
       2-day-old ON (seq=1, ts=t - 2*86400000) -> MUST be rejected (`stale_ignored: True`, `state: 'OFF'`)
       and MUST NOT lower `last_client_ts_ms`.
    2. Lower-seq requests on a named `client_id` are rejected strictly by sequence regardless of timestamp
       (25h old, 30d old, equal timestamp, or 3 days in the future).
    3. Higher-seq requests from the currently active `client_id` succeed by monotonic sequence even if
       that client's clock jumped backward, and `sync_from_shared_store` merges per-client state by `(seq, ts_ms)`.
    4. Cross-client and anonymous stale requests older than 24h (>25h, >48h) are rejected (`stale_ignored: True`).
    """

    async def _run() -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = FileStateBackend(Path(tmpdir) / "f8_state.json")
            e1 = SmartHomeEngine(state_backend=backend)
            e2 = SmartHomeEngine(state_backend=backend)
            e1.server_connected = True
            e2.server_connected = True

            t = int(time.time() * 1000)

            r_latest = await e1.execute_device_action(
                "fan",
                target_state="OFF",
                client_id="same-tab",
                client_seq=10,
                client_ts_ms=t,
                bypass_rbac=True,
                trigger_chains=False,
            )
            assert r_latest["state"] == "OFF"
            assert r_latest["stale_ignored"] is False

            # 1 & 2: Lower seq from same-tab across >24h old, >2d old, >30d old, equal ts, and +3d future ts
            for bad_seq, bad_ts in [
                (1, t - 2 * 86_400_000),
                (9, t - 25 * 3_600_000),
                (5, t - 30 * 86_400_000),
                (9, t),
                (2, t + 3 * 86_400_000),
            ]:
                r_stale = await e1.execute_device_action(
                    "fan",
                    target_state="ON",
                    client_id="same-tab",
                    client_seq=bad_seq,
                    client_ts_ms=bad_ts,
                    bypass_rbac=True,
                    trigger_chains=False,
                )
                assert r_stale["stale_ignored"] is True, f"Accepted stale seq={bad_seq}, ts_delta={bad_ts - t}"
                assert r_stale["state"] == "OFF"
                assert int(e1.devices["fan"].get("last_client_ts_ms", 0)) >= t

            # 3: Same active client advancing seq=11 with backward clock skew succeeds, and shared sync preserves seq=11
            r_seq11 = await e1.execute_device_action(
                "fan",
                target_state="ON",
                client_id="same-tab",
                client_seq=11,
                client_ts_ms=t - 5_000,
                bypass_rbac=True,
                trigger_chains=False,
            )
            assert r_seq11["stale_ignored"] is False
            assert r_seq11["state"] == "ON"

            r_seq10_on_e2 = await e2.execute_device_action(
                "fan",
                target_state="OFF",
                client_id="same-tab",
                client_seq=10,
                client_ts_ms=t,
                bypass_rbac=True,
                trigger_chains=False,
            )
            assert r_seq10_on_e2["stale_ignored"] is True
            assert r_seq10_on_e2["state"] == "ON"

            # 4: Newer client sets OFF at t+1000; >24h old cross-client and anonymous requests MUST be rejected
            r_other_new = await e2.execute_device_action(
                "fan",
                target_state="OFF",
                client_id="second-tab",
                client_seq=1,
                client_ts_ms=t + 1_000,
                bypass_rbac=True,
                trigger_chains=False,
            )
            assert r_other_new["stale_ignored"] is False and r_other_new["state"] == "OFF"

            r_cross_old_25h = await e1.execute_device_action(
                "fan",
                target_state="ON",
                client_id="ancient-tab",
                client_seq=1,
                client_ts_ms=t - 25 * 3_600_000,
                bypass_rbac=True,
                trigger_chains=False,
            )
            assert r_cross_old_25h["stale_ignored"] is True
            assert r_cross_old_25h["state"] == "OFF"

            r_anon_old_48h = await e1.execute_device_action(
                "fan",
                target_state="ON",
                client_seq=1,
                client_ts_ms=t - 2 * 86_400_000,
                bypass_rbac=True,
                trigger_chains=False,
            )
            assert r_anon_old_48h["stale_ignored"] is True
            assert r_anon_old_48h["state"] == "OFF"

            # Same named client_id ("same-tab") omitting / zeroing client_seq after c_prev_seq=11 must also be rejected
            r_zero_seq_same_cid = await e1.execute_device_action(
                "fan",
                target_state="ON",
                client_id="same-tab",
                client_seq=0,
                client_ts_ms=t + 5_000,
                bypass_rbac=True,
                trigger_chains=False,
            )
            assert r_zero_seq_same_cid["stale_ignored"] is True
            assert r_zero_seq_same_cid["state"] == "OFF"

    asyncio.run(_run())

    # Also verify via FastAPI HTTP /api/device endpoint
    client = TestClient(app)
    headers = _create_admin_session_cookies(client)
    now_ms = int(time.time() * 1000)
    cid = f"http_f8_{now_ms}"
    ok_res = client.post(
        "/api/device",
        json={"device_id": "fan", "target_state": "OFF", "client_id": cid, "client_seq": 10, "client_ts_ms": now_ms},
        headers=headers,
    ).json()
    assert ok_res["state"] == "OFF" and ok_res["stale_ignored"] is False

    old_2d = client.post(
        "/api/device",
        json={
            "device_id": "fan",
            "target_state": "ON",
            "client_id": cid,
            "client_seq": 1,
            "client_ts_ms": now_ms - 2 * 86_400_000,
        },
        headers=headers,
    ).json()
    assert old_2d["stale_ignored"] is True
    assert old_2d["state"] == "OFF"


def test_vercel_blob_403_circuit_breaker_fast_fail() -> None:
    backend = VercelBlobStateBackend("vercel_blob_rw_FAKE_TOKEN_123")
    call_count = 0

    def fake_urlopen(req: Any, timeout: float = 8.0) -> Any:
        nonlocal call_count
        call_count += 1
        raise urllib.error.HTTPError(
            url=req.full_url,
            code=403,
            msg="Forbidden",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        res1 = backend.load_state()
        assert isinstance(res1, dict)
        assert call_count == 1

        t0 = time.perf_counter()
        res2 = backend.load_state()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert isinstance(res2, dict)
        assert call_count == 1
        assert elapsed_ms < 20.0


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_server(base_url: str, timeout_s: float = 20.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/state", timeout=2.0) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"Server at {base_url} did not start within {timeout_s}s")


@pytest.fixture(scope="module")
def live_server_info() -> Generator[dict[str, str], None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        port = _find_free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)
        env["SIMULATOR_OFFLINE_SANDBOX"] = "1"
        env["SMARTHOME_STATE_BACKEND"] = "file"
        env["SMARTHOME_STATE_FILE"] = str(Path(tmpdir) / "live_test_state.json")
        for key in list(env):
            if any(s in key.upper() for s in ("BLOB_READ_WRITE_TOKEN", "VERCEL_OIDC_TOKEN")):
                env.pop(key, None)

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
            ],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _wait_for_server(base_url)
            req = urllib.request.Request(
                f"{base_url}/api/session/role",
                data=json.dumps({"role": "thanh_vien_a", "email": "thanhviena.hust@gmail.com"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                sess_data = json.loads(resp.read().decode("utf-8"))
                session_token = sess_data.get("session_token", "")

            ws_auth_script = f"""
                sessionStorage.setItem('session_token', {json.dumps(session_token)});
                localStorage.setItem('session_token', {json.dumps(session_token)});
                localStorage.setItem('smarthome_auth_session', JSON.stringify({{
                    email: 'thanhviena.hust@gmail.com',
                    display_name: 'Thành viên A',
                    tier: 2,
                    role: 'MEMBER',
                    session_token: {json.dumps(session_token)}
                }}));
                sessionStorage.setItem('mobileLoggedIn', '1');
                sessionStorage.setItem('mobileLoggedInEmail', 'thanhviena.hust@gmail.com');
                document.cookie = 'sh_session_token=' + {json.dumps(session_token)} + '; path=/';
                document.cookie = 'session_token=' + {json.dumps(session_token)} + '; path=/';
            """
            http_auth_script = (
                "window._FORCE_HTTP_POLLING = true;\nwindow._disableWebSocket = true;\n" + ws_auth_script
            )
            yield {
                "base_url": base_url,
                "session_token": session_token,
                "auth_init_script": http_auth_script,
                "ws_auth_script": ws_auth_script,
            }
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
            user_sess_path = REPO_ROOT / "simulator" / "data" / "user_sessions.json"
            if user_sess_path.exists():
                try:
                    user_sess_path.unlink()
                except Exception:
                    pass


def test_e2e_duplicate_listener_check_and_direct_checkbox_parity(live_server_info: dict[str, str]) -> None:
    """Verifies single listener via independent EventTarget.prototype.addEventListener hook
    AND Codex F6 (direct native `input.click()` & Spacebar keep `checked` in sync with `data-state`).
    """
    asyncio.run(_run_e2e_listener_and_checkbox(live_server_info))


async def _run_e2e_listener_and_checkbox(info: dict[str, str]) -> None:
    from playwright.async_api import async_playwright

    base_url = info["base_url"]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.add_init_script(
            """
            window.__rawListeners = [];
            const _origAdd = EventTarget.prototype.addEventListener;
            EventTarget.prototype.addEventListener = function(type, fn, opts) {
                if (type === 'click' || type === 'change') {
                    window.__rawListeners.push({ el: this, type });
                }
                return _origAdd.call(this, type, fn, opts);
            };
            """
            + info["auth_init_script"]
        )

        post_bodies: list[dict[str, Any]] = []

        async def route_handler(route: Any, request: Any) -> None:
            if not request.url.startswith(base_url):
                await route.abort()
                return
            if "/api/device" in request.url and request.method == "POST":
                post_bodies.append(request.post_data_json or {})
            await route.continue_()

        await page.route("**/*", route_handler)
        await page.goto(f"{base_url}/", wait_until="domcontentloaded")
        await page.wait_for_selector("#dev-card-living_room_light", timeout=15000)

        # Ensure OFF initially and render 10 times
        await page.evaluate(
            """async () => {
                await fetch('/api/device', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ device_id: 'living_room_light', target_state: 'OFF', client_id: 'setup_f6', client_seq: 1, client_ts_ms: Date.now() })
                });
                const snap = await (await fetch('/api/state')).json();
                for (let i = 0; i < 10; i++) {
                    window.applySnapshot(snap);
                }
            }"""
        )
        post_bodies.clear()

        raw_regs = await page.evaluate(
            """() => {
                const card = document.getElementById('dev-card-living_room_light');
                return window.__rawListeners
                    .filter(x => x.el === card || (x.el instanceof Node && card.contains(x.el)))
                    .map(x => ({ type: x.type, tag: x.el.tagName }));
            }"""
        )
        assert raw_regs == [{"type": "click", "tag": "DIV"}], f"Expected single DIV click listener, got: {raw_regs}"

        # 1. Direct native checkbox input.click() (Codex F6 exact reproduction)
        await page.locator("#dev-card-living_room_light .switch input").evaluate("(el) => el.click()")
        immediate = await page.locator("#dev-card-living_room_light").evaluate(
            "(card) => ({ state: card.dataset.state, checked: card.querySelector('.switch input').checked })"
        )
        assert immediate == {"state": "on", "checked": True}, f"F6 regression on direct input.click(): {immediate}"
        await asyncio.sleep(0.25)
        assert len(post_bodies) == 1
        assert post_bodies[0]["target_state"] == "ON"

        # 2. Label .switch click -> OFF, checked=False, exactly 1 more POST
        await page.locator("#dev-card-living_room_light .switch").click()
        after_label = await page.locator("#dev-card-living_room_light").evaluate(
            "(card) => ({ state: card.dataset.state, checked: card.querySelector('.switch input').checked })"
        )
        assert after_label == {"state": "off", "checked": False}
        await asyncio.sleep(0.25)
        assert len(post_bodies) == 2
        assert post_bodies[1]["target_state"] == "OFF"

        # 3. Keyboard Space activation on focused checkbox -> ON, checked=True, 1 more POST, 10s stability
        await page.locator("#dev-card-living_room_light .switch input").focus()
        await page.keyboard.press("Space")
        after_space = await page.locator("#dev-card-living_room_light").evaluate(
            "(card) => ({ state: card.dataset.state, checked: card.querySelector('.switch input').checked })"
        )
        assert after_space == {"state": "on", "checked": True}
        await asyncio.sleep(0.25)
        assert len(post_bodies) == 3
        assert post_bodies[2]["target_state"] == "ON"

        f6_samples: list[tuple[str, bool]] = []
        for _ in range(102):
            cur_pair = await page.locator("#dev-card-living_room_light").evaluate(
                "(card) => [card.dataset.state, card.querySelector('.switch input').checked]"
            )
            f6_samples.append((str(cur_pair[0]), bool(cur_pair[1])))
            await asyncio.sleep(0.1)
        assert all(p == ("on", True) for p in f6_samples), f"F6 10s stability failed: {f6_samples[:15]}"
        srv_f6 = await page.evaluate(
            "async () => (await (await fetch('/api/state')).json()).devices.find(d => d.id === 'living_room_light').state"
        )
        assert srv_f6 == "ON"

        await page.unroute_all(behavior="ignoreErrors")
        await ctx.close()
        await browser.close()


def test_e2e_stale_poll_and_push_protection_with_10s_zero_oscillation(
    live_server_info: dict[str, str],
) -> None:
    asyncio.run(_run_e2e_stale_poll_and_10s_hold(live_server_info))


async def _run_e2e_stale_poll_and_10s_hold(info: dict[str, str]) -> None:
    from playwright.async_api import async_playwright

    base_url = info["base_url"]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.add_init_script(info["auth_init_script"])

        delay_enabled = False

        async def handle_route(route: Any, request: Any) -> None:
            nonlocal delay_enabled
            try:
                if not request.url.startswith(base_url):
                    await route.abort()
                    return
                if "/api/device" in request.url and request.method == "POST":
                    if delay_enabled:
                        await asyncio.sleep(1.2)
                    resp = await route.fetch()
                    await route.fulfill(response=resp)
                    return
                if "/api/state" in request.url and request.method == "GET":
                    if delay_enabled:
                        await asyncio.sleep(0.35)
                    resp = await route.fetch()
                    await route.fulfill(response=resp)
                    return
                await route.continue_()
            except Exception:
                pass

        await page.route("**/*", handle_route)
        await page.goto(f"{base_url}/", wait_until="domcontentloaded")
        await page.wait_for_selector("#dev-card-living_room_light", timeout=15000)

        await page.evaluate(
            """async () => {
                await fetch('/api/device', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ device_id: 'living_room_light', target_state: 'OFF', client_id: 'setup_poll', client_seq: 1, client_ts_ms: Date.now() })
                });
                const r = await fetch('/api/state');
                const s = await r.json();
                window.applySnapshot(s);
            }"""
        )
        assert await page.get_attribute("#dev-card-living_room_light", "data-state") == "off"

        captured_stale = await page.evaluate("async () => await (await fetch('/api/state')).json()")
        delay_enabled = True
        await page.evaluate(
            """() => {
                window._testPollInterval = setInterval(() => {
                    fetch('/api/state').then(r => r.json()).then(s => window.applySnapshot(s)).catch(() => {});
                }, 250);
            }"""
        )
        await asyncio.sleep(0.08)

        await page.click("#dev-card-living_room_light")
        await asyncio.sleep(0.15)
        await page.evaluate("(s) => window.applySnapshot(s)", captured_stale)

        samples_10s: list[str] = []
        for _ in range(102):
            st = await page.get_attribute("#dev-card-living_room_light", "data-state")
            samples_10s.append(str(st))
            await asyncio.sleep(0.1)

        await page.evaluate("clearInterval(window._testPollInterval);")
        delay_enabled = False

        assert all(s == "on" for s in samples_10s), f"Oscillation detected in 10s samples: {samples_10s}"

        srv_state = await page.evaluate(
            "async () => (await (await fetch('/api/state')).json()).devices.find(d => d.id === 'living_room_light').state"
        )
        assert srv_state == "ON"

        await page.unroute_all(behavior="ignoreErrors")
        await ctx.close()
        await browser.close()


def test_e2e_f1_mobile_raw_websocket_stale_push_10s_stability(live_server_info: dict[str, str]) -> None:
    """Covers Codex F1: stale raw `device_updated` WebSocket frame must not flip-flop `/app` UI."""
    asyncio.run(_run_e2e_f1_mobile_ws(live_server_info))


async def _run_e2e_f1_mobile_ws(info: dict[str, str]) -> None:
    from playwright.async_api import async_playwright

    base_url = info["base_url"]
    token = info["session_token"]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        ctx = await browser.new_context()
        await ctx.add_cookies(
            [{"name": n, "value": token, "url": base_url} for n in ("sh_session_token", "session_token")]
        )
        page = await ctx.new_page()
        sockets: list[Any] = []
        await page.add_init_script(info["ws_auth_script"])
        await page.route_web_socket("**/ws", lambda ws: sockets.append(ws))

        async def route_handler(route: Any, request: Any) -> None:
            if not request.url.startswith(base_url):
                await route.abort()
                return
            await route.continue_()

        await page.route("**/*", route_handler)
        await page.goto(f"{base_url}/app", wait_until="domcontentloaded")
        await page.wait_for_selector("#mobileQuickBtnFan", timeout=15000)
        await asyncio.sleep(0.4)
        assert len(sockets) >= 1

        # Set server truth to ON so background polls agree with version 500 snapshot
        await page.evaluate(
            """async () => {
                await fetch('/api/device', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ device_id: 'fan', target_state: 'ON', client_id: 'f1_srv', client_seq: 1, client_ts_ms: Date.now() })
                });
            }"""
        )
        snap = await page.evaluate("async () => await (await fetch('/api/state')).json()")
        snap["revision_seq"] = 999999
        for d in snap["devices"]:
            if d["id"] == "fan":
                d.update(state="ON", version=500, last_client_seq=500)

        sockets[-1].send(json.dumps({"type": "state_snapshot", "snapshot": snap}))
        await asyncio.sleep(0.1)
        assert await page.get_attribute("#mobileQuickBtnFan", "data-state") == "on"

        # Inject stale raw device_updated (version=499 < 500)
        sockets[-1].send(
            json.dumps(
                {
                    "type": "device_updated",
                    "device_id": "fan",
                    "new_state": "OFF",
                    "version": 499,
                    "last_client_seq": 499,
                }
            )
        )

        samples: list[str] = []
        for idx in range(102):
            if idx in (5, 25, 50):
                # Repeatedly inject stale raw push during 10s window
                sockets[-1].send(
                    json.dumps(
                        {
                            "type": "device_updated",
                            "device_id": "fan",
                            "new_state": "OFF",
                            "version": 499,
                            "last_client_seq": 499,
                        }
                    )
                )
            st = await page.get_attribute("#mobileQuickBtnFan", "data-state")
            samples.append(str(st))
            await asyncio.sleep(0.1)

        assert all(s == "on" for s in samples), f"F1 flip-flop detected on mobile raw WS push: {samples[:15]}"

        await page.unroute_all(behavior="ignoreErrors")
        await ctx.close()
        await browser.close()


def test_e2e_f2_f4_wokwi_client_switch_and_stale_snapshot_10s_stability(
    live_server_info: dict[str, str],
) -> None:
    """Covers Codex F2 & F4 on `/wokwi`:
    - Fresh Wokwi client with seq=1 after another client sent seq=500 succeeds on server & UI.
    - If server responds `stale_ignored: true`, Wokwi reconciles button to authoritative server state.
    - Stale snapshot (`revision_seq` / `version` lower than current) is ignored over 10s.
    """
    asyncio.run(_run_e2e_f2_f4_wokwi(live_server_info))


async def _run_e2e_f2_f4_wokwi(info: dict[str, str]) -> None:
    from playwright.async_api import async_playwright

    base_url = info["base_url"]
    token = info["session_token"]

    # Another client sets fan OFF with high seq=500 right before Wokwi opens
    req = urllib.request.Request(
        f"{base_url}/api/device",
        data=json.dumps(
            {
                "device_id": "fan",
                "target_state": "OFF",
                "client_id": "prior_desktop_client",
                "client_seq": 500,
                "client_ts_ms": int(time.time() * 1000),
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Session-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert json.loads(resp.read().decode("utf-8"))["state"] == "OFF"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        ctx = await browser.new_context()
        await ctx.add_cookies(
            [{"name": n, "value": token, "url": base_url} for n in ("sh_session_token", "session_token")]
        )
        page = await ctx.new_page()
        await page.add_init_script(info["ws_auth_script"])
        sockets: list[Any] = []
        await page.route_web_socket("**/ws", lambda ws: sockets.append(ws))

        force_stale_reject = False
        replies: list[dict[str, Any]] = []

        async def route_handler(route: Any, request: Any) -> None:
            nonlocal force_stale_reject
            if not request.url.startswith(base_url):
                await route.abort()
                return
            if "/api/device" in request.url and request.method == "POST":
                if force_stale_reject:
                    snap_now = json.loads(
                        urllib.request.urlopen(f"{base_url}/api/state", timeout=5).read().decode("utf-8")
                    )
                    await route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "ok": True,
                                "device_id": "fan",
                                "state": "ON",
                                "stale_ignored": True,
                                "device_version": 900,
                                "revision_seq": snap_now.get("revision_seq", 900),
                                "snapshot": snap_now,
                            }
                        ),
                    )
                    return
                res = await route.fetch()
                data = await res.json()
                replies.append(data)
                await route.fulfill(response=res)
                return
            await route.continue_()

        await page.route("**/*", route_handler)
        await page.goto(f"{base_url}/wokwi", wait_until="domcontentloaded")
        await page.wait_for_selector("#btn_fan", timeout=15000)
        await page.evaluate("async () => syncWokwiComponents(await (await fetch('/api/state')).json())")

        # 1. Fresh Wokwi client clicks #btn_fan -> must turn ON on BOTH server and button (F2)
        await page.click("#btn_fan")
        await asyncio.sleep(0.35)
        assert len(replies) == 1
        assert replies[0]["stale_ignored"] is False
        assert replies[0]["state"] == "ON"
        assert await page.locator("#btn_fan").evaluate("(e) => e.classList.contains('on')") is True

        # 2. If server returns stale_ignored=True (authoritative state still ON while user clicked OFF),
        # Wokwi must reconcile back to authoritative ON instead of sticking at rejected OFF (F2)
        force_stale_reject = True
        await page.click("#btn_fan")
        await asyncio.sleep(0.25)
        assert await page.locator("#btn_fan").evaluate("(e) => e.classList.contains('on')") is True
        force_stale_reject = False

        # 3. Stale snapshot revision/version must NOT revert #btn_fan to OFF over 10s (F4)
        fresh_snap = await page.evaluate("async () => await (await fetch('/api/state')).json()")
        fresh_snap["revision_seq"] = 10000
        for d in fresh_snap["devices"]:
            if d["id"] == "fan":
                d.update(state="ON", version=500, last_client_seq=500)
        await page.evaluate("(s) => syncWokwiComponents(s)", fresh_snap)

        stale_snap = json.loads(json.dumps(fresh_snap))
        stale_snap["revision_seq"] = 1
        for d in stale_snap["devices"]:
            if d["id"] == "fan":
                d.update(state="OFF", version=1)

        await page.evaluate("(s) => syncWokwiComponents(s)", stale_snap)
        if sockets:
            sockets[-1].send(json.dumps({"type": "state_snapshot", "snapshot": stale_snap}))

        samples: list[bool] = []
        for idx in range(102):
            if idx == 30 and sockets:
                sockets[-1].send(json.dumps({"type": "state_snapshot", "snapshot": stale_snap}))
            is_on = await page.locator("#btn_fan").evaluate("(e) => e.classList.contains('on')")
            samples.append(bool(is_on))
            await asyncio.sleep(0.1)

        assert all(samples), f"F4 Wokwi stale snapshot reverted button state: {samples[:15]}"

        await page.unroute_all(behavior="ignoreErrors")
        await ctx.close()
        await browser.close()


def test_e2e_f5_root_websocket_pending_over_4s_and_10s_stability(
    live_server_info: dict[str, str],
) -> None:
    """Covers Codex F5: WebSocket `manual_toggle` keeps pending protection beyond 4.3s
    against pre-click zero-seq/zero-revision snapshots until ACK arrives, with 10s stability.
    """
    asyncio.run(_run_e2e_f5_root_ws(live_server_info))


async def _run_e2e_f5_root_ws(info: dict[str, str]) -> None:
    from playwright.async_api import async_playwright

    base_url = info["base_url"]
    token = info["session_token"]

    # Ensure server starts with living_room_light == OFF before opening the page
    setup_req = urllib.request.Request(
        f"{base_url}/api/device",
        data=json.dumps(
            {
                "device_id": "living_room_light",
                "target_state": "OFF",
                "client_id": "f5_setup_client",
                "client_seq": 1,
                "client_ts_ms": int(time.time() * 1000),
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Session-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(setup_req, timeout=5) as resp:
        setup_data = json.loads(resp.read().decode("utf-8"))
        assert setup_data["state"] == "OFF"
        cur_ver = int(setup_data.get("device_version") or 1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        ctx = await browser.new_context()
        await ctx.add_cookies(
            [{"name": n, "value": token, "url": base_url} for n in ("sh_session_token", "session_token")]
        )
        page = await ctx.new_page()
        await page.add_init_script(info["ws_auth_script"])

        root_sockets: list[Any] = []
        ws_messages: list[dict[str, Any]] = []

        def on_ws(ws: Any) -> None:
            root_sockets.append(ws)
            ws.on_message(lambda raw: ws_messages.append(json.loads(raw)))

        await page.route_web_socket("**/ws", on_ws)

        async def route_handler(route: Any, request: Any) -> None:
            if not request.url.startswith(base_url):
                await route.abort()
                return
            await route.continue_()

        await page.route("**/*", route_handler)
        await page.goto(f"{base_url}/", wait_until="domcontentloaded")
        await page.wait_for_selector("#dev-card-living_room_light", timeout=15000)
        await asyncio.sleep(0.3)
        assert len(root_sockets) >= 1

        initial = await page.evaluate("async () => await (await fetch('/api/state')).json()")
        initial["revision_seq"] = 0
        for d in initial["devices"]:
            if d["id"] == "living_room_light":
                d.update(state="OFF", last_client_seq=0, last_client_id="", version=cur_ver)
        for ws in root_sockets:
            ws.send(json.dumps({"type": "state_snapshot", "snapshot": initial}))
        await asyncio.sleep(0.1)
        assert await page.get_attribute("#dev-card-living_room_light", "data-state") == "off"

        await page.locator("#dev-card-living_room_light .switch input").evaluate("(e) => e.click()")
        immediate = await page.locator("#dev-card-living_room_light").evaluate(
            "(e) => ({ state: e.dataset.state, checked: e.querySelector('input').checked })"
        )
        assert immediate == {"state": "on", "checked": True}

        samples: list[str] = []
        # Sample across 4.5s BEFORE ack, inject old zero-rev/zero-seq snapshot at 4.4s, then ACK at 5.0s, and continue to 10.2s
        for idx in range(102):
            if idx == 44:
                for ws in root_sockets:
                    ws.send(json.dumps({"type": "state_snapshot", "snapshot": initial}))
            if idx == 50:
                manual_msgs = [m for m in ws_messages if m.get("type") == "manual_toggle"]
                assert len(manual_msgs) == 1
                m0 = manual_msgs[0]
                commit_req = urllib.request.Request(
                    f"{base_url}/api/device",
                    data=json.dumps(
                        {
                            "device_id": "living_room_light",
                            "target_state": "ON",
                            "client_id": m0.get("client_id"),
                            "client_seq": m0.get("client_seq", 1),
                            "client_ts_ms": m0.get("client_ts_ms", int(time.time() * 1000)),
                            "request_id": m0.get("request_id"),
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json", "X-Session-Token": token},
                    method="POST",
                )
                with urllib.request.urlopen(commit_req, timeout=5) as c_resp:
                    c_data = json.loads(c_resp.read().decode("utf-8"))
                for ws in root_sockets:
                    ws.send(
                        json.dumps(
                            {
                                "type": "manual_toggle_ack",
                                "ok": True,
                                "device_id": "living_room_light",
                                "state": c_data["state"],
                                "device_version": c_data["device_version"],
                                "revision_seq": c_data["revision_seq"],
                                "client_id": m0.get("client_id"),
                                "client_seq": m0.get("client_seq"),
                                "stale_ignored": False,
                                "snapshot": c_data["snapshot"],
                            }
                        )
                    )
            st = await page.get_attribute("#dev-card-living_room_light", "data-state")
            samples.append(str(st))
            await asyncio.sleep(0.1)

        assert all(s == "on" for s in samples), f"F5 WS pending protection failed over 10s: {samples}"
        srv_f5 = await page.evaluate(
            "async () => (await (await fetch('/api/state')).json()).devices.find(d => d.id === 'living_room_light').state"
        )
        assert srv_f5 == "ON"

        await page.unroute_all(behavior="ignoreErrors")
        await ctx.close()
        await browser.close()


def test_e2e_f3_multi_client_switch_and_late_old_response_10s_stability(
    live_server_info: dict[str, str],
) -> None:
    """Covers Codex F3 in real multi-tab browser execution:
    - Tab A builds high seq=50, then sends a slow request (delayed 1.2s in network) for ON.
    - Tab B (fresh client_id, seq=1) clicks OFF 150ms later and finishes immediately.
    - When Tab A's late older-timestamp request finally reaches the server at 1.2s, server rejects it (`stale_ignored: true`)
      and reconciles Tab A to authoritative `OFF`, while Tab B stays `OFF` for 10.2s (102 samples @ 100ms) with 0 oscillation.
    """
    asyncio.run(_run_e2e_f3_multi_client(live_server_info))


async def _run_e2e_f3_multi_client(info: dict[str, str]) -> None:
    from playwright.async_api import async_playwright

    base_url = info["base_url"]
    token = info["session_token"]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        ctx_a = await browser.new_context()
        ctx_b = await browser.new_context()
        page_a = await ctx_a.new_page()
        page_b = await ctx_b.new_page()
        await page_a.add_init_script(info["auth_init_script"])
        await page_b.add_init_script(info["auth_init_script"])

        delay_tab_a = False
        tab_a_replies: list[dict[str, Any]] = []
        tab_b_replies: list[dict[str, Any]] = []

        async def route_a(route: Any, request: Any) -> None:
            if not request.url.startswith(base_url):
                await route.abort()
                return
            if "/api/device" in request.url and request.method == "POST":
                if delay_tab_a:
                    await asyncio.sleep(1.2)
                res = await route.fetch()
                tab_a_replies.append(await res.json())
                await route.fulfill(response=res)
                return
            await route.continue_()

        async def route_b(route: Any, request: Any) -> None:
            if not request.url.startswith(base_url):
                await route.abort()
                return
            if "/api/device" in request.url and request.method == "POST":
                res = await route.fetch()
                tab_b_replies.append(await res.json())
                await route.fulfill(response=res)
                return
            await route.continue_()

        await page_a.route("**/*", route_a)
        await page_b.route("**/*", route_b)
        await page_a.goto(f"{base_url}/", wait_until="domcontentloaded")
        await page_b.goto(f"{base_url}/app", wait_until="domcontentloaded")
        await page_a.wait_for_selector("#dev-card-fan", timeout=15000)
        await page_b.wait_for_selector("#mobileQuickBtnFan", timeout=15000)

        # Ensure fan starts OFF on both UIs and server
        init_req = urllib.request.Request(
            f"{base_url}/api/device",
            data=json.dumps(
                {
                    "device_id": "fan",
                    "target_state": "OFF",
                    "client_id": f"f3_init_{int(time.time() * 1000)}",
                    "client_seq": 1,
                    "client_ts_ms": int(time.time() * 1000),
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Session-Token": token},
            method="POST",
        )
        with urllib.request.urlopen(init_req, timeout=5) as r_init:
            snap0 = json.loads(r_init.read().decode("utf-8"))["snapshot"]
        await page_a.evaluate(
            """(s) => {
                window.applySnapshot(s);
                window.__deviceControlState['fan'] = Object.assign(
                    window.__deviceControlState['fan'] || {},
                    { seq: 49, lastConfirmedSeq: 49 }
                );
            }""",
            snap0,
        )
        await page_b.evaluate("(s) => window.renderState(s)", snap0)
        assert await page_a.get_attribute("#dev-card-fan", "data-state") == "off"
        assert await page_b.get_attribute("#mobileQuickBtnFan", "data-state") == "off"

        delay_tab_a = True
        # Tab A clicks fan OFF -> ON (seq=50, timestamp T0, delayed 1.2s in transit)
        await page_a.click("#dev-card-fan")
        await asyncio.sleep(0.12)
        # Meanwhile Tab B (fresh client_id) clicks OFF -> ON (seq=1) then ON -> OFF (seq=2), both completing immediately!
        await page_b.click("#mobileQuickBtnFan")
        await asyncio.sleep(0.12)
        await page_b.click("#mobileQuickBtnFan")

        samples_b: list[str] = []
        for idx in range(102):
            if idx in (15, 30, 60):
                await page_b.evaluate("async () => window.renderState(await (await fetch('/api/state')).json())")
            st_b = await page_b.get_attribute("#mobileQuickBtnFan", "data-state")
            samples_b.append(str(st_b))
            await asyncio.sleep(0.1)

        delay_tab_a = False
        assert len(tab_b_replies) >= 1
        assert tab_b_replies[-1]["stale_ignored"] is False
        assert tab_b_replies[-1]["state"] == "OFF"
        assert len(tab_a_replies) >= 1
        assert tab_a_replies[-1]["stale_ignored"] is True
        assert tab_a_replies[-1]["state"] == "OFF"
        # Tab A reconciled its rejected ON back to authoritative OFF!
        assert await page_a.get_attribute("#dev-card-fan", "data-state") == "off"
        assert all(s == "off" for s in samples_b), f"F3 Tab B oscillated: {samples_b}"

        srv_f3 = await page_b.evaluate(
            "async () => (await (await fetch('/api/state')).json()).devices.find(d => d.id === 'fan').state"
        )
        assert srv_f3 == "OFF"

        await page_a.unroute_all(behavior="ignoreErrors")
        await page_b.unroute_all(behavior="ignoreErrors")
        await ctx_a.close()
        await ctx_b.close()
        await browser.close()


def test_e2e_rapid_double_and_triple_clicks_with_10s_stability(
    live_server_info: dict[str, str],
) -> None:
    """Verifies rapid double-click and rapid triple-click with slow out-of-order responses
    maintain 100% zero oscillation for a full 10.2s (102 samples @ 100ms) each on `/` and `/app`.
    """
    asyncio.run(_run_e2e_rapid_clicks_10s(live_server_info))


async def _run_e2e_rapid_clicks_10s(info: dict[str, str]) -> None:
    from playwright.async_api import async_playwright

    base_url = info["base_url"]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")

        async def _exercise_surface(path: str, selector: str, dev_id: str, render_fn: str) -> None:
            ctx = await browser.new_context()
            page = await ctx.new_page()
            await page.add_init_script(info["auth_init_script"])

            post_num = 0
            delay_active = False

            async def handle_route(route: Any, request: Any) -> None:
                nonlocal post_num
                try:
                    if not request.url.startswith(base_url):
                        await route.abort()
                        return
                    if "/api/device" in request.url and request.method == "POST":
                        if delay_active:
                            post_num += 1
                            cur_n = post_num
                            await asyncio.sleep(0.85 if cur_n == 1 else 0.1)
                        resp = await route.fetch()
                        await route.fulfill(response=resp)
                        return
                    await route.continue_()
                except Exception:
                    pass

            await page.route("**/*", handle_route)
            await page.goto(f"{base_url}{path}", wait_until="domcontentloaded")
            await page.wait_for_selector(selector, timeout=15000)

            await page.evaluate(
                f"""async () => {{
                    await fetch('/api/device', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ device_id: {json.dumps(dev_id)}, target_state: 'OFF', client_id: 'rapid_init_' + {json.dumps(dev_id)}, client_seq: 1, client_ts_ms: Date.now() }})
                    }});
                    const s = await (await fetch('/api/state')).json();
                    window[{json.dumps(render_fn)}](s);
                }}"""
            )
            assert await page.get_attribute(selector, "data-state") == "off"

            # Phase A: Rapid double-click spaced 90ms apart (2 separate dispatches: #1 slow 850ms ON, #2 fast 100ms OFF)
            post_num = 0
            delay_active = True
            await page.click(selector)
            await asyncio.sleep(0.09)
            await page.click(selector)

            double_samples: list[str] = []
            for _ in range(102):
                st = await page.get_attribute(selector, "data-state")
                double_samples.append(str(st))
                await asyncio.sleep(0.1)

            assert all(s == "off" for s in double_samples), (
                f"Double-click 10s oscillation on {path} ({dev_id}): {double_samples}"
            )
            srv_after_double = await page.evaluate(
                f"async () => (await (await fetch('/api/state')).json()).devices.find(d => d.id === {json.dumps(dev_id)}).state"
            )
            assert srv_after_double == "OFF"

            # Phase B: Rapid triple-click within debounce window (OFF -> ON -> OFF -> ON) + 10.2s observation
            post_num = 0
            await page.click(selector)
            await page.click(selector)
            await page.click(selector)

            triple_samples: list[str] = []
            for _ in range(102):
                st = await page.get_attribute(selector, "data-state")
                triple_samples.append(str(st))
                await asyncio.sleep(0.1)

            delay_active = False
            assert all(s == "on" for s in triple_samples), (
                f"Triple-click 10s oscillation on {path} ({dev_id}): {triple_samples}"
            )
            srv_after_triple = await page.evaluate(
                f"async () => (await (await fetch('/api/state')).json()).devices.find(d => d.id === {json.dumps(dev_id)}).state"
            )
            assert srv_after_triple == "ON"

            await page.unroute_all(behavior="ignoreErrors")
            await ctx.close()

        await asyncio.gather(
            _exercise_surface("/", "#dev-card-living_room_light", "living_room_light", "applySnapshot"),
            _exercise_surface("/app", "#mobileQuickBtnFan", "fan", "renderState"),
        )
        await browser.close()


def test_e2e_f7_stale_ws_ack_after_newer_snapshot_10s_stability(live_server_info: dict[str, str]) -> None:
    """Covers Codex F7 counterexample:
    1. UI sends `manual_toggle` ON (version vA, revision rA) over WebSocket; snapshot A confirms ON;
       another client commits OFF on the real server (version vB > vA, revision rB > rA) and snapshot B
       sets UI to OFF; then delayed `manual_toggle_ack` for version vA arrives (including both normal ACK
       and `stale_ignored` ACK carrying stale version vA). UI MUST stay OFF across 102 samples @ 100ms (>10s)
       matching authoritative server state OFF.
    2. Also verifies when snapshot B (vB > vA) arrives WHILE `manual_toggle` A is still pending (before
       snapshot A ever arrived), followed by late ACK A (vA < vB): clearing pending converges immediately to OFF.
    """
    asyncio.run(_run_e2e_f7_stale_ws_ack(live_server_info))


async def _run_e2e_f7_stale_ws_ack(info: dict[str, str]) -> None:
    from playwright.async_api import async_playwright

    base_url = info["base_url"]
    token = info["session_token"]

    def _api_post(payload: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            f"{base_url}/api/device",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Session-Token": token},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return dict(json.loads(resp.read().decode("utf-8")))

    def _api_state() -> dict[str, Any]:
        req = urllib.request.Request(
            f"{base_url}/api/state",
            headers={"X-Session-Token": token},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return dict(json.loads(resp.read().decode("utf-8")))

    dev = "living_room_light"
    _api_post(
        {
            "device_id": dev,
            "target_state": "OFF",
            "client_id": "f7_setup",
            "client_seq": 1,
            "client_ts_ms": int(time.time() * 1000),
        }
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        ctx = await browser.new_context()
        await ctx.add_cookies(
            [{"name": n, "value": token, "url": base_url} for n in ("sh_session_token", "session_token")]
        )
        page = await ctx.new_page()
        await page.add_init_script(info["ws_auth_script"])

        sockets: list[Any] = []
        sent_ws: list[dict[str, Any]] = []

        def on_ws(ws: Any) -> None:
            sockets.append(ws)
            ws.on_message(lambda raw: sent_ws.append(json.loads(raw)))

        await page.route_web_socket("**/ws", on_ws)

        async def route_local(route: Any, request: Any) -> None:
            if not request.url.startswith(base_url):
                await route.abort()
                return
            await route.continue_()

        await page.route("**/*", route_local)
        await page.goto(f"{base_url}/", wait_until="domcontentloaded")
        await page.wait_for_selector(f"#dev-card-{dev}", timeout=15000)
        await asyncio.sleep(0.35)
        assert len(sockets) >= 1

        init_snap = _api_state()
        sockets[-1].send(json.dumps({"type": "state_snapshot", "snapshot": init_snap}))
        await asyncio.sleep(0.1)
        assert await page.get_attribute(f"#dev-card-{dev}", "data-state") == "off"

        # Phase 1: Exact Codex F7 counterexample
        await page.click(f"#dev-card-{dev}")
        await asyncio.sleep(0.15)
        manual_1 = [m for m in sent_ws if m.get("type") == "manual_toggle"][-1]
        res_a = _api_post(manual_1)
        assert res_a["state"] == "ON"

        sockets[-1].send(json.dumps({"type": "state_snapshot", "snapshot": res_a["snapshot"]}))
        await asyncio.sleep(0.1)
        assert await page.get_attribute(f"#dev-card-{dev}", "data-state") == "on"

        res_b = _api_post(
            {
                "device_id": dev,
                "target_state": "OFF",
                "client_id": "f7_second_real_client",
                "client_seq": 1,
                "client_ts_ms": int(time.time() * 1000) + 20,
            }
        )
        assert res_b["state"] == "OFF"
        assert res_b["device_version"] > res_a["device_version"]
        assert res_b["revision_seq"] > res_a["revision_seq"]

        sockets[-1].send(json.dumps({"type": "state_snapshot", "snapshot": res_b["snapshot"]}))
        await asyncio.sleep(0.1)
        assert await page.get_attribute(f"#dev-card-{dev}", "data-state") == "off"

        ack_fields = [
            "ok",
            "device_id",
            "state",
            "device_version",
            "revision_seq",
            "client_id",
            "client_seq",
            "request_id",
            "stale_ignored",
            "snapshot",
        ]
        stale_ack = {k: res_a.get(k) for k in ack_fields}
        stale_ack["type"] = "manual_toggle_ack"
        sockets[-1].send(json.dumps(stale_ack))

        # Also test stale_ignored=True carrying an older version/state than res_b
        stale_ignored_ack = dict(stale_ack, stale_ignored=True)
        sockets[-1].send(json.dumps(stale_ignored_ack))

        samples: list[str] = []
        checked_samples: list[bool] = []
        for _ in range(102):
            dom_pair = await page.locator(f"#dev-card-{dev}").evaluate(
                "(el) => ({ state: el.dataset.state, checked: el.querySelector('input').checked })"
            )
            samples.append(str(dom_pair["state"]))
            checked_samples.append(bool(dom_pair["checked"]))
            await asyncio.sleep(0.1)

        srv_now = next(d["state"] for d in _api_state()["devices"] if d["id"] == dev)
        assert srv_now == "OFF"
        assert all(s == "off" for s in samples), f"F7 stale ACK overwrote newer OFF state: {samples[:10]}"
        assert all(c is False for c in checked_samples)

        # Phase 2: Snapshot B arrives WHILE manual_toggle A2 is still pending on WS, then stale ACK A2 arrives
        await page.click(f"#dev-card-{dev}")
        await asyncio.sleep(0.15)
        manual_2 = [m for m in sent_ws if m.get("type") == "manual_toggle"][-1]
        res_a2 = _api_post(manual_2)
        assert res_a2["state"] == "ON"
        res_b2 = _api_post(
            {
                "device_id": dev,
                "target_state": "OFF",
                "client_id": "f7_second_real_client",
                "client_seq": 2,
                "client_ts_ms": int(time.time() * 1000) + 50,
            }
        )
        assert res_b2["state"] == "OFF" and res_b2["device_version"] > res_a2["device_version"]

        # Deliver ONLY snapshot B2 while manual_2 is still pending, then deliver late ACK A2
        sockets[-1].send(json.dumps({"type": "state_snapshot", "snapshot": res_b2["snapshot"]}))
        await asyncio.sleep(0.08)
        stale_ack_2 = {k: res_a2.get(k) for k in ack_fields}
        stale_ack_2["type"] = "manual_toggle_ack"
        sockets[-1].send(json.dumps(stale_ack_2))
        await asyncio.sleep(0.12)

        assert await page.get_attribute(f"#dev-card-{dev}", "data-state") == "off"
        await page.unroute_all(behavior="ignoreErrors")
        await ctx.close()
        await browser.close()


def test_e2e_f7_stale_http_response_after_newer_snapshot_across_all_uis(
    live_server_info: dict[str, str],
) -> None:
    """Verifies across all 3 UIs (`/` bedroom_light, `/app` fan, `/wokwi` living_room_light) that when
    an HTTP `POST /api/device` executes at version vA, a newer server state vB > vA arrives via snapshot
    before the HTTP response resolves in the browser, the late HTTP response (vA < vB) never overwrites vB,
    and `/` `bedroom_light` holds `OFF` across 102 samples @ 100ms (>10s) with 0 oscillation.
    """
    asyncio.run(_run_e2e_f7_stale_http_all_uis(live_server_info))


async def _run_e2e_f7_stale_http_all_uis(info: dict[str, str]) -> None:
    from playwright.async_api import async_playwright

    base_url = info["base_url"]
    token = info["session_token"]

    def _api_post(payload: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            f"{base_url}/api/device",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Session-Token": token},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return dict(json.loads(resp.read().decode("utf-8")))

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")

        async def _check_ui(
            path: str,
            click_sel: str,
            dev_id: str,
            inactive_st: str,
            render_fn: str,
            observe_10s: bool,
        ) -> None:
            _api_post(
                {
                    "device_id": dev_id,
                    "target_state": inactive_st,
                    "client_id": f"f7_http_init_{dev_id}",
                    "client_seq": 1,
                    "client_ts_ms": int(time.time() * 1000),
                }
            )
            ctx = await browser.new_context()
            await ctx.add_cookies(
                [{"name": n, "value": token, "url": base_url} for n in ("sh_session_token", "session_token")]
            )
            page = await ctx.new_page()
            await page.add_init_script(info["auth_init_script"])
            if path == "/wokwi":
                await page.route_web_socket("**/ws", lambda ws: None)

            intercept_mode = ""
            fulfilled_evt = asyncio.Event()
            held_overlap_req1: list[tuple[Any, Any]] = []
            overlap_req1_seen = asyncio.Event()

            async def handle_route(route: Any, request: Any) -> None:
                nonlocal intercept_mode
                if not request.url.startswith(base_url):
                    await route.abort()
                    return
                if intercept_mode == "overlap_hold_first" and "/api/device" in request.url and request.method == "POST":
                    intercept_mode = "overlap_handle_second"
                    held_overlap_req1.append((route, request))
                    overlap_req1_seen.set()
                    return
                if intercept_mode == "overlap_handle_second" and "/api/device" in request.url and request.method == "POST":
                    intercept_mode = ""
                    route1, _ = held_overlap_req1.pop(0)
                    resp_1 = await route1.fetch()
                    body_1 = json.loads((await resp_1.body()).decode("utf-8"))
                    resp_2 = await route.fetch()
                    body_2 = json.loads((await resp_2.body()).decode("utf-8"))
                    active_st = "OPEN" if dev_id == "main_door" else "ON"
                    body_ext = await asyncio.to_thread(
                        _api_post,
                        {
                            "device_id": dev_id,
                            "target_state": active_st,
                            "client_id": f"f7_http_overlap_ext_{dev_id}",
                            "client_seq": 1,
                            "client_ts_ms": int(time.time() * 1000) + 50,
                        },
                    )
                    assert body_ext["device_version"] > body_2["device_version"] >= body_1["device_version"]
                    await page.evaluate(
                        "(arg) => window[arg.fn](arg.snap)",
                        {"fn": render_fn, "snap": body_ext["snapshot"]},
                    )
                    await asyncio.sleep(0.05)
                    # Fulfill newer request #2 FIRST (pendingCount 2 -> 1), then older request #1 SECOND (pendingCount 1 -> 0)
                    await route.fulfill(response=resp_2)
                    await asyncio.sleep(0.05)
                    await route1.fulfill(response=resp_1)
                    fulfilled_evt.set()
                    return
                if intercept_mode == "fail_after_newer_snap" and "/api/device" in request.url and request.method == "POST":
                    intercept_mode = ""
                    body_ext_off = await asyncio.to_thread(
                        _api_post,
                        {
                            "device_id": dev_id,
                            "target_state": inactive_st,
                            "client_id": f"f7_http_fail_ext_{dev_id}",
                            "client_seq": 1,
                            "client_ts_ms": int(time.time() * 1000) + 80,
                        },
                    )
                    await page.evaluate(
                        "(arg) => window[arg.fn](arg.snap)",
                        {"fn": render_fn, "snap": body_ext_off["snapshot"]},
                    )
                    await asyncio.sleep(0.05)
                    await route.abort("failed")
                    fulfilled_evt.set()
                    return
                if intercept_mode and "/api/device" in request.url and request.method == "POST":
                    mode_now = intercept_mode
                    intercept_mode = ""
                    resp_a = await route.fetch()
                    body_a = json.loads((await resp_a.body()).decode("utf-8"))
                    body_b = await asyncio.to_thread(
                        _api_post,
                        {
                            "device_id": dev_id,
                            "target_state": inactive_st,
                            "client_id": f"f7_http_other_{dev_id}_{mode_now}",
                            "client_seq": 1,
                            "client_ts_ms": int(time.time() * 1000) + 30,
                        },
                    )
                    assert body_b["device_version"] > body_a["device_version"]
                    if mode_now == "after_both_snapshots":
                        await page.evaluate(
                            "(arg) => window[arg.fn](arg.snap)",
                            {"fn": render_fn, "snap": body_a["snapshot"]},
                        )
                    await page.evaluate(
                        "(arg) => window[arg.fn](arg.snap)",
                        {"fn": render_fn, "snap": body_b["snapshot"]},
                    )
                    await asyncio.sleep(0.05)
                    await route.fulfill(response=resp_a)
                    fulfilled_evt.set()
                    return
                await route.continue_()

            await page.route("**/*", handle_route)
            await page.goto(f"{base_url}{path}", wait_until="domcontentloaded")
            await page.wait_for_selector(click_sel, timeout=15000)
            await page.evaluate(
                f"async () => {{ const s = await (await fetch('/api/state')).json(); window[{json.dumps(render_fn)}](s); }}"
            )
            await asyncio.sleep(0.1)

            async def _read_ui_is_active() -> bool:
                if path == "/wokwi":
                    return bool(await page.locator(click_sel).evaluate("(el) => el.classList.contains('on')"))
                st = await page.get_attribute(click_sel, "data-state")
                return st == "on"

            # Phase 1: Snapshot A + newer Snapshot B arrive, then stale HTTP response A resolves -> 102 samples (>10s)
            fulfilled_evt.clear()
            intercept_mode = "after_both_snapshots"
            await page.click(click_sel)
            await asyncio.wait_for(fulfilled_evt.wait(), timeout=10.0)
            await asyncio.sleep(0.08)

            if observe_10s:
                samples: list[bool] = []
                for _ in range(102):
                    samples.append(await _read_ui_is_active())
                    await asyncio.sleep(0.1)
                assert all(x is False for x in samples), f"Stale HTTP response overwrote newer state on {path}: {samples[:10]}"
            else:
                assert (await _read_ui_is_active()) is False, f"Stale HTTP response overwrote newer state on {path}"

            # Phase 2: Newer Snapshot B arrives while HTTP A is still in flight (without Snapshot A), then HTTP A resolves
            fulfilled_evt.clear()
            intercept_mode = "while_pending"
            await page.click(click_sel)
            await asyncio.wait_for(fulfilled_evt.wait(), timeout=10.0)
            await asyncio.sleep(0.08)
            assert (await _read_ui_is_active()) is False, f"Pending-interleaved stale HTTP response stuck on {path}"

            # Phase 3: 2 overlapping HTTP requests (#1 ON, #2 OFF) + newer Snapshot ON (v4) while both pending,
            # resolved out-of-order (#2 first: pending 2->1, #1 second: pending 1->0) must converge to ON (v4)
            fulfilled_evt.clear()
            overlap_req1_seen.clear()
            intercept_mode = "overlap_hold_first"
            await page.click(click_sel)
            await asyncio.wait_for(overlap_req1_seen.wait(), timeout=10.0)
            await page.click(click_sel)
            await asyncio.wait_for(fulfilled_evt.wait(), timeout=10.0)
            await asyncio.sleep(0.08)
            assert (await _read_ui_is_active()) is True, f"Overlapping out-of-order HTTP responses stuck at OFF on {path}"
            if path == "/wokwi" and dev_id == "garden_pump":
                pump_txt = await page.locator("#pump_state_txt").text_content()
                assert pump_txt is not None and "ON" in pump_txt, f"Wokwi garden_pump SVG out of sync: {pump_txt}"

            # Phase 4: Click OFF while ON, newer Snapshot OFF arrives while pending, then request fails -> stays OFF
            fulfilled_evt.clear()
            intercept_mode = "fail_after_newer_snap"
            await page.click(click_sel)
            await asyncio.wait_for(fulfilled_evt.wait(), timeout=10.0)
            await asyncio.sleep(0.08)
            assert (await _read_ui_is_active()) is False, f"Rollback overwrote newer serverKnownState on {path}"

            await page.unroute_all(behavior="ignoreErrors")
            await ctx.close()

        await asyncio.gather(
            _check_ui("/", "#dev-card-bedroom_light", "bedroom_light", "OFF", "applySnapshot", True),
            _check_ui("/app", "#mobileQuickBtnFan", "fan", "OFF", "renderState", True),
            _check_ui("/wokwi", "#btn_garden_pump", "garden_pump", "OFF", "syncWokwiComponents", True),
        )
        await browser.close()
