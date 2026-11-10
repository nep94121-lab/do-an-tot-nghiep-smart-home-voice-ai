"""Module simulator.live.tool_dispatcher_mixin: Điều phối Tool Calls và Thu âm Cấp quyền Giọng nói cho Gemini Live."""

from __future__ import annotations

import asyncio
import copy
import time
from typing import Any

from google.genai import types

from simulator.api.deps import (
    _REST_ENGINE,
    broadcast_rest_state_to_bridges as _broadcast_rest_state_to_bridges,
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
            "message": "✅ Đã thu âm! Đang kiểm định chất lượng mẫu đăng ký (12s + câu kiểm tra 3s)...",
        })

        # Bắt buộc 100% kiểm định chất lượng nghiêm ngặt phía server (12s + self-check 3s)
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

    async def handle_tool_call(self, fc: Any) -> dict[str, Any]:
        name = fc.name
        args = dict(fc.args or {})

        await self._ensure_current_mic_utterance_verified()

        _admin_tools = (
            "grant_user_permission",
            "revoke_user_permission",
            "start_voice_enrollment",
            "finalize_voice_enrollment",
            "set_query_permission_policy",
            "admin_update_system_policy",
            "admin_upsert_knowledge_rag",
            "factory_reset",
            "request_factory_reset",
            "confirm_factory_reset",
            "factory_reset_rules",
        )
        if name in _admin_tools or (
            name == "confirm_pending_action" and bool(getattr(self.engine, "pending_reset_confirmation", False))
        ):
            ok_cap1_sess = True
            if hasattr(self, "_is_ws_cap1_authorized"):
                ok_cap1_sess, _ = self._is_ws_cap1_authorized()
            if not ok_cap1_sess or self.engine.current_tier != 1 or self.engine.current_role != "ADMIN":
                rej_msg = FIXED_REJECTION_PHRASE_VI
                await self.send_ws_json({
                    "type": "rbac_blocked",
                    "action": name,
                    "role": self.engine.current_role,
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

        if self.last_mic_turn_blocked or self.engine.current_role == "UNKNOWN" or self.engine.current_tier >= 4:
            rej_info = self.last_mic_auth_result or {}
            rej_msg = str(
                rej_info.get("rejection_speech")
                or "Tôi không nhận ra giọng của bạn."
            )
            f0_val = rej_info.get("f0_hz", 0.0)
            await self.send_ws_json({
                "type": "rbac_blocked",
                "action": name,
                "role": "UNKNOWN",
                "reason": f"🚫 Chặn giọng nói không có quyền (F0={f0_val}Hz): {rej_msg}",
            })
            return {
                "ok": False,
                "error": rej_msg,
                "exact_spoken_reply": rej_msg,
                "instruction_for_ai": f"TUYỆT ĐỐI KHÔNG thực hiện lệnh. Chỉ nói ngắn gọn đúng câu: '{rej_msg}'",
            }

        if name == "control_device":
            return await self.engine.execute_device_action(
                device_id=str(args.get("device_id", "")),
                action=str(args.get("action", "")),
                source="gemini_live",
                trigger_chains=True,
            )

        if name == "schedule_action":
            sec = float(args.get("seconds", args.get("delay_seconds", 0)) or 0)
            hrs = float(args.get("hours", 0) or 0)
            mins = float(args.get("minutes", 0) or 0)
            vn_ampm = str(args.get("vn_time_ampm", "") or "")
            vn_date = str(args.get("vn_date", "") or "")
            repeat = str(args.get("repeat", "once") or "once")
            if (sec > 0 or mins > 0 or hrs > 0) and not vn_date:
                vn_ampm = ""
            res = await self.engine.schedule_timer_flexible(
                device_id=str(args.get("device_id", "")),
                action=str(args.get("action", "")),
                hours=hrs,
                minutes=mins,
                seconds=sec,
                vn_time_ampm=vn_ampm,
                vn_date=vn_date,
                repeat=repeat,
            )
            await self._sync_rules_context_to_gemini(res.get("message", "Đã đặt hẹn giờ."))
            return res

        if name == "update_timer":
            sec = float(args.get("seconds", 0) or 0)
            hrs = float(args.get("hours", 0) or 0)
            mins = float(args.get("minutes", 0) or 0)
            vn_ampm = str(args.get("vn_time_ampm", "") or "")
            vn_date = str(args.get("vn_date", "") or "")
            repeat = str(args.get("repeat", "once") or "once")
            if (sec > 0 or mins > 0 or hrs > 0) and not vn_date:
                vn_ampm = ""
            res = await self.engine.update_or_cancel_timer(
                device_id=str(args.get("device_id", "all_devices")),
                operation=str(args.get("operation", "modify")),
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
            res = await self.engine.set_word_mapping(
                custom_word=str(args.get("custom_word", "")),
                target_meaning=str(args.get("target_meaning", "")),
                require_confirmation=True,
            )
            if res.get("ok"):
                await self._sync_rules_context_to_gemini(res.get("message", "Đang chờ xác nhận đổi từ."))
            return res

        if name == "create_alias_rule":
            res = await self.engine.create_alias_rule(
                phrase=str(args.get("phrase", "")),
                target_devices_csv=str(args.get("target_devices_csv", "")),
                target_actions_csv=str(args.get("target_actions_csv", "")),
                require_confirmation=True,
            )
            if res.get("ok"):
                await self._sync_rules_context_to_gemini(res.get("message", "Đang chờ xác nhận đổi khẩu lệnh."))
            return res

        if name == "execute_alias_rule":
            return await self.engine.execute_alias_rule(phrase=str(args.get("phrase", "")))

        if name in ("set_if_else_rule", "create_chain_rule"):
            eval_now = bool(args.get("evaluate_now", False))
            res = await self.engine.set_if_else_rule(
                when_device_id=str(args.get("when_device_id", "")),
                when_state=str(args.get("when_state", "")),
                then_device_id=str(args.get("then_device_id", "")),
                then_action=str(args.get("then_action", "")),
                delay_seconds=float(args.get("delay_seconds", 0) or 0),
                else_device_id=str(args.get("else_device_id", "") or ""),
                else_action=str(args.get("else_action", "") or ""),
                evaluate_now=eval_now,
                require_confirmation=not eval_now,
            )
            if res.get("ok"):
                await self._sync_rules_context_to_gemini(res.get("message", "Đang chờ xác nhận luật IF."))
            return res

        if name == "query_pools":
            q_type = str(args.get("query_type", "all") or "all")
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

        if name == "request_factory_reset":
            scope = str(args.get("scope", "all") or "all")
            return await self.engine.request_factory_reset(scope=scope)

        if name in ("confirm_pending_action", "confirm_factory_reset", "factory_reset_rules"):
            confirmed = bool(args.get("confirmed", True))
            res = await self.engine.confirm_pending_action(confirmed=confirmed)
            if res.get("ok"):
                if res.get("reset_scope") in ("voice", "all"):
                    await self.send_ws_json({
                        "type": "voice_auth_result",
                        "sample_id": "reset_voice",
                        "label": "Đã reset giọng nói chỉ về của Chủ nhà",
                        "analysis": self.voice_auth.last_analysis,
                    })
                await self._sync_rules_context_to_gemini(res.get("message", "Đã xử lý xác nhận."))
            return res

        return {"ok": False, "error": f"Hàm '{name}' không được hỗ trợ."}
