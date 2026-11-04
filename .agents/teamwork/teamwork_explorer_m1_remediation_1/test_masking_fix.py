import re
import json

SENSITIVE_KEY_PATTERN = re.compile(r"(password|hint|secret|token|otp|mat_khau)", re.IGNORECASE)

def mask_sensitive_log_data(text):
    if isinstance(text, str):
        t = re.sub(r"(Mật khẩu gợi ý:\s*)([^\s\)]+)", r"\1******", text, flags=re.IGNORECASE)
        t = re.sub(
            r"((?:password|password_plain_hint|secret|token|otp)['\"]?\s*[:=]\s*['\"])([^'\"]+)(['\"])",
            r"\1******\3",
            t,
            flags=re.IGNORECASE,
        )
        return t
    if isinstance(text, dict):
        return {
            k: ("******" if SENSITIVE_KEY_PATTERN.search(str(k)) else mask_sensitive_log_data(v))
            for k, v in text.items()
        }
    if isinstance(text, list):
        return [mask_sensitive_log_data(item) for item in text]
    return text

sample = {
    "user": "nep94121@gmail.com",
    "password": "SuperPass2026",
    "details": {
        "password_plain_hint": "123456",
        "otp_code": "987654",
        "session_token": "abc-xyz-token",
        "safe_info": "Device Living Room Light turned ON",
    },
    "raw_log": "User registered with password: my_raw_pwd and Mật khẩu gợi ý: 123456",
}

masked = mask_sensitive_log_data(sample)
print(json.dumps(masked, indent=2, ensure_ascii=False))

# Assertions
assert masked["password"] == "******"
assert masked["details"]["password_plain_hint"] == "******"
assert masked["details"]["otp_code"] == "******"
assert masked["details"]["session_token"] == "******"
assert masked["details"]["safe_info"] == "Device Living Room Light turned ON"
assert "123456" not in masked["raw_log"]
print("ALL ASSERTIONS PASSED!")
