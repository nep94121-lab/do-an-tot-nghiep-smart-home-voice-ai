"""Router Điều Khiển Thiết Bị, Giả Lập Cảm Biến, SQLite WAL & Wokwi Firmware (Feature 14).

Danh sách 9 endpoints:
1. GET /api/state: Snapshot trạng thái toàn bộ thiết bị.
2. POST /api/device: Bật/tắt hoặc mở/đóng thiết bị (Actuate-First).
3. POST /api/mobile/schedule: Đặt hẹn giờ linh hoạt từ Mobile App.
4. POST /api/ir_learn: Học lệnh điều khiển từ xa hồng ngoại 38kHz.
5. POST /api/dht11: Cập nhật thông số cảm biến nhiệt độ & độ ẩm DHT11 (chân D6).
6. POST /api/soil_moisture: Cập nhật cảm biến độ ẩm đất YL-69 (A0) & tự kích hoạt máy bơm.
7. POST /api/server_mode: Chuyển đổi Online Gemini Live <-> Offline Mạch độc lập.
8. POST /api/text_command: Xử lý mệnh lệnh văn bản, cảm biến, alias và phân quyền giọng nói.
9. GET /api/wokwi_files: Trả về sơ đồ Wokwi diagram.json và mã nguồn Arduino esp8266_smarthome.ino.
"""

from __future__ import annotations

import base64
import copy
import re
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
from simulator.voice.stt_pipeline import process_voice_command_pipeline
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

    tn = strip_vietnamese_diacritics(mapped_text)

    if any(k in mapped_text for k in ("tất cả thiết bị", "toàn bộ thiết bị", "hết thiết bị", "mọi thiết bị", "all_devices")) or any(
        k in tn for k in ("tat ca thiet bi", "toan bo thiet bi", "het thiet bi", "moi thiet bi")
    ):
        return ["all_devices"]
    if any(k in mapped_text for k in ("tất cả đèn", "toàn bộ đèn", "hai đèn", "2 đèn", "cả 2 đèn", "cả hai đèn", "hết đèn", "các đèn", "all_lights")) or any(
        k in tn for k in ("tat ca den", "toan bo den", "hai den", "2 den", "ca 2 den", "ca hai den", "het den", "cac den")
    ):
        return ["all_lights"]

    targets: list[str] = []
    if (
        any(k in mapped_text for k in ("cửa chính", "cửa lớn", "cửa nhà", "cửa ra vào", "cửa sắt", "công tắc cổng", "main_door"))
        or any(k in tn for k in ("cua chinh", "cua lon", "cua nha", "cua ra vao", "cua sat", "cong tac cong", "mo cua", "dong cua", "khoa cua"))
        or re.search(r"\bcửa\b", mapped_text)
    ):
        targets.append("main_door")
    if any(k in mapped_text for k in ("đèn phòng khách", "đèn khách", "living_room_light")) or any(
        k in tn for k in ("den phong khach", "den khach")
    ):
        targets.append("living_room_light")
    if any(k in mapped_text for k in ("đèn phòng ngủ", "đèn ngủ", "bedroom_light")) or any(
        k in tn for k in ("den phong ngu", "den ngu")
    ):
        targets.append("bedroom_light")
    if any(k in mapped_text for k in ("quạt trần", "quạt điện", "quạt", "fan")) or any(
        k in tn for k in ("quat tran", "quat dien", "tat quat", "bat quat")
    ) or re.search(r"\bquat\b", tn):
        targets.append("fan")
    if any(k in mapped_text for k in ("điều hòa", "máy lạnh")) or any(
        k in tn for k in ("dieu hoa", "may lanh")
    ) or re.search(r"\bac\b", tn):
        targets.append("ac")
    if any(k in mapped_text for k in ("còi báo động", "báo động", "còi hú", "chống trộm", "alarm_siren")) or any(
        k in tn for k in ("coi bao dong", "bao dong", "coi hu", "chong trom")
    ) or re.search(r"\bcòi\b", mapped_text):
        targets.append("alarm_siren")
    if any(k in mapped_text for k in ("máy bơm", "bơm nước", "bơm vườn", "tưới cây", "tưới vườn", "garden_pump")) or any(
        k in tn for k in ("may bom", "bom nuoc", "bom vuon", "tuoi cay", "tuoi vuon")
    ):
        targets.append("garden_pump")

    if not targets and ("đèn" in mapped_text or re.search(r"\bden\b", tn)):
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


@router.get("/api/state")
async def api_get_state(request: Request) -> JSONResponse:
    """Trả về snapshot trạng thái theo phiên người dùng đang xác thực (hoặc bản rút gọn thiết bị công khai nếu chưa đăng nhập)."""
    _REST_ENGINE.sync_from_shared_store(force=True)
    sess = resolve_request_session(request, payload=None, engine=None)
    explicit_header_token = bool(
        str(request.headers.get("authorization") or "").strip()
        or str(request.headers.get("x-session-token") or "").strip()
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
            _REST_ENGINE.get_public_device_snapshot(),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )
    return JSONResponse(
        _REST_ENGINE.get_snapshot(session=sess),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
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

    req_sess = resolve_request_session(request, payload=body, engine=None)
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
    res["rbac_blocked"] = not bool(res.get("ok"))
    res["snapshot"] = _REST_ENGINE.get_snapshot(session=session)
    if not res.get("ok") and not res.get("error"):
        res["error"] = res.get("exact_spoken_reply") or "Bị chặn bởi phân quyền RBAC."
    spoken_dev_ctrl = str(res.get("exact_spoken_reply") or res.get("error") or "").strip()
    if not res.get("ok"):
        res["rejection_speech"] = spoken_dev_ctrl

    append_audit_log(
        category="DEVICE_IO",
        event_type="mobile_device_toggle",
        summary=f"📱 [App/Web] {session_user} (Tầng {session_tier}): {res.get('exact_spoken_reply') or f'{dev_id} -> {act}'}",
        user_name=session_user,
        tier=session_tier,
        details={
            "device_id": dev_id,
            "action": act,
            "target_state": target_state,
            "client_id": client_id,
            "client_seq": client_seq,
            "request_id": request_id,
            "result": res,
        },
    )
    await broadcast_rest_state_to_bridges()
    status_code = 200
    if not res.get("ok") and session.source != "legacy_test":
        status_code = 403
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
    dev_id = str(body.get("device_id") or "living_room_light").strip() or "living_room_light"
    act = str(body.get("action") or "turn_on").strip() or "turn_on"
    sec = _REST_ENGINE.mqtt_bridge._clamp_sensor_float(body.get("seconds", 15), 1.0, 86400.0, 15.0)

    req_sess = resolve_request_session(request, payload=body, engine=None)
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

    if effective_tier >= 3 and not bool(_REST_ENGINE.system_policies.get("tier3_can_schedule_timer", False)):
        msg = "Từ chối: Khách (Cấp 3) không có quyền tạo lịch hẹn giờ thiết bị."
        append_audit_log(
            category="TIMER_RULE",
            event_type="mobile_schedule_blocked_rbac",
            summary=f"🚫 [RBAC] Chặn tạo lịch hẹn giờ từ {user_name} (Tầng {effective_tier}): {dev_id} -> {act}",
            user_name=user_name,
            tier=effective_tier,
            details={"device_id": dev_id, "action": act, "seconds": sec, "blocked": True},
        )
        return JSONResponse(
            {
                "ok": False,
                "rbac_blocked": True,
                "tier": effective_tier,
                "error": msg,
                "exact_spoken_reply": msg,
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

    res = await _REST_ENGINE.schedule_timer_flexible(
        device_id=dev_id,
        action=act,
        seconds=sec,
    )
    append_audit_log(
        category="TIMER_RULE",
        event_type="mobile_schedule_created",
        summary=f"⏰ [App Android] {user_name} đặt hẹn giờ {int(sec)}s: {dev_id} -> {act}",
        user_name=user_name,
        tier=effective_tier,
        details={"device_id": dev_id, "action": act, "seconds": sec, "result": res},
    )
    await broadcast_rest_state_to_bridges()
    return JSONResponse(res)


@router.post("/api/ir_learn")
async def api_ir_learn(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Học lệnh điều khiển hồng ngoại IR từ xa."""
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
    dev_name = str(body.get("device_name") or "Điều hòa Casper")
    act = str(body.get("command_action") or "open")
    res = await _REST_ENGINE.learn_ir_remote_command(device_name=dev_name, command_action=act)
    await broadcast_rest_state_to_bridges()
    return JSONResponse(res)


@router.post("/api/dht11")
async def api_update_dht11(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Cập nhật thông số cảm biến nhiệt độ & độ ẩm không khí DHT11 (chân D6)."""
    body = payload if isinstance(payload, dict) else {}
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
    """Cập nhật cảm biến độ ẩm đất YL-69 (A0) và tự động bật/tắt bơm vườn."""
    body = payload if isinstance(payload, dict) else {}
    error = _owner_error(request, body)
    if error is not None:
        return error
    pct = body.get("soil_moisture_pct", 62.0)
    res = await _REST_ENGINE.update_soil_moisture_telemetry(pct)
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


@router.post("/api/text_command")
async def api_text_command(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Xử lý khẩu lệnh dạng text, hỗ trợ offline command, cảm biến, alias và phân quyền."""
    body = payload if isinstance(payload, dict) else {}
    text = str(body.get("text", "")).strip()

    req_sess = resolve_request_session(request, payload=body, engine=None)
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

    t_low = text.lower()
    if "độ ẩm đất" in t_low or "cảm biến đất" in t_low:
        m_soil = re.search(r"(\d+(?:\.\d+)?)\s*%?", t_low)
        if m_soil and any(w in t_low for w in ("set", "chỉnh", "đặt", "lên", "xuống", "thành", "=")):
            error = _owner_error(request, body)
            if error is not None:
                return error
            res_soil = await _REST_ENGINE.update_soil_moisture_telemetry(float(m_soil.group(1)))
            await broadcast_rest_state_to_bridges()
            return JSONResponse({"ok": True, "reply": res_soil["exact_spoken_reply"], "exact_spoken_reply": res_soil["exact_spoken_reply"]})
        soil = _REST_ENGINE.mqtt_bridge.soil_moisture_telemetry
        spoken = f"Độ ẩm đất hiện tại là {soil['soil_moisture_pct']}% ({soil['status_label']})."
        return JSONResponse({"ok": True, "reply": spoken, "exact_spoken_reply": spoken})

    if "tưới cây" in t_low or "bật máy bơm" in t_low:
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
        res = await _REST_ENGINE.execute_device_action(
            "garden_pump",
            "turn_on",
            source="text_command",
            bypass_rbac=False,
            request_tier=effective_tier,
            request_user_name=effective_user,
            request_role=effective_role,
        )
        await broadcast_rest_state_to_bridges()
        status_code = 200 if (res.get("ok") or session.source == "legacy_test") else 403
        return JSONResponse({
            "ok": bool(res.get("ok")),
            "rbac_blocked": not bool(res.get("ok")),
            "reply": res["exact_spoken_reply"],
            "exact_spoken_reply": res["exact_spoken_reply"],
            "results": res.get("results", []),
        }, status_code=status_code)

    if "tắt máy bơm" in t_low:
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
        res = await _REST_ENGINE.execute_device_action(
            "garden_pump",
            "turn_off",
            source="text_command",
            bypass_rbac=False,
            request_tier=effective_tier,
            request_user_name=effective_user,
            request_role=effective_role,
        )
        await broadcast_rest_state_to_bridges()
        status_code = 200 if (res.get("ok") or session.source == "legacy_test") else 403
        return JSONResponse({
            "ok": bool(res.get("ok")),
            "rbac_blocked": not bool(res.get("ok")),
            "reply": res["exact_spoken_reply"],
            "exact_spoken_reply": res["exact_spoken_reply"],
            "results": res.get("results", []),
        }, status_code=status_code)

    if "nhiệt độ" in t_low or "độ ẩm" in t_low:
        if any(w in t_low for w in ("set", "chỉnh", "đặt", "lên", "xuống", "thành", "=")):
            error = _owner_error(request, body)
            if error is not None:
                return error
            cur_dht = _REST_ENGINE.mqtt_bridge.dht11_telemetry
            m_t = re.search(r"nhiệt độ[^\d]*(\d+(?:\.\d+)?)", t_low)
            m_h = re.search(r"độ ẩm[^\d]*(\d+(?:\.\d+)?)", t_low)
            t_val = float(m_t.group(1)) if m_t else float(cur_dht.get("temp_c", 28.5))
            h_val = float(m_h.group(1)) if m_h else float(cur_dht.get("humidity_pct", 65.0))
            res_dht = await _REST_ENGINE.update_sensor_telemetry(t_val, h_val)
            await broadcast_rest_state_to_bridges()
            return JSONResponse({"ok": True, "reply": res_dht["exact_spoken_reply"], "exact_spoken_reply": res_dht["exact_spoken_reply"]})
        dht = _REST_ENGINE.mqtt_bridge.dht11_telemetry
        spoken = f"Nhiệt độ phòng là {dht['temp_c']}°C, độ ẩm {dht['humidity_pct']}%."
        return JSONResponse({"ok": True, "reply": spoken, "exact_spoken_reply": spoken})

    if "học lệnh" in t_low or "remote" in t_low:
        error = _owner_error(request, body)
        if error is not None:
            return error
        res = await _REST_ENGINE.learn_ir_remote_command("Điều hòa", "open")
        return JSONResponse({"ok": True, "reply": res["exact_spoken_reply"], "exact_spoken_reply": res["exact_spoken_reply"]})

    for phrase in _REST_ENGINE.get_merged_aliases():
        if phrase in t_low:
            error = _owner_error(request, body)
            if error is not None:
                return error
            res = await _REST_ENGINE.execute_alias_rule(phrase)
            await broadcast_rest_state_to_bridges()
            return JSONResponse({
                "ok": bool(res.get("ok", True)),
                "reply": res["exact_spoken_reply"],
                "exact_spoken_reply": res["exact_spoken_reply"],
                "results": res.get("results", []),
            })

    # Xử lý lệnh hẹn giờ / đặt lịch qua văn bản (예: "Hẹn 10 giây nữa bật đèn phòng khách")
    if "hẹn" in t_low or "đặt lịch" in t_low:
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
        if effective_tier >= 3 and not bool(_REST_ENGINE.system_policies.get("tier3_can_schedule_timer", False)):
            msg_sched = "Từ chối: Khách (Cấp 3) không có quyền tạo lịch hẹn giờ thiết bị."
            return JSONResponse(
                {
                    "ok": False,
                    "rbac_blocked": True,
                    "tier": effective_tier,
                    "error": msg_sched,
                    "reply": msg_sched,
                    "exact_spoken_reply": msg_sched,
                },
                status_code=403,
            )
        targets = _parse_text_device_targets(t_low)
        act = _parse_text_action(t_low) or "turn_on"
        dev_id = targets[0] if targets else "living_room_light"
        if effective_tier >= 2:
            allowed, reason = _REST_ENGINE.check_device_permission(dev_id, actor_tier=effective_tier)
            if not allowed:
                return JSONResponse(
                    {
                        "ok": False,
                        "rbac_blocked": True,
                        "tier": effective_tier,
                        "error": reason,
                        "reply": reason,
                        "exact_spoken_reply": reason,
                    },
                    status_code=403,
                )
        m_sec = re.search(r"(\d+(?:\.\d+)?)\s*(?:giây|s\b)", t_low)
        m_min = re.search(r"(\d+(?:\.\d+)?)\s*(?:phút|p\b|m\b)", t_low)
        m_hr = re.search(r"(\d+(?:\.\d+)?)\s*(?:giờ|tiếng|h\b)", t_low)
        seconds = float(m_sec.group(1)) if m_sec else 0.0
        minutes = float(m_min.group(1)) if m_min else 0.0
        hours = float(m_hr.group(1)) if m_hr else 0.0
        if seconds <= 0 and minutes <= 0 and hours <= 0:
            seconds = 10.0
        res_timer = await _REST_ENGINE.schedule_timer_flexible(
            device_id=dev_id,
            action=act,
            seconds=seconds,
            minutes=minutes,
            hours=hours,
        )
        await broadcast_rest_state_to_bridges()
        spoken_timer = res_timer.get("exact_spoken_reply") or res_timer.get("message") or f"Đã đặt hẹn giờ cho {dev_id}."
        return JSONResponse({
            "ok": bool(res_timer.get("ok", True)),
            "reply": spoken_timer,
            "exact_spoken_reply": spoken_timer,
            "timer": res_timer,
        })

    tn_cmd = strip_vietnamese_diacritics(t_low)
    if any(k in tn_cmd for k in ("reset he thong", "khoi phuc cai dat goc", "factory reset")):
        error = _owner_error(request, body)
        if error is not None:
            return error
        res_rst = await _REST_ENGINE.manual_factory_reset()
        await broadcast_rest_state_to_bridges()
        spoken_rst = res_rst.get("exact_spoken_reply") or "Đã khôi phục cài đặt gốc toàn hệ thống."
        return JSONResponse({
            "ok": True,
            "reply": spoken_rst,
            "exact_spoken_reply": spoken_rst,
            "snapshot": _REST_ENGINE.get_snapshot(session=session),
        })

    # Xử lý khẩu lệnh bật/tắt/mở/đóng thiết bị trực tiếp (kể cả word_mappings)
    targets = _parse_text_device_targets(t_low)
    act = _parse_text_action(t_low)
    if targets and act:
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
        dev_arg = ",".join(targets)
        res_dev = await _REST_ENGINE.execute_device_action(
            device_id=dev_arg,
            action=act,
            source="text_command",
            bypass_rbac=False,
            request_tier=effective_tier,
            request_user_name=effective_user,
            request_role=effective_role,
        )
        await broadcast_rest_state_to_bridges()
        spoken_dev = res_dev.get("exact_spoken_reply") or f"Đã xử lý lệnh: {text}"
        status_code = 200 if (res_dev.get("ok") or session.source == "legacy_test") else 403
        return JSONResponse({
            "ok": bool(res_dev.get("ok")),
            "rbac_blocked": not bool(res_dev.get("ok")),
            "tier": effective_tier,
            "reply": spoken_dev,
            "exact_spoken_reply": spoken_dev,
            "rejection_speech": spoken_dev if not res_dev.get("ok") else "",
            "results": res_dev.get("results", []),
            "snapshot": _REST_ENGINE.get_snapshot(session=session),
        }, status_code=status_code)

    return JSONResponse({
        "ok": True,
        "reply": f"Đã nhận lệnh: {text}",
        "exact_spoken_reply": f"Đã nhận lệnh: {text}",
        "snapshot": _REST_ENGINE.get_snapshot(session=session),
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
    if "snapshot" not in result and hasattr(_REST_ENGINE, "get_snapshot") and session is not None:
        try:
            result["snapshot"] = _REST_ENGINE.get_snapshot(session=session)
        except Exception:
            pass
    return JSONResponse(result, status_code=status)


@router.post("/api/voice/aoede_phrase")
async def api_voice_aoede_phrase(payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Trả về âm thanh 24kHz PCM/WAV của duy nhất giọng Aoede (Gemini Live) cho 2 câu cố định tiếng Việt."""
    from simulator.live.tts_rejection_vi import (
        FIXED_REJECTION_PHRASE_VI,
        FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
        build_aoede_http_audio_fields,
        synthesize_aoede_phrase_audio,
    )

    body = payload if isinstance(payload, dict) else {}
    phrase = str(body.get("phrase") or body.get("text") or "").strip()
    if phrase not in (FIXED_REJECTION_PHRASE_VI, FIXED_SAFE_DENY_REPEAT_PHRASE_VI):
        return JSONResponse(
            sanitize_api_payload(
                {
                    "ok": False,
                    "error": "Chỉ hỗ trợ phát giọng Aoede cho 2 câu thoại từ chối / yêu cầu nói lại cố định!",
                }
            ),
            status_code=400,
        )
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
async def api_get_wokwi_files() -> JSONResponse:
    """Trả về sơ đồ Wokwi diagram.json và code Arduino esp8266_smarthome.ino."""
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
