"""Kiểm thử tự động giao diện qua Chromium Headless (Chrome DevTools Equivalent).

Nhiệm vụ kiểm thử:
1. Mở tuần tự các trang trên máy chủ kiểm thử cô lập (hoặc SMARTHOME_LIVE_BASE_URL):
   - /
   - /auth
   - /guest_guide
   - /wokwi
   - /logs
   - /app
2. Xác nhận 0 console errors, 0 page errors, 0 HTTP 404/500 và OrbitControls.js không 404.
3. Xác nhận /guest và /guest_enroll không có token trả HTTP 403 (không trả 404/500).
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import socket
import sys
import threading
import time

import pytest
from playwright.async_api import async_playwright
import uvicorn

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.auth.invite_and_gmail_mixin import AuthInviteGmailMixin
from backend.server import _ACTIVE_BRIDGES, app

PAGES_TO_TEST = [
    ("/", "Trang chủ 3D"),
    ("/auth", "Trang Xác thực 3 Lớp"),
    ("/guest_guide", "Trang Hướng dẫn Khách QR"),
    ("/wokwi", "Trang Phần cứng Wokwi"),
    ("/logs", "Trang Nhật ký & CSDL"),
    ("/app", "Giao diện Di động"),
]


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def live_base_url():
    ext = os.environ.get("SMARTHOME_LIVE_BASE_URL", "").strip()
    if ext:
        yield ext.rstrip("/")
        return

    import urllib.request

    prev_pytest = os.environ.get("PYTEST")
    prev_gmail = os.environ.get("GMAIL_APP_PASSWORD")
    prev_smtp = os.environ.get("SMTP_PASSWORD")
    orig_send = AuthInviteGmailMixin.send_real_gmail_otp
    os.environ["PYTEST"] = "1"
    os.environ["GMAIL_APP_PASSWORD"] = ""
    os.environ["SMTP_PASSWORD"] = ""
    AuthInviteGmailMixin.send_real_gmail_otp = lambda self, *a, **kw: {
        "sent_real_gmail": False,
        "blocked_by_allowlist": False,
        "status": "MOCKED_TEST",
    }

    port = _get_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=0.5) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.1)

    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=3)
        for br in list(_ACTIVE_BRIDGES):
            try:
                br._closed = True
            except Exception:
                pass
        _ACTIVE_BRIDGES.clear()
        AuthInviteGmailMixin.send_real_gmail_otp = orig_send
        for k, v in (("PYTEST", prev_pytest), ("GMAIL_APP_PASSWORD", prev_gmail), ("SMTP_PASSWORD", prev_smtp)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


async def _launch_async_browser(p):
    args = ["--disable-dev-shm-usage", "--no-sandbox"]
    for ch in ("chrome", "msedge"):
        try:
            return await p.chromium.launch(channel=ch, headless=True, args=args)
        except Exception:
            continue
    return await p.chromium.launch(headless=True, args=args)


@pytest.mark.parametrize("path,label", PAGES_TO_TEST)
def test_page_zero_console_errors_and_zero_http_failures(live_base_url: str, path: str, label: str):
    """Kiểm tra từng trang: 0 uncaught console errors, 0 network 404/500 errors."""
    async def _test():
        async with async_playwright() as p:
            browser = await _launch_async_browser(p)
            context = await browser.new_context()
            page = await context.new_page()

            await page.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
            await page.route("https://fonts.gstatic.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))

            console_errors = []
            page_errors = []
            http_failures = []

            page.on(
                "console",
                lambda msg: console_errors.append(f"[{msg.type}] {msg.text}")
                if (msg.type == "error" and "status of 401" not in msg.text and "WebSocket" not in msg.text)
                else None,
            )
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            def handle_response(res):
                if res.status in (404, 500):
                    http_failures.append((res.status, res.url))

            page.on("response", handle_response)

            url = f"{live_base_url}{path}"
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)

            orbit_404s = [f for f in http_failures if "OrbitControls.js" in f[1]]
            assert not orbit_404s, f"Lỗi 404 OrbitControls.js vẫn xuất hiện trên {path}: {orbit_404s}"

            critical_http_failures = [
                f for f in http_failures if not f[1].endswith("/favicon.ico")
            ]

            await browser.close()

            assert not page_errors, f"Trang {path} ({label}) có lỗi pageerror chưa bắt: {page_errors}"
            assert not console_errors, f"Trang {path} ({label}) có console errors: {console_errors}"
            assert not critical_http_failures, f"Trang {path} ({label}) có request lỗi 404/500: {critical_http_failures}"

    asyncio.run(_test())


def test_guest_routes_without_token_return_403(live_base_url: str):
    """Route /guest và /guest-qr không có token phải trả 403; route cũ /guest_enroll trả 410."""
    async def _test():
        async with async_playwright() as p:
            browser = await _launch_async_browser(p)
            context = await browser.new_context()
            page = await context.new_page()
            for guest_path in ("/guest", "/guest-qr"):
                res = await page.goto(f"{live_base_url}{guest_path}", wait_until="domcontentloaded", timeout=15000)
                assert res is not None and res.status == 403, f"Expected 403 on {guest_path}, got {getattr(res, 'status', None)}"
            res_enroll = await page.goto(f"{live_base_url}/guest_enroll", wait_until="domcontentloaded", timeout=15000)
            assert res_enroll is not None and res_enroll.status == 410, f"Expected 410 on /guest_enroll, got {getattr(res_enroll, 'status', None)}"
            await browser.close()

    asyncio.run(_test())
