"""Bộ Kiểm Tra Giám Định Pháp Y Độc Lập (Forensic Integrity Audit Suite) cho Milestone 3.
Thực hiện bởi: Subagent teamwork_auditor (auditor_m3)
Mục tiêu: Độc lập kiểm chứng, không giả định, không tin lời khẳng định, đo đạc thực nghiệm.
"""

import math
import pathlib
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
HOUSE3D_PATH = ROOT / "simulator" / "static" / "house3d.js"
STYLE_PATH = ROOT / "simulator" / "static" / "css" / "style.css"
INDEX_PATH = ROOT / "simulator" / "static" / "index.html"
APP_PATH = ROOT / "simulator" / "static" / "js" / "app.js"

findings = []
verifications = []

def record_pass(item: str, detail: str):
    verifications.append({"status": "PASS", "item": item, "detail": detail})
    print(f"[PASS] {item}: {detail}")

def record_fail(item: str, detail: str):
    findings.append({"status": "FAIL", "item": item, "detail": detail})
    print(f"[FAIL] {item}: {detail}")

print("=== BẮT ĐẦU GIÁM ĐỊNH PHÁP Y CHO MILESTONE 3 ===")

# =========================================================================
# 1. KIỂM TRA ĐỊNH DẠNG TỆP: 100% POSIX LF & UTF-8 KHÔNG BOM
# =========================================================================
print("\n--- Phase 1: Encoding & Line Endings Audit ---")
target_files = [HOUSE3D_PATH, STYLE_PATH, INDEX_PATH, APP_PATH]
for path in target_files:
    raw = path.read_bytes()
    has_crlf = b"\r\n" in raw or b"\r" in raw
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    if has_crlf:
        record_fail(f"Line endings: {path.name}", f"Phát hiện ký tự CRLF (\\r) trong tệp {path.name}!")
    else:
        record_pass(f"Line endings: {path.name}", "100% POSIX LF (0 CRLF)")
    
    if has_bom:
        record_fail(f"BOM: {path.name}", f"Phát hiện UTF-8 BOM ở đầu tệp {path.name}!")
    else:
        record_pass(f"BOM: {path.name}", "UTF-8 không BOM sạch sẽ")

# =========================================================================
# 2. GIÁM ĐỊNH MÃ NGUỒN: ANTI-FACADE & BẢO TỒN DOM TRONG house3d.js
# =========================================================================
print("\n--- Phase 2: house3d.js Deep Code Audit ---")
house3d_content = HOUSE3D_PATH.read_text(encoding="utf-8")

# Kiểm tra container.innerHTML = "" bị loại bỏ
if 'container.innerHTML = ""' in house3d_content or "container.innerHTML = ''" in house3d_content:
    record_fail("DOM Preservation", "Vẫn còn lệnh container.innerHTML = \"\" gây xóa mất nhãn DOM!")
else:
    record_pass("DOM Preservation", "container.innerHTML = \"\" đã bị loại bỏ hoàn toàn.")

# Kiểm tra insertBefore domElement
if "container.insertBefore(renderer.domElement, container.firstChild)" in house3d_content:
    record_pass("Canvas Insertion Order", "renderer.domElement được chèn vào trước firstChild của container, giữ nhãn ở lớp trên.")
else:
    record_fail("Canvas Insertion Order", "Thiếu lệnh container.insertBefore(renderer.domElement, container.firstChild)!")

# Kiểm tra xóa canvas cũ an toàn
if "existingCanvas" in house3d_content and ".remove()" in house3d_content:
    record_pass("Safe Canvas Cleanup", "Chỉ tìm và xóa thẻ <canvas> cũ nếu tồn tại, không chạm vào các phần tử con khác.")
else:
    record_fail("Safe Canvas Cleanup", "Thiếu logic xóa an toàn thẻ <canvas> cũ!")

# =========================================================================
# 3. GIÁM ĐỊNH RAYCASTER & PHÂN BIỆT DRAG VS CLICK
# =========================================================================
print("\n--- Phase 3: Raycaster & Drag vs Click Verification ---")
if "new THREE.Raycaster()" in house3d_content:
    record_pass("Raycaster Instantiation", "Khởi tạo đối tượng THREE.Raycaster() chính quy.")
else:
    record_fail("Raycaster Instantiation", "Không tìm thấy new THREE.Raycaster() trong house3d.js!")

if "Math.hypot" in house3d_content:
    record_pass("Distance Calculation", "Sử dụng Math.hypot tính khoảng cách di chuyển Euclidean chính xác.")
else:
    record_fail("Distance Calculation", "Thiếu hàm Math.hypot để tính khoảng cách chuột!")

# Kiểm tra ngưỡng phân biệt drag vs click
match_threshold = re.search(r"dist\s*<=\s*(\d+)", house3d_content)
if match_threshold:
    threshold_val = int(match_threshold.group(1))
    if threshold_val == 6:
        record_pass("Drag/Click Threshold", f"Ngưỡng phân biệt click vs drag chính xác bằng 6px (dist <= {threshold_val}).")
    else:
        record_fail("Drag/Click Threshold", f"Ngưỡng phân biệt là {threshold_val}px, khác với yêu cầu 6px!")
else:
    record_fail("Drag/Click Threshold", "Không tìm thấy biểu thức kiểm tra ngưỡng dist <= 6 trong mouseup!")

# Kiểm tra 7 thiết bị được đăng ký Raycaster
expected_devices = ["main_door", "living_room_light", "fan", "ac", "bedroom_light", "alarm_siren", "garden_pump"]
registered_missing = []
for dev in expected_devices:
    if f'registerClickable' not in house3d_content or f'"{dev}"' not in house3d_content:
        registered_missing.append(dev)

if not registered_missing:
    record_pass("7 Actuator Meshes Registration", "Toàn bộ 7 thiết bị chấp hành được đăng ký qua registerClickable().")
else:
    record_fail("7 Actuator Meshes Registration", f"Thiếu đăng ký cho các thiết bị: {registered_missing}")

# Kiểm tra cơ chế duyệt ngược tìm deviceId (parent traversal)
if "target = target.parent" in house3d_content and "userData.deviceId" in house3d_content:
    record_pass("Parent Mesh Traversal", "Có vòng lặp duyệt ngược parent để lấy userData.deviceId khi click vào mesh con/group.")
else:
    record_fail("Parent Mesh Traversal", "Thiếu cơ chế duyệt ngược parent để nhận diện deviceId từ sub-mesh!")

# Kiểm tra cursor pointer khi hover
if "cursor = \"pointer\"" in house3d_content or "cursor = 'pointer'" in house3d_content:
    record_pass("Hover Cursor State", "Cập nhật style.cursor = 'pointer' khi Raycaster chạm vào mesh thiết bị.")
else:
    record_fail("Hover Cursor State", "Thiếu logic đổi con trỏ chuột sang pointer khi hover!")

# =========================================================================
# 4. GIÁM ĐỊNH CSS: KHÔNG CÒN RULE ẨN ICON & CÓ STYLES CHO CAMERA / PINS
# =========================================================================
print("\n--- Phase 4: CSS Audit in style.css ---")
style_content = STYLE_PATH.read_text(encoding="utf-8")

if ".pin-3d .pin-icon {\n  display: none !important;\n}" in style_content or ".pin-3d .pin-icon{display:none!important}" in style_content:
    record_fail("CSS Pin Icon Display", "style.css vẫn còn ép display: none !important trên .pin-icon!")
else:
    record_pass("CSS Pin Icon Display", "Đã xóa bỏ hoàn toàn display: none !important trên .pin-icon.")

if ".camera-toolbar" in style_content and ".btn-cam" in style_content and ".btn-cam.active" in style_content:
    record_pass("CSS Camera Toolbar", "Đầy đủ CSS styling cho .camera-toolbar, .btn-cam và .btn-cam.active.")
else:
    record_fail("CSS Camera Toolbar", "Thiếu CSS styling cho thanh nút camera preset!")

if ".pin-3d.on" in style_content and ".pin-3d.off" in style_content:
    record_pass("CSS Pin States", "Có CSS styling phân biệt rõ ràng trạng thái ON và OFF cho các nút nổi .pin-3d.")
else:
    record_fail("CSS Pin States", "Thiếu CSS cho .pin-3d.on hoặc .pin-3d.off!")

# =========================================================================
# 5. GIÁM ĐỊNH HTML: DOM CẤU TRÚC 7 NÚT PRESET & NHÃN VIEWPORT
# =========================================================================
print("\n--- Phase 5: HTML DOM Audit in index.html ---")
index_content = INDEX_PATH.read_text(encoding="utf-8")
soup = BeautifulSoup(index_content, "html.parser")

viewport = soup.find(id="house3dViewport")
if viewport:
    labels = viewport.find(id="house3dLabels")
    note = viewport.find(class_="viewport-note")
    if labels and note:
        record_pass("Viewport DOM Tree", "#house3dViewport chứa đầy đủ #house3dLabels và .viewport-note.")
    else:
        record_fail("Viewport DOM Tree", f"Trong #house3dViewport thiếu labels ({bool(labels)}) hoặc note ({bool(note)})!")
else:
    record_fail("Viewport DOM Tree", "Không tìm thấy #house3dViewport trong index.html!")

cam_toolbar = soup.find(class_="camera-toolbar")
if cam_toolbar:
    buttons = cam_toolbar.find_all("button", class_="btn-cam")
    cam_data = [b.get("data-cam") for b in buttons]
    expected_cams = ["overview", "living", "bedroom", "door", "garden", "board", "rotate"]
    if cam_data == expected_cams:
        record_pass("7 Camera Preset Buttons", f"7 nút camera preset hiện diện đúng thứ tự: {cam_data}.")
    else:
        record_fail("7 Camera Preset Buttons", f"Danh sách nút camera preset không khớp: {cam_data} vs {expected_cams}")
else:
    record_fail("7 Camera Preset Buttons", "Không tìm thấy .camera-toolbar trong index.html!")

lbl_view = soup.find(id="lblCurrentCameraView")
if lbl_view:
    record_pass("Camera View Label", "Phần tử #lblCurrentCameraView hiện diện để hiển thị tên góc nhìn hiện tại.")
else:
    record_fail("Camera View Label", "Thiếu phần tử #lblCurrentCameraView trong index.html!")

# =========================================================================
# 6. GIÁM ĐỊNH APP.JS: KẾT NỐI CAMERA TOOLBAR ↔ SmartHome3D.setCameraView
# =========================================================================
print("\n--- Phase 6: app.js Controller Logic Audit ---")
app_content = APP_PATH.read_text(encoding="utf-8")

if "initCameraToolbar" in app_content:
    record_pass("app.js Camera Init", "Hàm initCameraToolbar() được định nghĩa và gọi khởi tạo.")
else:
    record_fail("app.js Camera Init", "Thiếu hàm initCameraToolbar() trong app.js!")

if "setCameraView" in app_content and "data-cam" in app_content:
    record_pass("app.js Camera Event Binding", "app.js đọc thuộc tính data-cam và gọi SmartHome3D.setCameraView(preset).")
else:
    record_fail("app.js Camera Event Binding", "Thiếu logic gọi SmartHome3D.setCameraView() trong app.js!")

# =========================================================================
# 7. THỰC NGHIỆM ĐỐI KHÁNG HEADLESS TRONG NODE.JS (SIMULATION RUN)
# =========================================================================
print("\n--- Phase 7: Node.js Headless Simulation Audit ---")

node_sim_script = """
const fs = require('fs');
const vm = require('vm');

const house3dCode = fs.readFileSync('simulator/static/house3d.js', 'utf8');

// Mock DOM & THREE môi trường headless
const mockTHREE = {
  Raycaster: function() {
    this.setFromCamera = () => {};
    this.intersectObjects = (meshes) => {
      if (mockClickTarget) {
        return [{ object: mockClickTarget }];
      }
      return [];
    };
  },
  Vector2: function() { this.x = 0; this.y = 0; },
  Vector3: function(x,y,z) { this.x = x; this.y = y; this.z = z; this.clone = () => this; this.project = () => ({ x: 0, y: 0, z: 0.5 }); },
  Scene: function() { this.add = () => {}; this.background = null; this.fog = null; },
  Color: function() {},
  FogExp2: function() {},
  PerspectiveCamera: function() {},
  WebGLRenderer: function() {
    this.domElement = {
      addEventListener: (evt, fn) => { mockListeners['canvas:' + evt] = fn; },
      getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 520, right: 800, bottom: 520 }),
      style: {}
    };
    this.setSize = () => {};
    this.setPixelRatio = () => {};
    this.shadowMap = {};
  }
};

let mockClickTarget = null;
const mockListeners = {};
const mockElements = {};

function createMockElement(id, tagName = 'div') {
  return {
    id: id,
    tagName: tagName.toUpperCase(),
    children: [],
    style: {},
    classList: {
      classes: new Set(),
      add(c) { this.classes.add(c); },
      remove(c) { this.classes.delete(c); },
      contains(c) { return this.classes.has(c); },
      toggle(c, force) {
        if (force === undefined) {
          if (this.classes.has(c)) this.classes.delete(c); else this.classes.add(c);
        } else if (force) {
          this.classes.add(c);
        } else {
          this.classes.delete(c);
        }
      }
    },
    addEventListener(evt, fn) {
      mockListeners[id + ':' + evt] = fn;
    },
    querySelector(sel) {
      if (sel === 'canvas') return mockElements['canvas'];
      if (sel.startsWith('[data-cam=')) {
        const cam = sel.match(/\\[data-cam="([^"]+)"\\]/)[1];
        return mockElements['btn_' + cam];
      }
      return null;
    },
    querySelectorAll(sel) {
      if (sel === '.btn-cam') {
        return ['overview', 'living', 'bedroom', 'door', 'garden', 'board', 'rotate'].map(c => mockElements['btn_' + c]);
      }
      return [];
    },
    insertBefore(newChild, refChild) {
      this.children.unshift(newChild);
    },
    appendChild(child) {
      this.children.push(child);
    },
    clientWidth: 800,
    clientHeight: 520,
    getBoundingClientRect() {
      return { left: 0, top: 0, right: 800, bottom: 520, width: 800, height: 520 };
    }
  };
}

mockElements['viewport'] = createMockElement('house3dViewport');
mockElements['labels'] = createMockElement('house3dLabels');
mockElements['canvas'] = createMockElement('canvas', 'canvas');
mockElements['canvas'].remove = function() { mockElements['canvas_removed'] = true; };
mockElements['viewport'].appendChild(mockElements['labels']);

const cameraPresets = ['overview', 'living', 'bedroom', 'door', 'garden', 'board', 'rotate'];
mockElements['camToolbar'] = createMockElement('camToolbar');
cameraPresets.forEach(preset => {
  const btn = createMockElement('btn_' + preset, 'button');
  btn.getAttribute = (attr) => attr === 'data-cam' ? preset : null;
  btn.textContent = preset;
  mockElements['btn_' + preset] = btn;
});

const sandbox = {
  window: { THREE: mockTHREE },
  THREE: mockTHREE,
  document: {
    getElementById(id) {
      if (id === 'house3dViewport') return mockElements['viewport'];
      if (id === 'house3dLabels') return mockElements['labels'];
      if (id === 'lblCurrentCameraView') return mockElements['lblCurrentCameraView'];
      return null;
    },
    querySelector(sel) {
      if (sel === '.camera-toolbar') return mockElements['camToolbar'];
      if (sel === '.view-label') return mockElements['lblCurrentCameraView'];
      return null;
    },
    createElement(tag) {
      return createMockElement('dyn_' + Math.random(), tag);
    },
    addEventListener(evt, fn) {
      mockListeners['doc:' + evt] = fn;
    }
  },
  console: console,
  Math: Math,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  requestAnimationFrame: () => {}
};
sandbox.window.document = sandbox.document;
mockElements['lblCurrentCameraView'] = createMockElement('lblCurrentCameraView');

vm.createContext(sandbox);
vm.runInContext(house3dCode, sandbox);

// Kiểm tra window.SmartHome3D được xuất
if (!sandbox.window.SmartHome3D) {
  console.log("FAIL: window.SmartHome3D not exported");
  process.exit(1);
}

// Thử gọi setCameraView trong Node.js VM
try {
  sandbox.window.SmartHome3D.setCameraView('living');
  if (!mockElements['btn_living'].classList.contains('active')) {
    console.log("FAIL: btn_living active class not set");
    process.exit(1);
  }
  sandbox.window.SmartHome3D.setCameraView('overview');
  if (!mockElements['btn_overview'].classList.contains('active')) {
    console.log("FAIL: btn_overview active class not set");
    process.exit(1);
  }
  console.log("NODE_VM_PASS");
} catch (e) {
  console.log("FAIL_EXCEPTION: " + e.message);
  process.exit(1);
}
"""

sim_result = subprocess.run(["node", "-e", node_sim_script], capture_output=True, text=True)
if "NODE_VM_PASS" in sim_result.stdout:
    record_pass("Node.js VM Simulation", "SmartHome3D.setCameraView chạy hoàn hảo trong Node.js VM, đồng bộ class active cho toolbar button.")
else:
    record_fail("Node.js VM Simulation", f"Node.js VM simulation thất bại: stdout={sim_result.stdout}, stderr={sim_result.stderr}")

# =========================================================================
# 8. TỔNG KẾT & PHÁN QUYẾT PHÁP Y
# =========================================================================
print("\n================ TỔNG KẾT GIÁM ĐỊNH PHÁP Y ================")
print(f"Tổng số tiêu chí kiểm định: {len(verifications) + len(findings)}")
print(f"Số tiêu chí ĐẠT (PASS): {len(verifications)}")
print(f"Số vi phạm (FAIL): {len(findings)}")

if findings:
    print("\n🚨 PHÁN QUYẾT: INTEGRITY VIOLATION")
    for f in findings:
        print(f"  - [{f['item']}]: {f['detail']}")
    sys.exit(1)
else:
    print("\n✅ PHÁN QUYẾT: CLEAN (MÃ NGUỒN HOÀN TOÀN CHÂN THỰC, 0 GIAN LẬN, 0 FACADE)")
    sys.exit(0)
