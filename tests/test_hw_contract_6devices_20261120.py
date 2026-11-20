"""Comprehensive regression tests for the locked 6-device / 3-sensor / 10-pin ESP8266 contract."""
from __future__ import annotations

import asyncio
import json
import pathlib
import re
import sqlite3
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
INO_PATH = ROOT / "firmware_esp8266" / "esp8266_smarthome" / "esp8266_smarthome.ino"
WOKWI_DIAGRAM_PATH = ROOT / "firmware_esp8266" / "wokwi" / "diagram.json"
KB_PATH = ROOT / "simulator" / "data" / "knowledge_base.json"
HOUSE3D_PATH = ROOT / "simulator" / "static" / "house3d.js"

CANONICAL_6_DEVICES = (
    "main_door",
    "living_room_light",
    "bedroom_light",
    "garden_pump",
    "alarm_siren",
    "speaker_amp",
)

REMOVED_TOKENS = ("fan", "ac", "ir_learn", "vs1838b")


def test_constants_and_time_6_devices_3_sensors_contract() -> None:
    from simulator.engine.constants_and_time import (
        DEFAULT_DEVICES,
        DEVICE_CAPABILITIES,
        DEVICE_DEFAULT_SETTINGS,
        DEVICE_ID_ALIASES,
        HARDWARE_AUDIO_PINS,
    )

    assert tuple(DEFAULT_DEVICES.keys()) == CANONICAL_6_DEVICES
    assert tuple(DEVICE_CAPABILITIES.keys()) == CANONICAL_6_DEVICES
    assert "fan" not in DEFAULT_DEVICES and "ac" not in DEFAULT_DEVICES
    assert "fan" not in DEVICE_CAPABILITIES and "ac" not in DEVICE_CAPABILITIES
    assert set(DEVICE_DEFAULT_SETTINGS.keys()) == {"living_room_light", "bedroom_light"}
    assert "D7 / GPIO13" in HARDWARE_AUDIO_PINS["speaker_amp_relay"]
    assert "D3 / GPIO0" in HARDWARE_AUDIO_PINS["speaker_pwm_audio"]
    assert "D5 / GPIO14" in HARDWARE_AUDIO_PINS["sound_sensor_do"]

    assert "fan" not in DEVICE_ID_ALIASES.values()
    assert "ac" not in DEVICE_ID_ALIASES.values()
    for alias in ("speaker_relay", "pam8403", "speaker_power", "audio_amp"):
        assert DEVICE_ID_ALIASES[alias] == "speaker_amp"

    assert "D1 / GPIO5" in DEFAULT_DEVICES["main_door"]["gpio"]
    assert "D0 / GPIO16" in DEFAULT_DEVICES["living_room_light"]["gpio"]
    assert "D4 / GPIO2" in DEFAULT_DEVICES["bedroom_light"]["gpio"]
    assert "D6 / GPIO12" in DEFAULT_DEVICES["garden_pump"]["gpio"]
    assert "D8 / GPIO15" in DEFAULT_DEVICES["alarm_siren"]["gpio"]
    assert "D7 / GPIO13" in DEFAULT_DEVICES["speaker_amp"]["gpio"]


def test_tier_permissions_exact_6_devices_and_tiers() -> None:
    from simulator.auth.tier_permissions import (
        DEVICE_LABELS_VI,
        DEVICE_MIN_TIER,
        devices_visible_for_tier,
    )

    expected_tiers = {
        "main_door": 1,
        "alarm_siren": 1,
        "garden_pump": 2,
        "speaker_amp": 2,
        "living_room_light": 3,
        "bedroom_light": 3,
    }
    assert DEVICE_MIN_TIER == expected_tiers
    assert set(DEVICE_LABELS_VI.keys()) == set(CANONICAL_6_DEVICES)
    assert "PAM8403" in DEVICE_LABELS_VI["speaker_amp"]
    assert set(devices_visible_for_tier(1)) == set(CANONICAL_6_DEVICES)
    assert set(devices_visible_for_tier(2)) == {
        "living_room_light",
        "bedroom_light",
        "garden_pump",
        "speaker_amp",
    }
    assert set(devices_visible_for_tier(3)) == {"living_room_light", "bedroom_light"}


def test_mqtt_bridge_10_pin_contract_and_packet_generation(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMARTHOME_DATA_DIR", str(tmp_path))
    import simulator.mqtt_bridge as mb

    monkeypatch.setattr(mb, "EDGE_REPLICA_FILE", tmp_path / "esp8266_flash_replica.json")
    from simulator.mqtt_bridge import ESP8266_PIN_MAP, ESP8266_SENSOR_PIN_MAP, SmartHomeMQTTBridge

    assert ESP8266_PIN_MAP == {
        "main_door": {"pin": "D1", "gpio": 5, "mode": "PWM_SERVO"},
        "living_room_light": {"pin": "D0", "gpio": 16, "mode": "DIGITAL_OUT"},
        "bedroom_light": {"pin": "D4", "gpio": 2, "mode": "DIGITAL_OUT_SAFE_BOOT"},
        "garden_pump": {"pin": "D6", "gpio": 12, "mode": "RELAY_PUMP_5V_DIODE_1N4007"},
        "alarm_siren": {"pin": "D8", "gpio": 15, "mode": "DIGITAL_OUT_ACTIVE_HIGH"},
        "speaker_amp": {"pin": "D7", "gpio": 13, "mode": "RELAY_PAM8403_POWER_PWM_D3"},
    }
    assert ESP8266_SENSOR_PIN_MAP == {
        "dht11": {"pin": "D2", "gpio": 4, "mode": "ONE_WIRE_DHT11"},
        "soil_moisture": {"pin": "A0", "gpio": 0, "mode": "ADC0_SOIL_LM393"},
        "sound": {"pin": "D5", "gpio": 14, "mode": "DIGITAL_IN_KY037_DO"},
        "speaker_audio_pwm": {"pin": "D3", "gpio": 0, "mode": "AUDIO_PWM_OUT_RC"},
    }

    bridge = SmartHomeMQTTBridge()
    assert not any("ir" in k for k in bridge.retained_topics)

    async def _exercise() -> None:
        cmd_pkt = await bridge.publish_actuate_command(
            "speaker_amp", "ON", "turn_on", "test", "Nguyễn Tuấn Anh", 1
        )
        assert cmd_pkt["topic"] == "smarthome/cmd/actuate"
        assert cmd_pkt["payload"]["targets"][0]["pin"] == "D7"
        assert cmd_pkt["payload"]["targets"][0]["gpio"] == 13
        assert bridge.retained_topics["smarthome/state/report"]["payload"]["device_id"] == "speaker_amp"

        snd_pkt = await bridge.update_sound_telemetry(sound_detected=True, do_state=1, note="clap")
        assert snd_pkt["topic"] == "smarthome/telemetry/sound"
        assert snd_pkt["payload"]["sensor_pin"] == "D5"
        assert snd_pkt["payload"]["sound_detected"] is True
        assert snd_pkt["payload"]["event_count"] == 1

        soil_pkt = await bridge.update_soil_moisture_telemetry(28.0)
        assert soil_pkt["topic"] == "smarthome/telemetry/soil_moisture"
        assert soil_pkt["payload"]["sensor_pin"] == "A0"

    asyncio.run(_exercise())


def test_prompt_builder_and_knowledge_base_contract() -> None:
    from simulator.live.prompt_builder import ACTION_ENUM, DEVICE_ENUM, build_system_instruction, fn_set_device, make_live_config
    from simulator.rule_engine import SmartHomeEngine

    assert tuple(DEVICE_ENUM[:6]) == CANONICAL_6_DEVICES
    assert "fan" not in DEVICE_ENUM and "ac" not in DEVICE_ENUM
    assert ACTION_ENUM == ["open", "close", "turn_on", "turn_off"]

    dev_prop = fn_set_device.parameters.properties["device_id"]
    assert tuple(dev_prop.enum) == CANONICAL_6_DEVICES
    assert "temperature_c" not in fn_set_device.parameters.properties
    assert "fan_speed" not in fn_set_device.parameters.properties

    engine = SmartHomeEngine(on_event=None)
    prompt = build_system_instruction(engine)
    for expected_fragment in (
        "6 thiết bị",
        "Cửa chính (D1)",
        "Đèn phòng khách (D0)",
        "Đèn phòng ngủ (D4)",
        "Máy bơm tưới cây (D6)",
        "Còi báo động (D8)",
        "Nguồn mạch loa PAM8403 (D7, âm thanh PWM ra D3)",
        "DHT11 (D2)",
        "Độ ẩm đất (A0)",
        "KY-037 DO (D5",
    ):
        assert expected_fragment in prompt

    for word in ("ok", "đồng ý", "được", "đúng rồi"):
        assert word in prompt.lower()

    cfg = make_live_config(engine)
    assert cfg.speech_config.voice_config.prebuilt_voice_config.voice_name == "Aoede"

    kb = json.loads(KB_PATH.read_text(encoding="utf-8"))
    assert kb["version"] == "4.0-CONCISE-QA-6-DEVICES-3-SENSORS"
    kb_str = json.dumps(kb, ensure_ascii=False).lower()
    assert "quạt trần" not in kb_str
    assert "điều hòa" not in kb_str
    assert "vs1838b" not in kb_str


def test_firmware_ino_10pin_boot_safety_and_speaker_tail() -> None:
    ino = INO_PATH.read_text(encoding="utf-8")

    expected_defines = [
        "#define PIN_LIVING_LIGHT     16",
        "#define PIN_MAIN_DOOR_SERVO  5",
        "#define PIN_DHT11            4",
        "#define PIN_AUDIO_PWM        0",
        "#define PIN_BEDROOM_LIGHT    2",
        "#define PIN_KY037_DO         14",
        "#define PIN_GARDEN_PUMP      12",
        "#define PIN_SPEAKER_AMP      13",
        "#define PIN_ALARM_SIREN      15",
        "#define PIN_SOIL_MOISTURE    A0",
    ]
    for line in expected_defines:
        assert line in ino, f"Missing pin definition: {line}"

    # Boot-safety invariants:
    # 1. D4 (GPIO2) active-LOW & written HIGH before pinMode OUTPUT
    assert "#define BEDROOM_LED_ACTIVE_LOW    true" in ino
    d4_write = ino.index("digitalWrite(PIN_BEDROOM_LIGHT, BEDROOM_LED_ACTIVE_LOW ? HIGH : LOW);")
    d4_mode = ino.index("pinMode(PIN_BEDROOM_LIGHT, OUTPUT);")
    assert d4_write < d4_mode

    # 2. D3 (GPIO0) INPUT at setup and returned to INPUT after noTone()
    assert "pinMode(PIN_AUDIO_PWM, INPUT);" in ino
    notone_idx = ino.index("noTone(PIN_AUDIO_PWM);")
    post_notone_input = ino.index("pinMode(PIN_AUDIO_PWM, INPUT);", notone_idx)
    assert post_notone_input > notone_idx

    # 3. D8 (GPIO15) written LOW before pinMode OUTPUT
    d8_write = ino.index("digitalWrite(PIN_ALARM_SIREN, LOW);")
    d8_mode = ino.index("pinMode(PIN_ALARM_SIREN, OUTPUT);")
    assert d8_write < d8_mode

    # 4. speaker_amp 1500ms auto-on/idle-off tail + KY-037 + soil hysteresis + zero fan/ac/IR
    assert "#define SPEAKER_AMP_IDLE_TAIL_MS  1500UL" in ino
    assert "speakerAmpChimeActive = true;" in ino
    assert "speakerAmpAutoOffAtMs = millis() + SPEAKER_AMP_IDLE_TAIL_MS;" in ino
    assert "speakerAmpManualOn" in ino
    assert "soilPct < 40.0f && !pumpAutoTriggered" in ino
    assert "soilPct >= 70.0f && pumpAutoTriggered" in ino
    assert "attachInterrupt(digitalPinToInterrupt(PIN_KY037_DO), onKy037Interrupt, KY037_TRIGGER_EDGE);" in ino
    assert "smarthome/telemetry/sound" in ino
    assert "VS1838B" not in ino and "IRrecv" not in ino and "ir_learn" not in ino
    assert '"fan"' not in ino and '"ac"' not in ino


def test_wokwi_diagram_10pin_wiring_and_no_fan_ac_ir() -> None:
    diagram = json.loads(WOKWI_DIAGRAM_PATH.read_text(encoding="utf-8"))
    parts = {p["id"]: p for p in diagram["parts"]}
    expected_part_ids = {
        "bb1",
        "mcu",
        "servo_door",
        "led_living",
        "r_living_220",
        "dht11_sensor",
        "led_bedroom",
        "r_bedroom_220",
        "relay_pump",
        "r_pump_220",
        "motor_pump_indicator",
        "relay_speaker",
        "r_spk_220",
        "speaker_amp_indicator",
        "pam8403_speaker",
        "soil_yl69",
        "ky037_sound",
        "r_ky037_10k",
        "buzzer_alarm",
    }
    assert expected_part_ids.issubset(parts.keys())
    raw_lower = json.dumps(diagram).lower()
    for retired in ("fan", "vs1838", "ir_rx", "ir_tx", "vc02"):
        assert retired not in raw_lower

    conn_pairs = {(c[0], c[1]) for c in diagram["connections"]} | {(c[1], c[0]) for c in diagram["connections"]}
    assert ("mcu:16", "r_living_220:1") in conn_pairs
    assert ("mcu:5", "servo_door:PWM") in conn_pairs
    assert ("dht11_sensor:SDA", "mcu:4") in conn_pairs
    assert ("mcu:0", "pam8403_speaker:2") in conn_pairs
    assert ("mcu:2", "r_bedroom_220:1") in conn_pairs
    assert ("ky037_sound:2.l", "mcu:14") in conn_pairs
    assert ("mcu:12", "relay_pump:IN") in conn_pairs
    assert ("mcu:13", "relay_speaker:IN") in conn_pairs
    assert ("mcu:15", "buzzer_alarm:2") in conn_pairs
    assert ("soil_yl69:SIG", "mcu:34") in conn_pairs


def test_sqlite_7_to_6_migration_preserves_states_and_prunes_fan_ac(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from simulator.db_migrations import apply_schema_migrations, open_wal_connection

    db_path = tmp_path / "smarthome.db"
    monkeypatch.setenv("SMARTHOME_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SMARTHOME_SQLITE_PATH", str(db_path))
    conn = open_wal_connection(db_path)
    try:
        # Seed a legacy v4 schema DB with 7 devices (incl. fan & ac, missing speaker_amp)
        apply_schema_migrations(conn)
        conn.execute("DELETE FROM schema_migrations WHERE version >= 5")
        conn.execute("DELETE FROM devices")
        conn.execute("DELETE FROM device_state")
        legacy_rows = [
            ("main_door", "Cửa chính", "D1", "OPEN", 1, 0, "ADMIN", "entry", "door"),
            ("living_room_light", "Đèn phòng khách", "D0", "ON", 3, 1, "CHILD_GUEST", "living", "light"),
            ("bedroom_light", "Đèn phòng ngủ", "D4", "OFF", 3, 1, "CHILD_GUEST", "bedroom", "light"),
            ("garden_pump", "Máy bơm tưới cây", "D6", "ON", 2, 1, "MEMBER", "garden", "pump"),
            ("alarm_siren", "Còi báo động", "D8", "OFF", 1, 0, "ADMIN", "entry", "siren"),
            ("fan", "Quạt trần", "D4", "ON", 3, 1, "CHILD_GUEST", "living", "fan"),
            ("ac", "Điều hòa", "D7", "ON", 2, 1, "MEMBER", "living", "ac"),
        ]
        for did, name, pin, st, tier, off_ok, role, room, dtype in legacy_rows:
            conn.execute(
                """
                INSERT INTO devices (
                    device_id, device_name, gpio_pin, state, min_tier_required,
                    offline_controllable, updated_at, min_role, room, device_type
                ) VALUES (?, ?, ?, ?, ?, ?, '2026-11-19T00:00:00+07:00', ?, ?, ?)
                """,
                (did, name, pin, st, tier, off_ok, role, room, dtype),
            )
            conn.execute(
                "INSERT INTO device_state (device_id, state, version, updated_at) VALUES (?, ?, 3, 100.0)",
                (did, st),
            )
        conn.execute(
            """
            INSERT INTO ir_remote_codes (
                ir_code_id, device_id, appliance_name, command_action, protocol, hex_code, freq_khz, learned_at
            ) VALUES ('ir1', 'ac', 'AC', 'PWR', 'NEC', '0x1', 38, '2026-11-19')
            """
        )
        conn.commit()

        # Run v5 migration
        ver = apply_schema_migrations(conn)
        assert ver == 5
        mig_row = conn.execute("SELECT name FROM schema_migrations WHERE version = 5").fetchone()
        assert mig_row is not None and mig_row["name"] == "hardware_contract_6_devices_20261120"

        dev_rows = {
            r["device_id"]: r["state"]
            for r in conn.execute("SELECT device_id, state FROM devices ORDER BY device_id").fetchall()
        }
        assert set(dev_rows.keys()) == set(CANONICAL_6_DEVICES)
        assert "fan" not in dev_rows and "ac" not in dev_rows
        assert dev_rows["main_door"] == "OPEN"
        assert dev_rows["living_room_light"] == "ON"
        assert dev_rows["garden_pump"] == "ON"
        assert dev_rows["speaker_amp"] == "OFF"

        # sync_engine_state_to_sqlite also cleans ir_remote_codes and keeps 6 devices
        import simulator.database_sqlite as db_mod
        from simulator.database_sqlite import sync_engine_state_to_sqlite
        from simulator.engine import InMemoryStateBackend
        from simulator.rule_engine import SmartHomeEngine

        db_mod._INITIALIZED_DB_PATHS.clear()
        eng = SmartHomeEngine(on_event=None, state_backend=InMemoryStateBackend())
        sync_engine_state_to_sqlite(eng)
        ir_count = conn.execute("SELECT COUNT(*) FROM ir_remote_codes").fetchone()[0]
        assert ir_count == 0
        post_sync_ids = {
            r[0] for r in conn.execute("SELECT device_id FROM devices").fetchall()
        }
        assert post_sync_ids == set(CANONICAL_6_DEVICES)
    finally:
        conn.close()


def test_soil_hysteresis_speaker_toggle_and_ky037_engine(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMARTHOME_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SMARTHOME_SQLITE_PATH", str(tmp_path / "smarthome.db"))
    import simulator.database_sqlite as db_mod
    from simulator.engine import InMemoryStateBackend
    from simulator.rule_engine import SmartHomeEngine

    db_mod._INITIALIZED_DB_PATHS.clear()
    engine = SmartHomeEngine(on_event=None, state_backend=InMemoryStateBackend())
    engine.set_active_user("tuan_anh")

    async def _run() -> None:
        # Soil hysteresis: <40% ON, 55% stays ON, >=70% OFF
        r_dry = await engine.update_soil_moisture_telemetry(24.0)
        assert r_dry["auto_action"] == "AUTO_PUMP_ON"
        assert engine.devices["garden_pump"]["state"] == "ON"

        r_mid = await engine.update_soil_moisture_telemetry(55.0)
        assert r_mid["auto_action"] == "NONE"
        assert engine.devices["garden_pump"]["state"] == "ON"

        r_wet = await engine.update_soil_moisture_telemetry(75.0)
        assert r_wet["auto_action"] == "AUTO_PUMP_OFF"
        assert engine.devices["garden_pump"]["state"] == "OFF"

        # speaker_amp toggle
        r_on = await engine.execute_device_action("speaker_amp", "turn_on")
        assert r_on["ok"] is True and engine.devices["speaker_amp"]["state"] == "ON"
        r_off = await engine.execute_device_action("speaker_amp", "turn_off")
        assert r_off["ok"] is True and engine.devices["speaker_amp"]["state"] == "OFF"

        # KY-037 telemetry
        r_snd = await engine.update_sound_telemetry(sound_detected=True, do_state=1, note="test_clap")
        assert r_snd["ok"] is True
        assert r_snd["telemetry"]["sensor_pin"] == "D5 (GPIO 14)"
        assert r_snd["telemetry"]["event_count"] == 1

    asyncio.run(_run())


def test_voice_ok_confirmation_gate_for_both_set_device_and_control_device(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SMARTHOME_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SMARTHOME_SQLITE_PATH", str(tmp_path / "smarthome.db"))
    import simulator.database_sqlite as db_mod
    from simulator.engine import InMemoryStateBackend
    from simulator.live.tool_dispatcher_mixin import LiveToolDispatcherMixin
    from simulator.rule_engine import SmartHomeEngine

    db_mod._INITIALIZED_DB_PATHS.clear()

    class _FakeVoiceAuth:
        pass

    class _Harness(LiveToolDispatcherMixin):
        def __init__(self, eng: SmartHomeEngine) -> None:
            self.engine = eng
            self.voice_auth = _FakeVoiceAuth()
            self.knowledge_rag = None
            self.gemini_session = None
            self.last_mic_turn_blocked = False
            self.last_mic_auth_result = None
            self.ws_events: list[dict[str, Any]] = []

        async def send_ws_json(self, payload: dict[str, Any]) -> None:
            self.ws_events.append(payload)

        async def _sync_rules_context_to_gemini(self, spoken: str) -> None:
            return None

    engine = SmartHomeEngine(on_event=None, state_backend=InMemoryStateBackend())
    engine.set_active_user("tuan_anh")
    dispatcher = _Harness(engine)

    async def _verify_both_tools() -> None:
        # 1. set_device MUST require confirmation before mutating state
        assert engine.devices["speaker_amp"]["state"] == "OFF"
        res_set = await dispatcher.handle_tool_call(
            SimpleNamespace(name="set_device", args={"device_id": "speaker_amp", "action": "turn_on"})
        )
        assert res_set.get("requires_confirmation") is True
        assert engine.devices["speaker_amp"]["state"] == "OFF"

        conf_set = await dispatcher.handle_tool_call(
            SimpleNamespace(name="confirm_or_cancel_pending_action", args={"confirmed": True})
        )
        assert conf_set.get("ok") is True
        assert engine.devices["speaker_amp"]["state"] == "ON"

        # 2. control_device MUST also require confirmation before mutating state
        assert engine.devices["main_door"]["state"] == "CLOSED"
        res_ctrl = await dispatcher.handle_tool_call(
            SimpleNamespace(name="control_device", args={"device_id": "main_door", "action": "open"})
        )
        assert res_ctrl.get("requires_confirmation") is True
        assert res_ctrl.get("executed") is False
        assert engine.devices["main_door"]["state"] == "CLOSED"

        conf_ctrl = await dispatcher.handle_tool_call(
            SimpleNamespace(name="confirm_or_cancel_pending_action", args={"confirmed": True})
        )
        assert conf_ctrl.get("ok") is True
        assert engine.devices["main_door"]["state"] == "OPEN"

    asyncio.run(_verify_both_tools())


def test_house3d_16_glb_nodes_scene_spec_fallback_and_board_preset() -> None:
    js = HOUSE3D_PATH.read_text(encoding="utf-8")

    expected_16_glb_nodes = (
        "door_pivot",
        "main_door_leaf",
        "led_living_room",
        "led_bedroom",
        "pump_unit",
        "water_tube",
        "relay1_pump",
        "buzzer_alarm",
        "relay2_speaker",
        "pam8403_module",
        "speaker_mini",
        "sensor_dht11",
        "sensor_soil",
        "sensor_mic_ky037",
        "kicad_pcb_hub",
        "nodemcu_esp8266",
    )
    fn_match = re.search(r"function bindGlbLockedNodes\(villaRoot\)\s*\{(.*?)\n  \}", js, flags=re.S)
    assert fn_match is not None
    fn_body = fn_match.group(1)
    for node_name in expected_16_glb_nodes:
        assert f'"{node_name}"' in fn_body, f"Missing GLB node binding: {node_name}"

    assert 'fetch("/hardware/blender/SCENE_SPEC.json"' in js
    assert "if (!res || !res.ok) return null;" in js
    assert 'else if (preset === "board")' in js
    assert "sceneSpecPresets[preset]" in js


def test_http_ir_learn_410_and_scene_spec_route() -> None:
    from simulator.auth.session_store import get_session_store
    from simulator.server import app

    store = get_session_store()
    owner_sess = store.create_session(
        user_id="tuan_anh",
        tier=1,
        role="ADMIN",
        display_name="Nguyễn Tuấn Anh",
        email="nep94121@gmail.com",
        source="test",
    )
    member_sess = store.create_session(
        user_id="thanh_vien_a",
        tier=2,
        role="MEMBER",
        display_name="Thành viên A",
        source="test",
    )

    with TestClient(app) as client:
        # Unauth -> 401
        r_unauth = client.post("/api/ir_learn", json={"command_name": "ac_on"})
        assert r_unauth.status_code == 401

        # Non-owner Tier 2 -> 403
        r_mem = client.post(
            "/api/ir_learn",
            json={"command_name": "ac_on"},
            headers={"X-Session-Token": member_sess.session_id},
        )
        assert r_mem.status_code == 403

        # Owner Tier 1 -> 410 Gone
        r_own = client.post(
            "/api/ir_learn",
            json={"command_name": "ac_on"},
            headers={"X-Session-Token": owner_sess.session_id},
        )
        assert r_own.status_code == 410
        assert r_own.json().get("gone") is True

        # SCENE_SPEC.json route
        r_spec = client.get("/hardware/blender/SCENE_SPEC.json")
        if (ROOT / "hardware" / "blender" / "SCENE_SPEC.json").exists():
            assert r_spec.status_code == 200
            assert isinstance(r_spec.json(), dict)
        else:
            assert r_spec.status_code == 404
