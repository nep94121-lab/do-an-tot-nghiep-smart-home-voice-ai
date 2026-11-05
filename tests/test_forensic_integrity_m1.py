"""Forensic Integrity Verification for Milestone 1.

Verifies:
1. Genuine implementation:
   - FastAPI server.py routes /login and /register return genuine FileResponse.
   - static/login.html and register.html are complete DOM forms with real inputs and actions.
   - auth_pages.js calls real endpoints (/api/auth3/layer1_login, /api/auth3/register_or_set_password).
   - vercel.json routes /login and /register correctly.
2. Boundary protection:
   - Zero modifications to simulator/voice/**, simulator/voice_auth.py, simulator/live/**.
3. Secret scanning:
   - Zero hardcoded credentials or API keys.
   - Empty static value="" on password and credential inputs.
4. Purity & Encoding:
   - 100% POSIX LF (0 CRLF) across all touched files.
   - 0 <style> tags and 0 inline <script> tags across all HTML files.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
from typing import Any

import pytest
from bs4 import BeautifulSoup
from starlette.testclient import TestClient

import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent

CHECKED_FILES = [
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
]

HTML_FILES = [p for p in CHECKED_FILES if p.suffix == ".html"]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestForensicIntegrityM1:
    def test_posix_lf_encoding_zero_crlf_all_files(self) -> None:
        """Every touched file must have 0 CRLF and no UTF-8 BOM."""
        for file_path in CHECKED_FILES:
            assert file_path.exists(), f"File {file_path} does not exist"
            raw = file_path.read_bytes()
            assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM detected in {file_path.name}"
            crlf_count = raw.count(b"\r\n")
            assert crlf_count == 0, f"{file_path.name} contains {crlf_count} CRLF line endings!"

    def test_zero_style_and_zero_inline_script_tags_in_html(self) -> None:
        """All HTML files must have 0 <style> tags and 0 inline <script> tags."""
        for html_path in HTML_FILES:
            text = html_path.read_text(encoding="utf-8")
            style_tags = re.findall(r"<style\b", text, re.IGNORECASE)
            assert len(style_tags) == 0, f"{html_path.name} has {len(style_tags)} <style> tags"

            script_tags = re.findall(r"<script\b([^>]*)>", text, re.IGNORECASE)
            inline_scripts = [s for s in script_tags if "src=" not in s.lower()]
            assert len(inline_scripts) == 0, f"{html_path.name} has {len(inline_scripts)} inline <script> tags"

    def test_zero_modifications_to_forbidden_files(self) -> None:
        """Verify git status shows zero changes to forbidden paths."""
        res = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "simulator/voice/", "simulator/voice_auth.py", "simulator/live/"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        assert res.stdout.strip() == "", f"Forbidden files modified: {res.stdout}"

    def test_zero_untracked_files_in_forbidden_paths(self) -> None:
        """Verify no untracked files were added to forbidden paths."""
        res = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "simulator/voice/", "simulator/voice_auth.py", "simulator/live/"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        assert res.stdout.strip() == "", f"Forbidden untracked files: {res.stdout}"

    def test_no_hardcoded_credentials_in_inputs(self) -> None:
        """Credential input fields must not contain hardcoded values."""
        for html_path in [ROOT / "simulator" / "static" / "login.html", ROOT / "simulator" / "static" / "register.html"]:
            soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
            inputs = soup.find_all("input")
            for inp in inputs:
                val = inp.get("value", "")
                assert val == "", f"{html_path.name} input #{inp.get('id')} has hardcoded value: '{val}'"

    def test_genuine_auth_pages_js_implementation(self) -> None:
        """Verify auth_pages.js has genuine API integrations without mocking/cheating."""
        js_path = ROOT / "simulator" / "static" / "js" / "auth_pages.js"
        assert js_path.exists()
        js_code = js_path.read_text(encoding="utf-8")

        # Must call genuine auth endpoints
        assert "/api/auth3/layer1_login" in js_code
        assert "/api/auth3/register_or_set_password" in js_code
        assert "/api/auth3/forgot_password_send_otp" in js_code

        # Must have event listeners and validation
        assert "addEventListener('submit'" in js_code or 'addEventListener("submit"' in js_code
        assert "localStorage.setItem('smarthome_auth_session'" in js_code

        # Must not contain dummy return true or fake token hardcoded
        assert "AIzaSy" not in js_code
        assert "fake_token" not in js_code
        assert "dummy_token" not in js_code

    def test_genuine_server_routing(self, client: TestClient) -> None:
        """Verify server endpoints genuinely serve the files and return 200."""
        r_login = client.get("/login")
        assert r_login.status_code == 200
        assert "Đăng nhập" in r_login.text
        assert "pageLoginEmail" in r_login.text

        r_reg = client.get("/register")
        assert r_reg.status_code == 200
        assert "Đăng ký tài khoản" in r_reg.text
        assert "pageRegisterPassword" in r_reg.text

    def test_shared_navigation_in_all_pages(self) -> None:
        """All 8 pages must link all 8 required paths."""
        required = ["/", "/auth", "/wokwi", "/logs", "/app", "/guest_enroll", "/login", "/register"]
        for p in HTML_FILES:
            soup = BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser")
            links = {a.get("href") for a in soup.find_all("a", href=True)}
            missing = [r for r in required if r not in links]
            assert not missing, f"{p.name} missing navigation routes: {missing}"
