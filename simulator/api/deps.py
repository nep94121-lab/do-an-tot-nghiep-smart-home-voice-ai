"""Shared Dependencies and Engine State Singletons for Smart Home Simulator API Routers.

Cung cấp các đối tượng Singleton trung tâm:
- _REST_ENGINE: Instance SmartHomeEngine dùng chung cho REST APIs.
- _BOOT_VOICE_AUTH: Instance VoiceAuthManager dùng cho khởi tạo & kiểm thử.
- _ACTIVE_BRIDGES: Danh sách các WebSocket session Gemini Live đang hoạt động.
- _KNOWLEDGE_RAG: Instance SmartHomeKnowledgeRAG.
- broadcast_rest_state_to_bridges: Đồng bộ snapshot trạng thái phần cứng sang tất cả bridge.
"""

from __future__ import annotations

import copy
import os
import pathlib
from typing import Any

from simulator.knowledge_rag import SmartHomeKnowledgeRAG
from simulator.rule_engine import SmartHomeEngine
from simulator.voice_auth import VoiceAuthManager

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
AUDIO_DIR = ROOT / "test_audio"
STATIC_DIR = ROOT / "simulator" / "static"
MOBILE_APP_DIR = ROOT / "mobile_app"

_ACTIVE_BRIDGES: list[Any] = []
_BOOT_VOICE_AUTH = VoiceAuthManager(AUDIO_DIR)


async def _emit_to_all_active_bridges(event: dict[str, Any]) -> None:
    """Phát sự kiện trực tiếp từ _REST_ENGINE tới toàn bộ các kết nối WebSocket đang hoạt động."""
    for br in list(_ACTIVE_BRIDGES):
        try:
            await br.send_ws_json(event)
        except Exception:
            pass


_REST_ENGINE = SmartHomeEngine(
    on_event=_emit_to_all_active_bridges,
    on_voice_reset=_BOOT_VOICE_AUTH.reset_to_owner_only,
)
_KNOWLEDGE_RAG = SmartHomeKnowledgeRAG()


def get_knowledge_rag() -> SmartHomeKnowledgeRAG:
    """Trả về Singleton kho tri thức RAG."""
    return _KNOWLEDGE_RAG


def get_rest_engine() -> SmartHomeEngine:
    """Trả về Singleton engine quản trị thiết bị và luật."""
    return _REST_ENGINE


def get_boot_voice_auth() -> VoiceAuthManager:
    """Trả về Singleton quản trị sinh trắc học giọng nói."""
    return _BOOT_VOICE_AUTH


def get_active_bridges() -> list[Any]:
    """Trả về danh sách các phiên kết nối WebSocket Gemini Live đang hoạt động."""
    return _ACTIVE_BRIDGES


async def broadcast_rest_state_to_bridges() -> None:
    """Đồng bộ trạng thái thiết bị vật lý của REST Engine sang các kết nối WebSocket đang hoạt động mà không ghi đè danh tính người nói riêng của từng phiên."""
    pub_snap = _REST_ENGINE.get_public_device_snapshot()
    for br in list(_ACTIVE_BRIDGES):
        try:
            br.engine.server_connected = _REST_ENGINE.server_connected
            if br.engine.devices is not _REST_ENGINE.devices:
                br.engine.devices = copy.deepcopy(_REST_ENGINE.devices)
            if br.engine.mqtt_bridge is not _REST_ENGINE.mqtt_bridge:
                br.engine.mqtt_bridge.esp8266_status = copy.deepcopy(_REST_ENGINE.mqtt_bridge.esp8266_status)
                br.engine.mqtt_bridge.dht11_telemetry = copy.deepcopy(_REST_ENGINE.mqtt_bridge.dht11_telemetry)
                br.engine.mqtt_bridge.soil_moisture_telemetry = copy.deepcopy(_REST_ENGINE.mqtt_bridge.soil_moisture_telemetry)
                br.engine.mqtt_bridge.ir_devices = copy.deepcopy(_REST_ENGINE.mqtt_bridge.ir_devices)
            snap_for_br = (
                br.engine.get_snapshot()
                if getattr(br.engine, "current_tier", 99) == 1
                else pub_snap
            )
            await br.send_ws_json({"type": "state_snapshot", "snapshot": snap_for_br})
        except Exception:
            pass


# Alias tương thích
_broadcast_rest_state_to_bridges = broadcast_rest_state_to_bridges


def load_key() -> str:
    """Đọc GEMINI_API_KEY từ .env hoặc biến môi trường."""
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("GEMINI_API_KEY="):
                val = line.split("=", 1)[1].strip()
                if val:
                    return val
    return os.environ.get("GEMINI_API_KEY", "").strip()


KEY = load_key()


def safe_str(msg: object) -> str:
    """Che key nếu xuất hiện trong log hoặc thông báo lỗi."""
    s = str(msg)
    if KEY:
        return s.replace(KEY, "***")
    return s
