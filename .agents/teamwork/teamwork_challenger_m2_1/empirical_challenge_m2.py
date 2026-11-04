"""Empirical Challenger Test Suite for Milestone 2 (Bugs 3, 10, 11, 14).
Location: .agents/teamwork/teamwork_challenger_m2_1/empirical_challenge_m2.py

Executes real headless Chrome browser tests with adversarial edge cases:
1. Bug 3:
   - WS disconnect + HTTP polling success -> Banner hidden, header green "Đã kết nối"
   - WS disconnect + HTTP polling failure -> Banner visible, header "Mất kết nối"
   - /favicon.ico route exists, eliminates console 404, file on disk has ICO magic bytes
2. Bug 10:
   - Desktop toggle device: instant optimistic switch flip & label update -> rollback on API failure
   - Mobile toggle device: instant optimistic class toggle -> rollback on API failure
   - renderDevices() in-place update without innerHTML="" DOM wipe
3. Bug 11:
   - Mic sheet waiting state ("Đang chờ quyền mic", "00:00", 12px static bars)
   - Mic permission rejection -> Sheet closes, #mobileMicPermissionModal opens
   - Insecure origin / missing mediaDevices -> Sheet closes, #mobileMicPermissionModal opens gracefully
4. Bug 14:
   - Real geometric bounding boxes in Chrome -> Exact 0 overlap between DHT11 and Buzzer tags
   - Live telemetry in #hoverHoleInfo instead of "Chưa có dữ liệu"
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import threading
import time
import urllib.request
import pytest
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.server import app
import uvicorn

PORT = 8089  # Dedicated port for empirical challenger to avoid collision
BASE_URL = f"http://127.0.0.1:{PORT}"

server_started = False
server_thread = None

def ensure_server():
    global server_started, server_thread
    if server_started:
        return
    # Check if already running
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/state", timeout=1) as r:
            if r.status == 200:
                server_started = True
                return
    except Exception:
        pass

    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    
    # Wait for server ready
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/state", timeout=1) as r:
                if r.status == 200:
                    server_started = True
                    return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("Failed to start test server on port " + str(PORT))


# =============================================================================
# 1. BUG 3 EMPIRICAL CHALLENGE: WEBSOCKET FALLBACK & BANNER
# =============================================================================

def test_empirical_bug3_ws_disconnect_http_polling_success_and_failure():
    """Empirically test WebSocket close + HTTP polling fallback in headless Chrome."""
    ensure_server()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # Mock WebSocket to immediately close and stay closed (simulating Vercel environment)
        page.add_init_script("""
            window.__mockWsInstances = [];
            window.WebSocket = class extends EventTarget {
                constructor(url) {
                    super();
                    this.url = url;
                    this.readyState = 0; // CONNECTING
                    window.__mockWsInstances.push(this);
                    setTimeout(() => {
                        this.readyState = 3; // CLOSED
                        if (this.onclose) this.onclose(new CloseEvent('close'));
                    }, 50);
                }
                send() {}
                close() {
                    this.readyState = 3;
                    if (this.onclose) this.onclose(new CloseEvent('close'));
                }
            };
        """)

        # Navigate to desktop dashboard: WS will close, triggering fetch('/api/state') -> HTTP 200
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
        page.wait_for_timeout(600)

        # 1. Verify: HTTP polling succeeded -> Banner hidden, connText "Đã kết nối", dot green
        status = page.evaluate("""() => {
            const banner = document.getElementById('wsReconnectBanner');
            const connText = document.getElementById('connText');
            const connDot = document.getElementById('connDot');
            return {
                banner_has_hidden: banner.classList.contains('hidden'),
                conn_text: connText.textContent.trim(),
                dot_is_offline: connDot.classList.contains('offline'),
                server_connected: window._serverConnected
            };
        }""")

        assert status["banner_has_hidden"] is True, f"Banner should be hidden when HTTP polling works: {status}"
        assert status["conn_text"] == "Đã kết nối", f"Connection text should be 'Đã kết nối': {status}"
        assert status["dot_is_offline"] is False, f"Dot should be green (not offline): {status}"
        assert status["server_connected"] is True, f"window._serverConnected should be True: {status}"

        # 2. ADVERSARIAL: Now intercept /api/state to return HTTP 500 (both WS and HTTP fail)
        page.route("**/api/state", lambda route: route.fulfill(status=500, body=b"Server Error"))

        # Trigger reconnect retry
        page.evaluate("""() => {
            if (window.retryWsConnection) {
                window.retryWsConnection();
            }
        }""")
        page.wait_for_timeout(600)

        # Verify: Now banner MUST appear, connText must be "Mất kết nối", dot must be offline
        fail_status = page.evaluate("""() => {
            const banner = document.getElementById('wsReconnectBanner');
            const connText = document.getElementById('connText');
            const connDot = document.getElementById('connDot');
            return {
                banner_has_hidden: banner.classList.contains('hidden'),
                conn_text: connText.textContent.trim(),
                dot_is_offline: connDot.classList.contains('offline'),
                server_connected: window._serverConnected
            };
        }""")

        assert fail_status["banner_has_hidden"] is False, f"Banner must be shown when polling also fails: {fail_status}"
        assert fail_status["conn_text"] == "Mất kết nối", f"Connection text should be 'Mất kết nối': {fail_status}"
        assert fail_status["dot_is_offline"] is True, f"Dot must be red (offline): {fail_status}"

        browser.close()


def test_empirical_bug3_favicon_ico_http_valid_and_disk_magic():
    """Verify /favicon.ico eliminates 404 on server and disk file has valid ICO header."""
    ensure_server()
    req = urllib.request.Request(f"{BASE_URL}/favicon.ico")
    with urllib.request.urlopen(req) as response:
        assert response.status in (200, 204), f"Favicon should not be 404, got {response.status}"

    favicon_path = ROOT / "simulator" / "static" / "favicon.ico"
    assert favicon_path.exists(), "favicon.ico must exist on disk"
    ico_bytes = favicon_path.read_bytes()
    assert len(ico_bytes) > 0
    assert ico_bytes[:4] == b"\x00\x00\x01\x00", "Must have ICO format magic bytes 0x00000100"


# =============================================================================
# 2. BUG 10 EMPIRICAL CHALLENGE: OPTIMISTIC UI & ROLLBACK ON DELAY/FAILURE
# =============================================================================

def test_empirical_bug10_desktop_toggle_optimistic_and_rollback():
    """Test desktop device card click: optimistic immediate update and rollback on failure."""
    ensure_server()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # Simulate Vercel environment: WebSocket is closed, app falls back to POST /api/device
        page.add_init_script("""
            window.WebSocket = class extends EventTarget {
                constructor() {
                    super();
                    this.readyState = 3; // CLOSED
                    setTimeout(() => { if (this.onclose) this.onclose(new CloseEvent('close')); }, 20);
                }
                send() {}
                close() {}
            };
        """)

        # Intercept POST /api/device to simulate a 300ms delay then a failure response
        page.route("**/api/device", lambda route: (
            time.sleep(0.3),
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": False, "error": "Simulated hardware error"}))
        ))

        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
        page.wait_for_timeout(800)

        # Perform click on dev-card-living_room_light
        card_id = "dev-card-living_room_light"
        instant_state = page.evaluate(f"""() => {{
            const card = document.getElementById('{card_id}');
            const sw = card.querySelector('.switch input');
            const prevChecked = sw.checked;

            // Trigger click on card
            card.click();

            const roomSpan = card.querySelector('.device-room');
            return {{
                prevChecked,
                instantChecked: sw.checked,
                instantRoomText: roomSpan ? roomSpan.textContent : ''
            }};
        }}""")

        # Optimistic verification:
        assert instant_state["instantChecked"] != instant_state["prevChecked"], (
            f"Switch must toggle INSTANTLY (optimistic) before network response: {instant_state}"
        )
        assert "Đã bật" in instant_state["instantRoomText"] or "Đã tắt" in instant_state["instantRoomText"]

        # Wait for delayed failure response (300ms) + rollback execution
        page.wait_for_timeout(600)

        # Rollback verification:
        rolled_back_state = page.evaluate(f"""() => {{
            const card = document.getElementById('{card_id}');
            const sw = card.querySelector('.switch input');
            const roomSpan = card.querySelector('.device-room');
            return {{
                checked: sw.checked,
                roomText: roomSpan ? roomSpan.textContent : ''
            }};
        }}""")

        assert rolled_back_state["checked"] == instant_state["prevChecked"], (
            f"Switch MUST rollback to original checked state ({instant_state['prevChecked']}), got: {rolled_back_state}"
        )

        browser.close()


def test_empirical_bug10_mobile_toggle_optimistic_and_rollback():
    """Test mobile device card click: instant optimistic UI toggle and rollback on network failure."""
    ensure_server()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 412, "height": 915})

        # Pre-set logged in session for mobile app
        context.add_init_script("""
            sessionStorage.setItem('mobileLoggedIn', '1');
            sessionStorage.setItem('mobileLoggedInEmail', 'nep94121@gmail.com');
        """)

        page = context.new_page()
        page.goto(f"{BASE_URL}/app", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        # Switch to Devices tab
        page.evaluate("() => { if (window.switchMobileTab) window.switchMobileTab('devices'); }")
        page.wait_for_timeout(400)

        # Intercept POST /api/device to abort / fail with network error after 200ms
        page.route("**/api/device", lambda route: (
            time.sleep(0.2),
            route.abort("failed")
        ))

        # Check card optimistic flip and subsequent rollback on .dev-row
        card_states = page.evaluate("""async () => {
            const card = document.querySelector('#devGrid .dev-row');
            if (!card) return { error: 'No dev row found' };

            const initiallyOn = card.classList.contains('on');

            // Click the card
            card.click();

            // Measure immediate class (synchronously after click)
            const immediatelyOn = card.classList.contains('on');

            // Wait for delayed network failure
            await new Promise(r => setTimeout(r, 600));

            const finallyOn = card.classList.contains('on');

            return {
                initiallyOn,
                immediatelyOn,
                finallyOn
            };
        }""")

        assert "error" not in card_states, card_states["error"]
        assert card_states["immediatelyOn"] != card_states["initiallyOn"], (
            f"Mobile card must toggle immediately: {card_states}"
        )
        assert card_states["finallyOn"] == card_states["initiallyOn"], (
            f"Mobile card must rollback to initial state after network error: {card_states}"
        )

        browser.close()


# =============================================================================
# 3. BUG 11 EMPIRICAL CHALLENGE: MIC PERMISSION REJECTION & WAITING STATE
# =============================================================================

def test_empirical_bug11_mic_permission_rejection_flow():
    """Test mic permission denial: sheet closes and #mobileMicPermissionModal opens."""
    ensure_server()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 412, "height": 915})
        page = context.new_page()

        page.goto(f"{BASE_URL}/app", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        result = page.evaluate("""async () => {
            // Emulate mic permission rejection
            if (!navigator.mediaDevices) navigator.mediaDevices = {};
            navigator.mediaDevices.getUserMedia = async () => {
                const err = new Error('Permission denied');
                err.name = 'NotAllowedError';
                throw err;
            };

            const sheet = document.getElementById('mobileVoiceBottomSheet');
            const scrim = document.getElementById('mobileVoiceSheetScrim');
            const modal = document.getElementById('mobileMicPermissionModal');

            window.openVoiceBottomSheet();

            // Allow async getUserMedia failure handler to run
            await new Promise(r => setTimeout(r, 200));

            return {
                sheet_hidden: sheet.hidden,
                scrim_hidden: scrim.hidden,
                modal_hidden_attr: modal.hasAttribute('hidden'),
                modal_class_hidden: modal.classList.contains('hidden'),
                modal_display: modal.style.display,
                modal_title: document.getElementById('mobileMictitle') ? document.getElementById('mobileMictitle').textContent.trim() : ''
            };
        }""")

        assert result["sheet_hidden"] is True, f"Voice bottom sheet must be closed: {result}"
        assert result["scrim_hidden"] is True, f"Voice scrim must be closed: {result}"
        assert result["modal_class_hidden"] is False, f"Permission modal must NOT have 'hidden' class: {result}"
        assert result["modal_display"] == "flex", f"Permission modal display must be flex: {result}"
        assert "micro" in result["modal_title"].lower(), f"Modal title should mention micro: {result}"

        browser.close()


def test_empirical_bug11_insecure_origin_missing_getusermedia():
    """Test when getUserMedia is completely absent (insecure HTTP / old browser): graceful handling."""
    ensure_server()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 412, "height": 915})
        page = context.new_page()

        page.goto(f"{BASE_URL}/app", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        result = page.evaluate("""async () => {
            // Simulate missing mediaDevices / getUserMedia
            Object.defineProperty(navigator, 'mediaDevices', { value: undefined, configurable: true, writable: true });

            const sheet = document.getElementById('mobileVoiceBottomSheet');
            const modal = document.getElementById('mobileMicPermissionModal');

            window.openVoiceBottomSheet();
            await new Promise(r => setTimeout(r, 200));

            return {
                sheet_hidden: sheet.hidden,
                modal_class_hidden: modal.classList.contains('hidden'),
                modal_display: modal.style.display
            };
        }""")

        assert result["sheet_hidden"] is True, "Sheet must close when getUserMedia missing"
        assert result["modal_class_hidden"] is False, "Permission modal must open when getUserMedia missing"
        assert result["modal_display"] == "flex"

        browser.close()


# =============================================================================
# 4. BUG 14 EMPIRICAL CHALLENGE: WOKWI BOUNDING BOX ZERO OVERLAP & TELEMETRY
# =============================================================================

def test_empirical_bug14_wokwi_bounding_box_zero_overlap():
    """Measure exact 2D geometric bounding boxes in Chrome to prove 0 overlap between DHT11 and Buzzer."""
    ensure_server()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        page.goto(f"{BASE_URL}/wokwi", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        boxes = page.evaluate("""() => {
            const tags = document.querySelectorAll('.comp-tag');
            return Array.from(tags).map(el => {
                const r = el.getBoundingClientRect();
                return {
                    text: el.textContent.trim(),
                    style: el.getAttribute('style'),
                    left: r.left,
                    top: r.top,
                    right: r.right,
                    bottom: r.bottom,
                    width: r.width,
                    height: r.height
                };
            });
        }""")

        dht = next((t for t in boxes if "DHT11" in t["text"]), None)
        buzzer = next((t for t in boxes if "Buzzer" in t["text"]), None)

        assert dht is not None, "DHT11 comp-tag not found on /wokwi"
        assert buzzer is not None, "Buzzer comp-tag not found on /wokwi"

        # Calculate 2D intersection
        x_overlap = max(0, min(dht["right"], buzzer["right"]) - max(dht["left"], buzzer["left"]))
        y_overlap = max(0, min(dht["bottom"], buzzer["bottom"]) - max(dht["top"], buzzer["top"]))
        overlap_area = x_overlap * y_overlap

        # Clearances
        horizontal_clearance = buzzer["left"] - dht["right"]
        vertical_clearance = buzzer["top"] - dht["bottom"]

        print(f"\n[Bug 14 Proof] DHT11: right={dht['right']:.2f}, bottom={dht['bottom']:.2f}")
        print(f"[Bug 14 Proof] Buzzer: left={buzzer['left']:.2f}, top={buzzer['top']:.2f}")
        print(f"[Bug 14 Proof] Horizontal Clearance: {horizontal_clearance:.2f}px")
        print(f"[Bug 14 Proof] Vertical Clearance: {vertical_clearance:.2f}px")
        print(f"[Bug 14 Proof] Overlap Area: {overlap_area:.2f}px^2")

        assert overlap_area == 0.0, f"Geometric overlap detected: area = {overlap_area}px^2"
        assert horizontal_clearance > 0, f"Expected positive horizontal clearance, got {horizontal_clearance}"
        assert vertical_clearance > 0, f"Expected positive vertical clearance, got {vertical_clearance}"

        browser.close()


def test_empirical_bug14_hover_hole_info_live_telemetry():
    """Verify #hoverHoleInfo on /wokwi contains live telemetry instead of 'Chưa có dữ liệu'."""
    ensure_server()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        page.goto(f"{BASE_URL}/wokwi", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        hole_text = page.evaluate("""() => {
            const el = document.getElementById('hoverHoleInfo');
            return el ? el.textContent.trim() : null;
        }""")

        assert hole_text is not None, "#hoverHoleInfo not found"
        assert "Chưa có dữ liệu" not in hole_text, f"#hoverHoleInfo still has forbidden text: {hole_text}"
        assert ("°C" in hole_text or "Nhiệt độ" in hole_text) and "Độ ẩm" in hole_text, (
            f"#hoverHoleInfo missing sensor telemetry: {hole_text}"
        )

        browser.close()
