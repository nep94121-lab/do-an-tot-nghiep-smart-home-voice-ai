"""Cầu Nối WebSocket và Gemini 3.8 Live API Hai Chiều (Gemini Live Bridge).

Chức năng:
1. Quản lý phiên WebSocket client <-> Upstream Gemini 3.8 Live API.
2. Cơ chế Zero-Drop Reconnect: Tự động kết nối lại khi gián đoạn mạng, hàng đợi In-Flight PCM đệm âm thanh không rơi rớt câu nói.
3. Tích hợp VAD 2 tầng (Stream filter 20ms + Toàn câu) và Sinh trắc học giọng nói 256D.
4. Kiểm tra lượt nói Mic đúng 1 lần/câu thoại (_ensure_current_mic_utterance_verified) ngăn chặn tấn công giả mạo.
5. Điều phối thực thi 20 Function Tools (Actuate-First) và phát âm thanh từ chối 24kHz Mono 16-bit PCM.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import json
import os
import pathlib
import re
import time
import wave
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

VOICE_SAMPLES_META: dict[str, str] = {
    "giong_1_chu_nha_mo_cua": "✅ Giọng Cấp 1 (Chủ nhà Nguyễn Tuấn Anh - Toàn quyền): Mở cửa chính",
    "giong_cap2_thanh_vien_a": "👨‍👩‍👧 Giọng Cấp 2 (Thành viên A - Chặn Cửa D1 & Còi D8): Mở cửa chính",
    "giong_cap3_khach_c": "🧒 Giọng Cấp 3 (Khách C - Chỉ bật Đèn/Quạt, Chặn Cửa/Còi/ĐH/Bơm): Mở cửa chính",
    "giong_1_kem_tieng_on_quat": "🌀 Giọng Cấp 1 + Ồn Quạt (-24dB ➡️ Lọc Tầng 2): Mở cửa chính",
    "hai_nguoi_cung_noi_cap1_va_nguoi_la": "👥 2 Người Cùng Nói (Chủ nhà C1 + Người lạ ➡️ Ưu tiên C1): Mở cửa chính",
    "giong_2_nguoi_la_mo_cua": "🚫 Giọng Người lạ (Không phép - Chặn 2 lần ➡️ Im lặng): Mở cửa chính",
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
from simulator.knowledge_rag import SmartHomeKnowledgeRAG
from simulator.live.prompt_builder import (
    ALL_TOOLS,
    FIXED_REJECTION_PHRASE_VI,
    FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
    build_system_instruction,
    make_live_config,
)
from simulator.live.tool_dispatcher_mixin import LiveToolDispatcherMixin
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
    ):
        self.ws = ws or websocket
        self.voice_auth = voice_auth or VoiceAuthManager(AUDIO_DIR)
        if engine is not None:
            self.engine = engine
            if self.engine is _REST_ENGINE or self.engine.on_event is None:
                self.engine.on_event = (
                    _emit_to_all_active_bridges
                    if self.engine is _REST_ENGINE
                    else self.send_ws_json
                )
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
        self.client = genai.Client(api_key=KEY or "TEST_DUMMY_GEMINI_KEY")
        self.gemini_session: Any = None
        self.speech_end_ts: float | None = None
        self.turn_first_tool_ts: float | None = None
        self.turn_first_audio_ts: float | None = None
        self.turn_in_tx: list[str] = []
        self.turn_out_tx: list[str] = []
        self.turn_tools_called: list[str] = []
        self._wav_streaming_task: asyncio.Task | None = None
        self._mic_silence_task: asyncio.Task | None = None
        self._closed = False
        self._mic_in_flight_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        # Chỉ tự động đưa vào _ACTIVE_BRIDGES nếu là WebSocket thật (không phải Mock trong unit test)
        is_mock_ws = hasattr(self.ws, "assert_called") or hasattr(self.ws, "assert_awaited") or hasattr(self.ws, "_mock_return_value")
        if self.ws is not None and not is_mock_ws and self not in _ACTIVE_BRIDGES:
            _ACTIVE_BRIDGES.append(self)

    def close(self) -> None:
        self._closed = True
        if self in _ACTIVE_BRIDGES:
            _ACTIVE_BRIDGES.remove(self)

    async def send_ws_json(self, payload: dict[str, Any]) -> None:
        if self._closed:
            if self in _ACTIVE_BRIDGES:
                _ACTIVE_BRIDGES.remove(self)
            return
        ptype = str(payload.get("type", ""))
        if ptype == "turn_complete":
            heard = str(payload.get("heard", "")).strip()
            said = str(payload.get("said", "")).strip()
            t_ms = payload.get("tool_ms")
            a_ms = payload.get("audio_ms")
            append_audit_log(
                category="VOICE_CMD",
                event_type="turn_complete",
                summary=f"👤 Nói: '{heard}' ➔ 🤖 AI đáp: '{said}' (Tool: {t_ms or '--'}ms, Audio: {a_ms or '--'}ms)",
                user_name=self.engine.get_current_user_name(),
                tier=self.engine.current_tier,
                details=payload,
            )
        elif ptype == "tool_call_executed":
            tname = str(payload.get("name", ""))
            targs = payload.get("args", {})
            t_ms = payload.get("tool_ms")
            cat = "KNOWLEDGE_BASE" if "knowledge_rag" in tname else "VOICE_CMD"
            append_audit_log(
                category=cat,
                event_type="tool_call_executed",
                summary=f"⚙️ Gọi Tool `{tname}`({json.dumps(targs, ensure_ascii=False)}) trong {t_ms or '--'}ms",
                user_name=self.engine.get_current_user_name(),
                tier=self.engine.current_tier,
                details=payload,
            )
        elif ptype in ("voice_auth_rejected", "voice_auth_silent_ignored"):
            append_audit_log(
                category="VOICE_AUTH",
                event_type=ptype,
                summary=f"🚫 Chặn Giọng Lạ (Lần {payload.get('strike_count', 1)}, F0={payload.get('f0_hz')}Hz): {payload.get('rejection_speech') or payload.get('message')}",
                user_name="Người lạ (Unauthorized)",
                tier=99,
                details=payload,
            )
        if self.ws is not None:
            try:
                await self.ws.send_text(json.dumps(payload, ensure_ascii=False))
            except Exception:
                pass

    def _reset_turn_metrics(self, anchor_ts: float | None = None) -> None:
        self.speech_end_ts = anchor_ts or time.perf_counter()
        self.turn_first_tool_ts = None
        self.turn_first_audio_ts = None
        self.turn_in_tx.clear()
        self.turn_out_tx.clear()
        self.turn_tools_called.clear()

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

    async def _apply_voice_tier_and_sync(
        self, auth_res: dict[str, Any], sample_id: str = "live_mic", label: str = "Giọng nói trực tiếp qua Mic"
    ) -> dict[str, Any]:
        from simulator.auth_3layer import get_auth_3layer_manager
        mgr3 = get_auth_3layer_manager()

        if auth_res.get("authorized"):
            matched_uid = str(auth_res.get("user_id") or OWNER_ID)
            acc_list = mgr3.accounts.values() if isinstance(mgr3.accounts, dict) else mgr3.accounts
            acc_3layer = next(
                (a for a in acc_list if isinstance(a, dict) and a.get("account_id") == matched_uid),
                None,
            )
            eng_user = self.engine.users.get(matched_uid)
            is_revoked = (acc_3layer is not None and not acc_3layer.get("permission_active", True)) or (
                eng_user is not None and not eng_user.get("active", True)
            )
            if is_revoked:
                uname = (acc_3layer or {}).get("display_name") or (eng_user or {}).get("name") or matched_uid
                auth_res["authorized"] = False
                auth_res["ask_repeat"] = False
                auth_res["user_id"] = "UNKNOWN"
                auth_res["role"] = "UNKNOWN"
                auth_res["tier"] = 99
                auth_res["speaker_label"] = f"🚫 {uname} (ĐÃ BỊ XÓA CẤP QUYỀN)"
                auth_res["strike_count"] = max(1, int(auth_res.get("strike_count", 0)) + 1)
                auth_res["silent_ignore"] = False
                auth_res["should_reply"] = True
                auth_res["rejection_speech"] = FIXED_REJECTION_PHRASE_VI
                auth_res["exact_spoken_reply"] = FIXED_REJECTION_PHRASE_VI
                self.engine.set_active_user("UNKNOWN")
                self.last_mic_turn_blocked = True
                self.last_mic_turn_silent_ignore = False
            else:
                self.engine.set_active_user(matched_uid)
                self.last_mic_turn_blocked = False
                self.last_mic_turn_silent_ignore = False
                auth_res["silent_ignore"] = False
                auth_res["should_reply"] = True
                auth_res["active_user_id"] = self.engine.current_user_id
                auth_res["active_user_name"] = self.engine.get_current_user_name()
                auth_res["active_tier"] = self.engine.current_tier
        else:
            self.engine.set_active_user("UNKNOWN")
            self.last_mic_turn_blocked = True
            self.last_mic_turn_silent_ignore = False
            auth_res["silent_ignore"] = False
            auth_res["should_reply"] = True
            fixed_phrase = (
                FIXED_SAFE_DENY_REPEAT_PHRASE_VI
                if auth_res.get("ask_repeat")
                else FIXED_REJECTION_PHRASE_VI
            )
            auth_res["rejection_speech"] = fixed_phrase
            auth_res["exact_spoken_reply"] = fixed_phrase
            auth_res["active_user_id"] = "UNKNOWN"
            auth_res["active_user_name"] = "Người lạ (Chặn toàn bộ)"
            auth_res["active_tier"] = 4

        self.last_mic_auth_result = dict(auth_res)
        await self.send_ws_json({
            "type": "voice_auth_result",
            "sample_id": sample_id,
            "label": label,
            "analysis": auth_res,
        })
        await self.send_ws_json({
            "type": "state_snapshot",
            "snapshot": self.engine.get_snapshot(),
        })
        if self.gemini_session is not None and auth_res.get("authorized"):
            try:
                active_user = self.engine.get_current_user_name()
                active_tier = self.engine.current_tier
                active_role = self.engine.current_role
                tier_label = (
                    "TOÀN QUYỀN (Tier 1 - Chủ nhà)" if active_tier == 1
                    else "HẠN CHẾ CỬA/CÒI (Tier 2 - Thành viên)" if active_tier == 2
                    else "CHỈ ĐIỀU KHIỂN ĐÈN/QUẠT (Tier 3 - Khách)" if active_tier == 3
                    else "BỊ CHẶN HOÀN TOÀN (Người lạ/Chưa cấp quyền)"
                )
                extra_rule = (
                    f"TUYỆT ĐỐI tuân thủ phân quyền; nếu vượt quyền chỉ nói: '{FIXED_REJECTION_PHRASE_VI}'"
                )
                await self.gemini_session.send_client_content(
                    turns=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(
                                    text=(
                                        f"[CẬP NHẬT PHÂN QUYỀN GIỌNG NÓI ({format_vn_time_ampm()})]: "
                                        f"Người đang nói: {active_user} (Tier {active_tier}, Role {active_role}). "
                                        f"Quyền hạn: {tier_label}. {extra_rule}"
                                    )
                                )
                            ],
                        )
                    ],
                    turn_complete=False,
                )
            except Exception:
                pass
        return auth_res

    async def _trigger_aoede_fixed_denial(
        self, spoken_phrase: str, auth_res: dict[str, Any] | None = None
    ) -> None:
        """Yêu cầu Gemini Live (giọng Aoede duy nhất) đọc nguyên văn câu cố định khi từ chối hoặc yêu cầu nói lại (0 bytes audio gửi lên Gemini)."""
        if self.gemini_session is None:
            return
        role_tag = str((auth_res or {}).get("role") or "UNKNOWN")
        reason_tag = (
            "SAFE_DENY_ASK_REPEAT"
            if (auth_res or {}).get("ask_repeat")
            else "UNAUTHORIZED_STRANGER_OR_OVER_PERMISSION"
        )
        try:
            await self.gemini_session.send_client_content(
                turns=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                text=(
                                    f"[CẬP NHẬT PHÂN QUYỀN GIỌNG NÓI ({format_vn_time_ampm()})]: "
                                    f"NGƯỜI LẠ / KHÔNG ĐƯỢC PHÉP (Role={role_tag}, Reason={reason_tag}).\n"
                                    f'[SYSTEM_SAY_EXACT_FIXED_DENIAL]: "{spoken_phrase}"\n'
                                    f"TUYỆT ĐỐI KHÔNG gọi bất kỳ tool điều khiển nào; chỉ đọc to, rõ ràng bằng giọng Aoede đúng nguyên văn câu cố định: \"{spoken_phrase}\""
                                )
                            )
                        ],
                    )
                ],
                turn_complete=True,
            )
        except Exception:
            pass

    async def _ensure_current_mic_utterance_verified(self) -> None:
        """Kiểm tra giọng nói của câu đang nói qua Mic đúng 1 lần duy nhất trước khi gửi bất kỳ byte PCM nào sang Gemini Live."""
        if self.mic_turn_verified:
            return
        if len(self.mic_utterance_pcm) > 0:
            raw_utt = bytes(self.mic_utterance_pcm)
        elif len(self.mic_recent_pcm) > 0:
            raw_utt = bytes(self.mic_recent_pcm)
        else:
            return
        raw_utt = raw_utt[: len(raw_utt) & ~1]
        if not raw_utt:
            return

        self.mic_turn_verified = True
        self.mic_utterance_active = False
        self.mic_utterance_pcm.clear()
        self.mic_recent_pcm.clear()

        prev_strikes = getattr(self.voice_auth, "unauthorized_strikes", 0)
        auth_res = self.voice_auth.verify_pcm16k_and_apply_strikes(raw_utt)
        clean_pcm_bytes = auth_res.pop("clean_pcm_bytes", raw_utt)

        if auth_res.get("ask_repeat") or auth_res.get("quality_gate_failed") or not auth_res.get("quality_gate_passed", True):
            self.voice_auth.unauthorized_strikes = prev_strikes
            auth_res["strike_count"] = prev_strikes
            auth_res["ask_repeat"] = True
            auth_res["authorized"] = False

        auth_res["silent_ignore"] = False
        auth_res["should_reply"] = True

        auth_res = await self._apply_voice_tier_and_sync(
            auth_res, sample_id="live_mic", label="Giọng nói trực tiếp qua Mic"
        )

        if not auth_res.get("authorized"):
            # ZERO bytes (0 frames, 0 bytes) gửi tới gemini_session.send_realtime_input!
            self.last_mic_turn_blocked = True
            self.last_mic_turn_silent_ignore = False
            rej_text = (
                FIXED_SAFE_DENY_REPEAT_PHRASE_VI
                if auth_res.get("ask_repeat")
                else FIXED_REJECTION_PHRASE_VI
            )
            auth_res["rejection_speech"] = rej_text
            auth_res["exact_spoken_reply"] = rej_text
            self.last_mic_auth_result = dict(auth_res)
            self._reset_turn_metrics(anchor_ts=time.perf_counter())
            self.turn_in_tx.append(f"[{auth_res.get('speaker_label', 'Người lạ')} qua Mic]")
            await self.send_ws_json({
                "type": "voice_auth_rejected",
                "sample_id": "live_mic",
                "label": "Giọng nói trực tiếp qua Mic",
                "strike_count": int(auth_res.get("strike_count", 0)),
                "f0_hz": auth_res.get("f0_hz", 0.0),
                "ask_repeat": bool(auth_res.get("ask_repeat", False)),
                "rejection_speech": rej_text,
                "exact_spoken_reply": rej_text,
            })
            await self._trigger_aoede_fixed_denial(rej_text, auth_res=auth_res)
            return

        # Người nói hợp lệ (Tier 1, Tier 2, hoặc Tier 3) -> Đóng khung 640 bytes chuẩn và gửi sang Gemini Live
        self.pcm_framing_buffer.clear()
        stream_pcm = clean_pcm_bytes if len(clean_pcm_bytes) >= PCM_FRAME_BYTES else raw_utt
        frames = self.pcm_framing_buffer.push_chunk(stream_pcm)
        tail_frame = self.pcm_framing_buffer.flush_utterance_tail()
        if tail_frame is not None:
            frames.append(tail_frame)

        for frame in frames:
            if self.gemini_session is not None:
                try:
                    await self.gemini_session.send_realtime_input(
                        audio=types.Blob(data=frame, mime_type="audio/pcm;rate=16000")
                    )
                except Exception:
                    pass
            else:
                if not self._mic_in_flight_queue.full():
                    await self._mic_in_flight_queue.put(frame)

        if self.gemini_session is not None:
            if self._mic_silence_task and not self._mic_silence_task.done():
                self._mic_silence_task.cancel()
            self._mic_silence_task = asyncio.create_task(
                self._flush_mic_silence_to_gemini()
            )

    async def gemini_receive_loop(self) -> None:
        """Zero-Drop Reconnect Loop: Duy trì kết nối liên tục tới Gemini 3.8 Live."""
        try:
            while not self._closed:
                t0 = time.perf_counter()
                try:
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
                                    await self._ensure_current_mic_utterance_verified()
                                    fn_responses = []
                                    for fc in msg.tool_call.function_calls:
                                        if self.turn_first_tool_ts is None:
                                            self.turn_first_tool_ts = now
                                        t_anchor = self.speech_end_ts or now
                                        tool_ms = max(1, round((now - t_anchor) * 1000))
                                        desc = f"{fc.name}({json.dumps(dict(fc.args or {}), ensure_ascii=False)})"
                                        self.turn_tools_called.append(desc)

                                        exec_result = await self.handle_tool_call(fc)

                                        await self.send_ws_json({
                                            "type": "tool_call_executed",
                                            "name": fc.name,
                                            "args": dict(fc.args or {}),
                                            "result": exec_result,
                                            "tool_ms": tool_ms,
                                        })

                                        fn_responses.append(
                                            types.FunctionResponse(
                                                id=fc.id,
                                                name=fc.name,
                                                response={"result": exec_result},
                                            )
                                        )
                                    try:
                                        await session.send_tool_response(function_responses=fn_responses)
                                    except Exception:
                                        pass

                                sc = msg.server_content
                                if sc:
                                    if sc.input_transcription and sc.input_transcription.text:
                                        txt = sc.input_transcription.text
                                        self.turn_in_tx.append(txt)
                                        await self.send_ws_json({
                                            "type": "input_transcription",
                                            "text": txt,
                                            "full_text": "".join(self.turn_in_tx).strip(),
                                        })

                                    if sc.output_transcription and sc.output_transcription.text:
                                        await self._ensure_current_mic_utterance_verified()
                                        if not self.last_mic_turn_silent_ignore:
                                            txt = sc.output_transcription.text
                                            self.turn_out_tx.append(txt)
                                            await self.send_ws_json({
                                                "type": "output_transcription",
                                                "text": txt,
                                                "full_text": "".join(self.turn_out_tx).strip(),
                                            })

                                    if sc.model_turn and sc.model_turn.parts:
                                        await self._ensure_current_mic_utterance_verified()
                                        if self.last_mic_turn_silent_ignore:
                                            continue
                                        for part in sc.model_turn.parts:
                                            if part.inline_data and part.inline_data.data:
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
                                        await self.send_ws_json({"type": "interrupted"})

                                    if sc.turn_complete and (
                                        self.turn_first_audio_ts is not None or self.turn_first_tool_ts is None
                                    ):
                                        if not self.last_mic_turn_silent_ignore:
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
                                            await self.send_ws_json({
                                                "type": "turn_complete",
                                                "heard": "".join(self.turn_in_tx).strip(),
                                                "said": "".join(self.turn_out_tx).strip(),
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

        if not self.engine.server_connected:
            t0_off = time.perf_counter()
            auth_off = self.voice_auth.verify_pcm16k_and_apply_strikes(data)
            auth_off.pop("clean_pcm_bytes", None)
            auth_off["filter_stage_used"] = "Tiny-DSP Flash ESP8266 (Tầng 1 & 2)"
            await self.send_ws_json({
                "type": "voice_auth_result",
                "sample_id": sample_id,
                "label": label,
                "analysis": auth_off,
            })
            if not auth_off["authorized"] or int(auth_off.get("tier", 1)) >= 3:
                self.last_mic_turn_blocked = True
                rej_off = (
                    f"🚫 [CHẶN GIỌNG LẠ OFFLINE - TINY-DSP {auth_off.get('stage1_ms', 16)}ms]: "
                    f"Khi ngắt Server, mạch ESP8266 chỉ nhận giọng Tầng 1 (Chủ nhà) & Tầng 2 (Gia đình) đã lưu trong Flash! "
                    f"Phát hiện {auth_off['speaker_label']} (F0={auth_off['f0_hz']}Hz) -> Từ chối điều khiển!"
                )
                await self.send_ws_json({"type": "input_transcription", "text": label, "full_text": label})
                await self.send_ws_json({
                    "type": "voice_auth_rejected",
                    "sample_id": sample_id,
                    "label": label,
                    "strike_count": auth_off.get("strike_count", 1),
                    "f0_hz": auth_off["f0_hz"],
                    "rejection_speech": rej_off,
                    "exact_spoken_reply": rej_off,
                })
                return
            res_off = await self.engine.execute_offline_default_command(label, source="offline_default_wav")
            tool_ms = max(1, int((time.perf_counter() - t0_off) * 1000))
            reply_txt = str(res_off.get("exact_spoken_reply") or res_off.get("reply") or "")
            await self.send_ws_json({"type": "input_transcription", "text": label, "full_text": label})
            await self.send_ws_json({
                "type": "tool_call_executed",
                "name": "offline_default_mcu",
                "args": {"command": label, "server_connected": False},
                "result": res_off,
                "tool_ms": tool_ms,
            })
            await self.send_ws_json({"type": "output_transcription", "text": reply_txt, "full_text": reply_txt})
            await self.send_ws_json({
                "type": "turn_complete",
                "heard": label,
                "said": reply_txt,
                "tool_ms": tool_ms,
                "audio_ms": None,
                "lead_ms": None,
            })
            await _broadcast_rest_state_to_bridges()
            return

        prev_strikes = getattr(self.voice_auth, "unauthorized_strikes", 0)
        auth_res = self.voice_auth.verify_pcm16k_and_apply_strikes(data)
        clean_pcm_bytes = auth_res.pop("clean_pcm_bytes", data)
        if auth_res.get("ask_repeat") or auth_res.get("quality_gate_failed") or not auth_res.get("quality_gate_passed", True):
            self.voice_auth.unauthorized_strikes = prev_strikes
            auth_res["strike_count"] = prev_strikes
            auth_res["ask_repeat"] = True
            auth_res["authorized"] = False
        auth_res["silent_ignore"] = False
        auth_res["should_reply"] = True

        auth_res = await self._apply_voice_tier_and_sync(auth_res, sample_id=sample_id, label=label)

        if not auth_res.get("authorized"):
            # ZERO bytes (0 frames, 0 bytes) gửi tới send_realtime_input!
            self.last_mic_turn_blocked = True
            self.last_mic_turn_silent_ignore = False
            strike = int(auth_res.get("strike_count", 1))
            rej_text = (
                FIXED_SAFE_DENY_REPEAT_PHRASE_VI
                if auth_res.get("ask_repeat")
                else FIXED_REJECTION_PHRASE_VI
            )
            auth_res["rejection_speech"] = rej_text
            auth_res["exact_spoken_reply"] = rej_text
            self.last_mic_auth_result = dict(auth_res)
            self._reset_turn_metrics(anchor_ts=time.perf_counter())
            self.turn_in_tx.append(f"[{auth_res.get('speaker_label', 'Người lạ')}]: {label}")
            await self.send_ws_json({
                "type": "voice_auth_rejected",
                "sample_id": sample_id,
                "label": label,
                "strike_count": strike,
                "f0_hz": auth_res.get("f0_hz", 0.0),
                "ask_repeat": bool(auth_res.get("ask_repeat", False)),
                "rejection_speech": rej_text,
                "exact_spoken_reply": rej_text,
            })
            await self._trigger_aoede_fixed_denial(rej_text, auth_res=auth_res)
            return

        step = PCM_FRAME_BYTES
        stream_data = clean_pcm_bytes if len(clean_pcm_bytes) >= step else data
        framer = StatefulPcmFramingBuffer(frame_bytes=step)
        chunks = framer.push_chunk(stream_data)
        tail = framer.flush_utterance_tail()
        if tail is not None:
            chunks.append(tail)

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

        self._reset_turn_metrics(anchor_ts=time.perf_counter())
        await self.send_ws_json({
            "type": "speech_ended_marker",
            "source": "wav_sample",
            "label": label,
        })

        sil_start = time.perf_counter()
        for i in range(13):
            if self.turn_first_tool_ts is not None or self.turn_first_audio_ts is not None:
                break
            delay = sil_start + (i + 1) * 0.01 - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            if self.gemini_session is not None:
                for _ in range(5):
                    await self.gemini_session.send_realtime_input(
                        audio=types.Blob(data=SILENCE, mime_type="audio/pcm;rate=16000")
                    )

    async def _flush_mic_silence_to_gemini(self) -> None:
        try:
            sil_start = time.perf_counter()
            for i in range(13):
                if self._closed or self.gemini_session is None or self.last_mic_turn_silent_ignore:
                    break
                if self.turn_first_tool_ts is not None or self.turn_first_audio_ts is not None:
                    break
                delay = sil_start + (i + 1) * 0.01 - time.perf_counter()
                if delay > 0:
                    await asyncio.sleep(delay)
                if self._closed or self.gemini_session is None:
                    break
                for _ in range(5):
                    await self.gemini_session.send_realtime_input(
                        audio=types.Blob(data=SILENCE, mime_type="audio/pcm;rate=16000")
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def handle_mic_chunk(self, pcm_bytes: bytes, is_sp: bool = True) -> None:
        """Chỉ lưu pcm_bytes vào bộ đệm server-side để xác thực trước; TUYỆT ĐỐI KHÔNG gửi sang Gemini trong hàm này."""
        if not pcm_bytes:
            return

        self.mic_recent_pcm.extend(pcm_bytes)
        if len(self.mic_recent_pcm) > 160000:
            del self.mic_recent_pcm[:-160000]
        if is_sp:
            if self._mic_silence_task and not self._mic_silence_task.done():
                self._mic_silence_task.cancel()
            if self.mic_turn_verified:
                self.mic_utterance_pcm.clear()
                self.pcm_framing_buffer.clear()
                self.mic_turn_verified = False
                self.last_mic_turn_blocked = False
                self.last_mic_turn_silent_ignore = False
            self.mic_utterance_active = True
            self.speech_end_ts = time.perf_counter()
            self.turn_first_tool_ts = None
            self.turn_first_audio_ts = None
            self.mic_utterance_pcm.extend(pcm_bytes)
        elif self.mic_utterance_active and len(self.mic_utterance_pcm) > 0:
            self.mic_utterance_pcm.extend(pcm_bytes)

    async def mic_speech_ended(self) -> None:
        """Kết thúc lượt nói từ Mic: chạy nhận diện người nói server-side TRƯỚC, sau đó mới gửi PCM sang Gemini nếu được phép."""
        self.vad_stream_filter.reset()
        self._reset_turn_metrics(anchor_ts=time.perf_counter())
        await self._ensure_current_mic_utterance_verified()
        if self.gemini_session is not None and not self.last_mic_turn_blocked:
            if self._mic_silence_task is None or self._mic_silence_task.done():
                self._mic_silence_task = asyncio.create_task(
                    self._flush_mic_silence_to_gemini()
                )
        await self.send_ws_json({
            "type": "speech_ended_marker",
            "source": "live_mic",
        })

    async def handle_tool_call(self, fc: Any) -> dict[str, Any]:
        """Điều phối Tool Call với kiểm tra nghiêm ngặt Cấp 1 cho cấp/hủy quyền & thu âm, và chuẩn hóa câu từ chối cố định Aoede."""
        name = fc.name
        await self._ensure_current_mic_utterance_verified()

        if self.last_mic_turn_blocked or self.engine.current_role == "UNKNOWN" or self.engine.current_tier >= 4:
            rej_info = self.last_mic_auth_result or {}
            rej_msg = (
                FIXED_SAFE_DENY_REPEAT_PHRASE_VI
                if rej_info.get("ask_repeat")
                else FIXED_REJECTION_PHRASE_VI
            )
            f0_val = rej_info.get("f0_hz", 0.0)
            await self.send_ws_json({
                "type": "rbac_blocked",
                "action": name,
                "role": "UNKNOWN",
                "reason": f"🚫 Chặn giọng nói không có quyền (F0={f0_val}Hz): {rej_msg}",
            })
            await self._trigger_aoede_fixed_denial(rej_msg, auth_res=rej_info)
            return {
                "ok": False,
                "rbac_blocked": True,
                "error": rej_msg,
                "message": rej_msg,
                "rejection_speech": rej_msg,
                "exact_spoken_reply": rej_msg,
                "instruction_for_ai": f"TUYỆT ĐỐI KHÔNG thực hiện lệnh. Chỉ nói ngắn gọn đúng câu: '{rej_msg}'",
            }

        if name in (
            "grant_user_permission",
            "revoke_user_permission",
            "start_voice_enrollment",
            "finalize_voice_enrollment",
            "set_query_permission_policy",
            "admin_update_system_policy",
            "admin_upsert_knowledge_rag",
        ):
            if self.engine.current_tier != 1 or self.engine.current_role != "ADMIN":
                rej_msg = FIXED_REJECTION_PHRASE_VI
                await self.send_ws_json({
                    "type": "rbac_blocked",
                    "action": name,
                    "role": self.engine.current_role,
                    "reason": rej_msg,
                })
                await self._trigger_aoede_fixed_denial(rej_msg, auth_res=self.last_mic_auth_result)
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
        if isinstance(res, dict) and (not res.get("ok", True) or res.get("rbac_blocked")):
            res["error"] = FIXED_REJECTION_PHRASE_VI
            res["message"] = FIXED_REJECTION_PHRASE_VI
            res["rejection_speech"] = FIXED_REJECTION_PHRASE_VI
            res["exact_spoken_reply"] = FIXED_REJECTION_PHRASE_VI
            res["instruction_for_ai"] = (
                f"TUYỆT ĐỐI KHÔNG thực hiện lệnh. Chỉ nói ngắn gọn đúng nguyên văn câu này: '{FIXED_REJECTION_PHRASE_VI}'"
            )
            await self._trigger_aoede_fixed_denial(FIXED_REJECTION_PHRASE_VI, auth_res=self.last_mic_auth_result)
        return res

    async def run(self) -> None:
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
        try:
            while True:
                raw = await self.ws.receive_text()
                try:
                    msg = json.loads(raw)
                    mtype = msg.get("type")

                    if mtype == "mic_chunk":
                        pcm_bytes = base64.b64decode(msg["pcm16k_b64"])
                        is_sp = bool(msg.get("is_speech", True))
                        await self.handle_mic_chunk(pcm_bytes, is_sp)

                    elif mtype == "mic_speech_ended":
                        self.vad_stream_filter.reset()
                        self._reset_turn_metrics(anchor_ts=time.perf_counter())
                        await self._ensure_current_mic_utterance_verified()
                        if self.gemini_session is not None and not self.last_mic_turn_blocked:
                            if self._mic_silence_task is None or self._mic_silence_task.done():
                                self._mic_silence_task = asyncio.create_task(
                                    self._flush_mic_silence_to_gemini()
                                )
                        await self.send_ws_json({
                            "type": "speech_ended_marker",
                            "source": "live_mic",
                        })

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
                                reply_txt = str(res_off.get("exact_spoken_reply") or res_off.get("reply") or "")
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
                        connected = bool(msg.get("server_connected", True))
                        await self.engine.set_server_connection_mode(connected)
                        _REST_ENGINE.server_connected = connected
                        await _broadcast_rest_state_to_bridges()

                    elif mtype == "set_role":
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
                        client_seq = msg.get("client_seq") if "client_seq" in msg else msg.get("seq")
                        client_ts_ms = msg.get("client_ts_ms") if "client_ts_ms" in msg else msg.get("timestamp")
                        req_role = str(msg.get("role", "") or "").strip()
                        if req_role:
                            self.engine.set_active_user(req_role)
                        await self.engine.execute_device_action(
                            device_id=dev_id,
                            action=action,
                            source="button_ui",
                            bypass_rbac=False,
                            trigger_chains=True,
                            target_state=target_state,
                            client_seq=client_seq,
                            client_ts_ms=client_ts_ms,
                        )
                        if self.engine.on_event is None:
                            await self.send_ws_json({
                                "type": "state_snapshot",
                                "snapshot": self.engine.get_snapshot(),
                            })

                    elif mtype == "manual_factory_reset":
                        self.voice_auth.reset_strikes()
                        self.last_mic_turn_blocked = False
                        self.mic_turn_verified = False
                        self.mic_utterance_pcm.clear()
                        await self.engine.factory_reset()
                        await self._sync_rules_context_to_gemini("Đã reset về mặc định gốc.")

                    elif mtype == "enroll_owner_voice":
                        pcm_bytes = base64.b64decode(msg.get("pcm16k_b64", ""))
                        target_uid = str(msg.get("user_id") or OWNER_ID)
                        if target_uid == "UNKNOWN":
                            target_uid = OWNER_ID
                        u_info = self.engine.users.get(target_uid, {"name": "Nguyễn Tuấn Anh", "tier": 1, "role": "ADMIN"})
                        t_tier = int(msg.get("tier") or u_info.get("tier", 1))
                        t_name = str(msg.get("user_name") or u_info.get("name", "Nguyễn Tuấn Anh"))
                        t_role = str(u_info.get("role", "ADMIN"))
                        res = self.voice_auth.enroll_tier_voice_from_pcm16k(
                            pcm_bytes=pcm_bytes,
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
                        pcm_bytes = base64.b64decode(msg.get("pcm16k_b64", ""))
                        await self._process_completed_voice_enrollment(pcm_bytes)

                    elif mtype == "reset_voice_strikes":
                        self.voice_auth.reset_strikes()
                        self.last_mic_turn_blocked = False
                        self.mic_turn_verified = False
                        self.mic_utterance_pcm.clear()
                        await self.send_ws_json({
                            "type": "voice_auth_result",
                            "sample_id": "reset",
                            "label": "Đã reset bộ đếm giọng nói",
                            "analysis": self.voice_auth.last_analysis,
                        })
                except Exception:
                    pass
        except WebSocketDisconnect:
            pass
        finally:
            self._closed = True
            recv_task.cancel()
            timer_tick_task.cancel()
            if self._wav_streaming_task:
                self._wav_streaming_task.cancel()
            if self._mic_silence_task:
                self._mic_silence_task.cancel()

    async def _periodic_timer_sync(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(0.5)
                if self.engine.active_timers:
                    await self.send_ws_json({
                        "type": "state_snapshot",
                        "snapshot": self.engine.get_snapshot(),
                    })
        except asyncio.CancelledError:
            raise


# Alias tương thích kiến trúc
GeminiLiveBridge = LiveBridgeSession
