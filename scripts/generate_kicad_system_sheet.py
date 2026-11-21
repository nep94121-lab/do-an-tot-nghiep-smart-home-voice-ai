#!/usr/bin/env python3
"""Deterministic KiCad 10 System Plug-In Wiring Schematic Generator.

Reads Single Source of Truth `hardware/wiring_contract.py` and:
1. Generates `hardware/kicad/smarthome_hub/system_wiring.kicad_sch` (KiCad 10,
   version 20251024, paper A2 landscape) showing the Central Hub PCB (Type 1)
   connected via real orthogonal color-coded KiCad wires to EVERY off-board
   module (NodeMCU v2 Amica on U1/U2, 5V 2A PSU, SG90 Servo, 2x 5mm LEDs,
   Relay 1 Blue 5V, Mini Submersible Pump, Active 5V Buzzer, Relay 2 Red Opto
   5V Jmp=H, PAM8403 Audio Amp, Mini Speaker 28mm 8Ohm, DHT11, Soil LM393,
   YL-69 Soil Fork Probe, KY-037/038 Sound Module).
2. All off-board & system-view symbols carry `(on_board no)` and `(in_bom no)`
   so the 100x80mm 1-Layer DIY Hub PCB and `bom.csv` remain 100% untouched.
3. Links `system_wiring.kicad_sch` cleanly and idempotently as a hierarchical
   sub-sheet (Page 2) inside `hardware/kicad/smarthome_hub/smarthome_hub.kicad_sch`.

Zero fan, zero AC, zero IR anywhere.
"""

from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from hardware.wiring_contract import (  # noqa: E402
    FIRMWARE_PIN_CONTRACT,
    HUB_CONNECTOR_MAP,
    HUB_CONNECTORS,
    MODULE_DIMENSIONS_MM,
    WIRE_COLORS,
    WIRING_TABLE,
    WireEntry,
)

KICAD_DIR = ROOT_DIR / "hardware" / "kicad" / "smarthome_hub"
ROOT_SCH_PATH = KICAD_DIR / "smarthome_hub.kicad_sch"
SYS_SCH_PATH = KICAD_DIR / "system_wiring.kicad_sch"
SYS_SYM_LIB_PATH = KICAD_DIR / "SystemWiring.kicad_sym"
SYM_LIB_TABLE_PATH = KICAD_DIR / "sym-lib-table"

PROJECT_NAME = "smarthome_hub"
ROOT_SHEET_UUID = "20f08b23-d419-582e-a433-7afe7edbad64"
NAMESPACE = uuid.UUID("c5f7d92e-7b2a-4c31-9e12-8b9a3d4e1f00")
SUBSHEET_BLOCK_UUID = str(uuid.uuid5(NAMESPACE, "sheet:system_wiring"))
SUBSHEET_FILE_UUID = str(uuid.uuid5(NAMESPACE, "file:system_wiring.kicad_sch"))
SUBSHEET_INSTANCE_PATH = f"/{ROOT_SHEET_UUID}/{SUBSHEET_BLOCK_UUID}"

# High-contrast print-safe RGB tuples for KiCad wire strokes (white background)
WIRE_COLOR_META: dict[str, tuple[str, tuple[int, int, int]]] = {
    "Red":    ("RED", (210, 32, 32)),
    "Black":  ("BLK", (28, 28, 34)),
    "Orange": ("ORG", (220, 92, 12)),
    "Yellow": ("YEL", (184, 130, 0)),
    "Green":  ("GRN", (22, 148, 64)),
    "Blue":   ("BLU", (30, 96, 215)),
    "Cyan":   ("CYN", (8, 138, 168)),
    "Purple": ("PRP", (138, 42, 210)),
    "White":  ("WHT", (105, 118, 136)),
    "Brown":  ("BRN", (126, 62, 24)),
}


def det_uuid(key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, key))


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def fmt(v: float) -> str:
    return f"{v:.2f}"


# ---------------------------------------------------------------------------
# Symbol Library Builder (embedded custom off-board symbols, all on_board=no, in_bom=no)
# ---------------------------------------------------------------------------
def build_custom_lib_symbol(
    lib_id: str,
    ref_prefix: str,
    width: float,
    height: float,
    pins: list[dict],
    *,
    fill_rgb: tuple[int, int, int, float] = (250, 250, 244, 1.0),
    stroke_rgb: tuple[int, int, int] = (40, 72, 120),
    pin_len: float = 5.08,
    extra_graphics: list[str] | None = None,
    pin_font_size: float = 1.27,
) -> str:
    """Create a KiCad 10 lib_symbol centered at (0, 0).

    Reminder of KiCad coordinates:
    - Inside lib_symbols, +Y is UP.
    - When placed on sheet at (sx, sy, 0), local (lx, ly) maps to (sx + lx, sy - ly).
    - Pin dict keys:
        num: unique pin number string (e.g. "1")
        name: visible pin label inside body
        side: "left" or "right"
        sy_offset: offset from symbol center in SHEET Y coordinates (+down).
                   Converted internally to lib_y = -sy_offset!
    """
    short_name = lib_id.split(":", 1)[1]
    hw = width / 2.0
    hh = height / 2.0
    r, g, b, a = fill_rgb
    sr, sg, sb = stroke_rgb

    lines: list[str] = [
        f'\t\t(symbol "{esc(lib_id)}"',
        "\t\t\t(pin_numbers",
        "\t\t\t\t(hide yes)",
        "\t\t\t)",
        "\t\t\t(pin_names",
        "\t\t\t\t(offset 1.27)",
        "\t\t\t)",
        "\t\t\t(exclude_from_sim yes)",
        "\t\t\t(in_bom no)",
        "\t\t\t(on_board no)",
        "\t\t\t(in_pos_files no)",
        "\t\t\t(duplicate_pin_numbers_are_jumpers no)",
        f'\t\t\t(property "Reference" "{esc(ref_prefix)}"',
        f"\t\t\t\t(at 0 {fmt(hh + 2.54)} 0)",
        "\t\t\t\t(effects (font (size 1.524 1.524) (bold yes)))",
        "\t\t\t)",
        f'\t\t\t(property "Value" "{esc(short_name)}"',
        f"\t\t\t\t(at 0 {fmt(-(hh + 2.54))} 0)",
        "\t\t\t\t(effects (font (size 1.27 1.27)))",
        "\t\t\t)",
        '\t\t\t(property "Footprint" ""',
        "\t\t\t\t(at 0 0 0)",
        "\t\t\t\t(effects (font (size 1.27 1.27)) (hide yes))",
        "\t\t\t)",
        '\t\t\t(property "Datasheet" ""',
        "\t\t\t\t(at 0 0 0)",
        "\t\t\t\t(effects (font (size 1.27 1.27)) (hide yes))",
        "\t\t\t)",
        '\t\t\t(property "Description" "Off-board system wiring module (not on PCB / not in BOM)"',
        "\t\t\t\t(at 0 0 0)",
        "\t\t\t\t(effects (font (size 1.27 1.27)) (hide yes))",
        "\t\t\t)",
        f'\t\t\t(symbol "{esc(short_name)}_0_1"',
        "\t\t\t\t(rectangle",
        f"\t\t\t\t\t(start {fmt(-hw)} {fmt(hh)})",
        f"\t\t\t\t\t(end {fmt(hw)} {fmt(-hh)})",
        f"\t\t\t\t\t(stroke (width 0.35) (type default) (color {sr} {sg} {sb} 1))",
        f"\t\t\t\t\t(fill (type color) (color {r} {g} {b} {a}))",
        "\t\t\t\t)",
    ]
    if extra_graphics:
        for g_item in extra_graphics:
            lines.append(g_item)
    lines.append("\t\t\t)")

    lines.append(f'\t\t\t(symbol "{esc(short_name)}_1_1"')
    for p in pins:
        ly = -p["sy_offset"]
        if p["side"] == "left":
            lx = -(hw + pin_len)
            angle = 0
        elif p["side"] == "right":
            lx = hw + pin_len
            angle = 180
        else:
            raise ValueError(f"Unsupported pin side: {p['side']}")
        pname = re.sub(r"\s+", " ", p["name"].strip())
        pname = pname.replace(" (", "(").replace(" +", "+").replace(" -", "-").replace(" ", "_")
        lines.extend([
            f"\t\t\t\t(pin passive line (at {fmt(lx)} {fmt(ly)} {angle}) (length {fmt(pin_len)})",
            f'\t\t\t\t\t(name "{esc(pname)}" (effects (font (size {fmt(pin_font_size)} {fmt(pin_font_size)}))))',
            f'\t\t\t\t\t(number "{esc(p["num"])}" (effects (font (size 1.016 1.016))))',
            "\t\t\t\t)",
        ])
    lines.append("\t\t\t)")
    lines.append("\t\t)")
    return "\n".join(lines)


def build_symbol_instance(
    lib_id: str,
    ref: str,
    value: str,
    desc: str,
    cx: float,
    cy: float,
    width: float,
    height: float,
    pins: list[dict],
    *,
    ref_pos: tuple[float, float] | None = None,
    val_pos: tuple[float, float] | None = None,
) -> str:
    hh = height / 2.0
    rx, ry = ref_pos if ref_pos else (cx, cy - hh - 2.20)
    vx, vy = val_pos if val_pos else (cx, cy + hh + 2.20)
    sym_uuid = det_uuid(f"sym:{ref}")

    lines = [
        f'\t(symbol (lib_id "{esc(lib_id)}") (at {fmt(cx)} {fmt(cy)} 0) (unit 1)',
        "\t\t(exclude_from_sim yes) (in_bom no) (on_board no) (dnp no)",
        f'\t\t(uuid "{sym_uuid}")',
        f'\t\t(property "Reference" "{esc(ref)}" (at {fmt(rx)} {fmt(ry)} 0)',
        "\t\t\t(effects (font (size 1.65 1.65) (bold yes)))",
        "\t\t)",
        f'\t\t(property "Value" "{esc(value)}" (at {fmt(vx)} {fmt(vy)} 0)',
        "\t\t\t(effects (font (size 1.35 1.35) (bold yes)))",
        "\t\t)",
        f'\t\t(property "Footprint" "" (at {fmt(cx)} {fmt(cy)} 0)',
        "\t\t\t(effects (font (size 1.27 1.27)) (hide yes))",
        "\t\t)",
        f'\t\t(property "Datasheet" "" (at {fmt(cx)} {fmt(cy)} 0)',
        "\t\t\t(effects (font (size 1.27 1.27)) (hide yes))",
        "\t\t)",
        f'\t\t(property "Description" "{esc(desc)}" (at {fmt(cx)} {fmt(cy)} 0)',
        "\t\t\t(effects (font (size 1.27 1.27)) (hide yes))",
        "\t\t)",
    ]
    for p in pins:
        pu = det_uuid(f"pin:{ref}:{p['num']}")
        lines.append(f'\t\t(pin "{esc(p["num"])}" (uuid "{pu}"))')
    lines.extend([
        "\t\t(instances",
        f'\t\t\t(project "{PROJECT_NAME}"',
        f'\t\t\t\t(path "{SUBSHEET_INSTANCE_PATH}" (reference "{esc(ref)}") (unit 1))',
        "\t\t\t)",
        "\t\t)",
        "\t)",
    ])
    return "\n".join(lines)


def kicad_wire(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color_name: str,
    key: str,
    width: float = 0.40,
) -> str:
    _, (r, g, b) = WIRE_COLOR_META[color_name]
    return "\n".join([
        f"\t(wire (pts (xy {fmt(x1)} {fmt(y1)}) (xy {fmt(x2)} {fmt(y2)}))",
        f"\t\t(stroke (width {fmt(width)}) (type solid) (color {r} {g} {b} 1))",
        f'\t\t(uuid "{det_uuid(key)}")',
        "\t)",
    ])


def kicad_label(
    name: str,
    x: float,
    y: float,
    key: str,
    *,
    angle: int = 0,
    justify: str = "left bottom",
    size: float = 1.22,
) -> str:
    return "\n".join([
        f'\t(label "{esc(name)}" (at {fmt(x)} {fmt(y)} {angle})',
        f"\t\t(effects (font (size {fmt(size)} {fmt(size)})) (justify {justify}))",
        f'\t\t(uuid "{det_uuid(key)}")',
        "\t)",
    ])


def kicad_text(
    text: str,
    x: float,
    y: float,
    key: str,
    *,
    size: float = 1.15,
    bold: bool = False,
    justify: str = "left",
    color: tuple[int, int, int] | None = None,
) -> str:
    bold_s = " (bold yes)" if bold else ""
    color_s = f" (color {color[0]} {color[1]} {color[2]} 1)" if color else ""
    # In KiCad S-expr, centered text omits (justify ...); "center" is invalid!
    just_s = "" if justify == "center" else f" (justify {justify})"
    return "\n".join([
        f'\t(text "{esc(text)}" (exclude_from_sim yes) (at {fmt(x)} {fmt(y)} 0)',
        f"\t\t(effects (font (size {fmt(size)} {fmt(size)}){bold_s}{color_s}){just_s})",
        f'\t\t(uuid "{det_uuid(key)}")',
        "\t)",
    ])


def kicad_rect(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    key: str,
    *,
    stroke_w: float = 0.25,
    stroke_type: str = "dash",
    stroke_rgb: tuple[int, int, int] = (45, 95, 165),
    fill_rgba: tuple[int, int, int, float] | None = None,
) -> str:
    sr, sg, sb = stroke_rgb
    fill_line = (
        f"\t\t(fill (type color) (color {fill_rgba[0]} {fill_rgba[1]} {fill_rgba[2]} {fill_rgba[3]}))"
        if fill_rgba
        else "\t\t(fill (type none))"
    )
    return "\n".join([
        f"\t(rectangle (start {fmt(x1)} {fmt(y1)}) (end {fmt(x2)} {fmt(y2)})",
        f"\t\t(stroke (width {fmt(stroke_w)}) (type {stroke_type}) (color {sr} {sg} {sb} 1))",
        fill_line,
        f'\t\t(uuid "{det_uuid(key)}")',
        "\t)",
    ])


def kicad_no_connect(x: float, y: float, key: str) -> str:
    return f'\t(no_connect (at {fmt(x)} {fmt(y)}) (uuid "{det_uuid(key)}"))'


def wire_lookup() -> dict[tuple[str, str], WireEntry]:
    """Index WIRING_TABLE by (hub_ref, hub_pin) for SSOT lookup."""
    return {(w.hub_ref, w.hub_pin): w for w in WIRING_TABLE}


# ---------------------------------------------------------------------------
# Main System Wiring Schematic Assembly (A2 Landscape: 594 x 420 mm)
# ---------------------------------------------------------------------------
def generate_system_wiring_sch() -> str:
    wmap = wire_lookup()
    # Sanity check SSOT integrity
    assert len(HUB_CONNECTORS) == 15, f"Expected 15 connectors, got {len(HUB_CONNECTORS)}"
    assert len(WIRING_TABLE) == 40, f"Expected 40 wires (W01..W40), got {len(WIRING_TABLE)}"
    assert len(FIRMWARE_PIN_CONTRACT) == 10, f"Expected 10 active firmware pins"

    # -----------------------------------------------------------------------
    # Master Geometry Constants (all snapped to 2.54 mm KiCad grid!)
    # A2 Landscape: 594 x 420 mm (border margin ~10mm -> usable 15.24..579.12 x 15.24..403.86)
    # -----------------------------------------------------------------------
    PIN_LEN = 5.08

    # Central Hub PCB Spine (HUB1)
    HUB_CX = 297.18
    HUB_CY = 193.04
    HUB_W = 86.36   # body x: 254.00 .. 340.36
    HUB_H = 325.12  # body y: 30.48 .. 355.60
    HUB_LEFT_PIN_X = HUB_CX - HUB_W / 2.0 - PIN_LEN   # 248.92
    HUB_RIGHT_PIN_X = HUB_CX + HUB_W / 2.0 + PIN_LEN  # 345.44

    # Primary Left Column (MCU1, PSU1, DHT1, SOIL1, MIC1, RLY1, PMP1)
    L1_W = 53.34
    L1_CX = 157.48  # body x: 130.81 .. 184.15 -> let's keep body edges on 2.54mm grid!
    # With L1_W = 55.88 (22 grid units), L1_CX = 157.48 -> body x: 129.54 .. 185.42,
    # right pin tip = 185.42 + 5.08 = 190.50 (exact 2.54mm multiple: 75 * 2.54),
    # left pin tip = 129.54 - 5.08 = 124.46 (exact 2.54mm multiple: 49 * 2.54)!
    L1_W = 55.88
    L1_CX = 157.48
    L1_RIGHT_PIN_X = L1_CX + L1_W / 2.0 + PIN_LEN  # 190.50
    L1_LEFT_PIN_X = L1_CX - L1_W / 2.0 - PIN_LEN   # 124.46

    # Secondary Far-Left Module (PRB1: YL-69 Soil Fork Probe)
    L2_W = 45.72   # 18 grid units
    L2_CX = 53.34  # body x: 30.48 .. 76.20, right pin tip = 81.28
    L2_RIGHT_PIN_X = L2_CX + L2_W / 2.0 + PIN_LEN  # 81.28

    # Primary Right Column (SRV1, LED1, LED2, BUZ1, RLY2, AMP1)
    R1_W = 55.88
    R1_CX = 436.88  # body x: 408.94 .. 464.82, left pin tip = 403.86, right pin tip = 469.90
    R1_LEFT_PIN_X = R1_CX - R1_W / 2.0 - PIN_LEN   # 403.86
    R1_RIGHT_PIN_X = R1_CX + R1_W / 2.0 + PIN_LEN  # 469.90

    # Secondary Far-Right Module (SPK1: Mini Speaker 28mm 8Ohm)
    R2_W = 45.72
    R2_CX = 541.02  # body x: 518.16 .. 563.88, left pin tip = 513.08
    R2_LEFT_PIN_X = R2_CX - R2_W / 2.0 - PIN_LEN   # 513.08

    # -----------------------------------------------------------------------
    # Define every Hub pin and its Y coordinate (all exact multiples of 2.54mm)
    # -----------------------------------------------------------------------
    # NodeMCU v2 Amica mounted on U1/U2 (13 active pins, top-left of HUB1)
    MCU_PINS_SPEC = [
        # (sheet_y, mcu_label, hub_label, net, color, tag)
        (43.18, "A0/ADC0(U1.1)",          "U1.1:A0_SOIL",         "A0_SOIL",      "Green",  "MCU-A0"),
        (48.26, "VIN/+5V(U1.15)",         "U1.15:+5V(VIN)",       "+5V",          "Red",    "MCU-5V"),
        (53.34, "3V3(U1.11/U2.6)",        "U1.11:+3V3_OUT",       "+3V3",         "Red",    "MCU-3V3"),
        (58.42, "GND(U1.10/14,U2.7/14)",  "U1.14:GND",            "GND",          "Black",  "MCU-GND"),
        (63.50, "D0/GPIO16(U2.1)",        "U2.1:D0_LED_LR",       "D0_LED_LR",    "Yellow", "MCU-D0"),
        (68.58, "D1/GPIO5(U2.2)",         "U2.2:D1_SERVO",        "D1_SERVO",     "Orange", "MCU-D1"),
        (73.66, "D2/GPIO4(U2.3)",         "U2.3:D2_DHT11",        "D2_DHT11",     "Blue",   "MCU-D2"),
        (78.74, "D3/GPIO0(U2.4)",         "U2.4:D3_AUDIO_PWM",    "D3_AUDIO_PWM", "White",  "MCU-D3"),
        (83.82, "D4/GPIO2(U2.5)",         "U2.5:D4_LED_BR",       "D4_LED_BR",    "White",  "MCU-D4"),
        (88.90, "D5/GPIO14(U2.8)",        "U2.8:D5_MIC_DO",       "D5_MIC_DO",    "Yellow", "MCU-D5"),
        (93.98, "D6/GPIO12(U2.9)",        "U2.9:D6_RLY1_PUMP",    "D6_RLY1_PUMP", "Green",  "MCU-D6"),
        (99.06, "D7/GPIO13(U2.10)",       "U2.10:D7_RLY2_AMP",    "D7_RLY2_AMP",  "Cyan",   "MCU-D7"),
        (104.14, "D8/GPIO15(U2.11)",      "U2.11:D8_BUZZER",      "D8_BUZZER",    "Orange", "MCU-D8"),
    ]

    # Left-side Hub Connectors (J1, J13, J14, J15, J7, J8, J2)
    LEFT_CONN_LAYOUT: list[tuple[str, list[float]]] = [
        ("J1",  [129.54, 134.62]),                     # PSU 5V 2A
        ("J13", [167.64, 172.72, 177.80]),             # DHT11
        ("J14", [200.66, 205.74, 210.82]),             # Soil LM393
        ("J15", [238.76, 243.84, 248.92]),             # KY-037
        ("J7",  [284.48, 289.56, 294.64]),             # Relay 1 Coil
        ("J8",  [304.80, 309.88]),                     # Relay 1 Contacts
        ("J2",  [335.28, 340.36]),                     # Submersible Pump
    ]

    # Right-side Hub Connectors (J3, J4, J5, J6, J9, J10, J11, J12)
    RIGHT_CONN_LAYOUT: list[tuple[str, list[float]]] = [
        ("J3",  [48.26, 53.34, 58.42]),                # SG90 Servo
        ("J4",  [83.82, 88.90]),                       # Living Room LED
        ("J5",  [116.84, 121.92]),                     # Bedroom LED
        ("J6",  [149.86, 154.94]),                     # Active Buzzer
        ("J9",  [195.58, 200.66, 205.74]),             # Relay 2 Coil
        ("J10", [215.90, 220.98]),                     # Relay 2 Contacts
        ("J11", [251.46, 256.54]),                     # PAM8403 Power
        ("J12", [266.70, 271.78]),                     # PAM8403 Audio In
    ]

    # Verify all 15 connectors J1..J15 are accounted for exactly once
    placed_conns = {ref for ref, _ in LEFT_CONN_LAYOUT} | {ref for ref, _ in RIGHT_CONN_LAYOUT}
    assert placed_conns == set(HUB_CONNECTOR_MAP.keys()), f"Connector mismatch: {placed_conns}"

    # -----------------------------------------------------------------------
    # Build HUB1 pins & internal divider graphics
    # -----------------------------------------------------------------------
    hub_pins: list[dict] = []
    hub_graphics: list[str] = []
    hub_pin_num = 1
    hub_pin_xy: dict[str, tuple[float, float]] = {}

    def hub_lib_y(sheet_y: float) -> float:
        return HUB_CY - sheet_y

    # Subtle vertical centerline inside HUB1 separating Left & Right pin columns
    hub_graphics.append(
        f"\t\t\t\t(polyline (pts (xy 0.00 {fmt(hub_lib_y(36.83))}) (xy 0.00 {fmt(hub_lib_y(278.13))}))"
        "\n\t\t\t\t\t(stroke (width 0.15) (type dash) (color 150 170 195 1))\n\t\t\t\t)"
    )

    # Header banner inside top of HUB1
    hub_graphics.append(
        f"\t\t\t\t(rectangle (start {fmt(-HUB_W/2)} {fmt(HUB_H/2)}) (end {fmt(HUB_W/2)} {fmt(HUB_H/2 - 6.35)})"
        "\n\t\t\t\t\t(stroke (width 0.25) (type default) (color 20 83 45 1))"
        "\n\t\t\t\t\t(fill (type color) (color 215 242 225 1))\n\t\t\t\t)"
    )

    # Add U1/U2 socket pins on left side of HUB1
    for sy, _, hlabel, _, _, _ in MCU_PINS_SPEC:
        pnum = str(hub_pin_num)
        hub_pin_num += 1
        hub_pins.append({
            "num": pnum,
            "name": hlabel,
            "side": "left",
            "sy_offset": sy - HUB_CY,
        })
        hub_pin_xy[f"MCU:{sy}"] = (HUB_LEFT_PIN_X, sy)

    # Divider line under U1/U2 on left side of HUB1
    def add_hub_div(side: str, sheet_y: float) -> None:
        ly = hub_lib_y(sheet_y)
        x_a, x_b = (-HUB_W / 2 + 1.27, -1.27) if side == "left" else (1.27, HUB_W / 2 - 1.27)
        hub_graphics.append(
            f"\t\t\t\t(polyline (pts (xy {fmt(x_a)} {fmt(ly)}) (xy {fmt(x_b)} {fmt(ly)}))"
            "\n\t\t\t\t\t(stroke (width 0.15) (type dot) (color 120 155 130 1))\n\t\t\t\t)"
        )

    add_hub_div("left", 114.30)

    # Add Left Connectors (J1, J13, J14, J15, J7, J8, J2)
    hub_conn_group_headers: list[tuple[str, float, float, str]] = []
    for ref, ys in LEFT_CONN_LAYOUT:
        conn = HUB_CONNECTOR_MAP[ref]
        assert len(conn.pins) == len(ys), f"{ref} pin count mismatch"
        hub_conn_group_headers.append((f"{ref} ({conn.value})", HUB_CX - HUB_W / 2 + 2.0, ys[0] - 4.0, "left"))
        for (pin_str, _, _, net), sy in zip(conn.pins, ys):
            pnum = str(hub_pin_num)
            hub_pin_num += 1
            hub_pins.append({
                "num": pnum,
                "name": f"{ref}.{pin_str}:{net}",
                "side": "left",
                "sy_offset": sy - HUB_CY,
            })
            hub_pin_xy[f"{ref}.{pin_str}"] = (HUB_LEFT_PIN_X, sy)
        if ref != "J2":
            add_hub_div("left", ys[-1] + 5.08)

    # Add Right Connectors (J3, J4, J5, J6, J9, J10, J11, J12)
    for ref, ys in RIGHT_CONN_LAYOUT:
        conn = HUB_CONNECTOR_MAP[ref]
        assert len(conn.pins) == len(ys), f"{ref} pin count mismatch"
        hub_conn_group_headers.append((f"{ref} ({conn.value})", HUB_CX + HUB_W / 2 - 2.0, ys[0] - 4.0, "right"))
        for (pin_str, _, _, net), sy in zip(conn.pins, ys):
            pnum = str(hub_pin_num)
            hub_pin_num += 1
            hub_pins.append({
                "num": pnum,
                "name": f"{net}:{ref}.{pin_str}",
                "side": "right",
                "sy_offset": sy - HUB_CY,
            })
            hub_pin_xy[f"{ref}.{pin_str}"] = (HUB_RIGHT_PIN_X, sy)
        if ref != "J12":
            add_hub_div("right", ys[-1] + 5.08)

    # On-board circuitry reference box inside bottom-right empty area of HUB1
    hub_graphics.append(
        f"\t\t\t\t(rectangle (start {fmt(2.54)} {fmt(hub_lib_y(281.94))}) (end {fmt(HUB_W/2 - 2.54)} {fmt(hub_lib_y(350.52))})"
        "\n\t\t\t\t\t(stroke (width 0.20) (type solid) (color 30 100 60 1))"
        "\n\t\t\t\t\t(fill (type color) (color 236 250 240 1))\n\t\t\t\t)"
    )

    # -----------------------------------------------------------------------
    # Build All 15 Off-Board Module Symbols
    # -----------------------------------------------------------------------
    lib_symbols: list[str] = []
    sheet_items: list[str] = []

    # 0. HUB1 lib_symbol + instance
    lib_symbols.append(build_custom_lib_symbol(
        "SystemWiring:Central_Hub_PCB",
        "HUB",
        HUB_W,
        HUB_H,
        hub_pins,
        fill_rgb=(242, 252, 245, 1.0),
        stroke_rgb=(22, 101, 52),
        pin_len=PIN_LEN,
        extra_graphics=hub_graphics,
        pin_font_size=1.18,
    ))
    sheet_items.append(build_symbol_instance(
        "SystemWiring:Central_Hub_PCB",
        "HUB1",
        "Central Hub DIY PCB (100x80mm 1-Layer, Sheet 1)",
        "Central Hub PCB Plug-In Interface (U1/U2 + J1..J15) - reference view only",
        HUB_CX,
        HUB_CY,
        HUB_W,
        HUB_H,
        hub_pins,
        ref_pos=(HUB_CX, 27.94),
        val_pos=(HUB_CX, 358.80),
    ))

    # HUB1 internal banner text & connector silkscreen headers
    sheet_items.append(kicad_text(
        "CENTRAL HUB PCB (DIY 1L - 100x80mm)",
        HUB_CX, 33.65, "txt:hub_banner",
        size=1.45, bold=True, justify="center", color=(20, 83, 45),
    ))
    sheet_items.append(kicad_text(
        "U1/U2 (NodeMCU 2x15 Socket)",
        HUB_CX - HUB_W / 2 + 2.0, 39.80, "txt:hub_u1u2_hdr",
        size=1.05, bold=True, justify="left", color=(20, 83, 45),
    ))
    for hdr_text, hx, hy, hjust in hub_conn_group_headers:
        sheet_items.append(kicad_text(
            hdr_text, hx, hy, f"txt:hub_hdr:{hdr_text}",
            size=1.00, bold=True, justify=hjust, color=(22, 101, 52),
        ))

    # HUB1 internal on-board circuitry box text (bottom-right of HUB1)
    onboard_notes = [
        ("ON-BOARD HUB PCB (Sheet 1)", True, (20, 83, 45)),
        ("100x80mm 1-Layer B.Cu (DRC=0)", False, (40, 60, 45)),
        ("C1/C2: 470uF 16V Bulk", False, (40, 60, 45)),
        ("C3/C6/C7: 100nF Decoupling", False, (40, 60, 45)),
        ("D1(Pump)/D2(Buzz): 1N4007", False, (40, 60, 45)),
        ("Q1(S8050)+R10(1k): Buzz NPN", False, (40, 60, 45)),
        ("D3: Green PWR LED + R8 1k", False, (40, 60, 45)),
        ("R1(D0)/R2(D4): 220R LED Lim", False, (40, 60, 45)),
        ("R3(D2)/R4(D3)/R7(D4): 10k PU", False, (40, 60, 45)),
        ("R9(D8): 10k Boot Pull-Down", False, (40, 60, 45)),
        ("C4/R5/R6/C5: PWM Audio RC", False, (40, 60, 45)),
        ("H1..H4: 4x M3 (90x70mm)", False, (40, 60, 45)),
    ]
    for idx, (line_txt, is_bold, col) in enumerate(onboard_notes):
        sheet_items.append(kicad_text(
            line_txt,
            HUB_CX + 4.2,
            286.2 + idx * 5.25,
            f"txt:hub_onboard:{idx}",
            size=1.02 if is_bold else 0.96,
            bold=is_bold,
            justify="left",
            color=col,
        ))

    # Helper to add a standard off-board module + its horizontal wires
    def add_module(
        *,
        lib_name: str,
        ref: str,
        value: str,
        desc: str,
        cx: float,
        cy: float,
        w: float,
        h: float,
        pins: list[dict],
        fill_rgb: tuple[int, int, int, float],
        stroke_rgb: tuple[int, int, int],
        extra_graphics: list[str] | None = None,
        ref_pos: tuple[float, float] | None = None,
        val_pos: tuple[float, float] | None = None,
    ) -> None:
        lib_id = f"SystemWiring:{lib_name}"
        lib_symbols.append(build_custom_lib_symbol(
            lib_id,
            re.sub(r"\d+$", "", ref),
            w,
            h,
            pins,
            fill_rgb=fill_rgb,
            stroke_rgb=stroke_rgb,
            pin_len=PIN_LEN,
            extra_graphics=extra_graphics,
            pin_font_size=1.18,
        ))
        sheet_items.append(build_symbol_instance(
            lib_id,
            ref,
            value,
            desc,
            cx,
            cy,
            w,
            h,
            pins,
            ref_pos=ref_pos,
            val_pos=val_pos,
        ))

    def connect_horizontal_wire(
        *,
        x_left: float,
        x_right: float,
        y: float,
        net: str,
        color: str,
        tag_text: str,
        side_of_hub: str,  # "left" (hub is on right) or "right" (hub is on left)
        key: str,
    ) -> None:
        code, col_rgb = WIRE_COLOR_META[color]
        sheet_items.append(kicad_wire(x_left, y, x_right, y, color, f"wire:{key}"))
        if side_of_hub == "left":
            # Net label cleanly inside dashed box (x_right - 5.08 = 243.84, right-justified)
            # Wire color tag near Module (x_left + 2.54 = 193.04, left-justified)
            sheet_items.append(kicad_label(
                net, x_right - 5.08, y, f"lbl:{key}",
                angle=0, justify="right bottom", size=1.15,
            ))
            sheet_items.append(kicad_text(
                f"{tag_text} [{code}]", x_left + 2.54, y - 0.70, f"wtag:{key}",
                size=1.02, bold=True, justify="left", color=col_rgb,
            ))
        else:
            # Net label cleanly inside dashed box (x_left + 5.08 = 350.52, left-justified)
            # Wire color tag near Module (x_right - 2.54 = 401.32, right-justified)
            sheet_items.append(kicad_label(
                net, x_left + 5.08, y, f"lbl:{key}",
                angle=0, justify="left bottom", size=1.15,
            ))
            sheet_items.append(kicad_text(
                f"{tag_text} [{code}]", x_right - 2.54, y - 0.70, f"wtag:{key}",
                size=1.02, bold=True, justify="right", color=col_rgb,
            ))

    # -----------------------------------------------------------------------
    # 1. MCU1 — NodeMCU v2 Amica (ESP8266) mounted on Hub U1/U2
    # -----------------------------------------------------------------------
    mcu_cy = 73.66
    mcu_h = 68.58  # y: 39.37 .. 107.95 (exact: 73.66 +/- 34.29)
    mcu_pins = [
        {"num": str(i + 1), "name": mlabel, "side": "right", "sy_offset": sy - mcu_cy}
        for i, (sy, mlabel, _, _, _, _) in enumerate(MCU_PINS_SPEC)
    ]
    # Small ESP-12E Wi-Fi shield graphic on left interior of MCU1
    mcu_gfx = [
        f"\t\t\t\t(rectangle (start {fmt(-L1_W/2 + 2.54)} {fmt(14.0)}) (end {fmt(-L1_W/2 + 12.7)} {fmt(-14.0)})"
        "\n\t\t\t\t\t(stroke (width 0.22) (type solid) (color 80 95 115 1))"
        "\n\t\t\t\t\t(fill (type color) (color 226 232 240 1))\n\t\t\t\t)",
    ]
    add_module(
        lib_name="NodeMCU_v2_Amica",
        ref="MCU1",
        value="NodeMCU v2 Amica (ESP8266)",
        desc="ESP8266 NodeMCU v2 Amica (48.26x25.4mm) plugged into Hub PCB sockets U1/U2",
        cx=L1_CX, cy=mcu_cy, w=L1_W, h=mcu_h,
        pins=mcu_pins,
        fill_rgb=(236, 244, 255, 1.0),
        stroke_rgb=(29, 78, 216),
        extra_graphics=mcu_gfx,
        ref_pos=(L1_CX, 37.30),
        val_pos=(L1_CX, 110.20),
    )
    for sy, _, _, net, color, tag in MCU_PINS_SPEC:
        connect_horizontal_wire(
            x_left=L1_RIGHT_PIN_X, x_right=HUB_LEFT_PIN_X, y=sy,
            net=net, color=color, tag_text=tag, side_of_hub="left", key=f"mcu:{tag}",
        )
    # MCU1 callout notes on far-left inside Box L1
    mcu_notes = [
        ("Mounts directly onto Hub", True),
        ("PCB sockets U1 & U2", True),
        ("(2x15 female, 22.86mm pitch)", False),
        ("", False),
        ("Dimensions: 48.26 x 25.4 mm", False),
        ("10 Active GPIOs Locked:", True),
        ("  D0=LED_LR   D1=SG90", False),
        ("  D2=DHT11    D3=Audio PWM", False),
        ("  D4=LED_BR   D5=KY-037 DO", False),
        ("  D6=Relay1   D7=Relay2", False),
        ("  D8=Buzzer   A0=Soil AO", False),
        ("Power: VIN=+5V, Reg=+3V3", False),
    ]
    for i, (nt, is_b) in enumerate(mcu_notes):
        if nt:
            sheet_items.append(kicad_text(
                nt, 25.40, 44.50 + i * 5.08, f"txt:mcu_note:{i}",
                size=1.08, bold=is_b, justify="left",
                color=(29, 78, 216) if is_b else (45, 55, 72),
            ))

    # -----------------------------------------------------------------------
    # 2. PSU1 — External 5V 2A Power Supply -> J1
    # -----------------------------------------------------------------------
    psu_cy = 132.08
    psu_h = 15.24  # y: 124.46 .. 139.70
    psu_pins = [
        {"num": "1", "name": "+5V OUT (2A)", "side": "right", "sy_offset": 129.54 - psu_cy},
        {"num": "2", "name": "GND RETURN",   "side": "right", "sy_offset": 134.62 - psu_cy},
    ]
    add_module(
        lib_name="External_PSU_5V_2A",
        ref="PSU1",
        value="External 5V 2A Power Supply",
        desc="External 5V 2A regulated DC power adapter wired to J1 screw terminal",
        cx=L1_CX, cy=psu_cy, w=L1_W, h=psu_h,
        pins=psu_pins,
        fill_rgb=(254, 242, 242, 1.0),
        stroke_rgb=(185, 28, 28),
        ref_pos=(L1_CX, 122.40),
        val_pos=(L1_CX, 142.00),
    )
    for pin_s, sy in [("1", 129.54), ("2", 134.62)]:
        w = wmap[("J1", pin_s)]
        connect_horizontal_wire(
            x_left=L1_RIGHT_PIN_X, x_right=HUB_LEFT_PIN_X, y=sy,
            net=w.net, color=w.color, tag_text=w.wire_id, side_of_hub="left", key=w.wire_id,
        )
    sheet_items.append(kicad_text(
        "22AWG Screw Terminal (J1)", 25.40, 129.54, "txt:psu_n1",
        size=1.10, bold=True, color=(185, 28, 28),
    ))
    sheet_items.append(kicad_text(
        "Feeds +5V rail (C1/C2 470uF,", 25.40, 134.62, "txt:psu_n2",
        size=1.05, color=(55, 65, 81),
    ))
    sheet_items.append(kicad_text(
        "C3 100nF, D3 Green PWR LED)", 25.40, 139.20, "txt:psu_n3",
        size=1.05, color=(55, 65, 81),
    ))

    # -----------------------------------------------------------------------
    # 3. Sensors (3.3V Domain): DHT1 (J13), SOIL1 (J14) + PRB1, MIC1 (J15)
    # -----------------------------------------------------------------------
    # 3a. DHT11 -> J13
    dht_cy = 172.72
    dht_h = 17.78  # y: 163.83 .. 181.61
    dht_pins = [
        {"num": "1", "name": "VCC (+3.3V)",  "side": "right", "sy_offset": 167.64 - dht_cy},
        {"num": "2", "name": "DATA (OUT)",   "side": "right", "sy_offset": 172.72 - dht_cy},
        {"num": "3", "name": "GND (-)",      "side": "right", "sy_offset": 177.80 - dht_cy},
    ]
    add_module(
        lib_name="DHT11_3Pin_Breakout",
        ref="DHT1",
        value="DHT11 Temp & Humidity (3-Pin)",
        desc="Aosong DHT11 3-pin breakout module (28x14x7.1mm) wired via Dupont 1x3 to J13",
        cx=L1_CX, cy=dht_cy, w=L1_W, h=dht_h,
        pins=dht_pins,
        fill_rgb=(239, 246, 255, 1.0),
        stroke_rgb=(37, 99, 235),
        ref_pos=(L1_CX, 161.80),
        val_pos=(L1_CX, 184.00),
    )
    for pin_s, sy in [("1", 167.64), ("2", 172.72), ("3", 177.80)]:
        w = wmap[("J13", pin_s)]
        connect_horizontal_wire(
            x_left=L1_RIGHT_PIN_X, x_right=HUB_LEFT_PIN_X, y=sy,
            net=w.net, color=w.color, tag_text=w.wire_id, side_of_hub="left", key=w.wire_id,
        )
    sheet_items.append(kicad_text(
        "DHT11 Breakout (28x14mm)", 25.40, 168.50, "txt:dht_n1",
        size=1.08, bold=True, color=(37, 99, 235),
    ))
    sheet_items.append(kicad_text(
        "Dupont 1x3 F-F -> J13 (D2)", 25.40, 173.50, "txt:dht_n2",
        size=1.02, color=(55, 65, 81),
    ))
    sheet_items.append(kicad_text(
        "Hub on-board R3 10k pull-up", 25.40, 178.50, "txt:dht_n3",
        size=1.02, color=(55, 65, 81),
    ))

    # 3b. SOIL1 (LM393 Comparator) -> J14 & -> PRB1 (YL-69 Soil Fork Probe)
    soil_cy = 208.28
    soil_h = 22.86  # y: 196.85 .. 219.71
    soil_pins = [
        {"num": "1", "name": "VCC (+3.3V!)", "side": "right", "sy_offset": 200.66 - soil_cy},
        {"num": "2", "name": "GND",          "side": "right", "sy_offset": 205.74 - soil_cy},
        {"num": "3", "name": "AO (Analog)",  "side": "right", "sy_offset": 210.82 - soil_cy},
        {"num": "4", "name": "P1 (Probe+)",  "side": "left",  "sy_offset": 200.66 - soil_cy},
        {"num": "5", "name": "P2 (Probe-)",  "side": "left",  "sy_offset": 205.74 - soil_cy},
        {"num": "6", "name": "DO (Unused)",  "side": "left",  "sy_offset": 215.90 - soil_cy},
    ]
    add_module(
        lib_name="Soil_LM393_Comparator",
        ref="SOIL1",
        value="Soil LM393 Comparator (3.3V ONLY)",
        desc="LM393 soil moisture comparator (32x14mm) powered STRICTLY at 3.3V; DO unused (NC)",
        cx=L1_CX, cy=soil_cy, w=L1_W, h=soil_h,
        pins=soil_pins,
        fill_rgb=(240, 253, 244, 1.0),
        stroke_rgb=(21, 128, 61),
        ref_pos=(L1_CX, 194.80),
        val_pos=(L1_CX, 222.00),
    )
    for pin_s, sy in [("1", 200.66), ("2", 205.74), ("3", 210.82)]:
        w = wmap[("J14", pin_s)]
        connect_horizontal_wire(
            x_left=L1_RIGHT_PIN_X, x_right=HUB_LEFT_PIN_X, y=sy,
            net=w.net, color=w.color, tag_text=w.wire_id, side_of_hub="left", key=w.wire_id,
        )
    # No-connect marker on SOIL1 pin 6 (DO) at left pin tip
    sheet_items.append(kicad_no_connect(L1_LEFT_PIN_X, 215.90, "nc:soil_do"))
    sheet_items.append(kicad_text(
        "NC (DO unused)", L1_LEFT_PIN_X - 2.0, 215.90, "txt:soil_do_nc",
        size=0.98, justify="right", color=(140, 50, 50),
    ))

    # PRB1 (YL-69 Soil Fork Probe) wired to SOIL1 P1, P2
    prb_cy = 203.20
    prb_h = 15.24  # y: 195.58 .. 210.82
    prb_pins = [
        {"num": "1", "name": "Prong A", "side": "right", "sy_offset": 200.66 - prb_cy},
        {"num": "2", "name": "Prong B", "side": "right", "sy_offset": 205.74 - prb_cy},
    ]
    # Stylized 2-prong fork icon on left inside PRB1
    prb_gfx = [
        f"\t\t\t\t(polyline (pts (xy {fmt(-L2_W/2 + 3.0)} 3.0) (xy {fmt(-L2_W/2 + 13.0)} 3.0))"
        "\n\t\t\t\t\t(stroke (width 0.50) (type solid) (color 140 90 35 1))\n\t\t\t\t)",
        f"\t\t\t\t(polyline (pts (xy {fmt(-L2_W/2 + 3.0)} -3.0) (xy {fmt(-L2_W/2 + 13.0)} -3.0))"
        "\n\t\t\t\t\t(stroke (width 0.50) (type solid) (color 140 90 35 1))\n\t\t\t\t)",
    ]
    add_module(
        lib_name="YL69_Soil_Fork_Probe",
        ref="PRB1",
        value="YL-69 Soil Fork Probe",
        desc="YL-69 2-prong resistive soil moisture probe (60x20mm) wired to LM393 P1/P2",
        cx=L2_CX, cy=prb_cy, w=L2_W, h=prb_h,
        pins=prb_pins,
        fill_rgb=(254, 249, 195, 1.0),
        stroke_rgb=(161, 98, 7),
        extra_graphics=prb_gfx,
        ref_pos=(L2_CX, 193.60),
        val_pos=(L2_CX, 213.20),
    )
    for pin_s, sy in [("P1", 200.66), ("P2", 205.74)]:
        w = wmap[("LM393", pin_s)]
        connect_horizontal_wire(
            x_left=L2_RIGHT_PIN_X, x_right=L1_LEFT_PIN_X, y=sy,
            net=w.net, color=w.color, tag_text=w.wire_id, side_of_hub="left", key=w.wire_id,
        )
    sheet_items.append(kicad_text(
        "STRICTLY 3.3V (ESP8266 ADC0 safe); Hub C7 100nF", 25.40, 222.50, "txt:soil_warn",
        size=0.98, bold=True, color=(21, 128, 61),
    ))

    # 3c. MIC1 (KY-037 / KY-038 Sound Module) -> J15
    mic_cy = 243.84
    mic_h = 17.78  # y: 234.95 .. 252.73
    mic_pins = [
        {"num": "1", "name": "+ (VCC 3.3V)", "side": "right", "sy_offset": 238.76 - mic_cy},
        {"num": "2", "name": "G (GND)",      "side": "right", "sy_offset": 243.84 - mic_cy},
        {"num": "3", "name": "DO (Trigger)", "side": "right", "sy_offset": 248.92 - mic_cy},
        {"num": "4", "name": "AO (Unused)",  "side": "left",  "sy_offset": 248.92 - mic_cy},
    ]
    # Small electret mic capsule circle inside MIC1
    mic_gfx = [
        f"\t\t\t\t(circle (center {fmt(-L1_W/2 + 8.0)} 3.0) (radius 3.2)"
        "\n\t\t\t\t\t(stroke (width 0.28) (type solid) (color 161 98 7 1))"
        "\n\t\t\t\t\t(fill (type color) (color 254 243 199 1))\n\t\t\t\t)",
    ]
    add_module(
        lib_name="KY037_Sound_Module",
        ref="MIC1",
        value="KY-037 / KY-038 Sound Sensor",
        desc="KY-037/038 sound module (35x15mm) powered at 3.3V; DO->J15.3(D5), AO unused (NC)",
        cx=L1_CX, cy=mic_cy, w=L1_W, h=mic_h,
        pins=mic_pins,
        fill_rgb=(255, 251, 235, 1.0),
        stroke_rgb=(180, 83, 9),
        extra_graphics=mic_gfx,
        ref_pos=(L1_CX, 233.00),
        val_pos=(L1_CX, 255.20),
    )
    for pin_s, sy in [("1", 238.76), ("2", 243.84), ("3", 248.92)]:
        w = wmap[("J15", pin_s)]
        connect_horizontal_wire(
            x_left=L1_RIGHT_PIN_X, x_right=HUB_LEFT_PIN_X, y=sy,
            net=w.net, color=w.color, tag_text=w.wire_id, side_of_hub="left", key=w.wire_id,
        )
    sheet_items.append(kicad_no_connect(L1_LEFT_PIN_X, 248.92, "nc:mic_ao"))
    sheet_items.append(kicad_text(
        "NC (AO unused)", L1_LEFT_PIN_X - 2.0, 248.92, "txt:mic_ao_nc",
        size=0.98, justify="right", color=(140, 50, 50),
    ))
    sheet_items.append(kicad_text(
        "KY-037/038 (35x15mm, 3.3V)", 25.40, 237.50, "txt:mic_n1",
        size=1.08, bold=True, color=(180, 83, 9),
    ))
    sheet_items.append(kicad_text(
        "Clap/Loud interrupt on D5", 25.40, 242.50, "txt:mic_n2",
        size=1.02, color=(55, 65, 81),
    ))

    # -----------------------------------------------------------------------
    # 4. Garden Pump Subsystem: RLY1 (J7, J8) & PMP1 (J2)
    # -----------------------------------------------------------------------
    # 4a. RLY1 (Relay 1 Blue 5V 1-ch)
    rly1_cy = 297.18
    rly1_h = 33.02  # y: 280.67 .. 313.69
    rly1_pins = [
        {"num": "1", "name": "VCC (+5V Coil)", "side": "right", "sy_offset": 284.48 - rly1_cy},
        {"num": "2", "name": "GND",            "side": "right", "sy_offset": 289.56 - rly1_cy},
        {"num": "3", "name": "IN (Active-HI)", "side": "right", "sy_offset": 294.64 - rly1_cy},
        {"num": "4", "name": "COM (Screw)",    "side": "right", "sy_offset": 304.80 - rly1_cy},
        {"num": "5", "name": "NO  (Screw)",    "side": "right", "sy_offset": 309.88 - rly1_cy},
        {"num": "6", "name": "NC  (Unused)",   "side": "left",  "sy_offset": 309.88 - rly1_cy},
    ]
    rly1_gfx = [
        f"\t\t\t\t(polyline (pts (xy {fmt(-L1_W/2 + 1.27)} {fmt(rly1_cy - 299.72)}) (xy {fmt(L1_W/2 - 1.27)} {fmt(rly1_cy - 299.72)}))"
        "\n\t\t\t\t\t(stroke (width 0.18) (type dash) (color 37 99 235 1))\n\t\t\t\t)",
    ]
    add_module(
        lib_name="Relay1_Blue_5V_1ch",
        ref="RLY1",
        value="Relay 1 (Blue 5V 1-ch Songle)",
        desc="Songle SRD-05VDC-SL-C 1-channel blue relay (50x26mm); J7 coil, J8 COM/NO, NC unused",
        cx=L1_CX, cy=rly1_cy, w=L1_W, h=rly1_h,
        pins=rly1_pins,
        fill_rgb=(219, 234, 254, 1.0),
        stroke_rgb=(29, 78, 216),
        extra_graphics=rly1_gfx,
        ref_pos=(L1_CX, 278.60),
        val_pos=(L1_CX, 316.20),
    )
    for ref_c, pin_s, sy in [
        ("J7", "1", 284.48), ("J7", "2", 289.56), ("J7", "3", 294.64),
        ("J8", "1", 304.80), ("J8", "2", 309.88),
    ]:
        w = wmap[(ref_c, pin_s)]
        connect_horizontal_wire(
            x_left=L1_RIGHT_PIN_X, x_right=HUB_LEFT_PIN_X, y=sy,
            net=w.net, color=w.color, tag_text=w.wire_id, side_of_hub="left", key=w.wire_id,
        )
    sheet_items.append(kicad_no_connect(L1_LEFT_PIN_X, 309.88, "nc:rly1_nc"))
    sheet_items.append(kicad_text(
        "NC (unused)", L1_LEFT_PIN_X - 2.0, 309.88, "txt:rly1_nc",
        size=0.98, justify="right", color=(140, 50, 50),
    ))
    sheet_items.append(kicad_text(
        "Relay 1: Songle 5V (50x26mm)", 25.40, 285.00, "txt:rly1_n1",
        size=1.08, bold=True, color=(29, 78, 216),
    ))
    sheet_items.append(kicad_text(
        "Coil: J7 (D6 Active-HIGH)", 25.40, 290.08, "txt:rly1_n2",
        size=1.02, color=(55, 65, 81),
    ))
    sheet_items.append(kicad_text(
        "Contacts: J8 switches +5V", 25.40, 295.16, "txt:rly1_n3",
        size=1.02, color=(55, 65, 81),
    ))
    sheet_items.append(kicad_text(
        "-> PUMP_5V -> Hub D1 -> J2", 25.40, 300.24, "txt:rly1_n4",
        size=1.02, color=(55, 65, 81),
    ))

    # 4b. PMP1 (Mini Submersible Water Pump 3-6V) -> J2
    pmp_cy = 337.82
    pmp_h = 15.24  # y: 330.20 .. 345.44
    pmp_pins = [
        {"num": "1", "name": "Pump + (Red)",   "side": "right", "sy_offset": 335.28 - pmp_cy},
        {"num": "2", "name": "Pump - (Black)", "side": "right", "sy_offset": 340.36 - pmp_cy},
    ]
    pmp_gfx = [
        f"\t\t\t\t(circle (center {fmt(-L1_W/2 + 9.0)} 0.0) (radius 4.2)"
        "\n\t\t\t\t\t(stroke (width 0.30) (type solid) (color 3 105 161 1))"
        "\n\t\t\t\t\t(fill (type color) (color 224 242 254 1))\n\t\t\t\t)",
    ]
    add_module(
        lib_name="Mini_Submersible_Pump",
        ref="PMP1",
        value="Mini Submersible Pump (3-6V DC)",
        desc="Horizontal 3-6V DC submersible water pump (45x24x33mm) wired to J2 screw terminal",
        cx=L1_CX, cy=pmp_cy, w=L1_W, h=pmp_h,
        pins=pmp_pins,
        fill_rgb=(224, 242, 254, 1.0),
        stroke_rgb=(3, 105, 161),
        extra_graphics=pmp_gfx,
        ref_pos=(L1_CX, 328.20),
        val_pos=(L1_CX, 347.90),
    )
    sheet_items.append(kicad_text(
        "M", L1_CX - L1_W / 2 + 9.0, pmp_cy, "txt:pmp_m",
        size=1.80, bold=True, justify="center", color=(3, 105, 161),
    ))
    for pin_s, sy in [("1", 335.28), ("2", 340.36)]:
        w = wmap[("J2", pin_s)]
        connect_horizontal_wire(
            x_left=L1_RIGHT_PIN_X, x_right=HUB_LEFT_PIN_X, y=sy,
            net=w.net, color=w.color, tag_text=w.wire_id, side_of_hub="left", key=w.wire_id,
        )
    sheet_items.append(kicad_text(
        "J2 Screw Term (22AWG)", 25.40, 332.74, "txt:pmp_n1",
        size=1.08, bold=True, color=(3, 105, 161),
    ))
    sheet_items.append(kicad_text(
        "Protected on Hub PCB by:", 25.40, 337.82, "txt:pmp_n2",
        size=1.02, color=(55, 65, 81),
    ))
    sheet_items.append(kicad_text(
        "D1 (1N4007 flyback) &", 25.40, 342.90, "txt:pmp_n3",
        size=1.02, bold=True, color=(153, 27, 27),
    ))
    sheet_items.append(kicad_text(
        "C2 (470uF 16V bulk cap)", 25.40, 347.98, "txt:pmp_n4",
        size=1.02, bold=True, color=(153, 27, 27),
    ))

    # -----------------------------------------------------------------------
    # 5. Core Actuators (Right Column Top): SRV1 (J3), LED1 (J4), LED2 (J5), BUZ1 (J6)
    # -----------------------------------------------------------------------
    # 5a. SRV1 (SG90 Micro Servo) -> J3
    srv_cy = 53.34
    srv_h = 17.78  # y: 44.45 .. 62.23
    srv_pins = [
        {"num": "1", "name": "PWM (Orange)", "side": "left", "sy_offset": 48.26 - srv_cy},
        {"num": "2", "name": "VCC (Red)",    "side": "left", "sy_offset": 53.34 - srv_cy},
        {"num": "3", "name": "GND (Brown)",  "side": "left", "sy_offset": 58.42 - srv_cy},
    ]
    srv_gfx = [
        f"\t\t\t\t(circle (center {fmt(R1_W/2 - 8.5)} 0.0) (radius 4.0)"
        "\n\t\t\t\t\t(stroke (width 0.28) (type solid) (color 194 65 12 1))"
        "\n\t\t\t\t\t(fill (type color) (color 255 237 213 1))\n\t\t\t\t)",
        f"\t\t\t\t(polyline (pts (xy {fmt(R1_W/2 - 8.5)} 0.0) (xy {fmt(R1_W/2 - 3.5)} 4.5))"
        "\n\t\t\t\t\t(stroke (width 0.45) (type solid) (color 194 65 12 1))\n\t\t\t\t)",
    ]
    add_module(
        lib_name="SG90_Micro_Servo",
        ref="SRV1",
        value="SG90 Micro Servo (Main Door)",
        desc="TowerPro SG90 9g micro servo (22.8x12.2x22.5mm) wired via Dupont 1x3 F-M to J3",
        cx=R1_CX, cy=srv_cy, w=R1_W, h=srv_h,
        pins=srv_pins,
        fill_rgb=(255, 247, 237, 1.0),
        stroke_rgb=(194, 65, 12),
        extra_graphics=srv_gfx,
        ref_pos=(R1_CX, 42.40),
        val_pos=(R1_CX, 64.60),
    )
    for pin_s, sy in [("1", 48.26), ("2", 53.34), ("3", 58.42)]:
        w = wmap[("J3", pin_s)]
        connect_horizontal_wire(
            x_left=HUB_RIGHT_PIN_X, x_right=R1_LEFT_PIN_X, y=sy,
            net=w.net, color=w.color, tag_text=w.wire_id, side_of_hub="right", key=w.wire_id,
        )
    sheet_items.append(kicad_text(
        "SG90 Main Door Servo", 472.44, 48.26, "txt:srv_n1",
        size=1.08, bold=True, color=(194, 65, 12),
    ))
    sheet_items.append(kicad_text(
        "50Hz PWM: 0 deg / 90 deg", 472.44, 53.34, "txt:srv_n2",
        size=1.02, color=(55, 65, 81),
    ))
    sheet_items.append(kicad_text(
        "Dupont 1x3 F-M; Hub C1 470uF", 472.44, 58.42, "txt:srv_n3",
        size=1.02, color=(55, 65, 81),
    ))

    # 5b. LED1 (Living Room 5mm LED) -> J4
    led1_cy = 86.36
    led1_h = 15.24  # y: 78.74 .. 93.98
    led1_pins = [
        {"num": "1", "name": "Anode (+)",   "side": "left", "sy_offset": 83.82 - led1_cy},
        {"num": "2", "name": "Cathode (-)", "side": "left", "sy_offset": 88.90 - led1_cy},
    ]
    led_diode_gfx = [
        # Diode triangle pointing down inside right side of LED box
        f"\t\t\t\t(polyline (pts (xy {fmt(R1_W/2 - 12.0)} 2.8) (xy {fmt(R1_W/2 - 6.0)} 2.8) (xy {fmt(R1_W/2 - 9.0)} -2.2) (xy {fmt(R1_W/2 - 12.0)} 2.8))"
        "\n\t\t\t\t\t(stroke (width 0.30) (type solid) (color 161 98 7 1))"
        "\n\t\t\t\t\t(fill (type color) (color 254 240 138 1))\n\t\t\t\t)",
        f"\t\t\t\t(polyline (pts (xy {fmt(R1_W/2 - 12.0)} -2.2) (xy {fmt(R1_W/2 - 6.0)} -2.2))"
        "\n\t\t\t\t\t(stroke (width 0.35) (type solid) (color 161 98 7 1))\n\t\t\t\t)",
    ]
    add_module(
        lib_name="LED_5mm_LivingRoom",
        ref="LED1",
        value="5mm LED (Living Room, D0)",
        desc="5mm T-1 3/4 LED (Living Room, Active-HIGH) via on-board R1 220R on J4",
        cx=R1_CX, cy=led1_cy, w=R1_W, h=led1_h,
        pins=led1_pins,
        fill_rgb=(254, 252, 232, 1.0),
        stroke_rgb=(161, 98, 7),
        extra_graphics=led_diode_gfx,
        ref_pos=(R1_CX, 76.70),
        val_pos=(R1_CX, 96.30),
    )
    for pin_s, sy in [("1", 83.82), ("2", 88.90)]:
        w = wmap[("J4", pin_s)]
        connect_horizontal_wire(
            x_left=HUB_RIGHT_PIN_X, x_right=R1_LEFT_PIN_X, y=sy,
            net=w.net, color=w.color, tag_text=w.wire_id, side_of_hub="right", key=w.wire_id,
        )
    sheet_items.append(kicad_text(
        "Living Room LED (Active-HIGH)", 472.44, 83.82, "txt:led1_n1",
        size=1.08, bold=True, color=(161, 98, 7),
    ))
    sheet_items.append(kicad_text(
        "Hub on-board R1 220R limiter", 472.44, 88.90, "txt:led1_n2",
        size=1.02, color=(55, 65, 81),
    ))

    # 5c. LED2 (Bedroom 5mm LED, Boot-Safe Active-LOW) -> J5
    led2_cy = 119.38
    led2_h = 15.24  # y: 111.76 .. 127.00
    led2_pins = [
        {"num": "1", "name": "Anode (+ via R2)", "side": "left", "sy_offset": 116.84 - led2_cy},
        {"num": "2", "name": "Cathode (D4 Sink)", "side": "left", "sy_offset": 121.92 - led2_cy},
    ]
    led2_diode_gfx = [
        f"\t\t\t\t(polyline (pts (xy {fmt(R1_W/2 - 12.0)} 2.8) (xy {fmt(R1_W/2 - 6.0)} 2.8) (xy {fmt(R1_W/2 - 9.0)} -2.2) (xy {fmt(R1_W/2 - 12.0)} 2.8))"
        "\n\t\t\t\t\t(stroke (width 0.30) (type solid) (color 126 34 206 1))"
        "\n\t\t\t\t\t(fill (type color) (color 233 213 255 1))\n\t\t\t\t)",
        f"\t\t\t\t(polyline (pts (xy {fmt(R1_W/2 - 12.0)} -2.2) (xy {fmt(R1_W/2 - 6.0)} -2.2))"
        "\n\t\t\t\t\t(stroke (width 0.35) (type solid) (color 126 34 206 1))\n\t\t\t\t)",
    ]
    add_module(
        lib_name="LED_5mm_Bedroom",
        ref="LED2",
        value="5mm LED (Bedroom, Boot-Safe)",
        desc="5mm T-1 3/4 LED (Bedroom, Active-LOW on D4/GPIO2) via R2 220R & R7 10k pull-up",
        cx=R1_CX, cy=led2_cy, w=R1_W, h=led2_h,
        pins=led2_pins,
        fill_rgb=(250, 245, 255, 1.0),
        stroke_rgb=(126, 34, 206),
        extra_graphics=led2_diode_gfx,
        ref_pos=(R1_CX, 109.70),
        val_pos=(R1_CX, 129.30),
    )
    for pin_s, sy in [("1", 116.84), ("2", 121.92)]:
        w = wmap[("J5", pin_s)]
        connect_horizontal_wire(
            x_left=HUB_RIGHT_PIN_X, x_right=R1_LEFT_PIN_X, y=sy,
            net=w.net, color=w.color, tag_text=w.wire_id, side_of_hub="right", key=w.wire_id,
        )
    sheet_items.append(kicad_text(
        "Bedroom LED (Active-LOW)", 472.44, 114.80, "txt:led2_n1",
        size=1.08, bold=True, color=(126, 34, 206),
    ))
    sheet_items.append(kicad_text(
        "Boot-Safe: R2 220R + R7 10k", 472.44, 119.88, "txt:led2_n2",
        size=1.02, color=(55, 65, 81),
    ))
    sheet_items.append(kicad_text(
        "keeps GPIO2 HIGH at boot", 472.44, 124.50, "txt:led2_n3",
        size=1.02, color=(55, 65, 81),
    ))

    # 5d. BUZ1 (Active 5V Buzzer TMB12A05) -> J6
    buz_cy = 152.40
    buz_h = 15.24  # y: 144.78 .. 160.02
    buz_pins = [
        {"num": "1", "name": "Buzzer (+)", "side": "left", "sy_offset": 149.86 - buz_cy},
        {"num": "2", "name": "Buzzer (-)", "side": "left", "sy_offset": 154.94 - buz_cy},
    ]
    buz_gfx = [
        f"\t\t\t\t(circle (center {fmt(R1_W/2 - 9.0)} 0.0) (radius 4.2)"
        "\n\t\t\t\t\t(stroke (width 0.30) (type solid) (color 194 65 12 1))"
        "\n\t\t\t\t\t(fill (type color) (color 254 215 170 1))\n\t\t\t\t)",
        f"\t\t\t\t(circle (center {fmt(R1_W/2 - 9.0)} 0.0) (radius 1.4)"
        "\n\t\t\t\t\t(stroke (width 0.25) (type solid) (color 194 65 12 1))"
        "\n\t\t\t\t\t(fill (type none))\n\t\t\t\t)",
    ]
    add_module(
        lib_name="Active_Buzzer_TMB12A05",
        ref="BUZ1",
        value="Active 5V Buzzer (TMB12A05)",
        desc="Active 5V piezo/electromagnetic buzzer (12x12x9.5mm) wired to J6 (D8/GPIO15)",
        cx=R1_CX, cy=buz_cy, w=R1_W, h=buz_h,
        pins=buz_pins,
        fill_rgb=(255, 247, 237, 1.0),
        stroke_rgb=(194, 65, 12),
        extra_graphics=buz_gfx,
        ref_pos=(R1_CX, 142.80),
        val_pos=(R1_CX, 162.40),
    )
    for pin_s, sy in [("1", 149.86), ("2", 154.94)]:
        w = wmap[("J6", pin_s)]
        connect_horizontal_wire(
            x_left=HUB_RIGHT_PIN_X, x_right=R1_LEFT_PIN_X, y=sy,
            net=w.net, color=w.color, tag_text=w.wire_id, side_of_hub="right", key=w.wire_id,
        )
    sheet_items.append(kicad_text(
        "Alarm Siren (TMB12A05, 5V)", 472.44, 148.00, "txt:buz_n1",
        size=1.08, bold=True, color=(194, 65, 12),
    ))
    sheet_items.append(kicad_text(
        "Hub Q1 S8050 NPN + R10 1k (D8)", 472.44, 153.08, "txt:buz_n2",
        size=1.02, color=(55, 65, 81),
    ))
    sheet_items.append(kicad_text(
        "R9 10k pull-down + D2 1N4007", 472.44, 158.16, "txt:buz_n3",
        size=1.02, color=(55, 65, 81),
    ))

    # -----------------------------------------------------------------------
    # 6. Audio Subsystem (Right Column Middle): RLY2 (J9, J10), AMP1 (J11, J12), SPK1
    # -----------------------------------------------------------------------
    # 6a. RLY2 (Relay 2 Red Opto 5V, Jmp=H) -> J9 & J10
    rly2_cy = 208.28
    rly2_h = 33.02  # y: 191.77 .. 224.79
    rly2_pins = [
        {"num": "1", "name": "DC+ (+5V)",     "side": "left",  "sy_offset": 195.58 - rly2_cy},
        {"num": "2", "name": "DC- (GND)",     "side": "left",  "sy_offset": 200.66 - rly2_cy},
        {"num": "3", "name": "IN (Jmp=H)",    "side": "left",  "sy_offset": 205.74 - rly2_cy},
        {"num": "4", "name": "COM (Screw)",   "side": "left",  "sy_offset": 215.90 - rly2_cy},
        {"num": "5", "name": "NO  (Screw)",   "side": "left",  "sy_offset": 220.98 - rly2_cy},
        {"num": "6", "name": "NC  (Unused)",  "side": "right", "sy_offset": 220.98 - rly2_cy},
    ]
    rly2_gfx = [
        f"\t\t\t\t(polyline (pts (xy {fmt(-R1_W/2 + 1.27)} {fmt(rly2_cy - 210.82)}) (xy {fmt(R1_W/2 - 1.27)} {fmt(rly2_cy - 210.82)}))"
        "\n\t\t\t\t\t(stroke (width 0.18) (type dash) (color 185 28 28 1))\n\t\t\t\t)",
    ]
    add_module(
        lib_name="Relay2_Red_Opto_5V",
        ref="RLY2",
        value="Relay 2 (Red Opto 5V, Jmp=H)",
        desc="Red opto-isolated 5V 1-ch relay (50x26mm, trigger jumper=H); J9 ctrl, J10 COM/NO",
        cx=R1_CX, cy=rly2_cy, w=R1_W, h=rly2_h,
        pins=rly2_pins,
        fill_rgb=(254, 226, 226, 1.0),
        stroke_rgb=(185, 28, 28),
        extra_graphics=rly2_gfx,
        ref_pos=(R1_CX, 189.70),
        val_pos=(R1_CX, 227.30),
    )
    for ref_c, pin_s, sy in [
        ("J9", "1", 195.58), ("J9", "2", 200.66), ("J9", "3", 205.74),
        ("J10", "1", 215.90), ("J10", "2", 220.98),
    ]:
        w = wmap[(ref_c, pin_s)]
        connect_horizontal_wire(
            x_left=HUB_RIGHT_PIN_X, x_right=R1_LEFT_PIN_X, y=sy,
            net=w.net, color=w.color, tag_text=w.wire_id, side_of_hub="right", key=w.wire_id,
        )
    sheet_items.append(kicad_no_connect(R1_RIGHT_PIN_X, 220.98, "nc:rly2_nc"))
    sheet_items.append(kicad_text(
        "NC (unused)", R1_RIGHT_PIN_X + 2.0, 220.98, "txt:rly2_nc",
        size=0.98, justify="left", color=(140, 50, 50),
    ))
    sheet_items.append(kicad_text(
        "Relay 2: Red Opto 5V (50x26)", 472.44, 195.58, "txt:rly2_n1",
        size=1.08, bold=True, color=(185, 28, 28),
    ))
    sheet_items.append(kicad_text(
        "Trigger Jumper = H (Act-HI)", 472.44, 200.66, "txt:rly2_n2",
        size=1.02, color=(55, 65, 81),
    ))
    sheet_items.append(kicad_text(
        "Switches +5V -> AMP_5V (J11)", 472.44, 205.74, "txt:rly2_n3",
        size=1.02, color=(55, 65, 81),
    ))
    sheet_items.append(kicad_text(
        "Auto-off 1.5s after chime", 472.44, 210.82, "txt:rly2_n4",
        size=1.02, color=(55, 65, 81),
    ))

    # 6b. AMP1 (PAM8403 Mini Audio Amp) -> J11, J12 & -> SPK1
    amp_cy = 261.62
    amp_h = 27.94  # y: 247.65 .. 275.59
    amp_pins = [
        {"num": "1", "name": "5V+ (AMP_5V)", "side": "left",  "sy_offset": 251.46 - amp_cy},
        {"num": "2", "name": "5V- (GND)",    "side": "left",  "sy_offset": 256.54 - amp_cy},
        {"num": "3", "name": "L_IN (Audio)", "side": "left",  "sy_offset": 266.70 - amp_cy},
        {"num": "4", "name": "AUD_GND",      "side": "left",  "sy_offset": 271.78 - amp_cy},
        {"num": "5", "name": "L_OUT+",       "side": "right", "sy_offset": 256.54 - amp_cy},
        {"num": "6", "name": "L_OUT-",       "side": "right", "sy_offset": 266.70 - amp_cy},
    ]
    amp_gfx = [
        f"\t\t\t\t(polyline (pts (xy {fmt(-R1_W/2 + 1.27)} {fmt(amp_cy - 261.62)}) (xy 0.0 {fmt(amp_cy - 261.62)}))"
        "\n\t\t\t\t\t(stroke (width 0.16) (type dash) (color 21 128 61 1))\n\t\t\t\t)",
    ]
    add_module(
        lib_name="PAM8403_Mini_Audio_Amp",
        ref="AMP1",
        value="PAM8403 Mini Audio Amp",
        desc="PAM8403 3W Class-D stereo mini audio amplifier (21x18mm) - BTL differential output",
        cx=R1_CX, cy=amp_cy, w=R1_W, h=amp_h,
        pins=amp_pins,
        fill_rgb=(220, 252, 231, 1.0),
        stroke_rgb=(21, 128, 61),
        extra_graphics=amp_gfx,
        ref_pos=(R1_CX, 245.50),
        val_pos=(R1_CX, 278.00),
    )
    for ref_c, pin_s, sy in [
        ("J11", "1", 251.46), ("J11", "2", 256.54),
        ("J12", "1", 266.70), ("J12", "2", 271.78),
    ]:
        w = wmap[(ref_c, pin_s)]
        connect_horizontal_wire(
            x_left=HUB_RIGHT_PIN_X, x_right=R1_LEFT_PIN_X, y=sy,
            net=w.net, color=w.color, tag_text=w.wire_id, side_of_hub="right", key=w.wire_id,
        )

    # 6c. SPK1 (Mini Speaker 28mm 8Ohm 0.5W) wired directly to AMP1 L_OUT+, L_OUT-
    spk_cy = 261.62
    spk_h = 20.32  # y: 251.46 .. 271.78
    spk_pins = [
        {"num": "1", "name": "SPK +", "side": "left", "sy_offset": 256.54 - spk_cy},
        {"num": "2", "name": "SPK -", "side": "left", "sy_offset": 266.70 - spk_cy},
    ]
    # Speaker cone symbol inside right half of SPK1
    spk_gfx = [
        f"\t\t\t\t(rectangle (start {fmt(R2_W/2 - 14.0)} 3.0) (end {fmt(R2_W/2 - 10.5)} -3.0)"
        "\n\t\t\t\t\t(stroke (width 0.28) (type solid) (color 88 28 135 1))"
        "\n\t\t\t\t\t(fill (type color) (color 233 213 255 1))\n\t\t\t\t)",
        f"\t\t\t\t(polyline (pts (xy {fmt(R2_W/2 - 10.5)} 3.0) (xy {fmt(R2_W/2 - 5.0)} 6.5) (xy {fmt(R2_W/2 - 5.0)} -6.5) (xy {fmt(R2_W/2 - 10.5)} -3.0))"
        "\n\t\t\t\t\t(stroke (width 0.30) (type solid) (color 88 28 135 1))"
        "\n\t\t\t\t\t(fill (type none))\n\t\t\t\t)",
    ]
    add_module(
        lib_name="Mini_Speaker_28mm_8Ohm",
        ref="SPK1",
        value="Mini Speaker (28mm 8Ohm 0.5W)",
        desc="28mm 8Ohm 0.5W mini speaker driven by PAM8403 BTL output (DO NOT TIE TO GND)",
        cx=R2_CX, cy=spk_cy, w=R2_W, h=spk_h,
        pins=spk_pins,
        fill_rgb=(245, 243, 255, 1.0),
        stroke_rgb=(109, 40, 217),
        extra_graphics=spk_gfx,
        ref_pos=(R2_CX, 249.40),
        val_pos=(R2_CX, 274.20),
    )
    for pin_s, sy in [("L_OUT+", 256.54), ("L_OUT-", 266.70)]:
        w = wmap[("PAM8403", pin_s)]
        connect_horizontal_wire(
            x_left=R1_RIGHT_PIN_X, x_right=R2_LEFT_PIN_X, y=sy,
            net=w.net, color=w.color, tag_text=w.wire_id, side_of_hub="right", key=w.wire_id,
        )
    # Critical BTL warning banner under PAM8403 -> Speaker
    sheet_items.append(kicad_text(
        "WARNING: BTL DIFFERENTIAL OUTPUT — NEVER TIE SPK+ OR SPK- TO GND!",
        464.82, 286.00, "txt:btl_warn",
        size=1.18, bold=True, justify="center", color=(185, 28, 28),
    ))
    sheet_items.append(kicad_text(
        "Audio path: D3(GPIO0) -> Hub C4(10uF) / R5(2.2k) / R6(2.2k) / C5(10nF) + R4(10k safe-boot) -> J12 -> PAM8403; Hub C6(100nF) on AMP_5V",
        355.60, 294.64, "txt:aud_note",
        size=1.02, color=(55, 65, 81),
    ))

    # -----------------------------------------------------------------------
    # Section Border Rectangles & Titles (matching Sheet 1 aesthetic)
    # -----------------------------------------------------------------------
    sections = [
        # (x1, y1, x2, y2, title, color_rgb)
        (20.32, 30.48, 246.38, 114.30, "1. ESP8266 NodeMCU v2 Amica (Mounted on Hub U1/U2)", (29, 78, 216)),
        (20.32, 116.84, 246.38, 147.32, "2. External 5V 2A Power Supply (J1)", (185, 28, 28)),
        (20.32, 152.40, 246.38, 261.62, "3. Real Sensors — Strictly 3.3V Domain (J13, J14, J15)", (21, 128, 61)),
        (20.32, 266.70, 246.38, 358.14, "4. Garden Pump — Relay 1 Blue 5V (J7, J8) & Submersible Pump (J2)", (3, 105, 161)),
        (347.98, 30.48, 574.04, 170.18, "5. Core Actuators — SG90 Door (J3), LEDs (J4, J5), Alarm Buzzer (J6)", (194, 65, 12)),
        (347.98, 175.26, 574.04, 302.26, "6. Audio Subsystem — Relay 2 Red Opto (J9, J10), PAM8403 (J11, J12), Mini Speaker", (109, 40, 217)),
    ]
    for idx, (x1, y1, x2, y2, title, col) in enumerate(sections):
        sheet_items.append(kicad_rect(x1, y1, x2, y2, f"sec_rect:{idx}", stroke_rgb=col))
        sheet_items.append(kicad_text(
            title, x1 + 3.0, y1 + 4.2, f"sec_title:{idx}",
            size=1.55, bold=True, justify="left", color=col,
        ))

    # Top Sheet Banner
    sheet_items.append(kicad_text(
        "SMART HOME VOICE AI — COMPLETE PLUG-IN SYSTEM WIRING HARNESS (TYPE 1 HUB PCB + ESP8266 NODEMCU + 14 OFF-BOARD MODULES, 40 WIRES W01-W40)",
        297.18, 22.86, "txt:sheet_banner",
        size=2.20, bold=True, justify="center", color=(15, 23, 42),
    ))

    # -----------------------------------------------------------------------
    # Box 7 (Right, above Title Block): Design Rules & SSOT Summary
    # -----------------------------------------------------------------------
    sheet_items.append(kicad_rect(
        347.98, 307.34, 574.04, 358.14, "sec_rect:notes",
        stroke_rgb=(51, 65, 85), fill_rgba=(248, 250, 252, 0.9),
    ))
    sheet_items.append(kicad_text(
        "7. System Wiring Contract & Safety Rules (SSOT: hardware/wiring_contract.py)",
        351.00, 311.80, "txt:notes_hdr",
        size=1.40, bold=True, color=(15, 23, 42),
    ))
    contract_bullets = [
        "- BOM / PCB Isolation: Every symbol on Sheet 2 has (on_board no) & (in_bom no). 1-Layer DIY Hub PCB (100x80mm) & bom.csv stay 100% intact.",
        "- Locked Hardware Scope: 6 Actuators (SG90 D1, Living LED D0, Bedroom LED D4, Pump/RLY1 D6, Buzzer D8, Amp/RLY2 D7+D3) + 3 Sensors.",
        "- Strictly Excluded: ZERO Fan, ZERO AC Mains, ZERO IR Blaster anywhere in schematic, PCB, firmware, or docs.",
        "- Voltage Safety: Soil LM393 (J14) & KY-037 (J15) & DHT11 (J13) strictly +3.3V; SG90/Relays/Pump/PAM8403 on +5V rail.",
        "- Unused Pins Marked NC (ERC=0): Relay 1 NC, Relay 2 NC, Soil LM393 DO, KY-037 AO.",
        "- Harness Totals: 15 Hub Connectors (J1..J15 = 36 pins) + 4 Inter-Module Wires (PAM8403->Spk, LM393->YL-69) = 40 Wires (W01..W40).",
    ]
    for i, btxt in enumerate(contract_bullets):
        sheet_items.append(kicad_text(
            btxt, 354.50, 318.20 + i * 6.00, f"txt:notes_b:{i}",
            size=1.02, color=(30, 41, 59),
        ))

    # -----------------------------------------------------------------------
    # Box 8 (Bottom Left): Wire Color Legend (10 Colors from WIRE_COLORS)
    # -----------------------------------------------------------------------
    sheet_items.append(kicad_rect(
        20.32, 363.22, 464.82, 403.86, "sec_rect:legend",
        stroke_rgb=(51, 65, 85), fill_rgba=(248, 250, 252, 0.9),
    ))
    sheet_items.append(kicad_text(
        "8. Dupont / Screw-Terminal Wire Color Standard (Consistent Across KiCad, 3D Blender, 2D SVG & WIRING_TABLE.md)",
        23.50, 367.80, "txt:legend_hdr",
        size=1.35, bold=True, color=(15, 23, 42),
    ))
    color_items = list(WIRE_COLORS.items())
    for idx, (cname, meta) in enumerate(color_items):
        col_i = idx // 5  # 2 columns x 5 rows
        row_i = idx % 5
        lx = 25.40 + col_i * 218.44
        ly = 374.65 + row_i * 5.60
        code, rgb = WIRE_COLOR_META[cname]
        # Draw a colored sample stroke bar (polyline, not electrical wire, so ERC ignores it!)
        sheet_items.append("\n".join([
            f"\t(polyline (pts (xy {fmt(lx)} {fmt(ly)}) (xy {fmt(lx + 11.43)} {fmt(ly)}))",
            f"\t\t(stroke (width 0.85) (type solid) (color {rgb[0]} {rgb[1]} {rgb[2]} 1))",
            f'\t\t(uuid "{det_uuid(f"leg_bar:{cname}")}")',
            "\t)",
        ]))
        sheet_items.append(kicad_text(
            f"[{code}] {cname}: {meta['role']}",
            lx + 13.50, ly, f"txt:leg:{cname}",
            size=1.02, bold=False, justify="left", color=(30, 41, 59),
        ))

    # -----------------------------------------------------------------------
    # Assemble Complete KiCad 10 S-Expression Schematic + Project Symbol Library
    # -----------------------------------------------------------------------
    header = f"""(kicad_sch
\t(version 20251024)
\t(generator "eeschema")
\t(generator_version "10.0")
\t(uuid "{SUBSHEET_FILE_UUID}")
\t(paper "A2")
\t(title_block
\t\t(title "SmartHome System Plug-In Wiring (All Modules)")
\t\t(date "2026-11-20")
\t\t(rev "2.0")
\t\t(company "DATN Smart Home Voice AI - SEEE HUST")
\t\t(comment 1 "Type 1 Hub PCB (J1..J15, U1/U2) + ESP8266 NodeMCU + 14 Off-Board Modules (40 Wires)")
\t\t(comment 2 "All Off-Board Symbols: (on_board no) (in_bom no) | Zero Fan, Zero AC, Zero IR")
\t)
\t(lib_symbols
"""
    sch_content = header + "\n".join(lib_symbols) + "\n\t)\n" + "\n".join(sheet_items) + "\n)\n"

    # Also build SystemWiring.kicad_sym so KiCad ERC has ZERO lib_symbol_issues warnings!
    sym_lib_entries = []
    for block in lib_symbols:
        # Remove one leading tab level and strip the "SystemWiring:" library prefix
        dedented = "\n".join(line[1:] if line.startswith("\t") else line for line in block.splitlines())
        dedented = dedented.replace('(symbol "SystemWiring:', '(symbol "', 1)
        sym_lib_entries.append(dedented)
    sym_lib_content = (
        "(kicad_symbol_lib\n"
        "\t(version 20251024)\n"
        '\t(generator "kicad_symbol_editor")\n'
        '\t(generator_version "10.0")\n'
        + "\n".join(sym_lib_entries)
        + "\n)\n"
    )
    return sch_content, sym_lib_content


def ensure_sym_lib_table_entry(table_path: Path) -> str:
    """Idempotently register the local SystemWiring.kicad_sym library in sym-lib-table."""
    orig = table_path.read_text(encoding="utf-8")
    entry = '\t(lib (name "SystemWiring") (type "KiCad") (uri "${KIPRJMOD}/SystemWiring.kicad_sym") (options "") (descr "Off-board system wiring module symbols"))'
    if '(name "SystemWiring")' in orig:
        return "present"
    close_idx = orig.rfind(")")
    if close_idx == -1:
        raise RuntimeError(f"Invalid sym-lib-table: {table_path}")
    updated = orig[:close_idx].rstrip() + "\n" + entry + "\n)\n"
    table_path.write_text(updated, encoding="utf-8", newline="\n")
    return "added"


# ---------------------------------------------------------------------------
# Idempotent Hierarchical Sub-Sheet Link in Root Schematic
# ---------------------------------------------------------------------------
def build_root_sheet_block() -> str:
    """Create the hierarchical (sheet ...) block placed in open space on Sheet 1."""
    # Open space on Sheet 1 (A3: 420x297mm):
    # H1..H4 end around x=233; Title block starts at x=300; Box 6 ends at y=248.92.
    # Place sheet block at x=241.30..294.64 (w=53.34), y=256.54..274.32 (h=17.78).
    return f"""\t(sheet
\t\t(at 241.30 256.54)
\t\t(size 53.34 17.78)
\t\t(exclude_from_sim yes)
\t\t(in_bom no)
\t\t(on_board no)
\t\t(dnp no)
\t\t(fields_autoplaced yes)
\t\t(stroke (width 0.25) (type solid) (color 22 101 52 1))
\t\t(fill (color 232 248 238 0.9))
\t\t(uuid "{SUBSHEET_BLOCK_UUID}")
\t\t(property "Sheetname" "System Plug-In Wiring Harness"
\t\t\t(at 241.30 255.60 0)
\t\t\t(effects (font (size 1.27 1.27) (bold yes)) (justify left bottom))
\t\t)
\t\t(property "Sheetfile" "system_wiring.kicad_sch"
\t\t\t(at 241.30 275.20 0)
\t\t\t(effects (font (size 1.15 1.15)) (justify left top))
\t\t)
\t\t(instances
\t\t\t(project "{PROJECT_NAME}"
\t\t\t\t(path "/{ROOT_SHEET_UUID}"
\t\t\t\t\t(page "2")
\t\t\t\t)
\t\t\t)
\t\t)
\t)"""


def _find_balanced_block(text: str, start_idx: int) -> int:
    """Given index of '(', return index right after its matching ')'."""
    depth = 0
    in_str = False
    escape = False
    for i in range(start_idx, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i + 1
    raise ValueError("Unbalanced S-expression in root schematic")


def link_subsheet_idempotent(root_sch_path: Path) -> str:
    """Insert or replace the hierarchical (sheet ...) block for system_wiring.kicad_sch."""
    orig = root_sch_path.read_text(encoding="utf-8")
    new_block = build_root_sheet_block()

    # Check if a (sheet ...) block referencing system_wiring.kicad_sch already exists
    marker = '"system_wiring.kicad_sch"'
    if marker in orig:
        m_pos = orig.index(marker)
        # Walk backwards to find the enclosing '\t(sheet\n' or '\t(sheet '
        sheet_start = orig.rfind("\t(sheet", 0, m_pos)
        if sheet_start == -1:
            raise RuntimeError("Found system_wiring.kicad_sch reference but no enclosing (sheet ...) block")
        paren_start = orig.index("(", sheet_start)
        block_end = _find_balanced_block(orig, paren_start)
        updated = orig[:sheet_start] + new_block + orig[block_end:]
        action = "replaced"
    else:
        inst_marker = "\t(sheet_instances"
        inst_pos = orig.rfind(inst_marker)
        if inst_pos == -1:
            raise RuntimeError("Could not locate (sheet_instances ...) in smarthome_hub.kicad_sch")
        updated = orig[:inst_pos] + new_block + "\n" + orig[inst_pos:]
        action = "inserted"

    # Also ensure sheet_instances includes page 2 cleanly (only if not already there)
    # Note: KiCad 10 reads page from (sheet (instances ...)); root (sheet_instances) stays clean.
    if updated != orig:
        root_sch_path.write_text(updated, encoding="utf-8", newline="\n")
    return action


def main() -> int:
    sch_content, sym_lib_content = generate_system_wiring_sch()
    SYS_SCH_PATH.write_text(sch_content, encoding="utf-8", newline="\n")
    SYS_SYM_LIB_PATH.write_text(sym_lib_content, encoding="utf-8", newline="\n")
    sym_action = ensure_sym_lib_table_entry(SYM_LIB_TABLE_PATH)
    action = link_subsheet_idempotent(ROOT_SCH_PATH)
    print(f"[OK] Generated {SYS_SCH_PATH} ({len(sch_content)} bytes)")
    print(f"[OK] Generated {SYS_SYM_LIB_PATH} ({len(sym_lib_content)} bytes, sym-lib-table: {sym_action})")
    print(f"[OK] Linked hierarchical sub-sheet in {ROOT_SCH_PATH} ({action})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
