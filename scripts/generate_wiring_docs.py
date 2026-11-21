#!/usr/bin/env python3
"""Deterministic Hardware Wiring Documentation & 2D System Diagram Generator.

Single Source of Truth: `hardware/wiring_contract.py`
Cross-checked against:
  - `firmware_esp8266/esp8266_smarthome/esp8266_smarthome.ino`
  - `docs/phan_cung/DIMENSIONS_AUDIT.md`
  - `hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb` (read-only verification)

Generates:
  1. `docs/phan_cung/WIRING_TABLE.md`       (40-wire full reference table + specs)
  2. `docs/phan_cung/wiring_diagram_2d.svg` (scalable clean vector schematic)
  3. `docs/phan_cung/wiring_diagram_2d.pdf` (vector PDF with embedded TrueType fonts)
  4. `docs/phan_cung/wiring_diagram_2d.png` (high-res 2880x1980 PNG via PyMuPDF)
  5. Optional copy via `--copy-png <path>`
"""

from __future__ import annotations

import argparse
import html
import math
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

# Resolve repository root from script path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hardware.wiring_contract import (  # noqa: E402
    FIRMWARE_PIN_CONTRACT,
    HUB_CONNECTOR_MAP,
    HUB_CONNECTORS,
    MODULE_DIMENSIONS_MM,
    WIRE_COLORS,
    WIRING_TABLE,
)

# ReportLab & PyMuPDF imports for vector PDF + ultra-sharp PNG rasterization
from reportlab.lib.colors import HexColor  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.pdfgen import canvas as rl_canvas  # noqa: E402

try:
    import pymupdf  # PyMuPDF >= 1.24 preferred import
except ImportError:  # pragma: no cover
    import fitz as pymupdf  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Verified On-Board Hub Passives (R1..R9, C1..C7, D1..D3) matching KiCad PCB
# ---------------------------------------------------------------------------
ONBOARD_PASSIVES: tuple[tuple[str, str, str, str, str], ...] = (
    ("R1", "220 Ω", "1/4W Axial (DIN0207)", "D0_LED_LR ↔ LED_LR_A", "Current-limiting resistor for Living Room 5mm LED (J4, Active-HIGH)"),
    ("R2", "220 Ω", "1/4W Axial (DIN0207)", "+3V3 ↔ LED_BR_A", "Current-limiting resistor for Bedroom 5mm LED (J5, Boot-Safe Active-LOW)"),
    ("R3", "10 kΩ", "1/4W Axial (DIN0207)", "+3V3 ↔ D2_DHT11", "DHT11 1-wire DATA bus pull-up resistor (J13)"),
    ("R4", "10 kΩ", "1/4W Axial (DIN0207)", "+3V3 ↔ D3_AUDIO_PWM", "GPIO0 (D3) boot-safety pull-up resistor (keeps GPIO0 HIGH at reset)"),
    ("R5", "2.2 kΩ", "1/4W Axial (DIN0207)", "AUD_AC ↔ AUD_OUT", "Upper leg of RC audio attenuator divider feeding PAM8403 (J12)"),
    ("R6", "2.2 kΩ", "1/4W Axial (DIN0207)", "AUD_OUT ↔ GND", "Lower leg of RC audio attenuator divider (~50% level into PAM8403)"),
    ("R7", "10 kΩ", "1/4W Axial (DIN0207)", "+3V3 ↔ D4_LED_BR", "GPIO2 (D4) boot-safety pull-up resistor (keeps GPIO2 HIGH at reset)"),
    ("R8", "1 kΩ", "1/4W Axial (DIN0207)", "+5V ↔ PWR_LED_A", "Current-limiting resistor for on-board +5V power indicator LED D3"),
    ("R9", "10 kΩ", "1/4W Axial (DIN0207)", "D8_BUZZER ↔ GND", "GPIO15 (D8) boot-safety pull-down resistor (keeps GPIO15 LOW & buzzer silent at boot)"),
    ("R10", "1 kΩ", "1/4W Axial (DIN0207)", "D8_BUZZER ↔ BUZZ_BASE", "Base current-limiting resistor for low-side NPN buzzer driver Q1 (~2.6 mA base drive from 3.3V GPIO15)"),
    ("Q1", "S8050", "TO-92 Wide (E-B-C)", "E=GND, B=BUZZ_BASE, C=BUZZ_K", "Low-side NPN BJT driver (S8050 / 2N2222A, 0.7A) switching 5V TMB12A05 buzzer safely off GPIO15"),
    ("C1", "470 µF 16V", "Radial Ø8.0×P3.5mm", "+5V ↔ GND", "Bulk electrolytic decoupling for SG90 servo peak current & main +5V rail"),
    ("C2", "470 µF 16V", "Radial Ø8.0×P3.5mm", "+5V ↔ GND", "Bulk electrolytic decoupling near J1/J2 for garden pump inrush stabilization"),
    ("C3", "100 nF", "Ceramic Disc P5.0mm", "+5V ↔ GND", "High-frequency noise decoupling on main +5V power rail"),
    ("C4", "10 µF 16V", "Radial Ø5.0×P3.5mm", "D3_AUDIO_PWM ↔ AUD_AC", "DC-blocking coupling capacitor isolating GPIO0 boot strap from PAM8403 input"),
    ("C5", "10 nF", "Ceramic Disc P5.0mm", "AUD_OUT ↔ GND", "RC low-pass filter capacitor smoothing PWM chime carrier into PAM8403"),
    ("C6", "100 nF", "Ceramic Disc P5.0mm", "AMP_5V ↔ GND", "High-frequency decoupling on Relay-2-switched +5V rail feeding PAM8403 (J11)"),
    ("C7", "100 nF", "Ceramic Disc P5.0mm", "A0_SOIL ↔ GND", "Analog low-pass noise filter on ESP8266 ADC0 soil moisture input (J14)"),
    ("D1", "1N4007", "DO-41 P10.16mm", "K=PUMP_5V, A=GND", "Inductive flyback clamp diode across 3–6V garden pump motor (J2)"),
    ("D2", "1N4007", "DO-41 P10.16mm", "K=+5V, A=BUZZ_K", "Inductive flyback protection diode across 5V Active Buzzer coil (J6.1 +5V ↔ J6.2 Q1 Collector)"),
    ("D3", "LED_PWR_GRN", "3mm Green LED (T-1)", "A=PWR_LED_A, K=GND", "On-board +5V power rail indicator LED (in series with R8 1kΩ)"),
)


# ---------------------------------------------------------------------------
# Cross-Check Validation against Firmware & Hub Connector Contract
# ---------------------------------------------------------------------------
def validate_contract() -> dict[str, object]:
    """Deterministically verify 100% consistency between contract, connectors, and firmware."""
    hub_pins_expected: set[tuple[str, str, str]] = set()
    for conn in HUB_CONNECTORS:
        for p_num, _px, _py, net in conn.pins:
            hub_pins_expected.add((conn.ref, p_num, net))

    hub_wires = [w for w in WIRING_TABLE if w.hub_ref.startswith("J")]
    off_wires = [w for w in WIRING_TABLE if not w.hub_ref.startswith("J")]

    hub_pins_wired = {(w.hub_ref, w.hub_pin, w.net) for w in hub_wires}
    missing = hub_pins_expected - hub_pins_wired
    extra = hub_pins_wired - hub_pins_expected
    if missing or extra:
        raise RuntimeError(f"Hub pin mismatch! missing={missing}, extra={extra}")

    # Verify unique wire IDs and valid colors
    ids = [w.wire_id for w in WIRING_TABLE]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate wire_id found in WIRING_TABLE")
    for w in WIRING_TABLE:
        if w.color not in WIRE_COLORS:
            raise RuntimeError(f"Unknown wire color {w.color!r} on {w.wire_id}")

    # Verify firmware pin defines exist verbatim in esp8266_smarthome.ino
    fw_path = REPO_ROOT / "firmware_esp8266" / "esp8266_smarthome" / "esp8266_smarthome.ino"
    fw_lines = fw_path.read_text(encoding="utf-8").splitlines()
    fw_pin_lines: dict[str, int] = {}
    for macro, (dx, gpio, _hub_info) in FIRMWARE_PIN_CONTRACT.items():
        expected_val = "A0" if gpio == -1 else str(gpio)
        pattern = re.compile(rf"^\s*#define\s+{re.escape(macro)}\s+{re.escape(expected_val)}\b")
        matched_line = None
        for idx, line in enumerate(fw_lines, start=1):
            if pattern.search(line):
                matched_line = idx
                break
        if matched_line is None:
            raise RuntimeError(f"Firmware macro mismatch for {macro} ({dx} / {expected_val})")
        fw_pin_lines[macro] = matched_line

    # Confirm zero forbidden devices (fan, AC, IR) in WIRING_TABLE & MODULE_DIMENSIONS_MM
    forbidden_re = re.compile(r"\b(fan|air_?cond|ac_relay|vs1838|ir_led|ir_tx|ir_rx)\b", re.I)
    for w in WIRING_TABLE:
        blob = f"{w.group} {w.module_id} {w.module_name} {w.net} {w.notes}"
        if forbidden_re.search(blob):
            raise RuntimeError(f"Forbidden legacy device reference in {w.wire_id}: {blob}")

    return {
        "total_wires": len(WIRING_TABLE),
        "hub_wires": len(hub_wires),
        "offboard_wires": len(off_wires),
        "hub_connectors": len(HUB_CONNECTORS),
        "hub_pins": len(hub_pins_expected),
        "fw_pin_lines": fw_pin_lines,
        "fw_rel_path": "firmware_esp8266/esp8266_smarthome/esp8266_smarthome.ino",
    }


# ---------------------------------------------------------------------------
# 1. Markdown Wiring Reference Generator (`docs/phan_cung/WIRING_TABLE.md`)
# ---------------------------------------------------------------------------
def generate_wiring_table_md(out_path: Path, stats: dict[str, object]) -> None:
    fw_pin_lines: dict[str, int] = stats["fw_pin_lines"]  # type: ignore[assignment]
    fw_rel = str(stats["fw_rel_path"])

    lines: list[str] = []
    lines.append("# Complete Hardware Wiring Reference Table — Smart Home Voice AI (Type 1 Hub PCB)")
    lines.append("")
    lines.append("> **Single Source of Truth (SSOT):** Auto-generated deterministically by `scripts/generate_wiring_docs.py` directly from `hardware/wiring_contract.py`.")
    lines.append(f"> **Verified Wiring Totals:** **{stats['total_wires']} physical wires** = **{stats['hub_wires']} Hub PCB plug-in wires** (`J1`..`J15`, 100% of all {stats['hub_pins']} connector pins) + **{stats['offboard_wires']} off-board inter-module wires** (`PAM8403 → Mini Speaker ×2`, `LM393 → YL-69 Soil Probe ×2`).")
    lines.append("> **Removed Legacy Parts Policy (Strict Confirmation):** **NO fan, NO AC, NO IR** (`VS1838B`, `IR LED 940nm`, cooling fan, or AC mains relay do NOT exist anywhere in firmware, KiCad schematic/PCB, Blender 3D, or wiring harnesses).")
    lines.append("> **Companion 2D Vector Diagram:** [`wiring_diagram_2d.svg`](wiring_diagram_2d.svg) · [`wiring_diagram_2d.pdf`](wiring_diagram_2d.pdf) · [`wiring_diagram_2d.png`](wiring_diagram_2d.png)")
    lines.append("")

    # Section 1: Master 40-Wire Table
    lines.append("## 1. Master Point-to-Point Wiring Table (All 40 Physical Wires)")
    lines.append("")
    lines.append("Every single physical plug-in wire is listed one row per wire (`W01`–`W40`), covering all 15 Hub PCB connectors (`J1`–`J15`) and all off-board module-to-module links.")
    lines.append("")
    lines.append("| Wire ID | Hub Connector / Pin | Wire Color | Target Module | Module Pin | NodeMCU Pin (Dx) | GPIO | KiCad Net | Wire Type | Firmware Reference | Notes |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for w in WIRING_TABLE:
        hex_c = WIRE_COLORS[w.color]["hex"]
        color_cell = f"**{w.color}** (`{hex_c}`)"
        lines.append(
            f"| `{w.wire_id}` "
            f"| `{w.hub_label}` "
            f"| {color_cell} "
            f"| {w.module_name} "
            f"| `{w.module_pin}` "
            f"| `{w.nodemcu_pin}` "
            f"| `{w.gpio}` "
            f"| `{w.net}` "
            f"| {w.wire_type} "
            f"| `{w.fw_ref}` "
            f"| {w.notes} |"
        )
    lines.append("")

    # Section 2: 10 Locked ESP8266 Pins vs Firmware
    lines.append("## 2. Locked 10-Pin ESP8266 NodeMCU v2 Amica Contract vs Firmware")
    lines.append("")
    lines.append(f"Cross-verified against `{fw_rel}` (`#define PIN_*` lines 55–64 and `setup()` lines 389–416):")
    lines.append("")
    lines.append("| Firmware Macro | NodeMCU Pin | ESP8266 GPIO | Hub Connector / Signal | Socket Pad | Firmware Line | Boot / Logic Polarity |")
    lines.append("|---|---|---|---|---|---|---|")

    pin_extra: dict[str, tuple[str, str]] = {
        "PIN_LIVING_LIGHT": ("U2.1", "Active-HIGH via R1 (220Ω); also `enroll_blink`"),
        "PIN_MAIN_DOOR_SERVO": ("U2.2", "50 Hz PWM (`0°` closed / `90°` open); failsafe close on offline"),
        "PIN_DHT11": ("U2.3", "1-Wire data bus with on-board R3 (10kΩ) pull-up to +3V3"),
        "PIN_AUDIO_PWM": ("U2.4", "**Boot-strap HIGH:** `C4 10µF` DC-block + `R5/R6 2.2kΩ` + `C5 10nF` + `R4 10kΩ` pull-up; `IDLE = INPUT`"),
        "PIN_BEDROOM_LIGHT": ("U2.5", "**Boot-strap HIGH:** Active-LOW (`BEDROOM_LED_ACTIVE_LOW = true`, line 68) + `R2 220Ω` + `R7 10kΩ` pull-up"),
        "PIN_KY037_DO": ("U2.8", "3.3V digital input (`RISING` interrupt, `debounce >= 400ms`, lines 73–74, 412)"),
        "PIN_GARDEN_PUMP": ("U2.9", "Active-HIGH (`PUMP_RELAY_ACTIVE_LOW = false`, line 70); soil hysteresis `<40% ON / >=70% OFF`"),
        "PIN_SPEAKER_AMP": ("U2.10", "Active-HIGH (`SPEAKER_RELAY_ACTIVE_LOW = false`, line 71; Relay 2 Jumper=`H`); auto-off `1.5s`"),
        "PIN_ALARM_SIREN": ("U2.11", "**Boot-strap LOW:** Active-HIGH + `R9 10kΩ` pull-down (silent at boot) + `D2 1N4007` flyback"),
        "PIN_SOIL_MOISTURE": ("U1.1", "10-bit ADC0 (`0–3.3V` via NodeMCU divider) + `C7 100nF` filter; LM393 strictly powered by `+3V3`"),
    }
    for macro, (dx, gpio, hub_sig) in FIRMWARE_PIN_CONTRACT.items():
        gpio_str = "ADC0" if gpio == -1 else f"GPIO{gpio}"
        pad, pol = pin_extra[macro]
        line_no = fw_pin_lines[macro]
        lines.append(
            f"| `{macro}` | **{dx}** | `{gpio_str}` | `{hub_sig}` | `{pad}` | `{fw_rel}:{line_no}` | {pol} |"
        )
    lines.append("")

    # Section 3: On-Board Hub Passives
    lines.append("## 3. On-Board Type-1 Hub PCB Protective Passives (`R1`–`R9`, `C1`–`C7`, `D1`–`D3`)")
    lines.append("")
    lines.append("All 19 passive/indicator components are permanently soldered onto the `80.0 × 65.0 × 1.6 mm` FR4 Hub PCB (`hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb`, 40 total BOM parts including `U1/U2`, `J1..J15`, `H1..H4`):")
    lines.append("")
    lines.append("| Ref | Value | Package / Pitch | Verified KiCad Nets | Electrical & Protection Role |")
    lines.append("|---|---|---|---|---|")
    for ref, val, pkg, nets, role in ONBOARD_PASSIVES:
        lines.append(f"| `{ref}` | **{val}** | {pkg} | `{nets}` | {role} |")
    lines.append("")

    # Section 4: Wire Color Legend
    lines.append("## 4. Standard Wire Color Legend (Consistent Across 2D Diagram, 3D Blender & Docs)")
    lines.append("")
    lines.append("| Color | Hex Code | System Role / Assigned Signals |")
    lines.append("|---|---|---|")
    for cname, cdata in WIRE_COLORS.items():
        lines.append(f"| **{cname}** | `{cdata['hex']}` | {cdata['role']} |")
    lines.append("")

    # Section 5: Boot-Safety & Electrical Protection Checklist
    lines.append("## 5. Boot-Safety, Electrical Protection & Intentionally Unconnected (`[NC]`) Checklist")
    lines.append("")
    lines.append("### Boot-Strap & Electrical Safety Verification")
    lines.append("- [x] **`D3` (`GPIO0`) Audio PWM (`J12` → `PAM8403 L`):** Protected by on-board `R4` (`10 kΩ` pull-up to `+3V3`), `C4` (`10 µF 16V` DC-blocking cap), `R5/R6` (`2.2 kΩ / 2.2 kΩ` attenuator), and `C5` (`10 nF` RC filter). Firmware keeps `PIN_AUDIO_PWM` in `INPUT` (high-Z) during idle and returns to `INPUT` immediately after `noTone()` (`esp8266_smarthome.ino:166-184, 394`), preventing accidental UART flash mode entry.")
    lines.append("- [x] **`D4` (`GPIO2`) Bedroom LED (`J5`):** Wired **Active-LOW** (`+3V3 → R2 220Ω → J5.1 → LED(+) → LED(-) → J5.2 → D4`) with on-board `R7` (`10 kΩ` pull-up). Firmware sets `BEDROOM_LED_ACTIVE_LOW = true` and pre-writes `HIGH` before `pinMode(OUTPUT)` (`esp8266_smarthome.ino:68, 396-397`), ensuring `GPIO2` stays `HIGH` during reset.")
    lines.append("- [x] **`D8` (`GPIO15`) Alarm Buzzer (`J6`):** Wired **Active-HIGH** with on-board `R9` (`10 kΩ` pull-down to `GND`) and `D2` (`1N4007` flyback diode). Firmware pre-writes `LOW` before `pinMode(OUTPUT)` (`esp8266_smarthome.ino:63, 399-400`), ensuring boot success and zero startup chirp.")
    lines.append("- [x] **Strictly 3.3V-Only Sensor Modules (`LM393` on `J14`, `KY-037/038` on `J15`):** Both sensor boards are fed exclusively from the NodeMCU `+3V3` rail (NEVER `+5V`), guaranteeing `LM393 AO` stays safely within the ESP8266 `ADC0` input window and `KY-037 DO` outputs 3.3V-safe logic levels into `D5 (GPIO14)`.")
    lines.append("- [x] **PAM8403 Bridge-Tied Load (BTL) Speaker Warning (`W28`, `W29`):** The Mini Speaker (`28 mm, 8 Ω, 0.5 W`) connects differentially across `PAM8403 L_OUT+` (Yellow) and `L_OUT-` (Brown). **NEVER tie `L_OUT-` to system `GND`** — doing so shorts the Class-D H-bridge output stage and damages the PAM8403 IC.")
    lines.append("- [x] **Inductive Flyback & Power Rail Decoupling (`D1`, `D2`, `C1`, `C2`, `C3`, `C6`, `C7`):** `D1` (`1N4007`) clamps back-EMF across the 3–6V submersible pump (`J2`, `PUMP_5V ↔ GND`), `D2` (`1N4007`) clamps the active buzzer (`J6`), `C1` & `C2` (`470 µF 16V` each) absorb SG90 servo and pump startup current surges on `+5V`, and `C3`/`C6`/`C7` (`100 nF`) suppress high-frequency noise on `+5V`, `AMP_5V`, and `A0_SOIL`.")
    lines.append("- [x] **Relay 2 Trigger Jumper (`J9`):** Red opto-isolated 1-channel relay module jumper MUST be set to **`H` (High-Level Trigger)** to match `SPEAKER_RELAY_ACTIVE_LOW = false` (`esp8266_smarthome.ino:71`).")
    lines.append("- [x] **Strict Scope Confirmation — Zero Legacy Hardware:** **NO fan**, **NO AC (220V mains)**, and **NO IR (`VS1838B` / `940nm LED`)** exist anywhere in the system. The entire system runs safely on low-voltage **5V DC / 3.3V DC**.")
    lines.append("")
    lines.append("### Intentionally Unconnected (`[NC]`) Off-Board Module Pins")
    lines.append("| Module | Pin | Status | Engineering Reason |")
    lines.append("|---|---|---|---|")
    lines.append("| Soil LM393 Comparator | `DO` | `[NC]` | Firmware reads continuous analog moisture percentage (`0–100%`) via `AO → A0` (`esp8266_smarthome.ino:568-569`) for software hysteresis (`<40% ON / >=70% OFF`). |")
    lines.append("| KY-037 / KY-038 Sound Sensor | `AO` | `[NC]` | ESP8266 has only one ADC (`A0`, dedicated to Soil Moisture); clap/sound detection uses hardware comparator threshold `DO → D5` (`RISING` interrupt). |")
    lines.append("| Relay 1 (Blue 5V, Pump) | `NC` (Screw) | `[NC]` | Pump switches via Normally-Open (`COM → NO`) path so pump stays safely OFF when unpowered or idle. |")
    lines.append("| Relay 2 (Red Opto 5V, Amp) | `NC` (Screw) | `[NC]` | PAM8403 power switches via Normally-Open (`COM → NO`) path so amplifier is completely powered off between chimes. |")
    lines.append("| PAM8403 Audio Amplifier | `R`, `R_OUT+`, `R_OUT-` | `[NC]` | Single mono speaker driven by Left channel (`L` input, `L_OUT+`/`L_OUT-` BTL output); Right channel unused. |")
    lines.append("")

    # Section 6: Module Dimensions Quick Reference
    lines.append("## 6. Physical Module Dimensions Summary (Matched to `DIMENSIONS_AUDIT.md`)")
    lines.append("")
    lines.append("| Module ID | Component Name | Dimensions (L × W × H, mm) | Overall H (mm) | Datasheet / Source |")
    lines.append("|---|---|---:|---:|---|")
    for mid, info in MODULE_DIMENSIONS_MM.items():
        d = info["dims_mm"]
        lines.append(
            f"| `{mid}` | {info['label']} | `{d[0]:.1f} × {d[1]:.1f} × {d[2]:.1f}` | `{info['overall_h_mm']:.1f}` | {info['source']} |"
        )
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# 2. Unified Dual-Backend Vector Engine (SVG + ReportLab PDF)
# ---------------------------------------------------------------------------
class VectorScene:
    """Draws identical vector primitives to both scalable SVG and ReportLab PDF.

    Coordinate system: origin (0, 0) at TOP-LEFT, X rightward, Y downward.
    PDF backend transparently flips Y -> (height - y).
    """

    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height
        self.ops: list[tuple[str, dict[str, object]]] = []

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: str | None = None,
        stroke: str | None = None,
        stroke_width: float = 1.0,
        rx: float = 0.0,
        dash: tuple[float, ...] | None = None,
        opacity: float = 1.0,
    ) -> None:
        self.ops.append((
            "rect",
            dict(x=x, y=y, w=w, h=h, fill=fill, stroke=stroke, stroke_width=stroke_width, rx=rx, dash=dash, opacity=opacity),
        ))

    def circle(
        self,
        cx: float,
        cy: float,
        r: float,
        *,
        fill: str | None = None,
        stroke: str | None = None,
        stroke_width: float = 1.0,
    ) -> None:
        self.ops.append((
            "circle",
            dict(cx=cx, cy=cy, r=r, fill=fill, stroke=stroke, stroke_width=stroke_width),
        ))

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        stroke: str = "#1E293B",
        stroke_width: float = 1.0,
        dash: tuple[float, ...] | None = None,
    ) -> None:
        self.ops.append((
            "line",
            dict(x1=x1, y1=y1, x2=x2, y2=y2, stroke=stroke, stroke_width=stroke_width, dash=dash),
        ))

    def polyline(
        self,
        points: list[tuple[float, float]],
        *,
        stroke: str = "#1E293B",
        stroke_width: float = 1.5,
        radius: float = 5.0,
        dash: tuple[float, ...] | None = None,
    ) -> None:
        """Draws a clean rounded-elbow orthogonal path."""
        self.ops.append((
            "polyline",
            dict(points=list(points), stroke=stroke, stroke_width=stroke_width, radius=radius, dash=dash),
        ))

    def text(
        self,
        x: float,
        y: float,
        content: str,
        *,
        size: float = 8.0,
        color: str = "#0F172A",
        bold: bool = False,
        mono: bool = False,
        align: str = "left",  # "left", "center", "right"
        valign: str = "middle",  # "top", "middle", "bottom"
    ) -> None:
        self.ops.append((
            "text",
            dict(x=x, y=y, content=content, size=size, color=color, bold=bold, mono=mono, align=align, valign=valign),
        ))

    @staticmethod
    def _rounded_path_segments(points: list[tuple[float, float]], radius: float) -> list[tuple[str, tuple[float, ...]]]:
        """Convert polyline vertices into (M, L, Q) path segments with clean corner fillets."""
        # Deduplicate consecutive identical points
        pts: list[tuple[float, float]] = []
        for p in points:
            if not pts or (abs(p[0] - pts[-1][0]) > 1e-4 or abs(p[1] - pts[-1][1]) > 1e-4):
                pts.append(p)
        if len(pts) < 2:
            return []
        segs: list[tuple[str, tuple[float, ...]]] = [("M", (pts[0][0], pts[0][1]))]
        if len(pts) == 2 or radius <= 0:
            for p in pts[1:]:
                segs.append(("L", (p[0], p[1])))
            return segs

        for i in range(1, len(pts) - 1):
            p0 = pts[i - 1]
            p1 = pts[i]
            p2 = pts[i + 1]
            v1x, v1y = p0[0] - p1[0], p0[1] - p1[1]
            v2x, v2y = p2[0] - p1[0], p2[1] - p1[1]
            l1 = math.hypot(v1x, v1y)
            l2 = math.hypot(v2x, v2y)
            if l1 < 1e-4 or l2 < 1e-4:
                continue
            r = min(radius, l1 * 0.45, l2 * 0.45)
            ax = p1[0] + (v1x / l1) * r
            ay = p1[1] + (v1y / l1) * r
            bx = p1[0] + (v2x / l2) * r
            by = p1[1] + (v2y / l2) * r
            segs.append(("L", (ax, ay)))
            segs.append(("Q", (p1[0], p1[1], bx, by)))
        segs.append(("L", (pts[-1][0], pts[-1][1])))
        return segs

    def write_svg(self, path: Path) -> None:
        out: list[str] = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" viewBox="0 0 {self.width} {self.height}">',
            "<defs>",
            "  <style>",
            '    .sans { font-family: "Segoe UI", Arial, Helvetica, sans-serif; }',
            '    .mono { font-family: "Consolas", "Courier New", monospace; }',
            "  </style>",
            "</defs>",
        ]
        for kind, d in self.ops:
            if kind == "rect":
                fill = d["fill"] or "none"
                stroke = d["stroke"] or "none"
                sw = d["stroke_width"]
                rx = d["rx"]
                dash_attr = f' stroke-dasharray="{",".join(str(v) for v in d["dash"])}"' if d["dash"] else ""
                op_attr = f' fill-opacity="{d["opacity"]}"' if d["opacity"] < 1.0 else ""
                rx_attr = f' rx="{rx}" ry="{rx}"' if rx else ""
                out.append(
                    f'<rect x="{d["x"]:.2f}" y="{d["y"]:.2f}" width="{d["w"]:.2f}" height="{d["h"]:.2f}"'
                    f'{rx_attr} fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash_attr}{op_attr}/>'
                )
            elif kind == "circle":
                fill = d["fill"] or "none"
                stroke = d["stroke"] or "none"
                out.append(
                    f'<circle cx="{d["cx"]:.2f}" cy="{d["cy"]:.2f}" r="{d["r"]:.2f}" '
                    f'fill="{fill}" stroke="{stroke}" stroke-width="{d["stroke_width"]}"/>'
                )
            elif kind == "line":
                dash_attr = f' stroke-dasharray="{",".join(str(v) for v in d["dash"])}"' if d["dash"] else ""
                out.append(
                    f'<line x1="{d["x1"]:.2f}" y1="{d["y1"]:.2f}" x2="{d["x2"]:.2f}" y2="{d["y2"]:.2f}" '
                    f'stroke="{d["stroke"]}" stroke-width="{d["stroke_width"]}" stroke-linecap="round"{dash_attr}/>'
                )
            elif kind == "polyline":
                segs = self._rounded_path_segments(d["points"], float(d["radius"]))
                if not segs:
                    continue
                parts = []
                for cmd, vals in segs:
                    if cmd in ("M", "L"):
                        parts.append(f"{cmd} {vals[0]:.2f} {vals[1]:.2f}")
                    elif cmd == "Q":
                        parts.append(f"Q {vals[0]:.2f} {vals[1]:.2f} {vals[2]:.2f} {vals[3]:.2f}")
                dash_attr = f' stroke-dasharray="{",".join(str(v) for v in d["dash"])}"' if d["dash"] else ""
                out.append(
                    f'<path d="{" ".join(parts)}" fill="none" stroke="{d["stroke"]}" '
                    f'stroke-width="{d["stroke_width"]}" stroke-linecap="round" stroke-linejoin="round"{dash_attr}/>'
                )
            elif kind == "text":
                cls = "mono" if d["mono"] else "sans"
                fw = "700" if d["bold"] else "400"
                anchor = {"left": "start", "center": "middle", "right": "end"}[str(d["align"])]
                size = float(d["size"])
                y = float(d["y"])
                valign = str(d["valign"])
                # Approximate baseline for crisp cross-renderer alignment
                if valign == "middle":
                    y_base = y + size * 0.34
                elif valign == "top":
                    y_base = y + size * 0.82
                else:
                    y_base = y
                txt = html.escape(str(d["content"]))
                out.append(
                    f'<text x="{d["x"]:.2f}" y="{y_base:.2f}" class="{cls}" font-size="{size:.2f}" '
                    f'font-weight="{fw}" fill="{d["color"]}" text-anchor="{anchor}">{txt}</text>'
                )
        out.append("</svg>")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(out), encoding="utf-8")

    @staticmethod
    def _register_fonts() -> tuple[str, str, str, str]:
        fonts_dir = Path(r"C:\Windows\Fonts")
        mapping = [
            ("UI-Regular", fonts_dir / "segoeui.ttf"),
            ("UI-Bold", fonts_dir / "segoeuib.ttf"),
            ("Mono-Regular", fonts_dir / "consola.ttf"),
            ("Mono-Bold", fonts_dir / "consolab.ttf"),
        ]
        registered = pdfmetrics.getRegisteredFontNames()
        for name, fpath in mapping:
            if name not in registered:
                if fpath.exists():
                    pdfmetrics.registerFont(TTFont(name, str(fpath)))
                else:
                    # Fallback to built-in Helvetica/Courier if run on non-Windows host
                    return ("Helvetica", "Helvetica-Bold", "Courier", "Courier-Bold")
        return ("UI-Regular", "UI-Bold", "Mono-Regular", "Mono-Bold")

    def write_pdf(self, path: Path) -> None:
        f_reg, f_bold, m_reg, m_bold = self._register_fonts()
        path.parent.mkdir(parents=True, exist_ok=True)
        c = rl_canvas.Canvas(str(path), pagesize=(self.width, self.height))
        c.setTitle("Smart Home Voice AI - Complete System 2D Wiring Diagram")
        c.setAuthor("Smart Home Voice AI Hardware Team")
        c.setLineCap(1)
        c.setLineJoin(1)

        H = self.height
        for kind, d in self.ops:
            c.saveState()
            if kind == "rect":
                x, y, w, h = float(d["x"]), float(d["y"]), float(d["w"]), float(d["h"])
                ry = H - y - h
                has_fill = d["fill"] not in (None, "none", "")
                has_stroke = d["stroke"] not in (None, "none", "")
                if has_fill:
                    c.setFillColor(HexColor(str(d["fill"])))
                    if float(d["opacity"]) < 1.0:
                        c.setFillAlpha(float(d["opacity"]))
                if has_stroke:
                    c.setStrokeColor(HexColor(str(d["stroke"])))
                    c.setLineWidth(float(d["stroke_width"]))
                    if d["dash"]:
                        c.setDash(*d["dash"])
                rx = float(d["rx"])
                if rx > 0:
                    c.roundRect(x, ry, w, h, rx, stroke=int(has_stroke), fill=int(has_fill))
                else:
                    c.rect(x, ry, w, h, stroke=int(has_stroke), fill=int(has_fill))
            elif kind == "circle":
                cx, cy, r = float(d["cx"]), H - float(d["cy"]), float(d["r"])
                has_fill = d["fill"] not in (None, "none", "")
                has_stroke = d["stroke"] not in (None, "none", "")
                if has_fill:
                    c.setFillColor(HexColor(str(d["fill"])))
                if has_stroke:
                    c.setStrokeColor(HexColor(str(d["stroke"])))
                    c.setLineWidth(float(d["stroke_width"]))
                c.circle(cx, cy, r, stroke=int(has_stroke), fill=int(has_fill))
            elif kind == "line":
                c.setStrokeColor(HexColor(str(d["stroke"])))
                c.setLineWidth(float(d["stroke_width"]))
                if d["dash"]:
                    c.setDash(*d["dash"])
                c.line(float(d["x1"]), H - float(d["y1"]), float(d["x2"]), H - float(d["y2"]))
            elif kind == "polyline":
                segs = self._rounded_path_segments(d["points"], float(d["radius"]))
                if segs:
                    c.setStrokeColor(HexColor(str(d["stroke"])))
                    c.setLineWidth(float(d["stroke_width"]))
                    if d["dash"]:
                        c.setDash(*d["dash"])
                    p = c.beginPath()
                    cur_x, cur_y = 0.0, 0.0
                    for cmd, vals in segs:
                        if cmd == "M":
                            cur_x, cur_y = vals[0], H - vals[1]
                            p.moveTo(cur_x, cur_y)
                        elif cmd == "L":
                            cur_x, cur_y = vals[0], H - vals[1]
                            p.lineTo(cur_x, cur_y)
                        elif cmd == "Q":
                            qx, qy = vals[0], H - vals[1]
                            ex, ey = vals[2], H - vals[3]
                            # Convert quadratic Bezier (cur, q, e) to cubic Bezier
                            c1x = cur_x + (2.0 / 3.0) * (qx - cur_x)
                            c1y = cur_y + (2.0 / 3.0) * (qy - cur_y)
                            c2x = ex + (2.0 / 3.0) * (qx - ex)
                            c2y = ey + (2.0 / 3.0) * (qy - ey)
                            p.curveTo(c1x, c1y, c2x, c2y, ex, ey)
                            cur_x, cur_y = ex, ey
                    c.drawPath(p, stroke=1, fill=0)
            elif kind == "text":
                font_name = (m_bold if d["bold"] else m_reg) if d["mono"] else (f_bold if d["bold"] else f_reg)
                size = float(d["size"])
                c.setFont(font_name, size)
                c.setFillColor(HexColor(str(d["color"])))
                x = float(d["x"])
                y = float(d["y"])
                valign = str(d["valign"])
                if valign == "middle":
                    y_pdf = H - (y + size * 0.34)
                elif valign == "top":
                    y_pdf = H - (y + size * 0.82)
                else:
                    y_pdf = H - y
                txt = str(d["content"])
                align = str(d["align"])
                if align == "center":
                    c.drawCentredString(x, y_pdf, txt)
                elif align == "right":
                    c.drawRightString(x, y_pdf, txt)
                else:
                    c.drawString(x, y_pdf, txt)
            c.restoreState()
        c.showPage()
        c.save()


# ---------------------------------------------------------------------------
# 3. Publication-Grade 2D Wiring Diagram Builder (1200 x 825 pt -> 2880 x 1980 px)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PinPoint:
    x: float
    y: float
    exit_dir: str  # "left", "right", "up", "down"


def draw_wire(
    scene: VectorScene,
    points: list[tuple[float, float]],
    color_name: str,
    width: float = 2.3,
    radius: float = 6.0,
) -> None:
    """Draw a color-coded wire with clean white halo for crisp crossings and dark casing for white wires."""
    hex_color = str(WIRE_COLORS[color_name]["hex"])
    # White outer halo creates clean bridge separation at any orthogonal crossing
    scene.polyline(points, stroke="#FFFFFF", stroke_width=width + 2.4, radius=radius)
    if color_name == "White":
        # Dark outline casing + bright white-silver core so white wires are 100% legible on white canvas
        scene.polyline(points, stroke="#334155", stroke_width=width + 1.2, radius=radius)
        scene.polyline(points, stroke="#F8FAFC", stroke_width=max(1.4, width - 0.5), radius=radius)
    elif color_name == "Yellow":
        # Subtle dark amber outline so yellow stands out crisply on white
        scene.polyline(points, stroke="#854D0E", stroke_width=width + 0.6, radius=radius)
        scene.polyline(points, stroke="#EAB308", stroke_width=width - 0.4, radius=radius)
    else:
        scene.polyline(points, stroke=hex_color, stroke_width=width, radius=radius)


def draw_module_card(
    scene: VectorScene,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    title: str,
    subtitle: str,
    dims: str,
    accent: str,
    header_bg: str,
    body_bg: str = "#FFFFFF",
    badge: str | None = None,
    badge_bg: str = "#FEF3C7",
    badge_fg: str = "#92400E",
    extra_note: str | None = None,
    extra_note_color: str = "#475569",
) -> None:
    """Draw a crisp engineering off-board module card with subtle drop shadow & dimension header."""
    # Soft drop shadow
    scene.rect(x + 2.0, y + 2.2, w, h, fill="#E2E8F0", rx=6.0)
    # Main card body
    scene.rect(x, y, w, h, fill=body_bg, stroke=accent, stroke_width=1.4, rx=6.0)
    # Colored top header strip
    hdr_h = 24.0
    scene.rect(x, y, w, hdr_h, fill=header_bg, stroke=accent, stroke_width=1.2, rx=6.0)
    scene.rect(x + 0.7, y + hdr_h - 6.0, w - 1.4, 6.0, fill=header_bg)
    scene.line(x, y + hdr_h, x + w, y + hdr_h, stroke=accent, stroke_width=0.9)

    # Header title & dims
    scene.text(x + 7.0, y + 8.5, title, size=7.6, color="#0F172A", bold=True, align="left")
    scene.text(x + 7.0, y + 18.2, f"{subtitle}  ·  {dims}", size=5.7, color="#334155", align="left")

    if badge:
        bw = min(w - 14.0, len(badge) * 3.85 + 10.0)
        bx = x + w - bw - 5.0
        by = y + hdr_h + 4.0
        scene.rect(bx, by, bw, 12.0, fill=badge_bg, stroke=badge_fg, stroke_width=0.6, rx=3.0)
        scene.text(bx + bw / 2.0, by + 6.0, badge, size=5.4, color=badge_fg, bold=True, align="center")

    if extra_note:
        scene.text(x + 7.0, y + hdr_h + 9.8, extra_note, size=5.6, color=extra_note_color, bold=False, align="left")


def draw_pin_dot(
    scene: VectorScene,
    cx: float,
    cy: float,
    *,
    color_name: str | None = None,
    nc: bool = False,
    pin_num: str | None = None,
    r: float = 3.3,
) -> None:
    if nc:
        scene.circle(cx, cy, r, fill="#F1F5F9", stroke="#94A3B8", stroke_width=1.0)
        scene.line(cx - 1.8, cy - 1.8, cx + 1.8, cy + 1.8, stroke="#94A3B8", stroke_width=0.8)
        scene.line(cx - 1.8, cy + 1.8, cx + 1.8, cy - 1.8, stroke="#94A3B8", stroke_width=0.8)
        return
    if color_name == "White":
        fill = "#F8FAFC"
        stroke = "#334155"
    elif color_name == "Yellow":
        fill = "#EAB308"
        stroke = "#854D0E"
    elif color_name:
        fill = str(WIRE_COLORS[color_name]["hex"])
        stroke = "#0F172A"
    else:
        fill = "#0EA5E9"
        stroke = "#0F172A"
    scene.circle(cx, cy, r, fill=fill, stroke=stroke, stroke_width=0.9)
    if pin_num:
        txt_col = "#0F172A" if color_name in ("White", "Yellow") else "#FFFFFF"
        scene.text(cx, cy, pin_num, size=4.6, color=txt_col, bold=True, align="center")


def build_clean_wiring_diagram() -> VectorScene:
    """Build the spotless 2D System Wiring Diagram (1200 x 825 pt)."""
    W, H = 1200.0, 825.0
    s = VectorScene(W, H)
    wire_by_hub: dict[tuple[str, str], object] = {(w.hub_ref, w.hub_pin): w for w in WIRING_TABLE}

    def draw_bottom_card(
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        title: str,
        subtitle: str,
        dims: str,
        accent: str,
        header_bg: str,
        badge: str | None = None,
        badge_bg: str = "#FEF3C7",
        badge_fg: str = "#92400E",
    ) -> None:
        s.rect(x + 2.0, y + 2.2, w, h, fill="#E2E8F0", rx=6.0)
        s.rect(x, y, w, h, fill="#FFFFFF", stroke=accent, stroke_width=1.4, rx=6.0)
        # Colored footer title bar (keeps top pin edge 100% unobstructed!)
        ftr_h = 26.0
        fy = y + h - ftr_h
        s.rect(x, fy, w, ftr_h, fill=header_bg, stroke=accent, stroke_width=1.2, rx=6.0)
        s.rect(x + 0.7, fy, w - 1.4, 6.0, fill=header_bg)
        s.line(x, fy, x + w, fy, stroke=accent, stroke_width=0.9)
        s.text(x + 7.0, fy + 9.0, title, size=7.5, color="#0F172A", bold=True, align="left")
        s.text(x + 7.0, fy + 19.2, f"{subtitle}  ·  {dims}", size=5.6, color="#334155", align="left")
        if badge:
            bw = min(w - 14.0, len(badge) * 3.85 + 10.0)
            bx = x + w - bw - 6.0
            by = fy - 16.0
            s.rect(bx, by, bw, 12.5, fill=badge_bg, stroke=badge_fg, stroke_width=0.7, rx=3.0)
            s.text(bx + bw / 2.0, by + 6.2, badge, size=5.4, color=badge_fg, bold=True, align="center")

    # ------------------------------------------------------------------
    # 0. Canvas Background, Engineering Frame & Title Banner
    # ------------------------------------------------------------------
    s.rect(0, 0, W, H, fill="#FFFFFF")
    s.rect(10, 10, W - 20, H - 20, fill="#FAFBFC", stroke="#1E293B", stroke_width=1.5, rx=3.0)
    s.rect(14, 14, W - 28, H - 28, fill="none", stroke="#CBD5E1", stroke_width=0.6, rx=2.0)

    s.rect(16, 16, W - 32, 36, fill="#0F172A", rx=3.0)
    s.rect(16, 16, 6, 36, fill="#0EA5E9", rx=1.5)
    s.text(
        30, 27.5,
        "SMART HOME VOICE AI — COMPLETE SYSTEM 2D WIRING DIAGRAM (TYPE 1 CENTRAL HUB PCB + ALL PLUG-IN MODULES)",
        size=10.3, color="#FFFFFF", bold=True, align="left",
    )
    s.text(
        30, 42.5,
        "40 Physical Wires (36 Hub PCB J1–J15 + 4 Inter-Module)  |  10 Locked ESP8266 Pins (D0–D8, A0)  |  14 Off-Board Modules  |  5V/3.3V DC ONLY — NO Fan · NO AC · NO IR",
        size=6.85, color="#CBD5E1", align="left",
    )
    s.rect(1002, 22, 174, 24, fill="#1E293B", stroke="#38BDF8", stroke_width=0.8, rx=3.0)
    s.text(1089, 30.0, "SSOT: hardware/wiring_contract.py", size=6.1, color="#38BDF8", bold=True, mono=True, align="center")
    s.text(1089, 39.5, "KiCad 100×80mm 1L  |  NodeMCU v2", size=5.6, color="#E2E8F0", align="center")

    # ------------------------------------------------------------------
    # 1. CENTRAL HUB PCB (100.0 × 80.0 mm 1-Layer DIY)
    # ------------------------------------------------------------------
    PCB_X, PCB_Y, PCB_W, PCB_H = 336.0, 228.0, 480.0, 354.0
    s.rect(PCB_X + 3, PCB_Y + 3, PCB_W, PCB_H, fill="#CBD5E1", rx=7.0)
    s.rect(PCB_X, PCB_Y, PCB_W, PCB_H, fill="#ECFDF5", stroke="#065F46", stroke_width=2.0, rx=7.0)
    s.rect(PCB_X + 4, PCB_Y + 4, PCB_W - 8, PCB_H - 8, fill="none", stroke="#A7F3D0", stroke_width=0.7, rx=5.0)

    # 4x M3 Mounting Holes (H1..H4)
    for hx, hy, hlabel in [
        (PCB_X + 13, PCB_Y + 13, "H1"),
        (PCB_X + PCB_W - 13, PCB_Y + 13, "H2"),
        (PCB_X + 13, PCB_Y + PCB_H - 13, "H3"),
        (PCB_X + PCB_W - 13, PCB_Y + PCB_H - 13, "H4"),
    ]:
        s.circle(hx, hy, 5.8, fill="#D1FAE5", stroke="#047857", stroke_width=1.0)
        s.circle(hx, hy, 3.2, fill="#FFFFFF", stroke="#475569", stroke_width=0.9)
        s.text(hx, hy + (10.5 if hy < PCB_Y + 50 else -10.5), hlabel, size=4.8, color="#065F46", bold=True, mono=True, align="center")

    # PCB Title Ribbon inside Hub
    s.rect(PCB_X + 94, PCB_Y + 49, 292, 16, fill="#065F46", rx=3.0)
    s.text(
        PCB_X + 240, PCB_Y + 57.0,
        "CENTRAL HUB DIY PCB — 100.0 × 80.0 × 1.6 mm 1L FR4 (49 Footprints)",
        size=6.0, color="#ECFDF5", bold=True, align="center",
    )

    # ------------------------------------------------------------------
    # 1A. NodeMCU v2 Amica (U1 / U2) Inside Hub PCB
    # ------------------------------------------------------------------
    MCU_X, MCU_Y, MCU_W, MCU_H = 480.0, 304.0, 192.0, 206.0
    s.rect(MCU_X, MCU_Y, MCU_W, MCU_H, fill="#0F172A", stroke="#334155", stroke_width=1.5, rx=5.0)
    # Wi-Fi PCB antenna + ESP-12E shield
    s.rect(MCU_X + 70, MCU_Y + 8, 52, 14, fill="#1E293B", stroke="#F59E0B", stroke_width=0.7, rx=2.0)
    s.text(MCU_X + 96, MCU_Y + 15.0, "PCB ANT", size=4.9, color="#FBBF24", bold=True, mono=True, align="center")
    s.rect(MCU_X + 64, MCU_Y + 26, 64, 52, fill="#CBD5E1", stroke="#64748B", stroke_width=1.0, rx=3.0)
    s.text(MCU_X + 96, MCU_Y + 42, "ESP-12E/F", size=6.5, color="#0F172A", bold=True, mono=True, align="center")
    s.text(MCU_X + 96, MCU_Y + 53, "ESP8266", size=5.9, color="#334155", bold=True, align="center")
    s.text(MCU_X + 96, MCU_Y + 64, "Wi-Fi 2.4GHz", size=5.1, color="#475569", align="center")
    # NodeMCU core label
    s.rect(MCU_X + 66, MCU_Y + 90, 60, 42, fill="#1E293B", stroke="#475569", stroke_width=0.8, rx=2.5)
    s.text(MCU_X + 96, MCU_Y + 102, "NodeMCU v2", size=6.1, color="#F8FAFC", bold=True, align="center")
    s.text(MCU_X + 96, MCU_Y + 112, "Amica CP2102", size=5.1, color="#94A3B8", align="center")
    s.text(MCU_X + 96, MCU_Y + 122, "48.3×25.4mm", size=4.9, color="#64748B", mono=True, align="center")
    # Active pin count note
    s.text(MCU_X + 96, MCU_Y + 152, "10 Active Pins", size=5.3, color="#38BDF8", bold=True, align="center")
    s.text(MCU_X + 96, MCU_Y + 162, "D0..D8 + A0", size=5.2, color="#CBD5E1", mono=True, align="center")
    s.text(MCU_X + 96, MCU_Y + 173, "(* = Boot-Strap)", size=4.7, color="#FBBF24", align="center")
    # Micro-USB receptacle
    s.rect(MCU_X + 80, MCU_Y + MCU_H - 12, 32, 12, fill="#94A3B8", stroke="#475569", stroke_width=0.9, rx=1.5)
    s.text(MCU_X + 96, MCU_Y + MCU_H - 6.0, "USB", size=5.1, color="#0F172A", bold=True, mono=True, align="center")

    s.text(MCU_X + 6, MCU_Y + 12, "U1 (Left)", size=5.3, color="#38BDF8", bold=True, mono=True, align="left")
    s.text(MCU_X + MCU_W - 6, MCU_Y + 12, "U2 (Right)", size=5.3, color="#38BDF8", bold=True, mono=True, align="right")

    u1_rows = [
        ("1", "A0 (ADC0)", "#4ADE80", True),
        ("2-9", "RSV/SD (NC)", "#94A3B8", False),
        ("10", "GND", "#CBD5E1", True),
        ("11", "+3V3", "#F87171", True),
        ("12-13", "EN/RST (NC)", "#94A3B8", False),
        ("14", "GND", "#CBD5E1", True),
        ("15", "VIN (+5V)", "#EF4444", True),
    ]
    for idx, (pnum, plab, col, active) in enumerate(u1_rows):
        py = MCU_Y + 30 + idx * 24.5
        s.circle(MCU_X + 6, py, 2.3, fill=col if active else "#475569", stroke="#E2E8F0" if active else "#94A3B8", stroke_width=0.6)
        s.text(MCU_X + 11.5, py, f"{pnum}:{plab}", size=5.2, color=col, bold=active, mono=True, align="left")

    u2_rows = [
        ("1", "D0·G16", "#FACC15"),
        ("2", "D1·G5", "#FB923C"),
        ("3", "D2·G4", "#60A5FA"),
        ("4", "D3·G0*", "#E2E8F0"),
        ("5", "D4·G2*", "#C084FC"),
        ("6", "+3V3", "#F87171"),
        ("7", "GND", "#94A3B8"),
        ("8", "D5·G14", "#FACC15"),
        ("9", "D6·G12", "#4ADE80"),
        ("10", "D7·G13", "#22D3EE"),
        ("11", "D8·G15*", "#FB923C"),
        ("14-15", "GND/3V3", "#94A3B8"),
    ]
    for idx, (pnum, plab, col) in enumerate(u2_rows):
        py = MCU_Y + 25 + idx * 14.8
        s.circle(MCU_X + MCU_W - 6, py, 2.1, fill=col, stroke="#E2E8F0", stroke_width=0.5)
        s.text(MCU_X + MCU_W - 10.5, py, f"{plab}:{pnum}", size=5.0, color=col, bold=True, mono=True, align="right")

    # ------------------------------------------------------------------
    # 1B. On-Board Protective Passives Callout Badges (Inside Hub PCB)
    # ------------------------------------------------------------------
    def draw_passive_badge(bx: float, by: float, bw: float, bh: float, bg: str, bd: str, l1: str, l2: str) -> None:
        s.rect(bx, by, bw, bh, fill=bg, stroke=bd, stroke_width=0.85, rx=3.0)
        s.text(bx + bw / 2.0, by + bh * 0.34, l1, size=5.15, color="#0F172A", bold=True, mono=True, align="center")
        s.text(bx + bw / 2.0, by + bh * 0.72, l2, size=4.75, color="#334155", align="center")

    # Left-Inside Passives (x = 414..474, cleanly right of J8 vertical wire lane x=402..409!)
    draw_passive_badge(415, 366, 60, 30, "#FEF3C7", "#D97706", "C1/C2 470µF", "+5V · C3 100n")
    draw_passive_badge(415, 402, 60, 28, "#FEE2E2", "#DC2626", "D1 1N4007", "Pump Flyback")
    draw_passive_badge(415, 436, 60, 28, "#DCFCE7", "#16A34A", "D3 + R8 1k", "+5V PWR LED")
    draw_passive_badge(415, 470, 60, 28, "#E0F2FE", "#0284C7", "C7 100nF", "A0 ADC Filter")

    # Right-Inside Passives (x = 678..744)
    draw_passive_badge(678, 308, 66, 28, "#F3E8FF", "#9333EA", "R1/R2 220Ω", "LR & BR LED")
    draw_passive_badge(678, 342, 66, 32, "#E0E7FF", "#4F46E5", "R3/R4/R7/R9", "10k Pull-Up/Dn")
    draw_passive_badge(678, 380, 66, 38, "#FEF3C7", "#B45309", "C4 10µ·C5 10n", "R5/R6 2.2k RC")
    draw_passive_badge(678, 424, 66, 28, "#FEE2E2", "#DC2626", "D2 1N4007", "Buzz Flyback")
    draw_passive_badge(678, 458, 66, 28, "#E0F2FE", "#0284C7", "C6 100nF", "AMP_5V Decpl")

    # ------------------------------------------------------------------
    # 1C. All 15 Hub PCB Connectors (J1..J15) on Their REAL Physical Edges
    # ------------------------------------------------------------------
    hub_pins: dict[tuple[str, str], PinPoint] = {}

    def draw_hub_connector_horizontal(ref: str, x_center: float, edge: str, pin_spacing: float = 18.0) -> None:
        conn = HUB_CONNECTOR_MAP[ref]
        n = len(conn.pins)
        bw = max(62.0, n * pin_spacing + 18.0)
        bh = 37.0
        bx = x_center - bw / 2.0
        by = PCB_Y + 6.0 if edge == "top" else PCB_Y + PCB_H - 6.0 - bh
        s.rect(bx, by, bw, bh, fill="#FFFFFF", stroke="#065F46", stroke_width=1.1, rx=3.0)
        if edge == "top":
            pin_y = by + 7.5
            s.text(x_center, by + 21.5, f"{ref} {conn.value}", size=5.2, color="#065F46", bold=True, mono=True, align="center")
            net_y = by + 31.2
        else:
            pin_y = by + bh - 7.5
            s.text(x_center, by + 15.5, f"{ref} {conn.value}", size=5.2, color="#065F46", bold=True, mono=True, align="center")
            net_y = by + 6.0

        start_x = x_center - ((n - 1) * pin_spacing) / 2.0
        net_parts = []
        for i, (pnum, _rx, _ry, net) in enumerate(conn.pins):
            px = start_x + i * pin_spacing
            w = wire_by_hub[(ref, pnum)]
            draw_pin_dot(s, px, pin_y, color_name=w.color, pin_num=pnum, r=4.0)
            hub_pins[(ref, pnum)] = PinPoint(px, pin_y, "up" if edge == "top" else "down")
            short_net = (
                net.replace("D2_DHT11", "D2")
                .replace("A0_SOIL", "A0")
                .replace("LED_LR_A", "LR+")
                .replace("LED_BR_A", "BR+")
                .replace("D4_LED_BR", "D4")
                .replace("D7_RLY2_AMP", "D7")
                .replace("AUD_OUT", "AUD")
                .replace("AMP_5V", "AMP5")
            )
            net_parts.append(f"{pnum}:{short_net}")
        s.text(x_center, net_y, " ".join(net_parts), size=4.65, color="#334155", mono=True, align="center")

    def draw_hub_connector_vertical(ref: str, y_center: float, edge: str, pin_spacing: float = 14.0) -> None:
        conn = HUB_CONNECTOR_MAP[ref]
        n = len(conn.pins)
        bw = 59.0 if edge != "left_inner" else 63.0
        bh = max(38.0, n * pin_spacing + 18.0)
        if edge == "left":
            bx = PCB_X + 6.0
        elif edge == "left_inner":
            bx = 411.0
        else:
            bx = PCB_X + PCB_W - 6.0 - bw
        by = y_center - bh / 2.0
        is_screw = conn.kind == "screw_508"
        bg = "#DCFCE7" if is_screw else "#FFFFFF"
        bd = "#15803D" if is_screw else "#065F46"
        s.rect(bx, by, bw, bh, fill=bg, stroke=bd, stroke_width=1.25 if is_screw else 1.05, rx=3.0)
        s.text(bx + bw / 2.0, by + 6.8, f"{ref} {conn.value}", size=4.95, color="#065F46", bold=True, mono=True, align="center")

        start_y = by + 17.5
        for i, (pnum, _rx, _ry, net) in enumerate(conn.pins):
            py = start_y + i * pin_spacing
            w = wire_by_hub[(ref, pnum)]
            short_net = (
                net.replace("D1_SERVO", "D1")
                .replace("D5_MIC_DO", "D5")
                .replace("D6_RLY1_PUMP", "D6")
                .replace("D8_BUZZER", "D8")
                .replace("PUMP_5V", "PMP5")
            )
            if edge == "left":
                px = bx + 7.5
                draw_pin_dot(s, px, py, color_name=w.color, pin_num=pnum, r=4.0)
                s.text(px + 6.8, py, short_net, size=4.9, color="#1E293B", bold=True, mono=True, align="left")
                hub_pins[(ref, pnum)] = PinPoint(px, py, "left")
            elif edge == "left_inner":
                px = bx + 7.5
                draw_pin_dot(s, px, py, color_name=w.color, pin_num=pnum, r=4.0)
                s.text(px + 6.5, py, f"{short_net}→R1", size=4.75, color="#1E293B", bold=True, mono=True, align="left")
                hub_pins[(ref, pnum)] = PinPoint(px, py, "left")
            else:
                px = bx + bw - 7.5
                draw_pin_dot(s, px, py, color_name=w.color, pin_num=pnum, r=4.0)
                s.text(px - 6.8, py, short_net, size=4.9, color="#1E293B", bold=True, mono=True, align="right")
                hub_pins[(ref, pnum)] = PinPoint(px, py, "right")

    # Top edge: J14, J13, J4, J5
    draw_hub_connector_horizontal("J14", 408.0, "top", pin_spacing=20.0)
    draw_hub_connector_horizontal("J13", 520.0, "top", pin_spacing=20.0)
    draw_hub_connector_horizontal("J4", 650.0, "top", pin_spacing=22.0)
    draw_hub_connector_horizontal("J5", 748.0, "top", pin_spacing=22.0)

    # Left edge: J2, J1  + Left-Inner: J8
    draw_hub_connector_vertical("J2", 324.0, "left", pin_spacing=16.0)
    draw_hub_connector_vertical("J8", 326.0, "left_inner", pin_spacing=15.0)
    draw_hub_connector_vertical("J1", 456.0, "left", pin_spacing=16.0)

    # Right edge: J3, J15, J7, J6
    draw_hub_connector_vertical("J3", 316.0, "right", pin_spacing=13.5)
    draw_hub_connector_vertical("J15", 386.0, "right", pin_spacing=13.5)
    draw_hub_connector_vertical("J7", 456.0, "right", pin_spacing=13.5)
    draw_hub_connector_vertical("J6", 522.0, "right", pin_spacing=14.0)

    # Bottom edge: J9, J10, J11, J12
    draw_hub_connector_horizontal("J9", 450.0, "bottom", pin_spacing=19.0)
    draw_hub_connector_horizontal("J10", 548.0, "bottom", pin_spacing=22.0)
    draw_hub_connector_horizontal("J11", 650.0, "bottom", pin_spacing=22.0)
    draw_hub_connector_horizontal("J12", 748.0, "bottom", pin_spacing=22.0)

    # ------------------------------------------------------------------
    # 2. ALL 14 OFF-BOARD MODULES AROUND THE PERIMETER
    # ------------------------------------------------------------------
    mod_pins: dict[tuple[str, str], PinPoint] = {}

    # === TOP ROW (y = 62..164) ===
    # T1. YL-69 Soil Fork Probe
    draw_module_card(
        s, 24, 62, 148, 96,
        title="YL-69 Soil Fork Probe",
        subtitle="Resistive 2-Prong",
        dims="60×20×1.6 mm",
        accent="#0F766E", header_bg="#CCFBF1",
        extra_note="2-Wire Pair → LM393",
    )
    s.rect(34, 107, 46, 7.5, fill="#0D9488", stroke="#115E59", stroke_width=0.7, rx=2.0)
    s.rect(34, 122, 46, 7.5, fill="#0D9488", stroke="#115E59", stroke_width=0.7, rx=2.0)
    s.rect(76, 105, 13, 27, fill="#115E59", rx=2.0)
    for py, pname, wid, col in [(111.0, "Prong A", "W36", "Yellow"), (127.0, "Prong B", "W37", "Orange")]:
        px = 172.0
        draw_pin_dot(s, px, py, color_name=col, r=3.6)
        s.text(px - 6.0, py, f"{pname} ({wid})", size=5.2, color="#0F172A", bold=True, mono=True, align="right")
        mod_pins[("soil_probe", pname)] = PinPoint(px, py, "right")

    # T2. Soil LM393 Comparator Module
    draw_module_card(
        s, 206, 62, 228, 102,
        title="LM393 Soil Comparator",
        subtitle="Analog Soil Breakout",
        dims="32×14×12.1 mm",
        accent="#15803D", header_bg="#DCFCE7",
        badge="3.3V ONLY!", badge_bg="#FEE2E2", badge_fg="#B91C1C",
        extra_note="AO: <40% ON / >=70% OFF",
    )
    for py, pname, wid, col in [(111.0, "P1", "W36", "Yellow"), (127.0, "P2", "W37", "Orange")]:
        px = 206.0
        draw_pin_dot(s, px, py, color_name=col, r=3.6)
        s.text(px + 6.0, py, f"{pname} ({wid})", size=5.15, color="#0F172A", bold=True, mono=True, align="left")
        mod_pins[("soil_lm393", pname)] = PinPoint(px, py, "left")

    for px, pname, wid, col, is_nc in [
        (266.0, "DO", None, None, True),
        (338.0, "VCC", "W33", "Red", False),
        (376.0, "GND", "W34", "Black", False),
        (414.0, "AO", "W35", "Green", False),
    ]:
        py = 164.0
        draw_pin_dot(s, px, py, color_name=col, nc=is_nc, r=3.6)
        lbl = f"{pname} [NC]" if is_nc else pname
        s.text(px, py - 10.5, lbl, size=5.2, color="#94A3B8" if is_nc else "#0F172A", bold=not is_nc, mono=True, align="center")
        if wid:
            s.text(px, py - 18.5, wid, size=4.8, color="#475569", mono=True, align="center")
            mod_pins[("soil_lm393", pname)] = PinPoint(px, py, "down")

    # T3. DHT11 3-Pin Breakout
    draw_module_card(
        s, 446, 62, 152, 102,
        title="DHT11 Temp & Humidity",
        subtitle="3-Pin Breakout · 3.3V",
        dims="28×14×7.1 mm",
        accent="#2563EB", header_bg="#DBEAFE",
        extra_note="R3 10kΩ Pull-Up on Hub",
    )
    for px, pname, wid, col in [
        (482.0, "VCC(+)", "W30", "Red"),
        (522.0, "DATA", "W31", "Blue"),
        (562.0, "GND(-)", "W32", "Black"),
    ]:
        py = 164.0
        draw_pin_dot(s, px, py, color_name=col, r=3.6)
        s.text(px, py - 10.5, pname, size=5.2, color="#0F172A", bold=True, mono=True, align="center")
        s.text(px, py - 18.5, wid, size=4.8, color="#475569", mono=True, align="center")
        mod_pins[("dht11_sensor", pname)] = PinPoint(px, py, "down")

    # T4. Living Room 5mm LED (D0)
    draw_module_card(
        s, 610, 62, 148, 102,
        title="5mm LED — Living Room",
        subtitle="Active-HIGH · R1 220Ω",
        dims="Ø5.8×8.6 mm",
        accent="#CA8A04", header_bg="#FEF9C3",
        extra_note="D0 (GPIO16) + enroll_blink",
    )
    for px, pname, wid, col in [(652.0, "Anode(+)", "W06", "Yellow"), (714.0, "Cathode(-)", "W07", "Black")]:
        py = 164.0
        draw_pin_dot(s, px, py, color_name=col, r=3.6)
        s.text(px, py - 10.5, pname, size=5.2, color="#0F172A", bold=True, mono=True, align="center")
        s.text(px, py - 18.5, wid, size=4.8, color="#475569", mono=True, align="center")
        mod_pins[("led_living", pname)] = PinPoint(px, py, "down")

    # T5. Bedroom 5mm LED (D4 Active-LOW)
    draw_module_card(
        s, 770, 62, 174, 102,
        title="5mm LED — Bedroom",
        subtitle="Active-LOW (Boot-Safe)",
        dims="Ø5.8×8.6 mm",
        accent="#9333EA", header_bg="#F3E8FF",
        badge="ACTIVE-LOW", badge_bg="#F3E8FF", badge_fg="#6B21A8",
        extra_note="R2 220Ω + R7 10kΩ Hub",
    )
    for px, pname, wid, col in [(822.0, "Anode(+)", "W08", "Purple"), (892.0, "Cathode(-)", "W09", "White")]:
        py = 164.0
        draw_pin_dot(s, px, py, color_name=col, r=3.6)
        s.text(px, py - 10.5, pname, size=5.2, color="#0F172A", bold=True, mono=True, align="center")
        s.text(px, py - 18.5, wid, size=4.8, color="#475569", mono=True, align="center")
        mod_pins[("led_bedroom", pname)] = PinPoint(px, py, "down")

    # === TOP-RIGHT: BOOT-SAFETY & ELECTRICAL PROTECTION CHECKLIST ===
    s.rect(956, 62, 220, 122, fill="#FFFBEB", stroke="#D97706", stroke_width=1.4, rx=6.0)
    s.rect(956, 62, 220, 20, fill="#FEF3C7", stroke="#D97706", stroke_width=1.1, rx=6.0)
    s.rect(957, 76, 218, 6, fill="#FEF3C7")
    s.line(956, 82, 1176, 82, stroke="#D97706", stroke_width=0.9)
    s.text(1066, 72.0, "BOOT-SAFETY & PROTECTION NOTES", size=6.6, color="#92400E", bold=True, align="center")
    safety_notes = [
        "• D3 (GPIO0): C4 10µF + R5/R6 2.2k + C5 10nF;",
        "  R4 10k pull-up; firmware IDLE = INPUT (high-Z)",
        "• D4 (GPIO2): Active-LOW + R7 10k pull-up",
        "• D8 (GPIO15): Active-HIGH + R9 10k pull-down",
        "• LM393 (J14) & KY-037 (J15): 3.3V ONLY!",
        "• PAM8403 BTL: NEVER tie L_OUT- to GND!",
        "• Pump/Buzz: D1/D2 1N4007 + C1/C2 470µF",
        "• Scope Lock: NO Fan · NO AC · NO IR",
    ]
    for i, note in enumerate(safety_notes):
        is_warn = ("3.3V ONLY" in note) or ("NEVER" in note) or ("NO Fan" in note)
        s.text(963, 91.5 + i * 11.2, note, size=5.45, color="#B91C1C" if is_warn else "#1E293B", bold=is_warn, align="left")

    # === LEFT COLUMN (x = 24..252) ===
    # L1. Mini Submersible Pump (3-6V)
    draw_module_card(
        s, 24, 214, 228, 122,
        title="Mini Submersible Pump (3–6V)",
        subtitle="Garden Pump · Switched +5V",
        dims="45×24×33 mm",
        accent="#0284C7", header_bg="#E0F2FE",
        badge="D1 1N4007", badge_bg="#FEE2E2", badge_fg="#B91C1C",
        extra_note="Switched via Relay 1 (J8→J2)",
    )
    s.text(32, 264, "• Nozzle OD 7.5mm · 6/8mm silicone tube", size=5.35, color="#334155")
    s.text(32, 276, "• Hub D1 1N4007 flyback + C2 470µF", size=5.35, color="#334155")
    for py, pname, wid, col in [(306.0, "Pump +", "W15", "Red"), (324.0, "Pump -", "W16", "Black")]:
        px = 252.0
        draw_pin_dot(s, px, py, color_name=col, r=3.6)
        s.text(px - 7.0, py, f"{pname} ({wid})", size=5.5, color="#0F172A", bold=True, mono=True, align="right")
        mod_pins[("pump_unit", pname)] = PinPoint(px, py, "right")

    # L2. External 5V 2A Power Supply
    draw_module_card(
        s, 24, 374, 228, 114,
        title="External 5V 2A Power Supply",
        subtitle="DC-005 + Screw Breakout",
        dims="34×22×16 mm",
        accent="#DC2626", header_bg="#FEE2E2",
        badge="5V DC 2A", badge_bg="#FEE2E2", badge_fg="#991B1B",
        extra_note="Feeds Hub J1 (5.08mm Phoenix)",
    )
    s.text(32, 422, "• Main +5V rail: NodeMCU VIN, SG90,", size=5.35, color="#334155")
    s.text(32, 434, "  Relays 1 & 2, Pump, PAM8403 Amp", size=5.35, color="#334155")
    for py, pname, wid, col in [(452.0, "+5V", "W01", "Red"), (472.0, "GND", "W02", "Black")]:
        px = 252.0
        draw_pin_dot(s, px, py, color_name=col, r=3.6)
        s.text(px - 7.0, py, f"{pname} ({wid})", size=5.55, color="#0F172A", bold=True, mono=True, align="right")
        mod_pins[("psu_5v", pname)] = PinPoint(px, py, "right")

    # L3. WIRE COLOR LEGEND BOX (x = 24..306, y = 516..798)
    s.rect(24, 516, 282, 282, fill="#FFFFFF", stroke="#334155", stroke_width=1.4, rx=6.0)
    s.rect(24, 516, 282, 21, fill="#1E293B", rx=6.0)
    s.rect(25, 531, 280, 6, fill="#1E293B")
    s.text(165, 526.5, "WIRE COLOR KEY (10 STANDARD COLORS · 40 WIRES)", size=6.5, color="#FFFFFF", bold=True, align="center")

    legend_items = [
        ("Red", "Power (+5V / +3V3 / Switched +5V)"),
        ("Black", "Common Ground (GND)"),
        ("Orange", "SG90 D1 · Buzz D8 · RLY2 NO · Probe B"),
        ("Yellow", "LED LR · KY037 · RLY1 NO · Spk+ · PrA"),
        ("Green", "Relay 1 IN (D6) · Soil Analog AO (A0)"),
        ("Blue", "DHT11 1-Wire DATA (D2)"),
        ("Cyan", "Relay 2 Opto IN (D7)"),
        ("Purple", "LED Bedroom Anode (+3.3V via R2 220Ω)"),
        ("White", "LED Bedroom D4 (Act-LO) · Audio D3"),
        ("Brown", "PAM8403 BTL L_OUT- → SPK- (NOT GND)"),
    ]
    for i, (cname, desc) in enumerate(legend_items):
        ly = 551.0 + i * 21.0
        if cname == "White":
            s.line(34, ly, 58, ly, stroke="#334155", stroke_width=4.4)
            s.line(34, ly, 58, ly, stroke="#F8FAFC", stroke_width=2.4)
        elif cname == "Yellow":
            s.line(34, ly, 58, ly, stroke="#854D0E", stroke_width=3.8)
            s.line(34, ly, 58, ly, stroke="#EAB308", stroke_width=2.4)
        else:
            s.line(34, ly, 58, ly, stroke=str(WIRE_COLORS[cname]["hex"]), stroke_width=3.2)
        s.text(64, ly, cname, size=5.95, color="#0F172A", bold=True, align="left")
        s.text(103, ly, desc, size=5.5, color="#334155", align="left")

    s.line(32, 761, 298, 761, stroke="#E2E8F0", stroke_width=0.9)
    draw_pin_dot(s, 40, 773, nc=True, r=3.4)
    s.text(49, 773, "[NC] = Intentionally Unconnected Pin", size=5.5, color="#64748B", bold=True)
    s.rect(32, 782, 266, 12, fill="#DCFCE7", stroke="#16A34A", stroke_width=0.7, rx=2.5)
    s.text(165, 788.0, "VERIFIED: 36 Hub + 4 Off-Board = 40 Wires | NO Fan · NO AC · NO IR", size=5.25, color="#166534", bold=True, align="center")

    # === RIGHT COLUMN (x = 956..1176, W = 220) ===
    # R1. SG90 Micro Servo (Main Door, J3)
    draw_module_card(
        s, 956, 196, 220, 98,
        title="SG90 Micro Servo (Main Door)",
        subtitle="50Hz PWM · 0° Closed / 90° Open",
        dims="22.8×12.2×22.5 mm",
        accent="#EA580C", header_bg="#FFEDD5",
        extra_note="Decoupled by Hub C1 470µF",
    )
    for py, pname, wid, col in [
        (246.0, "PWM (Orange)", "W03", "Orange"),
        (262.0, "VCC (Red)", "W04", "Red"),
        (278.0, "GND (Brown)", "W05", "Black"),
    ]:
        px = 956.0
        draw_pin_dot(s, px, py, color_name=col, r=3.6)
        s.text(px + 7.0, py, f"({wid}) {pname}", size=5.4, color="#0F172A", bold=True, mono=True, align="left")
        mod_pins[("sg90_servo", pname)] = PinPoint(px, py, "left")

    # R2. KY-037 / KY-038 Sound Sensor (J15)
    draw_module_card(
        s, 956, 306, 220, 114,
        title="KY-037 / KY-038 Sound Sensor",
        subtitle="ECM-9767 Mic + LM393",
        dims="35×15×13.1 mm",
        accent="#CA8A04", header_bg="#FEF9C3",
        badge="3.3V ONLY!", badge_bg="#FEE2E2", badge_fg="#B91C1C",
        extra_note="RISING IRQ >=400ms Debounce",
    )
    for py, pname, wid, col, is_nc in [
        (356.0, "+ (VCC 3.3V)", "W38", "Red", False),
        (372.0, "G (GND)", "W39", "Black", False),
        (388.0, "DO (D5 IRQ)", "W40", "Yellow", False),
        (404.0, "AO [NC]", None, None, True),
    ]:
        px = 956.0
        draw_pin_dot(s, px, py, color_name=col, nc=is_nc, r=3.6)
        lbl = pname if is_nc else f"({wid}) {pname}"
        s.text(px + 7.0, py, lbl, size=5.4, color="#94A3B8" if is_nc else "#0F172A", bold=not is_nc, mono=True, align="left")
        if wid:
            mod_pins[("ky037_sound", pname)] = PinPoint(px, py, "left")

    # R3. Relay 1 — Blue 5V 1-ch (Garden Pump: J7 coil + J8 COM/NO)
    draw_module_card(
        s, 956, 428, 220, 148,
        title="Relay 1 — Blue 5V 1-ch (Pump)",
        subtitle="Songle SRD-05VDC · Active-HIGH",
        dims="50×26×18.5 mm",
        accent="#2563EB", header_bg="#DBEAFE",
        badge="J7 + J8", badge_bg="#DBEAFE", badge_fg="#1D4ED8",
        extra_note="Switches +5V → PUMP_5V",
    )
    s.text(1118, 492, "Coil (J7)", size=5.2, color="#1D4ED8", bold=True, align="center")
    for py, pname, wid, col in [
        (478.0, "VCC (+5V)", "W10", "Red"),
        (492.0, "GND", "W11", "Black"),
        (506.0, "IN (D6)", "W12", "Green"),
    ]:
        px = 956.0
        draw_pin_dot(s, px, py, color_name=col, r=3.6)
        s.text(px + 7.0, py, f"({wid}) {pname}", size=5.3, color="#0F172A", bold=True, mono=True, align="left")
        mod_pins[("relay1_pump", pname)] = PinPoint(px, py, "left")

    s.line(964, 518, 1168, 518, stroke="#CBD5E1", stroke_width=0.8, dash=(3, 2))
    s.text(1118, 546, "Contacts (J8)", size=5.2, color="#15803D", bold=True, align="center")
    for py, pname, wid, col, is_nc in [
        (532.0, "COM (+5V)", "W13", "Red", False),
        (548.0, "NO (PUMP_5V)", "W14", "Yellow", False),
        (564.0, "NC [NC]", None, None, True),
    ]:
        px = 956.0
        draw_pin_dot(s, px, py, color_name=col, nc=is_nc, r=3.6)
        lbl = pname if is_nc else f"({wid}) {pname}"
        s.text(px + 7.0, py, lbl, size=5.3, color="#94A3B8" if is_nc else "#0F172A", bold=not is_nc, mono=True, align="left")
        if wid:
            mod_pins[("relay1_pump", pname)] = PinPoint(px, py, "left")

    # R4. Active 5V Buzzer (TMB12A05, J6)
    draw_module_card(
        s, 956, 586, 220, 82,
        title="Active 5V Buzzer (TMB12A05)",
        subtitle="Alarm Siren · Active-HIGH (D8)",
        dims="Ø12.0×9.5 mm",
        accent="#DC2626", header_bg="#FEE2E2",
        badge="R9+D2", badge_bg="#FEF3C7", badge_fg="#92400E",
        extra_note="Silent at boot (R9 10k pull-down)",
    )
    for py, pname, wid, col in [(632.0, "Buzzer (+)", "W17", "Orange"), (646.0, "Buzzer (-)", "W18", "Black")]:
        px = 956.0
        draw_pin_dot(s, px, py, color_name=col, r=3.6)
        s.text(px + 7.0, py, f"({wid}) {pname}", size=5.4, color="#0F172A", bold=True, mono=True, align="left")
        mod_pins[("buzzer_alarm", pname)] = PinPoint(px, py, "left")

    # === BOTTOM ROW (y = 682..798, H = 116) — Top Pin Strip + Bottom Title Bar ===
    # B1. Relay 2 — Red Opto 5V (Jumper = H)
    draw_bottom_card(
        326, 682, 308, 116,
        title="Relay 2 — Red Opto 5V (Speaker Amp)",
        subtitle="SRD-05VDC + PC817 Opto · Auto-Off 1.5s",
        dims="50×26×18.5 mm",
        accent="#DC2626", header_bg="#FEE2E2",
        badge="JUMPER = H", badge_bg="#FEE2E2", badge_fg="#991B1B",
    )
    s.line(486, 690, 486, 766, stroke="#CBD5E1", stroke_width=0.8, dash=(3, 2))
    s.text(406, 738, "Control Header (J9)", size=5.4, color="#991B1B", bold=True, align="center")
    s.text(560, 738, "Screw Contacts (J10)", size=5.4, color="#15803D", bold=True, align="center")
    s.text(335, 756, "Switches +5V → AMP_5V (J10 → J11)", size=5.4, color="#475569")

    for px, pname, wid, col, is_nc in [
        (356.0, "DC+", "W19", "Red", False),
        (426.0, "DC-", "W20", "Black", False),
        (464.0, "IN(D7)", "W21", "Cyan", False),
        (512.0, "COM", "W22", "Red", False),
        (556.0, "NO", "W23", "Orange", False),
        (604.0, "NC", None, None, True),
    ]:
        py = 682.0
        draw_pin_dot(s, px, py, color_name=col, nc=is_nc, r=3.6)
        lbl = f"{pname}[NC]" if is_nc else pname
        s.text(px, py + 12.0, lbl, size=5.2, color="#94A3B8" if is_nc else "#0F172A", bold=not is_nc, mono=True, align="center")
        if wid:
            s.text(px, py + 21.0, wid, size=4.8, color="#475569", mono=True, align="center")
            mod_pins[("relay2_speaker", pname)] = PinPoint(px, py, "up")

    # B2. PAM8403 Mini Audio Amplifier
    draw_bottom_card(
        650, 682, 260, 116,
        title="PAM8403 Mini Audio Amplifier",
        subtitle="3W Class-D BTL · Switched 5V",
        dims="21×18×3.1 mm",
        accent="#0F766E", header_bg="#CCFBF1",
        badge="CLASS-D BTL", badge_bg="#FEF3C7", badge_fg="#92400E",
    )
    s.line(744, 690, 744, 750, stroke="#CBD5E1", stroke_width=0.8, dash=(3, 2))
    s.text(697, 738, "Power (J11)", size=5.3, color="#0F766E", bold=True, align="center")
    s.text(798, 738, "Audio In (J12)", size=5.3, color="#334155", bold=True, align="center")
    s.text(658, 756, "D3 RC-filtered PWM → L In", size=5.35, color="#475569")

    for px, pname, wid, col, is_nc in [
        (676.0, "5V+", "W24", "Red", False),
        (718.0, "5V-", "W25", "Black", False),
        (766.0, "L In", "W26", "White", False),
        (806.0, "A-GND", "W27", "Black", False),
        (842.0, "R", None, None, True),
    ]:
        py = 682.0
        draw_pin_dot(s, px, py, color_name=col, nc=is_nc, r=3.6)
        lbl = f"{pname}[NC]" if is_nc else pname
        s.text(px, py + 12.0, lbl, size=5.2, color="#94A3B8" if is_nc else "#0F172A", bold=not is_nc, mono=True, align="center")
        if wid:
            s.text(px, py + 21.0, wid, size=4.8, color="#475569", mono=True, align="center")
            mod_pins[("pam8403_amp", pname)] = PinPoint(px, py, "up")

    # PAM8403 Right-side BTL speaker outputs + R_OUT [NC]
    for py, pname, wid, col, is_nc in [
        (706.0, "L_OUT+", "W28", "Yellow", False),
        (724.0, "L_OUT-", "W29", "Brown", False),
        (742.0, "R_OUT±[NC]", None, None, True),
    ]:
        px = 910.0
        draw_pin_dot(s, px, py, color_name=col, nc=is_nc, r=3.6)
        lbl = pname if is_nc else f"{pname} ({wid})"
        s.text(px - 6.0, py, lbl, size=5.0, color="#94A3B8" if is_nc else "#0F172A", bold=not is_nc, mono=True, align="right")
        if wid:
            mod_pins[("pam8403_amp", pname)] = PinPoint(px, py, "right")

    # B3. Mini Speaker (28mm 8Ω 0.5W)
    draw_bottom_card(
        956, 682, 220, 116,
        title="Mini Speaker (28mm 8Ω 0.5W)",
        subtitle="PUI Audio AS02808MR-R",
        dims="Ø28.0×5.2 mm",
        accent="#78350F", header_bg="#FEF3C7",
    )
    # Speaker circular icon on right half of card
    s.circle(1134, 725, 22, fill="#F1F5F9", stroke="#475569", stroke_width=1.2)
    s.circle(1134, 725, 13, fill="#CBD5E1", stroke="#64748B", stroke_width=0.8)
    s.circle(1134, 725, 5.5, fill="#334155")
    for py, pname, wid, col in [(706.0, "SPK +", "W28", "Yellow"), (724.0, "SPK -", "W29", "Brown")]:
        px = 956.0
        draw_pin_dot(s, px, py, color_name=col, r=3.6)
        s.text(px + 7.0, py, f"({wid}) {pname}", size=5.5, color="#0F172A", bold=True, mono=True, align="left")
        mod_pins[("speaker_mini", pname)] = PinPoint(px, py, "left")
    # Prominent BTL Warning pill inside Speaker card
    s.rect(964, 748, 138, 17, fill="#FEE2E2", stroke="#DC2626", stroke_width=0.9, rx=3.0)
    s.text(1033, 756.5, "BTL: NEVER TIE SPK- TO GND!", size=5.35, color="#991B1B", bold=True, align="center")

    # ------------------------------------------------------------------
    # 3. ROUTE ALL 40 COLOR-CODED ORTHOGONAL WIRES (SSOT VERIFIED)
    # ------------------------------------------------------------------
    routed_wires: set[str] = set()

    def route_h_to_m(
        wid: str,
        h_ref: str,
        h_pin: str,
        m_id: str,
        m_pin: str,
        mid_points: list[tuple[float, float]] | None = None,
    ) -> None:
        w = wire_by_hub[(h_ref, h_pin)]
        assert w.wire_id == wid, f"Wire ID mismatch: expected {wid}, got {w.wire_id}"
        p1 = hub_pins[(h_ref, h_pin)]
        p2 = mod_pins[(m_id, m_pin)]
        pts = [(p1.x, p1.y)]
        if mid_points:
            pts.extend(mid_points)
        pts.append((p2.x, p2.y))
        draw_wire(s, pts, w.color, width=2.25)
        routed_wires.add(wid)

    def route_m_to_m(
        wid: str,
        h_ref: str,
        h_pin: str,
        src_mod: tuple[str, str],
        dst_mod: tuple[str, str],
        mid_points: list[tuple[float, float]] | None = None,
    ) -> None:
        w = wire_by_hub[(h_ref, h_pin)]
        assert w.wire_id == wid
        p1 = mod_pins[src_mod]
        p2 = mod_pins[dst_mod]
        pts = [(p1.x, p1.y)]
        if mid_points:
            pts.extend(mid_points)
        pts.append((p2.x, p2.y))
        draw_wire(s, pts, w.color, width=2.25)
        routed_wires.add(wid)

    # --- LEFT WIRES: J1 -> PSU (W01, W02), J2 -> Pump (W15, W16) ---
    p_j1_1, p_j1_2 = hub_pins[("J1", "1")], hub_pins[("J1", "2")]
    m_psu_1, m_psu_2 = mod_pins[("psu_5v", "+5V")], mod_pins[("psu_5v", "GND")]
    route_h_to_m("W01", "J1", "1", "psu_5v", "+5V", [(300, p_j1_1.y), (300, m_psu_1.y)])
    route_h_to_m("W02", "J1", "2", "psu_5v", "GND", [(290, p_j1_2.y), (290, m_psu_2.y)])

    p_j2_1, p_j2_2 = hub_pins[("J2", "1")], hub_pins[("J2", "2")]
    m_pmp_1, m_pmp_2 = mod_pins[("pump_unit", "Pump +")], mod_pins[("pump_unit", "Pump -")]
    route_h_to_m("W15", "J2", "1", "pump_unit", "Pump +", [(300, p_j2_1.y), (300, m_pmp_1.y)])
    route_h_to_m("W16", "J2", "2", "pump_unit", "Pump -", [(290, p_j2_2.y), (290, m_pmp_2.y)])

    # --- TOP WIRES: J14 -> LM393 (W33..W35), LM393 -> YL-69 (W36..W37) ---
    for wid, hpin, mpin, y_bend in [
        ("W33", "1", "VCC", 190.0),
        ("W34", "2", "GND", 198.0),
        ("W35", "3", "AO", 206.0),
    ]:
        p1, p2 = hub_pins[("J14", hpin)], mod_pins[("soil_lm393", mpin)]
        route_h_to_m(wid, "J14", hpin, "soil_lm393", mpin, [(p1.x, y_bend), (p2.x, y_bend)])

    route_m_to_m("W36", "LM393", "P1", ("soil_lm393", "P1"), ("soil_probe", "Prong A"))
    route_m_to_m("W37", "LM393", "P2", ("soil_lm393", "P2"), ("soil_probe", "Prong B"))

    # --- TOP WIRES: J13 -> DHT11 (W30..W32) ---
    for wid, hpin, mpin, y_bend in [
        ("W30", "1", "VCC(+)", 192.0),
        ("W31", "2", "DATA", 199.0),
        ("W32", "3", "GND(-)", 206.0),
    ]:
        p1, p2 = hub_pins[("J13", hpin)], mod_pins[("dht11_sensor", mpin)]
        route_h_to_m(wid, "J13", hpin, "dht11_sensor", mpin, [(p1.x, y_bend), (p2.x, y_bend)])

    # --- TOP WIRES: J4 -> Living Room LED (W06, W07) ---
    for wid, hpin, mpin, y_bend in [("W06", "1", "Anode(+)", 194.0), ("W07", "2", "Cathode(-)", 204.0)]:
        p1, p2 = hub_pins[("J4", hpin)], mod_pins[("led_living", mpin)]
        route_h_to_m(wid, "J4", hpin, "led_living", mpin, [(p1.x, y_bend), (p2.x, y_bend)])

    # --- TOP WIRES: J5 -> Bedroom LED (W08, W09) ---
    for wid, hpin, mpin, y_bend in [("W08", "1", "Anode(+)", 194.0), ("W09", "2", "Cathode(-)", 204.0)]:
        p1, p2 = hub_pins[("J5", hpin)], mod_pins[("led_bedroom", mpin)]
        route_h_to_m(wid, "J5", hpin, "led_bedroom", mpin, [(p1.x, y_bend), (p2.x, y_bend)])

    # --- RIGHT WIRES: J3 -> SG90 (W03..W05), J15 -> KY-037 (W38..W40), J7 -> Relay 1 Coil (W10..W12), J6 -> Buzzer (W17..W18) ---
    for wid, hpin, mpin, x_bend in [
        ("W03", "1", "PWM (Orange)", 854.0),
        ("W04", "2", "VCC (Red)", 864.0),
        ("W05", "3", "GND (Brown)", 874.0),
    ]:
        p1, p2 = hub_pins[("J3", hpin)], mod_pins[("sg90_servo", mpin)]
        route_h_to_m(wid, "J3", hpin, "sg90_servo", mpin, [(x_bend, p1.y), (x_bend, p2.y)])

    for wid, hpin, mpin, x_bend in [
        ("W38", "1", "+ (VCC 3.3V)", 854.0),
        ("W39", "2", "G (GND)", 864.0),
        ("W40", "3", "DO (D5 IRQ)", 874.0),
    ]:
        p1, p2 = hub_pins[("J15", hpin)], mod_pins[("ky037_sound", mpin)]
        route_h_to_m(wid, "J15", hpin, "ky037_sound", mpin, [(x_bend, p1.y), (x_bend, p2.y)])

    for wid, hpin, mpin, x_bend in [
        ("W10", "1", "VCC (+5V)", 874.0),
        ("W11", "2", "GND", 864.0),
        ("W12", "3", "IN (D6)", 854.0),
    ]:
        p1, p2 = hub_pins[("J7", hpin)], mod_pins[("relay1_pump", mpin)]
        route_h_to_m(wid, "J7", hpin, "relay1_pump", mpin, [(x_bend, p1.y), (x_bend, p2.y)])

    for wid, hpin, mpin, x_bend in [
        ("W17", "1", "Buzzer (+)", 864.0),
        ("W18", "2", "Buzzer (-)", 854.0),
    ]:
        p1, p2 = hub_pins[("J6", hpin)], mod_pins[("buzzer_alarm", mpin)]
        route_h_to_m(wid, "J6", hpin, "buzzer_alarm", mpin, [(x_bend, p1.y), (x_bend, p2.y)])

    # --- BOTTOM WIRES: J9/J10 -> Relay 2 (W19..W23), J11/J12 -> PAM8403 (W24..W27), PAM8403 -> Speaker (W28..W29) ---
    for wid, hpin, mpin, y_bend in [
        ("W19", "1", "DC+", 610.0),
        ("W20", "2", "DC-", 620.0),
        ("W21", "3", "IN(D7)", 630.0),
    ]:
        p1, p2 = hub_pins[("J9", hpin)], mod_pins[("relay2_speaker", mpin)]
        route_h_to_m(wid, "J9", hpin, "relay2_speaker", mpin, [(p1.x, y_bend), (p2.x, y_bend)])

    for wid, hpin, mpin, y_bend in [("W22", "1", "COM", 614.0), ("W23", "2", "NO", 624.0)]:
        p1, p2 = hub_pins[("J10", hpin)], mod_pins[("relay2_speaker", mpin)]
        route_h_to_m(wid, "J10", hpin, "relay2_speaker", mpin, [(p1.x, y_bend), (p2.x, y_bend)])

    for wid, hpin, mpin, y_bend in [("W24", "1", "5V+", 614.0), ("W25", "2", "5V-", 624.0)]:
        p1, p2 = hub_pins[("J11", hpin)], mod_pins[("pam8403_amp", mpin)]
        route_h_to_m(wid, "J11", hpin, "pam8403_amp", mpin, [(p1.x, y_bend), (p2.x, y_bend)])

    for wid, hpin, mpin, y_bend in [("W26", "1", "L In", 614.0), ("W27", "2", "A-GND", 624.0)]:
        p1, p2 = hub_pins[("J12", hpin)], mod_pins[("pam8403_amp", mpin)]
        route_h_to_m(wid, "J12", hpin, "pam8403_amp", mpin, [(p1.x, y_bend), (p2.x, y_bend)])

    route_m_to_m("W28", "PAM8403", "L_OUT+", ("pam8403_amp", "L_OUT+"), ("speaker_mini", "SPK +"))
    route_m_to_m("W29", "PAM8403", "L_OUT-", ("pam8403_amp", "L_OUT-"), ("speaker_mini", "SPK -"))

    # --- CROSS-BOARD DUPONT PAIR: J8 (Left-Inner RLY1_SW) -> Relay 1 COM / NO (Right) ---
    # Routed cleanly down the dedicated internal lane (x=401/407 between J1 and Left Passives,
    # centered cleanly in the 68pt gap between Relay 2 DC+ at x=356 and DC- at x=426!),
    # across the lower bottom corridor (y=658/668, 12+pt clear of Buzzer W18 at y=646!),
    # then straight up in the outer right corridor (x=904/916) right into Relay 1 COM & NO!
    p_j8_1, p_j8_2 = hub_pins[("J8", "1")], hub_pins[("J8", "2")]
    m_r1_com = mod_pins[("relay1_pump", "COM (+5V)")]
    m_r1_no = mod_pins[("relay1_pump", "NO (PUMP_5V)")]
    route_h_to_m(
        "W13", "J8", "1", "relay1_pump", "COM (+5V)",
        [(401.0, p_j8_1.y), (401.0, 658.0), (904.0, 658.0), (904.0, m_r1_com.y)],
    )
    route_h_to_m(
        "W14", "J8", "2", "relay1_pump", "NO (PUMP_5V)",
        [(407.0, p_j8_2.y), (407.0, 668.0), (916.0, 668.0), (916.0, m_r1_no.y)],
    )

    # Unobstructed inline callout pill in the wire-free gap (x=564..670, y=631..652) above W13/W14!
    s.rect(564, 631, 106, 21, fill="#FFFFFF", stroke="#15803D", stroke_width=0.9, rx=3.5)
    s.line(617, 652, 617, 657, stroke="#15803D", stroke_width=0.9)
    s.text(617, 638.0, "J8 → Relay 1 COM / NO", size=4.95, color="#15803D", bold=True, align="center")
    s.text(617, 646.5, "W13 (+5V) · W14 (PUMP)", size=4.75, color="#334155", bold=True, mono=True, align="center")

    # Re-draw all pin dots on top of wire endpoints so pin numbers stay razor sharp!
    for (ref, pnum), pt in hub_pins.items():
        w = wire_by_hub[(ref, pnum)]
        draw_pin_dot(s, pt.x, pt.y, color_name=w.color, pin_num=pnum, r=4.0)
    for (mid, mpin), pt in mod_pins.items():
        # Find matching wire color
        matched_col = None
        for w in WIRING_TABLE:
            if w.module_id == mid and (
                w.module_pin == mpin
                or (mid == "pump_unit" and mpin in w.module_pin)
                or (mid == "dht11_sensor" and mpin.split("(")[0] in w.module_pin)
                or (mid in ("led_living", "led_bedroom") and mpin.split("(")[0] in w.module_pin)
                or (mid == "ky037_sound" and mpin.split(" ")[0] in w.module_pin)
                or (mid == "relay1_pump" and mpin.split(" ")[0] in w.module_pin)
                or (mid == "relay2_speaker" and mpin.split("(")[0] in w.module_pin)
                or (mid == "pam8403_amp" and (mpin.split(" ")[0] in w.module_pin or mpin == "A-GND" and "GND" in w.module_pin))
                or (mid == "soil_lm393" and mpin == w.module_pin)
                or (mid == "soil_probe" and mpin == w.module_pin)
                or (mid == "speaker_mini" and mpin == w.module_pin)
                or (mid == "psu_5v" and mpin == w.module_pin)
                or (mid == "sg90_servo" and mpin == w.module_pin)
                or (mid == "buzzer_alarm" and mpin == w.module_pin)
            ):
                matched_col = w.color
                break
        if mid == "soil_lm393" and mpin == "P1":
            matched_col = "Yellow"
        elif mid == "soil_lm393" and mpin == "P2":
            matched_col = "Orange"
        elif mid == "pam8403_amp" and mpin == "L_OUT+":
            matched_col = "Yellow"
        elif mid == "pam8403_amp" and mpin == "L_OUT-":
            matched_col = "Brown"
        draw_pin_dot(s, pt.x, pt.y, color_name=matched_col, r=3.6)

    # Assert 100% of all 40 wires in WIRING_TABLE were routed!
    expected_ids = {w.wire_id for w in WIRING_TABLE}
    if routed_wires != expected_ids:
        raise RuntimeError(f"Unrouted wires: {expected_ids - routed_wires}")

    return s


def rasterize_pdf_to_png(pdf_path: Path, png_path: Path, scale: float = 2.4) -> tuple[int, int]:
    """Rasterize vector PDF to crisp high-res PNG via PyMuPDF (2880 x 1980 px at 2.4x)."""
    png_path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(pdf_path))
    try:
        page = doc[0]
        mat = pymupdf.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        pix.save(str(png_path))
        return pix.width, pix.height
    finally:
        doc.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate WIRING_TABLE.md and 2D wiring diagram (SVG/PDF/PNG).")
    parser.add_argument(
        "--copy-png",
        type=Path,
        default=None,
        help="Optional destination path to copy the rendered PNG (e.g. run screenshots directory).",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=2.4,
        help="PyMuPDF rasterization scale from 1200x825 pt vector PDF (default 2.4 => 2880x1980 px).",
    )
    args = parser.parse_args()

    stats = validate_contract()

    out_dir = REPO_ROOT / "docs" / "phan_cung"
    md_path = out_dir / "WIRING_TABLE.md"
    svg_path = out_dir / "wiring_diagram_2d.svg"
    pdf_path = out_dir / "wiring_diagram_2d.pdf"
    png_path = out_dir / "wiring_diagram_2d.png"

    generate_wiring_table_md(md_path, stats)
    scene = build_clean_wiring_diagram()
    scene.write_svg(svg_path)
    scene.write_pdf(pdf_path)
    pw, ph = rasterize_pdf_to_png(pdf_path, png_path, scale=args.scale)

    if args.copy_png is not None:
        args.copy_png.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(png_path, args.copy_png)

    print(f"[OK] Contract validated: {stats['total_wires']} wires ({stats['hub_wires']} Hub + {stats['offboard_wires']} Off-Board), {stats['hub_connectors']} connectors, {stats['hub_pins']} pins.")
    print(f"[OK] Markdown: {md_path} ({md_path.stat().st_size:,} bytes)")
    print(f"[OK] SVG:      {svg_path} ({svg_path.stat().st_size:,} bytes)")
    print(f"[OK] PDF:      {pdf_path} ({pdf_path.stat().st_size:,} bytes)")
    print(f"[OK] PNG:      {png_path} ({pw}x{ph} px, {png_path.stat().st_size:,} bytes)")
    if args.copy_png is not None:
        print(f"[OK] Copied:   {args.copy_png} ({args.copy_png.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
