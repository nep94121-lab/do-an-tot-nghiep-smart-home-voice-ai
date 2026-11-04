import json
import re
from simulator.api.routes_logs import mask_sensitive_log_data

test_cases = [
    "Lỗi đăng nhập (Mật khẩu gợi ý: 123456)",
    '{"event": "auth_fail", "detail": "Sai mật khẩu! (Mật khẩu gợi ý: 123456 - Lớp 1)"}',
    {"detail": 'password = "secret123"', "nested": {"password_plain_hint": "GiaDinh@123", "safe": "OK"}},
    ["Mật khẩu gợi ý: abcxyz", {"foo": "bar"}]
]

for tc in test_cases:
    res = mask_sensitive_log_data(tc)
    print("RAW:", tc)
    print("MASKED:", res)
    if isinstance(res, (dict, list)):
        serialized = json.dumps(res, ensure_ascii=False)
        deserialized = json.loads(serialized)
        assert deserialized == res
    assert "123456" not in str(res), f"123456 leaked in {res}"
    assert "secret123" not in str(res), f"secret123 leaked in {res}"
    assert "GiaDinh@123" not in str(res), f"GiaDinh@123 leaked in {res}"

print("ALL ACCENTED MASKING TESTS PASSED!")
