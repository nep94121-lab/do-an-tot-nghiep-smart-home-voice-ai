"""Module simulator.engine.timers_pool: Quản lý Bể 1 (Bể Hẹn Giờ 1 lần hoặc lặp lại, bảo vệ lịch Tầng 1)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from simulator.engine.constants_and_time import (
    ACTION_TO_STATE,
    REPEAT_INTERVAL_SECONDS,
    REPEAT_VI_LABELS,
    detect_repeat_mode,
    parse_vn_clock_and_date,
)


class EngineTimersMixin:
    """Mixin xử lý Bể 1 (Timer Pool): đặt lịch linh hoạt AM/PM/đếm ngược, sửa/hủy và chống ghi đè Tầng 1."""

    devices: dict[str, dict[str, Any]]
    active_timers: dict[str, dict[str, Any]]
    _timer_tasks: dict[str, asyncio.Task]
    _timer_seq: int
    _current_user_id: str

    def _check_t1_timer_conflict(self, device_id: str, new_fire_at: float) -> str | None:
        """Kiểm tra xem cấp dưới có đặt lệnh vướng vào khung giờ hẹn giờ của Tầng 1 Nguyễn Tuấn Anh hay không."""
        if self.current_tier <= 1 or self.system_policies.get("tier2_can_override_tier1", False):
            return None
        target_dev_id = "living_room_light" if device_id in ("all_lights", "all_devices") else device_id
        for tinfo in self.active_timers.values():
            if tinfo.get("owner_tier", 1) != 1:
                continue
            same_dev = (
                device_id == "all_devices"
                or tinfo.get("raw_target") == "all_devices"
                or tinfo.get("device_id") == target_dev_id
                or tinfo.get("raw_target") == device_id
            )
            if not same_dev:
                continue
            if abs(new_fire_at - tinfo["fire_at"]) <= 1800.0:
                dname = self.devices.get(target_dev_id, {}).get("name", target_dev_id)
                return f"Không thể đặt hẹn giờ: {dname} đang có lịch hẹn giờ của Tầng 1 Nguyễn Tuấn Anh trong khung giờ này."
        return None

    async def schedule_timer_flexible(
        self,
        device_id: str,
        action: str,
        hours: float = 0.0,
        minutes: float = 0.0,
        seconds: float = 0.0,
        vn_time_ampm: str = "",
        vn_date: str = "",
        repeat: str = "once",
        reason: str = "Hẹn giờ giọng nói",
    ) -> dict[str, Any]:
        if self.current_tier >= 3 and not self.system_policies.get("tier3_can_schedule_timer", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) chỉ được gọi lệnh đóng mở cố định, không có quyền hẹn giờ."
            await self.emit({"type": "rbac_blocked", "device_id": device_id, "action": "schedule_timer", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        act_phrase = self._action_device_phrase_vi(device_id, action)
        repeat_mode = detect_repeat_mode(f"{vn_time_ampm} {vn_date} {reason}", repeat)
        rep_vi = REPEAT_VI_LABELS.get(repeat_mode, "")

        if vn_time_ampm and vn_time_ampm.strip():
            parsed = parse_vn_clock_and_date(vn_time_ampm, vn_date, repeat=repeat_mode)
            if not parsed or not parsed.get("slots"):
                return {"ok": False, "error": f"Không hiểu định dạng giờ '{vn_time_ampm}'."}

            slots = parsed["slots"]
            repeat_mode = parsed.get("repeat", repeat_mode)
            rep_vi = parsed.get("repeat_label", rep_vi)
            scheduled_ids: list[str] = []
            for slot in slots:
                res = await self.schedule_action(
                    device_id=device_id,
                    action=action,
                    delay_seconds=slot["delay_seconds"],
                    reason=f"Hẹn lúc {slot['target_vn_time']}",
                    target_vn_time=slot["target_vn_time"],
                    repeat=repeat_mode,
                )
                if not res.get("ok"):
                    return res
                scheduled_ids.append(res["timer_id"])

            rep_part = f" {rep_vi}" if rep_vi else ""
            if parsed["both_ampm"] and len(slots) == 2:
                date_part = f" {parsed['date_label']}" if parsed.get("date_label") else ""
                spoken = f"Đã hẹn {slots[0]['clock_label']} và {slots[1]['clock_label']}{date_part}{rep_part} {act_phrase}."
            else:
                date_part = f" {parsed['date_label']}" if parsed.get("date_label") else ""
                spoken = f"Đã hẹn {slots[0]['clock_label']}{date_part}{rep_part} {act_phrase}."

            return {
                "ok": True,
                "timer_id": scheduled_ids[0],
                "timer_ids": scheduled_ids,
                "both_ampm": parsed["both_ampm"],
                "has_date": parsed["has_date"],
                "repeat": repeat_mode,
                "timer_pool_count": len(self.active_timers),
                "exact_spoken_reply": spoken,
                "instruction_for_ai": f"BẮT BUỘC trả lời CỰC NGẮN GỌN đúng nguyên văn câu này: '{spoken}'",
                "message": spoken,
            }

        delay_seconds = float(hours) * 3600.0 + float(minutes) * 60.0 + float(seconds)
        if delay_seconds <= 0:
            delay_seconds = 5.0
        dur_str = self.format_duration_vi(delay_seconds)
        res = await self.schedule_action(
            device_id=device_id,
            action=action,
            delay_seconds=delay_seconds,
            reason=f"Đếm ngược {dur_str}" + (f" ({rep_vi})" if rep_vi else ""),
            target_vn_time=f"({rep_vi})" if rep_vi else "",
            repeat=repeat_mode,
        )
        if not res.get("ok"):
            return res

        rep_part = f" ({rep_vi})" if rep_vi else ""
        spoken = f"Đã hẹn {dur_str} nữa{rep_part} {act_phrase}."
        return {
            "ok": True,
            "timer_id": res["timer_id"],
            "timer_ids": [res["timer_id"]],
            "both_ampm": False,
            "has_date": False,
            "repeat": repeat_mode,
            "timer_pool_count": len(self.active_timers),
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời CỰC NGẮN GỌN đúng nguyên văn câu này (TUYỆT ĐỐI KHÔNG đọc kèm giờ đồng hồ hay ngày): '{spoken}'",
            "message": spoken,
        }

    async def schedule_action(
        self,
        device_id: str,
        action: str,
        delay_seconds: float,
        reason: str = "Hẹn giờ giọng nói",
        bypass_rbac: bool = False,
        trigger_chains: bool = True,
        target_vn_time: str = "",
        repeat: str = "once",
    ) -> dict[str, Any]:
        if device_id not in self.devices and device_id not in ("all_lights", "all_devices"):
            return {"ok": False, "error": f"Thiết bị '{device_id}' không hợp lệ."}

        delay_seconds = max(1.0, min(float(delay_seconds), 365.0 * 86400.0))
        new_fire_at = time.time() + delay_seconds

        if not bypass_rbac:
            if self.current_tier >= 3 and not self.system_policies.get("tier3_can_schedule_timer", False):
                msg = "Từ chối truy cập! Cấp khách (Tầng 3) chỉ được đóng mở cố định, không có quyền hẹn giờ."
                await self.emit({"type": "rbac_blocked", "device_id": device_id, "action": action, "role": self.current_role, "reason": msg})
                return {"ok": False, "error": msg, "exact_spoken_reply": msg}

            req_role = "CHILD_GUEST" if self.system_policies.get("tier3_can_schedule_timer", False) else "MEMBER"
            allowed, msg = self.check_permission(req_role)
            if not allowed:
                await self.emit({"type": "rbac_blocked", "device_id": device_id, "action": action, "role": self.current_role, "reason": msg})
                return {"ok": False, "error": msg, "exact_spoken_reply": msg}

            conflict_err = self._check_t1_timer_conflict(device_id, new_fire_at)
            if conflict_err:
                await self.emit({"type": "rbac_blocked", "device_id": device_id, "action": action, "role": self.current_role, "reason": conflict_err})
                return {"ok": False, "error": conflict_err, "exact_spoken_reply": conflict_err}

        repeat_mode = repeat if repeat in REPEAT_VI_LABELS else "once"

        self._timer_seq += 1
        tid = f"timer_{self._timer_seq}"
        target_dev_id = "living_room_light" if device_id in ("all_lights", "all_devices") else device_id
        self.active_timers[tid] = {
            "id": tid,
            "device_id": target_dev_id,
            "raw_target": device_id,
            "action": action,
            "delay_seconds": delay_seconds,
            "fire_at": new_fire_at,
            "target_vn_time": target_vn_time,
            "repeat": repeat_mode,
            "reason": reason,
            "owner_id": self._current_user_id,
            "owner_name": self.get_current_user_name(),
            "owner_tier": self.current_tier,
        }

        async def _runner() -> None:
            try:
                cur_wait = delay_seconds
                while True:
                    await asyncio.sleep(cur_wait)
                    if repeat_mode == "once":
                        self.active_timers.pop(tid, None)
                        self._timer_tasks.pop(tid, None)
                        await self.execute_device_action(
                            device_id=device_id,
                            action=action,
                            source=f"timer ({reason})",
                            bypass_rbac=True,
                            trigger_chains=trigger_chains,
                        )
                        break

                    await self.execute_device_action(
                        device_id=device_id,
                        action=action,
                        source=f"timer lặp ({reason})",
                        bypass_rbac=True,
                        trigger_chains=trigger_chains,
                    )
                    cur_wait = REPEAT_INTERVAL_SECONDS.get(repeat_mode, 86400.0)
                    if tid in self.active_timers:
                        self.active_timers[tid]["delay_seconds"] = cur_wait
                        self.active_timers[tid]["fire_at"] = time.time() + cur_wait
                        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
                    else:
                        break
            except asyncio.CancelledError:
                self.active_timers.pop(tid, None)
                self._timer_tasks.pop(tid, None)
                raise

        self._timer_tasks[tid] = asyncio.create_task(_runner())
        await self.emit({
            "type": "timer_scheduled",
            "timer_id": tid,
            "device_id": device_id,
            "action": action,
            "delay_seconds": delay_seconds,
            "target_vn_time": target_vn_time,
            "repeat": repeat_mode,
            "reason": reason,
            "owner_id": self._current_user_id,
            "owner_tier": self.current_tier,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        act_phrase = self._action_device_phrase_vi(device_id, action)
        if target_vn_time:
            spoken = f"Đã hẹn {target_vn_time} {act_phrase}."
        else:
            dur_str = self.format_duration_vi(delay_seconds)
            spoken = f"Đã hẹn {dur_str} nữa {act_phrase}."
        return {
            "ok": True,
            "timer_id": tid,
            "repeat": repeat_mode,
            "timer_pool_count": len(self.active_timers),
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời CỰC NGẮN GỌN đúng nguyên văn câu này: '{spoken}'",
            "message": spoken,
        }

    async def update_or_cancel_timer(
        self,
        device_id: str,
        operation: str = "modify",
        new_action: str = "",
        hours: float = 0.0,
        minutes: float = 0.0,
        seconds: float = 0.0,
        vn_time_ampm: str = "",
        vn_date: str = "",
        repeat: str = "once",
    ) -> dict[str, Any]:
        if self.current_tier >= 3 and not self.system_policies.get("tier3_can_schedule_timer", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền sửa hoặc hủy hẹn giờ."
            await self.emit({"type": "rbac_blocked", "device_id": device_id, "action": "update_or_cancel_timer", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        all_matched = [
            tid
            for tid, info in self.active_timers.items()
            if device_id in ("all_devices", info["device_id"], info["raw_target"])
        ]
        if not all_matched and len(self.active_timers) == 1:
            all_matched = list(self.active_timers.keys())

        if self.current_tier == 1 or self.system_policies.get("tier2_can_override_tier1", False):
            matched_tids = all_matched
        else:
            own_tids = [tid for tid in all_matched if self.active_timers[tid].get("owner_id") == self._current_user_id]
            t1_tids = [tid for tid in all_matched if self.active_timers[tid].get("owner_tier", 1) == 1]
            if not own_tids and t1_tids:
                msg = "Không thể sửa hoặc hủy lịch hẹn giờ của Tầng 1 Nguyễn Tuấn Anh."
                await self.emit({"type": "rbac_blocked", "device_id": device_id, "action": "update_or_cancel_timer", "role": self.current_role, "reason": msg})
                return {"ok": False, "error": msg, "exact_spoken_reply": msg}
            if not own_tids and all_matched:
                msg = "Bạn chỉ được phép sửa hoặc hủy lịch hẹn giờ do chính bạn đặt."
                await self.emit({"type": "rbac_blocked", "device_id": device_id, "action": "update_or_cancel_timer", "role": self.current_role, "reason": msg})
                return {"ok": False, "error": msg, "exact_spoken_reply": msg}
            matched_tids = own_tids

        if not matched_tids:
            if operation == "cancel":
                return {"ok": False, "error": "Trong Bể hẹn giờ hiện không có lịch nào khớp để hủy."}
            act = new_action or "turn_off"
            return await self.schedule_timer_flexible(
                device_id=device_id if device_id in self.devices else "living_room_light",
                action=act,
                hours=hours,
                minutes=minutes,
                seconds=seconds,
                vn_time_ampm=vn_time_ampm,
                vn_date=vn_date,
                repeat=repeat,
                reason="Tạo/Sửa hẹn giờ",
            )

        old_info = self.active_timers[matched_tids[-1]]
        target_dev = old_info["raw_target"]
        target_act = new_action if new_action in ACTION_TO_STATE else old_info["action"]

        for tid in matched_tids:
            t = self._timer_tasks.pop(tid, None)
            if t:
                t.cancel()
            self.active_timers.pop(tid, None)

        if operation == "cancel":
            await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
            dev_n = self.devices.get(target_dev, {}).get("name", target_dev).lower()
            spoken = f"Đã hủy hẹn giờ {dev_n}."
            return {
                "ok": True,
                "timer_pool_count": len(self.active_timers),
                "exact_spoken_reply": spoken,
                "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn: '{spoken}'",
                "message": spoken,
            }

        return await self.schedule_timer_flexible(
            device_id=target_dev,
            action=target_act,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            vn_time_ampm=vn_time_ampm,
            vn_date=vn_date,
            repeat=repeat,
            reason="Đã sửa hẹn giờ",
        )
