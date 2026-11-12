"""Các endpoint đăng ký / xác minh giọng nói đã gỡ: luôn trả HTTP 410."""

from __future__ import annotations

from starlette.responses import JSONResponse

ENROLLMENT_GONE_PATHS = frozenset(
    {
        "/api/auth3/enroll_first_page_voice",
        "/api/auth3/enroll_voice_sample",
        "/api/mobile/enroll_voice",
        "/api/voice_auth/enroll_tier_pcm",
        "/api/voice_enroll",
        "/api/voice/enroll",
        "/api/auth3/layer3_voice",
        "/api/auth3/guest_qr_complete_voice",
        "/api/auth3/guest_qr_complete_voice_alias",
        "/api/voice/enroll_tier_pcm",
        "/api/auth3/enroll_voice",
        "/api/auth/enroll_voice",
        "/api/auth3/layer3_verify_voice",
        "/api/auth3/guest/enroll_voice",
        "/api/qr/guest_enroll",
        "/api/auth3/invite_oauth_start",
        "/api/auth3/invite_verify_otp",
        "/api/auth3/guest_qr_handshake",
        "/api/auth3/guest_handshake",
        "/api/auth3/guest/handshake",
        "/api/auth3/guest_qr_send_otp",
        "/api/auth3/guest_qr_verify_otp",
        "/api/auth3/guest/verify_email",
    }
)

_GONE_BODY = {
    "ok": False,
    "gone": True,
    "error": "Đã gỡ đăng ký giọng nói và xác minh người nói. Hãy đăng nhập (mật khẩu / OTP) hoặc dùng mã mời khách do chủ nhà tạo.",
}


def is_enrollment_gone_path(path: str) -> bool:
    raw = str(path or "").rstrip("/")
    if raw in ENROLLMENT_GONE_PATHS:
        return True
    # Một số alias kết thúc bằng /enroll_voice hoặc layer3_voice
    if raw.endswith("/enroll_first_page_voice") or raw.endswith("/enroll_voice_sample"):
        return True
    if raw.endswith("/guest_qr_complete_voice") or raw.endswith("/enroll_voice") or raw.endswith("/guest_enroll"):
        return True
    return raw in ENROLLMENT_GONE_PATHS


class EnrollmentGoneMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and is_enrollment_gone_path(scope.get("path") or ""):
            response = JSONResponse(_GONE_BODY, status_code=410)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
