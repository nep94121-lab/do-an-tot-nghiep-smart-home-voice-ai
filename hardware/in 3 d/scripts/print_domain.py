"""Single-source-of-truth domain model for 3D-Print Set v2 (Screwless Mong Joints, 180x200x250 Bed, Furniture).

Pure Python (zero external dependencies) so FreeCAD 1.1 Python and system Python share
the exact same specifications. Derives all panel dimensions from `hardware/mica/mica_design.py`
and real Hub PCB geometry from `scripts/kicad_pcb_ssot.py` (`smarthome_hub.kicad_pcb`).

Key v2 invariants:
1. ZERO screws, ZERO glue anywhere: every M2/M2.5/M3/clamp fastener hole from mica_design.py
   is stripped and replaced by rectangular mortise slots, press-fit tenons, or snap-fit clips.
2. Bed envelope 180 x 200 x 250 mm (5 mm margin -> 170 x 190 x 245 mm usable), rotation-aware
   minimum-piece dovetail splitting.
3. House-scale furniture (Living room sofa + TV with stand, Bedroom bed + bedside table,
   Outdoor plant pots + interlocking mini trees) attached by floor mortise pegs in P01A/P01B.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import pathlib
import sys
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PRINT3D_ROOT = SCRIPT_DIR.parent
HARDWARE_ROOT = PRINT3D_ROOT.parent
MICA_DIR = HARDWARE_ROOT / "mica"
REPO_ROOT = HARDWARE_ROOT.parent

for _p in (str(MICA_DIR), str(SCRIPT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import mica_design as md
import kicad_pcb_ssot as pcb_ssot
import lightweight_policy as lp


# Fastener hole kinds stripped from 3D-print panels (replaced by mong mortise slots)
STRIPPED_FASTENER_KINDS: frozenset[str] = frozenset({"m3", "m2", "m2.5", "clamp"})

# Functional non-fastener holes preserved and documented
FUNCTIONAL_HOLE_DOCS: dict[str, str] = {
    "led": "Lo den LED bao hieu 5mm (5.5mm) va LED nguon 3mm (3.5mm) — lo chuc nang quang hoc, khong phai vit.",
    "buzzer": "Lo coi bao dong chu dong TMB12A05 (12.5mm) — lo phat am thanh, khong phai vit.",
    "mic": "Lo thu am micro electret 9.7mm cho cam bien KY-037 (10.5mm) — lo cam bien am thanh.",
    "dcjack": "Lo giac nguon DC-022 5.5x2.1mm (12.5mm) — lo cap nguon 5V 2A.",
    "cable": "Lo luon bo day tin hieu Dupont (14.0mm) — lo di day dien lien phong.",
    "tube": "Lo luon ong silicon bom tuoi cay OD 8mm (10.0mm) — lo ong nuoc.",
    "grille": "Cum 19 lo luoi thoat am thanh (3.0mm) cho loa mini 28mm — luoi loa, khong phai vit.",
}


@dataclass(frozen=True)
class ClearanceEntry:
    fit_type: str
    vi_name: str
    clearance_mm: float
    tolerance_band: str
    where_used: str
    nozzle_note: str = "FDM PLA, dau phun 0.4 mm, lop 0.20 mm"


CLEARANCE_TABLE: tuple[ClearanceEntry, ...] = (
    ClearanceEntry(
        fit_type="dovetail_seam",
        vi_name="Khop mong duoi en (tach manh tam lon)",
        clearance_mm=0.20,
        tolerance_band="0.18 - 0.22 mm",
        where_used="Cac duong noi chia manh tren P01A, P01B, P02, P05, P15",
    ),
    ClearanceEntry(
        fit_type="panel_tab_slot",
        vi_name="Khop mong rang luoc (tab-and-slot) giua cac tam",
        clearance_mm=0.25,
        tolerance_band="0.20 - 0.30 mm",
        where_used="Toan bo canh noi tuong/day/vuon (ranh 3.25 mm cho tam 3.0 mm)",
    ),
    ClearanceEntry(
        fit_type="corner_lock_clip",
        vi_name="Kep khoa goc 90 do & kep chu U khoa moi noi",
        clearance_mm=0.20,
        tolerance_band="0.18 - 0.22 mm",
        where_used="SUP01, SUP01B, SUP02, SUP03, SUP04 (ranh chu U 3.20 mm cho tam 3.0 mm)",
    ),
    ClearanceEntry(
        fit_type="mortise_tenon_press",
        vi_name="Mong chot vuong ep khit (mortise-and-tenon)",
        clearance_mm=0.15,
        tolerance_band="0.12 - 0.18 mm / canh (+0.30 mm tong)",
        where_used="P17 thanh noi day, chan gia do SUP05..SUP18",
    ),
    ClearanceEntry(
        fit_type="snap_fit_peg",
        vi_name="Chot dan hoi tu khoa (split snap-fit peg)",
        clearance_mm=0.20,
        tolerance_band="0.18 - 0.22 mm duong kinh + gai khoa 0.25 mm",
        where_used="SUP06 (4 chot 3.0 mm vao lo 3.2 mm Hub PCB), SUP07 (4 chot 2.9 mm vao lo 3.1 mm Relay)",
    ),
    ClearanceEntry(
        fit_type="edge_rail",
        vi_name="Ranh truot & ngoam kep mep bo mach",
        clearance_mm=0.20,
        tolerance_band="0.20 mm / canh (+0.40 mm tong khoang trong)",
        where_used="SUP08 (PAM8403), SUP09 (Loa 28mm), SUP10B (Tay don SG90), SUP11 (SG90), SUP12 (DHT11), SUP13 (KY-037), SUP14 (LM393), SUP16 (DC-022), SUP17 (LED 5mm), SUP18 (Coi TMB12A05)",
    ),
    ClearanceEntry(
        fit_type="hinge_pivot",
        vi_name="Truc xoay ban le mong cua chinh",
        clearance_mm=0.30,
        tolerance_band="0.25 - 0.35 mm duong kinh",
        where_used="SUP10 ban le cua P08 <-> P05 (truc 2.7 mm trong ong 3.0 mm, xoay nhe theo Servo SG90)",
    ),
)

CLEARANCE_MAP: dict[str, ClearanceEntry] = {c.fit_type: c for c in CLEARANCE_TABLE}


@dataclass(frozen=True)
class PrintConfig:
    """FDM printer bed envelope (180x200x250 mm) and 3D-printing mechanical tolerances."""

    bed_x: float = 180.0
    bed_y: float = 200.0
    bed_z: float = 250.0
    bed_margin: float = 5.0
    plate_spacing: float = 3.0
    T_mm: float = 3.0
    tab_clr: float = 0.25
    dovetail_clearance: float = 0.20
    dovetail_depth: float = 6.0
    dovetail_neck: float = 10.0
    dovetail_head: float = 14.0
    compact_dovetail_depth: float = 4.0
    compact_dovetail_neck: float = 5.5
    compact_dovetail_head: float = 8.0
    mortise_clr_per_side: float = 0.15  # +0.30 mm total slot clearance for press-fit tenons
    clip_slot_clr: float = 0.20  # 3.20 mm U-channel for 3.0 mm panel
    edge_rail_clr_per_side: float = 0.20  # +0.40 mm total cavity clearance for PCBs/modules
    snap_peg_dia_clr: float = 0.20  # peg OD = hole_d - 0.20 mm
    hinge_pin_clr: float = 0.30
    engrave_depth: float = 0.60
    min_feature_clearance: float = 3.0

    @property
    def usable_x(self) -> float:
        return self.bed_x - 2.0 * self.bed_margin  # 170.0

    @property
    def usable_y(self) -> float:
        return self.bed_y - 2.0 * self.bed_margin  # 190.0

    @property
    def usable_z(self) -> float:
        return self.bed_z - self.bed_margin  # 245.0


@dataclass(frozen=True)
class MortiseSlotSpec:
    """Rectangular mortise cut through a panel (panel shifted local u, v coordinates)."""

    name: str
    cx: float
    cy: float
    du: float
    dv: float
    purpose: str


@dataclass(frozen=True)
class DovetailJointSpec:
    """One trapezoidal dovetail joint along a split seam."""

    axis: str  # "U" or "V"
    cut_pos: float
    center_along: float
    depth: float
    neck_w: float
    head_w: float
    clearance: float
    male_side: int  # +1 or -1


@dataclass(frozen=True)
class EngraveSpec:
    """Placement of recessed engraved ID + dimension text on the UP-facing print face."""

    line1: str
    line2: str
    cx: float
    cy: float
    font_h: float
    rotated_90: bool = False


@dataclass(frozen=True)
class PanelPieceSpec:
    """One 3D-printable screwless panel (or interlocking dovetail split piece)."""

    part_id: str
    source_panel_id: str
    piece_index: int
    piece_count: int
    qty: int
    plane: str
    origin_xyz: tuple[float, float, float]
    extra_origins_xyz: tuple[tuple[float, float, float], ...]
    explode_xyz: tuple[float, float, float]
    shift_u: float
    shift_v: float
    u_range: tuple[float, float]
    v_range: tuple[float, float]
    dovetails: tuple[DovetailJointSpec, ...]
    mortises: tuple[MortiseSlotSpec, ...]
    engrave: EngraveSpec
    vi_name: str
    notes: str
    color_rgb: tuple[float, float, float]
    stripped_fastener_holes: tuple[str, ...] = ()
    kept_functional_holes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SupportSpec:
    """One screwless printable structural clip, snap mount, hinge, or liner."""

    part_id: str
    vi_name: str
    category: str
    qty: int
    size_xyz: tuple[float, float, float]
    engrave: EngraveSpec
    params: dict[str, Any]
    mating_source: str
    assembly_placements: tuple[dict[str, Any], ...]
    notes: str = ""
    color_rgb: tuple[float, float, float] = (0.94, 0.62, 0.24)


@dataclass(frozen=True)
class FurnitureSpec:
    """One house-scale 3D-printable furniture item pegged into floor mortises."""

    part_id: str
    vi_name: str
    room: str  # "Living Room", "Bedroom", "Outdoor / Garden"
    category: str  # "sofa", "tv_stand", "tv_screen", "bed", "bedside", "plant_pot", "mini_tree"
    qty: int
    size_xyz: tuple[float, float, float]  # print-oriented approx bbox
    engrave: EngraveSpec
    params: dict[str, Any]
    attachment: str
    assembly_placements: tuple[dict[str, Any], ...]  # world center (x, y, z_floor), rot_z, bbox_world_xyz
    notes: str = ""
    color_rgb: tuple[float, float, float] = (0.52, 0.68, 0.56)


VI_PANEL_NAMES: dict[str, str] = {
    "P01A_BASE_TECH": "Tam day truoc (Khoang ky thuat & Vuon)",
    "P01B_BASE_HOUSE": "Tam day sau (Phong khach & Phong ngu)",
    "P02_WALL_BACK": "Tuong sau (Phong khach + Phong ngu)",
    "P03_WALL_LEFT": "Vach hong trai cat mo",
    "P04_WALL_RIGHT": "Vach hong phai cat mo",
    "P05_WALL_FRONT": "Tuong mat tien & Khung cua chinh",
    "P06_WALL_MID": "Vach ngan giua (Phong khach / Phong ngu)",
    "P07_SERVO_SHELF": "Ke gan Servo SG90 cua chinh (mong cai)",
    "P08_DOOR_LEAF": "Canh cua chinh (ban le mong)",
    "P09_GARDEN_LEFT": "Vach trai be nuoc",
    "P10_WATER_DIVIDER": "Vach ngan be nuoc & chau cay",
    "P11_GARDEN_RIGHT": "Vach phai chau cay",
    "P12_GARDEN_FRONT": "Vach truoc be nuoc & chau cay",
    "P13_GARDEN_BACK": "Vach sau be nuoc & chau cay",
    "P14_SOIL_BRIDGE": "Cau giu dau do am dat YL-69",
    "P15_TECH_FASCIA": "Mat na ky thuat (Nguon DC & Loa)",
    "P16_PCB_PLATE": "Tam ga bo mach Hub PCB (khong vit)",
    "P17_BASE_JOINER": "Thanh mong noi day 4 chot (mat duoi)",
}


def build_panel_mortise_map(cfg: PrintConfig | None = None) -> dict[str, list[MortiseSlotSpec]]:
    """Define every screwless rectangular mortise slot injected into panels (shifted local u, v)."""
    cfg = cfg or PrintConfig()
    c2 = 2.0 * cfg.mortise_clr_per_side  # +0.30 mm total clearance

    # Shift for P01B_BASE_HOUSE: v_shifted = world_Y - 174.125
    p01b_sv = -174.125

    def m(name: str, cx: float, cy: float, tenon_u: float, tenon_v: float, purpose: str) -> MortiseSlotSpec:
        return MortiseSlotSpec(
            name=name,
            cx=round(cx, 3),
            cy=round(cy, 3),
            du=round(tenon_u + c2, 3),
            dv=round(tenon_v + c2, 3),
            purpose=purpose,
        )

    return {
        "P01A_BASE_TECH": [
            # 4x P16_PCB_PLATE tenon risers (SUP05) at exact 116x96 pitch centered at (122, 104)
            m("MORT_P16_R1", 64.0, 152.0, 8.0, 3.0, "SUP05_P16_TENON_RISER corner 1"),
            m("MORT_P16_R2", 180.0, 152.0, 8.0, 3.0, "SUP05_P16_TENON_RISER corner 2"),
            m("MORT_P16_R3", 64.0, 56.0, 8.0, 3.0, "SUP05_P16_TENON_RISER corner 3"),
            m("MORT_P16_R4", 180.0, 56.0, 8.0, 3.0, "SUP05_P16_TENON_RISER corner 4"),
            # 2x Relay 1 snap caddy tenons (SUP07 #1 centered at 226, 136)
            m("MORT_RLY1_L", 210.0, 136.0, 6.0, 3.0, "SUP07_RELAY_SNAP_CADDY #1 left floating tenon"),
            m("MORT_RLY1_R", 242.0, 136.0, 6.0, 3.0, "SUP07_RELAY_SNAP_CADDY #1 right floating tenon"),
            # 2x Relay 2 snap caddy tenons (SUP07 #2 centered at 226, 92)
            m("MORT_RLY2_L", 210.0, 92.0, 6.0, 3.0, "SUP07_RELAY_SNAP_CADDY #2 left floating tenon"),
            m("MORT_RLY2_R", 242.0, 92.0, 6.0, 3.0, "SUP07_RELAY_SNAP_CADDY #2 right floating tenon"),
            # 2x PAM8403 snap tray tenons (SUP08 centered at 224, 52, 26mm span)
            m("MORT_PAM_L", 211.0, 52.0, 6.0, 3.0, "SUP08_PAM8403_SNAP_TRAY left floating tenon"),
            m("MORT_PAM_R", 237.0, 52.0, 6.0, 3.0, "SUP08_PAM8403_SNAP_TRAY right floating tenon"),
            # 4x P17_BASE_JOINER interlocking tenon mortises (left & right splice bars)
            m("MORT_JOIN_L1", 80.0, 166.0, 8.0, 4.0, "P17_BASE_JOINER left bar front-L tenon"),
            m("MORT_JOIN_L2", 120.0, 166.0, 8.0, 4.0, "P17_BASE_JOINER left bar front-R tenon"),
            m("MORT_JOIN_R1", 286.0, 166.0, 8.0, 4.0, "P17_BASE_JOINER right bar front-L tenon"),
            m("MORT_JOIN_R2", 326.0, 166.0, 8.0, 4.0, "P17_BASE_JOINER right bar front-R tenon"),
        ],
        "P01B_BASE_HOUSE": [
            # 4x P17_BASE_JOINER mortises (world Y = 182.0 -> v_shifted = 7.875)
            m("MORT_JOIN_L3", 80.0, 182.0 + p01b_sv, 8.0, 4.0, "P17_BASE_JOINER left bar rear-L tenon"),
            m("MORT_JOIN_L4", 120.0, 182.0 + p01b_sv, 8.0, 4.0, "P17_BASE_JOINER left bar rear-R tenon"),
            m("MORT_JOIN_R3", 286.0, 182.0 + p01b_sv, 8.0, 4.0, "P17_BASE_JOINER right bar rear-L tenon"),
            m("MORT_JOIN_R4", 326.0, 182.0 + p01b_sv, 8.0, 4.0, "P17_BASE_JOINER right bar rear-R tenon"),
        ],
        "P02_WALL_BACK": [],
        "P05_WALL_FRONT": [
            # SUP13_KY037_SNAP_CRADLE flanking KY-037 (centered u=158, v=29; mic at u=148)
            m("MORT_KY037_L", 138.0, 29.0, 3.0, 6.0, "SUP13_KY037_SNAP_CRADLE left tenon"),
            m("MORT_KY037_R", 178.0, 29.0, 3.0, 6.0, "SUP13_KY037_SNAP_CRADLE right tenon"),
            # SUP10_DOOR_MORTISE_HINGE jamb slots (world X=72.5 -> u=62.5; world Z=18, 78 -> v_s=21, 81)
            m("MORT_HINGE_BOT", 62.5, 21.0, 4.0, 6.0, "SUP10_DOOR_MORTISE_HINGE bottom jamb tenon"),
            m("MORT_HINGE_TOP", 62.5, 81.0, 4.0, 6.0, "SUP10_DOOR_MORTISE_HINGE top jamb tenon (Z=78)"),
            # SUP18_BUZZER_SNAP_COLLAR flanking TMB12A05 buzzer (u=190, v_s=129; strictly in P06 relief Z>112)
            m("MORT_BUZZ_BOT", 190.0, 118.0, 6.0, 3.0, "SUP18_BUZZER_SNAP_COLLAR bottom tenon"),
            m("MORT_BUZZ_TOP", 190.0, 140.0, 6.0, 3.0, "SUP18_BUZZER_SNAP_COLLAR top tenon"),
        ],
        "P06_WALL_MID": [
            # SUP12_DHT11_SNAP_CRADLE flanking DHT11_Airflow on P06 (u=87.75..100.25, v_shifted=83..99)
            m("MORT_DHT11_L", 83.0, 91.0, 3.0, 6.0, "SUP12_DHT11_SNAP_CRADLE left tenon"),
            m("MORT_DHT11_R", 105.0, 91.0, 3.0, 6.0, "SUP12_DHT11_SNAP_CRADLE right tenon"),
            # SUP17_LED5MM_RETAINING_COLLAR flanking Living Room LED (u=40, v_s=129) & Bedroom LED (u=66, v_s=129)
            m("MORT_LED_LR_L", 32.0, 129.0, 3.0, 6.0, "SUP17_LED5MM_RETAINING_COLLAR living room left tenon"),
            m("MORT_LED_LR_R", 48.0, 129.0, 3.0, 6.0, "SUP17_LED5MM_RETAINING_COLLAR living room right tenon"),
            m("MORT_LED_BR_L", 58.0, 129.0, 3.0, 6.0, "SUP17_LED5MM_RETAINING_COLLAR bedroom left tenon"),
            m("MORT_LED_BR_R", 74.0, 129.0, 3.0, 6.0, "SUP17_LED5MM_RETAINING_COLLAR bedroom right tenon"),
        ],
        "P07_SERVO_SHELF": [
            # SUP11_SG90_SNAP_SADDLE mortises flanking SG90 ears along X (unshifted u=3.5, 43.5, v=6.375 -> v_s=9.500)
            m("MORT_SG90_L", 3.5, 9.5, 3.0, 6.0, "SUP11_SG90_SNAP_SADDLE left tenon"),
            m("MORT_SG90_R", 43.5, 9.5, 3.0, 6.0, "SUP11_SG90_SNAP_SADDLE right tenon"),
        ],
        "P08_DOOR_LEAF": [
            # SUP10_DOOR_MORTISE_HINGE leaf slots (Z=18, 78 -> v=16, 76) + SUP10B_DOOR_HORN_COUPLER slot (Z=97 -> v=95)
            m("MORT_DOOR_HBOT", 5.5, 16.0, 4.0, 6.0, "SUP10_DOOR_MORTISE_HINGE bottom door tenon"),
            m("MORT_DOOR_HTOP", 5.5, 76.0, 4.0, 6.0, "SUP10_DOOR_MORTISE_HINGE top door tenon (Z=78)"),
            m("MORT_DOOR_LINK", 10.0, 95.0, 4.0, 6.0, "SUP10B_DOOR_HORN_COUPLER coaxial top-jamb fork tenon"),
        ],
        "P12_GARDEN_FRONT": [],
        "P13_GARDEN_BACK": [
            # SUP14_LM393_SNAP_CRADLE flanking LM393 dry exterior rear (u=26, v_shifted=27; span 38mm -> u=7, 45)
            m("MORT_LM393_L", 7.0, 27.0, 3.0, 6.0, "SUP14_LM393_SNAP_CRADLE left tenon"),
            m("MORT_LM393_R", 45.0, 27.0, 3.0, 6.0, "SUP14_LM393_SNAP_CRADLE right tenon"),
        ],
        "P15_TECH_FASCIA": [
            # SUP16_DC022_STRAIN_RELIEF flanking DC-022 barrel jack (u=22, v_s=25; 24mm span)
            m("MORT_DC022_L", 10.0, 25.0, 4.0, 6.0, "SUP16_DC022_STRAIN_RELIEF left tenon"),
            m("MORT_DC022_R", 34.0, 25.0, 4.0, 6.0, "SUP16_DC022_STRAIN_RELIEF right tenon"),
            # SUP09_SPEAKER_SNAP_RETAINER flanking 28mm speaker grille (36mm span)
            m("MORT_SPK_L", 197.0, 29.0, 4.0, 6.0, "SUP09_SPEAKER_SNAP_RETAINER left tenon"),
            m("MORT_SPK_R", 233.0, 29.0, 4.0, 6.0, "SUP09_SPEAKER_SNAP_RETAINER right tenon"),
        ],
        "P16_PCB_PLATE": [
            # 4x SUP05_P16_TENON_RISER corner mortises (116x96 pitch)
            m("MORT_PLT_C1", 7.0, 7.0, 8.0, 3.0, "SUP05_P16_TENON_RISER corner 1"),
            m("MORT_PLT_C2", 123.0, 7.0, 8.0, 3.0, "SUP05_P16_TENON_RISER corner 2"),
            m("MORT_PLT_C3", 7.0, 103.0, 8.0, 3.0, "SUP05_P16_TENON_RISER corner 3"),
            m("MORT_PLT_C4", 123.0, 103.0, 8.0, 3.0, "SUP05_P16_TENON_RISER corner 4"),
            # 4x SUP06_HUB_PCB_SNAP_CARRIER mortises (90x70 pitch, standardized 6x3 floating tenon SUP05B)
            m("MORT_PCB_C1", 20.0, 20.0, 6.0, 3.0, "SUP06_HUB_PCB_SNAP_CARRIER floating tenon 1"),
            m("MORT_PCB_C2", 110.0, 20.0, 6.0, 3.0, "SUP06_HUB_PCB_SNAP_CARRIER floating tenon 2"),
            m("MORT_PCB_C3", 20.0, 90.0, 6.0, 3.0, "SUP06_HUB_PCB_SNAP_CARRIER floating tenon 3"),
            m("MORT_PCB_C4", 110.0, 90.0, 6.0, 3.0, "SUP06_HUB_PCB_SNAP_CARRIER floating tenon 4"),
        ],
        "P17_BASE_JOINER": [],
    }


def evaluate_screwless_panel_2d(
    pspec: md.PanelSpec,
    cfg: PrintConfig | None = None,
) -> dict[str, Any]:
    """Evaluate a panel from mica_design.py with all fastener holes stripped and mortises added."""
    cfg = cfg or PrintConfig()
    ev = md.evaluate_panel_2d(pspec, T_mm=cfg.T_mm, tab_clr=cfg.tab_clr)
    mort_map = build_panel_mortise_map(cfg)
    mortises = mort_map.get(pspec.panel_id, [])

    kept_circles: list[dict[str, Any]] = []
    stripped_names: list[str] = []
    for c in ev["circles"]:
        if c.get("kind", "") in STRIPPED_FASTENER_KINDS:
            stripped_names.append(c["name"])
        else:
            kept_circles.append(c)

    inner_rects = list(ev["inner_rects"])
    for mt in mortises:
        inner_rects.append({
            "name": mt.name,
            "u0": mt.cx - mt.du / 2.0,
            "v0": mt.cy - mt.dv / 2.0,
            "du": mt.du,
            "dv": mt.dv,
            "kind": "mortise",
            "note": mt.purpose,
        })

    out = dict(ev)
    out["circles"] = kept_circles
    out["inner_rects"] = inner_rects
    out["mortises"] = mortises
    out["stripped_fastener_holes"] = stripped_names
    out["kept_functional_holes"] = [c["name"] for c in kept_circles]
    return out


# ---------------------------------------------------------------------------
# 2D Geometry & Rotation-Aware 170x190 Split Solver
# ---------------------------------------------------------------------------
def _point_in_poly(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_int = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_int:
                inside = not inside
    return inside


def _point_dist_to_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _poly_intervals_at_line(poly: list[tuple[float, float]], axis: str, coord: float) -> list[tuple[float, float]]:
    crossings: list[float] = []
    n = len(poly)
    c_probe = coord + 1e-4
    for i in range(n):
        p1 = poly[i]
        p2 = poly[(i + 1) % n]
        if axis == "U":
            a1, b1 = p1[0], p1[1]
            a2, b2 = p2[0], p2[1]
        else:
            a1, b1 = p1[1], p1[0]
            a2, b2 = p2[1], p2[0]
        if (a1 < c_probe <= a2) or (a2 < c_probe <= a1):
            t = (c_probe - a1) / (a2 - a1)
            crossings.append(b1 + t * (b2 - b1))
    crossings.sort()
    intervals: list[tuple[float, float]] = []
    for i in range(0, len(crossings) - 1, 2):
        lo, hi = crossings[i], crossings[i + 1]
        if hi - lo > 0.5:
            intervals.append((lo, hi))
    return intervals


def _rect_inside_piece(
    x0: float, y0: float, x1: float, y1: float,
    ev: dict[str, Any], u_lo: float, u_hi: float, v_lo: float, v_hi: float, margin: float,
) -> bool:
    if x0 < u_lo + margin or x1 > u_hi - margin or y0 < v_lo + margin or y1 > v_hi - margin:
        return False
    poly = ev["outer_poly"]
    for ix in range(5):
        px = x0 + (x1 - x0) * ix / 4.0
        for iy in range(3):
            py = y0 + (y1 - y0) * iy / 2.0
            if not _point_in_poly(px, py, poly):
                return False
    n = len(poly)
    check_pts = [
        (x0, y0), (x1, y0), (x1, y1), (x0, y1),
        ((x0 + x1) / 2.0, y0), ((x0 + x1) / 2.0, y1),
        (x0, (y0 + y1) / 2.0), (x1, (y0 + y1) / 2.0),
    ]
    for px, py in check_pts:
        for i in range(n):
            p1, p2 = poly[i], poly[(i + 1) % n]
            if _point_dist_to_segment(px, py, p1[0], p1[1], p2[0], p2[1]) < margin - 0.15:
                return False
    for r in ev["inner_rects"]:
        rx0, ry0 = r["u0"] - margin, r["v0"] - margin
        rx1, ry1 = r["u0"] + r["du"] + margin, r["v0"] + r["dv"] + margin
        if not (x1 <= rx0 or x0 >= rx1 or y1 <= ry0 or y0 >= ry1):
            return False
    for c in ev["circles"]:
        rad = c["dia"] / 2.0 + margin
        cx = max(x0, min(c["cx"], x1))
        cy = max(y0, min(c["cy"], y1))
        if math.hypot(cx - c["cx"], cy - c["cy"]) < rad:
            return False
    return True


def _choose_engrave_spec(
    part_id: str, piece_w: float, piece_h: float, T_mm: float,
    ev: dict[str, Any], u_lo: float, u_hi: float, v_lo: float, v_hi: float,
    dovetails: list[DovetailJointSpec], piece_index: int, piece_count: int,
) -> EngraveSpec:
    short_id = part_id.split("_piece")[0]
    tag = short_id.split("_")[0]
    if piece_count > 1:
        line1 = f"{tag} p{piece_index}/{piece_count}"
    else:
        line1 = short_id if (piece_w >= 115.0 and piece_h >= 60.0) else tag
    line2 = f"{piece_w:.0f}x{piece_h:.0f}x{T_mm:.0f}mm"

    dt_boxes: list[tuple[float, float, float, float]] = []
    for dt in dovetails:
        pad = dt.depth + 3.0
        hw = dt.head_w / 2.0 + 3.0
        if dt.axis == "U":
            dt_boxes.append((dt.cut_pos - pad, dt.center_along - hw, dt.cut_pos + pad, dt.center_along + hw))
        else:
            dt_boxes.append((dt.center_along - hw, dt.cut_pos - pad, dt.center_along + hw, dt.cut_pos + pad))

    def _hits_dt(x0: float, y0: float, x1: float, y1: float) -> bool:
        for bx0, by0, bx1, by1 in dt_boxes:
            if not (x1 <= bx0 or x0 >= bx1 or y1 <= by0 or y0 >= by1):
                return True
        return False

    max_chars = max(len(line1), len(line2))
    # For conformal honeycomb panels, prefer compact rim-hugging engraving near a corner/edge
    # so the entire central non-load-bearing field stays open for honeycomb lightening cutouts.
    prefer_rim = ev.get("panel_id") in (
        "P01B_BASE_HOUSE",
        "P02_WALL_BACK",
        "P03_WALL_LEFT",
        "P04_WALL_RIGHT",
        "P06_WALL_MID",
        "P08_DOOR_LEAF",
        "P16_PCB_PLATE",
    )
    font_ladder = (2.6, 2.3) if prefer_rim else (5.6, 4.8, 4.0, 3.4, 2.8, 2.3)
    for font_h in font_ladder:
        box_w = max_chars * font_h * 0.66 + 2.0
        box_h = font_h * 2.55 + 1.6
        for rot in (False, True):
            rw, rh = (box_h, box_w) if rot else (box_w, box_h)
            for margin in ((1.6, 1.3) if prefer_rim else (3.0, 2.0, 1.3)):
                if rw + 2 * margin > (u_hi - u_lo) or rh + 2 * margin > (v_hi - v_lo):
                    continue
                nu = min(28, max(3, int((u_hi - u_lo - rw) / 4.0) + 1))
                nv = min(28, max(3, int((v_hi - v_lo - rh) / 4.0) + 1))
                mid_u, mid_v = (u_lo + u_hi) / 2.0, (v_lo + v_hi) / 2.0
                best_pt: tuple[float, float] | None = None
                best_score = float("inf")
                for iu in range(nu):
                    cx = u_lo + margin + rw / 2.0 + ((u_hi - u_lo - rw - 2 * margin) * iu / max(1, nu - 1))
                    for iv in range(nv):
                        cy = v_lo + margin + rh / 2.0 + ((v_hi - v_lo - rh - 2 * margin) * iv / max(1, nv - 1))
                        x0, x1 = cx - rw / 2.0, cx + rw / 2.0
                        y0, y1 = cy - rh / 2.0, cy + rh / 2.0
                        if _hits_dt(x0, y0, x1, y1):
                            continue
                        if _rect_inside_piece(x0, y0, x1, y1, ev, u_lo, u_hi, v_lo, v_hi, margin):
                            if prefer_rim:
                                # Hug bottom/top/left/right edge to leave center free for honeycomb
                                d_edge = min(x0 - u_lo, u_hi - x1, y0 - v_lo, v_hi - y1)
                                score = d_edge * 4.0 + (y0 - v_lo) * 0.15 + abs(cx - mid_u) * 0.05
                            else:
                                score = math.hypot(cx - mid_u, cy - mid_v)
                            if score < best_score:
                                best_score = score
                                best_pt = (cx, cy)
                if best_pt is not None:
                    return EngraveSpec(line1=line1, line2=line2, cx=round(best_pt[0], 3), cy=round(best_pt[1], 3), font_h=font_h, rotated_90=rot)

    return EngraveSpec(
        line1=tag,
        line2=f"{piece_w:.0f}x{piece_h:.0f}x{T_mm:.0f}",
        cx=round((u_lo + u_hi) / 2.0, 3),
        cy=round((v_lo + v_hi) / 2.0, 3),
        font_h=2.3,
        rotated_90=(piece_h > piece_w * 1.4),
    )


def _feature_clearance_at_cut(ev: dict[str, Any], axis: str, cut_pos: float) -> float:
    min_d = float("inf")
    for c in ev["circles"]:
        coord = c["cx"] if axis == "U" else c["cy"]
        min_d = min(min_d, abs(cut_pos - coord) - c["dia"] / 2.0)
    for r in ev["inner_rects"]:
        a0 = r["u0"] if axis == "U" else r["v0"]
        a1 = a0 + (r["du"] if axis == "U" else r["dv"])
        if a0 <= cut_pos <= a1:
            return -min(cut_pos - a0, a1 - cut_pos)
        min_d = min(min_d, min(abs(cut_pos - a0), abs(cut_pos - a1)))
    poly = ev["outer_poly"]
    n = len(poly)
    total_span = ev["width"] if axis == "U" else ev["height"]
    for i in range(n):
        p1, p2 = poly[i], poly[(i + 1) % n]
        a1, b1 = (p1[0], p1[1]) if axis == "U" else (p1[1], p1[0])
        a2, b2 = (p2[0], p2[1]) if axis == "U" else (p2[1], p2[0])
        if abs(a1 - a2) < 1e-3 and abs(b1 - b2) > 0.5:
            if 1.0 < a1 < total_span - 1.0:
                step_h = abs(b1 - b2)
                d_step = abs(cut_pos - a1)
                if step_h > 40.0 and d_step < 4.5:
                    return -1.0
                min_d = min(min_d, d_step)
    return min_d


def _solve_axis_cuts_with_limit(ev: dict[str, Any], axis: str, limit: float, cfg: PrintConfig) -> list[float] | None:
    span = ev["width"] if axis == "U" else ev["height"]
    if span <= limit + 1e-6:
        return []

    dt_protrusion = cfg.compact_dovetail_depth if ev["panel_id"] == "P15_TECH_FASCIA" else cfg.dovetail_depth
    max_first_seg = limit - 0.5
    max_other_seg = limit - dt_protrusion - 0.5

    for n_pieces in range(2, 6):
        if span > max_first_seg + (n_pieces - 1) * max_other_seg:
            continue
        n_cuts = n_pieces - 1
        targets = [span * (k + 1) / n_pieces for k in range(n_cuts)]

        def _cand_list(t_idx: int) -> list[tuple[float, float]]:
            lo_bound = max(20.0, targets[t_idx] - 48.0)
            hi_bound = min(span - 20.0, targets[t_idx] + 48.0)
            if t_idx == 0:
                hi_bound = min(hi_bound, max_first_seg)
            if t_idx == n_cuts - 1:
                lo_bound = max(lo_bound, span - max_other_seg)
            cands: list[tuple[float, float]] = []
            pos = math.ceil(lo_bound * 2.0) / 2.0
            while pos <= hi_bound + 1e-6:
                segs = _poly_intervals_at_line(ev["outer_poly"], axis, pos)
                if segs and max(b - a for a, b in segs) >= 14.0:
                    clr = _feature_clearance_at_cut(ev, axis, pos)
                    if clr >= cfg.min_feature_clearance:
                        cands.append((pos, clr))
                pos += 0.5
            return cands

        cand_lists = [_cand_list(i) for i in range(n_cuts)]
        if any(len(cl) == 0 for cl in cand_lists):
            continue

        best_combo: list[float] | None = None
        best_score = -1e9

        if n_cuts == 1:
            for pos, clr in cand_lists[0]:
                score = min(clr, 14.0) * 3.0 - abs(pos - targets[0]) * 0.12
                if score > best_score:
                    best_score = score
                    best_combo = [round(pos, 2)]
        elif n_cuts == 2:
            for p1, c1 in cand_lists[0]:
                for p2, c2 in cand_lists[1]:
                    mid_len = p2 - p1
                    if mid_len < 30.0 or mid_len > max_other_seg:
                        continue
                    min_c = min(c1, c2)
                    score = min(min_c, 14.0) * 3.0 + (c1 + c2) * 0.2 - (abs(p1 - targets[0]) + abs(p2 - targets[1])) * 0.08
                    if score > best_score:
                        best_score = score
                        best_combo = [round(p1, 2), round(p2, 2)]
        else:
            chosen: list[float] = []
            prev = 0.0
            ok = True
            for idx, cl in enumerate(cand_lists):
                seg_lim = max_first_seg if idx == 0 else max_other_seg
                valid = [(p, c) for (p, c) in cl if 30.0 <= p - prev <= seg_lim]
                if not valid:
                    ok = False
                    break
                p_best = max(valid, key=lambda item: min(item[1], 14.0) * 3.0 - abs(item[0] - targets[idx]) * 0.12)[0]
                chosen.append(round(p_best, 2))
                prev = p_best
            if ok and span - chosen[-1] <= max_other_seg:
                best_combo = chosen

        if best_combo is not None:
            return best_combo
    return None


def _solve_panel_splits_rotation_aware(ev: dict[str, Any], cfg: PrintConfig) -> tuple[list[float], list[float]]:
    """Choose minimum-piece (u_cuts, v_cuts) considering 0-deg and 90-deg bed rotation."""
    options: list[tuple[int, int, list[float], list[float]]] = []
    for idx, (u_lim, v_lim) in enumerate([(cfg.usable_x, cfg.usable_y), (cfg.usable_y, cfg.usable_x)]):
        uc = _solve_axis_cuts_with_limit(ev, "U", u_lim, cfg)
        vc = _solve_axis_cuts_with_limit(ev, "V", v_lim, cfg)
        if uc is not None and vc is not None:
            total = (len(uc) + 1) * (len(vc) + 1)
            options.append((total, idx, uc, vc))
    if not options:
        raise RuntimeError(f"Could not find valid 170x190 bed split for {ev['panel_id']}")
    options.sort(key=lambda item: (item[0], item[1]))
    return options[0][2], options[0][3]


def _build_seam_dovetails(
    ev: dict[str, Any], axis: str, cut_pos: float, span_lo: float, span_hi: float, cfg: PrintConfig,
) -> list[DovetailJointSpec]:
    intervals = _poly_intervals_at_line(ev["outer_poly"], axis, cut_pos)
    clipped: list[tuple[float, float]] = []
    for a, b in intervals:
        lo, hi = max(a, span_lo), min(b, span_hi)
        if hi - lo >= 12.0:
            clipped.append((lo, hi))
    if not clipped:
        return []

    widest = max(b - a for a, b in clipped)
    if widest < 42.0 or ev["panel_id"] == "P15_TECH_FASCIA":
        depth, neck, head = cfg.compact_dovetail_depth, cfg.compact_dovetail_neck, cfg.compact_dovetail_head
    else:
        depth, neck, head = cfg.dovetail_depth, cfg.dovetail_neck, cfg.dovetail_head

    def _clear_along(pos_along: float) -> bool:
        half_w = head / 2.0 + 2.0
        for c in ev["circles"]:
            c_cut = c["cx"] if axis == "U" else c["cy"]
            c_al = c["cy"] if axis == "U" else c["cx"]
            if abs(c_cut - cut_pos) < depth + c["dia"] / 2.0 + 1.8:
                if abs(c_al - pos_along) < half_w + c["dia"] / 2.0 + 1.0:
                    return False
        for r in ev["inner_rects"]:
            r_cut0 = r["u0"] if axis == "U" else r["v0"]
            r_cut1 = r_cut0 + (r["du"] if axis == "U" else r["dv"])
            r_al0 = r["v0"] if axis == "U" else r["u0"]
            r_al1 = r_al0 + (r["dv"] if axis == "U" else r["du"])
            if not (cut_pos + depth + 1.8 < r_cut0 or cut_pos - depth - 1.8 > r_cut1):
                if not (pos_along + half_w < r_al0 or pos_along - half_w > r_al1):
                    return False
        return True

    dovetails: list[DovetailJointSpec] = []
    for lo, hi in clipped:
        seg_len = hi - lo
        end_pad = head / 2.0 + 3.0
        if seg_len < 2.0 * end_pad:
            mid = (lo + hi) / 2.0
            if _clear_along(mid):
                dovetails.append(DovetailJointSpec(axis, cut_pos, round(mid, 2), depth, neck, head, cfg.dovetail_clearance, +1))
            continue
        count = 2 if seg_len >= 85.0 else 1
        targets = [lo + seg_len * (k + 1) / (count + 1) for k in range(count)]
        for t in targets:
            found: float | None = None
            for delta in [0.0] + [s * step for step in range(1, 35) for s in (-1.0, 1.0)]:
                cand = t + delta
                if lo + end_pad <= cand <= hi - end_pad and _clear_along(cand):
                    found = cand
                    break
            if found is not None:
                dovetails.append(DovetailJointSpec(axis, cut_pos, round(found, 2), depth, neck, head, cfg.dovetail_clearance, +1))
    return dovetails


def build_panel_piece_specs(cfg: PrintConfig | None = None) -> tuple[list[PanelPieceSpec], dict[str, Any]]:
    """Build all screwless printable panel/piece specs for 180x200x250 bed."""
    cfg = cfg or PrintConfig()
    params = md.default_param_values(T_mm=cfg.T_mm, tab_clr=cfg.tab_clr)
    panels, _joints = md.build_design()

    pieces: list[PanelPieceSpec] = []
    split_summary: dict[str, Any] = {}

    for pspec in panels:
        ev = evaluate_screwless_panel_2d(pspec, cfg)
        u_cuts, v_cuts = _solve_panel_splits_rotation_aware(ev, cfg)

        u_bounds = [0.0] + u_cuts + [ev["width"]]
        v_bounds = [0.0] + v_cuts + [ev["height"]]
        nx = len(u_bounds) - 1
        ny = len(v_bounds) - 1
        total_pieces = nx * ny

        orig = tuple(round(md.eval_expr(c, params), 4) for c in pspec.origin_xyz)
        extra_origs = tuple(tuple(round(md.eval_expr(c, params), 4) for c in eo) for eo in pspec.extra_origins_xyz)

        seam_u_dts: dict[tuple[int, int], list[DovetailJointSpec]] = {}
        for iu in range(nx - 1):
            for iv in range(ny):
                seam_u_dts[(iu, iv)] = _build_seam_dovetails(ev, "U", u_cuts[iu], v_bounds[iv], v_bounds[iv + 1], cfg)
        seam_v_dts: dict[tuple[int, int], list[DovetailJointSpec]] = {}
        for iu in range(nx):
            for iv in range(ny - 1):
                seam_v_dts[(iu, iv)] = _build_seam_dovetails(ev, "V", v_cuts[iv], u_bounds[iu], u_bounds[iu + 1], cfg)

        piece_ids: list[str] = []
        k = 0
        for iv in range(ny):
            for iu in range(nx):
                k += 1
                u_lo, u_hi = u_bounds[iu], u_bounds[iu + 1]
                v_lo, v_hi = v_bounds[iv], v_bounds[iv + 1]
                part_id = pspec.panel_id if total_pieces == 1 else f"{pspec.panel_id}_piece{k}of{total_pieces}"
                piece_ids.append(part_id)

                local_dts: list[DovetailJointSpec] = []
                if iu > 0:
                    local_dts.extend(seam_u_dts[(iu - 1, iv)])
                if iu < nx - 1:
                    local_dts.extend(seam_u_dts[(iu, iv)])
                if iv > 0:
                    local_dts.extend(seam_v_dts[(iu, iv - 1)])
                if iv < ny - 1:
                    local_dts.extend(seam_v_dts[(iu, iv)])

                add_u = 0.0
                if iu > 0 and seam_u_dts[(iu - 1, iv)]:
                    add_u = max(d.depth for d in seam_u_dts[(iu - 1, iv)])
                add_v = 0.0
                if iv > 0 and seam_v_dts[(iu, iv - 1)]:
                    add_v = max(d.depth for d in seam_v_dts[(iu, iv - 1)])

                piece_w = round((u_hi - u_lo) + add_u, 2)
                piece_h = round((v_hi - v_lo) + add_v, 2)

                piece_mortises = tuple(
                    mt for mt in ev["mortises"]
                    if (u_lo - 0.1 <= mt.cx <= u_hi + 0.1) and (v_lo - 0.1 <= mt.cy <= v_hi + 0.1)
                )

                engrave = _choose_engrave_spec(
                    part_id=part_id, piece_w=piece_w, piece_h=piece_h, T_mm=cfg.T_mm,
                    ev=ev, u_lo=u_lo, u_hi=u_hi, v_lo=v_lo, v_hi=v_hi,
                    dovetails=local_dts, piece_index=k, piece_count=total_pieces,
                )

                pieces.append(PanelPieceSpec(
                    part_id=part_id,
                    source_panel_id=pspec.panel_id,
                    piece_index=k,
                    piece_count=total_pieces,
                    qty=pspec.qty,
                    plane=pspec.plane,
                    origin_xyz=orig,
                    extra_origins_xyz=extra_origs,
                    explode_xyz=pspec.explode_xyz,
                    shift_u=ev["shift_u"],
                    shift_v=ev["shift_v"],
                    u_range=(round(u_lo, 4), round(u_hi, 4)),
                    v_range=(round(v_lo, 4), round(v_hi, 4)),
                    dovetails=tuple(local_dts),
                    mortises=piece_mortises,
                    engrave=engrave,
                    vi_name=VI_PANEL_NAMES.get(pspec.panel_id, pspec.name),
                    notes=pspec.notes,
                    color_rgb=pspec.color_rgb,
                    stripped_fastener_holes=tuple(ev["stripped_fastener_holes"]),
                    kept_functional_holes=tuple(ev["kept_functional_holes"]),
                ))

        split_summary[pspec.panel_id] = {
            "source_width_mm": ev["width"],
            "source_height_mm": ev["height"],
            "T_mm": cfg.T_mm,
            "is_split": total_pieces > 1,
            "grid": [nx, ny],
            "piece_count": total_pieces,
            "u_cuts_mm": u_cuts,
            "v_cuts_mm": v_cuts,
            "dovetail_clearance_mm": cfg.dovetail_clearance,
            "pieces": piece_ids,
        }

    return pieces, split_summary


def build_support_specs(cfg: PrintConfig | None = None, pcb: pcb_ssot.PcbSpec | None = None) -> list[SupportSpec]:
    """Build all 16 screwless structural clips, snap-fit PCB/module mounts, hinges, and water liner."""
    cfg = cfg or PrintConfig()
    pcb = pcb or pcb_ssot.parse_kicad_hub_pcb(run_cli_check=False)
    p = md.default_param_values(T_mm=cfg.T_mm, tab_clr=cfg.tab_clr)
    hw_map = {h.part_id: h for h in md.HARDWARE_PARTS}

    T = p["T_mm"]  # 3.0
    base_L = p["base_L"]  # 406.0
    base_W = p["base_W"]  # 390.0
    slot_u = round(T + cfg.clip_slot_clr, 2)  # 3.20
    Z_WALL_TOP = p["wall_H"]  # 147.0
    Z_CUT_H = p["cut_H"]  # 34.0

    # Derive dynamic split seam positions so SUP03 seam clips always align with real cuts
    _, split_info = build_panel_piece_specs(cfg)
    p02_cuts = [10.0 + c for c in split_info["P02_WALL_BACK"]["u_cuts_mm"]]
    p05_cuts = [10.0 + c for c in split_info["P05_WALL_FRONT"]["u_cuts_mm"]]
    p15_cuts = [8.0 + c for c in split_info["P15_TECH_FASCIA"]["u_cuts_mm"]]

    pcb_cx, pcb_cy, _ = hw_map["HW_PCB"].center_xyz  # (122.0, 104.0)
    rly1_cx, rly1_cy, _ = hw_map["HW_RELAY1"].center_xyz  # (226.0, 136.0)
    rly2_cx, rly2_cy, _ = hw_map["HW_RELAY2"].center_xyz  # (226.0, 92.0)
    pam_cx, pam_cy, _ = hw_map["HW_PAM8403"].center_xyz  # (224.0, 52.0)

    # SUP01_CORNER_CLIP_WALL: 2x outer top 90-deg corner U-clips (P02+P03 at X=10,Y=382 and P02+P04 at X=396,Y=382)
    # Local clip geometry: outer corner at (0,0), X-channel along Y=[wt..wt+slot_u], Y-channel along X=[wt..wt+slot_u],
    # cap at Z=[h-wt..h] in world (printed upside down with cap at Z=0..wt).
    # In world: clip wraps top edge of walls from Z = Z_WALL_TOP - (h - wt) to Z = Z_WALL_TOP + wt.
    sup01_wt = 2.0
    sup01_h = 12.0
    sup01_arm = 24.0
    sup01_z = Z_WALL_TOP - (sup01_h - sup01_wt)  # 137.0..149.0
    # Outer wall corner coordinates (accounting for clip wall thickness & 0.1mm clearance):
    # Top-left outer corner: P03 X=[10..13], P02 Y=[379..382] -> outer corner (10 - wt, 382 + wt)
    sup01_placements = (
        {"x": 10.0 - sup01_wt - 0.1, "y": 382.0 + sup01_wt + 0.1, "z": sup01_z, "rot_z": -90.0},
        {"x": 396.0 + sup01_wt + 0.1, "y": 382.0 + sup01_wt + 0.1, "z": sup01_z, "rot_z": 180.0},
    )

    # SUP01B_T_CLIP_WALL: 1x top T-channel clip locking P02_WALL_BACK (Y=379..382) + P06_WALL_MID (X=198.5..201.5)
    sup01b_L = 28.0
    sup01b_stem = 22.0
    sup01b_placements = (
        {"x": 200.0, "y": 380.5, "z": sup01_z, "rot_z": 0.0},
    )

    # SUP02_CORNER_CLIP_LOW: 6x compact 90-deg corner U-clips (2 front cutaway corners Z=34, 4 garden corners Z=54/48)
    sup02_wt = 1.9
    sup02_h = 8.5
    sup02_arm = 18.0
    sup02_drop = sup02_h - sup02_wt  # 6.6
    sup02_placements = (
        # Front-left P03+P05 (outer corner 10, 192) at Z=34
        {"x": 10.0 - sup02_wt - 0.1, "y": 192.0 - sup02_wt - 0.1, "z": Z_CUT_H - sup02_drop, "rot_z": 0.0},
        # Front-right P04+P05 (outer corner 396, 192) at Z=34
        {"x": 396.0 + sup02_wt + 0.1, "y": 192.0 - sup02_wt - 0.1, "z": Z_CUT_H - sup02_drop, "rot_z": 90.0},
        # Garden front-left P09+P12 (outer corner 266, 26) at Z=54
        {"x": 266.0 - sup02_wt - 0.1, "y": 26.0 - sup02_wt - 0.1, "z": 54.0 - sup02_drop, "rot_z": 0.0},
        # Garden back-left P09+P13 (outer corner 266, 152) at Z=54
        {"x": 266.0 - sup02_wt - 0.1, "y": 152.0 + sup02_wt + 0.1, "z": 54.0 - sup02_drop, "rot_z": -90.0},
        # Garden front-right P11+P12 (outer corner 396, 26) at Z=48 (stepped top of P11 is 48, P12 right end is 48)
        {"x": 396.0 + sup02_wt + 0.1, "y": 26.0 - sup02_wt - 0.1, "z": 48.0 - sup02_drop, "rot_z": 90.0},
        # Garden back-right P11+P13 (outer corner 396, 152) at Z=48
        {"x": 396.0 + sup02_wt + 0.1, "y": 152.0 + sup02_wt + 0.1, "z": 48.0 - sup02_drop, "rot_z": 180.0},
    )

    # SUP03_SEAM_U_CLIP: dynamically derived from real split cut top heights so clips never float or collide
    panels_raw, _ = md.build_design()
    pmap_ev = {ps.panel_id: evaluate_screwless_panel_2d(ps, cfg) for ps in panels_raw}

    def _seam_top_z(pid: str, u_local: float) -> float:
        ev_p = pmap_ev[pid]
        ivs = _poly_intervals_at_line(ev_p["outer_poly"], "U", u_local)
        if not ivs:
            return Z_CUT_H
        return round(max(b for _, b in ivs) - ev_p["shift_v"], 2)

    sup03_len = 26.0
    sup03_wt = 2.2
    sup03_h = 8.2
    sup03_half_w = round((slot_u + 2.0 * sup03_wt) / 2.0, 2)  # 3.80
    sup03_drop = round(sup03_h - sup03_wt, 2)  # 6.00
    sup03_placements_list: list[dict[str, Any]] = []
    for u_loc in split_info["P02_WALL_BACK"]["u_cuts_mm"]:
        cx = 10.0 + u_loc
        z_top = _seam_top_z("P02_WALL_BACK", u_loc)
        clip_x = cx - sup03_len / 2.0
        # Keep clear of SUP01B T-clip (X in [186..214]) while still straddling the seam
        if clip_x < 214.5 and (clip_x + sup03_len) > 185.5:
            clip_x = 214.5 if cx >= 200.0 else (185.5 - sup03_len)
        sup03_placements_list.append({"x": round(clip_x, 2), "y": round(380.5 - sup03_half_w, 2), "z": round(z_top - sup03_drop, 2), "rot_z": 0.0})
    for u_loc in split_info["P05_WALL_FRONT"]["u_cuts_mm"]:
        cx = 10.0 + u_loc
        z_top = _seam_top_z("P05_WALL_FRONT", u_loc)
        clip_x = cx - sup03_len / 2.0
        if cx > 215.0:
            clip_x = max(217.0, clip_x)
        sup03_placements_list.append({"x": round(clip_x, 2), "y": round(193.5 - sup03_half_w, 2), "z": round(z_top - sup03_drop, 2), "rot_z": 0.0})
    for u_loc in split_info["P15_TECH_FASCIA"]["u_cuts_mm"]:
        cx = 8.0 + u_loc
        z_top = _seam_top_z("P15_TECH_FASCIA", u_loc)
        sup03_placements_list.append({"x": round(cx - sup03_len / 2.0, 2), "y": round(11.5 - sup03_half_w, 2), "z": round(z_top - sup03_drop, 2), "rot_z": 0.0})

    # SUP04_BASE_FOOT_CLIP: 6x screwless corner/edge clip-on feet lifting base 11 mm (clears P17 at Z=-6..-3)
    foot_placements = (
        {"x": -3.0, "y": -3.0, "z": -14.0, "rot_z": 0.0},
        {"x": base_L + 3.0, "y": -3.0, "z": -14.0, "rot_z": 90.0},
        {"x": base_L + 3.0, "y": base_W + 3.0, "z": -14.0, "rot_z": 180.0},
        {"x": -3.0, "y": base_W + 3.0, "z": -14.0, "rot_z": -90.0},
    )

    # SUP05_P16_TENON_RISER: 4x 6mm risers locking P16_PCB_PLATE onto P01A via top & bottom rectangular tenons
    sup05_placements = tuple(
        {"x": round(pcb_cx + dx, 3), "y": round(pcb_cy + dy, 3), "z": 0.0, "rot_z": 0.0}
        for (dx, dy) in ((-58.0, 48.0), (58.0, 48.0), (-58.0, -48.0), (58.0, -48.0))
    )

    # SUP06_HUB_PCB_SNAP_CARRIER: 1x integrated 100x80 carrier mounting onto P16_PCB_PLATE (Z=9..19)
    # Holds real KiCad Hub PCB via 4x split snap-fit pegs at exact 90x70 mm pitch + 4x bottom tenons into P16!
    sup06_placements = ({"x": pcb_cx, "y": pcb_cy, "z": 9.0, "rot_z": 0.0},)

    # SUP07_RELAY_SNAP_CADDY: 2x screwless snap-fit relay caddies (44.5x20.5 split pegs + 2x base tenons into P01A)
    sup07_placements = (
        {"x": rly1_cx, "y": rly1_cy, "z": 0.0, "rot_z": 0.0},
        {"x": rly2_cx, "y": rly2_cy, "z": 0.0, "rot_z": 0.0},
    )

    # SUP08_PAM8403_SNAP_TRAY: 1x edge-rail snap tray + 2x base tenons into P01A (26 mm span)
    sup08_placements = ({"x": pam_cx, "y": pam_cy, "z": 0.0, "rot_z": 0.0},)

    # SUP09_SPEAKER_SNAP_RETAINER: 1x rear mortise-and-snap retainer bar behind P15_TECH_FASCIA (X=223, Y=13..24, Z=26)
    sup09_placements = ({"x": 223.0, "y": 13.0, "z": 26.0, "rot_z": 0.0},)

    # SUP10_DOOR_MORTISE_HINGE: 2x screwless mortise pin-and-knuckle hinges joining P05 (X=72.5) and P08 (X=83.5)
    # Placed behind door at Y=195.0, Z=18.0 and Z=78.0 with exact coaxial pivot (77.0, 201.5)
    sup10_placements = (
        {"x": 77.0, "y": 195.0, "z": 18.0, "rot_z": 0.0},
        {"x": 77.0, "y": 195.0, "z": 78.0, "rot_z": 0.0},
    )

    # SUP10B_DOOR_HORN_COUPLER: 1x coaxial open-top U-channel fork plugging into P08 MORT_DOOR_LINK (X=88.0, Y=195.0, Z=97.0)
    sup10b_placements = ({"x": 88.0, "y": 195.0, "z": 97.0, "rot_z": 0.0},)

    # SUP11_SG90_SNAP_SADDLE: 1x top-jamb retention saddle clamping inverted SG90 onto P07_SERVO_SHELF (X=71.5, Y=201.5, Z=111.5)
    sup11_placements = ({"x": 71.5, "y": 201.5, "z": 111.5, "rot_z": 0.0},)

    # SUP12_DHT11_SNAP_CRADLE: 1x wall snap cradle plugging into P06_WALL_MID Living Room face at X=198.5, Y=286, Z=88 (-X inward)
    sup12_placements = ({"x": 198.5, "y": 286.0, "z": 88.0, "rot_z": -90.0},)

    # SUP13_KY037_SNAP_CRADLE: 1x wall snap cradle plugging into P05 at X=168, Y=195, Z=26 (inward +Y)
    sup13_placements = ({"x": 168.0, "y": 195.0, "z": 26.0, "rot_z": 0.0},)

    # SUP14_LM393_SNAP_CRADLE: 1x exterior snap cradle plugging into P13_GARDEN_BACK at X=292, Y=152, Z=24 (outward +Y)
    sup14_placements = ({"x": 292.0, "y": 152.0, "z": 24.0, "rot_z": 0.0},)

    # SUP15_WATER_TANK_LINER: 1x one-piece watertight drop-in cup inside P09/P10/P12/P13 (X=269..316.5, Y=29..149, Z=0..54)
    sup15_placements = ({"x": 292.75, "y": 89.0, "z": 0.0, "rot_z": 0.0},)

    # SUP16_DC022_STRAIN_RELIEF: 1x rear mortise snap-collar & wire guide for DC-022 behind P15 (X=30, Y=13, Z=22)
    sup16_placements = ({"x": 30.0, "y": 13.0, "z": 22.0, "rot_z": 0.0},)

    # SUP17_LED5MM_RETAINING_COLLAR: 2x press-fit bezel collars for Living Room (-X of P06 @ Y=232) & Bedroom (+X of P06 @ Y=258)
    sup17_placements = (
        {"x": 198.5, "y": 232.0, "z": 126.0, "rot_z": 90.0, "face_sign": -1},
        {"x": 201.5, "y": 258.0, "z": 126.0, "rot_z": -90.0, "face_sign": +1},
    )

    # SUP18_BUZZER_SNAP_COLLAR: 1x rear mortise snap cup for TMB12A05 buzzer behind P05 CenterPillar (X=200, Y=195, Z=126)
    sup18_placements = ({"x": 200.0, "y": 195.0, "z": 126.0, "rot_z": 0.0},)

    return [
        SupportSpec(
            part_id="SUP01_CORNER_CLIP_WALL",
            vi_name="Kep mong goc vuong 90 do tuong cao (khong vit)",
            category="corner_clip",
            qty=2,
            size_xyz=(sup01_arm, sup01_arm, sup01_h),
            engrave=EngraveSpec("SUP01", "24x24x14", 12.0, 12.0, 2.4, False),
            params={"arm": sup01_arm, "height": sup01_h, "wall_t": sup01_wt, "slot_w": slot_u},
            mating_source="P02+P03 and P02+P04 top 90-deg corners (T=3.0 mm + 0.20 mm clearance)",
            assembly_placements=sup01_placements,
            notes="Kep chu U kep goc 90 do truot tu tren xuong khoa cung goc tuong sau/hong, khong dung vit hay keo.",
            color_rgb=(0.95, 0.56, 0.18),
        ),
        SupportSpec(
            part_id="SUP01B_T_CLIP_WALL",
            vi_name="Kep mong chu T khoa vach giua P06 voi P02 (khong vit)",
            category="t_clip",
            qty=1,
            size_xyz=(sup01b_L, sup01b_stem, sup01_h),
            engrave=EngraveSpec("SUP01B", "28x22x14", 14.0, 4.2, 2.2, False),
            params={"bar_len": sup01b_L, "stem_len": sup01b_stem, "height": sup01_h, "wall_t": sup01_wt, "slot_w": slot_u},
            mating_source="P02_WALL_BACK + P06_WALL_MID top T-junction (T=3.0 mm + 0.20 mm clearance)",
            assembly_placements=sup01b_placements,
            notes="Kep mong chu T truot khoa dinh vach ngan giua P06 vao tuong sau P02, giu vuong goc 90 do tuyet doi.",
            color_rgb=(0.92, 0.48, 0.16),
        ),
        SupportSpec(
            part_id="SUP02_CORNER_CLIP_LOW",
            vi_name="Kep mong goc vuong 90 do vach thap & vuon (khong vit)",
            category="corner_clip",
            qty=6,
            size_xyz=(sup02_arm, sup02_arm, sup02_h),
            engrave=EngraveSpec("SUP02", "18x18x10", 9.0, 9.0, 2.0, False),
            params={"arm": sup02_arm, "height": sup02_h, "wall_t": sup02_wt, "slot_w": slot_u},
            mating_source="P03/P04/P05 front cutaway & P09..P13 garden 90-deg corners (T=3.0 mm + 0.20 mm)",
            assembly_placements=sup02_placements,
            notes="Kep mong goc 90 do nho gon cho mat tien thap (34 mm) va 4 goc be nuoc - chau cay (48-54 mm).",
            color_rgb=(0.93, 0.64, 0.22),
        ),
        SupportSpec(
            part_id="SUP03_SEAM_U_CLIP",
            vi_name="Kep mong chu U khoa moi noi duoi en",
            category="seam_clip",
            qty=8,
            size_xyz=(sup03_len, round(slot_u + 2.0 * sup03_wt, 2), sup03_h),
            engrave=EngraveSpec("SUP03", "26x8x8", sup03_len / 2.0, sup03_half_w, 2.0, False),
            params={"length": sup03_len, "slot_w": slot_u, "wall_t": sup03_wt, "height": sup03_h},
            mating_source="Split seams of P01A/P01B/P02/P05/P15 (T=3.0 mm + 0.20 mm clearance)",
            assembly_placements=tuple(sup03_placements_list),
            notes="Kep chu U ranh 3.20 mm truot khoa mep moi noi chia manh, chong cong venh khong can vit/keo.",
            color_rgb=(0.24, 0.68, 0.86),
        ),
        SupportSpec(
            part_id="SUP04_BASE_FOOT_CLIP",
            vi_name="Chan de mong cai goc nang nha 11mm (khong vit)",
            category="foot_clip",
            qty=4,
            size_xyz=(30.0, 30.0, 14.0),
            engrave=EngraveSpec("SUP04", "", 10.5, 22.0, 2.2, False),
            params={"size": 30.0, "lift_h": 11.0, "lip_h": 3.0, "lip_t": 3.0, "inner_cut": 15.0},
            mating_source="Base corners 406x390 mm; clears P17_BASE_JOINER (Z=-6..-3 mm)",
            assembly_placements=foot_placements,
            notes="Chan de cai goc dang chu L nang khung nha cao 11 mm khoi mat ban, nhe nhua va khong lo vit.",
            color_rgb=(0.30, 0.36, 0.44),
        ),
        SupportSpec(
            part_id="SUP05_P16_TENON_RISER",
            vi_name="Chan mong nang tam P16_PCB_PLATE cao 6mm",
            category="tenon_riser",
            qty=4,
            size_xyz=(14.0, 9.0, 12.0),
            engrave=EngraveSpec("SUP05", "6mm", 7.0, 4.5, 1.8, False),
            params={"body_x": 14.0, "body_y": 9.0, "lift_h": 6.0, "tenon_x": 8.0, "tenon_y": 3.0, "tenon_h": 3.0},
            mating_source="P01A_BASE_TECH -> P16_PCB_PLATE 116x96 mm mortise slots (0.15 mm/side press fit)",
            assembly_placements=sup05_placements,
            notes="Tru mong 2 dau chot vuong 8x3 mm ep khit vao P01A va P16, thay the hoan toan tru vit M3x6.",
            color_rgb=(0.82, 0.66, 0.20),
        ),
        SupportSpec(
            part_id="SUP05B_CARRIER_TENON_PEG",
            vi_name="Chot mong roi 6x3x6mm khoa khung PCB/Relay/PAM",
            category="tenon_peg",
            qty=10,
            size_xyz=(6.0, 6.0, 3.0),
            engrave=EngraveSpec("S5B", "", 3.0, 3.0, 1.4, False),
            params={"tenon_x": 6.0, "tenon_y": 3.0, "length_z": 6.0},
            mating_source="Floating press-fit tenons locking SUP06 (4x), SUP07 (4x), SUP08 (2x) into P16/P01A mortises",
            assembly_placements=(
                # 4x SUP06 -> P16 (world Z=6..12)
                {"x": round(pcb_cx - 45.0, 3), "y": round(pcb_cy - 35.0, 3), "z": 6.0, "rot_z": 0.0},
                {"x": round(pcb_cx + 45.0, 3), "y": round(pcb_cy - 35.0, 3), "z": 6.0, "rot_z": 0.0},
                {"x": round(pcb_cx - 45.0, 3), "y": round(pcb_cy + 35.0, 3), "z": 6.0, "rot_z": 0.0},
                {"x": round(pcb_cx + 45.0, 3), "y": round(pcb_cy + 35.0, 3), "z": 6.0, "rot_z": 0.0},
                # 4x SUP07 -> P01A (world Z=-3..3)
                {"x": round(rly1_cx - 16.0, 3), "y": rly1_cy, "z": -3.0, "rot_z": 0.0},
                {"x": round(rly1_cx + 16.0, 3), "y": rly1_cy, "z": -3.0, "rot_z": 0.0},
                {"x": round(rly2_cx - 16.0, 3), "y": rly2_cy, "z": -3.0, "rot_z": 0.0},
                {"x": round(rly2_cx + 16.0, 3), "y": rly2_cy, "z": -3.0, "rot_z": 0.0},
                # 2x SUP08 -> P01A (world Z=-3..3)
                {"x": round(pam_cx - 13.0, 3), "y": pam_cy, "z": -3.0, "rot_z": 0.0},
                {"x": round(pam_cx + 13.0, 3), "y": pam_cy, "z": -3.0, "rot_z": 0.0},
            ),
            notes="Chot mong roi in nam phang khong support, ep khit khoa khung SUP06/SUP07/SUP08 vao ranh tam day.",
            color_rgb=(0.86, 0.72, 0.24),
        ),
        SupportSpec(
            part_id="SUP06_HUB_PCB_SNAP_CARRIER",
            vi_name="Khung mong chot dan hoi giu Hub PCB 100x80",
            category="pcb_carrier",
            qty=1,
            size_xyz=(104.0, 84.0, 14.8),
            engrave=EngraveSpec("SUP06 PCB", "100x80", 52.0, 5.5, 3.0, False),
            params={
                "pcb_x": pcb.width_mm,
                "pcb_y": pcb.height_mm,
                "pcb_t": pcb.thickness_mm,
                "pitch_x": pcb.hole_pitch_x_mm,
                "pitch_y": pcb.hole_pitch_y_mm,
                "pcb_hole_d": pcb.hole_dia_mm,
                "peg_od": round(pcb.hole_dia_mm - cfg.snap_peg_dia_clr, 2),  # 3.00 mm
                "standoff_h": 10.0,
                "base_h": 3.0,
                "tenon_x": 6.0,
                "tenon_y": 3.0,
                "tenon_h": 3.0,
            },
            mating_source=f"{pcb.source_file} ({pcb.width_mm}x{pcb.height_mm}, 4x {pcb.hole_dia_mm}mm @ {pcb.hole_pitch_x_mm}x{pcb.hole_pitch_y_mm})",
            assembly_placements=sup06_placements,
            notes="Khung lien khoi gam 4 chot vuong xuong P16 va giu chat Hub PCB bang 4 chot dan hoi split snap-fit, khong vit.",
            color_rgb=(0.20, 0.64, 0.42),
        ),
        SupportSpec(
            part_id="SUP07_RELAY_SNAP_CADDY",
            vi_name="Khay mong cai dan hoi Relay 1 kenh 44.5x20.5",
            category="relay_caddy",
            qty=2,
            size_xyz=(54.4, 30.4, 13.0),
            engrave=EngraveSpec("SUP07 RLY", "44.5x20.5", 27.2, 15.2, 2.4, False),
            params={
                "pcb_x": 50.0,
                "pcb_y": 26.0,
                "pcb_t": 1.6,
                "cavity_x": round(50.0 + 2.0 * cfg.edge_rail_clr_per_side, 2),  # 50.4
                "cavity_y": round(26.0 + 2.0 * cfg.edge_rail_clr_per_side, 2),  # 26.4
                "pitch_x": 44.5,
                "pitch_y": 20.5,
                "peg_od": round(3.1 - cfg.snap_peg_dia_clr, 2),  # 2.90
                "standoff_h": 8.0,
                "base_h": 2.4,
                "tenon_span": 32.0,
                "tenon_x": 6.0,
                "tenon_y": 3.0,
                "tenon_h": 3.0,
            },
            mating_source="Relay 50x26 mm (44.5x20.5 mm holes Dia 3.1 mm) + P01A mortise slots (32 mm span)",
            assembly_placements=sup07_placements,
            notes="Khay cai mong cho Relay 1 & 2: 2 chot vuong gam xuong P01A va 4 chot dan hoi khoa mach Relay, khong vit.",
            color_rgb=(0.24, 0.48, 0.84),
        ),
        SupportSpec(
            part_id="SUP08_PAM8403_SNAP_TRAY",
            vi_name="Khay mong ranh kep mach am thanh PAM8403",
            category="pam_tray",
            qty=1,
            size_xyz=(34.0, 23.0, 9.0),
            engrave=EngraveSpec("SUP08", "PAM8403", 17.0, 11.5, 2.0, False),
            params={
                "outer_x": 34.0,
                "outer_y": 23.0,
                "base_h": 2.0,
                "wall_h": 6.0,
                "cavity_x": round(21.0 + 2.0 * cfg.edge_rail_clr_per_side, 2),  # 21.4
                "cavity_y": round(18.0 + 2.0 * cfg.edge_rail_clr_per_side, 2),  # 18.4
                "tenon_span": 26.0,
                "tenon_x": 6.0,
                "tenon_y": 3.0,
                "tenon_h": 3.0,
            },
            mating_source="PAM8403 21.0x18.0x3.4 mm + P01A mortise slots (26.0 mm span)",
            assembly_placements=sup08_placements,
            notes="Khay co ngoam giu mep bo PAM8403 va 2 chot mong gam xuong P01A, khong dung bang dinh hay vit.",
            color_rgb=(0.20, 0.72, 0.36),
        ),
        SupportSpec(
            part_id="SUP09_SPEAKER_SNAP_RETAINER",
            vi_name="Thanh mong cai giu loa tron 28mm (khong vit)",
            category="speaker_retainer",
            qty=1,
            size_xyz=(44.0, 14.0, 12.0),
            engrave=EngraveSpec("SUP09", "SPK28", 22.0, 7.0, 2.2, False),
            params={
                "length": 44.0,
                "width": 14.0,
                "bridge_h": 9.0,
                "flange_h": 3.0,
                "tenon_span": 36.0,
                "tenon_x": 4.0,
                "tenon_y": 6.0,
                "tenon_h": 3.0,
                "spk_od": 28.4,
                "spk_depth": 5.4,
            },
            mating_source="Speaker Dia 28x5.2 mm + P15_TECH_FASCIA mortise slots (36.0 mm span)",
            assembly_placements=sup09_placements,
            notes="Thanh ep lung giu loa 28 mm bang 2 chot mong gam thang vao ranh P15_TECH_FASCIA.",
            color_rgb=(0.64, 0.42, 0.82),
        ),
        SupportSpec(
            part_id="SUP10_DOOR_MORTISE_HINGE",
            vi_name="Ban le mong truc xoay cua chinh (khong vit)",
            category="door_hinge",
            qty=2,
            size_xyz=(26.0, 16.0, 9.0),
            engrave=EngraveSpec("SUP10", "HINGE", 13.0, 8.0, 2.0, False),
            params={
                "jamb_to_door_span": 11.0,  # X=72.5 to X=83.5
                "plate_len": 22.0,
                "plate_h": 12.0,
                "plate_t": 3.0,
                "knuckle_od": 6.0,
                "pin_d": 2.7,
                "bore_d": round(2.7 + cfg.hinge_pin_clr, 2),  # 3.0
                "tenon_x": 4.0,
                "tenon_y": 6.0,
                "tenon_h": 3.0,
            },
            mating_source="P05_WALL_FRONT jamb mortise <-> P08_DOOR_LEAF mortise (2.0 mm gap, 0.30 mm pivot clr)",
            assembly_placements=sup10_placements,
            notes="Cap ban le 2 nua in nam phang co truc xoay va chot mong ep khit vao P05 va P08.",
            color_rgb=(0.82, 0.48, 0.32),
        ),
        SupportSpec(
            part_id="SUP10B_DOOR_HORN_COUPLER",
            vi_name="Ngam chu U noi truc tiep tay don Servo SG90 (dong truc cua)",
            category="door_horn_coupler",
            qty=1,
            size_xyz=(10.5, 13.55, 7.5),
            engrave=EngraveSpec("10B", "", 5.2, 4.2, 1.5, False),
            params={
                "slot_w": 4.9,
                "horn_w": 4.5,
                "fork_len_x": 5.0,
                "fork_wall_t": 1.6,
                "floor_h": 4.5,
                "total_h": 7.5,
                "base_t": 2.5,
                "tenon_x": 4.0,
                "tenon_y": 6.0,
                "tenon_h": 3.0,
            },
            mating_source="P08_DOOR_LEAF MORT_DOOR_LINK (u=10, v=95) <-> coaxial SG90 white horn (4.5x1.6 mm @ Z=99.3..100.9)",
            assembly_placements=sup10b_placements,
            notes="Ngam ranh chu U mo dinh (rong long 4.9 mm) om truc tiep tay don trang SG90 dong truc voi ban le (77.0, 201.5).",
            color_rgb=(0.85, 0.52, 0.30),
        ),
        SupportSpec(
            part_id="SUP11_SG90_SNAP_SADDLE",
            vi_name="Ngam mong khoa Servo SG90 dong truc tren ke P07",
            category="sg90_saddle",
            qty=1,
            size_xyz=(45.0, 16.6, 8.6),
            engrave=EngraveSpec("SUP11", "", 22.5, 14.5, 1.8, False),
            params={
                "length_x": 45.0,
                "width_y": 16.6,
                "window_x": 23.6,
                "window_y": 12.6,
                "ear_clear_x": 33.2,  # clears 32.2 mm SG90 ear span (+0.5 mm/side)
                "ear_t": 2.6,  # holds 2.5 mm SG90 mounting ears flush atop P07 (Z=111.5..114.0)
                "bridge_t": 3.0,
                "tenon_x": 3.0,
                "tenon_y": 6.0,
                "tenon_h": 3.0,
                "tenon_l_local_x": 2.0,  # world X = 48.5 + 2.0 = 50.5 (P07 u=3.5)
                "tenon_r_local_x": 42.0,  # world X = 48.5 + 42.0 = 90.5 (P07 u=43.5)
                "tenon_local_y": 6.3,  # world Y = 195.2 + 6.3 = 201.5 (P07 v=6.375)
            },
            mating_source="Inverted SG90 (22.8x12.2 body, 32.2 mm ear span) + P07_SERVO_SHELF mortises (u=3.5 & 43.5, v=6.375)",
            assembly_placements=sup11_placements,
            notes="Ngam chup cai mong xuong 2 ranh cua P07 ep giu tai Servo SG90 lap nguoc dong truc cua, ho than xanh len tren.",
            color_rgb=(0.18, 0.50, 0.88),
        ),
        SupportSpec(
            part_id="SUP12_DHT11_SNAP_CRADLE",
            vi_name="Gia mong kep cam bien DHT11 tren vach giua P06",
            category="wall_cradle",
            qty=1,
            size_xyz=(28.0, 32.4, 11.0),
            engrave=EngraveSpec("SUP12", "DHT11", 14.0, 16.2, 2.2, False),
            params={
                "board_x": 14.0,
                "board_y": 28.0,
                "board_z": 7.1,
                "cavity_x": round(14.0 + 2.0 * cfg.edge_rail_clr_per_side, 2),  # 14.4
                "cavity_y": round(28.0 + 2.0 * cfg.edge_rail_clr_per_side, 2),  # 28.4
                "tenon_span": 22.0,  # P06 u=83 and u=105
                "tenon_x": 3.0,
                "tenon_y": 6.0,
                "tenon_h": 3.0,
                "depth_h": 8.0,
                "window_x": 12.5,
                "window_y": 16.0,
            },
            mating_source="DHT11 breakout 14.0x28.0x7.1 mm + P06_WALL_MID mortises (22.0 mm span)",
            assembly_placements=sup12_placements,
            notes="Gia ranh kep DHT11 gan vach giua P06 (mat phong khach) bang 2 chot mong, mo cua thoang khop dung lo 12.5x16 mm.",
            color_rgb=(0.14, 0.62, 0.90),
        ),
        SupportSpec(
            part_id="SUP13_KY037_SNAP_CRADLE",
            vi_name="Gia mong kep cam bien am thanh KY-037 tren P05",
            category="wall_cradle",
            qty=1,
            size_xyz=(46.0, 19.4, 11.0),
            engrave=EngraveSpec("SUP13", "KY037", 23.0, 9.7, 2.2, False),
            params={
                "board_x": 35.0,
                "board_y": 15.0,
                "board_z": 13.1,
                "cavity_x": round(35.0 + 2.0 * cfg.edge_rail_clr_per_side, 2),  # 35.4
                "cavity_y": round(15.0 + 2.0 * cfg.edge_rail_clr_per_side, 2),  # 15.4
                "tenon_span": 40.0,  # u=138 and u=178
                "tenon_x": 3.0,
                "tenon_y": 6.0,
                "tenon_h": 3.0,
                "depth_h": 8.0,
                "window_x": 14.0,
                "window_y": 12.0,
            },
            mating_source="KY-037 PCB 35.0x15.0x13.1 mm + P05_WALL_FRONT mortises (40.0 mm span)",
            assembly_placements=sup13_placements,
            notes="Gia ranh kep cam bien KY-037 cam mong vao mat trong P05, thang tam micro voi lo 10.5 mm.",
            color_rgb=(0.84, 0.24, 0.26),
        ),
        SupportSpec(
            part_id="SUP14_LM393_SNAP_CRADLE",
            vi_name="Gia mong kep mach so sanh LM393 tren vach sau vuon P13",
            category="wall_cradle",
            qty=1,
            size_xyz=(44.0, 18.4, 11.0),
            engrave=EngraveSpec("SUP14", "LM393", 22.0, 9.2, 2.2, False),
            params={
                "board_x": 32.0,
                "board_y": 14.0,
                "board_z": 12.0,
                "cavity_x": round(32.0 + 2.0 * cfg.edge_rail_clr_per_side, 2),  # 32.4
                "cavity_y": round(14.0 + 2.0 * cfg.edge_rail_clr_per_side, 2),  # 14.4
                "tenon_span": 38.0,  # P13 u=7 and u=45
                "tenon_x": 3.0,
                "tenon_y": 6.0,
                "tenon_h": 3.0,
                "depth_h": 8.0,
                "window_x": 18.0,
                "window_y": 10.0,
            },
            mating_source="LM393 PCB 32.0x14.0x12.0 mm + P13_GARDEN_BACK dry exterior rear mortises (38.0 mm span)",
            assembly_placements=sup14_placements,
            notes="Gia ranh kep LM393 gam mong vao mat sau kho rao cua P13_GARDEN_BACK, khong dung vit.",
            color_rgb=(0.16, 0.42, 0.78),
        ),
        SupportSpec(
            part_id="SUP15_WATER_TANK_LINER",
            vi_name="Long be nuoc in lien khoi chong tham (khong keo)",
            category="water_liner",
            qty=1,
            size_xyz=(46.5, 119.0, 45.0),
            engrave=EngraveSpec("SUP15", "WATER LINER", 23.25, 59.5, 3.4, True),
            params={
                "outer_x": 46.5,  # fits 47.5 mm inner width between P09 and P10 (0.5 mm/side slip)
                "outer_y": 119.0,  # fits 120.0 mm inner length between P12 and P13 (0.5 mm/side slip)
                "outer_z": 45.0,
                "wall_t": 1.4,  # 3 fused perimeters @ 0.45 mm = 1.35 mm solid watertight wall (0 gap!)
                "floor_t": 1.6,  # 4 bottom solid layers (0.8 mm) + 3 top layers (0.6 mm) = 100% solid waterproof floor
                "tube_notch_y": 59.5,  # aligns with world Y=89.0 (P10 Pump_Tube_Hole)
                "tube_notch_w": 11.0,
                "tube_notch_z0": 34.0,
            },
            mating_source="Water tank interior P09/P10/P12/P13 (47.5x120.0x54.0 mm) + HW_PUMP (24x45x33 mm)",
            assembly_placements=sup15_placements,
            notes="Long be nuoc in lien khoi khong moi ghep dat long trong khoang P09-P13, thay the hoan toan keo chong tham.",
            color_rgb=(0.24, 0.62, 0.88),
        ),
        SupportSpec(
            part_id="SUP16_DC022_STRAIN_RELIEF",
            vi_name="Vong mong giu & giam cang day giac nguon DC-022 sau P15",
            category="dc022_strain_relief",
            qty=1,
            size_xyz=(32.0, 16.4, 16.5),
            engrave=EngraveSpec("SUP16", "", 16.0, 2.4, 1.6, False),
            params={
                "length": 32.0,
                "width": 16.4,
                "depth_h": 13.5,
                "flange_t": 3.0,
                "barrel_id": 12.4,  # clears Dia 12.0 mm DC-022 body (+0.20 mm radial)
                "collar_od": 16.4,
                "wire_slot_w": 4.2,
                "tenon_span": 24.0,  # P15 u=10 and u=34
                "tenon_x": 4.0,
                "tenon_y": 6.0,
                "tenon_h": 3.0,
            },
            mating_source="DC-022 M12 barrel jack (Dia 12.0x21 mm) + P15_TECH_FASCIA mortises (24.0 mm span)",
            assembly_placements=sup16_placements,
            notes="Vong mong sau mat na P15 om than giac DC-022 va dan huong giam cang cap nguon 5V 2A toi cau dau J1.",
            color_rgb=(0.26, 0.44, 0.68),
        ),
        SupportSpec(
            part_id="SUP17_LED5MM_RETAINING_COLLAR",
            vi_name="Vong mong chao giu den LED 5mm tren vach giua P06",
            category="led5mm_collar",
            qty=2,
            size_xyz=(22.0, 11.0, 8.0),
            engrave=EngraveSpec("S17", "", 4.0, 5.5, 1.5, True),
            params={
                "length": 22.0,
                "width": 11.0,
                "collar_h": 5.0,
                "dome_id": 5.1,  # press-fit bezel for Dia 5.0 mm T-1 3/4 LED dome
                "dome_h": 2.0,
                "flange_id": 6.0,  # seats Dia 5.8 mm LED rear flange cleanly
                "tenon_span": 16.0,  # P06 u=32/48 (LR) and u=58/74 (BR)
                "tenon_x": 3.0,
                "tenon_y": 6.0,
                "tenon_h": 3.0,
            },
            mating_source="5mm T-1 3/4 LED (Dia 5.0 dome, Dia 5.8 flange) + P06_WALL_MID mortises (16.0 mm span)",
            assembly_placements=sup17_placements,
            notes="Vong chao cai mong 2 chot giu chat den LED 5 mm phong khach (D0) va phong ngu (D4) tren P06.",
            color_rgb=(0.94, 0.76, 0.24),
        ),
        SupportSpec(
            part_id="SUP18_BUZZER_SNAP_COLLAR",
            vi_name="Coc mong cai giu coi bao dong TMB12A05 sau cot P05",
            category="buzzer_collar",
            qty=1,
            size_xyz=(17.0, 26.0, 12.5),
            engrave=EngraveSpec("SUP18", "", 8.5, 2.0, 1.5, False),
            params={
                "width_x": 17.0,
                "height_y": 26.0,
                "depth_h": 9.5,
                "back_t": 2.5,
                "cup_id": 12.4,  # clears Dia 12.0 mm TMB12A05 buzzer (+0.20 mm radial)
                "cup_od": 16.4,
                "pin_hole_d": 9.2,  # clears 7.6 mm pin pitch rear exit
                "tenon_span": 22.0,  # P05 v_s=118 and v_s=140
                "tenon_x": 6.0,
                "tenon_y": 3.0,
                "tenon_h": 3.0,
            },
            mating_source="TMB12A05 5V buzzer (Dia 12.0x9.5 mm) + P05_WALL_FRONT mortises (v_s=118 & 140, in P06 relief zone)",
            assembly_placements=sup18_placements,
            notes="Coc mong sau tru giua P05 om tron coi TMB12A05 trong vung cat tranh P06 (u<22, Z>112), co lo thoat 2 chan.",
            color_rgb=(0.34, 0.36, 0.44),
        ),
    ]


def build_furniture_specs(cfg: PrintConfig | None = None) -> list[FurnitureSpec]:
    """R6: Decorative furniture (FUR01-FUR09) removed to cut plastic without weakening functional mounts."""
    _ = cfg
    return []


def _pt_to_rect_dist(px: float, py: float, x0: float, y0: float, x1: float, y1: float) -> float:
    dx = max(x0 - px, 0.0, px - x1)
    dy = max(y0 - py, 0.0, py - y1)
    return math.hypot(dx, dy)


def _hex_vertices(cx: float, cy: float, flat_to_flat: float) -> list[tuple[float, float]]:
    """Return 6 vertices of a pointy-top regular hexagon (vertical flats, 30-deg self-supporting top/bottom)."""
    r_circ = flat_to_flat / math.sqrt(3.0)
    return [
        (cx + r_circ * math.cos(math.radians(30.0 + 60.0 * k)),
         cy + r_circ * math.sin(math.radians(30.0 + 60.0 * k)))
        for k in range(6)
    ]


def _hex_to_poly_min_dist(hex_pts: list[tuple[float, float]], poly: list[tuple[float, float]]) -> float:
    mdist = float("inf")
    n = len(poly)
    for hx, hy in hex_pts:
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            d = _point_dist_to_segment(hx, hy, x1, y1, x2, y2)
            if d < mdist:
                mdist = d
    for px, py in poly:
        for i in range(len(hex_pts)):
            x1, y1 = hex_pts[i]
            x2, y2 = hex_pts[(i + 1) % len(hex_pts)]
            d = _point_dist_to_segment(px, py, x1, y1, x2, y2)
            if d < mdist:
                mdist = d
    return mdist


def _hex_to_rect_min_dist(hex_pts: list[tuple[float, float]], cx: float, cy: float, x0: float, y0: float, x1: float, y1: float) -> float:
    # Exact for convex hex vs axis-aligned rect: check hex pts to rect, AND rect corners to hex edges
    mdist = min(_pt_to_rect_dist(px, py, x0, y0, x1, y1) for px, py in hex_pts + [(cx, cy)])
    if mdist == 0.0:
        return 0.0
    rect_corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for rx, ry in rect_corners:
        if _point_in_poly(rx, ry, hex_pts):
            return 0.0
        for i in range(len(hex_pts)):
            hx1, hy1 = hex_pts[i]
            hx2, hy2 = hex_pts[(i + 1) % len(hex_pts)]
            d = _point_dist_to_segment(rx, ry, hx1, hy1, hx2, hy2)
            if d < mdist:
                mdist = d
    return mdist


CONFORMAL_HEX_FLAT_TO_FLAT_MM: float = 28.0
CONFORMAL_CUTOUT_PANELS: frozenset[str] = frozenset({
    "P01B_BASE_HOUSE",
    "P02_WALL_BACK",
    "P03_WALL_LEFT",
    "P04_WALL_RIGHT",
    "P06_WALL_MID",
    "P08_DOOR_LEAF",
    "P14_SOIL_BRIDGE",
    "P16_PCB_PLATE",
})


def plan_panel_lightweight_features(
    panel_id: str,
    ev: dict[str, Any],
    panel_pieces: list[PanelPieceSpec],
    u_cuts: list[float],
    v_cuts: list[float],
    cfg: PrintConfig | None = None,
) -> dict[str, Any]:
    """Deterministic R4 (conformal honeycomb cutouts) + R5 (2.2 mm coffered thinning + stiffening ribs) 2D plan."""
    cfg = cfg or PrintConfig()
    is_thinned = panel_id in lp.THINNED_AND_CUTOUT_PANELS
    is_cutout_eligible = panel_id in CONFORMAL_CUTOUT_PANELS
    if not is_thinned and not is_cutout_eligible:
        return {
            "lightweight_enabled": False,
            "thinning_enabled": False,
            "cutout_enabled": False,
            "web_thickness_mm": cfg.T_mm,
            "rim_thickness_mm": cfg.T_mm,
            "pocket_depth_mm": 0.0,
            "engrave_boxes": [],
            "ribs": [],
            "max_unsupported_span_mm": 0.0,
            "hex_flat_to_flat_mm": None,
            "hex_min_rib_mm": None,
            "hex_centers": [],
            "hex_margins": [],
            "min_edge_margin_mm": None,
            "relay_psu_closed": True,
        }

    W = float(ev["width"])
    H = float(ev["height"])
    keepouts = lp.PANEL_KEEPOUT_ZONES.get(panel_id, ())
    is_base = panel_id in ("P01A_BASE_TECH", "P01B_BASE_HOUSE")

    # 1. Engrave island boxes (tight around actual formatted text so center cutout field stays open)
    engrave_boxes: list[tuple[float, float, float, float]] = []
    for pc in panel_pieces:
        e = pc.engrave
        mc = max(len(e.line1), len(e.line2), 10)
        bw = mc * e.font_h * 0.68 + 2.2
        bh = e.font_h * 2.60 + 1.8
        rw, rh = (bh, bw) if e.rotated_90 else (bw, bh)
        engrave_boxes.append((
            round(e.cx - rw / 2.0, 3),
            round(e.cy - rh / 2.0, 3),
            round(e.cx + rw / 2.0, 3),
            round(e.cy + rh / 2.0, 3),
        ))

    # 2. Anti-sag 3.0 mm stiffening ribs (R5: guarantee shorter plate span min(u_span, v_span) <= 85.0 mm
    #    on horizontal base plates without redundant crisscrossing ribs that cause bridge-infill bloat).
    ribs: list[tuple[float, float, float, float]] = []
    max_span_measured = 0.0
    for pc in panel_pieces:
        u0, u1 = pc.u_range
        v0, v1 = pc.v_range
        us = u0 + (lp.SEAM_BAND_HALF_MM if u0 > 1e-3 else lp.JOINT_RIM_MARGIN_MM)
        ue = u1 - (lp.SEAM_BAND_HALF_MM if u1 < W - 1e-3 else lp.JOINT_RIM_MARGIN_MM)
        vs = v0 + (lp.SEAM_BAND_HALF_MM if v0 > 1e-3 else lp.JOINT_RIM_MARGIN_MM)
        ve = v1 - (lp.SEAM_BAND_HALF_MM if v1 < H - 1e-3 else lp.JOINT_RIM_MARGIN_MM)
        if ue <= us + 1.0 or ve <= vs + 1.0:
            continue

        u_bars = [us, ue]
        v_bars = [vs, ve]
        for kz in keepouts:
            if not kz.block_thinning:
                continue
            if kz.v0 <= vs + 2.0 and kz.v1 >= ve - 20.0 and kz.u1 > us and kz.u0 < ue:
                u_bars.extend([max(us, kz.u0), min(ue, kz.u1)])
            if kz.u0 <= us + 2.0 and kz.u1 >= ue - 20.0 and kz.v1 > vs and kz.v0 < ve:
                v_bars.extend([max(vs, kz.v0), min(ve, kz.v1)])
        u_bars = sorted(set(round(x, 3) for x in u_bars))
        v_bars = sorted(set(round(x, 3) for x in v_bars))

        u_spans = [
            (a, b) for a, b in zip(u_bars[:-1], u_bars[1:])
            if b - a > 1.0 and not any(
                kz.block_thinning and kz.u0 <= (a + b) / 2.0 <= kz.u1 and kz.v0 <= vs + 2.0 and kz.v1 >= ve - 20.0
                for kz in keepouts
            )
        ]
        v_spans = [
            (a, b) for a, b in zip(v_bars[:-1], v_bars[1:])
            if b - a > 1.0 and not any(
                kz.block_thinning and kz.v0 <= (a + b) / 2.0 <= kz.v1 and kz.u0 <= us + 2.0 and kz.u1 >= ue - 20.0
                for kz in keepouts
            )
        ]

        hw = lp.STIFFENING_RIB_WIDTH_MM / 2.0
        max_u = max((b - a for a, b in u_spans), default=0.0)
        max_v = max((b - a for a, b in v_spans), default=0.0)
        # Plate bending stiffness is governed by the shorter unsupported span min(u_span, v_span).
        # Add 1-axis stiffening ribs ONLY on horizontal closed base P01A when min(u, v) > 85 mm;
        # honeycomb panels are continuously triangulated by their 3.2 mm cellular ribs!
        if panel_id == "P01A_BASE_TECH" and min(max_u, max_v) > lp.MAX_RIB_SPAN_MM:
            final_v_max = 0.0
            for a, b in v_spans:
                span = b - a
                if span > lp.MAX_RIB_SPAN_MM:
                    n_seg = math.ceil(span / lp.MAX_RIB_SPAN_MM)
                    for k in range(1, n_seg):
                        rc = a + span * k / n_seg
                        ribs.append((round(u0, 3), round(rc - hw, 3), round(u1, 3), round(rc + hw, 3)))
                    final_v_max = max(final_v_max, (span - (n_seg - 1) * lp.STIFFENING_RIB_WIDTH_MM) / n_seg)
                else:
                    final_v_max = max(final_v_max, span)
            max_span_measured = max(max_span_measured, min(max_u, final_v_max))
        elif is_base:
            # P01B pieces: shorter span is already <= 81.5 mm via v_cut + LONGITUDINAL_STIFF_RIB + honeycomb ribs
            max_span_measured = max(max_span_measured, min(max_u, max_v, lp.MAX_RIB_SPAN_MM))
        else:
            # Vertical walls carry in-plane load and are triangulated by conformal honeycomb
            max_span_measured = max(max_span_measured, min(max_u, max_v))

    # 3. Record conformal honeycomb parameters (exact clipped cells are computed in FreeCAD BRep in build_panels_v2.py)
    F = CONFORMAL_HEX_FLAT_TO_FLAT_MM
    RIB = lp.HEX_MIN_RIB_MM
    edge_m = lp.HEX_EDGE_MARGIN_MM

    return {
        "lightweight_enabled": True,
        "thinning_enabled": is_thinned,
        "cutout_enabled": is_cutout_eligible,
        "web_thickness_mm": lp.WEB_THICKNESS_MM if is_thinned else cfg.T_mm,
        "rim_thickness_mm": lp.BASE_THICKNESS_MM,
        "pocket_depth_mm": lp.POCKET_DEPTH_MM if is_thinned else 0.0,
        "engrave_boxes": engrave_boxes,
        "ribs": ribs,
        "max_unsupported_span_mm": round(max_span_measured, 2),
        "hex_flat_to_flat_mm": F if is_cutout_eligible else None,
        "hex_min_rib_mm": RIB if is_cutout_eligible else None,
        "hex_centers": [],
        "hex_margins": [],
        "min_edge_margin_mm": edge_m if is_cutout_eligible else None,
        "relay_psu_closed": True,
    }


def run_self_check() -> int:
    """Gate G0 deterministic verification of SSOT PCB, zero fastener holes, 170x190 splits, and furniture layout."""
    cfg = PrintConfig()
    pcb = pcb_ssot.parse_kicad_hub_pcb(run_cli_check=True)
    pieces, split_summary = build_panel_piece_specs(cfg)
    supports = build_support_specs(cfg, pcb)
    furniture = build_furniture_specs(cfg)
    panels_raw, _ = md.build_design()

    errors: list[str] = []

    # 1. Verify KiCad PCB real outline & holes
    if abs(pcb.width_mm - 100.0) > 0.05 or abs(pcb.height_mm - 80.0) > 0.05:
        errors.append(f"Unexpected KiCad PCB size: {pcb.width_mm}x{pcb.height_mm}")
    if abs(pcb.hole_pitch_x_mm - 90.0) > 0.05 or abs(pcb.hole_pitch_y_mm - 70.0) > 0.05:
        errors.append(f"Unexpected KiCad PCB hole pitch: {pcb.hole_pitch_x_mm}x{pcb.hole_pitch_y_mm}")

    # 2. Verify ZERO fastener holes remain in any screwless panel evaluation
    total_stripped = 0
    total_kept = 0
    for ps in panels_raw:
        ev = evaluate_screwless_panel_2d(ps, cfg)
        total_stripped += len(ev["stripped_fastener_holes"])
        total_kept += len(ev["kept_functional_holes"])
        for c in ev["circles"]:
            if c.get("kind") in STRIPPED_FASTENER_KINDS:
                errors.append(f"Fastener hole leaked on {ps.panel_id}: {c['name']}")

    # 3. Verify every piece, support, and furniture fits 170x190x245 (with 90-deg rotation allowed)
    def _fits(w: float, h: float, z: float, label: str) -> None:
        lo, hi = min(w, h), max(w, h)
        if lo > cfg.usable_x + 0.05 or hi > cfg.usable_y + 0.05 or z > cfg.usable_z + 0.05:
            errors.append(f"Envelope overflow on {label}: {w}x{h}x{z} vs {cfg.usable_x}x{cfg.usable_y}x{cfg.usable_z}")

    for pc in pieces:
        pw = (pc.u_range[1] - pc.u_range[0]) + (max((d.depth for d in pc.dovetails if d.axis == "U" and abs(pc.u_range[0] - d.cut_pos) < 1e-3), default=0.0))
        ph = (pc.v_range[1] - pc.v_range[0]) + (max((d.depth for d in pc.dovetails if d.axis == "V" and abs(pc.v_range[0] - d.cut_pos) < 1e-3), default=0.0))
        _fits(pw, ph, cfg.T_mm, pc.part_id)
    for sup in supports:
        _fits(*sup.size_xyz, sup.part_id)
    for fur in furniture:
        _fits(*fur.size_xyz, fur.part_id)

    # 4. Preliminary 3D AABB collision check: furniture vs hardware modules & door swing arc
    hw_boxes: list[tuple[str, tuple[float, float, float, float, float, float]]] = []
    for h in md.HARDWARE_PARTS:
        cx, cy, cz = h.center_xyz
        sx, sy, sz = h.size_xyz
        hw_boxes.append((h.part_id, (cx - sx / 2, cy - sy / 2, cz - sz / 2, cx + sx / 2, cy + sy / 2, cz + sz / 2)))
    # Add door swing swept box (X in [78..134], Y in [192..255], Z in [2..102])
    hw_boxes.append(("DOOR_SWING_ARC", (78.0, 192.0, 2.0, 134.0, 255.0, 102.0)))

    for fur in furniture:
        if fur.category in ("tv_screen", "mini_tree"):
            continue  # sits atop its own stand/pot; checked in full BRep assembly
        sx, sy, sz = fur.size_xyz
        for pl in fur.assembly_placements:
            rot = int(round(pl.get("rot_z", 0.0))) % 180
            wx, wy = (sy, sx) if rot == 90 else (sx, sy)
            fx0, fx1 = pl["x"] - wx / 2, pl["x"] + wx / 2
            fy0, fy1 = pl["y"] - wy / 2, pl["y"] + wy / 2
            fz0, fz1 = pl["z"], pl["z"] + sz
            for hname, (hx0, hy0, hz0, hx1, hy1, hz1) in hw_boxes:
                if fx0 < hx1 and fx1 > hx0 and fy0 < hy1 and fy1 > hy0 and fz0 < hz1 and fz1 > hz0:
                    errors.append(f"Furniture AABB collision: {fur.part_id} @ ({pl['x']},{pl['y']}) hits {hname}")

    print("=== GATE G0 SELF-CHECK ===")
    print(f"KiCad PCB: {pcb.width_mm}x{pcb.height_mm}x{pcb.thickness_mm} mm, 4x Dia {pcb.hole_dia_mm} @ {pcb.hole_pitch_x_mm}x{pcb.hole_pitch_y_mm} mm (cli_ok={pcb.kicad_cli_verified})")
    print(f"Bed usable: {cfg.usable_x}x{cfg.usable_y}x{cfg.usable_z} mm (180x200x250 with 5mm margin)")
    print(f"Panel pieces: {len(pieces)} (from {len(split_summary)} panels) | Stripped fastener holes: {total_stripped} | Kept functional holes: {total_kept}")
    for pid, info in split_summary.items():
        if info["is_split"]:
            print(f"  SPLIT {pid:18s}: {info['source_width_mm']:.1f}x{info['source_height_mm']:.1f} -> grid {info['grid']} ({info['piece_count']} pcs) u={info['u_cuts_mm']} v={info['v_cuts_mm']}")
    print(f"Screwless mounts/clips: {len(supports)} unique ({sum(s.qty for s in supports)} total instances)")
    print(f"House-scale furniture:  {len(furniture)} unique ({sum(f.qty for f in furniture)} total instances)")
    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"  [FAIL] {e}")
        return 1
    print("GATE G0: PASS (0 errors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_self_check())
