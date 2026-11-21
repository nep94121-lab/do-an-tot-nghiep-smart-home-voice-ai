#!/usr/bin/env python3
"""Deterministic KiCad 10 Single-Layer DIY Hub PCB & Schematic Synchronizer.

Redesigns `hardware/kicad/smarthome_hub` for home toner-transfer etching and hand drilling:
  - Board outline: 100.0 x 80.0 x 1.6 mm rectangular with 3.0 mm corner radius (Edge.Cuts)
  - 4x M3 (3.2 mm NPTH) mounting holes at (5,5), (95,5), (5,75), (95,75) mm from board
    lower-left corner (90 x 70 mm hole pattern)
  - Single copper layer ONLY (B.Cu): 0 vias, 0 copper on F.Cu (tracks/zones/pads)
  - Signal tracks >= 1.0 mm, Power & GND tracks >= 2.0 mm, Copper clearance >= 0.60 mm
  - Exactly 4 drill classes: 0.9 mm, 1.1 mm, 1.3 mm, 3.2 mm (enforced by .kicad_dru)
  - Oversized forgiving pads (>= 2.6 mm round; elongated 3.80 x 1.80 mm ovals on 2.54 mm headers)
  - Large readable F.SilkS labels (>= 1.5 mm height, >= 0.25 mm thickness), zero pad overlap
  - 7 minimal top-side wire jumpers (JP1..JP7) modeled as real parts in schematic, PCB, BOM
  - Exact 50.00 mm calibration scale bar on Dwgs.User for 1:1 toner PDF verification
  - Synchronizes smarthome_hub.kicad_sch, smarthome_hub.kicad_pcb, smarthome_hub.kicad_pro,
    smarthome_hub.kicad_dru, DIY_Hub.pretty/, fp-lib-table, and bom.csv with:
      * 0 ERC errors / 0 warnings
      * 0 DRC violations / 0 unconnected items / 0 schematic-parity errors
"""
from __future__ import annotations

import collections
import csv
import json
import math
import pathlib
import re
import subprocess
import uuid
from dataclasses import dataclass

KICAD_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = KICAD_DIR.parent.parent.parent
FP_LIB_DIR = KICAD_DIR / "DIY_Hub.pretty"
KCLI = r"C:\Users\LENOVO\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe"
KPY = r"C:\Users\LENOVO\AppData\Local\Programs\KiCad\10.0\bin\python.exe"

BOARD_W = 100.0
BOARD_H = 80.0
CORNER_R = 3.0
BX0 = 50.0
BY0 = 45.0
BY_BOT = BY0 + BOARD_H  # 125.0 (board lower-left in KiCad sheet coords)

ROOT_SHEET_UUID = "20f08b23-d419-582e-a433-7afe7edbad64"
NS = uuid.UUID("a4b8c2d0-7f13-4e21-9b5a-3c8e7d6f2026")

POWER_NETS_ALL = (
    "+5V", "+5V_RLY1", "+5V_RLY2", "+5V_TOP", "+5V_SERVO",
    "+3V3", "+3V3_R", "+3V3_TOP", "+3V3_SOIL",
    "GND", "PUMP_5V", "AMP_5V",
)


def duuid(key: str) -> str:
    return str(uuid.uuid5(NS, key))


def b2k(bx: float, by: float) -> tuple[float, float]:
    return round(BX0 + bx, 4), round(BY_BOT - by, 4)


def rot_local(dx: float, dyk: float, rot_deg: float) -> tuple[float, float]:
    a = math.radians(rot_deg)
    c, s = math.cos(a), math.sin(a)
    return dx * c + dyk * s, dx * s - dyk * c


def fmt(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _pad_sexpr(
    num: str,
    ptype: str,
    shape: str,
    x: float,
    y: float,
    sx: float,
    sy: float,
    drill: float,
    *,
    pad_rot: float = 0.0,
    net: tuple[int, str] | None = None,
    key: str = "",
) -> str:
    rot_s = f" {fmt(pad_rot)}" if abs(pad_rot) > 1e-6 else ""
    if ptype == "np_thru_hole":
        return (
            f'\t(pad "" np_thru_hole circle\n'
            f'\t\t(at {fmt(x)} {fmt(y)}{rot_s})\n'
            f'\t\t(size {fmt(drill)} {fmt(drill)})\n'
            f'\t\t(drill {fmt(drill)})\n'
            f'\t\t(layers "*.Cu" "*.Mask")\n'
            f'\t\t(uuid "{duuid(key)}")\n'
            f'\t)'
        )
    net_line = f'\t\t(net {net[0]} "{net[1]}")\n' if net and net[0] > 0 else ""
    return (
        f'\t(pad "{num}" thru_hole {shape}\n'
        f'\t\t(at {fmt(x)} {fmt(y)}{rot_s})\n'
        f'\t\t(size {fmt(sx)} {fmt(sy)})\n'
        f'\t\t(drill {fmt(drill)})\n'
        f'\t\t(layers "B.Cu" "B.Mask")\n'
        f'\t\t(remove_unused_layers no)\n'
        f'{net_line}'
        f'\t\t(uuid "{duuid(key)}")\n'
        f'\t)'
    )


def _line(x1: float, y1: float, x2: float, y2: float, layer: str, width: float, key: str) -> str:
    return (
        f'\t(fp_line (start {fmt(x1)} {fmt(y1)}) (end {fmt(x2)} {fmt(y2)})\n'
        f'\t\t(stroke (width {fmt(width)}) (type solid)) (layer "{layer}") (uuid "{duuid(key)}"))'
    )


def _rect(x1: float, y1: float, x2: float, y2: float, layer: str, width: float, key: str) -> str:
    return (
        f'\t(fp_rect (start {fmt(x1)} {fmt(y1)}) (end {fmt(x2)} {fmt(y2)})\n'
        f'\t\t(stroke (width {fmt(width)}) (type solid)) (fill no) (layer "{layer}") (uuid "{duuid(key)}"))'
    )


def _circle(cx: float, cy: float, r: float, layer: str, width: float, key: str) -> str:
    return (
        f'\t(fp_circle (center {fmt(cx)} {fmt(cy)}) (end {fmt(cx + r)} {fmt(cy)})\n'
        f'\t\t(stroke (width {fmt(width)}) (type solid)) (fill no) (layer "{layer}") (uuid "{duuid(key)}"))'
    )


def _model(path: str, ox: float = 0.0, oy: float = 0.0, oz: float = 0.0) -> str:
    return (
        f'\t(model "{path}"\n'
        f'\t\t(offset (xyz {fmt(ox)} {fmt(oy)} {fmt(oz)}))\n'
        f'\t\t(scale (xyz 1 1 1))\n'
        f'\t\t(rotate (xyz 0 0 0))\n'
        f'\t)'
    )


def build_footprint_body(
    name: str,
    descr: str,
    *,
    is_board_instance: bool = False,
    ref: str = "REF**",
    value: str = "",
    at_kx: float = 0.0,
    at_ky: float = 0.0,
    rot_deg: float = 0.0,
    pad_nets: dict[str, tuple[int, str]] | None = None,
    fp_uuid_key: str = "",
    jumper_pitch: float | None = None,
    sch_path: str = "",
    sch_descr: str | None = None,
) -> str:
    p = pad_nets or {}
    kpref = fp_uuid_key or f"lib:{name}"
    val_str = value or name
    pad_rot = rot_deg if is_board_instance else 0.0
    desc_prop = sch_descr if (is_board_instance and sch_descr is not None) else descr

    lines: list[str] = []
    if is_board_instance:
        lines.append(f'\t(footprint "DIY_Hub:{name}"')
        lines.append('\t\t(layer "F.Cu")')
        lines.append(f'\t\t(uuid "{duuid(kpref + ":fp")}")')
        lines.append(f'\t\t(at {fmt(at_kx)} {fmt(at_ky)} {fmt(rot_deg)})')
    else:
        lines.append(f'(footprint "{name}"')
        lines.append('\t(version 20260206)')
        lines.append('\t(generator "pcbnew")')
        lines.append('\t(generator_version "10.0")')
        lines.append('\t(layer "F.Cu")')
    lines.append(f'\t(descr "{descr}")')

    lines.append(
        f'\t(property "Reference" "{ref}"\n'
        f'\t\t(at 0 -3.5 0)\n'
        f'\t\t(layer "F.SilkS")\n'
        f'\t\t(hide yes)\n'
        f'\t\t(uuid "{duuid(kpref + ":ref")}")\n'
        f'\t\t(effects (font (size 1.5 1.5) (thickness 0.25)))\n'
        f'\t)'
    )
    lines.append(
        f'\t(property "Value" "{val_str}"\n'
        f'\t\t(at 0 3.5 0)\n'
        f'\t\t(layer "F.Fab")\n'
        f'\t\t(hide yes)\n'
        f'\t\t(uuid "{duuid(kpref + ":val")}")\n'
        f'\t\t(effects (font (size 1.0 1.0) (thickness 0.15)))\n'
        f'\t)'
    )
    lines.append(
        f'\t(property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{duuid(kpref + ":ds")}")\n'
        f'\t\t(effects (font (size 1.0 1.0) (thickness 0.15))))'
    )
    lines.append(
        f'\t(property "Description" "{desc_prop}" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{duuid(kpref + ":desc")}")\n'
        f'\t\t(effects (font (size 1.0 1.0) (thickness 0.15))))'
    )
    if is_board_instance and sch_path:
        lines.append(f'\t(path "{sch_path}")')
    if name == "MountingHole_3.2mm_M3_DIY":
        lines.append('\t(attr exclude_from_pos_files)')
    else:
        lines.append('\t(attr through_hole)')
    lines.append('\t(duplicate_pad_numbers_are_jumpers no)')

    sw = 0.25

    if name in ("PinSocket_1x15_P2.54mm_DIY", "PinHeader_1x02_P2.54mm_DIY", "PinHeader_1x03_P2.54mm_DIY"):
        n_pins = 15 if "1x15" in name else (3 if "1x03" in name else 2)
        y_end = (n_pins - 1) * 2.54
        lines.append(_rect(-1.45, -1.45, 1.45, y_end + 1.45, "F.SilkS", sw, f"{kpref}:sbox"))
        lines.append(_line(-1.45, -1.45, 1.45, -1.45, "F.SilkS", 0.45, f"{kpref}:sp1"))
        lines.append(_rect(-1.27, -1.27, 1.27, y_end + 1.27, "F.Fab", 0.12, f"{kpref}:fab"))
        lines.append(_rect(-2.00, -1.35, 2.00, y_end + 1.35, "F.CrtYd", 0.05, f"{kpref}:crt"))
        for i in range(n_pins):
            pnum = str(i + 1)
            shp = "rect" if i == 0 else "oval"
            lines.append(_pad_sexpr(pnum, "thru_hole", shp, 0.0, i * 2.54, 3.80, 1.80, 1.1, pad_rot=pad_rot, net=p.get(pnum), key=f"{kpref}:p{pnum}"))
        if n_pins == 15:
            lines.append(_model("${KICAD10_3DMODEL_DIR}/Connector_PinSocket_2.54mm.3dshapes/PinSocket_1x15_P2.54mm_Vertical.step"))
        elif n_pins == 3:
            lines.append(_model("${KICAD10_3DMODEL_DIR}/Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x03_P2.54mm_Vertical.step"))
        else:
            lines.append(_model("${KICAD10_3DMODEL_DIR}/Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x02_P2.54mm_Vertical.step"))

    elif name == "TerminalBlock_MKDS_1x02_P5.08mm_DIY":
        lines.append(_rect(-2.65, -4.95, 7.73, 4.95, "F.SilkS", sw, f"{kpref}:sbox"))
        lines.append(_line(-2.65, 3.80, 7.73, 3.80, "F.SilkS", sw, f"{kpref}:smouth"))
        lines.append(_rect(-2.54, -4.90, 7.62, 4.90, "F.Fab", 0.12, f"{kpref}:fab"))
        lines.append(_rect(-2.85, -5.15, 7.93, 5.15, "F.CrtYd", 0.05, f"{kpref}:crt"))
        lines.append(_pad_sexpr("1", "thru_hole", "rect", 0.0, 0.0, 3.20, 4.40, 1.3, pad_rot=pad_rot, net=p.get("1"), key=f"{kpref}:p1"))
        lines.append(_pad_sexpr("2", "thru_hole", "oval", 5.08, 0.0, 3.20, 4.40, 1.3, pad_rot=pad_rot, net=p.get("2"), key=f"{kpref}:p2"))
        lines.append(_model("${KICAD10_3DMODEL_DIR}/TerminalBlock_Phoenix.3dshapes/TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal.step"))

    elif name == "R_Axial_P10.16mm_DIY":
        lines.append(_rect(1.90, -1.35, 8.26, 1.35, "F.SilkS", sw, f"{kpref}:sbox"))
        lines.append(_rect(1.93, -1.25, 8.23, 1.25, "F.Fab", 0.12, f"{kpref}:fab"))
        lines.append(_rect(-1.50, -1.50, 11.66, 1.50, "F.CrtYd", 0.05, f"{kpref}:crt"))
        lines.append(_pad_sexpr("1", "thru_hole", "circle", 0.0, 0.0, 2.60, 2.60, 0.9, pad_rot=pad_rot, net=p.get("1"), key=f"{kpref}:p1"))
        lines.append(_pad_sexpr("2", "thru_hole", "circle", 10.16, 0.0, 2.60, 2.60, 0.9, pad_rot=pad_rot, net=p.get("2"), key=f"{kpref}:p2"))
        lines.append(_model("${KICAD10_3DMODEL_DIR}/Resistor_THT.3dshapes/R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal.step"))

    elif name == "D_DO41_P10.16mm_DIY":
        lines.append(_rect(2.35, -1.50, 7.81, 1.50, "F.SilkS", sw, f"{kpref}:sbox"))
        lines.append(_line(3.15, -1.50, 3.15, 1.50, "F.SilkS", 0.60, f"{kpref}:kbar"))
        lines.append(_line(3.65, -1.50, 3.65, 1.50, "F.SilkS", 0.45, f"{kpref}:kbar2"))
        lines.append(_rect(2.48, -1.36, 7.68, 1.36, "F.Fab", 0.12, f"{kpref}:fab"))
        lines.append(_rect(-1.50, -1.90, 11.66, 1.90, "F.CrtYd", 0.05, f"{kpref}:crt"))
        lines.append(_pad_sexpr("1", "thru_hole", "rect", 0.0, 0.0, 2.60, 3.40, 1.1, pad_rot=pad_rot, net=p.get("1"), key=f"{kpref}:p1"))
        lines.append(_pad_sexpr("2", "thru_hole", "oval", 10.16, 0.0, 2.60, 3.40, 1.1, pad_rot=pad_rot, net=p.get("2"), key=f"{kpref}:p2"))
        lines.append(_model("${KICAD10_3DMODEL_DIR}/Diode_THT.3dshapes/D_DO-41_SOD81_P10.16mm_Horizontal.step"))

    elif name == "CP_Radial_D8.0mm_P3.50mm_DIY":
        lines.append(_circle(1.75, 0.0, 4.15, "F.SilkS", sw, f"{kpref}:scirc"))
        lines.append(_line(-3.4, -2.5, -2.0, -2.5, "F.SilkS", 0.25, f"{kpref}:plus_h"))
        lines.append(_line(-2.7, -3.2, -2.7, -1.8, "F.SilkS", 0.25, f"{kpref}:plus_v"))
        lines.append(_circle(1.75, 0.0, 4.00, "F.Fab", 0.12, f"{kpref}:fab"))
        lines.append(_circle(1.75, 0.0, 4.35, "F.CrtYd", 0.05, f"{kpref}:crt"))
        lines.append(_pad_sexpr("1", "thru_hole", "rect", 0.0, 0.0, 2.60, 3.60, 0.9, pad_rot=pad_rot, net=p.get("1"), key=f"{kpref}:p1"))
        lines.append(_pad_sexpr("2", "thru_hole", "oval", 3.50, 0.0, 2.60, 3.60, 0.9, pad_rot=pad_rot, net=p.get("2"), key=f"{kpref}:p2"))
        lines.append(_model("${KICAD10_3DMODEL_DIR}/Capacitor_THT.3dshapes/CP_Radial_D8.0mm_P3.50mm.step"))

    elif name == "CP_Radial_D5.0mm_P3.50mm_DIY":
        lines.append(_circle(1.75, 0.0, 2.65, "F.SilkS", sw, f"{kpref}:scirc"))
        lines.append(_line(-2.2, -1.8, -1.2, -1.8, "F.SilkS", 0.25, f"{kpref}:plus_h"))
        lines.append(_line(-1.7, -2.3, -1.7, -1.3, "F.SilkS", 0.25, f"{kpref}:plus_v"))
        lines.append(_circle(1.75, 0.0, 2.50, "F.Fab", 0.12, f"{kpref}:fab"))
        lines.append(_circle(1.75, 0.0, 2.90, "F.CrtYd", 0.05, f"{kpref}:crt"))
        lines.append(_pad_sexpr("1", "thru_hole", "rect", 0.0, 0.0, 2.60, 3.40, 0.9, pad_rot=pad_rot, net=p.get("1"), key=f"{kpref}:p1"))
        lines.append(_pad_sexpr("2", "thru_hole", "oval", 3.50, 0.0, 2.60, 3.40, 0.9, pad_rot=pad_rot, net=p.get("2"), key=f"{kpref}:p2"))
        lines.append(_model("${KICAD10_3DMODEL_DIR}/Capacitor_THT.3dshapes/CP_Radial_D5.0mm_P2.50mm.step", ox=0.50))

    elif name == "C_Disc_D5.0mm_P5.00mm_DIY":
        lines.append(_rect(1.05, -1.40, 3.95, 1.40, "F.SilkS", sw, f"{kpref}:sbox"))
        lines.append(_rect(0.0, -1.25, 5.0, 1.25, "F.Fab", 0.12, f"{kpref}:fab"))
        lines.append(_rect(-1.50, -1.60, 6.50, 1.60, "F.CrtYd", 0.05, f"{kpref}:crt"))
        lines.append(_pad_sexpr("1", "thru_hole", "circle", 0.0, 0.0, 2.60, 2.60, 0.9, pad_rot=pad_rot, net=p.get("1"), key=f"{kpref}:p1"))
        lines.append(_pad_sexpr("2", "thru_hole", "circle", 5.00, 0.0, 2.60, 2.60, 0.9, pad_rot=pad_rot, net=p.get("2"), key=f"{kpref}:p2"))
        lines.append(_model("${KICAD10_3DMODEL_DIR}/Capacitor_THT.3dshapes/C_Disc_D5.0mm_W2.5mm_P5.00mm.step"))

    elif name == "LED_D3.0mm_P5.08mm_DIY":
        lines.append(_circle(2.54, 0.0, 1.95, "F.SilkS", sw, f"{kpref}:scirc"))
        lines.append(_line(1.20, -1.40, 1.20, 1.40, "F.SilkS", 0.35, f"{kpref}:kflat"))
        lines.append(_line(4.55, -2.10, 5.55, -2.10, "F.SilkS", 0.25, f"{kpref}:plus_h"))
        lines.append(_line(5.05, -2.60, 5.05, -1.60, "F.SilkS", 0.25, f"{kpref}:plus_v"))
        lines.append(_circle(2.54, 0.0, 1.50, "F.Fab", 0.12, f"{kpref}:fab"))
        lines.append(_rect(-1.60, -2.20, 6.68, 2.20, "F.CrtYd", 0.05, f"{kpref}:crt"))
        lines.append(_pad_sexpr("1", "thru_hole", "rect", 0.0, 0.0, 2.80, 2.80, 0.9, pad_rot=pad_rot, net=p.get("1"), key=f"{kpref}:p1"))
        lines.append(_pad_sexpr("2", "thru_hole", "circle", 5.08, 0.0, 2.80, 2.80, 0.9, pad_rot=pad_rot, net=p.get("2"), key=f"{kpref}:p2"))
        lines.append(_model("${KICAD10_3DMODEL_DIR}/LED_THT.3dshapes/LED_D3.0mm_Green.step", ox=1.27))

    elif name == "TO-92_Wide_DIY":
        # Flat face at +Y (bottom when rot=0), curved back at -Y; Pin 1=E (0,0), Pin 2=B (2.54,-2.54), Pin 3=C (5.08,0)
        lines.append(_line(0.74, 1.85, 4.34, 1.85, "F.SilkS", 0.35, f"{kpref}:sflat"))
        lines.append(
            f'\t(fp_arc (start 0.1728 -1.1038) (mid 0.6790 -1.8327) (end 1.40 -2.35)\n'
            f'\t\t(stroke (width {fmt(sw)}) (type solid)) (layer "F.SilkS") (uuid "{duuid(f"{kpref}:sa1")}"))'
        )
        lines.append(
            f'\t(fp_arc (start 0.74 1.85) (mid 0.4461 1.5093) (end 0.2158 1.1228)\n'
            f'\t\t(stroke (width {fmt(sw)}) (type solid)) (layer "F.SilkS") (uuid "{duuid(f"{kpref}:sa2")}"))'
        )
        lines.append(
            f'\t(fp_arc (start 3.65 -2.35) (mid 4.3823 -1.8332) (end 4.8955 -1.0984)\n'
            f'\t\t(stroke (width {fmt(sw)}) (type solid)) (layer "F.SilkS") (uuid "{duuid(f"{kpref}:sa3")}"))'
        )
        lines.append(
            f'\t(fp_arc (start 4.8642 1.1228) (mid 4.6339 1.5093) (end 4.34 1.85)\n'
            f'\t\t(stroke (width {fmt(sw)}) (type solid)) (layer "F.SilkS") (uuid "{duuid(f"{kpref}:sa4")}"))'
        )
        lines.append(_line(0.80, 1.75, 4.30, 1.75, "F.Fab", 0.12, f"{kpref}:fabflat"))
        lines.append(
            f'\t(fp_arc (start 0.7864 1.7536) (mid 0.2488 -0.9491) (end 2.54 -2.48)\n'
            f'\t\t(stroke (width 0.12) (type solid)) (layer "F.Fab") (uuid "{duuid(f"{kpref}:fa1")}"))'
        )
        lines.append(
            f'\t(fp_arc (start 2.54 -2.48) (mid 4.8312 -0.9491) (end 4.2936 1.7536)\n'
            f'\t\t(stroke (width 0.12) (type solid)) (layer "F.Fab") (uuid "{duuid(f"{kpref}:fa2")}"))'
        )
        lines.append(_rect(-1.50, -4.05, 6.58, 2.05, "F.CrtYd", 0.05, f"{kpref}:crt"))
        lines.append(_pad_sexpr("1", "thru_hole", "circle", 0.0, 0.0, 2.60, 2.60, 0.9, pad_rot=pad_rot, net=p.get("1"), key=f"{kpref}:p1"))
        lines.append(_pad_sexpr("2", "thru_hole", "circle", 2.54, -2.54, 2.60, 2.60, 0.9, pad_rot=pad_rot, net=p.get("2"), key=f"{kpref}:p2"))
        lines.append(_pad_sexpr("3", "thru_hole", "circle", 5.08, 0.0, 2.60, 2.60, 0.9, pad_rot=pad_rot, net=p.get("3"), key=f"{kpref}:p3"))
        lines.append(_model("${KICAD10_3DMODEL_DIR}/Package_TO_SOT_THT.3dshapes/TO-92_Wide.step"))

    elif name == "MountingHole_3.2mm_M3_DIY":
        lines.append(_circle(0.0, 0.0, 3.00, "F.SilkS", sw, f"{kpref}:scirc"))
        lines.append(_circle(0.0, 0.0, 3.00, "F.Fab", 0.12, f"{kpref}:fab"))
        lines.append(_circle(0.0, 0.0, 3.25, "F.CrtYd", 0.05, f"{kpref}:crt"))
        lines.append(_pad_sexpr("", "np_thru_hole", "circle", 0.0, 0.0, 3.20, 3.20, 3.2, pad_rot=pad_rot, key=f"{kpref}:npth"))

    elif name.startswith("WireJumper_P"):
        pitch = jumper_pitch if jumper_pitch is not None else float(name.split("_P")[1].split("mm")[0])
        lines.append(_line(1.30, 0.0, pitch - 1.30, 0.0, "F.SilkS", 0.45, f"{kpref}:jline"))
        lines.append(_circle(0.0, 0.0, 1.15, "F.SilkS", 0.25, f"{kpref}:jc1"))
        lines.append(_circle(pitch, 0.0, 1.15, "F.SilkS", 0.25, f"{kpref}:jc2"))
        lines.append(_line(0.0, 0.0, pitch, 0.0, "F.Fab", 0.25, f"{kpref}:jfab"))
        lines.append(_rect(-1.55, -1.55, pitch + 1.55, 1.55, "F.CrtYd", 0.05, f"{kpref}:crt"))
        lines.append(_pad_sexpr("1", "thru_hole", "circle", 0.0, 0.0, 2.80, 2.80, 0.9, pad_rot=pad_rot, net=p.get("1"), key=f"{kpref}:p1"))
        lines.append(_pad_sexpr("2", "thru_hole", "circle", pitch, 0.0, 2.80, 2.80, 0.9, pad_rot=pad_rot, net=p.get("2"), key=f"{kpref}:p2"))
    else:
        raise ValueError(f"Unknown footprint: {name}")

    lines.append('\t(embedded_fonts no)')
    if is_board_instance:
        lines.append("\t)")
        return "\n".join("\t" + ln if not ln.startswith("\t") else ln for ln in lines)
    lines.append(")")
    return "\n".join(lines) + "\n"


FP_DESCRS: dict[str, str] = {
    "MountingHole_3.2mm_M3_DIY": "M3 Mounting Hole 3.2mm NPTH (DIY)",
    "PinSocket_1x15_P2.54mm_DIY": "1x15 2.54mm Female Pin Socket (B.Cu oval pads, 1.1mm drill)",
    "PinHeader_1x02_P2.54mm_DIY": "1x02 2.54mm Male Pin Header (B.Cu oval pads, 1.1mm drill)",
    "PinHeader_1x03_P2.54mm_DIY": "1x03 2.54mm Male Pin Header (B.Cu oval pads, 1.1mm drill)",
    "TerminalBlock_MKDS_1x02_P5.08mm_DIY": "Phoenix MKDS 1,5/2-5,08 Screw Terminal (B.Cu pads, 1.3mm drill)",
    "R_Axial_P10.16mm_DIY": "1/4W Axial Resistor P10.16mm (B.Cu 2.6mm pads, 0.9mm drill)",
    "D_DO41_P10.16mm_DIY": "DO-41 Diode P10.16mm (B.Cu 2.6x3.4mm pads, 1.1mm drill)",
    "CP_Radial_D8.0mm_P3.50mm_DIY": "Electrolytic Cap D8.0mm P3.50mm (B.Cu 2.6x3.6mm pads, 0.9mm drill)",
    "CP_Radial_D5.0mm_P3.50mm_DIY": "Electrolytic Cap D5.0mm P3.50mm formed (B.Cu 2.6x3.4mm pads, 0.9mm drill)",
    "C_Disc_D5.0mm_P5.00mm_DIY": "Ceramic Disc Cap D5.0mm P5.00mm (B.Cu 2.6mm pads, 0.9mm drill)",
    "LED_D3.0mm_P5.08mm_DIY": "3mm LED formed P5.08mm (B.Cu 2.8mm pads, 0.9mm drill)",
    "TO-92_Wide_DIY": "TO-92 Wide Formed NPN BJT E-B-C (B.Cu 2.6mm round pads, 0.9mm drill)",
    "WireJumper_P7.62mm_DIY": "Top-side 22AWG Insulated Wire Jumper P7.62mm (B.Cu 2.8mm pads, 0.9mm drill)",
    "WireJumper_P12.70mm_DIY": "Top-side 22AWG Insulated Wire Jumper P12.70mm (B.Cu 2.8mm pads, 0.9mm drill)",
    "WireJumper_P17.78mm_DIY": "Top-side 22AWG Insulated Wire Jumper P17.78mm (B.Cu 2.8mm pads, 0.9mm drill)",
    "WireJumper_P20.32mm_DIY": "Top-side 22AWG Insulated Wire Jumper P20.32mm (B.Cu 2.8mm pads, 0.9mm drill)",
    "WireJumper_P25.40mm_DIY": "Top-side 22AWG Insulated Wire Jumper P25.40mm (B.Cu 2.8mm pads, 0.9mm drill)",
    "WireJumper_P35.56mm_DIY": "Top-side 22AWG Insulated Wire Jumper P35.56mm (B.Cu 2.8mm pads, 0.9mm drill)",
}


@dataclass
class ComponentSpec:
    ref: str
    value: str
    fp_name: str
    bx: float
    by: float
    rot: float
    pins: dict[str, str]
    jumper_pitch: float | None = None
    jumper_color: str = ""
    jumper_note: str = ""


def get_components() -> list[ComponentSpec]:
    """42 circuit parts (incl. Q1 S8050 + R10 1k buzzer driver) + 7 wire jumpers (JP1..JP7) = 49 footprints."""
    return [
        # --- 4 Fixed Corner M3 Mounting Holes (90 x 70 mm pattern, 5 mm edge inset) ---
        ComponentSpec("H1", "M3_3.2mm", "MountingHole_3.2mm_M3_DIY", 5.0, 75.0, 0.0, {}),
        ComponentSpec("H2", "M3_3.2mm", "MountingHole_3.2mm_M3_DIY", 95.0, 75.0, 0.0, {}),
        ComponentSpec("H3", "M3_3.2mm", "MountingHole_3.2mm_M3_DIY", 5.0, 5.0, 0.0, {}),
        ComponentSpec("H4", "M3_3.2mm", "MountingHole_3.2mm_M3_DIY", 95.0, 5.0, 0.0, {}),

        # --- NodeMCU v2 Amica Female Sockets (2x15 @ 2.54mm pitch, 22.86mm row spacing) ---
        ComponentSpec(
            "U1", "NodeMCU_Left_1x15", "PinSocket_1x15_P2.54mm_DIY", 37.00, 59.00, 0.0,
            {"1": "A0_SOIL", "10": "GND", "11": "+3V3", "14": "GND", "15": "+5V"},
        ),
        ComponentSpec(
            "U2", "NodeMCU_Right_1x15", "PinSocket_1x15_P2.54mm_DIY", 59.86, 59.00, 0.0,
            {
                "1": "D0_LED_LR", "2": "D1_SERVO", "3": "D2_DHT11", "4": "D3_AUDIO_PWM",
                "5": "D4_LED_BR", "6": "+3V3_R", "7": "GND", "8": "D5_MIC_DO",
                "9": "D6_RLY1_PUMP", "10": "D7_RLY2_AMP", "11": "D8_BUZZER",
                "14": "GND", "15": "+3V3_R",
            },
        ),

        # --- LEFT EDGE: Power Supply & Water Pump ---
        ComponentSpec("J2", "PUMP_OUT", "TerminalBlock_MKDS_1x02_P5.08mm_DIY", 9.0, 58.0, -90.0, {"1": "PUMP_5V", "2": "GND"}),
        ComponentSpec("D1", "1N4007", "D_DO41_P10.16mm_DIY", 16.5, 58.0, -90.0, {"1": "PUMP_5V", "2": "GND"}),
        ComponentSpec("J8", "RLY1_SW", "PinHeader_1x02_P2.54mm_DIY", 23.5, 55.46, 180.0, {"1": "+5V", "2": "PUMP_5V"}),
        ComponentSpec("J1", "PWR_5V_IN", "TerminalBlock_MKDS_1x02_P5.08mm_DIY", 9.0, 26.5, -90.0, {"1": "+5V", "2": "GND"}),
        ComponentSpec("C1", "470uF 16V", "CP_Radial_D8.0mm_P3.50mm_DIY", 23.5, 42.5, 180.0, {"1": "+5V", "2": "GND"}),
        ComponentSpec("C2", "470uF 16V", "CP_Radial_D8.0mm_P3.50mm_DIY", 23.5, 32.5, 180.0, {"1": "+5V", "2": "GND"}),
        ComponentSpec("C3", "100nF", "C_Disc_D5.0mm_P5.00mm_DIY", 29.0, 23.44, 90.0, {"1": "+5V", "2": "GND"}),
        ComponentSpec("R8", "1k", "R_Axial_P10.16mm_DIY", 22.0, 17.0, 180.0, {"1": "+5V", "2": "PWR_LED_A"}),
        ComponentSpec("D3", "LED_PWR_GRN", "LED_D3.0mm_P5.08mm_DIY", 7.5, 12.5, 0.0, {"1": "GND", "2": "PWR_LED_A"}),

        # --- TOP EDGE ---
        ComponentSpec("J14", "SOIL_A0", "PinHeader_1x03_P2.54mm_DIY", 16.5, 71.0, 90.0, {"1": "+3V3_SOIL", "2": "GND", "3": "A0_SOIL"}),
        ComponentSpec("C7", "100nF", "C_Disc_D5.0mm_P5.00mm_DIY", 26.5, 66.5, 0.0, {"1": "A0_SOIL", "2": "GND"}),
        ComponentSpec("J4", "LED_LR_D0", "PinHeader_1x02_P2.54mm_DIY", 40.5, 71.0, 90.0, {"1": "LED_LR_A", "2": "GND"}),
        ComponentSpec("R1", "220R", "R_Axial_P10.16mm_DIY", 54.0, 65.5, 180.0, {"1": "D0_LED_LR", "2": "LED_LR_A"}),
        ComponentSpec("J3", "SERVO_D1", "PinHeader_1x03_P2.54mm_DIY", 58.0, 71.0, 90.0, {"1": "D1_SERVO", "2": "+5V_SERVO", "3": "GND"}),
        ComponentSpec("J13", "DHT11_D2", "PinHeader_1x03_P2.54mm_DIY", 81.58, 72.5, -90.0, {"1": "+3V3_TOP", "2": "D2_DHT11", "3": "GND"}),
        ComponentSpec("R3", "10k", "R_Axial_P10.16mm_DIY", 76.0, 64.1, 180.0, {"1": "+3V3_TOP", "2": "D2_DHT11"}),

        # --- RIGHT EDGE ---
        ComponentSpec("J5", "LED_BR_D4", "PinHeader_1x02_P2.54mm_DIY", 91.0, 62.0, 0.0, {"1": "LED_BR_A", "2": "D4_LED_BR"}),
        ComponentSpec("R2", "220R", "R_Axial_P10.16mm_DIY", 76.0, 60.8, 0.0, {"1": "+3V3_TOP", "2": "LED_BR_A"}),
        ComponentSpec("R7", "10k", "R_Axial_P10.16mm_DIY", 76.0, 57.5, 0.0, {"1": "+3V3_TOP", "2": "D4_LED_BR"}),
        ComponentSpec("J15", "KY037_D5", "PinHeader_1x03_P2.54mm_DIY", 91.0, 47.0, 0.0, {"1": "+3V3_R", "2": "GND", "3": "D5_MIC_DO"}),
        ComponentSpec("J7", "RLY1_PUMP_D6", "PinHeader_1x03_P2.54mm_DIY", 91.0, 28.42, 180.0, {"1": "+5V_RLY1", "2": "GND", "3": "D6_RLY1_PUMP"}),
        ComponentSpec("J9", "RLY2_AMP_D7", "PinHeader_1x03_P2.54mm_DIY", 91.0, 15.42, 180.0, {"1": "+5V_RLY2", "2": "GND", "3": "D7_RLY2_AMP"}),

        # --- BOTTOM EDGE ---
        ComponentSpec("J10", "RLY2_SW", "PinHeader_1x02_P2.54mm_DIY", 16.5, 8.5, 90.0, {"1": "+5V", "2": "AMP_5V"}),
        ComponentSpec("J11", "PAM8403_PWR", "PinHeader_1x02_P2.54mm_DIY", 29.0, 8.5, 90.0, {"1": "AMP_5V", "2": "GND"}),
        ComponentSpec("C6", "100nF", "C_Disc_D5.0mm_P5.00mm_DIY", 33.5, 14.5, 0.0, {"1": "AMP_5V", "2": "GND"}),
        ComponentSpec("R4", "10k", "R_Axial_P10.16mm_DIY", 43.0, 51.38, 0.0, {"1": "+3V3", "2": "D3_AUDIO_PWM"}),
        ComponentSpec("C4", "10uF 16V", "CP_Radial_D5.0mm_P3.50mm_DIY", 43.5, 14.5, 0.0, {"1": "D3_AUDIO_PWM", "2": "AUD_AC"}),
        ComponentSpec("R5", "2.2k", "R_Axial_P10.16mm_DIY", 50.0, 16.5, 0.0, {"1": "AUD_AC", "2": "AUD_OUT"}),
        ComponentSpec("R6", "2.2k", "R_Axial_P10.16mm_DIY", 60.16, 12.8, 180.0, {"1": "AUD_OUT", "2": "GND"}),
        ComponentSpec("C5", "10nF", "C_Disc_D5.0mm_P5.00mm_DIY", 60.0, 8.5, 0.0, {"1": "AUD_OUT", "2": "GND"}),
        ComponentSpec("J12", "AUDIO_D3", "PinHeader_1x02_P2.54mm_DIY", 53.5, 8.5, 90.0, {"1": "AUD_OUT", "2": "GND"}),
        ComponentSpec("R9", "10k", "R_Axial_P10.16mm_DIY", 75.5, 30.2, 180.0, {"1": "D8_BUZZER", "2": "GND"}),
        ComponentSpec("R10", "1k", "R_Axial_P10.16mm_DIY", 75.5, 26.5, -90.0, {"1": "D8_BUZZER", "2": "BUZZ_BASE"}),
        ComponentSpec("Q1", "S8050", "TO-92_Wide_DIY", 69.0, 10.5, 0.0, {"1": "GND", "2": "BUZZ_BASE", "3": "BUZZ_K"}),
        ComponentSpec("D2", "1N4007", "D_DO41_P10.16mm_DIY", 80.5, 22.1, -90.0, {"1": "+5V_RLY2", "2": "BUZZ_K"}),
        ComponentSpec("J6", "BUZZ_D8", "PinHeader_1x02_P2.54mm_DIY", 85.0, 8.0, -90.0, {"1": "+5V_RLY2", "2": "BUZZ_K"}),

        # --- 7 MINIMAL TOP-SIDE WIRE JUMPERS (ALL on +3V3 / +5V rails, 0 on GND or signals!) ---
        ComponentSpec(
            "JP1", "JUMPER_12.70mm", "WireJumper_P12.70mm_DIY", 43.0, 46.30, 0.0,
            {"1": "+3V3", "2": "+3V3_R"}, jumper_pitch=12.70, jumper_color="Orange (+3.3V)",
            jumper_note="Bridges +3V3 from NodeMCU belly (U1.11/R4.1) across D3_AUDIO_PWM to +3V3 right bus (U2.6/U2.15/J15)",
        ),
        ComponentSpec(
            "JP2", "JUMPER_17.78mm", "WireJumper_P17.78mm_DIY", 40.5, 62.0, 180.0,
            {"1": "+3V3", "2": "+3V3_SOIL"}, jumper_pitch=17.78, jumper_color="Orange (+3.3V)",
            jumper_note="Bridges +3V3 from NodeMCU belly across A0_SOIL to J14.1 (SOIL_A0 +3.3V)",
        ),
        ComponentSpec(
            "JP3", "JUMPER_7.62mm", "WireJumper_P7.62mm_DIY", 76.0, 46.7, 90.0,
            {"1": "+3V3_R", "2": "+3V3_TOP"}, jumper_pitch=7.62, jumper_color="Orange (+3.3V)",
            jumper_note="Bridges +3V3 vertically across D4_LED_BR from U2.6/J15 bus up to R7/R2/R3/J13 pull-ups",
        ),
        ComponentSpec(
            "JP4", "JUMPER_35.56mm", "WireJumper_P35.56mm_DIY", 36.5, 20.0, 0.0,
            {"1": "+5V", "2": "+5V_RLY2"}, jumper_pitch=35.56, jumper_color="Red (+5V)",
            jumper_note="Bridges +5V from U1.15 across belly GND/D3/+3V3, U2.14 GND, and D8_BUZZER to right-side Relay 2 +5V bus",
        ),
        ComponentSpec(
            "JP5", "JUMPER_12.70mm", "WireJumper_P12.70mm_DIY", 85.5, 15.72, 90.0,
            {"1": "+5V_RLY2", "2": "+5V_RLY1"}, jumper_pitch=12.70, jumper_color="Red (+5V)",
            jumper_note="Bridges +5V vertically from J9.1 (Relay 2) across D7_RLY2_AMP to J7.1 (Relay 1)",
        ),
        ComponentSpec(
            "JP6", "JUMPER_20.32mm", "WireJumper_P20.32mm_DIY", 85.5, 33.0, 90.0,
            {"1": "+5V_RLY1", "2": "+5V_TOP"}, jumper_pitch=20.32, jumper_color="Red (+5V)",
            jumper_note="Bridges +5V vertically from Relay 1 across D6, D5, GND, +3V3_R, and D4 into open tunnel under R7 & R2",
        ),
        ComponentSpec(
            "JP7", "JUMPER_25.40mm", "WireJumper_P25.40mm_DIY", 85.5, 67.3, 180.0,
            {"1": "+5V_TOP", "2": "+5V_SERVO"}, jumper_pitch=25.40, jumper_color="Red (+5V)",
            jumper_note="Bridges +5V horizontally across +3V3_TOP and D2_DHT11 into J3.2 (SERVO_D1 +5V)",
        ),
    ]


def compute_pad_coords(comps: list[ComponentSpec]) -> dict[tuple[str, str], tuple[float, float, str]]:
    out: dict[tuple[str, str], tuple[float, float, str]] = {}
    for c in comps:
        if c.fp_name.startswith("PinSocket_1x15"):
            lps = [(str(i + 1), 0.0, i * 2.54) for i in range(15)]
        elif c.fp_name.startswith("PinHeader_1x02"):
            lps = [(str(i + 1), 0.0, i * 2.54) for i in range(2)]
        elif c.fp_name.startswith("PinHeader_1x03"):
            lps = [(str(i + 1), 0.0, i * 2.54) for i in range(3)]
        elif c.fp_name.startswith("TerminalBlock"):
            lps = [("1", 0.0, 0.0), ("2", 5.08, 0.0)]
        elif c.fp_name.startswith("R_Axial") or c.fp_name.startswith("D_DO41"):
            lps = [("1", 0.0, 0.0), ("2", 10.16, 0.0)]
        elif c.fp_name.startswith("CP_Radial"):
            lps = [("1", 0.0, 0.0), ("2", 3.50, 0.0)]
        elif c.fp_name.startswith("C_Disc"):
            lps = [("1", 0.0, 0.0), ("2", 5.00, 0.0)]
        elif c.fp_name.startswith("LED_D3"):
            lps = [("1", 0.0, 0.0), ("2", 5.08, 0.0)]
        elif c.fp_name.startswith("TO-92_Wide"):
            lps = [("1", 0.0, 0.0), ("2", 2.54, -2.54), ("3", 5.08, 0.0)]
        elif c.fp_name.startswith("WireJumper_P"):
            pitch = c.jumper_pitch or float(c.fp_name.split("_P")[1].split("mm")[0])
            lps = [("1", 0.0, 0.0), ("2", pitch, 0.0)]
        else:
            lps = []
        for pnum, dx, dyk in lps:
            dbx, dby = rot_local(dx, dyk, c.rot)
            out[(c.ref, pnum)] = (round(c.bx + dbx, 4), round(c.by + dby, 4), c.pins.get(pnum, ""))
    return out


def get_tracks(pm: dict[tuple[str, str], tuple[float, float, str]]) -> list[tuple[str, float, list[tuple[float, float]]]]:
    def P(ref: str, pin: str, dx: float = 0.0, dy: float = 0.0) -> tuple[float, float]:
        x, y = pm[(ref, pin)][0], pm[(ref, pin)][1]
        return round(x + dx, 4), round(y + dy, 4)

    W_PWR = 2.0
    W_SIG = 1.0
    OFF = 0.85  # Stay well inside 3.80mm oval pad (+/-1.90) while guaranteeing >= 1.06mm opposite-exit clearance

    return [
        # 1. GND PERIMETER RING + ALL 27 GND PADS (2.0 mm wide, 0 jumpers)
        ("GND", W_PWR, [
            (2.8, 12.0), (2.8, 67.5),
            (11.0, 71.0), (12.5, 77.2),
            (87.5, 77.2), (89.0, 71.0), (97.2, 67.5),
            (97.2, 12.5), (89.0, 9.0), (87.5, 2.8),
            (12.5, 2.8), (11.0, 9.0), (2.8, 12.0),
        ]),
        ("GND", W_PWR, [P("J14", "2", 0.0, +OFF), (P("J14", "2")[0], 77.2)]),
        ("GND", W_PWR, [P("J4", "2"), (P("J4", "2")[0], 77.2)]),
        ("GND", W_PWR, [P("J3", "3", 0.0, +OFF), (P("J3", "3")[0], 77.2)]),
        ("GND", W_PWR, [P("J13", "3"), (P("J13", "3")[0], 77.2)]),
        ("GND", W_PWR, [P("C7", "2"), (35.5, 66.5), (35.5, 77.2)]),
        ("GND", W_PWR, [P("U1", "10", -OFF, 0.0), (32.0, P("U1", "10")[1]), (32.0, 28.44), P("C3", "2")]),
        ("GND", W_PWR, [(32.0, 28.44), (32.0, P("U1", "14")[1]), P("U1", "14"), (40.5, P("U1", "14")[1]), (40.5, 19.0), (38.5, 17.0), P("C6", "2"), (38.5, 2.8)]),
        ("GND", W_PWR, [P("J15", "2", +OFF, 0.0), (97.2, P("J15", "2")[1])]),
        ("GND", W_PWR, [P("J7", "2", +OFF, 0.0), (97.2, P("J7", "2")[1])]),
        ("GND", W_PWR, [P("J9", "2", +OFF, 0.0), (97.2, P("J9", "2")[1])]),
        ("GND", W_PWR, [P("U2", "7", +0.90, -0.035), (62.5, 43.725), (64.0, 43.40), (86.5, 43.40), (88.0, P("J15", "2")[1]), P("J15", "2", -OFF, 0.0)]),
        ("GND", W_PWR, [P("J12", "2"), (P("J12", "2")[0], 2.8)]),
        ("GND", W_PWR, [P("J11", "2", 0.0, -OFF), (P("J11", "2")[0], 2.8)]),
        ("GND", W_PWR, [P("Q1", "1"), (P("Q1", "1")[0], 2.8)]),
        ("GND", W_PWR, [P("U2", "14", +OFF, 0.0), (65.0, P("U2", "14")[1]), P("R9", "2")]),
        ("GND", W_PWR, [(65.0, P("U2", "14")[1]), P("C5", "2"), (65.0, 2.8)]),
        ("GND", W_PWR, [P("R6", "2"), (50.0, 2.8)]),
        ("GND", W_PWR, [(2.8, P("J1", "2")[1]), P("J1", "2")]),
        ("GND", W_PWR, [(2.8, P("D3", "1")[1]), P("D3", "1")]),
        ("GND", W_PWR, [(2.8, P("J2", "2")[1]), P("J2", "2"), (16.5, 52.92), P("D1", "2"), (20.0, 47.84), P("C1", "2"), P("C2", "2")]),

        # 2. PUMP_5V & AMP_5V (2.0 mm wide, 0 jumpers)
        ("PUMP_5V", W_PWR, [P("J2", "1"), P("D1", "1"), P("J8", "2", -OFF, 0.0)]),
        ("AMP_5V", W_PWR, [P("J10", "2", +0.16, +OFF), (19.20, 13.5), (29.0, 13.5), P("J11", "1", 0.0, +OFF)]),
        ("AMP_5V", W_PWR, [(29.0, 13.5), (33.5, 13.5), P("C6", "1")]),

        # 3. ALL 15 SIGNAL NETS (1.0 mm wide, 0 jumpers)
        ("PWR_LED_A", W_SIG, [P("R8", "2"), P("D3", "2")]),
        ("A0_SOIL", W_SIG, [P("J14", "3"), (21.58, 67.5), (26.5, 66.5), P("C7", "1"), (26.5, 59.0), P("U1", "1")]),
        ("D0_LED_LR", W_SIG, [P("U2", "1"), (54.0, 59.0), P("R1", "1")]),
        ("LED_LR_A", W_SIG, [P("R1", "2"), (40.5, 65.5), P("J4", "1")]),
        ("D1_SERVO", W_SIG, [P("U2", "2"), (63.2, P("U2", "2")[1]), (63.2, 61.5), (57.2, 62.5), (57.2, 69.5), P("J3", "1")]),
        ("D2_DHT11", W_SIG, [P("U2", "3"), (65.84, P("U2", "3")[1]), P("R3", "2"), (65.84, 68.8), (79.04, 68.8), P("J13", "2")]),
        ("D3_AUDIO_PWM", W_SIG, [P("U2", "4"), P("R4", "2"), (47.0, 51.38), (47.0, 28.0), (43.5, 24.5), P("C4", "1")]),
        ("AUD_AC", W_SIG, [P("C4", "2"), (47.0, 16.5), P("R5", "1")]),
        ("AUD_OUT", W_SIG, [P("R5", "2"), P("R6", "1"), (60.0, 12.8), P("C5", "1")]),
        ("AUD_OUT", W_SIG, [P("R6", "1"), (53.5, 12.8), P("J12", "1")]),
        ("D4_LED_BR", W_SIG, [P("U2", "5"), (63.5, P("U2", "5")[1]), (65.0, 50.0), (88.5, 50.0), (88.5, 57.5), P("R7", "2")]),
        ("D4_LED_BR", W_SIG, [(88.5, 57.5), (88.5, 59.46), P("J5", "2")]),
        ("LED_BR_A", W_SIG, [P("R2", "2"), (86.16, 62.0), P("J5", "1")]),
        ("D5_MIC_DO", W_SIG, [P("U2", "8"), (87.5, P("U2", "8")[1]), (88.5, P("J15", "3")[1]), P("J15", "3")]),
        ("D6_RLY1_PUMP", W_SIG, [P("U2", "9"), (78.0, P("U2", "9")[1]), (81.5, 36.5), (88.5, 36.5), (89.5, P("J7", "3")[1]), P("J7", "3")]),
        ("D7_RLY2_AMP", W_SIG, [P("U2", "10"), (76.0, P("U2", "10")[1]), (82.6, 30.0), (82.6, 24.8), (88.5, 24.8), (88.5, 21.5), (89.5, P("J9", "3")[1]), P("J9", "3")]),
        ("D8_BUZZER", W_SIG, [P("U2", "11"), (75.5, P("U2", "11")[1]), P("R9", "1"), P("R10", "1")]),
        ("BUZZ_BASE", W_SIG, [P("R10", "2"), P("Q1", "2")]),
        ("BUZZ_K", W_SIG, [P("Q1", "3"), (78.5, P("Q1", "3")[1]), P("D2", "2")]),
        ("BUZZ_K", W_SIG, [(78.5, P("Q1", "3")[1]), (80.5, 8.0), P("J6", "2")]),

        # 4. +3V3 NETS (2.0 mm wide, bridged by JP1, JP2, JP3)
        ("+3V3", W_PWR, [P("U1", "11", +OFF, 0.0), (43.0, P("U1", "11")[1]), P("JP1", "1"), P("R4", "1"), (41.0, 55.0), (40.5, 60.5), P("JP2", "1")]),
        ("+3V3_SOIL", W_PWR, [P("JP2", "2"), (16.5, 62.0), P("J14", "1", 0.0, -OFF)]),
        ("+3V3_R", W_PWR, [P("U2", "15", -OFF, 0.0), (54.5, P("U2", "15")[1]), (54.5, 46.30), P("JP1", "2"), P("U2", "6", -OFF, 0.0)]),
        ("+3V3_R", W_PWR, [P("U2", "6", +0.90, +0.035), (62.5, 46.335), (64.0, 46.50), (76.0, 46.50), P("JP3", "1")]),
        ("+3V3_R", W_PWR, [P("JP3", "1"), (77.5, 47.16), P("J15", "1", -OFF, +0.16)]),
        ("+3V3_TOP", W_PWR, [P("JP3", "2"), P("R7", "1"), P("R2", "1"), P("R3", "1"), (76.0, 66.0), (81.58, 66.0), P("J13", "1")]),

        # 5. +5V NETS (2.0 mm wide, bridged by JP4, JP5, JP6, JP7)
        ("+5V", W_PWR, [P("J1", "1"), (23.5, 26.5), P("C2", "1"), P("C1", "1"), P("J8", "1", 0.0, -0.16)]),
        ("+5V", W_PWR, [(23.5, 26.5), (23.5, 23.44), P("C3", "1"), (29.0, 22.0), (36.5, 22.0), (37.0, 22.5), P("U1", "15", 0.0, -0.16)]),
        ("+5V", W_PWR, [(36.5, 22.0), P("JP4", "1")]),
        ("+5V", W_PWR, [(23.5, 23.44), (22.0, 21.0), P("R8", "1"), (16.34, 17.0), P("J10", "1", -0.16, +OFF)]),
        ("+5V_RLY2", W_PWR, [P("JP4", "2"), (75.5, 21.4), P("D2", "1"), (83.5, 21.8), (85.5, 19.8), P("JP5", "1"), (88.0, P("J9", "1")[1]), P("J9", "1", -OFF, 0.0)]),
        ("+5V_RLY2", W_PWR, [P("JP5", "1"), (85.5, 11.5), P("J6", "1", 0.0, +OFF)]),
        ("+5V_RLY1", W_PWR, [P("JP6", "1"), P("JP5", "2"), P("J7", "1", -OFF, 0.0)]),
        ("+5V_TOP", W_PWR, [P("JP6", "2"), (81.0, 54.5), (81.0, 62.5), (82.5, 62.5), (85.5, 64.2), P("JP7", "1")]),
        ("+5V_SERVO", W_PWR, [P("JP7", "2"), (60.54, 68.0), P("J3", "2", 0.0, -OFF)]),
    ]


# ---------------------------------------------------------------------------
# 3. Synchronize Schematic (`smarthome_hub.kicad_sch`), Project (`.kicad_pro`), BOM
# ---------------------------------------------------------------------------
PWR_SWAP_MAP: dict[str, str] = {
    "#PWR005": "+3V3_R",
    "#PWR008": "+3V3_R",
    "#PWR028": "+3V3_R",
    "#PWR022": "+3V3_TOP",
    "#PWR024": "+3V3_TOP",
    "#PWR033": "+3V3_TOP",
    "#PWR034": "+3V3_TOP",
    "#PWR025": "+3V3_SOIL",
    "#PWR043": "+5V_RLY2",
    "#PWR038": "+5V_RLY1",
    "#PWR030": "+5V_SERVO",
    "#PWR035": "BUZZ_K",
    "#PWR037": "BUZZ_K",
}

BASE_SCH_COMMIT = "131bdc2"
KICAD_BJT_SYM_LIB = pathlib.Path(
    r"C:\Users\LENOVO\AppData\Local\Programs\KiCad\10.0\share\kicad\symbols\Transistor_BJT.kicad_sym"
)


def _extract_lib_symbol(lib_path: pathlib.Path, sym_name: str, lib_prefix: str) -> str:
    txt = lib_path.read_text(encoding="utf-8")
    marker = f'\t(symbol "{sym_name}"'
    start = txt.index(marker)
    depth = 0
    i = start + 1
    while i < len(txt):
        ch = txt[i]
        if ch == '"':
            i += 1
            while i < len(txt) and txt[i] != '"':
                if txt[i] == "\\":
                    i += 1
                i += 1
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    blk = txt[start:end].replace(f'(symbol "{sym_name}"', f'(symbol "{lib_prefix}:{sym_name}"', 1)
    return "\n" + "\n".join("\t" + ln for ln in blk.splitlines())


def sync_schematic(comps: list[ComponentSpec]) -> tuple[dict[str, str], dict[str, str], dict[tuple[str, str], str]]:
    """Update smarthome_hub.kicad_sch from clean pre-DIY base commit so re-runs are 100% idempotent.

    Returns:
      - sch_paths: {ref: schematic_symbol_path}
      - sch_descrs: {ref: schematic_Description_field}
      - sch_pad_nets: {(ref, pin): exact_kicad_schematic_net_name} (from kicad-cli sch export netlist)
    """
    # Always start from clean pre-DIY git base schematic so repeated runs are 100% idempotent!
    raw = subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), "show", f"{BASE_SCH_COMMIT}:hardware/kicad/smarthome_hub/smarthome_hub.kicad_sch"],
    ).decode("utf-8")

    # Update title block revision/date
    raw = raw.replace(
        '(title "SmartHome Hub PCB (Type 1 - ESP8266 NodeMCU v2)")',
        '(title "SmartHome Hub DIY Single-Layer PCB v3.0 (100x80mm, B.Cu Only)")',
    )
    raw = raw.replace('(date "2026-11-20")', '(date "2026-11-21")')
    raw = raw.replace('(rev "2.0")', '(rev "3.0-DIY")')

    # Rewire J6.1 & D2.1 from D8_BUZZER to +5V_RLY2 (low-side NPN driver puts buzzer & flyback across +5V_RLY2 <-> BUZZ_K)
    raw = raw.replace(
        '(label "D8_BUZZER" (at 365.7600 48.2600 180)',
        '(label "+5V_RLY2" (at 365.7600 48.2600 180)',
        1,
    )
    raw = raw.replace(
        '(label "D8_BUZZER" (at 370.8400 63.5000 0)',
        '(label "+5V_RLY2" (at 370.8400 63.5000 0)',
        1,
    )
    raw = raw.replace(
        '(property "Description" "5V Alarm Buzzer Header (D8 Active-HIGH)"',
        '(property "Description" "5V Alarm Buzzer Header (+5V / Q1 S8050 Low-Side NPN Collector)"',
        1,
    )
    raw = raw.replace(
        '(text "Safe Boot: 10k pull-down -> GPIO15 LOW (silent)"',
        '(text "Low-Side NPN Driver (Q1 S8050 + R10 1k) + R9 10k Boot Pull-Down + D2 1N4007"',
        1,
    )

    fp_by_ref = {c.ref: f"DIY_Hub:{c.fp_name}" for c in comps}
    sch_paths: dict[str, str] = {}
    sch_descrs: dict[str, str] = {}

    # Find exact end of `(lib_symbols ...)` so ALL schematic symbols (including U1!) are processed
    ls_start = raw.index("\n\t(lib_symbols")
    depth = 0
    i = ls_start + 2
    while i < len(raw):
        ch = raw[i]
        if ch == '"':
            i += 1
            while i < len(raw) and raw[i] != '"':
                if raw[i] == "\\":
                    i += 1
                i += 1
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                idx_body = i + 1
                break
        i += 1
    # Embed Transistor_BJT:Q_NPN_EBC into (lib_symbols ...) for zero ERC lib_symbol_issues
    bjt_lib_sym = _extract_lib_symbol(KICAD_BJT_SYM_LIB, "Q_NPN_EBC", "Transistor_BJT")
    head = raw[:idx_body - 1] + bjt_lib_sym + "\n\t)"
    body = raw[idx_body:]

    # Parse balanced S-expr blocks of `(symbol (lib_id ...` in body
    out_parts: list[str] = []
    pos = 0
    while True:
        m = re.search(r'\n\t\(symbol \(lib_id "', body[pos:])
        if not m:
            out_parts.append(body[pos:])
            break
        start = pos + m.start()
        out_parts.append(body[pos:start])
        # Find matching closing paren
        depth = 0
        i = start + 2  # at '('
        while i < len(body):
            ch = body[i]
            if ch == '"':
                i += 1
                while i < len(body) and body[i] != '"':
                    if body[i] == "\\":
                        i += 1
                    i += 1
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
            i += 1
        block = body[start:end]
        ref_m = re.search(r'\(property "Reference" "([^"]+)"', block)
        ref = ref_m.group(1) if ref_m else ""
        uuid_m = re.search(r'\n\t\t\(uuid "([^"]+)"\)', block)
        sym_uuid = uuid_m.group(1) if uuid_m else ""
        desc_m = re.search(r'\(property "Description" "([^"]*)"', block)

        if ref in PWR_SWAP_MAP:
            # Replace power symbol with exact local net label at its (at x y rot) pin point!
            at_m = re.search(r'\(at ([\d.\-]+) ([\d.\-]+) ([\d.\-]+)\)', block)
            lx, ly = at_m.group(1), at_m.group(2)
            net_lbl = PWR_SWAP_MAP[ref]
            lbl_block = (
                f'\n\t(label "{net_lbl}" (at {lx} {ly} 0)\n'
                f'\t\t(effects (font (size 1.27 1.27)) (justify left bottom))\n'
                f'\t\t(uuid "{duuid(f"sch_lbl:{ref}:{net_lbl}")}")\n'
                f'\t)'
            )
            out_parts.append(lbl_block)
        else:
            if ref in fp_by_ref:
                block = re.sub(
                    r'(\(property "Footprint" )"[^"]*"',
                    rf'\1"{fp_by_ref[ref]}"',
                    block,
                    count=1,
                )
                if sym_uuid:
                    sch_paths[ref] = f"/{ROOT_SHEET_UUID}/{sym_uuid}"
                if desc_m:
                    sch_descrs[ref] = desc_m.group(1)
            out_parts.append(block)
        pos = end

    new_body = "".join(out_parts)

    # Add the 7 real wire jumper symbols (JP1..JP7) cleanly in lower-right open area (x=312..398, y=252..276)
    jumpers = [c for c in comps if c.ref.startswith("JP")]
    jp_blocks: list[str] = [
        f'\n\t(text "Single-Layer B.Cu Top-Side Wire Jumpers (JP1-JP7, 22AWG)" (exclude_from_sim no) (at 304.80 247.65 0)\n'
        f'\t\t(effects (font (size 1.27 1.27) (bold yes)) (justify left))\n'
        f'\t\t(uuid "{duuid("sch:jp_title")}")\n'
        f'\t)'
    ]
    pwr_idx = 90
    for idx_j, jp in enumerate(jumpers):
        col = idx_j % 4
        row = idx_j // 4
        sx = 317.50 + col * 25.40
        sy = 256.54 + row * 15.24
        sym_u = duuid(f"sch:sym:{jp.ref}")
        sch_paths[jp.ref] = f"/{ROOT_SHEET_UUID}/{sym_u}"
        sch_descrs[jp.ref] = jp.jumper_note
        n1, n2 = jp.pins["1"], jp.pins["2"]

        jp_blocks.append(
            f'\n\t(symbol (lib_id "Connector_Generic:Conn_01x02") (at {sx:.4f} {sy:.4f} 0) (unit 1)\n'
            f'\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n'
            f'\t\t(uuid "{sym_u}")\n'
            f'\t\t(property "Reference" "{jp.ref}" (at {sx + 2.54:.4f} {sy - 2.54:.4f} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)))\n'
            f'\t\t)\n'
            f'\t\t(property "Value" "{jp.value}" (at {sx + 2.54:.4f} {sy + 2.54:.4f} 0)\n'
            f'\t\t\t(effects (font (size 1.00 1.00)))\n'
            f'\t\t)\n'
            f'\t\t(property "Footprint" "DIY_Hub:{jp.fp_name}" (at {sx:.4f} {sy:.4f} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
            f'\t\t)\n'
            f'\t\t(property "Datasheet" "" (at {sx:.4f} {sy:.4f} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
            f'\t\t)\n'
            f'\t\t(property "Description" "{jp.jumper_note}" (at {sx:.4f} {sy:.4f} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
            f'\t\t)\n'
            f'\t\t(pin "1" (uuid "{duuid(f"sch:pin:{jp.ref}:1")}"))\n'
            f'\t\t(pin "2" (uuid "{duuid(f"sch:pin:{jp.ref}:2")}"))\n'
            f'\t\t(instances\n'
            f'\t\t\t(project "smarthome_hub"\n'
            f'\t\t\t\t(path "/{ROOT_SHEET_UUID}" (reference "{jp.ref}") (unit 1))\n'
            f'\t\t\t)\n'
            f'\t\t)\n'
            f'\t)'
        )
        # Connect Pin 1 at (sx - 5.08, sy) and Pin 2 at (sx - 5.08, sy + 2.54)
        for p_idx, (net_n, py) in enumerate([(n1, sy), (n2, sy + 2.54)], start=1):
            px_pin = sx - 5.08
            px_end = sx - 10.16
            jp_blocks.append(
                f'\n\t(wire (pts (xy {px_pin:.4f} {py:.4f}) (xy {px_end:.4f} {py:.4f}))\n'
                f'\t\t(stroke (width 0) (type default))\n'
                f'\t\t(uuid "{duuid(f"sch:w:{jp.ref}:{p_idx}")}")\n'
                f'\t)'
            )
            if net_n in ("+5V", "+3V3"):
                pwr_idx += 1
                pref = f"#PWR{pwr_idx:03d}"
                jp_blocks.append(
                    f'\n\t(symbol (lib_id "power:{net_n}") (at {px_end:.4f} {py:.4f} 90) (unit 1)\n'
                    f'\t\t(exclude_from_sim no) (in_bom no) (on_board no) (dnp no)\n'
                    f'\t\t(uuid "{duuid(f"sch:pwr:{pref}")}")\n'
                    f'\t\t(property "Reference" "{pref}" (at {px_end:.4f} {py - 2.54:.4f} 0)\n'
                    f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
                    f'\t\t)\n'
                    f'\t\t(property "Value" "{net_n}" (at {px_end - 2.54:.4f} {py:.4f} 0)\n'
                    f'\t\t\t(effects (font (size 1.00 1.00)))\n'
                    f'\t\t)\n'
                    f'\t\t(property "Footprint" "" (at {px_end:.4f} {py:.4f} 0)\n'
                    f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
                    f'\t\t)\n'
                    f'\t\t(property "Datasheet" "" (at {px_end:.4f} {py:.4f} 0)\n'
                    f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
                    f'\t\t)\n'
                    f'\t\t(property "Description" "" (at {px_end:.4f} {py:.4f} 0)\n'
                    f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
                    f'\t\t)\n'
                    f'\t\t(pin "1" (uuid "{duuid(f"sch:pwrpin:{pref}")}"))\n'
                    f'\t\t(instances\n'
                    f'\t\t\t(project "smarthome_hub"\n'
                    f'\t\t\t\t(path "/{ROOT_SHEET_UUID}" (reference "{pref}") (unit 1))\n'
                    f'\t\t\t)\n'
                    f'\t\t)\n'
                    f'\t)'
                )
            else:
                jp_blocks.append(
                    f'\n\t(label "{net_n}" (at {px_end:.4f} {py:.4f} 0)\n'
                    f'\t\t(effects (font (size 1.00 1.00)) (justify right bottom))\n'
                    f'\t\t(uuid "{duuid(f"sch:jplbl:{jp.ref}:{p_idx}")}")\n'
                    f'\t)'
                )

    # Add R10 (1k base resistor) & Q1 (S8050 NPN low-side buzzer driver) cleanly inside Box 4
    r10_u = duuid("sch:sym:R10")
    q1_u = duuid("sch:sym:Q1")
    sch_paths["R10"] = f"/{ROOT_SHEET_UUID}/{r10_u}"
    sch_descrs["R10"] = "Base Current-Limiting Resistor for Q1 Buzzer NPN Driver"
    sch_paths["Q1"] = f"/{ROOT_SHEET_UUID}/{q1_u}"
    sch_descrs["Q1"] = "Low-Side NPN Transistor Buzzer Driver (S8050 / 2N2222A, E-B-C, TO-92)"

    buzzer_drv_blocks: list[str] = [
        # R10 horizontal at (340.36, 48.26, rot=90): Pin 1 at (336.55, 48.26), Pin 2 at (344.17, 48.26)
        f'\n\t(symbol (lib_id "Device:R") (at 340.3600 48.2600 90) (unit 1)\n'
        f'\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n'
        f'\t\t(uuid "{r10_u}")\n'
        f'\t\t(property "Reference" "R10" (at 340.3600 44.4500 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)))\n'
        f'\t\t)\n'
        f'\t\t(property "Value" "1k" (at 340.3600 52.0700 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)))\n'
        f'\t\t)\n'
        f'\t\t(property "Footprint" "DIY_Hub:R_Axial_P10.16mm_DIY" (at 340.3600 48.2600 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
        f'\t\t)\n'
        f'\t\t(property "Datasheet" "" (at 340.3600 48.2600 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
        f'\t\t)\n'
        f'\t\t(property "Description" "{sch_descrs["R10"]}" (at 340.3600 48.2600 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
        f'\t\t)\n'
        f'\t\t(pin "1" (uuid "{duuid("sch:pin:R10:1")}"))\n'
        f'\t\t(pin "2" (uuid "{duuid("sch:pin:R10:2")}"))\n'
        f'\t\t(instances\n'
        f'\t\t\t(project "smarthome_hub"\n'
        f'\t\t\t\t(path "/{ROOT_SHEET_UUID}" (reference "R10") (unit 1))\n'
        f'\t\t\t)\n'
        f'\t\t)\n'
        f'\t)',
        f'\n\t(wire (pts (xy 336.5500 48.2600) (xy 332.7400 48.2600))\n'
        f'\t\t(stroke (width 0) (type default))\n'
        f'\t\t(uuid "{duuid("sch:w:R10:1")}")\n'
        f'\t)',
        f'\n\t(label "D8_BUZZER" (at 332.7400 48.2600 180)\n'
        f'\t\t(effects (font (size 1.27 1.27)) (justify right bottom))\n'
        f'\t\t(uuid "{duuid("sch:lbl:R10:D8")}")\n'
        f'\t)',
        f'\n\t(wire (pts (xy 344.1700 48.2600) (xy 350.5200 48.2600))\n'
        f'\t\t(stroke (width 0) (type default))\n'
        f'\t\t(uuid "{duuid("sch:w:R10:2")}")\n'
        f'\t)',
        f'\n\t(label "BUZZ_BASE" (at 347.9800 48.2600 0)\n'
        f'\t\t(effects (font (size 1.00 1.00)) (justify left bottom))\n'
        f'\t\t(uuid "{duuid("sch:lbl:Q1:BASE")}")\n'
        f'\t)',
        # Q1 S8050 at (355.60, 48.26, rot=0): Pin 1(E)=(358.14, 53.34), Pin 2(B)=(350.52, 48.26), Pin 3(C)=(358.14, 43.18)
        f'\n\t(symbol (lib_id "Transistor_BJT:Q_NPN_EBC") (at 355.6000 48.2600 0) (unit 1)\n'
        f'\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n'
        f'\t\t(uuid "{q1_u}")\n'
        f'\t\t(property "Reference" "Q1" (at 360.6800 46.9900 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (justify left))\n'
        f'\t\t)\n'
        f'\t\t(property "Value" "S8050" (at 360.6800 49.5300 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (justify left))\n'
        f'\t\t)\n'
        f'\t\t(property "Footprint" "DIY_Hub:TO-92_Wide_DIY" (at 355.6000 48.2600 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
        f'\t\t)\n'
        f'\t\t(property "Datasheet" "" (at 355.6000 48.2600 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
        f'\t\t)\n'
        f'\t\t(property "Description" "{sch_descrs["Q1"]}" (at 355.6000 48.2600 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
        f'\t\t)\n'
        f'\t\t(pin "1" (uuid "{duuid("sch:pin:Q1:1")}"))\n'
        f'\t\t(pin "2" (uuid "{duuid("sch:pin:Q1:2")}"))\n'
        f'\t\t(pin "3" (uuid "{duuid("sch:pin:Q1:3")}"))\n'
        f'\t\t(instances\n'
        f'\t\t\t(project "smarthome_hub"\n'
        f'\t\t\t\t(path "/{ROOT_SHEET_UUID}" (reference "Q1") (unit 1))\n'
        f'\t\t\t)\n'
        f'\t\t)\n'
        f'\t)',
        f'\n\t(wire (pts (xy 358.1400 43.1800) (xy 358.1400 40.6400))\n'
        f'\t\t(stroke (width 0) (type default))\n'
        f'\t\t(uuid "{duuid("sch:w:Q1:C")}")\n'
        f'\t)',
        f'\n\t(label "BUZZ_K" (at 358.1400 40.6400 0)\n'
        f'\t\t(effects (font (size 1.27 1.27)) (justify left bottom))\n'
        f'\t\t(uuid "{duuid("sch:lbl:Q1:C")}")\n'
        f'\t)',
        f'\n\t(wire (pts (xy 358.1400 53.3400) (xy 358.1400 55.8800))\n'
        f'\t\t(stroke (width 0) (type default))\n'
        f'\t\t(uuid "{duuid("sch:w:Q1:E")}")\n'
        f'\t)',
        f'\n\t(symbol (lib_id "power:GND") (at 358.1400 55.8800 0) (unit 1)\n'
        f'\t\t(exclude_from_sim no) (in_bom no) (on_board no) (dnp no)\n'
        f'\t\t(uuid "{duuid("sch:pwr:#PWR098")}")\n'
        f'\t\t(property "Reference" "#PWR098" (at 358.1400 61.9760 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
        f'\t\t)\n'
        f'\t\t(property "Value" "GND" (at 358.1400 59.6900 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)))\n'
        f'\t\t)\n'
        f'\t\t(property "Footprint" "" (at 358.1400 55.8800 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
        f'\t\t)\n'
        f'\t\t(property "Datasheet" "" (at 358.1400 55.8800 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
        f'\t\t)\n'
        f'\t\t(property "Description" "" (at 358.1400 55.8800 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
        f'\t\t)\n'
        f'\t\t(pin "1" (uuid "{duuid("sch:pwrpin:#PWR098")}"))\n'
        f'\t\t(instances\n'
        f'\t\t\t(project "smarthome_hub"\n'
        f'\t\t\t\t(path "/{ROOT_SHEET_UUID}" (reference "#PWR098") (unit 1))\n'
        f'\t\t\t)\n'
        f'\t\t)\n'
        f'\t)',
    ]

    # Insert buzzer driver & jumper blocks right before `(sheet_instances`
    ins = new_body.rindex("\n\t(sheet_instances")
    final_sch = head + new_body[:ins] + "".join(buzzer_drv_blocks) + "".join(jp_blocks) + new_body[ins:]
    sch_path = KICAD_DIR / "smarthome_hub.kicad_sch"
    sch_path.write_text(final_sch, encoding="utf-8")

    # Export exact KiCad netlist from the synchronized schematic for 100% --schematic-parity match
    net_file = KICAD_DIR / "smarthome_hub.net"
    subprocess.run(
        [KCLI, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(net_file), str(sch_path)],
        check=True, capture_output=True, text=True,
    )
    net_txt = net_file.read_text(encoding="utf-8")
    sch_pad_nets: dict[tuple[str, str], str] = {}
    pos_n = 0
    while True:
        m = re.search(r'\(net\s+\(code\s+"[^"]*"\)\s+\(name\s+"([^"]+)"\)', net_txt[pos_n:])
        if not m:
            break
        net_name = m.group(1)
        start_n = pos_n + m.start()
        depth_n = 0
        j = start_n
        end_n = len(net_txt)
        while j < len(net_txt):
            ch = net_txt[j]
            if ch == '"':
                j += 1
                while j < len(net_txt) and net_txt[j] != '"':
                    if net_txt[j] == "\\":
                        j += 1
                    j += 1
            elif ch == "(":
                depth_n += 1
            elif ch == ")":
                depth_n -= 1
                if depth_n == 0:
                    end_n = j + 1
                    break
            j += 1
        block_n = net_txt[start_n:end_n]
        for nm in re.finditer(r'\(node\s+\(ref\s+"([^"]+)"\)\s+\(pin\s+"([^"]+)"\)', block_n):
            sch_pad_nets[(nm.group(1), nm.group(2))] = net_name
        pos_n = end_n
    net_file.unlink(missing_ok=True)
    return sch_paths, sch_descrs, sch_pad_nets


def update_kicad_pro(power_net_names: list[str]) -> None:
    """Persist DIY design rules & Power/Default netclasses in smarthome_hub.kicad_pro."""
    pro_path = KICAD_DIR / "smarthome_hub.kicad_pro"
    data = json.loads(pro_path.read_text(encoding="utf-8"))
    rules = data["board"]["design_settings"]["rules"]
    rules["min_clearance"] = 0.6
    rules["min_copper_edge_clearance"] = 0.6
    rules["min_track_width"] = 1.0
    rules["min_through_hole_diameter"] = 0.9
    rules["min_text_height"] = 1.5
    rules["min_text_thickness"] = 0.25
    rules["min_silk_clearance"] = 0.1

    defs = data["board"]["design_settings"]["defaults"]
    defs["silk_text_size_h"] = 1.5
    defs["silk_text_size_v"] = 1.5
    defs["silk_text_thickness"] = 0.25
    defs["silk_line_width"] = 0.25

    data["net_settings"]["classes"] = [
        {
            "bus_width": 12,
            "clearance": 0.6,
            "diff_pair_gap": 0.6,
            "diff_pair_via_gap": 0.6,
            "diff_pair_width": 1.0,
            "line_style": 0,
            "microvia_diameter": 0.6,
            "microvia_drill": 0.3,
            "name": "Default",
            "pcb_color": "rgba(0, 0, 0, 0.000)",
            "priority": 2147483647,
            "schematic_color": "rgba(0, 0, 0, 0.000)",
            "track_width": 1.0,
            "tuning_profile": "",
            "via_diameter": 1.8,
            "via_drill": 0.9,
            "wire_width": 6,
        },
        {
            "bus_width": 12,
            "clearance": 0.6,
            "diff_pair_gap": 0.6,
            "diff_pair_via_gap": 0.6,
            "diff_pair_width": 2.0,
            "line_style": 0,
            "microvia_diameter": 0.6,
            "microvia_drill": 0.3,
            "name": "Power",
            "pcb_color": "rgba(220, 38, 38, 0.800)",
            "priority": 1,
            "schematic_color": "rgba(220, 38, 38, 0.800)",
            "track_width": 2.0,
            "tuning_profile": "",
            "via_diameter": 2.4,
            "via_drill": 1.1,
            "wire_width": 10,
        },
    ]
    data["net_settings"]["netclass_assignments"] = {n: ["Power"] for n in power_net_names}
    pro_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_bom(comps: list[ComponentSpec]) -> None:
    """Regenerate hardware/kicad/smarthome_hub/bom.csv synchronized with schematic & PCB."""
    bom_path = KICAD_DIR / "bom.csv"
    with bom_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["Refs", "Value", "Footprint", "Qty", "DNP"])
        for c in sorted(comps, key=lambda x: (re.sub(r"\d+", "", x.ref), int(re.search(r"\d+", x.ref).group()))):
            w.writerow([c.ref, c.value, f"DIY_Hub:{c.fp_name}", "1", ""])


def write_footprint_library(comps: list[ComponentSpec]) -> None:
    FP_LIB_DIR.mkdir(parents=True, exist_ok=True)
    for old in FP_LIB_DIR.glob("*.kicad_mod"):
        old.unlink()
    written: set[str] = set()
    for c in comps:
        if c.fp_name in written:
            continue
        written.add(c.fp_name)
        mod_text = build_footprint_body(
            c.fp_name, FP_DESCRS[c.fp_name], is_board_instance=False, jumper_pitch=c.jumper_pitch
        )
        (FP_LIB_DIR / f"{c.fp_name}.kicad_mod").write_text(mod_text, encoding="utf-8")


def write_fp_lib_table() -> None:
    txt = """(fp_lib_table
\t(version 7)
\t(lib (name "DIY_Hub") (type "KiCad") (uri "${KIPRJMOD}/DIY_Hub.pretty") (options "") (descr "Single-layer DIY home-etch oversized-pad footprints"))
\t(lib (name "Capacitor_THT") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Capacitor_THT.pretty") (options "") (descr ""))
\t(lib (name "Connector_PinHeader_2.54mm") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Connector_PinHeader_2.54mm.pretty") (options "") (descr ""))
\t(lib (name "Connector_PinSocket_2.54mm") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Connector_PinSocket_2.54mm.pretty") (options "") (descr ""))
\t(lib (name "Diode_THT") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Diode_THT.pretty") (options "") (descr ""))
\t(lib (name "LED_THT") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/LED_THT.pretty") (options "") (descr ""))
\t(lib (name "MountingHole") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/MountingHole.pretty") (options "") (descr ""))
\t(lib (name "Resistor_THT") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Resistor_THT.pretty") (options "") (descr ""))
\t(lib (name "TerminalBlock_Phoenix") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/TerminalBlock_Phoenix.pretty") (options "") (descr ""))
)
"""
    (KICAD_DIR / "fp-lib-table").write_text(txt, encoding="utf-8")
    sym_tbl = KICAD_DIR / "sym-lib-table"
    if sym_tbl.exists():
        stxt = sym_tbl.read_text(encoding="utf-8")
        if '(name "Transistor_BJT")' not in stxt:
            entry = '\t(lib (name "Transistor_BJT") (type "KiCad") (uri "${KICAD10_SYMBOL_DIR}/Transistor_BJT.kicad_sym") (options "") (descr ""))'
            stxt = stxt[:stxt.rfind(")")].rstrip() + "\n" + entry + "\n)\n"
            sym_tbl.write_text(stxt, encoding="utf-8")


def write_dru(power_net_names: list[str]) -> None:
    pwr_cond = " || ".join(f"A.NetName == '{n}'" for n in power_net_names)
    dru = f"""(version 1)

# =============================================================================
# DIY Single-Layer Toner-Transfer & Hand-Drilling Design Rules (smarthome_hub)
# =============================================================================

(rule "DIY_No_Vias"
  (constraint disallow via)
)

(rule "DIY_No_Front_Copper_Tracks_Zones_Graphics"
  (layer "F.Cu")
  (constraint disallow track zone graphic)
)

(rule "DIY_No_Front_SMD_Pads"
  (layer "F.Cu")
  (condition "A.Type == 'Pad' && A.Pad_Type == 'SMD'")
  (constraint disallow pad)
)

(rule "DIY_Min_Copper_Clearance"
  (constraint clearance (min 0.6mm))
)

(rule "DIY_Min_Copper_Edge_Clearance"
  (constraint edge_clearance (min 0.6mm))
)

(rule "DIY_Min_Signal_Track_Width"
  (constraint track_width (min 1.0mm))
)

(rule "DIY_Min_Power_GND_Track_Width"
  (condition "{pwr_cond}")
  (constraint track_width (min 2.0mm))
)

# Global minimum annular ring >= 0.6 mm (satisfied on ALL round, diode, cap, terminal, jumper pads)
(rule "DIY_Min_Annular_Ring_Global"
  (constraint annular_width (min 0.6mm))
)

# Euclidean bound on 2.54mm-pitch headers/sockets (U1, U2, J3..J15):
# Along 2.54mm pitch, drill(1.10mm) + clearance(0.60mm) leaves 0.84mm total (0.42mm max/side).
# We preserve FULL >= 0.60mm clearance (actual 0.74mm!) and use 3.80 x 1.80 mm oval pads
# (transverse annular ring = 1.35 mm >> 0.60 mm; longitudinal ring = 0.35 mm).
(rule "DIY_Header_254mm_Oval_Annular_Ring"
  (priority 10)
  (condition "A.Reference == 'U1' || A.Reference == 'U2' || A.Reference == 'J3' || A.Reference == 'J4' || A.Reference == 'J5' || A.Reference == 'J6' || A.Reference == 'J7' || A.Reference == 'J8' || A.Reference == 'J9' || A.Reference == 'J10' || A.Reference == 'J11' || A.Reference == 'J12' || A.Reference == 'J13' || A.Reference == 'J14' || A.Reference == 'J15'")
  (constraint annular_width (min 0.35mm))
)

# Strictly enforce at most 4 drill classes total: 0.9mm, 1.1mm, 1.3mm, and 3.2mm (M3 mounting)
(rule "DIY_Strict_Four_Drill_Classes_Only"
  (condition "A.Type == 'Pad' && A.Hole_Size_X > 0mm && A.Hole_Size_X != 0.9mm && A.Hole_Size_X != 1.1mm && A.Hole_Size_X != 1.3mm && A.Hole_Size_X != 3.2mm")
  (constraint disallow pad)
)
"""
    (KICAD_DIR / "smarthome_hub.kicad_dru").write_text(dru, encoding="utf-8")


def build_edge_cuts() -> list[str]:
    x0, y0 = BX0, BY0
    x1, y1 = BX0 + BOARD_W, BY0 + BOARD_H
    r = CORNER_R
    d = r * (1.0 - math.sqrt(0.5))
    return [
        f'\t(gr_line (start {fmt(x0 + r)} {fmt(y0)}) (end {fmt(x1 - r)} {fmt(y0)}) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts") (uuid "{duuid("ec:top")}"))',
        f'\t(gr_line (start {fmt(x1)} {fmt(y0 + r)}) (end {fmt(x1)} {fmt(y1 - r)}) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts") (uuid "{duuid("ec:right")}"))',
        f'\t(gr_line (start {fmt(x1 - r)} {fmt(y1)}) (end {fmt(x0 + r)} {fmt(y1)}) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts") (uuid "{duuid("ec:bot")}"))',
        f'\t(gr_line (start {fmt(x0)} {fmt(y1 - r)}) (end {fmt(x0)} {fmt(y0 + r)}) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts") (uuid "{duuid("ec:left")}"))',
        f'\t(gr_arc (start {fmt(x0)} {fmt(y0 + r)}) (mid {fmt(x0 + d)} {fmt(y0 + d)}) (end {fmt(x0 + r)} {fmt(y0)}) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts") (uuid "{duuid("ec:tl")}"))',
        f'\t(gr_arc (start {fmt(x1 - r)} {fmt(y0)}) (mid {fmt(x1 - d)} {fmt(y0 + d)}) (end {fmt(x1)} {fmt(y0 + r)}) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts") (uuid "{duuid("ec:tr")}"))',
        f'\t(gr_arc (start {fmt(x1)} {fmt(y1 - r)}) (mid {fmt(x1 - d)} {fmt(y1 - d)}) (end {fmt(x1 - r)} {fmt(y1)}) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts") (uuid "{duuid("ec:br")}"))',
        f'\t(gr_arc (start {fmt(x0 + r)} {fmt(y1)}) (mid {fmt(x0 + d)} {fmt(y1 - d)}) (end {fmt(x0)} {fmt(y1 - r)}) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts") (uuid "{duuid("ec:bl")}"))',
    ]


def build_scale_bar() -> list[str]:
    sx0 = BX0 + 25.0
    sx1 = BX0 + 75.0
    sy = BY_BOT + 12.0
    items = [
        f'\t(gr_line (start {fmt(sx0)} {fmt(sy)}) (end {fmt(sx1)} {fmt(sy)}) (stroke (width 0.35) (type solid)) (layer "Dwgs.User") (uuid "{duuid("sb:main")}"))',
    ]
    for mm in (0, 10, 20, 30, 40, 50):
        tx = sx0 + mm
        th = 3.0 if mm in (0, 50) else 1.8
        items.append(f'\t(gr_line (start {fmt(tx)} {fmt(sy - th)}) (end {fmt(tx)} {fmt(sy + th)}) (stroke (width 0.30) (type solid)) (layer "Dwgs.User") (uuid "{duuid(f"sb:t{mm}")}"))')
    items.append(
        f'\t(gr_text "IN DUNG TI LE 1:1 - THANH NAY PHAI DO DUOC 50 mm"\n'
        f'\t\t(at {fmt((sx0 + sx1) / 2.0)} {fmt(sy + 6.5)} 0)\n'
        f'\t\t(layer "Dwgs.User")\n'
        f'\t\t(uuid "{duuid("sb:txt")}")\n'
        f'\t\t(effects (font (size 2.0 2.0) (thickness 0.35)))\n'
        f'\t)'
    )
    items.append(f'\t(gr_text "0 mm" (at {fmt(sx0)} {fmt(sy - 5.0)} 0) (layer "Dwgs.User") (uuid "{duuid("sb:t0l")}") (effects (font (size 1.6 1.6) (thickness 0.25))))')
    items.append(f'\t(gr_text "50.0 mm" (at {fmt(sx1)} {fmt(sy - 5.0)} 0) (layer "Dwgs.User") (uuid "{duuid("sb:t50l")}") (effects (font (size 1.6 1.6) (thickness 0.25))))')
    # Mirror-check label on Dwgs.User inside bottom-right margin (reads backwards on mirrored toner PDF, forward on check PDF!)
    items.append(
        f'\t(gr_text "SMARTHOME HUB DIY v3.0 - B.Cu (100x80mm)"\n'
        f'\t\t(at {fmt(BX0 + BOARD_W / 2.0)} {fmt(BY0 - 6.0)} 0)\n'
        f'\t\t(layer "Dwgs.User")\n'
        f'\t\t(uuid "{duuid("sb:hdr")}")\n'
        f'\t\t(effects (font (size 2.0 2.0) (thickness 0.35)))\n'
        f'\t)'
    )
    for cname, cx, cy, dx, dy in [
        ("tl", BX0, BY0, -4.0, -4.0),
        ("tr", BX0 + BOARD_W, BY0, 4.0, -4.0),
        ("bl", BX0, BY_BOT, -4.0, 4.0),
        ("br", BX0 + BOARD_W, BY_BOT, 4.0, 4.0),
    ]:
        items.append(f'\t(gr_line (start {fmt(cx + dx * 0.3)} {fmt(cy)}) (end {fmt(cx + dx)} {fmt(cy)}) (stroke (width 0.20) (type solid)) (layer "Dwgs.User") (uuid "{duuid(f"cm:{cname}h")}"))')
        items.append(f'\t(gr_line (start {fmt(cx)} {fmt(cy + dy * 0.3)}) (end {fmt(cx)} {fmt(cy + dy)}) (stroke (width 0.20) (type solid)) (layer "Dwgs.User") (uuid "{duuid(f"cm:{cname}v")}"))')
    return items


def build_silkscreen_and_fab(comps: list[ComponentSpec]) -> list[str]:
    """Big readable F.SilkS labels (>= 1.5 mm height, >= 0.25 mm thickness) + F.Fab ref/val assembly labels."""
    labels: list[tuple[str, float, float, float, float, float]] = [
        ("HUB DIY v3", 48.5, 41.5, 0.0, 1.8, 0.30),
        ("1L B.Cu", 48.5, 37.5, 0.0, 1.5, 0.25),
        ("100x80mm", 48.5, 34.0, 0.0, 1.5, 0.25),
        ("NODEMCU", 48.5, 29.5, 0.0, 1.5, 0.25),
        ("USB v", 48.5, 25.0, 0.0, 1.5, 0.25),

        # Top edge headers
        ("J14 SOIL A0", 19.0, 77.2, 0.0, 1.5, 0.25),
        ("3V G A0", 19.0, 68.0, 0.0, 1.5, 0.25),
        ("J4 LED_LR D0", 41.8, 77.2, 0.0, 1.5, 0.25),
        ("+  G", 41.8, 68.0, 0.0, 1.5, 0.25),
        ("J3 SERVO D1", 60.5, 77.2, 0.0, 1.5, 0.25),
        ("S 5V G", 60.5, 74.6, 0.0, 1.5, 0.25),
        ("J13 DHT D2", 79.0, 77.6, 0.0, 1.5, 0.25),
        ("G D 3V", 79.0, 75.5, 0.0, 1.5, 0.25),

        # Right edge headers (module + NodeMCU pin + per-pin labels)
        ("J5 BR D4", 93.2, 66.5, 0.0, 1.5, 0.25),
        ("+", 95.8, 62.0, 0.0, 1.5, 0.25),
        ("D4", 95.8, 59.4, 0.0, 1.5, 0.25),
        ("J15 MIC", 93.5, 51.5, 0.0, 1.5, 0.25),
        ("3V", 95.8, 47.0, 0.0, 1.5, 0.25),
        ("G", 95.8, 44.5, 0.0, 1.5, 0.25),
        ("D5", 95.8, 41.9, 0.0, 1.5, 0.25),
        ("J7 RLY1", 92.8, 38.0, 0.0, 1.5, 0.25),
        ("D6", 95.8, 33.5, 0.0, 1.5, 0.25),
        ("G", 95.8, 30.9, 0.0, 1.5, 0.25),
        ("5V", 95.8, 28.4, 0.0, 1.5, 0.25),
        ("J9 RLY2", 92.8, 24.5, 0.0, 1.5, 0.25),
        ("D7", 95.8, 20.5, 0.0, 1.5, 0.25),
        ("G", 95.8, 17.9, 0.0, 1.5, 0.25),
        ("5V", 95.8, 15.4, 0.0, 1.5, 0.25),

        # Bottom edge headers
        ("J10 RLY2", 16.5, 3.0, 0.0, 1.5, 0.25),
        ("5V A5", 17.8, 11.8, 0.0, 1.5, 0.25),
        ("J11 PAM", 30.8, 3.0, 0.0, 1.5, 0.25),
        ("5V G", 30.3, 11.8, 0.0, 1.5, 0.25),
        ("J12 AUD D3", 54.0, 2.8, 0.0, 1.5, 0.25),
        ("L  G", 54.8, 5.4, 0.0, 1.5, 0.25),
        ("Q1 S8050", 71.5, 4.8, 0.0, 1.5, 0.25),
        ("E B C", 71.5, 7.2, 0.0, 1.5, 0.25),
        ("J6 BUZZ D8", 83.7, 2.8, 0.0, 1.5, 0.25),
        ("-  +", 83.7, 5.2, 0.0, 1.5, 0.25),

        # Left edge terminals & header
        ("J2 PUMP", 10.0, 64.5, 0.0, 1.5, 0.25),
        ("+", 2.5, 58.0, 0.0, 1.5, 0.25),
        ("-", 2.5, 52.9, 0.0, 1.5, 0.25),
        ("J8 SW", 28.5, 52.0, 0.0, 1.5, 0.25),
        ("P", 27.5, 58.0, 0.0, 1.5, 0.25),
        ("5V", 28.0, 55.4, 0.0, 1.5, 0.25),
        ("J1 5V IN", 10.0, 33.0, 0.0, 1.5, 0.25),
        ("+", 2.5, 26.5, 0.0, 1.5, 0.25),
        ("-", 2.5, 21.4, 0.0, 1.5, 0.25),

        # Jumper labels J-1..J-7
        ("J-1", 49.3, 48.5, 0.0, 1.5, 0.25),
        ("J-2", 32.1, 60.2, 0.0, 1.5, 0.25),
        ("J-3", 73.2, 50.5, 90.0, 1.5, 0.25),
        ("J-4", 54.0, 22.0, 0.0, 1.5, 0.25),
        ("J-5", 83.0, 22.0, 90.0, 1.5, 0.25),
        ("J-6", 83.0, 41.5, 90.0, 1.5, 0.25),
        ("J-7", 72.8, 69.2, 0.0, 1.5, 0.25),
    ]
    out = []
    for idx, (txt, bx, by, rot, sz, th) in enumerate(labels):
        kx, ky = b2k(bx, by)
        out.append(
            f'\t(gr_text "{txt}" (at {fmt(kx)} {fmt(ky)} {fmt(rot)}) (layer "F.SilkS") (uuid "{duuid(f"silk:{idx}:{txt}")}")\n'
            f'\t\t(effects (font (size {fmt(sz)} {fmt(sz)}) (thickness {fmt(th)}))))'
        )

    # Assembly reference + value labels on F.Fab for every passive / active part (plotted on placement_top_silk_1to1.pdf!)
    fab_notes: list[tuple[str, float, float, float]] = [
        ("C1 470uF+", 21.75, 47.6, 0.0),
        ("C2 470uF+", 21.75, 37.6, 0.0),
        ("C3 100n", 32.0, 25.94, 90.0),
        ("C4 10uF+", 45.25, 10.6, 0.0),
        ("C5 10n", 62.5, 5.6, 0.0),
        ("C6 100n", 36.0, 17.6, 0.0),
        ("C7 100n", 29.0, 69.5, 0.0),
        ("D1 1N4007", 13.8, 52.9, 90.0),
        ("D2 1N4007", 80.5, 16.7, 90.0),
        ("D3 PWR", 10.0, 15.8, 0.0),
        ("Q1 S8050", 71.5, 11.2, 0.0),
        ("R1 220R", 48.9, 65.5, 0.0),
        ("R2 220R", 81.1, 60.8, 0.0),
        ("R3 10k", 70.9, 64.1, 0.0),
        ("R4 10k", 48.1, 51.38, 0.0),
        ("R5 2.2k", 55.1, 16.5, 0.0),
        ("R6 2.2k", 55.1, 12.8, 0.0),
        ("R7 10k", 81.1, 57.5, 0.0),
        ("R8 1k", 16.9, 17.0, 0.0),
        ("R9 10k", 70.4, 30.2, 0.0),
        ("R10 1k", 75.5, 21.4, 90.0),
        ("U1 LEFT 1x15", 34.4, 41.2, 90.0),
        ("U2 RIGHT 1x15", 62.5, 41.2, 90.0),
    ]
    for idx, (txt, bx, by, rot) in enumerate(fab_notes):
        kx, ky = b2k(bx, by)
        out.append(
            f'\t(gr_text "{txt}" (at {fmt(kx)} {fmt(ky)} {fmt(rot)}) (layer "F.Fab") (uuid "{duuid(f"fabtxt:{idx}:{txt}")}")\n'
            f'\t\t(effects (font (size 1.1 1.1) (thickness 0.18))))'
        )

    # NodeMCU v2 Amica mechanical outline on F.Fab (exact 48.26 x 25.40 mm centered between U1 & U2)
    nx0, ny1 = b2k(35.73, 65.35)
    nx1, ny0 = b2k(61.13, 17.09)
    out.append(f'\t(gr_rect (start {fmt(nx0)} {fmt(ny1)}) (end {fmt(nx1)} {fmt(ny0)}) (stroke (width 0.15) (type dash)) (fill no) (layer "F.Fab") (uuid "{duuid("fab:nodemcu")}"))')
    return out


def build_all() -> None:
    comps = get_components()
    write_footprint_library(comps)
    write_fp_lib_table()
    sch_paths, sch_descrs, sch_pad_nets = sync_schematic(comps)
    write_bom(comps)

    # Map logical net names in get_components()/get_tracks() to exact KiCad schematic net names
    net_alias: dict[str, str] = {}
    for c in comps:
        for pnum, logical_net in c.pins.items():
            if not logical_net:
                continue
            sch_net = sch_pad_nets.get((c.ref, pnum))
            if not sch_net:
                raise RuntimeError(f"Missing schematic net for {c.ref}.{pnum} (logical={logical_net})")
            if logical_net in net_alias and net_alias[logical_net] != sch_net:
                raise RuntimeError(
                    f"Net alias conflict for {logical_net}: {net_alias[logical_net]} vs {sch_net} at {c.ref}.{pnum}"
                )
            net_alias[logical_net] = sch_net

    power_net_names = sorted({net_alias[n] for n in POWER_NETS_ALL})
    update_kicad_pro(power_net_names)
    write_dru(power_net_names)

    # Collect EVERY schematic net (including unconnected-(U1/U2-...) NC pad nets) for 0 --schematic-parity warnings
    all_net_names = sorted(set(sch_pad_nets.values()))
    net_id = {n: i + 1 for i, n in enumerate(all_net_names)}
    pm = compute_pad_coords(comps)
    tracks = get_tracks(pm)

    lines: list[str] = [
        '(kicad_pcb',
        '\t(version 20260206)',
        '\t(generator "pcbnew")',
        '\t(generator_version "10.0")',
        '\t(general (thickness 1.6) (legacy_teardrops no))',
        '\t(paper "A4")',
        '\t(title_block',
        '\t\t(title "SmartHome Hub DIY Single-Layer PCB (100x80mm)")',
        '\t\t(date "2026-11-21")',
        '\t\t(rev "3.0-DIY")',
        '\t\t(company "DATN Smart Home Voice AI - SEEE HUST")',
        '\t)',
        '\t(layers',
        '\t\t(0 "F.Cu" signal)',
        '\t\t(2 "B.Cu" signal)',
        '\t\t(9 "F.Adhes" user "F.Adhesive")',
        '\t\t(11 "B.Adhes" user "B.Adhesive")',
        '\t\t(13 "F.Paste" user)',
        '\t\t(15 "B.Paste" user)',
        '\t\t(5 "F.SilkS" user "F.Silkscreen")',
        '\t\t(7 "B.SilkS" user "B.Silkscreen")',
        '\t\t(1 "F.Mask" user)',
        '\t\t(3 "B.Mask" user)',
        '\t\t(17 "Dwgs.User" user "User.Drawings")',
        '\t\t(19 "Cmts.User" user "User.Comments")',
        '\t\t(21 "Eco1.User" user "User.Eco1")',
        '\t\t(23 "Eco2.User" user "User.Eco2")',
        '\t\t(25 "Edge.Cuts" user)',
        '\t\t(27 "Margin" user)',
        '\t\t(31 "F.CrtYd" user "F.Courtyard")',
        '\t\t(29 "B.CrtYd" user "B.Courtyard")',
        '\t\t(35 "F.Fab" user)',
        '\t\t(33 "B.Fab" user)',
        '\t)',
        '\t(setup (pad_to_mask_clearance 0) (allow_soldermask_bridges_in_footprints no))',
        '\t(net 0 "")',
    ]
    for n in all_net_names:
        lines.append(f'\t(net {net_id[n]} "{n}")')

    for c in comps:
        kx, ky = b2k(c.bx, c.by)
        pn: dict[str, tuple[int, str]] = {}
        for (r, pnum), sch_net in sch_pad_nets.items():
            if r == c.ref:
                pn[pnum] = (net_id[sch_net], sch_net)
        lines.append(
            build_footprint_body(
                c.fp_name, FP_DESCRS[c.fp_name],
                is_board_instance=True,
                ref=c.ref, value=c.value,
                at_kx=kx, at_ky=ky, rot_deg=c.rot,
                pad_nets=pn,
                fp_uuid_key=f"board:{c.ref}",
                jumper_pitch=c.jumper_pitch,
                sch_path=sch_paths.get(c.ref, ""),
                sch_descr=sch_descrs.get(c.ref),
            )
        )

    lines.extend(build_edge_cuts())
    lines.extend(build_scale_bar())
    lines.extend(build_silkscreen_and_fab(comps))

    seg_idx = 0
    for net, width, pts in tracks:
        nid = net_id[net_alias[net]]
        for i in range(len(pts) - 1):
            x1, y1 = b2k(pts[i][0], pts[i][1])
            x2, y2 = b2k(pts[i + 1][0], pts[i + 1][1])
            if math.hypot(x2 - x1, y2 - y1) < 1e-4:
                continue
            seg_idx += 1
            lines.append(
                f'\t(segment (start {fmt(x1)} {fmt(y1)}) (end {fmt(x2)} {fmt(y2)}) '
                f'(width {fmt(width)}) (layer "B.Cu") (net {nid}) (uuid "{duuid(f"seg:{seg_idx}")}"))'
            )

    lines.append(")")
    pcb_path = KICAD_DIR / "smarthome_hub.kicad_pcb"
    pcb_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Canonicalize DIY_Hub.pretty footprints via KiCad 10 pcbnew so lib_footprint_mismatch == 0
    canon_code = f"""
import pcbnew
b = pcbnew.LoadBoard(r"{pcb_path}")
lib_dir = r"{FP_LIB_DIR}"
seen = set()
for fp in b.GetFootprints():
    name = str(fp.GetFPID().GetLibItemName())
    if name in seen:
        continue
    seen.add(name)
    fp.SetOrientationDegrees(0.0)
    fp.SetPosition(pcbnew.VECTOR2I(0, 0))
    fp.SetReference("REF**")
    fp.SetValue(name)
    for p in fp.Pads():
        p.SetNetCode(0)
    pcbnew.FootprintSave(lib_dir, fp)
"""
    subprocess.run([KPY, "-c", canon_code], check=True)

    # Run ERC + DRC with --schematic-parity!
    rep_dir = KICAD_DIR / "reports"
    rep_dir.mkdir(parents=True, exist_ok=True)
    erc_txt = rep_dir / "erc.txt"
    drc_txt = rep_dir / "drc.txt"
    erc_json = rep_dir / "erc.json"
    drc_json = rep_dir / "drc.json"

    r_erc = subprocess.run(
        [KCLI, "sch", "erc", "--severity-all", "--format", "report", "-o", str(erc_txt), str(KICAD_DIR / "smarthome_hub.kicad_sch")],
        capture_output=True, text=True,
    )
    subprocess.run(
        [KCLI, "sch", "erc", "--severity-all", "--format", "json", "-o", str(erc_json), str(KICAD_DIR / "smarthome_hub.kicad_sch")],
        capture_output=True, text=True,
    )
    r_drc = subprocess.run(
        [KCLI, "pcb", "drc", "--schematic-parity", "--severity-all", "--format", "report", "-o", str(drc_txt), str(pcb_path)],
        capture_output=True, text=True,
    )
    subprocess.run(
        [KCLI, "pcb", "drc", "--schematic-parity", "--severity-all", "--format", "json", "-o", str(drc_json), str(pcb_path)],
        capture_output=True, text=True,
    )

    print(f"Built synchronized DIY Hub: {len(comps)} footprints ({len(sch_paths)} linked to schematic), {seg_idx} B.Cu segments.")
    print("=== ERC ===")
    print(erc_txt.read_text(encoding="utf-8"))
    print("=== DRC (--schematic-parity) ===")
    print(drc_txt.read_text(encoding="utf-8"))


if __name__ == "__main__":
    build_all()
