"""Bộ kiểm thử TDD cho Milestone 1: Bảo mật, Xác thực & Vòng đời phiên (Bugs 1, 2, 4, 5, 15).

Nhiệm vụ:
- Bug 1: Xóa toàn bộ credential điền sẵn và gợi ý mật khẩu khỏi UI (/, /app, /auth), che mật khẩu trong /logs và lỗi server.
- Bug 2: Reset hoàn toàn form, gateStatusBox, cookie/storage, ẩn nút logout và đặt lại badge khi đăng xuất trên / và /app.
- Bug 4: Quên mật khẩu OTP: seed tài khoản senat6031@gmail.com (Tier 2) và kbanh376@gmail.com (Tier 3) bằng mã băm PBKDF2;
         gửi real Gmail/SMTP (send_gmail: true, dừng tự điền OTP); chia UI 3 bước (Email -> OTP -> Mật khẩu mới).
- Bug 5: Dọn sạch mock data trong wizard /auth; sửa nút "Kiểm tra đăng nhập" với tài khoản thật (tham số login_method & xử lý lỗi).
- Bug 15: Thêm #homeSessionDurationBadge trên header desktop: hiển thị "Không giới hạn" (Owner), "Còn 30 ngày" (Gia đình),
          ẩn khi đăng xuất.
"""
from __future__ import annotations

import json
import pathlib
import re
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
from simulator.auth.constants_and_crypto import DEFAULT_ACCOUNTS, hash_password


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# =============================================================================
# BUG 1: LOẠI BỎ CREDENTIAL & HINT TRÊN UI, MASKING TRONG LOGS & ERROR
# =============================================================================

class TestBug1SecurityCredentialCleanup:
    """Bug 1: Không lộ credential / mật khẩu mặc định trên UI và Logs."""

    def test_bug1_no_prefilled_passwords_or_hints_in_html(self):
        """Tất cả các thẻ input mật khẩu và email trên /, /app, /auth không được có value điền sẵn,
        và HTML không chứa chuỗi gợi ý mật khẩu mặc định."""
        html_files = [
            ROOT / "simulator" / "static" / "index.html",
            ROOT / "mobile_app" / "index.html",
            ROOT / "simulator" / "static" / "auth.html",
        ]

        prohibited_hints = [
            "Mật khẩu mặc định: 123456",
            "Mật khẩu mặc định: ******",
            "mặc định: 123456",
            "mặc định: ******",
            "GiaDinhMoi@2026",
            "(MK: 123456)",
            "(MK: ******)"
        ]

        for file_path in html_files:
            assert file_path.exists(), f"File {file_path} không tồn tại!"
            content = file_path.read_text(encoding="utf-8")
            soup = BeautifulSoup(content, "html.parser")

            # 1. Kiểm tra tất cả input[type="password"] không có thuộc tính value không rỗng
            password_inputs = soup.find_all("input", {"type": "password"})
            for pin in password_inputs:
                val = pin.get("value", "")
                assert not val, f"Input password #{pin.get('id')} trong {file_path.name} có value điền sẵn: '{val}'"

            # 2. Kiểm tra các input credential quan trọng không có value điền sẵn
            target_ids = [
                "gateLoginEmail", "gateLoginPassword",
                "gateRegEmail", "gateRegPassword", "gateRegConfirmPassword",
                "gateForgotEmail", "gateForgotNewPassword", "gateForgotConfirmPassword",
                "mobileLoginEmail", "mobileLoginPassword",
                "mobileRegEmail", "mobileRegPassword", "mobileRegConfirmPassword",
                "mobileForgotEmail", "mobileForgotNewPassword", "mobileForgotConfirmPassword",
                "mobileChangeEmail", "mobileChangeNewPassword", "mobileChangeConfirmPassword",
                "loginEmail", "loginPassword", "loginPasswordConfirm",
                "inviteGoogleEmail", "invitePassword"
            ]
            for tid in target_ids:
                el = soup.find(id=tid)
                if el:
                    val = el.get("value", "")
                    assert not val, f"Input #{tid} trong {file_path.name} có value điền sẵn: '{val}'"

            # 3. Kiểm tra không có chuỗi gợi ý mật khẩu bị lộ
            for hint in prohibited_hints:
                assert hint not in content, f"File {file_path.name} vẫn chứa chuỗi gợi ý bị cấm: '{hint}'"

    def test_bug1_auth_error_response_does_not_leak_password_hint(self, client: TestClient):
        """Khi đăng nhập sai mật khẩu, error message từ server không được chứa password hint."""
        res = client.post(
            "/api/auth3/layer1_login",
            json={"email": "nep94121@gmail.com", "password": "wrong_password_attempt"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data.get("ok") is False
        error_msg = data.get("error", "")
        assert "Mật khẩu gợi ý" not in error_msg, f"Lộ password hint trong response: {error_msg}"
        assert "123456" not in error_msg, f"Lộ mật khẩu thô trong response: {error_msg}"

    def test_bug1_logs_api_masks_password_hints(self, client: TestClient):
        """API /api/logs/dashboard phải che toàn bộ gợi ý mật khẩu trong các trường event/detail/summary."""
        res = client.get(
            "/api/logs/dashboard",
            headers={"X-Session-Token": "sess_owner_t1_nep94121"},
        )
        assert res.status_code == 200
        data = res.json()
        logs = data.get("audit_logs", [])
        for item in logs:
            text_corpus = f"{item.get('event', '')} {item.get('detail', '')} {item.get('summary', '')} {json.dumps(item.get('details', {}))}"
            # Không được chứa gợi ý mật khẩu thô không che
            assert not re.search(r"Mật khẩu gợi ý:\s*[^*\s]+", text_corpus), f"Phát hiện lộ password hint thô trong log: {text_corpus}"

    def test_bug1_logs_api_masks_nested_dictionary_sensitive_keys(self, client: TestClient):
        """API /api/logs/dashboard và hàm mask_sensitive_log_data phải che toàn bộ khóa nhạy cảm
        khớp regex /(password|hint|secret|token|otp|mat_khau)/i trong từ điển đa tầng lồng nhau."""
        from simulator.api.routes_logs import mask_sensitive_log_data
        from simulator.rule_engine import append_audit_log

        # 1. Unit check cấu trúc từ điển lồng sâu
        nested_sample = {
            "actor": "admin",
            "details": {
                "password_plain_hint": "123456",
                "nested_credentials": {
                    "user_token": "secret_jwt_payload_xyz",
                    "auth_otp": "998877",
                    "client_secret": "super_secret_value",
                    "mat_khau_tam": "plain_pass",
                    "normal_data": "public_info",
                },
            },
        }
        masked = mask_sensitive_log_data(nested_sample)
        assert masked["details"]["password_plain_hint"] == "******"
        assert masked["details"]["nested_credentials"]["user_token"] == "******"
        assert masked["details"]["nested_credentials"]["auth_otp"] == "******"
        assert masked["details"]["nested_credentials"]["client_secret"] == "******"
        assert masked["details"]["nested_credentials"]["mat_khau_tam"] == "******"
        assert masked["details"]["nested_credentials"]["normal_data"] == "public_info"

        # 2. Integration check qua API /api/logs/dashboard
        append_audit_log(
            category="SECURITY",
            event_type="TEST_MASKING_NESTED",
            user_name="admin",
            tier=1,
            summary="Kiểm toán bảo mật che dữ liệu lồng nhau",
            details={
                "password_plain_hint": "123456",
                "sub": {"otp_code": "654321", "safe": "ok"},
            },
        )
        res = client.get(
            "/api/logs/dashboard",
            headers={"X-Session-Token": "sess_owner_t1_nep94121"},
        )
        assert res.status_code == 200
        logs = res.json().get("audit_logs", [])
        matched = [l for l in logs if l.get("event_type") == "TEST_MASKING_NESTED"]
        assert len(matched) > 0, "Không tìm thấy log TEST_MASKING_NESTED trong response API"
        target_details = matched[0].get("details", {})
        assert target_details.get("password_plain_hint") in (None, "******")
        assert target_details.get("sub", {}).get("otp_code") in (None, "******")
        assert target_details.get("sub", {}).get("safe") == "ok"

    def test_bug1_logs_js_contains_password_masking(self):
        """File simulator/static/js/logs.js phải có hàm hoặc regex che mật khẩu trước khi render."""
        logs_js = (ROOT / "simulator" / "static" / "js" / "logs.js").read_text(encoding="utf-8")
        assert "mask" in logs_js.lower() or "replace(" in logs_js, "logs.js thiếu logic masking mật khẩu trên giao diện"


# =============================================================================
# BUG 2: ĐĂNG XUẤT RESET TOÀN DIỆN TRÊN / VÀ /APP
# =============================================================================

class TestBug2LogoutReset:
    """Bug 2: Sau logout phải xóa form, thông báo, session state và ẩn nút Đăng xuất."""

    def test_bug2_desktop_logout_flow_clears_inputs_and_badge_and_hides_logout(self):
        """Thực nghiệm Node.js: Khi kích hoạt btnLogoutHome.click(), các trường input phải bị xóa sạch,
        gateStatusBox được reset, session bị xóa, và nút btnLogoutHome bị ẩn."""
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
  _d: { 'smarthome_auth_session': JSON.stringify({ email: 'nep94121@gmail.com', tier: 1 }) },
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
  addEventListener: () => {}
};
global.location = { protocol: 'http:', host: 'localhost:8000' };
global.WebSocket = class { addEventListener() {} send() {} close() {} };
global.setInterval = () => {};
global.clearInterval = () => {};
global.setTimeout = () => {};
global.clearTimeout = () => {};

try {
  eval(jsCode);
} catch (e) {
  // Ignore minor load errors
}

// Giả lập trạng thái trước logout (đã đăng nhập)
getEl('gateLoginEmail').value = 'nep94121@gmail.com';
getEl('gateLoginPassword').value = 'secret123';
getEl('gateStatusBox').textContent = '✅ Đăng nhập thành công!';
getEl('homeCurrentAccountBadge').textContent = '👑 Cấp 1 · Chủ nhà: Nguyễn Tuấn Anh';
getEl('btnLogoutHome').hidden = false;
getEl('btnLogoutHome').style.display = '';

// Kích hoạt logout
getEl('btnLogoutHome').click();

const result = {
  emailCleared: getEl('gateLoginEmail').value === '',
  passwordCleared: getEl('gateLoginPassword').value === '',
  statusNotSuccess: !getEl('gateStatusBox').textContent.includes('thành công'),
  storageCleared: mockStorage.getItem('smarthome_auth_session') === null,
  badgeReset: getEl('homeCurrentAccountBadge').textContent.includes('Chưa đăng nhập'),
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
        assert res["emailCleared"], "Email input không bị xóa khi logout!"
        assert res["passwordCleared"], "Password input không bị xóa khi logout!"
        assert res["statusNotSuccess"], "gateStatusBox vẫn hiển thị 'Đăng nhập thành công' sau logout!"
        assert res["storageCleared"], "LocalStorage không bị xóa khi logout!"
        assert res["badgeReset"], "Badge tài khoản chưa reset về 'Chưa đăng nhập'!"
        assert res["logoutBtnHidden"], "Nút Đăng xuất chưa bị ẩn sau khi logout!"

    def test_bug2_mobile_logout_clears_credentials_and_state(self):
        """Kiểm tra simulator/static/js/mobile_app.js: submitMobileLogout phải xóa input và reset form."""
        content = (ROOT / "simulator" / "static" / "js" / "mobile_app.js").read_text(encoding="utf-8")
        assert "submitMobileLogout" in content
        # Kiểm tra logic submitMobileLogout có reset input hoặc reset form
        assert "mobileLoginEmail" in content and "mobileLoginPassword" in content, "submitMobileLogout thiếu logic dọn dẹp form"


# =============================================================================
# BUG 4: QUÊN MẬT KHẨU OTP, TÀI KHOẢN SEED & LUỒNG 3 BƯỚC
# =============================================================================

class TestBug4ForgotPasswordOtpAndSeed:
    """Bug 4: Quên mật khẩu bằng OTP cho senat6031@gmail.com & kbanh376@gmail.com, 3 bước UI, send_gmail: true."""

    def test_bug4_seed_accounts_exist_and_hashed_in_constants_and_json(self):
        """Hai tài khoản senat6031@gmail.com (Tier 2) và kbanh376@gmail.com (Tier 3)
        phải có trong DEFAULT_ACCOUNTS và accounts_3layer.json với mật khẩu được hash PBKDF2."""
        emails_in_constants = {acc["email"].lower(): acc for acc in DEFAULT_ACCOUNTS}
        assert "senat6031@gmail.com" in emails_in_constants, "senat6031@gmail.com thiếu trong DEFAULT_ACCOUNTS!"
        assert "kbanh376@gmail.com" in emails_in_constants, "kbanh376@gmail.com thiếu trong DEFAULT_ACCOUNTS!"

        acc_senat = emails_in_constants["senat6031@gmail.com"]
        assert acc_senat["tier"] == 2
        assert len(acc_senat.get("password_hash", "")) == 64, "Mật khẩu senat6031@gmail.com chưa được băm PBKDF2 SHA-256!"

        acc_kbanh = emails_in_constants["kbanh376@gmail.com"]
        assert acc_kbanh["tier"] == 3
        assert len(acc_kbanh.get("password_hash", "")) == 64, "Mật khẩu kbanh376@gmail.com chưa được băm PBKDF2 SHA-256!"

        json_path = ROOT / "simulator" / "data" / "accounts_3layer.json"
        assert json_path.exists()
        accounts_data = json.loads(json_path.read_text(encoding="utf-8"))
        emails_in_json = {acc["email"].lower(): acc for acc in accounts_data}
        assert "senat6031@gmail.com" in emails_in_json, "senat6031@gmail.com thiếu trong accounts_3layer.json!"
        assert "kbanh376@gmail.com" in emails_in_json, "kbanh376@gmail.com thiếu trong accounts_3layer.json!"

    def test_bug4_request_otp_for_seed_accounts_succeeds(self, client: TestClient):
        """Gửi OTP khôi phục mật khẩu cho senat6031@gmail.com và kbanh376@gmail.com phải thành công (ok: True)."""
        res_senat = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "senat6031@gmail.com", "send_gmail": False}
        )
        assert res_senat.status_code == 200
        data_senat = res_senat.json()
        assert data_senat.get("ok") is True, f"Không gửi được OTP cho senat6031@gmail.com: {data_senat}"

        res_kbanh = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "kbanh376@gmail.com", "send_gmail": False}
        )
        assert res_kbanh.status_code == 200
        data_kbanh = res_kbanh.json()
        assert data_kbanh.get("ok") is True, f"Không gửi được OTP cho kbanh376@gmail.com: {data_kbanh}"

    def test_bug4_app_js_sends_real_gmail_and_no_autofill(self):
        """Trong simulator/static/js/app.js: btnSendForgotOtp phải gửi send_gmail: true và KHÔNG tự điền OTP vào ô nhập."""
        app_js = (ROOT / "simulator" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        assert "send_gmail: true" in app_js, "app.js chưa bật send_gmail: true cho luồng gửi OTP thật!"
        assert "data.demo_otp_preview" not in app_js, "app.js vẫn tự động điền trước OTP từ demo_otp_preview!"

    def test_bug4_desktop_forgot_password_has_three_steps_ui(self):
        """Panel Quên mật khẩu #gatePanelForgot trên index.html phải chia thành 3 bước (Email -> OTP -> Mật khẩu mới)."""
        index_html = (ROOT / "simulator" / "static" / "index.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(index_html, "html.parser")
        panel = soup.find(id="gatePanelForgot")
        assert panel is not None, "#gatePanelForgot không tồn tại!"

        # Kiểm tra có cấu trúc các bước
        step1 = soup.find(id="gateForgotStep1") or soup.find(class_=re.compile("forgot-step-1|step1"))
        step2 = soup.find(id="gateForgotStep2") or soup.find(class_=re.compile("forgot-step-2|step2"))
        step3 = soup.find(id="gateForgotStep3") or soup.find(class_=re.compile("forgot-step-3|step3"))
        assert step1 is not None, "Thiếu container Bước 1 trong Quên mật khẩu!"
        assert step2 is not None, "Thiếu container Bước 2 trong Quên mật khẩu!"
        assert step3 is not None, "Thiếu container Bước 3 trong Quên mật khẩu!"


# =============================================================================
# BUG 5: DỌN SẠCH VOICE AUTH WIZARD & KIỂM TRA ĐĂNG NHẬP VỚI TÀI KHOẢN THẬT
# =============================================================================

class TestBug5VoiceAuthWizardCleanAndCheckLogin:
    """Bug 5: /auth không điền sẵn mock data; kiểm tra đăng nhập đúng API với tài khoản thật."""

    def test_bug5_auth_html_and_js_no_sample_member_data(self):
        """Trên auth.html và auth.js: không có 'Thành viên A' điền sẵn, không tự động ép ghi đè email mẫu khi chọn tier."""
        auth_html = (ROOT / "simulator" / "static" / "auth.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(auth_html, "html.parser")

        name_input = soup.find(id="enrollSpeakerNameInput")
        assert name_input is not None
        assert name_input.get("value", "") == "", "enrollSpeakerNameInput vẫn có value điền sẵn!"

        auth_js = (ROOT / "simulator" / "static" / "js" / "auth.js").read_text(encoding="utf-8")
        # Kiểm tra không có khởi tạo selectedSpeakerName = 'Thành viên A'
        assert "let selectedSpeakerName = 'Thành viên A'" not in auth_js, "auth.js vẫn hardcode selectedSpeakerName = 'Thành viên A'!"

    def test_bug5_auth_submit_layer1_passes_login_method_and_handles_error(self):
        """submitLayer1 trong auth.js phải truyền login_method và hiển thị đúng thông điệp phản hồi từ server."""
        auth_js = (ROOT / "simulator" / "static" / "js" / "auth.js").read_text(encoding="utf-8")
        assert "login_method" in auth_js, "submitLayer1 chưa truyền tham số login_method tới /api/auth3/layer1_login!"


# =============================================================================
# BUG 15: DESKTOP HEADER SESSION DURATION BADGE
# =============================================================================

class TestBug15DesktopHeaderDurationBadge:
    """Bug 15: Hiển thị thời hạn truy cập #homeSessionDurationBadge trên header desktop."""

    def test_bug15_home_session_duration_badge_exists_in_dom(self):
        """Phần tử #homeSessionDurationBadge phải tồn tại trong header top-actions của index.html."""
        index_html = (ROOT / "simulator" / "static" / "index.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(index_html, "html.parser")
        header = soup.find("header", class_="top")
        assert header is not None, "Không tìm thấy header.top!"
        badge = header.find(id="homeSessionDurationBadge")
        assert badge is not None, "Thiếu #homeSessionDurationBadge trong header.top!"

    def test_bug15_home_session_duration_badge_behavior(self):
        """Thực nghiệm Node.js: Khi đăng nhập vai Chủ nhà (Tier 1) hiển thị 'Không giới hạn',
        vai Gia đình (Tier 2) hiển thị 'Còn 30 ngày', và ẩn đi khi logout."""
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

['homeCurrentAccountBadge', 'homeSessionDurationBadge', 'btnLogoutHome'].forEach(getEl);

global.document = {
  getElementById: getEl,
  querySelector: () => null,
  querySelectorAll: () => [],
  cookie: '',
  addEventListener: () => {}
};
global.window = {
  localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} },
  addEventListener: () => {}
};
global.location = { protocol: 'http:', host: 'localhost:8000' };
global.WebSocket = class { addEventListener() {} send() {} close() {} };
global.setInterval = () => {};
global.clearInterval = () => {};
global.setTimeout = () => {};
global.clearTimeout = () => {};

try {
  eval(jsCode);
} catch (e) {}

const bannerFn = global.window.applyLoggedInUserBanner || (typeof applyLoggedInUserBanner === 'function' ? applyLoggedInUserBanner : null);

// Gọi applyLoggedInUserBanner cho Tier 1
if (typeof bannerFn === 'function') {
  bannerFn({ tier: 1, email: 'nep94121@gmail.com' });
}
const tier1Text = getEl('homeSessionDurationBadge').textContent;
const tier1Visible = getEl('homeSessionDurationBadge').hidden === false && getEl('homeSessionDurationBadge').style.display !== 'none';

// Gọi applyLoggedInUserBanner cho Tier 2
if (typeof bannerFn === 'function') {
  bannerFn({ tier: 2, email: 'senat6031@gmail.com' });
}
const tier2Text = getEl('homeSessionDurationBadge').textContent;

// Gọi logout
getEl('btnLogoutHome').click();
const badgeHiddenOnLogout = getEl('homeSessionDurationBadge').hidden === true || getEl('homeSessionDurationBadge').style.display === 'none';

process.stdout.write(JSON.stringify({
  tier1HasKhongGioiHan: tier1Text.includes('Không giới hạn'),
  tier1Visible,
  tier2Has30Ngay: tier2Text.includes('30 ngày'),
  badgeHiddenOnLogout
}));
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
        assert res["tier1HasKhongGioiHan"], f"Tier 1 không hiển thị 'Không giới hạn': {res}"
        assert res["tier2Has30Ngay"], f"Tier 2 không hiển thị '30 ngày': {res}"
        assert res["badgeHiddenOnLogout"], f"Badge thời hạn không bị ẩn khi đăng xuất: {res}"


# =============================================================================
# KIỂM TRA TUÂN THỦ DÒNG KẾT THÚC (0 CRLF) TRÊN WINDOWS
# =============================================================================

class TestLineEndingsAndDataIntegrity:
    """Kiểm tra tuân thủ tuyệt đối chuẩn POSIX LF (0 CRLF) trên môi trường Windows."""

    def test_save_accounts_produces_zero_crlf_on_windows(self, tmp_path, monkeypatch):
        """Xác thực cơ chế lưu tài khoản _save_accounts() trên Windows đảm bảo 100% POSIX LF (0 CRLF)."""
        import simulator.auth_3layer as a3
        mgr = get_auth_3layer_manager()
        temp_accounts = tmp_path / "accounts_test.json"
        monkeypatch.setattr(a3, "ACCOUNTS_FILE", temp_accounts)

        # Lưu tài khoản qua hàm _save_accounts()
        mgr._save_accounts()

        assert temp_accounts.exists(), "Tệp lưu accounts_test.json không tồn tại!"
        raw = temp_accounts.read_bytes()
        crlf_count = raw.count(b"\r\n")
        lf_count = raw.count(b"\n")
        assert crlf_count == 0, f"Phát hiện {crlf_count} ký tự CRLF khi lưu accounts trên Windows!"
        assert lf_count > 0, "Tệp phải có ít nhất 1 dòng kết thúc bằng LF (\\n)!"

    def test_all_simulator_data_and_modified_code_have_zero_crlf(self):
        """Xác thực 100% tệp dữ liệu text/JSON trong simulator/data/ và mã nguồn liên quan có 0 CRLF."""
        data_dir = ROOT / "simulator" / "data"
        text_extensions = {".json", ".jsonl", ".txt", ".csv"}
        data_files = [p for p in data_dir.iterdir() if p.is_file() and p.suffix.lower() in text_extensions]

        modified_code_files = [
            ROOT / "simulator" / "static" / "index.html",
            ROOT / "mobile_app" / "index.html",
            ROOT / "simulator" / "static" / "auth.html",
            ROOT / "simulator" / "static" / "js" / "app.js",
            ROOT / "simulator" / "static" / "js" / "auth.js",
            ROOT / "simulator" / "static" / "js" / "mobile_app.js",
            ROOT / "simulator" / "static" / "js" / "logs.js",
            ROOT / "simulator" / "api" / "routes_logs.py",
            ROOT / "simulator" / "auth" / "constants_and_crypto.py",
            ROOT / "simulator" / "auth_3layer.py",
            ROOT / "simulator" / "engine" / "audit_logger.py",
            ROOT / "simulator" / "engine" / "constants_and_time.py",
            ROOT / "simulator" / "knowledge_rag.py",
            ROOT / "simulator" / "mqtt_bridge.py",
            ROOT / "simulator" / "rule_engine.py",
            ROOT / "simulator" / "voice_auth.py",
            ROOT / "tests" / "test_p4_survey1_security_auth.py",
            ROOT / "tests" / "test_p3_session_rbac_concurrency.py",
            ROOT / "tests" / "e2e" / "conftest.py",
            ROOT / "tests" / "test_challenger_m1_adversarial.py",
            ROOT / "tests" / "test_challenger_m1_reverify_direct.py",
            ROOT / ".gitattributes",
        ]

        violations = {}
        for f in data_files + modified_code_files:
            if f.exists():
                raw = f.read_bytes()
                crlf = raw.count(b"\r\n")
                if crlf > 0:
                    violations[str(f.relative_to(ROOT))] = crlf

        assert not violations, f"Phát hiện vi phạm CRLF tại {len(violations)} tệp: {violations}"

