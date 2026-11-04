"""Bộ kiểm thử tự động cho Phase 1 (FIX_PLAN_20261104.md — Mục 2 & Mục 4 Phase 1).

Kiểm tra đầy đủ 6 lỗi đã sửa trong Phase 1:
1. SECURITY: api_control_device (/api/device) không nhận bypass_rbac/tier từ client; tier lấy từ session đã xác thực.
2. text_command (/api/text_command): thực sự bật/tắt thiết bị (và tôn trọng RBAC) thay vì chỉ echo.
3. Pump rule: tắt tay garden_pump khi đất khô (< 40%) sẽ giữ trạng thái OFF (pump_manual_override_off) cho tới khi đất đủ ẩm hoặc bật lại.
4. Sensor clamping: giá trị cảm biến NaN / Inf / ngoài ngưỡng được kẹp trong miền hợp lệ (0..100% cho đất/độ ẩm, 0..60°C cho nhiệt độ), NaN không bao giờ biến thành 100%.
5. Mobile schedule RBAC: Khách Cấp 3 (tier=3) bị chặn tạo lịch tại /api/mobile/schedule và lệnh hẹn giờ tại /api/text_command.
6. Bảng 14 kịch bản trên /auth: dữ liệu trả về từ /api/auth3/overview và /api/auth3/run_test_suite có đủ passed, total, results, id (14/14, không bị undefined/undefined).
"""

from __future__ import annotations

import asyncio
import math
import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import simulator.api.deps as api_deps
import simulator.api.routes_auth as routes_auth
import simulator.api.routes_devices as routes_devices
from simulator.auth_3layer import get_auth_3layer_manager
from simulator.server import app


def _eng():
    """Trả về instance _REST_ENGINE đang gắn trực tiếp với router devices/auth."""
    eng = routes_devices._REST_ENGINE
    routes_auth._REST_ENGINE = eng
    api_deps._REST_ENGINE = eng
    return eng


@pytest.fixture(autouse=True)
def reset_rest_engine_session():
    """Đảm bảo _REST_ENGINE luôn quay về trạng thái mặc định (Chủ nhà Cấp 1) trước và sau mỗi test."""
    eng = _eng()
    eng.set_active_user("tuan_anh")
    eng.server_connected = True
    asyncio.run(eng.factory_reset())
    eng.set_active_user("tuan_anh")
    for d in ("living_room_light", "bedroom_light", "fan", "garden_pump"):
        if d in eng.devices:
            eng.devices[d]["state"] = "OFF"
    if "main_door" in eng.devices:
        eng.devices["main_door"]["state"] = "CLOSED"
    eng.pump_manual_override_off = False
    if hasattr(eng, "mqtt_bridge") and hasattr(eng.mqtt_bridge, "soil_moisture_telemetry"):
        eng.mqtt_bridge.soil_moisture_telemetry["soil_moisture_pct"] = 62.0
    api_deps._ACTIVE_BRIDGES.clear()
    yield
    eng = _eng()
    eng.set_active_user("tuan_anh")
    eng.server_connected = True
    asyncio.run(eng.factory_reset())
    eng.set_active_user("tuan_anh")
    for d in ("living_room_light", "bedroom_light", "fan", "garden_pump"):
        if d in eng.devices:
            eng.devices[d]["state"] = "OFF"
    if "main_door" in eng.devices:
        eng.devices["main_door"]["state"] = "CLOSED"
    eng.pump_manual_override_off = False
    if hasattr(eng, "mqtt_bridge") and hasattr(eng.mqtt_bridge, "soil_moisture_telemetry"):
        eng.mqtt_bridge.soil_moisture_telemetry["soil_moisture_pct"] = 62.0
    api_deps._ACTIVE_BRIDGES.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_fix1_security_device_api_ignores_client_bypass_rbac_and_tier(client: TestClient) -> None:
    """Fix 1 (SECURITY): Khách Cấp 3 gửi bypass_rbac=True, tier=1 lên /api/device vẫn bị chặn mở cửa & còi."""
    eng = _eng()
    # Đặt phiên xác thực hiện tại là Khách Cấp 3 (khach_c)
    eng.set_active_user("khach_c")
    assert eng.current_tier == 3

    # Cửa chính ban đầu đang CLOSED
    assert eng.devices["main_door"]["state"] == "CLOSED"

    # Client cố tình giả mạo payload với tier=1 và bypass_rbac=True để mở cửa chính
    resp = client.post(
        "/api/device",
        json={
            "device_id": "main_door",
            "action": "open",
            "tier": 1,
            "bypass_rbac": True,
            "user_name": "Fake Admin",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert data.get("rbac_blocked") is True
    assert data.get("tier") == 3
    assert eng.devices["main_door"]["state"] == "CLOSED"

    # Khách Cấp 3 bật đèn phòng khách (được phép theo RBAC Cấp 3)
    resp_light = client.post(
        "/api/device",
        json={"device_id": "living_room_light", "action": "turn_on"},
    )
    assert resp_light.status_code == 200
    assert resp_light.json().get("ok") is True
    assert eng.devices["living_room_light"]["state"] == "ON"

    # Gia đình Cấp 2 cũng bị chặn mở cửa chính dù gửi bypass_rbac=True
    eng.set_active_user("thanh_vien_a")
    assert eng.current_tier == 2
    resp_t2_door = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open", "tier": 1, "bypass_rbac": True},
    )
    assert resp_t2_door.json().get("ok") is False
    assert eng.devices["main_door"]["state"] == "CLOSED"


def test_fix2_text_command_executes_real_device_actions_and_respects_rbac(client: TestClient) -> None:
    """Fix 2: /api/text_command thực thi bật/tắt thiết bị thật thay vì chỉ echo."""
    eng = _eng()
    eng.set_active_user("tuan_anh")
    assert eng.devices["living_room_light"]["state"] == "OFF"
    assert eng.devices["fan"]["state"] == "OFF"

    # Bật đèn phòng khách bằng lệnh văn bản
    r1 = client.post("/api/text_command", json={"text": "Bật đèn phòng khách"})
    assert r1.status_code == 200
    assert r1.json().get("ok") is True
    assert eng.devices["living_room_light"]["state"] == "ON"

    # Bật quạt trần bằng lệnh văn bản
    r2 = client.post("/api/text_command", json={"text": "Bật quạt trần"})
    assert r2.status_code == 200
    assert r2.json().get("ok") is True
    assert eng.devices["fan"]["state"] == "ON"

    # Tắt đèn phòng khách bằng lệnh văn bản
    r3 = client.post("/api/text_command", json={"text": "Tắt đèn phòng khách"})
    assert r3.status_code == 200
    assert r3.json().get("ok") is True
    assert eng.devices["living_room_light"]["state"] == "OFF"

    # Khi ở vai trò Khách Cấp 3, lệnh văn bản "Mở cửa chính" phải bị chặn
    eng.set_active_user("khach_c")
    r_door = client.post("/api/text_command", json={"text": "Mở cửa chính"})
    assert r_door.status_code == 200
    assert r_door.json().get("ok") is False
    assert r_door.json().get("rbac_blocked") is True
    assert eng.devices["main_door"]["state"] == "CLOSED"


def test_fix3_pump_manual_override_does_not_immediately_turn_back_on(client: TestClient) -> None:
    """Fix 3: Khi đất khô (<40%) tự bật bơm, nếu người dùng tắt tay thì nhịp cảm biến tiếp theo không tự bật lại ngay."""
    eng = _eng()
    eng.set_active_user("tuan_anh")

    # 1. Độ ẩm đất giảm xuống 25% (< 40%) -> Tự động bật máy bơm
    r_dry1 = client.post("/api/soil_moisture", json={"soil_moisture_pct": 25.0})
    assert r_dry1.status_code == 200
    assert r_dry1.json().get("auto_action") == "AUTO_PUMP_ON"
    assert eng.devices["garden_pump"]["state"] == "ON"

    # 2. Người dùng tắt tay máy bơm
    r_off = client.post("/api/device", json={"device_id": "garden_pump", "action": "turn_off"})
    assert r_off.status_code == 200
    assert r_off.json().get("ok") is True
    assert eng.devices["garden_pump"]["state"] == "OFF"
    assert eng.pump_manual_override_off is True

    # 3. Cảm biến độ ẩm đất tiếp tục gửi 28% (< 40%) -> Bơm VẪN GIỮ OFF (không tự bật lại ngay)
    r_dry2 = client.post("/api/soil_moisture", json={"soil_moisture_pct": 28.0})
    assert r_dry2.status_code == 200
    assert r_dry2.json().get("auto_action") == "MANUAL_OVERRIDE_KEEP_OFF"
    assert eng.devices["garden_pump"]["state"] == "OFF"

    # 4. Khi đất ẩm trở lại (>= 40%, ví dụ 55%) -> Cờ manual override được xóa, sẵn sàng cho chu kỳ khô tiếp theo
    r_norm = client.post("/api/soil_moisture", json={"soil_moisture_pct": 55.0})
    assert r_norm.status_code == 200
    assert eng.pump_manual_override_off is False

    # 5. Chu kỳ khô mới (22%) -> Tự bật bơm lại bình thường
    r_dry3 = client.post("/api/soil_moisture", json={"soil_moisture_pct": 22.0})
    assert r_dry3.status_code == 200
    assert r_dry3.json().get("auto_action") == "AUTO_PUMP_ON"
    assert eng.devices["garden_pump"]["state"] == "ON"


def test_fix4_sensor_clamping_nan_and_out_of_bounds(client: TestClient) -> None:
    """Fix 4: Cảm biến kẹp giá trị hợp lệ; NaN / Inf / âm / >100 không làm sai lệch hoặc biến NaN thành 100%."""
    eng = _eng()
    # Đặt giá trị hợp lệ ban đầu = 55.0%
    client.post("/api/soil_moisture", json={"soil_moisture_pct": 55.0})
    assert eng.mqtt_bridge.soil_moisture_telemetry["soil_moisture_pct"] == 55.0

    # Truyền NaN trực tiếp vào update_soil_moisture_telemetry -> Phải giữ fallback (55.0), tuyệt đối KHÔNG thành 100.0
    asyncio.run(eng.update_soil_moisture_telemetry(float("nan")))
    soil_after_nan = eng.mqtt_bridge.soil_moisture_telemetry["soil_moisture_pct"]
    assert math.isfinite(soil_after_nan)
    assert soil_after_nan == 55.0
    assert soil_after_nan != 100.0

    # Truyền chuỗi "NaN" qua REST API -> Giữ fallback (55.0), không thành 100.0
    r_str_nan = client.post("/api/soil_moisture", json={"soil_moisture_pct": "NaN"})
    assert r_str_nan.status_code == 200
    assert eng.mqtt_bridge.soil_moisture_telemetry["soil_moisture_pct"] == 55.0

    # Truyền giá trị âm (-25) và vượt ngưỡng (250) -> Kẹp đúng về 0.0 và 100.0
    client.post("/api/soil_moisture", json={"soil_moisture_pct": -25.0})
    assert eng.mqtt_bridge.soil_moisture_telemetry["soil_moisture_pct"] == 0.0

    client.post("/api/soil_moisture", json={"soil_moisture_pct": 250.0})
    assert eng.mqtt_bridge.soil_moisture_telemetry["soil_moisture_pct"] == 100.0

    # Kiểm tra DHT11: kẹp nhiệt độ (0..60°C) và độ ẩm (0..100%)
    client.post("/api/dht11", json={"temp_c": 999.0, "humidity_pct": -15.0, "wifi_rssi_dbm": 50})
    dht = eng.mqtt_bridge.dht11_telemetry
    assert dht["temp_c"] == 60.0
    assert dht["humidity_pct"] == 0.0
    assert dht["wifi_rssi_dbm"] == 0


def test_fix5_tier3_guest_blocked_from_creating_mobile_schedule(client: TestClient) -> None:
    """Fix 5: Khách Cấp 3 (tier=3) bị chặn tạo lịch hẹn giờ trên mobile (/api/mobile/schedule & /api/text_command)."""
    eng = _eng()
    # Khi đang ở phiên Khách Cấp 3
    eng.set_active_user("khach_c")
    assert eng.current_tier == 3
    timers_before = len(eng.active_timers)

    # Gọi /api/mobile/schedule (dù cố gửi tier=1 cũng bị chặn vì session là tier 3)
    r_sched = client.post(
        "/api/mobile/schedule",
        json={"device_id": "living_room_light", "action": "turn_on", "seconds": 15, "tier": 1},
    )
    assert r_sched.status_code == 403
    data_sched = r_sched.json()
    assert data_sched.get("ok") is False
    assert data_sched.get("rbac_blocked") is True
    assert len(eng.active_timers) == timers_before

    # Gọi lệnh hẹn giờ qua /api/text_command (luồng PWA submitPwaSchedule)
    r_text_sched = client.post(
        "/api/text_command",
        json={"text": "Hẹn 10 giây nữa bật đèn phòng khách"},
    )
    assert r_text_sched.status_code == 403
    assert r_text_sched.json().get("ok") is False
    assert r_text_sched.json().get("rbac_blocked") is True
    assert len(eng.active_timers) == timers_before

    # Chủ nhà Cấp 1 tạo lịch bình thường
    eng.set_active_user("tuan_anh")
    r_owner_sched = client.post(
        "/api/mobile/schedule",
        json={"device_id": "living_room_light", "action": "turn_on", "seconds": 15},
    )
    assert r_owner_sched.status_code == 200
    assert r_owner_sched.json().get("ok") is True
    assert len(eng.active_timers) == timers_before + 1


def test_fix6_auth_14_scenarios_report_keys_complete(client: TestClient) -> None:
    """Fix 6: /api/auth3/overview và /api/auth3/run_test_suite trả đủ passed, total, results, id cho bảng 14 kịch bản."""
    # Reset latest_test_report để kiểm tra trường hợp /api/auth3/overview tự khởi chạy lần đầu
    mgr = get_auth_3layer_manager()
    mgr.latest_test_report = {}

    r_ov = client.get("/api/auth3/overview")
    assert r_ov.status_code == 200
    ov = r_ov.json()
    rep = ov.get("test_report") or {}
    assert rep.get("total") == 14
    assert rep.get("passed") == 14
    assert rep.get("total_cases") == 14
    assert rep.get("passed_cases") == 14
    results = rep.get("results") or []
    assert len(results) == 14
    for tc in results:
        assert tc.get("id"), f"Thiếu trường id trong kịch bản: {tc}"
        assert tc.get("test_id") == tc.get("id")
        assert tc.get("passed") is True

    # Kiểm tra thêm endpoint /api/auth3/run_test_suite
    r_run = client.post("/api/auth3/run_test_suite", json={"send_live_email": False})
    assert r_run.status_code == 200
    run_data = r_run.json()
    assert run_data.get("passed") == 14
    assert run_data.get("total") == 14
    assert len(run_data.get("results", [])) == 14
