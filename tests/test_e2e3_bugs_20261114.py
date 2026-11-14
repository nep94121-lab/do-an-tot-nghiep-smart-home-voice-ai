"""Bộ kiểm thử toàn diện cho 5 lỗi E2E3 (2026-11-14):
1. P1 Link mời khách dùng một lần (/guest?token=..., /qr_expired?reason=used vs /qr_expired, cookie phiên gốc giữ nguyên).
2. P1 Từ chối mật khẩu mặc định cũ (_LEGACY_DEFAULT_HASHES) khi đăng ký và đặt lại mật khẩu (không đốt OTP hợp lệ).
3. P2 Chủ nhà OTP Lớp 2 gửi lần đầu báo "Đã gửi mã OTP 6 số tới n***@gmail.com, hiệu lực 5 phút", không kẹt "Đang gửi...", không báo nhầm "đã được gửi trước đó".
4. P2 Thông báo thành công Quên mật khẩu Chủ nhà: "Đặt lại mật khẩu thành công. Hãy đăng nhập bằng mật khẩu mới."
5. P2 Cô lập khóa đăng nhập sai theo account_id/email thật thay vì canonical_gmail_mailbox(email)|IP.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import simulator.auth_3layer as auth3_mod
from simulator.auth.constants_and_crypto import hash_password
from simulator.auth.guest_invites import create_invite, get_invite
from simulator.auth_3layer import (
    LEGACY_DEFAULT_PASSWORD_ERROR,
    _LEGACY_DEFAULT_HASHES,
    get_auth_3layer_manager,
)
from simulator.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ==============================================================================
# BUG 1 (P1): LINK MỜI DÙNG MỘT LẦN (/guest?token=...)
# ==============================================================================


class TestBug1SingleUseGuestInvite:
    """Sau lần quét/redeem đầu tiên, máy khác không có cookie phải bị từ chối và chuyển /qr_expired?reason=used."""

    def test_first_device_reloads_cleanly_while_second_device_redirects_to_used_qr(
        self, client: TestClient
    ) -> None:
        inv = create_invite(owner_user_id="tuan_anh", tier=3, ttl_sec=600)
        token = inv["token"]
        jti = inv["invite_id"]

        # Device A: mở trang khách lần đầu + redeem tạo cookie phiên
        r_page1 = client.get(f"/guest?token={token}")
        assert r_page1.status_code == 200

        r_redeem1 = client.post("/api/guest/redeem", json={"token": token})
        assert r_redeem1.status_code == 200
        d1 = r_redeem1.json()
        assert d1.get("ok") is True
        sid1 = d1.get("session_token")
        assert sid1
        assert "sh_session_token" in r_redeem1.cookies

        rec_after_first = get_invite(jti)
        assert rec_after_first is not None
        assert int(rec_after_first.get("redeem_count") or 0) == 1

        # Device A (cùng cookie): reload /guest, validate, redeem idempotent KHÔNG tăng redeem_count, bật đèn được, chặn cửa chính
        r_reload = client.get(f"/guest?token={token}")
        assert r_reload.status_code == 200
        r_val1 = client.get("/api/guest/invite/validate", params={"token": token})
        assert r_val1.status_code == 200
        assert r_val1.json().get("valid") is True
        r_redeem_same = client.post("/api/guest/redeem", json={"token": token})
        assert r_redeem_same.status_code == 200
        assert r_redeem_same.json().get("session_token") == sid1
        rec_after_reload = get_invite(jti)
        assert rec_after_reload is not None
        assert int(rec_after_reload.get("redeem_count") or 0) == 1

        r_light = client.post("/api/device", json={"device_id": "living_room_light", "action": "turn_on"})
        assert r_light.status_code == 200
        r_door = client.post("/api/device", json={"device_id": "main_door", "action": "open"})
        assert r_door.status_code == 403

        # Device B (máy/trình duyệt khác không có cookie phiên đã bind): bị từ chối & chuyển /qr_expired?reason=used
        client_b = TestClient(app, raise_server_exceptions=False)
        r_b_no_redir = client_b.get(f"/guest?token={token}", follow_redirects=False)
        assert r_b_no_redir.status_code in (302, 303, 307)
        loc = r_b_no_redir.headers.get("location", "")
        assert loc.endswith("/qr_expired?reason=used")

        r_b_followed = client_b.get(f"/guest?token={token}", follow_redirects=True)
        assert r_b_followed.status_code == 200
        assert "Mã QR đã được sử dụng" in r_b_followed.text

        r_b_val = client_b.get("/api/guest/invite/validate", params={"token": token})
        assert r_b_val.status_code == 403
        assert r_b_val.json().get("reason") == "used"

        r_b_redeem = client_b.post("/api/guest/redeem", json={"token": token})
        assert r_b_redeem.status_code == 403
        b_red_data = r_b_redeem.json()
        assert b_red_data.get("ok") is False
        assert b_red_data.get("reason") == "used"
        assert b_red_data.get("redirect") == "/qr_expired?reason=used"
        assert "Mã QR đã được sử dụng" in b_red_data.get("error", "")

        # Số lần redeem giữ nguyên 1
        assert int((get_invite(jti) or {}).get("redeem_count") or 0) == 1

    def test_direct_qr_expired_still_shows_expired_not_used(self, client: TestClient) -> None:
        r_direct = client.get("/qr_expired")
        assert r_direct.status_code == 200
        assert "Mã QR đã hết hạn" in r_direct.text
        assert "Mã QR đã được sử dụng" not in r_direct.text

        r_used = client.get("/qr_expired?reason=used")
        assert r_used.status_code == 200
        assert "Mã QR đã được sử dụng" in r_used.text

    def test_invite_registration_consumes_single_use_invite(self, client: TestClient) -> None:
        inv = create_invite(owner_user_id="tuan_anh", tier=3, ttl_sec=600)
        token = inv["token"]
        email = f"guest.e2e3.{uuid.uuid4().hex[:8]}@gmail.com"
        r_reg = client.post(
            "/api/auth3/register_or_set_password",
            json={
                "email": email,
                "password": "SafeGuest#2026",
                "confirm_password": "SafeGuest#2026",
                "display_name": "Guest Invite Once",
                "invite_token": token,
            },
        )
        assert r_reg.status_code == 200
        assert r_reg.json().get("ok") is True

        client_other = TestClient(app, raise_server_exceptions=False)
        r_reuse = client_other.post("/api/guest/redeem", json={"token": token})
        assert r_reuse.status_code == 403
        assert r_reuse.json().get("reason") == "used"

    def test_qr_expired_and_guest_control_js_used_reason_behavior(self) -> None:
        node_script = """
const fs = require('fs');
const vm = require('vm');
const qrJs = fs.readFileSync('simulator/static/js/qr_expired.js', 'utf8');

function runQrJs(searchStr) {
  const elems = {
    qrExpiredTitle: { textContent: 'Mã QR đã hết hạn' },
    qrExpiredDesc: { textContent: 'Liên kết mã QR hoặc mã mời này đã quá thời hạn hiệu lực hoặc đã bị Chủ nhà thu hồi.' },
  };
  const doc = {
    title: 'Mã QR hết hạn · Nhà thông minh',
    getElementById: (id) => elems[id] || null,
  };
  const win = { location: { search: searchStr } };
  const sandbox = { window: win, document: doc, URLSearchParams };
  vm.createContext(sandbox);
  vm.runInContext(qrJs, sandbox);
  return { title: doc.title, h1: elems.qrExpiredTitle.textContent, desc: elems.qrExpiredDesc.textContent };
}

const usedRes = runQrJs('?reason=used');
if (usedRes.h1 !== 'Mã QR đã được sử dụng' || !usedRes.title.includes('Mã QR đã được sử dụng')) {
  console.error('qr_expired.js ?reason=used mismatch:', usedRes);
  process.exit(1);
}
const expRes = runQrJs('');
if (expRes.h1 !== 'Mã QR đã hết hạn') {
  console.error('qr_expired.js default mismatch:', expRes);
  process.exit(1);
}

const guestJs = fs.readFileSync('simulator/static/js/guest_control.js', 'utf8');
let replacedUrl = '';
const stubEl = () => ({ textContent: '', innerHTML: '', hidden: false, style: {}, addEventListener() {}, dataset: {} });
const gElems = {};
let domCb = null;
const gSandbox = {
  window: {
    location: { search: '?token=inv_used', replace: (u) => { replacedUrl = u; } },
  },
  document: {
    cookie: '',
    getElementById: (id) => (gElems[id] = gElems[id] || stubEl()),
    querySelectorAll: () => [],
    addEventListener: (ev, fn) => { if (ev === 'DOMContentLoaded') domCb = fn; },
  },
  URLSearchParams,
  fetch: async () => ({
    ok: false,
    status: 403,
    json: async () => ({ ok: false, valid: false, reason: 'used', redirect: '/qr_expired?reason=used', error: 'Mã QR đã được sử dụng.' }),
  }),
  console,
  setTimeout,
  clearTimeout,
};
vm.createContext(gSandbox);
vm.runInContext(guestJs, gSandbox);
(async () => {
  if (typeof domCb === 'function') {
    await domCb();
  } else {
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  if (replacedUrl !== '/qr_expired?reason=used') {
    console.error('guest_control.js did not redirect to /qr_expired?reason=used:', replacedUrl);
    process.exit(1);
  }
  console.log('QR_EXPIRED_AND_GUEST_USED_JS_OK');
})();
"""
        proc = subprocess.run(["node", "-e", node_script], cwd=str(ROOT), capture_output=True, text=True, timeout=15)
        assert proc.returncode == 0, proc.stderr or proc.stdout
        assert "QR_EXPIRED_AND_GUEST_USED_JS_OK" in proc.stdout

    def test_failed_redeem_session_creation_rolls_back_invite(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from simulator.auth.session_store import get_session_store

        inv = create_invite(owner_user_id="tuan_anh", tier=3, ttl_sec=600)
        token = inv["token"]
        invite_id = inv["invite_id"]
        store = get_session_store()

        def boom(*args, **kwargs):
            raise RuntimeError("session store unavailable")

        monkeypatch.setattr(store, "create_session", boom)
        r_fail = client.post("/api/guest/redeem", json={"token": token})
        assert r_fail.status_code == 500
        assert int((get_invite(invite_id) or {}).get("redeem_count") or 0) == 0

        monkeypatch.undo()
        r_ok = client.post("/api/guest/redeem", json={"token": token})
        assert r_ok.status_code == 200
        assert r_ok.json().get("ok") is True
        assert int((get_invite(invite_id) or {}).get("redeem_count") or 0) == 1


# ==============================================================================
# BUG 2 (P1): TỪ CHỐI MẬT KHẨU MẶC ĐỊNH CŨ (_LEGACY_DEFAULT_HASHES)
# ==============================================================================


class TestBug2RejectLegacyDefaultPasswords:
    """register_or_update_password và reset_password_with_otp từ chối mật khẩu nằm trong _LEGACY_DEFAULT_HASHES."""

    def test_legacy_default_hashes_table_present(self) -> None:
        assert len(_LEGACY_DEFAULT_HASHES) >= 4
        for h in _LEGACY_DEFAULT_HASHES:
            assert len(h) == 64

    def test_register_and_reset_reject_legacy_default_password_without_burning_otp(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        legacy_plain = "LegacyOldDefault#2026"
        monkeypatch.setattr(
            auth3_mod,
            "_LEGACY_DEFAULT_HASHES",
            frozenset(auth3_mod._LEGACY_DEFAULT_HASHES) | {hash_password(legacy_plain)},
        )

        # 1. Đăng ký với mật khẩu mặc định cũ -> HTTP 400 + đúng thông báo
        reg_email = f"legacy.reg.{uuid.uuid4().hex[:8]}@gmail.com"
        r_reg = client.post(
            "/api/auth3/register_or_set_password",
            json={
                "email": reg_email,
                "password": legacy_plain,
                "confirm_password": legacy_plain,
                "display_name": "Legacy Test",
            },
        )
        assert r_reg.status_code == 400
        assert r_reg.json().get("ok") is False
        assert r_reg.json().get("error") == LEGACY_DEFAULT_PASSWORD_ERROR

        # 2. Đặt lại mật khẩu (forgot_password_reset) với mật khẩu mặc định cũ -> HTTP 400, KHÔNG tiêu hủy OTP
        mgr = get_auth_3layer_manager()
        user_email = f"legacy.rst.{uuid.uuid4().hex[:8]}@gmail.com"
        ok_reg = mgr.register_or_update_password(
            email=user_email,
            password="InitialSafe#111",
            confirm_password="InitialSafe#111",
            display_name="Legacy Reset User",
            target_tier=2,
            source="pytest_e2e3",
        )
        assert ok_reg.get("ok") is True
        acc = mgr.find_account(user_email)
        assert acc is not None
        acc["permission_active"] = True
        acc["permission_status"] = "ACTIVE"
        mgr._save_accounts()

        otp_send = mgr.request_password_reset_otp(email=user_email, send_gmail=False, source="pytest_e2e3")
        assert otp_send.get("ok") is True
        otp_code = mgr.pending_otps[user_email]["otp_code"]

        r_bad_reset = client.post(
            "/api/auth3/forgot_password_reset",
            json={
                "email": user_email,
                "otp_code": otp_code,
                "new_password": legacy_plain,
                "confirm_password": legacy_plain,
            },
        )
        assert r_bad_reset.status_code == 400
        assert r_bad_reset.json().get("ok") is False
        assert r_bad_reset.json().get("error") == LEGACY_DEFAULT_PASSWORD_ERROR

        # OTP vẫn còn nguyên hiệu lực để thử lại mật khẩu an toàn khác
        new_safe = "BrandNewSafe#789"
        r_good_reset = client.post(
            "/api/auth3/forgot_password_reset",
            json={
                "email": user_email,
                "otp_code": otp_code,
                "new_password": new_safe,
                "confirm_password": new_safe,
            },
        )
        assert r_good_reset.status_code == 200
        assert r_good_reset.json().get("ok") is True

        r_login = client.post(
            "/api/auth3/layer1_login",
            json={"email": user_email, "password": new_safe, "send_gmail": False},
        )
        assert r_login.status_code == 200
        assert r_login.json().get("ok") is True


# ==============================================================================
# BUG 3 (P2) & BUG 4 (P2): CHỦ NHÀ OTP LỚP 2 LẦN ĐẦU & THÔNG BÁO QUÊN MẬT KHẨU
# ==============================================================================


class TestBug3And4OwnerOtpFirstSendAndForgotMessage:
    """Chủ nhà nhận đúng thông báo OTP lần đầu (ẩn email, không dính cooldown/Đang gửi) và thông báo reset mật khẩu."""

    def test_owner_layer2_otp_first_send_backend_and_cooldown_on_resend(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mgr = get_auth_3layer_manager()
        owner_acc = mgr.find_account("nep94121@gmail.com")
        assert owner_acc is not None
        monkeypatch.setitem(owner_acc, "password_hash", hash_password("OwnerTmpTest#2026"))
        monkeypatch.setattr(
            mgr,
            "send_real_gmail_otp",
            lambda *a, **kw: {"sent_real_gmail": True, "actual_recipient": "nep94121@gmail.com"},
        )

        # Case A: layer1_login với send_gmail=True -> trả về otp_sent=True + thông báo lần đầu ngay
        r_l1_direct = client.post(
            "/api/auth3/layer1_login",
            json={"email": "nep94121@gmail.com", "password": "OwnerTmpTest#2026", "send_gmail": True},
        )
        assert r_l1_direct.status_code == 200
        d_l1 = r_l1_direct.json()
        assert d_l1.get("otp_required") is True
        assert d_l1.get("otp_sent") is True
        assert d_l1.get("cooldown_active") is False
        assert d_l1.get("masked_email") == "n***@gmail.com"
        assert d_l1.get("message") == "Đã gửi mã OTP 6 số tới n***@gmail.com, hiệu lực 5 phút"
        assert "đã được gửi trước đó" not in d_l1.get("message", "")

        # Lần gọi lại layer2_send_otp ngay sau đó (bấm gửi lại trong 60s) -> báo cooldown "đã được gửi trước đó"
        r_resend = client.post("/api/auth3/layer2_send_otp", json={"email": "nep94121@gmail.com"})
        assert r_resend.status_code == 200
        d_resend = r_resend.json()
        assert d_resend.get("cooldown_active") is True
        assert "đã được gửi trước đó" in d_resend.get("message", "")

        # Case B: layer1_login với send_gmail=False -> lần gọi layer2_send_otp ĐẦU TIÊN phải báo đã gửi (chưa cooldown)
        r_l1_defer = client.post(
            "/api/auth3/layer1_login",
            json={"email": "nep94121@gmail.com", "password": "OwnerTmpTest#2026", "send_gmail": False},
        )
        assert r_l1_defer.status_code == 200
        assert r_l1_defer.json().get("otp_sent") is False

        r_l2_first = client.post("/api/auth3/layer2_send_otp", json={"email": "nep94121@gmail.com"})
        assert r_l2_first.status_code == 200
        d_l2_first = r_l2_first.json()
        assert d_l2_first.get("cooldown_active") is False
        assert d_l2_first.get("masked_email") == "n***@gmail.com"
        assert d_l2_first.get("message") == "Đã gửi mã OTP 6 số tới n***@gmail.com, hiệu lực 5 phút"
        assert "đã được gửi trước đó" not in d_l2_first.get("message", "")

    def test_auth_pages_js_login_first_otp_no_duplicate_send_and_no_stuck_loading(self) -> None:
        node_script = """
const fs = require('fs');
const vm = require('vm');
const jsCode = fs.readFileSync('simulator/static/js/auth_pages.js', 'utf8');

const elems = {
  loginForm: { style: {}, addEventListener(ev, fn) { if (ev === 'submit') this.onSubmit = fn; } },
  pageLoginEmail: { value: 'nep94121@gmail.com', setAttribute() {}, removeAttribute() {}, focus() {}, addEventListener() {} },
  pageLoginPassword: { value: 'OwnerPass#2026', setAttribute() {}, removeAttribute() {}, focus() {}, addEventListener() {} },
  pageLoginSubmitBtn: { disabled: false, textContent: 'Đăng nhập' },
  loginStatusBox: { textContent: '', style: {}, className: '' },
  loginOtpSection: { style: {}, hidden: true },
  loginOtpDesc: { textContent: '' },
  loginOtpInput: { value: '', focus() {}, addEventListener() {} },
  btnVerifyLoginOtp: { addEventListener() {} },
  btnResendLoginOtp: { disabled: false, textContent: 'Gửi lại OTP', addEventListener() {} },
  btnCancelLoginOtp: { addEventListener() {} },
};
let domReadyCb = null;
const fetchCalls = [];
const sandbox = {
  document: {
    getElementById: (id) => elems[id] || null,
    addEventListener: (ev, fn) => { if (ev === 'DOMContentLoaded') domReadyCb = fn; },
    cookie: '',
  },
  localStorage: { setItem() {}, getItem: () => null },
  sessionStorage: { setItem() {}, getItem: () => null },
  location: { protocol: 'http:', search: '' },
  fetch: async (url, init) => {
    fetchCalls.push(url);
    return {
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({
        ok: true,
        otp_required: true,
        otp_sent: true,
        cooldown_remaining_seconds: 60,
        masked_email: 'n***@gmail.com',
        message: 'Đã gửi mã OTP 6 số tới n***@gmail.com, hiệu lực 5 phút',
      }),
    };
  },
  setInterval: () => 1,
  clearInterval: () => {},
  setTimeout,
  console,
};
vm.createContext(sandbox);
vm.runInContext(jsCode, sandbox);
domReadyCb();

(async () => {
  await elems.loginForm.onSubmit({ preventDefault() {} });
  if (fetchCalls.length !== 1 || fetchCalls[0] !== '/api/auth3/layer1_login') {
    console.error('Expected single /api/auth3/layer1_login call when otp_sent=true, got:', fetchCalls);
    process.exit(1);
  }
  const expected = 'Đã gửi mã OTP 6 số tới n***@gmail.com, hiệu lực 5 phút';
  if (elems.loginOtpDesc.textContent !== expected) {
    console.error('loginOtpDesc mismatch:', elems.loginOtpDesc.textContent);
    process.exit(1);
  }
  if (elems.loginStatusBox.textContent !== expected) {
    console.error('loginStatusBox mismatch:', elems.loginStatusBox.textContent);
    process.exit(1);
  }
  if (elems.loginOtpDesc.textContent.includes('nep94121@gmail.com') || elems.loginOtpDesc.textContent.includes('Đang gửi')) {
    console.error('Leaked raw email or stuck loading in loginOtpDesc:', elems.loginOtpDesc.textContent);
    process.exit(1);
  }
  console.log('AUTH_PAGES_OTP_FIRST_SEND_OK');
})();
"""
        proc = subprocess.run(["node", "-e", node_script], cwd=str(ROOT), capture_output=True, text=True, timeout=15)
        assert proc.returncode == 0, proc.stderr or proc.stdout
        assert "AUTH_PAGES_OTP_FIRST_SEND_OK" in proc.stdout

    def test_mobile_and_app_js_no_unmasked_seed_email_or_forced_resend(self) -> None:
        mobile_js = (ROOT / "simulator" / "static" / "js" / "mobile_app.js").read_text(encoding="utf-8")
        app_js = (ROOT / "simulator" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        assert "if (data.otp_sent === true)" in mobile_js
        assert "if (!data.otp_sent && !data.sent_real_gmail)" in app_js
        assert "maskedEmail" in app_js

    def test_owner_forgot_password_reset_returns_verbatim_success_message(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mgr = get_auth_3layer_manager()
        owner_acc = mgr.find_account("nep94121@gmail.com")
        assert owner_acc is not None
        monkeypatch.setitem(owner_acc, "password_hash", hash_password("OwnerTmpBefore#1"))
        monkeypatch.setitem(owner_acc, "otp_cooldown_started_at", 0.0)
        monkeypatch.setattr(
            mgr,
            "send_real_gmail_otp",
            lambda *a, **kw: {"sent_real_gmail": True, "actual_recipient": "nep94121@gmail.com"},
        )

        r_send = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": True},
        )
        assert r_send.status_code == 200
        otp_code = mgr.pending_otps["nep94121@gmail.com"]["otp_code"]

        r_reset = client.post(
            "/api/auth3/forgot_password_reset",
            json={
                "email": "nep94121@gmail.com",
                "otp_code": otp_code,
                "new_password": "OwnerTmpAfter#2026",
                "confirm_password": "OwnerTmpAfter#2026",
            },
        )
        assert r_reset.status_code == 200
        d_reset = r_reset.json()
        assert d_reset.get("ok") is True
        assert d_reset.get("message") == "Đặt lại mật khẩu thành công. Hãy đăng nhập bằng mật khẩu mới."


# ==============================================================================
# BUG 5 (P2): CÔ LẬP KHÓA ĐĂNG NHẬP THEO ACCOUNT_ID / EMAIL THẬT
# ==============================================================================


class TestBug5LoginLockoutKeyIsolation:
    """Đăng nhập sai bằng alias nep94121+tag@gmail.com không được cộng/xóa bộ đếm khóa của Chủ nhà."""

    def test_unregistered_alias_failures_do_not_lock_owner_while_locked_owner_blocks_alias(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mgr = get_auth_3layer_manager()
        mgr._login_rate_limits.clear()
        owner_acc = mgr.find_account("nep94121@gmail.com")
        assert owner_acc is not None
        monkeypatch.setitem(owner_acc, "password_hash", hash_password("OwnerRealPass#2026"))

        # 5 lần sai với nep94121+tag@gmail.com và 5 lần sai với nep94121+e2e1114a@gmail.com cùng IP
        for alias in ("nep94121+tag@gmail.com", "nep94121+e2e1114a@gmail.com"):
            for i in range(4):
                r = client.post(
                    "/api/auth3/layer1_login",
                    json={"email": alias, "password": "WrongPass!99", "send_gmail": False},
                )
                assert r.status_code == 401, f"{alias} attempt {i+1}: expected 401, got {r.status_code}"
            r5 = client.post(
                "/api/auth3/layer1_login",
                json={"email": alias, "password": "WrongPass!99", "send_gmail": False},
            )
            assert r5.status_code == 429, f"{alias} attempt 5: expected 429, got {r5.status_code}"

        # Chủ nhà nep94121@gmail.com vẫn đăng nhập ĐÚNG được (không hề bị alias làm khóa!)
        r_owner_ok = client.post(
            "/api/auth3/layer1_login",
            json={"email": "nep94121@gmail.com", "password": "OwnerRealPass#2026", "send_gmail": False},
        )
        assert r_owner_ok.status_code == 200
        assert r_owner_ok.json().get("ok") is True

        # Reset sạch, rồi khóa chính Chủ nhà (nep94121@gmail.com) -> khóa theo acct:tuan_anh|<ip>
        mgr._login_rate_limits.clear()
        for _ in range(4):
            r_bad = client.post(
                "/api/auth3/layer1_login",
                json={"email": "nep94121@gmail.com", "password": "WrongOwner!99", "send_gmail": False},
            )
            assert r_bad.status_code == 401
        r_lock = client.post(
            "/api/auth3/layer1_login",
            json={"email": "nep94121@gmail.com", "password": "WrongOwner!99", "send_gmail": False},
        )
        assert r_lock.status_code == 429

        # Khi chính Chủ nhà đã bị khóa, thử đăng nhập qua alias chưa đăng ký cũng bị chặn 429
        r_alias_blocked = client.post(
            "/api/auth3/layer1_login",
            json={"email": "nep94121+probe1114@gmail.com", "password": "OwnerRealPass#2026", "send_gmail": False},
        )
        assert r_alias_blocked.status_code == 429
