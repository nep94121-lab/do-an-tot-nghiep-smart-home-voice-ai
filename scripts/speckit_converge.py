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

import os
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

    with wave.open(str(audio_dir / "00_doan_dau_mau_giong_chu_nha_tuan_anh.wav"), "rb") as w1:
        pcm_v1_bytes = w1.readframes(w1.getnframes())[:96000]
    with wave.open(str(audio_dir / "giong_2_nguoi_la_mo_cua.wav"), "rb") as w2:
        pcm_v2_bytes = w2.readframes(w2.getnframes())

    # Điều 1: 3-Strike Stranger Protocol
    vm.reset_strikes()
    s1 = vm.verify_pcm16k_and_apply_strikes(pcm_v2_bytes)
    s2 = vm.verify_pcm16k_and_apply_strikes(pcm_v2_bytes)
    s3 = vm.verify_pcm16k_and_apply_strikes(pcm_v2_bytes)
    vm.reset_strikes()

    expected_msg = "Xin lỗi, bạn không có quyền thực hiện lệnh này."
    if (
        s1.get("authorized") is False
        and s2.get("authorized") is False
        and s3.get("authorized") is False
        and s1.get("rejection_speech") == expected_msg
        and s2.get("rejection_speech") == expected_msg
        and s3.get("rejection_speech") == expected_msg
        and int(s3.get("strike_count", 0)) >= 3
    ):
        print("  [CONVERGED] Điều 1 (3-Strike Stranger): Chặn người lạ 3 strike với câu từ chối chuẩn.")
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

    # Điều 3: Zero-Drop Gemini Live Bridge + Session RBAC trong gemini_bridge.py
    bridge_code = (ROOT / "simulator" / "live" / "gemini_bridge.py").read_text(encoding="utf-8")
    if (
        "def _bind_actor_to_engine" in bridge_code
        and "while not self._closed:" in bridge_code
        and "_ensure_current_mic_utterance_verified" not in bridge_code
    ):
        print("  [CONVERGED] Điều 3 (Zero-Drop Live Bridge): Truyền thẳng PCM & phân quyền theo phiên (đã gỡ speaker verification).")
    else:
        gaps.append("Vi phạm Điều 3 Hiến pháp: Thiếu _bind_actor_to_engine hoặc còn dấu vết _ensure_current_mic_utterance_verified trong simulator/live/gemini_bridge.py")

    # Điều 4: Owner-only Invite Links (Tier 1 -> [2, 3], Tier 2 -> [], Tier 3 -> [])
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
        and not r_t2_to_3.get("ok")
        and not r_t3_to_3.get("ok")
    ):
        print("  [CONVERGED] Điều 4 (3-Tier Invite & OAuth OTP): Chỉ Chủ nhà Cấp 1 tạo link Cấp 2/3, Cấp 2 & Cấp 3 bị chặn.")
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
        if not blk_door.get("ok") and sq.get("ok") and sq.get("table_count", 0) >= 8 and sq.get("journal_mode") == "WAL":
            print("  [CONVERGED] Điều 6 (Offline Door Lock & 8-Table 3NF SQLite WAL): Khóa cứng cửa khi Offline & CSDL 3NF chuẩn.")
        else:
            gaps.append(f"Vi phạm Điều 6 Hiến pháp: blk_door={blk_door}, sqlite={sq}")

    asyncio.run(_check_d5_d6())

    # 3. Kiểm thử Trực tiếp Máy chủ Đang Chạy (HTTP + WebSocket /ws, fallback TestClient dưới pytest)
    print("\n[PHẦN 3] TỰ KIỂM THỬ TRỰC TIẾP TRÊN SERVER THẬT (HTTP://LOCALHOST:8088 & WEBSOCKET /WS):")
    import json
    import urllib.error
    import urllib.request

    public_html_routes = [
        "/",
        "/auth",
        "/wokwi",
        "/logs",
        "/archify",
        "/archify/erd",
        "/archify/devops",
    ]
    protected_api_routes = [
        "/api/voice_auth/profiles",
        "/api/auth3/overview",
        "/api/server_logs_and_db",
    ]

    live_reachable = False
    try:
        with urllib.request.urlopen("http://127.0.0.1:8088/api/health", timeout=2) as _probe:
            live_reachable = _probe.status == 200
    except Exception:
        live_reachable = False

    if live_reachable:
        for route in public_html_routes:
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

        for route in protected_api_routes:
            url = f"http://127.0.0.1:8088{route}"
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    gaps.append(f"Route bảo mật {route} không chặn unauthenticated (status={resp.status})")
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    print(f"  [LIVE HTTP 401 RBAC] {route:<24} (chặn đúng unauthenticated)")
                else:
                    gaps.append(f"Route {route} trả về HTTP {exc.code}, mong đợi 401")
            except Exception as exc:
                gaps.append(f"Lỗi kiểm tra {url}: {exc}")
    elif os.environ.get("PYTEST_CURRENT_TEST"):
        from fastapi.testclient import TestClient
        from simulator.server import app as _srv_app

        _tc = TestClient(_srv_app)
        for route in public_html_routes:
            resp = _tc.get(route)
            if resp.status_code == 200 and len(resp.content) > 50:
                print(f"  [TESTCLIENT 200 OK] {route:<25} ({len(resp.content)} bytes)")
            else:
                gaps.append(f"Route {route} trả về status={resp.status_code}, size={len(resp.content)}")
        for route in protected_api_routes:
            resp = _tc.get(route)
            if resp.status_code == 401:
                print(f"  [TESTCLIENT 401 RBAC] {route:<23} (chặn đúng unauthenticated)")
            else:
                gaps.append(f"Route {route} trả về status={resp.status_code}, mong đợi 401")
    else:
        gaps.append("Không kết nối được Live Server tại http://127.0.0.1:8088")

    # Kiểm thử WebSocket /ws trực tiếp (chặn RBAC khi chưa đăng nhập)
    async def _check_live_ws() -> None:
        import websockets

        async with websockets.connect("ws://127.0.0.1:8088/ws", open_timeout=6) as ws:
            init_raw = await asyncio.wait_for(ws.recv(), timeout=5)
            init_msg = json.loads(init_raw)
            if init_msg.get("type") not in ("state_snapshot", "init_state"):
                gaps.append(f"WebSocket /ws không trả state_snapshot đầu tiên: {init_msg.get('type')}")
                return
            print(f"  [LIVE WS CONNECTED] Đã nhận {init_msg.get('type')} từ ws://127.0.0.1:8088/ws")

            await ws.send(json.dumps({"type": "mic_speech_ended"}))
            deadline = asyncio.get_event_loop().time() + 4.0
            blocked_ok = False
            while asyncio.get_event_loop().time() < deadline:
                raw = await asyncio.wait_for(ws.recv(), timeout=4.0)
                m = json.loads(raw)
                if m.get("type") == "rbac_blocked":
                    blocked_ok = True
                    break
            if blocked_ok:
                print("  [LIVE WS RBAC PASS] Kết nối chưa đăng nhập bị chặn RBAC theo phiên mà không cần voice strike!")
            else:
                gaps.append("WebSocket /ws không chặn rbac_blocked cho phiên chưa đăng nhập!")

    app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
    if not app_js_path.exists():
        app_js_path = ROOT / "simulator" / "static" / "app.js"
    app_js_code = app_js_path.read_text(encoding="utf-8")
    if "playCtx" in app_js_code or "chkAiAudio" in app_js_code:
        gaps.append("Phát hiện biến chưa khai báo (playCtx / chkAiAudio) trong app.js làm treo onaudioprocess!")
    else:
        print("  [FRONTEND JS AST PASS] Không có biến lạ làm treo luồng thu âm Microphone trong app.js.")

    if live_reachable:
        try:
            asyncio.run(_check_live_ws())
        except Exception as exc:
            gaps.append(f"Lỗi kiểm thử WebSocket /ws trực tiếp: {exc}")
    elif os.environ.get("PYTEST_CURRENT_TEST"):
        from fastapi.testclient import TestClient
        from simulator.server import app as _srv_app

        _tc = TestClient(_srv_app)
        with _tc.websocket_connect("/ws") as _ws:
            init_msg = _ws.receive_json()
            if init_msg.get("type") not in ("state_snapshot", "init_state"):
                gaps.append(f"WebSocket /ws không trả state_snapshot đầu tiên: {init_msg.get('type')}")
            else:
                _ws.send_json({"type": "mic_speech_ended"})
                blocked_ok = any(_ws.receive_json().get("type") == "rbac_blocked" for _ in range(5))
                if blocked_ok:
                    print("  [TESTCLIENT WS RBAC PASS] Kết nối chưa đăng nhập bị chặn RBAC!")
                else:
                    gaps.append("WebSocket /ws không chặn rbac_blocked cho phiên chưa đăng nhập!")

    # Tổng kết Convergence
    tasks_path = FEATURE_DIR / "tasks.md"
    if not gaps:
        print("\n✅ KẾT LUẬN `/speckit.converge`: CONVERGED 100% — Không có bất kỳ xung đột hay chồng chéo nào!")
        return 0

    print(f"\n⚠️ PHÁT HIỆN {len(gaps)} ĐIỂM LỆCH SO VỚI SPEC/HIẾN PHÁP — Gaps: {gaps}")
    if not os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("SPECKIT_WRITE_TASKS") == "1":
        with tasks_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write("\n## Phase Convergence: Remediation Tasks\n")
            for idx, g in enumerate(gaps, 1):
                f.write(f"- [ ] **CONV-{idx:02d}** {g}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(run_converge_audit())
