"""Adversarial Empirical Challenge Test Suite for Milestone 1 (Phase 7 UI Overhaul).

Author: teamwork_challenger / challenger_m1_1
Target: Milestone 1: Navigation, Routing & Dedicated Login/Register
Features Challenged:
  - Feature 1: Dedicated GET /login
  - Feature 2: Dedicated GET /register
  - Feature 3: Shared 8-route navigation
  - Feature 4: Routing configuration in server.py and vercel.json

Stress Dimensions:
  1. Routing Edge Cases: Trailing slashes, case sensitivity, query params, prefix hijacking, 404 catch-all
  2. Vercel Routing Engine Simulation: Exact pattern matching, boundary clamping (^ and $), catch-all integrity
  3. HTML Purity & Security: 0 <style> tags, 0 inline <script> tags across all repository HTML files
  4. Encoding & Formatting: 0 CRLF (\\r\\n), 0 UTF-8 BOM across all modified files
  5. Shared Navigation Completeness: Full 8-route coverage across all 8 static pages
  6. Forbidden Boundaries: Zero modifications to simulator/voice/**, simulator/voice_auth.py, simulator/live/**
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
from typing import Any

import pytest
from bs4 import BeautifulSoup
ROOT = pathlib.Path(__file__).resolve().parent.parent
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient

from simulator.server import app

VERCEL_JSON_PATH = ROOT / "vercel.json"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


REQUIRED_ROUTES = [
    "/",
    "/auth",
    "/wokwi",
    "/logs",
    "/app",
    "/guest_enroll",
    "/login",
    "/register",
]

STATIC_PAGES = [
    ROOT / "simulator" / "static" / "index.html",
    ROOT / "simulator" / "static" / "auth.html",
    ROOT / "simulator" / "static" / "wokwi.html",
    ROOT / "simulator" / "static" / "logs.html",
    ROOT / "simulator" / "static" / "guest_enroll.html",
    ROOT / "simulator" / "static" / "login.html",
    ROOT / "simulator" / "static" / "register.html",
    ROOT / "mobile_app" / "index.html",
]

MODIFIED_FILES_M1 = [
    ROOT / "simulator" / "server.py",
    ROOT / "vercel.json",
    ROOT / "simulator" / "static" / "login.html",
    ROOT / "simulator" / "static" / "register.html",
    ROOT / "simulator" / "static" / "js" / "auth_pages.js",
    ROOT / "simulator" / "static" / "css" / "style.css",
    ROOT / "simulator" / "static" / "css" / "guest_enroll.css",
    ROOT / "simulator" / "static" / "index.html",
    ROOT / "simulator" / "static" / "auth.html",
    ROOT / "simulator" / "static" / "wokwi.html",
    ROOT / "simulator" / "static" / "logs.html",
    ROOT / "simulator" / "static" / "guest_enroll.html",
    ROOT / "mobile_app" / "index.html",
    ROOT / "tests" / "test_milestone_m1_navigation_routing.py",
]



@pytest.fixture(scope="module")
def vercel_config() -> dict[str, Any]:
    assert VERCEL_JSON_PATH.exists()
    return json.loads(VERCEL_JSON_PATH.read_text(encoding="utf-8"))


def simulate_vercel_route(routes: list[dict[str, Any]], pathname: str) -> dict[str, Any] | None:
    for index, route in enumerate(routes):
        pattern = route.get("src")
        if not pattern:
            continue
        regex = re.compile(pattern)
        match = regex.search(pathname)
        if match:
            dest = route.get("dest")
            if dest and "$" in dest:
                for g_idx in range(1, len(match.groups()) + 1):
                    val = match.group(g_idx) or ""
                    dest = dest.replace(f"${g_idx}", val)
            return {
                "route_index": index,
                "src": pattern,
                "dest": dest,
                "status": route.get("status"),
                "headers": route.get("headers"),
            }
    return None


# =============================================================================
# 1. FASTAPI ROUTING EDGE CASES
# =============================================================================
class TestFastAPIRoutingEdgeCases:
    """Stress test FastAPI route handlers for /login and /register."""

    def test_fastapi_login_direct_and_trailing_slash(self, client: TestClient):
        # 1. Direct GET /login
        resp_direct = client.get("/login", follow_redirects=False)
        assert resp_direct.status_code == 200
        assert "text/html" in resp_direct.headers.get("content-type", "")
        assert "loginForm" in resp_direct.text

        # 2. Trailing slash GET /login/ (following redirects)
        resp_slash_follow = client.get("/login/", follow_redirects=True)
        assert resp_slash_follow.status_code == 200
        assert "loginForm" in resp_slash_follow.text

        # 3. Trailing slash without following redirects (Starlette returns 307)
        resp_slash_no_follow = client.get("/login/", follow_redirects=False)
        assert resp_slash_no_follow.status_code in (200, 307)
        if resp_slash_no_follow.status_code == 307:
            loc = resp_slash_no_follow.headers.get("location", "")
            assert loc == "/login" or loc.endswith("/login")

    def test_fastapi_register_direct_and_trailing_slash(self, client: TestClient):
        # 1. Direct GET /register
        resp_direct = client.get("/register", follow_redirects=False)
        assert resp_direct.status_code == 200
        assert "text/html" in resp_direct.headers.get("content-type", "")
        assert "registerForm" in resp_direct.text

        # 2. Trailing slash GET /register/ (following redirects)
        resp_slash_follow = client.get("/register/", follow_redirects=True)
        assert resp_slash_follow.status_code == 200
        assert "registerForm" in resp_slash_follow.text

        # 3. Trailing slash without following redirects (Starlette returns 307)
        resp_slash_no_follow = client.get("/register/", follow_redirects=False)
        assert resp_slash_no_follow.status_code in (200, 307)
        if resp_slash_no_follow.status_code == 307:
            loc = resp_slash_no_follow.headers.get("location", "")
            assert loc == "/register" or loc.endswith("/register")

    def test_fastapi_query_parameters_preserved(self, client: TestClient):
        """Query parameters like /login?redirect=/app should serve the login page normally."""
        resp = client.get("/login?redirect=%2Fapp&source=invite")
        assert resp.status_code == 200
        assert "loginForm" in resp.text

        resp_reg = client.get("/register?referral=xyz")
        assert resp_reg.status_code == 200
        assert "registerForm" in resp_reg.text

    def test_fastapi_prefix_hijacking_rejected(self, client: TestClient):
        """Routes like /login_extra or /register_admin must not serve login/register."""
        for bad_path in ["/login_extra", "/register_admin", "/login123", "/register_fake"]:
            headers = {"Accept": "text/html"}
            resp = client.get(bad_path, headers=headers)
            assert resp.status_code == 404, f"Path '{bad_path}' returned {resp.status_code} instead of 404!"
            assert "Không tìm thấy trang" in resp.text

    def test_fastapi_post_method_on_get_routes(self, client: TestClient):
        """Direct POST to static route /login or /register returns 405 Method Not Allowed."""
        resp_login = client.post("/login", json={"email": "test@example.com"})
        assert resp_login.status_code == 405

        resp_register = client.post("/register", json={"email": "test@example.com"})
        assert resp_register.status_code == 405

    def test_fastapi_catchall_integrity(self, client: TestClient):
        """Custom 404 page is preserved for non-existent HTML routes, JSON 404 for API."""
        headers = {"Accept": "text/html"}
        resp_html = client.get("/non_existent_page_9999", headers=headers)
        assert resp_html.status_code == 404
        assert "LỖI 404" in resp_html.text

        resp_api = client.get("/api/non_existent_endpoint_9999")
        assert resp_api.status_code == 404
        assert "application/json" in resp_api.headers.get("content-type", "")


# =============================================================================
# 2. VERCEL ROUTING ENGINE ADVERSARIAL STRESS TESTS
# =============================================================================
class TestVercelRoutingStress:
    """Stress test vercel.json regex rules for /login and /register."""

    def test_vercel_login_route_matches(self, vercel_config: dict[str, Any]):
        routes = vercel_config["routes"]

        # Exact match
        m1 = simulate_vercel_route(routes, "/login")
        assert m1 is not None
        assert m1["dest"] == "/simulator/static/login.html"
        assert m1["status"] is None

        # Trailing slash
        m2 = simulate_vercel_route(routes, "/login/")
        assert m2 is not None
        assert m2["dest"] == "/simulator/static/login.html"

    def test_vercel_register_route_matches(self, vercel_config: dict[str, Any]):
        routes = vercel_config["routes"]

        # Exact match
        m1 = simulate_vercel_route(routes, "/register")
        assert m1 is not None
        assert m1["dest"] == "/simulator/static/register.html"
        assert m1["status"] is None

        # Trailing slash
        m2 = simulate_vercel_route(routes, "/register/")
        assert m2 is not None
        assert m2["dest"] == "/simulator/static/register.html"

    def test_vercel_boundary_clamping_prevents_prefix_hijack(self, vercel_config: dict[str, Any]):
        routes = vercel_config["routes"]
        adversarial_paths = [
            "/login_bypass",
            "/login/extra",
            "/login.php",
            "/register_admin",
            "/register/subpath",
            "/register.html",
        ]
        for path in adversarial_paths:
            m = simulate_vercel_route(routes, path)
            assert m is not None
            # Must fall through to catch-all 404
            assert m["status"] == 404, f"Path '{path}' hijacked route {m['src']}"
            assert m["dest"] == "/simulator/static/404.html"

    def test_vercel_precedence_login_register_before_catchall(self, vercel_config: dict[str, Any]):
        routes = vercel_config["routes"]
        route_srcs = [r.get("src") for r in routes]

        login_idx = route_srcs.index("^/login/?$")
        register_idx = route_srcs.index("^/register/?$")
        catchall_idx = route_srcs.index("^/(.*)$")

        assert login_idx < catchall_idx, "Login route is after catch-all route!"
        assert register_idx < catchall_idx, "Register route is after catch-all route!"


# =============================================================================
# 3. HTML SECURITY & PURITY AUDIT
# =============================================================================
class TestHTMLSecurityAndPurity:
    """Audit active application pages for 0 inline scripts and 0 style tags."""

    @pytest.mark.parametrize("page_path", STATIC_PAGES)
    def test_active_pages_zero_inline_styles(self, page_path: pathlib.Path):
        """Assert zero <style> tags across all 8 active application pages."""
        assert page_path.exists(), f"File does not exist: {page_path}"
        content = page_path.read_text(encoding="utf-8")
        styles = re.findall(r"<style\b", content, re.IGNORECASE)
        assert len(styles) == 0, f"{page_path.name} contains {len(styles)} inline <style> tags!"

    @pytest.mark.parametrize("page_path", STATIC_PAGES)
    def test_active_pages_zero_inline_scripts(self, page_path: pathlib.Path):
        """Assert zero inline <script> tags across all 8 active application pages."""
        assert page_path.exists(), f"File does not exist: {page_path}"
        content = page_path.read_text(encoding="utf-8")
        script_tags = re.findall(r"<script\b([^>]*)>", content, re.IGNORECASE)
        inline_scripts = [s for s in script_tags if "src=" not in s.lower()]
        assert len(inline_scripts) == 0, f"{page_path.name} contains {len(inline_scripts)} inline <script> tags!"

    def test_dedicated_login_and_register_purity(self):
        """Dedicated login.html and register.html must be 100% pure (0 styles, 0 inline scripts)."""
        for p in [ROOT / "simulator" / "static" / "login.html", ROOT / "simulator" / "static" / "register.html"]:
            raw = p.read_text(encoding="utf-8")
            assert "<style" not in raw.lower(), f"{p.name} contains <style> tag"
            scripts = re.findall(r"<script\b([^>]*)>", raw, re.IGNORECASE)
            assert all("src=" in s.lower() for s in scripts), f"{p.name} contains inline <script>"

    def test_login_and_register_credential_hygiene(self):
        """Ensure login.html and register.html do not leak static credential values (empty value='')."""
        for p in [ROOT / "simulator" / "static" / "login.html", ROOT / "simulator" / "static" / "register.html"]:
            soup = BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser")
            for inp in soup.find_all("input", {"type": ["password", "email"]}):
                val = inp.get("value", "")
                assert val == "", f"Input {inp.get('id')} in {p.name} contains non-empty static value: '{val}'"


# =============================================================================
# 4. BYTE-LEVEL CRLF & UTF-8 BOM AUDIT
# =============================================================================
class TestEncodingAndLineEndings:
    """Assert 100% POSIX LF line endings (0 CRLF) and UTF-8 without BOM on all Milestone 1 files."""

    @pytest.mark.parametrize("file_path", MODIFIED_FILES_M1)
    def test_strictly_zero_crlf_and_no_bom(self, file_path: pathlib.Path):
        assert file_path.exists(), f"File does not exist: {file_path}"
        raw = file_path.read_bytes()

        # Check BOM
        assert not raw.startswith(b"\xef\xbb\xbf"), f"{file_path.name} has UTF-8 BOM!"

        # Check CRLF
        crlf_count = raw.count(b"\r\n")
        assert crlf_count == 0, f"{file_path.name} has {crlf_count} CRLF line endings (must be 0)!"


# =============================================================================
# 5. SHARED 8-ROUTE NAVIGATION COMPREHENSIVENESS
# =============================================================================
class TestShared8RouteNavigation:
    """Assert all 8 static pages link all 8 required routes."""

    @pytest.mark.parametrize("page_path", STATIC_PAGES)
    def test_page_has_all_8_links(self, page_path: pathlib.Path):
        assert page_path.exists(), f"Page does not exist: {page_path}"
        content = page_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")

        # Collect all href targets
        hrefs = {a.get("href") for a in soup.find_all("a", href=True)}

        missing = [route for route in REQUIRED_ROUTES if route not in hrefs]
        assert not missing, f"Page '{page_path.name}' is missing links to: {missing}"


# =============================================================================
# 6. FORBIDDEN FILE BOUNDARIES INVARIANT
# =============================================================================
class TestForbiddenBoundariesInvariant:
    """Ensure zero modifications to voice backend files."""

    def test_voice_backend_files_untouched(self):
        cmd = ["git", "status", "--porcelain", "simulator/voice", "simulator/voice_auth.py", "simulator/live"]
        result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        assert result.returncode == 0
        assert result.stdout.strip() == "", f"Forbidden files were modified!\n{result.stdout}"


# =============================================================================
# 7. LIVE BROWSER INTERACTION AUDIT (PLAYWRIGHT CHROMIUM)
# =============================================================================
class TestLiveBrowserNavigationPlaywright:
    """Live headless Chromium browser tests for Milestone 1."""

    @classmethod
    def setup_class(cls):
        import threading
        import time
        import uvicorn

        cls.port = 8996
        cls.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="error")
        )
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()
        time.sleep(1.5)

    @classmethod
    def teardown_class(cls):
        cls.server.should_exit = True
        cls.server_thread.join(timeout=2.0)

    def test_live_login_and_register_navigation(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()

            console_errors = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

            # 1. Access /login
            page.goto(f"http://127.0.0.1:{self.port}/login")
            assert "Đăng nhập" in page.title()
            assert page.locator("#pageLoginEmail").is_visible()
            assert page.locator("#pageLoginPassword").is_visible()
            assert page.locator("#pageLoginSubmitBtn").is_visible()

            # 2. Click "Đăng ký tài khoản" -> /register
            page.locator('a[href="/register"]').first.click()
            page.wait_for_url(f"http://127.0.0.1:{self.port}/register")
            assert "Đăng ký" in page.title()
            assert page.locator("#pageRegisterName").is_visible()
            assert page.locator("#pageRegisterEmail").is_visible()

            # 3. Click "Đăng nhập ngay" -> /login
            page.locator('a[href="/login"]').first.click()
            page.wait_for_url(f"http://127.0.0.1:{self.port}/login")
            assert "Đăng nhập" in page.title()

            # 4. Trailing slash test in live browser
            page.goto(f"http://127.0.0.1:{self.port}/login/")
            assert "Đăng nhập" in page.title()

            # 5. Trailing slash on register
            page.goto(f"http://127.0.0.1:{self.port}/register/")
            assert "Đăng ký" in page.title()

            browser.close()
            assert len(console_errors) == 0, f"Encountered browser console errors: {console_errors}"
