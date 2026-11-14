"""Regression & behavioral coverage for all 10 production E2E bugs (P1-1..P2-10)."""
from __future__ import annotations

import email
import io
import json
import pathlib
import re
import secrets
import subprocess
import urllib.error
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from simulator.auth.constants_and_crypto import canonical_gmail_mailbox
from simulator.auth.guest_invites import create_invite
from simulator.auth.invite_and_gmail_mixin import (
    HARDCODED_REAL_EMAIL_ALLOWLIST,
    is_email_allowlisted_for_real_send,
)
from simulator.auth.security_state import GitHubSecurityState
from simulator.auth.session_store import get_session_store
from simulator.auth_3layer import ThreeLayerAuthManager, get_auth_3layer_manager, hash_password
from simulator.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")
    return TestClient(app, raise_server_exceptions=False)


# ==============================================================================
# P1-1 & P1-2: Logged-out /app fail-closed, /api/session/role, no fake auth/mic
# ==============================================================================


class TestP1_1AndP1_2LoggedOutAppAndSessionRole:
    """Logged-out /app must fail closed and role must derive solely from /api/session/role."""

    def test_get_and_post_session_role_require_authentication_with_no_store(self, client: TestClient):
        for method in ("get", "post"):
            resp = getattr(client, method)("/api/session/role")
            assert resp.status_code == 401
            assert "no-store" in (resp.headers.get("cache-control") or "")
            assert "set-cookie" not in resp.headers
            data = resp.json()
            assert data.get("ok") is False
            assert data.get("authenticated") is False

        headers = {"X-Session-Token": "sess_family_t2_member_a"}
        for method in ("get", "post"):
            resp_ok = getattr(client, method)("/api/session/role", headers=headers)
            assert resp_ok.status_code == 200
            assert "no-store" in (resp_ok.headers.get("cache-control") or "")
            body = resp_ok.json()
            assert body.get("authenticated") is True
            assert body.get("tier") == 2
            assert body.get("role") == "MEMBER"
            assert body.get("active_user_id") == "thanh_vien_a"

    def test_mobile_app_static_has_no_hasFakeMic_and_no_owner_fallback_defaults(self):
        mobile_js = (ROOT / "simulator" / "static" / "js" / "mobile_app.js").read_text(encoding="utf-8")
        mobile_html = (ROOT / "mobile_app" / "index.html").read_text(encoding="utf-8")

        assert "hasFakeMic" not in mobile_js
        assert "nep94121@gmail.com" not in mobile_js
        assert "nep94121@gmail.com" not in mobile_html
        assert "/api/session/role" in mobile_js
        assert "Chưa đăng nhập" in mobile_html
        assert "Vui lòng đăng nhập" in mobile_js

    def test_mobile_app_js_logged_out_refuses_fake_voice_success(self):
        js_file = ROOT / "simulator" / "static" / "js" / "mobile_app.js"
        node_script = r"""
const fs = require('fs');
const code = fs.readFileSync(process.argv[1], 'utf8');
const els = {};
function getEl(id) {
  if (!els[id]) {
    els[id] = {
      id, value: '', textContent: '', innerHTML: '', hidden: false, style: {},
      classList: { _s: new Set(), add(c){this._s.add(c);}, remove(c){this._s.delete(c);}, contains(c){return this._s.has(c);} },
      setAttribute(k, v) { this[k] = v; },
      removeAttribute(k) { delete this[k]; },
      appendChild() {},
      addEventListener() {},
      focus() {},
    };
  }
  return els[id];
}
const mem = { _d: {}, getItem(k){return this._d[k]||null;}, setItem(k,v){this._d[k]=String(v);}, removeItem(k){delete this._d[k];}, clear(){this._d={};} };
global.document = {
  getElementById: getEl,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: () => ({ style: {}, className: '', textContent: '', appendChild(){}, onclick: null }),
  cookie: '',
  addEventListener: () => {},
};
global.window = { localStorage: mem, sessionStorage: mem, addEventListener: () => {}, location: { search: '', hostname: 'example.vercel.app', protocol: 'https:' } };
global.location = global.window.location;
global.navigator = {};
global.localStorage = mem;
global.sessionStorage = mem;
global.setInterval = () => 0;
global.clearInterval = () => {};
global.setTimeout = () => 0;
global.clearTimeout = () => {};
global.fetch = async () => ({ ok: false, status: 401, json: async () => ({ ok: false, authenticated: false }) });

eval(code);

(async () => {
  const res = await global.window.executeMobileVoiceCommandHttp({ transcript: 'Mở cửa chính', is_live_mic: true });
  const badgeText = getEl('voiceStateBadge').textContent;
  const replyText = getEl('voiceReplyText').textContent;
  const errText = res && res.error ? res.error : '';
  const leakedSuccess = /Xác thực thành công|Đạt|Đã thực hiện lệnh/i.test(badgeText + ' ' + replyText + ' ' + errText);
  process.stdout.write(JSON.stringify({
    ok: !!(res && res.ok),
    authorized: !!(res && res.authorized),
    badgeText,
    errText,
    gateVisible: getEl('mobileLoginGate').hidden === false,
    leakedSuccess,
  }));
  process.exit(0);
})();
"""
        proc = subprocess.run(
            ["node", "-e", node_script, str(js_file)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["ok"] is False
        assert out["authorized"] is False
        assert out["leakedSuccess"] is False
        assert out["badgeText"] == "Chưa đăng nhập"
        assert "đăng nhập" in out["errText"].lower()
        assert out["gateVisible"] is True


# ==============================================================================
# P1-3: Owner Tier-1 2FA gate, uniform 401, cross-instance lockout, RBAC
# ==============================================================================


class TestP1_3Owner2FAUniform401AndCasLockout:
    """Owner cannot log in on password alone; lockout syncs across instances via CAS."""

    @pytest.mark.parametrize("send_gmail", [False, True])
    def test_owner_layer1_never_issues_session_and_requires_layer2_otp(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, send_gmail: bool
    ):
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "test-app-pw")
        monkeypatch.setenv("SMTP_USER", "nep94121@gmail.com")
        mgr = get_auth_3layer_manager()
        owner_acc = mgr.find_account("nep94121@gmail.com")
        assert owner_acc is not None
        ephemeral_pw = "Owner_" + secrets.token_urlsafe(12)
        monkeypatch.setitem(owner_acc, "password_hash", hash_password(ephemeral_pw))

        res1 = client.post(
            "/api/auth3/layer1_login",
            json={"email": owner_acc["email"], "password": ephemeral_pw, "send_gmail": send_gmail},
        )
        assert res1.status_code == 200
        d1 = res1.json()
        assert d1.get("ok") is True
        assert d1.get("otp_required") is True
        assert d1.get("next_layer") == 2
        assert not d1.get("session_token")
        assert "sh_session_token" not in res1.cookies
        assert "session_token" not in res1.cookies
        assert "set-cookie" not in res1.headers

        otp_code = mgr.pending_otps[owner_acc["email"].lower()]["otp_code"]

        # Wrong OTP rejected without minting session
        bad_otp = "000000" if otp_code != "000000" else "111111"
        res_bad = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": owner_acc["email"], "otp_code": bad_otp},
        )
        assert res_bad.status_code in (400, 401)
        assert res_bad.json().get("ok") is False
        assert not res_bad.json().get("session_token")
        assert "sh_session_token" not in res_bad.cookies

        # Valid OTP mints Owner Tier-1 session and burns OTP against replay
        res2 = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": owner_acc["email"], "otp_code": otp_code},
        )
        assert res2.status_code == 200
        d2 = res2.json()
        assert d2.get("ok") is True
        tok = d2.get("session_token")
        assert tok
        assert (d2.get("session") or {}).get("tier") == 1
        assert (d2.get("session") or {}).get("role") == "ADMIN"
        assert "sh_session_token" in res2.cookies

        res_replay = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": owner_acc["email"], "otp_code": otp_code},
        )
        assert res_replay.status_code in (400, 401)
        assert res_replay.json().get("ok") is False

    def test_layer2_send_otp_endpoint_requires_valid_layer1_challenge(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "test-app-pw")
        monkeypatch.setenv("SMTP_USER", "nep94121@gmail.com")
        mgr = get_auth_3layer_manager()
        owner_acc = mgr.find_account("nep94121@gmail.com")
        assert owner_acc is not None
        ephemeral_pw = "Owner_" + secrets.token_urlsafe(12)
        monkeypatch.setitem(owner_acc, "password_hash", hash_password(ephemeral_pw))

        # Without Layer-1 challenge -> 401
        r_no_l1 = client.post("/api/auth3/layer2_send_otp", json={"email": owner_acc["email"]})
        assert r_no_l1.status_code == 401
        assert r_no_l1.json().get("ok") is False

        # After Layer-1 send_gmail=False -> layer2_send_otp succeeds
        r_l1 = client.post(
            "/api/auth3/layer1_login",
            json={"email": owner_acc["email"], "password": ephemeral_pw, "send_gmail": False},
        )
        assert r_l1.status_code == 200
        r_send = client.post("/api/auth3/layer2_send_otp", json={"email": owner_acc["email"]})
        assert r_send.status_code == 200
        assert r_send.json().get("ok") is True

    def test_uniform_401_across_unknown_wrong_password_and_empty_hash(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        mgr = get_auth_3layer_manager()
        owner_acc = mgr.find_account("nep94121@gmail.com")
        member_acc = mgr.find_account("thanhviena.hust@gmail.com")
        assert owner_acc is not None and member_acc is not None
        monkeypatch.setitem(member_acc, "password_hash", hash_password("StrongMemberPass#1"))
        monkeypatch.setitem(owner_acc, "password_hash", "")

        r_unknown = client.post(
            "/api/auth3/layer1_login",
            json={"email": "nobody.here.20261114@gmail.com", "password": "wrong", "send_gmail": False},
            headers={"X-Forwarded-For": "198.51.100.11"},
        )
        r_wrong = client.post(
            "/api/auth3/layer1_login",
            json={"email": member_acc["email"], "password": "wrong", "send_gmail": False},
            headers={"X-Forwarded-For": "198.51.100.12"},
        )
        r_empty = client.post(
            "/api/auth3/layer1_login",
            json={"email": owner_acc["email"], "password": "wrong", "send_gmail": False},
            headers={"X-Forwarded-For": "198.51.100.13"},
        )

        for r in (r_unknown, r_wrong, r_empty):
            assert r.status_code == 401
            body = r.json()
            assert body.get("ok") is False
            assert body.get("error") == "Email hoặc mật khẩu không chính xác."
            assert "needs_password_reset" not in body

    def test_cross_instance_cas_login_lockout_and_ip_isolation(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("SIMULATOR_SECURITY_STATE_DIR", str(tmp_path))
        mgr1 = ThreeLayerAuthManager()

        def _seed_owner_pw() -> bool:
            acc = next(a for a in mgr1.accounts if a.get("email") == "nep94121@gmail.com")
            acc["password_hash"] = hash_password("CorrectOwnerPass#99")
            return mgr1._save_accounts()

        assert mgr1._with_cas_accounts(_seed_owner_pw) is True

        ip_attacker = "203.0.113.10"
        ip_other = "198.51.100.7"
        for idx in range(4):
            res = mgr1.layer1_login(
                email="nep94121@gmail.com",
                password=f"BadAttempt#{idx}",
                send_gmail=False,
                client_ip=ip_attacker,
            )
            assert res.get("status_code") == 401

        res5 = mgr1.layer1_login(
            email="nep94121@gmail.com",
            password="BadAttempt#4",
            send_gmail=False,
            client_ip=ip_attacker,
        )
        assert res5.get("status_code") == 429
        assert res5.get("locked") is True
        assert int(res5.get("retry_after_seconds", 0)) > 0

        # Fresh instance against same CAS dir enforces lockout across dot/plus Gmail aliases
        mgr2 = ThreeLayerAuthManager()
        res_alias_locked = mgr2.layer1_login(
            email="n.e.p.94121+test@googlemail.com",
            password="CorrectOwnerPass#99",
            send_gmail=False,
            client_ip=ip_attacker,
        )
        assert res_alias_locked.get("status_code") == 429
        assert res_alias_locked.get("locked") is True

        # Different IP is NOT locked out for the canonical mailbox
        res_other_ip = mgr2.layer1_login(
            email="nep94121@gmail.com",
            password="CorrectOwnerPass#99",
            send_gmail=False,
            client_ip=ip_other,
        )
        assert res_other_ip.get("ok") is True
        assert res_other_ip.get("otp_required") is True

    def test_http_429_includes_retry_after_and_tier2_3_rbac(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ):
        monkeypatch.setenv("SIMULATOR_SECURITY_STATE_DIR", str(tmp_path))
        mgr = get_auth_3layer_manager()

        def _seed_t2_t3() -> bool:
            senat = next(a for a in mgr.accounts if a.get("email") == "senat6031@gmail.com")
            kbanh = next(a for a in mgr.accounts if a.get("email") == "kbanh376@gmail.com")
            senat["password_hash"] = hash_password("FamilyPass#22")
            kbanh["password_hash"] = hash_password("GuestPass#33")
            return mgr._save_accounts()

        assert mgr._with_cas_accounts(_seed_t2_t3) is True
        try:
            # Tier 2 & Tier 3 active logins succeed at Layer 1 without OTP and cannot grant/revoke
            for acc_email, pw, expected_tier in (
                ("senat6031@gmail.com", "FamilyPass#22", 2),
                ("kbanh376@gmail.com", "GuestPass#33", 3),
            ):
                r_ok = client.post(
                    "/api/auth3/layer1_login",
                    json={"email": acc_email, "password": pw, "send_gmail": False},
                    headers={"X-Forwarded-For": "198.51.100.50"},
                )
                assert r_ok.status_code == 200
                d_ok = r_ok.json()
                assert d_ok.get("ok") is True
                assert not d_ok.get("otp_required")
                tok = d_ok.get("session_token")
                assert tok
                assert (d_ok.get("session") or {}).get("tier") == expected_tier

                r_grant = client.post(
                    "/api/users/grant",
                    headers={"X-Session-Token": tok},
                    json={"target_name": "Test User", "target_tier": 2},
                )
                r_revoke = client.post(
                    "/api/users/revoke",
                    headers={"X-Session-Token": tok},
                    json={"target_name": "Test User"},
                )
                assert r_grant.status_code == 403
                assert r_revoke.status_code == 403

            # 5 bad logins over HTTP -> 429 with Retry-After header
            for i in range(4):
                r_f = client.post(
                    "/api/auth3/layer1_login",
                    json={"email": "ratelimit.http@gmail.com", "password": f"bad{i}", "send_gmail": False},
                    headers={"X-Forwarded-For": "203.0.113.77"},
                )
                assert r_f.status_code == 401
            r_429 = client.post(
                "/api/auth3/layer1_login",
                json={"email": "ratelimit.http@gmail.com", "password": "bad4", "send_gmail": False},
                headers={"X-Forwarded-For": "203.0.113.77"},
            )
            assert r_429.status_code == 429
            assert int(r_429.headers.get("retry-after", "0")) > 0
        finally:
            monkeypatch.delenv("SIMULATOR_SECURITY_STATE_DIR", raising=False)
            mgr._load_state()

    def test_public_html_and_js_expose_zero_seed_emails(self):
        forbidden = ("nep94121@gmail.com", "senat6031@gmail.com", "kbanh376@gmail.com")
        files = [
            ROOT / "simulator" / "static" / "login.html",
            ROOT / "simulator" / "static" / "register.html",
            ROOT / "simulator" / "static" / "index.html",
            ROOT / "simulator" / "static" / "auth.html",
            ROOT / "mobile_app" / "index.html",
            ROOT / "simulator" / "static" / "js" / "auth_pages.js",
            ROOT / "simulator" / "static" / "js" / "app.js",
            ROOT / "simulator" / "static" / "js" / "auth.js",
            ROOT / "simulator" / "static" / "js" / "mobile_app.js",
        ]
        for path in files:
            text = path.read_text(encoding="utf-8")
            for addr in forbidden:
                assert addr not in text, f"Exposed email {addr} in {path}"


# ==============================================================================
# P1-4: CAS 404 init, multi-instance OTP sync, strict allowlist, purpose check
# ==============================================================================


class TestP1_4CasSyncAllowlistAndForgotPassword:
    """Cross-instance CAS accounts + hashed OTP sync, strict allowlist, and UI flows."""

    def test_github_security_state_404_bootstrap_and_put_omits_sha(self, monkeypatch: pytest.MonkeyPatch):
        state = GitHubSecurityState("owner/private-repo", "ghp_dummy_token")
        put_bodies: list[dict[str, Any]] = []

        def fake_urlopen(req, timeout=8):
            url = req.full_url
            method = req.get_method()
            if method == "GET" and url.split("?")[0].endswith("/repos/owner/private-repo"):
                return io.BytesIO(json.dumps({"private": True}).encode("utf-8"))
            if method == "GET" and "/contents/auth3_accounts_state.json" in url:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            if method == "PUT" and "/contents/auth3_accounts_state.json" in url:
                put_bodies.append(json.loads(req.data.decode("utf-8")))
                return io.BytesIO(json.dumps({"content": {"sha": "newsha123"}}).encode("utf-8"))
            raise AssertionError(f"Unexpected request: {method} {url}")

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        raw, sha, rev = state.read("auth3_accounts_state.json")
        assert raw == b"{}"
        assert sha == ""
        assert rev == 0

        state.compare_and_swap("auth3_accounts_state.json", b'{"accounts":[]}', expected_sha="", revision=0)
        assert len(put_bodies) == 1
        assert "sha" not in put_bodies[0]

        state.compare_and_swap("auth3_accounts_state.json", b'{"accounts":[1]}', expected_sha="abc123", revision=1)
        assert put_bodies[1].get("sha") == "abc123"

    def test_multi_instance_cas_register_forgot_otp_reset_strips_plaintext_otp(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("SIMULATOR_SECURITY_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "mock-app-pw")
        monkeypatch.setenv("SMTP_USER", "nep94121@gmail.com")

        # Instance A registers non-owner account cleanly
        mgr_a = ThreeLayerAuthManager()
        reg = mgr_a.register_or_update_password(
            email="casflow.user@gmail.com",
            password="OldPassword#11",
            confirm_password="OldPassword#11",
            display_name="CAS Flow User",
            create_only=True,
        )
        assert reg.get("ok") is True

        # Also stage legacy alias nep94121+e2e1114a@gmail.com directly in CAS to test real-mail CAS OTP sync
        mgr_b = ThreeLayerAuthManager()
        captured_otps: list[str] = []

        def spy_send(target_email: str, otp_code: str, display_name: str = ""):
            captured_otps.append(otp_code)
            return {"sent_real_gmail": True, "actual_recipient": target_email, "transport": "SMTP"}

        monkeypatch.setattr(mgr_b, "send_real_gmail_otp", spy_send)
        otp_req = mgr_b.request_password_reset_otp("casflow.user@gmail.com", send_gmail=True)
        assert otp_req.get("ok") is True
        assert len(captured_otps) == 1
        otp_code = captured_otps[0]

        # Inspect CAS file on disk: must contain otp_hash + otp_salt and ZERO plaintext otp_code
        cas_path = tmp_path / "auth3_accounts_state.json"
        assert cas_path.exists()
        cas_text = cas_path.read_text(encoding="utf-8")
        assert '"otp_hash"' in cas_text
        assert '"otp_salt"' in cas_text
        assert '"otp_code"' not in cas_text
        assert otp_code not in cas_text

        # Instance C (clean memory pending_otps) resets password via CAS hash check
        mgr_c = ThreeLayerAuthManager()
        assert "casflow.user@gmail.com" not in mgr_c.pending_otps
        reset_res = mgr_c.reset_password_with_otp(
            email="casflow.user@gmail.com",
            otp_code=otp_code,
            new_password="NewPassword#22",
            confirm_password="NewPassword#22",
        )
        assert reset_res.get("ok") is True

        # Instance D sees new password accepted (reaches PENDING 403) while old password returns 401
        mgr_d = ThreeLayerAuthManager()
        res_old = mgr_d.layer1_login("casflow.user@gmail.com", "OldPassword#11", send_gmail=False)
        res_new = mgr_d.layer1_login("casflow.user@gmail.com", "NewPassword#22", send_gmail=False)
        assert res_old.get("status_code") == 401
        assert res_new.get("status_code") == 403
        assert res_new.get("permission_status") == "PENDING"

    def test_layer2_verify_otp_rejects_forgot_password_purpose_without_session(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        mgr = get_auth_3layer_manager()
        owner_acc = mgr.find_account("nep94121@gmail.com")
        assert owner_acc is not None
        monkeypatch.setitem(owner_acc, "password_hash", hash_password("SomePass#1"))
        res_otp = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "nep94121@gmail.com", "send_gmail": False},
        )
        assert res_otp.status_code == 200
        otp_code = mgr.pending_otps["nep94121@gmail.com"]["otp_code"]

        res_cross = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": "nep94121@gmail.com", "otp_code": otp_code, "purpose": "layer2_login"},
        )
        assert res_cross.status_code in (400, 401)
        assert res_cross.json().get("ok") is False
        assert not res_cross.json().get("session_token")
        assert "sh_session_token" not in res_cross.cookies

        # Omitting `purpose` on a forgot_password OTP must never mint a login session or cookie
        res_otp2 = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": "thanhviena.hust@gmail.com", "send_gmail": False},
        )
        assert res_otp2.status_code == 200
        otp_code2 = mgr.pending_otps["thanhviena.hust@gmail.com"]["otp_code"]
        res_no_purpose = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": "thanhviena.hust@gmail.com", "otp_code": otp_code2},
        )
        assert not res_no_purpose.json().get("session_token")
        assert "sh_session_token" not in res_no_purpose.cookies
        assert client.get("/api/session/role").status_code == 401

    def test_real_email_allowlist_restricted_to_owner_canonical_and_ignores_env_on_vercel(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        assert HARDCODED_REAL_EMAIL_ALLOWLIST == frozenset({"nep94121@gmail.com"})
        for allowed in (
            "nep94121@gmail.com",
            "NEP94121@GMAIL.COM",
            "nep94121+e2e1114a@gmail.com",
            "n.e.p.94121@googlemail.com",
        ):
            assert is_email_allowlisted_for_real_send(allowed) is True

        for blocked in (
            "senat6031@gmail.com",
            "kbanh376@gmail.com",
            "stranger@gmail.com",
            "nep94121+bad..tag@gmail.com",
            "nep94121@gmail.com.evil.com",
        ):
            assert is_email_allowlisted_for_real_send(blocked) is False

        monkeypatch.setenv("VERCEL", "1")
        monkeypatch.setenv("REAL_EMAIL_ALLOWLIST", "senat6031@gmail.com,attacker@evil.com")
        assert is_email_allowlisted_for_real_send("senat6031@gmail.com") is False
        assert is_email_allowlisted_for_real_send("attacker@evil.com") is False
        assert is_email_allowlisted_for_real_send("nep94121+e2e1114a@gmail.com") is True

    def test_forgot_password_ui_elements_present_on_all_auth_pages(self):
        login_html = (ROOT / "simulator" / "static" / "login.html").read_text(encoding="utf-8")
        auth_pages_js = (ROOT / "simulator" / "static" / "js" / "auth_pages.js").read_text(encoding="utf-8")
        index_html = (ROOT / "simulator" / "static" / "index.html").read_text(encoding="utf-8")
        auth_html = (ROOT / "simulator" / "static" / "auth.html").read_text(encoding="utf-8")
        mobile_html = (ROOT / "mobile_app" / "index.html").read_text(encoding="utf-8")

        for marker in ("forgotEmailInput", "forgotOtpInput", "forgotNewPasswordInput", "forgotConfirmPasswordInput"):
            assert marker in login_html
        assert "/api/auth3/forgot_password_send_otp" in auth_pages_js
        assert "/api/auth3/forgot_password_reset" in auth_pages_js
        assert "gateForgotOtpInput" in index_html and "gateForgotConfirmPassword" in index_html
        assert "authForgotNewPassword" in auth_html and "authForgotConfirmPassword" in auth_html
        assert "mobileForgotOtp" in mobile_html and "mobileForgotConfirmPassword" in mobile_html


# ==============================================================================
# P2-5 & P2-6: PENDING vs REVOKED & Gmail Canonical Duplicate vs Legacy Lookup
# ==============================================================================


class TestP2_5AndP2_6PendingVsRevokedAndGmailCanonical:
    """New accounts start PENDING; Gmail aliases of Owner collide (409) on registration."""

    def test_new_account_is_pending_403_distinct_from_owner_revoked_403(
        self, client: TestClient
    ):
        reg = client.post(
            "/api/auth3/register_or_set_password",
            json={
                "email": "pending.user.20261114@gmail.com",
                "password": "PendingPass#123",
                "confirm_password": "PendingPass#123",
                "display_name": "Pending User",
            },
        )
        assert reg.status_code == 200
        d_reg = reg.json()
        assert d_reg.get("permission_status") == "PENDING"

        r_pending = client.post(
            "/api/auth3/layer1_login",
            json={"email": "pending.user.20261114@gmail.com", "password": "PendingPass#123", "send_gmail": False},
        )
        assert r_pending.status_code == 403
        b_pending = r_pending.json()
        assert b_pending.get("permission_status") == "PENDING"
        assert "chờ Chủ nhà phê duyệt" in b_pending.get("error", "")
        assert "thu hồi" not in b_pending.get("error", "")

        # Owner grants then revokes -> status becomes REVOKED with revocation message
        owner_hdr = {"X-Session-Token": "sess_owner_t1_nep94121"}
        r_grant = client.post(
            "/api/auth3/voice_permission_command",
            headers=owner_hdr,
            json={"target_identifier": "pending.user.20261114@gmail.com", "enable_permission": True},
        )
        assert r_grant.status_code == 200
        r_revoke = client.post(
            "/api/auth3/voice_permission_command",
            headers=owner_hdr,
            json={"target_identifier": "pending.user.20261114@gmail.com", "enable_permission": False},
        )
        assert r_revoke.status_code == 200

        r_revoked = client.post(
            "/api/auth3/layer1_login",
            json={"email": "pending.user.20261114@gmail.com", "password": "PendingPass#123", "send_gmail": False},
        )
        assert r_revoked.status_code == 403
        b_revoked = r_revoked.json()
        assert b_revoked.get("permission_status") == "REVOKED"
        assert "xóa cấp quyền" in b_revoked.get("error", "")

    def test_family_allowlist_add_activates_pending_account_for_login_and_password_reset(
        self, client: TestClient
    ):
        target_email = "pending.allowlist.20261114@gmail.com"
        initial_pw = "PendingAllow#123"
        reset_pw = "PendingReset#456"

        reg = client.post(
            "/api/auth3/register_or_set_password",
            json={
                "email": target_email,
                "password": initial_pw,
                "confirm_password": initial_pw,
                "display_name": "Pending Allowlist Member",
            },
        )
        assert reg.status_code == 200
        assert reg.json().get("permission_status") == "PENDING"

        r_pending = client.post(
            "/api/auth3/layer1_login",
            json={"email": target_email, "password": initial_pw, "send_gmail": False},
        )
        assert r_pending.status_code == 403
        assert r_pending.json().get("permission_status") == "PENDING"

        owner_hdr = {"X-Session-Token": "sess_owner_t1_nep94121"}
        r_add = client.post(
            "/api/auth3/family_allowlist/add",
            headers=owner_hdr,
            json={"target_email": target_email, "target_tier": 2},
        )
        assert r_add.status_code == 200, r_add.text
        d_add = r_add.json()
        assert d_add.get("ok") is True
        assert d_add["account"].get("permission_active") is True
        assert d_add["account"].get("permission_status") == "ACTIVE"
        assert d_add["account"].get("tier") == 2

        r_login = client.post(
            "/api/auth3/layer1_login",
            json={"email": target_email, "password": initial_pw, "send_gmail": False},
        )
        assert r_login.status_code == 200, r_login.text
        d_login = r_login.json()
        assert d_login.get("authenticated") is True
        assert bool(d_login.get("session_token"))

        r_otp = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": target_email, "send_gmail": False},
        )
        assert r_otp.status_code == 200, r_otp.text
        mgr = get_auth_3layer_manager()
        otp_code = mgr.pending_otps[target_email]["otp_code"]

        r_rst = client.post(
            "/api/auth3/forgot_password_reset",
            json={
                "email": target_email,
                "otp_code": otp_code,
                "new_password": reset_pw,
                "confirm_password": reset_pw,
            },
        )
        assert r_rst.status_code == 200, r_rst.text
        assert r_rst.json().get("ok") is True

        r_new_login = client.post(
            "/api/auth3/layer1_login",
            json={"email": target_email, "password": reset_pw, "send_gmail": False},
        )
        assert r_new_login.status_code == 200, r_new_login.text
        assert r_new_login.json().get("authenticated") is True

    @pytest.mark.parametrize(
        "alias_email",
        [
            "nep94121@googlemail.com",
            "n.e.p.94121@gmail.com",
            "nep94121+newalias2026@gmail.com",
        ],
    )
    def test_gmail_canonical_duplicate_returns_409_on_register(
        self, client: TestClient, alias_email: str
    ):
        assert canonical_gmail_mailbox(alias_email) == "nep94121@gmail.com"
        resp = client.post(
            "/api/auth3/register_or_set_password",
            json={
                "email": alias_email,
                "password": "AnotherPass#123",
                "confirm_password": "AnotherPass#123",
            },
        )
        assert resp.status_code == 409
        assert resp.json().get("ok") is False

    def test_exact_first_find_account_preserves_existing_legacy_aliases(self):
        mgr = get_auth_3layer_manager()
        legacy_plus = {
            "account_id": "legacy_plus_t3",
            "email": "nep94121+e2e1114a@gmail.com",
            "display_name": "Legacy Plus",
            "tier": 3,
            "role": "CHILD_GUEST",
            "permission_active": False,
        }
        legacy_gm = {
            "account_id": "legacy_gm_t3",
            "email": "nep94121@googlemail.com",
            "display_name": "Legacy Googlemail",
            "tier": 3,
            "role": "CHILD_GUEST",
            "permission_active": False,
        }
        mgr.accounts.extend([legacy_plus, legacy_gm])

        assert (mgr.find_account("nep94121+e2e1114a@gmail.com") or {}).get("account_id") == "legacy_plus_t3"
        assert (mgr.find_account("nep94121@googlemail.com") or {}).get("account_id") == "legacy_gm_t3"
        assert (mgr.find_account("nep94121@gmail.com") or {}).get("account_id") == "tuan_anh"


# ==============================================================================
# P2-7, P2-8, P2-9, P2-10: Nav /guest links, /auth gate, polling cleanup, /wokwi
# ==============================================================================


class TestP2_7ToP2_10FrontendRoutesGateAndWokwiCloud:
    """Verify frontend links, /auth gate, no stale polling, and /wokwi HTTP cloud sync."""

    def test_zero_guest_enroll_nav_links_and_guest_route_behavior(self, client: TestClient):
        for html_file in sorted((ROOT / "simulator" / "static").glob("*.html")) + [ROOT / "mobile_app" / "index.html"]:
            text = html_file.read_text(encoding="utf-8")
            assert not re.search(r'(?<!/css)(?<!/js)/guest_enroll(?![.\w])', text), f"Stale /guest_enroll link in {html_file}"
        for js_file in sorted((ROOT / "simulator" / "static" / "js").glob("*.js")):
            text = js_file.read_text(encoding="utf-8")
            assert not re.search(r'(?<!/css)(?<!/js)/guest_enroll(?![.\w])', text), f"Stale /guest_enroll reference in {js_file}"

        assert client.get("/guest_enroll").status_code == 410
        assert client.get("/guest").status_code == 403
        inv = create_invite(owner_user_id="tuan_anh", tier=3, ttl_sec=600)
        assert client.get(f"/guest?token={inv['token']}").status_code == 200

    def test_auth_page_gated_and_zero_voice_enrollment_forms(self):
        auth_html = (ROOT / "simulator" / "static" / "auth.html").read_text(encoding="utf-8")
        auth_js = (ROOT / "simulator" / "static" / "js" / "auth.js").read_text(encoding="utf-8")

        assert 'id="authUnauthGate"' in auth_html
        assert "/api/session/role" in auth_js
        assert "showUnauthenticatedAuthView" in auth_js
        for gone in ("enroll_first_page_voice", "enroll_voice_sample", "enroll_tier_pcm"):
            assert gone not in auth_html
            assert gone not in auth_js

    def test_no_guest_qr_current_polling_anywhere_in_frontend(self):
        for folder in (ROOT / "simulator" / "static", ROOT / "mobile_app"):
            for path in folder.rglob("*"):
                if path.is_file() and path.suffix in (".html", ".js"):
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    assert "guest_qr_current" not in text, f"Found guest_qr_current in {path}"

    def test_wokwi_uses_http_cloud_polling_on_vercel_and_displays_login_banner_on_401(self):
        wokwi_html = (ROOT / "simulator" / "static" / "wokwi.html").read_text(encoding="utf-8")
        wokwi_js = (ROOT / "simulator" / "static" / "js" / "wokwi.js").read_text(encoding="utf-8")

        assert 'id="wokwiAuthBanner"' in wokwi_html
        assert "isLocalWokwiHost" in wokwi_js
        assert "Đồng bộ HTTP Cloud" in wokwi_js
        assert "showWokwiAuthError" in wokwi_js
        assert "location.hostname === 'localhost'" in wokwi_js or "h === 'localhost' || h === '127.0.0.1'" in wokwi_js
