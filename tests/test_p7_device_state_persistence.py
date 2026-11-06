"""Automated Unit & Integration Tests for P7 Shared Device State Persistence & Read-After-Write Consistency.

Kiểm chứng toàn diện:
1. Unit tests cho `InMemoryStateBackend`, `FileStateBackend`, `VercelBlobStateBackend` (mocked Vercel Blob REST API
   với kiểm thử chống stale CDN cache bằng versioned pathname `st_{ts_ns}_{seq}_{nonce}.json` + garbage collection),
   và `TrackedDeviceDict` (direct mutation + `copy.deepcopy`).
2. Multi-instance Serverless Integration Tests: Mô phỏng nhiều serverless instances độc lập (`instance_a`, `instance_b`,
   `instance_c`, và cold-start `_REST_ENGINE`) cùng chia sẻ `StateBackend`:
   - Kiểm chứng các kịch bản lỗi thực tế từ `p7_state.txt`:
     + Chủ nhà Cấp 1 (`cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav`) -> `fan=ON`, `ac=ON` đọc từ instance khác khớp 100%.
     + Thành viên Cấp 2 (`level2_bat_den_phong_khach.wav`) -> `living_room_light=ON` đọc từ instance khác khớp 100%.
     + Khách Cấp 3 (`level3_bat_den_phong_khach.wav`) -> `living_room_light=ON` đọc từ instance khác khớp 100%.
   - Chuỗi 24 chu kỳ liên tiếp (Command trên Instance X -> Đọc ngay lập tức trên Instance Y / Cold-Start Instance Z)
     bật/tắt nhiều thiết bị (`main_door`, `living_room_light`, `bedroom_light`, `fan`, `ac`, `garden_pump`) qua cả
     3 tầng phân quyền (L1/L2/L3) và cả 3 kênh (`/api/voice_command`, `/api/device`, `/api/text_command`).
"""

from __future__ import annotations

import asyncio
import base64
import copy
import io
import json
import pathlib
import urllib.parse
import urllib.request
from typing import Any

import pytest
from fastapi.testclient import TestClient

import simulator.api.deps as api_deps
import simulator.api.routes_auth as routes_auth
import simulator.api.routes_devices as routes_devices
from simulator.engine.state_store import (
    FileStateBackend,
    InMemoryStateBackend,
    TrackedDeviceDict,
    VercelBlobStateBackend,
    build_default_shared_state_payload,
    create_state_backend_from_env,
    get_default_state_backend,
    set_default_state_backend,
)
from simulator.rule_engine import SmartHomeEngine
from simulator.server import app
from simulator.voice.stt_pipeline import process_voice_command_pipeline

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "test_audio"
SEP_DIR = AUDIO_DIR / "cac_cau_lenh_cua_sep"
VOICES_DIR = ROOT.parent / "voices"
ROLE_DIR = VOICES_DIR if VOICES_DIR.exists() else (AUDIO_DIR / "role_commands")


def _wav_b64(path: pathlib.Path) -> str:
    assert path.exists(), f"Missing audio fixture: {path}"
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _devices_map_from_snapshot(snap: dict[str, Any]) -> dict[str, str]:
    devs = snap.get("devices", [])
    if isinstance(devs, list):
        return {str(d["id"]): str(d["state"]) for d in devs if isinstance(d, dict) and "id" in d}
    if isinstance(devs, dict):
        return {
            str(k): str(v["state"] if isinstance(v, dict) else v)
            for k, v in devs.items()
        }
    return {}


class FakeVercelBlobServer:
    """Mô phỏng chính xác hành vi Vercel Blob API (bao gồm cả lỗi CDN cache trên URL cố định nếu không dùng versioned path)."""

    def __init__(self) -> None:
        self.blobs_by_url: dict[str, dict[str, Any]] = {}
        self.put_count: int = 0
        self.list_count: int = 0
        self.get_count: int = 0
        self.delete_count: int = 0
        self.simulate_store_suspended: bool = False
        self.last_put_headers: dict[str, str] = {}

    def urlopen(self, req: urllib.request.Request, timeout: float = 8.0) -> Any:
        url = req.full_url
        method = req.get_method()
        parsed = urllib.parse.urlparse(url)

        if method == "PUT":
            self.put_count += 1
            self.last_put_headers = {str(k).lower(): str(v) for k, v in req.headers.items()}
            if self.simulate_store_suspended:
                err_body = json.dumps({"error": {"code": "store_suspended", "message": "Store is suspended"}}).encode("utf-8")
                fp = io.BytesIO(err_body)
                raise urllib.error.HTTPError(url, 403, "Forbidden", {"Content-Type": "application/json"}, fp)
            pathname = parsed.path.lstrip("/")
            raw_bytes = req.data or b"{}"
            add_rand = req.headers.get("X-add-random-suffix") or req.headers.get("x-add-random-suffix")
            if add_rand == "1" and pathname.endswith(".json"):
                stored_pathname = pathname[:-5] + f"-r{self.put_count:04d}.json"
            else:
                stored_pathname = pathname
            blob_url = f"https://fake-blob.public.blob.vercel-storage.com/{stored_pathname}"
            self.blobs_by_url[blob_url] = {
                "url": blob_url,
                "downloadUrl": f"{blob_url}?download=1",
                "pathname": stored_pathname,
                "size": len(raw_bytes),
                "uploadedAt": f"2026-11-05T09:00:{self.put_count % 60:02d}.000Z",
                "payload": raw_bytes.decode("utf-8"),
            }
            resp_body = json.dumps({
                "url": blob_url,
                "downloadUrl": f"{blob_url}?download=1",
                "pathname": stored_pathname,
                "contentType": "application/json",
            }).encode("utf-8")
            return self._make_response(resp_body)

        if method == "POST" and parsed.path.endswith("/delete"):
            self.delete_count += 1
            body = json.loads((req.data or b"{}").decode("utf-8"))
            for u in body.get("urls", []):
                self.blobs_by_url.pop(u, None)
            return self._make_response(b"{}")

        if method == "GET" and parsed.netloc == "blob.vercel-storage.com":
            self.list_count += 1
            qs = urllib.parse.parse_qs(parsed.query)
            prefix = qs.get("prefix", [""])[0]
            matching = [
                {
                    "url": info["url"],
                    "downloadUrl": info["downloadUrl"],
                    "pathname": info["pathname"],
                    "size": info["size"],
                    "uploadedAt": info["uploadedAt"],
                }
                for info in self.blobs_by_url.values()
                if str(info["pathname"]).startswith(prefix)
            ]
            resp_body = json.dumps({"blobs": matching, "hasMore": False}).encode("utf-8")
            return self._make_response(resp_body)

        if method == "GET":
            self.get_count += 1
            base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if base_url not in self.blobs_by_url:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            raw_payload = self.blobs_by_url[base_url]["payload"].encode("utf-8")
            return self._make_response(raw_payload)

        raise AssertionError(f"Unsupported request: {method} {url}")

    @staticmethod
    def _make_response(body: bytes) -> Any:
        bio = io.BytesIO(body)
        bio.status = 200
        return bio


@pytest.fixture(autouse=True)
def isolated_shared_state_backend(tmp_path: pathlib.Path):
    """Đặt FileStateBackend cô lập trong tmp_path cho mỗi test và khôi phục nguyên trạng sau khi chạy."""
    prev_backend = get_default_state_backend()
    prev_engine = routes_devices._REST_ENGINE
    temp_backend = FileStateBackend(tmp_path / "test_shared_device_state.json")
    set_default_state_backend(temp_backend)

    eng = routes_devices._REST_ENGINE
    eng.set_state_backend(temp_backend)
    eng.set_active_user("tuan_anh")
    eng.server_connected = True
    asyncio.run(eng.factory_reset())
    for dev_id in ("living_room_light", "bedroom_light", "fan", "ac", "alarm_siren", "garden_pump"):
        if dev_id in eng.devices:
            eng.devices[dev_id]["state"] = "OFF"
    if "main_door" in eng.devices:
        eng.devices["main_door"]["state"] = "CLOSED"
    eng.persist_to_shared_store()

    yield temp_backend

    eng = prev_engine
    eng.set_state_backend(None)
    routes_devices._REST_ENGINE = eng
    routes_auth._REST_ENGINE = eng
    api_deps._REST_ENGINE = eng
    set_default_state_backend(prev_backend)
    eng.set_active_user("tuan_anh")
    eng.server_connected = True
    asyncio.run(eng.factory_reset())


# ==============================================================================
# 1. UNIT TESTS: BACKENDS & TRACKED DEVICE DICT
# ==============================================================================

def test_in_memory_state_backend_monotonic_revisions_and_isolation() -> None:
    backend = InMemoryStateBackend()
    assert backend.load_state() is None

    p1 = build_default_shared_state_payload()
    p1["devices"]["fan"]["state"] = "ON"
    s1 = backend.save_state(p1)
    assert s1["revision_seq"] == 1
    assert s1["revision_ts_ns"] > 0

    loaded1 = backend.load_state()
    assert loaded1 is not None
    assert loaded1["devices"]["fan"]["state"] == "ON"
    # Đảm bảo deep copy cô lập, sửa bản đọc ra không làm hỏng store
    loaded1["devices"]["fan"]["state"] = "MUTATED_LOCALLY"
    assert backend.load_state()["devices"]["fan"]["state"] == "ON"

    p2 = copy.deepcopy(s1)
    p2["devices"]["ac"]["state"] = "ON"
    s2 = backend.save_state(p2)
    assert s2["revision_seq"] == 2
    assert s2["revision_ts_ns"] > s1["revision_ts_ns"]

    backend.clear()
    assert backend.load_state() is None


def test_file_state_backend_cross_instance_read_after_write(tmp_path: pathlib.Path) -> None:
    state_file = tmp_path / "cross_instance_state.json"
    writer = FileStateBackend(state_file)
    reader = FileStateBackend(state_file)

    payload = build_default_shared_state_payload()
    payload["devices"]["living_room_light"]["state"] = "ON"
    payload["devices"]["fan"]["state"] = "ON"
    writer.save_state(payload)

    loaded = reader.load_state()
    assert loaded is not None
    assert loaded["devices"]["living_room_light"]["state"] == "ON"
    assert loaded["devices"]["fan"]["state"] == "ON"

    payload["devices"]["living_room_light"]["state"] = "OFF"
    writer.save_state(payload)

    loaded_after = reader.load_state()
    assert loaded_after is not None
    assert loaded_after["devices"]["living_room_light"]["state"] == "OFF"
    assert loaded_after["revision_seq"] == 2


def test_vercel_blob_state_backend_versioned_read_after_write_and_gc(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_blob = FakeVercelBlobServer()
    monkeypatch.setattr(urllib.request, "urlopen", fake_blob.urlopen)

    instance_1 = VercelBlobStateBackend(token="vercel_blob_rw_mock_token", prefix="test_p7_prefix/")
    instance_2 = VercelBlobStateBackend(token="vercel_blob_rw_mock_token", prefix="test_p7_prefix/")

    for i in range(1, 9):
        expected_fan = "ON" if i % 2 == 1 else "OFF"
        expected_ac = "ON" if i % 3 == 0 else "OFF"
        p = build_default_shared_state_payload()
        p["devices"]["fan"]["state"] = expected_fan
        p["devices"]["ac"]["state"] = expected_ac

        writer = instance_1 if i % 2 == 1 else instance_2
        reader = instance_2 if i % 2 == 1 else instance_1

        saved = writer.save_state(p)
        assert saved["revision_seq"] == i

        loaded = reader.load_state()
        assert loaded is not None
        assert loaded["revision_seq"] == i
        assert loaded["devices"]["fan"]["state"] == expected_fan
        assert loaded["devices"]["ac"]["state"] == expected_ac

    # Kiểm tra cơ chế dọn rác (GC) tự động giữ số lượng blob nhỏ gọn
    assert fake_blob.delete_count >= 1
    assert len(fake_blob.blobs_by_url) <= 4

    instance_1.clear()
    assert len(fake_blob.blobs_by_url) == 0


def test_tracked_device_dict_direct_mutation_and_deepcopy() -> None:
    backend = InMemoryStateBackend()
    eng_a = SmartHomeEngine(state_backend=backend)
    eng_b = SmartHomeEngine(state_backend=backend)

    # Sửa trực tiếp trong RAM trên eng_a (như các fixture pytest cũ)
    eng_a.devices["fan"]["state"] = "ON"
    assert isinstance(eng_a.devices["fan"], TrackedDeviceDict)

    # eng_b đọc snapshot phải thấy ngay fan == ON
    snap_b = eng_b.get_snapshot()
    assert _devices_map_from_snapshot(snap_b)["fan"] == "ON"

    # Kiểm tra copy.deepcopy không gây đệ quy vô hạn
    cloned = copy.deepcopy(eng_a.devices)
    assert cloned["fan"]["state"] == "ON"


def test_multi_target_comma_expansion_atomic_persistence() -> None:
    backend = InMemoryStateBackend()
    eng_a = SmartHomeEngine(state_backend=backend)
    eng_b = SmartHomeEngine(state_backend=backend)

    res = asyncio.run(eng_a.execute_device_action("fan,ac", "turn_on", source="test_comma"))
    assert res["ok"] is True
    snap_b = eng_b.get_snapshot()
    dev_map = _devices_map_from_snapshot(snap_b)
    assert dev_map["fan"] == "ON"
    assert dev_map["ac"] == "ON"


def test_create_state_backend_from_env_and_telemetry_reset_persistence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setenv("SMARTHOME_STATE_BACKEND", "memory")
    b_mem = create_state_backend_from_env()
    assert isinstance(b_mem, InMemoryStateBackend)

    custom_file = tmp_path / "env_state.json"
    monkeypatch.setenv("SMARTHOME_STATE_BACKEND", "file")
    monkeypatch.setenv("SMARTHOME_STATE_FILE", str(custom_file))
    b_file = create_state_backend_from_env()
    assert isinstance(b_file, FileStateBackend)
    assert b_file.file_path == custom_file

    monkeypatch.setenv("SMARTHOME_STATE_BACKEND", "blob")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_dummy_token")
    b_blob = create_state_backend_from_env()
    assert isinstance(b_blob, VercelBlobStateBackend)

    # Kiểm tra đồng bộ telemetry cảm biến, offline mode và factory_reset giữa 2 instance
    shared = InMemoryStateBackend()
    eng_1 = SmartHomeEngine(state_backend=shared)
    eng_2 = SmartHomeEngine(state_backend=shared)

    asyncio.run(eng_1.update_sensor_telemetry(31.5, 68.0))
    asyncio.run(eng_1.update_soil_moisture_telemetry(25.0))  # < 40% -> auto bật garden_pump
    snap_2 = eng_2.get_snapshot()
    assert _devices_map_from_snapshot(snap_2)["garden_pump"] == "ON"
    assert eng_2.mqtt_bridge.dht11_telemetry["temp_c"] == 31.5

    # Mở cửa trên eng_1 rồi chuyển sang Offline trên eng_2 -> cửa tự động đóng và đồng bộ ngược về eng_1
    asyncio.run(eng_1.execute_device_action("main_door", "open"))
    assert _devices_map_from_snapshot(eng_2.get_snapshot())["main_door"] == "OPEN"
    asyncio.run(eng_2.set_server_connection_mode(False))
    snap_1_offline = eng_1.get_snapshot()
    assert snap_1_offline["server_connected"] is False
    assert _devices_map_from_snapshot(snap_1_offline)["main_door"] == "CLOSED"

    # Factory reset trên eng_1 -> đưa toàn bộ thiết bị và server_connected về mặc định trên eng_2
    asyncio.run(eng_1.factory_reset("all"))
    snap_2_reset = eng_2.get_snapshot()
    assert snap_2_reset["server_connected"] is True
    assert _devices_map_from_snapshot(snap_2_reset)["garden_pump"] == "OFF"


# ==============================================================================
# 2. MULTI-INSTANCE INTEGRATION TESTS: EXACT P7_STATE.TXT FAILING SCENARIOS
# ==============================================================================

def test_serverless_multi_instance_p7_reported_failures_fixed() -> None:
    """Kiểm tra chính xác 3 kịch bản lỗi được báo cáo trong p7_state.txt giữa các instance serverless độc lập:
    1. Chủ nhà Cấp 1: cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav -> fan=ON, ac=ON trên instance đọc mới.
    2. Thành viên Cấp 2: level2_bat_den_phong_khach.wav -> living_room_light=ON trên instance đọc mới.
    3. Khách Cấp 3: level3_bat_den_phong_khach.wav -> living_room_light=ON trên instance đọc mới.
    """
    shared_backend = InMemoryStateBackend()
    instance_cmd_1 = SmartHomeEngine(state_backend=shared_backend)
    instance_cmd_2 = SmartHomeEngine(state_backend=shared_backend)
    instance_cmd_3 = SmartHomeEngine(state_backend=shared_backend)
    instance_reader = SmartHomeEngine(state_backend=shared_backend)

    # 1. Owner cau_5: Bật quạt trần và điều hòa trên instance_cmd_1 -> Đọc trên instance_reader
    res_cau5 = asyncio.run(
        process_voice_command_pipeline(
            {"wav_b64": _wav_b64(SEP_DIR / "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav")},
            engine=instance_cmd_1,
            voice_auth=api_deps._BOOT_VOICE_AUTH,
        )
    )
    assert res_cau5["authorized"] is True
    assert res_cau5["permission"] == "ALLOWED"
    state_after_cau5 = _devices_map_from_snapshot(instance_reader.get_snapshot())
    assert state_after_cau5["fan"] == "ON"
    assert state_after_cau5["ac"] == "ON"

    # Reset đèn phòng khách về OFF trên instance_cmd_1
    asyncio.run(instance_cmd_1.execute_device_action("living_room_light", "turn_off"))
    assert _devices_map_from_snapshot(instance_reader.get_snapshot())["living_room_light"] == "OFF"

    # 2. Level 2: Bật đèn phòng khách trên instance_cmd_2 -> Đọc trên instance_reader
    res_l2 = asyncio.run(
        process_voice_command_pipeline(
            {"wav_b64": _wav_b64(ROLE_DIR / "level2_bat_den_phong_khach.wav")},
            engine=instance_cmd_2,
            voice_auth=api_deps._BOOT_VOICE_AUTH,
        )
    )
    assert res_l2["authorized"] is True
    assert res_l2["permission"] == "ALLOWED"
    state_after_l2 = _devices_map_from_snapshot(instance_reader.get_snapshot())
    assert state_after_l2["living_room_light"] == "ON"
    # Và trạng thái fan, ac từ lệnh trước trên instance_cmd_1 vẫn phải được bảo toàn!
    assert state_after_l2["fan"] == "ON"
    assert state_after_l2["ac"] == "ON"

    # Tắt đèn phòng khách từ instance_reader
    asyncio.run(instance_reader.execute_device_action("living_room_light", "turn_off"))
    assert _devices_map_from_snapshot(instance_cmd_3.get_snapshot())["living_room_light"] == "OFF"

    # 3. Level 3: Bật đèn phòng khách trên instance_cmd_3 -> Đọc trên instance newly spawned (cold start)
    res_l3 = asyncio.run(
        process_voice_command_pipeline(
            {"wav_b64": _wav_b64(ROLE_DIR / "level3_bat_den_phong_khach.wav")},
            engine=instance_cmd_3,
            voice_auth=api_deps._BOOT_VOICE_AUTH,
        )
    )
    assert res_l3["authorized"] is True
    assert res_l3["permission"] == "ALLOWED"

    cold_start_instance = SmartHomeEngine(state_backend=shared_backend)
    state_after_l3 = _devices_map_from_snapshot(cold_start_instance.get_snapshot())
    assert state_after_l3["living_room_light"] == "ON"
    assert state_after_l3["fan"] == "ON"
    assert state_after_l3["ac"] == "ON"


def test_24_sequential_command_and_read_cycles_across_serverless_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Thực hiện 24 chu kỳ Command -> Read liên tiếp qua HTTP TestClient với việc hoán đổi _REST_ENGINE
    sang instance mới sau mỗi request để mô phỏng 100% môi trường Vercel Serverless đa container chạy trên VercelBlobStateBackend.
    """
    fake_blob = FakeVercelBlobServer()
    monkeypatch.setattr(urllib.request, "urlopen", fake_blob.urlopen)
    blob_backend = VercelBlobStateBackend(token="vercel_blob_rw_cycle_test", prefix="cycles_24/")
    set_default_state_backend(blob_backend)

    def _swap_to_fresh_serverless_instance() -> SmartHomeEngine:
        fresh = SmartHomeEngine(
            on_event=api_deps._emit_to_all_active_bridges,
            on_voice_reset=api_deps._BOOT_VOICE_AUTH.reset_to_owner_only,
            state_backend=blob_backend,
        )
        routes_devices._REST_ENGINE = fresh
        routes_auth._REST_ENGINE = fresh
        api_deps._REST_ENGINE = fresh
        return fresh

    client = TestClient(app)

    # Khởi tạo trạng thái ban đầu tất cả OFF / CLOSED
    init_eng = _swap_to_fresh_serverless_instance()
    for d in ("living_room_light", "bedroom_light", "fan", "ac", "alarm_siren", "garden_pump"):
        init_eng.devices[d]["state"] = "OFF"
    init_eng.devices["main_door"]["state"] = "CLOSED"
    init_eng.persist_to_shared_store()

    cycles: list[dict[str, Any]] = [
        # Cycle 1: L1 Voice mở cửa chính
        {"type": "voice", "wav": SEP_DIR / "cau_2_mo_cua_chinh.wav", "level": 1, "expect": {"main_door": "OPEN"}},
        # Cycle 2: L1 Voice đóng cửa chính
        {"type": "voice", "wav": SEP_DIR / "cau_3_dong_cua_chinh.wav", "level": 1, "expect": {"main_door": "CLOSED"}},
        # Cycle 3: L1 Voice bật đèn phòng khách
        {"type": "voice", "wav": SEP_DIR / "cau_4_bat_den_phong_khach.wav", "level": 1, "expect": {"living_room_light": "ON"}},
        # Cycle 4: L1 Voice tắt hết đèn
        {"type": "voice", "wav": SEP_DIR / "cau_6_tat_het_den.wav", "level": 1, "expect": {"living_room_light": "OFF", "bedroom_light": "OFF"}},
        # Cycle 5: L1 Voice bật quạt trần và điều hòa (cau_5)
        {"type": "voice", "wav": SEP_DIR / "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav", "level": 1, "expect": {"fan": "ON", "ac": "ON"}},
        # Cycle 6: L2 Voice tắt quạt
        {"type": "voice", "wav": ROLE_DIR / "level2_tat_quat.wav", "level": 2, "expect": {"fan": "OFF", "ac": "ON"}},
        # Cycle 7: L2 Voice bật đèn phòng khách
        {"type": "voice", "wav": ROLE_DIR / "level2_bat_den_phong_khach.wav", "level": 2, "expect": {"living_room_light": "ON", "fan": "OFF", "ac": "ON"}},
        # Cycle 8: L2 Voice cố mở cửa chính -> RBAC DENIED, cửa vẫn CLOSED
        {"type": "voice_denied", "wav": ROLE_DIR / "level2_mo_cua_chinh.wav", "level": 2, "expect": {"main_door": "CLOSED", "living_room_light": "ON"}},
        # Cycle 9: L1 Voice tắt hết đèn
        {"type": "voice", "wav": SEP_DIR / "cau_6_tat_het_den.wav", "level": 1, "expect": {"living_room_light": "OFF"}},
        # Cycle 10: L3 Voice bật đèn phòng khách
        {"type": "voice", "wav": ROLE_DIR / "level3_bat_den_phong_khach.wav", "level": 3, "expect": {"living_room_light": "ON"}},
        # Cycle 11: L3 Voice cố mở cửa chính -> RBAC DENIED, cửa vẫn CLOSED
        {"type": "voice_denied", "wav": ROLE_DIR / "level3_mo_cua_chinh.wav", "level": 3, "expect": {"main_door": "CLOSED", "living_room_light": "ON"}},
        # Cycle 12: L1 Voice bật quạt trần và điều hòa
        {"type": "voice", "wav": SEP_DIR / "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav", "level": 1, "expect": {"fan": "ON", "ac": "ON"}},
        # Cycle 13: L3 Voice tắt quạt
        {"type": "voice", "wav": ROLE_DIR / "level3_tat_quat.wav", "level": 3, "expect": {"fan": "OFF", "ac": "ON"}},
        # Cycle 14: REST text_command tắt điều hòa (Owner L1)
        {"type": "text", "text": "Tắt điều hòa", "role": "tuan_anh", "expect": {"ac": "OFF", "fan": "OFF"}},
        # Cycle 15: REST text_command bật đèn phòng ngủ (Member L2)
        {"type": "text", "text": "Bật đèn phòng ngủ", "role": "thanh_vien_a", "expect": {"bedroom_light": "ON"}},
        # Cycle 16: REST text_command tắt đèn phòng ngủ (Guest L3)
        {"type": "text", "text": "Tắt đèn phòng ngủ", "role": "khach_c", "expect": {"bedroom_light": "OFF"}},
        # Cycle 17: REST /api/device bật máy bơm (Owner L1)
        {"type": "device", "device_id": "garden_pump", "action": "turn_on", "role": "tuan_anh", "expect": {"garden_pump": "ON"}},
        # Cycle 18: REST /api/device tắt máy bơm (Member L2)
        {"type": "device", "device_id": "garden_pump", "action": "turn_off", "role": "thanh_vien_a", "expect": {"garden_pump": "OFF"}},
        # Cycle 19: L1 Voice mở cửa chính
        {"type": "voice", "wav": SEP_DIR / "cau_2_mo_cua_chinh.wav", "level": 1, "expect": {"main_door": "OPEN"}},
        # Cycle 20: L1 Voice đóng hết cửa
        {"type": "voice", "wav": SEP_DIR / "cau_7_dong_het_cua.wav", "level": 1, "expect": {"main_door": "CLOSED"}},
        # Cycle 21: L1 Voice tắt hết đèn
        {"type": "voice", "wav": SEP_DIR / "cau_6_tat_het_den.wav", "level": 1, "expect": {"living_room_light": "OFF", "bedroom_light": "OFF"}},
        # Cycle 22: L2 Voice bật đèn phòng khách
        {"type": "voice", "wav": ROLE_DIR / "level2_bat_den_phong_khach.wav", "level": 2, "expect": {"living_room_light": "ON"}},
        # Cycle 23: REST /api/device tắt đèn phòng khách (Guest L3)
        {"type": "device", "device_id": "living_room_light", "action": "turn_off", "role": "khach_c", "expect": {"living_room_light": "OFF"}},
        # Cycle 24: L3 Voice bật đèn phòng khách
        {"type": "voice", "wav": ROLE_DIR / "level3_bat_den_phong_khach.wav", "level": 3, "expect": {"living_room_light": "ON"}},
    ]

    for idx, c in enumerate(cycles, 1):
        # Mỗi lệnh chạy trên 1 serverless instance hoàn toàn mới
        cmd_eng = _swap_to_fresh_serverless_instance()

        if c["type"] in ("voice", "voice_denied"):
            resp = client.post(
                "/api/voice_command",
                json={"wav_b64": _wav_b64(c["wav"])},
            )
            assert resp.status_code == 200, f"Cycle {idx} voice HTTP status != 200"
            body = resp.json()
            if c["type"] == "voice":
                assert body["authorized"] is True, f"Cycle {idx} unauthorized: {body}"
                assert body["permission"] == "ALLOWED", f"Cycle {idx} permission != ALLOWED: {body}"
            else:
                assert body["permission"] == "DENIED", f"Cycle {idx} expected DENIED: {body}"
        elif c["type"] == "text":
            cmd_eng.set_active_user(c["role"])
            resp = client.post("/api/text_command", json={"text": c["text"]})
            assert resp.status_code == 200, f"Cycle {idx} text HTTP status != 200"
            assert resp.json()["ok"] is True
        elif c["type"] == "device":
            cmd_eng.set_active_user(c["role"])
            resp = client.post(
                "/api/device",
                json={"device_id": c["device_id"], "action": c["action"]},
            )
            assert resp.status_code == 200, f"Cycle {idx} device HTTP status != 200"
            assert resp.json()["ok"] is True

        # Và bước ĐỌC trạng thái ngay sau đó chạy trên 1 serverless instance MỚI KHÁC (Cold-start reader)
        _swap_to_fresh_serverless_instance()
        state_resp = client.get("/api/state")
        assert state_resp.status_code == 200
        dev_map = _devices_map_from_snapshot(state_resp.json())
        for exp_dev, exp_state in c["expect"].items():
            assert dev_map.get(exp_dev) == exp_state, (
                f"Cycle {idx} stale/wrong state for {exp_dev}: expected {exp_state}, got {dev_map.get(exp_dev)}"
            )


# ==============================================================================
# 3. UNIT & INTEGRATION TESTS: 403 STORE SUSPENDED GRACEFUL DEGRADATION
# ==============================================================================

def test_vercel_blob_save_state_graceful_degradation_on_403_store_suspended(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kiểm chứng VercelBlobStateBackend:
    1. Khi remote PUT gặp HTTP 403 store_suspended, save_state không raise exception.
    2. Header "x-vercel-blob-access": "public" được gửi đi.
    3. State được lưu bền vững vào RAM cache (_cached_state, _last_seq, _last_ts_ns).
    4. Fallback snapshot được ghi xuống file cục bộ (/tmp/smarthome_shared_device_state.json).
    5. load_state() đọc lại đúng dữ liệu từ RAM/file fallback.
    """
    fake_blob = FakeVercelBlobServer()
    fake_blob.simulate_store_suspended = True
    monkeypatch.setattr(urllib.request, "urlopen", fake_blob.urlopen)

    fallback_file = tmp_path / "mock_fallback_device_state.json"
    backend = VercelBlobStateBackend(
        token="vercel_blob_rw_mock_token",
        prefix="test_suspended/",
        fallback_file_path=fallback_file,
    )

    p1 = build_default_shared_state_payload()
    p1["devices"]["main_door"]["state"] = "CLOSED"
    p1["devices"]["fan"]["state"] = "ON"
    p1["devices"]["ac"]["state"] = "ON"

    # save_state() tuyệt đối không ném ngoại lệ dù server blob bị đình chỉ 403
    saved = backend.save_state(p1)
    assert saved is not None
    assert saved["revision_seq"] == 1
    assert saved["revision_ts_ns"] > 0
    assert saved["devices"]["fan"]["state"] == "ON"
    assert saved["devices"]["ac"]["state"] == "ON"

    # Khẳng định header x-vercel-blob-access: public được gửi đi
    assert fake_blob.last_put_headers.get("x-vercel-blob-access") == "public"

    # Khẳng định RAM cache được cập nhật
    assert backend._cached_state is not None
    assert backend._cached_state["devices"]["fan"]["state"] == "ON"
    assert backend._last_seq == 1

    # Khẳng định file fallback được ghi đúng đĩa
    assert fallback_file.exists()
    fb_data = backend.fallback_backend.load_state()
    assert fb_data is not None
    assert fb_data["devices"]["fan"]["state"] == "ON"
    assert fb_data["devices"]["ac"]["state"] == "ON"

    # Khẳng định load_state() trả về đúng trạng thái vừa lưu
    loaded = backend.load_state()
    assert loaded is not None
    assert loaded["devices"]["fan"]["state"] == "ON"
    assert loaded["devices"]["ac"]["state"] == "ON"
    assert loaded["devices"]["main_door"]["state"] == "CLOSED"

    # Thao tác lưu lần 2: tăng seq tuần tự
    p2 = copy.deepcopy(saved)
    p2["devices"]["fan"]["state"] = "OFF"
    saved2 = backend.save_state(p2)
    assert saved2["revision_seq"] == 2
    assert backend._last_seq == 2
    assert backend.load_state()["devices"]["fan"]["state"] == "OFF"


def test_rule_engine_state_transaction_resilient_to_backend_crash() -> None:
    """Kiểm chứng SmartHomeEngine:
    Nếu backend ném ngoại lệ bất kỳ trong save_state hoặc persist_to_shared_store,
    state_transaction.__exit__ và persist_to_shared_store tuyệt đối không văng lỗi ra ngoài.
    """
    class CrashingStateBackend:
        is_remote: bool = True

        def load_state(self) -> dict[str, Any] | None:
            return None

        def save_state(self, state: dict[str, Any]) -> dict[str, Any]:
            raise urllib.error.HTTPError(
                "https://blob.vercel-storage.com",
                403,
                "Forbidden (Store is suspended)",
                {},
                None,
            )

        def clear(self) -> None:
            pass

    engine = SmartHomeEngine(state_backend=CrashingStateBackend())

    # Thao tác trong state_transaction: không bị crash
    with engine.state_transaction():
        engine.devices["fan"]["state"] = "ON"
        engine.devices["ac"]["state"] = "ON"

    # Trạng thái trong RAM vẫn được bảo toàn
    assert engine.devices["fan"]["state"] == "ON"
    assert engine.devices["ac"]["state"] == "ON"

    # Gọi trực tiếp persist_to_shared_store cũng không crash, trả về payload
    result = engine.persist_to_shared_store()
    assert isinstance(result, dict)
    assert result["devices"]["fan"]["state"] == "ON"


def test_voice_command_succeeds_under_403_store_suspended_preserving_auth(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """Kiểm chứng End-to-End API /api/voice_command:
    1. Chủ nhà Cấp 1 ra lệnh điều khiển thiết bị (cau_3_dong_cua_chinh.wav) khi Vercel Blob 403:
       - Phản hồi HTTP 200 OK (KHÔNG bị HTTP 500!).
       - authorized=True, permission="ALLOWED".
       - main_door chuyển sang CLOSED.
    2. Bảo toàn Sinh trắc học & Phân quyền RBAC (Authentication Preservation):
       - Lệnh mở cửa của Thành viên Cấp 2 (level2_mo_cua_chinh.wav) bị RBAC DENIED, cửa vẫn CLOSED.
       - Không có bất kỳ sự bypass bảo mật nào.
    """
    fake_blob = FakeVercelBlobServer()
    fake_blob.simulate_store_suspended = True
    monkeypatch.setattr(urllib.request, "urlopen", fake_blob.urlopen)

    fallback_file = tmp_path / "api_fallback_device_state.json"
    suspended_backend = VercelBlobStateBackend(
        token="vercel_blob_rw_api_test",
        prefix="api_suspended/",
        fallback_file_path=fallback_file,
    )
    set_default_state_backend(suspended_backend)

    test_engine = SmartHomeEngine(
        on_event=api_deps._emit_to_all_active_bridges,
        on_voice_reset=api_deps._BOOT_VOICE_AUTH.reset_to_owner_only,
        state_backend=suspended_backend,
    )
    routes_devices._REST_ENGINE = test_engine
    routes_auth._REST_ENGINE = test_engine
    api_deps._REST_ENGINE = test_engine

    # Ban đầu mở cửa chính
    test_engine.devices["main_door"]["state"] = "OPEN"
    test_engine.devices["fan"]["state"] = "OFF"
    test_engine.persist_to_shared_store()

    client = TestClient(app)

    # 1. Chủ nhà lệnh đóng cửa chính (cau_3) -> Phải trả về HTTP 200 OK (Đã khắc phục lỗi HTTP 500)
    resp_owner = client.post(
        "/api/voice_command",
        json={"wav_b64": _wav_b64(SEP_DIR / "cau_3_dong_cua_chinh.wav")},
    )
    assert resp_owner.status_code == 200, f"Owner command failed with status {resp_owner.status_code}: {resp_owner.text}"
    body_owner = resp_owner.json()
    assert body_owner["authorized"] is True
    assert body_owner["permission"] == "ALLOWED"

    # Trạng thái cửa đã đóng
    assert test_engine.devices["main_door"]["state"] == "CLOSED"
    # Fallback và cache RAM đều đã ghi nhận CLOSED
    assert suspended_backend._cached_state["devices"]["main_door"]["state"] == "CLOSED"
    assert suspended_backend.fallback_backend.load_state()["devices"]["main_door"]["state"] == "CLOSED"

    # 2. Thành viên Cấp 2 cố mở cửa chính -> RBAC DENIED, cửa vẫn đóng (Không bypass RBAC)
    resp_l2 = client.post(
        "/api/voice_command",
        json={"wav_b64": _wav_b64(ROLE_DIR / "level2_mo_cua_chinh.wav")},
    )
    assert resp_l2.status_code == 200
    body_l2 = resp_l2.json()
    assert body_l2["permission"] == "DENIED"
    assert test_engine.devices["main_door"]["state"] == "CLOSED"

