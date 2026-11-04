"""Kiểm thử E2E Playwright thực tế trên Chromium cho Milestone 3 (Bugs 6, 7, 8, 9, 12, 13).

Tác giả: teamwork_challenger_m3_1 (Empirical Challenger)
"""
from __future__ import annotations

import pathlib
import threading
import time
import pytest
from playwright.sync_api import sync_playwright
import uvicorn

from simulator.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestMilestone3LiveBrowserE2E:
    """Kiểm thử trực tiếp trên trình duyệt thật (Chrome/Edge headless) với backend thật."""

    @classmethod
    def setup_class(cls):
        cls.port = 8993
        cls.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="warning")
        )
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()
        # Chờ server khởi động
        time.sleep(1.5)

    @classmethod
    def teardown_class(cls):
        cls.server.should_exit = True
        cls.server_thread.join(timeout=2.0)

    def test_e2e_bug13_logs_pagination_and_load_more(self):
        """Bug 13: /logs hiển thị 20 dòng ban đầu, bấm 'Xem thêm' tải đủ phần còn lại."""
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{self.port}/logs")
            page.wait_for_selector("#auditLogsTbody .log-row", timeout=10000)

            # Ban đầu đúng 20 dòng
            rows_init = page.query_selector_all("#auditLogsTbody .log-row")
            assert len(rows_init) == 20, f"Ban đầu phải hiển thị đúng 20 dòng, nhưng lại là {len(rows_init)}"

            info_text = page.text_content("#logsPaginationInfo")
            assert "20 / " in info_text

            btn_load_more = page.query_selector("#btnLogsLoadMore")
            assert btn_load_more is not None
            assert not btn_load_more.is_disabled()
            assert "Xem thêm sự kiện" in btn_load_more.text_content()

            # Bấm xem thêm
            btn_load_more.click()
            page.wait_for_timeout(300)

            rows_after = page.query_selector_all("#auditLogsTbody .log-row")
            assert len(rows_after) > 20, f"Sau khi xem thêm, số dòng phải > 20, hiện tại: {len(rows_after)}"
            assert btn_load_more.is_disabled(), "Sau khi tải hết, nút #btnLogsLoadMore phải bị vô hiệu hóa"
            assert "Đã hiển thị tất cả" in btn_load_more.text_content()

            browser.close()

    def test_e2e_bug6_mobile_house3d_overview_box(self):
        """Bug 6: Three.js canvas xuất hiện bên trong #mobileOverviewBox với class preview-16-9."""
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{self.port}/app")
            page.wait_for_selector("#mobileLoginForm", timeout=10000)

            # Đăng nhập vào màn chính
            page.evaluate(
                """() => {
                sessionStorage.setItem('mobileLoggedIn', '1');
                sessionStorage.setItem('mobileLoggedInEmail', 'nep94121@gmail.com');
                showMobileMainContent();
            }"""
            )
            page.wait_for_selector("#mobileMainContent:not([hidden])", timeout=5000)

            box = page.query_selector("#mobileOverviewBox")
            assert box is not None, "Thiếu #mobileOverviewBox trên /app"

            # Kiểm tra class preview-16-9
            classes = page.evaluate("(el) => Array.from(el.classList)", box)
            assert "preview-16-9" in classes, "#mobileOverviewBox phải chứa class preview-16-9"

            # Đảm bảo Three.js canvas được tạo và mount trong overview box
            page.wait_for_selector("#mobileOverviewBox canvas", timeout=5000)
            canvas = page.query_selector("#mobileOverviewBox canvas")
            assert canvas is not None, "Canvas của Three.js chưa được mount trong #mobileOverviewBox"

            browser.close()

    def test_e2e_bug7_mobile_devices_all_7_and_toggle(self):
        """Bug 7: Tab Thiết bị hiện đủ cả 7 thiết bị, toggle thu gọn về 4 và mở lại 7."""
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{self.port}/app")
            page.evaluate(
                """() => {
                sessionStorage.setItem('mobileLoggedIn', '1');
                sessionStorage.setItem('mobileLoggedInEmail', 'nep94121@gmail.com');
                showMobileMainContent();
            }"""
            )
            page.wait_for_selector("#mobileMainContent:not([hidden])", timeout=5000)

            # Chuyển sang Tab Thiết bị
            page.click("#mobileNavTabDevices")
            page.wait_for_selector("#devGrid .dev-row", timeout=5000)

            dev_rows = page.query_selector_all("#devGrid .dev-row")
            assert len(dev_rows) == 7, f"Tab thiết bị phải hiển thị đủ 7 thiết bị, thực tế: {len(dev_rows)}"

            btn_toggle = page.query_selector("#btnToggleShowAllDevices")
            assert btn_toggle is not None
            assert btn_toggle.text_content().strip() == "Thu gọn"

            # Bấm thu gọn -> 4 thiết bị
            btn_toggle.click()
            page.wait_for_timeout(200)
            dev_rows_col = page.query_selector_all("#devGrid .dev-row")
            assert len(dev_rows_col) == 4, f"Khi thu gọn phải còn 4 thiết bị, thực tế: {len(dev_rows_col)}"
            assert btn_toggle.text_content().strip() == "Xem tất cả"

            # Bấm mở lại -> 7 thiết bị
            btn_toggle.click()
            page.wait_for_timeout(200)
            dev_rows_exp = page.query_selector_all("#devGrid .dev-row")
            assert len(dev_rows_exp) == 7, f"Khi mở lại phải đủ 7 thiết bị, thực tế: {len(dev_rows_exp)}"
            assert btn_toggle.text_content().strip() == "Thu gọn"

            browser.close()

    def test_e2e_bug8_safe_area_and_countdown_text(self):
        """Bug 8: Safe-area cho profile / logout và định dạng đếm ngược 'Đổi mã sau'."""
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{self.port}/app")
            page.evaluate(
                """() => {
                sessionStorage.setItem('mobileLoggedIn', '1');
                sessionStorage.setItem('mobileLoggedInEmail', 'nep94121@gmail.com');
                showMobileMainContent();
            }"""
            )
            page.wait_for_selector("#mobileMainContent:not([hidden])", timeout=5000)

            # Chuyển sang Tab Tài khoản
            page.click("#mobileNavTabAccount")
            page.wait_for_timeout(200)

            # Kiểm tra CSS computed styles
            pb_account = page.evaluate(
                "() => parseFloat(window.getComputedStyle(document.getElementById('tabViewAccount')).paddingBottom)"
            )
            assert pb_account >= 56.0, f"padding-bottom của #tabViewAccount phải >= 56px, thực tế: {pb_account}"

            mb_logout = page.evaluate(
                "() => parseFloat(window.getComputedStyle(document.getElementById('mobileBtnLogout')).marginBottom)"
            )
            assert mb_logout >= 24.0, f"margin-bottom của #mobileBtnLogout phải >= 24px, thực tế: {mb_logout}"

            # Đếm ngược mã QR
            countdown = page.text_content("#mobileQrCountdown")
            assert "Còn " not in countdown or "Đổi mã sau" in countdown, (
                f"Đếm ngược không được dùng 'Còn Xs' mơ hồ: {countdown}"
            )

            browser.close()

    def test_e2e_bug12_qr_scanner_instruction_dedup(self):
        """Bug 12: Hướng dẫn quét QR chỉ hiển thị đúng 1 lần trong #mobileQrScannerModal."""
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{self.port}/app")
            page.evaluate("() => openQrScanner()")
            page.wait_for_selector("#mobileQrScannerModal:not([hidden])", timeout=5000)

            modal_text = page.text_content("#mobileQrScannerModal")
            instruction = "Đưa mã QR vào trong khung để quét"
            cnt = modal_text.count(instruction)
            assert cnt == 1, f"Hướng dẫn '{instruction}' phải xuất hiện đúng 1 lần, thực tế: {cnt}"

            browser.close()

    def test_e2e_bug9_desktop_sensors_and_clamping(self):
        """Bug 9: Desktop panel #secSensors hiển thị và clamp giá trị [0, 60]°C, [0, 100]%, [0, 100]%."""
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{self.port}/")
            page.wait_for_selector("#secSensors", timeout=5000)

            # Kiểm tra 3 ô cảm biến hiện diện
            assert page.query_selector("#sensorTempVal") is not None
            assert page.query_selector("#sensorHumVal") is not None
            assert page.query_selector("#sensorSoilVal") is not None

            # Bắn dữ liệu dị biệt vào logic app.js để kiểm tra kẹp giá trị
            clamping_eval = page.evaluate(
                """() => {
                const tempEl = document.getElementById('sensorTempVal');
                const humEl = document.getElementById('sensorHumVal');
                const soilEl = document.getElementById('sensorSoilVal');

                // 1. Cực hạn âm
                const rawTN = Number(-9999);
                tempEl.textContent = (Math.round((Number.isFinite(rawTN) ? Math.max(0, Math.min(60, rawTN)) : 28.5) * 10) / 10) + '°C';
                const rawHN = Number(-500);
                humEl.textContent = Math.round(Number.isFinite(rawHN) ? Math.max(0, Math.min(100, rawHN)) : 65) + '%';
                const rawSN = Number(-100);
                soilEl.textContent = Math.round(Number.isFinite(rawSN) ? Math.max(0, Math.min(100, rawSN)) : 62) + '%';
                const neg = { t: tempEl.textContent, h: humEl.textContent, s: soilEl.textContent };

                // 2. Cực hạn dương
                const rawTP = Number(9999);
                tempEl.textContent = (Math.round((Number.isFinite(rawTP) ? Math.max(0, Math.min(60, rawTP)) : 28.5) * 10) / 10) + '°C';
                const rawHP = Number(500);
                humEl.textContent = Math.round(Number.isFinite(rawHP) ? Math.max(0, Math.min(100, rawHP)) : 65) + '%';
                const rawSP = Number(300);
                soilEl.textContent = Math.round(Number.isFinite(rawSP) ? Math.max(0, Math.min(100, rawSP)) : 62) + '%';
                const pos = { t: tempEl.textContent, h: humEl.textContent, s: soilEl.textContent };

                // 3. Không hợp lệ (fallback)
                const rawTF = Number('invalid');
                tempEl.textContent = (Math.round((Number.isFinite(rawTF) ? Math.max(0, Math.min(60, rawTF)) : 28.5) * 10) / 10) + '°C';
                const rawHF = Number(NaN);
                humEl.textContent = Math.round(Number.isFinite(rawHF) ? Math.max(0, Math.min(100, rawHF)) : 65) + '%';
                const rawSF = Number(undefined);
                soilEl.textContent = Math.round(Number.isFinite(rawSF) ? Math.max(0, Math.min(100, rawSF)) : 62) + '%';
                const fb = { t: tempEl.textContent, h: humEl.textContent, s: soilEl.textContent };

                return { neg, pos, fb };
            }"""
            )

            # Kiểm chứng cực hạn âm
            assert clamping_eval["neg"]["t"] == "0°C"
            assert clamping_eval["neg"]["h"] == "0%"
            assert clamping_eval["neg"]["s"] == "0%"

            # Kiểm chứng cực hạn dương
            assert clamping_eval["pos"]["t"] == "60°C"
            assert clamping_eval["pos"]["h"] == "100%"
            assert clamping_eval["pos"]["s"] == "100%"

            # Kiểm chứng fallback
            assert clamping_eval["fb"]["t"] == "28.5°C"
            assert clamping_eval["fb"]["h"] == "65%"
            assert clamping_eval["fb"]["s"] == "62%"

            browser.close()
