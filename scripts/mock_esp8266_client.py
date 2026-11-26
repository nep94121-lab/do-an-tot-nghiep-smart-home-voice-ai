#!/usr/bin/env python3
"""Mock ESP8266 Hardware Client & Local LAN Offline Voice Node (Session S2).

Implements the frozen G1 + Addendum A1-A4 cross-layer contract dynamically from
`backend.engine.constants_and_time.DEFAULT_DEVICES` and `backend.engine.offline_contract`
(zero hardcoded device lists or static policy copies):
- Sends periodic `POST /api/hardware/heartbeat` to `--server-url` using `X-Hardware-Key`.
- Hosts a local LAN HTTP server (`ESP8266WebServer` simulation) on `--listen-port` (default 8093):
  * `GET /`               -> Clean Vietnamese local LAN offline status & voice console UI.
  * `GET /offline/status` -> JSON physical device states, sensors, offline changes & history.
  * `POST /offline/cmd`   -> Addendum A1-A3 zero-auth/zero-role local offline command execution
                             (allows fixed basic commands, HTTP 403 hard firmware block on
                             forbidden door-open actions, HTTP 400 refusal on custom/schedule commands).
  * `POST /sim/disconnect`-> Stops heartbeats & enforces A3 fail-safe door lock.
  * `POST /sim/reconnect` -> Resumes heartbeats & posts `POST /api/hardware/resync` (Addendum A4).
"""

from __future__ import annotations

import argparse
import html
import json
import os
import pathlib
import re
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# Ensure repo root is on sys.path when invoked as `python scripts/mock_esp8266_client.py`
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.engine.constants_and_time import (  # noqa: E402
    ACTION_TO_STATE,
    ACTION_VI_LABEL,
    DEFAULT_DEVICES,
    DEVICE_CAPABILITIES,
    DEVICE_ID_ALIASES,
    format_vn_timestamp_vi,
)
from backend.engine.offline_contract import (  # noqa: E402
    OFFLINE_ALLOWED_DEVICE_ACTIONS,
    OFFLINE_AUTOMATION_MUTATION_ALLOWED,
    OFFLINE_CUSTOM_COMMANDS_ALLOWED,
    OFFLINE_FORBIDDEN_DEVICE_ACTIONS,
    OFFLINE_ROLE_CHECK_ENABLED,
    OFFLINE_SAFETY_DEFAULTS,
    OFFLINE_STATUS_QUERY_ALLOWED,
    is_offline_action_allowed,
    is_offline_action_forbidden,
)
from backend.voice.enrollment_quality import strip_vietnamese_diacritics  # noqa: E402

DOOR_OPEN_REFUSAL_VI = "Đang mất kết nối máy chủ, tuyệt đối không được phép mở cửa chính."
CUSTOM_CMD_REFUSAL_VI = (
    "Đang ngoại tuyến, chỉ hỗ trợ các lệnh bật tắt cơ bản cố định, "
    "không hỗ trợ lệnh tùy chỉnh hay đặt lịch."
)

_SCHEDULE_OR_CUSTOM_PATTERNS = (
    r"\bhẹn\s*giờ\b",
    r"\bđặt\s*lịch\b",
    r"\blịch\s*trình\b",
    r"\bsau\s+\d+\s*(?:giây|phút|giờ)\b",
    r"\b\d+\s*(?:giây|phút|giờ)\s*nữa\b",
    r"\blúc\s+\d+\s*(?:giờ|h)\b",
    r"\bnếu\b.+\bthì\b",
    r"\btạo\s*luật\b",
    r"\btạo\s*lệnh\b",
    r"\bđổi\s*lệnh\b",
    r"\bđổi\s*từ\b",
    r"\blệnh\s*tùy\s*chỉnh\b",
    r"\btùy\s*chỉnh\b",
    r"\bchế\s*độ\s*đi\s*ngủ\b",
    r"\bchế\s*độ\s*về\s*nhà\b",
    r"\bchế\s*độ\s*ra\s*ngoài\b",
    r"\bngữ\s*cảnh\b",
    r"\bhen\s*gio\b",
    r"\bdat\s*lich\b",
    r"\blenh\s*tuy\s*chinh\b",
)


def _normalize_action_for_device(device_id: str, action: str) -> str:
    act = str(action or "").strip().lower()
    dev_type = str(DEFAULT_DEVICES.get(device_id, {}).get("type") or "").strip().lower()
    if dev_type == "door":
        if act in ("on", "turn_on", "open", "mo", "mở"):
            return "open"
        if act in ("off", "turn_off", "close", "dong", "đóng", "khoa", "khóa"):
            return "close"
    else:
        if act in ("on", "turn_on", "open", "bat", "bật", "mo", "mở"):
            return "turn_on"
        if act in ("off", "turn_off", "close", "tat", "tắt", "dong", "đóng"):
            return "turn_off"
    return act


def _build_device_match_tokens() -> dict[str, list[str]]:
    """Build Vietnamese matching tokens dynamically from DEFAULT_DEVICES & DEVICE_ID_ALIASES."""
    tokens_by_dev: dict[str, list[str]] = {}
    for dev_id, meta in DEFAULT_DEVICES.items():
        name_low = str(meta.get("name") or "").strip().lower()
        name_ascii = strip_vietnamese_diacritics(name_low)
        cands = [dev_id.lower(), name_low, name_ascii]
        # Shorter natural forms derived from device registry names
        if name_low.startswith("máy "):
            cands.append(name_low[4:])
            cands.append(strip_vietnamese_diacritics(name_low[4:]))
        if name_low.startswith("nguồn "):
            cands.append(name_low[6:])
            cands.append(strip_vietnamese_diacritics(name_low[6:]))
        # Include aliases pointing to this device_id
        for alias, target in DEVICE_ID_ALIASES.items():
            if target == dev_id:
                cands.append(alias.lower().replace("_", " "))
        # Deduplicate longest-first to avoid partial mismatches
        uniq = sorted({c.strip() for c in cands if c and c.strip()}, key=len, reverse=True)
        tokens_by_dev[dev_id] = uniq
    return tokens_by_dev


_DEVICE_MATCH_TOKENS = _build_device_match_tokens()


def parse_offline_vietnamese_command(text: str) -> dict[str, Any]:
    """Parse local offline Vietnamese command without calling central server or AI."""
    raw = str(text or "").strip()
    low = re.sub(r"\s+", " ", raw.lower())
    ascii_low = strip_vietnamese_diacritics(low)

    if not low:
        return {"kind": "unsupported", "reason": "empty"}

    # Reject custom commands, schedules, timers, rules, scenes (Addendum A2)
    for pat in _SCHEDULE_OR_CUSTOM_PATTERNS:
        if re.search(pat, low, flags=re.I) or re.search(pat, ascii_low, flags=re.I):
            return {"kind": "custom_or_schedule", "text": raw}

    # Allow read-only status queries if enabled by contract
    if OFFLINE_STATUS_QUERY_ALLOWED and any(
        k in low or k in ascii_low
        for k in ("trạng thái", "trang thai", "nhiệt độ", "nhiet do", "độ ẩm", "do am", "cảm biến", "cam bien")
    ):
        return {"kind": "status_query", "text": raw}

    # Match device dynamically from DEFAULT_DEVICES
    matched_dev: str | None = None
    best_len = 0
    for dev_id, tokens in _DEVICE_MATCH_TOKENS.items():
        for tok in tokens:
            if tok in low or tok in ascii_low:
                if len(tok) > best_len:
                    best_len = len(tok)
                    matched_dev = dev_id

    if matched_dev is None:
        return {"kind": "custom_or_schedule", "text": raw}

    # Determine action verb dynamically (check accented Vietnamese first; avoid 'báo động' -> 'dong')
    has_diacritics = bool(
        re.search(
            r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]",
            low,
        )
    )
    off_verbs_vi = ("tắt", "đóng", "khóa", "ngắt", "dừng", "turn_off", "turn off", "close")
    on_verbs_vi = ("bật", "mở", "khởi động", "chạy", "turn_on", "turn on", "open")

    raw_action: str | None = None
    for v in off_verbs_vi:
        if re.search(rf"(?:^|\s){re.escape(v)}(?:\s|$)", low):
            raw_action = "close" if v in ("đóng", "khóa", "close") else "turn_off"
            break
    if raw_action is None:
        for v in on_verbs_vi:
            if re.search(rf"(?:^|\s){re.escape(v)}(?:\s|$)", low):
                raw_action = "open" if v in ("mở", "open") else "turn_on"
                break
    if raw_action is None and not has_diacritics:
        cleaned_ascii = re.sub(r"\bbao\s+dong\b", " ", ascii_low)
        for v in ("tat", "dong", "khoa", "ngat", "dung"):
            if re.search(rf"(?:^|\s){re.escape(v)}(?:\s|$)", cleaned_ascii):
                raw_action = "close" if v in ("dong", "khoa") else "turn_off"
                break
    if raw_action is None and not has_diacritics:
        for v in ("bat", "mo", "khoi dong", "chay"):
            if re.search(rf"(?:^|\s){re.escape(v)}(?:\s|$)", ascii_low):
                raw_action = "open" if v == "mo" else "turn_on"
                break

    if raw_action is None:
        return {"kind": "custom_or_schedule", "text": raw}

    norm_action = _normalize_action_for_device(matched_dev, raw_action)
    return {
        "kind": "device_action",
        "device_id": matched_dev,
        "action": norm_action,
        "text": raw,
    }


class MockESP8266Node:
    """In-process & HTTP-hosted Mock ESP8266 hardware node implementing G1 + A1-A4."""

    def __init__(
        self,
        *,
        server_url: str = "http://127.0.0.1:8092",
        listen_host: str = "127.0.0.1",
        listen_port: int = 8093,
        heartbeat_interval: float = 1.5,
        node_id: str = "esp8266_node_01",
        hardware_key: str = "",
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.listen_host = listen_host
        self.listen_port = int(listen_port)
        self.heartbeat_interval = max(0.3, float(heartbeat_interval))
        self.node_id = node_id
        self.hardware_key = hardware_key or str(os.environ.get("SMARTHOME_HARDWARE_API_KEY") or "").strip()

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._boot_ts = time.time()
        self._connected_to_server = True
        self._offline_since_ts: float | None = None
        self._heartbeat_sent_count = 0
        self._last_heartbeat_ok_ts: float = 0.0
        self._resync_count = 0

        self.device_states: dict[str, str] = dict(OFFLINE_SAFETY_DEFAULTS)
        self.sensors: dict[str, Any] = {
            "temp_c": 28.4,
            "humidity_pct": 63.0,
            "soil_moisture_pct": 58.0,
            "sound_detected": False,
        }
        self.offline_changed_devices: list[str] = []
        self.offline_events: list[dict[str, Any]] = []
        self.command_history: list[dict[str, Any]] = []

        self._httpd: ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._hb_thread: threading.Thread | None = None

    def _hw_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.hardware_key:
            headers["X-Hardware-Key"] = self.hardware_key
        return headers

    def _post_server(self, path: str, payload: dict[str, Any], timeout: float = 3.5) -> tuple[int, dict[str, Any]]:
        url = f"{self.server_url}{path}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._hw_headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                return resp.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            try:
                body = json.loads(raw) if raw else {"ok": False, "error": str(exc)}
            except Exception:
                body = {"ok": False, "error": raw or str(exc)}
            return exc.code, body
        except Exception as exc:
            return 0, {"ok": False, "error": str(exc)}

    def _get_server_state(self, timeout: float = 2.5) -> dict[str, Any] | None:
        url = f"{self.server_url}/api/state"
        req = urllib.request.Request(url, headers=self._hw_headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                return json.loads(raw) if raw else None
        except Exception:
            return None

    def send_heartbeat_once(self) -> tuple[int, dict[str, Any]]:
        uptime_ms = int((time.time() - self._boot_ts) * 1000)
        code, body = self._post_server(
            "/api/hardware/heartbeat",
            {
                "node_id": self.node_id,
                "wifi_rssi_dbm": -52,
                "uptime_ms": uptime_ms,
                "firmware_mode": "ONLINE",
            },
        )
        if code == 200 and body.get("ok"):
            with self._lock:
                self._heartbeat_sent_count += 1
                self._last_heartbeat_ok_ts = time.time()
        return code, body

    def _sync_states_from_server_when_online(self) -> None:
        snap = self._get_server_state()
        if not isinstance(snap, dict):
            return
        devs = snap.get("devices")
        if isinstance(devs, list):
            dev_map = {str(d.get("id") or ""): d for d in devs if isinstance(d, dict) and d.get("id")}
        elif isinstance(devs, dict):
            dev_map = devs
        else:
            return
        with self._lock:
            if not self._connected_to_server:
                return
            for dev_id in DEFAULT_DEVICES:
                rec = dev_map.get(dev_id)
                if isinstance(rec, dict) and rec.get("state"):
                    self.device_states[dev_id] = str(rec["state"])

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                should_send = self._connected_to_server
            if should_send:
                self.send_heartbeat_once()
                self._sync_states_from_server_when_online()
            self._stop_event.wait(self.heartbeat_interval)

    def simulate_disconnect(self, *, send_lwt: bool = False) -> dict[str, Any]:
        with self._lock:
            self._connected_to_server = False
            self._offline_since_ts = time.time()
            self.offline_changed_devices = []
            self.offline_events = []
            # Addendum A3 fail-safe: force any forbidden-open door device to safe CLOSED state
            for dev_id in OFFLINE_FORBIDDEN_DEVICE_ACTIONS:
                safe_state = OFFLINE_SAFETY_DEFAULTS[dev_id]
                if self.device_states.get(dev_id) != safe_state:
                    self.device_states[dev_id] = safe_state
                    self.offline_changed_devices.append(dev_id)
                    self.offline_events.append(
                        {
                            "device_id": dev_id,
                            "state": safe_state,
                            "reason": "disconnect_failsafe_lock",
                            "offset_ms": 0,
                        }
                    )
        lwt_res: dict[str, Any] | None = None
        if send_lwt:
            _, lwt_res = self._post_server("/api/hardware/lwt", {"node_id": self.node_id, "online": False})
        return {
            "ok": True,
            "connected_to_server": False,
            "offline_mode": True,
            "lwt_sent": bool(send_lwt),
            "lwt_response": lwt_res,
            "devices": dict(self.device_states),
        }

    def simulate_reconnect(self) -> dict[str, Any]:
        with self._lock:
            now_ts = time.time()
            offline_duration_ms = (
                int((now_ts - self._offline_since_ts) * 1000)
                if self._offline_since_ts is not None
                else 0
            )
            payload = {
                "node_id": self.node_id,
                "offline_duration_ms": max(0, offline_duration_ms),
                "wifi_rssi_dbm": -53,
                "device_states": dict(self.device_states),
                "offline_changed_devices": list(self.offline_changed_devices),
                "offline_events": list(self.offline_events),
                "sensors": dict(self.sensors),
            }
        code, resync_body = self._post_server("/api/hardware/resync", payload, timeout=5.0)
        hb_code, hb_body = self.send_heartbeat_once()
        with self._lock:
            self._connected_to_server = True
            self._offline_since_ts = None
            if code == 200 and resync_body.get("ok"):
                self._resync_count += 1
                self.offline_changed_devices = []
                self.offline_events = []
        return {
            "ok": code == 200 and bool(resync_body.get("ok")),
            "connected_to_server": True,
            "offline_mode": False,
            "resync_status_code": code,
            "resync_response": resync_body,
            "heartbeat_status_code": hb_code,
            "heartbeat_response": hb_body,
            "devices": dict(self.device_states),
        }

    def execute_offline_cmd(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Execute Addendum A1-A3 local LAN offline command (zero auth, zero role checks)."""
        assert OFFLINE_ROLE_CHECK_ENABLED is False
        assert OFFLINE_CUSTOM_COMMANDS_ALLOWED is False
        assert OFFLINE_AUTOMATION_MUTATION_ALLOWED is False

        text = str(body.get("text") or "").strip()
        explicit_dev = str(body.get("device_id") or "").strip()
        explicit_act = str(body.get("action") or "").strip()

        if explicit_dev and explicit_act:
            dev_id = DEVICE_ID_ALIASES.get(explicit_dev, explicit_dev)
            if dev_id not in DEFAULT_DEVICES:
                parsed = {"kind": "custom_or_schedule", "text": text or f"{explicit_act} {explicit_dev}"}
            else:
                parsed = {
                    "kind": "device_action",
                    "device_id": dev_id,
                    "action": _normalize_action_for_device(dev_id, explicit_act),
                    "text": text or f"{ACTION_VI_LABEL.get(_normalize_action_for_device(dev_id, explicit_act), explicit_act)} {DEFAULT_DEVICES[dev_id]['name']}",
                }
        else:
            parsed = parse_offline_vietnamese_command(text)

        now_vi = format_vn_timestamp_vi(time.time())
        display_input = str(parsed.get("text") or text or "(trống)")

        with self._lock:
            offset_ms = (
                int((time.time() - self._offline_since_ts) * 1000)
                if self._offline_since_ts is not None
                else 0
            )
            if parsed["kind"] == "status_query":
                on_names = [
                    DEFAULT_DEVICES[d]["name"]
                    for d, st in self.device_states.items()
                    if st in ("ON", "OPEN")
                ]
                active_txt = ", ".join(on_names) if on_names else "tất cả thiết bị đang tắt/đóng"
                reply_vi = (
                    f"Chế độ ngoại tuyến: nhiệt độ {self.sensors['temp_c']}°C, "
                    f"độ ẩm {self.sensors['humidity_pct']}%, độ ẩm đất {self.sensors['soil_moisture_pct']}%; "
                    f"trạng thái: {active_txt}."
                )
                resp = {
                    "ok": True,
                    "offline_mode": not self._connected_to_server,
                    "refused": False,
                    "reason_code": "STATUS_QUERY_OK",
                    "reply_vi": reply_vi,
                    "devices": dict(self.device_states),
                    "sensors": dict(self.sensors),
                }
                self.command_history.append(
                    {
                        "time_vi": now_vi,
                        "input": display_input,
                        "status_code": 200,
                        "ok": True,
                        "reason_code": "STATUS_QUERY_OK",
                        "reply_vi": reply_vi,
                    }
                )
                return 200, resp

            if parsed["kind"] != "device_action":
                resp = {
                    "ok": False,
                    "offline_mode": not self._connected_to_server,
                    "refused": True,
                    "reason_code": "CUSTOM_OR_ADVANCED_FORBIDDEN_OFFLINE",
                    "reply_vi": CUSTOM_CMD_REFUSAL_VI,
                    "devices": dict(self.device_states),
                }
                self.command_history.append(
                    {
                        "time_vi": now_vi,
                        "input": display_input,
                        "status_code": 400,
                        "ok": False,
                        "reason_code": "CUSTOM_OR_ADVANCED_FORBIDDEN_OFFLINE",
                        "reply_vi": CUSTOM_CMD_REFUSAL_VI,
                    }
                )
                return 400, resp

            dev_id = parsed["device_id"]
            action = parsed["action"]

            # Addendum A3 hard firmware actuator boundary check
            if is_offline_action_forbidden(dev_id, action):
                safe_st = OFFLINE_SAFETY_DEFAULTS[dev_id]
                self.device_states[dev_id] = safe_st
                self.offline_events.append(
                    {
                        "device_id": dev_id,
                        "state": safe_st,
                        "reason": "door_open_refused_offline",
                        "offset_ms": max(0, offset_ms),
                    }
                )
                resp = {
                    "ok": False,
                    "offline_mode": not self._connected_to_server,
                    "refused": True,
                    "reason_code": "DOOR_OPEN_FORBIDDEN_OFFLINE",
                    "device_id": dev_id,
                    "state": safe_st,
                    "door_angle_deg": 0,
                    "reply_vi": DOOR_OPEN_REFUSAL_VI,
                    "devices": dict(self.device_states),
                }
                self.command_history.append(
                    {
                        "time_vi": now_vi,
                        "input": display_input,
                        "status_code": 403,
                        "ok": False,
                        "reason_code": "DOOR_OPEN_FORBIDDEN_OFFLINE",
                        "device_id": dev_id,
                        "reply_vi": DOOR_OPEN_REFUSAL_VI,
                    }
                )
                return 403, resp

            if not is_offline_action_allowed(dev_id, action):
                resp = {
                    "ok": False,
                    "offline_mode": not self._connected_to_server,
                    "refused": True,
                    "reason_code": "CUSTOM_OR_ADVANCED_FORBIDDEN_OFFLINE",
                    "reply_vi": CUSTOM_CMD_REFUSAL_VI,
                    "devices": dict(self.device_states),
                }
                self.command_history.append(
                    {
                        "time_vi": now_vi,
                        "input": display_input,
                        "status_code": 400,
                        "ok": False,
                        "reason_code": "CUSTOM_OR_ADVANCED_FORBIDDEN_OFFLINE",
                        "reply_vi": CUSTOM_CMD_REFUSAL_VI,
                    }
                )
                return 400, resp

            new_state = ACTION_TO_STATE[action]
            self.device_states[dev_id] = new_state
            if dev_id not in self.offline_changed_devices:
                self.offline_changed_devices.append(dev_id)
            self.offline_events.append(
                {
                    "device_id": dev_id,
                    "state": new_state,
                    "reason": "offline_voice",
                    "offset_ms": max(0, offset_ms),
                }
            )
            verb_vi = ACTION_VI_LABEL.get(action, action).lower()
            dev_name = str(DEFAULT_DEVICES[dev_id]["name"]).lower()
            reply_vi = f"Đã {verb_vi} {dev_name} ở chế độ ngoại tuyến."
            resp = {
                "ok": True,
                "offline_mode": not self._connected_to_server,
                "refused": False,
                "reason_code": "OK",
                "device_id": dev_id,
                "state": new_state,
                "reply_vi": reply_vi,
                "devices": dict(self.device_states),
                "offline_changed_devices": list(self.offline_changed_devices),
            }
            self.command_history.append(
                {
                    "time_vi": now_vi,
                    "input": display_input,
                    "status_code": 200,
                    "ok": True,
                    "reason_code": "OK",
                    "device_id": dev_id,
                    "state": new_state,
                    "reply_vi": reply_vi,
                }
            )
            return 200, resp

    def get_status_payload(self) -> dict[str, Any]:
        with self._lock:
            door_id = next(
                (d for d, m in DEFAULT_DEVICES.items() if str(m.get("type") or "").lower() == "door"),
                None,
            )
            door_angle = 0 if (door_id and self.device_states.get(door_id) == "CLOSED") else 90
            device_meta = {
                dev_id: {
                    "id": dev_id,
                    "name": meta["name"],
                    "gpio": meta["gpio"],
                    "type": meta["type"],
                    "state": self.device_states.get(dev_id, OFFLINE_SAFETY_DEFAULTS[dev_id]),
                    "allowed_offline_actions": list(OFFLINE_ALLOWED_DEVICE_ACTIONS.get(dev_id, ())),
                    "forbidden_offline_actions": list(OFFLINE_FORBIDDEN_DEVICE_ACTIONS.get(dev_id, ())),
                }
                for dev_id, meta in DEFAULT_DEVICES.items()
            }
            return {
                "ok": True,
                "node_id": self.node_id,
                "server_url": self.server_url,
                "connected_to_server": self._connected_to_server,
                "offline_mode": not self._connected_to_server,
                "role_check_enabled": OFFLINE_ROLE_CHECK_ENABLED,
                "custom_commands_allowed": OFFLINE_CUSTOM_COMMANDS_ALLOWED,
                "door_angle_deg": door_angle,
                "heartbeat_sent_count": self._heartbeat_sent_count,
                "resync_count": self._resync_count,
                "devices": dict(self.device_states),
                "device_meta": device_meta,
                "sensors": dict(self.sensors),
                "offline_changed_devices": list(self.offline_changed_devices),
                "offline_events": list(self.offline_events),
                "command_history": list(self.command_history[-12:]),
            }

    def render_html_console(self) -> str:
        st = self.get_status_payload()
        is_offline = bool(st["offline_mode"])
        banner_cls = "banner offline" if is_offline else "banner online"
        banner_txt = (
            "Mất kết nối máy chủ trung tâm — Chế độ ngoại tuyến cục bộ (LAN trực tiếp · Không phân biệt vai trò · Khóa cứng mở cửa chính)"
            if is_offline
            else "Đang kết nối máy chủ trung tâm — Chế độ trực tuyến"
        )
        cards_html: list[str] = []
        for dev_id, meta in st["device_meta"].items():
            cur = str(meta["state"])
            is_active = cur in ("ON", "OPEN")
            state_vi = (
                ("Đang mở (90°)" if is_active else "Đang đóng · Khóa cứng (0°)")
                if meta["type"] == "door"
                else ("Đang bật (ON)" if is_active else "Đang tắt (OFF)")
            )
            changed_tag = (
                '<span class="chip changed">Thay đổi ngoại tuyến</span>'
                if dev_id in st["offline_changed_devices"]
                else ""
            )
            door_guard = (
                '<span class="chip guard">Chặn mở cửa khi ngoại tuyến (A3)</span>'
                if dev_id in OFFLINE_FORBIDDEN_DEVICE_ACTIONS
                else ""
            )
            cards_html.append(
                f"""
                <div class="card {'active' if is_active else ''}" data-device-id="{html.escape(dev_id)}" data-state="{html.escape(cur)}">
                  <div class="card-head">
                    <strong>{html.escape(str(meta['name']))}</strong>
                    <span class="state-pill {'on' if is_active else 'off'}">{html.escape(state_vi)}</span>
                  </div>
                  <div class="meta">{html.escape(str(meta['gpio']))}</div>
                  <div class="chips">{changed_tag}{door_guard}</div>
                </div>
                """
            )

        hist_rows: list[str] = []
        for item in reversed(st["command_history"]):
            cls = "log-item ok" if item["ok"] else ("log-item forbidden" if item["status_code"] == 403 else "log-item refused")
            badge = (
                "HTTP 200 · Thực thi cục bộ"
                if item["ok"]
                else ("HTTP 403 · Firmware chặn mở cửa (A3)" if item["status_code"] == 403 else "HTTP 400 · Từ chối lệnh tùy chỉnh (A2)")
            )
            hist_rows.append(
                f"""
                <div class="{cls}" data-reason="{html.escape(str(item['reason_code']))}">
                  <div class="log-top">
                    <span class="cmd-in">Khẩu lệnh: “{html.escape(str(item['input']))}”</span>
                    <span class="http-badge">{html.escape(badge)}</span>
                  </div>
                  <div class="cmd-out">Phản hồi ESP8266: {html.escape(str(item['reply_vi']))}</div>
                  <div class="cmd-time">{html.escape(str(item['time_vi']))}</div>
                </div>
                """
            )
        history_html = "".join(hist_rows) if hist_rows else '<p class="empty">Chưa có khẩu lệnh ngoại tuyến nào.</p>'

        return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ESP8266 Ngoại Tuyến · LAN Voice Console</title>
  <style>
    :root {{
      --bg: #f4f7f8; --surface: #ffffff; --ink: #0f2226; --muted: #51666c;
      --line: #d6e1e4; --accent: #0b6e66; --ok-bg: #e7f6f2; --ok-ink: #0a5c55;
      --red-bg: #fdecea; --red-ink: #b42318; --amber-bg: #fef5e7; --amber-ink: #8a5200;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Be Vietnam Pro", "Segoe UI", system-ui, sans-serif; background: var(--bg); color: var(--ink); }}
    .wrap {{ max-width: 1120px; margin: 0 auto; padding: 20px; }}
    .head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }}
    .head h1 {{ margin: 0; font-size: 22px; }}
    .sub {{ font-size: 13px; color: var(--muted); }}
    .banner {{ padding: 12px 16px; border-radius: 12px; font-weight: 600; font-size: 14px; margin-bottom: 16px; border: 1px solid; }}
    .banner.offline {{ background: var(--red-bg); color: var(--red-ink); border-color: rgba(180,35,24,0.35); }}
    .banner.online {{ background: var(--ok-bg); color: var(--ok-ink); border-color: rgba(11,110,102,0.35); }}
    .layout {{ display: grid; grid-template-columns: 1.15fr 1fr; gap: 16px; }}
    @media (max-width: 820px) {{ .layout {{ grid-template-columns: 1fr; }} }}
    .panel {{ background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 16px; }}
    .panel h2 {{ margin: 0 0 12px; font-size: 16px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }}
    @media (max-width: 560px) {{ .grid {{ grid-template-columns: 1fr; }} }}
    .card {{ border: 1px solid var(--line); border-radius: 12px; padding: 12px; background: #fbfdfd; }}
    .card.active {{ border-color: var(--accent); background: var(--ok-bg); }}
    .card-head {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
    .meta {{ font-size: 11px; color: var(--muted); margin-top: 4px; }}
    .state-pill {{ font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }}
    .state-pill.on {{ background: var(--accent); color: #fff; }}
    .state-pill.off {{ background: #e8eff1; color: #364b50; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
    .chip {{ font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 999px; }}
    .chip.changed {{ background: #e0f2fe; color: #075985; }}
    .chip.guard {{ background: var(--red-bg); color: var(--red-ink); }}
    .cmd-form {{ display: flex; gap: 8px; margin-bottom: 12px; }}
    .cmd-form input {{ flex: 1; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; font-size: 14px; }}
    .cmd-form button {{ padding: 10px 16px; border: none; border-radius: 10px; background: var(--accent); color: #fff; font-weight: 600; cursor: pointer; }}
    .reply-box {{ padding: 12px; border-radius: 10px; border: 1px solid var(--line); background: #f8fbfb; margin-bottom: 12px; font-size: 14px; }}
    .log-list {{ display: grid; gap: 10px; }}
    .log-item {{ padding: 10px 12px; border-radius: 10px; border: 1px solid; }}
    .log-item.ok {{ background: var(--ok-bg); border-color: rgba(11,110,102,0.3); }}
    .log-item.forbidden {{ background: var(--red-bg); border-color: rgba(180,35,24,0.4); }}
    .log-item.refused {{ background: var(--amber-bg); border-color: rgba(138,82,0,0.35); }}
    .log-top {{ display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-size: 13px; font-weight: 600; }}
    .http-badge {{ font-size: 11px; padding: 2px 7px; border-radius: 999px; background: rgba(255,255,255,0.75); }}
    .cmd-out {{ margin-top: 6px; font-size: 14px; }}
    .cmd-time {{ margin-top: 4px; font-size: 11px; color: var(--muted); }}
    .empty {{ font-size: 13px; color: var(--muted); }}
    .policy-note {{ font-size: 12px; color: var(--muted); margin-top: 10px; line-height: 1.5; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="head">
      <div>
        <h1>ESP8266 Node · Điều khiển giọng nói ngoại tuyến qua LAN (A1–A3)</h1>
        <div class="sub">Node: <strong>{html.escape(self.node_id)}</strong> · Endpoint: <code>POST /offline/cmd</code> · Không cần máy chủ · Không kiểm tra vai trò (Cấp 1/2/3 như nhau)</div>
      </div>
      <div class="sub">Góc Servo Cửa chính: <strong id="doorAngleVal">{int(st['door_angle_deg'])}°</strong></div>
    </div>

    <div id="offlineBanner" class="{banner_cls}" role="status">{html.escape(banner_txt)}</div>

    <div class="layout">
      <section class="panel">
        <h2>Trạng thái phần cứng vật lý trên mạch ESP8266</h2>
        <div class="grid" id="hwDeviceGrid">
          {''.join(cards_html)}
        </div>
        <p class="policy-note">
          Quy tắc ngoại tuyến cố định: Hỗ trợ bật/tắt cơ bản đèn, bơm, loa, còi và đóng cửa không cần tài khoản/phân quyền.
          Tuyệt đối chặn mở cửa chính tại firmware (HTTP 403) và từ chối lệnh tùy chỉnh/đặt lịch (HTTP 400).
        </p>
      </section>

      <section class="panel">
        <h2>Khẩu lệnh giọng nói ngoại tuyến (On-device ASR → LAN)</h2>
        <form class="cmd-form" id="offlineCmdForm">
          <input id="offlineCmdInput" type="text" placeholder="Nhập khẩu lệnh tiếng Việt (ví dụ: bật đèn phòng khách)..." autocomplete="off">
          <button id="btnSendOfflineCmd" type="submit">Gửi LAN</button>
        </form>
        <div id="latestOfflineReply" class="reply-box" role="status" aria-live="polite">
          Sẵn sàng nhận lệnh giọng nói ngoại tuyến trực tiếp trên mạch ESP8266.
        </div>
        <div class="log-list" id="offlineLogList">
          {history_html}
        </div>
      </section>
    </div>
  </div>
  <script>
    const form = document.getElementById('offlineCmdForm');
    const input = document.getElementById('offlineCmdInput');
    const replyBox = document.getElementById('latestOfflineReply');
    form.addEventListener('submit', async (ev) => {{
      ev.preventDefault();
      const text = (input.value || '').trim();
      if (!text) return;
      const res = await fetch('/offline/cmd', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ text }})
      }});
      const data = await res.json();
      replyBox.textContent = `[HTTP ${{res.status}}] ${{data.reply_vi || ''}}`;
      window.location.reload();
    }});
  </script>
</body>
</html>
"""

    def start(self) -> None:
        node = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

            def _send_json(self, code: int, payload: dict[str, Any]) -> None:
                raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _send_html(self, code: int, html_str: str) -> None:
                raw = html_str.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length") or "0")
                if length <= 0:
                    return {}
                raw = self.rfile.read(length).decode("utf-8", errors="ignore")
                try:
                    data = json.loads(raw)
                    return data if isinstance(data, dict) else {}
                except Exception:
                    return {}

            def do_OPTIONS(self) -> None:
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self) -> None:
                path = self.path.split("?", 1)[0]
                if path == "/offline/status":
                    self._send_json(200, node.get_status_payload())
                    return
                if path in ("/", "/index.html"):
                    self._send_html(200, node.render_html_console())
                    return
                self._send_json(404, {"ok": False, "error": "Not found"})

            def do_POST(self) -> None:
                path = self.path.split("?", 1)[0]
                body = self._read_json()
                if path == "/offline/cmd":
                    code, payload = node.execute_offline_cmd(body)
                    self._send_json(code, payload)
                    return
                if path == "/sim/disconnect":
                    res = node.simulate_disconnect(send_lwt=bool(body.get("send_lwt", False)))
                    self._send_json(200, res)
                    return
                if path == "/sim/reconnect":
                    res = node.simulate_reconnect()
                    self._send_json(200, res)
                    return
                if path == "/sim/reset_history":
                    with node._lock:
                        node.command_history = []
                    self._send_json(200, {"ok": True})
                    return
                self._send_json(404, {"ok": False, "error": "Not found"})

        self._stop_event.clear()
        self._httpd = ThreadingHTTPServer((self.listen_host, self.listen_port), _Handler)
        self._httpd.daemon_threads = True
        self._http_thread = threading.Thread(
            target=self._httpd.serve_forever,
            kwargs={"poll_interval": 0.2},
            daemon=True,
            name="mock-esp8266-http",
        )
        self._http_thread.start()
        self._hb_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="mock-esp8266-heartbeat",
        )
        self._hb_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None
        if self._http_thread is not None:
            self._http_thread.join(timeout=2.0)
            self._http_thread = None
        if self._hb_thread is not None:
            self._hb_thread.join(timeout=2.0)
            self._hb_thread = None


def main() -> int:
    parser = argparse.ArgumentParser(description="Mock ESP8266 Hardware Client & LAN Offline Node")
    parser.add_argument("--server-url", default="http://127.0.0.1:8092", help="Central server URL (never 8088)")
    parser.add_argument("--listen-host", default="127.0.0.1", help="Local LAN mock HTTP bind host")
    parser.add_argument("--listen-port", type=int, default=8093, help="Local LAN mock HTTP bind port")
    parser.add_argument("--heartbeat-interval", type=float, default=1.5, help="Heartbeat interval seconds")
    parser.add_argument("--node-id", default="esp8266_node_01", help="ESP8266 node identifier")
    parser.add_argument("--hardware-key", default="", help="Override SMARTHOME_HARDWARE_API_KEY")
    args = parser.parse_args()

    node = MockESP8266Node(
        server_url=args.server_url,
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        heartbeat_interval=args.heartbeat_interval,
        node_id=args.node_id,
        hardware_key=args.hardware_key,
    )
    node.start()
    stop_flag = threading.Event()

    def _on_signal(_sig: int, _frame: Any) -> None:
        stop_flag.set()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)
    print(
        f"[mock_esp8266] Listening on http://{args.listen_host}:{args.listen_port} "
        f"(server={args.server_url}, interval={args.heartbeat_interval}s, node={args.node_id})",
        flush=True,
    )
    try:
        while not stop_flag.is_set():
            stop_flag.wait(0.5)
    finally:
        node.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
