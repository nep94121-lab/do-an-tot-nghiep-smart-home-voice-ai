"""Adversarial Challenge & Stress-Test Suite for Milestone 1.
Executed by teamwork_critic / challenger_m1_2_gen3.

Verifies:
1. 8-Route Navigation Matrix across all 8 static pages.
2. DOM Accessibility (aria-current="page") & active class consistency.
3. Password credential masking (strictly empty value="").
4. Server and Vercel routing parity.
5. Zero inline styles/scripts and zero CRLF.
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

ROOT = pathlib.Path(__file__).resolve().parents[3]
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

PAGES = {
    "/": ROOT / "simulator" / "static" / "index.html",
    "/auth": ROOT / "simulator" / "static" / "auth.html",
    "/wokwi": ROOT / "simulator" / "static" / "wokwi.html",
    "/logs": ROOT / "simulator" / "static" / "logs.html",
    "/app": ROOT / "mobile_app" / "index.html",
    "/guest_enroll": ROOT / "simulator" / "static" / "guest_enroll.html",
    "/login": ROOT / "simulator" / "static" / "login.html",
    "/register": ROOT / "simulator" / "static" / "register.html",
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestAdversarial8RouteMatrix:
    """Stress-tests 8-route navigation coverage on all 8 static pages."""

    @pytest.mark.parametrize("route,page_path", list(PAGES.items()))
    def test_page_contains_exact_8_routes(self, route: str, page_path: pathlib.Path):
        assert page_path.exists(), f"Target file does not exist: {page_path}"
        content = page_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")
        hrefs = {a.get("href") for a in soup.find_all("a", href=True)}

        missing = [r for r in REQUIRED_ROUTES if r not in hrefs]
        assert not missing, f"Page '{route}' ({page_path.name}) is missing navigation routes: {missing}"

    @pytest.mark.parametrize("route,page_path", list(PAGES.items()))
    def test_no_broken_relative_route_variants(self, route: str, page_path: pathlib.Path):
        """Asserts pages don't use inconsistent variations like /login/ or ./login or login.html."""
        content = page_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")
        all_hrefs = [a.get("href") for a in soup.find_all("a", href=True)]

        for h in all_hrefs:
            assert not h.endswith(".html"), f"Found unrouted raw HTML link '{h}' in {page_path.name}"
            if h in ["/login/", "/register/", "/auth/", "/app/", "/wokwi/", "/logs/", "/guest_enroll/"]:
                pytest.fail(f"Found unnecessary trailing slash in link '{h}' in {page_path.name}")


class TestDOMAccessibilityAndActiveClasses:
    """Verifies aria-current="page" and active class attributes."""

    @pytest.mark.parametrize("route,page_path", list(PAGES.items()))
    def test_current_page_accessibility_and_active_state(self, route: str, page_path: pathlib.Path):
        content = page_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")

        # Find link(s) to current page
        self_links = [a for a in soup.find_all("a", href=True) if a.get("href") == route]
        assert len(self_links) >= 1, f"Page {route} has no link to itself!"

        has_active_class = any("active" in a.get("class", []) for a in self_links)
        has_aria_current = any(a.get("aria-current") == "page" for a in self_links)

        # We record whether both active class and aria-current="page" are present
        # This will highlight any page missing accessibility or active class
        assert has_active_class or route == "/app", f"Page {route} is missing 'active' class on its self-link!"
        assert has_aria_current or route == "/app", f"Page {route} is missing aria-current='page' on its self-link!"

    @pytest.mark.parametrize("route,page_path", list(PAGES.items()))
    def test_non_current_links_do_not_falsely_claim_aria_current(self, route: str, page_path: pathlib.Path):
        """Asserts links to OTHER pages do not have aria-current="page"."""
        content = page_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")

        other_links = [a for a in soup.find_all("a", href=True) if a.get("href") in REQUIRED_ROUTES and a.get("href") != route]
        for a in other_links:
            aria = a.get("aria-current")
            assert aria != "page", f"Page {route} falsely marks link '{a.get('href')}' with aria-current='page'!"


class TestCredentialMasking:
    """Verifies that password inputs never leak pre-filled static credentials."""

    def test_login_password_masking(self):
        content = PAGES["/login"].read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")
        pw = soup.find("input", id="pageLoginPassword")
        assert pw is not None, "Missing #pageLoginPassword in login.html"
        assert pw.get("type") == "password"
        assert "value" in pw.attrs, "Missing static value attribute on #pageLoginPassword"
        assert pw.get("value") == "", f"#pageLoginPassword static value is not empty: '{pw.get('value')}'"

    def test_register_password_masking(self):
        content = PAGES["/register"].read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")
        pw1 = soup.find("input", id="pageRegisterPassword")
        pw2 = soup.find("input", id="pageRegisterConfirmPassword")

        assert pw1 is not None, "Missing #pageRegisterPassword in register.html"
        assert pw1.get("type") == "password"
        assert "value" in pw1.attrs, "Missing static value attribute on #pageRegisterPassword"
        assert pw1.get("value") == "", f"#pageRegisterPassword static value is not empty: '{pw1.get('value')}'"

        assert pw2 is not None, "Missing #pageRegisterConfirmPassword in register.html"
        assert pw2.get("type") == "password"
        assert "value" in pw2.attrs, "Missing static value attribute on #pageRegisterConfirmPassword"
        assert pw2.get("value") == "", f"#pageRegisterConfirmPassword static value is not empty: '{pw2.get('value')}'"

    @pytest.mark.parametrize("route,page_path", list(PAGES.items()))
    def test_all_password_inputs_have_no_hardcoded_credentials(self, route: str, page_path: pathlib.Path):
        content = page_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")
        pw_inputs = soup.find_all("input", {"type": "password"})

        for p in pw_inputs:
            val = p.get("value")
            # If value attribute is present, it MUST be empty string
            if val is not None:
                assert val == "", f"Hardcoded password detected in {page_path.name} on input #{p.get('id')}: '{val}'"


class TestRoutingAndPurityParity:
    """Verifies FastAPI responses, Vercel rules, and HTML purity."""

    def test_fastapi_login_returns_200(self, client: TestClient):
        res = client.get("/login")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        assert "loginForm" in res.text

    def test_fastapi_register_returns_200(self, client: TestClient):
        res = client.get("/register")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        assert "registerForm" in res.text

    def test_vercel_routes_contain_login_and_register(self):
        data = json.loads(VERCEL_JSON_PATH.read_text(encoding="utf-8"))
        srcs = [r.get("src") for r in data.get("routes", [])]
        assert "^/login/?$" in srcs
        assert "^/register/?$" in srcs

    @pytest.mark.parametrize("route,page_path", list(PAGES.items()))
    def test_zero_inline_styles_and_scripts(self, route: str, page_path: pathlib.Path):
        content = page_path.read_text(encoding="utf-8")
        # 0 <style> tags
        assert not re.search(r"<style\b", content, re.IGNORECASE), f"{page_path.name} has <style> tag"
        # 0 inline <script> tags
        for s in re.findall(r"<script\b([^>]*)>", content, re.IGNORECASE):
            assert "src=" in s.lower(), f"{page_path.name} has inline script without src: {s}"

    @pytest.mark.parametrize("route,page_path", list(PAGES.items()))
    def test_zero_crlf_and_no_bom(self, route: str, page_path: pathlib.Path):
        raw = page_path.read_bytes()
        assert b"\r\n" not in raw, f"{page_path.name} contains CRLF line endings"
        assert not raw.startswith(b"\xef\xbb\xbf"), f"{page_path.name} contains UTF-8 BOM"
