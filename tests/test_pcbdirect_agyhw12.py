"""Regression & verification tests for agyhw12_20261127 (R6 — PCB-Direct, Zero Breadboard).

Verifies:
1. No breadboard in default guide, web UI, 3D scene, wiring contract, or docs.
2. All 40 wires (W01..W40) have 0 < length_cm <= 30.0, 15 <= slack_pct <= 20,
   real header pins matching HUB_CONNECTOR_MAP, and non-empty waypoints_threejs.
3. On-board C8 (100nF), C9 (100uF 16V), C1..C7, D1..D2 in KiCad PCB (51 footprints),
   schematic, BOM, pos file, 0 ERC errors/warnings, 0 DRC violations/unconnected/parity,
   and renders copied into docs/phan_cung/diy_pcb/.
4. Unified dimension SSOT parity: NodeMCU v2 Amica (48.26x25.40 mm, 22.86 mm row spacing)
   vs rejected v3 LoLin (58x31 mm), DIMENSIONS_AUDIT.md + live audit_component_dimensions.py
   passing 26/26 with 0 FAIL.
5. 3D-print v2 constraints (verification_report.json & build_meta/assembly_report.json):
   180x200x250 bed, 17/17 plates fit, 0 supports, 0 fastener holes, 0 forbidden instructions,
   0 BRep collisions, 7/7 R3 clearances, total_filament_g <= 1035.87.
6. Blender & Web 3D GLB (web/models/smarthome_villa.glb < 10 MB, SCENE_SPEC.json 40 wires,
   breadboard_used is False).
7. Guide step navigation, wire table search/sort, full Vietnamese group & channel parity,
   mobile >= 44px touch targets in wokwi.css, and working USB firmware guide link.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import pathlib
import re
from typing import Any

import pytest

from hardware.component_dimensions_ssot import COMPONENT_DIM_MAP, COMPONENT_DIMENSIONS
from hardware.wiring_contract import (
    HUB_CONNECTOR_MAP,
    PROTECTION_COMPONENTS,
    WIRING_TABLE,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

EXPECTED_WIRE_IDS = tuple(f"W{i:02d}" for i in range(1, 41))
OFFBOARD_ALLOWED_PINS: dict[str, set[str]] = {
    "PAM8403": {"L_OUT+", "L_OUT-"},
    "LM393": {"P1", "P2"},
}
REQUIRED_CAPS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9")
REQUIRED_DIODES = ("D1", "D2")

BREADBOARD_NEGATION_OR_LEGACY_RE = re.compile(
    r"(legacy|không\s+(?:dùng\s+)?(?:bảng\s+cắm\s+)?breadboard|zero\s+(?:white\s+)?breadboard|"
    r"no\s+(?:white\s+)?breadboard|không\s+dùng|removed|0\s+breadboard|"
    r"chính\s+sách\s+không\s+dùng\s+breadboard|thay\s+thế\s+hoàn\s+toàn)",
    re.IGNORECASE,
)


def _load_json(rel_path: str) -> dict[str, Any]:
    path = REPO_ROOT / rel_path
    assert path.exists(), f"Missing JSON artifact: {rel_path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_kicad_pcb_footprints(pcb_path: pathlib.Path) -> list[dict[str, str]]:
    text = pcb_path.read_text(encoding="utf-8")
    matches = re.findall(
        r'\(footprint\s+"([^"]+)".*?\(property\s+"Reference"\s+"([^"]+)".*?\(property\s+"Value"\s+"([^"]+)"',
        text,
        re.DOTALL,
    )
    return [{"footprint": fp, "ref": ref, "value": val} for fp, ref, val in matches]


class TestNoBreadboardInDefaultGuideAndData:
    def test_wiring_contract_json_defaults_to_pcb_direct_without_breadboard(self) -> None:
        contract = _load_json("web/data/wiring_contract.json")
        assert contract.get("default_view") == "pcb_direct"
        assert contract.get("breadboard_used") is False

    def test_wiring_contract_py_c8_c9_onboard_and_zero_active_breadboard(self) -> None:
        prot_by_ref = {p.ref: p for p in PROTECTION_COMPONENTS}
        for ref in (*REQUIRED_CAPS, *REQUIRED_DIODES):
            assert ref in prot_by_ref, f"Missing {ref} in PROTECTION_COMPONENTS"
            assert prot_by_ref[ref].pcb_status == "onboard_pcb", (
                f"{ref} must have pcb_status='onboard_pcb', got {prot_by_ref[ref].pcb_status!r}"
            )
        assert prot_by_ref["C8"].pcb_status == "onboard_pcb"
        assert prot_by_ref["C9"].pcb_status == "onboard_pcb"

        for wire in WIRING_TABLE:
            combined = " ".join(
                (wire.group, wire.hub_ref, wire.hub_label, wire.module_id, wire.module_name, wire.notes)
            )
            assert "breadboard" not in combined.lower(), f"Active breadboard ref in wire {wire.wire_id}"

        for comp in PROTECTION_COMPONENTS:
            combined = " ".join((comp.placement_pins, comp.role_vi, comp.datasheet_ref))
            assert "breadboard" not in combined.lower(), f"Active breadboard ref in protection {comp.ref}"

        src_lines = (REPO_ROOT / "hardware/wiring_contract.py").read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(src_lines, 1):
            if "breadboard" in line.lower():
                assert BREADBOARD_NEGATION_OR_LEGACY_RE.search(line), (
                    f"Active breadboard reference at hardware/wiring_contract.py:{lineno}: {line.strip()}"
                )

    def test_wokwi_html_and_js_default_to_pcb2d_with_workbench_hidden(self) -> None:
        html = (REPO_ROOT / "web/wokwi.html").read_text(encoding="utf-8")
        m_wb = re.search(r'<div\b[^>]*\bid="workbenchScroll"[^>]*>', html)
        assert m_wb is not None, "#workbenchScroll not found in web/wokwi.html"
        assert re.search(r"\bhidden\b", m_wb.group(0)), "#workbenchScroll must have hidden attribute by default"

        m_pcb = re.search(r'<div\b[^>]*\bid="pcb2dScroll"[^>]*>', html)
        assert m_pcb is not None, "#pcb2dScroll not found in web/wokwi.html"
        assert not re.search(r"\bhidden\b", m_pcb.group(0)), "#pcb2dScroll must be visible by default"

        js = (REPO_ROOT / "web/js/wokwi.js").read_text(encoding="utf-8")
        assert re.search(r"let\s+wokwiActiveDiagramMode\s*=\s*['\"]pcb2d['\"]", js), (
            "web/js/wokwi.js must initialize wokwiActiveDiagramMode to 'pcb2d'"
        )

    def test_house3d_and_scene_spec_disable_breadboard(self) -> None:
        house3d = (REPO_ROOT / "web/house3d.js").read_text(encoding="utf-8")
        assert re.search(r"breadboardUsed\s*:\s*false\b", house3d), (
            "web/house3d.js must expose breadboardUsed: false"
        )

        spec = _load_json("hardware/blender/SCENE_SPEC.json")
        assert spec.get("breadboard_used") is False
        assert "breadboard" in (spec.get("removed_devices") or [])

    @pytest.mark.parametrize(
        "rel_path",
        [
            "docs/phan_cung/WIRING_TABLE.md",
            "docs/phan_cung/DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md",
            "docs/HARDWARE_BUILD_GUIDE.md",
            "README.md",
        ],
    )
    def test_docs_do_not_instruct_white_breadboard(self, rel_path: str) -> None:
        path = REPO_ROOT / rel_path
        assert path.exists(), f"Missing doc: {rel_path}"
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, 1):
            if re.search(r"breadboard|bo\s+mạch\s+cắm|bo\s+cắm", line, re.IGNORECASE):
                assert BREADBOARD_NEGATION_OR_LEGACY_RE.search(line), (
                    f"{rel_path}:{lineno} mentions breadboard without negation/legacy label: {line.strip()}"
                )


class TestFortyWiresLengthsAndHeaderPins:
    def test_all_three_wire_sources_have_exact_40_wires_within_30cm_and_valid_pins(self) -> None:
        wl = _load_json("hardware/wire_lengths.json")
        wc = _load_json("web/data/wiring_contract.json")
        csv_path = REPO_ROOT / "docs/phan_cung/wire_lengths.csv"
        assert csv_path.exists(), "Missing docs/phan_cung/wire_lengths.csv"

        wl_wires = wl.get("wires") or []
        wc_wires = wc.get("wires") or []
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            csv_rows = list(csv.DictReader(fh))

        assert len(wl_wires) == 40
        assert len(wc_wires) == 40
        assert len(csv_rows) == 40

        assert tuple(w["wire_id"] for w in wl_wires) == EXPECTED_WIRE_IDS
        assert tuple(w["wire_id"] for w in wc_wires) == EXPECTED_WIRE_IDS
        assert tuple(r["Wire_ID"] for r in csv_rows) == EXPECTED_WIRE_IDS

        summary_slack_pct = round((float(wl["slack_factor"]) - 1.0) * 100.0, 2)
        assert 15.0 <= summary_slack_pct <= 20.0, f"Unexpected slack_factor: {wl['slack_factor']}"
        wc_summary = wc["wire_lengths_summary"]
        wc_slack_pct = round((float(wc_summary["slack_factor"]) - 1.0) * 100.0, 2)
        assert 15.0 <= wc_slack_pct <= 20.0
        assert wc_summary["all_within_30cm"] is True
        assert wl["all_within_30cm"] is True

        for w_wl, w_wc, r_csv in zip(wl_wires, wc_wires, csv_rows):
            wid = w_wl["wire_id"]
            len_wl = float(w_wl["length_cm"])
            len_wc = float(w_wc["length_cm"])
            len_csv = float(r_csv["Length_Incl_18pct_Slack_cm"])

            assert 0.0 < len_wl <= 30.0, f"{wid} length_cm out of range in wire_lengths.json: {len_wl}"
            assert 0.0 < len_wc <= 30.0, f"{wid} length_cm out of range in wiring_contract.json: {len_wc}"
            assert 0.0 < len_csv <= 30.0, f"{wid} length_cm out of range in wire_lengths.csv: {len_csv}"
            assert abs(len_wl - len_wc) <= 0.02, f"{wid} length mismatch json vs contract: {len_wl} != {len_wc}"
            assert abs(len_wl - len_csv) <= 0.02, f"{wid} length mismatch json vs csv: {len_wl} != {len_csv}"

            assert w_wl["within_30cm"] is True, f"{wid} within_30cm must be True in wire_lengths.json"
            assert w_wc["within_30cm"] is True, f"{wid} within_30cm must be True in wiring_contract.json"
            assert r_csv["Within_30cm"].strip() == "PASS", f"{wid} CSV Within_30cm must be PASS"

            slack_pct = float(w_wl["slack_pct"])
            assert 15.0 <= slack_pct <= 20.0, f"{wid} slack_pct out of [15, 20]: {slack_pct}"

            for src_name, item in (("wire_lengths.json", w_wl), ("wiring_contract.json", w_wc)):
                hub_ref = item["hub_ref"]
                hub_pin = str(item["hub_pin"])
                if hub_ref in HUB_CONNECTOR_MAP:
                    valid_pins = {p[0] for p in HUB_CONNECTOR_MAP[hub_ref].pins}
                    assert hub_pin in valid_pins, (
                        f"{wid} ({src_name}) invalid pin {hub_ref}.{hub_pin}; expected one of {valid_pins}"
                    )
                else:
                    assert hub_ref in OFFBOARD_ALLOWED_PINS, f"{wid} ({src_name}) unknown hub_ref {hub_ref!r}"
                    assert hub_pin in OFFBOARD_ALLOWED_PINS[hub_ref], (
                        f"{wid} ({src_name}) invalid off-board pin {hub_ref}.{hub_pin}"
                    )

                wp3 = item.get("waypoints_threejs") or []
                assert len(wp3) >= 2, f"{wid} ({src_name}) must have non-empty waypoints_threejs"
                for pt in wp3:
                    assert len(pt) == 3, f"{wid} ({src_name}) malformed 3D waypoint {pt}"

            expected_csv_pin = f"{w_wl['hub_ref']}.{w_wl['hub_pin']}"
            assert r_csv["PCB_Header_Pin"].strip() == expected_csv_pin, (
                f"{wid} CSV PCB_Header_Pin mismatch: {r_csv['PCB_Header_Pin']} != {expected_csv_pin}"
            )


class TestKiCadOnBoardPassivesAndManufacturing:
    def test_kicad_pcb_schematic_bom_pos_have_c1_c9_d1_d2_and_51_footprints(self) -> None:
        kicad_dir = REPO_ROOT / "hardware/kicad/smarthome_hub"
        pcb_path = kicad_dir / "smarthome_hub.kicad_pcb"
        sch_path = kicad_dir / "smarthome_hub.kicad_sch"
        bom_path = kicad_dir / "bom.csv"
        pos_path = kicad_dir / "smarthome_hub-all-pos.csv"

        for p in (pcb_path, sch_path, bom_path, pos_path):
            assert p.exists(), f"Missing KiCad artifact: {p}"

        fps = _parse_kicad_pcb_footprints(pcb_path)
        assert len(fps) == 51, f"Expected 51 footprints in smarthome_hub.kicad_pcb, got {len(fps)}"
        pcb_by_ref = {fp["ref"]: fp["value"] for fp in fps}

        with bom_path.open("r", encoding="utf-8", newline="") as fh:
            bom_by_ref = {row["Refs"].strip(): row["Value"].strip() for row in csv.DictReader(fh)}

        with pos_path.open("r", encoding="utf-8", newline="") as fh:
            pos_by_ref = {row["Ref"].strip(): row["Val"].strip() for row in csv.DictReader(fh)}

        sch_text = sch_path.read_text(encoding="utf-8")
        sch_refs = set(re.findall(r'\(property\s+"Reference"\s+"([^"]+)"', sch_text))

        for ref in (*REQUIRED_CAPS, *REQUIRED_DIODES):
            assert ref in pcb_by_ref, f"{ref} missing from KiCad PCB"
            assert ref in sch_refs, f"{ref} missing from KiCad schematic"
            assert ref in bom_by_ref, f"{ref} missing from bom.csv"
            assert ref in pos_by_ref, f"{ref} missing from smarthome_hub-all-pos.csv"

        assert pcb_by_ref["C8"] == "100nF"
        assert bom_by_ref["C8"] == "100nF"
        assert pos_by_ref["C8"] == "100nF"

        assert pcb_by_ref["C9"] == "100uF 16V"
        assert bom_by_ref["C9"] == "100uF 16V"
        assert pos_by_ref["C9"] == "100uF 16V"

        for dref in REQUIRED_DIODES:
            assert pcb_by_ref[dref] == "1N4007"
            assert bom_by_ref[dref] == "1N4007"
            assert pos_by_ref[dref] == "1N4007"

    def test_erc_and_drc_are_clean_and_renders_copied_to_docs(self) -> None:
        erc = _load_json("hardware/kicad/smarthome_hub/reports/erc.json")
        sheets = erc.get("sheets") or []
        assert len(sheets) >= 1, "ERC report must contain at least one sheet"
        erc_violations = [v for s in sheets for v in (s.get("violations") or [])]
        assert len(erc_violations) == 0, f"ERC has violations: {erc_violations}"

        drc = _load_json("hardware/kicad/smarthome_hub/reports/drc.json")
        assert len(drc.get("violations") or []) == 0, f"DRC violations: {drc.get('violations')}"
        assert len(drc.get("unconnected_items") or []) == 0, f"DRC unconnected: {drc.get('unconnected_items')}"
        assert len(drc.get("schematic_parity") or []) == 0, f"DRC parity errors: {drc.get('schematic_parity')}"

        diy_dir = REPO_ROOT / "docs/phan_cung/diy_pcb"
        required_exports = (
            "kicad_2d_copper_layout.png",
            "kicad_3d_iso.png",
            "kicad_3d_top.png",
            "kicad_drc_result.png",
            "smarthome_hub-all-pos.csv",
            "erc_report.json",
            "drc_report.json",
        )
        for name in required_exports:
            fp = diy_dir / name
            assert fp.exists() and fp.stat().st_size > 0, f"Missing or empty PCB export in docs/phan_cung/diy_pcb/{name}"


class TestUnifiedDimensionSsotParity:
    def test_nodemcu_v2_amica_locked_and_v3_lolin_rejected(self) -> None:
        assert len(COMPONENT_DIMENSIONS) == 26
        nodemcu = COMPONENT_DIM_MAP["nodemcu"]
        assert nodemcu.dims_mm[:2] == (48.26, 25.4)
        assert "v2 Amica" in nodemcu.label
        assert "22.86 mm" in nodemcu.datasheet_summary

        ssot_src = (REPO_ROOT / "hardware/component_dimensions_ssot.py").read_text(encoding="utf-8")
        assert "48.26 x 25.40" in ssot_src
        assert "22.86 mm" in ssot_src
        assert "v3 LoLin (58 x 31 mm" in ssot_src

    def test_dimensions_audit_md_and_live_auditor_pass_26_of_26_with_zero_fail(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        md_text = (REPO_ROOT / "docs/phan_cung/DIMENSIONS_AUDIT.md").read_text(encoding="utf-8")
        assert "Total SSOT components audited:** `26`" in md_text
        assert "`FAIL`: **0**" in md_text
        assert "v2 Amica" in md_text and "48.26 × 25.40" in md_text and "22.86 mm" in md_text
        assert "v3 LoLin" in md_text and "58.00 × 31.00" in md_text

        script_path = REPO_ROOT / "scripts/audit_component_dimensions.py"
        assert script_path.exists()
        spec = importlib.util.spec_from_file_location("audit_component_dimensions_mod", script_path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        monkeypatch.setattr(mod, "OUT_MD_PATH", tmp_path / "DIMENSIONS_AUDIT.md")
        receipt = mod.run_audit(tmp_path / "dimensions_audit.json")
        summary = receipt["summary"]
        assert summary["overall_pass"] is True, f"Audit failed: {summary.get('mismatches')}"
        assert summary["total_components"] == 26
        assert summary["fail_count"] == 0
        assert receipt["kicad_pcb"]["u1_u2_row_spacing_mm"] == pytest.approx(22.86, abs=0.05)


class TestPrint3DV2Constraints:
    def test_verification_and_assembly_reports_pass_all_constraints(self) -> None:
        vrep = _load_json("hardware/in 3 d/verification_report.json")
        arep = _load_json("hardware/in 3 d/build_meta/assembly_report.json")

        assert vrep["all_passed"] is True
        assert [float(x) for x in vrep["bed_mm"]] == [180.0, 200.0, 250.0]

        totals = vrep["totals"]
        assert totals["total_plates"] == 17
        assert totals["plates_passed"] == 17
        assert vrep["plates_verified"] == 17
        assert totals["any_plate_needs_supports"] is False
        assert vrep.get("needs_slicer_supports") is False
        # agyhw12 baseline was 1035.87 g; agyhw13 added SUP10B, SUP16, SUP17 (2x), SUP18 & P07 end-stops (+8.99 g -> 1044.86 g)
        assert float(totals["total_filament_g"]) <= 1060.0

        audit = vrep["screw_glue_audit"]
        assert audit["passed"] is True
        assert audit["geometry_fastener_hole_count"] == 0
        assert audit["readme_forbidden_instruction_count"] == 0

        for report_name, asm in (("verification_report.json", vrep["assembly"]), ("assembly_report.json", arep)):
            assert asm["assembly_passed"] is True, f"{report_name} assembly_passed is not True"
            assert len(asm.get("reconstruction_failures") or []) == 0
            assert len(asm.get("panel_collisions") or []) == 0
            assert len(asm.get("support_collisions") or []) == 0
            assert len(asm.get("furniture_collisions") or []) == 0
            assert len(asm.get("hardware_collisions") or []) == 0

            r3 = asm["r3_clearances"]
            assert r3["all_passed"] is True
            assert r3["passed_count"] == 7
            assert r3["total_count"] == 7
            checks = r3["checks"]
            assert len(checks) == 7
            for check_name, check_data in checks.items():
                assert check_data["passed"] is True, f"{report_name} R3 clearance failed: {check_name}"


class TestBlenderAndWeb3DGlb:
    def test_glb_exists_under_10mb_and_scene_spec_matches(self) -> None:
        glb_path = REPO_ROOT / "web/models/smarthome_villa.glb"
        assert glb_path.exists(), "Missing web/models/smarthome_villa.glb"
        size_bytes = glb_path.stat().st_size
        assert 0 < size_bytes < 10 * 1024 * 1024, f"GLB size out of bounds: {size_bytes} bytes"

        spec = _load_json("hardware/blender/SCENE_SPEC.json")
        assert spec["routed_wires_count"] == 40
        assert spec["breadboard_used"] is False


class TestGuideStepNavAndWireTableParity:
    def test_step_controls_wire_table_vietnamese_maps_mobile_css_and_usb_link(self) -> None:
        html = (REPO_ROOT / "web/wokwi.html").read_text(encoding="utf-8")
        js = (REPO_ROOT / "web/js/wokwi.js").read_text(encoding="utf-8")
        css = (REPO_ROOT / "web/css/wokwi.css").read_text(encoding="utf-8")
        contract = _load_json("web/data/wiring_contract.json")

        required_ids = (
            "btnStepMode",
            "btnStepPrev",
            "btnStepNext",
            "btnStepAll",
            "stepModeCounter",
            "pcbStepDetailCard",
            "wireSearchInput",
            "wireGroupFilter",
        )
        for el_id in required_ids:
            assert f'id="{el_id}"' in html, f"Missing #{el_id} in web/wokwi.html"
            assert el_id in js, f"Missing #{el_id} binding in web/js/wokwi.js"

        sort_btns = re.findall(r'class="[^"]*\bwire-sort-btn\b[^"]*"', html)
        assert len(sort_btns) >= 6, f"Expected >= 6 .wire-sort-btn controls, found {len(sort_btns)}"
        assert ".wire-sort-btn" in js

        m_group_map = re.search(r"const\s+GROUP_VI_MAP\s*=\s*\{(.*?)\};", js, re.DOTALL)
        assert m_group_map is not None, "GROUP_VI_MAP not found in web/js/wokwi.js"
        group_map_keys = set(re.findall(r"'([^']+)'\s*:", m_group_map.group(1)))
        contract_groups = {w["group"] for w in contract["wires"]}
        missing_groups = sorted(contract_groups - group_map_keys)
        assert not missing_groups, f"GROUP_VI_MAP missing Vietnamese translations for groups: {missing_groups}"

        m_chan_map = re.search(r"const\s+ROUTE_CHANNEL_VI_MAP\s*=\s*\{(.*?)\};", js, re.DOTALL)
        assert m_chan_map is not None, "ROUTE_CHANNEL_VI_MAP not found in web/js/wokwi.js"
        chan_map_keys = set(re.findall(r"'([^']+)'\s*:", m_chan_map.group(1)))
        contract_channels = {w["route_channel"] for w in contract["wires"] if w.get("route_channel")}
        missing_channels = sorted(contract_channels - chan_map_keys)
        assert not missing_channels, f"ROUTE_CHANNEL_VI_MAP missing Vietnamese translations for channels: {missing_channels}"

        assert re.search(r"min-height\s*:\s*44px", css), "web/css/wokwi.css must enforce >= 44px mobile min-height"
        assert re.search(r"min-width\s*:\s*44px", css), "web/css/wokwi.css must enforce >= 44px mobile min-width"

        usb_href = "/docs/phan_cung/HUONG_DAN_NAP_FIRMWARE_USB.md"
        assert f'href="{usb_href}"' in html, f"Missing {usb_href} link in web/wokwi.html"
        usb_doc = REPO_ROOT / "docs/phan_cung/HUONG_DAN_NAP_FIRMWARE_USB.md"
        assert usb_doc.exists() and usb_doc.stat().st_size > 0, "USB firmware guide markdown file missing or empty"
