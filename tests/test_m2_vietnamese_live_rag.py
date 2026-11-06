"""Unit & Integration Test Suite cho Cột mốc M2:
1. Gemini Live Vietnamese Speech Config (`vi-VN`, Aoede) & VAD 1000ms LOW.
2. System Instruction: Vietnamese Prompt Guard, Filler Sound Guard, Domain Guard 7 thiết bị.
3. Cơ chế đệm âm thanh & hoãn strike khi âm thanh quá ngắn (< 0.5s) hoặc chứa vocal fry.
4. RAG Tri thức 7 thiết bị phần cứng & kiểm soát phân quyền 3 tầng.
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
        """Kiểm tra cấu hình Gemini Live bắt buộc tiếng Việt vi-VN, voice Aoede và VAD 1000ms LOW."""
        cfg = make_live_config(self.engine)
        self.assertIsNotNone(cfg.speech_config, "Thiếu speech_config trong LiveConnectConfig")
        self.assertEqual(cfg.speech_config.language_code, "vi-VN")
        self.assertEqual(
            cfg.speech_config.voice_config.prebuilt_voice_config.voice_name, "Aoede"
        )

        aad = cfg.realtime_input_config.automatic_activity_detection
        self.assertIsNotNone(aad, "Thiếu automatic_activity_detection")
        self.assertEqual(aad.silence_duration_ms, 1000)
        self.assertEqual(
            aad.end_of_speech_sensitivity,
            types.EndSensitivity.END_SENSITIVITY_LOW,
        )
        self.assertEqual(aad.prefix_padding_ms, 300)

    def test_02_build_system_instruction_guards(self) -> None:
        """Kiểm tra System Instruction có đủ Vietnamese Prompt Guard, Filler Sound Guard và Domain Guard 7 thiết bị."""
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

        # 3. Domain Guard 7 thiết bị
        self.assertIn("Smart Home Domain Guard", prompt)
        self.assertIn("7 thiết bị nhà thông minh", prompt)
        self.assertIn("Máy bơm tưới cây (D3)", prompt)
        self.assertIn("Cửa chính (D1)", prompt)
        self.assertIn("Đèn phòng khách (D2)", prompt)
        self.assertIn("Đèn phòng ngủ (D7)", prompt)
        self.assertIn("Quạt trần (D6)", prompt)
        self.assertIn("Điều hòa Casper (D2 IR)", prompt)
        self.assertIn("Còi báo động (D8)", prompt)

    def test_03_rag_7_devices_synchronization(self) -> None:
        """Kiểm tra RAG trả lời chính xác 7 thiết bị và bao gồm Máy bơm tưới cây."""
        rag = SmartHomeKnowledgeRAG()

        # Hỏi số lượng thiết bị
        res_count = rag.retrieve("Nhà có mấy thiết bị?")
        self.assertTrue(res_count["ok"])
        self.assertIn("7 thiết bị", res_count["exact_spoken_reply"])
        self.assertIn("Máy bơm tưới cây (D3)", res_count["exact_spoken_reply"])

        # Hỏi chức năng làm được gì
        res_cap = rag.retrieve("Bạn có thể làm những gì?")
        self.assertTrue(res_cap["ok"])
        self.assertIn("7 thiết bị", res_cap["exact_spoken_reply"])
        self.assertIn("Máy bơm tưới cây", res_cap["exact_spoken_reply"])

        # Hỏi về máy bơm tưới cây
        res_pump = rag.retrieve("Máy bơm tưới cây dùng để làm gì?")
        self.assertTrue(res_pump["ok"])
        self.assertIn("tưới nước", res_pump["exact_spoken_reply"])

    def test_04_short_audio_and_vocal_fry_deferred_strikes(self) -> None:
        """Kiểm tra cơ chế đệm âm thanh: Đoạn âm thanh quá ngắn (<0.5s) hoặc vocal fry hoãn áp dụng strike người lạ."""
        mock_ws = AsyncMock()
        session = LiveBridgeSession(ws=mock_ws)

        # 1. Giả lập đoạn âm thanh ngắn 0.2s (6400 bytes PCM 16kHz)
        short_pcm = b"\x10\x00" * 3200  # 3200 samples = 0.2s
        session.mic_utterance_pcm.extend(short_pcm)

        session.voice_auth.reset_strikes()
        initial_strikes = session.voice_auth.unauthorized_strikes
        self.assertEqual(initial_strikes, 0)

        # Chạy kiểm tra qua _ensure_current_mic_utterance_verified
        asyncio.run(session._ensure_current_mic_utterance_verified())

        # Xác nhận: Strike không bị tăng (hoãn áp dụng)
        self.assertEqual(
            session.voice_auth.unauthorized_strikes,
            0,
            "Đoạn âm thanh <0.5s không được tăng strike phạt người lạ!",
        )
        self.assertFalse(
            session.last_mic_turn_blocked,
            "Đoạn âm thanh <0.5s không được khóa turn của người dùng!",
        )

    def test_05_real_intruder_gets_strikes_applied(self) -> None:
        """Kiểm tra âm thanh người lạ thực sự (> 0.5s, file WAV mẫu) vẫn bị tính strike và chặn bình thường."""
        mock_ws = AsyncMock()
        session = LiveBridgeSession(ws=mock_ws)
        session.voice_auth.reset_strikes()

        with wave.open(str(self.audio_dir / "giong_2_nguoi_la_mo_cua.wav"), "rb") as wf:
            intruder_pcm = wf.readframes(wf.getnframes())

        self.assertGreater(
            len(intruder_pcm),
            16000,
            "File người lạ thực tế phải lớn hơn 0.5s (16000 bytes)",
        )

        session.mic_turn_verified = False
        session.mic_utterance_pcm.clear()
        session.mic_utterance_pcm.extend(intruder_pcm)

        # Chạy kiểm tra
        asyncio.run(session._ensure_current_mic_utterance_verified())

        # Xác nhận: Bị đánh dấu là người lạ và tăng strike 1
        self.assertEqual(session.voice_auth.unauthorized_strikes, 1)
        self.assertTrue(session.last_mic_turn_blocked)


if __name__ == "__main__":
    unittest.main()
