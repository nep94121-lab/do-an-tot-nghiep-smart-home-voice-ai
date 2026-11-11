"""Module simulator.auth.qr_totp_mixin: Sinh mã QR Động 10 giây (TOTP HMAC-SHA256), Bắt tay Single-Use và Email OTP + DNS MX."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Any

from simulator.auth.constants_and_crypto import (
    DURATION_LABELS_VN,
    DURATION_MAP_SECONDS,
    validate_dns_mx_record,
)


class AuthQrTotpMixin:
    """Mixin xử lý QR Động 10 giây (TOTP), Single-Use Handshake và xác thực Email OTP kèm DNS MX."""

    used_qr_tokens: set[str]
    active_qr_tokens: dict[str, dict[str, Any]]
    guest_qr_sessions: dict[str, dict[str, Any]]
    pending_guest_email_otps: dict[str, dict[str, Any]]

    def generate_dynamic_qr_token(
        self,
        issuer_tier: int = 1,
        duration_type: str = "1d",
        host_url: str = "http://localhost:8088",
    ) -> dict[str, Any]:
        """Sinh mã QR Động xoay vòng mỗi 10 giây (TOTP HMAC-SHA256) kèm giới hạn thời hạn cho Khách Cấp 3."""
        if not hasattr(self, "used_qr_tokens"):
            self.used_qr_tokens = set()
        if not hasattr(self, "active_qr_tokens"):
            self.active_qr_tokens = {}
        if not hasattr(self, "guest_qr_sessions"):
            self.guest_qr_sessions = {}

        if int(issuer_tier) != 1:
            return {
                "ok": False,
                "rbac_blocked": True,
                "error": "Chỉ Cấp 1 (Chủ nhà Nguyễn Tuấn Anh) mới có quyền tạo mã QR động cho khách!",
                "status_code": 403,
            }

        dur_key = str(duration_type or "").strip().lower()
        if dur_key not in DURATION_MAP_SECONDS:
            return {
                "ok": False,
                "error": f"Thời hạn '{duration_type}' không hợp lệ (chỉ hỗ trợ: 1d, 2d, 1w, 1m, 1y).",
                "status_code": 400,
            }

        now_ts = time.time()
        window = int(now_ts // 10)
        dur_sec = DURATION_MAP_SECONDS[dur_key]
        dur_label = DURATION_LABELS_VN.get(dur_key, dur_key)
        secret = os.environ.get("SMARTHOME_TOTP_SECRET", "bk_smarthome_totp_salt_2026")
        raw_payload = f"{window}:{issuer_tier}:{dur_key}:{dur_sec}"
        token = hmac.new(secret.encode("utf-8"), raw_payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
        expires_in_sec = max(1, 10 - int(now_ts % 10))
        qr_url = f"/guest_enroll?token={token}&window={window}&dur={dur_key}"
        full_url = f"{host_url.rstrip('/')}{qr_url}"

        self.active_qr_tokens[token] = {
            "token": token,
            "window": window,
            "issuer_tier": int(issuer_tier),
            "duration_type": dur_key,
            "duration_label": dur_label,
            "duration_seconds": dur_sec,
            "created_at_ts": now_ts,
        }

        return {
            "ok": True,
            "token": token,
            "window": window,
            "issuer_tier": int(issuer_tier),
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
    ) -> dict[str, Any]:
        """Xác thực mã QR 10s khi khách quét mã mở trang thu âm (Single-Use Token + 15-min Guest Session)."""
        if not hasattr(self, "used_qr_tokens"):
            self.used_qr_tokens = set()
        if not hasattr(self, "active_qr_tokens"):
            self.active_qr_tokens = {}
        if not hasattr(self, "guest_qr_sessions"):
            self.guest_qr_sessions = {}

        clean_tok = str(token or "").strip()
        if not clean_tok:
            return {"ok": False, "error": "Thiếu mã token QR động!", "status_code": 400}

        store = self.used_qr_tokens if used_token_store is None else used_token_store
        if clean_tok in store:
            return {
                "ok": False,
                "error": "Mã QR này đã được sử dụng một lần (Single-Use Token). Vui lòng quét mã mới trên màn hình!",
                "status_code": 400,
            }

        cur_window = int(time.time() // 10)
        tok_meta = self.active_qr_tokens.get(clean_tok)
        token_win = None

        if tok_meta is not None:
            token_win = int(tok_meta["window"])
            if target_window is not None and int(target_window) != token_win:
                return {
                    "ok": False,
                    "error": "Mã QR không khớp thông số cửa sổ thời gian!",
                    "status_code": 401,
                }
        else:
            matched_win = None
            secret = os.environ.get("SMARTHOME_TOTP_SECRET", "bk_smarthome_totp_salt_2026")
            # Cửa sổ 180 giây: kiểm tra lùi tối đa 18 chu kỳ (180s) và tiến 2 chu kỳ (clock skew)
            w_candidates = list(range(cur_window + 2, cur_window - 19, -1))
            if target_window is not None:
                try:
                    tw = int(target_window)
                    if tw in w_candidates:
                        w_candidates.remove(tw)
                    w_candidates.insert(0, tw)
                except (ValueError, TypeError):
                    pass

            for w_chk in w_candidates:
                for t_chk in (1,):
                    for d_key, d_sec in DURATION_MAP_SECONDS.items():
                        raw_p = f"{w_chk}:{t_chk}:{d_key}:{d_sec}"
                        cand = hmac.new(secret.encode("utf-8"), raw_p.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
                        if cand == clean_tok:
                            matched_win = w_chk
                            tok_meta = {
                                "token": clean_tok,
                                "window": w_chk,
                                "issuer_tier": t_chk,
                                "duration_type": d_key,
                                "duration_label": DURATION_LABELS_VN.get(d_key, d_key),
                                "duration_seconds": d_sec,
                            }
                            break
                    if matched_win is not None:
                        break
                if matched_win is not None:
                    break

            if matched_win is not None:
                token_win = matched_win

        if token_win is None:
            return {
                "ok": False,
                "error": "Mã QR không hợp lệ hoặc đã hết hạn 180 giây, vui lòng quét lại mã mới trên màn hình!",
                "status_code": 401,
            }

        # Cửa sổ thời gian chấp nhận token 180 giây (18 chu kỳ window x 10s)
        if (cur_window - token_win) > 18 or (token_win - cur_window) > 2:
            return {
                "ok": False,
                "error": "Mã QR đã hết hạn 180 giây, vui lòng quét lại mã mới trên màn hình!",
                "status_code": 401,
            }

        store.add(clean_tok)
        dur_key = (tok_meta or {}).get("duration_type") or (duration_type if duration_type in DURATION_MAP_SECONDS else "1d")
        dur_sec = DURATION_MAP_SECONDS.get(dur_key, 86400)
        dur_label = DURATION_LABELS_VN.get(dur_key, dur_key)
        now_ts = time.time()
        session_id = f"guest_sess_{int(now_ts)}_{clean_tok[:6]}"
        sess_obj = {
            "guest_session_id": session_id,
            "token": clean_tok,
            "duration_type": dur_key,
            "duration_label": dur_label,
            "duration_seconds": dur_sec,
            "created_at": now_ts,
            "session_expires_at": now_ts + 900.0,
            "voice_enrolled": False,
            "email_verified": False,
            "email": "",
        }
        self.guest_qr_sessions[session_id] = sess_obj
        return {
            "ok": True,
            "guest_session_id": session_id,
            "duration_type": dur_key,
            "duration_label": dur_label,
            "duration_seconds": dur_sec,
            "session_expires_at": sess_obj["session_expires_at"],
            "reading_prompt": "Xin chào hệ thống Nhà Thông Minh Bách Khoa, tôi xác nhận đăng ký giọng nói khách Cấp 3.",
            "message": f"Bắt tay thành công! Mở phiên thu âm 15 phút (Thời hạn quyền khách: {dur_label}).",
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
        if not hasattr(self, "pending_guest_email_otps"):
            self.pending_guest_email_otps = {}

        session_store = self.pending_guest_email_otps if store is None else store
        e1 = str(email or "").strip()
        e2 = str(confirm_email or "").strip()

        if not e1 or not e2:
            return {"ok": False, "error": "Vui lòng nhập đầy đủ cả 2 ô Email và Xác nhận Email!", "status_code": 400}

        if e1 != e2:
            return {
                "ok": False,
                "error": "Hai ô nhập email không khớp nhau (Email và Xác nhận Email phải giống nhau 100%)!",
                "status_code": 400,
            }

        mx_ok, mx_msg = validate_dns_mx_record(e1)
        if not mx_ok:
            return {"ok": False, "error": mx_msg, "status_code": 400}

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
            if send_gmail:
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
            return {
                "ok": False,
                "error": f"Mã OTP không chính xác (Lần thử {record['attempts']})!",
                "status_code": 400,
            }

        session_store.pop(clean_email, None)
        if session_id and hasattr(self, "guest_qr_sessions") and session_id in self.guest_qr_sessions:
            self.guest_qr_sessions[session_id]["email_verified"] = True
            self.guest_qr_sessions[session_id]["email"] = clean_email

        return {
            "ok": True,
            "verified": True,
            "email": clean_email,
            "message": f"Xác nhận email {clean_email} thành công qua OTP thực tế!",
        }
