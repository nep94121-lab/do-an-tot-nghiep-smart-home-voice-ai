"""Session / account RBAC, mã mời khách, trang khách, lệnh giọng không nhận dạng người nói."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from simulator.auth.guest_invites import (
    create_invite,
    inspect_token,
    redeem_token,
    reset_invite_store_for_tests,
    revoke_invite,
)
from simulator.auth.session_store import get_session_store


OWNER_SESSION = "sess_owner_t1_nep94121"
FAMILY_SESSION = "sess_family_t2_member_a"
GUEST_SESSION = "sess_guest_t3_visitor_c"

NAV_MARKERS = (
    "Tổng quan",
    "Xác thực",
    "Phần cứng",
    "Nhật ký",
    "Ứng dụng",
    "Đăng nhập",
    "Đăng ký",
    'href="/"',
    'href="/auth"',
    'href="/hardware"',
    "guest_enroll",
)

REPEAT_MARKERS = (
    "vui lòng nói lại",
    "âm thanh chưa rõ",
)


@pytest.fixture
def client(monkeypatch):
    reset_invite_store_for_tests()
    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")
    from simulator.server import app

    with TestClient(app) as test_client:
        yield test_client


def _auth(session_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {session_id}", "x-session-token": session_id}


def _cookies(session_id: str) -> dict[str, str]:
    return {"sh_session_token": session_id, "session_token": session_id}


def test_owner_session_can_control_main_door(client):
    res = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open", "source": "test"},
        headers=_auth(OWNER_SESSION),
        cookies=_cookies(OWNER_SESSION),
    )
    body = res.json()
    assert res.status_code == 200, body
    assert body.get("ok") is True
    assert body.get("rbac_blocked") is not True


def test_tier3_session_denied_main_door_allowed_light(client):
    denied = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open", "source": "test"},
        headers=_auth(GUEST_SESSION),
        cookies=_cookies(GUEST_SESSION),
    )
    denied_body = denied.json()
    assert denied.status_code in (200, 403)
    assert denied_body.get("ok") is False
    assert denied_body.get("rbac_blocked") is True

    allowed = client.post(
        "/api/device",
        json={"device_id": "living_room_light", "action": "on", "source": "test"},
        headers=_auth(GUEST_SESSION),
        cookies=_cookies(GUEST_SESSION),
    )
    allowed_body = allowed.json()
    assert allowed.status_code == 200, allowed_body
    assert allowed_body.get("ok") is True


def test_tier2_session_can_control_ac_not_door(client):
    ac = client.post(
        "/api/device",
        json={"device_id": "ac", "action": "on", "source": "test"},
        headers=_auth(FAMILY_SESSION),
        cookies=_cookies(FAMILY_SESSION),
    )
    ac_body = ac.json()
    assert ac.status_code == 200, ac_body
    assert ac_body.get("ok") is True

    door = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open", "source": "test"},
        headers=_auth(FAMILY_SESSION),
        cookies=_cookies(FAMILY_SESSION),
    )
    door_body = door.json()
    assert door_body.get("ok") is False
    assert door_body.get("rbac_blocked") is True


def test_unauthenticated_device_and_voice_rejected_silently(client):
    device = client.post("/api/device", json={"device_id": "fan", "action": "on"})
    assert device.status_code in (401, 403)
    body = device.json()
    blob = " ".join(str(body.get(k) or "") for k in body).lower()
    assert not any(marker in blob for marker in REPEAT_MARKERS)

    voice = client.post("/api/voice_command", json={"transcript": "bật quạt"})
    assert voice.status_code in (401, 403)
    vbody = voice.json()
    assert vbody.get("ask_repeat") is not True
    assert not (vbody.get("pcm24k_b64") or vbody.get("audio_b64"))
    vblob = " ".join(str(vbody.get(k) or "") for k in vbody).lower()
    assert not any(marker in vblob for marker in REPEAT_MARKERS)


def test_anyone_voice_with_transcript_executes_within_tier(client):
    """Không cần mẫu giọng / WeSpeaker: transcript + phiên là đủ."""
    ok = client.post(
        "/api/voice_command",
        json={"transcript": "bật đèn phòng khách", "pcm16k_b64": "", "source": "test"},
        headers=_auth(GUEST_SESSION),
        cookies=_cookies(GUEST_SESSION),
    )
    body = ok.json()
    assert ok.status_code == 200, body
    assert body.get("ok") is True
    assert body.get("ask_repeat") is not True

    blocked = client.post(
        "/api/voice_command",
        json={"transcript": "mở cửa chính", "source": "test"},
        headers=_auth(GUEST_SESSION),
        cookies=_cookies(GUEST_SESSION),
    )
    blocked_body = blocked.json()
    assert blocked_body.get("ok") is False
    assert blocked_body.get("rbac_blocked") is True or blocked.status_code == 403
    assert blocked_body.get("ask_repeat") is not True
    blob = " ".join(str(blocked_body.get(k) or "") for k in blocked_body).lower()
    assert not any(marker in blob for marker in REPEAT_MARKERS)


def test_empty_transcript_is_silent_no_reprompt_loop(client):
    res = client.post(
        "/api/voice_command",
        json={"transcript": "  ", "pcm16k_b64": "", "audio_b64": "", "source": "test"},
        headers=_auth(OWNER_SESSION),
        cookies=_cookies(OWNER_SESSION),
    )
    body = res.json()
    assert res.status_code == 200, body
    assert body.get("ok") is False
    assert body.get("silent") is True
    assert body.get("ask_repeat") is not True
    assert body.get("should_reply") is not True
    assert body.get("no_reprompt") is True
    assert not (body.get("pcm24k_b64") or body.get("audio_b64"))
    blob = " ".join(str(body.get(k) or "") for k in body).lower()
    assert not any(marker in blob for marker in REPEAT_MARKERS)


def test_dummy_audio_without_transcript_does_not_speak_repeat(client):
    # Một payload âm thanh giả, không transcript: im lặng, không nhận dạng người lạ, không nói lại.
    res = client.post(
        "/api/voice_command",
        json={"pcm16k_b64": "AAAA", "transcript": "", "source": "test"},
        headers=_auth(OWNER_SESSION),
        cookies=_cookies(OWNER_SESSION),
    )
    body = res.json()
    assert res.status_code == 200, body
    assert body.get("ask_repeat") is not True
    assert not (body.get("pcm24k_b64") or body.get("audio_b64"))
    blob = " ".join(str(body.get(k) or "") for k in body).lower()
    assert not any(marker in blob for marker in REPEAT_MARKERS)
    assert "không nhận ra" not in blob


def test_create_invite_requires_owner_login(client):
    anon = client.post("/api/auth3/guest_invites", json={"tier": 3, "ttl_sec": 600, "pin": "2468", "pin_confirm": "2468"})
    assert anon.status_code in (401, 403)

    guest = client.post(
        "/api/auth3/guest_invites",
        json={"tier": 3, "ttl_sec": 600, "pin": "2468", "pin_confirm": "2468"},
        headers=_auth(GUEST_SESSION),
        cookies=_cookies(GUEST_SESSION),
    )
    assert guest.status_code in (401, 403)

    owner = client.post(
        "/api/auth3/guest_invites",
        json={"tier": 3, "ttl_sec": 600, "pin": "2468", "pin_confirm": "2468"},
        headers=_auth(OWNER_SESSION),
        cookies=_cookies(OWNER_SESSION),
    )
    body = owner.json()
    assert owner.status_code == 200, body
    assert body.get("ok") is True
    assert body.get("token", "").startswith("inv_")
    assert body.get("tier") == 3
    svg = body.get("qr_svg") or ""
    assert "<svg" in svg.lower()
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg
    assert len(svg) > 200
    assert "/guest?token=" in (body.get("path") or body.get("url") or "")


def test_invite_tier_2_and_invalid_tier_rejected(client):
    bad = client.post(
        "/api/auth3/guest_invites",
        json={"tier": 1, "ttl_sec": 600, "pin": "2468", "pin_confirm": "2468"},
        headers=_auth(OWNER_SESSION),
        cookies=_cookies(OWNER_SESSION),
    )
    assert bad.status_code == 400

    ok = client.post(
        "/api/auth3/guest_invites",
        json={"tier": 2, "ttl_sec": 600, "pin": "2468", "pin_confirm": "2468"},
        headers=_auth(OWNER_SESSION),
        cookies=_cookies(OWNER_SESSION),
    )
    body = ok.json()
    assert ok.status_code == 200, body
    assert body.get("tier") == 2


def test_invite_token_validate_redeem_expiry_and_revocation(client):
    created = create_invite(owner_user_id="owner", tier=3, ttl_sec=600, host_origin="https://example.test")
    token = created["token"]
    invite_id = created["invite_id"]

    good = inspect_token(token)
    assert good.get("valid") is True
    assert good.get("tier") == 3

    redeem = client.post("/api/guest/redeem", json={"token": token})
    body = redeem.json()
    assert redeem.status_code == 200, body
    assert body.get("ok") is True
    assert body.get("tier") == 3
    assert body.get("session_token")
    assert redeem.cookies.get("sh_session_token") or redeem.cookies.get("session_token")

    session_id = body["session_token"]
    light = client.post(
        "/api/device",
        json={"device_id": "fan", "action": "on", "source": "test"},
        headers=_auth(session_id),
        cookies=_cookies(session_id),
    )
    assert light.json().get("ok") is True

    door = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open", "source": "test"},
        headers=_auth(session_id),
        cookies=_cookies(session_id),
    )
    assert door.json().get("ok") is False

    revoked = revoke_invite(invite_id)
    assert revoked.get("ok") is True
    after = inspect_token(token)
    assert after.get("valid") is False
    assert after.get("reason") == "revoked"
    redeem2 = client.post("/api/guest/redeem", json={"token": token})
    assert redeem2.status_code == 403
    # Phiên gắn với mã đã thu hồi cũng không còn điều khiển được.
    after_voice = client.post(
        "/api/voice_command",
        json={"transcript": "bật quạt"},
        headers=_auth(session_id),
        cookies=_cookies(session_id),
    )
    assert after_voice.status_code in (401, 403) or after_voice.json().get("ok") is False

    fresh = create_invite(owner_user_id="owner", tier=3, ttl_sec=600)
    record = __import__("simulator.auth.guest_invites", fromlist=["get_invite"]).get_invite(fresh["invite_id"])
    assert record is not None
    record["expires_at"] = time.time() - 10
    expired = inspect_token(fresh["token"])
    assert expired.get("valid") is False
    assert expired.get("reason") == "expired"
    redeem_exp = client.post("/api/guest/redeem", json={"token": fresh["token"]})
    assert redeem_exp.status_code == 403
    assert "hết hạn" in (redeem_exp.json().get("error") or "").lower() or redeem_exp.json().get("reason") == "expired"

    assert inspect_token(token[:-1] + ("A" if token[-1] != "A" else "B")).get("valid") is False
    assert inspect_token("").get("valid") is False
    assert inspect_token("not-a-token").get("valid") is False


def test_guest_page_without_token_is_invalid_and_has_no_navigation(client):
    res = client.get("/guest")
    assert res.status_code == 403
    html = res.text
    assert "không hợp lệ" in html.lower() or "hết hạn" in html.lower()
    for marker in NAV_MARKERS:
        assert marker not in html, marker


def test_guest_page_with_valid_token_has_controls_and_no_navigation(client):
    created = create_invite(owner_user_id="owner", tier=3, ttl_sec=600, host_origin="https://example.test")
    res = client.get(f"/guest?token={created['token']}")
    assert res.status_code == 200, res.text[:400]
    html = res.text
    assert "Trang điều khiển khách" in html or "guestDeviceGrid" in html
    assert 'id="guestMicBtn"' in html
    assert 'id="guestDeviceGrid"' in html
    for marker in ("Tổng quan", "Đăng nhập", "Đăng ký", "Phần cứng", "Nhật ký", "href=\"/auth\"", "guest_enroll"):
        assert marker not in html, marker
    # Không phải trang enroll cũ.
    assert "enroll_first_page_voice" not in html
    assert 'src="/static/js/guest_control.js"' in html


def test_owner_dashboard_qr_markup_has_no_static_copyable_guest_link():
    root = Path(__file__).resolve().parents[1]
    index_html = (root / "simulator" / "static" / "index.html").read_text(encoding="utf-8")
    assert "Sao chép liên kết" not in index_html
    assert "copyOwnerGuestLink" not in index_html
    assert "Cấp 3 · Công khai" not in index_html
    # Ô QR vẫn còn, nhưng không in URL tĩnh /guest không có token.
    assert "ownerDashboardQrBox" in index_html or "ownerGuestQr" in index_html
    assert 'id="ownerGuestQrSvg"' in index_html or "ownerDashboardQrSvg" in index_html
    app_js = (root / "simulator" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "function copyOwnerGuestLink" not in app_js
    assert "function copyInviteLink" not in app_js
    # QR phải được gắn SVG, không chỉ để trống.
    assert "qr_svg" in app_js
    assert "ownerGuestQrSvg" in app_js or "ownerDashboardQrSvg" in app_js


def test_app_js_has_no_reprompt_loop_hooks():
    app_js = (Path(__file__).resolve().parents[1] / "simulator" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    # Mic không bị phát ra loa (feedback TTS -> STT).
    assert "micProcessor.connect(micAudioCtx.destination)" not in app_js
    assert "TTS_HOLDOFF_SEC" in app_js
    assert "isTtsPlaybackActive" in app_js
    # Không tự gửi lệnh khi đang phát TTS / không transcript.
    assert "flushServerlessMicVoiceCommand" in app_js


def test_enrollment_and_speaker_endpoints_are_gone(client):
    paths = (
        "/api/auth3/enroll_first_page_voice",
        "/api/auth3/enroll_voice_sample",
        "/api/mobile/enroll_voice",
        "/api/voice_auth/enroll_tier_pcm",
        "/api/voice_enroll",
        "/api/voice/enroll",
        "/api/auth3/layer3_voice",
        "/api/auth3/guest_qr_complete_voice",
    )
    for path in paths:
        res = client.post(path, json={})
        assert res.status_code == 410, f"{path} -> {res.status_code}"
        body = res.json()
        assert body.get("ok") is False

def test_json_user_id_cannot_bypass_authentication(client):
    """Không token thì user_id/role/tier trong JSON không được thành chủ nhà."""
    for body, path in (
        ({"transcript": "mo cua chinh", "user_id": "tuan_anh"}, "/api/voice_command"),
        ({"transcript": "mo cua chinh", "role": "ADMIN"}, "/api/voice_command"),
        ({"transcript": "mo cua chinh", "tier": 1}, "/api/voice_command"),
        ({"device_id": "main_door", "action": "open", "user_id": "tuan_anh"}, "/api/device"),
        ({"tier": 3, "user_id": "tuan_anh"}, "/api/auth3/guest_invites"),
    ):
        res = client.post(path, json=body)
        assert res.status_code in (401, 403), (path, body, res.status_code, res.text)
        payload = res.json()
        assert payload.get("ok") is not True
        assert payload.get("executed") is not True


def test_speaker_id_cannot_veto_valid_session(client):
    """Metadata speaker_id không được phủ quyết phiên chủ nhà hợp lệ."""
    res = client.post(
        "/api/voice_command",
        json={"transcript": "bat quat", "speaker_id": "stranger", "source": "test"},
        headers=_auth(OWNER_SESSION),
        cookies=_cookies(OWNER_SESSION),
    )
    body = res.json()
    assert res.status_code == 200, body
    assert body.get("ok") is True
    assert body.get("tier") == 1
    assert body.get("ask_repeat") is not True


def test_additional_enrollment_aliases_are_gone(client):
    for path in ("/api/auth3/guest/enroll_voice", "/api/qr/guest_enroll"):
        res = client.post(path, json={})
        assert res.status_code == 410, f"{path} -> {res.status_code} {res.text}"
        assert res.json().get("ok") is False
