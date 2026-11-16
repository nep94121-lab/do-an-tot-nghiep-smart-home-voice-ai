"""REST API CRUD for countdown timers, Asia/Saigon clock schedules, linked automation rules, and custom scenes."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from simulator.api.deps import (
    _REST_ENGINE,
    broadcast_rest_state_to_bridges,
)
from simulator.auth.session_store import resolve_request_session
from simulator.auth.tier_permissions import can_control_device
from simulator.automation_nlu import parse_multi_steps_from_text, prepare_pending_mutation, execute_confirmed_mutation
from simulator.automation_repo import (
    GUEST_ONLY_TOGGLE_MSG_VI,
    _normalize_steps,
    can_user_create_links,
    check_steps_rbac,
    check_tier1_schedule_conflict,
    create_automation_rule,
    create_schedule,
    delete_automation_rule,
    delete_custom_command,
    delete_schedule,
    format_device_action_vi,
    inspect_and_consume_pending_confirmation,
    list_automation_rules,
    list_custom_commands,
    list_household_members,
    list_pending_timers,
    list_schedules,
    normalize_phrase,
    set_user_can_create_links,
    update_schedule,
    upsert_custom_command,
    validate_automation_rule_input,
)
from simulator.engine.audit_logger import append_audit_log
from simulator.engine.constants_and_time import ACTION_TO_STATE, DEFAULT_DEVICES

router = APIRouter()


def _require_auth(request: Request, body: dict[str, Any] | None = None):
    sess = resolve_request_session(request, payload=body, engine=None)
    if not sess.is_authenticated:
        return None, JSONResponse(
            {"ok": False, "authenticated": False, "error": "Yêu cầu đăng nhập để quản lý tự động hóa."},
            status_code=401,
        )
    return sess, None


def _deny_guest_tier3(sess: Any, endpoint_name: str) -> JSONResponse | None:
    tier_val = int(getattr(sess, "tier", 3) or 3)
    if tier_val >= 3:
        append_audit_log(
            "SECURITY",
            "automation_rbac_blocked",
            f"RBAC Chặn Cấp 3 ({getattr(sess, 'display_name', 'Khách')}) gọi {endpoint_name}: {GUEST_ONLY_TOGGLE_MSG_VI}",
            user_name=str(getattr(sess, "display_name", "Khách") or "Khách"),
            tier=tier_val,
        )
        return JSONResponse(
            {
                "ok": False,
                "rbac_blocked": True,
                "tier": tier_val,
                "error": GUEST_ONLY_TOGGLE_MSG_VI,
                "exact_spoken_reply": GUEST_ONLY_TOGGLE_MSG_VI,
            },
            status_code=403,
        )
    return None


def _can_manage_timers(sess: Any) -> bool:
    return int(getattr(sess, "tier", 3) or 3) <= 2


def _can_manage_rules(sess: Any) -> bool:
    return int(getattr(sess, "tier", 3) or 3) <= 2


def _extract_confirm_token(request: Request, body: dict[str, Any] | None = None) -> str:
    b = body if isinstance(body, dict) else {}
    raw = (
        b.get("confirm_token")
        or b.get("pending_id")
        or request.query_params.get("confirm_token")
        or request.query_params.get("pending_id")
        or request.headers.get("X-Confirm-Token")
        or request.headers.get("X-Pending-Id")
        or ""
    )
    return str(raw).strip()


def _parse_confirmed_flag(body: dict[str, Any]) -> bool:
    decision = str(body.get("decision") or "").strip().lower()
    if decision in ("cancel", "cancelled", "no", "false", "huy", "khong"):
        return False
    if "confirmed" in body:
        val = body["confirmed"]
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().lower() not in ("false", "0", "no", "cancel", "")
        return bool(val)
    return True


def _confirmation_failure_response(reason: str) -> JSONResponse:
    if reason == "wrong_owner":
        return JSONResponse(
            {
                "ok": False,
                "rbac_blocked": True,
                "error": "Bạn không có quyền xác nhận thao tác của người khác.",
            },
            status_code=403,
        )
    if reason == "expired":
        return JSONResponse(
            {
                "ok": False,
                "cancelled": True,
                "expired": True,
                "error": "Yêu cầu xác nhận đã hết hạn (20 giây).",
                "reply": "Đã hủy.",
                "exact_spoken_reply": "Đã hủy.",
            },
            status_code=409,
        )
    return JSONResponse(
        {
            "ok": False,
            "error": "Mã xác nhận không hợp lệ hoặc đã được sử dụng.",
        },
        status_code=400,
    )


async def stage_or_execute_rest_confirmation(
    *,
    request: Request,
    sess: Any,
    body: dict[str, Any] | None,
    action_kind: str,
    payload: dict[str, Any],
    prompt_summary: str,
    source: str,
    expected_payload_match: dict[str, Any] | None = None,
) -> JSONResponse:
    """Stage a 4-step pending confirmation or execute after validating a single-use owner token."""
    token = _extract_confirm_token(request, body)
    if not token:
        staged = await prepare_pending_mutation(
            engine=_REST_ENGINE,
            session=sess,
            source=source,
            action_kind=action_kind,
            payload=payload,
            prompt_summary=prompt_summary,
        )
        return JSONResponse(staged["payload"], status_code=int(staged["status_code"]))

    reason, consumed = inspect_and_consume_pending_confirmation(
        token,
        owner_user_id=str(sess.user_id),
        new_status="confirmed",
        expected_action_kind=action_kind,
        expected_payload_match=expected_payload_match,
    )
    if reason != "ok" or consumed is None:
        return _confirmation_failure_response(reason)

    res = await execute_confirmed_mutation(
        engine=_REST_ENGINE,
        session=sess,
        source=source,
        action_kind=consumed["action_kind"],
        payload=consumed["payload"],
    )
    if int(res["status_code"]) == 200:
        await broadcast_rest_state_to_bridges()
        snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
        res["payload"]["snapshot"] = snap
    return JSONResponse(res["payload"], status_code=int(res["status_code"]))


async def _handle_confirm_automation(
    request: Request,
    body: dict[str, Any],
    *,
    path_pending_id: str = "",
) -> JSONResponse:
    sess, err = _require_auth(request, body)
    if err is not None:
        return err
    g_err = _deny_guest_tier3(sess, "POST /api/automation/confirm")
    if g_err is not None:
        return g_err

    pid = str(path_pending_id or _extract_confirm_token(request, body)).strip()
    if not pid:
        return JSONResponse({"ok": False, "error": "Thiếu pending_id / confirm_token xác nhận."}, status_code=400)

    confirmed = _parse_confirmed_flag(body)
    new_status = "confirmed" if confirmed else "cancelled"
    reason, row = inspect_and_consume_pending_confirmation(
        pid,
        owner_user_id=str(sess.user_id),
        new_status=new_status,
    )
    if reason != "ok" or row is None:
        return _confirmation_failure_response(reason)

    if not confirmed:
        await _REST_ENGINE.emit({
            "type": "pending_confirmation_cancelled",
            "pending_id": pid,
            "owner_user_id": str(sess.user_id),
        })
        await broadcast_rest_state_to_bridges()
        snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
        return JSONResponse(
            {
                "ok": False,
                "cancelled": True,
                "kind": "confirmation_cancelled",
                "pending_id": pid,
                "reply": "Đã hủy.",
                "exact_spoken_reply": "Đã hủy.",
                "snapshot": snap,
            },
            status_code=200,
        )

    res = await execute_confirmed_mutation(
        engine=_REST_ENGINE,
        session=sess,
        source=f"REST ({sess.display_name})",
        action_kind=row["action_kind"],
        payload=row["payload"],
    )
    if int(res["status_code"]) == 200:
        await broadcast_rest_state_to_bridges()
        res["payload"]["snapshot"] = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse(res["payload"], status_code=int(res["status_code"]))


async def _optional_json_body(request: Request) -> dict[str, Any]:
    """Read an optional JSON dict body without rejecting empty DELETE requests."""
    try:
        raw = await request.body()
        if not raw or not raw.strip():
            return {}
        import json as _json

        parsed = _json.loads(raw.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _parse_hhmm_or_error(raw_hhmm: str) -> tuple[str | None, JSONResponse | None]:
    txt = str(raw_hhmm or "").strip()
    if ":" not in txt:
        return None, JSONResponse({"ok": False, "error": "Giờ phải nằm trong 00:00 đến 23:59."}, status_code=400)
    try:
        hh, mm = [int(p) for p in txt.split(":", 1)]
    except (TypeError, ValueError):
        return None, JSONResponse({"ok": False, "error": "Giờ phải nằm trong 00:00 đến 23:59."}, status_code=400)
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None, JSONResponse({"ok": False, "error": "Giờ phải nằm trong 00:00 đến 23:59."}, status_code=400)
    return f"{hh:02d}:{mm:02d}", None


@router.post("/api/automation/confirm")
async def api_confirm_automation(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    body = payload if isinstance(payload, dict) else {}
    return await _handle_confirm_automation(request, body)


@router.post("/api/confirmations/{pending_id}")
async def api_confirm_automation_by_id(
    request: Request,
    pending_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> JSONResponse:
    body = payload if isinstance(payload, dict) else {}
    return await _handle_confirm_automation(request, body, path_pending_id=pending_id)


@router.get("/api/automation")
async def api_get_automation_overview(request: Request) -> JSONResponse:
    sess, err = _require_auth(request)
    if err is not None:
        return err
    g_err = _deny_guest_tier3(sess, "GET /api/automation")
    if g_err is not None:
        return g_err
    _REST_ENGINE.sync_from_shared_store(force=True)
    snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse({
        "ok": True,
        "tier": int(sess.tier),
        "timers": snap.get("timers", []),
        "schedules": snap.get("schedules", []),
        "automation_rules": snap.get("automation_rules", []),
        "custom_commands": snap.get("custom_commands", []),
        "scenes": snap.get("scenes", snap.get("custom_commands", [])),
    })


# =============================================================================
# TIMERS
# =============================================================================

@router.post("/api/timers")
async def api_create_timer(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    body = payload if isinstance(payload, dict) else {}
    sess, err = _require_auth(request, body)
    if err is not None:
        return err
    if not _can_manage_timers(sess):
        return _deny_guest_tier3(sess, "POST /api/timers")

    device_id = str(body.get("device_id") or "living_room_light").strip()
    action = str(body.get("action") or "turn_on").strip().lower()
    if action not in ACTION_TO_STATE:
        action = "turn_on"

    target_devs = (
        ["living_room_light", "bedroom_light"]
        if device_id == "all_lights"
        else (list(DEFAULT_DEVICES.keys()) if device_id == "all_devices" else [device_id])
    )
    for td in target_devs:
        if td not in DEFAULT_DEVICES:
            return JSONResponse({"ok": False, "error": f"Thiết bị '{td}' không hợp lệ."}, status_code=400)
        if not can_control_device(int(sess.tier), td):
            msg = f"Từ chối: Bậc {sess.tier} không có quyền hẹn giờ thiết bị {td}."
            append_audit_log("SECURITY", "timer_rbac_blocked", msg, user_name=sess.display_name, tier=int(sess.tier))
            return JSONResponse({"ok": False, "rbac_blocked": True, "error": msg}, status_code=403)

    try:
        hours = max(0.0, float(body.get("hours") or 0.0))
        minutes = max(0.0, float(body.get("minutes") or 0.0))
        seconds = max(0.0, float(body.get("seconds") or 0.0))
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "Thời gian đếm ngược không hợp lệ."}, status_code=400)
    if hours <= 0 and minutes <= 0 and seconds <= 0:
        seconds = 10.0
    repeat = str(body.get("repeat") or "once").strip() or "once"

    total_sec = hours * 3600.0 + minutes * 60.0 + seconds
    fire_epoch = time.time() + total_sec
    conflict_msg = check_tier1_schedule_conflict(
        actor_tier=int(sess.tier),
        fire_epoch=fire_epoch,
        schedule_type=repeat,
        engine=_REST_ENGINE,
    )
    if conflict_msg:
        append_audit_log(
            "SECURITY",
            "timer_conflict_tier1",
            f"RBAC Chặn Cấp 2 ({sess.display_name}) đặt hẹn giờ trùng lịch Cấp 1: {conflict_msg}",
            user_name=sess.display_name,
            tier=int(sess.tier),
        )
        return JSONResponse(
            {
                "ok": False,
                "rbac_blocked": True,
                "conflict_tier1": True,
                "error": conflict_msg,
                "exact_spoken_reply": conflict_msg,
            },
            status_code=409,
        )

    sec_i = max(1, int(round(total_sec)))
    summary = f"Đặt hẹn giờ sau {sec_i} giây sẽ {format_device_action_vi(device_id, action).lower()}"
    return await stage_or_execute_rest_confirmation(
        request=request,
        sess=sess,
        body=body,
        action_kind="create_timer",
        payload={
            "device_id": device_id,
            "action": action,
            "hours": hours,
            "minutes": minutes,
            "seconds": seconds,
            "repeat": repeat,
        },
        prompt_summary=summary,
        source=f"REST ({sess.display_name})",
    )


@router.patch("/api/timers/{timer_id}")
@router.put("/api/timers/{timer_id}")
async def api_update_timer(
    request: Request,
    timer_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> JSONResponse:
    body = payload if isinstance(payload, dict) else {}
    sess, err = _require_auth(request, body)
    if err is not None:
        return err
    if not _can_manage_timers(sess):
        return _deny_guest_tier3(sess, "PATCH /api/timers")

    existing = _REST_ENGINE.active_timers.get(timer_id) or next(
        (r for r in list_pending_timers() if str(r.get("timer_id") or r.get("id")) == str(timer_id)),
        None,
    )
    if existing is None:
        return JSONResponse({"ok": False, "error": "Không tìm thấy hẹn giờ cần cập nhật."}, status_code=404)

    eff_tier = int(sess.tier)
    owner_id = str(existing.get("owner_user_id") or existing.get("owner_id") or "")
    owner_tier = int(existing.get("owner_tier") or 1)
    if eff_tier == 2 and not _REST_ENGINE.system_policies.get("tier2_can_override_tier1", False):
        if owner_tier == 1:
            append_audit_log("SECURITY", "timer_update_blocked", f"RBAC Chặn Cấp 2 ({sess.display_name}) sửa hẹn giờ Cấp 1 {timer_id}", user_name=sess.display_name, tier=eff_tier)
            return JSONResponse({"ok": False, "rbac_blocked": True, "error": "Không thể sửa hẹn giờ của Chủ nhà (Tầng 1)."}, status_code=403)
        if owner_id != sess.user_id:
            append_audit_log("SECURITY", "timer_update_blocked", f"RBAC Chặn {sess.display_name} sửa hẹn giờ của {owner_id}", user_name=sess.display_name, tier=eff_tier)
            return JSONResponse({"ok": False, "rbac_blocked": True, "error": "Bạn chỉ có quyền sửa hẹn giờ của chính mình."}, status_code=403)

    target_dev = str(body.get("device_id") or existing.get("raw_target") or existing.get("device_id") or "living_room_light").strip()
    new_action = str(body.get("new_action") or body.get("action") or existing.get("action") or "turn_on").strip().lower()
    if new_action not in ACTION_TO_STATE:
        return JSONResponse({"ok": False, "error": f"Hành động '{new_action}' không hợp lệ."}, status_code=400)
    target_devs = (
        ["living_room_light", "bedroom_light"]
        if target_dev == "all_lights"
        else (list(DEFAULT_DEVICES.keys()) if target_dev == "all_devices" else [target_dev])
    )
    for td in target_devs:
        if td not in DEFAULT_DEVICES:
            return JSONResponse({"ok": False, "error": f"Thiết bị '{td}' không hợp lệ."}, status_code=400)
        if not can_control_device(eff_tier, td):
            return JSONResponse({"ok": False, "rbac_blocked": True, "error": f"Bậc {eff_tier} không có quyền điều khiển {td}."}, status_code=403)

    try:
        has_time_fields = any(k in body for k in ("hours", "minutes", "seconds"))
        if has_time_fields:
            hours = max(0.0, float(body.get("hours") or 0.0))
            minutes = max(0.0, float(body.get("minutes") or 0.0))
            seconds = max(0.0, float(body.get("seconds") or 0.0))
        else:
            hours = 0.0
            minutes = 0.0
            seconds = max(1.0, float(existing.get("delay_seconds") or 10.0))
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "Thời gian đếm ngược không hợp lệ."}, status_code=400)

    total_sec = hours * 3600.0 + minutes * 60.0 + seconds
    repeat = str(body.get("repeat") or existing.get("repeat_rule") or "once").strip() or "once"
    if total_sec <= 0:
        seconds = max(1.0, float(existing.get("delay_seconds") or 10.0))
        total_sec = seconds

    conflict_msg = check_tier1_schedule_conflict(
        actor_tier=eff_tier,
        fire_epoch=time.time() + total_sec,
        schedule_type=repeat,
        exclude_timer_id=timer_id,
        engine=_REST_ENGINE,
    )
    if conflict_msg:
        append_audit_log("SECURITY", "timer_conflict_tier1", f"RBAC Chặn Cấp 2 ({sess.display_name}) sửa hẹn giờ trùng lịch Cấp 1: {conflict_msg}", user_name=sess.display_name, tier=eff_tier)
        return JSONResponse(
            {"ok": False, "rbac_blocked": True, "conflict_tier1": True, "error": conflict_msg, "exact_spoken_reply": conflict_msg},
            status_code=409,
        )

    sec_i = max(1, int(round(total_sec)))
    summary = f"Cập nhật hẹn giờ sau {sec_i} giây sẽ {format_device_action_vi(target_dev, new_action).lower()}"
    return await stage_or_execute_rest_confirmation(
        request=request,
        sess=sess,
        body=body,
        action_kind="modify_timer",
        payload={
            "timer_id": timer_id,
            "device_id": target_dev,
            "new_action": new_action,
            "hours": hours,
            "minutes": minutes,
            "seconds": seconds,
            "repeat": repeat,
        },
        prompt_summary=summary,
        source=f"REST ({sess.display_name})",
        expected_payload_match={"timer_id": timer_id},
    )


@router.delete("/api/timers/{timer_id}")
async def api_delete_timer(request: Request, timer_id: str) -> JSONResponse:
    body = await _optional_json_body(request)
    sess, err = _require_auth(request, body)
    if err is not None:
        return err
    g_err = _deny_guest_tier3(sess, "DELETE /api/timers")
    if g_err is not None:
        return g_err

    existing = _REST_ENGINE.active_timers.get(timer_id) or next(
        (r for r in list_pending_timers() if str(r.get("timer_id") or r.get("id")) == str(timer_id)),
        None,
    )
    if existing is None:
        return JSONResponse({"ok": False, "error": "Không tìm thấy hẹn giờ cần hủy."}, status_code=404)

    eff_tier = int(sess.tier)
    owner_id = str(existing.get("owner_user_id") or existing.get("owner_id") or "")
    owner_tier = int(existing.get("owner_tier") or 1)
    if eff_tier == 2 and not _REST_ENGINE.system_policies.get("tier2_can_override_tier1", False):
        if owner_tier == 1:
            msg = "Không thể hủy hẹn giờ của Chủ nhà (Tầng 1)."
            append_audit_log("SECURITY", "timer_delete_blocked", msg, user_name=sess.display_name, tier=eff_tier)
            return JSONResponse({"ok": False, "rbac_blocked": True, "error": msg}, status_code=403)
        if owner_id != sess.user_id:
            msg = "Bạn chỉ được hủy hẹn giờ do chính bạn đặt."
            append_audit_log("SECURITY", "timer_delete_blocked", msg, user_name=sess.display_name, tier=eff_tier)
            return JSONResponse({"ok": False, "rbac_blocked": True, "error": msg}, status_code=403)

    dev_name = str(existing.get("device_id") or "thiết bị")
    return await stage_or_execute_rest_confirmation(
        request=request,
        sess=sess,
        body=body,
        action_kind="delete_timer",
        payload={"timer_id": timer_id},
        prompt_summary=f"Hủy hẹn giờ {dev_name}",
        source=f"REST ({sess.display_name})",
        expected_payload_match={"timer_id": timer_id},
    )


# =============================================================================
# CLOCK SCHEDULES (Asia/Saigon, once / daily)
# =============================================================================

@router.get("/api/schedules")
async def api_list_schedules(request: Request) -> JSONResponse:
    sess, err = _require_auth(request)
    if err is not None:
        return err
    g_err = _deny_guest_tier3(sess, "GET /api/schedules")
    if g_err is not None:
        return g_err
    snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse({"ok": True, "schedules": snap.get("schedules", [])})


@router.post("/api/schedules")
async def api_create_schedule(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    body = payload if isinstance(payload, dict) else {}
    sess, err = _require_auth(request, body)
    if err is not None:
        return err
    if not _can_manage_timers(sess):
        return _deny_guest_tier3(sess, "POST /api/schedules")

    device_id = str(body.get("device_id") or "").strip()
    action = str(body.get("action") or "turn_on").strip().lower()
    time_hhmm = str(body.get("time_hhmm") or "").strip()
    schedule_type = str(body.get("schedule_type") or body.get("repeat") or "once").strip().lower()
    run_date_vn = str(body.get("run_date_vn") or "").strip()
    label = str(body.get("label") or "").strip()

    if device_id not in DEFAULT_DEVICES:
        return JSONResponse({"ok": False, "error": f"Thiết bị '{device_id}' không hợp lệ."}, status_code=400)
    if not can_control_device(int(sess.tier), device_id):
        msg = f"Từ chối: Bậc {sess.tier} không có quyền đặt lịch cho {device_id}."
        append_audit_log("SECURITY", "schedule_rbac_blocked", msg, user_name=sess.display_name, tier=int(sess.tier))
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": msg}, status_code=403)
    if action not in ACTION_TO_STATE:
        return JSONResponse({"ok": False, "error": f"Hành động '{action}' không hợp lệ."}, status_code=400)
    hhmm_norm, hhmm_err = _parse_hhmm_or_error(time_hhmm)
    if hhmm_err is not None or hhmm_norm is None:
        return hhmm_err
    st_type = "daily" if schedule_type == "daily" else "once"

    conflict_msg = check_tier1_schedule_conflict(
        actor_tier=int(sess.tier),
        time_hhmm=hhmm_norm,
        schedule_type=st_type,
        run_date_vn=run_date_vn,
        engine=_REST_ENGINE,
    )
    if conflict_msg:
        append_audit_log(
            "SECURITY",
            "schedule_conflict_tier1",
            f"RBAC Chặn Cấp 2 ({sess.display_name}) đặt lịch {hhmm_norm} trùng Cấp 1: {conflict_msg}",
            user_name=sess.display_name,
            tier=int(sess.tier),
        )
        return JSONResponse(
            {
                "ok": False,
                "rbac_blocked": True,
                "conflict_tier1": True,
                "error": conflict_msg,
                "exact_spoken_reply": conflict_msg,
            },
            status_code=409,
        )

    rep_txt = "hằng ngày" if st_type == "daily" else "một lần"
    summary = f"Đặt lịch {format_device_action_vi(device_id, action).lower()} lúc {hhmm_norm} ({rep_txt})"
    return await stage_or_execute_rest_confirmation(
        request=request,
        sess=sess,
        body=body,
        action_kind="create_schedule",
        payload={
            "target_devs": [device_id],
            "action": action,
            "time_hhmm": hhmm_norm,
            "schedule_type": st_type,
            "run_date_vn": run_date_vn,
            "label": label,
        },
        prompt_summary=summary,
        source=f"REST ({sess.display_name})",
    )


@router.patch("/api/schedules/{schedule_id}")
@router.put("/api/schedules/{schedule_id}")
async def api_update_schedule(request: Request, schedule_id: str, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    body = payload if isinstance(payload, dict) else {}
    sess, err = _require_auth(request, body)
    if err is not None:
        return err
    if not _can_manage_timers(sess):
        return _deny_guest_tier3(sess, "PATCH /api/schedules")

    existing = next((s for s in list_schedules(include_disabled=True) if s["schedule_id"] == schedule_id), None)
    if existing is None:
        return JSONResponse({"ok": False, "error": "Không tìm thấy lịch hẹn."}, status_code=404)
    if int(sess.tier) > 1 and existing["owner_user_id"] != sess.user_id:
        append_audit_log("SECURITY", "schedule_update_blocked", f"RBAC Chặn {sess.display_name} sửa lịch của {existing['owner_user_id']}", user_name=sess.display_name, tier=int(sess.tier))
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": "Bạn chỉ có quyền sửa lịch của chính mình."}, status_code=403)

    new_dev = str(body.get("device_id") or "").strip() or None
    if new_dev is not None:
        if new_dev not in DEFAULT_DEVICES:
            return JSONResponse({"ok": False, "error": f"Thiết bị '{new_dev}' không hợp lệ."}, status_code=400)
        if not can_control_device(int(sess.tier), new_dev):
            return JSONResponse({"ok": False, "rbac_blocked": True, "error": f"Bậc {sess.tier} không có quyền điều khiển {new_dev}."}, status_code=403)

    new_action = str(body.get("action") or "").strip().lower() or None
    if new_action is not None and new_action not in ACTION_TO_STATE:
        return JSONResponse({"ok": False, "error": f"Hành động '{new_action}' không hợp lệ."}, status_code=400)

    new_hhmm: str | None = None
    if "time_hhmm" in body and body.get("time_hhmm") is not None:
        new_hhmm, hhmm_err = _parse_hhmm_or_error(str(body.get("time_hhmm")))
        if hhmm_err is not None:
            return hhmm_err

    new_type = str(body.get("schedule_type") or body.get("repeat") or "").strip().lower() or None
    if new_type is not None:
        new_type = "daily" if new_type == "daily" else "once"
    new_run_date = str(body.get("run_date_vn") or "").strip() if "run_date_vn" in body else None
    new_enabled = bool(body.get("enabled")) if "enabled" in body else bool(existing.get("enabled", True))
    if new_enabled:
        cand_hhmm = new_hhmm or existing["time_hhmm"]
        cand_type = new_type or existing["schedule_type"]
        cand_date = new_run_date if new_run_date is not None else str(existing.get("run_date_vn") or "")
        conflict_msg = check_tier1_schedule_conflict(
            actor_tier=int(sess.tier),
            time_hhmm=cand_hhmm,
            schedule_type=cand_type,
            run_date_vn=cand_date,
            exclude_schedule_id=schedule_id,
            engine=_REST_ENGINE,
        )
        if conflict_msg:
            append_audit_log("SECURITY", "schedule_conflict_tier1", f"RBAC Chặn Cấp 2 ({sess.display_name}) sửa lịch trùng Cấp 1", user_name=sess.display_name, tier=int(sess.tier))
            return JSONResponse(
                {"ok": False, "rbac_blocked": True, "conflict_tier1": True, "error": conflict_msg, "exact_spoken_reply": conflict_msg},
                status_code=409,
            )

    cand_dev = new_dev or existing["device_id"]
    cand_act = new_action or existing["action"]
    cand_time = new_hhmm or existing["time_hhmm"]
    summary = f"Cập nhật lịch {format_device_action_vi(cand_dev, cand_act).lower()} lúc {cand_time}"
    update_payload: dict[str, Any] = {
        "schedule_id": schedule_id,
        "time_hhmm": new_hhmm,
        "schedule_type": new_type,
        "device_id": new_dev,
        "action": new_action,
        "enabled": body.get("enabled") if "enabled" in body else None,
        "label": body.get("label"),
    }
    if new_run_date is not None:
        update_payload["run_date_vn"] = new_run_date
    return await stage_or_execute_rest_confirmation(
        request=request,
        sess=sess,
        body=body,
        action_kind="update_schedule",
        payload=update_payload,
        prompt_summary=summary,
        source=f"REST ({sess.display_name})",
        expected_payload_match={"schedule_id": schedule_id},
    )


@router.delete("/api/schedules/{schedule_id}")
async def api_delete_schedule(request: Request, schedule_id: str) -> JSONResponse:
    body = await _optional_json_body(request)
    sess, err = _require_auth(request, body)
    if err is not None:
        return err
    if not _can_manage_timers(sess):
        return _deny_guest_tier3(sess, "DELETE /api/schedules")

    existing = next((s for s in list_schedules(include_disabled=True) if s["schedule_id"] == schedule_id), None)
    if existing is None:
        return JSONResponse({"ok": False, "error": "Không tìm thấy lịch hẹn."}, status_code=404)
    if int(sess.tier) > 1 and existing["owner_user_id"] != sess.user_id:
        append_audit_log("SECURITY", "schedule_delete_blocked", f"RBAC Chặn {sess.display_name} xóa lịch của {existing['owner_user_id']}", user_name=sess.display_name, tier=int(sess.tier))
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": "Bạn chỉ có quyền xóa lịch của chính mình."}, status_code=403)

    summary = f"Xóa lịch {format_device_action_vi(existing['device_id'], existing['action']).lower()} lúc {existing['time_hhmm']}"
    return await stage_or_execute_rest_confirmation(
        request=request,
        sess=sess,
        body=body,
        action_kind="delete_schedule",
        payload={"schedule_id": schedule_id},
        prompt_summary=summary,
        source=f"REST ({sess.display_name})",
        expected_payload_match={"schedule_id": schedule_id},
    )


# =============================================================================
# LINKED AUTOMATION RULES (when devA == state -> then devB action)
# =============================================================================

@router.get("/api/rules")
async def api_list_rules(request: Request) -> JSONResponse:
    sess, err = _require_auth(request)
    if err is not None:
        return err
    g_err = _deny_guest_tier3(sess, "GET /api/rules")
    if g_err is not None:
        return g_err
    snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse({"ok": True, "rules": snap.get("automation_rules", [])})


@router.post("/api/rules")
async def api_create_rule(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    body = payload if isinstance(payload, dict) else {}
    sess, err = _require_auth(request, body)
    if err is not None:
        return err
    if not _can_manage_rules(sess):
        return _deny_guest_tier3(sess, "POST /api/rules")
    if not can_user_create_links(sess.user_id, int(sess.tier), engine=_REST_ENGINE):
        msg = "Cấp 2 chưa được Chủ nhà cấp quyền tạo luật liên kết ạ."
        append_audit_log("SECURITY", "rule_link_permission_blocked", f"RBAC Chặn Cấp 2 ({sess.display_name}) tạo liên kết khi chưa được cấp quyền", user_name=sess.display_name, tier=int(sess.tier))
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": msg, "exact_spoken_reply": msg}, status_code=403)

    wdev = str(body.get("when_device_id") or "").strip()
    wstate = str(body.get("when_state") or "ON").strip().upper()
    tdev = str(body.get("then_device_id") or "").strip()
    tact = str(body.get("then_action") or "turn_on").strip().lower()
    edev = str(body.get("else_device_id") or "").strip()
    eact = str(body.get("else_action") or "").strip().lower()
    delay_sec = float(body.get("delay_seconds") or 0.0)
    label = str(body.get("label") or "").strip()

    if tdev in DEFAULT_DEVICES and not can_control_device(int(sess.tier), tdev):
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": f"Bậc {sess.tier} không có quyền điều khiển {tdev}."}, status_code=403)
    if edev and edev in DEFAULT_DEVICES and not can_control_device(int(sess.tier), edev):
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": f"Bậc {sess.tier} không có quyền điều khiển {edev}."}, status_code=403)

    try:
        v_wdev, v_wstate, v_tdev, v_tact, v_edev, v_eact = validate_automation_rule_input(
            when_device_id=wdev,
            when_state=wstate,
            then_device_id=tdev,
            then_action=tact,
            else_device_id=edev,
            else_action=eact,
        )
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    summary = f"Tạo liên kết khi {DEFAULT_DEVICES[v_wdev]['name']} {v_wstate} thì {format_device_action_vi(v_tdev, v_tact).lower()}"
    return await stage_or_execute_rest_confirmation(
        request=request,
        sess=sess,
        body=body,
        action_kind="create_automation_rule",
        payload={
            "when_device_id": v_wdev,
            "when_state": v_wstate,
            "then_device_id": v_tdev,
            "then_action": v_tact,
            "else_device_id": v_edev,
            "else_action": v_eact,
            "delay_seconds": delay_sec,
            "label": label,
        },
        prompt_summary=summary,
        source=f"REST ({sess.display_name})",
    )


@router.delete("/api/rules/{rule_id}")
async def api_delete_rule(request: Request, rule_id: str) -> JSONResponse:
    body = await _optional_json_body(request)
    sess, err = _require_auth(request, body)
    if err is not None:
        return err
    if not _can_manage_rules(sess):
        return _deny_guest_tier3(sess, "DELETE /api/rules")

    existing = next((r for r in list_automation_rules(include_disabled=True) if r["rule_id"] == rule_id), None)
    if existing is None:
        return JSONResponse({"ok": False, "error": "Không tìm thấy luật liên kết."}, status_code=404)
    if int(sess.tier) > 1 and existing["owner_user_id"] != sess.user_id:
        append_audit_log("SECURITY", "rule_delete_blocked", f"RBAC Chặn {sess.display_name} xóa luật của {existing['owner_user_id']}", user_name=sess.display_name, tier=int(sess.tier))
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": "Bạn chỉ có quyền xóa luật của chính mình."}, status_code=403)

    return await stage_or_execute_rest_confirmation(
        request=request,
        sess=sess,
        body=body,
        action_kind="delete_automation_rule",
        payload={"rule_id": rule_id},
        prompt_summary=f"Xóa luật liên kết '{existing.get('label') or rule_id}'",
        source=f"REST ({sess.display_name})",
        expected_payload_match={"rule_id": rule_id},
    )


# =============================================================================
# CUSTOM COMMANDS / MULTI-STEP SCENES
# =============================================================================

@router.get("/api/scenes")
async def api_list_scenes(request: Request) -> JSONResponse:
    sess, err = _require_auth(request)
    if err is not None:
        return err
    g_err = _deny_guest_tier3(sess, "GET /api/scenes")
    if g_err is not None:
        return g_err
    snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse({"ok": True, "scenes": snap.get("scenes", snap.get("custom_commands", []))})


@router.post("/api/scenes")
async def api_create_scene(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    body = payload if isinstance(payload, dict) else {}
    sess, err = _require_auth(request, body)
    if err is not None:
        return err
    if not _can_manage_rules(sess):
        return _deny_guest_tier3(sess, "POST /api/scenes")

    phrase = str(body.get("phrase") or "").strip()
    if not normalize_phrase(phrase):
        return JSONResponse({"ok": False, "error": "Tên câu lệnh không được để trống."}, status_code=400)
    steps = body.get("steps")
    if not isinstance(steps, list) or not steps:
        steps_text = str(body.get("steps_text") or body.get("actions_text") or "").strip()
        steps = parse_multi_steps_from_text(steps_text)
    clean_steps = _normalize_steps(steps if isinstance(steps, list) else [])
    if not clean_steps:
        return JSONResponse({"ok": False, "error": "Chưa có bước thực hiện hợp lệ nào."}, status_code=400)

    allowed_steps, rbac_msg = check_steps_rbac(clean_steps, int(sess.tier))
    if not allowed_steps:
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": rbac_msg}, status_code=403)

    step_summary = ", ".join(format_device_action_vi(s["device_id"], s["action"]).lower() for s in clean_steps)
    return await stage_or_execute_rest_confirmation(
        request=request,
        sess=sess,
        body=body,
        action_kind="create_custom_command",
        payload={"phrase": phrase, "steps": clean_steps},
        prompt_summary=f"Tạo lệnh '{phrase}' gồm: {step_summary}",
        source=f"REST ({sess.display_name})",
    )


@router.put("/api/scenes/{command_id}")
@router.patch("/api/scenes/{command_id}")
async def api_update_scene(request: Request, command_id: str, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    body = payload if isinstance(payload, dict) else {}
    sess, err = _require_auth(request, body)
    if err is not None:
        return err
    if not _can_manage_rules(sess):
        return _deny_guest_tier3(sess, "PATCH /api/scenes")

    existing = next((c for c in list_custom_commands(include_disabled=True) if c["command_id"] == command_id), None)
    if existing is None:
        return JSONResponse({"ok": False, "error": "Không tìm thấy ngữ cảnh."}, status_code=404)
    if int(sess.tier) > 1 and existing["owner_user_id"] != sess.user_id:
        append_audit_log("SECURITY", "scene_update_blocked", f"RBAC Chặn {sess.display_name} sửa lệnh custom của {existing['owner_user_id']}", user_name=sess.display_name, tier=int(sess.tier))
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": "Bạn chỉ có quyền sửa ngữ cảnh của chính mình."}, status_code=403)

    phrase = str(body.get("phrase") or existing["phrase"]).strip()
    if not normalize_phrase(phrase):
        return JSONResponse({"ok": False, "error": "Tên câu lệnh không được để trống."}, status_code=400)
    steps = body.get("steps")
    if not isinstance(steps, list) or not steps:
        steps_text = str(body.get("steps_text") or "").strip()
        steps = parse_multi_steps_from_text(steps_text) if steps_text else existing["steps"]
    clean_steps = _normalize_steps(steps if isinstance(steps, list) else [])
    if not clean_steps:
        return JSONResponse({"ok": False, "error": "Chưa có bước thực hiện hợp lệ nào."}, status_code=400)
    enabled = bool(body.get("enabled")) if "enabled" in body else existing["enabled"]

    allowed_steps, rbac_msg = check_steps_rbac(clean_steps, int(sess.tier))
    if not allowed_steps:
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": rbac_msg}, status_code=403)

    return await stage_or_execute_rest_confirmation(
        request=request,
        sess=sess,
        body=body,
        action_kind="update_custom_command",
        payload={"command_id": command_id, "phrase": phrase, "steps": clean_steps, "enabled": enabled},
        prompt_summary=f"Cập nhật ngữ cảnh '{phrase}'",
        source=f"REST ({sess.display_name})",
        expected_payload_match={"command_id": command_id},
    )


@router.delete("/api/scenes/{command_id}")
async def api_delete_scene(request: Request, command_id: str) -> JSONResponse:
    body = await _optional_json_body(request)
    sess, err = _require_auth(request, body)
    if err is not None:
        return err
    if not _can_manage_rules(sess):
        return _deny_guest_tier3(sess, "DELETE /api/scenes")

    existing = next((c for c in list_custom_commands(include_disabled=True) if c["command_id"] == command_id), None)
    if existing is None:
        return JSONResponse({"ok": False, "error": "Không tìm thấy ngữ cảnh."}, status_code=404)
    if int(sess.tier) > 1 and existing["owner_user_id"] != sess.user_id:
        append_audit_log("SECURITY", "scene_delete_blocked", f"RBAC Chặn {sess.display_name} xóa lệnh custom của {existing['owner_user_id']}", user_name=sess.display_name, tier=int(sess.tier))
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": "Bạn chỉ có quyền xóa ngữ cảnh của chính mình."}, status_code=403)

    return await stage_or_execute_rest_confirmation(
        request=request,
        sess=sess,
        body=body,
        action_kind="delete_custom_command",
        payload={"command_id": command_id},
        prompt_summary=f"Xóa ngữ cảnh '{existing['phrase']}'",
        source=f"REST ({sess.display_name})",
        expected_payload_match={"command_id": command_id},
    )


@router.post("/api/scenes/{command_id}/run")
async def api_run_scene(request: Request, command_id: str) -> JSONResponse:
    sess, err = _require_auth(request)
    if err is not None:
        return err
    g_err = _deny_guest_tier3(sess, "POST /api/scenes/run")
    if g_err is not None:
        return g_err
    res = await _REST_ENGINE.execute_custom_scene(
        command_id,
        session=sess,
        source=f"REST ({sess.display_name})",
    )
    if not res.get("ok"):
        code = 403 if res.get("rbac_blocked") else 404
        return JSONResponse(res, status_code=code)
    await broadcast_rest_state_to_bridges()
    snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse({**res, "reply": res.get("exact_spoken_reply", ""), "snapshot": snap})


@router.post("/api/members/{user_id}/link_permission")
async def api_set_member_link_permission(
    request: Request,
    user_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> JSONResponse:
    body = payload if isinstance(payload, dict) else {}
    sess, err = _require_auth(request, body)
    if err is not None:
        return err
    if int(getattr(sess, "tier", 3) or 3) != 1:
        msg = GUEST_ONLY_TOGGLE_MSG_VI if int(sess.tier) >= 3 else "Chỉ Chủ nhà (Cấp 1) mới có quyền phân quyền liên kết ạ."
        append_audit_log("SECURITY", "member_perm_blocked", f"RBAC Chặn {sess.display_name} đổi quyền liên kết cho {user_id}", user_name=sess.display_name, tier=int(sess.tier))
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": msg, "exact_spoken_reply": msg}, status_code=403)
    members = {m["user_id"]: m for m in list_household_members(include_inactive=True)}
    if user_id not in members:
        return JSONResponse({"ok": False, "error": "Không tìm thấy thành viên."}, status_code=404)
    allowed = bool(body.get("allowed", body.get("can_create_links", False)))
    target_m = members[user_id]
    verb = "Cấp quyền tạo liên kết cho" if allowed else "Thu hồi quyền tạo liên kết của"
    return await stage_or_execute_rest_confirmation(
        request=request,
        sess=sess,
        body=body,
        action_kind="set_member_link_permission",
        payload={
            "target_user_id": user_id,
            "target_name": str(target_m["full_name"]),
            "target_tier": int(target_m["tier"]),
            "allowed": allowed,
        },
        prompt_summary=f"{verb} {target_m['full_name']}",
        source=f"REST ({sess.display_name})",
        expected_payload_match={"target_user_id": user_id},
    )


async def run_scheduler_tick_once(now_override: Any = None) -> int:
    """Kiểm tra và kích hoạt lịch đồng hồ Asia/Saigon đến hạn; trả về số lịch đã kích hoạt."""
    from simulator.automation_repo import mark_schedule_fired, now_saigon

    now_vn = now_override if now_override is not None else now_saigon()
    cur_hhmm = now_vn.strftime("%H:%M")
    today_vn = now_vn.strftime("%Y-%m-%d")
    fired = 0
    for sc in await asyncio.to_thread(list_schedules, include_disabled=False):
        if str(sc.get("time_hhmm") or "") != cur_hhmm:
            continue
        if str(sc.get("last_fired_date_vn") or "") == today_vn:
            continue
        st_type = str(sc.get("schedule_type") or "once").lower()
        run_date = str(sc.get("run_date_vn") or "")
        if st_type == "once" and run_date and run_date != today_vn:
            continue
        sid = str(sc["schedule_id"])
        dev_id = str(sc["device_id"])
        act = str(sc["action"])
        owner_tier = int(sc.get("owner_tier") or 1)
        owner_name = str(sc.get("owner_name") or sc.get("owner_user_id") or "Hệ thống")

        mark_schedule_fired(
            sid,
            fired_date_vn=today_vn,
            disable_after_once=(st_type == "once"),
        )
        if not can_control_device(owner_tier, dev_id):
            append_audit_log(
                "SECURITY",
                "schedule_rbac_blocked",
                f"Bỏ qua lịch {sid} ({dev_id}:{act}) vì vượt quyền bậc {owner_tier}",
                user_name=owner_name,
                tier=owner_tier,
            )
            continue

        await _REST_ENGINE.execute_device_action(
            dev_id,
            act,
            source=f"schedule ({cur_hhmm})",
            bypass_rbac=True,
            trigger_chains=True,
        )
        append_audit_log(
            "AUTOMATION",
            "schedule_fired",
            f"Thực thi lịch {cur_hhmm} ({sc.get('label') or dev_id})",
            user_name=owner_name,
            tier=owner_tier,
        )
        await _REST_ENGINE.emit({"type": "schedule_fired", "schedule": sc, "time_hhmm": cur_hhmm})
        fired += 1

    if fired > 0:
        await broadcast_rest_state_to_bridges()
    return fired

