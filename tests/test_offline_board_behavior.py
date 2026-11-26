"""Registry-Driven Unit & Integration Tests for Board Offline Behavior, Heartbeat Timeout,
HTTP 503 No-False-Success, Vietnamese Voice AI Replies, A4 Resync, and Cross-Layer Config Parity.

All device/action test matrices are generated dynamically from `DEFAULT_DEVICES`,
`DEVICE_CAPABILITIES`, `DEVICE_MIN_TIER`, and `offline_contract.py` (zero hardcoded device lists).
"""

from __future__ import annotations

import asyncio
import pathlib
import re
import time
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import backend.api.deps as api_deps
import backend.api.routes_devices as routes_devices
from backend.auth.session_store import UserSession, get_session_store
from backend.auth.tier_permissions import devices_visible_for_tier
from backend.engine.audit_logger import read_audit_logs
from backend.engine.board_health import (
    BOARD_STATUS_OFFLINE,
    BOARD_STATUS_ONLINE,
    BOARD_STATUS_VI_OFFLINE,
    BOARD_STATUS_VI_ONLINE,
    BoardHealthTracker,
)
from backend.engine.constants_and_time import (
    ACTION_VI_LABEL,
    DEFAULT_DEVICES,
    DEVICE_CAPABILITIES,
    STATE_TO_OPPOSITE,
    get_board_heartbeat_timeout_sec,
)
from backend.engine.offline_contract import (
    HEARTBEAT_INTERVAL_MS,
    OFFLINE_ALLOWED_DEVICE_ACTIONS,
    OFFLINE_AUTOMATION_MUTATION_ALLOWED,
    OFFLINE_CUSTOM_COMMANDS_ALLOWED,
    OFFLINE_FORBIDDEN_DEVICE_ACTIONS,
    OFFLINE_LED_CYCLE_MS,
    OFFLINE_ROLE_CHECK_ENABLED,
    OFFLINE_STATUS_QUERY_ALLOWED,
    PUMP_MAX_CONTINUOUS_RUN_MS,
    SERVER_BACKOFF_INITIAL_MS,
    SERVER_BACKOFF_MAX_MS,
    SERVER_BACKOFF_MULTIPLIER,
    SIREN_MAX_OFFLINE_RUN_MS,
    SPEAKER_AMP_IDLE_TAIL_MS,
    WIFI_BACKOFF_INITIAL_MS,
    WIFI_BACKOFF_MAX_MS,
    WIFI_BACKOFF_MULTIPLIER,
    format_device_offline_reply_vi,
    is_offline_action_allowed,
    is_offline_action_forbidden,
)
from backend.engine.state_store import (
    InMemoryStateBackend,
    get_default_state_backend,
    set_default_state_backend,
)
from backend.live.prompt_builder import build_system_instruction
from backend.live.tool_dispatcher_mixin import LiveToolDispatcherMixin
from backend.mqtt_bridge import ESP8266_PIN_MAP, SmartHomeMQTTBridge
from backend.realtime_hub import get_realtime_hub
from backend.rule_engine import SmartHomeEngine
from backend.server import app
from hardware.wiring_contract import FIRMWARE_PIN_CONTRACT
from tests.voice_policy.run_voice_journeys import verify_vietnamese_only_output

ROOT = pathlib.Path(__file__).resolve().parent.parent
HW_KEY_TEST = "test-hw-key-s2-offline"


def _all_device_action_pairs() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for dev_id in DEFAULT_DEVICES:
        for act in DEVICE_CAPABILITIES.get(dev_id, {}).get("actions", ("turn_on", "turn_off")):
            pairs.append((dev_id, act))
    return pairs


def _build_vi_command_from_registry(dev_id: str, action: str) -> str:
    dev_meta = DEFAULT_DEVICES[dev_id]
    verb = ACTION_VI_LABEL.get(action, action).lower()
    name = str(dev_meta["name"]).lower()
    return f"{verb} {name}"


def _assert_no_false_success_vi(reply: str, expected_dev_name: str | None = None) -> None:
    assert reply, "Reply must not be empty"
    ok_vi, reason = verify_vietnamese_only_output(reply, allow_empty=False)
    assert ok_vi, f"Reply must be 100% Vietnamese ({reason}): {reply!r}"
    low = reply.lower()
    assert "mất kết nối" in low, f"Expected 'mất kết nối' in offline reply: {reply!r}"
    for false_ok in ("đã bật", "đã tắt", "đã mở", "đã đóng", "đã thực hiện", "thành công"):
        assert false_ok not in low, f"False success phrase {false_ok!r} found in offline reply: {reply!r}"
    if expected_dev_name:
        assert expected_dev_name.lower() in low, f"Expected device name {expected_dev_name!r} in reply: {reply!r}"


class _DummyLiveDispatcher(LiveToolDispatcherMixin):
    def __init__(self, engine: SmartHomeEngine, session: UserSession) -> None:
        self.engine = engine
        self.voice_auth = None
        self.knowledge_rag = None
        self.gemini_session = None
        self.last_mic_turn_blocked = False
        self.last_mic_auth_result = None
        self._session = session
        self.ws_events: list[dict[str, Any]] = []

    def _resolve_ws_session(self) -> UserSession:
        return self._session

    def _bind_actor_to_engine(self) -> UserSession:
        self.engine._current_user_id = self._session.user_id
        self.engine._current_role = self._session.role
        return self._session

    async def send_ws_json(self, payload: dict[str, Any], **kwargs: Any) -> None:
        self.ws_events.append(payload)

    async def _sync_rules_context_to_gemini(self, msg: str) -> None:
        return None


def _make_tier_sessions() -> dict[int, UserSession]:
    store = get_session_store()
    tag = uuid.uuid4().hex[:8]
    return {
        1: store.create_session(
            user_id="tuan_anh",
            email=f"owner_{tag}@sandbox.local",
            display_name="Nguyễn Tuấn Anh",
            tier=1,
            role="ADMIN",
            source="offline_test",
            ttl_sec=3600,
        ),
        2: store.create_session(
            user_id="thanh_vien_a",
            email=f"member_{tag}@sandbox.local",
            display_name="Thành viên A",
            tier=2,
            role="MEMBER",
            source="offline_test",
            ttl_sec=3600,
        ),
        3: store.create_session(
            user_id="khach_c",
            email=f"guest_{tag}@sandbox.local",
            display_name="Khách C",
            tier=3,
            role="CHILD_GUEST",
            source="offline_test",
            ttl_sec=3600,
        ),
    }


def _reset_engine_devices_fast(eng: SmartHomeEngine) -> None:
    now_ts = time.time()
    eng._applying_shared_state_depth += 1
    eng._applying_shared_state = True
    try:
        for dev_id, meta in DEFAULT_DEVICES.items():
            if dev_id in eng.devices:
                eng.devices[dev_id]["state"] = str(meta["state"])
                eng.devices[dev_id]["version"] = 1
                eng.devices[dev_id]["updated_at"] = now_ts
                eng.devices[dev_id]["last_client_seq"] = 0
                eng.devices[dev_id]["last_client_ts_ms"] = 0
                eng.devices[dev_id]["last_client_id"] = ""
                eng.devices[dev_id]["client_seqs"] = {}
        eng.server_connected = True
        eng.pump_manual_override_off = False
        eng.house_mode = "HOME"
        bh = eng.board_health.detach(now=now_ts)
        eng.mqtt_bridge.sync_from_board_health(bh)
    finally:
        eng._applying_shared_state_depth = max(0, eng._applying_shared_state_depth - 1)
        eng._applying_shared_state = eng._applying_shared_state_depth > 0
    eng.persist_to_shared_store()


@pytest.fixture(autouse=True)
def isolated_offline_test_env(monkeypatch: pytest.MonkeyPatch):
    """Isolate state backend, heartbeat timeout, hardware API key, and clean up _REST_ENGINE."""
    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")
    monkeypatch.setenv("SMARTHOME_AOEDE_CACHE_ONLY", "1")
    monkeypatch.setenv("SMARTHOME_SKIP_STT_PRELOAD", "1")
    monkeypatch.setenv("SMARTHOME_HARDWARE_API_KEY", HW_KEY_TEST)
    monkeypatch.setenv("SMARTHOME_BOARD_HEARTBEAT_TIMEOUT_SEC", "5.0")

    prev_backend = get_default_state_backend()
    temp_backend = InMemoryStateBackend()
    set_default_state_backend(temp_backend)

    eng = routes_devices._REST_ENGINE
    eng.set_state_backend(temp_backend)
    eng.set_active_user("tuan_anh")
    _reset_engine_devices_fast(eng)

    yield eng

    eng.set_state_backend(None)
    set_default_state_backend(prev_backend)
    eng.set_active_user("tuan_anh")
    _reset_engine_devices_fast(eng)


# ==============================================================================
# (a) & (b) HEARTBEAT LIVENESS, TIMEOUT TRANSITION, LWT & SNAPSHOT ENRICHMENT
# ==============================================================================


def test_heartbeat_timeout_config_dynamic_and_minimum_clamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMARTHOME_BOARD_HEARTBEAT_TIMEOUT_SEC", "12.5")
    assert get_board_heartbeat_timeout_sec() == 12.5

    monkeypatch.setenv("SMARTHOME_BOARD_HEARTBEAT_TIMEOUT_SEC", "0.2")
    assert get_board_heartbeat_timeout_sec() == 1.0

    monkeypatch.setenv("SMARTHOME_BOARD_HEARTBEAT_TIMEOUT_SEC", "not-a-number")
    assert get_board_heartbeat_timeout_sec() == 30.0


def test_heartbeat_keeps_board_online_and_timeout_marks_mat_ket_noi(
    isolated_offline_test_env: SmartHomeEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SMARTHOME_BOARD_HEARTBEAT_TIMEOUT_SEC", "5.0")
    client = TestClient(app)
    sessions = _make_tier_sessions()

    # Unauthenticated heartbeat -> 401; Cap 2 / Cap 3 -> 403
    assert client.post("/api/hardware/heartbeat", json={}).status_code == 401
    assert client.post(
        "/api/hardware/heartbeat",
        headers={"X-Session-Token": sessions[2].session_id},
        json={},
    ).status_code == 403
    assert client.post(
        "/api/hardware/heartbeat",
        headers={"X-Session-Token": sessions[3].session_id},
        json={},
    ).status_code == 403

    # Valid hardware key heartbeat keeps board online
    r_hb = client.post(
        "/api/hardware/heartbeat",
        headers={"X-Hardware-Key": HW_KEY_TEST},
        json={"node_id": "esp8266_node_01", "wifi_rssi_dbm": -48, "uptime_ms": 9876, "firmware_mode": "ONLINE"},
    )
    assert r_hb.status_code == 200
    hb_body = r_hb.json()
    assert hb_body["ok"] is True
    assert hb_body["board_health"]["online"] is True
    assert hb_body["board_health"]["status"] == BOARD_STATUS_ONLINE
    assert hb_body["board_health"]["status_vi"] == BOARD_STATUS_VI_ONLINE
    assert hb_body["board_health"]["wifi_rssi_dbm"] == -48
    assert re.match(r"^\d{2}:\d{2}:\d{2} \d{2}/\d{2}/\d{4}$", hb_body["board_health"]["last_seen_vi"])

    # Simulate timeout past SMARTHOME_BOARD_HEARTBEAT_TIMEOUT_SEC
    eng = isolated_offline_test_env
    eng.board_health.last_seen = time.time() - 10.0
    transition, bh_off = eng.check_board_heartbeat_transition()
    assert transition == "ONLINE_TO_OFFLINE"
    assert bh_off["online"] is False
    assert bh_off["status"] == BOARD_STATUS_OFFLINE
    assert bh_off["status_vi"] == BOARD_STATUS_VI_OFFLINE
    assert bh_off["offline_since"] is not None
    assert re.match(r"^\d{2}:\d{2}:\d{2} \d{2}/\d{2}/\d{4}$", bh_off["last_seen_vi"])

    # Audit log recorded board_heartbeat_timeout
    logs = read_audit_logs(limit=25)
    assert any(entry.get("event_type") == "board_heartbeat_timeout" for entry in logs)

    # GET /api/state exposes board_health and enriched per-device connectivity fields across all tiers
    for tier in (1, 2, 3):
        r_st = client.get("/api/state", headers={"X-Session-Token": sessions[tier].session_id})
        assert r_st.status_code == 200
        st = r_st.json()
        assert st["board_health"]["online"] is False
        assert st["board_health"]["status"] == BOARD_STATUS_OFFLINE
        assert st["board_health"]["status_vi"] == BOARD_STATUS_VI_OFFLINE
        expected_ids = set(devices_visible_for_tier(tier))
        got_ids = {d["id"] for d in st["devices"]}
        assert got_ids == expected_ids
        for dev in st["devices"]:
            assert dev["board_online"] is False
            assert dev["connectivity_status"] == BOARD_STATUS_OFFLINE
            assert dev["connectivity_label_vi"] == BOARD_STATUS_VI_OFFLINE
            assert dev["last_seen"] > 0
            assert dev["last_seen_vi"] == bh_off["last_seen_vi"]

    # Recovery via heartbeat
    r_rec = client.post(
        "/api/hardware/heartbeat",
        headers={"X-Hardware-Key": HW_KEY_TEST},
        json={"node_id": "esp8266_node_01", "wifi_rssi_dbm": -51},
    )
    assert r_rec.status_code == 200
    assert r_rec.json()["recovered"] is True
    assert r_rec.json()["board_health"]["online"] is True
    assert r_rec.json()["board_health"]["status_vi"] == BOARD_STATUS_VI_ONLINE


def test_lwt_offline_and_telemetry_refresh_last_seen(isolated_offline_test_env: SmartHomeEngine) -> None:
    client = TestClient(app)
    r_lwt = client.post(
        "/api/hardware/lwt",
        headers={"X-Hardware-Key": HW_KEY_TEST},
        json={"node_id": "esp8266_node_01", "online": False},
    )
    assert r_lwt.status_code == 200
    assert r_lwt.json()["board_health"]["online"] is False
    assert r_lwt.json()["board_health"]["status_vi"] == BOARD_STATUS_VI_OFFLINE
    assert isolated_offline_test_env.is_board_online() is False

    # Hardware telemetry endpoints recover connectivity and refresh last_seen
    for path, payload in (
        ("/api/dht11", {"temp_c": 29.0, "humidity_pct": 60.0, "wifi_rssi_dbm": -49}),
        ("/api/soil_moisture", {"soil_moisture_pct": 55.0}),
        ("/api/sound_sensor", {"sound_detected": False}),
    ):
        client.post(
            "/api/hardware/lwt",
            headers={"X-Hardware-Key": HW_KEY_TEST},
            json={"node_id": "esp8266_node_01", "online": False},
        )
        assert isolated_offline_test_env.is_board_online() is False
        r_tel = client.post(path, headers={"X-Hardware-Key": HW_KEY_TEST}, json=payload)
        assert r_tel.status_code == 200
        assert isolated_offline_test_env.is_board_online() is True


# ==============================================================================
# (c) HTTP 503 NO-FALSE-SUCCESS FOR EVERY DEVICE IN DEFAULT_DEVICES
# ==============================================================================


@pytest.mark.parametrize("dev_id,action", _all_device_action_pairs())
def test_rest_device_control_returns_503_and_zero_mutation_when_board_offline(
    isolated_offline_test_env: SmartHomeEngine,
    dev_id: str,
    action: str,
) -> None:
    client = TestClient(app)
    sessions = _make_tier_sessions()
    eng = isolated_offline_test_env

    # Record baseline state & version before marking board offline
    before_state = str(eng.devices[dev_id]["state"])
    before_version = int(eng.devices[dev_id].get("version", 1))

    # Force board offline via timeout (after hardware has attached)
    eng.record_board_heartbeat(node_id="esp8266_node_01", persist=False)
    eng.board_health.last_seen = time.time() - (get_board_heartbeat_timeout_sec() + 5.0)
    eng.persist_to_shared_store()

    resp = client.post(
        "/api/device",
        headers={"X-Session-Token": sessions[1].session_id},
        json={"device_id": dev_id, "action": action, "source": "web_dashboard"},
    )
    assert resp.status_code == 503, f"Expected 503 for {dev_id}/{action}, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["ok"] is False
    assert body["executed"] is False
    assert body["board_offline"] is True
    assert body["delivery_status"] == "BOARD_OFFLINE"
    assert body["board_health"]["online"] is False
    assert body["last_seen_vi"]
    _assert_no_false_success_vi(str(body.get("exact_spoken_reply") or ""), DEFAULT_DEVICES[dev_id]["name"])
    _assert_no_false_success_vi(str(body.get("reply") or ""), DEFAULT_DEVICES[dev_id]["name"])
    _assert_no_false_success_vi(str(body.get("error") or ""), DEFAULT_DEVICES[dev_id]["name"])

    # Verify ZERO state mutation
    assert str(eng.devices[dev_id]["state"]) == before_state
    assert int(eng.devices[dev_id].get("version", 1)) == before_version


def test_mqtt_bridge_never_fabricates_ack_when_board_offline() -> None:
    bridge = SmartHomeMQTTBridge()
    bridge.esp8266_status["online"] = False
    bridge.esp8266_status["lwt_online"] = False

    async def _run():
        before_count = len(bridge.recent_messages)
        for dev_id, dev_meta in DEFAULT_DEVICES.items():
            res = await bridge.publish_actuate_command(
                device_id=dev_id,
                state=STATE_TO_OPPOSITE.get(str(dev_meta["state"]), "ON"),
                action="turn_on",
                source="test",
                user_name="Nguyễn Tuấn Anh",
                tier=1,
            )
            assert res.get("ok") is False
            assert res.get("board_offline") is True
            assert res.get("ack") is False
            assert res.get("delivery_status") == "BOARD_OFFLINE"
        assert len(bridge.recent_messages) == before_count

    asyncio.run(_run())


# ==============================================================================
# (d) VOICE AI (/api/text_command + GEMINI LIVE set_device) ACROSS CAP 1, 2, 3
# ==============================================================================


@pytest.mark.parametrize("tier", [1, 2, 3])
def test_text_command_and_gemini_live_offline_replies_across_tiers(
    isolated_offline_test_env: SmartHomeEngine,
    tier: int,
) -> None:
    client = TestClient(app)
    sessions = _make_tier_sessions()
    sess = sessions[tier]
    eng = isolated_offline_test_env

    # Mark board offline via explicit LWT
    r_lwt = client.post(
        "/api/hardware/lwt",
        headers={"X-Hardware-Key": HW_KEY_TEST},
        json={"node_id": "esp8266_node_01", "online": False},
    )
    assert r_lwt.status_code == 200

    allowed_ids = devices_visible_for_tier(tier)
    assert allowed_ids, f"Tier {tier} should have at least one visible device"

    dispatcher = _DummyLiveDispatcher(eng, sess)
    for dev_id in allowed_ids:
        dev_meta = DEFAULT_DEVICES[dev_id]
        actions = DEVICE_CAPABILITIES[dev_id]["actions"]
        act = actions[0]
        cmd_text = _build_vi_command_from_registry(dev_id, act)
        before_state = str(eng.devices[dev_id]["state"])

        # 1. REST /api/text_command
        r_txt = client.post(
            "/api/text_command",
            headers={"X-Session-Token": sess.session_id},
            json={"text": cmd_text},
        )
        assert r_txt.status_code == 503, (
            f"Tier {tier} /api/text_command {cmd_text!r} expected 503, got {r_txt.status_code}: {r_txt.text}"
        )
        txt_body = r_txt.json()
        assert txt_body["ok"] is False
        assert txt_body["executed"] is False
        assert txt_body["board_offline"] is True
        assert txt_body["delivery_status"] == "BOARD_OFFLINE"
        _assert_no_false_success_vi(str(txt_body.get("exact_spoken_reply") or ""), dev_meta["name"])
        assert str(eng.devices[dev_id]["state"]) == before_state

        # 2. Gemini Live set_device tool call
        fc = SimpleNamespace(name="set_device", args={"device_id": dev_id, "action": act})
        live_res = asyncio.run(dispatcher.handle_tool_call(fc))
        assert live_res["ok"] is False
        assert live_res["executed"] is False
        assert live_res["board_offline"] is True
        assert live_res["status_code"] == 503
        _assert_no_false_success_vi(str(live_res.get("exact_spoken_reply") or ""), dev_meta["name"])
        assert str(eng.devices[dev_id]["state"]) == before_state

        # 3. Gemini Live control_device tool call
        fc_ctrl = SimpleNamespace(name="control_device", args={"device_id": dev_id, "action": act})
        ctrl_res = asyncio.run(dispatcher.handle_tool_call(fc_ctrl))
        assert ctrl_res["ok"] is False
        assert ctrl_res["executed"] is False
        assert ctrl_res["board_offline"] is True
        assert ctrl_res["status_code"] == 503
        _assert_no_false_success_vi(str(ctrl_res.get("exact_spoken_reply") or ""), dev_meta["name"])
        assert str(eng.devices[dev_id]["state"]) == before_state

    # Verify list_devices, get_device_state, and build_system_instruction report offline state accurately
    list_res = asyncio.run(dispatcher.handle_tool_call(SimpleNamespace(name="list_devices", args={})))
    assert list_res["ok"] is True
    assert list_res["board_health"]["online"] is False
    assert "mất kết nối" in list_res["summary_vi"].lower()

    first_dev = allowed_ids[0]
    get_res = asyncio.run(
        dispatcher.handle_tool_call(SimpleNamespace(name="get_device_state", args={"device_id": first_dev}))
    )
    assert get_res["ok"] is True
    assert get_res["device"]["board_online"] is False
    assert get_res["device"]["connectivity_label_vi"] == BOARD_STATUS_VI_OFFLINE

    prompt = build_system_instruction(eng)
    assert BOARD_STATUS_VI_OFFLINE in prompt
    assert "board_offline=True" in prompt

    # Devices forbidden by RBAC for Cap 2 / Cap 3 must still reject with 403 (never claim success)
    for forbidden_id in [d for d in DEFAULT_DEVICES if d not in allowed_ids]:
        act = DEVICE_CAPABILITIES[forbidden_id]["actions"][0]
        cmd_forb = _build_vi_command_from_registry(forbidden_id, act)
        r_forb = client.post(
            "/api/text_command",
            headers={"X-Session-Token": sess.session_id},
            json={"text": cmd_forb},
        )
        assert r_forb.status_code == 403
        assert r_forb.json()["ok"] is False
        assert r_forb.json()["rbac_blocked"] is True


@pytest.mark.parametrize("tier", [2, 3])
def test_ws_aoede_speak_denial_allowed_for_authenticated_cap2_cap3_and_blocked_for_unauth(
    isolated_offline_test_env: SmartHomeEngine,
    tier: int,
) -> None:
    """DEFECT-S2-01: Authenticated Cap 2/3 WS aoede_speak_denial must not emit rbac_blocked; unauth must stay blocked."""
    import json
    from fastapi import WebSocketDisconnect
    from backend.live.gemini_bridge import LiveBridgeSession

    eng = isolated_offline_test_env
    sessions = _make_tier_sessions()
    sess = sessions[tier]

    dev_id = devices_visible_for_tier(tier)[0]
    offline_bh = BoardHealthTracker()
    offline_bh.record_lwt(online=False)
    spoken_offline = format_device_offline_reply_vi(DEFAULT_DEVICES[dev_id], offline_bh.evaluate_board_health())

    async def _run_ws(ws_session: UserSession) -> list[dict[str, Any]]:
        sent_frames: list[dict[str, Any]] = []
        incoming = [json.dumps({"type": "aoede_speak_denial", "text": spoken_offline})]

        fake_ws = AsyncMock()
        fake_ws.headers = {}
        fake_ws.cookies = {}
        fake_ws.query_params = {}

        async def _recv_text() -> str:
            if incoming:
                return incoming.pop(0)
            raise WebSocketDisconnect(code=1000)

        async def _send_text(raw: str) -> None:
            sent_frames.append(json.loads(raw))

        fake_ws.receive_text = AsyncMock(side_effect=_recv_text)
        fake_ws.send_text = AsyncMock(side_effect=_send_text)

        bridge = LiveBridgeSession(
            ws=fake_ws,
            engine=eng.create_isolated_ws_view(),
            ws_session=ws_session,
        )
        await bridge.run()
        return sent_frames

    # 1. Authenticated Cap 2 / Cap 3 session -> allowed, emits aoede_voice_request, ZERO rbac_blocked
    auth_frames = asyncio.run(_run_ws(sess))
    assert not any(
        f.get("type") == "rbac_blocked" and f.get("action") == "aoede_speak_denial"
        for f in auth_frames
    ), f"Unexpected rbac_blocked for authenticated Cap {tier}: {auth_frames}"
    aoede_reqs = [f for f in auth_frames if f.get("type") == "aoede_voice_request"]
    assert aoede_reqs, f"Expected aoede_voice_request for authenticated Cap {tier}: {auth_frames}"
    assert aoede_reqs[0].get("spoken_phrase") == spoken_offline

    # 2. Unauthenticated / UNKNOWN session -> MUST remain strictly blocked with rbac_blocked
    unauth_sess = UserSession(
        session_id="ws_unauth_defect_s2_01",
        user_id="unknown",
        email="",
        display_name="Người lạ",
        tier=99,
        role="UNKNOWN",
        created_at=time.time(),
        expires_at=time.time() + 3600,
        source="unauthenticated",
        is_authenticated=False,
    )
    unauth_frames = asyncio.run(_run_ws(unauth_sess))
    assert any(
        f.get("type") == "rbac_blocked" and f.get("action") == "aoede_speak_denial"
        for f in unauth_frames
    ), f"Expected rbac_blocked for unauthenticated session: {unauth_frames}"
    assert not any(f.get("type") == "aoede_voice_request" for f in unauth_frames)


# ==============================================================================
# (e) ADDENDUM A4: BOARD-AUTHORITATIVE AUTOMATIC RECONNECT RESYNC + AUDIT LOG
# ==============================================================================


def test_hardware_resync_adopts_offline_physical_states_and_writes_audit_log(
    isolated_offline_test_env: SmartHomeEngine,
) -> None:
    client = TestClient(app)
    sessions = _make_tier_sessions()
    eng = isolated_offline_test_env

    # 1. Board goes offline
    r_lwt = client.post(
        "/api/hardware/lwt",
        headers={"X-Hardware-Key": HW_KEY_TEST},
        json={"node_id": "esp8266_node_01", "online": False},
    )
    assert r_lwt.status_code == 200
    assert eng.is_board_online() is False

    # 2. Construct board-reported physical states dynamically from offline_contract & DEFAULT_DEVICES
    reported_states: dict[str, str] = {}
    offline_changed: list[str] = []
    offline_events: list[dict[str, Any]] = []
    for idx, (dev_id, dev_meta) in enumerate(DEFAULT_DEVICES.items()):
        if is_offline_action_allowed(dev_id, "turn_on") and str(dev_meta.get("type")) != "door":
            # Flip odd/even subset so both changed and unchanged devices are tested dynamically
            if idx % 2 == 1:
                reported_states[dev_id] = "ON"
                offline_changed.append(dev_id)
                offline_events.append({
                    "device_id": dev_id,
                    "state": "ON",
                    "reason": "offline_voice",
                    "offset_ms": 1500 * (idx + 1),
                })
            else:
                reported_states[dev_id] = str(dev_meta["state"])
        else:
            reported_states[dev_id] = str(dev_meta["state"])

    assert offline_changed, "Expected at least one offline-changed device from DEFAULT_DEVICES"

    resync_payload = {
        "node_id": "esp8266_node_01",
        "offline_duration_ms": 18500,
        "wifi_rssi_dbm": -54,
        "device_states": reported_states,
        "offline_changed_devices": offline_changed,
        "offline_events": offline_events,
        "sensors": {
            "temp_c": 31.2,
            "humidity_pct": 58.0,
            "soil_moisture_pct": 47.0,
            "sound_detected": True,
        },
    }

    r_sync = client.post(
        "/api/hardware/resync",
        headers={"X-Hardware-Key": HW_KEY_TEST},
        json=resync_payload,
    )
    assert r_sync.status_code == 200, r_sync.text
    body = r_sync.json()
    assert body["ok"] is True
    assert body["resynced"] is True
    assert body["board_health"]["online"] is True
    assert body["board_health"]["status"] == BOARD_STATUS_ONLINE
    assert body["board_health"]["status_vi"] == BOARD_STATUS_VI_ONLINE
    assert body["board_health"]["offline_resync_count"] >= 1
    assert set(body["board_health"]["last_resync_changed_devices"]) == set(offline_changed)

    adopted_ids = {c["device_id"] for c in body["adopted_changes"]}
    assert adopted_ids == set(offline_changed)
    for ch in body["adopted_changes"]:
        assert ch["old_state"] == DEFAULT_DEVICES[ch["device_id"]]["state"]
        assert ch["new_state"] == reported_states[ch["device_id"]]

    # Verify GET /api/state immediately reflects adopted physical states + updated sensors + ONLINE status
    r_state = client.get("/api/state", headers={"X-Session-Token": sessions[1].session_id})
    assert r_state.status_code == 200
    snap = r_state.json()
    assert snap["board_health"]["online"] is True
    snap_dev_map = {d["id"]: d for d in snap["devices"]}
    for dev_id, expected_state in reported_states.items():
        assert snap_dev_map[dev_id]["state"] == expected_state
        assert snap_dev_map[dev_id]["board_online"] is True
        assert snap_dev_map[dev_id]["connectivity_label_vi"] == BOARD_STATUS_VI_ONLINE
    assert snap["sensors"]["temperature_c"] == 31.2
    assert snap["sensors"]["humidity_pct"] == 58.0
    assert snap["sensors"]["soil_moisture_pct"] == 47.0
    assert snap["sensors"]["sound_detected"] is True

    # Verify structured audit log entry board_offline_resync
    logs = read_audit_logs(limit=25)
    resync_logs = [
        entry for entry in logs
        if entry.get("category") == "DEVICE_IO" and entry.get("event_type") == "board_offline_resync"
    ]
    assert resync_logs, "Expected DEVICE_IO / board_offline_resync audit log entry"
    latest = resync_logs[-1]
    details = latest.get("details") or {}
    assert details.get("offline_duration_ms") == 18500
    assert set(details.get("offline_changed_devices") or []) == set(offline_changed)
    assert len(details.get("adopted_changes") or []) == len(offline_changed)
    assert len(details.get("offline_events") or []) == len(offline_events)


def test_realtime_hub_receives_sse_push_on_timeout_and_resync(
    isolated_offline_test_env: SmartHomeEngine,
) -> None:
    """Verify SSE subscribers immediately receive board_health transitions on timeout & A4 resync."""
    eng = isolated_offline_test_env
    sessions = _make_tier_sessions()
    hub = get_realtime_hub()

    async def _run_check() -> None:
        loop = asyncio.get_running_loop()
        sub = hub.register(sessions[1], loop=loop)
        try:
            # 1. Timeout transition pushes OFFLINE snapshot (after hardware has attached)
            eng.record_board_heartbeat(node_id="esp8266_node_01", persist=False)
            eng.board_health.last_seen = time.time() - (get_board_heartbeat_timeout_sec() + 5.0)
            transition, _bh = eng.check_board_heartbeat_transition()
            assert transition == "ONLINE_TO_OFFLINE"
            await api_deps.broadcast_rest_state_to_bridges(sync_engine=False)
            await asyncio.sleep(0.05)

            events_off: list[str] = []
            while not sub.queue.empty():
                events_off.append(sub.queue.get_nowait())
            assert events_off, "Expected SSE push on ONLINE -> OFFLINE timeout"
            assert any(BOARD_STATUS_VI_OFFLINE in ev for ev in events_off)

            # 2. A4 resync pushes ONLINE snapshot with adopted physical state
            non_door_id = next(d for d, m in DEFAULT_DEVICES.items() if m["type"] != "door")
            eng.apply_hardware_resync(
                {
                    "node_id": "esp8266_node_01",
                    "offline_duration_ms": 9000,
                    "device_states": {non_door_id: "ON"},
                    "offline_changed_devices": [non_door_id],
                }
            )
            await api_deps.broadcast_rest_state_to_bridges(sync_engine=False)
            await asyncio.sleep(0.05)

            events_on: list[str] = []
            while not sub.queue.empty():
                events_on.append(sub.queue.get_nowait())
            assert events_on, "Expected SSE push on A4 hardware resync"
            assert any(BOARD_STATUS_VI_ONLINE in ev and f'"{non_door_id}"' in ev for ev in events_on)
        finally:
            hub.unregister(sub.sub_id)

    asyncio.run(_run_check())


# ==============================================================================
# (f) SINGLE-CONFIG CROSS-LAYER PARITY (backend <-> wiring_contract <-> firmware)
# ==============================================================================


def test_offline_contract_parity_with_registry_wiring_and_firmware_header() -> None:
    # 1. Parity with DEFAULT_DEVICES & Addendum A2/A3 policy
    assert OFFLINE_ROLE_CHECK_ENABLED is False
    assert OFFLINE_CUSTOM_COMMANDS_ALLOWED is False
    assert OFFLINE_AUTOMATION_MUTATION_ALLOWED is False
    assert OFFLINE_STATUS_QUERY_ALLOWED is True
    assert set(OFFLINE_ALLOWED_DEVICE_ACTIONS.keys()) == set(DEFAULT_DEVICES.keys())
    assert OFFLINE_FORBIDDEN_DEVICE_ACTIONS == {"main_door": ("open",)}

    for dev_id, dev_meta in DEFAULT_DEVICES.items():
        if dev_meta["type"] == "door":
            assert is_offline_action_forbidden(dev_id, "open") is True
            assert is_offline_action_allowed(dev_id, "open") is False
            assert is_offline_action_allowed(dev_id, "close") is True
        else:
            for act in DEVICE_CAPABILITIES[dev_id]["actions"]:
                assert is_offline_action_allowed(dev_id, act) is True
                assert is_offline_action_forbidden(dev_id, act) is False

        # Dynamic reply formatter derives name purely from device_record + board_health
        sample_bh = BoardHealthTracker().evaluate_board_health()
        reply = format_device_offline_reply_vi(dev_meta, sample_bh)
        _assert_no_false_success_vi(reply, dev_meta["name"])
        assert sample_bh["last_seen_vi"] in reply

    # 2. Parity with hardware/wiring_contract.py (6 actuators pin/GPIO lock)
    fw_key_by_device = {
        "living_room_light": "PIN_LIVING_LIGHT",
        "main_door": "PIN_MAIN_DOOR_SERVO",
        "bedroom_light": "PIN_BEDROOM_LIGHT",
        "garden_pump": "PIN_GARDEN_PUMP",
        "speaker_amp": "PIN_SPEAKER_AMP",
        "alarm_siren": "PIN_ALARM_SIREN",
    }
    assert set(fw_key_by_device.keys()) == set(DEFAULT_DEVICES.keys()) == set(ESP8266_PIN_MAP.keys())
    for dev_id, fw_key in fw_key_by_device.items():
        pin_name, gpio_num, _ = FIRMWARE_PIN_CONTRACT[fw_key]
        assert ESP8266_PIN_MAP[dev_id]["pin"] == pin_name
        assert ESP8266_PIN_MAP[dev_id]["gpio"] == gpio_num
        assert f"{pin_name} / GPIO{gpio_num}" in DEFAULT_DEVICES[dev_id]["gpio"]

    # 3. Parity with firmware/esp8266_smarthome/offline_safety_config.h when present
    hdr_path = ROOT / "firmware" / "esp8266_smarthome" / "offline_safety_config.h"
    if hdr_path.exists():
        hdr_text = hdr_path.read_text(encoding="utf-8")

        def _extract_cpp_int(const_name: str) -> int:
            m = re.search(rf"\b{re.escape(const_name)}\s*=\s*(\d+)[uUlL]*\s*;", hdr_text)
            assert m is not None, f"Missing C++ constant {const_name} in {hdr_path}"
            return int(m.group(1))

        def _extract_cpp_bool(const_name: str) -> bool:
            m = re.search(rf"\b{re.escape(const_name)}\s*=\s*(true|false)\s*;", hdr_text)
            assert m is not None, f"Missing C++ bool {const_name} in {hdr_path}"
            return m.group(1) == "true"

        assert _extract_cpp_bool("OFFLINE_ROLE_CHECK_ENABLED") == OFFLINE_ROLE_CHECK_ENABLED
        assert _extract_cpp_bool("OFFLINE_CUSTOM_COMMANDS_ALLOWED") == OFFLINE_CUSTOM_COMMANDS_ALLOWED
        assert _extract_cpp_bool("OFFLINE_AUTOMATION_MUTATION_ALLOWED") == OFFLINE_AUTOMATION_MUTATION_ALLOWED
        assert _extract_cpp_bool("OFFLINE_STATUS_QUERY_ALLOWED") == OFFLINE_STATUS_QUERY_ALLOWED
        assert _extract_cpp_bool("OFFLINE_MAIN_DOOR_OPEN_ALLOWED") is False

        assert _extract_cpp_int("PUMP_MAX_CONTINUOUS_RUN_MS") == PUMP_MAX_CONTINUOUS_RUN_MS
        assert _extract_cpp_int("SIREN_MAX_OFFLINE_RUN_MS") == SIREN_MAX_OFFLINE_RUN_MS
        assert _extract_cpp_int("SPEAKER_AMP_IDLE_TAIL_DEFAULT_MS") == SPEAKER_AMP_IDLE_TAIL_MS
        assert _extract_cpp_int("WIFI_BACKOFF_INITIAL_MS") == WIFI_BACKOFF_INITIAL_MS
        assert _extract_cpp_int("WIFI_BACKOFF_MAX_MS") == WIFI_BACKOFF_MAX_MS
        assert _extract_cpp_int("WIFI_BACKOFF_MULTIPLIER") == WIFI_BACKOFF_MULTIPLIER
        assert _extract_cpp_int("SERVER_BACKOFF_INITIAL_MS") == SERVER_BACKOFF_INITIAL_MS
        assert _extract_cpp_int("SERVER_BACKOFF_MAX_MS") == SERVER_BACKOFF_MAX_MS
        assert _extract_cpp_int("SERVER_BACKOFF_MULTIPLIER") == SERVER_BACKOFF_MULTIPLIER
        assert _extract_cpp_int("HEARTBEAT_INTERVAL_MS") == HEARTBEAT_INTERVAL_MS
        assert _extract_cpp_int("OFFLINE_LED_CYCLE_MS") == OFFLINE_LED_CYCLE_MS

        for dev_id in DEFAULT_DEVICES:
            assert f'"{dev_id}"' in hdr_text, f"Missing device_id {dev_id!r} in {hdr_path}"


# ==============================================================================
# (g) S2 REVIEW MUST_FIX REGRESSION TESTS (COLD START, DETACH, 503 VOICE/NLU/WS)
# ==============================================================================


def test_boardless_cold_start_stays_online_past_timeout_and_strict_env_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S2-MF-1: Board-less cold start must stay ONLINE past heartbeat timeout unless opt-in env is set."""
    monkeypatch.delenv("SMARTHOME_REQUIRE_BOARD_HEARTBEAT", raising=False)
    monkeypatch.setenv("SMARTHOME_BOARD_HEARTBEAT_TIMEOUT_SEC", "5.0")

    t0 = 1_700_000_000.0
    tracker = BoardHealthTracker(now=t0)
    assert tracker.hardware_attached is False

    # 120s later (> 5s timeout), board-less prod stays ONLINE with zero transition
    bh_later = tracker.evaluate_board_health(now=t0 + 120.0)
    assert bh_later["online"] is True
    assert bh_later["hardware_attached"] is False
    assert bh_later["status"] == BOARD_STATUS_ONLINE
    tr, _ = tracker.check_transition(now=t0 + 120.0)
    assert tr is None

    # Opt-in SMARTHOME_REQUIRE_BOARD_HEARTBEAT=1 enforces timeout even before hardware attaches
    monkeypatch.setenv("SMARTHOME_REQUIRE_BOARD_HEARTBEAT", "1")
    tr_strict, bh_strict = tracker.check_transition(now=t0 + 120.0)
    assert tr_strict == "ONLINE_TO_OFFLINE"
    assert bh_strict["online"] is False
    assert bh_strict["status"] == BOARD_STATUS_OFFLINE


def test_hardware_attach_timeout_and_detach_restores_clean_online_state(
    isolated_offline_test_env: SmartHomeEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S2-MF-1: Mock/physical board attaches on heartbeat, times out cleanly, and POST /api/hardware/detach restores prod."""
    monkeypatch.delenv("SMARTHOME_REQUIRE_BOARD_HEARTBEAT", raising=False)
    monkeypatch.setenv("SMARTHOME_BOARD_HEARTBEAT_TIMEOUT_SEC", "5.0")
    client = TestClient(app)
    sessions = _make_tier_sessions()
    eng = isolated_offline_test_env

    # RBAC on POST /api/hardware/detach: unauth -> 401, Cap 2 / Cap 3 -> 403
    assert client.post("/api/hardware/detach", json={}).status_code == 401
    assert client.post(
        "/api/hardware/detach",
        headers={"X-Session-Token": sessions[2].session_id},
        json={},
    ).status_code == 403
    assert client.post(
        "/api/hardware/detach",
        headers={"X-Session-Token": sessions[3].session_id},
        json={},
    ).status_code == 403

    # 1. QA mock board sends heartbeat -> attaches hardware & overrides node_id
    r_hb = client.post(
        "/api/hardware/heartbeat",
        headers={"X-Hardware-Key": HW_KEY_TEST},
        json={"node_id": "qa-mock-board-s4-20261126", "wifi_rssi_dbm": -45},
    )
    assert r_hb.status_code == 200
    assert r_hb.json()["board_health"]["hardware_attached"] is True
    assert r_hb.json()["board_health"]["node_id"] == "qa-mock-board-s4-20261126"

    # 2. Stopping mock board causes heartbeat timeout -> OFFLINE (HTTP 503)
    eng.board_health.last_seen = time.time() - 20.0
    tr, bh_off = eng.check_board_heartbeat_transition()
    assert tr == "ONLINE_TO_OFFLINE"
    assert bh_off["online"] is False

    # 3. POST /api/hardware/detach (Cap 1 Owner) restores clean board-less ONLINE state & default node_id
    r_det = client.post(
        "/api/hardware/detach",
        headers={"X-Session-Token": sessions[1].session_id},
        json={},
    )
    assert r_det.status_code == 200
    det_bh = r_det.json()["board_health"]
    assert r_det.json()["detached"] is True
    assert det_bh["online"] is True
    assert det_bh["hardware_attached"] is False
    assert det_bh["node_id"] == "esp8266_node_01"
    assert det_bh["offline_since"] is None

    # 4. Even 120s later with zero heartbeats, board stays ONLINE and device control succeeds (HTTP 200)
    eng.board_health.last_seen = time.time() - 120.0
    assert eng.check_board_heartbeat_transition()[0] is None
    assert eng.is_board_online() is True
    non_door_id = next(d for d, m in DEFAULT_DEVICES.items() if m["type"] != "door")
    r_dev = client.post(
        "/api/device",
        headers={"X-Session-Token": sessions[1].session_id},
        json={"device_id": non_door_id, "action": "turn_on", "source": "web_dashboard"},
    )
    assert r_dev.status_code == 200 and r_dev.json()["ok"] is True


def test_owner_ui_sensor_simulation_does_not_attach_hardware_timeout(
    isolated_offline_test_env: SmartHomeEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S2-MF-1: Owner simulating sensors from Web UI must not arm 30s hardware heartbeat lockout."""
    monkeypatch.delenv("SMARTHOME_REQUIRE_BOARD_HEARTBEAT", raising=False)
    monkeypatch.setenv("SMARTHOME_BOARD_HEARTBEAT_TIMEOUT_SEC", "5.0")
    client = TestClient(app)
    sessions = _make_tier_sessions()
    eng = isolated_offline_test_env

    assert eng.board_health.hardware_attached is False
    r_dht = client.post(
        "/api/dht11",
        headers={"X-Session-Token": sessions[1].session_id},
        json={"temp_c": 30.0, "humidity_pct": 62.0},
    )
    assert r_dht.status_code == 200
    assert eng.board_health.hardware_attached is False
    eng.board_health.last_seen = time.time() - 60.0
    assert eng.is_board_online() is True


def test_voice_command_endpoint_returns_503_and_offline_metadata(
    isolated_offline_test_env: SmartHomeEngine,
) -> None:
    """S2-MF-2: POST /api/voice_command must return HTTP 503 with full board_offline metadata."""
    client = TestClient(app)
    sessions = _make_tier_sessions()
    eng = isolated_offline_test_env

    client.post(
        "/api/hardware/lwt",
        headers={"X-Hardware-Key": HW_KEY_TEST},
        json={"node_id": "esp8266_node_01", "online": False},
    )
    assert eng.is_board_online() is False

    non_door_id = next(d for d, m in DEFAULT_DEVICES.items() if m["type"] != "door")
    cmd_vi = _build_vi_command_from_registry(non_door_id, "turn_on")
    resp = client.post(
        "/api/voice_command",
        headers={"X-Session-Token": sessions[1].session_id},
        json={"transcript": cmd_vi, "source": "web_voice"},
    )
    assert resp.status_code == 503, f"Expected 503 from /api/voice_command, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["ok"] is False
    assert body["executed"] is False
    assert body["board_offline"] is True
    assert body["delivery_status"] == "BOARD_OFFLINE"
    assert body["rejection_speech"]
    assert body["last_seen"]
    assert body["last_seen_vi"]
    assert body["board_health"]["online"] is False
    _assert_no_false_success_vi(str(body.get("exact_spoken_reply") or ""), DEFAULT_DEVICES[non_door_id]["name"])


def test_automation_nlu_custom_command_reset_devices_and_ai_tool_registry_return_503_offline(
    isolated_offline_test_env: SmartHomeEngine,
) -> None:
    """S2-MF-3: Saved custom commands, reset_devices, and ai_tool_registry must return 503 offline (no false success)."""
    from backend.ai_tool_registry import dispatch_tool
    from backend.automation_nlu import execute_confirmed_mutation
    from backend.automation_repo import upsert_custom_command

    client = TestClient(app)
    sessions = _make_tier_sessions()
    eng = isolated_offline_test_env

    non_door_id = next(d for d, m in DEFAULT_DEVICES.items() if m["type"] != "door")
    custom_phrase = f"khởi chạy kiểm tra {uuid.uuid4().hex[:6]}"
    upsert_custom_command(
        owner_user_id=sessions[1].user_id,
        owner_name=sessions[1].display_name,
        owner_tier=1,
        phrase=custom_phrase,
        steps=[{"device_id": non_door_id, "action": "turn_on"}],
    )

    # Take board offline via LWT
    client.post(
        "/api/hardware/lwt",
        headers={"X-Hardware-Key": HW_KEY_TEST},
        json={"node_id": "esp8266_node_01", "online": False},
    )
    assert eng.is_board_online() is False

    # 1. Saved custom command via /api/text_command (stage -> confirm) -> HTTP 503, ok=False, executed=False
    r_stage = client.post(
        "/api/text_command",
        headers={"X-Session-Token": sessions[1].session_id},
        json={"text": custom_phrase},
    )
    if r_stage.status_code == 200 and r_stage.json().get("requires_confirmation"):
        r_cc = client.post(
            "/api/text_command",
            headers={"X-Session-Token": sessions[1].session_id},
            json={"text": "đồng ý"},
        )
    else:
        r_cc = r_stage
    assert r_cc.status_code == 503, f"Expected 503 for custom command offline, got {r_cc.status_code}: {r_cc.text}"
    cc_body = r_cc.json()
    assert cc_body["ok"] is False
    assert cc_body["executed"] is False
    assert cc_body["board_offline"] is True
    assert cc_body["delivery_status"] == "BOARD_OFFLINE"
    _assert_no_false_success_vi(str(cc_body.get("exact_spoken_reply") or ""), DEFAULT_DEVICES[non_door_id]["name"])

    # 2. reset_devices via automation_nlu -> status_code=503, ok=False, executed=False
    rst_res = asyncio.run(
        execute_confirmed_mutation(
            action_kind="reset_devices",
            payload={},
            engine=eng,
            session=sessions[1],
            source="text_command",
        )
    )
    assert rst_res["status_code"] == 503
    rst_pl = rst_res["payload"]
    assert rst_pl["ok"] is False
    assert rst_pl["executed"] is False
    assert rst_pl["board_offline"] is True
    assert rst_pl["delivery_status"] == "BOARD_OFFLINE"
    _assert_no_false_success_vi(str(rst_pl.get("exact_spoken_reply") or ""))

    # 3. ai_tool_registry set_device & control_device -> status_code=503
    for tool_name in ("set_device", "control_device"):
        tool_res = asyncio.run(
            dispatch_tool(
                tool_name,
                {"device_id": non_door_id, "action": "turn_on"},
                engine=eng,
                session=sessions[1],
                source="text_command",
                session_key="s2_mf3_test",
            )
        )
        assert tool_res["status_code"] == 503, f"{tool_name} expected 503, got {tool_res}"
        tool_body = tool_res.get("payload") if isinstance(tool_res.get("payload"), dict) else tool_res
        assert tool_body.get("board_offline") is True


def test_ws_manual_toggle_offline_emits_offline_ack_and_offline_speech_not_rbac(
    isolated_offline_test_env: SmartHomeEngine,
) -> None:
    """S2-MF-4: WS manual_toggle when board is offline must include offline metadata and speak offline refusal (not RBAC)."""
    import json
    from fastapi import WebSocketDisconnect
    from backend.live.gemini_bridge import LiveBridgeSession
    from backend.live.tts_rejection_vi import FIXED_REJECTION_PHRASE_VI

    eng = isolated_offline_test_env
    sessions = _make_tier_sessions()
    sess = sessions[1]
    eng.record_board_lwt(online=False, node_id="esp8266_node_01")
    non_door_id = next(d for d, m in DEFAULT_DEVICES.items() if m["type"] != "door")

    async def _run_ws() -> list[dict[str, Any]]:
        sent_frames: list[dict[str, Any]] = []
        incoming = [
            json.dumps({
                "type": "manual_toggle",
                "device_id": non_door_id,
                "action": "turn_on",
                "request_id": "req-s2-mf4",
            })
        ]
        fake_ws = AsyncMock()
        fake_ws.headers = {}
        fake_ws.cookies = {}
        fake_ws.query_params = {}

        async def _recv_text() -> str:
            if incoming:
                return incoming.pop(0)
            raise WebSocketDisconnect(code=1000)

        async def _send_text(raw: str) -> None:
            sent_frames.append(json.loads(raw))

        fake_ws.receive_text = AsyncMock(side_effect=_recv_text)
        fake_ws.send_text = AsyncMock(side_effect=_send_text)

        bridge = LiveBridgeSession(
            ws=fake_ws,
            engine=eng.create_isolated_ws_view(),
            ws_session=sess,
        )
        await bridge.run()
        return sent_frames

    frames = asyncio.run(_run_ws())
    acks = [f for f in frames if f.get("type") == "manual_toggle_ack"]
    assert acks, f"Expected manual_toggle_ack in frames: {frames}"
    ack = acks[0]
    assert ack["ok"] is False
    assert ack["rbac_blocked"] is False
    assert ack["board_offline"] is True
    assert ack["delivery_status"] == "BOARD_OFFLINE"
    assert ack["last_seen_vi"]
    assert ack["board_health"]["online"] is False

    aoede_reqs = [f for f in frames if f.get("type") == "aoede_voice_request"]
    assert aoede_reqs, f"Expected aoede_voice_request for offline manual_toggle: {frames}"
    spoken = str(aoede_reqs[0].get("spoken_phrase") or "")
    assert spoken != FIXED_REJECTION_PHRASE_VI, "Offline manual_toggle must NOT play RBAC denial audio!"
    _assert_no_false_success_vi(spoken, DEFAULT_DEVICES[non_door_id]["name"])
