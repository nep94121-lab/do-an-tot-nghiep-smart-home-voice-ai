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

import lightweight_policy as lp
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


def _rasterize_mesh_xy_mask(mesh: trimesh.Trimesh, step_mm: float = 1.0, fill_small_holes_mm2: float = 1500.0) -> np.ndarray:
    """Fast C-level PIL rasterization of projected XY solid footprint on a step_mm grid; fill small hex holes."""
    from PIL import Image, ImageDraw

    verts = mesh.vertices.copy()
    verts -= mesh.bounds[0]
    ext = mesh.extents
    nx = max(1, int(math.ceil(float(ext[0]) / step_mm)))
    ny = max(1, int(math.ceil(float(ext[1]) / step_mm)))

    # PIL Image size is (width=nx, height=ny); array is (ny, nx) -> transpose to (nx, ny)
    im = Image.new("1", (nx, ny), 0)
    draw = ImageDraw.Draw(im)

    normals = mesh.face_normals
    up_mask = np.abs(normals[:, 2]) > 0.15
    tris = verts[mesh.faces[up_mask]][:, :, :2] / step_mm
    for t in tris:
        pts = [(float(t[0, 0]), float(t[0, 1])), (float(t[1, 0]), float(t[1, 1])), (float(t[2, 0]), float(t[2, 1]))]
        draw.polygon(pts, fill=1, outline=1)
    mask = np.array(im, dtype=bool).T.copy()

    # Fill small interior holes (< fill_small_holes_mm2, e.g. 15 mm hex cutouts ~195 mm2) so no tiny peg nests inside a hex!
    if fill_small_holes_mm2 > 0.0:
        from collections import deque

        pad = np.zeros((nx + 2, ny + 2), dtype=bool)
        pad[1:-1, 1:-1] = mask
        visited = pad.copy()
        q: deque[tuple[int, int]] = deque([(0, 0)])
        visited[0, 0] = True
        while q:
            cx, cy = q.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx_, ny_ = cx + dx, cy + dy
                if 0 <= nx_ < nx + 2 and 0 <= ny_ < ny + 2 and not visited[nx_, ny_]:
                    visited[nx_, ny_] = True
                    q.append((nx_, ny_))
        hole_px = ~visited[1:-1, 1:-1]
        if np.any(hole_px):
            seen_h = np.zeros((nx, ny), dtype=bool)
            min_hole_cells = int(math.ceil(fill_small_holes_mm2 / (step_mm * step_mm)))
            hx_idx, hy_idx = np.where(hole_px)
            for sx, sy in zip(hx_idx.tolist(), hy_idx.tolist()):
                if seen_h[sx, sy]:
                    continue
                comp: list[tuple[int, int]] = []
                hq: deque[tuple[int, int]] = deque([(sx, sy)])
                seen_h[sx, sy] = True
                while hq:
                    cx, cy = hq.popleft()
                    comp.append((cx, cy))
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx_, ny_ = cx + dx, cy + dy
                        if 0 <= nx_ < nx and 0 <= ny_ < ny and hole_px[nx_, ny_] and not seen_h[nx_, ny_]:
                            seen_h[nx_, ny_] = True
                            hq.append((nx_, ny_))
                if len(comp) < min_hole_cells:
                    for cx, cy in comp:
                        mask[cx, cy] = True
    return mask


def _dilate_mask(mask: np.ndarray, radius_px: int) -> np.ndarray:
    """Exact Euclidean disk dilation on a 2D boolean mask (returns mask padded by radius_px on all sides)."""
    nx, ny = mask.shape
    out = np.zeros((nx + 2 * radius_px, ny + 2 * radius_px), dtype=bool)
    r2 = radius_px * radius_px
    for dx in range(-radius_px, radius_px + 1):
        for dy in range(-radius_px, radius_px + 1):
            if dx * dx + dy * dy <= r2:
                x0 = radius_px + dx
                y0 = radius_px + dy
                out[x0 : x0 + nx, y0 : y0 + ny] |= mask
    return out


class RasterBin:
    """2D True-Shape Occupancy-Grid Bin (170x190 mm @ 1 mm grid, 256x256 FFT search, >= 3.0 mm real clearance)."""

    FFT_N = 256

    def __init__(self, width_px: int, height_px: int, step_mm: float = 1.0, spacing_px: int = 4) -> None:
        self.W = width_px
        self.H = height_px
        self.step_mm = step_mm
        self.spacing_px = spacing_px
        self.occ_dilated = np.zeros((width_px, height_px), dtype=bool)
        self.occ_solid = np.zeros((width_px, height_px), dtype=bool)
        self._occ_fft: np.ndarray | None = None
        self.placements: list[tuple[PackItem, float, float, float, float, bool]] = []

    def _get_occ_fft(self) -> np.ndarray:
        if self._occ_fft is None:
            buf = np.zeros((self.FFT_N, self.FFT_N), dtype=np.float32)
            buf[: self.W, : self.H] = self.occ_dilated.astype(np.float32)
            self._occ_fft = np.fft.rfft2(buf)
        return self._occ_fft

    def find_position(
        self,
        item: PackItem,
        mask_0: np.ndarray,
        fft_0: np.ndarray,
        mask_90: np.ndarray,
        fft_90: np.ndarray,
        prefer_compact: bool = True,
    ) -> tuple[int, int, bool, tuple[float, float]] | None:
        occ_fft = self._get_occ_fft()
        best_choice: tuple[int, int, bool] | None = None
        best_score = (float("inf"), float("inf"))

        cur_xmax = max((p[1] + p[3] for p in self.placements), default=0.0)
        cur_ymax = max((p[2] + p[4] for p in self.placements), default=0.0)
        s = self.step_mm

        orientations = [(mask_0, fft_0, item.w, item.h, False)]
        if abs(item.w - item.h) > 1e-3 or mask_0.shape != mask_90.shape:
            orientations.append((mask_90, fft_90, item.h, item.w, True))

        for m, m_fft, pw, ph, rot in orientations:
            mw, mh = m.shape
            max_x = min(int(math.floor((self.W * s - pw) / s + 1e-6)), self.W - mw)
            max_y = min(int(math.floor((self.H * s - ph) / s + 1e-6)), self.H - mh)
            if max_x < 0 or max_y < 0:
                continue

            if not self.placements:
                # Place solid mass toward bed edges so any L-shaped cutaway merges with remaining bed margin!
                xs_m, ys_m = np.where(m)
                mean_x = float(xs_m.mean()) if len(xs_m) else mw / 2.0
                mean_y = float(ys_m.mean()) if len(ys_m) else mh / 2.0
                fx = max_x if mean_x > mw / 2.0 else 0
                fy = max_y if mean_y > mh / 2.0 else 0
                # For non-convex L-shaped panels (fill < 60%), prefer orientation maximizing the merged empty quadrant!
                fill_ratio = float(m.sum()) / max(1.0, float(mw * mh))
                if fill_ratio < 0.60 and max(item.w, item.h) <= self.W:
                    # Measure open margin along the cutaway edge (prefer wider X margin when X-cutaway aligns)
                    open_x = self.W - (mw - int(xs_m.min() if fx > 0 else (mw - 1 - xs_m.max())))
                    open_y = self.H - (mh - int(ys_m.min() if fy > 0 else (mh - 1 - ys_m.max())))
                    sc = (0.0, -float(min(open_x, open_y)) - 0.01 * float(ph))
                else:
                    sc = (0.0, float(ph))
                if sc < best_score:
                    best_score = sc
                    best_choice = (fx, fy, rot)
                continue

            conv = np.fft.irfft2(occ_fft * m_fft, s=(self.FFT_N, self.FFT_N))
            valid_map = conv[mw - 1 : mw - 1 + max_x + 1, mh - 1 : mh - 1 + max_y + 1] < 0.25
            xs, ys = np.where(valid_map)
            if len(xs) == 0:
                continue

            if prefer_compact:
                new_xmax = np.maximum(cur_xmax, xs * s + pw)
                new_ymax = np.maximum(cur_ymax, ys * s + ph)
                bbox_inc = (new_xmax * new_ymax) - (cur_xmax * cur_ymax)
                primary = bbox_inc + 0.01 * (xs + ys)
                secondary = ys + 0.1 * xs
            else:
                primary = ys + 0.05 * xs
                secondary = xs.astype(np.float64)

            idx_order = np.lexsort((secondary, primary))
            for k in idx_order[:8]:
                cx, cy = int(xs[k]), int(ys[k])
                if not np.any(self.occ_dilated[cx : cx + mw, cy : cy + mh] & m):
                    sc = (float(primary[k]), float(secondary[k]))
                    if sc < best_score:
                        best_score = sc
                        best_choice = (cx, cy, rot)
                    break

        if best_choice is None:
            return None
        return (*best_choice, best_score)

    def place(self, item: PackItem, x: int, y: int, rot: bool, mask_solid: np.ndarray, mask_dil: np.ndarray) -> None:
        mw, mh = mask_solid.shape
        r = self.spacing_px
        self.occ_solid[x : x + mw, y : y + mh] |= mask_solid
        dx0 = max(0, x - r)
        dy0 = max(0, y - r)
        dx1 = min(self.W, x + mw + r)
        dy1 = min(self.H, y + mh + r)
        sx0 = dx0 - (x - r)
        sy0 = dy0 - (y - r)
        self.occ_dilated[dx0:dx1, dy0:dy1] |= mask_dil[sx0 : sx0 + (dx1 - dx0), sy0 : sy0 + (dy1 - dy0)]
        self._occ_fft = None
        pw = item.h if rot else item.w
        ph = item.w if rot else item.h
        self.placements.append((item, float(x) * self.step_mm, float(y) * self.step_mm, pw, ph, rot))


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
        if mp.stem in ("fit_table", "assembly_report", "plates_manifest", "slice_report", "user_like_test_report", "strength_report"):
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


def run_packing(items: list[PackItem], cfg: pd_mod.PrintConfig) -> tuple[list[list[PlacedItem]], dict[str, np.ndarray]]:
    """True-shape 2D raster occupancy-grid nesting (0/90 deg, >= 3.0 mm real Euclidean clearance) minimizing plates."""
    step_mm = 1.0
    W = int(round(cfg.usable_x / step_mm))  # 170
    H = int(round(cfg.usable_y / step_mm))  # 190
    sp_px = int(math.ceil((cfg.plate_spacing + step_mm) / step_mm))  # 4 px = 4 mm -> >= 3.0 mm real clearance!
    FFT_N = RasterBin.FFT_N

    # Precompute 0-deg & 90-deg solid masks, dilated masks, and reversed FFT kernels per unique part_id
    mask_cache: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
    solid_masks_0: dict[str, np.ndarray] = {}
    for it in items:
        if it.part_id in mask_cache:
            continue
        mesh = trimesh.load(str(it.stl_path), force="mesh")
        m0 = _rasterize_mesh_xy_mask(mesh, step_mm=step_mm, fill_small_holes_mm2=1500.0)
        m90 = np.ascontiguousarray(m0.T[::-1, :])
        d0 = _dilate_mask(m0, sp_px)
        d90 = _dilate_mask(m90, sp_px)

        def _rev_fft(arr: np.ndarray) -> np.ndarray:
            buf = np.zeros((FFT_N, FFT_N), dtype=np.float32)
            rev = arr[::-1, ::-1]
            buf[: rev.shape[0], : rev.shape[1]] = rev.astype(np.float32)
            return np.fft.rfft2(buf)

        mask_cache[it.part_id] = (m0, d0, _rev_fft(m0), m90, d90, _rev_fft(m90))
        solid_masks_0[it.part_id] = m0

    def _pack_seq(ordered: list[PackItem], prefer_compact: bool, global_best: bool, force_rot_nonconvex: bool = False) -> list[RasterBin]:
        bins: list[RasterBin] = []
        for it in ordered:
            m0, d0, f0, m90, d90, f90 = mask_cache[it.part_id]
            chosen_bin: RasterBin | None = None
            chosen_pos: tuple[int, int, bool] | None = None
            chosen_sc = (float("inf"), float("inf"), float("inf"))

            for b in bins:
                res = b.find_position(it, m0, f0, m90, f90, prefer_compact=prefer_compact)
                if res is None:
                    continue
                cx, cy, rot, sc = res
                z_diff = abs(it.z - max(p[0].z for p in b.placements)) if b.placements else 0.0
                full_sc = (sc[0], sc[1], z_diff)
                if not global_best:
                    chosen_bin = b
                    chosen_pos = (cx, cy, rot)
                    break
                if full_sc < chosen_sc:
                    chosen_sc = full_sc
                    chosen_bin = b
                    chosen_pos = (cx, cy, rot)

            if chosen_bin is None:
                nb = RasterBin(W, H, step_mm=step_mm, spacing_px=sp_px)
                if force_rot_nonconvex and it.solid_xy_area / max(1.0, it.bbox_xy_area) < 0.55 and it.h <= W and it.w <= H:
                    # Force 90-deg orientation on non-convex L-shaped hosts to test opposite cutaway merge
                    mw, mh = m90.shape
                    xs_m, ys_m = np.where(m90)
                    fx = (W - mw) if float(xs_m.mean()) > mw / 2.0 else 0
                    fy = (H - mh) if float(ys_m.mean()) > mh / 2.0 else 0
                    nb.place(it, fx, fy, True, m90, d90)
                else:
                    res = nb.find_position(it, m0, f0, m90, f90, prefer_compact=prefer_compact)
                    if res is None:
                        raise RuntimeError(f"Item {it.inst_id} ({it.w}x{it.h}) does not fit usable bed {cfg.usable_x}x{cfg.usable_y}!")
                    cx, cy, rot, _ = res
                    nb.place(it, cx, cy, rot, m90 if rot else m0, d90 if rot else d0)
                bins.append(nb)
            else:
                assert chosen_pos is not None
                cx, cy, rot = chosen_pos
                chosen_bin.place(it, cx, cy, rot, m90 if rot else m0, d90 if rot else d0)
        return bins

    def _eval_bins(bins: list[RasterBin]) -> tuple[int, int, float, float]:
        lone_small = sum(
            1 for b in bins
            if len(b.placements) == 1 and b.placements[0][0].bbox_xy_area < 0.45 * (cfg.usable_x * cfg.usable_y)
        )
        z_spread = sum((max(p[0].z for p in b.placements) - min(p[0].z for p in b.placements)) for b in bins) / max(1, len(bins))
        min_util = min(sum(p[0].solid_xy_area for p in b.placements) / (cfg.usable_x * cfg.usable_y) for b in bins)
        return (len(bins), lone_small, round(z_spread, 2), round(-min_util, 4))

    sort_orders: list[tuple[str, list[PackItem]]] = [
        ("sup15_early_tight", sorted(items, key=lambda it: (0 if it.bbox_xy_area >= 14000 else (1 if it.part_id in ("P16_PCB_PLATE", "SUP15_WATER_TANK_LINER", "SUP06_HUB_PCB_SNAP_CARRIER", "P05_WALL_FRONT_piece1of3") else (2 if max(it.w, it.h) >= 50.0 else 3)), -min(it.w, it.h), -max(it.w, it.h)))),
        ("sup15_maxside", sorted(items, key=lambda it: (0 if it.bbox_xy_area >= 12000 else (1 if it.part_id == "SUP06_HUB_PCB_SNAP_CARRIER" else (2 if max(it.w, it.h) >= 40.0 else 3)), -max(it.w, it.h), -it.bbox_xy_area))),
        ("lshape_sup06_sup15", sorted(items, key=lambda it: (0 if (it.bbox_xy_area >= 14000 and it.solid_xy_area / max(1.0, it.bbox_xy_area) < 0.62) else (1 if (it.bbox_xy_area >= 11000 or it.part_id == "SUP06_HUB_PCB_SNAP_CARRIER") else (2 if it.part_id == "SUP15_WATER_TANK_LINER" else 3)), -max(it.w, it.h), -it.bbox_xy_area))),
        ("minside_desc", sorted(items, key=lambda it: (min(it.w, it.h), max(it.w, it.h), it.bbox_xy_area), reverse=True)),
        ("bbox_desc", sorted(items, key=lambda it: (it.bbox_xy_area, max(it.w, it.h), it.solid_xy_area), reverse=True)),
    ]

    best_bins: list[RasterBin] | None = None
    best_rank: tuple[int, int, float, float] | None = None
    best_tag = ""

    for sname, ordered in sort_orders:
        bins = _pack_seq(ordered, True, False, force_rot_nonconvex=False)
        rank = _eval_bins(bins)
        print(f"  [try] {sname}/compact -> {len(bins)} plates (rank={rank})", flush=True)
        if best_rank is None or rank < best_rank:
            best_rank = rank
            best_bins = bins
            best_tag = f"{sname}/compact"
        if rank[0] > 15 or rank[1] > 0:
            bins2 = _pack_seq(ordered, False, False, force_rot_nonconvex=False)
            rank2 = _eval_bins(bins2)
            print(f"  [try] {sname}/bl -> {len(bins2)} plates (rank={rank2})", flush=True)
            if rank2 < best_rank:
                best_rank = rank2
                best_bins = bins2
                best_tag = f"{sname}/bl"

    assert best_bins is not None
    print(f"Best true-shape packing strategy: {best_tag} -> {len(best_bins)} plates (rank={best_rank})", flush=True)

    # Convert to actual bed coordinates (offset by bed_margin = 5.0 mm, and center each plate's used bbox on the 180x200 bed!)
    plates: list[list[PlacedItem]] = []
    for b in best_bins:
        raw: list[PlacedItem] = []
        for it, rx, ry, pw, ph, rot in b.placements:
            raw.append(PlacedItem(
                item=it,
                x=round(cfg.bed_margin + rx, 3),
                y=round(cfg.bed_margin + ry, 3),
                w_placed=round(pw, 3),
                h_placed=round(ph, 3),
                rotated_90=rot,
            ))
        min_x = min(p.x for p in raw)
        min_y = min(p.y for p in raw)
        max_x = max(p.x + p.w_placed for p in raw)
        max_y = max(p.y + p.h_placed for p in raw)
        dx = round((cfg.bed_x - (max_x - min_x)) / 2.0 - min_x, 3)
        dy = round((cfg.bed_y - (max_y - min_y)) / 2.0 - min_y, 3)
        dx = max(cfg.bed_margin - min_x, min(cfg.bed_x - cfg.bed_margin - max_x, dx))
        dy = max(cfg.bed_margin - min_y, min(cfg.bed_y - cfg.bed_margin - max_y, dy))
        for p in raw:
            p.x = round(p.x + dx, 3)
            p.y = round(p.y + dy, 3)
        plates.append(raw)

    def _plate_sort_key(pl: list[PlacedItem]) -> tuple[int, float]:
        order = {"base": 0, "walls": 1, "garden": 2, "tech": 3, "furniture": 4, "mounts": 5}
        dom = max(set(p.item.group for p in pl), key=lambda g: sum(p.item.solid_xy_area for p in pl if p.item.group == g))
        return (order.get(dom, 9), -sum(p.item.solid_xy_area for p in pl))

    plates.sort(key=_plate_sort_key)
    return plates, solid_masks_0


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
    objects: list[tuple[str, str, str, trimesh.Trimesh, list[float]]],
    plate_title: str,
) -> dict[str, dict[str, str]]:
    """Write PrusaSlicer 2.9.7 native multi-object 3MF with baked Slic3r_PE.config & Slic3r_PE_model.config.

    Returns mapping inst_id -> per-object overrides baked into Metadata/Slic3r_PE_model.config.
    """
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        '  <Default Extension="config" ContentType="text/plain"/>\n'
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
        f'  <metadata name="Application">{lp.SLICER_APPLICATION_TAG}</metadata>',
        '  <metadata name="Description">180x200x250 mm lightweight build plate, baked R1-R3 slicer config, zero screws/glue/supports</metadata>',
        '  <resources>',
    ]

    model_cfg_lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<config>',
    ]
    baked_overrides_by_inst: dict[str, dict[str, str]] = {}

    build_items: list[str] = []
    for obj_id, (inst_name, part_id, kind, base_mesh, tf_3mf) in enumerate(objects, start=1):
        # Write mesh in its own normalized local coords [0..w]x[0..h]x[0..z] and apply exact bed transform in <item>!
        m = base_mesh.copy()
        m.apply_translation(-m.bounds[0])
        verts = m.vertices
        faces = m.faces
        n_tris = len(faces)
        lines.append(f'    <object id="{obj_id}" name="{inst_name}" type="model">')
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
        build_items.append(f'    <item objectid="{obj_id}" transform="{tf_str}" printable="1"/>')

        # Bake per-object R1-R3 slicer overrides into Metadata/Slic3r_PE_model.config
        overrides = lp.get_object_slicer_overrides(part_id, kind)
        baked_overrides_by_inst[inst_name] = dict(overrides)
        model_cfg_lines.append(f'  <object id="{obj_id}" instances_count="1">')
        model_cfg_lines.append(f'    <metadata type="object" key="name" value="{inst_name}"/>')
        for ok, ov in sorted(overrides.items()):
            model_cfg_lines.append(f'    <metadata type="object" key="{ok}" value="{ov}"/>')
        model_cfg_lines.append(f'    <volume firstid="0" lastid="{max(0, n_tris - 1)}">')
        model_cfg_lines.append(f'      <metadata type="volume" key="name" value="{inst_name}"/>')
        model_cfg_lines.append('      <metadata type="volume" key="source_object_id" value="0"/>')
        model_cfg_lines.append('      <metadata type="volume" key="source_volume_id" value="0"/>')
        model_cfg_lines.append('      <metadata type="volume" key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>')
        model_cfg_lines.append('    </volume>')
        model_cfg_lines.append('  </object>')

    lines.append('  </resources>')
    lines.append('  <build>')
    lines.extend(build_items)
    lines.append('  </build>')
    lines.append('</model>')
    model_xml = "\n".join(lines) + "\n"

    model_cfg_lines.append('</config>')
    model_cfg_xml = "\n".join(model_cfg_lines) + "\n"
    slic3r_pe_config = lp.format_slic3r_pe_config()

    out_3mf.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(out_3mf), "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("3D/3dmodel.model", model_xml)
        zf.writestr("Metadata/Slic3r_PE.config", slic3r_pe_config)
        zf.writestr("Metadata/Slic3r_PE_model.config", model_cfg_xml)
    return baked_overrides_by_inst


def verify_plates_gate_g3(
    items: list[PackItem],
    plates: list[list[PlacedItem]],
    cfg: pd_mod.PrintConfig,
    solid_masks_0: dict[str, np.ndarray] | None = None,
) -> list[str]:
    """Gate G3 verification: bijection, >=3.0 mm real Euclidean clearance, strictly inside [5..175]x[5..195]."""
    errors: list[str] = []
    expected_ids = {it.inst_id for it in items}
    seen_ids: list[str] = []
    # Exact 0.5 mm grid clearance check (dilate radius = 6 px = 3.0 mm!)
    step = 0.5
    rad_px = int(round(cfg.plate_spacing / step))
    hi_res_cache: dict[tuple[str, bool], np.ndarray] = {}

    def _get_hires(pi: PlacedItem) -> np.ndarray:
        key = (pi.item.part_id, pi.rotated_90)
        if key not in hi_res_cache:
            m = trimesh.load(str(pi.item.stl_path), force="mesh")
            m0 = _rasterize_mesh_xy_mask(m, step_mm=step, fill_small_holes_mm2=0.0)
            hi_res_cache[(pi.item.part_id, False)] = m0
            hi_res_cache[(pi.item.part_id, True)] = np.ascontiguousarray(m0.T[::-1, :])
        return hi_res_cache[key]

    bed_gx = int(round(cfg.bed_x / step))
    bed_gy = int(round(cfg.bed_y / step))

    for p_idx, pl in enumerate(plates, 1):
        if len(pl) == 1 and pl[0].item.bbox_xy_area < 0.45 * (cfg.usable_x * cfg.usable_y):
            errors.append(f"PLATE{p_idx:02d} has only one small part: {pl[0].item.inst_id}")
        occ_dil = np.zeros((bed_gx, bed_gy), dtype=bool)
        for a in pl:
            seen_ids.append(a.item.inst_id)
            if a.x < cfg.bed_margin - 0.02 or a.y < cfg.bed_margin - 0.02:
                errors.append(f"PLATE{p_idx:02d} {a.item.inst_id} violates low bed margin: ({a.x}, {a.y})")
            if a.x + a.w_placed > cfg.bed_x - cfg.bed_margin + 0.02 or a.y + a.h_placed > cfg.bed_y - cfg.bed_margin + 0.02:
                errors.append(f"PLATE{p_idx:02d} {a.item.inst_id} exceeds usable bed: ({a.x+a.w_placed}, {a.y+a.h_placed})")
            if a.item.z > cfg.usable_z + 0.02:
                errors.append(f"PLATE{p_idx:02d} {a.item.inst_id} exceeds height {cfg.usable_z}")
            hm = _get_hires(a)
            ix0 = int(round(a.x / step))
            iy0 = int(round(a.y / step))
            mw, mh = hm.shape
            ix1 = min(bed_gx, ix0 + mw)
            iy1 = min(bed_gy, iy0 + mh)
            if np.any(occ_dil[ix0:ix1, iy0:iy1] & hm[: ix1 - ix0, : iy1 - iy0]):
                errors.append(f"PLATE{p_idx:02d} real clearance < {cfg.plate_spacing} mm involving {a.item.inst_id}")
            hd = _dilate_mask(hm, rad_px)
            dx0 = max(0, ix0 - rad_px)
            dy0 = max(0, iy0 - rad_px)
            dx1 = min(bed_gx, ix0 + mw + rad_px)
            dy1 = min(bed_gy, iy0 + mh + rad_px)
            sx0 = dx0 - (ix0 - rad_px)
            sy0 = dy0 - (iy0 - rad_px)
            occ_dil[dx0:dx1, dy0:dy1] |= hd[sx0 : sx0 + (dx1 - dx0), sy0 : sy0 + (dy1 - dy0)]

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

    plates, solid_masks_0 = run_packing(items, cfg)
    g3_errors = verify_plates_gate_g3(items, plates, cfg, solid_masks_0)
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
        mf_objects: list[tuple[str, str, str, trimesh.Trimesh, list[float]]] = []
        item_records: list[dict[str, Any]] = []

        for pi in pl:
            if pi.item.part_id not in mesh_cache:
                mesh_cache[pi.item.part_id] = trimesh.load(str(pi.item.stl_path), force="mesh")
            base_m = mesh_cache[pi.item.part_id]
            pos_m, tf_3mf = _transform_mesh_for_plate(base_m, pi)
            positioned_meshes.append(pos_m)
            mf_objects.append((pi.item.inst_id, pi.item.part_id, pi.item.kind, base_m, tf_3mf))
            overrides = lp.get_object_slicer_overrides(pi.item.part_id, pi.item.kind)
            eff_slicer = lp.get_effective_object_slicer_settings(pi.item.part_id, pi.item.kind)
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
                "slicer_overrides": overrides,
                "effective_perimeters": int(eff_slicer["perimeters"]),
                "effective_fill_density": eff_slicer["fill_density"],
                "effective_top_solid_layers": int(eff_slicer["top_solid_layers"]),
                "effective_bottom_solid_layers": int(eff_slicer["bottom_solid_layers"]),
            })

        combined = trimesh.util.concatenate(positioned_meshes)
        combined.export(str(stl_out), file_type="stl")
        baked_overrides = write_multi_object_3mf(mf_out, mf_objects, plate_id)
        per_obj_overrides_nonempty = {k: v for k, v in baked_overrides.items() if v}

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
            "baked_slicer_config": dict(lp.SLICER_GLOBAL_CONFIG),
            "per_object_overrides": per_obj_overrides_nonempty,
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
        "slicer_application_tag": lp.SLICER_APPLICATION_TAG,
        "baked_slicer_config": dict(lp.SLICER_GLOBAL_CONFIG),
        "three_perimeter_parts": sorted(lp.THREE_PERIMETER_PARTS),
        "watertight_exceptions": lp.WATERTIGHT_SOLID_LAYER_EXCEPTIONS,
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
