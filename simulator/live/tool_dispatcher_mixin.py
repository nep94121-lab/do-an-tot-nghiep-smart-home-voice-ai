"""Module simulator.live.tool_dispatcher_mixin: Điều phối Tool Calls và Thu âm Cấp quyền Giọng nói cho Gemini Live."""

from __future__ import annotations

import asyncio
import copy
import time
from types import SimpleNamespace
from typing import Any

from google.genai import types

from simulator.api.deps import (
    _REST_ENGINE,
    broadcast_rest_state_to_bridges as _broadcast_rest_state_to_bridges,
)
from simulator.automation_nlu import (
    _deny_mutation_error,
    _parse_clock_hhmm_vi,
    format_pool_items_summary,
    handle_confirmation_reply,
    parse_multi_steps_from_text,
    prepare_pending_mutation,
)
from simulator.automation_repo import (
    GUEST_ONLY_TOGGLE_MSG_VI,
    can_user_create_links,
    check_steps_rbac,
    check_tier1_schedule_conflict,
    find_custom_command_by_text,
    format_device_action_vi,
    resolve_target_user_by_query,
)
from simulator.live.prompt_builder import FIXED_REJECTION_PHRASE_VI
from simulator.voice.enrollment_quality import check_enrollment_quality_gate



class LiveToolDispatcherMixin:
    """Mixin xử lý luồng thu âm cấp quyền giọng nói và thực thi các Function Calls từ Gemini Live."""

    engine: Any
    voice_auth: Any
    knowledge_rag: Any
    gemini_session: Any
    last_mic_turn_blocked: bool
    last_mic_auth_result: dict[str, Any] | None

    async def _run_voice_enrollment_sequence(
        self, duration_seconds: int, target_tier: int, target_name: str
    ) -> None:
        try:
            sig_dev = str(
                (self.engine.pending_voice_enrollment or {}).get("signal_device_id")
                or self.engine.system_policies.get("enrollment_signal_device_id", "living_room_light")
            )
            await asyncio.sleep(1.2)
            await self.engine.blink_signal_light(sig_dev, pulse_sec=0.35)
            await self.send_ws_json({
                "type": "start_voice_capture",
                "duration_seconds": duration_seconds,
                "target_tier": target_tier,
                "target_name": target_name,
                "message": f"💡 Đèn đã nháy! Hãy nói trong {duration_seconds} giây để thu âm cấp quyền Cấp {target_tier}...",
            })
            await asyncio.sleep(float(duration_seconds) + 2.2)
            if (
                self.engine.pending_voice_enrollment
                and self.engine.pending_voice_enrollment.get("step") == "RECORDING"
            ):
                await self._process_completed_voice_enrollment(b"")
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def _process_completed_voice_enrollment(
        self,
        pcm_bytes: bytes,
        self_check_pcm_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        if not self.engine.pending_voice_enrollment:
            return {"ok": False, "status": "NO_PENDING_ENROLLMENT"}
        if self.engine.pending_voice_enrollment.get("step") != "RECORDING":
            return {"ok": False, "status": "INVALID_ENROLLMENT_STEP"}

        self.engine.pending_voice_enrollment["step"] = "ANALYZING"
        sig_dev = str(
            self.engine.pending_voice_enrollment.get("signal_device_id")
            or self.engine.system_policies.get("enrollment_signal_device_id", "living_room_light")
        )

        await self.engine.blink_signal_light(sig_dev, pulse_sec=0.25)
        await self.send_ws_json({
            "type": "voice_enrollment_captured",
            "message": "✅ Đã thu âm! Đang kiểm định chất lượng mẫu đăng ký (11s + câu kiểm tra 3s)...",
        })

        # Bắt buộc 100% kiểm định chất lượng nghiêm ngặt phía server (11s + self-check 3s)
        gate_res = check_enrollment_quality_gate(
            enroll_pcm=pcm_bytes,
            self_check_pcm=self_check_pcm_bytes,
            sr=16000,
            require_self_check=True,
        )
        if not gate_res.get("ok"):
            self.engine.pending_voice_enrollment = None
            rej_spoken = str(gate_res.get("message") or "Mẫu giọng đăng ký không đạt chuẩn chất lượng, vui lòng thu âm lại.")
            await self.send_ws_json({
                "type": "voice_enrollment_rejected_quality",
                "reason": gate_res.get("reason"),
                "message": rej_spoken,
                "result": gate_res,
            })
            if self.gemini_session is not None:
                try:
                    await self.gemini_session.send_client_content(
                        turns=[types.Content(role="user", parts=[types.Part(text=f"BẮT BUỘC nói đúng câu: '{rej_spoken}'")])],
                        turn_complete=True,
                    )
                except Exception:
                    pass
            return gate_res

        target_tier_req = int(self.engine.pending_voice_enrollment.get("target_tier", 3))
        if pcm_bytes and len(pcm_bytes) >= 3200:
            dup_res = self.voice_auth.check_duplicate_voice_gate(
                pcm_bytes,
                target_tier=target_tier_req,
            )
            if dup_res.is_duplicate:
                self.engine.pending_voice_enrollment = None
                rej_spoken = (
                    f"Từ chối lưu! Giọng vừa thu trùng với {dup_res.matched_name} đã có trong nhà. "
                    f"Hệ thống bảo vệ nguyên vẹn quyền Cấp {dup_res.matched_tier} của bạn và không lưu thành Cấp {target_tier_req}."
                )
                await self.send_ws_json({
                    "type": "voice_enrollment_rejected_duplicate",
                    "reason": dup_res.reason,
                    "matched_name": dup_res.matched_name,
                    "matched_tier": dup_res.matched_tier,
                    "message": rej_spoken,
                })
                if self.gemini_session is not None:
                    try:
                        await self.gemini_session.send_client_content(
                            turns=[types.Content(role="user", parts=[types.Part(text=f"BẮT BUỘC nói đúng câu: '{rej_spoken}'")])],
                            turn_complete=True,
                        )
                    except Exception:
                        pass
                return {"ok": False, "status": "DUPLICATE_VOICE", "reason": dup_res.reason, "message": rej_spoken}

        analysis = self.voice_auth.analyze_voice_pcm16k(pcm_bytes)
        res = await self.engine.stage_voice_enrollment_analysis(
            f0_hz=analysis["f0_hz"],
            centroid_hz=analysis["centroid_hz"],
            embedding=analysis["embedding"],
            duration_sec=analysis.get("duration_sec", 12.0),
        )
        if self.engine.pending_voice_enrollment is not None:
            self.engine.pending_voice_enrollment["quality_gate_passed"] = True
            self.engine.pending_voice_enrollment["verified_pcm_bytes"] = pcm_bytes
            self.engine.pending_voice_enrollment["verified_self_check_bytes"] = self_check_pcm_bytes

        if res.get("status") == "VOICE_ENROLLMENT_COMPLETED" and res.get("target_user"):
            u = res["target_user"]
            enroll_res = self.voice_auth.enroll_tier_voice_from_pcm16k(
                pcm_bytes=pcm_bytes,
                self_check_pcm_bytes=self_check_pcm_bytes,
                user_id=u["id"],
                user_name=u["name"],
                tier=u["tier"],
                role=u["role"],
            )
            if not enroll_res.get("ok"):
                return enroll_res

        spoken_msg = res.get("exact_spoken_reply", "Đã thu âm đủ và phân tích xong. Người ấy tên là gì?")
        await self._sync_rules_context_to_gemini(spoken_msg)

        if self.gemini_session is not None:
            try:
                self._reset_turn_metrics(anchor_ts=time.perf_counter())
                await self.gemini_session.send_client_content(
                    turns=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(
                                    text=(
                                        f"[HỆ THỐNG ĐÃ THU ÂM ĐỦ VÀ PHÂN TÍCH XONG GIỌNG NÓI]: "
                                        f"KHÔNG gọi thêm tool nào lúc này. "
                                        f"BẮT BUỘC nói to, rõ ràng, ngắn gọn đúng câu này: '{spoken_msg}'"
                                    )
                                )
                            ],
                        )
                    ],
                    turn_complete=True,
                )
            except Exception:
                pass
        return res

    def _actor_session(self) -> Any:
        if hasattr(self, "_resolve_ws_session"):
            try:
                sess = self._resolve_ws_session()
                if sess is not None and getattr(sess, "is_authenticated", False):
                    return sess
            except Exception:
                pass
        return SimpleNamespace(
            user_id=str(getattr(self.engine, "_current_user_id", "") or "tuan_anh"),
            tier=int(getattr(self.engine, "current_tier", 3) or 3),
            display_name=str(self.engine.get_current_user_name() or "User"),
            role=str(getattr(self.engine, "current_role", "GUEST") or "GUEST"),
            session_id=f"live:{id(self)}",
            token_hash="",
        )

    @staticmethod
    def _wrap_nlu_tool_result(nlu_res: dict[str, Any]) -> dict[str, Any]:
        payload = dict((nlu_res or {}).get("payload") or {})
        spoken = str(
            payload.get("exact_spoken_reply")
            or payload.get("reply")
            or payload.get("error")
            or ""
        ).strip()
        if spoken and "instruction_for_ai" not in payload:
            payload["instruction_for_ai"] = (
                f"BẮT BUỘC nói ngắn gọn, đúng nguyên văn câu sau: '{spoken}'"
            )
        if "message" not in payload and spoken:
            payload["message"] = spoken
        return payload

    async def handle_tool_call(self, fc: Any) -> dict[str, Any]:
        name = fc.name
        args = dict(fc.args or {})

        if hasattr(self, "_bind_actor_to_engine"):
            actor = self._bind_actor_to_engine()
            if not actor.is_authenticated or actor.is_expired():
                rej_msg = FIXED_REJECTION_PHRASE_VI
                await self.send_ws_json({
                    "type": "rbac_blocked",
                    "action": name,
                    "role": "UNKNOWN",
                    "reason": rej_msg,
                })
                return {
                    "ok": False,
                    "rbac_blocked": True,
                    "error": rej_msg,
                    "message": rej_msg,
                    "rejection_speech": rej_msg,
                    "exact_spoken_reply": rej_msg,
                    "instruction_for_ai": f"TUYỆT ĐỐI KHÔNG thực hiện lệnh. Chỉ nói ngắn gọn đúng câu: '{rej_msg}'",
                }

        actor_sess = self._actor_session()
        actor_uid = str(getattr(actor_sess, "user_id", "") or "tuan_anh").strip()
        actor_tier = int(getattr(actor_sess, "tier", 3) or 3)
        live_session_key = f"live:{actor_uid}"

        _admin_tools = (
            "grant_user_permission",
            "revoke_user_permission",
            "manage_member_link_permission",
            "set_query_permission_policy",
            "admin_update_system_policy",
            "admin_upsert_knowledge_rag",
            "factory_reset",
        )
        if name in _admin_tools:
            ok_cap1_sess = True
            if hasattr(self, "_is_ws_cap1_authorized"):
                ok_cap1_sess, _ = self._is_ws_cap1_authorized()
            if not ok_cap1_sess or self.engine.current_tier != 1 or str(self.engine.current_role).upper() not in ("ADMIN", "OWNER"):
                err_nlu = _deny_mutation_error(
                    session=actor_sess,
                    source="gemini_live",
                    category=f"rbac_deny_{name}",
                    msg=GUEST_ONLY_TOGGLE_MSG_VI if actor_tier >= 3 else "Chỉ chủ nhà cấp 1 mới có quyền thực hiện lệnh này ạ.",
                    status_code=403,
                    target=name,
                )
                return self._wrap_nlu_tool_result(err_nlu)

        if self.last_mic_turn_blocked or self.engine.current_role == "UNKNOWN" or self.engine.current_tier >= 4:
            rej_msg = FIXED_REJECTION_PHRASE_VI
            await self.send_ws_json({
                "type": "rbac_blocked",
                "action": name,
                "role": "UNKNOWN",
                "reason": rej_msg,
            })
            return {
                "ok": False,
                "rbac_blocked": True,
                "error": rej_msg,
                "exact_spoken_reply": rej_msg,
                "instruction_for_ai": f"TUYỆT ĐỐI KHÔNG thực hiện lệnh. Chỉ nói ngắn gọn đúng câu: '{rej_msg}'",
            }

        if name in ("start_voice_enrollment", "finalize_voice_enrollment"):
            msg_ret = "Tính năng nhận diện giọng nói đã được gỡ bỏ; phân quyền dùng tài khoản và lời mời."
            return {"ok": False, "status": "RETIRED_ENDPOINT", "error": msg_ret, "exact_spoken_reply": msg_ret}

        if name == "control_device":
            res_ctrl = await self.engine.execute_device_action(
                device_id=str(args.get("device_id", "")),
                action=str(args.get("action", "")),
                source="gemini_live",
                trigger_chains=True,
                actor_tier=actor_tier,
                actor_name=str(getattr(actor_sess, "display_name", "") or actor_uid),
            )
            try:
                await _broadcast_rest_state_to_bridges()
            except Exception:
                pass
            return res_ctrl

        if name in ("confirm_or_cancel_pending_action", "confirm_pending_action", "confirm_factory_reset"):
            confirmed = bool(args.get("confirmed", True))
            if actor_tier >= 3:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category=f"rbac_deny_{name}",
                        msg=GUEST_ONLY_TOGGLE_MSG_VI,
                        status_code=403,
                        target="pending_confirmation",
                    )
                )
            conf_res = await handle_confirmation_reply(
                raw_text=("xác nhận" if confirmed else "hủy"),
                engine=self.engine,
                session=actor_sess,
                source="gemini_live",
                session_key=live_session_key,
            )
            if conf_res is not None:
                out = self._wrap_nlu_tool_result(conf_res)
                if out.get("ok"):
                    await self._sync_rules_context_to_gemini(out.get("exact_spoken_reply", "Đã xác nhận. Xong rồi ạ."))
                    try:
                        await _broadcast_rest_state_to_bridges()
                    except Exception:
                        pass
                return out
            if getattr(self.engine, "pending_reset_confirmation", False) or getattr(self.engine, "pending_action_confirmation", None):
                res_legacy = await self.engine.confirm_pending_action(confirmed=confirmed)
                if res_legacy.get("ok"):
                    await self._sync_rules_context_to_gemini(res_legacy.get("message", "Đã xử lý xác nhận."))
                return res_legacy
            return {
                "ok": False,
                "silent_cancel": True,
                "reply": "Đã hủy.",
                "exact_spoken_reply": "Đã hủy.",
                "instruction_for_ai": "BẮT BUỘC nói ngắn gọn đúng câu: 'Đã hủy.'",
            }

        if name == "query_pools_or_members":
            p_kind = str(args.get("pool_kind", "timers") or "timers").strip().lower()
            t_name = str(args.get("target_member_name", "") or "").strip() or None
            if actor_tier >= 3:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category=f"rbac_deny_query_{p_kind}",
                        msg=GUEST_ONLY_TOGGLE_MSG_VI,
                        status_code=403,
                        target=p_kind,
                    )
                )
            ok_q, code_q, spoken_q, data_q = format_pool_items_summary(
                pool_kind=p_kind,
                engine=self.engine,
                session=actor_sess,
                target_query=t_name,
            )
            return self._wrap_nlu_tool_result({
                "handled": True,
                "status_code": code_q,
                "payload": {
                    "ok": ok_q,
                    "kind": f"query_{p_kind}",
                    **data_q,
                    "reply": spoken_q,
                    "exact_spoken_reply": spoken_q,
                },
            })

        if name in ("reset_user_pool", "request_factory_reset"):
            raw_pool = str(args.get("pool_kind") or args.get("scope") or "custom_commands").strip().lower()
            pool_map = {
                "rules": "custom_commands",
                "custom_commands": "custom_commands",
                "commands": "custom_commands",
                "links": "links",
                "if_else": "links",
                "timers": "timers",
                "schedules": "timers",
                "all": "all",
                "voice": "custom_commands",
            }
            pool_kind = pool_map.get(raw_pool, "custom_commands")
            t_name = str(args.get("target_member_name", "") or "").strip()
            clear_all = bool(args.get("clear_all", False))
            if actor_tier >= 3:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category=f"rbac_deny_reset_{pool_kind}",
                        msg=GUEST_ONLY_TOGGLE_MSG_VI,
                        status_code=403,
                        target=pool_kind,
                    )
                )
            target_uid = actor_uid
            target_label = "của bạn"
            if clear_all:
                if actor_tier != 1:
                    return self._wrap_nlu_tool_result(
                        _deny_mutation_error(
                            session=actor_sess,
                            source="gemini_live",
                            category=f"rbac_deny_reset_all_{pool_kind}",
                            msg="Chỉ chủ nhà cấp 1 mới được reset dữ liệu của mọi người ạ.",
                            status_code=403,
                            target=pool_kind,
                        )
                    )
                target_label = "của mọi người"
            elif t_name:
                resolved = resolve_target_user_by_query(t_name)
                if resolved is None:
                    msg_nf = f"Không tìm thấy thành viên '{t_name}' ạ."
                    return {"ok": False, "error": msg_nf, "exact_spoken_reply": msg_nf}
                if actor_tier != 1 and str(resolved["user_id"]) != actor_uid:
                    return self._wrap_nlu_tool_result(
                        _deny_mutation_error(
                            session=actor_sess,
                            source="gemini_live",
                            category=f"rbac_deny_cross_reset_{pool_kind}",
                            msg="Chỉ chủ nhà cấp 1 mới được reset dữ liệu của người khác ạ.",
                            status_code=403,
                            target=str(resolved["user_id"]),
                        )
                    )
                target_uid = str(resolved["user_id"])
                target_label = f"của {resolved['display_name']}"
            pool_vi = {
                "custom_commands": "Reset lệnh custom",
                "links": "Reset liên kết thiết bị",
                "timers": "Xóa toàn bộ hẹn giờ và lịch hẹn",
                "all": "Reset toàn bộ dữ liệu tùy chỉnh",
            }.get(pool_kind, "Reset dữ liệu")
            nlu_res = await prepare_pending_mutation(
                engine=self.engine,
                session=actor_sess,
                source="gemini_live",
                session_key=live_session_key,
                action_kind="reset_pool",
                payload={
                    "pool_kind": pool_kind,
                    "target_owner_id": target_uid,
                    "clear_all": clear_all,
                    "target_display_name": target_label,
                },
                prompt_summary=f"{pool_vi} {target_label}",
            )
            return self._wrap_nlu_tool_result(nlu_res)

        if name == "manage_member_link_permission":
            t_name = str(args.get("target_member_name", "") or "").strip()
            allowed_flag = bool(args.get("allowed", True))
            resolved = resolve_target_user_by_query(t_name)
            if resolved is None:
                msg_nf = f"Không tìm thấy thành viên '{t_name}' ạ."
                return {"ok": False, "error": msg_nf, "exact_spoken_reply": msg_nf}
            verb_txt = "Cấp quyền tạo liên kết cho" if allowed_flag else "Thu hồi quyền tạo liên kết của"
            nlu_res = await prepare_pending_mutation(
                engine=self.engine,
                session=actor_sess,
                source="gemini_live",
                session_key=live_session_key,
                action_kind="set_member_link_permission",
                payload={
                    "target_user_id": resolved["user_id"],
                    "target_name": resolved["display_name"],
                    "target_tier": resolved["tier"],
                    "allowed": allowed_flag,
                },
                prompt_summary=f"{verb_txt} {resolved['display_name']}",
            )
            return self._wrap_nlu_tool_result(nlu_res)

        if name == "schedule_action":
            if actor_tier >= 3:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_timer",
                        msg=GUEST_ONLY_TOGGLE_MSG_VI,
                        status_code=403,
                        target="timers",
                    )
                )
            dev_id = str(args.get("device_id", "") or "living_room_light").strip()
            act = str(args.get("action", "") or "turn_on").strip()
            sec = float(args.get("seconds", args.get("delay_seconds", 0)) or 0)
            hrs = float(args.get("hours", 0) or 0)
            mins = float(args.get("minutes", 0) or 0)
            vn_ampm = str(args.get("vn_time_ampm", "") or "").strip()
            repeat = str(args.get("repeat", "once") or "once").strip().lower()
            total_sec = hrs * 3600.0 + mins * 60.0 + sec

            if total_sec <= 0 and vn_ampm:
                hhmm, parsed_daily, _ = _parse_clock_hhmm_vi(f"lúc {vn_ampm}")
                if hhmm:
                    sc_type = "daily" if (repeat == "daily" or parsed_daily) else "once"
                    allowed_td, reason_td = self.engine.check_device_permission(dev_id, actor_tier=actor_tier)
                    if not allowed_td:
                        return self._wrap_nlu_tool_result(
                            _deny_mutation_error(
                                session=actor_sess,
                                source="gemini_live",
                                category="rbac_deny_schedule_device",
                                msg=reason_td,
                                status_code=403,
                                target=dev_id,
                            )
                        )
                    conflict_msg = check_tier1_schedule_conflict(
                        actor_tier=actor_tier,
                        time_hhmm=hhmm,
                        schedule_type=sc_type,
                        engine=self.engine,
                    )
                    if conflict_msg:
                        return self._wrap_nlu_tool_result(
                            _deny_mutation_error(
                                session=actor_sess,
                                source="gemini_live",
                                category="tier1_schedule_conflict",
                                msg=conflict_msg,
                                status_code=409,
                                target="schedules",
                            )
                        )
                    rep_txt = "hằng ngày " if sc_type == "daily" else ""
                    nlu_res = await prepare_pending_mutation(
                        engine=self.engine,
                        session=actor_sess,
                        source="gemini_live",
                        session_key=live_session_key,
                        action_kind="create_schedule",
                        payload={
                            "target_devs": [dev_id],
                            "action": act,
                            "time_hhmm": hhmm,
                            "schedule_type": sc_type,
                        },
                        prompt_summary=f"Đặt lịch lúc {hhmm} {rep_txt}{format_device_action_vi(dev_id, act)}",
                    )
                    return self._wrap_nlu_tool_result(nlu_res)

            if total_sec <= 0:
                total_sec = 10.0
            allowed_td, reason_td = self.engine.check_device_permission(dev_id, actor_tier=actor_tier)
            if not allowed_td:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_timer_device",
                        msg=reason_td,
                        status_code=403,
                        target=dev_id,
                    )
                )
            conflict_msg = check_tier1_schedule_conflict(
                actor_tier=actor_tier,
                fire_epoch=time.time() + total_sec,
                engine=self.engine,
            )
            if conflict_msg:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="tier1_timer_conflict",
                        msg=conflict_msg,
                        status_code=409,
                        target="timers",
                    )
                )
            sec_i = max(1, int(round(total_sec)))
            nlu_res = await prepare_pending_mutation(
                engine=self.engine,
                session=actor_sess,
                source="gemini_live",
                session_key=live_session_key,
                action_kind="create_timer",
                payload={"device_id": dev_id, "action": act, "seconds": total_sec},
                prompt_summary=f"Đặt hẹn giờ sau {sec_i} giây sẽ {format_device_action_vi(dev_id, act).lower()}",
            )
            return self._wrap_nlu_tool_result(nlu_res)

        if name == "update_timer":
            if actor_tier >= 3:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_update_timer",
                        msg=GUEST_ONLY_TOGGLE_MSG_VI,
                        status_code=403,
                        target="timers",
                    )
                )
            op = str(args.get("operation", "modify") or "modify").strip().lower()
            dev_id = str(args.get("device_id", "all_devices") or "all_devices").strip()
            if op == "cancel":
                nlu_res = await prepare_pending_mutation(
                    engine=self.engine,
                    session=actor_sess,
                    source="gemini_live",
                    session_key=live_session_key,
                    action_kind="delete_timer",
                    payload={"device_id": dev_id},
                    prompt_summary=f"Hủy hẹn giờ {dev_id}",
                )
                return self._wrap_nlu_tool_result(nlu_res)
            sec = float(args.get("seconds", 0) or 0)
            hrs = float(args.get("hours", 0) or 0)
            mins = float(args.get("minutes", 0) or 0)
            vn_ampm = str(args.get("vn_time_ampm", "") or "")
            vn_date = str(args.get("vn_date", "") or "")
            repeat = str(args.get("repeat", "once") or "once")
            if (sec > 0 or mins > 0 or hrs > 0) and not vn_date:
                vn_ampm = ""
            res = await self.engine.update_or_cancel_timer(
                device_id=dev_id,
                operation=op,
                new_action=str(args.get("new_action", "") or ""),
                hours=hrs,
                minutes=mins,
                seconds=sec,
                vn_time_ampm=vn_ampm,
                vn_date=vn_date,
                repeat=repeat,
            )
            await self._sync_rules_context_to_gemini(res.get("message", "Đã cập nhật hẹn giờ."))
            return res

        if name == "set_word_mapping":
            if actor_tier >= 3:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_word_mapping",
                        msg=GUEST_ONLY_TOGGLE_MSG_VI,
                        status_code=403,
                        target="word_mappings",
                    )
                )
            res = await self.engine.set_word_mapping(
                custom_word=str(args.get("custom_word", "")),
                target_meaning=str(args.get("target_meaning", "")),
                require_confirmation=False,
            )
            if res.get("ok"):
                await self._sync_rules_context_to_gemini(res.get("message", "Đã lưu đổi từ."))
            return res

        if name == "create_alias_rule":
            if actor_tier >= 3:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_create_alias",
                        msg=GUEST_ONLY_TOGGLE_MSG_VI,
                        status_code=403,
                        target="custom_commands",
                    )
                )
            phrase_str = str(args.get("phrase", "")).strip()
            devs_csv = str(args.get("target_devices_csv", "")).strip()
            acts_csv = str(args.get("target_actions_csv", "")).strip()
            dev_list = [d.strip() for d in devs_csv.split(",") if d.strip()]
            act_list = [a.strip() for a in acts_csv.split(",") if a.strip()]
            steps = [
                {
                    "device_id": d,
                    "action": act_list[idx] if idx < len(act_list) else (act_list[-1] if act_list else "turn_on"),
                }
                for idx, d in enumerate(dev_list)
            ]
            ok_steps, err_steps = check_steps_rbac(steps, actor_tier)
            if not ok_steps:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_alias_device",
                        msg=err_steps,
                        status_code=403,
                        target="custom_commands",
                    )
                )
            steps_summary = ", ".join(format_device_action_vi(s["device_id"], s["action"]) for s in steps)
            nlu_res = await prepare_pending_mutation(
                engine=self.engine,
                session=actor_sess,
                source="gemini_live",
                session_key=live_session_key,
                action_kind="create_custom_command",
                payload={"phrase": phrase_str, "steps": steps},
                prompt_summary=f"Tạo lệnh '{phrase_str}' gồm {steps_summary}",
            )
            return self._wrap_nlu_tool_result(nlu_res)

        if name == "execute_alias_rule":
            if actor_tier >= 3:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_run_alias",
                        msg=GUEST_ONLY_TOGGLE_MSG_VI,
                        status_code=403,
                        target="custom_commands",
                    )
                )
            phrase_q = str(args.get("phrase", "")).strip()
            cmd_hit = find_custom_command_by_text(phrase_q, owner_user_id=actor_uid)
            if cmd_hit is not None:
                res_sc = await self.engine.execute_custom_scene(cmd_hit["command_id"], source="gemini_live")
                try:
                    await _broadcast_rest_state_to_bridges()
                except Exception:
                    pass
                return res_sc
            return await self.engine.execute_alias_rule(phrase=phrase_q)

        if name in ("set_if_else_rule", "create_chain_rule"):
            if actor_tier >= 3:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_create_link",
                        msg=GUEST_ONLY_TOGGLE_MSG_VI,
                        status_code=403,
                        target="automation_rules",
                    )
                )
            if not can_user_create_links(actor_uid, actor_tier, engine=self.engine):
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_create_link_permission",
                        msg="Bạn chưa được chủ nhà cấp quyền tạo liên kết thiết bị.",
                        status_code=403,
                        target="automation_rules",
                    )
                )
            wdev = str(args.get("when_device_id", "")).strip()
            wstate = str(args.get("when_state", "ON") or "ON").strip()
            tdev = str(args.get("then_device_id", "")).strip()
            tact = str(args.get("then_action", "turn_on") or "turn_on").strip()
            edev = str(args.get("else_device_id", "") or "").strip()
            eact = str(args.get("else_action", "") or "").strip()
            allowed_then, reason_then = self.engine.check_device_permission(tdev, actor_tier=actor_tier)
            if not allowed_then:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_link_device",
                        msg=reason_then,
                        status_code=403,
                        target=tdev,
                    )
                )
            if edev:
                allowed_else, reason_else = self.engine.check_device_permission(edev, actor_tier=actor_tier)
                if not allowed_else:
                    return self._wrap_nlu_tool_result(
                        _deny_mutation_error(
                            session=actor_sess,
                            source="gemini_live",
                            category="rbac_deny_link_else_device",
                            msg=reason_else,
                            status_code=403,
                            target=edev,
                        )
                    )
            if wdev and wdev == tdev:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="invalid_automation_rule_cycle",
                        msg="Không thể tạo liên kết tự kích hoạt chính thiết bị nguồn.",
                        status_code=400,
                        target=wdev,
                    )
                )
            prompt_desc = f"Tạo liên kết khi {wdev}={wstate} thì {format_device_action_vi(tdev, tact)}"
            if edev:
                prompt_desc += f", ngược lại {format_device_action_vi(edev, eact)}"
            nlu_res = await prepare_pending_mutation(
                engine=self.engine,
                session=actor_sess,
                source="gemini_live",
                session_key=live_session_key,
                action_kind="create_automation_rule",
                payload={
                    "when_device_id": wdev,
                    "when_state": wstate,
                    "then_device_id": tdev,
                    "then_action": tact,
                    "else_device_id": edev,
                    "else_action": eact,
                },
                prompt_summary=prompt_desc,
            )
            return self._wrap_nlu_tool_result(nlu_res)

        if name == "create_schedule_clock":
            if actor_tier >= 3:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_schedule",
                        msg=GUEST_ONLY_TOGGLE_MSG_VI,
                        status_code=403,
                        target="schedules",
                    )
                )
            dev_id = str(args.get("device_id", "living_room_light")).strip()
            act = str(args.get("action", "turn_on")).strip()
            hhmm = str(args.get("time_hhmm", "")).strip()
            sc_type = str(args.get("schedule_type", "once") or "once").strip().lower()
            allowed_td, reason_td = self.engine.check_device_permission(dev_id, actor_tier=actor_tier)
            if not allowed_td:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_schedule_device",
                        msg=reason_td,
                        status_code=403,
                        target=dev_id,
                    )
                )
            conflict_msg = check_tier1_schedule_conflict(
                actor_tier=actor_tier,
                time_hhmm=hhmm,
                schedule_type=sc_type,
                engine=self.engine,
            )
            if conflict_msg:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="tier1_schedule_conflict",
                        msg=conflict_msg,
                        status_code=409,
                        target="schedules",
                    )
                )
            rep_txt = "hằng ngày " if sc_type == "daily" else ""
            nlu_res = await prepare_pending_mutation(
                engine=self.engine,
                session=actor_sess,
                source="gemini_live",
                session_key=live_session_key,
                action_kind="create_schedule",
                payload={
                    "target_devs": [dev_id],
                    "action": act,
                    "time_hhmm": hhmm,
                    "schedule_type": sc_type,
                },
                prompt_summary=f"Đặt lịch lúc {hhmm} {rep_txt}{format_device_action_vi(dev_id, act)}",
            )
            return self._wrap_nlu_tool_result(nlu_res)

        if name == "create_custom_scene":
            if actor_tier >= 3:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_create_custom_command",
                        msg=GUEST_ONLY_TOGGLE_MSG_VI,
                        status_code=403,
                        target="custom_commands",
                    )
                )
            phrase = str(args.get("phrase", "")).strip()
            steps_text = str(args.get("steps_text", "")).strip()
            steps = parse_multi_steps_from_text(steps_text)
            if not steps:
                msg_empty = "Không nhận diện được các bước thiết bị cho lệnh tùy chỉnh."
                return {"ok": False, "error": msg_empty, "exact_spoken_reply": msg_empty}
            ok_steps, err_steps = check_steps_rbac(steps, actor_tier)
            if not ok_steps:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_custom_command_device",
                        msg=err_steps,
                        status_code=403,
                        target="custom_commands",
                    )
                )
            steps_summary = ", ".join(format_device_action_vi(s["device_id"], s["action"]) for s in steps)
            nlu_res = await prepare_pending_mutation(
                engine=self.engine,
                session=actor_sess,
                source="gemini_live",
                session_key=live_session_key,
                action_kind="create_custom_command",
                payload={"phrase": phrase, "steps": steps},
                prompt_summary=f"Tạo lệnh '{phrase}' gồm {steps_summary}",
            )
            return self._wrap_nlu_tool_result(nlu_res)

        if name == "run_custom_scene":
            if actor_tier >= 3:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_run_custom_command",
                        msg=GUEST_ONLY_TOGGLE_MSG_VI,
                        status_code=403,
                        target="custom_commands",
                    )
                )
            phrase_or_id = str(args.get("phrase_or_id", "")).strip()
            cmd_hit = find_custom_command_by_text(phrase_or_id, owner_user_id=actor_uid)
            target_id = cmd_hit["command_id"] if cmd_hit is not None else phrase_or_id
            res_sc = await self.engine.execute_custom_scene(target_id, source="gemini_live")
            try:
                await _broadcast_rest_state_to_bridges()
            except Exception:
                pass
            return res_sc

        if name == "delete_automation_item":
            if actor_tier >= 3:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_delete_automation",
                        msg=GUEST_ONLY_TOGGLE_MSG_VI,
                        status_code=403,
                        target="automation",
                    )
                )
            kind = str(args.get("kind", "schedule") or "schedule").strip().lower()
            kw = str(args.get("keyword_or_id", "")).strip()
            kind_map = {
                "schedule": ("delete_schedule", {"time_hhmm": kw if ":" in kw else None, "schedule_id": kw if kw.startswith("sc_") else ""}),
                "rule": ("delete_automation_rule", {"rule_id": kw if kw.startswith("rule_") else ""}),
                "scene": ("delete_custom_command", {"phrase": kw, "command_id": kw if kw.startswith("cmd_") else ""}),
            }
            act_k, pl = kind_map.get(kind, ("delete_schedule", {}))
            nlu_res = await prepare_pending_mutation(
                engine=self.engine,
                session=actor_sess,
                source="gemini_live",
                session_key=live_session_key,
                action_kind=act_k,
                payload=pl,
                prompt_summary=f"Xóa {kind} '{kw}'".strip(),
            )
            return self._wrap_nlu_tool_result(nlu_res)

        if name == "query_pools":
            if actor_tier >= 3:
                return self._wrap_nlu_tool_result(
                    _deny_mutation_error(
                        session=actor_sess,
                        source="gemini_live",
                        category="rbac_deny_query_pools",
                        msg=GUEST_ONLY_TOGGLE_MSG_VI,
                        status_code=403,
                        target="pools",
                    )
                )
            q_type = str(args.get("query_type", "all") or "all")
            if q_type == "timers":
                _, _, sp_t, d_t = format_pool_items_summary(pool_kind="timers", engine=self.engine, session=actor_sess)
                return self._wrap_nlu_tool_result({"handled": True, "status_code": 200, "payload": {"ok": True, **d_t, "reply": sp_t, "exact_spoken_reply": sp_t}})
            t_dev = str(args.get("target_device_id", "") or "")
            return self.engine.get_pools_summary(query_type=q_type, target_device_id=t_dev)

        if name == "query_knowledge_rag":
            q = str(args.get("question", "") or "")
            return self.knowledge_rag.retrieve(
                q,
                current_tier=self.engine.current_tier,
                query_permission_mode=self.engine.query_permission_mode,
            )

        if name == "start_voice_enrollment":
            target_tier = int(args.get("target_tier", 3) or 3)
            target_name = str(args.get("target_name", "") or "")
            dur = int(args.get("duration_seconds", 5) or 5)
            res = await self.engine.start_voice_enrollment(
                target_tier=target_tier,
                target_name=target_name,
                duration_seconds=dur,
            )
            if res.get("ok"):
                asyncio.create_task(
                    self._run_voice_enrollment_sequence(
                        duration_seconds=res.get("duration_seconds", 5),
                        target_tier=res.get("target_tier", 3),
                        target_name=res.get("target_name", ""),
                    )
                )
            return res

        if name == "finalize_voice_enrollment":
            target_name = str(args.get("target_name", "") or "")
            target_tier = int(args.get("target_tier", 0) or 0)
            p_info = dict(self.engine.pending_voice_enrollment or {})
            v_pcm = p_info.get("verified_pcm_bytes") or b""
            v_sc = p_info.get("verified_self_check_bytes")
            gate_res = check_enrollment_quality_gate(
                enroll_pcm=v_pcm,
                self_check_pcm=v_sc,
                sr=16000,
                require_self_check=True,
            )
            if not gate_res.get("ok"):
                return gate_res
            res = await self.engine.finalize_voice_enrollment(
                target_name=target_name,
                target_tier=target_tier,
            )
            if res.get("ok") and res.get("target_user"):
                u = res["target_user"]
                enroll_res = self.voice_auth.enroll_tier_voice_from_pcm16k(
                    pcm_bytes=v_pcm,
                    self_check_pcm_bytes=v_sc,
                    user_id=u["id"],
                    user_name=u["name"],
                    tier=u["tier"],
                    role=u["role"],
                )
                if not enroll_res.get("ok"):
                    return enroll_res
                await self._sync_rules_context_to_gemini(res.get("message", "Đã lưu giọng nói và cấp quyền."))
            return res

        if name == "grant_user_permission":
            target_name = str(args.get("target_name", "") or "")
            target_tier = int(args.get("target_tier", 3) or 3)
            if (
                self.engine.pending_voice_enrollment
                and self.engine.pending_voice_enrollment.get("step") == "AWAITING_NAME"
            ):
                p_info = dict(self.engine.pending_voice_enrollment or {})
                v_pcm = p_info.get("verified_pcm_bytes") or b""
                v_sc = p_info.get("verified_self_check_bytes")
                gate_res = check_enrollment_quality_gate(
                    enroll_pcm=v_pcm,
                    self_check_pcm=v_sc,
                    sr=16000,
                    require_self_check=True,
                )
                if not gate_res.get("ok"):
                    return gate_res
                res = await self.engine.finalize_voice_enrollment(
                    target_name=target_name,
                    target_tier=target_tier,
                )
                if res.get("ok") and res.get("target_user"):
                    u = res["target_user"]
                    enroll_res = self.voice_auth.enroll_tier_voice_from_pcm16k(
                        pcm_bytes=v_pcm,
                        self_check_pcm_bytes=v_sc,
                        user_id=u["id"],
                        user_name=u["name"],
                        tier=u["tier"],
                        role=u["role"],
                    )
                    if not enroll_res.get("ok"):
                        return enroll_res
                    await self._sync_rules_context_to_gemini(res.get("message", "Đã lưu giọng nói và cấp quyền."))
                return res

            res = await self.engine.grant_user_permission(target_name=target_name, target_tier=target_tier)
            if res.get("ok"):
                from simulator.auth_3layer import get_auth_3layer_manager
                get_auth_3layer_manager().set_account_permission_by_voice_or_admin(
                    target_identifier=target_name,
                    enable_permission=True,
                    actor_tier=self.engine.current_tier,
                    spoken_command=f"Cấp/Bật lại quyền cho {target_name}",
                    source_device="Gemini Live Voice",
                )
                await self._sync_rules_context_to_gemini(res.get("message", "Đã cấp quyền."))
            return res

        if name == "revoke_user_permission":
            target_name = str(args.get("target_name", "") or "")
            res = await self.engine.revoke_user_permission(target_name=target_name)
            if res.get("ok"):
                from simulator.auth_3layer import get_auth_3layer_manager
                get_auth_3layer_manager().set_account_permission_by_voice_or_admin(
                    target_identifier=target_name,
                    enable_permission=False,
                    actor_tier=self.engine.current_tier,
                    spoken_command=f"Xóa cấp quyền của {target_name}",
                    source_device="Gemini Live Voice",
                )
                await self._sync_rules_context_to_gemini(res.get("message", "Đã hủy quyền."))
            return res

        if name == "set_query_permission_policy":
            mode = str(args.get("mode", "tier_restricted") or "tier_restricted")
            res = await self.engine.set_query_permission_policy(mode=mode)
            if res.get("ok"):
                await self._sync_rules_context_to_gemini(res.get("message", "Đã cập nhật quy tắc phân quyền hỏi."))
            return res

        if name == "admin_update_system_policy":
            policy_key = str(args.get("policy_key", "") or "")
            policy_value = str(args.get("policy_value", "") or "")
            target_device_id = str(args.get("target_device_id", "") or "")
            res = await self.engine.admin_update_system_policy(
                policy_key=policy_key,
                policy_value=policy_value,
                target_device_id=target_device_id,
            )
            if res.get("ok"):
                await self._sync_rules_context_to_gemini(res.get("message", "Đã cập nhật quy tắc hệ thống."))
            return res

        if name == "admin_upsert_knowledge_rag":
            topic = str(args.get("topic", "") or "")
            content = str(args.get("content", "") or "")
            keywords = str(args.get("keywords", "") or "")
            min_tier = int(args.get("min_tier", 3) or 3)
            res = self.knowledge_rag.upsert_knowledge_item(
                topic=topic,
                content=content,
                keywords=keywords,
                min_tier=min_tier,
                current_tier=self.engine.current_tier,
            )
            if res.get("ok"):
                await self.send_ws_json({
                    "type": "system_policy_updated",
                    "policy_key": "knowledge_rag",
                    "message": res.get("message", "Đã cập nhật tri thức RAG."),
                })
                await self._sync_rules_context_to_gemini(res.get("message", "Đã cập nhật tri thức RAG."))
            return res

        if name == "set_or_query_sensors":
            op = str(args.get("operation", "query") or "query").lower()
            temp_c = args.get("temp_c")
            humidity_pct = args.get("humidity_pct")
            soil_pct = args.get("soil_moisture_pct")
            replies: list[str] = []
            if op == "set" or temp_c is not None or humidity_pct is not None or soil_pct is not None:
                if temp_c is not None or humidity_pct is not None:
                    cur_dht = self.engine.mqtt_bridge.dht11_telemetry
                    t_val = float(temp_c) if temp_c is not None else float(cur_dht.get("temp_c", 28.5))
                    h_val = float(humidity_pct) if humidity_pct is not None else float(cur_dht.get("humidity_pct", 65.0))
                    r_dht = await self.engine.update_sensor_telemetry(temp_c=t_val, humidity_pct=h_val)
                    _REST_ENGINE.mqtt_bridge.dht11_telemetry = copy.deepcopy(self.engine.mqtt_bridge.dht11_telemetry)
                    replies.append(str(r_dht.get("exact_spoken_reply", "")))
                if soil_pct is not None:
                    r_soil = await self.engine.update_soil_moisture_telemetry(soil_moisture_pct=float(soil_pct))
                    _REST_ENGINE.mqtt_bridge.soil_moisture_telemetry = copy.deepcopy(self.engine.mqtt_bridge.soil_moisture_telemetry)
                    replies.append(str(r_soil.get("exact_spoken_reply", "")))
                await _broadcast_rest_state_to_bridges()
                spoken = " ".join(r for r in replies if r).strip() or "Đã cập nhật thông số cảm biến."
                return {
                    "ok": True,
                    "exact_spoken_reply": spoken,
                    "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
                    "message": spoken,
                }
            cur_dht = self.engine.mqtt_bridge.dht11_telemetry
            cur_soil = self.engine.mqtt_bridge.soil_moisture_telemetry
            spoken = (
                f"Nhiệt độ phòng đang là {float(cur_dht.get('temp_c', 28.5)):.1f} độ C, "
                f"độ ẩm không khí {float(cur_dht.get('humidity_pct', 65.0)):.0f}%, "
                f"độ ẩm đất {float(cur_soil.get('soil_moisture_pct', 55.0)):.0f}%."
            )
            return {
                "ok": True,
                "dht11": cur_dht,
                "soil": cur_soil,
                "exact_spoken_reply": spoken,
                "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
                "message": spoken,
            }

        return {"ok": False, "error": f"Hàm '{name}' không được hỗ trợ."}
