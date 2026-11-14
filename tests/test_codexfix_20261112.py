"""Regression coverage for production security boundaries, recovery and invite lifetimes."""
from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from simulator.server import app
from simulator.auth import guest_invites, owner_pin
from simulator.auth.session_store import get_session_store, resolve_request_session
from simulator.auth_3layer import get_auth_3layer_manager, hash_password


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")
    return TestClient(app)


def owner_login(client, monkeypatch):
    account = get_auth_3layer_manager().find_account("nep94121@gmail.com")
    monkeypatch.setitem(account, "password_hash", hash_password("fixture-password"))
    response = client.post("/api/auth3/layer1_login", json={
        "email": account["email"], "password": "fixture-password", "send_gmail": False,
    })
    assert response.json()["ok"]
    return response.json()["session_token"]


@pytest.mark.parametrize("path", ["/api/device", "/api/device_control", "/api/device/fan", "/api/devices/fan/control", "/api/session/role", "/api/text_command"])
def test_cookieless_always_401(client, path):
    from simulator.api.deps import _REST_ENGINE
    _REST_ENGINE.set_active_user("tuan_anh")
    response = client.post(path, json={"device_id": "fan", "action": "on", "text": "bật quạt", "role": "MEMBER", "user_id": "tuan_anh"})
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("token", ["sess_owner_t1_nep94121", "sess_family_t2_member_a", "sess_guest_t3_visitor_c"])
def test_predictable_fixture_tokens_never_work_on_vercel(client, monkeypatch, token):
    monkeypatch.setenv("VERCEL", "1")
    assert get_session_store().get_session(token) is None
    response = client.post("/api/device", headers={"X-Session-Token": token}, json={"device_id": "fan", "action": "on"})
    assert response.status_code == 401


@pytest.mark.parametrize("method", ["email_allowlist", "family_allowlist", "google_oauth"])
def test_login_method_cannot_skip_password(client, method):
    response = client.post("/api/auth3/layer1_login", json={"email": "thanhvien.a@gmail.com", "login_method": method, "send_gmail": False})
    assert response.status_code == 401
    assert not response.json().get("session_token")


def test_registration_cannot_overwrite_owner_or_existing_password(client):
    manager = get_auth_3layer_manager()
    account = manager.find_account("nep94121@gmail.com")
    before = account["password_hash"]
    result = client.post("/api/auth3/register_or_set_password", json={"email": account["email"], "password": "attacker-password", "confirm_password": "attacker-password"})
    assert result.status_code == 409
    assert account["password_hash"] == before
    assert not result.json().get("session_token")


def test_plain_gmail_registration_without_name_or_voice(client):
    result = client.post("/api/auth3/register_or_set_password", json={"email": "new.registration@gmail.com", "password": "a-password", "confirm_password": "a-password", "tier": 1})
    assert result.status_code == 200
    assert result.json()["ok"]
    account = get_auth_3layer_manager().find_account("new.registration@gmail.com")
    assert account["tier"] == 3
    assert account["needs_first_page_voice_enroll"] is False
    assert account["permission_active"] is False
    assert not result.json().get("session_token")


@pytest.mark.parametrize("email", ["a@b@gmail.com", "@gmail.com", "a@example.com", "a gmail@gmail.com"])
def test_invalid_registration_email_denied(client, email):
    result = client.post("/api/auth3/register_or_set_password", json={"email": email, "password": "a-password", "confirm_password": "a-password"})
    assert result.status_code == 400


@pytest.mark.parametrize("tier", [2, 3])
@pytest.mark.parametrize("path", ["/api/server_mode", "/api/soil_moisture", "/api/dht11", "/api/ir_learn", "/api/users/grant", "/api/auth3/guest_invites"])
def test_guests_cannot_mutate_settings_users_invites(client, tier, path):
    invite = guest_invites.create_invite(owner_user_id="tuan_anh", tier=tier)
    token = guest_invites.redeem_token(invite["token"])["session"].session_id
    response = client.post(path, headers={"X-Session-Token": token}, json={"server_connected": False, "device_id": "main_door", "pin": "2468", "pin_confirm": "2468"})
    assert response.status_code in (401, 403)
    assert not response.json()["ok"]


@pytest.mark.parametrize("path", ["/api/auth3/guest_qr_current", "/api/auth3/qr/generate", "/api/auth3/create_invite_link"])
def test_all_qr_aliases_require_pin(client, monkeypatch, path):
    owner_login(client, monkeypatch)
    assert client.post(path, json={"tier": 3}).status_code == 400
    result = client.post(path, json={"tier": 3, "pin": "2468", "pin_confirm": "2468"})
    assert result.status_code == 200
    assert result.json()["token"].startswith("inv_")


def test_pin_and_otp_hashing_lock_expiry_single_use(client, monkeypatch):
    assert owner_pin.setup_or_replace_pin("2468", "2468")["ok"]
    assert "2468" not in json.dumps(owner_pin._CACHE)
    for _ in range(5):
        owner_pin.verify_pin("1111")
    assert owner_pin.verify_pin("2468")["status_code"] == 423
    issued, code = owner_pin.issue_reset_otp()
    assert code not in json.dumps(owner_pin._CACHE)
    assert owner_pin.issue_reset_otp()[0]["status_code"] == 429
    assert owner_pin.reset_pin_with_otp(code, "9876", "9876")["ok"]
    assert not owner_pin.reset_pin_with_otp(code, "1111", "1111")["ok"]
    monkeypatch.setitem(owner_pin._CACHE, "otp_issued_at", 0)
    _, expired = owner_pin.issue_reset_otp()
    monkeypatch.setitem(owner_pin._CACHE, "otp_expires_at", time.time() - 1)
    assert not owner_pin.reset_pin_with_otp(expired, "1111", "1111")["ok"]


def test_pin_reset_code_attempt_limit(client):
    _, code = owner_pin.issue_reset_otp()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert not owner_pin.reset_pin_with_otp(wrong, "1234", "1234")["ok"]
    assert owner_pin.reset_pin_with_otp(code, "1234", "1234")["status_code"] == 423


def test_invited_registration_and_relogin_bound_to_invite(client):
    invite = guest_invites.create_invite(owner_user_id="tuan_anh", tier=2, ttl_sec=60)
    result = client.post("/api/auth3/register_or_set_password", json={"email": "short.invite@gmail.com", "password": "a-password", "confirm_password": "a-password", "invite_token": invite["token"]})
    assert result.json()["ok"]
    token = result.json()["session_token"]
    session = get_session_store().get_session(token)
    assert session.expires_at <= invite["expires_at"]
    guest_invites.revoke_invite(invite["invite_id"])
    assert client.post("/api/device", json={"device_id": "fan", "action": "on"}, headers={"X-Session-Token": token}).status_code == 401
    assert client.post("/api/auth3/layer1_login", json={"email": "short.invite@gmail.com", "password": "a-password", "send_gmail": False}).status_code == 403


def test_revoked_stateless_session_cannot_reappear(client):
    invite = guest_invites.create_invite(owner_user_id="tuan_anh", tier=3)
    token = guest_invites.redeem_token(invite["token"])["session"].session_id
    # Simulate another worker decoding a signed token without its revocation cache.
    guest_invites.revoke_invite(invite["invite_id"])
    get_session_store()._revoked_sids.discard(token)
    request = SimpleNamespace(headers={"X-Session-Token": token}, cookies={}, query_params={})
    # Real HTTP headers are case insensitive.
    request.headers = {"x-session-token": token}
    assert not resolve_request_session(request).is_authenticated


def test_pin_storage_failure_does_not_report_setup_success(client, monkeypatch):
    from simulator.auth.security_state import SecurityStateUnavailable
    owner_login(client, monkeypatch)
    def unavailable(*args):
        raise SecurityStateUnavailable("unavailable")
    monkeypatch.setattr(owner_pin, "save_security_state", unavailable)
    response = client.post("/api/auth3/guest_invites", json={"tier": 3, "pin": "2468", "pin_confirm": "2468"})
    assert response.status_code == 503
    assert not owner_pin._CACHE.get("pin_hash")


def test_offline_mode_still_enforces_guest_device_table(client):
    from simulator.api.deps import _REST_ENGINE
    old = _REST_ENGINE.server_connected
    _REST_ENGINE.server_connected = False
    try:
        invite = guest_invites.create_invite(owner_user_id="tuan_anh", tier=3)
        token = guest_invites.redeem_token(invite["token"])["session"].session_id
        response = client.post("/api/device", json={"device_id": "garden_pump", "action": "on"}, headers={"X-Session-Token": token})
        assert response.status_code == 403
    finally:
        _REST_ENGINE.server_connected = old


def test_guest_ui_reads_snapshot_and_can_toggle_both_directions():
    """Execute the real guest script with a list snapshot, including hostile state text."""
    import subprocess
    from pathlib import Path

    script = Path("simulator/static/js/guest_control.js").read_text(encoding="utf-8")
    harness = r'''
const assert = require('node:assert/strict');
const nodes = {};
const node = () => ({hidden: true, children: [], className: '', textContent: '', appendChild(x) {this.children.push(x)}, setAttribute(k,v) {this[k]=v}, addEventListener(k,fn) {this[k]=fn}, set innerHTML(v) { assert.equal(v, ''); this.children=[]; }});
global.document = {getElementById(id) {return nodes[id] ||= node()}, createElement: node};
global.window = {location: {search:'?token=test-invite'}};
let state = 'OFF';
const actions = [];
global.fetch = async (url, options) => {
 let data;
 if (url.includes('permissions')) data={device_min_tiers:{main_door:1,alarm_siren:1,ac:2,garden_pump:2,living_room_light:3,bedroom_light:3,fan:3}};
 else if(url.includes('redeem')) data={ok:true,tier:3,session_token:'session'};
 else if(url==='/api/state') data={devices:[{id:'fan',state}]};
 else { const body=JSON.parse(options.body); actions.push(body.action); state=body.action==='on'?'ON':'OFF'; data={ok:true,snapshot:{devices:[{id:'fan',state}]}}; }
 return {ok:true,json:async()=>data};
};
'''
    assertions = r'''
setTimeout(async () => {
 const cards = () => nodes.guestDeviceGrid.children;
 assert.equal(cards().length,3);
 assert(!cards().some(x => x['data-device-id']==='main_door'));
 const fan = () => cards().find(x => x['data-device-id']==='fan');
 assert.equal(fan().children[1].textContent,'Trạng thái: OFF');
 await fan().children[2].click();
 await new Promise(resolve => setImmediate(resolve));
 assert.equal(fan().children[1].textContent,'Trạng thái: ON');
 await fan().children[2].click();
 await new Promise(resolve => setImmediate(resolve));
 assert.deepEqual(actions,['on','off']);
},0);
'''
    result = subprocess.run(["node", "-e", harness + script + assertions], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_websocket_guest_cannot_toggle_door_or_change_settings(client):
    invite = guest_invites.create_invite(owner_user_id="tuan_anh", tier=3)
    token = guest_invites.redeem_token(invite["token"])["session"].session_id
    with client.websocket_connect("/ws", headers={"X-Session-Token": token}) as ws:
        ws.send_json({"type": "set_server_mode", "server_connected": False})
        for _ in range(20):
            response = ws.receive_json()
            if response.get("type") == "rbac_blocked":
                assert response["action"] == "set_server_mode"
                break
        else:
            pytest.fail("No settings denial")
        ws.send_json({"type": "manual_toggle", "device_id": "main_door", "action": "open", "role": "ADMIN", "tier": 1})
        for _ in range(20):
            response = ws.receive_json()
            if response.get("type") == "manual_toggle_ack":
                assert not response["ok"]
                break
        else:
            pytest.fail("No door denial")


def test_vercel_guest_routes_use_backend_token_validation():
    from pathlib import Path
    config = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
    assert next(route for route in config["routes"] if route["src"] == "^/guest/?$")["dest"] == "/api/index.py"


def test_security_cloud_load_failure_is_not_first_pin_setup(monkeypatch, tmp_path):
    from simulator.auth.security_state import load_security_state, SecurityStateUnavailable
    from simulator.durable_store import get_durable_store
    monkeypatch.setenv("VERCEL", "1")
    store = get_durable_store()
    monkeypatch.setattr(store, "_load_bundle_from_upstash_kv", lambda: None)
    monkeypatch.setattr(store, "_load_bundle_from_gmail_imap", lambda: None)
    with pytest.raises(SecurityStateUnavailable):
        load_security_state("owner_pin.json", tmp_path)


@pytest.mark.parametrize("tier", [2, 3])
def test_guest_text_cannot_reset_or_write_sensor(client, tier):
    token = guest_invites.redeem_token(guest_invites.create_invite(owner_user_id="tuan_anh", tier=tier)["token"])["session"].session_id
    for text in ("reset hệ thống", "chỉnh độ ẩm đất thành 10%", "đặt nhiệt độ 100", "học lệnh remote"):
        response = client.post("/api/text_command", json={"text": text}, headers={"X-Session-Token": token})
        assert response.status_code == 403


def test_pin_mail_failure_returns_503_without_code(client, monkeypatch):
    owner_login(client, monkeypatch)
    monkeypatch.setattr(owner_pin, "send_reset_email", lambda code: {"ok": False})
    response = client.post("/api/auth3/owner_pin/forgot", json={})
    assert response.status_code == 503
    assert "otp_code_for_test" not in response.json()


def test_mailer_recognizes_failed_delivery(monkeypatch):
    monkeypatch.delenv("SIMULATOR_OFFLINE_SANDBOX", raising=False)
    monkeypatch.setattr(get_auth_3layer_manager(), "send_real_gmail_otp", lambda **kwargs: {"sent_real_gmail": False})
    assert owner_pin.send_reset_email("123456")["ok"] is False


def test_owner_pin_forgot_email_failure_rolls_back_otp_and_cooldown(client, monkeypatch):
    owner_pin.reset_owner_pin_store_for_tests()
    owner_login(client, monkeypatch)
    monkeypatch.setattr(owner_pin, "send_reset_email", lambda code: {"ok": False})
    failed = client.post("/api/auth3/owner_pin/forgot", json={})
    assert failed.status_code == 503
    assert not (owner_pin._CACHE or {}).get("otp_hash")
    assert not (owner_pin._CACHE or {}).get("otp_issued_at")

    monkeypatch.setattr(owner_pin, "send_reset_email", lambda code: {"ok": True, "sent": True})
    retried = client.post("/api/auth3/owner_pin/forgot", json={})
    assert retried.status_code == 200
    assert retried.json()["ok"] is True


def test_run_tests_endpoints_require_owner_admin_session(client, monkeypatch):
    for path in ("/api/auth3/run_tests", "/api/auth3/run_test_suite"):
        anon = client.post(path, json={"send_real_gmail": False})
        assert anon.status_code == 401

    guest_token = guest_invites.redeem_token(guest_invites.create_invite(owner_user_id="tuan_anh", tier=3)["token"])["session"].session_id
    for path in ("/api/auth3/run_tests", "/api/auth3/run_test_suite"):
        guest = client.post(path, json={"send_real_gmail": False}, headers={"X-Session-Token": guest_token})
        assert guest.status_code == 403

    admin_token = owner_login(client, monkeypatch)
    ok = client.post("/api/auth3/run_tests", json={"send_real_gmail": False}, headers={"X-Session-Token": admin_token})
    assert ok.status_code == 200
    assert ok.json()["total"] == 14
    assert len(ok.json()["results"]) == 14


def test_ui_pending_registration_does_not_unlock_gate_without_session_token():
    import subprocess
    from pathlib import Path

    node_script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');

function runWebCase(apiPayload) {
  const elements = {};
  const getEl = (id) => {
    if (!elements[id]) {
      elements[id] = {
        id, value: '', textContent: '', innerHTML: '', hidden: false, disabled: false,
        style: {}, dataset: {}, listeners: {},
        classList: { _s: new Set(), add(c){this._s.add(c);}, remove(c){this._s.delete(c);}, contains(c){return this._s.has(c);} },
        addEventListener(e, fn){ (this.listeners[e] ||= []).push(fn); },
        setAttribute(k, v){ this[k] = v; },
        removeAttribute(k){ delete this[k]; }
      };
    }
    return elements[id];
  };
  [
    'homeLoginGateModal','btnCloseLoginGateModal','btnLogoutHome','homeCurrentAccountBadge',
    'homeSessionDurationBadge','btnTabGateLogin','btnTabGateRegister','btnTabGateForgot',
    'gatePanelLogin','gatePanelRegister','gatePanelForgot','gateStatusBox',
    'btnSubmitGateLogin','btnSubmitGateRegister','btnSubmitForgotReset',
    'gateLoginEmail','gateLoginPassword','gateRegTier','gateRegName','gateRegEmail',
    'gateRegPassword','gateRegConfirmPassword','gateForgotEmail','gateForgotOtpInput',
    'gateForgotNewPassword','gateForgotConfirmPassword'
  ].forEach(getEl);
  getEl('btnCloseLoginGateModal').hidden = true;
  getEl('gateRegEmail').value = 'pending.user@gmail.com';
  getEl('gateRegName').value = 'Pending User';
  getEl('gateRegPassword').value = 'secret123';
  getEl('gateRegConfirmPassword').value = 'secret123';

  const store = { _d: {}, getItem(k){return this._d[k] ?? null;}, setItem(k,v){this._d[k]=String(v);}, removeItem(k){delete this._d[k];} };
  const scheduled = [];
  global.document = { getElementById: getEl, querySelector: () => null, querySelectorAll: () => [], cookie: '', addEventListener: () => {} };
  global.window = { localStorage: store, sessionStorage: store, location: { search: '' }, addEventListener: () => {} };
  global.location = { protocol: 'http:', host: 'localhost:8000', search: '' };
  global.WebSocket = class { addEventListener(){} send(){} close(){} };
  global.setInterval = () => 1;
  global.clearInterval = () => {};
  global.clearTimeout = () => {};
  global.setTimeout = (fn) => { scheduled.push(fn); return 1; };
  global.fetch = async (url) => ({
    ok: true, status: 200,
    json: async () => (String(url).includes('register_or_set_password') ? apiPayload : { ok: true, devices: [] })
  });

  const code = fs.readFileSync('simulator/static/js/app.js', 'utf8');
  try { eval(code); } catch (_) {}
  return new Promise(r => setImmediate(r)).then(() => {
    scheduled.length = 0;
    getEl('btnCloseLoginGateModal').hidden = true;
    getEl('homeLoginGateModal').classList.remove('hidden');
    const submitFn = getEl('btnSubmitGateRegister').listeners.click[0];
    return submitFn({ preventDefault(){} });
  }).then(() => {
    scheduled.forEach(fn => { try { fn(); } catch (_) {} });
    return {
      storedSession: store.getItem('smarthome_auth_session'),
      modalHidden: getEl('homeLoginGateModal').classList.contains('hidden'),
      closeBtnHidden: getEl('btnCloseLoginGateModal').hidden,
      statusText: getEl('gateStatusBox').textContent
    };
  });
}

function runMobileCase(apiPayload) {
  const elements = {};
  const getEl = (id) => {
    if (!elements[id]) {
      elements[id] = {
        id, value: '', textContent: '', innerHTML: '', hidden: false, disabled: false,
        style: {}, dataset: {},
        classList: { _s: new Set(), add(c){this._s.add(c);}, remove(c){this._s.delete(c);}, contains(c){return this._s.has(c);} },
        addEventListener(){}, setAttribute(k, v){ this[k] = v; }, removeAttribute(k){ delete this[k]; },
        querySelector: () => null, querySelectorAll: () => []
      };
    }
    return elements[id];
  };
  ['mobileRegTier','mobileRegName','mobileRegEmail','mobileRegPassword','mobileRegConfirmPassword','mobileRegMsg','mobileRegisterBtn','mobileLoginScreen','mobileMainContent','mobileBottomNav'].forEach(getEl);
  getEl('mobileMainContent').hidden = true;
  getEl('mobileRegEmail').value = 'pending.mobile@gmail.com';
  getEl('mobileRegName').value = 'Pending Mobile';
  getEl('mobileRegPassword').value = 'secret123';
  getEl('mobileRegConfirmPassword').value = 'secret123';

  const sessStore = { _d: {}, getItem(k){return this._d[k] ?? null;}, setItem(k,v){this._d[k]=String(v);}, removeItem(k){delete this._d[k];} };
  const scheduled = [];
  global.sessionStorage = sessStore;
  global.localStorage = sessStore;
  global.document = { getElementById: getEl, querySelector: () => null, querySelectorAll: () => [], cookie: '', addEventListener: () => {} };
  global.fetch = async () => ({ ok: true, status: 200, json: async () => apiPayload });
  global.window = { fetch: global.fetch, sessionStorage: sessStore, localStorage: sessStore, location: { search: '' }, addEventListener: () => {} };
  global.location = { protocol: 'http:', host: 'localhost:8000', search: '' };
  global.WebSocket = class { addEventListener(){} send(){} close(){} };
  global.setInterval = () => 1;
  global.clearInterval = () => {};
  global.clearTimeout = () => {};
  global.setTimeout = (fn) => { scheduled.push(fn); return 1; };

  const code = fs.readFileSync('simulator/static/js/mobile_app.js', 'utf8');
  try { eval(code); } catch (_) {}
  return global.window.submitMobileRegister({ preventDefault(){} }).then(() => {
    scheduled.forEach(fn => { try { fn(); } catch (_) {} });
    return {
      loggedInFlag: sessStore.getItem('mobileLoggedIn'),
      mainHidden: getEl('mobileMainContent').hidden,
      msgText: getEl('mobileRegMsg').textContent
    };
  });
}

(async () => {
  const pendingPayload = {
    ok: true,
    permission_active: false,
    message: 'Đã tạo tài khoản. Chờ chủ nhà cấp quyền hoặc xác thực mã mời.'
  };
  const webPending = await runWebCase(pendingPayload);
  assert.equal(webPending.storedSession, null);
  assert.equal(webPending.modalHidden, false);
  assert.equal(webPending.closeBtnHidden, true);
  assert.match(webPending.statusText, /Chờ chủ nhà cấp quyền/);

  const mobPending = await runMobileCase(pendingPayload);
  assert.equal(mobPending.loggedInFlag, null);
  assert.equal(mobPending.mainHidden, true);
  assert.match(mobPending.msgText, /Chờ chủ nhà cấp quyền/);

  const activePayload = {
    ok: true,
    permission_active: true,
    session_token: 'tok_invited_ok',
    account: { email: 'invited@gmail.com', display_name: 'Invited', tier: 2 },
    message: 'Đã lưu tài khoản.'
  };
  const webActive = await runWebCase(activePayload);
  assert.ok(webActive.storedSession);
  assert.equal(webActive.closeBtnHidden, false);

  const mobActive = await runMobileCase(activePayload);
  assert.equal(mobActive.loggedInFlag, '1');
})();
"""
    proc = subprocess.run(["node", "-e", node_script], cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True, timeout=20)
    assert proc.returncode == 0, proc.stderr


def test_forgot_password_email_failure_rolls_back_otp_and_does_not_fake_200_cooldown(monkeypatch, tmp_path):
    monkeypatch.setenv("SMARTHOME_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SMARTHOME_DURABLE_DIR", str(tmp_path / "durable"))
    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    from simulator.auth_3layer import get_auth_3layer_manager
    from simulator.voice_config import OWNER_EMAIL

    mgr = get_auth_3layer_manager()
    mgr.pending_otps.clear()
    monkeypatch.setattr(
        mgr,
        "send_real_gmail_otp",
        lambda *_a, **_k: {"sent_real_gmail": False, "missing_secret": "GMAIL_APP_PASSWORD", "error": "Missing GMAIL_APP_PASSWORD"},
    )

    with TestClient(app) as client:
        res1 = client.post("/api/auth3/forgot_password_send_otp", json={"email": OWNER_EMAIL, "send_gmail": True})
        assert res1.status_code == 503
        assert res1.json()["ok"] is False
        assert mgr.pending_otps.get(OWNER_EMAIL.lower()) is None
        owner_acc = mgr.find_account(OWNER_EMAIL)
        assert owner_acc is not None and owner_acc.get("pending_otp") is None

        res2 = client.post("/api/auth3/forgot_password_send_otp", json={"email": OWNER_EMAIL})
        assert res2.status_code == 503
        assert res2.json()["ok"] is False


def test_logout_endpoint_revokes_session_and_clears_httponly_cookie(monkeypatch, tmp_path):
    from simulator import durable_store
    from simulator.auth import session_store
    from simulator.voice_config import OWNER_EMAIL, OWNER_ID

    monkeypatch.setenv("SMARTHOME_DURABLE_DIR", str(tmp_path / "durable"))
    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")
    monkeypatch.setattr(durable_store, "_GLOBAL_DURABLE_STORE", None)
    isolated_store = session_store.SessionStore(db_path=tmp_path / "smarthome.db")
    monkeypatch.setattr(session_store, "_SESSION_STORE", isolated_store)

    sess = isolated_store.create_session(
        user_id=OWNER_ID,
        email=OWNER_EMAIL,
        display_name="Owner Logout Test",
        tier=1,
        role="ADMIN",
        source="logout_test",
    )
    with TestClient(app) as client:
        client.cookies.set("sh_session_token", sess.session_id)
        before = client.get("/api/state")
        assert before.status_code == 200
        assert before.json()["authenticated"] is True

        out = client.post("/api/auth/logout")
        assert out.status_code == 200
        assert out.json()["ok"] is True
        set_cookie_hdr = " ".join(out.headers.get_list("set-cookie"))
        assert "sh_session_token=" in set_cookie_hdr

        after_state = client.get("/api/state")
        assert after_state.status_code == 200
        assert after_state.json()["authenticated"] is False

        replay = client.post(
            "/api/device",
            headers={"Cookie": f"sh_session_token={sess.session_id}"},
            json={"device_id": "fan", "action": "off"},
        )
        assert replay.status_code == 401


