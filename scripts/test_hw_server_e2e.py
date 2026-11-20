"""Self-contained Hardware-Simulator <-> Server (port 8097) E2E & Performance Benchmark.

Verifies the locked 6-actuator / 3-sensor / 10-pin ESP8266 contract over:
1. Isolated uvicorn server on 127.0.0.1:8097 (isolated SQLite WAL + temp dirs).
2. Embedded pure-Python MQTT 3.1.1 TCP broker + paho-mqtt 2.2.0 + SmartHomeMQTTBridge.
3. All 6 actuators (D1/D0/D4/D6/D8/D7), soil hysteresis (<40% ON / >=70% OFF),
   DHT11 (D2), KY-037 sound sensor (D5), voice "ok" confirmation gate, retired
   /api/ir_learn (410), SCENE_SPEC.json (404/200), and zero fan/ac/ir.
4. Performance benchmarks (N >= 30) for HTTP GET /api/state, HTTP POST /api/device,
   MQTT QoS 1 Pub/Sub round-trip, and SSE /api/events push latency (p50 & p95 ms).
"""
from __future__ import annotations

import asyncio
import copy
import json
import math
import os
import pathlib
import queue
import secrets
import shutil
import socket
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from typing import Any

import httpx
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8097
BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

EXPECTED_6_DEVICES = [
    "main_door",
    "living_room_light",
    "bedroom_light",
    "garden_pump",
    "alarm_siren",
    "speaker_amp",
]

EXPECTED_PINOUT = {
    "main_door": ("D1", 5, "open", "OPEN"),
    "living_room_light": ("D0", 16, "turn_on", "ON"),
    "bedroom_light": ("D4", 2, "turn_on", "ON"),
    "garden_pump": ("D6", 12, "turn_on", "ON"),
    "alarm_siren": ("D8", 15, "turn_on", "ON"),
    "speaker_amp": ("D7", 13, "turn_on", "ON"),
}

BENCHMARK_ITERATIONS = 35


def _assert_port_free(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        if sock.connect_ex((host, port)) == 0:
            raise RuntimeError(f"Port {host}:{port} is already in use; aborting E2E test.")


def _percentile_ms(samples: list[float], pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    k = (len(ordered) - 1) * (pct / 100.0)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return round(ordered[lo], 3)
    val = ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)
    return round(val, 3)


def _compute_stats(samples: list[float]) -> dict[str, Any]:
    return {
        "n": len(samples),
        "min_ms": round(min(samples), 3) if samples else 0.0,
        "p50_ms": _percentile_ms(samples, 50.0),
        "p95_ms": _percentile_ms(samples, 95.0),
        "max_ms": round(max(samples), 3) if samples else 0.0,
        "mean_ms": round(sum(samples) / len(samples), 3) if samples else 0.0,
    }


def _mqtt_topic_matches(topic_filter: str, topic: str) -> bool:
    if not topic_filter or not topic:
        return False
    if topic.startswith("$") and topic_filter[0] in ("+", "#"):
        return False
    if topic_filter == topic:
        return True
    f_parts = topic_filter.split("/")
    t_parts = topic.split("/")
    for idx, f_seg in enumerate(f_parts):
        if f_seg == "#":
            return idx == len(f_parts) - 1
        if idx >= len(t_parts):
            return False
        if f_seg != "+" and f_seg != t_parts[idx]:
            return False
    return len(f_parts) == len(t_parts)


def _encode_remaining_length(length: int) -> bytes:
    out = bytearray()
    val = length
    while True:
        encoded = val % 128
        val //= 128
        if val > 0:
            encoded |= 0x80
        out.append(encoded)
        if val == 0:
            break
    return bytes(out)


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        chunk = sock.recv(count - len(chunks))
        if not chunk:
            raise EOFError("MQTT client socket closed")
        chunks.extend(chunk)
    return bytes(chunks)


def _decode_remaining_length(sock: socket.socket) -> int:
    multiplier = 1
    value = 0
    for _ in range(4):
        byte_val = _recv_exact(sock, 1)[0]
        value += (byte_val & 0x7F) * multiplier
        if (byte_val & 0x80) == 0:
            return value
        multiplier *= 128
    raise ValueError("Malformed MQTT remaining length")


def _encode_utf8(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("!H", len(raw)) + raw


def _read_utf8(buf: bytes, offset: int) -> tuple[str, int]:
    if offset + 2 > len(buf):
        raise ValueError("Truncated UTF-8 length")
    slen = struct.unpack("!H", buf[offset : offset + 2])[0]
    offset += 2
    if offset + slen > len(buf):
        raise ValueError("Truncated UTF-8 body")
    return buf[offset : offset + slen].decode("utf-8", errors="replace"), offset + slen


def _build_publish_packet(
    topic: str,
    payload: bytes,
    qos: int = 0,
    retain: bool = False,
    packet_id: int | None = None,
) -> bytes:
    flags = ((qos & 0x03) << 1) | (1 if retain else 0)
    header_byte = 0x30 | flags
    var_header = bytearray(_encode_utf8(topic))
    if qos > 0:
        var_header.extend(struct.pack("!H", packet_id or 1))
    body = bytes(var_header) + payload
    return bytes([header_byte]) + _encode_remaining_length(len(body)) + body


class _BrokerClientState:
    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.send_lock = threading.Lock()
        self.client_id = ""
        self.clean_disconnect = False
        self.will_topic: str | None = None
        self.will_payload: bytes = b""
        self.will_qos: int = 0
        self.will_retain: bool = False

    def send_packet(self, data: bytes) -> bool:
        try:
            with self.send_lock:
                self.sock.sendall(data)
            return True
        except OSError:
            return False


class _MQTT311Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        broker: EmbeddedMQTTBroker = self.server  # type: ignore[assignment]
        state = _BrokerClientState(self.request)
        self.request.settimeout(30.0)
        broker.register_client(state)
        try:
            while True:
                try:
                    b1 = _recv_exact(self.request, 1)[0]
                except socket.timeout:
                    continue
                pkt_type = (b1 >> 4) & 0x0F
                flags = b1 & 0x0F
                rem_len = _decode_remaining_length(self.request)
                payload = _recv_exact(self.request, rem_len) if rem_len > 0 else b""

                if pkt_type == 1:  # CONNECT
                    proto_name, off = _read_utf8(payload, 0)
                    _proto_level = payload[off]
                    conn_flags = payload[off + 1]
                    _keepalive = struct.unpack("!H", payload[off + 2 : off + 4])[0]
                    off += 4
                    client_id, off = _read_utf8(payload, off)
                    state.client_id = client_id
                    if conn_flags & 0x04:  # Will flag
                        state.will_qos = (conn_flags >> 3) & 0x03
                        state.will_retain = bool((conn_flags >> 5) & 0x01)
                        w_topic, off = _read_utf8(payload, off)
                        w_len = struct.unpack("!H", payload[off : off + 2])[0]
                        off += 2
                        w_payload = payload[off : off + w_len]
                        state.will_topic = w_topic
                        state.will_payload = w_payload
                    state.send_packet(b"\x20\x02\x00\x00")  # CONNACK accepted

                elif pkt_type == 8:  # SUBSCRIBE
                    pkt_id = struct.unpack("!H", payload[:2])[0]
                    off = 2
                    granted: list[int] = []
                    new_filters: list[tuple[str, int]] = []
                    while off < len(payload):
                        t_filter, off = _read_utf8(payload, off)
                        req_qos = payload[off] & 0x03
                        off += 1
                        grant_qos = min(req_qos, 1)
                        granted.append(grant_qos)
                        new_filters.append((t_filter, grant_qos))
                    broker.add_subscriptions(state, new_filters)
                    suback = bytes([0x90]) + _encode_remaining_length(2 + len(granted)) + struct.pack("!H", pkt_id) + bytes(granted)
                    state.send_packet(suback)
                    broker.deliver_retained(state, new_filters)

                elif pkt_type == 10:  # UNSUBSCRIBE
                    pkt_id = struct.unpack("!H", payload[:2])[0]
                    off = 2
                    filters: list[str] = []
                    while off < len(payload):
                        t_filter, off = _read_utf8(payload, off)
                        filters.append(t_filter)
                    broker.remove_subscriptions(state, filters)
                    state.send_packet(b"\xb0\x02" + struct.pack("!H", pkt_id))

                elif pkt_type == 3:  # PUBLISH
                    qos = (flags >> 1) & 0x03
                    retain = bool(flags & 0x01)
                    topic, off = _read_utf8(payload, 0)
                    pkt_id = None
                    if qos > 0:
                        pkt_id = struct.unpack("!H", payload[off : off + 2])[0]
                        off += 2
                    msg_body = payload[off:]
                    if qos == 1 and pkt_id is not None:
                        state.send_packet(b"\x40\x02" + struct.pack("!H", pkt_id))
                    broker.dispatch_publish(topic, msg_body, qos=qos, retain=retain)

                elif pkt_type == 4:  # PUBACK
                    continue

                elif pkt_type == 12:  # PINGREQ
                    state.send_packet(b"\xd0\x00")

                elif pkt_type == 14:  # DISCONNECT
                    state.clean_disconnect = True
                    break
        except (EOFError, OSError, ValueError):
            pass
        finally:
            broker.unregister_client(state)
            if not state.clean_disconnect and state.will_topic:
                broker.dispatch_publish(
                    state.will_topic,
                    state.will_payload,
                    qos=state.will_qos,
                    retain=state.will_retain,
                )


class EmbeddedMQTTBroker(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._lock = threading.Lock()
        self._clients: set[_BrokerClientState] = set()
        self._subs: dict[_BrokerClientState, dict[str, int]] = {}
        self._retained: dict[str, tuple[int, bytes]] = {}
        self._next_packet_id = 1
        super().__init__((host, port), _MQTT311Handler)
        self.port: int = int(self.server_address[1])

    def _alloc_packet_id(self) -> int:
        pid = self._next_packet_id
        self._next_packet_id = 1 if pid >= 65535 else pid + 1
        return pid

    def register_client(self, client: _BrokerClientState) -> None:
        with self._lock:
            self._clients.add(client)
            self._subs.setdefault(client, {})

    def unregister_client(self, client: _BrokerClientState) -> None:
        with self._lock:
            self._clients.discard(client)
            self._subs.pop(client, None)

    def add_subscriptions(self, client: _BrokerClientState, filters: list[tuple[str, int]]) -> None:
        with self._lock:
            cmap = self._subs.setdefault(client, {})
            for t_filter, qos in filters:
                cmap[t_filter] = qos

    def remove_subscriptions(self, client: _BrokerClientState, filters: list[str]) -> None:
        with self._lock:
            cmap = self._subs.get(client)
            if cmap:
                for t_filter in filters:
                    cmap.pop(t_filter, None)

    def deliver_retained(self, client: _BrokerClientState, filters: list[tuple[str, int]]) -> None:
        deliveries: list[bytes] = []
        with self._lock:
            for topic, (ret_qos, payload) in self._retained.items():
                matched_qos = [sq for tf, sq in filters if _mqtt_topic_matches(tf, topic)]
                if not matched_qos:
                    continue
                eff_qos = min(ret_qos, max(matched_qos))
                pid = self._alloc_packet_id() if eff_qos > 0 else None
                deliveries.append(_build_publish_packet(topic, payload, qos=eff_qos, retain=True, packet_id=pid))
        for pkt in deliveries:
            client.send_packet(pkt)

    def dispatch_publish(self, topic: str, payload: bytes, qos: int = 0, retain: bool = False) -> None:
        targets: list[tuple[_BrokerClientState, bytes]] = []
        with self._lock:
            if retain:
                if len(payload) == 0:
                    self._retained.pop(topic, None)
                else:
                    self._retained[topic] = (min(qos, 1), payload)
            for client, cmap in list(self._subs.items()):
                matched = [sq for tf, sq in cmap.items() if _mqtt_topic_matches(tf, topic)]
                if not matched:
                    continue
                eff_qos = min(qos, max(matched), 1)
                pid = self._alloc_packet_id() if eff_qos > 0 else None
                pkt = _build_publish_packet(topic, payload, qos=eff_qos, retain=False, packet_id=pid)
                targets.append((client, pkt))
        for client, pkt in targets:
            client.send_packet(pkt)


def _setup_isolated_environment() -> tuple[tempfile.TemporaryDirectory[str], dict[str, str], str, str]:
    tmp = tempfile.TemporaryDirectory(prefix="smarthome_hw_e2e_")
    tmp_root = pathlib.Path(tmp.name)
    data_dir = tmp_root / "data"
    vault_dir = tmp_root / "vault"
    logs_dir = tmp_root / "logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    vault_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    repo_data = ROOT / "simulator" / "data"
    if repo_data.exists():
        for src in repo_data.iterdir():
            if not src.is_file():
                continue
            if src.name.startswith("smarthome.db") or src.name.startswith(".tx_") or src.name == "ir_devices_db.json":
                continue
            shutil.copy2(src, data_dir / src.name)

    db_path = data_dir / "smarthome.db"
    hw_key = f"hw_e2e_{secrets.token_hex(12)}"

    isolated_vars = {
        "SMARTHOME_DATA_DIR": str(data_dir),
        "SMARTHOME_SQLITE_PATH": str(db_path),
        "SMARTHOME_LOG_DIR": str(logs_dir),
        "SMARTHOME_DURABLE_DIR": str(vault_dir),
        "SIMULATOR_SECURITY_STATE_DIR": str(data_dir),
        "SMARTHOME_STATE_BACKEND": "sqlite",
        "SIMULATOR_OFFLINE_SANDBOX": "1",
        "SMARTHOME_SKIP_PREWARM": "1",
        "DISABLE_REAL_EMAIL": "1",
        "GEMINI_API_KEY": "test_dummy_key_12345",
        "PYTEST": "1",
        "SMARTHOME_HARDWARE_API_KEY": hw_key,
        "PYTHONUTF8": "1",
    }
    for k, v in isolated_vars.items():
        os.environ[k] = v
    for unset_key in ("VERCEL", "PYTEST_CURRENT_TEST", "SMARTHOME_FORCE_CLOUD_DURABLE"):
        os.environ.pop(unset_key, None)

    from simulator.auth_3layer import hash_password
    from simulator.voice_config import OWNER_EMAIL
    from scripts.migrate_to_sqlite import migrate_all

    acct_file = data_dir / "accounts_3layer.json"
    accounts = json.loads(acct_file.read_text(encoding="utf-8"))
    owner_password = secrets.token_urlsafe(24)
    for acc in accounts:
        acc.pop("pending_otp", None)
        if str(acc.get("email") or "").lower() == OWNER_EMAIL.lower():
            acc["password_hash"] = hash_password(owner_password)
    acct_file.write_text(json.dumps(accounts, ensure_ascii=False, indent=2), encoding="utf-8")

    mig = migrate_all(
        target_db=db_path,
        source_dir=data_dir,
        fetch_github=False,
        seed_assets=False,
        upgrade_repo_db=False,
    )
    if not mig.get("ok"):
        raise RuntimeError(f"migrate_all failed: {mig}")

    server_env = os.environ.copy()
    return tmp, server_env, owner_password, hw_key


class _SSEStreamReader:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url
        self.token = token
        self.events: queue.Queue[tuple[str, dict[str, Any], float]] = queue.Queue()
        self._stop_event = threading.Event()
        self._connected = threading.Event()
        self._error: Exception | None = None
        self._thread = threading.Thread(target=self._run, name="e2e-sse-reader", daemon=True)
        self._client: httpx.Client | None = None

    def start(self) -> None:
        self._thread.start()
        if not self._connected.wait(timeout=8.0):
            raise RuntimeError(f"SSE stream did not connect in time: {self._error}")

    def stop(self) -> None:
        self._stop_event.set()
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._thread.join(timeout=3.0)

    def drain(self) -> None:
        while True:
            try:
                self.events.get_nowait()
            except queue.Empty:
                break

    def wait_for_snapshot(
        self,
        predicate: Any,
        timeout: float = 5.0,
    ) -> tuple[dict[str, Any], float]:
        deadline = time.perf_counter() + timeout
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise TimeoutError("Timed out waiting for matching SSE state_snapshot")
            ev_name, payload, recv_ts = self.events.get(timeout=remaining)
            if ev_name != "state_snapshot":
                continue
            if predicate(payload):
                return payload, recv_ts

    def _run(self) -> None:
        try:
            self._client = httpx.Client(
                timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
            )
            with self._client.stream(
                "GET",
                f"{self.base_url}/api/events",
                headers={"X-Session-Token": self.token},
            ) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"SSE returned status {resp.status_code}")
                self._connected.set()
                ev_name = "message"
                data_lines: list[str] = []
                for line in resp.iter_lines():
                    if self._stop_event.is_set():
                        break
                    if line == "":
                        if data_lines:
                            raw_json = "\n".join(data_lines)
                            try:
                                parsed = json.loads(raw_json)
                            except json.JSONDecodeError:
                                parsed = {"raw": raw_json}
                            self.events.put((ev_name, parsed, time.perf_counter()))
                        ev_name = "message"
                        data_lines = []
                    elif line.startswith(":"):
                        continue
                    elif line.startswith("event:"):
                        ev_name = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].strip())
        except Exception as exc:
            self._error = exc
            self._connected.set()


def _device_state_map(snapshot: dict[str, Any]) -> dict[str, str]:
    devices = snapshot.get("devices") or []
    return {str(d["id"]): str(d["state"]) for d in devices if isinstance(d, dict) and "id" in d}


def run_e2e() -> dict[str, Any]:
    _assert_port_free(SERVER_HOST, SERVER_PORT)
    tmp_dir, server_env, owner_password, hw_key = _setup_isolated_environment()

    from simulator.mqtt_bridge import SmartHomeMQTTBridge

    broker = EmbeddedMQTTBroker(SERVER_HOST, 0)
    broker_thread = threading.Thread(target=broker.serve_forever, name="e2e-mqtt-broker", daemon=True)
    broker_thread.start()

    uvicorn_proc: subprocess.Popen[str] | None = None
    http_client: httpx.Client | None = None
    sse_reader: _SSEStreamReader | None = None
    esp_client: mqtt.Client | None = None
    monitor_client: mqtt.Client | None = None

    try:
        # 1. Start isolated uvicorn on port 8097
        uvicorn_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "simulator.server:app",
                "--host",
                SERVER_HOST,
                "--port",
                str(SERVER_PORT),
                "--log-level",
                "warning",
            ],
            cwd=str(ROOT),
            env=server_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        http_client = httpx.Client(
            base_url=BASE_URL,
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
        )

        health_data: dict[str, Any] = {}
        deadline = time.perf_counter() + 25.0
        while time.perf_counter() < deadline:
            if uvicorn_proc.poll() is not None:
                out, err = uvicorn_proc.communicate(timeout=2)
                raise RuntimeError(f"uvicorn exited prematurely ({uvicorn_proc.returncode}): {out} {err}")
            try:
                r = http_client.get("/api/health")
                if r.status_code == 200:
                    body = r.json()
                    if body.get("sqlite_ok") is True:
                        health_data = body
                        break
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        else:
            raise TimeoutError("Timed out waiting for /api/health sqlite_ok=True on port 8097")

        assert health_data.get("voice_model") == "gemini-3.8-live", health_data
        assert health_data.get("single_voice") == "Aoede", health_data

        # 2. Authenticate Owner via Layer 1 + Layer 2 OTP
        r1 = http_client.post(
            "/api/auth3/layer1_login",
            json={"email": "nep94121@gmail.com", "password": owner_password, "send_gmail": False},
        )
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1.get("ok") is True, d1
        otp_code = d1.get("otp_code_for_test")
        assert otp_code, f"Missing otp_code_for_test: {d1}"

        r2 = http_client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": "nep94121@gmail.com", "otp_code": otp_code},
        )
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        owner_token = str(d2.get("session_token") or "")
        assert owner_token, f"Missing owner session_token: {d2}"

        owner_headers = {"X-Session-Token": owner_token}
        hw_headers = {"X-Hardware-Key": hw_key}

        # 3. Connect paho-mqtt 2.2.0 ESP8266 simulator + Monitor client to embedded broker
        mqtt_lock = threading.Lock()
        esp_connected = threading.Event()
        mon_connected = threading.Event()
        mon_suback = threading.Event()
        esp_suback = threading.Event()
        esp_msgs: list[tuple[str, dict[str, Any], float]] = []
        mon_msgs: list[tuple[str, dict[str, Any], bool, float]] = []
        mon_notify = threading.Condition(mqtt_lock)

        def _on_esp_connect(client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
            if reason_code == 0 or getattr(reason_code, "value", 0) == 0:
                client.subscribe([("smarthome/cmd/#", 1), ("smarthome/sync/pools", 1)])
                esp_connected.set()

        def _on_esp_sub(client: mqtt.Client, userdata: Any, mid: int, reason_code_list: Any, properties: Any) -> None:
            esp_suback.set()

        def _on_esp_msg(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
            ts = time.perf_counter()
            payload = json.loads(msg.payload.decode("utf-8"))
            with mqtt_lock:
                esp_msgs.append((msg.topic, payload, ts))

        def _on_mon_connect(client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
            if reason_code == 0 or getattr(reason_code, "value", 0) == 0:
                client.subscribe("smarthome/#", qos=1)
                mon_connected.set()

        def _on_mon_sub(client: mqtt.Client, userdata: Any, mid: int, reason_code_list: Any, properties: Any) -> None:
            mon_suback.set()

        def _on_mon_msg(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
            ts = time.perf_counter()
            payload = json.loads(msg.payload.decode("utf-8"))
            with mon_notify:
                mon_msgs.append((msg.topic, payload, bool(msg.retain), ts))
                mon_notify.notify_all()

        monitor_client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id="e2e_monitor",
            protocol=mqtt.MQTTv311,
        )
        monitor_client.on_connect = _on_mon_connect
        monitor_client.on_subscribe = _on_mon_sub
        monitor_client.on_message = _on_mon_msg
        monitor_client.connect(SERVER_HOST, broker.port, keepalive=30)
        monitor_client.loop_start()
        assert mon_connected.wait(timeout=5.0) and mon_suback.wait(timeout=5.0), "Monitor MQTT connect/sub failed"

        esp_client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id="esp8266_node_01",
            protocol=mqtt.MQTTv311,
        )
        esp_client.will_set(
            "smarthome/status/esp8266",
            json.dumps({"node_id": "esp8266_node_01", "online": False}),
            qos=1,
            retain=True,
        )
        esp_client.on_connect = _on_esp_connect
        esp_client.on_subscribe = _on_esp_sub
        esp_client.on_message = _on_esp_msg
        esp_client.connect(SERVER_HOST, broker.port, keepalive=30)
        esp_client.loop_start()
        assert esp_connected.wait(timeout=5.0) and esp_suback.wait(timeout=5.0), "ESP8266 MQTT connect/sub failed"

        birth_info = esp_client.publish(
            "smarthome/status/esp8266",
            json.dumps({"node_id": "esp8266_node_01", "online": True, "chip": "NodeMCU ESP8266 (ESP-12E)"}),
            qos=1,
            retain=True,
        )
        birth_info.wait_for_publish(timeout=5.0)

        # Verify LWT delivery using an abrupt TCP disconnect on a probe client
        lwt_probe_sock = socket.create_connection((SERVER_HOST, broker.port), timeout=5.0)
        cid_b = _encode_utf8("lwt_probe_client")
        wt_b = _encode_utf8("smarthome/status/lwt_probe")
        wp_raw = json.dumps({"node_id": "lwt_probe", "online": False}).encode("utf-8")
        wp_b = struct.pack("!H", len(wp_raw)) + wp_raw
        connect_vh = _encode_utf8("MQTT") + bytes([4, 0x06]) + struct.pack("!H", 30)
        connect_body = connect_vh + cid_b + wt_b + wp_b
        lwt_probe_sock.sendall(b"\x10" + _encode_remaining_length(len(connect_body)) + connect_body)
        _ = _recv_exact(lwt_probe_sock, 4)  # CONNACK
        lwt_probe_sock.close()  # Abrupt EOF without DISCONNECT -> triggers LWT

        with mon_notify:
            ok_lwt = mon_notify.wait_for(
                lambda: any(t == "smarthome/status/lwt_probe" and p.get("online") is False for t, p, _, _ in mon_msgs),
                timeout=3.0,
            )
            assert ok_lwt, "Embedded MQTT broker failed to dispatch LWT on abrupt disconnect"

        # SmartHomeMQTTBridge wired to forward generated packets through the embedded broker
        async def _forward_bridge_event(ev: dict[str, Any]) -> None:
            if ev.get("type") == "mqtt_packet":
                pkt = ev["packet"]
                info = esp_client.publish(
                    pkt["topic"],
                    json.dumps(pkt["payload"], ensure_ascii=False),
                    qos=min(int(pkt.get("qos", 1)), 1),
                    retain=bool(pkt.get("retain", False)),
                )
                info.wait_for_publish(timeout=5.0)

        bridge = SmartHomeMQTTBridge(on_event=_forward_bridge_event)

        # 4. Open SSE /api/events stream and assert initial state_snapshot
        sse_reader = _SSEStreamReader(BASE_URL, owner_token)
        sse_reader.start()
        init_ev, _ = sse_reader.wait_for_snapshot(lambda p: p.get("reason") == "initial", timeout=5.0)
        init_map = _device_state_map(init_ev["snapshot"])
        assert set(init_map.keys()) == set(EXPECTED_6_DEVICES), f"Unexpected SSE initial devices: {init_map}"

        # 5. Functional Check: GET /api/state exact 6 devices, zero fan/ac/ir
        st_resp = http_client.get("/api/state", headers=owner_headers)
        assert st_resp.status_code == 200, st_resp.text
        st_json = st_resp.json()
        dev_ids = [d["id"] for d in st_json["devices"]]
        assert dev_ids == EXPECTED_6_DEVICES, f"Expected {EXPECTED_6_DEVICES}, got {dev_ids}"
        assert "fan" not in dev_ids and "ac" not in dev_ids and "ir" not in st_json

        # 6. Retired /api/ir_learn -> 410, SCENE_SPEC.json -> 404 (or 200 valid JSON if present)
        ir_resp = http_client.post("/api/ir_learn", json={"command_name": "test"}, headers=owner_headers)
        assert ir_resp.status_code == 410, f"Expected 410 from /api/ir_learn, got {ir_resp.status_code}: {ir_resp.text}"
        assert ir_resp.json().get("gone") is True

        spec_resp = http_client.get("/hardware/blender/SCENE_SPEC.json")
        if (ROOT / "hardware" / "blender" / "SCENE_SPEC.json").exists():
            assert spec_resp.status_code == 200 and isinstance(spec_resp.json(), dict)
        else:
            assert spec_resp.status_code == 404, f"Expected 404 for absent SCENE_SPEC.json, got {spec_resp.status_code}"

        # 7. Actuate ALL 6 devices via POST /api/device + GET /api/state + MQTT + SSE
        for dev_id, (exp_pin, exp_gpio, action, exp_state) in EXPECTED_PINOUT.items():
            sse_reader.drain()
            act_resp = http_client.post(
                "/api/device",
                json={"device_id": dev_id, "action": action, "source": "e2e_hw_test"},
                headers=owner_headers,
            )
            assert act_resp.status_code == 200, f"{dev_id} failed: {act_resp.text}"
            act_body = act_resp.json()
            assert act_body.get("ok") is True and act_body.get("state") == exp_state, act_body

            verify_state = _device_state_map(http_client.get("/api/state", headers=owner_headers).json())
            assert verify_state[dev_id] == exp_state, f"GET /api/state mismatch for {dev_id}: {verify_state}"

            sse_snap, _ = sse_reader.wait_for_snapshot(
                lambda p, d=dev_id, s=exp_state: _device_state_map(p.get("snapshot", {})).get(d) == s,
                timeout=5.0,
            )
            assert _device_state_map(sse_snap["snapshot"])[dev_id] == exp_state

            asyncio.run(bridge.publish_actuate_command(dev_id, exp_state, action, "e2e_hw_test", "Nguyễn Tuấn Anh", 1))
            with mon_notify:
                got_cmd = mon_notify.wait_for(
                    lambda d=dev_id, pin=exp_pin, g=exp_gpio, st=exp_state: any(
                        t == "smarthome/cmd/actuate"
                        and len(p.get("targets", [])) == 1
                        and p["targets"][0].get("device_id") == d
                        and p["targets"][0].get("pin") == pin
                        and p["targets"][0].get("gpio") == g
                        and p["targets"][0].get("state") == st
                        for t, p, _, _ in mon_msgs
                    ),
                    timeout=5.0,
                )
                assert got_cmd, f"Monitor missed smarthome/cmd/actuate for {dev_id}"
                got_rep = mon_notify.wait_for(
                    lambda d=dev_id, pin=exp_pin, st=exp_state: any(
                        t == "smarthome/state/report"
                        and p.get("device_id") == d
                        and p.get("pin") == pin
                        and p.get("state") == st
                        and p.get("ack") is True
                        for t, p, _, _ in mon_msgs
                    ),
                    timeout=5.0,
                )
                assert got_rep, f"Monitor missed smarthome/state/report for {dev_id}"

        # Verify ESP8266 client received all 6 commands via subscription
        with mqtt_lock:
            received_cmd_devs = {
                p["targets"][0]["device_id"]
                for t, p, _ in esp_msgs
                if t == "smarthome/cmd/actuate" and p.get("targets")
            }
        assert received_cmd_devs == set(EXPECTED_6_DEVICES), f"ESP missing cmd targets: {received_cmd_devs}"

        # Reset actuators back to default OFF/CLOSED and clear manual pump override via 62% soil baseline
        for dev_id in EXPECTED_6_DEVICES:
            reset_action = "close" if dev_id == "main_door" else "turn_off"
            r_rst = http_client.post(
                "/api/device",
                json={"device_id": dev_id, "action": reset_action, "source": "e2e_reset"},
                headers=owner_headers,
            )
            assert r_rst.status_code == 200, r_rst.text

        r_baseline = http_client.post("/api/soil_moisture", json={"soil_moisture_pct": 62.0}, headers=hw_headers)
        assert r_baseline.status_code == 200 and r_baseline.json().get("pump_manual_override_off") is False

        # 8. Soil moisture hysteresis: <40% -> pump ON; 55% -> stays ON; >=70% -> pump OFF
        r_dry = http_client.post("/api/soil_moisture", json={"soil_moisture_pct": 25.0}, headers=hw_headers)
        assert r_dry.status_code == 200 and r_dry.json().get("auto_action") == "AUTO_PUMP_ON", r_dry.text
        assert _device_state_map(http_client.get("/api/state", headers=owner_headers).json())["garden_pump"] == "ON"

        r_mid = http_client.post("/api/soil_moisture", json={"soil_moisture_pct": 55.0}, headers=hw_headers)
        assert r_mid.status_code == 200 and r_mid.json().get("auto_action") == "NONE", r_mid.text
        assert _device_state_map(http_client.get("/api/state", headers=owner_headers).json())["garden_pump"] == "ON"

        r_wet = http_client.post("/api/soil_moisture", json={"soil_moisture_pct": 72.0}, headers=hw_headers)
        assert r_wet.status_code == 200 and r_wet.json().get("auto_action") == "AUTO_PUMP_OFF", r_wet.text
        assert _device_state_map(http_client.get("/api/state", headers=owner_headers).json())["garden_pump"] == "OFF"

        asyncio.run(bridge.update_soil_moisture_telemetry(25.0))
        with mon_notify:
            assert mon_notify.wait_for(
                lambda: any(t == "smarthome/telemetry/soil_moisture" and p.get("sensor_pin") == "A0" for t, p, _, _ in mon_msgs),
                timeout=3.0,
            )

        # 9. DHT11 telemetry (D2 / GPIO 4)
        r_dht = http_client.post(
            "/api/dht11",
            json={"temp_c": 31.4, "humidity_pct": 58.0, "wifi_rssi_dbm": -49},
            headers=hw_headers,
        )
        assert r_dht.status_code == 200, r_dht.text
        assert r_dht.json()["telemetry"]["sensor_pin"] == "D2 (GPIO 4)"
        st_dht = http_client.get("/api/state", headers=owner_headers).json()
        assert st_dht["sensors"]["temperature_c"] == 31.4 and st_dht["sensors"]["humidity_pct"] == 58.0

        asyncio.run(bridge.update_dht11_telemetry(31.4, 58.0, -49))
        with mon_notify:
            assert mon_notify.wait_for(
                lambda: any(t == "smarthome/telemetry/dht11" and p.get("temp_c") == 31.4 for t, p, _, _ in mon_msgs),
                timeout=3.0,
            )

        # 10. KY-037 sound sensor (/api/sound_sensor, /api/ky037, MQTT smarthome/telemetry/sound, SSE)
        prev_sound_count = int(st_dht["sensors"].get("sound_event_count", 0))
        sse_reader.drain()
        r_snd1 = http_client.post(
            "/api/sound_sensor",
            json={"sound_detected": True, "do_state": 1, "note": "e2e_clap_1"},
            headers=hw_headers,
        )
        assert r_snd1.status_code == 200, r_snd1.text
        t_snd1 = r_snd1.json()["telemetry"]
        assert t_snd1["sensor_pin"] == "D5 (GPIO 14)"
        assert t_snd1["event_count"] == prev_sound_count + 1

        st_snd1 = http_client.get("/api/state", headers=owner_headers).json()
        assert st_snd1["sensors"]["sound_detected"] is True
        assert st_snd1["sensors"]["sound_pin"] == "D5 (GPIO 14)"
        assert st_snd1["sensors"]["sound_event_count"] == prev_sound_count + 1

        sse_snd, _ = sse_reader.wait_for_snapshot(
            lambda p: (p.get("snapshot", {}).get("sensors") or {}).get("sound_event_count") == prev_sound_count + 1,
            timeout=5.0,
        )
        assert sse_snd["snapshot"]["sensors"]["sound_detected"] is True

        r_snd2 = http_client.post(
            "/api/ky037",
            json={"sound_detected": True, "do_state": 1, "note": "e2e_clap_2"},
            headers=hw_headers,
        )
        assert r_snd2.status_code == 200 and r_snd2.json()["telemetry"]["event_count"] == prev_sound_count + 2

        asyncio.run(bridge.update_sound_telemetry(sound_detected=True, do_state=1, note="mqtt_clap"))
        asyncio.run(bridge.sync_pools_to_esp8266_flash([], [], {"device_min_tiers": {"speaker_amp": 2}}))
        with mon_notify:
            assert mon_notify.wait_for(
                lambda: any(t == "smarthome/telemetry/sound" and p.get("sensor_pin") == "D5" and p.get("sound_detected") is True for t, p, _, _ in mon_msgs),
                timeout=3.0,
            )
            assert mon_notify.wait_for(
                lambda: any(t == "smarthome/sync/pools" for t, _, _, _ in mon_msgs),
                timeout=3.0,
            )

        # 11. Voice "ok" confirmation gate + removed device rejection ("Bật quạt trần")
        assert _device_state_map(http_client.get("/api/state", headers=owner_headers).json())["main_door"] == "CLOSED"

        v_step1 = http_client.post(
            "/api/voice_command",
            json={"transcript": "Mở cửa chính"},
            headers=owner_headers,
        )
        assert v_step1.status_code == 200, v_step1.text
        v1_body = v_step1.json()
        assert v1_body.get("requires_confirmation") is True, v1_body
        assert v1_body.get("executed") is False, v1_body
        assert _device_state_map(http_client.get("/api/state", headers=owner_headers).json())["main_door"] == "CLOSED"

        v_step2 = http_client.post(
            "/api/voice_command",
            json={"transcript": "ok"},
            headers=owner_headers,
        )
        assert v_step2.status_code == 200, v_step2.text
        v2_body = v_step2.json()
        assert v2_body.get("executed") is True, v2_body
        assert v2_body.get("confirmed") is True, v2_body
        assert _device_state_map(http_client.get("/api/state", headers=owner_headers).json())["main_door"] == "OPEN"

        # Close main_door cleanly before removed-device check
        http_client.post("/api/device", json={"device_id": "main_door", "action": "close"}, headers=owner_headers)
        pre_removed_map = _device_state_map(http_client.get("/api/state", headers=owner_headers).json())

        v_removed = http_client.post(
            "/api/voice_command",
            json={"transcript": "Bật quạt trần"},
            headers=owner_headers,
        )
        assert v_removed.status_code == 200, v_removed.text
        vr_body = v_removed.json()
        assert vr_body.get("executed") is False, vr_body
        assert not vr_body.get("requires_confirmation"), vr_body
        post_removed_map = _device_state_map(http_client.get("/api/state", headers=owner_headers).json())
        assert post_removed_map == pre_removed_map, f"State mutated on removed device command: {post_removed_map}"
        assert "fan" not in post_removed_map and "ac" not in post_removed_map

        # 12. Performance Benchmarks (N >= 30 per metric)
        # Warmup 3 calls
        for _ in range(3):
            http_client.get("/api/state", headers=owner_headers)

        get_state_ms: list[float] = []
        for _ in range(BENCHMARK_ITERATIONS):
            t0 = time.perf_counter()
            rg = http_client.get("/api/state", headers=owner_headers)
            dt = (time.perf_counter() - t0) * 1000.0
            assert rg.status_code == 200
            get_state_ms.append(dt)

        post_device_ms: list[float] = []
        for i in range(BENCHMARK_ITERATIONS):
            act = "turn_on" if (i % 2 == 0) else "turn_off"
            t0 = time.perf_counter()
            rp = http_client.post(
                "/api/device",
                json={"device_id": "living_room_light", "action": act, "source": "e2e_bench"},
                headers=owner_headers,
            )
            dt = (time.perf_counter() - t0) * 1000.0
            assert rp.status_code == 200
            post_device_ms.append(dt)

        mqtt_rtt_ms: list[float] = []
        for i in range(BENCHMARK_ITERATIONS):
            nonce = f"bench_{i}_{secrets.token_hex(4)}"
            t0 = time.perf_counter()
            pinfo = esp_client.publish(
                "smarthome/telemetry/bench",
                json.dumps({"nonce": nonce}),
                qos=1,
                retain=False,
            )
            pinfo.wait_for_publish(timeout=5.0)
            with mon_notify:
                matched_ts: list[float] = []

                def _find_bench() -> bool:
                    for t, p, _, rts in mon_msgs:
                        if t == "smarthome/telemetry/bench" and p.get("nonce") == nonce:
                            matched_ts.append(rts)
                            return True
                    return False

                ok_m = mon_notify.wait_for(_find_bench, timeout=5.0)
                assert ok_m, f"MQTT bench packet {nonce} timed out"
                mqtt_rtt_ms.append((matched_ts[0] - t0) * 1000.0)

        sse_push_ms: list[float] = []
        # Ensure bedroom_light is OFF before starting alternating SSE benchmark
        http_client.post("/api/device", json={"device_id": "bedroom_light", "action": "turn_off"}, headers=owner_headers)
        time.sleep(0.05)
        sse_reader.drain()
        for i in range(BENCHMARK_ITERATIONS):
            act = "turn_on" if (i % 2 == 0) else "turn_off"
            exp_st = "ON" if (i % 2 == 0) else "OFF"
            sse_reader.drain()
            t0 = time.perf_counter()
            rp = http_client.post(
                "/api/device",
                json={"device_id": "bedroom_light", "action": act, "source": "e2e_sse_bench"},
                headers=owner_headers,
            )
            assert rp.status_code == 200
            _, recv_ts = sse_reader.wait_for_snapshot(
                lambda p, s=exp_st: _device_state_map(p.get("snapshot", {})).get("bedroom_light") == s,
                timeout=5.0,
            )
            sse_push_ms.append((recv_ts - t0) * 1000.0)

        summary = {
            "ok": True,
            "server_url": BASE_URL,
            "mqtt_broker": f"{SERVER_HOST}:{broker.port}",
            "devices": dev_ids,
            "voice_model": health_data.get("voice_model"),
            "single_voice": health_data.get("single_voice"),
            "checks": {
                "health_sqlite_wal": True,
                "owner_auth_3layer": True,
                "exact_6_devices_zero_fan_ac_ir": True,
                "ir_learn_410": True,
                "scene_spec_route": spec_resp.status_code,
                "all_6_actuators_http_mqtt_sse": True,
                "mqtt_lwt_and_birth": True,
                "soil_hysteresis_lt40_ge70": True,
                "dht11_d2": True,
                "ky037_d5_http_mqtt_sse": True,
                "voice_ok_confirmation_gate": True,
                "removed_fan_voice_no_actuation": True,
            },
            "benchmarks_ms": {
                "http_get_state": _compute_stats(get_state_ms),
                "http_post_device": _compute_stats(post_device_ms),
                "mqtt_qos1_pubsub_rtt": _compute_stats(mqtt_rtt_ms),
                "sse_push_latency": _compute_stats(sse_push_ms),
            },
        }
        return summary
    finally:
        if sse_reader is not None:
            sse_reader.stop()
        if http_client is not None:
            try:
                http_client.close()
            except Exception:
                pass
        for cli in (esp_client, monitor_client):
            if cli is not None:
                try:
                    cli.disconnect()
                except Exception:
                    pass
                try:
                    cli.loop_stop()
                except Exception:
                    pass
        try:
            broker.shutdown()
            broker.server_close()
        except Exception:
            pass
        if uvicorn_proc is not None:
            if uvicorn_proc.poll() is None:
                uvicorn_proc.terminate()
                try:
                    uvicorn_proc.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    uvicorn_proc.kill()
                    uvicorn_proc.wait(timeout=5.0)
        try:
            tmp_dir.cleanup()
        except Exception:
            pass


def main() -> int:
    result = run_e2e()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
