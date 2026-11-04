import re
from typing import Any

# Worker 1's function as implemented in simulator/api/routes_logs.py
def mask_sensitive_log_data(text: Any) -> Any:
    if isinstance(text, str):
        t = re.sub(r"(Mật khẩu gợi ý:\s*)([^\s\)]+)", r"\1******", text, flags=re.IGNORECASE)
        t = re.sub(r"((?:password|password_plain_hint)['\"]?\s*[:=]\s*['\"])([^'\"]+)(['\"])", r"\1******\3", t, flags=re.IGNORECASE)
        return t
    if isinstance(text, dict):
        return {k: mask_sensitive_log_data(v) for k, v in text.items()}
    if isinstance(text, list):
        return [mask_sensitive_log_data(item) for item in text]
    return text

# Adversarial test case 1: structured log details containing dictionary key 'password' or 'password_plain_hint'
dict_log = {
    "user": "nep",
    "password": "supersecretpassword",
    "details": {
        "password_plain_hint": "123456",
        "nested_note": "Mật khẩu gợi ý: 123456"
    }
}

masked = mask_sensitive_log_data(dict_log)
print("Masked result:", masked)

leak_detected = False
if masked.get("password") == "supersecretpassword":
    print("VULNERABILITY: Dict key 'password' value was NOT masked!")
    leak_detected = True

if masked["details"].get("password_plain_hint") == "123456":
    print("VULNERABILITY: Dict key 'password_plain_hint' value was NOT masked!")
    leak_detected = True

if "123456" in masked["details"].get("nested_note"):
    print("VULNERABILITY: String hint was NOT masked!")
    leak_detected = True
else:
    print("PASS: String hint was properly masked.")

print(f"Overall leak detected: {leak_detected}")
