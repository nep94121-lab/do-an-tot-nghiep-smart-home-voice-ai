# -*- coding: utf-8 -*-
"""Mobile viewport auth-gate: unauthenticated home must not expose device/PIN/QR controls."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]

OWNER_SEED = "sess_owner_t1_nep94121"
OWNER_EMAIL = "nep94121@gmail.com"


def _app_client() -> TestClient:
    os.environ["SIMULATOR_OFFLINE_SANDBOX"] = "1"
    os.environ.pop("VERCEL", None)
    os.environ.pop("SMARTHOME_FORCE_CLOUD_DURABLE", None)
    from simulator.server import app

    return TestClient(app)


def test_unauthenticated_device_toggle_rejected_by_server() -> None:
    client = _app_client()
    resp = client.post(
        "/api/device",
        json={
            "device_id": "living_room_light",
            "target_state": "ON",
            "client_id": "authgate_anon",
            "client_seq": 1,
            "client_ts_ms": int(time.time() * 1000),
        },
    )
    assert resp.status_code in (401, 403), resp.text
    data = resp.json()
    assert data.get("ok") is False


def test_owner_session_can_create_guest_qr() -> None:
    client = _app_client()
    resp = client.post(
        "/api/auth3/guest_invites",
        json={"tier": 3, "ttl_sec": 600},
        headers={"X-Session-Token": OWNER_SEED},
        cookies={"sh_session_token": OWNER_SEED, "session_token": OWNER_SEED},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("ok") is True
    svg = str(data.get("qr_svg") or "")
    assert "<svg" in svg
    assert data.get("invite_id")


def test_unauthenticated_guest_qr_is_rejected() -> None:
    client = _app_client()
    resp = client.post("/api/auth3/guest_invites", json={"tier": 3, "ttl_sec": 600})
    assert resp.status_code in (401, 403), resp.text
    data = resp.json()
    assert data.get("ok") is False


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(base_url: str, timeout_s: float = 20.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/version", timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"server did not start: {base_url}")


@pytest.fixture()
def live_server() -> Generator[str, None, None]:
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
            yield base_url
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()


def _owner_init_script() -> str:
    token = json.dumps(OWNER_SEED)
    email = json.dumps(OWNER_EMAIL)
    return f"""
        sessionStorage.setItem('session_token', {token});
        localStorage.setItem('session_token', {token});
        localStorage.setItem('smarthome_auth_session', JSON.stringify({{
            email: {email},
            display_name: 'Nguyen Tuan Anh',
            tier: 1,
            role: 'ADMIN',
            session_token: {token}
        }}));
        document.cookie = 'sh_session_token=' + {token} + '; path=/';
        document.cookie = 'session_token=' + {token} + '; path=/';
    """


def test_e2e_mobile_unauthenticated_home_shows_login_and_blocks_controls(live_server: str) -> None:
    import asyncio
    from playwright.async_api import async_playwright

    async def _run() -> None:
        posts: list[str] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, channel="chrome")
            ctx = await browser.new_context(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                has_touch=True,
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
                ),
            )
            page = await ctx.new_page()

            async def on_route(route: Any, request: Any) -> None:
                if not request.url.startswith(live_server):
                    await route.abort()
                    return
                if "/api/device" in request.url and request.method == "POST":
                    posts.append(request.url)
                if "/api/auth3/guest_invites" in request.url and request.method == "POST" and "/revoke" not in request.url:
                    posts.append("guest_invites")
                await route.continue_()

            await page.route("**/*", on_route)
            await page.goto(f"{live_server}/", wait_until="domcontentloaded")
            await page.wait_for_selector("#homeLoginGateModal", timeout=15000)
            await page.wait_for_function(
                """() => {
                    const modal = document.getElementById('homeLoginGateModal');
                    const sec = document.getElementById('secDevices');
                    return !!(modal && !modal.classList.contains('hidden')
                        && sec && sec.classList.contains('devices-logged-out')
                        && document.body.classList.contains('dashboard-logged-out'));
                }""",
                timeout=15000,
            )
            meta = await page.locator("#ownerGuestQrMeta").text_content()
            assert meta is not None and "Hãy đăng nhập" in meta
            card = page.locator("#dev-card-living_room_light")
            if await card.count():
                try:
                    await card.click(timeout=2000, force=True)
                except Exception:
                    pass
            pins = page.locator(".pin-3d")
            if await pins.count():
                try:
                    await pins.first.click(timeout=2000, force=True)
                except Exception:
                    pass
            gen = page.locator("#ownerGuestQrGenerateBtn")
            if await gen.count():
                try:
                    await gen.click(timeout=2000, force=True)
                except Exception:
                    pass
            await page.wait_for_timeout(800)
            meta_after = await page.locator("#ownerGuestQrMeta").text_content()
            assert meta_after is not None and "Hãy đăng nhập" in meta_after
            assert "Không tạo được mã QR khách." not in (meta_after or "")
            assert posts == []
            visible_gate = await page.locator("#homeLoginGateModal").is_visible()
            assert visible_gate is True
            await browser.close()

    asyncio.run(_run())


def test_e2e_mobile_stale_localstorage_still_shows_login(live_server: str) -> None:
    import asyncio
    from playwright.async_api import async_playwright

    async def _run() -> None:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, channel="chrome")
            ctx = await browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            page = await ctx.new_page()
            await page.add_init_script(
                """
                localStorage.setItem('smarthome_auth_session', JSON.stringify({
                    email: 'stale-user@example.com',
                    display_name: 'Stale User',
                    tier: 1
                }));
                """
            )
            await page.goto(f"{live_server}/", wait_until="domcontentloaded")
            await page.wait_for_function(
                """() => {
                    const modal = document.getElementById('homeLoginGateModal');
                    const sec = document.getElementById('secDevices');
                    return !!(modal && !modal.classList.contains('hidden')
                        && sec && sec.classList.contains('devices-logged-out'));
                }""",
                timeout=15000,
            )
            meta = await page.locator("#ownerGuestQrMeta").text_content()
            assert meta is not None and "Hãy đăng nhập" in meta
            assert "Không tạo được mã QR khách." not in (meta or "")
            await browser.close()

    asyncio.run(_run())


def test_e2e_mobile_owner_can_generate_guest_qr(live_server: str) -> None:
    import asyncio
    from playwright.async_api import async_playwright

    async def _run() -> None:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, channel="chrome")
            ctx = await browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            await ctx.add_cookies(
                [
                    {"name": "sh_session_token", "value": OWNER_SEED, "url": live_server},
                    {"name": "session_token", "value": OWNER_SEED, "url": live_server},
                ]
            )
            page = await ctx.new_page()
            await page.add_init_script(_owner_init_script())
            await page.goto(f"{live_server}/", wait_until="domcontentloaded")
            await page.wait_for_function(
                """() => {
                    const sec = document.getElementById('secDevices');
                    const modal = document.getElementById('homeLoginGateModal');
                    return !!(sec && !sec.classList.contains('devices-logged-out')
                        && modal && modal.classList.contains('hidden'));
                }""",
                timeout=15000,
            )
            await page.locator("#ownerGuestQrGenerateBtn").click()
            await page.wait_for_function(
                """() => {
                    const box = document.getElementById('ownerGuestQrSvg');
                    return !!(box && box.querySelector('svg'));
                }""",
                timeout=15000,
            )
            meta = await page.locator("#ownerGuestQrMeta").text_content()
            assert meta is not None
            assert "Hãy đăng nhập" not in meta
            assert "Không tạo được mã QR khách." not in meta
            await browser.close()

    asyncio.run(_run())
