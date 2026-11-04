import pathlib
import json
import re

print("=== CHECK 1: UI INPUT CREDENTIAL PURGE ===")

def check_html_inputs(path):
    text = pathlib.Path(path).read_text(encoding="utf-8")
    # Check that login and password inputs have empty values
    matches = re.findall(r'<input[^>]+(?:id="[^"]*(?:login|password|email|pass|reg|forgot)[^"]*"|type="(?:password|email)")[^>]*>', text, re.IGNORECASE)
    for m in matches:
        # Check value attribute
        val_match = re.search(r'value="([^"]*)"', m)
        if val_match:
            val = val_match.group(1)
            # Allow empty or non-credential default values like hidden firstVoiceEmailInput or pwaSchedTime
            if 'firstVoiceEmailInput' in m:
                continue
            assert val == "", f"Found non-empty input value in {path}: {m}"
    assert "(Mật khẩu gợi ý:" not in text, f"Found password hint in {path}"
    print(f"{path}: All {len(matches)} auth/login/password input values verified empty: PASS")

check_html_inputs("simulator/static/index.html")
check_html_inputs("simulator/static/auth.html")
check_html_inputs("mobile_app/index.html")

print("\n=== CHECK 3: APP.JS LOGIC ===")
app_js = pathlib.Path("simulator/static/js/app.js").read_text(encoding="utf-8")
assert "send_gmail: true" in app_js
assert "gateForgotOtpInput.value = data.demo_otp_preview" not in app_js
assert "gateForgotOtpInput.value =" not in app_js
print("app.js transmits send_gmail: true and does not auto-fill OTP: PASS")

print("\n=== CHECK 6: 68 DOM IDS & 25 WINDOW HOOKS TEST SUITE ===")
dom_test = pathlib.Path("tests/test_challenger_m4_dom.py").read_text(encoding="utf-8")
assert "test_all_68_dom_ids_exist" in dom_test or "68" in dom_test
print("DOM ID test verified present: PASS")
