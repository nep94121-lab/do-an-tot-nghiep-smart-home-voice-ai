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

import asyncio
import contextlib
import hashlib
import json
import logging
from email.utils import formatdate
from logging.handlers import RotatingFileHandler
import os
import pathlib
import subprocess
from typing import Any
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from simulator.api import (
    _ACTIVE_BRIDGES,
    _BOOT_VOICE_AUTH,
    _KNOWLEDGE_RAG,
    _REST_ENGINE,
    auth_router,
    automation_router,
    broadcast_rest_state_to_bridges,
    devices_router,
    get_knowledge_rag,
    logs_router,
    qr_router,
)
from simulator.auth.session_store import resolve_request_session, resolve_strict_ws_session
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


def _configure_rotating_file_logging() -> None:
    """Thiết lập ghi nhật ký xoay vòng UTF-8 khi chạy máy chủ thường trú."""
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("VERCEL") == "1":
        return
    explicit_log_dir = os.environ.get("SMARTHOME_LOG_DIR", "").strip()
    log_dir = (
        pathlib.Path(explicit_log_dir)
        if explicit_log_dir
        else pathlib.Path(r"C:\Users\LENOVO\.smarthome_server\logs")
    )
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "server.log"
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            if isinstance(handler, RotatingFileHandler) and pathlib.Path(handler.baseFilename) == log_path:
                return
        fh = RotatingFileHandler(
            str(log_path),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        root_logger.addHandler(fh)
        if root_logger.level == logging.NOTSET or root_logger.level > logging.INFO:
            root_logger.setLevel(logging.INFO)
    except Exception:
        pass


_configure_rotating_file_logging()

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


def _compute_file_etag(stat_result: os.stat_result) -> str:
    etag_base = f"{stat_result.st_mtime}-{stat_result.st_size}"
    digest = hashlib.md5(etag_base.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f'"{digest}"'


def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    raw = if_none_match.strip()
    if raw == "*":
        return True
    norm_target = etag.removeprefix("W/").strip()
    for part in raw.split(","):
        if part.strip().removeprefix("W/").strip() == norm_target:
            return True
    return False


def _serve_cached_html(request: Request | None, file_path: pathlib.Path) -> Response:
    stat_result = os.stat(file_path)
    etag = _compute_file_etag(stat_result)
    last_modified = formatdate(stat_result.st_mtime, usegmt=True)
    headers = {
        "Cache-Control": "private, max-age=0, must-revalidate",
        "ETag": etag,
        "Last-Modified": last_modified,
    }
    if request is not None and request.method in ("GET", "HEAD") and _etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return FileResponse(file_path, media_type="text/html", stat_result=stat_result, headers=headers)


def _require_authenticated_page(
    request: Request,
    *,
    max_tier: int = 2,
    next_path: str = "/",
) -> Response | None:
    """Enforce session authentication on protected HTML routes before rendering."""
    sess = resolve_request_session(request)
    if not sess.is_authenticated or sess.is_expired():
        target = f"/login?next={quote(next_path, safe='/')}"
        return RedirectResponse(
            url=target,
            status_code=302,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    if sess.tier > max_tier:
        file_403 = STATIC_DIR / "403.html"
        if file_403.exists():
            return FileResponse(
                file_403,
                status_code=403,
                media_type="text/html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
        return HTMLResponse(
            "<h1>403 Forbidden</h1><p>Bạn không có quyền truy cập trang này.</p>",
            status_code=403,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return None


@app.middleware("http")
async def configure_http_cache_headers(request: Request, call_next: Any) -> Response:
    """Bật cache ETag/304 cho /static/* và HTML; chặn trực tiếp HTML bảo vệ và giữ no-store cho /api/*."""
    path = request.url.path or "/"
    low_path = path.lower()
    if low_path in ("/static/wokwi.html", "/static/logs.html", "/static/guest_enroll.html"):
        max_tier = 1 if ("logs" in low_path or "guest_enroll" in low_path) else 2
        next_target = "/logs" if "logs" in low_path else ("/wokwi" if "wokwi" in low_path else "/")
        denied = _require_authenticated_page(request, max_tier=max_tier, next_path=next_target)
        if denied is not None:
            return denied
    response = await call_next(request)
    if low_path in ("/wokwi", "/logs", "/static/wokwi.html", "/static/logs.html"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    if (path.startswith("/static/") or path.startswith("/test_audio/")) and response.status_code in (200, 304):
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    if path == "/sw.js" and response.status_code in (200, 304):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response
    if "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


class ConditionalGZipMiddleware:
    """Bỏ qua nén GZip với luồng SSE /api/events để không đệm sự kiện thời gian thực."""

    def __init__(self, app: Any, minimum_size: int = 500) -> None:
        self.app = app
        self.gzip_app = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and scope.get("path") == "/api/events":
            await self.app(scope, receive, send)
            return
        await self.gzip_app(scope, receive, send)


app.add_middleware(ConditionalGZipMiddleware, minimum_size=500)


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
app.include_router(automation_router)
app.include_router(qr_router)
app.include_router(logs_router)
app.include_router(guest_invite_router)
app.add_middleware(EnrollmentGoneMiddleware)

from simulator.auth.security_state import SecurityStateUnavailable


@app.exception_handler(SecurityStateUnavailable)
async def security_store_unavailable(request: Request, exc: SecurityStateUnavailable) -> JSONResponse:
    return JSONResponse({"ok": False, "error": "Kho bảo mật tạm thời không khả dụng. Hãy thử lại sau."}, status_code=503)

# Mount các thư mục tài nguyên tĩnh
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/test_audio", StaticFiles(directory=str(AUDIO_DIR)), name="test_audio")


# Giao diện người dùng Web & Mobile
@app.get("/")
async def index(request: Request) -> Response:
    return _serve_cached_html(request, STATIC_DIR / "index.html")


@app.get("/login")
async def login_page(request: Request) -> Response:
    return _serve_cached_html(request, STATIC_DIR / "login.html")


@app.get("/register")
async def register_page(request: Request) -> Response:
    return _serve_cached_html(request, STATIC_DIR / "register.html")


@app.get("/app")
async def mobile_app_index(request: Request) -> Response:
    return _serve_cached_html(request, MOBILE_APP_DIR / "index.html")


@app.get("/mobile")
async def mobile_redirect() -> RedirectResponse:
    """Chuyển hướng 307 từ /mobile về ứng dụng /app."""
    return RedirectResponse(url="/app", status_code=307)


@app.get("/hardware/blender/SCENE_SPEC.json")
async def get_blender_scene_spec() -> JSONResponse:
    """Trả về SCENE_SPEC.json khi đã có trên đĩa hoặc HTTP 404 JSON gọn khi chưa merge nhánh CAD."""
    spec_path = ROOT / "hardware" / "blender" / "SCENE_SPEC.json"
    if not spec_path.exists() or not spec_path.is_file():
        return JSONResponse(
            {"ok": False, "error": "SCENE_SPEC.json not found"},
            status_code=404,
        )
    try:
        data = json.loads(spec_path.read_text(encoding="utf-8"))
        return JSONResponse(data, status_code=200)
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "error": f"Invalid SCENE_SPEC.json: {exc}"},
            status_code=500,
        )


@app.get("/wokwi")
async def wokwi_page(request: Request) -> Response:
    denied = _require_authenticated_page(request, max_tier=2, next_path="/wokwi")
    if denied is not None:
        return denied
    return _serve_cached_html(request, STATIC_DIR / "wokwi.html")


@app.get("/logs")
async def logs_page(request: Request) -> Response:
    denied = _require_authenticated_page(request, max_tier=1, next_path="/logs")
    if denied is not None:
        return denied
    return _serve_cached_html(request, STATIC_DIR / "logs.html")


@app.get("/auth")
async def auth_page(request: Request) -> Response:
    return _serve_cached_html(request, STATIC_DIR / "auth.html")


@app.get("/guest_guide")
@app.get("/guest_guide/")
async def guest_guide_page(request: Request) -> Response:
    return _serve_cached_html(request, STATIC_DIR / "guest_guide.html")


@app.get("/guest_legacy_removed")
@app.get("/guest_enroll_legacy_removed")
@app.get("/guest-qr_legacy_removed")
async def guest_enroll_page(request: Request) -> Response:
    denied = _require_authenticated_page(request, max_tier=1, next_path="/")
    if denied is not None:
        return denied
    return _serve_cached_html(request, STATIC_DIR / "guest_enroll.html")


@app.get("/archify")
async def archify_architecture_page(request: Request) -> Response:
    return _serve_cached_html(request, DOCS_ARCH_DIR / "smart-home-voice-ai.architecture.html")


@app.get("/architecture")
async def architecture_page(request: Request) -> Response:
    """Trang Sơ đồ Kiến trúc Hệ thống tương tác (Archify)."""
    return _serve_cached_html(request, DOCS_ARCH_DIR / "smart-home-voice-ai.architecture.html")


@app.get("/archify/devops")
async def archify_devops_page(request: Request) -> Response:
    return _serve_cached_html(request, DOCS_ARCH_DIR / "devops-cicd-pipeline.workflow.html")


@app.get("/archify/erd")
async def archify_erd_page(request: Request) -> Response:
    return _serve_cached_html(request, DOCS_ARCH_DIR / "smarthome-database.erd.html")


@app.get("/docs/phan_cung/mica/MICA_PANELS.md")
async def hardware_mica_panels_doc() -> Response:
    doc_path = ROOT / "docs" / "phan_cung" / "mica" / "MICA_PANELS.md"
    if not doc_path.exists() or not doc_path.is_file():
        return JSONResponse({"ok": False, "error": "MICA_PANELS.md not found"}, status_code=404)
    return FileResponse(doc_path, media_type="text/markdown; charset=utf-8")


@app.get("/docs/phan_cung/DIMENSIONS_AUDIT.md")
async def hardware_dimensions_audit_doc() -> Response:
    doc_path = ROOT / "docs" / "phan_cung" / "DIMENSIONS_AUDIT.md"
    if not doc_path.exists() or not doc_path.is_file():
        return JSONResponse({"ok": False, "error": "DIMENSIONS_AUDIT.md not found"}, status_code=404)
    return FileResponse(doc_path, media_type="text/markdown; charset=utf-8")


@app.get("/hardware/kicad/smarthome_hub/bom.csv")
async def hardware_kicad_bom() -> Response:
    bom_path = ROOT / "hardware" / "kicad" / "smarthome_hub" / "bom.csv"
    if not bom_path.exists() or not bom_path.is_file():
        return JSONResponse({"ok": False, "error": "bom.csv not found"}, status_code=404)
    return FileResponse(bom_path, media_type="text/csv; charset=utf-8")


@app.get("/docs/phan_cung/WIRING_TABLE.md")
async def hardware_wiring_table_doc() -> Response:
    doc_path = ROOT / "docs" / "phan_cung" / "WIRING_TABLE.md"
    if not doc_path.exists() or not doc_path.is_file():
        return JSONResponse({"ok": False, "error": "WIRING_TABLE.md not found"}, status_code=404)
    return FileResponse(doc_path, media_type="text/markdown; charset=utf-8")


@app.get("/docs/phan_cung/wiring_diagram_2d.svg")
async def hardware_wiring_diagram_svg() -> Response:
    doc_path = ROOT / "docs" / "phan_cung" / "wiring_diagram_2d.svg"
    if not doc_path.exists() or not doc_path.is_file():
        return JSONResponse({"ok": False, "error": "wiring_diagram_2d.svg not found"}, status_code=404)
    return FileResponse(doc_path, media_type="image/svg+xml; charset=utf-8")


@app.get("/docs/phan_cung/wiring_diagram_2d.png")
async def hardware_wiring_diagram_png() -> Response:
    doc_path = ROOT / "docs" / "phan_cung" / "wiring_diagram_2d.png"
    if not doc_path.exists() or not doc_path.is_file():
        return JSONResponse({"ok": False, "error": "wiring_diagram_2d.png not found"}, status_code=404)
    return FileResponse(doc_path, media_type="image/png")


@app.get("/docs/phan_cung/wiring_diagram_2d.pdf")
async def hardware_wiring_diagram_pdf() -> Response:
    doc_path = ROOT / "docs" / "phan_cung" / "wiring_diagram_2d.pdf"
    if not doc_path.exists() or not doc_path.is_file():
        return JSONResponse({"ok": False, "error": "wiring_diagram_2d.pdf not found"}, status_code=404)
    return FileResponse(doc_path, media_type="application/pdf")


@app.get("/hardware/blender/system_wired_assembly.glb")
async def hardware_wired_assembly_glb() -> Response:
    glb_path = ROOT / "hardware" / "blender" / "system_wired_assembly.glb"
    if not glb_path.exists() or not glb_path.is_file():
        return JSONResponse({"ok": False, "error": "system_wired_assembly.glb not found"}, status_code=404)
    return FileResponse(glb_path, media_type="model/gltf-binary")


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
async def page_qr_expired(request: Request) -> Response:
    qr_file = STATIC_DIR / "qr_expired.html"
    reason = str(request.query_params.get("reason") or "").strip().lower()
    if reason == "used":
        html = qr_file.read_text(encoding="utf-8")
        html = html.replace(
            "<title>Mã QR hết hạn · Nhà thông minh</title>",
            "<title>Mã QR đã được sử dụng · Nhà thông minh</title>",
        ).replace(
            '<h1 id="qrExpiredTitle">Mã QR đã hết hạn</h1>',
            '<h1 id="qrExpiredTitle">Mã QR đã được sử dụng</h1>',
        ).replace(
            '<p id="qrExpiredDesc" class="muted">Mã QR này đã hết hạn hoặc đã được sử dụng một lần.</p>',
            '<p id="qrExpiredDesc" class="muted">Mã QR này chỉ có hiệu lực cho lần quét đầu tiên và đã được kích hoạt trên thiết bị khác.</p>',
        )
        return HTMLResponse(html, media_type="text/html", headers={"Cache-Control": "no-store"})
    return FileResponse(qr_file, media_type="text/html", headers={"Cache-Control": "no-store"})


@app.get("/403")
@app.get("/403.html")
async def page_403() -> FileResponse:
    return FileResponse(STATIC_DIR / "403.html", status_code=403, media_type="text/html")


_CACHED_GIT_SHA: str | None = None
_CACHED_GIT_BRANCH: str | None = None


def _resolve_deployment_version_info() -> dict[str, Any]:
    global _CACHED_GIT_SHA, _CACHED_GIT_BRANCH
    commit_sha = (
        os.environ.get("VERCEL_GIT_COMMIT_SHA", "").strip()
        or os.environ.get("APP_GIT_COMMIT_SHA", "").strip()
        or os.environ.get("GIT_COMMIT_SHA", "").strip()
    )
    branch = (
        os.environ.get("VERCEL_GIT_COMMIT_REF", "").strip()
        or os.environ.get("APP_GIT_BRANCH", "").strip()
    )
    if not commit_sha:
        if _CACHED_GIT_SHA is None:
            try:
                _CACHED_GIT_SHA = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(ROOT),
                    stderr=subprocess.DEVNULL,
                    timeout=2.0,
                ).decode("utf-8").strip() or "unknown"
            except Exception:
                _CACHED_GIT_SHA = "unknown"
        commit_sha = _CACHED_GIT_SHA
    if not branch:
        if _CACHED_GIT_BRANCH is None:
            try:
                _CACHED_GIT_BRANCH = subprocess.check_output(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=str(ROOT),
                    stderr=subprocess.DEVNULL,
                    timeout=2.0,
                ).decode("utf-8").strip() or "master"
            except Exception:
                _CACHED_GIT_BRANCH = "master"
        branch = _CACHED_GIT_BRANCH
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


@app.get("/api/health")
async def api_health() -> JSONResponse:
    """Kiểm tra sức khỏe máy chủ thường trú, SQLite WAL, số bảng 3NF và kết nối real-time."""
    from simulator.db_migrations import open_wal_connection, resolve_sqlite_db_path
    from simulator.realtime_hub import get_realtime_hub

    sqlite_ok = False
    journal_mode = ""
    table_count = 0
    db_path = resolve_sqlite_db_path()
    conn = None
    try:
        conn = open_wal_connection(db_path, readonly=True) if db_path.exists() else open_wal_connection(db_path, readonly=False)
        ping = conn.execute("SELECT 1").fetchone()
        jm_row = conn.execute("PRAGMA journal_mode;").fetchone()
        journal_mode = str(jm_row[0] if jm_row else "").lower()
        table_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
        )
        sqlite_ok = bool(ping and ping[0] == 1)
    except Exception:
        sqlite_ok = False
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()

    hub = get_realtime_hub()
    stt_warm = {"ready": False, "cold_start_ms": 0.0, "models": []}
    try:
        from simulator.voice.vietnamese_stt import get_local_stt_warm_state

        stt_warm = get_local_stt_warm_state()
    except Exception:
        pass
    status_code = 200 if sqlite_ok else 503
    payload = {
        "ok": sqlite_ok,
        "status": "healthy" if sqlite_ok else "degraded",
        "sqlite_ok": sqlite_ok,
        "journal_mode": journal_mode,
        "table_count": table_count,
        "realtime_subscribers": hub.subscriber_count(),
        "active_ws_bridges": len(_ACTIVE_BRIDGES),
        "stt_warm": bool(stt_warm.get("ready")),
        "stt_cold_start_ms": float(stt_warm.get("cold_start_ms") or 0.0),
        "stt_models": list(stt_warm.get("models") or []),
        **_resolve_deployment_version_info(),
    }
    return JSONResponse(payload, status_code=status_code, headers={"Cache-Control": "no-store"})


_SCHEDULER_TASK: asyncio.Task[Any] | None = None


async def _automation_scheduler_loop() -> None:
    from simulator.api.routes_automation import run_scheduler_tick_once

    while True:
        try:
            await run_scheduler_tick_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(1.0)


@app.on_event("startup")
async def _on_server_startup_prewarm() -> None:
    global _SCHEDULER_TASK
    _BOOT_VOICE_AUTH.reset_strikes()
    try:
        await _REST_ENGINE.restore_timers_from_sqlite()
    except Exception:
        pass
    if _SCHEDULER_TASK is None or _SCHEDULER_TASK.done():
        _SCHEDULER_TASK = asyncio.create_task(_automation_scheduler_loop())
    if (
        os.environ.get("PYTEST_CURRENT_TEST")
        or os.environ.get("PYTEST", "").strip() == "1"
        or os.environ.get("VERCEL", "").strip() == "1"
        or os.environ.get("SMARTHOME_UPSTREAM_URL", "").strip()
    ):
        return
    if os.environ.get("SMARTHOME_DISABLE_LOCAL_STT", "0").strip() != "1" and os.environ.get("SMARTHOME_SKIP_STT_PRELOAD", "0").strip() != "1":
        async def _delayed_preload_local_stt() -> None:
            # Yield briefly so uvicorn finishes binding its HTTP socket before heavy torch/ONNX imports.
            await asyncio.sleep(0.6)
            try:
                from simulator.voice.vietnamese_stt import preload_local_stt_models

                await asyncio.to_thread(preload_local_stt_models)
            except Exception:
                pass

        asyncio.create_task(_delayed_preload_local_stt())
    if os.environ.get("SIMULATOR_OFFLINE_SANDBOX", "").strip() == "1":
        return
    try:
        from simulator.live.tts_rejection_vi import prewarm_aoede_common_phrases

        asyncio.create_task(prewarm_aoede_common_phrases())
    except Exception:
        pass


@app.on_event("shutdown")
async def _on_server_shutdown_cleanup() -> None:
    global _SCHEDULER_TASK
    if _SCHEDULER_TASK is not None and not _SCHEDULER_TASK.done():
        _SCHEDULER_TASK.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await _SCHEDULER_TASK
    _SCHEDULER_TASK = None


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
