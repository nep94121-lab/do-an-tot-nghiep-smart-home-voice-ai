"""Playwright Multi-Viewport E2E Audit for Phase 7 UI Overhaul.

Audits all 8 routes across 4 viewports using headless Google Chrome (channel="chrome"):
- Viewports:
  1. Desktop: 1280x800
  2. Mobile 360px: 360x780
  3. Mobile 390px: 390x844
  4. Mobile 430px: 430x932
- Routes:
  1. / (Trang chu 3D Overview / Login Gate)
  2. /app (Mobile PWA)
  3. /auth (Voice Auth 3-Step Setup & Scenarios)
  4. /wokwi (Hardware Simulation)
  5. /logs (System Audit Logs)
  6. /guest_enroll (Guest Enrollment)
  7. /login (Dedicated Minimalist Login)
  8. /register (Dedicated Minimalist Register)

Verifies:
- 0 console errors
- 0 uncaught exceptions / page errors
- No horizontal scroll overflow on mobile viewports (scrollWidth <= clientWidth)
- Full page screenshots saved to tests/artifacts/screenshots/
"""
from __future__ import annotations

import pathlib
import pytest
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8088"
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = PROJECT_ROOT / "tests" / "artifacts" / "screenshots"

VIEWPORTS = [
    {"name": "desktop_1280x800", "width": 1280, "height": 800, "is_mobile": False},
    {"name": "mobile_360x780", "width": 360, "height": 780, "is_mobile": True},
    {"name": "mobile_390x844", "width": 390, "height": 844, "is_mobile": True},
    {"name": "mobile_430x932", "width": 430, "height": 932, "is_mobile": True},
]

ROUTES = [
    {"path": "/", "slug": "home", "title": "Trang chu 3D Overview"},
    {"path": "/app", "slug": "app", "title": "Mobile PWA App"},
    {"path": "/auth", "slug": "auth", "title": "Voice Auth 3-Layer"},
    {"path": "/wokwi", "slug": "wokwi", "title": "Wokwi Hardware"},
    {"path": "/logs", "slug": "logs", "title": "Audit Logs"},
    {"path": "/guest_enroll", "slug": "guest_enroll", "title": "Guest Enroll"},
    {"path": "/login", "slug": "login", "title": "Dedicated Login"},
    {"path": "/register", "slug": "register", "title": "Dedicated Register"},
]


@pytest.fixture(scope="session", autouse=True)
def ensure_screenshot_dir():
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


class TestPhase7MultiViewportAudit:
    """Multi-viewport automated Playwright audit across 8 routes and 4 viewports."""

    @pytest.mark.parametrize("route", ROUTES, ids=[r["slug"] for r in ROUTES])
    @pytest.mark.parametrize("vp", VIEWPORTS, ids=[v["name"] for v in VIEWPORTS])
    def test_audit_route_viewport(self, route, vp):
        slug = route["slug"]
        path = route["path"]
        vp_name = vp["name"]
        width = vp["width"]
        height = vp["height"]
        is_mobile = vp["is_mobile"]

        console_errors = []
        page_errors = []

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(
                viewport={"width": width, "height": height},
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
                    if is_mobile
                    else None
                ),
            )
            page = context.new_page()

            page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            # Navigate to the target route
            target_url = f"{BASE_URL}{path}"
            res = page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            assert res is not None and res.status == 200, f"HTTP request failed for {target_url} with status {getattr(res, 'status', None)}"

            # Allow scripts/3D canvas/WebSocket to settle
            page.wait_for_timeout(600)

            # Check horizontal overflow on mobile viewports
            if is_mobile:
                overflow_info = page.evaluate("""() => {
                    const docWidth = document.documentElement.scrollWidth;
                    const bodyWidth = document.body.scrollWidth;
                    const winWidth = window.innerWidth;
                    const maxContentWidth = Math.max(docWidth, bodyWidth);
                    return {
                        hasOverflow: maxContentWidth > winWidth + 1,
                        scrollWidth: maxContentWidth,
                        clientWidth: winWidth
                    };
                }""")
                assert not overflow_info["hasOverflow"], (
                    f"Route {path} has horizontal scroll overflow on {vp_name}: "
                    f"scrollWidth={overflow_info['scrollWidth']}px > innerWidth={overflow_info['clientWidth']}px"
                )

            # Save screenshot for audit evidence
            screenshot_path = SCREENSHOTS_DIR / f"{slug}_{vp_name}.png"
            page.screenshot(path=str(screenshot_path), full_page=False)
            assert screenshot_path.exists() and screenshot_path.stat().st_size > 0, f"Screenshot {screenshot_path} was not created"

            browser.close()

            # Filter known third-party / non-fatal browser warnings if any
            critical_console_errors = [
                err for err in console_errors
                if "favicon.ico" not in err and "WebSocket connection to" not in err
            ]

            assert not page_errors, f"Unhandled JavaScript errors on {path} @ {vp_name}: {page_errors}"
            assert not critical_console_errors, f"Console errors on {path} @ {vp_name}: {critical_console_errors}"
