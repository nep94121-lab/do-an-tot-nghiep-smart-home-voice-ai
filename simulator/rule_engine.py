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
import json
import re
import time
from typing import Any, Callable, Coroutine

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
    _extract_vn_date,
    _format_clock_12h,
    append_audit_log,
    clear_audit_logs,
    detect_repeat_mode,
    ensure_factory_file,
    format_vn_time_ampm,
    get_vn_now,
    normalize_reset_scope,
    parse_vn_clock_and_date,
    parse_vn_time_string,
    read_audit_logs,
)
from simulator.mqtt_bridge import SmartHomeMQTTBridge


class SmartHomeEngine(EngineVoiceRbacMixin, EngineTimersMixin, EngineRulesMixin):
    """Lõi điều hành trung tâm Smart Home: tích hợp 3 Mixin (Voice RBAC, Bể 1 Timers, Bể 2 Rules) và Actuation MQTT."""

    def __init__(
        self,
        on_event: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
        on_voice_reset: Callable[[], dict[str, Any]] | None = None,
    ):
        self.on_event = on_event
        self.on_voice_reset = on_voice_reset
        self._current_user_id: str = "tuan_anh"
        self._current_role: str = "ADMIN"
        self.devices: dict[str, dict[str, Any]] = {
            k: dict(v, updated_at=time.time()) for k, v in DEFAULT_DEVICES.items()
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
        try:
            init_sqlite_database()
            sync_engine_state_to_sqlite(self)
        except Exception:
            pass

    def _default_overlay(self) -> dict[str, Any]:
        return {
            "word_mappings": {},
            "aliases": {},
            "if_else_rules": [],
            "chains": [],
            "users": {k: dict(v) for k, v in DEFAULT_USERS.items()},
            "user_pools": {
                "tuan_anh": {"word_mappings": {}, "aliases": {}, "if_else_rules": []},
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
                if "user_pools" not in base or not isinstance(base["user_pools"], dict):
                    base["user_pools"] = self._default_overlay()["user_pools"]
                t1_pool = base["user_pools"].setdefault(
                    "tuan_anh", {"word_mappings": {}, "aliases": {}, "if_else_rules": []}
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
        pools = self.overlay_rules.setdefault("user_pools", {})
        if uid not in pools or not isinstance(pools[uid], dict):
            pools[uid] = {"word_mappings": {}, "aliases": {}, "if_else_rules": []}
        pools[uid].setdefault("word_mappings", {})
        pools[uid].setdefault("aliases", {})
        pools[uid].setdefault("if_else_rules", [])
        return pools[uid]

    def _save_overlay(self) -> None:
        t1_pool = self._get_user_pool("tuan_anh")
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
        return [(device_id, action)]

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

    def set_active_user(self, user_or_role: str) -> dict[str, Any]:
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
    ) -> tuple[bool, str]:
        """Kiểm tra quyền điều khiển thiết bị theo RBAC 3 Tầng.
        Hỗ trợ actor_tier truyền vào trực tiếp từ request session để không phụ thuộc vào trạng thái toàn cục Singleton."""
        tier = int(actor_tier) if actor_tier is not None else int(self.current_tier)
        uid = actor_user_id or self._current_user_id

        u = self.users.get(uid) if uid else None
        if u and not u.get("active", True):
            return (
                False,
                f"Từ chối truy cập! Quyền của {u.get('name', uid)} đã bị hủy.",
            )

        dev = self.devices.get(dev_id, {})
        default_tier_map = {"ADMIN": 1, "MEMBER": 2, "CHILD_GUEST": 3}
        fallback_tier = default_tier_map.get(dev.get("min_role", "CHILD_GUEST"), 3)
        min_tier = int(self.system_policies.get("device_min_tiers", {}).get(dev_id, fallback_tier))

        if tier > min_tier:
            dname = dev.get("name", dev_id)
            return (
                False,
                f"Từ chối truy cập! Thiết bị {dname} chỉ cho phép từ Cấp {min_tier} trở lên điều khiển.",
            )

        # Kiểm tra custom directives của Admin
        ok_dir, reason_dir = self._check_custom_directive_device_lock_parameterized(dev_id, tier)
        if not ok_dir:
            return False, reason_dir

        req_role = {1: "ADMIN", 2: "MEMBER", 3: "CHILD_GUEST"}.get(min_tier, dev.get("min_role", "CHILD_GUEST"))
        role_map_rev = {1: "ADMIN", 2: "MEMBER", 3: "CHILD_GUEST"}
        actor_role = role_map_rev.get(tier, "CHILD_GUEST")
        user_lvl = ROLE_LEVELS.get(actor_role, 0)
        req_lvl = ROLE_LEVELS.get(req_role, 3)
        if user_lvl < req_lvl:
            return (
                False,
                f"Từ chối truy cập! Cấp hiện tại (Tầng {tier}) không đủ quyền.",
            )
        return True, "OK"

    async def execute_device_action(
        self,
        device_id: str,
        action: str,
        source: str = "voice",
        bypass_rbac: bool = False,
        trigger_chains: bool = True,
        request_tier: int | None = None,
        request_user_name: str | None = None,
        request_role: str | None = None,
    ) -> dict[str, Any]:
        targets = self._expand_targets(device_id, action)
        results = []
        for dev_id, act in targets:
            if dev_id not in self.devices:
                results.append({"ok": False, "device_id": dev_id, "error": f"Thiết bị '{dev_id}' không tồn tại."})
                continue
            dev = self.devices[dev_id]

            effective_tier = int(request_tier) if request_tier is not None else int(self.current_tier)
            effective_user = request_user_name or self.get_current_user_name()
            role_map_rev = {1: "ADMIN", 2: "MEMBER", 3: "CHILD_GUEST"}
            effective_role = request_role or role_map_rev.get(effective_tier, self.current_role)

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
                    results.append({"ok": False, "device_id": dev_id, "error": reason})
                    continue

            if dev["type"] == "door":
                new_state = "OPEN" if act in ("open", "turn_on") else "CLOSED"
            else:
                new_state = "ON" if act in ("open", "turn_on") else "OFF"

            if dev_id == "garden_pump" and not str(source).startswith("Cảm biến đất"):
                self.pump_manual_override_off = (new_state == "OFF")

            old_state = dev["state"]
            if old_state == new_state:
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
                })
                continue

            dev["state"] = new_state
            dev["updated_at"] = time.time()

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
            })

            results.append({
                "ok": True,
                "device_id": dev_id,
                "device_name": dev["name"],
                "state": new_state,
                "already_in_state": False,
            })

            if trigger_chains and self.server_connected:
                triggered_fx = await self._evaluate_reactive_if_else(dev_id, new_state)
                results.extend(triggered_fx)

        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        all_ok = all(r["ok"] for r in results) if results else False
        concise_reply = self._build_concise_spoken_reply(results)
        return {
            "ok": all_ok,
            "results": results,
            "exact_spoken_reply": concise_reply,
            "instruction_for_ai": f"BẮT BUỘC trả lời CỰC NGẮN GỌN đúng nguyên văn câu này: '{concise_reply}'",
            "summary": concise_reply,
        }

    async def sync_edge_flash(self) -> dict[str, Any]:
        """Đồng bộ bản sao 2 Bể (Bể 1 Hẹn giờ & Bể 2 Luật IF-ELSE) xuống Flash LittleFS của ESP8266."""
        snap = self.get_snapshot()
        combined_rules = list(snap.get("t1_global_if_else_rules", []))
        if self._current_user_id != "tuan_anh":
            combined_rules.extend(snap.get("if_else_rules", []))
        return await self.mqtt_bridge.sync_pools_to_esp8266_flash(
            timers=snap.get("timers", []),
            if_else_rules=combined_rules,
            system_policies=self.system_policies,
        )

    async def update_sensor_telemetry(self, temp_c: Any, humidity_pct: Any, wifi_rssi_dbm: Any = -52) -> dict[str, Any]:
        """Cập nhật thông số cảm biến DHT11 từ mạch ESP8266 và tự động kiểm tra luật ngưỡng nhiệt độ/độ ẩm."""
        pkt = await self.mqtt_bridge.update_dht11_telemetry(temp_c, humidity_pct, wifi_rssi_dbm)
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
        pkt = await self.mqtt_bridge.update_soil_moisture_telemetry(soil_moisture_pct)
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

        t1_rules = list(self._get_user_pool("tuan_anh").get("if_else_rules", []))
        rule_batches: list[tuple[int, list[dict[str, Any]]]] = [(1, t1_rules)]
        if self.current_tier == 2 and self._current_user_id != "tuan_anh":
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
