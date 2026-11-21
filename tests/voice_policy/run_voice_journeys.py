"""End-to-End Voice & Text Journey QA Runner on isolated temp server (127.0.0.1:8099).

Executes:
  Phase A: All >=200 utterances across 10 complete ordered E2E user journeys via POST /api/text_command
  Phase B: All >=200 utterances as clean synthesized Vietnamese/foreign/noise WAVs via POST /api/voice_command
           (wav_b64 ONLY, NO transcript hint -> real local Whisper STT -> NLU -> SmartHomeEngine)
  Phase C: All 11 audio degradations (white/babble SNR 20/10/5 dB, reverb/echo, -20dB low gain,
           clipping, speed 0.8x, speed 1.2x) on >=25 representative utterances spanning all categories,
           pure noise, and foreign speech via POST /api/voice_command (NO transcript hint!)

Outputs saved to C:\\Users\\LENOVO\\datn-wt\\agyvoicefix1_20261120\\voice_tests\\:
  - results.json
  - results.csv
  - metrics_summary.json
  - journey_results.json
  - coverage_matrix.json
Summary chart saved to:
  - C:\\Users\\LENOVO\\datn-wt\\agyvoicefix1_20261120\\screenshots\\65_voice_test_summary.png
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import time
from collections import defaultdict
from typing import Any

import numpy as np
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.voice.vietnamese_policy import (  # noqa: E402
    _FOREIGN_LATIN_DIACRITIC_RE,
    _NON_VI_SCRIPT_RE,
    _VI_DIACRITIC_RE,
    _detect_foreign_latin,
)
from tests.voice_policy.audio_synth import (  # noqa: E402
    DEGRADATIONS,
    apply_degradation,
    pcm16_to_wav_b64,
    synth_babble_only,
    synth_foreign_audio,
    synth_pure_white_noise,
    synthesize_edge_tts_speech,
    synthesize_persona_speech,
)
from tests.voice_policy.journey_suite import (  # noqa: E402
    COVERAGE_CATEGORIES,
    JourneyStep,
    UserJourney,
    build_user_journeys,
    flatten_steps,
    get_degraded_eval_steps,
)

try:
    from langdetect import DetectorFactory as _LDFactory
    from langdetect import detect as _ld_detect

    _LDFactory.seed = 0
except Exception:
    _ld_detect = None  # type: ignore[assignment]

DEFAULT_RUN_DIR = pathlib.Path(r"C:\Users\LENOVO\datn-wt\agyvoicefix2_20261121")
DEFAULT_AUDIO_CACHE_DIR = pathlib.Path(r"C:\Users\LENOVO\datn-wt\agyvoicefix1_20261120\voice_tests\audio_cache")

RUN_DIR = DEFAULT_RUN_DIR
TEMP_DATA_DIR = RUN_DIR / "temp_data"
TEMP_LOG_DIR = RUN_DIR / "temp_logs"
VOICE_TESTS_DIR = RUN_DIR / "voice_tests"
AUDIO_CACHE_DIR = DEFAULT_AUDIO_CACHE_DIR
SCREENSHOTS_DIR = RUN_DIR / "screenshots"

TEMP_PORT = 8099
BASE_URL = f"http://127.0.0.1:{TEMP_PORT}"
SESSION_SECRET = "voice_policy_qa_8099_secret"

ALL_6_DEVICES = (
    "main_door",
    "living_room_light",
    "bedroom_light",
    "garden_pump",
    "alarm_siren",
    "speaker_amp",
)


def _log(msg: str, log_file: pathlib.Path | None = None) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            pass


def verify_vietnamese_only_output(reply_text: str, *, allow_empty: bool = False) -> tuple[bool, str]:
    """Verify output is strictly Vietnamese using script checks + policy detector + langdetect."""
    txt = str(reply_text or "").strip()
    if not txt:
        return (True, "empty_silent") if allow_empty else (False, "empty_reply")
    if _NON_VI_SCRIPT_RE.search(txt):
        return False, "non_vi_script"
    if _FOREIGN_LATIN_DIACRITIC_RE.search(txt):
        return False, "foreign_latin_diacritic"
    if _detect_foreign_latin(txt):
        return False, "foreign_latin_words"

    # Cross-check with langdetect on sentences long enough for reliable statistical detection
    alpha_only = re.sub(r"[^A-Za-zÀ-ỹ\s]+", " ", txt)
    alpha_only = " ".join(alpha_only.split())
    has_vi_diac = bool(_VI_DIACRITIC_RE.search(txt))
    if _ld_detect is not None and len(alpha_only) >= 24:
        try:
            lang = str(_ld_detect(alpha_only) or "").lower()
            if lang and lang != "vi" and not has_vi_diac:
                return False, f"langdetect={lang}"
            if lang in ("en", "fr", "de", "es", "ko", "ja", "zh-cn", "zh-tw", "ru", "th"):
                # Even if a single accented name appeared, reject if predominantly foreign
                return False, f"langdetect={lang}"
        except Exception:
            pass
    return True, "vi"


def _seed_temp_db_and_sessions(data_dir: pathlib.Path, log_dir: pathlib.Path, env: dict[str, str]) -> dict[str, str]:
    """Initialize fresh SQLite DB and create throwaway Tier 1/2/3 test sessions inside temp_data ONLY."""
    if data_dir.exists():
        shutil.rmtree(data_dir, ignore_errors=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    seed_script = r"""
import json
from simulator.database_sqlite import init_sqlite_database
from simulator.auth_3layer import get_auth_3layer_manager
from simulator.auth.constants_and_crypto import hash_password
from simulator.auth.session_store import get_session_store

init_sqlite_database()
mgr = get_auth_3layer_manager()
def _upd():
    for a in mgr.accounts:
        if str(a.get("email") or "").strip().lower() == "nep94121@gmail.com":
            a["password_hash"] = hash_password("VoiceQaTest#2026!")
            a["permission_active"] = True
            a["permission_status"] = "ACTIVE"
    return mgr._save_accounts()
mgr._with_cas_accounts(_upd)

store = get_session_store()
s1 = store.create_session(user_id="tuan_anh", email="nep94121@gmail.com", display_name="Chủ nhà QA", tier=1, role="ADMIN", source="qa_voice_test")
s1_b = store.create_session(user_id="tuan_anh", email="nep94121@gmail.com", display_name="Chủ nhà QA", tier=1, role="ADMIN", source="qa_voice_resume")
s1_deg = store.create_session(user_id="tuan_anh", email="nep94121@gmail.com", display_name="Chủ nhà QA", tier=1, role="ADMIN", source="qa_degraded")
s2 = store.create_session(user_id="qa_family_t2", email="qa_family@test.local", display_name="Thành viên QA", tier=2, role="MEMBER", source="qa_voice_test")
s3 = store.create_session(user_id="qa_guest_t3", email="qa_guest@test.local", display_name="Khách QA", tier=3, role="CHILD_GUEST", source="qa_voice_test")
print(json.dumps({
    "tier1": s1.session_id,
    "tier1_resume": s1_b.session_id,
    "tier1_deg": s1_deg.session_id,
    "tier2": s2.session_id,
    "tier3": s3.session_id,
}))
"""
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", seed_script],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Temp DB seed failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}")
    json_lines = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")]
    if not json_lines:
        raise RuntimeError(f"No JSON session output from seed script: {proc.stdout}")
    return json.loads(json_lines[-1])


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _start_temp_server(
    env: dict[str, str],
    log_dir: pathlib.Path,
    log_name: str = "uvicorn_8099.log",
) -> subprocess.Popen[Any]:
    if _port_in_use(TEMP_PORT):
        raise RuntimeError(f"Port {TEMP_PORT} is already in use! Refusing to overwrite another process.")
    srv_log = log_dir / log_name
    fh = srv_log.open("wb")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "uvicorn",
            "simulator.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(TEMP_PORT),
            "--timeout-keep-alive",
            "30",
            "--log-level",
            "warning",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=fh,
        stderr=fh,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.time() + 35.0
    while time.time() < deadline:
        if proc.poll() is not None:
            fh.close()
            err_txt = srv_log.read_text(encoding="utf-8", errors="replace")[-1500:]
            raise RuntimeError(f"Temp server exited early ({proc.returncode}):\n{err_txt}")
        try:
            r = requests.get(f"{BASE_URL}/api/health", timeout=2.0)
            if r.status_code == 200:
                return proc
        except Exception:
            pass
        time.sleep(0.3)
    _stop_process_tree(proc)
    raise RuntimeError("Temp server failed to become healthy on port 8099 within 35s")


def _stop_process_tree(proc: subprocess.Popen[Any] | None) -> None:
    if proc is None:
        return
    try:
        if proc.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=15,
            )
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _get_device_states(http: requests.Session, headers: dict[str, str]) -> dict[str, str]:
    r = http.get(f"{BASE_URL}/api/state", headers=headers, timeout=10.0)
    if r.status_code != 200:
        return {}
    data = r.json()
    out: dict[str, str] = {}
    devs = data.get("devices")
    if isinstance(devs, dict):
        for k, v in devs.items():
            if isinstance(v, dict):
                out[k] = str(v.get("state") or "").upper()
    elif isinstance(devs, list):
        for d in devs:
            if isinstance(d, dict) and d.get("id"):
                out[str(d["id"])] = str(d.get("state") or "").upper()
    return out


def _reset_all_devices_off(http: requests.Session, owner_headers: dict[str, str]) -> None:
    for did in ALL_6_DEVICES:
        act = "close" if did == "main_door" else "turn_off"
        http.post(
            f"{BASE_URL}/api/device",
            headers=owner_headers,
            json={"device_id": did, "action": act, "source": "qa_harness"},
            timeout=10.0,
        )


def _expire_pending_in_temp_db(data_dir: pathlib.Path) -> None:
    import sqlite3

    db_path = data_dir / "smarthome.db"
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    try:
        conn.execute(
            "UPDATE pending_confirmations SET expires_at = ? WHERE status = 'pending'",
            (time.time() - 10.0,),
        )
        conn.commit()
    finally:
        conn.close()


def _clear_pending_in_temp_db(data_dir: pathlib.Path) -> None:
    import sqlite3

    db_path = data_dir / "smarthome.db"
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    try:
        conn.execute("UPDATE pending_confirmations SET status = 'cancelled' WHERE status = 'pending'")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def _cancel_all_timers_and_schedules(
    http: requests.Session,
    owner_headers: dict[str, str],
    data_dir: pathlib.Path,
) -> None:
    """Cancel all active in-memory timers and persisted timers/schedules between journeys/phases."""
    _clear_pending_in_temp_db(data_dir)
    try:
        r1 = http.post(
            f"{BASE_URL}/api/text_command",
            headers=owner_headers,
            json={"text": "xóa hết hẹn giờ"},
            timeout=15.0,
        )
        b1 = r1.json() if r1.headers.get("content-type", "").startswith("application/json") else {}
        if b1.get("requires_confirmation"):
            http.post(
                f"{BASE_URL}/api/text_command",
                headers=owner_headers,
                json={"text": "ok"},
                timeout=15.0,
            )
    except Exception:
        pass
    _clear_pending_in_temp_db(data_dir)


def _run_pre_setup(
    hook: str,
    http: requests.Session,
    owner_headers: dict[str, str],
    data_dir: pathlib.Path,
) -> None:
    if not hook:
        return
    if hook == "reset_devices_off":
        _reset_all_devices_off(http, owner_headers)
    elif hook == "clear_pending":
        _clear_pending_in_temp_db(data_dir)
    elif hook == "set_sensors_known":
        http.post(f"{BASE_URL}/api/dht11", headers=owner_headers, json={"temp_c": 28.5, "humidity_pct": 65.0}, timeout=10.0)
        http.post(f"{BASE_URL}/api/soil_moisture", headers=owner_headers, json={"soil_moisture_pct": 58.0}, timeout=10.0)
        http.post(f"{BASE_URL}/api/sound_sensor", headers=owner_headers, json={"sound_detected": False}, timeout=10.0)
    elif hook == "prep_custom_di_lam":
        http.post(f"{BASE_URL}/api/device", headers=owner_headers, json={"device_id": "living_room_light", "action": "turn_on"}, timeout=10.0)
        http.post(f"{BASE_URL}/api/device", headers=owner_headers, json={"device_id": "bedroom_light", "action": "turn_on"}, timeout=10.0)
        http.post(f"{BASE_URL}/api/device", headers=owner_headers, json={"device_id": "main_door", "action": "open"}, timeout=10.0)
    elif hook == "ensure_bedroom_off":
        http.post(f"{BASE_URL}/api/device", headers=owner_headers, json={"device_id": "bedroom_light", "action": "turn_off"}, timeout=10.0)
    elif hook == "prep_door_light_rule":
        http.post(f"{BASE_URL}/api/device", headers=owner_headers, json={"device_id": "main_door", "action": "close"}, timeout=10.0)
        http.post(f"{BASE_URL}/api/device", headers=owner_headers, json={"device_id": "living_room_light", "action": "turn_off"}, timeout=10.0)
    elif hook == "prep_soil_pump_rule":
        http.post(f"{BASE_URL}/api/soil_moisture", headers=owner_headers, json={"soil_moisture_pct": 62.0}, timeout=10.0)
        http.post(f"{BASE_URL}/api/device", headers=owner_headers, json={"device_id": "garden_pump", "action": "turn_off"}, timeout=10.0)
    elif hook == "prep_sound_siren_rule":
        http.post(f"{BASE_URL}/api/sound_sensor", headers=owner_headers, json={"sound_detected": False}, timeout=10.0)
        http.post(f"{BASE_URL}/api/device", headers=owner_headers, json={"device_id": "alarm_siren", "action": "turn_off"}, timeout=10.0)
    elif hook == "expire_pending_confirmations":
        _expire_pending_in_temp_db(data_dir)


def _run_post_verify(
    hook: str,
    http: requests.Session,
    owner_headers: dict[str, str],
) -> tuple[bool, str]:
    if not hook:
        return True, ""
    if hook == "wait_timer_bedroom_on":
        deadline = time.time() + 5.5
        while time.time() < deadline:
            st = _get_device_states(http, owner_headers)
            if st.get("bedroom_light") == "ON":
                return True, "timer_fired:bedroom_light=ON"
            time.sleep(0.35)
        st = _get_device_states(http, owner_headers)
        return False, f"timer_did_not_fire:bedroom_light={st.get('bedroom_light')}"
    if hook == "wait_timer_living_off":
        deadline = time.time() + 6.5
        while time.time() < deadline:
            st = _get_device_states(http, owner_headers)
            if st.get("living_room_light") == "OFF":
                return True, "timer_fired:living_room_light=OFF"
            time.sleep(0.35)
        st = _get_device_states(http, owner_headers)
        return False, f"timer_did_not_fire:living_room_light={st.get('living_room_light')}"
    if hook == "trigger_door_to_light":
        http.post(f"{BASE_URL}/api/device", headers=owner_headers, json={"device_id": "main_door", "action": "close"}, timeout=10.0)
        http.post(f"{BASE_URL}/api/device", headers=owner_headers, json={"device_id": "living_room_light", "action": "turn_off"}, timeout=10.0)
        http.post(f"{BASE_URL}/api/device", headers=owner_headers, json={"device_id": "main_door", "action": "open"}, timeout=10.0)
        time.sleep(0.25)
        st = _get_device_states(http, owner_headers)
        ok = st.get("living_room_light") == "ON"
        return ok, f"door->light:{st.get('living_room_light')}"
    if hook == "trigger_soil_to_pump":
        http.post(f"{BASE_URL}/api/soil_moisture", headers=owner_headers, json={"soil_moisture_pct": 65.0}, timeout=10.0)
        http.post(f"{BASE_URL}/api/device", headers=owner_headers, json={"device_id": "garden_pump", "action": "turn_off"}, timeout=10.0)
        http.post(f"{BASE_URL}/api/soil_moisture", headers=owner_headers, json={"soil_moisture_pct": 25.0}, timeout=10.0)
        time.sleep(0.25)
        st = _get_device_states(http, owner_headers)
        ok = st.get("garden_pump") == "ON"
        return ok, f"soil_dry->pump:{st.get('garden_pump')}"
    if hook == "trigger_sound_to_siren":
        http.post(f"{BASE_URL}/api/sound_sensor", headers=owner_headers, json={"sound_detected": False}, timeout=10.0)
        http.post(f"{BASE_URL}/api/device", headers=owner_headers, json={"device_id": "alarm_siren", "action": "turn_off"}, timeout=10.0)
        http.post(f"{BASE_URL}/api/sound_sensor", headers=owner_headers, json={"sound_detected": True}, timeout=10.0)
        time.sleep(0.25)
        st = _get_device_states(http, owner_headers)
        ok = st.get("alarm_siren") == "ON"
        return ok, f"sound_loud->siren:{st.get('alarm_siren')}"
    return True, ""


def _evaluate_response(
    step: JourneyStep,
    *,
    status_code: int,
    body: dict[str, Any],
    before_states: dict[str, str],
    after_states: dict[str, str],
    post_ok: bool,
    post_note: str,
    mode: str,
) -> dict[str, Any]:
    """Evaluate action correctness, confirmation policy correctness, VI-only output, and false-action flag."""
    reply = str(body.get("exact_spoken_reply") or body.get("reply") or body.get("error") or "").strip()
    reply_low = reply.lower()
    req_conf = bool(body.get("requires_confirmation"))
    executed = bool(body.get("executed"))
    rbac_blocked = bool(body.get("rbac_blocked"))
    silent = bool(body.get("silent"))
    confirmed = bool(body.get("confirmed"))
    cancelled = bool(body.get("cancelled"))
    expired = bool(body.get("expired"))
    kind = str(body.get("kind") or "")

    # Detect ANY unexpected device state mutation
    mutated_devices = [
        d for d in ALL_6_DEVICES
        if before_states.get(d) and after_states.get(d) and before_states[d] != after_states[d]
    ]

    allow_empty = (step.expected_behavior == "noise_no_action" and silent) or (
        step.expected_behavior in ("foreign_no_action", "clarify_no_action") and mode != "text" and silent
    )
    vi_ok, vi_reason = verify_vietnamese_only_output(reply, allow_empty=allow_empty)

    beh = step.expected_behavior
    action_ok = True
    confirm_policy_ok = True
    false_action = False
    reasons: list[str] = []

    if beh == "small_talk":
        if status_code != 200 or rbac_blocked or req_conf or executed or mutated_devices:
            action_ok = False
            reasons.append(f"small_talk bad flags status={status_code} rbac={rbac_blocked} conf={req_conf} exec={executed} mut={mutated_devices}")
        if req_conf:
            confirm_policy_ok = False
        if mutated_devices or executed:
            false_action = True

    elif beh == "immediate_device":
        if status_code != 200 or rbac_blocked or req_conf or not executed:
            action_ok = False
            reasons.append(f"immediate_device fail status={status_code} rbac={rbac_blocked} conf={req_conf} exec={executed}")
        if req_conf:
            confirm_policy_ok = False
        for d, exp_st in step.expected_device_states.items():
            if after_states.get(d) != exp_st:
                action_ok = False
                reasons.append(f"device {d} expected {exp_st} got {after_states.get(d)}")

    elif beh in ("sensor_query", "status_query"):
        if status_code != 200 or rbac_blocked or req_conf or mutated_devices:
            action_ok = False
            reasons.append(f"{beh} fail status={status_code} rbac={rbac_blocked} conf={req_conf} mut={mutated_devices}")
        if req_conf:
            confirm_policy_ok = False
        if mutated_devices:
            false_action = True

    elif beh == "pool_query":
        if status_code != 200 or rbac_blocked or req_conf or mutated_devices:
            action_ok = False
            reasons.append(f"pool_query fail status={status_code} rbac={rbac_blocked} conf={req_conf}")
        if req_conf:
            confirm_policy_ok = False

    elif beh == "confirm_prompt":
        if status_code != 200 or not req_conf or executed or mutated_devices:
            action_ok = False
            confirm_policy_ok = False
            reasons.append(f"confirm_prompt fail status={status_code} conf={req_conf} exec={executed} mut={mutated_devices}")

    elif beh == "confirm_yes":
        if status_code != 200 or not (confirmed or body.get("ok")):
            action_ok = False
            reasons.append(f"confirm_yes fail status={status_code} confirmed={confirmed} ok={body.get('ok')}")
        for d, exp_st in step.expected_device_states.items():
            if after_states.get(d) != exp_st:
                action_ok = False
                reasons.append(f"post-confirm device {d} expected {exp_st} got {after_states.get(d)}")

    elif beh == "confirm_no":
        if status_code != 200 or not cancelled or executed or mutated_devices:
            action_ok = False
            reasons.append(f"confirm_no fail status={status_code} cancelled={cancelled} exec={executed} mut={mutated_devices}")
        if executed or mutated_devices:
            false_action = True

    elif beh == "confirm_expired":
        if status_code != 200 or not (expired or cancelled) or executed or mutated_devices:
            action_ok = False
            reasons.append(f"confirm_expired fail status={status_code} expired={expired} cancelled={cancelled} exec={executed}")
        if executed or mutated_devices:
            false_action = True

    elif beh == "confirm_reminder":
        if status_code != 200 or not req_conf or executed or mutated_devices or kind != "confirmation_reminder":
            action_ok = False
            reasons.append(f"confirm_reminder fail status={status_code} conf={req_conf} exec={executed} kind={kind}")
        if executed or mutated_devices:
            false_action = True

    elif beh in ("clarify_no_action", "noise_no_action", "foreign_no_action"):
        # CRITICAL: ZERO device actions allowed!
        if executed or mutated_devices or req_conf:
            action_ok = False
            false_action = True
            reasons.append(f"{beh} FALSE ACTION exec={executed} conf={req_conf} mut={mutated_devices}")
        if rbac_blocked or status_code == 403:
            action_ok = False
            reasons.append(f"{beh} unexpected 403/rbac_blocked")

    elif beh == "rbac_denied":
        if status_code != 403 or not rbac_blocked or executed or mutated_devices:
            action_ok = False
            reasons.append(f"rbac_denied fail status={status_code} rbac={rbac_blocked} exec={executed} mut={mutated_devices}")
        if executed or mutated_devices:
            false_action = True
        for d, exp_st in step.expected_device_states.items():
            if after_states.get(d) != exp_st:
                action_ok = False
                reasons.append(f"rbac_denied device {d} expected {exp_st} got {after_states.get(d)}")

    # Check expected & forbidden reply substrings (skip exact substring check on noisy/degraded STT if action passed,
    # still enforce forbidden_reply_substrings ALWAYS!)
    for forb in step.forbidden_reply_substrings:
        if forb.lower() in reply_low:
            action_ok = False
            reasons.append(f"forbidden_substring:{forb!r}")

    if mode == "text":
        for sub in step.expected_reply_substrings:
            if sub.lower() not in reply_low:
                action_ok = False
                reasons.append(f"missing_substring:{sub!r}")

    if not post_ok:
        action_ok = False
        reasons.append(f"post_verify_failed:{post_note}")

    if not vi_ok:
        reasons.append(f"non_vietnamese_reply:{vi_reason}")

    passed = action_ok and confirm_policy_ok and vi_ok and (not false_action)
    return {
        "passed": passed,
        "action_ok": action_ok,
        "confirm_policy_ok": confirm_policy_ok,
        "vi_only_ok": vi_ok,
        "vi_reason": vi_reason,
        "false_action": false_action,
        "mutated_devices": mutated_devices,
        "reasons": "; ".join(reasons),
    }


def _build_step_pcm16(step: JourneyStep, idx: int, cache_dir: pathlib.Path) -> np.ndarray:
    if step.audio_kind == "pure_white_noise":
        return synth_pure_white_noise(duration_sec=1.8, seed=1000 + idx)
    if step.audio_kind == "pure_babble_noise":
        return synth_babble_only(duration_sec=2.0, seed=2000 + idx, cache_dir=cache_dir)
    if step.lang != "vi":
        return synth_foreign_audio(step.text, lang=step.lang, persona="neutral", cache_dir=cache_dir)
    return synthesize_persona_speech(step.text, persona=step.persona, lang="vi", cache_dir=cache_dir)


def _prewarm_audio_cache(
    steps: list[JourneyStep],
    cache_dir: pathlib.Path,
    log_file: pathlib.Path,
) -> dict[str, np.ndarray]:
    _log(f"Pre-synthesizing / loading audio cache for {len(steps)} utterances from {cache_dir}...", log_file)
    t0 = time.perf_counter()
    cache: dict[str, np.ndarray] = {}

    def _job(pair: tuple[int, JourneyStep]) -> tuple[str, np.ndarray]:
        i, st = pair
        return st.step_id, _build_step_pcm16(st, i, cache_dir)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for sid, pcm in ex.map(_job, enumerate(steps)):
            cache[sid] = pcm
    _log(f"Audio cache ready ({len(cache)} clips) in {time.perf_counter() - t0:.1f}s.", log_file)
    return cache


FRESH_VOICE_PROFILES: dict[str, dict[str, Any]] = {
    "hoaimy_normal": {"voice": "vi-VN-HoaiMyNeural", "rate": "+0%", "pitch": "+0Hz", "degradation": "clean"},
    "hoaimy_fast": {"voice": "vi-VN-HoaiMyNeural", "rate": "+18%", "pitch": "+0Hz", "degradation": "clean"},
    "namminh_normal": {"voice": "vi-VN-NamMinhNeural", "rate": "+0%", "pitch": "+0Hz", "degradation": "clean"},
    "namminh_slow": {"voice": "vi-VN-NamMinhNeural", "rate": "-15%", "pitch": "-10Hz", "degradation": "clean"},
    "namminh_noisy10": {"voice": "vi-VN-NamMinhNeural", "rate": "+0%", "pitch": "+0Hz", "degradation": "white_snr10"},
    # Round-3 additional diverse speaker styles (+40 fresh voices -> 80 total)
    "elderly_slow_female": {"voice": "vi-VN-HoaiMyNeural", "rate": "-22%", "pitch": "-16Hz", "degradation": "clean"},
    "kid_fast_high": {"voice": "vi-VN-HoaiMyNeural", "rate": "+22%", "pitch": "+24Hz", "degradation": "clean"},
    "fast_male_bac": {"voice": "vi-VN-NamMinhNeural", "rate": "+20%", "pitch": "-5Hz", "degradation": "clean"},
    "regional_nam_style": {"voice": "vi-VN-HoaiMyNeural", "rate": "+5%", "pitch": "+6Hz", "degradation": "clean"},
    "regional_trung_reverb": {"voice": "vi-VN-NamMinhNeural", "rate": "-8%", "pitch": "-8Hz", "degradation": "reverb_echo"},
    "noisy_babble10_female": {"voice": "vi-VN-HoaiMyNeural", "rate": "+0%", "pitch": "+0Hz", "degradation": "babble_snr10"},
}


def build_fresh_voice_steps() -> list[JourneyStep]:
    """80 fresh real-user utterances (40 R2 + 40 R3 elderly/kid/fast/regional/noisy) across all 10 categories."""
    jid = "FRESH_neural_voices"

    def _f(
        sid: str,
        cat: int,
        subcat: str,
        profile: str,
        text: str,
        beh: str,
        **kw: Any,
    ) -> JourneyStep:
        return JourneyStep(
            step_id=sid,
            journey_id=jid,
            category=cat,
            subcat=subcat,
            persona=profile,
            tier=1,
            text=text,
            expected_behavior=beh,
            **kw,
        )

    return [
        # Cat 1: Session start (3)
        _f("F01", 1, "fresh_greeting", "hoaimy_normal", "chào buổi tối", "small_talk"),
        _f("F02", 1, "fresh_help", "namminh_normal", "bạn có thể giúp gì cho tôi", "small_talk"),
        _f("F03", 1, "fresh_greet_slow", "namminh_slow", "xin chào trợ lý nhà thông minh", "small_talk"),
        # Cat 2: Direct device commands covering all 6 devices + all_lights + multi-device (9)
        _f("F04", 2, "fresh_door_open", "hoaimy_normal", "mở cửa chính giúp mình", "immediate_device", pre_setup="reset_devices_off", expected_device_states={"main_door": "OPEN"}),
        _f("F05", 2, "fresh_door_close", "hoaimy_fast", "đóng cửa chính lại", "immediate_device", expected_device_states={"main_door": "CLOSED"}),
        _f("F06", 2, "fresh_living_on", "namminh_normal", "bật đèn phòng khách lên", "immediate_device", expected_device_states={"living_room_light": "ON"}),
        _f("F07", 2, "fresh_bedroom_on", "namminh_slow", "bật đèn phòng ngủ giúp bác", "immediate_device", expected_device_states={"bedroom_light": "ON"}),
        _f("F08", 2, "fresh_all_lights_off", "namminh_noisy10", "tắt tất cả đèn", "immediate_device", expected_device_states={"living_room_light": "OFF", "bedroom_light": "OFF"}),
        _f("F09", 2, "fresh_pump_on", "hoaimy_fast", "bật máy bơm tưới cây", "immediate_device", expected_device_states={"garden_pump": "ON"}),
        _f("F10", 2, "fresh_pump_off", "namminh_noisy10", "tắt máy bơm tưới cây", "immediate_device", expected_device_states={"garden_pump": "OFF"}),
        _f("F11", 2, "fresh_siren_on", "hoaimy_normal", "bật còi báo động", "immediate_device", expected_device_states={"alarm_siren": "ON"}),
        _f("F12", 2, "fresh_multi_siren_spk", "namminh_normal", "tắt còi báo động và bật nguồn mạch loa", "immediate_device", expected_device_states={"alarm_siren": "OFF", "speaker_amp": "ON"}),
        # Cat 3: Sensor & status queries (4)
        _f("F13", 3, "fresh_temp", "hoaimy_normal", "nhiệt độ trong nhà hiện tại bao nhiêu", "sensor_query", pre_setup="set_sensors_known"),
        _f("F14", 3, "fresh_soil", "namminh_normal", "độ ẩm đất bây giờ là bao nhiêu", "sensor_query"),
        _f("F15", 3, "fresh_light_status", "namminh_slow", "trạng thái đèn phòng khách thế nào", "status_query"),
        _f("F16", 3, "fresh_sound", "namminh_noisy10", "cảm biến âm thanh có phát hiện gì không", "sensor_query"),
        # Cat 4: Custom commands (4)
        _f("F17", 4, "fresh_custom_create", "hoaimy_normal", "tạo lệnh nghỉ ngơi là tắt đèn phòng khách và bật đèn phòng ngủ", "confirm_prompt"),
        _f("F18", 4, "fresh_custom_create_ok", "hoaimy_fast", "đồng ý", "confirm_yes"),
        _f("F19", 4, "fresh_custom_delete", "namminh_normal", "xóa lệnh nghỉ ngơi", "confirm_prompt"),
        _f("F20", 4, "fresh_custom_delete_ok", "namminh_slow", "ok", "confirm_yes"),
        # Cat 5: Schedules & timers (4)
        _f("F21", 5, "fresh_sched_create", "hoaimy_fast", "đặt lịch 6 giờ sáng hằng ngày mở cửa chính", "confirm_prompt"),
        _f("F22", 5, "fresh_sched_cancel", "namminh_noisy10", "hủy", "confirm_no"),
        _f("F23", 5, "fresh_timer_create", "namminh_normal", "hẹn giờ 5 phút nữa tắt đèn phòng ngủ", "confirm_prompt"),
        _f("F24", 5, "fresh_timer_cancel", "hoaimy_normal", "không", "confirm_no"),
        # Cat 6: Cross-connected rules (2)
        _f("F25", 6, "fresh_rule_create", "namminh_slow", "khi mở cửa chính thì bật đèn phòng khách", "confirm_prompt"),
        _f("F26", 6, "fresh_rule_cancel", "hoaimy_fast", "thôi", "confirm_no"),
        # Cat 7: Reset (2)
        _f("F27", 7, "fresh_reset_devices", "namminh_noisy10", "reset trạng thái thiết bị", "confirm_prompt"),
        _f("F28", 7, "fresh_reset_devices_ok", "namminh_normal", "được", "confirm_yes", expected_device_states={"main_door": "CLOSED", "living_room_light": "OFF", "bedroom_light": "OFF", "garden_pump": "OFF", "alarm_siren": "OFF", "speaker_amp": "OFF"}),
        # Cat 8: Confirmation edge flow (interrupt mid-confirm) (2)
        _f("F29", 8, "fresh_interrupt_stage", "hoaimy_normal", "10 phút nữa bật đèn phòng khách", "confirm_prompt"),
        _f("F30", 8, "fresh_interrupt_cmd", "hoaimy_fast", "bật đèn phòng ngủ", "immediate_device", expected_device_states={"bedroom_light": "ON"}),
        # Cat 9: Adversarial & edge cases (9)
        _f("F31", 9, "fresh_unk_curtain", "hoaimy_normal", "đóng rèm cửa", "clarify_no_action", pre_setup="clear_pending"),
        _f("F32", 9, "fresh_unk_fan", "hoaimy_fast", "bật quạt trần", "clarify_no_action"),
        _f("F33", 9, "fresh_unk_ac", "namminh_normal", "bật điều hòa", "clarify_no_action"),
        _f("F34", 9, "fresh_unk_rollerdoor", "namminh_slow", "mở cửa cuốn", "clarify_no_action"),
        _f("F35", 9, "fresh_ambig_door", "namminh_noisy10", "cửa chính", "clarify_no_action"),
        _f("F36", 9, "fresh_ambig_lights", "hoaimy_fast", "tất cả đèn", "clarify_no_action"),
        _f("F37", 9, "fresh_filler", "namminh_slow", "ờ à ừm", "clarify_no_action"),
        _f("F38", 9, "fresh_white_noise", "namminh_noisy10", "[PURE_WHITE_NOISE_FRESH]", "noise_no_action", audio_kind="pure_white_noise"),
        _f("F39", 9, "fresh_foreign_en", "hoaimy_normal", "turn on the lights", "foreign_no_action", lang="en"),
        # Cat 10: Session end (1)
        _f("F40", 10, "fresh_goodbye", "namminh_slow", "cảm ơn và tạm biệt", "small_talk"),
        # ------------------------------------------------------------------
        # Round-3 +40 Fresh Diverse Voices (F41..F80): elderly, kid, fast, Bac/Trung/Nam regional, reverb, babble10
        # ------------------------------------------------------------------
        # Cat 1: Greetings / Identity / Help (4)
        _f("F41", 1, "r3_greet_elderly", "elderly_slow_female", "chào buổi sáng cháu nhé", "small_talk"),
        _f("F42", 1, "r3_identity_kid", "kid_fast_high", "bạn là ai", "small_talk"),
        _f("F43", 1, "r3_help_nam", "regional_nam_style", "bạn làm được những gì", "small_talk"),
        _f("F44", 1, "r3_greet_trung", "regional_trung_reverb", "xin chào trợ lý", "small_talk"),
        # Cat 2: Direct device commands across all 6 devices + all_lights + multi + regional (12)
        _f("F45", 2, "r3_door_open_elderly", "elderly_slow_female", "mở cửa chính giúp bà ạ", "immediate_device", pre_setup="reset_devices_off", expected_device_states={"main_door": "OPEN"}),
        _f("F46", 2, "r3_door_close_kid", "kid_fast_high", "đóng cửa chính", "immediate_device", expected_device_states={"main_door": "CLOSED"}),
        _f("F47", 2, "r3_living_on_fast", "fast_male_bac", "bật đèn phòng khách", "immediate_device", expected_device_states={"living_room_light": "ON"}),
        _f("F48", 2, "r3_bedroom_on_nam", "regional_nam_style", "bật đèn phòng ngủ giùm nha", "immediate_device", expected_device_states={"bedroom_light": "ON"}),
        _f("F49", 2, "r3_all_lights_off_trung", "regional_trung_reverb", "tắt hết đèn", "immediate_device", expected_device_states={"living_room_light": "OFF", "bedroom_light": "OFF"}),
        _f("F50", 2, "r3_all_lights_on_babble", "noisy_babble10_female", "bật tất cả đèn", "immediate_device", expected_device_states={"living_room_light": "ON", "bedroom_light": "ON"}),
        _f("F51", 2, "r3_pump_on_elderly", "elderly_slow_female", "bật máy bơm tưới cây ạ", "immediate_device", expected_device_states={"garden_pump": "ON"}),
        _f("F52", 2, "r3_pump_off_nam", "regional_nam_style", "tắt máy bơm giùm tôi", "immediate_device", expected_device_states={"garden_pump": "OFF"}),
        _f("F53", 2, "r3_siren_on_fast", "fast_male_bac", "bật còi báo động", "immediate_device", expected_device_states={"alarm_siren": "ON"}),
        _f("F54", 2, "r3_siren_off_kid", "kid_fast_high", "tắt còi báo động", "immediate_device", expected_device_states={"alarm_siren": "OFF"}),
        _f("F55", 2, "r3_spk_on_trung", "regional_trung_reverb", "bật nguồn mạch loa", "immediate_device", expected_device_states={"speaker_amp": "ON"}),
        _f("F56", 2, "r3_multi_fast", "fast_male_bac", "tắt nguồn mạch loa và mở cửa chính", "immediate_device", expected_device_states={"speaker_amp": "OFF", "main_door": "OPEN"}),
        # Cat 3: Sensor & status readings (4)
        _f("F57", 3, "r3_temp_elderly", "elderly_slow_female", "nhiệt độ bây giờ là bao nhiêu", "sensor_query", pre_setup="set_sensors_known"),
        _f("F58", 3, "r3_soil_nam", "regional_nam_style", "độ ẩm đất hiện tại bao nhiêu", "sensor_query"),
        _f("F59", 3, "r3_door_status_fast", "fast_male_bac", "cửa chính đang mở hay đóng", "status_query"),
        _f("F60", 3, "r3_autopump_trung", "regional_trung_reverb", "chế độ bơm tự động đang thế nào", "status_query"),
        # Cat 4: Custom commands (4)
        _f("F61", 4, "r3_custom_create", "regional_nam_style", "tạo lệnh xem phim là tắt đèn phòng khách và bật nguồn mạch loa", "confirm_prompt"),
        _f("F62", 4, "r3_custom_ok", "fast_male_bac", "đồng ý", "confirm_yes"),
        _f("F63", 4, "r3_custom_del", "elderly_slow_female", "xóa lệnh xem phim", "confirm_prompt"),
        _f("F64", 4, "r3_custom_del_ok", "kid_fast_high", "ok", "confirm_yes"),
        # Cat 5: Schedules & timers (4)
        _f("F65", 5, "r3_sched_create", "fast_male_bac", "đặt lịch 8 giờ tối hằng ngày bật đèn phòng khách", "confirm_prompt"),
        _f("F66", 5, "r3_sched_cancel", "noisy_babble10_female", "hủy", "confirm_no"),
        _f("F67", 5, "r3_timer_create", "kid_fast_high", "hẹn giờ 10 phút nữa tắt đèn phòng ngủ", "confirm_prompt"),
        _f("F68", 5, "r3_timer_cancel", "elderly_slow_female", "thôi", "confirm_no"),
        # Cat 6: Cross-connected rules (2)
        _f("F69", 6, "r3_rule_soil", "regional_trung_reverb", "khi đất khô thì bật máy bơm tưới cây", "confirm_prompt"),
        _f("F70", 6, "r3_rule_cancel", "regional_nam_style", "không", "confirm_no"),
        # Cat 7: Reset (2)
        _f("F71", 7, "r3_reset_links", "fast_male_bac", "reset liên kết", "confirm_prompt"),
        _f("F72", 7, "r3_reset_cancel", "kid_fast_high", "hủy", "confirm_no"),
        # Cat 8: Confirmation edge flow (2)
        _f("F73", 8, "r3_interrupt_stage", "elderly_slow_female", "15 phút nữa tắt đèn phòng khách", "confirm_prompt"),
        _f("F74", 8, "r3_interrupt_cmd", "regional_nam_style", "đóng cửa chính", "immediate_device", expected_device_states={"main_door": "CLOSED"}),
        # Cat 9: Adversarial zero-false-action across diverse styles (5)
        _f("F75", 9, "r3_unk_curtain_nam", "regional_nam_style", "đóng rèm cửa", "clarify_no_action", pre_setup="clear_pending"),
        _f("F76", 9, "r3_unk_ac_babble", "noisy_babble10_female", "bật điều hòa", "clarify_no_action"),
        _f("F77", 9, "r3_ambig_light_elderly", "elderly_slow_female", "đèn phòng khách", "clarify_no_action"),
        _f("F78", 9, "r3_ambig_verb_kid", "kid_fast_high", "bật lên đi", "clarify_no_action"),
        _f("F79", 9, "r3_foreign_fr", "fast_male_bac", "bonjour ouvre la porte", "foreign_no_action", lang="fr"),
        # Cat 10: Session end (1)
        _f("F80", 10, "r3_goodbye_elderly", "elderly_slow_female", "tạm biệt bạn nhé", "small_talk"),
    ]


def _build_fresh_step_pcm16(step: JourneyStep, idx: int, fresh_cache_dir: pathlib.Path) -> np.ndarray:
    if step.audio_kind == "pure_white_noise":
        return synth_pure_white_noise(duration_sec=1.8, seed=9100 + idx)
    if step.lang != "vi":
        foreign_voice = "fr-FR-DeniseNeural" if step.lang == "fr" else "en-US-JennyNeural"
        return synthesize_edge_tts_speech(
            step.text,
            voice=foreign_voice,
            rate="+0%",
            pitch="+0Hz",
            cache_dir=fresh_cache_dir,
        )
    prof = FRESH_VOICE_PROFILES[step.persona]
    pcm = synthesize_edge_tts_speech(
        step.text,
        voice=prof["voice"],
        rate=prof["rate"],
        pitch=prof["pitch"],
        cache_dir=fresh_cache_dir,
    )
    if prof["degradation"] != "clean":
        pcm = apply_degradation(
            pcm,
            prof["degradation"],
            seed=9500 + idx,
            cache_dir=fresh_cache_dir,
        )
    return pcm


def _prewarm_fresh_audio_cache(
    fresh_steps: list[JourneyStep],
    fresh_cache_dir: pathlib.Path,
    log_file: pathlib.Path,
) -> dict[str, np.ndarray]:
    _log(f"Pre-synthesizing / loading {len(fresh_steps)} fresh edge-tts neural voice clips in {fresh_cache_dir}...", log_file)
    t0 = time.perf_counter()
    cache: dict[str, np.ndarray] = {}

    def _job(pair: tuple[int, JourneyStep]) -> tuple[str, np.ndarray]:
        i, st = pair
        return st.step_id, _build_fresh_step_pcm16(st, i, fresh_cache_dir)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        for sid, pcm in ex.map(_job, enumerate(fresh_steps)):
            cache[sid] = pcm
    _log(f"Fresh neural audio cache ready ({len(cache)} clips) in {time.perf_counter() - t0:.1f}s.", log_file)
    return cache


def _percentile(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    return round(float(np.percentile(np.array(vals, dtype=np.float64), p)), 1)


def _generate_summary_chart(
    summary: dict[str, Any],
    out_path: pathlib.Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Segoe UI", "Arial", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig = plt.figure(figsize=(16.5, 10.5), dpi=100, facecolor="#0f172a")
    gs = fig.add_gridspec(2, 2, height_ratios=[1.1, 1.05], width_ratios=[1.25, 1.0], hspace=0.38, wspace=0.25, left=0.06, right=0.97, top=0.88, bottom=0.07)

    # Header banner
    fig.suptitle(
        "Smart Home Voice Policy QA — Act-First, Vietnamese-Only E2E & Degradation Evaluation",
        fontsize=18,
        fontweight="bold",
        color="#f8fafc",
        y=0.96,
    )
    overall = summary["overall"]
    subtitle = (
        f"Total Runs: {overall['total_evals']} (Text: {overall['text_total']} | Clean Voice: {overall['clean_voice_total']} | Degraded Voice: {overall['degraded_voice_total']})   •   "
        f"Vietnamese-Only Output: {overall['vi_only_rate_pct']:.1f}%   •   "
        f"Confirm Policy: {overall['confirm_policy_rate_pct']:.1f}%   •   "
        f"False-Action Rate (Noise/Nonsense/Foreign): {overall['false_action_rate_pct']:.2f}%"
    )
    fig.text(0.5, 0.915, subtitle, ha="center", fontsize=11, color="#94a3b8")

    # Panel 1 (Top-Left): Action Correctness by Category (1..10) — Text vs Clean Voice
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor("#1e293b")
    cats = list(range(1, 11))
    cat_labels = [f"C{c}" for c in cats]
    txt_accs = [summary["by_category"][str(c)]["text_acc_pct"] for c in cats]
    cln_accs = [summary["by_category"][str(c)]["clean_voice_acc_pct"] for c in cats]
    x = np.arange(len(cats))
    w = 0.36
    b1 = ax1.bar(x - w / 2, txt_accs, width=w, label="Typed (/api/text_command)", color="#38bdf8")
    b2 = ax1.bar(x + w / 2, cln_accs, width=w, label="Clean Voice (Whisper STT)", color="#34d399")
    ax1.set_ylim(0, 114)
    ax1.set_xticks(x)
    ax1.set_xticklabels(cat_labels, color="#e2e8f0", fontsize=10, fontweight="bold")
    ax1.set_ylabel("Accuracy (%)", color="#cbd5e1", fontsize=10)
    ax1.set_title("Accuracy by Mandatory Coverage Category (C1–C10)", color="#f8fafc", fontsize=12, fontweight="bold", pad=10)
    ax1.tick_params(axis="y", colors="#cbd5e1")
    ax1.grid(axis="y", color="#334155", linestyle="--", alpha=0.6)
    ax1.legend(loc="lower right", facecolor="#0f172a", edgecolor="#334155", labelcolor="#f8fafc", fontsize=9)
    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width() / 2, h + 1.5, f"{h:.0f}%", ha="center", va="bottom", color="#e2e8f0", fontsize=8)

    # Panel 2 (Top-Right): Accuracy across Clean + 11 Audio Degradations
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor("#1e293b")
    deg_keys = [d for d in DEGRADATIONS if d in summary["by_degradation"]]
    deg_vals = [summary["by_degradation"][d]["acc_pct"] for d in deg_keys]
    y_pos = np.arange(len(deg_keys))
    colors = ["#34d399" if v >= 85 else ("#fbbf24" if v >= 70 else "#f87171") for v in deg_vals]
    bars2 = ax2.barh(y_pos, deg_vals, color=colors, height=0.68)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(deg_keys, color="#e2e8f0", fontsize=9)
    ax2.invert_yaxis()
    ax2.set_xlim(0, 115)
    ax2.set_xlabel("Action / Policy Accuracy (%)", color="#cbd5e1", fontsize=10)
    ax2.set_title("Real Whisper Voice Pipeline across 12 Audio Conditions", color="#f8fafc", fontsize=12, fontweight="bold", pad=10)
    ax2.tick_params(axis="x", colors="#cbd5e1")
    ax2.grid(axis="x", color="#334155", linestyle="--", alpha=0.6)
    for bar, v in zip(bars2, deg_vals):
        ax2.text(v + 1.5, bar.get_y() + bar.get_height() / 2, f"{v:.1f}%", va="center", color="#f8fafc", fontsize=8.5)

    # Panel 3 (Bottom-Left): Persona Accuracy + Latency Summary
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.set_facecolor("#1e293b")
    p_keys = list(summary["by_persona"].keys())
    p_txt = [summary["by_persona"][k]["text_acc_pct"] for k in p_keys]
    p_cln = [summary["by_persona"][k]["clean_voice_acc_pct"] for k in p_keys]
    px = np.arange(len(p_keys))
    ax3.bar(px - 0.18, p_txt, width=0.35, label="Typed", color="#818cf8")
    ax3.bar(px + 0.18, p_cln, width=0.35, label="Clean Voice", color="#22d3ee")
    ax3.set_ylim(0, 115)
    ax3.set_xticks(px)
    ax3.set_xticklabels(p_keys, color="#e2e8f0", fontsize=9, rotation=12)
    ax3.set_ylabel("Accuracy (%)", color="#cbd5e1", fontsize=10)
    ax3.set_title("Accuracy Across 6 Vietnamese User Personas", color="#f8fafc", fontsize=12, fontweight="bold", pad=10)
    ax3.tick_params(axis="y", colors="#cbd5e1")
    ax3.grid(axis="y", color="#334155", linestyle="--", alpha=0.6)
    ax3.legend(loc="lower right", facecolor="#0f172a", edgecolor="#334155", labelcolor="#f8fafc", fontsize=9)
    for i, (vt, vc) in enumerate(zip(p_txt, p_cln)):
        ax3.text(i - 0.18, vt + 1.5, f"{vt:.0f}%", ha="center", color="#e2e8f0", fontsize=8)
        ax3.text(i + 0.18, vc + 1.5, f"{vc:.0f}%", ha="center", color="#e2e8f0", fontsize=8)

    # Panel 4 (Bottom-Right): Key Policy & Latency KPI Table
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.set_facecolor("#1e293b")
    ax4.axis("off")
    ax4.set_title("Key Policy & Latency Metrics (Temp Server 8099)", color="#f8fafc", fontsize=12, fontweight="bold", pad=10)

    lat = summary["latency_ms"]
    rows = [
        ["Text E2E Accuracy (all 10 journeys)", f"{overall['text_acc_pct']:.1f}% ({overall['text_passed']}/{overall['text_total']})"],
        ["Clean Voice E2E Accuracy (Whisper STT)", f"{overall['clean_voice_acc_pct']:.1f}% ({overall['clean_voice_passed']}/{overall['clean_voice_total']})"],
        ["Degraded Voice Accuracy (11 conditions)", f"{overall['degraded_voice_acc_pct']:.1f}% ({overall['degraded_voice_passed']}/{overall['degraded_voice_total']})"],
        ["Confirmation-Policy Correctness", f"{overall['confirm_policy_rate_pct']:.1f}%"],
        ["Vietnamese-Only Output (langdetect+script)", f"{overall['vi_only_rate_pct']:.1f}%"],
        ["False-Action Rate (Noise/Nonsense/Foreign)", f"{overall['false_action_rate_pct']:.2f}% ({overall['false_action_count']}/{overall['adversarial_total']})"],
        ["Simple Cmd Latency — Text (p50 / p95)", f"{lat['simple_text_p50']} ms / {lat['simple_text_p95']} ms"],
        ["Simple Cmd Latency — Clean Voice (p50/p95)", f"{lat['simple_voice_clean_p50']} ms / {lat['simple_voice_clean_p95']} ms"],
        ["STT Model / Server Port", f"whisper-{summary['whisper_model']} / 127.0.0.1:{TEMP_PORT}"],
    ]
    tbl = ax4.table(
        cellText=rows,
        colLabels=["Metric", "Observed Value"],
        colWidths=[0.58, 0.42],
        cellLoc="left",
        loc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9.5)
    tbl.scale(1.0, 1.65)
    for (r_idx, c_idx), cell in tbl.get_celld().items():
        cell.set_edgecolor("#334155")
        if r_idx == 0:
            cell.set_facecolor("#0284c7")
            cell.set_text_props(color="#ffffff", fontweight="bold")
        else:
            cell.set_facecolor("#0f172a" if r_idx % 2 == 1 else "#1e293b")
            cell.set_text_props(color="#e2e8f0" if c_idx == 0 else "#38bdf8", fontweight=("bold" if c_idx == 1 else "normal"))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)


def run_suite(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = pathlib.Path(args.run_dir)
    audio_cache_dir = pathlib.Path(args.audio_cache_dir)
    output_dir = run_dir / args.output_subdir
    temp_data_dir = run_dir / "temp_data"
    temp_log_dir = run_dir / "temp_logs"
    screenshots_dir = run_dir / "screenshots"
    fresh_cache_dir = run_dir / "voice_tests" / "fresh_audio_cache"

    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    progress_log = output_dir / "progress.log"
    if progress_log.exists():
        progress_log.unlink()

    stt_mode = str(args.stt_mode or "gemini").strip().lower()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["SMARTHOME_DATA_DIR"] = str(temp_data_dir)
    env["SMARTHOME_LOG_DIR"] = str(temp_log_dir)
    env["SMARTHOME_SKIP_PREWARM"] = "1"
    env["SMARTHOME_AOEDE_CACHE_ONLY"] = "1"
    env["SMARTHOME_STT_MODE"] = stt_mode
    env["SMARTHOME_SESSION_SECRET"] = SESSION_SECRET
    env["SMARTHOME_WHISPER_MODEL"] = args.whisper_model
    env["GMAIL_APP_PASSWORD"] = ""
    env["SMTP_PASSWORD"] = ""

    if stt_mode == "offline":
        env["SIMULATOR_OFFLINE_SANDBOX"] = "1"
        env.pop("SMARTHOME_ENV_FILE", None)
        env.pop("GEMINI_API_KEY", None)
    else:
        env.pop("SIMULATOR_OFFLINE_SANDBOX", None)
        env["SMARTHOME_GEMINI_PACE_RPM"] = os.environ.get("SMARTHOME_GEMINI_PACE_RPM", "12")
        if args.env_file:
            env["SMARTHOME_ENV_FILE"] = str(args.env_file)

    journeys = build_user_journeys()
    all_steps = flatten_steps(journeys)
    deg_steps_all = get_degraded_eval_steps(journeys)
    if args.degraded_limit > 0 and len(deg_steps_all) > args.degraded_limit:
        # Stratified round-robin selection across categories 1..10 so every category, noise & foreign stays included
        by_cat_deg: dict[int, list[JourneyStep]] = defaultdict(list)
        for st in deg_steps_all:
            by_cat_deg[st.category].append(st)
        selected: list[JourneyStep] = []
        cat_order = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        while len(selected) < args.degraded_limit:
            added_any = False
            for c in cat_order:
                bucket = by_cat_deg.get(c)
                if bucket and len(selected) < args.degraded_limit:
                    selected.append(bucket.pop(0))
                    added_any = True
            if not added_any:
                break
        deg_steps = selected
    else:
        deg_steps = deg_steps_all

    run_fresh = bool(args.include_fresh_voices) or (args.phase == "fresh")
    fresh_steps = build_fresh_voice_steps() if run_fresh else []

    _log(
        f"Starting Voice Policy QA Suite: stt_mode={stt_mode}, phase={args.phase}, "
        f"{len(journeys)} journeys ({len(all_steps)} utterances), "
        f"{len(deg_steps)} degraded x 11 = {len(deg_steps) * 11}, "
        f"fresh_voices={len(fresh_steps)}, whisper={args.whisper_model}, "
        f"min_interval_ms={args.min_interval_ms}, output={output_dir}",
        progress_log,
    )

    sessions = _seed_temp_db_and_sessions(temp_data_dir, temp_log_dir, env)
    _log("Seeded isolated temp_data DB & throwaway Tier 1/2/3 sessions.", progress_log)

    audio_cache: dict[str, np.ndarray] = {}
    if args.phase in ("all", "clean", "degraded"):
        audio_cache = _prewarm_audio_cache(all_steps, audio_cache_dir, progress_log)

    fresh_audio_cache: dict[str, np.ndarray] = {}
    if fresh_steps:
        fresh_audio_cache = _prewarm_fresh_audio_cache(fresh_steps, fresh_cache_dir, progress_log)

    proc = _start_temp_server(env, temp_log_dir, log_name=f"uvicorn_8099_{stt_mode}.log")
    _log(f"Temp server healthy on {BASE_URL} (PID={proc.pid}, stt_mode={stt_mode}).", progress_log)

    http = requests.Session()
    owner_headers = {"X-Session-Token": sessions["tier1"]}

    def _headers_for(step: JourneyStep, rotated_owner: bool = False) -> dict[str, str]:
        if step.tier == 1:
            return {"X-Session-Token": sessions["tier1_resume"] if rotated_owner else sessions["tier1"]}
        if step.tier == 2:
            return {"X-Session-Token": sessions["tier2"]}
        return {"X-Session-Token": sessions["tier3"]}

    min_interval_s = max(0.0, float(args.min_interval_ms or 0) / 1000.0)
    if min_interval_s >= 2.5:
        http.headers.update({"Connection": "close"})
    last_voice_ts = 0.0

    def _pace_voice() -> None:
        nonlocal last_voice_ts
        if min_interval_s > 0.0 and last_voice_ts > 0.0:
            rem = min_interval_s - (time.perf_counter() - last_voice_ts)
            if rem > 0.0:
                time.sleep(rem)
        last_voice_ts = time.perf_counter()

    voice_engine_live: dict[str, int] = defaultdict(int)
    all_records: list[dict[str, Any]] = []
    journey_summaries: dict[str, dict[str, Any]] = {}
    warmed = False

    def _warm_stt_once() -> None:
        nonlocal warmed
        if warmed:
            return
        _reset_all_devices_off(http, owner_headers)
        _cancel_all_timers_and_schedules(http, owner_headers, temp_data_dir)
        warm_pcm = audio_cache.get("J01_53")
        if warm_pcm is None:
            warm_pcm = synthesize_persona_speech("xin chào", persona="bac_male", lang="vi", cache_dir=fresh_cache_dir)
        t_w = time.perf_counter()
        _pace_voice()
        w_resp = http.post(
            f"{BASE_URL}/api/voice_command",
            headers={"X-Session-Token": sessions["tier1_deg"]},
            json={"wav_b64": pcm16_to_wav_b64(warm_pcm), "source": "qa_warmup"},
            timeout=90.0,
        )
        w_body = w_resp.json() if w_resp.headers.get("content-type", "").startswith("application/json") else {}
        _log(
            f"  STT warmed on 8099 ('xin chào' -> {w_body.get('recognized_text')!r}, "
            f"stt_engine={w_body.get('stt_engine')!r}, stt_ms={w_body.get('stt_ms')}) "
            f"in {time.perf_counter() - t_w:.1f}s",
            progress_log,
        )
        warmed = True

    try:
        # --------------------------------------------------------------
        # PHASE A: Full E2E Journeys via POST /api/text_command
        # --------------------------------------------------------------
        if args.phase in ("all", "text"):
            _log(f"=== PHASE A: Running {len(all_steps)} utterances via /api/text_command ===", progress_log)
            for j in journeys:
                _cancel_all_timers_and_schedules(http, owner_headers, temp_data_dir)
                _reset_all_devices_off(http, owner_headers)
                _clear_pending_in_temp_db(temp_data_dir)
                rotated = False
                j_pass = 0
                j_fail = 0
                for st in j.steps:
                    if st.audio_kind in ("pure_white_noise", "pure_babble_noise"):
                        payload_txt = "ờ à"
                    else:
                        payload_txt = st.text
                    if st.pre_setup == "rotate_owner_session":
                        rotated = True
                    else:
                        _run_pre_setup(st.pre_setup, http, owner_headers, temp_data_dir)

                    hdrs = _headers_for(st, rotated_owner=rotated)
                    before = _get_device_states(http, owner_headers)
                    t0 = time.perf_counter()
                    resp = http.post(
                        f"{BASE_URL}/api/text_command",
                        headers=hdrs,
                        json={"text": payload_txt},
                        timeout=30.0,
                    )
                    lat_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    post_ok, post_note = _run_post_verify(st.post_verify, http, owner_headers)
                    after = _get_device_states(http, owner_headers)

                    ev = _evaluate_response(
                        st,
                        status_code=resp.status_code,
                        body=body,
                        before_states=before,
                        after_states=after,
                        post_ok=post_ok,
                        post_note=post_note,
                        mode="text",
                    )
                    if ev["passed"]:
                        j_pass += 1
                    else:
                        j_fail += 1
                    all_records.append({
                        "mode": "text",
                        "degradation": "text",
                        "journey_id": j.journey_id,
                        "step_id": st.step_id,
                        "category": st.category,
                        "subcat": st.subcat,
                        "persona": st.persona,
                        "tier": st.tier,
                        "input_text": st.text,
                        "recognized_text": payload_txt,
                        "expected_behavior": st.expected_behavior,
                        "http_status": resp.status_code,
                        "reply": str(body.get("exact_spoken_reply") or body.get("reply") or body.get("error") or ""),
                        "requires_confirmation": bool(body.get("requires_confirmation")),
                        "executed": bool(body.get("executed")),
                        "rbac_blocked": bool(body.get("rbac_blocked")),
                        "stt_engine": "text",
                        "stt_ms": 0.0,
                        "latency_ms": lat_ms,
                        **ev,
                    })
                journey_summaries[j.journey_id] = {
                    "title": j.title,
                    "persona": j.persona,
                    "tier": j.tier,
                    "text_passed": j_pass,
                    "text_total": j_pass + j_fail,
                    "clean_voice_passed": 0,
                    "clean_voice_total": 0,
                }
                _log(f"  [TEXT] {j.journey_id}: {j_pass}/{j_pass + j_fail} passed", progress_log)

        # --------------------------------------------------------------
        # PHASE B: Full E2E Journeys via POST /api/voice_command (CLEAN WAV, NO transcript hint!)
        # --------------------------------------------------------------
        if args.phase in ("all", "clean"):
            _log(
                f"=== PHASE B: Running {len(all_steps)} CLEAN WAVs via /api/voice_command (stt_mode={stt_mode}) ===",
                progress_log,
            )
            _warm_stt_once()

            done_cnt = 0
            t_phase_b = time.perf_counter()
            for j in journeys:
                _cancel_all_timers_and_schedules(http, owner_headers, temp_data_dir)
                _reset_all_devices_off(http, owner_headers)
                _clear_pending_in_temp_db(temp_data_dir)
                rotated = False
                j_pass = 0
                j_fail = 0
                for st in j.steps:
                    if st.pre_setup == "rotate_owner_session":
                        rotated = True
                    else:
                        _run_pre_setup(st.pre_setup, http, owner_headers, temp_data_dir)

                    hdrs = _headers_for(st, rotated_owner=rotated)
                    before = _get_device_states(http, owner_headers)
                    wav_b64 = pcm16_to_wav_b64(audio_cache[st.step_id])
                    _pace_voice()
                    t0 = time.perf_counter()
                    resp = http.post(
                        f"{BASE_URL}/api/voice_command",
                        headers=hdrs,
                        json={"wav_b64": wav_b64, "source": "qa_voice_clean"},
                        timeout=90.0,
                    )
                    lat_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    post_ok, post_note = _run_post_verify(st.post_verify, http, owner_headers)
                    after = _get_device_states(http, owner_headers)

                    stt_eng = str(body.get("stt_engine") or "")
                    stt_ms = round(float(body.get("stt_ms") or 0.0), 1)
                    voice_engine_live[stt_eng or "unknown"] += 1

                    ev = _evaluate_response(
                        st,
                        status_code=resp.status_code,
                        body=body,
                        before_states=before,
                        after_states=after,
                        post_ok=post_ok,
                        post_note=post_note,
                        mode="voice_clean",
                    )
                    if ev["passed"]:
                        j_pass += 1
                    else:
                        j_fail += 1
                    done_cnt += 1
                    all_records.append({
                        "mode": "voice_clean",
                        "degradation": "clean",
                        "journey_id": j.journey_id,
                        "step_id": st.step_id,
                        "category": st.category,
                        "subcat": st.subcat,
                        "persona": st.persona,
                        "tier": st.tier,
                        "input_text": st.text,
                        "recognized_text": str(body.get("recognized_text") or body.get("transcript") or ""),
                        "expected_behavior": st.expected_behavior,
                        "http_status": resp.status_code,
                        "reply": str(body.get("exact_spoken_reply") or body.get("reply") or body.get("error") or ""),
                        "requires_confirmation": bool(body.get("requires_confirmation")),
                        "executed": bool(body.get("executed")),
                        "rbac_blocked": bool(body.get("rbac_blocked")),
                        "stt_engine": stt_eng,
                        "stt_ms": stt_ms,
                        "latency_ms": lat_ms,
                        **ev,
                    })
                    if done_cnt % 15 == 0:
                        elapsed = time.perf_counter() - t_phase_b
                        rate = elapsed / done_cnt
                        eta = rate * (len(all_steps) - done_cnt)
                        _log(
                            f"  [CLEAN VOICE] {done_cnt}/{len(all_steps)} done ({rate:.2f}s/clip, ETA {eta:.0f}s) "
                            f"engines={dict(voice_engine_live)}",
                            progress_log,
                        )
                if j.journey_id in journey_summaries:
                    journey_summaries[j.journey_id]["clean_voice_passed"] = j_pass
                    journey_summaries[j.journey_id]["clean_voice_total"] = j_pass + j_fail
                else:
                    journey_summaries[j.journey_id] = {
                        "title": j.title,
                        "persona": j.persona,
                        "tier": j.tier,
                        "text_passed": 0,
                        "text_total": 0,
                        "clean_voice_passed": j_pass,
                        "clean_voice_total": j_pass + j_fail,
                    }
                _log(f"  [CLEAN VOICE] {j.journey_id}: {j_pass}/{j_pass + j_fail} passed", progress_log)

        # --------------------------------------------------------------
        # PHASE C: ALL 11 Audio Degradations via POST /api/voice_command (NO transcript hint!)
        # --------------------------------------------------------------
        if args.phase in ("all", "degraded"):
            _warm_stt_once()
            _cancel_all_timers_and_schedules(http, owner_headers, temp_data_dir)
            degs_to_run = [d for d in DEGRADATIONS if d != "clean"]
            total_deg = len(degs_to_run) * len(deg_steps)
            _log(
                f"=== PHASE C: Running {total_deg} DEGRADED WAVs ({len(degs_to_run)} degradations x {len(deg_steps)} clips) ===",
                progress_log,
            )
            t_phase_c = time.perf_counter()
            done_deg = 0
            for deg_idx, deg_name in enumerate(degs_to_run):
                deg_pass = 0
                deg_false = 0
                for st_idx, st in enumerate(deg_steps):
                    _reset_all_devices_off(http, owner_headers)
                    _clear_pending_in_temp_db(temp_data_dir)
                    if st.pre_setup and st.pre_setup not in ("rotate_owner_session", "expire_pending_confirmations"):
                        _run_pre_setup(st.pre_setup, http, owner_headers, temp_data_dir)

                    base_pcm = audio_cache[st.step_id]
                    deg_pcm = apply_degradation(
                        base_pcm,
                        deg_name,
                        seed=5000 + deg_idx * 100 + st_idx,
                        cache_dir=audio_cache_dir,
                    )
                    hdrs = (
                        {"X-Session-Token": sessions["tier1_deg"]}
                        if st.tier == 1
                        else _headers_for(st, rotated_owner=False)
                    )
                    before = _get_device_states(http, owner_headers)
                    _pace_voice()
                    t0 = time.perf_counter()
                    resp = http.post(
                        f"{BASE_URL}/api/voice_command",
                        headers=hdrs,
                        json={"wav_b64": pcm16_to_wav_b64(deg_pcm), "source": f"qa_deg_{deg_name}"},
                        timeout=90.0,
                    )
                    lat_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    after = _get_device_states(http, owner_headers)

                    stt_eng = str(body.get("stt_engine") or "")
                    stt_ms = round(float(body.get("stt_ms") or 0.0), 1)
                    voice_engine_live[stt_eng or "unknown"] += 1

                    ev = _evaluate_response(
                        st,
                        status_code=resp.status_code,
                        body=body,
                        before_states=before,
                        after_states=after,
                        post_ok=True,
                        post_note="",
                        mode=f"voice_{deg_name}",
                    )
                    if ev["passed"]:
                        deg_pass += 1
                    if ev["false_action"]:
                        deg_false += 1
                    done_deg += 1
                    all_records.append({
                        "mode": "voice_degraded",
                        "degradation": deg_name,
                        "journey_id": st.journey_id,
                        "step_id": st.step_id,
                        "category": st.category,
                        "subcat": st.subcat,
                        "persona": st.persona,
                        "tier": st.tier,
                        "input_text": st.text,
                        "recognized_text": str(body.get("recognized_text") or body.get("transcript") or ""),
                        "expected_behavior": st.expected_behavior,
                        "http_status": resp.status_code,
                        "reply": str(body.get("exact_spoken_reply") or body.get("reply") or body.get("error") or ""),
                        "requires_confirmation": bool(body.get("requires_confirmation")),
                        "executed": bool(body.get("executed")),
                        "rbac_blocked": bool(body.get("rbac_blocked")),
                        "stt_engine": stt_eng,
                        "stt_ms": stt_ms,
                        "latency_ms": lat_ms,
                        **ev,
                    })
                elapsed = time.perf_counter() - t_phase_c
                rate = elapsed / max(1, done_deg)
                eta = rate * (total_deg - done_deg)
                _log(
                    f"  [DEGRADED:{deg_name:14s}] {deg_pass}/{len(deg_steps)} passed, false_actions={deg_false} "
                    f"(ETA {eta:.0f}s) engines={dict(voice_engine_live)}",
                    progress_log,
                )

        # --------------------------------------------------------------
        # PHASE D: Fresh Vietnamese Neural Voices (edge-tts HoaiMy & NamMinh)
        # --------------------------------------------------------------
        if fresh_steps:
            _warm_stt_once()
            _cancel_all_timers_and_schedules(http, owner_headers, temp_data_dir)
            _reset_all_devices_off(http, owner_headers)
            _clear_pending_in_temp_db(temp_data_dir)
            _log(
                f"=== PHASE D: Running {len(fresh_steps)} FRESH NEURAL VOICE WAVs (edge-tts HoaiMy & NamMinh) ===",
                progress_log,
            )
            f_pass = 0
            f_false = 0
            t_phase_d = time.perf_counter()
            for idx_f, st in enumerate(fresh_steps, start=1):
                if st.pre_setup:
                    _run_pre_setup(st.pre_setup, http, owner_headers, temp_data_dir)
                before = _get_device_states(http, owner_headers)
                wav_b64 = pcm16_to_wav_b64(fresh_audio_cache[st.step_id])
                _pace_voice()
                t0 = time.perf_counter()
                resp = http.post(
                    f"{BASE_URL}/api/voice_command",
                    headers=owner_headers,
                    json={"wav_b64": wav_b64, "source": f"qa_fresh_{st.persona}"},
                    timeout=90.0,
                )
                lat_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                after = _get_device_states(http, owner_headers)

                stt_eng = str(body.get("stt_engine") or "")
                stt_ms = round(float(body.get("stt_ms") or 0.0), 1)
                voice_engine_live[stt_eng or "unknown"] += 1

                prof_deg = (
                    FRESH_VOICE_PROFILES.get(st.persona, {}).get("degradation", "clean")
                    if st.audio_kind == "speech" and st.lang == "vi"
                    else ("noise" if st.audio_kind != "speech" else "foreign")
                )
                ev = _evaluate_response(
                    st,
                    status_code=resp.status_code,
                    body=body,
                    before_states=before,
                    after_states=after,
                    post_ok=True,
                    post_note="",
                    mode="voice_fresh",
                )
                if ev["passed"]:
                    f_pass += 1
                if ev["false_action"]:
                    f_false += 1
                all_records.append({
                    "mode": "voice_fresh",
                    "degradation": f"fresh_{prof_deg}",
                    "journey_id": st.journey_id,
                    "step_id": st.step_id,
                    "category": st.category,
                    "subcat": st.subcat,
                    "persona": st.persona,
                    "tier": st.tier,
                    "input_text": st.text,
                    "recognized_text": str(body.get("recognized_text") or body.get("transcript") or ""),
                    "expected_behavior": st.expected_behavior,
                    "http_status": resp.status_code,
                    "reply": str(body.get("exact_spoken_reply") or body.get("reply") or body.get("error") or ""),
                    "requires_confirmation": bool(body.get("requires_confirmation")),
                    "executed": bool(body.get("executed")),
                    "rbac_blocked": bool(body.get("rbac_blocked")),
                    "stt_engine": stt_eng,
                    "stt_ms": stt_ms,
                    "latency_ms": lat_ms,
                    **ev,
                })
                if idx_f % 10 == 0 or idx_f == len(fresh_steps):
                    elapsed = time.perf_counter() - t_phase_d
                    _log(
                        f"  [FRESH VOICES] {idx_f}/{len(fresh_steps)} done ({f_pass}/{idx_f} passed, "
                        f"false_actions={f_false}, {elapsed:.1f}s) engines={dict(voice_engine_live)}",
                        progress_log,
                    )
    finally:
        http.close()
        _stop_process_tree(proc)
        _log("Stopped temp server on port 8099 cleanly.", progress_log)

    # ------------------------------------------------------------------
    # AGGREGATE METRICS & COVERAGE MATRIX
    # ------------------------------------------------------------------
    txt_recs = [r for r in all_records if r["mode"] == "text"]
    cln_recs = [r for r in all_records if r["mode"] == "voice_clean"]
    deg_recs = [r for r in all_records if r["mode"] == "voice_degraded"]
    frsh_recs = [r for r in all_records if r["mode"] == "voice_fresh"]
    voice_recs = cln_recs + deg_recs + frsh_recs

    adv_behaviors = {"clarify_no_action", "noise_no_action", "foreign_no_action"}
    adv_recs = [r for r in all_records if r["expected_behavior"] in adv_behaviors]
    false_acts = [r for r in adv_recs if r["false_action"]]

    def _pct(num: int, den: int) -> float:
        return round(100.0 * num / den, 2) if den > 0 else 0.0

    by_category: dict[str, Any] = {}
    coverage_matrix: list[dict[str, Any]] = []
    for cat in range(1, 11):
        ct = [r for r in txt_recs if r["category"] == cat]
        cc = [r for r in cln_recs if r["category"] == cat]
        cd = [r for r in deg_recs if r["category"] == cat]
        cf = [r for r in frsh_recs if r["category"] == cat]
        ct_p = sum(1 for r in ct if r["passed"])
        cc_p = sum(1 for r in cc if r["passed"])
        cd_p = sum(1 for r in cd if r["passed"])
        cf_p = sum(1 for r in cf if r["passed"])
        entry = {
            "category": cat,
            "name": COVERAGE_CATEGORIES[cat],
            "text_passed": ct_p,
            "text_total": len(ct),
            "text_acc_pct": _pct(ct_p, len(ct)),
            "clean_voice_passed": cc_p,
            "clean_voice_total": len(cc),
            "clean_voice_acc_pct": _pct(cc_p, len(cc)),
            "degraded_voice_passed": cd_p,
            "degraded_voice_total": len(cd),
            "degraded_voice_acc_pct": _pct(cd_p, len(cd)),
            "fresh_voice_passed": cf_p,
            "fresh_voice_total": len(cf),
            "fresh_voice_acc_pct": _pct(cf_p, len(cf)),
        }
        by_category[str(cat)] = entry
        coverage_matrix.append(entry)

    by_degradation: dict[str, Any] = {}
    for deg_name in DEGRADATIONS:
        dr = [
            r for r in all_records
            if r["mode"] in ("voice_clean", "voice_degraded") and r["degradation"] == deg_name
        ]
        if not dr:
            continue
        dp = sum(1 for r in dr if r["passed"])
        df = sum(1 for r in dr if r["false_action"])
        dvi = sum(1 for r in dr if r["vi_only_ok"])
        by_degradation[deg_name] = {
            "passed": dp,
            "total": len(dr),
            "acc_pct": _pct(dp, len(dr)),
            "false_actions": df,
            "vi_only_pct": _pct(dvi, len(dr)),
            "latency_p50_ms": _percentile([r["latency_ms"] for r in dr], 50),
            "latency_p95_ms": _percentile([r["latency_ms"] for r in dr], 95),
        }

    by_persona: dict[str, Any] = {}
    for persona in sorted({r["persona"] for r in all_records}):
        pt = [r for r in txt_recs if r["persona"] == persona]
        pc = [r for r in cln_recs if r["persona"] == persona]
        pf = [r for r in frsh_recs if r["persona"] == persona]
        pt_p = sum(1 for r in pt if r["passed"])
        pc_p = sum(1 for r in pc if r["passed"])
        pf_p = sum(1 for r in pf if r["passed"])
        by_persona[persona] = {
            "text_passed": pt_p,
            "text_total": len(pt),
            "text_acc_pct": _pct(pt_p, len(pt)),
            "clean_voice_passed": pc_p,
            "clean_voice_total": len(pc),
            "clean_voice_acc_pct": _pct(pc_p, len(pc)),
            "fresh_voice_passed": pf_p,
            "fresh_voice_total": len(pf),
            "fresh_voice_acc_pct": _pct(pf_p, len(pf)),
        }

    def _engine_counts(recs: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for r in recs:
            eng = str(r.get("stt_engine") or "unknown")
            counts[eng] += 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    stt_engine_counts = {
        "all_voice": _engine_counts(voice_recs),
        "voice_clean": _engine_counts(cln_recs),
        "voice_degraded": _engine_counts(deg_recs),
        "voice_fresh": _engine_counts(frsh_recs),
    }

    def _split_served_stats(recs: list[dict[str, Any]]) -> dict[str, Any]:
        gem = [r for r in recs if str(r.get("stt_engine") or "").startswith("gemini:")]
        loc = [r for r in recs if str(r.get("stt_engine") or "").startswith("cascade_local:")]
        fb = [r for r in recs if "offline_fallback" in str(r.get("stt_engine") or "") or "offline_no_key" in str(r.get("stt_engine") or "")]
        gate = [r for r in recs if str(r.get("stt_engine") or "") in ("acoustic_gate", "babble_guard") or ":babble_guard" in str(r.get("stt_engine") or "")]
        other = [r for r in recs if r not in gem and r not in loc and r not in fb and r not in gate]
        return {
            "total": len(recs),
            "cascade_local_served": len(loc),
            "cascade_local_passed": sum(1 for r in loc if r["passed"]),
            "cascade_local_acc_pct": _pct(sum(1 for r in loc if r["passed"]), len(loc)),
            "gemini_served": len(gem),
            "gemini_passed": sum(1 for r in gem if r["passed"]),
            "gemini_acc_pct": _pct(sum(1 for r in gem if r["passed"]), len(gem)),
            "gemini_calls_per_100": round(100.0 * len(gem) / max(1, len(recs)), 2),
            "fallback_served": len(fb),
            "fallback_passed": sum(1 for r in fb if r["passed"]),
            "fallback_acc_pct": _pct(sum(1 for r in fb if r["passed"]), len(fb)),
            "acoustic_gate_count": len(gate),
            "other_count": len(other),
        }

    served_breakdown = {
        "all_voice": _split_served_stats(voice_recs),
        "voice_clean": _split_served_stats(cln_recs),
        "voice_clean_c2": _split_served_stats([r for r in cln_recs if r["category"] == 2]),
        "voice_degraded": _split_served_stats(deg_recs),
        "voice_fresh": _split_served_stats(frsh_recs),
    }

    frsh_passed = sum(1 for r in frsh_recs if r["passed"])
    frsh_vi_ok = sum(1 for r in frsh_recs if r["vi_only_ok"])
    frsh_conf_ok = sum(1 for r in frsh_recs if r["confirm_policy_ok"])
    frsh_adv = [r for r in frsh_recs if r["expected_behavior"] in adv_behaviors]
    frsh_false = [r for r in frsh_adv if r["false_action"]]
    fresh_by_profile: dict[str, Any] = {}
    for prof in sorted({r["persona"] for r in frsh_recs}):
        pr = [r for r in frsh_recs if r["persona"] == prof]
        pp = sum(1 for r in pr if r["passed"])
        pf_cnt = sum(1 for r in pr if r["false_action"])
        fresh_by_profile[prof] = {
            "passed": pp,
            "total": len(pr),
            "acc_pct": _pct(pp, len(pr)),
            "false_actions": pf_cnt,
            "latency_p50_ms": _percentile([r["latency_ms"] for r in pr], 50),
            "latency_p95_ms": _percentile([r["latency_ms"] for r in pr], 95),
        }
    fresh_voices_summary: dict[str, Any] = {
        "passed": frsh_passed,
        "total": len(frsh_recs),
        "acc_pct": _pct(frsh_passed, len(frsh_recs)),
        "vi_only_rate_pct": _pct(frsh_vi_ok, len(frsh_recs)),
        "confirm_policy_rate_pct": _pct(frsh_conf_ok, len(frsh_recs)),
        "false_action_count": len(frsh_false),
        "adversarial_total": len(frsh_adv),
        "false_action_rate_pct": _pct(len(frsh_false), len(frsh_adv)),
        "latency_p50_ms": _percentile([r["latency_ms"] for r in frsh_recs], 50),
        "latency_p95_ms": _percentile([r["latency_ms"] for r in frsh_recs], 95),
        "by_profile": fresh_by_profile,
        "failures": [r for r in frsh_recs if not r["passed"]],
    }

    simple_txt_lats = [r["latency_ms"] for r in txt_recs if r["expected_behavior"] == "immediate_device"]
    simple_cln_lats = [r["latency_ms"] for r in cln_recs if r["expected_behavior"] == "immediate_device"]
    simple_frsh_lats = [r["latency_ms"] for r in frsh_recs if r["expected_behavior"] == "immediate_device"]

    vi_ok_total = sum(1 for r in all_records if r["vi_only_ok"])
    conf_ok_total = sum(1 for r in all_records if r["confirm_policy_ok"])
    txt_conf_ok = sum(1 for r in txt_recs if r["confirm_policy_ok"])
    cln_conf_ok = sum(1 for r in cln_recs if r["confirm_policy_ok"])
    deg_conf_ok = sum(1 for r in deg_recs if r["confirm_policy_ok"])
    txt_passed = sum(1 for r in txt_recs if r["passed"])
    cln_passed = sum(1 for r in cln_recs if r["passed"])
    deg_passed = sum(1 for r in deg_recs if r["passed"])

    failures = [r for r in all_records if not r["passed"]]
    summary: dict[str, Any] = {
        "stt_mode": stt_mode,
        "whisper_model": args.whisper_model,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "overall": {
            "total_evals": len(all_records),
            "text_passed": txt_passed,
            "text_total": len(txt_recs),
            "text_acc_pct": _pct(txt_passed, len(txt_recs)),
            "clean_voice_passed": cln_passed,
            "clean_voice_total": len(cln_recs),
            "clean_voice_acc_pct": _pct(cln_passed, len(cln_recs)),
            "degraded_voice_passed": deg_passed,
            "degraded_voice_total": len(deg_recs),
            "degraded_voice_acc_pct": _pct(deg_passed, len(deg_recs)),
            "fresh_voice_passed": frsh_passed,
            "fresh_voice_total": len(frsh_recs),
            "fresh_voice_acc_pct": _pct(frsh_passed, len(frsh_recs)),
            "vi_only_ok": vi_ok_total,
            "vi_only_rate_pct": _pct(vi_ok_total, len(all_records)),
            "confirm_policy_ok": conf_ok_total,
            "confirm_policy_rate_pct": _pct(conf_ok_total, len(all_records)),
            "text_confirm_policy_rate_pct": _pct(txt_conf_ok, len(txt_recs)),
            "clean_voice_confirm_policy_rate_pct": _pct(cln_conf_ok, len(cln_recs)),
            "degraded_voice_confirm_policy_rate_pct": _pct(deg_conf_ok, len(deg_recs)),
            "fresh_voice_confirm_policy_rate_pct": _pct(frsh_conf_ok, len(frsh_recs)),
            "false_action_count": len(false_acts),
            "adversarial_total": len(adv_recs),
            "false_action_rate_pct": _pct(len(false_acts), len(adv_recs)),
            "total_failures": len(failures),
        },
        "latency_ms": {
            "simple_text_p50": _percentile(simple_txt_lats, 50),
            "simple_text_p95": _percentile(simple_txt_lats, 95),
            "simple_voice_clean_p50": _percentile(simple_cln_lats, 50),
            "simple_voice_clean_p95": _percentile(simple_cln_lats, 95),
            "simple_voice_fresh_p50": _percentile(simple_frsh_lats, 50),
            "simple_voice_fresh_p95": _percentile(simple_frsh_lats, 95),
        },
        "stt_engine_counts": stt_engine_counts,
        "served_breakdown": served_breakdown,
        "fresh_voices": fresh_voices_summary,
        "by_category": by_category,
        "by_degradation": by_degradation,
        "by_persona": by_persona,
        "failure_samples": failures[:100],
    }

    # Save raw JSON & CSV artifacts
    (output_dir / "results.json").write_text(json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "metrics_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "journey_results.json").write_text(json.dumps(journey_summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "coverage_matrix.json").write_text(json.dumps(coverage_matrix, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_fields = [
        "mode", "degradation", "journey_id", "step_id", "category", "subcat", "persona", "tier",
        "input_text", "recognized_text", "expected_behavior", "http_status", "reply",
        "requires_confirmation", "executed", "rbac_blocked", "stt_engine", "stt_ms", "latency_ms",
        "passed", "action_ok", "confirm_policy_ok", "vi_only_ok", "vi_reason", "false_action", "reasons",
    ]
    with (output_dir / "results.csv").open("w", encoding="utf-8-sig", newline="") as cf:
        writer = csv.DictWriter(cf, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_records)

    if args.generate_chart and all_records:
        chart_path = screenshots_dir / f"65_voice_test_summary_{stt_mode}.png"
        _generate_summary_chart(summary, chart_path)
        _log(f"Generated summary chart: {chart_path}", progress_log)

    _log("=== SUMMARY ===", progress_log)
    _log(json.dumps(summary["overall"], ensure_ascii=False, indent=2), progress_log)
    _log(f"Latency ms: {summary['latency_ms']}", progress_log)
    _log(f"STT engine counts: {json.dumps(stt_engine_counts['all_voice'], ensure_ascii=False)}", progress_log)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Voice Policy E2E & Degradation QA Suite on port 8099.")
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR), help="Isolated run directory for temp_data/temp_logs/outputs")
    parser.add_argument("--audio-cache-dir", default=str(DEFAULT_AUDIO_CACHE_DIR), help="Audio cache dir for round-1 WAV reuse")
    parser.add_argument("--output-subdir", default="voice_tests", help="Output subdir relative to --run-dir")
    parser.add_argument("--stt-mode", choices=("gemini", "offline", "auto"), default="gemini")
    parser.add_argument("--env-file", default="", help="Optional path passed ONLY as SMARTHOME_ENV_FILE to temp server")
    parser.add_argument("--phase", choices=("all", "text", "clean", "degraded", "fresh"), default="all")
    parser.add_argument("--whisper-model", default=os.environ.get("SMARTHOME_WHISPER_MODEL", "small"))
    parser.add_argument("--degraded-limit", type=int, default=25, help="Utterances per degradation (0 = all marked)")
    parser.add_argument("--include-fresh-voices", action="store_true", help="Run Phase D with 40 fresh edge-tts neural clips")
    parser.add_argument("--min-interval-ms", type=int, default=0, help="Optional pacing between voice requests in ms")
    parser.add_argument("--no-chart", dest="generate_chart", action="store_false")
    args = parser.parse_args()
    run_suite(args)


if __name__ == "__main__":
    main()
