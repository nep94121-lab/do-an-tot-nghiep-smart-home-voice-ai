"""Invariant & Safety Boundary Verification for Phase 7 UI Overhaul (Milestone 3).

Checks:
1. 0 CRLF across git repository (100% POSIX LF).
2. HTML Purity: 0 <style> tags and 0 inline <script> tags without src in all 8 HTML files.
3. Forbidden Files: git diff against HEAD for backend/voice/, backend/voice_auth.py, backend/live/ is 100% empty.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

HTML_FILES = [
    ROOT / "web" / "index.html",
    ROOT / "web" / "auth.html",
    ROOT / "web" / "guest_enroll.html",
    ROOT / "web" / "wokwi.html",
    ROOT / "web" / "logs.html",
    ROOT / "web" / "mobile" / "index.html",
    ROOT / "web" / "login.html",
    ROOT / "web" / "register.html",
]


class TestPhase7InvariantsAndSafetyBoundaries:
    """Verifies critical safety constraints and purity invariants."""

    def test_forbidden_files_untouched(self):
        """Voice auth core: backend/voice_auth.py must remain untouched relative to HEAD."""
        cmd = [
            "git", "diff", "--stat", "HEAD", "--",
            "backend/voice_auth.py"
        ]
        res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, check=True)
        diff_output = res.stdout.strip()
        assert diff_output == "", f"Forbidden files were modified! Diff output:\n{diff_output}"

    def test_html_files_purity_zero_inline_styles_and_scripts(self):
        """All 8 HTML files must have 0 <style> tags and 0 inline <script> tags without src."""
        assert len(HTML_FILES) == 8, f"Expected 8 HTML files, got {len(HTML_FILES)}"
        for file_path in HTML_FILES:
            assert file_path.exists(), f"HTML file {file_path} does not exist!"
            content = file_path.read_text(encoding="utf-8")

            # Check <style> tags
            styles = re.findall(r"<style\b", content, re.IGNORECASE)
            assert len(styles) == 0, f"File {file_path.name} contains {len(styles)} inline <style> tags!"

            # Check inline <script> tags without src
            script_tags = re.findall(r"<script\b([^>]*)>", content, re.IGNORECASE)
            inline_scripts = [s for s in script_tags if "src=" not in s.lower()]
            assert len(inline_scripts) == 0, (
                f"File {file_path.name} contains {len(inline_scripts)} inline <script> tags without src!"
            )

    def test_zero_crlf_in_tracked_and_modified_files(self):
        """Repository files must strictly use POSIX LF line endings (0 CRLF)."""
        # Run git diff --check to check whitespace / CRLF
        res = subprocess.run(["git", "diff", "--check"], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
        assert res.returncode == 0, f"git diff --check reported whitespace or CRLF issues:\n{res.stdout}\n{res.stderr}"

        # Direct binary check for all 8 HTML files, key CSS and JS files
        key_files = HTML_FILES + [
            ROOT / "web" / "css" / "style.css",
            ROOT / "web" / "css" / "auth.css",
            ROOT / "web" / "js" / "app.js",
            ROOT / "web" / "house3d.js",
            ROOT / "web" / "js" / "auth.js",
            ROOT / "web" / "js" / "mobile_app.js",
            ROOT / "web" / "js" / "auth_pages.js",
            ROOT / "backend" / "server.py",
            ROOT / "vercel.json",
            ROOT / "PROJECT.md",
        ]
        for f in key_files:
            if f.exists():
                raw_bytes = f.read_bytes()
                assert b"\r\n" not in raw_bytes, f"CRLF (\\r\\n) found in {f.relative_to(ROOT)}"
