"""Simulator API Package — Modular Routers & Dependencies for Smart Home Voice AI.

Exports:
- devices_router: Điều khiển thiết bị phần cứng, cảm biến và Wokwi (Feature 14)
- auth_router: Xác thực 3 tầng, Google OAuth/OTP và danh sách gia đình (Feature 15)
- qr_router: Quản lý mã QR động TOTP 10s & thu âm giọng khách C3 (Feature 16)
- logs_router: Quản trị nhật ký kiểm toán, CSDL SQLite WAL và tri thức RAG (Feature 17)
- deps: Các đối tượng singletons dùng chung toàn bộ simulator
"""

from __future__ import annotations

from simulator.api.deps import (
    _ACTIVE_BRIDGES,
    _BOOT_VOICE_AUTH,
    _KNOWLEDGE_RAG,
    _REST_ENGINE,
    _emit_to_all_active_bridges,
    broadcast_rest_state_to_bridges,
    get_active_bridges,
    get_boot_voice_auth,
    get_knowledge_rag,
    get_rest_engine,
)
from simulator.api.routes_auth import router as auth_router
from simulator.api.routes_devices import router as devices_router
from simulator.api.routes_logs import router as logs_router
from simulator.api.routes_qr import router as qr_router

__all__ = [
    "devices_router",
    "auth_router",
    "qr_router",
    "logs_router",
    "_REST_ENGINE",
    "_BOOT_VOICE_AUTH",
    "_ACTIVE_BRIDGES",
    "_KNOWLEDGE_RAG",
    "_emit_to_all_active_bridges",
    "broadcast_rest_state_to_bridges",
    "get_knowledge_rag",
    "get_rest_engine",
    "get_boot_voice_auth",
    "get_active_bridges",
]
