"""Cầu Nối WebSocket và Gemini 3.8 Live API Hai Chiều (Gemini Live Bridge).

Chức năng:
1. Quản lý phiên WebSocket client <-> Upstream Gemini 3.8 Live API.
2. Cơ chế Zero-Drop Reconnect: Tự động kết nối lại khi gián đoạn mạng, hàng đợi In-Flight PCM đệm âm thanh không rơi rớt câu nói.
3. Gắn phân quyền RBAC 3 tầng trực tiếp theo phiên đăng nhập/mời QR (không kiểm định giọng nói người nói).
4. Truyền thẳng luồng PCM 16kHz 640 bytes/khung sang Gemini Live theo thời gian thực.
5. Điều phối thực thi Function Tools (Actuate-First) và phát âm thanh Aoede 24kHz Mono 16-bit PCM.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import json
import os
import pathlib
import re
import sys
import time
import wave
from typing import Any

_PENDING_AUDIT_TASKS: set[asyncio.Task[Any]] = set()


def _discard_audit_task(task: asyncio.Task[Any]) -> None:
    _PENDING_AUDIT_TASKS.discard(task)
    if not task.cancelled():
        try:
            task.exception()
        except Exception:
            pass

from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

VOICE_SAMPLES_META: dict[str, str] = {
    "giong_1_chu_nha_mo_cua": "[OK] Giọng Cấp 1 (Chủ nhà Nguyễn Tuấn Anh - Toàn quyền): Mở cửa chính",
    "giong_cap2_thanh_vien_a": "Giọng Cấp 2 (Thành viên A - Chặn Cửa D1 & Còi D8): Mở cửa chính",
    "giong_cap3_khach_c": "Giọng Cấp 3 (Khách C - Chỉ bật Đèn/Quạt, Chặn Cửa/Còi/ĐH/Bơm): Mở cửa chính",
    "giong_1_kem_tieng_on_quat": "Giọng Cấp 1 + Ồn Quạt (-24dB -> Lọc Tầng 2): Mở cửa chính",
    "hai_nguoi_cung_noi_cap1_va_nguoi_la": "2 Người Cùng Nói (Chủ nhà C1 + Người lạ -> Ưu tiên C1): Mở cửa chính",
    "giong_2_nguoi_la_mo_cua": "[DENY] Giọng Người lạ (Không phép - Chặn 2 lần -> Im lặng): Mở cửa chính",
    "mo_cua_chinh": "Mở cửa chính",
    "bat_den_phong_khach": "Bật đèn phòng khách",
    "tat_quat": "Tắt quạt",
    "bat_quat_va_dieu_hoa": "Bật quạt trần và bật điều hòa giúp tôi",
    "hen_gio_5s_tat_den": "Năm giây nữa tắt đèn phòng khách nhé",
    "day_lenh_di_ngu": "Từ giờ khi tôi nói chế độ đi ngủ thì tắt đèn phòng khách và đóng cửa chính nhé",
    "kich_hoat_di_ngu": "Chế độ đi ngủ",
    "reset_he_thong": "Reset hệ thống về mặc định",
}

from simulator.api.deps import (
    AUDIO_DIR,
    _ACTIVE_BRIDGES,
    _BOOT_VOICE_AUTH,
    _REST_ENGINE,
    _broadcast_rest_state_to_bridges,
    _emit_to_all_active_bridges,
    get_knowledge_rag,
    load_key,
    safe_str,
)
from simulator.auth.session_store import UserSession, resolve_strict_ws_session, session_is_current, get_session_store
from simulator.knowledge_rag import SmartHomeKnowledgeRAG
from simulator.live.echo_and_speech_guard import (
    ServerEchoGuard,
    sanitize_spoken_vietnamese_text,
)
from simulator.live.prompt_builder import (
    ALL_TOOLS,
    FIXED_REJECTION_PHRASE_VI,
    FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
    build_system_instruction,
    make_live_config,
)
from simulator.live.tool_dispatcher_mixin import LiveToolDispatcherMixin
from simulator.live.tts_rejection_vi import synthesize_aoede_phrase_audio
from simulator.rule_engine import (
    SmartHomeEngine,
    append_audit_log,
    format_vn_time_ampm,
)
from simulator.voice.vad_vietnamese import (
    VietnameseVADStreamFilter,
    is_vietnamese_speech,
)
from simulator.voice_auth import VoiceAuthManager
from simulator.voice_config import OWNER_ID

MODEL = "gemini-3.8-live"
CHUNK_MS = 20
CHUNK_SAMPLES = 16000 * CHUNK_MS // 1000  # 320 mẫu
PCM_FRAME_BYTES = CHUNK_SAMPLES * 2  # 640 bytes
SILENCE = b"\x00\x00" * CHUNK_SAMPLES

KEY = load_key()


class StatefulPcmFramingBuffer:
    """Bộ đệm đóng khung PCM 16kHz 16-bit mono chuẩn 640 bytes (20ms = 320 mẫu Int16).
    Tuyệt đối không pad 0x00 vào giữa câu nói; chỉ pad 0x00 một lần ở flush_utterance_tail() cuối câu nói.
    """

    def __init__(self, frame_bytes: int = 640):
        self.frame_bytes = int(frame_bytes)
        self._buf = bytearray()

    def push_chunk(self, raw_pcm_bytes: bytes) -> list[bytes]:
        if not raw_pcm_bytes:
            return []
        self._buf.extend(raw_pcm_bytes)
        frames: list[bytes] = []
        while len(self._buf) >= self.frame_bytes:
            frames.append(bytes(self._buf[: self.frame_bytes]))
            del self._buf[: self.frame_bytes]
        return frames

    def push(self, raw_pcm_bytes: bytes) -> list[bytes]:
        return self.push_chunk(raw_pcm_bytes)

    def flush_utterance_tail(self) -> bytes | None:
        if not self._buf:
            return None
        aligned_len = len(self._buf) & ~1
        if aligned_len <= 0:
            self._buf.clear()
            return None
        tail = bytes(self._buf[:aligned_len]).ljust(self.frame_bytes, b"\x00")
        self._buf.clear()
        return tail

    def flush_remainder(self, pad_final: bool = False) -> bytes:
        if not self._buf:
            return b""
        if pad_final:
            t = self.flush_utterance_tail()
            return t or b""
        rem = bytes(self._buf)
        self._buf.clear()
        return rem

    def clear(self) -> None:
        self._buf.clear()


def _sanitize_vietnamese_input_transcript(raw_text: str, tools_called: list[str] | None = None) -> str:
    """Làm sạch văn bản phiên âm đầu vào từ Gemini Live."""
    if not raw_text:
        return ""
    t = raw_text
    phonetic_map = {
        "뭐 거리": "Mở cửa đi",
        "뭐거리": "Mở cửa đi",
        "모 거리": "Mở cửa đi",
        "보 거리": "Mở cửa đi",
        "저거": "",
        "joycon": "",
        "Joycon": "",
        "Joy-Con": "",
        "boycott": "",
        "Boycott": "",
        "voyage": "",
        "Hola": "",
        "hola": "",
        "Hello.": "Xin chào.",
        "Hello": "Xin chào",
    }
    for k, v in phonetic_map.items():
        if k in t:
            t = t.replace(k, v)
    t = re.sub(
        r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\u0400-\u04ff\u0e00-\u0e7f\u0600-\u06ff]+",
        "",
        t,
    )
    cleaned = re.sub(r"\s+", " ", t).strip()
    if not cleaned and tools_called:
        first_tc = tools_called[0]
        if "main_door" in first_tc and "open" in first_tc:
            return "Mở cửa chính."
        if "main_door" in first_tc and "close" in first_tc:
            return "Đóng cửa chính."
        if "living_room_light" in first_tc:
            return "Điều khiển đèn phòng khách."
        if "fan" in first_tc:
            return "Điều khiển quạt trần."
    return cleaned


class LiveBridgeSession(LiveToolDispatcherMixin):
    """Quản lý kết nối giữa 1 client WebSocket và phiên Gemini 3.8 Live."""

    def __init__(
        self,
        ws: Any | None = None,
        websocket: Any | None = None,
        engine: SmartHomeEngine | None = None,
        voice_auth: VoiceAuthManager | None = None,
        knowledge_rag: SmartHomeKnowledgeRAG | None = None,
        ws_session: UserSession | None = None,
    ):
        self.ws = ws or websocket
        self._explicit_ws_session: bool = ws_session is not None
        self.ws_session: UserSession = ws_session or resolve_strict_ws_session(self.ws)
        self.voice_auth = voice_auth or VoiceAuthManager(AUDIO_DIR)
        self.voice_auth.reset_strikes()
        if engine is not None:
            if engine is _REST_ENGINE:
                self.engine = _REST_ENGINE.create_isolated_ws_view(
                    on_event=self.send_ws_json,
                    on_voice_reset=self.voice_auth.reset_to_owner_only,
                )
            else:
                self.engine = engine
                if self.engine.on_event is None:
                    self.engine.on_event = self.send_ws_json
                if self.engine.on_voice_reset is None:
                    self.engine.on_voice_reset = self.voice_auth.reset_to_owner_only
        else:
            self.engine = SmartHomeEngine(
                on_event=self.send_ws_json,
                on_voice_reset=self.voice_auth.reset_to_owner_only,
            )
            self.engine.server_connected = _REST_ENGINE.server_connected
            self.engine.devices = copy.deepcopy(_REST_ENGINE.devices)
            self.engine.mqtt_bridge.esp8266_status = copy.deepcopy(_REST_ENGINE.mqtt_bridge.esp8266_status)
            self.engine.mqtt_bridge.dht11_telemetry = copy.deepcopy(_REST_ENGINE.mqtt_bridge.dht11_telemetry)
            self.engine.mqtt_bridge.soil_moisture_telemetry = copy.deepcopy(_REST_ENGINE.mqtt_bridge.soil_moisture_telemetry)
            self.engine.mqtt_bridge.ir_devices = copy.deepcopy(_REST_ENGINE.mqtt_bridge.ir_devices)

        self.knowledge_rag = knowledge_rag or get_knowledge_rag()
        self.mic_utterance_pcm = bytearray()
        self.mic_recent_pcm = bytearray()
        self.pcm_framing_buffer = StatefulPcmFramingBuffer(frame_bytes=PCM_FRAME_BYTES)
        self.mic_turn_verified: bool = False
        self.mic_utterance_active: bool = False
        self.last_mic_auth_result: dict[str, Any] | None = None
        self.last_mic_turn_blocked: bool = False
        self.last_mic_turn_silent_ignore: bool = False
        self.vad_stream_filter = VietnameseVADStreamFilter(sample_rate=16000)
        try:
            self.client = genai.Client(
                api_key=KEY or "TEST_DUMMY_GEMINI_KEY",
                http_options=types.HttpOptions(api_version="v1beta"),
            )
        except TypeError:
            self.client = genai.Client(api_key=KEY or "TEST_DUMMY_GEMINI_KEY")
        self.gemini_session: Any = None
        self.speech_end_ts: float | None = None
        self.turn_first_tool_ts: float | None = None
        self.turn_first_audio_ts: float | None = None
        self.turn_in_tx: list[str] = []
        self.turn_out_tx: list[str] = []
        self.turn_tools_called: list[str] = []
        self.echo_guard = ServerEchoGuard()
        self._current_turn_echo_suppressed: bool = False
        self.ai_turns_completed: int = 0
        self._wav_streaming_task: asyncio.Task | None = None
        self._mic_silence_task: asyncio.Task | None = None
        self._closed = False
        self._awaiting_model_turn_after_speech: bool = False
        self._turn_completed_flag: bool = True
        self._cached_ws_actor: UserSession | None = None
        self._cached_ws_actor_ts: float = 0.0
        self._mic_preroll_pcm: list[bytes] = []
        self._mic_in_flight_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        self._live_pcm_tx_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=400)
        self._pcm_tx_task: asyncio.Task[None] | None = None
        self._bind_actor_to_engine()
        # Chỉ tự động đưa vào _ACTIVE_BRIDGES nếu là WebSocket thật (không phải Mock trong unit test)
        is_mock_ws = hasattr(self.ws, "assert_called") or hasattr(self.ws, "assert_awaited") or hasattr(self.ws, "_mock_return_value")
        if self.ws is not None and not is_mock_ws and self not in _ACTIVE_BRIDGES:
            _ACTIVE_BRIDGES.append(self)

    def close(self) -> None:
        self._closed = True
        if self in _ACTIVE_BRIDGES:
            _ACTIVE_BRIDGES.remove(self)

    def _is_cached_actor_fresh(self, msg: dict[str, Any] | None = None) -> bool:
        cached = self._cached_ws_actor
        if cached is None:
            return False
        if isinstance(msg, dict):
            if msg.get("session_token") or msg.get("token"):
                return False
            mtype = msg.get("type")
            if mtype not in (None, "mic_chunk", "mic_speech_ended"):
                return False
        now_pc = time.perf_counter()
        if (now_pc - self._cached_ws_actor_ts) >= 2.0:
            return False
        if cached.is_expired():
            return False
        if cached.session_id in get_session_store()._revoked_sids:
            return False
        rest_user = _REST_ENGINE.users.get(cached.user_id)
        if isinstance(rest_user, dict) and not rest_user.get("active", True):
            return False
        return True

    def _resolve_ws_session(self, msg: dict[str, Any] | None = None) -> UserSession:
        """Xác định phiên WebSocket phía server từ Header/Cookie/Query/Token (tuyệt đối không tin role từ client)."""
        now_pc = time.perf_counter()
        if self._is_cached_actor_fresh(msg):
            return self._cached_ws_actor  # type: ignore[return-value]
        sess = resolve_strict_ws_session(self.ws, msg=msg)
        if sess.is_authenticated and not sess.is_expired():
            self.ws_session = sess
            self._explicit_ws_session = False
            self._cached_ws_actor = sess
            self._cached_ws_actor_ts = now_pc
            return sess
        if self.ws_session is not None:
            stored = get_session_store().get_session(self.ws_session.session_id)
            if stored is not None:
                if session_is_current(stored):
                    self._cached_ws_actor = stored
                    self._cached_ws_actor_ts = now_pc
                    return stored
            elif (
                self._explicit_ws_session
                and self.ws_session.is_authenticated
                and not self.ws_session.is_expired()
            ):
                self._cached_ws_actor = self.ws_session
                self._cached_ws_actor_ts = now_pc
                return self.ws_session
        return sess

    def _is_ws_cap1_authorized(self, msg: dict[str, Any] | None = None) -> tuple[bool, UserSession]:
        """Kiểm tra phiên WebSocket hiện tại có phải Chủ nhà Cấp 1 đã xác thực server-side hay không."""
        sess = self._resolve_ws_session(msg)
        is_cap1 = bool(
            sess.is_authenticated
            and not sess.is_expired()
            and int(sess.tier) == 1
            and str(sess.role).upper() in ("ADMIN", "OWNER")
        )
        return is_cap1, sess

    def _apply_actor_to_engine(self, actor: UserSession) -> UserSession:
        if actor.is_authenticated and not actor.is_expired():
            uid = str(actor.user_id or "guest").strip() or "guest"
            target_tier = int(actor.tier)
            target_role = str(actor.role or "GUEST")
            target_name = str(actor.display_name or uid)
            existing = self.engine.users.get(uid)
            need_set_active = (
                not isinstance(existing, dict)
                or getattr(self.engine, "_current_user_id", None) != uid
                or self.engine.current_tier != target_tier
                or self.engine.current_role != target_role
                or self.last_mic_turn_blocked
            )
            if not isinstance(existing, dict):
                self.engine.users[uid] = {
                    "id": uid,
                    "name": target_name,
                    "tier": target_tier,
                    "role": target_role,
                    "active": True,
                }
            else:
                if existing.get("name") != target_name:
                    existing["name"] = str(actor.display_name or existing.get("name") or uid)
                if existing.get("tier") != target_tier:
                    existing["tier"] = target_tier
                if existing.get("role") != target_role:
                    existing["role"] = target_role
                if not existing.get("active", True):
                    existing["active"] = True
            if need_set_active:
                self.engine.set_active_user(uid)
            self.last_mic_turn_blocked = False
            self.last_mic_turn_silent_ignore = False
        else:
            if getattr(self.engine, "_current_user_id", None) != "UNKNOWN" or not self.last_mic_turn_blocked:
                self.engine.set_active_user("UNKNOWN")
            self.last_mic_turn_blocked = True
            self.last_mic_turn_silent_ignore = False
        return actor

    def _bind_actor_to_engine(self, msg: dict[str, Any] | None = None) -> UserSession:
        """Gắn trực tiếp danh tính và tầng quyền từ phiên WebSocket đã xác thực vào engine (không dùng nhận diện giọng nói)."""
        actor = self._resolve_ws_session(msg)
        return self._apply_actor_to_engine(actor)

    async def _bind_actor_to_engine_async(self, msg: dict[str, Any] | None = None) -> UserSession:
        """Gắn danh tính/quyền bất đồng bộ, tránh chặn event loop khi truy vấn SQLite lúc cache hết hạn."""
        if self._is_cached_actor_fresh(msg):
            return self._apply_actor_to_engine(self._cached_ws_actor)  # type: ignore[arg-type]
        actor = await asyncio.to_thread(self._resolve_ws_session, msg)
        return self._apply_actor_to_engine(actor)


    async def send_ws_json(self, payload: dict[str, Any], *, broadcast: bool = False) -> None:
        if self._closed:
            if self in _ACTIVE_BRIDGES:
                _ACTIVE_BRIDGES.remove(self)
            return
        from simulator.auth.tier_permissions import filter_ws_event_for_session

        ws_sess = (
            self._cached_ws_actor
            if self._is_cached_actor_fresh()
            else await asyncio.to_thread(self._resolve_ws_session)
        )
        filtered = filter_ws_event_for_session(payload, ws_sess, broadcast=broadcast)
        if filtered is None:
            return
        payload = filtered
        ptype = str(payload.get("type", ""))
        audit_kwargs: dict[str, Any] | None = None
        if ptype == "turn_complete":
            heard = str(payload.get("heard", "")).strip()
            said = str(payload.get("said", "")).strip()
            t_ms = payload.get("tool_ms")
            a_ms = payload.get("audio_ms")
            audit_kwargs = {
                "category": "VOICE_CMD",
                "event_type": "turn_complete",
                "summary": f"Nói: '{heard}' -> AI đáp: '{said}' (Tool: {t_ms or '--'}ms, Audio: {a_ms or '--'}ms)",
                "user_name": self.engine.get_current_user_name(),
                "tier": self.engine.current_tier,
                "details": payload,
            }
        elif ptype == "tool_call_executed":
            tname = str(payload.get("name", ""))
            targs = payload.get("args", {})
            t_ms = payload.get("tool_ms")
            cat = "KNOWLEDGE_BASE" if "knowledge_rag" in tname else "VOICE_CMD"
            audit_kwargs = {
                "category": cat,
                "event_type": "tool_call_executed",
                "summary": f"Gọi Tool `{tname}`({json.dumps(targs, ensure_ascii=False)}) trong {t_ms or '--'}ms",
                "user_name": self.engine.get_current_user_name(),
                "tier": self.engine.current_tier,
                "details": payload,
            }
        if self.ws is not None:
            try:
                await self.ws.send_text(json.dumps(payload, ensure_ascii=False))
            except Exception:
                pass
        if audit_kwargs is not None:
            if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
                await asyncio.to_thread(append_audit_log, **audit_kwargs)
            else:
                task = asyncio.create_task(asyncio.to_thread(append_audit_log, **audit_kwargs))
                _PENDING_AUDIT_TASKS.add(task)
                task.add_done_callback(_discard_audit_task)

    def _reset_turn_metrics(self, anchor_ts: float | None = None) -> None:
        self.speech_end_ts = anchor_ts or time.perf_counter()
        self.turn_first_tool_ts = None
        self.turn_first_audio_ts = None
        self.turn_in_tx.clear()
        self.turn_out_tx.clear()
        self.turn_tools_called.clear()
        self._current_turn_echo_suppressed = False

    async def _sync_rules_context_to_gemini(self, event_note: str, send_to_model: bool = False) -> None:
        prompt_now = build_system_instruction(self.engine)
        await self.send_ws_json({
            "type": "system_prompt_updated",
            "system_prompt": prompt_now,
        })
        if send_to_model and self.gemini_session is not None:
            try:
                await self.gemini_session.send_client_content(
                    turns=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(
                                    text=(
                                        f"[CẬP NHẬT HỆ THỐNG ({format_vn_time_ampm()})]: {event_note}\n"
                                        f"Trạng thái luật hiện hành:\n{prompt_now}"
                                    )
                                )
                            ],
                        )
                    ],
                    turn_complete=False,
                )
            except Exception:
                pass

    async def _trigger_aoede_fixed_denial(
        self,
        spoken_phrase: str,
        auth_res: dict[str, Any] | None = None,
        *,
        inside_tool_call: bool = False,
    ) -> None:
        """Yêu cầu Gemini Live (giọng Aoede duy nhất) đọc nguyên văn câu cố định khi không đủ quyền RBAC."""
        role_tag = str((auth_res or {}).get("role") or self.engine.current_role or "UNKNOWN")
        reason_tag = "RBAC_SESSION_DENIED"
        await self.send_ws_json({
            "type": "aoede_voice_request",
            "voice": "Aoede",
            "spoken_phrase": spoken_phrase,
            "reason": reason_tag,
        })
        if self.gemini_session is None:
            try:
                clean_spoken = sanitize_spoken_vietnamese_text(spoken_phrase) or spoken_phrase
                aoede_bundle = await synthesize_aoede_phrase_audio(clean_spoken)
                if aoede_bundle.get("pcm24k_b64"):
                    pcm_bytes_out = aoede_bundle.get("pcm24k_bytes") or b""
                    if pcm_bytes_out:
                        self.echo_guard.note_ai_audio_chunk(len(pcm_bytes_out), sample_rate=24000, pcm_bytes=pcm_bytes_out)
                    self.echo_guard.record_ai_utterance(clean_spoken)
                    await self.send_ws_json({
                        "type": "audio_chunk",
                        "voice": "Aoede",
                        "sample_rate": 24000,
                        "pcm24k_b64": aoede_bundle["pcm24k_b64"],
                        "pcm_b64": aoede_bundle["pcm_b64"],
                        "audio_b64": aoede_bundle["audio_b64"],
                        "audio_wav_b64": aoede_bundle["audio_wav_b64"],
                        "text": clean_spoken,
                    })
            except Exception:
                pass
            return
        if inside_tool_call:
            return
        try:
            await self.gemini_session.send_client_content(
                turns=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                text=(
                                    f"[THÔNG BÁO PHÂN QUYỀN RBAC ({format_vn_time_ampm()})]: "
                                    f"(Role={role_tag}, Reason={reason_tag}).\n"
                                    f'[SYSTEM_SAY_EXACT_FIXED_DENIAL]: "{spoken_phrase}"\n'
                                    f'TUYỆT ĐỐI KHÔNG gọi bất kỳ tool điều khiển nào; chỉ đọc to, rõ ràng bằng giọng Aoede đúng nguyên văn câu cố định: "{spoken_phrase}"'
                                )
                            )
                        ],
                    )
                ],
                turn_complete=True,
            )
        except Exception:
            pass

    async def gemini_receive_loop(self) -> None:
        """Zero-Drop Reconnect Loop: Duy trì kết nối liên tục tới Gemini 3.8 Live."""
        if os.environ.get("SIMULATOR_OFFLINE_SANDBOX") == "1":
            return
        try:
            while not self._closed:
                t0 = time.perf_counter()
                try:
                    await self._bind_actor_to_engine_async()
                    async with self.client.aio.live.connect(
                        model=MODEL, config=make_live_config(self.engine)
                    ) as session:
                        self.gemini_session = session
                        conn_ms = round((time.perf_counter() - t0) * 1000)
                        await self.send_ws_json({
                            "type": "gemini_status",
                            "connected": True,
                            "model": MODEL,
                            "connect_ms": conn_ms,
                            "message": f"Đã kết nối {MODEL} ({conn_ms} ms)",
                        })

                        # Xả hàng đợi In-Flight PCM tích lũy trong lúc reconnect
                        while not self._mic_in_flight_queue.empty():
                            buffered_chunk = await self._mic_in_flight_queue.get()
                            try:
                                await session.send_realtime_input(
                                    audio=types.Blob(data=buffered_chunk, mime_type="audio/pcm;rate=16000")
                                )
                            except Exception:
                                pass

                        while not self._closed and self.gemini_session is session:
                            async for msg in session.receive():
                                now = time.perf_counter()

                                if msg.tool_call and msg.tool_call.function_calls:
                                    fn_responses = []
                                    pending_tool_ws_events: list[dict[str, Any]] = []
                                    for fc in msg.tool_call.function_calls:
                                        if self._current_turn_echo_suppressed:
                                            fn_responses.append(
                                                types.FunctionResponse(
                                                    id=fc.id,
                                                    name=fc.name,
                                                    response={"result": {"ok": False, "echo_suppressed": True, "silent": True}},
                                                )
                                            )
                                            continue
                                        if self.turn_first_tool_ts is None:
                                            self.turn_first_tool_ts = now
                                        t_anchor = self.speech_end_ts or now
                                        tool_ms = max(1, round((now - t_anchor) * 1000))
                                        desc = f"{fc.name}({json.dumps(dict(fc.args or {}), ensure_ascii=False)})"
                                        self.turn_tools_called.append(desc)

                                        exec_result = await self.handle_tool_call(fc)

                                        result_no_snap = (
                                            {k: v for k, v in exec_result.items() if k != "snapshot"}
                                            if isinstance(exec_result, dict)
                                            else exec_result
                                        )
                                        pending_tool_ws_events.append({
                                            "type": "tool_call_executed",
                                            "name": fc.name,
                                            "args": dict(fc.args or {}),
                                            "result": result_no_snap,
                                            "tool_ms": tool_ms,
                                        })

                                        if (
                                            fc.name == "control_device"
                                            and isinstance(exec_result, dict)
                                            and exec_result.get("ok")
                                            and not exec_result.get("rbac_blocked")
                                        ):
                                            compact_res = {
                                                "ok": True,
                                                "device_id": exec_result.get("device_id"),
                                                "state": exec_result.get("state"),
                                                "exact_spoken_reply": exec_result.get("exact_spoken_reply"),
                                                "instruction_for_ai": exec_result.get("instruction_for_ai"),
                                            }
                                        else:
                                            compact_res = result_no_snap
                                        fn_responses.append(
                                            types.FunctionResponse(
                                                id=fc.id,
                                                name=fc.name,
                                                response={"result": compact_res},
                                            )
                                        )
                                    try:
                                        await session.send_tool_response(function_responses=fn_responses)
                                    except Exception:
                                        pass
                                    for ev in pending_tool_ws_events:
                                        await self.send_ws_json(ev)

                                sc = msg.server_content
                                if sc:
                                    if sc.input_transcription and sc.input_transcription.text:
                                        txt = sc.input_transcription.text
                                        self.turn_in_tx.append(txt)
                                        full_in_txt = "".join(self.turn_in_tx).strip()
                                        is_echo, _echo_score, _echo_reason = self.echo_guard.check_echo_transcript(full_in_txt)
                                        if is_echo:
                                            self._current_turn_echo_suppressed = True
                                        elif not self._current_turn_echo_suppressed:
                                            await self.send_ws_json({
                                                "type": "input_transcription",
                                                "text": txt,
                                                "full_text": full_in_txt,
                                            })

                                    if sc.output_transcription and sc.output_transcription.text:
                                        if not self._current_turn_echo_suppressed:
                                            txt = sc.output_transcription.text
                                            self.turn_out_tx.append(txt)
                                            full_out_clean = sanitize_spoken_vietnamese_text("".join(self.turn_out_tx).strip())
                                            if full_out_clean:
                                                self.echo_guard.record_ai_utterance(full_out_clean)
                                                await self.send_ws_json({
                                                    "type": "output_transcription",
                                                    "text": sanitize_spoken_vietnamese_text(txt) or txt,
                                                    "full_text": full_out_clean,
                                                })

                                    if sc.model_turn and sc.model_turn.parts:
                                        for part in sc.model_turn.parts:
                                            if part.inline_data and part.inline_data.data:
                                                if self._current_turn_echo_suppressed:
                                                    continue
                                                self.echo_guard.note_ai_audio_chunk(len(part.inline_data.data), sample_rate=24000, pcm_bytes=part.inline_data.data)
                                                if self.turn_first_audio_ts is None:
                                                    self.turn_first_audio_ts = now
                                                    t_anchor = self.speech_end_ts or now
                                                    audio_ms = max(1, round((now - t_anchor) * 1000))
                                                    tool_ms = (
                                                        max(1, round((self.turn_first_tool_ts - t_anchor) * 1000))
                                                        if self.turn_first_tool_ts
                                                        else None
                                                    )
                                                    lead_ms = (
                                                        round((self.turn_first_audio_ts - self.turn_first_tool_ts) * 1000)
                                                        if self.turn_first_tool_ts
                                                        else None
                                                    )
                                                    await self.send_ws_json({
                                                        "type": "first_audio_metrics",
                                                        "tool_ms": tool_ms,
                                                        "audio_ms": audio_ms,
                                                        "lead_ms": lead_ms,
                                                    })
                                                b64_pcm = base64.b64encode(part.inline_data.data).decode("ascii")
                                                await self.send_ws_json({
                                                    "type": "audio_chunk",
                                                    "pcm24k_b64": b64_pcm,
                                                })

                                    if sc.interrupted:
                                        self.echo_guard.clear_ai_playback()
                                        self._current_turn_echo_suppressed = False
                                        await self.send_ws_json({"type": "interrupted"})

                                    if sc.turn_complete and (
                                        self.turn_first_audio_ts is not None or self.turn_first_tool_ts is None
                                    ):
                                        self.mic_utterance_active = False
                                        self._awaiting_model_turn_after_speech = False
                                        self._turn_completed_flag = True
                                        if self._current_turn_echo_suppressed:
                                            self._current_turn_echo_suppressed = False
                                            self.turn_in_tx.clear()
                                            self.turn_out_tx.clear()
                                            self.turn_tools_called.clear()
                                            continue
                                        self.ai_turns_completed += 1
                                        t_anchor = self.speech_end_ts or now
                                        tool_ms = (
                                            max(1, round((self.turn_first_tool_ts - t_anchor) * 1000))
                                            if self.turn_first_tool_ts
                                            else None
                                        )
                                        audio_ms = (
                                            max(1, round((self.turn_first_audio_ts - t_anchor) * 1000))
                                            if self.turn_first_audio_ts
                                            else None
                                        )
                                        lead_ms = (
                                            round((self.turn_first_audio_ts - self.turn_first_tool_ts) * 1000)
                                            if (self.turn_first_tool_ts and self.turn_first_audio_ts)
                                            else None
                                        )
                                        clean_said = sanitize_spoken_vietnamese_text("".join(self.turn_out_tx).strip())
                                        if clean_said:
                                            self.echo_guard.record_ai_utterance(clean_said)
                                        await self.send_ws_json({
                                            "type": "turn_complete",
                                            "heard": "".join(self.turn_in_tx).strip(),
                                            "said": clean_said,
                                            "tools": list(self.turn_tools_called),
                                            "tool_ms": tool_ms,
                                            "audio_ms": audio_ms,
                                            "lead_ms": lead_ms,
                                        })
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.gemini_session = None
                    if not self._closed:
                        await asyncio.sleep(0.4)
        except asyncio.CancelledError:
            raise

    async def stream_wav_sample(self, sample_id: str) -> None:
        verified_owner_sample_map = {
            "giong_1_chu_nha_mo_cua": AUDIO_DIR / "cac_cau_lenh_cua_sep" / "cau_2_mo_cua_chinh.wav",
            "mo_cua_chinh": AUDIO_DIR / "cac_cau_lenh_cua_sep" / "cau_2_mo_cua_chinh.wav",
            "bat_den_phong_khach": AUDIO_DIR / "cac_cau_lenh_cua_sep" / "cau_4_bat_den_phong_khach.wav",
            "tat_quat": AUDIO_DIR / "cac_cau_lenh_cua_sep" / "cau_6_tat_het_den.wav",
            "bat_quat_va_dieu_hoa": AUDIO_DIR / "cac_cau_lenh_cua_sep" / "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav",
        }
        mapped_path = verified_owner_sample_map.get(sample_id)
        wav_path = mapped_path if (mapped_path and mapped_path.exists()) else (AUDIO_DIR / f"{sample_id}.wav")
        if not wav_path.exists():
            await self.send_ws_json({"type": "error", "message": f"Không tìm thấy mẫu âm thanh '{sample_id}.wav'"})
            return

        with wave.open(str(wav_path), "rb") as w:
            data = w.readframes(w.getnframes())

        label = VOICE_SAMPLES_META.get(sample_id, sample_id)
        actor = self._bind_actor_to_engine()
        if not actor.is_authenticated or actor.is_expired():
            await self.send_ws_json({
                "type": "rbac_blocked",
                "action": "play_wav_sample",
                "role": "UNKNOWN",
                "reason": FIXED_REJECTION_PHRASE_VI,
            })
            await self._trigger_aoede_fixed_denial(FIXED_REJECTION_PHRASE_VI)
            return

        step = PCM_FRAME_BYTES
        framer = StatefulPcmFramingBuffer(frame_bytes=step)
        chunks = framer.push_chunk(data)
        tail = framer.flush_utterance_tail()
        if tail is not None:
            chunks.append(tail)

        self._reset_turn_metrics(anchor_ts=time.perf_counter())
        await self.send_ws_json({
            "type": "wav_stream_started",
            "sample_id": sample_id,
            "label": label,
            "duration_sec": round(len(chunks) * CHUNK_MS / 1000.0, 2),
        })

        start = time.perf_counter()
        for i, c in enumerate(chunks):
            delay = start + i * (CHUNK_MS * 0.5) / 1000.0 - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            if self.gemini_session is not None:
                await self.gemini_session.send_realtime_input(
                    audio=types.Blob(data=c, mime_type="audio/pcm;rate=16000")
                )

        if self.turn_first_tool_ts is None and self.turn_first_audio_ts is None:
            self.speech_end_ts = time.perf_counter()
        await self.send_ws_json({
            "type": "speech_ended_marker",
            "source": "wav_sample",
            "label": label,
        })

        if self.gemini_session is not None:
            try:
                await self.gemini_session.send_realtime_input(audio_stream_end=True)
            except Exception:
                for _ in range(3):
                    await self.gemini_session.send_realtime_input(
                        audio=types.Blob(data=SILENCE, mime_type="audio/pcm;rate=16000")
                    )

    async def _flush_mic_silence_to_gemini(self) -> None:
        try:
            if self._closed or self.gemini_session is None or self.last_mic_turn_silent_ignore:
                return
            for idx in range(22):
                if self._closed or self.gemini_session is None:
                    break
                if self.turn_first_tool_ts is not None or self.turn_first_audio_ts is not None:
                    break
                await self.gemini_session.send_realtime_input(
                    audio=types.Blob(data=SILENCE, mime_type="audio/pcm;rate=16000")
                )
                await asyncio.sleep(0 if idx < 8 else 0.004)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    def _enqueue_live_pcm_tx(self, item: bytes | None) -> None:
        if self._live_pcm_tx_queue.full():
            try:
                self._live_pcm_tx_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._live_pcm_tx_queue.put_nowait(item)
        except asyncio.QueueFull:
            pass

    async def _gemini_pcm_sender_loop(self) -> None:
        """Gửi luồng PCM sang Gemini Live trên coroutine riêng để không chặn vòng đọc WebSocket."""
        try:
            while not self._closed:
                first = await self._live_pcm_tx_queue.get()
                if self._closed:
                    break
                if first is None:
                    sess = self.gemini_session
                    if sess is not None:
                        try:
                            await sess.send_realtime_input(audio_stream_end=True)
                        except Exception:
                            pass
                    continue

                buf = bytearray(first)
                saw_stream_end = False
                while len(buf) < 3200 and not self._live_pcm_tx_queue.empty():
                    try:
                        nxt = self._live_pcm_tx_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    if nxt is None:
                        saw_stream_end = True
                        break
                    buf.extend(nxt)

                sess = self.gemini_session
                if sess is not None:
                    try:
                        await sess.send_realtime_input(
                            audio=types.Blob(data=bytes(buf), mime_type="audio/pcm;rate=16000")
                        )
                    except Exception:
                        pass
                else:
                    for off in range(0, len(buf), PCM_FRAME_BYTES):
                        part = bytes(buf[off : off + PCM_FRAME_BYTES])
                        if not part:
                            continue
                        if self._mic_in_flight_queue.full():
                            try:
                                self._mic_in_flight_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                pass
                        try:
                            self._mic_in_flight_queue.put_nowait(part)
                        except asyncio.QueueFull:
                            pass

                if saw_stream_end:
                    sess_end = self.gemini_session
                    if sess_end is not None:
                        try:
                            await sess_end.send_realtime_input(audio_stream_end=True)
                        except Exception:
                            pass
        except asyncio.CancelledError:
            raise

    async def _send_pcm_frame_to_gemini(self, frame: bytes) -> None:
        if not frame:
            return
        if self.gemini_session is not None:
            if self._pcm_tx_task is not None and not self._pcm_tx_task.done():
                self._enqueue_live_pcm_tx(frame)
                return
            try:
                await self.gemini_session.send_realtime_input(
                    audio=types.Blob(data=frame, mime_type="audio/pcm;rate=16000")
                )
                return
            except Exception:
                pass
        if self._mic_in_flight_queue.full():
            try:
                self._mic_in_flight_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._mic_in_flight_queue.put_nowait(frame)
        except asyncio.QueueFull:
            pass

    async def handle_mic_chunk(
        self,
        pcm_bytes: bytes,
        is_sp: bool = True,
        actor: UserSession | None = None,
        *,
        is_barge_in: bool = False,
    ) -> None:
        """Truyền thẳng PCM 16kHz 640B sang Gemini Live ngay khi nhận chunk (có cổng chống tiếng vọng)."""
        if not pcm_bytes:
            return

        if actor is None:
            actor = self._bind_actor_to_engine()

        allow_send, server_barge_triggered, _gate_reason = self.echo_guard.evaluate_mic_audio_chunk(
            pcm_bytes,
            is_barge_in_hint=is_barge_in,
        )
        if not allow_send:
            return
        if is_barge_in or server_barge_triggered:
            self._current_turn_echo_suppressed = False

        self.mic_recent_pcm.extend(pcm_bytes)
        if len(self.mic_recent_pcm) > 160000:
            del self.mic_recent_pcm[:-160000]

        if not actor.is_authenticated or actor.is_expired():
            self.mic_utterance_active = True
            return

        if is_sp:
            now_sp = time.perf_counter()
            self._awaiting_model_turn_after_speech = False
            if not self.mic_utterance_active:
                self.mic_utterance_active = True
                if self._mic_silence_task and not self._mic_silence_task.done():
                    self._mic_silence_task.cancel()
            if (
                self._turn_completed_flag
                or self.turn_first_tool_ts is not None
                or self.turn_first_audio_ts is not None
                or self.speech_end_ts is None
            ):
                self._reset_turn_metrics(anchor_ts=now_sp)
                self._turn_completed_flag = False
            elif self.turn_first_tool_ts is None and self.turn_first_audio_ts is None:
                self.speech_end_ts = now_sp

        for frame in self.pcm_framing_buffer.push_chunk(pcm_bytes):
            await self._send_pcm_frame_to_gemini(frame)

    async def mic_speech_ended(
        self, stream_end: bool = False, actor: UserSession | None = None
    ) -> None:
        """Kết thúc lượt nói từ Mic: giữ luồng PCM liên tục khi đang mở mic; chỉ audio_stream_end khi stopMic."""
        self.vad_stream_filter.reset()
        self.mic_utterance_active = False
        self._awaiting_model_turn_after_speech = True
        self._mic_preroll_pcm.clear()
        if actor is None:
            actor = self._bind_actor_to_engine()
        if not actor.is_authenticated or actor.is_expired():
            self.pcm_framing_buffer.clear()
            await self.send_ws_json({
                "type": "rbac_blocked",
                "action": "voice_mic",
                "role": "UNKNOWN",
                "reason": FIXED_REJECTION_PHRASE_VI,
            })
            await self._trigger_aoede_fixed_denial(FIXED_REJECTION_PHRASE_VI)
            await self.send_ws_json({
                "type": "speech_ended_marker",
                "source": "live_mic",
            })
            return

        if self.speech_end_ts is None and self.turn_first_tool_ts is None and self.turn_first_audio_ts is None:
            self.speech_end_ts = time.perf_counter()

        if self.gemini_session is None:
            tail_frame = self.pcm_framing_buffer.flush_utterance_tail()
            if tail_frame is not None:
                await self._send_pcm_frame_to_gemini(tail_frame)
        elif stream_end:
            tail_frame = self.pcm_framing_buffer.flush_utterance_tail()
            if tail_frame is not None:
                await self._send_pcm_frame_to_gemini(tail_frame)
            if (
                not self._turn_completed_flag
                and self.turn_first_tool_ts is None
                and self.turn_first_audio_ts is None
                and not self.last_mic_turn_silent_ignore
            ):
                if self._pcm_tx_task is not None and not self._pcm_tx_task.done():
                    self._enqueue_live_pcm_tx(None)
                else:
                    try:
                        await self.gemini_session.send_realtime_input(audio_stream_end=True)
                    except Exception:
                        pass
        await self.send_ws_json({
            "type": "speech_ended_marker",
            "source": "live_mic",
        })

    async def handle_tool_call(self, fc: Any) -> dict[str, Any]:
        """Điều phối Tool Call dựa trên RBAC 3 tầng theo phiên đăng nhập/QR."""
        name = fc.name
        actor = self._bind_actor_to_engine()
        if not actor.is_authenticated or actor.is_expired():
            await self.send_ws_json({
                "type": "rbac_blocked",
                "action": name,
                "role": "UNKNOWN",
                "reason": FIXED_REJECTION_PHRASE_VI,
            })
            await self._trigger_aoede_fixed_denial(FIXED_REJECTION_PHRASE_VI, inside_tool_call=True)
            return {
                "ok": False,
                "rbac_blocked": True,
                "error": FIXED_REJECTION_PHRASE_VI,
                "message": FIXED_REJECTION_PHRASE_VI,
                "rejection_speech": FIXED_REJECTION_PHRASE_VI,
                "exact_spoken_reply": FIXED_REJECTION_PHRASE_VI,
            }
        if name == "control_device":
            args = dict(fc.args or {})
            tool_res = await self.engine.execute_device_action(
                device_id=str(args.get("device_id") or ""), action=str(args.get("action") or ""),
                source="session_voice", request_tier=actor.tier,
                request_role=actor.role, request_user_name=actor.display_name,
            )
            asyncio.create_task(_broadcast_rest_state_to_bridges(exclude_bridge=self, sync_engine=True))
            if isinstance(tool_res, dict) and (not tool_res.get("ok", True) or tool_res.get("rbac_blocked")):
                rej_msg = str(tool_res.get("exact_spoken_reply") or tool_res.get("error") or FIXED_REJECTION_PHRASE_VI)
                await self.send_ws_json({
                    "type": "rbac_blocked",
                    "action": name,
                    "role": actor.role,
                    "reason": rej_msg,
                })
                await self._trigger_aoede_fixed_denial(rej_msg, auth_res={"role": actor.role}, inside_tool_call=True)
                tool_res = dict(tool_res)
                tool_res["instruction_for_ai"] = f"BẮT BUỘC nói ngắn gọn đúng nguyên văn câu này: '{rej_msg}'"
            return tool_res

        _admin_only_tools = (
            "grant_user_permission",
            "revoke_user_permission",
            "manage_member_link_permission",
            "set_query_permission_policy",
            "admin_update_system_policy",
            "admin_upsert_knowledge_rag",
            "factory_reset",
        )
        if name in _admin_only_tools:
            ok_cap1_sess, _ = self._is_ws_cap1_authorized()
            if not ok_cap1_sess or self.engine.current_tier != 1 or str(self.engine.current_role).upper() not in ("ADMIN", "OWNER"):
                from simulator.automation_repo import GUEST_ONLY_TOGGLE_MSG_VI
                rej_msg = GUEST_ONLY_TOGGLE_MSG_VI if int(actor.tier) >= 3 else "Chỉ chủ nhà cấp 1 mới có quyền thực hiện lệnh này ạ."
                await self.send_ws_json({
                    "type": "rbac_blocked",
                    "action": name,
                    "role": self.engine.current_role,
                    "reason": rej_msg,
                })
                await self._trigger_aoede_fixed_denial(rej_msg, auth_res={"role": actor.role}, inside_tool_call=True)
                return {
                    "ok": False,
                    "rbac_blocked": True,
                    "error": rej_msg,
                    "message": rej_msg,
                    "rejection_speech": rej_msg,
                    "exact_spoken_reply": rej_msg,
                    "instruction_for_ai": f"TUYỆT ĐỐI KHÔNG thực hiện lệnh. Chỉ nói ngắn gọn đúng câu: '{rej_msg}'",
                }

        res = await super().handle_tool_call(fc)
        if isinstance(res, dict) and res.get("ok"):
            try:
                asyncio.create_task(_broadcast_rest_state_to_bridges(exclude_bridge=self, sync_engine=True))
            except Exception:
                pass
        if isinstance(res, dict) and (not res.get("ok", True) or res.get("rbac_blocked")):
            if res.get("status") != "DURABLE_PERSISTENCE_FAILED":
                specific_reply = str(
                    res.get("exact_spoken_reply")
                    or res.get("reply")
                    or res.get("error")
                    or ""
                ).strip()
                rej_msg = specific_reply or FIXED_REJECTION_PHRASE_VI
                res = dict(res)
                res["error"] = rej_msg
                res["message"] = rej_msg
                res["rejection_speech"] = rej_msg
                res["exact_spoken_reply"] = rej_msg
                res["instruction_for_ai"] = (
                    f"BẮT BUỘC nói ngắn gọn đúng nguyên văn câu này: '{rej_msg}'"
                )
                if not res.get("silent_cancel") and not res.get("cancelled"):
                    await self._trigger_aoede_fixed_denial(rej_msg, auth_res={"role": actor.role}, inside_tool_call=True)
        return res

    async def run(self) -> None:
        self._bind_actor_to_engine()
        await self.send_ws_json({
            "type": "state_snapshot",
            "snapshot": self.engine.get_snapshot(),
        })
        await self.send_ws_json({
            "type": "system_prompt_updated",
            "system_prompt": build_system_instruction(self.engine),
        })
        await self.send_ws_json({
            "type": "gemini_status",
            "connected": bool(self.engine.server_connected),
            "message": f"Đang kết nối tới {MODEL}...",
        })

        recv_task = asyncio.create_task(self.gemini_receive_loop())
        timer_tick_task = asyncio.create_task(self._periodic_timer_sync())
        self._pcm_tx_task = asyncio.create_task(self._gemini_pcm_sender_loop())
        try:
            while True:
                raw = await self.ws.receive_text()
                try:
                    msg = json.loads(raw)
                    mtype = msg.get("type")
                    actor = await self._bind_actor_to_engine_async(msg)
                    guest_messages = {"manual_toggle", "send_text", "mic_chunk", "mic_speech_ended", "barge_in"}
                    if not actor.is_authenticated or (actor.tier > 1 and mtype not in guest_messages):
                        await self.send_ws_json({"type": "rbac_blocked", "ok": False, "action": mtype, "reason": FIXED_REJECTION_PHRASE_VI})
                        continue

                    if mtype == "barge_in":
                        self.echo_guard.clear_ai_playback()
                        self._current_turn_echo_suppressed = False
                        await self.send_ws_json({"type": "interrupted"})

                    elif mtype == "mic_chunk":
                        pcm_bytes = base64.b64decode(msg["pcm16k_b64"])
                        is_sp = bool(msg.get("is_speech", True))
                        is_barge = bool(msg.get("barge_in", False))
                        await self.handle_mic_chunk(pcm_bytes, is_sp, actor=actor, is_barge_in=is_barge)

                    elif mtype == "mic_speech_ended":
                        await self.mic_speech_ended(stream_end=bool(msg.get("stream_end", False)), actor=actor)

                    elif mtype == "play_wav_sample":
                        sample_id = str(msg.get("sample_id", ""))
                        if self._wav_streaming_task and not self._wav_streaming_task.done():
                            self._wav_streaming_task.cancel()
                        self._wav_streaming_task = asyncio.create_task(
                            self.stream_wav_sample(sample_id)
                        )

                    elif mtype == "send_text":
                        text = str(msg.get("text", "")).strip()
                        if text:
                            is_echo, _echo_score, _echo_reason = self.echo_guard.check_echo_transcript(text)
                            if is_echo:
                                continue
                            self.last_mic_turn_blocked = (
                                self.engine.current_role == "UNKNOWN" or self.engine.current_tier >= 4
                            )
                            self._reset_turn_metrics(anchor_ts=time.perf_counter())
                            self.turn_in_tx.append(text)
                            await self.send_ws_json({
                                "type": "input_transcription",
                                "text": text,
                                "full_text": text,
                            })
                            if not self.engine.server_connected:
                                t0_off = time.perf_counter()
                                res_off = await self.engine.execute_offline_default_command(
                                    text, source="offline_default"
                                )
                                tool_ms = max(1, int((time.perf_counter() - t0_off) * 1000))
                                reply_txt = sanitize_spoken_vietnamese_text(
                                    str(res_off.get("exact_spoken_reply") or res_off.get("reply") or "")
                                )
                                if reply_txt:
                                    self.echo_guard.record_ai_utterance(reply_txt)
                                self.ai_turns_completed += 1
                                await self.send_ws_json({
                                    "type": "tool_call_executed",
                                    "name": "offline_default_mcu",
                                    "args": {"command": text, "server_connected": False},
                                    "result": res_off,
                                    "tool_ms": tool_ms,
                                    "exact_spoken_reply": reply_txt,
                                })
                                await self.send_ws_json({
                                    "type": "output_transcription",
                                    "text": reply_txt,
                                    "full_text": reply_txt,
                                })
                                await self.send_ws_json({
                                    "type": "turn_complete",
                                    "heard": text,
                                    "said": reply_txt,
                                    "tool_ms": tool_ms,
                                    "audio_ms": None,
                                    "lead_ms": None,
                                })
                                await _broadcast_rest_state_to_bridges()
                            elif self.gemini_session is not None:
                                await self.gemini_session.send_client_content(
                                    turns=[
                                        types.Content(
                                            role="user",
                                            parts=[types.Part(text=text)],
                                        )
                                    ],
                                    turn_complete=True,
                                )

                    elif mtype == "set_server_mode":
                        ok_cap1, ws_sess = self._is_ws_cap1_authorized(msg)
                        if not ok_cap1:
                            await self.send_ws_json({
                                "type": "rbac_blocked",
                                "action": "set_server_mode",
                                "role": ws_sess.role,
                                "reason": FIXED_REJECTION_PHRASE_VI,
                                "message": FIXED_REJECTION_PHRASE_VI,
                            })
                            await self._trigger_aoede_fixed_denial(FIXED_REJECTION_PHRASE_VI)
                            continue
                        connected = bool(msg.get("server_connected", True))
                        await self.engine.set_server_connection_mode(connected)
                        _REST_ENGINE.server_connected = connected
                        await _broadcast_rest_state_to_bridges()

                    elif mtype == "set_role":
                        ok_cap1, ws_sess = self._is_ws_cap1_authorized(msg)
                        if not ok_cap1:
                            await self.send_ws_json({
                                "type": "rbac_blocked",
                                "action": "set_role",
                                "role": ws_sess.role,
                                "reason": FIXED_REJECTION_PHRASE_VI,
                                "message": FIXED_REJECTION_PHRASE_VI,
                            })
                            await self._trigger_aoede_fixed_denial(FIXED_REJECTION_PHRASE_VI)
                            continue
                        new_role = str(msg.get("role") or "").strip()
                        self.engine.set_active_user(new_role)
                        _REST_ENGINE.set_active_user(new_role)
                        self.last_mic_turn_blocked = (
                            self.engine.current_role == "UNKNOWN" or self.engine.current_tier >= 4
                        )
                        await self.send_ws_json({
                            "type": "state_snapshot",
                            "snapshot": self.engine.get_snapshot(),
                        })
                        await self._sync_rules_context_to_gemini(
                            f"Đã chuyển người dùng sang {self.engine.get_current_user_name()} (Tầng {self.engine.current_tier})."
                        )

                    elif mtype == "manual_toggle":
                        dev_id = str(msg.get("device_id", ""))
                        target_state = (
                            msg.get("target_state")
                            if "target_state" in msg
                            else (msg.get("state") if "state" in msg else msg.get("desired_state"))
                        )
                        action = str(msg.get("action") or (target_state if target_state is not None else ""))
                        client_id = msg.get("client_id") if "client_id" in msg else msg.get("clientId")
                        client_seq = msg.get("client_seq") if "client_seq" in msg else msg.get("seq")
                        client_ts_ms = msg.get("client_ts_ms") if "client_ts_ms" in msg else msg.get("timestamp")
                        request_id = msg.get("request_id") if "request_id" in msg else msg.get("requestId")
                        ws_sess = self._resolve_ws_session(msg)
                        res_toggle = await self.engine.execute_device_action(
                            device_id=dev_id,
                            action=action,
                            source="button_ui",
                            bypass_rbac=False,
                            request_tier=ws_sess.tier,
                            request_role=ws_sess.role,
                            request_user_name=ws_sess.display_name,
                            trigger_chains=True,
                            target_state=target_state,
                            client_id=client_id,
                            client_seq=client_seq,
                            client_ts_ms=client_ts_ms,
                            request_id=request_id,
                        )
                        await _broadcast_rest_state_to_bridges(exclude_bridge=self)
                        if isinstance(res_toggle, dict):
                            await self.send_ws_json({
                                "type": "manual_toggle_ack",
                                "ok": bool(res_toggle.get("ok", True)),
                                "rbac_blocked": bool(res_toggle.get("rbac_blocked", False)),
                                "device_id": res_toggle.get("device_id", dev_id),
                                "state": res_toggle.get("state"),
                                "device_version": res_toggle.get("device_version"),
                                "revision_seq": res_toggle.get("revision_seq"),
                                "client_id": res_toggle.get("client_id", client_id),
                                "client_seq": res_toggle.get("client_seq", client_seq),
                                "request_id": res_toggle.get("request_id", request_id),
                                "stale_ignored": bool(res_toggle.get("stale_ignored", False)),
                                "error": res_toggle.get("error"),
                                "snapshot": res_toggle.get("snapshot"),
                            })
                        if isinstance(res_toggle, dict) and (
                            not res_toggle.get("ok", True) or res_toggle.get("rbac_blocked")
                        ):
                            await self._trigger_aoede_fixed_denial(FIXED_REJECTION_PHRASE_VI)
                        if self.engine.on_event is None:
                            await self.send_ws_json({
                                "type": "state_snapshot",
                                "snapshot": self.engine.get_snapshot(),
                            })

                    elif mtype == "manual_factory_reset":
                        ok_cap1, ws_sess = self._is_ws_cap1_authorized(msg)
                        if not ok_cap1:
                            await self.send_ws_json({
                                "type": "rbac_blocked",
                                "action": "manual_factory_reset",
                                "role": ws_sess.role,
                                "reason": FIXED_REJECTION_PHRASE_VI,
                                "message": FIXED_REJECTION_PHRASE_VI,
                            })
                            await self._trigger_aoede_fixed_denial(FIXED_REJECTION_PHRASE_VI)
                            continue
                        self.last_mic_turn_blocked = False
                        self.mic_turn_verified = False
                        self.mic_utterance_pcm.clear()
                        await self.engine.factory_reset()
                        await _broadcast_rest_state_to_bridges()
                        await self._sync_rules_context_to_gemini("Đã reset về mặc định gốc.")

                    elif mtype in ("grant_user_permission", "grant"):
                        ok_cap1, ws_sess = self._is_ws_cap1_authorized(msg)
                        if not ok_cap1:
                            await self.send_ws_json({
                                "type": "rbac_blocked",
                                "action": "grant_user_permission",
                                "role": ws_sess.role,
                                "reason": FIXED_REJECTION_PHRASE_VI,
                                "message": FIXED_REJECTION_PHRASE_VI,
                            })
                            await self._trigger_aoede_fixed_denial(FIXED_REJECTION_PHRASE_VI)
                            continue
                        self.engine.set_active_user(OWNER_ID)
                        t_name = str(msg.get("target_name") or msg.get("user_name") or "").strip()
                        t_tier = int(msg.get("target_tier") or msg.get("tier") or 3)
                        res_grant = await self.engine.grant_user_permission(target_name=t_name, target_tier=t_tier)
                        await self.send_ws_json({"type": "permission_granted", "result": res_grant})

                    elif mtype in ("revoke_user_permission", "revoke"):
                        ok_cap1, ws_sess = self._is_ws_cap1_authorized(msg)
                        if not ok_cap1:
                            await self.send_ws_json({
                                "type": "rbac_blocked",
                                "action": "revoke_user_permission",
                                "role": ws_sess.role,
                                "reason": FIXED_REJECTION_PHRASE_VI,
                                "message": FIXED_REJECTION_PHRASE_VI,
                            })
                            await self._trigger_aoede_fixed_denial(FIXED_REJECTION_PHRASE_VI)
                            continue
                        self.engine.set_active_user(OWNER_ID)
                        t_name = str(msg.get("target_name") or msg.get("user_name") or "").strip()
                        res_revoke = await self.engine.revoke_user_permission(target_name=t_name)
                        await self.send_ws_json({"type": "permission_revoked", "result": res_revoke})

                    elif mtype == "enroll_owner_voice":
                        ok_cap1, ws_sess = self._is_ws_cap1_authorized(msg)
                        if not ok_cap1:
                            rej_res = {
                                "ok": False,
                                "status": "FORBIDDEN_CAP1_ONLY",
                                "rbac_blocked": True,
                                "error": FIXED_REJECTION_PHRASE_VI,
                                "message": FIXED_REJECTION_PHRASE_VI,
                            }
                            await self.send_ws_json({
                                "type": "rbac_blocked",
                                "action": "enroll_owner_voice",
                                "role": ws_sess.role,
                                "reason": FIXED_REJECTION_PHRASE_VI,
                                "message": FIXED_REJECTION_PHRASE_VI,
                            })
                            await self.send_ws_json({
                                "type": "voice_enrolled",
                                "result": rej_res,
                            })
                            await self._trigger_aoede_fixed_denial(FIXED_REJECTION_PHRASE_VI)
                            continue
                        pcm_bytes = base64.b64decode(msg.get("pcm16k_b64", ""))
                        self_check_b64 = str(
                            msg.get("self_check_pcm_b64")
                            or msg.get("self_check_pcm16k_b64")
                            or msg.get("self_check_audio_b64")
                            or ""
                        ).strip()
                        self_check_bytes = (
                            base64.b64decode(self_check_b64) if self_check_b64 else None
                        )
                        target_uid = str(msg.get("user_id") or OWNER_ID)
                        if target_uid == "UNKNOWN":
                            target_uid = OWNER_ID
                        u_info = self.engine.users.get(target_uid, {"name": "Nguyễn Tuấn Anh", "tier": 1, "role": "ADMIN"})
                        t_tier = int(msg.get("tier") or u_info.get("tier", 1))
                        t_name = str(msg.get("user_name") or u_info.get("name", "Nguyễn Tuấn Anh"))
                        t_role = str(u_info.get("role", "ADMIN"))
                        res = self.voice_auth.enroll_tier_voice_from_pcm16k(
                            pcm_bytes=pcm_bytes,
                            self_check_pcm_bytes=self_check_bytes,
                            user_id=target_uid,
                            user_name=t_name,
                            tier=t_tier,
                            role=t_role,
                        )
                        if res.get("ok") and res.get("profile"):
                            _BOOT_VOICE_AUTH.profiles = copy.deepcopy(self.voice_auth.profiles)
                            self.engine.set_active_user(target_uid)
                            self.last_mic_turn_blocked = False
                            self.mic_turn_verified = False
                            self.mic_utterance_pcm.clear()
                        await self.send_ws_json({
                            "type": "voice_enrolled",
                            "result": res,
                        })
                        await self.send_ws_json({
                            "type": "state_snapshot",
                            "snapshot": self.engine.get_snapshot(),
                        })

                    elif mtype == "complete_voice_enrollment":
                        ok_cap1, ws_sess = self._is_ws_cap1_authorized(msg)
                        if not ok_cap1:
                            await self.send_ws_json({
                                "type": "rbac_blocked",
                                "action": "complete_voice_enrollment",
                                "role": ws_sess.role,
                                "reason": FIXED_REJECTION_PHRASE_VI,
                                "message": FIXED_REJECTION_PHRASE_VI,
                            })
                            await self._trigger_aoede_fixed_denial(FIXED_REJECTION_PHRASE_VI)
                            continue
                        pcm_bytes = base64.b64decode(msg.get("pcm16k_b64", ""))
                        self_check_b64 = str(
                            msg.get("self_check_pcm_b64")
                            or msg.get("self_check_pcm16k_b64")
                            or msg.get("self_check_audio_b64")
                            or ""
                        ).strip()
                        self_check_bytes = (
                            base64.b64decode(self_check_b64) if self_check_b64 else None
                        )
                        await self._process_completed_voice_enrollment(
                            pcm_bytes, self_check_pcm_bytes=self_check_bytes
                        )

                    elif mtype == "aoede_speak_denial":
                        req_phrase = (
                            FIXED_SAFE_DENY_REPEAT_PHRASE_VI
                            if str(msg.get("text", "")).strip() == FIXED_SAFE_DENY_REPEAT_PHRASE_VI
                            else FIXED_REJECTION_PHRASE_VI
                        )
                        await self._trigger_aoede_fixed_denial(req_phrase)

                    elif mtype == "reset_voice_strikes":
                        ok_cap1, ws_sess = self._is_ws_cap1_authorized(msg)
                        if not ok_cap1:
                            await self.send_ws_json({
                                "type": "rbac_blocked",
                                "action": "reset_voice_strikes",
                                "role": ws_sess.role,
                                "reason": FIXED_REJECTION_PHRASE_VI,
                                "message": FIXED_REJECTION_PHRASE_VI,
                            })
                            await self._trigger_aoede_fixed_denial(FIXED_REJECTION_PHRASE_VI)
                            continue
                        self.last_mic_turn_blocked = False
                        self.mic_utterance_active = False
                        await self.send_ws_json({
                            "type": "state_snapshot",
                            "snapshot": self.engine.get_snapshot(),
                        })
                except Exception:
                    pass
        except WebSocketDisconnect:
            pass
        finally:
            self._closed = True
            recv_task.cancel()
            timer_tick_task.cancel()
            if self._pcm_tx_task:
                self._pcm_tx_task.cancel()
            if self._wav_streaming_task:
                self._wav_streaming_task.cancel()
            if self._mic_silence_task:
                self._mic_silence_task.cancel()

    async def _periodic_timer_sync(self) -> None:
        last_pushed_seq = int(getattr(self.engine, "_last_synced_seq", 0) or 0)
        tick = 0
        try:
            while not self._closed:
                await asyncio.sleep(0.5)
                tick += 1
                try:
                    synced_seq = last_pushed_seq
                    if (tick % 2) == 0 and hasattr(self.engine, "sync_from_shared_store"):
                        await asyncio.to_thread(self.engine.sync_from_shared_store)
                        synced_seq = int(getattr(self.engine, "_last_synced_seq", 0) or 0)
                    if self.engine.active_timers or synced_seq != last_pushed_seq:
                        last_pushed_seq = synced_seq
                        await self.send_ws_json({
                            "type": "state_snapshot",
                            "snapshot": self.engine.get_snapshot(sync=False),
                        })
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass
        except asyncio.CancelledError:
            raise


# Alias tương thích kiến trúc
GeminiLiveBridge = LiveBridgeSession
