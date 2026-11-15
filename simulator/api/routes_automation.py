"""REST API CRUD for countdown timers, Asia/Saigon clock schedules, linked automation rules, and custom scenes."""

from __future__ import annotations

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
from simulator.automation_nlu import parse_multi_steps_from_text
from simulator.automation_repo import (
    GUEST_ONLY_TOGGLE_MSG_VI,
    can_user_create_links,
    check_steps_rbac,
    check_tier1_schedule_conflict,
    create_automation_rule,
    create_schedule,
    delete_automation_rule,
    delete_custom_command,
    delete_schedule,
    list_automation_rules,
    list_custom_commands,
    list_household_members,
    list_schedules,
    set_user_can_create_links,
    update_schedule,
    upsert_custom_command,
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

    fire_epoch = time.time() + (hours * 3600.0 + minutes * 60.0 + seconds)
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

    prev_uid = getattr(_REST_ENGINE, "_current_user_id", "tuan_anh")
    prev_role = getattr(_REST_ENGINE, "_current_role", "ADMIN")
    try:
        _REST_ENGINE._current_user_id = str(sess.user_id)
        _REST_ENGINE._current_role = str(sess.role)
        res = await _REST_ENGINE.schedule_timer_flexible(
            device_id=device_id,
            action=action,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            repeat=repeat,
        )
    finally:
        _REST_ENGINE._current_user_id = prev_uid
        _REST_ENGINE._current_role = prev_role

    if not res.get("ok"):
        err_s = str(res.get("error", ""))
        code = 409 if "Trùng lịch" in err_s else (403 if ("Từ chối" in err_s or res.get("rbac_blocked")) else 400)
        return JSONResponse(res, status_code=code)

    append_audit_log("AUTOMATION", "timer_created", f"Tạo hẹn giờ {res.get('timer_id')} ({device_id}:{action})", user_name=sess.display_name, tier=int(sess.tier))
    await broadcast_rest_state_to_bridges()
    snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse({
        "ok": True,
        "timer_id": res.get("timer_id"),
        "reply": res.get("exact_spoken_reply", ""),
        "exact_spoken_reply": res.get("exact_spoken_reply", ""),
        "timers": snap.get("timers", []),
        "snapshot": snap,
    })


@router.delete("/api/timers/{timer_id}")
async def api_delete_timer(request: Request, timer_id: str) -> JSONResponse:
    sess, err = _require_auth(request)
    if err is not None:
        return err
    g_err = _deny_guest_tier3(sess, "DELETE /api/timers")
    if g_err is not None:
        return g_err
    res = await _REST_ENGINE.cancel_timer_by_id(
        timer_id,
        actor_user_id=sess.user_id,
        actor_tier=int(sess.tier),
    )
    if not res.get("ok"):
        if res.get("rbac_blocked"):
            append_audit_log("SECURITY", "timer_delete_blocked", str(res.get("error") or ""), user_name=sess.display_name, tier=int(sess.tier))
        code = 403 if res.get("rbac_blocked") else 404
        return JSONResponse(res, status_code=code)
    await broadcast_rest_state_to_bridges()
    snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse({"ok": True, "deleted": True, "timer_id": timer_id, "snapshot": snap})


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

    try:
        conflict_msg = check_tier1_schedule_conflict(
            actor_tier=int(sess.tier),
            time_hhmm=time_hhmm,
            schedule_type=schedule_type,
            run_date_vn=run_date_vn,
            engine=_REST_ENGINE,
        )
    except Exception:
        conflict_msg = None
    if conflict_msg:
        append_audit_log(
            "SECURITY",
            "schedule_conflict_tier1",
            f"RBAC Chặn Cấp 2 ({sess.display_name}) đặt lịch {time_hhmm} trùng Cấp 1: {conflict_msg}",
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

    try:
        sc = create_schedule(
            owner_user_id=sess.user_id,
            owner_tier=int(sess.tier),
            owner_name=sess.display_name,
            device_id=device_id,
            action=action,
            time_hhmm=time_hhmm,
            schedule_type=schedule_type,
            run_date_vn=run_date_vn,
            label=label,
        )
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    _REST_ENGINE.sync_automation_pools_from_sqlite(emit_snapshot=False)
    append_audit_log("AUTOMATION", "schedule_created", f"Đặt lịch {sc['schedule_id']} ({device_id}:{action} lúc {sc['time_hhmm']})", user_name=sess.display_name, tier=int(sess.tier))
    await _REST_ENGINE.emit({"type": "schedule_created", "schedule": sc})
    await broadcast_rest_state_to_bridges()
    snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse({"ok": True, "schedule": sc, "schedules": snap.get("schedules", []), "snapshot": snap})


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
    if new_dev is not None and not can_control_device(int(sess.tier), new_dev):
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": f"Bậc {sess.tier} không có quyền điều khiển {new_dev}."}, status_code=403)

    new_enabled = bool(body.get("enabled")) if "enabled" in body else bool(existing.get("enabled", True))
    if new_enabled:
        cand_hhmm = str(body.get("time_hhmm") or existing["time_hhmm"]).strip()
        cand_type = str(body.get("schedule_type") or body.get("repeat") or existing["schedule_type"]).strip()
        try:
            conflict_msg = check_tier1_schedule_conflict(
                actor_tier=int(sess.tier),
                time_hhmm=cand_hhmm,
                schedule_type=cand_type,
                run_date_vn=str(existing.get("run_date_vn") or ""),
                exclude_schedule_id=schedule_id,
                engine=_REST_ENGINE,
            )
        except Exception:
            conflict_msg = None
        if conflict_msg:
            append_audit_log("SECURITY", "schedule_conflict_tier1", f"RBAC Chặn Cấp 2 ({sess.display_name}) sửa lịch trùng Cấp 1", user_name=sess.display_name, tier=int(sess.tier))
            return JSONResponse(
                {"ok": False, "rbac_blocked": True, "conflict_tier1": True, "error": conflict_msg, "exact_spoken_reply": conflict_msg},
                status_code=409,
            )

    try:
        updated = update_schedule(
            schedule_id,
            time_hhmm=body.get("time_hhmm"),
            schedule_type=body.get("schedule_type") or body.get("repeat"),
            device_id=new_dev,
            action=body.get("action"),
            enabled=body.get("enabled") if "enabled" in body else None,
            label=body.get("label"),
        )
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    _REST_ENGINE.sync_automation_pools_from_sqlite(emit_snapshot=False)
    append_audit_log("AUTOMATION", "schedule_updated", f"Cập nhật lịch {schedule_id}", user_name=sess.display_name, tier=int(sess.tier))
    await broadcast_rest_state_to_bridges()
    snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse({"ok": True, "schedule": updated, "schedules": snap.get("schedules", []), "snapshot": snap})


@router.delete("/api/schedules/{schedule_id}")
async def api_delete_schedule(request: Request, schedule_id: str) -> JSONResponse:
    sess, err = _require_auth(request)
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

    delete_schedule(schedule_id)
    _REST_ENGINE.sync_automation_pools_from_sqlite(emit_snapshot=False)
    append_audit_log("AUTOMATION", "schedule_deleted", f"Xóa lịch {schedule_id}", user_name=sess.display_name, tier=int(sess.tier))
    await broadcast_rest_state_to_bridges()
    snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse({"ok": True, "deleted": True, "schedule_id": schedule_id, "snapshot": snap})


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

    if not can_control_device(int(sess.tier), tdev):
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": f"Bậc {sess.tier} không có quyền điều khiển {tdev}."}, status_code=403)
    if edev and not can_control_device(int(sess.tier), edev):
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": f"Bậc {sess.tier} không có quyền điều khiển {edev}."}, status_code=403)

    try:
        rule = create_automation_rule(
            owner_user_id=sess.user_id,
            owner_tier=int(sess.tier),
            owner_name=sess.display_name,
            when_device_id=wdev,
            when_state=wstate,
            then_device_id=tdev,
            then_action=tact,
            else_device_id=edev,
            else_action=eact,
            delay_seconds=delay_sec,
            label=label,
        )
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    _REST_ENGINE.sync_automation_pools_from_sqlite(emit_snapshot=False)
    append_audit_log("AUTOMATION", "rule_created", f"Tạo luật {rule['rule_id']} ({rule['label']})", user_name=sess.display_name, tier=int(sess.tier))
    await _REST_ENGINE.emit({"type": "automation_rule_created", "rule": rule})
    await broadcast_rest_state_to_bridges()
    snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse({"ok": True, "rule": rule, "rules": snap.get("automation_rules", []), "snapshot": snap})


@router.delete("/api/rules/{rule_id}")
async def api_delete_rule(request: Request, rule_id: str) -> JSONResponse:
    sess, err = _require_auth(request)
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

    delete_automation_rule(rule_id)
    _REST_ENGINE.sync_automation_pools_from_sqlite(emit_snapshot=False)
    append_audit_log("AUTOMATION", "rule_deleted", f"Xóa luật {rule_id}", user_name=sess.display_name, tier=int(sess.tier))
    await broadcast_rest_state_to_bridges()
    snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse({"ok": True, "deleted": True, "rule_id": rule_id, "snapshot": snap})


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
    steps = body.get("steps")
    if not isinstance(steps, list) or not steps:
        steps_text = str(body.get("steps_text") or body.get("actions_text") or "").strip()
        steps = parse_multi_steps_from_text(steps_text)

    allowed_steps, rbac_msg = check_steps_rbac(steps if isinstance(steps, list) else [], int(sess.tier))
    if not allowed_steps:
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": rbac_msg}, status_code=403)

    try:
        scene = upsert_custom_command(
            phrase=phrase,
            steps=steps,
            owner_user_id=sess.user_id,
            owner_tier=int(sess.tier),
            owner_name=sess.display_name,
        )
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    _REST_ENGINE.sync_automation_pools_from_sqlite(emit_snapshot=False)
    append_audit_log("AUTOMATION", "scene_created", f"Lưu ngữ cảnh '{scene['phrase']}'", user_name=sess.display_name, tier=int(sess.tier))
    await _REST_ENGINE.emit({"type": "custom_command_created", "command": scene})
    await broadcast_rest_state_to_bridges()
    snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse({"ok": True, "scene": scene, "command": scene, "scenes": snap.get("scenes", []), "snapshot": snap})


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
    steps = body.get("steps")
    if not isinstance(steps, list) or not steps:
        steps_text = str(body.get("steps_text") or "").strip()
        steps = parse_multi_steps_from_text(steps_text) if steps_text else existing["steps"]
    enabled = bool(body.get("enabled")) if "enabled" in body else existing["enabled"]

    allowed_steps, rbac_msg = check_steps_rbac(steps, int(sess.tier))
    if not allowed_steps:
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": rbac_msg}, status_code=403)

    try:
        scene = upsert_custom_command(
            phrase=phrase,
            steps=steps,
            owner_user_id=existing["owner_user_id"],
            owner_tier=int(existing["owner_tier"]),
            enabled=enabled,
            command_id=command_id,
        )
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    _REST_ENGINE.sync_automation_pools_from_sqlite(emit_snapshot=False)
    append_audit_log("AUTOMATION", "scene_updated", f"Cập nhật ngữ cảnh '{scene['phrase']}'", user_name=sess.display_name, tier=int(sess.tier))
    await broadcast_rest_state_to_bridges()
    snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse({"ok": True, "scene": scene, "command": scene, "scenes": snap.get("scenes", []), "snapshot": snap})


@router.delete("/api/scenes/{command_id}")
async def api_delete_scene(request: Request, command_id: str) -> JSONResponse:
    sess, err = _require_auth(request)
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

    delete_custom_command(command_id)
    _REST_ENGINE.sync_automation_pools_from_sqlite(emit_snapshot=False)
    append_audit_log("AUTOMATION", "scene_deleted", f"Xóa ngữ cảnh '{existing['phrase']}'", user_name=sess.display_name, tier=int(sess.tier))
    await broadcast_rest_state_to_bridges()
    snap = _REST_ENGINE.get_snapshot(session=sess, sync=False)
    return JSONResponse({"ok": True, "deleted": True, "command_id": command_id, "snapshot": snap})


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
    res = set_user_can_create_links(user_id, allowed, owner_tier=int(target_m["tier"]), display_name=str(target_m["full_name"]))
    append_audit_log(
        "SECURITY",
        "member_link_permission_updated",
        f"Chủ nhà cập nhật quyền tạo liên kết cho {target_m['full_name']} ({user_id}): {allowed}",
        user_name=sess.display_name,
        tier=1,
    )
    await broadcast_rest_state_to_bridges()
    return JSONResponse({"ok": True, **res})


async def run_scheduler_tick_once(now_override: Any = None) -> int:
    """Kiểm tra và kích hoạt lịch đồng hồ Asia/Saigon đến hạn; trả về số lịch đã kích hoạt."""
    from simulator.automation_repo import mark_schedule_fired, now_saigon

    now_vn = now_override if now_override is not None else now_saigon()
    cur_hhmm = now_vn.strftime("%H:%M")
    today_vn = now_vn.strftime("%Y-%m-%d")
    fired = 0
    for sc in list_schedules(include_disabled=False):
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

