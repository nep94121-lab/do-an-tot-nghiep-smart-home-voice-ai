"""Shared Dependencies and Engine State Singletons for Smart Home Simulator API Routers.

Cung cấp các đối tượng Singleton trung tâm:
- _REST_ENGINE: Instance SmartHomeEngine dùng chung cho REST APIs.
- _BOOT_VOICE_AUTH: Instance VoiceAuthManager dùng cho khởi tạo & kiểm thử.
- _ACTIVE_BRIDGES: Danh sách các WebSocket session Gemini Live đang hoạt động.
- _KNOWLEDGE_RAG: Instance SmartHomeKnowledgeRAG.
- broadcast_rest_state_to_bridges: Đồng bộ snapshot trạng thái phần cứng sang tất cả bridge.
"""

from __future__ import annotations

import asyncio
import copy
import os
import pathlib
from typing import Any

from backend.knowledge_rag import SmartHomeKnowledgeRAG
from backend.rule_engine import SmartHomeEngine
from backend.voice_auth import VoiceAuthManager

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
AUDIO_DIR = ROOT / "test_audio"
STATIC_DIR = ROOT / "web"
MOBILE_APP_DIR = ROOT / "web" / "mobile"

_ACTIVE_BRIDGES: list[Any] = []
_BOOT_VOICE_AUTH = VoiceAuthManager(AUDIO_DIR)


async def _send_ws_safe(br: Any, payload: dict[str, Any], *, broadcast: bool = True) -> None:
    if getattr(br, "_closed", False):
        return
    try:
        await asyncio.wait_for(br.send_ws_json(payload, broadcast=broadcast), timeout=0.25)
    except TypeError:
        try:
            from backend.auth.tier_permissions import filter_ws_event_for_session

            ws_sess = getattr(br, "_cached_ws_actor", None)
            if ws_sess is None and hasattr(br, "_resolve_ws_session"):
                ws_sess = br._resolve_ws_session()
            filtered = filter_ws_event_for_session(payload, ws_sess, broadcast=broadcast)
            if filtered is None:
                return
            await asyncio.wait_for(br.send_ws_json(filtered), timeout=0.25)
        except Exception:
            pass
    except Exception:
        pass


async def _emit_to_all_active_bridges(event: dict[str, Any]) -> None:
    """Phát sự kiện trực tiếp từ _REST_ENGINE tới SSE hub và toàn bộ WebSocket đang hoạt động."""
    try:
        from backend.realtime_hub import get_realtime_hub

        ev_type = str(event.get("type") or "engine_event") if isinstance(event, dict) else "engine_event"
        if ev_type != "mqtt_packet":
            get_realtime_hub().publish_snapshot(_REST_ENGINE, reason=ev_type)
    except Exception:
        pass
    bridges = [br for br in list(_ACTIVE_BRIDGES) if not getattr(br, "_closed", False)]
    if bridges:
        try:
            await asyncio.wait_for(
                asyncio.gather(*(_send_ws_safe(br, event, broadcast=True) for br in bridges), return_exceptions=True),
                timeout=0.35,
            )
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


async def broadcast_rest_state_to_bridges(
    *,
    exclude_bridge: Any = None,
    sync_engine: bool = True,
) -> None:
    """Đồng bộ trạng thái thiết bị vật lý của REST Engine sang SSE hub và mọi WebSocket song song."""
    if sync_engine:
        try:
            _REST_ENGINE.sync_from_shared_store(force=True)
        except Exception:
            pass
    try:
        from backend.realtime_hub import get_realtime_hub

        get_realtime_hub().publish_snapshot(_REST_ENGINE, reason="rest_broadcast")
    except Exception:
        pass
    bridges = [br for br in list(_ACTIVE_BRIDGES) if not getattr(br, "_closed", False)]
    if not bridges:
        return
    full_snap = _REST_ENGINE.get_snapshot(sync=False)
    tasks: list[Any] = []
    for br in bridges:
        try:
            br.engine.server_connected = _REST_ENGINE.server_connected
            if br.engine is not _REST_ENGINE:
                br.engine._last_synced_seq = getattr(_REST_ENGINE, "_last_synced_seq", 0)
                br.engine._last_synced_ts_ns = getattr(_REST_ENGINE, "_last_synced_ts_ns", 0)
            if br.engine.devices is not _REST_ENGINE.devices:
                br.engine.devices = copy.deepcopy(_REST_ENGINE.devices)
            if br.engine.mqtt_bridge is not _REST_ENGINE.mqtt_bridge:
                br.engine.mqtt_bridge.esp8266_status = copy.deepcopy(_REST_ENGINE.mqtt_bridge.esp8266_status)
                br.engine.mqtt_bridge.dht11_telemetry = copy.deepcopy(_REST_ENGINE.mqtt_bridge.dht11_telemetry)
                br.engine.mqtt_bridge.soil_moisture_telemetry = copy.deepcopy(_REST_ENGINE.mqtt_bridge.soil_moisture_telemetry)
                if hasattr(_REST_ENGINE.mqtt_bridge, "sound_telemetry") and hasattr(br.engine.mqtt_bridge, "sound_telemetry"):
                    br.engine.mqtt_bridge.sound_telemetry = copy.deepcopy(_REST_ENGINE.mqtt_bridge.sound_telemetry)
            if exclude_bridge is not None and br is exclude_bridge:
                continue
            tasks.append(_send_ws_safe(br, {"type": "state_snapshot", "snapshot": full_snap}, broadcast=True))
        except Exception:
            pass
    if tasks:
        try:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=0.35)
        except Exception:
            pass


# Alias tương thích
_broadcast_rest_state_to_bridges = broadcast_rest_state_to_bridges


_LAST_LOADED_KEY: str = ""


def _read_key_from_env_file(env_file: pathlib.Path) -> str:
    if not env_file.is_file():
        return ""
    try:
        for raw_line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("GEMINI_API_KEY="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'").strip()
                if val:
                    return val
    except OSError:
        return ""
    return ""


def load_key() -> str:
    """Đọc GEMINI_API_KEY từ biến môi trường, SMARTHOME_ENV_FILE, hoặc tệp .env."""
    global _LAST_LOADED_KEY
    env_val = os.environ.get("GEMINI_API_KEY", "").strip().strip('"').strip("'").strip()
    if env_val:
        _LAST_LOADED_KEY = env_val
        return env_val

    custom_env = os.environ.get("SMARTHOME_ENV_FILE", "").strip()
    if custom_env:
        val = _read_key_from_env_file(pathlib.Path(custom_env))
        if val:
            _LAST_LOADED_KEY = val
            return val

    val = _read_key_from_env_file(ROOT / ".env")
    if val:
        _LAST_LOADED_KEY = val
        return val
    return ""


KEY = load_key()


def safe_str(msg: object) -> str:
    """Che key nếu xuất hiện trong log hoặc thông báo lỗi."""
    s = str(msg)
    for secret in (KEY, _LAST_LOADED_KEY, os.environ.get("GEMINI_API_KEY", "").strip().strip('"').strip("'").strip()):
        if secret:
            s = s.replace(secret, "***")
    return s
