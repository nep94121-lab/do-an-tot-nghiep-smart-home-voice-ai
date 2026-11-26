"""Host-side deterministic unit tests for ESP8266 offline/lost-connection firmware (Session S2, A1..A4)."""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass, field

import pytest

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


def _parse_cpp_bool(header_text: str, name: str) -> bool:
    m = re.search(rf"\b{re.escape(name)}\s*=\s*(true|false)\s*;", header_text)
    assert m is not None, f"Missing bool constant {name} in offline_safety_config.h"
    return m.group(1) == "true"


def _parse_cpp_str(header_text: str, name: str) -> str:
    m = re.search(rf'\b{re.escape(name)}\s*=\s*\n?\s*"([^"]*)"\s*;', header_text)
    assert m is not None, f"Missing string constant {name} in offline_safety_config.h"
    return m.group(1)


def _load_config_constants() -> dict[str, object]:
    txt = CONFIG_H.read_text(encoding="utf-8")
    return {
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


# ---------------------------------------------------------------------------
# Faithful Python behavioral model driven strictly by offline_safety_config.h
# ---------------------------------------------------------------------------
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
    return f" {phrase} " in f" {norm} "


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
    server_online: bool = False
    has_ever_been_online: bool = False
    offline_since_ms: int = 0
    last_offline_duration_ms: int = 0
    pending_resync: bool = False
    dirty_mask: int = 0
    events: list[dict[str, object]] = field(default_factory=list)
    states: dict[str, bool] = field(
        default_factory=lambda: {
            "main_door": False,
            "living_room_light": False,
            "bedroom_light": False,
            "garden_pump": False,
            "alarm_siren": False,
            "speaker_amp": False,
        }
    )
    pump_started_ms: int | None = None
    pump_safety_locked_until_wet: bool = False
    siren_started_ms: int | None = None
    wifi_disconnected_since_ms: int | None = None

    DEVICES = (
        "main_door",
        "living_room_light",
        "bedroom_light",
        "garden_pump",
        "alarm_siren",
        "speaker_amp",
    )

    def _dev_bit(self, dev_id: str) -> int:
        return 1 << self.DEVICES.index(dev_id)

    def _push_event(self, dev_id: str, state_on: bool, reason: str, offset_ms: int) -> None:
        cap = int(self.cfg["OFFLINE_EVENT_RING_CAPACITY"])
        if len(self.events) >= cap:
            self.events.pop(0)
        self.events.append(
            {
                "device_id": dev_id,
                "state": ("OPEN" if state_on else "CLOSED") if dev_id == "main_door" else ("ON" if state_on else "OFF"),
                "reason": reason,
                "offset_ms": offset_ms,
            }
        )

    def can_set_main_door(self, open_door: bool) -> bool:
        if open_door and not self.server_online:
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
            if self.states["main_door"]:
                self.states["main_door"] = False
                self.dirty_mask |= self._dev_bit("main_door")
                self._push_event("main_door", False, "offline_fail_safe", 0)
            if self.states["alarm_siren"]:
                self.siren_started_ms = now_ms
        else:
            self.server_online = True
            self.last_offline_duration_ms = now_ms - self.offline_since_ms
            self.siren_started_ms = None
            tr["became_online"] = True
            if self.dirty_mask != 0 or self.events or self.has_ever_been_online:
                self.pending_resync = True
                tr["need_resync"] = True
            self.has_ever_been_online = True
        return tr

    def record_change(self, dev_id: str, state_on: bool, now_ms: int, reason: str, clear_pump_lock: bool = False) -> None:
        if dev_id == "garden_pump" and clear_pump_lock:
            self.pump_safety_locked_until_wet = False
        prev = self.states[dev_id]
        self.states[dev_id] = state_on
        if dev_id == "garden_pump":
            if state_on and not prev:
                self.pump_started_ms = now_ms
            elif not state_on:
                self.pump_started_ms = None
        if dev_id == "alarm_siren":
            if state_on and not self.server_online:
                if not prev or self.siren_started_ms is None:
                    self.siren_started_ms = now_ms
            elif not state_on:
                self.siren_started_ms = None
        if not self.server_online:
            self.dirty_mask |= self._dev_bit(dev_id)
            self._push_event(dev_id, state_on, reason, now_ms - self.offline_since_ms)

    def tick_safety_timers(self, now_ms: int) -> dict[str, bool]:
        trips = {"pump_tripped": False, "siren_tripped": False}
        if (
            self.states["garden_pump"]
            and self.pump_started_ms is not None
            and (now_ms - self.pump_started_ms) >= int(self.cfg["PUMP_MAX_CONTINUOUS_RUN_MS"])
        ):
            self.states["garden_pump"] = False
            self.pump_started_ms = None
            self.pump_safety_locked_until_wet = True
            trips["pump_tripped"] = True
            if not self.server_online:
                self.dirty_mask |= self._dev_bit("garden_pump")
                self._push_event("garden_pump", False, "pump_max_runtime", now_ms - self.offline_since_ms)

        if (
            not self.server_online
            and self.states["alarm_siren"]
            and self.siren_started_ms is not None
            and (now_ms - self.siren_started_ms) >= int(self.cfg["SIREN_MAX_OFFLINE_RUN_MS"])
        ):
            self.states["alarm_siren"] = False
            self.siren_started_ms = None
            trips["siren_tripped"] = True
            self.dirty_mask |= self._dev_bit("alarm_siren")
            self._push_event("alarm_siren", False, "siren_max_runtime", now_ms - self.offline_since_ms)
        return trips

    def handle_text(self, text: str, now_ms: int) -> dict[str, object]:
        norm = _normalize_vi_ascii(text)
        forbidden = (
            "hen gio", "dat lich", "tao lich", "lich trinh", "phut nua", "giay nua", "gio nua",
            "tu dong", "tao luat", "them luat", "luat moi", "luat tu dong", "dieu kien", "neu",
            "khi nao", "tao lenh", "them lenh", "lenh tuy chinh", "khau lenh", "tuy chinh",
            "vung oi", "kich ban", "che do ngu", "che do ra ngoai", "che do ve nha", "che do chieu",
            "schedule", "timer", "cron", "custom", "automation", "rule", "create_timer", "add_rule",
        )
        if any(_contains_phrase(norm, p) for p in forbidden) or (
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

        has_open = any(_contains_phrase(norm, w) for w in ("mo", "open", "unlock"))
        has_close = any(_contains_phrase(norm, w) for w in ("dong", "khoa", "close", "lock"))
        has_on_dev = any(_contains_phrase(norm, w) for w in ("bat", "turn_on", "on")) or has_open
        has_off_dev = any(_contains_phrase(norm, w) for w in ("tat", "ngat", "dung", "turn_off", "off"))

        if any(_contains_phrase(norm, p) for p in ("cua chinh", "cua", "main_door", "door")):
            if (has_close or has_off_dev) and not has_open:
                self.record_change("main_door", False, now_ms, "offline_voice")
                return {
                    "ok": True,
                    "refused": False,
                    "http_status": 200,
                    "device_id": "main_door",
                    "state": "CLOSED",
                    "reason_code": self.cfg["REASON_OK"],
                }
            if has_open or has_on_dev:
                self.states["main_door"] = False
                return {
                    "ok": False,
                    "refused": True,
                    "http_status": 403,
                    "device_id": "main_door",
                    "state": "CLOSED",
                    "reason_code": self.cfg["REASON_DOOR_OPEN_FORBIDDEN"],
                    "reply_vi": self.cfg["REPLY_DOOR_OPEN_FORBIDDEN_VI"],
                }

        if not has_on_dev and not has_off_dev and any(
            _contains_phrase(norm, p)
            for p in ("trang thai", "tinh trang", "kiem tra", "bao cao", "nhiet do", "do am", "status", "state")
        ):
            return {"ok": True, "refused": False, "http_status": 200, "reason_code": self.cfg["REASON_STATUS_OK"]}

        if not has_on_dev and not has_off_dev:
            return {
                "ok": False,
                "refused": True,
                "http_status": 400,
                "reason_code": self.cfg["REASON_CUSTOM_FORBIDDEN"],
                "reply_vi": self.cfg["REPLY_CUSTOM_FORBIDDEN_VI"],
            }

        target_on = has_on_dev and not has_off_dev
        dev_id = None
        if any(_contains_phrase(norm, p) for p in ("den phong khach", "den khach", "phong khach", "living_room_light", "living light")):
            dev_id = "living_room_light"
        elif any(_contains_phrase(norm, p) for p in ("den phong ngu", "den ngu", "phong ngu", "bedroom_light", "bedroom light")):
            dev_id = "bedroom_light"
        elif any(_contains_phrase(norm, p) for p in ("may bom", "bom tuoi", "tuoi cay", "bom nuoc", "bom", "garden_pump", "pump")):
            dev_id = "garden_pump"
        elif any(_contains_phrase(norm, p) for p in ("coi bao dong", "bao dong", "chuong bao dong", "coi", "alarm_siren", "siren", "buzzer")):
            dev_id = "alarm_siren"
        elif any(_contains_phrase(norm, p) for p in ("nguon mach loa", "mach loa", "nguon loa", "pam8403", "speaker_amp", "speaker", "loa")):
            dev_id = "speaker_amp"

        if dev_id is None:
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
            "state": "ON" if target_on else "OFF",
            "reason_code": self.cfg["REASON_OK"],
        }


# ---------------------------------------------------------------------------
# 1. Pure C++ header purity, SSOT alignment & Wokwi mirror parity
# ---------------------------------------------------------------------------
def test_pure_cpp_headers_have_zero_arduino_includes_and_match_ssot() -> None:
    from backend.engine.constants_and_time import DEFAULT_DEVICES
    from hardware.wiring_contract import FIRMWARE_PIN_CONTRACT

    for hdr in (CONFIG_H, GRAMMAR_H, FSM_H):
        assert hdr.exists(), f"Missing pure C++ header: {hdr}"
        content = hdr.read_text(encoding="utf-8")
        for forbidden in ("<Arduino.h>", "<ESP8266", "<Servo.h>", "<DHT.h>", "<PubSubClient.h>", "<ArduinoJson.h>", "delay("):
            assert forbidden not in content, f"{hdr.name} must not depend on Arduino/blocking API: {forbidden}"

    cfg = _load_config_constants()
    assert cfg["OFFLINE_ROLE_CHECK_ENABLED"] is False
    assert cfg["OFFLINE_CUSTOM_COMMANDS_ALLOWED"] is False
    assert cfg["OFFLINE_AUTOMATION_MUTATION_ALLOWED"] is False
    assert cfg["OFFLINE_STATUS_QUERY_ALLOWED"] is True
    assert cfg["OFFLINE_MAIN_DOOR_OPEN_ALLOWED"] is False

    assert cfg["WIFI_BACKOFF_INITIAL_MS"] == 1000
    assert cfg["WIFI_BACKOFF_MAX_MS"] == 30000
    assert cfg["WIFI_BACKOFF_MULTIPLIER"] == 2
    assert cfg["SERVER_BACKOFF_INITIAL_MS"] == 1000
    assert cfg["SERVER_BACKOFF_MAX_MS"] == 30000
    assert cfg["SERVER_BACKOFF_MULTIPLIER"] == 2
    assert cfg["HEARTBEAT_INTERVAL_MS"] == 3000
    assert cfg["OFFLINE_HTTP_PORT"] == 80
    assert cfg["WIFI_AP_FALLBACK_AFTER_MS"] == 15000
    assert cfg["PUMP_MAX_CONTINUOUS_RUN_MS"] == 120000
    assert cfg["SIREN_MAX_OFFLINE_RUN_MS"] == 30000
    assert cfg["SPEAKER_AMP_IDLE_TAIL_DEFAULT_MS"] == 1500
    assert cfg["OFFLINE_LED_CYCLE_MS"] == 4000
    assert cfg["OFFLINE_LED_PULSE_MS"] == 120
    assert cfg["OFFLINE_LED_GAP_MS"] == 160
    assert cfg["OFFLINE_DISCONNECT_BEEP_MS"] == 80
    assert cfg["OFFLINE_DISCONNECT_BEEP_COUNT"] == 2
    assert cfg["REPLY_DOOR_OPEN_FORBIDDEN_VI"] == "Đang mất kết nối máy chủ, tuyệt đối không được phép mở cửa chính."

    # Verify all 6 canonical devices in offline_safety_config.h match DEFAULT_DEVICES exactly
    cfg_text = CONFIG_H.read_text(encoding="utf-8")
    for dev_id in DEFAULT_DEVICES.keys():
        assert f'"{dev_id}"' in cfg_text, f"Device {dev_id} missing from offline_safety_config.h"
    assert '"fan"' not in cfg_text and '"ac"' not in cfg_text

    # Verify 10 locked pins in esp8266_smarthome.ino match hardware/wiring_contract.py
    ino = INO_PATH.read_text(encoding="utf-8")
    for macro, (_dx, gpio, _lbl) in FIRMWARE_PIN_CONTRACT.items():
        expected_val = "A0" if gpio == -1 else str(gpio)
        assert re.search(rf"#define\s+{macro}\s+{expected_val}\b", ino), f"Pin mismatch in .ino: {macro} -> {expected_val}"

    # Verify Wokwi sketch shares headers/constants and keeps POST marker
    wokwi = WOKWI_SKETCH.read_text(encoding="utf-8")
    assert "offline_safety_config.h" in wokwi
    assert "120000UL" in wokwi and "30000UL" in wokwi
    assert "WOKWI_POST_OK: 6_DEVICES_3_SENSORS" in wokwi
    assert "Đang mất kết nối máy chủ, tuyệt đối không được phép mở cửa chính." in wokwi

    # Verify backend/engine/offline_contract.py parity if already created by parallel track
    backend_contract = ROOT / "backend" / "engine" / "offline_contract.py"
    if backend_contract.exists():
        from backend.engine import offline_contract as oc

        assert getattr(oc, "OFFLINE_ROLE_CHECK_ENABLED", False) is cfg["OFFLINE_ROLE_CHECK_ENABLED"]
        assert getattr(oc, "OFFLINE_CUSTOM_COMMANDS_ALLOWED", False) is cfg["OFFLINE_CUSTOM_COMMANDS_ALLOWED"]


# ---------------------------------------------------------------------------
# 2. Standalone C++ syntax/type/static_assert compilation (zero Arduino)
# ---------------------------------------------------------------------------
def _find_cpp_compiler() -> tuple[str, bool] | None:
    # Prefer native host compiler if installed (can both compile and execute),
    # otherwise use PlatformIO's xtensa-lx106-elf-g++ for strict -Wall -Wextra -Werror compile check.
    import os

    for candidate in ("g++", "clang++"):
        found = shutil.which(candidate)
        if found:
            return (found, True)

    pio_roots = []
    if os.environ.get("PLATFORMIO_CORE_DIR"):
        pio_roots.append(pathlib.Path(os.environ["PLATFORMIO_CORE_DIR"]))
    pio_roots.append(pathlib.Path.home() / ".platformio")
    for root in pio_roots:
        pio_gpp = root / "packages" / "toolchain-xtensa" / "bin" / "xtensa-lx106-elf-g++.exe"
        if pio_gpp.exists():
            return (str(pio_gpp), False)
        pio_gpp_posix = root / "packages" / "toolchain-xtensa" / "bin" / "xtensa-lx106-elf-g++"
        if pio_gpp_posix.exists():
            return (str(pio_gpp_posix), False)
    return None


def test_pure_cpp_headers_compile_cleanly_standalone() -> None:
    compiler_info = _find_cpp_compiler()
    if compiler_info is None:
        pytest.skip("No C++ compiler found (install PlatformIO espressif8266 toolchain or g++)")

    compiler, can_run_native = compiler_info
    harness_cpp = r"""
#include <assert.h>
#include <string.h>
#include "offline_safety_config.h"
#include "offline_command_grammar.h"
#include "offline_fsm.h"

using namespace smarthome::offline;

static_assert(DEV_COUNT == 6, "Must have exactly 6 canonical devices");
static_assert(!OFFLINE_ROLE_CHECK_ENABLED, "A2: Zero role distinction offline");
static_assert(!OFFLINE_CUSTOM_COMMANDS_ALLOWED, "A2: No custom commands offline");
static_assert(!OFFLINE_MAIN_DOOR_OPEN_ALLOWED, "A3: Main door open forbidden offline");
static_assert(PUMP_MAX_CONTINUOUS_RUN_MS == 120000UL, "Pump max runtime 120s");
static_assert(SIREN_MAX_OFFLINE_RUN_MS == 30000UL, "Siren max offline runtime 30s");
static_assert(WIFI_BACKOFF_INITIAL_MS == 1000UL && WIFI_BACKOFF_MAX_MS == 30000UL, "Backoff bounds");

int main() {
  ExponentialBackoff bo(WIFI_BACKOFF_INITIAL_MS, WIFI_BACKOFF_MAX_MS, WIFI_BACKOFF_MULTIPLIER);
  assert(bo.shouldAttempt(0));
  assert(bo.recordFailure(0) == 1000UL);
  assert(!bo.shouldAttempt(999));
  assert(bo.shouldAttempt(1000));
  assert(bo.recordFailure(1000) == 2000UL);
  assert(bo.recordFailure(3000) == 4000UL);
  assert(bo.recordFailure(7000) == 8000UL);
  assert(bo.recordFailure(15000) == 16000UL);
  assert(bo.recordFailure(31000) == 30000UL);
  assert(bo.recordFailure(61000) == 30000UL);
  bo.recordSuccess();
  assert(bo.current_delay_ms == 1000UL);

  OfflineFsm fsm;
  fsm.begin(0);
  // A3: Cannot open door offline
  assert(!fsm.canSetMainDoor(true));
  OfflineCommandResult r_door = fsm.handleOfflineTextCommand("mở cửa chính", 1000);
  assert(!r_door.ok && r_door.refused && r_door.http_status == 403);
  assert(strcmp(r_door.reason_code, REASON_DOOR_OPEN_FORBIDDEN) == 0);
  assert(strcmp(r_door.reply_vi, REPLY_DOOR_OPEN_FORBIDDEN_VI) == 0);

  // A2: Role tag ignored offline; basic command succeeds
  OfflineCommandResult r_light = fsm.handleOfflineTextCommand("[tier3] bật đèn phòng khách", 2000);
  assert(r_light.ok && !r_light.refused && r_light.http_status == 200);
  assert(fsm.getDeviceState(DEV_LIVING_ROOM_LIGHT));
  assert(fsm.isDeviceDirtyOffline(DEV_LIVING_ROOM_LIGHT));

  // A2: Custom / schedule refused
  OfflineCommandResult r_sched = fsm.handleOfflineTextCommand("hẹn giờ bật máy bơm sau 5 phút", 2500);
  assert(!r_sched.ok && r_sched.refused && r_sched.http_status == 400);
  assert(strcmp(r_sched.reason_code, REASON_CUSTOM_FORBIDDEN) == 0);

  // Safety timers: pump 120s & siren 30s
  OfflineCommandResult r_pump = fsm.handleOfflineTextCommand("bật máy bơm tưới cây", 3000);
  assert(r_pump.ok && fsm.getDeviceState(DEV_GARDEN_PUMP));
  OfflineCommandResult r_siren = fsm.handleOfflineTextCommand("bật còi báo động", 3000);
  assert(r_siren.ok && fsm.getDeviceState(DEV_ALARM_SIREN));
  SafetyTripResult t1 = fsm.tickSafetyTimers(33000);
  assert(!t1.pump_tripped && t1.siren_tripped);
  assert(!fsm.getDeviceState(DEV_ALARM_SIREN));
  SafetyTripResult t2 = fsm.tickSafetyTimers(123000);
  assert(t2.pump_tripped && !fsm.getDeviceState(DEV_GARDEN_PUMP));
  assert(fsm.isPumpSafetyLocked());

  // A4: Reconnect triggers pending resync
  ConnectivityTransition tr = fsm.onConnectivityChanged(true, 130000);
  assert(tr.became_online && tr.need_resync && fsm.hasPendingResync());
  assert(fsm.events().count() >= 4);
  fsm.markResyncCompleted();
  assert(!fsm.hasPendingResync() && fsm.offlineDirtyMask() == 0);

  // Disconnect closes main door & triggers beep
  fsm.syncHardwareState(DEV_MAIN_DOOR, true, 131000);
  ConnectivityTransition tr_off = fsm.onConnectivityChanged(false, 132000);
  assert(tr_off.became_offline && tr_off.close_door_for_safety && tr_off.trigger_disconnect_beep);
  assert(!fsm.getDeviceState(DEV_MAIN_DOOR));

  return 0;
}
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
    cfg = _load_config_constants()
    bo = _BackoffModel(
        int(cfg["WIFI_BACKOFF_INITIAL_MS"]),
        int(cfg["WIFI_BACKOFF_MAX_MS"]),
        int(cfg["WIFI_BACKOFF_MULTIPLIER"]),
    )
    now = 0
    observed = []
    for _ in range(7):
        assert bo.should_attempt(now)
        wait = bo.record_failure(now)
        observed.append(wait)
        assert not bo.should_attempt(now + wait - 1)
        now += wait
    assert observed == [1000, 2000, 4000, 8000, 16000, 30000, 30000]

    bo.record_success()
    assert bo.current_delay_ms == 1000
    assert bo.attempts == 0
    assert bo.should_attempt(now)


def test_online_to_offline_fail_safe_closes_door_and_beeps_once() -> None:
    cfg = _load_config_constants()
    fsm = _OfflineFsmModel(cfg)
    fsm.on_connectivity_changed(True, 1000)
    fsm.states["main_door"] = True

    tr = fsm.on_connectivity_changed(False, 5000)
    assert tr["became_offline"] is True
    assert tr["close_door"] is True
    assert tr["beep"] is True
    assert fsm.states["main_door"] is False
    assert fsm.events[-1]["device_id"] == "main_door"
    assert fsm.events[-1]["state"] == "CLOSED"
    assert fsm.events[-1]["reason"] == "offline_fail_safe"

    # One-shot disconnect beeper timing: 2 x 80ms separated by 100ms = 260ms total
    beep_ms = int(cfg["OFFLINE_DISCONNECT_BEEP_MS"])
    gap_ms = int(cfg["OFFLINE_DISCONNECT_BEEP_GAP_MS"])
    period = beep_ms + gap_ms
    total = period + beep_ms
    assert total == 260
    # Pulse 1: [0, 80), Gap: [80, 180), Pulse 2: [180, 260), Done: >= 260
    def beep_at(elapsed: int) -> bool:
        return elapsed < total and (elapsed % period) < beep_ms

    assert beep_at(0) is True and beep_at(79) is True
    assert beep_at(80) is False and beep_at(179) is False
    assert beep_at(180) is True and beep_at(259) is True
    assert beep_at(260) is False and beep_at(5000) is False


def test_offline_led_double_blink_cadence_and_user_state_restore() -> None:
    cfg = _load_config_constants()
    cycle = int(cfg["OFFLINE_LED_CYCLE_MS"])
    pulse = int(cfg["OFFLINE_LED_PULSE_MS"])
    gap = int(cfg["OFFLINE_LED_GAP_MS"])

    def led_out(user_on: bool, is_online: bool, elapsed: int) -> bool:
        if is_online:
            return user_on
        e = elapsed % cycle
        in_pulse = (e < pulse) or ((pulse + gap) <= e < (2 * pulse + gap))
        return (not user_on) if in_pulse else user_on

    # User light OFF: pulses HIGH during [0..120) and [280..400), OFF for [400..4000)
    assert led_out(False, False, 0) is True
    assert led_out(False, False, 119) is True
    assert led_out(False, False, 120) is False
    assert led_out(False, False, 279) is False
    assert led_out(False, False, 280) is True
    assert led_out(False, False, 399) is True
    assert led_out(False, False, 400) is False
    assert led_out(False, False, 3999) is False
    assert led_out(False, False, 4000) is True

    # User light ON: dips LOW during pulses, restores ON cleanly afterward
    assert led_out(True, False, 50) is False
    assert led_out(True, False, 500) is True
    # Online: always reflects user light immediately
    assert led_out(True, True, 50) is True
    assert led_out(False, True, 50) is False


def test_safety_timers_pump_120s_lockout_and_siren_30s_offline() -> None:
    cfg = _load_config_constants()
    fsm = _OfflineFsmModel(cfg)
    fsm.record_change("garden_pump", True, 1000, "soil_auto_offline")
    fsm.record_change("alarm_siren", True, 1000, "offline_voice")

    assert fsm.tick_safety_timers(30999) == {"pump_tripped": False, "siren_tripped": False}
    assert fsm.tick_safety_timers(31000) == {"pump_tripped": False, "siren_tripped": True}
    assert fsm.states["alarm_siren"] is False
    assert fsm.events[-1]["reason"] == "siren_max_runtime"

    assert fsm.tick_safety_timers(120999) == {"pump_tripped": False, "siren_tripped": False}
    assert fsm.tick_safety_timers(121000) == {"pump_tripped": True, "siren_tripped": False}
    assert fsm.states["garden_pump"] is False
    assert fsm.pump_safety_locked_until_wet is True
    assert fsm.events[-1]["reason"] == "pump_max_runtime"


def test_addendum_a2_fixed_basic_commands_zero_roles_and_custom_refusal() -> None:
    cfg = _load_config_constants()
    fsm = _OfflineFsmModel(cfg)

    # All 5 basic ON/OFF devices + main_door close + status query work offline
    for text, dev, st in (
        ("bật đèn phòng khách", "living_room_light", "ON"),
        ("[tier3] tắt đèn phòng khách", "living_room_light", "OFF"),
        ("[khach] bật đèn phòng ngủ", "bedroom_light", "ON"),
        ("[stranger] bật máy bơm tưới cây", "garden_pump", "ON"),
        ("bật còi báo động", "alarm_siren", "ON"),
        ("tắt còi báo động", "alarm_siren", "OFF"),
        ("bật nguồn mạch loa PAM8403", "speaker_amp", "ON"),
        ("đóng cửa chính", "main_door", "CLOSED"),
    ):
        res = fsm.handle_text(text, 2000)
        assert res["ok"] is True and res["http_status"] == 200, f"Expected OK for {text!r}, got {res}"
        assert res["device_id"] == dev and res["state"] == st

    st_res = fsm.handle_text("kiểm tra trạng thái thiết bị", 2500)
    assert st_res["ok"] is True and st_res["reason_code"] == "STATUS_OK"

    # Custom commands, schedules, automation rules, and unsupported devices refused (HTTP 400)
    for refused_cmd in (
        "vừng ơi mở ra",
        "hẹn giờ tắt đèn phòng khách",
        "bật đèn phòng khách sau 5 phút",
        "đặt lịch bật máy bơm lúc 6 giờ",
        "nếu nhiệt độ lớn hơn 35 thì bật máy bơm",
        "tạo lệnh tùy chỉnh đi ngủ",
        "bật quạt trần",
        "bật điều hòa",
    ):
        res = fsm.handle_text(refused_cmd, 3000)
        assert res["ok"] is False and res["refused"] is True and res["http_status"] == 400, f"Must refuse {refused_cmd!r}"
        assert res["reason_code"] == "CUSTOM_OR_ADVANCED_FORBIDDEN_OFFLINE"


def test_addendum_a3_main_door_open_absolutely_forbidden_offline() -> None:
    cfg = _load_config_constants()
    fsm = _OfflineFsmModel(cfg)

    assert fsm.can_set_main_door(True) is False
    assert fsm.can_set_main_door(False) is True

    for open_cmd in ("mở cửa chính", "mo cua chinh", "mo cua", "open main_door"):
        res = fsm.handle_text(open_cmd, 4000)
        assert res["ok"] is False and res["refused"] is True and res["http_status"] == 403
        assert res["reason_code"] == "DOOR_OPEN_FORBIDDEN_OFFLINE"
        assert res["device_id"] == "main_door" and res["state"] == "CLOSED"
        assert res["reply_vi"] == "Đang mất kết nối máy chủ, tuyệt đối không được phép mở cửa chính."
        assert fsm.states["main_door"] is False

    # Online restores ability to open door
    fsm.on_connectivity_changed(True, 5000)
    assert fsm.can_set_main_door(True) is True


def test_addendum_a1_softap_fallback_and_a4_resync_ring_buffer() -> None:
    cfg = _load_config_constants()
    fsm = _OfflineFsmModel(cfg)

    # A1: SoftAP activates only after WIFI_AP_FALLBACK_AFTER_MS (15000 ms)
    assert fsm.should_enable_softap(False, 1000) is False
    assert fsm.should_enable_softap(False, 15999) is False
    assert fsm.should_enable_softap(False, 16000) is True
    assert fsm.should_enable_softap(True, 17000) is False

    # A4: Ring buffer caps at 16 without overflow & triggers resync on reconnect
    for i in range(20):
        fsm.handle_text("bật đèn phòng khách" if i % 2 == 0 else "tắt đèn phòng khách", 2000 + i * 100)
    assert len(fsm.events) == 16
    assert fsm.dirty_mask & (1 << fsm.DEVICES.index("living_room_light"))

    tr = fsm.on_connectivity_changed(True, 10000)
    assert tr["became_online"] is True and tr["need_resync"] is True and fsm.pending_resync is True
