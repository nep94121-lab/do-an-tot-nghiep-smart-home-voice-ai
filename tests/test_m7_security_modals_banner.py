"""Kiểm thử Chuyên biệt Milestone M7: Security Modals & WebSocket Reconnect Banner.

Phạm vi kiểm thử:
1. Security Lockdown Modal (`#securityLockdownModal`):
   - Cấu trúc alertdialog, aria-modal, Lucide shield-alert icon.
   - Không có nút đóng X và backdrop click disabled.
   - Form mở khóa hỗ trợ Password / OTP Gmail, Enter key, toggle password.
2. Microphone Permission Modal (`#micPermissionModal`):
   - Cấu trúc dialog, aria-modal, Lucide mic-off icon.
   - Nút Thử lại, Mở bản HTTPS, Đóng.
3. WebSocket Reconnect Banner (`#wsReconnectBanner`):
   - Cấu trúc status, aria-live polite, amber warning banner.
   - Nút 'Kết nối ngay' gọi window.retryWsConnection().
   - Trạng thái restored đổi màu xanh và ẩn sau 2s.
4. CSS Tokens & Styles trong style.css.
5. Window Exports & Headless VM Runtime Tests trong app.js.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
from bs4 import BeautifulSoup
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX_HTML = ROOT / "simulator" / "static" / "index.html"
STYLE_CSS = ROOT / "simulator" / "static" / "css" / "style.css"
APP_JS = ROOT / "simulator" / "static" / "js" / "app.js"


@pytest.fixture(scope="module")
def html_soup() -> BeautifulSoup:
    content = INDEX_HTML.read_text(encoding="utf-8")
    return BeautifulSoup(content, "html.parser")


@pytest.fixture(scope="module")
def css_content() -> str:
    return STYLE_CSS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js_content() -> str:
    return APP_JS.read_text(encoding="utf-8")


class TestSecurityLockdownModal:
    """Kiểm thử Hộp thoại Khóa An ninh (#securityLockdownModal)."""

    def test_lockdown_modal_exists_and_attributes(self, html_soup: BeautifulSoup):
        modal = html_soup.find("div", id="securityLockdownModal")
        assert modal is not None, "Không tìm thấy #securityLockdownModal trong index.html"
        assert modal.get("role") == "alertdialog", "Modal phải có role='alertdialog'"
        assert modal.get("aria-modal") == "true", "Modal phải có aria-modal='true'"
        assert modal.get("aria-labelledby") == "locktitle", "Modal phải có aria-labelledby='locktitle'"
        classes = modal.get("class", [])
        assert "modal" in classes and "hidden" in classes, "Modal phải có class 'modal hidden'"

    def test_lockdown_modal_has_shield_alert_icon(self, html_soup: BeautifulSoup):
        modal = html_soup.find("div", id="securityLockdownModal")
        assert modal is not None
        mark = modal.find("div", class_="mark")
        assert mark is not None and "red" in mark.get("class", []), "Modal phải có div.mark.red"
        svg = mark.find("svg")
        assert svg is not None, "Phải có svg icon trong .mark.red"
        # Kiểm tra path Lucide shield-alert
        path = svg.find("path")
        assert path is not None and "12 22s8-4 8-10V5l-8-3-8 3v7" in path.get("d", "")

    def test_lockdown_modal_strictly_no_close_button(self, html_soup: BeautifulSoup):
        modal = html_soup.find("div", id="securityLockdownModal")
        assert modal is not None
        close_btns = modal.find_all(lambda tag: (
            tag.get("aria-label") in ("Đóng", "Close") or
            "btn-close" in tag.get("class", []) or
            tag.get("id") == "btnCloseLockdown"
        ))
        assert len(close_btns) == 0, (
            "Khóa an ninh bắt buộc KHÔNG ĐƯỢC CÓ nút đóng X hoặc nút close để chống vượt rào an ninh!"
        )

    def test_lockdown_modal_form_and_inputs(self, html_soup: BeautifulSoup):
        modal = html_soup.find("div", id="securityLockdownModal")
        assert modal is not None
        form = modal.find("form", id="lockdownForm")
        assert form is not None, "Phải có form #lockdownForm"

        # Password input
        pw_input = modal.find("input", id="lockdownPassword")
        assert pw_input is not None, "Phải có ô nhập mật khẩu #lockdownPassword"
        assert pw_input.get("type") == "password"
        # Eye toggle
        eye_btn = modal.find("button", onclick=lambda val: val and "togglePasswordVisibility" in val)
        assert eye_btn is not None, "Phải có nút toggle password visibility"

        # OTP input
        otp_input = modal.find("input", id="lockdownOtp")
        assert otp_input is not None, "Phải có ô nhập OTP #lockdownOtp"
        assert otp_input.get("maxlength") == "6"

        # Buttons
        send_otp_btn = modal.find(id="btnLockdownSendOtp")
        assert send_otp_btn is not None, "Phải có nút #btnLockdownSendOtp"

        unlock_btn = modal.find(id="btnLockdownUnlock")
        assert unlock_btn is not None, "Phải có nút #btnLockdownUnlock ('Xác minh và mở khóa')"

        toggle_btn = modal.find(id="btnLockdownToggleMode")
        assert toggle_btn is not None, "Phải có nút #btnLockdownToggleMode ('Dùng mã OTP Gmail')"

        status_box = modal.find(id="lockdownStatusBox")
        assert status_box is not None, "Phải có box #lockdownStatusBox"


class TestMicPermissionModal:
    """Kiểm thử Hộp thoại Quyền Microphone (#micPermissionModal)."""

    def test_mic_modal_exists_and_attributes(self, html_soup: BeautifulSoup):
        modal = html_soup.find("div", id="micPermissionModal")
        assert modal is not None, "Không tìm thấy #micPermissionModal trong index.html"
        assert modal.get("role") == "dialog", "Modal phải có role='dialog'"
        assert modal.get("aria-modal") == "true", "Modal phải có aria-modal='true'"
        assert modal.get("aria-labelledby") == "mictitle", "Modal phải có aria-labelledby='mictitle'"
        classes = modal.get("class", [])
        assert "modal" in classes and "hidden" in classes

    def test_mic_modal_has_mic_off_icon(self, html_soup: BeautifulSoup):
        modal = html_soup.find("div", id="micPermissionModal")
        assert modal is not None
        mark = modal.find("div", class_="mark")
        assert mark is not None, "Phải có div.mark"
        svg = mark.find("svg")
        assert svg is not None, "Phải có svg icon trong .mark"
        path = svg.find("path")
        assert path is not None and "M9 5a3 3 0 0 1 6 0v6" in path.get("d", "")

    def test_mic_modal_action_buttons(self, html_soup: BeautifulSoup):
        modal = html_soup.find("div", id="micPermissionModal")
        assert modal is not None

        retry_btn = modal.find(id="btnMicPermissionRetry")
        assert retry_btn is not None, "Phải có nút #btnMicPermissionRetry ('Thử lại')"

        https_link = modal.find(id="btnMicPermissionHttps")
        assert https_link is not None, "Phải có liên kết/nút #btnMicPermissionHttps ('Mở bản HTTPS')"

        close_btn = modal.find(id="btnMicPermissionClose")
        assert close_btn is not None, "Phải có nút #btnMicPermissionClose ('Đóng')"


class TestWsReconnectBanner:
    """Kiểm thử Thanh Thông báo Kết nối lại WebSocket (#wsReconnectBanner)."""

    def test_ws_banner_exists_and_attributes(self, html_soup: BeautifulSoup):
        banner = html_soup.find("div", id="wsReconnectBanner")
        assert banner is not None, "Không tìm thấy #wsReconnectBanner trong index.html"
        assert banner.get("role") == "status", "Banner phải có role='status'"
        assert banner.get("aria-live") == "polite", "Banner phải có aria-live='polite'"
        classes = banner.get("class", [])
        assert "banner" in classes and "hidden" in classes

    def test_ws_banner_elements(self, html_soup: BeautifulSoup):
        banner = html_soup.find("div", id="wsReconnectBanner")
        assert banner is not None

        msg_box = banner.find(id="wsReconnectBannerMsg")
        assert msg_box is not None, "Phải có #wsReconnectBannerMsg"

        subtext = banner.find(id="wsReconnectSubtext")
        assert subtext is not None, "Phải có #wsReconnectSubtext"

        retry_btn = banner.find(id="btnWsReconnectNow")
        assert retry_btn is not None, "Phải có nút #btnWsReconnectNow ('Kết nối ngay')"
        onclick = retry_btn.get("onclick", "")
        assert "retryWsConnection" in onclick, "Nút phải gọi window.retryWsConnection()"


class TestCssDesignTokensAndStyles:
    """Kiểm thử các CSS tokens và styling trong style.css."""

    def test_css_root_tokens_defined(self, css_content: str):
        assert "--redsoft:" in css_content
        assert "--orangesoft:" in css_content
        assert "--greensoft:" in css_content
        assert "--orange:" in css_content
        assert "--green:" in css_content

    def test_css_banner_and_modal_classes(self, css_content: str):
        assert ".banner {" in css_content or ".banner" in css_content
        assert ".banner.banner-restored" in css_content
        assert ".banner.banner-sliding-out" in css_content
        assert ".mark.red" in css_content
        assert ".eyebrow" in css_content
        assert ".note.red" in css_content


class TestAppJsImplementation:
    """Kiểm thử logic JavaScript và window exports trong app.js."""

    def test_window_exports_present(self, js_content: str):
        expected_exports = [
            "retryWsConnection",
            "showWsReconnectBanner",
            "hideWsReconnectBanner",
            "triggerSecurityLockdown",
            "openSecurityLockdownModal",
            "closeSecurityLockdownModal",
            "unlockSecurityLockdown",
            "toggleLockdownMode",
            "sendLockdownOtp",
            "showMicPermissionModal",
            "openMicPermissionModal",
            "closeMicPermissionModal",
            "retryMicPermission",
        ]
        for exp in expected_exports:
            pat = rf"window\.{exp}\s*="
            assert re.search(pat, js_content), f"Thiếu export window.{exp} trong app.js"

    def test_strike_and_lockdown_triggers_in_app_js(self, js_content: str):
        assert "triggerSecurityLockdown" in js_content
        # Trigger on strikes >= 3 or silent_ignore
        assert "a.strike_count >= 3" in js_content or "a.strike_count && a.strike_count >= 3" in js_content
        assert "msg.strike_count >= 3" in js_content or "msg.strike_count && msg.strike_count >= 3" in js_content

    def test_mic_permission_triggers_in_app_js(self, js_content: str):
        assert "showMicPermissionModal" in js_content
        # Kiểm tra insecure context và NotAllowedError
        assert "isSecureContext" in js_content
        assert "NotAllowedError" in js_content

    def test_reconnect_banner_restored_state(self, js_content: str):
        assert "showWsRestoredBanner" in js_content
        assert "banner-restored" in js_content
        assert "banner-sliding-out" in js_content

    def test_node_headless_runtime_execution(self):
        """Chạy kiểm thử Headless Node VM kiểm tra các hàm M7 hoạt động không ném lỗi."""
        test_script = """
const fs = require('fs');
const vm = require('vm');

function createMockElement(id) {
  return {
    id: id || '',
    addEventListener: () => {},
    removeEventListener: () => {},
    style: {},
    classList: {
      _classes: new Set(),
      add: function(c) { this._classes.add(c); },
      remove: function(c) { this._classes.delete(c); },
      toggle: function(c, force) { if (force !== undefined) { force ? this._classes.add(c) : this._classes.delete(c); } else { this._classes.has(c) ? this._classes.delete(c) : this._classes.add(c); } },
      contains: function(c) { return this._classes.has(c); }
    },
    innerText: '',
    textContent: '',
    innerHTML: '',
    value: '',
    checked: false,
    disabled: false,
    appendChild: () => {},
    removeChild: () => {},
    setAttribute: () => {},
    getAttribute: () => null,
    hasAttribute: () => false,
    removeAttribute: () => {},
    scrollIntoView: () => {},
    focus: () => {},
    blur: () => {},
    click: () => {},
    querySelector: () => ({ innerHTML: '' }),
    querySelectorAll: () => []
  };
}

const mockWindow = {
  location: { href: 'http://localhost:8088', search: '', protocol: 'http:', host: 'localhost:8088', hostname: 'localhost', pathname: '/' },
  isSecureContext: true,
  addEventListener: () => {},
  removeEventListener: () => {},
  setTimeout: (fn) => setTimeout(fn, 1),
  clearTimeout: () => {},
  setInterval: () => {},
  clearInterval: () => {},
  AudioContext: class { createMediaStreamSource() { return { connect() {} }; } },
  webkitAudioContext: class {},
  navigator: { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [] }) }, clipboard: { writeText: async () => {} }, onLine: true },
  document: {
    getElementById: (id) => createMockElement(id),
    querySelector: () => createMockElement(),
    querySelectorAll: () => [],
    createElement: (tag) => createMockElement(tag),
    addEventListener: () => {},
    removeEventListener: () => {}
  },
  WebSocket: class { constructor() {} addEventListener() {} send() {} close() {} },
  performance: { now: () => Date.now() },
  btoa: (str) => Buffer.from(str, 'binary').toString('base64'),
  atob: (b64) => Buffer.from(b64, 'base64').toString('binary'),
  localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  fetch: async () => ({ ok: true, json: async () => ({ ok: true, devices: [] }) }),
  console: console
};
mockWindow.window = mockWindow;
mockWindow.globalThis = mockWindow;

const code = fs.readFileSync('simulator/static/js/app.js', 'utf8');
vm.runInNewContext(code, mockWindow);

// Kiểm tra gọi các hàm M7 trên window
if (typeof mockWindow.triggerSecurityLockdown !== 'function') throw new Error('triggerSecurityLockdown not exported');
if (typeof mockWindow.closeSecurityLockdownModal !== 'function') throw new Error('closeSecurityLockdownModal not exported');
if (typeof mockWindow.toggleLockdownMode !== 'function') throw new Error('toggleLockdownMode not exported');
if (typeof mockWindow.showMicPermissionModal !== 'function') throw new Error('showMicPermissionModal not exported');
if (typeof mockWindow.closeMicPermissionModal !== 'function') throw new Error('closeMicPermissionModal not exported');
if (typeof mockWindow.showWsReconnectBanner !== 'function') throw new Error('showWsReconnectBanner not exported');
if (typeof mockWindow.retryWsConnection !== 'function') throw new Error('retryWsConnection not exported');

mockWindow.triggerSecurityLockdown();
mockWindow.toggleLockdownMode();
mockWindow.closeSecurityLockdownModal();
mockWindow.showMicPermissionModal('permission_denied');
mockWindow.closeMicPermissionModal();
mockWindow.showWsReconnectBanner(2, 5);
mockWindow.retryWsConnection();
mockWindow.hideWsReconnectBanner();

console.log(JSON.stringify({ ok: true, message: 'Tất cả hàm M7 thực thi an toàn trong headless VM!' }));
"""
        proc = subprocess.run(
            ["node", "-e", test_script],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        assert proc.returncode == 0, f"Lỗi Node VM: {proc.stderr}"
        res = json.loads(proc.stdout)
        assert res.get("ok") is True, f"Kết quả Node VM: {res}"
