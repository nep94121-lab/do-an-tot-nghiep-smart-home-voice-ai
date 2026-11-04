"""Package simulator.auth: Các phân hệ mô-đun của ThreeLayerAuthManager (Hằng số & Crypto, Invite & Gmail OTP, QR TOTP 10s, Test Suite 14 Kịch bản)."""

from __future__ import annotations

from .constants_and_crypto import (
    ACCOUNTS_FILE,
    AUTH_EVENTS_FILE,
    DATA_DIR,
    DEFAULT_ACCOUNTS,
    DEFAULT_INVITE_LINKS,
    DURATION_LABELS_VN,
    DURATION_MAP_SECONDS,
    FAMILY_ALLOWLIST_FILE,
    INVITE_LINKS_FILE,
    ROOT_DIR,
    _now_vn,
    build_reading_prompt,
    hash_password,
    validate_dns_mx_record,
    verify_password_hash,
)
from .invite_and_gmail_mixin import AuthInviteGmailMixin
from .qr_totp_mixin import AuthQrTotpMixin
from .test_suite_mixin import AuthTestSuiteMixin

__all__ = [
    "ROOT_DIR",
    "DATA_DIR",
    "ACCOUNTS_FILE",
    "AUTH_EVENTS_FILE",
    "INVITE_LINKS_FILE",
    "FAMILY_ALLOWLIST_FILE",
    "_now_vn",
    "hash_password",
    "verify_password_hash",
    "build_reading_prompt",
    "DEFAULT_ACCOUNTS",
    "DEFAULT_INVITE_LINKS",
    "DURATION_MAP_SECONDS",
    "DURATION_LABELS_VN",
    "validate_dns_mx_record",
    "AuthInviteGmailMixin",
    "AuthQrTotpMixin",
    "AuthTestSuiteMixin",
]
