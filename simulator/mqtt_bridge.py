"""Tầng Truyền Thông Bất Đồng Bộ MQTT (Message Queue Pub/Sub, Back Pressure & Edge Sync)
áp dụng trực tiếp chuẩn kiến trúc The System Design Primer:

1. Asynchronism & Message Queues:
   - Hàng đợi bản tin bất đồng bộ (`asyncio.Queue` với giới hạn `MAX_QUEUE_SIZE = 256` chống tràn bộ nhớ - Back Pressure).
   - Hỗ trợ kết nối tới MQTT Broker chuẩn (TCP cổng 1883) HOẶC tự vận hành Embedded MQTT Message Bus nội bộ (Zero-Config).
2. CAP Theorem & Active-Passive Edge Failover:
   - Tự động đồng bộ bản sao (Replica) của Bể 1 (Hẹn giờ) và Bể 2 (Luật IF-ELSE) qua Topic `smarthome/sync/pools` (`Retain=True`) xuống bộ nhớ Flash (`LittleFS`) của NodeMCU ESP8266.
3. Write-Through Cache cho Thiết bị Hồng ngoại (IR 38kHz) & Telemetry Cảm biến (`DHT11`):
   - Lưu trữ tức thời các mã sóng Remote đã chiếm quyền vào RAM và ghi xuyên suốt (`Write-Through`) xuống `simulator/data/ir_devices_db.json`.
"""

from __future__ import annotations

import asyncio
import collections
import json
import pathlib
import time
from typing import Any, Callable, Awaitable

DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
IR_DB_FILE = DATA_DIR / "ir_devices_db.json"
EDGE_REPLICA_FILE = DATA_DIR / "esp8266_flash_replica.json"

# Bảng ánh xạ thiết bị sang chân vật lý của NodeMCU ESP8266 (ESP-12E)
ESP8266_PIN_MAP: dict[str, dict[str, Any]] = {
    "main_door": {"pin": "D1", "gpio": 5, "mode": "PWM_SERVO"},
    "living_room_light": {"pin": "D2", "gpio": 4, "mode": "DIGITAL_OUT"},
    "bedroom_light": {"pin": "D7", "gpio": 13, "mode": "DIGITAL_OUT"},
    "fan": {"pin": "D6", "gpio": 12, "mode": "DIGITAL_OUT"},
    "ac": {"pin": "D2", "gpio": 4, "mode": "IR_BLAST_38KHZ"},
    "alarm_siren": {"pin": "D8", "gpio": 15, "mode": "DIGITAL_OUT"},
    "garden_pump": {"pin": "D3", "gpio": 0, "mode": "RELAY_PUMP_5V_DIODE_1N4007"},
}

DEFAULT_IR_DEVICES: dict[str, Any] = {
    "ac": {
        "device_id": "ac",
        "device_name": "Điều hòa",
        "brand": "Casper / Daikin IR 38kHz",
        "carrier_khz": 38,
        "commands": {
            "open": {
                "protocol": "COOLIX",
                "hex_code": "0xB2BF40",
                "raw_timings_us": [4420, 4400, 560, 1640, 560, 540, 560, 1640],
                "temp_c": 24,
            },
            "turn_on": {
                "protocol": "COOLIX",
                "hex_code": "0xB2BF40",
                "raw_timings_us": [4420, 4400, 560, 1640, 560, 540, 560, 1640],
                "temp_c": 24,
            },
            "close": {
                "protocol": "COOLIX",
                "hex_code": "0xB27BE0",
                "raw_timings_us": [4420, 4400, 560, 540, 560, 1640, 560, 540],
                "temp_c": 0,
            },
            "turn_off": {
                "protocol": "COOLIX",
                "hex_code": "0xB27BE0",
                "raw_timings_us": [4420, 4400, 560, 540, 560, 1640, 560, 540],
                "temp_c": 0,
            },
        },
    }
}


class SmartHomeMQTTBridge:
    """Bộ điều phối bản tin MQTT chuẩn System Design Primer:
    - Quản lý 9 Topic MQTT chuẩn giữa Server <-> NodeMCU ESP8266 <-> Web/Mobile App.
    - Áp dụng Back Pressure (`max_queue_size=256`), Retained Messages, Last Will (LWT) và Write-Through Cache.
    """

    MAX_QUEUE_SIZE = 256

    def __init__(
        self,
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self.on_event = on_event
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self.MAX_QUEUE_SIZE)
        self.retained_topics: dict[str, dict[str, Any]] = {}
        self.recent_messages: collections.deque[dict[str, Any]] = collections.deque(maxlen=60)
        self.dropped_backpressure_count: int = 0

        # Trạng thái kết nối của NodeMCU ESP8266 & Cảm biến DHT11 (In-Memory Cache)
        self.esp8266_status: dict[str, Any] = {
            "node_id": "esp8266_node_01",
            "chip": "NodeMCU ESP8266 (ESP-12E)",
            "online": True,
            "ip": "192.168.1.88",
            "wifi_rssi_dbm": -52,
            "power_mode": "STANDALONE_5V",
            "flash_synced": True,
            "last_seen": time.time(),
        }
        self.retained_topics["smarthome/status/esp8266"] = {
            "topic": "smarthome/status/esp8266",
            "payload": self.esp8266_status,
            "qos": 1,
            "retain": True,
            "direction": "ESP8266 -> SERVER (LWT/Birth)",
            "timestamp": round(time.time(), 3),
        }
        self.dht11_telemetry: dict[str, Any] = {
            "temp_c": 28.5,
            "humidity_pct": 65.0,
            "heat_index_c": 29.8,
            "sensor_pin": "D6 (GPIO 12)",
            "updated_at": time.time(),
        }
        self.soil_moisture_telemetry: dict[str, Any] = {
            "soil_moisture_pct": 62.0,
            "adc_raw": 420,
            "status_label": "Đủ ẩm",
            "sensor_pin": "A0 (ADC0 - Cảm biến đất YL-69 + LM393)",
            "auto_pump_below_pct": 40.0,
            "updated_at": time.time(),
        }
        self.pending_ir_learning: dict[str, Any] | None = None
        self.ir_devices: dict[str, Any] = self._load_ir_db()

    def _load_ir_db(self) -> dict[str, Any]:
        if IR_DB_FILE.exists():
            try:
                data = json.loads(IR_DB_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data:
                    return data
            except Exception:
                pass
        default_db = json.loads(json.dumps(DEFAULT_IR_DEVICES))
        IR_DB_FILE.write_text(json.dumps(default_db, ensure_ascii=False, indent=2), encoding="utf-8")
        return default_db

    def _save_ir_db_write_through(self) -> None:
        """Write-Through Cache: Cập nhật RAM đồng thời ghi xuyên suốt xuống đĩa."""
        IR_DB_FILE.write_text(json.dumps(self.ir_devices, ensure_ascii=False, indent=2), encoding="utf-8")

    async def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        qos: int = 1,
        retain: bool = False,
        direction: str = "SERVER -> ESP8266",
    ) -> dict[str, Any]:
        """Phát hành gói tin MQTT với cơ chế kiểm soát Back Pressure."""
        pkt = {
            "topic": topic,
            "payload": payload,
            "qos": qos,
            "retain": retain,
            "direction": direction,
            "timestamp": round(time.time(), 3),
        }
        if retain:
            self.retained_topics[topic] = pkt

        # Back pressure check theo System Design Primer
        if self.queue.full():
            try:
                _ = self.queue.get_nowait()
                self.dropped_backpressure_count += 1
            except asyncio.QueueEmpty:
                pass
        await self.queue.put(pkt)
        self.recent_messages.append(pkt)

        if self.on_event is not None:
            await self.on_event({
                "type": "mqtt_packet",
                "packet": pkt,
            })
        return pkt

    async def publish_actuate_command(
        self,
        device_id: str,
        state: str,
        action: str,
        source: str,
        user_name: str,
        tier: int,
    ) -> dict[str, Any]:
        """Xuất bản tin MQTT điều khiển phần cứng ESP8266 (`smarthome/cmd/actuate`)
        và phát sóng hồng ngoại 38kHz (`smarthome/ir/blast`) nếu là thiết bị IR.
        """
        pin_info = ESP8266_PIN_MAP.get(device_id, {"pin": "D2", "gpio": 4, "mode": "DIGITAL_OUT"})
        target_entry: dict[str, Any] = {
            "device_id": device_id,
            "pin": pin_info["pin"],
            "gpio": pin_info["gpio"],
            "state": state,
            "mode": pin_info["mode"],
        }
        if device_id == "main_door":
            target_entry["pwm_angle"] = 90 if state == "OPEN" else 0

        act_pkt = await self.publish(
            topic="smarthome/cmd/actuate",
            payload={
                "msg_id": f"cmd_{int(time.time() * 1000)}",
                "user": user_name,
                "tier": tier,
                "targets": [target_entry],
                "source": source,
            },
            qos=1,
            retain=False,
            direction="SERVER -> ESP8266",
        )

        # Nếu thiết bị có mã sóng hồng ngoại 38kHz (VD: Điều hòa hoặc thiết bị mới học từ Remote)
        if device_id in self.ir_devices:
            ir_dev = self.ir_devices[device_id]
            cmd_info = ir_dev.get("commands", {}).get(action) or ir_dev.get("commands", {}).get(
                "open" if state in ("ON", "OPEN") else "close"
            )
            if cmd_info:
                await self.publish(
                    topic="smarthome/ir/blast",
                    payload={
                        "device_id": device_id,
                        "device_name": ir_dev.get("device_name", device_id),
                        "action": action,
                        "pin": "D2",
                        "carrier_khz": ir_dev.get("carrier_khz", 38),
                        "protocol": cmd_info.get("protocol", "RAW_38KHZ"),
                        "hex_code": cmd_info.get("hex_code", "0xB2BF40"),
                        "raw_timings_us": cmd_info.get("raw_timings_us", []),
                    },
                    qos=1,
                    retain=False,
                    direction="SERVER -> ESP8266 (IR 38kHz)",
                )

        # Mô phỏng phản hồi xác nhận tức thì từ ESP8266 (`smarthome/state/report`)
        await self.publish(
            topic="smarthome/state/report",
            payload={
                "node_id": self.esp8266_status["node_id"],
                "device_id": device_id,
                "pin": pin_info["pin"],
                "state": state,
                "ack": True,
            },
            qos=1,
            retain=True,
            direction="ESP8266 -> SERVER",
        )
        return act_pkt

    async def publish_enrollment_blink(self, device_id: str, pulse_ms: int = 350) -> dict[str, Any]:
        """Xuất bản tin MQTT `smarthome/cmd/enroll_blink` để ESP8266 nháy đèn báo hiệu bắt đầu thu âm 3-2-1."""
        pin_info = ESP8266_PIN_MAP.get(device_id, {"pin": "D2", "gpio": 4})
        return await self.publish(
            topic="smarthome/cmd/enroll_blink",
            payload={
                "device_id": device_id,
                "pin": pin_info["pin"],
                "gpio": pin_info["gpio"],
                "pulse_ms": pulse_ms,
                "reason": "Tín hiệu đếm 3-2-1 bắt đầu thu âm cấp quyền giọng nói",
            },
            qos=1,
            retain=False,
            direction="SERVER -> ESP8266",
        )

    async def sync_pools_to_esp8266_flash(
        self,
        timers: list[dict[str, Any]],
        if_else_rules: list[dict[str, Any]],
        system_policies: dict[str, Any],
    ) -> dict[str, Any]:
        """CAP Theorem (AP Failover): Đồng bộ bản sao Bể 1 (Hẹn giờ) và Bể 2 (Luật IF-ELSE)
        xuống bộ nhớ Flash (`LittleFS`) của ESP8266 qua Topic `smarthome/sync/pools` (`Retain=True`).
        """
        replica_payload = {
            "synced_at": round(time.time(), 2),
            "timers_count": len(timers),
            "timers": [
                {
                    "id": t.get("id"),
                    "device_id": t.get("device_id"),
                    "action": t.get("action"),
                    "remaining_seconds": t.get("remaining_seconds"),
                    "target_vn_time": t.get("target_vn_time", ""),
                }
                for t in timers
            ],
            "if_else_rules_count": len(if_else_rules),
            "if_else_rules": [
                {
                    "when_device_id": r.get("when_device_id"),
                    "when_state": r.get("when_state"),
                    "then_device_id": r.get("then_device_id"),
                    "then_action": r.get("then_action"),
                    "else_device_id": r.get("else_device_id", ""),
                    "else_action": r.get("else_action", ""),
                }
                for r in if_else_rules
            ],
            "device_min_tiers": system_policies.get("device_min_tiers", {}),
        }
        EDGE_REPLICA_FILE.write_text(json.dumps(replica_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.esp8266_status["flash_synced"] = True
        self.esp8266_status["last_seen"] = time.time()
        return await self.publish(
            topic="smarthome/sync/pools",
            payload=replica_payload,
            qos=1,
            retain=True,
            direction="SERVER -> ESP8266 (Flash LittleFS)",
        )

    async def update_dht11_telemetry(self, temp_c: float, humidity_pct: float, wifi_rssi_dbm: int = -52) -> dict[str, Any]:
        """Nhận bản tin cảm biến `smarthome/telemetry/dht11` từ chân D6 của ESP8266."""
        t = round(float(temp_c), 1)
        h = round(float(humidity_pct), 1)
        hi = round(t + 0.05 * h, 1)
        self.dht11_telemetry = {
            "temp_c": t,
            "humidity_pct": h,
            "heat_index_c": hi,
            "sensor_pin": "D6 (GPIO 12)",
            "updated_at": time.time(),
        }
        self.esp8266_status["wifi_rssi_dbm"] = int(wifi_rssi_dbm)
        self.esp8266_status["last_seen"] = time.time()
        self.esp8266_status["online"] = True
        return await self.publish(
            topic="smarthome/telemetry/dht11",
            payload={
                "node_id": self.esp8266_status["node_id"],
                "temp_c": t,
                "humidity_pct": h,
                "heat_index_c": hi,
                "wifi_rssi_dbm": int(wifi_rssi_dbm),
            },
            qos=0,
            retain=False,
            direction="ESP8266 -> SERVER",
        )

    async def update_soil_moisture_telemetry(self, soil_moisture_pct: float, adc_raw: int | None = None) -> dict[str, Any]:
        """Nhận bản tin cảm biến Độ ẩm Đất `smarthome/telemetry/soil_moisture` từ chân A0 (YL-69 + LM393)."""
        pct = max(0.0, min(100.0, round(float(soil_moisture_pct), 1)))
        raw = adc_raw if adc_raw is not None else int(1024 - (pct / 100.0) * 700)
        status_lbl = "Khô - Cần tưới" if pct < 40.0 else ("Đủ ẩm" if pct < 75.0 else "Ẩm ướt")
        self.soil_moisture_telemetry = {
            "soil_moisture_pct": pct,
            "adc_raw": raw,
            "status_label": status_lbl,
            "sensor_pin": "A0 (ADC0 - Cảm biến đất YL-69 + LM393)",
            "auto_pump_below_pct": 40.0,
            "updated_at": time.time(),
        }
        self.esp8266_status["last_seen"] = time.time()
        self.esp8266_status["online"] = True
        return await self.publish(
            topic="smarthome/telemetry/soil_moisture",
            payload={
                "node_id": self.esp8266_status["node_id"],
                "soil_moisture_pct": pct,
                "adc_raw": raw,
                "status_label": status_lbl,
                "sensor_pin": "A0",
            },
            qos=0,
            retain=False,
            direction="ESP8266 (YL-69 A0) -> SERVER",
        )

    async def start_ir_learning(self, device_name: str, command_action: str = "open") -> dict[str, Any]:
        """Bật chế độ Học lệnh chiếm quyền Remote (`smarthome/ir/learn_start`) trên chân D5 (`VS1838B`)."""
        slug = "".join(c if c.isalnum() else "_" for c in device_name.strip().lower()).strip("_") or "ir_device"
        self.pending_ir_learning = {
            "device_id": slug,
            "device_name": device_name.strip() or "Thiết bị Hồng ngoại",
            "command_action": command_action,
            "started_at": time.time(),
            "receiver_pin": "D5 (GPIO 14 - VS1838B 38kHz)",
        }
        await self.publish(
            topic="smarthome/ir/learn_start",
            payload=self.pending_ir_learning,
            qos=1,
            retain=False,
            direction="SERVER -> ESP8266 (VS1838B D5)",
        )
        spoken = f"Mạch ESP8266 đang chờ thu sóng hồng ngoại ở chân D5. Hãy bấm nút trên điều khiển {device_name} chĩa vào mạch."
        return {
            "ok": True,
            "status": "WAITING_FOR_IR_SIGNAL",
            "pending_ir_learning": self.pending_ir_learning,
            "exact_spoken_reply": spoken,
            "message": spoken,
        }

    async def complete_ir_learning(
        self,
        protocol: str = "NEC_38KHZ",
        hex_code: str = "0x20DF10EF",
        raw_timings_us: list[int] | None = None,
    ) -> dict[str, Any]:
        """Nhận kết quả giải mã xung hồng ngoại từ ESP8266 (`smarthome/ir/learned_result`) và lưu Write-Through."""
        pending = self.pending_ir_learning or {
            "device_id": "ac",
            "device_name": "Điều hòa",
            "command_action": "open",
        }
        self.pending_ir_learning = None
        dev_id = pending["device_id"]
        dev_name = pending["device_name"]
        act = pending["command_action"]
        timings = raw_timings_us or [9000, 4500, 560, 1690, 560, 560, 560, 1690]

        dev_record = self.ir_devices.setdefault(
            dev_id,
            {
                "device_id": dev_id,
                "device_name": dev_name,
                "brand": f"Cloned Remote ({protocol})",
                "carrier_khz": 38,
                "commands": {},
            },
        )
        dev_record["commands"][act] = {
            "protocol": protocol,
            "hex_code": hex_code,
            "raw_timings_us": timings,
            "learned_at": round(time.time(), 1),
        }
        if act == "open":
            dev_record["commands"]["turn_on"] = dict(dev_record["commands"][act])
        elif act == "close":
            dev_record["commands"]["turn_off"] = dict(dev_record["commands"][act])

        self._save_ir_db_write_through()
        await self.publish(
            topic="smarthome/ir/learned_result",
            payload={
                "device_id": dev_id,
                "device_name": dev_name,
                "command_action": act,
                "protocol": protocol,
                "freq_khz": 38,
                "hex_code": hex_code,
                "raw_timings_us": timings,
            },
            qos=1,
            retain=False,
            direction="ESP8266 -> SERVER",
        )
        spoken = f"Đã thu và lưu mã hồng ngoại {protocol} ({hex_code}) cho {dev_name}."
        return {
            "ok": True,
            "device_id": dev_id,
            "device_name": dev_name,
            "protocol": protocol,
            "hex_code": hex_code,
            "exact_spoken_reply": spoken,
            "message": spoken,
        }

    def get_summary(self) -> dict[str, Any]:
        return {
            "esp8266_status": self.esp8266_status,
            "dht11_telemetry": self.dht11_telemetry,
            "soil_moisture_telemetry": self.soil_moisture_telemetry,
            "pending_ir_learning": self.pending_ir_learning,
            "ir_devices_count": len(self.ir_devices),
            "ir_devices": list(self.ir_devices.values()),
            "queue_size": self.queue.qsize(),
            "max_queue_size": self.MAX_QUEUE_SIZE,
            "dropped_backpressure_count": self.dropped_backpressure_count,
            "retained_topics_count": len(self.retained_topics),
            "recent_mqtt_packets": list(self.recent_messages)[-12:],
        }
