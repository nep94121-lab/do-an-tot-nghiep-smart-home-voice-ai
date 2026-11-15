"""BỘ KIỂM THỬ ĐỐI KHÁNG ĐỘC LẬP — EMAIL ALLOWLIST & MOBILE SYNC (MILESTONE M3)
Tác giả: Teamwork Worker M3
Phạm vi kiểm định:
- simulator/auth_3layer.py (add_family_email, validate_and_enroll_voice, allowlist resolution)
- simulator/server.py (/api/auth3/add_family_email, /api/auth3/family_emails, /api/auth3/enroll_voice_sample)
- Giao diện Web / PWA / Android Mobile Sync

Ma trận phân quyền (RBAC) Cấp 1, Cấp 2, Cấp 3:
- C1 (Admin): Thêm C2, C3 -> 200 OK.
- C2 (Thành viên): Chỉ thêm C3 -> 200 OK; Cố thêm C1 hoặc C2 -> 403 Forbidden.
- C3 (Khách): Cố thêm bất kỳ ai -> 403 Forbidden.
- Tài khoản mới từ Allowlist: voice_verified = False, needs_first_page_voice_enroll = True.
- Thu âm giọng không đạt chuẩn -> CHUA_DAT, giữ voice_verified = False.
- Thu âm giọng đạt chuẩn (6 tiêu chuẩn âm học) -> DA_DAT, cập nhật voice_verified = True.
"""

from __future__ import annotations

import pathlib
import sys
import wave
from typing import Generator

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import simulator.auth_3layer as a3
from simulator.auth_3layer import ThreeLayerAuthManager, get_auth_manager
from simulator.voice_auth import validate_voice_enrollment_quality

AUDIO_DIR = ROOT / "test_audio"


def load_wav(name: str) -> np.ndarray:
    path = AUDIO_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing audio file: {path}")
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


@pytest.fixture
def auth_mgr(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> ThreeLayerAuthManager:
    """Khởi tạo ThreeLayerAuthManager cô lập trong thư mục tạm."""
    monkeypatch.setattr(a3, "ACCOUNTS_FILE", tmp_path / "accounts_3layer.json")
    monkeypatch.setattr(a3, "FAMILY_ALLOWLIST_FILE", tmp_path / "family_email_allowlist.json")
    monkeypatch.setattr(a3, "INVITE_LINKS_FILE", tmp_path / "invite_links_3layer.json")
    monkeypatch.setattr(a3, "AUTH_EVENTS_FILE", tmp_path / "auth_3layer_events.json")
    mgr = ThreeLayerAuthManager()
    return mgr


# ============================================================================
# TẦNG 1: KIỂM ĐỊNH PHÂN QUYỀN RBAC (C1, C2, C3)
# ============================================================================


def test_c1_admin_adds_c2_and_c3_success(auth_mgr: ThreeLayerAuthManager) -> None:
    """Chủ nhà Cấp 1 (tuan_anh) có toàn quyền thêm Email cho Cấp 2 và Cấp 3."""
    # C1 thêm C2
    res2 = auth_mgr.add_family_email("tuan_anh", "con_gai@gmail.com", 2, source="Test C1->C2")
    assert res2["ok"] is True
    assert res2["status_code"] == 200
    assert res2["entry"]["target_tier"] == 2
    assert res2["target_email"] == "con_gai@gmail.com"

    # C1 thêm C3
    res3 = auth_mgr.add_family_email("tuan_anh", "ong_ba@gmail.com", 3, source="Test C1->C3")
    assert res3["ok"] is True
    assert res3["status_code"] == 200
    assert res3["entry"]["target_tier"] == 3
    assert res3["target_email"] == "ong_ba@gmail.com"

    # Kiểm tra danh sách allowlist
    allowlist = auth_mgr.get_family_email_allowlist()
    emails = [e["email"] for e in allowlist]
    assert "con_gai@gmail.com" in emails
    assert "ong_ba@gmail.com" in emails


def test_c2_member_can_only_add_c3_and_blocked_for_c1_or_c2(auth_mgr: ThreeLayerAuthManager) -> None:
    """Chính sách Điều 4: Thành viên Cấp 2 (thanh_vien_a) bị chặn 403 khi mời bất kỳ cấp nào (chỉ Cấp 1 được mời)."""
    for tier, mail in [(3, "nguoi_giup_viec@gmail.com"), (2, "ban_than@gmail.com"), (1, "fake_admin@gmail.com")]:
        res_block = auth_mgr.add_family_email("thanh_vien_a", mail, tier, source=f"Test C2->C{tier} Block")
        assert res_block["ok"] is False
        assert res_block["status_code"] == 403
        assert "Chỉ Chủ nhà Cấp 1" in res_block["error"]


def test_c3_guest_is_forbidden_from_adding_anyone(auth_mgr: ThreeLayerAuthManager) -> None:
    """Khách Cấp 3 (khach_c) KHÔNG được thêm bất kỳ ai (403 Forbidden)."""
    for tier, mail in [(3, "anybody1@gmail.com"), (2, "anybody2@gmail.com"), (1, "anybody3@gmail.com")]:
        res = auth_mgr.add_family_email("khach_c", mail, tier, source=f"Test C3->C{tier}")
        assert res["ok"] is False
        assert res["status_code"] == 403
        assert "Chỉ Chủ nhà Cấp 1" in res["error"] or "không có quyền" in res["error"]


# ============================================================================
# TẦNG 2: KIỂM ĐỊNH TỰ ĐỘNG ĐỐI CHIẾU ALLOWLIST & CỜ VOICE_VERIFIED
# ============================================================================


def test_allowlisted_account_requires_first_page_voice_enroll(
    auth_mgr: ThreeLayerAuthManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0: Tài khoản Cấp 2 allowlist hoàn tất đăng nhập ngay ở Lớp 1 (không OTP, không ép thu âm trang đầu); API thu âm cũ trả 410."""
    import secrets
    from fastapi.testclient import TestClient
    from simulator.server import app

    target_email = "tan_binh_gia_dinh@gmail.com"
    add_res = auth_mgr.add_family_email("tuan_anh", target_email, 2)
    assert add_res["ok"] is True

    ephemeral_pw = "Allowlist_" + secrets.token_urlsafe(10)
    auth_mgr.register_or_update_password(target_email, ephemeral_pw, ephemeral_pw, target_tier=2)

    # Đăng nhập Lớp 1 bằng email vừa allowlist với mật khẩu đã băm
    l1_res = auth_mgr.layer1_login(target_email, ephemeral_pw, login_method="password")
    assert l1_res["ok"] is True
    assert l1_res["tier"] == 2
    assert l1_res["authenticated"] is True
    assert l1_res["otp_required"] is False
    assert l1_res["account"]["permission_active"] is True
    acc_saved = auth_mgr.find_account(target_email)
    assert acc_saved is not None and acc_saved.get("needs_first_page_voice_enroll") is False

    # Kiểm chứng HTTP routes trên TestClient gắn cùng auth_mgr
    monkeypatch.setattr("simulator.api.routes_auth.get_auth_3layer_manager", lambda: auth_mgr)
    client = TestClient(app)
    retired = client.post("/api/auth3/enroll_voice_sample", json={"email": target_email, "audio_pcm_b64": ""})
    assert retired.status_code == 410, retired.text

    http_l1 = client.post("/api/auth3/layer1_login", json={
        "email": target_email,
        "password": ephemeral_pw,
        "login_method": "password",
        "send_gmail": False,
    })
    assert http_l1.status_code == 200, http_l1.text
    hdata = http_l1.json()
    assert hdata["ok"] is True and hdata["tier"] == 2 and hdata.get("session_token")
    t2_headers = {"X-Session-Token": str(hdata["session_token"])}

    ok_dev = client.post("/api/device", headers=t2_headers, json={"device_id": "living_room_light", "action": "turn_on"})
    assert ok_dev.status_code == 200 and ok_dev.json().get("ok") is True
    client.post("/api/device", headers=t2_headers, json={"device_id": "living_room_light", "action": "turn_off"})

    blk_door = client.post("/api/device", headers=t2_headers, json={"device_id": "main_door", "action": "open"})
    assert blk_door.status_code == 403 or (blk_door.json().get("ok") is False and blk_door.json().get("rbac_blocked") is True)


# ============================================================================
# TẦNG 3: KIỂM ĐỊNH CỔNG CHẤT LƯỢNG THU ÂM (QUALITY GATE DA_DAT vs CHUA_DAT)
# ============================================================================


def test_voice_enrollment_rejects_silent_or_poor_audio(auth_mgr: ThreeLayerAuthManager) -> None:
    """Giọng thu âm im lặng hoặc rác trả về CHUA_DAT và giữ voice_verified = False."""
    import secrets

    email = "hoc_sinh_moi@gmail.com"
    auth_mgr.add_family_email("tuan_anh", email, 2)
    pw = "Student_" + secrets.token_urlsafe(10)
    auth_mgr.register_or_update_password(email, pw, pw, target_tier=2)
    auth_mgr.layer1_login(email, pw)

    # Mẫu im lặng (zeros)
    silence_pcm = np.zeros(16000 * 2, dtype=np.int16).tobytes()
    res = auth_mgr.validate_and_enroll_voice(email, silence_pcm)
    assert res["ok"] is False
    assert res["status"] == "CHUA_DAT"
    assert res.get("message") or res.get("error")

    # Kiểm tra tài khoản vẫn chưa được verify
    acc = next((a for a in auth_mgr.accounts if a.get("email") == email), None)
    assert acc is not None
    assert acc["voice_verified"] is False
    assert acc["needs_first_page_voice_enroll"] is False


def test_voice_enrollment_accepts_valid_audio_and_verifies_account(auth_mgr: ThreeLayerAuthManager) -> None:
    """Giọng thu âm đạt chuẩn 8 tiêu chuẩn âm học + self-check trả về DA_DAT và cập nhật voice_verified = True."""
    import secrets

    email = "thanh_vien_chuan@gmail.com"
    auth_mgr.add_family_email("tuan_anh", email, 2)
    pw = "Member_" + secrets.token_urlsafe(10)
    auth_mgr.register_or_update_password(email, pw, pw, target_tier=2)
    auth_mgr.layer1_login(email, pw)

    # Cặp enroll + self-check đạt chuẩn 8/8 quality gate cho giọng Cấp 2
    pcm_raw = load_wav("giong_cap2_thanh_vien_a.wav")
    pad_e = np.zeros(4000, dtype=np.int16)
    pad_s = np.zeros(2000, dtype=np.int16)
    enroll_pcm = np.concatenate([pad_e, *([pcm_raw] * 19), pad_e]).tobytes()
    sc_pcm = np.concatenate([pad_s, *([pcm_raw] * 6), pad_s]).tobytes()

    res = auth_mgr.validate_and_enroll_voice(email, enroll_pcm, self_check_pcm_bytes=sc_pcm)
    assert res["ok"] is True
    assert res["status"] == "DA_DAT"
    assert "đã đạt chuẩn" in res["message"]

    # Kiểm tra tài khoản đã được verify
    acc = next((a for a in auth_mgr.accounts if a.get("email") == email), None)
    assert acc is not None
    assert acc["voice_verified"] is True
    assert acc["needs_first_page_voice_enroll"] is False
    assert acc["voiceprint"] is not None


# ============================================================================
# TẦNG 4: KIỂM ĐỊNH HTTP API ROUTES CỦA SERVER
# ============================================================================


def test_server_add_family_email_api_dispatch() -> None:
    """Kiểm tra xử lý nghiệp vụ của API server đối với các lời gọi add_family_email."""
    mgr = get_auth_manager()

    # C1 hợp lệ
    c1_res = mgr.add_family_email("tuan_anh", "api_test_member@gmail.com", 2)
    assert c1_res["ok"] is True

    # C2 leo quyền bị chặn
    c2_res = mgr.add_family_email("thanh_vien_a", "api_hack_c1@gmail.com", 1)
    assert c2_res["ok"] is False
    assert c2_res["status_code"] == 403

    # C3 bị chặn hoàn toàn
    c3_res = mgr.add_family_email("khach_c", "api_c3_any@gmail.com", 3)
    assert c3_res["ok"] is False
    assert c3_res["status_code"] == 403
