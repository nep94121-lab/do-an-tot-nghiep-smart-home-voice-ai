"""Regression tests for device toggle oscillation fix (togglefix-20261110).

Covers:
1. Single listener binding (no duplicate listeners across re-renders, no click+change double fire).
2. Per-device request sequencing (ignore stale responses via version/sequence numbers or timestamps).
3. Server as source of truth with idempotent set-state API (target_state/state).
4. Debounce rapid double/triple clicks.
5. Stale poll (GET /api/state) and push (applySnapshot) updates do not overwrite a newer pending local intent.
6. 10-second continuous observation confirming zero oscillation and final state matching last user intent.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
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

from simulator.engine.state_store import VercelBlobStateBackend
from simulator.server import app


def _create_admin_session_cookies(client: TestClient) -> dict[str, str]:
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
    base_ts = int(time.time() * 1000) + 5000

    # Set living_room_light explicitly to OFF
    r0 = client.post(
        "/api/device",
        json={
            "device_id": "living_room_light",
            "action": "turn_off",
            "target_state": "OFF",
            "client_seq": 10,
            "client_ts_ms": base_ts,
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

    # Set living_room_light to ON via idempotent target_state even if action says toggle
    r1 = client.post(
        "/api/device",
        json={
            "device_id": "living_room_light",
            "action": "toggle",
            "target_state": "ON",
            "client_seq": 11,
            "client_ts_ms": base_ts + 100,
        },
        headers=headers,
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["ok"] is True
    assert d1["state"] == "ON"
    assert d1["device_version"] == v0 + 1

    # Repeat idempotent target_state="ON" -> stays ON, does not toggle back to OFF
    r2 = client.post(
        "/api/devices/living_room_light/control",
        json={
            "action": "toggle",
            "target_state": "ON",
            "client_seq": 12,
            "client_ts_ms": base_ts + 200,
        },
        headers=headers,
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["ok"] is True
    assert d2["state"] == "ON"
    assert d2["device_version"] == d1["device_version"]

    # Also verify /api/device/{device_id} route alias
    r3 = client.post(
        "/api/device/living_room_light",
        json={
            "target_state": "OFF",
            "client_seq": 13,
            "client_ts_ms": base_ts + 300,
        },
        headers=headers,
    )
    assert r3.status_code == 200
    assert r3.json()["state"] == "OFF"


def test_out_of_order_stale_sequence_and_timestamp_ignored_by_server() -> None:
    client = TestClient(app)
    headers = _create_admin_session_cookies(client)
    base_ts = int(time.time() * 1000) + 15000

    # Newer request (client_seq=50, target_state="OFF") arrives first
    r_new = client.post(
        "/api/device",
        json={
            "device_id": "fan",
            "action": "turn_off",
            "target_state": "OFF",
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

    # Older request (client_seq=49, target_state="ON") arrives late out-of-order
    r_old = client.post(
        "/api/device",
        json={
            "device_id": "fan",
            "action": "turn_on",
            "target_state": "ON",
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

    # Older timestamp without sequence number also ignored
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

    # Verify /api/state confirms fan is still OFF
    snap = client.get("/api/state", headers=headers).json()
    fan_dev = next(d for d in snap["devices"] if d["id"] == "fan")
    assert fan_dev["state"] == "OFF"
    assert fan_dev["last_client_seq"] == 50


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
        assert call_count == 1  # Fails immediately on 403 without 3x retry

        t0 = time.perf_counter()
        res2 = backend.load_state()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert isinstance(res2, dict)
        assert call_count == 1  # Circuit breaker skips network call completely
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
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["SIMULATOR_OFFLINE_SANDBOX"] = "1"
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

        auth_init_script = f"""
            window._FORCE_HTTP_POLLING = true;
            window._disableWebSocket = true;
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
        yield {"base_url": base_url, "auth_init_script": auth_init_script}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def test_e2e_duplicate_listener_check_and_single_binding(live_server_info: dict[str, str]) -> None:
    asyncio.run(_run_e2e_duplicate_listener_check(live_server_info))


async def _run_e2e_duplicate_listener_check(info: dict[str, str]) -> None:
    from playwright.async_api import async_playwright

    base_url = info["base_url"]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.add_init_script(info["auth_init_script"])
        await page.goto(f"{base_url}/", wait_until="networkidle")
        await page.wait_for_selector("#dev-card-living_room_light", timeout=10000)

        listener_check = await page.evaluate(
            """() => {
                const snap = {
                    server_connected: true,
                    devices: [
                        { id: 'living_room_light', name: 'Đèn phòng khách', type: 'light', state: 'ON', version: 999, last_client_seq: 0 },
                        { id: 'fan', name: 'Quạt phòng khách', type: 'fan', state: 'OFF', version: 999, last_client_seq: 0 }
                    ]
                };
                for (let i = 0; i < 10; i++) {
                    window.applySnapshot(snap);
                }
                const card = document.getElementById('dev-card-living_room_light');
                return {
                    boundAttr: card.dataset.toggleListenerBound,
                    listenerCount: card._toggleListenerCount || 0,
                    initialState: card.getAttribute('data-state')
                };
            }"""
        )
        assert listener_check["boundAttr"] == "1"
        assert listener_check["listenerCount"] == 1
        assert listener_check["initialState"] == "on"

        seq_before = await page.evaluate("window.__deviceControlState['living_room_light'].seq")
        await page.locator("#dev-card-living_room_light .switch").click()
        await asyncio.sleep(0.25)
        after_switch_click = await page.evaluate(
            """() => ({
                domState: document.getElementById('dev-card-living_room_light').getAttribute('data-state'),
                checked: document.querySelector('#dev-card-living_room_light .switch input').checked,
                seq: window.__deviceControlState['living_room_light'].seq
            })"""
        )
        assert after_switch_click["domState"] == "off"
        assert after_switch_click["checked"] is False
        assert after_switch_click["seq"] == seq_before + 1

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
        await page.goto(f"{base_url}/", wait_until="networkidle")
        await page.wait_for_selector("#dev-card-living_room_light", timeout=10000)

        await page.evaluate(
            """async () => {
                await fetch('/api/device', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ device_id: 'living_room_light', target_state: 'OFF', client_seq: 100, client_ts_ms: Date.now() })
                });
                const r = await fetch('/api/state');
                const s = await r.json();
                window.applySnapshot(s);
            }"""
        )
        assert await page.get_attribute("#dev-card-living_room_light", "data-state") == "off"

        delay_enabled = True
        await page.evaluate(
            """() => {
                window._testPollInterval = setInterval(() => {
                    fetch('/api/state').then(r => r.json()).then(s => window.applySnapshot(s)).catch(() => {});
                }, 250);
            }"""
        )
        await asyncio.sleep(0.08)

        # User clicks living_room_light once (intent: ON)
        await page.click("#dev-card-living_room_light")

        # Inject a synthetic stale snapshot 150ms later
        await asyncio.sleep(0.15)
        await page.evaluate(
            """() => {
                window.applySnapshot({
                    server_connected: true,
                    revision_seq: 1,
                    devices: [
                        { id: 'living_room_light', name: 'Đèn phòng khách', type: 'light', state: 'OFF', version: 1, last_client_seq: 1 }
                    ]
                });
            }"""
        )

        # Sample DOM state every 100ms for 10.0 seconds (100 samples)
        samples_10s: list[str] = []
        for _ in range(100):
            st = await page.get_attribute("#dev-card-living_room_light", "data-state")
            samples_10s.append(str(st))
            await asyncio.sleep(0.1)

        await page.evaluate("clearInterval(window._testPollInterval);")
        delay_enabled = False

        assert all(s == "on" for s in samples_10s), f"Oscillation detected in 10s samples: {samples_10s}"

        srv_state = await page.evaluate(
            """async () => {
                const r = await fetch('/api/state');
                const s = await r.json();
                return s.devices.find(d => d.id === 'living_room_light').state;
            }"""
        )
        assert srv_state == "ON"

        await page.unroute_all(behavior="ignoreErrors")
        await ctx.close()
        await browser.close()


def test_e2e_rapid_double_and_triple_clicks_with_slow_out_of_order_backend(
    live_server_info: dict[str, str],
) -> None:
    asyncio.run(_run_e2e_rapid_clicks(live_server_info))


async def _run_e2e_rapid_clicks(info: dict[str, str]) -> None:
    from playwright.async_api import async_playwright

    base_url = info["base_url"]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.add_init_script(info["auth_init_script"])

        post_num = 0

        async def handle_route(route: Any, request: Any) -> None:
            nonlocal post_num
            try:
                if "/api/device" in request.url and request.method == "POST":
                    post_num += 1
                    cur_n = post_num
                    if cur_n == 1:
                        await asyncio.sleep(0.7)
                    else:
                        await asyncio.sleep(0.1)
                    resp = await route.fetch()
                    await route.fulfill(response=resp)
                    return
                await route.continue_()
            except Exception:
                pass

        await page.route("**/*", handle_route)
        await page.goto(f"{base_url}/app", wait_until="networkidle")
        await page.wait_for_selector("#mobileQuickBtnFan", timeout=10000)

        # Ensure fan starts OFF
        await page.evaluate(
            """async () => {
                await fetch('/api/device', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ device_id: 'fan', target_state: 'OFF', client_seq: 200, client_ts_ms: Date.now() })
                });
                const r = await fetch('/api/state');
                const s = await r.json();
                window.renderState(s);
            }"""
        )
        assert await page.get_attribute("#mobileQuickBtnFan", "data-state") == "off"
        post_num = 0

        # Rapid double click spaced 100ms apart (Request 1 slow 700ms, Request 2 fast 100ms)
        await page.click("#mobileQuickBtnFan")
        await asyncio.sleep(0.1)
        await page.click("#mobileQuickBtnFan")

        double_click_samples: list[str] = []
        for _ in range(15):
            st = await page.get_attribute("#mobileQuickBtnFan", "data-state")
            double_click_samples.append(str(st))
            await asyncio.sleep(0.1)

        assert all(s == "off" for s in double_click_samples), (
            f"Out-of-order response caused oscillation after double click: {double_click_samples}"
        )

        # Rapid triple click within debounce window (OFF -> ON -> OFF -> ON)
        await page.click("#mobileQuickBtnFan")
        await page.click("#mobileQuickBtnFan")
        await page.click("#mobileQuickBtnFan")
        await asyncio.sleep(0.4)

        final_btn_state = await page.get_attribute("#mobileQuickBtnFan", "data-state")
        final_srv_fan = await page.evaluate(
            """async () => {
                const r = await fetch('/api/state');
                const s = await r.json();
                return s.devices.find(d => d.id === 'fan').state;
            }"""
        )
        assert final_btn_state == "on"
        assert final_srv_fan == "ON"

        await page.unroute_all(behavior="ignoreErrors")
        await ctx.close()
        await browser.close()
