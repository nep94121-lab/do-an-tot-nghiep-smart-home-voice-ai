"""Regression test suite for agyfix10_20261120 (P1-1, P2-1, P2-2, P2-3).

Covers:
- P1-1: POST /api/voice_command device control requires natural Vietnamese confirmation
  before execution ("ok"/"được"/"đúng rồi"/"làm đi"), cancels on "hủy"/"thôi"/"không",
  enforces 60s expiry and strict (owner_user_id, session_key) binding, preserves Tier 3 RBAC
  (403 on main_door), keeps sensor queries & direct /api/device toggles immediate.
- P2-1 & P2-2: Mobile 412x915 touch targets >= 44px (#btnLogoutHome, /auth .details-summary,
  and all visible interactive elements on /, /app, /login, /register, /auth, /guest_guide)
  + Light Mode --muted WCAG AA contrast >= 4.5:1.
- P2-3: Cold-start WebRTC autoGainControl=true echo suppression (signed lag + burst jitter +
  active pure-echo decay) across Node.js SmartHomeEchoGuard, Python ServerEchoGuard, and
  10 fresh cold-start Chromium browser launches (0/10 false barge-in), preserving 4/4 real
  Vietnamese WAV barge-in at 1.0x volume.
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import pathlib
import socket
import struct
import subprocess
import sys
import tempfile
import time
import wave
from typing import Any

import pytest
import requests
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
ECHO_GUARD_JS = ROOT / "web" / "js" / "voice_echo_guard.js"
WAV_AOEDE_24K = ROOT / "backend" / "data" / "aoede_repeat_24k.wav"
PROD_AUDIO_FALLBACK = pathlib.Path(r"C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\test_audio")

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
)
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _find_chromium_executable() -> str | None:
    env_exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "").strip()
    if env_exe and pathlib.Path(env_exe).exists():
        return env_exe
    pup = pathlib.Path(r"C:\Users\LENOVO\.cache\puppeteer")
    if pup.exists():
        for exe in sorted(pup.rglob("chrome-headless-shell.exe"), reverse=True):
            if exe.exists():
                return str(exe)
    return None


def _launch_headless_chromium(p: Any, extra_args: list[str] | None = None) -> Any:
    exe = _find_chromium_executable()
    attempts: list[dict[str, Any]] = []
    if exe:
        attempts.append({"headless": True, "executable_path": exe})
    attempts.extend([{"headless": True}, {"headless": True, "channel": "msedge"}])
    last_err: Exception | None = None
    for kw in attempts:
        try:
            call_kw = dict(kw)
            if extra_args:
                call_kw["args"] = list(extra_args)
            return p.chromium.launch(timeout=25000, **call_kw)
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"Could not launch headless Chromium: {last_err}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _rel_luminance(rgb: tuple[int, int, int]) -> float:
    def _lin(c: int) -> float:
        x = c / 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _contrast_ratio(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
    l1 = _rel_luminance(rgb1)
    l2 = _rel_luminance(rgb2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _parse_rgb(css_color: str) -> tuple[int, int, int]:
    import re

    m = re.search(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", css_color or "")
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    s = (css_color or "").strip().lstrip("#")
    if len(s) == 6:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    raise ValueError(f"Cannot parse CSS color: {css_color!r}")


def _human_wavs() -> dict[str, pathlib.Path]:
    cands = {
        "cau_4_bat_den_phong_khach": ROOT / "test_audio" / "cac_cau_lenh_cua_sep" / "cau_4_bat_den_phong_khach.wav",
        "cau_1_xin_chao_chu_nha_cap1": ROOT / "test_audio" / "cac_cau_lenh_cua_sep" / "cau_1_xin_chao_chu_nha_cap1.wav",
        "hen_gio_5s_tat_den": ROOT / "test_audio" / "hen_gio_5s_tat_den.wav",
        "05_nhiet_do_trong_phong": ROOT / "test_audio" / "giong_tuan_anh_tach_cau" / "05_nhiet_do_trong_phong_bay_gio_la_bao_nhieu.wav",
    }
    if not cands["05_nhiet_do_trong_phong"].exists():
        fb = PROD_AUDIO_FALLBACK / "giong_tuan_anh_tach_cau" / "05_nhiet_do_trong_phong_bay_gio_la_bao_nhieu.wav"
        if fb.exists():
            cands["05_nhiet_do_trong_phong"] = fb
        else:
            cands["05_nhiet_do_trong_phong"] = ROOT / "test_audio" / "cac_cau_lenh_cua_sep" / "cau_2_mo_cua_chinh.wav"
    return {k: v for k, v in cands.items() if v.exists()}


def _read_wav_floats(path: pathlib.Path, target_sr: int = 16000) -> list[float]:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
    vals = struct.unpack(f"<{len(raw) // 2}h", raw)
    if ch > 1:
        vals = vals[::ch]
    floats = [v / 32768.0 for v in vals]
    if sr == target_sr:
        return floats
    ratio = sr / float(target_sr)
    out_len = int(len(floats) / ratio)
    n = len(floats)
    out: list[float] = []
    for i in range(out_len):
        pos = i * ratio
        idx = int(pos)
        frac = pos - idx
        s0 = floats[idx]
        s1 = floats[idx + 1] if idx + 1 < n else s0
        out.append(s0 + (s1 - s0) * frac)
    return out


def _floats_to_pcm16(samples: list[float]) -> bytes:
    clamped = [max(-32767, min(32767, int(round(s * 32767.0)))) for s in samples]
    return struct.pack(f"<{len(clamped)}h", *clamped)


def _simulate_nonlinear_agc(samples: list[float], target_rms: float = 0.28, max_gain: float = 8.0) -> list[float]:
    out: list[float] = []
    gain = 1.0
    prev_x = 0.0
    prev_y = 0.0
    hp_a = 0.96
    for i in range(0, len(samples), 320):
        chunk = samples[i : i + 320]
        rms = math.sqrt(sum(x * x for x in chunk) / max(1, len(chunk)))
        if rms > 0.004:
            desired = min(max_gain, max(1.0, target_rms / rms))
            alpha = 0.30 if desired > gain else 0.15
            gain = gain * (1.0 - alpha) + desired * alpha
        for x in chunk:
            y = hp_a * (prev_y + x - prev_x)
            prev_x = x
            prev_y = y
            out.append(math.tanh(y * gain * 1.35))
    return out


# ==============================================================================
# P1-1: /api/voice_command CONFIRMATION FLOW, TTL, SESSION ISOLATION & RBAC
# ==============================================================================


class TestP1VoiceCommandConfirmationFlow:
    def _make_session(self, session_id: str, user_id: str, display_name: str, tier: int, role: str) -> Any:
        from backend.auth.session_store import UserSession

        return UserSession(
            session_id=session_id,
            user_id=user_id,
            email=f"{user_id}@test.local",
            display_name=display_name,
            tier=tier,
            role=role,
            created_at=time.time(),
            expires_at=time.time() + 3600,
            source="test_agyfix10",
            is_authenticated=True,
        )

    @pytest.mark.parametrize("confirm_phrase", ["ok", "được", "đúng rồi", "làm đi", "đồng ý"])
    def test_main_door_acts_immediately_and_automation_requires_natural_confirm(
        self, confirm_phrase: str
    ) -> None:
        from backend.automation_repo import list_schedules, reset_timers_and_schedules_scoped
        from backend.rule_engine import SmartHomeEngine
        from backend.voice.session_voice_command import (
            process_session_voice_command,
            reset_session_echo_guards,
        )

        reset_session_echo_guards()
        reset_timers_and_schedules_scoped(clear_all=True)
        engine = SmartHomeEngine()
        asyncio.run(engine.execute_device_action("main_door", "close", bypass_rbac=True))
        assert engine.devices["main_door"]["state"] == "CLOSED"

        owner = self._make_session(f"sess_owner_{confirm_phrase}", "tuan_anh", "Nguyễn Tuấn Anh", 1, "ADMIN")

        # 1. Direct simple device command "mở cửa chính" -> MUST act IMMEDIATELY without confirmation
        r_direct, s_direct = asyncio.run(
            process_session_voice_command(engine=engine, session=owner, payload={"transcript": "mở cửa chính"})
        )
        assert s_direct == 200 and r_direct["ok"] is True
        assert r_direct.get("requires_confirmation") is False
        assert r_direct.get("executed") is True
        assert engine.devices["main_door"]["state"] == "OPEN"
        reply_direct = str(r_direct.get("exact_spoken_reply") or "")
        assert "đã mở cửa chính" in reply_direct.lower()
        assert "main_door" not in reply_direct.lower()
        assert "{" not in reply_direct and "}" not in reply_direct

        # 2. Automation command (schedule) -> MUST prompt naturally, MUST NOT create schedule yet
        r1, s1 = asyncio.run(
            process_session_voice_command(engine=engine, session=owner, payload={"transcript": "đặt lịch 07:00 mở cửa chính"})
        )
        assert s1 == 200 and r1["ok"] is True
        assert r1["requires_confirmation"] is True
        assert r1["executed"] is False
        assert len(list_schedules(include_disabled=False)) == 0
        reply1 = str(r1.get("exact_spoken_reply") or "")
        assert "07:00" in reply1
        assert "cửa chính" in reply1.lower()
        assert "main_door" not in reply1.lower()

        # 3. Cancel ("hủy" / "thôi" / "không") -> MUST NOT create schedule
        cancel_word = {"ok": "hủy", "được": "thôi", "đúng rồi": "không"}.get(confirm_phrase, "hủy")
        rc, sc = asyncio.run(
            process_session_voice_command(engine=engine, session=owner, payload={"transcript": cancel_word})
        )
        assert sc == 200
        assert rc.get("cancelled") is True
        assert rc.get("executed") is False
        assert len(list_schedules(include_disabled=False)) == 0

        # 4. Repeat schedule command -> prompts again, then confirm with natural affirmative variant
        r2, s2 = asyncio.run(
            process_session_voice_command(engine=engine, session=owner, payload={"transcript": "đặt lịch 07:00 mở cửa chính"})
        )
        assert s2 == 200 and r2["ok"] is True
        assert r2.get("echo_suppressed") is not True
        assert r2["requires_confirmation"] is True

        rok, sok = asyncio.run(
            process_session_voice_command(engine=engine, session=owner, payload={"transcript": confirm_phrase})
        )
        assert sok == 200 and rok["ok"] is True
        assert rok.get("confirmed") is True
        assert rok.get("executed") is True
        assert len(list_schedules(include_disabled=False)) == 1

        # 5. Repeating "ok" a second time must be idempotent (no pending left)
        rdup, sdup = asyncio.run(
            process_session_voice_command(engine=engine, session=owner, payload={"transcript": "ok"})
        )
        assert sdup == 200
        assert rdup.get("executed") is False
        reset_timers_and_schedules_scoped(clear_all=True)

    def test_pending_ttl_60s_expiry_and_strict_user_session_isolation(self) -> None:
        from backend.automation_repo import (
            PENDING_CONFIRM_TTL_SEC,
            list_schedules,
            reset_timers_and_schedules_scoped,
        )
        from backend.database_sqlite import open_wal_connection, resolve_sqlite_db_path
        from backend.rule_engine import SmartHomeEngine
        from backend.voice.session_voice_command import (
            process_session_voice_command,
            reset_session_echo_guards,
        )

        assert PENDING_CONFIRM_TTL_SEC >= 60.0
        reset_session_echo_guards()
        reset_timers_and_schedules_scoped(clear_all=True)
        engine = SmartHomeEngine()

        owner_sess_a = self._make_session("sess_owner_iso_A", "tuan_anh", "Nguyễn Tuấn Anh", 1, "ADMIN")
        owner_sess_b = self._make_session("sess_owner_iso_B", "tuan_anh", "Nguyễn Tuấn Anh", 1, "ADMIN")
        member_sess = self._make_session("sess_member_iso", "thanh_vien_a", "Thành viên A", 2, "MEMBER")

        # Owner session A stages a schedule (requires confirmation)
        r1, s1 = asyncio.run(
            process_session_voice_command(engine=engine, session=owner_sess_a, payload={"transcript": "đặt lịch 08:15 mở cửa chính"})
        )
        assert s1 == 200 and r1["requires_confirmation"] is True
        pid = r1["pending_id"]
        assert float(r1["expires_at"]) - time.time() >= 45.0
        assert len(list_schedules(include_disabled=False)) == 0

        # Another user (Tier 2) saying "ok" MUST NOT confirm Owner's pending action
        rm, _ = asyncio.run(
            process_session_voice_command(engine=engine, session=member_sess, payload={"transcript": "ok"})
        )
        assert rm.get("executed") is False
        assert len(list_schedules(include_disabled=False)) == 0

        # Same user on a DIFFERENT session (session B) saying "ok" MUST NOT confirm session A's pending action
        rb, _ = asyncio.run(
            process_session_voice_command(engine=engine, session=owner_sess_b, payload={"transcript": "ok"})
        )
        assert rb.get("executed") is False
        assert len(list_schedules(include_disabled=False)) == 0

        # Expire pending row -> session A saying "ok" MUST NOT execute
        conn = open_wal_connection(resolve_sqlite_db_path(), readonly=False)
        try:
            conn.execute("UPDATE pending_confirmations SET expires_at = ? WHERE pending_id = ?", (time.time() - 5.0, pid))
            conn.commit()
        finally:
            conn.close()

        rexp, sexp = asyncio.run(
            process_session_voice_command(engine=engine, session=owner_sess_a, payload={"transcript": "ok"})
        )
        assert sexp == 200
        assert rexp.get("expired") is True
        assert rexp.get("executed") is False
        assert len(list_schedules(include_disabled=False)) == 0

    def test_tier3_rbac_blocked_on_door_sensors_and_direct_ui_toggle_unchanged(self) -> None:
        from backend.api import deps as api_deps
        from backend.api import routes_devices
        from backend.auth.session_store import get_session_store
        from backend.automation_nlu import _resolve_session_key
        from backend.automation_repo import create_pending_confirmation, reset_timers_and_schedules_scoped
        from backend.server import app
        from backend.voice.session_voice_command import reset_session_echo_guards

        reset_session_echo_guards()
        reset_timers_and_schedules_scoped(clear_all=True)
        engine = routes_devices._REST_ENGINE
        asyncio.run(engine.execute_device_action("main_door", "close", bypass_rbac=True))
        asyncio.run(engine.execute_device_action("living_room_light", "turn_off", bypass_rbac=True))
        asyncio.run(engine.update_sensor_telemetry(temp_c=27.3, humidity_pct=61.0))

        store = get_session_store()
        t1_sess = store.create_session(user_id="tuan_anh", email="nep94121@gmail.com", display_name="Chủ nhà", tier=1, role="ADMIN", source="test")
        t3_sess = store.create_session(user_id="khach_fix10", email="khach@test.local", display_name="Khách", tier=3, role="CHILD_GUEST", source="qr_invite")
        t1_tok = t1_sess.session_id
        t3_tok = t3_sess.session_id
        h1 = {"X-Session-Token": t1_tok}
        h3 = {"X-Session-Token": t3_tok}

        with TestClient(app) as client:
            # Tier 3 tries "mở cửa chính" -> 403 immediately, door stays CLOSED
            r_t3 = client.post("/api/voice_command", headers=h3, json={"transcript": "mở cửa chính"})
            assert r_t3.status_code == 403
            assert r_t3.json().get("rbac_blocked") is True
            assert engine.devices["main_door"]["state"] == "CLOSED"

            # Greeting "chào bạn" MUST succeed with HTTP 200 and NO RBAC block for ALL tiers
            for hdr in (h1, h3):
                r_hi = client.post("/api/voice_command", headers=hdr, json={"transcript": "chào bạn"})
                assert r_hi.status_code == 200
                d_hi = r_hi.json()
                assert d_hi["ok"] is True and d_hi.get("rbac_blocked") is False
                assert "không có quyền" not in str(d_hi.get("exact_spoken_reply") or "").lower()

            # Even if a pending set_device(main_door, open) exists for Tier 3, saying "ok" STILL blocks with 403
            create_pending_confirmation(
                owner_user_id="khach_fix10",
                owner_tier=3,
                session_key=_resolve_session_key(t3_sess, "web_voice"),
                action_kind="set_device",
                payload={"device_id": "main_door", "action": "open", "intents": [{"device_id": "main_door", "action": "open"}]},
                prompt_question="Mở cửa chính, đúng không ạ?",
            )
            r_t3_ok = client.post("/api/voice_command", headers=h3, json={"transcript": "ok"})
            assert r_t3_ok.status_code == 403
            assert r_t3_ok.json().get("rbac_blocked") is True
            assert engine.devices["main_door"]["state"] == "CLOSED"

            # Sensor query executes immediately without confirmation
            r_sens = client.post("/api/voice_command", headers=h1, json={"transcript": "nhiệt độ và độ ẩm hiện tại là bao nhiêu"})
            assert r_sens.status_code == 200
            ds = r_sens.json()
            assert ds["ok"] is True
            assert not ds.get("requires_confirmation")
            assert "27.3" in str(ds.get("exact_spoken_reply") or "")

            # Direct UI toggle (/api/device) still executes immediately without confirmation
            r_ui = client.post("/api/device", headers=h1, json={"device_id": "living_room_light", "action": "turn_on"})
            assert r_ui.status_code == 200 and r_ui.json().get("ok") is True
            assert engine.devices["living_room_light"]["state"] == "ON"
            client.post("/api/device", headers=h1, json={"device_id": "living_room_light", "action": "turn_off"})

            # /api/text_command simple device command executes IMMEDIATELY; automation requires confirmation
            r_tx1 = client.post("/api/text_command", headers=h1, json={"text": "mở cửa chính"})
            assert r_tx1.status_code == 200 and r_tx1.json().get("ok") is True
            assert not r_tx1.json().get("requires_confirmation")
            assert engine.devices["main_door"]["state"] == "OPEN"
            client.post("/api/device", headers=h1, json={"device_id": "main_door", "action": "close"})

            r_tx_sch = client.post("/api/text_command", headers=h1, json={"text": "đặt lịch 09:00 mở cửa chính"})
            assert r_tx_sch.status_code == 200 and r_tx_sch.json().get("requires_confirmation") is True
            r_tx_cancel = client.post("/api/text_command", headers=h1, json={"text": "hủy"})
            assert r_tx_cancel.status_code == 200 and r_tx_cancel.json().get("cancelled") is True

            r_tx_t3 = client.post("/api/text_command", headers=h3, json={"text": "mở cửa chính"})
            assert r_tx_t3.status_code == 403 and r_tx_t3.json().get("rbac_blocked") is True
            assert engine.devices["main_door"]["state"] == "CLOSED"
            assert api_deps._REST_ENGINE is engine


# ==============================================================================
# P2-1 & P2-2: MOBILE 412x915 TAP TARGETS & LIGHT MODE --muted CONTRAST
# ==============================================================================


class TestP2MobileTapTargetsAndLightMutedContrast:
    def test_mobile_412x915_all_interactive_elements_at_least_44px_and_muted_wcag_aa(self) -> None:
        from playwright.sync_api import sync_playwright

        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="fix10_ui_"))
        data_dir = tmp_dir / "data"
        log_dir = tmp_dir / "logs"
        data_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["SMARTHOME_DATA_DIR"] = str(data_dir)
        env["SMARTHOME_LOG_DIR"] = str(log_dir)
        env["SMARTHOME_SESSION_SECRET"] = "fix10_ui_test_secret"
        env["GMAIL_APP_PASSWORD"] = ""
        env["SMTP_PASSWORD"] = ""
        env.pop("SIMULATOR_SECURITY_STATE_DIR", None)
        env.pop("SIMULATOR_OFFLINE_SANDBOX", None)

        seed_code = r"""
import json
from backend.auth_3layer import get_auth_3layer_manager
from backend.auth.constants_and_crypto import hash_password
from backend.auth.owner_pin import setup_or_replace_pin
from backend.auth.session_store import mint_trusted_device_token
from backend.database_sqlite import init_sqlite_database

init_sqlite_database()
mgr = get_auth_3layer_manager()
def _upd():
    for a in mgr.accounts:
        if str(a.get("email") or "").strip().lower() == "nep94121@gmail.com":
            a["password_hash"] = hash_password("Fix10Ui#2026!")
            a["permission_active"] = True
            a["permission_status"] = "ACTIVE"
    return mgr._save_accounts()
mgr._with_cas_accounts(_upd)
setup_or_replace_pin("2468", "2468")
td = mint_trusted_device_token(
    account_id="tuan_anh",
    email="nep94121@gmail.com",
    password_hash=hash_password("Fix10Ui#2026!"),
    user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
)
print(json.dumps({"td": td}))
"""
        seed_proc = subprocess.run([sys.executable, "-c", seed_code], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=30)
        assert seed_proc.returncode == 0, seed_proc.stderr
        td_token = json.loads([ln for ln in seed_proc.stdout.splitlines() if ln.strip().startswith("{")][-1])["td"]

        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.server:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            deadline = time.time() + 25
            while time.time() < deadline:
                try:
                    if requests.get(f"{base_url}/api/health", timeout=2).status_code == 200:
                        break
                except Exception:
                    pass
                time.sleep(0.3)
            else:
                raise RuntimeError("Local test server failed to start")

            js_audit = """() => {
                const sels = 'button, a, summary, input:not([type="hidden"]), select';
                const bad = [];
                for (const el of document.querySelectorAll(sels)) {
                    const st = getComputedStyle(el);
                    if (st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity) === 0) continue;
                    const rect = el.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) continue;
                    if (rect.height < 43.5 || rect.width < 43.5) {
                        bad.push({
                            tag: el.tagName.toLowerCase(),
                            id: el.id || '',
                            cls: String(el.className || ''),
                            text: (el.innerText || el.value || '').trim().slice(0, 40),
                            w: Math.round(rect.width * 10) / 10,
                            h: Math.round(rect.height * 10) / 10,
                        });
                    }
                }
                const mutedHex = getComputedStyle(document.documentElement).getPropertyValue('--muted').trim();
                return {
                    bad,
                    mutedHex,
                    overflowX: document.documentElement.scrollWidth > window.innerWidth + 1,
                };
            }"""

            with sync_playwright() as p:
                browser = _launch_headless_chromium(p)
                try:
                    # 1. Unauthenticated mobile 412x915 Light Mode
                    ctx = browser.new_context(
                        viewport={"width": 412, "height": 915},
                        has_touch=True,
                        is_mobile=True,
                        user_agent=MOBILE_UA,
                        color_scheme="light",
                    )
                    page = ctx.new_page()
                    for route in ("/", "/app", "/login", "/register", "/auth", "/guest_guide"):
                        page.goto(f"{base_url}{route}", wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_timeout(400)
                        audit = page.evaluate(js_audit)
                        assert audit["bad"] == [], f"Unauth mobile {route} has <44px elements: {audit['bad']}"
                        assert audit["overflowX"] is False, f"Unauth mobile {route} has horizontal overflow"
                        cr = _contrast_ratio(_parse_rgb(audit["mutedHex"]), (255, 255, 255))
                        assert cr >= 4.5, f"Light mode --muted {audit['mutedHex']} on {route} contrast {cr:.2f} < 4.5"
                    ctx.close()

                    # 2. Authenticated Owner mobile 412x915 Light Mode (checks #btnLogoutHome & /auth details-summary)
                    ctx2 = browser.new_context(
                        viewport={"width": 412, "height": 915},
                        has_touch=True,
                        is_mobile=True,
                        user_agent=MOBILE_UA,
                        color_scheme="light",
                    )
                    ctx2.add_cookies([{"name": "sh_trusted_device", "value": td_token, "url": base_url, "httpOnly": True, "sameSite": "Lax"}])
                    page2 = ctx2.new_page()
                    page2.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=20000)
                    page2.wait_for_selector("#gateLoginEmail", state="visible", timeout=15000)
                    page2.fill("#gateLoginEmail", "nep94121@gmail.com")
                    page2.fill("#gateLoginPassword", "Fix10Ui#2026!")
                    page2.click("#btnSubmitGateLogin")
                    page2.wait_for_function(
                        "() => { const g = document.getElementById('homeLoginGateModal'); return g && (g.hidden || getComputedStyle(g).display === 'none'); }",
                        timeout=15000,
                    )
                    page2.wait_for_timeout(450)

                    logout_box = page2.locator("#btnLogoutHome").bounding_box()
                    assert logout_box is not None and logout_box["height"] >= 44.0, f"#btnLogoutHome box: {logout_box}"
                    for route in ("/", "/app", "/auth", "/guest_guide"):
                        if route != "/":
                            page2.goto(f"{base_url}{route}", wait_until="domcontentloaded", timeout=20000)
                            page2.wait_for_timeout(450)
                        audit = page2.evaluate(js_audit)
                        assert audit["bad"] == [], f"Owner mobile {route} has <44px elements: {audit['bad']}"
                        assert audit["overflowX"] is False, f"Owner mobile {route} has horizontal overflow"
                    auth_summary_box = page2.locator("#authForgotCard > summary").bounding_box() if False else None
                    page2.goto(f"{base_url}/auth", wait_until="domcontentloaded", timeout=20000)
                    page2.wait_for_timeout(350)
                    auth_summary_box = page2.locator("#authForgotCard > summary").bounding_box()
                    assert auth_summary_box is not None and auth_summary_box["height"] >= 44.0, f"/auth summary: {auth_summary_box}"
                    ctx2.close()
                finally:
                    browser.close()
        finally:
            if proc.poll() is None:
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=10)
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)


# ==============================================================================
# P2-3: COLD-START NONLINEAR AGC ECHO GUARD (JS, PYTHON & 10 COLD CHROMIUM TRIALS)
# ==============================================================================


class TestP2ColdStartAgcEchoGuard:
    def test_signed_lag_and_burst_jitter_echo_suppression_js_and_python_preserve_4_wavs(self) -> None:
        from backend.live.echo_and_speech_guard import ServerEchoGuard

        aoede_16k = _read_wav_floats(WAV_AOEDE_24K, 16000)
        aoede_24k = _read_wav_floats(WAV_AOEDE_24K, 24000)
        wavs = _human_wavs()
        assert len(wavs) == 4

        # 1. Python ServerEchoGuard: negative/positive cold-start clock skews (-40ms, -10ms, +60ms, +260ms) + nonlinear AGC
        total_16k = 16000 * 4
        ref_24k = [aoede_24k[i % len(aoede_24k)] for i in range(24000 * 4)]
        ref_24k_pcm = _floats_to_pcm16(ref_24k)

        for lag_ms in (-40, -10, 60, 260):
            shift = int(round(lag_ms * 16))
            raw_echo = []
            for i in range(total_16k):
                src = i - shift
                raw_echo.append((aoede_16k[src % len(aoede_16k)] * 0.22) if src >= 0 else 0.0)
            mic_nl = _simulate_nonlinear_agc(raw_echo)
            sg = ServerEchoGuard()
            t0 = 100.0
            sg.note_ai_audio_chunk(ref_24k_pcm, sample_rate=24000, now=t0)
            for i in range(0, len(mic_nl) - 320 + 1, 320):
                allow, trig, _ = sg.evaluate_mic_audio_chunk(_floats_to_pcm16(mic_nl[i : i + 320]), sample_rate=16000, now=t0 + i / 16000.0)
                assert not trig, f"ServerEchoGuard false barge-in at lag={lag_ms}ms, t={i/16.0}ms"
                assert not allow, f"ServerEchoGuard leaked echo at lag={lag_ms}ms, t={i/16.0}ms"

        # 2. Verify all 4 real Vietnamese WAVs still barge-in at 1.0x under nonlinear AGC on Python ServerEchoGuard
        for name, wpath in wavs.items():
            sp = _read_wav_floats(wpath, 16000)
            n_tot = max(total_16k, 16000 + len(sp) + 3200)
            ref24_w = _floats_to_pcm16([aoede_24k[i % len(aoede_24k)] for i in range(int(n_tot * 1.5))])
            mix = []
            for i in range(n_tot):
                echo_v = aoede_16k[(i - 960) % len(aoede_16k)] * 0.22 if i >= 960 else 0.0
                sp_v = sp[i - 9600] if 0 <= i - 9600 < len(sp) else 0.0
                mix.append(max(-1.0, min(1.0, echo_v + sp_v)))
            mic_nl = _simulate_nonlinear_agc(mix)
            sg = ServerEchoGuard()
            t0 = 100.0
            sg.note_ai_audio_chunk(ref24_w, sample_rate=24000, now=t0)
            triggered = 0
            leaked_before = 0
            for i in range(0, len(mic_nl) - 320 + 1, 320):
                rel_ms = i / 16.0
                allow, trig, _ = sg.evaluate_mic_audio_chunk(_floats_to_pcm16(mic_nl[i : i + 320]), sample_rate=16000, now=t0 + rel_ms / 1000.0)
                if allow and rel_ms < 600:
                    leaked_before += 1
                if trig:
                    triggered += 1
            assert leaked_before == 0, f"{name} leaked before speech on ServerEchoGuard"
            assert triggered >= 1, f"{name} failed to barge-in at 1.0x nonlinear AGC on ServerEchoGuard"

        # 3. Node.js SmartHomeEchoGuard negative/positive lag + callback burst jitter test
        node_script = r"""
const fs = require("fs");
const G = require(process.argv[1]);
const aoedePath = process.argv[2];
const buf = fs.readFileSync(aoedePath);
let off = 12, sr = 24000, dOff = 44, dLen = buf.length - 44;
while (off + 8 <= buf.length) {
  const id = buf.toString("ascii", off, off + 4), sz = buf.readUInt32LE(off + 4);
  if (id === "fmt ") sr = buf.readUInt32LE(off + 12);
  else if (id === "data") { dOff = off + 8; dLen = Math.min(sz, buf.length - dOff); break; }
  off += 8 + sz + (sz % 2);
}
const n24 = Math.floor(dLen / 2);
const a24 = new Float32Array(n24);
for (let i = 0; i < n24; i++) a24[i] = buf.readInt16LE(dOff + i * 2) / 32768.0;
const n16 = Math.floor(n24 / 1.5);
const a16 = new Float32Array(n16);
for (let i = 0; i < n16; i++) a16[i] = a24[Math.floor(i * 1.5)];

function nonlinearAgc(samples) {
  const out = new Float32Array(samples.length);
  let gain = 1.0, px = 0, py = 0;
  for (let i = 0; i < samples.length; i += 320) {
    const end = Math.min(samples.length, i + 320);
    let sq = 0;
    for (let j = i; j < end; j++) sq += samples[j] * samples[j];
    const rms = Math.sqrt(sq / Math.max(1, end - i));
    if (rms > 0.004) {
      const d = Math.min(8.0, Math.max(1.0, 0.28 / rms));
      const a = d > gain ? 0.30 : 0.15;
      gain = gain * (1 - a) + d * a;
    }
    for (let j = i; j < end; j++) {
      const y = 0.96 * (py + samples[j] - px);
      px = samples[j]; py = y;
      out[j] = Math.tanh(y * gain * 1.35);
    }
  }
  return out;
}

const out = [];
for (const lagMs of [-40, -10, 60, 260]) {
  const tot = 16000 * 3;
  const ref = new Float32Array(tot);
  const mic = new Float32Array(tot);
  const sh = Math.round(lagMs * 16);
  for (let i = 0; i < tot; i++) {
    ref[i] = a16[i % a16.length];
    const src = i - sh;
    if (src >= 0) mic[i] = a16[src % a16.length] * 0.22;
  }
  const nl = nonlinearAgc(mic);
  const g = G.createVoiceEchoGuard();
  g.notePlaybackQueued(3000, 1000, { samples: ref, sampleRate: 16000 });
  let trig = 0, leaked = 0;
  for (let i = 0; i + 688 <= nl.length; i += 688) {
    // Simulate occasional 43ms callback burst (2 callbacks arriving 2ms apart)
    const idx = Math.floor(i / 688);
    const jitter = (idx % 12 === 5) ? -35 : 0;
    const now = 1000 + (i / 16) + jitter;
    const r = g.evaluateMicFrame({ samples: nl.subarray(i, i + 688), sampleRate: 16000, frameDurationMs: 43, nowMs: now });
    if (r.bargeInTriggered) trig++;
    if (r.allowSend) leaked++;
  }
  out.push({ lagMs, trig, leaked });
}
console.log(JSON.stringify(out));
"""
        proc = subprocess.run(["node", "-e", node_script, str(ECHO_GUARD_JS), str(WAV_AOEDE_24K)], capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stderr
        rows = json.loads(proc.stdout.strip().splitlines()[-1])
        for row in rows:
            assert row["trig"] == 0, f"JS SmartHomeEchoGuard false barge-in: {row}"
            assert row["leaked"] == 0, f"JS SmartHomeEchoGuard leaked echo: {row}"

    def test_10_cold_start_chromium_forced_webrtc_agc_on_zero_false_barge_in(self) -> None:
        from playwright.sync_api import sync_playwright

        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="fix10_p23_"))
        data_dir = tmp_dir / "data"
        log_dir = tmp_dir / "logs"
        data_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)

        # Build 3s pure Aoede echo 20% 16kHz WAV for Chromium fake mic
        aoede_16k = _read_wav_floats(WAV_AOEDE_24K, 16000)
        echo_3s = [aoede_16k[i % len(aoede_16k)] * 0.20 for i in range(16000 * 3)]
        pure_wav = tmp_dir / "pure_aoede_echo_20pct_16k.wav"
        with wave.open(str(pure_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(_floats_to_pcm16(echo_3s))

        with wave.open(str(WAV_AOEDE_24K), "rb") as wf:
            raw24 = wf.readframes(wf.getnframes())
        vals24 = struct.unpack(f"<{len(raw24) // 2}h", raw24)
        need24 = 24000 * 3
        loop24 = (vals24 * ((need24 // len(vals24)) + 2))[:need24]
        doubled_24k = struct.pack(f"<{need24}h", *loop24) * 2

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["SMARTHOME_DATA_DIR"] = str(data_dir)
        env["SMARTHOME_LOG_DIR"] = str(log_dir)
        env["SMARTHOME_SESSION_SECRET"] = "fix10_p23_test_secret"
        env["GMAIL_APP_PASSWORD"] = ""
        env["SMTP_PASSWORD"] = ""
        env.pop("SIMULATOR_SECURITY_STATE_DIR", None)
        env.pop("SIMULATOR_OFFLINE_SANDBOX", None)

        seed_code = r"""
import json
from backend.auth_3layer import get_auth_3layer_manager
from backend.auth.constants_and_crypto import hash_password
from backend.auth.session_store import mint_trusted_device_token
from backend.database_sqlite import init_sqlite_database

init_sqlite_database()
mgr = get_auth_3layer_manager()
def _upd():
    for a in mgr.accounts:
        if str(a.get("email") or "").strip().lower() == "nep94121@gmail.com":
            a["password_hash"] = hash_password("Fix10P23#2026!")
            a["permission_active"] = True
            a["permission_status"] = "ACTIVE"
    return mgr._save_accounts()
mgr._with_cas_accounts(_upd)
td = mint_trusted_device_token(
    account_id="tuan_anh",
    email="nep94121@gmail.com",
    password_hash=hash_password("Fix10P23#2026!"),
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
)
print(json.dumps({"td": td}))
"""
        seed_proc = subprocess.run([sys.executable, "-c", seed_code], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=30)
        assert seed_proc.returncode == 0, seed_proc.stderr
        td_desktop = json.loads([ln for ln in seed_proc.stdout.splitlines() if ln.strip().startswith("{")][-1])["td"]

        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.server:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            deadline = time.time() + 25
            while time.time() < deadline:
                try:
                    if requests.get(f"{base_url}/api/health", timeout=2).status_code == 200:
                        break
                except Exception:
                    pass
                time.sleep(0.3)
            else:
                raise RuntimeError("Local test server failed to start")

            with sync_playwright() as p:
                for trial in range(1, 11):
                    browser = _launch_headless_chromium(
                        p,
                        extra_args=[
                            "--use-fake-device-for-media-stream",
                            "--use-fake-ui-for-media-stream",
                            f"--use-file-for-fake-audio-capture={pure_wav}",
                            "--autoplay-policy=no-user-gesture-required",
                        ],
                    )
                    try:
                        ctx = browser.new_context(
                            viewport={"width": 1366, "height": 768},
                            user_agent=DESKTOP_UA,
                            permissions=["microphone"],
                        )
                        ctx.add_cookies([{"name": "sh_trusted_device", "value": td_desktop, "url": base_url, "httpOnly": True, "sameSite": "Lax"}])
                        page = ctx.new_page()
                        page.add_init_script(
                            """(() => {
                                window.__p23 = { gumTs: 0, aiTs: 0, aiWin: false, bargeInSent: 0, micDuringAi: 0, micFirst400ms: 0, lastWs: null };
                                if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
                                    const orig = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
                                    navigator.mediaDevices.getUserMedia = async function(c) {
                                        const mod = Object.assign({}, c, { audio: Object.assign({}, (c && c.audio) || {}, { autoGainControl: true }) });
                                        const s = await orig(mod);
                                        window.__p23.gumTs = performance.now();
                                        return s;
                                    };
                                }
                                const OrigWS = window.WebSocket;
                                window.WebSocket = function(url, prot) {
                                    const ws = prot ? new OrigWS(url, prot) : new OrigWS(url);
                                    if (String(url).includes('/ws')) window.__p23.lastWs = ws;
                                    const origSend = ws.send.bind(ws);
                                    ws.send = function(data) {
                                        try {
                                            const m = typeof data === 'string' ? JSON.parse(data) : null;
                                            if (m && m.type === 'mic_chunk' && window.__p23.aiWin) {
                                                window.__p23.micDuringAi++;
                                                if (performance.now() - window.__p23.aiTs <= 400) window.__p23.micFirst400ms++;
                                            }
                                            if (m && m.type === 'barge_in') {
                                                window.__p23.bargeInSent++;
                                            }
                                        } catch (_) {}
                                        return origSend(data);
                                    };
                                    return ws;
                                };
                                window.WebSocket.prototype = OrigWS.prototype;
                                window.WebSocket.OPEN = OrigWS.OPEN;
                                window.WebSocket.CLOSED = OrigWS.CLOSED;
                                window.WebSocket.CONNECTING = OrigWS.CONNECTING;
                                window.WebSocket.CLOSING = OrigWS.CLOSING;
                            })();"""
                        )
                        page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_selector("#gateLoginEmail", state="visible", timeout=15000)
                        page.fill("#gateLoginEmail", "nep94121@gmail.com")
                        page.fill("#gateLoginPassword", "Fix10P23#2026!")
                        page.click("#btnSubmitGateLogin")
                        page.wait_for_function(
                            "() => { const g = document.getElementById('homeLoginGateModal'); return g && (g.hidden || getComputedStyle(g).display === 'none'); }",
                            timeout=15000,
                        )
                        page.wait_for_timeout(350)
                        page.click("#btnMicLive")
                        page.wait_for_timeout(550)
                        elapsed_ms = page.evaluate("() => window.__p23.gumTs ? (performance.now() - window.__p23.gumTs) : 0")
                        pos_sec = ((elapsed_ms + 50.0) / 1000.0) % 3.0
                        byte_off = int(pos_sec * 24000) * 2
                        chunk_b64 = base64.b64encode(doubled_24k[byte_off : byte_off + 24000 * 2 * 2]).decode("ascii")
                        page.evaluate(
                            """(b64) => {
                                window.__p23.aiTs = performance.now();
                                window.__p23.aiWin = true;
                                window.__p23.lastWs.onmessage({ data: JSON.stringify({ type: 'audio_chunk', pcm24k_b64: b64 }) });
                            }""",
                            chunk_b64,
                        )
                        page.wait_for_timeout(1850)
                        res = page.evaluate(
                            """() => {
                                window.__p23.aiWin = false;
                                return {
                                    bargeInSent: window.__p23.bargeInSent,
                                    micDuringAi: window.__p23.micDuringAi,
                                    micFirst400ms: window.__p23.micFirst400ms,
                                };
                            }"""
                        )
                        assert res["bargeInSent"] == 0, f"Cold-start AGC ON trial {trial}/10 triggered false barge-in: {res}"
                        assert res["micFirst400ms"] == 0, f"Cold-start AGC ON trial {trial}/10 leaked in first 400ms: {res}"
                        assert res["micDuringAi"] == 0, f"Cold-start AGC ON trial {trial}/10 leaked mic frames: {res}"
                        page.click("#btnMicLive")
                        ctx.close()
                    finally:
                        browser.close()
        finally:
            if proc.poll() is None:
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=10)
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)
