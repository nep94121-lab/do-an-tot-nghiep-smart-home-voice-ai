import re
from typing import Any

SENSITIVE_KEY_PATTERN = re.compile(r"(password|hint|secret|token|otp)", re.IGNORECASE)

def mask_sensitive_log_data(text: Any) -> Any:
    """Che gợi ý mật khẩu và thông tin xác thực nhạy cảm trong log hiển thị."""
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
                else mask_sensitive_log_data(v)
            )
            for k, v in text.items()
        }
    if isinstance(text, list):
        return [mask_sensitive_log_data(item) for item in text]
    return text

if __name__ == "__main__":
    sample1 = {"details": {"password_plain_hint": "123456"}}
    res1 = mask_sensitive_log_data(sample1)
    print("Sample 1:", res1)
    assert res1 == {"details": {"password_plain_hint": "******"}}, f"Failed sample1: {res1}"

    sample2 = {"details": {"nested": {"deep": {"user_token": "secret_jwt_token", "normal": "hello"}}}}
    res2 = mask_sensitive_log_data(sample2)
    print("Sample 2:", res2)
    assert res2 == {"details": {"nested": {"deep": {"user_token": "******", "normal": "hello"}}}}, f"Failed sample2: {res2}"

    sample3 = {"otp_code": "998877", "safe_key": 123}
    res3 = mask_sensitive_log_data(sample3)
    print("Sample 3:", res3)
    assert res3 == {"otp_code": "******", "safe_key": 123}, f"Failed sample3: {res3}"

    sample4 = 'User entered password="super_secret" and otp=\'123456\''
    res4 = mask_sensitive_log_data(sample4)
    print("Sample 4:", res4)
    assert res4 == 'User entered password="******" and otp=\'******\'', f"Failed sample4: {res4}"

    # Also test mixed lists and nested structures
    sample5 = {
        "event": "Login attempt",
        "actor": "admin",
        "details": {
            "attempts": [
                {"timestamp": 123, "secret_key": "topsecret", "status": "failed"},
                {"timestamp": 124, "token": "xyz987", "status": "ok"}
            ],
            "password_plain_hint": "123456",
            "metadata": {"hint_question": "pet?", "hint_answer": "cat"}
        }
    }
    res5 = mask_sensitive_log_data(sample5)
    print("Sample 5:", res5)
    assert res5["details"]["password_plain_hint"] == "******"
    assert res5["details"]["metadata"]["hint_question"] == "******"
    assert res5["details"]["metadata"]["hint_answer"] == "******"
    assert res5["details"]["attempts"][0]["secret_key"] == "******"
    assert res5["details"]["attempts"][1]["token"] == "******"

    print("ALL MASKING TESTS PASSED!")
