"""Single-source-of-truth parametric specification for the Smart Home Acrylic (Mica) House (MICA2).

Pure Python (zero external dependencies) so it can be imported directly by both:
  - FreeCAD 1.1 (Python 3.11) in `build_mica.py` to build native parametric `.FCStd` solids
  - System Python in `export_drawings_and_verify.py` to generate DXFs, drawings,
    nesting layouts, documentation, and full geometric verification.

Hardware contract: 100 x 80 mm Hub PCB (90 x 70 mm M3 pattern) + 14 off-board modules
(plus 3 mm power indicator LED). Zero fan, zero AC, zero IR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any


# ---------------------------------------------------------------------------
# Global Parametric Defaults (loaded into FreeCAD Spreadsheet 'Params')
# ---------------------------------------------------------------------------
# FreeCAD's expression parser reserves single-letter 'T' as Tesla;
# alias 'T_mm' represents sheet thickness in Spreadsheet 'Params'.
PARAM_ROWS: list[tuple[str, str, str, str]] = [
    # (alias, label, formula_or_value, unit_note)
    ("T_mm", "T (Sheet Thickness mm)", "3.0", "mm — change this single cell to 2, 3, or 5 and recompute"),
    ("tab_clr", "Tab-Slot Joint Clearance", "0.25", "mm — 0.20-0.30 mm forgiving hand-cut slip fit"),
    ("slot_w", "Slot Width (= T_mm + tab_clr)", "=T_mm + tab_clr", "mm"),
    ("base_L", "Base Plate Total Length (X)", "406.0", "mm — split into P01A+P01B to fit A3 usable (410x287)"),
    ("base_W", "Base Plate Total Width (Y)", "390.0", "mm — split at Y=174 into Tech Bay (182) + House (216)"),
    ("house_L", "House Outer Length (X)", "386.0", "mm — X: 10..396"),
    ("house_D", "House Outer Depth (Y)", "190.0", "mm — Y: 192..382"),
    ("wall_H", "Full Wall Height (Z)", "147.0", "mm — +3mm base = 150.0mm total height"),
    ("cut_H", "Cutaway Low Wall Height (Z)", "34.0", "mm — open-cutaway front & side waist"),
    ("door_W", "Main Door Opening Width", "60.0", "mm — door leaf 56x100 (2.0mm clearance all sides)"),
    ("door_H", "Main Door Opening Height", "104.0", "mm"),
    ("tab_W", "House Wall Finger Tab Width", "18.0", "mm — >= 12mm hand-cut friendly"),
    ("tab_G", "Garden & Corner Tab Width", "14.0", "mm — >= 12mm hand-cut friendly"),
    ("tab_S", "Base Seam Finger Tab Width", "24.0", "mm — P01A/P01B interlocking seam"),
    ("pcb_L", "Hub PCB Length (X)", "100.0", "mm — redesigned 100x80x1.6 mm Hub PCB"),
    ("pcb_W", "Hub PCB Width (Y)", "80.0", "mm — redesigned 100x80x1.6 mm Hub PCB"),
    ("pcb_hx", "Hub PCB M3 Pattern X", "90.0", "mm — 5.0mm inset from corners"),
    ("pcb_hy", "Hub PCB M3 Pattern Y", "70.0", "mm — 5.0mm inset from corners"),
    ("pcb_margin", "PCB Mounting Plate Margin", "15.0", "mm — P16_PCB_PLATE = 130x110 mm (>= 10mm all sides)"),
    ("pcb_m3_d", "PCB / Plate / Joiner M3 Dia", "3.4", "mm — 90x70 PCB holes, P16 corner & P17 joiner M3 holes"),
    ("m3_mod_d", "Module M3 Mount Hole Dia", "3.5", "mm — M3 3.0+0.5mm (Relays, DHT11, KY-037, LM393, Speaker)"),
    ("clamp_d", "Clamp / Hinge / Linkage Dia", "3.0", "mm — PAM8403 ties, door hinges & servo linkage (>= 3.0mm)"),
    ("sg90_m2_d", "SG90 M2 Ear Screw Hole Dia", "2.5", "mm — ONLY <3mm exception: M2 2.0+0.5mm (use M2 washers)"),
    ("sg90_L", "SG90 Body Cutout Length", "23.3", "mm — 22.8mm body + 0.5mm clearance"),
    ("sg90_W", "SG90 Body Cutout Width", "12.7", "mm — 12.2mm body + 0.5mm clearance"),
    ("sg90_pitch", "SG90 M2 Hole Spacing", "27.8", "mm — datasheet mounting ear pitch"),
    ("led5_d", "5mm LED Mount Hole Dia", "5.5", "mm — 5.0 + 0.5mm (Living Room & Bedroom LEDs)"),
    ("led3_d", "3mm Power LED Hole Dia", "3.5", "mm — 3.0 + 0.5mm (Front Power Indicator)"),
    ("buzzer_d", "12mm Active Buzzer Hole Dia", "12.5", "mm — TMB12A05 12.0 + 0.5mm"),
    ("mic_d", "KY-037 Mic Aperture Dia", "10.5", "mm — 9.7mm electret capsule + 0.8mm (>= +0.5mm)"),
    ("dcjack_d", "DC-022 5V Barrel Jack Dia", "12.5", "mm — M12 barrel 12.0 + 0.5mm (fits 2/3/5mm panels)"),
    ("cable_d", "Cable Pass-Through Hole Dia", "14.0", "mm — generous Dupont bundle pass-through"),
    ("tube_d", "Silicone Water Tube Hole Dia", "10.0", "mm — 8.0mm OD pump tube + 2.0mm"),
    ("spk_hd", "Speaker Grille Hole Dia", "3.0", "mm — 19-hole concentric grille (>= 3.0mm)"),
    ("dht_w", "DHT11 Vent Cutout Width", "12.5", "mm — 12.0 + 0.5mm"),
    ("dht_h", "DHT11 Vent Cutout Height", "16.0", "mm — 15.5 + 0.5mm"),
    ("soil_slot_L", "YL-69 Soil Probe Slot Length", "22.0", "mm — 20.0 + 2.0mm"),
    ("soil_slot_W", "YL-69 Soil Probe Slot Width", "3.5", "mm — 1.6/2.5 + >=0.5mm"),
]


def default_param_values(
    T_mm: float = 3.0,
    tab_clr: float = 0.25,
    kerf: float | None = None,
) -> dict[str, float]:
    clr = float(tab_clr if kerf is None else kerf)
    vals: dict[str, float] = {}
    for alias, _lbl, val_str, _note in PARAM_ROWS:
        if alias == "T_mm":
            vals[alias] = float(T_mm)
        elif alias == "tab_clr":
            vals[alias] = clr
        elif alias == "slot_w":
            vals[alias] = float(T_mm) + clr
        else:
            vals[alias] = float(val_str)
    vals["kerf"] = clr
    return vals


def eval_expr(expr: str | float | int, params: dict[str, float]) -> float:
    """Evaluate a simple numeric or 'Params.<alias>' expression string."""
    if isinstance(expr, (int, float)):
        return float(expr)
    s = str(expr).replace("Params.", "")
    return float(eval(s, {"__builtins__": {}}, params))


def fmt_expr(val: str | float | int) -> str:
    if isinstance(val, (int, float)):
        return f"{float(val):.4f}".rstrip("0").rstrip(".") or "0"
    return str(val)


# ---------------------------------------------------------------------------
# Core Geometric Primitives (2D Local Panel Coords u, v -> 3D Extruded Solid)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RectOp:
    """Axis-aligned rectangle in panel local (u, v) coordinates [u0, u0+du] x [v0, v0+dv]."""
    name: str
    u0: str | float
    v0: str | float
    du: str | float
    dv: str | float
    kind: str = "cut"  # "add", "cut", "slot", "notch", "window", "door"
    note: str = ""
    joint_id: str = ""


@dataclass(frozen=True)
class CircleOp:
    """Circular hole in panel local (u, v) coordinates."""
    name: str
    u: str | float
    v: str | float
    dia: str | float
    kind: str = "hole"  # "m3", "clamp", "m2", "led", "buzzer", "mic", "dcjack", "cable", "tube", "grille"
    note: str = ""


@dataclass
class PanelSpec:
    panel_id: str
    name: str
    qty: int
    # Orientation of panel local (u, v, w=thickness) in 3D house coords (X, Y, Z):
    #   "XY": u->+X, v->+Y, w->+Z
    #   "XZ": u->+X, v->+Z, w->+Y
    #   "YZ": u->+Y, v->+Z, w->+X
    plane: str
    origin_xyz: tuple[str | float, str | float, str | float]
    explode_xyz: tuple[float, float, float]
    add_rects: list[RectOp] = field(default_factory=list)
    cut_rects: list[RectOp] = field(default_factory=list)
    cut_circles: list[CircleOp] = field(default_factory=list)
    outer_poly_expr: list[tuple[str | float, str | float]] = field(default_factory=list)
    notes: str = ""
    color_rgb: tuple[float, float, float] = (0.76, 0.90, 0.98)
    extra_origins_xyz: list[tuple[str | float, str | float, str | float]] = field(default_factory=list)


@dataclass(frozen=True)
class JointPair:
    joint_id: str
    tab_panel: str
    slot_panel: str
    axis: str  # "X", "Y", "Z" direction of slot length
    world_center_expr: tuple[str | float, str | float, str | float]
    tab_len_expr: str | float
    slot_len_expr: str | float
    tab_depth_expr: str | float
    slot_width_expr: str | float
    joint_kind: str = "slot"  # "slot", "notch", "seam_notch"


@dataclass(frozen=True)
class HardwarePartSpec:
    part_id: str
    name: str
    room: str
    mount_panel: str
    fasteners: str
    # World 3D bounding box center & size (X, Y, Z) at T=3 mm
    center_xyz: tuple[float, float, float]
    size_xyz: tuple[float, float, float]
    color_rgb: tuple[float, float, float]
    datasheet_dims: str
    source_name: str
    source_url: str


# ---------------------------------------------------------------------------
# Datasheet-Grounded Real Hardware Specs (Hub PCB + 14 Off-Board Modules + Power LED)
# Zero Fan, Zero AC, Zero IR
# ---------------------------------------------------------------------------
HARDWARE_PARTS: list[HardwarePartSpec] = [
    HardwarePartSpec(
        part_id="HW_PCB",
        name="Smart Home Central Hub PCB (Redesigned 100x80)",
        room="Technical Bay",
        mount_panel="P16_PCB_PLATE",
        fasteners="4x M3x10 brass standoffs on P16_PCB_PLATE (90x70 mm pattern, Dia 3.4 mm)",
        center_xyz=(122.0, 104.0, 19.8),
        size_xyz=(100.0, 80.0, 1.6),
        color_rgb=(0.08, 0.45, 0.18),
        datasheet_dims="100.0 x 80.0 x 1.6 mm; 4x M3 (3.2 mm) holes at 5 mm corner inset -> 90.0 x 70.0 mm",
        source_name="Project Fixed Spec (Hub PCB Redesign 100x80)",
        source_url="hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb",
    ),
    HardwarePartSpec(
        part_id="HW_NODEMCU",
        name="ESP8266 NodeMCU v2 Amica (CP2102)",
        room="Technical Bay",
        mount_panel="P16_PCB_PLATE (plugged into Hub PCB U1/U2 sockets)",
        fasteners="2x 1x15 female pin sockets on Hub PCB (22.86 mm row spacing); Micro-USB faces open cutaway",
        center_xyz=(122.0, 104.0, 31.0),
        size_xyz=(25.4, 48.3, 7.1),
        color_rgb=(0.10, 0.12, 0.16),
        datasheet_dims="48.26 x 25.40 x 1.60 mm PCB (49.4 mm w/ Micro-USB), 22.86 mm row spacing",
        source_name="Components101 NodeMCU ESP8266 Datasheet",
        source_url="https://components101.com/development-boards/nodemcu-esp8266-pinout-features-and-datasheet",
    ),
    HardwarePartSpec(
        part_id="HW_RELAY1",
        name="5V 1-Channel Relay Module #1 (Blue SRD-05VDC, Pump D6)",
        room="Technical Bay",
        mount_panel="P01A_BASE_TECH",
        fasteners="4x M3x8 nylon standoffs + M3 screws/nuts (Dia 3.5 mm holes at 44.5 x 20.5 mm)",
        center_xyz=(226.0, 136.0, 17.25),
        size_xyz=(50.0, 26.0, 18.5),
        color_rgb=(0.09, 0.32, 0.78),
        datasheet_dims="50.0 x 26.0 x 18.5 mm; 4x M3 (3.1 mm) holes at 44.5 x 20.5 mm",
        source_name="Reichelt / HandsOnTech 1-Ch SRD-05VDC Relay Spec",
        source_url="https://www.reichelt.com/de/en/shop/product/developer_boards_-_relay_1_channel_srd-05vdc-sl-c-371953",
    ),
    HardwarePartSpec(
        part_id="HW_RELAY2",
        name="5V 1-Channel Relay Module #2 (Red Opto, PAM8403 Power D7)",
        room="Technical Bay",
        mount_panel="P01A_BASE_TECH",
        fasteners="4x M3x8 nylon standoffs + M3 screws/nuts (Dia 3.5 mm holes at 44.5 x 20.5 mm)",
        center_xyz=(226.0, 92.0, 17.25),
        size_xyz=(50.0, 26.0, 18.5),
        color_rgb=(0.76, 0.12, 0.14),
        datasheet_dims="50.0 x 26.0 x 18.5 mm; 4x M3 (3.1 mm) holes at 44.5 x 20.5 mm",
        source_name="Electrokit SRD-05VDC Opto Relay Spec",
        source_url="https://www.electrokit.com/en/rela-srd-1-pol-vaxlande-5v",
    ),
    HardwarePartSpec(
        part_id="HW_PAM8403",
        name="PAM8403 3W Class-D Audio Amplifier Module (PWM D3)",
        room="Technical Bay",
        mount_panel="P01A_BASE_TECH",
        fasteners="2x Dia 3.0 mm nylon tie/clamp holes (26.0 mm span) + double-sided foam pad",
        center_xyz=(224.0, 52.0, 3.0),
        size_xyz=(21.0, 18.0, 3.4),
        color_rgb=(0.10, 0.56, 0.24),
        datasheet_dims="21.0 x 18.0 x 3.4 mm (bare stamp PCB, no internal screw holes)",
        source_name="Elecrow PAM8403 Datasheet",
        source_url="https://www.elecrow.com/download/PAM8403-datasheet.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_SPEAKER",
        name="Mini Round Speaker 8 Ohm 0.5 W (Dia 28 mm, PUI AS02808MR-R)",
        room="Technical Bay (Front Fascia)",
        mount_panel="P15_TECH_FASCIA",
        fasteners="2x M3x10 screws + wide nylon washers (Dia 3.5 mm holes, 36.0 mm span) behind 19-hole grille",
        center_xyz=(223.0, 15.6, 26.0),
        size_xyz=(28.0, 5.2, 28.0),
        color_rgb=(0.70, 0.72, 0.76),
        datasheet_dims="Dia 28.0 mm x 5.2 mm slim round metal-frame micro speaker (8 Ohm 0.5 W)",
        source_name="PUI Audio AS02808MR-R Datasheet",
        source_url="https://puiaudio.com/file/specs-AS02808MR-R.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_DC_JACK",
        name="DC-022 5V 2A Panel-Mount Barrel Power Jack (5.5x2.1 mm)",
        room="Technical Bay (Front Fascia)",
        mount_panel="P15_TECH_FASCIA",
        fasteners="M12 threaded barrel + hex nut through Dia 12.5 mm hole (fits 2/3/5 mm panels)",
        center_xyz=(30.0, 19.5, 22.0),
        size_xyz=(14.0, 21.0, 14.0),
        color_rgb=(0.18, 0.18, 0.20),
        datasheet_dims="M12x1.0 panel cutout Dia 12.0 mm, flange Dia 14.0 mm, rear body length 21.0 mm (5.5x2.1 mm center-positive)",
        source_name="Adafruit Product 610 / DC-022 Panel Mount 2.1mm DC Barrel Jack",
        source_url="https://www.adafruit.com/product/610",
    ),
    HardwarePartSpec(
        part_id="HW_LED_PWR",
        name="Power Indicator 3mm LED (Kingbright WP710A10)",
        room="Technical Bay (Front Fascia)",
        mount_panel="P15_TECH_FASCIA",
        fasteners="Dia 3.5 mm hole + 3mm LED bezel/clip",
        center_xyz=(57.0, 12.0, 22.0),
        size_xyz=(3.8, 5.3, 3.8),
        color_rgb=(0.14, 0.88, 0.30),
        datasheet_dims="Standard T-1 (3.0 mm lens, 3.8 mm flange, 5.3 mm height)",
        source_name="Kingbright WP710A10 Datasheet",
        source_url="http://www.kingbrightusa.com/webimages/catalog/2012-2013%20KC%20eCatalog.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_SG90",
        name="TowerPro SG90 9g Micro Servo (Main Door D1)",
        room="Living Room (Door Jamb)",
        mount_panel="P07_SERVO_SHELF",
        fasteners="2x M2x10 screws + M2 nuts + M2 washers (Dia 2.5 mm holes, 27.8 mm pitch — only <3mm exception)",
        center_xyz=(51.0, 218.1, 24.0),
        size_xyz=(12.2, 32.2, 26.0),
        color_rgb=(0.12, 0.45, 0.90),
        datasheet_dims="Body 22.8 x 12.2 x 22.5 mm; tab span 32.2 mm; M2 holes 27.8 mm apart",
        source_name="HandsOnTech TowerPro SG90 Datasheet",
        source_url="https://www.handsontec.com/dataspecs/SG90-Servo.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_BUZZER",
        name="5V Active Electromagnetic Buzzer (TMB12A05, D8)",
        room="Center Pillar (Front)",
        mount_panel="P05_WALL_FRONT",
        fasteners="Dia 12.5 mm clearance hole + silicone/hot-glue bead on rear",
        center_xyz=(200.0, 196.8, 126.0),
        size_xyz=(12.0, 9.5, 12.0),
        color_rgb=(0.12, 0.12, 0.14),
        datasheet_dims="Dia 12.0 mm x 9.5 mm body, 7.6 mm pin pitch",
        source_name="Osoyoo TMB12A05 Buzzer Datasheet",
        source_url="https://osoyoo.com/2017/05/05/buzzer-5v-breadboard-friendlytmb12a05/",
    ),
    HardwarePartSpec(
        part_id="HW_LED_LR",
        name="Living Room 5mm LED (Kingbright WP7113, D0)",
        room="Living Room",
        mount_panel="P06_WALL_MID",
        fasteners="Dia 5.5 mm hole + 5mm LED panel bezel",
        center_xyz=(197.0, 232.0, 126.0),
        size_xyz=(8.6, 5.8, 5.8),
        color_rgb=(1.00, 0.86, 0.42),
        datasheet_dims="Standard T-1 3/4 (5.0 mm dome, 5.8 mm flange, 8.6 mm height)",
        source_name="Kingbright WP7113 Datasheet",
        source_url="https://www.kingbrightusa.com/images/catalog/spec/wp7113id.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_LED_BR",
        name="Bedroom 5mm LED (Kingbright WP7113, D4)",
        room="Bedroom",
        mount_panel="P06_WALL_MID",
        fasteners="Dia 5.5 mm hole + 5mm LED panel bezel",
        center_xyz=(203.0, 258.0, 126.0),
        size_xyz=(8.6, 5.8, 5.8),
        color_rgb=(1.00, 0.78, 0.34),
        datasheet_dims="Standard T-1 3/4 (5.0 mm dome, 5.8 mm flange, 8.6 mm height)",
        source_name="Kingbright WP7113 Datasheet",
        source_url="https://www.kingbrightusa.com/images/catalog/spec/wp7113id.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_DHT11",
        name="DHT11 Temperature & Humidity 3-Pin Breakout Module (D2)",
        room="Living Room",
        mount_panel="P06_WALL_MID",
        fasteners="1x M3x8 nylon standoff + screw (Dia 3.5 mm) above 12.5 x 16.0 mm airflow vent",
        center_xyz=(195.0, 286.0, 92.0),
        size_xyz=(7.1, 14.0, 28.0),
        color_rgb=(0.14, 0.58, 0.92),
        datasheet_dims="Breakout PCB 28.0 x 14.0 x 1.6 mm; Aosong sensor 15.5 x 12.0 x 5.5 mm",
        source_name="Aosong / DFRobot DHT11 Datasheet",
        source_url="https://image.dfrobot.com/image/data/KIT0003/DHT11%20datasheet.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_KY037",
        name="KY-037 / KY-038 Sound Sensor Module (D5)",
        room="Living Room (Front Ledge)",
        mount_panel="P05_WALL_FRONT",
        fasteners="1x M3x8 nylon standoff + screw (Dia 3.5 mm); Dia 9.7 mm mic behind Dia 10.5 mm aperture",
        center_xyz=(168.0, 201.6, 26.0),
        size_xyz=(35.0, 13.1, 15.0),
        color_rgb=(0.82, 0.14, 0.16),
        datasheet_dims="PCB 35.0 x 15.0 x 1.6 mm (H 13.1 mm w/ 3296W pot); mic Dia 9.7x6.7 mm; M3 hole",
        source_name="Joy-IT KY-038 / KY-037 Datasheet",
        source_url="https://sensorkit.joy-it.net/en/sensors/ky-038",
    ),
    HardwarePartSpec(
        part_id="HW_SOIL_PROBE",
        name="YL-69 / FC-28 Soil Moisture 2-Prong Probe (A0)",
        room="Garden Planter",
        mount_panel="P14_SOIL_BRIDGE",
        fasteners="Inserted vertically through 22.0 x 3.5 mm slot in P14_SOIL_BRIDGE",
        center_xyz=(358.0, 89.0, 32.0),
        size_xyz=(1.6, 20.0, 60.0),
        color_rgb=(0.16, 0.18, 0.22),
        datasheet_dims="Fork PCB 60.0 x 20.0 x 1.6 mm (2-prong resistive probe)",
        source_name="HandsOnTech Soil Moisture Sensor Spec",
        source_url="https://handsontec.com/dataspecs/sensor/Soil%20Moisture%20Sensor.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_LM393",
        name="LM393 Soil Comparator Board (YL-38, A0)",
        room="Garden Planter (Dry Exterior Rear)",
        mount_panel="P13_GARDEN_BACK",
        fasteners="1x M3x8 nylon standoff + screw (Dia 3.5 mm) on dry exterior rear of garden back wall",
        center_xyz=(292.0, 158.0, 24.0),
        size_xyz=(32.0, 12.0, 14.0),
        color_rgb=(0.10, 0.34, 0.76),
        datasheet_dims="PCB 32.0 x 14.0 x 1.6 mm (H 12.0 mm w/ 3296W pot); 1x M3 mounting hole",
        source_name="HandsOnTech Soil Moisture Sensor Spec",
        source_url="https://handsontec.com/dataspecs/sensor/Soil%20Moisture%20Sensor.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_PUMP",
        name="3-6V DC Mini Submersible Water Pump + 6/8mm Silicone Tube",
        room="Water Reservoir",
        mount_panel="P01A_BASE_TECH / P10_WATER_DIVIDER",
        fasteners="Horizontal free-standing inside sealed water tank; OD 8.0 mm tube through Dia 10.0 mm hole",
        center_xyz=(292.0, 89.0, 16.5),
        size_xyz=(24.0, 45.0, 33.0),
        color_rgb=(0.92, 0.94, 0.96),
        datasheet_dims="Horizontal cylinder 45.0 (L) x 24.0 (Dia) x 33.0 (H) mm; nozzle OD 7.5 mm; tube OD 8.0 mm",
        source_name="Soldered / Mouser Mini Water Pump Datasheet",
        source_url="https://www.mouser.lt/datasheet/2/1398/Soldered_101844_mini_water_pump-3532437.pdf",
    ),
]


def check_hardware_clearances(min_gap_mm: float = 15.0) -> dict[str, Any]:
    """Verify 3D bounding-box wiring clearance between all non-mated hardware modules."""
    mated_pairs = {frozenset(("HW_PCB", "HW_NODEMCU"))}
    min_found = float("inf")
    min_pair = ("", "")
    violations: list[dict[str, Any]] = []
    pair_count = 0

    for i in range(len(HARDWARE_PARTS)):
        a = HARDWARE_PARTS[i]
        ax0, ay0, az0 = (a.center_xyz[k] - a.size_xyz[k] / 2.0 for k in range(3))
        ax1, ay1, az1 = (a.center_xyz[k] + a.size_xyz[k] / 2.0 for k in range(3))
        for j in range(i + 1, len(HARDWARE_PARTS)):
            b = HARDWARE_PARTS[j]
            if frozenset((a.part_id, b.part_id)) in mated_pairs:
                continue
            pair_count += 1
            bx0, by0, bz0 = (b.center_xyz[k] - b.size_xyz[k] / 2.0 for k in range(3))
            bx1, by1, bz1 = (b.center_xyz[k] + b.size_xyz[k] / 2.0 for k in range(3))
            gx = max(0.0, bx0 - ax1, ax0 - bx1)
            gy = max(0.0, by0 - ay1, ay0 - by1)
            gz = max(0.0, bz0 - az1, az0 - bz1)
            gap_cheb = max(gx, gy, gz)
            gap_euclid = math.sqrt(gx * gx + gy * gy + gz * gz)
            if gap_cheb < min_found:
                min_found = gap_cheb
                min_pair = (a.part_id, b.part_id)
            if gap_cheb < min_gap_mm - 1e-6:
                violations.append({
                    "pair": [a.part_id, b.part_id],
                    "gap_cheb_mm": round(gap_cheb, 3),
                    "gap_euclid_mm": round(gap_euclid, 3),
                    "axis_gaps": [round(gx, 3), round(gy, 3), round(gz, 3)],
                })

    return {
        "hardware_count": len(HARDWARE_PARTS),
        "checked_pairs": pair_count,
        "excluded_mated_pairs": [["HW_PCB", "HW_NODEMCU"]],
        "required_min_gap_mm": min_gap_mm,
        "measured_min_gap_mm": round(min_found, 3),
        "closest_pair": list(min_pair),
        "violations": violations,
        "passed": len(violations) == 0,
    }


# ---------------------------------------------------------------------------
# Polygon Edge Helpers (exact match with 3D Box/Cut geometry)
# ---------------------------------------------------------------------------
def _tab_edge_poly_bottom(
    u_start: float,
    u_end: float,
    tab_centers: list[float],
    tab_w: float,
    T_expr: str = "Params.T_mm",
) -> list[tuple[str | float, str | float]]:
    pts: list[tuple[str | float, str | float]] = [(u_start, 0.0)]
    for c in sorted(tab_centers):
        pts.append((c - tab_w / 2.0, 0.0))
        pts.append((c - tab_w / 2.0, f"-({T_expr})"))
        pts.append((c + tab_w / 2.0, f"-({T_expr})"))
        pts.append((c + tab_w / 2.0, 0.0))
    pts.append((u_end, 0.0))
    return pts


def _notch_edge_poly_vertical(
    u_edge: str | float,
    v_start: float,
    v_end: float,
    notch_centers: list[float],
    notch_h: float,
    inward_sign: int,  # +1 left edge (notches go +u), -1 right edge (notches go -u)
) -> list[tuple[str | float, str | float]]:
    going_up = v_end > v_start
    centers = sorted(notch_centers, reverse=not going_up)
    pts: list[tuple[str | float, str | float]] = []
    depth = "(Params.T_mm + Params.tab_clr / 2.0)"
    if inward_sign > 0:
        u_in = f"({fmt_expr(u_edge)}) + {depth}"
    else:
        u_in = f"({fmt_expr(u_edge)}) - {depth}"
    for c in centers:
        half = f"({notch_h / 2.0} + Params.tab_clr / 2.0)"
        v_a = f"{c} - {half}" if going_up else f"{c} + {half}"
        v_b = f"{c} + {half}" if going_up else f"{c} - {half}"
        pts.append((u_edge, v_a))
        pts.append((u_in, v_a))
        pts.append((u_in, v_b))
        pts.append((u_edge, v_b))
    return pts


def _tab_edge_poly_vertical(
    u_body: str | float,
    v_start: float,
    v_end: float,
    tab_centers: list[float],
    tab_h: float,
    u_tip: str | float,
) -> list[tuple[str | float, str | float]]:
    going_up = v_end > v_start
    centers = sorted(tab_centers, reverse=not going_up)
    pts: list[tuple[str | float, str | float]] = []
    for c in centers:
        v_a = c - tab_h / 2.0 if going_up else c + tab_h / 2.0
        v_b = c + tab_h / 2.0 if going_up else c - tab_h / 2.0
        pts.append((u_body, v_a))
        pts.append((u_tip, v_a))
        pts.append((u_tip, v_b))
        pts.append((u_body, v_b))
    return pts


# ---------------------------------------------------------------------------
# Parametric Builders for All 18 Unique Panels (19 Physical Pieces) & Joint Table
# ---------------------------------------------------------------------------
def build_design() -> tuple[list[PanelSpec], list[JointPair]]:
    """Build the complete parametric 18-unique-panel (19-piece) design and 1:1 joint table."""
    panels: list[PanelSpec] = []
    joints: list[JointPair] = []

    # Shared structural datum constants (world mm)
    BASE_L = 406.0
    BASE_W = 390.0
    Y_SEAM = 174.0
    SEAM_DEPTH = 8.0
    TAB_S = 24.0
    seam_tab_xs = [50.0, 150.0, 256.0, 356.0]
    joiner_xs_l = [80.0, 120.0]
    joiner_xs_r = [286.0, 326.0]

    # House outer envelope: X in [10, 396] (386), Y in [192, 382] (190), Z in [0, 147]
    X_L = 10.0
    X_R = 396.0
    HOUSE_L = X_R - X_L  # 386.0
    X_M = 200.0          # local u = 190.0 on P02 & P05
    Y_F = 192.0
    Y_B = 382.0
    HOUSE_D = Y_B - Y_F  # 190.0
    WALL_H = 147.0
    CUT_H = 34.0
    DOOR_W = 60.0
    DOOR_H = 104.0
    TAB_W = 18.0
    TAB_G = 14.0

    # Garden / Water box outer: X in [266, 396] (130), Y in [26, 152] (126)
    GX_L = 266.0
    GX_M = 318.0         # local u = 52.0 on P12 & P13
    GX_R = 396.0
    G_LEN = GX_R - GX_L  # 130.0
    GY_F = 26.0
    GY_B = 152.0
    G_DEP = GY_B - GY_F  # 126.0
    GW_H = 54.0          # Water reservoir height
    GP_H = 48.0          # Garden planter height

    # Tech Fascia: X in [8, 254] (246), Y_outer = 10.0
    TX_0 = 8.0
    TX_L = 246.0
    TY_F = 10.0

    # Tab center lists (world coordinates)
    back_base_xs = [42.0, 102.0, 162.0, 244.0, 304.0, 364.0]
    side_base_ys = [224.0, 288.0, 350.0]
    front_base_xs = [56.0, 168.0, 260.0, 354.0]
    mid_base_ys = [298.0, 350.0]
    gside_base_ys = [56.0, 122.0]
    gfb_base_xs = [292.0, 342.0, 376.0]
    fascia_base_xs = [40.0, 128.0, 223.0]

    rear_vert_zs = [26.0, 73.0, 120.0]
    front_corner_zs = [17.0]    # 14mm tall tab/notch in 34mm front cutaway
    mid_front_zs = [36.0, 82.0] # safely below Buzzer hole at Z=126
    garden_vert_zs = [24.0]     # 14mm tall tab/notch in 48-54mm garden box

    def _add_base_slot_x(
        slot_list: list[RectOp],
        base_pid: str,
        prefix: str,
        src_panel: str,
        xs: list[float],
        y_ctr: str,
        tw: float,
    ) -> None:
        for idx, xc in enumerate(xs, 1):
            jid = f"J_{src_panel}_{base_pid}_{idx}"
            slot_list.append(RectOp(
                name=f"Slot_{prefix}_{idx}",
                u0=f"{xc} - ({tw} + Params.tab_clr) / 2.0",
                v0=f"({y_ctr}) - Params.slot_w / 2.0",
                du=f"{tw} + Params.tab_clr",
                dv="Params.slot_w",
                kind="slot",
                note=f"Receives {src_panel} bottom tab #{idx}",
                joint_id=jid,
            ))
            joints.append(JointPair(
                joint_id=jid,
                tab_panel=src_panel,
                slot_panel=base_pid,
                axis="X",
                world_center_expr=(xc, y_ctr, "-(Params.T_mm / 2.0)"),
                tab_len_expr=tw,
                slot_len_expr=f"{tw} + Params.tab_clr",
                tab_depth_expr="Params.T_mm",
                slot_width_expr="Params.slot_w",
                joint_kind="slot",
            ))

    def _add_base_slot_y(
        slot_list: list[RectOp],
        base_pid: str,
        prefix: str,
        src_panel: str,
        x_ctr: str,
        ys: list[float],
        tw: float,
    ) -> None:
        for idx, yc in enumerate(ys, 1):
            jid = f"J_{src_panel}_{base_pid}_{idx}"
            slot_list.append(RectOp(
                name=f"Slot_{prefix}_{idx}",
                u0=f"({x_ctr}) - Params.slot_w / 2.0",
                v0=f"{yc} - ({tw} + Params.tab_clr) / 2.0",
                du="Params.slot_w",
                dv=f"{tw} + Params.tab_clr",
                kind="slot",
                note=f"Receives {src_panel} bottom tab #{idx}",
                joint_id=jid,
            ))
            joints.append(JointPair(
                joint_id=jid,
                tab_panel=src_panel,
                slot_panel=base_pid,
                axis="Y",
                world_center_expr=(x_ctr, yc, "-(Params.T_mm / 2.0)"),
                tab_len_expr=tw,
                slot_len_expr=f"{tw} + Params.tab_clr",
                tab_depth_expr="Params.T_mm",
                slot_width_expr="Params.slot_w",
                joint_kind="slot",
            ))

    # ------------------------------------------------------------------
    # P01A_BASE_TECH: Front Technical Bay & Garden Base (406 x 182 mm, XY at Z = -T..0)
    # ------------------------------------------------------------------
    p01a_adds: list[RectOp] = [
        RectOp("BaseTechBody", 0.0, 0.0, BASE_L, f"{Y_SEAM} - Params.tab_clr / 2.0", "add"),
    ]
    for idx, xc in enumerate(seam_tab_xs, 1):
        p01a_adds.append(RectOp(
            f"SeamTab_{idx}",
            xc - TAB_S / 2.0,
            f"{Y_SEAM} - Params.tab_clr / 2.0",
            TAB_S,
            SEAM_DEPTH,
            "add",
        ))

    p01a_cuts: list[RectOp] = []
    _add_base_slot_x(p01a_cuts, "P01A_BASE_TECH", "Fascia", "P15_TECH_FASCIA", fascia_base_xs, f"{TY_F} + Params.T_mm / 2.0", TAB_W)
    _add_base_slot_y(p01a_cuts, "P01A_BASE_TECH", "GLeft", "P09_GARDEN_LEFT", f"{GX_L} + Params.T_mm / 2.0", gside_base_ys, TAB_G)
    _add_base_slot_y(p01a_cuts, "P01A_BASE_TECH", "GDiv", "P10_WATER_DIVIDER", f"{GX_M}", gside_base_ys, TAB_G)
    _add_base_slot_y(p01a_cuts, "P01A_BASE_TECH", "GRight", "P11_GARDEN_RIGHT", f"{GX_R} - Params.T_mm / 2.0", gside_base_ys, TAB_G)
    _add_base_slot_x(p01a_cuts, "P01A_BASE_TECH", "GFront", "P12_GARDEN_FRONT", gfb_base_xs, f"{GY_F} + Params.T_mm / 2.0", TAB_G)
    _add_base_slot_x(p01a_cuts, "P01A_BASE_TECH", "GBack", "P13_GARDEN_BACK", gfb_base_xs, f"{GY_B} - Params.T_mm / 2.0", TAB_G)

    p01a_circles: list[CircleOp] = [
        # 4x M3 (3.4mm) holes for P16_PCB_PLATE corner standoffs (116x96 pitch centered at 122, 104)
        CircleOp("PLT_H1_M3", 122.0 - 58.0, 104.0 + 48.0, "Params.pcb_m3_d", "m3", "P16_PCB_PLATE corner standoff M3 #1"),
        CircleOp("PLT_H2_M3", 122.0 + 58.0, 104.0 + 48.0, "Params.pcb_m3_d", "m3", "P16_PCB_PLATE corner standoff M3 #2"),
        CircleOp("PLT_H3_M3", 122.0 - 58.0, 104.0 - 48.0, "Params.pcb_m3_d", "m3", "P16_PCB_PLATE corner standoff M3 #3"),
        CircleOp("PLT_H4_M3", 122.0 + 58.0, 104.0 - 48.0, "Params.pcb_m3_d", "m3", "P16_PCB_PLATE corner standoff M3 #4"),
        # Relay 1 (Blue, Pump) 4x M3 (3.5mm) at 44.5 x 20.5 mm centered at (226.0, 136.0)
        CircleOp("RLY1_H1_M3", 226.0 - 22.25, 136.0 + 10.25, "Params.m3_mod_d", "m3", "Relay 1 (Pump) M3 #1"),
        CircleOp("RLY1_H2_M3", 226.0 + 22.25, 136.0 + 10.25, "Params.m3_mod_d", "m3", "Relay 1 (Pump) M3 #2"),
        CircleOp("RLY1_H3_M3", 226.0 - 22.25, 136.0 - 10.25, "Params.m3_mod_d", "m3", "Relay 1 (Pump) M3 #3"),
        CircleOp("RLY1_H4_M3", 226.0 + 22.25, 136.0 - 10.25, "Params.m3_mod_d", "m3", "Relay 1 (Pump) M3 #4"),
        # Relay 2 (Red Opto, Amp) 4x M3 (3.5mm) at 44.5 x 20.5 mm centered at (226.0, 92.0)
        CircleOp("RLY2_H1_M3", 226.0 - 22.25, 92.0 + 10.25, "Params.m3_mod_d", "m3", "Relay 2 (Amp) M3 #1"),
        CircleOp("RLY2_H2_M3", 226.0 + 22.25, 92.0 + 10.25, "Params.m3_mod_d", "m3", "Relay 2 (Amp) M3 #2"),
        CircleOp("RLY2_H3_M3", 226.0 - 22.25, 92.0 - 10.25, "Params.m3_mod_d", "m3", "Relay 2 (Amp) M3 #3"),
        CircleOp("RLY2_H4_M3", 226.0 + 22.25, 92.0 - 10.25, "Params.m3_mod_d", "m3", "Relay 2 (Amp) M3 #4"),
        # PAM8403 (21 x 18 mm) 2x Dia 3.0mm clamp/zip-tie holes (26.0 mm span) centered at (224.0, 52.0)
        CircleOp("PAM_CLAMP_L", 224.0 - 13.0, 52.0, "Params.clamp_d", "clamp", "PAM8403 nylon tie/clamp left"),
        CircleOp("PAM_CLAMP_R", 224.0 + 13.0, 52.0, "Params.clamp_d", "clamp", "PAM8403 nylon tie/clamp right"),
        # 4x Joiner M3 holes (3.4mm) at Y = 166.0 matching P17_BASE_JOINER_L & R
        CircleOp("JOIN_L1_M3", joiner_xs_l[0], 166.0, "Params.pcb_m3_d", "m3", "Base seam joiner left M3 #1"),
        CircleOp("JOIN_L2_M3", joiner_xs_l[1], 166.0, "Params.pcb_m3_d", "m3", "Base seam joiner left M3 #2"),
        CircleOp("JOIN_R1_M3", joiner_xs_r[0], 166.0, "Params.pcb_m3_d", "m3", "Base seam joiner right M3 #1"),
        CircleOp("JOIN_R2_M3", joiner_xs_r[1], 166.0, "Params.pcb_m3_d", "m3", "Base seam joiner right M3 #2"),
    ]

    p01a_poly: list[tuple[str | float, str | float]] = [
        (0.0, 0.0),
        (BASE_L, 0.0),
        (BASE_L, f"{Y_SEAM} - Params.tab_clr / 2.0"),
    ]
    for xc in sorted(seam_tab_xs, reverse=True):
        p01a_poly.extend([
            (xc + TAB_S / 2.0, f"{Y_SEAM} - Params.tab_clr / 2.0"),
            (xc + TAB_S / 2.0, f"{Y_SEAM + SEAM_DEPTH} - Params.tab_clr / 2.0"),
            (xc - TAB_S / 2.0, f"{Y_SEAM + SEAM_DEPTH} - Params.tab_clr / 2.0"),
            (xc - TAB_S / 2.0, f"{Y_SEAM} - Params.tab_clr / 2.0"),
        ])
    p01a_poly.append((0.0, f"{Y_SEAM} - Params.tab_clr / 2.0"))

    panels.append(PanelSpec(
        panel_id="P01A_BASE_TECH",
        name="Base Plate Front (Tech Bay & Garden)",
        qty=1,
        plane="XY",
        origin_xyz=(0.0, 0.0, "-Params.T_mm"),
        explode_xyz=(0.0, -30.0, -48.0),
        add_rects=p01a_adds,
        cut_rects=p01a_cuts,
        cut_circles=p01a_circles,
        outer_poly_expr=p01a_poly,
        notes="Front A3-sized base half (406x182 mm): Tech Fascia, P16_PCB_PLATE standoffs, Relay1, Relay2, PAM8403, Water Tank & Garden Planter, interlocking seam tabs.",
        color_rgb=(0.66, 0.83, 0.94),
    ))

    # ------------------------------------------------------------------
    # P01B_BASE_HOUSE: Rear House Base (406 x 216 mm, XY at Z = -T..0)
    # ------------------------------------------------------------------
    p01b_adds: list[RectOp] = [
        RectOp(
            "BaseHouseBody",
            0.0,
            f"{Y_SEAM} + Params.tab_clr / 2.0",
            BASE_L,
            f"{BASE_W - Y_SEAM} - Params.tab_clr / 2.0",
            "add",
        ),
    ]
    p01b_cuts: list[RectOp] = []
    for idx, xc in enumerate(seam_tab_xs, 1):
        jid = f"J_P01A_P01B_{idx}"
        p01b_cuts.append(RectOp(
            name=f"SeamNotch_{idx}",
            u0=f"{xc} - ({TAB_S} + Params.tab_clr) / 2.0",
            v0=f"{Y_SEAM} - 1.0",
            du=f"{TAB_S} + Params.tab_clr",
            dv=f"{SEAM_DEPTH + 1.0} + Params.tab_clr / 2.0",
            kind="notch",
            note=f"Receives P01A_BASE_TECH seam finger tab #{idx}",
            joint_id=jid,
        ))
        joints.append(JointPair(
            joint_id=jid,
            tab_panel="P01A_BASE_TECH",
            slot_panel="P01B_BASE_HOUSE",
            axis="X",
            world_center_expr=(xc, Y_SEAM + SEAM_DEPTH / 2.0, "-(Params.T_mm / 2.0)"),
            tab_len_expr=TAB_S,
            slot_len_expr=f"{TAB_S} + Params.tab_clr",
            tab_depth_expr=SEAM_DEPTH,
            slot_width_expr=f"{SEAM_DEPTH} + Params.tab_clr",
            joint_kind="seam_notch",
        ))

    _add_base_slot_x(p01b_cuts, "P01B_BASE_HOUSE", "Back", "P02_WALL_BACK", back_base_xs, f"{Y_B} - Params.T_mm / 2.0", TAB_W)
    _add_base_slot_y(p01b_cuts, "P01B_BASE_HOUSE", "Left", "P03_WALL_LEFT", f"{X_L} + Params.T_mm / 2.0", side_base_ys, TAB_W)
    _add_base_slot_y(p01b_cuts, "P01B_BASE_HOUSE", "Right", "P04_WALL_RIGHT", f"{X_R} - Params.T_mm / 2.0", side_base_ys, TAB_W)
    _add_base_slot_x(p01b_cuts, "P01B_BASE_HOUSE", "Front", "P05_WALL_FRONT", front_base_xs, f"{Y_F} + Params.T_mm / 2.0", TAB_W)
    _add_base_slot_y(p01b_cuts, "P01B_BASE_HOUSE", "Mid", "P06_WALL_MID", f"{X_M}", mid_base_ys, TAB_W)

    p01b_circles: list[CircleOp] = [
        CircleOp("JOIN_L3_M3", joiner_xs_l[0], 182.0, "Params.pcb_m3_d", "m3", "Base seam joiner left M3 #3"),
        CircleOp("JOIN_L4_M3", joiner_xs_l[1], 182.0, "Params.pcb_m3_d", "m3", "Base seam joiner left M3 #4"),
        CircleOp("JOIN_R3_M3", joiner_xs_r[0], 182.0, "Params.pcb_m3_d", "m3", "Base seam joiner right M3 #3"),
        CircleOp("JOIN_R4_M3", joiner_xs_r[1], 182.0, "Params.pcb_m3_d", "m3", "Base seam joiner right M3 #4"),
    ]

    p01b_poly: list[tuple[str | float, str | float]] = [(0.0, f"{Y_SEAM} + Params.tab_clr / 2.0")]
    for xc in sorted(seam_tab_xs):
        p01b_poly.extend([
            (f"{xc} - ({TAB_S} + Params.tab_clr) / 2.0", f"{Y_SEAM} + Params.tab_clr / 2.0"),
            (f"{xc} - ({TAB_S} + Params.tab_clr) / 2.0", f"{Y_SEAM + SEAM_DEPTH} + Params.tab_clr / 2.0"),
            (f"{xc} + ({TAB_S} + Params.tab_clr) / 2.0", f"{Y_SEAM + SEAM_DEPTH} + Params.tab_clr / 2.0"),
            (f"{xc} + ({TAB_S} + Params.tab_clr) / 2.0", f"{Y_SEAM} + Params.tab_clr / 2.0"),
        ])
    p01b_poly.extend([
        (BASE_L, f"{Y_SEAM} + Params.tab_clr / 2.0"),
        (BASE_L, BASE_W),
        (0.0, BASE_W),
    ])

    panels.append(PanelSpec(
        panel_id="P01B_BASE_HOUSE",
        name="Base Plate Rear (Living & Bedroom House)",
        qty=1,
        plane="XY",
        origin_xyz=(0.0, 0.0, "-Params.T_mm"),
        explode_xyz=(0.0, 30.0, -48.0),
        add_rects=p01b_adds,
        cut_rects=p01b_cuts,
        cut_circles=p01b_circles,
        outer_poly_expr=p01b_poly,
        notes="Rear A3-sized base half (406x216 mm): Living Room & Bedroom floor with slots for P02..P06 and interlocking seam notches.",
        color_rgb=(0.70, 0.85, 0.95),
    ))

    # ------------------------------------------------------------------
    # P02_WALL_BACK: Rear Wall (386 x 147 mm + bottom tabs, XZ at Y = 382 - T)
    # ------------------------------------------------------------------
    back_local_tabs = [x - X_L for x in back_base_xs]
    p02_adds = [RectOp("BackBody", 0.0, 0.0, HOUSE_L, WALL_H, "add")]
    for idx, uc in enumerate(back_local_tabs, 1):
        p02_adds.append(RectOp(f"BackTab_{idx}", uc - TAB_W / 2.0, "-Params.T_mm", TAB_W, "Params.T_mm", "add"))

    p02_cuts: list[RectOp] = [
        RectOp("BedWindow", 228.0, 46.0, 124.0, 64.0, "window", "Bedroom panoramic window (124x64)"),
    ]
    for idx, zc in enumerate(rear_vert_zs, 1):
        jid_l = f"J_P03_P02_{idx}"
        p02_cuts.append(RectOp(
            f"NotchLeft_{idx}", -1.0, f"{zc} - ({TAB_W} + Params.tab_clr) / 2.0",
            "Params.T_mm + Params.tab_clr / 2.0 + 1.0", f"{TAB_W} + Params.tab_clr",
            "notch", f"Receives P03 rear tab #{idx}", jid_l,
        ))
        joints.append(JointPair(
            jid_l, "P03_WALL_LEFT", "P02_WALL_BACK", "Z",
            (f"{X_L} + Params.T_mm / 2.0", f"{Y_B} - Params.T_mm / 2.0", zc),
            TAB_W, f"{TAB_W} + Params.tab_clr", "Params.T_mm", "Params.T_mm + Params.tab_clr / 2.0",
            joint_kind="notch",
        ))

        jid_r = f"J_P04_P02_{idx}"
        p02_cuts.append(RectOp(
            f"NotchRight_{idx}", f"{HOUSE_L} - Params.T_mm - Params.tab_clr / 2.0", f"{zc} - ({TAB_W} + Params.tab_clr) / 2.0",
            "Params.T_mm + Params.tab_clr / 2.0 + 1.0", f"{TAB_W} + Params.tab_clr",
            "notch", f"Receives P04 rear tab #{idx}", jid_r,
        ))
        joints.append(JointPair(
            jid_r, "P04_WALL_RIGHT", "P02_WALL_BACK", "Z",
            (f"{X_R} - Params.T_mm / 2.0", f"{Y_B} - Params.T_mm / 2.0", zc),
            TAB_W, f"{TAB_W} + Params.tab_clr", "Params.T_mm", "Params.T_mm + Params.tab_clr / 2.0",
            joint_kind="notch",
        ))

        jid_m = f"J_P06_P02_{idx}"
        p02_cuts.append(RectOp(
            f"SlotMid_{idx}", "190.0 - Params.slot_w / 2.0", f"{zc} - ({TAB_W} + Params.tab_clr) / 2.0",
            "Params.slot_w", f"{TAB_W} + Params.tab_clr",
            "slot", f"Receives P06 rear tab #{idx}", jid_m,
        ))
        joints.append(JointPair(
            jid_m, "P06_WALL_MID", "P02_WALL_BACK", "Z",
            (X_M, f"{Y_B} - Params.T_mm / 2.0", zc),
            TAB_W, f"{TAB_W} + Params.tab_clr", "Params.T_mm", "Params.slot_w",
            joint_kind="slot",
        ))

    p02_circles = [
        CircleOp("Cable_Rear_LR", 34.0, 20.0, "Params.cable_d", "cable", "Living Room rear Dupont routing"),
        CircleOp("Cable_Rear_BR", 224.0, 20.0, "Params.cable_d", "cable", "Bedroom rear Dupont routing"),
    ]

    p02_poly: list[tuple[str | float, str | float]] = []
    p02_poly.extend(_tab_edge_poly_bottom(0.0, HOUSE_L, back_local_tabs, TAB_W))
    p02_poly.extend(_notch_edge_poly_vertical(HOUSE_L, 0.0, WALL_H, rear_vert_zs, TAB_W, inward_sign=-1))
    p02_poly.append((HOUSE_L, WALL_H))
    p02_poly.append((0.0, WALL_H))
    p02_poly.extend(_notch_edge_poly_vertical(0.0, WALL_H, 0.0, rear_vert_zs, TAB_W, inward_sign=+1))

    panels.append(PanelSpec(
        panel_id="P02_WALL_BACK",
        name="Rear Wall (Living + Bedroom)",
        qty=1,
        plane="XZ",
        origin_xyz=(X_L, f"{Y_B} - Params.T_mm", 0.0),
        explode_xyz=(0.0, 75.0, 0.0),
        add_rects=p02_adds,
        cut_rects=p02_cuts,
        cut_circles=p02_circles,
        outer_poly_expr=p02_poly,
        notes="Full-height rear wall (386x147) with 124x64 Bedroom window, Living/Bedroom 5mm LEDs (Dia 5.5), DHT11 vent (12.5x16.0) + M3 (Dia 3.5), Dia 14 cable holes.",
        color_rgb=(0.80, 0.92, 0.99),
    ))

    # ------------------------------------------------------------------
    # P03_WALL_LEFT & P04_WALL_RIGHT: Stepped Open-Cutaway Side Walls (190 x 147 mm)
    # ------------------------------------------------------------------
    side_local_tabs = [y - Y_F for y in side_base_ys]
    u_front_body = "Params.T_mm + Params.tab_clr / 2.0"
    u_rear_body = f"{HOUSE_D} - Params.T_mm - Params.tab_clr / 2.0"

    def _make_side_wall(
        pid: str, name: str, x_orig: str, exp_x: float, step_u: float, add_cable_hole: bool
    ) -> PanelSpec:
        adds = [
            RectOp("FrontLowBody", u_front_body, 0.0, f"{step_u} - ({u_front_body})", CUT_H, "add"),
            RectOp("RearFullBody", step_u, 0.0, f"({u_rear_body}) - {step_u}", WALL_H, "add"),
        ]
        for idx, uc in enumerate(side_local_tabs, 1):
            adds.append(RectOp(f"BotTab_{idx}", uc - TAB_W / 2.0, "-Params.T_mm", TAB_W, "Params.T_mm", "add"))
        for idx, zc in enumerate(rear_vert_zs, 1):
            adds.append(RectOp(f"RearTab_{idx}", u_rear_body, zc - TAB_W / 2.0, u_front_body, TAB_W, "add"))
        for idx, zc in enumerate(front_corner_zs, 1):
            adds.append(RectOp(f"FrontTab_{idx}", 0.0, zc - TAB_G / 2.0, u_front_body, TAB_G, "add"))

        circles: list[CircleOp] = []
        if add_cable_hole:
            circles.append(CircleOp("Cable_Left_Service", 128.0, 20.0, "Params.cable_d", "cable", "Left service Dupont pass-through"))

        poly: list[tuple[str | float, str | float]] = [(u_front_body, 0.0)]
        for c in sorted(side_local_tabs):
            poly.extend([
                (c - TAB_W / 2.0, 0.0),
                (c - TAB_W / 2.0, "-Params.T_mm"),
                (c + TAB_W / 2.0, "-Params.T_mm"),
                (c + TAB_W / 2.0, 0.0),
            ])
        poly.append((u_rear_body, 0.0))
        poly.extend(_tab_edge_poly_vertical(u_rear_body, 0.0, WALL_H, rear_vert_zs, TAB_W, HOUSE_D))
        poly.extend([
            (u_rear_body, WALL_H),
            (step_u, WALL_H),
            (step_u, CUT_H),
            (u_front_body, CUT_H),
        ])
        poly.extend(_tab_edge_poly_vertical(u_front_body, CUT_H, 0.0, front_corner_zs, TAB_G, 0.0))

        return PanelSpec(
            panel_id=pid,
            name=name,
            qty=1,
            plane="YZ",
            origin_xyz=(x_orig, Y_F, 0.0),
            explode_xyz=(exp_x, 0.0, 0.0),
            add_rects=adds,
            cut_rects=[],
            cut_circles=circles,
            outer_poly_expr=poly,
            notes=f"Open-cutaway side wall: full height {int(WALL_H)}mm rear, low {int(CUT_H)}mm cutaway front (step u={int(step_u)}mm).",
            color_rgb=(0.78, 0.91, 0.98),
        )

    panels.append(_make_side_wall("P03_WALL_LEFT", "Left Cutaway Side Wall", f"{X_L}", -80.0, 64.0, True))
    panels.append(_make_side_wall("P04_WALL_RIGHT", "Right Cutaway Side Wall", f"{X_R} - Params.T_mm", 80.0, 72.0, False))

    # ------------------------------------------------------------------
    # P05_WALL_FRONT: Front Cutaway Facade Wall (386 mm wide, XZ at Y = 192)
    # ------------------------------------------------------------------
    front_local_tabs = [x - X_L for x in front_base_xs]
    p05_adds = [
        RectOp("FrontLeftLow", 0.0, 0.0, 28.0, CUT_H, "add"),
        RectOp("DoorPortal", 28.0, 0.0, 110.0, 120.0, "add"),
        RectOp("KY037_Ledge", 138.0, 0.0, 40.0, 48.0, "add"),
        RectOp("CenterPillar", 178.0, 0.0, 26.0, WALL_H, "add"),
        RectOp("BedFrontLow", 204.0, 0.0, 182.0, CUT_H, "add"),
    ]
    for idx, uc in enumerate(front_local_tabs, 1):
        p05_adds.append(RectOp(f"FrontTab_{idx}", uc - TAB_W / 2.0, "-Params.T_mm", TAB_W, "Params.T_mm", "add"))

    p05_cuts: list[RectOp] = [
        RectOp("MainDoorOpening", 66.0, -1.0, DOOR_W, DOOR_H + 1.0, "door", "Main Door opening (60x104)"),
        RectOp(
            "NotchLeft_1", -1.0, f"17.0 - ({TAB_G} + Params.tab_clr) / 2.0",
            "Params.T_mm + Params.tab_clr / 2.0 + 1.0", f"{TAB_G} + Params.tab_clr",
            "notch", "Receives P03 front tab", "J_P03_P05_1",
        ),
        RectOp(
            "NotchRight_1", f"{HOUSE_L} - Params.T_mm - Params.tab_clr / 2.0", f"17.0 - ({TAB_G} + Params.tab_clr) / 2.0",
            "Params.T_mm + Params.tab_clr / 2.0 + 1.0", f"{TAB_G} + Params.tab_clr",
            "notch", "Receives P04 front tab", "J_P04_P05_1",
        ),
        RectOp(
            "SlotServoShelf", "41.0 - (16.0 + Params.tab_clr) / 2.0", "28.0 - Params.slot_w / 2.0",
            "16.0 + Params.tab_clr", "Params.slot_w",
            "slot", "Receives P07_SERVO_SHELF tab (16mm)", "J_P07_P05_1",
        ),
    ]
    joints.append(JointPair(
        "J_P03_P05_1", "P03_WALL_LEFT", "P05_WALL_FRONT", "Z",
        (f"{X_L} + Params.T_mm / 2.0", f"{Y_F} + Params.T_mm / 2.0", 17.0),
        TAB_G, f"{TAB_G} + Params.tab_clr", "Params.T_mm", "Params.T_mm + Params.tab_clr / 2.0",
        joint_kind="notch",
    ))
    joints.append(JointPair(
        "J_P04_P05_1", "P04_WALL_RIGHT", "P05_WALL_FRONT", "Z",
        (f"{X_R} - Params.T_mm / 2.0", f"{Y_F} + Params.T_mm / 2.0", 17.0),
        TAB_G, f"{TAB_G} + Params.tab_clr", "Params.T_mm", "Params.T_mm + Params.tab_clr / 2.0",
        joint_kind="notch",
    ))
    joints.append(JointPair(
        "J_P07_P05_1", "P07_SERVO_SHELF", "P05_WALL_FRONT", "X",
        (X_L + 41.0, f"{Y_F} + Params.T_mm / 2.0", 28.0),
        16.0, "16.0 + Params.tab_clr", "Params.T_mm", "Params.slot_w",
        joint_kind="slot",
    ))

    for idx, zc in enumerate(mid_front_zs, 1):
        jid = f"J_P06_P05_{idx}"
        p05_cuts.append(RectOp(
            f"SlotMidFront_{idx}", "190.0 - Params.slot_w / 2.0", f"{zc} - ({TAB_W} + Params.tab_clr) / 2.0",
            "Params.slot_w", f"{TAB_W} + Params.tab_clr",
            "slot", f"Receives P06 front tab #{idx}", jid,
        ))
        joints.append(JointPair(
            jid, "P06_WALL_MID", "P05_WALL_FRONT", "Z",
            (X_M, f"{Y_F} + Params.T_mm / 2.0", zc),
            TAB_W, f"{TAB_W} + Params.tab_clr", "Params.T_mm", "Params.slot_w",
            joint_kind="slot",
        ))

    p05_circles = [
        CircleOp("Buzzer_12mm", 190.0, 126.0, "Params.buzzer_d", "buzzer", "12mm Active Buzzer TMB12A05 (D8)"),
        CircleOp("KY037_Mic_Aperture", 148.0, 26.0, "Params.mic_d", "mic", "KY-037 electret mic acoustic window"),
        CircleOp("KY037_Mount_M3", 168.0, 26.0, "Params.m3_mod_d", "m3", "KY-037 PCB M3 mounting hole"),
        CircleOp("Cable_Front_LR", 16.0, 17.0, "Params.cable_d", "cable", "Tech Bay to Living Room cable pass-through"),
        CircleOp("Cable_Front_BR", 214.0, 17.0, "Params.cable_d", "cable", "Tech Bay to Bedroom/Mid-Wall cable pass-through (world X=224)"),
    ]

    p05_poly: list[tuple[str | float, str | float]] = [(0.0, 0.0)]
    # Tab 1 at u = 46.0 (before door opening [66..126])
    c1 = front_local_tabs[0]
    p05_poly.extend([
        (c1 - TAB_W / 2.0, 0.0), (c1 - TAB_W / 2.0, "-Params.T_mm"),
        (c1 + TAB_W / 2.0, "-Params.T_mm"), (c1 + TAB_W / 2.0, 0.0),
    ])
    # Main door opening [66..126] x [0..104]
    p05_poly.extend([(66.0, 0.0), (66.0, DOOR_H), (126.0, DOOR_H), (126.0, 0.0)])
    # Tabs 2..4 at u = 158, 250, 344
    for c in front_local_tabs[1:]:
        p05_poly.extend([
            (c - TAB_W / 2.0, 0.0), (c - TAB_W / 2.0, "-Params.T_mm"),
            (c + TAB_W / 2.0, "-Params.T_mm"), (c + TAB_W / 2.0, 0.0),
        ])
    p05_poly.append((HOUSE_L, 0.0))
    p05_poly.extend(_notch_edge_poly_vertical(HOUSE_L, 0.0, CUT_H, front_corner_zs, TAB_G, inward_sign=-1))
    p05_poly.extend([
        (HOUSE_L, CUT_H), (204.0, CUT_H),
        (204.0, WALL_H), (178.0, WALL_H),
        (178.0, 48.0), (138.0, 48.0),
        (138.0, 120.0), (28.0, 120.0),
        (28.0, CUT_H), (0.0, CUT_H),
    ])
    p05_poly.extend(_notch_edge_poly_vertical(0.0, CUT_H, 0.0, front_corner_zs, TAB_G, inward_sign=+1))

    panels.append(PanelSpec(
        panel_id="P05_WALL_FRONT",
        name="Front Cutaway Facade & Door Portal",
        qty=1,
        plane="XZ",
        origin_xyz=(X_L, Y_F, 0.0),
        explode_xyz=(0.0, -55.0, 0.0),
        add_rects=p05_adds,
        cut_rects=p05_cuts,
        cut_circles=p05_circles,
        outer_poly_expr=p05_poly,
        notes="Open-cutaway front facade (386x147) with 60x104 Door portal, P07 servo shelf slot, KY-037 mic+M3, Dia 12.5 Buzzer pillar, Dia 14 cable holes.",
        color_rgb=(0.76, 0.90, 0.98),
    ))

    # ------------------------------------------------------------------
    # P06_WALL_MID: Center Dividing Wall (Living/Bedroom, YZ at X = 200 - T/2)
    # Top-front corner relief [u_front_body..22.0] x [112.0..WALL_H] clears
    # HW_BUZZER (Y=192..201.6, Z=120..132) + rear Dupont pins behind P05!
    # ------------------------------------------------------------------
    mid_local_tabs = [y - Y_F for y in mid_base_ys]
    BUZZ_RELIEF_U = 22.0
    BUZZ_RELIEF_V = 112.0
    p06_adds = [
        RectOp("MidFrontLower", u_front_body, 0.0, f"{BUZZ_RELIEF_U} - ({u_front_body})", BUZZ_RELIEF_V, "add"),
        RectOp("MidMainBody", BUZZ_RELIEF_U, 0.0, f"{HOUSE_D} - {BUZZ_RELIEF_U} - Params.T_mm - Params.tab_clr / 2.0", WALL_H, "add"),
    ]
    for idx, uc in enumerate(mid_local_tabs, 1):
        p06_adds.append(RectOp(f"MidBotTab_{idx}", uc - TAB_W / 2.0, "-Params.T_mm", TAB_W, "Params.T_mm", "add"))
    for idx, zc in enumerate(rear_vert_zs, 1):
        p06_adds.append(RectOp(f"MidRearTab_{idx}", u_rear_body, zc - TAB_W / 2.0, u_front_body, TAB_W, "add"))
    for idx, zc in enumerate(mid_front_zs, 1):
        p06_adds.append(RectOp(f"MidFrontTab_{idx}", 0.0, zc - TAB_W / 2.0, u_front_body, TAB_W, "add"))

    p06_cuts = [
        RectOp("InteriorDoorway", 22.0, -1.0, 52.0, DOOR_H + 1.0, "door", "Interior Living-Bedroom doorway (52x104)"),
        RectOp(
            "DHT11_Airflow",
            "94.0 - Params.dht_w / 2.0",
            "88.0 - Params.dht_h / 2.0",
            "Params.dht_w",
            "Params.dht_h",
            "window",
            "DHT11 sensor airflow vent (12.5x16.0, relocated to P06 for <=30cm Dupont wiring)",
        ),
    ]
    p06_circles = [
        CircleOp("LED_Living_5mm", 40.0, 126.0, "Params.led5_d", "led", "Living Room 5mm LED (D0, relocated to P06 for <=30cm Dupont wiring)"),
        CircleOp("LED_Bedroom_5mm", 66.0, 126.0, "Params.led5_d", "led", "Bedroom 5mm LED (D4, relocated to P06 for <=30cm Dupont wiring)"),
        CircleOp("DHT11_Mount_M3", 94.0, 104.0, "Params.m3_mod_d", "m3", "DHT11 breakout M3 mount"),
        CircleOp("Cable_Mid_Rooms", 154.0, 20.0, "Params.cable_d", "cable", "Living Room to Bedroom cable pass-through"),
    ]

    p06_poly: list[tuple[str | float, str | float]] = [
        (u_front_body, 0.0), (22.0, 0.0), (22.0, DOOR_H), (74.0, DOOR_H), (74.0, 0.0),
    ]
    for c in sorted(mid_local_tabs):
        p06_poly.extend([
            (c - TAB_W / 2.0, 0.0), (c - TAB_W / 2.0, "-Params.T_mm"),
            (c + TAB_W / 2.0, "-Params.T_mm"), (c + TAB_W / 2.0, 0.0),
        ])
    p06_poly.append((u_rear_body, 0.0))
    p06_poly.extend(_tab_edge_poly_vertical(u_rear_body, 0.0, WALL_H, rear_vert_zs, TAB_W, HOUSE_D))
    p06_poly.extend([
        (u_rear_body, WALL_H),
        (BUZZ_RELIEF_U, WALL_H),
        (BUZZ_RELIEF_U, BUZZ_RELIEF_V),
        (u_front_body, BUZZ_RELIEF_V),
    ])
    p06_poly.extend(_tab_edge_poly_vertical(u_front_body, BUZZ_RELIEF_V, 0.0, mid_front_zs, TAB_W, 0.0))

    panels.append(PanelSpec(
        panel_id="P06_WALL_MID",
        name="Center Dividing Wall (Living/Bedroom)",
        qty=1,
        plane="YZ",
        origin_xyz=(f"{X_M} - Params.T_mm / 2.0", Y_F, 0.0),
        explode_xyz=(0.0, 0.0, 100.0),
        add_rects=p06_adds,
        cut_rects=p06_cuts,
        cut_circles=p06_circles,
        outer_poly_expr=p06_poly,
        notes="Divides Living Room & Bedroom: 52x104 doorway, Dia 14 cable hole, top-front buzzer relief step (u<22, Z>112).",
        color_rgb=(0.74, 0.89, 0.97),
    ))

    # ------------------------------------------------------------------
    # P07_SERVO_SHELF: Horizontal SG90 Door Servo Bracket (XY at Z = 28 - T/2)
    # World X in [34, 68] (34mm), World Y body starts at 192 + T + tab_clr/2 (46mm deep)
    # Front tab (16mm wide) extends across P05_WALL_FRONT to Y = 192
    # ------------------------------------------------------------------
    p07_tab_d = "Params.T_mm + Params.tab_clr / 2.0"
    p07_adds = [
        RectOp("ShelfBody", 0.0, 0.0, 34.0, 46.0, "add"),
        RectOp("ShelfTab", 9.0, f"-({p07_tab_d})", 16.0, p07_tab_d, "add"),
    ]
    p07_cuts = [
        RectOp(
            "SG90_Cutout",
            "17.0 - Params.sg90_W / 2.0",
            "23.0 - Params.sg90_L / 2.0",
            "Params.sg90_W",
            "Params.sg90_L",
            "cut",
            "SG90 servo body cutout (12.7x23.3)",
        ),
    ]
    p07_circles = [
        CircleOp("SG90_M2_Front", 17.0, "23.0 - Params.sg90_pitch / 2.0", "Params.sg90_m2_d", "m2", "SG90 M2 tab screw #1 (Dia 2.5mm, use M2 washer)"),
        CircleOp("SG90_M2_Rear", 17.0, "23.0 + Params.sg90_pitch / 2.0", "Params.sg90_m2_d", "m2", "SG90 M2 tab screw #2 (Dia 2.5mm, use M2 washer)"),
    ]
    p07_poly: list[tuple[str | float, str | float]] = [
        (0.0, 0.0), (9.0, 0.0), (9.0, f"-({p07_tab_d})"), (25.0, f"-({p07_tab_d})"), (25.0, 0.0),
        (34.0, 0.0), (34.0, 46.0), (0.0, 46.0),
    ]
    panels.append(PanelSpec(
        panel_id="P07_SERVO_SHELF",
        name="SG90 Door Servo Mount Shelf",
        qty=1,
        plane="XY",
        origin_xyz=(34.0, f"{Y_F} + Params.T_mm + Params.tab_clr / 2.0", "28.0 - Params.T_mm / 2.0"),
        explode_xyz=(-60.0, 35.0, 60.0),
        add_rects=p07_adds,
        cut_rects=p07_cuts,
        cut_circles=p07_circles,
        outer_poly_expr=p07_poly,
        notes="Slots into P05 left door jamb (16mm tab); 12.7x23.3mm SG90 cutout + 2x Dia 2.5mm M2 holes (only <3mm exception, use M2 washers).",
        color_rgb=(0.66, 0.86, 0.99),
    ))

    # ------------------------------------------------------------------
    # P08_DOOR_LEAF: Hinged Main Door Panel (56 x 100 mm, XZ at Y = 192)
    # ------------------------------------------------------------------
    p08_adds = [RectOp("DoorLeafBody", 0.0, 0.0, 56.0, 100.0, "add")]
    p08_cuts = [RectOp("DoorWindow", 15.0, 54.0, 26.0, 30.0, "window", "Main Door window cutout (26x30)")]
    p08_circles = [
        CircleOp("Door_Hinge_Bot", 5.5, 16.0, "Params.clamp_d", "clamp", "Bottom hinge Dia 3.0mm hole"),
        CircleOp("Door_Hinge_Top", 5.5, 84.0, "Params.clamp_d", "clamp", "Top hinge Dia 3.0mm hole"),
        CircleOp("Door_Servo_Link", 15.0, 28.0, "Params.clamp_d", "clamp", "SG90 servo push-rod linkage Dia 3.0mm hole"),
    ]
    p08_poly = [(0.0, 0.0), (56.0, 0.0), (56.0, 100.0), (0.0, 100.0)]
    panels.append(PanelSpec(
        panel_id="P08_DOOR_LEAF",
        name="Main Door Leaf",
        qty=1,
        plane="XZ",
        origin_xyz=(X_L + 68.0, Y_F, 2.0),
        explode_xyz=(0.0, -100.0, 20.0),
        add_rects=p08_adds,
        cut_rects=p08_cuts,
        cut_circles=p08_circles,
        outer_poly_expr=p08_poly,
        notes="Fits 60x104mm opening with 2.0mm clearance all sides; decorative 26x30mm window & 3x Dia 3.0mm hinge/linkage holes.",
        color_rgb=(0.94, 0.84, 0.68),
    ))

    # ------------------------------------------------------------------
    # P09_GARDEN_LEFT, P10_WATER_DIVIDER, P11_GARDEN_RIGHT (YZ, depth 126mm)
    # ------------------------------------------------------------------
    gside_local_tabs = [y - GY_F for y in gside_base_ys]
    g_u_front = "Params.T_mm + Params.tab_clr / 2.0"
    g_u_rear = f"{G_DEP} - Params.T_mm - Params.tab_clr / 2.0"

    def _make_garden_side(
        pid: str, name: str, x_orig: str, h: float, exp_xyz: tuple[float, float, float],
        has_tube_hole: bool = False, has_wire_notch: bool = False, notes: str = ""
    ) -> PanelSpec:
        adds = [RectOp("GSideBody", g_u_front, 0.0, f"{G_DEP} - 2.0 * Params.T_mm - Params.tab_clr", h, "add")]
        for idx, uc in enumerate(gside_local_tabs, 1):
            adds.append(RectOp(f"GBotTab_{idx}", uc - TAB_G / 2.0, "-Params.T_mm", TAB_G, "Params.T_mm", "add"))
        for idx, zc in enumerate(garden_vert_zs, 1):
            adds.append(RectOp(f"GFrontTab_{idx}", 0.0, zc - TAB_G / 2.0, g_u_front, TAB_G, "add"))
            adds.append(RectOp(f"GRearTab_{idx}", g_u_rear, zc - TAB_G / 2.0, g_u_front, TAB_G, "add"))

        cuts: list[RectOp] = []
        circles: list[CircleOp] = []
        if has_tube_hole:
            circles.append(CircleOp("Pump_Tube_Hole", 63.0, 38.0, "Params.tube_d", "tube", "Silicone pump tube pass-through (Dia 10.0mm)"))
        if has_wire_notch:
            cuts.append(RectOp("Pump_Wire_Notch", 68.0, h - 8.0, 10.0, 9.0, "notch", "Pump wire exit notch (10x8, aligned w/ pump & Hub PCB)"))

        poly: list[tuple[str | float, str | float]] = [(g_u_front, 0.0)]
        for c in sorted(gside_local_tabs):
            poly.extend([
                (c - TAB_G / 2.0, 0.0), (c - TAB_G / 2.0, "-Params.T_mm"),
                (c + TAB_G / 2.0, "-Params.T_mm"), (c + TAB_G / 2.0, 0.0),
            ])
        poly.append((g_u_rear, 0.0))
        poly.extend(_tab_edge_poly_vertical(g_u_rear, 0.0, h, garden_vert_zs, TAB_G, G_DEP))
        poly.append((g_u_rear, h))
        if has_wire_notch:
            poly.extend([(78.0, h), (78.0, h - 8.0), (68.0, h - 8.0), (68.0, h)])
        poly.append((g_u_front, h))
        poly.extend(_tab_edge_poly_vertical(g_u_front, h, 0.0, garden_vert_zs, TAB_G, 0.0))

        return PanelSpec(
            panel_id=pid,
            name=name,
            qty=1,
            plane="YZ",
            origin_xyz=(x_orig, GY_F, 0.0),
            explode_xyz=exp_xyz,
            add_rects=adds,
            cut_rects=cuts,
            cut_circles=circles,
            outer_poly_expr=poly,
            notes=notes,
            color_rgb=(0.64, 0.88, 0.96) if h == GW_H else (0.72, 0.90, 0.82),
        )

    panels.append(_make_garden_side(
        "P09_GARDEN_LEFT", "Water Tank Left Wall", f"{GX_L}", GW_H, (-25.0, -50.0, 40.0),
        has_wire_notch=True, notes="Water reservoir left wall (126x54) with 10x8mm top pump cable notch; seal inner seams with silicone.",
    ))
    panels.append(_make_garden_side(
        "P10_WATER_DIVIDER", "Water-to-Garden Divider Wall", f"{GX_M} - Params.T_mm / 2.0", GW_H, (0.0, -50.0, 50.0),
        has_tube_hole=True, notes="Separates water tank (52mm) from soil planter (78mm) with Dia 10.0mm silicone pump tube hole.",
    ))
    panels.append(_make_garden_side(
        "P11_GARDEN_RIGHT", "Garden Planter Right Wall", f"{GX_R} - Params.T_mm", GP_H, (55.0, -50.0, 40.0),
        notes="Outer right wall of garden soil planter box (126x48).",
    ))

    # ------------------------------------------------------------------
    # P12_GARDEN_FRONT & P13_GARDEN_BACK (130 mm wide, XZ at Y=26 and Y=152-T)
    # ------------------------------------------------------------------
    gfb_local_tabs = [x - GX_L for x in gfb_base_xs]

    def _make_garden_fb(pid: str, name: str, y_orig: str, exp_y: float, is_front: bool) -> PanelSpec:
        adds = [
            RectOp("WaterFace", 0.0, 0.0, 52.0, GW_H, "add"),
            RectOp("SoilFace", 52.0, 0.0, 78.0, GP_H, "add"),
        ]
        for idx, uc in enumerate(gfb_local_tabs, 1):
            adds.append(RectOp(f"GFBTab_{idx}", uc - TAB_G / 2.0, "-Params.T_mm", TAB_G, "Params.T_mm", "add"))

        y_ctr = f"{GY_F} + Params.T_mm / 2.0" if is_front else f"{GY_B} - Params.T_mm / 2.0"
        cuts = [
            RectOp(
                "NotchGLeft", -1.0, f"24.0 - ({TAB_G} + Params.tab_clr) / 2.0",
                "Params.T_mm + Params.tab_clr / 2.0 + 1.0", f"{TAB_G} + Params.tab_clr",
                "notch", "Receives P09 tab", f"J_P09_{pid}",
            ),
            RectOp(
                "SlotGDiv", "52.0 - Params.slot_w / 2.0", f"24.0 - ({TAB_G} + Params.tab_clr) / 2.0",
                "Params.slot_w", f"{TAB_G} + Params.tab_clr",
                "slot", "Receives P10 tab", f"J_P10_{pid}",
            ),
            RectOp(
                "NotchGRight", f"{G_LEN} - Params.T_mm - Params.tab_clr / 2.0", f"24.0 - ({TAB_G} + Params.tab_clr) / 2.0",
                "Params.T_mm + Params.tab_clr / 2.0 + 1.0", f"{TAB_G} + Params.tab_clr",
                "notch", "Receives P11 tab", f"J_P11_{pid}",
            ),
            RectOp(
                "NotchSoilBridge", f"92.0 - ({TAB_G} + Params.tab_clr) / 2.0", f"{GP_H} - Params.T_mm - Params.tab_clr / 2.0",
                f"{TAB_G} + Params.tab_clr", "Params.T_mm + Params.tab_clr / 2.0 + 1.0",
                "notch", "Receives P14_SOIL_BRIDGE tab (14mm)", f"J_P14_{pid}",
            ),
        ]
        joints.append(JointPair(
            f"J_P09_{pid}", "P09_GARDEN_LEFT", pid, "Z",
            (f"{GX_L} + Params.T_mm / 2.0", y_ctr, 24.0),
            TAB_G, f"{TAB_G} + Params.tab_clr", "Params.T_mm", "Params.T_mm + Params.tab_clr / 2.0",
            joint_kind="notch",
        ))
        joints.append(JointPair(
            f"J_P10_{pid}", "P10_WATER_DIVIDER", pid, "Z",
            (GX_M, y_ctr, 24.0),
            TAB_G, f"{TAB_G} + Params.tab_clr", "Params.T_mm", "Params.slot_w",
            joint_kind="slot",
        ))
        joints.append(JointPair(
            f"J_P11_{pid}", "P11_GARDEN_RIGHT", pid, "Z",
            (f"{GX_R} - Params.T_mm / 2.0", y_ctr, 24.0),
            TAB_G, f"{TAB_G} + Params.tab_clr", "Params.T_mm", "Params.T_mm + Params.tab_clr / 2.0",
            joint_kind="notch",
        ))
        joints.append(JointPair(
            f"J_P14_{pid}", "P14_SOIL_BRIDGE", pid, "X",
            (GX_L + 92.0, y_ctr, f"{GP_H} - Params.T_mm / 2.0"),
            TAB_G, f"{TAB_G} + Params.tab_clr", "Params.T_mm", "Params.T_mm + Params.tab_clr / 2.0",
            joint_kind="notch",
        ))

        circles: list[CircleOp] = []
        if not is_front:
            circles.append(CircleOp("LM393_Mount_M3", 26.0, 24.0, "Params.m3_mod_d", "m3", "LM393 soil comparator M3 dry exterior rear mount"))

        poly: list[tuple[str | float, str | float]] = []
        poly.extend(_tab_edge_poly_bottom(0.0, G_LEN, gfb_local_tabs, TAB_G))
        poly.extend(_notch_edge_poly_vertical(G_LEN, 0.0, GP_H, garden_vert_zs, TAB_G, inward_sign=-1))
        poly.extend([
            (G_LEN, GP_H),
            (f"92.0 + ({TAB_G} + Params.tab_clr) / 2.0", GP_H),
            (f"92.0 + ({TAB_G} + Params.tab_clr) / 2.0", f"{GP_H} - Params.T_mm - Params.tab_clr / 2.0"),
            (f"92.0 - ({TAB_G} + Params.tab_clr) / 2.0", f"{GP_H} - Params.T_mm - Params.tab_clr / 2.0"),
            (f"92.0 - ({TAB_G} + Params.tab_clr) / 2.0", GP_H),
            (52.0, GP_H), (52.0, GW_H), (0.0, GW_H),
        ])
        poly.extend(_notch_edge_poly_vertical(0.0, GW_H, 0.0, garden_vert_zs, TAB_G, inward_sign=+1))

        return PanelSpec(
            panel_id=pid,
            name=name,
            qty=1,
            plane="XZ",
            origin_xyz=(GX_L, y_orig, 0.0),
            explode_xyz=(35.0, exp_y, 20.0),
            add_rects=adds,
            cut_rects=cuts,
            cut_circles=circles,
            outer_poly_expr=poly,
            notes="Encloses Water Tank + Garden Planter front (130x54/48) with exterior LM393 M3 hole (Dia 3.5)." if is_front else "Encloses Water Tank + Garden Planter rear (40mm dry air gap from house front wall).",
            color_rgb=(0.68, 0.89, 0.90),
        )

    panels.append(_make_garden_fb("P12_GARDEN_FRONT", "Water & Garden Front Wall", f"{GY_F}", -90.0, True))
    panels.append(_make_garden_fb("P13_GARDEN_BACK", "Water & Garden Rear Wall", f"{GY_B} - Params.T_mm", -15.0, False))

    # ------------------------------------------------------------------
    # P14_SOIL_BRIDGE: Soil Moisture Probe Holder Bridge (XY at Z = 48 - T)
    # World X in [342, 374] (32mm), World Y in [26, 152] (126mm), 14mm tabs
    # ------------------------------------------------------------------
    p14_adds = [
        RectOp("BridgeBody", 0.0, g_u_front, 32.0, f"{G_DEP} - 2.0 * Params.T_mm - Params.tab_clr", "add"),
        RectOp("BridgeTabF", 9.0, 0.0, TAB_G, g_u_front, "add"),
        RectOp("BridgeTabB", 9.0, g_u_rear, TAB_G, g_u_front, "add"),
    ]
    p14_cuts = [
        RectOp(
            "SoilProbeSlot",
            "16.0 - Params.soil_slot_W / 2.0",
            "63.0 - Params.soil_slot_L / 2.0",
            "Params.soil_slot_W",
            "Params.soil_slot_L",
            "slot",
            "YL-69 2-prong soil probe vertical slot (22.0x3.5)",
        ),
    ]
    p14_poly: list[tuple[str | float, str | float]] = [
        (0.0, g_u_front), (9.0, g_u_front), (9.0, 0.0), (23.0, 0.0), (23.0, g_u_front),
        (32.0, g_u_front), (32.0, g_u_rear), (23.0, g_u_rear),
        (23.0, G_DEP), (9.0, G_DEP), (9.0, g_u_rear), (0.0, g_u_rear),
    ]
    panels.append(PanelSpec(
        panel_id="P14_SOIL_BRIDGE",
        name="Garden Soil Probe Holder Bridge",
        qty=1,
        plane="XY",
        origin_xyz=(342.0, GY_F, f"{GP_H} - Params.T_mm"),
        explode_xyz=(35.0, -50.0, 85.0),
        add_rects=p14_adds,
        cut_rects=p14_cuts,
        cut_circles=[],
        outer_poly_expr=p14_poly,
        notes="Slots across top of Garden Planter (14mm tabs) to hold YL-69 2-prong soil probe vertically (22.0x3.5mm slot).",
        color_rgb=(0.74, 0.92, 0.78),
    ))

    # ------------------------------------------------------------------
    # P15_TECH_FASCIA: Front Technical Bay Power & Speaker Fascia (246 mm, XZ at Y = 10)
    #   [0..56]:    H=42 (DC-022 Dia 12.5 at u=22,v=22; 3mm Power LED Dia 3.5 at u=49,v=22)
    #   [56..184]:  H=16 (Open USB service cutaway for direct NodeMCU access)
    #   [184..246]: H=48 (28mm speaker 19-hole Dia 3.0 grille @ u=215,v=26 + 2x M3 clamps @ u=197,233)
    # ------------------------------------------------------------------
    fascia_local_tabs = [x - TX_0 for x in fascia_base_xs]
    p15_adds = [
        RectOp("PowerZone", 0.0, 0.0, 56.0, 42.0, "add"),
        RectOp("USB_LowCut", 56.0, 0.0, 128.0, 16.0, "add"),
        RectOp("SpeakerBaffle", 184.0, 0.0, 62.0, 48.0, "add"),
    ]
    for idx, uc in enumerate(fascia_local_tabs, 1):
        p15_adds.append(RectOp(f"FasciaTab_{idx}", uc - TAB_W / 2.0, "-Params.T_mm", TAB_W, "Params.T_mm", "add"))

    p15_circles: list[CircleOp] = [
        CircleOp("DC022_Power_Jack", 22.0, 22.0, "Params.dcjack_d", "dcjack", "DC-022 5V 2A M12 panel-mount barrel jack (Dia 12.5mm)"),
        CircleOp("LED_Power_3mm", 49.0, 22.0, "Params.led3_d", "led", "3mm Power Indicator LED (Dia 3.5mm)"),
        CircleOp("Speaker_Clamp_L", 197.0, 26.0, "Params.m3_mod_d", "m3", "28mm Speaker M3 clamp left (Dia 3.5mm)"),
        CircleOp("Speaker_Clamp_R", 233.0, 26.0, "Params.m3_mod_d", "m3", "28mm Speaker M3 clamp right (Dia 3.5mm)"),
        CircleOp("Spk_Grille_00", 215.0, 26.0, "Params.spk_hd", "grille", "Speaker grille center (Dia 3.0mm)"),
    ]
    for k in range(6):
        ang = math.radians(k * 60.0)
        p15_circles.append(CircleOp(
            f"Spk_Grille_I{k+1}",
            round(215.0 + 6.0 * math.cos(ang), 3),
            round(26.0 + 6.0 * math.sin(ang), 3),
            "Params.spk_hd", "grille", "Speaker grille inner ring (R=6.0, Dia 3.0mm)",
        ))
    # Outer 12-hole ring offset by 15 deg so all grille-to-clamp and grille-to-grille webs >= 3.0 mm
    for k in range(12):
        ang = math.radians(k * 30.0 + 15.0)
        p15_circles.append(CircleOp(
            f"Spk_Grille_O{k+1:02d}",
            round(215.0 + 12.0 * math.cos(ang), 3),
            round(26.0 + 12.0 * math.sin(ang), 3),
            "Params.spk_hd", "grille", "Speaker grille outer ring (R=12.0, Dia 3.0mm)",
        ))

    p15_poly: list[tuple[str | float, str | float]] = []
    p15_poly.extend(_tab_edge_poly_bottom(0.0, TX_L, fascia_local_tabs, TAB_W))
    p15_poly.extend([
        (TX_L, 48.0), (184.0, 48.0),
        (184.0, 16.0), (56.0, 16.0),
        (56.0, 42.0), (0.0, 42.0),
    ])

    panels.append(PanelSpec(
        panel_id="P15_TECH_FASCIA",
        name="Tech Bay Power & Speaker Fascia",
        qty=1,
        plane="XZ",
        origin_xyz=(TX_0, TY_F, 0.0),
        explode_xyz=(-30.0, -95.0, 15.0),
        add_rects=p15_adds,
        cut_rects=[],
        cut_circles=p15_circles,
        outer_poly_expr=p15_poly,
        notes="Front technical fascia (246x48): DC-022 Dia 12.5mm power jack, 3mm Power LED, 128mm open USB service cutaway, 19-hole Dia 3.0mm speaker grille + 2x M3 clamps.",
        color_rgb=(0.70, 0.87, 0.98),
    ))

    # ------------------------------------------------------------------
    # P16_PCB_PLATE: Dedicated Hub PCB Mounting Plate (130 x 110 mm, XY at Z = 6.0..6.0+T)
    # 90 x 70 mm Hub PCB M3 pattern (Dia 3.4) with 15.0 mm free margin all 4 sides around 100x80 PCB
    # 116 x 96 mm corner M3 holes (Dia 3.4) to bolt onto P01A_BASE_TECH on 4x M3x6 standoffs
    # ------------------------------------------------------------------
    p16_adds = [RectOp("PCBPlateBody", 0.0, 0.0, 130.0, 110.0, "add")]
    p16_circles = [
        # 4x Hub PCB M3 (3.4mm) at exact 90.0 x 70.0 mm pattern
        CircleOp("PCB_H1_M3", 20.0, 20.0, "Params.pcb_m3_d", "m3", "Hub PCB M3 standoff hole #1 (90x70 pattern)"),
        CircleOp("PCB_H2_M3", 110.0, 20.0, "Params.pcb_m3_d", "m3", "Hub PCB M3 standoff hole #2 (90x70 pattern)"),
        CircleOp("PCB_H3_M3", 20.0, 90.0, "Params.pcb_m3_d", "m3", "Hub PCB M3 standoff hole #3 (90x70 pattern)"),
        CircleOp("PCB_H4_M3", 110.0, 90.0, "Params.pcb_m3_d", "m3", "Hub PCB M3 standoff hole #4 (90x70 pattern)"),
        # 4x Plate-to-Base M3 corner holes (3.4mm) at 116.0 x 96.0 mm pitch (outside 100x80 PCB)
        CircleOp("PLATE_C1_M3", 7.0, 7.0, "Params.pcb_m3_d", "m3", "Plate-to-base M3 standoff corner #1"),
        CircleOp("PLATE_C2_M3", 123.0, 7.0, "Params.pcb_m3_d", "m3", "Plate-to-base M3 standoff corner #2"),
        CircleOp("PLATE_C3_M3", 7.0, 103.0, "Params.pcb_m3_d", "m3", "Plate-to-base M3 standoff corner #3"),
        CircleOp("PLATE_C4_M3", 123.0, 103.0, "Params.pcb_m3_d", "m3", "Plate-to-base M3 standoff corner #4"),
    ]
    p16_poly = [(0.0, 0.0), (130.0, 0.0), (130.0, 110.0), (0.0, 110.0)]
    panels.append(PanelSpec(
        panel_id="P16_PCB_PLATE",
        name="Hub PCB Mounting Plate (100x80 / 90x70 M3)",
        qty=1,
        plane="XY",
        origin_xyz=(57.0, 49.0, 6.0),
        explode_xyz=(-55.0, -20.0, 75.0),
        add_rects=p16_adds,
        cut_rects=[],
        cut_circles=p16_circles,
        outer_poly_expr=p16_poly,
        notes="Removable 130x110 mm PCB mounting plate: exact 90x70 mm Dia 3.4mm M3 pattern with 15.0 mm free margin on all 4 sides around 100x80 mm Hub PCB.",
        color_rgb=(0.62, 0.88, 0.80),
    ))

    # ------------------------------------------------------------------
    # P17_BASE_JOINER (qty=2): Base Seam Reinforcement Joiner Plates (64 x 28 mm, XY at Z = -2*T..-T)
    # Bolted underneath P01A + P01B across Y_SEAM = 174 at X_ctr = 100 & 306
    # ------------------------------------------------------------------
    p17_adds = [RectOp("JoinerBody", 0.0, 0.0, 64.0, 28.0, "add")]
    p17_circles = [
        CircleOp("JOIN_H1_M3", 12.0, 6.0, "Params.pcb_m3_d", "m3", "Seam joiner M3 bolt hole #1 (to P01A)"),
        CircleOp("JOIN_H2_M3", 52.0, 6.0, "Params.pcb_m3_d", "m3", "Seam joiner M3 bolt hole #2 (to P01A)"),
        CircleOp("JOIN_H3_M3", 12.0, 22.0, "Params.pcb_m3_d", "m3", "Seam joiner M3 bolt hole #3 (to P01B)"),
        CircleOp("JOIN_H4_M3", 52.0, 22.0, "Params.pcb_m3_d", "m3", "Seam joiner M3 bolt hole #4 (to P01B)"),
    ]
    p17_poly = [(0.0, 0.0), (64.0, 0.0), (64.0, 28.0), (0.0, 28.0)]
    panels.append(PanelSpec(
        panel_id="P17_BASE_JOINER",
        name="Base Seam Joiner Plate (qty=2)",
        qty=2,
        plane="XY",
        origin_xyz=(68.0, 160.0, "-2.0 * Params.T_mm"),
        explode_xyz=(0.0, 0.0, -90.0),
        add_rects=p17_adds,
        cut_rects=[],
        cut_circles=p17_circles,
        outer_poly_expr=p17_poly,
        notes="Cut 2 pieces (64x28 mm); bolted underneath P01A+P01B seam at X=100 and X=306 with 4x M3x12 screws & nuts each.",
        color_rgb=(0.60, 0.78, 0.90),
        extra_origins_xyz=[(274.0, 160.0, "-2.0 * Params.T_mm")],
    ))

    return panels, joints


def evaluate_panel_2d(
    panel: PanelSpec,
    T_mm: float = 3.0,
    tab_clr: float = 0.25,
    kerf: float | None = None,
) -> dict[str, Any]:
    """Evaluate a panel's exact 2D outline, inner cutouts, circles, and bounding box in mm.

    Shifts local coordinates so bounding box bottom-left is exactly (0.0, 0.0)
    for laser/hand cutting and bottom/left edge datum dimensioning.
    """
    clr = float(tab_clr if kerf is None else kerf)
    p = default_param_values(T_mm=T_mm, tab_clr=clr)
    raw_outer = [(eval_expr(u, p), eval_expr(v, p)) for (u, v) in panel.outer_poly_expr]
    min_u = min(pt[0] for pt in raw_outer)
    max_u = max(pt[0] for pt in raw_outer)
    min_v = min(pt[1] for pt in raw_outer)
    max_v = max(pt[1] for pt in raw_outer)

    outer = [(round(u - min_u, 4), round(v - min_v, 4)) for (u, v) in raw_outer]

    inner_rects = []
    for r in panel.cut_rects:
        if r.kind in ("notch", "door"):
            continue
        u0 = eval_expr(r.u0, p) - min_u
        v0 = eval_expr(r.v0, p) - min_v
        du = eval_expr(r.du, p)
        dv = eval_expr(r.dv, p)
        inner_rects.append({
            "name": r.name,
            "kind": r.kind,
            "u0": round(u0, 4),
            "v0": round(v0, 4),
            "du": round(du, 4),
            "dv": round(dv, 4),
            "cx": round(u0 + du / 2.0, 4),
            "cy": round(v0 + dv / 2.0, 4),
            "note": r.note,
            "joint_id": r.joint_id,
        })

    circles = []
    for c in panel.cut_circles:
        u = eval_expr(c.u, p) - min_u
        v = eval_expr(c.v, p) - min_v
        d = eval_expr(c.dia, p)
        circles.append({
            "name": c.name,
            "kind": c.kind,
            "cx": round(u, 4),
            "cy": round(v, 4),
            "dia": round(d, 4),
            "note": c.note,
        })

    def _poly_area(pts: list[tuple[float, float]]) -> float:
        a = 0.0
        n = len(pts)
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            a += x1 * y2 - x2 * y1
        return abs(a) * 0.5

    net_area = _poly_area(outer)
    for ir in inner_rects:
        net_area -= ir["du"] * ir["dv"]
    for ci in circles:
        net_area -= math.pi * (ci["dia"] / 2.0) ** 2

    return {
        "panel_id": panel.panel_id,
        "name": panel.name,
        "qty": panel.qty,
        "T_mm": T_mm,
        "tab_clr": clr,
        "kerf": clr,
        "width": round(max_u - min_u, 4),
        "height": round(max_v - min_v, 4),
        "shift_u": round(-min_u, 4),
        "shift_v": round(-min_v, 4),
        "outer_poly": outer,
        "inner_rects": inner_rects,
        "circles": circles,
        "net_area_mm2": round(net_area, 3),
        "bbox_area_mm2": round((max_u - min_u) * (max_v - min_v), 3),
        "notes": panel.notes,
    }
