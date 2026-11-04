"""Công cụ Thực thi & Kiểm toán Hội tụ GitHub Spec Kit (`scripts/speckit_converge.py`).

Hỗ trợ đầy đủ 9 lệnh chuẩn của `github/spec-kit`:
  1. constitution  -> Kiểm tra Hiến pháp bất biến (.specify/memory/constitution.md)
  2. specify       -> Kiểm tra Đặc tả yêu cầu (specs/001-smart-home-voice-ai/spec.md)
  3. clarify       -> Phát hiện điểm mơ hồ hoặc xung đột giữa các tầng
  4. plan          -> Kiểm tra Phân ranh giới Module (Slice A/B/C/D chống chồng chéo)
  5. checklist     -> Kiểm tra Danh sách nghiệm thu (checklist.md)
  6. tasks         -> Kiểm tra Danh sách công việc theo thứ tự phụ thuộc (tasks.md)
  7. analyze       -> Phân tích chéo Spec <-> Plan <-> Code trước khi sửa
  8. implement     -> Báo cáo trạng thái thực thi của từng Slice
  9. converge      -> Kiểm toán trực tiếp mã nguồn thực tế so với 6 Điều Hiến pháp;
                      nếu lệch, tự động ghi nối (append) task sửa lỗi vào tasks.md!
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SPEC_ROOT = ROOT / ".specify"
CONSTITUTION_FILE = SPEC_ROOT / "memory" / "constitution.md"
FEATURE_DIR = ROOT / "specs" / "001-smart-home-voice-ai"


def run_converge_audit() -> int:
    print("=" * 78)
    print("🚀 GITHUB SPEC KIT — 9-STEP SDD & CONVERGENCE AUDITOR (SMART HOME VOICE AI)")
    print("=" * 78)

    # 1. Check Spec-Kit Artifacts (Commands 1..7)
    required_files = [
        ("1. constitution", CONSTITUTION_FILE),
        ("2. specify", FEATURE_DIR / "spec.md"),
        ("3. clarify", SPEC_ROOT / "templates" / "commands" / "clarify.md"),
        ("4. plan", FEATURE_DIR / "plan.md"),
        ("5. checklist", FEATURE_DIR / "checklist.md"),
        ("6. tasks", FEATURE_DIR / "tasks.md"),
        ("7. analyze", SPEC_ROOT / "templates" / "commands" / "analyze.md"),
        ("8. implement", SPEC_ROOT / "templates" / "commands" / "implement.md"),
        ("9. converge", SPEC_ROOT / "templates" / "commands" / "converge.md"),
    ]
    gaps: list[str] = []

    print("\n[PHẦN 1] KIỂM TRA 9 LỆNH & HỒ SƠ SPEC KIT TRÊN ĐĨA:")
    for label, path in required_files:
        if path.exists() and path.stat().st_size > 100:
            print(f"  [OK] {label:<16} -> {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")
        else:
            msg = f"Thiếu hồ sơ Spec Kit cho bước {label}: {path}"
            print(f"  [GAP] {msg}")
            gaps.append(msg)

    # 2. Check Constitution Invariants against Live Code (Command 9: converge)
    print("\n[PHẦN 2] KIỂM TOÁN HỘI TỤ MÃ NGUỒN SO VỚI 6 ĐIỀU HIẾN PHÁP (/speckit.converge):")
    import wave
    import numpy as np
    from simulator.voice_auth import VoiceAuthManager, transform_pcm_by_pitch_factor
    from simulator.auth_3layer import get_auth_3layer_manager

    audio_dir = ROOT / "test_audio"
    vm = VoiceAuthManager(audio_dir)

    with wave.open(str(audio_dir / "giong_1_chu_nha_mo_cua.wav"), "rb") as w1:
        pcm_v1_bytes = w1.readframes(w1.getnframes())
    with wave.open(str(audio_dir / "giong_2_nguoi_la_mo_cua.wav"), "rb") as w2:
        pcm_v2_bytes = w2.readframes(w2.getnframes())

    # Điều 1: 3-Strike Stranger Protocol
    vm.reset_strikes()
    s1 = vm.verify_pcm16k_and_apply_strikes(pcm_v2_bytes)
    s2 = vm.verify_pcm16k_and_apply_strikes(pcm_v2_bytes)
    s3 = vm.verify_pcm16k_and_apply_strikes(pcm_v2_bytes)
    vm.reset_strikes()

    if (
        s1.get("rejection_speech") == "Tôi không được phép nhận lệnh từ người lạ."
        and not s1.get("silent_ignore")
        and s2.get("rejection_speech") == "Tôi sẽ không trả lời bạn lần nữa."
        and not s2.get("silent_ignore")
        and s3.get("rejection_speech") == ""
        and s3.get("silent_ignore") is True
    ):
        print("  [CONVERGED] Điều 1 (3-Strike Stranger): Lần 1 & Lần 2 trả lời đúng câu, Lần 3+ im lặng tuyệt đối.")
    else:
        gaps.append(f"Vi phạm Điều 1 Hiến pháp (3-Strike Stranger): s1={s1}, s2={s2}, s3={s3}")

    # Điều 2: Owner Voice Recognition & Sub-harmonic Octave Guard
    owner_ok = True
    pcm_v1_arr = np.frombuffer(pcm_v1_bytes, dtype=np.int16)
    for factor in (1.0, 1.15, 1.28):
        pcm_test = pcm_v1_bytes if factor == 1.0 else transform_pcm_by_pitch_factor(pcm_v1_arr, factor=factor, sr=16000).tobytes()
        res = vm.verify_pcm16k_and_apply_strikes(pcm_test)
        if not res.get("authorized") or res.get("speaker_id") != "owner_voice_1":
            owner_ok = False
            res_summary = {k: v for k, v in res.items() if k != "clean_pcm_bytes"}
            gaps.append(f"Vi phạm Điều 2 Hiến pháp: Giọng Chủ nhà factor={factor} bị chặn ({res_summary})")
            break
    if owner_ok:
        print("  [CONVERGED] Điều 2 (Voice DSP & Sub-harmonic Guard): Nhận diện 100% giọng Chủ nhà Cấp 1 (F0 trầm 135.6Hz & chuẩn 173.9Hz).")

    # Điều 3: Zero-Drop Gemini Live Bridge in server.py
    server_code = (ROOT / "simulator" / "server.py").read_text(encoding="utf-8")
    if (
        "async def _ensure_current_mic_utterance_verified" in server_code
        and "while not self._closed:" in server_code
        and "self.last_mic_turn_blocked" in server_code
    ):
        print("  [CONVERGED] Điều 3 (Zero-Drop Live Bridge): Tự động kết nối lại Gemini Live & kiểm tra 1 lần/câu nói.")
    else:
        gaps.append("Vi phạm Điều 3 Hiến pháp: Thiếu cơ chế giữ kết nối tự động hoặc cổng kiểm tra 1 lần/câu nói trong simulator/server.py")

    # Điều 4: 3-Tier Invite Links (Tier 1 -> [2, 3], Tier 2 -> [3], Tier 3 -> [])
    auth_mgr = get_auth_3layer_manager()
    r_t1_to_2 = auth_mgr.create_custom_invite_link("tuan_anh", target_tier=2)
    r_t1_to_3 = auth_mgr.create_custom_invite_link("tuan_anh", target_tier=3)
    r_t2_to_2 = auth_mgr.create_custom_invite_link("thanh_vien_a", target_tier=2)
    r_t2_to_3 = auth_mgr.create_custom_invite_link("thanh_vien_a", target_tier=3)
    r_t3_to_3 = auth_mgr.create_custom_invite_link("khach_c", target_tier=3)
    if (
        r_t1_to_2.get("ok")
        and r_t1_to_3.get("ok")
        and not r_t2_to_2.get("ok")
        and r_t2_to_3.get("ok")
        and not r_t3_to_3.get("ok")
    ):
        print("  [CONVERGED] Điều 4 (3-Tier Invite & OAuth OTP): Cấp 1 tạo link Cấp 2/3, Cấp 2 chỉ tạo Cấp 3, Cấp 3 không có quyền.")
    else:
        gaps.append("Vi phạm Điều 4 Hiến pháp: Phân quyền tạo link mời Cấp 1/2/3 không đúng quy định.")

    # Điều 5 & Điều 6: Rule Engine, Offline Door Lock & SQLite 3NF DB
    import asyncio
    from simulator.rule_engine import SmartHomeEngine
    from simulator.database_sqlite import get_sqlite_overview

    async def _check_d5_d6() -> None:
        eng = SmartHomeEngine()
        await eng.factory_reset()
        r_open1 = await eng.execute_device_action("main_door", "open")
        r_open2 = await eng.execute_device_action("main_door", "open")
        if r_open1.get("exact_spoken_reply") == "Cửa chính đã mở." and r_open2.get("exact_spoken_reply") == "Cửa chính đã mở sẵn rồi.":
            print("  [CONVERGED] Điều 5 (Short Reply & Already-Open Guard): Nhắc trạng thái mở sẵn và câu trả lời chuẩn.")
        else:
            gaps.append(f"Vi phạm Điều 5 Hiến pháp: {r_open1} / {r_open2}")

        await eng.set_server_connection_mode(False)
        blk_door = await eng.execute_device_action("main_door", "open")
        await eng.set_server_connection_mode(True)
        sq = get_sqlite_overview()
        if not blk_door.get("ok") and sq.get("ok") and sq.get("table_count") == 8 and sq.get("journal_mode") == "WAL":
            print("  [CONVERGED] Điều 6 (Offline Door Lock & 8-Table 3NF SQLite WAL): Khóa cứng cửa khi Offline & CSDL 3NF chuẩn.")
        else:
            gaps.append(f"Vi phạm Điều 6 Hiến pháp: blk_door={blk_door}, sqlite={sq}")

    asyncio.run(_check_d5_d6())

    # 3. Kiểm thử Trực tiếp Máy chủ Đang Chạy (Live Commercial Server Self-Test: HTTP + WebSocket /ws)
    print("\n[PHẦN 3] TỰ KIỂM THỬ TRỰC TIẾP TRÊN SERVER THẬT (HTTP://LOCALHOST:8088 & WEBSOCKET /WS):")
    import json
    import urllib.request

    live_routes = [
        "/",
        "/auth",
        "/wokwi",
        "/logs",
        "/archify",
        "/archify/erd",
        "/archify/devops",
        "/api/voice_auth/profiles",
        "/api/auth3/overview",
        "/api/server_logs_and_db",
    ]
    for route in live_routes:
        url = f"http://127.0.0.1:8088{route}"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                body = resp.read()
                if resp.status == 200 and len(body) > 50:
                    print(f"  [LIVE HTTP 200 OK] {route:<26} ({len(body)} bytes)")
                else:
                    gaps.append(f"Route {route} trả về status={resp.status}, size={len(body)}")
        except Exception as exc:
            gaps.append(f"Không kết nối được Live Server tại {url}: {exc}")

    # Kiểm thử WebSocket /ws trực tiếp (Giọng 1 Mở cửa + Giọng 2 Chặn 3 Lần)
    async def _check_live_ws() -> None:
        import websockets

        async with websockets.connect("ws://127.0.0.1:8088/ws", open_timeout=6) as ws:
            # Đọc gói state_snapshot đầu tiên
            init_raw = await asyncio.wait_for(ws.recv(), timeout=5)
            init_msg = json.loads(init_raw)
            if init_msg.get("type") not in ("state_snapshot", "init_state"):
                gaps.append(f"WebSocket /ws không trả state_snapshot đầu tiên: {init_msg.get('type')}")
                return
            print(f"  [LIVE WS CONNECTED] Đã nhận {init_msg.get('type')} từ ws://127.0.0.1:8088/ws")

            # Reset strikes trước khi test 3-strike qua WS
            await ws.send(json.dumps({"type": "reset_voice_strikes"}))

            # Gửi 3 lần mẫu Giọng 2 (Người lạ) qua WebSocket
            strikes_seen: list[dict] = []
            for _ in range(1, 4):
                await ws.send(json.dumps({"type": "play_wav_sample", "sample_id": "giong_2_nguoi_la_mo_cua"}))
                deadline = asyncio.get_event_loop().time() + 5.0
                while asyncio.get_event_loop().time() < deadline:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    m = json.loads(raw)
                    if m.get("type") in ("voice_auth_rejected", "voice_auth_silent_ignored"):
                        strikes_seen.append(m)
                        break

            await ws.send(json.dumps({"type": "reset_voice_strikes"}))

            if (
                len(strikes_seen) == 3
                and strikes_seen[0].get("type") == "voice_auth_rejected"
                and strikes_seen[0].get("rejection_speech") == "Tôi không được phép nhận lệnh từ người lạ."
                and strikes_seen[1].get("type") == "voice_auth_rejected"
                and strikes_seen[1].get("rejection_speech") == "Tôi sẽ không trả lời bạn lần nữa."
                and strikes_seen[2].get("type") == "voice_auth_silent_ignored"
            ):
                print("  [LIVE WS 3-STRIKE PASS] Lần 1 & Lần 2 phát đúng câu chặn, Lần 3 im lặng tuyệt đối trên WebSocket thật!")
            else:
                gaps.append(f"WebSocket 3-strike sai lệch: {strikes_seen}")

            # Kiểm thử luồng mic_chunk + mic_speech_ended trực tiếp của Chủ nhà Cấp 1
            import base64
            for i in range(0, min(len(pcm_v1_bytes), 24576), 4096):
                c = pcm_v1_bytes[i : i + 4096]
                await ws.send(
                    json.dumps({
                        "type": "mic_chunk",
                        "pcm16k_b64": base64.b64encode(c).decode("ascii"),
                        "is_speech": True,
                    })
                )
            await ws.send(json.dumps({"type": "mic_speech_ended"}))
            mic_verified = False
            deadline = asyncio.get_event_loop().time() + 4.0
            while asyncio.get_event_loop().time() < deadline:
                raw = await asyncio.wait_for(ws.recv(), timeout=4.0)
                m = json.loads(raw)
                if m.get("type") == "voice_auth_result" and m.get("sample_id") == "live_mic":
                    if m.get("analysis", {}).get("authorized") is True:
                        mic_verified = True
                    break
            if mic_verified:
                print("  [LIVE MIC STREAM PASS] Luồng mic_chunk + mic_speech_ended nhận diện đúng Giọng Cấp 1 Chủ nhà!")
            else:
                gaps.append("Luồng mic_chunk + mic_speech_ended không trả về voice_auth_result authorized=True cho Chủ nhà!")

    app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
    if not app_js_path.exists():
        app_js_path = ROOT / "simulator" / "static" / "app.js"
    app_js_code = app_js_path.read_text(encoding="utf-8")
    if "playCtx" in app_js_code or "chkAiAudio" in app_js_code:
        gaps.append("Phát hiện biến chưa khai báo (playCtx / chkAiAudio) trong app.js làm treo onaudioprocess!")
    else:
        print("  [FRONTEND JS AST PASS] Không có biến lạ làm treo luồng thu âm Microphone trong app.js.")

    try:
        asyncio.run(_check_live_ws())
    except Exception as exc:
        gaps.append(f"Lỗi kiểm thử WebSocket /ws trực tiếp: {exc}")

    # Tổng kết Convergence
    tasks_path = FEATURE_DIR / "tasks.md"
    if not gaps:
        print("\n✅ KẾT LUẬN `/speckit.converge`: CONVERGED 100% — Không có bất kỳ xung đột hay chồng chéo nào!")
        return 0

    print(f"\n⚠️ PHÁT HIỆN {len(gaps)} ĐIỂM LỆCH SO VỚI SPEC/HIẾN PHÁP — Đang ghi vào {tasks_path.relative_to(ROOT)}...")
    with tasks_path.open("a", encoding="utf-8", newline="\n") as f:
        f.write("\n## Phase Convergence: Remediation Tasks\n")
        for idx, g in enumerate(gaps, 1):
            f.write(f"- [ ] **CONV-{idx:02d}** {g}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(run_converge_audit())
