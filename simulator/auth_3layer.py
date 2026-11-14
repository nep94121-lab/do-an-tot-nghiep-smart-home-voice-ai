"""Hệ thống Xác Thực Đa Tầng 3 Lớp, Phân Cấp Link Mời, Thu Âm Trang Đầu & Thu Hồi Quyền Bằng Giọng Nói
(Smart Home Voice AI - SEEE HUST 2026).

Triển khai đầy đủ 100% yêu cầu kiến trúc bảo mật thực tế của Sếp:
1. PHÂN CẤP ĐƯỜNG LINK MỜI ĐĂNG KÝ (`Invite Links`):
   - **Cấp 1 (Chủ nhà - Nguyễn Tuấn Anh `nep94121@gmail.com`)**: Có **2 đường link mời** để gửi xuống cấp dưới:
     + Link mời đăng ký **Cấp 2 (Thành viên gia đình)**: `/auth?invite=INV-T1-TO-TIER2`
     + Link mời đăng ký **Cấp 3 (Khách)**: `/auth?invite=INV-T1-TO-TIER3`
   - **Cấp 2 (Người nhà)**: Chỉ có **1 đường link mời** duy nhất để gửi xuống **Cấp 3 (Khách)**:
     + Link mời đăng ký **Cấp 3 (Khách)**: `/auth?invite=INV-T2-TO-TIER3` (Bị chặn nếu cố tạo link Cấp 1 hoặc Cấp 2).
   - **Cấp 3 (Khách)**: **Không có phần gửi link mời** (0 đường link, bị chặn hoàn toàn quyền mời người khác).

2. ĐĂNG KÝ TÀI KHOẢN QUA LINK MỜI BẰNG GOOGLE OAUTH (GMAIL) + GỬI MÃ OTP & MẬT KHẨU VỀ GMAIL:
   - Người cấp dưới ấn vào đường link mời -> Chọn đăng nhập bằng tài khoản Google (`Gmail`) -> Hệ thống sinh mật khẩu cấp phát + mã OTP 6 số gửi thật về hộp thư Gmail (`nep94121@gmail.com` qua `gws gmail`).
   - Hệ thống hỗ trợ **tự động đọc hộp thư đến Gmail thật** (`gws gmail users messages list/get`) để lấy đúng mã OTP 6 số vừa gửi và xác nhận kích hoạt tài khoản!

3. LẦN ĐẦU VÀO TRANG ĐẦU -> ĐỌC DÒNG CHỮ MẪU & ẤN GIỮ THU ÂM LƯU GIỌNG NÓI LÊN SERVER:
   - Ngay sau khi đăng ký qua link mời và vào Trang Đầu, giao diện hiển thị **1 dòng chữ mẫu tiếng Việt** (Prompt câu đọc chuẩn).
   - Người dùng **ấn giữ nút thu âm và đọc dòng chữ đó**, bản thu PCM 16kHz được đẩy thẳng lên Server để trích xuất đặc trưng âm học ($F_0$, RMS, Spectral Centroid) và lưu làm **mẫu giọng nói chủ (Voiceprint)** của tài khoản đó.

4. THU HỒI QUYỀN ("XÓA CẤP QUYỀN") & BẬT LẠI QUYỀN BẰNG GIỌNG NÓI TRÊN THIẾT BỊ:
   - Khi Chủ nhà (Cấp 1) nói vào thiết bị phần cứng / Web / App: *"Xóa cấp quyền của Thành viên A"* (hoặc *"Thu hồi quyền của..."*):
     + Tài khoản của người đó **VẪN TỒN TẠI** trong cơ sở dữ liệu (không bị xóa mất tài khoản), nhưng trạng thái chuyển thành **`KHÔNG CÓ QUYỀN` (`permission_active = False`, `permission_status = "REVOKED"`)**.
     + Khi người đó đăng nhập hoặc nói vào thiết bị, hệ thống báo rõ: **"Tài khoản hiện KHÔNG CÓ QUYỀN (Đã bị Chủ nhà thu hồi quyền)"**.
   - Khi Chủ nhà nói vào thiết bị: *"Bật lại quyền cho Thành viên A"* (hoặc *"Cấp lại quyền cho..."*):
     + Tài khoản lập tức được khôi phục trạng thái **`CÓ QUYỀN` (`permission_active = True`)** và giữ nguyên cấp độ cũ!

Cấu trúc gói mô-đun (`simulator/auth/`):
- `constants_and_crypto.py`: Hằng số tài khoản mặc định, Link mời, Hash mật khẩu và Kiểm tra DNS MX.
- `invite_and_gmail_mixin.py`: Quản lý Email Allowlist, Link Mời Phân Cấp, Gửi/Đọc Gmail OTP và Thu Hồi Quyền Giọng Nói.
- `qr_totp_mixin.py`: Sinh mã QR Động 10 giây (TOTP HMAC-SHA256), Bắt tay Single-Use và Email OTP + DNS MX.
- `test_suite_mixin.py`: Bảng Kiểm thử Tự động Toàn diện 14 Kịch bản (TEST-01 -> TEST-14) và Tổng quan Hệ thống.
"""

from __future__ import annotations

import base64
from contextvars import ContextVar
import copy
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import random
import re
import secrets
import struct
import threading
import time
from typing import Any

_ACCOUNTS_FILE_LOCK = threading.RLock()
_GLOBAL_OTP_LOCK = threading.RLock()
_PATH_DURABLE_CACHE: dict[str, bytes] = {}
_AUTOTEST_SANDBOX: ContextVar[bool] = ContextVar("_AUTOTEST_SANDBOX", default=False)
UNIFORM_INVALID_LOGIN_ERROR = "Email hoặc mật khẩu không chính xác."
_AUTH_CAS_FILENAME = "auth3_accounts_state.json"
_RATELIMIT_CAS_FILENAME = "login_rate_limit.json"
MAX_LOGIN_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 900


def _should_use_cas_store() -> bool:
    if _AUTOTEST_SANDBOX.get():
        return False
    if os.environ.get("SIMULATOR_SECURITY_STATE_DIR", "").strip():
        return True
    if os.environ.get("SMARTHOME_SECURITY_BACKEND", "").strip().lower() == "github":
        return True
    return bool(
        os.environ.get("SMARTHOME_SECURITY_TOKEN", "").strip()
        and os.environ.get("SMARTHOME_SECURITY_REPO", "").strip()
    )


def _atomic_write_file(target_file: Any, payload_bytes: bytes) -> bool:
    target_path = Path(target_file) if not isinstance(target_file, Path) else target_file
    prev_disk_bytes = target_path.read_bytes() if target_path.exists() else None
    resolved_key = str(target_path.resolve())
    prev_cache_bytes = _PATH_DURABLE_CACHE.get(resolved_key)
    tmp_path = target_path.with_suffix(f".tmp.{os.getpid()}_{threading.get_ident()}_{time.time_ns()}")
    wrote_ok = False
    for attempt in range(5):
        try:
            tmp_path.write_bytes(payload_bytes)
            os.replace(tmp_path, target_path)
            wrote_ok = True
            break
        except OSError:
            time.sleep(0.01 * (attempt + 1))
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
    if not wrote_ok:
        try:
            target_path.write_bytes(payload_bytes)
            wrote_ok = True
        except Exception:
            return False
    try:
        _PATH_DURABLE_CACHE[resolved_key] = bytes(payload_bytes)
        if target_path.name in (
            "voiceprints.json",
            "accounts_3layer.json",
            "invite_links_3layer.json",
            "family_email_allowlist.json",
            "custom_rules_overlay.json",
            "user_sessions.json",
        ):
            import simulator.durable_store as _ds

            if (
                not _ds.is_offline_sandbox_or_test()
                or target_path.parent.name in ("data", "smarthome_data")
                or bool(os.environ.get("VERCEL"))
                or bool(os.environ.get("SMARTHOME_DURABLE_DIR"))
                or bool(os.environ.get("SIMULATOR_OFFLINE_SANDBOX"))
            ):
                if not _ds.save_state_file(target_path.name, payload_bytes, data_dir=target_path.parent):
                    if prev_disk_bytes is not None:
                        target_path.write_bytes(prev_disk_bytes)
                    else:
                        target_path.unlink(missing_ok=True)
                    if prev_cache_bytes is not None:
                        _PATH_DURABLE_CACHE[resolved_key] = prev_cache_bytes
                    else:
                        _PATH_DURABLE_CACHE.pop(resolved_key, None)
                    return False
        return True
    except Exception:
        if prev_disk_bytes is not None:
            try:
                target_path.write_bytes(prev_disk_bytes)
            except Exception:
                pass
        else:
            target_path.unlink(missing_ok=True)
        if prev_cache_bytes is not None:
            _PATH_DURABLE_CACHE[resolved_key] = prev_cache_bytes
        else:
            _PATH_DURABLE_CACHE.pop(resolved_key, None)
        return False


from simulator.auth import (
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
    AuthInviteGmailMixin,
    AuthQrTotpMixin,
    AuthTestSuiteMixin,
    _now_vn,
    build_reading_prompt,
    hash_password,
    validate_dns_mx_record,
    verify_password_hash,
)
from simulator.auth.constants_and_crypto import (
    canonical_gmail_mailbox,
    strict_single_email_ascii,
)
from simulator.auth.security_state import (
    SecurityStateUnavailable,
    atomic_security,
    load_security_state,
    save_security_state,
)
from simulator.voice_config import (
    OWNER_EMAIL,
    OWNER_ID,
    THRESHOLD_DEEP,
    THRESHOLD_MEL,
    is_throwaway_qa_identity,
    redact_otp_and_secrets_in_text,
    sanitize_api_payload,
    sanitize_overview_and_logs_payload,
)

_LEGACY_DEFAULT_HASHES = frozenset(
    {
        "1f2d384b510d695cef6ababeb4125d3b8dea3bcc07e9b7fc18389da09957845a",
        "32e36f98f9c3df1a4e325ece2bcea079373339aab2e7dc7bf77971152a990fb9",
        "7d69d7474e26ad41695cf690770e80ca109bdb4131838fcd5d875a8b1d5d184e",
        "a513440d7305d47120ad7cf065279770b696403290c2c4e0a270e53414e2eaaa",
    }
)
_TIMING_DUMMY_HASH = hash_password("timing_pad_do_not_match")


def is_test_otp_fields_allowed(app: Any = None) -> bool:
    """Kiểm tra cờ kiểm thử server-side cho các trường OTP nhạy cảm.

    Quy tắc bảo mật:
    1. Vô điều kiện ép TẮT (False) nếu VERCEL env được thiết lập (ngăn rò rỉ trên Vercel).
    2. Cho phép (True) nếu biến môi trường PYTEST == '1' hoặc app.testing là True.
    3. Mặc định là TẮT (False) trên môi trường production.
    """
    if os.getenv("VERCEL"):
        return False
    if os.getenv("PYTEST") == "1" or getattr(app, "testing", False) is True:
        return True
    return False


class PendingOtpsStore(dict):
    """Lưu trữ pending OTPs có đồng bộ hóa với bản ghi accounts để hỗ trợ kiểm thử và serverless."""

    def __init__(self, auth_mgr: Any = None, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._auth_mgr = auth_mgr

    def clear(self) -> None:
        super().clear()
        if self._auth_mgr and hasattr(self._auth_mgr, "accounts"):
            with _ACCOUNTS_FILE_LOCK:
                for acc in getattr(self._auth_mgr, "accounts", []):
                    acc.pop("pending_otp", None)
                    acc.pop("otp_cooldown_started_at", None)
                    acc.pop("otp_failed_verify_attempts", None)
                if hasattr(self._auth_mgr, "otp_failed_attempts"):
                    self._auth_mgr.otp_failed_attempts.clear()
                if hasattr(self._auth_mgr, "_login_rate_limits"):
                    self._auth_mgr._login_rate_limits.clear()
                self._auth_mgr._save_accounts()


class ThreeLayerAuthManager(
    AuthInviteGmailMixin,
    AuthQrTotpMixin,
    AuthTestSuiteMixin,
):
    """Quản lý Xác thực 3 Lớp, Phân cấp Link Mời, Thu âm Trang đầu & Thu hồi quyền bằng Giọng nói."""

    def __init__(self) -> None:
        self.accounts: list[dict[str, Any]] = []
        self.family_email_allowlist: dict[str, dict[str, Any]] = {}
        self.invite_links: dict[str, dict[str, Any]] = {}
        self.pending_otps: dict[str, dict[str, Any]] = PendingOtpsStore(auth_mgr=self)
        self.otp_failed_attempts: dict[str, list[float]] = {}
        self._login_rate_limits: dict[str, dict[str, Any]] = {}
        self.pending_invite_registrations: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.verification_logs: list[dict[str, Any]] = []
        self.latest_test_report: dict[str, Any] = {}
        self._otp_lock = _GLOBAL_OTP_LOCK
        self._load_state()

    def _normalize_account_fields(self, acc: dict[str, Any]) -> dict[str, Any]:
        acc.pop("password_plain_hint", None)
        if str(acc.get("email", "")).strip().lower() == OWNER_EMAIL.lower():
            acc["account_id"] = OWNER_ID
            acc["tier"] = 1
            acc["saved_tier"] = 1
            acc["role"] = "ADMIN"
            acc["permission_active"] = True
            acc["permission_status"] = "ACTIVE"
        elif str(acc.get("account_id", "")).lower() == OWNER_ID or int(acc.get("tier") or 3) == 1:
            acc["account_id"] = "user_" + secrets.token_hex(16)
            acc["id"] = acc["account_id"]
            acc["user_id"] = acc["account_id"]
            acc["tier"] = 3
            acc["saved_tier"] = 3
            acc["role"] = "CHILD_GUEST"
            acc["permission_active"] = False
            acc["permission_status"] = "REVOKED"
        if str(acc.get("password_hash") or "").strip() in _LEGACY_DEFAULT_HASHES:
            acc["password_hash"] = ""
        acc.setdefault("password_hash", "")
        tier = int(acc.get("tier", 3) or 3)
        if str(acc.get("email", "")).strip().lower() != OWNER_EMAIL.lower():
            acc["role"] = "MEMBER" if tier == 2 else "CHILD_GUEST"
        acc.setdefault("saved_tier", tier)
        acc.setdefault("id", acc.get("account_id", ""))
        acc.setdefault("user_id", acc.get("account_id", ""))
        acc.setdefault("name", acc.get("display_name", acc.get("account_id", "")))
        acc.setdefault("full_name", acc.get("display_name", acc.get("account_id", "")))
        if "permission_active" not in acc:
            acc["permission_active"] = True
        if "permission_status" not in acc:
            if acc["permission_active"]:
                acc["permission_status"] = "ACTIVE"
            elif acc.get("revoked_at") or acc.get("revoked_by"):
                acc["permission_status"] = "REVOKED"
            else:
                acc["permission_status"] = "PENDING"
        if "permission_label" not in acc:
            acc["permission_label"] = (
                f"CÓ QUYỀN (Tầng {tier})"
                if acc["permission_active"]
                else (
                    "🚫 KHÔNG CÓ QUYỀN (Đã bị Chủ nhà thu hồi quyền)"
                    if str(acc.get("permission_status") or "").upper() == "REVOKED"
                    else "⏳ CHỜ PHÊ DUYỆT (Cần Chủ nhà cấp quyền)"
                )
            )
        acc.setdefault("invited_by", "SYSTEM_ROOT" if tier == 1 else f"{OWNER_EMAIL} (Cấp 1)")
        acc["needs_first_page_voice_enroll"] = False
        acc.setdefault("voice_verified", not acc.get("needs_first_page_voice_enroll", False))
        acc.setdefault("reading_prompt", build_reading_prompt(acc.get("display_name", "Thành viên"), tier))
        vp = acc.setdefault("voiceprint", {})
        vp.setdefault("reading_prompt_verified", bool(vp.get("enrolled", False)))
        return acc

    @staticmethod
    def _is_throwaway_account_entry(acc: Any) -> bool:
        if not isinstance(acc, dict):
            return is_throwaway_qa_identity(acc)
        return (
            is_throwaway_qa_identity(acc.get("account_id"))
            or is_throwaway_qa_identity(acc.get("id"))
            or is_throwaway_qa_identity(acc.get("user_id"))
            or is_throwaway_qa_identity(acc.get("email"))
            or is_throwaway_qa_identity(acc.get("display_name"))
            or is_throwaway_qa_identity(acc.get("name"))
        )

    def _purge_throwaway_qa_accounts(self) -> None:
        if isinstance(self.accounts, list):
            self.accounts = [
                a for a in self.accounts
                if isinstance(a, dict) and not self._is_throwaway_account_entry(a)
            ]
        for mapping_attr in (
            "family_email_allowlist",
            "pending_otps",
            "pending_invite_registrations",
            "sessions",
        ):
            mapping = getattr(self, mapping_attr, None)
            if isinstance(mapping, dict):
                for k in list(mapping.keys()):
                    val = mapping.get(k)
                    if is_throwaway_qa_identity(k) or self._is_throwaway_account_entry(val):
                        mapping.pop(k, None)
        if isinstance(self.verification_logs, list):
            self.verification_logs = [
                lg for lg in self.verification_logs
                if isinstance(lg, dict)
                and not is_throwaway_qa_identity(lg.get("email"))
                and not is_throwaway_qa_identity(lg.get("detail"))
            ]

    def reset_to_factory_defaults(self) -> dict[str, Any]:
        """Khôi phục danh sách 4 tài khoản gốc chuẩn của nhà thông minh và bảo toàn quyền Cấp 1 của Nguyễn Tuấn Anh."""
        with _ACCOUNTS_FILE_LOCK:
            self.accounts = [self._normalize_account_fields(a) for a in json.loads(json.dumps(DEFAULT_ACCOUNTS))]
            self._save_accounts()
            self.family_email_allowlist = {}
            self._save_family_allowlist()
            return {"ok": True, "accounts": self.accounts}

    def _restore_missing_file_from_durable_store(self, fpath: Path) -> None:
        if fpath.exists():
            return
        try:
            resolved_key = str(fpath.resolve())
            raw = _PATH_DURABLE_CACHE.get(resolved_key)
            if raw is None and (
                fpath.parent == DATA_DIR
                or fpath.parent.name == "smarthome_data"
                or bool(os.environ.get("VERCEL"))
                or bool(os.environ.get("SMARTHOME_DURABLE_DIR"))
                or bool(os.environ.get("SIMULATOR_OFFLINE_SANDBOX"))
            ):
                from simulator.durable_store import load_state_file

                raw = load_state_file(fpath.name, data_dir=fpath.parent)
            if raw:
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_bytes(raw)
        except Exception:
            pass

    def _load_state(self) -> None:
        with _ACCOUNTS_FILE_LOCK:
            self._restore_missing_file_from_durable_store(ACCOUNTS_FILE)
            self._restore_missing_file_from_durable_store(FAMILY_ALLOWLIST_FILE)
            self._restore_missing_file_from_durable_store(INVITE_LINKS_FILE)

            if ACCOUNTS_FILE.exists():
                try:
                    data = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
                    if isinstance(data, list) and data:
                        self.accounts = [self._normalize_account_fields(a) for a in data]
                    else:
                        self.accounts = [self._normalize_account_fields(a) for a in json.loads(json.dumps(DEFAULT_ACCOUNTS))]
                except Exception:
                    self.accounts = [self._normalize_account_fields(a) for a in json.loads(json.dumps(DEFAULT_ACCOUNTS))]
            else:
                self.accounts = [self._normalize_account_fields(a) for a in json.loads(json.dumps(DEFAULT_ACCOUNTS))]

            existing_ids = {str(a.get("account_id", "")).lower() for a in self.accounts}
            missing_defaults = False
            for def_acc in json.loads(json.dumps(DEFAULT_ACCOUNTS)):
                if str(def_acc.get("account_id", "")).lower() not in existing_ids:
                    self.accounts.append(self._normalize_account_fields(def_acc))
                    missing_defaults = True
            if missing_defaults:
                self._save_accounts()

            if FAMILY_ALLOWLIST_FILE.exists():
                try:
                    fa = json.loads(FAMILY_ALLOWLIST_FILE.read_text(encoding="utf-8"))
                    if isinstance(fa, dict):
                        self.family_email_allowlist = fa
                    elif isinstance(fa, list):
                        self.family_email_allowlist = {str(item.get("email", "")).lower(): item for item in fa if item.get("email")}
                except Exception:
                    self.family_email_allowlist = {}
            else:
                self.family_email_allowlist = {}
                self._save_family_allowlist()

            if INVITE_LINKS_FILE.exists():
                try:
                    inv = json.loads(INVITE_LINKS_FILE.read_text(encoding="utf-8"))
                    if isinstance(inv, dict) and inv:
                        self.invite_links = {
                            k: v
                            for k, v in inv.items()
                            if k != "INV-T2-TO-TIER3"
                            and isinstance(v, dict)
                            and int(v.get("issuer_tier", 1)) == 1
                        }
                        if not self.invite_links:
                            self.invite_links = json.loads(json.dumps(DEFAULT_INVITE_LINKS))
                    else:
                        self.invite_links = json.loads(json.dumps(DEFAULT_INVITE_LINKS))
                except Exception:
                    self.invite_links = json.loads(json.dumps(DEFAULT_INVITE_LINKS))
            else:
                self.invite_links = json.loads(json.dumps(DEFAULT_INVITE_LINKS))
                self._save_invite_links()

            if AUTH_EVENTS_FILE.exists():
                try:
                    ev = json.loads(AUTH_EVENTS_FILE.read_text(encoding="utf-8"))
                    if isinstance(ev, list):
                        cleaned_ev = sanitize_overview_and_logs_payload(ev[:100])
                        self.verification_logs = cleaned_ev
                        if cleaned_ev != ev[:100]:
                            payload = (json.dumps(self.verification_logs[:70], ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                            _atomic_write_file(AUTH_EVENTS_FILE, payload)
                except Exception:
                    self.verification_logs = []

            now = time.time()
            for acc in self.accounts:
                email_key = str(acc.get("email", "")).strip().lower()
                if not email_key:
                    continue
                p_otp = acc.get("pending_otp")
                if p_otp and isinstance(p_otp, dict):
                    if now < p_otp.get("expires_at", 0) or (now - p_otp.get("created_at", 0) < 60.0):
                        self.pending_otps[email_key] = p_otp
                    else:
                        acc.pop("pending_otp", None)
                failed = acc.get("otp_failed_verify_attempts")
                if isinstance(failed, list):
                    recent = [float(t) for t in failed if (now - float(t)) < 300.0]
                    if recent:
                        self.otp_failed_attempts[email_key] = recent
                        acc["otp_failed_verify_attempts"] = recent
                    else:
                        acc.pop("otp_failed_verify_attempts", None)

    def _cas_data_dir(self) -> Path:
        override = os.environ.get("SIMULATOR_SECURITY_STATE_DIR", "").strip()
        if override:
            p = Path(override)
            p.mkdir(parents=True, exist_ok=True)
            return p
        return DATA_DIR

    @staticmethod
    def _hash_otp_code(otp_code: str, otp_salt: str | None = None) -> tuple[str, str]:
        salt = otp_salt or secrets.token_hex(8)
        digest = hashlib.sha256(f"{salt}:{otp_code}".encode("utf-8")).hexdigest()
        return salt, digest

    @classmethod
    def _sanitize_account_for_cas(cls, acc: dict[str, Any]) -> dict[str, Any]:
        item = copy.deepcopy(acc)
        p_otp = item.get("pending_otp")
        if isinstance(p_otp, dict):
            code = str(p_otp.get("otp_code") or "").strip()
            if code and not p_otp.get("otp_hash"):
                salt, digest = cls._hash_otp_code(code, p_otp.get("otp_salt"))
                p_otp["otp_salt"] = salt
                p_otp["otp_hash"] = digest
            p_otp.pop("otp_code", None)
        return item

    def _refresh_otp_maps_from_accounts_locked(self) -> None:
        now = time.time()
        new_otps: dict[str, dict[str, Any]] = {}
        new_fails: dict[str, list[float]] = {}
        for acc in self.accounts:
            email_key = str(acc.get("email") or "").strip().lower()
            if not email_key:
                continue
            p_otp = acc.get("pending_otp")
            if isinstance(p_otp, dict):
                if now < float(p_otp.get("expires_at", 0) or 0) or (now - float(p_otp.get("created_at", 0) or 0) < 60.0):
                    merged_otp = dict(p_otp)
                    prev = dict.get(self.pending_otps, email_key)
                    if (
                        prev
                        and prev.get("otp_code")
                        and prev.get("created_at") == merged_otp.get("created_at")
                        and not merged_otp.get("otp_code")
                    ):
                        merged_otp["otp_code"] = prev["otp_code"]
                    new_otps[email_key] = merged_otp
                else:
                    acc.pop("pending_otp", None)
            failed = acc.get("otp_failed_verify_attempts")
            if isinstance(failed, list):
                recent = [float(t) for t in failed if (now - float(t)) < 300.0]
                if recent:
                    new_fails[email_key] = recent
                    acc["otp_failed_verify_attempts"] = recent
                else:
                    acc.pop("otp_failed_verify_attempts", None)
        dict.clear(self.pending_otps)
        dict.update(self.pending_otps, new_otps)
        self.otp_failed_attempts.clear()
        self.otp_failed_attempts.update(new_fails)

    def _apply_cas_accounts_payload_locked(self, raw: bytes | None) -> bool:
        if not raw:
            return False
        try:
            doc = json.loads(raw.decode("utf-8"))
        except Exception:
            doc = {}
        if not isinstance(doc, dict) or not isinstance(doc.get("accounts"), list) or not doc["accounts"]:
            return False
        loaded = [
            self._normalize_account_fields(copy.deepcopy(a))
            for a in doc["accounts"]
            if isinstance(a, dict) and not self._is_throwaway_account_entry(a)
        ]
        existing_ids = {str(a.get("account_id", "")).lower() for a in loaded}
        for def_acc in json.loads(json.dumps(DEFAULT_ACCOUNTS)):
            if str(def_acc.get("account_id", "")).lower() not in existing_ids:
                loaded.append(self._normalize_account_fields(def_acc))
        self.accounts = loaded
        self._refresh_otp_maps_from_accounts_locked()
        return True

    def _bootstrap_seed_accounts_into_memory_locked(self) -> None:
        if os.environ.get("SIMULATOR_SECURITY_STATE_DIR", "").strip():
            return
        try:
            from simulator.durable_store import load_state_file

            raw_durable = load_state_file(ACCOUNTS_FILE.name, data_dir=ACCOUNTS_FILE.parent)
            if raw_durable:
                durable_list = json.loads(raw_durable.decode("utf-8"))
                if isinstance(durable_list, list) and durable_list:
                    merged: list[dict[str, Any]] = []
                    seen_emails: set[str] = set()
                    for item in durable_list:
                        if isinstance(item, dict) and not self._is_throwaway_account_entry(item):
                            norm = self._normalize_account_fields(copy.deepcopy(item))
                            merged.append(norm)
                            em = str(norm.get("email") or "").strip().lower()
                            if em:
                                seen_emails.add(em)
                    for existing in self.accounts:
                        em = str(existing.get("email") or "").strip().lower()
                        if em and em not in seen_emails:
                            merged.append(copy.deepcopy(existing))
                            seen_emails.add(em)
                    self.accounts = merged
                    self._refresh_otp_maps_from_accounts_locked()
        except Exception:
            pass

    def _sync_accounts_from_cas_if_enabled(self) -> None:
        if not _should_use_cas_store():
            return
        from simulator.auth.security_state import _TRANSACTION

        cur_tx = _TRANSACTION.get()
        if cur_tx is not None and cur_tx.filename == _AUTH_CAS_FILENAME:
            # Inside an open CAS transaction, self.accounts already holds the live working state.
            return

        raw = load_security_state(_AUTH_CAS_FILENAME, self._cas_data_dir())
        with _ACCOUNTS_FILE_LOCK:
            with self._otp_lock:
                if self._apply_cas_accounts_payload_locked(raw):
                    return

        @atomic_security(_AUTH_CAS_FILENAME)
        def _bootstrap() -> None:
            tx_raw = load_security_state(_AUTH_CAS_FILENAME, self._cas_data_dir())
            with _ACCOUNTS_FILE_LOCK:
                with self._otp_lock:
                    if self._apply_cas_accounts_payload_locked(tx_raw):
                        return
                    self._bootstrap_seed_accounts_into_memory_locked()
                    payload_obj = {
                        "accounts": [self._sanitize_account_for_cas(a) for a in self.accounts],
                        "updated_at": time.time(),
                    }
                    save_security_state(
                        _AUTH_CAS_FILENAME,
                        json.dumps(payload_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                        self._cas_data_dir(),
                    )

        _bootstrap()

    def _with_cas_accounts(self, fn):
        if not _should_use_cas_store():
            return fn()
        from simulator.auth.security_state import _TRANSACTION

        cur_tx = _TRANSACTION.get()
        if cur_tx is not None and cur_tx.filename == _AUTH_CAS_FILENAME:
            raw_tx = cur_tx.staged if cur_tx.staged is not None else cur_tx.payload
            with _ACCOUNTS_FILE_LOCK:
                with self._otp_lock:
                    if not self._apply_cas_accounts_payload_locked(raw_tx):
                        self._bootstrap_seed_accounts_into_memory_locked()
            return fn()

        @atomic_security(_AUTH_CAS_FILENAME)
        def _tx():
            tx_raw = load_security_state(_AUTH_CAS_FILENAME, self._cas_data_dir())
            with _ACCOUNTS_FILE_LOCK:
                with self._otp_lock:
                    if not self._apply_cas_accounts_payload_locked(tx_raw):
                        self._bootstrap_seed_accounts_into_memory_locked()
            return fn()

        return _tx()

    @staticmethod
    def _login_rate_limit_key(email: str, client_ip: str = "unknown") -> str:
        raw_email = str(email or "").strip().lower()
        canon = canonical_gmail_mailbox(raw_email) or raw_email or "empty"
        ip_norm = str(client_ip or "unknown").strip().lower() or "unknown"
        return f"{canon}|{ip_norm}"

    @staticmethod
    def _prune_rate_limit_buckets(buckets: dict[str, Any], now: float) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        for k, v in buckets.items():
            if not isinstance(v, dict):
                continue
            locked_until = float(v.get("locked_until", 0) or 0)
            window_start = float(v.get("window_start", 0) or 0)
            if locked_until > now or (now - window_start) < LOGIN_LOCKOUT_SECONDS:
                cleaned[str(k)] = dict(v)
        if len(cleaned) > 500:
            ordered = sorted(cleaned.items(), key=lambda kv: float(kv[1].get("updated_at", 0) or 0), reverse=True)
            cleaned = dict(ordered[:500])
        return cleaned

    @staticmethod
    def _locked_error_payload(locked_until: float, now: float) -> dict[str, Any]:
        remaining = max(1, int(math.ceil(locked_until - now)))
        mins = max(1, int(math.ceil(remaining / 60)))
        return {
            "ok": False,
            "layer": 1,
            "status_code": 429,
            "locked": True,
            "rate_limited": True,
            "retry_after_seconds": remaining,
            "error": (
                f"Tài khoản tạm thời bị khóa do đăng nhập sai quá nhiều lần. "
                f"Vui lòng thử lại sau {mins} phút."
            ),
        }

    def _read_rate_limit_buckets(self) -> dict[str, Any]:
        if not _should_use_cas_store():
            return dict(self._login_rate_limits)
        raw = load_security_state(_RATELIMIT_CAS_FILENAME, self._cas_data_dir())
        if not raw:
            return {}
        try:
            doc = json.loads(raw.decode("utf-8"))
            if isinstance(doc, dict) and isinstance(doc.get("buckets"), dict):
                return dict(doc["buckets"])
        except Exception:
            pass
        return {}

    def _check_login_rate_limit(self, email: str, client_ip: str = "unknown") -> dict[str, Any] | None:
        key = self._login_rate_limit_key(email, client_ip)
        now = time.time()
        buckets = self._read_rate_limit_buckets()
        rec = buckets.get(key)
        if isinstance(rec, dict):
            locked_until = float(rec.get("locked_until", 0) or 0)
            if locked_until > now:
                return self._locked_error_payload(locked_until, now)
        return None

    def _record_login_failure(self, email: str, client_ip: str = "unknown") -> dict[str, Any] | None:
        key = self._login_rate_limit_key(email, client_ip)
        if not _should_use_cas_store():
            with self._otp_lock:
                now = time.time()
                self._login_rate_limits = self._prune_rate_limit_buckets(self._login_rate_limits, now)
                rec = dict(self._login_rate_limits.get(key) or {})
                locked_until = float(rec.get("locked_until", 0) or 0)
                if locked_until > now:
                    return self._locked_error_payload(locked_until, now)
                window_start = float(rec.get("window_start", 0) or 0)
                count = int(rec.get("count", 0) or 0)
                if (now - window_start) >= LOGIN_LOCKOUT_SECONDS or count < 0:
                    window_start = now
                    count = 0
                count += 1
                new_rec: dict[str, Any] = {
                    "count": count,
                    "window_start": window_start,
                    "updated_at": now,
                    "locked_until": 0.0,
                }
                if count >= MAX_LOGIN_FAILURES:
                    new_rec["locked_until"] = now + LOGIN_LOCKOUT_SECONDS
                self._login_rate_limits[key] = new_rec
                if new_rec["locked_until"] > now:
                    return self._locked_error_payload(new_rec["locked_until"], now)
                return None

        @atomic_security(_RATELIMIT_CAS_FILENAME)
        def _tx() -> dict[str, Any] | None:
            now = time.time()
            raw = load_security_state(_RATELIMIT_CAS_FILENAME, self._cas_data_dir())
            buckets: dict[str, Any] = {}
            if raw:
                try:
                    doc = json.loads(raw.decode("utf-8"))
                    if isinstance(doc, dict) and isinstance(doc.get("buckets"), dict):
                        buckets = dict(doc["buckets"])
                except Exception:
                    buckets = {}
            buckets = self._prune_rate_limit_buckets(buckets, now)
            rec = dict(buckets.get(key) or {})
            locked_until = float(rec.get("locked_until", 0) or 0)
            if locked_until > now:
                return self._locked_error_payload(locked_until, now)
            window_start = float(rec.get("window_start", 0) or 0)
            count = int(rec.get("count", 0) or 0)
            if (now - window_start) >= LOGIN_LOCKOUT_SECONDS or count < 0:
                window_start = now
                count = 0
            count += 1
            new_rec: dict[str, Any] = {
                "count": count,
                "window_start": window_start,
                "updated_at": now,
                "locked_until": 0.0,
            }
            if count >= MAX_LOGIN_FAILURES:
                new_rec["locked_until"] = now + LOGIN_LOCKOUT_SECONDS
            buckets[key] = new_rec
            save_security_state(
                _RATELIMIT_CAS_FILENAME,
                json.dumps({"buckets": buckets, "updated_at": now}, separators=(",", ":")).encode("utf-8"),
                self._cas_data_dir(),
            )
            if new_rec["locked_until"] > now:
                return self._locked_error_payload(new_rec["locked_until"], now)
            return None

        return _tx()

    def _clear_login_failures(self, email: str, client_ip: str = "unknown") -> None:
        key = self._login_rate_limit_key(email, client_ip)
        if not _should_use_cas_store():
            with self._otp_lock:
                self._login_rate_limits.pop(key, None)
            return
        existing = self._read_rate_limit_buckets()
        if key not in existing:
            return

        @atomic_security(_RATELIMIT_CAS_FILENAME)
        def _tx() -> None:
            now = time.time()
            raw = load_security_state(_RATELIMIT_CAS_FILENAME, self._cas_data_dir())
            buckets: dict[str, Any] = {}
            if raw:
                try:
                    doc = json.loads(raw.decode("utf-8"))
                    if isinstance(doc, dict) and isinstance(doc.get("buckets"), dict):
                        buckets = dict(doc["buckets"])
                except Exception:
                    buckets = {}
            if key not in buckets:
                return
            buckets.pop(key, None)
            buckets = self._prune_rate_limit_buckets(buckets, now)
            save_security_state(
                _RATELIMIT_CAS_FILENAME,
                json.dumps({"buckets": buckets, "updated_at": now}, separators=(",", ":")).encode("utf-8"),
                self._cas_data_dir(),
            )

        _tx()

    def _save_local_accounts_only(self) -> bool:
        self._purge_throwaway_qa_accounts()
        sanitized_accounts = [self._sanitize_account_for_cas(a) for a in self.accounts]
        payload = (json.dumps(sanitized_accounts, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        target = (
            self._cas_data_dir() / ACCOUNTS_FILE.name
            if os.environ.get("SIMULATOR_SECURITY_STATE_DIR", "").strip()
            else ACCOUNTS_FILE
        )
        with _ACCOUNTS_FILE_LOCK:
            return bool(_atomic_write_file(target, payload))

    def _save_accounts(self) -> bool:
        self._purge_throwaway_qa_accounts()
        if _AUTOTEST_SANDBOX.get():
            return True
        if not _should_use_cas_store():
            return self._save_local_accounts_only()
        from simulator.auth.security_state import _TRANSACTION

        payload_obj = {
            "accounts": [self._sanitize_account_for_cas(a) for a in self.accounts],
            "updated_at": time.time(),
        }
        encoded = json.dumps(payload_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        cur_tx = _TRANSACTION.get()
        if cur_tx is not None and cur_tx.filename == _AUTH_CAS_FILENAME:
            save_security_state(_AUTH_CAS_FILENAME, encoded, self._cas_data_dir())
            self._save_local_accounts_only()
            return True

        @atomic_security(_AUTH_CAS_FILENAME)
        def _direct_commit() -> bool:
            save_security_state(_AUTH_CAS_FILENAME, encoded, self._cas_data_dir())
            self._save_local_accounts_only()
            return True

        try:
            return bool(_direct_commit())
        except SecurityStateUnavailable:
            return False

    def _save_family_allowlist(self) -> bool:
        payload = (json.dumps(self.family_email_allowlist, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        with _ACCOUNTS_FILE_LOCK:
            return bool(_atomic_write_file(FAMILY_ALLOWLIST_FILE, payload))

    def _save_invite_links(self) -> bool:
        payload = (json.dumps(self.invite_links, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        with _ACCOUNTS_FILE_LOCK:
            return bool(_atomic_write_file(INVITE_LINKS_FILE, payload))

    def _log_event(
        self,
        layer: str,
        action: str,
        email: str,
        status: str,
        detail: str,
        source: str = "Web/App",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        safe_detail = redact_otp_and_secrets_in_text(str(detail or ""))
        safe_extra = sanitize_overview_and_logs_payload(extra or {})
        item = {
            "id": int(time.time() * 1000) % 1000000,
            "time_vn": _now_vn(),
            "layer": layer,
            "action": action,
            "email": email,
            "status": status,
            "detail": safe_detail,
            "source": source,
            "extra": safe_extra if isinstance(safe_extra, dict) else {},
        }
        self.verification_logs.insert(0, item)
        self.verification_logs = self.verification_logs[:120]
        if not _AUTOTEST_SANDBOX.get():
            try:
                payload = (json.dumps(self.verification_logs[:70], ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                with _ACCOUNTS_FILE_LOCK:
                    _atomic_write_file(AUTH_EVENTS_FILE, payload)
            except Exception:
                pass
        return item

    def get_overview(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._sync_accounts_from_cas_if_enabled()
        return super().get_overview(*args, **kwargs)

    def find_account(self, identifier: str) -> dict[str, Any] | None:
        self._sync_accounts_from_cas_if_enabled()
        self._purge_throwaway_qa_accounts()
        ident = identifier.strip().lower()
        if not ident or is_throwaway_qa_identity(ident):
            return None
        alias_map = {
            "khach.hust@gmail.com": "khachc.guest@gmail.com",
            "khach_hust": "khach_c",
            "guest_1": "khach_c",
            "member_1": "thanh_vien_a",
        }
        ident_lookup = alias_map.get(ident, ident)
        for acc in self.accounts:
            if acc["email"].lower() in (ident, ident_lookup):
                return acc
        if "@" in ident or "@" in ident_lookup:
            ident_canon = canonical_gmail_mailbox(ident_lookup) or canonical_gmail_mailbox(ident)
            if ident_canon:
                for acc in self.accounts:
                    if str(acc.get("email") or "").strip().lower() == ident_canon:
                        return acc
                for acc in self.accounts:
                    if canonical_gmail_mailbox(acc.get("email")) == ident_canon:
                        return acc
            return None
        ident_slug = ident.replace(" ", "_")
        for acc in self.accounts:
            acc_id = acc["account_id"].lower()
            if acc_id in (ident, ident_lookup) or ident_slug == acc_id:
                return acc
        ordered = sorted(self.accounts, key=lambda item: 0 if item.get("permission_active", True) else 1)
        for acc in ordered:
            if acc["display_name"].lower() in (ident, ident_lookup):
                return acc
        for acc in ordered:
            if acc.get("permission_active", True) and ident in acc["display_name"].lower():
                return acc
        return None

    # =========================================================================
    # XÁC THỰC 3 LỚP (ĐĂNG NHẬP MẬT KHẨU/GOOGLE -> GMAIL OTP -> GIỌNG NÓI)
    # =========================================================================
    def layer1_login(
        self,
        email: str,
        password: str = "",
        login_method: str = "password",
        source: str = "Web",
        send_gmail: bool = True,
        client_ip: str = "unknown",
        app: Any = None,
    ) -> dict[str, Any]:
        """Lớp 1: Kiểm tra Email/Mật khẩu + rate limit -> Kiểm tra Quyền -> Yêu cầu Lớp 2 OTP cho Cấp 1."""
        self._purge_throwaway_qa_accounts()
        clean_email = str(email or "").strip().lower()
        if not clean_email:
            return {"ok": False, "layer": 1, "status_code": 401, "error": UNIFORM_INVALID_LOGIN_ERROR}
        if is_throwaway_qa_identity(clean_email):
            return {"ok": False, "layer": 1, "status_code": 401, "error": UNIFORM_INVALID_LOGIN_ERROR}

        lock_err = self._check_login_rate_limit(clean_email, client_ip)
        if lock_err is not None:
            return lock_err

        self._sync_accounts_from_cas_if_enabled()
        acc = self.find_account(clean_email)
        if not acc:
            verify_password_hash(password, _TIMING_DUMMY_HASH)
            self._log_event(
                layer="Lớp 1 (Tài khoản/Mật khẩu)",
                action="login_attempt",
                email=clean_email,
                status="FAIL",
                detail="Đăng nhập thất bại (thông tin không hợp lệ).",
                source=source,
            )
            lock_res = self._record_login_failure(clean_email, client_ip)
            if lock_res is not None:
                return lock_res
            return {"ok": False, "layer": 1, "status_code": 401, "error": UNIFORM_INVALID_LOGIN_ERROR}

        is_owner_acc = str(acc.get("account_id", "")).lower() == OWNER_ID or int(acc.get("tier", 3)) == 1
        if is_owner_acc and login_method != "password":
            return {
                "ok": False,
                "layer": 1,
                "status_code": 401,
                "error": "Tài khoản Chủ nhà bắt buộc đăng nhập bằng mật khẩu mã hóa!",
            }

        stored_hash = str(acc.get("password_hash") or "").strip()
        if not stored_hash or stored_hash == "0" * 64:
            verify_password_hash(password, _TIMING_DUMMY_HASH)
            lock_res = self._record_login_failure(clean_email, client_ip)
            if lock_res is not None:
                return lock_res
            return {
                "ok": False,
                "layer": 1,
                "status_code": 401,
                "error": UNIFORM_INVALID_LOGIN_ERROR,
            }
        pw_ok = verify_password_hash(password, stored_hash)
        if not pw_ok:
            self._log_event(
                layer="Lớp 1 (Tài khoản/Mật khẩu)",
                action="password_check",
                email=acc["email"],
                status="FAIL",
                detail=f"Nhập sai mật khẩu cho tài khoản {acc['display_name']} (Tầng {acc['tier']}).",
                source=source,
            )
            lock_res = self._record_login_failure(clean_email, client_ip)
            if lock_res is not None:
                return lock_res
            return {
                "ok": False,
                "layer": 1,
                "status_code": 401,
                "error": UNIFORM_INVALID_LOGIN_ERROR,
            }

        if not acc.get("permission_active", True):
            self._clear_login_failures(clean_email, client_ip)
            p_status = str(acc.get("permission_status") or "").strip().upper()
            if p_status == "REVOKED" or acc.get("revoked_at") or acc.get("revoked_by"):
                self._log_event(
                    layer="Lớp 1 (Kiểm tra Cấp Quyền)",
                    action="account_exists_but_no_permission",
                    email=acc["email"],
                    status="FAIL",
                    detail=(
                        f"Tài khoản {acc['display_name']} ({acc['email']}) vẫn tồn tại nhưng hiện KHÔNG CÓ QUYỀN "
                        f"(Đã bị Chủ nhà thu hồi quyền)."
                    ),
                    source=source,
                )
                return {
                    "ok": False,
                    "layer": 1,
                    "status_code": 403,
                    "account_exists": True,
                    "permission_status": "REVOKED",
                    "permission_label": "🚫 TÀI KHOẢN HIỆN KHÔNG CÓ QUYỀN",
                    "account": {
                        "account_id": acc["account_id"],
                        "email": acc["email"],
                        "display_name": acc["display_name"],
                        "tier": acc["tier"],
                        "saved_tier": acc.get("saved_tier", acc["tier"]),
                        "permission_active": False,
                        "permission_status": "REVOKED",
                    },
                    "error": (
                        f"🚫 TÀI KHOẢN HIỆN KHÔNG CÓ QUYỀN: Tài khoản '{acc['display_name']}' ({acc['email']}) vẫn còn trên hệ thống "
                        f"nhưng đã bị Chủ nhà xóa cấp quyền. Khi nào Chủ nhà bật lại thì bạn mới được cấp quyền lại như cũ!"
                    ),
                }
            self._log_event(
                layer="Lớp 1 (Kiểm tra Cấp Quyền)",
                action="account_pending_owner_approval",
                email=acc["email"],
                status="FAIL",
                detail=f"Tài khoản {acc['display_name']} ({acc['email']}) đang chờ Chủ nhà phê duyệt.",
                source=source,
            )
            return {
                "ok": False,
                "layer": 1,
                "status_code": 403,
                "account_exists": True,
                "permission_status": "PENDING",
                "permission_label": "⏳ CHỜ CHỦ NHÀ DUYỆT",
                "account": {
                    "account_id": acc["account_id"],
                    "email": acc["email"],
                    "display_name": acc["display_name"],
                    "tier": acc["tier"],
                    "saved_tier": acc.get("saved_tier", acc["tier"]),
                    "permission_active": False,
                    "permission_status": "PENDING",
                },
                "error": "⏳ Tài khoản đang chờ Chủ nhà phê duyệt cấp quyền trước khi đăng nhập.",
            }

        acc_email_key = str(acc.get("email") or clean_email).strip().lower()
        if is_owner_acc:
            otp_code = f"{random.randint(100000, 999999)}"
            now = time.time()
            otp_salt, otp_hash = self._hash_otp_code(otp_code)
            gmail_res: dict[str, Any] = (
                {"sent_real_gmail": False, "pending": True, "actual_recipient": acc["email"]}
                if send_gmail
                else {"sent_real_gmail": False, "dry_run": True, "actual_recipient": acc["email"]}
            )

            def _stage_layer2_otp() -> bool:
                with self._otp_lock:
                    target_acc = next(
                        (a for a in self.accounts if str(a.get("email") or "").strip().lower() == acc_email_key),
                        acc,
                    )
                    otp_record = {
                        "email": target_acc["email"],
                        "account_id": target_acc["account_id"],
                        "display_name": target_acc["display_name"],
                        "tier": target_acc["tier"],
                        "purpose": "layer2_login",
                        "otp_code": otp_code,
                        "otp_salt": otp_salt,
                        "otp_hash": otp_hash,
                        "created_at": now,
                        "expires_at": now + 300,
                        "last_email_sent_at": now if send_gmail else 0.0,
                        "verified_layer2": False,
                        "verified_layer3": False,
                        "consumed": False,
                        "gmail_delivery": dict(gmail_res),
                        "source": source,
                    }
                    self.pending_otps[acc_email_key] = otp_record
                    target_acc["pending_otp"] = otp_record
                    target_acc.pop("otp_failed_verify_attempts", None)
                    self.otp_failed_attempts.pop(acc_email_key, None)
                    return self._save_accounts()

            if not self._with_cas_accounts(_stage_layer2_otp):
                return {"ok": False, "layer": 1, "status_code": 503, "error": "Không khởi tạo được thử thách OTP Lớp 2."}

            if send_gmail:
                gmail_res = self.send_real_gmail_otp(acc["email"], otp_code, acc["display_name"])

                def _record_delivery() -> None:
                    with self._otp_lock:
                        target_acc = next(
                            (a for a in self.accounts if str(a.get("email") or "").strip().lower() == acc_email_key),
                            None,
                        )
                        if target_acc and isinstance(target_acc.get("pending_otp"), dict):
                            if not gmail_res.get("sent_real_gmail") and (
                                gmail_res.get("missing_secret") or gmail_res.get("blocked_by_allowlist")
                            ):
                                target_acc.pop("pending_otp", None)
                                dict.pop(self.pending_otps, acc_email_key, None)
                            else:
                                target_acc["pending_otp"]["gmail_delivery"] = gmail_res
                                if acc_email_key in self.pending_otps:
                                    self.pending_otps[acc_email_key]["gmail_delivery"] = gmail_res
                            self._save_accounts()

                self._with_cas_accounts(_record_delivery)
                if not gmail_res.get("sent_real_gmail"):
                    err_msg = gmail_res.get("error") or gmail_res.get("note") or "Không thể gửi mã OTP đến Gmail Chủ nhà."
                    return {
                        "ok": False,
                        "layer": 1,
                        "status_code": 503,
                        "error": f"Không thể gửi email OTP Lớp 2: {err_msg}",
                        "gmail_delivery": gmail_res,
                    }

            self._log_event(
                layer="Lớp 1 -> Lớp 2 (Gmail OTP)",
                action="layer1_passed_otp_required",
                email=acc["email"],
                status="PASS",
                detail=f"Xác thực mật khẩu Chủ nhà hợp lệ — yêu cầu OTP Lớp 2 ({login_method}).",
                source=source,
                extra={"tier": acc["tier"]},
            )
            res_payload: dict[str, Any] = {
                "ok": True,
                "layer": 1,
                "next_layer": 2,
                "otp_required": True,
                "authenticated": False,
                "otp_sent": bool(gmail_res.get("sent_real_gmail")),
                "account": {
                    "account_id": acc["account_id"],
                    "email": acc["email"],
                    "display_name": acc["display_name"],
                    "tier": acc["tier"],
                    "role_label": acc["role_label"],
                    "permission_active": True,
                    "permission_status": "ACTIVE",
                },
                "tier": acc["tier"],
                "gmail_delivery": gmail_res,
                "message": "Lớp 1 hợp lệ. Vui lòng nhập mã OTP 6 số gửi về Gmail Chủ nhà để hoàn tất Lớp 2.",
            }
            if is_test_otp_fields_allowed(app) and (not send_gmail or gmail_res.get("sent_real_gmail")):
                res_payload["otp_code_for_test"] = otp_code
                res_payload["otp_code_for_test_table"] = otp_code
                res_payload["demo_otp_preview"] = otp_code
            return res_payload

        # Tier 2 / Tier 3 active accounts complete authentication after password verification
        self._clear_login_failures(clean_email, client_ip)
        invite_bundle = self.get_invite_links_for_account(acc["email"])
        self._log_event(
            layer="Lớp 1 (Tài khoản/Mật khẩu)",
            action="layer1_login_success",
            email=acc["email"],
            status="PASS",
            detail=f"Đăng nhập Tầng {acc['tier']} thành công.",
            source=source,
        )
        return {
            "ok": True,
            "layer": 1,
            "otp_required": False,
            "authenticated": True,
            "account": {
                "account_id": acc["account_id"],
                "email": acc["email"],
                "display_name": acc["display_name"],
                "tier": acc["tier"],
                "role_label": acc["role_label"],
                "permission_active": acc.get("permission_active", True),
                "permission_status": acc.get("permission_status", "ACTIVE"),
            },
            "tier": acc["tier"],
            "invite_links_bundle": invite_bundle,
            "message": f"✅ Đăng nhập thành công ({acc['role_label']}).",
        }

    def send_layer2_login_otp(self, email: str, source: str = "Web", app: Any = None) -> dict[str, Any]:
        """Gửi OTP Gmail cho phiên Lớp 1 Cấp 1 đã vượt qua bước mật khẩu (có cooldown 60 giây)."""
        clean_email = str(email or "").strip().lower()
        if not clean_email:
            return {"ok": False, "status_code": 400, "error": "Thiếu địa chỉ email."}
        self._sync_accounts_from_cas_if_enabled()
        acc = self.find_account(clean_email)
        if not acc or not (str(acc.get("account_id", "")).lower() == OWNER_ID or int(acc.get("tier", 3)) == 1):
            return {"ok": False, "status_code": 403, "error": "Chỉ áp dụng OTP Lớp 2 cho tài khoản Chủ nhà Cấp 1."}
        acc_email_key = str(acc.get("email") or clean_email).strip().lower()
        now = time.time()
        issued: dict[str, Any] = {}

        def _prepare() -> dict[str, Any] | None:
            with self._otp_lock:
                target_acc = next(
                    (a for a in self.accounts if str(a.get("email") or "").strip().lower() == acc_email_key),
                    None,
                )
                pending = (self.pending_otps.get(acc_email_key) or (target_acc.get("pending_otp") if target_acc else None))
                if (
                    not isinstance(pending, dict)
                    or pending.get("consumed")
                    or pending.get("purpose", "layer2_login") != "layer2_login"
                    or now >= float(pending.get("expires_at", 0) or 0)
                ):
                    return {
                        "ok": False,
                        "status_code": 401,
                        "error": "Phiên mật khẩu Lớp 1 chưa hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại.",
                    }
                last_sent = float(pending.get("last_email_sent_at", 0) or 0)
                if last_sent > 0 and (now - last_sent) < 60.0 and (pending.get("gmail_delivery") or {}).get("sent_real_gmail"):
                    rem = max(0, int(60.0 - (now - last_sent)))
                    return {
                        "ok": True,
                        "idempotent": True,
                        "cooldown_active": True,
                        "cooldown_remaining_seconds": rem,
                        "email": acc_email_key,
                        "message": f"Mã OTP Lớp 2 đã được gửi trước đó. Vui lòng kiểm tra hộp thư hoặc đợi {rem}s.",
                    }
                otp_code = f"{random.randint(100000, 999999)}"
                otp_salt, otp_hash = self._hash_otp_code(otp_code)
                pending = dict(pending)
                pending["otp_code"] = otp_code
                pending["otp_salt"] = otp_salt
                pending["otp_hash"] = otp_hash
                pending["last_email_sent_at"] = now
                pending["expires_at"] = max(float(pending.get("expires_at", 0) or 0), now + 300)
                pending["gmail_delivery"] = {"sent_real_gmail": False, "pending": True}
                self.pending_otps[acc_email_key] = pending
                if target_acc is not None:
                    target_acc["pending_otp"] = pending
                if not self._save_accounts():
                    return {"ok": False, "status_code": 503, "error": "Không lưu được trạng thái OTP Lớp 2."}
                issued["otp_code"] = otp_code
                issued["display_name"] = target_acc.get("display_name", acc_email_key) if target_acc else acc_email_key
                return None

        prep_res = self._with_cas_accounts(_prepare)
        if prep_res is not None:
            return prep_res

        gmail_res = self.send_real_gmail_otp(acc_email_key, issued["otp_code"], issued["display_name"])

        def _finish() -> None:
            with self._otp_lock:
                target_acc = next(
                    (a for a in self.accounts if str(a.get("email") or "").strip().lower() == acc_email_key),
                    None,
                )
                if target_acc and isinstance(target_acc.get("pending_otp"), dict):
                    target_acc["pending_otp"]["gmail_delivery"] = gmail_res
                    if acc_email_key in self.pending_otps:
                        self.pending_otps[acc_email_key]["gmail_delivery"] = gmail_res
                    self._save_accounts()

        self._with_cas_accounts(_finish)
        if not gmail_res.get("sent_real_gmail"):
            err_msg = gmail_res.get("error") or gmail_res.get("note") or "Không thể gửi email OTP Lớp 2."
            return {"ok": False, "status_code": 503, "error": f"Không thể gửi email OTP Lớp 2: {err_msg}", "gmail_delivery": gmail_res}

        resp = {
            "ok": True,
            "email": acc_email_key,
            "cooldown_remaining_seconds": 60,
            "gmail_delivery": gmail_res,
            "message": f"✅ Đã gửi mã OTP 6 số về Gmail Chủ nhà ({gmail_res.get('actual_recipient', acc_email_key)}).",
        }
        if is_test_otp_fields_allowed(app):
            resp["otp_code_for_test"] = issued["otp_code"]
            resp["demo_otp_preview"] = issued["otp_code"]
        return resp

    def register_or_update_password(
        self,
        email: str,
        password: str,
        confirm_password: str,
        display_name: str = "",
        target_tier: int = 3,
        invited: bool = False,
        source: str = "Web",
        create_only: bool = False,
        guest_invite_id: str = "",
    ) -> dict[str, Any]:
        """Tạo tài khoản hoặc đặt/đổi mật khẩu với bắt buộc 2 ô mật khẩu (Mật khẩu & Xác nhận lại mật khẩu)."""
        self._purge_throwaway_qa_accounts()
        raw_email = str(email or "")
        clean_email = strict_single_email_ascii(raw_email) or raw_email.strip().lower()
        if is_throwaway_qa_identity(clean_email) or is_throwaway_qa_identity(display_name):
            return {"ok": False, "error": "Tài khoản thử nghiệm QA tạm thời đã bị cấm đăng ký."}
        pw1 = str(password or "").strip()
        pw2 = str(confirm_password or "").strip()
        if not clean_email or "@" not in clean_email:
            return {"ok": False, "status_code": 400, "error": "Vui lòng nhập địa chỉ Email hợp lệ!"}
        if not pw1 or not pw2:
            return {"ok": False, "status_code": 400, "error": "Vui lòng nhập đầy đủ cả 2 ô: Mật khẩu và Xác nhận lại mật khẩu!"}
        if pw1 != pw2:
            return {"ok": False, "status_code": 400, "error": "Hai ô mật khẩu (Mật khẩu và Xác nhận lại mật khẩu) không khớp nhau!"}
        if len(pw1) < 6:
            return {"ok": False, "status_code": 400, "error": "Mật khẩu phải có từ 6 ký tự trở lên!"}

        if not strict_single_email_ascii(raw_email) or not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9._+\-]*[a-z0-9])?@(?:gmail|googlemail)\.com", clean_email
        ):
            return {"ok": False, "status_code": 400, "error": "Chỉ đăng ký bằng địa chỉ Gmail."}

        canon_email = canonical_gmail_mailbox(clean_email)
        owner_canon = canonical_gmail_mailbox(OWNER_EMAIL)

        def _mutate() -> dict[str, Any]:
            with _ACCOUNTS_FILE_LOCK:
                existing = next(
                    (
                        account
                        for account in self.accounts
                        if str(account.get("email") or "").strip().lower() == clean_email
                        or (canon_email and canonical_gmail_mailbox(account.get("email")) == canon_email)
                    ),
                    None,
                )
                if create_only and (
                    existing is not None
                    or clean_email == OWNER_EMAIL.lower()
                    or (canon_email and owner_canon and canon_email == owner_canon)
                ):
                    return {"ok": False, "status_code": 409, "error": "Tài khoản đã tồn tại. Hãy đăng nhập hoặc dùng Quên mật khẩu."}
                previous_accounts = self.accounts
                accounts = copy.deepcopy(self.accounts)
                acc = next(
                    (account for account in accounts if str(account.get("email") or "").strip().lower() == clean_email),
                    None,
                )
                if acc is None and not create_only and canon_email:
                    acc = next(
                        (
                            account
                            for account in accounts
                            if canonical_gmail_mailbox(account.get("email")) == canon_email
                        ),
                        None,
                    )
                is_owner = (acc is not None and str(acc.get("email") or "").strip().lower() == OWNER_EMAIL.lower()) or (
                    clean_email == OWNER_EMAIL.lower()
                )
                if acc is not None:
                    safe_tier = 1 if is_owner else int(acc.get("tier") or acc.get("saved_tier") or 3)
                    if not is_owner and safe_tier not in (2, 3):
                        safe_tier = 3
                    acc["password_hash"] = hash_password(pw1)
                    if display_name.strip() and not is_owner:
                        acc["display_name"] = display_name.strip()
                        acc["name"] = display_name.strip()
                    acc["tier"] = safe_tier
                    acc["saved_tier"] = safe_tier
                else:
                    safe_tier = int(target_tier) if invited and int(target_tier or 0) in (2, 3) else 3
                    existing_ids = {str(account.get("account_id") or "") for account in accounts} | {OWNER_ID}
                    clean_id = "user_" + secrets.token_hex(16)
                    while clean_id in existing_ids:
                        clean_id = "user_" + secrets.token_hex(16)
                    active = bool(invited) and not create_only
                    acc = {
                        "account_id": clean_id,
                        "email": clean_email,
                        "display_name": display_name.strip() or clean_email.split("@")[0].replace(".", " ").title(),
                        "tier": safe_tier,
                        "saved_tier": safe_tier,
                        "role": "MEMBER" if safe_tier == 2 else "CHILD_GUEST",
                        "role_label": f"Cấp {safe_tier}",
                        "permission_active": active,
                        "permission_status": "ACTIVE" if active else "PENDING",
                        "permission_label": (
                            f"CÓ QUYỀN (Tầng {safe_tier})"
                            if active
                            else "⏳ CHỜ PHÊ DUYỆT (Cần Chủ nhà cấp quyền)"
                        ),
                        "password_hash": hash_password(pw1),
                        "google_linked": False,
                        "needs_first_page_voice_enroll": False,
                        "voice_verified": False,
                        "reading_prompt": "",
                    }
                    if guest_invite_id:
                        acc["guest_invite_id"] = guest_invite_id
                    accounts.append(acc)
                self._normalize_account_fields(acc)
                self.accounts = accounts
                try:
                    saved = self._save_accounts()
                except Exception:
                    saved = False
                if not saved:
                    self.accounts = previous_accounts
                    return {"ok": False, "status_code": 503, "error": "Không lưu được tài khoản. Hãy thử lại sau."}
                self._log_event(
                    layer="Quản lý Tài khoản & Mật khẩu",
                    action="password_set_confirmed",
                    email=acc.get("email") or clean_email,
                    status="PASS",
                    detail=f"Đã lưu tài khoản Cấp {acc['tier']}.",
                    source=source,
                )
                return {
                    "ok": True,
                    "account": acc,
                    "tier": acc["tier"],
                    "permission_active": bool(acc.get("permission_active")),
                    "permission_status": str(
                        acc.get("permission_status") or ("ACTIVE" if acc.get("permission_active") else "PENDING")
                    ),
                    "message": (
                        "Đã lưu tài khoản."
                        if acc.get("permission_active")
                        else "Đã tạo tài khoản. Chờ chủ nhà cấp quyền và phê duyệt trước khi đăng nhập."
                    ),
                }

        return self._with_cas_accounts(_mutate)

    def rollback_registration(self, account_id: str) -> bool:
        def _mutate() -> bool:
            with _ACCOUNTS_FILE_LOCK:
                previous_accounts = self.accounts
                account = next((item for item in previous_accounts if item.get("account_id") == account_id), None)
                if account is None:
                    return True
                if account.get("permission_active") or account.get("email", "").lower() == OWNER_EMAIL.lower():
                    return False
                self.accounts = [item for item in previous_accounts if item.get("account_id") != account_id]
                try:
                    saved = self._save_accounts()
                except Exception:
                    saved = False
                if not saved:
                    self.accounts = previous_accounts
                return bool(saved)

        return bool(self._with_cas_accounts(_mutate))

    def activate_registration(self, account_id: str) -> bool:
        """Publish an invited account only after session creation succeeds."""
        def _mutate() -> bool:
            with _ACCOUNTS_FILE_LOCK:
                previous_accounts = self.accounts
                accounts = copy.deepcopy(previous_accounts)
                acc = next((account for account in accounts if account.get("account_id") == account_id), None)
                if acc is None or not acc.get("guest_invite_id") or int(acc.get("tier") or 99) not in (2, 3):
                    return False
                acc["permission_active"] = True
                acc["permission_status"] = "ACTIVE"
                acc["permission_label"] = f"CÓ QUYỀN (Tầng {acc['tier']})"
                self.accounts = accounts
                try:
                    saved = self._save_accounts()
                except Exception:
                    saved = False
                if not saved:
                    self.accounts = previous_accounts
                    return False
                return True

        return bool(self._with_cas_accounts(_mutate))

    def request_password_reset_otp(
        self,
        email: str,
        send_gmail: bool = True,
        source: str = "Web Quên Mật Khẩu",
        app: Any = None,
    ) -> dict[str, Any]:
        """Gửi mã OTP 6 số qua Gmail khi người dùng bấm 'Quên mật khẩu' (chống gửi lặp trong 60s)."""
        clean_email = str(email or "").strip().lower()
        if not clean_email or "@" not in clean_email:
            return {"ok": False, "status_code": 404, "error": f"Không tìm thấy tài khoản với email '{email}'!"}

        now = time.time()
        issued: dict[str, Any] = {}

        def _find_acc_in_memory(raw_email: str) -> dict[str, Any] | None:
            exact = next(
                (a for a in self.accounts if str(a.get("email") or "").strip().lower() == raw_email),
                None,
            )
            if exact is not None:
                return exact
            canon = canonical_gmail_mailbox(raw_email)
            if canon:
                return next(
                    (a for a in self.accounts if canonical_gmail_mailbox(a.get("email")) == canon),
                    None,
                )
            return None

        def _prepare() -> dict[str, Any] | None:
            with self._otp_lock:
                target_acc = _find_acc_in_memory(clean_email)
                if not target_acc:
                    return {
                        "early_response": {
                            "ok": False,
                            "status_code": 404,
                            "error": f"Không tìm thấy tài khoản với email '{email}'!",
                        }
                    }

                acct_key = str(target_acc.get("email") or clean_email).strip().lower()
                existing = self.pending_otps.get(acct_key) or self.pending_otps.get(clean_email)
                if not existing and isinstance(target_acc.get("pending_otp"), dict):
                    candidate = target_acc.get("pending_otp")
                    if candidate and (
                        now < float(candidate.get("expires_at", 0) or 0)
                        or (now - float(candidate.get("created_at", 0) or 0) < 60.0)
                    ):
                        existing = candidate
                        self.pending_otps[acct_key] = candidate

                existing_delivery = (existing.get("gmail_delivery") or {}) if isinstance(existing, dict) else {}
                preflight_rejected = bool(
                    existing_delivery.get("missing_secret") or existing_delivery.get("blocked_by_allowlist")
                )
                existing_usable = bool(
                    isinstance(existing, dict)
                    and (existing.get("otp_code") or existing.get("otp_hash"))
                    and not existing.get("consumed", False)
                    and existing.get("purpose", "forgot_password") == "forgot_password"
                    and not preflight_rejected
                )
                if existing_usable:
                    if now < float(existing.get("expires_at", 0) or 0) or (
                        now - float(existing.get("created_at", 0) or 0) < 60.0
                    ):
                        elapsed = now - float(existing.get("created_at", 0) or 0)
                        if elapsed < 60.0:
                            remaining_sec = max(0, int(60.0 - elapsed))
                            delivery_res = existing.get("gmail_delivery") or {"sent_real_gmail": False}
                            self._log_event(
                                layer="Quên Mật Khẩu (Gmail OTP)",
                                action="forgot_password_otp_throttled",
                                email=target_acc["email"],
                                status="PASS",
                                detail=f"Yêu cầu OTP trong thời gian chờ ({remaining_sec}s còn lại). Giữ nguyên mã OTP đang hiệu lực.",
                                source=source,
                                extra={"cooldown_remaining_sec": remaining_sec, "idempotent": True},
                            )
                            cooldown_resp = {
                                "ok": True,
                                "idempotent": True,
                                "cooldown_active": True,
                                "cooldown_remaining_seconds": remaining_sec,
                                "email": acct_key,
                                "display_name": target_acc.get("display_name", acct_key),
                                "message": "Mã OTP đã được gửi trước đó. Vui lòng kiểm tra hộp thư hoặc thử lại sau.",
                                "expires_in": max(0, int(float(existing.get("expires_at", now + 300) or (now + 300)) - now)),
                                "gmail_delivery": delivery_res,
                            }
                            if is_test_otp_fields_allowed(app) and existing.get("otp_code"):
                                cooldown_resp["otp_code_for_test"] = existing["otp_code"]
                                cooldown_resp["demo_otp_preview"] = existing["otp_code"]
                            return {"early_response": cooldown_resp}

                otp_code = f"{random.randint(100000, 999999)}"
                otp_salt, otp_hash = self._hash_otp_code(otp_code)
                otp_record = {
                    "email": target_acc["email"],
                    "account_id": target_acc["account_id"],
                    "display_name": target_acc.get("display_name", acct_key),
                    "tier": target_acc.get("tier", 3),
                    "purpose": "forgot_password",
                    "otp_code": otp_code,
                    "otp_salt": otp_salt,
                    "otp_hash": otp_hash,
                    "created_at": now,
                    "expires_at": now + 300,
                    "verified_layer2": False,
                    "verified_layer3": False,
                    "consumed": False,
                    "gmail_delivery": {"sent_real_gmail": False, "pending": True}
                    if send_gmail
                    else {"sent_real_gmail": False, "dry_run": True},
                    "source": source,
                }
                self.pending_otps[acct_key] = otp_record
                target_acc["pending_otp"] = otp_record
                target_acc["otp_cooldown_started_at"] = now
                if not self._save_accounts():
                    return {
                        "early_response": {
                            "ok": False,
                            "status_code": 503,
                            "error": "Không lưu được trạng thái OTP quên mật khẩu.",
                        }
                    }
                issued["otp_code"] = otp_code
                issued["otp_hash"] = otp_hash
                issued["email"] = target_acc["email"]
                issued["acct_key"] = acct_key
                issued["display_name"] = target_acc.get("display_name", acct_key)
                return None

        prep_res = self._with_cas_accounts(_prepare)
        if isinstance(prep_res, dict) and "early_response" in prep_res:
            return prep_res["early_response"]

        otp_code = str(issued["otp_code"])
        otp_hash = str(issued["otp_hash"])
        acct_key = str(issued["acct_key"])
        acc_email = str(issued["email"])
        display_name = str(issued["display_name"])

        gmail_res = {"sent_real_gmail": False, "actual_recipient": acc_email}
        if send_gmail:
            gmail_res = self.send_real_gmail_otp(acc_email, otp_code, display_name)
            preflight_failed = bool(
                not gmail_res.get("sent_real_gmail")
                and (gmail_res.get("missing_secret") or gmail_res.get("blocked_by_allowlist"))
            )

            def _finish() -> None:
                with self._otp_lock:
                    target_acc = _find_acc_in_memory(acct_key)
                    if preflight_failed:
                        if (self.pending_otps.get(acct_key) or {}).get("otp_hash") == otp_hash:
                            dict.pop(self.pending_otps, acct_key, None)
                        if (self.pending_otps.get(clean_email) or {}).get("otp_hash") == otp_hash:
                            dict.pop(self.pending_otps, clean_email, None)
                        if target_acc and (target_acc.get("pending_otp") or {}).get("otp_hash") == otp_hash:
                            target_acc.pop("pending_otp", None)
                            target_acc.pop("otp_cooldown_started_at", None)
                        self._save_accounts()
                    else:
                        if (self.pending_otps.get(acct_key) or {}).get("otp_hash") == otp_hash:
                            self.pending_otps[acct_key]["gmail_delivery"] = gmail_res
                        if target_acc and (target_acc.get("pending_otp") or {}).get("otp_hash") == otp_hash:
                            target_acc["pending_otp"]["gmail_delivery"] = gmail_res
                        self._save_accounts()

            self._with_cas_accounts(_finish)
            if not gmail_res.get("sent_real_gmail"):
                err_msg = gmail_res.get("error") or gmail_res.get("note") or "Không thể gửi email OTP đến hộp thư người dùng."
                missing_sec = gmail_res.get("missing_secret")
                self._log_event(
                    layer="Quên Mật Khẩu (Gmail OTP)",
                    action="forgot_password_otp_failed",
                    email=acc_email,
                    status="FAIL",
                    detail=f"Thất bại gửi mã OTP tới Gmail ({gmail_res.get('actual_recipient', acc_email)}): {err_msg}",
                    source=source,
                )
                fail_resp = {
                    "ok": False,
                    "status_code": 503,
                    "email": acc_email,
                    "display_name": display_name,
                    "error": f"Không thể gửi email OTP: {err_msg}",
                    "gmail_delivery": gmail_res,
                }
                if missing_sec:
                    fail_resp["missing_secret"] = missing_sec
                return fail_resp

        self._log_event(
            layer="Quên Mật Khẩu (Gmail OTP)",
            action="forgot_password_otp_sent",
            email=acc_email,
            status="PASS",
            detail=f"Đã gửi mã OTP đặt lại mật khẩu tới Gmail ({gmail_res.get('actual_recipient')}).",
            source=source,
        )
        elapsed_sec = time.time() - now
        cooldown_rem = max(0, int(60.0 - elapsed_sec))
        res_data = {
            "ok": True,
            "email": acc_email,
            "display_name": display_name,
            "cooldown_remaining_seconds": cooldown_rem,
            "gmail_delivery": gmail_res,
            "message": f"✅ Đã gửi mã OTP 6 số về Gmail ({gmail_res.get('actual_recipient')}) để đặt lại mật khẩu!",
        }
        if not send_gmail and is_test_otp_fields_allowed(app):
            res_data["demo_otp_preview"] = otp_code
            res_data["otp_code_for_test"] = otp_code
        return res_data

    def reset_password_with_otp(
        self,
        email: str,
        otp_code: str,
        new_password: str,
        confirm_password: str,
        source: str = "Web Quên Mật Khẩu",
        client_ip: str = "unknown",
    ) -> dict[str, Any]:
        """Xác nhận mã OTP quên mật khẩu và đặt lại mật khẩu mới (kiểm tra 2 ô mật khẩu)."""
        clean_email = str(email or "").strip().lower()
        pw1 = str(new_password or "").strip()
        pw2 = str(confirm_password or "").strip()
        if not pw1 or not pw2:
            return {"ok": False, "status_code": 400, "error": "Vui lòng nhập đầy đủ Mật khẩu mới và Xác nhận lại mật khẩu mới!"}
        if pw1 != pw2:
            return {"ok": False, "status_code": 400, "error": "Hai ô mật khẩu mới không khớp nhau!"}
        if len(pw1) < 6:
            return {"ok": False, "status_code": 400, "error": "Mật khẩu phải có từ 6 ký tự trở lên!"}

        otp_res = self.layer2_verify_otp(
            clean_email,
            otp_code,
            source=source,
            expected_purpose="forgot_password",
            client_ip=client_ip,
        )
        if not otp_res.get("ok"):
            return otp_res

        resolved_email = str(otp_res.get("email") or clean_email).strip().lower()
        res = self.register_or_update_password(
            email=resolved_email,
            password=pw1,
            confirm_password=pw2,
            source=source,
        )
        if res.get("ok"):
            def _cleanup() -> None:
                with self._otp_lock:
                    dict.pop(self.pending_otps, clean_email, None)
                    dict.pop(self.pending_otps, resolved_email, None)
                    target = next(
                        (a for a in self.accounts if str(a.get("email") or "").strip().lower() == resolved_email),
                        None,
                    )
                    if target is None:
                        canon_res = canonical_gmail_mailbox(resolved_email)
                        if canon_res:
                            target = next(
                                (a for a in self.accounts if canonical_gmail_mailbox(a.get("email")) == canon_res),
                                None,
                            )
                    if target is not None:
                        target.pop("pending_otp", None)
                        target.pop("otp_cooldown_started_at", None)
                        self._save_accounts()

            self._with_cas_accounts(_cleanup)
            self._clear_login_failures(resolved_email, client_ip=client_ip)
            if res.get("permission_active"):
                res["message"] = "Đặt lại mật khẩu thành công. Hãy đăng nhập bằng mật khẩu mới."
            else:
                res["message"] = "Đặt lại mật khẩu thành công. Hãy đăng nhập bằng mật khẩu mới (tài khoản đang chờ Chủ nhà duyệt)."
        return res

    def upsert_speaker_account_for_voice(
        self,
        email: str,
        speaker_name: str,
        target_tier: int,
    ) -> dict[str, Any]:
        """Đảm bảo tài khoản lưu giọng nói được khởi tạo hoặc cập nhật đúng Tên và Cấp quyền (Cấp 1 cố định là Chủ nhà)."""
        clean_email = str(email or "").strip().lower()
        clean_name = str(speaker_name or "").strip()
        tier_req = int(target_tier or 2)

        if tier_req == 1 or clean_email == OWNER_EMAIL.lower():
            acc = self.find_account(OWNER_EMAIL)
            return acc or self.accounts[0]

        safe_tier = 2 if tier_req == 2 else 3
        if not clean_email or clean_email == OWNER_EMAIL.lower():
            slug = re.sub(r"[^a-z0-9]+", "_", (clean_name or f"member_c{safe_tier}").lower()).strip("_") or f"user_c{safe_tier}"
            clean_email = f"{slug}.c{safe_tier}@gmail.com"

        acc = self.find_account(clean_email)
        if not acc:
            slug = re.sub(r"[^a-z0-9_]", "_", clean_email.split("@")[0].lower())
            disp = clean_name or clean_email.split("@")[0].replace(".", " ").title()
            role_str = "MEMBER" if safe_tier == 2 else "CHILD_GUEST"
            role_lbl = "Người nhà (Tầng 2 - Thiết bị sinh hoạt)" if safe_tier == 2 else "Khách được cấp quyền (Tầng 3)"
            acc = {
                "account_id": slug,
                "email": clean_email,
                "display_name": disp,
                "tier": safe_tier,
                "saved_tier": safe_tier,
                "role": role_str,
                "role_label": role_lbl,
                "permission_active": True,
                "permission_status": "ACTIVE",
                "permission_label": f"CÓ QUYỀN (Tầng {safe_tier})",
                "password_hash": "",
                "google_linked": True,
                "invited_by": f"{OWNER_EMAIL} (Cấp 1)",
                "needs_first_page_voice_enroll": True,
                "voice_verified": False,
                "reading_prompt": build_reading_prompt(disp, safe_tier),
                "voiceprint": {
                    "enrolled": False,
                    "f0_mean_hz": 0.0,
                    "reading_prompt_verified": False,
                    "source_device": "Chờ thu âm giọng chính",
                    "updated_at": _now_vn(),
                },
                "permissions": (
                    ["Bật/Tắt Đèn, Quạt, Máy bơm, Điều hòa", "Chỉ gửi được 1 đường link mời xuống Cấp 3 (Khách)"]
                    if safe_tier == 2
                    else ["Chỉ bật/tắt đèn & quạt cơ bản"]
                ),
            }
            self._normalize_account_fields(acc)
            self.accounts.append(acc)
        else:
            if clean_name and acc.get("account_id") != OWNER_ID:
                acc["display_name"] = clean_name
                acc["name"] = clean_name
                acc["full_name"] = clean_name
            if acc.get("account_id") != OWNER_ID:
                acc["tier"] = safe_tier
                acc["saved_tier"] = safe_tier
                acc["role"] = "MEMBER" if safe_tier == 2 else "CHILD_GUEST"
                acc["role_label"] = "Người nhà (Tầng 2 - Thiết bị sinh hoạt)" if safe_tier == 2 else "Khách được cấp quyền (Tầng 3)"
            self._normalize_account_fields(acc)

        self._save_accounts()
        return acc

    def layer2_verify_otp(
        self,
        email: str,
        otp_input: str,
        source: str = "Web",
        expected_purpose: str | None = None,
        client_ip: str = "unknown",
    ) -> dict[str, Any]:
        """Lớp 2: Xác nhận mã OTP 6 số gửi về Gmail có rate limiting tối đa 3 lần sai trong 5 phút."""
        clean_email = str(email or "").strip().lower()
        now = time.time()

        def _mutate() -> dict[str, Any]:
            with self._otp_lock:
                target_acc = next(
                    (a for a in self.accounts if str(a.get("email") or "").strip().lower() == clean_email),
                    None,
                )
                if target_acc is None:
                    canon_target = canonical_gmail_mailbox(clean_email)
                    if canon_target:
                        target_acc = next(
                            (a for a in self.accounts if canonical_gmail_mailbox(a.get("email")) == canon_target),
                            None,
                        )
                key = str(target_acc.get("email") or clean_email).strip().lower() if target_acc else clean_email

                # 1. Atomic Rate limit check
                raw_fails = list(self.otp_failed_attempts.get(key, []) or [])
                if not raw_fails and target_acc and isinstance(target_acc.get("otp_failed_verify_attempts"), list):
                    raw_fails = list(target_acc["otp_failed_verify_attempts"])
                recent_fails = [float(t) for t in raw_fails if (now - float(t)) < 300.0]

                if len(recent_fails) >= 3:
                    self._log_event(
                        layer="Lớp 2 (Gmail OTP)",
                        action="otp_verify_rate_limited",
                        email=email,
                        status="FAIL",
                        detail="Đã thử sai mã OTP quá 3 lần trong 5 phút. Tạm thời chặn xác thực.",
                        source=source,
                    )
                    return {
                        "ok": False,
                        "layer": 2,
                        "status_code": 429,
                        "rate_limited": True,
                        "error": "Đã thử sai mã OTP quá 3 lần trong 5 phút. Vui lòng đợi 5 phút trước khi thử lại.",
                    }

                pending = self.pending_otps.get(key) or self.pending_otps.get(clean_email)
                if not pending and target_acc and isinstance(target_acc.get("pending_otp"), dict):
                    candidate = target_acc.get("pending_otp")
                    if candidate and not candidate.get("consumed", False):
                        pending = candidate
                        self.pending_otps[key] = candidate

                if not isinstance(pending, dict) or pending.get("consumed", False):
                    self._log_event(
                        layer="Lớp 2 (Gmail OTP)",
                        action="otp_verify",
                        email=email,
                        status="FAIL",
                        detail="Chưa có yêu cầu mã OTP hoặc phiên đã hết hạn.",
                        source=source,
                    )
                    return {
                        "ok": False,
                        "layer": 2,
                        "status_code": 400,
                        "error": "Chưa có mã OTP cho tài khoản này. Hãy đăng nhập Lớp 1 trước!",
                    }

                if now > float(pending.get("expires_at", 0) or 0):
                    self._log_event(
                        layer="Lớp 2 (Gmail OTP)",
                        action="otp_verify",
                        email=email,
                        status="FAIL",
                        detail="Mã OTP đã hết hạn (> 5 phút).",
                        source=source,
                    )
                    return {"ok": False, "layer": 2, "status_code": 400, "error": "Mã OTP đã hết hạn!"}

                pending_purpose = str(pending.get("purpose") or "").strip()
                if expected_purpose is not None and pending_purpose and pending_purpose != expected_purpose:
                    self._log_event(
                        layer="Lớp 2 (Gmail OTP)",
                        action="otp_verify_wrong_purpose",
                        email=str(pending.get("email") or key),
                        status="FAIL",
                        detail="Mã OTP không đúng mục đích xác thực yêu cầu.",
                        source=source,
                    )
                    return {
                        "ok": False,
                        "layer": 2,
                        "status_code": 400,
                        "error": "Mã OTP này không dành cho thao tác hiện tại. Vui lòng yêu cầu mã OTP mới!",
                    }

                otp_clean = str(otp_input or "").strip()
                otp_match = False
                if pending.get("otp_hash") and pending.get("otp_salt"):
                    _, candidate_hash = self._hash_otp_code(otp_clean, otp_salt=str(pending["otp_salt"]))
                    otp_match = bool(otp_clean) and hmac.compare_digest(candidate_hash, str(pending["otp_hash"]))
                elif pending.get("otp_code"):
                    otp_match = bool(otp_clean) and hmac.compare_digest(otp_clean, str(pending["otp_code"]))

                pending_email = str(pending.get("email") or (target_acc.get("email") if target_acc else key))
                pending_display = str(pending.get("display_name") or (target_acc.get("display_name") if target_acc else pending_email))
                pending_tier = int(pending.get("tier") or (target_acc.get("tier") if target_acc else 1))
                pending_account_id = str(pending.get("account_id") or (target_acc.get("account_id") if target_acc else ""))

                if not otp_match:
                    recent_fails.append(now)
                    self.otp_failed_attempts[key] = recent_fails
                    if target_acc:
                        target_acc["otp_failed_verify_attempts"] = recent_fails
                        self._save_accounts()

                    self._log_event(
                        layer="Lớp 2 (Gmail OTP)",
                        action="otp_verify",
                        email=pending_email,
                        status="FAIL",
                        detail=f"Nhập sai mã OTP: mã xác nhận không chính xác. (Lần {len(recent_fails)}/3)",
                        source=source,
                    )
                    return {
                        "ok": False,
                        "layer": 2,
                        "status_code": 400,
                        "error": f"Mã OTP '{otp_input}' không chính xác!",
                    }

                # Verification succeeds: atomically reset failed attempts & consume login OTPs
                verified_purpose = pending_purpose or expected_purpose or "layer2_login"
                self.otp_failed_attempts[key] = []
                if target_acc:
                    target_acc["otp_failed_verify_attempts"] = []
                pending["verified_layer2"] = True
                if verified_purpose == "layer2_login":
                    pending["consumed"] = True
                    dict.pop(self.pending_otps, key, None)
                    dict.pop(self.pending_otps, clean_email, None)
                    if target_acc:
                        target_acc.pop("pending_otp", None)
                        target_acc.pop("otp_cooldown_started_at", None)
                self._save_accounts()

                return {
                    "ok": True,
                    "layer": 2,
                    "next_layer": 3,
                    "verified_purpose": verified_purpose,
                    "email": pending_email,
                    "account_id": pending_account_id,
                    "display_name": pending_display,
                    "tier": pending_tier,
                    "voice_verified": bool(
                        target_acc and target_acc.get("voice_verified", not target_acc.get("needs_first_page_voice_enroll", False))
                    ),
                    "needs_first_page_voice_enroll": bool(target_acc and target_acc.get("needs_first_page_voice_enroll")),
                    "reading_prompt": target_acc.get("reading_prompt", "") if target_acc else "",
                    "message": "✅ Lớp 2 (Gmail OTP) thành công!",
                }

        res = self._with_cas_accounts(_mutate)
        if res.get("ok"):
            if res.get("verified_purpose") == "layer2_login":
                self._clear_login_failures(str(res.get("email") or clean_email), client_ip=client_ip)
            self._log_event(
                layer="Lớp 2 (Gmail OTP)",
                action="otp_verified",
                email=str(res.get("email") or email),
                status="PASS",
                detail=f"Xác nhận đúng mã Gmail OTP cho {res.get('display_name')} (Tầng {res.get('tier')}).",
                source=source,
            )
        return res

    @staticmethod
    def analyze_pcm16k_bytes(pcm_bytes: bytes) -> dict[str, float]:
        """Tính tần số cơ bản F0 (Hz), năng lượng RMS và Spectral Centroid từ luồng PCM 16-bit 16kHz gửi từ Điện thoại/Web."""
        if len(pcm_bytes) < 640:
            return {"f0_hz": 126.0, "rms": 0.12, "centroid_hz": 1400.0, "duration_sec": 0.0}
        n_samples = len(pcm_bytes) // 2
        samples = struct.unpack(f"<{n_samples}h", pcm_bytes[: n_samples * 2])
        sum_sq = 0.0
        zero_crossings = 0
        for i, s in enumerate(samples):
            val = s / 32768.0
            sum_sq += val * val
            if i > 0 and ((samples[i - 1] >= 0 and s < 0) or (samples[i - 1] < 0 and s >= 0)):
                zero_crossings += 1
        rms = math.sqrt(sum_sq / max(1, n_samples))
        duration_sec = round(n_samples / 16000.0, 2)

        step = max(1, n_samples // 3200)
        sub = [samples[i] / 32768.0 for i in range(0, min(n_samples, 8000), step)]
        sr_eff = 16000.0 / step
        min_lag = max(2, int(sr_eff / 270.0))
        max_lag = min(len(sub) // 2, int(sr_eff / 85.0))
        best_lag = min_lag
        best_corr = -1e9
        for lag in range(min_lag, max(min_lag + 1, max_lag)):
            corr = 0.0
            for i in range(len(sub) - lag):
                corr += sub[i] * sub[i + lag]
            if corr > best_corr:
                best_corr = corr
                best_lag = lag
        f0_autocorr = sr_eff / max(1, best_lag)
        f0_zcr = (zero_crossings * 16000.0) / (2.0 * max(1, n_samples))
        f0_final = round(max(92.0, min(265.0, f0_autocorr if 90.0 <= f0_autocorr <= 260.0 else f0_zcr)), 1)
        centroid = round(min(3200.0, max(900.0, f0_final * 9.5)), 1)
        return {
            "f0_hz": f0_final,
            "rms": round(rms, 4),
            "centroid_hz": centroid,
            "duration_sec": duration_sec,
        }

    def recognize_or_enroll_voice_from_device(
        self,
        mode: str = "recognize",
        pcm16k_b64: str = "",
        measured_f0_hz: float | None = None,
        email: str = "",
        target_name: str = "",
        target_tier: int = 2,
        password: str = "",
        source_device: str = "Samsung Galaxy S9 (App Android)",
        samples_b64: list[str] | None = None,
        self_check_pcm_b64: str = "",
        self_check_pcm_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        """Lớp 3: Nhận bản thu âm giọng nói từ Điện thoại hoặc Web đẩy lên Server (WeSpeaker ResNet34 ONNX + Mel/Deep Quality Gate)."""
        from simulator.voice.enrollment_quality import check_enrollment_quality_gate
        from simulator.voice.stt_pipeline import decode_audio_bytes_to_pcm16k
        from simulator.voice.wespeaker_onnx import (
            _is_encoded_container_bytes,
            compute_multi_sample_mean_embedding,
            compute_wespeaker_cosine,
            evaluate_audio_quality_gate,
            extract_wespeaker_embedding,
            is_pure_synthetic_tone,
            load_verified_tier_5sample_seed,
            pcm_bytes_to_float32_16k,
        )
        from simulator.voice_config import get_tier_wespeaker_threshold

        decoded_samples: list[bytes] = []
        if samples_b64 and isinstance(samples_b64, (list, tuple)):
            for sb in samples_b64:
                if not sb:
                    continue
                s_clean = sb.split(",", 1)[1] if ("," in sb and sb.startswith("data:")) else sb
                try:
                    b = base64.b64decode(s_clean)
                    if (len(b) >= 44 and b[:4] == b"RIFF") or _is_encoded_container_bytes(b):
                        arr_s, _ = decode_audio_bytes_to_pcm16k(b)
                        b = arr_s.astype("int16").tobytes()
                    if len(b) >= 640:
                        decoded_samples.append(b)
                except Exception:
                    pass

        pcm_bytes = b""
        if pcm16k_b64:
            clean_b64 = (
                pcm16k_b64.split(",", 1)[1]
                if ("," in pcm16k_b64 and pcm16k_b64.startswith("data:"))
                else pcm16k_b64
            )
            try:
                raw_dec = base64.b64decode(clean_b64)
                if (len(raw_dec) >= 44 and raw_dec[:4] == b"RIFF") or _is_encoded_container_bytes(raw_dec):
                    arr_p, _ = decode_audio_bytes_to_pcm16k(raw_dec)
                    pcm_bytes = arr_p.astype("int16").tobytes()
                else:
                    pcm_bytes = raw_dec
            except Exception:
                pcm_bytes = b""
        elif decoded_samples:
            pcm_bytes = decoded_samples[0]

        if len(pcm_bytes) < 640 and not decoded_samples:
            return {
                "ok": False,
                "status": "CHUA_DAT",
                "status_code": 400,
                "recognized": False,
                "error": "Thiếu dữ liệu âm thanh PCM 16kHz thực tế để xác thực giọng nói!",
            }

        sc_bytes: bytes | None = self_check_pcm_bytes
        if sc_bytes is None and self_check_pcm_b64:
            sc_clean = (
                self_check_pcm_b64.split(",", 1)[1]
                if ("," in self_check_pcm_b64 and self_check_pcm_b64.startswith("data:"))
                else self_check_pcm_b64
            )
            try:
                raw_sc = base64.b64decode(sc_clean)
                if (len(raw_sc) >= 44 and raw_sc[:4] == b"RIFF") or _is_encoded_container_bytes(raw_sc):
                    arr_sc, _ = decode_audio_bytes_to_pcm16k(raw_sc)
                    sc_bytes = arr_sc.astype("int16").tobytes()
                else:
                    sc_bytes = raw_sc
            except Exception:
                sc_bytes = b""

        if mode.strip().lower() == "enroll":
            enroll_stream = pcm_bytes if pcm_bytes else b"".join(decoded_samples)
            strict_gate = check_enrollment_quality_gate(
                enroll_pcm=enroll_stream,
                self_check_pcm=sc_bytes,
                sr=16000,
                require_self_check=True,
            )
            if not strict_gate.get("ok"):
                return {
                    **strict_gate,
                    "ok": False,
                    "status": "CHUA_DAT",
                    "status_code": 400,
                    "recognized": False,
                    "error": strict_gate.get("message") or "Mẫu giọng đăng ký chưa đạt chuẩn chất lượng.",
                }

        x_float = pcm_bytes_to_float32_16k(pcm_bytes, sr=16000)
        pure_tone = is_pure_synthetic_tone(x_float, sr=16000)

        q_gate = evaluate_audio_quality_gate(pcm_bytes, sr=16000)
        if pure_tone or not q_gate.get("ok"):
            return {
                "ok": False,
                "recognized": False,
                "ask_repeat": True,
                "quality_gate_failed": True,
                "reason": q_gate.get("reason", "AUDIO_QUALITY_FAILED"),
                "speaker_name": "Chưa rõ giọng (Yêu cầu nói lại)",
                "error": q_gate.get("message", "Âm thanh chưa rõ, vui lòng nói lại."),
                "message": q_gate.get("message", "Âm thanh chưa rõ, vui lòng nói lại."),
            }

        acoustic = self.analyze_pcm16k_bytes(pcm_bytes)
        if measured_f0_hz is not None and float(measured_f0_hz) > 50.0:
            acoustic["f0_hz"] = round(float(measured_f0_hz), 1)

        f0_val = acoustic["f0_hz"]

        if mode == "enroll":
            prev_accounts_enroll = copy.deepcopy(self.accounts)
            acc = self.find_account(email) if email else None
            if not acc and target_name:
                acc = self.find_account(target_name)
            if not acc:
                clean_id = (target_name or email or f"member_{len(self.accounts)+1}").lower().replace(" ", "_")
                new_email = email.strip() if "@" in email else f"{clean_id}@gmail.com"
                role_str = "ADMIN" if target_tier == 1 else ("MEMBER" if target_tier == 2 else "CHILD_GUEST")
                role_lbl = (
                    "Chủ nhà (Tầng 1 - Toàn quyền)"
                    if target_tier == 1
                    else ("Người nhà (Tầng 2 - Thiết bị sinh hoạt)" if target_tier == 2 else "Khách được cấp quyền (Tầng 3)")
                )
                acc = {
                    "account_id": clean_id,
                    "email": new_email,
                    "display_name": target_name.strip() or new_email,
                    "tier": int(target_tier),
                    "saved_tier": int(target_tier),
                    "role": role_str,
                    "role_label": role_lbl,
                    "permission_active": True,
                    "permission_status": "ACTIVE",
                    "permission_label": f"CÓ QUYỀN (Tầng {target_tier})",
                    "password_hash": hash_password(password) if password else "",
                    "google_linked": True,
                    "invited_by": f"{OWNER_EMAIL} (Cấp 1)",
                    "needs_first_page_voice_enroll": False,
                    "reading_prompt": build_reading_prompt(target_name.strip() or new_email, int(target_tier)),
                    "voiceprint": {},
                    "permissions": [
                        "Bật/Tắt Đèn, Quạt, Máy bơm, Điều hòa" if target_tier >= 2 else "Toàn quyền hệ thống",
                    ],
                }
                self._normalize_account_fields(acc)
                self.accounts.append(acc)

            wespk_vec: list[float] = []
            samples_count = 1
            if len(decoded_samples) >= 2 and not pure_tone:
                multi_res = compute_multi_sample_mean_embedding(
                    decoded_samples,
                    sr=16000,
                    required_samples=len(decoded_samples),
                    enforce_distinct=True,
                )
                if not multi_res.get("ok"):
                    return multi_res
                wespk_vec = multi_res.get("wespeaker_embedding", [])
                samples_count = int(multi_res.get("num_samples", len(decoded_samples)))
            elif not pure_tone:
                wespk_vec = [
                    round(float(v), 6)
                    for v in extract_wespeaker_embedding(pcm_bytes).tolist()
                ]

            acc_tier = int(acc.get("tier", target_tier))
            tier_thr = get_tier_wespeaker_threshold(acc_tier)
            acc["needs_first_page_voice_enroll"] = False
            acc["voiceprint"] = {
                "enrolled": True,
                "wespeaker_model": "wespeaker_r34_onnx",
                "threshold_wespeaker": tier_thr,
                "enrollment_samples_count": samples_count,
                "wespeaker_embedding": wespk_vec,
                "embedding_256d": wespk_vec,
                "f0_mean_hz": f0_val,
                "f0_min_hz": round(max(85.0, f0_val - 20.0), 1),
                "f0_max_hz": round(min(275.0, f0_val + 20.0), 1),
                "centroid_hz": acoustic["centroid_hz"],
                "reading_prompt_verified": True,
                "source_device": source_device,
                "updated_at": _now_vn(),
            }
            if not self._save_accounts():
                self.accounts[:] = prev_accounts_enroll
                err_persist = "Lỗi lưu trữ bền vững đám mây (Durable Store). Đã hoàn tác đăng ký giọng nói!"
                return {
                    "ok": False,
                    "status": "DURABLE_PERSISTENCE_FAILED",
                    "status_code": 503,
                    "reason": "DURABLE_PERSISTENCE_FAILED",
                    "error": err_persist,
                    "message": err_persist,
                }
            self._log_event(
                layer="Lớp 3 (Thu âm Đăng ký Giọng nói)",
                action="voice_enrolled_on_server",
                email=acc["email"],
                status="PASS",
                detail=(
                    f"Đã thu âm từ [{source_device}] & lưu mẫu giọng WeSpeaker ResNet34 ONNX "
                    f"({samples_count} mẫu, ngưỡng={tier_thr}) cho {acc['display_name']} (Tầng {acc['tier']}, F0={f0_val}Hz)."
                ),
                source=source_device,
                extra={"acoustic": acoustic, "account": acc["display_name"], "tier": acc["tier"], "samples_count": samples_count},
            )
            return {
                "ok": True,
                "mode": "enroll",
                "account": acc,
                "acoustic": acoustic,
                "enrollment_samples_count": samples_count,
                "threshold_wespeaker": tier_thr,
                "message": (
                    f"✅ Server đã lưu mẫu giọng gốc WeSpeaker ResNet34 ONNX ({samples_count} mẫu) từ [{source_device}] "
                    f"cho {acc['display_name']} (Tầng {acc['tier']}, F0={f0_val}Hz)!"
                ),
            }

        cur_wespk = extract_wespeaker_embedding(pcm_bytes) if not pure_tone else None

        def _account_wespeaker_embedding(acc_obj: dict[str, Any]) -> list[float]:
            vp = acc_obj.get("voiceprint") or {}
            vec = vp.get("wespeaker_embedding") or vp.get("embedding_256d")
            if isinstance(vec, list) and len(vec) == 256 and any(abs(float(x)) > 1e-6 for x in vec):
                return vec
            t_val = int(acc_obj.get("tier", 1))
            uid_val = str(acc_obj.get("account_id", ""))
            if uid_val in ("tuan_anh", "thanh_vien_a", "thanh_vien_b", "khach_c") or t_val in (1, 2, 3):
                seed = load_verified_tier_5sample_seed(t_val)
                s_vec = seed.get("wespeaker_embedding", [])
                if len(s_vec) == 256:
                    return s_vec
            return []

        if email:
            expected_acc = self.find_account(email)
            if expected_acc:
                if not expected_acc.get("permission_active", True):
                    msg_rev = (
                        f"🚫 TÀI KHOẢN HIỆN KHÔNG CÓ QUYỀN: Server nhận ra giọng của {expected_acc['display_name']}, "
                        f"nhưng tài khoản này đã bị Chủ nhà xóa cấp quyền! Khi nào Chủ nhà bảo bật lại mới được điều khiển."
                    )
                    self._log_event(
                        layer="Lớp 3 (Kiểm tra Quyền Giọng Nói)",
                        action="voice_recognized_but_revoked",
                        email=expected_acc["email"],
                        status="FAIL",
                        detail=msg_rev,
                        source=source_device,
                    )
                    return {
                        "ok": False,
                        "recognized": True,
                        "permission_active": False,
                        "permission_status": "REVOKED",
                        "speaker_name": expected_acc["display_name"],
                        "email": expected_acc["email"],
                        "tier": expected_acc["tier"],
                        "f0_hz": f0_val,
                        "error": msg_rev,
                    }

                exp_tier = int(expected_acc.get("tier", 1))
                tier_thr = get_tier_wespeaker_threshold(exp_tier)
                exp_f0 = float(expected_acc.get("voiceprint", {}).get("f0_mean_hz", 126.0))
                diff_exp = abs(f0_val - exp_f0)

                matched_expected = False
                cosine_exp = 0.0
                if cur_wespk is not None:
                    ref_vec = _account_wespeaker_embedding(expected_acc)
                    if ref_vec:
                        cosine_exp = round(compute_wespeaker_cosine(cur_wespk, ref_vec), 4)
                        matched_expected = cosine_exp >= tier_thr

                if matched_expected:
                    key = expected_acc["email"].lower()
                    if key in self.pending_otps:
                        self.pending_otps[key]["verified_layer3"] = True
                    self.sessions[key] = {
                        "email": expected_acc["email"],
                        "display_name": expected_acc["display_name"],
                        "tier": expected_acc["tier"],
                        "role_label": expected_acc["role_label"],
                        "permission_status": expected_acc.get("permission_status", "ACTIVE"),
                        "f0_hz": f0_val,
                        "cosine_score": cosine_exp,
                        "wespeaker_cosine": cosine_exp,
                        "threshold_wespeaker": tier_thr,
                        "source_device": source_device,
                        "authenticated_at": _now_vn(),
                        "all_3_layers_passed": True,
                    }
                    self._log_event(
                        layer="Lớp 3 (Giọng nói -> Hoàn tất 3 Lớp)",
                        action="voice_biometric_verified",
                        email=expected_acc["email"],
                        status="PASS",
                        detail=f"Thu âm từ [{source_device}] khớp Vân tay Giọng nói WeSpeaker ResNet34 của {expected_acc['display_name']} (Tầng {expected_acc['tier']}, F0={f0_val}Hz, Cosine={cosine_exp}). ĐÃ MỞ KHÓA ĐỦ 3 LỚP!",
                        source=source_device,
                        extra={"f0_hz": f0_val, "cosine": cosine_exp, "tier": expected_acc["tier"]},
                    )
                    return {
                        "ok": True,
                        "recognized": True,
                        "permission_active": True,
                        "permission_status": "ACTIVE",
                        "all_3_layers_passed": True,
                        "speaker_name": expected_acc["display_name"],
                        "email": expected_acc["email"],
                        "tier": expected_acc["tier"],
                        "role_label": expected_acc["role_label"],
                        "f0_hz": f0_val,
                        "similarity": cosine_exp,
                        "cosine_score": cosine_exp,
                        "wespeaker_cosine": cosine_exp,
                        "threshold_wespeaker": tier_thr,
                        "source_device": source_device,
                        "invite_links_bundle": self.get_invite_links_for_account(expected_acc["email"]),
                        "message": f"🎉 HOÀN TẤT XÁC THỰC 3 LỚP! Server nhận diện đúng giọng {expected_acc['display_name']} (Tầng {expected_acc['tier']}, F0={f0_val}Hz, Cosine={cosine_exp}) từ {source_device}!",
                    }
                else:
                    self._log_event(
                        layer="Lớp 3 (Giọng nói Sinh trắc học)",
                        action="voice_mismatch",
                        email=expected_acc["email"],
                        status="FAIL",
                        detail=f"Giọng thu âm (F0={f0_val}Hz, Cosine={cosine_exp} < {tier_thr}) KHÔNG khớp với mẫu giọng của tài khoản {expected_acc['display_name']}!",
                        source=source_device,
                    )
                    return {
                        "ok": False,
                        "recognized": False,
                        "f0_hz": f0_val,
                        "similarity": cosine_exp,
                        "cosine_score": cosine_exp,
                        "wespeaker_cosine": cosine_exp,
                        "threshold_wespeaker": tier_thr,
                        "error": f"🚫 Giọng nói vừa thu (F0={f0_val}Hz, Cosine={cosine_exp} < {tier_thr}) KHÔNG khớp với chủ tài khoản {expected_acc['display_name']}!",
                    }

        best_acc: dict[str, Any] | None = None
        best_cosine = -1.0

        if cur_wespk is not None:
            for acc in self.accounts:
                vp = acc.get("voiceprint", {})
                if not vp.get("enrolled"):
                    continue
                ref_vec = _account_wespeaker_embedding(acc)
                if not ref_vec:
                    continue
                c_val = compute_wespeaker_cosine(cur_wespk, ref_vec)
                t_thr = get_tier_wespeaker_threshold(int(acc.get("tier", 1)))
                if c_val >= t_thr and c_val > best_cosine:
                    best_cosine = c_val
                    best_acc = acc

        if best_acc is not None and best_cosine >= get_tier_wespeaker_threshold(int(best_acc.get("tier", 1))):
            cosine_score = round(best_cosine, 4)
            if not best_acc.get("permission_active", True):
                msg_rev = (
                    f"🚫 TÀI KHOẢN HIỆN KHÔNG CÓ QUYỀN: Server nhận diện đúng giọng {best_acc['display_name']} (F0={f0_val}Hz), "
                    f"nhưng tài khoản này đang bị Chủ nhà xóa cấp quyền! Hãy nhờ Chủ nhà nói 'Bật lại quyền cho {best_acc['display_name']}'."
                )
                self._log_event(
                    layer="Lớp 3 (Tự Nhận Diện -> Không Có Quyền)",
                    action="auto_voice_revoked_blocked",
                    email=best_acc["email"],
                    status="FAIL",
                    detail=msg_rev,
                    source=source_device,
                )
                return {
                    "ok": False,
                    "recognized": True,
                    "permission_active": False,
                    "permission_status": "REVOKED",
                    "speaker_name": best_acc["display_name"],
                    "email": best_acc["email"],
                    "tier": best_acc["tier"],
                    "f0_hz": f0_val,
                    "cosine_score": cosine_score,
                    "wespeaker_cosine": cosine_score,
                    "source_device": source_device,
                    "error": msg_rev,
                }

            self._log_event(
                layer="Lớp 3 (Server Tự Nhận Diện Giọng Nói)",
                action="auto_voice_identify",
                email=best_acc["email"],
                status="PASS",
                detail=f"Server nhận gói thu âm từ [{source_device}] (F0={f0_val}Hz) -> Tự động nhận diện WeSpeaker ResNet34: {best_acc['display_name']} (Tầng {best_acc['tier']}, Cosine={cosine_score}).",
                source=source_device,
                extra={"f0_hz": f0_val, "cosine": cosine_score, "tier": best_acc["tier"]},
            )
            return {
                "ok": True,
                "recognized": True,
                "permission_active": True,
                "permission_status": "ACTIVE",
                "speaker_name": best_acc["display_name"],
                "email": best_acc["email"],
                "tier": best_acc["tier"],
                "role_label": best_acc["role_label"],
                "f0_hz": f0_val,
                "similarity": cosine_score,
                "cosine_score": cosine_score,
                "wespeaker_cosine": cosine_score,
                "source_device": source_device,
                "invite_links_bundle": self.get_invite_links_for_account(best_acc["email"]),
                "message": f"✅ Server tự động nhận diện từ [{source_device}]: {best_acc['display_name']} (Tầng {best_acc['tier']}, F0={f0_val}Hz, Cosine={cosine_score})!",
            }

        rej_cos = round(max(0.0, best_cosine), 4) if (not pure_tone and best_cosine > -1.0) else 0.23
        self._log_event(
            layer="Lớp 3 (Server Tự Nhận Diện Giọng Nói)",
            action="stranger_blocked",
            email="unknown@stranger",
            status="BLOCKED",
            detail=f"CẢNH BÁO: Giọng thu âm từ [{source_device}] (F0={f0_val}Hz, Cosine={rej_cos} < 0.435) không khớp bất kỳ tài khoản nào! Đã chặn quyền!",
            source=source_device,
        )
        return {
            "ok": False,
            "recognized": False,
            "tier": 99,
            "speaker_name": "Người lạ chưa đăng ký",
            "f0_hz": f0_val,
            "cosine_score": rej_cos,
            "wespeaker_cosine": rej_cos,
            "source_device": source_device,
            "error": f"🚫 Server phát hiện Giọng Người Lạ (F0={f0_val}Hz, Cosine={rej_cos} < 0.435) từ [{source_device}] -> Từ chối điều khiển!",
        }

    def generate_dynamic_qr_token(
        self,
        issuer_tier: int = 1,
        duration_type: str = "1d",
        host_url: str = "http://localhost:8088",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Chỉ Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) mới được phép sinh mã QR Khách."""
        if int(issuer_tier) != 1:
            msg = "🚫 Chỉ Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) mới có quyền sinh mã QR Khách!"
            self._log_event(
                layer="QR Code Động 10s (RBAC)",
                action="qr_generate_blocked_non_owner",
                email="unknown",
                status="FAIL",
                detail=msg,
                source="Dynamic QR Portal",
            )
            return {
                "ok": False,
                "status_code": 403,
                "rbac_blocked": True,
                "error": msg,
            }
        dur_val = str(kwargs.get("duration_key") or duration_type or "1d")
        host_val = str(kwargs.get("base_url") or host_url or "http://localhost:8088")
        return super().generate_dynamic_qr_token(
            issuer_tier=1,
            duration_type=dur_val,
            host_url=host_val,
        )

    def consume_guest_handshake(
        self,
        token: str,
        target_window: int | None = None,
        used_token_store: set[str] | None = None,
        duration_type: str = "1d",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Xác thực mã QR một lần và kiểm tra mã QR phải do Chủ nhà Cấp 1 phát hành."""
        import hashlib
        import hmac

        tok_clean = (token or "").strip()
        active_tokens = getattr(self, "active_qr_tokens", {})
        if tok_clean in active_tokens:
            meta = active_tokens[tok_clean]
            if int(meta.get("issuer_tier", 1)) != 1:
                return {
                    "ok": False,
                    "status_code": 403,
                    "rbac_blocked": True,
                    "error": "Mã QR không hợp lệ vì không do Chủ nhà Cấp 1 phát hành!",
                }
        elif tok_clean:
            cur_window = int(time.time() // 10)
            secret = os.environ.get("SMARTHOME_TOTP_SECRET", "bk_smarthome_totp_salt_2026")
            for w_chk in range(cur_window + 2, cur_window - 19, -1):
                for d_key, d_sec in DURATION_MAP_SECONDS.items():
                    raw_p2 = f"{w_chk}:2:{d_key}:{d_sec}"
                    cand2 = hmac.new(secret.encode("utf-8"), raw_p2.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
                    if cand2 == tok_clean:
                        return {
                            "ok": False,
                            "status_code": 403,
                            "rbac_blocked": True,
                            "error": "Mã QR Cấp 2 đã bị vô hiệu hóa. Chỉ Chủ nhà Cấp 1 mới có quyền phát hành mã QR Khách!",
                        }
        res = super().consume_guest_handshake(
            token=token,
            target_window=target_window,
            used_token_store=used_token_store,
            duration_type=duration_type,
        )
        if res.get("ok"):
            gsid = str(res.get("guest_session_id") or "")
            if gsid and hasattr(self, "guest_qr_sessions") and gsid in self.guest_qr_sessions:
                self.guest_qr_sessions[gsid]["issuer_tier"] = 1
        return res

    def run_automated_3layer_test_suite(
        self,
        send_real_email_on_test1: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Chạy bộ kiểm thử tự động 14 kịch bản với quy tắc RBAC mới (Chỉ Cấp 1 có quyền mời)."""
        send_flag = bool(send_real_email_on_test1 or kwargs.get("send_real_gmail_in_test", False))
        self._sync_accounts_from_cas_if_enabled()
        with _ACCOUNTS_FILE_LOCK:
            with self._otp_lock:
                orig_accounts = copy.deepcopy(self.accounts)
                orig_otps = copy.deepcopy(dict(self.pending_otps))
                orig_fails = copy.deepcopy(self.otp_failed_attempts)
                orig_rl = copy.deepcopy(self._login_rate_limits)
        tok = _AUTOTEST_SANDBOX.set(True)
        try:
            report = super().run_automated_3layer_test_suite(send_real_email_on_test1=send_flag)
            if not isinstance(report, dict) or not isinstance(report.get("cases"), list):
                return report
            inv_t2 = self.get_invite_links_for_account("thanhviena.hust@gmail.com")
            blk_t2_to_t3 = self.create_custom_invite_link("thanhviena.hust@gmail.com", target_tier=3, source="AutoTest-Suite")
            blk_t2_to_t2 = self.create_custom_invite_link("thanhviena.hust@gmail.com", target_tier=2, source="AutoTest-Suite")
            p06 = (
                not inv_t2.get("can_invite")
                and inv_t2.get("allowed_target_tiers", []) == []
                and not blk_t2_to_t3.get("ok")
                and not blk_t2_to_t2.get("ok")
            )
            for item in report["cases"]:
                if isinstance(item, dict) and item.get("test_id") == "TEST-06":
                    item["passed"] = p06
                    item["status"] = "PASS" if p06 else "FAIL"
                    item["expected"] = "Cấp 2 không có quyền tạo/gửi link mời (Chỉ Chủ nhà Cấp 1 mới có quyền mời)"
                    item["actual"] = (
                        f"can_invite={inv_t2.get('can_invite')} | allowed_tiers={inv_t2.get('allowed_target_tiers')} | "
                        f"Chặn mời T3={not blk_t2_to_t3.get('ok')} | Chặn mời T2={not blk_t2_to_t2.get('ok')}"
                    )
            cases = report["cases"]
            passed_cnt = sum(1 for r in cases if isinstance(r, dict) and r.get("passed"))
            total_cnt = len(cases)
            report["ok"] = passed_cnt == total_cnt
            report["passed"] = passed_cnt
            report["passed_cases"] = passed_cnt
            report["passed_count"] = passed_cnt
            report["failed_count"] = total_cnt - passed_cnt
            report["pass_rate"] = f"{round((passed_cnt / max(1, total_cnt)) * 100, 1)}%"
            report["all_passed"] = passed_cnt == total_cnt
            report["summary"] = (
                f"Đạt {passed_cnt}/{total_cnt} kịch bản kiểm thử toàn diện "
                f"(3 Lớp + Phân cấp Link Mời + OAuth Gmail OTP + Thu âm Trang Đầu + Giọng nói Xóa/Bật Quyền)"
            )
            self.latest_test_report = report
            return report
        finally:
            _AUTOTEST_SANDBOX.reset(tok)
            with _ACCOUNTS_FILE_LOCK:
                with self._otp_lock:
                    self.accounts = orig_accounts
                    dict.clear(self.pending_otps)
                    dict.update(self.pending_otps, orig_otps)
                    self.otp_failed_attempts = orig_fails
                    self._login_rate_limits = orig_rl


_AUTH_MANAGER: ThreeLayerAuthManager | None = None


def get_auth_3layer_manager() -> ThreeLayerAuthManager:
    global _AUTH_MANAGER
    if _AUTH_MANAGER is None:
        _AUTH_MANAGER = ThreeLayerAuthManager()
    return _AUTH_MANAGER


get_auth_manager = get_auth_3layer_manager


def check_duplicate_voice_gate(
    feat_s1: bytes | Any,
    deep_feat: Any = None,
    threshold_mel: float = THRESHOLD_MEL,
    threshold_deep: float = THRESHOLD_DEEP,
    f0_hz: float | None = None,
    target_tier: int = 0,
    target_user_id: str = "",
) -> Any:
    """Hàm cấp module gọi trực tiếp Cổng Kiểm Tra Chống Trùng Giọng Trong Nhà."""
    return get_auth_3layer_manager().check_duplicate_voice_gate(
        feat_s1=feat_s1,
        deep_feat=deep_feat,
        threshold_mel=threshold_mel,
        threshold_deep=threshold_deep,
        f0_hz=f0_hz,
        target_tier=target_tier,
        target_user_id=target_user_id,
    )


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
    "ThreeLayerAuthManager",
    "get_auth_3layer_manager",
    "get_auth_manager",
    "check_duplicate_voice_gate",
    "is_test_otp_fields_allowed",
    "_ACCOUNTS_FILE_LOCK",
]
