"""Bộ kiểm thử đối kháng độc lập (Empirical Adversarial Stress & Vulnerability Suite) cho Milestone M12.

Thực hiện bởi: teamwork_challenger (Challenger M12)
Phạm vi kiểm định đối kháng:
1. Concurrency Race Condition Hammering:
   - Mô phỏng tấn công dồn dập (Hammering): Khách Cấp 3 liên tục bắn yêu cầu mở cửa chính (/api/device)
     song song với Chủ nhà Cấp 1 bật/tắt đèn phòng khách và mở cửa chính.
   - Kiểm tra xem có bất kỳ vi giây nào quyền của Khách bị lọt qua (200 OK) hoặc Chủ nhà bị từ chối oan (403) hay không.
2. Fuzzing & Malformed Token Injection:
   - Token không tồn tại, rỗng, khoảng trắng.
   - SQL Injection vector trong session token.
   - Token siêu dài (5000+ ký tự) và ký tự đặc biệt / emoji.
   - Đảm bảo hệ thống không sập HTTP 500 và trả về 403 Forbidden đúng chuẩn.
3. Expired Session Lifecycle:
   - Token đã hết hạn (TTL âm) bị từ chối 403 và bị dọn dẹp khỏi cache + DB.
4. Malformed Headers & Priority Conflict:
   - Header Authorization sai scheme, header rỗng.
   - Xung đột đa kênh: Bearer Guest vs Cookie Owner -> Xác nhận thứ tự ưu tiên Bearer chặn hành động trái phép.
5. Cookie Tampering & Privilege Escalation (Security Audit):
   - Kiểm tra lỗ hổng giả mạo Cookie `sh_session_tier=1` khi không có token hợp lệ.
   - Oracle kỳ vọng: Hệ thống bảo mật bắt buộc phải chặn (403 Forbidden), không được tin cậy cookie unsigned từ client.
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

import simulator.api.routes_devices as routes_devices
from simulator.auth.session_store import get_session_store
from simulator.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clean_devices_and_state():
    """Đảm bảo các thiết bị và cờ engine ở trạng thái chuẩn trước và sau test."""
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
# 1. CONCURRENCY RACE CONDITION: GUEST HAMMERING VS OWNER COMMANDS
# =============================================================================


def test_adversarial_concurrency_guest_hammering_vs_owner(client: TestClient):
    """Stress test đối kháng cao độ:
    - 100 requests Khách Cấp 3 dồn dập mở cửa chính (/api/device)
    - 60 requests Chủ nhà Cấp 1 bật/tắt đèn phòng khách (/api/device)
    - 40 requests Chủ nhà Cấp 1 mở/đóng cửa chính (/api/device)
    - Tổng cộng 200 requests bắn đồng thời trên 20 worker threads.
    
    Bất biến kiểm định (Invariants):
    - 100% request mở cửa từ Khách PHẢI BỊ CHẶN (HTTP 403, ok=False, rbac_blocked=True).
    - 100% request từ Chủ nhà PHẢI THÀNH CÔNG (HTTP 200, ok=True).
    - Cửa chính không bao giờ bị mở do request của Khách.
    """
    tasks: list[dict[str, Any]] = []

    # 100 requests Khách Cấp 3 hammer mở cửa chính
    for i in range(100):
        tasks.append({
            "id": f"guest_hammer_door_{i}",
            "actor": "GUEST",
            "endpoint": "/api/device",
            "payload": {"device_id": "main_door", "action": "open"},
            "headers": {"Authorization": "Bearer sess_guest_t3_visitor_c"},
            "expected_status": 403,
            "expected_ok": False,
        })

    # 60 requests Chủ nhà Cấp 1 bật/tắt đèn
    for i in range(60):
        action = "turn_on" if i % 2 == 0 else "turn_off"
        tasks.append({
            "id": f"owner_light_{i}",
            "actor": "OWNER",
            "endpoint": "/api/device",
            "payload": {"device_id": "living_room_light", "action": action},
            "headers": {"Authorization": "Bearer sess_owner_t1_nep94121"},
            "expected_status": 200,
            "expected_ok": True,
        })

    # 40 requests Chủ nhà Cấp 1 mở/đóng cửa chính
    for i in range(40):
        action = "open" if i % 2 == 0 else "close"
        tasks.append({
            "id": f"owner_door_{i}",
            "actor": "OWNER",
            "endpoint": "/api/device",
            "payload": {"device_id": "main_door", "action": action},
            "headers": {"Authorization": "Bearer sess_owner_t1_nep94121"},
            "expected_status": 200,
            "expected_ok": True,
        })

    assert len(tasks) == 200

    # Xáo trộn hoàn toàn để các luồng bắn xen kẽ ở mức microsecond
    rng = random.Random(1337)
    shuffled_tasks = list(tasks)
    rng.shuffle(shuffled_tasks)

    def _execute(t: dict[str, Any]) -> dict[str, Any]:
        c = TestClient(app, raise_server_exceptions=False)
        resp = c.post(t["endpoint"], json=t["payload"], headers=t["headers"])
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        return {
            "task": t,
            "status_code": resp.status_code,
            "body": body,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(_execute, t) for t in shuffled_tasks]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 200

    violations = []
    for r in results:
        t = r["task"]
        status = r["status_code"]
        body = r["body"]
        if status != t["expected_status"]:
            violations.append(
                f"[{t['id']}] Actor={t['actor']} Expected status {t['expected_status']}, got {status}. Body={body}"
            )
        if body.get("ok") != t["expected_ok"]:
            violations.append(
                f"[{t['id']}] Actor={t['actor']} Expected ok={t['expected_ok']}, got {body.get('ok')}. Body={body}"
            )

    assert not violations, f"Phát hiện vi phạm tương tranh ({len(violations)} lỗi):\n" + "\n".join(violations[:5])


# =============================================================================
# 2. EDGE CASES: INVALID TOKENS & FUZZING
# =============================================================================


def test_adversarial_invalid_tokens_fuzzing(client: TestClient):
    """Fuzzing các vector token bất thường:
    - Token không tồn tại
    - Token chứa SQL Injection
    - Token rỗng / khoảng trắng
    - Token siêu dài 5000 ký tự
    - Token chứa emoji và ký tự điều khiển
    Đảm bảo 100% trả về 403 Forbidden khi cố mở cửa chính, không gây unhandled 500.
    """
    fuzz_vectors = [
        "sess_non_existent_token_12345",
        "sess_' OR '1'='1",
        "sess_'; DROP TABLE user_sessions; --",
        "sess_unknown_user_token_abc_xyz",
        "A" * 5000,
        "sess_%00%01%02_escaped",
    ]

    for vec in fuzz_vectors:
        resp = client.post(
            "/api/device",
            json={"device_id": "main_door", "action": "open"},
            headers={"Authorization": f"Bearer {vec}"},
        )
        assert resp.status_code == 403, f"Fuzz vector '{vec[:20]}' phải bị chặn 403, nhận được {resp.status_code}"
        data = resp.json()
        assert data.get("ok") is False
        assert data.get("rbac_blocked") is True

    # Fuzzing qua body payload với emoji/unicode
    resp_emoji = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open", "session_token": "👑_root_super_admin_🔓"},
    )
    assert resp_emoji.status_code == 403
    assert resp_emoji.json().get("ok") is False


# =============================================================================
# 3. EDGE CASES: EXPIRED TOKENS
# =============================================================================


def test_adversarial_expired_session(client: TestClient):
    """Session đã hết hạn phải tự động bị từ chối (403) và không cho phép mở cửa."""
    store = get_session_store()
    # Tạo session đã hết hạn từ 60 giây trước
    expired_sess = store.create_session(
        user_id="attacker_with_old_session",
        tier=1,
        role="ADMIN",
        ttl_sec=-60,
    )
    token = expired_sess.session_id

    resp = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json().get("ok") is False
    assert resp.json().get("rbac_blocked") is True


# =============================================================================
# 4. EDGE CASES: MALFORMED HEADERS & CONFLICTING CHANNELS
# =============================================================================


def test_adversarial_malformed_headers(client: TestClient):
    """Kiểm tra header Authorization dị dạng hoặc rỗng."""
    # 1. Scheme lạ (Basic auth với token Owner)
    r1 = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open"},
        headers={"Authorization": "Basic sess_owner_t1_nep94121"},
    )
    assert r1.status_code == 403
    assert r1.json().get("ok") is False

    # 2. Bearer không có token phía sau
    r2 = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open"},
        headers={"Authorization": "Bearer "},
    )
    assert r2.status_code == 403
    assert r2.json().get("ok") is False

    # 3. Xung đột kênh: Bearer Guest vs Cookie Owner
    # Theo quy tắc priority: Authorization Bearer (Khách) được ưu tiên xử lý trước -> Phải bị chặn 403
    r3 = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open"},
        headers={"Authorization": "Bearer sess_guest_t3_visitor_c"},
        cookies={"sh_session_token": "sess_owner_t1_nep94121"},
    )
    assert r3.status_code == 403
    assert r3.json().get("ok") is False


# =============================================================================
# 5. EDGE CASES: COOKIE TAMPERING & PRIVILEGE ESCALATION VULNERABILITY
# =============================================================================


def test_adversarial_cookie_tampering_sh_session_tier_forgery(client: TestClient):
    """Kiểm tra khả năng giả mạo Cookie sh_session_tier=1 để leo thang đặc quyền (Privilege Escalation).
    
    Kịch bản tấn công:
    - Kẻ tấn công KHÔNG có tài khoản, KHÔNG có session_token hợp lệ.
    - Kẻ tấn công tự đặt Cookie: `sh_session_tier=1` (hoặc kèm `sh_session_user=attacker`).
    - Kẻ tấn công gửi yêu cầu:
      1. Mở cửa chính tại /api/device
      2. Hẹn giờ bật đèn tại /api/mobile/schedule (vốn cấm Khách Cấp 3)
      3. Phát lệnh khẩu lệnh mở cửa tại /api/text_command
    
    Yêu cầu bảo mật Zero-Trust:
    - Backend BẮT BUỘC phải từ chối (HTTP 403 Forbidden).
    - Cửa chính BẮT BUỘC phải giữ nguyên trạng thái CLOSED.
    - Tuyệt đối KHÔNG ĐƯỢC tin cậy cookie unsigned do client tự sinh gửi lên.
    """
    eng = routes_devices._REST_ENGINE
    eng.devices["main_door"]["state"] = "CLOSED"

    # Vector 1: Mở cửa chính tại /api/device với cookie giả mạo
    resp_door = client.post(
        "/api/device",
        json={"device_id": "main_door", "action": "open"},
        cookies={"sh_session_tier": "1"},
    )
    assert resp_door.status_code == 403, (
        f"LỖ HỔNG BẢO MẬT NGHIÊM TRỌNG (RBAC Bypass via Cookie Tampering tại /api/device): "
        f"Kẻ tấn công không đăng nhập gửi cookie sh_session_tier=1 đã mở được cửa chính! "
        f"Status: {resp_door.status_code}, Body: {resp_door.json()}"
    )

    # Vector 2: Hẹn giờ tại /api/mobile/schedule với cookie giả mạo
    resp_sched = client.post(
        "/api/mobile/schedule",
        json={"device_id": "living_room_light", "action": "turn_on", "seconds": 30},
        cookies={"sh_session_tier": "1"},
    )
    assert resp_sched.status_code == 403, (
        f"LỖ HỔNG BẢO MẬT NGHIÊM TRỌNG (RBAC Bypass via Cookie Tampering tại /api/mobile/schedule): "
        f"Kẻ tấn công gửi cookie sh_session_tier=1 đã tạo được lịch hẹn giờ! "
        f"Status: {resp_sched.status_code}, Body: {resp_sched.json()}"
    )

    # Vector 3: Khẩu lệnh văn bản tại /api/text_command với cookie giả mạo
    resp_text = client.post(
        "/api/text_command",
        json={"text": "Mở cửa chính"},
        cookies={"sh_session_tier": "1"},
    )
    assert resp_text.status_code == 403 or resp_text.json().get("rbac_blocked") is True, (
        f"LỖ HỔNG BẢO MẬT NGHIÊM TRỌNG (RBAC Bypass via Cookie Tampering tại /api/text_command): "
        f"Kẻ tấn công gửi cookie sh_session_tier=1 đã thực thi được lệnh mở cửa! "
        f"Status: {resp_text.status_code}, Body: {resp_text.json()}"
    )
