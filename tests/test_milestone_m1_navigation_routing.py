"""Empirical Verification Suite for Milestone 1:
Navigation, Routing & Dedicated Login/Register Pages.

Verifies:
1. FastAPI server routes for GET /login and GET /register return HTTP 200 OK.
2. Vercel routing rules for ^/login/?$ and ^/register/?$ map to valid destination files.
3. Pure HTML compliance: 0 <style> tags and 0 inline <script> tags on login.html and register.html.
4. Zero CRLF (100% POSIX LF) line endings on all milestone files.
5. Shared 8-route navigation consistency across all 8 static pages:
   - / (Overview)
   - /auth (Voice Auth)
   - /wokwi (Hardware)
   - /logs (Logs)
   - /app (App)
   - /guest_enroll (Guest)
   - /login (Login)
   - /register (Register)
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

import pytest
from bs4 import BeautifulSoup
from starlette.testclient import TestClient

from simulator.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERCEL_JSON_PATH = ROOT / "vercel.json"

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


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def vercel_config() -> dict[str, Any]:
    assert VERCEL_JSON_PATH.exists()
    return json.loads(VERCEL_JSON_PATH.read_text(encoding="utf-8"))


class TestMilestone1RoutingAndPages:
    """Verifies FastAPI and Vercel routing for /login and /register."""

    def test_fastapi_get_login(self, client: TestClient):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "loginForm" in resp.text
        assert "pageLoginEmail" in resp.text
        assert "pageLoginPassword" in resp.text
        assert "pageLoginSubmitBtn" in resp.text

    def test_fastapi_get_register(self, client: TestClient):
        resp = client.get("/register")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "registerForm" in resp.text
        assert "pageRegisterName" in resp.text
        assert "pageRegisterEmail" in resp.text
        assert "pageRegisterPassword" in resp.text
        assert "pageRegisterConfirmPassword" in resp.text
        assert "pageRegisterSubmitBtn" in resp.text

    def test_vercel_routes_contain_login_and_register(self, vercel_config: dict[str, Any]):
        routes = vercel_config.get("routes", [])
        src_patterns = [r.get("src") for r in routes if "src" in r]

        assert "^/login/?$" in src_patterns
        assert "^/register/?$" in src_patterns

        login_rule = next(r for r in routes if r.get("src") == "^/login/?$")
        register_rule = next(r for r in routes if r.get("src") == "^/register/?$")

        assert login_rule.get("dest") == "/simulator/static/login.html"
        assert register_rule.get("dest") == "/simulator/static/register.html"

        # Verify destination files exist on disk
        login_file = ROOT / login_rule["dest"].lstrip("/")
        register_file = ROOT / register_rule["dest"].lstrip("/")
        assert login_file.exists()
        assert register_file.exists()


class TestMilestone1PurityAndEncoding:
    """Verifies strict 0 inline styles, 0 inline scripts, and 0 CRLF."""

    @pytest.mark.parametrize("page_path", STATIC_PAGES)
    def test_html_purity_zero_inline_styles_and_scripts(self, page_path: pathlib.Path):
        assert page_path.exists(), f"Missing file: {page_path}"
        content = page_path.read_text(encoding="utf-8")

        # 1. 0 <style> tags
        style_matches = re.findall(r"<style\b", content, re.IGNORECASE)
        assert len(style_matches) == 0, f"{page_path.name} contains {len(style_matches)} <style> tags!"

        # 2. 0 inline <script> tags
        script_tags = re.findall(r"<script\b([^>]*)>", content, re.IGNORECASE)
        inline_scripts = [s for s in script_tags if "src=" not in s.lower()]
        assert len(inline_scripts) == 0, f"{page_path.name} contains {len(inline_scripts)} inline <script> tags!"

    @pytest.mark.parametrize("page_path", STATIC_PAGES)
    def test_posix_lf_line_endings_zero_crlf(self, page_path: pathlib.Path):
        raw_bytes = page_path.read_bytes()
        crlf_count = raw_bytes.count(b"\r\n")
        assert crlf_count == 0, f"{page_path.name} contains {crlf_count} CRLF line endings!"
        assert not raw_bytes.startswith(b"\xef\xbb\xbf"), f"{page_path.name} contains UTF-8 BOM!"


class TestMilestone1SharedNavigation:
    """Verifies that all 8 static pages link all 8 routes."""

    @pytest.mark.parametrize("page_path", STATIC_PAGES)
    def test_page_contains_all_8_routes(self, page_path: pathlib.Path):
        content = page_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")
        hrefs = {a.get("href") for a in soup.find_all("a", href=True)}

        missing_routes = [r for r in REQUIRED_ROUTES if r not in hrefs]
        assert not missing_routes, f"{page_path.name} is missing links to: {missing_routes}"
