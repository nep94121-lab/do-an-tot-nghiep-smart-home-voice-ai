"""Contract parity tests between `hardware/wiring_contract.py` (SSOT) and web wiring data."""
from __future__ import annotations

import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hardware.wiring_contract import (
    FIRMWARE_PIN_CONTRACT,
    HUB_CONNECTORS,
    WIRE_COLORS,
    WIRING_TABLE,
)
from scripts.export_wiring_contract_web import (
    DEFAULT_OUTPUT,
    build_web_contract_payload,
    serialize_payload,
)

SVG_2D_PATH = REPO_ROOT / "docs" / "phan_cung" / "wiring_diagram_2d.svg"


def test_web_wiring_contract_json_matches_ssot_exactly() -> None:
    """Fail immediately if `web/data/wiring_contract.json` drifts from `hardware/wiring_contract.py`."""
    assert DEFAULT_OUTPUT.exists(), f"Missing exported web contract JSON: {DEFAULT_OUTPUT}"
    expected_payload = build_web_contract_payload()
    expected_text = serialize_payload(expected_payload)
    actual_text = DEFAULT_OUTPUT.read_text(encoding="utf-8")
    assert actual_text == expected_text, (
        "web/data/wiring_contract.json drifted from hardware/wiring_contract.py. "
        "Re-run: python scripts/export_wiring_contract_web.py"
    )

    actual_payload = json.loads(actual_text)
    assert actual_payload["source"] == "hardware/wiring_contract.py"
    assert actual_payload["counts"]["wires"] == len(WIRING_TABLE)
    assert actual_payload["counts"]["connectors"] == len(HUB_CONNECTORS)
    assert actual_payload["counts"]["firmware_pins"] == len(FIRMWARE_PIN_CONTRACT)


def test_every_ssot_wire_and_pin_preserved_in_web_json() -> None:
    """Every wire in WIRING_TABLE appears in order with matching endpoints, colors, and nets."""
    data = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
    wires = data["wires"]
    assert len(wires) == len(WIRING_TABLE)

    for idx, (entry, exported) in enumerate(zip(WIRING_TABLE, wires), start=1):
        assert exported["step_number"] == idx
        assert exported["wire_id"] == entry.wire_id
        assert exported["hub_ref"] == entry.hub_ref
        assert exported["hub_pin"] == entry.hub_pin
        assert exported["hub_label"] == entry.hub_label
        assert exported["module_id"] == entry.module_id
        assert exported["module_name"] == entry.module_name
        assert exported["module_pin"] == entry.module_pin
        assert exported["nodemcu_pin"] == entry.nodemcu_pin
        assert exported["gpio"] == entry.gpio
        assert exported["net"] == entry.net
        assert exported["color"] == entry.color
        assert exported["color_hex"] == WIRE_COLORS[entry.color]["hex"]
        assert exported["wire_type"] == entry.wire_type
        assert exported["fw_ref"] == entry.fw_ref
        assert exported["notes"] == entry.notes
        assert exported["color_vi"].strip()
        assert exported["module_label_vi"].strip()
        assert exported["power_gnd_note_vi"].strip()
        assert exported["instruction_vi"].strip()

    expected_modules = []
    for entry in WIRING_TABLE:
        if entry.module_id not in expected_modules:
            expected_modules.append(entry.module_id)
    assert [m["module_id"] for m in data["modules"]] == expected_modules


def test_web_contract_has_zero_legacy_removed_devices() -> None:
    """Verify no retired legacy devices (fan, AC, IR) appear in exported web JSON."""
    raw = DEFAULT_OUTPUT.read_text(encoding="utf-8")
    forbidden_re = re.compile(r"\b(fan|air_?cond|ac_relay|vs1838b?|ir_learn|ir_rx|ir_tx)\b", re.IGNORECASE)
    assert not forbidden_re.search(raw), "Legacy removed hardware token found in web/data/wiring_contract.json"


def test_2d_pcb_svg_tags_every_contract_wire_and_endpoints() -> None:
    """Every wire in hardware/wiring_contract.py is tagged for interactive highlight/filter in 2D SVG."""
    assert SVG_2D_PATH.exists(), f"Missing 2D SVG diagram: {SVG_2D_PATH}"
    svg_text = SVG_2D_PATH.read_text(encoding="utf-8")

    for entry in WIRING_TABLE:
        wire_marker = f'class="pcb-wire" data-wire-id="{entry.wire_id}" data-module-id="{entry.module_id}"'
        assert wire_marker in svg_text, f"2D SVG missing wire tag for {entry.wire_id} ({entry.module_id})"
        pin_count = svg_text.count(f'class="pcb-pin" data-wire-id="{entry.wire_id}"')
        assert pin_count == 2, f"Expected 2 endpoint pins for {entry.wire_id} in 2D SVG, found {pin_count}"
