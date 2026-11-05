"""Module simulator.engine.voice_rbac_mixin: Quản lý Chính sách Hệ thống, Phân quyền 3 Tầng (RBAC) và Thu âm Cấp quyền Giọng nói."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from simulator.engine.constants_and_time import (
    DEFAULT_USERS,
    DEVICE_ID_ALIASES,
    ROLE_LEVELS,
    get_vn_now,
)
from simulator.voice_config import (
    OWNER_DISPLAY_NAME,
    OWNER_EMAIL,
    OWNER_ID,
    ROLE_MAP,
    USER_ROLE_MAP,
)

UNKNOWN_REJECTION_REASON = (
    "🚫 NGƯỜI LẠ / VAI TRÒ KHÔNG XÁC ĐỊNH: Từ chối toàn bộ quyền điều khiển thiết bị!"
)
UNKNOWN_SPOKEN_REPLY = (
    "Xin lỗi, hệ thống không nhận diện được danh tính của bạn nên từ chối điều khiển thiết bị."
)


class PermissionCheckResult(dict):
    """Dict kết quả kiểm tra quyền RBAC tương thích kép:
    - Truy cập như dict: res['allowed'], res['reason'], res['tier'], res['role'], res == {...}
    - Unpack 2 phần tử: allowed, reason = eng.check_device_permission(...)
    """

    def __iter__(self):
        yield bool(self.get("allowed", False))
        yield str(self.get("reason", ""))

    def __getitem__(self, key: Any) -> Any:
        if key == 0:
            return bool(self.get("allowed", False))
        if key == 1:
            return str(self.get("reason", ""))
        return super().__getitem__(key)


class EngineVoiceRbacMixin:
    """Mixin quản lý system_policies, kiểm tra phân quyền thiết bị theo 3 Tầng và quy trình thu âm cấp quyền giọng nói."""

    devices: dict[str, dict[str, Any]]
    overlay_rules: dict[str, Any]
    users: dict[str, dict[str, Any]]
    _current_user_id: str
    _current_role: str
    pending_voice_enrollment: dict[str, Any] | None
    mqtt_bridge: Any

    @property
    def system_policies(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "tier3_can_schedule_timer": False,
            "tier3_can_custom_rules": False,
            "tier3_can_grant_revoke": False,
            "tier2_can_grant_tier2": False,
            "tier2_can_revoke_same_tier": False,
            "tier2_can_override_tier1": False,
            "require_rule_confirmation": True,
            "require_reset_confirmation": True,
            "enrollment_signal_device_id": "living_room_light",
            "enrollment_duration_seconds": 5,
            "device_min_tiers": {
                "main_door": 1,
                "living_room_light": 3,
                "bedroom_light": 3,
                "fan": 3,
                "ac": 2,
                "alarm_siren": 1,
                "garden_pump": 2,
            },
            "custom_system_directives": [],
        }
        pol = self.overlay_rules.setdefault("system_policies", {})
        if not isinstance(pol, dict):
            pol = {}
            self.overlay_rules["system_policies"] = pol
        for k, v in defaults.items():
            if k not in pol:
                pol[k] = dict(v) if isinstance(v, dict) else (list(v) if isinstance(v, list) else v)
        if not isinstance(pol.get("device_min_tiers"), dict):
            pol["device_min_tiers"] = dict(defaults["device_min_tiers"])
        else:
            for dk, dv in defaults["device_min_tiers"].items():
                pol["device_min_tiers"].setdefault(dk, dv)
        if not isinstance(pol.get("custom_system_directives"), list):
            pol["custom_system_directives"] = []
        return pol

    @property
    def query_permission_mode(self) -> str:
        return str(self.overlay_rules.get("query_permission_mode", "tier_restricted"))

    async def set_query_permission_policy(self, mode: str) -> dict[str, Any]:
        """Thay đổi quy tắc phân quyền hỏi đáp (CHỈ Cấp 1 Nguyễn Tuấn Anh mới có quyền thay đổi)."""
        if self.current_tier > 1:
            msg = "Từ chối truy cập! Chỉ Cấp 1 Nguyễn Tuấn Anh mới có quyền thay đổi quy định trả lời câu hỏi của hệ thống."
            await self.emit({"type": "rbac_blocked", "action": "set_query_permission_policy", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        m_low = (mode or "").strip().lower()
        if m_low in ("open_all", "all", "everyone", "tat_ca", "open", "true", "allow"):
            norm_mode = "open_all"
            spoken = "Đã mở quyền hỏi: Tất cả các cấp đều được trả lời mọi thông tin."
        else:
            norm_mode = "tier_restricted"
            spoken = "Đã giới hạn quyền hỏi: Từng cấp chỉ được trả lời trong phạm vi quyền của cấp đó."

        self.overlay_rules["query_permission_mode"] = norm_mode
        self._save_overlay()
        await self.emit({
            "type": "query_policy_updated",
            "query_permission_mode": norm_mode,
            "message": spoken,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "query_permission_mode": norm_mode,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
            "message": spoken,
        }

    async def admin_update_system_policy(
        self,
        policy_key: str,
        policy_value: str = "",
        target_device_id: str = "",
    ) -> dict[str, Any]:
        """Cho phép Admin Cấp 1 (Nguyễn Tuấn Anh) sửa BẤT KỲ quy tắc hệ thống, quyền hạn của Cấp 2/Cấp 3."""
        if self.current_tier > 1:
            msg = "Từ chối truy cập! Chỉ Admin Cấp 1 Nguyễn Tuấn Anh mới có quyền sửa quy tắc và phân quyền hệ thống bằng giọng nói."
            await self.emit({"type": "rbac_blocked", "action": "admin_update_system_policy", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        key = (policy_key or "").strip().lower()
        val_str = (policy_value or "").strip()
        val_low = val_str.lower()
        is_true = val_low in ("true", "1", "yes", "on", "allow", "open", "open_all", "cho_phep", "bat", "co")
        pol = self.system_policies

        if key == "query_permission_mode":
            return await self.set_query_permission_policy(val_str)

        if key == "tier3_can_schedule_timer":
            pol["tier3_can_schedule_timer"] = is_true
            spoken = (
                "Đã cập nhật luật: Cho phép Cấp 3 (Khách) được đặt và hủy hẹn giờ."
                if is_true
                else "Đã cập nhật luật: Cấm Cấp 3 (Khách) hẹn giờ."
            )
        elif key == "tier3_can_custom_rules":
            pol["tier3_can_custom_rules"] = is_true
            spoken = (
                "Đã cập nhật luật: Cho phép Cấp 3 (Khách) tùy chỉnh khẩu lệnh và đặt luật IF-ELSE."
                if is_true
                else "Đã cập nhật luật: Cấp 3 (Khách) chỉ được gọi lệnh đóng mở cố định."
            )
        elif key == "tier3_can_grant_revoke":
            pol["tier3_can_grant_revoke"] = is_true
            spoken = (
                "Đã cập nhật luật: Cho phép Cấp 3 được cấp và hủy quyền Cấp 3."
                if is_true
                else "Đã cập nhật luật: Cấm Cấp 3 cấp hoặc hủy quyền của bất kỳ ai."
            )
        elif key == "tier2_can_grant_tier2":
            pol["tier2_can_grant_tier2"] = is_true
            spoken = (
                "Đã cập nhật luật: Cho phép Cấp 2 được cấp quyền cho cả Cấp 2 và Cấp 3."
                if is_true
                else "Đã cập nhật luật: Cấp 2 chỉ được cấp quyền cho Cấp 3."
            )
        elif key == "tier2_can_revoke_same_tier":
            pol["tier2_can_revoke_same_tier"] = is_true
            spoken = (
                "Đã cập nhật luật: Cho phép Cấp 2 được hủy quyền cùng cấp Cấp 2."
                if is_true
                else "Đã cập nhật luật: Cấm Cấp 2 hủy quyền cùng cấp."
            )
        elif key == "tier2_can_override_tier1":
            pol["tier2_can_override_tier1"] = is_true
            spoken = (
                "Đã cập nhật luật: Cho phép Cấp 2 điều chỉnh lịch hẹn và luật của Cấp 1."
                if is_true
                else "Đã cập nhật luật: Bảo vệ tuyệt đối lịch hẹn và luật của Cấp 1 Nguyễn Tuấn Anh."
            )
        elif key == "require_rule_confirmation":
            pol["require_rule_confirmation"] = is_true
            spoken = (
                "Đã cập nhật luật: Khi xét luật mới phải hỏi xác nhận trước khi lưu."
                if is_true
                else "Đã cập nhật luật: Khi xét luật mới sẽ lưu thẳng ngay lập tức, không cần hỏi xác nhận."
            )
        elif key == "require_reset_confirmation":
            pol["require_reset_confirmation"] = is_true
            spoken = (
                "Đã cập nhật luật: Khi reset hệ thống phải hỏi xác nhận trước."
                if is_true
                else "Đã cập nhật luật: Khi gọi reset sẽ thực thi ngay lập tức không cần hỏi lại."
            )
        elif key == "enrollment_signal_device_id":
            dev_id = target_device_id.strip() or val_str
            if dev_id not in self.devices:
                dev_id = "living_room_light"
            pol["enrollment_signal_device_id"] = dev_id
            dname = self.devices[dev_id]["name"].lower()
            spoken = f"Đã cập nhật luật: Khi thu âm cấp quyền sẽ nháy {dname} làm tín hiệu bắt đầu."
        elif key == "enrollment_duration_seconds":
            try:
                sec = max(3, min(int(float(val_str)), 15))
            except Exception:
                sec = 5
            pol["enrollment_duration_seconds"] = sec
            spoken = f"Đã cập nhật luật: Thời gian thu âm giọng nói cấp quyền là {sec} giây."
        elif key == "device_min_tier":
            dev_id = (target_device_id or "").strip()
            try:
                min_t = max(1, min(int(float(val_str)), 3))
            except Exception:
                min_t = 3
            role_for_tier = ROLE_MAP.get(min_t, "CHILD_GUEST")
            if dev_id in ("all_devices", "all"):
                for dk in self.devices:
                    pol["device_min_tiers"][dk] = min_t
                    self.devices[dk]["min_role"] = role_for_tier
                spoken = f"Đã cập nhật luật: Tất cả thiết bị yêu cầu tối thiểu Cấp {min_t} mới được điều khiển."
            elif dev_id in self.devices:
                pol["device_min_tiers"][dev_id] = min_t
                self.devices[dev_id]["min_role"] = role_for_tier
                dname = self.devices[dev_id]["name"].lower()
                spoken = f"Đã cập nhật luật: Chỉ từ Cấp {min_t} trở lên mới được điều khiển {dname}."
            else:
                return {"ok": False, "error": f"Không tìm thấy thiết bị '{dev_id}'."}
        elif key in ("custom_directive_add", "custom_rule", "add_directive"):
            if not val_str:
                return {"ok": False, "error": "Nội dung quy tắc mới không được để trống."}
            directives: list[str] = pol.setdefault("custom_system_directives", [])
            if val_str not in directives:
                directives.append(val_str)
            spoken = f"Đã ghi nhận quy tắc hệ thống mới: {val_str}."
        elif key in ("custom_directive_remove", "remove_directive", "clear_directives"):
            directives = pol.setdefault("custom_system_directives", [])
            if not val_str or val_low in ("all", "tat_ca", "clear"):
                directives.clear()
                spoken = "Đã xóa toàn bộ các quy tắc hệ thống tùy chỉnh."
            else:
                pol["custom_system_directives"] = [
                    d for d in directives if val_low not in d.lower()
                ]
                spoken = f"Đã xóa quy tắc hệ thống khớp với '{val_str}'."
        else:
            rule_text = f"{policy_key}: {val_str}".strip(": ")
            directives = pol.setdefault("custom_system_directives", [])
            if rule_text and rule_text not in directives:
                directives.append(rule_text)
            spoken = f"Đã cập nhật quy tắc hệ thống: {rule_text}."

        self._save_overlay()
        await self.emit({
            "type": "system_policy_updated",
            "policy_key": key,
            "policy_value": val_str,
            "system_policies": pol,
            "message": spoken,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "policy_key": key,
            "system_policies": pol,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
            "message": spoken,
        }

    def _init_users(self) -> dict[str, dict[str, Any]]:
        users_map = {k: dict(v) for k, v in DEFAULT_USERS.items()}
        saved_users = self.overlay_rules.get("users", {})
        if isinstance(saved_users, dict):
            for uid, uinfo in saved_users.items():
                if isinstance(uinfo, dict):
                    users_map[uid] = dict(uinfo)
        users_map[OWNER_ID] = dict(DEFAULT_USERS[OWNER_ID])
        self.overlay_rules["users"] = users_map
        return users_map

    @property
    def current_user_id(self) -> str:
        return self._current_user_id

    @property
    def current_tier(self) -> int:
        if self._current_role == "UNKNOWN" or str(self._current_user_id).strip().lower() == "unknown":
            return 99
        u = self.users.get(self._current_user_id)
        if u:
            if not u.get("active", True):
                return 99
            return int(u.get("tier", 99))
        if self._current_role == "ADMIN":
            return 1
        if self._current_role == "MEMBER":
            return 2
        if self._current_role == "CHILD_GUEST":
            return 3
        return 99

    def get_current_user_name(self) -> str:
        if self._current_role == "UNKNOWN" or str(self._current_user_id).strip().lower() == "unknown":
            return "Người lạ"
        u = self.users.get(self._current_user_id)
        if u:
            return u.get("name", self._current_user_id)
        return "Người lạ"

    @property
    def current_role(self) -> str:
        return self._current_role

    @current_role.setter
    def current_role(self, val: str | None) -> None:
        v = str(val or "").strip()
        v_low = v.lower()
        if not v or v_low in ("unknown", "stranger", "stranger_1", "none", "null", "intruder", "unauthorized"):
            self._current_user_id = "unknown"
            self._current_role = "UNKNOWN"
            return

        role_alias_map = {
            "member_1": USER_ROLE_MAP.get(2, "thanh_vien_a"),
            "member_2": "thanh_vien_b",
            "guest_1": USER_ROLE_MAP.get(3, "khach_c"),
            "guest_2": "khach_d",
            "stranger_1": "unknown",
        }
        if v_low in role_alias_map:
            v_low = role_alias_map[v_low]
            if v_low == "unknown":
                self._current_user_id = "unknown"
                self._current_role = "UNKNOWN"
                return
        if hasattr(self, "users") and v_low in self.users:
            u = self.users[v_low]
            self._current_user_id = v_low
            self._current_role = u["role"] if u.get("active", True) else "UNKNOWN"
            return
        if hasattr(self, "users"):
            for uid, u in self.users.items():
                if u.get("name", "").strip().lower() == v_low:
                    self._current_user_id = uid
                    self._current_role = u["role"] if u.get("active", True) else "UNKNOWN"
                    return
        r = v.upper()
        if r in ("ADMIN", "MEMBER", "CHILD_GUEST"):
            self._current_role = r
            if r == "ADMIN":
                self._current_user_id = OWNER_ID
            elif r == "MEMBER":
                if not hasattr(self, "users") or self.users.get(self._current_user_id, {}).get("tier") != 2:
                    self._current_user_id = USER_ROLE_MAP.get(2, "thanh_vien_a")
            elif r == "CHILD_GUEST":
                if not hasattr(self, "users") or self.users.get(self._current_user_id, {}).get("tier") != 3:
                    self._current_user_id = USER_ROLE_MAP.get(3, "khach_c")
            return
        self._current_user_id = "unknown"
        self._current_role = "UNKNOWN"

    def set_active_user(self, user_or_role: str | None) -> dict[str, Any]:
        self.current_role = user_or_role
        u = self.users.get(self._current_user_id, {
            "id": self._current_user_id,
            "name": self.get_current_user_name(),
            "tier": self.current_tier,
            "role": self._current_role,
            "active": self._current_role != "UNKNOWN",
        })
        return {
            "ok": True,
            "user_id": self._current_user_id,
            "user_name": u.get("name", self._current_user_id),
            "tier": self.current_tier,
            "role": self._current_role,
            "active": bool(u.get("active", True)) and self._current_role != "UNKNOWN",
        }

    def check_permission(self, required_role: str) -> tuple[bool, str]:
        u = self.users.get(self._current_user_id)
        if u and not u.get("active", True):
            return (
                False,
                f"Từ chối truy cập! Quyền của {u.get('name', self._current_user_id)} đã bị hủy.",
            )
        user_lvl = ROLE_LEVELS.get(self.current_role, 0)
        req_lvl = ROLE_LEVELS.get(required_role, 3)
        if user_lvl < req_lvl:
            return (
                False,
                f"Từ chối truy cập! Cấp hiện tại ({self.get_current_user_name()} - Tầng {self.current_tier}) không đủ quyền.",
            )
        return True, "OK"

    def _check_custom_directive_device_lock(self, dev_id: str) -> tuple[bool, str]:
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
            if "cấp 3" in d_low and "cấp 2" not in d_low and self.current_tier < 3:
                continue
            if "cấp 2" in d_low and "cấp 3" not in d_low and self.current_tier != 2:
                continue
            if self.current_tier == 1 and ("cấp 2" in d_low or "cấp 3" in d_low or "khách" in d_low):
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

    def check_device_permission(self, dev_id: str) -> PermissionCheckResult:
        if (
            self._current_role == "UNKNOWN"
            or str(self._current_user_id).strip().lower() == "unknown"
            or self.current_tier not in (1, 2, 3)
        ):
            return PermissionCheckResult({
                "allowed": False,
                "reason": UNKNOWN_REJECTION_REASON,
                "tier": 99,
                "role": "UNKNOWN",
            })
        u = self.users.get(self._current_user_id)
        if u and not u.get("active", True):
            return PermissionCheckResult({
                "allowed": False,
                "reason": f"Từ chối truy cập! Quyền của {u.get('name', self._current_user_id)} đã bị hủy.",
                "tier": 99,
                "role": "UNKNOWN",
            })
        canonical_id = DEVICE_ID_ALIASES.get(dev_id, dev_id)
        dev = self.devices.get(canonical_id, {})
        default_tier_map = {"ADMIN": 1, "MEMBER": 2, "CHILD_GUEST": 3}
        fallback_tier = default_tier_map.get(dev.get("min_role", "CHILD_GUEST"), 3)
        min_tier = int(self.system_policies.get("device_min_tiers", {}).get(canonical_id, fallback_tier))
        if self.current_tier > min_tier:
            dname = dev.get("name", dev_id)
            return PermissionCheckResult({
                "allowed": False,
                "reason": f"Từ chối truy cập! Thiết bị {dname} chỉ cho phép từ Cấp {min_tier} trở lên điều khiển.",
                "tier": self.current_tier,
                "role": self._current_role,
            })
        ok_dir, reason_dir = self._check_custom_directive_device_lock(canonical_id)
        if not ok_dir:
            return PermissionCheckResult({
                "allowed": False,
                "reason": reason_dir,
                "tier": self.current_tier,
                "role": self._current_role,
            })
        req_role = ROLE_MAP.get(min_tier, dev.get("min_role", "CHILD_GUEST"))
        ok_perm, reason_perm = self.check_permission(req_role)
        return PermissionCheckResult({
            "allowed": ok_perm,
            "reason": reason_perm,
            "tier": self.current_tier,
            "role": self._current_role,
        })

    def _find_or_slug_user(self, target_name: str) -> tuple[str, dict[str, Any] | None]:
        t_clean = target_name.strip()
        t_low = t_clean.lower()
        if t_low in self.users:
            return t_low, self.users[t_low]
        for uid, uinfo in self.users.items():
            if uinfo.get("name", "").strip().lower() == t_low or uid == t_low:
                return uid, uinfo
            uname_low = uinfo.get("name", "").strip().lower()
            if t_low in uname_low or uname_low in t_low:
                return uid, uinfo
        slug = re.sub(r"[^a-z0-9_]+", "_", t_low).strip("_") or f"user_{int(time.time())}"
        return slug, self.users.get(slug)

    async def blink_signal_light(self, device_id: str = "living_room_light", pulse_sec: float = 0.35) -> None:
        dev = self.devices.get(device_id)
        if not dev:
            return
        await self.mqtt_bridge.publish_enrollment_blink(device_id=device_id, pulse_ms=int(pulse_sec * 1000))
        orig_state = dev["state"]
        flash_state = "OFF" if orig_state == "ON" else "ON"

        dev["state"] = flash_state
        dev["updated_at"] = time.time()
        await self.emit({
            "type": "device_updated",
            "device_id": device_id,
            "device_name": dev["name"],
            "gpio": dev["gpio"],
            "old_state": orig_state,
            "new_state": flash_state,
            "source": "tín hiệu nháy đèn thu âm",
            "timestamp": dev["updated_at"],
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})

        await asyncio.sleep(max(0.15, float(pulse_sec)))

        dev["state"] = orig_state
        dev["updated_at"] = time.time()
        await self.emit({
            "type": "device_updated",
            "device_id": device_id,
            "device_name": dev["name"],
            "gpio": dev["gpio"],
            "old_state": flash_state,
            "new_state": orig_state,
            "source": "tín hiệu nháy đèn thu âm",
            "timestamp": dev["updated_at"],
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})

    async def start_voice_enrollment(
        self,
        target_tier: int = 3,
        target_name: str = "",
        duration_seconds: int = 0,
        duration_sec: int | None = None,
    ) -> dict[str, Any]:
        pol = self.system_policies
        if self.current_tier >= 3 and not pol.get("tier3_can_grant_revoke", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền thu âm cấp quyền cho ai."
            await self.emit({"type": "rbac_blocked", "action": "start_voice_enrollment", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        target_tier = int(target_tier or 3)
        if target_tier not in (2, 3):
            target_tier = 3

        if self.current_tier == 2 and target_tier != 3 and not pol.get("tier2_can_grant_tier2", False):
            msg = "Thành viên Cấp 2 chỉ được phép thu âm cấp quyền cho Cấp 3 (Khách)."
            await self.emit({"type": "rbac_blocked", "action": "start_voice_enrollment", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        default_dur = int(pol.get("enrollment_duration_seconds", 5) or 5)
        raw_dur = duration_sec if duration_sec is not None else (duration_seconds or default_dur)
        dur = max(3, min(int(raw_dur or default_dur), 15))
        sig_dev = str(pol.get("enrollment_signal_device_id", "living_room_light"))
        if sig_dev not in self.devices:
            sig_dev = "living_room_light"
        clean_name = (target_name or "").strip()
        self.pending_voice_enrollment = {
            "step": "RECORDING",
            "target_tier": target_tier,
            "target_name": clean_name,
            "duration_seconds": dur,
            "signal_device_id": sig_dev,
            "granted_by": self._current_user_id,
            "granted_by_tier": self.current_tier,
        }
        tier_label = "Cấp 2 (Thành viên gia đình)" if target_tier == 2 else "Cấp 3 (Khách)"
        spoken = f"Tôi sẽ cấp quyền {tier_label} trong 3, 2, 1. Khi đèn nháy một phát, hãy nói trong {dur} giây để thu âm."
        await self.emit({
            "type": "voice_enrollment_countdown",
            "target_tier": target_tier,
            "target_name": clean_name,
            "duration_seconds": dur,
            "signal_device_id": sig_dev,
            "message": spoken,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "status": "VOICE_ENROLLMENT_COUNTDOWN",
            "target_tier": target_tier,
            "target_name": clean_name,
            "duration_seconds": dur,
            "signal_device_id": sig_dev,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
            "message": spoken,
        }

    async def stage_voice_enrollment_analysis(
        self,
        f0_hz: float,
        centroid_hz: float,
        embedding: list[float],
        duration_sec: float = 5.0,
    ) -> dict[str, Any]:
        pending = self.pending_voice_enrollment or {
            "target_tier": 3,
            "target_name": "",
            "duration_seconds": 5,
            "granted_by": self._current_user_id,
            "granted_by_tier": self.current_tier,
        }
        target_tier = int(pending.get("target_tier", 3))
        target_name = str(pending.get("target_name", "")).strip()

        pending["step"] = "AWAITING_NAME"
        pending["f0_hz"] = f0_hz
        pending["centroid_hz"] = centroid_hz
        pending["embedding"] = embedding
        pending["duration_sec"] = duration_sec
        self.pending_voice_enrollment = pending

        if target_name and target_name.lower() not in ("người mới", "nguoi moi", "khách mới", "thành viên mới"):
            return await self.finalize_voice_enrollment(target_name=target_name, target_tier=target_tier)

        tier_label = "Cấp 2 (Thành viên gia đình)" if target_tier == 2 else "Cấp 3 (Khách)"
        spoken = (
            f"Đã thu âm đủ và đã phân tích xong giọng nói (tần số {f0_hz} Hz), "
            f"người này sẽ được cấp quyền {tier_label}. Người ấy tên là gì?"
        )
        await self.emit({
            "type": "voice_enrollment_analyzed",
            "f0_hz": f0_hz,
            "centroid_hz": centroid_hz,
            "target_tier": target_tier,
            "message": spoken,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "status": "VOICE_ENROLLMENT_ANALYZED_AWAITING_NAME",
            "f0_hz": f0_hz,
            "centroid_hz": centroid_hz,
            "target_tier": target_tier,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC nói đúng câu: '{spoken}'",
            "message": spoken,
        }

    async def finalize_voice_enrollment(self, target_name: str, target_tier: int = 0) -> dict[str, Any]:
        clean_name = (target_name or "").strip()
        if not clean_name:
            return {"ok": False, "error": "Vui lòng cho biết tên của người được cấp quyền."}

        pending = self.pending_voice_enrollment or {}
        tier = int(target_tier or pending.get("target_tier", 3))
        if tier not in (2, 3):
            tier = 3

        res = await self.grant_user_permission(target_name=clean_name, target_tier=tier)
        if not res.get("ok"):
            return res

        f0_hz = pending.get("f0_hz", 185.0)
        centroid_hz = pending.get("centroid_hz", 1520.0)
        embedding = pending.get("embedding", [0.15] * 26)
        self.pending_voice_enrollment = None

        user_obj = res["target_user"]
        user_obj["voice_f0_hz"] = f0_hz
        user_obj["voice_centroid_hz"] = centroid_hz
        self._save_overlay()

        tier_label = "Cấp 2 (Thành viên gia đình)" if tier == 2 else "Cấp 3 (Khách)"
        spoken = f"Đã lưu giọng nói (tần số {f0_hz} Hz) và cấp quyền {tier_label} cho {user_obj['name']}."
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "status": "VOICE_ENROLLMENT_COMPLETED",
            "user_id": user_obj["id"],
            "target_name": user_obj["name"],
            "target_tier": tier,
            "target_user": user_obj,
            "f0_hz": f0_hz,
            "centroid_hz": centroid_hz,
            "embedding": embedding,
            "voice_profile": {
                "f0_hz": f0_hz,
                "centroid_hz": centroid_hz,
                "embedding": embedding,
            },
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
            "message": spoken,
        }

    async def grant_user_permission(
        self, target_name: str, target_tier: int = 3, tier: int | None = None
    ) -> dict[str, Any]:
        if tier is not None:
            target_tier = int(tier)
        pol = self.system_policies
        if self.current_tier >= 3 and not pol.get("tier3_can_grant_revoke", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền cấp quyền cho bất kỳ ai."
            await self.emit({"type": "rbac_blocked", "action": "grant_user_permission", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        target_tier = int(target_tier)
        if target_tier not in (2, 3):
            target_tier = 3

        if self.current_tier == 2 and target_tier != 3 and not pol.get("tier2_can_grant_tier2", False):
            msg = "Thành viên Tầng 2 chỉ được cấp quyền cho Khách (Tầng 3), không được cấp quyền Tầng 1 hay Tầng 2."
            await self.emit({"type": "rbac_blocked", "action": "grant_user_permission", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if self.current_tier >= 3 and target_tier != 3:
            msg = "Cấp khách (Tầng 3) chỉ được phép cấp quyền Tầng 3."
            await self.emit({"type": "rbac_blocked", "action": "grant_user_permission", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        uid, existing = self._find_or_slug_user(target_name)
        if uid == OWNER_ID:
            msg = f"{OWNER_DISPLAY_NAME} đã là Admin tối cao Tầng 1."
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if (
            existing
            and existing.get("granted_by_tier") == 1
            and existing.get("active", True)
            and self.current_tier > 1
            and not pol.get("tier2_can_override_tier1", False)
        ):
            msg = f"Không thể sửa quyền: {existing['name']} do Tầng 1 Nguyễn Tuấn Anh trực tiếp cấp quyền."
            await self.emit({"type": "rbac_blocked", "action": "grant_user_permission", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        role_code = "MEMBER" if target_tier == 2 else "CHILD_GUEST"
        disp_name = existing["name"] if existing else target_name.strip()
        self.users[uid] = {
            "id": uid,
            "name": disp_name,
            "tier": target_tier,
            "role": role_code,
            "granted_by": self._current_user_id,
            "granted_by_name": f"{self.get_current_user_name()} (Tầng {self.current_tier})",
            "granted_by_tier": self.current_tier,
            "active": True,
        }
        if target_tier == 2:
            self._get_user_pool(uid)
        self._save_overlay()

        tier_label = "Tầng 2 (Thành viên gia đình)" if target_tier == 2 else "Tầng 3 (Khách)"
        spoken = f"Đã cấp quyền {tier_label} cho {disp_name}."
        await self.emit({
            "type": "permission_granted",
            "target_user": self.users[uid],
            "by_user": self._current_user_id,
            "by_tier": self.current_tier,
            "message": spoken,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "target_user": self.users[uid],
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
            "message": spoken,
        }

    async def revoke_user_permission(self, target_name: str) -> dict[str, Any]:
        pol = self.system_policies
        if self.current_tier >= 3 and not pol.get("tier3_can_grant_revoke", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền hủy quyền của bất kỳ ai."
            await self.emit({"type": "rbac_blocked", "action": "revoke_user_permission", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        uid, existing = self._find_or_slug_user(target_name)
        if not existing:
            msg = f"Không tìm thấy người dùng '{target_name}'."
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if uid == OWNER_ID or existing.get("tier") == 1:
            msg = f"Không ai được phép hủy quyền của Tầng 1 {OWNER_DISPLAY_NAME}."
            await self.emit({"type": "rbac_blocked", "action": "revoke_user_permission", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if self.current_tier >= 2:
            if existing.get("granted_by_tier") == 1 and not pol.get("tier2_can_override_tier1", False):
                msg = f"Không thể hủy quyền: {existing['name']} được Tầng 1 Nguyễn Tuấn Anh cấp quyền, ngoài Tầng 1 ra không ai được phép hủy."
                await self.emit({"type": "rbac_blocked", "action": "revoke_user_permission", "role": self.current_role, "reason": msg})
                return {"ok": False, "error": msg, "exact_spoken_reply": msg}
            if self.current_tier == 2 and existing.get("tier") == 2 and not pol.get("tier2_can_revoke_same_tier", False):
                msg = f"Không thể hủy quyền: Thành viên Tầng 2 không được phép hủy quyền cùng cấp ({existing['name']})."
                await self.emit({"type": "rbac_blocked", "action": "revoke_user_permission", "role": self.current_role, "reason": msg})
                return {"ok": False, "error": msg, "exact_spoken_reply": msg}
            if self.current_tier >= 3 and existing.get("tier") < 3:
                msg = f"Không thể hủy quyền của cấp cao hơn ({existing['name']})."
                await self.emit({"type": "rbac_blocked", "action": "revoke_user_permission", "role": self.current_role, "reason": msg})
                return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        existing["active"] = False
        existing["role"] = "UNKNOWN"
        self._save_overlay()

        spoken = f"Đã hủy quyền của {existing['name']}."
        await self.emit({
            "type": "permission_revoked",
            "target_user": existing,
            "by_user": self._current_user_id,
            "by_tier": self.current_tier,
            "message": spoken,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "target_user": existing,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
            "message": spoken,
        }
