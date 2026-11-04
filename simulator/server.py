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

import pathlib
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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


@app.get("/app")
async def mobile_app_index() -> FileResponse:
    return FileResponse(MOBILE_APP_DIR / "index.html")


@app.get("/wokwi")
async def wokwi_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "wokwi.html")


@app.get("/logs")
async def logs_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "logs.html")


@app.get("/auth")
async def auth_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "auth.html")


@app.get("/guest_enroll")
@app.get("/guest-qr")
async def guest_enroll_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "guest_enroll.html")


@app.get("/archify")
async def archify_architecture_page() -> FileResponse:
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
