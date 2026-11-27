"""Single-source-of-truth parser for the real KiCad Hub PCB and off-board module specs.

Reads board outline (Edge.Cuts), mounting holes, and component footprint positions
directly from `hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb` (no hand-retyped
PCB geometry), and cross-checks with `kicad-cli` when available.
Also consolidates all off-board module dimensions from `hardware/mica/mica_design.py`
into a single structured registry for fit verification and screwless mount generation.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PRINT3D_ROOT = SCRIPT_DIR.parent
HARDWARE_ROOT = PRINT3D_ROOT.parent
MICA_DIR = HARDWARE_ROOT / "mica"
KICAD_PCB_PATH = HARDWARE_ROOT / "kicad" / "smarthome_hub" / "smarthome_hub.kicad_pcb"

if str(MICA_DIR) not in sys.path:
    sys.path.insert(0, str(MICA_DIR))

import mica_design as md


@dataclass(frozen=True)
class MountingHoleSpec:
    ref: str
    x_mm: float  # relative to PCB bottom-left (0, 0)
    y_mm: float
    drill_dia_mm: float
    pad_dia_mm: float


@dataclass(frozen=True)
class ComponentKeepout:
    ref: str
    footprint: str
    x_mm: float  # relative to PCB bottom-left (0, 0)
    y_mm: float
    rot_deg: float


@dataclass(frozen=True)
class PcbSpec:
    source_file: str
    origin_x_mm: float
    origin_y_mm: float
    width_mm: float
    height_mm: float
    thickness_mm: float
    corner_chamfer_mm: float
    mounting_holes: tuple[MountingHoleSpec, ...]
    hole_pitch_x_mm: float
    hole_pitch_y_mm: float
    hole_dia_mm: float
    keepouts: tuple[ComponentKeepout, ...]
    kicad_cli_verified: bool
    kicad_cli_version: str


@dataclass(frozen=True)
class ModuleFitSource:
    part_id: str
    name: str
    source_of_dimension: str
    board_size_xyz: tuple[float, float, float]
    hole_pitch_xy: tuple[float, float] | None
    hole_dia_mm: float | None
    mount_part_id: str
    holding_method: str
    clearance_key: str
    center_xyz: tuple[float, float, float]


def find_kicad_cli() -> pathlib.Path | None:
    candidates = [
        pathlib.Path(r"C:\Users\LENOVO\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe"),
        pathlib.Path(r"C:\Users\LENOVO\AppData\Local\Programs\KiCad\9.0\bin\kicad-cli.exe"),
        pathlib.Path(r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"),
        pathlib.Path(r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _extract_balanced_blocks(text: str, token: str) -> list[str]:
    """Extract balanced S-expression blocks starting with `(<token>`."""
    blocks: list[str] = []
    needle = f"({token}"
    start = 0
    n = len(text)
    while True:
        idx = text.find(needle, start)
        if idx < 0:
            break
        # Ensure token boundary (space, newline, or tab)
        after = idx + len(needle)
        if after < n and text[after] not in " \t\r\n":
            start = after
            continue
        depth = 0
        in_str = False
        esc = False
        i = idx
        while i < n:
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
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
                        blocks.append(text[idx : i + 1])
                        start = i + 1
                        break
            i += 1
        else:
            break
    return blocks


def parse_kicad_hub_pcb(pcb_path: pathlib.Path = KICAD_PCB_PATH, run_cli_check: bool = True) -> PcbSpec:
    """Parse real Edge.Cuts outline, mounting holes, and footprints from `smarthome_hub.kicad_pcb`."""
    if not pcb_path.exists():
        raise FileNotFoundError(f"KiCad PCB not found: {pcb_path}")
    text = pcb_path.read_text(encoding="utf-8")

    # 1. Board thickness from (general (thickness ...))
    m_thick = re.search(r"\(thickness\s+([0-9.]+)\)", text)
    thickness_mm = float(m_thick.group(1)) if m_thick else 1.6

    # 2. Extract all Edge.Cuts segments (gr_line, gr_arc, gr_rect)
    xs: list[float] = []
    ys: list[float] = []
    chamfer_vals: list[float] = []

    for tok in ("gr_line", "gr_arc", "gr_rect"):
        for blk in _extract_balanced_blocks(text, tok):
            if '"Edge.Cuts"' not in blk and "Edge.Cuts" not in blk:
                continue
            pts = re.findall(r"\((?:start|mid|end)\s+([0-9.\-]+)\s+([0-9.\-]+)\)", blk)
            for sx, sy in pts:
                xs.append(float(sx))
                ys.append(float(sy))
            if tok == "gr_line" and len(pts) == 2:
                x1, y1 = float(pts[0][0]), float(pts[0][1])
                x2, y2 = float(pts[1][0]), float(pts[1][1])
                if abs(x1 - x2) > 0.1 and abs(y1 - y2) > 0.1:
                    chamfer_vals.append(round(abs(x1 - x2), 3))

    if not xs or not ys:
        raise ValueError(f"No Edge.Cuts geometry found in {pcb_path}")

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width_mm = round(max_x - min_x, 4)
    height_mm = round(max_y - min_y, 4)

    # Infer corner chamfer/fillet from Edge.Cuts endpoints vs bounding box
    if not chamfer_vals:
        for tok in ("gr_line",):
            for blk in _extract_balanced_blocks(text, tok):
                if "Edge.Cuts" not in blk:
                    continue
                pts = re.findall(r"\((?:start|end)\s+([0-9.\-]+)\s+([0-9.\-]+)\)", blk)
                for sx, sy in pts:
                    fx, fy = float(sx), float(sy)
                    if abs(fy - min_y) < 1e-3 or abs(fy - max_y) < 1e-3:
                        dx = min(abs(fx - min_x), abs(fx - max_x))
                        if dx > 0.1:
                            chamfer_vals.append(round(dx, 3))
    corner_chamfer_mm = round(min(chamfer_vals), 3) if chamfer_vals else 0.0

    # 3. Extract footprints: mounting holes & keepouts
    mounting_holes: list[MountingHoleSpec] = []
    keepouts: list[ComponentKeepout] = []

    for blk in _extract_balanced_blocks(text, "footprint"):
        m_fp = re.match(r'\(footprint\s+"([^"]+)"', blk)
        if not m_fp:
            continue
        fp_name = m_fp.group(1)
        m_at = re.search(r"\(at\s+([0-9.\-]+)\s+([0-9.\-]+)(?:\s+([0-9.\-]+))?\)", blk)
        if not m_at:
            continue
        fx = float(m_at.group(1))
        fy = float(m_at.group(2))
        rot = float(m_at.group(3)) if m_at.group(3) else 0.0
        # Board-local coordinates (Y flipped so bottom-left is (0, 0) in CAD XY)
        # Note: KiCad Y increases downward; board is symmetric (5.0 mm inset on all 4 corners).
        lx = round(fx - min_x, 4)
        ly = round(max_y - fy, 4)

        m_ref = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', blk)
        if not m_ref:
            m_ref = re.search(r'\(fp_text\s+reference\s+"([^"]+)"', blk)
        ref = m_ref.group(1) if m_ref else fp_name.split(":")[-1]

        if "mountinghole" in fp_name.lower() or ref.upper().startswith("H"):
            m_drill = re.search(r"\(drill\s+([0-9.]+)\)", blk)
            m_pad = re.search(r"\(size\s+([0-9.]+)\s+([0-9.]+)\)", blk)
            drill_d = float(m_drill.group(1)) if m_drill else 3.2
            pad_d = float(m_pad.group(1)) if m_pad else drill_d
            mounting_holes.append(MountingHoleSpec(
                ref=ref,
                x_mm=lx,
                y_mm=ly,
                drill_dia_mm=round(drill_d, 3),
                pad_dia_mm=round(pad_d, 3),
            ))
        else:
            keepouts.append(ComponentKeepout(
                ref=ref,
                footprint=fp_name,
                x_mm=lx,
                y_mm=ly,
                rot_deg=rot,
            ))

    if len(mounting_holes) < 4:
        raise ValueError(f"Expected 4 mounting holes in {pcb_path}, found {len(mounting_holes)}")

    hx_vals = sorted({round(h.x_mm, 3) for h in mounting_holes})
    hy_vals = sorted({round(h.y_mm, 3) for h in mounting_holes})
    pitch_x = round(hx_vals[-1] - hx_vals[0], 3)
    pitch_y = round(hy_vals[-1] - hy_vals[0], 3)
    hole_dia = round(sum(h.drill_dia_mm for h in mounting_holes) / len(mounting_holes), 3)

    # 4. Optional cross-check via kicad-cli (verifies real KiCad CLI reads the board cleanly)
    cli_ok = False
    cli_ver = ""
    if run_cli_check:
        cli = find_kicad_cli()
        if cli is not None:
            try:
                vproc = subprocess.run([str(cli), "--version"], capture_output=True, text=True, timeout=15)
                if vproc.returncode == 0:
                    cli_ver = vproc.stdout.strip()
                with tempfile.TemporaryDirectory(prefix="kicad_chk_") as td:
                    out_pos = pathlib.Path(td) / "pos.csv"
                    pproc = subprocess.run(
                        [str(cli), "pcb", "export", "pos", "--format", "csv", "--units", "mm", "-o", str(out_pos), str(pcb_path)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    cli_ok = (pproc.returncode == 0 and out_pos.exists() and out_pos.stat().st_size > 50)
            except Exception:
                cli_ok = False

    return PcbSpec(
        source_file="hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb",
        origin_x_mm=round(min_x, 4),
        origin_y_mm=round(min_y, 4),
        width_mm=width_mm,
        height_mm=height_mm,
        thickness_mm=thickness_mm,
        corner_chamfer_mm=corner_chamfer_mm,
        mounting_holes=tuple(sorted(mounting_holes, key=lambda h: (h.y_mm, h.x_mm))),
        hole_pitch_x_mm=pitch_x,
        hole_pitch_y_mm=pitch_y,
        hole_dia_mm=hole_dia,
        keepouts=tuple(keepouts),
        kicad_cli_verified=cli_ok,
        kicad_cli_version=cli_ver,
    )


def build_module_fit_registry(pcb: PcbSpec | None = None) -> list[ModuleFitSource]:
    """Build single-source module fit table combining KiCad PCB and mica_design.py datasheets."""
    pcb = pcb or parse_kicad_hub_pcb(run_cli_check=False)
    hw_map = {h.part_id: h for h in md.HARDWARE_PARTS}

    return [
        ModuleFitSource(
            part_id="HW_PCB",
            name="Smart Home Central Hub PCB (Type 1)",
            source_of_dimension=f"{pcb.source_file} (Edge.Cuts + 4x MountingHole_3.2mm)",
            board_size_xyz=(pcb.width_mm, pcb.height_mm, pcb.thickness_mm),
            hole_pitch_xy=(pcb.hole_pitch_x_mm, pcb.hole_pitch_y_mm),
            hole_dia_mm=pcb.hole_dia_mm,
            mount_part_id="SUP06_HUB_PCB_SNAP_CARRIER",
            holding_method="4x split cantilever snap-fit pegs into 3.2mm PCB holes + corner support pads",
            clearance_key="snap_fit_peg",
            center_xyz=hw_map["HW_PCB"].center_xyz,
        ),
        ModuleFitSource(
            part_id="HW_NODEMCU",
            name="ESP8266 NodeMCU v2 Amica",
            source_of_dimension=f"{pcb.source_file} (PinSocket_1x15 22.86mm) + Components101 datasheet",
            board_size_xyz=hw_map["HW_NODEMCU"].size_xyz,
            hole_pitch_xy=(22.86, 35.56),
            hole_dia_mm=None,
            mount_part_id="SUP06_HUB_PCB_SNAP_CARRIER (via Hub PCB U1/U2 sockets)",
            holding_method="Direct 2x15 female pin headers on Hub PCB; carrier clears USB and underside solder pins",
            clearance_key="edge_rail",
            center_xyz=hw_map["HW_NODEMCU"].center_xyz,
        ),
        ModuleFitSource(
            part_id="HW_RELAY1",
            name="5V 1-Channel Relay #1 (Pump D6)",
            source_of_dimension="mica_design.py + Reichelt/HandsOnTech SRD-05VDC datasheet",
            board_size_xyz=hw_map["HW_RELAY1"].size_xyz,
            hole_pitch_xy=(44.5, 20.5),
            hole_dia_mm=3.1,
            mount_part_id="SUP07_RELAY_SNAP_CADDY",
            holding_method="4x split snap-fit pegs (44.5x20.5) + perimeter rail + base mortise tenons into P01A",
            clearance_key="snap_fit_peg",
            center_xyz=hw_map["HW_RELAY1"].center_xyz,
        ),
        ModuleFitSource(
            part_id="HW_RELAY2",
            name="5V 1-Channel Relay #2 (Audio D7)",
            source_of_dimension="mica_design.py + Electrokit SRD-05VDC datasheet",
            board_size_xyz=hw_map["HW_RELAY2"].size_xyz,
            hole_pitch_xy=(44.5, 20.5),
            hole_dia_mm=3.1,
            mount_part_id="SUP07_RELAY_SNAP_CADDY",
            holding_method="4x split snap-fit pegs (44.5x20.5) + perimeter rail + base mortise tenons into P01A",
            clearance_key="snap_fit_peg",
            center_xyz=hw_map["HW_RELAY2"].center_xyz,
        ),
        ModuleFitSource(
            part_id="HW_PAM8403",
            name="PAM8403 3W Class-D Audio Amplifier",
            source_of_dimension="mica_design.py + Elecrow PAM8403 datasheet",
            board_size_xyz=hw_map["HW_PAM8403"].size_xyz,
            hole_pitch_xy=None,
            hole_dia_mm=None,
            mount_part_id="SUP08_PAM8403_SNAP_TRAY",
            holding_method="Edge rails + side cantilever snap lips + 2x base mortise tenons into P01A",
            clearance_key="edge_rail",
            center_xyz=hw_map["HW_PAM8403"].center_xyz,
        ),
        ModuleFitSource(
            part_id="HW_SPEAKER",
            name="Mini Round Speaker 28mm 8Ohm 0.5W",
            source_of_dimension="mica_design.py + PUI Audio AS02808MR-R datasheet",
            board_size_xyz=hw_map["HW_SPEAKER"].size_xyz,
            hole_pitch_xy=None,
            hole_dia_mm=None,
            mount_part_id="SUP09_SPEAKER_SNAP_RETAINER",
            holding_method="Rear pressure cradle locking into 2x rectangular mortise slots on P15_TECH_FASCIA",
            clearance_key="edge_rail",
            center_xyz=hw_map["HW_SPEAKER"].center_xyz,
        ),
        ModuleFitSource(
            part_id="HW_SG90",
            name="TowerPro SG90 9g Micro Servo",
            source_of_dimension="mica_design.py + HandsOnTech SG90 datasheet",
            board_size_xyz=(12.2, 22.8, 22.5),  # body in P07 cutout (tab span 32.2 mm)
            hole_pitch_xy=(0.0, 27.8),
            hole_dia_mm=2.0,
            mount_part_id="SUP11_SG90_SNAP_SADDLE + P07_SERVO_SHELF",
            holding_method="Drop-in P07 cutout (12.7x23.3) clamped by snap-fit saddle locking into 2x P07 mortises",
            clearance_key="edge_rail",
            center_xyz=hw_map["HW_SG90"].center_xyz,
        ),
        ModuleFitSource(
            part_id="HW_DHT11",
            name="DHT11 Temp/Humidity Breakout Module",
            source_of_dimension="mica_design.py + Aosong/DFRobot DHT11 datasheet",
            board_size_xyz=hw_map["HW_DHT11"].size_xyz,
            hole_pitch_xy=None,
            hole_dia_mm=3.0,
            mount_part_id="SUP12_DHT11_SNAP_CRADLE",
            holding_method="Vertical edge-rail snap cradle plugging into 2x P06_WALL_MID Living Room mortise slots",
            clearance_key="edge_rail",
            center_xyz=hw_map["HW_DHT11"].center_xyz,
        ),
        ModuleFitSource(
            part_id="HW_KY037",
            name="KY-037 / KY-038 Sound Sensor Module",
            source_of_dimension="mica_design.py + Joy-IT KY-038/KY-037 datasheet",
            board_size_xyz=hw_map["HW_KY037"].size_xyz,
            hole_pitch_xy=None,
            hole_dia_mm=3.0,
            mount_part_id="SUP13_KY037_SNAP_CRADLE",
            holding_method="Horizontal edge-rail snap cradle plugging into 2x P05_WALL_FRONT mortise slots",
            clearance_key="edge_rail",
            center_xyz=hw_map["HW_KY037"].center_xyz,
        ),
        ModuleFitSource(
            part_id="HW_SOIL_PROBE",
            name="YL-69 Soil Moisture 2-Prong Probe",
            source_of_dimension="mica_design.py + HandsOnTech Soil Sensor datasheet",
            board_size_xyz=hw_map["HW_SOIL_PROBE"].size_xyz,
            hole_pitch_xy=None,
            hole_dia_mm=None,
            mount_part_id="P14_SOIL_BRIDGE",
            holding_method="Direct vertical drop-in through 22.0 x 3.5 mm slot on P14_SOIL_BRIDGE",
            clearance_key="panel_tab_slot",
            center_xyz=hw_map["HW_SOIL_PROBE"].center_xyz,
        ),
        ModuleFitSource(
            part_id="HW_LM393",
            name="LM393 Soil Comparator Module (YL-38)",
            source_of_dimension="mica_design.py + HandsOnTech Soil Sensor datasheet",
            board_size_xyz=hw_map["HW_LM393"].size_xyz,
            hole_pitch_xy=None,
            hole_dia_mm=3.0,
            mount_part_id="SUP14_LM393_SNAP_CRADLE",
            holding_method="Edge-rail snap cradle plugging into 2x P13_GARDEN_BACK dry exterior rear mortise slots",
            clearance_key="edge_rail",
            center_xyz=hw_map["HW_LM393"].center_xyz,
        ),
        ModuleFitSource(
            part_id="HW_DOOR_HINGE",
            name="Main Door Hinge & Servo Linkage (P08 -> P05)",
            source_of_dimension="mica_design.py (P08 56x100 in 60x104 opening, 2.0mm clearance)",
            board_size_xyz=(56.0, 3.0, 100.0),
            hole_pitch_xy=None,
            hole_dia_mm=None,
            mount_part_id="SUP10_DOOR_MORTISE_HINGE + SUP10B_SERVO_LINK_CLIP",
            holding_method="Mortise-tenon pin-and-knuckle hinge (0.30mm pivot clearance) + snap linkage clip",
            clearance_key="hinge_pivot",
            center_xyz=(106.0, 193.5, 52.0),
        ),
    ]


if __name__ == "__main__":
    pcb = parse_kicad_hub_pcb(run_cli_check=True)
    mods = build_module_fit_registry(pcb)
    print(f"KiCad PCB: {pcb.width_mm} x {pcb.height_mm} x {pcb.thickness_mm} mm (chamfer {pcb.corner_chamfer_mm} mm)")
    print(f"  Holes: {len(pcb.mounting_holes)}x dia={pcb.hole_dia_mm} mm, pitch={pcb.hole_pitch_x_mm} x {pcb.hole_pitch_y_mm} mm")
    for h in pcb.mounting_holes:
        print(f"    {h.ref}: ({h.x_mm}, {h.y_mm}) drill={h.drill_dia_mm} mm")
    print(f"  Footprints/keepouts: {len(pcb.keepouts)}, kicad-cli verified={pcb.kicad_cli_verified} ({pcb.kicad_cli_version})")
    print(f"  Registered modules in fit table: {len(mods)}")
