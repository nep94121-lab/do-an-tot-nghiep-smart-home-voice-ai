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
import json
import logging
import re
import time
from typing import Any, Callable, Coroutine, Iterator

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
from simulator.engine.constants_and_time import DEVICE_ID_ALIASES
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
        self._explicit_test_user_set: bool = False
        self.mqtt_bridge = SmartHomeMQTTBridge(on_event=self.emit)
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
                }
                for k, v in self.devices.items()
            },
        }
        if hasattr(self, "mqtt_bridge") and self.mqtt_bridge is not None:
            if hasattr(self.mqtt_bridge, "dht11_telemetry"):
                payload["dht11_telemetry"] = dict(self.mqtt_bridge.dht11_telemetry)
            if hasattr(self.mqtt_bridge, "soil_moisture_telemetry"):
                payload["soil_moisture_telemetry"] = dict(self.mqtt_bridge.soil_moisture_telemetry)
        return payload

    def persist_to_shared_store(self) -> dict[str, Any]:
        """Ghi trạng thái thiết bị hiện tại xuống tầng lưu trữ chia sẻ (Vercel Blob / File / InMemory)."""
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
        return saved

    def sync_from_shared_store(self, force: bool = False) -> bool:
        """Đồng bộ trạng thái thiết bị mới nhất từ tầng lưu trữ chia sẻ về RAM của instance hiện tại."""
        if not force and self._mutation_depth > 0:
            return False
        shared = self.state_backend.load_state()
        if not isinstance(shared, dict) or not isinstance(shared.get("devices"), dict):
            if self._dirty_device_ids:
                self.persist_to_shared_store()
            return False

        dirty_ids = set(self._dirty_device_ids)
        prev_synced_seq = self._last_synced_seq
        prev_states = {k: v.get("state") for k, v in self.devices.items() if isinstance(v, dict)}
        self._applying_shared_state = True
        try:
            if "server_connected" in shared and not dirty_ids:
                self.server_connected = bool(shared["server_connected"])
                if hasattr(self, "mqtt_bridge") and self.mqtt_bridge is not None:
                    self.mqtt_bridge.esp8266_status["online"] = self.server_connected
                    self.mqtt_bridge.esp8266_status["power_mode"] = (
                        "SERVER_ONLINE_FULL_AI" if self.server_connected else "OFFLINE_DEFAULT_DOOR_LOCKED"
                    )
            if "pump_manual_override_off" in shared and "garden_pump" not in dirty_ids:
                self.pump_manual_override_off = bool(shared["pump_manual_override_off"])

            remote_devices = shared.get("devices", {})
            for dev_id, dev_data in remote_devices.items():
                if dev_id in dirty_ids:
                    continue
                if dev_id in self.devices and isinstance(dev_data, dict):
                    if "state" in dev_data:
                        self.devices[dev_id]["state"] = str(dev_data["state"])
                    if "updated_at" in dev_data:
                        self.devices[dev_id]["updated_at"] = float(dev_data["updated_at"])
                    if "min_role" in dev_data:
                        self.devices[dev_id]["min_role"] = str(dev_data["min_role"])
                    if "version" in dev_data:
                        self.devices[dev_id]["version"] = max(
                            int(self.devices[dev_id].get("version", 1)),
                            int(dev_data["version"]),
                        )
                    remote_rev = int(shared.get("revision_seq", 0) or 0)
                    local_rev = int(self._last_synced_seq or 0)
                    remote_ts_ms = int(dev_data.get("last_client_ts_ms", 0) or 0)
                    local_ts_ms = int(self.devices[dev_id].get("last_client_ts_ms", 0) or 0)
                    if remote_rev >= local_rev or remote_ts_ms >= local_ts_ms:
                        if "last_client_id" in dev_data:
                            self.devices[dev_id]["last_client_id"] = str(dev_data["last_client_id"])
                        if "last_client_seq" in dev_data:
                            self.devices[dev_id]["last_client_seq"] = int(dev_data["last_client_seq"])
                        if "last_client_ts_ms" in dev_data:
                            self.devices[dev_id]["last_client_ts_ms"] = max(local_ts_ms, remote_ts_ms)
                        if "last_request_id" in dev_data:
                            self.devices[dev_id]["last_request_id"] = str(dev_data["last_request_id"])
                        if "last_requested_state" in dev_data:
                            self.devices[dev_id]["last_requested_state"] = str(dev_data["last_requested_state"])
                    if isinstance(dev_data.get("client_seqs"), dict):
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
                elif dev_id in DEFAULT_DEVICES and isinstance(dev_data, dict):
                    merged_dev = dict(DEFAULT_DEVICES[dev_id])
                    merged_dev.update(dev_data)
                    self.devices[dev_id] = TrackedDeviceDict(merged_dev, _engine=self)

            if hasattr(self, "mqtt_bridge") and self.mqtt_bridge is not None:
                if isinstance(shared.get("dht11_telemetry"), dict):
                    self.mqtt_bridge.dht11_telemetry.update(shared["dht11_telemetry"])
                if isinstance(shared.get("soil_moisture_telemetry"), dict):
                    self.mqtt_bridge.soil_moisture_telemetry.update(shared["soil_moisture_telemetry"])

            self._last_synced_seq = max(self._last_synced_seq, int(shared.get("revision_seq", 0)))
            self._last_synced_ts_ns = max(self._last_synced_ts_ns, int(shared.get("revision_ts_ns", 0)))
        finally:
            self._applying_shared_state = False

        if dirty_ids:
            self._dirty_device_ids.clear()
            self.persist_to_shared_store()
        else:
            cur_states = {k: v.get("state") for k, v in self.devices.items() if isinstance(v, dict)}
            if self._last_synced_seq != prev_synced_seq or cur_states != prev_states:
                try:
                    sync_engine_state_to_sqlite(self)
                except Exception:
                    pass
        return True

    def _on_direct_device_mutation(self, dev_id: str) -> None:
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

    def _save_overlay(self) -> None:
        self._purge_throwaway_qa_users()
        t1_pool = self._get_user_pool(OWNER_ID)
        self.overlay_rules["word_mappings"] = dict(t1_pool.get("word_mappings", {}))
        self.overlay_rules["aliases"] = dict(t1_pool.get("aliases", {}))
        self.overlay_rules["if_else_rules"] = list(t1_pool.get("if_else_rules", []))
        self.overlay_rules["users"] = self.users
        OVERLAY_FILE.write_bytes((json.dumps(self.overlay_rules, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        try:
            sync_engine_state_to_sqlite(self)
        except Exception:
            pass

    async def emit(self, event: dict[str, Any]) -> None:
        if self.on_event is not None:
            await self.on_event(event)
        ev_type = str(event.get("type", ""))
        if ev_type and ev_type not in ("state_snapshot", "mqtt_message", "mqtt_packet"):
            if getattr(self, "_mutation_depth", 0) == 0:
                try:
                    sync_engine_state_to_sqlite(self)
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
                "ir_code_learned": "SENSOR_IOT",
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
            append_audit_log(
                category=cat,
                event_type=ev_type,
                summary=msg,
                user_name=self.get_current_user_name(),
                tier=self.current_tier,
                details={k: v for k, v in event.items() if k != "snapshot"},
            )

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
                    ("fan", "turn_off"),
                    ("ac", "turn_off"),
                    ("alarm_siren", "turn_off"),
                    ("garden_pump", "turn_off"),
                    ("main_door", "close"),
                ]
            return [
                ("living_room_light", "turn_on"),
                ("bedroom_light", "turn_on"),
                ("fan", "turn_on"),
                ("ac", "turn_on"),
            ]
        return [(DEVICE_ID_ALIASES.get(device_id, device_id), action)]

    def _state_verb_vi(self, dev_type: str, state: str, already: bool = False) -> str:
        suffix = " sẵn rồi" if already else ""
        if dev_type == "door":
            return f"đã {'mở' if state == 'OPEN' else 'đóng'}{suffix}"
        if dev_type == "ac":
            return f"đã {'mở' if state == 'ON' else 'tắt'}{suffix}"
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

    async def factory_reset(self, scope: str = "all") -> dict[str, Any]:
        """Khôi phục cài đặt gốc, dọn dẹp cờ override của test."""
        self._explicit_test_user_set = False
        self.server_connected = True
        return await super().factory_reset(scope)

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
            "fan": ("quạt", "fan"),
            "ac": ("điều hòa", "máy lạnh", "ac"),
            "alarm_siren": ("còi báo động", "còi", "báo động", "alarm_siren"),
            "garden_pump": ("máy bơm tưới cây", "máy bơm", "bơm nước", "tưới cây", "garden_pump"),
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

        uid = actor_user_id or (
            self._current_user_id
            if str(self._current_user_id).strip().lower() != "unknown"
            else USER_ROLE_MAP.get(tier, OWNER_ID)
        )
        actor_role = ROLE_MAP.get(tier, "UNKNOWN")

        u = self.users.get(uid) if uid else None
        if u and not u.get("active", True):
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
        min_tier = int(self.system_policies.get("device_min_tiers", {}).get(canonical_id, fallback_tier))

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
                            "Còi báo động bị khóa bảo vệ, chỉ cho phép điều khiển Đèn, Điều hòa, Quạt, Máy bơm!"
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

                if not bypass_rbac and self.server_connected:
                    allowed, reason = self.check_device_permission(dev_id, action=act, actor_tier=effective_tier)
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
                if req_seq > 0 or req_ts_ms > 0:
                    if cid_key != "__anon__":
                        if req_seq > 0:
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

                await self.mqtt_bridge.publish_actuate_command(
                    device_id=dev_id,
                    state=new_state,
                    action=act,
                    source=source,
                    user_name=effective_user,
                    tier=effective_tier,
                )

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

        snap = self.get_snapshot()
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
            "snapshot": snap,
            "message": concise_reply,
            "exact_spoken_reply": concise_reply,
            "instruction_for_ai": f"BẮT BUỘC trả lời CỰC NGẮN GỌN đúng nguyên văn câu này: '{concise_reply}'",
            "summary": concise_reply,
        }
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
        with self.state_transaction():
            pkt = await self.mqtt_bridge.update_dht11_telemetry(temp_c, humidity_pct, wifi_rssi_dbm)
            self._state_dirty_in_tx = True
            t_clamped = float(self.mqtt_bridge.dht11_telemetry["temp_c"])
            h_clamped = float(self.mqtt_bridge.dht11_telemetry["humidity_pct"])
            triggered: list[dict[str, Any]] = []
            for raw_dir in self.system_policies.get("custom_system_directives", []):
                d_low = str(raw_dir).lower()
                m_temp = re.search(r"nhiệt độ\s*(?:trên|>|lớn hơn|vượt)\s*(\d+(?:\.\d+)?)", d_low)
                if m_temp and t_clamped > float(m_temp.group(1)):
                    if any(k in d_low for k in ("mở điều hòa", "bật điều hòa", "ac")):
                        res = await self.execute_device_action("ac", "open", source=f"DHT11 ({t_clamped}°C > {m_temp.group(1)}°C)", bypass_rbac=True)
                        triggered.extend(res.get("results", []))
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
        """Cập nhật thông số cảm biến Độ ẩm Đất YL-69 (Chân A0) và tự động điều khiển Máy bơm tưới cây (Chân D3)."""
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

    async def learn_ir_remote_command(
        self,
        device_name: str,
        command_action: str = "open",
        protocol: str = "COOLIX_38KHZ",
        hex_code: str = "0xB2BF40",
    ) -> dict[str, Any]:
        """Chiếm quyền / Học lệnh Remote Hồng ngoại 38kHz (VS1838B D5 -> Lưu Write-Through -> Phát IR LED D2)."""
        if self.current_tier >= 3 and not self.system_policies.get("tier3_can_custom_rules", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền học lệnh điều khiển hồng ngoại mới."
            await self.emit({"type": "rbac_blocked", "action": "learn_ir_remote_command", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}
        await self.mqtt_bridge.start_ir_learning(device_name=device_name, command_action=command_action)
        res = await self.mqtt_bridge.complete_ir_learning(protocol=protocol, hex_code=hex_code)
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return res

    async def _evaluate_reactive_if_else(self, changed_dev_id: str, new_state: str) -> list[dict[str, Any]]:
        """Kiểm tra luật IF khi `changed_dev_id` chuyển sang `new_state`."""
        triggered_results: list[dict[str, Any]] = []
        t1_locked_targets: set[str] = set()

        t1_rules = list(self._get_user_pool(OWNER_ID).get("if_else_rules", []))
        rule_batches: list[tuple[int, list[dict[str, Any]]]] = [(1, t1_rules)]
        if self.current_tier == 2 and self._current_user_id != OWNER_ID:
            t2_rules = list(self._get_user_pool(self._current_user_id).get("if_else_rules", []))
            rule_batches.append((2, t2_rules))

        for batch_tier, rules_list in rule_batches:
            for rule in rules_list:
                if rule.get("when_device_id") != changed_dev_id:
                    continue

                if_state = rule.get("when_state", "OPEN")
                delay_sec = float(rule.get("delay_seconds", 0.0))

                if new_state == if_state:
                    then_dev = rule.get("then_device_id")
                    then_act = rule.get("then_action")
                    if then_dev and then_act:
                        if batch_tier > 1 and then_dev in t1_locked_targets:
                            continue
                        if batch_tier == 1:
                            t1_locked_targets.add(then_dev)
                        reason_lbl = f"IF {self.devices[changed_dev_id]['name']}={new_state}"
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

                elif new_state == STATE_TO_OPPOSITE.get(if_state):
                    else_dev = rule.get("else_device_id", "")
                    else_act = rule.get("else_action", "")
                    if else_dev and else_act:
                        if batch_tier > 1 and else_dev in t1_locked_targets:
                            continue
                        if batch_tier == 1:
                            t1_locked_targets.add(else_dev)
                        reason_lbl = f"ELSE {self.devices[changed_dev_id]['name']}={new_state}"
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
