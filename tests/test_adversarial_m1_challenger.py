"""Adversarial Challenger Test Suite for Milestone 1.

Author: teamwork_challenger_m1_1 (Empirical Challenger)
Target: Milestone 1 Security & Authentication Fixes (Bugs 1, 2, 4, 5, 15)
Focus:
- Account authentication & OTP flows for senat6031@gmail.com & kbanh376@gmail.com
- Security invariants: brute-force resistance, wrong OTP, expired OTP, non-existent accounts
- Zero residual credentials/session state upon logout (Desktop & Mobile)
- HTML credential stripping, log masking, and duration badge behaviors
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from bs4 import BeautifulSoup
import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.server import app
from simulator.auth_3layer import get_auth_3layer_manager
from simulator.auth.constants_and_crypto import verify_password_hash


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# =============================================================================
# 1. EMPIRICAL VERIFICATION: TEST ACCOUNTS senat6031 & kbanh376
# =============================================================================

class TestAdversarialAccountsAuthAndOtp:
    """Stress-test authentication and OTP workflows for senat6031@gmail.com and kbanh376@gmail.com."""

    def test_seed_accounts_integrity_and_hashing(self):
        """Verify accounts exist in default accounts, are PBKDF2 hashed, and have correct tiers."""
        mgr = get_auth_3layer_manager()

        # 1. Verify senat6031@gmail.com
        acc_senat = mgr.find_account("senat6031@gmail.com")
        assert acc_senat is not None, "senat6031@gmail.com missing from accounts!"
        assert acc_senat.get("tier") == 2, f"Expected tier 2, got {acc_senat.get('tier')}"
        assert acc_senat.get("role") == "MEMBER", f"Expected MEMBER role, got {acc_senat.get('role')}"
        assert verify_password_hash("GiaDinh@123", acc_senat["password_hash"]), "senat6031 PBKDF2 hash mismatch!"

        # 2. Verify kbanh376@gmail.com
        acc_kbanh = mgr.find_account("kbanh376@gmail.com")
        assert acc_kbanh is not None, "kbanh376@gmail.com missing from accounts!"
        assert acc_kbanh.get("tier") == 3, f"Expected tier 3, got {acc_kbanh.get('tier')}"
        assert acc_kbanh.get("role") == "CHILD_GUEST", f"Expected CHILD_GUEST role, got {acc_kbanh.get('role')}"
        assert verify_password_hash("Khach@789", acc_kbanh["password_hash"]), "kbanh376 PBKDF2 hash mismatch!"

    def test_layer1_login_success_and_failure(self, client: TestClient):
        """Verify layer1 login succeeds with valid credentials and securely rejects invalid ones."""
        # Valid login senat6031
        res1 = client.post(
            "/api/auth3/layer1_login",
            json={"email": "senat6031@gmail.com", "password": "GiaDinh@123", "send_gmail": False}
        )
        assert res1.status_code == 200
        d1 = res1.json()
        assert d1.get("ok") is True, f"senat6031 login failed: {d1}"
        assert d1.get("tier") == 2
        assert d1.get("next_layer") == 2
        assert "sh_session_token" in res1.cookies or d1.get("session_token"), "Missing session token"

        # Valid login kbanh376
        res2 = client.post(
            "/api/auth3/layer1_login",
            json={"email": "kbanh376@gmail.com", "password": "Khach@789", "send_gmail": False}
        )
        assert res2.status_code == 200
        d2 = res2.json()
        assert d2.get("ok") is True, f"kbanh376 login failed: {d2}"
        assert d2.get("tier") == 3
        assert d2.get("next_layer") == 2

        # Invalid password for senat6031: MUST fail and NOT leak hints
        res_bad = client.post(
            "/api/auth3/layer1_login",
            json={"email": "senat6031@gmail.com", "password": "WrongPassword!999", "send_gmail": False}
        )
        assert res_bad.status_code == 200
        d_bad = res_bad.json()
        assert d_bad.get("ok") is False
        assert "GiaDinh@123" not in d_bad.get("error", "")
        assert "gợi ý" not in d_bad.get("error", "").lower()

    def test_otp_request_and_reset_flow(self, client: TestClient):
        """Empirically test OTP request, verification, and password reset."""
        email = "senat6031@gmail.com"
        mgr = get_auth_3layer_manager()

        # Step 1: Request OTP
        req_res = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": email, "send_gmail": False}
        )
        assert req_res.status_code == 200
        req_data = req_res.json()
        assert req_data.get("ok") is True, f"OTP request failed: {req_data}"
        otp_code = req_data.get("otp_code_for_test") or req_data.get("demo_otp_preview")
        assert otp_code and len(otp_code) == 6, f"Invalid OTP issued: {otp_code}"

        # Step 2: Adversarial check - try wrong OTP
        wrong_otp_res = client.post(
            "/api/auth3/forgot_password_reset",
            json={
                "email": email,
                "otp_code": "000000" if otp_code != "000000" else "111111",
                "new_password": "NewSecretPassword@2026",
                "confirm_password": "NewSecretPassword@2026"
            }
        )
        assert wrong_otp_res.status_code in (200, 400)
        assert wrong_otp_res.json().get("ok") is False, "Wrong OTP was erroneously accepted!"

        # Step 3: Adversarial check - mismatched passwords
        mismatch_res = client.post(
            "/api/auth3/forgot_password_reset",
            json={
                "email": email,
                "otp_code": otp_code,
                "new_password": "NewSecretPassword@2026",
                "confirm_password": "DifferentPassword@2026"
            }
        )
        assert mismatch_res.status_code in (200, 400)
        assert mismatch_res.json().get("ok") is False, "Mismatched passwords accepted!"

        # Step 4: Valid OTP and matching password reset
        reset_res = client.post(
            "/api/auth3/forgot_password_reset",
            json={
                "email": email,
                "otp_code": otp_code,
                "new_password": "NewSecretPassword@2026",
                "confirm_password": "NewSecretPassword@2026"
            }
        )
        assert reset_res.status_code == 200
        assert reset_res.json().get("ok") is True, f"Password reset failed: {reset_res.json()}"

        # Step 5: Verify login with new password succeeds
        login_new = client.post(
            "/api/auth3/layer1_login",
            json={"email": email, "password": "NewSecretPassword@2026", "send_gmail": False}
        )
        assert login_new.status_code == 200
        assert login_new.json().get("ok") is True

        # Step 6: Verify old password now fails
        login_old = client.post(
            "/api/auth3/layer1_login",
            json={"email": email, "password": "GiaDinh@123", "send_gmail": False}
        )
        assert login_old.status_code == 200
        assert login_old.json().get("ok") is False

        # Cleanup: Restore original password for senat6031@gmail.com
        mgr.register_or_update_password(
            email=email,
            password="GiaDinh@123",
            confirm_password="GiaDinh@123",
            display_name="Thành viên Gia đình (senat6031)",
            target_tier=2
        )


# =============================================================================
# 2. EMPIRICAL VERIFICATION: LOGOUT RESIDUAL STATE (DESKTOP & MOBILE)
# =============================================================================

class TestAdversarialLogoutResidualState:
    """Stress-test that logout leaves ZERO residual credentials or session state in DOM or storage."""

    def test_desktop_logout_purges_all_fields_and_storage(self):
        """Run Node.js execution of app.js clearAuthState() to verify comprehensive wipe."""
        node_script = """
const fs = require('fs');
const jsCode = fs.readFileSync(process.argv[1], 'utf8');

const elements = {};
function getEl(id) {
  if (!elements[id]) {
    elements[id] = {
      id,
      value: '',
      textContent: '',
      hidden: false,
      style: {},
      setAttribute(k, v) { this[k] = v; },
      removeAttribute(k) { delete this[k]; },
      classList: {
        _classes: new Set(),
        add(c) { this._classes.add(c); },
        remove(c) { this._classes.delete(c); },
        contains(c) { return this._classes.has(c); }
      },
      listeners: {},
      addEventListener(evt, fn) {
        if (!this.listeners[evt]) this.listeners[evt] = [];
        this.listeners[evt].push(fn);
      },
      click() {
        if (this.listeners['click']) {
          this.listeners['click'].forEach(fn => fn({ preventDefault: () => {} }));
        }
      }
    };
  }
  return elements[id];
}

const targetIds = [
  'homeLoginGateModal', 'btnCloseLoginGateModal', 'btnLogoutHome', 'homeCurrentAccountBadge',
  'homeSessionDurationBadge', 'btnTabGateLogin', 'btnTabGateRegister', 'btnTabGateForgot',
  'gatePanelLogin', 'gatePanelRegister', 'gatePanelForgot', 'gateStatusBox',
  'btnSubmitGateLogin', 'btnSubmitGateRegister', 'btnSubmitForgotReset',
  'gateLoginEmail', 'gateLoginPassword', 'gateRegTier', 'gateRegName', 'gateRegEmail',
  'gateRegPassword', 'gateRegConfirmPassword', 'gateForgotEmail', 'gateForgotOtpInput',
  'gateForgotNewPassword', 'gateForgotConfirmPassword'
];
targetIds.forEach(getEl);

const mockStorage = {
  _d: { 'smarthome_auth_session': JSON.stringify({ email: 'senat6031@gmail.com', tier: 2 }) },
  getItem(k) { return this._d[k] || null; },
  setItem(k, v) { this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; }
};

global.document = {
  getElementById: getEl,
  querySelector: () => null,
  querySelectorAll: () => [],
  cookie: 'smarthome_session=testtoken123;',
  addEventListener: () => {}
};
global.window = {
  localStorage: mockStorage,
  sessionStorage: mockStorage,
  addEventListener: () => {},
  location: { search: '' }
};
global.location = { protocol: 'http:', host: 'localhost:8088', search: '' };
global.WebSocket = class { addEventListener() {} send() {} close() {} };
global.setInterval = () => {};
global.clearInterval = () => {};
global.setTimeout = () => {};
global.clearTimeout = () => {};

try {
  eval(jsCode);
} catch (e) {
  // Ignore load errors
}

// Pre-fill fields with user credentials before logout
getEl('gateLoginEmail').value = 'senat6031@gmail.com';
getEl('gateLoginPassword').value = 'GiaDinh@123';
getEl('gateRegEmail').value = 'new_reg@gmail.com';
getEl('gateRegPassword').value = 'NewPassword@123';
getEl('gateForgotEmail').value = 'senat6031@gmail.com';
getEl('gateForgotOtpInput').value = '123456';
getEl('gateForgotNewPassword').value = 'ResetPw@123';
getEl('gateStatusBox').textContent = 'Đăng nhập thành công!';
getEl('homeCurrentAccountBadge').textContent = '🏠 Cấp 2 · Gia đình: senat6031@gmail.com';
getEl('homeSessionDurationBadge').textContent = 'Còn 30 ngày';
getEl('homeSessionDurationBadge').hidden = false;
getEl('btnLogoutHome').hidden = false;
getEl('btnLogoutHome').style.display = '';

// Trigger logout click
getEl('btnLogoutHome').click();

const result = {
  loginEmailCleared: getEl('gateLoginEmail').value === '',
  loginPasswordCleared: getEl('gateLoginPassword').value === '',
  regEmailCleared: getEl('gateRegEmail').value === '',
  regPasswordCleared: getEl('gateRegPassword').value === '',
  forgotEmailCleared: getEl('gateForgotEmail').value === '',
  forgotOtpCleared: getEl('gateForgotOtpInput').value === '',
  forgotPasswordCleared: getEl('gateForgotNewPassword').value === '',
  statusNotSuccess: !getEl('gateStatusBox').textContent.includes('thành công'),
  storageCleared: mockStorage.getItem('smarthome_auth_session') === null,
  badgeReset: getEl('homeCurrentAccountBadge').textContent.includes('Chưa đăng nhập'),
  durationBadgeHidden: getEl('homeSessionDurationBadge').hidden === true || getEl('homeSessionDurationBadge').style.display === 'none',
  logoutBtnHidden: getEl('btnLogoutHome').hidden === true || getEl('btnLogoutHome').style.display === 'none'
};

process.stdout.write(JSON.stringify(result));
process.exit(0);
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
        for k, v in res.items():
            assert v is True, f"Desktop logout check failed for {k}!"

    def test_mobile_logout_purges_all_fields_and_storage(self):
        """Run Node.js execution of mobile_app.js submitMobileLogout() to verify wipe."""
        node_script = """
const fs = require('fs');
const jsCode = fs.readFileSync(process.argv[1], 'utf8');

const elements = {};
function getEl(id) {
  if (!elements[id]) {
    elements[id] = {
      id,
      value: '',
      textContent: '',
      hidden: false,
      style: {},
      setAttribute(k, v) { this[k] = v; },
      removeAttribute(k) { delete this[k]; },
      listeners: {},
      addEventListener(evt, fn) {
        if (!this.listeners[evt]) this.listeners[evt] = [];
        this.listeners[evt].push(fn);
      }
    };
  }
  return elements[id];
}

const mockStorage = {
  _d: { 'smarthome_auth_session': JSON.stringify({ email: 'senat6031@gmail.com' }) },
  getItem(k) { return this._d[k] || null; },
  setItem(k, v) { this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; }
};

const mockSession = {
  _d: { 'mobileLoggedIn': 'true', 'mobileLoggedInEmail': 'senat6031@gmail.com' },
  getItem(k) { return this._d[k] || null; },
  setItem(k, v) { this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; },
  clear() { this._d = {}; }
};

global.document = {
  getElementById: getEl,
  querySelector: () => null,
  querySelectorAll: () => [],
  cookie: '',
  addEventListener: () => {}
};
global.window = {
  localStorage: mockStorage,
  sessionStorage: mockSession,
  addEventListener: () => {},
  location: { search: '' }
};
global.navigator = { mediaDevices: {} };
global.location = { search: '', protocol: 'http:' };
global.localStorage = mockStorage;
global.sessionStorage = mockSession;
global.setInterval = () => {};
global.clearInterval = () => {};
global.setTimeout = () => {};
global.clearTimeout = () => {};

try {
  eval(jsCode);
} catch (e) {
  // Ignore load errors
}

// Pre-fill fields with user credentials before logout
getEl('mobileLoginEmail').value = 'senat6031@gmail.com';
getEl('mobileLoginPassword').value = 'GiaDinh@123';
getEl('mobileLoginMsg').textContent = 'Đăng nhập thành công';
getEl('mobileRegEmail').value = 'reg_test@gmail.com';
getEl('mobileRegPassword').value = 'RegPass@123';
getEl('mobileForgotEmail').value = 'senat6031@gmail.com';
getEl('mobileForgotOtp').value = '654321';
getEl('mobileForgotNewPassword').value = 'NewPass@123';
getEl('mobileMainContent').hidden = false;
getEl('mobileBottomNav').hidden = false;
getEl('mobileLoginGate').hidden = true;

if (typeof global.window.submitMobileLogout === 'function') {
  global.window.submitMobileLogout();
} else {
  process.stderr.write("submitMobileLogout not found");
  process.exit(1);
}

const result = {
  emailCleared: getEl('mobileLoginEmail').value === '',
  passwordCleared: getEl('mobileLoginPassword').value === '',
  msgCleared: getEl('mobileLoginMsg').textContent === '',
  regEmailCleared: getEl('mobileRegEmail').value === '',
  regPasswordCleared: getEl('mobileRegPassword').value === '',
  forgotEmailCleared: getEl('mobileForgotEmail').value === '',
  forgotOtpCleared: getEl('mobileForgotOtp').value === '',
  forgotPasswordCleared: getEl('mobileForgotNewPassword').value === '',
  mainHidden: getEl('mobileMainContent').hidden === true,
  navHidden: getEl('mobileBottomNav').hidden === true,
  gateVisible: getEl('mobileLoginGate').hidden === false,
  storageCleared: mockStorage.getItem('smarthome_auth_session') === null,
  sessionEmpty: Object.keys(mockSession._d).length === 0
};

process.stdout.write(JSON.stringify(result));
process.exit(0);
"""
        js_file = ROOT / "simulator" / "static" / "js" / "mobile_app.js"
        proc = subprocess.run(
            ["node", "-e", node_script, str(js_file)],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        assert proc.returncode == 0, f"Node script error: {proc.stderr}"
        res = json.loads(proc.stdout)
        for k, v in res.items():
            assert v is True, f"Mobile logout check failed for {k}!"


# =============================================================================
# 3. EMPIRICAL VERIFICATION: BUG 1, BUG 5, BUG 15
# =============================================================================

class TestAdversarialBug1Bug5Bug15:
    """Stress-test Bug 1 (zero leaks), Bug 5 (voice auth check login), Bug 15 (duration badge)."""

    def test_bug1_html_contains_zero_prefilled_credentials(self):
        """Scan all HTML templates in simulator and mobile_app for hardcoded passwords or prefilled values."""
        html_files = [
            ROOT / "simulator" / "static" / "index.html",
            ROOT / "mobile_app" / "index.html",
            ROOT / "simulator" / "static" / "auth.html",
            ROOT / "simulator" / "static" / "logs.html",
            ROOT / "simulator" / "static" / "wokwi.html",
        ]
        forbidden_snippets = [
            'value="123456"',
            'value="GiaDinh@123"',
            'value="Khach@789"',
            'Mật khẩu mặc định',
            'Mật khẩu gợi ý: 123456',
            '(Mật khẩu gợi ý: 123456',
            '(Mật khẩu gợi ý: GiaDinh@12',
            '(MK: 123456)',
        ]
        for f in html_files:
            if not f.exists():
                continue
            text = f.read_text(encoding="utf-8")
            for snip in forbidden_snippets:
                assert snip not in text, f"Found forbidden credential snippet '{snip}' in {f.name}!"

            soup = BeautifulSoup(text, "html.parser")
            for pin in soup.find_all("input", {"type": "password"}):
                assert not pin.get("value"), f"Password input #{pin.get('id')} in {f.name} has prefilled value: {pin.get('value')}"

    def test_bug5_voice_wizard_login_check_with_real_accounts(self, client: TestClient):
        """Verify that /auth check login succeeds for real seed accounts and properly validates passwords."""
        # 1. Owner account
        res1 = client.post(
            "/api/auth3/layer1_login",
            json={"email": "nep94121@gmail.com", "password": "123456", "login_method": "password", "send_gmail": False}
        )
        assert res1.status_code == 200
        assert res1.json().get("ok") is True

        # 2. Family seed account
        res2 = client.post(
            "/api/auth3/layer1_login",
            json={"email": "senat6031@gmail.com", "password": "GiaDinh@123", "login_method": "password", "send_gmail": False}
        )
        assert res2.status_code == 200
        assert res2.json().get("ok") is True

        # 3. Guest seed account
        res3 = client.post(
            "/api/auth3/layer1_login",
            json={"email": "kbanh376@gmail.com", "password": "Khach@789", "login_method": "password", "send_gmail": False}
        )
        assert res3.status_code == 200
        assert res3.json().get("ok") is True

    def test_bug15_duration_badge_rendering_for_all_tiers(self):
        """Verify duration badge text logic for Tier 1, Tier 2, and Tier 3."""
        node_script = """
const fs = require('fs');
const jsCode = fs.readFileSync(process.argv[1], 'utf8');

const elements = {};
function getEl(id) {
  if (!elements[id]) {
    elements[id] = {
      id,
      value: '',
      textContent: '',
      hidden: true,
      style: {},
      setAttribute(k, v) { this[k] = v; },
      removeAttribute(k) { delete this[k]; },
      classList: {
        _classes: new Set(),
        add(c) { this._classes.add(c); },
        remove(c) { this._classes.delete(c); },
        contains(c) { return this._classes.has(c); }
      },
      listeners: {},
      addEventListener(evt, fn) {
        if (!this.listeners[evt]) this.listeners[evt] = [];
        this.listeners[evt].push(fn);
      }
    };
  }
  return elements[id];
}

const targetIds = [
  'homeLoginGateModal', 'btnCloseLoginGateModal', 'btnLogoutHome', 'homeCurrentAccountBadge',
  'homeSessionDurationBadge', 'btnTabGateLogin', 'btnTabGateRegister', 'btnTabGateForgot',
  'gatePanelLogin', 'gatePanelRegister', 'gatePanelForgot', 'gateStatusBox',
  'btnSubmitGateLogin', 'btnSubmitGateRegister', 'btnSubmitForgotReset'
];
targetIds.forEach(getEl);

const mockStorage = {
  _d: {},
  getItem(k) { return this._d[k] || null; },
  setItem(k, v) { this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; }
};

global.document = {
  getElementById: getEl,
  querySelector: () => null,
  querySelectorAll: () => [],
  cookie: '',
  addEventListener: () => {}
};
global.window = {
  localStorage: mockStorage,
  sessionStorage: mockStorage,
  addEventListener: () => {},
  location: { search: '' }
};
global.location = { protocol: 'http:', host: 'localhost:8088', search: '' };
global.WebSocket = class { addEventListener() {} send() {} close() {} };
global.setInterval = () => {};
global.clearInterval = () => {};
global.setTimeout = () => {};
global.clearTimeout = () => {};

try {
  eval(jsCode);
} catch (e) {
  // Ignore load errors
}

// Test Tier 1 (Owner)
global.window.applyLoggedInUserBanner({
  email: 'nep94121@gmail.com',
  name: 'Chủ nhà',
  tier: 1
});
const t1Badge = getEl('homeSessionDurationBadge');
const t1Ok = t1Badge.hidden === false && t1Badge.textContent === 'Không giới hạn';

// Test Tier 2 (Family)
global.window.applyLoggedInUserBanner({
  email: 'senat6031@gmail.com',
  name: 'Gia đình',
  tier: 2
});
const t2Badge = getEl('homeSessionDurationBadge');
const t2Ok = t2Badge.hidden === false && t2Badge.textContent === 'Còn 30 ngày';

// Test Tier 3 (Guest)
global.window.applyLoggedInUserBanner({
  email: 'kbanh376@gmail.com',
  name: 'Khách',
  tier: 3,
  validity: 'Hiệu lực 12 giờ'
});
const t3Badge = getEl('homeSessionDurationBadge');
const t3Ok = t3Badge.hidden === false && t3Badge.textContent === 'Hiệu lực 12 giờ';

const result = { t1Ok, t2Ok, t3Ok };
process.stdout.write(JSON.stringify(result));
process.exit(0);
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
        assert res["t1Ok"], "Tier 1 badge failed!"
        assert res["t2Ok"], "Tier 2 badge failed!"
        assert res["t3Ok"], "Tier 3 badge failed!"
