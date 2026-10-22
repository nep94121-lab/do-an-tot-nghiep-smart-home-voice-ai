"""Kiểm tra nhanh API key với Gemini 3.8 Live.

- Đọc key từ .env (không in key ra màn hình).
- Liệt kê model Live mà key truy cập được.
- Mở 1 phiên Live, gửi 1 câu tiếng Việt, đo thời gian tới tool_call và tới âm thanh đầu tiên.

Chỉ gọi API 2 lần để tiết kiệm hạn mức.
"""

import asyncio
import pathlib
import time

from google import genai
from google.genai import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL = "gemini-3.8-live"


def load_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("Không tìm thấy GEMINI_API_KEY trong .env")


KEY = load_key()


def safe(msg: object) -> str:
    """Che key nếu nó lỡ xuất hiện trong thông báo lỗi."""
    return str(msg).replace(KEY, "***")


control_device = types.FunctionDeclaration(
    name="control_device",
    description="Bật/tắt hoặc mở/đóng thiết bị trong nhà.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "device_id": {"type": "STRING", "enum": ["main_door", "living_room_light", "fan"]},
            "action": {"type": "STRING", "enum": ["open", "close", "turn_on", "turn_off"]},
        },
        "required": ["device_id", "action"],
    },
)

CONFIG = types.LiveConnectConfig(
    response_modalities=[types.Modality.AUDIO],
    output_audio_transcription=types.AudioTranscriptionConfig(),
    system_instruction=types.Content(parts=[types.Part(text=(
        "Bạn là trợ lý nhà thông minh. Luôn trả lời bằng tiếng Việt, ngắn gọn 1 câu. "
        "Khi người dùng ra lệnh điều khiển thiết bị, gọi hàm control_device."
    ))]),
    tools=[types.Tool(function_declarations=[control_device])],
)


async def live_test(client: genai.Client) -> None:
    t0 = time.perf_counter()
    async with client.aio.live.connect(model=MODEL, config=CONFIG) as session:
        t_conn = time.perf_counter()
        print(f"  Kết nối WebSocket: {(t_conn - t0) * 1000:.0f} ms")

        t_send = time.perf_counter()
        await session.send_realtime_input(text="Mở cửa chính giúp tôi")

        t_tool = t_audio = None
        audio_bytes = 0
        transcript = []
        done = False

        # receive() trả về các message của 1 lượt rồi dừng, nên gọi lại tới khi có âm thanh.
        for _turn in range(4):
            async for msg in session.receive():
                now = time.perf_counter()
                if msg.tool_call:
                    for fc in msg.tool_call.function_calls:
                        if t_tool is None:
                            t_tool = now
                        print(f"  tool_call: {fc.name}({dict(fc.args or {})})")
                        await session.send_tool_response(function_responses=[
                            types.FunctionResponse(id=fc.id, name=fc.name, response={"result": "ok"})
                        ])
                sc = msg.server_content
                if sc:
                    if sc.model_turn:
                        for part in sc.model_turn.parts or []:
                            if part.inline_data and part.inline_data.data:
                                if t_audio is None:
                                    t_audio = now
                                audio_bytes += len(part.inline_data.data)
                    if sc.output_transcription and sc.output_transcription.text:
                        transcript.append(sc.output_transcription.text)
                    if sc.turn_complete and t_audio:
                        done = True
            if done:
                break

        def ms(t):
            return f"{(t - t_send) * 1000:.0f} ms" if t else "không nhận được"

        print(f"  Gửi câu -> tool_call:       {ms(t_tool)}")
        print(f"  Gửi câu -> âm thanh đầu:    {ms(t_audio)}")
        if t_tool and t_audio:
            first = "tool_call" if t_tool < t_audio else "âm thanh"
            print(f"  Đến trước: {first}")
        print(f"  Âm thanh nhận: {audio_bytes / 48000:.1f} giây (PCM 24 kHz 16-bit)")
        print(f"  Gemini nói: {''.join(transcript).strip() or '(không có phiên âm)'}")


async def main() -> None:
    client = genai.Client(api_key=KEY)

    print("1) Model Live mà key truy cập được:")
    try:
        names = [m.name for m in client.models.list() if "live" in (m.name or "")]
        for n in names:
            print(f"  - {n}")
        if not any(MODEL in n for n in names):
            print(f"  (không thấy {MODEL} trong danh sách)")
    except Exception as e:  # noqa: BLE001
        print(f"  LỖI: {type(e).__name__}: {safe(e)}")
        return

    print(f"\n2) Thử 1 phiên {MODEL} bằng câu tiếng Việt (văn bản vào, giọng nói ra):")
    try:
        await asyncio.wait_for(live_test(client), timeout=40)
    except asyncio.TimeoutError:
        print("  LỖI: quá 40 giây không xong")
    except Exception as e:  # noqa: BLE001
        print(f"  LỖI: {type(e).__name__}: {safe(e)}")


if __name__ == "__main__":
    asyncio.run(main())
