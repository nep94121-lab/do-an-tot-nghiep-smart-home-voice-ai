"""2D Bin-Packing & Multi-Object Build Plate Exporter for 180 x 200 x 250 mm FDM Bed.

Packs every printable part instance (all qty expanded) flat (Z=0) onto the minimum
possible number of build plates within the 170 x 190 x 245 mm usable region (5 mm margin
on a 180 x 200 x 250 mm bed) with >= 3.0 mm spacing between all parts and 0/90-deg rotation.

Outputs under `hardware/in 3 d/plates/`:
  - `PLATEnn_<short-content>.stl`  Combined binary STL positioned in [5..175] x [5..195]
  - `PLATEnn_<short-content>.3mf`  Valid multi-object 3MF archive (separate named objects,
                                   positioned in 180x200 bed coords ready to slice in PrusaSlicer)
  - `build_meta/plates_manifest.json` Complete plate mapping, lower-bound math, & bijection proof.

Usage:
    python "hardware/in 3 d/scripts/nest_plates.py"
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import pathlib
import re
import sys
import time
import zipfile
from typing import Any

import numpy as np
import trimesh

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PRINT3D_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import print_domain as pd_mod

PARTS_DIR = PRINT3D_ROOT / "parts"
PLATES_DIR = PRINT3D_ROOT / "plates"
META_DIR = PRINT3D_ROOT / "build_meta"


@dataclass(frozen=True)
class PackItem:
    inst_id: str
    part_id: str
    kind: str  # "panel", "support", "furniture"
    group: str  # short content group tag
    w: float
    h: float
    z: float
    solid_xy_area: float
    bbox_xy_area: float
    stl_path: pathlib.Path


@dataclass
class PlacedItem:
    item: PackItem
    x: float  # actual bed X_min (mm, >= 5.0)
    y: float  # actual bed Y_min (mm, >= 5.0)
    w_placed: float
    h_placed: float
    rotated_90: bool


class MaxRectsBin:
    """2D MaxRects bin packer with 90-deg rotation and exact non-overlap guarantee."""

    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height
        self.free_rects: list[tuple[float, float, float, float]] = [(0.0, 0.0, width, height)]
        self.used_rects: list[tuple[float, float, float, float]] = []
        self.placements: list[tuple[PackItem, float, float, float, float, bool]] = []

    def find_position(self, rw: float, rh: float, method: str = "BSSF") -> tuple[float, float, float, float, bool, tuple[float, float]] | None:
        best_score = (float("inf"), float("inf"))
        best_choice: tuple[float, float, float, float, bool] | None = None

        orientations = [(rw, rh, False)]
        if abs(rw - rh) > 1e-4:
            orientations.append((rh, rw, True))

        for fx, fy, fw, fh in self.free_rects:
            for pw, ph, rot in orientations:
                if pw <= fw + 1e-6 and ph <= fh + 1e-6:
                    rem_x = fw - pw
                    rem_y = fh - ph
                    if method == "BSSF":
                        score = (min(rem_x, rem_y), max(rem_x, rem_y))
                    elif method == "BLSF":
                        score = (max(rem_x, rem_y), min(rem_x, rem_y))
                    elif method == "BAF":
                        score = (fw * fh - pw * ph, min(rem_x, rem_y))
                    elif method == "BL":
                        score = (fy + ph, fx)
                    else:
                        score = (min(rem_x, rem_y), max(rem_x, rem_y))
                    if score < best_score:
                        best_score = score
                        best_choice = (fx, fy, pw, ph, rot)

        if best_choice is None:
            return None
        return (*best_choice, best_score)

    def place(self, item: PackItem, x: float, y: float, pw: float, ph: float, rot: bool) -> None:
        rect = (x, y, pw, ph)
        self.used_rects.append(rect)
        self.placements.append((item, x, y, pw, ph, rot))
        self._split_free_rects(rect)
        self._prune_free_rects()

    def _split_free_rects(self, used: tuple[float, float, float, float]) -> None:
        ux, uy, uw, uh = used
        ux2, uy2 = ux + uw, uy + uh
        new_free: list[tuple[float, float, float, float]] = []
        for fx, fy, fw, fh in self.free_rects:
            fx2, fy2 = fx + fw, fy + fh
            if ux >= fx2 - 1e-7 or ux2 <= fx + 1e-7 or uy >= fy2 - 1e-7 or uy2 <= fy + 1e-7:
                new_free.append((fx, fy, fw, fh))
                continue
            if ux > fx + 1e-6:
                new_free.append((fx, fy, ux - fx, fh))
            if ux2 < fx2 - 1e-6:
                new_free.append((ux2, fy, fx2 - ux2, fh))
            if uy > fy + 1e-6:
                new_free.append((fx, fy, fw, uy - fy))
            if uy2 < fy2 - 1e-6:
                new_free.append((fx, uy2, fw, fy2 - uy2))
        self.free_rects = new_free

    def _prune_free_rects(self) -> None:
        pruned: list[tuple[float, float, float, float]] = []
        n = len(self.free_rects)
        for i in range(n):
            ax, ay, aw, ah = self.free_rects[i]
            ax2, ay2 = ax + aw, ay + ah
            contained = False
            for j in range(n):
                if i == j:
                    continue
                bx, by, bw, bh = self.free_rects[j]
                bx2, by2 = bx + bw, by + bh
                if ax >= bx - 1e-6 and ay >= by - 1e-6 and ax2 <= bx2 + 1e-6 and ay2 <= by2 + 1e-6:
                    if j < i or (abs(ax - bx) > 1e-6 or abs(ay - by) > 1e-6 or abs(aw - bw) > 1e-6 or abs(ah - bh) > 1e-6):
                        contained = True
                        break
            if not contained and aw > 0.5 and ah > 0.5:
                pruned.append((ax, ay, aw, ah))
        self.free_rects = pruned


def _group_tag(part_id: str, kind: str) -> str:
    if kind == "furniture":
        return "furniture"
    if kind == "support":
        return "mounts"
    if part_id.startswith(("P01A", "P01B", "P17")):
        return "base"
    if part_id.startswith(("P02", "P03", "P04", "P05", "P06", "P07", "P08")):
        return "walls"
    if part_id.startswith(("P09", "P10", "P11", "P12", "P13", "P14")):
        return "garden"
    return "tech"


def _compute_mesh_xy_solid_area(mesh: trimesh.Trimesh) -> float:
    """Compute true 2D projected XY footprint area of a flat-printed mesh."""
    tris = mesh.triangles
    # 2D cross product magnitude / 2 for upward-facing triangles (normal_z > 0.5)
    nz = mesh.face_normals[:, 2]
    up = tris[nz > 0.5]
    if len(up) == 0:
        return float(mesh.extents[0] * mesh.extents[1])
    v0, v1, v2 = up[:, 0, :2], up[:, 1, :2], up[:, 2, :2]
    cross = (v1[:, 0] - v0[:, 0]) * (v2[:, 1] - v0[:, 1]) - (v1[:, 1] - v0[:, 1]) * (v2[:, 0] - v0[:, 0])
    return round(float(0.5 * np.abs(cross).sum()), 2)


def load_pack_items() -> list[PackItem]:
    items: list[PackItem] = []
    for mp in sorted(META_DIR.glob("*.json")):
        if mp.stem in ("fit_table", "assembly_report", "plates_manifest", "slice_report", "user_like_test_report"):
            continue
        meta = json.loads(mp.read_text(encoding="utf-8"))
        if "part_id" not in meta or "kind" not in meta:
            continue
        pid = meta["part_id"]
        kind = meta["kind"]
        qty = int(meta["qty"])
        stl_p = PARTS_DIR / f"{pid}.stl"
        mesh = trimesh.load(str(stl_p), force="mesh")
        ext = mesh.extents
        w, h, z = round(float(ext[0]), 3), round(float(ext[1]), 3), round(float(ext[2]), 3)
        solid_area = _compute_mesh_xy_solid_area(mesh)
        bbox_area = round(w * h, 2)
        grp = _group_tag(pid, kind)
        for q_idx in range(1, qty + 1):
            inst_id = pid if qty == 1 else f"{pid}_copy{q_idx}of{qty}"
            items.append(PackItem(
                inst_id=inst_id,
                part_id=pid,
                kind=kind,
                group=grp,
                w=w,
                h=h,
                z=z,
                solid_xy_area=solid_area,
                bbox_xy_area=bbox_area,
                stl_path=stl_p,
            ))
    return items


def run_packing(items: list[PackItem], cfg: pd_mod.PrintConfig) -> list[list[PlacedItem]]:
    """Run multi-heuristic MaxRects 2D bin packing; minimize plate count first, then Z-spread & cohesion."""
    sp = cfg.plate_spacing  # 3.0 mm
    bin_w = cfg.usable_x + sp  # 173.0
    bin_h = cfg.usable_y + sp  # 193.0

    sort_orders: list[tuple[str, list[PackItem]]] = [
        ("area_desc", sorted(items, key=lambda it: (it.bbox_xy_area, max(it.w, it.h), it.z), reverse=True)),
        ("maxside_desc", sorted(items, key=lambda it: (max(it.w, it.h), it.bbox_xy_area, it.z), reverse=True)),
        ("perim_desc", sorted(items, key=lambda it: (it.w + it.h, it.bbox_xy_area), reverse=True)),
        ("height_band_area", sorted(items, key=lambda it: (0 if it.z <= 3.5 else (1 if it.z <= 15.0 else 2), -it.bbox_xy_area, -max(it.w, it.h)))),
        ("tall_first_area", sorted(items, key=lambda it: (0 if it.z > 15.0 else (1 if it.z > 3.5 else 2), -it.bbox_xy_area))),
        ("group_area", sorted(items, key=lambda it: ({"base": 0, "walls": 1, "garden": 2, "tech": 3, "furniture": 4, "mounts": 5}[it.group], -it.bbox_xy_area))),
    ]

    best_bins: list[MaxRectsBin] | None = None
    best_rank: tuple[int, int, float, float] | None = None
    best_tag = ""

    def _pack_sequence(ordered: list[PackItem], method: str, global_best_bin: bool) -> list[MaxRectsBin]:
        bins: list[MaxRectsBin] = []
        for it in ordered:
            pw, ph = it.w + sp, it.h + sp
            chosen_bin: MaxRectsBin | None = None
            chosen_pos: tuple[float, float, float, float, bool] | None = None
            chosen_score = (float("inf"), float("inf"), float("inf"))

            for b in bins:
                res = b.find_position(pw, ph, method=method)
                if res is None:
                    continue
                fx, fy, uw, uh, rot, sc = res
                z_diff = abs(it.z - max(p[0].z for p in b.placements)) if b.placements else 0.0
                full_sc = (sc[0], sc[1], z_diff)
                if not global_best_bin:
                    chosen_bin = b
                    chosen_pos = (fx, fy, uw, uh, rot)
                    break
                if full_sc < chosen_score:
                    chosen_score = full_sc
                    chosen_bin = b
                    chosen_pos = (fx, fy, uw, uh, rot)

            if chosen_bin is None:
                nb = MaxRectsBin(bin_w, bin_h)
                res = nb.find_position(pw, ph, method=method)
                if res is None:
                    raise RuntimeError(f"Item {it.inst_id} ({it.w}x{it.h}) does not fit usable bed {cfg.usable_x}x{cfg.usable_y}!")
                fx, fy, uw, uh, rot, _ = res
                nb.place(it, fx, fy, uw, uh, rot)
                bins.append(nb)
            else:
                assert chosen_pos is not None
                fx, fy, uw, uh, rot = chosen_pos
                chosen_bin.place(it, fx, fy, uw, uh, rot)
        return bins

    def _eval_bins(bins: list[MaxRectsBin]) -> tuple[int, int, float, float]:
        lone_small = sum(
            1 for b in bins
            if len(b.placements) == 1 and b.placements[0][0].bbox_xy_area < 0.45 * (cfg.usable_x * cfg.usable_y)
        )
        z_spread = sum((max(p[0].z for p in b.placements) - min(p[0].z for p in b.placements)) for b in bins) / max(1, len(bins))
        min_util = min(sum(p[0].bbox_xy_area for p in b.placements) / (cfg.usable_x * cfg.usable_y) for b in bins)
        return (len(bins), lone_small, round(z_spread, 2), round(-min_util, 4))

    for sname, ordered in sort_orders:
        for method in ("BSSF", "BAF", "BLSF", "BL"):
            for global_best_bin in (True, False):
                bins = _pack_sequence(ordered, method, global_best_bin)
                rank = _eval_bins(bins)
                if best_rank is None or rank < best_rank:
                    best_rank = rank
                    best_bins = bins
                    best_tag = f"{sname}/{method}/global={global_best_bin}"

    # Iterative promote-sparse-bin refinement (deterministic local search to eliminate any low-utilization trailing plate)
    import random
    rng = random.Random(20261126)
    base_large = sorted(items, key=lambda it: (it.bbox_xy_area, max(it.w, it.h)), reverse=True)
    for trial in range(120):
        if trial < 40 and best_bins is not None:
            # Promote items from the least-utilized bin to just after the single-plate giant panels (>24000 mm2)
            sparse_bin = min(best_bins, key=lambda b: sum(p[0].bbox_xy_area for p in b.placements))
            sparse_ids = {p[0].inst_id for p in sparse_bin.placements}
            giants = [it for it in base_large if it.bbox_xy_area >= 24000.0 and it.inst_id not in sparse_ids]
            promoted = [it for it in base_large if it.inst_id in sparse_ids]
            rest = [it for it in base_large if it.bbox_xy_area < 24000.0 and it.inst_id not in sparse_ids]
            if trial % 2 == 1:
                rng.shuffle(rest[: min(24, len(rest))])
            seq = giants + promoted + rest
        else:
            # Area-biased deterministic jittered sort (keeps big items near front while varying pairings)
            seq = sorted(items, key=lambda it: it.bbox_xy_area * (0.75 + 0.50 * rng.random()), reverse=True)
        method = ("BAF", "BSSF", "BLSF")[trial % 3]
        bins = _pack_sequence(seq, method, True)
        rank = _eval_bins(bins)
        if best_rank is None or rank < best_rank:
            best_rank = rank
            best_bins = bins
            best_tag = f"refine#{trial}/{method}"

    assert best_bins is not None
    print(f"Best packing strategy: {best_tag} -> {len(best_bins)} plates (rank={best_rank})")

    # Convert to actual bed coordinates (offset by bed_margin = 5.0 mm, and center each plate's used bbox on the 180x200 bed!)
    plates: list[list[PlacedItem]] = []
    for b in best_bins:
        raw: list[PlacedItem] = []
        for it, rx, ry, uw, uh, rot in b.placements:
            w_act = it.h if rot else it.w
            h_act = it.w if rot else it.h
            raw.append(PlacedItem(
                item=it,
                x=round(cfg.bed_margin + rx, 3),
                y=round(cfg.bed_margin + ry, 3),
                w_placed=round(w_act, 3),
                h_placed=round(h_act, 3),
                rotated_90=rot,
            ))
        # Center the packed group nicely inside [5..175] x [5..195] (visually balanced on 180x200 bed!)
        min_x = min(p.x for p in raw)
        min_y = min(p.y for p in raw)
        max_x = max(p.x + p.w_placed for p in raw)
        max_y = max(p.y + p.h_placed for p in raw)
        dx = round((cfg.bed_x - (max_x - min_x)) / 2.0 - min_x, 3)
        dy = round((cfg.bed_y - (max_y - min_y)) / 2.0 - min_y, 3)
        # Clamp shifts so every part remains strictly inside [bed_margin, bed - bed_margin]
        dx = max(cfg.bed_margin - min_x, min(cfg.bed_x - cfg.bed_margin - max_x, dx))
        dy = max(cfg.bed_margin - min_y, min(cfg.bed_y - cfg.bed_margin - max_y, dy))
        for p in raw:
            p.x = round(p.x + dx, 3)
            p.y = round(p.y + dy, 3)
        plates.append(raw)

    # Sort plates sensibly: base first, then walls, then garden/tech, then furniture/mounts
    def _plate_sort_key(pl: list[PlacedItem]) -> tuple[int, float]:
        order = {"base": 0, "walls": 1, "garden": 2, "tech": 3, "furniture": 4, "mounts": 5}
        dom = max(set(p.item.group for p in pl), key=lambda g: sum(p.item.bbox_xy_area for p in pl if p.item.group == g))
        return (order.get(dom, 9), -sum(p.item.bbox_xy_area for p in pl))

    plates.sort(key=_plate_sort_key)
    return plates


def _plate_short_slug(pl: list[PlacedItem]) -> str:
    """Create a concise, informative filename slug describing what sits on a plate."""
    by_grp: dict[str, float] = {}
    for p in pl:
        by_grp[p.item.group] = by_grp.get(p.item.group, 0.0) + p.item.bbox_xy_area
    top_grps = [g for g, _ in sorted(by_grp.items(), key=lambda kv: kv[1], reverse=True)][:2]
    slug = "_".join(top_grps)
    return re.sub(r"[^a-z0-9_]+", "", slug.lower()) or "mixed"


def _transform_mesh_for_plate(mesh: trimesh.Trimesh, pl_item: PlacedItem) -> tuple[trimesh.Trimesh, list[float]]:
    """Return positioned mesh copy and exact 3MF 3x4 row-major affine matrix for this placement."""
    m = mesh.copy()
    # Normalize mesh origin to (0, 0, 0) just in case
    bmin = m.bounds[0]
    m.apply_translation(-bmin)

    if pl_item.rotated_90:
        # Rotate +90 deg around Z: (x, y, z) -> (-y, x, z), then shift X by +orig_h (= w_placed) so X_min = 0!
        R = trimesh.transformations.rotation_matrix(math.pi / 2.0, [0, 0, 1])
        m.apply_transform(R)
        m.apply_translation([pl_item.w_placed, 0.0, 0.0])
        tx = pl_item.x + pl_item.w_placed
        ty = pl_item.y
        # 3MF transform is 4x3 affine (row-vector convention: [x' y' z'] = [x y z 1] * M)
        # x' = -y + tx, y' = x + ty, z' = z
        tf_3mf = [0.0, 1.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 1.0, round(tx, 4), round(ty, 4), 0.0]
    else:
        tx = pl_item.x
        ty = pl_item.y
        tf_3mf = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, round(tx, 4), round(ty, 4), 0.0]

    m.apply_translation([pl_item.x, pl_item.y, 0.0])
    return m, tf_3mf


def write_multi_object_3mf(
    out_3mf: pathlib.Path,
    objects: list[tuple[str, trimesh.Trimesh, list[float]]],
    plate_title: str,
) -> None:
    """Write a clean, PrusaSlicer-native multi-object 3MF (unit=millimeter) with separate named objects."""
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        '</Types>\n'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        '</Relationships>\n'
    )

    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">',
        f'  <metadata name="Title">{plate_title}</metadata>',
        '  <metadata name="Application">SmartHome-3DPrint-v2-Nester</metadata>',
        '  <metadata name="Description">180x200x250 mm build plate, zero screws/glue, flat Z=0</metadata>',
        '  <resources>',
    ]

    build_items: list[str] = []
    for obj_id, (name, base_mesh, tf_3mf) in enumerate(objects, start=1):
        # Write mesh in its own normalized local coords [0..w]x[0..h]x[0..z] and apply exact bed transform in <item>!
        m = base_mesh.copy()
        m.apply_translation(-m.bounds[0])
        verts = m.vertices
        faces = m.faces
        lines.append(f'    <object id="{obj_id}" name="{name}" type="model">')
        lines.append('      <mesh>')
        lines.append('        <vertices>')
        for v in verts:
            lines.append(f'          <vertex x="{v[0]:.4f}" y="{v[1]:.4f}" z="{v[2]:.4f}"/>')
        lines.append('        </vertices>')
        lines.append('        <triangles>')
        for f in faces:
            lines.append(f'          <triangle v1="{int(f[0])}" v2="{int(f[1])}" v3="{int(f[2])}"/>')
        lines.append('        </triangles>')
        lines.append('      </mesh>')
        lines.append('    </object>')
        tf_str = " ".join(f"{val:.4f}" for val in tf_3mf)
        build_items.append(f'    <item objectid="{obj_id}" transform="{tf_str}"/>')

    lines.append('  </resources>')
    lines.append('  <build>')
    lines.extend(build_items)
    lines.append('  </build>')
    lines.append('</model>')
    model_xml = "\n".join(lines) + "\n"

    out_3mf.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(out_3mf), "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("3D/3dmodel.model", model_xml)


def verify_plates_gate_g3(
    items: list[PackItem],
    plates: list[list[PlacedItem]],
    cfg: pd_mod.PrintConfig,
) -> list[str]:
    """Gate G3 verification: bijection, >=3.0 mm spacing, strictly inside [5..175]x[5..195], zero lone small part."""
    errors: list[str] = []
    expected_ids = {it.inst_id for it in items}
    seen_ids: list[str] = []

    for p_idx, pl in enumerate(plates, 1):
        if len(pl) == 1 and pl[0].item.bbox_xy_area < 0.45 * (cfg.usable_x * cfg.usable_y):
            errors.append(f"PLATE{p_idx:02d} has only one small part: {pl[0].item.inst_id}")
        for i, a in enumerate(pl):
            seen_ids.append(a.item.inst_id)
            if a.x < cfg.bed_margin - 0.02 or a.y < cfg.bed_margin - 0.02:
                errors.append(f"PLATE{p_idx:02d} {a.item.inst_id} violates low bed margin: ({a.x}, {a.y})")
            if a.x + a.w_placed > cfg.bed_x - cfg.bed_margin + 0.02 or a.y + a.h_placed > cfg.bed_y - cfg.bed_margin + 0.02:
                errors.append(f"PLATE{p_idx:02d} {a.item.inst_id} exceeds usable bed: ({a.x+a.w_placed}, {a.y+a.h_placed})")
            if a.item.z > cfg.usable_z + 0.02:
                errors.append(f"PLATE{p_idx:02d} {a.item.inst_id} exceeds height {cfg.usable_z}")
            for j in range(i + 1, len(pl)):
                b = pl[j]
                gap_x = max(b.x - (a.x + a.w_placed), a.x - (b.x + b.w_placed))
                gap_y = max(b.y - (a.y + a.h_placed), a.y - (b.y + b.h_placed))
                sep = max(gap_x, gap_y)
                if sep < cfg.plate_spacing - 0.05:
                    errors.append(f"PLATE{p_idx:02d} spacing violation ({sep:.2f} mm < {cfg.plate_spacing}): {a.item.inst_id} vs {b.item.inst_id}")

    if len(seen_ids) != len(items) or set(seen_ids) != expected_ids:
        missing = expected_ids - set(seen_ids)
        errors.append(f"Bijection mismatch: expected {len(items)}, placed {len(seen_ids)}, missing={missing}")
    return errors


def main() -> int:
    t0 = time.time()
    cfg = pd_mod.PrintConfig()
    items = load_pack_items()

    usable_area = cfg.usable_x * cfg.usable_y  # 32,300 mm^2
    total_bbox_area = round(sum(it.bbox_xy_area for it in items), 2)
    total_solid_area = round(sum(it.solid_xy_area for it in items), 2)
    lb_bbox_exact = total_bbox_area / usable_area
    lb_solid_exact = total_solid_area / usable_area
    lb_bbox = math.ceil(lb_bbox_exact)
    lb_solid = math.ceil(lb_solid_exact)

    plates = run_packing(items, cfg)
    g3_errors = verify_plates_gate_g3(items, plates, cfg)
    if g3_errors:
        for e in g3_errors:
            print(f"[G3 FAIL] {e}")
        return 1

    # Clear old plate files and export fresh STL + multi-object 3MF per plate
    PLATES_DIR.mkdir(parents=True, exist_ok=True)
    for old in PLATES_DIR.glob("PLATE*.*"):
        old.unlink()

    mesh_cache: dict[str, trimesh.Trimesh] = {}
    plate_records: list[dict[str, Any]] = []

    for idx, pl in enumerate(plates, start=1):
        slug = _plate_short_slug(pl)
        plate_id = f"PLATE{idx:02d}_{slug}"
        stl_out = PLATES_DIR / f"{plate_id}.stl"
        mf_out = PLATES_DIR / f"{plate_id}.3mf"

        positioned_meshes: list[trimesh.Trimesh] = []
        mf_objects: list[tuple[str, trimesh.Trimesh, list[float]]] = []
        item_records: list[dict[str, Any]] = []

        for pi in pl:
            if pi.item.part_id not in mesh_cache:
                mesh_cache[pi.item.part_id] = trimesh.load(str(pi.item.stl_path), force="mesh")
            base_m = mesh_cache[pi.item.part_id]
            pos_m, tf_3mf = _transform_mesh_for_plate(base_m, pi)
            positioned_meshes.append(pos_m)
            mf_objects.append((pi.item.inst_id, base_m, tf_3mf))
            item_records.append({
                "inst_id": pi.item.inst_id,
                "part_id": pi.item.part_id,
                "kind": pi.item.kind,
                "group": pi.item.group,
                "x_mm": pi.x,
                "y_mm": pi.y,
                "w_mm": pi.w_placed,
                "h_mm": pi.h_placed,
                "z_mm": pi.item.z,
                "rotated_90": pi.rotated_90,
                "bbox_area_mm2": pi.item.bbox_xy_area,
                "solid_area_mm2": pi.item.solid_xy_area,
            })

        combined = trimesh.util.concatenate(positioned_meshes)
        combined.export(str(stl_out), file_type="stl")
        write_multi_object_3mf(mf_out, mf_objects, plate_id)

        bmin = combined.bounds[0]
        bmax = combined.bounds[1]
        used_w = round(float(bmax[0] - bmin[0]), 2)
        used_h = round(float(bmax[1] - bmin[1]), 2)
        max_z = round(float(bmax[2]), 2)
        bbox_util = round(100.0 * sum(p.item.bbox_xy_area for p in pl) / usable_area, 1)
        solid_util = round(100.0 * sum(p.item.solid_xy_area for p in pl) / usable_area, 1)

        plate_records.append({
            "plate_index": idx,
            "plate_id": plate_id,
            "stl_file": f"plates/{stl_out.name}",
            "threemf_file": f"plates/{mf_out.name}",
            "part_count": len(pl),
            "unique_parts": sorted({p.item.part_id for p in pl}),
            "bed_bounds_min_mm": [round(float(bmin[0]), 2), round(float(bmin[1]), 2), round(float(bmin[2]), 2)],
            "bed_bounds_max_mm": [round(float(bmax[0]), 2), round(float(bmax[1]), 2), round(float(bmax[2]), 2)],
            "used_bbox_mm": [used_w, used_h, max_z],
            "bbox_utilization_pct": bbox_util,
            "solid_utilization_pct": solid_util,
            "items": item_records,
        })
        print(
            f"  {plate_id:28s}: {len(pl):2d} pcs | used {used_w:5.1f}x{used_h:5.1f}x{max_z:4.1f} mm "
            f"(X={bmin[0]:.1f}..{bmax[0]:.1f}, Y={bmin[1]:.1f}..{bmax[1]:.1f}) | util={bbox_util:4.1f}%"
        )

    manifest = {
        "bed_mm": [cfg.bed_x, cfg.bed_y, cfg.bed_z],
        "margin_mm": cfg.bed_margin,
        "usable_mm": [cfg.usable_x, cfg.usable_y, cfg.usable_z],
        "min_spacing_mm": cfg.plate_spacing,
        "total_unique_parts": len({it.part_id for it in items}),
        "total_part_instances": len(items),
        "usable_area_mm2": usable_area,
        "total_bbox_area_mm2": total_bbox_area,
        "total_solid_area_mm2": total_solid_area,
        "theoretical_lower_bound_bbox_exact": round(lb_bbox_exact, 2),
        "theoretical_lower_bound_bbox_ceil": lb_bbox,
        "theoretical_lower_bound_solid_exact": round(lb_solid_exact, 2),
        "theoretical_lower_bound_solid_ceil": lb_solid,
        "achieved_plate_count": len(plate_records),
        "gate_g3_passed": True,
        "elapsed_sec": round(time.time() - t0, 2),
        "plates": plate_records,
    }
    (META_DIR / "plates_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("=== GATE G3 PLATE NESTING SUMMARY ===")
    print(f"Total unique parts: {manifest['total_unique_parts']} | Total instances placed: {manifest['total_part_instances']}")
    print(f"Usable bed area: {usable_area:.0f} mm2 (170x190)")
    print(f"Theoretical lower bound (solid footprint): {lb_solid_exact:.2f} -> {lb_solid} plates ({total_solid_area:.0f} mm2)")
    print(f"Theoretical lower bound (bbox footprint):  {lb_bbox_exact:.2f} -> {lb_bbox} plates ({total_bbox_area:.0f} mm2)")
    print(f"Achieved plates: {len(plate_records)} plates (Gate G3: PASS, elapsed {manifest['elapsed_sec']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
