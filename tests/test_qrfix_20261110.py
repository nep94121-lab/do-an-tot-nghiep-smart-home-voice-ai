"""Bộ Kiểm Thử Bảo Mật Toàn Diện cho Luồng Chia Sẻ QR & Đăng Ký Khách Độc Lập (Branch: qrfix-20261110).

Kiểm chứng đầy đủ 6 yêu cầu bảo mật:
1. Single-use post-scan link/token: tiêu thụ nguyên tử (atomic) ngay lần đăng ký thành công đầu tiên; mọi lần dùng lại bị từ chối ở server.
2. Gắn kết chặt với phiên quét (Scanning Session Binding qua HttpOnly cookie `sh_qr_scan_nonce` + hạn ngắn 180s); mở link hoặc gửi API từ trình duyệt/thiết bị/phiên khác bị từ chối 403.
3. Thao tác sai hoặc thử lại (retry) tự động hủy phiên hiện tại và bắt buộc quét lại mã QR của Chủ nhà (token mới); link sao chép không bao giờ hoạt động cho người khác.
4. Bản thân mã QR của Chủ nhà không tự cấp quyền đăng ký nếu thiếu gắn kết phiên quét; bắt buộc phê duyệt bởi Chủ nhà Cấp 1 (chỉ Cấp 1 mới có quyền cấp).
5. Toàn bộ kiểm tra ở phía server; kiểm thử tự động: reuse rejected, other-session rejected, expired rejected, rescan issues new token and invalidates old, concurrent double-submit only one succeeds.
6. Trang đăng ký mở từ link sau quét là trang độc lập hoàn toàn (Isolated Standalone Page): không menu, không thanh điều hướng (nav bar), không nút quay lại (back button), không chứa bất kỳ liên kết nội bộ nào; server từ chối 403 mọi truy cập từ phiên/token đăng ký QR sang bất kỳ route nào khác của hệ thống.
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import json
import pathlib
import re
import sys
import threading
import time
import uuid
from unittest.mock import patch
import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.auth.qr_totp_mixin import QR_SCAN_COOKIE_NAME, QR_SESSION_COOKIE_NAME
from simulator.auth_3layer import get_auth_3layer_manager
from simulator.server import _BOOT_VOICE_AUTH, app
from simulator.api import routes_qr
from simulator.api.deps import _REST_ENGINE


@pytest.fixture(autouse=True)
def clean_qr_and_voice_state():
    """Khôi phục trạng thái sạch cho bộ quản lý QR và VoiceAuth trước & sau mỗi bài test."""
    mgr = get_auth_3layer_manager()
    mgr._ensure_qr_stores()
    mgr.used_qr_tokens.clear()
    mgr.active_qr_tokens.clear()
    mgr.guest_qr_sessions.clear()
    mgr.pending_guest_email_otps.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    yield
    mgr.used_qr_tokens.clear()
    mgr.active_qr_tokens.clear()
    mgr.guest_qr_sessions.clear()
    mgr.pending_guest_email_otps.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()


def _make_owner_client() -> TestClient:
    """Client đại diện cho Chủ nhà Cấp 1 (Nguyễn Tuấn Anh - nep94121@gmail.com)."""
    return TestClient(app, headers={"Authorization": "Bearer sess_owner_t1_nep94121"})


def _make_scanner_client() -> TestClient:
    """Client độc lập đại diện cho thiết bị của người trực tiếp quét mã QR."""
    return TestClient(app)


def _generate_valid_guest_pcm_b64(f0: float = 242.0, duration_sec: float = 2.8) -> str:
    """Sinh mẫu âm thanh PCM 16kHz hợp lệ cho khách mới (không trùng giọng chủ nhà)."""
    sr = 16000
    silence_sec = 0.65
    n_silence = int(sr * silence_sec)
    n_voice = int(sr * max(0.5, duration_sec - silence_sec))
    silence = np.zeros(n_silence, dtype=np.float32)
    t = np.linspace(0, max(0.5, duration_sec - silence_sec), n_voice, endpoint=False)
    voice = (
        0.40 * np.sin(2 * np.pi * f0 * t)
        + 0.20 * np.sin(2 * np.pi * (f0 * 2) * t)
        + 0.10 * np.sin(2 * np.pi * (f0 * 3) * t)
    )
    sig = np.concatenate([silence, voice])
    pcm16 = (sig * 32767).astype(np.int16)
    return base64.b64encode(pcm16.tobytes()).decode("ascii")


# =============================================================================
# REQUIREMENT 1: SINGLE-USE POST-SCAN TOKEN/LINK (CONSUMED ATOMICALLY, REUSE REJECTED)
# =============================================================================

def test_req1_post_scan_token_single_use_consumed_atomically_and_reuse_rejected() -> None:
    owner_client = _make_owner_client()
    scanner_client = _make_scanner_client()

    # 1. Chủ nhà Cấp 1 tạo mã QR
    qr_res = owner_client.get("/api/auth3/guest_qr_current?duration=1d")
    assert qr_res.status_code == 200
    qr_data = qr_res.json()
    qr_token = qr_data["token"]

    # 2. Người quét thực hiện bắt tay (scan QR) -> nhận session_id, post_scan_token và cookie gắn phiên
    hs_res = scanner_client.post("/api/auth3/guest_qr_handshake", json={"token": qr_token, "duration": "1d"})
    assert hs_res.status_code == 200
    hs_data = hs_res.json()
    assert hs_data["ok"] is True
    session_id = hs_data["session_id"]
    post_scan_token = hs_data["post_scan_token"]
    post_scan_url = hs_data["post_scan_url"]
    assert QR_SCAN_COOKIE_NAME in scanner_client.cookies

    # 3. Người quét mở trang đăng ký từ post_scan_url lần đầu -> 200 OK
    page_res = scanner_client.get(post_scan_url)
    assert page_res.status_code == 200

    # 4. Đăng ký giọng nói lần thứ nhất -> Thành công (200 OK) và tiêu thụ nguyên tử token/session
    audio_b64 = _generate_valid_guest_pcm_b64(f0=240.0)
    reg1 = scanner_client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "session_id": session_id,
            "post_scan_token": post_scan_token,
            "guest_name": "Khách Hợp Lệ Lần 1",
            "duration": "1d",
            "audio_pcm_b64": audio_b64,
        },
    )
    assert reg1.status_code == 200
    assert reg1.json()["ok"] is True
    assert reg1.json()["single_use_consumed"] is True

    # 5. Dùng lại cùng post-scan token/session lần thứ 2 -> Bị từ chối 400 (SINGLE_USE_TOKEN_REUSED)
    audio_b64_2 = _generate_valid_guest_pcm_b64(f0=255.0)
    reg2 = scanner_client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "session_id": session_id,
            "post_scan_token": post_scan_token,
            "guest_name": "Kẻ Dùng Lại Token",
            "duration": "1d",
            "audio_pcm_b64": audio_b64_2,
        },
    )
    assert reg2.status_code == 400
    assert reg2.json()["ok"] is False
    assert reg2.json()["status"] == "TOKEN_ALREADY_CONSUMED"
    assert reg2.json()["reason"] == "SINGLE_USE_TOKEN_REUSED"

    # 6. Mở lại post_scan_url sau khi đã đăng ký -> Bị từ chối 403
    page_reuse = scanner_client.get(post_scan_url)
    assert page_reuse.status_code == 403
    assert page_reuse.json()["reason"] == "SINGLE_USE_TOKEN_REUSED"


# =============================================================================
# REQUIREMENT 2: BOUND TO SCANNING SESSION (OTHER SESSION & EXPIRED REJECTED)
# =============================================================================

def test_req2_other_browser_device_session_rejected_on_link_and_api() -> None:
    owner_client = _make_owner_client()
    scanner_client = _make_scanner_client()
    forwarded_client = _make_scanner_client()  # Thiết bị/trình duyệt khác nhận link copy

    qr_res = owner_client.get("/api/auth3/guest_qr_current?duration=1d")
    assert qr_res.status_code == 200
    qr_token = qr_res.json()["token"]
    qr_url = qr_res.json()["qr_url"]

    # Thiết bị 1 quét mã QR mở link trước -> gắn kết chặt với cookie của thiết bị 1
    open_scan = scanner_client.get(qr_url)
    assert open_scan.status_code == 200
    assert QR_SCAN_COOKIE_NAME in scanner_client.cookies

    # Thiết bị 2 mở link QR đã copy -> Bị từ chối 403 (OTHER_SESSION_REJECTED)
    open_forwarded_qr = forwarded_client.get(qr_url)
    assert open_forwarded_qr.status_code == 403
    assert open_forwarded_qr.json()["reason"] == "OTHER_SESSION_REJECTED"

    # Thiết bị 2 thử gọi handshake bằng token đã gắn với Thiết bị 1 -> Bị từ chối 403
    hs_forwarded = forwarded_client.post("/api/auth3/guest_qr_handshake", json={"token": qr_token, "duration": "1d"})
    assert hs_forwarded.status_code == 403
    assert hs_forwarded.json()["reason"] == "SESSION_BINDING_MISMATCH"

    # Thiết bị 1 gọi handshake -> Thành công 200
    hs_scanner = scanner_client.post("/api/auth3/guest_qr_handshake", json={"token": qr_token, "duration": "1d"})
    assert hs_scanner.status_code == 200
    hs_data = hs_scanner.json()
    session_id = hs_data["session_id"]
    post_scan_token = hs_data["post_scan_token"]
    post_scan_url = hs_data["post_scan_url"]

    # Thiết bị 2 mở post_scan_url đã copy -> Bị từ chối 403
    open_forwarded_post = forwarded_client.get(post_scan_url)
    assert open_forwarded_post.status_code == 403
    assert open_forwarded_post.json()["reason"] == "OTHER_SESSION_REJECTED"

    # Thiết bị 2 gửi đăng ký giọng nói bằng session_id + post_scan_token đã copy -> Bị từ chối 403
    audio_b64 = _generate_valid_guest_pcm_b64(f0=248.0)
    reg_forwarded = forwarded_client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "session_id": session_id,
            "post_scan_token": post_scan_token,
            "guest_name": "Người Nhận Link Forward",
            "duration": "1d",
            "audio_pcm_b64": audio_b64,
        },
    )
    assert reg_forwarded.status_code == 403
    assert reg_forwarded.json()["status"] == "SESSION_BINDING_MISMATCH"
    assert reg_forwarded.json()["reason"] == "OTHER_SESSION_REJECTED"

    # Thiết bị 2 thử giả mạo cookie scan_nonce ngẫu nhiên -> Vẫn bị từ chối 403
    forwarded_client.cookies.set(QR_SCAN_COOKIE_NAME, "forged_device_nonce_999999")
    reg_forged_cookie = forwarded_client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "session_id": session_id,
            "post_scan_token": post_scan_token,
            "guest_name": "Kẻ Giả Mạo Cookie",
            "duration": "1d",
            "audio_pcm_b64": audio_b64,
        },
    )
    assert reg_forged_cookie.status_code == 403
    assert reg_forged_cookie.json()["reason"] == "OTHER_SESSION_REJECTED"


def test_req2_and_req5_expired_token_and_expired_session_rejected() -> None:
    owner_client = _make_owner_client()
    scanner_client = _make_scanner_client()
    mgr = get_auth_3layer_manager()

    # 1. Kiểm tra token QR hết hạn trước khi quét
    qr_res = owner_client.get("/api/auth3/guest_qr_current?duration=1d")
    qr_token = qr_res.json()["token"]
    mgr.active_qr_tokens[qr_token]["expires_at_ts"] = time.time() - 5.0

    hs_exp = scanner_client.post("/api/auth3/guest_qr_handshake", json={"token": qr_token, "duration": "1d"})
    assert hs_exp.status_code == 401
    assert hs_exp.json()["ok"] is False
    assert hs_exp.json()["reason"] == "TOKEN_EXPIRED"

    # 2. Kiểm tra phiên sau quét (post-scan session) hết hạn 180s
    qr_res2 = owner_client.get("/api/auth3/guest_qr_current?duration=1d")
    qr_token2 = qr_res2.json()["token"]
    hs_ok = scanner_client.post("/api/auth3/guest_qr_handshake", json={"token": qr_token2, "duration": "1d"})
    assert hs_ok.status_code == 200
    session_id = hs_ok.json()["session_id"]
    post_scan_url = hs_ok.json()["post_scan_url"]

    # Tua thời gian hết hạn của phiên về quá khứ
    mgr.guest_qr_sessions[session_id]["session_expires_at"] = time.time() - 1.0

    page_exp = scanner_client.get(post_scan_url)
    assert page_exp.status_code == 403
    assert page_exp.json()["status"] == "SESSION_EXPIRED"

    reg_exp = scanner_client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "session_id": session_id,
            "guest_name": "Khách Hết Hạn",
            "duration": "1d",
            "audio_pcm_b64": _generate_valid_guest_pcm_b64(f0=240.0),
        },
    )
    assert reg_exp.status_code == 400
    assert reg_exp.json()["status"] == "SESSION_EXPIRED"
    assert reg_exp.json()["reason"] == "QR_SESSION_EXPIRED"


# =============================================================================
# REQUIREMENT 3: MISTAKE/RETRY REQUIRES RESCAN (NEW TOKEN) & RESCAN INVALIDATES OLD
# =============================================================================

def test_req3_mistake_invalidates_session_and_requires_new_qr_rescan() -> None:
    owner_client = _make_owner_client()
    scanner_client = _make_scanner_client()

    # 1. Quét QR lần 1
    qr1 = owner_client.get("/api/auth3/guest_qr_current?duration=1d").json()
    hs1 = scanner_client.post("/api/auth3/guest_qr_handshake", json={"token": qr1["token"], "duration": "1d"}).json()
    session_id_1 = hs1["session_id"]
    post_scan_token_1 = hs1["post_scan_token"]

    # 2. Người quét làm sai (gửi bản thu quá ngắn / lỗi) -> Server trả lỗi 400 kèm must_rescan=True và hủy phiên
    short_b64 = base64.b64encode(b"\x00\x00" * 500).decode("ascii")
    mistake_res = scanner_client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "session_id": session_id_1,
            "post_scan_token": post_scan_token_1,
            "guest_name": "Khách Thu Lỗi",
            "duration": "1d",
            "audio_pcm_b64": short_b64,
        },
    )
    assert mistake_res.status_code == 400
    assert mistake_res.json()["ok"] is False
    assert mistake_res.json()["must_rescan"] is True

    # 3. Người quét cố thử lại (retry) trên cùng session_id_1 với audio hợp lệ -> Bị từ chối 400 (SESSION_INVALIDATED)
    valid_b64 = _generate_valid_guest_pcm_b64(f0=238.0)
    retry_same_token = scanner_client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "session_id": session_id_1,
            "post_scan_token": post_scan_token_1,
            "guest_name": "Khách Thử Lại Link Cũ",
            "duration": "1d",
            "audio_pcm_b64": valid_b64,
        },
    )
    assert retry_same_token.status_code == 400
    assert retry_same_token.json()["status"] == "SESSION_INVALIDATED"
    assert retry_same_token.json()["must_rescan"] is True

    # 4. Bắt buộc quét lại mã QR mới của Chủ nhà -> nhận token mới và đăng ký thành công
    qr2 = owner_client.get("/api/auth3/guest_qr_current?duration=1d").json()
    assert qr2["token"] != qr1["token"]
    hs2 = scanner_client.post("/api/auth3/guest_qr_handshake", json={"token": qr2["token"], "duration": "1d"}).json()
    assert hs2["ok"] is True
    assert hs2["session_id"] != session_id_1

    reg_after_rescan = scanner_client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "session_id": hs2["session_id"],
            "post_scan_token": hs2["post_scan_token"],
            "guest_name": "Khách Quét Lại Thành Công",
            "duration": "1d",
            "audio_pcm_b64": valid_b64,
        },
    )
    assert reg_after_rescan.status_code == 200
    assert reg_after_rescan.json()["ok"] is True


def test_req3_and_req5_rescan_issues_new_token_and_invalidates_old_token_and_session() -> None:
    owner_client = _make_owner_client()
    scanner_client = _make_scanner_client()

    # Phát hành QR 1 và quét lấy phiên 1
    qr1 = owner_client.get("/api/auth3/guest_qr_current?duration=1d").json()
    tok1 = qr1["token"]
    hs1 = scanner_client.post("/api/auth3/guest_qr_handshake", json={"token": tok1, "duration": "1d"}).json()
    sid1 = hs1["session_id"]
    url1 = hs1["post_scan_url"]

    # Phát hành QR 2 (chưa dùng phiên 1) -> tạo token mới và tự động vô hiệu hóa phiên 1
    qr2 = owner_client.get("/api/auth3/guest_qr_current?duration=1d").json()
    tok2 = qr2["token"]
    assert tok2 != tok1

    # Phiên 1 lập tức bị vô hiệu hóa khi mở trang hoặc gửi đăng ký
    open_old = scanner_client.get(url1)
    assert open_old.status_code == 403
    assert open_old.json()["status"] == "SESSION_INVALIDATED"

    reg_old = scanner_client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "session_id": sid1,
            "guest_name": "Khách Dùng Phiên Cũ",
            "duration": "1d",
            "audio_pcm_b64": _generate_valid_guest_pcm_b64(f0=244.0),
        },
    )
    assert reg_old.status_code == 400
    assert reg_old.json()["status"] == "SESSION_INVALIDATED"

    # Ngoài ra, nếu phát hành QR 3 thì QR 2 chưa quét cũng bị hủy ngay lập tức
    qr3 = owner_client.get("/api/auth3/guest_qr_current?duration=1d").json()
    tok3 = qr3["token"]
    assert tok3 != tok2
    hs_old_tok2 = scanner_client.post("/api/auth3/guest_qr_handshake", json={"token": tok2, "duration": "1d"})
    assert hs_old_tok2.status_code == 400
    assert hs_old_tok2.json()["reason"] == "TOKEN_INVALIDATED_BY_RESCAN"


# =============================================================================
# REQUIREMENT 4: OWNER QR ALONE DOES NOT GRANT REGISTRATION; ONLY CAP 1 GRANTS
# =============================================================================

def test_req4_only_cap1_owner_can_issue_qr_and_raw_qr_cannot_register_without_binding() -> None:
    anon_client = TestClient(app)
    family_t2_client = TestClient(app, headers={"Authorization": "Bearer sess_family_t2_member_a"})
    guest_t3_client = TestClient(app, headers={"Authorization": "Bearer sess_guest_t3_visitor_c"})
    owner_t1_client = _make_owner_client()

    # 1. Không đăng nhập (401), Cấp 2 Gia đình (403), Cấp 3 Khách (403) đều bị chặn tạo QR
    assert anon_client.get("/api/auth3/guest_qr_current").status_code == 401
    assert family_t2_client.get("/api/auth3/guest_qr_current").status_code == 403
    assert guest_t3_client.get("/api/auth3/guest_qr_current").status_code == 403

    # Gọi trực tiếp hàm mixin với issuer_tier=2 hoặc 3 cũng bị từ chối 403
    mgr = get_auth_3layer_manager()
    assert mgr.generate_dynamic_qr_token(issuer_tier=2)["status_code"] == 403
    assert mgr.generate_dynamic_qr_token(issuer_tier=3)["status_code"] == 403

    # 2. Chủ nhà Cấp 1 tạo mã QR hợp lệ
    qr_res = owner_t1_client.get("/api/auth3/guest_qr_current?duration=1d")
    assert qr_res.status_code == 200
    raw_qr_token = qr_res.json()["token"]

    # 3. Dùng trực tiếp mã QR của Chủ nhà để gọi API đăng ký (bỏ qua bước quét gắn kết phiên) -> Bị từ chối 403
    direct_reg = anon_client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "session_id": raw_qr_token,
            "token": raw_qr_token,
            "guest_name": "Kẻ Dùng Trực Tiếp Mã QR",
            "duration": "1d",
            "audio_pcm_b64": _generate_valid_guest_pcm_b64(f0=240.0),
        },
    )
    assert direct_reg.status_code == 403
    assert direct_reg.json()["status"] == "QR_BINDING_REQUIRED"
    assert direct_reg.json()["reason"] == "OWNER_QR_CANNOT_REGISTER_DIRECTLY"


# =============================================================================
# REQUIREMENT 5: CONCURRENT DOUBLE-SUBMIT ONLY ONE SUCCEEDS
# =============================================================================

def test_req5_concurrent_double_submit_only_one_succeeds() -> None:
    owner_client = _make_owner_client()
    scanner_client = _make_scanner_client()

    qr_res = owner_client.get("/api/auth3/guest_qr_current?duration=1d")
    qr_token = qr_res.json()["token"]

    hs_res = scanner_client.post("/api/auth3/guest_qr_handshake", json={"token": qr_token, "duration": "1d"})
    assert hs_res.status_code == 200
    session_id = hs_res.json()["session_id"]
    post_scan_token = hs_res.json()["post_scan_token"]
    scan_nonce = scanner_client.cookies.get(QR_SCAN_COOKIE_NAME)
    assert scan_nonce

    audio_b64 = _generate_valid_guest_pcm_b64(f0=246.0)
    num_concurrent = 6
    barrier = threading.Barrier(num_concurrent)

    def _submit_worker(idx: int) -> tuple[int, dict]:
        worker_client = TestClient(app)
        worker_client.cookies.set(QR_SCAN_COOKIE_NAME, str(scan_nonce))
        worker_client.cookies.set(QR_SESSION_COOKIE_NAME, session_id)
        barrier.wait(timeout=5.0)
        resp = worker_client.post(
            "/api/auth3/guest_qr_complete_voice",
            json={
                "session_id": session_id,
                "post_scan_token": post_scan_token,
                "guest_name": f"Khách Đồng Thời {idx}",
                "duration": "1d",
                "audio_pcm_b64": audio_b64,
            },
        )
        return resp.status_code, resp.json()

    with ThreadPoolExecutor(max_workers=num_concurrent) as pool:
        futures = [pool.submit(_submit_worker, i) for i in range(num_concurrent)]
        results = [f.result(timeout=30.0) for f in futures]

    successes = [r for r in results if r[0] == 200 and r[1].get("ok") is True]
    rejections = [
        r
        for r in results
        if r[0] == 400
        and r[1].get("ok") is False
        and r[1].get("reason") == "SINGLE_USE_TOKEN_REUSED"
    ]

    assert len(successes) == 1, f"Expected exactly 1 success in concurrent double-submit, got {len(successes)}: {results}"
    assert len(rejections) == num_concurrent - 1, f"Expected {num_concurrent - 1} rejections, got {len(rejections)}: {results}"


# =============================================================================
# REQUIREMENT 6: ISOLATED STANDALONE PAGE (NO INTERNAL LINKS, OTHER ROUTES REJECTED)
# =============================================================================

def test_req6_isolated_page_html_contains_no_internal_links_menu_nav_or_back_button() -> None:
    owner_client = _make_owner_client()
    scanner_client = _make_scanner_client()

    qr_res = owner_client.get("/api/auth3/guest_qr_current?duration=1d")
    qr_token = qr_res.json()["token"]
    hs_res = scanner_client.post("/api/auth3/guest_qr_handshake", json={"token": qr_token, "duration": "1d"})
    post_scan_url = hs_res.json()["post_scan_url"]

    page_res = scanner_client.get(post_scan_url)
    assert page_res.status_code == 200
    html = page_res.text

    # 1. Không có thẻ <nav>, không có <header class="guesttop">, không có thẻ liên kết <a ...>
    assert "<nav" not in html.lower(), "Trang đăng ký không được chứa thanh điều hướng <nav>"
    assert "guesttop" not in html.lower(), "Trang đăng ký không được chứa header điều hướng"
    assert "<a " not in html.lower() and "<a>" not in html.lower(), "Trang đăng ký không được chứa bất kỳ thẻ liên kết <a> nào"

    # 2. Không có bất kỳ href nào trỏ tới trang chủ hoặc các trang khác trong hệ thống
    href_matches = re.findall(r'href\s*=\s*["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    for href_val in href_matches:
        # Chỉ cho phép duy nhất stylesheet tĩnh và icon SVG nội bộ #i-mic
        assert href_val in ("/static/css/guest_enroll.css", "#i-mic"), f"Phát hiện liên kết không được phép trong HTML: {href_val}"

    # 3. Không có nút quay lại (history.back) hay chuyển hướng sang route khác
    assert "history.back" not in html.lower()
    assert "history.go" not in html.lower()
    for forbidden_route in ["/app", "/auth", "/wokwi", "/logs", "/login", "/register", "/mobile", "/archify"]:
        assert f'"{forbidden_route}"' not in html and f"'{forbidden_route}'" not in html

    # 4. Đảm bảo chỉ có form đăng ký giọng nói hoạt động
    assert 'id="voiceEnrollCard"' in html
    assert 'id="guestNameInput"' in html
    assert 'id="btnRecordGuestVoice"' in html


def test_req6_server_refuses_registration_token_or_session_access_to_other_routes() -> None:
    owner_client = _make_owner_client()
    scanner_client = _make_scanner_client()

    qr_res = owner_client.get("/api/auth3/guest_qr_current?duration=1d")
    qr_token = qr_res.json()["token"]
    hs_res = scanner_client.post("/api/auth3/guest_qr_handshake", json={"token": qr_token, "duration": "1d"})
    assert hs_res.status_code == 200
    session_id = hs_res.json()["session_id"]
    post_scan_token = hs_res.json()["post_scan_token"]

    # Danh sách các route khác trên hệ thống mà phiên đăng ký QR tuyệt đối không được phép truy cập
    forbidden_get_routes = [
        "/",
        "/app",
        "/mobile",
        "/auth",
        "/logs",
        "/wokwi",
        "/login",
        "/register",
        "/archify",
        "/architecture",
        "/api/state",
        "/api/auth3/overview",
        "/api/auth3/guest_qr_current",
        "/api/logs",
    ]
    for route in forbidden_get_routes:
        res = scanner_client.get(route, follow_redirects=False)
        assert res.status_code == 403, f"Route {route} phải bị từ chối 403 cho phiên QR, nhưng trả về {res.status_code}"
        assert res.json()["status"] == "QR_REGISTRATION_SESSION_ISOLATED"

    # Kiểm tra cả khi client khác dùng Bearer token hoặc query param của phiên QR để gọi sang route khác
    token_bearer_client = TestClient(app, headers={"Authorization": f"Bearer {session_id}"})
    assert token_bearer_client.get("/").status_code == 403
    assert token_bearer_client.get("/api/state").status_code == 403

    pst_bearer_client = TestClient(app, headers={"Authorization": f"Bearer {post_scan_token}"})
    assert pst_bearer_client.get("/app").status_code == 403
    assert pst_bearer_client.post("/api/device", json={"device": "light", "state": True}).status_code == 403


# =============================================================================
# FIX ROUND 2 REGRESSION TESTS (F1: OTP BINDING/SINGLE-USE/CAP1 & F2: ALL CARRIERS + WS)
# =============================================================================

def _handshake_pair(nonce: str | None = None) -> tuple[TestClient, dict]:
    owner = _make_owner_client()
    scanner = _make_scanner_client()
    qr = owner.get("/api/auth3/guest_qr_current?duration=1d").json()
    payload = {"token": qr["token"], "duration": "1d"}
    if nonce:
        payload["scan_nonce"] = nonce
    hs = scanner.post("/api/auth3/guest_qr_handshake", json=payload)
    assert hs.status_code == 200
    return scanner, hs.json()


def test_round2_f1_otp_without_qr_or_binding_rejected_and_never_adds_guest() -> None:
    from unittest.mock import patch
    from simulator.api import routes_qr
    from simulator.api.deps import _REST_ENGINE

    mgr = get_auth_3layer_manager()
    anon = TestClient(app)
    name = "Round2NoQrGuest"
    email = "round2-noqr@example.invalid"
    before = name in [v.get("name") for v in _REST_ENGINE.users.values()]

    with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no DNS/mail")):
        send_res = anon.post(
            "/api/auth3/guest_qr_send_otp",
            json={"email": email, "confirm_email": email, "guest_name": name},
        )
    assert send_res.status_code in (401, 403)
    assert email not in mgr.pending_guest_email_otps

    verify_res = anon.post("/api/auth3/guest_qr_verify_otp", json={"email": email, "otp": "123456"})
    after = name in [v.get("name") for v in _REST_ENGINE.users.values()]
    assert verify_res.status_code in (401, 403)
    assert verify_res.json().get("verified") is not True
    assert not before and not after


def test_round2_f1_otp_single_use_consumed_atomically_multiple_registrations_rejected() -> None:
    from unittest.mock import patch
    from simulator.api import routes_qr

    scanner, hs = _handshake_pair()
    mgr = get_auth_3layer_manager()
    codes = []
    for i in range(2):
        email = f"round2-bound-{i}@example.invalid"
        payload = {
            "session_id": hs["session_id"],
            "post_scan_token": hs["post_scan_token"],
            "email": email,
            "confirm_email": email,
            "guest_name": f"Round2BoundGuest{i}",
        }
        with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no DNS/mail")):
            sent = scanner.post("/api/auth3/guest_qr_send_otp", json=payload)
        otp = mgr.pending_guest_email_otps.get(email, {}).get("otp", "")
        r = scanner.post("/api/auth3/guest_qr_verify_otp", json={**payload, "otp": otp})
        codes.append(r.status_code)

    state = mgr.guest_qr_sessions[hs["session_id"]]
    assert codes[0] == 200
    assert codes[1] in (400, 403)
    assert state["status"] == "CONSUMED"
    assert state["consumed"] is True


def test_round2_f1_otp_other_session_or_fake_session_id_override_rejected() -> None:
    from unittest.mock import patch
    from simulator.api import routes_qr

    scanner, hs = _handshake_pair()
    mgr = get_auth_3layer_manager()
    email = "round2-forward@example.invalid"
    with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no DNS/mail")):
        s_res = scanner.post(
            "/api/auth3/guest_qr_send_otp",
            json={
                "session_id": hs["session_id"],
                "email": email,
                "confirm_email": email,
                "guest_name": "Round2OtherSession",
            },
        )
    assert s_res.status_code == 200
    otp = mgr.pending_guest_email_otps[email]["otp"]

    other = TestClient(app)
    r_fake_sid = other.post(
        "/api/auth3/guest_qr_verify_otp",
        json={"session_id": "not-a-real-session", "email": email, "otp": otp},
    )
    assert r_fake_sid.status_code in (401, 403)
    assert r_fake_sid.json().get("verified") is not True

    r_real_sid_no_cookie = other.post(
        "/api/auth3/guest_qr_verify_otp",
        json={"session_id": hs["session_id"], "email": email, "otp": otp},
    )
    assert r_real_sid_no_cookie.status_code in (401, 403)
    assert r_real_sid_no_cookie.json().get("verified") is not True


@pytest.mark.parametrize("revocation", ["expired", "rescan"])
def test_round2_f1_otp_expired_or_rescanned_session_override_rejected(revocation: str) -> None:
    from unittest.mock import patch
    from simulator.api import routes_qr

    scanner, hs = _handshake_pair()
    mgr = get_auth_3layer_manager()
    email = f"round2-{revocation}@example.invalid"
    with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no DNS/mail")):
        scanner.post(
            "/api/auth3/guest_qr_send_otp",
            json={
                "session_id": hs["session_id"],
                "email": email,
                "confirm_email": email,
                "guest_name": "Round2Expired",
            },
        )
    otp = mgr.pending_guest_email_otps[email]["otp"]
    if revocation == "expired":
        mgr.guest_qr_sessions[hs["session_id"]]["session_expires_at"] = time.time() - 1.0
    else:
        _handshake_pair()
        assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True

    r_override = TestClient(app).post(
        "/api/auth3/guest_qr_verify_otp",
        json={"session_id": "not-a-real-session", "email": email, "otp": otp},
    )
    assert r_override.status_code in (400, 401, 403)

    r_scanner = scanner.post(
        "/api/auth3/guest_qr_verify_otp",
        json={"session_id": hs["session_id"], "email": email, "otp": otp},
    )
    assert r_scanner.status_code in (400, 401, 403)


def test_round2_f1_otp_concurrent_two_registrations_same_scan_only_one_succeeds() -> None:
    from unittest.mock import patch
    from simulator.api import routes_qr

    scanner, hs = _handshake_pair()
    mgr = get_auth_3layer_manager()
    payloads = []
    for i in range(2):
        email = f"round2-concurrent-{i}@example.invalid"
        with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no DNS/mail")):
            s_res = scanner.post(
                "/api/auth3/guest_qr_send_otp",
                json={
                    "session_id": hs["session_id"],
                    "email": email,
                    "confirm_email": email,
                    "guest_name": f"Round2Concurrent{i}",
                },
            )
            assert s_res.status_code == 200
        payloads.append(
            {
                "session_id": hs["session_id"],
                "email": email,
                "otp": mgr.pending_guest_email_otps[email]["otp"],
            }
        )
    cookies = dict(scanner.cookies)
    barrier = threading.Barrier(2)

    def _submit(p: dict) -> int:
        c = TestClient(app)
        c.cookies.update(cookies)
        barrier.wait(timeout=5.0)
        r = c.post("/api/auth3/guest_qr_verify_otp", json=p)
        return r.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(_submit, payloads))

    assert sum(c == 200 for c in codes) == 1
    assert mgr.guest_qr_sessions[hs["session_id"]]["consumed"] is True


def test_round2_req3_malformed_body_retry_invalidates_bound_session() -> None:
    scanner, hs = _handshake_pair()
    bad = scanner.post("/api/auth3/guest_qr_complete_voice", json=[])
    assert bad.status_code in (400, 422)
    page = scanner.get(hs["post_scan_url"])
    assert page.status_code == 403


@pytest.mark.parametrize("carrier", ["query_token", "x_session_token", "session_cookie", "sh_session_cookie"])
def test_round2_f2_alternative_token_carriers_and_auth_layer_rejected(carrier: str) -> None:
    from simulator.auth.session_store import resolve_request_session
    from simulator.api.deps import _REST_ENGINE

    _, hs = _handshake_pair()
    other = TestClient(app)
    kwargs: dict = {}
    if carrier == "query_token":
        kwargs["params"] = {"token": hs["session_id"]}
    elif carrier == "x_session_token":
        kwargs["headers"] = {"x-session-token": hs["session_id"]}
    elif carrier == "session_cookie":
        other.cookies.set("session_token", hs["session_id"])
    else:
        other.cookies.set("sh_session_token", hs["session_id"])

    r = other.get("/app", follow_redirects=False, **kwargs)
    assert r.status_code == 403

    # Kiểm chứng trực tiếp tại tầng auth session_store
    sess = resolve_request_session(request=None, payload={"token": hs["session_id"]}, engine=_REST_ENGINE)
    assert sess.is_authenticated is False


def test_round2_f2_websocket_rejected_for_qr_session_cookies_and_tokens() -> None:
    scanner, hs = _handshake_pair()
    accepted_cookie = False
    try:
        with scanner.websocket_connect("/ws"):
            accepted_cookie = True
    except Exception:
        pass
    assert not accepted_cookie

    other = TestClient(app)
    accepted_query = False
    try:
        with other.websocket_connect(f"/ws?token={hs['session_id']}"):
            accepted_query = True
    except Exception:
        pass
    assert not accepted_query


def test_round2_f1_otp_requires_cap1_owner_and_checks_grant_result() -> None:
    from unittest.mock import AsyncMock, patch
    from simulator.api import routes_qr
    from simulator.api.deps import _REST_ENGINE

    # 1. Nếu phiên bị hạ issuer_tier != 1 hoặc owner_approved = False -> từ chối 403
    scanner, hs = _handshake_pair()
    mgr = get_auth_3layer_manager()
    email1 = "round2-cap1-check@example.invalid"
    with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no DNS/mail")):
        s1 = scanner.post(
            "/api/auth3/guest_qr_send_otp",
            json={
                "session_id": hs["session_id"],
                "email": email1,
                "confirm_email": email1,
                "guest_name": "Round2Cap1Check",
            },
        )
        assert s1.status_code == 200
    otp1 = mgr.pending_guest_email_otps[email1]["otp"]
    mgr.guest_qr_sessions[hs["session_id"]]["issuer_tier"] = 2

    v1 = scanner.post(
        "/api/auth3/guest_qr_verify_otp",
        json={"session_id": hs["session_id"], "email": email1, "otp": otp1},
    )
    assert v1.status_code == 403
    assert v1.json().get("verified") is not True

    # 2. Nếu grant_user_permission trả về ok=False -> verify_otp phải kiểm tra kết quả và từ chối 403
    scanner2, hs2 = _handshake_pair()
    email2 = "round2-grant-fail@example.invalid"
    with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no DNS/mail")):
        s2 = scanner2.post(
            "/api/auth3/guest_qr_send_otp",
            json={
                "session_id": hs2["session_id"],
                "email": email2,
                "confirm_email": email2,
                "guest_name": "Round2GrantFail",
            },
        )
        assert s2.status_code == 200
    otp2 = mgr.pending_guest_email_otps[email2]["otp"]

    with patch.object(
        _REST_ENGINE,
        "grant_user_permission",
        new=AsyncMock(return_value={"ok": False, "error": "Simulated Cap1 grant rejection"}),
    ):
        v2 = scanner2.post(
            "/api/auth3/guest_qr_verify_otp",
            json={"session_id": hs2["session_id"], "email": email2, "otp": otp2},
        )
    assert v2.status_code == 403
    assert v2.json().get("ok") is False
    assert v2.json().get("verified") is not True


# =============================================================================
# FIX ROUND 3 REGRESSION TESTS (N1: MALFORMED JSON INVALIDATION & N2: BODY CARRIERS)
# =============================================================================


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/auth3/guest_qr_complete_voice",
        "/api/auth3/guest/enroll_voice",
        "/api/auth3/guest_qr_send_otp",
        "/api/auth3/guest_qr_verify_otp",
        "/api/auth3/guest/verify_email",
    ],
)
@pytest.mark.parametrize(
    "raw_body,content_type",
    [
        (b'{"', "application/json"),
        (b"", "application/json"),
        (b"\xff\xfe\xfd", "application/json"),
        (b"123", "application/json"),
        (b'{"bad_const": NaN}', "application/json"),
        (b"session_id=not_json_form", "application/x-www-form-urlencoded"),
    ],
)
def test_round3_n1_malformed_json_invalidates_session_and_requires_rescan(
    endpoint: str, raw_body: bytes, content_type: str
) -> None:
    scanner, hs = _handshake_pair()
    mgr = get_auth_3layer_manager()

    bad = scanner.post(endpoint, content=raw_body, headers={"content-type": content_type})
    assert bad.status_code == 422
    assert bad.json().get("ok") is False
    assert bad.json().get("must_rescan") is True
    assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True

    old_page = scanner.get(hs["post_scan_url"])
    assert old_page.status_code == 403


def test_round3_n1_invalid_json_blocks_subsequent_otp_and_voice_until_rescan() -> None:
    from unittest.mock import patch
    from simulator.api import routes_qr
    from simulator.api.deps import _REST_ENGINE

    # Case A: Malformed JSON on voice -> cannot proceed to send_otp / verify_otp / voice without rescan
    scanner, hs = _handshake_pair()
    mgr = get_auth_3layer_manager()
    bad = scanner.post(
        "/api/auth3/guest_qr_complete_voice",
        content='{"',
        headers={"content-type": "application/json"},
    )
    assert bad.status_code == 422

    email = "round3-json-retry@example.invalid"
    guest_name = "Round3JsonRetryBlocked"
    data = {
        "session_id": hs["session_id"],
        "email": email,
        "confirm_email": email,
        "guest_name": guest_name,
    }
    with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no DNS/mail")):
        send = scanner.post("/api/auth3/guest_qr_send_otp", json=data)
    otp = mgr.pending_guest_email_otps.get(email, {}).get("otp", "")
    verify = scanner.post("/api/auth3/guest_qr_verify_otp", json={**data, "otp": otp})
    voice_retry = scanner.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "session_id": hs["session_id"],
            "post_scan_token": hs["post_scan_token"],
            "guest_name": guest_name,
            "duration": "1d",
            "audio_pcm_b64": _generate_valid_guest_pcm_b64(f0=240.0),
        },
    )
    added = any(v.get("name") == guest_name for v in _REST_ENGINE.users.values())
    assert send.status_code in (400, 401, 403)
    assert verify.status_code in (400, 401, 403)
    assert verify.json().get("verified") is not True
    assert voice_retry.status_code in (400, 401, 403)
    assert not added

    # Case B: Send OTP valid first -> malformed JSON on verify_otp -> subsequent valid verify_otp rejected
    scanner2, hs2 = _handshake_pair()
    email2 = "round3-after-send@example.invalid"
    guest_name2 = "Round3AfterSendBlocked"
    data2 = {
        "session_id": hs2["session_id"],
        "email": email2,
        "confirm_email": email2,
        "guest_name": guest_name2,
    }
    with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no DNS/mail")):
        send2 = scanner2.post("/api/auth3/guest_qr_send_otp", json=data2)
    assert send2.status_code == 200
    real_otp2 = mgr.pending_guest_email_otps[email2]["otp"]

    bad_verify = scanner2.post(
        "/api/auth3/guest_qr_verify_otp",
        content='{"email":',
        headers={"content-type": "application/json"},
    )
    assert bad_verify.status_code == 422
    assert scanner2.get(hs2["post_scan_url"]).status_code == 403

    retry_verify2 = scanner2.post(
        "/api/auth3/guest_qr_verify_otp",
        json={**data2, "otp": real_otp2},
    )
    assert retry_verify2.status_code in (400, 401, 403)
    assert retry_verify2.json().get("verified") is not True
    assert not any(v.get("name") == guest_name2 for v in _REST_ENGINE.users.values())

    # Rescan with new QR succeeds cleanly
    scanner3, hs3 = _handshake_pair()
    email3 = "round3-rescan-ok@example.invalid"
    data3 = {
        "session_id": hs3["session_id"],
        "email": email3,
        "confirm_email": email3,
        "guest_name": "Round3RescanSuccess",
    }
    with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no DNS/mail")):
        s3 = scanner3.post("/api/auth3/guest_qr_send_otp", json=data3)
    assert s3.status_code == 200
    v3 = scanner3.post(
        "/api/auth3/guest_qr_verify_otp",
        json={**data3, "otp": mgr.pending_guest_email_otps[email3]["otp"]},
    )
    assert v3.status_code == 200
    assert v3.json().get("verified") is True


def test_round3_n1_malformed_field_types_and_third_party_dos_protection() -> None:
    mgr = get_auth_3layer_manager()

    # 1. Third-party client without scan_nonce sending broken JSON cannot DoS real scanner's session
    scanner, hs = _handshake_pair()
    attacker = TestClient(app)
    att_res = attacker.post(
        f"/api/auth3/guest_qr_complete_voice?session_id={hs['session_id']}",
        content='{"',
        headers={"content-type": "application/json"},
    )
    assert att_res.status_code == 422
    assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is False
    assert scanner.get(hs["post_scan_url"]).status_code == 200

    # 2. Scanner sending invalid field types (e.g. non-int sample_index or list email) invalidates session, no 500
    bad_field = scanner.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "session_id": hs["session_id"],
            "guest_name": "BadSampleIdx",
            "audio_pcm_b64": _generate_valid_guest_pcm_b64(f0=240.0),
            "sample_index": "not-an-int",
        },
    )
    assert bad_field.status_code in (400, 422)
    assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
    assert scanner.get(hs["post_scan_url"]).status_code == 403

    # 3. Scanner sending empty verify_otp dict {} invalidates bound session
    scanner_b, hs_b = _handshake_pair()
    empty_v = scanner_b.post("/api/auth3/guest_qr_verify_otp", json={})
    assert empty_v.status_code in (400, 403, 422)
    assert mgr.guest_qr_sessions[hs_b["session_id"]]["invalidated"] is True
    assert scanner_b.get(hs_b["post_scan_url"]).status_code == 403


@pytest.mark.parametrize("key", ["session_token", "guest_session_id", "session_id", "post_scan_token", "token"])
@pytest.mark.parametrize("value_kind", ["session_id", "post_scan_token"])
def test_round3_n2_json_body_token_fields_rejected_across_routes_and_methods(
    key: str, value_kind: str
) -> None:
    from simulator.auth.session_store import resolve_request_session
    from simulator.api.deps import _REST_ENGINE

    _, hs = _handshake_pair()
    value = hs[value_kind]
    payload = {key: value}

    c = TestClient(app)
    for route in ("/", "/app", "/api/state"):
        r_get = c.request("GET", route, json=payload, follow_redirects=False)
        assert r_get.status_code == 403, f"Expected 403 on GET {route} with body {key} ({value_kind}), got {r_get.status_code}"
        assert r_get.json().get("status") == "QR_REGISTRATION_SESSION_ISOLATED"

    r_post_dev = c.post("/api/device", json={**payload, "device_id": "living_room_light", "action": "turn_on"})
    assert r_post_dev.status_code == 403
    assert r_post_dev.json().get("status") == "QR_REGISTRATION_SESSION_ISOLATED"

    sess = resolve_request_session(payload=payload, engine=_REST_ENGINE)
    assert sess.is_authenticated is False


# =============================================================================
# FIX ROUND 4 REGRESSION TESTS (R3-N3: NUMERIC OVERFLOW / ABNORMAL INPUTS & R3-N4: QUERY SCAN_NONCE ISOLATION)
# =============================================================================


@pytest.mark.parametrize("field", ["sample_index", "total_samples"])
def test_round4_r3_n3_numeric_overflow_1e309_rejected_4xx_invalidates_and_blocks_otp_retry(
    field: str,
) -> None:
    """Counterexample R3-N3: JSON 1e309 in sample_index / total_samples must never give HTTP 500,
    must invalidate the bound QR session, make post_scan_url 403, and block subsequent OTP send/verify without rescan.
    """
    from unittest.mock import patch
    from simulator.api import routes_qr
    from simulator.api.deps import _REST_ENGINE

    scanner, hs = _handshake_pair()
    mgr = get_auth_3layer_manager()

    body = json.dumps({"session_id": hs["session_id"], "guest_name": "NumericMistake"})[:-1] + f',"{field}":1e309}}'
    c = TestClient(app, raise_server_exceptions=False)
    c.cookies.update(scanner.cookies)

    bad = c.post(
        "/api/auth3/guest_qr_complete_voice",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert 400 <= bad.status_code < 500, f"Expected 4xx for {field}=1e309, got {bad.status_code}"
    assert bad.json().get("ok") is False
    assert bad.json().get("must_rescan") is True

    inv = mgr.guest_qr_sessions[hs["session_id"]]["invalidated"]
    assert inv is True

    page = c.get(hs["post_scan_url"])
    assert page.status_code == 403

    email = f"round4-numeric-retry-{field}@example.invalid"
    guest_name = f"Round4NumericRetry_{field}"
    data = {
        "session_id": hs["session_id"],
        "email": email,
        "confirm_email": email,
        "guest_name": guest_name,
    }
    with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no mail")):
        send = c.post("/api/auth3/guest_qr_send_otp", json=data)
    otp = mgr.pending_guest_email_otps.get(email, {}).get("otp", "")
    verify = c.post("/api/auth3/guest_qr_verify_otp", json={**data, "otp": otp})
    added = any(v.get("name") == guest_name for v in _REST_ENGINE.users.values())

    assert send.status_code in (400, 401, 403)
    assert verify.status_code in (400, 401, 403)
    assert verify.json().get("verified") is not True
    assert added is False


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/auth3/guest_qr_complete_voice",
        "/api/auth3/guest/enroll_voice",
        "/api/auth3/guest_qr_send_otp",
        "/api/auth3/guest_qr_verify_otp",
        "/api/auth3/guest/verify_email",
        "/api/auth3/guest_qr_handshake",
        "/api/auth3/guest/handshake",
    ],
)
def test_round4_r3_n3_abnormal_numbers_and_types_across_every_qr_post_endpoint(
    endpoint: str,
) -> None:
    """Every numeric field across every QR POST endpoint rejects inf/nan/huge/float/negative/bool/wrong-type
    with 4xx (never 500), invalidates the bound QR session, and makes post_scan_url return 403 (1,183 probes).
    """
    mgr = get_auth_3layer_manager()
    fields = (
        "sample_index",
        "total_samples",
        "sample_count",
        "target_tier",
        "tier",
        "issuer_tier",
        "window",
        "target_window",
        "duration_seconds",
        "lock_ttl_sec",
        "attempts",
        "sr",
        "sample_rate",
    )
    raw_json_literals = (
        "1e309",
        "-1e309",
        "NaN",
        "Infinity",
        "-Infinity",
        "999999999999999999999999999999",
        "-1",
        "1.5",
        "true",
        '"1e309"',
        '"not-a-number"',
        "[]",
        "{}",
    )
    for field in fields:
        for raw_json_literal in raw_json_literals:
            scanner, hs = _handshake_pair()
            raw_body = (
                json.dumps({"session_id": hs["session_id"], "guest_name": "AbnormalMatrix"})[:-1]
                + f',"{field}":{raw_json_literal}}}'
            )
            c = TestClient(app, raise_server_exceptions=False)
            c.cookies.update(scanner.cookies)

            resp = c.post(endpoint, content=raw_body, headers={"content-type": "application/json"})
            assert 400 <= resp.status_code < 500, (
                f"Endpoint {endpoint} field {field}={raw_json_literal} returned {resp.status_code}"
            )
            assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
            assert c.get(hs["post_scan_url"]).status_code == 403


def test_round4_r3_n3_otp_fields_query_params_and_qr_generate_abnormal_inputs() -> None:
    """Covers OTP numeric/type edge cases, out-of-range ints (sample_index > total_samples, total_samples=0,
    tier=0/4), /guest_enroll abnormal query params, and /api/auth3/guest_qr_current (/qr/generate).
    """
    mgr = get_auth_3layer_manager()

    # 1. OTP fields (otp, otp_code, input_otp) with 1e309, float, negative, >999999, bool, list, dict
    for otp_key in ("otp", "otp_code", "input_otp"):
        for bad_lit in ("1e309", "-1", "1000000", "12.34", "true", "[]", "{}"):
            scanner, hs = _handshake_pair()
            c = TestClient(app, raise_server_exceptions=False)
            c.cookies.update(scanner.cookies)
            raw = (
                json.dumps({"session_id": hs["session_id"], "email": "otp-bad@example.invalid"})[:-1]
                + f',"{otp_key}":{bad_lit}}}'
            )
            r = c.post("/api/auth3/guest_qr_verify_otp", content=raw, headers={"content-type": "application/json"})
            assert 400 <= r.status_code < 500
            assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
            assert c.get(hs["post_scan_url"]).status_code == 403

    # 2. Out-of-range integers & sample_index > total_samples on voice / send_otp / verify_otp
    out_of_range_cases = [
        {"sample_index": 21},
        {"total_samples": 0},
        {"total_samples": 25},
        {"sample_index": 5, "total_samples": 3},
        {"target_tier": 0},
        {"target_tier": 4},
        {"issuer_tier": 2},
        {"verify_only": "yes"},
        {"enforce_12s_gate": 123},
    ]
    for extra_fields in out_of_range_cases:
        scanner, hs = _handshake_pair()
        c = TestClient(app, raise_server_exceptions=False)
        c.cookies.update(scanner.cookies)
        r = c.post(
            "/api/auth3/guest_qr_complete_voice",
            json={"session_id": hs["session_id"], "guest_name": "RangeCheck", **extra_fields},
        )
        assert 400 <= r.status_code < 500, f"Case {extra_fields} returned {r.status_code}"
        assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
        assert c.get(hs["post_scan_url"]).status_code == 403

    # 3. Abnormal query params on /guest_enroll and POST endpoints invalidate bound session
    for bad_qs in ("window=1e309", "sample_index=1e309", "total_samples=0", "tier=999", "target_tier=-5"):
        scanner, hs = _handshake_pair()
        c = TestClient(app, raise_server_exceptions=False)
        c.cookies.update(scanner.cookies)
        r_page = c.get(f"{hs['post_scan_url']}&{bad_qs}")
        assert 400 <= r_page.status_code < 500
        assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
        assert c.get(hs["post_scan_url"]).status_code == 403

    # 4. /api/auth3/guest_qr_current and /api/auth3/qr/generate reject 1e309 / out-of-range without 500
    owner = TestClient(
        app,
        headers={"Authorization": "Bearer sess_owner_t1_nep94121"},
        raise_server_exceptions=False,
    )
    assert 400 <= owner.get("/api/auth3/guest_qr_current?window=1e309").status_code < 500
    assert 400 <= owner.get("/api/auth3/guest_qr_current?tier=1e309").status_code < 500
    assert 400 <= owner.get("/api/auth3/guest_qr_current?issuer_tier=999").status_code < 500
    assert (
        400
        <= owner.post(
            "/api/auth3/qr/generate",
            content='{"issuer_tier": 1e309}',
            headers={"content-type": "application/json"},
        ).status_code
        < 500
    )


def test_round4_r3_n4_query_scan_nonce_and_all_nonce_carriers_isolated_from_other_routes() -> None:
    """Counterexample R3-N4: scan_nonce accepted as session-binding credential on registration API
    (?scan_nonce=...) MUST be rejected 403 on /, /app, /api/state, /api/device, closed 1008 on /ws,
    and rejected by resolve_request_session across query, headers, cookies, and JSON/form bodies.
    """
    from unittest.mock import patch
    from starlette.websockets import WebSocketDisconnect
    from simulator.api import routes_qr
    from simulator.api.deps import _REST_ENGINE
    from simulator.auth.session_store import resolve_request_session

    scanner, hs = _handshake_pair()
    nonce = scanner.cookies.get(QR_SCAN_COOKIE_NAME)
    assert nonce

    # 1. Exact R3-N4 counterexample: fresh client passes ?scan_nonce=<nonce> (no cookies)
    c_fresh = TestClient(app)
    email = "round4-query-nonce@example.invalid"
    with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no mail")):
        send = c_fresh.post(
            "/api/auth3/guest_qr_send_otp",
            params={"scan_nonce": nonce},
            json={
                "session_id": hs["session_id"],
                "email": email,
                "confirm_email": email,
                "guest_name": "Round4QueryNonce",
            },
        )
    assert send.status_code == 200

    other_routes = ("/", "/app", "/api/state", "/auth", "/logs", "/mobile", "/wokwi")
    for p in other_routes:
        r = c_fresh.get(p, params={"scan_nonce": nonce}, follow_redirects=False)
        assert r.status_code == 403, f"Route {p}?scan_nonce=... returned {r.status_code}, expected 403"
        assert r.json().get("status") == "QR_REGISTRATION_SESSION_ISOLATED"

    # 2. All query/header/cookie/body/form/WS carriers carrying scan_nonce rejected on non-QR routes
    for qk in ("scan_nonce", QR_SCAN_COOKIE_NAME, "token", "session_token", "sh_session_token", "session_id"):
        cq = TestClient(app)
        for p in ("/", "/app", "/api/state"):
            assert cq.get(p, params={qk: nonce}, follow_redirects=False).status_code == 403
        ws_accepted = False
        ws_code = None
        try:
            with cq.websocket_connect(f"/ws?{qk}={nonce}"):
                ws_accepted = True
        except WebSocketDisconnect as exc:
            ws_code = exc.code
        assert not ws_accepted and ws_code == 1008

    for hdr_k, hdr_v in (
        ("x-qr-scan-nonce", nonce),
        ("x-scan-nonce", nonce),
        ("x-session-token", nonce),
        ("authorization", f"Bearer {nonce}"),
    ):
        ch = TestClient(app, headers={hdr_k: hdr_v})
        for p in ("/", "/app", "/api/state"):
            assert ch.get(p, follow_redirects=False).status_code == 403

    for ck_k in (QR_SCAN_COOKIE_NAME, "scan_nonce", "session_token", "sh_session_token"):
        cc = TestClient(app)
        cc.cookies.set(ck_k, nonce)
        for p in ("/", "/app", "/api/state"):
            assert cc.get(p, follow_redirects=False).status_code == 403

    for body_k in ("scan_nonce", "session_token", "token", "post_scan_token", "session_id"):
        cb = TestClient(app)
        for p in ("/", "/app", "/api/state"):
            assert cb.request("GET", p, json={body_k: nonce}, follow_redirects=False).status_code == 403
            assert cb.request("GET", p, json={"session": {body_k: nonce}}, follow_redirects=False).status_code == 403
            assert cb.request("GET", p, json={"nested": {"auth": {body_k: nonce}}}, follow_redirects=False).status_code == 403
            assert cb.request("GET", p, data={body_k: nonce}, follow_redirects=False).status_code == 403
        sess = resolve_request_session(payload={body_k: nonce}, engine=_REST_ENGINE)
        assert sess.is_authenticated is False


# =============================================================================
# FIX ROUND 5 REGRESSION TESTS (R4-N1: UNICODE-ESCAPED NONCE + 1e309 & ALL CARRIERS/ENDPOINTS)
# =============================================================================


def _escape_json_u_all(val: str, *, upper_every_other: bool = False) -> str:
    out: list[str] = []
    for idx, ch in enumerate(val):
        cp = ord(ch)
        if cp <= 0xFFFF:
            fmt = "\\u%04X" if (upper_every_other and idx % 2 == 1) else "\\u%04x"
            out.append(fmt % cp)
        else:
            cp_adj = cp - 0x10000
            hi = 0xD800 + (cp_adj >> 10)
            lo = 0xDC00 + (cp_adj & 0x3FF)
            out.append(f"\\u{hi:04x}\\u{lo:04x}")
    return "".join(out)


@pytest.mark.parametrize("field", ["sample_index", "total_samples"])
@pytest.mark.parametrize(
    "carrier",
    [
        "cookie",
        "header",
        "duplicate_header",
        "query",
        "duplicate_query",
        "body",
        "escaped_body",
        "escaped_key_and_body",
        "mixed_case_hex_escaped_body",
        "duplicate_key_escaped_body",
        "percent_form_body",
        "multipart_body",
    ],
)
def test_round5_r4_n1_unicode_escaped_body_nonce_and_all_carriers_overflow_invalidation(
    carrier: str,
    field: str,
) -> None:
    """Counterexample R4-N1 & extended carrier matrix:
    A request carrying a valid scan_nonce (including \\uXXXX Unicode-escaped JSON body/key,
    duplicate headers/queries, %XX form, or multipart) alongside sample_index/total_samples=1e309
    MUST return 4xx (never 500), MUST atomically invalidate the bound session, MUST purge any
    pre-issued pending OTP, MUST reject reopening post_scan_url (403), and MUST reject OTP verify
    without adding any guest.
    """
    from unittest.mock import patch
    from urllib.parse import quote
    from simulator.api import routes_qr
    from simulator.api.deps import _REST_ENGINE

    scanner, hs = _handshake_pair()
    mgr = get_auth_3layer_manager()
    nonce = str(scanner.cookies.get(QR_SCAN_COOKIE_NAME) or "")
    assert nonce

    c = TestClient(app, raise_server_exceptions=False)
    send_headers: list[tuple[str, str]] = [("content-type", "application/json")]
    send_params: list[tuple[str, str]] = []
    bad_headers: list[tuple[str, str]] = [("content-type", "application/json")]
    bad_params: list[tuple[str, str]] = []
    verify_extra: dict = {}

    email = f"r5-{carrier}-{field}@example.invalid"
    guest_name = f"R5Guest_{carrier}_{field}"

    esc_nonce_lower = _escape_json_u_all(nonce, upper_every_other=False)
    esc_nonce_mixed = _escape_json_u_all(nonce, upper_every_other=True)
    esc_key = _escape_json_u_all("scan_nonce", upper_every_other=True)
    esc_sid = _escape_json_u_all(hs["session_id"], upper_every_other=True)

    send_base = {
        "session_id": hs["session_id"],
        "email": email,
        "confirm_email": email,
        "guest_name": guest_name,
    }

    if carrier == "cookie":
        c.cookies.set(QR_SCAN_COOKIE_NAME, nonce)
        send_raw = json.dumps(send_base).encode("utf-8")
        bad_raw = f'{{"session_id": "{hs["session_id"]}", "{field}": 1e309}}'.encode("utf-8")
    elif carrier == "header":
        send_headers.append(("x-qr-scan-nonce", nonce))
        bad_headers.append(("x-qr-scan-nonce", nonce))
        send_raw = json.dumps(send_base).encode("utf-8")
        bad_raw = f'{{"session_id": "{hs["session_id"]}", "{field}": 1e309}}'.encode("utf-8")
    elif carrier == "duplicate_header":
        send_headers.extend([("x-qr-scan-nonce", ""), ("x-qr-scan-nonce", nonce)])
        bad_headers.extend([("x-qr-scan-nonce", ""), ("x-qr-scan-nonce", nonce)])
        send_raw = json.dumps(send_base).encode("utf-8")
        bad_raw = f'{{"session_id": "{hs["session_id"]}", "{field}": 1e309}}'.encode("utf-8")
    elif carrier == "query":
        send_params.append(("scan_nonce", nonce))
        bad_params.append(("scan_nonce", nonce))
        send_raw = json.dumps(send_base).encode("utf-8")
        bad_raw = f'{{"session_id": "{hs["session_id"]}", "{field}": 1e309}}'.encode("utf-8")
    elif carrier == "duplicate_query":
        send_params.extend([("scan_nonce", ""), ("scan_nonce", nonce)])
        bad_params.extend([("scan_nonce", ""), ("scan_nonce", nonce)])
        send_raw = json.dumps(send_base).encode("utf-8")
        bad_raw = f'{{"session_id": "{hs["session_id"]}", "{field}": 1e309}}'.encode("utf-8")
    elif carrier == "body":
        send_raw = json.dumps({**send_base, "scan_nonce": nonce}).encode("utf-8")
        bad_raw = f'{{"session_id": "{hs["session_id"]}", "scan_nonce": "{nonce}", "{field}": 1e309}}'.encode("utf-8")
        verify_extra = {"scan_nonce": nonce}
    elif carrier == "escaped_body":
        send_raw = (
            "{"
            f'"session_id": "{hs["session_id"]}", '
            f'"scan_nonce": "{esc_nonce_lower}", '
            f'"email": "{email}", "confirm_email": "{email}", "guest_name": "{guest_name}"'
            "}"
        ).encode("utf-8")
        bad_raw = (
            "{"
            f'"session_id": "{hs["session_id"]}", '
            f'"scan_nonce": "{esc_nonce_lower}", '
            f'"{field}": 1e309'
            "}"
        ).encode("utf-8")
        verify_extra = {"scan_nonce": nonce}
    elif carrier == "escaped_key_and_body":
        send_raw = (
            "{"
            f'"session_id": "{esc_sid}", '
            f'"{esc_key}": "{esc_nonce_lower}", '
            f'"email": "{email}", "confirm_email": "{email}", "guest_name": "{guest_name}"'
            "}"
        ).encode("utf-8")
        bad_raw = (
            "{"
            f'"session_id": "{esc_sid}", '
            f'"{esc_key}": "{esc_nonce_lower}", '
            f'"{_escape_json_u_all(field)}": 1e309'
            "}"
        ).encode("utf-8")
        verify_extra = {"scan_nonce": nonce}
    elif carrier == "mixed_case_hex_escaped_body":
        send_raw = (
            "{"
            f'"session_id": "{hs["session_id"]}", '
            f'"scan_nonce": "{esc_nonce_mixed}", '
            f'"email": "{email}", "confirm_email": "{email}", "guest_name": "{guest_name}"'
            "}"
        ).encode("utf-8")
        bad_raw = (
            "{"
            f'"session_id": "{hs["session_id"]}", '
            f'"scan_nonce": "{esc_nonce_mixed}", '
            f'"{field}": 1e309'
            "}"
        ).encode("utf-8")
        verify_extra = {"scan_nonce": nonce}
    elif carrier == "duplicate_key_escaped_body":
        send_raw = json.dumps({**send_base, "scan_nonce": nonce}).encode("utf-8")
        bad_raw = (
            "{"
            f'"session_id": "{hs["session_id"]}", '
            f'"scan_nonce": "{esc_nonce_mixed}", '
            f'"scan_nonce": "wrong_override_after_valid", '
            f'"{field}": 1e309'
            "}"
        ).encode("utf-8")
        verify_extra = {"scan_nonce": nonce}
    elif carrier == "percent_form_body":
        send_raw = json.dumps({**send_base, "scan_nonce": nonce}).encode("utf-8")
        bad_headers = [("content-type", "application/x-www-form-urlencoded")]
        pct_nonce = "".join(f"%{b:02X}" for b in nonce.encode("utf-8"))
        bad_raw = f"session_id={quote(hs['session_id'])}&scan_nonce={pct_nonce}&{field}=1e309".encode("ascii")
        verify_extra = {"scan_nonce": nonce}
    else:
        send_raw = json.dumps({**send_base, "scan_nonce": nonce}).encode("utf-8")
        boundary = "----R5MultipartBoundary"
        bad_headers = [("content-type", f"multipart/form-data; boundary={boundary}")]
        bad_raw = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="session_id"\r\n\r\n{hs["session_id"]}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="scan_nonce"\r\n\r\n{nonce}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field}"\r\n\r\n1e309\r\n'
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        verify_extra = {"scan_nonce": nonce}

    # 1. Positive proof: carrier dispatches OTP 200 on the real scan session
    with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no mail")):
        send_resp = c.post(
            "/api/auth3/guest_qr_send_otp",
            content=send_raw,
            headers=send_headers,
            params=send_params,
        )
    assert send_resp.status_code == 200, f"Positive send failed for {carrier}: {send_resp.status_code}"
    saved_otp = mgr.pending_guest_email_otps[email]["otp"]

    # 2. Malformed/overflow request with 1e309 -> 4xx, invalidates session, purges pending OTP
    bad_resp = c.post(
        "/api/auth3/guest_qr_complete_voice",
        content=bad_raw,
        headers=bad_headers,
        params=bad_params,
    )
    assert 400 <= bad_resp.status_code < 500, f"Expected 4xx for {carrier}/{field}, got {bad_resp.status_code}"
    assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
    assert email not in mgr.pending_guest_email_otps

    # 3. Old post_scan_url is dead (403) and saved OTP cannot verify (verified=False, guest_added=False)
    assert scanner.get(hs["post_scan_url"]).status_code == 403
    verify_resp = c.post(
        "/api/auth3/guest_qr_verify_otp",
        json={"session_id": hs["session_id"], "email": email, "otp": saved_otp, **verify_extra},
        headers=[h for h in send_headers if h[0] != "content-type"],
        params=send_params,
    )
    assert verify_resp.status_code in (400, 401, 403)
    assert verify_resp.json().get("verified") is False
    assert not any(v.get("name") == guest_name for v in _REST_ENGINE.users.values())


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/auth3/guest_qr_complete_voice",
        "/api/auth3/guest/enroll_voice",
        "/api/auth3/guest_qr_send_otp",
        "/api/auth3/guest_qr_verify_otp",
        "/api/auth3/guest/verify_email",
        "/api/auth3/guest_qr_handshake",
        "/api/auth3/guest_handshake",
        "/api/auth3/guest/handshake",
        "/api/auth3/qr/generate",
    ],
)
def test_round5_escaped_nonce_abnormal_numbers_and_syntax_errors_across_all_qr_endpoints(endpoint: str) -> None:
    """Every QR endpoint receiving a body-only \\uXXXX-escaped scan_nonce (without cookies/headers/query)
    alongside 1e309, -1e309, NaN, Infinity, huge int, truncated JSON, or bad scalar type MUST return 4xx,
    invalidate the bound session, and purge pending OTPs.
    """
    from unittest.mock import patch
    from simulator.api import routes_qr

    mgr = get_auth_3layer_manager()
    esc_key = _escape_json_u_all("scan_nonce", upper_every_other=True)

    payload_templates = [
        lambda sid, en: f'{{"session_id":"{sid}","{esc_key}":"{en}","sample_index":1e309}}'.encode("utf-8"),
        lambda sid, en: f'{{"session_id":"{sid}","{esc_key}":"{en}","total_samples":-1e309}}'.encode("utf-8"),
        lambda sid, en: f'{{"session_id":"{sid}","{esc_key}":"{en}","window":NaN}}'.encode("utf-8"),
        lambda sid, en: f'{{"session_id":"{sid}","{esc_key}":"{en}","target_tier":Infinity}}'.encode("utf-8"),
        lambda sid, en: f'{{"session_id":"{sid}","{esc_key}":"{en}","sample_index":999999999999999999999999999}}'.encode("utf-8"),
        lambda sid, en: f'{{"session_id":"{sid}","{esc_key}":"{en}","broken_tail":'.encode("utf-8"),
        lambda sid, en: f'{{"session_id":"{sid}","{esc_key}":"{en}","duration":["bad_list"]}}'.encode("utf-8"),
        lambda sid, en: b"\xef\xbb\xbf" + f'{{"session_id":"{sid}","{esc_key}":"{en}","sample_index":1e309}}'.encode("utf-8"),
        lambda sid, en: b"\xff\xfe" + f'{{"session_id":"{sid}","{esc_key}":"{en}","sample_index":1e309}}'.encode("utf-16-le"),
    ]

    for idx, build_raw in enumerate(payload_templates):
        scanner, hs = _handshake_pair()
        nonce = str(scanner.cookies.get(QR_SCAN_COOKIE_NAME) or "")
        esc_nonce = _escape_json_u_all(nonce, upper_every_other=(idx % 2 == 0))
        email = f"r5-ep-{idx}@example.invalid"
        with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no mail")):
            assert (
                scanner.post(
                    "/api/auth3/guest_qr_send_otp",
                    json={"session_id": hs["session_id"], "email": email, "confirm_email": email, "guest_name": "R5Ep"},
                ).status_code
                == 200
            )

        c_fresh = TestClient(app, raise_server_exceptions=False)
        headers = {"content-type": "application/json"}
        if endpoint == "/api/auth3/qr/generate":
            headers["Authorization"] = "Bearer sess_owner_t1_nep94121"

        r = c_fresh.post(endpoint, content=build_raw(hs["session_id"], esc_nonce), headers=headers)
        assert 400 <= r.status_code < 500, f"{endpoint} template #{idx} returned {r.status_code}"
        assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
        assert email not in mgr.pending_guest_email_otps
        assert scanner.get(hs["post_scan_url"]).status_code == 403


def test_round5_escaped_json_and_raw_body_carriers_isolated_on_non_qr_routes_and_invalidate() -> None:
    """Any non-QR route (/, /app, /api/state, /api/device, /auth, /logs) receiving a QR credential
    encoded with \\uXXXX JSON escapes (even inside broken/1e309 JSON, UTF-16 BOM, %XX form, multipart,
    or duplicate headers) MUST return 403 and MUST invalidate any bound QR session.
    """
    mgr = get_auth_3layer_manager()
    non_qr_routes = ("/", "/app", "/api/state", "/api/device", "/auth", "/logs")

    for route in non_qr_routes:
        # 1. Unicode-escaped key & value + 1e309 in JSON body
        scanner1, hs1 = _handshake_pair()
        nonce1 = str(scanner1.cookies.get(QR_SCAN_COOKIE_NAME) or "")
        esc_k = _escape_json_u_all("scan_nonce", upper_every_other=True)
        esc_v = _escape_json_u_all(nonce1, upper_every_other=True)
        c1 = TestClient(app, raise_server_exceptions=False)
        r1 = c1.request(
            "POST" if route.startswith("/api/") else "GET",
            route,
            content=f'{{"{esc_k}":"{esc_v}","overflow":1e309}}'.encode("utf-8"),
            headers={"content-type": "application/json"},
            follow_redirects=False,
        )
        assert r1.status_code == 403, f"Route {route} allowed escaped+1e309 body: {r1.status_code}"
        assert mgr.guest_qr_sessions[hs1["session_id"]]["invalidated"] is True
        assert scanner1.get(hs1["post_scan_url"]).status_code == 403

        # 2. Truncated syntax-broken JSON carrying escaped post_scan_token + scan_nonce
        scanner2, hs2 = _handshake_pair()
        nonce2 = str(scanner2.cookies.get(QR_SCAN_COOKIE_NAME) or "")
        esc_pst = _escape_json_u_all(hs2["post_scan_token"])
        esc_n2 = _escape_json_u_all(nonce2)
        c2 = TestClient(app, raise_server_exceptions=False)
        r2 = c2.request(
            "GET",
            route,
            content=f'{{"post_scan_token":"{esc_pst}","scan_nonce":"{esc_n2}","broken":'.encode("utf-8"),
            headers={"content-type": "application/json"},
            follow_redirects=False,
        )
        assert r2.status_code == 403
        assert mgr.guest_qr_sessions[hs2["session_id"]]["invalidated"] is True

        # 3. Duplicate headers where first header is empty and second header carries scan_nonce
        scanner3, hs3 = _handshake_pair()
        nonce3 = str(scanner3.cookies.get(QR_SCAN_COOKIE_NAME) or "")
        c3 = TestClient(app, raise_server_exceptions=False)
        r3 = c3.get(
            route,
            headers=[("x-qr-scan-nonce", ""), ("x-qr-scan-nonce", nonce3)],
            follow_redirects=False,
        )
        assert r3.status_code == 403
        assert mgr.guest_qr_sessions[hs3["session_id"]]["invalidated"] is True


def test_round5_rfc8259_unescape_surrogates_404_405_and_third_party_anti_dos() -> None:
    """Verify RFC 8259 surrogate pairs, lone-surrogate crash safety (zero 500s), 404/405 error-path
    invalidation on /api/auth3/*, and anti-DoS guarantee (third party knowing only session_id cannot
    invalidate the real scanner's session by sending 1e309 without the valid scan_nonce).
    """
    from simulator.auth.qr_totp_mixin import (
        extract_tolerant_raw_body_pairs_and_strings,
        unescape_json_string_literal,
    )

    # 1. Unit verification of RFC 8259 unescaping (ASCII, Vietnamese, emoji surrogate pair, escapes, lone surrogate)
    original = 'nonce_việt_🔐_quote"_bs\\_tab\t_slash/'
    escaped = _escape_json_u_all(original, upper_every_other=True)
    assert unescape_json_string_literal(escaped) == original

    # Lone surrogate \ud800 must never crash or raise 500
    lone = unescape_json_string_literal(r"prefix_\ud800_suffix")
    assert lone.startswith("prefix_") and lone.endswith("_suffix")

    pairs, strs = extract_tolerant_raw_body_pairs_and_strings(
        raw_body=f'{{"{_escape_json_u_all("scan_nonce")}":"{escaped}","sample_index":1e309}}'.encode("utf-8"),
    )
    assert ("scan_nonce", original) in pairs
    assert original in strs

    c_surrogate = TestClient(app, raise_server_exceptions=False)
    r_lone = c_surrogate.post(
        "/api/auth3/guest_qr_complete_voice",
        content=b'{"session_id":"fake","scan_nonce":"\\ud800","sample_index":1e309}',
        headers={"content-type": "application/json"},
    )
    assert 400 <= r_lone.status_code < 500

    # 2. 405 Method Not Allowed & 404 Unknown /api/auth3/* subroute with escaped nonce invalidate bound session
    mgr = get_auth_3layer_manager()
    for method, bad_path in (
        ("DELETE", "/api/auth3/guest_qr_complete_voice"),
        ("POST", "/api/auth3/nonexistent_round5_probe"),
    ):
        scanner, hs = _handshake_pair()
        nonce = str(scanner.cookies.get(QR_SCAN_COOKIE_NAME) or "")
        esc_n = _escape_json_u_all(nonce)
        c_err = TestClient(app, raise_server_exceptions=False)
        r_err = c_err.request(
            method,
            bad_path,
            content=f'{{"scan_nonce":"{esc_n}","sample_index":1e309}}'.encode("utf-8"),
            headers={"content-type": "application/json"},
        )
        assert 400 <= r_err.status_code < 500
        assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
        assert scanner.get(hs["post_scan_url"]).status_code == 403

    # 3. Anti-DoS guarantee: attacker knowing ONLY session_id (no valid scan_nonce) sends 1e309 + forged escaped nonce
    scanner_real, hs_real = _handshake_pair()
    attacker = TestClient(app, raise_server_exceptions=False)
    forged_esc = _escape_json_u_all("forged_attacker_nonce_value_999")
    r_atk = attacker.post(
        "/api/auth3/guest_qr_complete_voice",
        content=f'{{"session_id":"{hs_real["session_id"]}","scan_nonce":"{forged_esc}","sample_index":1e309}}'.encode("utf-8"),
        headers={"content-type": "application/json"},
    )
    assert r_atk.status_code == 422
    assert mgr.guest_qr_sessions[hs_real["session_id"]]["invalidated"] is False
    assert scanner_real.get(hs_real["post_scan_url"]).status_code == 200


# =============================================================================
# FIX ROUND 6 REGRESSION TESTS (R5-N1, R5-N2, HARD 413 LIMITS & CHUNKED STREAMING)
# =============================================================================


@pytest.mark.parametrize(
    "kind",
    [
        "overflow",
        "overflow_total",
        "truncated",
        "wrong_method",
        "missing_email",
        "wrong_otp",
        "odd_quote_parity",
        "utf16le_bom_after_2mb",
    ],
)
def test_round6_r5_n1_nonce_after_2mb_stream_scanned_and_invalidated(kind: str) -> None:
    """R5-N1 Regression: Placing session_id and \\uXXXX-escaped scan_nonce after > 2,000,000 bytes
    (leading whitespace, JSON string padding, odd-quote parity shift, or UTF-16LE BOM) MUST never
    escape credential extraction: server rejects 4xx/413, atomically invalidates the scan session,
    purges pending OTP, kills post_scan_url (403), and blocks subsequent OTP verify.
    """
    from unittest.mock import patch
    from simulator.api import routes_qr
    from simulator.api.deps import _REST_ENGINE

    scanner, hs = _handshake_pair()
    nonce = str(scanner.cookies.get(QR_SCAN_COOKIE_NAME) or "")
    assert nonce
    mgr = get_auth_3layer_manager()
    c = TestClient(app, raise_server_exceptions=False)

    email = f"r6-n1-{kind}@example.invalid"
    guest_name = f"R6N1_{kind}"
    send_payload = {
        "session_id": hs["session_id"],
        "scan_nonce": nonce,
        "guest_name": guest_name,
        "email": email,
        "confirm_email": email,
    }
    with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no mail")):
        proof = c.post("/api/auth3/guest_qr_send_otp", json=send_payload)
    assert proof.status_code == 200
    saved_otp = mgr.pending_guest_email_otps[email]["otp"]

    esc_nonce = _escape_json_u_all(nonce, upper_every_other=True)
    pad_len = 2_000_100
    method = "POST"
    path = "/api/auth3/guest_qr_complete_voice"

    if kind == "overflow":
        raw_bytes = (
            " " * pad_len
            + f'{{"padding":"","session_id":{json.dumps(hs["session_id"])},"scan_nonce":"{esc_nonce}","sample_index":1e309}}'
        ).encode("utf-8")
    elif kind == "overflow_total":
        raw_bytes = (
            f'{{"padding":"{"x" * pad_len}","session_id":{json.dumps(hs["session_id"])},"scan_nonce":"{esc_nonce}","total_samples":1e309}}'
        ).encode("utf-8")
    elif kind == "truncated":
        raw_bytes = (
            f'{{"padding":"{"x" * pad_len}","session_id":{json.dumps(hs["session_id"])},"scan_nonce":"{esc_nonce}","broken":'
        ).encode("utf-8")
    elif kind == "wrong_method":
        method = "DELETE"
        raw_bytes = (
            " " * pad_len
            + f'{{"padding":"","session_id":{json.dumps(hs["session_id"])},"scan_nonce":"{esc_nonce}"}}'
        ).encode("utf-8")
    elif kind == "missing_email":
        path = "/api/auth3/guest_qr_send_otp"
        raw_bytes = (
            f'{{"padding":"{"x" * pad_len}","session_id":{json.dumps(hs["session_id"])},"scan_nonce":"{esc_nonce}"}}'
        ).encode("utf-8")
    elif kind == "wrong_otp":
        path = "/api/auth3/guest_qr_verify_otp"
        raw_bytes = (
            f'{{"padding":"{"x" * pad_len}","session_id":{json.dumps(hs["session_id"])},"scan_nonce":"{esc_nonce}","email":{json.dumps(email)},"otp":"000000"}}'
        ).encode("utf-8")
    elif kind == "odd_quote_parity":
        # Leading unclosed quote flips quote parity across every 64 KiB sliding window
        raw_bytes = (
            '"unclosed_quote_'
            + ("z" * pad_len)
            + f'","session_id":{json.dumps(hs["session_id"])},"scan_nonce":"{esc_nonce}"}}'
        ).encode("utf-8")
    else:
        # UTF-16LE BOM with > 2MB body (1,050,000 UTF-16 code units = 2,100,000+ bytes)
        u16_text = (
            " " * 1_050_000
            + f'{{"session_id":{json.dumps(hs["session_id"])},"scan_nonce":"{esc_nonce}","sample_index":1e309}}'
        )
        raw_bytes = b"\xff\xfe" + u16_text.encode("utf-16-le")

    assert len(raw_bytes) > 2_000_000
    bad_resp = c.request(
        method,
        path,
        content=raw_bytes,
        headers={"content-type": "application/json"},
        follow_redirects=False,
    )
    assert bad_resp.status_code == 413
    assert bad_resp.json().get("status") == "PAYLOAD_TOO_LARGE"
    assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
    assert email not in mgr.pending_guest_email_otps
    assert scanner.get(hs["post_scan_url"]).status_code == 403

    retry = c.post("/api/auth3/guest_qr_verify_otp", json={**send_payload, "otp": saved_otp})
    assert retry.status_code >= 400
    assert retry.json().get("verified") is False
    assert not any(v.get("name") == guest_name for v in _REST_ENGINE.users.values())


def test_round6_r5_n2_padded_get_head_options_bodies_fail_closed_and_isolate() -> None:
    """R5-N2 Regression:
    1. GET/HEAD/OPTIONS carrying a padded (> 2MB) or small body with QR credentials to /, /app, /api/state,
       /api/device, /auth, /logs MUST return 403 (route isolation) and MUST invalidate the bound session.
    2. GET/HEAD/OPTIONS carrying any body WITHOUT QR credentials MUST fail closed with 400 (small) or 413 (oversize),
       NEVER 200 OK.
    3. GET to /guest_enroll with scanner cookie AND an unexpected body MUST reject 400/413 and invalidate the session.
    """
    from unittest.mock import patch
    from simulator.api import routes_qr

    mgr = get_auth_3layer_manager()

    # 1. Padded > 2MB GET bodies carrying QR credentials to non-QR routes -> 403 + invalidated
    for route in ("/", "/app", "/api/state", "/api/device", "/auth", "/logs"):
        scanner, hs = _handshake_pair()
        nonce = str(scanner.cookies.get(QR_SCAN_COOKIE_NAME) or "")
        esc_nonce = _escape_json_u_all(nonce, upper_every_other=True)
        email = f"r6-get-{route.strip('/') or 'root'}-{hs['session_id'][-4:]}@example.invalid"
        with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no mail")):
            assert (
                scanner.post(
                    "/api/auth3/guest_qr_send_otp",
                    json={"session_id": hs["session_id"], "email": email, "confirm_email": email, "guest_name": "R6Get"},
                ).status_code
                == 200
            )

        padded_body = (
            '{"padding":"'
            + ("p" * 2_000_100)
            + f'","session_id":{json.dumps(hs["session_id"])},"scan_nonce":"{esc_nonce}"}}'
        ).encode("utf-8")
        c_fresh = TestClient(app, raise_server_exceptions=False)
        resp = c_fresh.request(
            "GET",
            route,
            content=padded_body,
            headers={"content-type": "application/json"},
            follow_redirects=False,
        )
        assert resp.status_code == 403, f"Padded GET on {route} returned {resp.status_code}"
        assert resp.json().get("status") == "QR_REGISTRATION_SESSION_ISOLATED"
        assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
        assert email not in mgr.pending_guest_email_otps
        assert scanner.get(hs["post_scan_url"]).status_code == 403

    # 2. Non-QR GET / HEAD / OPTIONS requests carrying small or oversize bodies -> fail closed (400 / 413, never 200)
    c_plain = TestClient(app, raise_server_exceptions=False)
    for method in ("GET", "HEAD", "OPTIONS"):
        for route in ("/", "/app", "/api/state", "/guest_enroll"):
            r_small = c_plain.request(
                method,
                route,
                content=b'{"unexpected":"body"}',
                headers={"content-type": "application/json"},
                follow_redirects=False,
            )
            assert r_small.status_code == 400, f"{method} {route} with body returned {r_small.status_code}"
        r_huge = c_plain.request(
            method,
            "/api/state",
            content=b" " * 2_000_100 + b"{}",
            headers={"content-type": "application/json"},
            follow_redirects=False,
        )
        assert r_huge.status_code == 413

    # 3. GET to /guest_enroll with valid scanner cookie + unexpected body -> 400 + session invalidated
    scanner_ge, hs_ge = _handshake_pair()
    r_ge_body = scanner_ge.request(
        "GET",
        hs_ge["post_scan_url"],
        content=b'{"unexpected":1}',
        headers={"content-type": "application/json"},
    )
    assert r_ge_body.status_code == 400
    assert mgr.guest_qr_sessions[hs_ge["session_id"]]["invalidated"] is True
    assert scanner_ge.get(hs_ge["post_scan_url"]).status_code == 403


def test_round6_hard_oversize_limits_413_and_anti_dos_preservation() -> None:
    """Verify per-route hard body size limits (64 KiB on JSON OTP/handshake/qr_generate; 1.5 MiB on voice),
    session invalidation when valid scan_nonce is anywhere in oversize body, positive voice compatibility
    below 1.5 MiB, and anti-DoS protection when attacker lacks valid scan_nonce.
    """
    from simulator.auth.qr_totp_mixin import MAX_HTTP_BODY_BYTES, MAX_QR_SMALL_JSON_BODY_BYTES

    mgr = get_auth_3layer_manager()

    # 1. > 64 KiB on small JSON QR endpoints -> 413 + invalidates bound session
    for small_ep in (
        "/api/auth3/guest_qr_handshake",
        "/api/auth3/guest_qr_send_otp",
        "/api/auth3/guest_qr_verify_otp",
        "/api/auth3/qr/generate",
    ):
        scanner, hs = _handshake_pair()
        nonce = str(scanner.cookies.get(QR_SCAN_COOKIE_NAME) or "")
        esc_nonce = _escape_json_u_all(nonce)
        over_64k = (
            '{"pad":"'
            + ("a" * (MAX_QR_SMALL_JSON_BODY_BYTES + 2048))
            + f'","session_id":"{hs["session_id"]}","scan_nonce":"{esc_nonce}"}}'
        ).encode("utf-8")
        c = TestClient(app, raise_server_exceptions=False)
        hdrs = {"content-type": "application/json"}
        if small_ep == "/api/auth3/qr/generate":
            hdrs["Authorization"] = "Bearer sess_owner_t1_nep94121"
        r = c.post(small_ep, content=over_64k, headers=hdrs)
        assert r.status_code == 413, f"{small_ep} did not return 413 on >64KB body: {r.status_code}"
        assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
        assert scanner.get(hs["post_scan_url"]).status_code == 403

    # 2. > 1.5 MiB (up to 4.2 MB) on voice endpoint with nonce at tail -> 413 + invalidates bound session
    scanner_v, hs_v = _handshake_pair()
    nonce_v = str(scanner_v.cookies.get(QR_SCAN_COOKIE_NAME) or "")
    over_voice = (
        '{"pad":"'
        + ("v" * (MAX_HTTP_BODY_BYTES + 600_000))
        + f'","session_id":"{hs_v["session_id"]}","scan_nonce":"{_escape_json_u_all(nonce_v)}"}}'
    ).encode("utf-8")
    c_v = TestClient(app, raise_server_exceptions=False)
    r_v = c_v.post("/api/auth3/guest_qr_complete_voice", content=over_voice, headers={"content-type": "application/json"})
    assert r_v.status_code == 413
    assert mgr.guest_qr_sessions[hs_v["session_id"]]["invalidated"] is True
    assert scanner_v.get(hs_v["post_scan_url"]).status_code == 403

    # 3. Anti-DoS: third party knowing ONLY session_id (no valid scan_nonce) sends 2.2 MB body -> 413/403, real session stays valid!
    scanner_keep, hs_keep = _handshake_pair()
    attacker = TestClient(app, raise_server_exceptions=False)
    atk_body = (
        '{"pad":"'
        + ("k" * 2_200_000)
        + f'","session_id":"{hs_keep["session_id"]}","scan_nonce":"forged_wrong_nonce_000000000"}}'
    ).encode("utf-8")
    r_atk_voice = attacker.post("/api/auth3/guest_qr_complete_voice", content=atk_body, headers={"content-type": "application/json"})
    assert r_atk_voice.status_code == 413
    r_atk_app = attacker.request("GET", "/app", content=atk_body, headers={"content-type": "application/json"})
    assert r_atk_app.status_code == 403
    assert mgr.guest_qr_sessions[hs_keep["session_id"]]["invalidated"] is False
    assert scanner_keep.get(hs_keep["post_scan_url"]).status_code == 200

    # Real scanner can still complete legitimate voice enrollment (< 1.5 MiB)
    audio_b64 = _generate_valid_guest_pcm_b64(f0=238.0, duration_sec=3.0)
    ok_voice = scanner_keep.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "session_id": hs_keep["session_id"],
            "post_scan_token": hs_keep["post_scan_token"],
            "guest_name": "Khách Hợp Lệ Sau AntiDoS",
            "duration": "1d",
            "audio_pcm_b64": audio_b64,
        },
    )
    assert ok_voice.status_code == 200
    assert ok_voice.json().get("ok") is True


def test_round6_chunked_transfer_encoding_split_boundary_and_malformed_framing() -> None:
    """Verify Transfer-Encoding: chunked streaming:
    1. Oversize (> 2.2 MiB) chunked POST where \\uXXXX scan_nonce is split across 7-byte chunk boundaries
       returns 413 and invalidates the bound session.
    2. Oversize (> 2.1 MiB) chunked GET to /, /app, /api/state with split credentials returns 403 and invalidates.
    3. Valid small chunked POST to /api/auth3/guest_qr_send_otp succeeds 200 OK.
    4. Malformed framing (conflicting Content-Length or CL + Transfer-Encoding) returns 400 and invalidates.
    """
    from unittest.mock import patch
    from simulator.api import routes_qr

    mgr = get_auth_3layer_manager()

    # 1. Chunked > 2.2 MiB POST with \uXXXX scan_nonce split across 7-byte chunks -> 413 + invalidated
    scanner1, hs1 = _handshake_pair()
    nonce1 = str(scanner1.cookies.get(QR_SCAN_COOKIE_NAME) or "")
    esc_nonce1 = _escape_json_u_all(nonce1, upper_every_other=True)
    email1 = "r6-chunked-voice@example.invalid"
    with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no mail")):
        assert (
            scanner1.post(
                "/api/auth3/guest_qr_send_otp",
                json={"session_id": hs1["session_id"], "email": email1, "confirm_email": email1, "guest_name": "R6Chunk1"},
            ).status_code
            == 200
        )

    tail_bytes = f'","session_id":"{hs1["session_id"]}","scan_nonce":"{esc_nonce1}","sample_index":1e309}}'.encode("utf-8")

    def _gen_oversize_split_chunks():
        yield b'{"padding":"'
        for _ in range(35):
            yield b"c" * 65_536
        # Split tail_bytes (including \uXXXX escapes) into tiny 7-byte chunks across boundaries
        for idx in range(0, len(tail_bytes), 7):
            yield tail_bytes[idx : idx + 7]

    c1 = TestClient(app, raise_server_exceptions=False)
    r_chunk_post = c1.post(
        "/api/auth3/guest_qr_complete_voice",
        content=_gen_oversize_split_chunks(),
        headers={"content-type": "application/json"},
    )
    assert r_chunk_post.status_code == 413
    assert mgr.guest_qr_sessions[hs1["session_id"]]["invalidated"] is True
    assert email1 not in mgr.pending_guest_email_otps
    assert scanner1.get(hs1["post_scan_url"]).status_code == 403

    # 2. Chunked > 2.1 MiB GET to /, /app, /api/state -> 403 + invalidated
    for route in ("/", "/app", "/api/state"):
        scanner2, hs2 = _handshake_pair()
        nonce2 = str(scanner2.cookies.get(QR_SCAN_COOKIE_NAME) or "")
        esc_n2 = _escape_json_u_all(nonce2)
        tail2 = f'","post_scan_token":"{hs2["post_scan_token"]}","scan_nonce":"{esc_n2}"}}'.encode("utf-8")

        def _gen_get_chunks(t_bytes: bytes = tail2):
            yield b'{"pad":"'
            for _ in range(33):
                yield b"g" * 65_536
            for idx in range(0, len(t_bytes), 9):
                yield t_bytes[idx : idx + 9]

        c2 = TestClient(app, raise_server_exceptions=False)
        r_chunk_get = c2.request(
            "GET",
            route,
            content=_gen_get_chunks(),
            headers={"content-type": "application/json"},
            follow_redirects=False,
        )
        assert r_chunk_get.status_code == 403
        assert mgr.guest_qr_sessions[hs2["session_id"]]["invalidated"] is True
        assert scanner2.get(hs2["post_scan_url"]).status_code == 403

    # 3. Valid small chunked POST to /api/auth3/guest_qr_send_otp -> 200 OK
    scanner3, hs3 = _handshake_pair()
    nonce3 = str(scanner3.cookies.get(QR_SCAN_COOKIE_NAME) or "")
    valid_small = json.dumps(
        {
            "session_id": hs3["session_id"],
            "scan_nonce": nonce3,
            "guest_name": "ChunkedSmallValid",
            "email": "r6-small-chunk@example.invalid",
            "confirm_email": "r6-small-chunk@example.invalid",
        }
    ).encode("utf-8")
    c3 = TestClient(app, raise_server_exceptions=False)
    with patch.object(routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no mail")):
        r_small_chunk = c3.post(
            "/api/auth3/guest_qr_send_otp",
            content=(valid_small[i : i + 11] for i in range(0, len(valid_small), 11)),
            headers={"content-type": "application/json"},
        )
    assert r_small_chunk.status_code == 200
    assert r_small_chunk.json().get("ok") is True

    # 4. Malformed HTTP framing (CL + Transfer-Encoding smuggling / invalid Content-Length) -> 400 + invalidated
    scanner4, hs4 = _handshake_pair()
    nonce4 = str(scanner4.cookies.get(QR_SCAN_COOKIE_NAME) or "")
    body4 = json.dumps({"session_id": hs4["session_id"], "scan_nonce": nonce4}).encode("utf-8")
    c4 = TestClient(app, raise_server_exceptions=False)
    r_smuggle = c4.post(
        "/api/auth3/guest_qr_complete_voice",
        content=body4,
        headers=[
            ("content-type", "application/json"),
            ("content-length", str(len(body4))),
            ("transfer-encoding", "chunked"),
        ],
    )
    assert r_smuggle.status_code == 400
    assert r_smuggle.json().get("status") == "MALFORMED_HTTP_FRAMING"
    assert mgr.guest_qr_sessions[hs4["session_id"]]["invalidated"] is True
    assert scanner4.get(hs4["post_scan_url"]).status_code == 403


# =============================================================================
# FIX ROUND 7 REGRESSION TESTS (R6-N1 LONG LITERAL, R6-N2 DEEP NESTING, R6-N3 34MB STREAM)
# =============================================================================


@pytest.mark.parametrize(
    "endpoint,spaces",
    [
        ("/api/auth3/guest_qr_complete_voice", 700),
        ("/api/auth3/guest_qr_send_otp", 700),
        ("/api/auth3/guest_qr_verify_otp", 700),
    ],
)
def test_round7_r6_n1_long_literal_escaped_nonce_requires_rescan(
    endpoint: str, spaces: int
) -> None:
    """R6-N1: Top-level body nonce written as a long literal (700 x \\u0020 escapes + escaped nonce)
    accepted as valid credential (proof 200), but when same body ends malformed (422) on voice/send-OTP/verify-OTP,
    session MUST be invalidated, pending OTP deleted, post-scan link 403, and retry verify rejected.
    """
    scanner, hs = _handshake_pair()
    nonce = str(scanner.cookies.get(QR_SCAN_COOKIE_NAME) or "")
    c = TestClient(app, raise_server_exceptions=False)
    mgr = get_auth_3layer_manager()
    name = "R7Literal_" + uuid.uuid4().hex[:8]
    email = "r7-literal@example.invalid"
    data = {
        "session_id": hs["session_id"],
        "guest_name": name,
        "email": email,
        "confirm_email": email,
    }
    literal = "\\u0020" * spaces + "".join("\\u%04x" % ord(ch) for ch in nonce)
    base = json.dumps(data)[:-1] + ',"scan_nonce":"' + literal + '"'
    with patch.object(
        routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no mail")
    ):
        proof = c.post(
            "/api/auth3/guest_qr_send_otp",
            content=base + "}",
            headers={"content-type": "application/json"},
        )
    assert proof.status_code == 200
    saved = mgr.pending_guest_email_otps[email]["otp"]
    raw = base + ',"broken":'
    bad = c.post(endpoint, content=raw, headers={"content-type": "application/json"})
    assert bad.status_code == 422
    assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
    assert email not in mgr.pending_guest_email_otps
    assert scanner.get(hs["post_scan_url"]).status_code == 403
    retry = c.post(
        "/api/auth3/guest_qr_verify_otp", json={**data, "scan_nonce": nonce, "otp": saved}
    )
    assert retry.status_code >= 400
    assert not retry.json().get("verified")
    assert not any(v.get("name") == name for v in _REST_ENGINE.users.values())


@pytest.mark.parametrize("depth", [64, 65, 80, 100])
def test_round7_r6_n2_deep_nested_nonce_requires_rescan(depth: int) -> None:
    """R6-N2: Nonce inside deeply nested JSON objects (>64 levels) must not lose invalidation
    when error occurs.
    """
    scanner, hs = _handshake_pair()
    nonce = str(scanner.cookies.get(QR_SCAN_COOKIE_NAME) or "")
    mgr = get_auth_3layer_manager()
    c = TestClient(app, raise_server_exceptions=False)
    name = "R7Depth_" + uuid.uuid4().hex[:8]
    email = "r7-depth@example.invalid"
    data = {
        "session_id": hs["session_id"],
        "scan_nonce": nonce,
        "guest_name": name,
        "email": email,
        "confirm_email": email,
    }
    with patch.object(
        routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no mail")
    ):
        proof = c.post("/api/auth3/guest_qr_send_otp", json=data)
    assert proof.status_code == 200
    saved = mgr.pending_guest_email_otps[email]["otp"]
    nested = {"scan_nonce": nonce}
    for _ in range(depth):
        nested = {"n": nested}
    raw = (
        json.dumps({"session_id": hs["session_id"], "nested": nested})[:-1]
        + ',"sample_index":1e309}'
    )
    bad = c.post(
        "/api/auth3/guest_qr_complete_voice",
        content=raw,
        headers={"content-type": "application/json"},
    )
    assert 400 <= bad.status_code < 500
    assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
    assert email not in mgr.pending_guest_email_otps
    assert scanner.get(hs["post_scan_url"]).status_code == 403
    retry = c.post(
        "/api/auth3/guest_qr_verify_otp", json={**data, "otp": saved}
    )
    assert retry.status_code >= 400
    assert not retry.json().get("verified")
    assert not any(v.get("name") == name for v in _REST_ENGINE.users.values())


@pytest.mark.parametrize(
    "padding,chunk_size",
    [(34 * 1024 * 1024, 65536), (34 * 1024 * 1024, 40 * 1024 * 1024)],
)
def test_round7_r6_n3_stream_34mb_requires_rescan(
    padding: int, chunk_size: int
) -> None:
    """R6-N3: Stream exceeding 32 MiB with tail credentials must be scanned within the 80 MiB stream
    scan window, returning 413 and invalidating the bound QR session.
    """
    import asyncio, httpx

    scanner, hs = _handshake_pair()
    nonce = str(scanner.cookies.get(QR_SCAN_COOKIE_NAME) or "")
    c = TestClient(app, raise_server_exceptions=False)
    mgr = get_auth_3layer_manager()
    name = "R7Stream_" + uuid.uuid4().hex[:8]
    email = "r7-stream@example.invalid"
    data = {
        "session_id": hs["session_id"],
        "scan_nonce": nonce,
        "guest_name": name,
        "email": email,
        "confirm_email": email,
    }
    with patch.object(
        routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no mail")
    ):
        proof = c.post("/api/auth3/guest_qr_send_otp", json=data)
    assert proof.status_code == 200
    saved = mgr.pending_guest_email_otps[email]["otp"]
    esc = "".join("\\u%04x" % ord(ch) for ch in nonce)
    tail = (
        '{"session_id":'
        + json.dumps(hs["session_id"])
        + ',"scan_nonce":"'
        + esc
        + '","sample_index":1e309}'
    ).encode()

    async def chunks():
        remaining = padding
        while remaining:
            size = min(remaining, chunk_size)
            remaining -= size
            yield b" " * size
        yield tail

    async def send():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as ac:
            return await ac.post(
                "/api/auth3/guest_qr_complete_voice",
                content=chunks(),
                headers={"content-type": "application/json"},
            )

    bad = asyncio.run(send())
    assert bad.status_code == 413
    assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
    assert email not in mgr.pending_guest_email_otps
    assert scanner.get(hs["post_scan_url"]).status_code == 403
    retry = c.post(
        "/api/auth3/guest_qr_verify_otp", json={**data, "otp": saved}
    )
    assert retry.status_code >= 400
    assert not retry.json().get("verified")
    assert not any(v.get("name") == name for v in _REST_ENGINE.users.values())


# =============================================================================
# FIX ROUND 8 REGRESSION TESTS (R7-N1 11_000 ESCAPES, R7-N2 82 MiB STREAM)
# =============================================================================



def test_round8_streaming_scanner_recovers_nonce_split_across_64kib() -> None:
    """Máy trạng thái phải ghép scan_nonce bị cắt đúng giữa literal 66 KiB (mốc 64 KiB)."""
    from simulator.auth.qr_totp_mixin import _StreamingQrCredentialScanner

    nonce = "scanNonceValue_R8_split_abcXYZ"
    literal = "\\u0020" * 11000 + "".join("\\u%04x" % ord(ch) for ch in nonce)
    raw = (
        '{"session_id":"guest_sess_dummy","scan_nonce":"' + literal + '","broken":'
    ).encode("utf-8")
    assert len(raw) > 65_536
    sc = _StreamingQrCredentialScanner()
    sc.feed_bytes(raw[:65_536])
    sc.feed_bytes(raw[65_536:])
    sc.finish()
    pairs, strings = sc.drain_pairs_and_strings()
    assert ("session_id", "guest_sess_dummy") in pairs
    assert ("scan_nonce", nonce) in pairs
    assert nonce in strings


def test_round8_extract_11000_escaped_spaces_from_truncated_json() -> None:
    """Bộ quét khoan dung phải khôi phục scan_nonce sau 11.000 escape \\u0020 trong JSON cắt cụt (~66 KiB)."""
    from simulator.auth.qr_totp_mixin import extract_tolerant_raw_body_pairs_and_strings

    nonce = "scanNonceValue_R8_11000_abcXYZ"
    literal = "\\u0020" * 11000 + "".join("\\u%04x" % ord(ch) for ch in nonce)
    raw = (
        '{"session_id":"guest_sess_dummy","scan_nonce":"' + literal + '","broken":'
    ).encode("utf-8")
    assert len(raw) > 65_536
    pairs, strings = extract_tolerant_raw_body_pairs_and_strings(raw_body=raw)
    assert ("scan_nonce", nonce) in pairs
    assert nonce in strings


@pytest.mark.parametrize(
    "endpoint,spaces",
    [
        ("/api/auth3/guest_qr_complete_voice", 11000),
        ("/api/auth3/guest_qr_send_otp", 11000),
        ("/api/auth3/guest_qr_verify_otp", 11000),
    ],
)
def test_round8_r7_n1_11000_escaped_spaces_malformed_requires_rescan(
    endpoint: str, spaces: int
) -> None:
    """R7-N1: Biểu diễn scan_nonce bằng ~11.000 escape \\u0020 vẫn được API chấp nhận (proof 200),
    nhưng JSON cắt cụt (~66 KB, dưới trần body voice 1,5 MiB) phải 422, hủy phiên, xóa OTP,
    link cũ 403, verify cũ bị từ chối, không thêm khách.
    """
    scanner, hs = _handshake_pair()
    nonce = str(scanner.cookies.get(QR_SCAN_COOKIE_NAME) or "")
    c = TestClient(app, raise_server_exceptions=False)
    mgr = get_auth_3layer_manager()
    name = "R8Literal_" + uuid.uuid4().hex[:8]
    email = "r8-literal@example.invalid"
    data = {
        "session_id": hs["session_id"],
        "guest_name": name,
        "email": email,
        "confirm_email": email,
    }
    literal = "\\u0020" * spaces + "".join("\\u%04x" % ord(ch) for ch in nonce)
    base = json.dumps(data)[:-1] + ',"scan_nonce":"' + literal + '"'
    with patch.object(
        routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no mail")
    ):
        proof = c.post(
            "/api/auth3/guest_qr_send_otp",
            json={**data, "scan_nonce": nonce},
        )
    assert proof.status_code == 200
    saved = mgr.pending_guest_email_otps[email]["otp"]
    proof_raw = (
        base
        + ',"verify_only":true,"audio_pcm_b64":'
        + json.dumps(_generate_valid_guest_pcm_b64(f0=240.0))
        + "}"
    )
    voice_proof = c.post(
        "/api/auth3/guest_qr_complete_voice",
        content=proof_raw,
        headers={"content-type": "application/json"},
    )
    assert voice_proof.status_code == 200
    raw = base + ',"broken":'
    assert len(raw.encode("utf-8")) > 65_536
    bad = c.post(endpoint, content=raw, headers={"content-type": "application/json"})
    # Voice cho phep toi 1.5 MiB (422 JSON gay); send_otp/verify_otp tran 64 KiB nen 413. Ca hai deu phai huy phien.
    if endpoint.rstrip('/').endswith('guest_qr_complete_voice'):
        assert bad.status_code == 422
    else:
        assert bad.status_code == 413
    assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
    assert email not in mgr.pending_guest_email_otps
    assert scanner.get(hs["post_scan_url"]).status_code == 403
    retry = c.post(
        "/api/auth3/guest_qr_verify_otp", json={**data, "scan_nonce": nonce, "otp": saved}
    )
    assert retry.status_code >= 400
    assert not retry.json().get("verified")
    assert not any(v.get("name") == name for v in _REST_ENGINE.users.values())


@pytest.mark.parametrize(
    "padding,chunk_size",
    [
        (82 * 1024 * 1024, 65536),
        (82 * 1024 * 1024, 90 * 1024 * 1024),
    ],
)
def test_round8_r7_n2_stream_82mb_requires_rescan(
    padding: int, chunk_size: int
) -> None:
    """R7-N2: Padding 82 MiB (chunk 64 KiB, hoặc một chunk lớn rồi credential ở chunk sau)
    phải trả 413 và hủy phiên; không được coi trần quét luồng là lối thoát.
    """
    import asyncio
    import httpx

    scanner, hs = _handshake_pair()
    nonce = str(scanner.cookies.get(QR_SCAN_COOKIE_NAME) or "")
    c = TestClient(app, raise_server_exceptions=False)
    mgr = get_auth_3layer_manager()
    name = "R8Stream_" + uuid.uuid4().hex[:8]
    email = "r8-stream@example.invalid"
    data = {
        "session_id": hs["session_id"],
        "scan_nonce": nonce,
        "guest_name": name,
        "email": email,
        "confirm_email": email,
    }
    with patch.object(
        routes_qr, "validate_dns_mx_record", return_value=(True, "mocked; no mail")
    ):
        proof = c.post("/api/auth3/guest_qr_send_otp", json=data)
    assert proof.status_code == 200
    saved = mgr.pending_guest_email_otps[email]["otp"]
    esc = "".join("\\u%04x" % ord(ch) for ch in nonce)
    tail = (
        '{"session_id":'
        + json.dumps(hs["session_id"])
        + ',"scan_nonce":"'
        + esc
        + '","sample_index":1e309}'
    ).encode()

    async def chunks():
        remaining = padding
        while remaining:
            size = min(remaining, chunk_size)
            remaining -= size
            yield b" " * size
        yield tail

    async def send():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as ac:
            return await ac.post(
                "/api/auth3/guest_qr_complete_voice",
                content=chunks(),
                headers={"content-type": "application/json"},
            )

    bad = asyncio.run(send())
    assert bad.status_code == 413
    assert mgr.guest_qr_sessions[hs["session_id"]]["invalidated"] is True
    assert email not in mgr.pending_guest_email_otps
    assert scanner.get(hs["post_scan_url"]).status_code == 403
    retry = c.post("/api/auth3/guest_qr_verify_otp", json={**data, "otp": saved})
    assert retry.status_code >= 400
    assert not retry.json().get("verified")
    assert not any(v.get("name") == name for v in _REST_ENGINE.users.values())






