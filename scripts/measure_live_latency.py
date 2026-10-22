"""Đo độ trễ Gemini 3.8 Live với âm thanh giọng nói tiếng Việt (giả lập mic).

Âm thanh được gửi theo nhịp thời gian thực (gói 20 ms) giống mic thật.
Mốc 0 = lúc gửi xong gói âm thanh cuối cùng của câu nói ("dứt lời").

3 chế độ phát hiện dứt lời:
  hybrid500  : client chờ 500 ms im lặng rồi gửi audio_stream_end (mức Google khuyến nghị)
  server_vad : client không báo gì, gửi im lặng liên tục, để server tự phát hiện (mặc định ~800 ms)
  hybrid0    : gửi audio_stream_end ngay khi hết câu (chỉ để tham khảo; Google không khuyến nghị
               vì với người nói thật dễ cắt mất câu)

Không tính: chặng Wi-Fi ESP32 -> laptop và thời gian đóng relay.
"""

import asyncio
import json
import pathlib
import statistics
import sys
import time
import wave

from google import genai
from google.genai import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL = "gemini-3.8-live"
CHUNK_MS = 20
CHUNK_SAMPLES = 16000 * CHUNK_MS // 1000
SILENCE = b"\x00\x00" * CHUNK_SAMPLES
RUNS_PER_MODE = int(sys.argv[1]) if len(sys.argv) > 1 else 5
MODES = sys.argv[2].split(",") if len(sys.argv) > 2 else ["server_vad", "server_vad500", "manual500", "manual0"]

PHRASES = ["mo_cua_chinh", "bat_den_phong_khach", "tat_quat"]


def load_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("Không tìm thấy GEMINI_API_KEY trong .env")


KEY = load_key()


def safe(msg: object) -> str:
    return str(msg).replace(KEY, "***")


def load_chunks(name: str) -> list[bytes]:
    with wave.open(str(ROOT / "test_audio" / f"{name}.wav")) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
        data = w.readframes(w.getnframes())
    step = CHUNK_SAMPLES * 2
    chunks = [data[i:i + step] for i in range(0, len(data), step)]
    chunks[-1] = chunks[-1].ljust(step, b"\x00")
    return chunks


control_device = types.FunctionDeclaration(
    name="control_device",
    description="Bật/tắt hoặc mở/đóng thiết bị trong nhà.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "device_id": {"type": "STRING",
                          "enum": ["main_door", "living_room_light", "fan"]},
            "action": {"type": "STRING", "enum": ["open", "close", "turn_on", "turn_off"]},
        },
        "required": ["device_id", "action"],
    },
)

def make_config(mode: str) -> types.LiveConnectConfig:
    rt = None
    if mode == "server_vad500":
        rt = types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(silence_duration_ms=500))
    elif mode.startswith("manual"):
        rt = types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True))
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=rt,
        system_instruction=types.Content(parts=[types.Part(text=(
            "Bạn là trợ lý nhà thông minh. Luôn trả lời bằng tiếng Việt, ngắn gọn 1 câu. "
            "Khi người dùng ra lệnh điều khiển thiết bị, gọi hàm control_device ngay."
        ))]),
        tools=[types.Tool(function_declarations=[control_device])],
    )


async def pace_send(session, chunks: list[bytes]) -> float:
    """Gửi các gói theo nhịp thời gian thực. Trả về thời điểm gửi xong gói cuối."""
    start = time.perf_counter()
    for i, c in enumerate(chunks):
        delay = start + i * CHUNK_MS / 1000 - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        await session.send_realtime_input(audio=types.Blob(data=c, mime_type="audio/pcm;rate=16000"))
    return time.perf_counter()


async def silence_until(session, stop: asyncio.Event):
    """Gửi im lặng liên tục như mic đang mở, tới khi có phản hồi."""
    start = time.perf_counter()
    i = 0
    while not stop.is_set():
        delay = start + i * CHUNK_MS / 1000 - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        await session.send_realtime_input(audio=types.Blob(data=SILENCE, mime_type="audio/pcm;rate=16000"))
        i += 1


async def sender(session, mode: str, chunks: list[bytes], t_end_box: list, stop: asyncio.Event):
    if mode.startswith("manual"):
        # VAD thủ công: kèm 200 ms âm thanh trước khi nói (tài liệu yêu cầu client tự thêm)
        await session.send_realtime_input(activity_start=types.ActivityStart())
        await pace_send(session, [SILENCE] * (200 // CHUNK_MS))
    t_end_box.append(await pace_send(session, chunks))
    if mode == "hybrid0":
        await session.send_realtime_input(audio_stream_end=True)
    elif mode == "hybrid500":
        await pace_send(session, [SILENCE] * (500 // CHUNK_MS))
        await session.send_realtime_input(audio_stream_end=True)
    elif mode in ("server_vad", "server_vad500"):
        await silence_until(session, stop)
    elif mode == "manual500":
        # giả lập client VAD chờ 500 ms im lặng rồi báo hết lượt
        await pace_send(session, [SILENCE] * (500 // CHUNK_MS))
        await session.send_realtime_input(activity_end=types.ActivityEnd())
    elif mode == "manual0":
        await session.send_realtime_input(activity_end=types.ActivityEnd())


DEBUG = bool(int(__import__("os").environ.get("LIVE_DEBUG", "0")))


async def pump(session, q: asyncio.Queue):
    """receive() dừng sau mỗi lượt nên gọi lại liên tục, đẩy message vào hàng đợi."""
    try:
        while True:
            async for msg in session.receive():
                if DEBUG:
                    sc = msg.server_content
                    parts = []
                    if msg.tool_call:
                        parts.append("tool_call")
                    if sc:
                        if sc.input_transcription:
                            parts.append(f"in_tx='{sc.input_transcription.text}'")
                        if sc.output_transcription:
                            parts.append(f"out_tx='{sc.output_transcription.text}'")
                        if sc.model_turn:
                            parts.append("model_turn")
                        if sc.turn_complete:
                            parts.append("turn_complete")
                        if sc.interrupted:
                            parts.append("interrupted")
                    if not parts:
                        parts.append(str(msg)[:200])
                    print(f"    <- {time.perf_counter():.3f} {' '.join(parts)}", flush=True)
                await q.put((time.perf_counter(), msg))
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"  LỖI vòng nhận: {type(e).__name__}: {safe(e)}", flush=True)


async def one_command(session, q: asyncio.Queue, mode: str, phrase: str) -> dict:
    while not q.empty():
        q.get_nowait()
    stop = asyncio.Event()
    t_end_box: list[float] = []
    send_task = asyncio.create_task(sender(session, mode, load_chunks(phrase), t_end_box, stop))

    t_tool = t_audio = None
    tool_desc = None
    heard, said = [], []
    deadline = time.perf_counter() + 25
    try:
        while time.perf_counter() < deadline:
            try:
                t, msg = await asyncio.wait_for(q.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if t_tool and t_audio and t_end_box and time.perf_counter() - max(t_tool, t_audio) > 2:
                    break
                continue
            if msg.tool_call:
                for fc in msg.tool_call.function_calls:
                    if t_tool is None:
                        t_tool = t
                        tool_desc = f"{fc.name}({json.dumps(dict(fc.args or {}), ensure_ascii=False)})"
                    await session.send_tool_response(function_responses=[
                        types.FunctionResponse(id=fc.id, name=fc.name, response={"result": "ok"})])
            sc = msg.server_content
            if sc:
                if sc.input_transcription and sc.input_transcription.text:
                    heard.append(sc.input_transcription.text)
                if sc.output_transcription and sc.output_transcription.text:
                    said.append(sc.output_transcription.text)
                if sc.model_turn:
                    for p in sc.model_turn.parts or []:
                        if p.inline_data and p.inline_data.data and t_audio is None:
                            t_audio = t
                if sc.turn_complete and t_tool and t_audio:
                    break
    finally:
        stop.set()
        await send_task

    t_end = t_end_box[0]
    ms = lambda x: round((x - t_end) * 1000) if x else None  # noqa: E731
    return {"mode": mode, "phrase": phrase,
            "tool_ms": ms(t_tool), "audio_ms": ms(t_audio),
            "tool": tool_desc, "heard": "".join(heard).strip(), "said": "".join(said).strip()}


async def run_mode(client, mode: str) -> list[dict]:
    results = []
    async with client.aio.live.connect(model=MODEL, config=make_config(mode)) as session:
        q: asyncio.Queue = asyncio.Queue()
        pump_task = asyncio.create_task(pump(session, q))
        try:
            for i in range(RUNS_PER_MODE):
                phrase = PHRASES[i % len(PHRASES)]
                r = await one_command(session, q, mode, phrase)
                results.append(r)
                print(f"  [{mode}] #{i + 1} {phrase:22s} tool_call={r['tool_ms']} ms  "
                      f"âm_thanh={r['audio_ms']} ms  | nghe: '{r['heard']}' | {r['tool']} | nói: '{r['said']}'",
                      flush=True)
                await asyncio.sleep(1.5)
        finally:
            pump_task.cancel()
    return results


def summarize(rows: list[dict], key: str) -> str:
    vals = [r[key] for r in rows if r[key] is not None]
    if not vals:
        return "không có dữ liệu"
    return (f"n={len(vals)}  min={min(vals)}  trung_vị={round(statistics.median(vals))}  "
            f"max={max(vals)} ms")


async def main():
    client = genai.Client(api_key=KEY)
    all_rows = []
    for mode in MODES:
        print(f"\n=== Chế độ {mode} ===", flush=True)
        try:
            all_rows += await run_mode(client, mode)
        except Exception as e:  # noqa: BLE001
            print(f"  LỖI: {type(e).__name__}: {safe(e)}", flush=True)

    print("\n=== TỔNG HỢP (tính từ lúc dứt lời) ===")
    for mode in MODES:
        rows = [r for r in all_rows if r["mode"] == mode]
        if rows:
            print(f"{mode:11s} tool_call : {summarize(rows, 'tool_ms')}")
            print(f"{'':11s} âm thanh  : {summarize(rows, 'audio_ms')}")
            first_tool = sum(1 for r in rows if r['tool_ms'] is not None and r['audio_ms'] is not None
                             and r['tool_ms'] < r['audio_ms'])
            both = sum(1 for r in rows if r['tool_ms'] is not None and r['audio_ms'] is not None)
            print(f"{'':11s} tool_call đến trước âm thanh: {first_tool}/{both} lần")

    out = ROOT / "test_audio" / f"latency_results_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nĐã lưu: {out}")


if __name__ == "__main__":
    asyncio.run(main())
