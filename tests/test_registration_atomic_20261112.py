"""Registration cannot claim the owner identity or survive a failed commit as active."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
import threading

import pytest
from fastapi.testclient import TestClient

from simulator.auth_3layer import get_auth_3layer_manager, hash_password
from simulator.auth.session_store import get_session_store
from simulator.auth.guest_invites import create_invite
from simulator.server import app
from simulator.voice_config import OWNER_EMAIL, OWNER_ID


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")
    return TestClient(app, raise_server_exceptions=False)


def registration(email, **extra):
    return {"email": email, "password": "regression-password", "confirm_password": "regression-password", **extra}


def test_owner_id_local_part_does_not_create_admin(client):
    email = OWNER_ID.replace("_", ".") + "@gmail.com"
    assert email.lower() != OWNER_EMAIL.lower()
    response = client.post("/api/auth3/register_or_set_password", json=registration(email))
    assert response.status_code == 200
    account = get_auth_3layer_manager().find_account(email)
    assert account["account_id"] != OWNER_ID
    assert account["tier"] == 3
    assert account["role"] == "CHILD_GUEST"
    assert account["permission_active"] is False
    assert not response.json().get("session_token")


def test_normalize_never_trusts_owner_id_for_another_email():
    manager = get_auth_3layer_manager()
    account = manager._normalize_account_fields({"account_id": OWNER_ID, "email": "other.owner@gmail.com", "tier": 1, "role": "ADMIN", "permission_active": True})
    assert account["account_id"] != OWNER_ID
    assert account["tier"] == 3
    assert account["permission_active"] is False


def test_registration_persistence_failure_rolls_back(client, monkeypatch):
    manager = get_auth_3layer_manager()
    before = copy.deepcopy(manager.accounts)
    monkeypatch.setattr(manager, "_save_accounts", lambda: False)
    response = client.post("/api/auth3/register_or_set_password", json=registration("failed.registration@gmail.com"))
    assert response.status_code == 503
    assert manager.accounts == before
    assert not response.json().get("session_token")


def test_invite_is_bound_in_the_first_successful_account_write(client, monkeypatch):
    manager = get_auth_3layer_manager()
    invite = create_invite(owner_user_id=OWNER_ID, tier=2)
    persisted = []
    original = manager._save_accounts
    def capture_save():
        persisted.append(copy.deepcopy(manager.accounts))
        return original()
    monkeypatch.setattr(manager, "_save_accounts", capture_save)
    response = client.post("/api/auth3/register_or_set_password", json=registration("bound.registration@gmail.com", invite_token=invite["token"]))
    assert response.status_code == 200
    written = next(account for account in persisted[0] if account["email"] == "bound.registration@gmail.com")
    assert written["guest_invite_id"] == invite["invite_id"]
    assert written["tier"] == 2


def test_session_failure_leaves_new_account_unusable(client, monkeypatch):
    manager = get_auth_3layer_manager()
    invite = create_invite(owner_user_id=OWNER_ID, tier=3)
    original_session = get_session_store().create_session
    def fail_session(*args, **kwargs):
        raise RuntimeError("session persistence unavailable")
    monkeypatch.setattr(get_session_store(), "create_session", fail_session)
    response = client.post("/api/auth3/register_or_set_password", json=registration("failed.session@gmail.com", invite_token=invite["token"]))
    assert response.status_code == 503
    account = manager.find_account("failed.session@gmail.com")
    assert account is None
    monkeypatch.setattr(get_session_store(), "create_session", original_session)
    retry = client.post("/api/auth3/register_or_set_password", json=registration("failed.session@gmail.com", invite_token=invite["token"]))
    assert retry.status_code == 200


def test_concurrent_public_registration_never_overwrites_password(client, monkeypatch):
    manager = get_auth_3layer_manager()
    barrier = threading.Barrier(2)
    original = manager.register_or_update_password
    def synchronize(*args, **kwargs):
        barrier.wait(timeout=10)
        return original(*args, **kwargs)
    monkeypatch.setattr(manager, "register_or_update_password", synchronize)
    payloads = [registration("concurrent.registration@gmail.com", password=password, confirm_password=password) for password in ("first-password", "second-password")]
    def register(payload):
        with TestClient(app, raise_server_exceptions=False) as local_client:
            return local_client.post("/api/auth3/register_or_set_password", json=payload)
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(register, payloads))
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(payload for payload, response in zip(payloads, responses) if response.status_code == 200)
    assert manager.find_account("concurrent.registration@gmail.com")["password_hash"] == hash_password(winner["password"])


def test_owner_otp_password_reset_still_works(client):
    manager = get_auth_3layer_manager()
    issued = manager.request_password_reset_otp(OWNER_EMAIL, send_gmail=False)
    assert issued["ok"]
    code = manager.pending_otps[OWNER_EMAIL.lower()]["otp_code"]
    result = manager.reset_password_with_otp(OWNER_EMAIL, code, "changed-password", "changed-password")
    assert result["ok"]
    owner = manager.find_account(OWNER_EMAIL)
    assert owner["tier"] == 1
    assert owner["password_hash"] == hash_password("changed-password")
    assert "pending_otp" not in owner


def test_invited_activation_failure_does_not_publish_account(client, monkeypatch):
    manager = get_auth_3layer_manager()
    invite = create_invite(owner_user_id=OWNER_ID, tier=2)
    original = manager._save_accounts
    saves = 0
    def fail_second_save():
        nonlocal saves
        saves += 1
        return original() if saves == 1 else False
    monkeypatch.setattr(manager, "_save_accounts", fail_second_save)
    response = client.post("/api/auth3/register_or_set_password", json=registration("failed.activation@gmail.com", invite_token=invite["token"]))
    assert response.status_code == 503
    assert not manager.find_account("failed.activation@gmail.com")["permission_active"]
    assert not response.json().get("session_token")


def test_display_name_email_spoofing_cannot_shadow_or_block_victim(client):
    attacker_resp = client.post(
        "/api/auth3/register_or_set_password",
        json=registration("attacker.shadow@gmail.com", display_name="victim.shadow@gmail.com"),
    )
    assert attacker_resp.status_code == 200
    assert not attacker_resp.json().get("session_token")

    invite = create_invite(owner_user_id=OWNER_ID, tier=2)
    victim_resp = client.post(
        "/api/auth3/register_or_set_password",
        json=registration("victim.shadow@gmail.com", display_name="Victim User", invite_token=invite["token"]),
    )
    assert victim_resp.status_code == 200
    assert victim_resp.json()["permission_active"] is True
    session_token = victim_resp.json()["session_token"]

    resolved = get_auth_3layer_manager().find_account("victim.shadow@gmail.com")
    assert resolved is not None
    assert resolved["email"] == "victim.shadow@gmail.com"
    assert resolved["permission_active"] is True

    login_resp = client.post(
        "/api/auth3/layer1_login",
        json={"email": "victim.shadow@gmail.com", "password": "regression-password", "send_gmail": False},
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["ok"] is True
    assert get_session_store().get_session(session_token).is_authenticated


def test_alias_login_binds_session_to_canonical_account_email(client, monkeypatch):
    member = get_auth_3layer_manager().find_account("thanh_vien_a")
    monkeypatch.setitem(member, "password_hash", hash_password("member-password"))
    monkeypatch.setitem(member, "permission_active", True)
    response = client.post(
        "/api/auth3/layer1_login",
        json={"email": "thanh_vien_a", "password": "member-password", "send_gmail": False},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    sess = get_session_store().get_session(response.json()["session_token"])
    assert sess is not None
    assert sess.email == member["email"]


def test_invited_registration_claims_invite_and_rejects_concurrent_revocation_with_403(client, monkeypatch):
    from simulator.auth import guest_invites

    invite = create_invite(owner_user_id=OWNER_ID, tier=2)
    ok_resp = client.post(
        "/api/auth3/register_or_set_password",
        json=registration("redeem.counted@gmail.com", invite_token=invite["token"]),
    )
    assert ok_resp.status_code == 200
    assert guest_invites.get_invite(invite["invite_id"])["redeem_count"] == 1

    race_invite = create_invite(owner_user_id=OWNER_ID, tier=3)
    original_save = get_auth_3layer_manager()._save_accounts
    revoked_once = False

    def revoke_during_account_create():
        nonlocal revoked_once
        res = original_save()
        if not revoked_once:
            revoked_once = True
            guest_invites.revoke_invite(race_invite["invite_id"])
        return res

    monkeypatch.setattr(get_auth_3layer_manager(), "_save_accounts", revoke_during_account_create)
    raced_resp = client.post(
        "/api/auth3/register_or_set_password",
        json=registration("revoked.during.reg@gmail.com", invite_token=race_invite["token"]),
    )
    assert raced_resp.status_code == 403
    assert not raced_resp.json().get("session_token")
    assert get_auth_3layer_manager().find_account("revoked.during.reg@gmail.com") is None

