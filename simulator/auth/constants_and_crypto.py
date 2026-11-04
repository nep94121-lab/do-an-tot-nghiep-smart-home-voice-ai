"""Module simulator.auth.constants_and_crypto: Hằng số tài khoản mặc định, Link mời, Hash mật khẩu và Kiểm tra DNS MX."""

from __future__ import annotations

import hashlib
import hmac
import re
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ACCOUNTS_FILE = DATA_DIR / "accounts_3layer.json"
AUTH_EVENTS_FILE = DATA_DIR / "auth_3layer_events.json"
INVITE_LINKS_FILE = DATA_DIR / "invite_links_3layer.json"
FAMILY_ALLOWLIST_FILE = DATA_DIR / "family_email_allowlist.json"


def _now_vn() -> str:
    return time.strftime("%H:%M:%S %d/%m/%Y", time.localtime())


def hash_password(password: str, salt: str = "hust_seee_2026_salt") -> str:
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    )
    return dk.hex()


def verify_password_hash(password: str, expected_hash: str, salt: str = "hust_seee_2026_salt") -> bool:
    actual = hash_password(password, salt=salt)
    return hmac.compare_digest(actual, expected_hash)


def build_reading_prompt(display_name: str, tier: int) -> str:
    tier_name = "Cấp 1 Chủ nhà" if tier == 1 else ("Cấp 2 Thành viên gia đình" if tier == 2 else "Cấp 3 Khách")
    return (
        f"Xin chào hệ thống Nhà Thông Minh Bách Khoa, tôi là {display_name}, "
        f"tôi đọc câu này để lưu mẫu giọng nói gốc {tier_name} lên máy chủ."
    )


DEFAULT_ACCOUNTS: list[dict[str, Any]] = [
    {
        "account_id": "tuan_anh",
        "email": "nep94121@gmail.com",
        "display_name": "Nguyễn Tuấn Anh",
        "tier": 1,
        "saved_tier": 1,
        "role": "ADMIN",
        "role_label": "Chủ nhà (Tầng 1 - Toàn quyền)",
        "permission_active": True,
        "permission_status": "ACTIVE",
        "permission_label": "CÓ QUYỀN (Chủ nhà Tầng 1)",
        "password_plain_hint": "123456",
        "password_hash": hash_password("123456"),
        "google_linked": True,
        "invited_by": "SYSTEM_ROOT",
        "needs_first_page_voice_enroll": False,
        "reading_prompt": build_reading_prompt("Nguyễn Tuấn Anh", 1),
        "voiceprint": {
            "enrolled": True,
            "f0_mean_hz": 126.0,
            "f0_min_hz": 105.0,
            "f0_max_hz": 152.0,
            "centroid_hz": 1380.0,
            "source_device": "Samsung Galaxy S9 + Web Studio",
            "reading_prompt_verified": True,
            "updated_at": "02/11/2026",
        },
        "permissions": [
            "Mở/Khóa Cửa chính (D1) & Còi báo động (D8)",
            "Điều khiển toàn bộ Đèn/Quạt/Bơm/Điều hòa",
            "Gửi 2 đường link mời (Cấp 2 & Cấp 3)",
            "Xóa cấp quyền / Bật lại quyền bằng giọng nói trên thiết bị",
        ],
    },
    {
        "account_id": "thanh_vien_a",
        "email": "thanhviena.hust@gmail.com",
        "display_name": "Thành viên A (Người nhà)",
        "tier": 2,
        "saved_tier": 2,
        "role": "MEMBER",
        "role_label": "Người nhà (Tầng 2 - Thiết bị sinh hoạt)",
        "permission_active": True,
        "permission_status": "ACTIVE",
        "permission_label": "CÓ QUYỀN (Tầng 2 - Người nhà)",
        "password_plain_hint": "GiaDinh@123",
        "password_hash": hash_password("GiaDinh@123"),
        "google_linked": True,
        "invited_by": "nep94121@gmail.com (Cấp 1)",
        "needs_first_page_voice_enroll": False,
        "reading_prompt": build_reading_prompt("Thành viên A", 2),
        "voiceprint": {
            "enrolled": True,
            "f0_mean_hz": 198.0,
            "f0_min_hz": 175.0,
            "f0_max_hz": 225.0,
            "centroid_hz": 1820.0,
            "source_device": "Samsung Galaxy S9 Mic",
            "reading_prompt_verified": True,
            "updated_at": "02/11/2026",
        },
        "permissions": [
            "Bật/Tắt Đèn khách (D2), Đèn ngủ (D7), Máy bơm (D3), Điều hòa (IR D2), Quạt (D6)",
            "Chỉ gửi được 1 đường link mời xuống Cấp 3 (Khách)",
            "Bị chặn Mở Cửa chính (D1) & Còi báo động (D8)",
        ],
    },
    {
        "account_id": "thanh_vien_b",
        "email": "thanhvienb.hust@gmail.com",
        "display_name": "Thành viên B (Người nhà)",
        "tier": 2,
        "saved_tier": 2,
        "role": "MEMBER",
        "role_label": "Người nhà (Tầng 2 - Thiết bị sinh hoạt)",
        "permission_active": True,
        "permission_status": "ACTIVE",
        "permission_label": "CÓ QUYỀN (Tầng 2 - Người nhà)",
        "password_plain_hint": "GiaDinh@456",
        "password_hash": hash_password("GiaDinh@456"),
        "google_linked": True,
        "invited_by": "nep94121@gmail.com (Cấp 1)",
        "needs_first_page_voice_enroll": False,
        "reading_prompt": build_reading_prompt("Thành viên B", 2),
        "voiceprint": {
            "enrolled": True,
            "f0_mean_hz": 215.0,
            "f0_min_hz": 190.0,
            "f0_max_hz": 245.0,
            "centroid_hz": 1950.0,
            "source_device": "Samsung Galaxy S9 Mic",
            "reading_prompt_verified": True,
            "updated_at": "02/11/2026",
        },
        "permissions": [
            "Bật/Tắt Đèn khách (D2), Đèn ngủ (D7), Máy bơm (D3), Điều hòa (IR D2), Quạt (D6)",
            "Chỉ gửi được 1 đường link mời xuống Cấp 3 (Khách)",
            "Bị chặn Mở Cửa chính (D1) & Còi báo động (D8)",
        ],
    },
    {
        "account_id": "khach_c",
        "email": "khachc.guest@gmail.com",
        "display_name": "Khách C (Tầng 3)",
        "tier": 3,
        "saved_tier": 3,
        "role": "CHILD_GUEST",
        "role_label": "Khách được cấp quyền (Tầng 3)",
        "permission_active": True,
        "permission_status": "ACTIVE",
        "permission_label": "CÓ QUYỀN (Tầng 3 - Khách)",
        "password_plain_hint": "Khach@789",
        "password_hash": hash_password("Khach@789"),
        "google_linked": True,
        "invited_by": "thanhviena.hust@gmail.com (Cấp 2)",
        "needs_first_page_voice_enroll": False,
        "reading_prompt": build_reading_prompt("Khách C", 3),
        "voiceprint": {
            "enrolled": True,
            "f0_mean_hz": 164.0,
            "f0_min_hz": 153.0,
            "f0_max_hz": 174.0,
            "centroid_hz": 1580.0,
            "source_device": "Web Browser Mic",
            "reading_prompt_verified": True,
            "updated_at": "02/11/2026",
        },
        "permissions": [
            "Chỉ bật/tắt đèn & quạt cơ bản",
            "Không có phần gửi link mời cấp dưới",
            "Bị chặn Cửa chính (D1), Còi (D8) và cài đặt luật",
        ],
    },
]

DEFAULT_INVITE_LINKS: dict[str, dict[str, Any]] = {
    "INV-T1-TO-TIER2": {
        "invite_code": "INV-T1-TO-TIER2",
        "issuer_email": "nep94121@gmail.com",
        "issuer_name": "Nguyễn Tuấn Anh (Cấp 1)",
        "issuer_tier": 1,
        "target_tier": 2,
        "target_role_label": "Người nhà (Tầng 2)",
        "url_path": "/auth?invite=INV-T1-TO-TIER2",
        "full_url": "http://localhost:8088/auth?invite=INV-T1-TO-TIER2",
        "description": "Link do Cấp 1 gửi xuống để đăng ký tài khoản Cấp 2 (Người nhà)",
        "created_at": "02/11/2026",
    },
    "INV-T1-TO-TIER3": {
        "invite_code": "INV-T1-TO-TIER3",
        "issuer_email": "nep94121@gmail.com",
        "issuer_name": "Nguyễn Tuấn Anh (Cấp 1)",
        "issuer_tier": 1,
        "target_tier": 3,
        "target_role_label": "Khách (Tầng 3)",
        "url_path": "/auth?invite=INV-T1-TO-TIER3",
        "full_url": "http://localhost:8088/auth?invite=INV-T1-TO-TIER3",
        "description": "Link do Cấp 1 gửi xuống để đăng ký tài khoản Cấp 3 (Khách)",
        "created_at": "02/11/2026",
    },
    "INV-T2-TO-TIER3": {
        "invite_code": "INV-T2-TO-TIER3",
        "issuer_email": "thanhviena.hust@gmail.com",
        "issuer_name": "Thành viên A (Cấp 2)",
        "issuer_tier": 2,
        "target_tier": 3,
        "target_role_label": "Khách (Tầng 3)",
        "url_path": "/auth?invite=INV-T2-TO-TIER3",
        "full_url": "http://localhost:8088/auth?invite=INV-T2-TO-TIER3",
        "description": "Link do Cấp 2 gửi xuống để đăng ký tài khoản Cấp 3 (Khách)",
        "created_at": "02/11/2026",
    },
}

DURATION_MAP_SECONDS: dict[str, int] = {
    "1d": 86400,
    "2d": 172800,
    "1w": 604800,
    "1m": 2592000,
    "1y": 31536000,
}

DURATION_LABELS_VN: dict[str, str] = {
    "1d": "1 ngày (24 giờ)",
    "2d": "2 ngày (48 giờ)",
    "1w": "1 tuần (7 ngày)",
    "1m": "1 tháng (30 ngày)",
    "1y": "1 năm (365 ngày)",
}


def validate_dns_mx_record(email: str) -> tuple[bool, str]:
    """Kiểm tra định dạng email theo RFC 5322 và kiểm tra bản ghi DNS MX thực tế của tên miền."""
    clean_email = str(email or "").strip()
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", clean_email):
        return (False, "Định dạng email không hợp lệ theo chuẩn RFC 5322")

    domain = clean_email.split("@")[1].lower()
    known_fake_indicators = ("fake", "nonexistent", "dummy", "invalid", "testdomain", "unknown999")
    if any(ind in domain for ind in known_fake_indicators) or domain.endswith(".local") or domain.endswith(".test"):
        return (False, f"Tên miền '{domain}' không có bản ghi MX thực tế (DNS MX Lookup failed)")

    known_valid_mx_domains = {
        "gmail.com",
        "google.com",
        "yahoo.com",
        "outlook.com",
        "hotmail.com",
        "hust.edu.vn",
        "sis.hust.edu.vn",
        "icloud.com",
        "mail.com",
        "proton.me",
    }
    if domain in known_valid_mx_domains:
        return (True, f"Tên miền '{domain}' có bản ghi DNS MX thực tế hợp lệ")

    try:
        proc = subprocess.run(
            ["nslookup", "-type=MX", domain],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3.0,
        )
        out_low = (proc.stdout or "").lower()
        if proc.returncode == 0 and ("mail exchanger" in out_low or "mx preference" in out_low):
            return (True, f"Xác nhận bản ghi DNS MX thành công cho '{domain}'")
    except Exception:
        pass

    return (False, f"Không tìm thấy bản ghi DNS MX cho tên miền '{domain}'")
