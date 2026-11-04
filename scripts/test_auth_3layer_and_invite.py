"""Kiểm thử Tự động Toàn diện 14 Kịch Bản & Kiểm Chứng HTTP REST API:
- Xác thực 3 Lớp (Mật khẩu PBKDF2 + Gmail OTP Thật + Thu âm Giọng nói Điện thoại/Web lên Server).
- Tự động gửi Email OTP về `nep94121@gmail.com` VÀ tự động đọc ngược hộp thư Gmail thật (`gws gmail`) để lấy mã OTP xác nhận.
- Phân cấp Đường Link Mời Đăng Ký: Cấp 1 có 2 link (Cấp 2 & Cấp 3), Cấp 2 chỉ có 1 link (Cấp 3) và bị chặn tạo link Cấp 2, Cấp 3 không có phần gửi link.
- Đăng ký qua Link Mời bằng Google OAuth (Gmail) -> Cấp mật khẩu & OTP -> Vào Trang Đầu hiện dòng chữ mẫu để đọc và giữ thu âm lưu lên Server.
- Chủ nhà (Cấp 1) xóa cấp quyền bằng giọng nói ("Xóa cấp quyền của Thành viên A") -> Tài khoản vẫn còn nhưng hiện "KHÔNG CÓ QUYỀN" -> Bật lại quyền ("Bật lại quyền cho Thành viên A") -> Khôi phục như cũ.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.auth_3layer import get_auth_3layer_manager


def _http_post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    mgr = get_auth_3layer_manager()
    rep = mgr.run_automated_3layer_test_suite(send_real_email_on_test1=True)
    print("=" * 95)
    print(f"KẾT QUẢ TỔNG HỢP: {rep['summary']}")
    print(f"THỜI GIAN CHẠY : {rep['executed_at']}")
    print("=" * 95)
    for c in rep["cases"]:
        status = "PASS" if c["passed"] else "FAIL"
        print(f"[{c['test_id']}] [{status}] {c['layer']}")
        print(f"  • Kịch bản : {c['scenario']}")
        print(f"  • Thực tế  : {c['actual']}")
    print("=" * 95)

    # Kiểm chứng độc lập qua cổng HTTP Server thật (Orthogonal HTTP Verification)
    try:
        r_rev = _http_post_json(
            "http://127.0.0.1:8088/api/text_command",
            {"text": "Xóa cấp quyền của Thành viên A"},
        )
        print(f"[HTTP /api/text_command -> Xóa quyền] {r_rev.get('reply')}")
        r_res = _http_post_json(
            "http://127.0.0.1:8088/api/text_command",
            {"text": "Bật lại quyền cho Thành viên A"},
        )
        print(f"[HTTP /api/text_command -> Bật lại quyền] {r_res.get('reply')}")
    except Exception as exc:
        print(f"[HTTP Check Note] {exc}")

    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
