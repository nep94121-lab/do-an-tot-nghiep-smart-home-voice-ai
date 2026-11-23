"""Behavioral regression tests for Phase 3 release v1.0 fixes (CRIT-01..04, TRIV-01, TRIV-04)."""

from __future__ import annotations

import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.auth.session_store import UserSession, get_session_store
from backend.live.echo_and_speech_guard import ServerEchoGuard, compute_echo_similarity, normalize_for_echo_compare
from backend.rule_engine import SmartHomeEngine
from backend.server import app
from backend.voice import vietnamese_stt
from backend.voice.vietnamese_policy import (
    handle_sensor_or_status_query_vi,
    parse_direct_device_intents_vi,
)


def test_crit01_stt_warm_state_nonblocking_during_preload() -> None:
    """get_local_stt_warm_state() must return in <50ms even while _PRELOAD_LOCK is held."""
    acquired = threading.Event()
    release = threading.Event()

    def _hold_preload_lock() -> None:
        with vietnamese_stt._PRELOAD_LOCK:
            acquired.set()
            release.wait(timeout=2.0)

    t = threading.Thread(target=_hold_preload_lock, daemon=True)
    t.start()
    assert acquired.wait(timeout=1.0), "Failed to acquire _PRELOAD_LOCK in worker thread"
    try:
        t0 = time.perf_counter()
        state = vietnamese_stt.get_local_stt_warm_state()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert elapsed_ms < 50.0, f"get_local_stt_warm_state() blocked for {elapsed_ms:.1f}ms"
        assert isinstance(state, dict)
        assert set(state.keys()) >= {"ready", "cold_start_ms", "models"}
        assert isinstance(state["models"], list)
    finally:
        release.set()
        t.join(timeout=2.0)


def test_crit02_cap2_invite_registered_session_retains_user_id_and_link_permission() -> None:
    """Invite-registered Cap 2 account must retain user_id and link_permission after SQLite reload."""
    from backend.auth.guest_invites import create_invite

    store = get_session_store()
    inv = create_invite(owner_user_id="tuan_anh", tier=2, ttl_sec=3600)
    jti = str(inv["invite_id"])
    uid = f"user_{uuid.uuid4().hex[:16]}"
    sess = store.create_session(
        user_id=uid,
        tier=2,
        role="MEMBER",
        display_name="Thành viên thử nghiệm",
        email="cap2.member.test@example.com",
        source=f"guest_invite:{jti}",
        ttl_sec=3600,
    )

    # Simulate cache TTL expiry (>1.5s) by clearing in-memory cache so get_session reloads from SQLite
    with store._lock:
        store._memory_cache.pop(sess.session_id, None)
        store._sqlite_verified_mono.pop(sess.session_id, None)

    reloaded = store.get_session(sess.session_id)
    assert reloaded is not None
    assert reloaded.user_id == uid, f"Expected persistent user_id {uid}, got {reloaded.user_id}"
    assert not reloaded.user_id.startswith("guest_")
    assert reloaded.tier == 2
    assert reloaded.source == f"guest_invite:{jti}"

    # Verify ephemeral anonymous guest QR session still reloads cleanly as guest_<jti>
    ephemeral_uid = f"guest_{jti[:12]}"
    eph = store.create_session(
        user_id=ephemeral_uid,
        tier=3,
        role="CHILD_GUEST",
        display_name="Khách mời QR",
        email="",
        source=f"guest_invite:{jti}",
        ttl_sec=3600,
    )
    with store._lock:
        store._memory_cache.pop(eph.session_id, None)
        store._sqlite_verified_mono.pop(eph.session_id, None)
    eph_reloaded = store.get_session(eph.session_id)
    assert eph_reloaded is not None
    assert eph_reloaded.user_id == ephemeral_uid

    # End-to-end check: Cap 1 grants link_permission to uid, then Cap 2 creates a rule after reload
    client = TestClient(app)
    owner_sess = store.create_session(
        user_id="tuan_anh",
        tier=1,
        role="ADMIN",
        display_name="Chủ nhà",
        email="owner@example.com",
        ttl_sec=3600,
    )
    grant_resp = client.post(
        f"/api/members/{uid}/link_permission",
        headers={"X-Session-Token": owner_sess.session_id},
        json={"allowed": True},
    )
    assert grant_resp.status_code == 200, grant_resp.text
    grant_body = grant_resp.json()
    if grant_body.get("requires_confirmation") and grant_body.get("pending_id"):
        conf_resp = client.post(
            f"/api/confirmations/{grant_body['pending_id']}",
            headers={"X-Session-Token": owner_sess.session_id},
            json={"confirm": True},
        )
        assert conf_resp.status_code == 200, conf_resp.text

    with store._lock:
        store._memory_cache.pop(sess.session_id, None)
        store._sqlite_verified_mono.pop(sess.session_id, None)

    rule_resp = client.post(
        "/api/rules",
        headers={"X-Session-Token": sess.session_id},
        json={
            "when_device_id": "living_room_light",
            "when_state": "ON",
            "then_device_id": "bedroom_light",
            "then_action": "turn_on",
        },
    )
    assert rule_resp.status_code == 200, f"Cap 2 lost link_permission after reload: {rule_resp.status_code} {rule_resp.text}"
    rule_body = rule_resp.json()
    if rule_body.get("requires_confirmation") and rule_body.get("pending_id"):
        rconf = client.post(
            f"/api/confirmations/{rule_body['pending_id']}",
            headers={"X-Session-Token": sess.session_id},
            json={"confirm": True},
        )
        assert rconf.status_code == 200, rconf.text
        assert rconf.json().get("ok") is True


@pytest.mark.parametrize(
    "utterance,expected_dev",
    [
        ("cho máy bơm nghỉ chạy đi em", "garden_pump"),
        ("cho bom vuon nghi chay di", "garden_pump"),
        ("cho máy bơm ngừng hoạt động đi", "garden_pump"),
        ("cho đèn phòng khách nghỉ sáng đi", "living_room_light"),
        ("thôi chạy máy bơm nước đi", "garden_pump"),
        ("dừng bơm nước ngoài vườn lại", "garden_pump"),
        ("cho còi báo động ngừng kêu đi", "alarm_siren"),
        ("cho nguồn mạch loa thôi phát đi", "speaker_amp"),
        ("nghỉ tưới cây đi em", "garden_pump"),
    ],
)
def test_crit03_cease_activity_verb_compounds_always_resolve_off(utterance: str, expected_dev: str) -> None:
    """Cease/stop verbs preceding activity verbs must resolve to turn_off, never turn_on."""
    actions = parse_direct_device_intents_vi(utterance)
    assert actions is not None and len(actions) >= 1, f"Failed to parse stop compound: {utterance!r}"
    assert actions[0]["device_id"] == expected_dev, f"Wrong device for {utterance!r}: {actions}"
    assert actions[0]["action"] == "turn_off", f"Polarity inversion on {utterance!r}: {actions}"


def test_crit04_echo_guard_rescues_bare_imperative_after_refusal_and_compound() -> None:
    """Bare imperative commands must not be falsely echo-suppressed after an AI refusal reply."""
    guard = ServerEchoGuard()
    ai_refusal = (
        "Xin lỗi, thiết bị bạn vừa nhắc chưa được hỗ trợ. "
        "Hệ thống hiện chỉ hỗ trợ cửa chính, đèn phòng khách, đèn phòng ngủ, "
        "máy bơm tưới cây, còi báo động và nguồn mạch loa."
    )
    guard.record_ai_utterance(ai_refusal, now=100.0)

    user_norm = normalize_for_echo_compare("đóng cửa chính")
    ai_norm = normalize_for_echo_compare(ai_refusal)
    score, reason = compute_echo_similarity(user_norm, ai_norm)
    assert reason == "" and score < 0.80, f"False echo suppression on bare imperative: score={score}, reason={reason}"

    is_echo, _sc, _rsn = guard.check_echo_transcript("đóng cửa chính", now=101.0)
    assert not is_echo, "ServerEchoGuard falsely suppressed 'đóng cửa chính' after AI refusal"

    # Real verbatim echo of AI reply must still be suppressed
    real_echo, _sc2, _r2 = guard.check_echo_transcript(
        "Xin lỗi thiết bị bạn vừa nhắc chưa được hỗ trợ",
        now=101.5,
    )
    assert real_echo, "ServerEchoGuard failed to suppress genuine AI echo"


def test_triv01_get_timers_and_vietnamese_404_405() -> None:
    """GET /api/timers works with RBAC and 404/405 return Vietnamese detail strings."""
    client = TestClient(app)
    store = get_session_store()

    # Unauthenticated GET /api/timers -> 401
    r_unauth = client.get("/api/timers")
    assert r_unauth.status_code == 401

    # Cap 1 GET /api/timers -> 200
    owner = store.create_session(user_id="tuan_anh", tier=1, role="ADMIN", display_name="Chủ nhà", ttl_sec=3600)
    r_owner = client.get("/api/timers", headers={"X-Session-Token": owner.session_id})
    assert r_owner.status_code == 200
    body_owner = r_owner.json()
    assert body_owner.get("ok") is True
    assert isinstance(body_owner.get("timers"), list)

    # Cap 3 GET /api/timers -> 403
    guest = store.create_session(user_id="khach_c", tier=3, role="CHILD_GUEST", display_name="Khách C", ttl_sec=3600)
    r_guest = client.get("/api/timers", headers={"X-Session-Token": guest.session_id})
    assert r_guest.status_code == 403

    # HTTP 405 must return Vietnamese detail (no English 'Method Not Allowed')
    r_405 = client.delete("/api/health")
    assert r_405.status_code == 405
    d405 = str(r_405.json().get("detail") or "")
    assert "Method Not Allowed" not in d405
    assert "không được hỗ trợ" in d405.lower()

    # HTTP 404 must return Vietnamese detail (no English 'Not Found')
    r_404 = client.get("/api/this_route_does_not_exist_12345")
    assert r_404.status_code == 404
    d404 = str(r_404.json().get("detail") or "")
    assert "Not Found" not in d404
    assert "không tìm thấy" in d404.lower()


def test_triv04_garbled_prefix_not_hijacked_as_device_status_query() -> None:
    """Unrecognized/garbled non-query prefixes before 'trạng thái thiết bị' must not run device_status_query."""
    eng = SmartHomeEngine()
    sess = UserSession(
        session_id="sess_test_triv04",
        user_id="tuan_anh",
        email="owner@example.com",
        display_name="Chủ nhà",
        tier=1,
        role="ADMIN",
        created_at=time.time(),
        expires_at=time.time() + 3600,
        source="test",
        is_authenticated=True,
    )

    for bad in (
        "rexit trạng thái thiết bị",
        "ri xet trạng thái thiết bị",
        "blarg trạng thái thiết bị",
        "xyz tình trạng thiết bị",
    ):
        res = handle_sensor_or_status_query_vi(bad, eng, session=sess)
        assert res is None, f"Unexpectedly executed status query for {bad!r}: {res}"

    for good in (
        "trạng thái các thiết bị",
        "xem trạng thái thiết bị",
        "kiểm tra trạng thái đèn phòng khách",
    ):
        res = handle_sensor_or_status_query_vi(good, eng, session=sess)
        assert res is not None and res.get("kind") == "device_status_query", f"Legitimate query broken: {good!r}"
