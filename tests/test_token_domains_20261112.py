"""Invite and session signatures must never be interchangeable."""
import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from simulator.auth import guest_invites
from simulator.auth.session_store import SessionStore, _get_session_hmac_key
from simulator.server import app


def test_revoked_invite_prefix_swap_does_not_authenticate():
    invite = guest_invites.create_invite(owner_user_id="tuan_anh", tier=2)
    guest_invites.revoke_invite(invite["invite_id"])
    forged = "sess_" + invite["token"][4:]
    response = TestClient(app).post("/api/device", headers={"X-Session-Token": forged}, json={"device_id": "fan", "action": "off"})
    assert response.status_code == 401


@pytest.mark.parametrize("changes", [{"typ": "guest"}, {"u": ""}, {"r": "ADMIN", "t": 3}, {"typ": None}])
def test_malformed_session_claims_rejected_even_with_session_signature(changes):
    payload = {"typ": "session", "u": "visitor", "t": 3, "r": "CHILD_GUEST", "c": time.time(), "x": time.time() + 60, **changes}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = hmac.new(_get_session_hmac_key(), b"session:" + body.encode(), hashlib.sha256).hexdigest()[:28]
    assert SessionStore._decode_signed_token("sess_" + body + "." + signature) is None
