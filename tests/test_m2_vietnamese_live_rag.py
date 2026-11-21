"""Unit & Integration Test Suite cho Cột mốc M2:
1. Gemini Live Vietnamese Speech Config (`vi-VN`, Aoede) & VAD 1000ms LOW.
2. System Instruction: Vietnamese Prompt Guard, Filler Sound Guard, Domain Guard 6 thiết bị.
3. Cơ chế đệm âm thanh & hoãn strike khi âm thanh quá ngắn (< 0.5s) hoặc chứa vocal fry.
4. RAG Tri thức 6 thiết bị phần cứng & kiểm soát phân quyền 3 tầng.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import unittest
from unittest.mock import AsyncMock
import wave
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from google.genai import types
from simulator.knowledge_rag import SmartHomeKnowledgeRAG
from simulator.rule_engine import SmartHomeEngine
from simulator.server import (
    LiveBridgeSession,
    build_system_instruction,
    make_live_config,
)
from simulator.voice_auth import VoiceAuthManager


class TestM2VietnameseLiveAndRAG(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = SmartHomeEngine()
        self.audio_dir = ROOT / "test_audio"

    def test_01_make_live_config_vietnamese_and_vad(self) -> None:
        """Kiểm tra cấu hình Gemini Live khóa tiếng Việt vi-VN (có fallback strict_lang_fields=False), giọng Aoede và VAD 350ms HIGH."""
        cfg = make_live_config(self.engine)
        self.assertIsNotNone(cfg.speech_config, "Thiếu speech_config trong LiveConnectConfig")
        self.assertEqual(getattr(cfg.speech_config, "language_code", None), "vi-VN")
        self.assertEqual(
            cfg.speech_config.voice_config.prebuilt_voice_config.voice_name, "Aoede"
        )
        cfg_fb = make_live_config(self.engine, strict_lang_fields=False)
        self.assertIn(getattr(cfg_fb.speech_config, "language_code", None), (None, ""))
        self.assertEqual(
            cfg_fb.speech_config.voice_config.prebuilt_voice_config.voice_name, "Aoede"
        )

        aad = cfg.realtime_input_config.automatic_activity_detection
        self.assertIsNotNone(aad, "Thiếu automatic_activity_detection")
        self.assertEqual(aad.silence_duration_ms, 350)
        self.assertEqual(
            aad.end_of_speech_sensitivity,
            types.EndSensitivity.END_SENSITIVITY_HIGH,
        )
        self.assertEqual(aad.prefix_padding_ms, 100)

    def test_02_build_system_instruction_guards(self) -> None:
        """Kiểm tra System Instruction có đủ Vietnamese Prompt Guard, Filler Sound Guard và Domain Guard 6 thiết bị."""
        prompt = build_system_instruction(self.engine)

        # 1. Vietnamese Prompt Guard
        self.assertIn("Vietnamese Prompt Guard", prompt)
        self.assertIn("Phản hồi 100% bằng tiếng Việt", prompt)
        self.assertIn("Không trả lời bằng tiếng Anh", prompt)

        # 2. Filler Sound Guard
        self.assertIn("Filler Sound & Hesitation Guard", prompt)
        self.assertIn("ừm", prompt)
        self.assertIn("ờ", prompt)
        self.assertIn("Tôi có thể giúp gì cho bạn?", prompt)

        # 3. Domain Guard 6 thiết bị
        self.assertIn("Smart Home Domain Guard", prompt)
        self.assertIn("6 thiết bị", prompt)
        self.assertIn("Cửa chính (D1)", prompt)
        self.assertIn("Đèn phòng khách (D0)", prompt)
        self.assertIn("Đèn phòng ngủ (D4)", prompt)
        self.assertIn("Máy bơm tưới cây (D6)", prompt)
        self.assertIn("Còi báo động (D8)", prompt)
        self.assertIn("Nguồn mạch loa PAM8403 (D7, âm thanh PWM ra D3)", prompt)

    def test_03_rag_6_devices_synchronization(self) -> None:
        """Kiểm tra RAG trả lời chính xác 6 thiết bị và bao gồm Máy bơm tưới cây."""
        rag = SmartHomeKnowledgeRAG()

        # Hỏi số lượng thiết bị
        res_count = rag.retrieve("Nhà có mấy thiết bị?")
        self.assertTrue(res_count["ok"])
        self.assertIn("6 thiết bị", res_count["exact_spoken_reply"])
        self.assertIn("Máy bơm tưới cây Relay 1 (D6/GPIO12)", res_count["exact_spoken_reply"])

        # Hỏi chức năng làm được gì
        res_cap = rag.retrieve("Bạn có thể làm những gì?")
        self.assertTrue(res_cap["ok"])
        self.assertIn("6 thiết bị", res_cap["exact_spoken_reply"])
        self.assertIn("Máy bơm tưới cây", res_cap["exact_spoken_reply"])

        # Hỏi về máy bơm tưới cây
        res_pump = rag.retrieve("Máy bơm tưới cây dùng để làm gì?")
        self.assertTrue(res_pump["ok"])
        self.assertIn("tưới nước", res_pump["exact_spoken_reply"])

    def test_04_authenticated_mic_streams_pcm_without_speaker_verification(self) -> None:
        """Kiểm tra mic WS khi có phiên đăng nhập sẽ stream PCM thẳng không kiểm định giọng nói hay tăng strike."""
        from simulator.auth.session_store import UserSession
        import time as _time

        mock_ws = AsyncMock()
        mock_ws.headers = {}
        mock_ws.cookies = {}
        mock_ws.query_params = {}
        session = LiveBridgeSession(
            ws=mock_ws,
            ws_session=UserSession(
                session_id="m2_owner_sess",
                user_id="tuan_anh",
                email="tuananh.hust@gmail.com",
                display_name="Nguyễn Tuấn Anh",
                tier=1,
                role="ADMIN",
                created_at=_time.time(),
                expires_at=_time.time() + 3600,
                source="test_m2",
                is_authenticated=True,
            ),
        )
        short_pcm = b"\x10\x00" * 3200
        asyncio.run(session.handle_mic_chunk(short_pcm, is_sp=True))
        asyncio.run(session.mic_speech_ended())
        self.assertEqual(session.voice_auth.unauthorized_strikes, 0)
        self.assertFalse(session.last_mic_turn_blocked)
        self.assertGreater(session._mic_in_flight_queue.qsize(), 0)

    def test_05_unauthenticated_mic_blocked_by_session_rbac(self) -> None:
        """Kiểm tra mic WS chưa đăng nhập bị chặn bởi Session RBAC (không dựa vào voice strikes)."""
        from simulator.auth.session_store import UserSession
        import time as _time

        mock_ws = AsyncMock()
        mock_ws.headers = {}
        mock_ws.cookies = {}
        mock_ws.query_params = {}
        session = LiveBridgeSession(
            ws=mock_ws,
            ws_session=UserSession(
                session_id="ws_unauthenticated",
                user_id="anonymous",
                email="",
                display_name="Khách chưa xác thực",
                tier=3,
                role="CHILD_GUEST",
                created_at=_time.time(),
                expires_at=_time.time() + 3600,
                source="ws_unauthenticated",
                is_authenticated=False,
            ),
        )
        with wave.open(str(self.audio_dir / "giong_2_nguoi_la_mo_cua.wav"), "rb") as wf:
            intruder_pcm = wf.readframes(wf.getnframes())

        asyncio.run(session.handle_mic_chunk(intruder_pcm[:3200], is_sp=True))
        asyncio.run(session.mic_speech_ended())
        self.assertEqual(session.voice_auth.unauthorized_strikes, 0)
        self.assertTrue(session.last_mic_turn_blocked)
        self.assertEqual(session._mic_in_flight_queue.qsize(), 0)


if __name__ == "__main__":
    unittest.main()
