"""Registry-Driven Live End-to-End Offline & Reconnect Test on Isolated Local Port 8092.

Spins up:
- Isolated `uvicorn backend.server:app` on `127.0.0.1:8092` with isolated temp `SMARTHOME_DATA_DIR`
  and `SMARTHOME_BOARD_HEARTBEAT_TIMEOUT_SEC=3` (NEVER touches prod port 8088 or owner credentials).
- `scripts/mock_esp8266_client.py` on `127.0.0.1:8093` sending heartbeats to 8092 and hosting
  local LAN `/offline/cmd` + `/offline/status` + `/sim/disconnect` + `/sim/reconnect`.
- 3 temporary test accounts (`Cap 1`, `Cap 2`, `Cap 3`) created ONLY in the isolated temp data dir
  and completely deleted at teardown.

All device IDs, Vietnamese display names, allowed/forbidden actions, and tier visibility matrices
are derived dynamically from `DEFAULT_DEVICES`, `ACTION_VI_LABEL`, `OFFLINE_ALLOWED_DEVICE_ACTIONS`,
`OFFLINE_FORBIDDEN_DEVICE_ACTIONS`, and `devices_visible_for_tier` (R2: zero hardcoding).
"""

from __future__ import annotations

import copy
import json
import os
import pathlib
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any

import pytest

from backend.auth.constants_and_crypto import DEFAULT_ACCOUNTS, hash_password
from backend.auth.tier_permissions import devices_visible_for_tier
from backend.engine.constants_and_time import (
    ACTION_TO_STATE,
    ACTION_VI_LABEL,
    DEFAULT_DEVICES,
    DEVICE_CAPABILITIES,
)
from backend.engine.offline_contract import (
    OFFLINE_ALLOWED_DEVICE_ACTIONS,
    OFFLINE_FORBIDDEN_DEVICE_ACTIONS,
    OFFLINE_SAFETY_DEFAULTS,
)
from backend.voice_config import OWNER_EMAIL
from tests.live_auth_helpers import login_live_owner
from tests.voice_policy.run_voice_journeys import verify_vietnamese_only_output

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVER_PORT = 8092
MOCK_BOARD_PORT = 8093
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"
MOCK_BOARD_URL = f"http://127.0.0.1:{MOCK_BOARD_PORT}"


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any]]:
    hdrs = dict(headers or {})
    data: bytes | None = None
    if payload is not None:
        hdrs.setdefault("Content-Type", "application/json")
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            body = json.loads(raw) if raw else {"ok": False, "error": str(exc)}
        except Exception:
            body = {"ok": False, "error": raw or str(exc)}
        return exc.code, body


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def _wait_until(predicate, timeout_sec: float = 15.0, interval_sec: float = 0.25) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval_sec)
    return False


def _create_invited_temp_account(
    base_url: str,
    owner_token: str,
    *,
    tier: int,
    email: str,
    display_name: str,
) -> tuple[str, str]:
    """Create a temporary Cap 2 or Cap 3 account on isolated port 8092 via Cap 1 invite."""
    c_inv, inv = _http_json(
        f"{base_url}/api/auth3/guest_invites",
        method="POST",
        headers={"X-Session-Token": owner_token},
        payload={"tier": tier, "ttl_sec": 3600, "pin": "2468", "pin_confirm": "2468"},
    )
    assert c_inv == 200 and inv.get("ok") is True and inv.get("token"), (
        f"Failed to issue tier {tier} invite: {c_inv} {inv}"
    )
    pw = f"S2Temp#{secrets.token_hex(8)}Aa1"
    c_reg, reg = _http_json(
        f"{base_url}/api/auth3/register_or_set_password",
        method="POST",
        payload={
            "email": email,
            "display_name": display_name,
            "password": pw,
            "confirm_password": pw,
            "invite_token": inv["token"],
            "source": "qa_e2e_8092",
        },
    )
    assert c_reg == 200 and reg.get("ok") is True, (
        f"Failed to register temp tier {tier} account: {c_reg} {reg}"
    )
    sess_token = str(reg.get("session_token") or "").strip()
    if not sess_token:
        c_log, r_log = _http_json(
            f"{base_url}/api/auth3/layer1_login",
            method="POST",
            payload={"email": email, "password": pw, "send_gmail": False},
        )
        assert c_log == 200 and r_log.get("ok") is True and r_log.get("session_token"), (
            f"Temp tier {tier} login failed: {c_log} {r_log}"
        )
        sess_token = str(r_log["session_token"])
    return sess_token, pw


def _devices_by_id(snap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    devs = snap.get("devices")
    if isinstance(devs, list):
        return {str(d["id"]): d for d in devs if isinstance(d, dict) and d.get("id")}
    if isinstance(devs, dict):
        return devs
    return {}


def _vi_cmd(dev_id: str, action: str) -> str:
    verb = ACTION_VI_LABEL.get(action, action).lower()
    name = str(DEFAULT_DEVICES[dev_id]["name"]).lower()
    return f"{verb} {name}"


def _primary_non_door_device() -> str:
    for dev_id, meta in DEFAULT_DEVICES.items():
        if str(meta.get("type") or "").lower() == "light" and "turn_on" in OFFLINE_ALLOWED_DEVICE_ACTIONS.get(dev_id, ()):
            return dev_id
    for dev_id in DEFAULT_DEVICES:
        if dev_id not in OFFLINE_FORBIDDEN_DEVICE_ACTIONS and "turn_on" in OFFLINE_ALLOWED_DEVICE_ACTIONS.get(dev_id, ()):
            return dev_id
    raise AssertionError("No allowed non-door device found in DEFAULT_DEVICES")


def _terminate_proc(proc: subprocess.Popen[Any] | None) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3.0)


@pytest.fixture(scope="module")
def live_offline_stack() -> dict[str, Any]:
    assert not _is_port_open("127.0.0.1", SERVER_PORT), f"Port {SERVER_PORT} already in use"
    assert not _is_port_open("127.0.0.1", MOCK_BOARD_PORT), f"Port {MOCK_BOARD_PORT} already in use"

    tmp_root = pathlib.Path(tempfile.mkdtemp(prefix="smarthome_s2_8092_"))
    data_dir = tmp_root / "data"
    vault_dir = tmp_root / "vault"
    data_dir.mkdir(parents=True, exist_ok=True)
    vault_dir.mkdir(parents=True, exist_ok=True)

    cap1_password = secrets.token_urlsafe(24)
    accounts = copy.deepcopy(DEFAULT_ACCOUNTS)
    for acc in accounts:
        acc.pop("pending_otp", None)
        if acc.get("email") == OWNER_EMAIL:
            acc["password_hash"] = hash_password(cap1_password)
    (data_dir / "accounts_3layer.json").write_text(
        json.dumps(accounts, ensure_ascii=False),
        encoding="utf-8",
    )

    hw_key = secrets.token_urlsafe(24)
    env = os.environ.copy()
    env.pop("VERCEL", None)
    env.pop("SMARTHOME_FORCE_CLOUD_DURABLE", None)
    env["SMARTHOME_DATA_DIR"] = str(data_dir)
    env["SMARTHOME_DURABLE_DIR"] = str(vault_dir)
    env["SIMULATOR_SECURITY_STATE_DIR"] = str(data_dir)
    env["PYTEST"] = "1"
    env["SMARTHOME_BOARD_HEARTBEAT_TIMEOUT_SEC"] = "3"
    env["SMARTHOME_HARDWARE_API_KEY"] = hw_key
    env["SMARTHOME_AOEDE_CACHE_ONLY"] = "1"
    env["PYTHONUTF8"] = "1"

    server_log = tmp_root / "uvicorn_8092.log"
    board_log = tmp_root / "mock_board_8093.log"
    server_proc: subprocess.Popen[Any] | None = None
    board_proc: subprocess.Popen[Any] | None = None

    srv_fh = server_log.open("wb")
    brd_fh = board_log.open("wb")
    try:
        server_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(SERVER_PORT),
                "--log-level",
                "warning",
            ],
            cwd=str(ROOT),
            env=env,
            stdout=srv_fh,
            stderr=subprocess.STDOUT,
        )
        assert _wait_until(
            lambda: _http_json(f"{SERVER_URL}/api/state", headers={"X-Hardware-Key": hw_key})[0] == 200,
            timeout_sec=20.0,
        ), f"Local server {SERVER_URL} failed to boot. Log:\n{server_log.read_text(errors='ignore')}"

        board_proc = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "scripts" / "mock_esp8266_client.py"),
                "--server-url",
                SERVER_URL,
                "--listen-host",
                "127.0.0.1",
                "--listen-port",
                str(MOCK_BOARD_PORT),
                "--heartbeat-interval",
                "1.0",
            ],
            cwd=str(ROOT),
            env=env,
            stdout=brd_fh,
            stderr=subprocess.STDOUT,
        )
        assert _wait_until(
            lambda: _http_json(f"{MOCK_BOARD_URL}/offline/status")[0] == 200
            and _http_json(f"{MOCK_BOARD_URL}/offline/status")[1].get("heartbeat_sent_count", 0) >= 1,
            timeout_sec=12.0,
        ), f"Mock ESP8266 node {MOCK_BOARD_URL} failed to boot. Log:\n{board_log.read_text(errors='ignore')}"

        cap1_token = login_live_owner(SERVER_URL, cap1_password)
        cap2_email = f"s2.cap2.{secrets.token_hex(4)}@gmail.com"
        cap3_email = f"s2.cap3.{secrets.token_hex(4)}@gmail.com"
        cap2_token, _cap2_pw = _create_invited_temp_account(
            SERVER_URL,
            cap1_token,
            tier=2,
            email=cap2_email,
            display_name="Thành viên Thử nghiệm S2",
        )
        cap3_token, _cap3_pw = _create_invited_temp_account(
            SERVER_URL,
            cap1_token,
            tier=3,
            email=cap3_email,
            display_name="Khách Thử nghiệm S2",
        )
        tokens = {"cap1": cap1_token, "cap2": cap2_token, "cap3": cap3_token}
        creds = {
            "cap1": {"email": OWNER_EMAIL, "tier": "1"},
            "cap2": {"email": cap2_email, "tier": "2"},
            "cap3": {"email": cap3_email, "tier": "3"},
        }

        yield {
            "server_url": SERVER_URL,
            "board_url": MOCK_BOARD_URL,
            "data_dir": data_dir,
            "tokens": tokens,
            "creds": creds,
            "hw_key": hw_key,
        }
    finally:
        _terminate_proc(board_proc)
        _terminate_proc(server_proc)
        srv_fh.close()
        brd_fh.close()
        # Teardown verification: delete temp accounts/data dir and confirm ports closed
        shutil.rmtree(tmp_root, ignore_errors=True)
        assert not tmp_root.exists(), f"Temp directory {tmp_root} was not cleaned up"
        assert _wait_until(lambda: not _is_port_open("127.0.0.1", SERVER_PORT), timeout_sec=5.0)
        assert _wait_until(lambda: not _is_port_open("127.0.0.1", MOCK_BOARD_PORT), timeout_sec=5.0)


def test_01_online_heartbeat_and_toggle(live_offline_stack: dict[str, Any]) -> None:
    tokens = live_offline_stack["tokens"]
    for tier_num, key in ((1, "cap1"), (2, "cap2"), (3, "cap3")):
        code, snap = _http_json(
            f"{SERVER_URL}/api/state",
            headers={"X-Session-Token": tokens[key]},
        )
        assert code == 200
        bh = snap.get("board_health") or {}
        assert bh.get("online") is True
        assert bh.get("status") == "ONLINE"
        assert bh.get("status_vi") == "Đang kết nối"
        visible = set(devices_visible_for_tier(tier_num))
        dev_map = _devices_by_id(snap)
        assert set(dev_map.keys()) == visible
        for dev_id in visible:
            assert dev_map[dev_id]["board_online"] is True
            assert dev_map[dev_id]["connectivity_label_vi"] == "Đang kết nối"

    primary_dev = _primary_non_door_device()
    code_on, res_on = _http_json(
        f"{SERVER_URL}/api/device",
        method="POST",
        headers={"X-Session-Token": tokens["cap1"]},
        payload={"device_id": primary_dev, "action": "turn_on", "source": "qa_e2e"},
    )
    assert code_on == 200 and res_on.get("ok") is True
    assert res_on.get("state") == "ON"

    code_off, res_off = _http_json(
        f"{SERVER_URL}/api/device",
        method="POST",
        headers={"X-Session-Token": tokens["cap1"]},
        payload={"device_id": primary_dev, "action": "turn_off", "source": "qa_e2e"},
    )
    assert code_off == 200 and res_off.get("ok") is True
    assert res_off.get("state") == "OFF"


def test_02_disconnect_timeout_offline_badge_and_503_no_false_success(live_offline_stack: dict[str, Any]) -> None:
    tokens = live_offline_stack["tokens"]
    disc_code, disc_body = _http_json(f"{MOCK_BOARD_URL}/sim/disconnect", method="POST", payload={})
    assert disc_code == 200 and disc_body.get("offline_mode") is True

    # Wait for genuine heartbeat timeout (configured to 3s)
    went_offline = _wait_until(
        lambda: _http_json(f"{SERVER_URL}/api/state", headers={"X-Session-Token": tokens["cap1"]})[1]
        .get("board_health", {})
        .get("online")
        is False,
        timeout_sec=10.0,
        interval_sec=0.4,
    )
    assert went_offline, "Server did not transition board_health to OFFLINE after heartbeat timeout"

    code, snap = _http_json(f"{SERVER_URL}/api/state", headers={"X-Session-Token": tokens["cap1"]})
    assert code == 200
    bh = snap["board_health"]
    assert bh["online"] is False
    assert bh["status"] == "OFFLINE"
    assert bh["status_vi"] == "Mất kết nối"
    assert bh.get("last_seen_vi"), "Expected formatted Vietnamese last_seen_vi timestamp"

    # Every device in DEFAULT_DEVICES must show offline metadata and return HTTP 503 without mutating state
    dev_map = _devices_by_id(snap)
    for dev_id in DEFAULT_DEVICES:
        dev_rec = dev_map[dev_id]
        assert dev_rec["board_online"] is False
        assert dev_rec["connectivity_label_vi"] == "Mất kết nối"
        assert dev_rec.get("last_seen_vi")
        prev_state = dev_rec["state"]
        act = DEVICE_CAPABILITIES[dev_id]["actions"][0]
        c_dev, r_dev = _http_json(
            f"{SERVER_URL}/api/device",
            method="POST",
            headers={"X-Session-Token": tokens["cap1"]},
            payload={"device_id": dev_id, "action": act, "source": "qa_e2e_offline"},
        )
        assert c_dev == 503, f"Expected HTTP 503 when offline for {dev_id}, got {c_dev}: {r_dev}"
        assert r_dev.get("ok") is False
        assert r_dev.get("executed") is False
        assert r_dev.get("board_offline") is True
        assert r_dev.get("delivery_status") == "BOARD_OFFLINE"
        assert "mất kết nối" in str(r_dev.get("error") or "").lower()
        # Verify zero state mutation
        _, snap_after = _http_json(f"{SERVER_URL}/api/state", headers={"X-Session-Token": tokens["cap1"]})
        assert _devices_by_id(snap_after)[dev_id]["state"] == prev_state

    # Verify Cap 2 & Cap 3 also get HTTP 503 on their allowed visible devices
    for tier_num, key in ((2, "cap2"), (3, "cap3")):
        vis = [d for d in devices_visible_for_tier(tier_num) if d not in OFFLINE_FORBIDDEN_DEVICE_ACTIONS]
        assert vis
        target = vis[0]
        c_t, r_t = _http_json(
            f"{SERVER_URL}/api/device",
            method="POST",
            headers={"X-Session-Token": tokens[key]},
            payload={"device_id": target, "action": "turn_on", "source": f"qa_e2e_{key}"},
        )
        assert c_t == 503 and r_t.get("board_offline") is True


def test_03_server_voice_offline_reply_no_false_success(live_offline_stack: dict[str, Any]) -> None:
    tokens = live_offline_stack["tokens"]
    primary_dev = _primary_non_door_device()
    cmd_vi = _vi_cmd(primary_dev, "turn_on")
    dev_name_low = str(DEFAULT_DEVICES[primary_dev]["name"]).lower()

    for key in ("cap1", "cap2", "cap3"):
        code, body = _http_json(
            f"{SERVER_URL}/api/text_command",
            method="POST",
            headers={"X-Session-Token": tokens[key]},
            payload={"text": cmd_vi},
        )
        assert code == 503, f"Expected HTTP 503 for voice command offline ({key}), got {code}: {body}"
        assert body.get("ok") is False
        assert body.get("board_offline") is True
        reply = str(body.get("exact_spoken_reply") or body.get("reply") or "")
        ok_vi, reason = verify_vietnamese_only_output(reply, allow_empty=False)
        assert ok_vi, f"Offline voice reply must be 100% Vietnamese ({reason}): {reply!r}"
        low = reply.lower()
        assert "mất kết nối" in low
        assert dev_name_low in low
        for forbidden_ok in ("đã bật", "đã tắt", "đã mở", "đã đóng", "thành công"):
            assert forbidden_ok not in low, f"False success phrase {forbidden_ok!r} in {reply!r}"


def test_04_a1_a2_local_offline_voice_no_roles_and_custom_refusal(live_offline_stack: dict[str, Any]) -> None:
    # Verify local LAN offline node operates without server and without any auth/role headers (A1 + A2)
    st_code, st_body = _http_json(f"{MOCK_BOARD_URL}/offline/status")
    assert st_code == 200
    assert st_body["offline_mode"] is True
    assert st_body["role_check_enabled"] is False

    primary_dev = _primary_non_door_device()
    non_door_devices = [d for d in DEFAULT_DEVICES if d not in OFFLINE_FORBIDDEN_DEVICE_ACTIONS]
    assert non_door_devices

    for dev_id in non_door_devices:
        for act in OFFLINE_ALLOWED_DEVICE_ACTIONS[dev_id]:
            cmd_text = _vi_cmd(dev_id, act)
            c, r = _http_json(
                f"{MOCK_BOARD_URL}/offline/cmd",
                method="POST",
                payload={"text": cmd_text},
            )
            assert c == 200, f"Allowed offline cmd {cmd_text!r} failed: {c} {r}"
            assert r["ok"] is True and r["refused"] is False
            assert r["device_id"] == dev_id
            assert r["state"] == ACTION_TO_STATE[act]
            assert "ngoại tuyến" in str(r.get("reply_vi") or "").lower()

    # Leave primary_dev ON offline so Step 6 (A4 resync) proves physical offline change syncs back to server
    c_on, r_on = _http_json(
        f"{MOCK_BOARD_URL}/offline/cmd",
        method="POST",
        payload={"text": _vi_cmd(primary_dev, "turn_on")},
    )
    assert c_on == 200 and r_on["state"] == "ON"

    # Custom commands & schedules must be refused with HTTP 400 (Addendum A2)
    custom_phrases = [
        f"mật mã tự đặt {secrets.token_hex(3)}",
        f"hẹn giờ {_vi_cmd(primary_dev, 'turn_off')} sau 5 phút",
        "tạo lệnh tùy chỉnh chế độ đi ngủ",
    ]
    for phrase in custom_phrases:
        c_ref, r_ref = _http_json(
            f"{MOCK_BOARD_URL}/offline/cmd",
            method="POST",
            payload={"text": phrase},
        )
        assert c_ref == 400, f"Custom/schedule phrase {phrase!r} must be refused with 400, got {c_ref}: {r_ref}"
        assert r_ref["ok"] is False and r_ref["refused"] is True
        assert r_ref["reason_code"] == "CUSTOM_OR_ADVANCED_FORBIDDEN_OFFLINE"
        assert "ngoại tuyến" in str(r_ref.get("reply_vi") or "").lower()


def test_05_a3_firmware_door_open_hard_refusal(live_offline_stack: dict[str, Any]) -> None:
    assert OFFLINE_FORBIDDEN_DEVICE_ACTIONS, "Expected door open forbidden in offline_contract"
    for door_id, forbidden_actions in OFFLINE_FORBIDDEN_DEVICE_ACTIONS.items():
        for act in forbidden_actions:
            cmd_text = _vi_cmd(door_id, act)
            c_txt, r_txt = _http_json(
                f"{MOCK_BOARD_URL}/offline/cmd",
                method="POST",
                payload={"text": cmd_text},
            )
            assert c_txt == 403, f"Door open via text must be HTTP 403, got {c_txt}: {r_txt}"
            assert r_txt["ok"] is False and r_txt["refused"] is True
            assert r_txt["reason_code"] == "DOOR_OPEN_FORBIDDEN_OFFLINE"
            assert r_txt["reply_vi"] == "Đang mất kết nối máy chủ, tuyệt đối không được phép mở cửa chính."
            assert r_txt["state"] == OFFLINE_SAFETY_DEFAULTS[door_id]
            assert r_txt.get("door_angle_deg") == 0

            # Also test direct JSON bypass attempt
            c_dir, r_dir = _http_json(
                f"{MOCK_BOARD_URL}/offline/cmd",
                method="POST",
                payload={"device_id": door_id, "action": act},
            )
            assert c_dir == 403 and r_dir["state"] == OFFLINE_SAFETY_DEFAULTS[door_id]

        # Closing door offline MUST remain allowed
        if "close" in OFFLINE_ALLOWED_DEVICE_ACTIONS.get(door_id, ()):
            c_cl, r_cl = _http_json(
                f"{MOCK_BOARD_URL}/offline/cmd",
                method="POST",
                payload={"text": _vi_cmd(door_id, "close")},
            )
            assert c_cl == 200 and r_cl["ok"] is True and r_cl["state"] == "CLOSED"


def test_06_a4_reconnect_auto_resync_and_audit_log(live_offline_stack: dict[str, Any]) -> None:
    tokens = live_offline_stack["tokens"]
    data_dir: pathlib.Path = live_offline_stack["data_dir"]
    primary_dev = _primary_non_door_device()

    # Before reconnect, server still shows primary_dev OFF (offline commands never touched server)
    _, snap_before = _http_json(f"{SERVER_URL}/api/state", headers={"X-Session-Token": tokens["cap1"]})
    assert snap_before["board_health"]["online"] is False
    assert _devices_by_id(snap_before)[primary_dev]["state"] == "OFF"

    # Reconnect mock ESP8266 -> triggers POST /api/hardware/resync automatically
    c_rec, r_rec = _http_json(f"{MOCK_BOARD_URL}/sim/reconnect", method="POST", payload={})
    assert c_rec == 200 and r_rec.get("ok") is True
    assert r_rec.get("resync_status_code") == 200
    assert r_rec["resync_response"].get("resynced") is True

    # Verify all 3 tiers immediately see board ONLINE and primary_dev == ON!
    for key in ("cap1", "cap2", "cap3"):
        c_st, snap_after = _http_json(f"{SERVER_URL}/api/state", headers={"X-Session-Token": tokens[key]})
        assert c_st == 200
        assert snap_after["board_health"]["online"] is True
        assert snap_after["board_health"]["status_vi"] == "Đang kết nối"
        assert snap_after["board_health"]["offline_resync_count"] >= 1
        after_devs = _devices_by_id(snap_after)
        assert after_devs[primary_dev]["state"] == "ON"
        assert after_devs[primary_dev]["board_online"] is True

    # Verify audit log recorded `board_offline_resync`
    audit_file = data_dir / "system_audit_logs.jsonl"
    assert audit_file.exists(), "Expected system_audit_logs.jsonl in isolated temp data dir"
    lines = [
        json.loads(line)
        for line in audit_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip()
    ]
    resync_entries = [e for e in lines if e.get("event_type") == "board_offline_resync"]
    assert resync_entries, f"Expected board_offline_resync audit entry, found types: {[e.get('event_type') for e in lines]}"
    assert any(primary_dev in json.dumps(e, ensure_ascii=False) for e in resync_entries)
