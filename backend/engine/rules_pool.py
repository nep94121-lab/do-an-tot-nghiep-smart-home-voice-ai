"""Module backend.engine.rules_pool: Quản lý Bể 2 (Đổi từ, Đổi lệnh, Luật IF-ELSE) và 4 Loại Reset Hệ thống."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from backend.engine.audit_logger import append_audit_log
from backend.engine.constants_and_time import (
    ACTION_TO_STATE,
    ACTION_VI_LABEL,
    DEFAULT_DEVICES,
    DEFAULT_USERS,
    ROLE_NAMES,
    ensure_factory_file,
    format_vn_time_ampm,
    normalize_reset_scope,
)
from backend.voice_config import (
    OWNER_ID,
    ROLE_MAP,
    is_throwaway_qa_identity,
    sanitize_api_payload,
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
        from backend.automation_repo import format_duration_vi as _fmt_dur_vi

        return _fmt_dur_vi(total_sec)

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
            deny_msg = "Khách chỉ được bật tắt thiết bị thôi ạ."
            return {
                "ok": False,
                "rbac_blocked": True,
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
            timers = [t for t in all_timers if str(t.get("owner_user_id") or t.get("owner_id") or "") == self._current_user_id]
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

    @staticmethod
    def _sanitize_user_entry(u: dict[str, Any]) -> dict[str, Any]:
        allowed_keys = (
            "id",
            "name",
            "tier",
            "role",
            "active",
            "granted_by",
            "granted_by_name",
            "granted_by_tier",
        )
        return {k: u[k] for k in allowed_keys if k in u}

    def get_public_device_snapshot(self, *, sync: bool = True) -> dict[str, Any]:
        if hasattr(self, "_purge_throwaway_qa_users"):
            self._purge_throwaway_qa_users()
        if sync and getattr(self, "_mutation_depth", 0) == 0 and hasattr(self, "sync_from_shared_store"):
            self.sync_from_shared_store()
        mqtt_raw = self.mqtt_bridge.get_summary() if hasattr(self, "mqtt_bridge") and self.mqtt_bridge else {}
        sound_raw = dict(mqtt_raw.get("sound_telemetry", {})) if isinstance(mqtt_raw.get("sound_telemetry"), dict) else {}
        public_mqtt = {
            "esp8266_status": dict(mqtt_raw.get("esp8266_status", {})) if isinstance(mqtt_raw.get("esp8266_status"), dict) else {},
            "dht11_telemetry": dict(mqtt_raw.get("dht11_telemetry", {})) if isinstance(mqtt_raw.get("dht11_telemetry"), dict) else {},
            "soil_moisture_telemetry": dict(mqtt_raw.get("soil_moisture_telemetry", {})) if isinstance(mqtt_raw.get("soil_moisture_telemetry"), dict) else {},
            "sound_telemetry": sound_raw,
            "ky037_telemetry": sound_raw,
        }
        sensors_data = self.read_all_sensors() if hasattr(self, "read_all_sensors") else {}
        rev_seq = int(getattr(self, "_last_synced_seq", 0))
        return sanitize_api_payload({
            "ok": True,
            "authenticated": False,
            "public_only": True,
            "revision_seq": rev_seq,
            "state_revision": rev_seq,
            "revision_ts_ns": int(getattr(self, "_last_synced_ts_ns", 0)),
            "vn_time_now": format_vn_time_ampm(),
            "server_connected": self.server_connected,
            "offline_locked_devices": ["main_door", "alarm_siren"],
            "devices": list(self.devices.values()),
            "sensors": sensors_data,
            "mqtt": public_mqtt,
        })

    def get_snapshot(
        self,
        session: Any | None = None,
        include_users: bool | None = None,
        public_only: bool = False,
        *,
        sync: bool = True,
    ) -> dict[str, Any]:
        if hasattr(self, "_purge_throwaway_qa_users"):
            self._purge_throwaway_qa_users()
        if public_only:
            return self.get_public_device_snapshot(sync=sync)
        if session is not None:
            if not getattr(session, "is_authenticated", False) or getattr(session, "source", "") in (
                "unauthenticated",
                "invalid_token",
                "rejected_unknown",
            ):
                return self.get_public_device_snapshot(sync=sync)
            if hasattr(session, "is_expired") and hasattr(session, "source") and hasattr(session, "email"):
                from backend.auth.session_store import session_is_current

                if not session_is_current(session):
                    return self.get_public_device_snapshot(sync=sync)

        if sync and getattr(self, "_mutation_depth", 0) == 0 and hasattr(self, "sync_from_shared_store"):
            self.sync_from_shared_store()

        if session is not None:
            uid = str(getattr(session, "user_id", "") or OWNER_ID)
            if is_throwaway_qa_identity(uid):
                uid = OWNER_ID
            u_obj = self.users.get(uid) or {}
            tier = int(getattr(session, "tier", 0) or u_obj.get("tier", 3))
            role = str(getattr(session, "role", "") or u_obj.get("role") or ROLE_MAP.get(tier, "CHILD_GUEST"))
            uname = str(u_obj.get("name") or getattr(session, "display_name", "") or uid)
        else:
            uid = self.current_user_id
            tier = self.current_tier
            role = self.current_role
            uname = self.get_current_user_name()

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
                "raw_target": tinfo.get("raw_target", tinfo["device_id"]),
                "device_name": dev_name,
                "action": tinfo["action"],
                "action_vi": ACTION_VI_LABEL.get(tinfo["action"], tinfo["action"]),
                "delay_seconds": tinfo["delay_seconds"],
                "remaining_seconds": rem,
                "remaining_label": self.format_duration_vi(rem),
                "fire_at": float(tinfo.get("fire_at") or now),
                "repeat": str(tinfo.get("repeat") or "once"),
                "target_vn_time": tinfo.get("target_vn_time", ""),
                "reason": tinfo.get("reason", "Hẹn giờ"),
                "label": tinfo.get("label", tinfo.get("reason", "Hẹn giờ")),
                "owner_id": tinfo.get("owner_user_id", tinfo.get("owner_id", "tuan_anh")),
                "owner_user_id": tinfo.get("owner_user_id", tinfo.get("owner_id", "tuan_anh")),
                "owner_name": tinfo.get("owner_name", "Nguyễn Tuấn Anh"),
                "owner_tier": tinfo.get("owner_tier", 1),
            })
        db_schedules: list[dict[str, Any]] = []
        db_rules: list[dict[str, Any]] = []
        db_scenes: list[dict[str, Any]] = []
        db_compound_rules: list[dict[str, Any]] = []
        try:
            from backend.automation_repo import get_automation_snapshot_bundle

            db_schedules, db_rules, db_scenes = get_automation_snapshot_bundle()
        except Exception:
            pass
        try:
            from backend.automation_engine import list_compound_rules

            db_compound_rules = list_compound_rules(include_disabled=True)
        except Exception:
            db_compound_rules = []
        if tier >= 3:
            timers_list = []
            db_schedules = []
            db_rules = []
            db_scenes = []
            db_compound_rules = []
        elif tier == 2:
            timers_list = [
                t for t in timers_list
                if str(t.get("owner_user_id") or t.get("owner_id") or "") == uid
            ]
            db_schedules = [
                s for s in db_schedules
                if str(s.get("owner_user_id") or "") == uid
            ]
            db_rules = [
                r for r in db_rules
                if str(r.get("owner_user_id") or "") == uid
            ]
            db_scenes = [
                c for c in db_scenes
                if str(c.get("owner_user_id") or "") == uid
            ]
            db_compound_rules = [
                r for r in db_compound_rules
                if str(r.get("owner_user_id") or "") == uid
            ]
        can_custom = tier <= 2
        cur_pool = self._get_user_pool(uid) if can_custom else {"word_mappings": {}, "aliases": {}, "if_else_rules": []}
        t1_pool = self._get_user_pool("tuan_anh")
        should_include_users = bool(include_users) if include_users is not None else (tier == 1 and role == "ADMIN")
        snap: dict[str, Any] = {
            "ok": True,
            "revision_seq": int(getattr(self, "_last_synced_seq", 0)),
            "state_revision": int(getattr(self, "_last_synced_seq", 0)),
            "revision_ts_ns": int(getattr(self, "_last_synced_ts_ns", 0)),
            "vn_time_now": format_vn_time_ampm(),
            "server_connected": self.server_connected,
            "offline_locked_devices": ["main_door", "alarm_siren"],
            "current_user_id": uid,
            "current_user_name": uname,
            "current_tier": tier,
            "query_permission_mode": self.query_permission_mode,
            "system_policies": self.system_policies,
            "role": role,
            "role_name": f"Tầng {tier} — {uname} ({ROLE_NAMES.get(role, role)})",
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
            "schedules": db_schedules,
            "automation_rules": db_rules,
            "compound_rules": db_compound_rules,
            "house_mode": str(getattr(getattr(self, "_root_engine", self), "house_mode", "HOME") or "HOME"),
            "custom_commands": db_scenes,
            "scenes": db_scenes,
            "sensors": self.read_all_sensors() if hasattr(self, "read_all_sensors") else {},
            "mqtt": self.mqtt_bridge.get_summary(),
        }
        if should_include_users:
            snap["users"] = [
                self._sanitize_user_entry(u)
                for u in self.users.values()
                if not is_throwaway_qa_identity(u.get("id"))
                and not is_throwaway_qa_identity(u.get("email"))
                and not is_throwaway_qa_identity(u.get("name"))
            ]
        if session is not None and getattr(session, "is_authenticated", False) and getattr(session, "source", "") not in (
            "unauthenticated",
            "invalid_token",
            "rejected_unknown",
        ):
            snap["authenticated"] = True
            snap["public_only"] = False
            email = str(getattr(session, "email", "") or "")
            if not email:
                try:
                    email = str((u_obj or {}).get("email") or "")
                except Exception:
                    email = ""
            if email:
                snap["current_user_email"] = email
        if session is not None and getattr(session, "is_authenticated", False) and getattr(session, "source", "") not in (
            "unauthenticated",
            "invalid_token",
            "rejected_unknown",
        ):
            from backend.auth.tier_permissions import filter_device_list, permission_table_payload

            snap["devices"] = filter_device_list(list(snap.get("devices") or []), int(tier))
            snap["permission_table"] = permission_table_payload()
            snap["allowed_device_ids"] = [d["id"] for d in snap["devices"] if isinstance(d, dict) and d.get("id")]
        from backend.auth.tier_permissions import restrict_guest_snapshot
        return sanitize_api_payload(
            restrict_guest_snapshot(snap, session, treat_none_as_unauthenticated=False)
        )

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
                "owner_user_id": self._current_user_id,
                "word": w,
                "meaning": m,
                "summary_vi": f"Đổi từ '{w}' -> {m}",
            }
            await self.emit({"type": "rule_confirmation_requested", "owner_user_id": self._current_user_id, "message": ask_msg, "pending_rule": self.pending_rule})
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
        await self.emit({"type": "rule_created", "rule_type": "word_mapping", "owner_user_id": self._current_user_id, "user_id": self._current_user_id, "word": w, "meaning": m})
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
                "owner_user_id": self._current_user_id,
                "phrase": phrase_clean,
                "steps": steps,
                "summary_vi": f"Đổi lệnh '{phrase_clean}' -> {step_vi}",
            }
            await self.emit({"type": "rule_confirmation_requested", "owner_user_id": self._current_user_id, "message": ask_msg, "pending_rule": self.pending_rule})
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
            "owner_user_id": self._current_user_id,
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
        target_connected = bool(connected)

        def _apply_mode(target_root: Any) -> dict[str, Any] | None:
            target_root.server_connected = target_connected
            if hasattr(target_root, "mqtt_bridge") and target_root.mqtt_bridge is not None:
                target_root.mqtt_bridge.esp8266_status["online"] = target_root.server_connected
                target_root.mqtt_bridge.esp8266_status["power_mode"] = (
                    "SERVER_ONLINE_FULL_AI" if target_root.server_connected else "OFFLINE_DEFAULT_DOOR_LOCKED"
                )
            closed_event: dict[str, Any] | None = None
            door = target_root.devices.get("main_door")
            if not target_root.server_connected and isinstance(door, dict) and door.get("state") == "OPEN":
                target_root._applying_shared_state_depth = getattr(target_root, "_applying_shared_state_depth", 0) + 1
                target_root._applying_shared_state = True
                try:
                    prev_ts = float(door.get("updated_at", 0.0) or 0.0)
                    now_ts = max(time.time(), prev_ts + 1e-6)
                    door["state"] = "CLOSED"
                    door["updated_at"] = now_ts
                    door["version"] = int(door.get("version", 1) or 1) + 1
                finally:
                    target_root._applying_shared_state_depth = max(
                        0, getattr(target_root, "_applying_shared_state_depth", 1) - 1
                    )
                    target_root._applying_shared_state = target_root._applying_shared_state_depth > 0
                closed_event = {
                    "type": "device_updated",
                    "device_id": "main_door",
                    "device_name": door["name"],
                    "gpio": door["gpio"],
                    "old_state": "OPEN",
                    "new_state": "CLOSED",
                    "source": "Tự động khóa cửa khi mất kết nối Server (Offline Fail-Safe)",
                    "timestamp": door["updated_at"],
                }
            return closed_event

        closed_event: dict[str, Any] | None = None
        if hasattr(self, "_commit_shared_state_mutation"):
            closed_event = await self._commit_shared_state_mutation(_apply_mode)
        else:
            if hasattr(self, "sync_from_shared_store"):
                self.sync_from_shared_store(force=True)
            closed_event = _apply_mode(self)
            if hasattr(self, "persist_to_shared_store"):
                self.persist_to_shared_store()

        auto_closed_door = closed_event is not None
        if closed_event is not None:
            await self.emit(closed_event)

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
                    f"'{phrase}' đã bị vô hiệu hóa! Chỉ nhận lệnh mặc định cơ bản cho Đèn, Máy bơm, Nguồn mạch loa PAM8403 (Cửa chính bị khóa)."
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
            if "main_door" in self.devices and self.devices["main_door"].get("state") != "CLOSED":
                self.devices["main_door"]["state"] = "CLOSED"
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
                "'Bật đèn phòng khách', 'Tắt đèn phòng ngủ', 'Bật máy bơm', 'Bật nguồn mạch loa' (Cửa chính bị khóa)."
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

        if any(k in t_low for k in ("nguồn mạch loa", "mạch loa", "nguồn loa", "pam8403", "loa")):
            matched_devs.append(("speaker_amp", act_std))
        if any(k in t_low for k in ("máy bơm", "bơm nước", "tưới cây")):
            matched_devs.append(("garden_pump", act_std))

        if not matched_devs:
            msg = (
                "⚠️ [CHẾ ĐỘ OFFLINE - MẶC ĐỊNH]: Không nhận diện được tên thiết bị mặc định (hoặc bạn đang dùng từ đã đổi). "
                "Khi mất Server, chỉ nhận tên gốc: Đèn phòng khách, Đèn phòng ngủ, Máy bơm, Nguồn mạch loa PAM8403."
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
                f"[CHẾ ĐỘ OFFLINE - MẶC ĐỊNH]: Khi không kết nối Server, khẩu lệnh tùy chỉnh '{phrase}' "
                "bị vô hiệu hóa! Hệ thống đã về lệnh mặc định và khóa cứng Cửa chính."
            )
            await self.emit({"type": "rbac_blocked", "action": "execute_alias_rule", "role": "OFFLINE_DEFAULT", "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if self.current_tier >= 3:
            msg = "Khách chỉ được bật tắt thiết bị thôi ạ."
            await self.emit({"type": "rbac_blocked", "action": "execute_alias_rule", "role": self.current_role, "reason": msg})
            return {"ok": False, "rbac_blocked": True, "error": msg, "exact_spoken_reply": msg}

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
        then_verb = "mở" if then_action in ("open", "turn_on") and then_device_id == "main_door" else ACTION_VI_LABEL.get(then_action, then_action).lower()
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
                "owner_user_id": self._current_user_id,
                "rule": new_rule,
                "candidate_list": candidate,
                "summary_vi": f"Nếu {when_verb} {when_n} -> {then_verb} {then_n}{else_vi}",
            }
            await self.emit({"type": "rule_confirmation_requested", "owner_user_id": self._current_user_id, "message": ask_msg, "pending_rule": self.pending_rule})
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
        await self.emit({"type": "rule_created", "rule_type": "if_else", "owner_user_id": self._current_user_id, "user_id": self._current_user_id, "rule": new_rule})
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

    async def confirm_pending_action(self, confirmed: bool = False) -> dict[str, Any]:
        confirmed = confirmed is True
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
                await self.emit({"type": "rule_created", "rule_type": "word_mapping", "owner_user_id": target_uid, "user_id": target_uid, "word": pr["word"], "meaning": pr["meaning"]})
            elif rtype == "alias":
                pool["aliases"][pr["phrase"]] = pr["steps"]
                self._save_overlay()
                await self.emit({"type": "rule_created", "rule_type": "alias", "owner_user_id": target_uid, "user_id": target_uid, "phrase": pr["phrase"], "steps": pr["steps"]})
            elif rtype == "if_else":
                pool["if_else_rules"] = pr["candidate_list"]
                self._save_overlay()
                await self.emit({"type": "rule_created", "rule_type": "if_else", "owner_user_id": target_uid, "user_id": target_uid, "rule": pr["rule"]})

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
            "owner_user_id": self._current_user_id,
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

    async def confirm_factory_reset(self, confirmed: bool = False) -> dict[str, Any]:
        confirmed = confirmed is True
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

    async def factory_reset(self, scope: str = "all", *, bypass_rbac: bool = False) -> dict[str, Any]:
        effective_tier = 1 if bypass_rbac else self.current_tier
        if effective_tier >= 3:
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền thực hiện reset."
            await self.emit({"type": "rbac_blocked", "action": "factory_reset", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        norm_scope = normalize_reset_scope(scope)
        if effective_tier == 2 and norm_scope == "voice":
            msg = "Chỉ Tầng 1 Nguyễn Tuấn Anh mới có quyền reset giọng nói toàn hệ thống."
            await self.emit({"type": "rbac_blocked", "action": "factory_reset", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        self.pending_reset_confirmation = False
        self.pending_reset_scope = "all"

        if effective_tier == 2:
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
                    try:
                        from backend.automation_repo import delete_timer_row

                        delete_timer_row(tid)
                    except Exception:
                        pass

            if norm_scope in ("rules", "all"):
                self.pending_rule = None
                self.overlay_rules.setdefault("user_pools", {})[uid] = {
                    "word_mappings": {},
                    "aliases": {},
                    "if_else_rules": [],
                }
                self._save_overlay()
                try:
                    from backend.automation_engine import clear_compound_rules_scoped

                    clear_compound_rules_scoped(target_owner_id=uid)
                except Exception:
                    pass

            spoken_t2 = {
                "timers": "Đã reset đặt thời gian riêng của bạn.",
                "rules": "Đã reset bể lệnh riêng của bạn.",
                "all": "Đã reset toàn bộ lệnh và hẹn giờ riêng của bạn.",
            }[norm_scope]
            detail_t2 = f"Đã xóa cài đặt ({norm_scope}) trong bể riêng của {uname}. Giữ nguyên 100% lệnh và hẹn giờ của Tầng 1 Nguyễn Tuấn Anh và người khác."
            await self.emit({
                "type": "factory_reset_completed",
                "scope": norm_scope,
                "owner_user_id": uid,
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
            try:
                from backend.automation_repo import clear_all_timers_rows

                clear_all_timers_rows()
            except Exception:
                pass

        if norm_scope in ("rules", "all"):
            self.pending_rule = None
            self.factory_rules = ensure_factory_file()
            saved_users = self.users
            self.overlay_rules = self._default_overlay()
            if norm_scope == "rules":
                self.overlay_rules["users"] = saved_users
            self._save_overlay()
            try:
                from backend.automation_repo import clear_all_rules_and_commands

                clear_all_rules_and_commands()
            except Exception:
                pass

        if norm_scope == "all":
            from backend.engine.state_store import TrackedDeviceDict

            def _apply_reset_all(target_root: Any) -> None:
                now_ts = time.time()
                target_root._applying_shared_state_depth = getattr(target_root, "_applying_shared_state_depth", 0) + 1
                target_root._applying_shared_state = True
                try:
                    for extra_k in [k for k in list(target_root.devices.keys()) if k not in DEFAULT_DEVICES]:
                        target_root.devices.pop(extra_k, None)
                    for k, default_v in DEFAULT_DEVICES.items():
                        existing = target_root.devices.get(k)
                        next_ver = (int(existing.get("version", 1) or 1) + 1) if isinstance(existing, dict) else 1
                        if isinstance(existing, TrackedDeviceDict):
                            existing.clear()
                            existing.update(default_v)
                            existing["updated_at"] = now_ts
                            existing["version"] = next_ver
                            existing["last_client_seq"] = 0
                            existing["last_client_ts_ms"] = 0
                            existing["last_client_id"] = ""
                            existing["last_request_id"] = ""
                            existing["last_requested_state"] = str(default_v.get("state", "OFF"))
                            existing["client_seqs"] = {}
                        else:
                            td = TrackedDeviceDict(default_v, updated_at=now_ts, _engine=target_root)
                            td["version"] = next_ver
                            td["last_client_seq"] = 0
                            td["last_client_ts_ms"] = 0
                            td["last_client_id"] = ""
                            td["last_request_id"] = ""
                            td["last_requested_state"] = str(default_v.get("state", "OFF"))
                            td["client_seqs"] = {}
                            target_root.devices[k] = td
                    target_root.server_connected = True
                    target_root.pump_manual_override_off = False
                    target_root.house_mode = "HOME"
                    if hasattr(target_root, "mqtt_bridge") and target_root.mqtt_bridge is not None:
                        target_root.mqtt_bridge.esp8266_status["online"] = True
                        target_root.mqtt_bridge.esp8266_status["power_mode"] = "SERVER_ONLINE_FULL_AI"
                finally:
                    target_root._applying_shared_state_depth = max(
                        0, getattr(target_root, "_applying_shared_state_depth", 1) - 1
                    )
                    target_root._applying_shared_state = target_root._applying_shared_state_depth > 0

            if hasattr(self, "_commit_shared_state_mutation"):
                await self._commit_shared_state_mutation(_apply_reset_all)
            else:
                _apply_reset_all(getattr(self, "_root_engine", self))
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
            "owner_user_id": "tuan_anh",
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

    async def execute_custom_scene(
        self,
        command_id: str,
        *,
        session: Any | None = None,
        source: str = "scene",
    ) -> dict[str, Any]:
        """Thực thi ngữ cảnh / lệnh tùy chỉnh nhiều bước từ SQLite `custom_commands`, tôn trọng RBAC."""
        from backend.automation_repo import (
            GUEST_ONLY_TOGGLE_MSG_VI,
            check_steps_rbac,
            find_custom_command_by_text,
            format_device_action_vi,
            is_custom_query_step,
            list_custom_commands,
        )

        eff_tier = int(getattr(session, "tier", 0) or self.current_tier) if session is not None else int(self.current_tier)
        eff_uid = str(getattr(session, "user_id", "") or self._current_user_id) if session is not None else str(self._current_user_id)
        eff_uname = str(getattr(session, "display_name", "") or self.get_current_user_name()) if session is not None else self.get_current_user_name()
        eff_role = str(getattr(session, "role", "") or self.current_role) if session is not None else self.current_role

        if eff_tier >= 3:
            append_audit_log(
                "SECURITY",
                "scene_rbac_blocked",
                f"Chặn Cấp 3 gọi lệnh custom ({eff_uid}): {GUEST_ONLY_TOGGLE_MSG_VI}",
                user_name=eff_uname,
                tier=eff_tier,
            )
            return {
                "ok": False,
                "rbac_blocked": True,
                "error": GUEST_ONLY_TOGGLE_MSG_VI,
                "exact_spoken_reply": GUEST_ONLY_TOGGLE_MSG_VI,
            }

        all_cmds = list_custom_commands(include_disabled=False)
        target_cmd = next((c for c in all_cmds if c["command_id"] == command_id), None)
        if target_cmd is None:
            target_cmd = find_custom_command_by_text(command_id, owner_user_id=eff_uid)
        if target_cmd is None:
            return {"ok": False, "error": f"Không tìm thấy ngữ cảnh '{command_id}'."}
        if eff_tier >= 2 and str(target_cmd.get("owner_user_id") or "") != eff_uid:
            deny = "Bạn chỉ được sử dụng lệnh tùy chỉnh trong bể riêng của mình."
            append_audit_log(
                "SECURITY",
                "scene_rbac_blocked",
                f"Chặn Cấp 2 ({eff_uid}) chạy lệnh custom của {target_cmd.get('owner_user_id')}",
                user_name=eff_uname,
                tier=eff_tier,
            )
            return {"ok": False, "rbac_blocked": True, "error": deny, "exact_spoken_reply": deny}

        steps = list(target_cmd.get("steps") or [])
        allowed, rbac_err = check_steps_rbac(steps, eff_tier)
        if not allowed:
            await self.emit({
                "type": "rbac_blocked",
                "action": "execute_custom_scene",
                "command_id": target_cmd["command_id"],
                "role": eff_role,
                "reason": rbac_err,
            })
            append_audit_log(
                "SECURITY",
                "scene_rbac_blocked",
                f"Chặn chạy lệnh {target_cmd['phrase']} ({eff_uid}): {rbac_err}",
                user_name=eff_uname,
                tier=eff_tier,
            )
            return {"ok": False, "rbac_blocked": True, "error": rbac_err, "exact_spoken_reply": rbac_err}

        control_steps = [
            s for s in steps
            if not is_custom_query_step(str(s.get("device_id") or ""), str(s.get("action") or ""))
        ]
        query_steps = [
            s for s in steps
            if is_custom_query_step(str(s.get("device_id") or ""), str(s.get("action") or ""))
        ]

        all_results: list[dict[str, Any]] = []
        phrase = str(target_cmd["phrase"])
        for step in control_steps:
            dev_id = str(step.get("device_id") or "")
            act = str(step.get("action") or "")
            if not dev_id or not act:
                continue
            step_res = await self.execute_device_action(
                device_id=dev_id,
                action=act,
                source=f"Scene {phrase} ({source})",
                bypass_rbac=False,
                trigger_chains=True,
                request_tier=eff_tier,
                request_user_name=eff_uname,
                request_role=eff_role,
            )
            all_results.extend(step_res.get("results") or [])
            if step_res.get("rbac_blocked"):
                err_msg = str(step_res.get("error") or step_res.get("exact_spoken_reply") or "Từ chối quyền thiết bị.")
                return {"ok": False, "rbac_blocked": True, "error": err_msg, "exact_spoken_reply": err_msg, "results": all_results}

        query_spoken = ""
        query_data: dict[str, Any] = {}
        if query_steps:
            from backend.voice.vietnamese_policy import execute_custom_command_query_steps

            q_ok, q_rbac, q_err, query_spoken, query_data = execute_custom_command_query_steps(
                query_steps, self, eff_tier
            )
            if not q_ok and q_rbac:
                return {"ok": False, "rbac_blocked": True, "error": q_err, "exact_spoken_reply": q_err, "results": all_results}

        summary = ", ".join(format_device_action_vi(s.get("device_id", ""), s.get("action", "")) for s in steps)
        if control_steps and query_spoken:
            ctrl_summary = ", ".join(format_device_action_vi(s.get("device_id", ""), s.get("action", "")) for s in control_steps)
            spoken = f"Đã chạy ngữ cảnh {phrase}: {ctrl_summary}. {query_spoken}"
        elif query_spoken:
            spoken = query_spoken
        else:
            spoken = f"Đã chạy ngữ cảnh {phrase}: {summary}."
        append_audit_log(
            "AUTOMATION",
            "scene_executed",
            f"Chạy lệnh {phrase} ({summary})",
            user_name=eff_uname,
            tier=eff_tier,
        )
        scene_owner_id = str(target_cmd.get("owner_user_id") or "").strip()
        scene_owner_tier = int(target_cmd.get("owner_tier") or 1)
        await self.emit({
            "type": "scene_executed",
            "command_id": target_cmd["command_id"],
            "phrase": phrase,
            "steps": steps,
            "owner_user_id": scene_owner_id,
            "owner_tier": scene_owner_tier,
            "actor_user_id": eff_uid,
            "executed_by_user_id": eff_uid,
            "user_id": eff_uid,
            "message": spoken,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "command_id": target_cmd["command_id"],
            "phrase": phrase,
            "steps": steps,
            "results": all_results,
            **query_data,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời CỰC NGẮN GỌN đúng nguyên văn câu này: '{spoken}'",
            "message": spoken,
        }

    def sync_automation_pools_from_sqlite(self, *, emit_snapshot: bool = False) -> None:
        """Đồng bộ nhẹ revision khi automation SQLite (schedules/rules/custom_commands) thay đổi."""
        try:
            root = getattr(self, "_root_engine", self)
            if hasattr(root, "persist_to_shared_store"):
                root.persist_to_shared_store()
        except Exception:
            pass
        if emit_snapshot:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot(sync=False)}))
            except Exception:
                pass
