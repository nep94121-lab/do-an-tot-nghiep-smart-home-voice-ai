"""Bộ quản lý Thiết bị 3D, Phân quyền (RBAC), 2 Bể (Bể Hẹn Giờ & Bể Luật Động),
Đổi từ, Đổi lệnh, Quan hệ IF sát nghĩa (1 chiều vs 2 chiều) và Reset có Xác nhận 2 bước.

Đã được phân tách mô-đun chuẩn kiến trúc sang gói `simulator/engine/`:
- `simulator.engine.constants_and_time`: Hằng số GPIO, Thiết bị mặc định, Phân tích giờ/ngày Việt Nam.
- `simulator.engine.audit_logger`: Nhật ký kiểm toán bền vững JSONL + SQLite.
- `simulator.engine.voice_rbac_mixin`: Chính sách hệ thống, Phân quyền 3 Tầng và Thu âm cấp quyền giọng nói.
- `simulator.engine.timers_pool`: Bể 1 (Bể Hẹn Giờ 1 lần/lặp lại, bảo vệ lịch Tầng 1).
- `simulator.engine.rules_pool`: Bể 2 (Đổi từ, Đổi lệnh, Luật IF-ELSE, Chế độ Offline, 4 Phạm vi Reset).
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import logging
import os
import re
import sys
import threading
import time
from typing import Any, Callable, Coroutine, Iterator

_PENDING_AUDIT_TASKS: set[asyncio.Task[Any]] = set()


def _discard_audit_task(task: asyncio.Task[Any]) -> None:
    _PENDING_AUDIT_TASKS.discard(task)
    if not task.cancelled():
        try:
            task.exception()
        except Exception:
            pass

logger = logging.getLogger(__name__)

from simulator.database_sqlite import (
    init_sqlite_database,
    insert_audit_log_sqlite,
    sync_engine_state_to_sqlite,
)
from simulator.engine import (
    ACTION_TO_STATE,
    ACTION_VI_LABEL,
    AUDIT_LOG_FILE,
    DATA_DIR,
    DEFAULT_DEVICES,
    DEFAULT_USERS,
    FACTORY_FILE,
    HARDWARE_AUDIO_PINS,
    OVERLAY_FILE,
    REPEAT_INTERVAL_SECONDS,
    REPEAT_VI_LABELS,
    ROLE_LEVELS,
    ROLE_NAMES,
    STATE_TO_OPPOSITE,
    VN_TZ,
    EngineRulesMixin,
    EngineTimersMixin,
    EngineVoiceRbacMixin,
    FileStateBackend,
    InMemoryStateBackend,
    StateBackend,
    TrackedDeviceDict,
    VercelBlobStateBackend,
    _extract_vn_date,
    _format_clock_12h,
    append_audit_log,
    clear_audit_logs,
    create_state_backend_from_env,
    detect_repeat_mode,
    ensure_factory_file,
    format_vn_time_ampm,
    get_default_state_backend,
    get_vn_now,
    normalize_reset_scope,
    parse_vn_clock_and_date,
    parse_vn_time_string,
    read_audit_logs,
    set_default_state_backend,
)
from simulator.engine.constants_and_time import (
    DEVICE_CAPABILITIES,
    DEVICE_DEFAULT_SETTINGS,
    DEVICE_ID_ALIASES,
)
from simulator.engine.voice_rbac_mixin import (
    PermissionCheckResult,
    UNKNOWN_REJECTION_REASON,
    UNKNOWN_SPOKEN_REPLY,
)
from simulator.mqtt_bridge import SmartHomeMQTTBridge
from simulator.voice_config import (
    OWNER_DISPLAY_NAME,
    OWNER_EMAIL,
    OWNER_ID,
    ROLE_MAP,
    USER_ROLE_MAP,
    is_throwaway_qa_identity,
)


class SmartHomeEngine(EngineVoiceRbacMixin, EngineTimersMixin, EngineRulesMixin):
    """Lõi điều hành trung tâm Smart Home: tích hợp 3 Mixin (Voice RBAC, Bể 1 Timers, Bể 2 Rules) và Actuation MQTT."""

    def __init__(
        self,
        on_event: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
        on_voice_reset: Callable[[], dict[str, Any]] | None = None,
        state_backend: StateBackend | None = None,
    ):
        self._root_engine: "SmartHomeEngine" = self
        self._state_sync_lock = threading.RLock()
        self._cas_owner_lock = threading.Lock()
        self._cas_owner_tid: int | None = None
        self._cas_owner_task_id: int | None = None
        self._applying_shared_state_depth: int = 1
        self._applying_shared_state: bool = True
        self._initialized_devices: bool = False
        self._state_backend: StateBackend | None = state_backend
        self._mutation_depth: int = 0
        self._state_dirty_in_tx: bool = False
        self._dirty_device_ids: set[str] = set()
        self._last_synced_seq: int = 0
        self._last_synced_ts_ns: int = 0
        self.on_event = on_event
        self.on_voice_reset = on_voice_reset
        self._current_user_id: str = OWNER_ID
        self._current_role: str = "ADMIN"
        self.devices: dict[str, dict[str, Any]] = {
            k: TrackedDeviceDict(v, updated_at=time.time(), _engine=self) for k, v in DEFAULT_DEVICES.items()
        }
        self.factory_rules = ensure_factory_file()
        self.overlay_rules = self._load_overlay()
        self.users: dict[str, dict[str, Any]] = self._init_users()
        self.active_timers: dict[str, dict[str, Any]] = {}
        self._timer_tasks: dict[str, asyncio.Task] = {}
        self._timer_seq = 0
        self.pending_reset_confirmation: bool = False
        self.pending_reset_scope: str = "all"
        self.pending_rule: dict[str, Any] | None = None
        self.pending_voice_enrollment: dict[str, Any] | None = None
        self.server_connected: bool = True
        self.pump_manual_override_off: bool = False
        self.house_mode: str = "HOME"
        self._compound_eval_depth: int = 0
        self._explicit_test_user_set: bool = False
        self.mqtt_bridge = SmartHomeMQTTBridge(on_event=self.emit)
        self._applying_shared_state_depth = 0
        self._applying_shared_state = False
        self._initialized_devices = True
        try:
            if state_backend is not None or not getattr(self.state_backend, "is_remote", False):
                self.sync_from_shared_store(force=True)
        except Exception:
            pass
        try:
            init_sqlite_database()
            sync_engine_state_to_sqlite(self)
        except Exception:
            pass

    def create_isolated_ws_view(
        self,
        on_event: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
        on_voice_reset: Callable[[], dict[str, Any]] | None = None,
    ) -> "SmartHomeEngine":
        """Tạo một khung nhìn Engine cô lập danh tính người nói (_current_user_id, _current_role)
        cho từng kết nối WebSocket /ws riêng biệt, trong khi vẫn chia sẻ trực tiếp trạng thái vật lý
        (devices, mqtt_bridge, active_timers, overlay_rules, users) với _REST_ENGINE.
        """
        root = getattr(self, "_root_engine", self)
        view = object.__new__(SmartHomeEngine)
        object.__setattr__(view, "_root_engine", root)
        object.__setattr__(view, "_state_sync_lock", root._state_sync_lock)
        object.__setattr__(view, "_cas_owner_lock", root._cas_owner_lock)
        object.__setattr__(view, "_cas_owner_tid", None)
        object.__setattr__(view, "_cas_owner_task_id", None)
        object.__setattr__(view, "_applying_shared_state_depth", 0)
        object.__setattr__(view, "_applying_shared_state", True)
        object.__setattr__(view, "_initialized_devices", False)
        object.__setattr__(view, "_state_backend", root._state_backend)
        object.__setattr__(view, "_mutation_depth", 0)
        object.__setattr__(view, "_state_dirty_in_tx", False)
        object.__setattr__(view, "_dirty_device_ids", root._dirty_device_ids)
        object.__setattr__(view, "_last_synced_seq", root._last_synced_seq)
        object.__setattr__(view, "_last_synced_ts_ns", root._last_synced_ts_ns)
        object.__setattr__(view, "on_event", on_event)
        object.__setattr__(view, "on_voice_reset", on_voice_reset or self.on_voice_reset)
        object.__setattr__(view, "_current_user_id", "UNKNOWN")
        object.__setattr__(view, "_current_role", "UNKNOWN")
        object.__setattr__(view, "_explicit_test_user_set", False)
        object.__setattr__(view, "devices", root.devices)
        object.__setattr__(view, "factory_rules", root.factory_rules)
        object.__setattr__(view, "overlay_rules", root.overlay_rules)
        object.__setattr__(view, "users", root.users)
        object.__setattr__(view, "active_timers", root.active_timers)
        object.__setattr__(view, "_timer_tasks", root._timer_tasks)
        object.__setattr__(view, "_timer_seq", root._timer_seq)
        object.__setattr__(view, "pending_reset_confirmation", False)
        object.__setattr__(view, "pending_reset_scope", "all")
        object.__setattr__(view, "pending_rule", None)
        object.__setattr__(view, "pending_voice_enrollment", None)
        object.__setattr__(view, "server_connected", root.server_connected)
        object.__setattr__(view, "pump_manual_override_off", root.pump_manual_override_off)
        object.__setattr__(view, "house_mode", getattr(root, "house_mode", "HOME"))
        object.__setattr__(view, "_compound_eval_depth", 0)
        object.__setattr__(view, "mqtt_bridge", root.mqtt_bridge)
        object.__setattr__(view, "_applying_shared_state", False)
        object.__setattr__(view, "_initialized_devices", True)
        view.set_active_user("UNKNOWN")
        return view

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "devices" and isinstance(value, dict):
            wrapped = {
                k: (v if isinstance(v, TrackedDeviceDict) and getattr(v, "_engine", None) is self else TrackedDeviceDict(v, _engine=self))
                for k, v in value.items()
            }
            super().__setattr__(name, wrapped)
            if getattr(self, "_initialized_devices", False) and not getattr(self, "_applying_shared_state", False):
                for dev_id in wrapped:
                    self._on_direct_device_mutation(str(dev_id))
            return
        super().__setattr__(name, value)

    @property
    def state_backend(self) -> StateBackend:
        if self._state_backend is not None:
            return self._state_backend
        return get_default_state_backend()

    def set_state_backend(self, backend: StateBackend | None) -> None:
        self._state_backend = backend

    def _build_shared_state_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "revision_seq": self._last_synced_seq,
            "revision_ts_ns": self._last_synced_ts_ns,
            "server_connected": bool(self.server_connected),
            "pump_manual_override_off": bool(getattr(self, "pump_manual_override_off", False)),
            "house_mode": str(getattr(self, "house_mode", "HOME") or "HOME"),
            "devices": {
                k: {
                    "id": str(v.get("id", k)),
                    "name": str(v.get("name", DEFAULT_DEVICES.get(k, {}).get("name", k))),
                    "gpio": str(v.get("gpio", DEFAULT_DEVICES.get(k, {}).get("gpio", ""))),
                    "type": str(v.get("type", DEFAULT_DEVICES.get(k, {}).get("type", "light"))),
                    "state": str(v.get("state", DEFAULT_DEVICES.get(k, {}).get("state", "OFF"))),
                    "min_role": str(v.get("min_role", DEFAULT_DEVICES.get(k, {}).get("min_role", "CHILD_GUEST"))),
                    "updated_at": float(v.get("updated_at", time.time())),
                    "version": int(v.get("version", 1)),
                    "last_client_id": str(v.get("last_client_id", "")),
                    "last_client_seq": int(v.get("last_client_seq", 0)),
                    "last_client_ts_ms": int(v.get("last_client_ts_ms", 0)),
                    "last_request_id": str(v.get("last_request_id", "")),
                    "last_requested_state": str(v.get("last_requested_state", v.get("state", "OFF"))),
                    "client_seqs": dict(v.get("client_seqs", {})) if isinstance(v.get("client_seqs"), dict) else {},
                    "settings": dict(v.get("settings", {})) if isinstance(v.get("settings"), dict) else {},
                }
                for k, v in self.devices.items()
            },
        }
        if hasattr(self, "mqtt_bridge") and self.mqtt_bridge is not None:
            if hasattr(self.mqtt_bridge, "dht11_telemetry"):
                payload["dht11_telemetry"] = dict(self.mqtt_bridge.dht11_telemetry)
            if hasattr(self.mqtt_bridge, "soil_moisture_telemetry"):
                payload["soil_moisture_telemetry"] = dict(self.mqtt_bridge.soil_moisture_telemetry)
            if hasattr(self.mqtt_bridge, "sound_telemetry"):
                payload["sound_telemetry"] = dict(self.mqtt_bridge.sound_telemetry)
        return payload

    def persist_to_shared_store(self) -> dict[str, Any]:
        """Ghi trạng thái thiết bị hiện tại xuống tầng lưu trữ chia sẻ (Vercel Blob / File / InMemory)."""
        root = getattr(self, "_root_engine", self)
        if root is not self:
            root.server_connected = self.server_connected
            root.pump_manual_override_off = getattr(self, "pump_manual_override_off", False)
            root.house_mode = getattr(self, "house_mode", getattr(root, "house_mode", "HOME"))
            saved = root.persist_to_shared_store()
            self._last_synced_seq = root._last_synced_seq
            self._last_synced_ts_ns = root._last_synced_ts_ns
            return saved
        with self._state_sync_lock:
            self._dirty_device_ids.clear()
            payload = self._build_shared_state_payload()
            try:
                saved = self.state_backend.save_state(payload)
                self._last_synced_seq = max(self._last_synced_seq, int(saved.get("revision_seq", 0)))
                self._last_synced_ts_ns = max(self._last_synced_ts_ns, int(saved.get("revision_ts_ns", 0)))
            except Exception as exc:
                logger.warning("Failed to persist state to backend %s: %s", self.state_backend, exc)
                saved = payload
            try:
                sync_engine_state_to_sqlite(self)
            except Exception:
                pass
            try:
                from simulator.realtime_hub import get_realtime_hub

                get_realtime_hub().publish_snapshot(self, reason="state_persist")
            except Exception:
                pass
            return saved

    def _apply_shared_dict(
        self,
        shared: dict[str, Any],
        *,
        authoritative: bool = False,
        dirty_ids: set[str] | None = None,
    ) -> bool:
        """Áp dụng payload trạng thái chia sẻ vào RAM của engine hiện tại (thread-safe nếu gọi dưới _state_sync_lock)."""
        if not isinstance(shared, dict) or not isinstance(shared.get("devices"), dict):
            return False
        dirty = dirty_ids or set()
        prev_synced_seq = self._last_synced_seq
        prev_states = {k: v.get("state") for k, v in self.devices.items() if isinstance(v, dict)}
        self._applying_shared_state_depth += 1
        self._applying_shared_state = True
        try:
            if "server_connected" in shared and not dirty:
                self.server_connected = bool(shared["server_connected"])
                if hasattr(self, "mqtt_bridge") and self.mqtt_bridge is not None:
                    self.mqtt_bridge.esp8266_status["online"] = self.server_connected
                    self.mqtt_bridge.esp8266_status["power_mode"] = (
                        "SERVER_ONLINE_FULL_AI" if self.server_connected else "OFFLINE_DEFAULT_DOOR_LOCKED"
                    )
            if "pump_manual_override_off" in shared and "garden_pump" not in dirty:
                self.pump_manual_override_off = bool(shared["pump_manual_override_off"])
            if "house_mode" in shared and not dirty:
                hm_val = str(shared.get("house_mode") or "HOME").strip().upper()
                if hm_val in ("HOME", "AWAY"):
                    self.house_mode = hm_val

            remote_rev = int(shared.get("revision_seq", 0) or 0)
            local_rev = int(self._last_synced_seq or 0)
            remote_devices = shared.get("devices", {})
            for dev_id, dev_data in remote_devices.items():
                if dev_id in dirty:
                    continue
                if dev_id in self.devices and isinstance(dev_data, dict):
                    if "state" in dev_data:
                        self.devices[dev_id]["state"] = str(dev_data["state"])
                    if "updated_at" in dev_data:
                        self.devices[dev_id]["updated_at"] = float(dev_data["updated_at"])
                    if "min_role" in dev_data:
                        self.devices[dev_id]["min_role"] = str(dev_data["min_role"])
                    if isinstance(dev_data.get("settings"), dict):
                        self.devices[dev_id]["settings"] = dict(dev_data["settings"])
                    if "version" in dev_data:
                        if authoritative:
                            self.devices[dev_id]["version"] = int(dev_data["version"])
                        else:
                            self.devices[dev_id]["version"] = max(
                                int(self.devices[dev_id].get("version", 1)),
                                int(dev_data["version"]),
                            )
                    remote_ts_ms = int(dev_data.get("last_client_ts_ms", 0) or 0)
                    local_ts_ms = int(self.devices[dev_id].get("last_client_ts_ms", 0) or 0)
                    if authoritative or remote_rev >= local_rev or remote_ts_ms >= local_ts_ms:
                        if "last_client_id" in dev_data:
                            self.devices[dev_id]["last_client_id"] = str(dev_data["last_client_id"])
                        elif authoritative:
                            self.devices[dev_id].pop("last_client_id", None)
                        if "last_client_seq" in dev_data:
                            self.devices[dev_id]["last_client_seq"] = int(dev_data["last_client_seq"])
                        elif authoritative:
                            self.devices[dev_id].pop("last_client_seq", None)
                        if "last_client_ts_ms" in dev_data:
                            self.devices[dev_id]["last_client_ts_ms"] = (
                                remote_ts_ms if authoritative else max(local_ts_ms, remote_ts_ms)
                            )
                        elif authoritative:
                            self.devices[dev_id].pop("last_client_ts_ms", None)
                        if "last_request_id" in dev_data:
                            self.devices[dev_id]["last_request_id"] = str(dev_data["last_request_id"])
                        elif authoritative:
                            self.devices[dev_id].pop("last_request_id", None)
                        if "last_requested_state" in dev_data:
                            self.devices[dev_id]["last_requested_state"] = str(dev_data["last_requested_state"])
                        elif authoritative:
                            self.devices[dev_id].pop("last_requested_state", None)
                    if isinstance(dev_data.get("client_seqs"), dict):
                        if authoritative:
                            self.devices[dev_id]["client_seqs"] = copy.deepcopy(dev_data["client_seqs"])
                        else:
                            merged_cseqs = (
                                dict(self.devices[dev_id].get("client_seqs"))
                                if isinstance(self.devices[dev_id].get("client_seqs"), dict)
                                else {}
                            )
                            for cid_k, cid_v in dev_data["client_seqs"].items():
                                if not isinstance(cid_v, dict):
                                    continue
                                cur_v = merged_cseqs.get(cid_k)
                                if str(cid_k) == "__anon__":
                                    incoming_key = (
                                        int(cid_v.get("ts_ms", 0) or 0),
                                        int(cid_v.get("seq", 0) or 0),
                                    )
                                    existing_key = (
                                        (
                                            int(cur_v.get("ts_ms", 0) or 0),
                                            int(cur_v.get("seq", 0) or 0),
                                        )
                                        if isinstance(cur_v, dict)
                                        else (-1, -1)
                                    )
                                else:
                                    incoming_key = (
                                        int(cid_v.get("seq", 0) or 0),
                                        int(cid_v.get("ts_ms", 0) or 0),
                                    )
                                    existing_key = (
                                        (
                                            int(cur_v.get("seq", 0) or 0),
                                            int(cur_v.get("ts_ms", 0) or 0),
                                        )
                                        if isinstance(cur_v, dict)
                                        else (-1, -1)
                                    )
                                if not isinstance(cur_v, dict) or incoming_key >= existing_key:
                                    merged_cseqs[str(cid_k)] = dict(cid_v)
                            self.devices[dev_id]["client_seqs"] = merged_cseqs
                    elif authoritative:
                        self.devices[dev_id].pop("client_seqs", None)
                elif dev_id in DEFAULT_DEVICES and isinstance(dev_data, dict):
                    merged_dev = dict(DEFAULT_DEVICES[dev_id])
                    merged_dev.update(dev_data)
                    self.devices[dev_id] = TrackedDeviceDict(merged_dev, _engine=self)

            if hasattr(self, "mqtt_bridge") and self.mqtt_bridge is not None:
                if isinstance(shared.get("dht11_telemetry"), dict):
                    self.mqtt_bridge.dht11_telemetry.update(shared["dht11_telemetry"])
                if isinstance(shared.get("soil_moisture_telemetry"), dict):
                    self.mqtt_bridge.soil_moisture_telemetry.update(shared["soil_moisture_telemetry"])
                if isinstance(shared.get("sound_telemetry"), dict):
                    self.mqtt_bridge.sound_telemetry.update(shared["sound_telemetry"])

            if authoritative:
                self._last_synced_seq = int(shared.get("revision_seq", 0) or 0)
                self._last_synced_ts_ns = int(shared.get("revision_ts_ns", 0) or 0)
            else:
                self._last_synced_seq = max(self._last_synced_seq, int(shared.get("revision_seq", 0) or 0))
                self._last_synced_ts_ns = max(self._last_synced_ts_ns, int(shared.get("revision_ts_ns", 0) or 0))
        finally:
            self._applying_shared_state_depth = max(0, self._applying_shared_state_depth - 1)
            self._applying_shared_state = self._applying_shared_state_depth > 0

        if not dirty:
            cur_states = {k: v.get("state") for k, v in self.devices.items() if isinstance(v, dict)}
            if (
                (self._last_synced_seq != prev_synced_seq or cur_states != prev_states)
                and getattr(getattr(self, "_root_engine", self).state_backend, "__class__", None).__name__
                != "SqliteStateBackend"
            ):
                try:
                    sync_engine_state_to_sqlite(self)
                except Exception:
                    pass
        return True

    def sync_from_shared_store(self, force: bool = False) -> bool:
        """Đồng bộ trạng thái thiết bị mới nhất từ tầng lưu trữ chia sẻ về RAM của instance hiện tại."""
        root = getattr(self, "_root_engine", self)
        if root is not self:
            ok = root.sync_from_shared_store(force=force)
            self.server_connected = root.server_connected
            self.pump_manual_override_off = getattr(root, "pump_manual_override_off", False)
            self.house_mode = getattr(root, "house_mode", "HOME")
            self._last_synced_seq = root._last_synced_seq
            self._last_synced_ts_ns = root._last_synced_ts_ns
            return ok
        with self._state_sync_lock:
            if not force and self._mutation_depth > 0:
                return False
            shared = self.state_backend.load_state()
            if not isinstance(shared, dict) or not isinstance(shared.get("devices"), dict):
                if self._dirty_device_ids:
                    self.persist_to_shared_store()
                return False

            dirty_ids = set(self._dirty_device_ids)
            is_authoritative = bool(getattr(self.state_backend, "authoritative_cas", False)) and not dirty_ids
            self._apply_shared_dict(shared, authoritative=is_authoritative, dirty_ids=dirty_ids)

            if dirty_ids:
                self._dirty_device_ids.clear()
                self.persist_to_shared_store()
            return True

    def _on_direct_device_mutation(self, dev_id: str) -> None:
        root = getattr(self, "_root_engine", self)
        if root is not self:
            root._on_direct_device_mutation(dev_id)
            return
        if self._applying_shared_state:
            return
        if self._mutation_depth > 0:
            self._state_dirty_in_tx = True
            return
        if getattr(self.state_backend, "is_remote", False):
            if dev_id:
                self._dirty_device_ids.add(dev_id)
        else:
            self.persist_to_shared_store()

    @contextlib.contextmanager
    def state_transaction(self) -> Iterator[None]:
        """Ngữ cảnh giao dịch trạng thái có thể lồng nhau: đồng bộ 1 lần khi vào và lưu bền vững 1 lần khi thoát."""
        root = getattr(self, "_root_engine", self)
        if root is not self:
            with root.state_transaction():
                self.server_connected = root.server_connected
                self.pump_manual_override_off = getattr(root, "pump_manual_override_off", False)
                self.house_mode = getattr(root, "house_mode", "HOME")
                try:
                    yield
                finally:
                    root.server_connected = self.server_connected
                    root.pump_manual_override_off = getattr(self, "pump_manual_override_off", False)
                    root.house_mode = getattr(self, "house_mode", getattr(root, "house_mode", "HOME"))
            return
        is_outer = (self._mutation_depth == 0)
        if is_outer:
            try:
                self.sync_from_shared_store(force=True)
            except Exception as exc:
                logger.warning("state_transaction initial sync failed: %s", exc)
            self._state_dirty_in_tx = False
        self._mutation_depth += 1
        try:
            yield
        finally:
            self._mutation_depth = max(0, self._mutation_depth - 1)
            if is_outer and (self._state_dirty_in_tx or self._dirty_device_ids):
                self._state_dirty_in_tx = False
                try:
                    self.persist_to_shared_store()
                except Exception as exc:
                    logger.warning("state_transaction persist failed: %s", exc)

    def _default_overlay(self) -> dict[str, Any]:
        return {
            "word_mappings": {},
            "aliases": {},
            "if_else_rules": [],
            "chains": [],
            "users": {k: dict(v) for k, v in DEFAULT_USERS.items()},
            "user_pools": {
                OWNER_ID: {"word_mappings": {}, "aliases": {}, "if_else_rules": []},
                "thanh_vien_a": {"word_mappings": {}, "aliases": {}, "if_else_rules": []},
                "thanh_vien_b": {"word_mappings": {}, "aliases": {}, "if_else_rules": []},
            },
        }

    def _load_overlay(self) -> dict[str, Any]:
        if OVERLAY_FILE.exists():
            try:
                data = json.loads(OVERLAY_FILE.read_text(encoding="utf-8"))
                base = self._default_overlay()
                base.update(data)
                if isinstance(base.get("users"), dict):
                    for uid in list(base["users"].keys()):
                        uinfo = base["users"].get(uid) or {}
                        if (
                            is_throwaway_qa_identity(uid)
                            or (isinstance(uinfo, dict) and (
                                is_throwaway_qa_identity(uinfo.get("id"))
                                or is_throwaway_qa_identity(uinfo.get("email"))
                                or is_throwaway_qa_identity(uinfo.get("name"))
                            ))
                        ):
                            base["users"].pop(uid, None)
                if "user_pools" not in base or not isinstance(base["user_pools"], dict):
                    base["user_pools"] = self._default_overlay()["user_pools"]
                for uid in list(base["user_pools"].keys()):
                    if is_throwaway_qa_identity(uid):
                        base["user_pools"].pop(uid, None)
                t1_pool = base["user_pools"].setdefault(
                    OWNER_ID, {"word_mappings": {}, "aliases": {}, "if_else_rules": []}
                )
                if base.get("word_mappings") and not t1_pool.get("word_mappings"):
                    t1_pool["word_mappings"] = dict(base["word_mappings"])
                if base.get("aliases") and not t1_pool.get("aliases"):
                    t1_pool["aliases"] = dict(base["aliases"])
                if base.get("if_else_rules") and not t1_pool.get("if_else_rules"):
                    t1_pool["if_else_rules"] = list(base["if_else_rules"])
                return base
            except Exception:
                pass
        default_ov = self._default_overlay()
        OVERLAY_FILE.write_bytes((json.dumps(default_ov, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return default_ov

    def _get_user_pool(self, user_id: str | None = None) -> dict[str, Any]:
        uid = user_id or self._current_user_id
        if is_throwaway_qa_identity(uid):
            uid = OWNER_ID
        pools = self.overlay_rules.setdefault("user_pools", {})
        if uid not in pools or not isinstance(pools[uid], dict):
            pools[uid] = {"word_mappings": {}, "aliases": {}, "if_else_rules": []}
        pools[uid].setdefault("word_mappings", {})
        pools[uid].setdefault("aliases", {})
        pools[uid].setdefault("if_else_rules", [])
        return pools[uid]

    def _save_overlay(self) -> bool:
        self._purge_throwaway_qa_users()
        t1_pool = self._get_user_pool(OWNER_ID)
        self.overlay_rules["word_mappings"] = dict(t1_pool.get("word_mappings", {}))
        self.overlay_rules["aliases"] = dict(t1_pool.get("aliases", {}))
        self.overlay_rules["if_else_rules"] = list(t1_pool.get("if_else_rules", []))
        self.overlay_rules["users"] = self.users
        prev_disk = OVERLAY_FILE.read_bytes() if OVERLAY_FILE.exists() else None
        raw_bytes = (json.dumps(self.overlay_rules, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        def _restore_overlay_file() -> None:
            if prev_disk is not None:
                with contextlib.suppress(Exception):
                    OVERLAY_FILE.write_bytes(prev_disk)
            elif OVERLAY_FILE.exists():
                with contextlib.suppress(Exception):
                    OVERLAY_FILE.unlink(missing_ok=True)
        try:
            import simulator.durable_store as _ds

            if not _ds.save_durable_json("custom_rules_overlay.json", self.overlay_rules, OVERLAY_FILE):
                _restore_overlay_file()
                return False
        except Exception:
            _restore_overlay_file()
            return False
        try:
            sync_engine_state_to_sqlite(self)
        except Exception:
            pass
        return True

    async def emit(self, event: dict[str, Any]) -> None:
        buf = getattr(self, "_cas_emit_buffer", None)
        if buf is not None:
            buf.append(event)
            return
        if self.on_event is not None:
            await self.on_event(event)
        ev_type = str(event.get("type", ""))
        if ev_type and ev_type not in ("state_snapshot", "mqtt_message", "mqtt_packet"):
            backend_name = getattr(getattr(self, "_root_engine", self).state_backend, "__class__", None).__name__
            skip_sqlite_sync = backend_name == "SqliteStateBackend" and ev_type in (
                "device_updated",
                "device_actuated",
                "device_already_in_state",
            )
            if getattr(self, "_mutation_depth", 0) == 0 and not skip_sqlite_sync:
                try:
                    await asyncio.to_thread(sync_engine_state_to_sqlite, self)
                except Exception:
                    pass
            cat_map = {
                "device_updated": "DEVICE_GPIO",
                "device_actuated": "DEVICE_GPIO",
                "timer_scheduled": "TIMER_POOL",
                "timer_fired": "TIMER_POOL",
                "timer_cancelled": "TIMER_POOL",
                "timer_updated": "TIMER_POOL",
                "word_mapping_added": "RULE_POOL",
                "alias_created": "RULE_POOL",
                "if_else_rule_added": "RULE_POOL",
                "chain_rule_created": "RULE_POOL",
                "pending_confirmation_requested": "RULE_POOL",
                "system_policy_updated": "RULE_POOL",
                "factory_reset_completed": "RULE_POOL",
                "sensor_telemetry_updated": "SENSOR_IOT",
                "soil_moisture_updated": "SENSOR_IOT",
                "sound_sensor_updated": "SENSOR_IOT",
                "server_mode_changed": "SECURITY_MODE",
                "offline_command_blocked": "SECURITY_MODE",
                "offline_default_executed": "SECURITY_MODE",
                "user_permission_granted": "VOICE_AUTH",
                "user_permission_revoked": "VOICE_AUTH",
                "voice_enrollment_started": "VOICE_AUTH",
                "voice_enrollment_completed": "VOICE_AUTH",
            }
            cat = cat_map.get(ev_type, "SYSTEM_EVENT")
            msg = str(
                event.get("message")
                or event.get("spoken_reply")
                or event.get("exact_spoken_reply")
                or (
                    f"Thiết bị {event.get('device_name', '')} ({event.get('gpio', '')}) -> {event.get('new_state', '')} (Nguồn: {event.get('source', '')})"
                    if event.get("device_name")
                    else ev_type
                )
            )
            if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
                await asyncio.to_thread(
                    append_audit_log,
                    category=cat,
                    event_type=ev_type,
                    summary=msg,
                    user_name=self.get_current_user_name(),
                    tier=self.current_tier,
                    details={k: v for k, v in event.items() if k != "snapshot"},
                )
            else:
                _audit_task = asyncio.create_task(
                    asyncio.to_thread(
                        append_audit_log,
                        category=cat,
                        event_type=ev_type,
                        summary=msg,
                        user_name=self.get_current_user_name(),
                        tier=self.current_tier,
                        details={k: v for k, v in event.items() if k != "snapshot"},
                    )
                )
                _PENDING_AUDIT_TASKS.add(_audit_task)
                _audit_task.add_done_callback(_discard_audit_task)

    def _expand_targets(self, device_id: str, action: str) -> list[tuple[str, str]]:
        if "," in device_id:
            expanded: list[tuple[str, str]] = []
            seen: set[tuple[str, str]] = set()
            for part in device_id.split(","):
                p = part.strip()
                if not p:
                    continue
                for item in self._expand_targets(p, action):
                    if item not in seen:
                        seen.add(item)
                        expanded.append(item)
            return expanded
        if device_id == "all_lights":
            act = "turn_on" if action in ("open", "turn_on") else "turn_off"
            return [("living_room_light", act), ("bedroom_light", act)]
        if device_id == "all_devices":
            if action in ("close", "turn_off"):
                return [
                    ("living_room_light", "turn_off"),
                    ("bedroom_light", "turn_off"),
                    ("garden_pump", "turn_off"),
                    ("speaker_amp", "turn_off"),
                    ("alarm_siren", "turn_off"),
                    ("main_door", "close"),
                ]
            return [
                ("living_room_light", "turn_on"),
                ("bedroom_light", "turn_on"),
                ("speaker_amp", "turn_on"),
            ]
        return [(DEVICE_ID_ALIASES.get(device_id, device_id), action)]

    def _state_verb_vi(self, dev_type: str, state: str, already: bool = False) -> str:
        suffix = " sẵn rồi" if already else ""
        if dev_type == "door":
            return f"đã {'mở' if state == 'OPEN' else 'đóng'}{suffix}"
        return f"đã {'bật' if state == 'ON' else 'tắt'}{suffix}"

    def _build_concise_spoken_reply(self, results: list[dict[str, Any]]) -> str:
        ok_items = [r for r in results if r.get("ok")]
        if not ok_items:
            errs = [r.get("error", "Lỗi") for r in results if not r.get("ok")]
            return errs[0] if errs else "Không thể thực hiện."

        changed = [r for r in ok_items if not r.get("already_in_state")]
        already = [r for r in ok_items if r.get("already_in_state")]

        if not changed and already:
            parts = []
            for r in already:
                dtype = self.devices.get(r["device_id"], {}).get("type", "light")
                parts.append(f"{r['device_name']} {self._state_verb_vi(dtype, r['state'], already=True)}")
            return ", ".join(parts) + "."

        if len(changed) >= 2:
            all_on_or_open = all(r["state"] in ("ON", "OPEN") for r in changed)
            all_off_or_closed = all(r["state"] in ("OFF", "CLOSED") for r in changed)
            names = [changed[0]["device_name"]] + [r["device_name"].lower() for r in changed[1:]]
            joined_names = " và ".join(names) if len(names) == 2 else ", ".join(names[:-1]) + " và " + names[-1]
            if all_on_or_open:
                return f"{joined_names} đã mở."
            if all_off_or_closed:
                has_door = any(self.devices.get(r["device_id"], {}).get("type") == "door" for r in changed)
                if not has_door:
                    return f"{joined_names} đã tắt."

        clauses = []
        for idx, r in enumerate(changed):
            dtype = self.devices.get(r["device_id"], {}).get("type", "light")
            dname = r["device_name"] if idx == 0 else r["device_name"].lower()
            clauses.append(f"{dname} {self._state_verb_vi(dtype, r['state'], already=False)}")
        return " và ".join(clauses) + "."

    def set_active_user(self, user_or_role: str | None) -> dict[str, Any]:
        """Đặt người dùng kích hoạt cho engine (kèm cờ _explicit_test_user_set phục vụ tương thích test)."""
        self._explicit_test_user_set = True
        return super().set_active_user(user_or_role)

    async def factory_reset(self, scope: str = "all", *, bypass_rbac: bool = False) -> dict[str, Any]:
        """Khôi phục cài đặt gốc, dọn dẹp cờ override của test."""
        self._explicit_test_user_set = False
        self.server_connected = True
        return await super().factory_reset(scope, bypass_rbac=bypass_rbac)

    def _check_custom_directive_device_lock_parameterized(self, dev_id: str, tier: int) -> tuple[bool, str]:
        """Kiểm tra chỉ thị riêng của Admin theo tier được chỉ định cụ thể."""
        directives = self.system_policies.get("custom_system_directives", [])
        if not directives:
            return True, "OK"
        dev = self.devices.get(dev_id, {})
        dname_low = dev.get("name", "").lower()
        dev_keywords = {
            "main_door": ("cửa chính", "cửa", "main_door"),
            "living_room_light": ("đèn phòng khách", "đèn khách", "living_room_light"),
            "bedroom_light": ("đèn phòng ngủ", "đèn ngủ", "bedroom_light"),
            "garden_pump": ("máy bơm tưới cây", "máy bơm", "bơm nước", "tưới cây", "garden_pump"),
            "alarm_siren": ("còi báo động", "còi", "báo động", "alarm_siren"),
            "speaker_amp": ("nguồn mạch loa", "mạch loa", "pam8403", "loa", "speaker_amp"),
        }.get(dev_id, (dname_low, dev_id))

        cur_hour = get_vn_now().hour
        for raw_dir in directives:
            d_low = str(raw_dir).lower()
            if not any(kw in d_low for kw in dev_keywords):
                continue
            if not any(neg in d_low for neg in ("không được", "cấm", "không cho", "khóa")):
                continue
            if "cấp 3" in d_low and "cấp 2" not in d_low and tier < 3:
                continue
            if "cấp 2" in d_low and "cấp 3" not in d_low and tier != 2:
                continue
            if tier == 1 and ("cấp 2" in d_low or "cấp 3" in d_low or "khách" in d_low):
                continue
            m_after = re.search(r"sau\s+(\d{1,2})\s*(?:giờ|h)", d_low)
            if m_after:
                hr = int(m_after.group(1))
                if any(w in d_low for w in ("đêm", "tối", "chiều", "pm")) and hr < 12:
                    hr += 12
                in_locked_hours = (cur_hour >= hr) or (hr >= 18 and cur_hour < 5)
                if in_locked_hours:
                    return False, f"Từ chối truy cập! Đang bị khóa theo quy định của Admin: '{raw_dir}'."
            else:
                return False, f"Từ chối truy cập! Đang bị khóa theo quy định của Admin: '{raw_dir}'."
        return True, "OK"

    def check_device_permission(
        self,
        dev_id: str,
        action: str | None = None,
        actor_tier: int | None = None,
        actor_user_id: str | None = None,
    ) -> PermissionCheckResult:
        """Kiểm tra quyền điều khiển thiết bị theo RBAC 3 Tầng.
        Hỗ trợ actor_tier truyền vào trực tiếp từ request session để không phụ thuộc vào trạng thái toàn cục Singleton."""
        if actor_tier is None:
            if (
                self._current_role == "UNKNOWN"
                or str(self._current_user_id).strip().lower() in ("", "unknown", "stranger")
                or self.current_tier not in (1, 2, 3)
            ):
                return PermissionCheckResult({
                    "allowed": False,
                    "reason": UNKNOWN_REJECTION_REASON,
                    "tier": 99,
                    "role": "UNKNOWN",
                })
        elif int(actor_tier) not in (1, 2, 3):
            return PermissionCheckResult({
                "allowed": False,
                "reason": UNKNOWN_REJECTION_REASON,
                "tier": 99,
                "role": "UNKNOWN",
            })

        if actor_user_id is not None and str(actor_user_id).strip().lower() in ("", "unknown", "stranger"):
            return PermissionCheckResult({
                "allowed": False,
                "reason": UNKNOWN_REJECTION_REASON,
                "tier": 99,
                "role": "UNKNOWN",
            })

        tier = int(actor_tier) if actor_tier is not None else int(self.current_tier)
        if tier not in (1, 2, 3):
            return PermissionCheckResult({
                "allowed": False,
                "reason": UNKNOWN_REJECTION_REASON,
                "tier": 99,
                "role": "UNKNOWN",
            })

        actor_role = ROLE_MAP.get(tier, "UNKNOWN")

        if actor_user_id is not None:
            uid_lookup = str(actor_user_id).strip()
            u = self.users.get(uid_lookup)
            if u is None:
                uid_low = uid_lookup.lower()
                u = next(
                    (cand for k, cand in self.users.items() if str(k).strip().lower() == uid_low),
                    None,
                )
            if u and not u.get("active", True) and tier != 1:
                return PermissionCheckResult({
                    "allowed": False,
                    "reason": f"Từ chối truy cập! Quyền của {u.get('name', uid_lookup)} đã bị hủy.",
                    "tier": 99,
                    "role": "UNKNOWN",
                })
        elif actor_tier is None:
            uid = (
                self._current_user_id
                if str(self._current_user_id).strip().lower() != "unknown"
                else USER_ROLE_MAP.get(tier, OWNER_ID)
            )
            u = self.users.get(uid) if uid else None
            if u and not u.get("active", True) and tier != 1:
                return PermissionCheckResult({
                    "allowed": False,
                    "reason": f"Từ chối truy cập! Quyền của {u.get('name', uid)} đã bị hủy.",
                    "tier": 99,
                    "role": "UNKNOWN",
                })

        canonical_id = DEVICE_ID_ALIASES.get(dev_id, dev_id)
        dev = self.devices.get(canonical_id, {})
        default_tier_map = {"ADMIN": 1, "MEMBER": 2, "CHILD_GUEST": 3}
        fallback_tier = default_tier_map.get(dev.get("min_role", "CHILD_GUEST"), 3)
        from simulator.auth.tier_permissions import enforce_fixed_policy, min_tier_for_device
        if isinstance(getattr(self, "system_policies", None), dict):
            enforce_fixed_policy(self.system_policies)
        min_tier = min_tier_for_device(canonical_id)


        if tier > min_tier:
            dname = dev.get("name", dev_id)
            return PermissionCheckResult({
                "allowed": False,
                "reason": f"Từ chối truy cập! Thiết bị {dname} chỉ cho phép từ Cấp {min_tier} trở lên điều khiển.",
                "tier": tier,
                "role": actor_role,
            })

        # Kiểm tra custom directives của Admin
        ok_dir, reason_dir = self._check_custom_directive_device_lock_parameterized(canonical_id, tier)
        if not ok_dir:
            return PermissionCheckResult({
                "allowed": False,
                "reason": reason_dir,
                "tier": tier,
                "role": actor_role,
            })

        req_role = ROLE_MAP.get(min_tier, dev.get("min_role", "CHILD_GUEST"))
        user_lvl = ROLE_LEVELS.get(actor_role, 0)
        req_lvl = ROLE_LEVELS.get(req_role, 3)
        if user_lvl < req_lvl:
            return PermissionCheckResult({
                "allowed": False,
                "reason": f"Từ chối truy cập! Cấp hiện tại (Tầng {tier}) không đủ quyền.",
                "tier": tier,
                "role": actor_role,
            })
        return PermissionCheckResult({
            "allowed": True,
            "reason": "OK",
            "tier": tier,
            "role": actor_role,
        })

    @staticmethod
    def _normalize_idempotent_action(action: str | None, target_state: Any = None) -> str:
        """Chuẩn hóa trạng thái đích tường minh (ON/OFF/OPEN/CLOSED/bool) về hành động lũy đẳng (idempotent)."""
        if target_state is not None and target_state != "":
            if isinstance(target_state, bool):
                return "open" if target_state else "close"
            st_up = str(target_state).strip().upper()
            if st_up in ("ON", "OPEN", "1", "TRUE", "TURN_ON"):
                return "open" if st_up == "OPEN" else "turn_on"
            if st_up in ("OFF", "CLOSED", "CLOSE", "0", "FALSE", "TURN_OFF"):
                return "close" if st_up in ("CLOSED", "CLOSE") else "turn_off"
        act_low = str(action or "open").strip().lower()
        if act_low in ("on", "turn_on", "true", "1"):
            return "turn_on"
        if act_low in ("off", "turn_off", "false", "0"):
            return "turn_off"
        if act_low in ("open",):
            return "open"
        if act_low in ("close", "closed"):
            return "close"
        return act_low or "open"

    def _is_in_active_mutation(self) -> bool:
        """Kiểm tra caller hiện tại có đang nằm trong giao dịch CAS/state của chính thread/task đó hay không."""
        root = getattr(self, "_root_engine", self)
        if root._mutation_depth <= 0:
            return False
        cur_tid = threading.get_ident()
        try:
            cur_task = asyncio.current_task()
            cur_task_id = id(cur_task) if cur_task is not None else None
        except RuntimeError:
            cur_task_id = None
        with root._cas_owner_lock:
            owner_tid = getattr(root, "_cas_owner_tid", None)
            owner_task_id = getattr(root, "_cas_owner_task_id", None)
        if owner_tid is None:
            return True
        if owner_tid != cur_tid:
            return False
        if owner_task_id is not None and cur_task_id is not None and owner_task_id != cur_task_id:
            return False
        return True

    async def _execute_with_cas_retry(self, op_factory: Any) -> dict[str, Any]:
        """Tuần tự hóa các thread/task cùng chia sẻ SmartHomeEngine trước khi chạy vòng lặp CAS."""
        root = getattr(self, "_root_engine", self)
        cur_tid = threading.get_ident()
        try:
            cur_task = asyncio.current_task()
            cur_task_id = id(cur_task) if cur_task is not None else None
        except RuntimeError:
            cur_task_id = None
        while True:
            with root._cas_owner_lock:
                if root._cas_owner_tid is None:
                    root._cas_owner_tid = cur_tid
                    root._cas_owner_task_id = cur_task_id
                    break
            await asyncio.sleep(0.001)
        try:
            return await self._execute_with_cas_retry_unlocked(op_factory)
        finally:
            with root._cas_owner_lock:
                if root._cas_owner_tid == cur_tid and root._cas_owner_task_id == cur_task_id:
                    root._cas_owner_tid = None
                    root._cas_owner_task_id = None

    async def _execute_with_cas_retry_unlocked(self, op_factory: Any) -> dict[str, Any]:
        """Thực thi chuyển đổi trạng thái dưới vòng lặp Compare-And-Swap, chỉ phát side-effects sau khi commit."""
        import secrets as _secrets

        root = getattr(self, "_root_engine", self)
        backend = root.state_backend
        last_result: dict[str, Any] = {"ok": False, "error": "CAS conflict"}
        for attempt in range(10):
            if getattr(backend, "__class__", None).__name__ == "SqliteStateBackend":
                shared, exp_rev, exp_tok = await asyncio.to_thread(backend.read_cas)
            else:
                shared, exp_rev, exp_tok = backend.read_cas()
            with root._state_sync_lock:
                if isinstance(shared, dict) and isinstance(shared.get("devices"), dict):
                    root._apply_shared_dict(shared, authoritative=True, dirty_ids=set())
                else:
                    root._last_synced_seq = 0
                    root._last_synced_ts_ns = 0
                if root is not self:
                    self.server_connected = root.server_connected
                    self.pump_manual_override_off = getattr(root, "pump_manual_override_off", False)
                    self._last_synced_seq = root._last_synced_seq
                    self._last_synced_ts_ns = root._last_synced_ts_ns

            emit_buf: list[dict[str, Any]] = []
            mqtt_buf: list[dict[str, Any]] = []
            root._dirty_device_ids.clear()
            root._state_dirty_in_tx = False
            prev_depth = root._mutation_depth
            root._mutation_depth = prev_depth + 1
            self._cas_emit_buffer = emit_buf
            self._cas_mqtt_buffer = mqtt_buf
            if root is not self:
                root._cas_emit_buffer = emit_buf
                root._cas_mqtt_buffer = mqtt_buf

            try:
                last_result = await op_factory()
            finally:
                self._cas_emit_buffer = None
                self._cas_mqtt_buffer = None
                if root is not self:
                    root._cas_emit_buffer = None
                    root._cas_mqtt_buffer = None
                root._mutation_depth = prev_depth

            if root is not self:
                root.server_connected = self.server_connected
                root.pump_manual_override_off = getattr(self, "pump_manual_override_off", False)

            needs_commit = bool(root._state_dirty_in_tx or root._dirty_device_ids)
            root._state_dirty_in_tx = False
            root._dirty_device_ids.clear()

            if needs_commit:
                payload = root._build_shared_state_payload()
                if getattr(backend, "__class__", None).__name__ == "SqliteStateBackend":
                    ok_cas, committed = await asyncio.to_thread(
                        backend.compare_and_swap,
                        payload,
                        expected_revision=exp_rev,
                        expected_token=exp_tok,
                    )
                else:
                    ok_cas, committed = backend.compare_and_swap(
                        payload,
                        expected_revision=exp_rev,
                        expected_token=exp_tok,
                    )
                if not ok_cas:
                    if isinstance(committed, dict) and isinstance(committed.get("devices"), dict):
                        with root._state_sync_lock:
                            root._apply_shared_dict(committed, authoritative=True, dirty_ids=set())
                    await asyncio.sleep(0.01 * (attempt + 1) + _secrets.randbelow(20) / 1000.0)
                    continue

                root._last_synced_seq = max(
                    root._last_synced_seq,
                    int((committed or {}).get("revision_seq", exp_rev + 1) or 0),
                )
                root._last_synced_ts_ns = max(
                    root._last_synced_ts_ns,
                    int((committed or {}).get("revision_ts_ns", root._last_synced_ts_ns) or 0),
                )
                if root is not self:
                    self._last_synced_seq = root._last_synced_seq
                    self._last_synced_ts_ns = root._last_synced_ts_ns
                if getattr(backend, "__class__", None).__name__ != "SqliteStateBackend":
                    try:
                        sync_engine_state_to_sqlite(root)
                    except Exception:
                        pass

            for ev in emit_buf:
                if ev.get("type") == "device_updated":
                    await self.emit(ev)

            for m_kw in mqtt_buf:
                await self.mqtt_bridge.publish_actuate_command(**m_kw)

            fresh_snap: dict[str, Any] | None = None
            if (isinstance(last_result, dict) and "snapshot" in last_result) or any(
                ev.get("type") == "state_snapshot" for ev in emit_buf
            ):
                fresh_snap = self.get_snapshot(sync=False)
                if isinstance(last_result, dict) and "snapshot" in last_result:
                    last_result["snapshot"] = fresh_snap
            if isinstance(last_result, dict):
                if "revision_seq" in last_result:
                    last_result["revision_seq"] = root._last_synced_seq
                if "revision_ts_ns" in last_result:
                    last_result["revision_ts_ns"] = root._last_synced_ts_ns

            for ev in emit_buf:
                if ev.get("type") == "device_updated":
                    continue
                if ev.get("type") == "state_snapshot" and fresh_snap is not None:
                    ev = {**ev, "snapshot": fresh_snap}
                await self.emit(ev)
            return last_result

    async def _commit_shared_state_mutation(
        self,
        mutate_fn: Callable[["SmartHomeEngine"], Any],
    ) -> Any:
        """Thực thi đột biến trạng thái mức engine (chế độ kết nối / reset) nguyên tử qua CAS."""
        import secrets as _secrets

        root = getattr(self, "_root_engine", self)
        backend = getattr(root, "state_backend", None)
        if not getattr(backend, "supports_cas", False):
            with root._state_sync_lock:
                root.sync_from_shared_store(force=True)
                if root is not self:
                    self.server_connected = root.server_connected
                    self.pump_manual_override_off = getattr(root, "pump_manual_override_off", False)
                res = mutate_fn(root)
                if root is not self:
                    self.server_connected = root.server_connected
                    self.pump_manual_override_off = getattr(root, "pump_manual_override_off", False)
                root.persist_to_shared_store()
                if root is not self:
                    self._last_synced_seq = root._last_synced_seq
                    self._last_synced_ts_ns = root._last_synced_ts_ns
                return res

        last_res: Any = None
        for attempt in range(12):
            conflict_sleep = False
            with root._state_sync_lock:
                cur, exp_rev, exp_tok = backend.read_cas()
                if isinstance(cur, dict) and isinstance(cur.get("devices"), dict):
                    root._apply_shared_dict(cur, authoritative=True, dirty_ids=set())
                last_res = mutate_fn(root)
                if root is not self:
                    self.server_connected = root.server_connected
                    self.pump_manual_override_off = getattr(root, "pump_manual_override_off", False)
                payload = root._build_shared_state_payload()
                try:
                    ok_cas, committed = backend.compare_and_swap(
                        payload,
                        expected_revision=exp_rev,
                        expected_token=exp_tok,
                    )
                except Exception as exc:
                    logger.warning("_commit_shared_state_mutation CAS error: %s", exc)
                    root.persist_to_shared_store()
                    if root is not self:
                        self._last_synced_seq = root._last_synced_seq
                        self._last_synced_ts_ns = root._last_synced_ts_ns
                    return last_res

                if ok_cas:
                    root._dirty_device_ids.clear()
                    root._last_synced_seq = max(
                        root._last_synced_seq,
                        int((committed or {}).get("revision_seq", exp_rev + 1) or 0),
                    )
                    root._last_synced_ts_ns = max(
                        root._last_synced_ts_ns,
                        int((committed or {}).get("revision_ts_ns", root._last_synced_ts_ns) or 0),
                    )
                    if root is not self:
                        self._last_synced_seq = root._last_synced_seq
                        self._last_synced_ts_ns = root._last_synced_ts_ns
                    try:
                        sync_engine_state_to_sqlite(root)
                    except Exception:
                        pass
                    return last_res

                if isinstance(committed, dict) and isinstance(committed.get("devices"), dict):
                    root._apply_shared_dict(committed, authoritative=True, dirty_ids=set())
                conflict_sleep = True
            if conflict_sleep:
                await asyncio.sleep(0.01 * (attempt + 1) + _secrets.randbelow(20) / 1000.0)

        root.persist_to_shared_store()
        if root is not self:
            self._last_synced_seq = root._last_synced_seq
            self._last_synced_ts_ns = root._last_synced_ts_ns
        return last_res

        raise RuntimeError("Concurrent CAS update conflict exceeded 10 retry attempts")

    async def execute_device_action(
        self,
        device_id: str,
        action: str = "",
        source: str = "voice",
        bypass_rbac: bool = False,
        trigger_chains: bool = True,
        request_tier: int | None = None,
        request_user_name: str | None = None,
        request_role: str | None = None,
        request_user_id: str | None = None,
        reason: str | None = None,
        target_state: Any = None,
        client_id: str | None = None,
        client_seq: int | None = None,
        client_ts_ms: int | None = None,
        request_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        root = getattr(self, "_root_engine", self)
        if getattr(root.state_backend, "supports_cas", False) and not root._is_in_active_mutation():
            return await self._execute_with_cas_retry(
                lambda: self._execute_device_action_once(
                    device_id=device_id,
                    action=action,
                    source=source,
                    bypass_rbac=bypass_rbac,
                    trigger_chains=trigger_chains,
                    request_tier=request_tier,
                    request_user_name=request_user_name,
                    request_role=request_role,
                    request_user_id=request_user_id,
                    reason=reason,
                    target_state=target_state,
                    client_id=client_id,
                    client_seq=client_seq,
                    client_ts_ms=client_ts_ms,
                    request_id=request_id,
                    **kwargs,
                )
            )
        return await self._execute_device_action_once(
            device_id=device_id,
            action=action,
            source=source,
            bypass_rbac=bypass_rbac,
            trigger_chains=trigger_chains,
            request_tier=request_tier,
            request_user_name=request_user_name,
            request_role=request_role,
            request_user_id=request_user_id,
            reason=reason,
            target_state=target_state,
            client_id=client_id,
            client_seq=client_seq,
            client_ts_ms=client_ts_ms,
            request_id=request_id,
            **kwargs,
        )

    def resolve_canonical_device_id(self, device_id: str) -> str:
        raw = str(device_id or "").strip().lower()
        return DEVICE_ID_ALIASES.get(raw, raw)

    def get_device_state_record(
        self,
        device_id: str,
        *,
        actor_tier: int | None = None,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Đọc trạng thái và thông số của một thiết bị, tôn trọng RBAC/pool theo tier."""
        cid = self.resolve_canonical_device_id(device_id)
        if cid not in self.devices:
            return {"ok": False, "error": f"Không tìm thấy thiết bị '{device_id}'.", "status_code": 404}
        tier = int(self.current_tier if actor_tier is None else actor_tier)
        allowed, reason = self.check_device_permission(cid, actor_tier=tier, actor_user_id=actor_user_id)
        if not allowed:
            return {
                "ok": False,
                "rbac_blocked": True,
                "status_code": 403,
                "device_id": cid,
                "error": "Xin lỗi, bạn không có quyền thực hiện lệnh này.",
                "exact_spoken_reply": "Xin lỗi, bạn không có quyền thực hiện lệnh này.",
            }
        dev = self.devices[cid]
        settings = dict(DEVICE_DEFAULT_SETTINGS.get(cid, {}))
        if isinstance(dev.get("settings"), dict):
            settings.update(dev["settings"])
        caps = DEVICE_CAPABILITIES.get(cid, {"actions": ("turn_on", "turn_off"), "params": {}})
        state_str = str(dev.get("state") or "OFF").upper()
        state_vi = {
            "ON": "đang bật",
            "OFF": "đang tắt",
            "OPEN": "đang mở",
            "CLOSED": "đang đóng",
        }.get(state_str, state_str.lower())
        return {
            "ok": True,
            "device_id": cid,
            "name": str(dev.get("name") or cid),
            "type": str(dev.get("type") or ""),
            "state": state_str,
            "state_vi": state_vi,
            "settings": settings,
            "capabilities": {
                "actions": list(caps.get("actions", ())),
                "params": {k: list(v) for k, v in (caps.get("params") or {}).items()},
            },
        }

    def list_accessible_devices(
        self,
        *,
        actor_tier: int | None = None,
        actor_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Liệt kê tất cả thiết bị thuộc pool quyền của người dùng hiện tại."""
        tier = int(self.current_tier if actor_tier is None else actor_tier)
        items: list[dict[str, Any]] = []
        for cid in self.devices:
            allowed, _ = self.check_device_permission(cid, actor_tier=tier, actor_user_id=actor_user_id)
            if not allowed:
                continue
            rec = self.get_device_state_record(cid, actor_tier=tier, actor_user_id=actor_user_id)
            if rec.get("ok"):
                items.append(rec)
        return items

    def read_all_sensors(self) -> dict[str, Any]:
        """Đọc toàn bộ thông số 3 cảm biến hiện có (DHT11 D2, Độ ẩm đất A0, KY-037 DO D5)."""
        dht = dict(getattr(self.mqtt_bridge, "dht11_telemetry", None) or {})
        soil = dict(getattr(self.mqtt_bridge, "soil_moisture_telemetry", None) or {})
        sound = dict(getattr(self.mqtt_bridge, "sound_telemetry", None) or {})
        temp_c = round(float(dht.get("temp_c", 28.5)), 1)
        hum_pct = round(float(dht.get("humidity_pct", 65.0)), 1)
        heat_idx = round(float(dht.get("heat_index_c", temp_c)), 1)
        soil_pct = round(float(soil.get("soil_moisture_pct", 62.0)), 1)
        soil_status = str(soil.get("status_label") or ("Đất khô" if soil_pct < 40.0 else "Đủ ẩm"))
        sound_detected = bool(sound.get("sound_detected", False))
        sound_status = str(sound.get("status_label") or ("Phát hiện tiếng động lớn / vỗ tay" if sound_detected else "Yên tĩnh"))
        return {
            "ok": True,
            "temperature_c": temp_c,
            "humidity_pct": hum_pct,
            "heat_index_c": heat_idx,
            "soil_moisture_pct": soil_pct,
            "soil_status": soil_status,
            "sound_detected": sound_detected,
            "sound_status": sound_status,
            "sound_event_count": int(sound.get("event_count", 0) or 0),
            "sound_last_event_at": float(sound.get("last_event_at", 0.0) or 0.0),
            "sound_pin": str(sound.get("sensor_pin") or "D5 (GPIO 14)"),
            "dht11": dht,
            "soil": soil,
            "sound": sound,
            "ky037": sound,
        }

    def validate_device_set_request(
        self,
        device_id: str,
        *,
        action: str | None = None,
        brightness_pct: Any = None,
        temperature_c: Any = None,
        fan_speed: Any = None,
        actor_tier: int | None = None,
        actor_user_id: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Kiểm tra chặt thiết bị, quyền RBAC và tham số cho set_device trước khi lưu nháp/thực thi."""
        cid = self.resolve_canonical_device_id(device_id)
        if cid not in self.devices:
            return False, {
                "ok": False,
                "status_code": 404,
                "error": f"Không tìm thấy thiết bị '{device_id}'.",
                "exact_spoken_reply": "Thiết bị bạn yêu cầu không có trong nhà thông minh.",
            }
        tier = int(self.current_tier if actor_tier is None else actor_tier)
        allowed, _reason = self.check_device_permission(cid, actor_tier=tier, actor_user_id=actor_user_id)
        if not allowed:
            return False, {
                "ok": False,
                "rbac_blocked": True,
                "status_code": 403,
                "device_id": cid,
                "error": "Xin lỗi, bạn không có quyền thực hiện lệnh này.",
                "exact_spoken_reply": "Xin lỗi, bạn không có quyền thực hiện lệnh này.",
            }

        caps = DEVICE_CAPABILITIES.get(cid, {"actions": ("turn_on", "turn_off"), "params": {}})
        allowed_params = caps.get("params") or {}
        norm_action = str(action or "").strip().lower()
        if norm_action == "on":
            norm_action = "open" if cid == "main_door" else "turn_on"
        elif norm_action == "off":
            norm_action = "close" if cid == "main_door" else "turn_off"
        elif norm_action in ("", "set", "set_value"):
            norm_action = ""

        valid_actions = {"open", "close", "turn_on", "turn_off"}
        if norm_action and norm_action not in valid_actions:
            return False, {
                "ok": False,
                "status_code": 400,
                "error": f"Hành động '{action}' không hợp lệ.",
                "exact_spoken_reply": "Yêu cầu điều khiển chưa đúng, bạn nói lại giúp mình nhé.",
            }
        if cid == "main_door" and norm_action in ("turn_on", "turn_off"):
            norm_action = "open" if norm_action == "turn_on" else "close"

        validated_params: dict[str, Any] = {}
        raw_params = {
            "brightness_pct": brightness_pct,
            "temperature_c": temperature_c,
            "fan_speed": fan_speed,
        }
        param_labels = {
            "brightness_pct": "độ sáng",
            "temperature_c": "nhiệt độ điều hòa",
            "fan_speed": "tốc độ quạt",
        }
        for pkey, pval in raw_params.items():
            if pval is None or pval == "":
                continue
            if pkey not in allowed_params:
                dev_name = str(self.devices[cid].get("name") or cid)
                return False, {
                    "ok": False,
                    "status_code": 400,
                    "error": f"{dev_name} không hỗ trợ chỉnh {param_labels[pkey]}.",
                    "exact_spoken_reply": f"{dev_name} không hỗ trợ chỉnh {param_labels[pkey]} ạ.",
                }
            lo, hi = allowed_params[pkey]
            try:
                num = int(round(float(pval)))
            except (TypeError, ValueError):
                return False, {
                    "ok": False,
                    "status_code": 400,
                    "error": f"Giá trị {param_labels[pkey]} không hợp lệ.",
                    "exact_spoken_reply": f"Giá trị {param_labels[pkey]} không hợp lệ ạ.",
                }
            if num < lo or num > hi:
                return False, {
                    "ok": False,
                    "status_code": 400,
                    "error": f"{param_labels[pkey].capitalize()} phải nằm trong khoảng từ {lo} đến {hi}.",
                    "exact_spoken_reply": f"{param_labels[pkey].capitalize()} chỉ chỉnh được từ {lo} đến {hi} ạ.",
                }
            validated_params[pkey] = num

        if not norm_action and not validated_params:
            return False, {
                "ok": False,
                "status_code": 400,
                "error": "Cần chọn hành động bật/tắt hoặc giá trị cần đặt cho thiết bị.",
                "exact_spoken_reply": "Bạn muốn bật, tắt hay đặt mức nào cho thiết bị này ạ?",
            }

        if not norm_action and validated_params:
            if "brightness_pct" in validated_params and validated_params["brightness_pct"] == 0:
                norm_action = "turn_off"
            else:
                norm_action = "open" if cid == "main_door" else "turn_on"

        return True, {
            "device_id": cid,
            "device_name": str(self.devices[cid].get("name") or cid),
            "action": norm_action,
            "params": validated_params,
        }

    async def set_device_parameters(
        self,
        device_id: str,
        *,
        action: str | None = None,
        brightness_pct: Any = None,
        temperature_c: Any = None,
        fan_speed: Any = None,
        source: str = "gemini_live",
        request_tier: int | None = None,
        request_role: str | None = None,
        request_user_name: str | None = None,
        request_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Thực thi bật/tắt/mở/đóng và cập nhật tham số thiết bị (độ sáng, nhiệt độ điều hòa, tốc độ quạt)."""
        ok_val, info = self.validate_device_set_request(
            device_id,
            action=action,
            brightness_pct=brightness_pct,
            temperature_c=temperature_c,
            fan_speed=fan_speed,
            actor_tier=request_tier,
            actor_user_id=request_user_id,
        )
        if not ok_val:
            return info

        cid = info["device_id"]
        norm_action = info["action"]
        params = info["params"]
        dev_name = info["device_name"]

        act_res = await self.execute_device_action(
            device_id=cid,
            action=norm_action,
            source=source,
            bypass_rbac=False,
            request_tier=request_tier,
            request_role=request_role,
            request_user_name=request_user_name,
            request_user_id=request_user_id,
            trigger_chains=True,
        )
        if isinstance(act_res, dict) and (not act_res.get("ok", True) or act_res.get("rbac_blocked")):
            return act_res

        with self.state_transaction():
            dev = self.devices[cid]
            cur_settings = dict(DEVICE_DEFAULT_SETTINGS.get(cid, {}))
            if isinstance(dev.get("settings"), dict):
                cur_settings.update(dev["settings"])
            cur_settings.update(params)
            dev["settings"] = cur_settings

        detail_parts: list[str] = []
        if "brightness_pct" in params:
            detail_parts.append(f"độ sáng {params['brightness_pct']}%")
        verb_vi = {
            "open": "Đã mở",
            "close": "Đã đóng",
            "turn_on": "Đã bật",
            "turn_off": "Đã tắt",
        }.get(norm_action, "Đã cập nhật")
        if detail_parts:
            spoken = f"{verb_vi} {dev_name.lower()} ({', '.join(detail_parts)})."
        else:
            spoken = f"{verb_vi} {dev_name.lower()}."
        return {
            "ok": True,
            "device_id": cid,
            "device_name": dev_name,
            "state": self.devices[cid]["state"],
            "settings": dict(self.devices[cid].get("settings") or {}),
            "exact_spoken_reply": spoken,
            "reply": spoken,
            "snapshot": self.get_snapshot(sync=False),
        }

    async def _execute_device_action_once(
        self,
        device_id: str,
        action: str = "",
        source: str = "voice",
        bypass_rbac: bool = False,
        trigger_chains: bool = True,
        request_tier: int | None = None,
        request_user_name: str | None = None,
        request_role: str | None = None,
        request_user_id: str | None = None,
        reason: str | None = None,
        target_state: Any = None,
        client_id: str | None = None,
        client_seq: int | None = None,
        client_ts_ms: int | None = None,
        request_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if reason and source == "voice":
            source = str(reason)
        if target_state is None:
            for k in ("state", "desired_state", "targetState", "desiredState"):
                if k in kwargs and kwargs[k] is not None and kwargs[k] != "":
                    target_state = kwargs[k]
                    break
        action = self._normalize_idempotent_action(action, target_state)

        raw_cid = client_id
        if raw_cid is None:
            for k in ("clientId", "client_token"):
                if k in kwargs and kwargs[k] is not None:
                    raw_cid = kwargs[k]
                    break
        req_client_id = str(raw_cid).strip()[:96] if raw_cid is not None and str(raw_cid).strip() else ""

        raw_req_id = request_id
        if raw_req_id is None:
            for k in ("requestId", "req_id"):
                if k in kwargs and kwargs[k] is not None:
                    raw_req_id = kwargs[k]
                    break
        req_id = str(raw_req_id).strip()[:128] if raw_req_id is not None and str(raw_req_id).strip() else ""

        raw_seq = client_seq
        if raw_seq is None:
            for k in ("seq", "request_seq", "clientSeq"):
                if k in kwargs and kwargs[k] is not None:
                    raw_seq = kwargs[k]
                    break
        try:
            req_seq = max(0, int(raw_seq)) if raw_seq is not None else 0
        except (TypeError, ValueError):
            req_seq = 0

        raw_ts = client_ts_ms
        if raw_ts is None:
            for k in ("timestamp", "client_ts", "clientTsMs"):
                if k in kwargs and kwargs[k] is not None:
                    raw_ts = kwargs[k]
                    break
        try:
            req_ts_ms = max(0, int(float(raw_ts))) if raw_ts is not None else 0
        except (TypeError, ValueError):
            req_ts_ms = 0

        if not bypass_rbac:
            if request_tier is None and request_role is None:
                is_unknown_caller = (
                    self._current_role == "UNKNOWN"
                    or str(self._current_user_id).strip().lower() in ("", "unknown", "stranger")
                    or self.current_tier not in (1, 2, 3)
                )
            else:
                is_unknown_caller = (
                    (request_role is not None and str(request_role).strip().upper() == "UNKNOWN")
                    or (request_tier is not None and int(request_tier) not in (1, 2, 3))
                    or (request_user_name is not None and str(request_user_name).strip().lower() in ("unknown", "stranger"))
                )
            if is_unknown_caller:
                canonical_dev = DEVICE_ID_ALIASES.get(device_id, device_id)
                await self.emit({
                    "type": "rbac_blocked",
                    "device_id": device_id,
                    "device_name": self.devices.get(canonical_dev, {}).get("name", device_id),
                    "action": action,
                    "role": "UNKNOWN",
                    "reason": UNKNOWN_REJECTION_REASON,
                })
                return {
                    "ok": False,
                    "rbac_blocked": True,
                    "device_id": device_id,
                    "tier": 99,
                    "role": "UNKNOWN",
                    "error": UNKNOWN_REJECTION_REASON,
                    "message": "Xin lỗi, bạn không có quyền thực hiện lệnh này.",
                    "rejection_speech": "Xin lỗi, bạn không có quyền thực hiện lệnh này.",
                    "exact_spoken_reply": "Xin lỗi, bạn không có quyền thực hiện lệnh này.",
                }

        with self.state_transaction():
            targets = self._expand_targets(device_id, action)
            results = []
            for dev_id, act in targets:
                if dev_id not in self.devices:
                    results.append({"ok": False, "device_id": dev_id, "error": f"Thiết bị '{dev_id}' không tồn tại."})
                    continue
                dev = self.devices[dev_id]

                effective_tier = int(request_tier) if request_tier is not None else int(self.current_tier)
                effective_user = request_user_name or self.get_current_user_name()
                effective_role = request_role or ROLE_MAP.get(effective_tier, self.current_role)

                if not bypass_rbac:
                    allowed, reason = self.check_device_permission(
                        dev_id,
                        action=act,
                        actor_tier=effective_tier,
                        actor_user_id=request_user_id,
                    )
                    if not allowed:
                        await self.emit({
                            "type": "rbac_blocked",
                            "device_id": dev_id,
                            "device_name": dev["name"],
                            "action": act,
                            "role": effective_role,
                            "reason": reason,
                        })
                        results.append({"ok": False, "rbac_blocked": True, "device_id": dev_id, "error": reason})
                        continue

                if not self.server_connected:
                    if dev_id == "main_door" and act in ("open", "turn_on"):
                        lock_reason = (
                            "🔒 [KHÓA AN NINH OFFLINE]: Mạch không kết nối Server xác thực giọng nói -> "
                            "Cửa chính bị khóa cứng, không ai được phép mở cửa khi mất kết nối Server!"
                        )
                        await self.emit({
                            "type": "rbac_blocked",
                            "device_id": dev_id,
                            "device_name": dev["name"],
                            "action": act,
                            "role": "OFFLINE_DEFAULT",
                            "reason": lock_reason,
                        })
                        results.append({"ok": False, "device_id": dev_id, "error": lock_reason})
                        continue
                    if dev_id == "alarm_siren":
                        lock_reason = (
                            "🔒 [KHÓA AN NINH OFFLINE]: Mạch không kết nối Server xác thực -> "
                            "Còi báo động bị khóa bảo vệ, chỉ cho phép điều khiển Đèn, Máy bơm, Nguồn mạch loa PAM8403!"
                        )
                        await self.emit({
                            "type": "rbac_blocked",
                            "device_id": dev_id,
                            "device_name": dev["name"],
                            "action": act,
                            "role": "OFFLINE_DEFAULT",
                            "reason": lock_reason,
                        })
                        results.append({"ok": False, "device_id": dev_id, "error": lock_reason})
                        continue

                if dev["type"] == "door":
                    new_state = "OPEN" if act in ("open", "turn_on", "on") else "CLOSED"
                else:
                    new_state = "ON" if act in ("open", "turn_on", "on") else "OFF"

                prev_global_seq = int(dev.get("last_client_seq", 0) or 0)
                prev_global_ts = int(dev.get("last_client_ts_ms", 0) or 0)
                prev_global_cid = str(dev.get("last_client_id", "") or "")
                client_seqs_map: dict[str, dict[str, Any]] = (
                    dict(dev.get("client_seqs")) if isinstance(dev.get("client_seqs"), dict) else {}
                )
                cid_key = req_client_id if req_client_id else "__anon__"
                c_rec = client_seqs_map.get(cid_key)
                if not isinstance(c_rec, dict):
                    if cid_key == "__anon__" and not prev_global_cid and (prev_global_seq > 0 or prev_global_ts > 0):
                        c_rec = {
                            "seq": prev_global_seq,
                            "ts_ms": prev_global_ts,
                            "state": str(dev.get("last_requested_state", dev.get("state", ""))),
                            "req_id": str(dev.get("last_request_id", "")),
                        }
                    else:
                        c_rec = {"seq": 0, "ts_ms": 0, "state": "", "req_id": ""}

                c_prev_seq = int(c_rec.get("seq", 0) or 0)
                c_prev_ts = int(c_rec.get("ts_ms", 0) or 0)
                c_prev_state = str(c_rec.get("state", "") or "")
                c_prev_req_id = str(c_rec.get("req_id", "") or "")

                is_stale_or_conflict = False
                if req_seq > 0 or req_ts_ms > 0 or (cid_key != "__anon__" and c_prev_seq > 0):
                    if cid_key != "__anon__":
                        if req_seq > 0 or c_prev_seq > 0:
                            if req_seq < c_prev_seq:
                                is_stale_or_conflict = True
                            elif req_seq == c_prev_seq and c_prev_seq > 0:
                                if (
                                    (req_ts_ms > 0 and c_prev_ts > 0 and req_ts_ms < c_prev_ts)
                                    or (c_prev_state and new_state != c_prev_state)
                                    or (req_id and c_prev_req_id and req_id != c_prev_req_id and new_state != c_prev_state)
                                ):
                                    is_stale_or_conflict = True
                        same_active_client_advancing_seq = (
                            bool(prev_global_cid)
                            and req_client_id == prev_global_cid
                            and req_seq > 0
                            and req_seq > c_prev_seq
                        )
                        if (
                            not is_stale_or_conflict
                            and not same_active_client_advancing_seq
                            and req_ts_ms > 0
                            and prev_global_ts > 0
                            and req_ts_ms < prev_global_ts
                        ):
                            is_stale_or_conflict = True
                    else:
                        if req_ts_ms > 0 and prev_global_ts > 0 and req_ts_ms < prev_global_ts:
                            is_stale_or_conflict = True
                        elif req_seq > 0:
                            is_anon_epoch_reset = (
                                req_seq == 1
                                and req_ts_ms > 0
                                and req_ts_ms > max(c_prev_ts, prev_global_ts)
                            )
                            if not is_anon_epoch_reset:
                                if req_seq < c_prev_seq:
                                    is_stale_or_conflict = True
                                elif req_seq == c_prev_seq and c_prev_seq > 0:
                                    if (
                                        (req_ts_ms > 0 and c_prev_ts > 0 and req_ts_ms < c_prev_ts)
                                        or (c_prev_state and new_state != c_prev_state)
                                        or (req_id and c_prev_req_id and req_id != c_prev_req_id and new_state != c_prev_state)
                                    ):
                                        is_stale_or_conflict = True

                if is_stale_or_conflict:
                    results.append({
                        "ok": True,
                        "device_id": dev_id,
                        "device_name": dev["name"],
                        "state": dev["state"],
                        "already_in_state": True,
                        "stale_ignored": True,
                        "version": int(dev.get("version", 1) or 1),
                        "last_client_seq": prev_global_seq,
                        "last_client_id": prev_global_cid,
                    })
                    continue

                if req_seq > 0 or req_ts_ms > 0:
                    if req_seq > 0:
                        dev["last_client_seq"] = req_seq
                        dev["last_client_id"] = req_client_id
                        dev["last_request_id"] = req_id
                    dev["last_requested_state"] = new_state
                    if req_ts_ms > 0:
                        dev["last_client_ts_ms"] = max(prev_global_ts, req_ts_ms)
                    client_seqs_map[cid_key] = {
                        "seq": req_seq if req_seq > 0 else c_prev_seq,
                        "ts_ms": max(c_prev_ts, req_ts_ms) if req_ts_ms > 0 else c_prev_ts,
                        "state": new_state,
                        "req_id": req_id,
                    }
                    if len(client_seqs_map) > 128:
                        oldest_keys = sorted(
                            client_seqs_map.keys(),
                            key=lambda k: int((client_seqs_map[k] or {}).get("ts_ms", 0) or 0),
                        )[: len(client_seqs_map) - 128]
                        for ok_del in oldest_keys:
                            client_seqs_map.pop(ok_del, None)
                    dev["client_seqs"] = client_seqs_map
                    self._state_dirty_in_tx = True

                if dev_id == "garden_pump" and not str(source).startswith("Cảm biến đất"):
                    prev_override = getattr(self, "pump_manual_override_off", False)
                    self.pump_manual_override_off = (new_state == "OFF")
                    if prev_override != self.pump_manual_override_off:
                        self._state_dirty_in_tx = True

                old_state = dev["state"]
                if old_state == new_state:
                    if self._last_synced_seq == 0:
                        self._state_dirty_in_tx = True
                    already_msg = f"{dev['name']} {self._state_verb_vi(dev['type'], new_state, already=True)}."
                    await self.emit({
                        "type": "device_already_in_state",
                        "device_id": dev_id,
                        "device_name": dev["name"],
                        "state": new_state,
                        "message": already_msg,
                    })
                    results.append({
                        "ok": True,
                        "device_id": dev_id,
                        "device_name": dev["name"],
                        "state": new_state,
                        "already_in_state": True,
                        "version": int(dev.get("version", 1) or 1),
                        "last_client_seq": int(dev.get("last_client_seq", 0) or 0),
                        "last_client_id": str(dev.get("last_client_id", "") or ""),
                    })
                    continue

                prev_ver = int(dev.get("version", 1) or 1)
                prev_updated_at = float(dev.get("updated_at", 0.0) or 0.0)
                dev["state"] = new_state
                dev["updated_at"] = max(time.time(), prev_updated_at + 1e-6)
                dev["version"] = max(int(dev.get("version", 1) or 1), prev_ver + 1)
                self._state_dirty_in_tx = True

                mqtt_args = {
                    "device_id": dev_id,
                    "state": new_state,
                    "action": act,
                    "source": source,
                    "user_name": effective_user,
                    "tier": effective_tier,
                }
                mqtt_buf = getattr(self, "_cas_mqtt_buffer", None)
                if mqtt_buf is not None:
                    mqtt_buf.append(mqtt_args)
                else:
                    await self.mqtt_bridge.publish_actuate_command(**mqtt_args)

                await self.emit({
                    "type": "device_updated",
                    "device_id": dev_id,
                    "device_name": dev["name"],
                    "gpio": dev["gpio"],
                    "old_state": old_state,
                    "new_state": new_state,
                    "source": source,
                    "timestamp": dev["updated_at"],
                    "version": int(dev["version"]),
                    "last_client_seq": int(dev.get("last_client_seq", 0) or 0),
                    "last_client_id": str(dev.get("last_client_id", "") or ""),
                })

                results.append({
                    "ok": True,
                    "device_id": dev_id,
                    "device_name": dev["name"],
                    "state": new_state,
                    "already_in_state": False,
                    "version": int(dev["version"]),
                    "last_client_seq": int(dev.get("last_client_seq", 0) or 0),
                    "last_client_id": str(dev.get("last_client_id", "") or ""),
                })

                if trigger_chains and self.server_connected:
                    triggered_fx = await self._evaluate_reactive_if_else(dev_id, new_state)
                    results.extend(triggered_fx)
                    try:
                        from simulator.automation_engine import evaluate_compound_rules

                        comp_fx = await evaluate_compound_rules(self, trigger_source=f"device:{dev_id}")
                        if comp_fx:
                            results.extend(comp_fx)
                    except Exception:
                        pass

        defer_voice_snap = (
            source == "session_voice"
            and "pytest" not in sys.modules
            and not os.environ.get("PYTEST_CURRENT_TEST")
        )
        snap: dict[str, Any] | None = None
        if defer_voice_snap:
            async def _bg_emit_voice_snapshot() -> None:
                try:
                    await asyncio.sleep(0)
                    await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot(sync=False)})
                except Exception:
                    pass

            bg_task = asyncio.create_task(_bg_emit_voice_snapshot())
            _PENDING_AUDIT_TASKS.add(bg_task)
            bg_task.add_done_callback(_discard_audit_task)
        else:
            snap = {} if getattr(self, "_cas_emit_buffer", None) is not None else self.get_snapshot(sync=False)
            await self.emit({"type": "state_snapshot", "snapshot": snap})
        all_ok = all(r["ok"] for r in results) if results else False
        any_rbac_blocked = any(bool(r.get("rbac_blocked")) for r in results)
        concise_reply = (
            "Xin lỗi, bạn không có quyền thực hiện lệnh này."
            if any_rbac_blocked and not all_ok
            else self._build_concise_spoken_reply(results)
        )
        primary_res = results[0] if results else {}
        out_res: dict[str, Any] = {
            "ok": all_ok,
            "rbac_blocked": any_rbac_blocked and not all_ok,
            "device_id": primary_res.get("device_id", DEVICE_ID_ALIASES.get(device_id, device_id)),
            "state": primary_res.get("state"),
            "device_version": primary_res.get("version"),
            "client_id": req_client_id if req_client_id else None,
            "client_seq": req_seq if req_seq > 0 else None,
            "request_id": req_id if req_id else None,
            "stale_ignored": bool(primary_res.get("stale_ignored", False)),
            "revision_seq": int(self._last_synced_seq),
            "revision_ts_ns": int(self._last_synced_ts_ns),
            "results": results,
            "message": concise_reply,
            "exact_spoken_reply": concise_reply,
            "instruction_for_ai": f"BẮT BUỘC trả lời CỰC NGẮN GỌN đúng nguyên văn câu này: '{concise_reply}'",
            "summary": concise_reply,
        }
        if not defer_voice_snap:
            out_res["snapshot"] = snap
        if any_rbac_blocked and not all_ok:
            out_res["error"] = concise_reply
            out_res["rejection_speech"] = concise_reply
        return out_res

    async def sync_edge_flash(self) -> dict[str, Any]:
        """Đồng bộ bản sao 2 Bể (Bể 1 Hẹn giờ & Bể 2 Luật IF-ELSE) xuống Flash LittleFS của ESP8266."""
        snap = self.get_snapshot()
        combined_rules = list(snap.get("t1_global_if_else_rules", []))
        if self._current_user_id != OWNER_ID:
            combined_rules.extend(snap.get("if_else_rules", []))
        return await self.mqtt_bridge.sync_pools_to_esp8266_flash(
            timers=snap.get("timers", []),
            if_else_rules=combined_rules,
            system_policies=self.system_policies,
        )

    async def update_sensor_telemetry(self, temp_c: Any, humidity_pct: Any, wifi_rssi_dbm: Any = -52) -> dict[str, Any]:
        """Cập nhật thông số cảm biến DHT11 từ mạch ESP8266 và tự động kiểm tra luật ngưỡng nhiệt độ/độ ẩm."""
        root = getattr(self, "_root_engine", self)
        if getattr(root.state_backend, "supports_cas", False) and not root._is_in_active_mutation():
            return await self._execute_with_cas_retry(
                lambda: self._update_sensor_telemetry_once(temp_c, humidity_pct, wifi_rssi_dbm)
            )
        return await self._update_sensor_telemetry_once(temp_c, humidity_pct, wifi_rssi_dbm)

    async def _update_sensor_telemetry_once(self, temp_c: Any, humidity_pct: Any, wifi_rssi_dbm: Any = -52) -> dict[str, Any]:
        """Cập nhật thông số cảm biến DHT11 từ mạch ESP8266 và tự động kiểm tra luật ngưỡng nhiệt độ/độ ẩm."""
        with self.state_transaction():
            pkt = await self.mqtt_bridge.update_dht11_telemetry(temp_c, humidity_pct, wifi_rssi_dbm)
            self._state_dirty_in_tx = True
            t_clamped = float(self.mqtt_bridge.dht11_telemetry["temp_c"])
            h_clamped = float(self.mqtt_bridge.dht11_telemetry["humidity_pct"])
            triggered: list[dict[str, Any]] = []
            temp_hits = await self._evaluate_numeric_sensor_rules("temp_sensor", t_clamped)
            if temp_hits:
                triggered.extend(temp_hits)
            hum_hits = await self._evaluate_numeric_sensor_rules("humidity_sensor", h_clamped)
            if hum_hits:
                triggered.extend(hum_hits)
            try:
                from simulator.automation_engine import evaluate_compound_rules

                comp_hits = await evaluate_compound_rules(self, trigger_source="sensor:dht11")
                if comp_hits:
                    triggered.extend(comp_hits)
            except Exception:
                pass
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        spoken = f"Nhiệt độ phòng là {t_clamped:.1f} độ C, độ ẩm {h_clamped:.0f}%."
        return {
            "ok": True,
            "telemetry": self.mqtt_bridge.dht11_telemetry,
            "mqtt_packet": pkt,
            "triggered_actions": triggered,
            "exact_spoken_reply": spoken,
        }

    async def update_soil_moisture_telemetry(
        self,
        soil_moisture_pct: Any,
        auto_pump_below_pct: float = 40.0,
        auto_stop_above_pct: float = 70.0,
    ) -> dict[str, Any]:
        """Cập nhật thông số cảm biến Độ ẩm Đất (Chân A0) và tự động điều khiển Máy bơm tưới cây (Chân D6)."""
        root = getattr(self, "_root_engine", self)
        if getattr(root.state_backend, "supports_cas", False) and not root._is_in_active_mutation():
            return await self._execute_with_cas_retry(
                lambda: self._update_soil_moisture_telemetry_once(
                    soil_moisture_pct,
                    auto_pump_below_pct=auto_pump_below_pct,
                    auto_stop_above_pct=auto_stop_above_pct,
                )
            )
        return await self._update_soil_moisture_telemetry_once(
            soil_moisture_pct,
            auto_pump_below_pct=auto_pump_below_pct,
            auto_stop_above_pct=auto_stop_above_pct,
        )

    async def _update_soil_moisture_telemetry_once(
        self,
        soil_moisture_pct: Any,
        auto_pump_below_pct: float = 40.0,
        auto_stop_above_pct: float = 70.0,
    ) -> dict[str, Any]:
        """Cập nhật thông số cảm biến Độ ẩm Đất (Chân A0) và tự động điều khiển Máy bơm tưới cây (Chân D6)."""
        with self.state_transaction():
            pkt = await self.mqtt_bridge.update_soil_moisture_telemetry(soil_moisture_pct)
            self._state_dirty_in_tx = True
            pct = float(self.mqtt_bridge.soil_moisture_telemetry["soil_moisture_pct"])
            triggered: list[dict[str, Any]] = []
            auto_action = "NONE"
            if pct >= float(auto_pump_below_pct):
                self.pump_manual_override_off = False
            if pct < float(auto_pump_below_pct):
                if getattr(self, "pump_manual_override_off", False) and self.devices.get("garden_pump", {}).get("state") == "OFF":
                    auto_action = "MANUAL_OVERRIDE_KEEP_OFF"
                    spoken = f"Độ ẩm đất đang thấp ({pct:.0f}%), nhưng máy bơm đang giữ trạng thái tắt do người dùng vừa tắt tay."
                else:
                    res = await self.execute_device_action(
                        "garden_pump",
                        "turn_on",
                        source=f"Cảm biến đất YL-69 A0 ({pct:.0f}% < {auto_pump_below_pct:.0f}%)",
                        bypass_rbac=True,
                    )
                    triggered.extend(res.get("results", []))
                    auto_action = "AUTO_PUMP_ON"
                    spoken = f"Độ ẩm đất đang thấp ({pct:.0f}%), máy bơm tưới cây đã tự động bật."
            elif pct >= float(auto_stop_above_pct) and self.devices.get("garden_pump", {}).get("state") == "ON":
                res = await self.execute_device_action(
                    "garden_pump",
                    "turn_off",
                    source=f"Cảm biến đất YL-69 A0 ({pct:.0f}% >= {auto_stop_above_pct:.0f}%)",
                    bypass_rbac=True,
                )
                triggered.extend(res.get("results", []))
                auto_action = "AUTO_PUMP_OFF"
                spoken = f"Độ ẩm đất đã đủ ({pct:.0f}%), máy bơm tưới cây đã tự động tắt."
            else:
                spoken = f"Độ ẩm đất hiện tại là {pct:.0f}%."
            soil_rule_hits = await self._evaluate_numeric_sensor_rules("soil_sensor", pct)
            if soil_rule_hits:
                triggered.extend(soil_rule_hits)
            try:
                from simulator.automation_engine import evaluate_compound_rules

                comp_soil_hits = await evaluate_compound_rules(self, trigger_source="sensor:soil")
                if comp_soil_hits:
                    triggered.extend(comp_soil_hits)
            except Exception:
                pass
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "auto_action": auto_action,
            "pump_manual_override_off": bool(getattr(self, "pump_manual_override_off", False)),
            "telemetry": self.mqtt_bridge.soil_moisture_telemetry,
            "mqtt_packet": pkt,
            "triggered_actions": triggered,
            "exact_spoken_reply": spoken,
        }

    async def update_sound_telemetry(
        self,
        sound_detected: Any = False,
        do_state: Any = None,
        note: str = "",
    ) -> dict[str, Any]:
        """Cập nhật thông số cảm biến Âm thanh KY-037/038 (Chân D5 / GPIO14 DO)."""
        root = getattr(self, "_root_engine", self)
        if getattr(root.state_backend, "supports_cas", False) and not root._is_in_active_mutation():
            return await self._execute_with_cas_retry(
                lambda: self._update_sound_telemetry_once(
                    sound_detected=sound_detected,
                    do_state=do_state,
                    note=note,
                )
            )
        return await self._update_sound_telemetry_once(
            sound_detected=sound_detected,
            do_state=do_state,
            note=note,
        )

    async def _update_sound_telemetry_once(
        self,
        sound_detected: Any = False,
        do_state: Any = None,
        note: str = "",
    ) -> dict[str, Any]:
        with self.state_transaction():
            pkt = await self.mqtt_bridge.update_sound_telemetry(
                sound_detected=sound_detected,
                do_state=do_state,
                note=note,
            )
            self._state_dirty_in_tx = True
            snd = dict(self.mqtt_bridge.sound_telemetry)
            is_loud = bool(snd.get("sound_detected", False))
            triggered_rules = await self._evaluate_reactive_if_else(
                "sound_sensor",
                "LOUD" if is_loud else "QUIET",
            )
            try:
                from simulator.automation_engine import evaluate_compound_rules

                comp_sound_hits = await evaluate_compound_rules(self, trigger_source="sensor:sound")
                if comp_sound_hits:
                    triggered_rules.extend(comp_sound_hits)
            except Exception:
                pass
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        spoken = (
            f"Cảm biến âm thanh KY-037 trên chân D5 phát hiện tiếng động lớn (tổng {snd.get('event_count', 0)} lần)."
            if is_loud
            else "Cảm biến âm thanh KY-037 trên chân D5 hiện đang yên tĩnh."
        )
        return {
            "ok": True,
            "telemetry": snd,
            "mqtt_packet": pkt,
            "triggered_actions": triggered_rules,
            "exact_spoken_reply": spoken,
        }

    async def set_house_mode(
        self,
        mode: str,
        *,
        source: str = "user",
        actor_name: str = "",
        actor_tier: int = 1,
    ) -> dict[str, Any]:
        """Chuyển trạng thái hiện diện ngôi nhà giữa Ở nhà (HOME) và Vắng nhà (AWAY) và đánh giá luật phức hợp."""
        norm_mode = str(mode or "HOME").strip().upper()
        if norm_mode not in ("HOME", "AWAY"):
            return {"ok": False, "error": "Chế độ nhà chỉ hỗ trợ HOME hoặc AWAY."}
        root = getattr(self, "_root_engine", self)
        old_mode = str(getattr(root, "house_mode", "HOME") or "HOME").upper()
        root.house_mode = norm_mode
        self.house_mode = norm_mode
        self.persist_to_shared_store()
        triggered: list[dict[str, Any]] = []
        try:
            from simulator.automation_engine import evaluate_compound_rules

            triggered = await evaluate_compound_rules(self, trigger_source=f"house_mode:{norm_mode}")
        except Exception:
            triggered = []
        mode_vi = "Vắng nhà" if norm_mode == "AWAY" else "Ở nhà"
        spoken = f"Đã chuyển sang chế độ {mode_vi}."
        append_audit_log(
            "AUTOMATION",
            "house_mode_changed",
            f"Đổi chế độ nhà {old_mode} -> {norm_mode} ({mode_vi})",
            user_name=actor_name or self.get_current_user_name(),
            tier=int(actor_tier or self.current_tier),
            details={"old_mode": old_mode, "house_mode": norm_mode, "source": source},
        )
        await self.emit(
            {
                "type": "house_mode_changed",
                "old_mode": old_mode,
                "house_mode": norm_mode,
                "message": spoken,
                "source": source,
            }
        )
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot(sync=False)})
        return {
            "ok": True,
            "house_mode": norm_mode,
            "mode_vi": mode_vi,
            "triggered_actions": triggered,
            "reply": spoken,
            "exact_spoken_reply": spoken,
        }

    async def _evaluate_numeric_sensor_rules(self, sensor_id: str, sensor_value: float) -> list[dict[str, Any]]:
        """Evaluate persisted sensor-trigger rules using each rule's own numeric threshold/operator (or qualitative spec)."""
        from simulator.auth.tier_permissions import can_control_device
        from simulator.automation_engine import QUALITATIVE_SENSOR_THRESHOLDS
        from simulator.automation_repo import SENSOR_TRIGGER_DEVICES, get_automation_snapshot_bundle

        def _cmp(val: float, op: str, thresh: float) -> bool:
            if op == ">":
                return val > thresh
            if op == ">=":
                return val >= thresh
            if op == "<":
                return val < thresh
            if op == "<=":
                return val <= thresh
            if op == "==":
                return abs(val - thresh) <= 1e-6
            if op == "!=":
                return abs(val - thresh) > 1e-6
            return False

        triggered_results: list[dict[str, Any]] = []
        t1_locked_targets: set[str] = set()
        source_name = str(SENSOR_TRIGGER_DEVICES.get(sensor_id, {}).get("name") or sensor_id)

        try:
            _, rules_cached, _ = get_automation_snapshot_bundle()
            db_rules = sorted(rules_cached, key=lambda r: int(r.get("owner_tier") or 1))
        except Exception:
            db_rules = []

        for rule in db_rules:
            if rule.get("when_device_id") != sensor_id:
                continue
            rule_tier = int(rule.get("owner_tier") or 1)
            if rule_tier >= 3:
                continue
            if_state = str(rule.get("when_state") or "").upper()
            op = str(rule.get("threshold_op") or "").strip()
            thresh_raw = rule.get("threshold_value")
            if op and thresh_raw is not None:
                matched = _cmp(sensor_value, op, float(thresh_raw))
            else:
                q_spec = QUALITATIVE_SENSOR_THRESHOLDS.get(sensor_id, {}).get(if_state)
                if q_spec is None:
                    continue
                q_op, q_val = q_spec
                matched = _cmp(sensor_value, q_op, float(q_val))

            delay_sec = float(rule.get("delay_seconds") or 0.0)
            if matched:
                target_dev = str(rule.get("then_device_id") or "")
                target_act = str(rule.get("then_action") or "")
                prefix_lbl = "IF"
            else:
                target_dev = str(rule.get("else_device_id") or "")
                target_act = str(rule.get("else_action") or "")
                prefix_lbl = "ELSE"

            if not target_dev or not target_act or target_dev == sensor_id:
                continue
            if not can_control_device(rule_tier, target_dev):
                continue
            if rule_tier > 1 and target_dev in t1_locked_targets:
                continue
            if rule_tier == 1:
                t1_locked_targets.add(target_dev)

            reason_lbl = f"{prefix_lbl} {source_name}={sensor_value:.1f}"
            if delay_sec <= 0.2:
                res = await self.execute_device_action(
                    device_id=target_dev,
                    action=target_act,
                    source=reason_lbl,
                    bypass_rbac=True,
                    trigger_chains=False,
                )
                triggered_results.extend(res.get("results", []))
            else:
                await self.schedule_action(
                    device_id=target_dev,
                    action=target_act,
                    delay_seconds=delay_sec,
                    reason=reason_lbl,
                    bypass_rbac=True,
                    trigger_chains=False,
                )
        return triggered_results

    async def _evaluate_reactive_if_else(self, changed_dev_id: str, new_state: str) -> list[dict[str, Any]]:
        """Kiểm tra luật IF khi `changed_dev_id` chuyển sang `new_state`."""
        from simulator.automation_repo import SENSOR_STATE_OPPOSITE, SENSOR_TRIGGER_DEVICES

        triggered_results: list[dict[str, Any]] = []
        t1_locked_targets: set[str] = set()
        source_name = (
            str(self.devices[changed_dev_id]["name"])
            if changed_dev_id in self.devices
            else str(SENSOR_TRIGGER_DEVICES.get(changed_dev_id, {}).get("name") or changed_dev_id)
        )

        t1_rules = list(self._get_user_pool(OWNER_ID).get("if_else_rules", []))
        rule_batches: list[tuple[int, list[dict[str, Any]]]] = [(1, t1_rules)]
        if self.current_tier == 2 and self._current_user_id != OWNER_ID:
            t2_rules = list(self._get_user_pool(self._current_user_id).get("if_else_rules", []))
            rule_batches.append((2, t2_rules))

        for batch_tier, rules_list in rule_batches:
            for rule in rules_list:
                if rule.get("when_device_id") != changed_dev_id:
                    continue

                if_state = str(rule.get("when_state", "OPEN")).upper()
                opp_state = STATE_TO_OPPOSITE.get(if_state) or SENSOR_STATE_OPPOSITE.get(if_state)
                delay_sec = float(rule.get("delay_seconds", 0.0))

                if new_state == if_state:
                    then_dev = rule.get("then_device_id")
                    then_act = rule.get("then_action")
                    if then_dev and then_act:
                        if batch_tier > 1 and then_dev in t1_locked_targets:
                            continue
                        if batch_tier == 1:
                            t1_locked_targets.add(then_dev)
                        reason_lbl = f"IF {source_name}={new_state}"
                        if delay_sec <= 0.2:
                            res = await self.execute_device_action(
                                device_id=then_dev,
                                action=then_act,
                                source=reason_lbl,
                                bypass_rbac=True,
                                trigger_chains=False,
                            )
                            triggered_results.extend(res.get("results", []))
                        else:
                            await self.schedule_action(
                                device_id=then_dev,
                                action=then_act,
                                delay_seconds=delay_sec,
                                reason=reason_lbl,
                                bypass_rbac=True,
                                trigger_chains=False,
                            )

                elif opp_state and new_state == opp_state:
                    else_dev = rule.get("else_device_id", "")
                    else_act = rule.get("else_action", "")
                    if else_dev and else_act:
                        if batch_tier > 1 and else_dev in t1_locked_targets:
                            continue
                        if batch_tier == 1:
                            t1_locked_targets.add(else_dev)
                        reason_lbl = f"ELSE {source_name}={new_state}"
                        if delay_sec <= 0.2:
                            res = await self.execute_device_action(
                                device_id=else_dev,
                                action=else_act,
                                source=reason_lbl,
                                bypass_rbac=True,
                                trigger_chains=False,
                            )
                            triggered_results.extend(res.get("results", []))
                        else:
                            await self.schedule_action(
                                device_id=else_dev,
                                action=else_act,
                                delay_seconds=delay_sec,
                                reason=reason_lbl,
                                bypass_rbac=True,
                                trigger_chains=False,
                            )

        # Luật liên kết lưu trong SQLite (`automation_rules` + `rules_pool` sensor_link)
        try:
            from simulator.auth.tier_permissions import can_control_device
            from simulator.automation_repo import get_automation_snapshot_bundle

            _, rules_cached, _ = get_automation_snapshot_bundle()
            db_rules = sorted(
                rules_cached,
                key=lambda r: int(r.get("owner_tier") or 1),
            )
        except Exception:
            db_rules = []

        for rule in db_rules:
            if rule.get("when_device_id") != changed_dev_id:
                continue
            rule_tier = int(rule.get("owner_tier") or 1)
            if rule_tier >= 3:
                continue
            if_state = str(rule.get("when_state") or "OPEN").upper()
            opp_state = STATE_TO_OPPOSITE.get(if_state) or SENSOR_STATE_OPPOSITE.get(if_state)
            delay_sec = float(rule.get("delay_seconds") or 0.0)
            target_dev = ""
            target_act = ""
            prefix_lbl = "IF"

            if new_state == if_state:
                target_dev = str(rule.get("then_device_id") or "")
                target_act = str(rule.get("then_action") or "")
            elif opp_state and new_state == opp_state:
                target_dev = str(rule.get("else_device_id") or "")
                target_act = str(rule.get("else_action") or "")
                prefix_lbl = "ELSE"

            if not target_dev or not target_act or target_dev == changed_dev_id:
                continue
            if not can_control_device(rule_tier, target_dev):
                continue
            if rule_tier > 1 and target_dev in t1_locked_targets:
                continue
            if rule_tier == 1:
                t1_locked_targets.add(target_dev)

            reason_lbl = f"{prefix_lbl} {source_name}={new_state}"
            if delay_sec <= 0.2:
                res = await self.execute_device_action(
                    device_id=target_dev,
                    action=target_act,
                    source=reason_lbl,
                    bypass_rbac=True,
                    trigger_chains=False,
                )
                triggered_results.extend(res.get("results", []))
            else:
                await self.schedule_action(
                    device_id=target_dev,
                    action=target_act,
                    delay_seconds=delay_sec,
                    reason=reason_lbl,
                    bypass_rbac=True,
                    trigger_chains=False,
                )
        return triggered_results


__all__ = [
    "DATA_DIR",
    "FACTORY_FILE",
    "OVERLAY_FILE",
    "AUDIT_LOG_FILE",
    "VN_TZ",
    "get_vn_now",
    "format_vn_time_ampm",
    "append_audit_log",
    "read_audit_logs",
    "clear_audit_logs",
    "HARDWARE_AUDIO_PINS",
    "DEFAULT_DEVICES",
    "ROLE_LEVELS",
    "ROLE_NAMES",
    "DEFAULT_USERS",
    "ACTION_TO_STATE",
    "ACTION_VI_LABEL",
    "STATE_TO_OPPOSITE",
    "_format_clock_12h",
    "_extract_vn_date",
    "REPEAT_VI_LABELS",
    "REPEAT_INTERVAL_SECONDS",
    "detect_repeat_mode",
    "normalize_reset_scope",
    "parse_vn_clock_and_date",
    "parse_vn_time_string",
    "ensure_factory_file",
    "SmartHomeEngine",
]
