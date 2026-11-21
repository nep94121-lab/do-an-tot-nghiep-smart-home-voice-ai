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

    # 3. Regional / clipped direct commands preserve polarity
    assert parse_direct_device_intents_vi("Bật thiết đèn.") == [
        {"device_id": "living_room_light", "action": "turn_on"},
        {"device_id": "bedroom_light", "action": "turn_on"},
    ]
    assert parse_direct_device_intents_vi("tắt hoa") == [{"device_id": "speaker_amp", "action": "turn_off"}]
    assert parse_direct_device_intents_vi("hóa cửa chính") == [{"device_id": "main_door", "action": "close"}]
    assert parse_direct_device_intents_vi("bật ngòi hú") == [{"device_id": "alarm_siren", "action": "turn_on"}]

    # 4. Spoken Vietnamese numbers, custom-command ASR wrappers, and sensor triggers
    assert "7 gio" in _normalize_vi_spoken_numbers("bảy giờ sáng")
    assert "2 giay" in _normalize_vi_spoken_numbers("hai giây nữa")
    assert _parse_sensor_trigger("Khi có biến động lớn") == ("sound_sensor", "LOUD")
    for utt in (
        "Sau khi đi làm là tắt tất cả đèn và đóng cửa chính.",
        "Chào, hãy đi làm là tắt tất cả đèn và đóng cửa chính.",
        "Chỉ tạo lệnh ghi âm là tắt tất cả đèn và đóng cửa chính.",
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

        # 5. J01_13 ASR slip 'bạn nguồn mệt loa' -> turns ON speaker_amp immediately
        r_amp = client.post("/api/voice_command", headers=h1, json={"transcript": "bạn nguồn mệt loa"})
        assert r_amp.status_code == 200 and r_amp.json().get("executed") is True
        assert engine.devices["speaker_amp"]["state"] == "ON"

        # 6. J04_14 ASR slip 'khôi phục ngày đàn tốt' -> requires confirmation for Tier 1, denied for Tier 2
        r_fr_t2 = client.post("/api/voice_command", headers=h2, json={"transcript": "khôi phục ngày đàn tốt"})
        assert r_fr_t2.status_code == 403
        r_fr_t1 = client.post("/api/voice_command", headers=h1, json={"transcript": "khôi phục ngày đàn tốt"})
        assert r_fr_t1.status_code == 200 and r_fr_t1.json().get("requires_confirmation") is True
        # Cancel with ASR slip 'đồng thời' (for 'không thôi')
        r_can = client.post("/api/voice_command", headers=h1, json={"transcript": "đồng thời"})
        assert r_can.status_code == 200 and r_can.json().get("executed") is False

        # 7. Scoped reset ASR slip 'reet lại trạng thái thiết bị' -> requires confirmation
        r_rs = client.post("/api/voice_command", headers=h1, json={"transcript": "reet lại trạng thái thiết bị"})
        assert r_rs.status_code == 200 and r_rs.json().get("requires_confirmation") is True
        client.post("/api/voice_command", headers=h1, json={"transcript": "hủy"})

        # 8. Schedule modify slip 'dự lịch 7 giờ thành 8 giờ' & delete rule slip 'xóa liên thiếp đèn phòng khách'
        r_mk = client.post("/api/voice_command", headers=h1, json={"transcript": "7 giờ sáng bật đèn phòng khách"})
        assert r_mk.status_code == 200 and r_mk.json().get("requires_confirmation") is True
        r_mk_ok = client.post("/api/voice_command", headers=h1, json={"transcript": "đồng ý"})
        assert r_mk_ok.status_code == 200 and r_mk_ok.json().get("confirmed") is True

        r_mod = client.post("/api/voice_command", headers=h1, json={"transcript": "dự lịch 7 giờ thành 8 giờ"})
        assert r_mod.status_code == 200 and r_mod.json().get("requires_confirmation") is True
        client.post("/api/voice_command", headers=h1, json={"transcript": "hủy"})

        r_del_rule = client.post("/api/voice_command", headers=h1, json={"transcript": "xóa liên thiếp đèn phòng khách"})
        assert r_del_rule.status_code == 200 and r_del_rule.json().get("requires_confirmation") is True
        client.post("/api/voice_command", headers=h1, json={"transcript": "hủy"})

        # 9. Iteration-3 ASR NLU slips: 're logic trạng thái thiết nghi', 'dự định 7 giờ thành 8 giờ', 'hát đèn' -> 'tắt đèn'
        r_rl = client.post("/api/voice_command", headers=h1, json={"transcript": "re logic trạng thái thiết nghi"})
        assert r_rl.status_code == 200 and r_rl.json().get("requires_confirmation") is True
        client.post("/api/voice_command", headers=h1, json={"transcript": "hủy"})

        r_dd = client.post("/api/voice_command", headers=h1, json={"transcript": "dự định bảy giờ thành tám giờ"})
        assert r_dd.status_code == 200 and r_dd.json().get("requires_confirmation") is True
        client.post("/api/voice_command", headers=h1, json={"transcript": "hủy"})

        r_ht = client.post("/api/voice_command", headers=h1, json={"transcript": "sau ba giây hát đèn hò khách"})
        assert r_ht.status_code == 200 and r_ht.json().get("requires_confirmation") is True
        assert "tắt đèn phòng khách" in str(r_ht.json().get("reply") or "").lower()
        client.post("/api/voice_command", headers=h1, json={"transcript": "hủy"})

        # 10. Multi-clause without comma ('tắt đèn phòng khách tắt đèn ngồi ngủ và tắt nguồn vài loa') -> all 3 devices
        from simulator.voice.vietnamese_policy import parse_direct_device_intents_vi

        m3 = parse_direct_device_intents_vi("tắt đèn phòng khách tắt đèn ngồi ngủ và tắt nguồn vài loa")
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
    assert _classify_offline_transcript_kind("vì sách trạng thái thiết bị") == ("recognized", None)

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

        # Reset via 'vì sách trạng thái thiết bị' must stage confirmation, not execute
        r_rst = client.post("/api/voice_command", headers=h1, json={"transcript": "vì sách trạng thái thiết bị"})
        assert r_rst.status_code == 200 and r_rst.json().get("requires_confirmation") is True

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
    assert parse_direct_device_intents_vi("bật ngùng mặt loa") == [
        {"device_id": "speaker_amp", "action": "turn_on"}
    ]
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

    g_j52 = gemini_stt._run_high_noise_hallucination_gate(
        gemini_text="tắt đèn",
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


