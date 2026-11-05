"""Router Xác Thực 3 Tầng, Email Allowlist, Google OAuth & Sinh Trắc Học Giọng Nói (Feature 14 & 16).

Chức năng:
- Quản lý quy trình xác thực 3 tầng (Lớp 1: PBKDF2/PIN, Lớp 2: OTP Gmail, Lớp 3: DSP 256D).
- Quản lý danh sách email gia đình (Email Allowlist) có phân cấp C1/C2/C3.
- Khắc phục triệt để lỗi 404 qua các Route Aliases:
  + /api/auth3/family_allowlist/add <-> /api/auth3/add_family_email
  + /api/auth3/run_test_suite <-> /api/auth3/run_tests
"""

from __future__ import annotations

import base64
import copy
import wave
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from simulator.api.deps import (
    AUDIO_DIR,
    _ACTIVE_BRIDGES,
    _BOOT_VOICE_AUTH,
    _REST_ENGINE,
    broadcast_rest_state_to_bridges,
)
from simulator.auth.session_store import get_session_store
from simulator.auth_3layer import get_auth_3layer_manager
from simulator.live.gemini_bridge import VOICE_SAMPLES_META
from simulator.rule_engine import append_audit_log
from simulator.voice_config import (
    OWNER_EMAIL,
    OWNER_ID,
    ROLE_MAP,
    THRESHOLD_DEEP,
    THRESHOLD_MEL,
    USER_ROLE_MAP,
    sanitize_api_payload,
)

router = APIRouter(tags=["auth"])


@router.get("/api/auth3/overview")
async def api_auth3_overview(email: str = OWNER_EMAIL) -> JSONResponse:
    """Tổng quan trạng thái phân quyền và tài khoản."""
    return JSONResponse(sanitize_api_payload(get_auth_3layer_manager().get_overview(active_email=email)))


@router.get("/api/auth3/invite_links")
async def api_auth3_invite_links(email: str = OWNER_EMAIL) -> JSONResponse:
    """Danh sách link mời còn hiệu lực."""
    return JSONResponse(sanitize_api_payload(get_auth_3layer_manager().get_invite_links_for_account(email)))


@router.post("/api/auth3/send_invite_email")
async def api_auth3_send_invite_email(payload: dict[str, Any]) -> JSONResponse:
    """Gửi link mời qua Gmail thực tế."""
    invite_code = str(payload.get("invite_code", "INV-T1-TO-TIER2")).strip()
    recipient_email = str(payload.get("recipient_email", OWNER_EMAIL)).strip()
    res = get_auth_3layer_manager().send_invite_link_via_gmail(
        invite_code=invite_code,
        recipient_email=recipient_email,
        source="Web Portal (/auth)",
    )
    return JSONResponse(sanitize_api_payload(res))


@router.post("/api/auth3/create_invite_link")
async def api_auth3_create_invite_link(payload: dict[str, Any]) -> JSONResponse:
    """Tạo link mời theo phân quyền."""
    issuer_email = str(payload.get("issuer_email", OWNER_EMAIL)).strip()
    target_tier = int(payload.get("target_tier", 2) or 2)
    source = str(payload.get("source", "Web/App")).strip()
    res = get_auth_3layer_manager().create_custom_invite_link(
        issuer_identifier=issuer_email,
        target_tier=target_tier,
        source=source,
    )
    append_audit_log(
        category="AUTH_3LAYER",
        event_type="create_invite_link",
        summary=res.get("message") or res.get("error") or "Tạo link mời phân cấp",
        user_name=issuer_email,
        tier=target_tier if res.get("ok") else 99,
        details=res,
    )
    return JSONResponse(sanitize_api_payload(res))


@router.post("/api/auth3/add_family_email")
@router.post("/api/auth3/family_allowlist/add")
async def api_auth3_add_family_email(payload: dict[str, Any]) -> JSONResponse:
    """Thêm email vào allowlist gia đình (Hỗ trợ alias chống 404)."""
    actor_id = str(payload.get("actor_id") or payload.get("actor_email") or payload.get("issuer_email") or "").strip()
    if not actor_id:
        err_res = {"ok": False, "status_code": 401, "error": "Thiếu thông tin người thêm (actor_id)"}
        append_audit_log(
            category="AUTH_3LAYER",
            event_type="add_family_email_unauthorized",
            summary="Thiếu thông tin người thêm (actor_id)",
            user_name="ANONYMOUS",
            tier=99,
            details=err_res,
        )
        return JSONResponse(sanitize_api_payload(err_res), status_code=401)
    target_email = str(payload.get("target_email", "")).strip()
    target_tier = int(payload.get("target_tier", 2) or 2)
    source = str(payload.get("source", "Web/App")).strip()
    res = get_auth_3layer_manager().add_family_email(
        actor_id=actor_id,
        target_email=target_email,
        target_tier=target_tier,
        source=source,
    )
    append_audit_log(
        category="AUTH_3LAYER",
        event_type="add_family_email",
        summary=res.get("message") or res.get("error") or "Thêm Email Gia Đình (Email Allowlist)",
        user_name=actor_id,
        tier=target_tier if res.get("ok") else 99,
        details=res,
    )
    if not res.get("ok"):
        status_code = int(res.get("status_code", 403))
        return JSONResponse(sanitize_api_payload(res), status_code=status_code)
    return JSONResponse(sanitize_api_payload(res), status_code=200)


@router.get("/api/auth3/family_emails")
async def api_auth3_family_emails() -> JSONResponse:
    """Danh sách email gia đình trong allowlist."""
    return JSONResponse(sanitize_api_payload({
        "ok": True,
        "allowlist": get_auth_3layer_manager().get_family_email_allowlist(),
    }))


@router.post("/api/auth3/invite_oauth_start")
async def api_auth3_invite_oauth_start(payload: dict[str, Any]) -> JSONResponse:
    """Đăng ký qua link mời và Google OAuth."""
    invite_code = str(payload.get("invite_code", "INV-T1-TO-TIER2")).strip()
    google_email = str(payload.get("google_email", "")).strip()
    display_name = str(payload.get("display_name", "")).strip()
    custom_password = str(payload.get("custom_password", "")).strip()
    send_gmail = bool(payload.get("send_gmail", True))
    source = str(payload.get("source", "Web Invite Link")).strip()
    res = get_auth_3layer_manager().start_invite_oauth_registration(
        invite_code=invite_code,
        google_email=google_email,
        display_name=display_name,
        custom_password=custom_password,
        send_gmail=send_gmail,
        source=source,
    )
    append_audit_log(
        category="AUTH_3LAYER",
        event_type="invite_oauth_start",
        summary=res.get("message") or res.get("error") or "Đăng ký qua Link mời + Google OAuth",
        user_name=google_email or display_name,
        tier=int(res.get("target_tier", 2)) if res.get("ok") else 99,
        details=res,
    )
    return JSONResponse(sanitize_api_payload(res))


@router.post("/api/auth3/invite_verify_otp")
async def api_auth3_invite_verify_otp(payload: dict[str, Any]) -> JSONResponse:
    """Xác nhận mã OTP từ link mời và tạo tài khoản."""
    email = str(payload.get("email", "")).strip()
    otp_code = str(payload.get("otp_code", "")).strip()
    source = str(payload.get("source", "Web Invite Link")).strip()
    res = get_auth_3layer_manager().verify_invite_otp_and_create_account(
        email=email,
        otp_input=otp_code,
        source=source,
    )
    if res.get("ok") and res.get("account"):
        acc = res["account"]
        await _REST_ENGINE.grant_user_permission(target_name=acc["display_name"], target_tier=int(acc["tier"]))
        await broadcast_rest_state_to_bridges()
    append_audit_log(
        category="AUTH_3LAYER",
        event_type="invite_verify_otp",
        summary=res.get("message") or res.get("error") or "Xác nhận OTP đăng ký Link mời",
        user_name=email,
        tier=int(res.get("account", {}).get("tier", 2)) if res.get("ok") else 99,
        details=res,
    )
    return JSONResponse(sanitize_api_payload(res))


@router.post("/api/auth3/read_gmail_otp")
async def api_auth3_read_gmail_otp(payload: dict[str, Any] | None = None) -> JSONResponse:
    """Đọc mã OTP mới nhất từ hộp thư Gmail qua công cụ gws."""
    msg_id = str((payload or {}).get("message_id", "")).strip()
    res = get_auth_3layer_manager().read_latest_otp_from_gmail_inbox(message_id=msg_id)
    return JSONResponse(sanitize_api_payload(res))


@router.post("/api/auth3/enroll_first_page_voice")
async def api_auth3_enroll_first_page_voice(payload: dict[str, Any]) -> JSONResponse:
    """Thu âm giọng nói câu mẫu trang đầu."""
    from simulator.voice.stt_pipeline import decode_audio_bytes_to_pcm16k

    email = str(payload.get("email", "")).strip()
    spoken_text = str(payload.get("spoken_text", "")).strip()
    pcm16k_b64 = str(
        payload.get("pcm16k_b64")
        or payload.get("audio_pcm_b64")
        or payload.get("wav_b64")
        or payload.get("audio_b64")
        or ""
    ).strip()
    f0_raw = payload.get("measured_f0_hz")
    measured_f0_hz = float(f0_raw) if f0_raw is not None else None
    hold_duration_sec = float(payload.get("hold_duration_sec", 3.2) or 3.2)
    source_device = str(payload.get("source_device", "Trang Đầu (Nhấn & Giữ Thu Âm)")).strip()
    pcm_bytes = b""
    if pcm16k_b64:
        try:
            raw_decoded = base64.b64decode(pcm16k_b64)
            if len(raw_decoded) >= 44 and raw_decoded[:4] == b"RIFF":
                pcm_arr, _ = decode_audio_bytes_to_pcm16k(raw_decoded)
                pcm_bytes = pcm_arr.astype("int16").tobytes()
                pcm16k_b64 = base64.b64encode(pcm_bytes).decode("ascii")
            else:
                pcm_bytes = raw_decoded
        except Exception:
            pcm_bytes = b""

    if len(pcm_bytes) < 640:
        return JSONResponse(
            sanitize_api_payload(
                {
                    "ok": False,
                    "status": "CHUA_DAT",
                    "error": "Thiếu dữ liệu âm thanh PCM 16kHz thực tế để đăng ký giọng nói!",
                }
            ),
            status_code=400,
        )

    mgr3 = get_auth_3layer_manager()
    acc_pre = mgr3.find_account(email)
    pre_tier = int((acc_pre or {}).get("tier", 2))
    pre_uid = str((acc_pre or {}).get("account_id", ""))

    if pcm_bytes:
        dup_res = _BOOT_VOICE_AUTH.check_duplicate_voice_gate(
            pcm_bytes, f0_hz=measured_f0_hz, target_tier=pre_tier, target_user_id=pre_uid
        )
        if dup_res.is_duplicate:
            return JSONResponse(
                sanitize_api_payload(
                    {
                        "ok": False,
                        "status": "DUPLICATE_VOICE_REJECTED",
                        "reason": dup_res.reason,
                        "error": dup_res.message,
                        "message": dup_res.message,
                        "matched_tier": dup_res.matched_tier,
                        "matched_name": dup_res.matched_name,
                    }
                ),
                status_code=400,
            )

    res = mgr3.complete_first_page_voice_enrollment(
        email=email,
        spoken_text=spoken_text,
        pcm16k_b64=pcm16k_b64,
        measured_f0_hz=measured_f0_hz,
        hold_duration_sec=hold_duration_sec,
        source_device=source_device,
    )
    append_audit_log(
        category="AUTH_3LAYER",
        event_type="enroll_first_page_voice",
        summary=res.get("message") or res.get("error") or "Thu âm câu mẫu trang đầu",
        user_name=email,
        tier=int(res.get("account", {}).get("tier", 2)) if res.get("ok") else 99,
        details=res,
    )
    if res.get("ok") and res.get("account"):
        acc = res["account"]
        uid = str(acc.get("account_id", "thanh_vien_a"))
        uname = str(acc.get("display_name", uid))
        utier = int(acc.get("tier", 2))
        urole = str(acc.get("role", ROLE_MAP.get(utier, "MEMBER")))
        v_an = _BOOT_VOICE_AUTH.analyze_voice_pcm16k(pcm_bytes)
        f0_v = float(v_an.get("f0_hz") or res.get("voiceprint", {}).get("f0_mean_hz", measured_f0_hz or 190.0))
        c_v = float(v_an.get("centroid_hz") or res.get("voiceprint", {}).get("centroid_hz", f0_v * 9.5))
        emb_vec = v_an.get("embedding", [0.1] * 26)
        form_vec = v_an.get("formants_hz")
        deep_vec = v_an.get("deep_embedding")
        _BOOT_VOICE_AUTH.register_enrolled_user_profile(
            user_id=uid,
            user_name=uname,
            tier=utier,
            role=urole,
            f0_hz=f0_v,
            centroid_hz=c_v,
            embedding=emb_vec,
            formants_hz=form_vec,
            deep_embedding=deep_vec,
        )
        for br in list(_ACTIVE_BRIDGES):
            br.voice_auth.profiles = copy.deepcopy(_BOOT_VOICE_AUTH.profiles)
    return JSONResponse(sanitize_api_payload(res))


@router.post("/api/auth3/enroll_voice_sample")
async def api_auth3_enroll_voice_sample(payload: dict[str, Any]) -> JSONResponse:
    """Kiểm định chất lượng và thu âm mẫu giọng chính."""
    email = str(payload.get("email", "")).strip()
    speaker_name = str(payload.get("speaker_name") or payload.get("display_name") or "").strip()
    raw_tier = payload.get("target_tier", payload.get("tier"))
    target_tier = None
    if raw_tier is not None and str(raw_tier).strip() != "":
        try:
            target_tier = int(raw_tier)
        except (ValueError, TypeError):
            target_tier = None

    from simulator.voice.stt_pipeline import decode_audio_bytes_to_pcm16k

    pcm16k_b64 = str(
        payload.get("audio_pcm_b64")
        or payload.get("pcm16k_b64")
        or payload.get("wav_b64")
        or payload.get("audio_b64")
        or payload.get("audio_base64")
        or ""
    ).strip()
    source_device = str(payload.get("source_device", "Thu Âm Giọng Chính")).strip()
    try:
        raw_decoded = base64.b64decode(pcm16k_b64) if pcm16k_b64 else b""
        if len(raw_decoded) >= 44 and raw_decoded[:4] == b"RIFF":
            pcm_arr, _ = decode_audio_bytes_to_pcm16k(raw_decoded)
            pcm_bytes = pcm_arr.astype("int16").tobytes()
        else:
            pcm_bytes = raw_decoded
    except Exception:
        pcm_bytes = b""

    if len(pcm_bytes) < 640:
        return JSONResponse(
            sanitize_api_payload(
                {
                    "ok": False,
                    "status": "CHUA_DAT",
                    "error": "Thiếu dữ liệu âm thanh PCM 16kHz thực tế!",
                }
            ),
            status_code=400,
        )

    mgr3 = get_auth_3layer_manager()
    if speaker_name or target_tier is not None:
        upserted = mgr3.upsert_speaker_account_for_voice(
            email=email,
            speaker_name=speaker_name,
            target_tier=target_tier if target_tier is not None else 2,
        )
        if upserted and upserted.get("email"):
            email = str(upserted["email"])

    acc_pre = mgr3.find_account(email)
    pre_tier = int((acc_pre or {}).get("tier", 2))
    pre_uid = str((acc_pre or {}).get("account_id", ""))

    if pcm_bytes:
        dup_res = _BOOT_VOICE_AUTH.check_duplicate_voice_gate(
            pcm_bytes, target_tier=pre_tier, target_user_id=pre_uid
        )
        if dup_res.is_duplicate:
            return JSONResponse(
                sanitize_api_payload(
                    {
                        "ok": False,
                        "status": "DUPLICATE_VOICE_REJECTED",
                        "reason": dup_res.reason,
                        "error": dup_res.message,
                        "message": dup_res.message,
                        "matched_tier": dup_res.matched_tier,
                        "matched_name": dup_res.matched_name,
                    }
                ),
                status_code=400,
            )

    res = mgr3.validate_and_enroll_voice(
        email=email,
        pcm_bytes=pcm_bytes,
        source_device=source_device,
    )
    append_audit_log(
        category="AUTH_3LAYER",
        event_type="enroll_voice_sample",
        summary=res.get("message") or res.get("reason") or "Kiểm định và thu âm mẫu giọng chính",
        user_name=email,
        tier=int(res.get("account", {}).get("tier", 2)) if res.get("ok") else 99,
        details=res,
    )
    if res.get("ok") and res.get("status") == "DA_DAT" and res.get("account"):
        acc = res["account"]
        uid = str(acc.get("account_id", "member"))
        uname = str(acc.get("display_name", uid))
        utier = int(acc.get("tier", 2))
        urole = str(acc.get("role", ROLE_MAP.get(utier, "MEMBER")))
        _BOOT_VOICE_AUTH.enroll_tier_voice_from_pcm16k(
            pcm_bytes=pcm_bytes,
            user_id=uid,
            user_name=uname,
            tier=utier,
            role=urole,
            check_duplicate=True,
        )
        for br in list(_ACTIVE_BRIDGES):
            br.voice_auth.profiles = copy.deepcopy(_BOOT_VOICE_AUTH.profiles)
    return JSONResponse(sanitize_api_payload(res), status_code=200)


@router.post("/api/mobile/enroll_voice")
async def api_mobile_enroll_voice(payload: dict[str, Any]) -> JSONResponse:
    """Thu âm & đăng ký mẫu giọng từ App Android."""
    target_name = str(payload.get("target_name", "Thành viên mới")).strip()
    target_tier = int(payload.get("target_tier", 2) or 2)
    f0_hz = float(payload.get("f0_hz", 195.0) or 195.0)
    email = str(payload.get("email", "")).strip()
    password = str(payload.get("password", "")).strip()
    res = await _REST_ENGINE.grant_user_permission(target_name=target_name, target_tier=target_tier)
    auth_mgr = get_auth_3layer_manager()
    auth_res = auth_mgr.recognize_or_enroll_voice_from_device(
        mode="enroll",
        measured_f0_hz=f0_hz,
        email=email,
        target_name=target_name,
        target_tier=target_tier,
        password=password,
        source_device=str(payload.get("source_device", "Samsung Galaxy S9 (App Android)")),
    )
    append_audit_log(
        category="VOICE_AUTH",
        event_type="mobile_voice_enrolled",
        summary=f"🎙️ [App Android] Đã thu âm & đăng ký mẫu giọng '{target_name}' (Tầng {target_tier}, F0={f0_hz:.1f}Hz)",
        user_name="Nguyễn Tuấn Anh (Admin Cấp 1)",
        tier=1,
        details={"target_name": target_name, "target_tier": target_tier, "f0_hz": f0_hz, "result": res, "auth3": auth_res},
    )
    await broadcast_rest_state_to_bridges()
    return JSONResponse(sanitize_api_payload({"ok": True, "f0_hz": f0_hz, "result": res, "auth3": auth_res}))


@router.get("/api/voice_auth/profiles")
async def api_voice_auth_profiles() -> JSONResponse:
    """Danh sách hồ sơ giọng nói gốc trên Server."""
    active_va = _ACTIVE_BRIDGES[-1].voice_auth if _ACTIVE_BRIDGES else _BOOT_VOICE_AUTH
    return JSONResponse(sanitize_api_payload({
        "ok": True,
        "profiles": active_va.profiles,
        "last_analysis": active_va.last_analysis,
    }))


@router.post("/api/voice_auth/enroll_tier_pcm")
@router.post("/api/voice_enroll")
@router.post("/api/voice/enroll")
async def api_voice_auth_enroll_tier_pcm(payload: dict[str, Any]) -> JSONResponse:
    """Thu âm giọng nói thật 16kHz PCM hoặc WAV từ mic/file lưu làm profile server."""
    from simulator.voice.stt_pipeline import decode_audio_bytes_to_pcm16k

    b64_pcm = str(
        payload.get("pcm16k_b64")
        or payload.get("wav_b64")
        or payload.get("audio_b64")
        or payload.get("audio_pcm_b64")
        or ""
    ).strip()
    user_id = str(payload.get("user_id", OWNER_ID)).strip()
    user_name = str(payload.get("user_name", "Nguyễn Tuấn Anh")).strip()
    tier = int(payload.get("tier") or payload.get("level") or 1)
    role = ROLE_MAP.get(tier, "CHILD_GUEST")
    try:
        raw_decoded = base64.b64decode(b64_pcm) if b64_pcm else b""
        if len(raw_decoded) >= 44 and raw_decoded[:4] == b"RIFF":
            pcm_arr, _ = decode_audio_bytes_to_pcm16k(raw_decoded)
            pcm_bytes = pcm_arr.astype("int16").tobytes()
        else:
            pcm_bytes = raw_decoded
    except Exception:
        pcm_bytes = b""

    if len(pcm_bytes) < 640:
        return JSONResponse(
            sanitize_api_payload(
                {
                    "ok": False,
                    "status": "CHUA_DAT",
                    "error": "Thiếu dữ liệu âm thanh PCM 16kHz thực tế!",
                }
            ),
            status_code=400,
        )

    res = _BOOT_VOICE_AUTH.enroll_tier_voice_from_pcm16k(
        pcm_bytes=pcm_bytes,
        user_id=user_id,
        user_name=user_name,
        tier=tier,
        role=role,
        check_duplicate=True,
    )
    if res.get("ok") and res.get("profile"):
        prof = res["profile"]
        email_map = {
            OWNER_ID: OWNER_EMAIL,
            "thanh_vien_a": "thanhviena.hust@gmail.com",
            "thanh_vien_b": "thanhvienb.hust@gmail.com",
            "khach_c": "khachc.guest@gmail.com",
        }
        target_email = str(payload.get("email") or email_map.get(user_id, f"{user_id}@gmail.com"))
        get_auth_3layer_manager().complete_first_page_voice_enrollment(
            email=target_email,
            spoken_text=str(payload.get("spoken_text", f"Thu âm giọng thật Cấp {tier} ({user_name})")),
            measured_f0_hz=float(prof["f0_hz"]),
            hold_duration_sec=float(res.get("duration_sec", 4.0)),
            source_device="Microphone Trực Tiếp (16kHz PCM)",
        )
        for br in list(_ACTIVE_BRIDGES):
            br.voice_auth.profiles = copy.deepcopy(_BOOT_VOICE_AUTH.profiles)
            br.engine.set_active_user(user_id)
        await broadcast_rest_state_to_bridges()
    return JSONResponse(sanitize_api_payload(res))


@router.post("/api/auth3/voice_permission_command")
async def api_auth3_voice_permission_command(payload: dict[str, Any]) -> JSONResponse:
    """Khẩu lệnh phân quyền hoặc thu hồi quyền bằng giọng nói."""
    mgr = get_auth_3layer_manager()
    spoken_text = str(payload.get("spoken_text") or payload.get("command_text") or "").strip()
    target_identifier = str(payload.get("target_identifier", "")).strip()
    try:
        actor_tier = int(payload.get("actor_tier") or payload.get("caller_tier") or 1)
    except (ValueError, TypeError):
        actor_tier = 1
    source_device = str(payload.get("source_device", "Mic Giọng Nói Thiết Bị")).strip()

    if target_identifier and "enable_permission" in payload:
        enable_perm = bool(payload.get("enable_permission"))
        res = mgr.set_account_permission_by_voice_or_admin(
            target_identifier=target_identifier,
            enable_permission=enable_perm,
            actor_tier=actor_tier,
            spoken_command=spoken_text or ("Bật lại quyền" if enable_perm else "Xóa cấp quyền"),
            source_device=source_device,
        )
    else:
        res = mgr.parse_and_execute_voice_permission_command(
            spoken_text=spoken_text,
            actor_tier=actor_tier,
            source_device=source_device,
        ) or {
            "ok": False,
            "error": f"Không nhận diện được lệnh xóa/bật lại quyền trong câu: '{spoken_text}'",
        }

    if res.get("ok") and res.get("account"):
        acc = res["account"]
        if res.get("action") == "REVOKED":
            await _REST_ENGINE.revoke_user_permission(target_name=acc["display_name"])
        elif res.get("action") == "RESTORED":
            await _REST_ENGINE.grant_user_permission(target_name=acc["display_name"], target_tier=int(acc["tier"]))
        await broadcast_rest_state_to_bridges()

    append_audit_log(
        category="AUTH_3LAYER",
        event_type="voice_permission_command",
        summary=res.get("message") or res.get("error") or "Lệnh giọng nói xóa/bật quyền",
        user_name="Nguyễn Tuấn Anh (Admin Cấp 1)",
        tier=actor_tier,
        details=res,
    )
    return JSONResponse(sanitize_api_payload(res))


@router.post("/api/auth3/layer1_login")
async def api_auth3_layer1_login(payload: dict[str, Any]) -> JSONResponse:
    """Xác thực Lớp 1 (Mật khẩu PBKDF2 hoặc PIN)."""
    email = str(payload.get("email", OWNER_EMAIL)).strip()
    password = str(payload.get("password", "")).strip()
    login_method = str(payload.get("login_method", "password")).strip()
    source = str(payload.get("source", "Web Portal")).strip()
    send_gmail = bool(payload.get("send_gmail", True))
    res = get_auth_3layer_manager().layer1_login(
        email=email,
        password=password,
        login_method=login_method,
        source=source,
        send_gmail=send_gmail,
    )
    session_token = None
    if res.get("ok"):
        acc = res.get("account") or {}
        tier_val = int(acc.get("tier") or res.get("tier") or 1)
        acc_id = str(acc.get("account_id") or "")
        role_map = ROLE_MAP
        role_name = acc.get("role") or role_map.get(tier_val, "CHILD_GUEST")
        disp_name = acc.get("display_name") or email
        store = get_session_store()
        sess = store.create_session(
            user_id=acc_id or email,
            tier=tier_val,
            role=role_name,
            display_name=disp_name,
            email=email,
            source=source,
        )
        res["session_token"] = sess.session_id
        res["session"] = sess.to_dict()
        session_token = sess.session_id
        engine_role_map = USER_ROLE_MAP
        _REST_ENGINE.set_active_user(acc_id or engine_role_map.get(tier_val, OWNER_ID))
        await broadcast_rest_state_to_bridges()
    append_audit_log(
        category="AUTH_3LAYER",
        event_type="layer1_login",
        summary=res.get("message") or res.get("error") or "Đăng nhập Lớp 1",
        user_name=email,
        tier=int(res.get("account", {}).get("tier", 1)) if res.get("ok") else 99,
        details=res,
    )
    resp = JSONResponse(sanitize_api_payload(res))
    if res.get("ok"):
        acc = res.get("account") or {}
        tier_val = int(acc.get("tier") or res.get("tier") or 1)
        if session_token:
            resp.set_cookie("sh_session_token", session_token, path="/", httponly=True, samesite="lax", max_age=86400)
            resp.set_cookie("session_token", session_token, path="/", httponly=False, samesite="lax", max_age=86400)
            resp.set_cookie("mobileLoggedIn", "1", path="/", httponly=False, samesite="lax", max_age=86400)
            resp.set_cookie("mobileLoggedInEmail", email, path="/", httponly=False, samesite="lax", max_age=86400)
    return resp


@router.post("/api/auth3/layer2_verify_otp")
async def api_auth3_layer2_verify_otp(payload: dict[str, Any]) -> JSONResponse:
    """Xác thực Lớp 2 (Mã OTP 6 số)."""
    email = str(payload.get("email", OWNER_EMAIL)).strip()
    otp_code = str(payload.get("otp_code") or payload.get("otp") or "").strip()
    source = str(payload.get("source", "Web Portal")).strip()
    res = get_auth_3layer_manager().layer2_verify_otp(email=email, otp_input=otp_code, source=source)
    session_token = None
    if res.get("ok"):
        tier_val = int(res.get("tier") or 1)
        acc_obj = get_auth_3layer_manager().find_account(email) or {}
        acc_id = str(acc_obj.get("account_id") or "")
        role_map = ROLE_MAP
        role_name = acc_obj.get("role") or role_map.get(tier_val, "CHILD_GUEST")
        disp_name = acc_obj.get("display_name") or email
        store = get_session_store()
        sess = store.create_session(
            user_id=acc_id or email,
            tier=tier_val,
            role=role_name,
            display_name=disp_name,
            email=email,
            source=source,
        )
        res["session_token"] = sess.session_id
        res["session"] = sess.to_dict()
        session_token = sess.session_id
    append_audit_log(
        category="AUTH_3LAYER",
        event_type="layer2_verify_otp",
        summary=res.get("message") or res.get("error") or "Xác thực OTP Lớp 2",
        user_name=email,
        tier=int(res.get("tier", 1)) if res.get("ok") else 99,
        details=res,
    )
    resp = JSONResponse(sanitize_api_payload(res))
    if res.get("ok"):
        tier_val = int(res.get("tier") or 1)
        acc_obj = get_auth_3layer_manager().find_account(email) or {}
        if session_token:
            resp.set_cookie("sh_session_token", session_token, path="/", httponly=True, samesite="lax", max_age=86400)
            resp.set_cookie("session_token", session_token, path="/", httponly=False, samesite="lax", max_age=86400)
            resp.set_cookie("mobileLoggedIn", "1", path="/", httponly=False, samesite="lax", max_age=86400)
            resp.set_cookie("mobileLoggedInEmail", email, path="/", httponly=False, samesite="lax", max_age=86400)
    return resp


@router.post("/api/auth3/register_or_set_password")
async def api_auth3_register_or_set_password(payload: dict[str, Any]) -> JSONResponse:
    """Tạo tài khoản hoặc đặt/đổi mật khẩu với 2 ô mật khẩu xác nhận."""
    email = str(payload.get("email", "")).strip()
    password = str(payload.get("password", "")).strip()
    confirm_password = str(payload.get("confirm_password", "")).strip()
    display_name = str(payload.get("display_name") or payload.get("name") or "").strip()
    try:
        target_tier = int(payload.get("target_tier") or payload.get("tier") or 2)
    except (ValueError, TypeError):
        target_tier = 2
    res = get_auth_3layer_manager().register_or_update_password(
        email=email,
        password=password,
        confirm_password=confirm_password,
        display_name=display_name,
        target_tier=target_tier,
        source=str(payload.get("source", "Web Login Gate")),
    )
    if res.get("ok") and res.get("account"):
        acc = res["account"]
        await _REST_ENGINE.grant_user_permission(target_name=acc["display_name"], target_tier=int(acc["tier"]))
        await broadcast_rest_state_to_bridges()
    status_code = 200 if res.get("ok") else int(res.get("status_code", 400))
    return JSONResponse(sanitize_api_payload(res), status_code=status_code)


@router.post("/api/auth3/forgot_password_send_otp")
async def api_auth3_forgot_password_send_otp(payload: dict[str, Any]) -> JSONResponse:
    """Gửi mã OTP 6 số về Gmail cho tính năng Quên mật khẩu."""
    email = str(payload.get("email", OWNER_EMAIL)).strip()
    send_gmail = bool(payload.get("send_gmail", True))
    res = get_auth_3layer_manager().request_password_reset_otp(
        email=email,
        send_gmail=send_gmail,
        source=str(payload.get("source", "Web Quên Mật Khẩu")),
    )
    status_code = 200 if res.get("ok") else int(res.get("status_code", 400))
    return JSONResponse(sanitize_api_payload(res), status_code=status_code)


@router.post("/api/auth3/forgot_password_reset")
async def api_auth3_forgot_password_reset(payload: dict[str, Any]) -> JSONResponse:
    """Xác nhận OTP quên mật khẩu và đặt lại mật khẩu mới (kiểm tra 2 ô mật khẩu)."""
    email = str(payload.get("email", OWNER_EMAIL)).strip()
    otp_code = str(payload.get("otp_code") or payload.get("otp") or "").strip()
    new_password = str(payload.get("new_password") or payload.get("password") or "").strip()
    confirm_password = str(payload.get("confirm_password", "")).strip()
    res = get_auth_3layer_manager().reset_password_with_otp(
        email=email,
        otp_code=otp_code,
        new_password=new_password,
        confirm_password=confirm_password,
        source=str(payload.get("source", "Web Quên Mật Khẩu")),
    )
    status_code = 200 if res.get("ok") else int(res.get("status_code", 400))
    return JSONResponse(sanitize_api_payload(res), status_code=status_code)


@router.post("/api/auth3/layer3_voice")
async def api_auth3_layer3_voice(payload: dict[str, Any]) -> JSONResponse:
    """Xác thực Lớp 3 (Sinh trắc học giọng nói)."""
    mode = str(payload.get("mode", "recognize")).strip()
    pcm16k_b64 = str(
        payload.get("audio_pcm_b64")
        or payload.get("pcm16k_b64")
        or payload.get("wav_b64")
        or payload.get("audio_b64")
        or ""
    ).strip()
    pcm_bytes = b""
    if pcm16k_b64:
        clean_b64 = (
            pcm16k_b64.split(",", 1)[1]
            if ("," in pcm16k_b64 and pcm16k_b64.startswith("data:"))
            else pcm16k_b64
        )
        try:
            pcm_bytes = base64.b64decode(clean_b64)
        except Exception:
            pcm_bytes = b""

    if (
        any(k in payload for k in ("sample_id", "profile_id", "speaker_id", "voiceprint"))
        or len(pcm_bytes) < 640
    ):
        return JSONResponse(
            sanitize_api_payload(
                {
                    "ok": False,
                    "recognized": False,
                    "error": "Bắt buộc cung cấp dữ liệu thu âm giọng nói thực tế; không chấp nhận sample_id hoặc voiceprint từ client!",
                }
            ),
            status_code=403,
        )

    f0_raw = payload.get("measured_f0_hz")
    measured_f0_hz = float(f0_raw) if f0_raw is not None else None
    email = str(payload.get("email", "")).strip()
    target_name = str(payload.get("target_name", "")).strip()
    target_tier = int(payload.get("target_tier", 2) or 2)
    password = str(payload.get("password", "")).strip()
    source_device = str(payload.get("source_device", "Samsung Galaxy S9 (App Android)")).strip()

    res = get_auth_3layer_manager().recognize_or_enroll_voice_from_device(
        mode=mode,
        pcm16k_b64=pcm16k_b64,
        measured_f0_hz=measured_f0_hz,
        email=email,
        target_name=target_name,
        target_tier=target_tier,
        password=password,
        source_device=source_device,
    )
    if res.get("ok") and res.get("recognized"):
        tier_val = int(res.get("tier", 1))
        role_map = USER_ROLE_MAP
        _REST_ENGINE.set_active_user(role_map.get(tier_val, OWNER_ID))
        await broadcast_rest_state_to_bridges()

    append_audit_log(
        category="AUTH_3LAYER",
        event_type=f"layer3_voice_{mode}",
        summary=res.get("message") or res.get("error") or "Xử lý Giọng nói Lớp 3",
        user_name=str(res.get("speaker_name") or target_name or email or "Voice User"),
        tier=int(res.get("tier", target_tier)),
        details=res,
    )
    return JSONResponse(sanitize_api_payload(res))


@router.post("/api/auth3/run_tests")
@router.post("/api/auth3/run_test_suite")
async def api_auth3_run_tests(payload: dict[str, Any] | None = None) -> JSONResponse:
    """Chạy bộ kiểm thử tự động 14 ca xác thực 3 tầng (Hỗ trợ alias chống 404)."""
    send_real = bool((payload or {}).get("send_real_gmail", False) or (payload or {}).get("send_live_email", False))
    rep = get_auth_3layer_manager().run_automated_3layer_test_suite(send_real_email_on_test1=send_real)
    cases_with_id = [{**c, "id": c.get("test_id", "")} for c in rep.get("cases", [])]
    rep["passed"] = rep.get("passed_cases", 0)
    rep["total"] = rep.get("total_cases", len(cases_with_id))
    rep["results"] = cases_with_id
    append_audit_log(
        category="AUTH_3LAYER",
        event_type="auth3_test_suite_executed",
        summary=f"🧪 Chạy Kiểm thử 3 Lớp: {rep.get('summary')}",
        user_name="Nguyễn Tuấn Anh (Admin Cấp 1)",
        tier=1,
        details=rep,
    )
    return JSONResponse(sanitize_api_payload(rep))


@router.get("/api/voice_samples")
async def api_list_voice_samples() -> JSONResponse:
    """Danh sách các file âm thanh wav mẫu trong test_audio/."""
    samples = []
    for key, label in VOICE_SAMPLES_META.items():
        wav_path = AUDIO_DIR / f"{key}.wav"
        if wav_path.exists():
            with wave.open(str(wav_path), "rb") as w:
                dur = round(w.getnframes() / float(w.getframerate()), 2)
            samples.append({"id": key, "label": label, "duration_sec": dur})
    return JSONResponse(sanitize_api_payload({"samples": samples}))
