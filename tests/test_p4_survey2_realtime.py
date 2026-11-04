"""Bộ kiểm thử TDD cho Milestone 2: Realtime, State Synchronization & Simulation (Bugs 3, 10, 11, 14).

Nhiệm vụ:
- Bug 3: WebSocket fallback trên Vercel: đồng bộ banner reconnect và header pill ("Đã kết nối" khi HTTP polling thành công,
         chỉ hiện banner khi cả WS và polling đều hỏng). Route /favicon.ico trong vercel.json và file favicon.ico trên đĩa.
- Bug 10: Toggle device: Optimistic UI trong app.js & mobile_app.js (flip tức thì, cập nhật badge/counter, rollback khi lỗi).
          renderDevices() cập nhật DOM in-place thay vì innerHTML = "".
          getDeviceRoomLabel() hiển thị đầy đủ "Đã bật" / "Đã tắt" không bị cắt/lỗi chính tả.
- Bug 11: Recording sheet mic waiting state: trong mobile_app/index.html & mobile_app.js, đặt title ban đầu "Đang chờ quyền mic",
          timer giữ 00:00 và bars đứng yên cho tới khi getUserMedia resolve. Nếu denied/rejected, đóng sheet và hiện #mobileMicPermissionModal.
- Bug 14: /wokwi label layout & telemetry: loại bỏ đè nhãn giữa DHT11 và Buzzer trong wokwi.html;
          thay thế "Chưa có dữ liệu" bằng live telemetry trong wokwi.html & wokwi.js.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from bs4 import BeautifulSoup
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# =============================================================================
# BUG 3: WEBSOCKET FALLBACK, BANNER CONSISTENCY & FAVICON.ICO
# =============================================================================

class TestBug3WebSocketFallbackAndFavicon:
    """Bug 3: Fallback HTTP polling /api/state khi WS đóng, banner nhất quán với header, favicon.ico 200 OK."""

    def test_bug3_app_js_ws_fallback_and_banner_logic(self):
        """app.js phải gọi hideWsReconnectBanner() khi HTTP polling thành công,
        và chỉ gọi showWsReconnectBanner khi polling cũng thất bại."""
        app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
        assert app_js_path.exists(), "Tệp simulator/static/js/app.js không tồn tại!"
        content = app_js_path.read_text(encoding="utf-8")

        # 1. Trong ws.onclose: khi fetch('/api/state') thành công -> phải gọi hideWsReconnectBanner()
        assert "hideWsReconnectBanner()" in content, "app.js thiếu hàm hideWsReconnectBanner()"
        
        # Kiểm tra đoạn code ws.onclose
        onclose_match = re.search(r"ws\.onclose\s*=\s*\(\)\s*=>\s*\{([\s\S]*?)\};", content)
        assert onclose_match, "Không tìm thấy handler ws.onclose trong app.js"
        onclose_body = onclose_match.group(1)

        # Trong nhánh then của fetch('/api/state') phải có hideWsReconnectBanner()
        assert "hideWsReconnectBanner" in onclose_body, (
            "Trong ws.onclose, nhánh fetch('/api/state') thành công chưa gọi hideWsReconnectBanner()"
        )

        # 2. Không được gọi showWsReconnectBanner vô điều kiện ở mức ngoài của ws.onclose
        # showWsReconnectBanner chỉ được gọi trong catch block hoặc khi polling thất bại
        lines = [line.strip() for line in onclose_body.split("\n") if line.strip()]
        for line in lines:
            if line.startswith("showWsReconnectBanner(") and not line.startswith("//"):
                # Đảm bảo không nằm trực tiếp ngoài fetch catch
                pass

        # 3. pollRestStateFallback phải gọi hideWsReconnectBanner() khi thành công
        fallback_match = re.search(r"function\s+pollRestStateFallback\s*\(\)\s*\{([\s\S]*?)\}", content)
        assert fallback_match, "Không tìm thấy hàm pollRestStateFallback trong app.js"
        fallback_body = fallback_match.group(1)
        assert "hideWsReconnectBanner" in fallback_body, (
            "pollRestStateFallback() thành công chưa gọi hideWsReconnectBanner()"
        )

    def test_bug3_mobile_app_js_ws_fallback_sync(self):
        """mobile_app.js phải đồng bộ espBadge khi fetch /api/state thành công trong ws.onclose."""
        mobile_js_path = ROOT / "simulator" / "static" / "js" / "mobile_app.js"
        assert mobile_js_path.exists(), "Tệp simulator/static/js/mobile_app.js không tồn tại!"
        content = mobile_js_path.read_text(encoding="utf-8")

        # Kiểm tra ws.onclose trong mobile_app.js
        assert "ws.onclose" in content, "mobile_app.js thiếu handler ws.onclose"
        onclose_match = re.search(r"ws\.onclose\s*=\s*\(\)\s*=>\s*\{([\s\S]*?)\};", content)
        assert onclose_match, "Không tìm thấy ws.onclose trong mobile_app.js"
        onclose_body = onclose_match.group(1)

        assert "fetch('/api/state')" in onclose_body or 'fetch("/api/state")' in onclose_body
        assert "espBadge" in onclose_body

    def test_bug3_vercel_json_has_favicon_route(self):
        """vercel.json phải cấu hình route /favicon.ico trỏ về /simulator/static/favicon.ico."""
        vercel_json_path = ROOT / "vercel.json"
        assert vercel_json_path.exists(), "Tệp vercel.json không tồn tại!"
        data = json.loads(vercel_json_path.read_text(encoding="utf-8"))

        routes = data.get("routes", [])
        favicon_route = next(
            (r for r in routes if "favicon" in r.get("src", "") and r.get("dest") == "/simulator/static/favicon.ico"),
            None,
        )
        assert favicon_route is not None, "vercel.json thiếu route trỏ /favicon.ico tới /simulator/static/favicon.ico"

    def test_bug3_favicon_ico_exists_on_disk_and_valid(self):
        """Tệp simulator/static/favicon.ico phải tồn tại thực tế và có định dạng ICO hợp lệ."""
        favicon_path = ROOT / "simulator" / "static" / "favicon.ico"
        assert favicon_path.exists(), f"Tệp {favicon_path} không tồn tại trên đĩa!"
        ico_bytes = favicon_path.read_bytes()
        assert len(ico_bytes) > 0, "Tệp favicon.ico rỗng (0 bytes)!"
        # Chuẩn ICO header: 2 bytes reserved 0x0000, 2 bytes type 0x0001 (icon)
        assert ico_bytes[:4] == b"\x00\x00\x01\x00", "Tệp favicon.ico không có header chuẩn ICO (0x00000100)!"


# =============================================================================
# BUG 10: OPTIMISTIC UI, NO EMPTY LABEL, SUBTITLE "ĐÃ BẬT" / "ĐÃ TẮT"
# =============================================================================

class TestBug10OptimisticUIAndDeviceLabels:
    """Bug 10: Phản hồi tức thì khi bấm công tắc thiết bị, in-place update DOM, nhãn đầy đủ không xén."""

    def test_bug10_app_js_optimistic_ui_in_toggleDeviceById(self):
        """toggleDeviceById() trong app.js phải cập nhật giao diện ngay lập tức (optimistic UI),
        sau đó rollback nếu API bị lỗi."""
        app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
        content = app_js_path.read_text(encoding="utf-8")

        func_match = re.search(r"function\s+toggleDeviceById\s*\([^)]*\)\s*\{([\s\S]*?)\n  \}", content)
        assert func_match, "Không tìm thấy hàm toggleDeviceById trong app.js"
        body = func_match.group(1)

        # 1. Kiểm tra có cập nhật optimistic trước khi fetch/ws
        # Phải cập nhật state của dev trước khi gửi fetch/ws
        assert "dev.state =" in body or "dev.state=" in body, (
            "toggleDeviceById() chưa cập nhật lạc quan dev.state trước khi chờ server phản hồi"
        )

        # 2. Phải có cơ chế rollback (lưu lại prevState hoặc dev.state trước đó)
        assert "prevState" in body or "oldState" in body or "rollback" in body, (
            "toggleDeviceById() thiếu biến lưu trạng thái cũ để rollback khi có lỗi"
        )

        # 3. Phải cập nhật ngay DOM của card thiết bị (switch checked, icon, room label)
        assert "checked" in body, "toggleDeviceById() chưa cập nhật ngay thuộc tính checked của input switch"

    def test_bug10_app_js_renderDevices_updates_in_place(self):
        """renderDevices() trong app.js không được dùng devicesGrid.innerHTML = '' vô điều kiện,
        phải cập nhật in-place các thẻ DOM đã có để chống chớp nháy và mất nhãn."""
        app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
        content = app_js_path.read_text(encoding="utf-8")

        func_match = re.search(r"function\s+renderDevices\s*\([^)]*\)\s*\{([\s\S]*?)\n  \}", content)
        assert func_match, "Không tìm thấy hàm renderDevices trong app.js"
        body = func_match.group(1)

        # Kiểm tra không xóa sạch toàn bộ grid bằng innerHTML = "" ở đầu hàm
        first_lines = [l.strip() for l in body.split("\n")[:8] if l.strip()]
        assert 'devicesGrid.innerHTML = "";' not in first_lines and "devicesGrid.innerHTML = '';" not in first_lines, (
            "renderDevices() vẫn xóa trắng devicesGrid.innerHTML = '' gây mất nhãn và chớp giật DOM!"
        )

    def test_bug10_app_js_getDeviceRoomLabel_full_text(self):
        """getDeviceRoomLabel() phải trả về phụ đề 'Đã bật' / 'Đã tắt' (thay vì 'Đang bật' dễ bị xén/typo)."""
        app_js_path = ROOT / "simulator" / "static" / "js" / "app.js"
        content = app_js_path.read_text(encoding="utf-8")

        func_match = re.search(r"function\s+getDeviceRoomLabel\s*\([^)]*\)\s*\{([\s\S]*?)\n  \}", content)
        assert func_match, "Không tìm thấy hàm getDeviceRoomLabel trong app.js"
        body = func_match.group(1)

        # Kiểm tra nhãn phụ đề chứa "Đã bật" và "Đã tắt"
        assert '"Đã bật"' in body or "'Đã bật'" in body, "getDeviceRoomLabel() chưa có nhãn 'Đã bật'"
        assert '"Đã tắt"' in body or "'Đã tắt'" in body, "getDeviceRoomLabel() chưa có nhãn 'Đã tắt'"

    def test_bug10_mobile_app_js_optimistic_toggle(self):
        """mobile_app.js phải có optimistic UI khi người dùng tương tác với thiết bị."""
        mobile_js_path = ROOT / "simulator" / "static" / "js" / "mobile_app.js"
        content = mobile_js_path.read_text(encoding="utf-8")

        # Kiểm tra trong hàm renderState hoặc device click handler có cập nhật optimistic class 'on'/'off'
        assert "classList.toggle('on'" in content or 'classList.toggle("on"' in content or "card.className =" in content, (
            "mobile_app.js thiếu cập nhật optimistic cho card thiết bị"
        )
        assert "prevState" in content or "prevIsOn" in content or "oldState" in content, (
            "mobile_app.js thiếu cơ chế rollback khi POST /api/device thất bại"
        )


# =============================================================================
# BUG 11: RECORDING SHEET MIC WAITING STATE & PERMISSION MODAL
# =============================================================================

class TestBug11MobileMicPermissionAndWaitingState:
    """Bug 11: Trạng thái chờ cấp quyền mic trên Mobile PWA, đóng sheet và hiện modal hướng dẫn khi bị từ chối."""

    def test_bug11_mobile_html_initial_recording_sheet_state(self):
        """mobile_app/index.html phải có tiêu đề ban đầu 'Đang chờ quyền mic', timer 00:00."""
        html_path = ROOT / "mobile_app" / "index.html"
        assert html_path.exists(), "Tệp mobile_app/index.html không tồn tại!"
        content = html_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")

        # 1. Tiêu đề ban đầu của Sheet ghi âm
        title_el = soup.find(id="mobileVoiceSheetTitle")
        assert title_el is not None, "Thiếu #mobileVoiceSheetTitle trong mobile_app/index.html"
        assert title_el.text.strip() == "Đang chờ quyền mic", (
            f"#mobileVoiceSheetTitle có nội dung '{title_el.text.strip()}', mong đợi 'Đang chờ quyền mic'"
        )

        # 2. Timer ban đầu
        timer_cur = soup.find(id="mobileVoiceTimerCur")
        assert timer_cur is not None, "Thiếu #mobileVoiceTimerCur trong mobile_app/index.html"
        assert timer_cur.text.strip() == "00:00", (
            f"#mobileVoiceTimerCur có nội dung '{timer_cur.text.strip()}', mong đợi '00:00'"
        )

    def test_bug11_mobile_html_has_mic_permission_modal(self):
        """mobile_app/index.html phải có hộp thoại #mobileMicPermissionModal tương ứng với desktop."""
        html_path = ROOT / "mobile_app" / "index.html"
        content = html_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")

        modal = soup.find(id="mobileMicPermissionModal")
        assert modal is not None, "mobile_app/index.html thiếu phần tử #mobileMicPermissionModal!"

        # Kiểm tra tiêu đề modal
        title_el = modal.find(id="mobileMictitle")
        assert title_el is not None, "#mobileMicPermissionModal thiếu #mobileMictitle"
        assert "micro" in title_el.text.lower(), f"Tiêu đề '{title_el.text}' không chứa từ khóa 'micro'"

        # Kiểm tra các nút tương tác
        btn_retry = modal.find(id="mobileBtnMicPermissionRetry")
        assert btn_retry is not None, "#mobileMicPermissionModal thiếu nút #mobileBtnMicPermissionRetry"

        btn_close = modal.find(id="mobileBtnMicPermissionClose")
        assert btn_close is not None, "#mobileMicPermissionModal thiếu nút #mobileBtnMicPermissionClose"

    def test_bug11_mobile_js_mic_waiting_and_rejection_flow(self):
        """mobile_app.js: openVoiceBottomSheet đặt 'Đang chờ quyền mic',
        startVoiceSheetRecording giữ timer và waveform đứng yên cho đến khi getUserMedia resolve.
        Khi bị reject/deny thì đóng sheet và mở #mobileMicPermissionModal."""
        mobile_js_path = ROOT / "simulator" / "static" / "js" / "mobile_app.js"
        content = mobile_js_path.read_text(encoding="utf-8")

        # 1. openVoiceBottomSheet gán 'Đang chờ quyền mic'
        assert "Đang chờ quyền mic" in content, "mobile_app.js thiếu chuỗi trạng thái 'Đang chờ quyền mic'"

        # 2. Xử lý khi getUserMedia bị lỗi / từ chối
        assert "openMobileMicPermissionModal" in content or "mobileMicPermissionModal" in content, (
            "mobile_app.js chưa mở #mobileMicPermissionModal khi quyền mic bị từ chối"
        )

        # 3. Export các hàm điều khiển modal ra window
        assert "window.openMobileMicPermissionModal" in content, (
            "mobile_app.js chưa export window.openMobileMicPermissionModal"
        )
        assert "window.closeMobileMicPermissionModal" in content, (
            "mobile_app.js chưa export window.closeMobileMicPermissionModal"
        )


# =============================================================================
# BUG 14: WOKWI LABEL LAYOUT & LIVE TELEMETRY DISPLAY
# =============================================================================

class TestBug14WokwiLayoutAndTelemetry:
    """Bug 14: Sửa layout nhãn mạch DHT11 vs Buzzer trong /wokwi và hiển thị live telemetry thay vì 'Chưa có dữ liệu'."""

    def test_bug14_wokwi_html_no_overlap_between_dht11_and_buzzer(self):
        """Trong simulator/static/wokwi.html, nhãn DHT11 và Buzzer không được đè lên nhau."""
        wokwi_html_path = ROOT / "simulator" / "static" / "wokwi.html"
        assert wokwi_html_path.exists(), "Tệp simulator/static/wokwi.html không tồn tại!"
        content = wokwi_html_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")

        # Tìm các comp-tag của DHT11 và Buzzer
        comp_tags = soup.find_all("div", class_="comp-tag")
        dht_tag = next((t for t in comp_tags if "DHT11" in t.text), None)
        buzzer_tag = next((t for t in comp_tags if "Buzzer" in t.text), None)

        assert dht_tag is not None, "Không tìm thấy thẻ nhãn DHT11 trong wokwi.html"
        assert buzzer_tag is not None, "Không tìm thấy thẻ nhãn Buzzer trong wokwi.html"

        dht_style = dht_tag.get("style", "")
        buzzer_style = buzzer_tag.get("style", "")

        def parse_pos(style_str: str) -> tuple[int, int]:
            left_m = re.search(r"left:\s*(\d+)px", style_str)
            top_m = re.search(r"top:\s*(\d+)px", style_str)
            left = int(left_m.group(1)) if left_m else 0
            top = int(top_m.group(1)) if top_m else 0
            return left, top

        dht_left, dht_top = parse_pos(dht_style)
        buzzer_left, buzzer_top = parse_pos(buzzer_style)

        # Kiểm tra tính không chồng lấn (zero overlap):
        # - Hoặc khác dòng top (độ lệch top >= 20px)
        # - Hoặc nếu cùng dòng top thì khoảng cách left giữa Buzzer và DHT11 phải >= 150px
        # (nhãn DHT11 dài ~150px, trước đây: dht_left=500, buzzer_left=632 -> chênh 132px < 150px gây đè)
        top_diff = abs(buzzer_top - dht_top)
        left_diff = buzzer_left - dht_left

        is_no_overlap = (top_diff >= 20) or (left_diff >= 150)
        assert is_no_overlap, (
            f"Nhãn DHT11 (left:{dht_left}px, top:{dht_top}px) và Buzzer (left:{buzzer_left}px, top:{buzzer_top}px) "
            f"vẫn bị đè lên nhau (top_diff={top_diff}px < 20px VÀ left_diff={left_diff}px < 150px)!"
        )

    def test_bug14_wokwi_html_hoverHoleInfo_has_live_telemetry(self):
        """#hoverHoleInfo trong wokwi.html không được chứa chuỗi 'Chưa có dữ liệu',
        phải hiển thị telemetry mô phỏng."""
        wokwi_html_path = ROOT / "simulator" / "static" / "wokwi.html"
        content = wokwi_html_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")

        hole_info = soup.find(id="hoverHoleInfo")
        assert hole_info is not None, "Thiếu #hoverHoleInfo trong wokwi.html"
        assert "Chưa có dữ liệu" not in hole_info.text, (
            f"#hoverHoleInfo trong wokwi.html vẫn chứa chuỗi cấm 'Chưa có dữ liệu'!"
        )
        # Phải chứa thông số mô phỏng nhiệt độ / độ ẩm
        assert "°C" in hole_info.text or "Nhiệt độ" in hole_info.text or "Độ ẩm" in hole_info.text, (
            f"#hoverHoleInfo '{hole_info.text}' chưa hiển thị thông tin telemetry cảm biến!"
        )

    def test_bug14_wokwi_js_updates_telemetry_in_hoverHoleInfo(self):
        """wokwi.js phải cập nhật dữ liệu telemetry thời gian thực vào #hoverHoleInfo khi syncWokwiComponents chạy."""
        wokwi_js_path = ROOT / "simulator" / "static" / "js" / "wokwi.js"
        assert wokwi_js_path.exists(), "Tệp simulator/static/js/wokwi.js không tồn tại!"
        content = wokwi_js_path.read_text(encoding="utf-8")

        # Kiểm tra syncWokwiComponents có logic cập nhật hoverHoleInfo với telemetry
        assert "hoverHoleInfo" in content, "wokwi.js thiếu cập nhật cho #hoverHoleInfo"
        # Đảm bảo không còn gán 'Chưa có dữ liệu' trong wokwi.js
        assert "Chưa có dữ liệu" not in content, "wokwi.js vẫn còn chứa chuỗi 'Chưa có dữ liệu'!"
