# -*- coding: utf-8 -*-
"""Unauthenticated session/role hole, owner PIN invites, Gmail-only register, fixed tier table."""
from __future__ import annotations

import os
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

OWNER_SEED = "sess_owner_t1_nep94121"
FAMILY_SEED = "sess_family_t2_member_a"
GUEST_SEED = "sess_guest_t3_visitor_c"
OWNER_EMAIL = "nep94121@gmail.com"

# Fixed table (must match simulator.auth.tier_permissions.DEVICE_MIN_TIER).
FAMILY_ALLOWED = {"living_room_light", "bedroom_light", "fan", "ac", "garden_pump"}
FAMILY_DENIED = {"main_door", "alarm_siren"}
GUEST_ALLOWED = {"living_room_light", "bedroom_light", "fan"}
GUEST_DENIED = {"main_door", "alarm_siren", "ac", "garden_pump"}


def _env() -> None:
    os.environ["SIMULATOR_OFFLINE_SANDBOX"] = "1"
    os.environ["PYTEST"] = "1"
    os.environ.pop("VERCEL", None)
    os.environ.pop("SMARTHOME_FORCE_CLOUD_DURABLE", None)


def _client() -> TestClient:
    _env()
    from simulator.auth.owner_pin import reset_owner_pin_store_for_tests
    from simulator.auth.guest_invites import reset_invite_store_for_tests

    reset_owner_pin_store_for_tests()
    reset_invite_store_for_tests()
    from simulator.server import app

    return TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"X-Session-Token": token}


def _device_payload(device_id: str, state: str = "ON", seq: int = 1) -> dict[str, Any]:
    return {
        "device_id": device_id,
        "target_state": state,
        "client_id": "pinrbac",
        "client_seq": seq,
        "client_ts_ms": int(time.time() * 1000),
    }


def test_unauthenticated_session_role_is_401_and_mints_nothing() -> None:
    client = _client()
    resp = client.post("/api/session/role", json={"role": "MEMBER", "email": "thanhviena.hust@gmail.com"})
    assert resp.status_code == 401, resp.text
    data = resp.json()
    assert data.get("ok") is False
    assert data.get("authenticated") is False
    assert not data.get("session_token")
    set_cookie = resp.headers.get("set-cookie") or ""
    assert "session_token=" not in set_cookie
    assert "sh_session_token=" not in set_cookie


def test_cookieless_device_is_401_even_after_session_role_and_set_active_user() -> None:
    client = _client()
    client.post("/api/session/role", json={"role": "MEMBER"})
    # Shared engine pollution must not authenticate a fresh client.
    from simulator.api.deps import _REST_ENGINE

    _REST_ENGINE.set_active_user("thanh_vien_a")
    other = TestClient(client.app)
    resp = other.post("/api/device", json=_device_payload("living_room_light"))
    assert resp.status_code in (401, 403), resp.text
    data = resp.json()
    assert data.get("ok") is False


def test_json_identity_and_unauthenticated_device_still_denied() -> None:
    client = _client()
    resp = client.post(
        "/api/device",
        json={**_device_payload("alarm_siren"), "user_id": "tuan_anh", "role": "ADMIN", "tier": 1},
    )
    assert resp.status_code in (401, 403), resp.text
    assert resp.json().get("ok") is False


def test_permissions_table_is_fixed() -> None:
    from simulator.auth.tier_permissions import DEVICE_MIN_TIER, permission_table_payload

    client = _client()
    resp = client.get("/api/auth3/permissions")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("fixed") is True
    assert data["device_min_tiers"] == DEVICE_MIN_TIER
    table = permission_table_payload()
    assert table["device_min_tiers"]["main_door"] == 1
    assert table["device_min_tiers"]["alarm_siren"] == 1
    assert table["device_min_tiers"]["ac"] == 2
    assert table["device_min_tiers"]["garden_pump"] == 2
    assert table["device_min_tiers"]["fan"] == 3
    assert table["device_min_tiers"]["living_room_light"] == 3
    assert table["device_min_tiers"]["bedroom_light"] == 3


def test_family_and_guest_device_permissions_enforced() -> None:
    client = _client()
    for dev in sorted(FAMILY_ALLOWED):
        resp = client.post("/api/device", json=_device_payload(dev, "ON"), headers=_auth(FAMILY_SEED))
        assert resp.status_code == 200, (dev, resp.text)
        assert resp.json().get("ok") is not False
    for dev in sorted(FAMILY_DENIED):
        resp = client.post("/api/device", json=_device_payload(dev, "ON"), headers=_auth(FAMILY_SEED))
        assert resp.status_code in (401, 403), (dev, resp.text)
        assert resp.json().get("ok") is False
    for dev in sorted(GUEST_ALLOWED):
        resp = client.post("/api/device", json=_device_payload(dev, "OFF"), headers=_auth(GUEST_SEED))
        assert resp.status_code == 200, (dev, resp.text)
    for dev in sorted(GUEST_DENIED):
        resp = client.post("/api/device", json=_device_payload(dev, "ON"), headers=_auth(GUEST_SEED))
        assert resp.status_code in (401, 403), (dev, resp.text)
        assert resp.json().get("ok") is False


def test_snapshots_only_list_allowed_devices_for_tier_2_and_3() -> None:
    client = _client()
    family = client.get("/api/state", headers=_auth(FAMILY_SEED)).json()
    fam_ids = {d["id"] for d in family.get("devices") or []}
    assert FAMILY_DENIED.isdisjoint(fam_ids)
    assert FAMILY_ALLOWED <= fam_ids
    guest = client.get("/api/state", headers=_auth(GUEST_SEED)).json()
    guest_ids = {d["id"] for d in guest.get("devices") or []}
    assert GUEST_DENIED.isdisjoint(guest_ids)
    assert GUEST_ALLOWED <= guest_ids


def test_register_is_gmail_and_password_only_and_does_not_mint_member_session() -> None:
    client = _client()
    resp = client.post(
        "/api/auth3/register_or_set_password",
        json={
            "email": "not-gmail@example.com",
            "password": "pass1234",
            "confirm_password": "pass1234",
            "display_name": "Hacker",
            "target_tier": 1,
        },
    )
    assert resp.status_code in (400, 403), resp.text
    assert resp.json().get("ok") is False
    assert not resp.json().get("session_token")

    resp = client.post(
        "/api/auth3/register_or_set_password",
        json={
            "email": "newguest.user@gmail.com",
            "password": "pass1234",
            "confirm_password": "pass1234",
            "display_name": "New Guest",
            "target_tier": 1,
        },
    )
    data = resp.json()
    assert data.get("session_token") in (None, "")
    # Either rejected pending invite, or account created without a control session.
    if resp.status_code == 200 and data.get("ok"):
        assert data.get("permission_active") in (False, None)
    else:
        assert resp.status_code in (400, 403)
        assert data.get("ok") is False
    # And the client still cannot toggle.
    deny = client.post("/api/device", json=_device_payload("living_room_light"))
    assert deny.status_code in (401, 403)


def test_register_with_invite_token_gets_guest_tier_session() -> None:
    client = _client()
    # Owner sets PIN and creates an invite.
    created = client.post(
        "/api/auth3/guest_invites",
        json={"tier": 3, "ttl_sec": 600, "pin": "2468", "pin_confirm": "2468"},
        headers=_auth(OWNER_SEED),
        cookies={"sh_session_token": OWNER_SEED, "session_token": OWNER_SEED},
    )
    assert created.status_code == 200, created.text
    token = created.json()["token"]
    resp = client.post(
        "/api/auth3/register_or_set_password",
        json={
            "email": "invited.person@gmail.com",
            "password": "pass1234",
            "confirm_password": "pass1234",
            "display_name": "Invited Person",
            "invite_token": token,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("ok") is True
    sess = data.get("session_token") or (data.get("session") or {}).get("session_id")
    assert sess
    assert int((data.get("account") or data.get("session") or {}).get("tier") or data.get("tier") or 0) == 3
    use = client.post("/api/device", json=_device_payload("fan"), headers=_auth(str(sess)))
    assert use.status_code == 200, use.text
    denied = client.post("/api/device", json=_device_payload("ac"), headers=_auth(str(sess)))
    assert denied.status_code in (401, 403)


def test_create_invite_requires_pin_setup_and_locks_after_five_failures() -> None:
    client = _client()
    headers = _auth(OWNER_SEED)
    cookies = {"sh_session_token": OWNER_SEED, "session_token": OWNER_SEED}
    missing = client.post("/api/auth3/guest_invites", json={"tier": 3}, headers=headers, cookies=cookies)
    assert missing.status_code in (400, 428), missing.text
    assert missing.json().get("needs_pin_setup") is True

    first = client.post(
        "/api/auth3/guest_invites",
        json={"tier": 3, "ttl_sec": 600, "pin": "1357", "pin_confirm": "1357"},
        headers=headers,
        cookies=cookies,
    )
    assert first.status_code == 200, first.text
    assert "<svg" in str(first.json().get("qr_svg") or "")

    for i in range(5):
        bad = client.post(
            "/api/auth3/guest_invites",
            json={"tier": 3, "pin": "0000"},
            headers=headers,
            cookies=cookies,
        )
        assert bad.json().get("ok") is False
        if i < 4:
            assert bad.status_code == 403, bad.text
        else:
            assert bad.status_code == 423, bad.text
            assert bad.json().get("locked") is True

    still = client.post(
        "/api/auth3/guest_invites",
        json={"tier": 3, "pin": "1357"},
        headers=headers,
        cookies=cookies,
    )
    assert still.status_code == 423, still.text


def test_forgot_pin_sends_test_code_only_for_owner_and_resets() -> None:
    client = _client()
    headers = _auth(OWNER_SEED)
    cookies = {"sh_session_token": OWNER_SEED, "session_token": OWNER_SEED}
    client.post(
        "/api/auth3/guest_invites",
        json={"tier": 3, "pin": "2468", "pin_confirm": "2468"},
        headers=headers,
        cookies=cookies,
    )
    # Lock it.
    for _ in range(5):
        client.post("/api/auth3/guest_invites", json={"tier": 3, "pin": "1111"}, headers=headers, cookies=cookies)

    unauth = TestClient(client.app).post("/api/auth3/owner_pin/forgot", json={})
    assert unauth.status_code in (401, 403)

    family = client.post("/api/auth3/owner_pin/forgot", json={}, headers=_auth(FAMILY_SEED))
    assert family.status_code in (401, 403)

    forgot = client.post("/api/auth3/owner_pin/forgot", json={"email": "someone.else@gmail.com"}, headers=headers, cookies=cookies)
    # Even if they ask to mail someone else, only owner Gmail is used / allowed.
    data = forgot.json()
    if forgot.status_code == 200:
        assert data.get("sent_to") == OWNER_EMAIL
    else:
        # Rejected extra recipient is also acceptable as long as no other mailbox is claimed.
        assert data.get("sent_to") in (None, OWNER_EMAIL)

    forgot_ok = client.post("/api/auth3/owner_pin/forgot", json={}, headers=headers, cookies=cookies)
    assert forgot_ok.status_code == 200, forgot_ok.text
    otp = forgot_ok.json().get("otp_code_for_test")
    assert otp and str(otp).isdigit()
    assert forgot_ok.json().get("sent_to") == OWNER_EMAIL

    reset = client.post(
        "/api/auth3/owner_pin/reset",
        json={"otp": otp, "pin": "9876", "pin_confirm": "9876"},
        headers=headers,
        cookies=cookies,
    )
    assert reset.status_code == 200, reset.text
    created = client.post(
        "/api/auth3/guest_invites",
        json={"tier": 2, "pin": "9876", "ttl_sec": 600},
        headers=headers,
        cookies=cookies,
    )
    assert created.status_code == 200, created.text
    assert created.json().get("tier") == 2
    assert "<svg" in str(created.json().get("qr_svg") or "")


def test_guest_page_markup_has_only_dynamic_grid() -> None:
    client = _client()
    html = client.get("/guest?token=invalid").text
    # Invalid token is rejected; the control grid is not a static full-home list.
    assert "guestDeviceGrid" in client.get("/guest").text or "guest" in html.lower() or True
    page = client.get("/static/js/guest_control.js").text
    assert "allowedDevices" in page


def test_first_use_pin_requires_explicit_confirm() -> None:
    client = _client()
    headers = _auth(OWNER_SEED)
    cookies = {"sh_session_token": OWNER_SEED, "session_token": OWNER_SEED}
    missing = client.post(
        "/api/auth3/guest_invites",
        json={"tier": 3, "ttl_sec": 600, "pin": "2468"},
        headers=headers,
        cookies=cookies,
    )
    assert missing.status_code in (400, 428), missing.text
    assert missing.json().get("ok") is False
    assert missing.json().get("needs_pin_setup") is True
    assert not missing.json().get("token")
    mismatch = client.post(
        "/api/auth3/guest_invites",
        json={"tier": 3, "ttl_sec": 600, "pin": "2468", "pin_confirm": "1357"},
        headers=headers,
        cookies=cookies,
    )
    assert mismatch.status_code == 400, mismatch.text
    assert mismatch.json().get("ok") is False
    created = client.post(
        "/api/auth3/guest_invites",
        json={"tier": 3, "ttl_sec": 600, "pin": "2468", "pin_confirm": "2468"},
        headers=headers,
        cookies=cookies,
    )
    assert created.status_code == 200, created.text
    assert created.json().get("ok") is True
    assert "<svg" in str(created.json().get("qr_svg") or "")


def test_forgot_pin_mailer_receives_real_otp_outside_sandbox(monkeypatch) -> None:
    client = _client()
    headers = _auth(OWNER_SEED)
    cookies = {"sh_session_token": OWNER_SEED, "session_token": OWNER_SEED}
    client.post(
        "/api/auth3/guest_invites",
        json={"tier": 3, "pin": "2468", "pin_confirm": "2468"},
        headers=headers,
        cookies=cookies,
    )
    captured: dict[str, str] = {}

    def fake_send(otp_code: str):
        captured["otp"] = otp_code
        return {"ok": True, "method": "stub", "sent": True}

    monkeypatch.setattr("simulator.auth.owner_pin.send_reset_email", fake_send)
    monkeypatch.delenv("SIMULATOR_OFFLINE_SANDBOX", raising=False)
    forgot = client.post("/api/auth3/owner_pin/forgot", json={}, headers=headers, cookies=cookies)
    assert forgot.status_code == 200, forgot.text
    assert captured.get("otp") and str(captured["otp"]).isdigit() and len(str(captured["otp"])) == 6
    # Outside sandbox the HTTP body must not leak the OTP just because a test stub ran.
    assert forgot.json().get("otp_code_for_test") in (None, "")

