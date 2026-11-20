"""Single-source-of-truth parametric specification for the Smart Home Acrylic (Mica) House.

Pure Python (zero external dependencies) so it can be imported directly by both:
  - FreeCAD 1.1 (Python 3.11) in `build_mica.py` to build native parametric `.FCStd` solids
  - System Python 3.14 in `export_drawings_and_verify.py` to generate DXFs, drawings,
    nesting layouts, documentation, and full geometric verification.

Hardware contract: 6 devices + 3 sensors on ESP8266 NodeMCU v2 Amica + KiCad 80x65 mm hub PCB.
Zero fan, zero AC, zero IR (removed devices are permanently excluded).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any


# ---------------------------------------------------------------------------
# Global Parametric Defaults (loaded into FreeCAD Spreadsheet 'Params')
# ---------------------------------------------------------------------------
# Note: FreeCAD's expression parser reserves single-letter 'T' as Tesla;
# we use alias 'T_mm' in Spreadsheet 'Params' with label 'T (Sheet Thickness mm)'.
PARAM_ROWS: list[tuple[str, str, str, str]] = [
    # (alias, label, formula_or_value, unit_note)
    ("T_mm", "T (Sheet Thickness mm)", "3.0", "mm — change this single cell to 2, 3, or 5 and recompute"),
    ("kerf", "Slot Clearance / Laser Kerf", "0.15", "mm — added to tab thickness & width for slip fit"),
    ("slot_w", "Slot Width (= T_mm + kerf)", "=T_mm + kerf", "mm"),
    ("base_L", "Base Plate Length (X)", "380.0", "mm — fits 1x A3 sheet (420x297)"),
    ("base_W", "Base Plate Width (Y)", "286.0", "mm — fits 1x A3 sheet (420x297)"),
    ("house_L", "House Outer Length (X)", "356.0", "mm — matches Blender SCENE_SPEC.json (356)"),
    ("house_D", "House Outer Depth (Y)", "178.0", "mm — matches Blender SCENE_SPEC.json (178)"),
    ("wall_H", "Full Wall Height (Z)", "132.0", "mm — +3mm base = 135mm matches SCENE_SPEC.json"),
    ("cut_H", "Cutaway Low Wall Height (Z)", "28.0", "mm — open-cutaway front & side waist"),
    ("door_W", "Main Door Opening Width", "54.0", "mm"),
    ("door_H", "Main Door Opening Height", "96.0", "mm"),
    ("tab_W", "Standard Finger Tab Width", "15.0", "mm"),
    ("tab_G", "Garden Box Tab Width", "12.0", "mm"),
    ("m3_d", "M3 Standoff/Screw Clearance Dia", "3.2", "mm — matches KiCad H1..H4 (3.2mm)"),
    ("m25_d", "M2.5 / Zip-Tie Clamp Hole Dia", "2.7", "mm"),
    ("m2_d", "M2 Servo Screw Hole Dia", "2.0", "mm — SG90 mounting ears"),
    ("led5_d", "5mm LED Mount Hole Dia", "5.2", "mm — Living Room & Bedroom 5mm LEDs"),
    ("led3_d", "3mm Power LED Hole Dia", "3.2", "mm — Front Power Indicator"),
    ("buzzer_d", "12mm Active Buzzer Hole Dia", "12.2", "mm — TMB12A05 press-fit"),
    ("mic_d", "KY-037 Mic Acoustic Aperture Dia", "10.5", "mm — 9.6mm electret capsule"),
    ("cable_d", "Cable Pass-Through Hole Dia", "10.0", "mm — Dupont bundle routing"),
    ("tube_d", "Silicone Water Tube Hole Dia", "9.5", "mm — 7.5-8.0mm OD pump tube"),
    ("spk_hd", "Speaker Grille Hole Dia", "2.5", "mm — 19-hole concentric grille"),
    ("sg90_L", "SG90 Body Cutout Length", "23.0", "mm — 22.8mm body + 0.2mm clearance"),
    ("sg90_W", "SG90 Body Cutout Width", "12.4", "mm — 12.2mm body + 0.2mm clearance"),
    ("sg90_pitch", "SG90 M2 Hole Spacing", "27.8", "mm — datasheet tab screw pitch"),
    ("pcb_L", "KiCad Hub PCB Length", "80.0", "mm — smarthome_hub.kicad_pcb"),
    ("pcb_W", "KiCad Hub PCB Width", "65.0", "mm — smarthome_hub.kicad_pcb"),
    ("pcb_hx", "KiCad PCB Hole Spacing X", "71.0", "mm — H1..H4 exact (175.5 - 104.5)"),
    ("pcb_hy", "KiCad PCB Hole Spacing Y", "56.0", "mm — H1..H4 exact (160.5 - 104.5)"),
]


def default_param_values(T_mm: float = 3.0, kerf: float = 0.15) -> dict[str, float]:
    vals: dict[str, float] = {}
    for alias, _lbl, val_str, _note in PARAM_ROWS:
        if alias == "T_mm":
            vals[alias] = float(T_mm)
        elif alias == "kerf":
            vals[alias] = float(kerf)
        elif alias == "slot_w":
            vals[alias] = float(T_mm) + float(kerf)
        else:
            vals[alias] = float(val_str)
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
    kind: str = "hole"  # "m3", "m25", "m2", "led", "buzzer", "mic", "cable", "tube", "grille"
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
    # 2D outer contour vertices in local (u, v) using expression pairs (for clean DXF & drawings)
    outer_poly_expr: list[tuple[str | float, str | float]] = field(default_factory=list)
    notes: str = ""
    color_rgb: tuple[float, float, float] = (0.76, 0.90, 0.98)


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


@dataclass(frozen=True)
class HardwarePartSpec:
    part_id: str
    name: str
    room: str
    mount_panel: str
    fasteners: str
    # World 3D bounding box center & size (X, Y, Z) at T=3 mm for containment & 3D viz
    center_xyz: tuple[float, float, float]
    size_xyz: tuple[float, float, float]
    color_rgb: tuple[float, float, float]
    datasheet_dims: str
    source_name: str
    source_url: str


# ---------------------------------------------------------------------------
# Datasheet-Grounded Real Hardware Specs (Zero Fan, Zero AC, Zero IR)
# ---------------------------------------------------------------------------
HARDWARE_PARTS: list[HardwarePartSpec] = [
    HardwarePartSpec(
        part_id="HW_PCB",
        name="Smart Home Central Hub PCB (KiCad)",
        room="Technical Bay",
        mount_panel="P01_BASE",
        fasteners="4x M3x10 brass standoffs + 4x M3x6 screws + 4x M3 nuts",
        center_xyz=(64.0, 56.0, 10.8),
        size_xyz=(80.0, 65.0, 1.6),
        color_rgb=(0.08, 0.45, 0.18),
        datasheet_dims="80.0 x 65.0 x 1.6 mm; H1..H4 M3 (3.2 mm) at 71.0 x 56.0 mm (inset 4.5 mm)",
        source_name="Repo KiCad PCB (smarthome_hub.kicad_pcb)",
        source_url="hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb",
    ),
    HardwarePartSpec(
        part_id="HW_NODEMCU",
        name="ESP8266 NodeMCU v2 Amica (CP2102)",
        room="Technical Bay",
        mount_panel="P01_BASE (plugged into PCB U1/U2 sockets)",
        fasteners="2x 1x15 female pin sockets on Hub PCB (22.86 mm row spacing)",
        center_xyz=(64.0, 56.0, 22.0),
        size_xyz=(25.4, 48.3, 7.1),
        color_rgb=(0.10, 0.12, 0.16),
        datasheet_dims="48.26 x 25.40 x 1.60 mm PCB (49.4 mm w/ Micro-USB), 22.86 mm row spacing",
        source_name="DIMENSIONS_AUDIT.md + Components101 NodeMCU Datasheet",
        source_url="https://components101.com/development-boards/nodemcu-esp8266-pinout-features-and-datasheet",
    ),
    HardwarePartSpec(
        part_id="HW_RELAY1",
        name="5V 1-Channel Relay Module #1 (Blue, Pump)",
        room="Technical Bay",
        mount_panel="P01_BASE",
        fasteners="4x M3x8 nylon standoffs + 4x M3 screws/nuts",
        center_xyz=(140.0, 79.0, 14.0),
        size_xyz=(50.0, 26.0, 18.5),
        color_rgb=(0.09, 0.32, 0.78),
        datasheet_dims="50.0 x 26.0 x 18.5 mm; 4x M3 (3.1 mm) holes at 44.5 x 20.5 mm",
        source_name="DIMENSIONS_AUDIT.md + Reichelt/HandsOnTech 1-Ch Relay Spec",
        source_url="https://www.reichelt.com/de/en/shop/product/developer_boards_-_relay_1_channel_srd-05vdc-sl-c-371953",
    ),
    HardwarePartSpec(
        part_id="HW_RELAY2",
        name="5V 1-Channel Relay Module #2 (Red Opto, Amp)",
        room="Technical Bay",
        mount_panel="P01_BASE",
        fasteners="4x M3x8 nylon standoffs + 4x M3 screws/nuts",
        center_xyz=(140.0, 39.0, 14.0),
        size_xyz=(50.0, 26.0, 18.5),
        color_rgb=(0.76, 0.12, 0.14),
        datasheet_dims="50.0 x 26.0 x 18.5 mm; 4x M3 (3.1 mm) holes at 44.5 x 20.5 mm",
        source_name="DIMENSIONS_AUDIT.md + Electrokit SRD-05VDC Opto Relay Spec",
        source_url="https://www.electrokit.com/en/rela-srd-1-pol-vaxlande-5v",
    ),
    HardwarePartSpec(
        part_id="HW_PAM8403",
        name="PAM8403 3W Class-D Audio Amplifier Module",
        room="Technical Bay",
        mount_panel="P01_BASE",
        fasteners="2x M2.5 nylon tie/clip holes (26 mm span) + double-sided foam pad",
        center_xyz=(191.0, 39.0, 3.0),
        size_xyz=(21.0, 18.0, 3.4),
        color_rgb=(0.10, 0.56, 0.24),
        datasheet_dims="21.0 x 18.0 x 3.4 mm (bare stamp PCB, no internal screw holes)",
        source_name="DIMENSIONS_AUDIT.md + Elecrow PAM8403 Datasheet",
        source_url="https://www.elecrow.com/download/PAM8403-datasheet.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_SPEAKER",
        name="Mini Round Speaker 8 Ohm 0.5 W (Dia 28 mm, PUI AS02808MR-R)",
        room="Technical Bay",
        mount_panel="P15_TECH_FASCIA",
        fasteners="2x M3x10 screws + large nylon washers clamping Dia 28mm rim behind grille",
        center_xyz=(195.0, 14.0, 22.0),
        size_xyz=(28.0, 5.2, 28.0),
        color_rgb=(0.70, 0.72, 0.76),
        datasheet_dims="Dia 28.0 mm x 5.2 mm slim round metal-frame micro speaker (8 Ohm 0.5 W)",
        source_name="DIMENSIONS_AUDIT.md + PUI Audio AS02808MR-R Datasheet",
        source_url="https://puiaudio.com/file/specs-AS02808MR-R.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_SG90",
        name="TowerPro SG90 9g Micro Servo (Main Door)",
        room="Living Room (Door Jamb)",
        mount_panel="P07_SERVO_SHELF",
        fasteners="2x M2x8 screws + M2 nuts + M2 washers (27.8 mm pitch)",
        center_xyz=(60.0, 125.0, 20.0),
        size_xyz=(12.2, 32.2, 26.0),
        color_rgb=(0.12, 0.45, 0.90),
        datasheet_dims="Body 22.8 x 12.2 x 22.5 mm; tab span 32.2 mm; M2 holes 27.8 mm apart",
        source_name="DIMENSIONS_AUDIT.md + HandsOnTech SG90 Datasheet",
        source_url="https://www.handsontec.com/dataspecs/SG90-Servo.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_BUZZER",
        name="5V Active Electromagnetic Buzzer (TMB12A05)",
        room="Center Pillar (Front)",
        mount_panel="P05_WALL_FRONT",
        fasteners="Dia 12.2 mm press-fit hole + drop of hot glue / silicone on rear",
        center_xyz=(185.0, 108.0, 114.0),
        size_xyz=(12.0, 9.5, 12.0),
        color_rgb=(0.12, 0.12, 0.14),
        datasheet_dims="Dia 12.0 mm x 9.5 mm body, 7.6 mm pin pitch",
        source_name="DIMENSIONS_AUDIT.md + Osoyoo TMB12A05 Datasheet",
        source_url="https://osoyoo.com/2017/05/05/buzzer-5v-breadboard-friendlytmb12a05/",
    ),
    HardwarePartSpec(
        part_id="HW_LED_LR",
        name="Living Room 5mm LED (Kingbright WP7113)",
        room="Living Room",
        mount_panel="P02_WALL_BACK",
        fasteners="Dia 5.2 mm press-fit / 5mm LED panel bezel",
        center_xyz=(95.0, 272.7, 112.0),
        size_xyz=(5.8, 8.6, 5.8),
        color_rgb=(1.00, 0.86, 0.42),
        datasheet_dims="Standard T-1 3/4 (5.0 mm dome, 5.8 mm flange, 8.6 mm height)",
        source_name="DIMENSIONS_AUDIT.md + Kingbright WP7113 Datasheet",
        source_url="https://www.kingbrightusa.com/images/catalog/spec/wp7113id.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_LED_BR",
        name="Bedroom 5mm LED (Kingbright WP7113)",
        room="Bedroom",
        mount_panel="P02_WALL_BACK",
        fasteners="Dia 5.2 mm press-fit / 5mm LED panel bezel",
        center_xyz=(278.0, 272.7, 118.0),
        size_xyz=(5.8, 8.6, 5.8),
        color_rgb=(1.00, 0.78, 0.34),
        datasheet_dims="Standard T-1 3/4 (5.0 mm dome, 5.8 mm flange, 8.6 mm height)",
        source_name="DIMENSIONS_AUDIT.md + Kingbright WP7113 Datasheet",
        source_url="https://www.kingbrightusa.com/images/catalog/spec/wp7113id.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_LED_PWR",
        name="Power Indicator 3mm LED (Kingbright WP710A10)",
        room="Technical Bay (Front Fascia)",
        mount_panel="P15_TECH_FASCIA",
        fasteners="Dia 3.2 mm press-fit / 3mm LED clip",
        center_xyz=(43.0, 11.0, 14.0),
        size_xyz=(3.8, 5.3, 3.8),
        color_rgb=(0.14, 0.88, 0.30),
        datasheet_dims="Standard T-1 (3.0 mm lens, 3.8 mm flange, 5.3 mm height)",
        source_name="DIMENSIONS_AUDIT.md + Kingbright WP710A10 Datasheet",
        source_url="http://www.kingbrightusa.com/webimages/catalog/2012-2013%20KC%20eCatalog.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_DHT11",
        name="DHT11 Temperature & Humidity 3-Pin Breakout Module",
        room="Living Room",
        mount_panel="P02_WALL_BACK",
        fasteners="1x M3x8 nylon standoff + screw above 12x14 mm airflow window",
        center_xyz=(148.0, 272.0, 86.0),
        size_xyz=(14.0, 7.1, 28.0),
        color_rgb=(0.14, 0.58, 0.92),
        datasheet_dims="Breakout PCB 28.0 x 14.0 x 1.6 mm; Aosong sensor 15.5 x 12.0 x 5.5 mm",
        source_name="DIMENSIONS_AUDIT.md + Aosong/DFRobot DHT11 Datasheet",
        source_url="https://image.dfrobot.com/image/data/KIT0003/DHT11%20datasheet.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_KY037",
        name="KY-037 / KY-038 Sound Sensor Module",
        room="Living Room (Front Ledge)",
        mount_panel="P05_WALL_FRONT",
        fasteners="1x M3x8 nylon standoff + screw; Dia 9.7mm mic aligned with Dia 10.5mm aperture",
        center_xyz=(158.0, 111.0, 24.0),
        size_xyz=(35.0, 13.1, 15.0),
        color_rgb=(0.82, 0.14, 0.16),
        datasheet_dims="PCB 35.0 x 15.0 x 1.6 mm (H 13.1 mm w/ 3296W pot); mic Dia 9.7x6.7 mm; M3 hole",
        source_name="DIMENSIONS_AUDIT.md + Joy-IT KY-038 Datasheet",
        source_url="https://sensorkit.joy-it.net/en/sensors/ky-038",
    ),
    HardwarePartSpec(
        part_id="HW_SOIL_PROBE",
        name="YL-69 / FC-28 Soil Moisture 2-Prong Probe",
        room="Garden Planter",
        mount_panel="P14_SOIL_BRIDGE",
        fasteners="Inserted vertically through 22.0 x 3.2 mm slot in soil bridge",
        center_xyz=(320.0, 55.0, 26.0),
        size_xyz=(1.6, 20.0, 60.0),
        color_rgb=(0.16, 0.18, 0.22),
        datasheet_dims="Fork PCB 60.0 x 20.0 x 1.6 mm (2-prong resistive probe)",
        source_name="DIMENSIONS_AUDIT.md + HandsOnTech Soil Moisture Spec",
        source_url="https://handsontec.com/dataspecs/sensor/Soil%20Moisture%20Sensor.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_LM393",
        name="LM393 Soil Comparator Board (YL-38)",
        room="Garden Planter (Dry Exterior)",
        mount_panel="P12_GARDEN_FRONT",
        fasteners="1x M3x8 nylon standoff + screw on dry exterior of planter front wall",
        center_xyz=(304.0, 12.0, 18.0),
        size_xyz=(32.0, 12.0, 14.0),
        color_rgb=(0.10, 0.34, 0.76),
        datasheet_dims="PCB 32.0 x 14.0 x 1.6 mm (H 12.0 mm w/ 3296W pot); 1x M3 mounting hole",
        source_name="DIMENSIONS_AUDIT.md + HandsOnTech Soil Moisture Spec",
        source_url="https://handsontec.com/dataspecs/sensor/Soil%20Moisture%20Sensor.pdf",
    ),
    HardwarePartSpec(
        part_id="HW_PUMP",
        name="3-6V DC Mini Submersible Water Pump + 6/8mm Tube",
        room="Water Reservoir",
        mount_panel="P01_BASE / P10_WATER_DIVIDER",
        fasteners="Horizontal free-standing inside sealed water box; OD 8.0mm tube through Dia 9.5mm hole",
        center_xyz=(254.0, 55.0, 16.5),
        size_xyz=(24.0, 45.0, 33.0),
        color_rgb=(0.92, 0.94, 0.96),
        datasheet_dims="Horizontal cylinder 45.0 (L) x 24.0 (Dia) x 33.0 (H) mm; nozzle OD 7.5 mm; tube OD 8.0 mm",
        source_name="DIMENSIONS_AUDIT.md + Soldered/Mouser Mini Water Pump Datasheet",
        source_url="https://www.mouser.lt/datasheet/2/1398/Soldered_101844_mini_water_pump-3532437.pdf",
    ),
]


# ---------------------------------------------------------------------------
# Parametric Builders for All 15 Acrylic Panels & All Tab-Slot Joint Pairs
# ---------------------------------------------------------------------------
def _tab_edge_poly_bottom(
    u_start: float,
    u_end: float,
    tab_centers: list[float],
    tab_w: float,
    T_expr: str = "Params.T_mm",
) -> list[tuple[str | float, str | float]]:
    """Build bottom-edge polygon points (from u_start to u_end at v=0 with downward tabs to v=-T_mm)."""
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
    inward_sign: int,  # +1 for left edge (notches go +u), -1 for right edge (notches go -u)
) -> list[tuple[str | float, str | float]]:
    """Return intermediate vertices along a vertical edge from v_start to v_end with rectangular notches."""
    going_up = v_end > v_start
    centers = sorted(notch_centers, reverse=not going_up)
    pts: list[tuple[str | float, str | float]] = []
    if inward_sign > 0:
        u_in = f"({fmt_expr(u_edge)}) + Params.T_mm"
    else:
        u_in = f"({fmt_expr(u_edge)}) - Params.T_mm"
    for c in centers:
        half = f"({notch_h / 2.0} + Params.kerf / 2.0)"
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
    outward_sign: int,  # -1 for left edge (tabs go -u by T), +1 for right edge (tabs go +u by T)
) -> list[tuple[str | float, str | float]]:
    """Return intermediate vertices along a vertical edge from v_start to v_end with outward tabs."""
    going_up = v_end > v_start
    centers = sorted(tab_centers, reverse=not going_up)
    pts: list[tuple[str | float, str | float]] = []
    if outward_sign > 0:
        u_out = f"({fmt_expr(u_body)}) + Params.T_mm"
    else:
        u_out = f"({fmt_expr(u_body)}) - Params.T_mm"
    for c in centers:
        v_a = c - tab_h / 2.0 if going_up else c + tab_h / 2.0
        v_b = c + tab_h / 2.0 if going_up else c - tab_h / 2.0
        pts.append((u_body, v_a))
        pts.append((u_out, v_a))
        pts.append((u_out, v_b))
        pts.append((u_body, v_b))
    return pts


def build_design() -> tuple[list[PanelSpec], list[JointPair]]:
    """Build the complete parametric 15-panel design and its 1:1 joint pairing table."""
    panels: list[PanelSpec] = []
    joints: list[JointPair] = []

    # Shared structural datum constants (world mm)
    # Base: X in [0, 380], Y in [0, 286], Z in [-T, 0]
    # House outer: X in [12, 368] (356), Y in [102, 280] (178), Z in [0, 132] (+T=135)
    X_L = 12.0
    X_R = 368.0
    X_M = 185.0  # local 173.0 on Back/Front walls
    Y_F = 102.0
    Y_B = 280.0
    WALL_H = 132.0
    CUT_H = 28.0
    TAB_W = 15.0
    TAB_G = 12.0

    # Garden / Water box outer: X in [230, 364] (134), Y in [18, 92] (74)
    GX_L = 230.0
    GX_M = 278.0  # Divider between Water Reservoir (left 48mm) and Soil Planter (right 86mm)
    GX_R = 364.0
    GY_F = 18.0
    GY_B = 92.0
    GW_H = 44.0  # Water reservoir height
    GP_H = 40.0  # Garden planter height

    # Tech Fascia: X in [14, 224] (210), Y_outer = 8.0
    TX_0 = 14.0
    TX_L = 210.0
    TY_F = 8.0

    # Tab center lists (world coordinates)
    back_base_xs = [34.0, 88.0, 146.0, 224.0, 282.0, 340.0]
    side_base_ys = [130.0, 190.0, 250.0]
    front_base_xs = [38.0, 152.0, 232.0, 328.0]
    mid_base_ys = [202.0, 248.0]
    gside_base_ys = [38.0, 72.0]
    gfb_base_xs = [254.0, 304.0, 342.0]
    fascia_base_xs = [38.0, 118.0, 196.0]

    rear_vert_zs = [22.0, 62.0, 102.0]
    front_corner_zs = [14.0]  # 10mm tall tab/notch in 28mm front cutaway
    mid_front_zs = [34.0, 72.0]  # safely below Buzzer hole at Z=114
    garden_vert_zs = [20.0]  # 14mm tall tab/notch in 40-44mm garden box

    # ------------------------------------------------------------------
    # P01_BASE: Main Base Plate (380 x 286 mm, XY plane at Z = -T..0)
    # ------------------------------------------------------------------
    p01_cuts: list[RectOp] = []

    def _add_base_slot_x(prefix: str, src_panel: str, xs: list[float], y_ctr: str, tw: float) -> None:
        for idx, xc in enumerate(xs, 1):
            jid = f"J_{src_panel}_BASE_{idx}"
            p01_cuts.append(RectOp(
                name=f"Slot_{prefix}_{idx}",
                u0=f"{xc} - ({tw} + Params.kerf) / 2.0",
                v0=f"({y_ctr}) - Params.slot_w / 2.0",
                du=f"{tw} + Params.kerf",
                dv="Params.slot_w",
                kind="slot",
                note=f"Receives {src_panel} bottom tab #{idx}",
                joint_id=jid,
            ))
            joints.append(JointPair(
                joint_id=jid,
                tab_panel=src_panel,
                slot_panel="P01_BASE",
                axis="X",
                world_center_expr=(xc, y_ctr, "-(Params.T_mm / 2.0)"),
                tab_len_expr=tw,
                slot_len_expr=f"{tw} + Params.kerf",
                tab_depth_expr="Params.T_mm",
                slot_width_expr="Params.slot_w",
            ))

    def _add_base_slot_y(prefix: str, src_panel: str, x_ctr: str, ys: list[float], tw: float) -> None:
        for idx, yc in enumerate(ys, 1):
            jid = f"J_{src_panel}_BASE_{idx}"
            p01_cuts.append(RectOp(
                name=f"Slot_{prefix}_{idx}",
                u0=f"({x_ctr}) - Params.slot_w / 2.0",
                v0=f"{yc} - ({tw} + Params.kerf) / 2.0",
                du="Params.slot_w",
                dv=f"{tw} + Params.kerf",
                kind="slot",
                note=f"Receives {src_panel} bottom tab #{idx}",
                joint_id=jid,
            ))
            joints.append(JointPair(
                joint_id=jid,
                tab_panel=src_panel,
                slot_panel="P01_BASE",
                axis="Y",
                world_center_expr=(x_ctr, yc, "-(Params.T_mm / 2.0)"),
                tab_len_expr=tw,
                slot_len_expr=f"{tw} + Params.kerf",
                tab_depth_expr="Params.T_mm",
                slot_width_expr="Params.slot_w",
            ))

    _add_base_slot_x("Back", "P02_WALL_BACK", back_base_xs, f"{Y_B} - Params.T_mm / 2.0", TAB_W)
    _add_base_slot_y("Left", "P03_WALL_LEFT", f"{X_L} + Params.T_mm / 2.0", side_base_ys, TAB_W)
    _add_base_slot_y("Right", "P04_WALL_RIGHT", f"{X_R} - Params.T_mm / 2.0", side_base_ys, TAB_W)
    _add_base_slot_x("Front", "P05_WALL_FRONT", front_base_xs, f"{Y_F} + Params.T_mm / 2.0", TAB_W)
    _add_base_slot_y("Mid", "P06_WALL_MID", f"{X_M}", mid_base_ys, TAB_W)
    _add_base_slot_y("GLeft", "P09_GARDEN_LEFT", f"{GX_L} + Params.T_mm / 2.0", gside_base_ys, TAB_G)
    _add_base_slot_y("GDiv", "P10_WATER_DIVIDER", f"{GX_M}", gside_base_ys, TAB_G)
    _add_base_slot_y("GRight", "P11_GARDEN_RIGHT", f"{GX_R} - Params.T_mm / 2.0", gside_base_ys, TAB_G)
    _add_base_slot_x("GFront", "P12_GARDEN_FRONT", gfb_base_xs, f"{GY_F} + Params.T_mm / 2.0", TAB_G)
    _add_base_slot_x("GBack", "P13_GARDEN_BACK", gfb_base_xs, f"{GY_B} - Params.T_mm / 2.0", TAB_G)
    _add_base_slot_x("Fascia", "P15_TECH_FASCIA", fascia_base_xs, f"{TY_F} + Params.T_mm / 2.0", TAB_W)

    # Exact KiCad PCB H1..H4 mounting holes (71.0 x 56.0 mm, Dia 3.2 mm) centered at (64.0, 56.0)
    p01_circles: list[CircleOp] = [
        CircleOp("PCB_H1_M3", 64.0 - 35.5, 56.0 + 28.0, "Params.m3_d", "m3", "KiCad Hub PCB H1 (M3 standoff)"),
        CircleOp("PCB_H2_M3", 64.0 + 35.5, 56.0 + 28.0, "Params.m3_d", "m3", "KiCad Hub PCB H2 (M3 standoff)"),
        CircleOp("PCB_H3_M3", 64.0 - 35.5, 56.0 - 28.0, "Params.m3_d", "m3", "KiCad Hub PCB H3 (M3 standoff)"),
        CircleOp("PCB_H4_M3", 64.0 + 35.5, 56.0 - 28.0, "Params.m3_d", "m3", "KiCad Hub PCB H4 (M3 standoff)"),
        # Relay 1 (Blue, Pump) 4x M3 at 44.5 x 20.5 mm centered at (140.0, 79.0)
        CircleOp("RLY1_H1_M3", 140.0 - 22.25, 79.0 + 10.25, "Params.m3_d", "m3", "Relay 1 (Pump) M3 #1"),
        CircleOp("RLY1_H2_M3", 140.0 + 22.25, 79.0 + 10.25, "Params.m3_d", "m3", "Relay 1 (Pump) M3 #2"),
        CircleOp("RLY1_H3_M3", 140.0 - 22.25, 79.0 - 10.25, "Params.m3_d", "m3", "Relay 1 (Pump) M3 #3"),
        CircleOp("RLY1_H4_M3", 140.0 + 22.25, 79.0 - 10.25, "Params.m3_d", "m3", "Relay 1 (Pump) M3 #4"),
        # Relay 2 (Red Opto, Speaker Amp) 4x M3 at 44.5 x 20.5 mm centered at (140.0, 39.0)
        CircleOp("RLY2_H1_M3", 140.0 - 22.25, 39.0 + 10.25, "Params.m3_d", "m3", "Relay 2 (Amp) M3 #1"),
        CircleOp("RLY2_H2_M3", 140.0 + 22.25, 39.0 + 10.25, "Params.m3_d", "m3", "Relay 2 (Amp) M3 #2"),
        CircleOp("RLY2_H3_M3", 140.0 - 22.25, 39.0 - 10.25, "Params.m3_d", "m3", "Relay 2 (Amp) M3 #3"),
        CircleOp("RLY2_H4_M3", 140.0 + 22.25, 39.0 - 10.25, "Params.m3_d", "m3", "Relay 2 (Amp) M3 #4"),
        # PAM8403 (21 x 18 mm) 2x M2.5 clamp / nylon tie-down holes (26.0 mm span) centered at (191.0, 39.0)
        CircleOp("PAM_CLAMP_L", 191.0 - 13.0, 39.0, "Params.m25_d", "m25", "PAM8403 nylon tie/clamp left"),
        CircleOp("PAM_CLAMP_R", 191.0 + 13.0, 39.0, "Params.m25_d", "m25", "PAM8403 nylon tie/clamp right"),
    ]

    panels.append(PanelSpec(
        panel_id="P01_BASE",
        name="Main Base Plate",
        qty=1,
        plane="XY",
        origin_xyz=(0.0, 0.0, "-Params.T_mm"),
        explode_xyz=(0.0, 0.0, -45.0),
        add_rects=[RectOp("BaseBody", 0.0, 0.0, 380.0, 286.0, "add")],
        cut_rects=p01_cuts,
        cut_circles=p01_circles,
        outer_poly_expr=[(0.0, 0.0), (380.0, 0.0), (380.0, 286.0), (0.0, 286.0)],
        notes="Houses Living Room, Bedroom, Tech Bay (KiCad PCB H1..H4, 2x Relays, PAM8403), Water Tank & Garden Planter.",
        color_rgb=(0.68, 0.84, 0.94),
    ))

    # ------------------------------------------------------------------
    # P02_WALL_BACK: Rear Wall (356 x 132 mm + bottom tabs, XZ at Y = 280 - T)
    # Local u in [0, 356] (world X = 12 + u), v in [-T, 132] (world Z = v)
    # ------------------------------------------------------------------
    back_local_tabs = [x - X_L for x in back_base_xs]
    p02_adds = [RectOp("BackBody", 0.0, 0.0, 356.0, WALL_H, "add")]
    for idx, uc in enumerate(back_local_tabs, 1):
        p02_adds.append(RectOp(f"BackTab_{idx}", uc - TAB_W / 2.0, "-Params.T_mm", TAB_W, "Params.T_mm", "add"))

    p02_cuts: list[RectOp] = [
        # Bedroom panoramic glass window cutout (116 x 60 mm, matching Blender BedWindowGlass)
        RectOp("BedWindow", 208.0, 44.0, 116.0, 60.0, "window", "Bedroom panoramic window (116x60)"),
        # DHT11 airflow vent window (12 x 14 mm at u=136, v=84 -> [130..142] x [77..91])
        RectOp("DHT11_Airflow", 130.0, 77.0, 12.0, 14.0, "window", "DHT11 sensor airflow vent (12x14)"),
    ]
    # Left & right edge notches receiving P03_WALL_LEFT and P04_WALL_RIGHT rear tabs
    for idx, zc in enumerate(rear_vert_zs, 1):
        jid_l = f"J_P03_P02_{idx}"
        p02_cuts.append(RectOp(
            f"NotchLeft_{idx}", -1.0, f"{zc} - ({TAB_W} + Params.kerf) / 2.0",
            "Params.T_mm + 1.0", f"{TAB_W} + Params.kerf", "notch", f"Receives P03 rear tab #{idx}", jid_l
        ))
        joints.append(JointPair(
            jid_l, "P03_WALL_LEFT", "P02_WALL_BACK", "Z",
            (f"{X_L} + Params.T_mm / 2.0", f"{Y_B} - Params.T_mm / 2.0", zc),
            TAB_W, f"{TAB_W} + Params.kerf", "Params.T_mm", "Params.T_mm"
        ))

        jid_r = f"J_P04_P02_{idx}"
        p02_cuts.append(RectOp(
            f"NotchRight_{idx}", "356.0 - Params.T_mm", f"{zc} - ({TAB_W} + Params.kerf) / 2.0",
            "Params.T_mm + 1.0", f"{TAB_W} + Params.kerf", "notch", f"Receives P04 rear tab #{idx}", jid_r
        ))
        joints.append(JointPair(
            jid_r, "P04_WALL_RIGHT", "P02_WALL_BACK", "Z",
            (f"{X_R} - Params.T_mm / 2.0", f"{Y_B} - Params.T_mm / 2.0", zc),
            TAB_W, f"{TAB_W} + Params.kerf", "Params.T_mm", "Params.T_mm"
        ))

        # Mid wall vertical through-slots at u = 173.0 (world X = 185.0)
        jid_m = f"J_P06_P02_{idx}"
        p02_cuts.append(RectOp(
            f"SlotMid_{idx}", "173.0 - Params.slot_w / 2.0", f"{zc} - ({TAB_W} + Params.kerf) / 2.0",
            "Params.slot_w", f"{TAB_W} + Params.kerf", "slot", f"Receives P06 rear tab #{idx}", jid_m
        ))
        joints.append(JointPair(
            jid_m, "P06_WALL_MID", "P02_WALL_BACK", "Z",
            (X_M, f"{Y_B} - Params.T_mm / 2.0", zc),
            TAB_W, f"{TAB_W} + Params.kerf", "Params.T_mm", "Params.slot_w"
        ))

    p02_circles = [
        CircleOp("LED_Living_5mm", 83.0, 112.0, "Params.led5_d", "led", "Living Room 5mm LED (D0)"),
        CircleOp("LED_Bedroom_5mm", 266.0, 118.0, "Params.led5_d", "led", "Bedroom 5mm LED (D4)"),
        CircleOp("DHT11_Mount_M3", 136.0, 100.0, "Params.m3_d", "m3", "DHT11 breakout M3 mount"),
        CircleOp("Cable_Rear_LR", 32.0, 18.0, "Params.cable_d", "cable", "Living Room rear wire routing"),
        CircleOp("Cable_Rear_BR", 206.0, 18.0, "Params.cable_d", "cable", "Bedroom rear wire routing"),
    ]

    p02_poly: list[tuple[str | float, str | float]] = []
    p02_poly.extend(_tab_edge_poly_bottom(0.0, 356.0, back_local_tabs, TAB_W))
    p02_poly.extend(_notch_edge_poly_vertical(356.0, 0.0, WALL_H, rear_vert_zs, TAB_W, inward_sign=-1))
    p02_poly.append((356.0, WALL_H))
    p02_poly.append((0.0, WALL_H))
    p02_poly.extend(_notch_edge_poly_vertical(0.0, WALL_H, 0.0, rear_vert_zs, TAB_W, inward_sign=+1))

    panels.append(PanelSpec(
        panel_id="P02_WALL_BACK",
        name="Rear Wall (Living + Bedroom)",
        qty=1,
        plane="XZ",
        origin_xyz=(X_L, f"{Y_B} - Params.T_mm", 0.0),
        explode_xyz=(0.0, 70.0, 0.0),
        add_rects=p02_adds,
        cut_rects=p02_cuts,
        cut_circles=p02_circles,
        outer_poly_expr=p02_poly,
        notes="Full-height rear wall with Bedroom panoramic window, Living/Bedroom 5mm LED holes, DHT11 airflow vent + M3 hole, cable holes.",
        color_rgb=(0.80, 0.92, 0.99),
    ))

    # ------------------------------------------------------------------
    # P03_WALL_LEFT & P04_WALL_RIGHT: Stepped Open-Cutaway Side Walls
    # Local u in [0, 178] (world Y = 102 + u), v in [-T, 132] (world Z = v)
    # Body sits between Front Wall (u=T) and Rear Wall (u=178-T) with outward tabs
    # extending to u=0 (front) and u=178 (rear).
    # ------------------------------------------------------------------
    side_local_tabs = [y - Y_F for y in side_base_ys]

    def _make_side_wall(
        pid: str, name: str, x_orig: str, exp_x: float, step_u: float, add_cable_hole: bool
    ) -> PanelSpec:
        # Main body: front low cutaway [T .. step_u] x [0 .. CUT_H], rear full height [step_u .. 178-T] x [0 .. WALL_H]
        adds = [
            RectOp("FrontLowBody", "Params.T_mm", 0.0, f"{step_u} - Params.T_mm", CUT_H, "add"),
            RectOp("RearFullBody", step_u, 0.0, f"178.0 - {step_u} - Params.T_mm", WALL_H, "add"),
        ]
        # Bottom tabs into Base
        for idx, uc in enumerate(side_local_tabs, 1):
            adds.append(RectOp(f"BotTab_{idx}", uc - TAB_W / 2.0, "-Params.T_mm", TAB_W, "Params.T_mm", "add"))
        # Rear tabs into P02_WALL_BACK (extending from u = 178-T to 178)
        for idx, zc in enumerate(rear_vert_zs, 1):
            adds.append(RectOp(f"RearTab_{idx}", "178.0 - Params.T_mm", zc - TAB_W / 2.0, "Params.T_mm", TAB_W, "add"))
        # Front tab into P05_WALL_FRONT (extending from u = 0 to T, height 10 mm at Z=14)
        for idx, zc in enumerate(front_corner_zs, 1):
            adds.append(RectOp(f"FrontTab_{idx}", 0.0, zc - 5.0, "Params.T_mm", 10.0, "add"))

        circles = []
        if add_cable_hole:
            circles.append(CircleOp("Cable_Left_Service", 120.0, 18.0, "Params.cable_d", "cable", "Optional left-side cable pass-through"))

        # Exact closed CCW outer polygon
        poly: list[tuple[str | float, str | float]] = []
        # Bottom edge from u = T to u = 178 - T with bottom tabs
        poly.append(("Params.T_mm", 0.0))
        for c in sorted(side_local_tabs):
            poly.append((c - TAB_W / 2.0, 0.0))
            poly.append((c - TAB_W / 2.0, "-Params.T_mm"))
            poly.append((c + TAB_W / 2.0, "-Params.T_mm"))
            poly.append((c + TAB_W / 2.0, 0.0))
        poly.append(("178.0 - Params.T_mm", 0.0))
        # Rear vertical edge up to WALL_H with outward tabs (+T)
        poly.extend(_tab_edge_poly_vertical("178.0 - Params.T_mm", 0.0, WALL_H, rear_vert_zs, TAB_W, outward_sign=+1))
        poly.append(("178.0 - Params.T_mm", WALL_H))
        # Stepped cutaway top edge back to front
        poly.append((step_u, WALL_H))
        poly.append((step_u, CUT_H))
        poly.append(("Params.T_mm", CUT_H))
        # Front vertical edge down to 0 with outward tab (-T)
        poly.extend(_tab_edge_poly_vertical("Params.T_mm", CUT_H, 0.0, front_corner_zs, 10.0, outward_sign=-1))

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
            notes=f"Open-cutaway side wall: full height {int(WALL_H)}mm rear, low {int(CUT_H)}mm cutaway front.",
            color_rgb=(0.78, 0.91, 0.98),
        )

    panels.append(_make_side_wall("P03_WALL_LEFT", "Left Cutaway Side Wall", f"{X_L}", -75.0, 58.0, True))
    panels.append(_make_side_wall("P04_WALL_RIGHT", "Right Cutaway Side Wall", f"{X_R} - Params.T_mm", 75.0, 66.0, False))

    # ------------------------------------------------------------------
    # P05_WALL_FRONT: Front Cutaway Facade Wall (356 mm wide, XZ at Y = 102)
    # Profile segments along u in [0, 356]:
    #   [0 .. 36]:     height 28 mm (left low cutaway)
    #   [36 .. 126]:   height 112 mm (Main Door Portal, opening [62..116] x [0..96])
    #   [126 .. 162]:  height 42 mm (KY-037 sound sensor ledge)
    #   [162 .. 186]:  height 132 mm (Center Buzzer Pillar, centered at u=173)
    #   [186 .. 356]:  height 28 mm (Bedroom open-cutaway front waist)
    # ------------------------------------------------------------------
    front_local_tabs = [x - X_L for x in front_base_xs]
    p05_adds = [
        RectOp("FrontLeftLow", 0.0, 0.0, 36.0, CUT_H, "add"),
        RectOp("DoorPortal", 36.0, 0.0, 90.0, 112.0, "add"),
        RectOp("KY037_Ledge", 126.0, 0.0, 36.0, 42.0, "add"),
        RectOp("CenterPillar", 162.0, 0.0, 24.0, WALL_H, "add"),
        RectOp("BedFrontLow", 186.0, 0.0, 170.0, CUT_H, "add"),
    ]
    for idx, uc in enumerate(front_local_tabs, 1):
        p05_adds.append(RectOp(f"FrontTab_{idx}", uc - TAB_W / 2.0, "-Params.T_mm", TAB_W, "Params.T_mm", "add"))

    p05_cuts: list[RectOp] = [
        # Main door opening (54 x 96 mm, open bottom threshold at v=0)
        RectOp("MainDoorOpening", 62.0, -1.0, 54.0, 97.0, "door", "Main Door opening (54x96)"),
        # Left & right corner notches receiving P03 & P04 front tabs (height 10 at Z=14)
        RectOp("NotchLeft_1", -1.0, "14.0 - (10.0 + Params.kerf) / 2.0", "Params.T_mm + 1.0", "10.0 + Params.kerf", "notch", "Receives P03 front tab", "J_P03_P05_1"),
        RectOp("NotchRight_1", "356.0 - Params.T_mm", "14.0 - (10.0 + Params.kerf) / 2.0", "Params.T_mm + 1.0", "10.0 + Params.kerf", "notch", "Receives P04 front tab", "J_P04_P05_1"),
        # Horizontal slot receiving P07_SERVO_SHELF rear tab (u=41..55, Z=24)
        RectOp("SlotServoShelf", "48.0 - (14.0 + Params.kerf) / 2.0", "24.0 - Params.slot_w / 2.0", "14.0 + Params.kerf", "Params.slot_w", "slot", "Receives P07_SERVO_SHELF tab", "J_P07_P05_1"),
    ]
    joints.append(JointPair(
        "J_P03_P05_1", "P03_WALL_LEFT", "P05_WALL_FRONT", "Z",
        (f"{X_L} + Params.T_mm / 2.0", f"{Y_F} + Params.T_mm / 2.0", 14.0),
        10.0, "10.0 + Params.kerf", "Params.T_mm", "Params.T_mm"
    ))
    joints.append(JointPair(
        "J_P04_P05_1", "P04_WALL_RIGHT", "P05_WALL_FRONT", "Z",
        (f"{X_R} - Params.T_mm / 2.0", f"{Y_F} + Params.T_mm / 2.0", 14.0),
        10.0, "10.0 + Params.kerf", "Params.T_mm", "Params.T_mm"
    ))
    joints.append(JointPair(
        "J_P07_P05_1", "P07_SERVO_SHELF", "P05_WALL_FRONT", "X",
        (X_L + 48.0, f"{Y_F} + Params.T_mm / 2.0", 24.0),
        14.0, "14.0 + Params.kerf", "Params.T_mm", "Params.slot_w"
    ))

    for idx, zc in enumerate(mid_front_zs, 1):
        jid = f"J_P06_P05_{idx}"
        p05_cuts.append(RectOp(
            f"SlotMidFront_{idx}", "173.0 - Params.slot_w / 2.0", f"{zc} - ({TAB_W} + Params.kerf) / 2.0",
            "Params.slot_w", f"{TAB_W} + Params.kerf", "slot", f"Receives P06 front tab #{idx}", jid
        ))
        joints.append(JointPair(
            jid, "P06_WALL_MID", "P05_WALL_FRONT", "Z",
            (X_M, f"{Y_F} + Params.T_mm / 2.0", zc),
            TAB_W, f"{TAB_W} + Params.kerf", "Params.T_mm", "Params.slot_w"
        ))

    p05_circles = [
        CircleOp("Buzzer_12mm", 173.0, 114.0, "Params.buzzer_d", "buzzer", "12mm Active Buzzer TMB12A05 (D8)"),
        CircleOp("KY037_Mic_Aperture", 136.0, 24.0, "Params.mic_d", "mic", "KY-037 electret mic acoustic window"),
        CircleOp("KY037_Mount_M3", 154.0, 24.0, "Params.m3_d", "m3", "KY-037 PCB M3 mounting hole"),
        CircleOp("Cable_Front_LR", 20.0, 14.0, "Params.cable_d", "cable", "Tech Bay to Living Room cable pass-through"),
        CircleOp("Cable_Front_BR", 204.0, 14.0, "Params.cable_d", "cable", "Tech Bay to Bedroom cable pass-through"),
    ]

    # Exact closed CCW outer polygon for P05_WALL_FRONT (including open door threshold [62..116])
    p05_poly: list[tuple[str | float, str | float]] = [(0.0, 0.0)]
    # Tab 1 at u=26
    p05_poly.extend([(26.0 - TAB_W / 2, 0.0), (26.0 - TAB_W / 2, "-Params.T_mm"),
                     (26.0 + TAB_W / 2, "-Params.T_mm"), (26.0 + TAB_W / 2, 0.0)])
    # Door opening cutout along bottom edge (u = 62 .. 116, v = 0 .. 96)
    p05_poly.extend([(62.0, 0.0), (62.0, 96.0), (116.0, 96.0), (116.0, 0.0)])
    # Remaining bottom tabs at u=140, 220, 316
    for c in [140.0, 220.0, 316.0]:
        p05_poly.extend([(c - TAB_W / 2, 0.0), (c - TAB_W / 2, "-Params.T_mm"),
                         (c + TAB_W / 2, "-Params.T_mm"), (c + TAB_W / 2, 0.0)])
    p05_poly.append((356.0, 0.0))
    # Right vertical edge up to 28 with notch
    p05_poly.extend(_notch_edge_poly_vertical(356.0, 0.0, CUT_H, front_corner_zs, 10.0, inward_sign=-1))
    # Top stepped silhouette right-to-left
    p05_poly.extend([
        (356.0, CUT_H), (186.0, CUT_H),
        (186.0, WALL_H), (162.0, WALL_H),
        (162.0, 42.0), (126.0, 42.0),
        (126.0, 112.0), (36.0, 112.0),
        (36.0, CUT_H), (0.0, CUT_H),
    ])
    # Left vertical edge down to 0 with notch
    p05_poly.extend(_notch_edge_poly_vertical(0.0, CUT_H, 0.0, front_corner_zs, 10.0, inward_sign=+1))

    panels.append(PanelSpec(
        panel_id="P05_WALL_FRONT",
        name="Front Cutaway Facade & Door Portal",
        qty=1,
        plane="XZ",
        origin_xyz=(X_L, Y_F, 0.0),
        explode_xyz=(0.0, -50.0, 0.0),
        add_rects=p05_adds,
        cut_rects=p05_cuts,
        cut_circles=p05_circles,
        outer_poly_expr=p05_poly,
        notes="Open-cutaway front facade with 54x96mm Main Door portal, SG90 shelf slot, KY-037 mic aperture+M3, 12mm Buzzer pillar, cable holes.",
        color_rgb=(0.76, 0.90, 0.98),
    ))

    # ------------------------------------------------------------------
    # P06_WALL_MID: Center Dividing Wall (Living/Bedroom, YZ at X = 185 - T/2)
    # Local u in [0, 178] (world Y = 102 + u), body u in [T, 178-T], tabs to 0 and 178
    # Interior doorway cutout: u in [20, 68] (48 mm wide), v in [0, 96] (96 mm tall)
    # ------------------------------------------------------------------
    mid_local_tabs = [y - Y_F for y in mid_base_ys]
    p06_adds = [RectOp("MidBody", "Params.T_mm", 0.0, "178.0 - 2.0 * Params.T_mm", WALL_H, "add")]
    for idx, uc in enumerate(mid_local_tabs, 1):
        p06_adds.append(RectOp(f"MidBotTab_{idx}", uc - TAB_W / 2.0, "-Params.T_mm", TAB_W, "Params.T_mm", "add"))
    for idx, zc in enumerate(rear_vert_zs, 1):
        p06_adds.append(RectOp(f"MidRearTab_{idx}", "178.0 - Params.T_mm", zc - TAB_W / 2.0, "Params.T_mm", TAB_W, "add"))
    for idx, zc in enumerate(mid_front_zs, 1):
        p06_adds.append(RectOp(f"MidFrontTab_{idx}", 0.0, zc - TAB_W / 2.0, "Params.T_mm", TAB_W, "add"))

    p06_cuts = [
        RectOp("InteriorDoorway", 20.0, -1.0, 48.0, 97.0, "door", "Interior Living-Bedroom doorway (48x96)")
    ]
    p06_circles = [
        CircleOp("Cable_Mid_Rooms", 145.0, 16.0, "Params.cable_d", "cable", "Living Room to Bedroom cable pass-through")
    ]

    p06_poly: list[tuple[str | float, str | float]] = [
        ("Params.T_mm", 0.0), (20.0, 0.0), (20.0, 96.0), (68.0, 96.0), (68.0, 0.0)
    ]
    for c in sorted(mid_local_tabs):
        p06_poly.extend([(c - TAB_W / 2, 0.0), (c - TAB_W / 2, "-Params.T_mm"),
                         (c + TAB_W / 2, "-Params.T_mm"), (c + TAB_W / 2, 0.0)])
    p06_poly.append(("178.0 - Params.T_mm", 0.0))
    p06_poly.extend(_tab_edge_poly_vertical("178.0 - Params.T_mm", 0.0, WALL_H, rear_vert_zs, TAB_W, outward_sign=+1))
    p06_poly.extend([("178.0 - Params.T_mm", WALL_H), ("Params.T_mm", WALL_H)])
    p06_poly.extend(_tab_edge_poly_vertical("Params.T_mm", WALL_H, 0.0, mid_front_zs, TAB_W, outward_sign=-1))

    panels.append(PanelSpec(
        panel_id="P06_WALL_MID",
        name="Center Dividing Wall (Living/Bedroom)",
        qty=1,
        plane="YZ",
        origin_xyz=(f"{X_M} - Params.T_mm / 2.0", Y_F, 0.0),
        explode_xyz=(0.0, 0.0, 95.0),
        add_rects=p06_adds,
        cut_rects=p06_cuts,
        cut_circles=p06_circles,
        outer_poly_expr=p06_poly,
        notes="Divides Living Room and Bedroom with 48x96mm doorway passage and Dia 10mm inter-room cable pass-through.",
        color_rgb=(0.74, 0.89, 0.97),
    ))

    # ------------------------------------------------------------------
    # P07_SERVO_SHELF: Horizontal SG90 Door Servo Bracket (XY plane at Z = 24 - T/2)
    # Mounted INSIDE Living Room right behind left door jamb:
    #   World X in [46, 74] (u in [0, 28], tab at u=7..21 -> world X = 53..67, local on P05 = 41..55)
    #   World Y in [102, 142+T] (v in [-T, 40]: tab v in [-T, 0] slots into P05, body v in [0, 40])
    # ------------------------------------------------------------------
    p07_adds = [
        RectOp("ShelfBody", 0.0, 0.0, 28.0, 40.0, "add"),
        RectOp("ShelfTab", 7.0, "-Params.T_mm", 14.0, "Params.T_mm", "add"),
    ]
    p07_cuts = [
        # SG90 body cutout: 12.4 mm (u) x 23.0 mm (v) centered at (14.0, 20.0)
        RectOp("SG90_Cutout", "14.0 - Params.sg90_W / 2.0", "20.0 - Params.sg90_L / 2.0",
               "Params.sg90_W", "Params.sg90_L", "cut", "SG90 servo body cutout (12.4x23.0)")
    ]
    p07_circles = [
        CircleOp("SG90_M2_Front", 14.0, "20.0 - Params.sg90_pitch / 2.0", "Params.m2_d", "m2", "SG90 M2 tab screw #1 (27.8mm pitch)"),
        CircleOp("SG90_M2_Rear", 14.0, "20.0 + Params.sg90_pitch / 2.0", "Params.m2_d", "m2", "SG90 M2 tab screw #2 (27.8mm pitch)"),
    ]
    p07_poly = [
        (0.0, 0.0), (7.0, 0.0), (7.0, "-Params.T_mm"), (21.0, "-Params.T_mm"), (21.0, 0.0),
        (28.0, 0.0), (28.0, 40.0), (0.0, 40.0),
    ]
    panels.append(PanelSpec(
        panel_id="P07_SERVO_SHELF",
        name="SG90 Door Servo Mount Shelf",
        qty=1,
        plane="XY",
        origin_xyz=(X_L + 34.0, f"{Y_F} + Params.T_mm", "24.0 - Params.T_mm / 2.0"),
        explode_xyz=(-55.0, 35.0, 55.0),
        add_rects=p07_adds,
        cut_rects=p07_cuts,
        cut_circles=p07_circles,
        outer_poly_expr=p07_poly,
        notes="Slots into P05 left door jamb inside Living Room; holds TowerPro SG90 vertically so horn swings door around Z axis.",
        color_rgb=(0.66, 0.86, 0.99),
    ))

    # ------------------------------------------------------------------
    # P08_DOOR_LEAF: Hinged Main Door Panel (51 x 93 mm, XZ at Y = 102)
    # ------------------------------------------------------------------
    p08_adds = [RectOp("DoorLeafBody", 0.0, 0.0, 51.0, 93.0, "add")]
    p08_cuts = [RectOp("DoorWindow", 13.5, 50.0, 24.0, 28.0, "window", "Main Door window cutout (24x28)")]
    p08_circles = [
        CircleOp("Door_Hinge_Bot", 4.5, 16.0, "Params.m2_d", "m2", "Bottom mini hinge M2 screw hole"),
        CircleOp("Door_Hinge_Top", 4.5, 77.0, "Params.m2_d", "m2", "Top mini hinge M2 screw hole"),
        CircleOp("Door_Servo_Link", 14.0, 26.0, "Params.m2_d", "m2", "SG90 servo push-rod linkage hole"),
    ]
    p08_poly = [(0.0, 0.0), (51.0, 0.0), (51.0, 93.0), (0.0, 93.0)]
    panels.append(PanelSpec(
        panel_id="P08_DOOR_LEAF",
        name="Main Door Leaf",
        qty=1,
        plane="XZ",
        origin_xyz=(X_L + 63.5, Y_F, 1.5),
        explode_xyz=(0.0, -95.0, 20.0),
        add_rects=p08_adds,
        cut_rects=p08_cuts,
        cut_circles=p08_circles,
        outer_poly_expr=p08_poly,
        notes="Fits 54x96mm opening with 1.5mm clearance; includes decorative window, M2 hinge holes & SG90 linkage hole.",
        color_rgb=(0.94, 0.84, 0.68),
    ))

    # ------------------------------------------------------------------
    # P09_GARDEN_LEFT, P10_WATER_DIVIDER, P11_GARDEN_RIGHT (YZ planes)
    # Local u in [0, 74] (world Y = 18 + u), body u in [T, 74-T], tabs to 0 and 74
    # ------------------------------------------------------------------
    gside_local_tabs = [y - GY_F for y in gside_base_ys]

    def _make_garden_side(
        pid: str, name: str, x_orig: str, h: float, exp_xyz: tuple[float, float, float],
        has_tube_hole: bool = False, has_wire_notch: bool = False, notes: str = ""
    ) -> PanelSpec:
        adds = [RectOp("GSideBody", "Params.T_mm", 0.0, "74.0 - 2.0 * Params.T_mm", h, "add")]
        for idx, uc in enumerate(gside_local_tabs, 1):
            adds.append(RectOp(f"GBotTab_{idx}", uc - TAB_G / 2.0, "-Params.T_mm", TAB_G, "Params.T_mm", "add"))
        for idx, zc in enumerate(garden_vert_zs, 1):
            adds.append(RectOp(f"GFrontTab_{idx}", 0.0, zc - 7.0, "Params.T_mm", 14.0, "add"))
            adds.append(RectOp(f"GRearTab_{idx}", "74.0 - Params.T_mm", zc - 7.0, "Params.T_mm", 14.0, "add"))

        cuts: list[RectOp] = []
        circles: list[CircleOp] = []
        if has_tube_hole:
            circles.append(CircleOp("Pump_Tube_Hole", 37.0, 33.0, "Params.tube_d", "tube", "Silicone pump tube pass-through (Dia 9.5mm)"))
        if has_wire_notch:
            # Top notch [10..18] x [h-7 .. h+1] for submersible pump wire exit above water line
            cuts.append(RectOp("Pump_Wire_Notch", 10.0, h - 7.0, 8.0, 8.0, "notch", "Pump wire exit notch (8x7)"))

        poly: list[tuple[str | float, str | float]] = [("Params.T_mm", 0.0)]
        for c in sorted(gside_local_tabs):
            poly.extend([(c - TAB_G / 2, 0.0), (c - TAB_G / 2, "-Params.T_mm"),
                         (c + TAB_G / 2, "-Params.T_mm"), (c + TAB_G / 2, 0.0)])
        poly.append(("74.0 - Params.T_mm", 0.0))
        poly.extend(_tab_edge_poly_vertical("74.0 - Params.T_mm", 0.0, h, garden_vert_zs, 14.0, outward_sign=+1))
        poly.append(("74.0 - Params.T_mm", h))
        if has_wire_notch:
            poly.extend([(18.0, h), (18.0, h - 7.0), (10.0, h - 7.0), (10.0, h)])
        poly.append(("Params.T_mm", h))
        poly.extend(_tab_edge_poly_vertical("Params.T_mm", h, 0.0, garden_vert_zs, 14.0, outward_sign=-1))

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
        "P09_GARDEN_LEFT", "Water Tank Left Wall", f"{GX_L}", GW_H, (-25.0, -45.0, 35.0),
        has_wire_notch=True, notes="Water reservoir left wall with 8x7mm top pump cable notch; seal inner seams with silicone."
    ))
    panels.append(_make_garden_side(
        "P10_WATER_DIVIDER", "Water-to-Garden Divider Wall", f"{GX_M} - Params.T_mm / 2.0", GW_H, (0.0, -45.0, 45.0),
        has_tube_hole=True, notes="Separates water tank (left) from garden soil planter (right) with Dia 9.5mm silicone water tube pass-through."
    ))
    panels.append(_make_garden_side(
        "P11_GARDEN_RIGHT", "Garden Planter Right Wall", f"{GX_R} - Params.T_mm", GP_H, (55.0, -45.0, 35.0),
        notes="Outer right wall of garden soil planter box."
    ))

    # ------------------------------------------------------------------
    # P12_GARDEN_FRONT & P13_GARDEN_BACK (134 mm wide, XZ at Y=18 and Y=92-T)
    # Left [0..48]: height 44 mm (Water Tank)
    # Right [48..134]: height 40 mm (Garden Planter)
    # Top notch [84..96] x [40-T..40] receives P14_SOIL_BRIDGE!
    # ------------------------------------------------------------------
    gfb_local_tabs = [x - GX_L for x in gfb_base_xs]

    def _make_garden_fb(pid: str, name: str, y_orig: str, exp_y: float, is_front: bool) -> PanelSpec:
        adds = [
            RectOp("WaterFace", 0.0, 0.0, 48.0, GW_H, "add"),
            RectOp("SoilFace", 48.0, 0.0, 86.0, GP_H, "add"),
        ]
        for idx, uc in enumerate(gfb_local_tabs, 1):
            adds.append(RectOp(f"GFBTab_{idx}", uc - TAB_G / 2.0, "-Params.T_mm", TAB_G, "Params.T_mm", "add"))

        tag = "F" if is_front else "B"
        y_ctr = f"{GY_F} + Params.T_mm / 2.0" if is_front else f"{GY_B} - Params.T_mm / 2.0"
        cuts = [
            # Left notch (P09)
            RectOp("NotchGLeft", -1.0, "20.0 - (14.0 + Params.kerf) / 2.0", "Params.T_mm + 1.0", "14.0 + Params.kerf", "notch", "Receives P09 tab", f"J_P09_{pid}"),
            # Divider slot at u=48 (P10)
            RectOp("SlotGDiv", "48.0 - Params.slot_w / 2.0", "20.0 - (14.0 + Params.kerf) / 2.0", "Params.slot_w", "14.0 + Params.kerf", "slot", "Receives P10 tab", f"J_P10_{pid}"),
            # Right notch (P11)
            RectOp("NotchGRight", "134.0 - Params.T_mm", "20.0 - (14.0 + Params.kerf) / 2.0", "Params.T_mm + 1.0", "14.0 + Params.kerf", "notch", "Receives P11 tab", f"J_P11_{pid}"),
            # Top edge notch [84..96] for P14_SOIL_BRIDGE tab (width 12 + kerf, depth T)
            RectOp("NotchSoilBridge", "90.0 - (12.0 + Params.kerf) / 2.0", "40.0 - Params.T_mm", "12.0 + Params.kerf", "Params.T_mm + 1.0", "notch", "Receives P14_SOIL_BRIDGE tab", f"J_P14_{pid}"),
        ]
        joints.append(JointPair(f"J_P09_{pid}", "P09_GARDEN_LEFT", pid, "Z", (f"{GX_L} + Params.T_mm / 2.0", y_ctr, 20.0), 14.0, "14.0 + Params.kerf", "Params.T_mm", "Params.T_mm"))
        joints.append(JointPair(f"J_P10_{pid}", "P10_WATER_DIVIDER", pid, "Z", (GX_M, y_ctr, 20.0), 14.0, "14.0 + Params.kerf", "Params.T_mm", "Params.slot_w"))
        joints.append(JointPair(f"J_P11_{pid}", "P11_GARDEN_RIGHT", pid, "Z", (f"{GX_R} - Params.T_mm / 2.0", y_ctr, 20.0), 14.0, "14.0 + Params.kerf", "Params.T_mm", "Params.T_mm"))
        joints.append(JointPair(f"J_P14_{pid}", "P14_SOIL_BRIDGE", pid, "X", (GX_L + 90.0, y_ctr, f"{GP_H} - Params.T_mm / 2.0"), 12.0, "12.0 + Params.kerf", "Params.T_mm", "Params.T_mm"))

        circles: list[CircleOp] = []
        if is_front:
            circles.append(CircleOp("LM393_Mount_M3", 74.0, 18.0, "Params.m3_d", "m3", "LM393 soil comparator board M3 exterior mount"))

        poly: list[tuple[str | float, str | float]] = []
        poly.extend(_tab_edge_poly_bottom(0.0, 134.0, gfb_local_tabs, TAB_G))
        poly.extend(_notch_edge_poly_vertical(134.0, 0.0, GP_H, garden_vert_zs, 14.0, inward_sign=-1))
        poly.extend([
            (134.0, GP_H),
            ("90.0 + (12.0 + Params.kerf) / 2.0", GP_H),
            ("90.0 + (12.0 + Params.kerf) / 2.0", f"{GP_H} - Params.T_mm"),
            ("90.0 - (12.0 + Params.kerf) / 2.0", f"{GP_H} - Params.T_mm"),
            ("90.0 - (12.0 + Params.kerf) / 2.0", GP_H),
            (48.0, GP_H), (48.0, GW_H), (0.0, GW_H),
        ])
        poly.extend(_notch_edge_poly_vertical(0.0, GW_H, 0.0, garden_vert_zs, 14.0, inward_sign=+1))

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
            notes="Encloses Water Reservoir + Garden Planter front; mounts dry LM393 board on exterior (M3)." if is_front else "Encloses Water Reservoir + Garden Planter rear (8mm dry air gap from bedroom wall).",
            color_rgb=(0.68, 0.89, 0.90),
        )

    panels.append(_make_garden_fb("P12_GARDEN_FRONT", "Water & Garden Front Wall", f"{GY_F}", -85.0, True))
    panels.append(_make_garden_fb("P13_GARDEN_BACK", "Water & Garden Rear Wall", f"{GY_B} - Params.T_mm", -15.0, False))

    # ------------------------------------------------------------------
    # P14_SOIL_BRIDGE: Soil Moisture Probe Holder Bridge (XY plane at Z = 40 - T)
    # World X in [308, 332] (u in [0, 24]), World Y in [18, 92] (v in [0, 74])
    # Body v in [T, 74-T], front/rear tabs (u in [6, 18], width 12) extend to v=0 and v=74
    # ------------------------------------------------------------------
    p14_adds = [
        RectOp("BridgeBody", 0.0, "Params.T_mm", 24.0, "74.0 - 2.0 * Params.T_mm", "add"),
        RectOp("BridgeTabF", 6.0, 0.0, 12.0, "Params.T_mm", "add"),
        RectOp("BridgeTabB", 6.0, "74.0 - Params.T_mm", 12.0, "Params.T_mm", "add"),
    ]
    p14_cuts = [
        # YL-69 fork probe (20 x 2 mm) vertical through-slot: 3.2 mm (u) x 22.0 mm (v) centered at (12, 37)
        RectOp("SoilProbeSlot", 12.0 - 1.6, 37.0 - 11.0, 3.2, 22.0, "slot", "YL-69 2-prong soil probe vertical slot (22.0x3.2)")
    ]
    p14_poly = [
        (0.0, "Params.T_mm"), (6.0, "Params.T_mm"), (6.0, 0.0), (18.0, 0.0), (18.0, "Params.T_mm"),
        (24.0, "Params.T_mm"), (24.0, "74.0 - Params.T_mm"), (18.0, "74.0 - Params.T_mm"),
        (18.0, 74.0), (6.0, 74.0), (6.0, "74.0 - Params.T_mm"), (0.0, "74.0 - Params.T_mm"),
    ]
    panels.append(PanelSpec(
        panel_id="P14_SOIL_BRIDGE",
        name="Garden Soil Probe Holder Bridge",
        qty=1,
        plane="XY",
        origin_xyz=(GX_L + 78.0, GY_F, f"{GP_H} - Params.T_mm"),
        explode_xyz=(35.0, -50.0, 80.0),
        add_rects=p14_adds,
        cut_rects=p14_cuts,
        cut_circles=[],
        outer_poly_expr=p14_poly,
        notes="Slots across top of Garden Planter to hold YL-69 2-prong soil probe vertically in soil (22.0x3.2mm slot).",
        color_rgb=(0.74, 0.92, 0.78),
    ))

    # ------------------------------------------------------------------
    # P15_TECH_FASCIA: Front Technical Bay Power & Speaker Acoustic Fascia
    # XZ plane at Y = 8.0, X in [14, 224] (u in [0, 210])
    #   [0 .. 38]:    height 28 mm (5V Power Terminal Opening 12x10 + 3mm Power LED)
    #   [38 .. 152]:  height 14 mm (Low cutaway for direct NodeMCU Micro-USB & Relay access)
    #   [152 .. 210]: height 42 mm (Dia 30mm Mini Speaker 19-hole Grille + 2x M3 clamp holes)
    # ------------------------------------------------------------------
    fascia_local_tabs = [x - TX_0 for x in fascia_base_xs]
    p15_adds = [
        RectOp("PowerZone", 0.0, 0.0, 38.0, 28.0, "add"),
        RectOp("USB_LowCut", 38.0, 0.0, 114.0, 14.0, "add"),
        RectOp("SpeakerBaffle", 152.0, 0.0, 58.0, 42.0, "add"),
    ]
    for idx, uc in enumerate(fascia_local_tabs, 1):
        p15_adds.append(RectOp(f"FasciaTab_{idx}", uc - TAB_W / 2.0, "-Params.T_mm", TAB_W, "Params.T_mm", "add"))

    p15_cuts = [
        # 5V Power Jack / Terminal opening (12.0 x 10.0 mm) centered at (13.0, 14.0)
        RectOp("Power_5V_Opening", 7.0, 9.0, 12.0, 10.0, "cut", "5V power jack / terminal opening (12x10)")
    ]
    p15_circles: list[CircleOp] = [
        CircleOp("LED_Power_3mm", 29.0, 14.0, "Params.led3_d", "led", "3mm Power Indicator LED"),
        # 2x M3 speaker clamp holes flanking Dia 28mm speaker (center u=181, v=22, span 35.0 mm)
        CircleOp("Speaker_Clamp_L", 163.5, 22.0, "Params.m3_d", "m3", "Mini Speaker (Dia 28mm) M3 clamp left"),
        CircleOp("Speaker_Clamp_R", 198.5, 22.0, "Params.m3_d", "m3", "Mini Speaker (Dia 28mm) M3 clamp right"),
        # 19-hole concentric speaker grille (1 center + 6 @ R=5.5 + 12 @ R=10.5, Dia 2.5 mm)
        CircleOp("Spk_Grille_00", 181.0, 22.0, "Params.spk_hd", "grille", "Speaker grille center"),
    ]
    for k in range(6):
        ang = math.radians(k * 60.0)
        p15_circles.append(CircleOp(
            f"Spk_Grille_I{k+1}",
            round(181.0 + 5.5 * math.cos(ang), 3),
            round(22.0 + 5.5 * math.sin(ang), 3),
            "Params.spk_hd", "grille", "Speaker grille inner ring"
        ))
    for k in range(12):
        ang = math.radians(k * 30.0)
        p15_circles.append(CircleOp(
            f"Spk_Grille_O{k+1:02d}",
            round(181.0 + 10.5 * math.cos(ang), 3),
            round(22.0 + 10.5 * math.sin(ang), 3),
            "Params.spk_hd", "grille", "Speaker grille outer ring"
        ))

    p15_poly: list[tuple[str | float, str | float]] = []
    p15_poly.extend(_tab_edge_poly_bottom(0.0, TX_L, fascia_local_tabs, TAB_W))
    p15_poly.extend([
        (TX_L, 42.0), (152.0, 42.0),
        (152.0, 14.0), (38.0, 14.0),
        (38.0, 28.0), (0.0, 28.0),
    ])

    panels.append(PanelSpec(
        panel_id="P15_TECH_FASCIA",
        name="Tech Bay Power & Speaker Fascia",
        qty=1,
        plane="XZ",
        origin_xyz=(TX_0, TY_F, 0.0),
        explode_xyz=(-30.0, -90.0, 15.0),
        add_rects=p15_adds,
        cut_rects=p15_cuts,
        cut_circles=p15_circles,
        outer_poly_expr=p15_poly,
        notes="Front technical fascia: 12x10mm 5V power opening, 3mm power LED, open USB cutout, and 19-hole Dia 28mm speaker grille.",
        color_rgb=(0.70, 0.87, 0.98),
    ))

    return panels, joints


def evaluate_panel_2d(panel: PanelSpec, T_mm: float = 3.0, kerf: float = 0.15) -> dict[str, Any]:
    """Evaluate a panel's exact 2D outline, inner cutouts, circles, and bounding box in mm.

    Shifts local coordinates so bounding box bottom-left is exactly (0.0, 0.0)
    for laser cutting and bottom/left edge datum dimensioning.
    """
    p = default_param_values(T_mm=T_mm, kerf=kerf)
    raw_outer = [(eval_expr(u, p), eval_expr(v, p)) for (u, v) in panel.outer_poly_expr]
    min_u = min(pt[0] for pt in raw_outer)
    max_u = max(pt[0] for pt in raw_outer)
    min_v = min(pt[1] for pt in raw_outer)
    max_v = max(pt[1] for pt in raw_outer)

    outer = [(round(u - min_u, 4), round(v - min_v, 4)) for (u, v) in raw_outer]

    inner_rects = []
    for r in panel.cut_rects:
        # Edge notches and open door cutouts are already baked into outer_poly_expr;
        # only closed interior cutouts (slot, window, cut) become inner closed loops.
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

    # Compute exact 2D area via shoelace minus inner rects & circles
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
        "kerf": kerf,
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
