"""BoardHealth Domain Module: ESP8266 Heartbeat Liveness, LWT, Timeout & A4 Resync Metadata."""

from __future__ import annotations

import math
import threading
import time
from typing import Any

from backend.engine.constants_and_time import (
    format_vn_timestamp_vi,
    get_board_heartbeat_timeout_sec,
)

DEFAULT_BOARD_NODE_ID = "esp8266_node_01"
BOARD_STATUS_ONLINE = "ONLINE"
BOARD_STATUS_OFFLINE = "OFFLINE"
BOARD_STATUS_VI_ONLINE = "Đang kết nối"
BOARD_STATUS_VI_OFFLINE = "Mất kết nối"


def _clamp_rssi(val: Any, fallback: int = -52) -> int:
    if val is None or isinstance(val, bool):
        return fallback
    try:
        f = float(val)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(f):
        return fallback
    return int(max(-100.0, min(0.0, f)))


def _safe_nonneg_int(val: Any, fallback: int = 0) -> int:
    if val is None or isinstance(val, bool):
        return fallback
    try:
        iv = int(float(val))
    except (TypeError, ValueError):
        return fallback
    return max(0, iv)


class BoardHealthTracker:
    """Thread-safe tracker for ESP8266 heartbeat liveness, LWT offline state, and A4 resync history."""

    def __init__(
        self,
        node_id: str = DEFAULT_BOARD_NODE_ID,
        *,
        now: float | None = None,
    ) -> None:
        self._lock = threading.RLock()
        t0 = float(time.time() if now is None else now)
        self.node_id: str = str(node_id or DEFAULT_BOARD_NODE_ID)
        self.last_seen: float = t0
        self.lwt_online: bool = True
        self.offline_since: float | None = None
        self.offline_resync_count: int = 0
        self.last_resync_at: float = 0.0
        self.last_resync_changed_devices: list[str] = []
        self.last_resync_events: list[dict[str, Any]] = []
        self.wifi_rssi_dbm: int = -52
        self.uptime_ms: int = 0
        self.firmware_mode: str = "ONLINE"
        self._last_evaluated_online: bool = True

    def evaluate_board_health(self, now: float | None = None) -> dict[str, Any]:
        """Compute canonical `board_health` snapshot payload according to frozen G1 contract."""
        with self._lock:
            cur = float(time.time() if now is None else now)
            timeout_sec = float(get_board_heartbeat_timeout_sec())
            age_sec = max(0.0, cur - float(self.last_seen or 0.0))
            timed_out = age_sec > timeout_sec
            online = bool(self.lwt_online and not timed_out)
            if not online:
                if self.offline_since is None:
                    self.offline_since = (
                        (float(self.last_seen) + timeout_sec)
                        if (self.lwt_online and timed_out)
                        else cur
                    )
            else:
                self.offline_since = None

            return {
                "node_id": self.node_id,
                "online": online,
                "status": BOARD_STATUS_ONLINE if online else BOARD_STATUS_OFFLINE,
                "status_vi": BOARD_STATUS_VI_ONLINE if online else BOARD_STATUS_VI_OFFLINE,
                "last_seen": round(float(self.last_seen), 3),
                "last_seen_vi": format_vn_timestamp_vi(self.last_seen),
                "last_seen_age_sec": round(age_sec, 2),
                "heartbeat_timeout_sec": timeout_sec,
                "offline_since": round(float(self.offline_since), 3) if self.offline_since is not None else None,
                "offline_resync_count": int(self.offline_resync_count),
                "last_resync_at": round(float(self.last_resync_at), 3),
                "last_resync_changed_devices": list(self.last_resync_changed_devices),
                "last_resync_events": list(self.last_resync_events),
                "wifi_rssi_dbm": int(self.wifi_rssi_dbm),
                "lwt_online": bool(self.lwt_online),
                "uptime_ms": int(self.uptime_ms),
                "firmware_mode": str(self.firmware_mode),
            }

    def is_online(self, now: float | None = None) -> bool:
        return bool(self.evaluate_board_health(now=now)["online"])

    def record_heartbeat(
        self,
        *,
        node_id: str | None = None,
        wifi_rssi_dbm: Any = None,
        uptime_ms: Any = None,
        firmware_mode: str | None = None,
        now: float | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Refresh `last_seen`, mark `lwt_online=True`, and return `(board_health, recovered)`."""
        with self._lock:
            cur = float(time.time() if now is None else now)
            was_online_live = bool(self.evaluate_board_health(now=cur)["online"])
            recovered = (not self._last_evaluated_online) or (not was_online_live)

            if node_id:
                self.node_id = str(node_id).strip()[:64] or self.node_id
            if wifi_rssi_dbm is not None:
                self.wifi_rssi_dbm = _clamp_rssi(wifi_rssi_dbm, self.wifi_rssi_dbm)
            if uptime_ms is not None:
                self.uptime_ms = _safe_nonneg_int(uptime_ms, self.uptime_ms)
            if firmware_mode:
                self.firmware_mode = str(firmware_mode).strip().upper()[:32] or self.firmware_mode
            else:
                self.firmware_mode = "ONLINE"

            self.last_seen = cur
            self.lwt_online = True
            self.offline_since = None
            self._last_evaluated_online = True
            return self.evaluate_board_health(now=cur), recovered

    def record_lwt(
        self,
        *,
        online: bool,
        node_id: str | None = None,
        now: float | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Apply explicit MQTT LWT / disconnect notification and return `(board_health, transitioned)`."""
        with self._lock:
            cur = float(time.time() if now is None else now)
            prev_online = bool(self.evaluate_board_health(now=cur)["online"]) and self._last_evaluated_online
            if node_id:
                self.node_id = str(node_id).strip()[:64] or self.node_id
            target_online = bool(online)
            self.lwt_online = target_online
            if target_online:
                self.last_seen = cur
                self.offline_since = None
                self.firmware_mode = "ONLINE"
            else:
                if self.offline_since is None:
                    self.offline_since = cur
                self.firmware_mode = "OFFLINE"
            bh = self.evaluate_board_health(now=cur)
            transitioned = bool(bh["online"]) != prev_online
            self._last_evaluated_online = bool(bh["online"])
            return bh, transitioned

    def record_resync(
        self,
        *,
        node_id: str | None = None,
        wifi_rssi_dbm: Any = None,
        changed_devices: list[str] | None = None,
        offline_events: list[dict[str, Any]] | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Record an Addendum A4 reconnect resync event and mark board online."""
        with self._lock:
            cur = float(time.time() if now is None else now)
            if node_id:
                self.node_id = str(node_id).strip()[:64] or self.node_id
            if wifi_rssi_dbm is not None:
                self.wifi_rssi_dbm = _clamp_rssi(wifi_rssi_dbm, self.wifi_rssi_dbm)
            self.last_seen = cur
            self.lwt_online = True
            self.offline_since = None
            self.firmware_mode = "ONLINE"
            self.offline_resync_count += 1
            self.last_resync_at = cur
            self.last_resync_changed_devices = [str(d) for d in (changed_devices or []) if str(d).strip()]
            self.last_resync_events = [
                dict(ev) for ev in (offline_events or []) if isinstance(ev, dict)
            ][-20:]
            self._last_evaluated_online = True
            return self.evaluate_board_health(now=cur)

    def check_transition(self, now: float | None = None) -> tuple[str | None, dict[str, Any]]:
        """Detect `ONLINE_TO_OFFLINE` or `OFFLINE_TO_ONLINE` transitions for the 1s watchdog."""
        with self._lock:
            bh = self.evaluate_board_health(now=now)
            cur_online = bool(bh["online"])
            prev_online = bool(self._last_evaluated_online)
            self._last_evaluated_online = cur_online
            if prev_online and not cur_online:
                return "ONLINE_TO_OFFLINE", bh
            if not prev_online and cur_online:
                return "OFFLINE_TO_ONLINE", bh
            return None, bh

    def reset_online(self, now: float | None = None) -> dict[str, Any]:
        """Reset connectivity state to clean ONLINE (used during full factory_reset)."""
        with self._lock:
            cur = float(time.time() if now is None else now)
            self.last_seen = cur
            self.lwt_online = True
            self.offline_since = None
            self.firmware_mode = "ONLINE"
            self._last_evaluated_online = True
            return self.evaluate_board_health(now=cur)

    def to_shared_dict(self) -> dict[str, Any]:
        """Serialize tracker state for shared state store persistence."""
        with self._lock:
            return {
                "node_id": self.node_id,
                "last_seen": float(self.last_seen),
                "lwt_online": bool(self.lwt_online),
                "offline_since": float(self.offline_since) if self.offline_since is not None else None,
                "offline_resync_count": int(self.offline_resync_count),
                "last_resync_at": float(self.last_resync_at),
                "last_resync_changed_devices": list(self.last_resync_changed_devices),
                "last_resync_events": list(self.last_resync_events),
                "wifi_rssi_dbm": int(self.wifi_rssi_dbm),
                "uptime_ms": int(self.uptime_ms),
                "firmware_mode": str(self.firmware_mode),
            }

    def apply_shared_dict(self, data: dict[str, Any]) -> None:
        """Hydrate tracker state from shared state store payload."""
        if not isinstance(data, dict):
            return
        with self._lock:
            if data.get("node_id"):
                self.node_id = str(data["node_id"])
            if "last_seen" in data and data["last_seen"] is not None:
                try:
                    ts = float(data["last_seen"])
                    if math.isfinite(ts) and ts > 0:
                        self.last_seen = ts
                except (TypeError, ValueError):
                    pass
            if "lwt_online" in data:
                self.lwt_online = bool(data["lwt_online"])
            if "offline_since" in data:
                raw_os = data["offline_since"]
                if raw_os is None:
                    self.offline_since = None
                else:
                    try:
                        val_os = float(raw_os)
                        self.offline_since = val_os if math.isfinite(val_os) and val_os > 0 else None
                    except (TypeError, ValueError):
                        pass
            if "offline_resync_count" in data:
                self.offline_resync_count = _safe_nonneg_int(data["offline_resync_count"], self.offline_resync_count)
            if "last_resync_at" in data:
                try:
                    v_ra = float(data["last_resync_at"] or 0.0)
                    if math.isfinite(v_ra) and v_ra >= 0:
                        self.last_resync_at = v_ra
                except (TypeError, ValueError):
                    pass
            if isinstance(data.get("last_resync_changed_devices"), list):
                self.last_resync_changed_devices = [str(x) for x in data["last_resync_changed_devices"]]
            if isinstance(data.get("last_resync_events"), list):
                self.last_resync_events = [dict(x) for x in data["last_resync_events"] if isinstance(x, dict)][-20:]
            if "wifi_rssi_dbm" in data:
                self.wifi_rssi_dbm = _clamp_rssi(data["wifi_rssi_dbm"], self.wifi_rssi_dbm)
            if "uptime_ms" in data:
                self.uptime_ms = _safe_nonneg_int(data["uptime_ms"], self.uptime_ms)
            if data.get("firmware_mode"):
                self.firmware_mode = str(data["firmware_mode"])
            self._last_evaluated_online = bool(self.evaluate_board_health()["online"])


def evaluate_board_health(tracker: BoardHealthTracker, now: float | None = None) -> dict[str, Any]:
    """Convenience functional wrapper around `BoardHealthTracker.evaluate_board_health()`."""
    return tracker.evaluate_board_health(now=now)


def enrich_device_with_board_health(
    device: dict[str, Any],
    board_health: dict[str, Any],
) -> dict[str, Any]:
    """Attach standardized connectivity fields to a device record for snapshots and API responses."""
    bh = board_health if isinstance(board_health, dict) else {}
    online = bool(bh.get("online", True))
    return {
        **dict(device),
        "board_online": online,
        "connectivity_status": str(bh.get("status") or (BOARD_STATUS_ONLINE if online else BOARD_STATUS_OFFLINE)),
        "connectivity_label_vi": str(bh.get("status_vi") or (BOARD_STATUS_VI_ONLINE if online else BOARD_STATUS_VI_OFFLINE)),
        "last_seen": float(bh.get("last_seen", 0.0) or 0.0),
        "last_seen_vi": str(bh.get("last_seen_vi") or ""),
    }


__all__ = [
    "DEFAULT_BOARD_NODE_ID",
    "BOARD_STATUS_ONLINE",
    "BOARD_STATUS_OFFLINE",
    "BOARD_STATUS_VI_ONLINE",
    "BOARD_STATUS_VI_OFFLINE",
    "BoardHealthTracker",
    "evaluate_board_health",
    "enrich_device_with_board_health",
]
