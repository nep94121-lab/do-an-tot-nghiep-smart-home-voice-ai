"""Module simulator.auth.qr_totp_mixin: Sinh mã QR Động 10 giây (TOTP HMAC-SHA256), Bắt tay Single-Use gắn kết Phiên Quét (Session/Device Nonce) và Email OTP + DNS MX."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from typing import Any

from simulator.auth.constants_and_crypto import (
    DURATION_LABELS_VN,
    DURATION_MAP_SECONDS,
    validate_dns_mx_record,
)

# Khóa nguyên tử toàn cục bảo vệ phát hành, bắt tay và tiêu thụ token QR (chống Race Condition / Double-Submit)
_QR_ATOMIC_LOCK = threading.RLock()
_QR_ISSUE_SEQ = 0

QR_SCAN_COOKIE_NAME = "sh_qr_scan_nonce"
QR_SESSION_COOKIE_NAME = "sh_qr_session_id"
QR_SHORT_EXPIRY_SEC = 180.0


def hash_qr_scan_nonce(nonce: str | None) -> str:
    """Băm SHA-256 cho device/session scan nonce để đối chiếu an toàn."""
    clean = str(nonce or "").strip()
    if not clean:
        return ""
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()


def is_qr_registration_token_or_session(val: str | None, mgr3: Any = None) -> bool:
    """Kiểm tra một giá trị token/session_id có thuộc luồng đăng ký QR cô lập hay không."""
    clean = str(val or "").strip()
    if not clean:
        return False
    if clean.startswith("guest_sess_"):
        return True
    if mgr3 is None:
        try:
            from simulator.auth_3layer import get_auth_3layer_manager
            mgr3 = get_auth_3layer_manager()
        except Exception:
            mgr3 = None
    if mgr3 is not None:
        if (
            clean in getattr(mgr3, "active_qr_tokens", {})
            or clean in getattr(mgr3, "used_qr_tokens", set())
            or clean in getattr(mgr3, "guest_qr_sessions", {})
        ):
            return True
        val_hash = hash_qr_scan_nonce(clean)
        for s_info in getattr(mgr3, "guest_qr_sessions", {}).values():
            if isinstance(s_info, dict):
                if str(s_info.get("post_scan_token") or "") == clean:
                    return True
                if str(s_info.get("token") or "") == clean:
                    return True
                exp_hash = str(s_info.get("bound_scan_nonce_hash") or "").strip()
                if val_hash and exp_hash and hmac.compare_digest(val_hash, exp_hash):
                    return True
        for t_info in getattr(mgr3, "active_qr_tokens", {}).values():
            if isinstance(t_info, dict):
                t_hash = str(t_info.get("bound_scan_nonce_hash") or "").strip()
                if val_hash and t_hash and hmac.compare_digest(val_hash, t_hash):
                    return True
    return False



class AuthQrTotpMixin:
    """Mixin xử lý QR Động 10 giây (TOTP), Single-Use Handshake gắn phiên quét và xác thực Email OTP kèm DNS MX."""

    used_qr_tokens: set[str]
    active_qr_tokens: dict[str, dict[str, Any]]
    guest_qr_sessions: dict[str, dict[str, Any]]
    pending_guest_email_otps: dict[str, dict[str, Any]]

    def _ensure_qr_stores(self) -> None:
        if not hasattr(self, "used_qr_tokens") or self.used_qr_tokens is None:
            self.used_qr_tokens = set()
        if not hasattr(self, "active_qr_tokens") or self.active_qr_tokens is None:
            self.active_qr_tokens = {}
        if not hasattr(self, "guest_qr_sessions") or self.guest_qr_sessions is None:
            self.guest_qr_sessions = {}
        if not hasattr(self, "pending_guest_email_otps") or self.pending_guest_email_otps is None:
            self.pending_guest_email_otps = {}

    def invalidate_previous_qr_tokens_and_sessions(
        self,
        reason: str = "RESCANNED_NEW_TOKEN_ISSUED",
        exclude_token: str = "",
        exclude_session_id: str = "",
    ) -> int:
        """Thu hồi tức thì mọi token QR chưa dùng và mọi phiên đăng ký QR đang mở khi phát hành/quét lại QR mới."""
        with _QR_ATOMIC_LOCK:
            self._ensure_qr_stores()
            now_ts = time.time()
            invalidated_count = 0

            for tok, meta in list(self.active_qr_tokens.items()):
                if tok == exclude_token:
                    continue
                if isinstance(meta, dict) and meta.get("status") not in ("CONSUMED", "INVALIDATED"):
                    meta["status"] = "INVALIDATED"
                    meta["invalidated"] = True
                    meta["invalidated_reason"] = reason
                    meta["invalidated_at"] = now_ts
                    self.used_qr_tokens.add(tok)
                    invalidated_count += 1

            for sid, s_meta in list(self.guest_qr_sessions.items()):
                if sid == exclude_session_id:
                    continue
                if isinstance(s_meta, dict) and s_meta.get("status") not in ("CONSUMED", "INVALIDATED", "INVALIDATED_ON_ERROR"):
                    s_meta["status"] = "INVALIDATED"
                    s_meta["invalidated"] = True
                    s_meta["consumed"] = True
                    s_meta["invalidated_reason"] = reason
                    s_meta["invalidated_at"] = now_ts
                    tok_ref = str(s_meta.get("token") or "").strip()
                    if tok_ref:
                        self.used_qr_tokens.add(tok_ref)
                    invalidated_count += 1

            return invalidated_count

    def invalidate_qr_session_on_mistake(
        self,
        session_id: str,
        reason: str = "REGISTRATION_ATTEMPT_FAILED_MUST_RESCAN",
    ) -> bool:
        """Hủy tức thì phiên/token sau khi người quét thao tác sai hoặc gửi dữ liệu lỗi (bắt buộc quét lại QR mới)."""
        clean_sid = str(session_id or "").strip()
        if not clean_sid:
            return False
        with _QR_ATOMIC_LOCK:
            self._ensure_qr_stores()
            s_meta = self.guest_qr_sessions.get(clean_sid)
            if not isinstance(s_meta, dict):
                return False
            if str(s_meta.get("status") or "").upper() == "CONSUMED":
                return False
            now_ts = time.time()
            s_meta["status"] = "INVALIDATED_ON_ERROR"
            s_meta["invalidated"] = True
            s_meta["consumed"] = True
            s_meta["invalidated_reason"] = reason
            s_meta["invalidated_at"] = now_ts
            tok_ref = str(s_meta.get("token") or "").strip()
            if tok_ref:
                self.used_qr_tokens.add(tok_ref)
                if tok_ref in self.active_qr_tokens and isinstance(self.active_qr_tokens[tok_ref], dict):
                    if str(self.active_qr_tokens[tok_ref].get("status") or "").upper() != "CONSUMED":
                        self.active_qr_tokens[tok_ref]["status"] = "INVALIDATED"
                        self.active_qr_tokens[tok_ref]["invalidated"] = True
                        self.active_qr_tokens[tok_ref]["invalidated_reason"] = reason
            return True

    def verify_owner_cap1_permission(self, owner_id: str = "tuan_anh") -> bool:
        """Kiểm tra Chủ nhà Cấp 1 (Cap 1) có quyền hợp lệ trên hệ thống để phê duyệt mã QR."""
        accounts = getattr(self, "accounts", None)
        if isinstance(accounts, dict) and accounts:
            acc = accounts.get(owner_id) or accounts.get("tuan_anh")
            if not isinstance(acc, dict):
                return False
            if int(acc.get("tier", 0)) != 1 or str(acc.get("role", "")).upper() != "ADMIN":
                return False
            if acc.get("revoked") or acc.get("disabled"):
                return False
        return True

    def generate_dynamic_qr_token(
        self,
        issuer_tier: int = 1,
        duration_type: str = "1d",
        host_url: str = "http://localhost:8088",
        owner_id: str = "tuan_anh",
        target_tier: int = 3,
        invalidate_previous: bool = True,
    ) -> dict[str, Any]:
        """Sinh mã QR Động xoay vòng mỗi 10 giây (TOTP HMAC-SHA256) chỉ dành riêng cho Chủ nhà Cấp 1."""
        global _QR_ISSUE_SEQ
        with _QR_ATOMIC_LOCK:
            self._ensure_qr_stores()

            if int(issuer_tier) != 1 or not self.verify_owner_cap1_permission(owner_id):
                return {
                    "ok": False,
                    "rbac_blocked": True,
                    "error": "Chỉ Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) mới có quyền phê duyệt và tạo mã QR động cho khách!",
                    "status_code": 403,
                }

            dur_key = str(duration_type or "").strip().lower()
            if dur_key not in DURATION_MAP_SECONDS:
                return {
                    "ok": False,
                    "error": f"Thời hạn '{duration_type}' không hợp lệ (chỉ hỗ trợ: 1d, 2d, 1w, 1m, 1y).",
                    "status_code": 400,
                }

            if invalidate_previous:
                self.invalidate_previous_qr_tokens_and_sessions(reason="RESCANNED_NEW_TOKEN_ISSUED")

            now_ts = time.time()
            window = int(now_ts // 10)
            dur_sec = DURATION_MAP_SECONDS[dur_key]
            dur_label = DURATION_LABELS_VN.get(dur_key, dur_key)
            secret = os.environ.get("SMARTHOME_TOTP_SECRET", "bk_smarthome_totp_salt_2026")

            _QR_ISSUE_SEQ += 1
            issue_nonce = secrets.token_hex(8)
            raw_payload = f"{window}:1:{dur_key}:{dur_sec}:{_QR_ISSUE_SEQ}:{issue_nonce}"
            token = hmac.new(secret.encode("utf-8"), raw_payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
            while token in self.used_qr_tokens or token in self.active_qr_tokens:
                _QR_ISSUE_SEQ += 1
                issue_nonce = secrets.token_hex(8)
                raw_payload = f"{window}:1:{dur_key}:{dur_sec}:{_QR_ISSUE_SEQ}:{issue_nonce}"
                token = hmac.new(secret.encode("utf-8"), raw_payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16]

            expires_in_sec = max(1, 10 - int(now_ts % 10))
            qr_url = f"/guest_enroll?token={token}&window={window}&dur={dur_key}"
            full_url = f"{host_url.rstrip('/')}{qr_url}"

            self.active_qr_tokens[token] = {
                "token": token,
                "window": window,
                "issuer_tier": 1,
                "owner_id": str(owner_id or "tuan_anh"),
                "owner_approved": True,
                "target_tier": int(target_tier) if int(target_tier) in (2, 3) else 3,
                "duration_type": dur_key,
                "duration_label": dur_label,
                "duration_seconds": dur_sec,
                "created_at_ts": now_ts,
                "expires_at_ts": now_ts + QR_SHORT_EXPIRY_SEC,
                "status": "ISSUED",
                "invalidated": False,
                "bound_scan_nonce_hash": "",
                "link_opened_count": 0,
            }

            return {
                "ok": True,
                "token": token,
                "window": window,
                "issuer_tier": 1,
                "owner_id": str(owner_id or "tuan_anh"),
                "owner_approved": True,
                "duration_type": dur_key,
                "duration_label": dur_label,
                "duration_seconds": dur_sec,
                "expires_in_sec": expires_in_sec,
                "qr_url": qr_url,
                "full_url": full_url,
            }

    def consume_guest_handshake(
        self,
        token: str,
        target_window: int | None = None,
        used_token_store: set[str] | None = None,
        duration_type: str = "1d",
        scan_nonce: str | None = None,
        user_agent: str = "",
    ) -> dict[str, Any]:
        """Xác thực mã QR khi khách quét mã (Single-Use Token + Gắn kết Phiên Quét 180s + Thu hồi phiên cũ)."""
        with _QR_ATOMIC_LOCK:
            self._ensure_qr_stores()

            clean_tok = str(token or "").strip()
            if not clean_tok:
                return {"ok": False, "error": "Thiếu mã token QR động!", "status_code": 400}

            store = self.used_qr_tokens if used_token_store is None else used_token_store
            tok_meta = self.active_qr_tokens.get(clean_tok)

            if clean_tok in store:
                if isinstance(tok_meta, dict) and tok_meta.get("invalidated"):
                    return {
                        "ok": False,
                        "reason": "TOKEN_INVALIDATED_BY_RESCAN",
                        "error": "Mã QR cũ đã bị vô hiệu hóa do phát hành/quét lại mã mới (Single-Use Token). Vui lòng quét mã mới trên màn hình!",
                        "status_code": 400,
                    }
                return {
                    "ok": False,
                    "reason": "SINGLE_USE_TOKEN_REUSED",
                    "error": "Mã QR này đã được sử dụng một lần (Single-Use Token). Vui lòng quét mã mới trên màn hình!",
                    "status_code": 400,
                }

            if not isinstance(tok_meta, dict):
                return {
                    "ok": False,
                    "reason": "TOKEN_INVALID_OR_EXPIRED",
                    "error": "Mã QR không hợp lệ hoặc đã hết hạn 180 giây, vui lòng quét lại mã mới trên màn hình!",
                    "status_code": 401,
                }

            if tok_meta.get("status") == "INVALIDATED" or tok_meta.get("invalidated"):
                store.add(clean_tok)
                return {
                    "ok": False,
                    "reason": "TOKEN_INVALIDATED_BY_RESCAN",
                    "error": "Mã QR cũ đã bị vô hiệu hóa do quét lại mã mới (Single-Use Token). Vui lòng quét mã mới!",
                    "status_code": 400,
                }

            if int(tok_meta.get("issuer_tier", 0)) != 1 or not tok_meta.get("owner_approved", False) or not self.verify_owner_cap1_permission(str(tok_meta.get("owner_id", "tuan_anh"))):
                return {
                    "ok": False,
                    "rbac_blocked": True,
                    "reason": "OWNER_CAP1_APPROVAL_REQUIRED",
                    "error": "Từ chối: Mã QR không có phê duyệt hợp lệ từ Chủ nhà Cấp 1!",
                    "status_code": 403,
                }

            token_win = int(tok_meta["window"])
            if target_window is not None and int(target_window) != token_win:
                return {
                    "ok": False,
                    "reason": "WINDOW_MISMATCH",
                    "error": "Mã QR không khớp thông số cửa sổ thời gian!",
                    "status_code": 401,
                }

            now_ts = time.time()
            cur_window = int(now_ts // 10)
            tok_expires_at = float(tok_meta.get("expires_at_ts", float(tok_meta.get("created_at_ts", now_ts)) + QR_SHORT_EXPIRY_SEC))
            if (cur_window - token_win) > 18 or (token_win - cur_window) > 2 or now_ts > tok_expires_at:
                tok_meta["status"] = "EXPIRED"
                return {
                    "ok": False,
                    "reason": "TOKEN_EXPIRED",
                    "error": "Mã QR không hợp lệ hoặc đã hết hạn 180 giây, vui lòng quét lại mã mới trên màn hình!",
                    "status_code": 401,
                }

            existing_nonce_hash = str(tok_meta.get("bound_scan_nonce_hash") or "").strip()
            incoming_nonce = str(scan_nonce or "").strip()
            if existing_nonce_hash:
                incoming_hash = hash_qr_scan_nonce(incoming_nonce)
                if not incoming_hash or not hmac.compare_digest(incoming_hash, existing_nonce_hash):
                    return {
                        "ok": False,
                        "reason": "SESSION_BINDING_MISMATCH",
                        "error": "Từ chối truy cập: Liên kết/mã QR này đã được gắn kết với phiên quét của thiết bị/trình duyệt khác!",
                        "status_code": 403,
                    }
                effective_nonce = incoming_nonce
                nonce_hash = existing_nonce_hash
            else:
                effective_nonce = incoming_nonce or secrets.token_urlsafe(24)
                nonce_hash = hash_qr_scan_nonce(effective_nonce)
                tok_meta["bound_scan_nonce_hash"] = nonce_hash

            # Thu hồi mọi phiên đăng ký QR cũ trước khi mở phiên mới
            self.invalidate_previous_qr_tokens_and_sessions(
                reason="RESCANNED_NEW_HANDSHAKE",
                exclude_token=clean_tok,
            )

            store.add(clean_tok)
            tok_meta["status"] = "HANDSHAKEN"
            tok_meta["handshaken_at"] = now_ts

            dur_key = str(tok_meta.get("duration_type") or (duration_type if duration_type in DURATION_MAP_SECONDS else "1d"))
            dur_sec = DURATION_MAP_SECONDS.get(dur_key, 86400)
            dur_label = DURATION_LABELS_VN.get(dur_key, dur_key)

            session_id = f"guest_sess_{int(now_ts)}_{clean_tok[:6]}_{secrets.token_hex(3)}"
            post_scan_token = secrets.token_urlsafe(24)
            session_expires_at = now_ts + QR_SHORT_EXPIRY_SEC
            post_scan_url = f"/guest_enroll?session_id={session_id}&post_scan_token={post_scan_token}"

            sess_obj: dict[str, Any] = {
                "session_id": session_id,
                "guest_session_id": session_id,
                "token": clean_tok,
                "post_scan_token": post_scan_token,
                "post_scan_url": post_scan_url,
                "bound_scan_nonce_hash": nonce_hash,
                "bound_user_agent": str(user_agent or ""),
                "issuer_tier": 1,
                "owner_id": str(tok_meta.get("owner_id", "tuan_anh")),
                "owner_approved": True,
                "duration_type": dur_key,
                "duration_label": dur_label,
                "duration_seconds": dur_sec,
                "created_at": now_ts,
                "session_expires_at": session_expires_at,
                "lock_ttl_sec": int(QR_SHORT_EXPIRY_SEC),
                "status": "ACTIVE",
                "consumed": False,
                "invalidated": False,
                "page_opened_count": int(tok_meta.get("link_opened_count", 0)),
                "voice_enrolled": False,
                "email_verified": False,
                "email": "",
            }
            self.guest_qr_sessions[session_id] = sess_obj

            return {
                "ok": True,
                "guest_session_id": session_id,
                "session_id": session_id,
                "post_scan_token": post_scan_token,
                "post_scan_url": post_scan_url,
                "scan_nonce": effective_nonce,
                "duration_type": dur_key,
                "duration_label": dur_label,
                "duration_seconds": dur_sec,
                "lock_ttl_sec": int(QR_SHORT_EXPIRY_SEC),
                "session_expires_at": session_expires_at,
                "reading_prompt": "Xin chào hệ thống Nhà Thông Minh Bách Khoa, tôi xác nhận đăng ký giọng nói khách Cấp 3.",
                "message": f"Bắt tay thành công! Mở phiên đăng ký độc lập 180 giây gắn kết thiết bị quét (Thời hạn quyền khách: {dur_label}).",
            }

    def validate_dns_mx_record(self, email: str) -> tuple[bool, str]:
        """Kiểm tra định dạng email và bản ghi DNS MX thực tế của tên miền."""
        return validate_dns_mx_record(email)

    def send_and_verify_email_otp(
        self,
        email: str,
        confirm_email: str,
        input_otp: str | None = None,
        otp_code: str | None = None,
        session_id: str = "",
        store: dict[str, dict[str, Any]] | None = None,
        send_gmail: bool = False,
    ) -> dict[str, Any]:
        """Xác thực Email tùy chọn của khách với 2 ô nhập khớp 100%, kiểm tra DNS MX và gửi/xác nhận mã OTP."""
        self._ensure_qr_stores()

        session_store = self.pending_guest_email_otps if store is None else store
        e1 = str(email or "").strip()
        e2 = str(confirm_email or "").strip()

        if not e1 or not e2:
            if session_id:
                self.invalidate_qr_session_on_mistake(session_id, "EMAIL_EMPTY_MISTAKE")
            return {"ok": False, "must_rescan": True, "error": "Vui lòng nhập đầy đủ cả 2 ô Email và Xác nhận Email!", "status_code": 400}

        if e1 != e2:
            if session_id:
                self.invalidate_qr_session_on_mistake(session_id, "EMAIL_MISMATCH_MISTAKE")
            return {
                "ok": False,
                "must_rescan": True,
                "error": "Hai ô nhập email không khớp nhau (Email và Xác nhận Email phải giống nhau 100%)!",
                "status_code": 400,
            }

        mx_ok, mx_msg = validate_dns_mx_record(e1)
        if not mx_ok:
            if session_id:
                self.invalidate_qr_session_on_mistake(session_id, "EMAIL_MX_INVALID_MISTAKE")
            return {"ok": False, "must_rescan": True, "error": mx_msg, "status_code": 400}

        clean_email = e1.lower()
        actual_otp_input = input_otp if input_otp is not None else otp_code

        if actual_otp_input is None:
            gen_otp = f"{secrets.randbelow(900000) + 100000}"
            session_store[clean_email] = {
                "otp": gen_otp,
                "generated_at": time.time(),
                "expires_at": time.time() + 300.0,
                "attempts": 0,
                "session_id": session_id,
            }
            gmail_res = {}
            if send_gmail and clean_email == "nep94121@gmail.com":
                gmail_res = self.send_real_gmail_otp(
                    target_email=clean_email,
                    otp_code=gen_otp,
                    display_name="Khách Quét QR Cấp 3",
                )
            return {
                "ok": True,
                "otp_dispatched": True,
                "email": clean_email,
                "mx_detail": mx_msg,
                "otp_code_for_test": gen_otp,
                "gmail_delivery": gmail_res,
                "message": f"Đã kiểm tra tên miền MX hợp lệ và gửi mã xác nhận OTP 6 số về hộp thư {clean_email}!",
            }

        record = session_store.get(clean_email)
        if not record:
            return {"ok": False, "error": "Chưa có mã OTP nào được gửi cho email này!", "status_code": 400}

        if time.time() > float(record.get("expires_at", 0)):
            return {"ok": False, "error": "Mã OTP đã hết hạn sau 5 phút, vui lòng yêu cầu mã mới!", "status_code": 400}

        if str(actual_otp_input).strip() != str(record.get("otp", "")):
            record["attempts"] = int(record.get("attempts", 0)) + 1
            rec_sid = str(session_id or record.get("session_id") or "").strip()
            if rec_sid:
                self.invalidate_qr_session_on_mistake(rec_sid, "WRONG_OTP_MISTAKE")
            return {
                "ok": False,
                "must_rescan": bool(rec_sid),
                "error": f"Mã OTP không chính xác (Lần thử {record['attempts']})!",
                "status_code": 400,
            }

        session_store.pop(clean_email, None)
        if session_id and session_id in self.guest_qr_sessions:
            self.guest_qr_sessions[session_id]["email_verified"] = True
            self.guest_qr_sessions[session_id]["email"] = clean_email

        return {
            "ok": True,
            "verified": True,
            "email": clean_email,
            "message": f"Xác nhận email {clean_email} thành công! Đã kích hoạt thông báo cho phiên khách.",
        }
