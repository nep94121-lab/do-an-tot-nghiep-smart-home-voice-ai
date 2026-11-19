"""Regression tests for agyfix7_20261119:
Hide bottom navigation & panel shortcuts before authentication on mobile/desktop,
enforce server-side 401/403 on all panel APIs, restore role-scoped nav after login,
and hide nav immediately on logout.
"""

from __future__ import annotations

import os
import pathlib
import re
import socket
import threading
import time
import urllib.request
from typing import Any

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "simulator" / "static"
MOBILE_HTML = ROOT / "mobile_app" / "index.html"


def _find_chromium_executable() -> str | None:
    env_exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "").strip()
    if env_exe and pathlib.Path(env_exe).exists():
        return env_exe
    home = pathlib.Path.home()
    roots = [home, home.parent, pathlib.Path(r"C:\Users\LENOVO")]
    rel_paths = [
        pathlib.Path(".cache") / "puppeteer" / "chrome-headless-shell" / "win64-154.0.8037.57" / "chrome-headless-shell-win64" / "chrome-headless-shell.exe",
        pathlib.Path(".cache") / "puppeteer" / "chrome-headless-shell" / "win64-153.0.8010.36" / "chrome-headless-shell-win64" / "chrome-headless-shell.exe",
    ]
    for root in roots:
        for rel in rel_paths:
            cand = root / rel
            if cand.exists():
                return str(cand)
    return None


def _launch_browser(p: Any) -> Any:
    exe = _find_chromium_executable()
    attempts: list[dict[str, Any]] = []
    if exe:
        attempts.append({"headless": True, "executable_path": exe})
    attempts.extend(
        [
            {"headless": True},
            {"headless": True, "channel": "msedge"},
            {"headless": True, "channel": "chrome"},
        ]
    )
    last_err: Exception | None = None
    for kw in attempts:
        try:
            return p.chromium.launch(timeout=20000, **kw)
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"Could not launch Chromium for Playwright test: {last_err}")


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class TestStaticHtmlCssDefaultHidden:
    """Before JS runs, protected bottom nav and panel links must default to hidden (no flash)."""

    def test_index_html_mobile_nav_default_hidden_and_owner_logs_marked(self) -> None:
        raw = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        assert "\r\n" not in raw
        soup = BeautifulSoup(raw, "html.parser")
        shell = soup.find(id="homeAppShell")
        assert shell is not None and shell.has_attr("hidden")
        nav = soup.find("nav", id="homeMobileNav")
        assert nav is not None, "index.html must define #homeMobileNav"
        assert nav.has_attr("hidden"), "#homeMobileNav must default to hidden in static HTML"
        assert nav.get("aria-hidden") == "true"
        logs_link = nav.find("a", href="/logs")
        assert logs_link is not None and logs_link.get("data-owner-only") == "true"

    def test_mobile_app_html_bottom_nav_and_main_default_hidden(self) -> None:
        raw = MOBILE_HTML.read_text(encoding="utf-8")
        assert "\r\n" not in raw
        soup = BeautifulSoup(raw, "html.parser")
        nav = soup.find("nav", id="mobileBottomNav")
        main = soup.find(id="mobileMainContent")
        assert nav is not None and nav.has_attr("hidden")
        assert main is not None and main.has_attr("hidden")
        logs_links = soup.select('#secNavigationLinks a[href="/logs"]')
        assert logs_links, "mobile_app/index.html must keep /logs links inside #secNavigationLinks"
        for a in logs_links:
            assert a.get("data-owner-only") == "true"

    @pytest.mark.parametrize("fname", ["logs.html", "wokwi.html"])
    def test_protected_pages_mobile_nav_default_hidden(self, fname: str) -> None:
        raw = (STATIC_DIR / fname).read_text(encoding="utf-8")
        assert "\r\n" not in raw
        soup = BeautifulSoup(raw, "html.parser")
        nav = soup.find("nav", class_="mobile-nav")
        assert nav is not None
        assert nav.has_attr("hidden"), f"{fname} .mobile-nav must default to hidden"
        assert nav.get("aria-hidden") == "true"

    @pytest.mark.parametrize("fname", ["auth.html", "login.html", "register.html", "guest_guide.html"])
    def test_public_and_gate_pages_hide_protected_panel_links_by_default(self, fname: str) -> None:
        raw = (STATIC_DIR / fname).read_text(encoding="utf-8")
        assert "\r\n" not in raw
        soup = BeautifulSoup(raw, "html.parser")
        nav = soup.find("nav", class_="mobile-nav")
        assert nav is not None
        for protected_href in ("/", "/auth", "/wokwi", "/logs"):
            link = nav.find("a", href=protected_href)
            assert link is not None, f"{fname} missing {protected_href} in .mobile-nav"
            assert link.has_attr("hidden"), f"{fname} .mobile-nav {protected_href} must default to hidden"
            assert link.get("data-auth-required") == "true"
        guest_link = nav.find("a", href="/guest_guide")
        assert guest_link is not None and not guest_link.has_attr("hidden")

    def test_css_zindex_and_hidden_rules_prevent_nav_over_login_gate(self) -> None:
        style_css = (STATIC_DIR / "css" / "style.css").read_text(encoding="utf-8")
        m_modal = re.search(r"#homeLoginGateModal\s*\{[^}]*z-index:\s*(\d+)", style_css)
        m_nav = re.search(r"\.mobile-nav\s*\{[^}]*z-index:\s*(\d+)", style_css)
        assert m_modal and m_nav
        assert int(m_modal.group(1)) > int(m_nav.group(1)), (
            f"#homeLoginGateModal z-index ({m_modal.group(1)}) must exceed .mobile-nav ({m_nav.group(1)})"
        )
        assert "body.dashboard-logged-out .mobile-nav" in style_css
        assert "body.login-gate-open .mobile-nav" in style_css
        for css_name in ("auth.css", "logs.css", "wokwi.css"):
            css_text = (STATIC_DIR / "css" / css_name).read_text(encoding="utf-8")
            assert "[hidden]" in css_text or ".mobile-nav[hidden]" in css_text


class TestServerSidePanelApiAuthEnforcement:
    """All panel data APIs must reject unauthenticated callers (401/403) and succeed with a valid session."""

    @pytest.fixture(scope="class")
    def client_and_tokens(cls) -> dict[str, Any]:
        from simulator.auth.session_store import get_session_store
        from simulator.server import app

        store = get_session_store()
        owner_sess = store.create_session(
            user_id="test_owner_agyfix7",
            email="test_owner_agyfix7@example.com",
            display_name="Test Owner AgyFix7",
            tier=1,
            role="ADMIN",
            ttl_sec=1800,
        )
        family_sess = store.create_session(
            user_id="test_family_agyfix7",
            email="test_family_agyfix7@example.com",
            display_name="Test Family AgyFix7",
            tier=2,
            role="FAMILY",
            ttl_sec=1800,
        )
        owner_tok = owner_sess.session_id
        family_tok = family_sess.session_id
        client = TestClient(app)
        try:
            yield {
                "client": client,
                "owner_tok": owner_tok,
                "family_tok": family_tok,
            }
        finally:
            store.revoke_session(owner_tok)
            store.revoke_session(family_tok)

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/state"),
            ("GET", "/api/wokwi_files"),
            ("GET", "/api/voice_samples"),
            ("GET", "/api/automation"),
            ("GET", "/api/schedules"),
            ("GET", "/api/scenes"),
            ("GET", "/api/rules"),
            ("GET", "/api/logs/dashboard"),
            ("GET", "/api/server_logs_and_db"),
            ("GET", "/api/sqlite/overview"),
            ("GET", "/api/devops/status"),
            ("GET", "/api/auth3/overview"),
            ("GET", "/api/auth3/family_emails"),
            ("GET", "/api/auth3/invite_links"),
            ("GET", "/api/auth3/owner_pin/status"),
            ("GET", "/api/voice_auth/profiles"),
            ("GET", "/api/auth3/guest_invites"),
            ("GET", "/api/guest/invites"),
            ("GET", "/api/events"),
            ("POST", "/api/device"),
            ("POST", "/api/dht11"),
            ("POST", "/api/soil_moisture"),
            ("POST", "/api/ir_learn"),
            ("POST", "/api/server_mode"),
            ("POST", "/api/logs/sql_query"),
            ("POST", "/api/auth3/guest_invites"),
            ("POST", "/api/auth3/guest_qr_current"),
            ("POST", "/api/auth3/add_family_email"),
            ("POST", "/api/auth/ws_ticket"),
        ],
    )
    def test_panel_apis_reject_unauthenticated_401_or_403(
        self, client_and_tokens: dict[str, Any], method: str, path: str
    ) -> None:
        client: TestClient = client_and_tokens["client"]
        resp = client.get(path) if method == "GET" else client.post(path, json={})
        assert resp.status_code in (401, 403), (
            f"Unauthenticated {method} {path} returned {resp.status_code}: {resp.text[:200]}"
        )

    @pytest.mark.parametrize(
        "path",
        [
            "/api/state",
            "/api/wokwi_files",
            "/api/voice_samples",
            "/api/automation",
            "/api/logs/dashboard",
            "/api/auth3/overview",
            "/api/auth3/guest_invites",
        ],
    )
    def test_panel_apis_return_200_with_owner_test_session(
        self, client_and_tokens: dict[str, Any], path: str
    ) -> None:
        client: TestClient = client_and_tokens["client"]
        headers = {"X-Session-Token": client_and_tokens["owner_tok"]}
        resp = client.get(path, headers=headers)
        assert resp.status_code == 200, f"Owner GET {path} failed with {resp.status_code}: {resp.text[:200]}"

    def test_family_session_allowed_general_apis_and_blocked_owner_only_apis(
        self, client_and_tokens: dict[str, Any]
    ) -> None:
        client: TestClient = client_and_tokens["client"]
        headers = {"X-Session-Token": client_and_tokens["family_tok"]}
        for allowed in ("/api/state", "/api/wokwi_files", "/api/voice_samples", "/api/automation"):
            r = client.get(allowed, headers=headers)
            assert r.status_code == 200, f"Family GET {allowed} expected 200, got {r.status_code}"
        for owner_only in ("/api/logs/dashboard", "/api/auth3/overview", "/api/auth3/family_emails"):
            r = client.get(owner_only, headers=headers)
            assert r.status_code in (401, 403), f"Family GET {owner_only} expected 401/403, got {r.status_code}"

    def test_public_login_register_guest_guide_and_qr_apis_stay_working(
        self, client_and_tokens: dict[str, Any]
    ) -> None:
        client: TestClient = client_and_tokens["client"]
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/version").status_code == 200
        assert client.get("/api/auth3/permissions").status_code == 200
        assert client.get("/login").status_code == 200
        assert client.get("/register").status_code == 200
        assert client.get("/guest_guide").status_code == 200
        assert client.get("/api/guest/invite/validate").status_code == 403
        assert client.post("/api/auth3/layer1_login", json={"email": "nobody@example.com", "password": "wrong"}).status_code == 401
        assert client.post("/api/auth3/register_or_set_password", json={}).status_code == 400


class TestBrowserMobileAndDesktopNavGuardE2E:
    """Real Playwright checks on 412x915 mobile and 1366x768 desktop for unauth -> login -> logout."""

    @pytest.fixture(scope="class")
    def live_url_and_tokens(self) -> dict[str, Any]:
        import uvicorn
        from simulator.auth.session_store import get_session_store
        from simulator.server import _ACTIVE_BRIDGES, app

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

        store = get_session_store()
        owner_tok = store.create_session(
            user_id="pw_owner_agyfix7",
            email="pw_owner_agyfix7@example.com",
            display_name="Owner E2E Test",
            tier=1,
            role="ADMIN",
            ttl_sec=1800,
        ).session_id
        family_tok = store.create_session(
            user_id="pw_family_agyfix7",
            email="pw_family_agyfix7@example.com",
            display_name="Family E2E Test",
            tier=2,
            role="FAMILY",
            ttl_sec=1800,
        ).session_id
        try:
            yield {"base_url": base_url, "owner_tok": owner_tok, "family_tok": family_tok}
        finally:
            store.revoke_session(owner_tok)
            store.revoke_session(family_tok)
            server.should_exit = True
            thread.join(timeout=3)
            for br in list(_ACTIVE_BRIDGES):
                try:
                    br._closed = True
                except Exception:
                    pass
            _ACTIVE_BRIDGES.clear()

    def test_unauthenticated_mobile_and_desktop_hide_nav_and_block_deep_links(
        self, live_url_and_tokens: dict[str, Any]
    ) -> None:
        from playwright.sync_api import sync_playwright

        base_url = live_url_and_tokens["base_url"]
        with sync_playwright() as p:
            browser = _launch_browser(p)
            try:
                for vp in ({"width": 412, "height": 915}, {"width": 1366, "height": 768}):
                    ctx = browser.new_context(viewport=vp, is_mobile=(vp["width"] < 700))
                    page = ctx.new_page()
                    page.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
                    page.route("https://fonts.gstatic.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))

                    page.goto(f"{base_url}/#ownerGuestQrPanel", wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_selector("#homeLoginGateModal:not(.hidden)", timeout=10000)
                    page.wait_for_timeout(300)

                    state = page.evaluate(
                        """() => ({
                            hash: window.location.hash,
                            hasShell: document.getElementById('homeAppShell') !== null,
                            hasQrPanel: document.getElementById('ownerGuestQrPanel') !== null,
                            hasMobileNav: document.querySelector('.mobile-nav') !== null,
                            gateVisible: !document.getElementById('homeLoginGateModal').classList.contains('hidden'),
                        })"""
                    )
                    assert state["gateVisible"] is True
                    assert state["hasShell"] is False
                    assert state["hasQrPanel"] is False
                    assert state["hasMobileNav"] is False
                    assert state["hash"] == ""

                    # Programmatic hashchange and SPA nav attempt must remain blocked
                    page.evaluate("() => { window.location.hash = '#ownerGuestQrPanel'; }")
                    page.wait_for_timeout(150)
                    assert page.evaluate("() => window.location.hash") == ""
                    assert page.evaluate("() => document.getElementById('ownerGuestQrPanel') === null")

                    page.evaluate("() => { if (window.shNavigateSpa) window.shNavigateSpa('/logs'); }")
                    page.wait_for_timeout(200)
                    assert "/logs" not in page.url

                    # /mobile -> /app unauthenticated must hide #mobileBottomNav and block tab shortcuts
                    page.goto(f"{base_url}/mobile#secDevices", wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_selector("#mobileLoginGate:not([hidden])", timeout=10000)
                    page.wait_for_timeout(300)
                    mob = page.evaluate(
                        """() => {
                            const nav = document.getElementById('mobileBottomNav');
                            const main = document.getElementById('mobileMainContent');
                            const gate = document.getElementById('mobileLoginGate');
                            return {
                                navHidden: !nav || nav.hidden || getComputedStyle(nav).display === 'none',
                                mainHidden: !main || main.hidden || getComputedStyle(main).display === 'none',
                                gateVisible: Boolean(gate && !gate.hidden),
                                hash: window.location.hash,
                            };
                        }"""
                    )
                    assert mob["gateVisible"] is True
                    assert mob["navHidden"] is True
                    assert mob["mainHidden"] is True
                    assert mob["hash"] == ""

                    page.evaluate("() => { if (window.scrollToSection) window.scrollToSection('secDevices'); }")
                    page.wait_for_timeout(150)
                    assert page.evaluate("() => document.getElementById('mobileBottomNav').hidden") is True
                    ctx.close()
            finally:
                browser.close()

    def test_authenticated_role_visibility_and_logout_hides_nav_immediately(
        self, live_url_and_tokens: dict[str, Any]
    ) -> None:
        from playwright.sync_api import sync_playwright

        base_url = live_url_and_tokens["base_url"]
        with sync_playwright() as p:
            browser = _launch_browser(p)
            try:
                # 1. Family (Tier 2): nav visible, owner-only /logs hidden
                ctx_fam = browser.new_context(viewport={"width": 412, "height": 915}, is_mobile=True, has_touch=True)
                ctx_fam.add_cookies(
                    [
                        {"name": "sh_session_token", "value": live_url_and_tokens["family_tok"], "url": base_url},
                        {"name": "session_token", "value": live_url_and_tokens["family_tok"], "url": base_url},
                    ]
                )
                page_fam = ctx_fam.new_page()
                page_fam.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
                page_fam.route("https://fonts.gstatic.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
                page_fam.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=15000)
                page_fam.wait_for_selector("#homeMobileNav:not([hidden])", timeout=10000)
                fam_nav = page_fam.evaluate(
                    """() => {
                        const nav = document.getElementById('homeMobileNav');
                        const links = Array.from(nav.querySelectorAll('a')).map(a => ({
                            href: a.getAttribute('href'),
                            visible: !a.hidden && getComputedStyle(a).display !== 'none',
                        }));
                        return { navVisible: !nav.hidden && getComputedStyle(nav).display !== 'none', links };
                    }"""
                )
                assert fam_nav["navVisible"] is True
                vis_map = {item["href"]: item["visible"] for item in fam_nav["links"]}
                assert vis_map["/"] is True
                assert vis_map["/auth"] is True
                assert vis_map["/wokwi"] is True
                assert vis_map["/guest_guide"] is True
                assert vis_map["/logs"] is False, "Owner-only /logs nav item must stay hidden for Tier 2 Family"
                ctx_fam.close()

                # 2. Owner (Tier 1): nav visible with all 5 items, logout hides nav immediately
                ctx_own = browser.new_context(viewport={"width": 412, "height": 915}, is_mobile=True, has_touch=True)
                ctx_own.add_cookies(
                    [
                        {"name": "sh_session_token", "value": live_url_and_tokens["owner_tok"], "url": base_url},
                        {"name": "session_token", "value": live_url_and_tokens["owner_tok"], "url": base_url},
                    ]
                )
                page_own = ctx_own.new_page()
                page_own.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
                page_own.route("https://fonts.gstatic.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
                page_own.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=15000)
                page_own.wait_for_selector("#homeMobileNav:not([hidden])", timeout=10000)
                own_nav = page_own.evaluate(
                    """() => Array.from(document.querySelectorAll('#homeMobileNav a')).map(a => ({
                        href: a.getAttribute('href'),
                        visible: !a.hidden && getComputedStyle(a).display !== 'none',
                    }))"""
                )
                assert all(item["visible"] for item in own_nav), f"Owner should see all 5 nav links: {own_nav}"

                # Click logout -> nav must disappear immediately
                page_own.locator("#btnLogoutHome").click()
                page_own.wait_for_selector("#homeLoginGateModal:not(.hidden)", timeout=10000)
                page_own.wait_for_timeout(200)
                assert page_own.evaluate("() => document.querySelector('.mobile-nav') === null")
                assert page_own.evaluate("() => document.getElementById('homeAppShell') === null")
                ctx_own.close()
            finally:
                browser.close()
