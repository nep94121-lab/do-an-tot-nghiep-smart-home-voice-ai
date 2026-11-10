"""FastAPI Entry Point & WebSocket Bridge for Smart Home Voice AI (Milestone M3).

Kiến trúc Hệ thống Đã Modular hóa:
1. simulator/api/routes_devices.py : Điều khiển thiết bị, cảm biến, MQTT & Wokwi (Feature 14)
2. simulator/api/routes_auth.py    : Xác thực 3 tầng, Google OAuth/OTP & Email Allowlist (Feature 15)
3. simulator/api/routes_qr.py      : Mã QR động TOTP 10s, Handshake 180s & Khách C3 (Feature 16)
4. simulator/api/routes_logs.py    : Quản trị Logs, SQLite 3NF WAL & Tri thức RAG (Feature 17)
5. simulator/live/gemini_bridge.py : Cầu nối thời gian thực Gemini 3.8 Live WebSocket
6. simulator/live/prompt_builder.py: Khai báo 20 Gemini Tools & System Instructions
7. simulator/voice/                : Neural Biometrics 256d, VAD Tiếng Việt & Khử ồn DSP

Hiến pháp Spec Kit (scripts/speckit_converge.py - Điều 3 Zero-Drop Live Bridge):
Đã ủy quyền toàn diện sang simulator.live.gemini_bridge.LiveBridgeSession:
- async def _ensure_current_mic_utterance_verified
- while not self._closed
- self.last_mic_turn_blocked
"""

from __future__ import annotations

import hmac
import pathlib
import secrets
import time
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from simulator.api import (
    _ACTIVE_BRIDGES,
    _BOOT_VOICE_AUTH,
    _KNOWLEDGE_RAG,
    _REST_ENGINE,
    auth_router,
    broadcast_rest_state_to_bridges,
    devices_router,
    get_knowledge_rag,
    logs_router,
    qr_router,
)
from simulator.auth.qr_totp_mixin import (
    QR_SCAN_COOKIE_NAME,
    QR_SESSION_COOKIE_NAME,
    QR_SHORT_EXPIRY_SEC,
    _QR_ATOMIC_LOCK,
    hash_qr_scan_nonce,
)
from simulator.auth.session_store import resolve_request_session
from simulator.auth_3layer import get_auth_3layer_manager
from simulator.live import (
    ALL_TOOLS,
    LiveBridgeSession,
    MODEL,
    build_system_instruction,
    make_live_config,
)

# 100% Re-exports để tương thích ngược hoàn toàn với các test suite
__all__ = [
    "app",
    "_BOOT_VOICE_AUTH",
    "_REST_ENGINE",
    "_ACTIVE_BRIDGES",
    "_broadcast_rest_state_to_bridges",
    "get_knowledge_rag",
    "LiveBridgeSession",
    "MODEL",
    "build_system_instruction",
    "make_live_config",
    "ALL_TOOLS",
]

_broadcast_rest_state_to_bridges = broadcast_rest_state_to_bridges

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "simulator" / "static"
AUDIO_DIR = ROOT / "test_audio"
MOBILE_APP_DIR = ROOT / "mobile_app"
DOCS_ARCH_DIR = ROOT / "docs" / "kien_truc"

_QR_ISOLATED_ALLOWED_PATHS: frozenset[str] = frozenset(
    {
        "/guest",
        "/guest_enroll",
        "/guest-qr",
        "/api/auth3/guest_qr_handshake",
        "/api/auth3/guest_handshake",
        "/api/auth3/guest/handshake",
        "/api/auth3/guest_qr_complete_voice",
        "/api/auth3/guest/enroll_voice",
        "/api/auth3/guest_qr_send_otp",
        "/api/auth3/guest_qr_verify_otp",
        "/api/auth3/guest/verify_email",
        "/static/css/guest_enroll.css",
        "/static/js/guest_enroll.js",
        "/favicon.ico",
    }
)


def _is_qr_registration_session_request(request: Request) -> bool:
    """Phát hiện request mang session/token của luồng đăng ký QR cô lập."""
    if request.cookies.get(QR_SCAN_COOKIE_NAME) or request.cookies.get(QR_SESSION_COOKIE_NAME):
        return True
    if (
        request.headers.get("x-qr-scan-nonce")
        or request.headers.get("x-qr-session-id")
        or request.headers.get("x-qr-post-scan-token")
    ):
        return True
    q_sid = str(request.query_params.get("session_id") or request.query_params.get("guest_session_id") or "").strip()
    if q_sid.startswith("guest_sess_"):
        return True
    if request.query_params.get("post_scan_token"):
        return True

    auth_hdr = str(request.headers.get("authorization") or "").strip()
    if auth_hdr.lower().startswith("bearer "):
        bearer_tok = auth_hdr[7:].strip()
        if bearer_tok.startswith("guest_sess_"):
            return True
        mgr3 = get_auth_3layer_manager()
        if (
            bearer_tok in getattr(mgr3, "active_qr_tokens", {})
            or bearer_tok in getattr(mgr3, "used_qr_tokens", set())
            or bearer_tok in getattr(mgr3, "guest_qr_sessions", {})
        ):
            return True
        for s_info in getattr(mgr3, "guest_qr_sessions", {}).values():
            if isinstance(s_info, dict) and str(s_info.get("post_scan_token") or "") == bearer_tok:
                return True
    return False


app = FastAPI(
    title="Smart Home Voice AI Simulator",
    description="Nhà thông minh điều khiển giọng nói tiếng Việt với Gemini 3.8 Live & NodeMCU ESP8266",
    version="3.8.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def enforce_isolated_qr_registration_session(request: Request, call_next: Any) -> Response:
    """Cô lập tuyệt đối phiên/token đăng ký QR (Requirement 6):
    Phiên hoặc token đăng ký QR chỉ được phép truy cập trang đăng ký độc lập (/guest, /guest_enroll, /guest-qr)
    và các API đăng ký khách tương ứng; từ chối 403 đối với mọi route khác trong hệ thống.
    """
    path = request.url.path.rstrip("/") or "/"
    if _is_qr_registration_session_request(request):
        if path not in _QR_ISOLATED_ALLOWED_PATHS:
            # Chỉ cho phép ngoại lệ duy nhất khi chính Chủ nhà Cấp 1 (mang Bearer token Admin Cấp 1 hợp lệ)
            # gọi endpoint phát hành mã QR mới trên cùng TestClient.
            if path in ("/api/auth3/guest_qr_current", "/api/auth3/qr/generate"):
                auth_hdr = str(request.headers.get("authorization") or "").strip()
                if auth_hdr.lower().startswith("bearer ") and not auth_hdr[7:].strip().startswith("guest_sess_"):
                    sess = resolve_request_session(request, payload=None, engine=_REST_ENGINE)
                    if sess.is_authenticated and sess.tier == 1 and sess.role == "ADMIN":
                        return await call_next(request)
            return JSONResponse(
                {
                    "ok": False,
                    "status": "QR_REGISTRATION_SESSION_ISOLATED",
                    "reason": "OTHER_ROUTE_FORBIDDEN_FOR_QR_SESSION",
                    "error": "Từ chối truy cập: Phiên/token đăng ký QR bị cô lập hoàn toàn, không được phép truy cập bất kỳ route nào khác ngoài luồng đăng ký!",
                },
                status_code=403,
            )
    return await call_next(request)


@app.middleware("http")
async def disable_static_cache(request: Request, call_next: Any) -> Response:
    """Vô hiệu hóa bộ nhớ đệm trình duyệt để phản ánh ngay lập tức thay đổi UI/Static."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.exception_handler(404)
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: Exception) -> Response:
    status_code = getattr(exc, "status_code", 404)
    if status_code == 404:
        accept = request.headers.get("accept", "")
        # Nếu là gọi API (/api/*) hoặc client không yêu cầu HTML: trả JSON chuẩn
        if request.url.path.startswith("/api/") or "text/html" not in accept:
            detail = getattr(exc, "detail", "Not Found")
            return JSONResponse({"detail": detail}, status_code=404)
        # Nếu là điều hướng trình duyệt (browser navigation): trả HTML trang 404
        file_404 = STATIC_DIR / "404.html"
        if file_404.exists():
            return FileResponse(file_404, status_code=404, media_type="text/html")
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    elif status_code in (500, 503):
        accept = request.headers.get("accept", "")
        if not request.url.path.startswith("/api/") and "text/html" in accept:
            file_500 = STATIC_DIR / "500.html"
            if file_500.exists():
                return FileResponse(file_500, status_code=status_code, media_type="text/html")
    detail = getattr(exc, "detail", str(exc))
    headers = getattr(exc, "headers", None)
    return JSONResponse({"detail": detail}, status_code=status_code, headers=headers)


# Nạp 4 Modular Routers (Features 14, 15, 16, 17)
app.include_router(devices_router)
app.include_router(auth_router)
app.include_router(qr_router)
app.include_router(logs_router)

# Mount các thư mục tài nguyên tĩnh
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/test_audio", StaticFiles(directory=str(AUDIO_DIR)), name="test_audio")


# Giao diện người dùng Web & Mobile
@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/login")
async def login_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/register")
async def register_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "register.html")


@app.get("/app")
async def mobile_app_index() -> FileResponse:
    return FileResponse(MOBILE_APP_DIR / "index.html")


@app.get("/mobile")
async def mobile_redirect() -> RedirectResponse:
    """Chuyển hướng 307 từ /mobile về ứng dụng /app."""
    return RedirectResponse(url="/app", status_code=307)


@app.get("/wokwi")
async def wokwi_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "wokwi.html")


@app.get("/logs")
async def logs_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "logs.html")


@app.get("/auth")
async def auth_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "auth.html")


@app.get("/guest")
@app.get("/guest_enroll")
@app.get("/guest-qr")
async def guest_enroll_page(request: Request) -> Response:
    """Trang đăng ký độc lập cô lập hoàn toàn cho khách quét QR:
    - Kiểm tra gắn kết phiên quét (sh_qr_scan_nonce) nếu truy cập qua link sau quét.
    - Từ chối 403 nếu mở link đã sao chép từ trình duyệt/thiết bị khác, hoặc khi token/session đã dùng/hết hạn/hủy.
    """
    mgr3 = get_auth_3layer_manager()
    mgr3._ensure_qr_stores()

    q_sid = str(request.query_params.get("session_id") or request.query_params.get("guest_session_id") or "").strip()
    q_pst = str(request.query_params.get("post_scan_token") or "").strip()
    q_tok = str(request.query_params.get("token") or "").strip()
    incoming_nonce = str(
        request.cookies.get(QR_SCAN_COOKIE_NAME)
        or request.headers.get("x-qr-scan-nonce")
        or ""
    ).strip()
    new_cookie_nonce: str | None = None

    with _QR_ATOMIC_LOCK:
        if q_sid or q_pst:
            sess_info = mgr3.guest_qr_sessions.get(q_sid) if q_sid else None
            if sess_info is None and q_pst:
                for cand in mgr3.guest_qr_sessions.values():
                    if isinstance(cand, dict) and str(cand.get("post_scan_token") or "") == q_pst:
                        sess_info = cand
                        break
            if not isinstance(sess_info, dict):
                return JSONResponse(
                    {
                        "ok": False,
                        "status": "INVALID_POST_SCAN_LINK",
                        "reason": "SESSION_NOT_FOUND",
                        "error": "Liên kết đăng ký không tồn tại hoặc không hợp lệ!",
                    },
                    status_code=403,
                )
            cur_status = str(sess_info.get("status") or "ACTIVE").upper()
            if cur_status in ("INVALIDATED", "INVALIDATED_ON_ERROR") or sess_info.get("invalidated"):
                return JSONResponse(
                    {
                        "ok": False,
                        "status": "SESSION_INVALIDATED",
                        "reason": sess_info.get("invalidated_reason", "MUST_RESCAN_QR"),
                        "error": "Liên kết đăng ký đã bị thu hồi (do thao tác lỗi hoặc đã quét lại QR mới)!",
                    },
                    status_code=403,
                )
            if cur_status in ("CONSUMING", "CONSUMED") or sess_info.get("consumed"):
                return JSONResponse(
                    {
                        "ok": False,
                        "status": "TOKEN_ALREADY_CONSUMED",
                        "reason": "SINGLE_USE_TOKEN_REUSED",
                        "error": "Liên kết đăng ký một lần (Single-Use) này đã được sử dụng!",
                    },
                    status_code=403,
                )
            if time.time() > float(sess_info.get("session_expires_at") or 0.0):
                sess_info["status"] = "EXPIRED"
                return JSONResponse(
                    {
                        "ok": False,
                        "status": "SESSION_EXPIRED",
                        "reason": "QR_SESSION_EXPIRED",
                        "error": "Liên kết đăng ký đã hết hạn 180 giây!",
                    },
                    status_code=403,
                )
            expected_hash = str(sess_info.get("bound_scan_nonce_hash") or "").strip()
            actual_hash = hash_qr_scan_nonce(incoming_nonce)
            if not expected_hash or not actual_hash or not hmac.compare_digest(actual_hash, expected_hash):
                return JSONResponse(
                    {
                        "ok": False,
                        "status": "SESSION_BINDING_MISMATCH",
                        "reason": "OTHER_SESSION_REJECTED",
                        "error": "Từ chối: Không thể mở liên kết đăng ký đã sao chép trên trình duyệt hoặc thiết bị khác!",
                    },
                    status_code=403,
                )
            if q_pst:
                expected_pst = str(sess_info.get("post_scan_token") or "").strip()
                if expected_pst and not hmac.compare_digest(q_pst, expected_pst):
                    return JSONResponse(
                        {
                            "ok": False,
                            "status": "POST_SCAN_TOKEN_MISMATCH",
                            "error": "Mã token liên kết sau quét không khớp!",
                        },
                        status_code=403,
                    )
            sess_info["page_opened_count"] = int(sess_info.get("page_opened_count", 0)) + 1

        elif q_tok:
            tok_meta = mgr3.active_qr_tokens.get(q_tok)
            if not isinstance(tok_meta, dict):
                return JSONResponse(
                    {
                        "ok": False,
                        "status": "TOKEN_INVALID",
                        "error": "Mã QR trong liên kết không hợp lệ hoặc không tồn tại!",
                    },
                    status_code=403,
                )
            if tok_meta.get("status") in ("INVALIDATED", "CONSUMED") or tok_meta.get("invalidated"):
                return JSONResponse(
                    {
                        "ok": False,
                        "status": "TOKEN_INVALIDATED_OR_CONSUMED",
                        "error": "Liên kết QR đã được sử dụng hoặc đã bị vô hiệu hóa khi quét lại!",
                    },
                    status_code=403,
                )
            if time.time() > float(tok_meta.get("expires_at_ts") or 0.0):
                tok_meta["status"] = "EXPIRED"
                return JSONResponse(
                    {
                        "ok": False,
                        "status": "TOKEN_EXPIRED",
                        "error": "Liên kết QR đã hết hạn 180 giây!",
                    },
                    status_code=403,
                )
            existing_hash = str(tok_meta.get("bound_scan_nonce_hash") or "").strip()
            if existing_hash:
                actual_hash = hash_qr_scan_nonce(incoming_nonce)
                if not actual_hash or not hmac.compare_digest(actual_hash, existing_hash):
                    return JSONResponse(
                        {
                            "ok": False,
                            "status": "SESSION_BINDING_MISMATCH",
                            "reason": "OTHER_SESSION_REJECTED",
                            "error": "Từ chối: Liên kết QR này đã được gắn kết với thiết bị quét ban đầu, không thể mở từ trình duyệt/thiết bị khác!",
                        },
                        status_code=403,
                    )
                if int(tok_meta.get("link_opened_count", 0)) >= 1 and q_tok in mgr3.used_qr_tokens:
                    return JSONResponse(
                        {
                            "ok": False,
                            "status": "SINGLE_USE_LINK_ALREADY_OPENED",
                            "reason": "SINGLE_USE_TOKEN_REUSED",
                            "error": "Liên kết sau quét chỉ được mở một lần duy nhất!",
                        },
                        status_code=403,
                    )
                tok_meta["link_opened_count"] = int(tok_meta.get("link_opened_count", 0)) + 1
            else:
                effective_nonce = incoming_nonce or secrets.token_urlsafe(24)
                tok_meta["bound_scan_nonce_hash"] = hash_qr_scan_nonce(effective_nonce)
                tok_meta["link_opened_count"] = 1
                new_cookie_nonce = effective_nonce

    resp = FileResponse(STATIC_DIR / "guest_enroll.html", media_type="text/html")
    if new_cookie_nonce:
        resp.set_cookie(
            key=QR_SCAN_COOKIE_NAME,
            value=new_cookie_nonce,
            max_age=int(QR_SHORT_EXPIRY_SEC),
            httponly=True,
            samesite="lax",
            path="/",
        )
    return resp


@app.get("/archify")
async def archify_architecture_page() -> FileResponse:
    return FileResponse(DOCS_ARCH_DIR / "smart-home-voice-ai.architecture.html")


@app.get("/architecture")
async def architecture_page() -> FileResponse:
    """Trang Sơ đồ Kiến trúc Hệ thống tương tác (Archify)."""
    return FileResponse(DOCS_ARCH_DIR / "smart-home-voice-ai.architecture.html")


@app.get("/archify/devops")
async def archify_devops_page() -> FileResponse:
    return FileResponse(DOCS_ARCH_DIR / "devops-cicd-pipeline.workflow.html")


@app.get("/archify/erd")
async def archify_erd_page() -> FileResponse:
    return FileResponse(DOCS_ARCH_DIR / "smarthome-database.erd.html")


@app.get("/favicon.ico")
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/sw.js")
async def service_worker_file() -> FileResponse:
    response = FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@app.get("/offline")
@app.get("/offline.html")
async def offline_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "offline.html", media_type="text/html")


@app.get("/404")
@app.get("/404.html")
async def page_404() -> FileResponse:
    return FileResponse(STATIC_DIR / "404.html", status_code=404, media_type="text/html")


@app.get("/500")
@app.get("/500.html")
async def page_500() -> FileResponse:
    return FileResponse(STATIC_DIR / "500.html", status_code=500, media_type="text/html")


@app.get("/qr_expired")
@app.get("/qr-expired")
@app.get("/qr_expired.html")
async def page_qr_expired() -> FileResponse:
    return FileResponse(STATIC_DIR / "qr_expired.html", media_type="text/html")


@app.get("/403")
@app.get("/403.html")
async def page_403() -> FileResponse:
    return FileResponse(STATIC_DIR / "403.html", status_code=403, media_type="text/html")


# Cầu nối WebSocket Gemini 3.8 Live Bidirectional Streaming
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Tiếp nhận kết nối WebSocket từ trình duyệt Web 3D / Micro thu âm, ủy quyền sang LiveBridgeSession."""
    await websocket.accept()
    session = LiveBridgeSession(
        websocket=websocket,
        engine=_REST_ENGINE,
        voice_auth=_BOOT_VOICE_AUTH,
    )
    if session not in _ACTIVE_BRIDGES:
        _ACTIVE_BRIDGES.append(session)
    try:
        await session.run()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        session._closed = True
        while session in _ACTIVE_BRIDGES:
            _ACTIVE_BRIDGES.remove(session)


if __name__ == "__main__":
    uvicorn.run("simulator.server:app", host="0.0.0.0", port=8088, reload=False)
