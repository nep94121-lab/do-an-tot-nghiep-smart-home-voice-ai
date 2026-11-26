"""Single Source of Truth (SSOT) for Offline Board Policy & Safety Contract (Addendum A2 & A3).

Derived dynamically from `DEFAULT_DEVICES` and `DEVICE_CAPABILITIES` in
`backend.engine.constants_and_time` (zero hardcoded device lists) and parity-tested
against `hardware/wiring_contract.py` and `firmware/esp8266_smarthome/offline_safety_config.h`.
"""

from __future__ import annotations

from typing import Any

from backend.engine.constants_and_time import (
    DEFAULT_DEVICES,
    DEVICE_CAPABILITIES,
    get_board_heartbeat_timeout_sec,
)

# ---------------------------------------------------------------------------
# Addendum A2 & A3 Policy Flags (Single Config)
# ---------------------------------------------------------------------------
OFFLINE_ROLE_CHECK_ENABLED: bool = False
OFFLINE_CUSTOM_COMMANDS_ALLOWED: bool = False
OFFLINE_AUTOMATION_MUTATION_ALLOWED: bool = False
OFFLINE_STATUS_QUERY_ALLOWED: bool = True

# ---------------------------------------------------------------------------
# Actuator Safety Runtime Limits & Reconnect Timing (parity with offline_safety_config.h)
# ---------------------------------------------------------------------------
PUMP_MAX_CONTINUOUS_RUN_MS: int = 120000
SIREN_MAX_OFFLINE_RUN_MS: int = 30000
SPEAKER_AMP_IDLE_TAIL_MS: int = 1500

WIFI_BACKOFF_INITIAL_MS: int = 1000
WIFI_BACKOFF_MAX_MS: int = 30000
WIFI_BACKOFF_MULTIPLIER: int = 2

SERVER_BACKOFF_INITIAL_MS: int = 1000
SERVER_BACKOFF_MAX_MS: int = 30000
SERVER_BACKOFF_MULTIPLIER: int = 2

HEARTBEAT_INTERVAL_MS: int = 3000
OFFLINE_LED_CYCLE_MS: int = 4000

# ---------------------------------------------------------------------------
# Registry-Derived Allowed / Forbidden Actions & Safe Defaults
# ---------------------------------------------------------------------------
OFFLINE_FORBIDDEN_DEVICE_ACTIONS: dict[str, tuple[str, ...]] = {
    dev_id: ("open",)
    for dev_id, dev_meta in DEFAULT_DEVICES.items()
    if str(dev_meta.get("type") or "").strip().lower() == "door"
}

OFFLINE_ALLOWED_DEVICE_ACTIONS: dict[str, tuple[str, ...]] = {
    dev_id: tuple(
        action
        for action in tuple(
            DEVICE_CAPABILITIES.get(dev_id, {}).get("actions", ("turn_on", "turn_off"))
        )
        if action not in OFFLINE_FORBIDDEN_DEVICE_ACTIONS.get(dev_id, ())
    )
    for dev_id in DEFAULT_DEVICES
}

OFFLINE_SAFETY_DEFAULTS: dict[str, str] = {
    dev_id: str(
        dev_meta.get("state")
        or ("CLOSED" if str(dev_meta.get("type") or "").strip().lower() == "door" else "OFF")
    )
    for dev_id, dev_meta in DEFAULT_DEVICES.items()
}

_DEVICE_TYPE_MAX_RUN_MS: dict[str, int] = {
    "pump": PUMP_MAX_CONTINUOUS_RUN_MS,
    "siren": SIREN_MAX_OFFLINE_RUN_MS,
    "speaker": SPEAKER_AMP_IDLE_TAIL_MS,
}

OFFLINE_ACTUATOR_MAX_RUN_MS: dict[str, int] = {
    dev_id: _DEVICE_TYPE_MAX_RUN_MS[str(dev_meta.get("type") or "").strip().lower()]
    for dev_id, dev_meta in DEFAULT_DEVICES.items()
    if str(dev_meta.get("type") or "").strip().lower() in _DEVICE_TYPE_MAX_RUN_MS
}


def is_offline_action_forbidden(device_id: str, action: str) -> bool:
    """Return True if `(device_id, action)` is explicitly forbidden offline (e.g. door open)."""
    act_norm = str(action or "").strip().lower()
    if act_norm in ("on", "turn_on") and str(DEFAULT_DEVICES.get(device_id, {}).get("type") or "") == "door":
        act_norm = "open"
    return act_norm in OFFLINE_FORBIDDEN_DEVICE_ACTIONS.get(device_id, ())


def is_offline_action_allowed(device_id: str, action: str) -> bool:
    """Return True if `(device_id, action)` belongs to the fixed offline basic command set."""
    if device_id not in OFFLINE_ALLOWED_DEVICE_ACTIONS:
        return False
    act_norm = str(action or "").strip().lower()
    dev_type = str(DEFAULT_DEVICES.get(device_id, {}).get("type") or "").strip().lower()
    if dev_type == "door":
        if act_norm in ("on", "turn_on"):
            act_norm = "open"
        elif act_norm in ("off", "turn_off"):
            act_norm = "close"
    else:
        if act_norm in ("on", "open"):
            act_norm = "turn_on"
        elif act_norm in ("off", "close"):
            act_norm = "turn_off"
    if act_norm in OFFLINE_FORBIDDEN_DEVICE_ACTIONS.get(device_id, ()):
        return False
    return act_norm in OFFLINE_ALLOWED_DEVICE_ACTIONS[device_id]


def format_device_offline_reply_vi(
    device_record: dict[str, Any] | None,
    board_health: dict[str, Any] | None = None,
) -> str:
    """Derive concise Vietnamese offline refusal purely from `device_record` and `board_health`."""
    rec = device_record if isinstance(device_record, dict) else {}
    dev_name = str(rec.get("name") or rec.get("id") or "Thiết bị").strip()
    bh = board_health if isinstance(board_health, dict) else {}
    last_seen_vi = str(bh.get("last_seen_vi") or "").strip()
    if last_seen_vi:
        return f"{dev_name} hiện đang mất kết nối (lần cuối: {last_seen_vi}), chưa thể điều khiển lúc này."
    return f"{dev_name} hiện đang mất kết nối, chưa thể điều khiển lúc này."


def format_devices_offline_reply_vi(
    device_records: list[dict[str, Any]],
    board_health: dict[str, Any] | None = None,
) -> str:
    """Derive concise Vietnamese offline refusal for one or multiple devices purely from registry records."""
    valid = [r for r in (device_records or []) if isinstance(r, dict)]
    if not valid:
        return format_device_offline_reply_vi({"name": "Mạch điều khiển"}, board_health)
    if len(valid) == 1:
        return format_device_offline_reply_vi(valid[0], board_health)
    names: list[str] = []
    for idx, rec in enumerate(valid):
        nm = str(rec.get("name") or rec.get("id") or "Thiết bị").strip()
        names.append(nm if idx == 0 else nm.lower())
    if len(names) == 2:
        joined = f"{names[0]} và {names[1]}"
    else:
        joined = ", ".join(names[:-1]) + f" và {names[-1]}"
    return format_device_offline_reply_vi({"name": joined}, board_health)


def get_offline_contract_summary() -> dict[str, Any]:
    """Return a JSON-serializable summary of the frozen offline safety & policy contract."""
    return {
        "board_heartbeat_timeout_sec": get_board_heartbeat_timeout_sec(),
        "offline_role_check_enabled": OFFLINE_ROLE_CHECK_ENABLED,
        "offline_custom_commands_allowed": OFFLINE_CUSTOM_COMMANDS_ALLOWED,
        "offline_automation_mutation_allowed": OFFLINE_AUTOMATION_MUTATION_ALLOWED,
        "offline_status_query_allowed": OFFLINE_STATUS_QUERY_ALLOWED,
        "allowed_device_actions": {k: list(v) for k, v in OFFLINE_ALLOWED_DEVICE_ACTIONS.items()},
        "forbidden_device_actions": {k: list(v) for k, v in OFFLINE_FORBIDDEN_DEVICE_ACTIONS.items()},
        "safety_defaults": dict(OFFLINE_SAFETY_DEFAULTS),
        "actuator_max_run_ms": dict(OFFLINE_ACTUATOR_MAX_RUN_MS),
        "pump_max_continuous_run_ms": PUMP_MAX_CONTINUOUS_RUN_MS,
        "siren_max_offline_run_ms": SIREN_MAX_OFFLINE_RUN_MS,
        "speaker_amp_idle_tail_ms": SPEAKER_AMP_IDLE_TAIL_MS,
        "heartbeat_interval_ms": HEARTBEAT_INTERVAL_MS,
        "offline_led_cycle_ms": OFFLINE_LED_CYCLE_MS,
        "wifi_backoff_initial_ms": WIFI_BACKOFF_INITIAL_MS,
        "wifi_backoff_max_ms": WIFI_BACKOFF_MAX_MS,
        "wifi_backoff_multiplier": WIFI_BACKOFF_MULTIPLIER,
        "server_backoff_initial_ms": SERVER_BACKOFF_INITIAL_MS,
        "server_backoff_max_ms": SERVER_BACKOFF_MAX_MS,
        "server_backoff_multiplier": SERVER_BACKOFF_MULTIPLIER,
    }


__all__ = [
    "OFFLINE_ROLE_CHECK_ENABLED",
    "OFFLINE_CUSTOM_COMMANDS_ALLOWED",
    "OFFLINE_AUTOMATION_MUTATION_ALLOWED",
    "OFFLINE_STATUS_QUERY_ALLOWED",
    "OFFLINE_ALLOWED_DEVICE_ACTIONS",
    "OFFLINE_FORBIDDEN_DEVICE_ACTIONS",
    "OFFLINE_SAFETY_DEFAULTS",
    "OFFLINE_ACTUATOR_MAX_RUN_MS",
    "PUMP_MAX_CONTINUOUS_RUN_MS",
    "SIREN_MAX_OFFLINE_RUN_MS",
    "SPEAKER_AMP_IDLE_TAIL_MS",
    "WIFI_BACKOFF_INITIAL_MS",
    "WIFI_BACKOFF_MAX_MS",
    "WIFI_BACKOFF_MULTIPLIER",
    "SERVER_BACKOFF_INITIAL_MS",
    "SERVER_BACKOFF_MAX_MS",
    "SERVER_BACKOFF_MULTIPLIER",
    "HEARTBEAT_INTERVAL_MS",
    "OFFLINE_LED_CYCLE_MS",
    "is_offline_action_allowed",
    "is_offline_action_forbidden",
    "format_device_offline_reply_vi",
    "format_devices_offline_reply_vi",
    "get_offline_contract_summary",
]
