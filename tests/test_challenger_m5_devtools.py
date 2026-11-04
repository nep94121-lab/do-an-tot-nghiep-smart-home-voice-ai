"""Kiểm thử tự động giao diện 6 trang qua Chromium Headless (Chrome DevTools Equivalent).

Người thực hiện: teamwork_challenger (Instance 1)
Nhiệm vụ kiểm thử:
1. Mở tuần tự 6 trang trên máy chủ local (http://127.0.0.1:8088):
   - /
   - /auth
   - /guest_enroll
   - /wokwi
   - /logs
   - /app
2. Lắng nghe và ghi lại:
   - Tất cả console errors & page errors (bắt buộc 0 uncaught errors)
   - Tất cả network responses có status HTTP 404 hoặc 500 (bắt buộc 0 network 404/500)
   - Kiểm tra đặc thù: OrbitControls.js tuyệt đối không còn bị lỗi 404
"""

import asyncio
import pathlib
import sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.async_api import async_playwright

PAGES_TO_TEST = [
    ("/", "Trang chủ 3D"),
    ("/auth", "Trang Xác thực 3 Lớp"),
    ("/guest_enroll", "Trang Thu âm Khách QR"),
    ("/wokwi", "Trang Phần cứng Wokwi"),
    ("/logs", "Trang Nhật ký & CSDL"),
    ("/app", "Giao diện Di động"),
]


@pytest.mark.parametrize("path,label", PAGES_TO_TEST)
def test_page_zero_console_errors_and_zero_http_failures(path, label):
    """Kiểm tra từng trang: 0 uncaught console errors, 0 network 404/500 errors."""
    async def _test():
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            console_errors = []
            page_errors = []
            http_failures = []
            requested_urls = []

            page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
            page.on("pageerror", lambda err: page_errors.append(str(err)))
            
            def handle_response(res):
                requested_urls.append(res.url)
                if res.status in (404, 500):
                    http_failures.append((res.status, res.url))

            page.on("response", handle_response)

            url = f"http://127.0.0.1:8088{path}"
            # Navigate to page and wait until DOMContentLoaded and networkidle
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)  # Wait 1s for background scripts & WebSocket

            # Check specific condition: OrbitControls.js must not be 404
            orbit_404s = [f for f in http_failures if "OrbitControls.js" in f[1]]
            assert not orbit_404s, f"Lỗi 404 OrbitControls.js vẫn xuất hiện trên {path}: {orbit_404s}"

            # Filter out expected benign noise if any, e.g. favicon.ico if browser auto-requests
            critical_http_failures = [
                f for f in http_failures if not f[1].endswith("/favicon.ico")
            ]

            await browser.close()

            assert not page_errors, f"Trang {path} ({label}) có lỗi pageerror chưa bắt: {page_errors}"
            assert not console_errors, f"Trang {path} ({label}) có console errors: {console_errors}"
            assert not critical_http_failures, f"Trang {path} ({label}) có request lỗi 404/500: {critical_http_failures}"

    asyncio.run(_test())
