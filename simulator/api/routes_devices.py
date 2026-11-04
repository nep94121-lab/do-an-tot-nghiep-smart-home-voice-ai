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

import copy
import re
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from simulator.api.deps import (
    ROOT,
    _ACTIVE_BRIDGES,
    _REST_ENGINE,
    broadcast_rest_state_to_bridges,
)
from simulator.rule_engine import append_audit_log

router = APIRouter(tags=["devices"])


@router.get("/api/state")
async def api_get_state() -> JSONResponse:
    """Trả về toàn bộ snapshot trạng thái thiết bị, cảm biến và luật hiện tại."""
    return JSONResponse(_REST_ENGINE.get_snapshot())


@router.post("/api/device")
@router.post("/api/device_control")
async def api_control_device(payload: dict[str, Any]) -> JSONResponse:
    """Điều khiển bật/tắt hoặc mở/đóng thiết bị từ App Mobile hoặc Web."""
    dev_id = str(payload.get("device_id", "main_door"))
    act = str(payload.get("action", "open"))
    user_name = str(payload.get("user_name", "Nguyễn Tuấn Anh (App Android)"))
    tier = int(payload.get("tier", 1) or 1)
    source = str(payload.get("source", "mobile_app"))
    bypass = bool(payload.get("bypass_rbac", tier == 1))
    res = await _REST_ENGINE.execute_device_action(dev_id, act, source=source, bypass_rbac=bypass)
    append_audit_log(
        category="DEVICE_IO",
        event_type="mobile_device_toggle",
        summary=f"📱 [App/Web] {user_name} (Tầng {tier}): {res.get('exact_spoken_reply') or f'{dev_id} -> {act}'}",
        user_name=user_name,
        tier=tier,
        details={"device_id": dev_id, "action": act, "result": res},
    )
    await broadcast_rest_state_to_bridges()
    return JSONResponse(res)


@router.post("/api/devices/{device_id}/control")
async def api_control_device_by_path(device_id: str, payload: dict[str, Any] | None = None) -> JSONResponse:
    """Điều khiển bật/tắt thiết bị theo đường dẫn REST /api/devices/{device_id}/control."""
    body = dict(payload or {})
    body["device_id"] = device_id
    return await api_control_device(body)


@router.post("/api/mobile/schedule")
async def api_mobile_schedule(payload: dict[str, Any]) -> JSONResponse:
    """Tạo hẹn giờ từ ứng dụng di động Android."""
    dev_id = str(payload.get("device_id", "living_room_light"))
    act = str(payload.get("action", "turn_on"))
    sec = float(payload.get("seconds", 15) or 15)
    user_name = str(payload.get("user_name", "Nguyễn Tuấn Anh (App Android)"))
    tier = int(payload.get("tier", 1) or 1)
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
        tier=tier,
        details={"device_id": dev_id, "action": act, "seconds": sec, "result": res},
    )
    await broadcast_rest_state_to_bridges()
    return JSONResponse(res)


@router.post("/api/ir_learn")
async def api_ir_learn(payload: dict[str, Any]) -> JSONResponse:
    """Học lệnh điều khiển hồng ngoại IR từ xa."""
    dev_name = str(payload.get("device_name", "Điều hòa Casper"))
    act = str(payload.get("command_action", "open"))
    res = await _REST_ENGINE.learn_ir_remote_command(device_name=dev_name, command_action=act)
    await broadcast_rest_state_to_bridges()
    return JSONResponse(res)


@router.post("/api/dht11")
async def api_update_dht11(payload: dict[str, Any]) -> JSONResponse:
    """Cập nhật thông số cảm biến nhiệt độ & độ ẩm không khí DHT11 (chân D6)."""
    temp_c = float(payload.get("temp_c", 28.5))
    hum_pct = float(payload.get("humidity_pct", 65.0))
    rssi = int(payload.get("wifi_rssi_dbm", -52))
    res = await _REST_ENGINE.update_sensor_telemetry(temp_c, hum_pct, rssi)
    await broadcast_rest_state_to_bridges()
    return JSONResponse(res)


@router.post("/api/soil_moisture")
async def api_update_soil_moisture(payload: dict[str, Any]) -> JSONResponse:
    """Cập nhật cảm biến độ ẩm đất YL-69 (A0) và tự động bật/tắt bơm vườn."""
    pct = float(payload.get("soil_moisture_pct", 62.0))
    res = await _REST_ENGINE.update_soil_moisture_telemetry(pct)
    await broadcast_rest_state_to_bridges()
    return JSONResponse(res)


@router.post("/api/server_mode")
async def api_set_server_mode(payload: dict[str, Any]) -> JSONResponse:
    """Chuyển đổi chế độ Online Gemini Live <-> Offline Mạch độc lập."""
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
async def api_text_command(payload: dict[str, Any]) -> JSONResponse:
    """Xử lý khẩu lệnh dạng text, hỗ trợ offline command, cảm biến, alias và phân quyền."""
    text = str(payload.get("text", "")).strip()
    if not _REST_ENGINE.server_connected:
        res = await _REST_ENGINE.execute_offline_default_command(text, source="offline_default")
        await broadcast_rest_state_to_bridges()
        return JSONResponse(res)

    from simulator.auth_3layer import get_auth_3layer_manager
    perm_voice_res = get_auth_3layer_manager().parse_and_execute_voice_permission_command(
        spoken_text=text,
        actor_tier=_REST_ENGINE.current_tier,
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
            res_soil = await _REST_ENGINE.update_soil_moisture_telemetry(float(m_soil.group(1)))
            await broadcast_rest_state_to_bridges()
            return JSONResponse({"ok": True, "reply": res_soil["exact_spoken_reply"], "exact_spoken_reply": res_soil["exact_spoken_reply"]})
        soil = _REST_ENGINE.mqtt_bridge.soil_moisture_telemetry
        spoken = f"Độ ẩm đất hiện tại là {soil['soil_moisture_pct']}% ({soil['status_label']})."
        return JSONResponse({"ok": True, "reply": spoken, "exact_spoken_reply": spoken})

    if "tưới cây" in t_low or "bật máy bơm" in t_low:
        res = await _REST_ENGINE.execute_device_action("garden_pump", "turn_on", source="mobile_app")
        await broadcast_rest_state_to_bridges()
        return JSONResponse({"ok": True, "reply": res["exact_spoken_reply"], "exact_spoken_reply": res["exact_spoken_reply"]})

    if "tắt máy bơm" in t_low:
        res = await _REST_ENGINE.execute_device_action("garden_pump", "turn_off", source="mobile_app")
        await broadcast_rest_state_to_bridges()
        return JSONResponse({"ok": True, "reply": res["exact_spoken_reply"], "exact_spoken_reply": res["exact_spoken_reply"]})

    if "nhiệt độ" in t_low or "độ ẩm" in t_low:
        if any(w in t_low for w in ("set", "chỉnh", "đặt", "lên", "xuống", "thành", "=")):
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
        res = await _REST_ENGINE.learn_ir_remote_command("Điều hòa", "open")
        return JSONResponse({"ok": True, "reply": res["exact_spoken_reply"], "exact_spoken_reply": res["exact_spoken_reply"]})

    for phrase in _REST_ENGINE.get_merged_aliases():
        if phrase in t_low:
            res = await _REST_ENGINE.execute_alias_rule(phrase)
            return JSONResponse({"ok": True, "reply": res["exact_spoken_reply"], "exact_spoken_reply": res["exact_spoken_reply"]})

    return JSONResponse({"ok": True, "reply": f"Đã nhận lệnh: {text}", "exact_spoken_reply": f"Đã nhận lệnh: {text}"})


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
