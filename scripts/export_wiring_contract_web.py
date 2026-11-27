#!/usr/bin/env python3
"""Export `hardware/wiring_contract.py` (SSOT) to `web/data/wiring_contract.json`.

Deterministic web data generator so every web circuit/3D view reads pinouts,
wire colors, connectors, modules, and step-by-step wiring instructions directly
from the single hardware source of truth without hand-copied lists.
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

from hardware.wiring_contract import (  # noqa: E402
    FIRMWARE_PIN_CONTRACT,
    HUB_CONNECTORS,
    MODULE_DIMENSIONS_MM,
    PROTECTION_COMPONENTS,
    WIRE_COLORS,
    WIRING_TABLE,
    WireEntry,
)

DEFAULT_OUTPUT = REPO_ROOT / "web" / "data" / "wiring_contract.json"

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


def _build_power_gnd_note_vi(w: WireEntry) -> str:
    """Derive a concise Vietnamese electrical/power/GND/boot-safety note from the contract fields."""
    notes_low = w.notes.lower()
    net = w.net
    parts: list[str] = []

    if net == "+3V3" or "3.3v" in notes_low or "3v3" in w.nodemcu_pin.lower():
        if "strictly 3.3v" in notes_low:
            parts.append("Nguồn +3.3V BẮT BUỘC (tuyệt đối không cấp +5V để bảo vệ chân ESP8266; lọc nhiễu bằng tụ C8 100nF ngoài bo + tụ 10µF của AMS1117 trên NodeMCU).")
        elif w.module_id == "led_bedroom":
            parts.append("Nguồn +3.3V qua trở hạn dòng R2 220Ω trên PCB Hub (đấu Active-LOW an toàn khởi động).")
        else:
            parts.append("Nguồn cảm biến +3.3V lấy từ nhánh 3V3 trên PCB Hub (khuyến nghị gắn thêm tụ gốm C8 100nF lọc nhiễu cao tần).")
    elif net == "+5V":
        parts.append("Nguồn chính +5V (đã có tụ lọc C1/C2 470µF 16V và C3 100nF trên PCB Hub).")
    elif net in ("PUMP_5V", "AMP_5V"):
        if net == "PUMP_5V":
            parts.append("Nguồn +5V đóng cắt qua tiếp điểm Rơ-le 1 (có diode dập xung D1 1N4007 trên Hub).")
        else:
            parts.append("Nguồn +5V đóng cắt qua Rơ-le 2 cấp cho PAM8403 (lọc nhiễu bởi tụ C6 100nF trên Hub + tụ hóa C9 100µF 16V ngoài bo tại J11/PAM8403).")
    elif net == "GND":
        parts.append("Dây Mass chung (GND) nối về thanh GND chung của PCB Hub và NodeMCU.")
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
        parts.append("Ngõ vào tương tự ADC0 đã lọc nhiễu bởi tụ C7 100nF; bơm tự bật <40% và tắt ≥70%.")
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


def _build_instruction_vi(w: WireEntry, module_label_vi: str, color_vi: str) -> str:
    """Build a crisp Vietnamese step instruction directly from contract endpoints."""
    if w.hub_ref.startswith("J"):
        return (
            f"Nối chân {w.module_pin} của {module_label_vi} tới chân {w.hub_label} trên PCB Hub "
            f"(nối về {w.nodemcu_pin}, {w.gpio}) bằng dây màu {color_vi}."
        )
    return (
        f"Nối trực tiếp chân {w.module_pin} của {module_label_vi} tới chân {w.hub_label} "
        f"(dây liên kết ngoài mạch Hub) bằng dây màu {color_vi}."
    )


def build_web_contract_payload() -> dict[str, Any]:
    """Build deterministic JSON-serializable payload from `hardware/wiring_contract.py`."""
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

        wires_out.append(
            {
                "step_number": idx,
                "wire_id": w.wire_id,
                "group": w.group,
                "hub_ref": w.hub_ref,
                "hub_pin": w.hub_pin,
                "hub_label": w.hub_label,
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
                "instruction_vi": _build_instruction_vi(w, mod_vi, color_vi),
                "wokwi_group": wokwi_group,
                "house3d_wire_key": house3d_key,
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
                "pcb_status_vi": (
                    "Hàn trên PCB Hub"
                    if comp.pcb_status == "onboard_pcb"
                    else "Gắn ngoài bo (Header/Breadboard)"
                ),
            }
        )

    body = {
        "wire_colors": wire_colors,
        "modules": modules_out,
        "wires": wires_out,
        "connectors": connectors_out,
        "firmware_pins": firmware_pins_out,
        "protection_components": protection_out,
    }
    canonical_bytes = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(canonical_bytes).hexdigest()

    hub_count = sum(1 for w in wires_out if w["is_hub_wire"])
    return {
        "schema_version": 1,
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
        f"{payload['counts']['connectors']} connectors -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
