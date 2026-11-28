"""FEA-Lite Structural & Mechanical Sanity Verification for agyhw14 Lightweight 3D-Print Set (R4, R5, R7).

Reads built part metadata (`build_meta/P*.json`, `build_meta/SUP*.json`), `lightweight_policy.py`,
`print_domain.py`, and `component_dimensions_ssot.py`, and writes `build_meta/strength_report.json`.

Checks:
  (a) Cutout rib width >= 3.0 mm, edge margin >= 6.0 mm, Relay/PSU closed zones, open-area fraction, Gibson-Ashby E_eff
  (b) P01A/P01B base sag/deflection at 2.2 mm web + 9% gyroid + 3.0 mm ribs under 250 g worst-case load (<= 0.5 mm)
  (c) SG90 1.8 kg.cm coaxial door torque path: door torque margin >= 5x, P07 cantilever bending, 2x SUP10 pin shear,
      SUP11 saddle clamp shear, SUP10B U-fork shear
  (d) Dovetail & comb joint shear under 20 N handling load (FOS >= 5x)
  (e) P16 / 4x SUP05 / SUP06 PCB tray bending & tenon shear under 15 N insertion load (FOS >= 5x)

Usage:
    python "hardware/in 3 d/scripts/check_strength_hw14.py"
"""

from __future__ import annotations

import json
import math
import pathlib
import sys
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PRINT3D_ROOT = SCRIPT_DIR.parent
HARDWARE_ROOT = PRINT3D_ROOT.parent
META_DIR = PRINT3D_ROOT / "build_meta"

for _p in (str(SCRIPT_DIR), str(HARDWARE_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import component_dimensions_ssot as dim_ssot
import lightweight_policy as lp
import print_domain as pd_mod

# Conservative FDM PLA material properties (anisotropic print-safe design allowables)
E_PLA_MPA = 2800.0          # In-plane flexural modulus of printed PLA (MPa)
SIGMA_YIELD_MPA = 45.0      # Conservative PLA yield/bending strength (MPa)
TAU_SHEAR_MPA = 25.0        # Conservative PLA shear strength (MPa; ~0.55 * sigma_y)
NU_PLA = 0.35


def _load_part_metas() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for mp in sorted(META_DIR.glob("*.json")):
        if mp.stem in ("fit_table", "assembly_report", "plates_manifest", "slice_report", "user_like_test_report", "strength_report"):
            continue
        d = json.loads(mp.read_text(encoding="utf-8"))
        if "part_id" in d and "kind" in d:
            out[d["part_id"]] = d
    return out


def check_cutouts_and_closed_zones(metas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """(a) Verify cutout rib >= 3.0 mm, margin >= 6.0 mm, relay/PSU closed zones, and Gibson-Ashby stiffness."""
    total_hexes = 0
    min_rib = float("inf")
    min_margin = float("inf")
    all_closed_ok = True
    max_open_frac = 0.0
    per_panel: dict[str, dict[str, Any]] = {}

    for pid, meta in sorted(metas.items()):
        if meta.get("kind") != "panel":
            continue
        lw = meta.get("lightweight", {})
        spid = meta["source_panel_id"]
        cnt = int(lw.get("cutout_count", 0))
        total_hexes += cnt
        if cnt > 0:
            rib = float(lw["min_rib_mm"])
            marg = float(lw["min_edge_margin_mm"])
            min_rib = min(min_rib, rib)
            min_margin = min(min_margin, marg)
            if "cutout_area_mm2" in lw and float(lw["cutout_area_mm2"]) > 0.0:
                hex_a = float(lw["cutout_area_mm2"])
            else:
                hex_a = cnt * (math.sqrt(3.0) / 2.0) * (float(lw["hex_flat_to_flat_mm"]) ** 2)
            bbox_a = float(meta["print_bbox_mm"][0]) * float(meta["print_bbox_mm"][1])
            frac = hex_a / max(bbox_a, 1.0)
            max_open_frac = max(max_open_frac, frac)
        if not bool(lw.get("relay_psu_closed", True)):
            all_closed_ok = False

        rec = per_panel.setdefault(spid, {
            "cutout_count": 0,
            "web_thickness_mm": float(lw.get("web_thickness_mm", 3.0)),
            "max_unsupported_span_mm": float(lw.get("max_unsupported_span_mm", 0.0)),
            "relay_psu_closed": True,
        })
        rec["cutout_count"] += cnt
        rec["max_unsupported_span_mm"] = max(rec["max_unsupported_span_mm"], float(lw.get("max_unsupported_span_mm", 0.0)))
        rec["relay_psu_closed"] = rec["relay_psu_closed"] and bool(lw.get("relay_psu_closed", True))

    p01a_cutouts = per_panel.get("P01A_BASE_TECH", {}).get("cutout_count", 0)
    p15_cutouts = per_panel.get("P15_TECH_FASCIA", {}).get("cutout_count", 0)
    relay_psu_strict_ok = all_closed_ok and (p01a_cutouts == 0) and (p15_cutouts == 0)

    # Gibson-Ashby in-plane relative density & effective modulus for regular honeycomb lattice
    actual_fs = [float(m.get("lightweight", {}).get("hex_flat_to_flat_mm")) for m in metas.values() if m.get("lightweight", {}).get("cutout_count", 0) > 0 and m.get("lightweight", {}).get("hex_flat_to_flat_mm")]
    F = actual_fs[0] if actual_fs else lp.HEX_FLAT_TO_FLAT_MM
    t_rib = lp.HEX_MIN_RIB_MM
    P = F + t_rib
    # Area fraction of solid material inside a unit hexagonal cell: 1 - (F/P)^2
    rho_rel_lattice = 1.0 - (F / P) ** 2
    # Regular honeycomb in-plane effective bending/axial stiffness ratio ~ rho_rel
    e_eff_ratio_lattice = round(rho_rel_lattice, 3)

    passed = bool(
        total_hexes > 0
        and min_rib >= 3.0
        and min_margin >= 6.0
        and relay_psu_strict_ok
        and max_open_frac <= 0.65
    )
    return {
        "passed": passed,
        "total_hex_cutouts": total_hexes,
        "min_rib_mm": round(min_rib, 3) if not math.isinf(min_rib) else None,
        "required_min_rib_mm": 3.0,
        "min_edge_margin_mm": round(min_margin, 3) if not math.isinf(min_margin) else None,
        "required_min_edge_margin_mm": 6.0,
        "p01a_tech_bay_cutouts": p01a_cutouts,
        "p15_psu_fascia_cutouts": p15_cutouts,
        "relay_psu_closed_ok": relay_psu_strict_ok,
        "max_piece_open_area_fraction": round(max_open_frac, 3),
        "honeycomb_lattice_solid_fraction": round(rho_rel_lattice, 3),
        "gibson_ashby_e_eff_ratio": e_eff_ratio_lattice,
        "per_panel_summary": per_panel,
    }


def check_base_plate_deflection(metas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """(b) Base plate sag/deflection on P01A/P01B at 2.2 mm web + 9% gyroid under 250 g load across <= 85 mm rib span."""
    base_spans = [
        float(m.get("lightweight", {}).get("max_unsupported_span_mm", 0.0))
        for m in metas.values()
        if m.get("source_panel_id") in ("P01A_BASE_TECH", "P01B_BASE_HOUSE")
    ]
    max_span_mm = max(base_spans) if base_spans else lp.MAX_RIB_SPAN_MM

    # Sandwich cross-section at 2.2 mm web: 3 bottom layers (0.6 mm) + 1.0 mm 9% gyroid core + 3 top layers (0.6 mm)
    t_web = lp.WEB_THICKNESS_MM  # 2.2 mm
    t_skin = float(lp.SLICER_GLOBAL_CONFIG["top_solid_min_thickness"])  # 0.6 mm
    t_core = max(0.0, t_web - 2.0 * t_skin)  # 1.0 mm
    infill_rho = float(lp.SLICER_GLOBAL_CONFIG["fill_density"].rstrip("%")) / 100.0  # 0.09
    e_core_mpa = E_PLA_MPA * (infill_rho ** 2)  # Conservative Gibson-Ashby cellular core stiffness

    # Flexural rigidity per unit width D_eff = (E_skin*(t^3 - tc^3) + E_core*tc^3) / (12 * (1 - nu^2))
    d_eff_n_mm = (
        E_PLA_MPA * (t_web ** 3 - t_core ** 3) + e_core_mpa * (t_core ** 3)
    ) / (12.0 * (1.0 - NU_PLA ** 2))

    # Worst-case 250 g concentrated + distributed load (2.4525 N) at center of a square sub-panel bounded by 3.0 mm ribs
    # Timoshenko plate center-point load on simply-supported square plate of side a: w_max = 0.01160 * P * a^2 / D
    load_g = 250.0
    load_n = (load_g / 1000.0) * 9.81
    w_max_mm = 0.01160 * load_n * (max_span_mm ** 2) / d_eff_n_mm
    span_to_defl_ratio = max_span_mm / max(w_max_mm, 1e-9)

    passed = bool(max_span_mm <= lp.MAX_RIB_SPAN_MM + 0.05 and w_max_mm <= 0.50)
    return {
        "passed": passed,
        "web_thickness_mm": t_web,
        "skin_thickness_each_mm": t_skin,
        "gyroid_core_thickness_mm": round(t_core, 2),
        "gyroid_infill_pct": round(infill_rho * 100.0, 1),
        "flexural_rigidity_d_eff_n_mm": round(d_eff_n_mm, 2),
        "max_unsupported_base_span_mm": round(max_span_mm, 2),
        "required_max_span_mm": lp.MAX_RIB_SPAN_MM,
        "worst_case_load_g": load_g,
        "worst_case_load_n": round(load_n, 3),
        "max_deflection_mm": round(w_max_mm, 4),
        "required_max_deflection_mm": 0.50,
        "span_over_deflection": round(span_to_defl_ratio, 1),
    }


def check_servo_door_torque_path(metas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """(c) SG90 1.8 kg.cm door torque path: torque margin, P07 bending, SUP10 pin shear, SUP11 & SUP10B shear."""
    p08 = metas["P08_DOOR_LEAF"]
    sup10 = metas["SUP10_DOOR_MORTISE_HINGE"]["params"]
    sup10b = metas["SUP10B_DOOR_HORN_COUPLER"]["params"]
    sup11 = metas["SUP11_SG90_SNAP_SADDLE"]["params"]

    # Conservative solid-equivalent door mass (actual sliced mass at 2 perims + 9% gyroid is even lighter!)
    p08_mass_solid_g = round((float(p08["volume_mm3"]) / 1000.0) * 1.24, 2)
    tm = dim_ssot.compute_door_torque_margin(door_mass_g=p08_mass_solid_g)

    # SG90 full stall torque: 1.8 kg.cm = 176.5 N.mm
    tau_stall_nmm = float(dim_ssot.SG90_MECHANICAL_SPECS["stall_torque_nm_4v8"]) * 1000.0

    # 1. P07_SERVO_SHELF (3 perimeters, full 3.0 mm thick, 48 mm wide, 22 mm cantilever depth from P05 jamb)
    # Torsion/reaction moment from stall torque resisted by P07 root section (b=48 mm, h=3.0 mm, effective solid ratio ~0.85 at 3 perims)
    p07_b = 48.0
    p07_h = 3.0
    p07_section_mod = (p07_b * (p07_h ** 2) / 6.0) * 0.85  # mm^3
    p07_sigma_mpa = tau_stall_nmm / p07_section_mod
    p07_fos = SIGMA_YIELD_MPA / max(p07_sigma_mpa, 1e-6)
    # Tip deflection of P07 cantilever under equivalent stall tip force F = tau / 22 mm
    p07_I = (p07_b * (p07_h ** 3) / 12.0) * 0.85
    p07_L = 22.0
    p07_tip_defl_mm = (tau_stall_nmm * (p07_L ** 2)) / (2.0 * E_PLA_MPA * p07_I)

    # 2. 2x SUP10 hinge pins (Dia 2.7 mm, 3 perimeters -> 100% solid circular section!)
    # Vertical door weight + 2.0 N accidental bump load shared across 2 pins
    pin_d = float(sup10["pin_d"])
    pin_area_mm2 = 2.0 * (math.pi * (pin_d / 2.0) ** 2)
    door_bump_load_n = (p08_mass_solid_g / 1000.0) * 9.81 + 2.0
    sup10_tau_mpa = door_bump_load_n / pin_area_mm2
    sup10_fos = TAU_SHEAR_MPA / max(sup10_tau_mpa, 1e-6)

    # 3. SUP11 SG90 clamp tenons (2x 3.0x6.0 mm, 3 perimeters -> 100% solid!) resisting SG90 reaction torque at 40 mm span
    f_sup11_n = tau_stall_nmm / 40.0
    sup11_tenon_area = 2.0 * (float(sup11["tenon_x"]) * float(sup11["tenon_y"]))
    sup11_tau_mpa = f_sup11_n / sup11_tenon_area
    sup11_fos = TAU_SHEAR_MPA / max(sup11_tau_mpa, 1e-6)

    # 4. SUP10B U-fork coupler wall (fork_wall_t=1.6 mm, fork_len_x=5.0 mm, 3 perimeters -> 100% solid!)
    # Driven at horn lever radius r = 11.0 mm -> tangential force F = tau_stall / 11.0 = 16.05 N
    r_horn_mm = 11.0
    f_fork_n = tau_stall_nmm / r_horn_mm
    fork_t = float(sup10b["fork_wall_t"])
    fork_l = float(sup10b["fork_len_x"])
    # Bearing + shear across fork wall (thickness 1.6 mm x engagement length 5.0 mm = 8.0 mm^2)
    sup10b_tau_mpa = f_fork_n / (fork_t * fork_l)
    sup10b_fos = TAU_SHEAR_MPA / max(sup10b_tau_mpa, 1e-6)

    passed = bool(
        tm["passes_min_5x_margin"]
        and p07_fos >= 4.0
        and p07_tip_defl_mm <= 0.50
        and sup10_fos >= 10.0
        and sup11_fos >= 10.0
        and sup10b_fos >= 3.0
    )
    return {
        "passed": passed,
        "sg90_stall_torque_nmm": round(tau_stall_nmm, 2),
        "door_torque_margin": tm,
        "p07_servo_shelf": {
            "perimeters": int(lp.get_effective_object_slicer_settings("P07_SERVO_SHELF")["perimeters"]),
            "bending_stress_mpa": round(p07_sigma_mpa, 3),
            "fos_yield": round(p07_fos, 2),
            "tip_deflection_mm": round(p07_tip_defl_mm, 4),
            "passed": bool(p07_fos >= 4.0 and p07_tip_defl_mm <= 0.50),
        },
        "sup10_hinge_pins_2x": {
            "perimeters": int(lp.get_effective_object_slicer_settings("SUP10_DOOR_MORTISE_HINGE", "support")["perimeters"]),
            "pin_dia_mm": pin_d,
            "total_shear_area_mm2": round(pin_area_mm2, 2),
            "shear_stress_mpa": round(sup10_tau_mpa, 3),
            "fos_shear": round(sup10_fos, 2),
            "passed": bool(sup10_fos >= 10.0),
        },
        "sup11_clamp_saddle": {
            "perimeters": int(lp.get_effective_object_slicer_settings("SUP11_SG90_SNAP_SADDLE", "support")["perimeters"]),
            "tenon_shear_area_mm2": round(sup11_tenon_area, 2),
            "shear_stress_mpa": round(sup11_tau_mpa, 3),
            "fos_shear": round(sup11_fos, 2),
            "passed": bool(sup11_fos >= 10.0),
        },
        "sup10b_horn_coupler": {
            "perimeters": int(lp.get_effective_object_slicer_settings("SUP10B_DOOR_HORN_COUPLER", "support")["perimeters"]),
            "stall_force_n": round(f_fork_n, 2),
            "fork_wall_area_mm2": round(fork_t * fork_l, 2),
            "shear_stress_mpa": round(sup10b_tau_mpa, 3),
            "fos_shear": round(sup10b_fos, 2),
            "passed": bool(sup10b_fos >= 3.0),
        },
    }


def check_dovetail_and_comb_joints() -> dict[str, Any]:
    """(d) Dovetail neck & comb joint shear at full 3.0 mm seam thickness + 3-perimeter SUP03/P17 locks."""
    cfg = pd_mod.PrintConfig()
    handling_force_n = 20.0
    # Standard dovetail neck: 10.0 mm x 3.0 mm full thickness (2 perimeters + 6 solid skins = >= 65% effective cross-section)
    dt_area_eff = cfg.dovetail_neck * cfg.T_mm * 0.65
    dt_tau_mpa = handling_force_n / dt_area_eff
    dt_fos = TAU_SHEAR_MPA / max(dt_tau_mpa, 1e-6)

    # P17_BASE_JOINER 4x 8x4 mm tenons (3 perimeters -> >= 85% solid) locking P01A <-> P01B
    p17_area_eff = 2.0 * (8.0 * 4.0) * 0.85  # 2 tenons per side of seam
    p17_tau_mpa = handling_force_n / p17_area_eff
    p17_fos = TAU_SHEAR_MPA / max(p17_tau_mpa, 1e-6)

    passed = bool(dt_fos >= 5.0 and p17_fos >= 10.0)
    return {
        "passed": passed,
        "handling_load_n": handling_force_n,
        "dovetail_seam_thickness_mm": cfg.T_mm,
        "dovetail_neck_mm": cfg.dovetail_neck,
        "dovetail_eff_shear_area_mm2": round(dt_area_eff, 2),
        "dovetail_shear_stress_mpa": round(dt_tau_mpa, 3),
        "dovetail_fos_shear": round(dt_fos, 2),
        "p17_joiner_perimeters": int(lp.get_effective_object_slicer_settings("P17_BASE_JOINER")["perimeters"]),
        "p17_joiner_fos_shear": round(p17_fos, 2),
    }


def check_pcb_tray_load(metas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """(e) P16_PCB_PLATE + 4x SUP05 risers + SUP06 carrier under 15 N Hub PCB + NodeMCU + 40-wire insertion force."""
    load_n = 15.0
    # 4x SUP05 tenons (8x3 mm, 3 perimeters -> 100% solid!)
    sup05_area = 4.0 * (8.0 * 3.0)
    sup05_tau_mpa = load_n / sup05_area
    sup05_fos = TAU_SHEAR_MPA / max(sup05_tau_mpa, 1e-6)

    # P16_PCB_PLATE (130 x 110 x 3.0 mm full thickness) 2D plate bending across 116 x 96 mm 4-riser span under 15 N
    L = 116.0
    b = 110.0
    t = 3.0
    t_core = 1.8
    e_core = E_PLA_MPA * (0.09 ** 2)
    # 2D sandwich plate flexural rigidity D_eff (N.mm) and section modulus
    d_eff_p16 = (E_PLA_MPA * (t ** 3 - t_core ** 3) + e_core * (t_core ** 3)) / (12.0 * (1.0 - NU_PLA ** 2))
    i_eff_beam = (b * (t ** 3 - t_core ** 3) / 12.0) + (b * (t_core ** 3) / 12.0) * (0.09 ** 2)
    m_max_nmm = load_n * L / 4.0
    sigma_p16_mpa = m_max_nmm * (t / 2.0) / i_eff_beam
    p16_fos = SIGMA_YIELD_MPA / max(sigma_p16_mpa, 1e-6)
    # Timoshenko 2D plate deflection under 15 N load across 116 mm riser span (conservative: ignores SUP06 3mm frame & FR4 stiffening!)
    defl_p16_mm = 0.01160 * load_n * (L ** 2) / d_eff_p16

    passed = bool(sup05_fos >= 10.0 and p16_fos >= 5.0 and defl_p16_mm <= 0.50)
    return {
        "passed": passed,
        "insertion_load_n": load_n,
        "sup05_perimeters": int(lp.get_effective_object_slicer_settings("SUP05_P16_TENON_RISER", "support")["perimeters"]),
        "sup06_perimeters": int(lp.get_effective_object_slicer_settings("SUP06_HUB_PCB_SNAP_CARRIER", "support")["perimeters"]),
        "sup05_tenon_shear_mpa": round(sup05_tau_mpa, 3),
        "sup05_fos_shear": round(sup05_fos, 2),
        "p16_bending_stress_mpa": round(sigma_p16_mpa, 3),
        "p16_fos_yield": round(p16_fos, 2),
        "p16_center_deflection_mm": round(defl_p16_mm, 4),
    }


def main() -> int:
    metas = _load_part_metas()
    checks = {
        "a_cutouts_and_relay_psu_closed": check_cutouts_and_closed_zones(metas),
        "b_base_plate_2p2mm_deflection": check_base_plate_deflection(metas),
        "c_sg90_door_torque_path": check_servo_door_torque_path(metas),
        "d_dovetail_comb_joints": check_dovetail_and_comb_joints(),
        "e_pcb_tray_p16_sup05_sup06": check_pcb_tray_load(metas),
    }
    all_passed = all(bool(c["passed"]) for c in checks.values())
    report = {
        "schema": "hw14_fea_lite_strength_report_v1",
        "all_passed": all_passed,
        "passed_count": sum(1 for c in checks.values() if c["passed"]),
        "total_count": len(checks),
        "material_assumptions": {
            "material": "FDM PLA (0.4 mm nozzle, 0.20 mm layer)",
            "E_pla_mpa": E_PLA_MPA,
            "sigma_yield_mpa": SIGMA_YIELD_MPA,
            "tau_shear_mpa": TAU_SHEAR_MPA,
        },
        "checks": checks,
    }
    out_path = META_DIR / "strength_report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== HW14 FEA-LITE STRENGTH VERIFICATION ===")
    for k, v in checks.items():
        print(f"  [{'PASS' if v['passed'] else 'FAIL'}] {k}")
    c_a = checks["a_cutouts_and_relay_psu_closed"]
    c_b = checks["b_base_plate_2p2mm_deflection"]
    c_c = checks["c_sg90_door_torque_path"]
    print(
        f"  Cutouts: {c_a['total_hex_cutouts']} hexes | min_rib={c_a['min_rib_mm']}mm | "
        f"min_margin={c_a['min_edge_margin_mm']}mm | relay_psu_closed={c_a['relay_psu_closed_ok']}"
    )
    print(
        f"  Base 2.2mm sag: max_span={c_b['max_unsupported_base_span_mm']}mm | "
        f"w_max={c_b['max_deflection_mm']}mm (<= 0.50mm, L/{c_b['span_over_deflection']})"
    )
    print(
        f"  SG90 door path: torque_margin={c_c['door_torque_margin']['worst_case_safety_margin_x']}x | "
        f"P07 FOS={c_c['p07_servo_shelf']['fos_yield']}x | SUP10 FOS={c_c['sup10_hinge_pins_2x']['fos_shear']}x | "
        f"SUP11 FOS={c_c['sup11_clamp_saddle']['fos_shear']}x | SUP10B FOS={c_c['sup10b_horn_coupler']['fos_shear']}x"
    )
    print(f"STRENGTH REPORT: {'PASS' if all_passed else 'FAIL'} -> {out_path}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
