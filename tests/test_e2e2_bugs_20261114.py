"""Regression suite for all 8 E2E bugs fixed in agyfix_e2e2_20261114."""

from __future__ import annotations

import json
import pathlib
import re
import subprocess

import pytest
from starlette.testclient import TestClient

from simulator.auth_3layer import get_auth_3layer_manager, hash_password
from simulator.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestGuestGuideAndGoneHtml:
    """Bug (b) /guest_guide + nav links and Bug (f) /guest_enroll friendly 410 HTML."""

    def test_guest_guide_returns_200_html_and_guest_without_token_stays_403(self, client: TestClient) -> None:
        r_guide = client.get("/guest_guide")
        assert r_guide.status_code == 200
        assert "text/html" in (r_guide.headers.get("content-type") or "").lower()
        assert "Quét mã QR do Chủ nhà tạo để vào" in r_guide.text
        assert not re.findall(r"<style\b", r_guide.text, re.IGNORECASE)
        script_tags = re.findall(r"<script\b([^>]*)>", r_guide.text, re.IGNORECASE)
        assert not [s for s in script_tags if "src=" not in s.lower()]

        r_guest = client.get("/guest")
        assert r_guest.status_code == 403

    def test_all_nav_guest_links_point_to_guest_guide(self) -> None:
        nav_pages = [
            ROOT / "simulator" / "static" / "index.html",
            ROOT / "simulator" / "static" / "auth.html",
            ROOT / "simulator" / "static" / "login.html",
            ROOT / "simulator" / "static" / "register.html",
            ROOT / "simulator" / "static" / "logs.html",
            ROOT / "simulator" / "static" / "wokwi.html",
            ROOT / "simulator" / "static" / "guest_enroll.html",
            ROOT / "simulator" / "static" / "guest_guide.html",
            ROOT / "mobile_app" / "index.html",
        ]
        for page in nav_pages:
            html = page.read_text(encoding="utf-8")
            assert 'href="/guest_guide"' in html, f"{page.name} must link to /guest_guide"
            # Exclude hidden dynamic #mobileQrOpenLink inside Owner-only mobile card
            for line in html.splitlines():
                if 'id="mobileQrOpenLink"' in line:
                    continue
                assert 'href="/guest"' not in line, f"Stale href=\"/guest\" in {page.name}: {line.strip()}"

    def test_guest_enroll_browser_get_returns_friendly_410_html_and_api_returns_410_json(self, client: TestClient) -> None:
        r_html = client.get("/guest_enroll")
        assert r_html.status_code == 410
        assert "text/html" in (r_html.headers.get("content-type") or "").lower()
        assert "Tính năng đã gỡ, hãy quét mã mời mới" in r_html.text
        assert not r_html.text.lstrip().startswith("{")

        for api_path in ("/api/qr/guest_enroll", "/api/auth3/invite_oauth_start", "/api/auth3/invite_verify_otp"):
            r_api = client.post(api_path, json={})
            assert r_api.status_code == 410
            assert "application/json" in (r_api.headers.get("content-type") or "").lower()
            assert r_api.json().get("gone") is True

    def test_vercel_json_routes_guest_guide_before_catchall(self) -> None:
        cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        srcs = [r["src"] for r in cfg["routes"]]
        assert "^/guest_guide/?$" in srcs
        assert srcs.index("^/guest_guide/?$") < srcs.index("^/(.*)$")


class TestLogsPageGateAndVietnameseFeedback:
    """Bug (a) /logs: hidden Quản trị menu for non-Tier-1, clear 401 messages, export CSV guard."""

    def test_logs_html_and_css_fail_closed_and_clean(self) -> None:
        logs_html = (ROOT / "simulator" / "static" / "logs.html").read_text(encoding="utf-8")
        assert 'id="logsAdminMenu"' in logs_html
        assert 'id="logsAdminPanel" hidden' in logs_html
        assert 'id="logsAdminHint"' in logs_html
        assert "Chỉ Chủ nhà (Cấp 1)" in logs_html
        assert 'id="logsActionStatus"' in logs_html
        assert not re.findall(r"<style\b", logs_html, re.IGNORECASE)

    def test_logs_js_fail_closed_behavior_in_node_vm(self) -> None:
        node_script = """
const fs = require('fs');
const vm = require('vm');
const jsCode = fs.readFileSync('simulator/static/js/logs.js', 'utf8');

const elems = {};
function mkEl(id) {
  return {
    id,
    value: id === 'sqlQueryInput' ? 'SELECT 1' : '',
    textContent: '',
    innerHTML: '',
    hidden: false,
    open: false,
    disabled: false,
    className: '',
    attrs: {},
    style: {},
    listeners: {},
    setAttribute(k, v) { this.attrs[k] = v; },
    removeAttribute(k) { delete this.attrs[k]; },
    addEventListener(ev, fn) { this.listeners[ev] = fn; },
    appendChild() {},
    remove() {},
    click() { globalThis.__downloaded = true; },
  };
}
['logsAdminMenu','logsAdminSummary','logsAdminPanel','logsAdminHint','logsActionStatus',
 'auditLogsTbody','mobileLogCards','logSearchInput','sqlQueryInput','sqlResultThead',
 'sqlResultTbody','kbTopic','kbKeywords','kbContent','kbTier','logsPaginationInfo','btnLogsLoadMore'
].forEach(id => { elems[id] = mkEl(id); });

let mockStatus = 401;
const sandbox = {
  window: {
    sessionStorage: { getItem: () => null },
    localStorage: { getItem: () => null },
    addEventListener: () => {},
    confirm: () => true,
  },
  document: {
    getElementById: (id) => elems[id] || mkEl(id),
    createElement: (tag) => mkEl(tag),
    querySelectorAll: () => [],
    body: { appendChild: () => {} },
  },
  Blob: class Blob {},
  URL: { createObjectURL: () => 'blob:mock' },
  navigator: { clipboard: { writeText: () => Promise.resolve() } },
  console,
  setTimeout,
  clearTimeout,
};
sandbox.window.fetch = async () => ({
  ok: mockStatus === 200,
  status: mockStatus,
  json: async () => mockStatus === 200
    ? { ok: true, audit_logs: [], hardware_database: { server_connected: true }, automation_database: {}, storage_files: [], knowledge_base: [], connection_pools: [] }
    : { ok: false, error: 'Yêu cầu đăng nhập quyền Chủ nhà' },
});
sandbox.fetch = (...args) => sandbox.window.fetch(...args);
vm.createContext(sandbox);
vm.runInContext(jsCode, sandbox);

(async () => {
  sandbox.window.setLogsAdminUiState(false);
  const ok401 = await sandbox.window.loadDashboard();
  if (ok401 !== false || !elems.logsAdminPanel.hidden || elems.logsAdminHint.hidden) {
    console.error('Expected fail-closed state on 401'); process.exit(1);
  }
  const exp401 = sandbox.window.exportLogsCsv();
  if (exp401 !== false || !elems.logsActionStatus.textContent.includes('Cần đăng nhập để xuất nhật ký') || sandbox.__downloaded) {
    console.error('Export CSV was not blocked or wrong message:', elems.logsActionStatus.textContent); process.exit(1);
  }
  await sandbox.window.seedDemoLog();
  if (!elems.logsActionStatus.textContent.includes('Bạn cần đăng nhập quyền Chủ nhà để ghi nhật ký')) {
    console.error('Seed 401 message mismatch:', elems.logsActionStatus.textContent); process.exit(1);
  }
  await sandbox.window.clearCustomLogs();
  if (!elems.logsActionStatus.textContent.includes('Bạn cần đăng nhập quyền Chủ nhà để xóa nhật ký')) {
    console.error('Clear 401 message mismatch:', elems.logsActionStatus.textContent); process.exit(1);
  }
  mockStatus = 200;
  const ok200 = await sandbox.window.loadDashboard();
  if (ok200 !== true || elems.logsAdminPanel.hidden || !elems.logsAdminHint.hidden) {
    console.error('Expected admin panel unlocked on 200'); process.exit(1);
  }
  console.log('LOGS_VM_OK');
})();
"""
        proc = subprocess.run(["node", "-e", node_script], cwd=str(ROOT), capture_output=True, text=True, timeout=15)
        assert proc.returncode == 0, proc.stderr or proc.stdout
        assert "LOGS_VM_OK" in proc.stdout


class TestRegisterAndMobileForgotOtpAndResetMessages:
    """Bugs (c), (d), (e) + Alias identity privacy."""

    def test_register_and_auth_forms_have_novalidate_and_vietnamese_validation(self) -> None:
        reg_html = (ROOT / "simulator" / "static" / "register.html").read_text(encoding="utf-8")
        assert '<form id="registerForm"' in reg_html and "novalidate" in reg_html
        login_html = (ROOT / "simulator" / "static" / "login.html").read_text(encoding="utf-8")
        assert '<form id="loginForm"' in login_html and "novalidate" in login_html

        node_script = """
const fs = require('fs');
const vm = require('vm');
const jsCode = fs.readFileSync('simulator/static/js/auth_pages.js', 'utf8');

const elems = {
  registerForm: { addEventListener(ev, fn) { if (ev === 'submit') this.onSubmit = fn; } },
  pageRegisterName: { value: 'Test' },
  pageRegisterEmail: { value: 'abc@@gmail', setAttribute() {}, removeAttribute() {}, focus() {}, addEventListener() {} },
  pageRegisterPassword: { value: '123', setAttribute() {}, removeAttribute() {}, focus() {}, addEventListener() {} },
  pageRegisterConfirmPassword: { value: '123', setAttribute() {}, removeAttribute() {}, focus() {}, addEventListener() {} },
  pageRegisterSubmitBtn: { disabled: false, textContent: 'Đăng ký' },
  registerStatusBox: { textContent: '', style: {}, className: '' },
};
let domReadyCb = null;
const sandbox = {
  document: {
    getElementById: (id) => elems[id] || null,
    addEventListener: (ev, fn) => { if (ev === 'DOMContentLoaded') domReadyCb = fn; },
    cookie: '',
  },
  localStorage: { setItem() {}, getItem: () => null },
  sessionStorage: { setItem() {}, getItem: () => null },
  location: { protocol: 'http:', search: '' },
  console,
  setTimeout,
};
vm.createContext(sandbox);
vm.runInContext(jsCode, sandbox);
domReadyCb();

(async () => {
  await elems.registerForm.onSubmit({ preventDefault() {} });
  if (!elems.registerStatusBox.textContent.includes('Vui lòng nhập địa chỉ Email hợp lệ!')) {
    console.error('Bad email message:', elems.registerStatusBox.textContent); process.exit(1);
  }
  elems.pageRegisterEmail.value = 'valid.user@gmail.com';
  await elems.registerForm.onSubmit({ preventDefault() {} });
  if (!elems.registerStatusBox.textContent.includes('Mật khẩu phải có từ 6 ký tự trở lên!')) {
    console.error('Short password message:', elems.registerStatusBox.textContent); process.exit(1);
  }
  console.log('REGISTER_VALIDATION_OK');
})();
"""
        proc = subprocess.run(["node", "-e", node_script], cwd=str(ROOT), capture_output=True, text=True, timeout=15)
        assert proc.returncode == 0, proc.stderr or proc.stdout
        assert "REGISTER_VALIDATION_OK" in proc.stdout

    def test_forgot_password_reset_message_for_pending_and_active_and_alias_non_leak(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mgr = get_auth_3layer_manager()
        pending_email = "e2e2_pending_reset@gmail.com"
        # Clean up any leftover account before/after test
        mgr.accounts = [a for a in mgr.accounts if str(a.get("email") or "").lower() != pending_email]
        mgr._save_accounts()

        try:
            reg = mgr.register_or_update_password(
                email=pending_email,
                password="InitPass#123",
                confirm_password="InitPass#123",
                display_name="Pending Reset User",
                target_tier=3,
                source="pytest_e2e2",
            )
            assert reg.get("ok") is True and reg.get("permission_active") is False

            # Request OTP & verify Step 2 with wrong then right OTP (without minting session!)
            otp_send = mgr.request_password_reset_otp(email=pending_email, send_gmail=False, source="pytest_e2e2")
            assert otp_send.get("ok") is True
            otp_code = mgr.pending_otps[pending_email]["otp_code"]

            r_wrong = client.post(
                "/api/auth3/layer2_verify_otp",
                json={"email": pending_email, "otp_code": "000000" if otp_code != "000000" else "999999", "purpose": "forgot_password"},
            )
            assert r_wrong.status_code == 400
            assert r_wrong.json().get("ok") is False

            r_right = client.post(
                "/api/auth3/layer2_verify_otp",
                json={"email": pending_email, "otp_code": otp_code, "purpose": "forgot_password"},
            )
            assert r_right.status_code == 200
            assert r_right.json().get("ok") is True
            assert not r_right.json().get("session_token")
            assert "sh_session_token" not in r_right.cookies

            # Step 3 reset must say "Đặt lại mật khẩu thành công. Hãy đăng nhập bằng mật khẩu mới", NEVER "Đã tạo tài khoản"
            r_reset = client.post(
                "/api/auth3/forgot_password_reset",
                json={
                    "email": pending_email,
                    "otp_code": otp_code,
                    "new_password": "ResetPass#456",
                    "confirm_password": "ResetPass#456",
                },
            )
            assert r_reset.status_code == 200
            msg = r_reset.json().get("message", "")
            assert "Đặt lại mật khẩu thành công. Hãy đăng nhập bằng mật khẩu mới" in msg
            assert "chờ Chủ nhà duyệt" in msg
            assert "Đã tạo tài khoản" not in msg

            # Owner alias probe on forgot_password_send_otp must NOT leak nep94121@gmail.com or display_name
            mgr.pending_otps.clear()
            owner_acc = mgr.find_account("nep94121@gmail.com")
            assert owner_acc is not None
            monkeypatch.setitem(owner_acc, "password_hash", hash_password("OwnerTmp#99"))
            monkeypatch.setitem(owner_acc, "otp_cooldown_started_at", 0.0)
            monkeypatch.setattr(mgr, "send_real_gmail_otp", lambda *a, **kw: {"sent_real_gmail": True, "actual_recipient": "nep94121@gmail.com"})
            r_alias = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "nep94121+probe1114@gmail.com", "send_gmail": True},
            )
            assert r_alias.status_code == 200
            alias_text = r_alias.text
            assert "nep94121@gmail.com" not in alias_text
            assert "Nguyễn Tuấn Anh" not in alias_text
            assert "display_name" not in r_alias.json()

            # Unknown email probe must NOT disclose "Không tìm thấy tài khoản"
            r_unk_send = client.post(
                "/api/auth3/forgot_password_send_otp",
                json={"email": "unknown_probe_1114@gmail.com", "send_gmail": False},
            )
            assert r_unk_send.status_code == 404
            assert "Không tìm thấy tài khoản" not in r_unk_send.text

            r_unk_reset = client.post(
                "/api/auth3/forgot_password_reset",
                json={
                    "email": "unknown_probe_1114@gmail.com",
                    "otp_code": "000000",
                    "new_password": "ResetPass#456",
                    "confirm_password": "ResetPass#456",
                },
            )
            assert r_unk_reset.status_code == 400
            assert "Không tìm thấy tài khoản" not in r_unk_reset.text
        finally:
            mgr.pending_otps.clear()
            mgr.accounts = [a for a in mgr.accounts if str(a.get("email") or "").lower() != pending_email]
            mgr._save_accounts()

    def test_mobile_forgot_step2_stays_on_step2_on_wrong_otp(self) -> None:
        js_text = (ROOT / "simulator" / "static" / "js" / "mobile_app.js").read_text(encoding="utf-8")
        assert "async function submitForgotVerifyOtp()" in js_text
        assert "/api/auth3/layer2_verify_otp" in js_text
        assert "Mã OTP không chính xác" in js_text
        for fname in ("auth_pages.js", "mobile_app.js", "app.js", "auth.js"):
            txt = (ROOT / "simulator" / "static" / "js" / fname).read_text(encoding="utf-8")
            # Confirm forgot reset fallback text is never "Đã tạo tài khoản"
            assert "Đặt lại mật khẩu thành công. Hãy đăng nhập bằng mật khẩu mới" in txt
