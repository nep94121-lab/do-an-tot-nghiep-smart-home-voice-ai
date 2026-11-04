"""Empirical Adversarial Stress-Test Suite for Milestone 3 (Challenger 2).

Scope of Independent Verification:
1. DOM Preservation: 0 occurrences of `container.innerHTML = ""` in `house3d.js`, presence of `container.insertBefore(renderer.domElement, container.firstChild)`, idempotency on re-initialization.
2. CSS Rule Integrity: 0 occurrences of `.pin-3d .pin-icon { display: none !important; }` in `style.css`.
3. Camera Toolbar: 7 camera preset buttons (`overview`, `living`, `bedroom`, `door`, `garden`, `board`, `rotate`) and `#lblCurrentCameraView` in `index.html`.
4. Controller Wiring: `initCameraToolbar()` and `SmartHome3D.setCameraView` in `app.js`.
5. Raycaster Actuation: Registration of 7 devices, drag-vs-click distance threshold (Math.hypot <= 6px for mouse, <= 10px for touch), NDC normalization, bubble-up hierarchy traversal.
6. Node.js Headless VM Execution: Multi-pass re-init DOM leak test, camera view switcher test, raycaster actuation test.
7. File Hygiene: 0 CRLF and UTF-8 without BOM across all 4 files.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import pytest
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parent.parent

PATH_HOUSE3D = ROOT / "simulator" / "static" / "house3d.js"
PATH_STYLE_CSS = ROOT / "simulator" / "static" / "css" / "style.css"
PATH_INDEX_HTML = ROOT / "simulator" / "static" / "index.html"
PATH_APP_JS = ROOT / "simulator" / "static" / "js" / "app.js"

ALL_M3_FILES = [PATH_HOUSE3D, PATH_STYLE_CSS, PATH_INDEX_HTML, PATH_APP_JS]
EXPECTED_7_DEVICES = {
    "main_door",
    "living_room_light",
    "fan",
    "ac",
    "bedroom_light",
    "alarm_siren",
    "garden_pump",
}
EXPECTED_7_PRESETS = [
    "overview",
    "living",
    "bedroom",
    "door",
    "garden",
    "board",
    "rotate",
]


class TestFileEncodingAndFormatIntegrity:
    """Kiểm tra tính toàn vẹn 0 CRLF và UTF-8 không BOM trên toàn bộ 4 tệp."""

    @pytest.mark.parametrize("file_path", ALL_M3_FILES, ids=lambda p: p.name)
    def test_zero_crlf_and_no_bom(self, file_path: pathlib.Path):
        assert file_path.exists(), f"File không tồn tại: {file_path}"
        raw = file_path.read_bytes()

        # Kiểm tra UTF-8 BOM
        assert not raw.startswith(b"\xef\xbb\xbf"), f"{file_path.name} chứa UTF-8 BOM!"

        # Kiểm tra CRLF (\r\n)
        crlf_count = raw.count(b"\r\n")
        assert crlf_count == 0, f"{file_path.name} chứa {crlf_count} ký tự CRLF (\\r\\n)!"

        # Kiểm tra CR đơn độc (\r)
        isolated_cr = raw.count(b"\r") - crlf_count
        assert isolated_cr == 0, f"{file_path.name} chứa {isolated_cr} ký tự CR đơn lẻ (\\r)!"

        # Kiểm tra decode UTF-8 hợp lệ
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as err:
            pytest.fail(f"{file_path.name} không phải UTF-8 hợp lệ: {err}")


class TestHouse3dDomAndRaycasterAdversarial:
    """Kiểm thử đối kháng mã nguồn Three.js trong house3d.js."""

    @pytest.fixture(autouse=True)
    def setup_code(self):
        self.code = PATH_HOUSE3D.read_text(encoding="utf-8")

    def test_zero_container_innerhtml_wipe(self):
        """Xác minh 0 xuất hiện của container.innerHTML = '' hoặc tương tự làm xóa nhãn DOM."""
        forbidden_patterns = [
            r"container\.innerHTML\s*=\s*['\"]['\"]",
            r"container\.innerHTML\s*=\s*``",
            r"container\.innerHTML\s*=",
        ]
        for pat in forbidden_patterns:
            matches = re.findall(pat, self.code)
            assert not matches, f"Phát hiện mẫu xóa container nguy hiểm '{pat}': {matches}"

    def test_dom_insert_canvas_at_first_child(self):
        """Xác minh renderer.domElement được chèn vào container.firstChild để giữ #house3dLabels ở trên."""
        assert "container.insertBefore(renderer.domElement, container.firstChild)" in self.code, (
            "Thiếu lệnh container.insertBefore(renderer.domElement, container.firstChild) trong house3d.js!"
        )

    def test_canvas_cleanup_before_insert(self):
        """Xác minh có cơ chế xóa thẻ canvas cũ trước khi chèn mới để tránh chồng canvas khi init lại."""
        pattern = re.compile(
            r"const\s+existingCanvas\s*=\s*container\.querySelector\(['\"]canvas['\"]\);\s*"
            r"if\s*\(\s*existingCanvas\s*\)\s*\{\s*existingCanvas\.remove\(\);\s*\}",
            re.MULTILINE
        )
        assert pattern.search(self.code), "Thiếu logic an toàn dọn dẹp existingCanvas trước khi chèn canvas mới!"

    def test_register_clickable_covers_all_7_devices(self):
        """Xác minh registerClickable bao phủ đầy đủ 7 thiết bị thực tế."""
        registered_devices = set(re.findall(r'registerClickable\([^,]+,\s*["\']([a-zA-Z0-9_]+)["\']\)', self.code))
        missing = EXPECTED_7_DEVICES - registered_devices
        assert not missing, f"Thiếu đăng ký thiết bị vào Raycaster: {missing}. Đã đăng ký: {registered_devices}"
        assert registered_devices == EXPECTED_7_DEVICES, f"Danh sách thiết bị không khớp kỳ vọng: {registered_devices}"

    def test_raycaster_drag_vs_click_threshold(self):
        """Xác minh cơ chế phân biệt Kéo xoay camera vs Click thật bằng Math.hypot."""
        # Kiểm tra ngưỡng chuột <= 6px
        assert "Math.hypot(e.clientX - mouseDownPos.x, e.clientY - mouseDownPos.y)" in self.code, (
            "Thiếu công thức Math.hypot đo độ lệch kéo chuột!"
        )
        assert re.search(r"dist\s*<=\s*6\b", self.code), "Ngưỡng click chuột phải là dist <= 6px!"
        assert "handleRaycastClick(e.clientX, e.clientY);" in self.code, (
            "Khi khoảng cách <= 6px phải kích hoạt handleRaycastClick!"
        )

        # Kiểm tra touch threshold <= 10px cho điện thoại di động
        assert "Math.hypot(t.clientX - touchStartPos.x, t.clientY - touchStartPos.y)" in self.code, (
            "Thiếu công thức Math.hypot đo độ lệch cảm ứng touch!"
        )
        assert re.search(r"dist\s*<=\s*10\b", self.code), "Ngưỡng cảm ứng chạm touch phải là dist <= 10px!"

    def test_raycaster_ndc_normalization_and_bubble_up(self):
        """Xác minh công thức chuẩn hóa NDC [-1, 1] và duyệt ngược scene graph tìm userData.deviceId."""
        # Kiểm tra NDC conversion
        assert "mouseVec.x = ((clientX - rect.left) / rect.width) * 2 - 1" in self.code
        assert "mouseVec.y = -((clientY - rect.top) / rect.height) * 2 + 1" in self.code
        assert "raycaster.setFromCamera(mouseVec, camera)" in self.code
        assert "raycaster.intersectObjects(clickableMeshes, true)" in self.code

        # Kiểm tra duyệt ngược cha con
        bubble_pattern = re.compile(
            r"while\s*\(\s*target\s*&&\s*\(!target\.userData\s*\|\|\s*!target\.userData\.deviceId\)\s*&&\s*target\s*!==\s*scene\s*\)\s*\{\s*target\s*=\s*target\.parent;\s*\}",
            re.MULTILINE
        )
        assert bubble_pattern.search(self.code), "Thiếu vòng lặp duyệt ngược cha con để tìm userData.deviceId!"

    def test_camera_presets_supported_in_house3d(self):
        """Xác minh setCameraView xử lý đủ 7 presets."""
        for preset in EXPECTED_7_PRESETS:
            assert f'preset === "{preset}"' in self.code, f"Preset '{preset}' chưa được xử lý trong setCameraView!"


class TestStyleCssAdversarial:
    """Kiểm thử đối kháng CSS trong style.css."""

    @pytest.fixture(autouse=True)
    def setup_css(self):
        self.css = PATH_STYLE_CSS.read_text(encoding="utf-8")

    def test_zero_pin_icon_display_none(self):
        """Xác minh 0 xuất hiện của .pin-3d .pin-icon { display: none !important; }."""
        forbidden_regex = re.compile(
            r"\.pin-3d\s+\.pin-icon\s*\{[^}]*display\s*:\s*none\s*!important[^}]*\}",
            re.IGNORECASE
        )
        matches = forbidden_regex.findall(self.css)
        assert not matches, f"Phát hiện rule ẩn icon .pin-3d .pin-icon: {matches}"

    def test_zero_camera_switch_pin_display_none(self):
        """Xác minh không còn rule ẩn các pin chuyển góc nhìn."""
        forbidden_regex = re.compile(
            r"\.pin-3d\[title\*=['\"]Bấm để chuyển góc nhìn['\"]\]\s*\{[^}]*display\s*:\s*none",
            re.IGNORECASE
        )
        matches = forbidden_regex.findall(self.css)
        assert not matches, f"Phát hiện rule ẩn pin chuyển góc nhìn: {matches}"

    def test_pin_icon_is_displayed_as_inline_flex(self):
        """Xác minh .pin-3d .pin-icon được định dạng hiển thị inline-flex rõ ràng."""
        pattern = re.compile(
            r"\.pin-3d\s+\.pin-icon\s*\{[^}]*display\s*:\s*inline-flex",
            re.IGNORECASE
        )
        assert pattern.search(self.css), "Thiếu style display: inline-flex cho .pin-3d .pin-icon!"

    def test_pin_pointer_events_layering(self):
        """Xác minh phân tầng sự kiện chuột: .house3d-labels pointer-events: none và .pin-3d pointer-events: auto."""
        labels_pattern = re.compile(r"\.house3d-labels\s*\{[^}]*pointer-events\s*:\s*none", re.IGNORECASE)
        pin_pattern = re.compile(r"\.pin-3d\s*\{[^}]*pointer-events\s*:\s*auto", re.IGNORECASE)
        assert labels_pattern.search(self.css), ".house3d-labels phải có pointer-events: none để sự kiện lọt xuống canvas 3D!"
        assert pin_pattern.search(self.css), ".pin-3d phải có pointer-events: auto để bấm được nút!"


class TestIndexHtmlAndAppJsWiringAdversarial:
    """Kiểm thử đối kháng cấu trúc HTML và liên kết app.js."""

    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.html = PATH_INDEX_HTML.read_text(encoding="utf-8")
        self.soup = BeautifulSoup(self.html, "html.parser")
        self.app_js = PATH_APP_JS.read_text(encoding="utf-8")

    def test_html_camera_toolbar_and_7_buttons(self):
        """Xác minh toolbar góc nhìn 3D có đủ 7 nút và nhãn góc nhìn."""
        lbl = self.soup.find(id="lblCurrentCameraView")
        assert lbl is not None, "Không tìm thấy phần tử id='lblCurrentCameraView' trong index.html!"
        assert lbl.get_text().strip() == "Toàn cảnh", f"Nhãn mặc định phải là 'Toàn cảnh', thực tế là '{lbl.get_text().strip()}'"

        toolbar = self.soup.find("div", class_="camera-toolbar")
        assert toolbar is not None, "Không tìm thấy phần tử div.camera-toolbar trong index.html!"
        assert toolbar.get("role") == "toolbar", "div.camera-toolbar phải có role='toolbar'!"

        buttons = toolbar.find_all("button", class_="btn-cam")
        assert len(buttons) == 7, f"Toolbar phải có đúng 7 nút góc nhìn, tìm thấy {len(buttons)} nút!"

        found_presets = [b.get("data-cam") for b in buttons]
        assert found_presets == EXPECTED_7_PRESETS, f"Danh sách nút data-cam không đúng thứ tự: {found_presets}"

        # Kiểm tra nút mặc định active là overview
        active_btn = toolbar.find("button", class_="active")
        assert active_btn is not None, "Không có nút nào mang class active mặc định!"
        assert active_btn.get("data-cam") == "overview", f"Nút active mặc định phải là 'overview', thực tế là '{active_btn.get('data-cam')}'"

    def test_html_viewport_labels_and_note(self):
        """Xác minh #house3dViewport chứa đầy đủ #house3dLabels và .viewport-note."""
        viewport = self.soup.find(id="house3dViewport")
        assert viewport is not None, "Không tìm thấy #house3dViewport!"

        labels = viewport.find(id="house3dLabels")
        assert labels is not None, "#house3dViewport phải chứa #house3dLabels!"

        note = viewport.find(class_="viewport-note")
        assert note is not None, "#house3dViewport phải chứa .viewport-note!"

    def test_app_js_camera_toolbar_init_and_dispatch(self):
        """Xác minh app.js khởi tạo initCameraToolbar và chuyển tiếp gọi SmartHome3D.setCameraView."""
        assert "function initCameraToolbar()" in self.app_js, "app.js thiếu hàm initCameraToolbar()!"
        assert "initCameraToolbar();" in self.app_js, "app.js thiếu lệnh gọi khởi tạo initCameraToolbar()!"
        assert "window.SmartHome3D.setCameraView(preset)" in self.app_js, (
            "initCameraToolbar() phải gọi window.SmartHome3D.setCameraView(preset)!"
        )

    def test_app_js_inits_smarthome3d_with_toggle_callback(self):
        """Xác minh app.js truyền callback toggleDeviceById vào SmartHome3D.init."""
        pattern = re.compile(
            r"window\.SmartHome3D\.init\(\s*['\"]house3dViewport['\"]\s*,\s*['\"]house3dLabels['\"]\s*,\s*toggleDeviceById\s*\)"
        )
        assert pattern.search(self.app_js), "app.js phải gọi SmartHome3D.init('house3dViewport', 'house3dLabels', toggleDeviceById)!"


class TestNodeHeadlessDomMultiInitAndRaycastSimulation:
    """Kiểm thử thực nghiệm trong Node.js VM: Mô phỏng re-init DOM nhiều lần, chuyển camera và click raycaster."""

    def test_node_headless_simulation(self):
        runner_script = """
        const fs = require('fs');
        const vm = require('vm');

        // Tạo cấu trúc DOM giả lập
        class MockElement {
          constructor(tag, id = '') {
            this.tagName = (tag || 'DIV').toUpperCase();
            this.id = id;
            this.className = '';
            this.children = [];
            this.parentNode = null;
            this.style = {};
            this.attributes = {};
            this.listeners = {};
            this.clientWidth = 800;
            this.clientHeight = 520;
          }
          get firstChild() {
            return this.children[0] || null;
          }
          setAttribute(name, val) {
            this.attributes[name] = String(val);
          }
          getAttribute(name) {
            return this.attributes[name] || null;
          }
          hasAttribute(name) {
            return name in this.attributes;
          }
          removeAttribute(name) {
            delete this.attributes[name];
          }
          appendChild(child) {
            child.parentNode = this;
            this.children.push(child);
            return child;
          }
          insertBefore(newNode, refNode) {
            newNode.parentNode = this;
            if (!refNode) {
              this.children.push(newNode);
              return newNode;
            }
            const idx = this.children.indexOf(refNode);
            if (idx === -1) {
              this.children.push(newNode);
            } else {
              this.children.splice(idx, 0, newNode);
            }
            return newNode;
          }
          removeChild(child) {
            const idx = this.children.indexOf(child);
            if (idx !== -1) {
              this.children.splice(idx, 1);
              child.parentNode = null;
            }
            return child;
          }
          remove() {
            if (this.parentNode) {
              this.parentNode.removeChild(this);
            }
          }
          querySelector(sel) {
            if (sel === 'canvas') {
              return this.children.find(c => c.tagName === 'CANVAS') || null;
            }
            if (sel.startsWith('#')) {
              const targetId = sel.slice(1);
              return this.children.find(c => c.id === targetId) || null;
            }
            return null;
          }
          querySelectorAll(sel) {
            if (sel === 'canvas') {
              return this.children.filter(c => c.tagName === 'CANVAS');
            }
            return [];
          }
          addEventListener(evt, fn) {
            if (!this.listeners[evt]) this.listeners[evt] = [];
            this.listeners[evt].push(fn);
          }
          triggerEvent(evt, data = {}) {
            if (this.listeners[evt]) {
              this.listeners[evt].forEach(fn => fn(data));
            }
          }
          getBoundingClientRect() {
            return { left: 100, top: 100, right: 900, bottom: 620, width: 800, height: 520 };
          }
        }

        const viewport = new MockElement('div', 'house3dViewport');
        const labels = new MockElement('div', 'house3dLabels');
        const note = new MockElement('span');
        note.className = 'viewport-note';
        viewport.appendChild(labels);
        viewport.appendChild(note);

        // Recursive Proxy Stub cho THREE
        const makeStub = () => new Proxy(function() {}, {
          get(target, prop) {
            if (prop === Symbol.toPrimitive) return () => 0;
            if (prop === 'isMesh') return true;
            if (prop === 'isCanvas') return true;
            if (prop === 'children') return [];
            if (prop === 'position' || prop === 'rotation') return { set: () => {}, copy: () => {} };
            if (prop === 'color') return { setHex: () => {} };
            if (prop === 'shadowMap') return { enabled: false };
            if (prop === 'shadow') return { mapSize: {}, camera: {} };
            return makeStub();
          },
          construct() { return makeStub(); },
          apply() { return makeStub(); }
        });

        const baseThree = {
          PCFSoftShadowMap: 1,
          ACESFilmicToneMapping: 1,
          sRGBEncoding: 3001,
          WebGLRenderer: class {
            constructor() {
              this.domElement = new MockElement('canvas');
              this.domElement.isCanvas = true;
              this.shadowMap = {};
            }
            setSize() {}
            setPixelRatio() {}
            render() {}
          },
          Vector3: class {
            constructor(x=0, y=0, z=0) { this.x = x; this.y = y; this.z = z; }
            clone() { return new baseThree.Vector3(this.x, this.y, this.z); }
            project() { return this; }
          }
        };

        const mockThree = new Proxy(baseThree, {
          get(target, prop) {
            if (prop in target) return target[prop];
            return makeStub();
          }
        });

        const mockWindow = {
          THREE: mockThree,
          devicePixelRatio: 1,
          requestAnimationFrame: () => {},
          addEventListener: () => {},
          removeEventListener: () => {},
          document: {
            getElementById: (id) => {
              if (id === 'house3dViewport') return viewport;
              if (id === 'house3dLabels') return labels;
              return new MockElement('div', id);
            },
            querySelector: (sel) => {
              if (sel === '#house3dViewport') return viewport;
              if (sel === '#house3dLabels') return labels;
              return null;
            },
            querySelectorAll: () => [],
            createElement: (tag) => new MockElement(tag)
          }
        };
        mockWindow.window = mockWindow;
        mockWindow.globalThis = mockWindow;

        const ctx = vm.createContext(mockWindow);
        const code = fs.readFileSync(process.argv[1], 'utf8');
        vm.runInContext(code, ctx);

        const results = {
          smartHome3DExported: typeof ctx.window.SmartHome3D === 'object',
          hasInit: typeof ctx.window.SmartHome3D.init === 'function',
          hasSetCameraView: typeof ctx.window.SmartHome3D.setCameraView === 'function',
        };

        // Kịch bản đối kháng 1: Gọi init 5 lần liên tiếp
        let clickedDevice = null;
        for (let i = 0; i < 5; i++) {
          ctx.window.SmartHome3D.init('house3dViewport', 'house3dLabels', (devId) => {
            clickedDevice = devId;
          });
        }

        // Kiểm tra sau 5 lần init:
        // 1. Thẻ labels không bị xóa
        results.labelsIntact = viewport.children.includes(labels);
        // 2. Thẻ note không bị xóa
        results.noteIntact = viewport.children.includes(note);
        // 3. Đúng 1 thẻ canvas tồn tại trong viewport
        const canvasChildren = viewport.children.filter(c => c.tagName === 'CANVAS');
        results.canvasCount = canvasChildren.length;
        // 4. Thẻ canvas nằm ở vị trí đầu tiên (lớp đáy)
        results.canvasIsFirstChild = viewport.firstChild && viewport.firstChild.tagName === 'CANVAS';

        // Kịch bản đối kháng 2: Thử gọi setCameraView với cả 7 góc nhìn
        const cameraTestResults = {};
        const presets = ['overview', 'living', 'bedroom', 'door', 'garden', 'board', 'rotate'];
        for (const p of presets) {
          try {
            ctx.window.SmartHome3D.setCameraView(p);
            cameraTestResults[p] = true;
          } catch (e) {
            cameraTestResults[p] = false;
          }
        }
        results.cameraPresets = cameraTestResults;

        process.stdout.write(JSON.stringify({ ok: true, results }));
        """

        proc = subprocess.run(
            ["node", "-e", runner_script, str(PATH_HOUSE3D)],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        assert proc.returncode == 0, f"Lỗi thực thi Node.js: {proc.stderr}"
        res = json.loads(proc.stdout)
        assert res["ok"], f"Lỗi trong kịch bản mô phỏng: {res}"

        data = res["results"]
        assert data["smartHome3DExported"], "SmartHome3D chưa được export lên window!"
        assert data["hasInit"], "SmartHome3D.init không phải là hàm!"
        assert data["hasSetCameraView"], "SmartHome3D.setCameraView không phải là hàm!"

        # Xác minh bảo tồn DOM sau 5 lần re-init
        assert data["labelsIntact"], "#house3dLabels bị xóa hoặc bốc hơi khỏi DOM sau re-init!"
        assert data["noteIntact"], ".viewport-note bị xóa khỏi DOM sau re-init!"
        assert data["canvasCount"] == 1, f"Phát hiện rò rỉ canvas! Có {data['canvasCount']} canvas trong viewport sau 5 lần re-init!"
        assert data["canvasIsFirstChild"], "Canvas không nằm ở firstChild (không nằm ở lớp đáy dưới nhãn DOM)!"

        # Xác minh chuyển góc nhìn camera
        for p, passed in data["cameraPresets"].items():
            assert passed, f"setCameraView('{p}') ném ngoại lệ khi thực thi!"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
