"""Package simulator.live: Tầng Xử lý Gemini 3.8 Live API (Giọng Aoede) & WebSocket.

Exports:
- LiveBridgeSession, GeminiLiveBridge, MODEL, _sanitize_vietnamese_input_transcript
- build_system_instruction, make_live_config, ALL_TOOLS
- FIXED_REJECTION_PHRASE_VI, FIXED_SAFE_DENY_REPEAT_PHRASE_VI, get_rejection_speech_text
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
    FIXED_REJECTION_PHRASE_VI,
    FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
    build_system_instruction,
    make_live_config,
)
from .tool_dispatcher_mixin import LiveToolDispatcherMixin
from .tts_rejection_vi import (
    SAFE_DENY_REPEAT_PHRASE_VI,
    UNIFIED_REJECTION_PHRASE_VI,
    get_rejection_speech_text,
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
    "FIXED_REJECTION_PHRASE_VI",
    "FIXED_SAFE_DENY_REPEAT_PHRASE_VI",
    "UNIFIED_REJECTION_PHRASE_VI",
    "SAFE_DENY_REPEAT_PHRASE_VI",
    "get_rejection_speech_text",
]
