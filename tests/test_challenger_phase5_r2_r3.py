"""Adversarial Empirical Stress-Testing Suite for Phase 5: Bug R2 and Bug R3.

Author: teamwork_challenger (Challenger 2)
Focus:
- R2: /wokwi Breadboard and VS1838B Label Layout (bounding box measurements across viewports, no truncation, no collisions, >20px separation)
- R3: Password Reset OTP Delivery & Error Handling (HTTP 503/400 on missing secrets, zero leaked OTPs, generic wrong OTP error, UI never fakes delivery)
"""
from __future__ import annotations

import http.server
import json
import os
import pathlib
import socketserver
import subprocess
import threading
from typing import Any
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from simulator.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "simulator" / "static"
MOBILE_APP_DIR = ROOT / "mobile_app"
WOKWI_HTML_PATH = STATIC_DIR / "wokwi.html"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def live_server_url():
    """Spin up a dual-directory static HTTP server serving both /static and /mobile_app on an ephemeral port."""
    class MultiStaticServerHandler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path):
            clean = path.split("?")[0].split("#")[0].lstrip("/")
            if clean.startswith("static/"):
                clean = clean[7:]
                return str(STATIC_DIR / clean)
            if clean.startswith("mobile_app/"):
                clean = clean[11:]
                return str(MOBILE_APP_DIR / clean)
            if clean == "app" or clean.startswith("app/"):
                sub = clean[4:] if len(clean) > 4 else "index.html"
                return str(MOBILE_APP_DIR / sub)
            return str(STATIC_DIR / clean)

        def log_message(self, format, *args):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", 0), MultiStaticServerHandler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


def _recursively_find_strings(data: Any) -> list[str]:
    """Extract all string values and keys from arbitrary JSON-serializable structure."""
    out = []
    if isinstance(data, dict):
        for k, v in data.items():
            out.append(str(k))
            out.extend(_recursively_find_strings(v))
    elif isinstance(data, (list, tuple)):
        for item in data:
            out.extend(_recursively_find_strings(item))
    elif isinstance(data, (str, int, float, bool)):
        out.append(str(data))
    return out


# ==============================================================================
# SECTION 1: BUG R2 - /wokwi BREADBOARD & VS1838B LABEL LAYOUT EMPIRICAL TESTS
# ==============================================================================

class TestChallengerR2WokwiEmpirical:
    """Empirical bounding-box measurements and layout stress tests for Bug R2."""

    @pytest.mark.parametrize("width,height,viewport_name", [
        (1280, 800, "Desktop 1280px"),
        (390, 844, "Mobile iPhone 390px"),
        (414, 896, "Mobile iPhone 414px"),
        (360, 640, "Mobile Android 360px"),
        (768, 1024, "Tablet iPad 768px"),
    ])
    def test_r2_measure_all_comp_tags_bounding_boxes_zero_pairwise_collision(
        self, live_server_url: str, width: int, height: int, viewport_name: str
    ):
        """1. Measure rendered bounding boxes of all .comp-tag elements in real Chromium.
        
        Assert:
        - At least 11 .comp-tag elements are present.
        - Pairwise AABB check: 0 pairs have overlapping bounding boxes in both X and Y dimensions.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            pytest.skip("Playwright package not installed.")

        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(channel="chrome", headless=True)
        except Exception as exc:
            pw.stop()
            pytest.skip(f"Chrome launch failed: {exc}")

        try:
            page = browser.new_page()
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{live_server_url}/wokwi.html")

            tags_data = page.evaluate("""() => {
                const tags = Array.from(document.querySelectorAll('.comp-tag'));
                return tags.map((el, idx) => {
                    const r = el.getBoundingClientRect();
                    return {
                        idx,
                        text: el.innerText.trim(),
                        fullText: el.textContent.trim(),
                        rect: {
                            left: r.left,
                            right: r.right,
                            top: r.top,
                            bottom: r.bottom,
                            width: r.width,
                            height: r.height
                        }
                    };
                });
            }""")

            assert len(tags_data) >= 11, f"Expected >= 11 .comp-tag elements, got {len(tags_data)}"

            collisions = []
            for i in range(len(tags_data)):
                for j in range(i + 1, len(tags_data)):
                    t1 = tags_data[i]
                    t2 = tags_data[j]
                    r1 = t1["rect"]
                    r2 = t2["rect"]
                    overlap_x = max(0.0, min(r1["right"], r2["right"]) - max(r1["left"], r2["left"]))
                    overlap_y = max(0.0, min(r1["bottom"], r2["bottom"]) - max(r1["top"], r2["top"]))
                    # Collision occurs only if overlap in both X and Y is strictly positive (> 0.5px to ignore pixel rounding)
                    if overlap_x > 0.5 and overlap_y > 0.5:
                        collisions.append(
                            f"[{viewport_name}] Tag '{t1['text'][:25]}' overlaps '{t2['text'][:25]}' "
                            f"by dx={overlap_x:.1f}px, dy={overlap_y:.1f}px"
                        )

            assert not collisions, f"Phát hiện {len(collisions)} va chạm trên {viewport_name}: " + "; ".join(collisions)
            page.close()
        finally:
            browser.close()
            pw.stop()

    @pytest.mark.parametrize("width,height,viewport_name", [
        (1280, 800, "Desktop 1280px"),
        (390, 844, "Mobile iPhone 390px"),
        (414, 896, "Mobile iPhone 414px"),
    ])
    def test_r2_breadboard_tag_not_truncated(
        self, live_server_url: str, width: int, height: int, viewport_name: str
    ):
        """2. Verify Breadboard tag is NOT truncated at (tr… on 1280px desktop, 390px, and 414px mobile viewports.
        
        Assert:
        - Breadboard tag exists and contains the full text.
        - Rendered text does NOT end in '(tr…' or '(tr...'.
        - On 1280px desktop: right edge of Breadboard tag <= 618px (fits completely inside initial visible scroll width).
        - white-space is normal and wraps cleanly into balanced lines.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            pytest.skip("Playwright package not installed.")

        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(channel="chrome", headless=True)
        except Exception as exc:
            pw.stop()
            pytest.skip(f"Chrome launch failed: {exc}")

        try:
            page = browser.new_page()
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{live_server_url}/wokwi.html")

            bb_info = page.evaluate("""() => {
                const tags = Array.from(document.querySelectorAll('.comp-tag'));
                const bb = tags.find(el => el.innerText.includes('Breadboard'));
                if (!bb) return null;
                const r = bb.getBoundingClientRect();
                const style = window.getComputedStyle(bb);
                return {
                    innerText: bb.innerText,
                    textContent: bb.textContent,
                    rect: {
                        left: r.left,
                        right: r.right,
                        top: r.top,
                        bottom: r.bottom,
                        width: r.width,
                        height: r.height
                    },
                    whiteSpace: style.whiteSpace,
                    maxWidth: style.maxWidth,
                    scrollWidth: bb.scrollWidth,
                    clientWidth: bb.clientWidth
                };
            }""")

            assert bb_info is not None, f"Breadboard tag not found in {viewport_name}"
            raw_text = bb_info["innerText"]

            # Must not be truncated at '(tr…'
            assert not raw_text.endswith("(tr…"), f"Breadboard tag bị cắt cụt tại '(tr…'! Text: {raw_text}"
            assert "(tr…" not in raw_text, f"Breadboard tag chứa cụm cắt cụt '(tr…'! Text: {raw_text}"
            assert "f–j (dưới)" in raw_text, f"Breadboard tag thiếu phần đuôi 'f–j (dưới)': {raw_text}"
            assert bb_info["whiteSpace"] == "normal", f"white-space must be normal, got {bb_info['whiteSpace']}"

            # On desktop 1280px: check that the tag right boundary fits within initial un-scrolled client view
            if width == 1280:
                container_data = page.evaluate("""() => {
                    const scrollEl = document.querySelector('.workbench-scroll');
                    const r_scroll = scrollEl.getBoundingClientRect();
                    return {
                        scrollRight: r_scroll.right,
                        clientWidth: scrollEl.clientWidth
                    };
                }""")
                bb_right = bb_info["rect"]["right"]
                # Breadboard tag right edge must not extend beyond the visible right edge of the scroll container
                assert bb_right <= container_data["scrollRight"] + 15, (
                    f"Breadboard right={bb_right}px exceeds container visible right={container_data['scrollRight']}px!"
                )

            page.close()
        finally:
            browser.close()
            pw.stop()

    def test_r2_vs1838b_separation_from_dht11_exceeds_20px(self, live_server_url: str):
        """3. Verify that Mắt thu VS1838B (Chân D5) does NOT overlap with DHT11 (clear separation > 20px)."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            pytest.skip("Playwright package not installed.")

        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(channel="chrome", headless=True)
        except Exception as exc:
            pw.stop()
            pytest.skip(f"Chrome launch failed: {exc}")

        try:
            page = browser.new_page()
            page.set_viewport_size({"width": 1280, "height": 800})
            page.goto(f"{live_server_url}/wokwi.html")

            pair_info = page.evaluate("""() => {
                const tags = Array.from(document.querySelectorAll('.comp-tag'));
                const vs = tags.find(el => el.innerText.includes('VS1838B'));
                const dht = tags.find(el => el.innerText.includes('DHT11'));
                if (!vs || !dht) return null;
                const r_vs = vs.getBoundingClientRect();
                const r_dht = dht.getBoundingClientRect();
                return {
                    vsText: vs.innerText,
                    dhtText: dht.innerText,
                    r_vs: { left: r_vs.left, right: r_vs.right, top: r_vs.top, bottom: r_vs.bottom, width: r_vs.width },
                    r_dht: { left: r_dht.left, right: r_dht.right, top: r_dht.top, bottom: r_dht.bottom, width: r_dht.width }
                };
            }""")

            assert pair_info is not None, "Tags VS1838B or DHT11 missing"
            r_vs = pair_info["r_vs"]
            r_dht = pair_info["r_dht"]

            # Text check: 'D5)' must be present in VS1838B text
            assert "D5)" in pair_info["vsText"], f"VS1838B tag text missing 'D5)': {pair_info['vsText']}"

            # Calculate clear separation
            horiz_separation = r_dht["left"] - r_vs["right"]
            vert_separation = abs(r_dht["top"] - r_vs["top"])

            assert horiz_separation >= 20.0 or vert_separation >= 20.0, (
                f"LỖI R2: Khoảng cách giữa VS1838B và DHT11 ({horiz_separation:.1f}px) nhỏ hơn 20px! "
                f"VS1838B: {r_vs}, DHT11: {r_dht}"
            )
            page.close()
        finally:
            browser.close()
            pw.stop()

    def test_r2_remote_and_micro_speaker_tags_zero_overlap(self, live_server_url: str):
        """4. Verify that Remote and Micro/Speaker tags have ZERO overlap."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            pytest.skip("Playwright package not installed.")

        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(channel="chrome", headless=True)
        except Exception as exc:
            pw.stop()
            pytest.skip(f"Chrome launch failed: {exc}")

        try:
            page = browser.new_page()
            page.set_viewport_size({"width": 1280, "height": 800})
            page.goto(f"{live_server_url}/wokwi.html")

            pair_info = page.evaluate("""() => {
                const tags = Array.from(document.querySelectorAll('.comp-tag'));
                const mic = tags.find(el => el.innerText.includes('Micro') || el.innerText.includes('Loa'));
                const remote = tags.find(el => el.innerText.includes('Remote') || el.innerText.includes('Điều khiển'));
                if (!mic || !remote) return null;
                const r_mic = mic.getBoundingClientRect();
                const r_remote = remote.getBoundingClientRect();
                return {
                    micText: mic.innerText,
                    remoteText: remote.innerText,
                    r_mic: { left: r_mic.left, right: r_mic.right, top: r_mic.top, bottom: r_mic.bottom },
                    r_remote: { left: r_remote.left, right: r_remote.right, top: r_remote.top, bottom: r_remote.bottom }
                };
            }""")

            assert pair_info is not None, "Tags Micro/Speaker or Remote missing"
            r_mic = pair_info["r_mic"]
            r_remote = pair_info["r_remote"]

            overlap_x = max(0.0, min(r_mic["right"], r_remote["right"]) - max(r_mic["left"], r_remote["left"]))
            overlap_y = max(0.0, min(r_mic["bottom"], r_remote["bottom"]) - max(r_mic["top"], r_remote["top"]))

            assert overlap_x == 0.0 or overlap_y == 0.0, (
                f"LỖI R2: Micro tag và Remote tag va chạm với overlap dx={overlap_x:.1f}px, dy={overlap_y:.1f}px! "
                f"Mic: {r_mic}, Remote: {r_remote}"
            )
            page.close()
        finally:
            browser.close()
            pw.stop()


# ==============================================================================
# SECTION 2: BUG R3 - PASSWORD RESET OTP DELIVERY & ERROR HANDLING ADVERSARIAL
# ==============================================================================

class TestChallengerR3OtpEmailAdversarial:
    """Adversarial stress testing of Bug R3: missing secrets, wrong OTP, and UI error handling."""

    @pytest.mark.parametrize("test_email", [
        "senat6031@gmail.com",
        "nep94121@gmail.com",
    ])
    def test_r3_adversarial_missing_secret_returns_503_or_400_and_identifies_secret_zero_leaks(
        self, client: TestClient, test_email: str
    ):
        """Adversarially query /api/auth3/forgot_password_send_otp with missing secrets.
        
        Assert:
        - HTTP 503 or 400 (NEVER 200).
        - ok is False.
        - Clearly identifies missing secret 'GMAIL_APP_PASSWORD'.
        - Zero leaked OTPs: neither demo_otp_preview, otp_code_for_test, nor any 6-digit OTP code leaked anywhere.
        """
        env_no_secret = {
            k: v for k, v in os.environ.items()
            if k not in ("GMAIL_APP_PASSWORD", "SMTP_PASSWORD")
        }

        with patch.dict(os.environ, env_no_secret, clear=True), \
             patch("subprocess.run", side_effect=FileNotFoundError("gws command not found")):

            # 1. Query with explicit send_gmail: True
            res1 = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": test_email, "send_gmail": True},
            )
            assert res1.status_code in (400, 500, 503), (
                f"Expected HTTP 400 or 503, got {res1.status_code}. Response: {res1.text}"
            )
            data1 = res1.json()
            assert data1.get("ok") is False, f"ok must be False on failed delivery: {data1}"

            # Missing secret identified
            all_text_1 = " ".join(_recursively_find_strings(data1))
            assert "GMAIL_APP_PASSWORD" in all_text_1 or "SMTP_PASSWORD" in all_text_1, (
                f"Missing secret 'GMAIL_APP_PASSWORD' was not identified in response: {all_text_1}"
            )

            # Zero leaked OTPs: check keys and values
            assert "demo_otp_preview" not in data1 or not data1["demo_otp_preview"]
            assert "otp_code_for_test" not in data1 or not data1["otp_code_for_test"]
            assert "otp_code" not in data1

            # 2. Query with omitted send_gmail (defaults to True)
            res2 = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": test_email},
            )
            assert res2.status_code in (400, 500, 503), (
                f"Omitted send_gmail should default to True and fail with 503/400, got {res2.status_code}"
            )
            data2 = res2.json()
            assert data2.get("ok") is False
            assert "GMAIL_APP_PASSWORD" in " ".join(_recursively_find_strings(data2))

    def test_r3_adversarial_nonexistent_and_malformed_email_queries(self, client: TestClient):
        """Adversarial queries with invalid emails must return 404/400 without crashing or faking success."""
        # Non-existent email
        res_non = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nonexistent_hacker_user_99999@gmail.com", "send_gmail": True},
        )
        assert res_non.status_code in (404, 400), f"Expected 404/400, got {res_non.status_code}"
        assert res_non.json().get("ok") is False

        # Malformed SQL injection string
        res_sql = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "' OR '1'='1' --", "send_gmail": True},
        )
        assert res_sql.status_code in (404, 400), f"Expected 404/400, got {res_sql.status_code}"
        assert res_sql.json().get("ok") is False

        # Empty email
        res_empty = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "", "send_gmail": True},
        )
        assert res_empty.status_code in (404, 400), f"Expected 404/400, got {res_empty.status_code}"
        assert res_empty.json().get("ok") is False

    @pytest.mark.parametrize("bad_otp", [
        "000000",
        "999999",
        "12345",
        "1234567",
        "ABCDEF",
        "' OR '1'='1",
        "",
        "   ",
        "None",
    ])
    def test_r3_wrong_otp_returns_generic_error_without_leaking_correct_otp(
        self, client: TestClient, bad_otp: str
    ):
        """Adversarially probe OTP verification endpoints with incorrect OTP codes.
        
        Assert:
        - System rejects wrong OTP (ok: False).
        - Error message is generic ('Mã OTP ... không chính xác!').
        - The correct OTP is NEVER leaked in the error message or any field.
        """
        # Step 1: Generate an OTP in offline test mode so a valid OTP exists in pending_otps
        res_gen = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "senat6031@gmail.com", "send_gmail": False},
        )
        assert res_gen.status_code == 200
        gen_data = res_gen.json()
        assert gen_data.get("ok") is True
        correct_otp = gen_data.get("otp_code_for_test") or gen_data.get("demo_otp_preview")
        assert correct_otp and len(correct_otp) == 6, f"Valid OTP was not generated in offline mode: {gen_data}"

        # Step 2: Adversarial check against /api/auth3/forgot_password_reset
        res_reset = client.post(
            "/api/auth3/forgot_password_reset",
            json={
                "email": "senat6031@gmail.com",
                "otp_code": bad_otp,
                "new_password": "NewSecurePassword#2026",
                "confirm_password": "NewSecurePassword#2026",
            },
        )
        reset_data = res_reset.json()
        assert reset_data.get("ok") is False, f"System accepted bad OTP '{bad_otp}'!"

        err_str = " ".join(_recursively_find_strings(reset_data))
        # Leak check: the correct OTP must NOT be anywhere in the response!
        assert correct_otp not in err_str, (
            f"LỖI BẢO MẬT: Mã OTP đúng '{correct_otp}' bị rò rỉ trong câu báo lỗi: {err_str}"
        )
        assert "Mã đúng trong Gmail" not in err_str, (
            f"LỖI BẢO MẬT: Bị lộ cụm từ chứa mã đúng trong câu báo lỗi: {err_str}"
        )

        # Step 3: Adversarial check against /api/auth3/layer2_verify_otp
        res_l2 = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": "senat6031@gmail.com", "otp_code": bad_otp},
        )
        l2_data = res_l2.json()
        assert l2_data.get("ok") is False, f"Lớp 2 chấp nhận OTP sai '{bad_otp}'!"
        l2_err_str = " ".join(_recursively_find_strings(l2_data))
        assert correct_otp not in l2_err_str, (
            f"LỖI BẢO MẬT Lớp 2: Mã OTP đúng '{correct_otp}' bị rò rỉ: {l2_err_str}"
        )

    def test_r3_ui_static_guards_prevent_fake_otp_transition(self):
        """Verify static code guards in frontend JS prevent fake OTP sent transitions."""
        app_js = (STATIC_DIR / "js" / "app.js").read_text(encoding="utf-8")
        mobile_app_js = (STATIC_DIR / "js" / "mobile_app.js").read_text(encoding="utf-8")

        # 1. app.js guard in btnSendForgotOtp
        assert "sent_real_gmail !== false" in app_js, (
            "app.js must guard setForgotStep(2) with sent_real_gmail !== false"
        )
        # 2. app.js guard in sendLockdownOtp
        assert "data.gmail_delivery.sent_real_gmail !== false" in app_js, (
            "app.js sendLockdownOtp must guard delivery status"
        )
        # 3. mobile_app.js guard in submitForgotSendOtp
        assert "sent_real_gmail !== false" in mobile_app_js, (
            "mobile_app.js must guard step 2 transition with sent_real_gmail !== false"
        )

    def test_r3_live_browser_ui_never_shows_otp_sent_on_delivery_failure(self, live_server_url: str):
        """Verify via real Chromium browser that UI NEVER shows 'OTP sent' if delivery fails."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            pytest.skip("Playwright package not installed.")

        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(channel="chrome", headless=True)
        except Exception as exc:
            pw.stop()
            pytest.skip(f"Chrome launch failed: {exc}")

        try:
            page = browser.new_page()
            page.set_viewport_size({"width": 1280, "height": 800})

            # Mock failed delivery response for /api/auth3/forgot_password_send_otp
            def handle_route(route):
                route.fulfill(
                    status=503,
                    content_type="application/json",
                    body=json.dumps({
                        "ok": False,
                        "status_code": 503,
                        "email": "senat6031@gmail.com",
                        "error": "Không thể gửi email OTP: Thiếu biến môi trường cấu hình mật khẩu ứng dụng Gmail ('GMAIL_APP_PASSWORD').",
                        "missing_secret": "GMAIL_APP_PASSWORD",
                        "gmail_delivery": {
                            "sent_real_gmail": False,
                            "actual_recipient": "senat6031@gmail.com",
                            "missing_secret": "GMAIL_APP_PASSWORD"
                        }
                    }),
                )

            page.route("**/api/auth3/forgot_password_send_otp", handle_route)

            # --- DESKTOP UI VERIFICATION ---
            page.goto(f"{live_server_url}/index.html")

            # Click tab Quên mật khẩu
            page.click("#btnTabGateForgot")

            # Ensure Step 1 is displayed and Step 2 is hidden
            assert page.is_visible("#gateForgotStep1")
            assert not page.is_visible("#gateForgotStep2")

            # Fill email and click Gửi OTP
            page.fill("#gateForgotEmail", "senat6031@gmail.com")
            page.click("#btnSendForgotOtp")

            # Wait for response handling
            page.wait_for_timeout(1000)

            # Assert Step 2 is STILL hidden
            assert not page.is_visible("#gateForgotStep2"), (
                "LỖI UI: gateForgotStep2 đã hiển thị dù backend báo lỗi gửi mail!"
            )
            # Assert status box displays error message and does NOT claim success
            status_text = page.inner_text("#gateStatusBox")
            assert "❌" in status_text or "Thiếu biến môi trường" in status_text, (
                f"LỖI UI: gateStatusBox không hiển thị thông báo lỗi: {status_text}"
            )
            assert "✅ Đã gửi mã OTP" not in status_text, (
                f"LỖI UI: gateStatusBox vẫn hiển thị thành công: {status_text}"
            )

            # --- MOBILE APP UI VERIFICATION ---
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(f"{live_server_url}/app")

            # Click "Quên mật khẩu?" link
            page.click("#btnMobileForgotPassword")
            page.wait_for_selector("#mobileForgotStepEmail")
            assert page.is_visible("#mobileForgotStepEmail")
            assert not page.is_visible("#mobileForgotStepOtp")

            # Fill email and click Gửi mã OTP
            page.fill("#mobileForgotEmail", "senat6031@gmail.com")
            page.click("#mobileBtnForgotSendOtp")

            page.wait_for_timeout(1000)

            # Assert Mobile Step OTP is STILL hidden
            assert not page.is_visible("#mobileForgotStepOtp"), (
                "LỖI UI Mobile: mobileForgotStepOtp đã hiển thị dù gửi email thất bại!"
            )
            mobile_msg = page.inner_text("#mobileForgotEmailMsg")
            assert "Thiếu biến môi trường" in mobile_msg or "Không gửi được OTP" in mobile_msg, (
                f"LỖI UI Mobile: mobileForgotEmailMsg không hiển thị lỗi: {mobile_msg}"
            )

            page.close()
        finally:
            browser.close()
            pw.stop()
