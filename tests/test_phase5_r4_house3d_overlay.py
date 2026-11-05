"""Automated TDD Reproduction and Verification Test Suite for Milestone M19: Bug R4.

Issue R4: 3D Chip Overlay Initial Label State
Objective:
Prevent the 3D chip overlay from showing 'Đèn khách (D2):' with an empty value
during the initial update cycle; hide the label when no value is present.

TDD Validation Cycle:
1. Static inspection of simulator/static/house3d.js:
   - buildFloatingPins(): pins initialized with dataset.hasValue = "false", style.display = "none", empty .pin-state.
   - updateDevices(): checks stateVal, hides pin when empty (!stateVal -> display="none", dataset.hasValue="false"), sets hasValue="true" only on valid non-empty value.
   - updatePinPositions(): checks hasValue !== "false" and .pin-state non-empty before setting display = "inline-flex".
2. Node.js Headless VM execution:
   - Initial build state: living_room_light pin is hidden (display="none", dataset.hasValue="false", empty .pin-state).
   - Empty state update: updateDevices([{ id: 'living_room_light', state: '' }]) maintains hidden state (display="none", dataset.hasValue="false").
   - Animation frame update: updatePinPositions() does NOT force display="inline-flex" when pin has no value.
   - Valid state transition: updateDevices([{ id: 'living_room_light', state: 'ON' }]) sets hasValue="true" and allows display="inline-flex".
   - Subsequent empty state transition: updateDevices([{ id: 'living_room_light', state: '' }]) re-hides pin.
3. Encoding and file hygiene: UTF-8 without BOM, 0 CRLF.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOUSE3D_PATH = ROOT / "simulator" / "static" / "house3d.js"
TEST_FILE_PATH = pathlib.Path(__file__).resolve()


class TestBugR4StaticCodeGuards:
    """Kiểm tra mã nguồn tĩnh của house3d.js đảm bảo đầy đủ cơ chế ẩn nhãn rỗng."""

    def test_build_floating_pins_initializes_hidden_device_pins(self):
        """buildFloatingPins() phải khởi tạo các nhãn device với hasValue='false', display='none', và pin-state rỗng."""
        code = HOUSE3D_PATH.read_text(encoding="utf-8")

        # Tìm block else trong buildFloatingPins
        assert 'el.dataset.hasValue = "false";' in code or "el.dataset.hasValue = 'false';" in code, (
            "house3d.js: buildFloatingPins() thiếu khởi tạo el.dataset.hasValue = 'false' cho device pins!"
        )
        assert 'el.style.display = "none";' in code or "el.style.display = 'none';" in code, (
            "house3d.js: buildFloatingPins() thiếu khởi tạo el.style.display = 'none' cho device pins!"
        )
        assert '<strong class="pin-state"></strong>' in code, (
            "house3d.js: buildFloatingPins() không được điền sẵn 'OFF' trước khi có dữ liệu thật!"
        )

    def test_update_devices_handles_empty_state_properly(self):
        """updateDevices() phải kiểm tra stateVal và ẩn nhãn khi giá trị rỗng/chưa nạp."""
        code = HOUSE3D_PATH.read_text(encoding="utf-8")
        assert "stateVal" in code, "house3d.js: updateDevices() thiếu biến chuẩn hóa stateVal!"
        assert 'pin.dataset.hasValue = "false"' in code or "pin.dataset.hasValue = 'false'" in code, (
            "house3d.js: updateDevices() thiếu gán pin.dataset.hasValue = 'false' khi state rỗng!"
        )
        assert 'pin.dataset.hasValue = "true"' in code or "pin.dataset.hasValue = 'true'" in code, (
            "house3d.js: updateDevices() thiếu gán pin.dataset.hasValue = 'true' khi có giá trị hợp lệ!"
        )

    def test_update_pin_positions_guards_against_empty_display(self):
        """updatePinPositions() phải kiểm tra hasValue và pin-state text trước khi gán display='inline-flex'."""
        code = HOUSE3D_PATH.read_text(encoding="utf-8")
        assert "hasValue" in code, "house3d.js: updatePinPositions() thiếu kiểm tra hasValue!"
        assert "stSpan" in code, "house3d.js: updatePinPositions() thiếu kiểm tra nội dung stSpan!"


@pytest.fixture
def node_vm_runner():
    """Hàm chạy kịch bản mô phỏng Node.js VM tương tác với SmartHome3D."""
    def _run(scenario: str) -> dict:
        runner_script = f"""
        const fs = require('fs');
        const vm = require('vm');

        class MockElement {{
          constructor(tagName, id = '') {{
            this.tagName = (tagName || 'DIV').toUpperCase();
            this.id = id;
            this.className = '';
            this.style = {{}};
            this.dataset = {{}};
            this.children = [];
            this.attributes = {{}};
            this.textContentValue = '';
            this.innerHTMLValue = '';
            this.parentNode = null;
            this.clientWidth = 800;
            this.clientHeight = 600;
          }}

          get textContent() {{
            return this.textContentValue;
          }}

          set textContent(v) {{
            this.textContentValue = String(v);
          }}

          get innerHTML() {{
            return this.innerHTMLValue;
          }}

          set innerHTML(html) {{
            this.innerHTMLValue = html;
            this.children = [];
            if (!html) return;

            // Parse pin-icon
            const iconMatch = html.match(/<span[^>]*class="pin-icon"[^>]*>([^<]*)<\\/span>/);
            if (iconMatch) {{
              const el = new MockElement('span');
              el.className = 'pin-icon';
              el.textContent = iconMatch[1];
              el.parentNode = this;
              this.children.push(el);
            }}

            // Parse pin-name
            const nameMatch = html.match(/<span[^>]*class="pin-name"[^>]*>([^<]*)<\\/span>/);
            if (nameMatch) {{
              const el = new MockElement('span');
              el.className = 'pin-name';
              el.textContent = nameMatch[1];
              el.parentNode = this;
              this.children.push(el);
            }}

            // Parse pin-state
            const stMatch = html.match(/<strong[^>]*class="pin-state"[^>]*>([^<]*)<\\/strong>/);
            if (stMatch) {{
              const el = new MockElement('strong');
              el.className = 'pin-state';
              el.textContent = stMatch[1];
              el.parentNode = this;
              this.children.push(el);
            }}
          }}

          setAttribute(k, v) {{
            this.attributes[k] = String(v);
            if (k.startsWith('data-')) {{
              const dataKey = k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
              this.dataset[dataKey] = String(v);
            }}
          }}

          getAttribute(k) {{
            return this.attributes[k] !== undefined ? this.attributes[k] : null;
          }}

          appendChild(child) {{
            child.parentNode = this;
            this.children.push(child);
            return child;
          }}

          insertBefore(newNode, refNode) {{
            newNode.parentNode = this;
            const idx = this.children.indexOf(refNode);
            if (idx === -1) this.children.push(newNode);
            else this.children.splice(idx, 0, newNode);
            return newNode;
          }}

          removeChild(child) {{
            const idx = this.children.indexOf(child);
            if (idx !== -1) {{
              this.children.splice(idx, 1);
              child.parentNode = null;
            }}
            return child;
          }}

          querySelector(sel) {{
            if (sel === '.pin-state') {{
              return this.children.find(c => c.className === 'pin-state') || null;
            }}
            if (sel === '.pin-name') {{
              return this.children.find(c => c.className === 'pin-name') || null;
            }}
            if (sel === 'canvas') {{
              return this.children.find(c => c.tagName === 'CANVAS') || null;
            }}
            return null;
          }}

          querySelectorAll(sel) {{
            return [];
          }}

          addEventListener() {{}}
          removeEventListener() {{}}
        }}

        const viewport = new MockElement('div', 'house3dViewport');
        const labels = new MockElement('div', 'house3dLabels');
        viewport.appendChild(labels);

        const makeStub = () => new Proxy(function() {{}}, {{
          get: (target, prop) => {{
            if (prop === Symbol.toPrimitive || prop === 'valueOf') return () => 0;
            if (prop === 'x' || prop === 'y' || prop === 'z') return 0;
            return makeStub();
          }},
          construct: () => makeStub(),
          apply: () => makeStub()
        }});

        const mockThree = new Proxy({{
          WebGLRenderer: class {{
            constructor() {{
              this.domElement = new MockElement('canvas');
              this.shadowMap = {{}};
            }}
            setSize() {{}}
            setPixelRatio() {{}}
            render() {{}}
          }},
          Vector3: class {{
            constructor(x = 0, y = 0, z = 0) {{
              this.x = x;
              this.y = y;
              this.z = z;
            }}
            clone() {{
              return new mockThree.Vector3(this.x, this.y, this.z);
            }}
            project() {{
              return this; // Keep vector in view range z <= 1
            }}
          }}
        }}, {{
          get: (target, prop) => target[prop] || makeStub()
        }});

        let animCallback = null;
        const mockWindow = {{
          THREE: mockThree,
          devicePixelRatio: 1,
          requestAnimationFrame: (cb) => {{ animCallback = cb; }},
          addEventListener: () => {{}},
          removeEventListener: () => {{}},
          document: {{
            getElementById: (id) => {{
              if (id === 'house3dViewport') return viewport;
              if (id === 'house3dLabels') return labels;
              return new MockElement('div', id);
            }},
            querySelector: (sel) => {{
              if (sel === '#house3dViewport') return viewport;
              if (sel === '#house3dLabels') return labels;
              return null;
            }},
            querySelectorAll: () => [],
            createElement: (tag) => new MockElement(tag)
          }}
        }};
        mockWindow.window = mockWindow;
        mockWindow.globalThis = mockWindow;

        const code = fs.readFileSync('simulator/static/house3d.js', 'utf8');
        const ctx = vm.createContext(mockWindow);
        vm.runInContext(code, ctx);

        // Initialize SmartHome3D
        ctx.window.SmartHome3D.init('house3dViewport', 'house3dLabels');

        // Find living_room_light pin
        const livingPin = labels.children.find(c => c.getAttribute('data-id') === 'living_room_light');
        if (!livingPin) {{
          console.log(JSON.stringify({{ ok: false, error: 'living_room_light_not_found' }}));
          process.exit(0);
        }}

        const result = {{ ok: true }};

        {scenario}

        console.log(JSON.stringify(result));
        """

        proc = subprocess.run(
            ["node", "-e", runner_script],
            capture_output=True,
            text=True,
            cwd=str(ROOT)
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Node execution failed (code {proc.returncode}):\n{proc.stderr}\nSTDOUT:\n{proc.stdout}")
        return json.loads(proc.stdout.strip())

    return _run


class TestBugR4NodeVmHeadlessExecution:
    """Kiểm thử thực nghiệm hành vi nhãn living_room_light trên Node.js Headless VM."""

    def test_initial_state_living_room_light_hidden(self, node_vm_runner):
        """Khi vừa khởi tạo buildFloatingPins, nhãn 'Đèn khách (D2):' phải ẩn và không hiển thị OFF giả tạo."""
        scenario = """
        const stSpan = livingPin.querySelector('.pin-state');
        result.initialDisplay = livingPin.style.display || 'visible';
        result.initialHasValue = livingPin.dataset.hasValue || '';
        result.initialStateText = stSpan ? stSpan.textContent : '';
        result.isProperlyHidden = (livingPin.style.display === 'none' && livingPin.dataset.hasValue === 'false');
        result.isEmptyState = (!stSpan || !stSpan.textContent || stSpan.textContent.trim() === '');
        """
        res = node_vm_runner(scenario)
        assert res["ok"], f"Lỗi Node VM: {res}"
        assert res["initialStateText"] == "", (
            f"LỖI R4: Nhãn ban đầu có text='{res['initialStateText']}', mong đợi rỗng!"
        )
        assert res["isProperlyHidden"], (
            f"LỖI R4: Nhãn ban đầu chưa được ẩn: display='{res['initialDisplay']}', hasValue='{res['initialHasValue']}'"
        )

    def test_update_devices_with_empty_state_remains_hidden(self, node_vm_runner):
        """Khi updateDevices nhận mảng có state rỗng '', nhãn 'living_room_light' phải ẩn hoàn toàn."""
        scenario = """
        ctx.window.SmartHome3D.updateDevices([{ id: 'living_room_light', state: '' }]);
        const stSpan = livingPin.querySelector('.pin-state');
        result.displayAfterEmpty = livingPin.style.display || 'visible';
        result.hasValueAfterEmpty = livingPin.dataset.hasValue || '';
        result.stateTextAfterEmpty = stSpan ? stSpan.textContent : '';
        result.isHidden = (livingPin.style.display === 'none') && (livingPin.dataset.hasValue === 'false');
        """
        res = node_vm_runner(scenario)
        assert res["ok"], f"Lỗi Node VM: {res}"
        assert res["isHidden"], (
            f"LỖI R4: Sau khi cập nhật state rỗng, nhãn không bị ẩn! "
            f"display='{res['displayAfterEmpty']}', hasValue='{res['hasValueAfterEmpty']}'"
        )
        assert res["stateTextAfterEmpty"] == "", (
            f"LỖI R4: stateText sau khi cập nhật state rỗng là '{res['stateTextAfterEmpty']}', mong đợi ''"
        )

    def test_animation_frame_does_not_force_display_when_state_empty(self, node_vm_runner):
        """Khi animation frame chạy updatePinPositions, không được ép display='inline-flex' nếu nhãn không có giá trị."""
        scenario = """
        ctx.window.SmartHome3D.updateDevices([{ id: 'living_room_light', state: '' }]);
        // Kích hoạt một nhịp animation frame
        if (typeof animCallback === 'function') {
          animCallback(16);
        }
        result.displayAfterAnim = livingPin.style.display;
        result.hasValueAfterAnim = livingPin.dataset.hasValue || '';
        result.isStillHidden = (livingPin.style.display === 'none');
        """
        res = node_vm_runner(scenario)
        assert res["ok"], f"Lỗi Node VM: {res}"
        assert res["isStillHidden"], (
            f"LỖI R4: Animation frame đã ép nhãn hiển thị khi state rỗng! "
            f"display='{res['displayAfterAnim']}', mong đợi 'none'"
        )

    def test_valid_state_transitions(self, node_vm_runner):
        """Nhãn phải hiển thị đúng khi có state hợp lệ ('ON' / 'OFF') và tự động ẩn lại khi state trở về rỗng."""
        scenario = """
        // 1. Cập nhật trạng thái ON
        ctx.window.SmartHome3D.updateDevices([{ id: 'living_room_light', state: 'ON' }]);
        if (typeof animCallback === 'function') animCallback(32);
        const stSpan = livingPin.querySelector('.pin-state');
        result.displayOn = livingPin.style.display;
        result.hasValueOn = livingPin.dataset.hasValue || '';
        result.stateOn = stSpan ? stSpan.textContent : '';

        // 2. Chuyển lại trạng thái rỗng
        ctx.window.SmartHome3D.updateDevices([{ id: 'living_room_light', state: '' }]);
        if (typeof animCallback === 'function') animCallback(48);
        result.displayBackToEmpty = livingPin.style.display;
        result.hasValueBackToEmpty = livingPin.dataset.hasValue || '';
        """
        res = node_vm_runner(scenario)
        assert res["ok"], f"Lỗi Node VM: {res}"
        # Trạng thái ON: phải hiển thị
        assert res["hasValueOn"] == "true", f"Kỳ vọng hasValue='true' khi state='ON', nhưng nhận: {res['hasValueOn']}"
        assert res["stateOn"] == "ON", f"Kỳ vọng stateText='ON', nhưng nhận: {res['stateOn']}"
        assert res["displayOn"] == "inline-flex", f"Kỳ vọng display='inline-flex', nhưng nhận: {res['displayOn']}"

        # Trạng thái rỗng: phải tự ẩn
        assert res["hasValueBackToEmpty"] == "false", (
            f"Kỳ vọng hasValue='false' khi trở về rỗng, nhận: {res['hasValueBackToEmpty']}"
        )
        assert res["displayBackToEmpty"] == "none", (
            f"Kỳ vọng display='none' khi trở về rỗng, nhận: {res['displayBackToEmpty']}"
        )


class TestBugR4FileHygiene:
    """Kiểm tra mã hóa UTF-8 không BOM và 0 CRLF."""

    @pytest.mark.parametrize("file_path", [HOUSE3D_PATH, TEST_FILE_PATH])
    def test_zero_crlf_and_no_bom(self, file_path: pathlib.Path):
        raw = file_path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"{file_path.name} chứa UTF-8 BOM!"
        crlf_count = raw.count(b"\r\n")
        assert crlf_count == 0, f"{file_path.name} chứa {crlf_count} ký tự CRLF!"
