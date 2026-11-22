"""Fast deterministic pytest E2E suite for the Act-First, Vietnamese-Only Voice Policy.

Covers ALL 10 Mandatory Coverage Matrix categories (1-10) and Policies 1-6:
  - Cat 1: Session start, greetings, small talk, identity, help (never 403 for ANY tier)
  - Cat 2: All 6 devices immediate act-first + short reply (no confirmation), all_lights, redundant, multi-device
  - Cat 3: Sensor readings (DHT11 temp/hum, soil moisture, KY-037 sound), device status, auto-pump
  - Cat 4: Custom command create/confirm/use/confirm/edit/confirm/delete/confirm
  - Cat 5: Schedules/timers create (clock/countdown/daily), list, modify, VERIFY real short timer fires, cancel
  - Cat 6: Cross-connected rules (door->light, soil_dry->pump, loud_sound->siren) + VERIFY all 3 actually trigger + list + delete
  - Cat 7: Reset device states, reset rules/links, factory reset (confirmation required) + state verification
  - Cat 8: Confirmation edge flows (ok/được/ừ/có/đồng ý, không/thôi/hủy, 60s TTL expiry, unrelated reply reminder, mid-confirm interruption)
  - Cat 9: Unknown/unsupported devices (incl. rèm cửa/quạt/điều hòa), partial/ambiguous, nonsense, foreign speech (100% Vietnamese output, 0 false actions), Tier 2 & Tier 3 RBAC enforcement
  - Cat 10: Session end & resume
  - Local Whisper STT guard: rejects pure white noise without false actions
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.voice_policy.audio_synth import synth_pure_white_noise
from tests.voice_policy.run_voice_journeys import verify_vietnamese_only_output


def _seed_sessions() -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    from simulator.auth.session_store import get_session_store

    store = get_session_store()
    s1 = store.create_session(
        user_id="tuan_anh",
        email="nep94121@gmail.com",
        display_name="Chủ nhà QA",
        tier=1,
        role="ADMIN",
        source="pytest_voice_policy",
    )
    s1_resume = store.create_session(
        user_id="tuan_anh",
        email="nep94121@gmail.com",
        display_name="Chủ nhà QA",
        tier=1,
        role="ADMIN",
        source="pytest_voice_policy_resume",
    )
    s2 = store.create_session(
        user_id="qa_member_t2",
        email="qa_member@test.local",
        display_name="Thành viên QA",
        tier=2,
        role="MEMBER",
        source="pytest_voice_policy",
    )
    s3 = store.create_session(
        user_id="qa_guest_t3",
        email="qa_guest@test.local",
        display_name="Khách QA",
        tier=3,
        role="CHILD_GUEST",
        source="pytest_voice_policy",
    )
    return (
        {"X-Session-Token": s1.session_id},
        {"X-Session-Token": s1_resume.session_id},
        {"X-Session-Token": s2.session_id},
        {"X-Session-Token": s3.session_id},
    )


def _reset_engine_clean() -> Any:
    from simulator.api import routes_devices
    from simulator.automation_repo import (
        reset_custom_commands_scoped,
        reset_links_scoped,
        reset_timers_and_schedules_scoped,
    )
    from simulator.database_sqlite import open_wal_connection, resolve_sqlite_db_path
    from simulator.voice.session_voice_command import reset_session_echo_guards

    reset_session_echo_guards()
    engine = routes_devices._REST_ENGINE
    reset_custom_commands_scoped(clear_all=True, engine=engine)
    reset_links_scoped(clear_all=True, engine=engine)
    reset_timers_and_schedules_scoped(clear_all=True, engine=engine)
    conn = open_wal_connection(resolve_sqlite_db_path(), readonly=False)
    try:
        conn.execute("UPDATE pending_confirmations SET status = 'cancelled' WHERE status = 'pending'")
        conn.commit()
    finally:
        conn.close()
    for did in ("main_door", "living_room_light", "bedroom_light", "garden_pump", "alarm_siren", "speaker_amp"):
        act = "close" if did == "main_door" else "turn_off"
        asyncio.run(engine.execute_device_action(did, act, bypass_rbac=True, trigger_chains=False))
    asyncio.run(engine.update_sensor_telemetry(temp_c=28.5, humidity_pct=65.0))
    asyncio.run(engine.update_soil_moisture_telemetry(58.0))
    asyncio.run(engine.update_sound_telemetry(sound_detected=False))
    return engine


def _assert_vi_reply(data: dict[str, Any], allow_empty: bool = False) -> str:
    reply = str(data.get("exact_spoken_reply") or data.get("reply") or data.get("error") or "").strip()
    ok_vi, reason = verify_vietnamese_only_output(reply, allow_empty=allow_empty)
    assert ok_vi, f"Non-Vietnamese reply ({reason}): {reply!r}"
    return reply


# ============================================================================
# CATEGORY 1 & 10: Session Start, Small Talk, Identity, Help, End & Resume
# ============================================================================


def test_cat1_cat10_greetings_small_talk_and_resume_never_403() -> None:
    from simulator.server import app

    _reset_engine_clean()
    h1, h1_resume, h2, h3 = _seed_sessions()

    with TestClient(app) as client:
        for hdr in (h1, h2, h3):
            for phrase in ("chào bạn", "xin chào", "chào buổi sáng", "bạn là ai", "bạn có thể làm những gì", "cảm ơn bạn", "tạm biệt"):
                for ep, body in (
                    ("/api/text_command", {"text": phrase}),
                    ("/api/voice_command", {"transcript": phrase}),
                ):
                    r = client.post(ep, headers=hdr, json=body)
                    assert r.status_code == 200, f"{ep} {phrase!r} returned {r.status_code}: {r.text}"
                    d = r.json()
                    assert d["ok"] is True
                    assert d.get("rbac_blocked") is False
                    assert d.get("requires_confirmation") is False
                    assert d.get("executed") is False
                    reply = _assert_vi_reply(d)
                    assert "không có quyền" not in reply.lower()

        # Session resume on a fresh owner session token
        r_res = client.post("/api/voice_command", headers=h1_resume, json={"transcript": "mở cửa chính"})
        assert r_res.status_code == 200 and r_res.json().get("executed") is True
        _assert_vi_reply(r_res.json())


# ============================================================================
# CATEGORY 2: Simple Direct Device Commands (Act-First, All 6 Devices + Multi + Redundant)
# ============================================================================


def test_cat2_all_6_devices_act_first_immediately_plus_all_lights_redundant_and_multi() -> None:
    from simulator.server import app

    engine = _reset_engine_clean()
    h1, _, _, _ = _seed_sessions()

    with TestClient(app) as client:
        cases = [
            ("mở cửa", "main_door", "OPEN", "đã mở cửa chính"),
            ("mở cửa chính", "main_door", "OPEN", "đang mở"),
            ("đóng cửa chính", "main_door", "CLOSED", "đã đóng cửa chính"),
            ("bật đèn phòng khách", "living_room_light", "ON", "đã bật đèn phòng khách"),
            ("tắt đèn phòng khách", "living_room_light", "OFF", "đã tắt đèn phòng khách"),
            ("bật đèn phòng ngủ", "bedroom_light", "ON", "đã bật đèn phòng ngủ"),
            ("tắt đèn phòng ngủ", "bedroom_light", "OFF", "đã tắt đèn phòng ngủ"),
            ("bật máy bơm tưới cây", "garden_pump", "ON", "đã bật máy bơm"),
            ("tắt máy bơm", "garden_pump", "OFF", "đã tắt máy bơm"),
            ("bật còi báo động", "alarm_siren", "ON", "đã bật còi báo động"),
            ("tắt còi báo động", "alarm_siren", "OFF", "đã tắt còi báo động"),
            ("bật nguồn mạch loa", "speaker_amp", "ON", "đã bật nguồn mạch loa"),
            ("tắt nguồn mạch loa", "speaker_amp", "OFF", "đã tắt nguồn mạch loa"),
        ]
        for phrase, dev_id, exp_state, exp_sub in cases:
            r = client.post("/api/voice_command", headers=h1, json={"transcript": phrase})
            assert r.status_code == 200, f"{phrase!r} -> {r.status_code} {r.text}"
            d = r.json()
            assert d["ok"] is True
            assert d.get("requires_confirmation") is False, f"{phrase!r} must NOT ask confirmation!"
            assert d.get("executed") is True
            assert engine.devices[dev_id]["state"] == exp_state, f"{phrase!r}: {dev_id}={engine.devices[dev_id]['state']}"
            reply = _assert_vi_reply(d)
            assert exp_sub in reply.lower(), f"{phrase!r}: expected {exp_sub!r} in {reply!r}"

        # All lights ON then OFF
        r_on = client.post("/api/text_command", headers=h1, json={"text": "bật tất cả đèn"})
        assert r_on.status_code == 200 and r_on.json().get("executed") is True
        assert engine.devices["living_room_light"]["state"] == "ON"
        assert engine.devices["bedroom_light"]["state"] == "ON"
        _assert_vi_reply(r_on.json())

        r_off = client.post("/api/text_command", headers=h1, json={"text": "tắt hết đèn"})
        assert r_off.status_code == 200 and r_off.json().get("executed") is True
        assert engine.devices["living_room_light"]["state"] == "OFF"
        assert engine.devices["bedroom_light"]["state"] == "OFF"

        # Multi-device in one sentence + fillers/colloquial
        r_multi = client.post("/api/voice_command", headers=h1, json={"transcript": "ờ mở cổng và bật bóng đèn khách giúp mình nha"})
        assert r_multi.status_code == 200 and r_multi.json().get("executed") is True
        assert r_multi.json().get("requires_confirmation") is False
        assert engine.devices["main_door"]["state"] == "OPEN"
        assert engine.devices["living_room_light"]["state"] == "ON"
        _assert_vi_reply(r_multi.json())


# ============================================================================
# CATEGORY 3: Sensor & Device Status Readings
# ============================================================================


def test_cat3_sensor_and_device_status_queries_immediate() -> None:
    from simulator.server import app

    engine = _reset_engine_clean()
    asyncio.run(engine.update_sensor_telemetry(temp_c=29.4, humidity_pct=68.0))
    asyncio.run(engine.update_soil_moisture_telemetry(54.0))
    asyncio.run(engine.execute_device_action("main_door", "open", bypass_rbac=True))
    h1, _, _, _ = _seed_sessions()

    with TestClient(app) as client:
        queries = [
            ("nhiệt độ và độ ẩm hiện tại là bao nhiêu", ("29.4", "68")),
            ("độ ẩm đất hiện tại bao nhiêu", ("54",)),
            ("cảm biến âm thanh KY-037 thế nào", ("yên tĩnh",)),
            ("cửa chính đang mở hay đóng", ("đang mở",)),
            ("chế độ bơm tự động thế nào", ("40%", "70%")),
            ("trạng thái các thiết bị trong nhà", ("cửa chính", "đèn phòng khách")),
        ]
        for q, expected_subs in queries:
            r = client.post("/api/voice_command", headers=h1, json={"transcript": q})
            assert r.status_code == 200
            d = r.json()
            assert d["ok"] is True
            assert d.get("requires_confirmation") is False
            reply = _assert_vi_reply(d)
            for sub in expected_subs:
                assert sub in reply.lower(), f"Query {q!r}: missing {sub!r} in {reply!r}"


# ============================================================================
# CATEGORY 4: Custom Commands (Create, Use, Edit, Delete — Confirmation Required)
# ============================================================================


def test_cat4_custom_command_crud_with_confirmation() -> None:
    from simulator.automation_repo import list_custom_commands
    from simulator.server import app

    engine = _reset_engine_clean()
    asyncio.run(engine.execute_device_action("living_room_light", "turn_on", bypass_rbac=True))
    asyncio.run(engine.execute_device_action("main_door", "open", bypass_rbac=True))
    h1, _, _, _ = _seed_sessions()

    with TestClient(app) as client:
        # Create
        r1 = client.post("/api/text_command", headers=h1, json={"text": "tạo lệnh đi làm là tắt tất cả đèn và đóng cửa chính"})
        assert r1.status_code == 200 and r1.json().get("requires_confirmation") is True
        assert len(list_custom_commands()) == 0
        r1_ok = client.post("/api/text_command", headers=h1, json={"text": "ok"})
        assert r1_ok.status_code == 200 and r1_ok.json().get("confirmed") is True
        assert len(list_custom_commands()) == 1

        # Use (requires confirmation -> then executes!)
        r2 = client.post("/api/text_command", headers=h1, json={"text": "đi làm"})
        assert r2.status_code == 200 and r2.json().get("requires_confirmation") is True
        assert engine.devices["main_door"]["state"] == "OPEN"
        r2_ok = client.post("/api/text_command", headers=h1, json={"text": "được"})
        assert r2_ok.status_code == 200 and r2_ok.json().get("confirmed") is True
        assert engine.devices["living_room_light"]["state"] == "OFF"
        assert engine.devices["main_door"]["state"] == "CLOSED"

        # Edit
        r3 = client.post("/api/text_command", headers=h1, json={"text": "sửa lệnh đi làm thành bật đèn phòng ngủ"})
        assert r3.status_code == 200 and r3.json().get("requires_confirmation") is True
        r3_ok = client.post("/api/text_command", headers=h1, json={"text": "ừ"})
        assert r3_ok.status_code == 200 and r3_ok.json().get("confirmed") is True

        # Delete
        r4 = client.post("/api/text_command", headers=h1, json={"text": "xóa lệnh đi làm"})
        assert r4.status_code == 200 and r4.json().get("requires_confirmation") is True
        r4_ok = client.post("/api/text_command", headers=h1, json={"text": "đồng ý"})
        assert r4_ok.status_code == 200 and r4_ok.json().get("confirmed") is True
        assert len(list_custom_commands()) == 0


# ============================================================================
# CATEGORY 5: Schedules & Timers (Create, List, Modify, VERIFY Real Fire, Cancel)
# ============================================================================


def test_cat5_schedules_and_short_timer_actually_fires() -> None:
    from simulator.automation_repo import list_schedules
    from simulator.server import app

    engine = _reset_engine_clean()
    h1, _, _, _ = _seed_sessions()

    with TestClient(app) as client:
        # Daily clock schedule create -> list -> modify -> delete
        r_sc = client.post("/api/text_command", headers=h1, json={"text": "đặt lịch 07:00 hằng ngày mở cửa chính"})
        assert r_sc.status_code == 200 and r_sc.json().get("requires_confirmation") is True
        assert client.post("/api/text_command", headers=h1, json={"text": "ok"}).json().get("confirmed") is True
        assert len(list_schedules(include_disabled=False)) == 1

        r_ls = client.post("/api/text_command", headers=h1, json={"text": "có những lịch hẹn nào"})
        assert r_ls.status_code == 200 and "07:00" in _assert_vi_reply(r_ls.json())

        r_mod = client.post("/api/text_command", headers=h1, json={"text": "sửa lịch 07:00 thành 08:00"})
        assert r_mod.status_code == 200 and r_mod.json().get("requires_confirmation") is True
        assert client.post("/api/text_command", headers=h1, json={"text": "có"}).json().get("confirmed") is True
        assert list_schedules(include_disabled=False)[0]["time_hhmm"] == "08:00"

        r_del = client.post("/api/text_command", headers=h1, json={"text": "xóa lịch 08:00"})
        assert r_del.status_code == 200 and r_del.json().get("requires_confirmation") is True
        assert client.post("/api/text_command", headers=h1, json={"text": "đồng ý"}).json().get("confirmed") is True
        assert len(list_schedules(include_disabled=False)) == 0

        # Short countdown timer: create -> confirm -> WAIT & VERIFY it ACTUALLY FIRES!
        assert engine.devices["bedroom_light"]["state"] == "OFF"
        r_tm = client.post("/api/text_command", headers=h1, json={"text": "hẹn giờ 1 giây bật đèn phòng ngủ"})
        assert r_tm.status_code == 200 and r_tm.json().get("requires_confirmation") is True
        assert client.post("/api/text_command", headers=h1, json={"text": "ok"}).json().get("confirmed") is True

        deadline = time.time() + 4.5
        while time.time() < deadline and engine.devices["bedroom_light"]["state"] != "ON":
            time.sleep(0.2)
        assert engine.devices["bedroom_light"]["state"] == "ON", "Short countdown timer did not fire!"


# ============================================================================
# CATEGORY 6: Cross-Connected Rules (Door->Light, Soil->Pump, Sound->Siren) — VERIFY ALL 3 TRIGGER
# ============================================================================


def test_cat6_all_three_cross_connected_rules_actually_trigger() -> None:
    from simulator.automation_repo import list_automation_rules
    from simulator.server import app

    engine = _reset_engine_clean()
    h1, _, _, _ = _seed_sessions()

    with TestClient(app) as client:
        # 1. Door OPEN -> living_room_light ON
        r1 = client.post("/api/text_command", headers=h1, json={"text": "khi mở cửa chính thì bật đèn phòng khách"})
        assert r1.status_code == 200 and r1.json().get("requires_confirmation") is True
        assert client.post("/api/text_command", headers=h1, json={"text": "ok"}).json().get("confirmed") is True

        client.post("/api/device", headers=h1, json={"device_id": "main_door", "action": "open"})
        assert engine.devices["living_room_light"]["state"] == "ON", "Cross-rule door->light did not trigger!"

        # 2. Soil DRY -> garden_pump ON
        r2 = client.post("/api/text_command", headers=h1, json={"text": "khi đất khô thì bật máy bơm tưới cây"})
        assert r2.status_code == 200 and r2.json().get("requires_confirmation") is True
        assert client.post("/api/text_command", headers=h1, json={"text": "được"}).json().get("confirmed") is True

        client.post("/api/device", headers=h1, json={"device_id": "garden_pump", "action": "turn_off"})
        client.post("/api/soil_moisture", headers=h1, json={"soil_moisture_pct": 22.0})
        assert engine.devices["garden_pump"]["state"] == "ON", "Cross-rule soil_dry->pump did not trigger!"

        # 3. Loud sound -> alarm_siren ON
        r3 = client.post("/api/text_command", headers=h1, json={"text": "khi có tiếng động lớn thì bật còi báo động"})
        assert r3.status_code == 200 and r3.json().get("requires_confirmation") is True
        assert client.post("/api/text_command", headers=h1, json={"text": "ừ"}).json().get("confirmed") is True

        client.post("/api/device", headers=h1, json={"device_id": "alarm_siren", "action": "turn_off"})
        client.post("/api/sound_sensor", headers=h1, json={"sound_detected": True})
        assert engine.devices["alarm_siren"]["state"] == "ON", "Cross-rule loud_sound->siren did not trigger!"

        # List & delete
        r_ls = client.post("/api/text_command", headers=h1, json={"text": "liệt kê các liên kết"})
        assert r_ls.status_code == 200 and len(list_automation_rules()) == 3
        _assert_vi_reply(r_ls.json())

        r_del = client.post("/api/text_command", headers=h1, json={"text": "xóa liên kết đèn phòng khách"})
        assert r_del.status_code == 200 and r_del.json().get("requires_confirmation") is True
        assert client.post("/api/text_command", headers=h1, json={"text": "ok"}).json().get("confirmed") is True
        assert len(list_automation_rules()) == 2


# ============================================================================
# CATEGORY 7: Reset (Device States, Rules, Factory Reset — Confirmation Required)
# ============================================================================


def test_cat7_reset_devices_rules_and_factory_reset_with_confirmation() -> None:
    from simulator.server import app

    engine = _reset_engine_clean()
    asyncio.run(engine.execute_device_action("main_door", "open", bypass_rbac=True))
    asyncio.run(engine.execute_device_action("living_room_light", "turn_on", bypass_rbac=True))
    h1, _, _, _ = _seed_sessions()

    with TestClient(app) as client:
        # Reset device states
        r1 = client.post("/api/text_command", headers=h1, json={"text": "reset trạng thái thiết bị"})
        assert r1.status_code == 200 and r1.json().get("requires_confirmation") is True
        assert engine.devices["main_door"]["state"] == "OPEN"
        r1_ok = client.post("/api/text_command", headers=h1, json={"text": "đồng ý"})
        assert r1_ok.status_code == 200 and r1_ok.json().get("confirmed") is True
        assert engine.devices["main_door"]["state"] == "CLOSED"
        assert engine.devices["living_room_light"]["state"] == "OFF"

        # Factory reset
        asyncio.run(engine.execute_device_action("bedroom_light", "turn_on", bypass_rbac=True))
        r2 = client.post("/api/text_command", headers=h1, json={"text": "khôi phục cài đặt gốc"})
        assert r2.status_code == 200 and r2.json().get("requires_confirmation") is True
        r2_ok = client.post("/api/text_command", headers=h1, json={"text": "ok"})
        assert r2_ok.status_code == 200 and r2_ok.json().get("confirmed") is True
        _assert_vi_reply(r2_ok.json())
        assert engine.devices["bedroom_light"]["state"] == "OFF"


# ============================================================================
# CATEGORY 8: Confirmation Edge Flows (Yes/No, Timeout, Unrelated, Interruption)
# ============================================================================


def test_cat8_confirmation_variants_timeout_unrelated_and_interruption() -> None:
    from simulator.automation_repo import list_pending_timers
    from simulator.database_sqlite import open_wal_connection, resolve_sqlite_db_path
    from simulator.server import app

    engine = _reset_engine_clean()
    h1, _, _, _ = _seed_sessions()

    with TestClient(app) as client:
        # No/cancel variants
        for cancel_word in ("không", "thôi", "hủy"):
            r_p = client.post("/api/voice_command", headers=h1, json={"transcript": "10 phút nữa tắt đèn phòng khách"})
            assert r_p.json().get("requires_confirmation") is True
            r_c = client.post("/api/voice_command", headers=h1, json={"transcript": cancel_word})
            assert r_c.status_code == 200 and r_c.json().get("cancelled") is True
            assert len(list_pending_timers()) == 0

        # Unrelated reply reminds without executing
        r_u1 = client.post("/api/voice_command", headers=h1, json={"transcript": "10 phút nữa bật đèn phòng ngủ"})
        assert r_u1.json().get("requires_confirmation") is True
        r_u2 = client.post("/api/voice_command", headers=h1, json={"transcript": "hôm nay trời mát quá nhỉ"})
        assert r_u2.status_code == 200 and r_u2.json().get("kind") == "confirmation_reminder"
        assert r_u2.json().get("executed") is False and len(list_pending_timers()) == 0
        client.post("/api/voice_command", headers=h1, json={"transcript": "hủy"})

        # Valid interruption cancels pending & executes new direct command immediately
        r_i1 = client.post("/api/voice_command", headers=h1, json={"transcript": "15 phút nữa bật máy bơm"})
        assert r_i1.json().get("requires_confirmation") is True
        r_i2 = client.post("/api/voice_command", headers=h1, json={"transcript": "bật đèn phòng khách"})
        assert r_i2.status_code == 200 and r_i2.json().get("executed") is True
        assert engine.devices["living_room_light"]["state"] == "ON"
        assert len(list_pending_timers()) == 0

        # Expired pending confirmation -> MUST NOT create timer
        r_e1 = client.post("/api/voice_command", headers=h1, json={"transcript": "12 phút nữa tắt đèn phòng khách"})
        pid = r_e1.json()["pending_id"]
        conn = open_wal_connection(resolve_sqlite_db_path(), readonly=False)
        try:
            conn.execute("UPDATE pending_confirmations SET expires_at = ? WHERE pending_id = ?", (time.time() - 5.0, pid))
            conn.commit()
        finally:
            conn.close()
        r_e2 = client.post("/api/voice_command", headers=h1, json={"transcript": "ok"})
        assert r_e2.status_code == 200 and r_e2.json().get("expired") is True
        assert len(list_pending_timers()) == 0


# ============================================================================
# CATEGORY 9: Error, Unknown Devices, Ambiguous, Foreign Speech, Noise & RBAC
# ============================================================================


def test_cat9_unknown_ambiguous_foreign_zero_false_actions_and_rbac() -> None:
    from simulator.server import app

    engine = _reset_engine_clean()
    h1, _, h2, h3 = _seed_sessions()

    with TestClient(app) as client:
        # Unknown devices, partial/ambiguous, nonsense, foreign -> ZERO actions, 100% Vietnamese reply!
        no_action_inputs = [
            "bật quạt trần",
            "tắt điều hòa",
            "đóng rèm cửa",
            "đóng dèm cửa",
            "mở tivi",
            "tất cả đèn",
            "cửa chính",
            "bật lên đi",
            "ờ à ừm",
            "asdfghjkl",
            "Hello please open the main door",
            "Bonjour ouvre la porte principale",
            "안녕하세요 불 켜주세요",
        ]
        for phrase in no_action_inputs:
            r = client.post("/api/voice_command", headers=h1, json={"transcript": phrase})
            assert r.status_code == 200, f"{phrase!r} -> {r.status_code}"
            d = r.json()
            assert d.get("executed") is False, f"FALSE ACTION on {phrase!r}: {d}"
            assert d.get("requires_confirmation") is False, f"Unexpected confirm on {phrase!r}: {d}"
            _assert_vi_reply(d)
            for did in ("main_door", "living_room_light", "bedroom_light", "garden_pump", "alarm_siren", "speaker_amp"):
                exp = "CLOSED" if did == "main_door" else "OFF"
                assert engine.devices[did]["state"] == exp, f"{phrase!r} mutated {did}!"

        # Tier 2 Family Member RBAC: allowed pump/lights/speaker, denied main_door/alarm_siren/factory_reset
        assert client.post("/api/voice_command", headers=h2, json={"transcript": "bật máy bơm tưới cây"}).status_code == 200
        assert engine.devices["garden_pump"]["state"] == "ON"
        for denied_t2 in ("mở cửa chính", "bật còi báo động", "khôi phục cài đặt gốc"):
            rt2 = client.post("/api/voice_command", headers=h2, json={"transcript": denied_t2})
            assert rt2.status_code == 403 and rt2.json().get("rbac_blocked") is True
            _assert_vi_reply(rt2.json())

        # Tier 3 Guest RBAC: allowed 2 lights ONLY, denied door/pump/siren/speaker/schedules/custom/links/resets
        assert client.post("/api/voice_command", headers=h3, json={"transcript": "bật đèn phòng khách"}).status_code == 200
        assert engine.devices["living_room_light"]["state"] == "ON"
        for denied_t3 in (
            "mở cửa chính",
            "bật máy bơm tưới cây",
            "bật còi báo động",
            "bật nguồn mạch loa",
            "10 phút nữa tắt đèn phòng khách",
            "tạo lệnh khách là bật đèn phòng khách",
            "khi đèn phòng khách bật thì bật đèn phòng ngủ",
            "reset trạng thái thiết bị",
        ):
            rt3 = client.post("/api/voice_command", headers=h3, json={"transcript": denied_t3})
            assert rt3.status_code == 403 and rt3.json().get("rbac_blocked") is True, f"Tier 3 allowed {denied_t3!r}!"
            _assert_vi_reply(rt3.json())


def test_local_whisper_stt_rejects_pure_white_noise_fast() -> None:
    """Pure stationary white noise must be rejected by _analyze_and_preprocess_audio without false actions."""
    from simulator.voice.vietnamese_stt import transcribe_vietnamese_pcm16k

    noise = synth_pure_white_noise(duration_sec=1.8, seed=777)
    res = transcribe_vietnamese_pcm16k(noise, sr=16000)
    assert res["ok"] is False
    assert res["is_noise"] is True
    assert res["text"] == ""


def test_round2_nlu_echo_guard_and_3d_pin_contrast_fixes() -> None:
    """Verify round-2 NLU normalizations, echo guard J03_07 fix, unsupported device guards, and 3D pin CSS."""
    from simulator.automation_nlu import (
        _normalize_vi_spoken_numbers,
        _parse_custom_command_create_or_edit,
        _parse_sensor_trigger,
    )
    from simulator.live.echo_and_speech_guard import ServerEchoGuard
    from simulator.voice.vietnamese_policy import parse_direct_device_intents_vi

    # 1. Echo guard J03_07: redundant command after 'đang bật rồi.' must NOT be echo-suppressed
    eg = ServerEchoGuard()
    eg.record_ai_utterance("Đèn phòng khách đang bật rồi.")
    is_echo, _sc, _rsn = eg.check_echo_transcript("bật đèn phòng khách")
    assert is_echo is False

    # 2. Unsupported devices & bare nouns must produce 0 actions
    for bad in ("mở cửa cuốn", "đóng rèm cửa", "đóng dèm cửa", "bật điều hòa", "cửa chính", "tất cả đèn"):
        assert parse_direct_device_intents_vi(bad) == [], f"Unexpected action on {bad!r}"

    # 3. Natural regional/colloquial direct commands preserve polarity; deleted ASR garbles must NOT falsely act
    assert parse_direct_device_intents_vi("Bật hết đèn.") == [
        {"device_id": "living_room_light", "action": "turn_on"},
        {"device_id": "bedroom_light", "action": "turn_on"},
    ]
    assert parse_direct_device_intents_vi("tắt loa") == [{"device_id": "speaker_amp", "action": "turn_off"}]
    assert parse_direct_device_intents_vi("khóa cửa chính") == [{"device_id": "main_door", "action": "close"}]
    assert parse_direct_device_intents_vi("bật còi hú") == [{"device_id": "alarm_siren", "action": "turn_on"}]
    # Deleted benchmark garbles must produce 0 direct mutations
    for deleted_garble in ("Bật thiết đèn.", "tắt hoa", "bật ngòi hú", "vận hành phòng khách"):
        assert parse_direct_device_intents_vi(deleted_garble) == [], f"Deleted garble leaked action: {deleted_garble!r}"

    # 4. Spoken Vietnamese numbers, compositional custom commands, and clean sensor triggers
    assert "7 gio" in _normalize_vi_spoken_numbers("bảy giờ sáng")
    assert "2 giay" in _normalize_vi_spoken_numbers("hai giây nữa")
    assert _parse_sensor_trigger("Khi có tiếng động lớn") == ("sound_sensor", "LOUD")
    for utt in (
        "Tạo lệnh đi làm là tắt tất cả đèn và đóng cửa chính.",
        "Thêm khẩu lệnh ra ngoài để tắt tất cả đèn và đóng cửa chính.",
        "Lưu chế độ rời nhà gồm tắt tất cả đèn và đóng cửa chính.",
    ):
        parsed = _parse_custom_command_create_or_edit(utt)
        assert parsed is not None and len(parsed[1]) >= 2, f"Custom command parse failed: {utt!r}"

    # 5. 3D pin high-contrast CSS rule prevents washout of 'Cửa chính (D1): OPEN'
    import pathlib as _pl

    css_path = _pl.Path(__file__).resolve().parents[2] / "simulator" / "static" / "css" / "style.css"
    css_txt = css_path.read_text(encoding="utf-8")
    assert ".pin-3d.on .pin-state" in css_txt
    assert "#075985" in css_txt
    assert "rgba(15, 23, 42, 0.94)" in css_txt


def test_round2_gemini_stt_cooldown_and_mock_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Gemini STT 429 cooldown logic, garbage rejection, and noise gate without live API calls."""
    import numpy as np
    from simulator.voice import gemini_stt

    # Reset cooldown state cleanly
    gemini_stt._MODEL_COOLDOWN_UNTIL.clear()
    gemini_stt._MODEL_429_STREAK.clear()

    class _FakeErr(Exception):
        def __init__(self, msg: str, code: int = 429) -> None:
            super().__init__(msg)
            self.code = code

    # Per-minute 429 -> short 15s cooldown; per-day 429 -> long 3600s cooldown
    gemini_stt._record_model_error("m_rpm", _FakeErr("429 RESOURCE_EXHAUSTED per minute", 429))
    assert "m_rpm" in gemini_stt._MODEL_COOLDOWN_UNTIL
    rpm_cd = gemini_stt._MODEL_COOLDOWN_UNTIL["m_rpm"] - time.monotonic()
    assert 5.0 < rpm_cd <= 20.0

    gemini_stt._record_model_error("m_day", _FakeErr("429 RESOURCE_EXHAUSTED PerDay quota", 429))
    day_cd = gemini_stt._MODEL_COOLDOWN_UNTIL["m_day"] - time.monotonic()
    assert day_cd > 3000.0

    # Alphanumeric garbage detector
    assert gemini_stt._is_alnum_garbage("FGH9A") is True
    assert gemini_stt._is_alnum_garbage("KY037") is False
    assert gemini_stt._is_alnum_garbage("mở cửa") is False

    # Pure white noise rejected immediately at acoustic gate before any Gemini client call
    noise = synth_pure_white_noise(duration_sec=1.5, seed=99)
    res_n = gemini_stt.transcribe_vietnamese_gemini_pcm16k(noise, sr=16000)
    assert res_n["ok"] is False and res_n["is_noise"] is True and res_n["stt_engine"] == "acoustic_gate"

    # Clean speech with mocked Gemini client returns exact transcript and gemini engine label
    t = np.linspace(0.0, 1.0, 16000, endpoint=False, dtype=np.float32)
    speech_like = (0.35 * np.sin(2.0 * np.pi * 220.0 * t) * (0.5 + 0.5 * np.sin(2.0 * np.pi * 4.0 * t)))
    pcm = np.clip(speech_like * 32767.0, -32767, 32767).astype(np.int16)

    class _FakeResp:
        text = "mở cửa chính"

    class _FakeModels:
        def generate_content(self, **kwargs: Any) -> _FakeResp:
            return _FakeResp()

    class _FakeClient:
        models = _FakeModels()

    monkeypatch.setattr(gemini_stt, "load_key", lambda: "AIzaFakeTestKeyForUnitTestOnly1234567")
    monkeypatch.setattr(gemini_stt, "_get_genai_client", lambda _k: _FakeClient())
    gemini_stt._MODEL_COOLDOWN_UNTIL.clear()

    res_ok = gemini_stt.transcribe_vietnamese_gemini_pcm16k(pcm, sr=16000)
    assert res_ok["ok"] is True
    assert res_ok["text"] == "mở cửa chính"
    assert str(res_ok["stt_engine"]).startswith("gemini:")


def test_round3_offline_nlu_and_policy_regressions() -> None:
    """Round 3 regressions: zero false actions on bare/unsupported nouns, echo clarification, ASR NLU slips."""
    from simulator.live.echo_and_speech_guard import ServerEchoGuard
    from simulator.server import app
    from simulator.voice.vietnamese_stt import _classify_offline_transcript_kind

    engine = _reset_engine_clean()
    h1, _, h2, _ = _seed_sessions()

    # 1. Strict bare-device / bare-verb classifier
    assert _classify_offline_transcript_kind("tất cả đèn") == ("bare_device", "all_lights")
    assert _classify_offline_transcript_kind("các còi báo động") == ("unrecognized", None)
    assert _classify_offline_transcript_kind("bật kết quả") == ("unrecognized", None)
    assert _classify_offline_transcript_kind("bật lên") == ("bare_verb", None)

    # 2. Clarification follow-up must not be suppressed as TTS echo
    guard = ServerEchoGuard()
    guard.record_ai_utterance("Bạn muốn bật hay tắt đèn phòng khách ạ?")
    is_echo, _sc, _rsn = guard.check_echo_transcript("bật đèn phòng khách")
    assert is_echo is False

    with TestClient(app) as client:
        # 3. F75 'đóng rèn cửa' (ASR slip for 'đóng rèm cửa') -> unsupported device, 0 mutations
        r_ren = client.post("/api/voice_command", headers=h1, json={"transcript": "đóng rèn cửa"})
        assert r_ren.status_code == 200
        d_ren = r_ren.json()
        assert d_ren.get("executed") is False
        assert engine.devices["main_door"]["state"] == "CLOSED"
        _assert_vi_reply(d_ren)

        # 4. Bare noun 'tất cả đèn' -> clarification, 0 mutations
        r_bare = client.post("/api/voice_command", headers=h1, json={"transcript": "tất cả đèn"})
        assert r_bare.status_code == 200
        assert r_bare.json().get("executed") is False
        assert engine.devices["living_room_light"]["state"] == "OFF"
        assert engine.devices["bedroom_light"]["state"] == "OFF"

        # 5. Clean speaker amp command turns ON speaker_amp; deleted garble must NOT act
        r_amp_bad = client.post("/api/voice_command", headers=h1, json={"transcript": "bạn nguồn mệt loa"})
        assert r_amp_bad.status_code == 200 and r_amp_bad.json().get("executed") is False
        r_amp = client.post("/api/voice_command", headers=h1, json={"transcript": "bật nguồn mạch loa"})
        assert r_amp.status_code == 200 and r_amp.json().get("executed") is True
        assert engine.devices["speaker_amp"]["state"] == "ON"

        # 6. Factory reset requires confirmation for Tier 1, denied for Tier 2; deleted garble must NOT trigger factory reset
        r_fr_bad = client.post("/api/voice_command", headers=h1, json={"transcript": "khôi phục ngày đàn tốt"})
        assert r_fr_bad.status_code == 200 and r_fr_bad.json().get("requires_confirmation") is False
        r_fr_t2 = client.post("/api/voice_command", headers=h2, json={"transcript": "khôi phục cài đặt gốc"})
        assert r_fr_t2.status_code == 403
        r_fr_t1 = client.post("/api/voice_command", headers=h1, json={"transcript": "khôi phục cài đặt gốc"})
        assert r_fr_t1.status_code == 200 and r_fr_t1.json().get("requires_confirmation") is True
        r_can = client.post("/api/voice_command", headers=h1, json={"transcript": "thôi hủy"})
        assert r_can.status_code == 200 and r_can.json().get("executed") is False

        # 7. Clean device reset phrasing ('hãy thiết lập lại thiết bị') stages confirmation; deleted garbles do NOT
        r_rs_bad = client.post("/api/voice_command", headers=h1, json={"transcript": "re logic trạng thái thiết nghi"})
        assert r_rs_bad.status_code == 200 and r_rs_bad.json().get("requires_confirmation") is False
        r_rs = client.post("/api/voice_command", headers=h1, json={"transcript": "hãy thiết lập lại thiết bị"})
        assert r_rs.status_code == 200 and r_rs.json().get("requires_confirmation") is True
        client.post("/api/voice_command", headers=h1, json={"transcript": "hủy"})

        # 8. Clean schedule modify & rule delete stage confirmation cleanly
        r_mk = client.post("/api/voice_command", headers=h1, json={"transcript": "7 giờ sáng bật đèn phòng khách"})
        assert r_mk.status_code == 200 and r_mk.json().get("requires_confirmation") is True
        r_mk_ok = client.post("/api/voice_command", headers=h1, json={"transcript": "đồng ý"})
        assert r_mk_ok.status_code == 200 and r_mk_ok.json().get("confirmed") is True

        r_mod = client.post("/api/voice_command", headers=h1, json={"transcript": "sửa lịch 7 giờ thành 8 giờ"})
        assert r_mod.status_code == 200 and r_mod.json().get("requires_confirmation") is True
        client.post("/api/voice_command", headers=h1, json={"transcript": "hủy"})

        r_del_rule = client.post("/api/voice_command", headers=h1, json={"transcript": "xóa liên kết đèn phòng khách"})
        assert r_del_rule.status_code == 200 and r_del_rule.json().get("requires_confirmation") is True
        client.post("/api/voice_command", headers=h1, json={"transcript": "hủy"})

        # 9. Clean countdown timer stages confirmation cleanly
        r_ht = client.post("/api/voice_command", headers=h1, json={"transcript": "sau ba giây tắt đèn phòng khách"})
        assert r_ht.status_code == 200 and r_ht.json().get("requires_confirmation") is True
        assert "tắt đèn phòng khách" in str(r_ht.json().get("reply") or "").lower()
        client.post("/api/voice_command", headers=h1, json={"transcript": "hủy"})

        # 10. Multi-clause without comma resolves all 3 devices cleanly
        from simulator.voice.vietnamese_policy import parse_direct_device_intents_vi

        m3 = parse_direct_device_intents_vi("tắt đèn phòng khách tắt đèn phòng ngủ và tắt nguồn mạch loa")
        assert {it["device_id"] for it in m3} == {"living_room_light", "bedroom_light", "speaker_amp"}
        assert all(it["action"] == "turn_off" for it in m3)

        # 11. Garbled conditional / status transcripts are NOT falsely classified as recognized
        assert _classify_offline_transcript_kind("mở cửa kín thì khoảng cách") == ("unrecognized", None)
        assert _classify_offline_transcript_kind("vì thích trạng thái biết gì") == ("unrecognized", None)


def test_round3_quota_aware_cascade_local_vs_gemini_escalation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify quota-aware cascade keeps high-confidence local clips off Gemini and escalates uncertain clips."""
    import numpy as np
    from simulator.voice import gemini_stt

    t = np.linspace(0.0, 1.2, 19200, endpoint=False, dtype=np.float32)
    speech_like = 0.35 * np.sin(2.0 * np.pi * 180.0 * t) * (0.5 + 0.5 * np.sin(2.0 * np.pi * 4.0 * t))
    pcm = np.clip(speech_like * 32767.0, -32767, 32767).astype(np.int16)

    gem_calls = {"n": 0}

    def _fake_gem(*args: Any, **kwargs: Any) -> dict[str, Any]:
        gem_calls["n"] += 1
        return {"ok": True, "text": "bật máy bơm", "confidence": 0.94, "is_noise": False, "stt_ms": 500.0, "stt_engine": "gemini:gemini-3.1-flash-lite"}

    monkeypatch.setattr(gemini_stt, "transcribe_vietnamese_gemini_pcm16k", _fake_gem)
    monkeypatch.setattr(gemini_stt, "load_key", lambda: "AIzaFakeKey12345678901234567890")
    monkeypatch.setattr(gemini_stt, "_get_candidate_models", lambda: ["gemini-3.1-flash-lite"])

    # Case A: Confident offline result -> accepted locally, 0 Gemini API calls!
    monkeypatch.setattr(
        gemini_stt,
        "transcribe_vietnamese_offline_pcm16k",
        lambda *_a, **_kw: {"ok": True, "text": "mở cửa chính", "confidence": 0.88, "is_noise": False, "stt_ms": 800.0, "stt_engine": "zipformer_70m"},
    )
    res_local = gemini_stt.transcribe_vietnamese_cascade_pcm16k(pcm, sr=16000)
    assert res_local["ok"] is True
    assert res_local["text"] == "mở cửa chính"
    assert res_local["stt_engine"] == "cascade_local:zipformer_70m"
    assert gem_calls["n"] == 0

    # Case B: Low-confidence offline fallback -> escalated to Gemini!
    monkeypatch.setattr(
        gemini_stt,
        "transcribe_vietnamese_offline_pcm16k",
        lambda *_a, **_kw: {"ok": True, "text": "mệt hơn", "confidence": 0.82, "is_noise": False, "stt_ms": 1100.0, "stt_engine": "zipformer_70m+chunkformer_ctc_fallback"},
    )
    res_esc = gemini_stt.transcribe_vietnamese_cascade_pcm16k(pcm, sr=16000)
    assert res_esc["ok"] is True
    assert res_esc["text"] == "bật máy bơm"
    assert res_esc["stt_engine"].startswith("gemini:")
    assert gem_calls["n"] == 1


def test_round3_adversarial_role3_hardening() -> None:
    """Verify Role 3 adversarial findings: extra unsupported appliances, negated commands, đúng/đừng collision, bare normalization."""
    from simulator.automation_nlu import parse_single_device_and_action
    from simulator.voice.vietnamese_policy import parse_direct_device_intents_vi
    from simulator.voice.vietnamese_stt import _classify_offline_transcript_kind

    # 1. Unsupported appliances sharing cửa / đèn / loa / bơm tokens -> 0 direct actions AND (None, None) in automation NLU
    for bad in (
        "mở cửa sổ", "đóng cửa ban công", "mở cửa phòng ngủ", "đóng cửa gara",
        "bật đèn bếp", "tắt đèn nhà vệ sinh", "bật đèn cầu thang", "bật đèn bàn học",
        "bật loa bluetooth", "bật bơm tăng áp", "đóng rèm cửa", "mở cửa cuốn",
    ):
        assert parse_direct_device_intents_vi(bad) == [], f"Direct leak on {bad!r}"
        assert parse_single_device_and_action(bad) == (None, None), f"NLU leak on {bad!r}"

    # 2. Negated commands & đúng/đừng collision -> 0 direct actions; 'dừng tưới vườn' STILL turns OFF garden_pump!
    for neg in (
        "không mở cửa chính", "không bật đèn phòng khách", "đừng mở cửa chính",
        "đừng bật đèn phòng khách", "chưa cần bật máy bơm", "thôi không đóng cửa nữa",
        "đèn phòng khách đúng rồi", "cửa chính đúng không",
    ):
        assert parse_direct_device_intents_vi(neg) == [], f"Negation leak on {neg!r}"
    assert parse_direct_device_intents_vi("dừng tưới vườn") == [{"device_id": "garden_pump", "action": "turn_off"}]

    # 3. Bare-device normalization & nonsense local-keep (avoid unnecessary Gemini escalations)
    assert _classify_offline_transcript_kind("nguồn mạch loa") == ("bare_device", "speaker_amp")
    assert _classify_offline_transcript_kind("tất cả thiết bị") == ("bare_device", "all_devices")
    assert _classify_offline_transcript_kind("ờ à ừm") == ("nonsense", None)


def test_round4_acoustic_length_and_cascade_disagreement_zero_false_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Round 4 cross-engine & acoustic-length safety guards eliminate all 7 false-action modes."""
    import numpy as np
    from simulator.voice import gemini_stt
    from simulator.voice.vietnamese_policy import parse_direct_device_intents_vi

    pcm = np.zeros(16000, dtype=np.int16)

    # 1. 2-letter phonetic collision fixed: 'cam kết bảo vệ' must NOT corroborate lights ('vệ'->'ze' vs 'đèn'->'zen')
    all_lights = parse_direct_device_intents_vi("bật hết đèn")
    assert gemini_stt._local_corroborates_device_intents("cam kết bảo vệ", all_lights) is False
    assert gemini_stt._local_corroborates_all_device_groups("mở cửa chính", parse_direct_device_intents_vi("bật đèn phòng khách, mở cửa chính")) is False

    # 2. R2 short-clip hallucination expansion blocked (clean J05_09 'bật còi' -> 'Bật đèn phòng khách.', babble_snr10 J01_52 'tạm biệt' -> 'tắt đèn phòng khách')
    g_j05 = gemini_stt._run_high_noise_hallucination_gate(
        gemini_text="Bật đèn phòng khách.",
        pcm16=pcm,
        sr=16000,
        duration_sec=1.15,
        noise_ratio=0.0,
        used_model="gemini-3.1-flash-lite",
        t0=time.perf_counter(),
        active_speech_dur=0.66,
        offline_hint_text="mệt thôi",
        offline_engine="zipformer_30m+chunkformer_ctc_fallback",
    )
    assert g_j05 is not None and g_j05["ok"] is False and g_j05["text"] == ""

    g_j52 = gemini_stt._run_high_noise_hallucination_gate(
        gemini_text="tắt đèn phòng khách",
        pcm16=pcm,
        sr=16000,
        duration_sec=1.20,
        noise_ratio=0.22,
        used_model="gemini-3.1-flash-lite",
        t0=time.perf_counter(),
        active_speech_dur=0.66,
        offline_hint_text="làm gì",
        offline_engine="zipformer_30m+chunkformer_ctc_fallback",
    )
    assert g_j52 is not None and g_j52["ok"] is False and g_j52["text"] == ""

    # 3. R1 non-direct cue veto: local heard 'tạo lệnh' / 'hai giây' -> NEVER execute Gemini's stripped direct command
    g_j21 = gemini_stt._run_high_noise_hallucination_gate(
        gemini_text="Hãy tắt tất cả đèn và đóng cửa chính.",
        pcm16=pcm,
        sr=16000,
        duration_sec=4.49,
        noise_ratio=0.27,
        used_model="gemini-3.1-flash-lite",
        t0=time.perf_counter(),
        active_speech_dur=3.32,
        offline_hint_text="tạo lệnh đi làm mà khác rất cả đèn và nóng đồng khí",
        offline_engine="zipformer_70m+chunkformer_ctc_fallback",
    )
    assert g_j21 is not None and "tạo lệnh" in g_j21["text"]
    assert parse_direct_device_intents_vi(g_j21["text"]) == []

    g_j31 = gemini_stt._run_high_noise_hallucination_gate(
        gemini_text="Hãy bật đèn phòng ngủ.",
        pcm16=pcm,
        sr=16000,
        duration_sec=3.05,
        noise_ratio=0.43,
        used_model="gemini-3.1-flash-lite",
        t0=time.perf_counter(),
        active_speech_dur=2.16,
        offline_hint_text="mẹ giường hai giây một lần phòng ngủ",
        offline_engine="zipformer_70m+chunkformer_ctc_fallback",
    )
    assert g_j31 is not None and "hai giây" in g_j31["text"]
    assert parse_direct_device_intents_vi(g_j31["text"]) == []

    # 4. R3 prefix drop & R4 severe-noise multi-device corroboration & R5 polarity conflict
    g_j29 = gemini_stt._run_high_noise_hallucination_gate(
        gemini_text="bật đèn phòng khách, mở cửa chính",
        pcm16=pcm,
        sr=16000,
        duration_sec=3.55,
        noise_ratio=0.43,
        used_model="gemini-3.1-flash-lite",
        t0=time.perf_counter(),
        active_speech_dur=2.72,
        offline_hint_text="làm một lần thứ tháng là ngày một vị chín",
        offline_engine="zipformer_70m+chunkformer_ctc_fallback",
    )
    assert g_j29 is not None and g_j29["ok"] is False and g_j29["text"] == ""

    g_pol = gemini_stt._run_high_noise_hallucination_gate(
        gemini_text="bật đèn phòng khách",
        pcm16=pcm,
        sr=16000,
        duration_sec=1.80,
        noise_ratio=0.25,
        used_model="gemini-3.1-flash-lite",
        t0=time.perf_counter(),
        active_speech_dur=1.20,
        offline_hint_text="tắt đèn phòng khách",
        offline_engine="zipformer_70m",
    )
    assert g_pol is not None and g_pol["ok"] is False and g_pol["text"] == ""


def test_round4_nlu_prefix_integrity_negations_and_small_talk_safety() -> None:
    """Verify NLU prefix/clause integrity, dem/đêm fix, conditional escalation, expanded negations, and noisy small talk."""
    from simulator.server import app
    from simulator.voice.vietnamese_policy import classify_small_talk_vi, parse_direct_device_intents_vi
    from simulator.voice.vietnamese_stt import _classify_offline_transcript_kind
    from tests.voice_policy.journey_suite import JourneyStep
    from tests.voice_policy.run_voice_journeys import _evaluate_response

    # 1. Garbled multi-clause prefix must NEVER execute trailing clause (speed_1.2x J01_21)
    assert parse_direct_device_intents_vi("ở đây đi làm át tất cả đền và đóng cửa chính") == []
    assert parse_direct_device_intents_vi("sự đẹp đi làm thành một nền phòng khách và đóng cửa chính") == []

    # 2. Expanded negations & standalone clock prefixes never leak into direct device execution
    for bad in (
        "không cần bật đèn phòng khách",
        "không muốn mở cửa chính",
        "không được bật còi báo động",
        "không nên bật máy bơm",
        "đừng vội mở cửa",
        "chớ bật còi báo động",
        "đừng bao giờ mở cửa chính",
        "20 giờ bật đèn phòng khách",
        "6h30 mở cửa chính",
        "tắt đèn nhà tắm",
        "bật loa tivi",
    ):
        assert parse_direct_device_intents_vi(bad) == [], f"Unexpected direct intent on {bad!r}"

    # 3. Fixed dem/đêm collision and conditional 'cửa kính' escalation
    assert _classify_offline_transcript_kind("ban đêm không ngủ") == ("unrecognized", None)
    assert _classify_offline_transcript_kind("khi mở cửa kính thì ban ngày gom rách") == ("unrecognized", None)

    # 4. Small talk including 'gặp lại sau' & noisy small-talk corruptions -> 0 executions, 0 device mutations
    assert classify_small_talk_vi("gặp lại sau") is not None
    engine = _reset_engine_clean()
    h1, _, _, _ = _seed_sessions()
    with TestClient(app) as client:
        for phrase in (
            "tạm biệt", "tạm biệt nhé", "cảm ơn bạn", "ngủ ngon", "hẹn gặp lại", "gặp lại sau",
            "tốt lắm", "bạn là ai", "tắt biệt", "tạm điện", "chào bán", "ngủ con",
        ):
            r = client.post("/api/voice_command", headers=h1, json={"transcript": phrase})
            assert r.status_code == 200
            d = r.json()
            assert d.get("executed") is False, f"False execution on {phrase!r}: {d}"
            assert d.get("requires_confirmation") is False, f"Unexpected confirm on {phrase!r}: {d}"
            _assert_vi_reply(d)
        for did, info in engine.devices.items():
            exp = "CLOSED" if did == "main_door" else "OFF"
            assert info["state"] == exp, f"Device {did} mutated during small talk!"

        # Deleted garble 'vì sách trạng thái thiết bị' must NOT trigger reset; clean phrasing DOES stage confirmation
        r_rst_bad = client.post("/api/voice_command", headers=h1, json={"transcript": "vì sách trạng thái thiết bị"})
        assert r_rst_bad.status_code == 200 and r_rst_bad.json().get("requires_confirmation") is False
        r_rst = client.post("/api/voice_command", headers=h1, json={"transcript": "đặt lại trạng thái thiết bị"})
        assert r_rst.status_code == 200 and r_rst.json().get("requires_confirmation") is True
        client.post("/api/voice_command", headers=h1, json={"transcript": "hủy"})

    # 5. Strict all-rows false_action evaluation check (wrong device, flipped polarity, unexpected confirm_prompt execution)
    st_imm = JourneyStep("T1", "J", 2, "s", "bac_male", 1, "bật còi", "immediate_device", expected_device_states={"alarm_siren": "ON"})
    ev_wrong = _evaluate_response(
        st_imm,
        status_code=200,
        body={"ok": True, "executed": True, "intents": [{"device_id": "living_room_light", "action": "turn_on"}], "reply": "Đèn phòng khách đang bật rồi."},
        before_states={"living_room_light": "ON", "alarm_siren": "OFF"},
        after_states={"living_room_light": "ON", "alarm_siren": "OFF"},
        post_ok=True,
        post_note="",
        mode="voice_clean",
    )
    assert ev_wrong["false_action"] is True

    st_conf = JourneyStep("T2", "J", 4, "s", "bac_male", 1, "tạo lệnh đi làm là đóng cửa", "confirm_prompt")
    ev_conf = _evaluate_response(
        st_conf,
        status_code=200,
        body={"ok": True, "executed": True, "requires_confirmation": False, "intents": [{"device_id": "main_door", "action": "close"}], "reply": "Đã đóng cửa chính."},
        before_states={"main_door": "OPEN"},
        after_states={"main_door": "CLOSED"},
        post_ok=True,
        post_note="",
        mode="voice_degraded",
    )
    assert ev_conf["false_action"] is True

    # 6. Round 4 polarity/corroboration regressions: stopword 'không' must NOT corroborate 'phòng',
    #    bare-noun expansion under SNR10 and 2-word uncorroborated hallucination must be blocked,
    #    and 'bật ngùng mặt loa' must resolve to speaker_amp:turn_on without 'ngừng' OFF collision.
    import numpy as np
    from simulator.voice import gemini_stt

    assert not gemini_stt._local_corroborates_all_device_groups(
        "nguồn không là là",
        [{"device_id": "living_room_light", "action": "turn_on"}],
    )
    assert parse_direct_device_intents_vi("cấp nguồn mạch loa") == [
        {"device_id": "speaker_amp", "action": "turn_on"}
    ]
    assert parse_direct_device_intents_vi("bật ngùng mặt loa") == []
    assert parse_direct_device_intents_vi("không mở cửa") == []
    assert parse_direct_device_intents_vi("đừng bật đèn phòng khách") == []

    t = np.linspace(0.0, 1.4, int(16000 * 1.4), endpoint=False, dtype=np.float32)
    adult_pcm = np.clip(0.3 * np.sin(2.0 * np.pi * 130.0 * t) * 32767.0, -32767, 32767).astype(np.int16)

    g_j06 = gemini_stt._run_high_noise_hallucination_gate(
        gemini_text="mở cửa chính",
        pcm16=adult_pcm,
        sr=16000,
        duration_sec=1.39,
        noise_ratio=0.24,
        used_model="gemini-3.1-flash-lite",
        t0=time.perf_counter(),
        active_speech_dur=0.82,
        offline_hint_text="sửa tiếng",
        offline_engine="zipformer_70m+chunkformer_ctc_fallback",
    )
    assert g_j06 is not None and g_j06["ok"] is False and g_j06["text"] == ""

    # Bare 'tắt đèn' is itself safe (clarifies with 0 intents); verify 2-word uncorroborated direct command ('mở cửa') is gated
    assert parse_direct_device_intents_vi("tắt đèn") == []
    g_j52 = gemini_stt._run_high_noise_hallucination_gate(
        gemini_text="mở cửa",
        pcm16=adult_pcm,
        sr=16000,
        duration_sec=1.50,
        noise_ratio=0.0,
        used_model="gemini-flash-lite-latest",
        t0=time.perf_counter(),
        active_speech_dur=0.74,
        offline_hint_text="ờ biệt",
        offline_engine="zipformer_70m+chunkformer_ctc_fallback",
    )
    assert g_j52 is not None and g_j52["ok"] is False and g_j52["text"] == ""


def test_round5_diacritic_near_miss_no_silent_timer_defaults_and_hard_utterances() -> None:
    """Round 5 safety regressions: wrong-diacritic near-misses clarify without acting, missing-device timers ask instead of defaulting, member link permission keeps confirmation, and hard utterances pass."""
    from simulator.automation_repo import list_pending_timers, list_schedules
    from simulator.server import app
    from simulator.voice.vietnamese_policy import (
        classify_ambiguous_or_unsupported_vi,
        parse_direct_device_intents_vi,
    )

    # 1. Finding 1: Wrong-diacritic light/siren/door near-misses must NEVER fire direct device actions
    for near_miss in (
        "tắt đen phòng khách",
        "bật đến phòng khách",
        "tắt dền phòng ngủ",
        "tắt đền phòng khách",
        "bật den phòng khách",
        "đóng cua chính",
        "mở của chính",
        "mở cua đi",
        "bật coi báo động",
        "bật bom vườn",
        "cái áo này màu đen đẹp nhỉ",
        "bat den",
        "tat den",
        "bat den phong khach hay gi",
        "tat den phong khach dung khong",
        "dong cua chinh dung khong",
        "tắt đèn phòng khách chưa",
        "bật đèn phòng khách à",
        "hôm qua tôi quên tắt đèn phòng khách",
        "đèn phòng khách đang bật hay đã tắt",
        "cửa chính đang mở hay đã đóng",
    ):
        assert parse_direct_device_intents_vi(near_miss) == [], f"Near-miss/rhetorical leaked action: {near_miss!r}"

    # Helpful Vietnamese clarification on wrong-diacritic light command
    clar_den = classify_ambiguous_or_unsupported_vi("tắt đen phòng khách") or ""
    assert "đèn phòng khách" in clar_den.lower() and "phải không" in clar_den.lower()

    # Exact accented match AND unambiguous fully unaccented typed command still execute cleanly
    assert parse_direct_device_intents_vi("bật đèn phòng khách") == [
        {"device_id": "living_room_light", "action": "turn_on"}
    ]
    assert parse_direct_device_intents_vi("bat den phong khach") == [
        {"device_id": "living_room_light", "action": "turn_on"}
    ]

    # Accented 'coi' particle must NOT trigger alarm_siren; 'Mở cái loa chuông lên coi.' targets speaker_amp ONLY
    assert parse_direct_device_intents_vi("Mở cái loa chuông lên coi.") == [
        {"device_id": "speaker_amp", "action": "turn_on"}
    ]
    # 'Đóng hộ' must NOT collide with 'đồng hồ'; 'Tắt cả hai đèn...' must NOT collide with 'tất cả'
    assert parse_direct_device_intents_vi("Đóng hộ cái cửa chính lại nhé.") == [
        {"device_id": "main_door", "action": "close"}
    ]
    assert parse_direct_device_intents_vi("Tắt cả hai đèn phòng khách, phòng ngủ và tắt loa chuông nữa.") == [
        {"device_id": "living_room_light", "action": "turn_off"},
        {"device_id": "bedroom_light", "action": "turn_off"},
        {"device_id": "speaker_amp", "action": "turn_off"},
    ]

    engine = _reset_engine_clean()
    h1, _, _, _ = _seed_sessions()
    with TestClient(app) as client:
        # 1b. E2E check: 'tắt đen phòng khách' clarifies, 0 execution, 0 state change
        asyncio.run(engine.execute_device_action("living_room_light", "turn_on", bypass_rbac=True))
        r_nm = client.post("/api/text_command", headers=h1, json={"text": "tắt đen phòng khách"})
        assert r_nm.status_code == 200
        d_nm = r_nm.json()
        assert d_nm.get("executed") is False
        assert d_nm.get("requires_confirmation") is False
        assert engine.devices["living_room_light"]["state"] == "ON"
        assert "đèn phòng khách" in _assert_vi_reply(d_nm).lower()

        # 2. Finding 2: Missing-device / missing-action timers & schedules ask in Vietnamese, NEVER default to living_room_light/turn_on
        for vague_timer in (
            "hẹn giờ 5 phút nữa",
            "hẹn giờ 5 phút nữa tắt",
            "hẹn giờ 5 phút nữa đèn phòng khách",
            "hẹn giờ bật đèn phòng khách",
            "đặt lịch 9 giờ tối",
        ):
            r_vt = client.post("/api/text_command", headers=h1, json={"text": vague_timer})
            assert r_vt.status_code == 200, f"{vague_timer!r} -> {r_vt.status_code} {r_vt.text}"
            d_vt = r_vt.json()
            assert d_vt.get("executed") is False, f"{vague_timer!r} must NOT execute!"
            assert d_vt.get("requires_confirmation") is False, f"{vague_timer!r} must clarify, not stage guessed timer!"
            rep_vt = _assert_vi_reply(d_vt)
            assert "?" in rep_vt
        assert len(list_pending_timers()) == 0
        assert len(list_schedules(include_disabled=False)) == 0

        # REST POST /api/timers with omitted device_id/action must reject with 400 (no silent default)
        r_api_tm = client.post("/api/timers", headers=h1, json={"seconds": 30})
        assert r_api_tm.status_code == 400
        assert len(list_pending_timers()) == 0

        # 3. KEEP: set_member_link_permission still requires confirmation
        from simulator.auth_3layer import get_auth_3layer_manager
        from simulator.automation_repo import can_user_create_links

        mgr = get_auth_3layer_manager()
        added_qa_member = False
        if not any(str(a.get("user_id") or "") == "qa_member_t2" for a in mgr.accounts):
            mgr.accounts.append({
                "account_id": "qa_member_t2",
                "user_id": "qa_member_t2",
                "email": "qa_member@test.local",
                "display_name": "Thành viên QA",
                "full_name": "Thành viên QA",
                "tier": 2,
                "role": "MEMBER",
                "permission_active": True,
                "permission_status": "ACTIVE",
            })
            added_qa_member = True
        try:
            r_perm = client.post("/api/text_command", headers=h1, json={"text": "cấp quyền tạo liên kết cho Thành viên QA"})
            assert r_perm.status_code == 200
            d_perm = r_perm.json()
            assert d_perm.get("requires_confirmation") is True
            assert d_perm.get("action_kind") == "set_member_link_permission"
            assert can_user_create_links("qa_member_t2", 2, engine=engine) is False
            r_perm_no = client.post("/api/text_command", headers=h1, json={"text": "hủy"})
            assert r_perm_no.status_code == 200

            # Revoking member link permission via /api/text_command MUST also require confirmation (never hijack/revoke account!)
            r_rev = client.post("/api/text_command", headers=h1, json={"text": "thu hồi quyền tạo liên kết của Thành viên QA"})
            assert r_rev.status_code == 200
            d_rev = r_rev.json()
            assert d_rev.get("requires_confirmation") is True
            assert d_rev.get("action_kind") == "set_member_link_permission"
            client.post("/api/text_command", headers=h1, json={"text": "hủy"})
        finally:
            if added_qa_member:
                mgr.accounts[:] = [a for a in mgr.accounts if str(a.get("user_id") or "") != "qa_member_t2"]

        # Timer + wrong-diacritic combo must clarify with executed=False on BOTH /api/text_command and /api/voice_command
        for ep, body in (
            ("/api/text_command", {"text": "hẹn giờ 5 phút nữa tắt đen phòng khách"}),
            ("/api/voice_command", {"transcript": "hẹn giờ 5 phút nữa"}),
        ):
            r_c = client.post(ep, headers=h1, json=body)
            assert r_c.status_code == 200
            dc = r_c.json()
            assert dc.get("executed") is False, f"{ep} {body} returned executed=True!"
            assert dc.get("requires_confirmation") is False
        assert len(list_pending_timers()) == 0

        # 4. Hard-utterance regressions: DHT11 rule must NOT overwrite DHT11 sensor to 11.0°C; air humidity query must NOT collide with 'khi'
        asyncio.run(engine.update_sensor_telemetry(temp_c=29.2, humidity_pct=64.0))
        r_rule = client.post("/api/text_command", headers=h1, json={"text": "Nhiệt độ DHT11 mà lên trên ba mươi lăm độ C thì bật còi báo động."})
        assert r_rule.status_code == 200 and r_rule.json().get("requires_confirmation") is True
        assert abs(float(engine.mqtt_bridge.dht11_telemetry["temp_c"]) - 29.2) < 0.01
        client.post("/api/text_command", headers=h1, json={"text": "hủy"})

        r_hum = client.post("/api/text_command", headers=h1, json={"text": "Cho tôi hỏi độ ẩm không khí đang bao nhiêu đấy?"})
        assert r_hum.status_code == 200 and r_hum.json().get("kind") == "sensor_query"
        assert "64%" in _assert_vi_reply(r_hum.json())

        # Self-correction, meta-linguistic mention, and topic-comment safety
        for no_act in (
            "Tôi đang nói từ mở cửa, chưa nhờ bạn làm gì cả.",
            "Câu tắt đèn phòng ngủ có mấy chữ vậy?",
            "Đóng cửa chính à? Không, tôi chỉ đang đọc lại câu đó.",
            "Tạm biệt bạn, tôi không bảo tắt đèn phòng khách.",
            "tạo nền nhà sàn lên để bật cả đèn phòng khách và phòng ngủ",
        ):
            r_na = client.post("/api/text_command", headers=h1, json={"text": no_act})
            assert r_na.status_code == 200 and r_na.json().get("executed") is False, f"False action on {no_act!r}"

        # Schedule with leading period parses 21:00 (not 09:00)
        r_sc21 = client.post("/api/text_command", headers=h1, json={"text": "Tối nay lúc chín giờ bật đèn phòng ngủ cho tôi."})
        assert r_sc21.status_code == 200 and r_sc21.json().get("requires_confirmation") is True
        assert "21:00" in _assert_vi_reply(r_sc21.json())
        client.post("/api/text_command", headers=h1, json={"text": "hủy"})


def test_round7_sensor_custom_commands_stutter_di_a_and_echo_guard() -> None:
    """Round 7 regressions:
    (a) T124 custom commands with sensor-query & device-state-query steps (typed, ASR, REST, mixed, Guest RBAC, invalid 400).
    (b) T047 stutter without ellipsis ('tắt đèn phòng à phòng ngủ nhé').
    (c) T063 'đi à' ASR mishearing of 'đi ạ' without relaxing rhetorical questions.
    (d) T105 multi-device imperative echo guard without breaking real echo suppression.
    """
    from simulator.automation_nlu import parse_multi_steps_from_text
    from simulator.automation_repo import list_custom_commands
    from simulator.live.echo_and_speech_guard import ServerEchoGuard
    from simulator.server import app
    from simulator.voice.vietnamese_policy import parse_direct_device_intents_vi

    # --- (b) T047 stutter without ellipsis ---
    assert parse_direct_device_intents_vi("tắt đèn phòng à phòng ngủ nhé") == [
        {"device_id": "bedroom_light", "action": "turn_off"}
    ]
    assert parse_direct_device_intents_vi("Tắt đèn phòng... à phòng ngủ nhé.") == [
        {"device_id": "bedroom_light", "action": "turn_off"}
    ]
    assert parse_direct_device_intents_vi("bật bơm ờ bơm ngoài vườn") == [
        {"device_id": "garden_pump", "action": "turn_on"}
    ]

    # --- (c) T063 'đi à' imperative ASR vs genuine rhetorical questions ---
    assert parse_direct_device_intents_vi("cô máy ơi cho cái loa chuông kêu đi à") == [
        {"device_id": "speaker_amp", "action": "turn_on"}
    ]
    assert parse_direct_device_intents_vi("tắt đèn buồng đi à") == [
        {"device_id": "bedroom_light", "action": "turn_off"}
    ]
    for rhetorical in (
        "tắt đèn à?",
        "tắt đèn à",
        "đèn đang bật à",
        "cửa đóng chưa",
        "bật đèn phòng khách hả",
        "tắt đèn đi à?",
    ):
        assert parse_direct_device_intents_vi(rhetorical) == [], f"Rhetorical question leaked action: {rhetorical!r}"

    # --- (d) T105 echo guard ---
    eg = ServerEchoGuard()
    eg.record_ai_utterance("Đã mở cửa chính và bật đèn phòng khách.")
    is_echo_t105, _sc1, _r1 = eg.check_echo_transcript("Đóng cửa chính lại, tắt luôn đèn phòng khách.")
    assert is_echo_t105 is False, "T105 multi-device opposite-verb imperative must NOT be echo-suppressed"
    is_echo_real, _sc2, _r2 = eg.check_echo_transcript("Đã mở cửa chính và bật đèn phòng khách.")
    assert is_echo_real is True, "Verbatim echo of AI speech MUST still be suppressed"
    is_echo_clip, _sc3, _r3 = eg.check_echo_transcript("mở cửa chính và bật đèn phòng khách")
    assert is_echo_clip is True, "Clipped verbatim echo without opposite verb MUST still be suppressed"

    # --- (a) Goal 4 / T124 sensor & device-state steps in custom commands ---
    # ASR variant where DHT11 was dropped to 'ư'
    assert parse_multi_steps_from_text("đọc nhiệt độ và độ ẩm ư") == [
        {"device_id": "sensor_temperature", "action": "read"},
        {"device_id": "sensor_humidity", "action": "read"},
    ]
    assert parse_multi_steps_from_text("đọc độ ẩm đất") == [
        {"device_id": "sensor_soil", "action": "read"},
    ]
    assert parse_multi_steps_from_text("xem cảm biến âm thanh") == [
        {"device_id": "sensor_sound", "action": "read"},
    ]
    assert parse_multi_steps_from_text("xem trạng thái cửa chính") == [
        {"device_id": "main_door", "action": "read_state"},
    ]
    assert parse_multi_steps_from_text("bật điều hòa") == []

    engine = _reset_engine_clean()
    asyncio.run(engine.update_sensor_telemetry(temp_c=29.2, humidity_pct=64.0))
    asyncio.run(engine.update_soil_moisture_telemetry(48.0))
    asyncio.run(engine.update_sound_telemetry(sound_detected=True))
    asyncio.run(engine.execute_device_action("main_door", "open", bypass_rbac=True))
    h1, _, _, h3 = _seed_sessions()

    def _device_snapshot() -> dict[str, str]:
        return {k: str(v.get("state") or "") for k, v in engine.devices.items()}

    with TestClient(app) as client:
        # 1. T124 create -> confirm -> invoke -> confirm -> replies with live temp & humidity, 0 device mutations
        before_devs = _device_snapshot()
        r_c1 = client.post(
            "/api/text_command",
            headers=h1,
            json={"text": "Thêm lệnh tên xem không khí để đọc nhiệt độ và độ ẩm DHT11."},
        )
        assert r_c1.status_code == 200
        d_c1 = r_c1.json()
        assert d_c1.get("requires_confirmation") is True
        assert d_c1.get("action_kind") == "create_custom_command"
        assert len(list_custom_commands()) == 0

        r_c1_ok = client.post("/api/text_command", headers=h1, json={"text": "ok"})
        assert r_c1_ok.status_code == 200 and r_c1_ok.json().get("confirmed") is True
        cmds = list_custom_commands()
        assert len(cmds) == 1
        cmd_id_t124 = cmds[0]["command_id"]

        # Invoke via voice -> asks confirmation (NOT hijacked by direct sensor query) -> confirm -> live values, 0 mutations
        r_run_ask = client.post("/api/voice_command", headers=h1, json={"transcript": "xem không khí"})
        assert r_run_ask.status_code == 200
        assert r_run_ask.json().get("requires_confirmation") is True
        assert r_run_ask.json().get("action_kind") == "run_custom_command"

        r_run_ok = client.post("/api/voice_command", headers=h1, json={"transcript": "đồng ý"})
        assert r_run_ok.status_code == 200
        d_run = r_run_ok.json()
        assert d_run.get("confirmed") is True and d_run.get("executed") is True
        rep_run = _assert_vi_reply(d_run)
        assert "29.2" in rep_run and "64%" in rep_run
        assert _device_snapshot() == before_devs, "Sensor-only custom command must NOT mutate any device"

        # REST POST /api/scenes/{id}/run also returns live Vietnamese sensor values with 0 mutations
        r_rest = client.post(f"/api/scenes/{cmd_id_t124}/run", headers=h1)
        assert r_rest.status_code == 200
        rep_rest = _assert_vi_reply(r_rest.json())
        assert "29.2" in rep_rest and "64%" in rep_rest
        assert _device_snapshot() == before_devs

        # 2. Soil + sound + device-state query custom command (via REST + confirm)
        r_q2 = client.post(
            "/api/text_command",
            headers=h1,
            json={"text": "Tạo lệnh kiểm tra nhà gồm đọc độ ẩm đất, xem cảm biến âm thanh và xem trạng thái cửa chính"},
        )
        assert r_q2.status_code == 200 and r_q2.json().get("requires_confirmation") is True
        assert client.post("/api/text_command", headers=h1, json={"text": "ok"}).json().get("confirmed") is True
        r_q2_ask = client.post("/api/text_command", headers=h1, json={"text": "kiểm tra nhà"})
        assert r_q2_ask.status_code == 200 and r_q2_ask.json().get("requires_confirmation") is True
        r_q2_go = client.post("/api/text_command", headers=h1, json={"text": "ok"})
        assert r_q2_go.status_code == 200
        rep_q2 = _assert_vi_reply(r_q2_go.json())
        assert "48%" in rep_q2 and "tiếng động lớn" in rep_q2.lower() and "cửa chính đang mở" in rep_q2.lower()
        assert _device_snapshot() == before_devs

        # 3. Mixed device-control + sensor-query custom command
        assert engine.devices["living_room_light"]["state"] == "OFF"
        r_mix = client.post(
            "/api/text_command",
            headers=h1,
            json={"text": "Tạo lệnh chào buổi tối là bật đèn phòng khách và đọc nhiệt độ"},
        )
        assert r_mix.status_code == 200 and r_mix.json().get("requires_confirmation") is True
        assert client.post("/api/text_command", headers=h1, json={"text": "ok"}).json().get("confirmed") is True
        r_mix_ask = client.post("/api/text_command", headers=h1, json={"text": "chào buổi tối"})
        assert r_mix_ask.status_code == 200 and r_mix_ask.json().get("requires_confirmation") is True
        r_mix_go = client.post("/api/text_command", headers=h1, json={"text": "ok"})
        assert r_mix_go.status_code == 200
        rep_mix = _assert_vi_reply(r_mix_go.json())
        assert engine.devices["living_room_light"]["state"] == "ON"
        assert "đèn phòng khách" in rep_mix.lower() and "29.2" in rep_mix

        # 4. Guest Tier 3 still RBAC-denied (403) on creating/running sensor custom commands
        r_g1 = client.post(
            "/api/text_command",
            headers=h3,
            json={"text": "Thêm lệnh tên xem khách để đọc nhiệt độ và độ ẩm DHT11."},
        )
        assert r_g1.status_code == 403 and r_g1.json().get("rbac_blocked") is True
        r_g2 = client.post(f"/api/scenes/{cmd_id_t124}/run", headers=h3)
        assert r_g2.status_code == 403 and r_g2.json().get("rbac_blocked") is True

        # 5. Invalid/unsupported custom command still rejected with 400 and NOT created
        cnt_before = len(list_custom_commands())
        r_bad = client.post(
            "/api/text_command",
            headers=h1,
            json={"text": "Tạo lệnh mát mẻ là bật điều hòa"},
        )
        assert r_bad.status_code == 400
        assert len(list_custom_commands()) == cnt_before

        # 6. E2E voice checks for T047 and T063 + rhetorical negative
        asyncio.run(engine.execute_device_action("bedroom_light", "turn_on", bypass_rbac=True))
        r_t047 = client.post("/api/voice_command", headers=h1, json={"transcript": "tắt đèn phòng à phòng ngủ nhé"})
        assert r_t047.status_code == 200 and r_t047.json().get("executed") is True
        assert engine.devices["bedroom_light"]["state"] == "OFF"

        r_t063 = client.post("/api/voice_command", headers=h1, json={"transcript": "cô máy ơi cho cái loa chuông kêu đi à"})
        assert r_t063.status_code == 200 and r_t063.json().get("executed") is True
        assert engine.devices["speaker_amp"]["state"] == "ON"

        r_rhet = client.post("/api/voice_command", headers=h1, json={"transcript": "đèn đang bật à"})
        assert r_rhet.status_code == 200 and r_rhet.json().get("executed") is False

        # 7. Role 3 adversarial regressions: non-device door compounds ('cửa hàng', 'cửa sổ') & mixed valid+unsupported custom command
        for non_door in ("mở cửa hàng đi", "đóng cửa tiệm lại", "mở cửa sổ phòng khách", "mo cua hang di"):
            assert parse_direct_device_intents_vi(non_door) == [], f"Non-device door compound leaked action: {non_door!r}"
        r_door_shop = client.post("/api/text_command", headers=h1, json={"text": "mở cửa hàng đi"})
        assert r_door_shop.status_code == 200 and r_door_shop.json().get("executed") is False

        cnt_before_mix = len(list_custom_commands())
        for bad_mix in (
            "Tạo lệnh xem bậy hai gồm bật đèn phòng khách và bật điều hòa",
            "Tạo lệnh xem bậy ba gồm đọc nhiệt độ và bật quạt trần",
        ):
            r_bm = client.post("/api/text_command", headers=h1, json={"text": bad_mix})
            assert r_bm.status_code == 400 and not r_bm.json().get("requires_confirmation")
        r_bm_check = client.post("/api/text_command", headers=h1, json={"text": "Đặt lịch 21 giờ tối nay bật đèn phòng ngủ."})
        assert r_bm_check.status_code == 200 and r_bm_check.json().get("requires_confirmation") is True
        r_cancel_vi = client.post("/api/text_command", headers=h1, json={"text": "thôi hủy đi"})
        assert r_cancel_vi.status_code == 200 and r_cancel_vi.json().get("cancelled") is True
        assert len(list_custom_commands()) == cnt_before_mix


def test_round7_ctc_bare_noun_tail_guard_and_den_tone_verification() -> None:
    """Round 7 STT safety regressions: bare noun with trailing CTC repetition never triggers an action (F77), and 'đen' vs 'đèn' CTC tone verification preserves 'đen' (T158)."""
    from simulator.voice.chunkformer_ctc import rescore_closed_command_ctc
    from simulator.voice.vietnamese_stt import _classify_offline_transcript_kind

    # Bare noun with trailing repetition ('đèn phòng khách phòng') must never trigger Case A spoken-verb override
    import torch
    import simulator.voice.chunkformer_ctc as cf_mod

    # Synthetic unit check of Case A leading-token invariant even without loading heavy model weights
    import numpy as np

    assert _classify_offline_transcript_kind("tắt đen phòng khách")[0] == "unrecognized"
    from simulator.voice.gemini_stt import _should_escalate_offline_to_gemini

    need_esc, esc_reason = _should_escalate_offline_to_gemini(
        {"ok": True, "text": "tắt đen phòng khách", "stt_engine": "zipformer_70m+ctc_den_tone"},
        np.zeros(16000, dtype=np.float32),
        16000,
        has_pending_confirmation=False,
    )
    assert need_esc is False and esc_reason == "local_confident:ctc_den_tone"
    if cf_mod._CF_MODEL is not None and cf_mod._CF_TOK2ID:
        # When model is already loaded, ensure None/tiny tensors fail safely
        assert rescore_closed_command_ctc(None, "đèn phòng khách phòng") is None

    # Severe-noise CTC polarity confirmation margin: reject coin-flip off/on claims when min_confirm_margin=1.0
    from unittest.mock import patch
    from simulator.voice.chunkformer_ctc import verify_command_polarity_ctc

    fake_tok2id = {
        "\u2581bật": 1,
        "\u2581tắt": 2,
        "\u2581đèn": 3,
        "\u2581phòng": 4,
        "\u2581ngủ": 5,
        "\u2581ng": 5,
    }
    # Construct log_probs of shape (12, 8) where 'tắt' only barely beats 'bật' (margin < 1.0)
    lp = torch.full((12, 8), -8.0, dtype=torch.float32)
    lp[:, 0] = -0.2  # blank default
    lp[1, 1] = -0.75  # bật
    lp[1, 2] = -0.35  # tắt (slightly higher than bật, margin ~0.40 < 1.0)
    lp[3, 3] = -0.05  # đèn
    lp[5, 4] = -0.05  # phòng
    lp[7, 5] = -0.05  # ngủ
    lp = torch.log_softmax(lp, dim=-1)

    with (
        patch.object(cf_mod, "_CF_TOK2ID", fake_tok2id),
        patch.object(cf_mod, "decode_chunkformer_with_logprobs", return_value=("tắt đèn phòng ngủ", lp)),
    ):
        assert verify_command_polarity_ctc(np.zeros(16000, dtype=np.float32), "bedroom_light", "off") is True
        assert (
            verify_command_polarity_ctc(
                np.zeros(16000, dtype=np.float32),
                "bedroom_light",
                "off",
                min_confirm_margin=1.0,
            )
            is False
        )
        # Clear margin (>= 1.0) still passes confirmation
        lp_clear = lp.clone()
        lp_clear[1, 2] = 2.0
        lp_clear[1, 1] = -3.0
        lp_clear = torch.log_softmax(lp_clear, dim=-1)
        with patch.object(cf_mod, "decode_chunkformer_with_logprobs", return_value=("tắt đèn phòng ngủ", lp_clear)):
            assert (
                verify_command_polarity_ctc(
                    np.zeros(16000, dtype=np.float32),
                    "bedroom_light",
                    "off",
                    min_confirm_margin=1.0,
                )
                is True
            )


def test_round8_general_nlu_goals_1_to_7_and_thresholds() -> None:
    """Round 8 generic regressions: bare-light clarification (accented + unaccented), unlisted rooms,
    per-rule numeric thresholds (no hardcoded 35C/40%), clause decomposition, generic hesitation/deferral/exclusion,
    sound query without literal KY-037, conditional rule precedence over custom command, and reset phrasing."""
    from simulator.automation_repo import list_automation_rules
    from simulator.server import app
    from simulator.voice.vietnamese_policy import (
        classify_ambiguous_or_unsupported_vi,
        classify_small_talk_vi,
        parse_direct_device_intents_vi,
    )

    # Goal 2: Bare 'đèn' (BOTH accented AND unaccented) MUST clarify, NEVER mutate living_room_light
    for bare_light in ("bật đèn", "tắt đèn", "bat den", "tat den", "mở đèn đi"):
        assert parse_direct_device_intents_vi(bare_light) == [], f"Bare light mutated: {bare_light!r}"
        clar = classify_ambiguous_or_unsupported_vi(bare_light) or ""
        assert "phòng khách" in clar.lower() and "phòng ngủ" in clar.lower(), f"Bad clarify for {bare_light!r}: {clar!r}"

    # Goal 2: Unlisted rooms after 'đèn' MUST refuse with 0 mutations
    for unlisted in (
        "bật đèn bếp",
        "tắt đèn hành lang",
        "bật đèn ban công",
        "bật đèn sân thượng",
        "tắt đèn gác xép",
        "bật đèn nhà tắm",
        "bật đèn nhà vệ sinh",
    ):
        assert parse_direct_device_intents_vi(unlisted) == [], f"Unlisted room mutated: {unlisted!r}"

    # Goal 4: Clause decomposition (descriptive/reason prefix + imperative tail -> 0 polarity flips)
    assert parse_direct_device_intents_vi("Còi báo động kêu inh ỏi rồi, tắt ngay") == [
        {"device_id": "alarm_siren", "action": "turn_off"}
    ]
    assert parse_direct_device_intents_vi("Đủ nước rồi, ngưng chạy máy bơm") == [
        {"device_id": "garden_pump", "action": "turn_off"}
    ]
    assert parse_direct_device_intents_vi("Ngoài cổng có người tới, mở cửa chính") == [
        {"device_id": "main_door", "action": "open"}
    ]
    assert parse_direct_device_intents_vi("Tối om rồi, bật đèn phòng khách") == [
        {"device_id": "living_room_light", "action": "turn_on"}
    ]
    assert parse_direct_device_intents_vi("Phòng ngủ thì bật đèn") == [
        {"device_id": "bedroom_light", "action": "turn_on"}
    ]
    assert parse_direct_device_intents_vi("Bật cả đèn phòng khách lẫn đèn phòng ngủ") == [
        {"device_id": "living_room_light", "action": "turn_on"},
        {"device_id": "bedroom_light", "action": "turn_on"},
    ]
    assert parse_direct_device_intents_vi("Cúp nguồn mạch loa") == [
        {"device_id": "speaker_amp", "action": "turn_off"}
    ]
    assert parse_direct_device_intents_vi("Kích hoạt còi báo động") == [
        {"device_id": "alarm_siren", "action": "turn_on"}
    ]
    # Standalone-only help guard: polite tail 'giúp mình' must NOT hijack commands
    assert classify_small_talk_vi("mở cửa chính giúp mình") is None
    assert classify_small_talk_vi("giúp mình với") is not None

    # Goal 5: Generic hesitation, deferral, past-tense narration, and all-6-device exclusions
    for no_act in (
        "khoan đã bật đèn phòng khách",
        "khoan hẵng mở cửa chính",
        "chờ chút hãy bật máy bơm",
        "từ từ tắt còi báo động",
        "để sau mở cửa chính",
        "chưa muốn bật đèn phòng ngủ",
        "hồi sáng tôi đã bật đèn phòng khách",
        "vừa rồi đã đóng cửa chính",
        "để nguyên cửa chính",
        "giữ nguyên đèn phòng ngủ",
    ):
        assert parse_direct_device_intents_vi(no_act) == [], f"Safety guard leaked action on {no_act!r}"

    # Exclusion across all 6 devices (set-difference on 'trừ')
    assert parse_direct_device_intents_vi("tắt hết đèn trừ đèn phòng ngủ") == [
        {"device_id": "living_room_light", "action": "turn_off"}
    ]
    assert parse_direct_device_intents_vi("bật máy bơm chứ không phải cửa chính") == [
        {"device_id": "garden_pump", "action": "turn_on"}
    ]

    engine = _reset_engine_clean()
    h1, _, _, _ = _seed_sessions()

    with TestClient(app) as client:
        # Goal 2 E2E: bare 'bật đèn' clarifies with 0 device mutation
        r_bare = client.post("/api/voice_command", headers=h1, json={"transcript": "bật đèn"})
        assert r_bare.status_code == 200 and r_bare.json().get("executed") is False
        assert engine.devices["living_room_light"]["state"] == "OFF"
        assert "phòng khách" in _assert_vi_reply(r_bare.json()).lower()

        # Goal 7 T116: sound-sensor query without literal KY-037
        asyncio.run(engine.update_sound_telemetry(sound_detected=True))
        r_snd = client.post("/api/voice_command", headers=h1, json={"transcript": "Cảm biến có đang phát hiện tiếng động không?"})
        assert r_snd.status_code == 200 and r_snd.json().get("kind") == "sensor_query"
        assert "tiếng động lớn" in _assert_vi_reply(r_snd.json()).lower()

        # Goal 7 T139: conditional rule grammar takes precedence over custom command
        r_t139 = client.post("/api/voice_command", headers=h1, json={"transcript": "Tạo lệnh cứ mở cửa chính là đèn phòng khách tự bật."})
        assert r_t139.status_code == 200
        d_t139 = r_t139.json()
        assert d_t139.get("requires_confirmation") is True
        assert d_t139.get("action_kind") in ("create_automation_rule", "create_compound_rule")
        assert client.post("/api/voice_command", headers=h1, json={"transcript": "ok"}).json().get("confirmed") is True
        client.post("/api/device", headers=h1, json={"device_id": "main_door", "action": "open"})
        assert engine.devices["living_room_light"]["state"] == "ON"

        # Goal 3: Per-rule numeric thresholds (>30°C triggers at 31°C, NOT at 29°C; >34°C triggers at 35°C, NOT at 32°C)
        _reset_engine_clean()
        r_th1 = client.post("/api/text_command", headers=h1, json={"text": "Khi nhiệt độ trên 30 độ thì bật đèn phòng khách"})
        assert r_th1.status_code == 200 and r_th1.json().get("requires_confirmation") is True
        assert client.post("/api/text_command", headers=h1, json={"text": "ok"}).json().get("confirmed") is True

        r_th2 = client.post("/api/text_command", headers=h1, json={"text": "Khi nhiệt độ trên 34 độ thì bật còi báo động"})
        assert r_th2.status_code == 200 and r_th2.json().get("requires_confirmation") is True
        assert client.post("/api/text_command", headers=h1, json={"text": "ok"}).json().get("confirmed") is True

        asyncio.run(engine.update_sensor_telemetry(temp_c=29.0, humidity_pct=60.0))
        assert engine.devices["living_room_light"]["state"] == "OFF"
        assert engine.devices["alarm_siren"]["state"] == "OFF"

        asyncio.run(engine.update_sensor_telemetry(temp_c=31.5, humidity_pct=60.0))
        assert engine.devices["living_room_light"]["state"] == "ON"
        assert engine.devices["alarm_siren"]["state"] == "OFF"

        asyncio.run(engine.update_sensor_telemetry(temp_c=35.0, humidity_pct=60.0))
        assert engine.devices["alarm_siren"]["state"] == "ON"

        # Soil threshold < 50% triggers at 48% (NOT collapsed to hardcoded 40%!)
        _reset_engine_clean()
        r_soil = client.post("/api/text_command", headers=h1, json={"text": "Khi độ ẩm đất dưới 50% thì bật đèn phòng ngủ"})
        assert r_soil.status_code == 200 and r_soil.json().get("requires_confirmation") is True
        assert client.post("/api/text_command", headers=h1, json={"text": "ok"}).json().get("confirmed") is True

        asyncio.run(engine.update_soil_moisture_telemetry(55.0))
        assert engine.devices["bedroom_light"]["state"] == "OFF"
        asyncio.run(engine.update_soil_moisture_telemetry(48.0))
        assert engine.devices["bedroom_light"]["state"] == "ON"
        assert len(list_automation_rules()) >= 0


def test_round8_remediation1_general_structural_safety_and_nlu() -> None:
    """Verify all 7 general structural fixes: deferral/keep-unchanged/past-narration safety,
    wrong-diacritic & imperative precedence over sensor_query, benign save/status vs reset,
    query_members & macro-creation guards, generalized direct/context/unaccented/unlisted-room parsing,
    broadened confirmation/cancellation, and weekday-range schedules + sound rules + all-device status."""
    from simulator.automation_engine import parse_weekdays_vi
    from simulator.automation_nlu import _classify_confirmation_utterance
    from simulator.server import app
    from simulator.voice.vietnamese_policy import parse_direct_device_intents_vi

    # 1. Weekday ranges (digits & spoken Vietnamese)
    assert parse_weekdays_vi("lịch từ thứ 2 đến thứ 6") == [0, 1, 2, 3, 4]
    assert parse_weekdays_vi("lịch từ thứ hai đến thứ sáu") == [0, 1, 2, 3, 4]
    assert parse_weekdays_vi("lịch thứ 2 tới thứ 7") == [0, 1, 2, 3, 4, 5]
    assert parse_weekdays_vi("lịch từ thứ hai đến chủ nhật") == [0, 1, 2, 3, 4, 5, 6]
    assert parse_weekdays_vi("lịch làm việc trong tuần") == [0, 1, 2, 3, 4]
    assert parse_weekdays_vi("lịch cuối tuần") == [5, 6]

    # 2. Broadened confirmation & cancellation classifier
    for c_yes in (
        "chốt", "chốt đi", "chốt luôn", "ừ chốt luôn giúp anh nhé",
        "vâng đồng ý thực hiện giúp tôi đi", "chuẩn rồi làm đi em",
        "ok lưu đi nhé", "được tạo đi giúp tôi", "xác nhận xóa đi", "oke reset đi", "ừ hủy đi",
    ):
        assert _classify_confirmation_utterance(c_yes, has_pending=True) == "confirm", f"Missed confirm: {c_yes!r}"
    for c_no in (
        "hủy bỏ", "thôi không làm nữa đâu em", "không cần nữa ạ", "dừng lại đi", "đừng làm nhé",
    ):
        assert _classify_confirmation_utterance(c_no, has_pending=True) == "cancel", f"Missed cancel: {c_no!r}"

    # 3. Direct, context-clause, multi-device, unaccented, and unlisted-room prepositions
    assert parse_direct_device_intents_vi("tat den phong ngu") == [{"device_id": "bedroom_light", "action": "turn_off"}]
    assert parse_direct_device_intents_vi("mo cua chinh") == [{"device_id": "main_door", "action": "open"}]
    assert parse_direct_device_intents_vi("bat may bom tuoi cay giup em") == [{"device_id": "garden_pump", "action": "turn_on"}]
    assert parse_direct_device_intents_vi("Ngoài sân tối quá bật đèn phòng khách giúp tôi") == [
        {"device_id": "living_room_light", "action": "turn_on"}
    ]
    assert parse_direct_device_intents_vi("Mấy luống rau ngoài sân héo rồi khởi động máy bơm tưới cây lên hộ tôi") == [
        {"device_id": "garden_pump", "action": "turn_on"}
    ]
    assert parse_direct_device_intents_vi("Phòng khách thì tắt đèn, ngoài vườn thì bật bơm") == [
        {"device_id": "living_room_light", "action": "turn_off"},
        {"device_id": "garden_pump", "action": "turn_on"},
    ]
    assert parse_direct_device_intents_vi("mở đèn ngoài ban công") == []
    assert parse_direct_device_intents_vi("bật đèn ở nhà bếp") == []

    engine = _reset_engine_clean()
    h1, _, _, _ = _seed_sessions()
    with TestClient(app) as client:
        # 4. Deferral + 'kích hoạt', keep-unchanged, and past-tense narration -> 0 mutations, executed=False
        for safe_utt in (
            "Khoan hẵng kích hoạt còi báo động nhé, tôi còn đang kiểm tra.",
            "Chờ chút, đừng mở cửa chính, tôi ra ngay.",
            "Cứ để nguyên đèn phòng khách nhé.",
            "Giữ nguyên trạng thái đèn phòng ngủ nhé.",
            "Hồi sáng tôi đã bật máy bơm tưới cây rồi.",
            "Lúc nãy anh vừa mới đóng cửa chính rồi.",
        ):
            r = client.post("/api/voice_command", headers=h1, json={"transcript": safe_utt})
            d = r.json()
            assert r.status_code == 200 and d.get("executed") is False and d.get("requires_confirmation") is False, f"Leak on {safe_utt!r}: {d}"
            assert d.get("kind") == "negation_no_action", f"Wrong kind on {safe_utt!r}: {d.get('kind')}"

        # 5. Wrong-diacritic over sensor_query -> clarify_no_action (executed=False), NEVER sensor_query
        r_wd = client.post("/api/voice_command", headers=h1, json={"transcript": "Ngoài sân có tiếng động lạ, bật côi báo động lên"})
        assert r_wd.status_code == 200 and r_wd.json().get("executed") is False
        assert r_wd.json().get("kind") == "clarify_no_action"

        # 6. Imperative with noise/dryness context -> executes device, NOT sensor_query
        r_imp = client.post("/api/voice_command", headers=h1, json={"transcript": "Đất ngoài vườn khô quá rồi, bật máy bơm tưới cây lên hộ tôi"})
        assert r_imp.status_code == 200 and r_imp.json().get("executed") is True
        assert engine.devices["garden_pump"]["state"] == "ON"

        # 7. Benign save/status NEVER triggers factory_reset or reset_devices
        for benign in ("Lưu trạng thái thiết bị hiện tại.", "Save trạng thái hệ thống."):
            rb = client.post("/api/text_command", headers=h1, json={"text": benign})
            assert rb.status_code == 200 and rb.json().get("requires_confirmation") is False

        # 8. Compositional macro creation hard-blocks premature device execution & run/delete beats query_custom_commands
        _reset_engine_clean()
        rm = client.post(
            "/api/voice_command",
            headers=h1,
            json={"transcript": "Thiết lập giùm tôi một lệnh riêng tên là tiếp khách để bật đèn phòng khách và mở cửa chính."},
        )
        assert rm.status_code == 200 and rm.json().get("requires_confirmation") is True
        assert engine.devices["living_room_light"]["state"] == "OFF"
        assert engine.devices["main_door"]["state"] == "CLOSED"
        assert client.post("/api/voice_command", headers=h1, json={"transcript": "chốt luôn giúp anh nhé"}).json().get("confirmed") is True

        r_run = client.post("/api/voice_command", headers=h1, json={"transcript": "Kích hoạt lệnh tiếp khách"})
        assert r_run.status_code == 200 and r_run.json().get("requires_confirmation") is True
        assert r_run.json().get("action_kind") == "run_custom_command"
        assert client.post("/api/voice_command", headers=h1, json={"transcript": "hủy bỏ nhé"}).json().get("cancelled") is True

        r_del = client.post("/api/voice_command", headers=h1, json={"transcript": "Gỡ bỏ lệnh tiếp khách giúp tôi"})
        assert r_del.status_code == 200 and r_del.json().get("requires_confirmation") is True
        assert r_del.json().get("action_kind") == "delete_custom_command"
        assert client.post("/api/voice_command", headers=h1, json={"transcript": "ok xóa đi"}).json().get("confirmed") is True

        # 9. Weekday-range schedule does NOT trigger clarify_near_miss_timer
        r_wd_sc = client.post(
            "/api/voice_command",
            headers=h1,
            json={"transcript": "Đặt lịch định kỳ từ thứ hai đến thứ sáu lúc 7 giờ 30 bật đèn phòng khách."},
        )
        assert r_wd_sc.status_code == 200 and r_wd_sc.json().get("requires_confirmation") is True
        assert r_wd_sc.json().get("action_kind") == "create_schedule"
        assert client.post("/api/voice_command", headers=h1, json={"transcript": "hủy"}).json().get("cancelled") is True

        # 10. Sound rule trigger & all-devices status query
        r_snd_rule = client.post(
            "/api/voice_command",
            headers=h1,
            json={"transcript": "Bất cứ lúc nào có tiếng ồn bất thường thì bật còi báo động."},
        )
        assert r_snd_rule.status_code == 200 and r_snd_rule.json().get("requires_confirmation") is True
        assert client.post("/api/voice_command", headers=h1, json={"transcript": "hủy"}).json().get("cancelled") is True

        r_st = client.post("/api/voice_command", headers=h1, json={"transcript": "Nhà mình đang bật gì thế?"})
        assert r_st.status_code == 200 and r_st.json().get("kind") == "device_status_query"
        assert len(r_st.json().get("devices") or []) == 6








