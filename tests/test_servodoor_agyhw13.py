"""Automated verification & regression test suite for agyhw13_20261127 (R5 — Servo Door + 14-Module Parity).

Covers every R5 requirement:
1. Full parity of all 14 authoritative modules (`AUTHORITATIVE_14_MODULES`) + NodeMCU + Hub PCB across:
   - `hardware/in 3 d/build_meta/fit_table.json` & `hardware/in 3 d/verification_report.json` (16/16 PASS),
   - `hardware/blender/SCENE_SPEC.json` & binary `web/models/smarthome_villa.glb` (verified via `trimesh`),
   - `web/house3d.js` `PIN_META` Vietnamese label pins (`data-module-id`),
   - `web/data/wiring_contract.json`.
2. SG90 coaxial direct-drive mechanical SSOT parity across `component_dimensions_ssot.py`,
   `mica_design.py`, `print_domain.py`, `fit_table.json`, and `wiring_contract.json`,
   plus `compute_door_torque_margin()` safety margin >= 5x.
3. Door swept-volume check (`0..90 deg`, 19 poses, `0.0 mm^3` intersection, `collisions == []`)
   and integral `-2/+92 deg` end stops on `P07_SERVO_SHELF`.
4. All 40/40 wires satisfy `0 < length_cm <= 30.0`, SG90 wires `W03..W05 <= 25.0 cm`,
   and every endpoint maps to a real `HUB_CONNECTOR_MAP` pin or valid off-board module pin.
5. All 17/17 3D-print plates fit `180 x 200 x 250 mm`, are manifold, require 0 supports,
   0 fastener holes, and 0 forbidden glue/screw instructions.
6. Web 3D `web/house3d.js` runtime harness (Node.js VM): binds all 20 GLB contract nodes
   (incl. `SG90_DoorServo`, `sg90_horn_pivot`, `psu_5v_dc_jack`, `soil_lm393_board`),
   synchronously rotates `doorPivot` & `servoHornPivot` to `+90 deg` (OPEN) and `0 deg` (CLOSED),
   toggles living & bedroom LED emissive + PointLight (`> 0` ON, `0` OFF), and exposes `getDebugState()`.
7. KiCad PCB/schematic `C1..C9` + `D1..D2` presence and 0 ERC / 0 DRC errors.
"""

from __future__ import annotations

import importlib.util
import json
import math
import pathlib
import re
import subprocess
import sys
from typing import Any

import pytest
import trimesh

from hardware.component_dimensions_ssot import (
    AUTHORITATIVE_14_MODULES,
    AUTHORITATIVE_CORE_BOARDS,
    COMPONENT_DIM_MAP,
    SG90_MECHANICAL_SPECS,
    compute_door_torque_margin,
)
from hardware.wiring_contract import HUB_CONNECTOR_MAP

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

EXPECTED_WIRE_IDS = tuple(f"W{i:02d}" for i in range(1, 41))
OFFBOARD_ALLOWED_PINS: dict[str, set[str]] = {
    "PAM8403": {"L_OUT+", "L_OUT-"},
    "LM393": {"P1", "P2"},
}
REQUIRED_CAPS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9")
REQUIRED_DIODES = ("D1", "D2")


def _load_json(rel_path: str) -> dict[str, Any]:
    path = REPO_ROOT / rel_path
    assert path.exists(), f"Missing JSON artifact: {rel_path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_module_from_path(name: str, path: pathlib.Path) -> Any:
    assert path.exists(), f"Missing Python module: {path}"
    parent = str(path.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _parse_pin_meta_from_house3d() -> list[dict[str, str]]:
    js_text = (REPO_ROOT / "web/house3d.js").read_text(encoding="utf-8")
    m = re.search(r"const\s+PIN_META\s*=\s*\[(.*?)\];", js_text, re.DOTALL)
    assert m is not None, "PIN_META array not found in web/house3d.js"
    entries: list[dict[str, str]] = []
    for line in m.group(1).splitlines():
        if "id:" not in line:
            continue
        m_id = re.search(r'\bid\s*:\s*"([^"]+)"', line)
        m_mod = re.search(r'\bmoduleId\s*:\s*"([^"]+)"', line)
        m_name = re.search(r'\bshortName\s*:\s*"([^"]+)"', line)
        m_kind = re.search(r'\bkind\s*:\s*"([^"]+)"', line)
        if m_id:
            entries.append(
                {
                    "id": m_id.group(1),
                    "moduleId": m_mod.group(1) if m_mod else "",
                    "shortName": m_name.group(1) if m_name else "",
                    "kind": m_kind.group(1) if m_kind else "",
                }
            )
    return entries


class TestAuthoritative14ModulesParity:
    def test_all_14_modules_plus_nodemcu_and_hub_pcb_have_full_cross_layer_parity(self) -> None:
        assert len(AUTHORITATIVE_14_MODULES) == 14
        assert len(AUTHORITATIVE_CORE_BOARDS) == 2
        all_16 = (*AUTHORITATIVE_14_MODULES, *AUTHORITATIVE_CORE_BOARDS)
        assert len(all_16) == 16

        fit_table = _load_json("hardware/in 3 d/build_meta/fit_table.json")
        vrep = _load_json("hardware/in 3 d/verification_report.json")
        scene_spec = _load_json("hardware/blender/SCENE_SPEC.json")
        contract = _load_json("web/data/wiring_contract.json")

        # 1. fit_table.json & verification_report.json pcb_module_fit (16/16 PASS)
        assert fit_table["authoritative_row_count"] == 16
        assert fit_table["all_fit_passed"] is True
        fit_by_mod = {row["module_id"]: row for row in fit_table["rows"]}
        assert len(fit_by_mod) == 16

        vrep_fit = vrep["pcb_module_fit"]
        assert vrep_fit["authoritative_row_count"] == 16
        assert vrep_fit["all_fit_passed"] is True
        vrep_fit_by_mod = {row["module_id"]: row for row in vrep_fit["rows"]}
        assert len(vrep_fit_by_mod) == 16

        # 2. SCENE_SPEC.json & binary smarthome_villa.glb loaded via trimesh
        assert scene_spec["authoritative_module_count"] == 14
        assert scene_spec["contract_node_count"] == 20
        contract_nodes = scene_spec["contract_nodes"]
        assert len(contract_nodes) == 20

        glb_path = REPO_ROOT / "web/models/smarthome_villa.glb"
        assert glb_path.exists(), "Missing web/models/smarthome_villa.glb"
        assert 0 < glb_path.stat().st_size < 10 * 1024 * 1024
        glb_scene = trimesh.load(str(glb_path))
        glb_nodes = set(glb_scene.graph.nodes)
        missing_glb_contract_nodes = sorted(set(contract_nodes.keys()) - glb_nodes)
        assert missing_glb_contract_nodes == [], (
            f"SCENE_SPEC contract_nodes missing from binary GLB: {missing_glb_contract_nodes}"
        )

        # 3. web/house3d.js PIN_META Vietnamese labels & data-module-id wiring
        house3d_src = (REPO_ROOT / "web/house3d.js").read_text(encoding="utf-8")
        assert 'el.setAttribute("data-module-id", m.moduleId)' in house3d_src
        pin_entries = _parse_pin_meta_from_house3d()
        pin_by_id = {p["id"]: p for p in pin_entries}
        pin_by_mod = {p["moduleId"]: p for p in pin_entries if p["moduleId"]}

        # 4. web/data/wiring_contract.json parity
        assert contract["counts"]["modules"] == 14
        assert contract["counts"]["authoritative_14_modules"] == 14
        assert contract["counts"]["authoritative_core_boards"] == 2
        wc_modules = {m["module_id"]: m for m in contract["modules"]}
        wc_auth14 = {m["module_id"]: m for m in contract["authoritative_14_modules"]}
        wc_core = {m["module_id"]: m for m in contract["authoritative_core_boards"]}

        for item in all_16:
            mid = item["module_id"]
            hw_id = item["hw_part_id"]
            bnode = item["blender_node"]
            pin_id = item["web3d_pin_id"]

            # fit_table.json & verification_report.json
            assert mid in fit_by_mod, f"{mid} missing from fit_table.json"
            assert fit_by_mod[mid]["status"] == "PASS", f"{mid} fit_table status != PASS"
            assert fit_by_mod[mid]["hw_part_id"] == hw_id
            assert fit_by_mod[mid]["mount_part"].strip()

            assert mid in vrep_fit_by_mod, f"{mid} missing from verification_report.json pcb_module_fit"
            assert vrep_fit_by_mod[mid]["status"] == "PASS"
            assert vrep_fit_by_mod[mid]["hw_part_id"] == hw_id

            # SCENE_SPEC.json + binary GLB
            assert bnode in contract_nodes, f"{mid} blender_node {bnode!r} missing from SCENE_SPEC.json"
            assert bnode in glb_nodes, f"{mid} blender_node {bnode!r} missing from smarthome_villa.glb"

            # web/house3d.js PIN_META
            assert pin_id in pin_by_id, f"{mid} web3d_pin_id {pin_id!r} missing from house3d.js PIN_META"
            assert mid in pin_by_mod, f"{mid} moduleId missing from house3d.js PIN_META"
            assert pin_by_id[pin_id]["moduleId"] == mid
            assert pin_by_id[pin_id]["shortName"].strip(), f"{mid} empty Vietnamese pin label"

            # web/data/wiring_contract.json
            if mid in ("nodemcu", "hub_pcb"):
                assert mid in wc_core, f"Core board {mid} missing from wiring_contract.json authoritative_core_boards"
                assert wc_core[mid]["blender_node"] == bnode
                assert wc_core[mid]["web3d_pin_id"] == pin_id
            else:
                assert mid in wc_modules, f"Module {mid} missing from wiring_contract.json modules"
                assert mid in wc_auth14, f"Module {mid} missing from wiring_contract.json authoritative_14_modules"
                assert wc_modules[mid]["blender_node"] == bnode
                assert wc_modules[mid]["web3d_pin_id"] == pin_id
                assert len(wc_modules[mid].get("wire_ids") or []) >= 2


class TestSG90MechanicalSpecsAndTorque:
    def test_sg90_ssot_matches_mica_print_domain_fit_table_and_torque_margin(self) -> None:
        # 1. SSOT specs
        sg90_dim = COMPONENT_DIM_MAP["sg90_servo"]
        assert sg90_dim.dims_mm == (22.8, 12.2, 22.5)
        assert sg90_dim.pigtail_cm == 25.0

        assert SG90_MECHANICAL_SPECS["body_l_mm"] == pytest.approx(22.8)
        assert SG90_MECHANICAL_SPECS["body_w_mm"] == pytest.approx(12.2)
        assert SG90_MECHANICAL_SPECS["body_h_mm"] == pytest.approx(22.5)
        assert SG90_MECHANICAL_SPECS["ear_span_mm"] == pytest.approx(32.2)
        assert SG90_MECHANICAL_SPECS["ear_thickness_mm"] == pytest.approx(2.5)
        assert SG90_MECHANICAL_SPECS["ear_hole_pitch_mm"] == pytest.approx(27.8)
        assert SG90_MECHANICAL_SPECS["shaft_offset_from_front_mm"] == pytest.approx(5.9)
        assert SG90_MECHANICAL_SPECS["stall_torque_kg_cm_4v8"] == pytest.approx(1.80)
        assert SG90_MECHANICAL_SPECS["hinge_pivot_xy_mm"] == (77.0, 201.5)
        assert SG90_MECHANICAL_SPECS["endstop_deg_range"] == (-2.0, 92.0)

        # 2. Torque margin >= 5x
        tm = compute_door_torque_margin()
        assert tm["sg90_stall_torque_kg_cm"] == pytest.approx(1.80)
        assert tm["passes_min_5x_margin"] is True
        assert tm["worst_case_safety_margin_x"] >= 5.0
        assert tm["nominal_safety_margin_x"] >= 50.0

        # 3. mica_design.py cutout & HW_SG90 alignment
        md = _load_module_from_path("mica_design_test_mod", REPO_ROOT / "hardware/mica/mica_design.py")
        params = md.default_param_values(T_mm=3.0, tab_clr=0.25)
        assert params["sg90_L"] == pytest.approx(SG90_MECHANICAL_SPECS["body_l_mm"] + 0.5)
        assert params["sg90_W"] == pytest.approx(SG90_MECHANICAL_SPECS["body_w_mm"] + 0.5)
        assert params["sg90_pitch"] == pytest.approx(SG90_MECHANICAL_SPECS["ear_hole_pitch_mm"])

        panels, _ = md.build_design()
        p07 = next(p for p in panels if p.panel_id == "P07_SERVO_SHELF")
        sg90_cut = next(r for r in p07.cut_rects if r.name == "SG90_Cutout")
        assert md.eval_expr(sg90_cut.du, params) == pytest.approx(23.3)
        assert md.eval_expr(sg90_cut.dv, params) == pytest.approx(12.7)

        hw_sg90 = next(h for h in md.HARDWARE_PARTS if h.part_id == "HW_SG90")
        assert hw_sg90.center_xyz == SG90_MECHANICAL_SPECS["servo_body_center_xyz_mm"]
        assert hw_sg90.size_xyz == (
            SG90_MECHANICAL_SPECS["ear_span_mm"],
            SG90_MECHANICAL_SPECS["body_w_mm"],
            SG90_MECHANICAL_SPECS["body_h_mm"],
        )
        # Coaxial shaft X check: body front = center_x + body_l/2; shaft = front - shaft_offset_from_front
        shaft_x = hw_sg90.center_xyz[0] + SG90_MECHANICAL_SPECS["body_l_mm"] / 2.0 - SG90_MECHANICAL_SPECS["shaft_offset_from_front_mm"]
        assert shaft_x == pytest.approx(SG90_MECHANICAL_SPECS["hinge_pivot_xy_mm"][0], abs=0.05)

        # 4. print_domain.py supports (SUP10, SUP10B, SUP11)
        pd_mod = _load_module_from_path("print_domain_test_mod", REPO_ROOT / "hardware/in 3 d/scripts/print_domain.py")
        supports = {s.part_id: s for s in pd_mod.build_support_specs()}

        sup11 = supports["SUP11_SG90_SNAP_SADDLE"]
        assert sup11.params["window_x"] > SG90_MECHANICAL_SPECS["body_l_mm"]
        assert sup11.params["window_y"] > SG90_MECHANICAL_SPECS["body_w_mm"]
        assert sup11.params["ear_clear_x"] >= SG90_MECHANICAL_SPECS["ear_span_mm"]
        assert sup11.params["ear_t"] >= SG90_MECHANICAL_SPECS["ear_thickness_mm"]

        sup10b = supports["SUP10B_DOOR_HORN_COUPLER"]
        assert sup10b.params["horn_w"] == pytest.approx(SG90_MECHANICAL_SPECS["horn_width_mm"])
        assert sup10b.params["slot_w"] == pytest.approx(SG90_MECHANICAL_SPECS["coupler_slot_w_mm"])
        assert sup10b.params["slot_w"] > sup10b.params["horn_w"]

        sup10 = supports["SUP10_DOOR_MORTISE_HINGE"]
        assert sup10.qty == 2
        assert sup10.params["bore_d"] > sup10.params["pin_d"]
        hinge_pin_offset_y = sup10.params["plate_t"] + sup10.params["knuckle_od"] / 2.0 + 0.5
        for pl in sup10.assembly_placements:
            assert pl["x"] == pytest.approx(SG90_MECHANICAL_SPECS["hinge_pivot_xy_mm"][0])
            assert pl["y"] + hinge_pin_offset_y == pytest.approx(SG90_MECHANICAL_SPECS["hinge_pivot_xy_mm"][1])

        # 5. fit_table.json & wiring_contract.json parity
        fit_table = _load_json("hardware/in 3 d/build_meta/fit_table.json")
        sg90_row = next(r for r in fit_table["rows"] if r["module_id"] == "sg90_servo")
        assert sg90_row["status"] == "PASS"
        assert "22.8x12.2x22.5" in sg90_row["board_size_mm"]
        assert "32.2" in sg90_row["board_size_mm"]
        assert "23.3x12.7" in sg90_row["mount_inner_size_mm"]
        assert "SUP10B" in sg90_row["mount_part"] and "SUP11" in sg90_row["mount_part"]

        wc = _load_json("web/data/wiring_contract.json")
        wc_sg90 = wc["sg90_mechanical_specs"]
        assert wc_sg90["body_l_mm"] == pytest.approx(22.8)
        assert wc_sg90["body_w_mm"] == pytest.approx(12.2)
        assert wc_sg90["body_h_mm"] == pytest.approx(22.5)
        assert wc_sg90["ear_span_mm"] == pytest.approx(32.2)
        assert wc_sg90["shaft_offset_from_front_mm"] == pytest.approx(5.9)
        assert wc_sg90["stall_torque_kg_cm_4v8"] == pytest.approx(1.80)


class TestDoorSweptVolumeAndEndStops:
    def test_door_swept_volume_0_to_90_deg_zero_collision_and_endstops_present(self) -> None:
        vrep = _load_json("hardware/in 3 d/verification_report.json")
        arep = _load_json("hardware/in 3 d/build_meta/assembly_report.json")

        for label, swept in (
            ("verification_report.assembly.door_swept_volume_check", vrep["assembly"]["door_swept_volume_check"]),
            ("verification_report.door_swept_volume_check", vrep["door_swept_volume_check"]),
            ("assembly_report.door_swept_volume_check", arep["door_swept_volume_check"]),
        ):
            assert swept["passed"] is True, f"{label} did not pass"
            assert swept["pivot_xy_mm"] == [77.0, 201.5]
            assert swept["angle_range_deg"] == [0, 90]
            assert swept["angles_checked"] == 19
            assert swept["step_deg"] == 5
            assert float(swept["max_intersection_mm3"]) == 0.0
            assert float(swept["horn_coupler_intersection_mm3"]) == 0.0
            assert swept["collisions"] == []
            moving = set(swept["moving_parts"])
            assert {"SG90_WhiteHorn", "P08_DOOR_LEAF", "SUP10B_DOOR_HORN_COUPLER"} <= moving
            assert swept["torque_margin"]["passes_min_5x_margin"] is True
            assert float(swept["torque_margin"]["worst_case_safety_margin_x"]) >= 5.0

        # Verify integral -2/+92 deg end stops on P07_SERVO_SHELF
        assert SG90_MECHANICAL_SPECS["endstop_deg_range"] == (-2.0, 92.0)

        panels_v2_src = (REPO_ROOT / "hardware/in 3 d/scripts/build_panels_v2.py").read_text(encoding="utf-8")
        assert "lug_closed" in panels_v2_src and "-2 deg" in panels_v2_src
        assert "lug_open" in panels_v2_src and "+92 deg" in panels_v2_src
        assert "body.fuse(lug_closed).fuse(lug_open)" in panels_v2_src

        p07_meta = _load_json("hardware/in 3 d/build_meta/P07_SERVO_SHELF.json")
        assert p07_meta["valid"] is True
        assert p07_meta["solids"] == 1
        assert p07_meta["local_bbox_min"][2] == pytest.approx(-10.0, abs=0.1)
        assert p07_meta["print_bbox_mm"][2] == pytest.approx(13.0, abs=0.1)

        p07_recon = next(r for r in vrep["assembly"]["reconstruction_checks"] if r["source_panel_id"] == "P07_SERVO_SHELF")
        assert p07_recon["passed"] is True
        assert p07_recon["actual_bbox_min"][2] == pytest.approx(98.5, abs=0.1)
        assert p07_recon["actual_bbox_max"][2] == pytest.approx(111.5, abs=0.1)

        p07_stl = REPO_ROOT / "hardware/in 3 d/parts/P07_SERVO_SHELF.stl"
        assert p07_stl.exists()
        mesh = trimesh.load(str(p07_stl))
        z_extent = float(mesh.bounds[1][2] - mesh.bounds[0][2])
        assert z_extent == pytest.approx(13.0, abs=0.2), f"Expected 13.0mm Z extent incl. end-stop lug, got {z_extent}"


class TestFortyWiresAndSG90Pigtail:
    def test_40_wires_within_30cm_sg90_within_25cm_and_valid_endpoints(self) -> None:
        wl = _load_json("hardware/wire_lengths.json")
        wc = _load_json("web/data/wiring_contract.json")

        auth_mod_ids = {m["module_id"] for m in AUTHORITATIVE_14_MODULES}

        assert wl["total_wires"] == 40
        assert wl["all_within_30cm"] is True
        assert wl["sg90_within_25cm"] is True
        assert float(wl["sg90_max_length_cm"]) <= 25.0
        assert wc["wire_lengths_summary"]["total_wires"] == 40
        assert wc["wire_lengths_summary"]["all_within_30cm"] is True

        wl_wires = wl["wires"]
        wc_wires = wc["wires"]
        assert len(wl_wires) == 40
        assert len(wc_wires) == 40
        assert tuple(w["wire_id"] for w in wl_wires) == EXPECTED_WIRE_IDS
        assert tuple(w["wire_id"] for w in wc_wires) == EXPECTED_WIRE_IDS

        for w_wl, w_wc in zip(wl_wires, wc_wires):
            wid = w_wl["wire_id"]
            len_wl = float(w_wl["length_cm"])
            len_wc = float(w_wc["length_cm"])
            assert 0.0 < len_wl <= 30.0, f"{wid} exceeds 30 cm in wire_lengths.json: {len_wl}"
            assert 0.0 < len_wc <= 30.0, f"{wid} exceeds 30 cm in wiring_contract.json: {len_wc}"
            assert abs(len_wl - len_wc) <= 0.02

            if wid in ("W03", "W04", "W05"):
                assert w_wl["module_id"] == "sg90_servo"
                assert w_wl["hub_ref"] == "J3"
                assert 0.0 < len_wl <= 25.0, f"SG90 wire {wid} exceeds 25 cm pigtail limit: {len_wl}"
                assert 0.0 < len_wc <= 25.0, f"SG90 wire {wid} exceeds 25 cm in contract: {len_wc}"

            for src_name, item in (("wire_lengths.json", w_wl), ("wiring_contract.json", w_wc)):
                hub_ref = item["hub_ref"]
                hub_pin = str(item["hub_pin"])
                if hub_ref in HUB_CONNECTOR_MAP:
                    valid_pins = {p[0] for p in HUB_CONNECTOR_MAP[hub_ref].pins}
                    assert hub_pin in valid_pins, f"{wid} ({src_name}) invalid hub pin {hub_ref}.{hub_pin}"
                else:
                    assert hub_ref in OFFBOARD_ALLOWED_PINS, f"{wid} ({src_name}) unknown hub_ref {hub_ref!r}"
                    assert hub_pin in OFFBOARD_ALLOWED_PINS[hub_ref], f"{wid} ({src_name}) invalid offboard pin {hub_ref}.{hub_pin}"

                assert item["module_id"] in auth_mod_ids, f"{wid} ({src_name}) unknown module_id {item['module_id']!r}"
                assert str(item.get("module_pin", "")).strip(), f"{wid} ({src_name}) empty module_pin"


class TestPrintPlatesAndZeroScrewsGlue:
    def test_all_17_plates_fit_bed_manifold_zero_supports_and_zero_fasteners(self) -> None:
        vrep = _load_json("hardware/in 3 d/verification_report.json")
        srep = _load_json("hardware/in 3 d/build_meta/slice_report.json")

        assert vrep["all_passed"] is True
        assert [float(x) for x in vrep["bed_mm"]] == [180.0, 200.0, 250.0]
        assert vrep["plates_verified"] == 17
        assert vrep["totals"]["total_plates"] == 17
        assert vrep["totals"]["plates_passed"] == 17
        assert vrep["totals"]["any_plate_needs_supports"] is False
        assert vrep["needs_slicer_supports"] is False

        audit = vrep["screw_glue_audit"]
        assert audit["passed"] is True
        assert audit["geometry_fastener_hole_count"] == 0
        assert audit["readme_forbidden_instruction_count"] == 0

        assert srep["all_passed"] is True
        assert srep["parts_summary"]["all_manifold"] is True
        assert srep["parts_summary"]["passed_parts"] == srep["parts_summary"]["total_parts"] == 60
        plates = srep["plates"]
        assert len(plates) == 17

        for plate in plates:
            pid = plate["plate_id"]
            assert plate["stl_manifold"] is True, f"{pid} STL not manifold"
            assert plate["all_objects_manifold"] is True, f"{pid} 3MF object not manifold"
            assert plate["slice_ok"] is True and plate["slicer_returncode"] == 0, f"{pid} failed slicing"
            assert plate["needs_supports"] is False, f"{pid} needs supports"
            assert plate["outside_volume_warning"] is False, f"{pid} outside print volume"

            sx, sy, sz = [float(v) for v in plate["stl_size_mm"]]
            assert sx <= 180.0 and sy <= 200.0 and sz <= 250.0, f"{pid} exceeds bed: {(sx, sy, sz)}"

            gb = plate["gcode_extrusion_bounds_mm"]
            assert 0.0 <= float(gb["x_min"]) <= float(gb["x_max"]) <= 180.0, f"{pid} G-code X out of bed: {gb}"
            assert 0.0 <= float(gb["y_min"]) <= float(gb["y_max"]) <= 200.0, f"{pid} G-code Y out of bed: {gb}"
            assert 0.0 <= float(gb["z_min"]) <= float(gb["z_max"]) <= 250.0, f"{pid} G-code Z out of bed: {gb}"


class TestWeb3DHouse3DRuntimeHarness:
    def test_house3d_binds_all_20_glb_nodes_syncs_door_and_horn_and_toggles_leds(self) -> None:
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

class Vector2 {
  constructor(x = 0, y = 0) { this.x = x; this.y = y; }
}

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
  add(child) {
    if (!child) return this;
    child.parent = this;
    this.children.push(child);
    return this;
  }
  remove(child) {
    const i = this.children.indexOf(child);
    if (i >= 0) this.children.splice(i, 1);
    return this;
  }
  traverse(fn) {
    fn(this);
    for (const c of this.children) c.traverse(fn);
  }
  getObjectByName(name) {
    if (this.name === name) return this;
    for (const c of this.children) {
      const found = c.getObjectByName(name);
      if (found) return found;
    }
    return null;
  }
  clone() {
    const c = new Object3D(this.name);
    c.position = this.position.clone();
    c.rotation = this.rotation.clone();
    c.scale = this.scale.clone();
    return c;
  }
  lookAt() {}
  updateMatrixWorld() {}
  getWorldPosition(target) {
    target.set(this.position.x, this.position.y, this.position.z);
    return target;
  }
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
  constructor() {
    this.min = new Vector3(-0.1, -0.1, -0.1);
    this.max = new Vector3(0.1, 0.1, 0.1);
  }
  setFromObject(obj) {
    const p = obj && obj.position ? obj.position : new Vector3();
    this.min = new Vector3(p.x - 0.1, p.y - 0.1, p.z - 0.1);
    this.max = new Vector3(p.x + 0.1, p.y + 0.1, p.z + 0.1);
    return this;
  }
  getCenter(t) {
    t.set((this.min.x + this.max.x) * 0.5, (this.min.y + this.max.y) * 0.5, (this.min.z + this.max.z) * 0.5);
    return t;
  }
  isEmpty() { return false; }
  copy(other) { this.min = other.min.clone(); this.max = other.max.clone(); return this; }
  union(other) {
    this.min.x = Math.min(this.min.x, other.min.x);
    this.min.y = Math.min(this.min.y, other.min.y);
    this.min.z = Math.min(this.min.z, other.min.z);
    this.max.x = Math.max(this.max.x, other.max.x);
    this.max.y = Math.max(this.max.y, other.max.y);
    this.max.z = Math.max(this.max.z, other.max.z);
    return this;
  }
}

// Build mock GLB villa scene with all 20 contract nodes
const mockVillaRoot = new Object3D("VillaRoot");
for (const nodeName of expectedNodes) {
  const grp = new Object3D(nodeName);
  const xyz = sceneSpec.contract_nodes[nodeName].gltf_xyz || [0, 0, 0];
  grp.position.set(xyz[0], xyz[1], xyz[2]);
  const childMesh = new Mesh(null, new Material({ name: "Mat_" + nodeName }), nodeName + "_mesh");
  grp.add(childMesh);
  mockVillaRoot.add(grp);
}

class Light extends Object3D {
  constructor(color, intensity = 0, distance = 10) {
    super();
    this.color = makeColor(color);
    this.intensity = intensity;
    this.distance = distance;
    this.shadow = {
      mapSize: { width: 0, height: 0 },
      camera: { near: 0, far: 0, left: 0, right: 0, top: 0, bottom: 0 },
      bias: 0,
    };
  }
}

function makeMockEl(tag) {
  const attrs = {};
  let _innerHTML = "";
  const stateSpan = { textContent: "", style: {} };
  const el = {
    tagName: String(tag || "div").toUpperCase(),
    clientWidth: 960,
    clientHeight: 600,
    offsetWidth: 112,
    offsetHeight: 24,
    className: "",
    title: "",
    style: {},
    dataset: {},
    children: [],
    firstChild: null,
    classList: { toggle() {}, add() {}, remove() {} },
    setAttribute(k, v) { attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(attrs, k) ? attrs[k] : null; },
    addEventListener() {},
    appendChild(ch) { this.children.push(ch); return ch; },
    insertBefore(ch) { this.children.unshift(ch); this.firstChild = ch; return ch; },
    querySelector(sel) {
      if (sel === ".pin-state") return stateSpan;
      return null;
    },
    getBoundingClientRect() { return { left: 0, top: 0, right: 960, bottom: 600, width: 960, height: 600 }; },
    get innerHTML() { return _innerHTML; },
    set innerHTML(val) {
      _innerHTML = String(val || "");
      const m = _innerHTML.match(/<strong class="pin-state">([^<]*)<\/strong>/);
      if (m) stateSpan.textContent = m[1];
    },
  };
  return el;
}

const canvasContainer = makeMockEl("div");
const labelsContainer = makeMockEl("div");

const rafQueue = [];
const THREE = {
  Scene: Object3D,
  Group: Object3D,
  Mesh,
  Points: Mesh,
  Line: Mesh,
  Color: function(h) { return makeColor(h); },
  FogExp2: function() {},
  PerspectiveCamera: class extends Object3D {
    constructor(fov, aspect) { super(); this.fov = fov; this.aspect = aspect; }
    updateProjectionMatrix() {}
  },
  WebGLRenderer: class {
    constructor() {
      this.domElement = makeMockEl("canvas");
      this.shadowMap = { enabled: false, type: 0 };
    }
    setSize() {}
    setPixelRatio() {}
    render() {}
    getContext() { return null; }
  },
  Raycaster: class {
    setFromCamera() {}
    intersectObjects() { return []; }
  },
  Vector2,
  Vector3,
  Box3,
  HemisphereLight: Light,
  DirectionalLight: Light,
  PointLight: Light,
  PlaneGeometry: function() {},
  BoxGeometry: function() {},
  CylinderGeometry: function() {},
  SphereGeometry: function() {},
  ConeGeometry: function() {},
  RingGeometry: function() {},
  BufferGeometry: class {
    constructor() { this.attributes = {}; }
    setAttribute(k, v) { this.attributes[k] = v; }
    setFromPoints() { return this; }
  },
  BufferAttribute: class {
    constructor(arr) { this.array = arr; this.needsUpdate = false; }
  },
  CatmullRomCurve3: function() {},
  TubeGeometry: function() {},
  MeshStandardMaterial: Material,
  MeshBasicMaterial: Material,
  PointsMaterial: Material,
  LineBasicMaterial: Material,
  GridHelper: Object3D,
  DoubleSide: 2,
  PCFSoftShadowMap: 2,
  ACESFilmicToneMapping: 4,
  sRGBEncoding: 3001,
  GLTFLoader: class {
    load(url, onLoad) {
      onLoad({ scene: mockVillaRoot });
    }
  },
};

const sandbox = {
  THREE,
  window: {
    THREE,
    devicePixelRatio: 1,
    innerWidth: 1280,
    addEventListener() {},
  },
  document: {
    hidden: false,
    getElementById(id) {
      if (id === "canvasBox") return canvasContainer;
      if (id === "labelsBox") return labelsContainer;
      return null;
    },
    createElement(tag) { return makeMockEl(tag); },
    querySelector() { return null; },
  },
  navigator: { webdriver: false, userAgent: "NodeVM" },
  requestAnimationFrame(cb) { rafQueue.push(cb); },
  console,
  Math,
  Number,
  Boolean,
  String,
  Array,
  Object,
  Set,
  Promise,
  Float32Array,
  parseInt,
};
sandbox.window.document = sandbox.document;
vm.createContext(sandbox);
vm.runInContext(code, sandbox);

const sh = sandbox.window.SmartHome3D;
sh.init("canvasBox", "labelsBox", () => {});

let simTime = 0;
function stepFrames(count) {
  for (let i = 0; i < count; i++) {
    const cb = rafQueue.shift();
    if (!cb) break;
    simTime += 500;
    cb(simTime);
  }
}

stepFrames(4);
const initial = sh.getDebugState();

// Open door + turn ON both lights
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

// Close door + turn OFF both lights
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
const closedPivotRad = mockVillaRoot.getObjectByName("door_pivot").rotation.y;
const closedHornRad = mockVillaRoot.getObjectByName("sg90_horn_pivot").rotation.y;

const domModuleIds = labelsContainer.children
  .map((el) => el.getAttribute("data-module-id"))
  .filter(Boolean);

process.stdout.write(JSON.stringify({
  hasGetDebugState: typeof sh.getDebugState === "function",
  expectedNodesCount: expectedNodes.length,
  initial,
  opened,
  closed,
  openPivotRad,
  openHornRad,
  closedPivotRad,
  closedHornRad,
  domModuleIds,
}));
"""
        proc = subprocess.run(
            ["node", "-e", node_script, str(REPO_ROOT)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        assert proc.returncode == 0, f"Node VM harness failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        data = json.loads(proc.stdout)

        assert data["hasGetDebugState"] is True
        scene_spec = _load_json("hardware/blender/SCENE_SPEC.json")
        expected_nodes = set(scene_spec["contract_nodes"].keys())
        bound_nodes = set(data["initial"]["boundGlbNodes"])
        assert len(expected_nodes) == 20
        assert expected_nodes <= bound_nodes, f"Unbound GLB nodes: {sorted(expected_nodes - bound_nodes)}"
        for required_node in ("SG90_DoorServo", "sg90_horn_pivot", "psu_5v_dc_jack", "soil_lm393_board"):
            assert required_node in bound_nodes

        # Verify all 14 modules + nodemcu + hub_pcb have data-module-id pins created in DOM
        expected_module_ids = {m["module_id"] for m in (*AUTHORITATIVE_14_MODULES, *AUTHORITATIVE_CORE_BOARDS)}
        dom_module_ids = set(data["domModuleIds"])
        assert expected_module_ids <= dom_module_ids, (
            f"Missing DOM data-module-id pins: {sorted(expected_module_ids - dom_module_ids)}"
        )

        # Verify synchronized +90 deg open & 0 deg close for BOTH doorPivot & servoHornPivot
        opened = data["opened"]
        assert opened["doorOpen"] is True
        assert opened["doorAngleDeg"] == pytest.approx(90.0, abs=0.1)
        assert opened["servoHornAngleDeg"] == pytest.approx(90.0, abs=0.1)
        assert abs(opened["doorAngleDeg"] - opened["servoHornAngleDeg"]) < 1e-3
        assert data["openPivotRad"] == pytest.approx(math.pi / 2.0, abs=0.005)
        assert data["openHornRad"] == pytest.approx(math.pi / 2.0, abs=0.005)

        closed = data["closed"]
        assert closed["doorOpen"] is False
        assert closed["doorAngleDeg"] == pytest.approx(0.0, abs=0.1)
        assert closed["servoHornAngleDeg"] == pytest.approx(0.0, abs=0.1)
        assert abs(closed["doorAngleDeg"] - closed["servoHornAngleDeg"]) < 1e-3
        assert data["closedPivotRad"] == pytest.approx(0.0, abs=0.005)
        assert data["closedHornRad"] == pytest.approx(0.0, abs=0.005)

        # Verify living & bedroom LED emissive + PointLight ON (> 0) and OFF (== 0)
        assert opened["livingLightOn"] is True
        assert opened["livingLedEmissive"] > 0
        assert opened["livingPointLightIntensity"] > 0
        assert opened["bedroomLightOn"] is True
        assert opened["bedroomLedEmissive"] > 0
        assert opened["bedroomPointLightIntensity"] > 0

        assert closed["livingLightOn"] is False
        assert closed["livingLedEmissive"] == 0
        assert closed["livingPointLightIntensity"] == 0
        assert closed["bedroomLightOn"] is False
        assert closed["bedroomLedEmissive"] == 0
        assert closed["bedroomPointLightIntensity"] == 0


class TestKiCadErcDrcAndOnboardPassives:
    def test_kicad_pcb_sch_have_c1_c9_d1_d2_and_zero_erc_drc_errors(self) -> None:
        kicad_dir = REPO_ROOT / "hardware/kicad/smarthome_hub"
        pcb_path = kicad_dir / "smarthome_hub.kicad_pcb"
        sch_path = kicad_dir / "smarthome_hub.kicad_sch"
        assert pcb_path.exists() and sch_path.exists()

        pcb_text = pcb_path.read_text(encoding="utf-8")
        pcb_fps = re.findall(
            r'\(footprint\s+"([^"]+)".*?\(property\s+"Reference"\s+"([^"]+)"',
            pcb_text,
            re.DOTALL,
        )
        assert len(pcb_fps) == 51, f"Expected 51 footprints in PCB, got {len(pcb_fps)}"
        pcb_refs = {ref for _, ref in pcb_fps}

        sch_text = sch_path.read_text(encoding="utf-8")
        sch_refs = set(re.findall(r'\(property\s+"Reference"\s+"([^"]+)"', sch_text))

        for ref in (*REQUIRED_CAPS, *REQUIRED_DIODES):
            assert ref in pcb_refs, f"{ref} missing from smarthome_hub.kicad_pcb"
            assert ref in sch_refs, f"{ref} missing from smarthome_hub.kicad_sch"

        for rel_erc in (
            "hardware/kicad/smarthome_hub/reports/erc.json",
            "docs/phan_cung/diy_pcb/erc_report.json",
        ):
            erc = _load_json(rel_erc)
            sheets = erc.get("sheets") or []
            assert len(sheets) >= 1, f"No sheets in {rel_erc}"
            violations = [v for s in sheets for v in (s.get("violations") or [])]
            assert len(violations) == 0, f"ERC violations in {rel_erc}: {violations}"

        for rel_drc in (
            "hardware/kicad/smarthome_hub/reports/drc.json",
            "docs/phan_cung/diy_pcb/drc_report.json",
        ):
            drc = _load_json(rel_drc)
            assert len(drc.get("violations") or []) == 0, f"DRC violations in {rel_drc}: {drc.get('violations')}"
            assert len(drc.get("unconnected_items") or []) == 0, f"DRC unconnected in {rel_drc}"
            assert len(drc.get("schematic_parity") or []) == 0, f"DRC parity errors in {rel_drc}"
