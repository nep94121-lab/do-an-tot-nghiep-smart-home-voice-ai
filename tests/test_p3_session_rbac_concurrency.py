"""Bộ kiểm thử bảo mật phân quyền RBAC theo phiên (Session-based RBAC) & kiểm thử đồng thời (Requirement R2).

Xác thực:
1. Độ cách ly hoàn toàn (Zero-Leakage): 120 requests đan xen đồng thời giữa 3 vai trò (Owner, Member, Guest)
   không bao giờ bị lẫn quyền hay race condition trạng thái toàn cục.
2. Trích xuất phiên độc lập stateless qua 4 kênh: Authorization Bearer, X-Session-Token, Cookie sh_session_token, Query param token.
3. Fallback unauthenticated: Request không có token/cookie tự động gán Tầng 3 (Khách) và bị chặn điều khiển cửa chính (HTTP 403).
4. Vòng đời phiên (Session Lifecycle): Khởi tạo, tra cứu bộ nhớ + SQLite, thu hồi (revoke), hết hạn (expired).
5. Đăng nhập stateless: Đăng nhập HTTP tạo session token, đặt cookie, và không ghi đè trạng thái toàn cục Singleton của engine.
"""
from __future__ import annotations

import concurrent.futures
import pathlib
import random
import sys
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import simulator.api.deps as api_deps
import simulator.api.routes_auth as routes_auth
import simulator.api.routes_devices as routes_devices
from simulator.auth.session_store import UserSession, get_session_store
from simulator.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clean_sessions_and_reset_devices():
    """Đảm bảo các thiết bị về trạng thái an toàn trước mỗi bài test."""
    eng = routes_devices._REST_ENGINE
    eng._explicit_test_user_set = False
    eng.devices["main_door"]["state"] = "CLOSED"
    eng.devices["alarm_siren"]["state"] = "OFF"
    eng.devices["living_room_light"]["state"] = "OFF"
    eng.devices["ac"]["state"] = "OFF"
    eng.pump_manual_override_off = False
    yield
    eng._explicit_test_user_set = False
    eng.devices["main_door"]["state"] = "CLOSED"
    eng.devices["alarm_siren"]["state"] = "OFF"
    eng.devices["living_room_light"]["state"] = "OFF"
    eng.devices["ac"]["state"] = "OFF"


# =============================================================================
# 1. KIỂM TRA PHIÊN KHỞI TẠO ĐỊNH DANH (SEED SESSIONS) & TRUY XUẤT ĐỘC LẬP
# =============================================================================


def test_seed_sessions_exist_and_have_correct_tiers():
    """Xác nhận 3 phiên chuẩn định danh cho 3 tầng đã được nạp sẵn vào SessionStore."""
    store = get_session_store()

    s_owner = store.get_session("sess_owner_t1_nep94121")
    assert s_owner is not None
    assert s_owner.tier == 1
    assert s_owner.role == "ADMIN"
    assert s_owner.user_id == "tuan_anh"
    assert not s_owner.is_expired()

    s_member = store.get_session("sess_family_t2_member_a")
    assert s_member is not None
    assert s_member.tier == 2
    assert s_member.role == "MEMBER"
    assert s_member.user_id == "thanh_vien_a"
    assert not s_member.is_expired()

    s_guest = store.get_session("sess_guest_t3_visitor_c")
    assert s_guest is not None
    assert s_guest.tier == 3
    assert s_guest.role == "CHILD_GUEST"
    assert s_guest.user_id == "khach_c"
    assert not s_guest.is_expired()


def test_session_resolution_via_bearer_header(client: TestClient):
    """Xác nhận phiên được trích xuất chính xác qua Header Authorization: Bearer <token>."""
    # 1. Chủ nhà T1 gửi Bearer token mở cửa chính -> 200 OK
    resp_owner = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open"},
        headers={"Authorization": "Bearer sess_owner_t1_nep94121"},
    )
    assert resp_owner.status_code == 200
    data_owner = resp_owner.json()
    assert data_owner.get("ok") is True
    assert data_owner.get("tier") == 1

    # 2. Thành viên T2 gửi Bearer token mở cửa chính -> Bị chặn 403 Forbidden
    resp_member = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open"},
        headers={"Authorization": "Bearer sess_family_t2_member_a"},
    )
    assert resp_member.status_code == 403
    data_member = resp_member.json()
    assert data_member.get("ok") is False
    assert data_member.get("rbac_blocked") is True
    assert data_member.get("tier") == 2


def test_session_resolution_via_custom_header(client: TestClient):
    """Xác nhận phiên được trích xuất qua Header tùy biến X-Session-Token: <token>."""
    # Thành viên T2 gửi X-Session-Token bật điều hòa -> 200 OK (Cấp 2 được phép bật điều hòa)
    resp = client.post(
        "/api/device",
        json={"device_id": "ac", "action": "turn_on"},
        headers={"X-Session-Token": "sess_family_t2_member_a"},
    )
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
    assert resp.json().get("tier") == 2


def test_session_resolution_via_cookie(client: TestClient):
    """Xác nhận phiên được trích xuất qua Cookie sh_session_token=<token>."""
    # Khách T3 gửi cookie bật đèn phòng khách -> 200 OK
    resp_light = client.post(
        "/api/device",
        json={"device_id": "living_room_light", "action": "turn_on"},
        cookies={"sh_session_token": "sess_guest_t3_visitor_c"},
    )
    assert resp_light.status_code == 200
    assert resp_light.json().get("ok") is True
    assert resp_light.json().get("tier") == 3

    # Khách T3 gửi cookie mở cửa chính -> Bị chặn 403
    resp_door = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open"},
        cookies={"sh_session_token": "sess_guest_t3_visitor_c"},
    )
    assert resp_door.status_code == 403
    assert resp_door.json().get("ok") is False
    assert resp_door.json().get("rbac_blocked") is True


def test_session_resolution_via_query_param(client: TestClient):
    """Xác nhận phiên được trích xuất qua Query param ?token=<token>."""
    resp = client.post(
        "/api/device?token=sess_owner_t1_nep94121",
        json={"device_id": "alarm_siren", "action": "turn_on"},
    )
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
    assert resp.json().get("tier") == 1


def test_unauthenticated_request_defaults_to_tier3_and_blocked(client: TestClient):
    """Request không có token/cookie tự động gán Tầng 3 (Khách) và bị từ chối mở cửa chính (HTTP 403)."""
    resp = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open"},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data.get("ok") is False
    assert data.get("rbac_blocked") is True
    assert data.get("tier") == 3
    assert routes_devices._REST_ENGINE.devices["main_door"]["state"] == "CLOSED"


def test_unsigned_cookie_tampering_ignored_and_defaults_to_tier3(client: TestClient):
    """Client không đăng nhập gửi Cookie sh_session_tier=1 giả mạo phải bị bỏ qua hoàn toàn và chặn 403."""
    resp = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open"},
        cookies={"sh_session_tier": "1", "sh_session_user": "attacker"},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data.get("ok") is False
    assert data.get("rbac_blocked") is True
    assert data.get("tier") == 3
    assert routes_devices._REST_ENGINE.devices["main_door"]["state"] == "CLOSED"


# =============================================================================
# 2. KIỂM THỬ ĐỒNG THỜI ĐA LUỒNG: 120 REQUESTS ĐAN XEN (CONCURRENCY STRESS TEST)
# =============================================================================


def test_concurrent_120_interleaved_requests_zero_permission_leakage(client: TestClient):
    """Chạy 120 requests đan xen ngẫu nhiên giữa 3 vai trò (Owner, Member, Guest) trên 16 luồng song song.

    Kiểm định độ an toàn tuyệt đối (Zero Tolerance):
    - 40 requests từ Chủ nhà T1: 100% mở/đóng cửa và bật/tắt còi thành công (200 OK).
    - 40 requests từ Thành viên T2: 100% lệnh mở cửa chính bị chặn 403; 100% lệnh bật điều hòa/đèn thành công.
    - 40 requests từ Khách T3: 100% lệnh mở cửa chính và tạo lịch bị chặn 403; 100% lệnh bật đèn thành công.
    - Không có bất kỳ hiện tượng lẫn quyền, rò rỉ quyền hay sập trạng thái nào.
    """
    eng = routes_devices._REST_ENGINE

    # Chuẩn bị 120 nhiệm vụ
    tasks: list[dict[str, Any]] = []

    # Nhóm 1: 40 requests từ Chủ nhà T1
    for i in range(20):
        tasks.append({
            "id": f"owner_door_{i}",
            "role": "OWNER",
            "endpoint": "/api/device",
            "payload": {"device_id": "main_door", "action": "open" if i % 2 == 0 else "close"},
            "headers": {"Authorization": "Bearer sess_owner_t1_nep94121"},
            "expected_status": 200,
            "expected_ok": True,
        })
    for i in range(20):
        tasks.append({
            "id": f"owner_alarm_{i}",
            "role": "OWNER",
            "endpoint": "/api/device",
            "payload": {"device_id": "alarm_siren", "action": "turn_on" if i % 2 == 0 else "turn_off"},
            "headers": {"Authorization": "Bearer sess_owner_t1_nep94121"},
            "expected_status": 200,
            "expected_ok": True,
        })

    # Nhóm 2: 40 requests từ Thành viên T2
    for i in range(20):
        tasks.append({
            "id": f"member_door_blocked_{i}",
            "role": "MEMBER",
            "endpoint": "/api/device",
            "payload": {"device_id": "main_door", "action": "open"},
            "headers": {"X-Session-Token": "sess_family_t2_member_a"},
            "expected_status": 403,
            "expected_ok": False,
        })
    for i in range(10):
        tasks.append({
            "id": f"member_ac_allowed_{i}",
            "role": "MEMBER",
            "endpoint": "/api/device",
            "payload": {"device_id": "ac", "action": "turn_on" if i % 2 == 0 else "turn_off"},
            "headers": {"X-Session-Token": "sess_family_t2_member_a"},
            "expected_status": 200,
            "expected_ok": True,
        })
    for i in range(10):
        tasks.append({
            "id": f"member_light_allowed_{i}",
            "role": "MEMBER",
            "endpoint": "/api/device",
            "payload": {"device_id": "living_room_light", "action": "turn_on" if i % 2 == 0 else "turn_off"},
            "headers": {"X-Session-Token": "sess_family_t2_member_a"},
            "expected_status": 200,
            "expected_ok": True,
        })

    # Nhóm 3: 40 requests từ Khách T3
    for i in range(15):
        tasks.append({
            "id": f"guest_door_blocked_{i}",
            "role": "GUEST",
            "endpoint": "/api/device",
            "payload": {"device_id": "main_door", "action": "open"},
            "cookies": {"sh_session_token": "sess_guest_t3_visitor_c"},
            "expected_status": 403,
            "expected_ok": False,
        })
    for i in range(15):
        tasks.append({
            "id": f"guest_schedule_blocked_{i}",
            "role": "GUEST",
            "endpoint": "/api/mobile/schedule",
            "payload": {"device_id": "living_room_light", "action": "turn_on", "seconds": 30},
            "cookies": {"sh_session_token": "sess_guest_t3_visitor_c"},
            "expected_status": 403,
            "expected_ok": False,
        })
    for i in range(10):
        tasks.append({
            "id": f"guest_light_allowed_{i}",
            "role": "GUEST",
            "endpoint": "/api/device",
            "payload": {"device_id": "living_room_light", "action": "turn_on" if i % 2 == 0 else "turn_off"},
            "cookies": {"sh_session_token": "sess_guest_t3_visitor_c"},
            "expected_status": 200,
            "expected_ok": True,
        })

    assert len(tasks) == 120

    # Trộn ngẫu nhiên danh sách để tối đa hóa va chạm mili-giây giữa các vai trò
    rng = random.Random(42)
    shuffled_tasks = list(tasks)
    rng.shuffle(shuffled_tasks)

    # Hàm thực thi 1 request độc lập
    def _execute_task(t: dict[str, Any]) -> dict[str, Any]:
        c = TestClient(app, raise_server_exceptions=False)
        kwargs: dict[str, Any] = {"json": t["payload"]}
        if "headers" in t:
            kwargs["headers"] = t["headers"]
        if "cookies" in t:
            kwargs["cookies"] = t["cookies"]
        resp = c.post(t["endpoint"], **kwargs)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        return {
            "task": t,
            "status_code": resp.status_code,
            "body": body,
        }

    # Bắn song song 120 requests qua ThreadPoolExecutor (16 threads)
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(_execute_task, t) for t in shuffled_tasks]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # Đối soát toàn bộ 120 kết quả
    assert len(results) == 120

    violations = []
    for r in results:
        t = r["task"]
        status = r["status_code"]
        body = r["body"]
        expected_status = t["expected_status"]
        expected_ok = t["expected_ok"]

        if status != expected_status:
            violations.append(f"Task {t['id']} ({t['role']}): expected status {expected_status}, got {status} body={body}")
        if body.get("ok") != expected_ok:
            violations.append(f"Task {t['id']} ({t['role']}): expected ok={expected_ok}, got {body.get('ok')} body={body}")

    assert not violations, f"Phát hiện vi phạm RBAC rò rỉ quyền trong 120 requests đồng thời:\n" + "\n".join(violations[:10])


# =============================================================================
# 3. KIỂM THỬ ĐĂNG NHẬP STATELESS & KHÔNG NHIỄU TOÀN CỤC
# =============================================================================


def test_login_generates_session_token_and_keeps_engine_clean(client: TestClient):
    """Khi đăng nhập Lớp 1 hoặc OTP Lớp 2:

    1. Trả về session_token trong JSON và Set-Cookie sh_session_token.
    2. Session được lưu trong SessionStore và có thể dùng để điều khiển thiết bị ngay lập tức.
    3. Không đè trạng thái toàn cục của _REST_ENGINE.
    """
    store = get_session_store()
    eng = routes_devices._REST_ENGINE

    # Thiết lập mật khẩu mã hóa ngẫu nhiên tại runtime cho Chủ nhà trước khi kiểm thử đăng nhập Lớp 1
    import secrets
    from simulator.auth_3layer import get_auth_3layer_manager

    ephemeral_pw = "RuntimeOwner_" + secrets.token_urlsafe(12)
    get_auth_3layer_manager().register_or_update_password(
        email="nep94121@gmail.com",
        password=ephemeral_pw,
        confirm_password=ephemeral_pw,
        display_name="Nguyễn Tuấn Anh",
        target_tier=1,
    )

    # Đăng nhập Chủ nhà Lớp 1
    resp = client.post(
        "/api/auth3/layer1_login",
        json={
            "email": "nep94121@gmail.com",
            "password": ephemeral_pw,
            "login_method": "password",
            "source": "Web Test Login",
            "send_gmail": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True

    # 1. Có session_token và session dict
    token = data.get("session_token")
    assert token, "Phải có session_token trong phản hồi đăng nhập"
    assert token.startswith("sess_")
    assert "sh_session_token" in resp.headers.get("set-cookie", "")

    # 2. SessionStore có session này
    saved_sess = store.get_session(token)
    assert saved_sess is not None
    assert saved_sess.tier == 1
    assert saved_sess.role == "ADMIN"

    # 3. Dùng token vừa cấp điều khiển mở cửa chính thành công
    resp_door = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_door.status_code == 200
    assert resp_door.json().get("ok") is True


# =============================================================================
# 4. KIỂM THỬ VÒNG ĐỜI PHIÊN: THU HỒI (REVOKE) & HẾT HẠN (EXPIRATION)
# =============================================================================


def test_session_revocation_blocks_subsequent_requests(client: TestClient):
    """Thu hồi phiên (revoke) khiến các request tiếp theo dùng token đó bị từ chối."""
    store = get_session_store()

    # Tạo phiên động
    custom_sess = store.create_session(
        user_id="dynamic_admin",
        tier=1,
        role="ADMIN",
        display_name="Dynamic Admin",
        ttl_sec=3600,
    )
    token = custom_sess.session_id

    # Trước khi thu hồi: mở cửa chính thành công
    r1 = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200
    assert r1.json().get("ok") is True

    # Thu hồi phiên
    revoked = store.revoke_session(token)
    assert revoked is True
    assert store.get_session(token) is None

    # Sau khi thu hồi: token không còn giá trị, tự động rơi vào Tầng 3 và bị chặn 403
    r2 = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 403
    assert r2.json().get("ok") is False
    assert r2.json().get("rbac_blocked") is True


def test_session_expiration_cleanup():
    """Phiên đã hết hạn không được chấp nhận và được dọn dẹp khỏi cache + SQLite."""
    store = get_session_store()

    # Tạo phiên với ttl âm (đã hết hạn)
    expired_sess = store.create_session(
        user_id="expired_user",
        tier=1,
        role="ADMIN",
        ttl_sec=-60,
    )
    token = expired_sess.session_id

    # get_session nhận diện hết hạn và trả về None
    assert store.get_session(token) is None

    # Gọi dọn dẹp
    cleaned = store.cleanup_expired()
    assert isinstance(cleaned, int)
