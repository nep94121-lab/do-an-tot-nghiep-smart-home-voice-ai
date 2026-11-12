"""Isolated live-server fixtures: real password login and owner-issued invites."""
from __future__ import annotations

import copy
import json
import secrets
import urllib.request
from pathlib import Path


def prepare_live_auth(env: dict[str, str], temp_dir: str) -> str:
    from simulator.auth_3layer import get_auth_3layer_manager, hash_password
    from simulator.voice_config import OWNER_EMAIL

    root = Path(temp_dir)
    data = root / "data"
    data.mkdir()
    env["SMARTHOME_DATA_DIR"] = str(data)
    env["SMARTHOME_DURABLE_DIR"] = str(root / "vault")
    env.pop("VERCEL", None)
    env.pop("SMARTHOME_FORCE_CLOUD_DURABLE", None)
    accounts = copy.deepcopy(get_auth_3layer_manager().accounts)
    password = secrets.token_urlsafe(24)
    for account in accounts:
        account.pop("pending_otp", None)
        if account.get("email") == OWNER_EMAIL:
            account["password_hash"] = hash_password(password)
    (data / "accounts_3layer.json").write_text(json.dumps(accounts, ensure_ascii=False), encoding="utf-8")
    return password


def post_json(base_url: str, path: str, payload: dict, token: str = "") -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Session-Token"] = token
    request = urllib.request.Request(base_url + path, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        result = json.load(response)
    assert result.get("ok") is True, "Live authentication fixture failed"
    return result


def login_live_owner(base_url: str, password: str) -> str:
    return post_json(base_url, "/api/auth3/layer1_login", {
        "email": "nep94121@gmail.com", "password": password, "send_gmail": False,
    })["session_token"]


def invite_live_member(base_url: str, owner_token: str) -> str:
    invite = post_json(base_url, "/api/auth3/guest_invites", {
        "tier": 2, "ttl_sec": 3600, "pin": "2468", "pin_confirm": "2468",
    }, owner_token)
    return post_json(base_url, "/api/guest/redeem", {"token": invite["token"]})["session_token"]
