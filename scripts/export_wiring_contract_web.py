#!/usr/bin/env python3
"""Export `hardware/wiring_contract.py` (SSOT), `hardware/wire_lengths.json`, and
`hardware/component_dimensions_ssot.py` to `web/data/wiring_contract.json`.

Deterministic web data generator so every web circuit/3D view reads pinouts,
wire colors, connectors, modules, routed 3D wire lengths/waypoints, on-board
passives (C1-C9, D1-D3, Q1, R1-R10), datasheet dimensions, and step-by-step
wiring instructions directly from the single hardware source of truth without
hand-copied lists (PCB-direct build, zero breadboard).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hardware.component_dimensions_ssot import COMPONENT_DIMENSIONS  # noqa: E402
from hardware.wiring_contract import (  # noqa: E402
    FIRMWARE_PIN_CONTRACT,
    HUB_CONNECTOR_MAP,
    HUB_CONNECTORS,
    MODULE_DIMENSIONS_MM,
    PROTECTION_COMPONENTS,
    WIRE_COLORS,
    WIRING_TABLE,
    WireEntry,
)

DEFAULT_OUTPUT = REPO_ROOT / "web" / "data" / "wiring_contract.json"
WIRE_LENGTHS_JSON = REPO_ROOT / "hardware" / "wire_lengths.json"

COLOR_LABELS_VI: dict[str, str] = {
    "Red": "Đỏ",
    "Black": "Đen",
    "Orange": "Cam",
    "Yellow": "Vàng",
    "Green": "Xanh lá",
    "Blue": "Xanh dương",
    "Cyan": "Xanh lơ",
    "Purple": "Tím",
    "White": "Trắng",
    "Brown": "Nâu",
}

COLOR_ROLES_VI: dict[str, str] = {
    "Red": "Nguồn (+5V / +3.3V / +5V qua rơ-le)",
    "Black": "Mass chung (GND)",
    "Orange": "Tín hiệu (Servo D1, Còi D8, Rơ-le 2 NO, Đầu dò B)",
    "Yellow": "Tín hiệu (Đèn khách D0, KY-037 D5, Rơ-le 1 NO, Loa+, Đầu dò A)",
    "Green": "Tín hiệu (Rơ-le 1 IN D6, Độ ẩm đất AO A0)",
    "Blue": "Tín hiệu (Cảm biến DHT11 DATA D2)",
    "Cyan": "Tín hiệu (Rơ-le 2 IN D7)",
    "Purple": "Tín hiệu (Cực dương Đèn ngủ qua R2 220Ω)",
    "White": "Tín hiệu (Cực âm Đèn ngủ D4, Âm thanh PWM D3)",
    "Brown": "Âm thanh vi sai (PAM8403 L_OUT- tới Loa-, KHÔNG nối GND)",
}

MODULE_LABELS_VI: dict[str, str] = {
    "psu_5v": "Nguồn ngoài 5V 2A",
    "sg90_servo": "Động cơ Servo SG90 (Cửa chính)",
    "led_living": "Đèn LED 5mm Phòng khách (D0)",
    "led_bedroom": "Đèn LED 5mm Phòng ngủ (D4)",
    "relay1_pump": "Rơ-le 1 Xanh 5V (Máy bơm, D6)",
    "pump_unit": "Máy bơm chìm mini 3–6V",
    "buzzer_alarm": "Còi báo động 5V TMB12A05 (D8)",
    "relay2_speaker": "Rơ-le 2 Đỏ Opto 5V (Nguồn loa, D7)",
    "pam8403_amp": "Mạch khuếch đại loa PAM8403",
    "speaker_mini": "Loa tròn mini 28mm 8Ω 0.5W",
    "dht11_sensor": "Cảm biến nhiệt độ & độ ẩm DHT11 (D2)",
    "soil_lm393": "Mạch so sánh độ ẩm đất LM393 (A0)",
    "soil_probe": "Đầu dò độ ẩm đất YL-69",
    "ky037_sound": "Cảm biến âm thanh KY-037/KY-038 (D5)",
}

MODULE_WOKWI_GROUP: dict[str, str] = {
    "psu_5v": "power",
    "sg90_servo": "d1_servo",
    "led_living": "d0_living",
    "led_bedroom": "d4_bedroom",
    "relay1_pump": "d6_pump",
    "pump_unit": "d6_pump",
    "buzzer_alarm": "d8_buzzer",
    "relay2_speaker": "d3_d7_speaker",
    "pam8403_amp": "d3_d7_speaker",
    "speaker_mini": "d3_d7_speaker",
    "dht11_sensor": "d2_dht11",
    "soil_lm393": "a0_soil",
    "soil_probe": "a0_soil",
    "ky037_sound": "d5_ky037",
}

MODULE_HOUSE3D_KEY: dict[str, str] = {
    "psu_5v": "power",
    "sg90_servo": "d1_door",
    "led_living": "d0_living",
    "led_bedroom": "d4_bedroom",
    "relay1_pump": "d6_pump",
    "pump_unit": "d6_pump",
    "buzzer_alarm": "d8_siren",
    "relay2_speaker": "d7_d3_speaker",
    "pam8403_amp": "d7_d3_speaker",
    "speaker_mini": "d7_d3_speaker",
    "dht11_sensor": "d2_dht11",
    "soil_lm393": "a0_soil",
    "soil_probe": "a0_soil",
    "ky037_sound": "d5_ky037",
}

WIRE_TYPE_VI: dict[str, str] = {
    "Screw Terminal 22AWG": "Cầu đấu vít 22AWG",
    "Dupont 1x3 F-M": "Dây Dupont 1x3 Cái–Đực",
    "Dupont 1x2 F-F": "Dây Dupont 1x2 Cái–Cái",
    "Dupont 1x3 F-F": "Dây Dupont 1x3 Cái–Cái",
    "Dupont F-Pin (22AWG)": "Dây Dupont Cái–Đầu cốt (22AWG)",
    "Dupont F-Pin": "Dây Dupont Cái–Đầu cốt",
    "2-Wire Pair": "Cặp 2 dây xoắn",
}

# All 23 active/passive/indicator parts soldered directly on the 100x80mm Hub DIY v3 PCB
ONBOARD_PASSIVES_SPEC: tuple[dict[str, str], ...] = (
    {"ref": "R1", "kind": "resistor", "value": "220 Ω", "package": "1/4W Axial (DIN0207)", "nets": "D0_LED_LR ↔ LED_LR_A", "role_vi": "Điện trở hạn dòng LED 5mm Phòng khách (J4, Active-HIGH)."},
    {"ref": "R2", "kind": "resistor", "value": "220 Ω", "package": "1/4W Axial (DIN0207)", "nets": "+3V3 ↔ LED_BR_A", "role_vi": "Điện trở hạn dòng LED 5mm Phòng ngủ (J5, Active-LOW an toàn boot)."},
    {"ref": "R3", "kind": "resistor", "value": "10 kΩ", "package": "1/4W Axial (DIN0207)", "nets": "+3V3 ↔ D2_DHT11", "role_vi": "Điện trở kéo lên đường dữ liệu 1-Wire cảm biến DHT11 (J13)."},
    {"ref": "R4", "kind": "resistor", "value": "10 kΩ", "package": "1/4W Axial (DIN0207)", "nets": "+3V3 ↔ D3_AUDIO_PWM", "role_vi": "Điện trở kéo lên chân boot-strap D3 (GPIO0) giữ mức HIGH khi khởi động."},
    {"ref": "R5", "kind": "resistor", "value": "2.2 kΩ", "package": "1/4W Axial (DIN0207)", "nets": "AUD_AC ↔ AUD_OUT", "role_vi": "Nhánh trên cầu phân áp RC giảm biên độ âm thanh PWM vào PAM8403 (J12)."},
    {"ref": "R6", "kind": "resistor", "value": "2.2 kΩ", "package": "1/4W Axial (DIN0207)", "nets": "AUD_OUT ↔ GND", "role_vi": "Nhánh dưới cầu phân áp RC (~50% biên độ) vào PAM8403 (J12)."},
    {"ref": "R7", "kind": "resistor", "value": "10 kΩ", "package": "1/4W Axial (DIN0207)", "nets": "+3V3 ↔ D4_LED_BR", "role_vi": "Điện trở kéo lên chân boot-strap D4 (GPIO2) giữ mức HIGH khi khởi động."},
    {"ref": "R8", "kind": "resistor", "value": "1 kΩ", "package": "1/4W Axial (DIN0207)", "nets": "+5V ↔ PWR_LED_A", "role_vi": "Điện trở hạn dòng đèn LED xanh báo nguồn +5V trên PCB (D3)."},
    {"ref": "R9", "kind": "resistor", "value": "10 kΩ", "package": "1/4W Axial (DIN0207)", "nets": "D8_BUZZER ↔ GND", "role_vi": "Điện trở kéo xuống chân boot-strap D8 (GPIO15) giúp khởi động an toàn và im còi lúc mở nguồn."},
    {"ref": "R10", "kind": "resistor", "value": "1 kΩ", "package": "1/4W Axial (DIN0207)", "nets": "D8_BUZZER ↔ BUZZ_BASE", "role_vi": "Điện trở hạn dòng cực Base cho transistor NPN Q1 S8050 lái còi 5V."},
    {"ref": "Q1", "kind": "transistor", "value": "S8050", "package": "TO-92 Wide (E-B-C)", "nets": "E=GND, B=BUZZ_BASE, C=BUZZ_K", "role_vi": "Transistor NPN lái cực âm cho còi báo động 5V TMB12A05 (J6), bảo vệ GPIO15."},
    {"ref": "C1", "kind": "capacitor", "value": "470 µF 16V", "package": "Radial Ø8.0×P3.5mm", "nets": "+5V ↔ GND", "role_vi": "Tụ hóa lọc nguồn chính +5V, cấp dòng xung đỉnh cho Servo SG90 (J3)."},
    {"ref": "C2", "kind": "capacitor", "value": "470 µF 16V", "package": "Radial Ø8.0×P3.5mm", "nets": "+5V ↔ GND", "role_vi": "Tụ hóa lọc nguồn +5V gần J1/J2, ổn áp khi khởi động máy bơm mini 3–6V."},
    {"ref": "C3", "kind": "capacitor", "value": "100 nF 50V", "package": "Ceramic Disc P5.0mm", "nets": "+5V ↔ GND", "role_vi": "Tụ gốm lọc nhiễu cao tần trên đường nguồn +5V trước VIN NodeMCU."},
    {"ref": "C4", "kind": "capacitor", "value": "10 µF 16V", "package": "Radial Ø5.0×P3.5mm", "nets": "D3_AUDIO_PWM ↔ AUD_AC", "role_vi": "Tụ hóa chặn thành phần DC (DC-block), cô lập chân boot-strap D3 (GPIO0)."},
    {"ref": "C5", "kind": "capacitor", "value": "10 nF 50V", "package": "Ceramic Disc P5.0mm", "nets": "AUD_OUT ↔ GND", "role_vi": "Tụ gốm lọc thông thấp RC làm mịn tín hiệu PWM vào PAM8403."},
    {"ref": "C6", "kind": "capacitor", "value": "100 nF 50V", "package": "Ceramic Disc P5.0mm", "nets": "AMP_5V ↔ GND", "role_vi": "Tụ gốm lọc nhiễu cao tần trên đường nguồn +5V đóng cắt cấp cho PAM8403 (J11)."},
    {"ref": "C7", "kind": "capacitor", "value": "100 nF 50V", "package": "Ceramic Disc P5.0mm", "nets": "A0_SOIL ↔ GND", "role_vi": "Tụ gốm lọc nhiễu tương tự cho chân ADC0 (A0) cảm biến độ ẩm đất LM393 (J14)."},
    {"ref": "C8", "kind": "capacitor", "value": "100 nF 50V", "package": "Ceramic Disc P5.0mm", "nets": "+3V3 ↔ GND", "role_vi": "Tụ gốm lọc nhiễu cao tần hàn trực tiếp trên PCB Hub cạnh J14 cho đường nguồn +3.3V (ESP8266 & 3 cảm biến J13–J15)."},
    {"ref": "C9", "kind": "capacitor", "value": "100 µF 16V", "package": "Radial Ø6.3×P3.5mm", "nets": "AMP_5V ↔ GND", "role_vi": "Tụ hóa dự trữ năng lượng hàn trực tiếp trên PCB Hub cạnh J11 (song song C6) cho mạch loa Class-D PAM8403."},
    {"ref": "D1", "kind": "flyback_diode", "value": "1N4007", "package": "DO-41 P10.16mm", "nets": "K=PUMP_5V, A=GND", "role_vi": "Diode dập xung ngược (Flyback) bảo vệ mạch khi Rơ-le 1 ngắt máy bơm 3–6V (J2)."},
    {"ref": "D2", "kind": "flyback_diode", "value": "1N4007", "package": "DO-41 P10.16mm", "nets": "K=+5V, A=BUZZ_K", "role_vi": "Diode dập xung ngược (Flyback) bảo vệ transistor Q1 S8050 trước cuộn dây còi 5V (J6)."},
    {"ref": "D3", "kind": "indicator_led", "value": "LED Xanh 3mm", "package": "3mm Green LED (T-1)", "nets": "A=PWR_LED_A, K=GND", "role_vi": "Đèn LED xanh báo có nguồn +5V trên mạch PCB Hub (nối tiếp R8 1kΩ)."},
)


def _load_wire_lengths() -> dict[str, Any]:
    if not WIRE_LENGTHS_JSON.exists():
        return {}
    return json.loads(WIRE_LENGTHS_JSON.read_text(encoding="utf-8"))


def _get_hub_pin_xy_mm(hub_ref: str, hub_pin: str) -> list[float] | None:
    conn = HUB_CONNECTOR_MAP.get(hub_ref)
    if conn is None:
        return None
    for p_num, rx, ry, _net in conn.pins:
        if str(p_num) == str(hub_pin):
            return [round(float(rx), 2), round(float(ry), 2)]
    return None


def _build_power_gnd_note_vi(w: WireEntry) -> str:
    """Derive a concise Vietnamese electrical/power/GND/boot-safety note from the contract fields."""
    notes_low = w.notes.lower()
    net = w.net
    parts: list[str] = []

    if net == "+3V3" or "3.3v" in notes_low or "3v3" in w.nodemcu_pin.lower():
        if "strictly 3.3v" in notes_low:
            parts.append(
                "Nguồn +3.3V BẮT BUỘC (tuyệt đối không cấp +5V để bảo vệ chân ESP8266; "
                "lọc nhiễu bằng tụ C8 100nF hàn trên PCB Hub + tụ 10µF của AMS1117 trên NodeMCU v2 Amica)."
            )
        elif w.module_id == "led_bedroom":
            parts.append("Nguồn +3.3V qua trở hạn dòng R2 220Ω trên PCB Hub (đấu Active-LOW an toàn khởi động).")
        else:
            parts.append("Nguồn cảm biến +3.3V lấy từ nhánh 3V3 trên PCB Hub (đã có tụ gốm C8 100nF hàn trên PCB lọc nhiễu cao tần).")
    elif net == "+5V":
        parts.append("Nguồn chính +5V (đã có tụ lọc C1/C2 470µF 16V và C3 100nF hàn trực tiếp trên PCB Hub).")
    elif net in ("PUMP_5V", "AMP_5V"):
        if net == "PUMP_5V":
            parts.append("Nguồn +5V đóng cắt qua tiếp điểm Rơ-le 1 (có diode dập xung D1 1N4007 hàn trên PCB Hub).")
        else:
            parts.append(
                "Nguồn +5V đóng cắt qua Rơ-le 2 cấp cho PAM8403 "
                "(đã lọc nhiễu bằng cặp tụ C6 100nF + tụ hóa C9 100µF 16V hàn trực tiếp trên PCB Hub cạnh J11)."
            )
    elif net == "GND":
        parts.append("Dây Mass chung (GND) nối về thanh GND chung của PCB Hub và NodeMCU v2 Amica.")
    elif "btl" in notes_low:
        parts.append("Ngõ ra loa vi sai BTL từ PAM8403: TUYỆT ĐỐI KHÔNG nối L_OUT- xuống GND.")

    if w.net == "D4_LED_BR":
        parts.append("Đấu Active-LOW trên D4 (GPIO2) kèm trở kéo lên R7 10kΩ để an toàn khi khởi động.")
    elif w.net == "AUD_OUT":
        parts.append("Qua tụ chặn DC C4 10µF 16V, cầu R5/R6 2.2kΩ, C5 10nF và R4 10kΩ kéo lên 3.3V (chân D3 ở chế độ INPUT khi nghỉ).")
    elif w.net == "BUZZ_K":
        parts.append("Lái cực âm qua R10 1kΩ → transistor NPN Q1 (S8050) + R9 10kΩ kéo xuống GND + diode D2 1N4007 (không nối trực tiếp còi vào D8).")
    elif w.net == "D2_DHT11":
        parts.append("Đường dữ liệu 1-Wire DHT11 đã có trở kéo lên R3 10kΩ lên +3.3V trên PCB Hub.")
    elif w.net == "A0_SOIL":
        parts.append("Ngõ vào tương tự ADC0 đã lọc nhiễu bởi tụ C7 100nF trên PCB; bơm tự bật <40% và tắt ≥70%.")
    elif w.net == "D5_MIC_DO":
        parts.append("Ngõ vào số 3.3V bắt xung vỗ tay/tiếng động (ngắt sườn lên, chống dội ≥400ms).")
    elif w.net == "D1_SERVO":
        parts.append("Tín hiệu PWM 50Hz điều khiển Servo SG90 (0° đóng cửa / 90° mở cửa).")
    elif w.net == "LED_LR_A":
        parts.append("Đấu Active-HIGH qua điện trở hạn dòng R1 220Ω trên PCB Hub.")
    elif w.net == "D6_RLY1_PUMP":
        parts.append("Kích mức CAO (Active-HIGH) điều khiển cuộn hút Rơ-le 1 cho máy bơm.")
    elif w.net == "D7_RLY2_AMP":
        parts.append("Kích mức CAO (Active-HIGH, đặt jumper Rơ-le 2 về H); tự ngắt sau 1,5 giây khi phát chuông xong.")
    elif w.net in ("SOIL_PROBE_A", "SOIL_PROBE_B"):
        parts.append("Cặp 2 dây nối trực tiếp từ mạch so sánh LM393 tới 2 nhánh đầu dò đất YL-69.")

    if not parts:
        parts.append(f"Mạng tín hiệu {w.net} ({w.gpio}).")
    return " ".join(parts)


def _build_instruction_vi(w: WireEntry, module_label_vi: str, color_vi: str, length_cm: float | None = None, std_cm: int | None = None) -> str:
    """Build a crisp Vietnamese step instruction directly from contract endpoints."""
    len_suffix = ""
    if length_cm is not None and std_cm is not None:
        len_suffix = f" (chiều dài thực tế ~{length_cm:.2f} cm, dùng dây chuẩn {std_cm} cm)."
    elif length_cm is not None:
        len_suffix = f" (chiều dài thực tế ~{length_cm:.2f} cm)."
    else:
        len_suffix = "."

    if w.hub_ref.startswith("J"):
        return (
            f"Cắm trực tiếp từ chân {w.hub_label} trên PCB Hub tới chân {w.module_pin} của {module_label_vi} "
            f"(nối về {w.nodemcu_pin}, {w.gpio}) bằng dây màu {color_vi}{len_suffix}"
        )
    return (
        f"Nối trực tiếp chân {w.module_pin} của {module_label_vi} tới chân {w.hub_label} "
        f"(dây liên kết ngoài mạch Hub) bằng dây màu {color_vi}{len_suffix}"
    )


def build_web_contract_payload() -> dict[str, Any]:
    """Build deterministic JSON-serializable payload from `hardware/wiring_contract.py` + `wire_lengths.json`."""
    wl_data = _load_wire_lengths()
    wl_by_id: dict[str, dict[str, Any]] = {
        str(item["wire_id"]): item for item in (wl_data.get("wires") or []) if "wire_id" in item
    }

    wire_colors: dict[str, dict[str, Any]] = {}
    for color_name, meta in WIRE_COLORS.items():
        wire_colors[color_name] = {
            "hex": str(meta["hex"]),
            "role": str(meta["role"]),
            "label_vi": COLOR_LABELS_VI.get(color_name, color_name),
            "role_vi": COLOR_ROLES_VI.get(color_name, str(meta["role"])),
        }

    module_order: list[str] = []
    module_wires: dict[str, list[str]] = {}
    module_names: dict[str, str] = {}

    wires_out: list[dict[str, Any]] = []
    for idx, w in enumerate(WIRING_TABLE, start=1):
        if w.module_id not in module_wires:
            module_order.append(w.module_id)
            module_wires[w.module_id] = []
            module_names[w.module_id] = w.module_name
        module_wires[w.module_id].append(w.wire_id)

        color_vi = COLOR_LABELS_VI.get(w.color, w.color)
        color_hex = str(WIRE_COLORS[w.color]["hex"])
        mod_vi = MODULE_LABELS_VI.get(w.module_id, w.module_name)
        wokwi_group = MODULE_WOKWI_GROUP.get(w.module_id, "power")
        house3d_key = MODULE_HOUSE3D_KEY.get(w.module_id, "power")
        wl = wl_by_id.get(w.wire_id, {})

        length_cm = float(wl["length_cm"]) if "length_cm" in wl else None
        straight_cm = float(wl["straight_cm"]) if "straight_cm" in wl else None
        routed_cm = float(wl["routed_cm"]) if "routed_cm" in wl else None
        recommended_std_cm = int(wl["recommended_std_cm"]) if "recommended_std_cm" in wl else None
        recommended_note_vi = str(wl.get("recommended_note_vi") or "")
        within_30cm = bool(wl.get("within_30cm", True))
        route_channel = str(wl.get("route_channel") or "")
        waypoints_house_mm = wl.get("waypoints_house_mm") or []
        waypoints_threejs = wl.get("waypoints_threejs") or []
        hub_pin_xy_mm = _get_hub_pin_xy_mm(w.hub_ref, w.hub_pin)

        wires_out.append(
            {
                "step_number": idx,
                "wire_id": w.wire_id,
                "group": w.group,
                "hub_ref": w.hub_ref,
                "hub_pin": w.hub_pin,
                "hub_label": w.hub_label,
                "hub_pin_xy_mm": hub_pin_xy_mm,
                "is_hub_wire": w.hub_ref.startswith("J"),
                "module_id": w.module_id,
                "module_name": w.module_name,
                "module_label_vi": mod_vi,
                "module_pin": w.module_pin,
                "nodemcu_pin": w.nodemcu_pin,
                "gpio": w.gpio,
                "net": w.net,
                "color": w.color,
                "color_vi": color_vi,
                "color_hex": color_hex,
                "wire_type": w.wire_type,
                "wire_type_vi": WIRE_TYPE_VI.get(w.wire_type, w.wire_type),
                "fw_ref": w.fw_ref,
                "notes": w.notes,
                "power_gnd_note_vi": _build_power_gnd_note_vi(w),
                "instruction_vi": _build_instruction_vi(w, mod_vi, color_vi, length_cm, recommended_std_cm),
                "wokwi_group": wokwi_group,
                "house3d_wire_key": house3d_key,
                "length_cm": length_cm,
                "straight_cm": straight_cm,
                "routed_cm": routed_cm,
                "recommended_std_cm": recommended_std_cm,
                "recommended_note_vi": recommended_note_vi,
                "within_30cm": within_30cm,
                "route_channel": route_channel,
                "waypoints_house_mm": waypoints_house_mm,
                "waypoints_threejs": waypoints_threejs,
            }
        )

    modules_out: list[dict[str, Any]] = []
    for mid in module_order:
        dim_info = MODULE_DIMENSIONS_MM.get(mid, {})
        dims = dim_info.get("dims_mm")
        modules_out.append(
            {
                "module_id": mid,
                "module_name": module_names[mid],
                "label_vi": MODULE_LABELS_VI.get(mid, module_names[mid]),
                "wokwi_group": MODULE_WOKWI_GROUP.get(mid, "power"),
                "house3d_wire_key": MODULE_HOUSE3D_KEY.get(mid, "power"),
                "dims_mm": list(dims) if isinstance(dims, (tuple, list)) else None,
                "wire_ids": module_wires[mid],
                "wire_count": len(module_wires[mid]),
            }
        )

    connectors_out: list[dict[str, Any]] = []
    for c in HUB_CONNECTORS:
        connectors_out.append(
            {
                "ref": c.ref,
                "value": c.value,
                "kind": c.kind,
                "edge": c.edge,
                "rot_deg": c.rot_deg,
                "pins": [
                    {"pin_num": p_num, "rel_x": rx, "rel_y": ry, "net": net}
                    for p_num, rx, ry, net in c.pins
                ],
            }
        )

    firmware_pins_out: list[dict[str, Any]] = []
    for macro, (dx, gpio, hub_sig) in FIRMWARE_PIN_CONTRACT.items():
        firmware_pins_out.append(
            {
                "macro": macro,
                "nodemcu_pin": dx,
                "gpio": "ADC0" if gpio == -1 else f"GPIO{gpio}",
                "gpio_num": gpio,
                "hub_signal": hub_sig,
            }
        )

    protection_out: list[dict[str, Any]] = []
    for comp in PROTECTION_COMPONENTS:
        protection_out.append(
            {
                "ref": comp.ref,
                "kind": comp.kind,
                "kind_vi": "Diode dập xung" if comp.kind == "flyback_diode" else "Tụ điện",
                "value": comp.value,
                "voltage_rating": comp.voltage_rating,
                "polarity": comp.polarity,
                "placement_pins": comp.placement_pins,
                "net_pos": comp.net_pos,
                "net_neg": comp.net_neg,
                "role_vi": comp.role_vi,
                "datasheet_ref": comp.datasheet_ref,
                "pcb_status": comp.pcb_status,
                "pcb_status_vi": "Hàn trực tiếp trên PCB Hub" if comp.pcb_status == "onboard_pcb" else "Gắn ngoài bo",
            }
        )

    onboard_passives_out: list[dict[str, Any]] = [
        {
            **item,
            "pcb_status": "onboard_pcb",
            "pcb_status_vi": "Hàn trực tiếp trên PCB Hub",
        }
        for item in ONBOARD_PASSIVES_SPEC
    ]

    component_dimensions_out: list[dict[str, Any]] = []
    for spec in COMPONENT_DIMENSIONS:
        component_dimensions_out.append(
            {
                "component_id": spec.component_id,
                "category": spec.category,
                "label": spec.label,
                "label_vi": spec.label_vi,
                "dims_mm": list(spec.dims_mm),
                "overall_h_mm": spec.overall_h_mm,
                "pitch_mm": spec.pitch_mm,
                "hole_pitch_xy_mm": list(spec.hole_pitch_xy_mm) if spec.hole_pitch_xy_mm is not None else None,
                "hole_dia_mm": spec.hole_dia_mm,
                "tolerance_mm": spec.tolerance_mm,
                "kicad_ref": spec.kicad_ref,
                "kicad_footprint": spec.kicad_footprint,
                "datasheet_summary": spec.datasheet_summary,
                "source_name": spec.source_name,
                "source_url": spec.source_url,
                "pigtail_cm": spec.pigtail_cm,
                "notes": spec.notes,
            }
        )

    wire_lengths_summary = {
        "slack_factor": wl_data.get("slack_factor", 1.18),
        "max_allowed_cm": wl_data.get("max_allowed_cm", 30.0),
        "pcb_center_house_mm": wl_data.get("pcb_center_house_mm", [122.0, 104.0, 19.8]),
        "total_wires": wl_data.get("total_wires", len(wires_out)),
        "min_length_cm": wl_data.get("min_length_cm"),
        "max_length_cm": wl_data.get("max_length_cm"),
        "total_length_cm": wl_data.get("total_length_cm"),
        "total_standard_cm": wl_data.get("total_standard_cm"),
        "all_within_30cm": wl_data.get("all_within_30cm", True),
        "flagged_over_30cm": wl_data.get("flagged_over_30cm", []),
        "counts_by_standard_cm": wl_data.get("counts_by_standard_cm", {}),
        "purchasing_groups": wl_data.get("purchasing_groups", []),
    }

    body = {
        "default_view": "pcb_direct",
        "breadboard_used": False,
        "wire_lengths_summary": wire_lengths_summary,
        "wire_colors": wire_colors,
        "modules": modules_out,
        "wires": wires_out,
        "connectors": connectors_out,
        "firmware_pins": firmware_pins_out,
        "protection_components": protection_out,
        "onboard_passives": onboard_passives_out,
        "component_dimensions": component_dimensions_out,
    }
    canonical_bytes = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(canonical_bytes).hexdigest()

    hub_count = sum(1 for w in wires_out if w["is_hub_wire"])
    return {
        "schema_version": 2,
        "source": "hardware/wiring_contract.py",
        "contract_sha256": digest,
        "counts": {
            "wires": len(wires_out),
            "hub_wires": hub_count,
            "offboard_wires": len(wires_out) - hub_count,
            "connectors": len(connectors_out),
            "modules": len(modules_out),
            "firmware_pins": len(firmware_pins_out),
            "protection_components": len(protection_out),
            "onboard_passives": len(onboard_passives_out),
            "component_dimensions": len(component_dimensions_out),
        },
        **body,
    }


def serialize_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export hardware/wiring_contract.py to web JSON.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path.")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if output differs from fresh export.")
    args = parser.parse_args(argv)

    payload = build_web_contract_payload()
    rendered = serialize_payload(payload)

    if args.check:
        if not args.output.exists():
            print(f"[DRIFT] Missing exported contract file: {args.output}", file=sys.stderr)
            return 1
        existing = args.output.read_text(encoding="utf-8")
        if existing != rendered:
            print(f"[DRIFT] {args.output} does not match hardware/wiring_contract.py", file=sys.stderr)
            return 1
        print(f"[OK] {args.output} matches hardware/wiring_contract.py (sha256={payload['contract_sha256'][:12]})")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(
        f"[OK] Exported {payload['counts']['wires']} wires, {payload['counts']['modules']} modules, "
        f"{payload['counts']['connectors']} connectors, {payload['counts']['onboard_passives']} onboard passives, "
        f"{payload['counts']['component_dimensions']} component dims -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
