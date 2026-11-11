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
- while not self._closed:
- self.last_mic_turn_blocked
"""

from __future__ import annotations

import os
import pathlib
import subprocess
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
from simulator.auth.session_store import resolve_strict_ws_session
from simulator.api.routes_guest import router as guest_invite_router
from simulator.api.enrollment_gone import EnrollmentGoneMiddleware
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
app.include_router(guest_invite_router)
app.add_middleware(EnrollmentGoneMiddleware)

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


@app.get("/guest_legacy_removed")
@app.get("/guest_enroll_legacy_removed")
@app.get("/guest-qr_legacy_removed")
async def guest_enroll_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "guest_enroll.html")


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


def _resolve_deployment_version_info() -> dict[str, Any]:
    commit_sha = (
        os.environ.get("APP_GIT_COMMIT_SHA", "").strip()
        or os.environ.get("VERCEL_GIT_COMMIT_SHA", "").strip()
        or os.environ.get("GIT_COMMIT_SHA", "").strip()
    )
    branch = (
        os.environ.get("APP_GIT_BRANCH", "").strip()
        or os.environ.get("VERCEL_GIT_COMMIT_REF", "").strip()
    )
    if not commit_sha:
        try:
            commit_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(ROOT),
                stderr=subprocess.DEVNULL,
                timeout=2.0,
            ).decode("utf-8").strip()
        except Exception:
            commit_sha = "unknown"
    if not branch:
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(ROOT),
                stderr=subprocess.DEVNULL,
                timeout=2.0,
            ).decode("utf-8").strip()
        except Exception:
            branch = "master"
    return {
        "ok": True,
        "commit_sha": commit_sha,
        "short_sha": commit_sha[:7] if commit_sha and commit_sha != "unknown" else commit_sha,
        "branch": branch,
        "version": "3.8.0",
        "voice_model": MODEL,
        "single_voice": "Aoede",
    }


@app.get("/api/version")
@app.get("/api/health/version")
async def api_version() -> JSONResponse:
    """Trả về mã băm commit SHA triển khai hiện tại (Deployment SHA Proof)."""
    return JSONResponse(_resolve_deployment_version_info())


# Cầu nối WebSocket Gemini 3.8 Live Bidirectional Streaming
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Tiếp nhận kết nối WebSocket từ trình duyệt Web 3D / Micro thu âm, xác thực phiên server-side và ủy quyền sang LiveBridgeSession."""
    await websocket.accept()
    ws_session = resolve_strict_ws_session(websocket)
    isolated_engine = _REST_ENGINE.create_isolated_ws_view()
    session = LiveBridgeSession(
        websocket=websocket,
        engine=isolated_engine,
        voice_auth=_BOOT_VOICE_AUTH,
        ws_session=ws_session,
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
