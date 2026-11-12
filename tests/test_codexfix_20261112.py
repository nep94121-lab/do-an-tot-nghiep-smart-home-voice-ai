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
