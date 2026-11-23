"""Playwright Multi-Viewport E2E Audit for Phase 7 UI Overhaul.

Audits 8 active 200-OK routes across 4 viewports plus `/guest` token-gate on mobile 390x844:
- Desktop: 1280x800
- Mobile: 360x780, 390x844, 430x932
Routes: /, /app, /auth, /wokwi, /logs, /guest_guide, /login, /register
Saves audit screenshots to pytest tmp_path_factory so workspace stays clean.
"""
from __future__ import annotations

import os
import pathlib
import socket
import sys
import threading
import time

import pytest
from playwright.sync_api import sync_playwright
import uvicorn

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.auth.invite_and_gmail_mixin import AuthInviteGmailMixin
from backend.server import _ACTIVE_BRIDGES, app

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
    {"path": "/guest_guide", "slug": "guest_guide", "title": "Guest Guide"},
    {"path": "/login", "slug": "login", "title": "Dedicated Login"},
    {"path": "/register", "slug": "register", "title": "Dedicated Register"},
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


@pytest.fixture(scope="module")
def ui_audit_screenshots_dir(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    return tmp_path_factory.mktemp("ui_audit_shots")


def _launch_browser(p):
    args = ["--disable-dev-shm-usage", "--no-sandbox"]
    for ch in ("chrome", "msedge"):
        try:
            return p.chromium.launch(channel=ch, headless=True, args=args)
        except Exception:
            continue
    return p.chromium.launch(headless=True, args=args)


@pytest.fixture(scope="module")
def shared_browser():
    with sync_playwright() as p:
        browser = _launch_browser(p)
        try:
            yield browser
        finally:
            browser.close()


def _fulfill_fonts(page):
    try:
        page.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
        page.route("https://fonts.gstatic.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
    except Exception:
        pass


class TestPhase7MultiViewportAudit:
    """Multi-viewport automated Playwright audit across 8 routes and 4 viewports."""

    @pytest.mark.parametrize("route", ROUTES, ids=[r["slug"] for r in ROUTES])
    @pytest.mark.parametrize("vp", VIEWPORTS, ids=[v["name"] for v in VIEWPORTS])
    def test_audit_route_viewport(
        self,
        live_base_url: str,
        shared_browser,
        ui_audit_screenshots_dir: pathlib.Path,
        route: dict,
        vp: dict,
    ):
        slug = route["slug"]
        path = route["path"]
        vp_name = vp["name"]
        width = vp["width"]
        height = vp["height"]
        is_mobile = vp["is_mobile"]

        console_errors = []
        page_errors = []

        context = shared_browser.new_context(
            viewport={"width": width, "height": height},
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
                if is_mobile
                else None
            ),
        )
        try:
            page = context.new_page()
            _fulfill_fonts(page)

            page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            target_url = f"{live_base_url}{path}"
            res = page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            assert res is not None and res.status == 200, f"HTTP request failed for {target_url} with status {getattr(res, 'status', None)}"

            page.wait_for_timeout(450)

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

            screenshot_path = ui_audit_screenshots_dir / f"{slug}_{vp_name}.png"
            page.screenshot(path=str(screenshot_path), full_page=False)
            assert screenshot_path.exists() and screenshot_path.stat().st_size > 0
        finally:
            context.close()

        critical_console_errors = [
            err for err in console_errors
            if "favicon.ico" not in err and "WebSocket" not in err and "status of 401" not in err
        ]

        assert not page_errors, f"Unhandled JavaScript errors on {path} @ {vp_name}: {page_errors}"
        assert not critical_console_errors, f"Console errors on {path} @ {vp_name}: {critical_console_errors}"

    def test_guest_token_gate_and_mobile_viewport(self, live_base_url: str, shared_browser, ui_audit_screenshots_dir: pathlib.Path):
        """/guest không có token trả 403; /guest?token=<hợp lệ> trả 200 và không tràn ngang trên 390x844."""
        import json as _json
        import urllib.request

        req = urllib.request.Request(
            f"{live_base_url}/api/guest/invites",
            data=_json.dumps({"pin": "1357", "pin_confirm": "1357", "duration_code": "1d", "guest_name": "Audit Guest"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Session-Token": "sess_owner_t1_nep94121"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            inv = _json.loads(resp.read().decode("utf-8"))
        token = inv["url"].split("token=", 1)[1].split("&", 1)[0]

        console_errors = []
        page_errors = []
        ctx = shared_browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        try:
            page = ctx.new_page()
            _fulfill_fonts(page)
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            no_tok = page.goto(f"{live_base_url}/guest", wait_until="domcontentloaded", timeout=15000)
            assert no_tok is not None and no_tok.status == 403

            console_errors.clear()
            page_errors.clear()
            res_ok = page.goto(f"{live_base_url}/guest?token={token}", wait_until="domcontentloaded", timeout=15000)
            assert res_ok is not None and res_ok.status == 200
            page.wait_for_selector("#guestApp:not([hidden])", timeout=15000)

            overflow_x = page.evaluate(
                "() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) > window.innerWidth + 1"
            )
            assert overflow_x is False, "Trang /guest?token=... tràn ngang trên 390x844!"

            shot = ui_audit_screenshots_dir / "guest_valid_390x844.png"
            page.screenshot(path=str(shot), full_page=False)
            assert shot.exists() and shot.stat().st_size > 0
        finally:
            ctx.close()

        critical_console = [e for e in console_errors if "favicon.ico" not in e and "WebSocket" not in e and "status of 401" not in e]
        assert not page_errors, page_errors
        assert not critical_console, critical_console
