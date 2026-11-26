"""UI & integration tests for the SSOT Wiring Guide + Wire Toggle across /wokwi and /."""
from __future__ import annotations

import json
import pathlib
import re
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hardware.wiring_contract import WIRING_TABLE

WEB_DIR = REPO_ROOT / "web"
WOKWI_HTML = WEB_DIR / "wokwi.html"
WOKWI_JS = WEB_DIR / "js" / "wokwi.js"
INDEX_HTML = WEB_DIR / "index.html"
APP_JS = WEB_DIR / "js" / "app.js"
HOUSE3D_JS = WEB_DIR / "house3d.js"
WIRING_GUIDE_JS = WEB_DIR / "js" / "wiring_guide.js"
CONTRACT_JSON = WEB_DIR / "data" / "wiring_contract.json"


def test_wokwi_and_dashboard_mount_shared_wiring_guide() -> None:
    """Both /wokwi and / dashboard include the shared wiring guide assets and mount points."""
    wokwi_html = WOKWI_HTML.read_text(encoding="utf-8")
    index_html = INDEX_HTML.read_text(encoding="utf-8")

    for html_text, label in ((wokwi_html, "web/wokwi.html"), (index_html, "web/index.html")):
        assert "/static/css/wiring_guide.css" in html_text, f"{label} missing wiring_guide.css"
        assert "/static/js/wiring_guide.js" in html_text, f"{label} missing wiring_guide.js"

    assert 'id="wokwiWiringToolbar"' in wokwi_html
    assert 'id="wokwiWiringPanelMount"' in wokwi_html
    assert 'id="wokwiWireInspect"' in wokwi_html
    assert 'id="pcb2dSvgHost"' in wokwi_html

    assert 'id="dashWiringToolbar"' in index_html
    assert 'id="dashWiringPanelMount"' in index_html
    assert 'id="dashWireInspect"' in index_html


def test_no_hardcoded_guides_or_pinout_tables_in_web_ui() -> None:
    """Ensure hand-copied GUIDES array and static pinout rows were removed in favor of SSOT JSON."""
    wokwi_js = WOKWI_JS.read_text(encoding="utf-8")
    wokwi_html = WOKWI_HTML.read_text(encoding="utf-8")
    wg_js = WIRING_GUIDE_JS.read_text(encoding="utf-8")

    assert "const GUIDES =" not in wokwi_js, "Hardcoded GUIDES object still exists in web/js/wokwi.js"
    assert 'id="ssotPinoutTableBody"' in wokwi_html
    assert "/static/data/wiring_contract.json" in wg_js
    assert "smarthome_wiring_prefs_v1" in wg_js
    assert "Hướng dẫn nối dây" in wg_js
    assert "Ẩn dây nối" in wg_js and "Hiện dây nối" in wg_js
    assert "Trước" in wg_js and "Tiếp" in wg_js and "Đóng" in wg_js


def test_every_ssot_wire_id_is_referenced_on_wokwi_breadboard() -> None:
    """Every wire in hardware/wiring_contract.py maps to a tagged SVG wire path on /wokwi."""
    wokwi_js = WOKWI_JS.read_text(encoding="utf-8")
    missing = [w.wire_id for w in WIRING_TABLE if f"'{w.wire_id}'" not in wokwi_js]
    assert not missing, f"Wire IDs from wiring_contract.py missing in web/js/wokwi.js: {missing}"


def test_house3d_exposes_wire_visibility_filter_and_highlight_api() -> None:
    """3D dashboard view exposes wire visibility, module filter, step highlight, and click inspect."""
    house3d_js = HOUSE3D_JS.read_text(encoding="utf-8")
    app_js = APP_JS.read_text(encoding="utf-8")

    for fn_name in (
        "setWiresVisible",
        "applyWiringFilter",
        "highlightWiringStep",
        "setWireClickCallback",
        "getWiringDisplayState",
    ):
        assert fn_name in house3d_js, f"Missing {fn_name} in web/house3d.js"

    assert "dashWiringController" in app_js
    assert "SmartHomeWiringGuide.createController" in app_js


def test_wiring_contract_served_over_http_static_route() -> None:
    """FastAPI static route serves /static/data/wiring_contract.json identically to disk."""
    from fastapi.testclient import TestClient
    from backend.server import app

    expected = json.loads(CONTRACT_JSON.read_text(encoding="utf-8"))
    with TestClient(app) as client:
        resp = client.get("/static/data/wiring_contract.json")
        assert resp.status_code == 200
        served = resp.json()
        assert served["contract_sha256"] == expected["contract_sha256"]
        assert len(served["wires"]) == len(WIRING_TABLE)
