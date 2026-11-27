"""Automated tests for agyfix11 R5-R7:
- Capacitor (C1..C9) and flyback diode (D1, D2 / 1N4007) SSOT parity across
  hardware/wiring_contract.py, web/data/wiring_contract.json, docs/phan_cung/WIRING_TABLE.md,
  docs/phan_cung/wiring_diagram_2d.svg, docs/phan_cung/diy_pcb/BOM_DIY_SHOPPING.md,
  docs/phan_cung/DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md, and /wokwi DOM.
- Real Playwright headless test on /wokwi verifying Breadboard & PCB 2D zoom in (+),
  zoom out (-), mouse wheel zoom, drag/pan, "Vừa màn hình" (fit), "100%" reset,
  desktop 1366x768 & mobile 412x915 (has_touch=True), Light & Dark modes,
  toolbar & zoom buttons >= 44x44 px on mobile, 0 horizontal overflow,
  Vietnamese-only labels, and HTTP 200 on /docs/phan_cung/HUONG_DAN_NAP_FIRMWARE_USB.md.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any

import pytest
import requests

from hardware.wiring_contract import PROTECTION_COMPONENTS

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

REQUIRED_PROTECTION_REFS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "D1", "D2")
REQUIRED_PARITY_FILES = (
    "hardware/wiring_contract.py",
    "web/data/wiring_contract.json",
    "docs/phan_cung/WIRING_TABLE.md",
    "docs/phan_cung/wiring_diagram_2d.svg",
    "docs/phan_cung/diy_pcb/BOM_DIY_SHOPPING.md",
    "docs/phan_cung/DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md",
)

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
)
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _find_chromium_executable() -> str | None:
    env_exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "").strip()
    if env_exe and pathlib.Path(env_exe).exists():
        return env_exe
    for base in (pathlib.Path.home(), pathlib.Path(r"C:\Users\LENOVO")):
        pup = base / ".cache" / "puppeteer"
        if pup.exists():
            for pat in ("chrome-headless-shell.exe", "chrome.exe"):
                for exe in sorted(pup.rglob(pat), reverse=True):
                    if exe.exists():
                        return str(exe)
    return None


def _launch_headless_chromium(p: Any) -> Any:
    exe = _find_chromium_executable()
    attempts: list[dict[str, Any]] = []
    if exe:
        attempts.append({"headless": True, "executable_path": exe})
    attempts.extend([{"headless": True}, {"headless": True, "channel": "msedge"}])
    last_err: Exception | None = None
    for kw in attempts:
        try:
            return p.chromium.launch(timeout=25000, **kw)
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"Could not launch headless Chromium: {last_err}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _has_token(text: str, token: str) -> bool:
    return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", text))


# ==============================================================================
# R6: CAPACITOR (C1..C9) & FLYBACK DIODE (D1, D2 / 1N4007) SSOT PARITY
# ==============================================================================


class TestProtectionComponentParity:
    def test_ssot_contract_and_json_have_exact_c1_c9_and_d1_d2(self) -> None:
        refs = tuple(c.ref for c in PROTECTION_COMPONENTS)
        for req in REQUIRED_PROTECTION_REFS:
            assert req in refs, f"Missing {req} in hardware/wiring_contract.py PROTECTION_COMPONENTS"

        diodes = [c for c in PROTECTION_COMPONENTS if c.kind == "flyback_diode"]
        assert {d.ref for d in diodes} == {"D1", "D2"}
        for d in diodes:
            assert "1N4007" in d.value

        json_path = REPO_ROOT / "web" / "data" / "wiring_contract.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text(encoding="utf-8"))
        json_prot = data.get("protection_components") or []
        json_refs = tuple(item["ref"] for item in json_prot)
        assert json_refs == refs, f"JSON protection_components mismatch: {json_refs} != {refs}"

    @pytest.mark.parametrize("rel_path", REQUIRED_PARITY_FILES)
    def test_all_docs_bom_svg_and_contract_include_c1_c9_d1_d2_1n4007(self, rel_path: str) -> None:
        p = REPO_ROOT / rel_path
        assert p.exists(), f"Missing parity file: {rel_path}"
        content = p.read_text(encoding="utf-8")
        missing = [tok for tok in (*REQUIRED_PROTECTION_REFS, "1N4007") if not _has_token(content, tok)]
        assert not missing, f"{rel_path} is missing protection tokens: {missing}"


# ==============================================================================
# R5 + R6 + R7: REAL PLAYWRIGHT HEADLESS /wokwi ZOOM, PAN, MOBILE, DARK/LIGHT & DOC ROUTE
# ==============================================================================


class TestWokwiZoomPanProtectionAndUsbDoc:
    def test_wokwi_breadboard_and_pcb2d_zoom_pan_mobile_themes_protection_and_usb_doc(self) -> None:
        from playwright.sync_api import sync_playwright

        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"

        with tempfile.TemporaryDirectory(prefix="agyfix11_wokwi_") as td:
            data_dir = pathlib.Path(td) / "data"
            log_dir = pathlib.Path(td) / "logs"
            data_dir.mkdir(parents=True, exist_ok=True)
            log_dir.mkdir(parents=True, exist_ok=True)

            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT)
            env["SMARTHOME_DATA_DIR"] = str(data_dir)
            env["SMARTHOME_LOG_DIR"] = str(log_dir)
            env["GEMINI_API_KEY"] = ""
            env["SMARTHOME_SESSION_SECRET"] = "fix11_wokwi_test_secret"
            env["GMAIL_APP_PASSWORD"] = ""
            env["SMTP_PASSWORD"] = ""
            env.pop("SIMULATOR_SECURITY_STATE_DIR", None)
            env.pop("SIMULATOR_OFFLINE_SANDBOX", None)

            seed_code = r"""
import json
from backend.auth_3layer import get_auth_3layer_manager
from backend.auth.constants_and_crypto import hash_password
from backend.auth.session_store import mint_trusted_device_token
from backend.database_sqlite import init_sqlite_database

init_sqlite_database()
mgr = get_auth_3layer_manager()
pw = "Fix11Wokwi#2026!"
pw_hash = hash_password(pw)
owner_acc = next(a for a in mgr.accounts if int(a.get("tier") or 0) == 1)
owner_email = str(owner_acc["email"]).strip().lower()
owner_id = str(owner_acc.get("account_id") or owner_acc.get("id") or "tuan_anh")

def _upd():
    for a in mgr.accounts:
        if str(a.get("email") or "").strip().lower() == owner_email:
            a["password_hash"] = pw_hash
            a["permission_active"] = True
            a["permission_status"] = "ACTIVE"
    return mgr._save_accounts()

mgr._with_cas_accounts(_upd)
td_desk = mint_trusted_device_token(
    account_id=owner_id,
    email=owner_email,
    password_hash=pw_hash,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
)
td_mob = mint_trusted_device_token(
    account_id=owner_id,
    email=owner_email,
    password_hash=pw_hash,
    user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
)
print(json.dumps({"owner_email": owner_email, "td_desk": td_desk, "td_mob": td_mob}))
"""
            seed_proc = subprocess.run(
                [sys.executable, "-c", seed_code],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            assert seed_proc.returncode == 0, f"Seed failed:\n{seed_proc.stderr}\n{seed_proc.stdout}"
            tokens = json.loads(
                [ln for ln in seed_proc.stdout.splitlines() if ln.strip().startswith("{")][-1]
            )

            proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "backend.server:app", "--host", "127.0.0.1", "--port", str(port)],
                cwd=str(REPO_ROOT),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                deadline = time.time() + 25.0
                while time.time() < deadline:
                    try:
                        if requests.get(f"{base_url}/api/health", timeout=2).status_code == 200:
                            break
                    except Exception:
                        pass
                    time.sleep(0.3)
                else:
                    raise RuntimeError("Local FastAPI server did not become healthy in time")

                # 1. Verify /docs/phan_cung/HUONG_DAN_NAP_FIRMWARE_USB.md returns HTTP 200
                doc_resp = requests.get(f"{base_url}/docs/phan_cung/HUONG_DAN_NAP_FIRMWARE_USB.md", timeout=10)
                assert doc_resp.status_code == 200, f"Expected 200 for USB flash doc, got {doc_resp.status_code}"
                assert "flash_and_setup.ps1" in doc_resp.text
                assert "CP210x" in doc_resp.text or "CH340" in doc_resp.text

                def _login_and_open_wokwi(ctx: Any, td_token: str) -> Any:
                    ctx.add_cookies(
                        [
                            {
                                "name": "sh_trusted_device",
                                "value": td_token,
                                "url": base_url,
                                "httpOnly": True,
                                "sameSite": "Lax",
                            }
                        ]
                    )
                    page = ctx.new_page()
                    page.goto(f"{base_url}/login", wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_selector("#pageLoginEmail", state="visible", timeout=15000)
                    page.fill("#pageLoginEmail", tokens["owner_email"])
                    page.fill("#pageLoginPassword", "Fix11Wokwi#2026!")
                    page.click("#pageLoginSubmitBtn")
                    page.wait_for_function(
                        "() => window.location.pathname !== '/login'",
                        timeout=15000,
                    )
                    page.goto(f"{base_url}/wokwi", wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_selector("[data-wg-zoom='in']", state="visible", timeout=15000)
                    page.wait_for_selector("#wokwiProtectionTableMount table.wg-protection-table", timeout=15000)
                    page.wait_for_timeout(350)
                    return page

                def _verify_zoom_pan_cycle(page: Any, viewport_selector: str, mode_label: str) -> None:
                    # Ensure fit state initially
                    page.click("[data-wg-zoom='fit']")
                    page.wait_for_timeout(120)
                    st_fit = page.evaluate("() => window.wokwiDiagramZoom.getState()")
                    assert st_fit["mode"] == "fit", f"{mode_label}: expected fit mode, got {st_fit}"

                    # Zoom in (+)
                    page.click("[data-wg-zoom='in']")
                    page.wait_for_timeout(100)
                    st_in = page.evaluate("() => window.wokwiDiagramZoom.getState()")
                    assert st_in["scale"] > st_fit["scale"] + 0.05, (
                        f"{mode_label}: zoomIn did not increase scale ({st_fit['scale']} -> {st_in['scale']})"
                    )

                    # Zoom in once more so dragging has clear panning room
                    page.click("[data-wg-zoom='in']")
                    page.wait_for_timeout(100)
                    st_in2 = page.evaluate("() => window.wokwiDiagramZoom.getState()")
                    assert st_in2["scale"] > st_in["scale"]

                    # Zoom out (-)
                    page.click("[data-wg-zoom='out']")
                    page.wait_for_timeout(100)
                    st_out = page.evaluate("() => window.wokwiDiagramZoom.getState()")
                    assert st_out["scale"] < st_in2["scale"] - 0.05, (
                        f"{mode_label}: zoomOut did not decrease scale ({st_in2['scale']} -> {st_out['scale']})"
                    )

                    # Reset to 100%
                    page.click("[data-wg-zoom='reset']")
                    page.wait_for_timeout(100)
                    st_reset = page.evaluate("() => window.wokwiDiagramZoom.getState()")
                    assert abs(st_reset["scale"] - 1.0) < 0.01, f"{mode_label}: reset != 1.0: {st_reset}"
                    readout = page.locator("[data-wg-zoom-readout]").inner_text().strip()
                    assert readout == "100%", f"{mode_label}: expected '100%' readout, got {readout!r}"

                    # Mouse wheel zoom on viewport (ensure viewport is scrolled into view first)
                    vp_loc = page.locator(viewport_selector)
                    vp_loc.scroll_into_view_if_needed()
                    page.wait_for_timeout(80)
                    box = vp_loc.bounding_box()
                    assert box is not None and box["width"] > 100 and box["height"] > 100
                    cx = box["x"] + box["width"] * 0.5
                    cy = box["y"] + box["height"] * 0.5
                    page.mouse.move(cx, cy)
                    page.mouse.wheel(0, -180)
                    page.wait_for_timeout(120)
                    st_wheel = page.evaluate("() => window.wokwiDiagramZoom.getState()")
                    assert st_wheel["scale"] > st_reset["scale"] + 0.05, (
                        f"{mode_label}: wheel zoom did not increase scale ({st_reset['scale']} -> {st_wheel['scale']})"
                    )

                    # Drag/pan on viewport (using pointer events on a safe non-button region)
                    before_tx = st_wheel["tx"]
                    before_ty = st_wheel["ty"]
                    page.evaluate(
                        """(sel) => {
                            const el = document.querySelector(sel);
                            const r = el.getBoundingClientRect();
                            const sx = r.left + r.width * 0.5;
                            const sy = r.top + r.height * 0.5;
                            el.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true, pointerId:1, pointerType:'mouse', button:0, clientX:sx, clientY:sy}));
                            el.dispatchEvent(new PointerEvent('pointermove', {bubbles:true, pointerId:1, pointerType:'mouse', button:0, clientX:sx - 70, clientY:sy - 45}));
                            el.dispatchEvent(new PointerEvent('pointerup', {bubbles:true, pointerId:1, pointerType:'mouse', button:0, clientX:sx - 70, clientY:sy - 45}));
                        }""",
                        viewport_selector,
                    )
                    page.wait_for_timeout(120)
                    st_pan = page.evaluate("() => window.wokwiDiagramZoom.getState()")
                    moved = abs(st_pan["tx"] - before_tx) + abs(st_pan["ty"] - before_ty)
                    assert moved >= 15.0, f"{mode_label}: drag/pan did not move viewport (before=({before_tx},{before_ty}), after=({st_pan['tx']},{st_pan['ty']}))"

                    # Return to "Vừa màn hình" (fit)
                    page.click("[data-wg-zoom='fit']")
                    page.wait_for_timeout(100)
                    st_fit2 = page.evaluate("() => window.wokwiDiagramZoom.getState()")
                    assert st_fit2["mode"] == "fit"

                with sync_playwright() as p:
                    browser = _launch_headless_chromium(p)
                    try:
                        # --- DESKTOP 1366x768 (Light & Dark) ---
                        for scheme in ("light", "dark"):
                            ctx = browser.new_context(
                                viewport={"width": 1366, "height": 768},
                                user_agent=DESKTOP_UA,
                                color_scheme=scheme,
                            )
                            page = _login_and_open_wokwi(ctx, tokens["td_desk"])

                            # 0 horizontal overflow
                            overflow_x = page.evaluate(
                                "() => document.documentElement.scrollWidth > window.innerWidth + 1"
                            )
                            assert overflow_x is False, f"Desktop {scheme} /wokwi has horizontal overflow"

                            # Vietnamese-only labels on toolbar & zoom controls
                            toolbar_text = page.locator("#wokwiWiringToolbar").inner_text()
                            assert "Vừa màn hình" in toolbar_text
                            assert "Mạch Breadboard" in toolbar_text
                            assert "Sơ đồ PCB 2D" in toolbar_text
                            for forbidden_en in ("Zoom in", "Zoom out", "Fit to screen", "Reset zoom", "Hide wires"):
                                assert forbidden_en.lower() not in toolbar_text.lower()

                            # Protection card DOM parity: C1..C9, D1, D2, 1N4007
                            prot_text = page.locator("#wokwiProtectionCard").inner_text()
                            for tok in (*REQUIRED_PROTECTION_REFS, "1N4007"):
                                assert _has_token(prot_text, tok), f"#wokwiProtectionCard missing {tok}"

                            # Breadboard SVG/DOM markers for capacitors & diodes
                            bb_html = page.locator("#circuitStage").inner_html()
                            for tok in ("C4", "C5", "C6", "C9", "D2", "1N4007"):
                                assert _has_token(bb_html, tok), f"Breadboard stage missing marker {tok}"

                            # Breadboard zoom/pan cycle
                            _verify_zoom_pan_cycle(page, "#workbenchScroll", f"desktop-{scheme}-breadboard")

                            # Switch to PCB 2D mode
                            page.click("[data-wokwi-mode='pcb2d']")
                            page.wait_for_selector("#pcb2dSvgHost svg", state="visible", timeout=15000)
                            page.wait_for_timeout(250)

                            pcb_svg_html = page.locator("#pcb2dSvgHost").inner_html()
                            for tok in (*REQUIRED_PROTECTION_REFS, "1N4007"):
                                assert _has_token(pcb_svg_html, tok), f"PCB 2D SVG DOM missing {tok}"

                            # PCB 2D zoom/pan cycle
                            _verify_zoom_pan_cycle(page, "#pcb2dScroll", f"desktop-{scheme}-pcb2d")

                            ctx.close()

                        # --- MOBILE 412x915 (has_touch=True, Light & Dark) ---
                        for scheme in ("light", "dark"):
                            ctx_m = browser.new_context(
                                viewport={"width": 412, "height": 915},
                                has_touch=True,
                                is_mobile=True,
                                user_agent=MOBILE_UA,
                                color_scheme=scheme,
                            )
                            page_m = _login_and_open_wokwi(ctx_m, tokens["td_mob"])

                            overflow_m = page_m.evaluate(
                                "() => document.documentElement.scrollWidth > window.innerWidth + 1"
                            )
                            assert overflow_m is False, f"Mobile {scheme} /wokwi has horizontal overflow"

                            # All toolbar & zoom buttons >= 44x44 px on mobile
                            bad_btns = page_m.evaluate(
                                """() => {
                                    const bad = [];
                                    const nodes = document.querySelectorAll('#wokwiWiringToolbar button, #wokwiWiringToolbar select');
                                    for (const el of nodes) {
                                        const st = getComputedStyle(el);
                                        if (st.display === 'none' || st.visibility === 'hidden') continue;
                                        const r = el.getBoundingClientRect();
                                        if (r.width < 43.5 || r.height < 43.5) {
                                            bad.push({
                                                text: (el.innerText || el.getAttribute('aria-label') || '').trim(),
                                                cls: el.className,
                                                w: Math.round(r.width * 10) / 10,
                                                h: Math.round(r.height * 10) / 10,
                                            });
                                        }
                                    }
                                    return bad;
                                }"""
                            )
                            assert bad_btns == [], f"Mobile {scheme} toolbar/zoom controls < 44x44px: {bad_btns}"

                            # Breadboard zoom/pan cycle on mobile
                            _verify_zoom_pan_cycle(page_m, "#workbenchScroll", f"mobile-{scheme}-breadboard")

                            # Switch to PCB 2D mode on mobile & verify zoom/pan + 0 overflow
                            page_m.click("[data-wokwi-mode='pcb2d']")
                            page_m.wait_for_selector("#pcb2dSvgHost svg", state="visible", timeout=15000)
                            page_m.wait_for_timeout(250)
                            overflow_m_pcb = page_m.evaluate(
                                "() => document.documentElement.scrollWidth > window.innerWidth + 1"
                            )
                            assert overflow_m_pcb is False, f"Mobile {scheme} /wokwi PCB 2D has horizontal overflow"
                            _verify_zoom_pan_cycle(page_m, "#pcb2dScroll", f"mobile-{scheme}-pcb2d")

                            ctx_m.close()
                    finally:
                        browser.close()
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
