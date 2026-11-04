"""Voice DSP and Biometrics Neural Engine.

Package simulator.voice:
- biometrics_neural: Neural Speaker Embedding 256D, check_duplicate_voice_gate, verify_speaker_identity_256d.
- vad_vietnamese: VietnameseVADStreamFilter, is_vietnamese_speech, validate_voice_enrollment_quality.
- denoiser: denoise_and_isolate_human_voice (85Hz-3900Hz Wiener filter).
"""

from __future__ import annotations

from .biometrics_neural import (
    extract_neural_embedding_256d,
    compute_neural_similarity,
    check_duplicate_voice_gate,
    verify_speaker_identity_256d,
)
from .vad_vietnamese import (
    VietnameseVADStreamFilter,
    is_vietnamese_speech,
    validate_voice_enrollment_quality,
)
from .denoiser import denoise_and_isolate_human_voice

__all__ = [
    "extract_neural_embedding_256d",
    "compute_neural_similarity",
    "check_duplicate_voice_gate",
    "verify_speaker_identity_256d",
    "VietnameseVADStreamFilter",
    "is_vietnamese_speech",
    "validate_voice_enrollment_quality",
    "denoise_and_isolate_human_voice",
]
