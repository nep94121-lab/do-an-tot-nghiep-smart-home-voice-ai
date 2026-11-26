"""Host-side deterministic unit tests for ESP8266 offline/lost-connection firmware (Session S2, A1..A5).

Zero hardcoded device IDs, device names, command phrases, or numeric timing literals:
every test vector is derived dynamically from the single sources of truth:
  - `backend.engine.constants_and_time` (`DEFAULT_DEVICES`, `ACTION_TO_STATE`, `ACTION_VI_LABEL`, `DEVICE_ID_ALIASES`)
  - `backend.engine.offline_contract` (`OFFLINE_*`, timing/safety constants)
  - `hardware.wiring_contract` (`FIRMWARE_PIN_CONTRACT`)
  - `firmware/esp8266_smarthome/offline_safety_config.h`
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass, field

import pytest

from backend.engine.constants_and_time import (
    ACTION_TO_STATE,
    ACTION_VI_LABEL,
    DEFAULT_DEVICES,
    DEVICE_ID_ALIASES,
)
from backend.engine.offline_contract import (
    HEARTBEAT_INTERVAL_MS,
    OFFLINE_ACTUATOR_MAX_RUN_MS,
    OFFLINE_ALLOWED_DEVICE_ACTIONS,
    OFFLINE_AUTOMATION_MUTATION_ALLOWED,
    OFFLINE_CUSTOM_COMMANDS_ALLOWED,
    OFFLINE_FORBIDDEN_DEVICE_ACTIONS,
    OFFLINE_LED_CYCLE_MS,
    OFFLINE_ROLE_CHECK_ENABLED,
    OFFLINE_SAFETY_DEFAULTS,
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
    is_offline_action_allowed,
    is_offline_action_forbidden,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
FW_DIR = ROOT / "firmware" / "esp8266_smarthome"
CONFIG_H = FW_DIR / "offline_safety_config.h"
GRAMMAR_H = FW_DIR / "offline_command_grammar.h"
FSM_H = FW_DIR / "offline_fsm.h"
INO_PATH = FW_DIR / "esp8266_smarthome.ino"
PIO_INI = FW_DIR / "platformio.ini"
WOKWI_SKETCH = ROOT / "firmware" / "wokwi" / "sketch.ino"
FW_README = ROOT / "firmware" / "README.md"


def _parse_cpp_uint(header_text: str, name: str) -> int:
    m = re.search(rf"\b{re.escape(name)}\s*=\s*(\d+)(?:UL|U|L)?\s*;", header_text)
    assert m is not None, f"Missing constant {name} in offline_safety_config.h"
    return int(m.group(1))


def _parse_cpp_float(header_text: str, name: str) -> float:
    m = re.search(rf"\b{re.escape(name)}\s*=\s*([0-9]+(?:\.[0-9]+)?)f?\s*;", header_text)
    assert m is not None, f"Missing float constant {name} in offline_safety_config.h"
    return float(m.group(1))


def _parse_cpp_bool(header_text: str, name: str) -> bool:
    m = re.search(rf"\b{re.escape(name)}\s*=\s*(true|false)\s*;", header_text)
    assert m is not None, f"Missing bool constant {name} in offline_safety_config.h"
    return m.group(1) == "true"


def _parse_cpp_str(header_text: str, name: str) -> str:
    m = re.search(rf'\b{re.escape(name)}\s*=\s*\n?\s*"([^"]*)"\s*;', header_text)
    assert m is not None, f"Missing string constant {name} in offline_safety_config.h"
    return m.group(1)


def _parse_cpp_device_policies(header_text: str) -> list[dict[str, object]]:
    pattern = re.compile(
        r'\{\s*(DEV_[A-Z0-9_]+)\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,'
        r"\s*(true|false)\s*,\s*(true|false)\s*,\s*(true|false)\s*\}"
    )
    rows: list[dict[str, object]] = []
    for m in pattern.finditer(header_text):
        rows.append(
            {
                "enum_name": m.group(1),
                "id": m.group(2),
                "name_vi": m.group(3),
                "on_state": m.group(4),
                "off_state": m.group(5),
                "allow_offline_on_or_open": m.group(6) == "true",
                "allow_offline_off_or_close": m.group(7) == "true",
                "force_safe_off_on_disconnect": m.group(8) == "true",
            }
        )
    assert rows, "Failed to parse DEVICE_POLICIES from offline_safety_config.h"
    return rows


def _load_config_constants() -> dict[str, object]:
    txt = CONFIG_H.read_text(encoding="utf-8")
    return {
        "DEVICE_POLICIES": _parse_cpp_device_policies(txt),
        "OFFLINE_ROLE_CHECK_ENABLED": _parse_cpp_bool(txt, "OFFLINE_ROLE_CHECK_ENABLED"),
        "OFFLINE_CUSTOM_COMMANDS_ALLOWED": _parse_cpp_bool(txt, "OFFLINE_CUSTOM_COMMANDS_ALLOWED"),
        "OFFLINE_AUTOMATION_MUTATION_ALLOWED": _parse_cpp_bool(txt, "OFFLINE_AUTOMATION_MUTATION_ALLOWED"),
        "OFFLINE_STATUS_QUERY_ALLOWED": _parse_cpp_bool(txt, "OFFLINE_STATUS_QUERY_ALLOWED"),
        "OFFLINE_MAIN_DOOR_OPEN_ALLOWED": _parse_cpp_bool(txt, "OFFLINE_MAIN_DOOR_OPEN_ALLOWED"),
        "WIFI_BACKOFF_INITIAL_MS": _parse_cpp_uint(txt, "WIFI_BACKOFF_INITIAL_MS"),
        "WIFI_BACKOFF_MAX_MS": _parse_cpp_uint(txt, "WIFI_BACKOFF_MAX_MS"),
        "WIFI_BACKOFF_MULTIPLIER": _parse_cpp_uint(txt, "WIFI_BACKOFF_MULTIPLIER"),
        "SERVER_BACKOFF_INITIAL_MS": _parse_cpp_uint(txt, "SERVER_BACKOFF_INITIAL_MS"),
        "SERVER_BACKOFF_MAX_MS": _parse_cpp_uint(txt, "SERVER_BACKOFF_MAX_MS"),
        "SERVER_BACKOFF_MULTIPLIER": _parse_cpp_uint(txt, "SERVER_BACKOFF_MULTIPLIER"),
        "HEARTBEAT_INTERVAL_MS": _parse_cpp_uint(txt, "HEARTBEAT_INTERVAL_MS"),
        "OFFLINE_HTTP_PORT": _parse_cpp_uint(txt, "OFFLINE_HTTP_PORT"),
        "WIFI_AP_FALLBACK_AFTER_MS": _parse_cpp_uint(txt, "WIFI_AP_FALLBACK_AFTER_MS"),
        "PUMP_MAX_CONTINUOUS_RUN_MS": _parse_cpp_uint(txt, "PUMP_MAX_CONTINUOUS_RUN_MS"),
        "SIREN_MAX_OFFLINE_RUN_MS": _parse_cpp_uint(txt, "SIREN_MAX_OFFLINE_RUN_MS"),
        "SPEAKER_AMP_IDLE_TAIL_DEFAULT_MS": _parse_cpp_uint(txt, "SPEAKER_AMP_IDLE_TAIL_DEFAULT_MS"),
        "SOIL_PUMP_ON_THRESHOLD_PCT": _parse_cpp_float(txt, "SOIL_PUMP_ON_THRESHOLD_PCT"),
        "SOIL_PUMP_OFF_THRESHOLD_PCT": _parse_cpp_float(txt, "SOIL_PUMP_OFF_THRESHOLD_PCT"),
        "OFFLINE_LED_CYCLE_MS": _parse_cpp_uint(txt, "OFFLINE_LED_CYCLE_MS"),
        "OFFLINE_LED_PULSE_MS": _parse_cpp_uint(txt, "OFFLINE_LED_PULSE_MS"),
        "OFFLINE_LED_GAP_MS": _parse_cpp_uint(txt, "OFFLINE_LED_GAP_MS"),
        "OFFLINE_LED_PULSES_PER_CYCLE": _parse_cpp_uint(txt, "OFFLINE_LED_PULSES_PER_CYCLE"),
        "OFFLINE_DISCONNECT_BEEP_MS": _parse_cpp_uint(txt, "OFFLINE_DISCONNECT_BEEP_MS"),
        "OFFLINE_DISCONNECT_BEEP_GAP_MS": _parse_cpp_uint(txt, "OFFLINE_DISCONNECT_BEEP_GAP_MS"),
        "OFFLINE_DISCONNECT_BEEP_COUNT": _parse_cpp_uint(txt, "OFFLINE_DISCONNECT_BEEP_COUNT"),
        "OFFLINE_EVENT_RING_CAPACITY": _parse_cpp_uint(txt, "OFFLINE_EVENT_RING_CAPACITY"),
        "REPLY_DOOR_OPEN_FORBIDDEN_VI": _parse_cpp_str(txt, "REPLY_DOOR_OPEN_FORBIDDEN_VI"),
        "REPLY_CUSTOM_FORBIDDEN_VI": _parse_cpp_str(txt, "REPLY_CUSTOM_FORBIDDEN_VI"),
        "REASON_OK": _parse_cpp_str(txt, "REASON_OK"),
        "REASON_STATUS_OK": _parse_cpp_str(txt, "REASON_STATUS_OK"),
        "REASON_DOOR_OPEN_FORBIDDEN": _parse_cpp_str(txt, "REASON_DOOR_OPEN_FORBIDDEN"),
        "REASON_CUSTOM_FORBIDDEN": _parse_cpp_str(txt, "REASON_CUSTOM_FORBIDDEN"),
    }


def _devices_of_type(dev_type: str) -> tuple[str, ...]:
    return tuple(
        dev_id
        for dev_id, meta in DEFAULT_DEVICES.items()
        if str(meta.get("type") or "").strip().lower() == dev_type
    )


def _normalize_vi_ascii(raw: str) -> str:
    raw = raw.replace("đ", "d").replace("Đ", "d")
    decomposed = unicodedata.normalize("NFD", raw)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    out = []
    last_space = True
    for ch in stripped.lower():
        if ch.isalnum() or ch == "_":
            out.append(ch)
            last_space = False
        elif not last_space:
            out.append(" ")
            last_space = True
    return "".join(out).strip()


def _contains_phrase(norm: str, phrase: str) -> bool:
    return bool(phrase) and (f" {phrase} " in f" {norm} ")


def _build_registry_phrase_map() -> dict[str, tuple[str, ...]]:
    """Derive normalized recognition phrases for every device strictly from DEFAULT_DEVICES + DEVICE_ID_ALIASES."""
    phrases: dict[str, list[str]] = {}
    for dev_id, meta in DEFAULT_DEVICES.items():
        dev_phrases = [_normalize_vi_ascii(dev_id), _normalize_vi_ascii(str(meta.get("name") or ""))]
        dev_type = _normalize_vi_ascii(str(meta.get("type") or ""))
        if dev_type == "door":
            dev_phrases.append("door")
        phrases[dev_id] = [p for p in dev_phrases if p]
    for alias, target_id in DEVICE_ID_ALIASES.items():
        if target_id in phrases:
            norm_alias = _normalize_vi_ascii(alias)
            if norm_alias and norm_alias not in phrases[target_id]:
                phrases[target_id].append(norm_alias)
    return {k: tuple(v) for k, v in phrases.items()}


# ---------------------------------------------------------------------------
# Faithful Python behavioral model driven strictly by SSOT registry & header
# ---------------------------------------------------------------------------
@dataclass
class _BackoffModel:
    initial_ms: int
    max_ms: int
    multiplier: int
    current_delay_ms: int = field(init=False)
    next_attempt_ms: int = 0
    attempts: int = 0
    scheduled: bool = False

    def __post_init__(self) -> None:
        self.current_delay_ms = self.initial_ms

    def reset(self) -> None:
        self.current_delay_ms = self.initial_ms
        self.next_attempt_ms = 0
        self.attempts = 0
        self.scheduled = False

    def should_attempt(self, now_ms: int) -> bool:
        return (not self.scheduled) or (now_ms >= self.next_attempt_ms)

    def record_failure(self, now_ms: int) -> int:
        wait = self.current_delay_ms
        self.next_attempt_ms = now_ms + wait
        self.scheduled = True
        self.attempts += 1
        self.current_delay_ms = min(self.current_delay_ms * self.multiplier, self.max_ms)
        return wait

    def record_success(self) -> None:
        self.reset()


@dataclass
class _OfflineFsmModel:
    cfg: dict[str, object]
    devices: tuple[str, ...] = field(default_factory=lambda: tuple(DEFAULT_DEVICES.keys()))
    states: dict[str, bool] = field(
        default_factory=lambda: {
            dev_id: OFFLINE_SAFETY_DEFAULTS[dev_id] in (ACTION_TO_STATE["open"], ACTION_TO_STATE["turn_on"])
            for dev_id in DEFAULT_DEVICES
        }
    )
    server_online: bool = False
    has_ever_been_online: bool = False
    offline_since_ms: int = 0
    last_offline_duration_ms: int = 0
    pending_resync: bool = False
    dirty_mask: int = 0
    events: list[dict[str, object]] = field(default_factory=list)
    actuator_started_ms: dict[str, int] = field(default_factory=dict)
    pump_safety_locked_until_wet: bool = False
    wifi_disconnected_since_ms: int | None = None
    _phrase_map: dict[str, tuple[str, ...]] = field(default_factory=_build_registry_phrase_map)

    def _dev_bit(self, dev_id: str) -> int:
        return 1 << self.devices.index(dev_id)

    def _dev_type(self, dev_id: str) -> str:
        return str(DEFAULT_DEVICES[dev_id].get("type") or "").strip().lower()

    def _state_str(self, dev_id: str, state_on: bool) -> str:
        if self._dev_type(dev_id) == "door":
            return ACTION_TO_STATE["open"] if state_on else ACTION_TO_STATE["close"]
        return ACTION_TO_STATE["turn_on"] if state_on else ACTION_TO_STATE["turn_off"]

    def _push_event(self, dev_id: str, state_on: bool, reason: str, offset_ms: int) -> None:
        cap = int(self.cfg["OFFLINE_EVENT_RING_CAPACITY"])
        if len(self.events) >= cap:
            self.events.pop(0)
        self.events.append(
            {
                "device_id": dev_id,
                "state": self._state_str(dev_id, state_on),
                "reason": reason,
                "offset_ms": offset_ms,
            }
        )

    def can_set_device(self, dev_id: str, action: str) -> bool:
        if not self.server_online and is_offline_action_forbidden(dev_id, action):
            return bool(self.cfg["OFFLINE_MAIN_DOOR_OPEN_ALLOWED"])
        return True

    def should_enable_softap(self, wifi_connected: bool, now_ms: int) -> bool:
        if wifi_connected:
            self.wifi_disconnected_since_ms = None
            return False
        if self.wifi_disconnected_since_ms is None:
            self.wifi_disconnected_since_ms = now_ms
            return False
        return (now_ms - self.wifi_disconnected_since_ms) >= int(self.cfg["WIFI_AP_FALLBACK_AFTER_MS"])

    def on_connectivity_changed(self, online_now: bool, now_ms: int) -> dict[str, bool]:
        tr = {"became_offline": False, "became_online": False, "close_door": False, "beep": False, "need_resync": False}
        if online_now == self.server_online:
            return tr
        if not online_now:
            self.server_online = False
            self.offline_since_ms = now_ms
            tr["became_offline"] = True
            tr["close_door"] = True
            tr["beep"] = self.has_ever_been_online
            for door_id in _devices_of_type("door"):
                if self.states[door_id]:
                    self.states[door_id] = False
                    self.dirty_mask |= self._dev_bit(door_id)
                    self._push_event(door_id, False, "offline_fail_safe", 0)
            for siren_id in _devices_of_type("siren"):
                if self.states[siren_id]:
                    self.actuator_started_ms[siren_id] = now_ms
        else:
            self.server_online = True
            self.last_offline_duration_ms = now_ms - self.offline_since_ms
            for siren_id in _devices_of_type("siren"):
                self.actuator_started_ms.pop(siren_id, None)
            tr["became_online"] = True
            if self.dirty_mask != 0 or self.events or self.has_ever_been_online:
                self.pending_resync = True
                tr["need_resync"] = True
            self.has_ever_been_online = True
        return tr

    def record_change(self, dev_id: str, state_on: bool, now_ms: int, reason: str, clear_pump_lock: bool = False) -> None:
        dev_type = self._dev_type(dev_id)
        if dev_type == "pump" and clear_pump_lock:
            self.pump_safety_locked_until_wet = False
        prev = self.states[dev_id]
        self.states[dev_id] = state_on
        if dev_type == "pump":
            if state_on and not prev:
                self.actuator_started_ms[dev_id] = now_ms
            elif not state_on:
                self.actuator_started_ms.pop(dev_id, None)
        if dev_type == "siren":
            if state_on and not self.server_online:
                if not prev or dev_id not in self.actuator_started_ms:
                    self.actuator_started_ms[dev_id] = now_ms
            elif not state_on:
                self.actuator_started_ms.pop(dev_id, None)
        if not self.server_online:
            self.dirty_mask |= self._dev_bit(dev_id)
            self._push_event(dev_id, state_on, reason, now_ms - self.offline_since_ms)

    def tick_safety_timers(self, now_ms: int) -> dict[str, bool]:
        trips = {"pump_tripped": False, "siren_tripped": False}
        for pump_id in _devices_of_type("pump"):
            started = self.actuator_started_ms.get(pump_id)
            if self.states[pump_id] and started is not None and (now_ms - started) >= OFFLINE_ACTUATOR_MAX_RUN_MS[pump_id]:
                self.states[pump_id] = False
                self.actuator_started_ms.pop(pump_id, None)
                self.pump_safety_locked_until_wet = True
                trips["pump_tripped"] = True
                if not self.server_online:
                    self.dirty_mask |= self._dev_bit(pump_id)
                    self._push_event(pump_id, False, "pump_max_runtime", now_ms - self.offline_since_ms)

        for siren_id in _devices_of_type("siren"):
            started = self.actuator_started_ms.get(siren_id)
            if (
                not self.server_online
                and self.states[siren_id]
                and started is not None
                and (now_ms - started) >= OFFLINE_ACTUATOR_MAX_RUN_MS[siren_id]
            ):
                self.states[siren_id] = False
                self.actuator_started_ms.pop(siren_id, None)
                trips["siren_tripped"] = True
                self.dirty_mask |= self._dev_bit(siren_id)
                self._push_event(siren_id, False, "siren_max_runtime", now_ms - self.offline_since_ms)
        return trips

    def _match_device(self, norm: str) -> str | None:
        # Match longest registry phrase first so specific names win cleanly
        best_dev: str | None = None
        best_len = 0
        for dev_id, phrases in self._phrase_map.items():
            for phrase in phrases:
                if _contains_phrase(norm, phrase) and len(phrase) > best_len:
                    best_dev = dev_id
                    best_len = len(phrase)
        return best_dev

    def handle_text(self, text: str, now_ms: int) -> dict[str, object]:
        norm = _normalize_vi_ascii(text)
        forbidden_keywords = (
            "hen gio", "dat lich", "tao lich", "lich trinh", "phut nua", "giay nua", "gio nua",
            "tu dong", "tao luat", "them luat", "luat moi", "luat tu dong", "dieu kien", "neu",
            "khi nao", "tao lenh", "them lenh", "lenh tuy chinh", "khau lenh", "tuy chinh",
            "vung oi", "kich ban", "che do ngu", "che do ra ngoai", "che do ve nha", "che do chieu",
            "schedule", "timer", "cron", "custom", "automation", "rule", "create_timer", "add_rule",
        )
        if any(_contains_phrase(norm, p) for p in forbidden_keywords) or (
            _contains_phrase(norm, "sau")
            and any(_contains_phrase(norm, u) for u in ("phut", "giay", "gio"))
        ):
            return {
                "ok": False,
                "refused": True,
                "http_status": 400,
                "reason_code": self.cfg["REASON_CUSTOM_FORBIDDEN"],
                "reply_vi": self.cfg["REPLY_CUSTOM_FORBIDDEN_VI"],
            }

        open_verb = _normalize_vi_ascii(ACTION_VI_LABEL["open"])
        close_verb = _normalize_vi_ascii(ACTION_VI_LABEL["close"])
        on_verb = _normalize_vi_ascii(ACTION_VI_LABEL["turn_on"])
        off_verb = _normalize_vi_ascii(ACTION_VI_LABEL["turn_off"])

        has_open = any(_contains_phrase(norm, w) for w in (open_verb, "open", "unlock"))
        has_close = any(_contains_phrase(norm, w) for w in (close_verb, "khoa", "close", "lock"))
        has_on_dev = any(_contains_phrase(norm, w) for w in (on_verb, "turn_on", "on")) or has_open
        has_off_dev = any(_contains_phrase(norm, w) for w in (off_verb, "ngat", "dung", "turn_off", "off"))

        dev_id = self._match_device(norm)
        if dev_id is not None and self._dev_type(dev_id) == "door":
            if (has_close or has_off_dev) and not has_open:
                action = "close"
            elif has_open or has_on_dev:
                action = "open"
            else:
                action = ""
            if action and is_offline_action_forbidden(dev_id, action):
                self.states[dev_id] = False
                return {
                    "ok": False,
                    "refused": True,
                    "http_status": 403,
                    "device_id": dev_id,
                    "state": OFFLINE_SAFETY_DEFAULTS[dev_id],
                    "reason_code": self.cfg["REASON_DOOR_OPEN_FORBIDDEN"],
                    "reply_vi": self.cfg["REPLY_DOOR_OPEN_FORBIDDEN_VI"],
                }
            if action and is_offline_action_allowed(dev_id, action):
                self.record_change(dev_id, False, now_ms, "offline_voice")
                return {
                    "ok": True,
                    "refused": False,
                    "http_status": 200,
                    "device_id": dev_id,
                    "state": ACTION_TO_STATE[action],
                    "reason_code": self.cfg["REASON_OK"],
                }

        if not has_on_dev and not has_off_dev and any(
            _contains_phrase(norm, p)
            for p in ("trang thai", "tinh trang", "kiem tra", "bao cao", "nhiet do", "do am", "status", "state")
        ):
            return {"ok": True, "refused": False, "http_status": 200, "reason_code": self.cfg["REASON_STATUS_OK"]}

        if dev_id is None or (not has_on_dev and not has_off_dev):
            return {
                "ok": False,
                "refused": True,
                "http_status": 400,
                "reason_code": self.cfg["REASON_CUSTOM_FORBIDDEN"],
                "reply_vi": self.cfg["REPLY_CUSTOM_FORBIDDEN_VI"],
            }

        target_on = has_on_dev and not has_off_dev
        action = "turn_on" if target_on else "turn_off"
        if not is_offline_action_allowed(dev_id, action):
            return {
                "ok": False,
                "refused": True,
                "http_status": 400,
                "reason_code": self.cfg["REASON_CUSTOM_FORBIDDEN"],
                "reply_vi": self.cfg["REPLY_CUSTOM_FORBIDDEN_VI"],
            }

        self.record_change(dev_id, target_on, now_ms, "offline_voice", clear_pump_lock=True)
        return {
            "ok": True,
            "refused": False,
            "http_status": 200,
            "device_id": dev_id,
            "state": ACTION_TO_STATE[action],
            "reason_code": self.cfg["REASON_OK"],
        }


# ---------------------------------------------------------------------------
# 1. Pure C++ header purity, SSOT alignment & Wokwi mirror parity
# ---------------------------------------------------------------------------
def test_pure_cpp_headers_have_zero_arduino_includes_and_match_ssot() -> None:
    from hardware.wiring_contract import FIRMWARE_PIN_CONTRACT

    for hdr in (CONFIG_H, GRAMMAR_H, FSM_H):
        assert hdr.exists(), f"Missing pure C++ header: {hdr}"
        content = hdr.read_text(encoding="utf-8")
        for forbidden in ("<Arduino.h>", "<ESP8266", "<Servo.h>", "<DHT.h>", "<PubSubClient.h>", "<ArduinoJson.h>", "delay("):
            assert forbidden not in content, f"{hdr.name} must not depend on Arduino/blocking API: {forbidden}"

    cfg = _load_config_constants()

    # Exact parity against backend.engine.offline_contract SSOT (zero hardcoded timing literals)
    assert cfg["OFFLINE_ROLE_CHECK_ENABLED"] is OFFLINE_ROLE_CHECK_ENABLED
    assert cfg["OFFLINE_CUSTOM_COMMANDS_ALLOWED"] is OFFLINE_CUSTOM_COMMANDS_ALLOWED
    assert cfg["OFFLINE_AUTOMATION_MUTATION_ALLOWED"] is OFFLINE_AUTOMATION_MUTATION_ALLOWED
    assert cfg["OFFLINE_STATUS_QUERY_ALLOWED"] is OFFLINE_STATUS_QUERY_ALLOWED
    assert cfg["OFFLINE_MAIN_DOOR_OPEN_ALLOWED"] is False

    assert cfg["WIFI_BACKOFF_INITIAL_MS"] == WIFI_BACKOFF_INITIAL_MS
    assert cfg["WIFI_BACKOFF_MAX_MS"] == WIFI_BACKOFF_MAX_MS
    assert cfg["WIFI_BACKOFF_MULTIPLIER"] == WIFI_BACKOFF_MULTIPLIER
    assert cfg["SERVER_BACKOFF_INITIAL_MS"] == SERVER_BACKOFF_INITIAL_MS
    assert cfg["SERVER_BACKOFF_MAX_MS"] == SERVER_BACKOFF_MAX_MS
    assert cfg["SERVER_BACKOFF_MULTIPLIER"] == SERVER_BACKOFF_MULTIPLIER
    assert cfg["HEARTBEAT_INTERVAL_MS"] == HEARTBEAT_INTERVAL_MS
    assert cfg["PUMP_MAX_CONTINUOUS_RUN_MS"] == PUMP_MAX_CONTINUOUS_RUN_MS
    assert cfg["SIREN_MAX_OFFLINE_RUN_MS"] == SIREN_MAX_OFFLINE_RUN_MS
    assert cfg["SPEAKER_AMP_IDLE_TAIL_DEFAULT_MS"] == SPEAKER_AMP_IDLE_TAIL_MS
    assert cfg["OFFLINE_LED_CYCLE_MS"] == OFFLINE_LED_CYCLE_MS

    # Structural invariants for local indicators / SoftAP / thresholds (no magic numbers)
    assert int(cfg["OFFLINE_HTTP_PORT"]) > 0
    assert int(cfg["WIFI_AP_FALLBACK_AFTER_MS"]) > 0
    assert int(cfg["OFFLINE_LED_PULSES_PER_CYCLE"]) >= 2
    led_burst_ms = (
        int(cfg["OFFLINE_LED_PULSES_PER_CYCLE"]) * int(cfg["OFFLINE_LED_PULSE_MS"])
        + (int(cfg["OFFLINE_LED_PULSES_PER_CYCLE"]) - 1) * int(cfg["OFFLINE_LED_GAP_MS"])
    )
    assert 0 < led_burst_ms < int(cfg["OFFLINE_LED_CYCLE_MS"])
    assert int(cfg["OFFLINE_DISCONNECT_BEEP_COUNT"]) >= 1
    assert int(cfg["OFFLINE_DISCONNECT_BEEP_MS"]) > 0
    assert 0.0 < float(cfg["SOIL_PUMP_ON_THRESHOLD_PCT"]) < float(cfg["SOIL_PUMP_OFF_THRESHOLD_PCT"]) < 100.0
    door_id = next(iter(OFFLINE_FORBIDDEN_DEVICE_ACTIONS.keys()))
    assert str(DEFAULT_DEVICES[door_id]["name"]).lower() in str(cfg["REPLY_DOOR_OPEN_FORBIDDEN_VI"]).lower()

    # Verify DEVICE_POLICIES in offline_safety_config.h matches DEFAULT_DEVICES & offline_contract 1-to-1
    policies = cfg["DEVICE_POLICIES"]
    assert isinstance(policies, list)
    assert tuple(p["id"] for p in policies) == tuple(DEFAULT_DEVICES.keys())
    for pol in policies:
        dev_id = str(pol["id"])
        allowed = OFFLINE_ALLOWED_DEVICE_ACTIONS[dev_id]
        forbidden = OFFLINE_FORBIDDEN_DEVICE_ACTIONS.get(dev_id, ())
        is_door = str(DEFAULT_DEVICES[dev_id].get("type") or "") == "door"
        on_act = "open" if is_door else "turn_on"
        off_act = "close" if is_door else "turn_off"
        assert pol["allow_offline_on_or_open"] is (on_act in allowed and on_act not in forbidden)
        assert pol["allow_offline_off_or_close"] is (off_act in allowed)
        assert pol["off_state"] == OFFLINE_SAFETY_DEFAULTS[dev_id]

    # Verify 10 locked pins & soil SSOT constants in esp8266_smarthome.ino
    ino = INO_PATH.read_text(encoding="utf-8")
    for macro, (_dx, gpio, _lbl) in FIRMWARE_PIN_CONTRACT.items():
        expected_val = "A0" if gpio == -1 else str(gpio)
        assert re.search(rf"#define\s+{macro}\s+{expected_val}\b", ino), f"Pin mismatch in .ino: {macro} -> {expected_val}"
    assert "soilPct < SOIL_PUMP_ON_THRESHOLD_PCT" in ino
    assert "soilPct >= SOIL_PUMP_OFF_THRESHOLD_PCT" in ino

    # Verify Wokwi sketch shares headers/SSOT constants and keeps POST marker
    wokwi = WOKWI_SKETCH.read_text(encoding="utf-8")
    assert "offline_safety_config.h" in wokwi
    assert f"{PUMP_MAX_CONTINUOUS_RUN_MS}UL" in wokwi
    assert f"{SIREN_MAX_OFFLINE_RUN_MS}UL" in wokwi
    assert "WOKWI_SOIL_PUMP_ON_THRESHOLD_PCT" in wokwi
    assert "WOKWI_SOIL_PUMP_OFF_THRESHOLD_PCT" in wokwi
    assert "WOKWI_POST_OK: 6_DEVICES_3_SENSORS" in wokwi
    assert str(cfg["REPLY_DOOR_OPEN_FORBIDDEN_VI"]) in wokwi


# ---------------------------------------------------------------------------
# 2. Standalone C++ syntax/type/static_assert compilation (zero Arduino)
# ---------------------------------------------------------------------------
def _find_cpp_compiler() -> tuple[str, bool] | None:
    for candidate in ("g++", "clang++"):
        found = shutil.which(candidate)
        if found:
            return (found, True)

    pio_roots = []
    if os.environ.get("PLATFORMIO_CORE_DIR"):
        pio_roots.append(pathlib.Path(os.environ["PLATFORMIO_CORE_DIR"]))
    pio_roots.append(pathlib.Path.home() / ".platformio")
    for root in pio_roots:
        for exe_name in ("xtensa-lx106-elf-g++.exe", "xtensa-lx106-elf-g++"):
            pio_gpp = root / "packages" / "toolchain-xtensa" / "bin" / exe_name
            if pio_gpp.exists():
                return (str(pio_gpp), False)
    return None


def test_pure_cpp_headers_compile_cleanly_standalone() -> None:
    compiler_info = _find_cpp_compiler()
    if compiler_info is None:
        pytest.skip("No C++ compiler found (install PlatformIO espressif8266 toolchain or g++)")

    compiler, can_run_native = compiler_info
    cfg = _load_config_constants()
    policies = {str(p["id"]): str(p["enum_name"]) for p in cfg["DEVICE_POLICIES"]}  # type: ignore[index]

    door_id = next(iter(OFFLINE_FORBIDDEN_DEVICE_ACTIONS.keys()))
    door_forb_act = OFFLINE_FORBIDDEN_DEVICE_ACTIONS[door_id][0]
    door_open_vi = f"{ACTION_VI_LABEL[door_forb_act].lower()} {DEFAULT_DEVICES[door_id]['name'].lower()}"

    light_id = next(iter(_devices_of_type("light")))
    light_on_vi = f"[tier3] {ACTION_VI_LABEL['turn_on'].lower()} {DEFAULT_DEVICES[light_id]['name'].lower()}"

    pump_id = next(iter(_devices_of_type("pump")))
    pump_on_vi = f"{ACTION_VI_LABEL['turn_on'].lower()} {DEFAULT_DEVICES[pump_id]['name'].lower()}"
    sched_vi = f"hẹn giờ {pump_on_vi} sau 5 phút"

    siren_id = next(iter(_devices_of_type("siren")))
    siren_on_vi = f"{ACTION_VI_LABEL['turn_on'].lower()} {DEFAULT_DEVICES[siren_id]['name'].lower()}"

    harness_cpp = f"""
#include <assert.h>
#include <string.h>
#include "offline_safety_config.h"
#include "offline_command_grammar.h"
#include "offline_fsm.h"

using namespace smarthome::offline;

static_assert(DEV_COUNT == {len(DEFAULT_DEVICES)}, "Device count must match DEFAULT_DEVICES");
static_assert(OFFLINE_ROLE_CHECK_ENABLED == {str(OFFLINE_ROLE_CHECK_ENABLED).lower()}, "A2 role check parity");
static_assert(OFFLINE_CUSTOM_COMMANDS_ALLOWED == {str(OFFLINE_CUSTOM_COMMANDS_ALLOWED).lower()}, "A2 custom parity");
static_assert(!OFFLINE_MAIN_DOOR_OPEN_ALLOWED, "A3 door open forbidden offline");
static_assert(PUMP_MAX_CONTINUOUS_RUN_MS == {PUMP_MAX_CONTINUOUS_RUN_MS}UL, "Pump max runtime parity");
static_assert(SIREN_MAX_OFFLINE_RUN_MS == {SIREN_MAX_OFFLINE_RUN_MS}UL, "Siren max offline runtime parity");
static_assert(WIFI_BACKOFF_INITIAL_MS == {WIFI_BACKOFF_INITIAL_MS}UL &&
              WIFI_BACKOFF_MAX_MS == {WIFI_BACKOFF_MAX_MS}UL, "Backoff bounds parity");

int main() {{
  ExponentialBackoff bo(WIFI_BACKOFF_INITIAL_MS, WIFI_BACKOFF_MAX_MS, WIFI_BACKOFF_MULTIPLIER);
  assert(bo.shouldAttempt(0));
  unsigned long now = 0;
  unsigned long expected = WIFI_BACKOFF_INITIAL_MS;
  for (int i = 0; i < 7; ++i) {{
    unsigned long wait = bo.recordFailure(now);
    assert(wait == expected);
    assert(!bo.shouldAttempt(now + wait - 1UL));
    assert(bo.shouldAttempt(now + wait));
    now += wait;
    expected = (expected * WIFI_BACKOFF_MULTIPLIER > WIFI_BACKOFF_MAX_MS)
                   ? WIFI_BACKOFF_MAX_MS
                   : (expected * WIFI_BACKOFF_MULTIPLIER);
  }}
  bo.recordSuccess();
  assert(bo.current_delay_ms == WIFI_BACKOFF_INITIAL_MS);

  OfflineFsm fsm;
  fsm.begin(0);
  assert(!fsm.canSetMainDoor(true));
  OfflineCommandResult r_door = fsm.handleOfflineTextCommand("{door_open_vi}", 1000);
  assert(!r_door.ok && r_door.refused && r_door.http_status == 403);
  assert(strcmp(r_door.reason_code, REASON_DOOR_OPEN_FORBIDDEN) == 0);
  assert(strcmp(r_door.reply_vi, REPLY_DOOR_OPEN_FORBIDDEN_VI) == 0);

  OfflineCommandResult r_light = fsm.handleOfflineTextCommand("{light_on_vi}", 2000);
  assert(r_light.ok && !r_light.refused && r_light.http_status == 200);
  assert(fsm.getDeviceState({policies[light_id]}));
  assert(fsm.isDeviceDirtyOffline({policies[light_id]}));

  OfflineCommandResult r_sched = fsm.handleOfflineTextCommand("{sched_vi}", 2500);
  assert(!r_sched.ok && r_sched.refused && r_sched.http_status == 400);
  assert(strcmp(r_sched.reason_code, REASON_CUSTOM_FORBIDDEN) == 0);

  const unsigned long t0 = 3000UL;
  OfflineCommandResult r_pump = fsm.handleOfflineTextCommand("{pump_on_vi}", t0);
  assert(r_pump.ok && fsm.getDeviceState({policies[pump_id]}));
  OfflineCommandResult r_siren = fsm.handleOfflineTextCommand("{siren_on_vi}", t0);
  assert(r_siren.ok && fsm.getDeviceState({policies[siren_id]}));
  SafetyTripResult t1 = fsm.tickSafetyTimers(t0 + SIREN_MAX_OFFLINE_RUN_MS);
  assert(!t1.pump_tripped && t1.siren_tripped);
  assert(!fsm.getDeviceState({policies[siren_id]}));
  SafetyTripResult t2 = fsm.tickSafetyTimers(t0 + PUMP_MAX_CONTINUOUS_RUN_MS);
  assert(t2.pump_tripped && !fsm.getDeviceState({policies[pump_id]}));
  assert(fsm.isPumpSafetyLocked());

  ConnectivityTransition tr = fsm.onConnectivityChanged(true, t0 + PUMP_MAX_CONTINUOUS_RUN_MS + 1000UL);
  assert(tr.became_online && tr.need_resync && fsm.hasPendingResync());
  assert(fsm.events().count() >= 4);
  fsm.markResyncCompleted();
  assert(!fsm.hasPendingResync() && fsm.offlineDirtyMask() == 0);

  fsm.syncHardwareState({policies[door_id]}, true, t0 + PUMP_MAX_CONTINUOUS_RUN_MS + 2000UL);
  ConnectivityTransition tr_off = fsm.onConnectivityChanged(false, t0 + PUMP_MAX_CONTINUOUS_RUN_MS + 3000UL);
  assert(tr_off.became_offline && tr_off.close_door_for_safety && tr_off.trigger_disconnect_beep);
  assert(!fsm.getDeviceState({policies[door_id]}));

  return 0;
}}
"""
    with tempfile.TemporaryDirectory() as td:
        src_path = pathlib.Path(td) / "test_offline_harness.cpp"
        src_path.write_text(harness_cpp, encoding="utf-8")
        if can_run_native:
            bin_path = pathlib.Path(td) / "test_offline_harness.exe"
            comp = subprocess.run(
                [compiler, "-std=gnu++17", "-Wall", "-Wextra", "-Werror", f"-I{FW_DIR}", str(src_path), "-o", str(bin_path)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            assert comp.returncode == 0, f"C++ compile failed:\n{comp.stdout}\n{comp.stderr}"
            run = subprocess.run([str(bin_path)], capture_output=True, text=True, timeout=15, check=False)
            assert run.returncode == 0, f"C++ native test binary failed:\n{run.stdout}\n{run.stderr}"
        else:
            comp = subprocess.run(
                [compiler, "-std=gnu++17", "-Wall", "-Wextra", "-Werror", "-fsyntax-only", f"-I{FW_DIR}", str(src_path)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            assert comp.returncode == 0, f"Standalone xtensa C++ header compile failed:\n{comp.stdout}\n{comp.stderr}"


# ---------------------------------------------------------------------------
# 3. PlatformIO config & ESP8266 firmware structural invariants (A1..A4)
# ---------------------------------------------------------------------------
def test_platformio_ini_and_esp8266_ino_offline_contract() -> None:
    assert PIO_INI.exists(), "Missing firmware/esp8266_smarthome/platformio.ini"
    ini = PIO_INI.read_text(encoding="utf-8")
    for token in (
        "src_dir = .",
        "platform = espressif8266",
        "board = nodemcuv2",
        "PubSubClient",
        "ArduinoJson",
        "DHT sensor library",
        "Adafruit Unified Sensor",
    ):
        assert token in ini, f"platformio.ini missing required setting: {token}"

    ino = INO_PATH.read_text(encoding="utf-8")

    # A1: Local LAN ESP8266WebServer + mDNS + SoftAP fallback
    assert "#include <ESP8266WebServer.h>" in ino
    assert "#include <ESP8266mDNS.h>" in ino
    assert 'offlineServer.on("/offline/cmd"' in ino
    assert 'offlineServer.on("/offline/status"' in ino
    assert "offlineServer.handleClient();" in ino
    assert "WIFI_AP_STA" in ino
    assert "WiFi.softAP(" in ino

    # A2: Zero role checks offline
    for legacy_role_tok in ("[tier3]", "[khach]", "[stranger]", "[nguoi_la]", "TINY-DSP"):
        assert legacy_role_tok not in ino, f"Legacy offline role filter must be removed (A2): {legacy_role_tok}"

    # A3: Firmware door-open lock inside setMainDoorState()
    door_fn = re.search(r"bool\s+setMainDoorState\(bool\s+openDoor\)\s*\{(.*?)\n\}", ino, flags=re.S)
    assert door_fn is not None, "setMainDoorState must return bool and guard offline opening"
    door_body = door_fn.group(1)
    assert "!isServerOnline()" in door_body
    assert "doorServo.write(0);" in door_body
    assert "return false;" in door_body

    # A4: Heartbeat + Resync BEFORE pollLaptopHttpState()
    assert "/api/hardware/heartbeat" in ino
    assert "/api/hardware/resync" in ino
    assert 'mqtt.publish("smarthome/state/report"' in ino
    resync_branch = ino.index("if (onlineNow && offlineFsm.hasPendingResync())")
    poll_branch = ino.index("pollLaptopHttpState(now);", resync_branch)
    assert resync_branch < poll_branch

    # Anti-hang / Watchdog safety: zero blocking delay() and zero ESP.restart() reboot loops
    assert "ESP.restart" not in ino
    assert "delay(" not in ino, "esp8266_smarthome.ino must not use blocking delay() calls"
    assert "yield();" in ino

    # README documents Vietnamese offline LED/buzzer + A1..A4
    readme = FW_README.read_text(encoding="utf-8")
    for section_tok in ("Addendum A1", "Addendum A2", "Addendum A3", "Addendum A4", "/offline/cmd", "/api/hardware/resync", "pio run"):
        assert section_tok in readme


# ---------------------------------------------------------------------------
# 4. Deterministic behavioral tests (Backoff, LED, Beeper, Timers, A1..A4)
# ---------------------------------------------------------------------------
def test_exponential_backoff_sequence_and_reset() -> None:
    bo = _BackoffModel(WIFI_BACKOFF_INITIAL_MS, WIFI_BACKOFF_MAX_MS, WIFI_BACKOFF_MULTIPLIER)
    expected: list[int] = []
    cur = WIFI_BACKOFF_INITIAL_MS
    for _ in range(7):
        expected.append(cur)
        cur = min(cur * WIFI_BACKOFF_MULTIPLIER, WIFI_BACKOFF_MAX_MS)

    now = 0
    observed: list[int] = []
    for _ in expected:
        assert bo.should_attempt(now)
        wait = bo.record_failure(now)
        observed.append(wait)
        assert not bo.should_attempt(now + wait - 1)
        now += wait
    assert observed == expected

    bo.record_success()
    assert bo.current_delay_ms == WIFI_BACKOFF_INITIAL_MS
    assert bo.attempts == 0
    assert bo.should_attempt(now)


def test_online_to_offline_fail_safe_closes_door_and_beeps_once() -> None:
    cfg = _load_config_constants()
    fsm = _OfflineFsmModel(cfg)
    fsm.on_connectivity_changed(True, HEARTBEAT_INTERVAL_MS)

    door_ids = _devices_of_type("door")
    assert door_ids, "Expected at least one door device in DEFAULT_DEVICES"
    for door_id in door_ids:
        fsm.states[door_id] = True

    tr = fsm.on_connectivity_changed(False, HEARTBEAT_INTERVAL_MS * 2)
    assert tr["became_offline"] is True
    assert tr["close_door"] is True
    assert tr["beep"] is True
    for door_id in door_ids:
        assert fsm.states[door_id] is False
        matching = [e for e in fsm.events if e["device_id"] == door_id and e["reason"] == "offline_fail_safe"]
        assert matching and matching[-1]["state"] == OFFLINE_SAFETY_DEFAULTS[door_id]

    # One-shot disconnect beeper timing derived strictly from offline_safety_config.h
    beep_ms = int(cfg["OFFLINE_DISCONNECT_BEEP_MS"])
    gap_ms = int(cfg["OFFLINE_DISCONNECT_BEEP_GAP_MS"])
    beep_count = int(cfg["OFFLINE_DISCONNECT_BEEP_COUNT"])
    period = beep_ms + gap_ms
    total = (beep_count - 1) * period + beep_ms

    def beep_at(elapsed: int) -> bool:
        return elapsed < total and (elapsed % period) < beep_ms

    for idx in range(beep_count):
        slot_start = idx * period
        assert beep_at(slot_start) is True
        assert beep_at(slot_start + beep_ms - 1) is True
        if idx < beep_count - 1:
            assert beep_at(slot_start + beep_ms) is False
            assert beep_at(slot_start + period - 1) is False
    assert beep_at(total) is False
    assert beep_at(total + OFFLINE_LED_CYCLE_MS) is False


def test_offline_led_double_blink_cadence_and_user_state_restore() -> None:
    cfg = _load_config_constants()
    cycle = int(cfg["OFFLINE_LED_CYCLE_MS"])
    pulse = int(cfg["OFFLINE_LED_PULSE_MS"])
    gap = int(cfg["OFFLINE_LED_GAP_MS"])
    p2_start = pulse + gap
    p2_end = p2_start + pulse

    def led_out(user_on: bool, is_online: bool, elapsed: int) -> bool:
        if is_online:
            return user_on
        e = elapsed % cycle
        in_pulse = (e < pulse) or (p2_start <= e < p2_end)
        return (not user_on) if in_pulse else user_on

    # User light OFF: pulses HIGH during pulse 1 & pulse 2, OFF otherwise
    assert led_out(False, False, 0) is True
    assert led_out(False, False, pulse - 1) is True
    assert led_out(False, False, pulse) is False
    assert led_out(False, False, p2_start - 1) is False
    assert led_out(False, False, p2_start) is True
    assert led_out(False, False, p2_end - 1) is True
    assert led_out(False, False, p2_end) is False
    assert led_out(False, False, cycle - 1) is False
    assert led_out(False, False, cycle) is True

    # User light ON: dips LOW during pulse, restores ON cleanly afterward
    assert led_out(True, False, pulse // 2) is False
    assert led_out(True, False, p2_end + 1) is True
    # Online: always reflects user light immediately
    assert led_out(True, True, pulse // 2) is True
    assert led_out(False, True, pulse // 2) is False


def test_safety_timers_pump_120s_lockout_and_siren_30s_offline() -> None:
    cfg = _load_config_constants()
    fsm = _OfflineFsmModel(cfg)

    pump_id = next(iter(_devices_of_type("pump")))
    siren_id = next(iter(_devices_of_type("siren")))
    pump_limit_ms = OFFLINE_ACTUATOR_MAX_RUN_MS[pump_id]
    siren_limit_ms = OFFLINE_ACTUATOR_MAX_RUN_MS[siren_id]
    assert siren_limit_ms < pump_limit_ms

    t0 = HEARTBEAT_INTERVAL_MS
    fsm.record_change(pump_id, True, t0, "soil_auto_offline")
    fsm.record_change(siren_id, True, t0, "offline_voice")

    assert fsm.tick_safety_timers(t0 + siren_limit_ms - 1) == {"pump_tripped": False, "siren_tripped": False}
    assert fsm.tick_safety_timers(t0 + siren_limit_ms) == {"pump_tripped": False, "siren_tripped": True}
    assert fsm.states[siren_id] is False
    assert fsm.events[-1]["device_id"] == siren_id
    assert fsm.events[-1]["reason"] == "siren_max_runtime"

    assert fsm.tick_safety_timers(t0 + pump_limit_ms - 1) == {"pump_tripped": False, "siren_tripped": False}
    assert fsm.tick_safety_timers(t0 + pump_limit_ms) == {"pump_tripped": True, "siren_tripped": False}
    assert fsm.states[pump_id] is False
    assert fsm.pump_safety_locked_until_wet is True
    assert fsm.events[-1]["device_id"] == pump_id
    assert fsm.events[-1]["reason"] == "pump_max_runtime"


def test_addendum_a2_fixed_basic_commands_zero_roles_and_custom_refusal() -> None:
    cfg = _load_config_constants()
    fsm = _OfflineFsmModel(cfg)

    # Dynamically generate the entire allowed offline command matrix from registry + SSOT contract
    role_prefixes = ("", "[tier3] ", "[khach] ", "[stranger] ")
    step = 0
    for dev_id, allowed_actions in OFFLINE_ALLOWED_DEVICE_ACTIONS.items():
        dev_name_vi = str(DEFAULT_DEVICES[dev_id]["name"]).lower()
        for action in allowed_actions:
            prefix = role_prefixes[step % len(role_prefixes)]
            verb_vi = ACTION_VI_LABEL[action].lower()
            cmd_text = f"{prefix}{verb_vi} {dev_name_vi}"
            expected_state = ACTION_TO_STATE[action]
            res = fsm.handle_text(cmd_text, HEARTBEAT_INTERVAL_MS + step * 100)
            assert res["ok"] is True and res["http_status"] == 200, f"Expected OK for {cmd_text!r}, got {res}"
            assert res["device_id"] == dev_id and res["state"] == expected_state
            step += 1

    assert step >= len(DEFAULT_DEVICES), "Dynamic A2 matrix must cover every canonical device"

    st_res = fsm.handle_text("kiểm tra trạng thái thiết bị", HEARTBEAT_INTERVAL_MS + step * 100)
    assert st_res["ok"] is True and st_res["reason_code"] == cfg["REASON_STATUS_OK"]

    # Dynamically compose custom, schedule, automation, and unsupported-device refusals (HTTP 400)
    sample_toggle_id = next(
        dev_id for dev_id, acts in OFFLINE_ALLOWED_DEVICE_ACTIONS.items() if "turn_on" in acts and "turn_off" in acts
    )
    sample_name_vi = str(DEFAULT_DEVICES[sample_toggle_id]["name"]).lower()
    on_vi = ACTION_VI_LABEL["turn_on"].lower()
    off_vi = ACTION_VI_LABEL["turn_off"].lower()
    refused_cmds = (
        "vừng ơi mở ra",
        f"hẹn giờ {off_vi} {sample_name_vi}",
        f"{on_vi} {sample_name_vi} sau 5 phút",
        f"đặt lịch {on_vi} {sample_name_vi} lúc 6 giờ",
        f"nếu nhiệt độ lớn hơn 35 thì {on_vi} {sample_name_vi}",
        "tạo lệnh tùy chỉnh đi ngủ",
        f"{on_vi} thiết bị không tồn tại xyz",
    )
    for idx, refused_cmd in enumerate(refused_cmds):
        res = fsm.handle_text(refused_cmd, HEARTBEAT_INTERVAL_MS * 2 + idx * 100)
        assert res["ok"] is False and res["refused"] is True and res["http_status"] == 400, f"Must refuse {refused_cmd!r}"
        assert res["reason_code"] == cfg["REASON_CUSTOM_FORBIDDEN"]


def test_addendum_a3_main_door_open_absolutely_forbidden_offline() -> None:
    cfg = _load_config_constants()
    fsm = _OfflineFsmModel(cfg)

    assert OFFLINE_FORBIDDEN_DEVICE_ACTIONS, "Expected at least one forbidden offline device action"
    for dev_id, forbidden_actions in OFFLINE_FORBIDDEN_DEVICE_ACTIONS.items():
        dev_name_vi = str(DEFAULT_DEVICES[dev_id]["name"]).lower()
        dev_name_ascii = _normalize_vi_ascii(dev_name_vi)
        safe_default = OFFLINE_SAFETY_DEFAULTS[dev_id]

        for action in forbidden_actions:
            assert fsm.can_set_device(dev_id, action) is False
            verb_vi = ACTION_VI_LABEL[action].lower()
            verb_ascii = _normalize_vi_ascii(verb_vi)
            generated_cmds = (
                f"{verb_vi} {dev_name_vi}",
                f"{verb_ascii} {dev_name_ascii}",
                f"{action} {dev_id}",
            )
            for idx, cmd in enumerate(generated_cmds):
                res = fsm.handle_text(cmd, HEARTBEAT_INTERVAL_MS + idx * 100)
                assert res["ok"] is False and res["refused"] is True and res["http_status"] == 403
                assert res["reason_code"] == cfg["REASON_DOOR_OPEN_FORBIDDEN"]
                assert res["device_id"] == dev_id and res["state"] == safe_default
                assert res["reply_vi"] == cfg["REPLY_DOOR_OPEN_FORBIDDEN_VI"]
                assert fsm.states[dev_id] is False

        # Allowed close action for the same device succeeds offline
        for allowed_action in OFFLINE_ALLOWED_DEVICE_ACTIONS[dev_id]:
            assert fsm.can_set_device(dev_id, allowed_action) is True

    # Online restores ability to execute previously offline-forbidden actions
    fsm.on_connectivity_changed(True, HEARTBEAT_INTERVAL_MS * 2)
    for dev_id, forbidden_actions in OFFLINE_FORBIDDEN_DEVICE_ACTIONS.items():
        for action in forbidden_actions:
            assert fsm.can_set_device(dev_id, action) is True


def test_addendum_a1_softap_fallback_and_a4_resync_ring_buffer() -> None:
    cfg = _load_config_constants()
    fsm = _OfflineFsmModel(cfg)

    # A1: SoftAP activates strictly after WIFI_AP_FALLBACK_AFTER_MS
    ap_after_ms = int(cfg["WIFI_AP_FALLBACK_AFTER_MS"])
    t_disc = HEARTBEAT_INTERVAL_MS
    assert fsm.should_enable_softap(False, t_disc) is False
    assert fsm.should_enable_softap(False, t_disc + ap_after_ms - 1) is False
    assert fsm.should_enable_softap(False, t_disc + ap_after_ms) is True
    assert fsm.should_enable_softap(True, t_disc + ap_after_ms + 1) is False

    # A4: Dynamically select an allowed non-door toggleable device from registry + offline contract
    target_dev_id = next(
        dev_id
        for dev_id, acts in OFFLINE_ALLOWED_DEVICE_ACTIONS.items()
        if str(DEFAULT_DEVICES[dev_id].get("type") or "") != "door" and "turn_on" in acts and "turn_off" in acts
    )
    target_name_vi = str(DEFAULT_DEVICES[target_dev_id]["name"]).lower()
    cmd_on = f"{ACTION_VI_LABEL['turn_on'].lower()} {target_name_vi}"
    cmd_off = f"{ACTION_VI_LABEL['turn_off'].lower()} {target_name_vi}"

    ring_cap = int(cfg["OFFLINE_EVENT_RING_CAPACITY"])
    for i in range(ring_cap + 4):
        res = fsm.handle_text(cmd_on if i % 2 == 0 else cmd_off, t_disc + i * 100)
        assert res["ok"] is True and res["device_id"] == target_dev_id

    assert len(fsm.events) == ring_cap
    assert fsm.dirty_mask & (1 << fsm.devices.index(target_dev_id))

    tr = fsm.on_connectivity_changed(True, t_disc + ap_after_ms)
    assert tr["became_online"] is True and tr["need_resync"] is True and fsm.pending_resync is True
