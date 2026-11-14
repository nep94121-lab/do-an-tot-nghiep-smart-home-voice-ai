"""Unit & Integration Tests for Milestone M6:
- 5 Error Pages (offline.html, 404.html, 500.html, qr_expired.html, 403.html)
- Service Worker (sw.js)
- FastAPI 404 Content-Negotiation Handler and Static Error Routes
- Vercel Configuration (vercel.json)
"""

import json
import pathlib
import subprocess
import pytest
from starlette.testclient import TestClient

from simulator.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "simulator" / "static"
VERCEL_JSON = ROOT / "vercel.json"


@pytest.fixture(scope="module")
def client():
    """Tạo TestClient tái sử dụng cho test suite."""
    return TestClient(app)


# =============================================================================
# 1. KIỂM TRA SỰ TỒN TẠI VÀ NỘI DUNG CÁC TRANG LỖI TĨNH & SW
# =============================================================================

class TestStaticFilesExistenceAndContent:
    """Kiểm tra 5 file HTML lỗi và file sw.js tồn tại thực tế và đúng chuẩn thiết kế."""

    def test_offline_html_exists_and_valid(self):
        file_path = STATIC_DIR / "offline.html"
        assert file_path.exists(), f"Thiếu file: {file_path}"
        content = file_path.read_text(encoding="utf-8")
        assert "<title>Mất kết nối · Nhà thông minh</title>" in content
        assert "Mất kết nối tới Máy chủ Nhà thông minh" in content
        assert "Thử kết nối lại" in content
        assert "Chuyển sang Server Dự phòng" in content
        assert "Trạng thái mạch" in content
        assert "svg class=\"icon\"" in content

    def test_404_html_exists_and_valid(self):
        file_path = STATIC_DIR / "404.html"
        assert file_path.exists(), f"Thiếu file: {file_path}"
        content = file_path.read_text(encoding="utf-8")
        assert "<title>Không tìm thấy trang · Nhà thông minh</title>" in content
        assert "Không tìm thấy trang" in content
        assert "Về Trang chủ" in content
        assert "Mở Ứng dụng Điện thoại" in content
        assert "LỖI 404" in content

    def test_500_html_exists_and_valid(self):
        file_path = STATIC_DIR / "500.html"
        assert file_path.exists(), f"Thiếu file: {file_path}"
        content = file_path.read_text(encoding="utf-8")
        assert "<title>Hệ thống đang bận · Nhà thông minh</title>" in content
        assert "Hệ thống đang bận" in content
        assert "Tải lại trang" in content
        assert "Về Trang chủ" in content
        assert "LỖI 500 / 503" in content

    def test_qr_expired_html_exists_and_valid(self):
        file_path = STATIC_DIR / "qr_expired.html"
        assert file_path.exists(), f"Thiếu file: {file_path}"
        content = file_path.read_text(encoding="utf-8")
        assert "<title>Mã QR hết hạn · Nhà thông minh</title>" in content
        assert "Mã QR đã hết hạn" in content
        assert "Quét mã mới" in content
        assert "Nhập mã mới" in content
        assert "LỜI MỜI KHÔNG CÒN HIỆU LỰC" in content

    def test_403_html_exists_and_valid(self):
        file_path = STATIC_DIR / "403.html"
        assert file_path.exists(), f"Thiếu file: {file_path}"
        content = file_path.read_text(encoding="utf-8")
        assert "<title>Không đủ quyền · Nhà thông minh</title>" in content
        assert "Không đủ quyền truy cập" in content
        assert "Quay về Nhà" in content
        assert "Đăng nhập tài khoản khác" in content
        assert "Khách · Cấp 3" in content
        assert "LỖI 403" in content

    def test_sw_js_exists_and_valid(self):
        file_path = STATIC_DIR / "sw.js"
        assert file_path.exists(), f"Thiếu file: {file_path}"
        content = file_path.read_text(encoding="utf-8")
        assert "smarthome-cache-v2" in content
        assert "install" in content
        assert "activate" in content
        assert "fetch" in content
        assert "offline.html" in content
        assert "/api/" in content
        assert "/ws" in content

        # Kiểm tra cú pháp JavaScript với node --check nếu môi trường có node
        try:
            res = subprocess.run(
                ["node", "--check", str(file_path)],
                capture_output=True,
                text=True,
                timeout=5
            )
            assert res.returncode == 0, f"sw.js syntax error: {res.stderr}"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass


# =============================================================================
# 2. KIỂM TRA ĐỊNH TUYẾN SERVER VÀ CONTENT NEGOTIATION 404
# =============================================================================

class TestFastAPIServerRoutesAndNegotiation:
    """Kiểm tra các route mới và cơ chế content negotiation trong server.py."""

    def test_sw_js_served_with_allowed_header(self, client):
        resp = client.get("/sw.js")
        assert resp.status_code == 200
        assert "javascript" in resp.headers.get("content-type", "").lower()
        assert resp.headers.get("service-worker-allowed") == "/"
        assert "smarthome-cache-v2" in resp.text

    def test_offline_routes(self, client):
        for path in ["/offline", "/offline.html"]:
            resp = client.get(path)
            assert resp.status_code == 200
            assert "text/html" in resp.headers.get("content-type", "")
            assert "Mất kết nối tới Máy chủ Nhà thông minh" in resp.text

    def test_404_routes_explicit(self, client):
        for path in ["/404", "/404.html"]:
            resp = client.get(path)
            assert resp.status_code == 404
            assert "text/html" in resp.headers.get("content-type", "")
            assert "Không tìm thấy trang" in resp.text

    def test_500_routes_explicit(self, client):
        for path in ["/500", "/500.html"]:
            resp = client.get(path)
            assert resp.status_code == 500
            assert "text/html" in resp.headers.get("content-type", "")
            assert "Hệ thống đang bận" in resp.text

    def test_qr_expired_routes(self, client):
        for path in ["/qr_expired", "/qr-expired", "/qr_expired.html"]:
            resp = client.get(path)
            assert resp.status_code == 200
            assert "text/html" in resp.headers.get("content-type", "")
            assert "Mã QR đã hết hạn" in resp.text

    def test_403_routes_explicit(self, client):
        for path in ["/403", "/403.html"]:
            resp = client.get(path)
            assert resp.status_code == 403
            assert "text/html" in resp.headers.get("content-type", "")
            assert "Không đủ quyền truy cập" in resp.text

    def test_404_content_negotiation_browser_navigation(self, client):
        """Khi trình duyệt (Accept: text/html) truy cập route không tồn tại, trả về 404.html."""
        headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
        resp = client.get("/random_unknown_nonexistent_page", headers=headers)
        assert resp.status_code == 404
        assert "text/html" in resp.headers.get("content-type", "")
        assert "Không tìm thấy trang" in resp.text
        assert "Về Trang chủ" in resp.text

    def test_404_content_negotiation_api_request(self, client):
        """Khi gọi /api/* (kể cả Accept: text/html), bắt buộc phải trả về JSON 404."""
        headers = {"Accept": "text/html"}
        resp = client.get("/api/unknown_endpoint_xyz", headers=headers)
        assert resp.status_code == 404
        assert "application/json" in resp.headers.get("content-type", "")
        data = resp.json()
        assert "detail" in data
        assert data["detail"] == "Not Found"

    def test_404_content_negotiation_json_client(self, client):
        """Khi client gửi Accept: application/json, route không tồn tại trả về JSON 404."""
        headers = {"Accept": "application/json"}
        resp = client.get("/some_page_without_html_accept", headers=headers)
        assert resp.status_code == 404
        assert "application/json" in resp.headers.get("content-type", "")
        data = resp.json()
        assert "detail" in data
        assert data["detail"] == "Not Found"

    def test_device_api_404_preserved(self, client):
        """Gọi API thiết bị không tồn tại trả về JSON 404, không bị nuốt bởi custom handler."""
        resp = client.get("/api/devices/nonexistent_device_id_888")
        assert resp.status_code == 404
        assert "application/json" in resp.headers.get("content-type", "")
        data = resp.json()
        assert "detail" in data


# =============================================================================
# 3. KIỂM TRA CẤU HÌNH VERCEL (VERCEL.JSON)
# =============================================================================

class TestVercelConfiguration:
    """Kiểm tra tính hợp lệ của vercel.json cho các route mới và headers."""

    def test_vercel_json_syntax_and_routes(self):
        assert VERCEL_JSON.exists(), f"Thiếu file: {VERCEL_JSON}"
        config = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))
        assert config.get("version") == 2
        routes = config.get("routes", [])

        # Kiểm tra có route sw.js
        sw_route = next((r for r in routes if "sw" in r.get("src", "")), None)
        assert sw_route is not None, "Thiếu route cho /sw.js trong vercel.json"
        assert "sw.js" in sw_route.get("dest", "")

        # Kiểm tra headers cho sw.js
        headers = config.get("headers", [])
        sw_header = next((h for h in headers if "sw.js" in h.get("source", "")), None)
        assert sw_header is not None, "Thiếu headers cho /sw.js trong vercel.json"
        header_keys = {item["key"].lower(): item["value"] for item in sw_header.get("headers", [])}
        assert header_keys.get("service-worker-allowed") == "/"

        # Kiểm tra các routes cho offline, 404, 500, qr_expired, 403
        destinations = [r.get("dest", "") for r in routes]
        assert any("offline.html" in d for d in destinations), "Thiếu route offline trong vercel.json"
        assert any("404.html" in d for d in destinations), "Thiếu route 404 trong vercel.json"
        assert any("500.html" in d for d in destinations), "Thiếu route 500 trong vercel.json"
        assert any("qr_expired.html" in d for d in destinations), "Thiếu route qr_expired trong vercel.json"
        assert any("403.html" in d for d in destinations), "Thiếu route 403 trong vercel.json"
