"""Kiểm thử thử nghiệm các bài test mới được đề xuất cho test_p4_survey1_security_auth.py."""
import json
import pathlib
import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
from simulator.server import app
from simulator.auth_3layer import get_auth_3layer_manager
import simulator.auth_3layer as a3
from simulator.api.routes_logs import mask_sensitive_log_data
from simulator.rule_engine import append_audit_log

@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)

class TestRemediationAdditions:
    def test_save_accounts_produces_zero_crlf_on_windows(self, tmp_path, monkeypatch):
        """Xác thực cơ chế lưu tài khoản _save_accounts() trên Windows đảm bảo 100% POSIX LF (0 CRLF)."""
        mgr = get_auth_3layer_manager()
        temp_accounts = tmp_path / "accounts_test.json"
        monkeypatch.setattr(a3, "ACCOUNTS_FILE", temp_accounts)

        # Lưu tài khoản qua hàm _save_accounts()
        mgr._save_accounts()

        assert temp_accounts.exists(), "Tệp lưu accounts_test.json không tồn tại!"
        raw = temp_accounts.read_bytes()
        crlf_count = raw.count(b"\r\n")
        lf_count = raw.count(b"\n")
        assert crlf_count == 0, f"Phát hiện {crlf_count} ký tự CRLF khi lưu accounts trên Windows!"
        assert lf_count > 0, "Tệp phải có ít nhất 1 dòng kết thúc bằng LF (\n)!"

    def test_logs_api_masks_nested_dictionary_sensitive_keys(self, client: TestClient):
        """API /api/logs/dashboard và mask_sensitive_log_data phải che toàn bộ khóa nhạy cảm
        khớp regex /(password|hint|secret|token|otp)/i trong từ điển đa tầng lồng nhau."""
        # 1. Kiểm tra trực tiếp mask_sensitive_log_data với cấu trúc lồng sâu
        nested_sample = {
            "actor": "admin",
            "details": {
                "password_plain_hint": "123456",
                "nested_credentials": {
                    "user_token": "secret_jwt_payload_xyz",
                    "auth_otp": "998877",
                    "client_secret": "super_secret_value",
                    "normal_data": "public_info"
                }
            }
        }
        masked = mask_sensitive_log_data(nested_sample)
        assert masked["details"]["password_plain_hint"] == "******", f"Chưa che password_plain_hint: {masked}"
        assert masked["details"]["nested_credentials"]["user_token"] == "******", f"Chưa che user_token: {masked}"
        assert masked["details"]["nested_credentials"]["auth_otp"] == "******", f"Chưa che auth_otp: {masked}"
        assert masked["details"]["nested_credentials"]["client_secret"] == "******", f"Chưa che client_secret: {masked}"
        assert masked["details"]["nested_credentials"]["normal_data"] == "public_info", "Dữ liệu bình thường bị thay đổi!"

        # 2. Kiểm tra qua luồng API thật /api/logs/dashboard
        append_audit_log(
            category="SECURITY",
            event_type="TEST_MASKING",
            user_name="admin",
            tier=1,
            summary="Kiểm toán bảo mật che dữ liệu lồng nhau",
            details={
                "password_plain_hint": "123456",
                "sub": {"otp_code": "654321", "safe": "ok"}
            }
        )
        res = client.get("/api/logs/dashboard")
        assert res.status_code == 200
        logs = res.json().get("audit_logs", [])
        found = False
        for item in logs:
            if item.get("event_type") == "TEST_MASKING":
                found = True
                dt = item.get("details", {})
                assert dt.get("password_plain_hint") == "******", f"Lộ password_plain_hint trong API: {dt}"
                assert dt.get("sub", {}).get("otp_code") == "******", f"Lộ otp_code trong API: {dt}"
                assert dt.get("sub", {}).get("safe") == "ok"
                break
        assert found, "Không tìm thấy log TEST_MASKING trong API /api/logs/dashboard"

    def test_all_simulator_data_and_modified_code_have_zero_crlf(self):
        """Xác thực 100% tệp dữ liệu text/JSON trong simulator/data/ và mã nguồn liên quan có 0 CRLF."""
        data_dir = ROOT / "simulator" / "data"
        text_extensions = {".json", ".jsonl", ".txt", ".csv"}
        data_files = [p for p in data_dir.iterdir() if p.is_file() and p.suffix.lower() in text_extensions]

        modified_code_files = [
            ROOT / "simulator" / "static" / "index.html",
            ROOT / "mobile_app" / "index.html",
            ROOT / "simulator" / "static" / "auth.html",
            ROOT / "simulator" / "static" / "js" / "app.js",
            ROOT / "simulator" / "static" / "js" / "auth.js",
            ROOT / "simulator" / "static" / "js" / "mobile_app.js",
            ROOT / "simulator" / "static" / "js" / "logs.js",
            ROOT / "simulator" / "api" / "routes_logs.py",
            ROOT / "simulator" / "auth" / "constants_and_crypto.py",
            ROOT / "simulator" / "auth_3layer.py",
            ROOT / "tests" / "test_p4_survey1_security_auth.py",
            ROOT / "tests" / "test_p3_session_rbac_concurrency.py",
        ]

        violations = {}
        for f in data_files + modified_code_files:
            raw = f.read_bytes()
            crlf = raw.count(b"\r\n")
            if crlf > 0:
                violations[str(f.relative_to(ROOT))] = crlf

        assert not violations, f"Phát hiện vi phạm CRLF tại {len(violations)} tệp: {violations}"
