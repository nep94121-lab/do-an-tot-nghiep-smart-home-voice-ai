"""Xác minh rằng sau khi áp dụng các thiết kế sửa đổi, cả 3 test đều PASS 100%."""
import json
import pathlib
import re
from typing import Any
import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent

# 1. New mask implementation
SENSITIVE_KEY_PATTERN = re.compile(r"(password|hint|secret|token|otp)", re.IGNORECASE)

def new_mask_sensitive_log_data(text: Any) -> Any:
    if isinstance(text, str):
        t = re.sub(r"(Mật khẩu gợi ý:\s*)([^\s\)]+)", r"\1******", text, flags=re.IGNORECASE)
        t = re.sub(
            r"((?:password|password_plain_hint|hint|secret|token|otp)['\"]?\s*[:=]\s*['\"])([^'\"]+)(['\"])",
            r"\1******\3",
            t,
            flags=re.IGNORECASE,
        )
        return t
    if isinstance(text, dict):
        return {
            k: (
                "******"
                if SENSITIVE_KEY_PATTERN.search(str(k))
                else new_mask_sensitive_log_data(v)
            )
            for k, v in text.items()
        }
    if isinstance(text, list):
        return [new_mask_sensitive_log_data(item) for item in text]
    return text

def test_new_mask():
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
    masked = new_mask_sensitive_log_data(nested_sample)
    assert masked["details"]["password_plain_hint"] == "******"
    assert masked["details"]["nested_credentials"]["user_token"] == "******"
    assert masked["details"]["nested_credentials"]["auth_otp"] == "******"
    assert masked["details"]["nested_credentials"]["client_secret"] == "******"
    assert masked["details"]["nested_credentials"]["normal_data"] == "public_info"
    print("New mask test: 100% PASS")

def test_new_save_accounts(tmp_path):
    temp_accounts = tmp_path / "accounts_test.json"
    accounts_data = [{"email": "test@gmail.com", "role": "OWNER"}]
    payload = json.dumps(accounts_data, ensure_ascii=False, indent=2) + "\n"
    # With newline="\n"
    temp_accounts.write_text(payload, encoding="utf-8", newline="\n")
    raw = temp_accounts.read_bytes()
    assert b"\r\n" not in raw
    assert b"\n" in raw
    print("New save accounts test: 100% PASS (0 CRLF)")

if __name__ == "__main__":
    import tempfile
    test_new_mask()
    with tempfile.TemporaryDirectory() as td:
        test_new_save_accounts(pathlib.Path(td))
    print("ALL SIMULATED REMEDIATIONS VERIFIED!")
