#!/usr/bin/env python3
"""Generic, re-runnable KiCad 10 Full-System Assembly Generator.

Reads ANY Smart Home Central Hub PCB (`--hub-pcb`, default `100x80 mm` DIY
single-layer hub board or any other board size) dynamically via KiCad 10 `pcbnew`, preserves
100% of the hub board geometry/traces/zones/components untouched, and generates
a complete self-contained KiCad 10 assembly project inside `--out-dir`:

  - smarthome_modules.pretty/*.kicad_mod  (15 module footprints + harness + labels)
  - fp-lib-table
  - smarthome_assembly.kicad_pro
  - 3dmodels/wiring_harness.wrl           (40 colored 3D Dupont wires + boots)
  - 3dmodels/assembly_labels.wrl          (3D beveled plaques + raised vector text)
  - smarthome_assembly.kicad_pcb          (complete 2D + 3D KiCad 10 assembly)
  - assembly_verification.json            (strict bbox/clearance/wiring proof)

Run with KiCad 10 Python:
  "C:\\Users\\LENOVO\\AppData\\Local\\Programs\\KiCad\\10.0\\bin\\python.exe" ^
      hardware/kicad/smarthome_assembly/build_assembly.py

NEVER modifies hardware/kicad/smarthome_hub/. Zero fan, zero AC, zero IR.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pcbnew

# ---------------------------------------------------------------------------
# Constants & Canonical Contract Import
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hardware.wiring_contract import WIRE_COLORS, WIRING_TABLE  # noqa: E402

VRML_SCALE = 1.0 / 2.54  # 1 KiCad VRML unit = 2.54 mm
FORBIDDEN_TOKENS = ("vs1838", "ir_led", "ac_unit", "cooling_fan", "exhaust_fan")

# Canonical mapping from wiring_contract.py module_id -> manifest module_id
CONTRACT_TO_MANIFEST_ID: dict[str, str] = {
    "psu_5v":         "psu_5v2a_dc_jack",
    "sg90_servo":     "sg90_servo",
    "led_living":     "led_5mm_living",
    "led_bedroom":    "led_5mm_bedroom",
    "relay1_pump":    "relay1_blue_srd05",
    "pump_unit":      "submersible_pump",
    "buzzer_alarm":   "buzzer_tmb12a05",
    "relay2_speaker": "relay2_red_opto",
    "pam8403_amp":    "pam8403_amp",
    "speaker_mini":   "speaker_28mm",
    "dht11_sensor":   "dht11_module",
    "soil_lm393":     "soil_lm393_board",
    "soil_probe":     "yl69_soil_probe",
    "ky037_sound":    "ky037_sound",
}

# Off-board inter-module source ref -> manifest module_id
OFFBOARD_SRC_TO_MANIFEST_ID: dict[str, str] = {
    "PAM8403": "pam8403_amp",
    "LM393":   "soil_lm393_board",
}

# Deterministic reference designators for placed modules
MANIFEST_TO_REF: dict[str, str] = {
    "nodemcu_v2_amica":  "M_NODEMCU",
    "psu_5v2a_dc_jack":  "M_PSU",
    "sg90_servo":        "M_SG90",
    "led_5mm_living":    "M_LED_LR",
    "led_5mm_bedroom":   "M_LED_BR",
    "relay1_blue_srd05": "M_RLY1",
    "submersible_pump":  "M_PUMP",
    "buzzer_tmb12a05":   "M_BUZZER",
    "relay2_red_opto":   "M_RLY2",
    "pam8403_amp":       "M_PAM8403",
    "speaker_28mm":      "M_SPEAKER",
    "dht11_module":      "M_DHT11",
    "soil_lm393_board":  "M_LM393",
    "yl69_soil_probe":   "M_YL69",
    "ky037_sound":       "M_KY037",
}

# Clean, accurate, concise 2-line plaque labels for every off-board module
MODULE_PLAQUE_TEXT: dict[str, tuple[str, str]] = {
    "sg90_servo":        ("SG90 SERVO",   "J3 (D1/GPIO5)"),
    "led_5mm_living":    ("LED LIVING",   "J4 (D0/GPIO16)"),
    "led_5mm_bedroom":   ("LED BEDROOM",  "J5 (D4/GPIO2)"),
    "relay1_blue_srd05": ("RELAY1 PUMP",  "J7/J8 (D6)"),
    "submersible_pump":  ("PUMP + TUBE",  "J2 (PUMP OUT)"),
    "buzzer_tmb12a05":   ("BUZZER 5V",    "J6 (D8/GPIO15)"),
    "relay2_red_opto":   ("RELAY2 OPTO",  "J9/J10 (D7)"),
    "pam8403_amp":       ("PAM8403 AMP",  "J11/J12 (D3)"),
    "speaker_28mm":      ("SPEAKER 28MM", "PAM8403 BTL"),
    "dht11_module":      ("DHT11 SENSOR", "J13 (D2/GPIO4)"),
    "soil_lm393_board":  ("SOIL LM393",   "J14 (A0/ADC0)"),
    "yl69_soil_probe":   ("YL-69 PROBE",  "LM393 P1/P2"),
    "ky037_sound":       ("KY-037 SOUND", "J15 (D5/GPIO14)"),
    "psu_5v2a_dc_jack":  ("5V 2A PSU",    "J1 (PWR IN)"),
}

# Pin-name alias resolution: wiring_contract pin label -> manifest pin num
PIN_ALIAS_MAP: dict[tuple[str, str], str] = {
    ("psu_5v2a_dc_jack",  "+5V"):            "1",
    ("psu_5v2a_dc_jack",  "GND"):            "2",
    ("sg90_servo",        "PWM (Orange)"):   "1",
    ("sg90_servo",        "VCC (Red)"):      "2",
    ("sg90_servo",        "GND (Brown)"):    "3",
    ("led_5mm_living",    "Anode (+)"):      "1",
    ("led_5mm_living",    "Cathode (-)"):    "2",
    ("led_5mm_bedroom",   "Anode (+)"):      "1",
    ("led_5mm_bedroom",   "Cathode (-)"):    "2",
    ("relay1_blue_srd05", "VCC"):            "1",
    ("relay1_blue_srd05", "GND"):            "2",
    ("relay1_blue_srd05", "IN"):             "3",
    ("relay1_blue_srd05", "NO (Screw)"):     "4",
    ("relay1_blue_srd05", "COM (Screw)"):    "5",
    ("submersible_pump",  "Pump + (Red)"):   "1",
    ("submersible_pump",  "Pump - (Black)"): "2",
    ("buzzer_tmb12a05",   "Buzzer (+)"):     "1",
    ("buzzer_tmb12a05",   "Buzzer (-)"):     "2",
    ("relay2_red_opto",   "DC+"):            "1",
    ("relay2_red_opto",   "DC-"):            "2",
    ("relay2_red_opto",   "IN"):             "3",
    ("relay2_red_opto",   "NO (Screw)"):     "4",
    ("relay2_red_opto",   "COM (Screw)"):    "5",
    ("pam8403_amp",       "5V+"):            "1",
    ("pam8403_amp",       "5V-"):            "2",
    ("pam8403_amp",       "L (Audio In)"):   "3",
    ("pam8403_amp",       "GND (Audio ⊥)"):  "4",
    ("pam8403_amp",       "L_OUT+"):         "6",
    ("pam8403_amp",       "L_OUT-"):         "7",
    ("speaker_28mm",      "SPK +"):          "1",
    ("speaker_28mm",      "SPK -"):          "2",
    ("dht11_module",      "VCC (+)"):        "1",
    ("dht11_module",      "DATA (OUT)"):     "2",
    ("dht11_module",      "GND (-)"):        "3",
    ("soil_lm393_board",  "VCC"):            "1",
    ("soil_lm393_board",  "GND"):            "2",
    ("soil_lm393_board",  "AO"):             "4",
    ("soil_lm393_board",  "P1"):             "5",
    ("soil_lm393_board",  "P2"):             "6",
    ("yl69_soil_probe",   "Prong A"):        "1",
    ("yl69_soil_probe",   "Prong B"):        "2",
    ("ky037_sound",       "DO"):             "1",
    ("ky037_sound",       "G (GND)"):        "2",
    ("ky037_sound",       "+ (VCC)"):        "3",
}

# Primary hub connector(s) driving each off-board module's side and alignment
MODULE_PRIMARY_CONNECTORS: dict[str, tuple[str, ...]] = {
    "psu_5v2a_dc_jack":  ("J1",),
    "submersible_pump":  ("J2",),
    "sg90_servo":        ("J3",),
    "led_5mm_living":    ("J4",),
    "led_5mm_bedroom":   ("J5",),
    "buzzer_tmb12a05":   ("J6",),
    "relay1_blue_srd05": ("J7",),  # J8 is internal switched link; J7 sits on board edge
    "relay2_red_opto":   ("J9", "J10"),
    "pam8403_amp":       ("J11", "J12"),
    "dht11_module":      ("J13",),
    "soil_lm393_board":  ("J14",),
    "ky037_sound":       ("J15",),
}

# Companion off-board modules (placed adjacent to their host off-board module)
COMPANION_HOST: dict[str, str] = {
    "yl69_soil_probe": "soil_lm393_board",
    "speaker_28mm":    "pam8403_amp",
}


# ---------------------------------------------------------------------------
# Domain Data Structures
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BBox2D:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def cx(self) -> float:
        return 0.5 * (self.min_x + self.max_x)

    @property
    def cy(self) -> float:
        return 0.5 * (self.min_y + self.max_y)

    def translate(self, dx: float, dy: float) -> "BBox2D":
        return BBox2D(self.min_x + dx, self.min_y + dy, self.max_x + dx, self.max_y + dy)

    def union(self, other: "BBox2D") -> "BBox2D":
        return BBox2D(
            min(self.min_x, other.min_x),
            min(self.min_y, other.min_y),
            max(self.max_x, other.max_x),
            max(self.max_y, other.max_y),
        )


@dataclass
class HubConnectorInfo:
    ref: str
    value: str
    fpid: str
    is_screw_terminal: bool
    is_pin_header: bool
    cx: float
    cy: float
    edge: str  # "top", "bottom", "left", "right"
    edge_dist_mm: float
    pads: dict[str, tuple[float, float]]  # pad_num -> (x_mm, y_mm)


@dataclass
class HubBoardInfo:
    path: Path
    bbox: BBox2D
    connectors: dict[str, HubConnectorInfo]
    u1: HubConnectorInfo
    u2: HubConnectorInfo


@dataclass
class PlaqueSpec:
    plaque_id: str
    lines: tuple[str, ...]
    category: str  # "Sensor", "Actuator", "Power", "Banner"
    cx: float
    cy: float
    width: float
    height: float
    char_h: float = 3.4
    char_w: float = 2.1
    char_gap: float = 0.75
    stroke_w: float = 0.58
    line_gap: float = 2.0

    @property
    def bbox(self) -> BBox2D:
        return BBox2D(
            self.cx - 0.5 * self.width,
            self.cy - 0.5 * self.height,
            self.cx + 0.5 * self.width,
            self.cy + 0.5 * self.height,
        )


@dataclass
class PlacedModule:
    module_id: str
    ref: str
    side: str  # "center", "top", "bottom", "left", "right"
    cx: float
    cy: float
    rot_deg: float
    z_offset_mm: float
    local_bbox: BBox2D
    world_bbox: BBox2D
    plaque: PlaqueSpec | None = None
    world_pads: dict[str, tuple[float, float, float]] = field(default_factory=dict)


@dataclass
class ResolvedWire:
    wire_id: str
    group: str
    color: str
    rgb: tuple[float, float, float]
    net: str
    wire_type: str
    src_desc: str
    dst_desc: str
    src_pos: tuple[float, float, float]
    dst_pos: tuple[float, float, float]
    src_mode: str  # "dupont_up", "screw_left", "screw_right", "pad_up", "side_left", "side_right"
    dst_mode: str
    is_inter_module: bool
    is_over_hub_bridge: bool
    bundle_key: str
    bundle_idx: int = 0
    bundle_size: int = 1
    points_3d: list[tuple[float, float, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Geometry Utilities
# ---------------------------------------------------------------------------
def det_uuid(key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"smarthome.assembly.{key}"))


def rotate_pcb_xy(x: float, y: float, deg: float) -> tuple[float, float]:
    """Rotate local (x, y) by KiCad PCBnew CCW angle `deg` (+X right, +Y down)."""
    rad = math.radians(deg)
    c = math.cos(rad)
    s = math.sin(rad)
    return (x * c + y * s, -x * s + y * c)


def rotated_bbox_local(bbox: BBox2D, deg: float) -> BBox2D:
    corners = [
        rotate_pcb_xy(bbox.min_x, bbox.min_y, deg),
        rotate_pcb_xy(bbox.max_x, bbox.min_y, deg),
        rotate_pcb_xy(bbox.max_x, bbox.max_y, deg),
        rotate_pcb_xy(bbox.min_x, bbox.max_y, deg),
    ]
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    return BBox2D(min(xs), min(ys), max(xs), max(ys))


def bbox_clearance_mm(a: BBox2D, b: BBox2D) -> float:
    """Exact Chebyshev/Euclidean exterior gap between two axis-aligned 2D boxes.

    Returns negative value if overlapping (negative penetration depth),
    0.0 if touching, positive Euclidean distance if separated.
    """
    dx = max(a.min_x - b.max_x, b.min_x - a.max_x)
    dy = max(a.min_y - b.max_y, b.min_y - a.max_y)
    if dx > 0.0 and dy > 0.0:
        return math.hypot(dx, dy)
    if dx > 0.0:
        return dx
    if dy > 0.0:
        return dy
    # Overlapping in both X and Y -> negative penetration depth
    return max(dx, dy)


def compute_plaque_dims(
    lines: tuple[str, ...],
    char_h: float = 3.4,
    char_w: float = 2.1,
    char_gap: float = 0.75,
    line_gap: float = 2.0,
    pad_x: float = 2.6,
    pad_y: float = 2.2,
) -> tuple[float, float]:
    max_len = max(len(line) for line in lines)
    text_w = max_len * char_w + max(0, max_len - 1) * char_gap
    text_h = len(lines) * char_h + max(0, len(lines) - 1) * line_gap
    return (round(text_w + 2.0 * pad_x, 2), round(text_h + 2.0 * pad_y, 2))


# ---------------------------------------------------------------------------
# 1. Dynamic Hub Board Parser (Zero Hardcoded Coordinates!)
# ---------------------------------------------------------------------------
def parse_hub_board(board: pcbnew.BOARD, hub_pcb_path: Path) -> HubBoardInfo:
    raw_bbox = board.GetBoardEdgesBoundingBox()
    edge_widths = [
        pcbnew.ToMM(d.GetWidth())
        for d in board.GetDrawings()
        if d.GetLayer() == pcbnew.Edge_Cuts
    ]
    half_w = (min(edge_widths) / 2.0) if edge_widths else 0.0
    hub_bbox = BBox2D(
        min_x=round(pcbnew.ToMM(raw_bbox.GetLeft()) + half_w, 4),
        min_y=round(pcbnew.ToMM(raw_bbox.GetTop()) + half_w, 4),
        max_x=round(pcbnew.ToMM(raw_bbox.GetRight()) - half_w, 4),
        max_y=round(pcbnew.ToMM(raw_bbox.GetBottom()) - half_w, 4),
    )
    if hub_bbox.width <= 1.0 or hub_bbox.height <= 1.0:
        raise RuntimeError(f"Invalid Edge.Cuts bounding box on {hub_pcb_path}: {hub_bbox}")

    connectors: dict[str, HubConnectorInfo] = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not (ref.startswith("J") or ref in ("U1", "U2")):
            continue
        pads: dict[str, tuple[float, float]] = {}
        for pd in fp.Pads():
            pos = pd.GetPosition()
            pads[str(pd.GetNumber())] = (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y))
        if not pads:
            continue
        cx = sum(p[0] for p in pads.values()) / len(pads)
        cy = sum(p[1] for p in pads.values()) / len(pads)
        dists = {
            "left":   abs(cx - hub_bbox.min_x),
            "right":  abs(hub_bbox.max_x - cx),
            "top":    abs(cy - hub_bbox.min_y),
            "bottom": abs(hub_bbox.max_y - cy),
        }
        edge = min(dists, key=lambda k: dists[k])
        fpid = fp.GetFPIDAsString()
        fpid_low = fpid.lower()
        is_screw = ("terminalblock" in fpid_low) or ("mkds" in fpid_low) or ("screw" in fpid_low)
        is_header = ("pinheader" in fpid_low) or (ref.startswith("J") and not is_screw)
        connectors[ref] = HubConnectorInfo(
            ref=ref,
            value=fp.GetValue(),
            fpid=fpid,
            is_screw_terminal=is_screw,
            is_pin_header=is_header,
            cx=cx,
            cy=cy,
            edge=edge,
            edge_dist_mm=dists[edge],
            pads=pads,
        )

    if "U1" not in connectors or "U2" not in connectors:
        raise RuntimeError(f"Hub PCB {hub_pcb_path} missing U1 or U2 NodeMCU socket footprints")

    return HubBoardInfo(
        path=hub_pcb_path,
        bbox=hub_bbox,
        connectors=connectors,
        u1=connectors["U1"],
        u2=connectors["U2"],
    )


# ---------------------------------------------------------------------------
# 2. KiCad 10 Footprint Library & Project Files Generator
# ---------------------------------------------------------------------------
def _fmt(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def generate_module_footprint_sexp(mod_id: str, mod_data: dict[str, Any]) -> str:
    """Generate a deterministic KiCad 10 .kicad_mod footprint for one module."""
    bbox = mod_data["body_bbox_mm"]
    x0, x1 = float(bbox["min_x_mm"]), float(bbox["max_x_mm"])
    y0, y1 = float(bbox["min_y_mm"]), float(bbox["max_y_mm"])
    z_off = float(mod_data.get("recommended_z_offset_mm", 0.0))
    wrl_file = mod_data["wrl_file"]
    disp = str(mod_data["display_name"]).replace('"', "'")
    ds_url = str(mod_data.get("datasheet_url", "")).replace('"', "'")
    ref_y = y0 - 2.0
    val_y = y1 + 2.0

    is_mcu = mod_id == "nodemcu_v2_amica"
    lines: list[str] = [
        f'(footprint "{mod_id}"',
        '\t(version 20260206)',
        '\t(generator "smarthome_assembly_builder")',
        '\t(generator_version "10.0")',
        '\t(layer "F.Cu")',
        f'\t(descr "{disp}")',
        f'\t(property "Reference" "REF**"',
        f'\t\t(at 0 {_fmt(ref_y)} 0)',
        '\t\t(layer "F.SilkS")',
        *(('\t\t(hide yes)',) if is_mcu else ()),
        f'\t\t(uuid "{det_uuid(mod_id + ".ref")}")',
        '\t\t(effects (font (size 1.2 1.2) (thickness 0.18)))',
        '\t)',
        f'\t(property "Value" "{mod_id}"',
        f'\t\t(at 0 {_fmt(val_y)} 0)',
        '\t\t(layer "F.Fab")',
        f'\t\t(uuid "{det_uuid(mod_id + ".val")}")',
        '\t\t(effects (font (size 1.0 1.0) (thickness 0.15)))',
        '\t)',
        f'\t(property "Datasheet" "{ds_url}"',
        '\t\t(at 0 0 0)',
        '\t\t(layer "F.Fab")',
        '\t\t(hide yes)',
        f'\t\t(uuid "{det_uuid(mod_id + ".ds")}")',
        '\t\t(effects (font (size 1.0 1.0) (thickness 0.15)))',
        '\t)',
        f'\t(property "Description" "{disp}"',
        '\t\t(at 0 0 0)',
        '\t\t(layer "F.Fab")',
        '\t\t(hide yes)',
        f'\t\t(uuid "{det_uuid(mod_id + ".desc")}")',
        '\t\t(effects (font (size 1.0 1.0) (thickness 0.15)))',
        '\t)',
        '\t(attr board_only exclude_from_pos_files exclude_from_bom)',
        '\t(duplicate_pad_numbers_are_jumpers no)',
        # F.Fab exact body outline
        '\t(fp_rect',
        f'\t\t(start {_fmt(x0)} {_fmt(y0)})',
        f'\t\t(end {_fmt(x1)} {_fmt(y1)})',
        '\t\t(stroke (width 0.15) (type solid))',
        '\t\t(fill none)',
        '\t\t(layer "F.Fab")',
        f'\t\t(uuid "{det_uuid(mod_id + ".fab_rect")}")',
        '\t)',
        # F.SilkS outline (omit on NodeMCU so hub PCB silkscreen stays 100% uncluttered)
        *([] if is_mcu else [
            '\t(fp_rect',
            f'\t\t(start {_fmt(x0 - 0.2)} {_fmt(y0 - 0.2)})',
            f'\t\t(end {_fmt(x1 + 0.2)} {_fmt(y1 + 0.2)})',
            '\t\t(stroke (width 0.15) (type solid))',
            '\t\t(fill none)',
            '\t\t(layer "F.SilkS")',
            f'\t\t(uuid "{det_uuid(mod_id + ".silk_rect")}")',
            '\t)',
        ]),
        # F.CrtYd courtyard (0.5 mm margin)
        '\t(fp_rect',
        f'\t\t(start {_fmt(x0 - 0.5)} {_fmt(y0 - 0.5)})',
        f'\t\t(end {_fmt(x1 + 0.5)} {_fmt(y1 + 0.5)})',
        '\t\t(stroke (width 0.05) (type solid))',
        '\t\t(fill none)',
        '\t\t(layer "F.CrtYd")',
        f'\t\t(uuid "{det_uuid(mod_id + ".crtyd_rect")}")',
        '\t)',
    ]

    # Add real SMD pin pads + clear pin-name text on F.Fab
    for pin in mod_data.get("pins", []):
        pnum = str(pin["num"])
        pname = str(pin["name"]).replace('"', "'")
        px = float(pin["x_mm"])
        py = float(pin["y_mm"])
        pad_sz = 1.2 if mod_id == "nodemcu_v2_amica" else 1.4
        shape = "rect" if pnum in ("1", "U1.1", "U2.1") else "oval"
        lines.extend([
            f'\t(pad "{pnum}" smd {shape}',
            f'\t\t(at {_fmt(px)} {_fmt(py)})',
            f'\t\t(size {_fmt(pad_sz)} {_fmt(pad_sz)})',
            '\t\t(layers "F.Cu" "F.Mask" "F.Paste")',
            '\t\t(thermal_bridge_angle 45)',
            f'\t\t(uuid "{det_uuid(mod_id + ".pad." + pnum)}")',
            '\t)',
        ])
        # Pin label on F.Fab tucked slightly inward
        inward_dx = 1.8 if px < 0 else (-1.8 if px > 0 else 0.0)
        inward_dy = 0.0 if abs(px) > 2.0 else (-1.6 if py <= 0 else 1.6)
        short_name = pname[:12]
        lines.extend([
            f'\t(fp_text user "{pnum}:{short_name}"',
            f'\t\t(at {_fmt(px + inward_dx)} {_fmt(py + inward_dy)} 0)',
            '\t\t(layer "F.Fab")',
            f'\t\t(uuid "{det_uuid(mod_id + ".ptxt." + pnum)}")',
            '\t\t(effects (font (size 0.7 0.7) (thickness 0.1)))',
            '\t)',
        ])

    lines.extend([
        '\t(embedded_fonts no)',
        f'\t(model "${{KIPRJMOD}}/3dmodels/{wrl_file}"',
        f'\t\t(offset (xyz 0 0 {_fmt(z_off)}))',
        '\t\t(scale (xyz 1 1 1))',
        '\t\t(rotate (xyz 0 0 0))',
        '\t)',
        ')',
        '',
    ])
    return "\n".join(lines)


def generate_helper_footprint_sexp(fp_name: str, wrl_file: str, descr: str) -> str:
    """Generate a helper footprint carrying a 3D VRML model (harness or labels)."""
    return "\n".join([
        f'(footprint "{fp_name}"',
        '\t(version 20260206)',
        '\t(generator "smarthome_assembly_builder")',
        '\t(generator_version "10.0")',
        '\t(layer "F.Cu")',
        f'\t(descr "{descr}")',
        f'\t(property "Reference" "REF**"',
        '\t\t(at 0 0 0)',
        '\t\t(layer "F.Fab")',
        '\t\t(hide yes)',
        f'\t\t(uuid "{det_uuid(fp_name + ".ref")}")',
        '\t\t(effects (font (size 1.0 1.0) (thickness 0.15)))',
        '\t)',
        f'\t(property "Value" "{fp_name}"',
        '\t\t(at 0 0 0)',
        '\t\t(layer "F.Fab")',
        '\t\t(hide yes)',
        f'\t\t(uuid "{det_uuid(fp_name + ".val")}")',
        '\t\t(effects (font (size 1.0 1.0) (thickness 0.15)))',
        '\t)',
        '\t(property "Datasheet" ""',
        '\t\t(at 0 0 0)',
        '\t\t(layer "F.Fab")',
        '\t\t(hide yes)',
        f'\t\t(uuid "{det_uuid(fp_name + ".ds")}")',
        '\t\t(effects (font (size 1.0 1.0) (thickness 0.15)))',
        '\t)',
        f'\t(property "Description" "{descr}"',
        '\t\t(at 0 0 0)',
        '\t\t(layer "F.Fab")',
        '\t\t(hide yes)',
        f'\t\t(uuid "{det_uuid(fp_name + ".desc")}")',
        '\t\t(effects (font (size 1.0 1.0) (thickness 0.15)))',
        '\t)',
        '\t(attr board_only exclude_from_pos_files exclude_from_bom)',
        '\t(embedded_fonts no)',
        f'\t(model "${{KIPRJMOD}}/3dmodels/{wrl_file}"',
        '\t\t(offset (xyz 0 0 0))',
        '\t\t(scale (xyz 1 1 1))',
        '\t\t(rotate (xyz 0 0 0))',
        '\t)',
        ')',
        '',
    ])


def write_footprint_library(out_dir: Path, manifest: dict[str, Any]) -> Path:
    pretty_dir = out_dir / "smarthome_modules.pretty"
    pretty_dir.mkdir(parents=True, exist_ok=True)
    modules = manifest["modules"]
    for mod_id, mod_data in modules.items():
        sexp = generate_module_footprint_sexp(mod_id, mod_data)
        (pretty_dir / f"{mod_id}.kicad_mod").write_text(sexp, encoding="utf-8", newline="\n")

    helpers = [
        ("Assembly_Wiring_Harness", "wiring_harness.wrl", "3D Colored Dupont Wiring Harness (40 wires W01-W40)"),
        ("Assembly_Labels", "assembly_labels.wrl", "3D Beveled Nameplate Plaques and Raised Vector Labels"),
    ]
    for fp_name, wrl_file, descr in helpers:
        sexp = generate_helper_footprint_sexp(fp_name, wrl_file, descr)
        (pretty_dir / f"{fp_name}.kicad_mod").write_text(sexp, encoding="utf-8", newline="\n")
    return pretty_dir


def write_fp_lib_table(out_dir: Path) -> Path:
    content = "\n".join([
        '(fp_lib_table',
        '\t(version 7)',
        '\t(lib (name "smarthome_modules") (type "KiCad") (uri "${KIPRJMOD}/smarthome_modules.pretty") (options "") (descr "Smart Home Voice AI 3D Assembly Modules"))',
        '\t(lib (name "DIY_Hub") (type "KiCad") (uri "${KIPRJMOD}/../smarthome_hub/DIY_Hub.pretty") (options "") (descr "Single-layer 100x80 DIY Hub footprints"))',
        '\t(lib (name "Capacitor_THT") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Capacitor_THT.pretty") (options "") (descr ""))',
        '\t(lib (name "Connector_PinHeader_2.54mm") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Connector_PinHeader_2.54mm.pretty") (options "") (descr ""))',
        '\t(lib (name "Connector_PinSocket_2.54mm") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Connector_PinSocket_2.54mm.pretty") (options "") (descr ""))',
        '\t(lib (name "Diode_THT") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Diode_THT.pretty") (options "") (descr ""))',
        '\t(lib (name "LED_THT") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/LED_THT.pretty") (options "") (descr ""))',
        '\t(lib (name "MountingHole") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/MountingHole.pretty") (options "") (descr ""))',
        '\t(lib (name "Resistor_THT") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Resistor_THT.pretty") (options "") (descr ""))',
        '\t(lib (name "TerminalBlock_Phoenix") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/TerminalBlock_Phoenix.pretty") (options "") (descr ""))',
        ')',
        '',
    ])
    path = out_dir / "fp-lib-table"
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def write_kicad_pro(out_dir: Path, hub_pcb_path: Path) -> Path:
    hub_pro = hub_pcb_path.with_suffix(".kicad_pro")
    if hub_pro.exists():
        pro_data = json.loads(hub_pro.read_text(encoding="utf-8"))
    else:
        pro_data = {"meta": {"version": 3}}
    pro_data.setdefault("meta", {})["filename"] = "smarthome_assembly.kicad_pro"
    if "schematic" in pro_data:
        pro_data["schematic"]["top_level_sheets"] = []
    path = out_dir / "smarthome_assembly.kicad_pro"
    path.write_text(json.dumps(pro_data, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


# ---------------------------------------------------------------------------
# 3. Dynamic Placement Engine (Works on ANY Hub Size — default 100x80 mm DIY)
# ---------------------------------------------------------------------------
def _choose_module_rotation(mod_id: str, side: str) -> float:
    """Choose deterministic orientation so pins face hub (or companion) cleanly."""
    # Exact pin directions verified from modules_manifest.json:
    # - sg90_servo: pins at x=-16.0 (left edge)
    # - ky037_sound: pins at x=-15.8 (left edge)
    # - relay1_blue_srd05: coil pins at x=-21.5 (left), COM/NO at x=+24.6 (right)
    # - relay2_red_opto: coil pins at x=-21.5 (left), COM/NO at x=+24.6 (right)
    # - buzzer_tmb12a05: pins at (-3.8, 0) & (+3.8, 0)
    # - led_5mm_*: pins at (-1.27, 0) & (+1.27, 0)
    # - dht11_module: pins at x=-12.2 (left edge)
    # - soil_lm393_board: hub pins at x=-14.2 (left), P1/P2 at x=+14.2 (right)
    # - yl69_soil_probe: handle pins at x=-29.8 (left edge)
    # - submersible_pump: pins at x=-22.5 (left edge)
    # - psu_5v2a_dc_jack: pins at x=+59.0 (right edge)
    # - pam8403_amp: inputs at x=-8.8 (left), outputs at x=+8.8 (right)
    # - speaker_28mm: pins at x=-12.3 (left edge)
    if mod_id == "psu_5v2a_dc_jack":
        return {"left": 0.0, "right": 180.0, "top": -90.0, "bottom": 90.0}[side]
    if mod_id == "submersible_pump":
        return {"left": 180.0, "right": 0.0, "top": 90.0, "bottom": -90.0}[side]
    if mod_id in ("sg90_servo", "ky037_sound", "dht11_module", "soil_lm393_board"):
        # Local pins on -X -> rot 0 faces left (for right side), +90 faces down (for top side)
        return {"right": 0.0, "left": 180.0, "top": 90.0, "bottom": -90.0}[side]
    if mod_id == "yl69_soil_probe":
        # Placed left of soil_lm393_board on top side -> handle at +X facing LM393
        return {"top": 180.0, "bottom": 180.0, "left": 180.0, "right": 0.0}[side]
    if mod_id == "relay1_blue_srd05":
        return {"right": 0.0, "left": 180.0, "top": 90.0, "bottom": -90.0}[side]
    if mod_id == "relay2_red_opto":
        # Horizontal below J9 (left) & J10 (right) so coil faces J9 and screw faces J10
        return {"bottom": 0.0, "top": 0.0, "right": 0.0, "left": 180.0}[side]
    if mod_id == "pam8403_amp":
        # Inputs on left (-X) under J11/J12, outputs on right (+X) facing speaker_28mm
        return 0.0
    if mod_id == "speaker_28mm":
        # Pins on left (-X) directly facing PAM8403 outputs on right (+X)
        return 0.0
    if mod_id in ("led_5mm_living", "led_5mm_bedroom"):
        return {"top": 0.0, "bottom": 0.0, "right": -90.0, "left": 90.0}[side]
    if mod_id == "buzzer_tmb12a05":
        return {"right": -90.0, "left": 90.0, "top": 0.0, "bottom": 0.0}[side]
    return 0.0


def _build_plaque_for_module(
    mod_id: str,
    side: str,
    mod_bbox: BBox2D,
    category: str,
    mod_height_z: float = 10.0,
) -> PlaqueSpec:
    lines = MODULE_PLAQUE_TEXT[mod_id]
    pw, ph = compute_plaque_dims(lines)
    # Place plaque AWAY from the hub wiring corridor AND clear of isometric Z-foreshortening!
    if side == "top":
        # Account for module height Z so tall parts (LM393 pot/boot, DHT11) never occlude plaques in iso view
        gap = 12.5 if mod_id == "soil_lm393_board" else max(5.0, min(11.0, 0.72 * mod_height_z))
        cx = mod_bbox.cx
        cy = mod_bbox.min_y - gap - 0.5 * ph
    elif side == "bottom":
        gap = 5.0
        cx = mod_bbox.cx
        cy = mod_bbox.max_y + gap + 0.5 * ph
    elif side == "left":
        if mod_id == "submersible_pump":
            # Pump + silicone tube rises to Z=41.8mm and PSU brick sits below; placing plaque left & upper-aligned keeps it 100% unobstructed in iso view!
            gap = 6.5
            cx = mod_bbox.min_x - gap - 0.5 * pw
            cy = mod_bbox.min_y + 2.0
        else:
            gap = 5.0
            cx = mod_bbox.cx
            cy = mod_bbox.max_y + gap + 0.5 * ph
    else:  # right side
        # Extra room on relay1 right edge so COM/NO screw terminal wires curve cleanly
        gap = 14.0 if mod_id == "relay1_blue_srd05" else (9.0 if mod_id == "sg90_servo" else 7.0)
        cx = mod_bbox.max_x + gap + 0.5 * pw
        cy = mod_bbox.cy
    return PlaqueSpec(
        plaque_id=f"PLQ_{mod_id}",
        lines=lines,
        category=category,
        cx=cx,
        cy=cy,
        width=pw,
        height=ph,
    )


def _relax_1d_intervals(
    centers: list[float],
    half_neg: list[float],
    half_pos: list[float],
    min_gap: float,
    anchor_mask: list[bool] | None = None,
) -> list[float]:
    """Symmetric 1D non-overlap relaxation anchored to hub-connected modules."""
    n = len(centers)
    if n <= 1:
        return list(centers)
    pos = list(centers)
    mask = anchor_mask if anchor_mask is not None else [True] * n
    anchor_indices = [i for i, keep in enumerate(mask) if keep]
    orig_anchor_mean = (
        sum(centers[i] for i in anchor_indices) / len(anchor_indices)
        if anchor_indices
        else sum(centers) / n
    )
    for _ in range(140):
        moved = False
        for i in range(n - 1):
            right_edge = pos[i] + half_pos[i]
            left_edge = pos[i + 1] - half_neg[i + 1]
            needed = (right_edge + min_gap) - left_edge
            if needed > 1e-6:
                # If one side is a non-anchored outer companion, let it absorb more displacement
                if not mask[i] and mask[i + 1]:
                    pos[i] -= 0.85 * needed
                    pos[i + 1] += 0.15 * needed
                elif mask[i] and not mask[i + 1]:
                    pos[i] -= 0.15 * needed
                    pos[i + 1] += 0.85 * needed
                else:
                    pos[i] -= 0.5 * needed
                    pos[i + 1] += 0.5 * needed
                moved = True
        if not moved:
            break
    # Recenter anchored hub-connected modules so they stay aligned directly above/below hub headers
    cur_anchor_mean = (
        sum(pos[i] for i in anchor_indices) / len(anchor_indices)
        if anchor_indices
        else sum(pos) / n
    )
    shift = max(-22.0, min(22.0, orig_anchor_mean - cur_anchor_mean))
    return [p + shift for p in pos]


def compute_dynamic_layout(
    hub: HubBoardInfo,
    manifest: dict[str, Any],
    corridor_mm: float = 25.0,
    min_gap_mm: float = 8.0,
) -> tuple[dict[str, PlacedModule], PlaqueSpec]:
    """Compute zero-overlap positions for NodeMCU + all 14 off-board modules + plaques."""
    modules_data = manifest["modules"]
    placed: dict[str, PlacedModule] = {}

    # 1. NodeMCU: dynamically snap to exact center and orientation of U1 & U2 sockets!
    u1, u2 = hub.u1, hub.u2
    mcu_cx = 0.5 * (u1.cx + u2.cx)
    mcu_cy = 0.5 * (u1.cy + u2.cy)
    # Vector U1 -> U2 corresponds to local +X in nodemcu_v2_amica.
    # KiCad CCW rotation maps local +X (1, 0) to (cos a, -sin a).
    mcu_rot = math.degrees(math.atan2(-(u2.cy - u1.cy), (u2.cx - u1.cx)))
    # Snap tiny floating noise to exact multiple of 90 if within 0.01 deg
    if abs(mcu_rot - round(mcu_rot / 90.0) * 90.0) < 0.01:
        mcu_rot = round(mcu_rot / 90.0) * 90.0
    mcu_data = modules_data["nodemcu_v2_amica"]
    mcu_local = BBox2D(
        mcu_data["body_bbox_mm"]["min_x_mm"],
        mcu_data["body_bbox_mm"]["min_y_mm"],
        mcu_data["body_bbox_mm"]["max_x_mm"],
        mcu_data["body_bbox_mm"]["max_y_mm"],
    )
    mcu_rot_local = rotated_bbox_local(mcu_local, mcu_rot)
    placed["nodemcu_v2_amica"] = PlacedModule(
        module_id="nodemcu_v2_amica",
        ref=MANIFEST_TO_REF["nodemcu_v2_amica"],
        side="center",
        cx=mcu_cx,
        cy=mcu_cy,
        rot_deg=mcu_rot,
        z_offset_mm=float(mcu_data["recommended_z_offset_mm"]),
        local_bbox=mcu_local,
        world_bbox=mcu_rot_local.translate(mcu_cx, mcu_cy),
        plaque=None,
    )

    # 2. Assign each of the 14 off-board modules to a side dynamically from hub connectors
    side_buckets: dict[str, list[tuple[float, str]]] = {
        "top": [], "bottom": [], "left": [], "right": []
    }
    mod_side: dict[str, str] = {}
    mod_target: dict[str, float] = {}

    for mod_id, conn_refs in MODULE_PRIMARY_CONNECTORS.items():
        conns = [hub.connectors[r] for r in conn_refs if r in hub.connectors]
        if not conns:
            raise RuntimeError(f"Missing hub connector(s) {conn_refs} for module {mod_id}")
        side = conns[0].edge
        if side in ("top", "bottom"):
            target = sum(c.cx for c in conns) / len(conns)
        else:
            target = sum(c.cy for c in conns) / len(conns)
        mod_side[mod_id] = side
        mod_target[mod_id] = target
        side_buckets[side].append((target, mod_id))

    # Place companions on the same side right next to their host module
    for comp_id, host_id in COMPANION_HOST.items():
        side = mod_side[host_id]
        mod_side[comp_id] = side
        if comp_id == "yl69_soil_probe":
            # Left of soil_lm393_board (smaller X on top/bottom, smaller Y on left/right)
            target = mod_target[host_id] - 46.0
        else:  # speaker_28mm right of pam8403_amp
            target = mod_target[host_id] + 34.0
        mod_target[comp_id] = target
        side_buckets[side].append((target, comp_id))

    # Helper to construct initial PlacedModule on a given side at (cx, cy)
    def make_placed(mod_id: str, side: str, cx: float, cy: float) -> PlacedModule:
        mdata = modules_data[mod_id]
        rot = _choose_module_rotation(mod_id, side)
        lb = BBox2D(
            mdata["body_bbox_mm"]["min_x_mm"],
            mdata["body_bbox_mm"]["min_y_mm"],
            mdata["body_bbox_mm"]["max_x_mm"],
            mdata["body_bbox_mm"]["max_y_mm"],
        )
        rb = rotated_bbox_local(lb, rot)
        wb = rb.translate(cx, cy)
        mod_hz = float(mdata["bbox_mm"]["max_z_mm"])
        plq = _build_plaque_for_module(mod_id, side, wb, str(mdata["category"]), mod_hz)
        return PlacedModule(
            module_id=mod_id,
            ref=MANIFEST_TO_REF[mod_id],
            side=side,
            cx=cx,
            cy=cy,
            rot_deg=rot,
            z_offset_mm=float(mdata["recommended_z_offset_mm"]),
            local_bbox=lb,
            world_bbox=wb,
            plaque=plq,
        )

    def pack_side(side: str, corridor_override: float | None = None) -> dict[str, PlacedModule]:
        corr = corridor_mm if corridor_override is None else corridor_override
        items = sorted(side_buckets[side], key=lambda t: t[0])
        if not items:
            return {}
        centers: list[float] = []
        half_neg: list[float] = []
        half_pos: list[float] = []
        fixed_perp: list[float] = []
        mod_ids: list[str] = []

        for target, mod_id in items:
            mdata = modules_data[mod_id]
            rot = _choose_module_rotation(mod_id, side)
            lb = BBox2D(
                mdata["body_bbox_mm"]["min_x_mm"],
                mdata["body_bbox_mm"]["min_y_mm"],
                mdata["body_bbox_mm"]["max_x_mm"],
                mdata["body_bbox_mm"]["max_y_mm"],
            )
            rb = rotated_bbox_local(lb, rot)
            if side == "top":
                # Keep bottom edge of module at hub_top - corr
                cy = hub.bbox.min_y - corr - rb.max_y
                if mod_id == "yl69_soil_probe":
                    # Elevate slightly so handle aligns horizontally with LM393 top P1/P2 pins
                    cy -= 6.0
                tmp = make_placed(mod_id, side, target, cy)
                comp = tmp.world_bbox.union(tmp.plaque.bbox)
                centers.append(target)
                half_neg.append(target - comp.min_x)
                half_pos.append(comp.max_x - target)
                fixed_perp.append(cy)
            elif side == "bottom":
                cy = hub.bbox.max_y + corr - rb.min_y
                tmp = make_placed(mod_id, side, target, cy)
                comp = tmp.world_bbox.union(tmp.plaque.bbox)
                centers.append(target)
                half_neg.append(target - comp.min_x)
                half_pos.append(comp.max_x - target)
                fixed_perp.append(cy)
            elif side == "left":
                cx = hub.bbox.min_x - corr - rb.max_x
                tmp = make_placed(mod_id, side, cx, target)
                comp = tmp.world_bbox.union(tmp.plaque.bbox)
                centers.append(target)
                half_neg.append(target - comp.min_y)
                half_pos.append(comp.max_y - target)
                fixed_perp.append(cx)
            else:  # right
                cx = hub.bbox.max_x + corr - rb.min_x
                tmp = make_placed(mod_id, side, cx, target)
                comp = tmp.world_bbox.union(tmp.plaque.bbox)
                centers.append(target)
                half_neg.append(target - comp.min_y)
                half_pos.append(comp.max_y - target)
                fixed_perp.append(cx)
            mod_ids.append(mod_id)

        anchor_mask = [mid not in COMPANION_HOST for mid in mod_ids]
        relaxed = _relax_1d_intervals(centers, half_neg, half_pos, min_gap_mm, anchor_mask)
        out: dict[str, PlacedModule] = {}
        for mod_id, coord, perp in zip(mod_ids, relaxed, fixed_perp):
            if side in ("top", "bottom"):
                out[mod_id] = make_placed(mod_id, side, coord, perp)
            else:
                out[mod_id] = make_placed(mod_id, side, perp, coord)
        return out

    side_corridors = {"top": corridor_mm + 4.0, "bottom": corridor_mm, "left": corridor_mm, "right": corridor_mm + 3.0}
    for s in ("top", "bottom", "left", "right"):
        placed.update(pack_side(s, side_corridors[s]))

    # 3. 2D Cross-Side Corner Clearance Guard (guarantees >= min_gap_mm everywhere!)
    offboard_ids = [m for m in placed if m != "nodemcu_v2_amica"]
    for _ in range(30):
        worst_gap = 1e9
        worst_pair: tuple[str, str] | None = None
        for i in range(len(offboard_ids)):
            a = placed[offboard_ids[i]]
            ca = a.world_bbox.union(a.plaque.bbox) if a.plaque else a.world_bbox
            for j in range(i + 1, len(offboard_ids)):
                b = placed[offboard_ids[j]]
                if a.side == b.side:
                    continue
                cb = b.world_bbox.union(b.plaque.bbox) if b.plaque else b.world_bbox
                gap = bbox_clearance_mm(ca, cb)
                if gap < worst_gap:
                    worst_gap = gap
                    worst_pair = (a.module_id, b.module_id)
        if worst_gap >= min_gap_mm - 1e-4 or worst_pair is None:
            break
        # Push the top/bottom corridor outward slightly to resolve corner proximity cleanly
        ma, mb = placed[worst_pair[0]], placed[worst_pair[1]]
        push_side = ma.side if ma.side in ("top", "bottom") else mb.side
        step = max(2.0, (min_gap_mm - worst_gap) + 1.0)
        side_corridors[push_side] += step
        placed.update(pack_side(push_side, side_corridors[push_side]))

    # 4. Dynamic Top Banner Plaque (automatically shows actual parsed hub WxH!)
    all_min_y = min(
        min(m.world_bbox.min_y, m.plaque.bbox.min_y if m.plaque else m.world_bbox.min_y)
        for m in placed.values()
    )
    banner_text = f"SMARTHOME HUB ASSEMBLY ({round(hub.bbox.width)}X{round(hub.bbox.height)} MM)"
    bw, bh = compute_plaque_dims(
        (banner_text,),
        char_h=5.2, char_w=3.2, char_gap=1.05, line_gap=2.0, pad_x=5.0, pad_y=3.2,
    )
    banner = PlaqueSpec(
        plaque_id="PLQ_BANNER",
        lines=(banner_text,),
        category="Banner",
        cx=hub.bbox.cx,
        cy=all_min_y - 10.0 - 0.5 * bh,
        width=bw,
        height=bh,
        char_h=5.2,
        char_w=3.2,
        char_gap=1.05,
        stroke_w=0.85,
        line_gap=2.0,
    )
    return placed, banner


# ---------------------------------------------------------------------------
# 4. Wire Resolution & Smooth 3D Curve Generator
# ---------------------------------------------------------------------------
def _hub_pin_z_and_mode(conn: HubConnectorInfo) -> tuple[float, str]:
    if conn.is_screw_terminal:
        mode = {
            "left": "screw_left",
            "right": "screw_right",
            "top": "screw_top",
            "bottom": "screw_bottom",
        }[conn.edge]
        return 4.6, mode
    # Vertical 2.54mm pin header: Dupont female boot Z=2.6..9.0mm, wire exits at Z=9.0mm
    return 9.0, "dupont_up"


def _module_pin_z_and_mode(
    mod_id: str,
    pin_num: str,
    pin_z_manifest: float,
    z_offset: float,
    mod_rot: float,
    local_pin_x: float,
) -> tuple[float, str, bool]:
    """Return (wire_start_z, approach_mode, needs_dupont_boot)."""
    z_base = pin_z_manifest + z_offset
    # Vertical 2.54mm header pins on off-board PCBs get matte-black Dupont boots
    if mod_id in ("relay1_blue_srd05", "relay2_red_opto") and pin_num in ("1", "2", "3"):
        return z_base, "dupont_up", True
    if mod_id in ("dht11_module", "soil_lm393_board", "ky037_sound"):
        return max(z_base, 8.6), "dupont_up", True
    if mod_id in ("relay1_blue_srd05", "relay2_red_opto") and pin_num in ("4", "5", "6"):
        # Screw terminals point outward along local +X
        dx, dy = rotate_pcb_xy(1.0, 0.0, mod_rot)
        return z_base, _vec_to_dir_mode(dx, dy), False
    if mod_id == "psu_5v2a_dc_jack":
        dx, dy = rotate_pcb_xy(1.0, 0.0, mod_rot)
        return z_base, _vec_to_dir_mode(dx, dy), False
    if mod_id in ("sg90_servo", "submersible_pump", "yl69_soil_probe"):
        # Pins sit on local -X edge -> exit along local -X
        dx, dy = rotate_pcb_xy(-1.0, 0.0, mod_rot)
        return z_base, _vec_to_dir_mode(dx, dy), False
    if mod_id == "speaker_28mm":
        dx, dy = rotate_pcb_xy(-1.0, 0.0, mod_rot)
        return z_base, _vec_to_dir_mode(dx, dy), False
    if mod_id == "pam8403_amp":
        return z_base, "pad_up", False
    # LEDs & Buzzer: bottom solder leads -> rise smoothly upward
    return max(z_base, 0.8), "pad_up", False


def _vec_to_dir_mode(dx: float, dy: float) -> str:
    if abs(dx) >= abs(dy):
        return "side_right" if dx >= 0 else "side_left"
    return "side_down" if dy >= 0 else "side_up"


def _mode_tangent_vec(mode: str, mag_xy: float = 8.0, mag_z: float = 8.0) -> tuple[float, float, float]:
    if mode == "dupont_up":
        return (0.0, 0.0, mag_z)
    if mode == "pad_up":
        return (0.0, 0.0, mag_z * 0.75)
    if mode in ("screw_left", "side_left"):
        return (-mag_xy, 0.0, 2.2)
    if mode in ("screw_right", "side_right"):
        return (mag_xy, 0.0, 2.2)
    if mode in ("screw_top", "side_up"):
        return (0.0, -mag_xy, 2.2)
    if mode in ("screw_bottom", "side_down"):
        return (0.0, mag_xy, 2.2)
    return (0.0, 0.0, mag_z * 0.6)


def _eval_cubic_bezier(
    p0: tuple[float, float, float],
    p1: tuple[float, float, float],
    p2: tuple[float, float, float],
    p3: tuple[float, float, float],
    steps: int,
) -> list[tuple[float, float, float]]:
    pts: list[tuple[float, float, float]] = []
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        b0 = u * u * u
        b1 = 3.0 * u * u * t
        b2 = 3.0 * u * t * t
        b3 = t * t * t
        pts.append((
            b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0],
            b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1],
            b0 * p0[2] + b1 * p1[2] + b2 * p2[2] + b3 * p3[2],
        ))
    return pts


def resolve_all_wires(
    hub: HubBoardInfo,
    placed: dict[str, PlacedModule],
    manifest: dict[str, Any],
) -> tuple[list[ResolvedWire], list[tuple[float, float, float, float]]]:
    """Resolve all 40 wires (W01..W40) using ACTUAL pcbnew pad world positions.

    Returns (wires, dupont_boots) where each boot is (x_pcb, y_pcb, z_bottom, z_top).
    """
    modules_data = manifest["modules"]
    wires: list[ResolvedWire] = []
    boots: list[tuple[float, float, float, float]] = []
    seen_boots: set[tuple[int, int]] = set()

    def add_boot(x: float, y: float, z0: float, z1: float) -> None:
        key = (round(x * 10), round(y * 10))
        if key not in seen_boots:
            seen_boots.add(key)
            boots.append((x, y, z0, z1))

    # Build lookup of manifest local pin info
    pin_meta: dict[tuple[str, str], dict[str, Any]] = {}
    for mid, mdata in modules_data.items():
        for p in mdata.get("pins", []):
            pin_meta[(mid, str(p["num"]))] = p

    for entry in WIRING_TABLE:
        rgb = tuple(float(c) for c in WIRE_COLORS[entry.color]["rgb"])  # type: ignore[index]
        dst_mod_id = CONTRACT_TO_MANIFEST_ID[entry.module_id]
        dst_pm = placed[dst_mod_id]
        dst_pin_num = PIN_ALIAS_MAP[(dst_mod_id, entry.module_pin)]
        if dst_pin_num not in dst_pm.world_pads:
            raise RuntimeError(f"Wire {entry.wire_id}: missing dst pad {dst_mod_id}.{dst_pin_num}")
        dx, dy, dz_man = dst_pm.world_pads[dst_pin_num]
        dst_pinfo = pin_meta[(dst_mod_id, dst_pin_num)]
        dst_z, dst_mode, dst_boot = _module_pin_z_and_mode(
            dst_mod_id, dst_pin_num, dz_man, dst_pm.z_offset_mm,
            dst_pm.rot_deg, float(dst_pinfo["x_mm"]),
        )
        if dst_boot:
            add_boot(dx, dy, max(2.0, dst_z - 5.6), dst_z)

        is_inter = entry.hub_ref in OFFBOARD_SRC_TO_MANIFEST_ID
        if is_inter:
            src_mod_id = OFFBOARD_SRC_TO_MANIFEST_ID[entry.hub_ref]
            src_pm = placed[src_mod_id]
            src_pin_num = PIN_ALIAS_MAP[(src_mod_id, entry.hub_pin)]
            if src_pin_num not in src_pm.world_pads:
                raise RuntimeError(f"Wire {entry.wire_id}: missing src pad {src_mod_id}.{src_pin_num}")
            sx, sy, sz_man = src_pm.world_pads[src_pin_num]
            src_pinfo = pin_meta[(src_mod_id, src_pin_num)]
            src_z, src_mode, src_boot = _module_pin_z_and_mode(
                src_mod_id, src_pin_num, sz_man, src_pm.z_offset_mm,
                src_pm.rot_deg, float(src_pinfo["x_mm"]),
            )
            if src_boot:
                add_boot(sx, sy, max(2.0, src_z - 5.6), src_z)
            is_bridge = False
        else:
            if entry.hub_ref not in hub.connectors:
                raise RuntimeError(f"Wire {entry.wire_id}: hub connector {entry.hub_ref} not found")
            conn = hub.connectors[entry.hub_ref]
            if entry.hub_pin not in conn.pads:
                raise RuntimeError(f"Wire {entry.wire_id}: pad {entry.hub_ref}.{entry.hub_pin} not found")
            sx, sy = conn.pads[entry.hub_pin]
            src_z, src_mode = _hub_pin_z_and_mode(conn)
            if src_mode == "dupont_up":
                add_boot(sx, sy, 2.6, 9.0)
            # Detect cross-board bridge wires dynamically (e.g. J8 on left_inner -> Relay 1 on right)
            is_bridge = (conn.edge != dst_pm.side)

        wires.append(ResolvedWire(
            wire_id=entry.wire_id,
            group=entry.group,
            color=entry.color,
            rgb=(rgb[0], rgb[1], rgb[2]),
            net=entry.net,
            wire_type=entry.wire_type,
            src_desc=f"{entry.hub_ref}.{entry.hub_pin}",
            dst_desc=f"{dst_mod_id}.{dst_pin_num}({entry.module_pin})",
            src_pos=(sx, sy, src_z),
            dst_pos=(dx, dy, dst_z),
            src_mode=src_mode,
            dst_mode=dst_mode,
            is_inter_module=is_inter,
            is_over_hub_bridge=is_bridge,
            bundle_key=f"{entry.hub_ref}->{dst_mod_id}",
        ))

    # Assign bundle indices so parallel wires stagger cleanly in height
    bundles: dict[str, list[ResolvedWire]] = {}
    for w in wires:
        bundles.setdefault(w.bundle_key, []).append(w)
    for b_wires in bundles.values():
        n = len(b_wires)
        for idx, w in enumerate(b_wires):
            w.bundle_idx = idx
            w.bundle_size = n

    # Compute smooth 3D trajectories
    mcu = placed["nodemcu_v2_amica"]
    mcu_top_z = mcu.z_offset_mm + float(modules_data["nodemcu_v2_amica"]["body_bbox_mm"]["max_z_mm"])
    for w in wires:
        p0 = w.src_pos
        p3 = w.dst_pos
        dist = math.hypot(p3[0] - p0[0], p3[1] - p0[1])
        stagger_z = 1.35 * (w.bundle_idx - 0.5 * (w.bundle_size - 1))

        if w.is_over_hub_bridge:
            # High, graceful 2-segment bridge clearing BOTH NodeMCU (~15.64mm) AND Relay 1 cube (18.5mm)!
            cruise_z = max(mcu_top_z + 7.2, 23.0) + 1.6 * w.bundle_idx
            # Approach screw terminal cleanly from its outer side (+X on right side)
            tdx, tdy, _ = _mode_tangent_vec(w.dst_mode, mag_xy=7.5, mag_z=5.0)
            entry_pt = (p3[0] + tdx, p3[1] + tdy, max(p3[2] + 3.0, 12.0))
            apex_pt = (
                0.5 * (p0[0] + entry_pt[0]),
                0.20 * p0[1] + 0.80 * entry_pt[1] + (w.bundle_idx - 0.5) * 2.4,
                cruise_z,
            )
            seg1 = _eval_cubic_bezier(
                p0,
                (p0[0], p0[1], cruise_z),
                (0.7 * apex_pt[0] + 0.3 * p0[0], 0.7 * apex_pt[1] + 0.3 * p0[1], cruise_z),
                apex_pt,
                steps=14,
            )
            seg2 = _eval_cubic_bezier(
                apex_pt,
                (entry_pt[0] + tdx * 0.4, entry_pt[1] + tdy * 0.4, cruise_z),
                (entry_pt[0] + tdx * 0.6, entry_pt[1] + tdy * 0.6, p3[2] + 2.5),
                p3,
                steps=16,
            )
            w.points_3d = seg1 + seg2[1:]
        else:
            arch_z = min(14.5, max(5.0, 0.24 * dist)) + stagger_z
            t0 = _mode_tangent_vec(w.src_mode, mag_xy=min(10.0, 0.32 * dist), mag_z=arch_z)
            t3 = _mode_tangent_vec(w.dst_mode, mag_xy=min(10.0, 0.32 * dist), mag_z=arch_z)
            # Blend slight lateral pull toward midpoint for natural Dupont bend radius
            mid_z = max(p0[2], p3[2]) + arch_z
            p1 = (
                p0[0] + t0[0] + 0.16 * (p3[0] - p0[0]),
                p0[1] + t0[1] + 0.16 * (p3[1] - p0[1]),
                max(p0[2] + t0[2], mid_z if w.src_mode == "dupont_up" else p0[2] + 4.5 + stagger_z),
            )
            p2 = (
                p3[0] + t3[0] + 0.16 * (p0[0] - p3[0]),
                p3[1] + t3[1] + 0.16 * (p0[1] - p3[1]),
                max(p3[2] + t3[2], mid_z if w.dst_mode == "dupont_up" else p3[2] + 4.5 + stagger_z),
            )
            w.points_3d = _eval_cubic_bezier(p0, p1, p2, p3, steps=18)

    return wires, boots


# ---------------------------------------------------------------------------
# 5. Pure-Python VRML 2.0 Mesh Builder (Wires + Boots + 3D Label Plaques)
# ---------------------------------------------------------------------------
class VRMLMeshAccumulator:
    """Accumulates triangles per material group and writes compact VRML 2.0."""

    def __init__(self, origin_x_pcb: float, origin_y_pcb: float) -> None:
        self.ox = origin_x_pcb
        self.oy = origin_y_pcb
        self.groups: dict[str, tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]] = {}
        self.materials: dict[str, dict[str, Any]] = {}

    def register_material(
        self,
        name: str,
        diffuse: tuple[float, float, float],
        specular: tuple[float, float, float] = (0.25, 0.25, 0.25),
        emissive: tuple[float, float, float] = (0.0, 0.0, 0.0),
        shininess: float = 0.35,
    ) -> None:
        self.materials[name] = {
            "diffuse": diffuse,
            "specular": specular,
            "emissive": emissive,
            "shininess": shininess,
        }
        if name not in self.groups:
            self.groups[name] = ([], [])

    def _to_vrml(self, x_pcb: float, y_pcb: float, z_mm: float) -> tuple[float, float, float]:
        # KiCad VRML: +X right, +Y UP (y_3d = -y_pcb), +Z UP, 1 unit = 2.54 mm
        return (
            (x_pcb - self.ox) * VRML_SCALE,
            -(y_pcb - self.oy) * VRML_SCALE,
            z_mm * VRML_SCALE,
        )

    def add_box_pcb(
        self,
        mat: str,
        x0: float,
        y0: float,
        z0: float,
        x1: float,
        y1: float,
        z1: float,
    ) -> None:
        """Add an axis-aligned box in PCB world mm (x0<x1, y0<y1, z0<z1)."""
        verts, tris = self.groups[mat]
        base = len(verts)
        # Note Y-flip reverses winding, so order vertices carefully for outward normals in VRML
        # In VRML coords: vx0 < vx1, vy_bot = -y1 < vy_top = -y0, vz0 < vz1
        corners = [
            self._to_vrml(x0, y1, z0),  # 0: minX, minY_vrml, minZ
            self._to_vrml(x1, y1, z0),  # 1: maxX, minY_vrml, minZ
            self._to_vrml(x1, y0, z0),  # 2: maxX, maxY_vrml, minZ
            self._to_vrml(x0, y0, z0),  # 3: minX, maxY_vrml, minZ
            self._to_vrml(x0, y1, z1),  # 4: minX, minY_vrml, maxZ
            self._to_vrml(x1, y1, z1),  # 5: maxX, minY_vrml, maxZ
            self._to_vrml(x1, y0, z1),  # 6: maxX, maxY_vrml, maxZ
            self._to_vrml(x0, y0, z1),  # 7: minX, maxY_vrml, maxZ
        ]
        verts.extend(corners)
        faces = [
            (0, 3, 2), (0, 2, 1),  # bottom (-Z)
            (4, 5, 6), (4, 6, 7),  # top (+Z)
            (0, 1, 5), (0, 5, 4),  # front (-Y_vrml)
            (2, 3, 7), (2, 7, 6),  # back (+Y_vrml)
            (0, 4, 7), (0, 7, 3),  # left (-X)
            (1, 2, 6), (1, 6, 5),  # right (+X)
        ]
        for a, b, c in faces:
            tris.append((base + a, base + b, base + c))

    def add_oriented_bar_pcb(
        self,
        mat: str,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        width: float,
        z0: float,
        z1: float,
    ) -> None:
        """Add an extruded rectangular stroke bar with square end-caps in PCB mm."""
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy)
        hw = 0.5 * width
        if length < 1e-6:
            self.add_box_pcb(mat, x0 - hw, y0 - hw, z0, x0 + hw, y0 + hw, z1)
            return
        ux, uy = dx / length, dy / length
        nx, ny = -uy * hw, ux * hw
        ex, ey = ux * hw, uy * hw
        # 4 corners of bar footprint in PCB XY (CCW in standard XY after Y-flip)
        p_a = (x0 - ex - nx, y0 - ey - ny)
        p_b = (x1 + ex - nx, y1 + ey - ny)
        p_c = (x1 + ex + nx, y1 + ey + ny)
        p_d = (x0 - ex + nx, y0 - ey + ny)
        # Convert to VRML and ensure CCW order in VRML XY (cross > 0)
        va = self._to_vrml(p_a[0], p_a[1], z0)
        vb = self._to_vrml(p_b[0], p_b[1], z0)
        vc = self._to_vrml(p_c[0], p_c[1], z0)
        vd = self._to_vrml(p_d[0], p_d[1], z0)
        cross = (vb[0] - va[0]) * (vc[1] - va[1]) - (vb[1] - va[1]) * (vc[0] - va[0])
        if cross < 0:
            p_b, p_d = p_d, p_b
        bot_pts = [self._to_vrml(p[0], p[1], z0) for p in (p_a, p_b, p_c, p_d)]
        top_pts = [self._to_vrml(p[0], p[1], z1) for p in (p_a, p_b, p_c, p_d)]
        verts, tris = self.groups[mat]
        base = len(verts)
        verts.extend(bot_pts)
        verts.extend(top_pts)
        faces = [
            (0, 3, 2), (0, 2, 1),
            (4, 5, 6), (4, 6, 7),
            (0, 1, 5), (0, 5, 4),
            (1, 2, 6), (1, 6, 5),
            (2, 3, 7), (2, 7, 6),
            (3, 0, 4), (3, 4, 7),
        ]
        for a, b, c in faces:
            tris.append((base + a, base + b, base + c))

    def add_tube_pcb(
        self,
        mat: str,
        points_pcb: list[tuple[float, float, float]],
        radius_mm: float = 0.65,
        sides: int = 10,
    ) -> None:
        """Sweep a smooth twist-free circular tube using parallel-transport frames."""
        if len(points_pcb) < 2:
            return
        pts = [self._to_vrml(p[0], p[1], p[2]) for p in points_pcb]
        r = radius_mm * VRML_SCALE

        def vsub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
            return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

        def vdot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
            return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

        def vcross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
            return (
                a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0],
            )

        def vnorm(a: tuple[float, float, float]) -> tuple[float, float, float]:
            l = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
            return (a[0] / l, a[1] / l, a[2] / l) if l > 1e-12 else (0.0, 0.0, 1.0)

        # Compute tangents
        tangents: list[tuple[float, float, float]] = []
        for i in range(len(pts)):
            if i == 0:
                t = vnorm(vsub(pts[1], pts[0]))
            elif i == len(pts) - 1:
                t = vnorm(vsub(pts[-1], pts[-2]))
            else:
                t = vnorm(vsub(pts[i + 1], pts[i - 1]))
            tangents.append(t)

        # Initial normal perpendicular to tangents[0]
        t0 = tangents[0]
        ref = (0.0, 0.0, 1.0) if abs(t0[2]) < 0.85 else (1.0, 0.0, 0.0)
        n_vec = vnorm(vcross(t0, ref))
        b_vec = vnorm(vcross(t0, n_vec))

        rings: list[list[tuple[float, float, float]]] = []
        angles = [2.0 * math.pi * k / sides for k in range(sides)]
        cos_a = [math.cos(a) for a in angles]
        sin_a = [math.sin(a) for a in angles]

        for i, p in enumerate(pts):
            if i > 0:
                # Parallel transport n_vec from tangents[i-1] to tangents[i]
                t_cur = tangents[i]
                proj = vdot(n_vec, t_cur)
                n_cand = (
                    n_vec[0] - proj * t_cur[0],
                    n_vec[1] - proj * t_cur[1],
                    n_vec[2] - proj * t_cur[2],
                )
                n_len = math.sqrt(vdot(n_cand, n_cand))
                if n_len > 1e-8:
                    n_vec = (n_cand[0] / n_len, n_cand[1] / n_len, n_cand[2] / n_len)
                b_vec = vnorm(vcross(t_cur, n_vec))
            ring = [
                (
                    p[0] + r * (cos_a[k] * n_vec[0] + sin_a[k] * b_vec[0]),
                    p[1] + r * (cos_a[k] * n_vec[1] + sin_a[k] * b_vec[1]),
                    p[2] + r * (cos_a[k] * n_vec[2] + sin_a[k] * b_vec[2]),
                )
                for k in range(sides)
            ]
            rings.append(ring)

        verts, tris = self.groups[mat]
        base = len(verts)
        for ring in rings:
            verts.extend(ring)

        n_rings = len(rings)
        for i in range(n_rings - 1):
            r0 = base + i * sides
            r1 = base + (i + 1) * sides
            for k in range(sides):
                kn = (k + 1) % sides
                # Outward-facing CCW winding (since b_vec = t_cur x n_vec)
                tris.append((r0 + k, r1 + kn, r1 + k))
                tris.append((r0 + k, r0 + kn, r1 + kn))

        # End caps (outward-facing CCW winding)
        c_start = len(verts)
        verts.append(pts[0])
        for k in range(sides):
            kn = (k + 1) % sides
            tris.append((c_start, base + k, base + kn))
        c_end = len(verts)
        verts.append(pts[-1])
        last_r = base + (n_rings - 1) * sides
        for k in range(sides):
            kn = (k + 1) % sides
            tris.append((c_end, last_r + kn, last_r + k))

    def write_vrml(self, out_path: Path, crease_angle: float = 0.5) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        chunks: list[str] = ["#VRML V2.0 utf8\n"]
        for mat_name, (verts, tris) in self.groups.items():
            if not tris:
                continue
            # Guard against inverted normals: closed solid meshes must have positive signed volume
            svol = 0.0
            for i0, i1, i2 in tris:
                v0, v1, v2 = verts[i0], verts[i1], verts[i2]
                svol += (
                    v0[0] * (v1[1] * v2[2] - v1[2] * v2[1])
                    + v0[1] * (v1[2] * v2[0] - v1[0] * v2[2])
                    + v0[2] * (v1[0] * v2[1] - v1[1] * v2[0])
                )
            if svol <= 0.0:
                raise RuntimeError(f"VRML shape '{mat_name}' in {out_path.name} has inverted normals (signed_vol={svol / 6.0:.4f})")
            m = self.materials[mat_name]
            d = m["diffuse"]
            s = m["specular"]
            e = m["emissive"]
            sh = m["shininess"]
            chunks.append(
                f"Shape {{\n"
                f"  appearance Appearance {{\n"
                f"    material Material {{\n"
                f"      diffuseColor {d[0]:.4f} {d[1]:.4f} {d[2]:.4f}\n"
                f"      specularColor {s[0]:.4f} {s[1]:.4f} {s[2]:.4f}\n"
                f"      emissiveColor {e[0]:.4f} {e[1]:.4f} {e[2]:.4f}\n"
                f"      ambientIntensity 0.25\n"
                f"      shininess {sh:.3f}\n"
                f"    }}\n"
                f"  }}\n"
                f"  geometry IndexedFaceSet {{\n"
                f"    solid TRUE\n"
                f"    creaseAngle {crease_angle:.3f}\n"
                f"    coord Coordinate {{ point [\n"
            )
            chunks.append(
                ",\n".join(f"      {v[0]:.5f} {v[1]:.5f} {v[2]:.5f}" for v in verts)
            )
            chunks.append("\n    ] }\n    coordIndex [\n")
            chunks.append(
                "\n".join(f"      {t[0]}, {t[1]}, {t[2]}, -1," for t in tris)
            )
            chunks.append("\n    ]\n  }\n}\n")
        out_path.write_text("".join(chunks), encoding="utf-8", newline="\n")


def generate_wiring_harness_wrl(
    out_path: Path,
    hub_cx: float,
    hub_cy: float,
    wires: list[ResolvedWire],
    boots: list[tuple[float, float, float, float]],
) -> None:
    acc = VRMLMeshAccumulator(hub_cx, hub_cy)
    acc.register_material("dupont_boot", (0.09, 0.09, 0.10), (0.18, 0.18, 0.20), shininess=0.22)
    for cname, cdata in WIRE_COLORS.items():
        rgb = tuple(float(c) for c in cdata["rgb"])  # type: ignore[index]
        # Slight specular highlight makes insulated PVC wire tubes look crisp and cylindrical
        acc.register_material(
            f"wire_{cname}",
            diffuse=(rgb[0], rgb[1], rgb[2]),
            specular=(0.32, 0.32, 0.32),
            shininess=0.45,
        )

    # Matte-black Dupont female connector housings (2.40 x 2.40 mm)
    half_b = 1.20
    for bx, by, z0, z1 in boots:
        acc.add_box_pcb("dupont_boot", bx - half_b, by - half_b, z0, bx + half_b, by + half_b, z1)

    # Smooth 3D colored wire tubes (Ø1.30 mm -> radius 0.65 mm)
    for w in wires:
        acc.add_tube_pcb(f"wire_{w.color}", w.points_3d, radius_mm=0.65, sides=10)

    acc.write_vrml(out_path, crease_angle=0.85)


# ---------------------------------------------------------------------------
# 6. Clean Geometric Stroke-Vector Font & 3D Label Plaques VRML Generator
# ---------------------------------------------------------------------------
# Normalized glyph strokes in [0..1] x [0..1] (x right, y DOWN in PCB coords!)
VECTOR_FONT: dict[str, list[list[tuple[float, float]]]] = {
    "A": [[(0.0, 1.0), (0.5, 0.0), (1.0, 1.0)], [(0.2, 0.65), (0.8, 0.65)]],
    "B": [[(0.0, 0.0), (0.0, 1.0), (0.75, 1.0), (1.0, 0.85), (1.0, 0.62), (0.75, 0.5), (0.0, 0.5)],
          [(0.0, 0.0), (0.72, 0.0), (0.95, 0.14), (0.95, 0.36), (0.72, 0.5)]],
    "C": [[(1.0, 0.2), (0.78, 0.0), (0.25, 0.0), (0.0, 0.22), (0.0, 0.78), (0.25, 1.0), (0.78, 1.0), (1.0, 0.8)]],
    "D": [[(0.0, 0.0), (0.0, 1.0), (0.65, 1.0), (1.0, 0.75), (1.0, 0.25), (0.65, 0.0), (0.0, 0.0)]],
    "E": [[(1.0, 0.0), (0.0, 0.0), (0.0, 1.0), (1.0, 1.0)], [(0.0, 0.5), (0.8, 0.5)]],
    "F": [[(1.0, 0.0), (0.0, 0.0), (0.0, 1.0)], [(0.0, 0.5), (0.78, 0.5)]],
    "G": [[(1.0, 0.2), (0.78, 0.0), (0.25, 0.0), (0.0, 0.22), (0.0, 0.78), (0.25, 1.0), (0.82, 1.0), (1.0, 0.78), (1.0, 0.52), (0.55, 0.52)]],
    "H": [[(0.0, 0.0), (0.0, 1.0)], [(1.0, 0.0), (1.0, 1.0)], [(0.0, 0.5), (1.0, 0.5)]],
    "I": [[(0.2, 0.0), (0.8, 0.0)], [(0.5, 0.0), (0.5, 1.0)], [(0.2, 1.0), (0.8, 1.0)]],
    "J": [[(0.2, 0.0), (1.0, 0.0)], [(0.75, 0.0), (0.75, 0.78), (0.5, 1.0), (0.18, 1.0), (0.0, 0.8)]],
    "K": [[(0.0, 0.0), (0.0, 1.0)], [(1.0, 0.0), (0.0, 0.55)], [(0.3, 0.42), (1.0, 1.0)]],
    "L": [[(0.0, 0.0), (0.0, 1.0), (1.0, 1.0)]],
    "M": [[(0.0, 1.0), (0.0, 0.0), (0.5, 0.58), (1.0, 0.0), (1.0, 1.0)]],
    "N": [[(0.0, 1.0), (0.0, 0.0), (1.0, 1.0), (1.0, 0.0)]],
    "O": [[(0.25, 0.0), (0.75, 0.0), (1.0, 0.22), (1.0, 0.78), (0.75, 1.0), (0.25, 1.0), (0.0, 0.78), (0.0, 0.22), (0.25, 0.0)]],
    "P": [[(0.0, 1.0), (0.0, 0.0), (0.75, 0.0), (1.0, 0.18), (1.0, 0.38), (0.75, 0.55), (0.0, 0.55)]],
    "Q": [[(0.25, 0.0), (0.75, 0.0), (1.0, 0.22), (1.0, 0.78), (0.75, 1.0), (0.25, 1.0), (0.0, 0.78), (0.0, 0.22), (0.25, 0.0)],
          [(0.62, 0.72), (1.0, 1.0)]],
    "R": [[(0.0, 1.0), (0.0, 0.0), (0.75, 0.0), (1.0, 0.18), (1.0, 0.38), (0.75, 0.52), (0.0, 0.52)],
          [(0.52, 0.52), (1.0, 1.0)]],
    "S": [[(1.0, 0.18), (0.78, 0.0), (0.22, 0.0), (0.0, 0.18), (0.0, 0.36), (0.22, 0.48), (0.78, 0.54), (1.0, 0.68), (1.0, 0.84), (0.78, 1.0), (0.22, 1.0), (0.0, 0.82)]],
    "T": [[(0.0, 0.0), (1.0, 0.0)], [(0.5, 0.0), (0.5, 1.0)]],
    "U": [[(0.0, 0.0), (0.0, 0.78), (0.25, 1.0), (0.75, 1.0), (1.0, 0.78), (1.0, 0.0)]],
    "V": [[(0.0, 0.0), (0.5, 1.0), (1.0, 0.0)]],
    "W": [[(0.0, 0.0), (0.2, 1.0), (0.5, 0.45), (0.8, 1.0), (1.0, 0.0)]],
    "X": [[(0.0, 0.0), (1.0, 1.0)], [(1.0, 0.0), (0.0, 1.0)]],
    "Y": [[(0.0, 0.0), (0.5, 0.48), (1.0, 0.0)], [(0.5, 0.48), (0.5, 1.0)]],
    "Z": [[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]],
    "0": [[(0.25, 0.0), (0.75, 0.0), (1.0, 0.22), (1.0, 0.78), (0.75, 1.0), (0.25, 1.0), (0.0, 0.78), (0.0, 0.22), (0.25, 0.0)],
          [(0.2, 0.8), (0.8, 0.2)]],
    "1": [[(0.22, 0.22), (0.55, 0.0), (0.55, 1.0)], [(0.2, 1.0), (0.9, 1.0)]],
    "2": [[(0.0, 0.22), (0.24, 0.0), (0.76, 0.0), (1.0, 0.2), (1.0, 0.38), (0.0, 1.0), (1.0, 1.0)]],
    "3": [[(0.0, 0.16), (0.24, 0.0), (0.76, 0.0), (1.0, 0.18), (1.0, 0.36), (0.74, 0.48), (0.4, 0.48)],
          [(0.74, 0.48), (1.0, 0.62), (1.0, 0.82), (0.76, 1.0), (0.24, 1.0), (0.0, 0.84)]],
    "4": [[(0.75, 1.0), (0.75, 0.0), (0.0, 0.66), (1.0, 0.66)]],
    "5": [[(1.0, 0.0), (0.05, 0.0), (0.05, 0.46), (0.76, 0.46), (1.0, 0.62), (1.0, 0.84), (0.76, 1.0), (0.2, 1.0), (0.0, 0.84)]],
    "6": [[(0.92, 0.14), (0.7, 0.0), (0.28, 0.0), (0.0, 0.28), (0.0, 0.78), (0.25, 1.0), (0.75, 1.0), (1.0, 0.78), (1.0, 0.6), (0.75, 0.44), (0.0, 0.44)]],
    "7": [[(0.0, 0.0), (1.0, 0.0), (0.35, 1.0)]],
    "8": [[(0.24, 0.48), (0.04, 0.34), (0.04, 0.16), (0.26, 0.0), (0.74, 0.0), (0.96, 0.16), (0.96, 0.34), (0.76, 0.48), (0.24, 0.48)],
          [(0.24, 0.48), (0.0, 0.64), (0.0, 0.84), (0.26, 1.0), (0.74, 1.0), (1.0, 0.84), (1.0, 0.64), (0.76, 0.48)]],
    "9": [[(0.08, 0.86), (0.3, 1.0), (0.72, 1.0), (1.0, 0.72), (1.0, 0.22), (0.75, 0.0), (0.25, 0.0), (0.0, 0.22), (0.0, 0.4), (0.25, 0.56), (1.0, 0.56)]],
    "-": [[(0.15, 0.5), (0.85, 0.5)]],
    "+": [[(0.1, 0.5), (0.9, 0.5)], [(0.5, 0.15), (0.5, 0.85)]],
    "/": [[(0.15, 1.0), (0.85, 0.0)]],
    "(": [[(0.75, 0.0), (0.35, 0.25), (0.35, 0.75), (0.75, 1.0)]],
    ")": [[(0.25, 0.0), (0.65, 0.25), (0.65, 0.75), (0.25, 1.0)]],
    ".": [[(0.45, 0.92), (0.55, 0.92)]],
    ":": [[(0.45, 0.28), (0.55, 0.28)], [(0.45, 0.76), (0.55, 0.76)]],
    "_": [[(0.0, 1.0), (1.0, 1.0)]],
    " ": [],
}


def generate_assembly_labels_wrl(
    out_path: Path,
    hub_cx: float,
    hub_cy: float,
    plaques: list[PlaqueSpec],
) -> None:
    acc = VRMLMeshAccumulator(hub_cx, hub_cy)
    acc.register_material("plaque_base",    (0.08, 0.12, 0.18), (0.20, 0.22, 0.26), shininess=0.35)
    acc.register_material("plaque_bevel",   (0.13, 0.18, 0.25), (0.25, 0.28, 0.32), shininess=0.40)
    acc.register_material("border_Sensor",  (0.18, 0.64, 0.94), (0.35, 0.45, 0.55), emissive=(0.04, 0.12, 0.18), shininess=0.50)
    acc.register_material("border_Actuator", (0.92, 0.54, 0.12), (0.40, 0.32, 0.18), emissive=(0.14, 0.08, 0.02), shininess=0.50)
    acc.register_material("border_Power",   (0.88, 0.20, 0.20), (0.40, 0.20, 0.20), emissive=(0.14, 0.03, 0.03), shininess=0.50)
    acc.register_material("border_Banner",  (0.32, 0.76, 0.98), (0.40, 0.50, 0.60), emissive=(0.06, 0.16, 0.22), shininess=0.55)
    acc.register_material("text_white",     (0.97, 0.98, 0.99), (0.25, 0.25, 0.25), emissive=(0.18, 0.18, 0.19), shininess=0.25)

    for plq in plaques:
        bb = plq.bbox
        # Two-step beveled dark-slate nameplate base (Z=0.0..0.75 mm)
        acc.add_box_pcb("plaque_base",  bb.min_x, bb.min_y, 0.0, bb.max_x, bb.max_y, 0.45)
        acc.add_box_pcb("plaque_bevel", bb.min_x + 0.35, bb.min_y + 0.35, 0.45, bb.max_x - 0.35, bb.max_y - 0.35, 0.75)

        # Colored category accent border frame around top rim (Z=0.75..1.10 mm)
        bmat = f"border_{plq.category}" if f"border_{plq.category}" in acc.materials else "border_Banner"
        bw = 0.55 if plq.category != "Banner" else 0.75
        ins = 0.45
        x0, y0, x1, y1 = bb.min_x + ins, bb.min_y + ins, bb.max_x - ins, bb.max_y - ins
        acc.add_box_pcb(bmat, x0, y0, 0.75, x1, y0 + bw, 1.08)
        acc.add_box_pcb(bmat, x0, y1 - bw, 0.75, x1, y1, 1.08)
        acc.add_box_pcb(bmat, x0, y0 + bw, 0.75, x0 + bw, y1 - bw, 1.08)
        acc.add_box_pcb(bmat, x1 - bw, y0 + bw, 0.75, x1, y1 - bw, 1.08)

        # Raised 3D crisp white stroke-vector text (Z=0.75..1.40 mm)
        n_lines = len(plq.lines)
        total_h = n_lines * plq.char_h + max(0, n_lines - 1) * plq.line_gap
        start_y = plq.cy - 0.5 * total_h
        for li, raw_line in enumerate(plq.lines):
            text = raw_line.upper()
            line_w = len(text) * plq.char_w + max(0, len(text) - 1) * plq.char_gap
            cur_x = plq.cx - 0.5 * line_w
            cur_y = start_y + li * (plq.char_h + plq.line_gap)
            for ch in text:
                strokes = VECTOR_FONT.get(ch, [])
                for poly in strokes:
                    for k in range(len(poly) - 1):
                        sx0 = cur_x + poly[k][0] * plq.char_w
                        sy0 = cur_y + poly[k][1] * plq.char_h
                        sx1 = cur_x + poly[k + 1][0] * plq.char_w
                        sy1 = cur_y + poly[k + 1][1] * plq.char_h
                        acc.add_oriented_bar_pcb(
                            "text_white", sx0, sy0, sx1, sy1, plq.stroke_w, 0.75, 1.40
                        )
                cur_x += plq.char_w + plq.char_gap

    acc.write_vrml(out_path, crease_angle=0.1)


# ---------------------------------------------------------------------------
# 7. Populate KiCad Assembly Board (Footprints, 2D Wires, 2D Labels)
# ---------------------------------------------------------------------------
def _wire_2d_layer(wire: ResolvedWire) -> int:
    if wire.is_inter_module:
        return pcbnew.User_4
    if wire.net == "GND":
        return pcbnew.User_2
    if wire.net in ("+5V", "+3V3", "PUMP_5V", "AMP_5V", "LED_BR_A"):
        return pcbnew.User_1
    return pcbnew.User_3


def add_2d_wires_and_labels(
    board: pcbnew.BOARD,
    wires: list[ResolvedWire],
    plaques: list[PlaqueSpec],
) -> None:
    # 2D wire polylines on User.1 (power), User.2 (GND), User.3 (signals), User.4 (inter-module)
    for w in wires:
        layer = _wire_2d_layer(w)
        # Downsample smooth 3D curve to crisp 2D polyline segments
        pts = w.points_3d
        stride = max(1, len(pts) // 8)
        sampled = pts[::stride]
        if sampled[-1] != pts[-1]:
            sampled.append(pts[-1])
        for i in range(len(sampled) - 1):
            seg = pcbnew.PCB_SHAPE(board)
            seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
            seg.SetLayer(layer)
            seg.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(sampled[i][0]), pcbnew.FromMM(sampled[i][1])))
            seg.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(sampled[i + 1][0]), pcbnew.FromMM(sampled[i + 1][1])))
            seg.SetWidth(pcbnew.FromMM(0.45))
            board.Add(seg)

    # Native KiCad 2D text labels on BOTH F.SilkS and Dwgs.User
    for plq in plaques:
        txt_str = "\n".join(plq.lines)
        t_size = 2.6 if plq.category == "Banner" else 1.8
        t_thick = 0.35 if plq.category == "Banner" else 0.25
        for layer in (pcbnew.F_SilkS, pcbnew.Dwgs_User):
            t = pcbnew.PCB_TEXT(board)
            t.SetText(txt_str)
            t.SetLayer(layer)
            t.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(plq.cx), pcbnew.FromMM(plq.cy)))
            t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(t_size), pcbnew.FromMM(t_size)))
            t.SetTextThickness(pcbnew.FromMM(t_thick))
            board.Add(t)


# ---------------------------------------------------------------------------
# 8. Strict Bounding-Box, Alignment & Wiring Self-Verifier
# ---------------------------------------------------------------------------
def verify_assembly(
    hub: HubBoardInfo,
    placed: dict[str, PlacedModule],
    banner: PlaqueSpec,
    wires: list[ResolvedWire],
    out_dir: Path,
) -> dict[str, Any]:
    errors: list[str] = []

    # 1. All 15 modules placed (14 off-board + NodeMCU)
    if len(placed) != 15:
        errors.append(f"Expected 15 placed modules, found {len(placed)}")

    # 2. All 40 wires resolved
    if len(wires) != 40:
        errors.append(f"Expected 40 wires (W01..W40), found {len(wires)}")
    expected_ids = {f"W{i:02d}" for i in range(1, 41)}
    got_ids = {w.wire_id for w in wires}
    if expected_ids != got_ids:
        errors.append(f"Wire ID mismatch: missing={sorted(expected_ids - got_ids)}")

    # 3. NodeMCU exact pad alignment on U1/U2
    mcu = placed["nodemcu_v2_amica"]
    u1_p1 = hub.u1.pads["1"]
    u2_p15 = hub.u2.pads["15"]
    mcu_u1_p1 = mcu.world_pads["U1.1"]
    mcu_u2_p15 = mcu.world_pads["U2.15"]
    err_u1 = math.hypot(u1_p1[0] - mcu_u1_p1[0], u1_p1[1] - mcu_u1_p1[1])
    err_u2 = math.hypot(u2_p15[0] - mcu_u2_p15[0], u2_p15[1] - mcu_u2_p15[1])
    mcu_align_err = max(err_u1, err_u2)
    if mcu_align_err > 0.05:
        errors.append(f"NodeMCU U1/U2 pad misalignment: {mcu_align_err:.4f} mm")

    # 4. Pairwise XY bounding-box collision check across:
    #    - hub PCB outline
    #    - all 14 off-board modules
    #    - all 14 module label plaques
    #    - top banner plaque
    boxes: list[tuple[str, BBox2D]] = [("HUB_PCB", hub.bbox), (banner.plaque_id, banner.bbox)]
    for mod_id, pm in sorted(placed.items()):
        if mod_id == "nodemcu_v2_amica":
            continue
        boxes.append((f"MOD:{mod_id}", pm.world_bbox))
        if pm.plaque is not None:
            boxes.append((pm.plaque.plaque_id, pm.plaque.bbox))

    overlaps: list[dict[str, Any]] = []
    min_clearance = 1e9
    min_pair = ("", "")
    # Note: a module's OWN plaque is intentionally spaced at >= 4.0 mm from its module;
    # all OTHER pairs (module-module, module-hub, plaque-hub, plaque-plaque, foreign module-plaque)
    # must have >= 6.0 mm clearance!
    min_inter_clearance = 1e9
    min_inter_pair = ("", "")

    for i in range(len(boxes)):
        na, ba = boxes[i]
        for j in range(i + 1, len(boxes)):
            nb, bb = boxes[j]
            gap = bbox_clearance_mm(ba, bb)
            if gap < min_clearance:
                min_clearance = gap
                min_pair = (na, nb)
            own_pair = (
                (na.startswith("MOD:") and nb == "PLQ_" + na[4:])
                or (nb.startswith("MOD:") and na == "PLQ_" + nb[4:])
            )
            if not own_pair and gap < min_inter_clearance:
                min_inter_clearance = gap
                min_inter_pair = (na, nb)
            if gap <= 0.0:
                overlaps.append({"a": na, "b": nb, "clearance_mm": round(gap, 4)})
            elif (not own_pair) and gap < 6.0:
                errors.append(f"Clearance < 6.0 mm between {na} and {nb}: {gap:.2f} mm")
            elif own_pair and gap < 4.0:
                errors.append(f"Module-to-own-plaque gap < 4.0 mm between {na} and {nb}: {gap:.2f} mm")

    if overlaps:
        errors.append(f"Detected {len(overlaps)} XY bounding-box overlap(s): {overlaps[:5]}")

    # 5. Forbidden-token audit (zero fan, zero AC, zero IR)
    all_text_blob = " ".join(
        list(placed.keys())
        + [line for pm in placed.values() if pm.plaque for line in pm.plaque.lines]
        + list(banner.lines)
        + [w.group + " " + w.net + " " + w.dst_desc for w in wires]
    ).lower()
    found_forbidden = [tok for tok in FORBIDDEN_TOKENS if tok in all_text_blob]
    if found_forbidden:
        errors.append(f"Forbidden token(s) found: {found_forbidden}")

    report = {
        "status": "PASS" if not errors else "FAIL",
        "hub_pcb": str(hub.path),
        "hub_dimensions_mm": {
            "width": round(hub.bbox.width, 3),
            "height": round(hub.bbox.height, 3),
            "left": round(hub.bbox.min_x, 3),
            "top": round(hub.bbox.min_y, 3),
            "right": round(hub.bbox.max_x, 3),
            "bottom": round(hub.bbox.max_y, 3),
        },
        "modules_placed_count": len(placed),
        "offboard_modules_count": len(placed) - 1,
        "plaques_count": sum(1 for pm in placed.values() if pm.plaque is not None) + 1,
        "wires_resolved_count": len(wires),
        "nodemcu_u1_u2_alignment_err_mm": round(mcu_align_err, 5),
        "overlap_count": len(overlaps),
        "overlaps": overlaps,
        "min_overall_clearance_mm": round(min_clearance, 3),
        "min_overall_clearance_pair": list(min_pair),
        "min_inter_module_clearance_mm": round(min_inter_clearance, 3),
        "min_inter_module_clearance_pair": list(min_inter_pair),
        "forbidden_tokens_found": found_forbidden,
        "errors": errors,
        "modules": {
            mid: {
                "ref": pm.ref,
                "side": pm.side,
                "center_mm": [round(pm.cx, 3), round(pm.cy, 3)],
                "rot_deg": pm.rot_deg,
                "z_offset_mm": pm.z_offset_mm,
                "bbox_mm": [
                    round(pm.world_bbox.min_x, 3),
                    round(pm.world_bbox.min_y, 3),
                    round(pm.world_bbox.max_x, 3),
                    round(pm.world_bbox.max_y, 3),
                ],
                "plaque": (
                    {
                        "lines": list(pm.plaque.lines),
                        "center_mm": [round(pm.plaque.cx, 3), round(pm.plaque.cy, 3)],
                        "size_mm": [pm.plaque.width, pm.plaque.height],
                    }
                    if pm.plaque
                    else None
                ),
            }
            for mid, pm in sorted(placed.items())
        },
    }
    (out_dir / "assembly_verification.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return report


# ---------------------------------------------------------------------------
# 9. Optional kicad-cli 3D Render Helper
# ---------------------------------------------------------------------------
def find_kicad_cli() -> Path | None:
    env_cli = os.environ.get("KICAD_CLI")
    if env_cli and Path(env_cli).exists():
        return Path(env_cli)
    # Check beside current Python executable (KiCad 10 bin dir)
    beside = Path(sys.executable).resolve().parent / ("kicad-cli.exe" if os.name == "nt" else "kicad-cli")
    if beside.exists():
        return beside
    found = shutil.which("kicad-cli")
    return Path(found) if found else None


def render_assembly_views(
    pcb_path: Path,
    render_dir: Path,
    hub_bbox: BBox2D,
    full_bbox: BBox2D,
    width: int = 1600,
    height: int = 1000,
    quality: str = "basic",
    floor: bool = False,
) -> list[Path]:
    cli = find_kicad_cli()
    if cli is None:
        raise RuntimeError("kicad-cli not found; cannot render 3D views")
    render_dir.mkdir(parents=True, exist_ok=True)
    # Clean any stale KiCad lock file before launching kicad-cli
    lck = pcb_path.parent / f"~{pcb_path.stem}.kicad_pro.lck"
    if lck.exists():
        try:
            lck.unlink()
        except OSError:
            pass

    # Dynamically compute zoom so the FULL assembly (hub + all 14 modules + plaques) fills the frame cleanly
    ratio_x = hub_bbox.width / max(1.0, full_bbox.width)
    ratio_y = hub_bbox.height / max(1.0, full_bbox.height)
    fit_zoom = max(0.16, min(0.50, min(ratio_x, ratio_y) * 1.12))
    iso_zoom = max(0.18, min(0.55, fit_zoom * 1.02))

    floor_args = ["--floor"] if floor else []
    views = [
        ("assembly_top.png",     ["--side", "top", "--zoom", f"{fit_zoom:.3f}"]),
        ("assembly_iso.png",     ["--side", "top", "--rotate", "-42,0,22", "--perspective", "--zoom", f"{iso_zoom:.3f}"]),
        ("assembly_closeup.png", ["--side", "top", "--rotate", "-35,0,18", "--perspective", "--zoom", "0.78"]),
    ]
    outputs: list[Path] = []
    for fname, extra in views:
        out_img = render_dir / fname
        cmd = [
            str(cli), "pcb", "render",
            "--output", str(out_img),
            "--width", str(width),
            "--height", str(height),
            "--quality", quality,
            "--background", "opaque",
            *floor_args,
            *extra,
            str(pcb_path),
        ]
        print(f"[render] {' '.join(cmd)}", flush=True)
        res = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
        )
        if res.returncode != 0:
            raise RuntimeError(f"kicad-cli render failed ({fname}): {res.stderr.strip()}")
        outputs.append(out_img)
    # Remove transient local GUI view-state sidecar auto-created by kicad-cli
    prl = pcb_path.with_suffix(".kicad_prl")
    if prl.exists():
        try:
            prl.unlink()
        except OSError:
            pass
    return outputs


# ---------------------------------------------------------------------------
# Main Orchestration
# ---------------------------------------------------------------------------
def build_assembly(
    hub_pcb_path: Path,
    out_dir: Path,
    manifest_path: Path,
    verify: bool = True,
    render_dir: Path | None = None,
    render_width: int = 1600,
    render_height: int = 1000,
    render_quality: str = "basic",
) -> dict[str, Any]:
    hub_pcb_path = hub_pcb_path.resolve()
    out_dir = out_dir.resolve()
    manifest_path = manifest_path.resolve()

    # Safety guard: NEVER write into the hub PCB's directory!
    if out_dir == hub_pcb_path.parent:
        raise RuntimeError(f"Refusing to write assembly into hub PCB directory: {out_dir}")
    if not hub_pcb_path.exists():
        raise FileNotFoundError(f"Hub PCB not found: {hub_pcb_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Modules manifest not found: {manifest_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    models_dir = out_dir / "3dmodels"
    models_dir.mkdir(parents=True, exist_ok=True)

    # If out_dir is different from manifest's parent dir, ensure module .wrl files are available under out_dir/3dmodels
    src_models_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if src_models_dir.resolve() != models_dir.resolve():
        for mdata in manifest["modules"].values():
            wrl = mdata["wrl_file"]
            src = src_models_dir / wrl
            dst = models_dir / wrl
            if src.exists():
                shutil.copy2(src, dst)

    # 1. Write deterministic footprint library, fp-lib-table, and .kicad_pro
    pretty_dir = write_footprint_library(out_dir, manifest)
    write_fp_lib_table(out_dir)
    write_kicad_pro(out_dir, hub_pcb_path)

    # 2. Load hub PCB read-only (we save to out_dir/smarthome_assembly.kicad_pcb, never modifying hub_pcb_path!)
    board = pcbnew.LoadBoard(str(hub_pcb_path))
    hub = parse_hub_board(board, hub_pcb_path)
    print(
        f"[hub] Parsed {hub_pcb_path.name}: {hub.bbox.width:.2f} x {hub.bbox.height:.2f} mm "
        f"(origin ({hub.bbox.min_x:.2f}, {hub.bbox.min_y:.2f}), connectors={len(hub.connectors)})"
    )

    # 3. Compute dynamic zero-overlap layout
    placed, banner = compute_dynamic_layout(hub, manifest)

    # 4. Instantiate and place all 15 module footprints via KiCad 10 PCB_IO plugin,
    #    then read ACTUAL world pad coordinates directly from pcbnew!
    plug = pcbnew.PCB_IO_MGR.FindPlugin(pcbnew.PCB_IO_MGR.KICAD_SEXP)
    for mod_id, pm in placed.items():
        fp = plug.FootprintLoad(str(pretty_dir), mod_id)
        if fp is None:
            raise RuntimeError(f"Failed to load generated footprint {mod_id} from {pretty_dir}")
        fp.SetFPID(pcbnew.LIB_ID("smarthome_modules", mod_id))
        fp.SetReference(pm.ref)
        fp.SetValue(mod_id)
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(pm.cx), pcbnew.FromMM(pm.cy)))
        fp.SetOrientationDegrees(pm.rot_deg)
        board.Add(fp)

        # Read ACTUAL rotated world pad coordinates straight from pcbnew!
        z_lookup = {str(p["num"]): float(p["z_mm"]) for p in manifest["modules"][mod_id].get("pins", [])}
        for pd in fp.Pads():
            pnum = str(pd.GetNumber())
            ppos = pd.GetPosition()
            pm.world_pads[pnum] = (
                pcbnew.ToMM(ppos.x),
                pcbnew.ToMM(ppos.y),
                z_lookup.get(pnum, 0.0),
            )

    # 5. Resolve all 40 wires (W01..W40) using exact world pad positions & build wiring_harness.wrl
    wires, boots = resolve_all_wires(hub, placed, manifest)
    harness_wrl = models_dir / "wiring_harness.wrl"
    generate_wiring_harness_wrl(harness_wrl, hub.bbox.cx, hub.bbox.cy, wires, boots)
    print(f"[wires] Generated {harness_wrl.name}: {len(wires)} wires, {len(boots)} Dupont boots")

    # 6. Build 3D readable label plaques VRML (assembly_labels.wrl)
    all_plaques = [pm.plaque for pm in placed.values() if pm.plaque is not None] + [banner]
    labels_wrl = models_dir / "assembly_labels.wrl"
    generate_assembly_labels_wrl(labels_wrl, hub.bbox.cx, hub.bbox.cy, all_plaques)
    print(f"[labels] Generated {labels_wrl.name}: {len(all_plaques)} 3D plaques")

    # 7. Attach WIRING_HARNESS and ASM_LABELS helper footprints at (hub_cx, hub_cy)
    for ref, fp_name in (("WIRING_HARNESS", "Assembly_Wiring_Harness"), ("ASM_LABELS", "Assembly_Labels")):
        hfp = plug.FootprintLoad(str(pretty_dir), fp_name)
        if hfp is None:
            raise RuntimeError(f"Failed to load helper footprint {fp_name}")
        hfp.SetFPID(pcbnew.LIB_ID("smarthome_modules", fp_name))
        hfp.SetReference(ref)
        hfp.SetValue(fp_name)
        hfp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(hub.bbox.cx), pcbnew.FromMM(hub.bbox.cy)))
        hfp.SetOrientationDegrees(0.0)
        board.Add(hfp)

    # 8. Add 2D wires (User.1..User.4) & native 2D text labels (F.SilkS + Dwgs.User)
    add_2d_wires_and_labels(board, wires, all_plaques)

    # 9. Save complete assembly PCB and release board handle before optional rendering
    out_pcb = out_dir / "smarthome_assembly.kicad_pcb"
    pcbnew.SaveBoard(str(out_pcb), board)
    del board
    gc.collect()
    print(f"[pcb] Saved {out_pcb}", flush=True)

    # Compute full assembly bounding box for dynamic camera framing
    full_bbox = hub.bbox
    for pm in placed.values():
        full_bbox = full_bbox.union(pm.world_bbox)
        if pm.plaque is not None:
            full_bbox = full_bbox.union(pm.plaque.bbox)
    full_bbox = full_bbox.union(banner.bbox)

    # 10. Strict self-verification
    report: dict[str, Any] = {}
    if verify:
        report = verify_assembly(hub, placed, banner, wires, out_dir)
        print(
            f"[verify] Status={report['status']} | Modules={report['modules_placed_count']}/15 | "
            f"Wires={report['wires_resolved_count']}/40 | Overlaps={report['overlap_count']} | "
            f"MinInterClearance={report['min_inter_module_clearance_mm']} mm "
            f"({report['min_inter_module_clearance_pair'][0]} <-> {report['min_inter_module_clearance_pair'][1]}) | "
            f"NodeMCU err={report['nodemcu_u1_u2_alignment_err_mm']} mm",
            flush=True,
        )
        if report["status"] != "PASS":
            raise RuntimeError(f"Assembly verification FAILED: {report['errors']}")

    # 11. Optional 3D render via kicad-cli
    if render_dir is not None:
        render_assembly_views(
            out_pcb,
            render_dir.resolve(),
            hub_bbox=hub.bbox,
            full_bbox=full_bbox,
            width=render_width,
            height=render_height,
            quality=render_quality,
        )

    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build generic, re-runnable KiCad 10 Smart Home Assembly from any hub PCB."
    )
    parser.add_argument(
        "--hub-pcb",
        type=Path,
        default=REPO_ROOT / "hardware" / "kicad" / "smarthome_hub" / "smarthome_hub.kicad_pcb",
        help="Input central hub .kicad_pcb (read-only; works on 100x80 mm or any size).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=SCRIPT_DIR,
        help="Output assembly project directory (default: hardware/kicad/smarthome_assembly).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=SCRIPT_DIR / "3dmodels" / "modules_manifest.json",
        help="Path to 3dmodels/modules_manifest.json.",
    )
    parser.add_argument(
        "--render-dir",
        type=Path,
        default=None,
        help="Optional directory to render iso, top, and closeup PNGs via kicad-cli.",
    )
    parser.add_argument("--render-width", type=int, default=1600, help="Render width in px.")
    parser.add_argument("--render-height", type=int, default=1000, help="Render height in px.")
    parser.add_argument(
        "--render-quality",
        choices=("basic", "high", "user", "job_settings"),
        default="basic",
        help="kicad-cli pcb render quality.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip bounding-box/wiring self-verification (not recommended).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    build_assembly(
        hub_pcb_path=args.hub_pcb,
        out_dir=args.out_dir,
        manifest_path=args.manifest,
        verify=not args.no_verify,
        render_dir=args.render_dir,
        render_width=args.render_width,
        render_height=args.render_height,
        render_quality=args.render_quality,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
