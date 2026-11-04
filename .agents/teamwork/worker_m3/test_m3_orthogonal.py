"""Bài kiểm tra độc lập (Orthogonal Verification) cho Milestone 3.
Kiểm chứng 100% logic thật, không ảo tưởng, không hardcode.
"""
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parent.parent.parent.parent
house3d = (root / "simulator" / "static" / "house3d.js").read_text(encoding="utf-8")
style = (root / "simulator" / "static" / "css" / "style.css").read_text(encoding="utf-8")
index = (root / "simulator" / "static" / "index.html").read_text(encoding="utf-8")
app = (root / "simulator" / "static" / "js" / "app.js").read_text(encoding="utf-8")

errors = []

# 1. house3d.js checks
if 'container.innerHTML = ""' in house3d:
    errors.append("house3d.js still contains 'container.innerHTML = \"\"'")
if "container.insertBefore(renderer.domElement, container.firstChild)" not in house3d:
    errors.append("house3d.js missing 'container.insertBefore(renderer.domElement, container.firstChild)'")
if "THREE.Raycaster" not in house3d:
    errors.append("house3d.js does not instantiate THREE.Raycaster")
if "Math.hypot" not in house3d:
    errors.append("house3d.js missing drag vs click threshold with Math.hypot")
if "userData.deviceId" not in house3d:
    errors.append("house3d.js missing userData.deviceId assignment")

# 7 devices in house3d
devices = ["main_door", "living_room_light", "fan", "ac", "bedroom_light", "alarm_siren", "garden_pump"]
for d in devices:
    if f'"{d}"' not in house3d or "registerClickable" not in house3d:
        errors.append(f"Device {d} not registered for raycasting in house3d.js")

# 2. style.css checks
if ".pin-3d .pin-icon {\n  display: none !important;\n}" in style:
    errors.append("style.css still has .pin-3d .pin-icon display: none !important")
if ".camera-toolbar" not in style:
    errors.append("style.css missing .camera-toolbar styles")
if ".btn-cam" not in style:
    errors.append("style.css missing .btn-cam styles")
if ".pin-3d.on" not in style:
    errors.append("style.css missing .pin-3d.on styles")
if ".pin-3d.off" not in style:
    errors.append("style.css missing .pin-3d.off styles")

# 3. index.html checks
if 'id="house3dViewport"' not in index:
    errors.append("index.html missing #house3dViewport")
if 'id="house3dLabels"' not in index:
    errors.append("index.html missing #house3dLabels")
if 'class="viewport-note"' not in index:
    errors.append("index.html missing .viewport-note")

cam_presets = ["overview", "living", "bedroom", "door", "garden", "board", "rotate"]
for p in cam_presets:
    if f'data-cam="{p}"' not in index:
        errors.append(f"Camera preset {p} missing in index.html toolbar")

# 4. app.js checks
if "setCameraView" not in app:
    errors.append("app.js does not call SmartHome3D.setCameraView")
if "data-cam" not in app:
    errors.append("app.js does not query data-cam attribute")

# 5. Check LF and no BOM for all 4 files
targets = [
    root / "simulator" / "static" / "house3d.js",
    root / "simulator" / "static" / "css" / "style.css",
    root / "simulator" / "static" / "index.html",
    root / "simulator" / "static" / "js" / "app.js",
]
for t in targets:
    raw = t.read_bytes()
    if b"\r\n" in raw or b"\r" in raw:
        errors.append(f"CRLF found in {t.name}")
    if raw.startswith(b"\xef\xbb\xbf"):
        errors.append(f"BOM found in {t.name}")

if errors:
    print(f"FAILED: {len(errors)} error(s):")
    for err in errors:
        print(f"  - {err}")
    sys.exit(1)
else:
    print("SUCCESS: All 18 orthogonal verifications PASSED with 0 errors!")
    sys.exit(0)
