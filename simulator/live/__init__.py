"""Package simulator.live: Tầng Xử lý Gemini 3.8 Live API, WebSocket & Server-Side TTS 24kHz.

Exports:
- LiveBridgeSession, GeminiLiveBridge, MODEL, _sanitize_vietnamese_input_transcript
- build_system_instruction, make_live_config, ALL_TOOLS
- synthesize_vi_rejection_audio_24k, get_rejection_audio_b64, get_rejection_speech_text
"""

from __future__ import annotations

from .gemini_bridge import (
    MODEL,
    GeminiLiveBridge,
    LiveBridgeSession,
    _sanitize_vietnamese_input_transcript,
)
from .prompt_builder import (
    ALL_TOOLS,
    build_system_instruction,
    make_live_config,
)
from .tool_dispatcher_mixin import LiveToolDispatcherMixin
from .tts_rejection_vi import (
    get_rejection_audio_b64,
    get_rejection_speech_text,
    synthesize_vi_rejection_audio_24k,
)

__all__ = [
    "MODEL",
    "LiveBridgeSession",
    "GeminiLiveBridge",
    "LiveToolDispatcherMixin",
    "_sanitize_vietnamese_input_transcript",
    "build_system_instruction",
    "make_live_config",
    "ALL_TOOLS",
    "synthesize_vi_rejection_audio_24k",
    "get_rejection_audio_b64",
    "get_rejection_speech_text",
]
