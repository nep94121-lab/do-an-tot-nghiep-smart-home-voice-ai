"""Các endpoint đăng ký / xác minh giọng nói đã gỡ: luôn trả HTTP 410."""

from __future__ import annotations

from starlette.responses import HTMLResponse, JSONResponse

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

_GONE_HTML = """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover" />
  <title>Tính năng đã gỡ · Nhà thông minh</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="/static/css/style.css" />
</head>
<body>
  <div class="auth-wrapper">
    <section class="auth-card" aria-labelledby="gone-title">
      <div class="mark" aria-hidden="true">
        <svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></svg>
      </div>
      <p class="eyebrow">THÔNG BÁO HỆ THỐNG</p>
      <div class="auth-header" style="text-align:left;margin-bottom:16px;">
        <h1 id="gone-title">Tính năng đăng ký cũ đã được gỡ bỏ</h1>
        <p style="margin-top:8px;">Tính năng đã gỡ, hãy quét mã mời mới do Chủ nhà tạo để vào điều khiển thiết bị.</p>
      </div>
      <div class="status-box status-error" style="margin-bottom:18px;">
        Đường dẫn đăng ký giọng nói / khách cũ không còn hoạt động vì lý do bảo mật. Vui lòng nhận mã QR hoặc liên kết mời còn hiệu lực từ Chủ nhà.
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;">
        <a href="/guest_guide" class="btn btn-primary" style="flex:1 1 180px;">Hướng dẫn cho Khách</a>
        <a href="/app" class="btn btn-secondary" style="flex:1 1 140px;">Mở Ứng dụng</a>
        <a href="/" class="btn btn-secondary" style="flex:1 1 120px;">Trang chủ</a>
      </div>
    </section>
  </div>
</body>
</html>
"""


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
            raw_path = str(scope.get("path") or "")
            method = str(scope.get("method") or "GET").upper()
            if not raw_path.startswith("/api/") and method in ("GET", "HEAD"):
                response = HTMLResponse(_GONE_HTML, status_code=410)
            else:
                response = JSONResponse(_GONE_BODY, status_code=410)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
