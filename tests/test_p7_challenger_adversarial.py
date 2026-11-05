"""Bộ Thử Thách Thực Nghiệm Độc Lập (Phase 7 Challenger 1 Adversarial Test Suite).

Kiểm chứng thực nghiệm các khía cạnh an ninh Backend theo chỉ thị:
1. Thử thách tấn công vượt rào bảo mật 401 trên Backend:
   - Gửi các request giả mạo, không có token, token rác, token hết hạn, session giả tới:
     POST /api/device, POST /api/device_control, POST /api/devices/{id}/control,
     POST /api/mobile/schedule, POST /api/ir_learn, POST /api/text_command,
     GET /api/auth3/guest_qr_current.
   - Xác minh máy chủ từ chối với HTTP 401 Unauthorized, không một thiết bị nào bị bật/tắt trái phép.
2. Thử thách leo quyền Guest Voice Enrollment:
   - Cố tình gửi target_tier = 1 hoặc 2, role = "OWNER" tới /api/auth3/guest_qr_complete_voice.
   - Xác minh máy chủ kiên quyết ép về Cấp 3 (CHILD_GUEST).
3. Xác minh key trùng lặp remaining_Slot_sec đã biến mất hoàn toàn trong phản hồi JSON.
4. Kiểm thử áp lực đồng thời (Concurrency & Stress Test).
"""

from __future__ import annotations

import base64
import concurrent.futures
import copy
import io
import json
import pathlib
import sys
import time
from typing import Any

from fastapi.testclient import TestClient
import numpy as np
import pytest
import soundfile as sf

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.auth.session_store import get_session_store
from simulator.auth_3layer import get_auth_3layer_manager
from simulator.server import _ACTIVE_BRIDGES, _BOOT_VOICE_AUTH, _REST_ENGINE, app


@pytest.fixture(autouse=True)
def setup_and_teardown_adversarial():
    """Đảm bảo môi trường sạch trước và sau mỗi bài test adversarial."""
    _ACTIVE_BRIDGES.clear()
    _REST_ENGINE._explicit_test_user_set = False
    _REST_ENGINE._current_role = "ADMIN"
    _REST_ENGINE._current_user_id = "tuan_anh"
    _REST_ENGINE._current_tier = 1
    mgr = get_auth_3layer_manager()
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()

    # Dọn dẹp session tạm nếu có
    store = get_session_store()
    for sid in ["sess_challenger_expired", "sess_fake_hacker_session_12345"]:
        store.revoke_session(sid)

    yield

    _ACTIVE_BRIDGES.clear()
    _REST_ENGINE._explicit_test_user_set = False
    _REST_ENGINE._current_role = "ADMIN"
    _REST_ENGINE._current_user_id = "tuan_anh"
    _REST_ENGINE._current_tier = 1
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    mgr.accounts = [
        acc for acc in mgr.accounts
        if not str(acc.get("email", "")).endswith(".challenger@gmail.com")
    ]
    mgr._save_accounts()
    for sid in ["sess_challenger_expired", "sess_fake_hacker_session_12345"]:
        store.revoke_session(sid)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _generate_valid_test_pcm_b64(f0_hz: float = 230.0, duration_sec: float = 2.5) -> str:
    """Sinh âm thanh PCM 16kHz chuẩn F0 để test voice enrollment."""
    sr = 16000
    n_silence = int(sr * 0.3)
    n_voice = int(sr * (duration_sec - 0.3))
    silence = np.zeros(n_silence, dtype=np.float32)
    t = np.linspace(0, duration_sec - 0.3, n_voice, endpoint=False)
    voice = (
        0.45 * np.sin(2 * np.pi * f0_hz * t)
        + 0.20 * np.sin(2 * np.pi * (f0_hz * 2) * t)
        + 0.10 * np.sin(2 * np.pi * (f0_hz * 3) * t)
    )
    sig = np.concatenate([silence, voice])
    pcm16 = (sig * 32767).astype(np.int16)
    return base64.b64encode(pcm16.tobytes()).decode("utf-8")


# ==============================================================================
# PHẦN 1: MA TRẬN TẤN CÔNG 401 UNAUTHORIZED TRÊN TẤT CẢ 7 ENDPOINTS
# ==============================================================================

def test_adv_unauthenticated_request_matrix(client: TestClient) -> None:
    """Thử nghiệm ma trận tấn công toàn diện với 8 vector giả mạo token trên 7 endpoints."""
    store = get_session_store()
    # Tạo một session hết hạn chủ động
    store.create_session(
        user_id="victim_user",
        tier=1,
        role="ADMIN",
        session_id="sess_challenger_expired",
        ttl_sec=-3600,  # đã hết hạn 1 giờ trước
        source="test_expired",
    )

    attack_vectors = [
        ("NO_AUTH", {}, {}),
        ("GARBAGE_BEARER", {"Authorization": "Bearer garbage_fake_token_xyz999"}, {}),
        ("EMPTY_BEARER", {"Authorization": "Bearer "}, {}),
        ("WRONG_SCHEME", {"Authorization": "Basic YWRtaW46cGFzc3dvcmQ="}, {}),
        ("EXPIRED_TOKEN", {"Authorization": "Bearer sess_challenger_expired"}, {}),
        ("FORGED_HEADER_TOKEN", {"X-Session-Token": "sess_fake_hacker_session_12345"}, {}),
        ("SQLI_TOKEN", {"Authorization": "Bearer ' OR 1=1 --"}, {}),
        ("TRAVERSAL_TOKEN", {"Authorization": "Bearer ../../../etc/passwd"}, {}),
    ]

    endpoints_to_test = [
        ("POST", "/api/device", {"device_id": "living_room_light", "action": "turn_on"}),
        ("POST", "/api/device_control", {"device_id": "bedroom_light", "action": "turn_on"}),
        ("POST", "/api/devices/fan/control", {"action": "turn_on"}),
        ("POST", "/api/devices/living_room_light/control", {"action": "turn_off"}),
        ("POST", "/api/mobile/schedule", {"device_id": "living_room_light", "seconds": 30, "action": "turn_on"}),
        ("POST", "/api/ir_learn", {"device_name": "Điều hòa", "command_action": "open"}),
        ("POST", "/api/text_command", {"text": "bật đèn phòng khách"}),
        ("POST", "/api/text_command", {"text": "bật máy bơm"}),
        ("POST", "/api/text_command", {"text": "tắt máy bơm"}),
        ("POST", "/api/text_command", {"text": "hẹn 10 giây nữa bật đèn"}),
        ("GET", "/api/auth3/guest_qr_current?duration=1d", None),
    ]

    for v_name, headers, cookies in attack_vectors:
        for method, url, payload in endpoints_to_test:
            if method == "POST":
                resp = client.post(url, json=payload, headers=headers, cookies=cookies)
            else:
                resp = client.get(url, headers=headers, cookies=cookies)

            assert resp.status_code == 401, (
                f"LỖ HỔNG BẢO MẬT: Endpoint {method} {url} không chặn HTTP 401! "
                f"Vector: {v_name}, Nhận status: {resp.status_code}, Body: {resp.text}"
            )
            body = resp.json()
            assert body.get("ok") is False, f"Response ok flag is not False for {url}"


def test_adv_cookie_query_payload_forged_tokens_return_401(client: TestClient) -> None:
    """Xác minh token giả truyền qua Cookie, Query Param hoặc Body Payload đều bị 401."""
    # 1. Giả mạo qua Cookie
    r_cookie = client.post("/api/device", json={"device_id": "fan", "action": "turn_on"}, cookies={"sh_session_token": "fake_cookie_token"})
    assert r_cookie.status_code == 401

    r_cookie_qr = client.get("/api/auth3/guest_qr_current", cookies={"session_token": "fake_cookie_token"})
    assert r_cookie_qr.status_code == 401

    # 2. Giả mạo qua Query Param
    r_query = client.get("/api/auth3/guest_qr_current?token=fake_query_token&duration=1d")
    assert r_query.status_code == 401

    # 3. Giả mạo qua Body Payload session_token
    r_body = client.post("/api/device", json={"device_id": "fan", "action": "turn_on", "session_token": "fake_body_token"})
    assert r_body.status_code == 401


# ==============================================================================
# PHẦN 2: TÍNH TOÀN VẸN CỦA THIẾT BỊ (ZERO UNAUTHORIZED MUTATION)
# ==============================================================================

def test_adv_device_state_inviolability_under_brute_force(client: TestClient) -> None:
    """Bảo đảm sau loạt request tấn công, KHÔNG CÓ BẤT KỲ thiết bị nào bị thay đổi trạng thái."""
    # Ghi nhận trạng thái gốc ban đầu của toàn bộ thiết bị trong nhà
    initial_devices = {d["id"]: d["state"] for d in _REST_ENGINE.get_snapshot()["devices"]}

    # Phát các đợt tấn công giả mạo liên tục vào tất cả 7 thiết bị thực tế trong nhà
    real_targets = [
        ("main_door", "open", "mở cửa chính"),
        ("main_door", "close", "đóng cửa chính"),
        ("living_room_light", "turn_on", "bật đèn phòng khách"),
        ("living_room_light", "turn_off", "tắt đèn phòng khách"),
        ("bedroom_light", "turn_on", "bật đèn phòng ngủ"),
        ("bedroom_light", "turn_off", "tắt đèn phòng ngủ"),
        ("fan", "turn_on", "bật quạt"),
        ("fan", "turn_off", "tắt quạt"),
        ("ac", "turn_on", "bật điều hòa"),
        ("ac", "turn_off", "tắt điều hòa"),
        ("alarm_siren", "turn_on", "bật còi báo động"),
        ("alarm_siren", "turn_off", "tắt còi báo động"),
        ("garden_pump", "turn_on", "bật máy bơm"),
        ("garden_pump", "turn_off", "tắt máy bơm"),
        ("all_devices", "turn_on", "bật tất cả thiết bị"),
        ("all_lights", "turn_off", "tắt tất cả đèn"),
    ]

    for dev_id, act, text_cmd in real_targets:
        # Thử qua POST /api/device
        res1 = client.post("/api/device", json={"device_id": dev_id, "action": act})
        assert res1.status_code == 401

        # Thử qua POST /api/devices/{id}/control
        res2 = client.post(f"/api/devices/{dev_id}/control", json={"action": act})
        assert res2.status_code == 401

        # Thử qua POST /api/text_command
        res3 = client.post("/api/text_command", json={"text": text_cmd})
        assert res3.status_code == 401, f"Lệnh '{text_cmd}' không trả về 401! Nhận status: {res3.status_code}"

    # Kiểm tra lại trạng thái sau đợt tấn công
    current_devices = {d["id"]: d["state"] for d in _REST_ENGINE.get_snapshot()["devices"]}
    for dev_id, initial_state in initial_devices.items():
        assert current_devices[dev_id] == initial_state, (
            f"NGHIÊM TRỌNG: Thiết bị '{dev_id}' đã bị thay đổi trạng thái từ "
            f"'{initial_state}' sang '{current_devices[dev_id]}' sau đợt tấn công!"
        )


# ==============================================================================
# PHẦN 3: THỬ THÁCH CHỐNG LEO QUYỀN GUEST VOICE ENROLLMENT
# ==============================================================================

def test_adv_guest_voice_enrollment_privilege_escalation_denied(client: TestClient) -> None:
    """Cố tình truyền target_tier = 1, 2, 0, -1, role = 'OWNER', 'ADMIN' -> Máy chủ ép về Cấp 3."""
    pcm_b64 = _generate_valid_test_pcm_b64(f0_hz=220.0)

    escalation_payloads = [
        {"target_tier": 1, "role": "OWNER", "guest_name": "Attacker 1", "email": "att1.challenger@gmail.com"},
        {"target_tier": 2, "role": "ADMIN", "guest_name": "Attacker 2", "email": "att2.challenger@gmail.com"},
        {"target_tier": 0, "role": "ROOT", "guest_name": "Attacker 0", "email": "att0.challenger@gmail.com"},
        {"target_tier": -1, "role": "SUPERUSER", "guest_name": "Attacker Neg", "email": "attneg.challenger@gmail.com"},
        {"tier": 1, "role_code": "OWNER", "guest_name": "Attacker Tier1", "email": "attt1.challenger@gmail.com"},
    ]

    for p in escalation_payloads:
        p["audio_pcm_b64"] = pcm_b64
        p["duration"] = "1d"
        p["verify_only"] = False

        res = client.post("/api/auth3/guest_qr_complete_voice", json=p)
        assert res.status_code == 200, f"Enrollment failed: {res.text}"
        data = res.json()

        # Kiểm tra phản hồi bắt buộc phải là Cấp 3
        assert data.get("tier") == 3, f"Bị leo quyền: phản hồi trả về tier={data.get('tier')}"
        if "account" in data and data["account"]:
            assert data["account"]["tier"] == 3, f"Account tier bị leo quyền: {data['account']['tier']}"
            assert data["account"]["role"] == "CHILD_GUEST", f"Account role bị leo quyền: {data['account']['role']}"

        # Kiểm tra trực tiếp trong danh sách accounts lưu trữ
        mgr = get_auth_3layer_manager()
        stored_acc = next((a for a in mgr.accounts if a.get("email") == p["email"]), None)
        assert stored_acc is not None, f"Không tìm thấy tài khoản {p['email']} được lưu"
        assert stored_acc["tier"] == 3, f"Tài khoản trong DB có tier={stored_acc['tier']} (kỳ vọng 3)"
        assert stored_acc["role"] == "CHILD_GUEST", f"Tài khoản trong DB có role={stored_acc['role']} (kỳ vọng CHILD_GUEST)"

        # Reset voice auth để test payload kế tiếp không bị trùng F0
        _BOOT_VOICE_AUTH.reset_to_owner_only()


def test_adv_guest_voice_owner_email_spoofing_forbidden(client: TestClient) -> None:
    """Cố tình giả mạo email Chủ nhà nep94121@gmail.com trên trang khách -> Phải trả về 400."""
    pcm_b64 = _generate_valid_test_pcm_b64(f0_hz=210.0)
    payload = {
        "guest_name": "Hacker Giả Danh Chủ Nhà",
        "email": "nep94121@gmail.com",
        "target_tier": 1,
        "audio_pcm_b64": pcm_b64,
        "duration": "1d",
    }
    res = client.post("/api/auth3/guest_qr_complete_voice", json=payload)
    assert res.status_code == 400
    data = res.json()
    assert data.get("ok") is False
    assert data.get("status") == "OWNER_EMAIL_FORBIDDEN"


# ==============================================================================
# PHẦN 4: XÁC MINH TRIỆT ĐỂ KEY DUPLICATE REMAINING_SLOT_SEC
# ==============================================================================

def test_adv_remaining_slot_sec_key_sanitization(client: TestClient) -> None:
    """Kiểm tra phản hồi của GET /api/auth3/guest_qr_current KHÔNG BAO GIỜ chứa remaining_Slot_sec."""
    headers = {"Authorization": "Bearer sess_owner_t1_nep94121"}

    test_queries = [
        "duration=1h",
        "duration=1d",
        "duration=3d",
        "duration=7d",
        "duration=30d",
        "dur=1d",
        "duration_type=7d",
        "tier=2",
        "tier=3",
        "duration=invalid_foo_bar",
        "host=localhost:8088",
        "host=127.0.0.1:8088",
        "host=guest-bay.vercel.app",
    ]

    for q in test_queries:
        res = client.get(f"/api/auth3/guest_qr_current?{q}", headers=headers)
        assert res.status_code == 200, f"Query {q} failed with {res.status_code}"
        data = res.json()

        # 1. Có key chuẩn snake_case
        assert "remaining_slot_sec" in data, f"Thiếu key remaining_slot_sec trong query {q}"
        assert isinstance(data["remaining_slot_sec"], int)
        assert 1 <= data["remaining_slot_sec"] <= 10

        # 2. Tuyệt đối KHÔNG có key lỗi lạc remaining_Slot_sec
        assert "remaining_Slot_sec" not in data, f"Key trùng lặp remaining_Slot_sec vẫn còn xuất hiện trong query {q}!"

        # 3. Quét đệ quy toàn bộ JSON để chắc chắn không nằm trong object con nào
        def _check_no_corrupted_key(obj: Any):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    assert k != "remaining_Slot_sec", f"Tìm thấy remaining_Slot_sec trong key: {k}"
                    _check_no_corrupted_key(v)
            elif isinstance(obj, list):
                for item in obj:
                    _check_no_corrupted_key(item)

        _check_no_corrupted_key(data)


# ==============================================================================
# PHẦN 5: KIỂM THỬ ÁP LỰC ĐỒNG THỜI (CONCURRENCY RESILIENCE)
# ==============================================================================

def test_adv_concurrent_attack_resilience(client: TestClient) -> None:
    """Bắn 40 request giả mạo đồng thời qua đa luồng, máy chủ phải kiên quyết trả về 401."""
    def _attack_task(idx: int) -> int:
        headers = {"Authorization": f"Bearer fake_concurrent_token_{idx}"}
        endpoint = "/api/device" if idx % 2 == 0 else "/api/auth3/guest_qr_current"
        if idx % 2 == 0:
            res = client.post(endpoint, json={"device_id": "living_room_light", "action": "turn_on"}, headers=headers)
        else:
            res = client.get(endpoint, headers=headers)
        return res.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_attack_task, i) for i in range(40)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 40
    assert all(code == 401 for code in results), f"Có request không trả về 401: {set(results)}"
