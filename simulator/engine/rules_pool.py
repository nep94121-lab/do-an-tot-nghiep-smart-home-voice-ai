"""Module simulator.engine.rules_pool: Quản lý Bể 2 (Đổi từ, Đổi lệnh, Luật IF-ELSE) và 4 Loại Reset Hệ thống."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from simulator.engine.constants_and_time import (
    ACTION_TO_STATE,
    ACTION_VI_LABEL,
    DEFAULT_DEVICES,
    DEFAULT_USERS,
    ROLE_NAMES,
    ensure_factory_file,
    format_vn_time_ampm,
    normalize_reset_scope,
)


class EngineRulesMixin:
    """Mixin quản lý Bể 2 (Rule Pool), Chế độ Offline Default, Truy vấn 2 Bể và 4 Phạm vi Reset."""

    devices: dict[str, dict[str, Any]]
    factory_rules: dict[str, Any]
    overlay_rules: dict[str, Any]
    users: dict[str, dict[str, Any]]
    active_timers: dict[str, dict[str, Any]]
    _timer_tasks: dict[str, asyncio.Task]
    pending_reset_confirmation: bool
    pending_reset_scope: str
    pending_rule: dict[str, Any] | None
    pending_voice_enrollment: dict[str, Any] | None
    server_connected: bool
    mqtt_bridge: Any
    on_voice_reset: Callable[[], dict[str, Any]] | None
    _current_user_id: str

    def get_merged_aliases(self, user_id: str | None = None) -> dict[str, list[dict[str, str]]]:
        merged = dict(self.factory_rules.get("aliases", {}))
        if user_id is None and self.current_tier >= 3 and not self.system_policies.get("tier3_can_custom_rules", False):
            return merged
        pool = self._get_user_pool(user_id)
        merged.update(pool.get("aliases", {}))
        return merged

    def get_word_mappings(self, user_id: str | None = None) -> dict[str, str]:
        if user_id is None and self.current_tier >= 3 and not self.system_policies.get("tier3_can_custom_rules", False):
            return {}
        pool = self._get_user_pool(user_id)
        return dict(pool.get("word_mappings", {}))

    def get_if_else_rules(self, user_id: str | None = None) -> list[dict[str, Any]]:
        if user_id is None and self.current_tier >= 3 and not self.system_policies.get("tier3_can_custom_rules", False):
            return []
        pool = self._get_user_pool(user_id)
        return list(pool.get("if_else_rules", []))

    def get_chains(self) -> list[dict[str, Any]]:
        return self.get_if_else_rules()

    def format_duration_vi(self, total_sec: float) -> str:
        s = int(round(max(0.0, total_sec)))
        h = s // 3600
        m = (s % 3600) // 60
        sec = s % 60
        parts = []
        if h > 0:
            parts.append(f"{h} giờ")
        if m > 0:
            parts.append(f"{m} phút")
        if sec > 0 or not parts:
            parts.append(f"{sec} giây")
        return " ".join(parts)

    def _action_device_phrase_vi(self, device_id: str, action: str) -> str:
        if device_id == "all_lights":
            verb = "bật" if action in ("open", "turn_on") else "tắt"
            return f"{verb} tất cả đèn"
        if device_id == "all_devices":
            verb = "bật" if action in ("open", "turn_on") else "tắt"
            return f"{verb} tất cả thiết bị"
        dev = self.devices.get(device_id, {})
        dname = dev.get("name", device_id).lower()
        dtype = dev.get("type", "light")
        if dtype == "door":
            verb = "mở" if action in ("open", "turn_on") else "đóng"
        elif dtype == "ac":
            verb = "mở" if action in ("open", "turn_on") else "tắt"
        else:
            verb = "bật" if action in ("open", "turn_on") else "tắt"
        return f"{verb} {dname}"

    def describe_device_command(self, device_id: str) -> str:
        if device_id not in self.devices:
            return "Không tìm thấy thiết bị này."
        dev = self.devices[device_id]
        dname = dev["name"].lower()
        dtype = dev["type"]
        if dtype == "door":
            default_cmd = f"'mở {dname}' và 'đóng {dname}'"
        elif dtype == "ac":
            default_cmd = f"'mở {dname}' và 'tắt {dname}'"
        else:
            default_cmd = f"'bật {dname}' và 'tắt {dname}'"

        words = [
            f"'{w}'"
            for w, m in self.get_word_mappings().items()
            if device_id in m.lower() or dname in m.lower()
        ]
        aliases = [
            f"'{p}' ({', '.join(self._action_device_phrase_vi(s['device_id'], s['action']) for s in steps)})"
            for p, steps in self.get_merged_aliases().items()
            if any(s["device_id"] == device_id for s in steps)
        ]
        ifs = []
        for r in self.get_if_else_rules():
            if r["when_device_id"] == device_id or r["then_device_id"] == device_id or r.get("else_device_id") == device_id:
                when_v = "mở" if r["when_state"] in ("OPEN", "ON") else ("đóng" if r["when_state"] == "CLOSED" else "tắt")
                then_p = self._action_device_phrase_vi(r["then_device_id"], r["then_action"])
                ifs.append(f"nếu {when_v} {r['when_device_name'].lower()} thì {then_p}")

        if not words and not aliases and not ifs:
            return f"Lệnh của {dname} đang ở mặc định: {default_cmd}."

        parts = [f"Lệnh mặc định là {default_cmd}"]
        if words:
            parts.append(f"tên gọi thêm: {', '.join(words)}")
        if aliases:
            parts.append(f"khẩu lệnh đã đổi: {', '.join(aliases)}")
        if ifs:
            parts.append(f"luật đi kèm: {'; '.join(ifs)}")
        return "; ".join(parts) + "."

    def get_pools_summary(self, query_type: str = "all", target_device_id: str = "") -> dict[str, Any]:
        q_type = (query_type or "all").strip().lower()
        q_mode = self.query_permission_mode

        if q_mode != "open_all" and self.current_tier >= 3:
            if target_device_id and target_device_id in self.devices and q_type == "device_command":
                spoken = self.describe_device_command(target_device_id)
                return {
                    "ok": True,
                    "query_type": q_type,
                    "current_user_id": self._current_user_id,
                    "current_user_name": self.get_current_user_name(),
                    "current_tier": self.current_tier,
                    "timer_pool_count": 0,
                    "timer_pool_items": [],
                    "rule_pool_count": 0,
                    "rule_pool_items": [],
                    "exact_spoken_reply": spoken,
                    "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
                    "summary": spoken,
                }
            deny_msg = "Bạn đang ở Cấp 3 (Khách), chỉ được hỏi về lệnh đóng mở thiết bị cơ bản."
            return {
                "ok": False,
                "query_type": q_type,
                "current_user_id": self._current_user_id,
                "current_user_name": self.get_current_user_name(),
                "current_tier": self.current_tier,
                "timer_pool_count": 0,
                "timer_pool_items": [],
                "rule_pool_count": 0,
                "rule_pool_items": [],
                "exact_spoken_reply": deny_msg,
                "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{deny_msg}'",
                "summary": deny_msg,
            }

        snap = self.get_snapshot()
        all_timers = snap["timers"]
        if q_mode != "open_all" and self.current_tier == 2:
            timers = [t for t in all_timers if t.get("owner_id") == self._current_user_id]
        else:
            timers = all_timers

        if q_mode == "open_all" and self.current_tier >= 3:
            t1_p = self._get_user_pool("tuan_anh")
            words = dict(t1_p.get("word_mappings", {}))
            aliases = dict(t1_p.get("aliases", {}))
            if_rules = list(t1_p.get("if_else_rules", []))
        else:
            words = snap["word_mappings"]
            aliases = snap["custom_aliases"]
            if_rules = snap["if_else_rules"]

        timer_descriptions = []
        spoken_timers = []
        for idx, t in enumerate(timers, 1):
            act_vi = ACTION_VI_LABEL.get(t["action"], t["action"])
            act_phrase = self._action_device_phrase_vi(t["device_id"], t["action"])
            owner_tag = f" [Tầng {t.get('owner_tier', 1)}: {t.get('owner_name', '')}]" if t.get("owner_name") else ""
            if t.get("target_vn_time"):
                timer_descriptions.append(
                    f"#{idx}: {act_vi} {t['device_name']} lúc {t['target_vn_time']}{owner_tag}"
                )
                spoken_timers.append(f"{t['target_vn_time']} {act_phrase}")
            else:
                timer_descriptions.append(
                    f"#{idx}: {act_vi} {t['device_name']} sau {t['remaining_label']}{owner_tag}"
                )
                spoken_timers.append(f"{t['remaining_label']} nữa {act_phrase}")

        rule_descriptions = []
        spoken_rules = []
        for w, m in words.items():
            rule_descriptions.append(f"Đổi từ '{w}' thành {m}")
            spoken_rules.append(f"đổi từ '{w}' thành {m}")
        for p, steps in aliases.items():
            step_vi = ", ".join(
                f"{ACTION_VI_LABEL.get(s['action'], s['action'])} {self.devices.get(s['device_id'], {}).get('name', s['device_id'])}"
                for s in steps
            )
            step_spoken = ", ".join(
                self._action_device_phrase_vi(s["device_id"], s["action"]) for s in steps
            )
            rule_descriptions.append(f"Đổi lệnh '{p}' -> {step_vi}")
            spoken_rules.append(f"lệnh '{p}' là {step_spoken}")
        for r in if_rules:
            then_vi = f"{ACTION_VI_LABEL.get(r['then_action'], r['then_action'])} {r['then_device_name']}"
            when_v = "mở" if r["when_state"] in ("OPEN", "ON") else ("đóng" if r["when_state"] == "CLOSED" else "tắt")
            then_spoken = self._action_device_phrase_vi(r["then_device_id"], r["then_action"])
            desc = f"Quan hệ IF: Khi {r['when_device_name']}={r['when_state']} thì {then_vi}"
            sp_desc = f"nếu {when_v} {r['when_device_name'].lower()} thì {then_spoken}"
            if r.get("else_device_id") and r.get("else_action"):
                else_vi = f"{ACTION_VI_LABEL.get(r['else_action'], r['else_action'])} {r['else_device_name']}"
                else_spoken = self._action_device_phrase_vi(r["else_device_id"], r["else_action"])
                desc += f", ngược lại thì {else_vi}"
                sp_desc += f", ngược lại {else_spoken}"
            rule_descriptions.append(desc)
            spoken_rules.append(sp_desc)

        if target_device_id and target_device_id in self.devices and q_type in ("device_command", "rules", "all"):
            spoken = self.describe_device_command(target_device_id)
        elif q_type == "timers":
            if not spoken_timers:
                spoken = "Hiện không có lịch hẹn giờ nào."
            else:
                spoken = f"Đang có {len(spoken_timers)} lịch hẹn giờ: {', '.join(spoken_timers)}."
        elif q_type == "rules":
            if not spoken_rules:
                spoken = "Hiện không có luật hay lệnh đổi nào, các lệnh đều ở mặc định gốc."
            else:
                spoken = f"Đang có {len(spoken_rules)} luật: {'; '.join(spoken_rules)}."
        else:
            t_part = (
                f"Đang có {len(spoken_timers)} hẹn giờ ({', '.join(spoken_timers)})"
                if spoken_timers
                else "Không có hẹn giờ nào"
            )
            r_part = (
                f"có {len(spoken_rules)} luật ({'; '.join(spoken_rules)})"
                if spoken_rules
                else "không có luật phụ nào"
            )
            spoken = f"{t_part}, và {r_part}."

        return {
            "ok": True,
            "query_type": q_type,
            "query_permission_mode": q_mode,
            "current_user_id": self._current_user_id,
            "current_user_name": self.get_current_user_name(),
            "current_tier": self.current_tier,
            "timer_pool_count": len(timers),
            "timer_pool_items": timer_descriptions,
            "rule_pool_count": len(rule_descriptions),
            "rule_pool_items": rule_descriptions,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời NGẮN GỌN, ĐỦ Ý, KHÔNG LỄ NGHI đúng câu: '{spoken}'",
            "summary": spoken,
        }

    def get_snapshot(self) -> dict[str, Any]:
        if getattr(self, "_mutation_depth", 0) == 0 and hasattr(self, "sync_from_shared_store"):
            self.sync_from_shared_store()
        now = time.time()
        timers_list = []
        for tid, tinfo in self.active_timers.items():
            rem = max(0.0, round(tinfo["fire_at"] - now, 1))
            dev_name = (
                self.devices[tinfo["device_id"]]["name"]
                if tinfo["device_id"] in self.devices
                else tinfo["device_id"]
            )
            timers_list.append({
                "id": tid,
                "device_id": tinfo["device_id"],
                "device_name": dev_name,
                "action": tinfo["action"],
                "action_vi": ACTION_VI_LABEL.get(tinfo["action"], tinfo["action"]),
                "delay_seconds": tinfo["delay_seconds"],
                "remaining_seconds": rem,
                "remaining_label": self.format_duration_vi(rem),
                "target_vn_time": tinfo.get("target_vn_time", ""),
                "reason": tinfo.get("reason", "Hẹn giờ"),
                "owner_id": tinfo.get("owner_id", "tuan_anh"),
                "owner_name": tinfo.get("owner_name", "Nguyễn Tuấn Anh"),
                "owner_tier": tinfo.get("owner_tier", 1),
            })
        can_custom = self.current_tier <= 2 or self.system_policies.get("tier3_can_custom_rules", False)
        cur_pool = self._get_user_pool(self._current_user_id) if can_custom else {"word_mappings": {}, "aliases": {}, "if_else_rules": []}
        t1_pool = self._get_user_pool("tuan_anh")
        return {
            "vn_time_now": format_vn_time_ampm(),
            "server_connected": self.server_connected,
            "offline_locked_devices": ["main_door", "alarm_siren"],
            "current_user_id": self._current_user_id,
            "current_user_name": self.get_current_user_name(),
            "current_tier": self.current_tier,
            "query_permission_mode": self.query_permission_mode,
            "system_policies": self.system_policies,
            "role": self.current_role,
            "role_name": f"Tầng {self.current_tier} — {self.get_current_user_name()} ({ROLE_NAMES.get(self.current_role, self.current_role)})",
            "users": list(self.users.values()),
            "pending_reset_confirmation": self.pending_reset_confirmation,
            "pending_rule": self.pending_rule,
            "pending_voice_enrollment": self.pending_voice_enrollment,
            "devices": list(self.devices.values()),
            "word_mappings": dict(cur_pool.get("word_mappings", {})),
            "factory_aliases": self.factory_rules.get("aliases", {}),
            "custom_aliases": dict(cur_pool.get("aliases", {})),
            "if_else_rules": list(cur_pool.get("if_else_rules", [])),
            "t1_global_if_else_rules": list(t1_pool.get("if_else_rules", [])),
            "chains": list(cur_pool.get("if_else_rules", [])),
            "timers": timers_list,
            "mqtt": self.mqtt_bridge.get_summary(),
        }

    async def set_word_mapping(
        self, custom_word: str, target_meaning: str, require_confirmation: bool = False
    ) -> dict[str, Any]:
        pol = self.system_policies
        if self.current_tier >= 3 and not pol.get("tier3_can_custom_rules", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) chỉ được gọi lệnh đóng mở cố định, không được tùy chỉnh từ ngữ."
            await self.emit({"type": "rbac_blocked", "action": "set_word_mapping", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        req_role = "CHILD_GUEST" if pol.get("tier3_can_custom_rules", False) else "MEMBER"
        allowed, msg = self.check_permission(req_role)
        if not allowed:
            await self.emit({"type": "rbac_blocked", "action": "set_word_mapping", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        w = custom_word.strip().lower()
        m = target_meaning.strip()
        if not w or not m:
            return {"ok": False, "error": "Từ mới và ý nghĩa đích không được để trống."}

        if require_confirmation and pol.get("require_rule_confirmation", True):
            ask_msg = f"Bạn muốn đổi từ '{w}' thành {m}, đúng không?"
            self.pending_rule = {
                "rule_type": "word_mapping",
                "user_id": self._current_user_id,
                "word": w,
                "meaning": m,
                "summary_vi": f"Đổi từ '{w}' -> {m}",
            }
            await self.emit({"type": "rule_confirmation_requested", "message": ask_msg, "pending_rule": self.pending_rule})
            await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
            return {
                "ok": True,
                "status": "AWAITING_RULE_CONFIRMATION",
                "exact_spoken_reply": ask_msg,
                "instruction_for_ai": f"CHƯA LƯU! BẮT BUỘC nhắc lại và hỏi người dùng đúng câu: '{ask_msg}'",
                "message": ask_msg,
            }

        self.pending_rule = None
        pool = self._get_user_pool(self._current_user_id)
        pool["word_mappings"][w] = m
        self._save_overlay()
        await self.emit({"type": "rule_created", "rule_type": "word_mapping", "user_id": self._current_user_id, "word": w, "meaning": m})
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "user_id": self._current_user_id,
            "exact_spoken_reply": f"Đã lưu đổi từ '{w}'.",
            "message": f"Đã lưu vào Bể lệnh của {self.get_current_user_name()}: '{w}' -> '{m}'.",
        }

    async def create_alias_rule(
        self,
        phrase: str,
        target_devices_csv: str,
        target_actions_csv: str,
        require_confirmation: bool = False,
    ) -> dict[str, Any]:
        pol = self.system_policies
        if self.current_tier >= 3 and not pol.get("tier3_can_custom_rules", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) chỉ được gọi lệnh đóng mở cố định, không được tùy chỉnh khẩu lệnh."
            await self.emit({"type": "rbac_blocked", "action": "create_alias_rule", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        req_role = "CHILD_GUEST" if pol.get("tier3_can_custom_rules", False) else "MEMBER"
        allowed, msg = self.check_permission(req_role)
        if not allowed:
            await self.emit({"type": "rbac_blocked", "action": "create_alias_rule", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        phrase_clean = phrase.strip().lower()
        devs = [d.strip() for d in target_devices_csv.split(",") if d.strip()]
        acts = [a.strip() for a in target_actions_csv.split(",") if a.strip()]
        if not phrase_clean or not devs or len(devs) != len(acts):
            return {"ok": False, "error": "Cú pháp đổi lệnh không hợp lệ (số thiết bị và hành động phải khớp nhau)."}

        steps = []
        step_vi_parts = []
        for d, a in zip(devs, acts):
            if d not in self.devices and d not in ("all_lights", "all_devices"):
                return {"ok": False, "error": f"Thiết bị '{d}' không tồn tại."}
            if a not in ACTION_TO_STATE:
                return {"ok": False, "error": f"Hành động '{a}' không hợp lệ."}
            steps.append({"device_id": d, "action": a})
            dname = self.devices.get(d, {}).get("name", d).lower()
            step_vi_parts.append(f"{ACTION_VI_LABEL.get(a, a).lower()} {dname}")

        step_vi = " và ".join(step_vi_parts)
        if require_confirmation and pol.get("require_rule_confirmation", True):
            ask_msg = f"Bạn muốn đổi lệnh {step_vi} thành '{phrase_clean}', đúng không?"
            self.pending_rule = {
                "rule_type": "alias",
                "user_id": self._current_user_id,
                "phrase": phrase_clean,
                "steps": steps,
                "summary_vi": f"Đổi lệnh '{phrase_clean}' -> {step_vi}",
            }
            await self.emit({"type": "rule_confirmation_requested", "message": ask_msg, "pending_rule": self.pending_rule})
            await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
            return {
                "ok": True,
                "status": "AWAITING_RULE_CONFIRMATION",
                "exact_spoken_reply": ask_msg,
                "instruction_for_ai": f"CHƯA LƯU! BẮT BUỘC nhắc lại và hỏi người dùng đúng câu: '{ask_msg}'",
                "message": ask_msg,
            }

        self.pending_rule = None
        pool = self._get_user_pool(self._current_user_id)
        pool["aliases"][phrase_clean] = steps
        self._save_overlay()
        await self.emit({
            "type": "rule_created",
            "rule_type": "alias",
            "user_id": self._current_user_id,
            "phrase": phrase_clean,
            "steps": steps,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "user_id": self._current_user_id,
            "exact_spoken_reply": f"Đã lưu lệnh '{phrase_clean}'.",
            "message": f"Đã lưu vào Bể lệnh của {self.get_current_user_name()}: '{phrase_clean}' -> {steps}.",
        }

    async def set_server_connection_mode(self, connected: bool) -> dict[str, Any]:
        if hasattr(self, "sync_from_shared_store"):
            self.sync_from_shared_store(force=True)
        self.server_connected = bool(connected)
        self.mqtt_bridge.esp8266_status["online"] = self.server_connected
        self.mqtt_bridge.esp8266_status["power_mode"] = (
            "SERVER_ONLINE_FULL_AI" if self.server_connected else "OFFLINE_DEFAULT_DOOR_LOCKED"
        )
        auto_closed_door = False
        if not self.server_connected and self.devices.get("main_door", {}).get("state") == "OPEN":
            self.devices["main_door"]["state"] = "CLOSED"
            self.devices["main_door"]["updated_at"] = time.time()
            auto_closed_door = True
            await self.emit({
                "type": "device_updated",
                "device_id": "main_door",
                "device_name": self.devices["main_door"]["name"],
                "gpio": self.devices["main_door"]["gpio"],
                "old_state": "OPEN",
                "new_state": "CLOSED",
                "source": "Tự động khóa cửa khi mất kết nối Server (Offline Fail-Safe)",
                "timestamp": self.devices["main_door"]["updated_at"],
            })

        if hasattr(self, "persist_to_shared_store"):
            self.persist_to_shared_store()

        if self.server_connected:
            msg = "🟢 Đã kết nối Server Laptop: Khôi phục đầy đủ AI Giọng nói, Khẩu lệnh tùy chỉnh và quyền mở Cửa chính."
        else:
            door_note = " (Đã tự động đóng khóa Cửa chính!)" if auto_closed_door else ""
            msg = (
                f"🟠 Chế độ Mạch Độc Lập (Offline - Không kết nối Server): Đã đưa về Lệnh Mặc Định Cơ Bản, "
                f"vô hiệu hóa khẩu lệnh custom và KHÓA CỨNG Cửa chính + Còi báo động{door_note}."
            )

        await self.emit({
            "type": "server_mode_changed",
            "server_connected": self.server_connected,
            "auto_closed_door": auto_closed_door,
            "message": msg,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "server_connected": self.server_connected,
            "auto_closed_door": auto_closed_door,
            "message": msg,
            "exact_spoken_reply": msg,
        }

    async def execute_offline_default_command(self, text: str, source: str = "offline_default") -> dict[str, Any]:
        t_clean = (text or "").strip()
        t_low = t_clean.lower()

        if self.current_tier >= 3:
            who_lbl = "Khách (Tầng 3)" if self.current_tier == 3 else "Người lạ (Không có trong Flash)"
            deny_offline_voice = (
                f"🚫 [CHẶN GIỌNG NÓI OFFLINE - TINY-DSP 16ms]: Khi mất kết nối Server, bộ nhớ Flash của mạch ESP8266 "
                f"chỉ duyệt giọng Chủ nhà (Tầng 1) và Thành viên gia đình (Tầng 2)! {who_lbl} không được phép điều khiển thiết bị khi Offline."
            )
            await self.emit({
                "type": "rbac_blocked",
                "action": "offline_voice_tier_blocked",
                "role": self.current_role,
                "tier": self.current_tier,
                "reason": deny_offline_voice,
            })
            return {
                "ok": False,
                "error": deny_offline_voice,
                "exact_spoken_reply": deny_offline_voice,
                "reply": deny_offline_voice,
                "offline_dsp_ms": 16.4,
            }

        t1_aliases = dict(self._get_user_pool("tuan_anh").get("aliases", {}))
        cur_aliases = dict(self._get_user_pool(self._current_user_id).get("aliases", {}))
        all_custom_phrases = set(t1_aliases.keys()) | set(cur_aliases.keys())
        for phrase in all_custom_phrases:
            if phrase and phrase in t_low:
                warn_msg = (
                    f"⚠️ [CHẾ ĐỘ OFFLINE - VỀ MẶC ĐỊNH]: Mạch đang không kết nối Server nên khẩu lệnh tùy chỉnh "
                    f"'{phrase}' đã bị vô hiệu hóa! Chỉ nhận lệnh mặc định cơ bản cho Đèn, Điều hòa, Quạt, Máy bơm (Cửa chính bị khóa)."
                )
                await self.emit({
                    "type": "rbac_blocked",
                    "action": "offline_custom_blocked",
                    "role": "OFFLINE_DEFAULT",
                    "reason": warn_msg,
                })
                return {"ok": False, "error": warn_msg, "exact_spoken_reply": warn_msg, "reply": warn_msg}

        if any(k in t_low for k in ("cửa chính", "mở cửa", "cửa nhà", "khóa cửa", "đóng cửa")):
            if any(v in t_low for v in ("đóng", "khóa")) and "mở" not in t_low:
                return await self.execute_device_action(
                    "main_door", "close", source=source, bypass_rbac=True, trigger_chains=False
                )
            lock_msg = (
                "🔒 [KHÓA AN NINH OFFLINE]: Khi không kết nối Server xác thực giọng nói, "
                "Cửa chính bị khóa cứng tuyệt đối! Không ai được phép mở cửa khi mất kết nối Server."
            )
            await self.emit({
                "type": "rbac_blocked",
                "device_id": "main_door",
                "device_name": "Cửa chính",
                "action": "open",
                "role": "OFFLINE_DEFAULT",
                "reason": lock_msg,
            })
            return {"ok": False, "error": lock_msg, "exact_spoken_reply": lock_msg, "reply": lock_msg}

        if any(k in t_low for k in ("còi", "báo động", "hú")):
            lock_msg = (
                "🔒 [KHÓA AN NINH OFFLINE]: Khi không kết nối Server, Còi báo động bị khóa bảo vệ, "
                "không cho phép bật/tắt tự do!"
            )
            await self.emit({
                "type": "rbac_blocked",
                "device_id": "alarm_siren",
                "device_name": "Còi báo động",
                "action": "turn_off",
                "role": "OFFLINE_DEFAULT",
                "reason": lock_msg,
            })
            return {"ok": False, "error": lock_msg, "exact_spoken_reply": lock_msg, "reply": lock_msg}

        is_off = any(w in t_low for w in ("tắt", "đóng", "ngắt", "dừng"))
        is_on = any(w in t_low for w in ("bật", "mở", "tưới"))
        if not is_on and not is_off:
            msg = (
                "⚠️ [CHẾ ĐỘ OFFLINE - MẶC ĐỊNH]: Chỉ nhận các câu lệnh mặc định rõ ràng như: "
                "'Bật đèn phòng khách', 'Tắt đèn phòng ngủ', 'Bật điều hòa', 'Bật quạt', 'Bật máy bơm' (Cửa chính bị khóa)."
            )
            return {"ok": False, "error": msg, "exact_spoken_reply": msg, "reply": msg}

        act_std = "turn_off" if is_off else "turn_on"
        matched_devs: list[tuple[str, str]] = []

        if any(k in t_low for k in ("tất cả đèn", "hai đèn", "2 đèn", "cả hai đèn")):
            matched_devs.append(("living_room_light", act_std))
            matched_devs.append(("bedroom_light", act_std))
        else:
            if any(k in t_low for k in ("đèn phòng khách", "đèn khách")):
                matched_devs.append(("living_room_light", act_std))
            if any(k in t_low for k in ("đèn phòng ngủ", "đèn ngủ")):
                matched_devs.append(("bedroom_light", act_std))
            if "đèn" in t_low and not matched_devs:
                matched_devs.append(("living_room_light", act_std))

        if "điều hòa" in t_low:
            matched_devs.append(("ac", "close" if is_off else "open"))
        if "quạt" in t_low:
            matched_devs.append(("fan", act_std))
        if any(k in t_low for k in ("máy bơm", "bơm nước", "tưới cây")):
            matched_devs.append(("garden_pump", act_std))

        if not matched_devs:
            msg = (
                "⚠️ [CHẾ ĐỘ OFFLINE - MẶC ĐỊNH]: Không nhận diện được tên thiết bị mặc định (hoặc bạn đang dùng từ đã đổi). "
                "Khi mất Server, chỉ nhận tên gốc: Đèn phòng khách, Đèn phòng ngủ, Điều hòa, Quạt, Máy bơm."
            )
            return {"ok": False, "error": msg, "exact_spoken_reply": msg, "reply": msg}

        combined_results: list[dict[str, Any]] = []
        for d_id, d_act in matched_devs:
            r = await self.execute_device_action(
                device_id=d_id,
                action=d_act,
                source=source,
                bypass_rbac=True,
                trigger_chains=False,
            )
            combined_results.extend(r.get("results", []))

        spoken = self._build_concise_spoken_reply(combined_results)
        return {
            "ok": True,
            "results": combined_results,
            "exact_spoken_reply": spoken,
            "reply": spoken,
            "summary": spoken,
            "offline_dsp_ms": 16.4,
        }

    async def execute_alias_rule(self, phrase: str) -> dict[str, Any]:
        if not self.server_connected:
            msg = (
                f"⚠️ [CHẾ ĐỘ OFFLINE - MẶC ĐỊNH]: Khi không kết nối Server, khẩu lệnh tùy chỉnh '{phrase}' "
                "bị vô hiệu hóa! Hệ thống đã về lệnh mặc định và khóa cứng Cửa chính."
            )
            await self.emit({"type": "rbac_blocked", "action": "execute_alias_rule", "role": "OFFLINE_DEFAULT", "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if self.current_tier >= 3 and not self.system_policies.get("tier3_can_custom_rules", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) chỉ được gọi các lệnh đóng mở cố định, không sử dụng khẩu lệnh tùy chỉnh."
            await self.emit({"type": "rbac_blocked", "action": "execute_alias_rule", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        phrase_clean = phrase.strip().lower()
        aliases = self.get_merged_aliases()
        matched_steps = aliases.get(phrase_clean)
        if not matched_steps:
            for k, v in aliases.items():
                if k in phrase_clean or phrase_clean in k:
                    matched_steps = v
                    phrase_clean = k
                    break
        if not matched_steps:
            return {"ok": False, "error": f"Không tìm thấy khẩu lệnh '{phrase}' trong Bể lệnh của {self.get_current_user_name()}."}

        all_results: list[dict[str, Any]] = []
        for step in matched_steps:
            res = await self.execute_device_action(
                device_id=step["device_id"],
                action=step["action"],
                source=f"khẩu lệnh '{phrase_clean}' ({self.get_current_user_name()})",
                trigger_chains=True,
            )
            all_results.extend(res.get("results", []))
        concise_reply = self._build_concise_spoken_reply(all_results)
        return {
            "ok": True,
            "results": all_results,
            "exact_spoken_reply": concise_reply,
            "instruction_for_ai": f"BẮT BUỘC trả lời CỰC NGẮN GỌN đúng nguyên văn câu này: '{concise_reply}'",
            "message": concise_reply,
        }

    def _has_cycle(self, rules: list[dict[str, Any]]) -> bool:
        adj: dict[str, set[str]] = {}
        for r in rules:
            u = r["when_device_id"]
            if r.get("then_device_id"):
                adj.setdefault(u, set()).add(r["then_device_id"])
            if r.get("else_device_id"):
                adj.setdefault(u, set()).add(r["else_device_id"])

        visited: set[str] = set()
        in_stack: set[str] = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            in_stack.add(node)
            for nxt in adj.get(node, ()):
                if nxt not in visited:
                    if dfs(nxt):
                        return True
                elif nxt in in_stack:
                    return True
            in_stack.remove(node)
            return False

        for n in list(adj.keys()):
            if n not in visited and dfs(n):
                return True
        return False

    def _check_t1_rule_conflict(self, new_rule: dict[str, Any]) -> str | None:
        if self.current_tier <= 1 or self.system_policies.get("tier2_can_override_tier1", False):
            return None
        t1_rules = list(self._get_user_pool("tuan_anh").get("if_else_rules", []))
        for r1 in t1_rules:
            if (
                r1.get("when_device_id") == new_rule["when_device_id"]
                and r1.get("when_state") == new_rule["when_state"]
                and r1.get("then_device_id") == new_rule["then_device_id"]
            ):
                return "Không thể đặt luật: Đã có luật ưu tiên của Tầng 1 Nguyễn Tuấn Anh trên cặp thiết bị này."
        if self._has_cycle(t1_rules + [new_rule]):
            return "Không thể đặt luật: Luật này gây xung đột vòng lặp với luật của Tầng 1 Nguyễn Tuấn Anh."
        return None

    async def set_if_else_rule(
        self,
        when_device_id: str,
        when_state: str,
        then_device_id: str,
        then_action: str,
        delay_seconds: float = 0.0,
        else_device_id: str = "",
        else_action: str = "",
        evaluate_now: bool = False,
        require_confirmation: bool = False,
    ) -> dict[str, Any]:
        pol = self.system_policies
        if self.current_tier >= 3 and not pol.get("tier3_can_custom_rules", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) chỉ được gọi lệnh đóng mở cố định, không được đặt luật IF-ELSE."
            await self.emit({"type": "rbac_blocked", "action": "set_if_else_rule", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        req_role = "CHILD_GUEST" if pol.get("tier3_can_custom_rules", False) else "MEMBER"
        allowed, msg = self.check_permission(req_role)
        if not allowed:
            await self.emit({"type": "rbac_blocked", "action": "set_if_else_rule", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if when_device_id not in self.devices or then_device_id not in self.devices:
            return {"ok": False, "error": "Thiết bị điều kiện IF hoặc thiết bị đích THEN không tồn tại."}

        norm_state = ACTION_TO_STATE.get(when_state.lower(), when_state.upper())
        if norm_state not in ("ON", "OFF", "OPEN", "CLOSED"):
            return {"ok": False, "error": f"Trạng thái điều kiện '{when_state}' không hợp lệ."}

        if then_action not in ACTION_TO_STATE:
            return {"ok": False, "error": f"Hành động THEN '{then_action}' không hợp lệ."}

        valid_else_dev = else_device_id if else_device_id in self.devices else ""
        valid_else_act = else_action if else_action in ACTION_TO_STATE else ""
        if not (valid_else_dev and valid_else_act):
            valid_else_dev = ""
            valid_else_act = ""

        if evaluate_now:
            curr_st = self.devices[when_device_id]["state"]
            if curr_st == norm_state:
                res = await self.execute_device_action(then_device_id, then_action, source="if_branch_now")
                return {"ok": True, "exact_spoken_reply": res["exact_spoken_reply"], "message": res["summary"]}
            if valid_else_dev and valid_else_act:
                res = await self.execute_device_action(valid_else_dev, valid_else_act, source="else_branch_now")
                return {"ok": True, "exact_spoken_reply": res["exact_spoken_reply"], "message": res["summary"]}
            return {"ok": True, "message": f"Điều kiện ({when_device_id}={norm_state}) hiện không thỏa mãn (đang là {curr_st})."}

        new_rule = {
            "id": f"ifelse_{int(time.time() * 1000)}",
            "owner_id": self._current_user_id,
            "owner_name": self.get_current_user_name(),
            "owner_tier": self.current_tier,
            "when_device_id": when_device_id,
            "when_device_name": self.devices[when_device_id]["name"],
            "when_state": norm_state,
            "delay_seconds": max(0.0, float(delay_seconds)),
            "then_device_id": then_device_id,
            "then_device_name": self.devices[then_device_id]["name"],
            "then_action": then_action,
            "else_device_id": valid_else_dev,
            "else_device_name": self.devices[valid_else_dev]["name"] if valid_else_dev else "",
            "else_action": valid_else_act,
        }

        conflict_err = self._check_t1_rule_conflict(new_rule)
        if conflict_err:
            await self.emit({"type": "rbac_blocked", "action": "set_if_else_rule", "role": self.current_role, "reason": conflict_err})
            return {"ok": False, "error": conflict_err, "exact_spoken_reply": conflict_err}

        existing = [
            r
            for r in self.get_if_else_rules(self._current_user_id)
            if not (r["when_device_id"] == when_device_id and r["when_state"] == norm_state)
        ]
        candidate = existing + [new_rule]
        if self._has_cycle(candidate):
            return {
                "ok": False,
                "error": "Từ chối tạo luật IF: Phát hiện vòng lặp vô hạn (Cycle Detected) giữa các thiết bị!",
            }

        when_verb = "mở" if norm_state in ("OPEN", "ON") else ("đóng" if norm_state == "CLOSED" else "tắt")
        then_verb = "mở" if then_action in ("open", "turn_on") and then_device_id in ("main_door", "ac") else ACTION_VI_LABEL.get(then_action, then_action).lower()
        when_n = new_rule["when_device_name"].lower()
        then_n = new_rule["then_device_name"].lower()
        else_vi = ""
        if valid_else_dev and valid_else_act:
            ev = ACTION_VI_LABEL.get(valid_else_act, valid_else_act).lower()
            else_vi = f", ngược lại thì {ev} {new_rule['else_device_name'].lower()}"

        if require_confirmation and pol.get("require_rule_confirmation", True):
            ask_msg = f"Bạn muốn đặt luật: nếu {when_verb} {when_n} thì {then_verb} {then_n}{else_vi}, đúng không?"
            self.pending_rule = {
                "rule_type": "if_else",
                "user_id": self._current_user_id,
                "rule": new_rule,
                "candidate_list": candidate,
                "summary_vi": f"Nếu {when_verb} {when_n} -> {then_verb} {then_n}{else_vi}",
            }
            await self.emit({"type": "rule_confirmation_requested", "message": ask_msg, "pending_rule": self.pending_rule})
            await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
            return {
                "ok": True,
                "status": "AWAITING_RULE_CONFIRMATION",
                "exact_spoken_reply": ask_msg,
                "instruction_for_ai": f"CHƯA LƯU LUẬT! BẮT BUỘC nhắc lại luật và hỏi xác nhận đúng câu: '{ask_msg}'",
                "message": ask_msg,
            }

        self.pending_rule = None
        pool = self._get_user_pool(self._current_user_id)
        pool["if_else_rules"] = candidate
        self._save_overlay()
        await self.emit({"type": "rule_created", "rule_type": "if_else", "user_id": self._current_user_id, "rule": new_rule})
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})

        else_desc = (
            f", NGƯỢC LẠI sẽ {valid_else_act} {new_rule['else_device_name']}"
            if valid_else_dev
            else " (1 chiều: trạng thái ngược lại giữ nguyên không đổi)"
        )
        delay_desc = f" sau {new_rule['delay_seconds']:.0f}s" if new_rule["delay_seconds"] > 0 else " ngay lập tức"
        return {
            "ok": True,
            "user_id": self._current_user_id,
            "exact_spoken_reply": "Đã lưu luật.",
            "message": (
                f"Đã lưu vào Bể lệnh của {self.get_current_user_name()}: NẾU {new_rule['when_device_name']} = {norm_state} "
                f"THÌ{delay_desc} sẽ {then_action} {new_rule['then_device_name']}{else_desc}."
            ),
        }

    async def confirm_pending_action(self, confirmed: bool = True) -> dict[str, Any]:
        if self.current_tier >= 3 and not self.system_policies.get("tier3_can_custom_rules", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền xác nhận cài đặt."
            await self.emit({"type": "rbac_blocked", "action": "confirm_pending_action", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if self.pending_rule is not None:
            pr = self.pending_rule
            self.pending_rule = None
            if not confirmed:
                await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
                return {
                    "ok": True,
                    "status": "RULE_CANCELLED",
                    "exact_spoken_reply": "Đã hủy cài đặt luật.",
                    "message": "Đã hủy cài đặt luật đang chờ.",
                }
            rtype = pr["rule_type"]
            target_uid = pr.get("user_id", self._current_user_id)
            pool = self._get_user_pool(target_uid)
            if rtype == "word_mapping":
                pool["word_mappings"][pr["word"]] = pr["meaning"]
                self._save_overlay()
                await self.emit({"type": "rule_created", "rule_type": "word_mapping", "user_id": target_uid, "word": pr["word"], "meaning": pr["meaning"]})
            elif rtype == "alias":
                pool["aliases"][pr["phrase"]] = pr["steps"]
                self._save_overlay()
                await self.emit({"type": "rule_created", "rule_type": "alias", "user_id": target_uid, "phrase": pr["phrase"], "steps": pr["steps"]})
            elif rtype == "if_else":
                pool["if_else_rules"] = pr["candidate_list"]
                self._save_overlay()
                await self.emit({"type": "rule_created", "rule_type": "if_else", "user_id": target_uid, "rule": pr["rule"]})

            await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
            return {
                "ok": True,
                "status": "RULE_CONFIRMED_AND_SAVED",
                "exact_spoken_reply": "Đã lưu luật.",
                "instruction_for_ai": "BẮT BUỘC trả lời ngắn gọn: 'Đã lưu luật.'",
                "message": f"Đã xác nhận và lưu vào Bể luật: {pr['summary_vi']}.",
            }

        if self.pending_reset_confirmation:
            return await self.confirm_factory_reset(confirmed=confirmed)

        return {
            "ok": True,
            "status": "NOTHING_PENDING",
            "exact_spoken_reply": "Hiện không có yêu cầu nào đang chờ xác nhận.",
            "message": "Không có luật hay lệnh reset nào đang chờ xác nhận.",
        }

    async def request_factory_reset(self, scope: str = "all") -> dict[str, Any]:
        if self.current_tier >= 3:
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền thực hiện reset."
            await self.emit({"type": "rbac_blocked", "action": "request_factory_reset", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        norm_scope = normalize_reset_scope(scope)
        if self.current_tier == 2 and norm_scope == "voice":
            msg = "Chỉ Tầng 1 Nguyễn Tuấn Anh mới có quyền reset giọng nói toàn hệ thống."
            await self.emit({"type": "rbac_blocked", "action": "request_factory_reset", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if not self.system_policies.get("require_reset_confirmation", True):
            return await self.factory_reset(scope=norm_scope)

        self.pending_reset_confirmation = True
        self.pending_reset_scope = norm_scope

        if self.current_tier == 2:
            question_map = {
                "timers": "Bạn muốn reset lịch đặt thời gian riêng của bạn đúng không?",
                "rules": "Bạn muốn reset bể lệnh riêng của bạn đúng không?",
                "all": "Bạn muốn reset toàn bộ lệnh và hẹn giờ riêng của bạn đúng không?",
            }
            ask_q = question_map.get(norm_scope, "Bạn muốn reset toàn bộ cài đặt riêng của bạn đúng không?")
        else:
            question_map = {
                "voice": "Bạn muốn reset giọng nói chỉ về của bạn đúng không?",
                "timers": "Bạn muốn reset đặt thời gian đúng không?",
                "rules": "Bạn muốn reset toàn bộ luật đúng không?",
                "all": "Bạn muốn reset tất cả đúng không?",
            }
            ask_q = question_map.get(norm_scope, "Bạn muốn reset tất cả đúng không?")

        await self.emit({
            "type": "reset_confirmation_requested",
            "scope": norm_scope,
            "user_id": self._current_user_id,
            "tier": self.current_tier,
            "message": f"Đang chờ xác nhận Reset ({norm_scope}): {ask_q}",
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "status": "AWAITING_CONFIRMATION",
            "reset_scope": norm_scope,
            "exact_spoken_reply": ask_q,
            "instruction_for_ai": f"BẮT BUỘC hỏi lại người dùng đúng câu: '{ask_q}' và chờ người dùng xác nhận.",
            "message": ask_q,
        }

    async def confirm_factory_reset(self, confirmed: bool = True) -> dict[str, Any]:
        if self.pending_rule is not None and not self.pending_reset_confirmation:
            return await self.confirm_pending_action(confirmed=confirmed)

        if self.current_tier >= 3:
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền xác nhận reset."
            await self.emit({"type": "rbac_blocked", "action": "confirm_factory_reset", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if not confirmed:
            self.pending_reset_confirmation = False
            self.pending_reset_scope = "all"
            await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
            return {
                "ok": True,
                "status": "CANCELLED",
                "exact_spoken_reply": "Đã hủy reset.",
                "message": "Đã hủy yêu cầu reset, giữ nguyên toàn bộ cài đặt hiện tại.",
            }

        target_scope = self.pending_reset_scope or "all"
        return await self.factory_reset(scope=target_scope)

    async def factory_reset(self, scope: str = "all") -> dict[str, Any]:
        if self.current_tier >= 3:
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền thực hiện reset."
            await self.emit({"type": "rbac_blocked", "action": "factory_reset", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        norm_scope = normalize_reset_scope(scope)
        if self.current_tier == 2 and norm_scope == "voice":
            msg = "Chỉ Tầng 1 Nguyễn Tuấn Anh mới có quyền reset giọng nói toàn hệ thống."
            await self.emit({"type": "rbac_blocked", "action": "factory_reset", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        self.pending_reset_confirmation = False
        self.pending_reset_scope = "all"

        if self.current_tier == 2:
            uid = self._current_user_id
            uname = self.get_current_user_name()
            if norm_scope in ("timers", "all"):
                own_tids = [
                    tid for tid, info in self.active_timers.items()
                    if info.get("owner_id") == uid
                ]
                for tid in own_tids:
                    t = self._timer_tasks.pop(tid, None)
                    if t:
                        t.cancel()
                    self.active_timers.pop(tid, None)

            if norm_scope in ("rules", "all"):
                self.pending_rule = None
                self.overlay_rules.setdefault("user_pools", {})[uid] = {
                    "word_mappings": {},
                    "aliases": {},
                    "if_else_rules": [],
                }
                self._save_overlay()

            spoken_t2 = {
                "timers": "Đã reset đặt thời gian riêng của bạn.",
                "rules": "Đã reset bể lệnh riêng của bạn.",
                "all": "Đã reset toàn bộ lệnh và hẹn giờ riêng của bạn.",
            }[norm_scope]
            detail_t2 = f"Đã xóa cài đặt ({norm_scope}) trong bể riêng của {uname}. Giữ nguyên 100% lệnh và hẹn giờ của Tầng 1 Nguyễn Tuấn Anh và người khác."
            await self.emit({
                "type": "factory_reset_completed",
                "scope": norm_scope,
                "user_id": uid,
                "tier": 2,
                "message": detail_t2,
            })
            await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
            return {
                "ok": True,
                "status": "RESET_COMPLETED",
                "reset_scope": norm_scope,
                "user_id": uid,
                "tier": 2,
                "exact_spoken_reply": spoken_t2,
                "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken_t2}'",
                "message": detail_t2,
            }

        if norm_scope in ("voice", "all"):
            self.current_role = "ADMIN"
            self.users = {k: dict(v) for k, v in DEFAULT_USERS.items()}
            self._save_overlay()
            if self.on_voice_reset is not None:
                try:
                    self.on_voice_reset()
                except Exception:
                    pass

        if norm_scope in ("timers", "all"):
            for task in list(self._timer_tasks.values()):
                task.cancel()
            self._timer_tasks.clear()
            self.active_timers.clear()

        if norm_scope in ("rules", "all"):
            self.pending_rule = None
            self.factory_rules = ensure_factory_file()
            saved_users = self.users
            self.overlay_rules = self._default_overlay()
            if norm_scope == "rules":
                self.overlay_rules["users"] = saved_users
            self._save_overlay()

        if norm_scope == "all":
            self._applying_shared_state = True
            try:
                self.devices = {
                    k: dict(v, updated_at=time.time()) for k, v in DEFAULT_DEVICES.items()
                }
                self.pump_manual_override_off = False
            finally:
                self._applying_shared_state = False
            if hasattr(self, "persist_to_shared_store"):
                self.persist_to_shared_store()

        spoken_map = {
            "voice": "Đã reset giọng nói chỉ về của bạn.",
            "timers": "Đã reset đặt thời gian.",
            "rules": "Đã reset toàn bộ luật về ngôn ngữ gốc.",
            "all": "Đã reset tất cả về nguyên bản.",
        }
        detail_map = {
            "voice": "Đã xóa các giọng phụ và reset quyền giọng nói chỉ về duy nhất giọng của bạn (Nguyễn Tuấn Anh - Tầng 1). Giữ nguyên Bể hẹn giờ và Bể luật.",
            "timers": "Đã xóa sạch toàn bộ lịch hẹn trong Bể 1 (Bể hẹn giờ = 0). Giữ nguyên Bể luật và quyền giọng nói.",
            "rules": "Đã xóa sạch toàn bộ từ đã đổi, lệnh đã đổi và luật IF trong Bể 2. Giữ nguyên Bể hẹn giờ và quyền giọng nói.",
            "all": "Đã reset tất cả: Giọng nói chỉ về của bạn, xóa sạch Bể hẹn giờ (0), xóa sạch Bể luật động (0) và đưa 6 thiết bị về nguyên bản.",
        }
        spoken = spoken_map[norm_scope]
        detail = detail_map[norm_scope]

        await self.emit({
            "type": "factory_reset_completed",
            "scope": norm_scope,
            "user_id": "tuan_anh",
            "tier": 1,
            "message": detail,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "status": "RESET_COMPLETED",
            "reset_scope": norm_scope,
            "user_id": "tuan_anh",
            "tier": 1,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
            "message": detail,
        }
