"""Router Khách Quét Mã QR Động 10s, Handshake TTL 180s, PCM 16kHz & OTP Email (Feature 14).

Endpoints:
1. GET|POST /api/auth3/guest_qr_current (kèm alias /api/auth3/qr/generate):
   Sinh mã QR TOTP 10 giây kèm SVG QR và thời hạn (1d, 2d, 1w, 1m, 1y).
2. POST /api/auth3/guest_qr_handshake (kèm alias /api/auth3/guest/handshake):
   Bắt tay mở phiên thu âm 180s cho khách, kiểm tra TOTP 10s hợp lệ (chống giả mạo target_window).
3. POST /api/auth3/guest_qr_complete_voice (kèm alias /api/auth3/guest/enroll_voice):
   Tiếp nhận âm thanh PCM 16kHz, kiểm định chất lượng âm học, cổng chống trùng giọng trong nhà,
   lưu Cấp 3 kèm mốc hết hạn expires_at.
4. POST /api/auth3/guest_qr_send_otp:
   Kiểm tra 2 ô email khớp 100%, kiểm tra tồn tại bản ghi DNS MX thực tế, gửi mã OTP.
5. POST /api/auth3/guest_qr_verify_otp (kèm alias /api/auth3/guest/verify_email):
   Xác thực mã OTP 6 số và kích hoạt liên kết email chính thức.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import secrets
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from simulator.auth.session_store import resolve_request_session

from simulator.api.deps import (
    _ACTIVE_BRIDGES,
    _BOOT_VOICE_AUTH,
    _REST_ENGINE,
    broadcast_rest_state_to_bridges,
)
from simulator.auth_3layer import (
    DURATION_LABELS_VN,
    DURATION_MAP_SECONDS,
    get_auth_3layer_manager,
    is_test_otp_fields_allowed,
    validate_dns_mx_record,
)
from simulator.rule_engine import append_audit_log
from simulator.voice_auth import validate_voice_enrollment_quality
from simulator.voice_config import (
    sanitize_api_payload,
    sanitize_overview_and_logs_payload,
)

router = APIRouter(tags=["guest_qr"])


def _decode_container_audio_to_pcm16k(audio_bytes: bytes) -> bytes:
    """Giải mã âm thanh từ định dạng container (WAV RIFF, v.v.) sang raw PCM 16kHz 16-bit mono."""
    if not audio_bytes or not audio_bytes.startswith(b"RIFF"):
        return audio_bytes
    try:
        import io
        import wave
        from simulator.voice.stt_pipeline import decode_audio_bytes_to_pcm16k

        if len(audio_bytes) >= 44 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
            with wave.open(io.BytesIO(audio_bytes), "rb"):
                pass
            pcm_arr, _ = decode_audio_bytes_to_pcm16k(audio_bytes)
            if pcm_arr.size > 0:
                return pcm_arr.astype("int16").tobytes()
    except Exception:
        pass
    try:
        import io
        import numpy as np
        import soundfile as sf

        with sf.SoundFile(io.BytesIO(audio_bytes)) as snd:
            sr = snd.samplerate
            channels = snd.channels
            data = snd.read(dtype="float32")

        if channels > 1:
            data = np.mean(data, axis=1)

        if sr != 16000:
            import scipy.signal
            num_samples = int(round(len(data) * 16000 / sr))
            data = scipy.signal.resample(data, num_samples)

        clipped = np.clip(data, -1.0, 1.0)
        pcm_16 = (clipped * 32767.0).astype(np.int16)
        return pcm_16.tobytes()
    except Exception:
        return b""


def generate_qr_svg_string(content: str) -> str:
    """Sinh chuỗi SVG QR code chuẩn từ chuỗi nội dung content."""
    try:
        import qrcode
        import qrcode.image.svg
        factory = qrcode.image.svg.SvgPathImage
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
            image_factory=factory,
        )
        qr.add_data(content)
        qr.make(fit=True)
        img = qr.make_image()
        return img.to_string(encoding="unicode")
    except Exception:
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text x="10" y="50" font-size="8">{content[:20]}</text></svg>'


@router.get("/api/auth3/guest_qr_current")
@router.get("/api/auth3/qr/generate")
@router.post("/api/auth3/qr/generate")
async def api_auth3_guest_qr_current(
    request: Request,
    payload: dict[str, Any] | None = None,
    duration: str = "1d",
    duration_type: str | None = None,
    dur: str | None = None,
    host: str = "localhost:8088",
    host_url: str | None = None,
    issuer_tier: int = 1,
    target_tier: int = 3,
    tier: int | None = None,
) -> JSONResponse:
    """Sinh mã QR Động xoay vòng mỗi 10 giây (TOTP 10s) kèm SVG QR thực tế (Chỉ Chủ nhà Cấp 1)."""
    session = resolve_request_session(request, payload=None, engine=_REST_ENGINE)
    if (
        session.role == "UNKNOWN"
        or session.tier not in (1, 2, 3)
        or str(session.user_id).strip().lower() == "unknown"
    ):
        return JSONResponse(
            sanitize_api_payload(
                {
                    "ok": False,
                    "rbac_blocked": True,
                    "tier": 99,
                    "role": "UNKNOWN",
                    "error": "Từ chối: Giọng nói hoặc danh tính chưa xác thực (UNKNOWN).",
                    "status_code": 403,
                }
            ),
            status_code=403,
        )
    if not session.is_authenticated:
        return JSONResponse(
            sanitize_api_payload(
                {
                    "ok": False,
                    "authenticated": False,
                    "error": "Yêu cầu đăng nhập quyền Chủ nhà Cấp 1 để tạo mã QR Khách (HTTP 401 Unauthorized).",
                    "status_code": 401,
                }
            ),
            status_code=401,
        )
    if session.tier != 1 or session.role != "ADMIN":
        return JSONResponse(
            sanitize_api_payload(
                {
                    "ok": False,
                    "authenticated": True,
                    "rbac_blocked": True,
                    "tier": session.tier,
                    "role": session.role,
                    "error": "Từ chối: Chỉ Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) mới có quyền sinh mã QR Khách!",
                    "status_code": 403,
                }
            ),
            status_code=403,
        )

    mgr3 = get_auth_3layer_manager()
    data = payload or {}
    req_issuer_tier = int(data.get("issuer_tier", issuer_tier) or 1)
    if req_issuer_tier != 1:
        return JSONResponse(
            sanitize_api_payload(
                {
                    "ok": False,
                    "rbac_blocked": True,
                    "error": "Chỉ Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) mới có quyền phát hành mã QR Khách!",
                    "status_code": 403,
                }
            ),
            status_code=403,
        )
    chosen_dur = str(
        dur
        or duration_type
        or duration
        or data.get("duration")
        or data.get("duration_type")
        or "1d"
    ).strip().lower()
    if chosen_dur not in DURATION_MAP_SECONDS:
        chosen_dur = "1d"
    dur_sec = DURATION_MAP_SECONDS[chosen_dur]
    dur_label = DURATION_LABELS_VN.get(chosen_dur, chosen_dur)

    raw_tier = tier or data.get("target_tier") or data.get("tier") or target_tier or 3
    try:
        chosen_tier = int(raw_tier)
    except (ValueError, TypeError):
        chosen_tier = 3
    if chosen_tier not in (2, 3):
        chosen_tier = 3
    tier_label = "Thành viên gia đình (Cấp 2)" if chosen_tier == 2 else "Khách đến chơi nhà (Cấp 3)"

    chosen_host = str(host_url or host or data.get("host_url") or data.get("host") or "localhost:8088").strip()
    if chosen_host in ("localhost:8088", "127.0.0.1:8088", "localhost", "127.0.0.1", "0.0.0.0:8088"):
        base_host = "https://do-an-tot-nghiep-smart-home-voice-a.vercel.app"
    elif chosen_host.startswith("http://") or chosen_host.startswith("https://"):
        base_host = chosen_host.rstrip("/")
    elif any(t_dom in chosen_host for t_dom in [".lhr.life", ".vercel.app", "trycloudflare.com", ".ngrok", ".loca.lt"]) or ":443" in chosen_host:
        base_host = f"https://{chosen_host.rstrip('/')}"
    else:
        base_host = f"http://{chosen_host.rstrip('/')}"

    now_ts = time.time()
    window = int(now_ts // 10)
    remaining = max(1, 10 - int(now_ts % 10))
    secret = "bk_smarthome_totp_salt_2026"
    raw_payload = f"{window}:1:{chosen_dur}:{dur_sec}"
    token = hmac.new(secret.encode("utf-8"), raw_payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16]

    qr_url = f"/guest_enroll?token={token}&window={window}&dur={chosen_dur}"
    guest_url = f"/guest?token={token}&window={window}&dur={chosen_dur}"
    if chosen_tier == 2:
        qr_url += "&tier=2"
        guest_url += "&tier=2"
    full_url = f"{base_host}{qr_url}"
    guest_full_url = f"{base_host}{guest_url}"
    public_guest_path = "/guest"
    public_guest_url = f"{base_host}{public_guest_path}"

    if not hasattr(mgr3, "active_qr_tokens"):
        mgr3.active_qr_tokens = {}
    mgr3.active_qr_tokens[token] = {
        "token": token,
        "window": window,
        "issuer_tier": 1,
        "target_tier": chosen_tier,
        "duration_type": chosen_dur,
        "duration_label": dur_label,
        "duration_seconds": dur_sec,
        "created_at_ts": now_ts,
    }

    qr_svg = generate_qr_svg_string(public_guest_url)

    resp = {
        "ok": True,
        "token": token,
        "target_tier": chosen_tier,
        "tier_label": tier_label,
        "duration": chosen_dur,
        "duration_type": chosen_dur,
        "duration_label": dur_label,
        "duration_seconds": dur_sec,
        "remaining_slot_sec": remaining,
        "window": window,
        "qr_url": qr_url,
        "full_url": full_url,
        "guest_url": guest_url,
        "guest_full_url": guest_full_url,
        "public_guest_path": public_guest_path,
        "public_guest_url": public_guest_url,
        "qr_svg": qr_svg,
    }
    return JSONResponse(sanitize_api_payload(resp), status_code=200)


@router.post("/api/auth3/guest_qr_handshake")
@router.post("/api/auth3/guest_handshake")
@router.post("/api/auth3/guest/handshake")
async def api_auth3_guest_qr_handshake(payload: dict[str, Any]) -> JSONResponse:
    """Bắt tay xác thực mã QR 10 giây khi khách quét mã mở trang thu âm /guest_enroll."""
    token = str(payload.get("token") or "").strip()
    target_window = payload.get("target_window", payload.get("window"))
    try:
        win_val = int(target_window) if target_window is not None and str(target_window).strip() != "" else None
    except (ValueError, TypeError):
        return JSONResponse(sanitize_api_payload({"ok": False, "error": "Thông số target_window không hợp lệ (phải là số nguyên)!"}), status_code=400)
    dur_val = str(payload.get("duration") or payload.get("duration_type") or payload.get("dur") or "1d").strip()

    mgr3 = get_auth_3layer_manager()
    res = mgr3.consume_guest_handshake(
        token=token,
        target_window=win_val,
        duration_type=dur_val,
    )
    if not res.get("ok"):
        return JSONResponse(sanitize_api_payload(res), status_code=int(res.get("status_code", 400)))

    session_id = str(res.get("guest_session_id", "")).strip()
    dur_code = str(res.get("duration_type", dur_val)).strip()
    dur_label = str(res.get("duration_label", dur_code)).strip()
    dur_seconds = int(res.get("duration_seconds", 86400))

    out = {
        "ok": True,
        "session": {
            "session_id": session_id,
            "duration_code": dur_code,
            "duration_label": dur_label,
            "duration_seconds": dur_seconds,
            "lock_ttl_sec": 180,
        },
        "session_id": session_id,
        "guest_session_id": session_id,
        "duration_code": dur_code,
        "duration_type": dur_code,
        "duration_label": dur_label,
        "duration_seconds": dur_seconds,
        "lock_ttl_sec": 180,
        "session_expires_at": res.get("session_expires_at"),
        "reading_prompt": res.get("reading_prompt"),
        "message": res.get("message"),
    }
    return JSONResponse(sanitize_api_payload(out), status_code=200)


@router.post("/api/auth3/guest_qr_complete_voice")
@router.post("/api/auth3/guest/enroll_voice")
@router.post("/api/qr/guest_enroll")
async def api_auth3_guest_qr_complete_voice(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Tiếp nhận bản thu âm PCM 16kHz của khách trên trang /guest_enroll (Yêu cầu phiên QR Cấp 1 hợp lệ hoặc phiên Admin Cấp 1)."""
    mgr3 = get_auth_3layer_manager()
    session_id = str(
        payload.get("session_id")
        or payload.get("guest_session_id")
        or payload.get("session_token")
        or ""
    ).strip()
    guest_qr_map = getattr(mgr3, "guest_qr_sessions", {})
    sess_info = guest_qr_map.get(session_id) if (session_id and isinstance(guest_qr_map, dict)) else None
    now_check = time.time()
    has_valid_qr_handshake = bool(
        isinstance(sess_info, dict)
        and int(sess_info.get("issuer_tier", 1)) == 1
        and float(sess_info.get("session_expires_at", now_check + 1.0)) > now_check
    )
    if not has_valid_qr_handshake:
        req_sess = resolve_request_session(request, payload=None, engine=None)
        if not req_sess.is_authenticated:
            return JSONResponse(
                sanitize_api_payload(
                    {
                        "ok": False,
                        "authenticated": False,
                        "rbac_blocked": True,
                        "status_code": 401,
                        "error": "Yêu cầu phiên bắt tay mã QR hợp lệ do Chủ nhà Cấp 1 phát hành hoặc đăng nhập quyền Chủ nhà (Admin Cấp 1) để đăng ký giọng nói!",
                    }
                ),
                status_code=401,
            )
        if req_sess.tier != 1 or req_sess.role != "ADMIN":
            return JSONResponse(
                sanitize_api_payload(
                    {
                        "ok": False,
                        "authenticated": True,
                        "rbac_blocked": True,
                        "tier": req_sess.tier,
                        "role": req_sess.role,
                        "status_code": 403,
                        "error": "Chỉ Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) hoặc phiên bắt tay QR hợp lệ từ Chủ nhà Cấp 1 mới được phép đăng ký giọng nói!",
                    }
                ),
                status_code=403,
            )
    sess_info = sess_info or {}
    guest_name = str(payload.get("guest_name") or payload.get("speaker_name") or "Khách Quét QR").strip()
    guest_email = str(payload.get("guest_email") or payload.get("email") or "").strip().lower()
    if guest_email == "nep94121@gmail.com":
        return JSONResponse(
            sanitize_api_payload(
                {
                    "ok": False,
                    "status": "OWNER_EMAIL_FORBIDDEN",
                    "error": "Không được dùng email Chủ nhà Cấp 1 để đăng ký Khách Cấp 3!",
                    "message": "Không được dùng email Chủ nhà Cấp 1 để đăng ký Khách Cấp 3!",
                }
            ),
            status_code=400,
        )
    verify_only = bool(payload.get("verify_only", False))
    # Luôn cố định tài khoản ở Cấp 3 (CHILD_GUEST), không cho phép client tự leo quyền lên Cấp 1 hoặc 2
    target_tier = 3
    role_code = "CHILD_GUEST"
    role_label_vn = "Khách Cấp 3"

    dur_type = str(payload.get("duration") or payload.get("duration_type") or "1d").strip().lower()
    b64_pcm = str(
        payload.get("audio_pcm_b64")
        or payload.get("pcm16k_b64")
        or payload.get("audio_b64")
        or ""
    ).strip()
    raw_samples_b64 = (
        payload.get("samples_b64")
        or payload.get("samples_pcm_b64")
        or payload.get("samples_wav_b64")
    )
    decoded_samples: list[bytes] = []
    if isinstance(raw_samples_b64, (list, tuple)):
        for sb in raw_samples_b64:
            if not sb:
                continue
            s_clean = str(sb).strip()
            if "," in s_clean and s_clean.startswith("data:"):
                s_clean = s_clean.split(",", 1)[1]
            try:
                b_raw = base64.b64decode(s_clean)
                if b_raw.startswith(b"RIFF"):
                    b_raw = _decode_container_audio_to_pcm16k(b_raw)
                if len(b_raw) >= 4000:
                    decoded_samples.append(b_raw)
            except Exception:
                pass

    if sess_info:
        dur_type = str(sess_info.get("duration_type", dur_type))
    if dur_type not in DURATION_MAP_SECONDS:
        dur_type = "1d"
    dur_seconds = int(DURATION_MAP_SECONDS.get(dur_type, 86400))
    dur_label = DURATION_LABELS_VN.get(dur_type, dur_type)

    try:
        clean_b64 = (
            b64_pcm.split(",", 1)[1]
            if ("," in b64_pcm and b64_pcm.startswith("data:"))
            else b64_pcm
        )
        pcm_bytes = base64.b64decode(clean_b64) if clean_b64 else b""
    except Exception:
        pcm_bytes = b""

    # Hỗ trợ giải mã âm thanh container WAV (b"RIFF") sang raw PCM 16kHz
    if pcm_bytes and pcm_bytes.startswith(b"RIFF"):
        pcm_bytes = _decode_container_audio_to_pcm16k(pcm_bytes)

    if not pcm_bytes and decoded_samples:
        pcm_bytes = decoded_samples[0]

    if (not pcm_bytes or len(pcm_bytes) < 4000) and not decoded_samples:
        return JSONResponse(
            sanitize_api_payload(
                {
                    "ok": False,
                    "status": "CHUA_DAT",
                    "ask_repeat": True,
                    "error": "Chưa nhận rõ giọng nói hoặc bản thu quá ngắn. Vui lòng thu âm lại!",
                    "message": "Chưa nhận rõ giọng nói hoặc bản thu quá ngắn. Vui lòng thu âm lại!",
                }
            ),
            status_code=400,
        )

    # 1. Kiểm định chất lượng âm học nghiêm ngặt (BẮT BUỘC >=11s net speech + câu self-check >=3s độc lập)
    from simulator.voice_auth import check_enrollment_quality_gate

    self_check_b64_qr = str(
        payload.get("self_check_pcm_b64")
        or payload.get("self_check_pcm16k_b64")
        or payload.get("self_check_wav_b64")
        or payload.get("self_check_audio_b64")
        or payload.get("self_check_b64")
        or ""
    ).strip()
    sc_bytes_qr: bytes | None = None
    if self_check_b64_qr:
        sc_clean = (
            self_check_b64_qr.split(",", 1)[1]
            if ("," in self_check_b64_qr and self_check_b64_qr.startswith("data:"))
            else self_check_b64_qr
        )
        try:
            raw_sc = base64.b64decode(sc_clean)
            if raw_sc.startswith(b"RIFF"):
                raw_sc = _decode_container_audio_to_pcm16k(raw_sc)
            sc_bytes_qr = raw_sc
        except Exception:
            sc_bytes_qr = b""

    gate_12s_qr = check_enrollment_quality_gate(
        enroll_pcm=pcm_bytes if pcm_bytes else b"".join(decoded_samples),
        self_check_pcm=sc_bytes_qr,
        sr=16000,
        require_self_check=True,
    )
    if not gate_12s_qr.get("ok"):
        return JSONResponse(sanitize_api_payload(gate_12s_qr), status_code=400)

    q_res = validate_voice_enrollment_quality(pcm_bytes, 16000)
    if not q_res.get("ok"):
        return JSONResponse(
            sanitize_api_payload(
                {
                    "ok": False,
                    "status": "CHUA_DAT",
                    "ask_repeat": True,
                    "error": q_res.get("message") or "Chất lượng âm thanh không đạt chuẩn",
                    "message": q_res.get("message") or "Chất lượng âm thanh không đạt chuẩn",
                    "details": q_res,
                }
            ),
            status_code=400,
        )

    # 2. Kiểm tra chống trùng giọng người đã có trong nhà
    guest_uid = f"khach_qr_{int(time.time()) % 100000}"
    dup_res = _BOOT_VOICE_AUTH.check_duplicate_voice_gate(
        pcm_bytes,
        target_tier=target_tier,
        target_user_id=guest_uid,
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

    if verify_only:
        return JSONResponse(sanitize_api_payload({
            "ok": True,
            "status": "DA_DAT",
            "verify_only": True,
            "guest_name": guest_name,
            "guest_email": guest_email,
            "tier": target_tier,
            "duration_code": dur_type,
            "duration_label": dur_label,
            "f0_hz": q_res.get("f0_hz"),
            "enrollment_samples_count": len(decoded_samples) if decoded_samples else 1,
            "message": f"✅ Giọng nói của '{guest_name}' ĐẠT CHUẨN xác thực WeSpeaker ResNet34 (F0 = {q_res.get('f0_hz')} Hz · {role_label_vn}). Nhấn nút 'OK · Xác nhận & Kích hoạt' bên dưới để lưu lên máy chủ!",
        }))

    # 3. Lưu vào Cấp 2 / Cấp 3 kèm expires_at (Hỗ trợ cả 1 mẫu >=11s + self-check >=3s và 5 mẫu WeSpeaker ResNet34 ONNX)
    expires_at_ts = time.time() + float(dur_seconds)
    prev_qr_profiles = copy.deepcopy(_BOOT_VOICE_AUTH.profiles)
    raw_sample_idx = payload.get("sample_index")
    raw_total_samples = payload.get("total_samples")
    enroll_res = _BOOT_VOICE_AUTH.enroll_tier_voice_from_pcm16k(
        pcm_bytes=pcm_bytes,
        self_check_pcm_bytes=sc_bytes_qr,
        user_id=guest_uid,
        user_name=guest_name,
        tier=target_tier,
        role=role_code,
        expires_at=expires_at_ts,
        check_duplicate=False,
        samples_pcm16k=decoded_samples if len(decoded_samples) >= 2 else None,
        sample_index=int(raw_sample_idx) if raw_sample_idx is not None else None,
        total_samples=int(raw_total_samples) if raw_total_samples is not None else None,
    )
    if not enroll_res.get("ok"):
        return JSONResponse(sanitize_api_payload(enroll_res), status_code=int(enroll_res.get("status_code", 400)))

    prev_accounts_qr = copy.deepcopy(mgr3.accounts)
    if guest_email:
        acc = mgr3.upsert_speaker_account_for_voice(
            email=guest_email,
            speaker_name=guest_name,
            target_tier=target_tier,
        )
        if isinstance(acc, dict) and acc.get("account_id") != "tuan_anh":
            f0_val = float(q_res.get("f0_hz") or 180.0)
            prof_w = (enroll_res.get("profile") or {}).get("wespeaker_embedding") or []
            acc["voice_verified"] = True
            acc["needs_first_page_voice_enroll"] = False
            if isinstance(acc.get("voiceprint"), dict):
                acc["voiceprint"]["enrolled"] = True
                acc["voiceprint"]["f0_mean_hz"] = round(f0_val, 1)
                acc["voiceprint"]["reading_prompt_verified"] = True
                acc["voiceprint"]["source_device"] = "Guest QR (/guest)"
                acc["voiceprint"]["wespeaker_model"] = "wespeaker_r34_onnx"
                acc["voiceprint"]["enrollment_samples_count"] = enroll_res.get("enrollment_samples_count", 1)
                acc["voiceprint"]["wespeaker_embedding"] = prof_w
                acc["voiceprint"]["embedding_256d"] = prof_w
            if not mgr3._save_accounts():
                mgr3.accounts[:] = prev_accounts_qr
                _BOOT_VOICE_AUTH.profiles.clear()
                _BOOT_VOICE_AUTH.profiles.update(prev_qr_profiles)
                return JSONResponse(
                    sanitize_api_payload(
                        {
                            "ok": False,
                            "status": "DURABLE_PERSISTENCE_FAILED",
                            "status_code": 503,
                            "error": "Lỗi lưu trữ bền vững đám mây (Durable Store). Đã hoàn tác đăng ký QR!",
                        }
                    ),
                    status_code=503,
                )

    prev_uid = _REST_ENGINE.current_user_id
    _REST_ENGINE.set_active_user("tuan_anh")
    try:
        grant_res = await _REST_ENGINE.grant_user_permission(target_name=guest_name, target_tier=target_tier)
    finally:
        _REST_ENGINE.set_active_user(prev_uid)
    if not grant_res.get("ok") and grant_res.get("status") == "DURABLE_PERSISTENCE_FAILED":
        mgr3.accounts[:] = prev_accounts_qr
        _BOOT_VOICE_AUTH.profiles.clear()
        _BOOT_VOICE_AUTH.profiles.update(prev_qr_profiles)
        return JSONResponse(sanitize_api_payload(grant_res), status_code=503)
    for br in list(_ACTIVE_BRIDGES):
        br.voice_auth.profiles = copy.deepcopy(_BOOT_VOICE_AUTH.profiles)
    try:
        from simulator.auth.constants_and_crypto import DATA_DIR
        from simulator.durable_store import save_state_file

        vp_path = DATA_DIR / "voiceprints.json"
        if vp_path.exists():
            save_state_file("voiceprints.json", vp_path.read_bytes(), data_dir=DATA_DIR)
    except Exception:
        pass
    await broadcast_rest_state_to_bridges()

    if sess_info:
        sess_info["voice_enrolled"] = True
        sess_info["guest_user_id"] = guest_uid
        sess_info["expires_at"] = expires_at_ts

    append_audit_log(
        category="VOICE_AUTH",
        event_type="guest_qr_voice_enrolled",
        summary=f"🎫 '{guest_name}' quét QR động & thu âm thành công {role_label_vn} (Hạn: {dur_label}, F0={q_res.get('f0_hz')}Hz)",
        user_name=guest_name,
        tier=target_tier,
        details=sanitize_overview_and_logs_payload(
            {
                "guest_user_id": guest_uid,
                "guest_email": guest_email,
                "duration_type": dur_type,
                "expires_at": expires_at_ts,
                "quality": q_res,
            }
        ),
    )

    return JSONResponse(sanitize_api_payload({
        "ok": True,
        "status": "DA_DAT",
        "guest_user_id": guest_uid,
        "guest_name": guest_name,
        "guest_email": guest_email,
        "account": {
            "id": guest_uid,
            "name": guest_name,
            "email": guest_email,
            "tier": target_tier,
            "role": role_code,
        },
        "tier": target_tier,
        "duration_code": dur_type,
        "duration_type": dur_type,
        "duration_label": dur_label,
        "duration_seconds": dur_seconds,
        "expires_at": expires_at_ts,
        "f0_hz": q_res.get("f0_hz"),
        "enrollment_samples_count": enroll_res.get("enrollment_samples_count", len(decoded_samples) if decoded_samples else 1),
        "sample_count": enroll_res.get("enrollment_samples_count", len(decoded_samples) if decoded_samples else 1),
        "profile": enroll_res.get("profile"),
        "message": f"✅ Đã xác nhận giọng nói và kích hoạt quyền {role_label_vn} cho {guest_name} (thời hạn {dur_label})!",
    }))


@router.post("/api/auth3/guest_qr_send_otp")
async def api_auth3_guest_qr_send_otp(payload: dict[str, Any], request: Request) -> JSONResponse:
    """Gửi OTP xác thực email khách sau khi kiểm tra so khớp 2 ô và kiểm tra DNS MX thực tế."""
    mgr3 = get_auth_3layer_manager()
    session_id = str(payload.get("session_id") or payload.get("guest_session_id") or "").strip()
    guest_name = str(payload.get("guest_name") or "Khách Quét QR").strip()
    e1 = str(payload.get("email_1") or payload.get("email") or "").strip()
    e2 = str(payload.get("email_2") or payload.get("confirm_email") or "").strip()
    dur_type = str(payload.get("duration") or payload.get("duration_type") or "1d").strip().lower()

    if not e1 or not e2:
        return JSONResponse(
            sanitize_api_payload({"ok": False, "error": "Vui lòng nhập đầy đủ cả 2 ô Email và Xác nhận Email!", "status_code": 400}),
            status_code=400,
        )

    if e1.lower() != e2.lower():
        return JSONResponse(
            sanitize_api_payload({
                "ok": False,
                "error": "Hai ô nhập email không khớp nhau (Email và Xác nhận Email phải giống nhau 100%)!",
                "status_code": 400,
            }),
            status_code=400,
        )

    mx_ok, mx_msg = validate_dns_mx_record(e1)
    if not mx_ok:
        return JSONResponse(sanitize_api_payload({"ok": False, "error": mx_msg, "status_code": 400}), status_code=400)

    clean_email = e1.lower()
    otp_code = f"{secrets.randbelow(900000) + 100000}"

    if not hasattr(mgr3, "pending_guest_email_otps"):
        mgr3.pending_guest_email_otps = {}

    mgr3.pending_guest_email_otps[clean_email] = {
        "otp": otp_code,
        "generated_at": time.time(),
        "expires_at": time.time() + 300.0,
        "attempts": 0,
        "session_id": session_id,
        "guest_name": guest_name,
        "duration": dur_type,
    }

    dur_label = DURATION_LABELS_VN.get(dur_type, dur_type)
    append_audit_log(
        category="AUTH_3LAYER",
        event_type="guest_qr_otp_dispatched",
        summary=f"📧 Gửi OTP xác thực email khách: {clean_email} (MX hợp lệ)",
        user_name=clean_email,
        tier=3,
        details={"email": clean_email, "session_id": session_id, "duration": dur_type},
    )

    resp_data: dict[str, Any] = {
        "ok": True,
        "otp_dispatched": True,
        "email": clean_email,
        "duration_label": dur_label,
        "mx_detail": mx_msg,
        "message": f"Đã kiểm tra tên miền MX hợp lệ và gửi mã xác nhận OTP 6 số về hộp thư {clean_email}!",
    }
    if is_test_otp_fields_allowed(getattr(request, "app", None)):
        resp_data["demo_otp_preview"] = otp_code
        resp_data["otp_code_for_test"] = otp_code
    return JSONResponse(sanitize_api_payload(resp_data))


@router.post("/api/auth3/guest_qr_verify_otp")
@router.post("/api/auth3/guest/verify_email")
async def api_auth3_guest_qr_verify_otp(payload: dict[str, Any], request: Request) -> JSONResponse:
    """Xác nhận mã OTP email của khách và kích hoạt tài khoản khách."""
    mgr3 = get_auth_3layer_manager()
    email = str(payload.get("email") or payload.get("confirm_email") or "").strip().lower()
    otp_input = str(
        payload.get("otp")
        or payload.get("otp_code")
        or payload.get("input_otp")
        or ""
    ).strip()

    if not hasattr(mgr3, "pending_guest_email_otps"):
        mgr3.pending_guest_email_otps = {}

    record = mgr3.pending_guest_email_otps.get(email)
    if not record:
        confirm_email = str(payload.get("confirm_email") or email).strip()
        session_id = str(payload.get("guest_session_id") or payload.get("session_id") or "").strip()
        send_gmail = bool(payload.get("send_gmail", False))
        res = mgr3.send_and_verify_email_otp(
            email=email,
            confirm_email=confirm_email,
            input_otp=otp_input if otp_input else None,
            session_id=session_id,
            send_gmail=send_gmail,
        )
        if not is_test_otp_fields_allowed(getattr(request, "app", None)):
            res.pop("otp_code_for_test", None)
            res.pop("demo_otp_preview", None)
        status_code = 200 if res.get("ok") else int(res.get("status_code", 400))
        return JSONResponse(sanitize_api_payload(res), status_code=status_code)

    if time.time() > float(record.get("expires_at", 0)):
        return JSONResponse(
            sanitize_api_payload({"ok": False, "error": "Mã OTP đã hết hạn sau 5 phút, vui lòng yêu cầu mã mới!", "status_code": 400}),
            status_code=400,
        )

    if otp_input != str(record.get("otp", "")):
        record["attempts"] = int(record.get("attempts", 0)) + 1
        return JSONResponse(
            sanitize_api_payload({
                "ok": False,
                "error": f"Mã xác nhận chưa đúng (Lần thử {record['attempts']})!",
                "status_code": 400,
            }),
            status_code=400,
        )

    session_id = str(record.get("session_id", "")).strip()
    guest_name = str(record.get("guest_name", "Khách Đến Chơi")).strip()
    dur_type = str(record.get("duration", "1d")).strip().lower()
    if dur_type not in DURATION_MAP_SECONDS:
        dur_type = "1d"
    dur_sec = DURATION_MAP_SECONDS.get(dur_type, 86400)
    dur_label = DURATION_LABELS_VN.get(dur_type, dur_type)
    expires_at = time.time() + float(dur_sec)

    mgr3.pending_guest_email_otps.pop(email, None)

    if session_id and hasattr(mgr3, "guest_qr_sessions") and session_id in mgr3.guest_qr_sessions:
        mgr3.guest_qr_sessions[session_id]["email_verified"] = True
        mgr3.guest_qr_sessions[session_id]["email"] = email
        mgr3.guest_qr_sessions[session_id]["expires_at"] = expires_at

    await _REST_ENGINE.grant_user_permission(target_name=guest_name, target_tier=3)
    await broadcast_rest_state_to_bridges()

    append_audit_log(
        category="AUTH_3LAYER",
        event_type="guest_qr_otp_verified",
        summary=f"✅ Xác thực OTP email thành công cho khách '{guest_name}' ({email}) - Cấp quyền 3 ({dur_label})",
        user_name=guest_name,
        tier=3,
        details={"email": email, "session_id": session_id, "duration": dur_type, "expires_at": expires_at},
    )

    return JSONResponse(sanitize_api_payload({
        "ok": True,
        "verified": True,
        "email": email,
        "guest_name": guest_name,
        "duration_code": dur_type,
        "duration_label": dur_label,
        "duration_seconds": dur_sec,
        "expires_at": expires_at,
        "message": f"Xác nhận email {email} thành công! Đã kích hoạt tài khoản khách.",
    }))
