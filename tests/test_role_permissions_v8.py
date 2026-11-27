"""Isolated Role-Permission Regression Suite (Round 8).

Verifies ZERO wrong permission denials for ANY authenticated Tier-1 (`cap 1`) account
(lowercase ID, mixed-case ID, OWNER role, poisoned singleton engine, and expired 60s WS ticket)
and ZERO wrong permission grants for Tier-2 (`cap 2`) and Tier-3 (`cap 3`) accounts across
all 7 flows on REST, /api/text_command, /api/voice_command, and Gemini Live tool dispatch.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.voice_policy.run_voice_journeys import verify_vietnamese_only_output


@pytest.fixture(autouse=True)
def _sandbox_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")
    monkeypatch.setenv("SMARTHOME_AOEDE_CACHE_ONLY", "1")
    monkeypatch.setenv("SMARTHOME_SKIP_STT_PRELOAD", "1")


def _reset_clean_state() -> Any:
    from backend.api import routes_devices
    from backend.automation_engine import clear_compound_rules_scoped
    from backend.automation_repo import (
        reset_custom_commands_scoped,
        reset_links_scoped,
        reset_timers_and_schedules_scoped,
    )
    from backend.database_sqlite import open_wal_connection, resolve_sqlite_db_path
    from backend.voice.session_voice_command import reset_session_echo_guards

    reset_session_echo_guards()
    engine = routes_devices._REST_ENGINE
    reset_custom_commands_scoped(clear_all=True, engine=engine)
    reset_links_scoped(clear_all=True, engine=engine)
    reset_timers_and_schedules_scoped(clear_all=True, engine=engine)
    clear_compound_rules_scoped(clear_all=True)
    conn = open_wal_connection(resolve_sqlite_db_path(), readonly=False)
    try:
        conn.execute("UPDATE pending_confirmations SET status = 'cancelled' WHERE status = 'pending'")
        conn.commit()
    finally:
        conn.close()
    for did in ("main_door", "living_room_light", "bedroom_light", "garden_pump", "alarm_siren", "speaker_amp"):
        act = "close" if did == "main_door" else "turn_off"
        asyncio.run(engine.execute_device_action(did, act, bypass_rbac=True, trigger_chains=False))
    asyncio.run(engine.update_sensor_telemetry(temp_c=27.5, humidity_pct=62.0))
    asyncio.run(engine.update_soil_moisture_telemetry(58.0))
    asyncio.run(engine.update_sound_telemetry(sound_detected=False))
    return engine


def _assert_vi(data: dict[str, Any]) -> str:
    reply = str(
        data.get("exact_spoken_reply")
        or data.get("reply")
        or data.get("error")
        or data.get("message")
        or ""
    ).strip()
    ok_vi, reason = verify_vietnamese_only_output(reply, allow_empty=False)
    assert ok_vi, f"Non-Vietnamese reply ({reason}): {reply!r}"
    return reply


def _make_isolated_sessions() -> dict[str, Any]:
    """Create isolated throwaway cap 1 (lowercase, mixed-case, OWNER role), cap 2, and cap 3 sessions."""
    from backend.auth.session_store import get_session_store

    store = get_session_store()
    tag = secrets.token_hex(4)
    # Never use owner/prod credentials or print passwords.
    _runtime_pw_unused = secrets.token_urlsafe(16)
    assert len(_runtime_pw_unused) >= 16

    s_cap1_low = store.create_session(
        user_id=f"iso_cap1_low_{tag}",
        email=f"iso_cap1_low_{tag}@sandbox.local",
        display_name="Chủ nhà Thử Nghiệm 1",
        tier=1,
        role="ADMIN",
        source="rbac_v8_test",
    )
    s_cap1_mixed = store.create_session(
        user_id=f"IsoCap1_Mixed_{tag}",
        email=f"iso_cap1_mixed_{tag}@sandbox.local",
        display_name="Chủ nhà Thử Nghiệm 2",
        tier=1,
        role="ADMIN",
        source="rbac_v8_test",
    )
    s_cap1_owner_role = store.create_session(
        user_id=f"IsoCap1_OwnerRole_{tag}",
        email=f"iso_cap1_owner_{tag}@sandbox.local",
        display_name="Chủ nhà Thử Nghiệm 3",
        tier=1,
        role="OWNER",
        source="rbac_v8_test",
    )
    s_cap2 = store.create_session(
        user_id=f"IsoCap2_Member_{tag}",
        email=f"iso_cap2_{tag}@sandbox.local",
        display_name="Thành viên Thử Nghiệm",
        tier=2,
        role="MEMBER",
        source="rbac_v8_test",
    )
    s_cap3 = store.create_session(
        user_id=f"IsoCap3_Guest_{tag}",
        email=f"iso_cap3_{tag}@sandbox.local",
        display_name="Khách Thử Nghiệm",
        tier=3,
        role="CHILD_GUEST",
        source="rbac_v8_test",
    )
    return {
        "cap1_low": s_cap1_low,
        "cap1_mixed": s_cap1_mixed,
        "cap1_owner_role": s_cap1_owner_role,
        "cap2": s_cap2,
        "cap3": s_cap3,
    }


def test_cap1_zero_wrong_denials_rest_text_voice_and_poisoned_singleton() -> None:
    """Any authenticated cap 1 account has full permission on all 7 flows even if singleton engine had a revoked user."""
    from backend.server import app

    engine = _reset_clean_state()
    sessions = _make_isolated_sessions()

    # Poison singleton _REST_ENGINE._current_user_id with a revoked/inactive user (root cause #2 repro)
    revoked_id = f"revoked_member_{secrets.token_hex(3)}"
    engine.users[revoked_id] = {
        "id": revoked_id,
        "name": "Thành viên bị thu hồi",
        "tier": 2,
        "role": "UNKNOWN",
        "active": False,
    }
    engine._current_user_id = revoked_id
    engine._current_role = "UNKNOWN"

    try:
        with TestClient(app) as client:
            for key in ("cap1_low", "cap1_mixed", "cap1_owner_role"):
                sess = sessions[key]
                hdrs = {"X-Session-Token": sess.session_id}

                # 1. Direct control of ALL 6 devices via /api/voice_command & /api/device
                voice_cmds = [
                    ("mở cửa chính", "main_door", "OPEN"),
                    ("bật đèn phòng khách", "living_room_light", "ON"),
                    ("bật đèn phòng ngủ", "bedroom_light", "ON"),
                    ("bật máy bơm tưới cây", "garden_pump", "ON"),
                    ("bật còi báo động", "alarm_siren", "ON"),
                    ("bật nguồn mạch loa", "speaker_amp", "ON"),
                ]
                for utt, dev_id, exp_st in voice_cmds:
                    r = client.post("/api/voice_command", headers=hdrs, json={"transcript": utt})
                    assert r.status_code == 200, f"{key} denied on {utt!r}: {r.status_code} {r.text}"
                    d = r.json()
                    assert d.get("rbac_blocked") is False
                    assert d.get("executed") is True
                    reply = _assert_vi(d)
                    assert "không có quyền" not in reply.lower(), f"Wrong cap1 denial: {reply!r}"
                    assert engine.devices[dev_id]["state"] == exp_st

                # REST /api/device on restricted Tier-1 devices
                for dev_id, act in (("main_door", "close"), ("alarm_siren", "turn_off")):
                    r_dev = client.post("/api/device", headers=hdrs, json={"device_id": dev_id, "action": act})
                    assert r_dev.status_code == 200, f"{key} REST /api/device {dev_id} failed: {r_dev.text}"
                    assert r_dev.json().get("rbac_blocked") is False

                # 2. Sensor & status queries via voice
                for q in (
                    "nhiệt độ và độ ẩm hiện tại bao nhiêu",
                    "độ ẩm đất hiện tại bao nhiêu",
                    "cảm biến có đang phát hiện tiếng động không",
                    "trạng thái các thiết bị trong nhà",
                ):
                    rq = client.post("/api/voice_command", headers=hdrs, json={"transcript": q})
                    assert rq.status_code == 200 and rq.json().get("rbac_blocked") is False
                    assert "không có quyền" not in _assert_vi(rq.json()).lower()

                # 3. Custom command create + confirm + run + confirm + delete + confirm via voice
                rc1 = client.post(
                    "/api/voice_command",
                    headers=hdrs,
                    json={"transcript": "tạo lệnh về nhà là bật đèn phòng khách và mở cửa chính"},
                )
                assert rc1.status_code == 200 and rc1.json().get("requires_confirmation") is True
                rc1_ok = client.post("/api/voice_command", headers=hdrs, json={"transcript": "ok"})
                assert rc1_ok.status_code == 200 and rc1_ok.json().get("confirmed") is True

                rc_run = client.post("/api/voice_command", headers=hdrs, json={"transcript": "về nhà"})
                assert rc_run.status_code == 200
                assert rc_run.json().get("requires_confirmation") is False
                assert rc_run.json().get("executed") is True

                rc_del = client.post("/api/voice_command", headers=hdrs, json={"transcript": "xóa lệnh về nhà"})
                assert rc_del.status_code == 200 and rc_del.json().get("requires_confirmation") is True
                assert client.post("/api/voice_command", headers=hdrs, json={"transcript": "ok"}).json().get("confirmed") is True

                # 4. Timer & schedule create + confirm + delete via voice
                rt1 = client.post("/api/voice_command", headers=hdrs, json={"transcript": "hẹn giờ 10 phút nữa tắt đèn phòng khách"})
                assert rt1.status_code == 200 and rt1.json().get("requires_confirmation") is True
                assert client.post("/api/voice_command", headers=hdrs, json={"transcript": "ok"}).json().get("confirmed") is True
                rt_del = client.post("/api/voice_command", headers=hdrs, json={"transcript": "hủy hẹn giờ đèn phòng khách"})
                assert rt_del.status_code == 200 and rt_del.json().get("requires_confirmation") is True
                assert client.post("/api/voice_command", headers=hdrs, json={"transcript": "ok"}).json().get("confirmed") is True

                # 5. Cross-device & numeric-threshold rule via voice
                rr1 = client.post("/api/voice_command", headers=hdrs, json={"transcript": "khi nhiệt độ trên 33 độ thì bật còi báo động"})
                assert rr1.status_code == 200 and rr1.json().get("requires_confirmation") is True
                assert client.post("/api/voice_command", headers=hdrs, json={"transcript": "ok"}).json().get("confirmed") is True

                # 6. Resets via voice (device reset + factory reset staging -> cancel)
                rrst1 = client.post("/api/voice_command", headers=hdrs, json={"transcript": "hãy thiết lập lại thiết bị"})
                assert rrst1.status_code == 200 and rrst1.json().get("requires_confirmation") is True
                assert client.post("/api/voice_command", headers=hdrs, json={"transcript": "hủy"}).json().get("cancelled") is True

                rrst2 = client.post("/api/voice_command", headers=hdrs, json={"transcript": "khôi phục cài đặt gốc"})
                assert rrst2.status_code == 200 and rrst2.json().get("requires_confirmation") is True
                assert client.post("/api/voice_command", headers=hdrs, json={"transcript": "hủy"}).json().get("cancelled") is True

                # 7. Admin REST endpoint (/api/auth3/overview) allowed for ANY cap 1 (including OWNER role)
                r_adm = client.get("/api/auth3/overview", headers=hdrs)
                assert r_adm.status_code == 200, f"{key} denied on /api/auth3/overview: {r_adm.status_code}"
    finally:
        engine.users.pop(revoked_id, None)
        engine._current_user_id = "tuan_anh"
        engine._current_role = "ADMIN"


def test_cap1_live_bridge_mixed_case_owner_role_and_expired_ws_ticket() -> None:
    """LiveBridgeSession must bind mixed-case & OWNER-role cap 1 cleanly and retain auth after 60s WS ticket expiry."""
    from backend.live.gemini_bridge import LiveBridgeSession
    from backend.realtime_hub import mint_realtime_ticket

    _reset_clean_state()
    sessions = _make_isolated_sessions()

    class _FakeWS:
        def __init__(self, ticket: str = "") -> None:
            self.headers: dict[str, str] = {}
            self.cookies: dict[str, str] = {}
            self.query_params: dict[str, str] = {"ticket": ticket} if ticket else {}
            self.sent: list[dict[str, Any]] = []

        async def send_text(self, text: str) -> None:
            self.sent.append({"raw": text})

    async def _run() -> None:
        for key in ("cap1_low", "cap1_mixed", "cap1_owner_role"):
            sess = sessions[key]
            # Issue a real HMAC WS ticket valid for 2 seconds, then simulate expiry on open socket
            ws_ticket = mint_realtime_ticket(sess, ttl_sec=60)
            ws = _FakeWS(ticket=ws_ticket)
            bridge = LiveBridgeSession(ws)
            try:
                assert bridge.engine.current_tier == 1, f"{key}: tier={bridge.engine.current_tier}"
                assert str(bridge.engine.current_role).upper() in ("ADMIN", "OWNER")
                assert bridge.last_mic_turn_blocked is False

                # Simulate 60s ticket expiry on open WebSocket (ticket query param is now invalid/expired)
                ws.query_params["ticket"] = "rt_expired.invalid"
                bridge._cached_ws_actor_ts = time.perf_counter() - 10.0

                # Re-resolving session must retain valid stored session (NOT downgrade to unauthenticated!)
                actor_after = bridge._bind_actor_to_engine()
                assert actor_after.is_authenticated is True
                assert actor_after.tier == 1

                # Execute all critical Live Voice AI tools for cap 1 -> ZERO rbac_blocked!
                live_calls = [
                    ("control_device", {"device_id": "main_door", "action": "open"}),
                    ("control_device", {"device_id": "alarm_siren", "action": "turn_on"}),
                    ("read_sensors", {}),
                    ("create_timer", {"device_id": "living_room_light", "action": "turn_on", "seconds": 30}),
                    ("confirm_or_cancel_pending_action", {"confirmed": False}),
                    (
                        "create_automation_rule",
                        {
                            "logic": "AND",
                            "conditions": [{"source": "temp_sensor", "operator": ">", "value": 31}],
                            "actions": [{"device_id": "alarm_siren", "action": "turn_on"}],
                        },
                    ),
                    ("confirm_or_cancel_pending_action", {"confirmed": False}),
                    ("request_factory_reset", {"scope": "all"}),
                    ("confirm_factory_reset", {"confirmed": False}),
                    ("set_query_permission_policy", {"mode": "tier_restricted"}),
                ]
                for fn_name, fn_args in live_calls:
                    res = await bridge.handle_tool_call(SimpleNamespace(name=fn_name, args=fn_args))
                    assert res.get("rbac_blocked") is not True, f"{key} Live {fn_name} wrongly blocked: {res}"
                    assert (
                        res.get("ok") is True or res.get("cancelled") is True
                    ), f"{key} Live {fn_name} failed: {res}"
                    reply = str(res.get("exact_spoken_reply") or res.get("reply") or res.get("message") or "")
                    assert "không có quyền" not in reply.lower(), f"{key} Live {fn_name} wrong denial text: {reply!r}"
            finally:
                bridge.close()

    asyncio.run(_run())


def test_cap2_and_cap3_zero_wrong_grants_and_exact_vietnamese_policy() -> None:
    """Verify exact allow/deny matrix for cap 2 and cap 3 across REST, text, voice, and Live tools."""
    from backend.live.gemini_bridge import LiveBridgeSession
    from backend.server import app

    engine = _reset_clean_state()
    sessions = _make_isolated_sessions()
    s2 = sessions["cap2"]
    s3 = sessions["cap3"]
    h2 = {"X-Session-Token": s2.session_id}
    h3 = {"X-Session-Token": s3.session_id}

    with TestClient(app) as client:
        # --- CAP 2 ALLOWED ---
        for utt, dev_id in (
            ("bật đèn phòng khách", "living_room_light"),
            ("bật đèn phòng ngủ", "bedroom_light"),
            ("bật máy bơm tưới cây", "garden_pump"),
            ("bật nguồn mạch loa", "speaker_amp"),
        ):
            r = client.post("/api/voice_command", headers=h2, json={"transcript": utt})
            assert r.status_code == 200 and r.json().get("executed") is True
            assert engine.devices[dev_id]["state"] == "ON"
            assert "không có quyền" not in _assert_vi(r.json()).lower()

        # Cap 2 allowed own timers & custom commands
        rt2 = client.post("/api/voice_command", headers=h2, json={"transcript": "hẹn giờ 15 phút nữa tắt đèn phòng ngủ"})
        assert rt2.status_code == 200 and rt2.json().get("requires_confirmation") is True
        assert client.post("/api/voice_command", headers=h2, json={"transcript": "hủy"}).json().get("cancelled") is True

        # --- CAP 2 DENIED (0 wrong grants!) ---
        for denied_utt in (
            "mở cửa chính",
            "bật còi báo động",
            "khôi phục cài đặt gốc",
            "Reset trạng thái thiết bị.",
            "hãy thiết lập lại thiết bị",
            "khi đèn phòng khách bật thì bật đèn phòng ngủ",  # ungranted link permission
        ):
            r = client.post("/api/voice_command", headers=h2, json={"transcript": denied_utt})
            assert r.status_code == 403 and r.json().get("rbac_blocked") is True, f"cap2 wrongly allowed {denied_utt!r}"
            _assert_vi(r.json())
            r_txt = client.post("/api/text_command", headers=h2, json={"text": denied_utt})
            assert r_txt.status_code == 403 and r_txt.json().get("rbac_blocked") is True, f"cap2 text wrongly allowed {denied_utt!r}"
        assert engine.devices["main_door"]["state"] == "CLOSED"
        assert engine.devices["alarm_siren"]["state"] == "OFF"
        assert client.get("/api/auth3/overview", headers=h2).status_code == 403
        r_rst_dev = client.post("/api/automation/reset", headers=h2, json={"scope": "devices"})
        assert r_rst_dev.status_code == 403 and r_rst_dev.json().get("rbac_blocked") is True

        # --- CAP 3 ALLOWED (2 lights ONLY) ---
        for utt, dev_id in (
            ("tắt đèn phòng khách", "living_room_light"),
            ("tắt đèn phòng ngủ", "bedroom_light"),
        ):
            r = client.post("/api/voice_command", headers=h3, json={"transcript": utt})
            assert r.status_code == 200 and r.json().get("executed") is True
            assert engine.devices[dev_id]["state"] == "OFF"
            assert "không có quyền" not in _assert_vi(r.json()).lower()

        # --- CAP 3 DENIED (0 wrong grants on 4 devices + ALL automation/resets/admin) ---
        for denied_utt in (
            "mở cửa chính",
            "bật máy bơm tưới cây",
            "bật còi báo động",
            "bật nguồn mạch loa",
            "hẹn giờ 5 phút nữa bật đèn phòng khách",
            "đặt lịch 08:00 bật đèn phòng khách",
            "tạo lệnh khách là bật đèn phòng khách",
            "khi nhiệt độ trên 30 độ thì bật đèn phòng khách",
            "hãy thiết lập lại thiết bị",
            "khôi phục cài đặt gốc",
        ):
            for ep, payload in (
                ("/api/voice_command", {"transcript": denied_utt}),
                ("/api/text_command", {"text": denied_utt}),
            ):
                r = client.post(ep, headers=h3, json=payload)
                assert r.status_code == 403 and r.json().get("rbac_blocked") is True, f"cap3 wrongly allowed {ep} {denied_utt!r}"
                _assert_vi(r.json())

        assert client.get("/api/auth3/overview", headers=h3).status_code == 403
        assert client.post("/api/timers", headers=h3, json={"device_id": "living_room_light", "action": "turn_on", "seconds": 10}).status_code == 403
        assert client.post("/api/rules", headers=h3, json={"logic": "AND", "conditions": [{"source": "temp_sensor", "operator": ">", "value": 30}], "actions": [{"device_id": "living_room_light", "action": "turn_on"}]}).status_code == 403

    # Live tool RBAC for cap 2 and cap 3 -> 0 wrong grants
    class _StubWS:
        headers: dict[str, str] = {}
        cookies: dict[str, str] = {}
        query_params: dict[str, str] = {}

        async def send_text(self, text: str) -> None:
            return None

    async def _check_live_denials() -> None:
        br2 = LiveBridgeSession(_StubWS(), ws_session=s2)
        br3 = LiveBridgeSession(_StubWS(), ws_session=s3)
        try:
            for fn_name, fn_args in (
                ("control_device", {"device_id": "main_door", "action": "open"}),
                ("control_device", {"device_id": "alarm_siren", "action": "turn_on"}),
                ("reset_automations", {"scope": "devices"}),
                ("set_query_permission_policy", {"mode": "open_all"}),
            ):
                r2 = await br2.handle_tool_call(SimpleNamespace(name=fn_name, args=fn_args))
                assert r2.get("rbac_blocked") is True and r2.get("ok") is False, f"cap2 Live allowed {fn_name}: {r2}"

            for fn_name, fn_args in (
                ("control_device", {"device_id": "main_door", "action": "open"}),
                ("control_device", {"device_id": "garden_pump", "action": "turn_on"}),
                ("create_timer", {"device_id": "living_room_light", "action": "turn_on", "seconds": 10}),
                ("request_factory_reset", {"scope": "all"}),
                ("set_query_permission_policy", {"mode": "open_all"}),
            ):
                r3 = await br3.handle_tool_call(SimpleNamespace(name=fn_name, args=fn_args))
                assert r3.get("rbac_blocked") is True and r3.get("ok") is False, f"cap3 Live allowed {fn_name}: {r3}"

            # Cap 3 Live allowed on living_room_light
            r3_ok = await br3.handle_tool_call(SimpleNamespace(name="control_device", args={"device_id": "living_room_light", "action": "turn_on"}))
            assert r3_ok.get("ok") is True and r3_ok.get("rbac_blocked") is not True
        finally:
            br2.close()
            br3.close()

    asyncio.run(_check_live_denials())
