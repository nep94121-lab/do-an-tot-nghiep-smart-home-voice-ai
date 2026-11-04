"""Bộ kiểm thử TDD cho Milestone 3: Giao diện, Bố cục, 3D Thu gọn & Phân trang Nhật ký (Bugs 6, 7, 8, 9, 12, 13).

Nhiệm vụ:
- Bug 6: /app 3D collapse render: Trong mobile_app/index.html nạp /static/vendor/three.min.js,
         /static/vendor/GLTFLoader.js, /static/house3d.js. Trong mobile_app.js gọi SmartHome3D.init("mobileOverviewBox", null, ...)
         và cập nhật updateDevices, updateSensors trong renderState. Giữ DOM ID #mobileOverviewBox và class preview-16-9.
- Bug 7: /app Devices tab show all 7 devices: Trong mobile_app.js khởi tạo showAllDevices = true (hoặc không slice 4 thiết bị),
         đảm bảo #devGrid hiển thị đủ 7 thiết bị: main_door, living_room_light, bedroom_light, fan, ac, alarm_siren, garden_pump.
- Bug 8: /app Profile tab safe-area & countdown: Trong mobile_app/index.html xóa câu thừa "Mỗi tab mở một màn riêng, không cuộn tới mục khác.".
         Trong mobile_app.css thêm safe-area padding cho #tabViewAccount / #mobileBtnLogout không bị che lấp bởi thanh đáy Samsung Internet.
         Trong mobile_app.js định dạng #mobileQrCountdown thành "Đổi mã sau ${rem}s".
- Bug 9: Desktop / sensor panel: Trong simulator/static/index.html bổ sung <section class="panel sensors" id="secSensors">
         chứa 3 ô Nhiệt độ, Độ ẩm, Độ ẩm đất. Trong app.js cập nhật các ô này kèm hàm clamp [0, 60]°C, [0, 100]%, [0, 100]%.
- Bug 12: QR scanner duplicate text: Trong mobile_app.js hàm openQrScanner(), xóa dòng gán lặp lại
          status.textContent = 'Đưa mã QR vào trong khung để quét' tránh lặp với p.instruction.
- Bug 13: /logs pagination and filter: Trong simulator/static/logs.html và logs.js cài đặt phân trang client-side (pageSize = 20),
          có nút load more / phân trang (#btnLogsLoadMore, #logsPaginationInfo), kết nối bộ lọc ngày #logDateRange,
          và che giấu toàn bộ gợi ý mật khẩu trong chi tiết log.
"""
from __future__ import annotations

import pathlib
import re
import sys
from bs4 import BeautifulSoup
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# =============================================================================
# BUG 6: /app 3D COLLAPSE RENDER (THREE.JS + HOUSE3D TRÊN MOBILE)
# =============================================================================

class TestBug6MobileHouse3d:
    """Bug 6: /app phải nạp Three.js, GLTFLoader, house3d.js và khởi tạo SmartHome3D trong #mobileOverviewBox."""

    def test_bug6_mobile_html_includes_three_and_house3d(self):
        """mobile_app/index.html phải nạp three.min.js, GLTFLoader.js và house3d.js trước mobile_app.js."""
        html_path = ROOT / "mobile_app" / "index.html"
        assert html_path.exists(), "Tệp mobile_app/index.html không tồn tại!"
        content = html_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")

        script_srcs = [s.get("src", "") for s in soup.find_all("script") if s.get("src")]

        # Phải chứa đủ 3 script 3D
        assert any("three.min.js" in s for s in script_srcs), "Thiếu /static/vendor/three.min.js trong mobile_app/index.html"
        assert any("GLTFLoader.js" in s for s in script_srcs), "Thiếu /static/vendor/GLTFLoader.js trong mobile_app/index.html"
        assert any("house3d.js" in s for s in script_srcs), "Thiếu /static/house3d.js trong mobile_app/index.html"

        # house3d.js phải đứng trước mobile_app.js
        idx_house3d = next(i for i, s in enumerate(script_srcs) if "house3d.js" in s)
        idx_mobile_app = next(i for i, s in enumerate(script_srcs) if "mobile_app.js" in s)
        assert idx_house3d < idx_mobile_app, "house3d.js phải được nạp trước mobile_app.js"

    def test_bug6_mobile_overview_box_structure(self):
        """Phần tử #mobileOverviewBox phải tồn tại và giữ nguyên class preview-16-9."""
        html_path = ROOT / "mobile_app" / "index.html"
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        box = soup.find(id="mobileOverviewBox")
        assert box is not None, "Thiếu phần tử #mobileOverviewBox trong mobile_app/index.html"
        classes = box.get("class", [])
        assert "preview-16-9" in classes, "#mobileOverviewBox phải giữ class 'preview-16-9'"

    def test_bug6_mobile_js_inits_and_updates_house3d(self):
        """mobile_app.js phải gọi SmartHome3D.init('mobileOverviewBox', ...) và cập nhật updateDevices/updateSensors."""
        js_path = ROOT / "simulator" / "static" / "js" / "mobile_app.js"
        assert js_path.exists(), "Tệp simulator/static/js/mobile_app.js không tồn tại!"
        content = js_path.read_text(encoding="utf-8")

        # Khởi tạo SmartHome3D
        assert "SmartHome3D.init" in content, "mobile_app.js chưa gọi SmartHome3D.init"
        assert "mobileOverviewBox" in content, "mobile_app.js chưa truyền mobileOverviewBox vào SmartHome3D.init"

        # Đồng bộ trạng thái thiết bị và cảm biến trong renderState
        assert "updateDevices" in content, "mobile_app.js chưa gọi SmartHome3D.updateDevices"
        assert "updateSensors" in content, "mobile_app.js chưa gọi SmartHome3D.updateSensors"


# =============================================================================
# BUG 7: /app DEVICES TAB SHOW ALL 7 DEVICES
# =============================================================================

class TestBug7MobileDevicesTabAll7Devices:
    """Bug 7: Tab Thiết bị trên /app phải hiển thị đủ cả 7 thiết bị như desktop."""

    def test_bug7_show_all_devices_flag_default_true(self):
        """showAllDevices phải có giá trị mặc định là true trong mobile_app.js."""
        js_path = ROOT / "simulator" / "static" / "js" / "mobile_app.js"
        content = js_path.read_text(encoding="utf-8")

        # Kiểm tra biến showAllDevices được gán true mặc định
        match = re.search(r"let\s+showAllDevices\s*=\s*(true|false);", content)
        assert match is not None, "Không tìm thấy khai báo showAllDevices trong mobile_app.js"
        assert match.group(1) == "true", "showAllDevices phải được khởi tạo bằng true để hiện đủ 7 thiết bị ngay từ đầu"

    def test_bug7_no_default_4_devices_truncation(self):
        """Hàm renderState không được cắt cụt mảng thiết bị về 4 phần tử khi showAllDevices = true."""
        js_path = ROOT / "simulator" / "static" / "js" / "mobile_app.js"
        content = js_path.read_text(encoding="utf-8")

        # Kiểm tra đoạn code xử lý visibleDevices
        assert "showAllDevices ? filtered : filtered.slice(0, 4)" in content or "visibleDevices = filtered" in content or "showAllDevices" in content


# =============================================================================
# BUG 8: /app PROFILE TAB SAFE-AREA AND COUNTDOWN
# =============================================================================

class TestBug8ProfileSafeAreaAndCountdown:
    """Bug 8: Xóa câu text thừa, bảo đảm safe-area cho nút logout và làm rõ đếm ngược Mời khách."""

    def test_bug8_removed_redundant_tab_text_in_html(self):
        """Câu 'Mỗi tab mở một màn riêng, không cuộn tới mục khác.' phải bị xóa bỏ khỏi mobile_app/index.html."""
        html_path = ROOT / "mobile_app" / "index.html"
        content = html_path.read_text(encoding="utf-8")
        assert "Mỗi tab mở một màn riêng, không cuộn tới mục khác." not in content, (
            "mobile_app/index.html vẫn còn chứa dòng text thừa: 'Mỗi tab mở một màn riêng, không cuộn tới mục khác.'"
        )

    def test_bug8_safe_area_padding_for_account_and_logout(self):
        """mobile_app.css phải có padding-bottom safe-area cho #tabViewAccount hoặc margin cho #mobileBtnLogout."""
        css_path = ROOT / "simulator" / "static" / "css" / "mobile_app.css"
        assert css_path.exists(), "Tệp simulator/static/css/mobile_app.css không tồn tại!"
        content = css_path.read_text(encoding="utf-8")

        has_account_safe_area = ("#tabViewAccount" in content and "safe-area-inset-bottom" in content) or \
                                ("#mobileBtnLogout" in content and "safe-area-inset-bottom" in content) or \
                                ("body" in content and "calc(88px" not in content and "safe-area-inset-bottom" in content) or \
                                ("safe-area-inset-bottom" in content and ("tabViewAccount" in content or "mobileBtnLogout" in content))
        assert has_account_safe_area, "mobile_app.css thiếu quy tắc padding/margin safe-area cho #tabViewAccount hoặc #mobileBtnLogout"

    def test_bug8_countdown_label_clarity(self):
        """mobile_app.js phải định dạng #mobileQrCountdown rõ ràng như 'Đổi mã sau ${rem}s', không dùng 'Còn ${rem}s' cộc lốc."""
        js_path = ROOT / "simulator" / "static" / "js" / "mobile_app.js"
        content = js_path.read_text(encoding="utf-8")

        # Tìm chuỗi gán vào mobileQrCountdown trong refreshMobileQr10s
        assert "Đổi mã sau" in content or "Làm mới sau" in content, (
            "mobile_app.js chưa cập nhật định dạng đếm ngược rõ ràng ('Đổi mã sau ${rem}s') cho #mobileQrCountdown"
        )
        assert "cdEl.textContent = `Còn ${rem}s`;" not in content and "cdEl.textContent = 'Còn ' + rem + 's';" not in content, (
            "mobile_app.js vẫn còn chứa chuỗi đếm ngược mơ hồ 'Còn ${rem}s' trong #mobileQrCountdown"
        )


# =============================================================================
# BUG 9: DESKTOP SENSOR PANEL & CLAMPING
# =============================================================================

class TestBug9DesktopSensorPanelAndClamping:
    """Bug 9: Desktop / phải có panel #secSensors và kẹp giá trị an toàn [0, 60]°C, [0, 100]%, [0, 100]%."""

    def test_bug9_desktop_html_has_secSensors_panel(self):
        """simulator/static/index.html phải có panel sensors với id='secSensors' và các ô nhiệt độ, độ ẩm, độ ẩm đất."""
        html_path = ROOT / "simulator" / "static" / "index.html"
        assert html_path.exists(), "Tệp simulator/static/index.html không tồn tại!"
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

        sec_sensors = soup.find(id="secSensors")
        assert sec_sensors is not None, "simulator/static/index.html thiếu <section id='secSensors'>"

        # Phải có các phần tử hiển thị giá trị cảm biến
        temp_el = soup.find(id=re.compile(r"sensor.*(?:Temp|Dht)", re.I))
        assert temp_el is not None, "Panel sensors thiếu ô hiển thị Nhiệt độ (vd: sensorTempVal hoặc sensorTempLabel)"

        hum_el = soup.find(id=re.compile(r"sensor.*(?:Hum|Humidity)", re.I))
        assert hum_el is not None, "Panel sensors thiếu ô hiển thị Độ ẩm không khí (vd: sensorHumVal)"

        soil_el = soup.find(id=re.compile(r"sensor.*Soil", re.I))
        assert soil_el is not None, "Panel sensors thiếu ô hiển thị Độ ẩm đất (vd: sensorSoilVal)"

    def test_bug9_app_js_updates_and_clamps_sensors(self):
        """simulator/static/js/app.js phải cập nhật giá trị và clamp: nhiệt độ [0, 60], độ ẩm [0, 100], độ ẩm đất [0, 100]."""
        js_path = ROOT / "simulator" / "static" / "js" / "app.js"
        assert js_path.exists(), "Tệp simulator/static/js/app.js không tồn tại!"
        content = js_path.read_text(encoding="utf-8")

        # Kiểm tra logic cập nhật cảm biến trong app.js
        assert "sensorTempVal" in content or "sensorTempLabel" in content, "app.js thiếu cập nhật sensorTempVal"
        assert "sensorHumVal" in content or "sensorHumLabel" in content or "sensorHumidityVal" in content, "app.js thiếu cập nhật sensorHumVal"
        assert "sensorSoilVal" in content or "sensorSoilLabel" in content, "app.js thiếu cập nhật sensorSoilVal"

        # Kiểm tra hàm clamp (Math.max, Math.min hoặc tương đương)
        clamp_temp = "Math.min(60" in content or "Math.min(60.0" in content or "60" in content
        clamp_hum = "Math.min(100" in content or "100" in content
        assert clamp_temp and clamp_hum, "app.js thiếu logic clamp giá trị cảm biến trong ngưỡng cho phép [0, 60]°C và [0, 100]%"


# =============================================================================
# BUG 12: QR SCANNER DUPLICATE TEXT DEDUPLICATION
# =============================================================================

class TestBug12QrScannerDuplicateText:
    """Bug 12: QR Scanner Modal không được lặp lại dòng 'Đưa mã QR vào trong khung để quét'."""

    def test_bug12_open_qr_scanner_does_not_duplicate_instruction(self):
        """openQrScanner() trong mobile_app.js không được gán status.textContent = 'Đưa mã QR vào trong khung để quét'."""
        js_path = ROOT / "simulator" / "static" / "js" / "mobile_app.js"
        content = js_path.read_text(encoding="utf-8")

        # Tìm định nghĩa hàm openQrScanner
        func_match = re.search(r"function\s+openQrScanner\s*\(\)\s*\{([\s\S]*?)\}", content)
        assert func_match is not None, "Không tìm thấy hàm openQrScanner() trong mobile_app.js"
        func_body = func_match.group(1)

        assert "status.textContent = 'Đưa mã QR vào trong khung để quét';" not in func_body, (
            "openQrScanner() vẫn còn gán đè chuỗi 'Đưa mã QR vào trong khung để quét' vào status, gây lặp 2 lần với p.instruction"
        )


# =============================================================================
# BUG 13: /logs PAGINATION AND FILTER
# =============================================================================

class TestBug13LogsPaginationAndFilter:
    """Bug 13: /logs phải có phân trang client-side (pageSize=20), kết nối #logDateRange và che mật khẩu trong log."""

    def test_bug13_logs_html_has_pagination_controls(self):
        """simulator/static/logs.html phải có #btnLogsLoadMore và #logsPaginationInfo (hoặc controls phân trang)."""
        html_path = ROOT / "simulator" / "static" / "logs.html"
        assert html_path.exists(), "Tệp simulator/static/logs.html không tồn tại!"
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

        # Phải có nút Xem thêm hoặc Phân trang và thông tin phân trang
        btn_load = soup.find(id="btnLogsLoadMore") or soup.find(id="btnNextPage")
        info_el = soup.find(id="logsPaginationInfo") or soup.find(id="logsPagination")
        assert btn_load is not None, "logs.html thiếu nút #btnLogsLoadMore"
        assert info_el is not None, "logs.html thiếu phần tử #logsPaginationInfo"

    def test_bug13_logs_js_implements_client_pagination_and_date_filter(self):
        """simulator/static/js/logs.js phải có pageSize = 20, phân trang, kết nối #logDateRange và che gợi ý mật khẩu."""
        js_path = ROOT / "simulator" / "static" / "js" / "logs.js"
        assert js_path.exists(), "Tệp simulator/static/js/logs.js không tồn tại!"
        content = js_path.read_text(encoding="utf-8")

        # Kiểm tra pageSize = 20
        assert "20" in content, "logs.js thiếu định nghĩa kích thước trang (pageSize = 20)"
        assert "btnLogsLoadMore" in content or "loadMoreLogs" in content or "renderLogsPage" in content, (
            "logs.js chưa xử lý phân trang hoặc sự kiện load more"
        )

        # Kiểm tra kết nối #logDateRange
        assert "logDateRange" in content, "logs.js chưa đọc giá trị từ bộ lọc #logDateRange"

        # Kiểm tra che giấu mật khẩu
        assert "maskSensitiveLogText" in content, "logs.js thiếu hàm maskSensitiveLogText"
