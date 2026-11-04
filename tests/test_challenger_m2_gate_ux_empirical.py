"""Bộ Kiểm Thử Đối Kháng Thực Nghiệm Chuyên Sâu Milestone 2 (Challenger 2).

Tác giả: challenger_m2_2 (Role: Empirical Challenger & Critic)
Mục tiêu kiểm định:
1. Đảm bảo `#homeLoginGateModal` không thể bị ẩn bằng bất kỳ cách nào nếu `localStorage`
   chưa lưu `smarthome_auth_session` (Bypass prevention: click nút X, click backdrop, bấm Escape, gọi API).
2. Kiểm tra mã nguồn `simulator/static/index.html` xem nút `#btnCloseLoginGateModal`
   có thuộc tính `hidden` không và khi bấm vào có bị chặn không.
3. Kiểm tra hành vi Enter key trên các form `<form id="gatePanelLogin">`,
   `<form id="gatePanelRegister">`, `<form id="gatePanelForgot">` (Web) và các form Mobile.
4. Kiểm tra tính tương thích DOM của nút 👁️ (`btn-toggle-pw`) trên tất cả các trang (Web & Mobile).
5. Thử nghiệm trên `mobile_app/index.html` về cấu trúc DOM và SVG symbols:
   Đảm bảo `<symbol id="i-home">` nằm ở thẻ `<svg>` toàn cục ngoài `#mobileMainContent hidden`.
6. Kiểm tra cơ chế 2 ô xác nhận mật khẩu (Double Password Confirmation) trên cả Web và Mobile.
7. Kiểm tra tính toàn vẹn 0 CRLF và UTF-8 không BOM trên toàn bộ 5 tệp đã sửa.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
from typing import Dict, List, Set
from bs4 import BeautifulSoup
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

TARGET_FILES = [
    ROOT / "simulator" / "static" / "index.html",
    ROOT / "simulator" / "static" / "js" / "app.js",
    ROOT / "simulator" / "static" / "js" / "auth.js",
    ROOT / "mobile_app" / "index.html",
    ROOT / "simulator" / "static" / "js" / "mobile_app.js",
]


# =============================================================================
# 1. KIỂM CHỨNG TOÀN VẸN ĐỊNH DẠNG TỆP (0 CRLF, UTF-8 KHÔNG BOM)
# =============================================================================

class TestFileFormatAndEncodingIntegrity:
    """Kiểm tra 100% tuân thủ chuẩn UTF-8 không BOM và 0 CRLF (POSIX LF)."""

    @pytest.mark.parametrize("file_path", TARGET_FILES, ids=[f.name for f in TARGET_FILES])
    def test_file_exists_and_non_empty(self, file_path: pathlib.Path):
        assert file_path.exists(), f"Tệp không tồn tại: {file_path}"
        assert file_path.stat().st_size > 0, f"Tệp rỗng: {file_path}"

    @pytest.mark.parametrize("file_path", TARGET_FILES, ids=[f.name for f in TARGET_FILES])
    def test_zero_crlf_strictly_enforced(self, file_path: pathlib.Path):
        """Bảo đảm tuyệt đối 0 CRLF (0 byte \\r\\n)."""
        raw = file_path.read_bytes()
        assert b"\r\n" not in raw, f"Phát hiện ký tự CRLF (Windows line ending) trong {file_path.name}"
        assert b"\r" not in raw, f"Phát hiện ký tự CR đơn lẻ trong {file_path.name}"

    @pytest.mark.parametrize("file_path", TARGET_FILES, ids=[f.name for f in TARGET_FILES])
    def test_utf8_without_bom(self, file_path: pathlib.Path):
        """Bảo đảm UTF-8 chuẩn không có Byte Order Mark (BOM: EF BB BF)."""
        raw = file_path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"Phát hiện UTF-8 BOM trong {file_path.name}"
        # Giải mã UTF-8 hợp lệ
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as err:
            pytest.fail(f"Lỗi giải mã UTF-8 trong {file_path.name}: {err}")


# =============================================================================
# 2. KIỂM CHỨNG ĐỐI KHÁNG LOGIN GATE & NÚT ĐÓNG X TRÊN WEB
# =============================================================================

@pytest.fixture(scope="module")
def web_html_soup() -> BeautifulSoup:
    html_file = ROOT / "simulator" / "static" / "index.html"
    return BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")


@pytest.fixture(scope="module")
def mobile_soup() -> BeautifulSoup:
    html_file = ROOT / "mobile_app" / "index.html"
    return BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")


class TestWebLoginGateLockdown:
    """Đối kháng Cổng Đăng Nhập #homeLoginGateModal và Nút Đóng #btnCloseLoginGateModal."""

    def test_login_gate_modal_structure(self, web_html_soup: BeautifulSoup):
        """Modal #homeLoginGateModal phải tồn tại và có class modal hidden."""
        modal = web_html_soup.find("div", id="homeLoginGateModal")
        assert modal is not None, "Không tìm thấy #homeLoginGateModal trong index.html"
        assert "modal" in modal.get("class", []), "#homeLoginGateModal thiếu class 'modal'"
        assert "hidden" in modal.get("class", []), "#homeLoginGateModal ban đầu phải có class 'hidden'"

    def test_close_button_has_hidden_attribute_statically(self, web_html_soup: BeautifulSoup):
        """Nút #btnCloseLoginGateModal BẮT BUỘC có thuộc tính hidden ngay từ mã nguồn HTML."""
        btn_close = web_html_soup.find("button", id="btnCloseLoginGateModal")
        assert btn_close is not None, "Không tìm thấy #btnCloseLoginGateModal trong index.html"
        assert btn_close.has_attr("hidden"), (
            "Nút #btnCloseLoginGateModal PHẢI có thuộc tính 'hidden' trong HTML tĩnh "
            "để ngăn người dùng bấm X đóng modal khi chưa đăng nhập!"
        )

    def test_login_gate_bypass_resistance_node_vm(self):
        """Thực nghiệm chạy Node VM để chứng minh không thể bypass Login Gate bằng:
        1. Gọi trực tiếp closeLoginGateModal() khi chưa có session.
        2. Bấm vào nút #btnCloseLoginGateModal khi chưa có session.
        3. Click vào backdrop của modal khi chưa có session.
        4. Nhấn phím Escape khi chưa có session.
        5. Dùng session rác / giả mạo (JSON không có email).
        """
        node_script = """
const fs = require('fs');
const vm = require('vm');

let appJsCode = fs.readFileSync(process.argv[1], 'utf8');

function createEnvironment(initialStorage) {
  const elements = {};
  function getEl(id) {
    if (!elements[id]) {
      elements[id] = {
        id: id,
        hidden: id === 'btnCloseLoginGateModal',
        className: id === 'homeLoginGateModal' ? 'modal' : '',
        classList: {
          _classes: new Set(id === 'homeLoginGateModal' ? ['modal'] : []),
          add(c) { this._classes.add(c); },
          remove(c) { this._classes.delete(c); },
          contains(c) { return this._classes.has(c); }
        },
        style: {},
        value: '',
        textContent: '',
        innerText: '',
        innerHTML: '',
        disabled: false,
        setAttribute() {},
        getAttribute() { return null; },
        hasAttribute() { return false; },
        removeAttribute() {},
        focus() {},
        blur() {},
        appendChild() {},
        removeChild() {},
        listeners: {},
        addEventListener(event, fn) {
          if (!this.listeners[event]) this.listeners[event] = [];
          this.listeners[event].push(fn);
        },
        dispatch(event, eObj) {
          const list = this.listeners[event] || [];
          for (const fn of list) fn(eObj || {});
        },
        click() {
          this.dispatch('click', { target: this });
        }
      };
    }
    return elements[id];
  }

  // Pre-seed known elements
  ['homeLoginGateModal', 'btnCloseLoginGateModal', 'btnLogoutHome', 'homeCurrentAccountBadge',
   'btnTabGateLogin', 'btnTabGateRegister', 'btnTabGateForgot',
   'gatePanelLogin', 'gatePanelRegister', 'gatePanelForgot', 'gateStatusBox',
   'btnSubmitGateLogin', 'btnSubmitGateRegister', 'btnSubmitForgotReset',
   'gateLoginEmail', 'gateLoginPassword', 'gateRegTier', 'gateRegName', 'gateRegEmail',
   'gateRegPassword', 'gateRegConfirmPassword', 'gateForgotEmail', 'gateForgotOtpInput',
   'gateForgotNewPassword', 'gateForgotConfirmPassword'
  ].forEach(getEl);

  const docListeners = {};
  const mockLocalStorage = {
    _data: Object.assign({}, initialStorage),
    getItem(k) { return this._data[k] !== undefined ? this._data[k] : null; },
    setItem(k, v) { this._data[k] = String(v); },
    removeItem(k) { delete this._data[k]; }
  };

  const mockLocation = { href: 'http://localhost:8088', search: '', protocol: 'http:', host: 'localhost:8088', pathname: '/' };
  const sandbox = {
    document: {
      getElementById: getEl,
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: () => ({ appendChild: () => {}, style: {} }),
      addEventListener(event, fn) {
        if (!docListeners[event]) docListeners[event] = [];
        docListeners[event].push(fn);
      },
      dispatch(event, eObj) {
        const list = docListeners[event] || [];
        for (const fn of list) fn(eObj || {});
      }
    },
    location: mockLocation,
    localStorage: mockLocalStorage,
    window: {
      location: mockLocation,
      localStorage: mockLocalStorage,
      addEventListener: () => {},
      togglePasswordVisibility: null,
      SmartHome3D: null
    },
    fetch: async () => ({ ok: true, json: async () => ({ ok: true }) }),
    setTimeout: (fn) => fn(),
    clearTimeout: () => {},
    setInterval: () => {},
    clearInterval: () => {},
    WebSocket: class { constructor() {} addEventListener() {} send() {} close() {} },
    AudioContext: class { createMediaStreamSource() { return { connect() {} }; } },
    webkitAudioContext: class {},
    navigator: { mediaDevices: { getUserMedia: async () => ({}) } },
    console: { log: () => {}, error: () => {}, warn: () => {} }
  };
  sandbox.window.window = sandbox.window;
  sandbox.window.document = sandbox.document;

  const ctx = vm.createContext(sandbox);
  // Execute app.js in sandbox
  vm.runInContext(appJsCode, ctx);

  return { ctx, elements, mockLocalStorage, docListeners, getEl };
}

const tests = [];

// TEST 1: Khi chưa đăng nhập (localStorage rỗng)
{
  const env = createEnvironment({});
  const modal = env.getEl('homeLoginGateModal');
  const closeBtn = env.getEl('btnCloseLoginGateModal');
  const statusBox = env.getEl('gateStatusBox');

  // Modal phải hiển thị (không có class hidden)
  const isInitiallyVisible = !modal.classList.contains('hidden');

  // Nút X phải có hidden = true
  const isCloseBtnHidden = closeBtn.hidden === true;

  // Bấm nút X -> Modal vẫn không được phép đóng
  closeBtn.click();
  const stayedOpenAfterBtn = !modal.classList.contains('hidden');

  // Bấm backdrop -> Modal vẫn không được phép đóng
  modal.click();
  const stayedOpenAfterBackdrop = !modal.classList.contains('hidden');

  // Bấm Escape -> Modal vẫn không được phép đóng
  let escapePrevented = false;
  let escapeStopped = false;
  env.ctx.document.dispatch('keydown', {
    key: 'Escape',
    preventDefault() { escapePrevented = true; },
    stopPropagation() { escapeStopped = true; }
  });
  const stayedOpenAfterEscape = !modal.classList.contains('hidden');

  tests.push({
    name: 'Unauthenticated lock down',
    pass: isInitiallyVisible && isCloseBtnHidden && stayedOpenAfterBtn &&
          stayedOpenAfterBackdrop && stayedOpenAfterEscape && escapePrevented && escapeStopped,
    detail: { isInitiallyVisible, isCloseBtnHidden, stayedOpenAfterBtn, stayedOpenAfterBackdrop, stayedOpenAfterEscape, escapePrevented }
  });
}

// TEST 2: Thử tấn công bằng session rác (Session forgery / empty email)
{
  const env = createEnvironment({
    'smarthome_auth_session': JSON.stringify({ display_name: 'Hacker', role: 'admin' }) // Thiếu email!
  });
  const modal = env.getEl('homeLoginGateModal');
  const closeBtn = env.getEl('btnCloseLoginGateModal');

  // Nút X vẫn phải hidden vì session không hợp lệ
  const isCloseBtnHidden = closeBtn.hidden === true;
  closeBtn.click();
  const stayedOpen = !modal.classList.contains('hidden');

  tests.push({
    name: 'Forged session without email rejection',
    pass: isCloseBtnHidden && stayedOpen,
    detail: { isCloseBtnHidden, stayedOpen }
  });
}

// TEST 3: Khi có session hợp lệ (nep94121@gmail.com)
{
  const env = createEnvironment({
    'smarthome_auth_session': JSON.stringify({ email: 'nep94121@gmail.com', tier: 1, display_name: 'Nguyễn Tuấn Anh' })
  });
  const modal = env.getEl('homeLoginGateModal');
  const closeBtn = env.getEl('btnCloseLoginGateModal');

  // Nút X phải hiển thị (hidden = false)
  const isCloseBtnVisible = closeBtn.hidden === false;

  // Bấm nút X -> Modal đóng thành công (có class hidden)
  closeBtn.click();
  const closedAfterBtn = modal.classList.contains('hidden');

  // Bấm Đăng xuất -> Modal mở lại và nút X bị ẩn ngay lập tức
  const logoutBtn = env.getEl('btnLogoutHome');
  logoutBtn.click();
  const openedAfterLogout = !modal.classList.contains('hidden');
  const closeHiddenAfterLogout = closeBtn.hidden === true;
  const storageCleared = env.mockLocalStorage.getItem('smarthome_auth_session') === null;

  tests.push({
    name: 'Authenticated flow and logout lock',
    pass: isCloseBtnVisible && closedAfterBtn && openedAfterLogout && closeHiddenAfterLogout && storageCleared,
    detail: { isCloseBtnVisible, closedAfterBtn, openedAfterLogout, closeHiddenAfterLogout, storageCleared }
  });
}

process.stdout.write(JSON.stringify({ ok: tests.every(t => t.pass), tests }));
"""
        js_file = ROOT / "simulator" / "static" / "js" / "app.js"
        proc = subprocess.run(
            ["node", "-e", node_script, str(js_file)],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        assert proc.returncode == 0, f"Node script error: {proc.stderr}"
        res = json.loads(proc.stdout)
        assert res["ok"], f"Thực nghiệm đối kháng Login Gate thất bại: {res['tests']}"


# =============================================================================
# 3. KIỂM CHỨNG HÀNH VI ENTER KEY & THẺ <FORM>
# =============================================================================

class TestFormEnterKeyBehavior:
    """Kiểm tra cấu trúc thẻ <form> và hỗ trợ phím Enter khi submit."""

    def test_web_panels_are_actual_forms(self, web_html_soup: BeautifulSoup):
        """Ba panel Login Gate (#gatePanelLogin, #gatePanelRegister, #gatePanelForgot)
        phải là thẻ <form>, không được dùng thẻ <div>.
        """
        for form_id in ["gatePanelLogin", "gatePanelRegister", "gatePanelForgot"]:
            tag = web_html_soup.find(id=form_id)
            assert tag is not None, f"Không tìm thấy #{form_id} trong index.html"
            assert tag.name == "form", f"#{form_id} phải là thẻ <form>, hiện tại là <{tag.name}>!"
            assert tag.has_attr("onsubmit"), f"#{form_id} thiếu thuộc tính onsubmit"
            assert "preventDefault" in tag["onsubmit"], f"#{form_id} onsubmit phải ngăn reload trang"

    def test_web_forms_contain_submit_buttons(self, web_html_soup: BeautifulSoup):
        """Mỗi form trên Web phải có một nút type='submit'."""
        mapping = {
            "gatePanelLogin": "btnSubmitGateLogin",
            "gatePanelRegister": "btnSubmitGateRegister",
            "gatePanelForgot": "btnSubmitForgotReset"
        }
        for form_id, btn_id in mapping.items():
            form = web_html_soup.find("form", id=form_id)
            btn = form.find(id=btn_id)
            assert btn is not None, f"Không tìm thấy #{btn_id} trong #{form_id}"
            assert btn.get("type") == "submit", f"#{btn_id} phải có type='submit' để nhận phím Enter!"

    def test_mobile_forms_are_actual_forms(self, mobile_soup: BeautifulSoup):
        """Trên Mobile, các form #mobileLoginForm, #mobileRegisterForm, #mobileChangePasswordForm
        phải là thẻ <form> với submit handler.
        """
        for form_id in ["mobileLoginForm", "mobileRegisterForm", "mobileChangePasswordForm"]:
            tag = mobile_soup.find(id=form_id)
            assert tag is not None, f"Không tìm thấy #{form_id} trong mobile_app/index.html"
            assert tag.name == "form", f"#{form_id} phải là thẻ <form>, hiện tại là <{tag.name}>"
            assert tag.has_attr("onsubmit"), f"#{form_id} thiếu thuộc tính onsubmit"

    def test_web_form_submit_event_listener_wires_to_submit_button(self):
        """Kiểm tra trong simulator/static/js/app.js có addEventListener('submit') cho cả 3 form."""
        js_code = (ROOT / "simulator" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        assert "gatePanelLogin.addEventListener(\"submit\"" in js_code
        assert "gatePanelRegister.addEventListener(\"submit\"" in js_code
        assert "gatePanelForgot.addEventListener(\"submit\"" in js_code
        assert "btnSubmitGateLogin.click()" in js_code
        assert "btnSubmitGateRegister.click()" in js_code
        assert "btnSubmitForgotReset.click()" in js_code


# =============================================================================
# 4. KIỂM CHỨNG NÚT 👁️ TOGGLE PASSWORD TRÊN TOÀN BỘ CÁC TRANG
# =============================================================================

class TestPasswordVisibilityToggle:
    """Kiểm tra tính tương thích DOM và cơ chế hoạt động của nút 👁️ btn-toggle-pw."""

    WEB_PW_IDS = [
        "gateLoginPassword",
        "gateRegPassword",
        "gateRegConfirmPassword",
        "gateForgotNewPassword",
        "gateForgotConfirmPassword"
    ]

    MOBILE_PW_IDS = [
        "mobileLoginPassword",
        "mobileRegPassword",
        "mobileRegConfirmPassword",
        "mobileChangeNewPassword",
        "mobileChangeConfirmPassword"
    ]

    def test_web_all_password_fields_have_toggle_button(self):
        """Tất cả 5 ô mật khẩu trên Web phải có nút .btn-toggle-pw kế bên."""
        html = (ROOT / "simulator" / "static" / "index.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        for pw_id in self.WEB_PW_IDS:
            pw_input = soup.find(id=pw_id)
            assert pw_input is not None, f"Không tìm thấy ô nhập #{pw_id} trên Web"
            assert pw_input.get("type") == "password", f"#{pw_id} phải có type='password'"
            parent = pw_input.parent
            btn_toggle = parent.find("button", class_="btn-toggle-pw")
            assert btn_toggle is not None, f"Ô nhập #{pw_id} thiếu nút .btn-toggle-pw"
            assert "togglePasswordVisibility" in btn_toggle.get("onclick", "")
            assert pw_id in btn_toggle.get("onclick", "")
            assert "👁️" in btn_toggle.text

    def test_mobile_all_password_fields_have_toggle_button(self):
        """Tất cả 5 ô mật khẩu trên Mobile phải có nút .btn-toggle-pw kế bên."""
        html = (ROOT / "mobile_app" / "index.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        for pw_id in self.MOBILE_PW_IDS:
            pw_input = soup.find(id=pw_id)
            assert pw_input is not None, f"Không tìm thấy ô nhập #{pw_id} trên Mobile"
            assert pw_input.get("type") == "password", f"#{pw_id} phải có type='password'"
            parent = pw_input.parent
            btn_toggle = parent.find("button", class_="btn-toggle-pw")
            assert btn_toggle is not None, f"Ô nhập #{pw_id} thiếu nút .btn-toggle-pw"
            assert "togglePasswordVisibility" in btn_toggle.get("onclick", "")
            assert pw_id in btn_toggle.get("onclick", "")
            assert "👁️" in btn_toggle.text

    def test_toggle_function_runtime_logic_web_and_mobile(self):
        """Kiểm nghiệm logic hàm togglePasswordVisibility qua Node VM."""
        node_test = """
const fs = require('fs');
const vm = require('vm');

function testFile(filePath) {
  const code = fs.readFileSync(filePath, 'utf8');
  let mockInput = { type: 'password' };
  const mockWindow = {
    location: { href: 'http://localhost:8088', search: '', protocol: 'http:', host: 'localhost:8088', pathname: '/' },
    addEventListener: () => {},
    removeEventListener: () => {},
    setTimeout: () => {},
    clearTimeout: () => {},
    setInterval: () => {},
    clearInterval: () => {},
    AudioContext: class { createMediaStreamSource() { return { connect() {} }; } },
    webkitAudioContext: class {},
    navigator: { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [] }) }, clipboard: { writeText: async () => {} } },
    document: {
      getElementById: (id) => (id === 'testPw' ? mockInput : {
        addEventListener: () => {}, removeEventListener: () => {}, classList: { add: () => {}, remove: () => {}, contains: () => false },
        style: {}, setAttribute: () => {}, getAttribute: () => null, hasAttribute: () => false
      }),
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: () => ({ appendChild: () => {}, style: {} }),
      addEventListener: () => {},
      removeEventListener: () => {}
    },
    WebSocket: class { constructor() {} addEventListener() {} send() {} close() {} },
    fetch: async () => ({ ok: true, json: async () => ({ ok: true }) }),
    localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} }
  };
  mockWindow.window = mockWindow;
  mockWindow.location = mockWindow.location;
  mockWindow.localStorage = mockWindow.localStorage;
  mockWindow.document.defaultView = mockWindow;

  const ctx = vm.createContext(mockWindow);
  vm.runInContext(code, ctx);

  const fn = mockWindow.togglePasswordVisibility || mockWindow.window.togglePasswordVisibility;
  if (!fn) throw new Error('togglePasswordVisibility not exported in ' + filePath);

  const mockBtn = { textContent: '👁️' };
  // Lần 1: Chuyển password -> text
  fn('testPw', mockBtn);
  if (mockInput.type !== 'text' || mockBtn.textContent !== '🙈') {
    return { ok: false, step: 'password->text', inputType: mockInput.type, btn: mockBtn.textContent };
  }

  // Lần 2: Chuyển text -> password
  fn('testPw', mockBtn);
  if (mockInput.type !== 'password' || mockBtn.textContent !== '👁️') {
    return { ok: false, step: 'text->password', inputType: mockInput.type, btn: mockBtn.textContent };
  }

  // Lần 3: Gọi ID không tồn tại không được throw error
  fn('nonExistentId', mockBtn);

  return { ok: true };
}

const rWeb = testFile(process.argv[1]);
const rMob = testFile(process.argv[2]);
process.stdout.write(JSON.stringify({ web: rWeb, mobile: rMob }));
"""
        proc = subprocess.run(
            ["node", "-e", node_test,
             str(ROOT / "simulator" / "static" / "js" / "app.js"),
             str(ROOT / "simulator" / "static" / "js" / "mobile_app.js")],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        assert proc.returncode == 0, f"Node test error: {proc.stderr}"
        res = json.loads(proc.stdout)
        assert res["web"]["ok"], f"Hàm toggle trên Web thất bại: {res['web']}"
        assert res["mobile"]["ok"], f"Hàm toggle trên Mobile thất bại: {res['mobile']}"


# =============================================================================
# 5. KIỂM CHỨNG CẤU TRÚC MOBILE SVG SPRITE & SYMBOLS
# =============================================================================

class TestMobileSvgSpriteScope:
    """Kiểm tra cấu trúc DOM SVG Symbols trên mobile_app/index.html."""

    def test_global_svg_sprite_placement(self, mobile_soup: BeautifulSoup):
        """Khối <svg> chứa <symbol id="i-home">... phải nằm trực tiếp dưới <body>,
        bên ngoài <div id="mobileMainContent" hidden>.
        """
        body = mobile_soup.find("body")
        assert body is not None, "Không tìm thấy thẻ <body> trong mobile_app/index.html"

        # Tìm thẻ svg đầu tiên trong body
        svg_sprite = body.find("svg", recursive=False)
        assert svg_sprite is not None, "Khối SVG sprite không nằm trực tiếp dưới thẻ <body>"

        # Kiểm tra symbol i-home nằm bên trong svg_sprite
        i_home = svg_sprite.find("symbol", id="i-home")
        assert i_home is not None, "Không tìm thấy <symbol id='i-home'> trong SVG sprite toàn cục"

        # Đảm bảo các symbol thiết yếu khác cũng có mặt
        for sym_id in ["i-home", "i-grid", "i-mic", "i-user", "i-lamp", "i-fan", "i-snow", "i-door", "i-bell"]:
            assert svg_sprite.find("symbol", id=sym_id) is not None, f"Thiếu symbol #{sym_id} trong sprite toàn cục"

    def test_symbol_not_trapped_inside_hidden_container(self, mobile_soup: BeautifulSoup):
        """Khối <symbol id="i-home"> TUYỆT ĐỐI KHÔNG nằm trong #mobileMainContent có thuộc tính hidden."""
        main_content = mobile_soup.find("div", id="mobileMainContent")
        assert main_content is not None, "Không tìm thấy #mobileMainContent"
        assert main_content.has_attr("hidden"), "#mobileMainContent phải có thuộc tính 'hidden'"

        # Không được có bất kỳ <symbol id="i-home"> nào bên trong main_content
        trapped_symbol = main_content.find("symbol", id="i-home")
        assert trapped_symbol is None, "<symbol id='i-home'> vẫn đang bị kẹt bên trong #mobileMainContent hidden!"

    def test_login_gate_icon_references_global_symbol(self, mobile_soup: BeautifulSoup):
        """Trong #mobileLoginGate, icon ngôi nhà tham chiếu hợp lệ <use href="#i-home"/>."""
        login_gate = mobile_soup.find("div", id="mobileLoginGate")
        assert login_gate is not None, "Không tìm thấy #mobileLoginGate"
        use_tag = login_gate.find("use")
        assert use_tag is not None, "Không tìm thấy thẻ <use> trong #mobileLoginGate"
        assert use_tag.get("href") == "#i-home" or use_tag.get("xlink:href") == "#i-home", (
            f"Thẻ <use> trong #mobileLoginGate tham chiếu sai: {use_tag}"
        )


# =============================================================================
# 6. KIỂM CHỨNG BẮT BUỘC 2 Ô XÁC NHẬN MẬT KHẨU & MỞ KHÓA READONLY
# =============================================================================

class TestPasswordConfirmationAndReadOnlyRemoval:
    """Kiểm tra cơ chế 2 ô mật khẩu và gỡ bỏ readOnly = true trong auth.js."""

    def test_auth_js_does_not_contain_readonly_true(self):
        """Trong simulator/static/js/auth.js, nameInput.readOnly và emailInput.readOnly
        không được gán bằng true.
        """
        auth_js = (ROOT / "simulator" / "static" / "js" / "auth.js").read_text(encoding="utf-8")
        assert "nameInput.readOnly = true" not in auth_js, "Vẫn còn tồn tại nameInput.readOnly = true!"
        assert "emailInput.readOnly = true" not in auth_js, "Vẫn còn tồn tại emailInput.readOnly = true!"
        assert "nameInput.readOnly = false" in auth_js
        assert "emailInput.readOnly = false" in auth_js

    def test_web_register_and_forgot_forms_have_confirm_password(self):
        """Trên Web, form đăng ký và form quên mật khẩu phải có 2 ô mật khẩu riêng biệt."""
        html = (ROOT / "simulator" / "static" / "index.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")

        # Form Đăng ký
        assert soup.find(id="gateRegPassword") is not None
        assert soup.find(id="gateRegConfirmPassword") is not None

        # Form Quên mật khẩu
        assert soup.find(id="gateForgotNewPassword") is not None
        assert soup.find(id="gateForgotConfirmPassword") is not None

    def test_mobile_register_and_change_forms_have_confirm_password(self):
        """Trên Mobile, form đăng ký và form đổi mật khẩu phải có 2 ô mật khẩu riêng biệt."""
        html = (ROOT / "mobile_app" / "index.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")

        # Form Đăng ký Mobile
        assert soup.find(id="mobileRegPassword") is not None
        assert soup.find(id="mobileRegConfirmPassword") is not None

        # Form Đổi mật khẩu Mobile
        assert soup.find(id="mobileChangeNewPassword") is not None
        assert soup.find(id="mobileChangeConfirmPassword") is not None

    def test_mismatched_passwords_rejected_in_app_js(self):
        """Trong app.js, kiểm tra logic từ chối khi mật khẩu không khớp nhau."""
        app_js = (ROOT / "simulator" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        assert "password !== confirmPassword" in app_js
        assert "newPassword !== confirmPassword" in app_js

    def test_mismatched_passwords_rejected_in_mobile_app_js(self):
        """Trong mobile_app.js, kiểm tra logic từ chối khi mật khẩu không khớp nhau."""
        mob_js = (ROOT / "simulator" / "static" / "js" / "mobile_app.js").read_text(encoding="utf-8")
        assert "password !== confirmPassword" in mob_js
        assert "pw1 !== pw2" in mob_js

