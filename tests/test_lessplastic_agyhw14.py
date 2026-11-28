"""Automated verification & regression test suite for agyhw14_20261128 (R9 — Lightweight PLA + Baked 3MF Slicer + Zero Decorative Furniture).

Covers every R9 requirement:
1. Zero decorative furniture (`FUR*` parts) across `hardware/in 3 d/parts/`, `build_meta/`,
   `plates_manifest.json`, `slice_report.json`, `manifest.json`, and `verification_report.json`.
2. All 14 authoritative modules + NodeMCU + Hub PCB (`16/16` PASS in `fit_table.json`) and
   functional garden/pump parts (`P09..P14`, `SUP14`, `SUP15`) preserved intact.
3. Direct ZIP + XML parsing of ALL 16 `hardware/in 3 d/plates/PLATE*.3mf` archives:
   - `3D/3dmodel.model` declares `<metadata name="Application">PrusaSlicer-2.9.7</metadata>`.
   - `Metadata/Slic3r_PE.config` bakes `fill_density` in 8-10% (`9%`), `fill_pattern=gyroid`,
     `perimeters=2`, `top_solid_layers=3`, `bottom_solid_layers=3`, `top_solid_min_thickness=0.6`,
     `bottom_solid_min_thickness=0.6`, `filament_density=1.24`, `support_material=0`,
     `bed_shape=0x0,180x0,180x200,0x200`, `max_print_height=250`.
   - `Metadata/Slic3r_PE_model.config` overrides `perimeters=3` on `SUP10`, `P07`, `SUP11`,
     `SUP10B`, `P17`, `SUP01..SUP18` and `bottom_solid_layers=4` on `SUP15_WATER_TANK_LINER`,
     while standard structural panels inherit `perimeters=2`.
   - `lightweight_policy.get_object_slicer_overrides("DECOR_DUMMY", kind="decorative")`
     returns `{"fill_density": "0%"}`.
4. Printability, mass & plate reduction: every plate fits `180 x 200 x 250 mm`, all objects
   manifold, 0 supports, plate count < 17 (`== 16`), total PLA <= 680.0 g (saving >= 35% vs
   1044.86 g baseline).
5. Joints strictly mortise/tenon (`geometry_fastener_hole_count == 0`,
   `readme_forbidden_instruction_count == 0`).
6. Cutouts, panel thinning & FEA-lite strength (`build_meta/strength_report.json` 5/5 PASS):
   `min_rib >= 3.0 mm`, `min_edge_margin >= 6.0 mm`, `relay_psu_closed_ok == True`, base sag
   <= 0.50 mm, SG90 torque margin >= 5x, and `P07`/`SUP10`/`SUP11`/`SUP10B`/`dovetail`/`P16`
   FOS checks PASS.
7. Door swept-volume check (`0..90 deg`, `0.0 mm^3` collision).
8. All `40/40` wires <= 30.0 cm and SG90 wires `W03..W05` <= 25.0 cm.
9. Web 3D (`web/models/smarthome_villa.glb` via `trimesh`, `hardware/blender/SCENE_SPEC.json`,
   and `web/house3d.js` via Node.js VM): ZERO furniture nodes (`furnitureRemoved == True`,
   `furnitureNodesCount == 0`) while retaining all 14 modules + 20 contract nodes +
   synchronized door/servo animation + living/bedroom LED glow.
"""

from __future__ import annotations

import importlib.util
import json
import math
import pathlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

import pytest
import trimesh

from hardware.component_dimensions_ssot import (
    AUTHORITATIVE_14_MODULES,
    AUTHORITATIVE_CORE_BOARDS,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
IN3D_DIR = REPO_ROOT / "hardware" / "in 3 d"
PLATES_DIR = IN3D_DIR / "plates"
PARTS_DIR = IN3D_DIR / "parts"
BUILD_META_DIR = IN3D_DIR / "build_meta"

FUR_ID_RE = re.compile(r"(?:^|[^A-Za-z0-9])FUR\d{2}(?:_[A-Z0-9_]+)?(?=$|[^A-Za-z0-9])", re.IGNORECASE)
EXPECTED_WIRE_IDS = tuple(f"W{i:02d}" for i in range(1, 41))
FUNCTIONAL_GARDEN_PUMP_PARTS = (
    "P09_GARDEN_LEFT",
    "P10_WATER_DIVIDER",
    "P11_GARDEN_RIGHT",
    "P12_GARDEN_FRONT",
    "P13_GARDEN_BACK",
    "P14_SOIL_BRIDGE",
    "SUP14_LM393_SNAP_CRADLE",
    "SUP15_WATER_TANK_LINER",
)


def _load_json(rel_path: str) -> dict[str, Any]:
    path = REPO_ROOT / rel_path
    assert path.exists(), f"Missing JSON artifact: {rel_path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_lightweight_policy() -> Any:
    policy_path = IN3D_DIR / "scripts" / "lightweight_policy.py"
    assert policy_path.exists(), f"Missing lightweight_policy.py at {policy_path}"
    parent = str(policy_path.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    spec = importlib.util.spec_from_file_location("lightweight_policy_hw14_test", policy_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lightweight_policy_hw14_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _parse_slic3r_pe_config(raw: str) -> dict[str, str]:
    cfg: dict[str, str] = {}
    for line in raw.splitlines():
        s = line.strip()
        if not s.startswith(";"):
            continue
        body = s.lstrip(";").strip()
        if "=" not in body:
            continue
        key, val = body.split("=", 1)
        cfg[key.strip()] = val.strip()
    return cfg


def _base_part_id(obj_name: str) -> str:
    return re.sub(r"_copy\d+of\d+$", "", obj_name)


def _find_fur_strings(obj: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and FUR_ID_RE.search(k):
                hits.append(f"{path}.{k}")
            hits.extend(_find_fur_strings(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            hits.extend(_find_fur_strings(item, f"{path}[{idx}]"))
    elif isinstance(obj, str):
        if FUR_ID_RE.search(obj):
            hits.append(f"{path}={obj!r}")
    return hits


class TestZeroFurnitureAndFunctionalPartsPreserved:
    def test_zero_fur_parts_across_parts_meta_and_all_reports(self) -> None:
        fur_part_files = [p.name for p in PARTS_DIR.iterdir() if FUR_ID_RE.search(p.name)]
        assert fur_part_files == [], f"Unexpected FUR* files in parts/: {fur_part_files}"

        fur_meta_files = [p.name for p in BUILD_META_DIR.iterdir() if FUR_ID_RE.search(p.name)]
        assert fur_meta_files == [], f"Unexpected FUR* files in build_meta/: {fur_meta_files}"

        for rel_json in (
            "hardware/in 3 d/build_meta/plates_manifest.json",
            "hardware/in 3 d/build_meta/slice_report.json",
            "hardware/in 3 d/manifest.json",
            "hardware/in 3 d/verification_report.json",
        ):
            data = _load_json(rel_json)
            hits = _find_fur_strings(data)
            assert hits == [], f"Found FUR* references in {rel_json}: {hits[:10]}"

        srep = _load_json("hardware/in 3 d/build_meta/slice_report.json")
        assert int(srep["screwless_audit"].get("furniture_parts_audited", 0)) == 0

    def test_all_14_modules_core_boards_and_garden_pump_parts_intact(self) -> None:
        fit_table = _load_json("hardware/in 3 d/build_meta/fit_table.json")
        vrep = _load_json("hardware/in 3 d/verification_report.json")
        pman = _load_json("hardware/in 3 d/build_meta/plates_manifest.json")
        srep = _load_json("hardware/in 3 d/build_meta/slice_report.json")

        assert fit_table["authoritative_row_count"] == 16
        assert fit_table["all_fit_passed"] is True
        fit_by_mod = {row["module_id"]: row for row in fit_table["rows"]}
        assert len(fit_by_mod) == 16

        expected_16 = (*AUTHORITATIVE_14_MODULES, *AUTHORITATIVE_CORE_BOARDS)
        assert len(expected_16) == 16
        for item in expected_16:
            mid = item["module_id"]
            assert mid in fit_by_mod, f"Missing {mid} in fit_table.json"
            assert fit_by_mod[mid]["status"] == "PASS", f"{mid} did not PASS in fit_table.json"

        assert vrep["pcb_module_fit"]["authoritative_row_count"] == 16
        assert vrep["pcb_module_fit"]["all_fit_passed"] is True

        plated_parts = {
            item["part_id"]
            for plate in pman["plates"]
            for item in plate["items"]
        }
        sliced_parts = {
            part["part_id"] if isinstance(part, dict) and "part_id" in part else part
            for part in (srep.get("parts") or [])
        }
        if not sliced_parts:
            sliced_parts = {
                up
                for plate in srep["plates"]
                for up in plate["unique_parts"]
            }

        for part_id in FUNCTIONAL_GARDEN_PUMP_PARTS:
            stl_path = PARTS_DIR / f"{part_id}.stl"
            meta_path = BUILD_META_DIR / f"{part_id}.json"
            assert stl_path.exists() and stl_path.stat().st_size > 0, f"Missing STL for {part_id}"
            assert meta_path.exists(), f"Missing build_meta JSON for {part_id}"
            assert part_id in plated_parts, f"{part_id} missing from plates_manifest.json"
            assert part_id in sliced_parts, f"{part_id} missing from slice_report.json"


class TestBaked3MFSlicerSettingsAndOverrides:
    def test_all_16_3mf_plates_have_baked_prusaslicer_config_and_per_object_overrides(self) -> None:
        policy = _load_lightweight_policy()
        expected_3p_parts = set(policy.THREE_PERIMETER_PARTS)

        threemf_files = sorted(PLATES_DIR.glob("PLATE*.3mf"))
        assert len(threemf_files) == 16, f"Expected 16 PLATE*.3mf files, found {len(threemf_files)}"

        seen_3p_parts: set[str] = set()
        seen_standard_panels: set[str] = set()
        sup15_verified = False
        total_objects = 0

        for zpath in threemf_files:
            with zipfile.ZipFile(zpath, "r") as zf:
                names = set(zf.namelist())
                assert "3D/3dmodel.model" in names, f"{zpath.name} missing 3D/3dmodel.model"
                assert "Metadata/Slic3r_PE.config" in names, f"{zpath.name} missing Metadata/Slic3r_PE.config"
                assert "Metadata/Slic3r_PE_model.config" in names, f"{zpath.name} missing Metadata/Slic3r_PE_model.config"

                # 1. 3D/3dmodel.model Application metadata
                model_root = ET.fromstring(zf.read("3D/3dmodel.model"))
                ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
                app_nodes = [
                    m.text.strip()
                    for m in model_root.findall("m:metadata", ns)
                    if m.attrib.get("name") == "Application" and m.text
                ]
                assert app_nodes == ["PrusaSlicer-2.9.7"], (
                    f"{zpath.name} Application metadata mismatch: {app_nodes}"
                )

                # 2. Metadata/Slic3r_PE.config global lightweight settings
                cfg = _parse_slic3r_pe_config(zf.read("Metadata/Slic3r_PE.config").decode("utf-8"))
                fill_str = cfg.get("fill_density", "")
                assert fill_str.endswith("%"), f"{zpath.name} invalid fill_density: {fill_str!r}"
                fill_val = float(fill_str.rstrip("%"))
                assert 8.0 <= fill_val <= 10.0, f"{zpath.name} fill_density out of 8-10%: {fill_str}"
                assert fill_str == "9%", f"{zpath.name} expected 9% fill_density, got {fill_str}"

                assert cfg.get("fill_pattern") == "gyroid", f"{zpath.name} fill_pattern != gyroid"
                assert cfg.get("perimeters") == "2", f"{zpath.name} global perimeters != 2"
                assert cfg.get("top_solid_layers") == "3", f"{zpath.name} top_solid_layers != 3"
                assert cfg.get("bottom_solid_layers") == "3", f"{zpath.name} bottom_solid_layers != 3"
                assert float(cfg.get("top_solid_min_thickness", "0")) == pytest.approx(0.6)
                assert float(cfg.get("bottom_solid_min_thickness", "0")) == pytest.approx(0.6)
                assert float(cfg.get("filament_density", "0")) == pytest.approx(1.24)
                assert cfg.get("support_material") == "0", f"{zpath.name} support_material != 0"
                assert cfg.get("bed_shape") == "0x0,180x0,180x200,0x200", f"{zpath.name} bed_shape mismatch"
                assert cfg.get("max_print_height") == "250", f"{zpath.name} max_print_height != 250"

                # 3. Metadata/Slic3r_PE_model.config per-object overrides
                mcfg_root = ET.fromstring(zf.read("Metadata/Slic3r_PE_model.config"))
                objects = mcfg_root.findall("object")
                assert len(objects) >= 1, f"{zpath.name} has 0 objects in Slic3r_PE_model.config"

                for obj in objects:
                    total_objects += 1
                    obj_meta = {
                        m.attrib["key"]: m.attrib["value"]
                        for m in obj.findall("metadata")
                        if m.attrib.get("type") == "object"
                    }
                    obj_name = obj_meta.get("name", "")
                    assert obj_name, f"{zpath.name} object missing name metadata"
                    assert not obj_name.upper().startswith("FUR"), f"FUR object in {zpath.name}: {obj_name}"

                    base_id = _base_part_id(obj_name)
                    if base_id in expected_3p_parts:
                        assert obj_meta.get("perimeters") == "3", (
                            f"{zpath.name} object {obj_name} must override perimeters=3, got {obj_meta}"
                        )
                        seen_3p_parts.add(base_id)
                        if base_id == "SUP15_WATER_TANK_LINER":
                            assert obj_meta.get("bottom_solid_layers") == "4", (
                                f"{zpath.name} SUP15_WATER_TANK_LINER must have bottom_solid_layers=4, got {obj_meta}"
                            )
                            assert float(obj_meta.get("bottom_solid_min_thickness", "0")) == pytest.approx(0.8)
                            sup15_verified = True
                    else:
                        # Standard structural panel inherits global perimeters=2
                        assert "perimeters" not in obj_meta, (
                            f"{zpath.name} standard panel {obj_name} should inherit perimeters=2, got {obj_meta}"
                        )
                        seen_standard_panels.add(base_id)

        assert total_objects == 83, f"Expected 83 total 3MF object instances across 16 plates, got {total_objects}"
        assert seen_3p_parts == expected_3p_parts, (
            f"Missing 3-perimeter parts across 3MF plates: {sorted(expected_3p_parts - seen_3p_parts)}"
        )
        # Explicitly verify named R2 parts are all present with 3 perimeters
        for key_prefix in ("SUP10_DOOR_MORTISE_HINGE", "P07_SERVO_SHELF", "SUP11_SG90_SNAP_SADDLE", "SUP10B_DOOR_HORN_COUPLER", "P17_BASE_JOINER"):
            assert key_prefix in seen_3p_parts
        for idx in range(1, 19):
            sup_prefix = f"SUP{idx:02d}"
            assert any(p.startswith(sup_prefix) for p in seen_3p_parts), f"Missing {sup_prefix}* in 3-perimeter parts"
        assert sup15_verified is True, "SUP15_WATER_TANK_LINER watertight override was not found in any 3MF plate"
        assert len(seen_standard_panels) == 28, f"Expected 28 standard structural panel pieces, got {len(seen_standard_panels)}"

    def test_decorative_slicer_override_returns_zero_infill(self) -> None:
        policy = _load_lightweight_policy()
        assert policy.get_object_slicer_overrides("DECOR_DUMMY", kind="decorative") == {"fill_density": "0%"}


class TestPrintabilityMassReductionAndZeroFasteners:
    def test_16_plates_fit_bed_manifold_zero_supports_mass_saving_and_mortise_only(self) -> None:
        vrep = _load_json("hardware/in 3 d/verification_report.json")
        srep = _load_json("hardware/in 3 d/build_meta/slice_report.json")
        pman = _load_json("hardware/in 3 d/build_meta/plates_manifest.json")

        assert vrep["all_passed"] is True
        assert srep["all_passed"] is True
        assert [float(x) for x in vrep["bed_mm"]] == [180.0, 200.0, 250.0]

        # Plate count reduction (< 17 -> 16)
        assert vrep["plates_verified"] == 16
        assert vrep["totals"]["total_plates"] == 16
        assert vrep["totals"]["plates_passed"] == 16
        assert vrep["totals"]["total_plates"] < 17
        assert pman["achieved_plate_count"] == 16
        assert len(srep["plates"]) == 16

        # Zero supports & 100% manifold
        assert vrep["totals"]["any_plate_needs_supports"] is False
        assert vrep["needs_slicer_supports"] is False
        assert srep["parts_summary"]["all_manifold"] is True
        assert srep["parts_summary"]["total_parts"] == 51
        assert srep["parts_summary"]["passed_parts"] == 51

        # Mass reduction <= 680.0 g and >= 35% saving vs 1044.86 g baseline
        baseline_g = 1044.86
        total_g = float(vrep["totals"]["total_filament_g"])
        srep_total_g = float(srep["totals"]["total_filament_g"])
        assert total_g == pytest.approx(srep_total_g, abs=0.05)
        assert total_g <= 680.0, f"Total PLA {total_g} g exceeds 680.0 g cap"
        saving_pct = (baseline_g - total_g) / baseline_g * 100.0
        assert saving_pct >= 35.0, f"PLA mass saving {saving_pct:.2f}% is below 35% target"

        # Every plate fits 180 x 200 x 250 mm, manifold, 0 supports, baked config verified
        for plate in srep["plates"]:
            pid = plate["plate_id"]
            assert plate["plate_passed"] is True, f"{pid} did not pass"
            assert plate["stl_manifold"] is True, f"{pid} STL not manifold"
            assert plate["all_objects_manifold"] is True, f"{pid} 3MF objects not manifold"
            assert plate["slice_ok"] is True and plate["slicer_returncode"] == 0, f"{pid} slice failed"
            assert plate["needs_supports"] is False, f"{pid} requires supports"
            assert plate["outside_volume_warning"] is False, f"{pid} outside print volume"
            assert plate["baked_3mf_config_ok"] is True, f"{pid} baked_3mf_config_ok failed: {plate.get('baked_3mf_errors')}"
            assert plate["gcode_config_verified"] is True, f"{pid} gcode_config_verified failed: {plate.get('gcode_config_errors')}"

            sx, sy, sz = [float(v) for v in plate["stl_size_mm"]]
            assert sx <= 180.0 and sy <= 200.0 and sz <= 250.0, f"{pid} exceeds bed: {(sx, sy, sz)}"

            gb = plate["gcode_extrusion_bounds_mm"]
            assert 0.0 <= float(gb["x_min"]) <= float(gb["x_max"]) <= 180.0, f"{pid} X out of bed: {gb}"
            assert 0.0 <= float(gb["y_min"]) <= float(gb["y_max"]) <= 200.0, f"{pid} Y out of bed: {gb}"
            assert 0.0 <= float(gb["z_min"]) <= float(gb["z_max"]) <= 250.0, f"{pid} Z out of bed: {gb}"

        # Mortise/tenon only: 0 fastener holes and 0 forbidden glue/screw instructions
        audit = vrep["screw_glue_audit"]
        assert audit["passed"] is True
        assert audit["geometry_fastener_hole_count"] == 0
        assert audit["readme_forbidden_instruction_count"] == 0


class TestCutoutsThinningAndStrengthReport:
    def test_strength_report_passes_all_5_checks_and_structural_limits(self) -> None:
        srep = _load_json("hardware/in 3 d/build_meta/strength_report.json")
        vrep = _load_json("hardware/in 3 d/verification_report.json")

        for label, rep in (("build_meta/strength_report.json", srep), ("verification_report.strength_report", vrep["strength_report"])):
            assert rep["all_passed"] is True, f"{label} did not pass"
            assert rep["passed_count"] == 5 and rep["total_count"] == 5

        checks = srep["checks"]

        # (a) Cutouts, ribs, edge margin, relay/PSU closed
        ca = checks["a_cutouts_and_relay_psu_closed"]
        assert ca["passed"] is True
        assert int(ca["total_hex_cutouts"]) > 0
        assert float(ca["min_rib_mm"]) >= 3.0
        assert float(ca["min_edge_margin_mm"]) >= 6.0
        assert ca["relay_psu_closed_ok"] is True
        assert int(ca["p01a_tech_bay_cutouts"]) == 0
        assert int(ca["p15_psu_fascia_cutouts"]) == 0

        # (b) Base plate 2.2 mm deflection <= 0.50 mm
        cb = checks["b_base_plate_2p2mm_deflection"]
        assert cb["passed"] is True
        assert 2.0 <= float(cb["web_thickness_mm"]) <= 2.4
        assert float(cb["max_deflection_mm"]) <= 0.50

        # (c) SG90 door torque margin >= 5x & P07/SUP10/SUP11/SUP10B FOS PASS
        cc = checks["c_sg90_door_torque_path"]
        assert cc["passed"] is True
        assert cc["door_torque_margin"]["passes_min_5x_margin"] is True
        assert float(cc["door_torque_margin"]["worst_case_safety_margin_x"]) >= 5.0

        assert cc["p07_servo_shelf"]["passed"] is True
        assert cc["p07_servo_shelf"]["perimeters"] == 3
        assert float(cc["p07_servo_shelf"]["fos_yield"]) >= 3.0

        assert cc["sup10_hinge_pins_2x"]["passed"] is True
        assert cc["sup10_hinge_pins_2x"]["perimeters"] == 3
        assert float(cc["sup10_hinge_pins_2x"]["fos_shear"]) >= 3.0

        assert cc["sup11_clamp_saddle"]["passed"] is True
        assert cc["sup11_clamp_saddle"]["perimeters"] == 3
        assert float(cc["sup11_clamp_saddle"]["fos_shear"]) >= 3.0

        assert cc["sup10b_horn_coupler"]["passed"] is True
        assert cc["sup10b_horn_coupler"]["perimeters"] == 3
        assert float(cc["sup10b_horn_coupler"]["fos_shear"]) >= 3.0

        # (d) Dovetail comb joints & P17 joiner FOS PASS
        cd = checks["d_dovetail_comb_joints"]
        assert cd["passed"] is True
        assert float(cd["dovetail_seam_thickness_mm"]) == pytest.approx(3.0)
        assert float(cd["dovetail_fos_shear"]) >= 3.0
        assert cd["p17_joiner_perimeters"] == 3
        assert float(cd["p17_joiner_fos_shear"]) >= 3.0

        # (e) P16 PCB tray & SUP05/SUP06 FOS PASS
        ce = checks["e_pcb_tray_p16_sup05_sup06"]
        assert ce["passed"] is True
        assert ce["sup05_perimeters"] == 3
        assert ce["sup06_perimeters"] == 3
        assert float(ce["sup05_fos_shear"]) >= 3.0
        assert float(ce["p16_fos_yield"]) >= 3.0


class TestDoorSweptVolumeAndFortyWires:
    def test_door_swept_volume_0_to_90_deg_zero_collision(self) -> None:
        vrep = _load_json("hardware/in 3 d/verification_report.json")
        arep = _load_json("hardware/in 3 d/build_meta/assembly_report.json")

        for label, swept in (
            ("verification_report.door_swept_volume_check", vrep["door_swept_volume_check"]),
            ("assembly_report.door_swept_volume_check", arep["door_swept_volume_check"]),
        ):
            assert swept["passed"] is True, f"{label} failed"
            assert swept["angle_range_deg"] == [0, 90]
            assert float(swept["max_intersection_mm3"]) == 0.0
            assert float(swept["horn_coupler_intersection_mm3"]) == 0.0
            assert swept["collisions"] == []

    def test_40_wires_within_30cm_and_sg90_within_25cm(self) -> None:
        wl = _load_json("hardware/wire_lengths.json")
        wc = _load_json("web/data/wiring_contract.json")

        assert wl["total_wires"] == 40
        assert wl["all_within_30cm"] is True
        assert wl["sg90_within_25cm"] is True
        assert float(wl["sg90_max_length_cm"]) <= 25.0
        assert wc["wire_lengths_summary"]["total_wires"] == 40
        assert wc["wire_lengths_summary"]["all_within_30cm"] is True

        assert tuple(w["wire_id"] for w in wl["wires"]) == EXPECTED_WIRE_IDS
        assert tuple(w["wire_id"] for w in wc["wires"]) == EXPECTED_WIRE_IDS

        for w_wl, w_wc in zip(wl["wires"], wc["wires"]):
            wid = w_wl["wire_id"]
            len_wl = float(w_wl["length_cm"])
            len_wc = float(w_wc["length_cm"])
            assert 0.0 < len_wl <= 30.0, f"{wid} exceeds 30 cm in wire_lengths.json: {len_wl}"
            assert 0.0 < len_wc <= 30.0, f"{wid} exceeds 30 cm in wiring_contract.json: {len_wc}"
            if wid in ("W03", "W04", "W05"):
                assert len_wl <= 25.0 and len_wc <= 25.0, f"SG90 wire {wid} exceeds 25 cm"


class TestWeb3DZeroFurnitureAndIntactInteractivity:
    def test_glb_and_scene_spec_have_zero_furniture_and_all_20_contract_nodes(self) -> None:
        policy = _load_lightweight_policy()
        scene_spec = _load_json("hardware/blender/SCENE_SPEC.json")

        assert scene_spec.get("furniture_removed") is True
        assert scene_spec.get("authoritative_module_count") == 14
        assert scene_spec.get("contract_node_count") == 20
        assert set(scene_spec.get("removed_furniture_ids") or []) == set(policy.REMOVED_FURNITURE_IDS)

        glb_path = REPO_ROOT / "web/models/smarthome_villa.glb"
        assert glb_path.exists() and 0 < glb_path.stat().st_size < 10 * 1024 * 1024

        glb_scene = trimesh.load(str(glb_path))
        glb_nodes = set(glb_scene.graph.nodes)

        # Verify ZERO furniture nodes exist in binary GLB
        forbidden_prefixes = tuple(policy.REMOVED_BLENDER_FURNITURE_PREFIXES)
        found_furniture_nodes = sorted(
            n
            for n in glb_nodes
            if any(n.startswith(pfx) for pfx in forbidden_prefixes)
            or n.upper().startswith("FUR")
            or FUR_ID_RE.search(n)
        )
        assert found_furniture_nodes == [], f"Furniture nodes still present in GLB: {found_furniture_nodes}"

        # Verify all 20 contract nodes & all 14 modules + 2 core boards still exist in GLB
        contract_nodes = set(scene_spec["contract_nodes"].keys())
        assert len(contract_nodes) == 20
        missing_contract = sorted(contract_nodes - glb_nodes)
        assert missing_contract == [], f"Missing contract nodes in GLB: {missing_contract}"

        for item in (*AUTHORITATIVE_14_MODULES, *AUTHORITATIVE_CORE_BOARDS):
            assert item["blender_node"] in glb_nodes, f"Missing module node {item['blender_node']} in GLB"

    def test_house3d_node_vm_reports_zero_furniture_and_preserves_door_servo_and_leds(self) -> None:
        node_script = r"""
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const repoRoot = process.argv[1];
const house3dPath = path.join(repoRoot, "web", "house3d.js");
const sceneSpecPath = path.join(repoRoot, "hardware", "blender", "SCENE_SPEC.json");

const code = fs.readFileSync(house3dPath, "utf8");
const sceneSpec = JSON.parse(fs.readFileSync(sceneSpecPath, "utf8"));
const expectedNodes = Object.keys(sceneSpec.contract_nodes);

function makeColor(hex = 0) {
  let _hex = typeof hex === "number" ? hex : 0;
  return {
    getHex() { return _hex; },
    setHex(h) { _hex = h; return this; },
    clone() { return makeColor(_hex); },
  };
}
class Vector2 { constructor(x = 0, y = 0) { this.x = x; this.y = y; } }
class Vector3 {
  constructor(x = 0, y = 0, z = 0) { this.x = x; this.y = y; this.z = z; }
  set(x, y, z) { this.x = x; this.y = y; this.z = z; return this; }
  clone() { return new Vector3(this.x, this.y, this.z); }
  project() { this.x = 0; this.y = 0; this.z = 0.5; return this; }
}
class Material {
  constructor(opts = {}) {
    this.name = opts.name || "";
    this.color = makeColor(opts.color || 0);
    this.emissive = makeColor(opts.emissive || 0);
    this.emissiveIntensity = opts.emissiveIntensity !== undefined ? opts.emissiveIntensity : 0;
    this.opacity = opts.opacity !== undefined ? opts.opacity : 1;
    this.transparent = Boolean(opts.transparent);
    this.roughness = opts.roughness || 0.5;
    this.metalness = opts.metalness || 0;
    this.needsUpdate = false;
    this.userData = {};
  }
  clone() {
    return new Material({
      name: this.name,
      color: this.color.getHex(),
      emissive: this.emissive.getHex(),
      emissiveIntensity: this.emissiveIntensity,
      opacity: this.opacity,
      transparent: this.transparent,
      roughness: this.roughness,
      metalness: this.metalness,
    });
  }
}
class Object3D {
  constructor(name = "") {
    this.name = name;
    this.children = [];
    this.parent = null;
    this.visible = true;
    this.position = new Vector3(0, 0, 0);
    this.rotation = new Vector3(0, 0, 0);
    this.scale = new Vector3(1, 1, 1);
    this.userData = {};
    this.castShadow = false;
    this.receiveShadow = false;
  }
  add(child) { if (child) { child.parent = this; this.children.push(child); } return this; }
  remove(child) { const i = this.children.indexOf(child); if (i >= 0) this.children.splice(i, 1); return this; }
  traverse(fn) { fn(this); for (const c of this.children) c.traverse(fn); }
  getObjectByName(name) {
    if (this.name === name) return this;
    for (const c of this.children) { const f = c.getObjectByName(name); if (f) return f; }
    return null;
  }
  clone() { const c = new Object3D(this.name); c.position = this.position.clone(); c.rotation = this.rotation.clone(); c.scale = this.scale.clone(); return c; }
  lookAt() {}
  updateMatrixWorld() {}
  getWorldPosition(target) { target.set(this.position.x, this.position.y, this.position.z); return target; }
}
class Mesh extends Object3D {
  constructor(geo, mat, name = "") {
    super(name);
    this.isMesh = true;
    this.geometry = geo || { attributes: { position: { array: new Float32Array(30), needsUpdate: false } } };
    this.material = mat || new Material({ name: name ? "Mat_" + name : "" });
  }
}
class Box3 {
  constructor() { this.min = new Vector3(-0.1, -0.1, -0.1); this.max = new Vector3(0.1, 0.1, 0.1); }
  setFromObject(obj) {
    const p = obj && obj.position ? obj.position : new Vector3();
    this.min = new Vector3(p.x - 0.1, p.y - 0.1, p.z - 0.1);
    this.max = new Vector3(p.x + 0.1, p.y + 0.1, p.z + 0.1);
    return this;
  }
  getCenter(t) { t.set((this.min.x + this.max.x) * 0.5, (this.min.y + this.max.y) * 0.5, (this.min.z + this.max.z) * 0.5); return t; }
  isEmpty() { return false; }
  copy(other) { this.min = other.min.clone(); this.max = other.max.clone(); return this; }
  union(other) {
    this.min.x = Math.min(this.min.x, other.min.x); this.min.y = Math.min(this.min.y, other.min.y); this.min.z = Math.min(this.min.z, other.min.z);
    this.max.x = Math.max(this.max.x, other.max.x); this.max.y = Math.max(this.max.y, other.max.y); this.max.z = Math.max(this.max.z, other.max.z);
    return this;
  }
}
class Light extends Object3D {
  constructor(color, intensity = 0, distance = 10) {
    super();
    this.color = makeColor(color);
    this.intensity = intensity;
    this.distance = distance;
    this.shadow = { mapSize: { width: 0, height: 0 }, camera: { near: 0, far: 0, left: 0, right: 0, top: 0, bottom: 0 }, bias: 0 };
  }
}

const mockVillaRoot = new Object3D("VillaRoot");
for (const nodeName of expectedNodes) {
  const grp = new Object3D(nodeName);
  const xyz = sceneSpec.contract_nodes[nodeName].gltf_xyz || [0, 0, 0];
  grp.position.set(xyz[0], xyz[1], xyz[2]);
  grp.add(new Mesh(null, new Material({ name: "Mat_" + nodeName }), nodeName + "_mesh"));
  mockVillaRoot.add(grp);
}

function makeMockEl(tag) {
  const attrs = {};
  let _innerHTML = "";
  const stateSpan = { textContent: "", style: {} };
  return {
    tagName: String(tag || "div").toUpperCase(),
    clientWidth: 960, clientHeight: 600, offsetWidth: 112, offsetHeight: 24,
    className: "", title: "", style: {}, dataset: {}, children: [], firstChild: null,
    classList: { toggle() {}, add() {}, remove() {} },
    setAttribute(k, v) { attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(attrs, k) ? attrs[k] : null; },
    addEventListener() {},
    appendChild(ch) { this.children.push(ch); return ch; },
    insertBefore(ch) { this.children.unshift(ch); this.firstChild = ch; return ch; },
    querySelector(sel) { return sel === ".pin-state" ? stateSpan : null; },
    getBoundingClientRect() { return { left: 0, top: 0, right: 960, bottom: 600, width: 960, height: 600 }; },
    get innerHTML() { return _innerHTML; },
    set innerHTML(val) {
      _innerHTML = String(val || "");
      const m = _innerHTML.match(/<strong class="pin-state">([^<]*)<\/strong>/);
      if (m) stateSpan.textContent = m[1];
    },
  };
}

const canvasContainer = makeMockEl("div");
const labelsContainer = makeMockEl("div");
const rafQueue = [];
const THREE = {
  Scene: Object3D, Group: Object3D, Mesh, Points: Mesh, Line: Mesh,
  Color: function(h) { return makeColor(h); },
  FogExp2: function() {},
  PerspectiveCamera: class extends Object3D { constructor(fov, aspect) { super(); this.fov = fov; this.aspect = aspect; } updateProjectionMatrix() {} },
  WebGLRenderer: class { constructor() { this.domElement = makeMockEl("canvas"); this.shadowMap = { enabled: false, type: 0 }; } setSize() {} setPixelRatio() {} render() {} getContext() { return null; } },
  Raycaster: class { setFromCamera() {} intersectObjects() { return []; } },
  Vector2, Vector3, Box3,
  HemisphereLight: Light, DirectionalLight: Light, PointLight: Light,
  PlaneGeometry: function() {}, BoxGeometry: function() {}, CylinderGeometry: function() {},
  SphereGeometry: function() {}, ConeGeometry: function() {}, RingGeometry: function() {},
  BufferGeometry: class { constructor() { this.attributes = {}; } setAttribute(k, v) { this.attributes[k] = v; } setFromPoints() { return this; } },
  BufferAttribute: class { constructor(arr) { this.array = arr; this.needsUpdate = false; } },
  CatmullRomCurve3: function() {}, TubeGeometry: function() {},
  MeshStandardMaterial: Material, MeshBasicMaterial: Material, PointsMaterial: Material, LineBasicMaterial: Material,
  GridHelper: Object3D, DoubleSide: 2, PCFSoftShadowMap: 2, ACESFilmicToneMapping: 4, sRGBEncoding: 3001,
  GLTFLoader: class { load(url, onLoad) { onLoad({ scene: mockVillaRoot }); } },
};

const sandbox = {
  THREE,
  window: { THREE, devicePixelRatio: 1, innerWidth: 1280, addEventListener() {} },
  document: {
    hidden: false,
    getElementById(id) { return id === "canvasBox" ? canvasContainer : id === "labelsBox" ? labelsContainer : null; },
    createElement(tag) { return makeMockEl(tag); },
    querySelector() { return null; },
  },
  navigator: { webdriver: false, userAgent: "NodeVM" },
  requestAnimationFrame(cb) { rafQueue.push(cb); },
  console, Math, Number, Boolean, String, Array, Object, Set, Promise, Float32Array, parseInt,
};
sandbox.window.document = sandbox.document;
vm.createContext(sandbox);
vm.runInContext(code, sandbox);

const sh = sandbox.window.SmartHome3D;
sh.init("canvasBox", "labelsBox", () => {});

let simTime = 0;
function stepFrames(n) {
  for (let i = 0; i < n; i++) {
    const cb = rafQueue.shift();
    if (!cb) break;
    simTime += 500;
    cb(simTime);
  }
}

stepFrames(4);
const initial = sh.getDebugState();

sh.updateDevices([
  { id: "main_door", state: "OPEN" },
  { id: "living_room_light", state: "ON" },
  { id: "bedroom_light", state: "ON" },
  { id: "garden_pump", state: "OFF" },
  { id: "alarm_siren", state: "OFF" },
  { id: "speaker_amp", state: "OFF" },
]);
stepFrames(12);
const opened = sh.getDebugState();
const openPivotRad = mockVillaRoot.getObjectByName("door_pivot").rotation.y;
const openHornRad = mockVillaRoot.getObjectByName("sg90_horn_pivot").rotation.y;

sh.updateDevices([
  { id: "main_door", state: "CLOSED" },
  { id: "living_room_light", state: "OFF" },
  { id: "bedroom_light", state: "OFF" },
  { id: "garden_pump", state: "OFF" },
  { id: "alarm_siren", state: "OFF" },
  { id: "speaker_amp", state: "OFF" },
]);
stepFrames(12);
const closed = sh.getDebugState();

const domModuleIds = labelsContainer.children.map((el) => el.getAttribute("data-module-id")).filter(Boolean);
process.stdout.write(JSON.stringify({ initial, opened, closed, openPivotRad, openHornRad, domModuleIds }));
"""
        proc = subprocess.run(
            ["node", "-e", node_script, str(REPO_ROOT)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        assert proc.returncode == 0, f"Node VM failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        data = json.loads(proc.stdout)

        # Zero furniture in Web 3D runtime
        for phase in ("initial", "opened", "closed"):
            st = data[phase]
            assert st["furnitureRemoved"] is True, f"{phase}: furnitureRemoved must be True"
            assert st["furnitureNodesCount"] == 0, f"{phase}: furnitureNodesCount must be 0"

        # All 20 contract nodes bound & all 14 modules + 2 core boards rendered as DOM pins
        scene_spec = _load_json("hardware/blender/SCENE_SPEC.json")
        expected_nodes = set(scene_spec["contract_nodes"].keys())
        assert len(expected_nodes) == 20
        assert expected_nodes <= set(data["initial"]["boundGlbNodes"])

        expected_module_ids = {m["module_id"] for m in (*AUTHORITATIVE_14_MODULES, *AUTHORITATIVE_CORE_BOARDS)}
        assert expected_module_ids <= set(data["domModuleIds"])

        # Door + servo horn synchronized animation & LED glow intact
        opened = data["opened"]
        assert opened["doorOpen"] is True
        assert opened["doorAngleDeg"] == pytest.approx(90.0, abs=0.1)
        assert opened["servoHornAngleDeg"] == pytest.approx(90.0, abs=0.1)
        assert data["openPivotRad"] == pytest.approx(math.pi / 2.0, abs=0.005)
        assert data["openHornRad"] == pytest.approx(math.pi / 2.0, abs=0.005)
        assert opened["livingLedEmissive"] > 0 and opened["livingPointLightIntensity"] > 0
        assert opened["bedroomLedEmissive"] > 0 and opened["bedroomPointLightIntensity"] > 0

        closed = data["closed"]
        assert closed["doorOpen"] is False
        assert closed["doorAngleDeg"] == pytest.approx(0.0, abs=0.1)
        assert closed["servoHornAngleDeg"] == pytest.approx(0.0, abs=0.1)
        assert closed["livingLedEmissive"] == 0 and closed["livingPointLightIntensity"] == 0
        assert closed["bedroomLedEmissive"] == 0 and closed["bedroomPointLightIntensity"] == 0
