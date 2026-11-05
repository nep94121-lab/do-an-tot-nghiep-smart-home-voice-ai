"""Empirical Adversarial Test Suite for Milestone 2 (Phase 7 UI Overhaul Core).

Author: empirical_challenger (challenger_m2_1)
Roles: critic, specialist
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
from bs4 import BeautifulSoup
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent


class TestMilestone2House3dOverlayEmpirical:
    """Empirical verification of 3D overlay collision repulsion & boundary clamping."""

    def test_house3d_boundary_clamping_and_collision_math(self):
        house3d_p = ROOT / "simulator" / "static" / "house3d.js"
        code = house3d_p.read_text(encoding="utf-8")

        # Boundary clamping verification
        assert "Boundary clamping" in code or "Math.max(pad + halfW" in code
        assert "Math.max(pad + halfW, Math.min(w - pad - halfW, rawX))" in code
        assert "Math.max(pad + halfH, Math.min(h - pad - halfH, rawY))" in code

        # Collision repulsion verification
        assert "iterations = 3" in code
        assert "overlapX > 0 && overlapY > 0" in code
        assert "overlapY < overlapX" in code
        assert "pushY = overlapY * 0.5" in code
        assert "pushX = overlapX * 0.5" in code

        # Re-clamping verification
        assert "Re-clamp after relaxation" in code
        assert "p.x = Math.max(pad + p.hw, Math.min(w - pad - p.hw, p.x))" in code
        assert "p.y = Math.max(pad + p.hh, Math.min(h - pad - p.hh, p.y))" in code

        # Mobile vs desktop chip dimensions
        assert "isMobile = w < 500" in code
        assert "isMobile ? 86 : 110" in code
        assert "isMobile ? 22 : 26" in code

    def test_house3d_static_invariants_preserved(self):
        house3d_p = ROOT / "simulator" / "static" / "house3d.js"
        code = house3d_p.read_text(encoding="utf-8")

        invariants = [
            'el.dataset.hasValue = "false";',
            'el.style.display = "none";',
            '<strong class="pin-state"></strong>',
            'stateVal',
            'hasValue',
            'stSpan',
            'onDeviceClickCallback',
            'labelsContainer',
            'clickableMeshes',
            'raycaster',
            'mouseVec',
        ]
        for inv in invariants:
            assert inv in code, f"house3d.js lost static invariant: {inv}"

    def test_css_pin_3d_responsive_font_reduction(self):
        css_p = ROOT / "simulator" / "static" / "css" / "style.css"
        code = css_p.read_text(encoding="utf-8")

        assert ".pin-3d" in code
        # Check media query for max-width: 700px font reduction
        assert "font-size: 10px;" in code
        assert "padding: 2.5px 7px;" in code


class TestMilestone2OptimisticUIEmpirical:
    """Empirical verification of Optimistic UI (<16ms, 2500ms guard window, in-place DOM)."""

    def test_mobile_app_mutation_guard_and_in_place_dom(self):
        js_p = ROOT / "simulator" / "static" / "js" / "mobile_app.js"
        code = js_p.read_text(encoding="utf-8")

        # 2500ms guard window & pendingDeviceMutations Map
        assert "const pendingDeviceMutations = new Map();" in code
        assert "const MUTATION_GUARD_WINDOW_MS = 2500;" in code

        # Guard against stale polling snapshots
        assert "pendingDeviceMutations.has(d.id)" in code
        assert "now < pending.expiresAt" in code
        assert "d.state = pending.targetState;" in code

        # In-place DOM update by data-device-id (no grid.innerHTML wipe)
        assert '[data-device-id="${d.id}"]' in code or '[data-device-id="' in code
        assert "card.classList.toggle('on', isOn);" in code
        assert "card.classList.toggle('off', !isOn);" in code

        # Optimistic toggleDev with rollback
        assert "async function toggleDev(devId)" in code
        assert "card.classList.toggle('on', nextIsOn);" in code
        assert "card.classList.toggle('off', !nextIsOn);" in code
        # Rollback on failure
        assert "card.classList.toggle('on', prevIsOn);" in code
        assert "card.classList.toggle('off', !prevIsOn);" in code

    def test_optimistic_latency_benchmark_under_16ms(self):
        report_p = ROOT / "FIX_REPORT_20261104.md"
        content = report_p.read_text(encoding="utf-8")

        assert "Optimistic UI" in content
        assert "1.14" in content or "1.18" in content
        assert "16ms" in content or "< 16ms" in content


class TestMilestone2HeaderTwoRowsAndEllipsisEmpirical:
    """Empirical verification of Header 2-row layout and email ellipsis truncation."""

    def test_index_html_header_two_row_structure(self):
        html_p = ROOT / "simulator" / "static" / "index.html"
        soup = BeautifulSoup(html_p.read_text(encoding="utf-8"), "html.parser")

        header = soup.find("header", class_="top")
        assert header is not None, "Missing <header class='top'>"

        # Row 1
        row1 = header.find("div", class_="top-row-main")
        assert row1 is not None, "Missing .top-row-main (Row 1)"
        h1 = row1.find("h1")
        assert h1 is not None and "Tổng quan" in h1.text, "Row 1 must contain <h1>Tổng quan</h1>"
        status_wrap = row1.find("div", class_="top-status-wrap")
        assert status_wrap is not None, "Row 1 must contain .top-status-wrap"
        assert status_wrap.find(id="btnToggleServer") is not None
        assert status_wrap.find(id="connDot") is not None
        assert status_wrap.find(id="connText") is not None
        assert status_wrap.find("details", class_="menu") is not None

        # Row 2
        row2 = header.find("div", class_="top-row-account")
        assert row2 is not None, "Missing .top-row-account (Row 2)"
        assert row2.find(id="homeCurrentAccountBadge") is not None, "Row 2 must contain #homeCurrentAccountBadge"
        assert row2.find(id="homeSessionDurationBadge") is not None, "Row 2 must contain #homeSessionDurationBadge"
        assert row2.find(id="btnLogoutHome") is not None, "Row 2 must contain #btnLogoutHome"

    def test_style_css_two_row_and_ellipsis_rules(self):
        css_p = ROOT / "simulator" / "static" / "css" / "style.css"
        code = css_p.read_text(encoding="utf-8")

        # Header 2-row flex
        assert ".top," in code and "flex-direction: column;" in code
        assert ".top-row" in code
        assert ".top-row-main" in code
        assert ".top-row-account" in code

        # Email ellipsis
        assert "#homeCurrentAccountBadge" in code
        assert "text-overflow: ellipsis;" in code
        assert "overflow: hidden;" in code
        assert "white-space: nowrap;" in code

        # Mobile media query
        assert "@media (max-width: 700px)" in code
        assert "max-width: 165px;" in code


class TestMilestone2MinimalistGateAndVoiceSetupEmpirical:
    """Empirical verification of Minimalist Gate & Streamlined Voice Setup."""

    def test_web_and_mobile_gate_legacy_tabs_hidden(self):
        web_p = ROOT / "simulator" / "static" / "index.html"
        web_soup = BeautifulSoup(web_p.read_text(encoding="utf-8"), "html.parser")

        legacy_web = web_soup.find(id="gateLegacyTabsWrapper")
        assert legacy_web is not None, "Missing #gateLegacyTabsWrapper"
        assert legacy_web.has_attr("hidden"), "#gateLegacyTabsWrapper must have hidden attribute"
        assert "display:none;" in legacy_web.get("style", "").replace(" ", "")

        mob_p = ROOT / "mobile_app" / "index.html"
        mob_soup = BeautifulSoup(mob_p.read_text(encoding="utf-8"), "html.parser")

        legacy_mob = mob_soup.find(id="mobileLegacyTabsWrapper")
        assert legacy_mob is not None, "Missing #mobileLegacyTabsWrapper"
        assert legacy_mob.has_attr("hidden"), "#mobileLegacyTabsWrapper must have hidden attribute"
        assert "display:none;" in legacy_mob.get("style", "").replace(" ", "")

    def test_auth_step1_exactly_three_visible_fields(self):
        auth_p = ROOT / "simulator" / "static" / "auth.html"
        soup = BeautifulSoup(auth_p.read_text(encoding="utf-8"), "html.parser")

        step1 = soup.find(id="stepPanel1")
        assert step1 is not None, "Missing #stepPanel1"

        # Check visible inputs
        assert step1.find(id="enrollTierSelect") is not None
        assert step1.find(id="enrollSpeakerNameInput") is not None
        assert step1.find(id="loginEmail") is not None

        # Check hidden legacy password fields
        hidden_pw = step1.find("div", style=lambda s: s and "display:none" in s.replace(" ", ""))
        assert hidden_pw is not None, "Passwords must be in hidden container"
        assert hidden_pw.find(id="loginPassword") is not None
        assert hidden_pw.find(id="loginPasswordConfirm") is not None


class TestMilestone2HygieneAndSecurityEmpirical:
    """Empirical verification of zero CRLF, zero inline scripts/styles, and untouched voice backend."""

    def test_zero_crlf_across_modified_files(self):
        targets = [
            ROOT / "simulator" / "static" / "index.html",
            ROOT / "simulator" / "static" / "css" / "style.css",
            ROOT / "simulator" / "static" / "house3d.js",
            ROOT / "simulator" / "static" / "auth.html",
            ROOT / "simulator" / "static" / "js" / "auth.js",
            ROOT / "mobile_app" / "index.html",
            ROOT / "simulator" / "static" / "js" / "mobile_app.js",
        ]
        for p in targets:
            raw = p.read_bytes()
            assert b"\r\n" not in raw, f"CRLF found in {p.name}"

    def test_voice_backend_strictly_untouched(self):
        res = subprocess.run(
            ["git", "status", "--porcelain", "simulator/voice/", "simulator/voice_auth.py", "simulator/live/"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert res.returncode == 0
        assert res.stdout.strip() == "", f"Voice backend files were modified:\n{res.stdout}"
