"""Regression tests for UI Overhaul U1-U5 (2026-11-14)."""

from __future__ import annotations

import os
import pathlib
import re
import socket
import subprocess
import threading
import time
import urllib.request
from typing import Iterator

import pytest
import uvicorn
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from backend.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2300-\u23FF]|➔|⬅|\u200d|\ufe0f")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def uifix_live_server() -> Iterator[str]:
    old_sandbox = os.environ.get("SIMULATOR_OFFLINE_SANDBOX")
    os.environ["SIMULATOR_OFFLINE_SANDBOX"] = "1"
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 15.0
    ready = False
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/version", timeout=2) as r:
                if r.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.2)
    if not ready:
        server.should_exit = True
        thread.join(timeout=3.0)
        raise RuntimeError(f"uifix_live_server failed to start on port {port}")
    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=3.0)
        if old_sandbox is None:
            os.environ.pop("SIMULATOR_OFFLINE_SANDBOX", None)
        else:
            os.environ["SIMULATOR_OFFLINE_SANDBOX"] = old_sandbox
        if not os.environ.get("SMARTHOME_DATA_DIR"):
            subprocess.run(["git", "checkout", "--", "backend/data/"], cwd=str(ROOT), check=False)
            extra_sess = ROOT / "backend" / "data" / "user_sessions.json"
            if extra_sess.exists():
                try:
                    extra_sess.unlink()
                except OSError:
                    pass


def test_u4_zero_decorative_emojis_and_pure_invariants() -> None:
    """U4 & Purity: zero decorative emojis, zero CRLF; 0 <style>/inline <script> in app HTML files."""
    app_html_rel = {
        "web/index.html",
        "web/auth.html",
        "web/guest_enroll.html",
        "web/guest_guide.html",
        "web/wokwi.html",
        "web/logs.html",
        "web/login.html",
        "web/register.html",
        "web/mobile/index.html",
    }
    scan_dirs = [ROOT / "web", ROOT / "web" / "mobile"]
    violations: list[str] = []
    for base in scan_dirs:
        for f in sorted(base.rglob("*")):
            if not f.is_file() or f.suffix not in (".html", ".js", ".css"):
                continue
            raw = f.read_bytes()
            rel = f.relative_to(ROOT).as_posix()
            assert b"\r\n" not in raw, f"CRLF detected in {rel}"
            assert not raw.startswith(b"\xef\xbb\xbf"), f"UTF-8 BOM detected in {rel}"
            txt = raw.decode("utf-8")
            if f.suffix == ".html":
                if rel in app_html_rel:
                    assert "<style" not in txt.lower(), f"<style> found in {rel}"
                    for ln, line in enumerate(txt.splitlines(), 1):
                        low = line.lower()
                        if "<script" in low and "src=" not in low:
                            raise AssertionError(f"Inline <script> in {rel}:{ln}")
                for ln, line in enumerate(txt.splitlines(), 1):
                    if 'href="/guest"' in line and "mobileQrOpenLink" not in line:
                        raise AssertionError(f'Forbidden static href="/guest" in {rel}:{ln}')
            for ln, line in enumerate(txt.splitlines(), 1):
                hits = EMOJI_RE.findall(line)
                if hits:
                    violations.append(f"{rel}:{ln} -> {hits}")
    assert not violations, f"Decorative emojis remain: {violations[:10]}"


def test_u1_u2_u3_static_structure_contracts() -> None:
    """Verify U1a/U1b/U1c, U2a/U2b, U3a/U3b static DOM contracts without breaking preserved IDs."""
    index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    auth_html = (ROOT / "web" / "auth.html").read_text(encoding="utf-8")
    mobile_html = (ROOT / "web" / "mobile" / "index.html").read_text(encoding="utf-8")

    home_soup = BeautifulSoup(index_html, "html.parser")
    auth_soup = BeautifulSoup(auth_html, "html.parser")
    mob_soup = BeautifulSoup(mobile_html, "html.parser")

    # U1a: #ownerGuestQrPanel canonical card on /
    qr_panel = home_soup.find(id="ownerGuestQrPanel")
    assert qr_panel is not None
    for req_id in (
        "ownerGuestInviteTier",
        "ownerGuestQrPin",
        "ownerGuestQrPinConfirmWrap",
        "ownerGuestQrGenerateBtn",
        "ownerGuestQrRevokeBtn",
        "ownerGuestQrForgotPinBtn",
        "ownerGuestPinForgotBox",
        "ownerGuestQrSvg",
        "ownerGuestLinkText",
        "ownerGuestOpenLink",
        "ownerGuestQrMeta",
        "ownerGuestQrStatusBadge",
    ):
        assert qr_panel.find(id=req_id) is not None, f"Missing #{req_id} in #ownerGuestQrPanel"
    assert home_soup.find(id="ownerGuestOpenLink").get("href") == "/guest_guide"

    # U1b + U1c: /auth removes #dynamicQr10sCard, adds link to /#ownerGuestQrPanel, collapses forgot card
    assert auth_soup.find(id="dynamicQr10sCard") is None
    redirect_link = auth_soup.find(id="linkManageQrOnHome")
    assert redirect_link is not None
    assert redirect_link.get("href") == "/#ownerGuestQrPanel"
    forgot_card = auth_soup.find(id="authForgotCard")
    assert forgot_card is not None and forgot_card.name == "details"
    assert not forgot_card.has_attr("open")
    for req_id in (
        "loginEmail",
        "btnSendForgotOtpAuth",
        "authForgotResetSection",
        "otpInput",
        "authForgotNewPassword",
        "authForgotConfirmPassword",
        "btnSubmitForgotResetAuth",
        "btnResendForgotOtpAuth",
        "loginStatusBox",
        "familyAllowlistTableBody",
        "accountsTableBody",
        "authLogsTableBody",
    ):
        assert auth_soup.find(id=req_id) is not None, f"Missing #{req_id} on /auth"

    # U2a + U2b: No HTTP Cloud / Không giới hạn strings
    assert "HTTP Cloud" not in index_html
    assert "Không giới hạn" not in index_html

    # U3a + U3b: /app removes 3D box & duplicate home buttons
    for removed_id in (
        "mobileOverviewBox",
        "mobileHomeQuickDevices",
        "mobileQuickBtnLight",
        "mobileQuickBtnFan",
        "mobileQuickBtnDoor",
        "mobileBtnViewDevices",
    ):
        assert mob_soup.find(id=removed_id) is None, f"#{removed_id} must be removed on /app"
    assert "Mô hình Toàn cảnh 3D" not in mobile_html
    script_srcs = [s.get("src", "") for s in mob_soup.find_all("script") if s.get("src")]
    assert not any("three.min.js" in s or "GLTFLoader.js" in s or "house3d.js" in s for s in script_srcs)
    for tab_id in ("mobileNavTabHome", "mobileNavTabDevices", "mobileNavTabVoice", "mobileNavTabAccount"):
        assert mob_soup.find(id=tab_id) is not None


@pytest.mark.parametrize("viewport", [{"width": 1366, "height": 768}, {"width": 390, "height": 844}])
def test_u1_u2_u3_u4_playwright_layout_and_flows(
    uifix_live_server: str, viewport: dict[str, int]
) -> None:
    """Verify /, /auth, /app responsive layout, 0 console errors, 0 overflow, Owner QR create/revoke."""
    base_url = uifix_live_server
    owner_token = "sess_owner_t1_nep94121"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")

        # 1. Anonymous view: check login gate eye SVG toggle & compact /auth
        ctx_anon = browser.new_context(viewport=viewport)
        page = ctx_anon.new_page()
        page_errors: list[str] = []
        unexpected_http: list[str] = []
        console_errors: list[str] = []

        def _attach_listeners(p_obj, *, allow_unauth_401: bool) -> None:
            p_obj.on("pageerror", lambda err: page_errors.append(str(err)))

            def _on_console(msg) -> None:
                if msg.type != "error":
                    return
                if allow_unauth_401 and "status of 401" in msg.text:
                    return
                console_errors.append(msg.text)

            def _on_resp(resp) -> None:
                if resp.status >= 400:
                    if allow_unauth_401 and resp.status == 401 and (
                        "/api/session/role" in resp.url
                        or "/api/logs/dashboard" in resp.url
                        or "/api/state" in resp.url
                    ):
                        return
                    unexpected_http.append(f"{resp.status} {resp.url}")

            p_obj.on("console", _on_console)
            p_obj.on("response", _on_resp)

        _attach_listeners(page, allow_unauth_401=True)

        page.goto(f"{base_url}/", wait_until="domcontentloaded")
        page.wait_for_selector("#homeLoginGateModal", timeout=10000)
        page.wait_for_function("() => document.getElementById('homeAppShell') === null", timeout=5000)
        assert EMOJI_RE.search(page.evaluate("document.body ? document.body.innerText : ''") or "") is None

        # Test SVG eye toggle on web login gate
        pw_btn = page.locator("#gatePanelLogin .btn-toggle-pw").first
        assert pw_btn.locator("use").get_attribute("href") == "#i-eye"
        pw_btn.click()
        assert page.get_attribute("#gateLoginPassword", "type") == "text"
        assert pw_btn.locator("use").get_attribute("href") == "#i-eye-off"
        pw_btn.click()
        assert page.get_attribute("#gateLoginPassword", "type") == "password"
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        # Check /auth logged out + compact details
        page.goto(f"{base_url}/auth", wait_until="domcontentloaded")
        page.wait_for_selector("#authForgotCard", timeout=10000)
        assert page.evaluate("document.getElementById('authForgotCard').open === false")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        await_ctx_close = ctx_anon
        await_ctx_close.close()

        # 2. Owner authenticated view: check /, QR create/revoke, /auth link, /app 4 tabs
        ctx = browser.new_context(viewport=viewport)
        ctx.add_cookies(
            [
                {"name": "sh_session_token", "value": owner_token, "url": base_url},
                {"name": "session_token", "value": owner_token, "url": base_url},
            ]
        )
        opage = ctx.new_page()
        _attach_listeners(opage, allow_unauth_401=False)

        opage.goto(f"{base_url}/", wait_until="domcontentloaded")
        opage.wait_for_selector("#ownerGuestQrPanel", timeout=10000)
        opage.wait_for_function(
            "() => (document.getElementById('homeCurrentAccountBadge')?.textContent || '').includes('Cấp 1')",
            timeout=10000,
        )
        # U2a + U2b + U4 checks
        assert opage.text_content("#connText") == "Đã kết nối"
        assert opage.is_hidden("#homeServerStatusBadge")
        assert opage.is_hidden("#homeSessionDurationBadge")
        assert (opage.text_content("#homeSessionDurationBadge") or "") == ""
        acc_text = opage.text_content("#homeCurrentAccountBadge") or ""
        assert EMOJI_RE.search(acc_text) is None
        assert "Chủ nhà" in acc_text
        assert opage.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        # U1a: Create and revoke single-use QR via #ownerGuestQrPanel
        if opage.is_visible("#ownerGuestQrPinConfirm"):
            opage.fill("#ownerGuestQrPinConfirm", "1234")
        opage.fill("#ownerGuestQrPin", "1234")
        opage.click("#ownerGuestQrGenerateBtn")
        opage.wait_for_selector("#ownerGuestQrSvg svg", timeout=10000)
        assert "Dùng một lần" in (opage.text_content("#ownerGuestQrStatusBadge") or "")
        assert "/guest?token=" in (opage.text_content("#ownerGuestLinkText") or "")
        opage.click("#ownerGuestQrRevokeBtn")
        opage.wait_for_function(
            "() => !document.querySelector('#ownerGuestQrSvg svg')",
            timeout=10000,
        )

        # U1b/U1c: /auth Owner view has #linkManageQrOnHome -> /#ownerGuestQrPanel and no horizontal overflow
        opage.goto(f"{base_url}/auth", wait_until="domcontentloaded")
        opage.wait_for_selector("#linkManageQrOnHome", timeout=10000)
        assert opage.query_selector("#dynamicQr10sCard") is None
        assert opage.get_attribute("#linkManageQrOnHome", "href") == "/#ownerGuestQrPanel"
        assert opage.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        # U3a/U3b: /app 4 bottom tabs work cleanly, 0 3D placeholder, 0 duplicate quick buttons
        opage.goto(f"{base_url}/app", wait_until="domcontentloaded")
        opage.wait_for_selector("#mobileMainContent:not([hidden])", timeout=10000)
        assert opage.query_selector("#mobileOverviewBox") is None
        assert opage.query_selector("#mobileHomeQuickDevices") is None
        assert opage.query_selector("#mobileBtnViewDevices") is None
        assert opage.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        opage.click("#mobileNavTabDevices")
        opage.wait_for_selector("#devGrid [data-device-id='speaker_amp']", timeout=10000)
        assert len(opage.query_selector_all("#devGrid .dev-row")) == 6
        assert opage.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        opage.click("#mobileNavTabVoice")
        opage.wait_for_selector("#tabViewVoice:not([hidden])", timeout=5000)
        opage.click("#mobileNavTabAccount")
        opage.wait_for_selector("#tabViewAccount:not([hidden])", timeout=5000)
        assert opage.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        ctx.close()
        browser.close()
        assert not page_errors, f"Page errors on {viewport}: {page_errors}"
        assert not unexpected_http, f"Unexpected HTTP errors on {viewport}: {unexpected_http}"
        assert not console_errors, f"Console errors on {viewport}: {console_errors}"


@pytest.mark.parametrize("viewport", [{"width": 1366, "height": 768}, {"width": 390, "height": 844}])
def test_u5_production_public_pages_playwright(
    viewport: dict[str, int],
    request: pytest.FixtureRequest,
) -> None:
    """Verify public UI routes (using UIFIX_PROD_URL when set, otherwise uifix_live_server) for layout overflow, 0 emojis, SVG eye toggle, and 0 console errors."""
    prod_url = (os.environ.get("UIFIX_PROD_URL") or request.getfixturevalue("uifix_live_server")).rstrip("/")
    with urllib.request.urlopen(f"{prod_url}/api/version", timeout=10) as r:
        assert r.status == 200

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        ctx = browser.new_context(viewport=viewport)
        page = ctx.new_page()
        console_errors: list[str] = []
        page_errors: list[str] = []
        unexpected_http: list[str] = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.on(
            "console",
            lambda m: console_errors.append(m.text)
            if (m.type == "error" and "status of 401" not in m.text)
            else None,
        )
        page.on(
            "response",
            lambda r: unexpected_http.append(f"{r.status} {r.url}")
            if (
                r.status >= 400
                and not (
                    r.status == 401
                    and (
                        "/api/session/role" in r.url
                        or "/api/logs/dashboard" in r.url
                        or "/api/state" in r.url
                    )
                )
            )
            else None,
        )

        for route in ("/", "/auth", "/app", "/guest_guide", "/login", "/register", "/logs"):
            page.goto(f"{prod_url}{route}", wait_until="domcontentloaded")
            page.wait_for_timeout(400)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
                f"Horizontal overflow on {route} at {viewport}"
            )
            body_txt = page.evaluate("document.body ? document.body.innerText : ''") or ""
            assert EMOJI_RE.search(body_txt) is None, f"Decorative emoji found in {route}: {body_txt[:200]}"
            assert "HTTP Cloud" not in body_txt
            assert "Không giới hạn" not in body_txt

            if route == "/" and page.is_visible("#gateLoginPassword"):
                btn = page.locator("#gatePanelLogin .btn-toggle-pw").first
                if btn.count():
                    assert btn.locator("use").get_attribute("href") == "#i-eye"
                    btn.click()
                    assert page.get_attribute("#gateLoginPassword", "type") == "text"
                    assert btn.locator("use").get_attribute("href") == "#i-eye-off"
                    btn.click()
                    assert page.get_attribute("#gateLoginPassword", "type") == "password"
            elif route == "/auth":
                assert page.evaluate("document.getElementById('authForgotCard')?.open === false")
                assert page.query_selector("#dynamicQr10sCard") is None
            elif route == "/app":
                assert page.query_selector("#mobileOverviewBox") is None
                assert page.query_selector("#mobileHomeQuickDevices") is None
                assert page.query_selector("#mobileBtnViewDevices") is None
                if page.is_visible("#mobileLoginPassword"):
                    btn = page.locator("#mobileLoginGate .btn-toggle-pw").first
                    assert btn.locator("use").get_attribute("href") == "#i-eye"
                    btn.click()
                    assert page.get_attribute("#mobileLoginPassword", "type") == "text"
                    assert btn.locator("use").get_attribute("href") == "#i-eye-off"
                    btn.click()
                    assert page.get_attribute("#mobileLoginPassword", "type") == "password"

        ctx.close()
        browser.close()
        assert not page_errors, f"Production page errors on {viewport}: {page_errors}"
        assert not unexpected_http, f"Production HTTP errors on {viewport}: {unexpected_http}"
        assert not console_errors, f"Production console errors on {viewport}: {console_errors}"

