"""Module simulator.engine.timers_pool: Quản lý Bể 1 (Bể Hẹn Giờ 1 lần hoặc lặp lại, bảo vệ lịch Tầng 1)."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from simulator.engine.audit_logger import append_audit_log
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
        """ADDENDUM D: Kiểm tra xung đột ±60s trên mọi thiết bị với toàn bộ hẹn giờ và lịch Cấp 1."""
        from simulator.automation_repo import check_tier1_schedule_conflict

        return check_tier1_schedule_conflict(
            actor_tier=self.current_tier,
            fire_epoch=float(new_fire_at),
            engine=self,
        )

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

        root = getattr(self, "_root_engine", self)
        root._timer_seq = int(getattr(root, "_timer_seq", 0)) + 1
        self._timer_seq = root._timer_seq
        tid = f"timer_{int(time.time() * 1000)}_{root._timer_seq}_{uuid.uuid4().hex[:4]}"
        target_dev_id = "living_room_light" if device_id in ("all_lights", "all_devices") else device_id
        now_ts = time.time()
        lbl = f"{self._action_device_phrase_vi(device_id, action)} ({reason})".strip()
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
            "label": lbl,
            "mode": "clock" if target_vn_time else "countdown",
            "created_at": now_ts,
            "owner_id": self._current_user_id,
            "owner_name": self.get_current_user_name(),
            "owner_tier": self.current_tier,
        }

        try:
            from simulator.automation_repo import upsert_timer_row

            upsert_timer_row(
                timer_id=tid,
                owner_user_id=self._current_user_id,
                owner_tier=self.current_tier,
                owner_name=self.get_current_user_name(),
                device_id=device_id,
                action=action,
                fire_at_epoch=new_fire_at,
                delay_seconds=delay_seconds,
                repeat_rule=repeat_mode,
                schedule_mode="clock" if target_vn_time else "countdown",
                target_time_vn=target_vn_time or f"{int(round(delay_seconds))}s",
                label=lbl,
                status="pending",
            )
        except Exception:
            pass

        self._spawn_timer_task(
            tid=tid,
            device_id=device_id,
            action=action,
            initial_wait=delay_seconds,
            repeat_mode=repeat_mode,
            reason=reason,
            trigger_chains=trigger_chains,
        )
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

    def _spawn_timer_task(
        self,
        *,
        tid: str,
        device_id: str,
        action: str,
        initial_wait: float,
        repeat_mode: str,
        reason: str,
        trigger_chains: bool = True,
    ) -> None:
        async def _runner() -> None:
            try:
                cur_wait = max(0.05, float(initial_wait))
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
                        try:
                            from simulator.automation_repo import update_timer_status

                            update_timer_status(tid, "fired")
                        except Exception:
                            pass
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
                        next_fire = time.time() + cur_wait
                        self.active_timers[tid]["delay_seconds"] = cur_wait
                        self.active_timers[tid]["fire_at"] = next_fire
                        try:
                            from simulator.automation_repo import update_timer_status

                            update_timer_status(tid, "pending", fire_at_epoch=next_fire)
                        except Exception:
                            pass
                        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
                    else:
                        break
            except asyncio.CancelledError:
                if tid not in self._timer_tasks:
                    self.active_timers.pop(tid, None)
                raise

        existing = self._timer_tasks.pop(tid, None)
        if existing is not None and not existing.done():
            existing.cancel()
        self._timer_tasks[tid] = asyncio.create_task(_runner())

    async def cancel_timer_by_id(
        self,
        timer_id: str,
        *,
        actor_user_id: str | None = None,
        actor_tier: int | None = None,
    ) -> dict[str, Any]:
        info = self.active_timers.get(timer_id)
        eff_tier = int(actor_tier if actor_tier is not None else self.current_tier)
        eff_uid = str(actor_user_id or self._current_user_id or "")
        if eff_tier >= 3:
            return {"ok": False, "rbac_blocked": True, "error": "Khách chỉ được bật tắt thiết bị thôi ạ."}
        db_row = None
        if info is None:
            try:
                from simulator.automation_repo import list_pending_timers

                db_row = next((r for r in list_pending_timers() if str(r.get("timer_id") or r.get("id")) == str(timer_id)), None)
            except Exception:
                db_row = None
        target_info = info or db_row
        if target_info is not None and eff_tier == 2 and not self.system_policies.get("tier2_can_override_tier1", False):
            owner_id = str(target_info.get("owner_user_id") or target_info.get("owner_id") or "")
            if int(target_info.get("owner_tier", 1)) == 1:
                return {"ok": False, "rbac_blocked": True, "error": "Không thể hủy hẹn giờ của Chủ nhà (Tầng 1)."}
            if owner_id != eff_uid:
                return {"ok": False, "rbac_blocked": True, "error": "Bạn chỉ được hủy hẹn giờ do chính bạn đặt."}

        t = self._timer_tasks.pop(timer_id, None)
        if t is not None and not t.done():
            t.cancel()
        removed = self.active_timers.pop(timer_id, None)
        deleted_db = False
        try:
            from simulator.automation_repo import delete_timer_row

            deleted_db = delete_timer_row(timer_id)
        except Exception:
            deleted_db = False

        if removed is None and not deleted_db:
            return {"ok": False, "error": "Không tìm thấy hẹn giờ cần hủy."}

        dev_label = (removed or {}).get("device_id", "timer")
        append_audit_log(
            "AUTOMATION",
            "timer_cancelled",
            f"Hủy hẹn giờ {timer_id} ({dev_label})",
            user_name=eff_uid or "Hệ thống",
            tier=eff_tier,
        )
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {"ok": True, "timer_id": timer_id, "message": "Đã hủy hẹn giờ."}

    async def restore_timers_from_sqlite(self) -> dict[str, int]:
        from simulator.automation_repo import list_pending_timers, update_timer_status

        rows = list_pending_timers()
        restored = 0
        catchup = 0
        expired = 0
        now_ts = time.time()
        for row in rows:
            tid = str(row.get("timer_id") or "")
            if not tid or tid in self._timer_tasks:
                continue
            fire_at = float(row.get("fire_at") or 0.0)
            rem = fire_at - now_ts
            raw_target = str(row.get("raw_target") or row.get("device_id") or "")
            action = str(row.get("action") or "turn_on")
            repeat_mode = str(row.get("repeat") or "once")
            if repeat_mode not in REPEAT_VI_LABELS:
                repeat_mode = "once"
            label = str(row.get("label") or tid)

            if rem <= 0.0:
                if -rem <= 3600.0 and (raw_target in self.devices or raw_target in ("all_lights", "all_devices")):
                    try:
                        await self.execute_device_action(
                            device_id=raw_target,
                            action=action,
                            source=f"timer catchup ({label})",
                            bypass_rbac=True,
                            trigger_chains=True,
                        )
                        catchup += 1
                    except Exception:
                        pass
                    if repeat_mode == "once":
                        update_timer_status(tid, "fired")
                        continue
                    next_wait = REPEAT_INTERVAL_SECONDS.get(repeat_mode, 86400.0)
                    fire_at = time.time() + next_wait
                    rem = next_wait
                    update_timer_status(tid, "pending", fire_at_epoch=fire_at)
                else:
                    update_timer_status(tid, "expired")
                    expired += 1
                    continue

            dev_fk = "living_room_light" if raw_target in ("all_lights", "all_devices") else str(row.get("device_id") or raw_target)
            self.active_timers[tid] = {
                "id": tid,
                "device_id": dev_fk,
                "raw_target": raw_target,
                "action": action,
                "delay_seconds": float(row.get("delay_seconds") or rem),
                "fire_at": fire_at,
                "target_vn_time": str(row.get("target_vn_time") or ""),
                "repeat": repeat_mode,
                "reason": label,
                "label": label,
                "mode": "countdown",
                "created_at": float(row.get("created_at") or now_ts),
                "owner_id": str(row.get("owner_id") or "tuan_anh"),
                "owner_name": str(row.get("owner_name") or "Nguyễn Tuấn Anh"),
                "owner_tier": int(row.get("owner_tier") or 1),
            }
            self._spawn_timer_task(
                tid=tid,
                device_id=raw_target,
                action=action,
                initial_wait=rem,
                repeat_mode=repeat_mode,
                reason=label,
                trigger_chains=True,
            )
            restored += 1
        return {"restored": restored, "catchup": catchup, "expired": expired}

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
        if self.current_tier >= 3:
            msg = "Khách chỉ được bật tắt thiết bị thôi ạ."
            await self.emit({"type": "rbac_blocked", "device_id": device_id, "action": "update_or_cancel_timer", "role": self.current_role, "reason": msg})
            return {"ok": False, "rbac_blocked": True, "error": msg, "exact_spoken_reply": msg}

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
            try:
                from simulator.automation_repo import delete_timer_row

                delete_timer_row(tid)
            except Exception:
                pass

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
