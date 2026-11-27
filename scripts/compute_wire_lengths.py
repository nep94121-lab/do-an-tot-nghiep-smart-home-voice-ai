#!/usr/bin/env python3
"""Programmatic 3D Wire-Length Calculator & Route Generator (R3 SSOT).

Computes exact straight-line and routed 3D polyline lengths for all 40 physical
wires (`W01..W40`) directly from:
  1. Real KiCad PCB header pin coordinates (`hardware/wiring_contract.py` + `smarthome_hub.kicad_pcb`)
     transformed into the 3D-printed house world frame (`hardware/mica/mica_design.py` `HW_PCB`).
  2. Real off-board module mount coordinates (`hardware/mica/mica_design.py` `HARDWARE_PARTS`),
     synchronized 1:1 with 3D-print v2 (`hardware/in 3 d/`) and Blender (`scripts/build_smarthome_blender.py`).
  3. Real wall/base cable pass-through waypoints (`P05_WALL_FRONT`, `P06_WALL_MID`, `P09/P13`),
     vertical Dupont plug exit height (+14 mm), minimum bend radius (>= 8 mm fillet), and
     18% slack allowance (within required 15-20%).

Outputs:
  - `hardware/wire_lengths.json`           (canonical machine-readable routes & lengths)
  - `docs/phan_cung/wire_lengths.csv`      (spreadsheet CSV for all 40 wires)
  - `docs/phan_cung/WIRE_LIST_LENGTHS.md`  (Vietnamese + technical report + purchasing summary)
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
MICA_DIR = REPO_ROOT / "hardware" / "mica"
if str(MICA_DIR) not in sys.path:
    sys.path.insert(0, str(MICA_DIR))

from hardware.component_dimensions_ssot import COMPONENT_DIM_MAP  # noqa: E402
from hardware.wiring_contract import (  # noqa: E402
    HUB_CONNECTOR_MAP,
    WIRE_COLORS,
    WIRING_TABLE,
)
import mica_design as md  # noqa: E402

SLACK_FACTOR = 1.18  # +18% slack + bend allowance (within 15-20% requirement)
MAX_ALLOWED_CM = 30.0
DUPONT_EXIT_Z_MM = 14.0  # Vertical height above FR4 top where wire exits Dupont plug
PHOENIX_EXIT_Z_MM = 6.5  # Horizontal wire exit center for Phoenix MKDS 5.08mm terminal
FILLET_RADIUS_MM = 8.0   # Minimum bend radius for 22-26 AWG jumper/Dupont wires

# Printed house world frame (mm): X in [0..406], Y in [0..390], Z in [-3..147]
# Three.js / Blender tabletop frame (mm):
#   tx = house_x - 203.0
#   ty = house_z
#   tz = 235.0 - house_y   (front Tech Bay Y=10 -> tz=+225, rear wall Y=382 -> tz=-147)
# Note: we also output exact Blender scene coordinates matching SCENE_SPEC.json (`scale_mm_to_gltf = 0.025`).
HOUSE_TO_THREE_OFFSET_X = -203.0
HOUSE_TO_THREE_OFFSET_Y_INV = 235.0
SCALE_MM_TO_GLTF = 0.025


def house_mm_to_three_mm(pt: tuple[float, float, float]) -> tuple[float, float, float]:
    hx, hy, hz = pt
    return (round(hx + HOUSE_TO_THREE_OFFSET_X, 2), round(hz, 2), round(HOUSE_TO_THREE_OFFSET_Y_INV - hy, 2))


def house_mm_to_gltf(pt: tuple[float, float, float]) -> list[float]:
    tx, ty, tz = house_mm_to_three_mm(pt)
    return [round(tx * SCALE_MM_TO_GLTF, 4), round(ty * SCALE_MM_TO_GLTF, 4), round(tz * SCALE_MM_TO_GLTF, 4)]


def polyline_length_mm(pts: list[tuple[float, float, float]]) -> float:
    total = 0.0
    for a, b in zip(pts, pts[1:]):
        total += math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2)
    return total


def fillet_polyline(pts: list[tuple[float, float, float]], radius: float = FILLET_RADIUS_MM, subdiv: int = 3) -> list[tuple[float, float, float]]:
    """Apply smooth quadratic Bezier corner fillets honoring minimum wire bend radius."""
    if len(pts) <= 2:
        return list(pts)
    out: list[tuple[float, float, float]] = [pts[0]]
    for i in range(1, len(pts) - 1):
        p0, p1, p2 = pts[i - 1], pts[i], pts[i + 1]
        v1 = (p0[0] - p1[0], p0[1] - p1[1], p0[2] - p1[2])
        v2 = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
        l1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2 + v1[2] ** 2)
        l2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2 + v2[2] ** 2)
        if l1 < 1e-3 or l2 < 1e-3:
            out.append(p1)
            continue
        r = min(radius, l1 * 0.40, l2 * 0.40)
        a = (p1[0] + v1[0] * (r / l1), p1[1] + v1[1] * (r / l1), p1[2] + v1[2] * (r / l1))
        b = (p1[0] + v2[0] * (r / l2), p1[1] + v2[1] * (r / l2), p1[2] + v2[2] * (r / l2))
        for k in range(subdiv + 1):
            t = k / subdiv
            mt = 1.0 - t
            out.append((
                round(mt * mt * a[0] + 2 * mt * t * p1[0] + t * t * b[0], 2),
                round(mt * mt * a[1] + 2 * mt * t * p1[1] + t * t * b[1], 2),
                round(mt * mt * a[2] + 2 * mt * t * p1[2] + t * t * b[2], 2),
            ))
    out.append(pts[-1])
    return out


def pcb_pin_house_xyz(hub_ref: str, hub_pin: str, pcb_center: tuple[float, float, float]) -> tuple[float, float, float]:
    """Convert KiCad PCB local pin (origin top-left 0..100, 0..80) to house world mm.

    Note on PCB orientation on SUP06 / P16_PCB_PLATE:
      - PCB X runs left->right (+X): world_x = pcb_x0 + rel_x
      - KiCad local rel_y=0 is NORTH/REAR edge (J14/J4/J3/J13 facing house),
        rel_y=80 is SOUTH/FRONT edge (J10/J11/J12/J6 + NodeMCU Micro-USB facing P15 open cutaway):
        world_y = pcb_y0 + (80.0 - rel_y)
      - FR4 top surface sits at Z = pcb_z_bot + 1.6 = 19.0 + 1.6 = 20.6 mm.
    """
    conn = HUB_CONNECTOR_MAP[hub_ref]
    pcb_x0 = pcb_center[0] - 50.0
    pcb_y0 = pcb_center[1] - 40.0
    z_fr4_top = 20.6
    for pnum, rx, ry, _net in conn.pins:
        if pnum == hub_pin:
            wx = pcb_x0 + rx
            wy = pcb_y0 + (80.0 - ry)
            if conn.kind == "screw_508":
                return (round(wx - 4.6, 2), round(wy, 2), round(z_fr4_top + PHOENIX_EXIT_Z_MM, 2))
            return (round(wx, 2), round(wy, 2), round(z_fr4_top + DUPONT_EXIT_Z_MM, 2))
    raise KeyError(f"Unknown hub connector pin: {hub_ref}.{hub_pin}")


def get_module_pin_house_xyz(hw_map: dict[str, md.HardwarePartSpec], module_id: str, module_pin: str) -> tuple[float, float, float]:
    """Return exact 3D pin coordinate (house world mm) on each off-board module mount."""
    def C(pid: str) -> tuple[float, float, float]:
        return hw_map[pid].center_xyz

    if module_id == "psu_5v":
        cx, cy, cz = C("HW_DC_JACK")
        dz = 2.5 if "+" in module_pin else -2.5
        return (cx, cy + 10.5, cz + dz)
    if module_id == "sg90_servo":
        cx, cy, cz = C("HW_SG90")
        # Inverted coaxial top-jamb SG90: body X=60.1..82.9, Y=195.4..207.6, Z=107.4..129.9
        # 3-wire pigtail exits left end (X=59.5, Y=201.5, Z=124.0) with slight Y stagger
        dy = -1.27 if "PWM" in module_pin else (0.0 if "VCC" in module_pin else 1.27)
        return (round(cx - 12.0, 2), round(cy + dy, 2), round(cz + 5.35, 2))
    if module_id == "led_living":
        cx, cy, cz = C("HW_LED_LR")
        dz = 1.27 if "Anode" in module_pin else -1.27
        return (cx, cy, cz + dz)
    if module_id == "led_bedroom":
        cx, cy, cz = C("HW_LED_BR")
        dz = 1.27 if "Anode" in module_pin else -1.27
        return (cx, cy, cz + dz)
    if module_id == "relay1_pump":
        cx, cy, cz = C("HW_RELAY1")
        if "COM" in module_pin or "NO" in module_pin:
            dy = -2.54 if "COM" in module_pin else 2.54
            return (cx + 18.0, cy + dy, 21.0)
        dy = -2.54 if "VCC" in module_pin else (0.0 if "GND" in module_pin else 2.54)
        return (cx - 21.5, cy + dy, 16.0)
    if module_id == "pump_unit":
        cx, cy, cz = C("HW_PUMP")
        dy = -2.5 if "+" in module_pin else 2.5
        return (cx - 10.0, cy + dy, cz + 12.0)
    if module_id == "buzzer_alarm":
        cx, cy, cz = C("HW_BUZZER")
        dx = -3.8 if "+" in module_pin else 3.8
        return (cx + dx, cy + 3.0, cz)
    if module_id == "relay2_speaker":
        cx, cy, cz = C("HW_RELAY2")
        if "COM" in module_pin or "NO" in module_pin:
            dy = -2.54 if "COM" in module_pin else 2.54
            return (cx + 18.0, cy + dy, 21.0)
        dy = -2.54 if "DC+" in module_pin else (0.0 if "DC-" in module_pin else 2.54)
        return (cx - 21.5, cy + dy, 16.0)
    if module_id == "pam8403_amp":
        cx, cy, cz = C("HW_PAM8403")
        if "5V+" in module_pin:
            return (cx - 7.5, cy + 7.2, 8.0)
        if "5V-" in module_pin:
            return (cx - 4.5, cy + 7.2, 8.0)
        if "L (" in module_pin:
            return (cx - 7.0, cy - 7.2, 8.0)
        return (cx - 4.0, cy - 7.2, 8.0)
    if module_id == "speaker_mini":
        cx, cy, cz = C("HW_SPEAKER")
        dx = -4.0 if "+" in module_pin else 4.0
        return (cx + dx, cy + 3.0, cz)
    if module_id == "dht11_sensor":
        cx, cy, cz = C("HW_DHT11")
        dy = -2.54 if "VCC" in module_pin else (0.0 if "DATA" in module_pin else 2.54)
        return (cx, cy + dy, cz - 12.0)
    if module_id == "soil_lm393":
        cx, cy, cz = C("HW_LM393")
        dx = -2.54 if "VCC" in module_pin else (0.0 if "GND" in module_pin else 2.54)
        return (cx + dx, cy, cz + 6.0)
    if module_id == "soil_probe":
        cx, cy, cz = C("HW_SOIL_PROBE")
        dy = -1.27 if "A" in module_pin else 1.27
        return (cx, cy + dy, cz + 22.0)
    if module_id == "ky037_sound":
        cx, cy, cz = C("HW_KY037")
        dx = -2.54 if "+" in module_pin else (0.0 if "G (" in module_pin else 2.54)
        return (cx + dx, cy + 3.5, cz)
    raise KeyError(f"Unknown module_id: {module_id}")


def build_routed_waypoints(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    hub_ref: str,
    module_id: str,
    hw_map: dict[str, md.HardwarePartSpec],
) -> tuple[list[tuple[float, float, float]], str]:
    """Compute realistic obstacle-avoiding 3D waypoints through actual cable channels/holes."""
    pcb_c = hw_map["HW_PCB"].center_xyz
    # Nominal tech-bay floor cable tray elevation (between P01A top Z=0 and P16 bottom Z=6, or above deck at Z=24)
    sx, sy, sz = start
    ex, ey, ez = end

    if hub_ref == "PAM8403" and module_id == "speaker_mini":
        # Direct short pair from PAM8403 front edge to Speaker behind P15_TECH_FASCIA
        return [start, (sx, (sy + ey) / 2.0, 14.0), end], "Tech Bay front channel (PAM8403 -> P15 Speaker)"

    if hub_ref == "LM393" and module_id == "soil_probe":
        # Over P13 rear garden wall rim (Z=56) directly into YL-69 probe top (Z=54)
        return [start, (sx, sy - 6.0, 56.0), (ex, ey, 58.0), end], "Garden rim channel (LM393 -> YL-69 Probe)"

    if module_id == "psu_5v":
        # J1 left terminal -> front-left tray -> DC-022 rear terminals
        return [start, (sx - 12.0, sy, sz), (ex + 8.0, ey + 18.0, 22.0), end], "Tech Bay left power channel (J1 -> DC-022)"

    if module_id == "sg90_servo":
        # J3 top header -> climb Tech Bay -> through P05 Cable_Servo_D1 (X=48, Y=192..195, Z=110, Dia 10mm)
        # passing upper-left of hole (Z=112.5..113.0, strictly clearing P07_SERVO_SHELF top Z=111.5) -> SG90 left exit (59.5, 201.5, 124.0)
        off = round(ey - 201.5, 2)
        return [
            start,
            (92.0 + off, 168.0, 56.0),
            (47.2 + off, 188.0, 112.5),
            (47.2 + off, 196.5, 113.0),
            end,
        ], "Tech Bay -> P05 Cable_Servo_D1 (X=48, Z=110) -> Coaxial top-jamb SG90"

    if module_id in ("led_living", "dht11_sensor"):
        # Route from PCB north edge -> cleanly over P05 open front cutaway above KY037_Ledge (H=48mm, X=148..188) -> P06_WALL_MID Living Room face
        if ey > 320.0:
            return [start, (182.0, 175.0, 56.0), (182.0, 198.0, 56.0), (ex, ey - 10.0, 24.0), end], "P05 open cutaway -> P02 rear wall"
        return [
            start,
            (min(max(sx + 20.0, 152.0), 184.0), 178.0, 54.0),
            (184.0, 196.0, 56.0),
            (194.0, min(ey, 240.0), max(68.0, ez - 18.0)),
            end,
        ], "P05 open front cutaway (Z=56 above KY037 ledge) -> P06_WALL_MID Living Room chase"

    if module_id == "led_bedroom":
        # Route through P05 Cable_Front_BR (X=224, Y=192, Z=17) -> climb P06_WALL_MID Bedroom face
        if ey > 320.0:
            return [start, (224.0, 175.0, 22.0), (224.0, 196.0, 18.0), (ex, ey - 10.0, 18.0), end], "P05 Cable_Front_BR -> floor -> P02 rear wall"
        return [
            start,
            (min(max(sx + 25.0, 175.0), 224.0), 178.0, 26.0),
            (224.0, 195.0, 18.0),
            (204.0, min(ey, 240.0), 48.0),
            end,
        ], "P05 Cable_Front_BR (X=224) -> P06_WALL_MID Bedroom vertical chase"

    if module_id == "buzzer_alarm":
        # J6 bottom-right -> right side of PCB -> up center pillar P05 to Buzzer at Z=126
        return [start, (sx + 10.0, sy + 12.0, 28.0), (ex, 182.0, 32.0), (ex, 190.0, ez - 6.0), end], "Tech Bay -> P05 center pillar vertical chase -> Buzzer"

    if module_id == "ky037_sound":
        # J15 right edge -> straight north into P05 KY-037 rear
        return [start, (sx + 6.0, 172.0, 28.0), (ex, 186.0, ez), end], "Tech Bay -> P05 front wall KY-037 cradle"

    if module_id in ("relay1_pump", "relay2_speaker"):
        # Short direct tech-bay jumpers between PCB right/bottom headers and Relay 1/2 caddies
        mid_x = (sx + ex) / 2.0
        mid_y = (sy + ey) / 2.0
        arch_z = max(sz, ez) + 6.0
        return [start, (mid_x, mid_y, arch_z), end], "Tech Bay direct inter-board harness"

    if module_id == "pam8403_amp":
        # J11/J12 bottom edge -> front tech-bay floor tray -> PAM8403 tray
        return [start, (sx, sy - 14.0, 22.0), (ex - 12.0, ey, 14.0), end], "Tech Bay front audio/power tray (J11/J12 -> PAM8403)"

    if module_id == "pump_unit":
        # J2 left terminal -> across tech bay channel -> over P09_GARDEN_LEFT wire notch (X=266, Y=99, Z=50) -> pump
        return [start, (186.0, 114.0, 26.0), (266.0, 99.0, 52.0), end], "Tech Bay center channel -> P09 water tank wire notch (Y=99) -> Pump"

    if module_id == "soil_lm393":
        # J14 top-left -> along north tray (Y=160) -> straight across to dry rear P13 LM393 cradle
        if ey >= 140.0:
            return [start, (sx, 158.0, 28.0), (ex, 158.0, 28.0), end], "Tech Bay rear dry tray -> P13 dry rear LM393 cradle"
        return [start, (sx, 162.0, 28.0), (256.0, 162.0, 28.0), (256.0, 20.0, 24.0), end], "Tech Bay perimeter -> P12 front garden wall -> LM393"

    return [start, ((sx + ex) / 2.0, (sy + ey) / 2.0, max(sz, ez) + 8.0), end], "Direct routed path"


def recommend_standard_cm(length_with_slack_cm: float, module_id: str, wire_type: str) -> tuple[int, str]:
    """Recommend purchasable standard wire length (10 / 20 / 30 cm) + pigtail/type note."""
    if module_id == "sg90_servo":
        return (20 if length_with_slack_cm <= 20.0 else 30, "Dây đuôi SG90 sẵn 25 cm (nối thẳng J3, không cần nối dài)" if length_with_slack_cm <= 25.0 else "Dupont 30 cm nối dài SG90")
    if module_id == "pump_unit":
        return (30 if length_with_slack_cm > 20.0 else 20, "Dây 22AWG 30 cm (hoặc nối dài dây bơm 20 cm vào cầu vít J2)" if length_with_slack_cm > 20.0 else "Dây đuôi bơm sẵn 20 cm vào cầu vít J2")
    if length_with_slack_cm <= 10.0:
        return (10, "Dây tiêu chuẩn 10 cm")
    if length_with_slack_cm <= 20.0:
        return (20, "Dây tiêu chuẩn 20 cm")
    if length_with_slack_cm <= 30.0:
        return (30, "Dây tiêu chuẩn 30 cm")
    return (40, "VƯỢT 30 CM — CẦN DỊCH PCB HOẶC GIÁ ĐỠ!")


def compute_all_wires() -> dict[str, Any]:
    hw_map = {h.part_id: h for h in md.HARDWARE_PARTS}
    pcb_center = hw_map["HW_PCB"].center_xyz
    pam_c = hw_map["HW_PAM8403"].center_xyz
    lm_c = hw_map["HW_LM393"].center_xyz

    rows: list[dict[str, Any]] = []
    flagged: list[str] = []

    for w in WIRING_TABLE:
        if w.hub_ref in HUB_CONNECTOR_MAP:
            start_xyz = pcb_pin_house_xyz(w.hub_ref, w.hub_pin, pcb_center)
            hub_edge = HUB_CONNECTOR_MAP[w.hub_ref].edge
        elif w.hub_ref == "PAM8403":
            dx = 4.5 if "+" in w.hub_pin else 7.5
            start_xyz = (round(pam_c[0] + dx, 2), round(pam_c[1] - 7.2, 2), 8.0)
            hub_edge = "offboard_pam8403"
        elif w.hub_ref == "LM393":
            dx = -1.27 if w.hub_pin == "P1" else 1.27
            start_xyz = (round(lm_c[0] + dx, 2), round(lm_c[1] - 5.0, 2), round(lm_c[2] + 6.0, 2))
            hub_edge = "offboard_lm393"
        else:
            raise KeyError(f"Unhandled hub_ref {w.hub_ref}")

        end_xyz = get_module_pin_house_xyz(hw_map, w.module_id, w.module_pin)
        raw_pts, channel_note = build_routed_waypoints(start_xyz, end_xyz, w.hub_ref, w.module_id, hw_map)
        smooth_pts = fillet_polyline(raw_pts, radius=FILLET_RADIUS_MM, subdiv=3)

        straight_mm = polyline_length_mm([start_xyz, end_xyz])
        routed_mm = polyline_length_mm(smooth_pts)
        slack_mm = routed_mm * SLACK_FACTOR

        straight_cm = round(straight_mm / 10.0, 2)
        routed_cm = round(routed_mm / 10.0, 2)
        length_cm = round(slack_mm / 10.0, 2)
        std_cm, std_note_vi = recommend_standard_cm(length_cm, w.module_id, w.wire_type)
        within_30 = length_cm <= MAX_ALLOWED_CM
        if not within_30:
            flagged.append(f"{w.wire_id} ({w.hub_ref}.{w.hub_pin}->{w.module_id}:{length_cm}cm)")

        rows.append({
            "wire_id": w.wire_id,
            "group": w.group,
            "hub_ref": w.hub_ref,
            "hub_pin": w.hub_pin,
            "hub_label": w.hub_label,
            "hub_edge": hub_edge,
            "module_id": w.module_id,
            "module_name": w.module_name,
            "module_pin": w.module_pin,
            "signal": w.net,
            "nodemcu_pin": w.nodemcu_pin,
            "gpio": w.gpio,
            "color": w.color,
            "color_hex": WIRE_COLORS[w.color]["hex"],
            "connector_type": w.wire_type,
            "start_house_mm": list(start_xyz),
            "end_house_mm": list(end_xyz),
            "waypoints_house_mm": [list(p) for p in raw_pts],
            "smooth_waypoints_house_mm": [list(p) for p in smooth_pts],
            "waypoints_threejs": [house_mm_to_gltf(p) for p in smooth_pts],
            "straight_cm": straight_cm,
            "routed_cm": routed_cm,
            "slack_pct": int(round((SLACK_FACTOR - 1.0) * 100)),
            "length_cm": length_cm,
            "recommended_std_cm": std_cm,
            "recommended_note_vi": std_note_vi,
            "within_30cm": within_30,
            "route_channel": channel_note,
        })

    lengths = [r["length_cm"] for r in rows]
    sg90_lengths = [r["length_cm"] for r in rows if r["module_id"] == "sg90_servo"]
    sg90_within_25 = bool(sg90_lengths) and all(0.0 < v <= 25.0 for v in sg90_lengths)
    buy_counts = collections.Counter((r["recommended_std_cm"], r["connector_type"]) for r in rows)
    std_totals = collections.Counter(r["recommended_std_cm"] for r in rows)

    return {
        "schema_version": "1.1",
        "slack_factor": SLACK_FACTOR,
        "max_allowed_cm": MAX_ALLOWED_CM,
        "sg90_pigtail_limit_cm": 25.0,
        "sg90_max_length_cm": max(sg90_lengths) if sg90_lengths else 0.0,
        "sg90_within_25cm": sg90_within_25,
        "pcb_center_house_mm": list(pcb_center),
        "total_wires": len(rows),
        "min_length_cm": min(lengths),
        "max_length_cm": max(lengths),
        "total_length_cm": round(sum(lengths), 2),
        "total_standard_cm": sum(r["recommended_std_cm"] for r in rows),
        "all_within_30cm": len(flagged) == 0,
        "flagged_over_30cm": flagged,
        "counts_by_standard_cm": {str(k): v for k, v in sorted(std_totals.items())},
        "purchasing_groups": [
            {"std_cm": k[0], "connector_type": k[1], "qty": v}
            for k, v in sorted(buy_counts.items())
        ],
        "wires": rows,
    }


def write_outputs(data: dict[str, Any]) -> None:
    json_path = REPO_ROOT / "hardware" / "wire_lengths.json"
    csv_path = REPO_ROOT / "docs" / "phan_cung" / "wire_lengths.csv"
    md_path = REPO_ROOT / "docs" / "phan_cung" / "WIRE_LIST_LENGTHS.md"

    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "Wire_ID", "Group", "PCB_Header_Pin", "Module", "Module_Pin",
            "Signal_Net", "Color", "Connector_Type",
            "Straight_cm", "Routed_cm", "Length_Incl_18pct_Slack_cm",
            "Recommended_Std_cm", "Within_30cm", "Route_Channel",
        ])
        for r in data["wires"]:
            w.writerow([
                r["wire_id"], r["group"], f"{r['hub_ref']}.{r['hub_pin']}",
                r["module_name"], r["module_pin"], r["signal"], r["color"],
                r["connector_type"], f"{r['straight_cm']:.2f}", f"{r['routed_cm']:.2f}",
                f"{r['length_cm']:.2f}", r["recommended_std_cm"],
                "PASS" if r["within_30cm"] else "OVER_30CM", r["route_channel"],
            ])

    lines = [
        "# Danh Sách 40 Dây Nối & Chiều Dài Thực Tế 3D (PCB Trực Tiếp — Không Breadboard)",
        "",
        "> **Nguồn tính tự động:** `scripts/compute_wire_lengths.py` tính từ tọa độ chân thực trên `smarthome_hub.kicad_pcb` (`J1–J15`) và vị trí giá đỡ module thực trong nhà in 3D v2 (`hardware/mica/mica_design.py` + `hardware/in 3 d/`), đã cộng **+18% độ chùng & bán kính uốn `R >= 8 mm`**.",
        "",
        f"- **Tổng số dây:** **{data['total_wires']} dây** (36 dây từ PCB Hub `J1–J15` + 4 dây nối giữa module `PAM8403→Loa` và `LM393→Đầu dò đất`).",
        f"- **Chiều dài tính toán (đã cộng 18% độ chùng):** Ngắn nhất **`{data['min_length_cm']:.2f} cm`**, Dài nhất **`{data['max_length_cm']:.2f} cm`**, Tổng cộng **`{data['total_length_cm']:.2f} cm`** (`{data['total_length_cm']/100:.2f} m`).",
        f"- **Kiểm tra giới hạn dây Dupont chuẩn `<= 30 cm`:** **{'ĐẠT 40/40 (0 dây vượt 30 cm)' if data['all_within_30cm'] else 'CẢNH BÁO: ' + ', '.join(data['flagged_over_30cm'])}**.",
        "",
        "## 1. Bảng Chi Tiết 40 Dây Nối & Chiều Dài (cm)",
        "",
        "| ID | Đầu PCB (`J#`) | Mô-đun & Chân | Tín hiệu | Màu | Loại đầu nối | Thẳng (cm) | Đi dây 3D (cm) | Kèm 18% chùng (cm) | Mua chuẩn (cm) | Đạt <=30cm |",
        "| :---: | :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | :---: |",
    ]
    for r in data["wires"]:
        ok_s = "PASS" if r["within_30cm"] else "**FAIL**"
        lines.append(
            f"| `{r['wire_id']}` | `{r['hub_ref']}.{r['hub_pin']}` | {r['module_name']} (`{r['module_pin']}`) | `{r['signal']}` | {r['color']} | {r['connector_type']} | "
            f"{r['straight_cm']:.2f} | {r['routed_cm']:.2f} | **{r['length_cm']:.2f}** | **{r['recommended_std_cm']} cm** | {ok_s} |"
        )

    lines.extend([
        "",
        "## 2. Tổng Hợp Mua Dây Theo Cỡ Tiêu Chuẩn (`10 / 20 / 30 cm`)",
        "",
        "| Cỡ dây chuẩn | Loại đầu nối | Số sợi cần | Ghi chú mua sắm |",
        "| :---: | :--- | ---: | :--- |",
    ])
    for grp in data["purchasing_groups"]:
        lines.append(f"| **{grp['std_cm']} cm** | {grp['connector_type']} | **{grp['qty']}** | Mua theo bó 10/20/40 sợi cùng cỡ |")
    lines.append("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--strict", action="store_true", help="Exit non-zero if any wire exceeds 30 cm")
    args = ap.parse_args()
    data = compute_all_wires()
    if not args.dry_run:
        write_outputs(data)
    print(json.dumps({
        "total_wires": data["total_wires"],
        "min_length_cm": data["min_length_cm"],
        "max_length_cm": data["max_length_cm"],
        "sg90_max_length_cm": data["sg90_max_length_cm"],
        "sg90_within_25cm": data["sg90_within_25cm"],
        "total_length_cm": data["total_length_cm"],
        "all_within_30cm": data["all_within_30cm"],
        "flagged_over_30cm": data["flagged_over_30cm"],
        "counts_by_standard_cm": data["counts_by_standard_cm"],
    }, indent=2))
    if args.strict and (not data["all_within_30cm"] or not data["sg90_within_25cm"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
