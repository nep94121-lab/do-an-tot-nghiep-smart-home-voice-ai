#!/usr/bin/env python3
"""Script sinh mới và kiểm chứng độc lập hai tệp âm thanh WAV của giọng Aoede (Gemini Live).

Yêu cầu 4:
- Một câu từ chối cố định duy nhất cho Người lạ và Vượt quyền:
  "Xin lỗi, bạn không có quyền thực hiện lệnh này."
- Một câu yêu cầu nói lại cố định duy nhất cho Safe-Deny:
  "Âm thanh chưa rõ, vui lòng nói lại."
- Duy nhất giọng đọc tích hợp `Aoede` của Gemini Live (gemini-3.8-live, voice_name='Aoede').
- Lưu biên nhận chứng thực `simulator/data/AOEDE_AUDIO_RECEIPT.json` với chữ ký SHA-256,
  thời lượng, phổ năng lượng, và kết quả chép lời (transcription) kiểm chứng độc lập.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
import pathlib
import sys
import time
import wave
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env if present
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from simulator.live.tts_rejection_vi import (
    AOEDE_LIVE_MODEL,
    AOEDE_VOICE_NAME,
    FIXED_REJECTION_PHRASE_VI,
    FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
    SAMPLE_RATE,
    _fetch_live_aoede_pcm24k,
    _wrap_pcm24k_to_wav,
)

DATA_DIR = ROOT / "simulator" / "data"
REJECTION_WAV = DATA_DIR / "aoede_rejection_24k.wav"
REPEAT_WAV = DATA_DIR / "aoede_repeat_24k.wav"
RECEIPT_FILE = DATA_DIR / "AOEDE_AUDIO_RECEIPT.json"


def compute_audio_metrics(wav_bytes: bytes) -> dict[str, Any]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        raw_pcm = wf.readframes(nframes)
    duration_s = float(nframes) / float(framerate) if framerate > 0 else 0.0
    import numpy as np

    pcm_arr = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(pcm_arr**2) + 1e-12))
    rms_dbfs = float(20.0 * np.log10(max(rms, 1e-6)))
    peak = float(np.max(np.abs(pcm_arr))) if len(pcm_arr) > 0 else 0.0
    peak_dbfs = float(20.0 * np.log10(max(peak, 1e-6)))
    sha256 = hashlib.sha256(wav_bytes).hexdigest()
    return {
        "channels": channels,
        "sample_width_bytes": sampwidth,
        "sample_rate_hz": framerate,
        "total_frames": nframes,
        "duration_sec": round(duration_s, 3),
        "rms": round(rms, 5),
        "rms_dbfs": round(rms_dbfs, 2),
        "peak": round(peak, 5),
        "peak_dbfs": round(peak_dbfs, 2),
        "sha256": sha256,
        "byte_length": len(wav_bytes),
    }


async def transcribe_audio_with_gemini(wav_bytes: bytes, api_key: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    prompt = (
        "Hãy nghe đoạn âm thanh này và chép lại nguyên văn từng từ tiếng Việt "
        "(chỉ trả về đúng văn bản được nói, không thêm bất kỳ từ ngữ hay dấu ngoặc giải thích nào):"
    )
    resp = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-3.8-flash",
        contents=[types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"), prompt],
    )
    return str(resp.text or "").strip()


async def generate_and_verify_all() -> dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY chưa được cấu hình để sinh âm thanh trực tiếp từ Gemini Live!")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        ("rejection", FIXED_REJECTION_PHRASE_VI, REJECTION_WAV),
        ("safe_deny_repeat", FIXED_SAFE_DENY_REPEAT_PHRASE_VI, REPEAT_WAV),
    ]

    receipt_entries: dict[str, Any] = {
        "generator_model": AOEDE_LIVE_MODEL,
        "voice_name": AOEDE_VOICE_NAME,
        "language_code": "vi-VN",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phrases": {},
    }

    for key, phrase, target_path in targets:
        print(f"[*] Đang yêu cầu Gemini Live ({AOEDE_LIVE_MODEL}, voice={AOEDE_VOICE_NAME}) sinh câu: '{phrase}'...")
        pcm = await _fetch_live_aoede_pcm24k(phrase, api_key)
        if len(pcm) < SAMPLE_RATE * 2:
            raise RuntimeError(f"Luồng PCM nhận được quá ngắn ({len(pcm)} bytes) cho câu '{phrase}'!")
        wav = _wrap_pcm24k_to_wav(pcm)
        target_path.write_bytes(wav)
        metrics = compute_audio_metrics(wav)
        print(f"    -> Đã ghi {target_path.name}: {metrics['duration_sec']}s, {metrics['byte_length']} bytes, SHA256={metrics['sha256'][:16]}...")

        print(f"[*] Đang kiểm chứng độc lập lời nói bằng mô hình Gemini Audio...")
        transcription = await transcribe_audio_with_gemini(wav, api_key)
        print(f"    -> Nguyên văn mong muốn: {phrase}")
        print(f"    -> Chép lời thực tế:     {transcription}")

        # Chuẩn hóa so sánh bỏ dấu câu và khoảng trắng thừa
        import re
        norm_target = re.sub(r"[^\w\s]", "", phrase.lower()).split()
        norm_trans = re.sub(r"[^\w\s]", "", transcription.lower()).split()
        match_ok = bool(norm_target == norm_trans)

        receipt_entries["phrases"][key] = {
            "phrase_text": phrase,
            "filename": target_path.name,
            "metrics": metrics,
            "independent_transcription": transcription,
            "content_verified": match_ok,
        }

    receipt_bytes = (json.dumps(receipt_entries, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    RECEIPT_FILE.write_bytes(receipt_bytes)
    print(f"[+] Hoàn tất! Đã lưu biên nhận chứng thực vào {RECEIPT_FILE.relative_to(ROOT)}")
    return receipt_entries


if __name__ == "__main__":
    asyncio.run(generate_and_verify_all())
