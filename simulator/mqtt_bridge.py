"""Tầng Truyền Thông Bất Đồng Bộ MQTT (Message Queue Pub/Sub, Back Pressure & Edge Sync)
áp dụng trực tiếp chuẩn kiến trúc The System Design Primer:

1. Asynchronism & Message Queues:
   - Hàng đợi bản tin bất đồng bộ (`asyncio.Queue` với giới hạn `MAX_QUEUE_SIZE = 256` chống tràn bộ nhớ - Back Pressure).
   - Hỗ trợ kết nối tới MQTT Broker chuẩn (TCP cổng 1883) HOẶC tự vận hành Embedded MQTT Message Bus nội bộ (Zero-Config).
2. CAP Theorem & Active-Passive Edge Failover:
   - Tự động đồng bộ bản sao (Replica) của Bể 1 (Hẹn giờ) và Bể 2 (Luật IF-ELSE) qua Topic `smarthome/sync/pools` (`Retain=True`) xuống bộ nhớ Flash (`LittleFS`) của NodeMCU ESP8266.
3. Telemetry Cảm biến (`DHT11`, `YL-69/LM393`, `KY-037/038`) & Đồng bộ Edge:
   - Lưu trữ và phân phối thông số thời gian thực của 3 cảm biến (`D2`, `A0`, `D5`) qua các Topic MQTT chuẩn.
"""

from __future__ import annotations

import asyncio
import collections
import json
import math
import pathlib
import time
from typing import Any, Callable, Awaitable

from simulator.engine.constants_and_time import resolve_data_dir

DATA_DIR = resolve_data_dir()
EDGE_REPLICA_FILE = DATA_DIR / "esp8266_flash_replica.json"

# Bảng ánh xạ 6 thiết bị chấp hành sang chân vật lý của NodeMCU ESP8266 (ESP-12E)
ESP8266_PIN_MAP: dict[str, dict[str, Any]] = {
    "main_door": {"pin": "D1", "gpio": 5, "mode": "PWM_SERVO"},
    "living_room_light": {"pin": "D0", "gpio": 16, "mode": "DIGITAL_OUT"},
    "bedroom_light": {"pin": "D4", "gpio": 2, "mode": "DIGITAL_OUT_SAFE_BOOT"},
    "garden_pump": {"pin": "D6", "gpio": 12, "mode": "RELAY_PUMP_5V_DIODE_1N4007"},
    "alarm_siren": {"pin": "D8", "gpio": 15, "mode": "DIGITAL_OUT_ACTIVE_HIGH"},
    "speaker_amp": {"pin": "D7", "gpio": 13, "mode": "RELAY_PAM8403_POWER_PWM_D3"},
}

ESP8266_SENSOR_PIN_MAP: dict[str, dict[str, Any]] = {
    "dht11": {"pin": "D2", "gpio": 4, "mode": "ONE_WIRE_DHT11"},
    "soil_moisture": {"pin": "A0", "gpio": 0, "mode": "ADC0_SOIL_LM393"},
    "sound": {"pin": "D5", "gpio": 14, "mode": "DIGITAL_IN_KY037_DO"},
    "speaker_audio_pwm": {"pin": "D3", "gpio": 0, "mode": "AUDIO_PWM_OUT_RC"},
}


class SmartHomeMQTTBridge:
    """Bộ điều phối bản tin MQTT chuẩn System Design Primer:
    - Quản lý Topic MQTT chuẩn giữa Server <-> NodeMCU ESP8266 <-> Web/Mobile App.
    - Áp dụng Back Pressure (`max_queue_size=256`), Retained Messages, Last Will (LWT) và Edge Sync.
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

        # Trạng thái kết nối của NodeMCU ESP8266 & 3 Cảm biến (In-Memory Cache)
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
            "sensor_pin": "D2 (GPIO 4)",
            "updated_at": time.time(),
        }
        self.soil_moisture_telemetry: dict[str, Any] = {
            "soil_moisture_pct": 62.0,
            "adc_raw": 420,
            "status_label": "Đủ ẩm",
            "sensor_pin": "A0 (ADC0 - Cảm biến đất + LM393)",
            "auto_pump_below_pct": 40.0,
            "auto_stop_above_pct": 70.0,
            "updated_at": time.time(),
        }
        self.sound_telemetry: dict[str, Any] = {
            "sound_detected": False,
            "detected": False,
            "loud_sound": False,
            "do_state": 0,
            "event_count": 0,
            "last_event_at": 0.0,
            "status_label": "Yên tĩnh",
            "sensor_pin": "D5 (GPIO 14)",
            "voice_ai_mic_note": "Gemini Voice AI dùng mic/loa web-device; KY-037 DO trên D5 phát hiện vỗ tay/tiếng động lớn.",
            "updated_at": time.time(),
        }

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
        """Xuất bản tin MQTT điều khiển phần cứng ESP8266 (`smarthome/cmd/actuate`)."""
        pin_info = ESP8266_PIN_MAP.get(device_id, {"pin": "D0", "gpio": 16, "mode": "DIGITAL_OUT"})
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
        pin_info = ESP8266_PIN_MAP.get(device_id, {"pin": "D0", "gpio": 16})
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
            "offline_voice_policy": "TIER_1_AND_2_ONLY (Chặn Tầng 3 Khách & Người lạ, Tiny-DSP ~16ms)",
            "offline_voiceprints_t1_t2": [
                {"user_id": "tuan_anh", "name": "Nguyễn Tuấn Anh", "tier": 1, "f0_hz": 170.2, "centroid_hz": 1271.7, "tolerance_hz": 24.0},
                {"user_id": "thanh_vien_a", "name": "Thành viên A", "tier": 2, "f0_hz": 182.5, "centroid_hz": 1410.0, "tolerance_hz": 24.0},
                {"user_id": "thanh_vien_b", "name": "Thành viên B", "tier": 2, "f0_hz": 195.0, "centroid_hz": 1520.0, "tolerance_hz": 24.0},
            ],
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
        EDGE_REPLICA_FILE.write_bytes((json.dumps(replica_payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        self.esp8266_status["flash_synced"] = True
        self.esp8266_status["last_seen"] = time.time()
        return await self.publish(
            topic="smarthome/sync/pools",
            payload=replica_payload,
            qos=1,
            retain=True,
            direction="SERVER -> ESP8266 (Flash LittleFS)",
        )

    @staticmethod
    def _clamp_sensor_float(val: Any, min_val: float, max_val: float, fallback: float) -> float:
        """Ép kiểu và giới hạn (clamp) giá trị cảm biến an toàn, chống NaN/Inf biến thành 100%."""
        fb = fallback if (isinstance(fallback, (int, float)) and math.isfinite(float(fallback))) else min_val
        fb = round(max(min_val, min(max_val, float(fb))), 1)
        if val is None or isinstance(val, bool):
            return fb
        try:
            f = float(val)
        except (ValueError, TypeError):
            return fb
        if not math.isfinite(f):
            return fb
        return round(max(min_val, min(max_val, f)), 1)

    async def update_dht11_telemetry(self, temp_c: Any, humidity_pct: Any, wifi_rssi_dbm: Any = -52) -> dict[str, Any]:
        """Nhận bản tin cảm biến `smarthome/telemetry/dht11` từ chân D2 của ESP8266."""
        prev_t = self.dht11_telemetry.get("temp_c", 28.5)
        prev_h = self.dht11_telemetry.get("humidity_pct", 65.0)
        if not isinstance(prev_t, (int, float)) or not math.isfinite(float(prev_t)) or float(prev_t) >= 60.0:
            prev_t = 28.5
        if not isinstance(prev_h, (int, float)) or not math.isfinite(float(prev_h)) or float(prev_h) >= 100.0:
            prev_h = 65.0
        t = self._clamp_sensor_float(temp_c, 0.0, 60.0, float(prev_t))
        h = self._clamp_sensor_float(humidity_pct, 0.0, 100.0, float(prev_h))
        hi = round(t + 0.05 * h, 1)
        try:
            rssi_f = float(wifi_rssi_dbm)
            rssi_int = int(max(-100.0, min(0.0, rssi_f))) if math.isfinite(rssi_f) else -52
        except (ValueError, TypeError):
            rssi_int = -52
        self.dht11_telemetry = {
            "temp_c": t,
            "humidity_pct": h,
            "heat_index_c": hi,
            "wifi_rssi_dbm": rssi_int,
            "sensor_pin": "D2 (GPIO 4)",
            "updated_at": time.time(),
        }
        self.esp8266_status["wifi_rssi_dbm"] = rssi_int
        self.esp8266_status["last_seen"] = time.time()
        self.esp8266_status["online"] = True
        return await self.publish(
            topic="smarthome/telemetry/dht11",
            payload={
                "node_id": self.esp8266_status["node_id"],
                "temp_c": t,
                "humidity_pct": h,
                "heat_index_c": hi,
                "wifi_rssi_dbm": rssi_int,
            },
            qos=0,
            retain=False,
            direction="ESP8266 -> SERVER",
        )

    async def update_soil_moisture_telemetry(self, soil_moisture_pct: Any, adc_raw: int | None = None) -> dict[str, Any]:
        """Nhận bản tin cảm biến Độ ẩm Đất `smarthome/telemetry/soil_moisture` từ chân A0 (Đầu dò + LM393)."""
        prev_pct = self.soil_moisture_telemetry.get("soil_moisture_pct", 62.0)
        if not isinstance(prev_pct, (int, float)) or not math.isfinite(float(prev_pct)) or float(prev_pct) >= 100.0:
            prev_pct = 62.0
        pct = self._clamp_sensor_float(soil_moisture_pct, 0.0, 100.0, float(prev_pct))
        raw = adc_raw if adc_raw is not None else int(1024 - (pct / 100.0) * 700)
        status_lbl = "Khô - Cần tưới" if pct < 40.0 else ("Đủ ẩm" if pct < 70.0 else "Ẩm ướt")
        self.soil_moisture_telemetry = {
            "soil_moisture_pct": pct,
            "adc_raw": raw,
            "status_label": status_lbl,
            "sensor_pin": "A0 (ADC0 - Cảm biến đất + LM393)",
            "auto_pump_below_pct": 40.0,
            "auto_stop_above_pct": 70.0,
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
            direction="ESP8266 (Soil A0) -> SERVER",
        )

    async def update_sound_telemetry(
        self,
        sound_detected: Any = False,
        do_state: Any = None,
        note: str = "",
    ) -> dict[str, Any]:
        """Nhận bản tin cảm biến Âm thanh KY-037/038 `smarthome/telemetry/sound` từ chân D5 (GPIO14 DO)."""
        if do_state is not None and not isinstance(do_state, bool):
            try:
                is_loud = int(float(do_state)) != 0
            except (TypeError, ValueError):
                is_loud = bool(sound_detected)
        elif isinstance(sound_detected, str):
            is_loud = sound_detected.strip().lower() in ("1", "true", "yes", "on", "high", "detected", "loud")
        else:
            is_loud = bool(sound_detected)

        now = time.time()
        prev_count = int(self.sound_telemetry.get("event_count", 0) or 0)
        prev_last_evt = float(self.sound_telemetry.get("last_event_at", 0.0) or 0.0)
        new_count = prev_count + (1 if is_loud else 0)
        new_last_evt = now if is_loud else prev_last_evt
        status_lbl = "Phát hiện tiếng động lớn / vỗ tay" if is_loud else "Yên tĩnh"
        self.sound_telemetry = {
            "sound_detected": is_loud,
            "detected": is_loud,
            "loud_sound": is_loud,
            "do_state": 1 if is_loud else 0,
            "event_count": new_count,
            "last_event_at": new_last_evt,
            "status_label": status_lbl,
            "sensor_pin": "D5 (GPIO 14)",
            "voice_ai_mic_note": "Gemini Voice AI dùng mic/loa web-device; KY-037 DO trên D5 phát hiện vỗ tay/tiếng động lớn.",
            "note": str(note or ""),
            "updated_at": now,
        }
        self.esp8266_status["last_seen"] = now
        self.esp8266_status["online"] = True
        return await self.publish(
            topic="smarthome/telemetry/sound",
            payload={
                "node_id": self.esp8266_status["node_id"],
                "sound_detected": is_loud,
                "do_state": 1 if is_loud else 0,
                "event_count": new_count,
                "status_label": status_lbl,
                "sensor_pin": "D5",
            },
            qos=0,
            retain=False,
            direction="ESP8266 (KY-037 D5) -> SERVER",
        )

    def get_summary(self) -> dict[str, Any]:
        return {
            "esp8266_status": self.esp8266_status,
            "dht11_telemetry": self.dht11_telemetry,
            "soil_moisture_telemetry": self.soil_moisture_telemetry,
            "sound_telemetry": self.sound_telemetry,
            "ky037_telemetry": self.sound_telemetry,
            "queue_size": self.queue.qsize(),
            "max_queue_size": self.MAX_QUEUE_SIZE,
            "dropped_backpressure_count": self.dropped_backpressure_count,
            "retained_topics_count": len(self.retained_topics),
            "recent_mqtt_packets": list(self.recent_messages)[-12:],
        }
