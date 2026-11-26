"""Single-source-of-truth domain model for 3D-printable Smart Home House parts & supports.

Reads all panel geometry, hole patterns, joints, and hardware dimensions directly from
`hardware/mica/mica_design.py` and `hardware/mica/panel_geometry_from_freecad.json`.
Pure Python (zero external dependencies) so both FreeCAD 1.1 Python and system Python
import the exact same specifications without duplicating or hardcoding geometry.
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

if str(MICA_DIR) not in sys.path:
    sys.path.insert(0, str(MICA_DIR))

import mica_design as md


@dataclass(frozen=True)
class PrintConfig:
    """FDM printer bed envelope and 3D-printing mechanical tolerances (mm)."""

    bed_x: float = 220.0
    bed_y: float = 220.0
    bed_z: float = 250.0
    bed_margin: float = 5.0
    T_mm: float = 3.0
    tab_clr: float = 0.25
    dovetail_clearance: float = 0.20
    dovetail_depth: float = 6.0
    dovetail_neck: float = 10.0
    dovetail_head: float = 14.0
    compact_dovetail_depth: float = 4.0
    compact_dovetail_neck: float = 5.5
    compact_dovetail_head: float = 8.0
    engrave_depth: float = 0.60
    min_feature_clearance: float = 3.5

    @property
    def usable_x(self) -> float:
        return self.bed_x - 2.0 * self.bed_margin

    @property
    def usable_y(self) -> float:
        return self.bed_y - 2.0 * self.bed_margin

    @property
    def usable_z(self) -> float:
        return self.bed_z - self.bed_margin


@dataclass(frozen=True)
class DovetailJointSpec:
    """One trapezoidal dovetail joint along a split seam."""

    axis: str  # "U" (vertical cut at u=cut_pos, dovetails distributed along v) or "V" (horizontal cut at v=cut_pos)
    cut_pos: float
    center_along: float
    depth: float
    neck_w: float
    head_w: float
    clearance: float
    male_side: int  # +1 means piece with coord > cut_pos owns male tongue; -1 means piece with coord < cut_pos owns male tongue


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
    """One 3D-printable panel (or split piece of an oversized panel)."""

    part_id: str  # e.g. P16_PCB_PLATE or P02_WALL_BACK_piece1of2
    source_panel_id: str
    piece_index: int  # 1-based
    piece_count: int
    qty: int
    plane: str
    origin_xyz: tuple[float, float, float]
    extra_origins_xyz: tuple[tuple[float, float, float], ...]
    explode_xyz: tuple[float, float, float]
    shift_u: float  # local_shifted = raw_u + shift_u
    shift_v: float
    u_range: tuple[float, float]  # shifted 2D coordinates [u_min, u_max]
    v_range: tuple[float, float]  # shifted 2D coordinates [v_min, v_max]
    dovetails: tuple[DovetailJointSpec, ...]
    engrave: EngraveSpec
    vi_name: str
    notes: str
    color_rgb: tuple[float, float, float]


@dataclass(frozen=True)
class SupportSpec:
    """One printable mechanical support / bracket / standoff / foot."""

    part_id: str
    vi_name: str
    category: str  # "bracket", "clip", "foot", "standoff", "cradle", "retainer", "hinge"
    qty: int
    size_xyz: tuple[float, float, float]  # print-oriented bounding box (X, Y, Z)
    engrave: EngraveSpec
    params: dict[str, Any]
    mating_source: str
    assembly_placements: tuple[dict[str, Any], ...]  # world 3D placements for assembly check & render
    exclude_from_default_assembly: bool = False  # True for optional 1-piece alternatives (SUP07, SUP09)
    notes: str = ""
    color_rgb: tuple[float, float, float] = (0.94, 0.62, 0.24)


VI_PANEL_NAMES: dict[str, str] = {
    "P01A_BASE_TECH": "Tam day truoc (Khoang ky thuat & Vuon)",
    "P01B_BASE_HOUSE": "Tam day sau (Phong khach & Phong ngu)",
    "P02_WALL_BACK": "Tuong sau (Phong khach + Phong ngu)",
    "P03_WALL_LEFT": "Vach hong trai cat mo",
    "P04_WALL_RIGHT": "Vach hong phai cat mo",
    "P05_WALL_FRONT": "Tuong mat tien & Khung cua chinh",
    "P06_WALL_MID": "Vach ngan giua (Phong khach / Phong ngu)",
    "P07_SERVO_SHELF": "Ke gan Servo SG90 cua chinh",
    "P08_DOOR_LEAF": "Canh cua chinh",
    "P09_GARDEN_LEFT": "Vach trai be nuoc",
    "P10_WATER_DIVIDER": "Vach ngan be nuoc & chau cay",
    "P11_GARDEN_RIGHT": "Vach phai chau cay",
    "P12_GARDEN_FRONT": "Vach truoc be nuoc & chau cay",
    "P13_GARDEN_BACK": "Vach sau be nuoc & chau cay",
    "P14_SOIL_BRIDGE": "Cau giu dau do am dat YL-69",
    "P15_TECH_FASCIA": "Mat na ky thuat (Nguon DC & Loa)",
    "P16_PCB_PLATE": "Tam ga bo mach Hub PCB 100x80",
    "P17_BASE_JOINER": "Thanh noi day (mat duoi)",
}


def load_freecad_reference_geometry() -> dict[str, Any]:
    ref_path = MICA_DIR / "panel_geometry_from_freecad.json"
    with ref_path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def _poly_intervals_at_line(
    poly: list[tuple[float, float]],
    axis: str,
    coord: float,
) -> list[tuple[float, float]]:
    """Return sorted solid [a, b] intervals where the polygon intersects line u=coord or v=coord."""
    crossings: list[float] = []
    n = len(poly)
    # Tiny perturbation avoids hitting exact horizontal/vertical vertices
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
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    ev: dict[str, Any],
    u_lo: float,
    u_hi: float,
    v_lo: float,
    v_hi: float,
    margin: float,
) -> bool:
    if x0 < u_lo + margin or x1 > u_hi - margin or y0 < v_lo + margin or y1 > v_hi - margin:
        return False
    poly = ev["outer_poly"]
    # Sample perimeter and interior grid points to ensure rectangle stays strictly inside polygon
    for ix in range(5):
        px = x0 + (x1 - x0) * ix / 4.0
        for iy in range(3):
            py = y0 + (y1 - y0) * iy / 2.0
            if not _point_in_poly(px, py, poly):
                return False
    # Check polygon edge clearance at corners & midpoints
    n = len(poly)
    check_pts = [
        (x0, y0), (x1, y0), (x1, y1), (x0, y1),
        ((x0 + x1) / 2.0, y0), ((x0 + x1) / 2.0, y1),
        (x0, (y0 + y1) / 2.0), (x1, (y0 + y1) / 2.0),
    ]
    for px, py in check_pts:
        for i in range(n):
            p1 = poly[i]
            p2 = poly[(i + 1) % n]
            if _point_dist_to_segment(px, py, p1[0], p1[1], p2[0], p2[1]) < margin - 0.15:
                return False
    # Check inner rectangular cutouts/slots
    for r in ev["inner_rects"]:
        rx0, ry0 = r["u0"] - margin, r["v0"] - margin
        rx1, ry1 = r["u0"] + r["du"] + margin, r["v0"] + r["dv"] + margin
        if not (x1 <= rx0 or x0 >= rx1 or y1 <= ry0 or y0 >= ry1):
            return False
    # Check circular holes
    for c in ev["circles"]:
        rad = c["dia"] / 2.0 + margin
        cx = max(x0, min(c["cx"], x1))
        cy = max(y0, min(c["cy"], y1))
        if math.hypot(cx - c["cx"], cy - c["cy"]) < rad:
            return False
    return True


def _choose_engrave_spec(
    part_id: str,
    piece_w: float,
    piece_h: float,
    T_mm: float,
    ev: dict[str, Any],
    u_lo: float,
    u_hi: float,
    v_lo: float,
    v_hi: float,
    dovetails: list[DovetailJointSpec],
    piece_index: int,
    piece_count: int,
) -> EngraveSpec:
    """Find a guaranteed clear interior patch on the piece for readable engraved text."""
    short_id = part_id.split("_piece")[0]
    if piece_count > 1:
        # Compact readable ID on piece, e.g. P02 p1/2
        tag = short_id.split("_")[0]
        line1 = f"{tag} p{piece_index}/{piece_count}"
    else:
        tag = short_id.split("_")[0]
        # Use fuller ID when panel is large enough
        line1 = short_id if (piece_w >= 115.0 and piece_h >= 60.0) else tag
    line2 = f"{piece_w:.0f}x{piece_h:.0f}x{T_mm:.0f}mm"

    # Build exclusion boxes for dovetail zones so text never touches a joint
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
    # Try descending font heights and both horizontal / 90-deg orientations
    for font_h in (6.0, 5.0, 4.2, 3.6, 3.0, 2.5):
        box_w = max_chars * font_h * 0.66 + 2.0
        box_h = font_h * 2.55 + 1.6
        for rot in (False, True):
            rw, rh = (box_h, box_w) if rot else (box_w, box_h)
            for margin in (3.0, 2.0, 1.3):
                if rw + 2 * margin > (u_hi - u_lo) or rh + 2 * margin > (v_hi - v_lo):
                    continue
                # Grid search biased toward center of piece
                nu = max(3, int((u_hi - u_lo - rw) / 4.0) + 1)
                nv = max(3, int((v_hi - v_lo - rh) / 4.0) + 1)
                nu = min(nu, 28)
                nv = min(nv, 28)
                mid_u = (u_lo + u_hi) / 2.0
                mid_v = (v_lo + v_hi) / 2.0
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
                            score = math.hypot(cx - mid_u, cy - mid_v)
                            if score < best_score:
                                best_score = score
                                best_pt = (cx, cy)
                if best_pt is not None:
                    return EngraveSpec(
                        line1=line1,
                        line2=line2,
                        cx=round(best_pt[0], 3),
                        cy=round(best_pt[1], 3),
                        font_h=font_h,
                        rotated_90=rot,
                    )

    # Compact fallback (guaranteed inside tiny panels like P07)
    tag = short_id.split("_")[0]
    line1_s = tag
    line2_s = f"{piece_w:.0f}x{piece_h:.0f}x{T_mm:.0f}"
    return EngraveSpec(
        line1=line1_s,
        line2=line2_s,
        cx=round((u_lo + u_hi) / 2.0, 3),
        cy=round((v_lo + v_hi) / 2.0, 3),
        font_h=2.4,
        rotated_90=(piece_h > piece_w * 1.4),
    )


def _feature_clearance_at_cut(ev: dict[str, Any], axis: str, cut_pos: float) -> float:
    """Compute minimum distance from a cut line u=cut_pos (or v=cut_pos) to all holes, slots, and edge steps."""
    min_d = float("inf")
    # Circular holes
    for c in ev["circles"]:
        coord = c["cx"] if axis == "U" else c["cy"]
        d = abs(cut_pos - coord) - c["dia"] / 2.0
        min_d = min(min_d, d)
    # Inner rectangular slots/windows/cutouts
    for r in ev["inner_rects"]:
        a0 = r["u0"] if axis == "U" else r["v0"]
        a1 = a0 + (r["du"] if axis == "U" else r["dv"])
        if a0 <= cut_pos <= a1:
            return -min(cut_pos - a0, a1 - cut_pos)
        d = min(abs(cut_pos - a0), abs(cut_pos - a1))
        min_d = min(min_d, d)
    # Outer polygon vertical/horizontal step edges (notches, tabs, doors, steps)
    poly = ev["outer_poly"]
    n = len(poly)
    total_span = ev["width"] if axis == "U" else ev["height"]
    for i in range(n):
        p1 = poly[i]
        p2 = poly[(i + 1) % n]
        a1, b1 = (p1[0], p1[1]) if axis == "U" else (p1[1], p1[0])
        a2, b2 = (p2[0], p2[1]) if axis == "U" else (p2[1], p2[0])
        # Edge parallel to cut line (i.e. a1 == a2) that is not the extreme outer boundary
        if abs(a1 - a2) < 1e-3 and abs(b1 - b2) > 0.5:
            if 1.0 < a1 < total_span - 1.0:
                step_h = abs(b1 - b2)
                d_step = abs(cut_pos - a1)
                # Penalize cutting too close to a tall wall step (prevents fragile tall thin slivers)
                if step_h > 40.0 and d_step < 4.5:
                    return -1.0
                min_d = min(min_d, d_step)
    return min_d


def _solve_axis_cuts(
    ev: dict[str, Any],
    axis: str,
    cfg: PrintConfig,
) -> list[float]:
    """Find minimum count and optimal feature-clear cut positions along axis U or V."""
    span = ev["width"] if axis == "U" else ev["height"]
    limit = cfg.usable_x if axis == "U" else cfg.usable_y
    if span <= limit + 1e-6:
        return []

    dt_protrusion = cfg.dovetail_depth
    # Because male_side == +1, piece 0 (leftmost/bottommost) has ONLY female sockets (max len = limit),
    # while every subsequent piece k >= 1 has a male tongue on its low seam (max base len = limit - dt_protrusion).
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

    raise RuntimeError(f"Could not find valid bed-fit split for {ev['panel_id']} along axis {axis}")


def _build_seam_dovetails(
    ev: dict[str, Any],
    axis: str,
    cut_pos: float,
    span_lo: float,
    span_hi: float,
    cfg: PrintConfig,
) -> list[DovetailJointSpec]:
    """Place 1..2 trapezoidal dovetails cleanly inside solid material along a seam segment."""
    intervals = _poly_intervals_at_line(ev["outer_poly"], axis, cut_pos)
    # Clip intervals to [span_lo, span_hi]
    clipped: list[tuple[float, float]] = []
    for a, b in intervals:
        lo = max(a, span_lo)
        hi = min(b, span_hi)
        if hi - lo >= 12.0:
            clipped.append((lo, hi))
    if not clipped:
        return []

    # Choose standard or compact dovetail size based on widest available solid segment
    widest = max(b - a for a, b in clipped)
    if widest < 42.0:
        depth = cfg.compact_dovetail_depth
        neck = cfg.compact_dovetail_neck
        head = cfg.compact_dovetail_head
    else:
        depth = cfg.dovetail_depth
        neck = cfg.dovetail_neck
        head = cfg.dovetail_head

    # Exclude hole/slot zones along the seam
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

    # Pick dovetail centers inside clipped solid intervals
    dovetails: list[DovetailJointSpec] = []
    for lo, hi in clipped:
        seg_len = hi - lo
        end_pad = head / 2.0 + 3.0
        if seg_len < 2.0 * end_pad:
            # Compact centered dovetail for narrow bridges (e.g. 16 mm USB cutout on P15)
            mid = (lo + hi) / 2.0
            if _clear_along(mid):
                dovetails.append(DovetailJointSpec(
                    axis=axis,
                    cut_pos=cut_pos,
                    center_along=round(mid, 2),
                    depth=depth,
                    neck_w=neck,
                    head_w=head,
                    clearance=cfg.dovetail_clearance,
                    male_side=+1,
                ))
            continue

        # Target 2 dovetails for segments >= 85 mm, else 1 centered dovetail
        count = 2 if seg_len >= 85.0 else 1
        targets = [lo + seg_len * (k + 1) / (count + 1) for k in range(count)]
        for t in targets:
            # Search outward from target for first clear position
            found: float | None = None
            for delta in [0.0] + [s * step for step in range(1, 35) for s in (-1.0, 1.0)]:
                cand = t + delta
                if lo + end_pad <= cand <= hi - end_pad and _clear_along(cand):
                    found = cand
                    break
            if found is not None:
                dovetails.append(DovetailJointSpec(
                    axis=axis,
                    cut_pos=cut_pos,
                    center_along=round(found, 2),
                    depth=depth,
                    neck_w=neck,
                    head_w=head,
                    clearance=cfg.dovetail_clearance,
                    male_side=+1,
                ))
    return dovetails


def build_panel_piece_specs(cfg: PrintConfig | None = None) -> tuple[list[PanelPieceSpec], dict[str, Any]]:
    """Build all printable panel/piece specs directly from `mica_design.py`."""
    cfg = cfg or PrintConfig()
    params = md.default_param_values(T_mm=cfg.T_mm, tab_clr=cfg.tab_clr)
    panels, _joints = md.build_design()

    pieces: list[PanelPieceSpec] = []
    split_summary: dict[str, Any] = {}

    for pspec in panels:
        ev = md.evaluate_panel_2d(pspec, T_mm=cfg.T_mm, tab_clr=cfg.tab_clr)
        u_cuts = _solve_axis_cuts(ev, "U", cfg)
        v_cuts = _solve_axis_cuts(ev, "V", cfg)

        u_bounds = [0.0] + u_cuts + [ev["width"]]
        v_bounds = [0.0] + v_cuts + [ev["height"]]
        nx = len(u_bounds) - 1
        ny = len(v_bounds) - 1
        total_pieces = nx * ny

        orig = tuple(round(md.eval_expr(c, params), 4) for c in pspec.origin_xyz)
        extra_origs = tuple(
            tuple(round(md.eval_expr(c, params), 4) for c in eo)
            for eo in pspec.extra_origins_xyz
        )

        # Precompute dovetails on every internal seam segment
        seam_u_dts: dict[tuple[int, int], list[DovetailJointSpec]] = {}
        for iu in range(nx - 1):
            for iv in range(ny):
                seam_u_dts[(iu, iv)] = _build_seam_dovetails(
                    ev, "U", u_cuts[iu], v_bounds[iv], v_bounds[iv + 1], cfg
                )
        seam_v_dts: dict[tuple[int, int], list[DovetailJointSpec]] = {}
        for iu in range(nx):
            for iv in range(ny - 1):
                seam_v_dts[(iu, iv)] = _build_seam_dovetails(
                    ev, "V", v_cuts[iv], u_bounds[iu], u_bounds[iu + 1], cfg
                )

        piece_ids: list[str] = []
        k = 0
        for iv in range(ny):
            for iu in range(nx):
                k += 1
                u_lo, u_hi = u_bounds[iu], u_bounds[iu + 1]
                v_lo, v_hi = v_bounds[iv], v_bounds[iv + 1]
                part_id = (
                    pspec.panel_id
                    if total_pieces == 1
                    else f"{pspec.panel_id}_piece{k}of{total_pieces}"
                )
                piece_ids.append(part_id)

                local_dts: list[DovetailJointSpec] = []
                # Left seam (this piece is on +side of u_cuts[iu-1])
                if iu > 0:
                    local_dts.extend(seam_u_dts[(iu - 1, iv)])
                # Right seam (this piece is on -side of u_cuts[iu])
                if iu < nx - 1:
                    local_dts.extend(seam_u_dts[(iu, iv)])
                # Bottom seam (this piece is on +side of v_cuts[iv-1])
                if iv > 0:
                    local_dts.extend(seam_v_dts[(iu, iv - 1)])
                # Top seam (this piece is on -side of v_cuts[iv])
                if iv < ny - 1:
                    local_dts.extend(seam_v_dts[(iu, iv)])

                # Actual piece span including male dovetail protrusion on +side
                add_u = cfg.dovetail_depth if (iu > 0 and any(d.axis == "U" and d.male_side == +1 for d in seam_u_dts[(iu - 1, iv)])) else 0.0
                add_v = cfg.dovetail_depth if (iv > 0 and any(d.axis == "V" and d.male_side == +1 for d in seam_v_dts[(iu, iv - 1)])) else 0.0
                if pspec.panel_id == "P15_TECH_FASCIA" and add_u > 0:
                    add_u = cfg.compact_dovetail_depth

                piece_w = round((u_hi - u_lo) + add_u, 2)
                piece_h = round((v_hi - v_lo) + add_v, 2)

                engrave = _choose_engrave_spec(
                    part_id=part_id,
                    piece_w=piece_w,
                    piece_h=piece_h,
                    T_mm=cfg.T_mm,
                    ev=ev,
                    u_lo=u_lo,
                    u_hi=u_hi,
                    v_lo=v_lo,
                    v_hi=v_hi,
                    dovetails=local_dts,
                    piece_index=k,
                    piece_count=total_pieces,
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
                    engrave=engrave,
                    vi_name=VI_PANEL_NAMES.get(pspec.panel_id, pspec.name),
                    notes=pspec.notes,
                    color_rgb=pspec.color_rgb,
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


def build_support_specs(cfg: PrintConfig | None = None) -> list[SupportSpec]:
    """Build all 12 printable mechanical supports derived directly from `mica_design.py` parameters."""
    cfg = cfg or PrintConfig()
    p = md.default_param_values(T_mm=cfg.T_mm, tab_clr=cfg.tab_clr)
    panels, _joints = md.build_design()
    panel_map = {ps.panel_id: ps for ps in panels}
    ev_map = {ps.panel_id: md.evaluate_panel_2d(ps, T_mm=cfg.T_mm, tab_clr=cfg.tab_clr) for ps in panels}

    T = p["T_mm"]
    base_L = p["base_L"]
    base_W = p["base_W"]
    pcb_hx = p["pcb_hx"]  # 90.0
    pcb_hy = p["pcb_hy"]  # 70.0
    pcb_m3_d = p["pcb_m3_d"]  # 3.4
    m3_mod_d = p["m3_mod_d"]  # 3.5
    clamp_d = p["clamp_d"]  # 3.0

    # Read exact world coordinates of key hardware/holes from mica_design.py
    hw_map = {h.part_id: h for h in md.HARDWARE_PARTS}
    pcb_cx, pcb_cy, _ = hw_map["HW_PCB"].center_xyz  # (82.0, 99.0)
    rly1_cx, rly1_cy, _ = hw_map["HW_RELAY1"].center_xyz  # (196.0, 136.0)
    rly2_cx, rly2_cy, _ = hw_map["HW_RELAY2"].center_xyz  # (196.0, 92.0)
    pam_cx, pam_cy, _ = hw_map["HW_PAM8403"].center_xyz  # (182.0, 52.0)

    # Extract hole pitches directly from P01A / P16 / P15 / P08 circles
    def _hole_xy(pid: str, hole_name: str) -> tuple[float, float]:
        for c in ev_map[pid]["circles"]:
            if c["name"] == hole_name:
                return (c["cx"], c["cy"])
        raise KeyError(f"Missing hole {hole_name} on {pid}")

    p16_c1 = _hole_xy("P16_PCB_PLATE", "PLATE_C1_M3")
    p16_c4 = _hole_xy("P16_PCB_PLATE", "PLATE_C4_M3")
    plate_pitch_x = round(p16_c4[0] - p16_c1[0], 3)  # 116.0
    plate_pitch_y = round(p16_c4[1] - p16_c1[1], 3)  # 96.0

    rly_h1 = _hole_xy("P01A_BASE_TECH", "RLY1_H1_M3")
    rly_h4 = _hole_xy("P01A_BASE_TECH", "RLY1_H4_M3")
    rly_pitch_x = round(abs(rly_h4[0] - rly_h1[0]), 3)  # 44.5
    rly_pitch_y = round(abs(rly_h4[1] - rly_h1[1]), 3)  # 20.5

    pam_l = _hole_xy("P01A_BASE_TECH", "PAM_CLAMP_L")
    pam_r = _hole_xy("P01A_BASE_TECH", "PAM_CLAMP_R")
    pam_span = round(abs(pam_r[0] - pam_l[0]), 3)  # 26.0

    spk_l = _hole_xy("P15_TECH_FASCIA", "Speaker_Clamp_L")
    spk_r = _hole_xy("P15_TECH_FASCIA", "Speaker_Clamp_R")
    spk_span = round(abs(spk_r[0] - spk_l[0]), 3)  # 36.0

    # House inner wall coordinates derived from mica_design.py
    X_L_IN = 10.0 + T  # 13.0
    X_R_IN = 396.0 - T  # 393.0
    X_M_L = 200.0 - T / 2.0  # 198.5
    X_M_R = 200.0 + T / 2.0  # 201.5
    Y_B_IN = 382.0 - T  # 379.0
    Y_F_IN = 192.0 + T  # 195.0
    Z_WALL_TOP = p["wall_H"]  # 147.0
    Z_CUT_H = p["cut_H"]  # 34.0

    # Garden inner corners
    GX_L_IN = 266.0 + T  # 269.0
    GX_R_IN = 396.0 - T  # 393.0
    GY_F_IN = 26.0 + T  # 29.0
    GY_B_IN = 152.0 - T  # 149.0

    # Clear of vertical rear tabs (Z=26, 73, 120 +/- 9.1mm) -> place wall L-brackets at Z=42..58 and Z=89..105
    wall_bracket_placements = (
        {"x": X_L_IN, "y": Y_B_IN, "z": 42.0, "rot_z": -90.0},
        {"x": X_L_IN, "y": Y_B_IN, "z": 89.0, "rot_z": -90.0},
        {"x": X_R_IN, "y": Y_B_IN, "z": 42.0, "rot_z": 180.0},
        {"x": X_R_IN, "y": Y_B_IN, "z": 89.0, "rot_z": 180.0},
        {"x": X_M_L, "y": Y_B_IN, "z": 42.0, "rot_z": 180.0},
        {"x": X_M_L, "y": Y_B_IN, "z": 89.0, "rot_z": 180.0},
        {"x": X_M_R, "y": Y_B_IN, "z": 42.0, "rot_z": -90.0},
        {"x": X_M_R, "y": Y_B_IN, "z": 89.0, "rot_z": -90.0},
    )

    # Low L-brackets (18x18x10 mm): clear of front/garden vertical tabs (Z=17+/-7 and Z=24+/-7) -> sit cleanly at Z=1.0..11.0 or Z=35..45
    low_bracket_placements = (
        {"x": X_L_IN, "y": Y_F_IN, "z": 1.0, "rot_z": 0.0},
        {"x": X_R_IN, "y": Y_F_IN, "z": 1.0, "rot_z": 90.0},
        {"x": GX_L_IN, "y": GY_F_IN, "z": 1.0, "rot_z": 0.0},
        {"x": GX_L_IN, "y": GY_B_IN, "z": 1.0, "rot_z": -90.0},
        {"x": GX_R_IN, "y": GY_F_IN, "z": 1.0, "rot_z": 90.0},
        {"x": GX_R_IN, "y": GY_B_IN, "z": 1.0, "rot_z": 180.0},
    )

    # Seam join clips (34x9.2x9.0 mm U-channel gripping 3.0mm wall edge from above with 0.2mm clearance)
    # Placed on top edges of split panels (P02, P05, P15)
    # Exact seam coordinates computed dynamically from split plan
    _, split_info = build_panel_piece_specs(cfg)
    p02_cut = 10.0 + split_info["P02_WALL_BACK"]["u_cuts_mm"][0]
    p05_cut = 10.0 + split_info["P05_WALL_FRONT"]["u_cuts_mm"][0]
    p15_cut = 8.0 + split_info["P15_TECH_FASCIA"]["u_cuts_mm"][0]

    # U-channel local coords: X in [0..34], Y in [0..9.2] (channel Y in [3.0..6.2] centered at 4.6), Z in [0..9.0] (open down, solid cap at Z=6..9)
    seam_clip_placements = (
        # Top of P02_WALL_BACK at Y=[379..382] (center 380.5), Z_top=147 -> offset clear of P06_WALL_MID (X=201.5)
        {"x": p02_cut - 11.5, "y": 380.5 - 4.6, "z": Z_WALL_TOP - 6.0, "rot_z": 0.0},
        # Top of P05_WALL_FRONT low wall at Y=[192..195] (center 193.5), Z_top=34 -> offset clear of CenterPillar (X=214.0)
        {"x": p05_cut - 5.0, "y": 193.5 - 4.6, "z": Z_CUT_H - 6.0, "rot_z": 0.0},
        # Top of P15_TECH_FASCIA USB cutaway at Y=[10..13] (center 11.5), Z_top=16 -> clip Z=[10..19]
        {"x": p15_cut - 17.0, "y": 11.5 - 4.6, "z": 16.0 - 6.0, "rot_z": 0.0},
    )

    # Base feet (30x30x14 mm): bottom pad Z=-14..-3 (11mm lift clearing P17 at Z=-6..-3), outer lip outside [0..base_L]x[0..base_W]
    # Local foot: corner pad X in [-3..27], Y in [-3..27], Z in [0..11]; outer L-lip on X=[-3..0] & Y=[-3..0] from Z=11..14
    # In print orientation: shifted to [0..30]x[0..30]x[0..14]
    foot_placements = (
        {"x": -3.0, "y": -3.0, "z": -14.0, "rot_z": 0.0},
        {"x": base_L + 3.0, "y": -3.0, "z": -14.0, "rot_z": 90.0},
        {"x": base_L + 3.0, "y": base_W + 3.0, "z": -14.0, "rot_z": 180.0},
        {"x": -3.0, "y": base_W + 3.0, "z": -14.0, "rot_z": -90.0},
        # 2 mid-edge supports (rotated to cradle X=0 and X=base_L midpoints clear of seam joiners)
        {"x": -3.0, "y": 210.0, "z": -14.0, "rot_z": 0.0, "mode": "edge"},
        {"x": base_L + 3.0, "y": 210.0, "z": -14.0, "rot_z": 180.0, "mode": "edge"},
    )

    # SUP05: 4x Hub PCB M3x10 standoffs at exact 90x70 mm pattern (Z = 6+T .. 6+T+10 = 9..19)
    sup05_placements = tuple(
        {"x": pcb_cx + sx * pcb_hx / 2.0, "y": pcb_cy + sy * pcb_hy / 2.0, "z": 6.0 + T, "rot_z": 0.0}
        for sx in (-1.0, 1.0)
        for sy in (-1.0, 1.0)
    )

    # SUP06: 4x P16 plate M3x6 standoffs at exact 116x96 mm pattern (Z = 0..6)
    sup06_placements = tuple(
        {"x": pcb_cx + sx * plate_pitch_x / 2.0, "y": pcb_cy + sy * plate_pitch_y / 2.0, "z": 0.0, "rot_z": 0.0}
        for sx in (-1.0, 1.0)
        for sy in (-1.0, 1.0)
    )

    # SUP07: 1-piece Hub PCB carrier frame (100x80x10 mm, exact 90x70 mm pattern)
    sup07_placements = (
        {"x": pcb_cx - 50.0, "y": pcb_cy - 40.0, "z": 6.0 + T, "rot_z": 0.0},
    )

    # SUP08: 11x M3x8 module standoffs (4x Relay1, 4x Relay2, 1x DHT11, 1x KY-037, 1x LM393)
    sup08_list: list[dict[str, Any]] = []
    for rcx, rcy in ((rly1_cx, rly1_cy), (rly2_cx, rly2_cy)):
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                sup08_list.append({
                    "x": rcx + sx * rly_pitch_x / 2.0,
                    "y": rcy + sy * rly_pitch_y / 2.0,
                    "z": 0.0,
                    "rot_z": 0.0,
                })
    # Include the 8 vertical base standoffs in default 3D assembly (DHT11/KY-037/LM393 are wall-mounted)
    sup08_placements = tuple(sup08_list)

    # SUP09: 1-piece Relay caddy (50x26x8 mm, exact 44.5x20.5 mm pattern)
    sup09_placements = (
        {"x": rly1_cx - 25.0, "y": rly1_cy - 13.0, "z": 0.0, "rot_z": 0.0},
        {"x": rly2_cx - 25.0, "y": rly2_cy - 13.0, "z": 0.0, "rot_z": 0.0},
    )

    # SUP10: PAM8403 clip stand (32x22x5.5 mm) centered at (182, 52, Z=0), pocket clears 21x18x3.4 mm HW_PAM8403
    sup10_placements = (
        {"x": pam_cx - 16.0, "y": pam_cy - 11.0, "z": 0.0, "rot_z": 0.0},
    )

    # SUP11: 28mm speaker rear retainer (44x14x9 mm) behind P15_TECH_FASCIA (Y=13+5.2=18.2..27.2, centered at X=223, Z=26)
    sup11_placements = (
        {"x": 223.0 - 22.0, "y": 18.4, "z": 26.0 - 7.0, "rot_z": 0.0, "rot_x": 90.0},
    )

    # SUP12: Door hinge bracket (22x12x6 mm) behind P08_DOOR_LEAF & P05_WALL_FRONT (Y=195..201) at top/bottom hinges
    # Door_Hinge_Bot at P08 local (5.5, 16.0) -> world X = 78 + 5.5 = 83.5, Z = 2 + 16 = 18.0
    # Door_Hinge_Top at P08 local (5.5, 84.0) -> world X = 83.5, Z = 2 + 84 = 86.0
    sup12_placements = (
        {"x": 70.0, "y": 195.2, "z": 18.0 - 6.0, "rot_z": 0.0, "rot_x": 90.0},
        {"x": 70.0, "y": 195.2, "z": 86.0 - 6.0, "rot_z": 0.0, "rot_x": 90.0},
    )

    supports = [
        SupportSpec(
            part_id="SUP01_CORNER_L_BRACKET_WALL",
            vi_name="Ke goc vuong 90 do tuong cao",
            category="bracket",
            qty=8,
            size_xyz=(24.0, 24.0, 16.0),
            engrave=EngraveSpec("SUP01", "24x24x16", 13.5, 4.5, 2.6, False),
            params={"arm": 24.0, "height": 16.0, "wall_t": 3.0, "hole_d": pcb_m3_d, "gusset": True},
            mating_source="P02/P03/P04/P06 vertical 90-deg corners (T=3.0 mm)",
            assembly_placements=wall_bracket_placements,
            notes="Gia co goc vuong 90 do giua cac tuong dung cao 147mm, thay keo dan dung moi; in nam phang khong can support.",
            color_rgb=(0.95, 0.56, 0.18),
        ),
        SupportSpec(
            part_id="SUP02_CORNER_L_BRACKET_LOW",
            vi_name="Ke goc vuong 90 do vach thap & vuon",
            category="bracket",
            qty=6,
            size_xyz=(18.0, 18.0, 10.0),
            engrave=EngraveSpec("SUP02", "18x18x10", 10.0, 3.6, 2.2, False),
            params={"arm": 18.0, "height": 10.0, "wall_t": 2.5, "hole_d": pcb_m3_d, "gusset": True},
            mating_source="P03/P04/P05 front cutaway & P09..P13 garden corners (T=3.0 mm)",
            assembly_placements=low_bracket_placements,
            notes="Ke goc nho gon cho vach cat mo mat truoc (34mm) va cum be nuoc - chau cay (48-54mm).",
            color_rgb=(0.93, 0.64, 0.22),
        ),
        SupportSpec(
            part_id="SUP03_SEAM_JOIN_CLIP",
            vi_name="Kep chu U gia co moi noi tach manh",
            category="clip",
            qty=10,
            size_xyz=(34.0, 9.2, 9.0),
            engrave=EngraveSpec("SUP03", "34x9x9", 17.0, 4.6, 2.4, False),
            params={"length": 34.0, "slot_w": round(T + cfg.dovetail_clearance, 2), "wall_t": 3.0, "height": 9.0},
            mating_source="Split seams of P01A/P01B/P02/P05/P15 (T=3.0 mm + 0.20 mm clearance)",
            assembly_placements=seam_clip_placements,
            notes="Kep chu U ranh 3.2mm truot khoa tren mep moi noi duoi en cua cac tam chia manh, chong cong venh.",
            color_rgb=(0.24, 0.68, 0.86),
        ),
        SupportSpec(
            part_id="SUP04_BASE_FOOT_STAND",
            vi_name="Chan de nang nha (chong cham oc day)",
            category="foot",
            qty=6,
            size_xyz=(30.0, 30.0, 14.0),
            engrave=EngraveSpec("SUP04", "30x30x14", 16.5, 16.5, 3.0, False),
            params={"size": 30.0, "lift_h": 11.0, "lip_h": 3.0, "lip_t": 3.0, "hole_d": pcb_m3_d},
            mating_source="Base perimeter 406x390 mm; clears P17_BASE_JOINER (Z=-6..-3 mm) + M3 nuts",
            assembly_placements=foot_placements[:4],
            notes="Nang tam day nha cao 11mm khoi mat ban, chong cham thanh noi P17 va dau oc M3 duoi day.",
            color_rgb=(0.30, 0.36, 0.44),
        ),
        SupportSpec(
            part_id="SUP05_HUB_PCB_STANDOFF_10MM",
            vi_name="Tru do Hub PCB M3x10 (in 3D)",
            category="standoff",
            qty=4,
            size_xyz=(10.0, 10.0, 10.0),
            engrave=EngraveSpec("S05", "10x10", 5.0, 5.0, 1.8, False),
            params={"od": 7.4, "flange_od": 10.0, "flange_h": 2.0, "height": 10.0, "bore_d": pcb_m3_d},
            mating_source="P16_PCB_PLATE 90.0x70.0 mm M3 pattern (HW_PCB Z=9..19 mm)",
            assembly_placements=sup05_placements,
            notes="Tru do M3 cao 10mm thay the tru dong gan Hub PCB 100x80mm len tam P16_PCB_PLATE (mau lo 90x70mm).",
            color_rgb=(0.88, 0.72, 0.22),
        ),
        SupportSpec(
            part_id="SUP06_PCB_PLATE_STANDOFF_6MM",
            vi_name="Tru do tam P16_PCB_PLATE M3x6 (in 3D)",
            category="standoff",
            qty=4,
            size_xyz=(10.0, 10.0, 6.0),
            engrave=EngraveSpec("S06", "10x6", 5.0, 5.0, 1.8, False),
            params={"od": 7.4, "flange_od": 10.0, "flange_h": 1.8, "height": 6.0, "bore_d": pcb_m3_d},
            mating_source="P01A_BASE_TECH -> P16_PCB_PLATE 116.0x96.0 mm corner pattern (Z=0..6 mm)",
            assembly_placements=sup06_placements,
            notes="Tru do M3 cao 6mm nang tam P16_PCB_PLATE phia tren tam day P01A_BASE_TECH (mau lo 116x96mm).",
            color_rgb=(0.82, 0.66, 0.20),
        ),
        SupportSpec(
            part_id="SUP07_PCB_CARRIER_FRAME_90X70",
            vi_name="Khung de lien khoi Hub PCB 90x70",
            category="cradle",
            qty=1,
            size_xyz=(100.0, 80.0, 10.0),
            engrave=EngraveSpec("SUP07 90x70", "100x80x10mm", 50.0, 5.0, 3.0, False),
            params={
                "outer_x": 100.0, "outer_y": 80.0, "base_h": 3.0, "total_h": 10.0,
                "pitch_x": pcb_hx, "pitch_y": pcb_hy, "boss_od": 8.0, "bore_d": pcb_m3_d,
                "cutout_x": 74.0, "cutout_y": 54.0,
            },
            mating_source="Exact P16_PCB_PLATE 90.0x70.0 mm M3 pattern for 100x80 mm Hub PCB",
            assembly_placements=sup07_placements,
            exclude_from_default_assembly=True,
            notes="Khung do lien khoi tich hop 4 tru 10mm dung chuan lo 90x70mm (thay the tuy chon cho 4 tru roi SUP05).",
            color_rgb=(0.20, 0.64, 0.42),
        ),
        SupportSpec(
            part_id="SUP08_MODULE_STANDOFF_8MM",
            vi_name="Tru do module ngoai vi M3x8 (in 3D)",
            category="standoff",
            qty=11,
            size_xyz=(9.0, 9.0, 8.0),
            engrave=EngraveSpec("S08", "9x8", 4.5, 4.5, 1.6, False),
            params={"od": 6.8, "flange_od": 9.0, "flange_h": 1.8, "height": 8.0, "bore_d": m3_mod_d},
            mating_source="Relay1 (4x), Relay2 (4x), DHT11 (1x), KY-037 (1x), LM393 (1x) M3x8 standoffs",
            assembly_placements=sup08_placements,
            notes="Tru do M3 cao 8mm thay tru nhua cho 2 module Relay (44.5x20.5mm), DHT11, KY-037 va LM393.",
            color_rgb=(0.76, 0.78, 0.82),
        ),
        SupportSpec(
            part_id="SUP09_RELAY_CADDY_44P5X20P5",
            vi_name="Khung de Relay 1 kenh 44.5x20.5",
            category="cradle",
            qty=2,
            size_xyz=(52.0, 28.0, 8.0),
            engrave=EngraveSpec("SUP09", "52x28x8", 26.0, 14.0, 2.8, False),
            params={
                "outer_x": 52.0, "outer_y": 28.0, "base_h": 2.4, "total_h": 8.0,
                "pitch_x": rly_pitch_x, "pitch_y": rly_pitch_y, "boss_od": 7.0, "bore_d": m3_mod_d,
                "cutout_x": 30.0, "cutout_y": 10.0,
            },
            mating_source="P01A_BASE_TECH Relay1 & Relay2 exact 44.5x20.5 mm M3 pattern",
            assembly_placements=sup09_placements,
            exclude_from_default_assembly=True,
            notes="Khung de 4 tru lien khoi chuan 44.5x20.5mm cho Relay 1 va Relay 2 (thay the tuy chon cho 8 tru roi SUP08).",
            color_rgb=(0.24, 0.48, 0.84),
        ),
        SupportSpec(
            part_id="SUP10_PAM8403_CLIP_STAND",
            vi_name="Gia kep mach khuếch dai PAM8403",
            category="retainer",
            qty=1,
            size_xyz=(32.0, 22.0, 6.0),
            engrave=EngraveSpec("SUP10", "32x22x6", 16.0, 11.0, 2.2, False),
            params={
                "outer_x": 32.0, "outer_y": 22.0, "base_h": 1.8, "wall_h": 6.0,
                "pcb_x": 21.6, "pcb_y": 18.6, "hole_span": pam_span, "hole_d": clamp_d,
            },
            mating_source="P01A_BASE_TECH PAM_CLAMP_L/R (26.0 mm span, Dia 3.0 mm) + PAM8403 21x18 mm",
            assembly_placements=sup10_placements,
            notes="Gia giu khay co dinh mach PAM8403 (21x18mm) khop dung 2 lo PAM_CLAMP cach nhau 26.0mm, khong can bang dinh xop.",
            color_rgb=(0.20, 0.72, 0.36),
        ),
        SupportSpec(
            part_id="SUP11_SPEAKER_28MM_RETAINER",
            vi_name="Thanh ep giu loa tron 28mm",
            category="retainer",
            qty=1,
            size_xyz=(44.0, 14.0, 9.0),
            engrave=EngraveSpec("SUP11", "44x14x9", 22.0, 7.0, 2.4, False),
            params={
                "length": 44.0, "width": 14.0, "height": 9.0, "flange_h": 3.0,
                "hole_span": spk_span, "hole_d": m3_mod_d, "spk_od": 28.4, "spk_depth": 5.4,
            },
            mating_source="P15_TECH_FASCIA Speaker_Clamp_L/R (36.0 mm span, Dia 3.5 mm) + Dia 28x5.2 mm speaker",
            assembly_placements=sup11_placements,
            notes="Thanh ep lung giu loa mini tron duong kinh 28mm ap sat luoi loa 19 lo tren P15_TECH_FASCIA.",
            color_rgb=(0.64, 0.42, 0.82),
        ),
        SupportSpec(
            part_id="SUP12_DOOR_HINGE_BRACKET",
            vi_name="Ban le cua chinh in 3D",
            category="hinge",
            qty=2,
            size_xyz=(22.0, 12.0, 6.0),
            engrave=EngraveSpec("SUP12", "22x12x6", 11.0, 6.0, 2.0, False),
            params={"length": 22.0, "width": 12.0, "height": 6.0, "plate_t": 3.0, "hole_d": clamp_d, "pin_span": 13.5},
            mating_source="P08_DOOR_LEAF Door_Hinge_Bot/Top (Dia 3.0 mm) to P05_WALL_FRONT jamb (2.0 mm clearance)",
            assembly_placements=sup12_placements,
            notes="Cap ban le in 3D noi canh cua P08_DOOR_LEAF vao khung cua P05_WALL_FRONT, giu khe ho 2.0mm.",
            color_rgb=(0.82, 0.48, 0.32),
        ),
    ]
    return supports


def get_swarm_shards(cfg: PrintConfig | None = None) -> dict[str, list[str]]:
    """Deterministic partition of all printable part IDs into 4 non-overlapping /swarm shards."""
    pieces, _ = build_panel_piece_specs(cfg)
    supports = build_support_specs(cfg)

    std_ids = [p.part_id for p in pieces if p.piece_count == 1]
    split_base_ids = [
        p.part_id for p in pieces
        if p.piece_count > 1 and p.source_panel_id in ("P01A_BASE_TECH", "P01B_BASE_HOUSE")
    ]
    split_wall_ids = [
        p.part_id for p in pieces
        if p.piece_count > 1 and p.source_panel_id not in ("P01A_BASE_TECH", "P01B_BASE_HOUSE")
    ]
    support_ids = [s.part_id for s in supports]

    return {
        "panels-std": std_ids,
        "panels-split-base": split_base_ids,
        "panels-split-walls": split_wall_ids,
        "supports": support_ids,
    }


if __name__ == "__main__":
    cfg = PrintConfig()
    pieces, split_summary = build_panel_piece_specs(cfg)
    supports = build_support_specs(cfg)
    shards = get_swarm_shards(cfg)
    print(f"Total panel pieces: {len(pieces)} (from {len(split_summary)} unique panels)")
    for pid, info in split_summary.items():
        if info["is_split"]:
            print(f"  SPLIT {pid}: {info['source_width_mm']}x{info['source_height_mm']} -> grid {info['grid']} ({info['piece_count']} pcs) u={info['u_cuts_mm']} v={info['v_cuts_mm']}")
    print(f"Total supports: {len(supports)}")
    for k, v in shards.items():
        print(f"  Shard {k}: {len(v)} parts -> {v[:4]}{'...' if len(v) > 4 else ''}")
