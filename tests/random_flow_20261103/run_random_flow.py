# -*- coding: utf-8 -*-
"""Random / adversarial flow tester for DATN Smart Home Voice AI.
Does NOT modify project source. Writes only under tests/random_flow_20261103/
and a Desktop backup folder. Restores simulator/data after runs.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any

SEED = 20261103
BASE = "http://127.0.0.1:8088"
DESK = Path(r"C:\Users\LENOVO\Desktop")

def find_proj() -> Path:
    for name in os.listdir(DESK):
        if "\u0111\u1ed3" in name and "t\u1ed1t" in name:
            return DESK / name
    raise SystemExit("Project folder not found")

PROJ = find_proj()
DATA = PROJ / "simulator" / "data"
AUDIO = PROJ / "test_audio"
OUT = PROJ / "tests" / "random_flow_20261103"
BACKUP = DESK / "datn-backup-flowtest-20261103"
RESULTS: list[dict[str, Any]] = []

sys.path.insert(0, str(PROJ))

DATA_FILES = [
    "accounts_3layer.json",
    "auth_3layer_events.json",
    "custom_rules_overlay.json",
    "esp8266_flash_replica.json",
    "factory_default_rules.json",
    "family_email_allowlist.json",
    "invite_links_3layer.json",
    "ir_devices_db.json",
    "knowledge_base.json",
    "knowledge_embeddings_cache.json",
    "smarthome.db",
    "system_audit_logs.jsonl",
    "voiceprints.json",
]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def backup_data() -> dict[str, str]:
    BACKUP.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in DATA_FILES:
        src = DATA / name
        if src.exists():
            dst = BACKUP / name
            shutil.copy2(src, dst)
            hashes[name] = sha256_file(src)
    # also copy nested backup folder marker
    (BACKUP / "BACKUP_META.json").write_text(
        json.dumps({"ts": time.time(), "hashes": hashes, "seed": SEED}, indent=2),
        encoding="utf-8",
    )
    return hashes


def restore_data(pre_hashes: dict[str, str]) -> dict[str, Any]:
    report = {"restored": [], "mismatch_after": [], "missing_in_backup": []}
    for name in DATA_FILES:
        src = BACKUP / name
        dst = DATA / name
        if not src.exists():
            report["missing_in_backup"].append(name)
            continue
        shutil.copy2(src, dst)
        report["restored"].append(name)
        h = sha256_file(dst)
        if name in pre_hashes and h != pre_hashes[name]:
            report["mismatch_after"].append({"file": name, "expected": pre_hashes[name], "got": h})
    # verify all restored match backup
    ok = True
    verify = {}
    for name in DATA_FILES:
        b = BACKUP / name
        d = DATA / name
        if b.exists() and d.exists():
            hb, hd = sha256_file(b), sha256_file(d)
            verify[name] = {"match": hb == hd, "sha256": hd}
            if hb != hd:
                ok = False
    report["verify_ok"] = ok
    report["verify"] = verify
    return report


def http_json(method: str, path: str, body: dict | None = None, timeout: float = 20.0) -> tuple[int, Any]:
    url = BASE + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw.decode("utf-8"))
            except Exception:
                return resp.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode("utf-8"))
        except Exception:
            return e.code, raw.decode("utf-8", "replace")
    except Exception as e:
        return 0, {"error": str(e), "type": type(e).__name__}


def read_wav(name: str) -> bytes:
    path = AUDIO / name
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes())


def pcm_b64(name: str) -> str:
    return base64.b64encode(read_wav(name)).decode("ascii")


def record(
    sid: str,
    title: str,
    verdict: str,
    observed: str,
    expected: str,
    fault: str = "",
    detail: Any = None,
) -> None:
    RESULTS.append(
        {
            "id": sid,
            "title": title,
            "verdict": verdict,  # PASS / FAIL / QUESTIONABLE
            "observed": observed,
            "expected": expected,
            "fault": fault,
            "detail": detail,
        }
    )
    print(f"[{verdict}] {sid}: {title} :: {observed}")


def get_state() -> dict:
    code, data = http_json("GET", "/api/state")
    if code != 200 or not isinstance(data, dict):
        return {}
    return data


def device_state(dev_id: str) -> str | None:
    st = get_state()
    devices = st.get("devices") or {}
    # devices may be dict or list
    if isinstance(devices, dict):
        d = devices.get(dev_id) or {}
        return d.get("state")
    if isinstance(devices, list):
        for d in devices:
            if d.get("id") == dev_id:
                return d.get("state")
    return None


# -------------------- SCENARIOS --------------------

def scen_http_state_ok(rng: random.Random) -> None:
    code, data = http_json("GET", "/api/state")
    ok = code == 200 and isinstance(data, dict) and "current_tier" in data
    record(
        "S01",
        "GET /api/state trả về snapshot hợp lệ",
        "PASS" if ok else "FAIL",
        f"HTTP {code}; keys={list(data)[:8] if isinstance(data, dict) else type(data)}",
        "200 + current_tier/devices",
        "simulator/server.py:api_get_state" if not ok else "",
        data if not ok else {"tier": data.get("current_tier"), "user": data.get("current_user_name")},
    )


def scen_guest_spoof_tier_open_door(rng: random.Random) -> None:
    """Client claims tier=1 while acting as guest — should NOT open door if RBAC enforced on API."""
    before = device_state("main_door")
    # First close door as "owner"
    http_json("POST", "/api/device", {"device_id": "main_door", "action": "close", "tier": 1, "user_name": "reset"})
    code, data = http_json(
        "POST",
        "/api/device",
        {
            "device_id": "main_door",
            "action": "open",
            "tier": 1,  # spoofed
            "user_name": "Khách giả mạo Cấp 1",
        },
    )
    after = device_state("main_door")
    # Spec: guest must be blocked from door. Trusting client tier=1 is unsafe.
    opened = after == "OPEN" or (isinstance(data, dict) and data.get("ok") is True and not data.get("error"))
    if opened:
        record(
            "S02",
            "Khách giả mạo tier=1 qua /api/device để mở cửa",
            "FAIL",
            f"Cửa mở được (before={before}, after={after}); resp={str(data)[:200]}",
            "Phải từ chối: API không được tin tier do client gửi; cửa chỉ mở khi session Cấp 1 đã xác thực",
            "simulator/server.py:api_control_device (bypass_rbac=(tier==1) từ payload)",
            {"http": code, "resp": data, "after": after},
        )
    else:
        record(
            "S02",
            "Khách giả mạo tier=1 qua /api/device để mở cửa",
            "PASS",
            f"Bị chặn; after={after}; resp={str(data)[:180]}",
            "Từ chối mở cửa khi chưa xác thực Cấp 1 phía server",
            "",
            {"http": code, "resp": data},
        )
    # cleanup
    http_json("POST", "/api/device", {"device_id": "main_door", "action": "close", "tier": 1})


def scen_guest_tier3_claim_open_door(rng: random.Random) -> None:
    http_json("POST", "/api/device", {"device_id": "main_door", "action": "close", "tier": 1})
    code, data = http_json(
        "POST",
        "/api/device",
        {"device_id": "main_door", "action": "open", "tier": 3, "user_name": "Khách C"},
    )
    after = device_state("main_door")
    # With tier=3, bypass_rbac=False, but engine.current_tier may still be 1 from REST engine!
    # Important: RBAC uses engine.current_tier, NOT payload tier when bypass is false.
    blocked = after != "OPEN" and (isinstance(data, dict) and (data.get("ok") is False or data.get("error")))
    # Actually looking at code: bypass_rbac=(tier==1) so tier=3 means bypass=False, then check_device_permission uses self.current_tier which is likely still 1 (tuan_anh). So door WILL open — design bug / QUESTIONABLE or FAIL.
    if after == "OPEN":
        record(
            "S03",
            "Gọi /api/device mở cửa với payload tier=3 (engine vẫn C1)",
            "FAIL",
            f"Cửa OPEN dù payload khai tier=3; engine.current_tier không đổi theo payload. resp={str(data)[:180]}",
            "Phải gắn session/user đã xác thực; tier trong payload không được bỏ qua cũng không được dùng để bypass khi engine đang C1 mặc định",
            "simulator/server.py:api_control_device + rule_engine.current_tier",
            {"resp": data, "after": after},
        )
    else:
        record(
            "S03",
            "Gọi /api/device mở cửa với payload tier=3",
            "PASS",
            f"Bị chặn after={after}",
            "Khách C3 không mở được cửa",
            "",
            {"resp": data},
        )
    http_json("POST", "/api/device", {"device_id": "main_door", "action": "close", "tier": 1})


def scen_guest_allowed_light(rng: random.Random) -> None:
    """Engine is C1 so this always works — QUESTIONABLE for API lacking real session."""
    http_json("POST", "/api/device", {"device_id": "living_room_light", "action": "turn_off", "tier": 1})
    code, data = http_json(
        "POST",
        "/api/device",
        {"device_id": "living_room_light", "action": "turn_on", "tier": 3, "user_name": "Khách"},
    )
    after = device_state("living_room_light")
    if after == "ON":
        record(
            "S04",
            "Bật đèn phòng khách qua /api/device (khách được phép theo spec)",
            "QUESTIONABLE",
            f"Đèn ON (đúng quyền C3 theo catalog) nhưng API không chứng minh session C3 — đang chạy dưới engine C1. resp={str(data)[:120]}",
            "Cho phép C3 bật đèn khi đã xác thực C3; cần session thật",
            "simulator/server.py:api_control_device",
            {"resp": data},
        )
    else:
        record(
            "S04",
            "Bật đèn phòng khách",
            "FAIL",
            f"Không bật được after={after} resp={data}",
            "C3 được phép bật đèn",
            "rule_engine.check_device_permission / execute_device_action",
            {"resp": data},
        )
    http_json("POST", "/api/device", {"device_id": "living_room_light", "action": "turn_off", "tier": 1})


def scen_qr_generate_and_reuse(rng: random.Random) -> None:
    code, data = http_json("POST", "/api/auth3/qr/generate", {"issuer_tier": 1, "duration_type": "1d"})
    if not (code == 200 and isinstance(data, dict) and data.get("ok") and data.get("token")):
        record(
            "S05",
            "Sinh QR động 10s",
            "FAIL",
            f"HTTP {code} data={str(data)[:200]}",
            "ok + token + window",
            "auth_3layer.generate_dynamic_qr_token / server api_auth3_qr_generate",
            data,
        )
        return
    token = data["token"]
    window = data.get("window")
    # first handshake OK
    c1, d1 = http_json(
        "POST",
        "/api/auth3/guest/handshake",
        {"token": token, "target_window": window, "duration_type": "1d"},
    )
    ok1 = c1 == 200 and isinstance(d1, dict) and d1.get("ok")
    # reuse same token — must fail
    c2, d2 = http_json(
        "POST",
        "/api/auth3/guest/handshake",
        {"token": token, "target_window": window, "duration_type": "1d"},
    )
    blocked = not (isinstance(d2, dict) and d2.get("ok"))
    if ok1 and blocked:
        record(
            "S05",
            "QR single-use: handshake lần 1 OK, reuse bị chặn",
            "PASS",
            f"1st ok session={d1.get('guest_session_id')}; 2nd blocked={str(d2)[:120]}",
            "Token chỉ dùng 1 lần",
            "",
            {"d1": d1, "d2": d2},
        )
    else:
        record(
            "S05",
            "QR single-use",
            "FAIL",
            f"ok1={ok1} blocked_reuse={blocked} d1={str(d1)[:100]} d2={str(d2)[:100]}",
            "Lần 1 OK, lần 2 từ chối",
            "auth_3layer.consume_guest_handshake / used_qr_tokens",
            {"d1": d1, "d2": d2},
        )


def scen_qr_expired_window(rng: random.Random) -> None:
    code, data = http_json("POST", "/api/auth3/qr/generate", {"issuer_tier": 1, "duration_type": "2d"})
    if not (isinstance(data, dict) and data.get("token")):
        record("S06", "QR hết cửa sổ 10s", "FAIL", f"Không sinh được QR: {data}", "Sinh QR OK rồi thử window cũ", "auth_3layer.generate_dynamic_qr_token", data)
        return
    token = data["token"]
    bad_win = int(data.get("window", 0)) - 5
    c, d = http_json(
        "POST",
        "/api/auth3/guest/handshake",
        {"token": token, "target_window": bad_win, "duration_type": "2d"},
    )
    blocked = not (isinstance(d, dict) and d.get("ok"))
    record(
        "S06",
        "Handshake với window cũ (mô phỏng QR >10s)",
        "PASS" if blocked else "FAIL",
        f"blocked={blocked} HTTP {c} resp={str(d)[:160]}",
        "Từ chối token ngoài cửa sổ TOTP",
        "" if blocked else "auth_3layer.consume_guest_handshake",
        d,
    )


def scen_qr_tier3_issuer_blocked(rng: random.Random) -> None:
    code, data = http_json("POST", "/api/auth3/qr/generate", {"issuer_tier": 3, "duration_type": "1d"})
    blocked = not (isinstance(data, dict) and data.get("ok"))
    record(
        "S07",
        "Cấp 3 không được sinh QR mời khách",
        "PASS" if blocked else "FAIL",
        f"HTTP {code} resp={str(data)[:160]}",
        "issuer_tier chỉ 1 hoặc 2",
        "" if blocked else "auth_3layer.generate_dynamic_qr_token",
        data,
    )


def scen_qr_bad_duration(rng: random.Random) -> None:
    code, data = http_json("POST", "/api/auth3/qr/generate", {"issuer_tier": 1, "duration_type": "99z"})
    blocked = not (isinstance(data, dict) and data.get("ok"))
    record(
        "S08",
        "duration_type không hợp lệ",
        "PASS" if blocked else "FAIL",
        f"HTTP {code} {str(data)[:140]}",
        "Chỉ nhận 1d/2d/1w/1m/1y",
        "" if blocked else "auth_3layer.generate_dynamic_qr_token",
        data,
    )


def scen_soil_auto_pump(rng: random.Random) -> None:
    # reset pump off, soil high
    http_json("POST", "/api/soil_moisture", {"soil_moisture_pct": 80})
    time.sleep(0.3)
    http_json("POST", "/api/device", {"device_id": "garden_pump", "action": "turn_off", "tier": 1})
    code, data = http_json("POST", "/api/soil_moisture", {"soil_moisture_pct": 25})
    time.sleep(0.5)
    after = device_state("garden_pump")
    # Spec F21: soil < 40% -> pump ON
    if after == "ON":
        record(
            "S09",
            "Độ ẩm đất 25% tự bật máy bơm",
            "PASS",
            f"pump=ON; resp={str(data)[:140]}",
            "soil < 40% => garden_pump ON",
            "",
            data,
        )
    else:
        record(
            "S09",
            "Độ ẩm đất 25% tự bật máy bơm",
            "FAIL",
            f"pump={after}; resp={str(data)[:180]}",
            "Tự bật bơm khi <40%",
            "rule_engine.update_soil_moisture_telemetry",
            data,
        )
    # high moisture should turn off
    code2, data2 = http_json("POST", "/api/soil_moisture", {"soil_moisture_pct": 85})
    time.sleep(0.5)
    after2 = device_state("garden_pump")
    if after2 == "OFF":
        record(
            "S10",
            "Độ ẩm đất 85% tự tắt máy bơm",
            "PASS",
            f"pump=OFF",
            "soil > 75% => pump OFF",
            "",
            data2,
        )
    else:
        record(
            "S10",
            "Độ ẩm đất 85% tự tắt máy bơm",
            "FAIL",
            f"pump={after2}",
            "Tự tắt bơm khi >75%",
            "rule_engine.update_soil_moisture_telemetry",
            data2,
        )
    http_json("POST", "/api/soil_moisture", {"soil_moisture_pct": 62})
    http_json("POST", "/api/device", {"device_id": "garden_pump", "action": "turn_off", "tier": 1})


def scen_manual_off_vs_soil_rule(rng: random.Random) -> None:
    """Manual pump off while soil dry — does auto rule immediately turn it back on?"""
    http_json("POST", "/api/soil_moisture", {"soil_moisture_pct": 20})
    time.sleep(0.4)
    http_json("POST", "/api/device", {"device_id": "garden_pump", "action": "turn_off", "tier": 1})
    time.sleep(0.2)
    # trigger soil update again (same dry value)
    http_json("POST", "/api/soil_moisture", {"soil_moisture_pct": 20})
    time.sleep(0.4)
    after = device_state("garden_pump")
    # Design ambiguity: manual off vs auto irrigation
    if after == "ON":
        record(
            "S11",
            "Xung đột: tắt bơm thủ công khi đất khô — luật tự tưới bật lại",
            "QUESTIONABLE",
            f"pump={after} (luật sensor thắng lệnh tay ngay khi cập nhật lại soil)",
            "Cần chính sách rõ: khóa tạm / cooldown / ưu tiên lệnh tay",
            "rule_engine.update_soil_moisture_telemetry vs execute_device_action",
            {"pump": after},
        )
    else:
        record(
            "S11",
            "Tắt bơm thủ công khi đất khô giữ OFF",
            "QUESTIONABLE",
            f"pump={after} (giữ OFF sau cập nhật soil=20) — có thể thiếu auto-retrigger",
            "Spec F21 nói tự bật khi <40%; nếu không bật lại là lệch spec hoặc ưu tiên lệnh tay",
            "rule_engine.update_soil_moisture_telemetry",
            {"pump": after},
        )
    http_json("POST", "/api/soil_moisture", {"soil_moisture_pct": 62})
    http_json("POST", "/api/device", {"device_id": "garden_pump", "action": "turn_off", "tier": 1})


def scen_dht11_absurd(rng: random.Random) -> None:
    code, data = http_json("POST", "/api/dht11", {"temp_c": 999.0, "humidity_pct": -5.0})
    st = get_state()
    # Find telemetry
    dht = None
    for key in ("dht11", "dht11_telemetry", "sensors", "mqtt"):
        if key in st:
            dht = st.get(key)
    # also nested
    if dht is None:
        mb = st.get("mqtt_bridge") or st.get("telemetry") or {}
        dht = mb
    accepted = code == 200
    # Does it clamp?
    spoken = str(data)[:200] if data else ""
    record(
        "S12",
        "DHT11 giá trị vô lý (999°C, -5% RH)",
        "QUESTIONABLE" if accepted else "PASS",
        f"HTTP {code} accepted={accepted} resp={spoken}",
        "Nên validate/clamp (vd temp [-40,85], RH [0,100]) thay vì nuốt số vô lý",
        "server.api_update_dht11 / rule_engine.update_sensor_telemetry",
        data,
    )
    # restore sane
    http_json("POST", "/api/dht11", {"temp_c": 28.5, "humidity_pct": 65.0})


def scen_soil_nan(rng: random.Random) -> None:
    code, data = http_json("POST", "/api/soil_moisture", {"soil_moisture_pct": "NaN"})
    # float('NaN') might work or 400
    record(
        "S13",
        "soil_moisture_pct = 'NaN' / malformed",
        "PASS" if code >= 400 or (isinstance(data, dict) and data.get("ok") is False) else "QUESTIONABLE",
        f"HTTP {code} resp={str(data)[:160]}",
        "Từ chối hoặc báo lỗi rõ, không đưa NaN vào luật bơm",
        "server.api_update_soil_moisture",
        data,
    )
    http_json("POST", "/api/soil_moisture", {"soil_moisture_pct": 62})


def scen_offline_door_lock(rng: random.Random) -> None:
    http_json("POST", "/api/device", {"device_id": "main_door", "action": "close", "tier": 1})
    http_json("POST", "/api/server_mode", {"server_connected": False})
    time.sleep(0.2)
    code, data = http_json(
        "POST",
        "/api/device",
        {"device_id": "main_door", "action": "open", "tier": 1, "user_name": "Owner offline"},
    )
    after = device_state("main_door")
    locked = after != "OPEN"
    record(
        "S14",
        "Offline: khóa cứng cửa chính kể cả Cấp 1",
        "PASS" if locked else "FAIL",
        f"after={after} resp={str(data)[:160]}",
        "Không mở cửa khi server_connected=False",
        "" if locked else "rule_engine.execute_device_action offline branch",
        data,
    )
    # light should still work offline?
    http_json("POST", "/api/device", {"device_id": "living_room_light", "action": "turn_off", "tier": 1})
    c2, d2 = http_json(
        "POST",
        "/api/device",
        {"device_id": "living_room_light", "action": "turn_on", "tier": 1},
    )
    after_l = device_state("living_room_light")
    record(
        "S15",
        "Offline: vẫn bật được đèn sinh hoạt",
        "PASS" if after_l == "ON" else "FAIL",
        f"light={after_l} resp={str(d2)[:120]}",
        "Đèn/quạt/ĐH/bơm vẫn điều khiển khi offline",
        "" if after_l == "ON" else "rule_engine.execute_device_action offline",
        d2,
    )
    http_json("POST", "/api/server_mode", {"server_connected": True})
    http_json("POST", "/api/device", {"device_id": "main_door", "action": "close", "tier": 1})
    http_json("POST", "/api/device", {"device_id": "living_room_light", "action": "turn_off", "tier": 1})


def scen_text_ambiguous(rng: random.Random) -> None:
    phrases = [
        "tắt hết đi",
        "mở cửa rồi bật đèn",
        "điều hòa 99 độ",
        "xyzabc lệnh không tồn tại",
        "",
    ]
    for i, p in enumerate(phrases):
        code, data = http_json("POST", "/api/text_command", {"text": p})
        reply = ""
        if isinstance(data, dict):
            reply = str(data.get("exact_spoken_reply") or data.get("reply") or data)[:160]
        else:
            reply = str(data)[:160]
        # text_command often just echoes "Đã nhận lệnh" — weak NLU
        if p == "":
            verdict = "QUESTIONABLE"
            exp = "Từ chối lệnh rỗng"
        elif p == "xyzabc lệnh không tồn tại":
            verdict = "QUESTIONABLE" if "Đã nhận lệnh" in reply else "PASS"
            exp = "Báo không hiểu / không thực thi ngầm"
        elif p == "tắt hết đi":
            # Check if all devices off
            st = get_state()
            verdict = "QUESTIONABLE"
            exp = "Tắt all_lights/all_devices hoặc hỏi lại làm rõ"
        elif p == "mở cửa rồi bật đèn":
            door = device_state("main_door")
            light = device_state("living_room_light")
            if door == "OPEN" and light == "ON":
                verdict = "PASS"
            else:
                verdict = "QUESTIONABLE"
            exp = "Thực thi compound: mở cửa + bật đèn (nếu đã auth)"
        else:  # 99 độ
            verdict = "QUESTIONABLE"
            exp = "Chặn/clamp setpoint ngoài biên hoặc hỏi lại"
        record(
            f"S16{chr(ord('a')+i)}",
            f"text_command: '{p}'",
            verdict,
            f"HTTP {code} reply={reply}; door={device_state('main_door')} light={device_state('living_room_light')}",
            exp,
            "server.api_text_command (NLU rất mỏng, nhiều lệnh chỉ echo)",
            data,
        )
    # cleanup
    http_json("POST", "/api/device", {"device_id": "main_door", "action": "close", "tier": 1})
    http_json("POST", "/api/device", {"device_id": "living_room_light", "action": "turn_off", "tier": 1})


def scen_text_no_auth_door(rng: random.Random) -> None:
    """text path that mentions door — may not open via text_command (no device mapping)."""
    http_json("POST", "/api/device", {"device_id": "main_door", "action": "close", "tier": 1})
    code, data = http_json("POST", "/api/text_command", {"text": "mở cửa chính"})
    after = device_state("main_door")
    reply = str((data or {}).get("reply") if isinstance(data, dict) else data)[:160]
    if after == "OPEN":
        record(
            "S17",
            "text_command 'mở cửa chính' không qua giọng nói",
            "QUESTIONABLE",
            f"Cửa OPEN chỉ bằng text, không có voice auth. reply={reply}",
            "Lệnh cửa phải qua nhận diện giọng / session đã xác thực",
            "server.api_text_command",
            data,
        )
    else:
        # echo only
        record(
            "S17",
            "text_command 'mở cửa chính' không mở cửa (chỉ echo)",
            "QUESTIONABLE",
            f"Cửa vẫn {after}; reply={reply} — endpoint text không map lệnh cửa",
            "Hoặc thực thi có auth, hoặc từ chối rõ; không nên im lặng nuốt lệnh an ninh",
            "server.api_text_command",
            data,
        )
    http_json("POST", "/api/device", {"device_id": "main_door", "action": "close", "tier": 1})


def scen_rapid_fire(rng: random.Random) -> None:
    http_json("POST", "/api/device", {"device_id": "fan", "action": "turn_off", "tier": 1})
    results = []
    t0 = time.time()
    for i in range(12):
        act = "turn_on" if i % 2 == 0 else "turn_off"
        c, d = http_json("POST", "/api/device", {"device_id": "fan", "action": act, "tier": 1})
        results.append((c, isinstance(d, dict) and d.get("ok"), device_state("fan")))
    elapsed = time.time() - t0
    final = device_state("fan")
    expected_final = "OFF"  # last i=11 turn_off
    ok = final == expected_final and all(r[0] == 200 for r in results)
    record(
        "S18",
        "Race/rapid 12 lệnh bật-tắt quạt liên tiếp",
        "PASS" if ok else "FAIL",
        f"final={final} expected={expected_final} elapsed={elapsed:.2f}s results_ok={all(r[1] for r in results if r[1] is not None)}",
        "Trạng thái cuối khớp lệnh cuối, không crash",
        "" if ok else "rule_engine.execute_device_action concurrency",
        {"final": final, "sample": results[:3]},
    )
    http_json("POST", "/api/device", {"device_id": "fan", "action": "turn_off", "tier": 1})


def scen_malformed_api(rng: random.Random) -> None:
    cases = [
        ("S19a", "POST", "/api/device", {"device_id": "no_such_device", "action": "open", "tier": 1}),
        ("S19b", "POST", "/api/device", {"device_id": "main_door", "action": "explode", "tier": 1}),
        ("S19c", "POST", "/api/auth3/guest/handshake", {"token": "", "target_window": 0}),
        ("S19d", "POST", "/api/auth3/guest/enroll_voice", {"guest_session_id": "x", "pcm16k_b64": "!!!not-b64!!!"}),
        ("S19e", "POST", "/api/auth3/layer1_login", {"email": "not-an-email", "password": ""}),
    ]
    for sid, method, path, body in cases:
        code, data = http_json(method, path, body)
        # Should not 500
        if code >= 500 or code == 0:
            verdict = "FAIL"
            obs = f"HTTP {code} server error/conn {str(data)[:140]}"
            exp = "4xx hoặc ok=false, không 500"
            fault = "server.py handler exception path"
        else:
            verdict = "PASS"
            obs = f"HTTP {code} {str(data)[:140]}"
            exp = "Xử lý an toàn input xấu"
            fault = ""
        record(sid, f"Malformed {path}", verdict, obs, exp, fault, data)


def scen_email_mismatch_and_fake_mx(rng: random.Random) -> None:
    c1, d1 = http_json(
        "POST",
        "/api/auth3/guest/verify_email",
        {"email": "a@gmail.com", "confirm_email": "b@gmail.com", "guest_session_id": "sess_test"},
    )
    mismatch_blocked = not (isinstance(d1, dict) and d1.get("ok"))
    record(
        "S20",
        "Email xác nhận không khớp",
        "PASS" if mismatch_blocked else "FAIL",
        f"HTTP {c1} {str(d1)[:140]}",
        "Từ chối khi 2 ô email khác nhau",
        "" if mismatch_blocked else "auth_3layer.send_and_verify_email_otp",
        d1,
    )
    c2, d2 = http_json(
        "POST",
        "/api/auth3/guest/verify_email",
        {
            "email": "user@this-domain-should-not-exist-zzz-datn-test.invalid",
            "confirm_email": "user@this-domain-should-not-exist-zzz-datn-test.invalid",
            "guest_session_id": "sess_test2",
            "send_gmail": False,
        },
    )
    mx_blocked = not (isinstance(d2, dict) and d2.get("ok") and d2.get("verified"))
    record(
        "S21",
        "DNS MX tên miền giả .invalid",
        "PASS" if mx_blocked else "FAIL",
        f"HTTP {c2} {str(d2)[:160]}",
        "validate_dns_mx_record thất bại / ok=false",
        "" if mx_blocked else "auth_3layer.validate_dns_mx_record",
        d2,
    )


def scen_add_family_email_rbac(rng: random.Random) -> None:
    # Try as if tier issues - API may take actor from body
    c, d = http_json(
        "POST",
        "/api/auth3/add_family_email",
        {"email": f"guest{rng.randint(1000,9999)}@example.com", "tier": 1, "actor_tier": 3},
    )
    # Expect block if actor is C3 — depends on API shape
    record(
        "S22",
        "Cấp 3 thêm family email (RBAC)",
        "QUESTIONABLE",
        f"HTTP {c} resp={str(d)[:180]} — cần xác nhận API lấy actor từ đâu",
        "C3 bị chặn 100% khi add_family_email",
        "server.api + auth_3layer.add_family_email",
        d,
    )


def scen_already_in_state(rng: random.Random) -> None:
    http_json("POST", "/api/device", {"device_id": "bedroom_light", "action": "turn_on", "tier": 1})
    c, d = http_json("POST", "/api/device", {"device_id": "bedroom_light", "action": "turn_on", "tier": 1})
    already = isinstance(d, dict) and (
        d.get("already_in_state")
        or (isinstance(d.get("results"), list) and any(x.get("already_in_state") for x in d.get("results", [])))
        or ("sẵn" in str(d.get("exact_spoken_reply") or d.get("reply") or "").lower())
    )
    # response shape may nest
    raw = str(d)
    if "sẵn" in raw.lower() or "already" in raw.lower() or already:
        verdict = "PASS"
    else:
        # still ok=true without changing is acceptable if state unchanged
        verdict = "QUESTIONABLE"
    record(
        "S23",
        "Bật đèn ngủ khi đã ON (already-in-state)",
        verdict,
        f"resp={raw[:180]}",
        "Báo đã bật sẵn / already_in_state",
        "rule_engine.execute_device_action",
        d,
    )
    http_json("POST", "/api/device", {"device_id": "bedroom_light", "action": "turn_off", "tier": 1})


def scen_schedule_guest_timer(rng: random.Random) -> None:
    c, d = http_json(
        "POST",
        "/api/mobile/schedule",
        {"device_id": "living_room_light", "action": "turn_on", "seconds": 5, "tier": 3, "user_name": "Khách"},
    )
    # Spec: C3 cannot schedule — but API may not check payload tier
    record(
        "S24",
        "Khách C3 đặt hẹn giờ qua /api/mobile/schedule",
        "QUESTIONABLE",
        f"HTTP {c} {str(d)[:160]} — API nhận tier từ client, engine có thể vẫn C1",
        "C3 bị chặn đặt hẹn giờ (tier3_can_schedule_timer=False) khi session thật là C3",
        "server.api_mobile_schedule / rule_engine.schedule_timer_flexible",
        d,
    )


# -------- In-process DSP scenarios --------

def scen_dsp_suite(rng: random.Random) -> None:
    from simulator.voice_auth import VoiceAuthManager, validate_voice_enrollment_quality
    import numpy as np

    vm = VoiceAuthManager(AUDIO)
    vm.reset_strikes()

    owner = read_wav("giong_1_chu_nha_mo_cua.wav")
    intruder = read_wav("giong_2_nguoi_la_mo_cua.wav")
    dual = read_wav("hai_nguoi_cung_noi_cap1_va_nguoi_la.wav")
    noisy = read_wav("giong_1_kem_tieng_on_quat.wav")
    guest = read_wav("giong_cap3_khach_c.wav")
    member = read_wav("giong_cap2_thanh_vien_a.wav")

    # S25 owner auth
    r = vm.verify_pcm16k_and_apply_strikes(owner)
    record(
        "S25",
        "DSP: nhận diện chủ nhà C1",
        "PASS" if r.get("authorized") and r.get("tier") == 1 else "FAIL",
        f"auth={r.get('authorized')} tier={r.get('tier')} speaker={r.get('speaker_id')} strikes={r.get('strike_count')}",
        "authorized=True, tier=1, owner_voice_1",
        "" if r.get("authorized") else "voice_auth.verify_pcm16k_and_apply_strikes",
        {k: r.get(k) for k in ("authorized", "tier", "speaker_id", "strike_count", "rejection_speech", "reason")},
    )

    # S26 replay same wav twice — still auth, no strike
    vm.reset_strikes()
    r1 = vm.verify_pcm16k_and_apply_strikes(owner)
    r2 = vm.verify_pcm16k_and_apply_strikes(owner)
    ok = r1.get("authorized") and r2.get("authorized") and r2.get("strike_count") == 0
    record(
        "S26",
        "Replay cùng wav chủ nhà 2 lần",
        "PASS" if ok else "FAIL",
        f"r1={r1.get('authorized')} r2={r2.get('authorized')} strikes={r2.get('strike_count')}",
        "Vẫn authorized, không tăng strike",
        "" if ok else "voice_auth.verify_pcm16k_and_apply_strikes",
        {"r1": r1.get("speaker_id"), "r2": r2.get("speaker_id")},
    )

    # S27 stranger 3-strike
    vm.reset_strikes()
    s = []
    for _ in range(3):
        s.append(vm.verify_pcm16k_and_apply_strikes(intruder))
    ok = (
        all(not x.get("authorized") for x in s)
        and s[0].get("strike_count") == 1
        and s[1].get("strike_count") == 2
        and s[2].get("strike_count") >= 3
        and s[2].get("silent_ignore") is True
    )
    record(
        "S27",
        "Người lạ 3-strike (cảnh báo rồi im lặng)",
        "PASS" if ok else "FAIL",
        f"strikes={[x.get('strike_count') for x in s]} silent3={s[2].get('silent_ignore')} speech1={str(s[0].get('rejection_speech'))[:60]}",
        "1→cảnh báo, 2→cảnh báo, 3+→silent_ignore",
        "" if ok else "voice_auth.verify_pcm16k_and_apply_strikes",
        [{"strike": x.get("strike_count"), "silent": x.get("silent_ignore")} for x in s],
    )

    # S28 after strikes, owner still works
    r = vm.verify_pcm16k_and_apply_strikes(owner)
    # Does owner reset strikes?
    ok = r.get("authorized") is True and r.get("tier") == 1
    record(
        "S28",
        "Sau 3-strike người lạ, chủ nhà vẫn ra lệnh được",
        "PASS" if ok else "FAIL",
        f"auth={r.get('authorized')} tier={r.get('tier')} strikes_after={r.get('strike_count')} vm.strikes={getattr(vm,'unauthorized_strikes',None)}",
        "C1 authorized; ideally reset strikes",
        "" if ok else "voice_auth Tier1 immunity",
        {k: r.get(k) for k in ("authorized", "tier", "strike_count", "speaker_id")},
    )

    # S29 dual speaker priority
    vm.reset_strikes()
    r = vm.verify_pcm16k_and_apply_strikes(dual)
    ok = r.get("authorized") is True and r.get("tier") == 1
    record(
        "S29",
        "Hai người nói cùng lúc → ưu tiên C1",
        "PASS" if ok else "FAIL",
        f"auth={r.get('authorized')} tier={r.get('tier')} speaker={r.get('speaker_id')} multi={r.get('multi_speaker') or r.get('dual_pitch')}",
        "authorized C1",
        "" if ok else "voice_auth.detect_multi_speaker_and_resolve_priority",
        {k: r.get(k) for k in ("authorized", "tier", "speaker_id", "filter_stage_used")},
    )

    # S30 noisy fan
    vm.reset_strikes()
    r = vm.verify_pcm16k_and_apply_strikes(noisy)
    ok = r.get("authorized") is True and r.get("tier") == 1
    record(
        "S30",
        "Chủ nhà + tiếng ồn quạt vẫn nhận diện",
        "PASS" if ok else "FAIL",
        f"auth={r.get('authorized')} tier={r.get('tier')}",
        "authorized C1 sau denoise",
        "" if ok else "voice_auth.denoise_and_isolate_human_voice",
        {k: r.get(k) for k in ("authorized", "tier", "speaker_id")},
    )

    # S31 duplicate gate owner vs enroll as guest
    dup = vm.check_duplicate_voice_gate(owner, target_tier=3, target_user_id="khach_fake_dup")
    is_dup = getattr(dup, "is_duplicate", None)
    if is_dup is None and isinstance(dup, tuple):
        is_dup = dup[0]
    reason = getattr(dup, "reason", None) or (dup[1] if isinstance(dup, tuple) and len(dup) > 1 else "")
    record(
        "S31",
        "Cổng chống trùng: thu âm giọng C1 để đăng ký C3",
        "PASS" if is_dup else "FAIL",
        f"is_duplicate={is_dup} reason={reason}",
        "Từ chối TRUNG_GIONG_NGUOI_TRONG_NHA",
        "" if is_dup else "voice_auth.check_duplicate_voice_gate",
        str(dup)[:200],
    )

    # S32 quality gate short pcm
    short = np.zeros(1600, dtype=np.int16).tobytes()  # 0.1s
    q = validate_voice_enrollment_quality(short, 16000)
    record(
        "S32",
        "Quality gate từ chối PCM quá ngắn",
        "PASS" if not q.get("ok") else "FAIL",
        f"ok={q.get('ok')} status={q.get('status')} reason={q.get('reason') or q.get('message')}",
        "ok=False / CHUA_DAT",
        "" if not q.get("ok") else "voice_auth.validate_voice_enrollment_quality",
        q,
    )

    # S33 quality on real guest sample (may need tiling if short)
    g = np.frombuffer(guest, dtype=np.int16)
    if g.size < 16000 * 2:
        g = np.tile(g, int(np.ceil(32000 / max(g.size, 1))))[: 16000 * 3]
    q2 = validate_voice_enrollment_quality(g.tobytes(), 16000)
    record(
        "S33",
        "Quality gate trên mẫu khách thật",
        "PASS" if q2.get("ok") or q2.get("status") in ("DA_DAT", "CHUA_DAT") else "FAIL",
        f"ok={q2.get('ok')} status={q2.get('status')} f0={q2.get('f0_hz')}",
        "Trả về kết quả kiểm định hợp lệ (Đạt hoặc Chưa đạt có lý do)",
        "voice_auth.validate_voice_enrollment_quality",
        {k: q2.get(k) for k in ("ok", "status", "f0_hz", "reason", "message")},
    )

    # S34 member verify
    vm.reset_strikes()
    r = vm.verify_pcm16k_and_apply_strikes(member)
    # May or may not be enrolled as active member in current voiceprints
    record(
        "S34",
        "DSP mẫu thành viên C2",
        "QUESTIONABLE",
        f"auth={r.get('authorized')} tier={r.get('tier')} speaker={r.get('speaker_id')} reason={r.get('reason')}",
        "Nếu đã enroll C2: authorized tier=2; nếu chưa: xử lý như người lạ/strike — phụ thuộc data hiện tại",
        "voice_auth.verify_pcm16k_and_apply_strikes / voiceprints.json",
        {k: r.get(k) for k in ("authorized", "tier", "speaker_id", "strike_count", "reason")},
    )

    # S35 guest sample
    vm.reset_strikes()
    r = vm.verify_pcm16k_and_apply_strikes(guest)
    record(
        "S35",
        "DSP mẫu khách C3",
        "QUESTIONABLE",
        f"auth={r.get('authorized')} tier={r.get('tier')} speaker={r.get('speaker_id')} expires={r.get('reason')}",
        "Nếu profile C3 còn hạn: tier=3 auth; hết hạn: GUEST_EXPIRED",
        "voice_auth.verify + expires_at",
        {k: r.get(k) for k in ("authorized", "tier", "speaker_id", "reason", "rejection_speech")},
    )


def scen_auth3_inprocess_qr(rng: random.Random) -> None:
    from simulator.auth_3layer import get_auth_3layer_manager, DURATION_MAP_SECONDS

    mgr = get_auth_3layer_manager()
    # all durations
    fails = []
    for dur in ("1d", "2d", "1w", "1m", "1y"):
        res = mgr.generate_dynamic_qr_token(issuer_tier=1, duration_type=dur)
        if not res.get("ok") or res.get("duration_seconds") != DURATION_MAP_SECONDS[dur]:
            fails.append((dur, res))
    record(
        "S36",
        "5 mốc duration QR (in-process)",
        "PASS" if not fails else "FAIL",
        f"fails={len(fails)} sample={fails[:1]}",
        "Tất cả 1d/2d/1w/1m/1y OK đúng giây",
        "" if not fails else "auth_3layer.generate_dynamic_qr_token",
        fails[:2],
    )


def scen_engine_rbac_inprocess(rng: random.Random) -> None:
    import asyncio
    from simulator.rule_engine import SmartHomeEngine

    async def run():
        eng = SmartHomeEngine()
        # set as guest
        if hasattr(eng, "set_current_user"):
            eng.set_current_user("khach_c")
        elif hasattr(eng, "_current_user_id"):
            eng._current_user_id = "khach_c"
            # find role
            for uid, u in eng.users.items():
                if u.get("tier") == 3:
                    eng._current_user_id = uid
                    eng._current_role = u.get("role", "CHILD_GUEST")
                    break
        # ensure guest
        eng._current_role = "CHILD_GUEST"
        # force tier 3 via user
        # create ephemeral
        eng.users["tmp_guest_flow"] = {
            "id": "tmp_guest_flow",
            "name": "Tmp Guest",
            "tier": 3,
            "role": "CHILD_GUEST",
            "active": True,
        }
        eng._current_user_id = "tmp_guest_flow"
        eng._current_role = "CHILD_GUEST"

        r_door = await eng.execute_device_action("main_door", "open")
        r_light = await eng.execute_device_action("living_room_light", "turn_on")
        r_ac = await eng.execute_device_action("ac", "turn_on")
        r_siren = await eng.execute_device_action("alarm_siren", "turn_on")
        r_pump = await eng.execute_device_action("garden_pump", "turn_on")
        return r_door, r_light, r_ac, r_siren, r_pump, eng.current_tier

    r_door, r_light, r_ac, r_siren, r_pump, tier = asyncio.run(run())
    door_blocked = r_door.get("ok") is False
    light_ok = r_light.get("ok") is True
    ac_blocked = r_ac.get("ok") is False
    siren_blocked = r_siren.get("ok") is False
    pump_blocked = r_pump.get("ok") is False
    ok = door_blocked and light_ok and ac_blocked and siren_blocked and pump_blocked
    record(
        "S37",
        "RBAC engine C3: đèn OK; cửa/còi/ĐH/bơm chặn",
        "PASS" if ok else "FAIL",
        f"tier={tier} door_ok={r_door.get('ok')} light_ok={r_light.get('ok')} ac_ok={r_ac.get('ok')} siren_ok={r_siren.get('ok')} pump_ok={r_pump.get('ok')}",
        "F13: light/fan OK; door/siren/ac/pump blocked",
        "" if ok else "rule_engine.check_device_permission / execute_device_action",
        {
            "door": r_door.get("error") or r_door.get("exact_spoken_reply"),
            "light": r_light.get("exact_spoken_reply"),
            "ac": r_ac.get("error"),
            "siren": r_siren.get("error"),
            "pump": r_pump.get("error"),
        },
    )


def scen_engine_member_rbac(rng: random.Random) -> None:
    import asyncio
    from simulator.rule_engine import SmartHomeEngine

    async def run():
        eng = SmartHomeEngine()
        eng.users["tmp_member_flow"] = {
            "id": "tmp_member_flow",
            "name": "Tmp Member",
            "tier": 2,
            "role": "MEMBER",
            "active": True,
        }
        eng._current_user_id = "tmp_member_flow"
        eng._current_role = "MEMBER"
        r_door = await eng.execute_device_action("main_door", "open")
        r_ac = await eng.execute_device_action("ac", "turn_on")
        r_pump = await eng.execute_device_action("garden_pump", "turn_on")
        r_siren = await eng.execute_device_action("alarm_siren", "turn_on")
        return r_door, r_ac, r_pump, r_siren, eng.current_tier

    r_door, r_ac, r_pump, r_siren, tier = asyncio.run(run())
    ok = (
        r_door.get("ok") is False
        and r_ac.get("ok") is True
        and r_pump.get("ok") is True
        and r_siren.get("ok") is False
    )
    record(
        "S38",
        "RBAC engine C2: ĐH/bơm OK; cửa/còi chặn",
        "PASS" if ok else "FAIL",
        f"tier={tier} door={r_door.get('ok')} ac={r_ac.get('ok')} pump={r_pump.get('ok')} siren={r_siren.get('ok')}",
        "F17: member controls lights/fan/ac/pump; not door/siren",
        "" if ok else "rule_engine.check_device_permission",
        {"door": r_door.get("error"), "siren": r_siren.get("error")},
    )


def scen_guest_enroll_http_duplicate(rng: random.Random) -> None:
    """Handshake then try enroll with owner voice — must reject duplicate."""
    code, data = http_json("POST", "/api/auth3/qr/generate", {"issuer_tier": 1, "duration_type": "1d"})
    if not (isinstance(data, dict) and data.get("token")):
        record("S39", "Enroll khách bằng giọng C1 (duplicate)", "FAIL", "Không sinh QR", "Sinh QR rồi enroll", "qr generate", data)
        return
    c2, d2 = http_json(
        "POST",
        "/api/auth3/guest/handshake",
        {"token": data["token"], "target_window": data.get("window"), "duration_type": "1d"},
    )
    sess = d2.get("guest_session_id") if isinstance(d2, dict) else None
    # tile owner audio to >=2s if needed
    import numpy as np

    pcm = np.frombuffer(read_wav("giong_1_chu_nha_mo_cua.wav"), dtype=np.int16)
    if pcm.size < 32000:
        pcm = np.tile(pcm, int(np.ceil(32000 / max(pcm.size, 1))))[:48000]
    b64 = base64.b64encode(pcm.tobytes()).decode("ascii")
    c3, d3 = http_json(
        "POST",
        "/api/auth3/guest/enroll_voice",
        {
            "guest_session_id": sess or "",
            "guest_name": "Kẻ giả giọng chủ",
            "duration_type": "1d",
            "pcm16k_b64": b64,
        },
    )
    rejected = not (isinstance(d3, dict) and d3.get("ok"))
    dupish = rejected and (
        "DUPLICATE" in str(d3).upper()
        or "TRUNG" in str(d3).upper()
        or "trùng" in str(d3).lower()
        or c3 == 400
    )
    record(
        "S39",
        "HTTP guest enroll bằng giọng chủ nhà → chống trùng",
        "PASS" if dupish else ("FAIL" if not rejected else "QUESTIONABLE"),
        f"HTTP {c3} rejected={rejected} resp={str(d3)[:200]}",
        "400 DUPLICATE_VOICE_REJECTED / không lưu C3",
        "" if dupish else "server.api_auth3_guest_enroll_voice / check_duplicate_voice_gate",
        d3,
    )


def scen_profiles_endpoint(rng: random.Random) -> None:
    c, d = http_json("GET", "/api/voice_auth/profiles")
    ok = c == 200 and isinstance(d, dict) and "profiles" in d and "owner_voice_1" in (d.get("profiles") or {})
    record(
        "S40",
        "GET /api/voice_auth/profiles có owner_voice_1",
        "PASS" if ok else "FAIL",
        f"HTTP {c} n_profiles={len((d or {}).get('profiles') or {}) if isinstance(d, dict) else 'x'}",
        "Có hồ sơ Cấp 1",
        "" if ok else "voiceprints / VoiceAuthManager",
        list(((d or {}).get("profiles") or {}).keys())[:10] if isinstance(d, dict) else d,
    )


def run_pytest() -> dict[str, Any]:
    out_log = OUT / "pytest_reference.log"
    cmd = [
        sys.executable,
        "-X",
        "utf8",
        "-m",
        "pytest",
        "tests/e2e/test_all_36_project_flows.py",
        "tests/test_adversarial_dsp.py",
        "-q",
        "--tb=no",
        "--maxfail=20",
    ]
    try:
        p = subprocess.run(
            cmd,
            cwd=str(PROJ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        text = (p.stdout or "") + "\n" + (p.stderr or "")
        out_log.write_text(text, encoding="utf-8")
        return {"returncode": p.returncode, "tail": "\n".join(text.strip().splitlines()[-30:]), "log": str(out_log)}
    except Exception as e:
        out_log.write_text(traceback.format_exc(), encoding="utf-8")
        return {"returncode": -1, "tail": str(e), "log": str(out_log)}


def write_report(pre_hashes: dict[str, str], restore_info: dict[str, Any], pytest_info: dict[str, Any]) -> Path:
    counts = {"PASS": 0, "FAIL": 0, "QUESTIONABLE": 0}
    for r in RESULTS:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    lines = []
    lines.append("# Báo cáo kiểm thử luồng ngẫu nhiên / đối kháng")
    lines.append("")
    lines.append(f"- Thời gian (Asia/Saigon): {time.strftime('%Y-%m-%d %H:%M:%S')} (UTC+7)")
    lines.append(f"- Seed: `{SEED}`")
    lines.append(f"- Dự án: `{PROJ}`")
    lines.append(f"- Server: `{BASE}`")
    lines.append(f"- Backup: `{BACKUP}`")
    lines.append(f"- Tổng: **{len(RESULTS)}** tình huống — PASS={counts['PASS']} FAIL={counts['FAIL']} QUESTIONABLE={counts['QUESTIONABLE']}")
    lines.append("")
    lines.append("## Pytest tham chiếu")
    lines.append(f"- returncode: `{pytest_info.get('returncode')}`")
    lines.append("```")
    lines.append(str(pytest_info.get("tail") or "")[:4000])
    lines.append("```")
    lines.append("")
    lines.append("## Khôi phục dữ liệu")
    lines.append(f"- verify_ok: **{restore_info.get('verify_ok')}**")
    lines.append(f"- restored_files: {len(restore_info.get('restored') or [])}")
    if restore_info.get("mismatch_after"):
        lines.append(f"- mismatch_after: {restore_info['mismatch_after']}")
    lines.append("")
    lines.append("> Lưu ý: tiến trình FastAPI đang chạy trên :8088 có thể vẫn giữ state trong RAM sau khi restore file; cần restart server nếu muốn memory khớp disk.")
    lines.append("")
    lines.append("## Các FAIL")
    fails = [r for r in RESULTS if r["verdict"] == "FAIL"]
    if not fails:
        lines.append("_Không có._")
    for r in fails:
        lines.append(f"### {r['id']} — {r['title']}")
        lines.append(f"- Quan sát: {r['observed']}")
        lines.append(f"- Kỳ vọng: {r['expected']}")
        lines.append(f"- Nghi ngờ: `{r['fault']}`")
        lines.append("")
    lines.append("## Các QUESTIONABLE")
    qs = [r for r in RESULTS if r["verdict"] == "QUESTIONABLE"]
    if not qs:
        lines.append("_Không có._")
    for r in qs:
        lines.append(f"### {r['id']} — {r['title']}")
        lines.append(f"- Quan sát: {r['observed']}")
        lines.append(f"- Kỳ vọng/ghi chú: {r['expected']}")
        lines.append(f"- Liên quan: `{r['fault']}`")
        lines.append("")
    lines.append("## Toàn bộ kết quả")
    for r in RESULTS:
        lines.append(f"- **{r['verdict']}** `{r['id']}` {r['title']}: {r['observed']}")
    lines.append("")
    path = OUT / "REPORT.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    (OUT / "results.json").write_text(json.dumps({"seed": SEED, "counts": counts, "results": RESULTS, "pytest": pytest_info, "restore": restore_info}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    print("PROJ", PROJ)
    print("Backing up data...")
    pre = backup_data()
    print("Backup hashes", len(pre))

    # connectivity
    scen_http_state_ok(rng)

    http_scens = [
        scen_guest_spoof_tier_open_door,
        scen_guest_tier3_claim_open_door,
        scen_guest_allowed_light,
        scen_qr_generate_and_reuse,
        scen_qr_expired_window,
        scen_qr_tier3_issuer_blocked,
        scen_qr_bad_duration,
        scen_soil_auto_pump,
        scen_manual_off_vs_soil_rule,
        scen_dht11_absurd,
        scen_soil_nan,
        scen_offline_door_lock,
        scen_text_ambiguous,
        scen_text_no_auth_door,
        scen_rapid_fire,
        scen_malformed_api,
        scen_email_mismatch_and_fake_mx,
        scen_add_family_email_rbac,
        scen_already_in_state,
        scen_schedule_guest_timer,
        scen_guest_enroll_http_duplicate,
        scen_profiles_endpoint,
    ]
    for fn in http_scens:
        try:
            fn(rng)
        except Exception as e:
            record(fn.__name__, fn.__name__, "FAIL", f"Exception: {e}", "Chạy không crash", fn.__name__, traceback.format_exc()[-500:])

    try:
        scen_dsp_suite(rng)
    except Exception as e:
        record("S25-35", "DSP suite", "FAIL", f"Exception: {e}", "Chạy DSP", "voice_auth", traceback.format_exc()[-800:])

    for fn in (scen_auth3_inprocess_qr, scen_engine_rbac_inprocess, scen_engine_member_rbac):
        try:
            fn(rng)
        except Exception as e:
            record(fn.__name__, fn.__name__, "FAIL", f"Exception: {e}", "OK", fn.__name__, traceback.format_exc()[-500:])

    print("Running pytest reference...")
    pytest_info = run_pytest()
    print("pytest", pytest_info.get("returncode"))

    # best-effort revert live devices/sensors before restore
    try:
        http_json("POST", "/api/server_mode", {"server_connected": True})
        http_json("POST", "/api/soil_moisture", {"soil_moisture_pct": 62})
        http_json("POST", "/api/dht11", {"temp_c": 28.5, "humidity_pct": 65.0})
        for dev, act in [
            ("main_door", "close"),
            ("living_room_light", "turn_off"),
            ("bedroom_light", "turn_off"),
            ("fan", "turn_off"),
            ("ac", "turn_off"),
            ("alarm_siren", "turn_off"),
            ("garden_pump", "turn_off"),
        ]:
            http_json("POST", "/api/device", {"device_id": dev, "action": act, "tier": 1})
    except Exception:
        pass

    print("Restoring data...")
    restore_info = restore_data(pre)
    print("restore_ok", restore_info.get("verify_ok"))

    report = write_report(pre, restore_info, pytest_info)
    print("REPORT", report)
    counts = {"PASS": 0, "FAIL": 0, "QUESTIONABLE": 0}
    for r in RESULTS:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    summary = {
        "seed": SEED,
        "counts": counts,
        "report": str(report),
        "restore_ok": restore_info.get("verify_ok"),
        "fails": [r for r in RESULTS if r["verdict"] == "FAIL"],
        "questionable": [r for r in RESULTS if r["verdict"] == "QUESTIONABLE"],
        "pytest_rc": pytest_info.get("returncode"),
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"seed": SEED, "counts": counts, "restore_ok": restore_info.get("verify_ok"), "pytest_rc": pytest_info.get("returncode")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
