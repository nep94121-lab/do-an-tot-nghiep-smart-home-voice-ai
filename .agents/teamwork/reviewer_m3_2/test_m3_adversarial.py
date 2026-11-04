"""Adversarial stress-testing suite for Milestone 3 (Reviewer 2).
Tests edge cases, boundary conditions, integrity, and simulates DOM/JS behavior.
"""
import math
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(r"c:\Users\LENOVO\Desktop\đồ án tốt nghiệp")
HOUSE3D_PATH = ROOT / "simulator" / "static" / "house3d.js"
STYLE_PATH = ROOT / "simulator" / "static" / "css" / "style.css"
INDEX_PATH = ROOT / "simulator" / "static" / "index.html"
APP_PATH = ROOT / "simulator" / "static" / "js" / "app.js"

house3d_text = HOUSE3D_PATH.read_text(encoding="utf-8")
style_text = STYLE_PATH.read_text(encoding="utf-8")
index_text = INDEX_PATH.read_text(encoding="utf-8")
app_text = APP_PATH.read_text(encoding="utf-8")

failures = []

def assert_true(cond, msg):
    if not cond:
        failures.append(msg)

# 1. INTEGRITY VIOLATION CHECKS
suspicious_patterns = [
    r"pytest", r"test_challenger", r"mock_pass", r"skip_test", r"return true; // bypass"
]
for p in suspicious_patterns:
    if re.search(p, house3d_text, re.IGNORECASE):
        failures.append(f"INTEGRITY VIOLATION: Suspicious pattern '{p}' found in house3d.js")
    if re.search(p, app_text, re.IGNORECASE):
        failures.append(f"INTEGRITY VIOLATION: Suspicious pattern '{p}' found in app.js")

# 2. DRAG VS CLICK THRESHOLD BOUNDARY TESTING
# Math.hypot(dx, dy)
# Threshold is 6 for mouse, 10 for touch
assert_true("Math.hypot(e.clientX - mouseDownPos.x, e.clientY - mouseDownPos.y)" in house3d_text, "Mouse drag threshold calculation missing")
assert_true("dist <= 6" in house3d_text, "Mouse threshold <= 6 missing")
assert_true("Math.hypot(t.clientX - touchStartPos.x, t.clientY - touchStartPos.y)" in house3d_text, "Touch drag threshold calculation missing")
assert_true("dist <= 10" in house3d_text, "Touch threshold <= 10 missing")

# Boundary simulation:
# If mouse moves dx=4, dy=4 -> hypot = sqrt(32) = 5.6568 -> <= 6 -> CLICK
assert_true(math.hypot(4, 4) <= 6, "Simulation: 4,4 should be treated as click")
# If mouse moves dx=5, dy=4 -> hypot = sqrt(41) = 6.403 -> > 6 -> DRAG
assert_true(math.hypot(5, 4) > 6, "Simulation: 5,4 should be treated as drag")
# If mouse moves dx=0, dy=7 -> hypot = 7 -> > 6 -> DRAG
assert_true(math.hypot(0, 7) > 6, "Simulation: 0,7 should be treated as drag")

# 3. DOM ELEMENT PRESERVATION IN house3d.js
assert_true('container.innerHTML = ""' not in house3d_text, "CRITICAL: container.innerHTML still empties viewport")
assert_true("container.insertBefore(renderer.domElement, container.firstChild)" in house3d_text, "Missing container.insertBefore for canvas")
assert_true('id="house3dLabels"' in index_text, "index.html missing #house3dLabels")
assert_true('class="viewport-note"' in index_text, "index.html missing .viewport-note")
assert_true('id="lblCurrentCameraView"' in index_text, "index.html missing #lblCurrentCameraView")

# 4. CAMERA PRESET SYNC
expected_presets = ["overview", "living", "bedroom", "door", "garden", "board", "rotate"]
for preset in expected_presets:
    assert_true(f'data-cam="{preset}"' in index_text, f"Preset '{preset}' missing in index.html")
    assert_true(f'preset === "{preset}"' in house3d_text or f'"{preset}"' in house3d_text, f"Preset '{preset}' missing in house3d.js setCameraView")

assert_true("lblCurrentCameraView" in app_text, "app.js does not update #lblCurrentCameraView")
assert_true("SmartHome3D.setCameraView" in app_text, "app.js does not call SmartHome3D.setCameraView")

# 5. CSS PIN-ICON & STYLES INTEGRITY
assert_true(".pin-3d .pin-icon {\n  display: none !important;\n}" not in style_text, "style.css still hides pin icons")
assert_true(".pin-3d .pin-icon" in style_text, "style.css missing styling for .pin-3d .pin-icon")
assert_true(".camera-toolbar" in style_text, "style.css missing .camera-toolbar")
assert_true(".btn-cam" in style_text, "style.css missing .btn-cam")

# 6. ALL 7 DEVICES REGISTERED FOR RAYCASTING
devices = [
    "main_door",
    "living_room_light",
    "fan",
    "ac",
    "bedroom_light",
    "alarm_siren",
    "garden_pump",
]
for d in devices:
    pattern = rf'registerClickable\([^,]+,\s*"{d}"\)'
    matches = re.findall(pattern, house3d_text)
    assert_true(len(matches) > 0, f"Device '{d}' has 0 registerClickable calls in house3d.js")

# 7. RAYCASTER PARENT TRAVERSAL & NDC COORDINATES
assert_true("target = target.parent" in house3d_text, "Missing parent traversal for nested meshes in Raycaster")
assert_true("((clientX - rect.left) / rect.width) * 2 - 1" in house3d_text, "Missing standard NDC X transformation")
assert_true("-((clientY - rect.top) / rect.height) * 2 + 1" in house3d_text, "Missing standard NDC Y transformation")

# 8. JAVASCRIPT SYNTAX CHECK (Node.js engine)
res1 = subprocess.run(["node", "-c", str(HOUSE3D_PATH)], capture_output=True, text=True)
assert_true(res1.returncode == 0, f"Node.js syntax error in house3d.js: {res1.stderr}")

res2 = subprocess.run(["node", "-c", str(APP_PATH)], capture_output=True, text=True)
assert_true(res2.returncode == 0, f"Node.js syntax error in app.js: {res2.stderr}")

# 9. LINE ENDING & ENCODING CHECK (POSIX LF, 0 CRLF, NO BOM)
for p in [HOUSE3D_PATH, STYLE_PATH, INDEX_PATH, APP_PATH]:
    raw = p.read_bytes()
    assert_true(b"\r\n" not in raw and b"\r" not in raw, f"CRLF line ending detected in {p.name}")
    assert_true(not raw.startswith(b"\xef\xbb\xbf"), f"UTF-8 BOM detected in {p.name}")

if failures:
    print(f"FAILED with {len(failures)} issues:")
    for f in failures:
        print(f"  [X] {f}")
    sys.exit(1)
else:
    print("SUCCESS: All adversarial stress-tests and integrity checks PASSED (0 failures)!")
    sys.exit(0)
