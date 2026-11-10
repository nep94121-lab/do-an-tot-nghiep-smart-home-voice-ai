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
import pathlib
import re
import sys
import threading
import time
import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.auth.qr_totp_mixin import QR_SCAN_COOKIE_NAME, QR_SESSION_COOKIE_NAME
from simulator.auth_3layer import get_auth_3layer_manager
from simulator.server import _BOOT_VOICE_AUTH, app


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


