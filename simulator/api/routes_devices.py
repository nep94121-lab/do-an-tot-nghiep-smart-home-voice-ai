"""Router Điều Khiển Thiết Bị, Giả Lập Cảm Biến, SQLite WAL & Wokwi Firmware (Feature 14).

Danh sách các endpoints:
1. GET /api/state: Snapshot trạng thái toàn bộ 6 thiết bị & 3 cảm biến.
2. POST /api/device: Bật/tắt hoặc mở/đóng thiết bị (Actuate-First).
3. POST /api/mobile/schedule: Đặt hẹn giờ linh hoạt từ Mobile App.
4. POST /api/ir_learn: Đã gỡ bỏ (HTTP 410 Gone sau khi kiểm tra xác thực/quyền).
5. POST /api/dht11: Cập nhật thông số cảm biến nhiệt độ & độ ẩm DHT11 (chân D2).
6. POST /api/soil_moisture: Cập nhật cảm biến độ ẩm đất (A0) & tự kích hoạt máy bơm (D6).
7. POST /api/sound_sensor & /api/ky037: Cập nhật cảm biến âm thanh KY-037/038 DO (chân D5).
8. POST /api/server_mode: Chuyển đổi Online Gemini Live <-> Offline Mạch độc lập.
9. POST /api/text_command: Xử lý mệnh lệnh văn bản, cảm biến, alias và phân quyền giọng nói.
10. GET /api/wokwi_files: Trả về sơ đồ Wokwi diagram.json và mã nguồn Arduino esp8266_smarthome.ino.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import hmac
import json
import os
import re
import sys
import time
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from simulator.api.deps import (
    ROOT,
    _ACTIVE_BRIDGES,
    _BOOT_VOICE_AUTH,
    _REST_ENGINE,
    broadcast_rest_state_to_bridges,
)
from simulator.auth.session_store import get_session_store, resolve_request_session
from simulator.live.tts_rejection_vi import get_rejection_speech_text
from simulator.rule_engine import append_audit_log
from simulator.voice.enrollment_quality import strip_vietnamese_diacritics
from simulator.voice_config import (
    OWNER_EMAIL,
    OWNER_ID,
    ROLE_MAP,
    USER_ROLE_MAP,
    is_throwaway_qa_identity,
    sanitize_api_payload,
)

UNKNOWN_DEVICE_REJECTION_ERROR = (
    "🚫 NGƯỜI LẠ / VAI TRÒ KHÔNG XÁC ĐỊNH: Từ chối toàn bộ quyền điều khiển thiết bị!"
)

router = APIRouter(tags=["devices"])

_PENDING_DEVICE_AUDIT_TASKS: set[asyncio.Task[Any]] = set()


def _discard_device_audit_task(task: asyncio.Task[Any]) -> None:
    _PENDING_DEVICE_AUDIT_TASKS.discard(task)


def _owner_error(request: Request, payload: dict[str, Any]) -> JSONResponse | None:
    sess = resolve_request_session(request, payload=payload)
    if not sess.is_authenticated:
        return JSONResponse({"ok": False, "error": "Yêu cầu đăng nhập."}, status_code=401)
    if sess.tier != 1 or sess.role != "ADMIN":
        return JSONResponse({"ok": False, "rbac_blocked": True, "error": "Chỉ chủ nhà được thay đổi cài đặt."}, status_code=403)
    return None


def _parse_text_device_targets(t_low: str) -> list[str]:
    """Trích xuất danh sách device_id từ câu lệnh tiếng Việt (hỗ trợ cả có dấu, không dấu và word_mappings)."""
    mapped_text = t_low
    for custom_word, target_val in _REST_ENGINE.get_word_mappings().items():
        cw_low = str(custom_word).lower().strip()
        tv_low = str(target_val).lower().strip()
        if cw_low and cw_low in mapped_text:
            mapped_text = mapped_text.replace(cw_low, f" {tv_low} ")

    has_diac = bool(re.search(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", mapped_text))
    tn = strip_vietnamese_diacritics(mapped_text)

    if any(k in mapped_text for k in ("tất cả thiết bị", "toàn bộ thiết bị", "hết thiết bị", "mọi thiết bị", "all_devices")) or (
        not has_diac and any(k in tn for k in ("tat ca thiet bi", "toan bo thiet bi", "het thiet bi", "moi thiet bi"))
    ):
        return ["all_devices"]
    if any(k in mapped_text for k in ("tất cả đèn", "toàn bộ đèn", "hai đèn", "2 đèn", "cả 2 đèn", "cả hai đèn", "hết đèn", "các đèn", "all_lights")) or (
        not has_diac and any(k in tn for k in ("tat ca den", "toan bo den", "hai den", "2 den", "ca 2 den", "ca hai den", "het den", "cac den"))
    ):
        return ["all_lights"]

    targets: list[str] = []
    if (
        any(k in mapped_text for k in ("cửa chính", "cửa chánh", "cửa lớn", "cửa nhà", "cửa ra vào", "cửa sắt", "công tắc cổng", "main_door"))
        or (not has_diac and any(k in tn for k in ("cua chinh", "cua lon", "cua nha", "cua ra vao", "cua sat", "cong tac cong", "mo cua", "dong cua", "khoa cua")))
        or re.search(r"\bcửa\b", mapped_text)
    ):
        targets.append("main_door")
    if any(k in mapped_text for k in ("đèn phòng khách", "đèn khách", "living_room_light")) or (
        not has_diac and any(k in tn for k in ("den phong khach", "den khach"))
    ):
        targets.append("living_room_light")
    if any(k in mapped_text for k in ("đèn phòng ngủ", "đèn ngủ", "bedroom_light")) or (
        not has_diac and any(k in tn for k in ("den phong ngu", "den ngu"))
    ):
        targets.append("bedroom_light")
    if any(k in mapped_text for k in ("còi báo động", "báo động", "còi hú", "chống trộm", "alarm_siren")) or (
        not has_diac and any(k in tn for k in ("coi bao dong", "bao dong", "coi hu", "chong trom"))
    ) or re.search(r"\bcòi\b", mapped_text):
        targets.append("alarm_siren")
    if any(k in mapped_text for k in ("máy bơm", "bơm nước", "bơm vườn", "bơm ngoài vườn", "tưới cây", "tưới vườn", "garden_pump")) or (
        not has_diac and any(k in tn for k in ("may bom", "bom nuoc", "bom vuon", "bom ngoai vuon", "tuoi cay", "tuoi vuon"))
    ):
        targets.append("garden_pump")
    if (
        any(k in mapped_text for k in ("nguồn mạch loa", "mạch loa", "nguồn loa", "loa chuông", "pam8403", "speaker_amp"))
        or (not has_diac and any(k in tn for k in ("nguon mach loa", "mach loa", "nguon loa", "loa chuong", "pam8403", "speaker amp")))
        or re.search(r"\bloa\b", tn)
    ):
        targets.append("speaker_amp")

    if not targets and re.search(r"\bđèn\b", mapped_text):
        targets.append("living_room_light")
    return targets


def _parse_text_action(t_low: str) -> str | None:
    """Trích xuất hành động bật/mở hoặc tắt/đóng từ câu lệnh tiếng Việt (có dấu và không dấu)."""
    mapped_text = t_low
    for custom_word, target_val in _REST_ENGINE.get_word_mappings().items():
        cw_low = str(custom_word).lower().strip()
        tv_low = str(target_val).lower().strip()
        if cw_low and cw_low in mapped_text:
            mapped_text = mapped_text.replace(cw_low, f" {tv_low} ")

    off_patterns = ("tắt", "đóng", "khóa", "ngắt", "dừng", "turn_off", "turn off", "close")
    on_patterns = ("bật", "mở", "khởi động", "chạy", "turn_on", "turn on", "open")
    for p in off_patterns:
        if re.search(rf"(?:^|\s){re.escape(p)}(?:\s|$)", mapped_text):
            return "close" if p in ("đóng", "khóa", "close") else "turn_off"
    for p in on_patterns:
        if re.search(rf"(?:^|\s){re.escape(p)}(?:\s|$)", mapped_text):
            return "open" if p in ("mở", "open") else "turn_on"

    tn = strip_vietnamese_diacritics(mapped_text)
    has_door = any(k in tn for k in ("cua chinh", "cua lon", "cua nha", "mo cua", "dong cua", "khoa cua", "cong tac cong", "main_door"))
    for p_un in ("tat", "dong", "khoa", "ngat", "dung"):
        if re.search(rf"(?:^|\s){re.escape(p_un)}(?:\s|$)", tn):
            return "close" if (p_un in ("dong", "khoa") or has_door) else "turn_off"
    for p_un in ("bat", "mo", "khoi dong", "chay"):
        if re.search(rf"(?:^|\s){re.escape(p_un)}(?:\s|$)", tn):
            return "open" if (p_un == "mo" or has_door) else "turn_on"
    return None


def _has_valid_hardware_key(request: Request) -> bool:
    expected = str(os.environ.get("SMARTHOME_HARDWARE_API_KEY") or "").strip()
    if not expected:
        return False
    provided = str(request.headers.get("x-hardware-key") or "").strip()
    if not provided:
        auth_h = str(request.headers.get("authorization") or "").strip()
        if auth_h.lower().startswith("bearer "):
            provided = auth_h[7:].strip()
    return bool(provided) and hmac.compare_digest(provided, expected)


@router.get("/api/state")
async def api_get_state(request: Request) -> JSONResponse:
    """Trả về snapshot trạng thái theo phiên người dùng đang xác thực (hoặc bản rút gọn thiết bị công khai nếu chưa đăng nhập)."""
    sess = await asyncio.to_thread(resolve_request_session, request, None, None)
    is_hw = _has_valid_hardware_key(request)
    explicit_header_token = bool(
        str(request.headers.get("authorization") or "").strip()
        or str(request.headers.get("x-session-token") or "").strip()
    )
    if not sess.is_authenticated and is_hw:
        await asyncio.to_thread(_REST_ENGINE.sync_from_shared_store, True)
        return JSONResponse(
            _REST_ENGINE.get_public_device_snapshot(sync=False),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )
    if sess.source == "invalid_token" and explicit_header_token:
        return JSONResponse(
            {
                "ok": False,
                "authenticated": False,
                "error": "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
            },
            status_code=401,
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )
    if not sess.is_authenticated:
        return JSONResponse(
            {
                "ok": False,
                "authenticated": False,
                "error": "Vui lòng đăng nhập để xem trạng thái thiết bị và cảm biến.",
            },
            status_code=401,
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )
    await asyncio.to_thread(_REST_ENGINE.sync_from_shared_store, True)
    return JSONResponse(
        _REST_ENGINE.get_snapshot(session=sess, sync=False),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@router.get("/api/events", response_model=None)
async def api_sse_events(request: Request) -> JSONResponse | Any:
    """Server-Sent Events push stream delivering SQLite state updates in real time."""
    from fastapi.responses import StreamingResponse
    from simulator.realtime_hub import get_realtime_hub

    sess = resolve_request_session(request, payload=None, engine=None)
    is_hw = _has_valid_hardware_key(request)
    if not sess.is_authenticated and not is_hw:
        return JSONResponse(
            {
                "ok": False,
                "authenticated": False,
                "error": "Vui lòng đăng nhập để đăng ký luồng sự kiện thời gian thực.",
            },
            status_code=401,
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )
    _REST_ENGINE.sync_from_shared_store(force=True)
    hub = get_realtime_hub()
    stream = hub.subscribe_sse(
        request,
        sess if sess.is_authenticated else None,
        _REST_ENGINE,
        keepalive_sec=8.0,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _session_role_response(request: Request) -> JSONResponse:
    existing_sess = resolve_request_session(request, payload=None, engine=None)
    no_store_headers = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
    if not existing_sess.is_authenticated or existing_sess.source in ("invalid_token", "unauthenticated"):
        return JSONResponse(
            {
                "ok": False,
                "authenticated": False,
                "error": "Hãy đăng nhập hoặc dùng mã mời của chủ nhà.",
            },
            status_code=401,
            headers=no_store_headers,
        )
    return JSONResponse(
        {
            "ok": True,
            "authenticated": True,
            "active_user_id": existing_sess.user_id,
            "email": existing_sess.email,
            "display_name": existing_sess.display_name,
            "role": existing_sess.role,
            "tier": existing_sess.tier,
            "server_connected": bool(getattr(_REST_ENGINE, "server_connected", True)),
            "message": "Phiên giữ nguyên theo tài khoản đã đăng nhập. Không thể đổi cấp tại đây.",
        },
        headers=no_store_headers,
    )


@router.get("/api/session/role")
async def api_get_session_role(request: Request) -> JSONResponse:
    """Trả về thông tin vai trò của phiên hiện tại từ server (401 nếu chưa đăng nhập)."""
    return _session_role_response(request)


@router.post("/api/session/role")
async def api_set_session_role(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Phiên khách/thành viên chỉ được tạo bằng đăng nhập hoặc mã mời của chủ nhà."""
    _ = payload
    return _session_role_response(request)


@router.post("/api/device")
@router.post("/api/device_control")
async def api_control_device(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Điều khiển bật/tắt hoặc mở/đóng thiết bị từ App Mobile hoặc Web (RBAC lấy từ session đã xác thực)."""
    body = payload if isinstance(payload, dict) else {}
    dev_id = str(body.get("device_id") or "main_door").strip() or "main_door"
    target_state = (
        body.get("target_state")
        if "target_state" in body
        else (body.get("state") if "state" in body else body.get("desired_state"))
    )
    act = str(body.get("action") or (target_state if target_state is not None else "open")).strip() or "open"
    source = str(body.get("source") or "mobile_app").strip() or "mobile_app"
    client_id = body.get("client_id") if "client_id" in body else body.get("clientId")
    client_seq = body.get("client_seq") if "client_seq" in body else body.get("seq")
    client_ts_ms = body.get("client_ts_ms") if "client_ts_ms" in body else body.get("timestamp")
    request_id = body.get("request_id") if "request_id" in body else body.get("requestId")

    req_sess = await asyncio.to_thread(resolve_request_session, request, body, None)
    if (
        req_sess.role == "UNKNOWN"
        or req_sess.tier not in (1, 2, 3)
        or str(req_sess.user_id).strip().lower() == "unknown"
    ):
        return JSONResponse(
            {
                "ok": False,
                "rbac_blocked": True,
                "tier": 99,
                "role": "UNKNOWN",
                "error": UNKNOWN_DEVICE_REJECTION_ERROR,
                "rejection_speech": UNKNOWN_DEVICE_REJECTION_ERROR,
                "exact_spoken_reply": UNKNOWN_DEVICE_REJECTION_ERROR,
            },
            status_code=403,
        )

    session = req_sess
    if not session.is_authenticated:
        return JSONResponse(
            {
                "ok": False,
                "error": "Yêu cầu đăng nhập (HTTP 401 Unauthorized).",
                "rejection_speech": get_rejection_speech_text("STRANGER_BLOCKED"),
                "exact_spoken_reply": get_rejection_speech_text("STRANGER_BLOCKED"),
                "status_code": 401,
            },
            status_code=401,
        )
    session_tier = session.tier
    session_user = session.display_name
    session_role = session.role

    res = await _REST_ENGINE.execute_device_action(
        dev_id,
        act,
        source=source,
        bypass_rbac=False,
        request_tier=session_tier,
        request_user_name=session_user,
        request_role=session_role,
        target_state=target_state,
        client_id=client_id,
        client_seq=client_seq,
        client_ts_ms=client_ts_ms,
        request_id=request_id,
    )
    res["tier"] = session_tier
    res["user_name"] = session_user
    rbac_blocked = bool(res.get("rbac_blocked", False))
    res["rbac_blocked"] = rbac_blocked
    res["snapshot"] = res.get("snapshot") or _REST_ENGINE.get_snapshot(session=session, sync=False)
    if not res.get("ok") and not res.get("error"):
        res["error"] = res.get("exact_spoken_reply") or "Bị chặn bởi phân quyền RBAC."
    spoken_dev_ctrl = str(res.get("exact_spoken_reply") or res.get("error") or "").strip()
    if not res.get("ok"):
        res["rejection_speech"] = spoken_dev_ctrl

    await broadcast_rest_state_to_bridges(sync_engine=False)
    audit_kwargs = {
        "category": "DEVICE_IO",
        "event_type": "mobile_device_toggle",
        "summary": f"[App/Web] {session_user} (Tầng {session_tier}): {res.get('exact_spoken_reply') or f'{dev_id} -> {act}'}",
        "user_name": session_user,
        "tier": session_tier,
        "details": {
            "device_id": dev_id,
            "action": act,
            "target_state": target_state,
            "client_id": client_id,
            "client_seq": client_seq,
            "request_id": request_id,
            "result": {k: v for k, v in res.items() if k != "snapshot"},
        },
    }
    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        await asyncio.to_thread(append_audit_log, **audit_kwargs)
    else:
        task = asyncio.create_task(asyncio.to_thread(append_audit_log, **audit_kwargs))
        _PENDING_DEVICE_AUDIT_TASKS.add(task)
        task.add_done_callback(_discard_device_audit_task)
    status_code = 200
    if not res.get("ok") and session.source != "legacy_test":
        results_list = res.get("results") if isinstance(res.get("results"), list) else []
        first_err = str(
            (results_list[0].get("error") if results_list and isinstance(results_list[0], dict) else "")
            or res.get("error")
            or ""
        )
        if rbac_blocked or first_err.startswith("🔒"):
            status_code = 403
        elif "không tồn tại" in first_err or "Không tìm thấy thiết bị" in first_err:
            status_code = 404
        else:
            status_code = 400
    return JSONResponse(res, status_code=status_code)


@router.post("/api/device/{device_id}")
@router.post("/api/devices/{device_id}/control")
async def api_control_device_by_path(device_id: str, request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Điều khiển bật/tắt thiết bị theo đường dẫn REST /api/devices/{device_id}/control hoặc /api/device/{device_id}."""
    body = dict(payload or {})
    body["device_id"] = device_id
    return await api_control_device(request, body)


@router.post("/api/mobile/schedule")
async def api_mobile_schedule(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Tạo hẹn giờ từ ứng dụng di động Android / PWA (Chặn Khách Cấp 3 theo RBAC)."""
    body = payload if isinstance(payload, dict) else {}
    dev_id = str(body.get("device_id") or "").strip()
    act = str(body.get("action") or "").strip()
    if not dev_id or not act:
        msg_req = "Bạn muốn hẹn giờ cho thiết bị nào và bật hay tắt?"
        return JSONResponse({"ok": False, "error": msg_req, "reply": msg_req, "exact_spoken_reply": msg_req}, status_code=400)
    sec = _REST_ENGINE.mqtt_bridge._clamp_sensor_float(body.get("seconds", 15), 1.0, 86400.0, 15.0)

    req_sess = await asyncio.to_thread(resolve_request_session, request, body, None)
    if (
        req_sess.role == "UNKNOWN"
        or req_sess.tier not in (1, 2, 3)
        or str(req_sess.user_id).strip().lower() == "unknown"
    ):
        return JSONResponse(
            {
                "ok": False,
                "rbac_blocked": True,
                "tier": 99,
                "role": "UNKNOWN",
                "error": UNKNOWN_DEVICE_REJECTION_ERROR,
                "rejection_speech": UNKNOWN_DEVICE_REJECTION_ERROR,
                "exact_spoken_reply": UNKNOWN_DEVICE_REJECTION_ERROR,
            },
            status_code=403,
        )

    session = req_sess
    if not session.is_authenticated:
        return JSONResponse(
            {
                "ok": False,
                "error": "Yêu cầu đăng nhập (HTTP 401 Unauthorized).",
                "rejection_speech": get_rejection_speech_text("STRANGER_BLOCKED"),
                "exact_spoken_reply": get_rejection_speech_text("STRANGER_BLOCKED"),
                "status_code": 401,
            },
            status_code=401,
        )
    effective_tier = session.tier
    user_name = session.display_name

    if effective_tier >= 3:
        from simulator.automation_repo import GUEST_ONLY_TOGGLE_MSG_VI

        append_audit_log(
            category="SECURITY",
            event_type="mobile_schedule_blocked_rbac",
            summary=f"[RBAC] Chặn tạo lịch hẹn giờ từ {user_name} (Tầng {effective_tier}): {dev_id} -> {act}",
            user_name=user_name,
            tier=effective_tier,
            details={"device_id": dev_id, "action": act, "seconds": sec, "blocked": True},
        )
        return JSONResponse(
            {
                "ok": False,
                "rbac_blocked": True,
                "tier": effective_tier,
                "error": GUEST_ONLY_TOGGLE_MSG_VI,
                "exact_spoken_reply": GUEST_ONLY_TOGGLE_MSG_VI,
            },
            status_code=403,
        )

    if effective_tier >= 2:
        allowed, reason = _REST_ENGINE.check_device_permission(dev_id, actor_tier=effective_tier)
        if not allowed:
            return JSONResponse(
                {
                    "ok": False,
                    "rbac_blocked": True,
                    "tier": effective_tier,
                    "error": reason,
                    "exact_spoken_reply": reason,
                },
                status_code=403,
            )

    from simulator.automation_repo import check_tier1_schedule_conflict

    conflict_msg = check_tier1_schedule_conflict(
        actor_tier=effective_tier,
        fire_epoch=time.time() + float(sec or 0.0),
        engine=_REST_ENGINE,
    )
    if conflict_msg:
        append_audit_log(
            category="SECURITY",
            event_type="mobile_schedule_conflict_tier1",
            summary=f"[RBAC] Chặn Cấp 2 ({user_name}) đặt hẹn giờ trùng lịch Cấp 1: {conflict_msg}",
            user_name=user_name,
            tier=effective_tier,
            details={"device_id": dev_id, "action": act, "seconds": sec, "conflict": True},
        )
        return JSONResponse(
            {
                "ok": False,
                "rbac_blocked": True,
                "conflict_tier1": True,
                "tier": effective_tier,
                "error": conflict_msg,
                "exact_spoken_reply": conflict_msg,
            },
            status_code=409,
        )

    from simulator.api.routes_automation import stage_or_execute_rest_confirmation
    from simulator.automation_repo import format_device_action_vi, format_duration_vi

    sec_i = max(1, int(round(sec)))
    summary = f"Đặt hẹn giờ sau {format_duration_vi(sec_i)} sẽ {format_device_action_vi(dev_id, act).lower()}"
    return await stage_or_execute_rest_confirmation(
        request=request,
        sess=session,
        body=body,
        action_kind="create_timer",
        payload={
            "device_id": dev_id,
            "action": act,
            "hours": 0.0,
            "minutes": 0.0,
            "seconds": sec,
            "repeat": "once",
        },
        prompt_summary=summary,
        source="App Android",
    )


@router.post("/api/ir_learn")
async def api_ir_learn(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Endpoint học lệnh hồng ngoại IR đã được gỡ bỏ (410 Gone sau khi kiểm tra xác thực/quyền)."""
    body = payload if isinstance(payload, dict) else {}
    session = resolve_request_session(request, payload=body, engine=None)
    if not session.is_authenticated:
        return JSONResponse(
            {
                "ok": False,
                "error": "Yêu cầu đăng nhập (HTTP 401 Unauthorized).",
                "status_code": 401,
            },
            status_code=401,
        )
    error = _owner_error(request, body)
    if error is not None:
        return error
    return JSONResponse(
        {
            "ok": False,
            "gone": True,
            "error": "Tính năng học lệnh hồng ngoại IR đã được gỡ bỏ theo hợp đồng phần cứng 6 thiết bị mới.",
        },
        status_code=410,
    )


@router.post("/api/dht11")
async def api_update_dht11(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Cập nhật thông số cảm biến nhiệt độ & độ ẩm không khí DHT11 (chân D2)."""
    body = payload if isinstance(payload, dict) else {}
    if not _has_valid_hardware_key(request):
        error = _owner_error(request, body)
        if error is not None:
            return error
    temp_c = body.get("temp_c", 28.5)
    hum_pct = body.get("humidity_pct", 65.0)
    rssi = body.get("wifi_rssi_dbm", -52)
    res = await _REST_ENGINE.update_sensor_telemetry(temp_c, hum_pct, rssi)
    await broadcast_rest_state_to_bridges()
    return JSONResponse(res)


@router.post("/api/soil_moisture")
async def api_update_soil_moisture(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Cập nhật cảm biến độ ẩm đất (A0) và tự động bật/tắt bơm vườn (D6)."""
    body = payload if isinstance(payload, dict) else {}
    if not _has_valid_hardware_key(request):
        error = _owner_error(request, body)
        if error is not None:
            return error
    pct = body.get("soil_moisture_pct", 62.0)
    res = await _REST_ENGINE.update_soil_moisture_telemetry(pct)
    await broadcast_rest_state_to_bridges()
    return JSONResponse(res)


@router.post("/api/sound_sensor")
@router.post("/api/ky037")
async def api_update_sound_sensor(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Cập nhật trạng thái cảm biến âm thanh KY-037/038 DO (chân D5 / GPIO14)."""
    body = payload if isinstance(payload, dict) else {}
    if not _has_valid_hardware_key(request):
        error = _owner_error(request, body)
        if error is not None:
            return error
    sound_detected = body.get("sound_detected")
    if sound_detected is None:
        sound_detected = body.get("detected")
    if sound_detected is None:
        sound_detected = body.get("loud_sound", False)
    do_state = body.get("do_state")
    note = str(body.get("note") or "")
    res = await _REST_ENGINE.update_sound_telemetry(
        sound_detected=sound_detected,
        do_state=do_state,
        note=note,
    )
    await broadcast_rest_state_to_bridges()
    return JSONResponse(res)


@router.post("/api/server_mode")
async def api_set_server_mode(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Chuyển đổi chế độ Online Gemini Live <-> Offline Mạch độc lập."""
    error = _owner_error(request, payload)
    if error is not None:
        return error
    connected = bool(payload.get("server_connected", True))
    res = await _REST_ENGINE.set_server_connection_mode(connected)
    for br in list(_ACTIVE_BRIDGES):
        try:
            await br.engine.set_server_connection_mode(connected)
        except Exception:
            pass
    await broadcast_rest_state_to_bridges()
    return JSONResponse(res)


async def _attach_aoede_audio(data: dict[str, Any]) -> dict[str, Any]:
    """Tổng hợp âm thanh Gemini Live Aoede 24kHz cho phản hồi lệnh văn bản."""
    if not isinstance(data, dict):
        return data
    if data.get("pcm24k_b64"):
        if "play_audio" not in data:
            data["play_audio"] = True
        return data
    spoken = str(
        data.get("exact_spoken_reply")
        or data.get("reply")
        or data.get("rejection_speech")
        or data.get("error")
        or ""
    ).strip()
    if not spoken:
        data.setdefault("play_audio", False)
        return data
    try:
        from simulator.live.tts_rejection_vi import (
            build_aoede_http_audio_fields,
            schedule_aoede_background_warm,
            synthesize_aoede_phrase_audio,
        )

        cache_only = os.environ.get("SMARTHOME_AOEDE_CACHE_ONLY", "").strip().lower() in ("1", "true", "yes")
        bundle = await synthesize_aoede_phrase_audio(spoken, allow_live_refresh=not cache_only)
        fields = build_aoede_http_audio_fields(bundle)
        if not fields.get("pcm24k_b64") and cache_only:
            schedule_aoede_background_warm(spoken)
        merged = {**data, **fields}
        merged["play_audio"] = bool(fields.get("pcm24k_b64"))
        return merged
    except Exception:
        return data


@router.post("/api/text_command")
async def api_text_command(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Xử lý khẩu lệnh dạng text và gắn âm thanh Gemini Live Aoede trên mọi nhánh phản hồi."""
    resp = await _api_text_command_impl(request=request, payload=payload)
    if resp.status_code == 401:
        return resp
    try:
        raw_body = bytes(resp.body or b"").decode("utf-8")
        data = json.loads(raw_body) if raw_body else {}
    except Exception:
        return resp
    if not isinstance(data, dict):
        return resp
    enriched = await _attach_aoede_audio(data)
    hdrs = {k: v for k, v in resp.headers.items() if k.lower() not in ("content-length", "content-type")}
    return JSONResponse(enriched, status_code=resp.status_code, headers=hdrs or None)


async def _api_text_command_impl(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Xử lý khẩu lệnh dạng text, hỗ trợ offline command, cảm biến, alias và phân quyền."""
    body = payload if isinstance(payload, dict) else {}
    text = str(body.get("text", "")).strip()

    req_sess = await asyncio.to_thread(resolve_request_session, request, body, None)
    if (
        req_sess.role == "UNKNOWN"
        or req_sess.tier not in (1, 2, 3)
        or str(req_sess.user_id).strip().lower() == "unknown"
    ):
        return JSONResponse(
            {
                "ok": False,
                "rbac_blocked": True,
                "tier": 99,
                "role": "UNKNOWN",
                "error": UNKNOWN_DEVICE_REJECTION_ERROR,
                "rejection_speech": UNKNOWN_DEVICE_REJECTION_ERROR,
                "exact_spoken_reply": UNKNOWN_DEVICE_REJECTION_ERROR,
            },
            status_code=403,
        )

    session = req_sess
    effective_tier = session.tier
    effective_user = session.display_name
    effective_role = session.role

    if not session.is_authenticated:
        return JSONResponse({"ok": False, "error": "Yêu cầu đăng nhập."}, status_code=401)

    from simulator.auth_3layer import get_auth_3layer_manager
    perm_voice_res = get_auth_3layer_manager().parse_and_execute_voice_permission_command(
        spoken_text=text,
        actor_tier=effective_tier,
        source_device="Giọng nói Thiết bị / Text Command",
    )
    if perm_voice_res is not None:
        if perm_voice_res.get("ok") and perm_voice_res.get("account"):
            acc_p = perm_voice_res["account"]
            if perm_voice_res.get("action") == "REVOKED":
                await _REST_ENGINE.revoke_user_permission(target_name=acc_p["display_name"])
            else:
                await _REST_ENGINE.grant_user_permission(target_name=acc_p["display_name"], target_tier=int(acc_p["tier"]))
            await broadcast_rest_state_to_bridges()
        spoken_p = perm_voice_res.get("exact_spoken_reply") or perm_voice_res.get("message") or perm_voice_res.get("error", "")
        return JSONResponse({
            "ok": bool(perm_voice_res.get("ok")),
            "reply": spoken_p,
            "exact_spoken_reply": spoken_p,
            "permission_update": perm_voice_res,
        })

    from simulator.automation_nlu import (
        _classify_confirmation_utterance,
        _resolve_session_key,
        handle_confirmation_reply,
        handle_pending_interruption_if_any,
        process_automation_nlu_command,
    )
    from simulator.automation_repo import find_custom_command_by_text
    from simulator.engine.voice_rbac_mixin import FIXED_REJECTION_PHRASE_VI
    from simulator.voice.vietnamese_policy import (
        classify_ambiguous_or_unsupported_vi,
        classify_small_talk_vi,
        ensure_vietnamese_reply,
        format_short_action_reply_vi,
        handle_sensor_or_status_query_vi,
        parse_direct_device_intents_vi,
    )

    skey_txt = _resolve_session_key(session, "text_command")

    # 0. Active pending confirmation reply FIRST
    if _classify_confirmation_utterance(text) is not None:
        conf_res = await handle_confirmation_reply(
            raw_text=text,
            engine=_REST_ENGINE,
            session=session,
            source="text_command",
            session_key=skey_txt,
        )
        if conf_res is not None:
            await broadcast_rest_state_to_bridges()
            c_payload = dict(conf_res.get("payload") or {})
            if c_payload.get("exact_spoken_reply"):
                sp_c = ensure_vietnamese_reply(str(c_payload["exact_spoken_reply"]))
                c_payload["exact_spoken_reply"] = sp_c
                c_payload["reply"] = sp_c
            return JSONResponse(c_payload, status_code=int(conf_res.get("status_code") or 200))

    # 1. Small talk BEFORE any automation/permission rejections (unless saved custom command)
    saved_custom_txt = (
        find_custom_command_by_text(text, owner_user_id=str(session.user_id))
        if effective_tier < 3
        else None
    )
    if saved_custom_txt is None:
        small_talk = classify_small_talk_vi(text, user_name=str(effective_user or ""))
        if small_talk is not None:
            await handle_pending_interruption_if_any(
                raw_text=text,
                engine=_REST_ENGINE,
                session=session,
                source="text_command",
                session_key=skey_txt,
                is_new_valid_intent=True,
            )
            spoken_st = ensure_vietnamese_reply(str(small_talk.get("reply") or ""))
            return JSONResponse({
                "ok": True,
                "kind": "small_talk",
                "subkind": small_talk.get("subkind", "greeting"),
                "executed": False,
                "requires_confirmation": False,
                "rbac_blocked": False,
                "tier": effective_tier,
                "reply": spoken_st,
                "exact_spoken_reply": spoken_st,
                "snapshot": _REST_ENGINE.get_snapshot(session=session, sync=False),
            })

    t_low = text.lower()

    # 2a. Explicit owner-only sensor simulation SET commands (never hijack conditional/automation rules or DHT11 model digits)
    t_sensor_set_probe = re.sub(r"\b(?:dht\s*11|ky\s*-?\s*03[78]|yl\s*-?\s*69|pam\s*8403|esp\s*8266)\b", " ", t_low)
    is_rule_or_cond_sensor = bool(
        re.search(
            r"(?:^|\s)(?:nếu|khi|thì|cứ|quy\s+tắc|liên\s+kết|tạo\s+luật|cài\s+cho\s+tôi|mà\s+lên\s+trên|vượt\s+quá|xuống\s+dưới|lên\s+trên)(?:\s|$)",
            t_low,
        )
    )
    has_explicit_set_verb = bool(
        re.search(r"(?:^|\s)(?:set|chỉnh|đặt|thay\s+đổi)(?:\s|$)|=", t_low)
    )
    if not is_rule_or_cond_sensor and has_explicit_set_verb and ("độ ẩm đất" in t_low or "cảm biến đất" in t_low):
        m_soil = re.search(r"(\d+(?:\.\d+)?)\s*%?", t_sensor_set_probe)
        if m_soil:
            error = _owner_error(request, body)
            if error is not None:
                return error
            res_soil = await _REST_ENGINE.update_soil_moisture_telemetry(float(m_soil.group(1)))
            await broadcast_rest_state_to_bridges()
            sp_s = ensure_vietnamese_reply(str(res_soil.get("exact_spoken_reply") or ""))
            return JSONResponse({"ok": True, "executed": True, "reply": sp_s, "exact_spoken_reply": sp_s})

    if not is_rule_or_cond_sensor and has_explicit_set_verb and ("nhiệt độ" in t_low or "độ ẩm" in t_low) and "độ ẩm đất" not in t_low:
        if re.search(r"\d", t_sensor_set_probe):
            error = _owner_error(request, body)
            if error is not None:
                return error
            cur_dht = _REST_ENGINE.mqtt_bridge.dht11_telemetry
            m_t = re.search(r"nhiệt độ[^\d]*(\d+(?:\.\d+)?)", t_sensor_set_probe)
            m_h = re.search(r"độ ẩm[^\d]*(\d+(?:\.\d+)?)", t_sensor_set_probe)
            t_val = float(m_t.group(1)) if m_t else float(cur_dht.get("temp_c", 28.5))
            h_val = float(m_h.group(1)) if m_h else float(cur_dht.get("humidity_pct", 65.0))
            res_dht = await _REST_ENGINE.update_sensor_telemetry(t_val, h_val)
            await broadcast_rest_state_to_bridges()
            sp_d = ensure_vietnamese_reply(str(res_dht.get("exact_spoken_reply") or ""))
            return JSONResponse({"ok": True, "executed": True, "reply": sp_d, "exact_spoken_reply": sp_d})

    # 2b-pre. UI guidance questions ("ở đâu", "bấm vào đâu", "chỗ nào") take precedence over sensor value readout
    from simulator.compound_nlu import is_ui_guidance_question, process_compound_nlu_command

    if is_ui_guidance_question(text):
        ui_res = await process_compound_nlu_command(
            text=text,
            engine=_REST_ENGINE,
            session=session,
            source="text_command",
            session_key=skey_txt,
        )
        if ui_res is not None:
            ui_pl = dict(ui_res.get("payload") or {})
            if ui_pl.get("exact_spoken_reply"):
                sp_u = ensure_vietnamese_reply(str(ui_pl["exact_spoken_reply"]))
                ui_pl["exact_spoken_reply"] = sp_u
                ui_pl["reply"] = sp_u
            ui_pl.setdefault("snapshot", _REST_ENGINE.get_snapshot(session=session, sync=False))
            return JSONResponse(ui_pl, status_code=int(ui_res.get("status_code") or 200))

    # 2b. Sensor & device status queries (immediate, no confirmation)
    q_info = handle_sensor_or_status_query_vi(text, _REST_ENGINE, session)
    if q_info is not None:
        await handle_pending_interruption_if_any(
            raw_text=text,
            engine=_REST_ENGINE,
            session=session,
            source="text_command",
            session_key=skey_txt,
            is_new_valid_intent=True,
        )
        is_q_blk = bool(q_info.get("rbac_blocked"))
        q_code = int(q_info.get("status_code") or (403 if is_q_blk else 200))
        sp_q = ensure_vietnamese_reply(str(q_info.get("exact_spoken_reply") or q_info.get("reply") or ""))
        return JSONResponse(
            {
                **q_info,
                "ok": bool(q_info.get("ok", not is_q_blk)),
                "executed": not is_q_blk,
                "requires_confirmation": False,
                "rbac_blocked": is_q_blk,
                "tier": effective_tier,
                "reply": sp_q,
                "exact_spoken_reply": sp_q,
                "snapshot": _REST_ENGINE.get_snapshot(session=session, sync=False),
            },
            status_code=q_code,
        )

    # 2c. Compound NLU (UI guidance, removed-device guard, house mode, compound rules, weekday schedules, toggles)
    from simulator.compound_nlu import process_compound_nlu_command

    comp_res = await process_compound_nlu_command(
        text=text,
        engine=_REST_ENGINE,
        session=session,
        source="text_command",
        session_key=skey_txt,
    )
    if comp_res is not None:
        comp_pl = dict(comp_res.get("payload") or {})
        if comp_pl.get("ok") or comp_pl.get("executed") or comp_pl.get("confirmed"):
            await broadcast_rest_state_to_bridges()
        if comp_pl.get("exact_spoken_reply"):
            sp_c = ensure_vietnamese_reply(str(comp_pl["exact_spoken_reply"]))
            comp_pl["exact_spoken_reply"] = sp_c
            comp_pl["reply"] = sp_c
        comp_pl.setdefault("snapshot", _REST_ENGINE.get_snapshot(session=session, sync=False))
        return JSONResponse(comp_pl, status_code=int(comp_res.get("status_code") or 200))

    # 3. Automation NLU (custom commands create/use/edit/delete, schedules/timers, cross-rules, resets, pool queries)
    nlu_res = await process_automation_nlu_command(
        text=text,
        engine=_REST_ENGINE,
        session=session,
        source="text_command",
        session_key=skey_txt,
    )
    if nlu_res is not None:
        await broadcast_rest_state_to_bridges()
        nlu_pl = dict(nlu_res.get("payload") or {})
        if nlu_pl.get("exact_spoken_reply"):
            sp_n = ensure_vietnamese_reply(str(nlu_pl["exact_spoken_reply"]))
            nlu_pl["exact_spoken_reply"] = sp_n
            nlu_pl["reply"] = sp_n
        return JSONResponse(nlu_pl, status_code=int(nlu_res.get("status_code") or 200))

    # Fallback overlay aliases not in SQLite custom_commands
    for phrase in _REST_ENGINE.get_merged_aliases(user_id=session.user_id):
        if phrase in t_low:
            if effective_tier >= 3:
                from simulator.automation_repo import GUEST_ONLY_TOGGLE_MSG_VI

                return JSONResponse(
                    {
                        "ok": False,
                        "rbac_blocked": True,
                        "tier": effective_tier,
                        "error": GUEST_ONLY_TOGGLE_MSG_VI,
                        "reply": GUEST_ONLY_TOGGLE_MSG_VI,
                        "exact_spoken_reply": GUEST_ONLY_TOGGLE_MSG_VI,
                    },
                    status_code=403,
                )
            prev_uid = getattr(_REST_ENGINE, "_current_user_id", "tuan_anh")
            prev_role = getattr(_REST_ENGINE, "_current_role", "ADMIN")
            try:
                _REST_ENGINE._current_user_id = str(session.user_id)
                _REST_ENGINE._current_role = str(session.role)
                res = await _REST_ENGINE.execute_alias_rule(phrase)
            finally:
                _REST_ENGINE._current_user_id = prev_uid
                _REST_ENGINE._current_role = prev_role
            await broadcast_rest_state_to_bridges()
            sp_al = ensure_vietnamese_reply(str(res.get("exact_spoken_reply") or "Đã thực hiện."))
            return JSONResponse({
                "ok": bool(res.get("ok", True)),
                "executed": bool(res.get("ok", True)),
                "reply": sp_al,
                "exact_spoken_reply": sp_al,
                "results": res.get("results", []),
            })

    # 4. Direct simple device commands -> RBAC check -> EXECUTE IMMEDIATELY -> concise Vietnamese reply
    direct_intents = parse_direct_device_intents_vi(text, word_mappings=_REST_ENGINE.get_word_mappings())
    if direct_intents:
        await handle_pending_interruption_if_any(
            raw_text=text,
            engine=_REST_ENGINE,
            session=session,
            source="text_command",
            session_key=skey_txt,
            is_new_valid_intent=True,
        )
        for item in direct_intents:
            dev_id = item["device_id"]
            allowed, _reason = _REST_ENGINE.check_device_permission(dev_id, actor_tier=effective_tier)
            if not allowed:
                deny_msg = ensure_vietnamese_reply(FIXED_REJECTION_PHRASE_VI)
                deny_code = 200 if session.source == "legacy_test" else 403
                return JSONResponse(
                    {
                        "ok": False,
                        "executed": False,
                        "requires_confirmation": False,
                        "rbac_blocked": True,
                        "tier": effective_tier,
                        "error": deny_msg,
                        "reply": deny_msg,
                        "exact_spoken_reply": deny_msg,
                        "rejection_speech": deny_msg,
                        "snapshot": _REST_ENGINE.get_snapshot(session=session, sync=False),
                    },
                    status_code=deny_code,
                )

        exec_results: list[dict[str, Any]] = []
        exec_summary_items: list[dict[str, Any]] = []
        for item in direct_intents:
            dev_id = item["device_id"]
            act = item["action"]
            prev_st = str((_REST_ENGINE.devices.get(dev_id) or {}).get("state") or "")
            res = await _REST_ENGINE.execute_device_action(
                dev_id,
                act,
                source="text_command",
                bypass_rbac=False,
                request_tier=effective_tier,
                request_user_name=effective_user,
                request_role=effective_role,
            )
            if not res.get("ok"):
                is_blk = bool(res.get("rbac_blocked"))
                err_txt = ensure_vietnamese_reply(
                    FIXED_REJECTION_PHRASE_VI if is_blk else str(res.get("exact_spoken_reply") or res.get("error") or "Không thực hiện được lệnh.")
                )
                st_code = 200 if (is_blk and session.source == "legacy_test") else (403 if is_blk else 400)
                return JSONResponse(
                    {
                        "ok": False,
                        "executed": False,
                        "requires_confirmation": False,
                        "rbac_blocked": is_blk,
                        "tier": effective_tier,
                        "error": err_txt,
                        "reply": err_txt,
                        "exact_spoken_reply": err_txt,
                        "rejection_speech": err_txt if is_blk else "",
                        "snapshot": _REST_ENGINE.get_snapshot(session=session, sync=False),
                    },
                    status_code=st_code,
                )
            exec_results.append(res)
            new_st = str((_REST_ENGINE.devices.get(dev_id) or {}).get("state") or "")
            exec_summary_items.append({
                "device_id": dev_id,
                "action": act,
                "previous_state": prev_st,
                "state": new_st,
                "already_in_state": bool(prev_st and new_st and prev_st == new_st),
            })

        await broadcast_rest_state_to_bridges()
        spoken_ok = ensure_vietnamese_reply(format_short_action_reply_vi(exec_summary_items, _REST_ENGINE.devices))
        last_item = exec_summary_items[-1]
        return JSONResponse(
            {
                "ok": True,
                "executed": True,
                "confirmed": True,
                "requires_confirmation": False,
                "rbac_blocked": False,
                "tier": effective_tier,
                "device_id": last_item["device_id"],
                "state": last_item["state"],
                "intents": direct_intents,
                "results": exec_results,
                "reply": spoken_ok,
                "exact_spoken_reply": spoken_ok,
                "snapshot": _REST_ENGINE.get_snapshot(session=session, sync=False),
            },
            status_code=200,
        )

    # 5. Interruption reminder if a pending confirmation exists, else short Vietnamese clarification (ZERO actions)
    reminder = await handle_pending_interruption_if_any(
        raw_text=text,
        engine=_REST_ENGINE,
        session=session,
        source="text_command",
        session_key=skey_txt,
        is_new_valid_intent=False,
    )
    if reminder is not None:
        rem_pl = dict(reminder.get("payload") or {})
        sp_rem = ensure_vietnamese_reply(str(rem_pl.get("exact_spoken_reply") or rem_pl.get("reply") or ""))
        rem_pl["exact_spoken_reply"] = sp_rem
        rem_pl["reply"] = sp_rem
        return JSONResponse(rem_pl, status_code=200)

    clarification = ensure_vietnamese_reply(
        classify_ambiguous_or_unsupported_vi(text) or "Tôi chưa nghe rõ lệnh, bạn nói lại rõ hơn nhé."
    )
    return JSONResponse({
        "ok": True,
        "executed": False,
        "requires_confirmation": False,
        "needs_clarification": True,
        "rbac_blocked": False,
        "tier": effective_tier,
        "reply": clarification,
        "exact_spoken_reply": clarification,
        "play_audio": False,
        "snapshot": _REST_ENGINE.get_snapshot(session=session, sync=False),
    })


@router.post("/api/voice_command")
@router.post("/api/voice/command")
async def api_voice_command(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Lệnh giọng nói theo phiên: STT/transcript -> ý định -> RBAC phiên (không nhận dạng người nói)."""
    body = payload if isinstance(payload, dict) else {}
    session = resolve_request_session(request, payload=body, engine=None)
    from simulator.voice.session_voice_command import process_session_voice_command

    result, status = await process_session_voice_command(
        engine=_REST_ENGINE,
        session=session,
        payload=body,
        source=str(body.get("source") or "web_voice"),
    )
    if status != 401 and (result.get("ok") or result.get("executed")):
        await broadcast_rest_state_to_bridges()
    if (
        status != 401
        and "snapshot" not in result
        and hasattr(_REST_ENGINE, "get_snapshot")
        and session is not None
        and getattr(session, "is_authenticated", False)
    ):
        try:
            result["snapshot"] = _REST_ENGINE.get_snapshot(session=session, sync=False)
        except Exception:
            pass
    return JSONResponse(result, status_code=status)


_AOEDE_UNAUTH_BUCKETS: dict[str, list[float]] = {}
_AOEDE_UNAUTH_LOCK = __import__("threading").Lock()
AOEDE_UNAUTH_RATE_LIMIT = 30
AOEDE_UNAUTH_WINDOW_SEC = 60.0


def _reset_aoede_unauth_rate_limits() -> None:
    """Đặt lại bộ đếm giới hạn tốc độ unauth cho endpoint /api/voice/aoede_phrase (dùng trong kiểm thử)."""
    with _AOEDE_UNAUTH_LOCK:
        _AOEDE_UNAUTH_BUCKETS.clear()


@router.post("/api/voice/aoede_phrase")
async def api_voice_aoede_phrase(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Trả về âm thanh 24kHz PCM/WAV của duy nhất giọng Aoede (Gemini Live)."""
    from simulator.api.routes_auth import normalize_client_ip
    from simulator.live.tts_rejection_vi import (
        EXTENDED_TTS_SCRIPTS,
        FIXED_REJECTION_PHRASE_VI,
        FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
        build_aoede_http_audio_fields,
        synthesize_aoede_phrase_audio,
    )

    body = payload if isinstance(payload, dict) else {}
    phrase = str(body.get("phrase") or body.get("text") or "").strip()
    if not phrase or len(phrase) > 300:
        return JSONResponse(
            sanitize_api_payload(
                {
                    "ok": False,
                    "error": "Nội dung câu thoại phát giọng Aoede không hợp lệ.",
                }
            ),
            status_code=400,
        )
    session = resolve_request_session(request, payload=body, engine=None)
    is_auth = session is not None and bool(getattr(session, "is_authenticated", False))
    allowed_public_phrases = frozenset(EXTENDED_TTS_SCRIPTS.values()) | {
        FIXED_REJECTION_PHRASE_VI,
        FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
    }
    if not is_auth and phrase not in allowed_public_phrases:
        return JSONResponse(
            sanitize_api_payload(
                {
                    "ok": False,
                    "error": "Chỉ hỗ trợ phát giọng Aoede cho bộ câu thoại cố định khi chưa đăng nhập!",
                }
            ),
            status_code=400,
        )
    if not is_auth:
        client_ip = normalize_client_ip(request)
        now = __import__("time").monotonic()
        cutoff = now - AOEDE_UNAUTH_WINDOW_SEC
        with _AOEDE_UNAUTH_LOCK:
            recent = [ts for ts in _AOEDE_UNAUTH_BUCKETS.get(client_ip, []) if ts > cutoff]
            if len(recent) >= AOEDE_UNAUTH_RATE_LIMIT:
                retry_after = max(1, int(AOEDE_UNAUTH_WINDOW_SEC - (now - recent[0])) + 1)
                _AOEDE_UNAUTH_BUCKETS[client_ip] = recent
                return JSONResponse(
                    sanitize_api_payload(
                        {
                            "ok": False,
                            "error": "Quá nhiều yêu cầu phát âm thanh chưa đăng nhập. Vui lòng thử lại sau.",
                            "retry_after_seconds": retry_after,
                        }
                    ),
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
            recent.append(now)
            _AOEDE_UNAUTH_BUCKETS[client_ip] = recent
    bundle = await synthesize_aoede_phrase_audio(phrase)
    return JSONResponse(
        sanitize_api_payload(
            {
                "ok": True,
                "phrase": phrase,
                **build_aoede_http_audio_fields(bundle),
            }
        ),
        status_code=200,
    )


@router.get("/api/wokwi_files")
async def api_get_wokwi_files(request: Request) -> JSONResponse:
    """Trả về sơ đồ Wokwi diagram.json và code Arduino esp8266_smarthome.ino (yêu cầu đăng nhập)."""
    sess = await asyncio.to_thread(resolve_request_session, request, None, None)
    if not sess.is_authenticated:
        return JSONResponse(
            {
                "ok": False,
                "authenticated": False,
                "error": "Vui lòng đăng nhập để xem sơ đồ và mã nguồn phần cứng.",
            },
            status_code=401,
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )
    wokwi_dir = ROOT / "firmware_esp8266" / "wokwi"
    real_ino_path = ROOT / "firmware_esp8266" / "esp8266_smarthome" / "esp8266_smarthome.ino"
    diag = (wokwi_dir / "diagram.json").read_text(encoding="utf-8") if (wokwi_dir / "diagram.json").exists() else "{}"
    real_ino = real_ino_path.read_text(encoding="utf-8") if real_ino_path.exists() else ""
    return JSONResponse({
        "diagram_json": diag,
        "sketch_ino": real_ino,
        "esp8266_ino": real_ino,
        "ino_path": "firmware_esp8266/esp8266_smarthome/esp8266_smarthome.ino",
    })
