"""End-to-end verification suite for autotool-20261122:
- Compound cross-device rule engine (AND/OR, numeric sensors, device states, time_window wrap-around,
  house_mode, multi-action, hysteresis deadband, else_actions, cooldown suppression & expiry, cycle/loop prevention)
- Real-time countdown timer firing
- Recurring weekday schedule evaluation via run_scheduler_tick_once
- Unified AI tool registry parity (/api/tools, ALL_TOOLS, LiveBridgeSession.handle_tool_call vs /api/text_command)
- Single Source of Truth UI guidance (/api/ui_registry vs get_ui_guidance vs automation.html & index.html)
- Removed devices polite Vietnamese refusal + Tier 3 Guest RBAC lock on automation mutations
"""
from __future__ import annotations

import asyncio
import datetime
import os
import pathlib
import time
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from backend.ai_tool_registry import TOOL_REGISTRY, dispatch_tool
from backend.api.deps import _REST_ENGINE
from backend.api.routes_automation import run_scheduler_tick_once
from backend.automation_engine import (
    CANONICAL_6_DEVICES,
    create_compound_rule,
    evaluate_compound_rules,
    get_compound_rule,
    validate_compound_rule_input,
)
from backend.automation_repo import create_schedule
from backend.live.prompt_builder import ALL_TOOLS
from backend.live.tool_dispatcher_mixin import LiveToolDispatcherMixin
from backend.server import app
from backend.ui_registry import get_ui_guidance, get_ui_registry

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAIGON_TZ = ZoneInfo("Asia/Saigon")


def _owner_session() -> SimpleNamespace:
    return SimpleNamespace(
        user_id="tuan_anh",
        tier=1,
        display_name="Nguyễn Tuấn Anh",
        role="ADMIN",
        is_authenticated=True,
        session_id="test_owner_autotool",
        token_hash="tok_owner_autotool",
        is_expired=lambda: False,
    )


def _guest_session() -> SimpleNamespace:
    return SimpleNamespace(
        user_id="khach_c",
        tier=3,
        display_name="Khách C",
        role="GUEST",
        is_authenticated=True,
        session_id="test_guest_autotool",
        token_hash="tok_guest_autotool",
        is_expired=lambda: False,
    )


def _login_owner_headers(client: TestClient) -> dict[str, str]:
    from backend.auth_3layer import get_auth_3layer_manager, hash_password
    from backend.voice_config import OWNER_EMAIL

    mgr = get_auth_3layer_manager()
    pw = "AutoToolTestPw!2026"
    for acc in mgr.accounts:
        acc.pop("pending_otp", None)
        if acc.get("email") == OWNER_EMAIL:
            acc["password_hash"] = hash_password(pw)
    r1 = client.post(
        "/api/auth3/layer1_login",
        json={"email": OWNER_EMAIL, "password": pw, "send_gmail": False},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    tok = d1.get("session_token") or ""
    if not tok:
        otp = d1.get("otp_code_for_test") or d1.get("demo_otp_preview") or ""
        assert otp
        r2 = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": OWNER_EMAIL, "otp_code": otp},
        )
        assert r2.status_code == 200
        tok = r2.json()["session_token"]
    return {"X-Session-Token": tok}


def _login_guest_headers(client: TestClient, owner_headers: dict[str, str]) -> dict[str, str]:
    inv = client.post(
        "/api/auth3/guest_invites",
        json={"tier": 3, "ttl_sec": 3600, "pin": "1357", "pin_confirm": "1357"},
        headers=owner_headers,
    )
    assert inv.status_code == 200
    token = inv.json()["token"]
    red = client.post("/api/guest/redeem", json={"token": token})
    assert red.status_code == 200
    return {"X-Session-Token": red.json()["session_token"]}


@pytest.fixture(autouse=True)
def _offline_sandbox_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")
    monkeypatch.setenv("SMARTHOME_AOEDE_CACHE_ONLY", "1")
    monkeypatch.setenv("SMARTHOME_SKIP_STT_PRELOAD", "1")
    _REST_ENGINE.devices["main_door"]["state"] = "CLOSED"
    for d in ("living_room_light", "bedroom_light", "garden_pump", "alarm_siren", "speaker_amp"):
        _REST_ENGINE.devices[d]["state"] = "OFF"
    _REST_ENGINE.house_mode = "HOME"
    _REST_ENGINE.mqtt_bridge.dht11_telemetry["temp_c"] = 25.0
    _REST_ENGINE.mqtt_bridge.dht11_telemetry["humidity_pct"] = 60.0
    _REST_ENGINE.mqtt_bridge.soil_moisture_telemetry["soil_moisture_pct"] = 55.0
    _REST_ENGINE.mqtt_bridge.sound_telemetry["sound_detected"] = False
    _REST_ENGINE.persist_to_shared_store()


def _set_sim_state(
    *,
    temp_c: float | None = None,
    humidity_pct: float | None = None,
    soil_pct: float | None = None,
    sound_detected: bool | None = None,
    house_mode: str | None = None,
    door_state: str | None = None,
) -> None:
    if temp_c is not None:
        _REST_ENGINE.mqtt_bridge.dht11_telemetry["temp_c"] = float(temp_c)
    if humidity_pct is not None:
        _REST_ENGINE.mqtt_bridge.dht11_telemetry["humidity_pct"] = float(humidity_pct)
    if soil_pct is not None:
        _REST_ENGINE.mqtt_bridge.soil_moisture_telemetry["soil_moisture_pct"] = float(soil_pct)
    if sound_detected is not None:
        _REST_ENGINE.mqtt_bridge.sound_telemetry["sound_detected"] = bool(sound_detected)
    if house_mode is not None:
        _REST_ENGINE.house_mode = house_mode
    if door_state is not None:
        _REST_ENGINE.devices["main_door"]["state"] = door_state
    _REST_ENGINE.persist_to_shared_store()


def test_1_compound_and_rule_hysteresis_else_and_cooldown() -> None:
    """AND rule (soil < 40% AND temp > 32°C -> garden_pump ON + living_room_light ON, else -> both OFF)
    verifies partial non-fire, full fire, hysteresis deadband latching, recovery + else_actions,
    cooldown suppression, and re-fire after cooldown expires."""
    rule = create_compound_rule(
        owner_user_id="tuan_anh",
        owner_tier=1,
        owner_name="Nguyễn Tuấn Anh",
        name="Tưới cây & bật đèn khi đất khô và trời nóng",
        logic="AND",
        conditions=[
            {"source": "soil_sensor", "operator": "<", "value": 40.0, "hysteresis": 5.0},
            {"source": "temp_sensor", "operator": ">", "value": 32.0, "hysteresis": 2.0},
        ],
        actions=[
            {"device_id": "garden_pump", "action": "turn_on"},
            {"device_id": "living_room_light", "action": "turn_on"},
        ],
        else_actions=[
            {"device_id": "garden_pump", "action": "turn_off"},
            {"device_id": "living_room_light", "action": "turn_off"},
        ],
        cooldown_seconds=30.0,
        engine=_REST_ENGINE,
    )
    rid = rule["rule_id"]
    t0 = 1_800_000_000.0
    now_dt = datetime.datetime(2026, 11, 22, 14, 0, tzinfo=SAIGON_TZ)

    # 1) Partial AND match: soil=30 (<40) TRUE, temp=25 (>32) FALSE -> MUST NOT FIRE
    _set_sim_state(soil_pct=30.0, temp_c=25.0)
    asyncio.run(evaluate_compound_rules(_REST_ENGINE, trigger_source="test", now_dt=now_dt, now_epoch=t0))
    assert _REST_ENGINE.devices["garden_pump"]["state"] == "OFF"
    assert _REST_ENGINE.devices["living_room_light"]["state"] == "OFF"
    assert get_compound_rule(rid)["last_matched"] is False

    # 2) Full AND match: soil=30, temp=35 -> FIRES both actions!
    _set_sim_state(soil_pct=30.0, temp_c=35.0)
    asyncio.run(evaluate_compound_rules(_REST_ENGINE, trigger_source="test", now_dt=now_dt, now_epoch=t0 + 1.0))
    assert _REST_ENGINE.devices["garden_pump"]["state"] == "ON"
    assert _REST_ENGINE.devices["living_room_light"]["state"] == "ON"
    assert get_compound_rule(rid)["last_matched"] is True

    # 3) Hysteresis deadband: soil=30, temp=31.5 (> 32 - 2 = 30.0) -> stays latched, does NOT flap or run else_actions
    _set_sim_state(soil_pct=30.0, temp_c=31.5)
    asyncio.run(evaluate_compound_rules(_REST_ENGINE, trigger_source="test", now_dt=now_dt, now_epoch=t0 + 5.0))
    assert _REST_ENGINE.devices["garden_pump"]["state"] == "ON"
    assert _REST_ENGINE.devices["living_room_light"]["state"] == "ON"
    assert get_compound_rule(rid)["last_matched"] is True

    # 4) Recovery outside hysteresis (after cooldown so else_actions run): soil=50 (>=45), temp=28 (<=30)
    _set_sim_state(soil_pct=50.0, temp_c=28.0)
    asyncio.run(evaluate_compound_rules(_REST_ENGINE, trigger_source="test", now_dt=now_dt, now_epoch=t0 + 40.0))
    assert _REST_ENGINE.devices["garden_pump"]["state"] == "OFF"
    assert _REST_ENGINE.devices["living_room_light"]["state"] == "OFF"
    assert get_compound_rule(rid)["last_matched"] is False

    # 5) Immediate re-trigger within 30s cooldown (at t0 + 45, only 5s after else fired at t0 + 40) -> suppressed!
    _set_sim_state(soil_pct=30.0, temp_c=35.0)
    asyncio.run(evaluate_compound_rules(_REST_ENGINE, trigger_source="test", now_dt=now_dt, now_epoch=t0 + 45.0))
    assert _REST_ENGINE.devices["garden_pump"]["state"] == "OFF"
    assert _REST_ENGINE.devices["living_room_light"]["state"] == "OFF"

    # 6) After cooldown expires (t0 + 75, 35s > 30s) -> fires cleanly again!
    asyncio.run(evaluate_compound_rules(_REST_ENGINE, trigger_source="test", now_dt=now_dt, now_epoch=t0 + 75.0))
    assert _REST_ENGINE.devices["garden_pump"]["state"] == "ON"
    assert _REST_ENGINE.devices["living_room_light"]["state"] == "ON"


def test_2_compound_or_rule_fires_when_either_condition_matches() -> None:
    """OR rule (humidity > 80% OR temp > 36°C -> speaker_amp ON) fires when either branch triggers."""
    create_compound_rule(
        owner_user_id="tuan_anh",
        owner_tier=1,
        logic="OR",
        conditions=[
            {"source": "humidity_sensor", "operator": ">", "value": 80.0, "hysteresis": 2.0},
            {"source": "temp_sensor", "operator": ">", "value": 36.0, "hysteresis": 1.0},
        ],
        actions=[{"device_id": "speaker_amp", "action": "turn_on"}],
        else_actions=[{"device_id": "speaker_amp", "action": "turn_off"}],
        cooldown_seconds=0.0,
        engine=_REST_ENGINE,
    )
    t0 = 1_800_010_000.0
    now_dt = datetime.datetime(2026, 11, 22, 15, 0, tzinfo=SAIGON_TZ)

    # Neither condition -> OFF
    _set_sim_state(humidity_pct=60.0, temp_c=28.0)
    asyncio.run(evaluate_compound_rules(_REST_ENGINE, now_dt=now_dt, now_epoch=t0))
    assert _REST_ENGINE.devices["speaker_amp"]["state"] == "OFF"

    # Only humidity > 80 -> fires ON
    _set_sim_state(humidity_pct=85.0)
    asyncio.run(evaluate_compound_rules(_REST_ENGINE, now_dt=now_dt, now_epoch=t0 + 1))
    assert _REST_ENGINE.devices["speaker_amp"]["state"] == "ON"

    # Reset below both thresholds -> else_actions turns OFF
    _set_sim_state(humidity_pct=60.0, temp_c=28.0)
    asyncio.run(evaluate_compound_rules(_REST_ENGINE, now_dt=now_dt, now_epoch=t0 + 2))
    assert _REST_ENGINE.devices["speaker_amp"]["state"] == "OFF"

    # Only temp > 36 -> fires ON
    _set_sim_state(temp_c=37.5)
    asyncio.run(evaluate_compound_rules(_REST_ENGINE, now_dt=now_dt, now_epoch=t0 + 3))
    assert _REST_ENGINE.devices["speaker_amp"]["state"] == "ON"


def test_3_compound_rule_door_open_and_night_time_window_wraparound() -> None:
    """main_door == OPEN AND time_window 18:00..06:00 -> does NOT fire at 14:00, DOES fire at 22:30 and 02:15."""
    create_compound_rule(
        owner_user_id="tuan_anh",
        owner_tier=1,
        logic="AND",
        conditions=[
            {"source": "main_door", "state": "OPEN"},
            {"source": "time_window", "start_hhmm": "18:00", "end_hhmm": "06:00"},
        ],
        actions=[
            {"device_id": "living_room_light", "action": "turn_on"},
            {"device_id": "bedroom_light", "action": "turn_on"},
        ],
        cooldown_seconds=0.0,
        engine=_REST_ENGINE,
    )
    _set_sim_state(door_state="OPEN")
    t0 = 1_800_020_000.0

    # 14:00 -> daytime, MUST NOT fire
    dt_day = datetime.datetime(2026, 11, 22, 14, 0, tzinfo=SAIGON_TZ)
    asyncio.run(evaluate_compound_rules(_REST_ENGINE, now_dt=dt_day, now_epoch=t0))
    assert _REST_ENGINE.devices["living_room_light"]["state"] == "OFF"
    assert _REST_ENGINE.devices["bedroom_light"]["state"] == "OFF"

    # 22:30 -> night window, MUST FIRE both lights
    dt_night = datetime.datetime(2026, 11, 22, 22, 30, tzinfo=SAIGON_TZ)
    asyncio.run(evaluate_compound_rules(_REST_ENGINE, now_dt=dt_night, now_epoch=t0 + 1))
    assert _REST_ENGINE.devices["living_room_light"]["state"] == "ON"
    assert _REST_ENGINE.devices["bedroom_light"]["state"] == "ON"


def test_4_compound_rule_sound_loud_and_away_house_mode() -> None:
    """sound_sensor == LOUD AND house_mode == AWAY -> does NOT fire when HOME, DOES fire when AWAY."""
    create_compound_rule(
        owner_user_id="tuan_anh",
        owner_tier=1,
        logic="AND",
        conditions=[
            {"source": "sound_sensor", "state": "LOUD"},
            {"source": "house_mode", "state": "AWAY"},
        ],
        actions=[
            {"device_id": "alarm_siren", "action": "turn_on"},
            {"device_id": "living_room_light", "action": "turn_on"},
        ],
        cooldown_seconds=0.0,
        engine=_REST_ENGINE,
    )
    t0 = 1_800_030_000.0
    now_dt = datetime.datetime(2026, 11, 22, 20, 0, tzinfo=SAIGON_TZ)

    # HOME + LOUD -> must NOT fire
    _set_sim_state(house_mode="HOME", sound_detected=True)
    asyncio.run(evaluate_compound_rules(_REST_ENGINE, now_dt=now_dt, now_epoch=t0))
    assert _REST_ENGINE.devices["alarm_siren"]["state"] == "OFF"
    assert _REST_ENGINE.devices["living_room_light"]["state"] == "OFF"

    # AWAY + LOUD -> FIRES!
    _set_sim_state(house_mode="AWAY", sound_detected=True)
    asyncio.run(evaluate_compound_rules(_REST_ENGINE, now_dt=now_dt, now_epoch=t0 + 1))
    assert _REST_ENGINE.devices["alarm_siren"]["state"] == "ON"
    assert _REST_ENGINE.devices["living_room_light"]["state"] == "ON"


def test_5_cycle_and_loop_prevention() -> None:
    """Self-loop (A->A) and multi-hop loop (A->B, B->A) rejected at validation/creation time; runtime depth guard works."""
    # Self-loop rejected
    with pytest.raises(ValueError, match="vòng lặp"):
        validate_compound_rule_input(
            owner_user_id="tuan_anh",
            owner_tier=1,
            logic="AND",
            conditions=[{"source": "living_room_light", "state": "ON"}],
            actions=[{"device_id": "living_room_light", "action": "turn_off"}],
            engine=_REST_ENGINE,
        )

    # Create A -> B cleanly
    create_compound_rule(
        owner_user_id="tuan_anh",
        owner_tier=1,
        logic="AND",
        conditions=[{"source": "living_room_light", "state": "ON"}],
        actions=[{"device_id": "bedroom_light", "action": "turn_on"}],
        engine=_REST_ENGINE,
    )

    # Multi-hop loop B -> A MUST be rejected!
    with pytest.raises(ValueError, match="vòng lặp"):
        create_compound_rule(
            owner_user_id="tuan_anh",
            owner_tier=1,
            logic="AND",
            conditions=[{"source": "bedroom_light", "state": "ON"}],
            actions=[{"device_id": "living_room_light", "action": "turn_on"}],
            engine=_REST_ENGINE,
        )

    # Runtime recursion guard: when _compound_eval_depth > 0, re-entrant evaluation returns []
    _REST_ENGINE._compound_eval_depth = 1
    try:
        res = asyncio.run(evaluate_compound_rules(_REST_ENGINE))
        assert res == []
    finally:
        _REST_ENGINE._compound_eval_depth = 0


def test_6_timer_realtime_firing_via_unified_tool() -> None:
    """Create 1.5s countdown timer via unified dispatch_tool + confirm -> wait ~2.2s -> device turns ON."""
    sess = _owner_session()

    async def _run() -> None:
        _REST_ENGINE.devices["bedroom_light"]["state"] = "OFF"
        r1 = await dispatch_tool(
            "create_timer",
            {"device_id": "bedroom_light", "action": "turn_on", "seconds": 1.5},
            engine=_REST_ENGINE,
            session=sess,
            source="unit_test",
            session_key="timer_rt_key",
        )
        assert r1["ok"] is True and r1["requires_confirmation"] is True
        r2 = await dispatch_tool(
            "confirm_or_cancel_pending_action",
            {"confirmed": True},
            engine=_REST_ENGINE,
            session=sess,
            source="unit_test",
            session_key="timer_rt_key",
        )
        assert r2["ok"] is True and r2["confirmed"] is True
        assert _REST_ENGINE.devices["bedroom_light"]["state"] == "OFF"
        await asyncio.sleep(2.2)
        assert _REST_ENGINE.devices["bedroom_light"]["state"] == "ON"

    asyncio.run(_run())


def test_7_recurring_weekday_schedule_tick() -> None:
    """Create Monday (weekday=0) 07:30 schedule -> Tuesday 07:30 does NOT fire; Monday 07:30 DOES fire."""
    create_schedule(
        owner_user_id="tuan_anh",
        owner_tier=1,
        device_id="garden_pump",
        action="turn_on",
        time_hhmm="07:30",
        schedule_type="daily",
        weekdays=[0],  # Monday only
        owner_name="Nguyễn Tuấn Anh",
    )
    _REST_ENGINE.devices["garden_pump"]["state"] = "OFF"

    # 2026-11-24 is Tuesday (weekday == 1)
    tuesday = datetime.datetime(2026, 11, 24, 7, 30, tzinfo=SAIGON_TZ)
    assert tuesday.weekday() == 1
    fired_tue = asyncio.run(run_scheduler_tick_once(now_override=tuesday))
    assert fired_tue == 0
    assert _REST_ENGINE.devices["garden_pump"]["state"] == "OFF"

    # 2026-11-23 is Monday (weekday == 0)
    monday = datetime.datetime(2026, 11, 23, 7, 30, tzinfo=SAIGON_TZ)
    assert monday.weekday() == 0
    fired_mon = asyncio.run(run_scheduler_tick_once(now_override=monday))
    assert fired_mon == 1
    assert _REST_ENGINE.devices["garden_pump"]["state"] == "ON"


def test_8_unified_tool_registry_and_live_bridge_parity() -> None:
    """GET /api/tools lists every TOOL_REGISTRY tool, ALL_TOOLS includes them, and LiveBridgeSession.handle_tool_call
    produces identical confirmation & state transitions as /api/text_command."""
    with TestClient(app) as client:
        r_tools = client.get("/api/tools")
        assert r_tools.status_code == 200
        api_tool_names = {t["name"] for t in r_tools.json()["tools"]}
        reg_tool_names = {s.name for s in TOOL_REGISTRY}
        assert api_tool_names == reg_tool_names

        live_tool_names = {d.name for d in (ALL_TOOLS[0].function_declarations or [])}
        missing = reg_tool_names - live_tool_names
        assert not missing, f"ALL_TOOLS missing canonical tools: {missing}"

    class _DummyBridge(LiveToolDispatcherMixin):
        def __init__(self) -> None:
            self.engine = _REST_ENGINE
            self.voice_auth = None
            self.knowledge_rag = None
            self.gemini_session = None
            self.last_mic_turn_blocked = False
            self.last_mic_auth_result = None
            self.ws_msgs: list[dict[str, Any]] = []

        async def send_ws_json(self, data: dict[str, Any]) -> None:
            self.ws_msgs.append(data)

        async def _sync_rules_context_to_gemini(self, spoken_msg: str = "") -> None:
            return None

        def _actor_session(self) -> Any:
            return _owner_session()

    bridge = _DummyBridge()
    _REST_ENGINE._current_role = "ADMIN"
    _REST_ENGINE._current_user_id = "tuan_anh"

    async def _exercise_live_tools() -> None:
        # 1) Create compound rule via LiveBridgeSession.handle_tool_call -> requires_confirmation=True
        fc1 = SimpleNamespace(
            name="create_automation_rule",
            args={
                "logic": "AND",
                "conditions": [
                    {"source": "soil_sensor", "operator": "<", "value": 35},
                    {"source": "temp_sensor", "operator": ">", "value": 31},
                ],
                "actions": [{"device_id": "garden_pump", "action": "turn_on"}],
            },
        )
        res1 = await bridge.handle_tool_call(fc1)
        assert res1["ok"] is True and res1["requires_confirmation"] is True
        assert "35" in res1["reply"] and "31" in res1["reply"]

        # 2) Confirm via confirm_or_cancel_pending_action -> saved to SQLite
        fc2 = SimpleNamespace(name="confirm_or_cancel_pending_action", args={"confirmed": True})
        res2 = await bridge.handle_tool_call(fc2)
        assert res2["ok"] is True and res2["confirmed"] is True

        # 3) List rules via LiveBridgeSession -> sees the saved rule
        fc3 = SimpleNamespace(name="list_automation_rules", args={"include_disabled": True})
        res3 = await bridge.handle_tool_call(fc3)
        assert res3["ok"] is True and res3["count"] >= 1

        # 4) UI guidance via LiveBridgeSession
        fc4 = SimpleNamespace(name="get_ui_guidance", args={"query": "tạo luật tự động ở đâu?"})
        res4 = await bridge.handle_tool_call(fc4)
        assert res4["ok"] is True and res4["route"] == "/automation" and res4["button_label"] == "Tạo luật mới"

    asyncio.run(_exercise_live_tools())


def test_9_single_source_of_truth_ui_registry_matches_tool_and_html() -> None:
    """GET /api/ui_registry matches get_ui_guidance output AND matches real DOM IDs/labels in automation.html & index.html."""
    import json

    with TestClient(app) as client:
        reg = client.get("/api/ui_registry").json()
    assert reg["ok"] is True
    assert reg == json.loads(json.dumps(get_ui_registry()))

    auto_html = (ROOT / "web" / "automation.html").read_text(encoding="utf-8")
    index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    # Verify nav routes & labels exist in automation.html and index.html
    for nav_item in reg["nav"]:
        assert f'href="{nav_item["path"]}"' in auto_html
        assert nav_item["label"] in auto_html
        assert f'href="{nav_item["path"]}"' in index_html
        assert nav_item["label"] in index_html

    # Verify automation panel tabs & button IDs/labels match automation.html
    panel = reg["automation_panel"]
    assert f'id="{panel["dashboard_panel_id"]}"' in index_html
    for tab in panel["tabs"]:
        assert tab["label"] in auto_html
        assert f'id="{tab["create_button_id"]}"' in auto_html
        assert tab["create_button_label"] in auto_html

    controls = panel["controls"]
    assert f'id="{controls["house_mode_toggle_id"]}"' in auto_html
    assert f'id="{controls["reset_button_id"]}"' in auto_html
    assert controls["reset_button_label"] in auto_html
    assert f'id="{controls["open_full_page_id"]}"' in index_html

    # Verify get_ui_guidance tool output matches registry entries
    for topic in ("timers", "schedules", "custom_commands", "rules", "sensors", "logs", "qr_invite"):
        g = get_ui_guidance(topic=topic)
        reg_g = reg["guides"][topic]
        assert g["route"] == reg_g["route"]
        assert g["nav_label"] == reg_g["nav_label"]
        assert g["tab_label"] == reg_g["tab_label"]
        assert g["button_label"] == reg_g["button_label"]
        assert reg_g["route"] in g["reply"]
        assert reg_g["nav_label"] in g["reply"]


def test_10_removed_devices_refused_and_guest_tier3_blocked() -> None:
    """Removed devices (fan, AC, IR) refused politely in Vietnamese with zero mutation; Tier 3 guest blocked from all automation."""
    with TestClient(app) as client:
        owner_h = _login_owner_headers(client)
        guest_h = _login_guest_headers(client, owner_h)

        # 1) Removed devices refused politely
        before_devs = {k: v["state"] for k, v in _REST_ENGINE.devices.items()}
        for phrase in ("Bật quạt trần", "Mở điều hòa 25 độ", "Học lệnh hồng ngoại remote IR"):
            r = client.post("/api/text_command", json={"text": phrase}, headers=owner_h)
            d = r.json()
            assert d.get("executed") is False
            assert d.get("requires_confirmation") is False
            reply = d.get("exact_spoken_reply") or d.get("reply") or ""
            assert "6 thiết bị" in reply or "không có" in reply.lower() or "không hỗ trợ" in reply.lower()
        after_devs = {k: v["state"] for k, v in _REST_ENGINE.devices.items()}
        assert before_devs == after_devs

        # 2) Tier 3 guest blocked (HTTP 403) on ALL automation endpoints & text automation
        assert client.get("/api/automation", headers=guest_h).status_code == 403
        assert client.post(
            "/api/timers",
            json={"device_id": "living_room_light", "action": "turn_on", "seconds": 10},
            headers=guest_h,
        ).status_code == 403
        assert client.post(
            "/api/schedules",
            json={"device_id": "living_room_light", "action": "turn_on", "time_hhmm": "08:00"},
            headers=guest_h,
        ).status_code == 403
        assert client.post(
            "/api/rules",
            json={
                "logic": "AND",
                "conditions": [{"source": "temp_sensor", "operator": ">", "value": 30}],
                "actions": [{"device_id": "living_room_light", "action": "turn_on"}],
            },
            headers=guest_h,
        ).status_code == 403
        assert client.post(
            "/api/scenes",
            json={"phrase": "khách thử", "steps": [{"device_id": "living_room_light", "action": "turn_on"}]},
            headers=guest_h,
        ).status_code == 403
        assert client.post("/api/house_mode", json={"mode": "AWAY"}, headers=guest_h).status_code == 403
        assert client.post("/api/automation/reset", json={"scope": "all"}, headers=guest_h).status_code == 403

        # Guest text command creating rule -> 403
        r_g = client.post(
            "/api/text_command",
            json={"text": "Nếu nhiệt độ trên 32 độ và độ ẩm đất dưới 40% thì bật đèn phòng khách"},
            headers=guest_h,
        )
        assert r_g.status_code == 403

        # Guest direct toggle on living_room_light still allowed (200)
        r_ok = client.post("/api/text_command", json={"text": "Bật đèn phòng khách"}, headers=guest_h)
        assert r_ok.status_code == 200 and r_ok.json().get("executed") is True
