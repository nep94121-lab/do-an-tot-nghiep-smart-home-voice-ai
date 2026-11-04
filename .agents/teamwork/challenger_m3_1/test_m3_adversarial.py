"""Adversarial Stress Test Suite for Milestone 3 (Python/Pytest).

Author: Subagent teamwork_challenger (Challenger 1)
Role: Empirical Challenger
Workspace: c:\\Users\\LENOVO\\Desktop\\đồ án tốt nghiệp
"""

import math
import pathlib
import re
from bs4 import BeautifulSoup
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
HOUSE3D_PATH = ROOT / "simulator" / "static" / "house3d.js"
STYLE_CSS_PATH = ROOT / "simulator" / "static" / "css" / "style.css"
INDEX_HTML_PATH = ROOT / "simulator" / "static" / "index.html"
APP_JS_PATH = ROOT / "simulator" / "static" / "js" / "app.js"

REQUIRED_ACTUATORS = [
    "main_door",
    "living_room_light",
    "fan",
    "ac",
    "bedroom_light",
    "alarm_siren",
    "garden_pump",
]

CAMERA_PRESETS = [
    "overview",
    "living",
    "bedroom",
    "door",
    "garden",
    "board",
    "rotate",
]


class TestAdversarialM3Raycaster:
    """Kiểm thử đối kháng thuật toán phân biệt Drag và Click của Raycaster."""

    @pytest.mark.parametrize(
        "dx, dy, is_click_expected",
        [
            (0, 0, True),          # Pure click
            (3, 4, True),          # 5px (tremor)
            (6, 0, True),          # Exactly 6.0px
            (0, 6, True),          # Exactly 6.0px vertical
            (-4.24, 4.24, True),   # Diagonal 5.996px <= 6
            (6.001, 0, False),     # 6.001px > 6 (drag)
            (0, 6.001, False),     # 6.001px vertical > 6 (drag)
            (10, 10, False),       # 14.14px > 6 (drag)
            (-50, -50, False),     # 70.7px > 6 (drag)
            (200, 150, False),     # 250px > 6 (orbit rotation)
        ],
    )
    def test_drag_vs_click_threshold_math(self, dx: float, dy: float, is_click_expected: bool):
        """Kiểm chứng độ chính xác toán học của ngưỡng phân biệt Drag xoay camera vs Click thiết bị."""
        dist = math.hypot(dx, dy)
        is_click = dist <= 6.0
        assert is_click == is_click_expected, f"dx={dx}, dy={dy}, dist={dist} -> expected {is_click_expected}, got {is_click}"

    @pytest.mark.parametrize(
        "touch_dx, touch_dy, is_tap_expected",
        [
            (0, 0, True),         # Exact tap
            (5, 5, True),         # 7.07px <= 10
            (10, 0, True),        # 10.0px boundary
            (10.001, 0, False),   # > 10.0px swipe
            (50, 20, False),      # 53.85px swipe/scroll
        ],
    )
    def test_touch_tap_vs_swipe_threshold(self, touch_dx: float, touch_dy: float, is_tap_expected: bool):
        """Kiểm chứng ngưỡng chạm màn hình điện thoại (Touch Tap <= 10px vs Swipe > 10px)."""
        dist = math.hypot(touch_dx, touch_dy)
        is_tap = dist <= 10.0
        assert is_tap == is_tap_expected, f"touch dist={dist} -> expected {is_tap_expected}, got {is_tap}"

    def test_house3d_contains_exact_raycaster_implementation(self):
        """Kiểm tra mã nguồn house3d.js có chứa đúng logic Raycaster và Math.hypot."""
        content = HOUSE3D_PATH.read_text(encoding="utf-8")
        assert "new THREE.Raycaster()" in content, "house3d.js thiếu khởi tạo THREE.Raycaster"
        assert "Math.hypot(e.clientX - mouseDownPos.x, e.clientY - mouseDownPos.y)" in content
        assert "dist <= 6" in content, "house3d.js thiếu điều kiện dist <= 6"
        assert "handleRaycastClick(e.clientX, e.clientY)" in content

    def test_all_7_actuators_registered_for_raycast(self):
        """Kiểm tra 7 thiết bị chấp hành đều được gọi registerClickable trong house3d.js."""
        content = HOUSE3D_PATH.read_text(encoding="utf-8")
        for dev in REQUIRED_ACTUATORS:
            pattern = rf'registerClickable\([^,]+,\s*["\']{dev}["\']\)'
            matches = re.findall(pattern, content)
            assert len(matches) >= 1, f"Thiết bị {dev} chưa được đăng ký qua registerClickable() trong house3d.js"

    def test_raycaster_walks_parent_hierarchy_for_nested_meshes(self):
        """Kiểm tra logic duyệt ngược cây phân cấp (parent traversal) để tìm userData.deviceId."""
        content = HOUSE3D_PATH.read_text(encoding="utf-8")
        assert "while (target && (!target.userData || !target.userData.deviceId) && target !== scene)" in content, (
            "house3d.js thiếu vòng lặp duyệt ngược cha con khi raycast trúng mesh con lồng sâu"
        )


class TestAdversarialM3DomIntegrity:
    """Kiểm thử đối kháng cấu trúc DOM, nhãn và ghi đè container."""

    def test_house3d_never_clears_container_inner_html(self):
        """Xác nhận không còn lệnh container.innerHTML = '' xóa sạch DOM nhãn."""
        content = HOUSE3D_PATH.read_text(encoding="utf-8")
        assert 'container.innerHTML = ""' not in content, "Phát hiện lệnh container.innerHTML = \"\" trong house3d.js!"
        assert "container.innerHTML = ''" not in content, "Phát hiện lệnh container.innerHTML = '' trong house3d.js!"

    def test_canvas_inserted_before_existing_dom_labels(self):
        """Xác nhận canvas được chèn bằng insertBefore để giữ nguyên #house3dLabels và .viewport-note."""
        content = HOUSE3D_PATH.read_text(encoding="utf-8")
        assert "container.insertBefore(renderer.domElement, container.firstChild)" in content

    def test_index_html_viewport_hierarchy(self):
        """Kiểm tra cấu trúc cây phần tử trong #house3dViewport của index.html."""
        html = INDEX_HTML_PATH.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        viewport = soup.find(id="house3dViewport")
        assert viewport is not None, "Không tìm thấy #house3dViewport trong index.html"

        labels = viewport.find(id="house3dLabels")
        assert labels is not None, "Không tìm thấy #house3dLabels bên trong #house3dViewport"

        note = viewport.find(class_="viewport-note")
        assert note is not None, "Không tìm thấy .viewport-note bên trong #house3dViewport"


class TestAdversarialM3CssAndVisuals:
    """Kiểm thử đối kháng CSS, icon emoji và thanh điều khiển."""

    def test_style_css_pin_icon_not_hidden(self):
        """Xác nhận không còn rule .pin-3d .pin-icon { display: none !important; }."""
        css = STYLE_CSS_PATH.read_text(encoding="utf-8")
        hidden_pattern = re.compile(r"\.pin-3d\s+\.pin-icon\s*\{[^}]*display:\s*none\s*!important", re.DOTALL)
        assert not hidden_pattern.search(css), "CSS vẫn còn rule ẩn .pin-icon!"

    def test_style_css_pin_icon_displayed(self):
        """Xác nhận .pin-3d .pin-icon có display visible (inline-flex)."""
        css = STYLE_CSS_PATH.read_text(encoding="utf-8")
        visible_pattern = re.compile(r"\.pin-3d\s+\.pin-icon\s*\{[^}]*display:\s*inline-flex", re.DOTALL)
        assert visible_pattern.search(css), "CSS thiếu display: inline-flex cho .pin-3d .pin-icon"

    def test_style_css_contains_camera_toolbar_and_btn_cam(self):
        """Xác nhận style.css định nghĩa đầy đủ styles cho .camera-toolbar và .btn-cam."""
        css = STYLE_CSS_PATH.read_text(encoding="utf-8")
        assert ".camera-toolbar" in css, "CSS thiếu class .camera-toolbar"
        assert ".btn-cam" in css, "CSS thiếu class .btn-cam"
        assert ".btn-cam.active" in css or ".btn-cam:hover" in css, "CSS thiếu trạng thái active/hover cho .btn-cam"


class TestAdversarialM3CameraPresets:
    """Kiểm thử đối kháng 7 nút Camera Preset và liên kết app.js."""

    def test_index_html_has_all_7_camera_presets(self):
        """Xác nhận index.html có đủ 7 nút camera preset."""
        html = INDEX_HTML_PATH.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        toolbar = soup.find(class_="camera-toolbar")
        assert toolbar is not None, "Không tìm thấy .camera-toolbar trong index.html"

        buttons = toolbar.find_all("button")
        found_presets = [btn.get("data-cam") for btn in buttons if btn.has_attr("data-cam")]
        for p in CAMERA_PRESETS:
            assert p in found_presets, f"Thiếu nút camera preset data-cam='{p}' trong index.html"
        assert len(found_presets) == 7, f"Số nút camera preset không bằng 7 (thực tế: {len(found_presets)})"

    def test_house3d_implements_all_presets(self):
        """Xác nhận hàm setCameraView() trong house3d.js xử lý tất cả 7 presets."""
        content = HOUSE3D_PATH.read_text(encoding="utf-8")
        for p in CAMERA_PRESETS:
            assert f'preset === "{p}"' in content or f"preset === '{p}'" in content, (
                f"house3d.js setCameraView() thiếu xử lý preset '{p}'"
            )

    def test_app_js_camera_toolbar_initialization(self):
        """Xác nhận app.js có logic initCameraToolbar lắng nghe click gọi SmartHome3D.setCameraView."""
        content = APP_JS_PATH.read_text(encoding="utf-8")
        assert "initCameraToolbar" in content, "app.js thiếu hàm initCameraToolbar()"
        assert "SmartHome3D.setCameraView(preset)" in content, "app.js không gọi SmartHome3D.setCameraView(preset)"


class TestAdversarialM3FileIntegrity:
    """Kiểm thử mã hóa UTF-8 không BOM và định dạng dòng POSIX LF (0 CRLF)."""

    @pytest.mark.parametrize(
        "file_path",
        [HOUSE3D_PATH, STYLE_CSS_PATH, INDEX_HTML_PATH, APP_JS_PATH],
        ids=["house3d.js", "style.css", "index.html", "app.js"],
    )
    def test_no_crlf_and_no_bom(self, file_path: pathlib.Path):
        """Đảm bảo tuyệt đối không có CRLF (\\r\\n) và không có BOM byte-order mark."""
        raw = file_path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"Phát hiện UTF-8 BOM trong {file_path.name}"
        assert b"\r\n" not in raw, f"Phát hiện ký tự Windows CRLF (\\r\\n) trong {file_path.name}"
        assert b"\r" not in raw, f"Phát hiện ký tự CR (\\r) trong {file_path.name}"
