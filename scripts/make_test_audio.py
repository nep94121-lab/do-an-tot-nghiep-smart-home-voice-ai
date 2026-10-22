"""Tạo file giọng nói tiếng Việt 16kHz PCM mono (.wav) bằng Gemini 3.8 Live Audio (không phụ thuộc scipy)."""

from __future__ import annotations

import asyncio
import pathlib
import wave

import numpy as np
from google import genai
from google.genai import types

print("Bắt đầu khởi tạo make_test_audio.py...", flush=True)

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "test_audio"
LIVE_MODEL = "gemini-3.8-live"

PHRASES = {
    "luat_1_chieu_cua_dieu_hoa": "Nếu mở cửa chính thì điều hòa phải mở",
    "doi_lenh_vung_oi": "Đổi lệnh mở cửa chính thành Vừng ơi mở ra",
    "vung_oi_mo_ra": "Vừng ơi mở ra",
    "dong_cua_chinh": "Đóng cửa chính",
    "hen_gio_30s_den_khach": "Hẹn 30 giây nữa bật đèn phòng khách",
    "hoi_be_hen_gio": "Trong bể hẹn giờ đang có bao nhiêu lịch hẹn và đó là những gì",
    "yeu_cau_reset": "Reset hệ thống",
    "xac_nhan_reset": "Đúng rồi, reset tất cả đi",
}


def load_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("Không tìm thấy GEMINI_API_KEY trong .env")


def pcm24k_to_pcm16k(raw_pcm24k: bytes) -> np.ndarray:
    pcm24 = np.frombuffer(raw_pcm24k, dtype=np.int16).astype(np.float32)
    if pcm24.size == 0:
        return np.zeros(1600, dtype=np.int16)
    n_out = int(round(pcm24.size * 16000.0 / 24000.0))
    x_old = np.linspace(0.0, 1.0, num=pcm24.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    pcm16 = np.interp(x_new, x_old, pcm24)
    return np.clip(pcm16, -32768, 32767).astype(np.int16)


def trim_silence(pcm: np.ndarray, thresh: int = 400) -> np.ndarray:
    idx = np.where(np.abs(pcm) > thresh)[0]
    return pcm if idx.size == 0 else pcm[idx[0] : idx[-1] + 1]


async def synth_one(client: genai.Client, name: str, text: str) -> None:
    path = OUT / f"{name}.wav"
    if path.exists():
        print(f"  [SKIP] Đã có {path.name}", flush=True)
        return

    cfg = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=types.Content(
            parts=[
                types.Part(
                    text=(
                        "Bạn là máy phát âm tiếng Việt. Khi nhận được câu nào, hãy ĐỌC NGUYÊN VĂN câu đó "
                        "bằng tiếng Việt rõ ràng, không thêm bớt bất kỳ từ nào."
                    )
                )
            ]
        ),
    )
    async with client.aio.live.connect(model=LIVE_MODEL, config=cfg) as session:
        await session.send_client_content(
            turns=[types.Content(role="user", parts=[types.Part(text=f"Đọc nguyên văn: {text}")])],
            turn_complete=True,
        )
        buf = bytearray()
        said = []
        async for msg in session.receive():
            sc = msg.server_content
            if sc:
                if sc.output_transcription and sc.output_transcription.text:
                    said.append(sc.output_transcription.text)
                if sc.model_turn and sc.model_turn.parts:
                    for p in sc.model_turn.parts:
                        if p.inline_data and p.inline_data.data:
                            buf.extend(p.inline_data.data)
                if sc.turn_complete:
                    break

    pcm16k = trim_silence(pcm24k_to_pcm16k(bytes(buf)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm16k.tobytes())
    print(f"  [OK] {path.name} ({len(pcm16k)/16000:.2f}s) -> '{''.join(said).strip()}'", flush=True)


async def main() -> None:
    key = load_key()
    client = genai.Client(api_key=key)
    OUT.mkdir(exist_ok=True)
    # Chạy song song theo lô 4 câu để tạo cực nhanh trong ~3 giây
    items = list(PHRASES.items())
    for i in range(0, len(items), 4):
        batch = items[i : i + 4]
        await asyncio.gather(*(synth_one(client, k, v) for k, v in batch))
    print("Hoàn tất tạo toàn bộ file WAV 16kHz!", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
