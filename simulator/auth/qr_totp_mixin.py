"""Module simulator.auth.qr_totp_mixin: Sinh mã QR Động 10 giây (TOTP HMAC-SHA256), Bắt tay Single-Use gắn kết Phiên Quét (Session/Device Nonce) và Email OTP + DNS MX."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from typing import Any
from urllib.parse import parse_qsl, unquote_plus

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
    return hashlib.sha256(clean.encode("utf-8", errors="surrogatepass")).hexdigest()


class _JsonObjectPairs(list):
    """Lưu danh sách cặp (key, value) của JSON object để giữ nguyên các khóa trùng lặp khi phân tích khoan dung."""


class _RawJsonLiteral(str):
    """Đại diện nguyên văn cho số thực/số nguyên/hằng số JSON (kể cả 1e309, NaN, Infinity, số nguyên khổng lồ)."""


_HEX_DIGITS_SET: frozenset[str] = frozenset("0123456789abcdefABCDEF")
_JSON_SIMPLE_ESCAPES: dict[str, str] = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}
_NON_CREDENTIAL_HTTP_HEADERS: frozenset[str] = frozenset(
    {
        "host",
        "user-agent",
        "accept",
        "accept-encoding",
        "accept-language",
        "connection",
        "content-type",
        "content-length",
        "origin",
        "referer",
        "cache-control",
        "pragma",
        "cookie",
        "sec-fetch-dest",
        "sec-fetch-mode",
        "sec-fetch-site",
        "upgrade",
        "sec-websocket-key",
        "sec-websocket-version",
        "sec-websocket-extensions",
    }
)


def unescape_json_string_literal(raw_inner: str) -> str:
    """Giải mã đầy đủ chuỗi JSON (kể cả \\uXXXX, cặp surrogate UTF-16, \\\", \\\\) độc lập với lỗi cú pháp bên ngoài."""
    if not raw_inner:
        return ""
    if "\\" not in raw_inner:
        return raw_inner
    try:
        decoded = json.loads(f'"{raw_inner}"')
        if isinstance(decoded, str):
            return decoded
    except Exception:
        pass

    out: list[str] = []
    n = len(raw_inner)
    i = 0
    while i < n:
        ch = raw_inner[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= n:
            break
        esc = raw_inner[i + 1]
        if esc in _JSON_SIMPLE_ESCAPES:
            out.append(_JSON_SIMPLE_ESCAPES[esc])
            i += 2
            continue
        if esc == "u" and i + 6 <= n and all(c in _HEX_DIGITS_SET for c in raw_inner[i + 2 : i + 6]):
            code = int(raw_inner[i + 2 : i + 6], 16)
            if (
                0xD800 <= code <= 0xDBFF
                and i + 12 <= n
                and raw_inner[i + 6 : i + 8] == "\\u"
                and all(c in _HEX_DIGITS_SET for c in raw_inner[i + 8 : i + 12])
            ):
                low = int(raw_inner[i + 8 : i + 12], 16)
                if 0xDC00 <= low <= 0xDFFF:
                    combined = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                    out.append(chr(combined))
                    i += 12
                    continue
            out.append(chr(code))
            i += 6
            continue
        out.append(esc)
        i += 2
    return "".join(out)


def decode_raw_body_texts(raw_body: bytes | None) -> list[str]:
    """Giải mã khoan dung raw_body sang danh sách chuỗi văn bản (hỗ trợ UTF-8, UTF-8-SIG và UTF-16/UTF-32 có BOM/NUL)."""
    if not raw_body:
        return []
    bounded = raw_body[:2_000_000]
    texts: list[str] = []

    def _add_text(t: str) -> None:
        cleaned = t.lstrip("\ufeff").strip()
        if cleaned and cleaned not in texts:
            texts.append(cleaned)

    if bounded.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        enc = "utf-32-le" if bounded.startswith(b"\xff\xfe\x00\x00") else "utf-32-be"
        _add_text(bounded[4:].decode(enc, errors="ignore"))
    elif bounded.startswith((b"\xff\xfe", b"\xfe\xff")):
        enc = "utf-16-le" if bounded.startswith(b"\xff\xfe") else "utf-16-be"
        _add_text(bounded[2:].decode(enc, errors="ignore"))

    _add_text(bounded.decode("utf-8", errors="ignore"))

    sample = bounded[:64]
    if b"\x00" in sample:
        for alt_enc in ("utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"):
            try:
                _add_text(bounded.decode(alt_enc, errors="ignore"))
            except Exception:
                pass
    return texts


def extract_tolerant_raw_body_pairs_and_strings(
    raw_body: bytes | None = None,
    payload: Any = None,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Trích xuất khoan dung toàn bộ cặp (khóa, giá trị) và các chuỗi ngắn từ payload/raw_body TRƯỚC và ĐỘC LẬP với
    bước kiểm tra số học/cấu trúc JSON nghiêm ngặt:
    - Giải mã đầy đủ \\uXXXX cho cả khóa và giá trị kể cả khi cùng body có 1e309, -1e309, NaN, Infinity, số khổng lồ, khóa trùng hoặc JSON gãy dở.
    - Giải mã %XX cho application/x-www-form-urlencoded và multipart/form-data.
    """
    pairs: list[tuple[str, str]] = []
    strings: list[str] = []
    seen_pairs: set[tuple[str, str]] = set()
    seen_strings: set[str] = set()

    def _rec_pair(k: str, v: str) -> None:
        ck = k.strip()
        cv = v.strip()
        if not cv or len(cv) > 512:
            return
        if ck and len(ck) <= 256 and (ck, cv) not in seen_pairs:
            seen_pairs.add((ck, cv))
            pairs.append((ck, cv))
        if cv not in seen_strings:
            seen_strings.add(cv)
            strings.append(cv)

    def _rec_str(v: str) -> None:
        cv = v.strip()
        if cv and len(cv) <= 512 and cv not in seen_strings:
            seen_strings.add(cv)
            strings.append(cv)

    def _walk_obj(node: Any, depth: int = 0) -> None:
        if depth > 64 or node is None or isinstance(node, bool):
            return
        if isinstance(node, _JsonObjectPairs):
            for k, v in node:
                ks = str(k or "")
                if isinstance(v, str):
                    _rec_pair(ks, str(v))
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    _rec_pair(ks, str(v))
                else:
                    _walk_obj(v, depth + 1)
            return
        if isinstance(node, dict):
            for k, v in node.items():
                ks = str(k or "")
                if isinstance(v, str):
                    _rec_pair(ks, v)
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    _rec_pair(ks, str(v))
                else:
                    _walk_obj(v, depth + 1)
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                if isinstance(item, str) and not isinstance(item, _RawJsonLiteral):
                    _rec_str(item)
                else:
                    _walk_obj(item, depth + 1)
            return
        if isinstance(node, str) and not isinstance(node, _RawJsonLiteral):
            _rec_str(node)

    if payload is not None:
        _walk_obj(payload, 0)

    for text in decode_raw_body_texts(raw_body):
        parsed_ok = False
        try:
            tolerant_ast = json.loads(
                text,
                object_pairs_hook=_JsonObjectPairs,
                parse_float=_RawJsonLiteral,
                parse_int=_RawJsonLiteral,
                parse_constant=_RawJsonLiteral,
            )
            _walk_obj(tolerant_ast, 0)
            parsed_ok = True
        except Exception:
            parsed_ok = False

        if not parsed_ok:
            for m_kv in re.finditer(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"', text):
                raw_k, raw_v = m_kv.group(1), m_kv.group(2)
                if len(raw_k) <= 1024 and 1 <= len(raw_v) <= 4096:
                    _rec_pair(
                        unescape_json_string_literal(raw_k),
                        unescape_json_string_literal(raw_v),
                    )
            for m_kn in re.finditer(r'"((?:[^"\\]|\\.)*)"\s*:\s*([+-]?\d{1,64})\b', text):
                raw_k, raw_num = m_kn.group(1), m_kn.group(2)
                if len(raw_k) <= 1024:
                    _rec_pair(unescape_json_string_literal(raw_k), raw_num)
            for m_str in re.finditer(r'"((?:[^"\\]|\\.)*)"', text):
                raw_s = m_str.group(1)
                if 1 <= len(raw_s) <= 4096:
                    _rec_str(unescape_json_string_literal(raw_s))

        if "Content-Disposition:" in text and "name=" in text:
            for m_mp in re.finditer(r'name="([^"]{1,256})"(?:;[^\r\n]*)?\r?\n\r?\n([^\r\n]{1,1024})', text):
                raw_mp_k = m_mp.group(1)
                raw_mp_v = m_mp.group(2).strip()
                mp_k = unquote_plus(unescape_json_string_literal(raw_mp_k))
                _rec_pair(raw_mp_k, raw_mp_v)
                _rec_pair(mp_k, raw_mp_v)
                _rec_pair(mp_k, unescape_json_string_literal(raw_mp_v))

        if "=" in text and not text.startswith("{"):
            try:
                for fq_k, fq_v in parse_qsl(text, keep_blank_values=False):
                    _rec_pair(fq_k, fq_v)
            except Exception:
                pass

    return pairs, strings


def _iter_header_pairs(headers: Any) -> list[tuple[str, str]]:
    """Đọc toàn bộ cặp header (kể cả các header trùng tên) dưới dạng (lower_name, value)."""
    if headers is None:
        return []
    out: list[tuple[str, str]] = []
    raw_list = getattr(headers, "raw", None)
    if isinstance(raw_list, (list, tuple)) and raw_list:
        for item in raw_list:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                hk = item[0].decode("latin-1", errors="ignore") if isinstance(item[0], (bytes, bytearray)) else str(item[0])
                hv = item[1].decode("latin-1", errors="ignore") if isinstance(item[1], (bytes, bytearray)) else str(item[1])
                out.append((hk.strip().lower(), hv.strip()))
        return out
    if hasattr(headers, "keys") and hasattr(headers, "getlist"):
        for hk in headers.keys():
            for hv in headers.getlist(hk):
                out.append((str(hk).strip().lower(), str(hv or "").strip()))
        return out
    if hasattr(headers, "items"):
        for hk, hv in headers.items():
            out.append((str(hk).strip().lower(), str(hv or "").strip()))
    return out


def extract_all_request_qr_credentials(
    request: Any | None = None,
    payload: Any = None,
    raw_body: bytes | None = None,
) -> dict[str, list[str]]:
    """Thu thập toàn diện mọi thông tin định danh phiên/token/scan_nonce trên tất cả carrier:
    Cookies, Headers (kể cả trùng lặp & Bearer), Query Params (multi_items), và Raw Body khoan dung (JSON \\uXXXX, form, multipart).
    """
    nonces: list[str] = []
    session_ids: list[str] = []
    post_scan_tokens: list[str] = []
    qr_tokens: list[str] = []
    all_secrets: list[str] = []

    def _push(target: list[str], val: str) -> None:
        c = val.strip()
        if c and len(c) <= 512:
            if c not in target:
                target.append(c)
            if c not in all_secrets:
                all_secrets.append(c)

    if request is not None:
        if raw_body is None:
            cached = getattr(getattr(request, "state", None), "qr_raw_body", None)
            if isinstance(cached, (bytes, bytearray)):
                raw_body = bytes(cached)
            else:
                priv_body = getattr(request, "_body", None)
                if isinstance(priv_body, (bytes, bytearray)):
                    raw_body = bytes(priv_body)

        cookies = getattr(request, "cookies", None) or {}
        if hasattr(cookies, "items"):
            for ck_k, ck_v in cookies.items():
                k = str(ck_k or "").strip()
                v = str(ck_v or "").strip()
                if not v:
                    continue
                _push(all_secrets, v)
                if k in (QR_SCAN_COOKIE_NAME, "scan_nonce"):
                    _push(nonces, v)
                elif k in (QR_SESSION_COOKIE_NAME, "guest_session_id", "session_id", "session_token", "sh_session_token"):
                    _push(session_ids, v)
                elif k == "post_scan_token":
                    _push(post_scan_tokens, v)
                elif k in ("token", "qr_token"):
                    _push(qr_tokens, v)

        for hk, hv in _iter_header_pairs(getattr(request, "headers", None)):
            if not hv:
                continue
            if hk == "authorization":
                if hv.lower().startswith("bearer "):
                    bt = hv[7:].strip()
                    if bt:
                        _push(session_ids, bt)
                else:
                    _push(all_secrets, hv)
                continue
            if hk in ("x-qr-scan-nonce", "x-scan-nonce"):
                _push(nonces, hv)
            elif hk in ("x-qr-session-id", "x-session-token"):
                _push(session_ids, hv)
            elif hk == "x-qr-post-scan-token":
                _push(post_scan_tokens, hv)
            elif hk == "x-qr-token":
                _push(qr_tokens, hv)
            elif hk not in _NON_CREDENTIAL_HTTP_HEADERS:
                _push(all_secrets, hv)

        qp = getattr(request, "query_params", None)
        if qp is not None:
            qp_items = qp.multi_items() if hasattr(qp, "multi_items") else qp.items()
            for raw_qk, raw_qv in qp_items:
                qk = str(raw_qk or "").strip()
                qv = str(raw_qv or "").strip()
                if not qv:
                    continue
                _push(all_secrets, qv)
                if qk in ("scan_nonce", QR_SCAN_COOKIE_NAME):
                    _push(nonces, qv)
                elif qk in (QR_SESSION_COOKIE_NAME, "session_id", "guest_session_id", "session_token", "sh_session_token"):
                    _push(session_ids, qv)
                elif qk == "post_scan_token":
                    _push(post_scan_tokens, qv)
                elif qk in ("token", "qr_token"):
                    _push(qr_tokens, qv)

    body_pairs, body_strings = extract_tolerant_raw_body_pairs_and_strings(raw_body=raw_body, payload=payload)
    for bk, bv in body_pairs:
        if bk in ("scan_nonce", QR_SCAN_COOKIE_NAME):
            _push(nonces, bv)
        elif bk in (QR_SESSION_COOKIE_NAME, "session_id", "guest_session_id", "session_token", "sh_session_token"):
            _push(session_ids, bv)
        elif bk == "post_scan_token":
            _push(post_scan_tokens, bv)
        elif bk in ("token", "qr_token"):
            _push(qr_tokens, bv)
        else:
            _push(all_secrets, bv)
    for bs in body_strings:
        _push(all_secrets, bs)

    return {
        "nonces": nonces,
        "session_ids": session_ids,
        "post_scan_tokens": post_scan_tokens,
        "qr_tokens": qr_tokens,
        "all_candidate_secrets": all_secrets,
    }


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
        if val_hash and val_hash in getattr(mgr3, "known_qr_scan_nonce_hashes", set()):
            return True
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
    known_qr_scan_nonce_hashes: set[str]

    def _ensure_qr_stores(self) -> None:
        if not hasattr(self, "used_qr_tokens") or self.used_qr_tokens is None:
            self.used_qr_tokens = set()
        if not hasattr(self, "active_qr_tokens") or self.active_qr_tokens is None:
            self.active_qr_tokens = {}
        if not hasattr(self, "guest_qr_sessions") or self.guest_qr_sessions is None:
            self.guest_qr_sessions = {}
        if not hasattr(self, "pending_guest_email_otps") or self.pending_guest_email_otps is None:
            self.pending_guest_email_otps = {}
        if not hasattr(self, "known_qr_scan_nonce_hashes") or self.known_qr_scan_nonce_hashes is None:
            self.known_qr_scan_nonce_hashes = set()

    def _purge_pending_otps_for_sessions(self, session_ids: set[str]) -> int:
        """Xóa tức thì mọi mã OTP email đang chờ thuộc các phiên QR đã bị hủy hoặc hết hạn."""
        if not session_ids:
            return 0
        with _QR_ATOMIC_LOCK:
            self._ensure_qr_stores()
            purged = 0
            for mail_k, rec in list(self.pending_guest_email_otps.items()):
                if isinstance(rec, dict) and str(rec.get("session_id") or "").strip() in session_ids:
                    self.pending_guest_email_otps.pop(mail_k, None)
                    purged += 1
            return purged

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
            purged_sids: set[str] = set()

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
                    purged_sids.add(sid)
                    invalidated_count += 1

            if purged_sids:
                self._purge_pending_otps_for_sessions(purged_sids)
            return invalidated_count

    def invalidate_qr_session_on_mistake(
        self,
        session_id: str,
        reason: str = "REGISTRATION_ATTEMPT_FAILED_MUST_RESCAN",
    ) -> bool:
        """Hủy tức thì phiên/token và mọi OTP đang chờ sau khi người quét thao tác sai hoặc gửi dữ liệu lỗi (bắt buộc quét lại QR mới)."""
        clean_sid = str(session_id or "").strip()
        if not clean_sid:
            return False
        with _QR_ATOMIC_LOCK:
            self._ensure_qr_stores()
            s_meta = self.guest_qr_sessions.get(clean_sid)
            if not isinstance(s_meta, dict):
                return False
            cur_st = str(s_meta.get("status") or "").upper()
            if cur_st in ("CONSUMED", "EXPIRED"):
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
            self._purge_pending_otps_for_sessions({clean_sid})
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
            if target_window is not None:
                if isinstance(target_window, (bool, float)):
                    return {
                        "ok": False,
                        "reason": "INVALID_TARGET_WINDOW",
                        "error": "Thông số cửa sổ thời gian không hợp lệ!",
                        "status_code": 400,
                    }
                try:
                    parsed_win = int(target_window)
                except (ValueError, TypeError, OverflowError):
                    return {
                        "ok": False,
                        "reason": "INVALID_TARGET_WINDOW",
                        "error": "Thông số cửa sổ thời gian không hợp lệ!",
                        "status_code": 400,
                    }
                if parsed_win < 0 or parsed_win > 10**11:
                    return {
                        "ok": False,
                        "reason": "INVALID_TARGET_WINDOW",
                        "error": "Thông số cửa sổ thời gian vượt ngoài phạm vi hợp lệ!",
                        "status_code": 400,
                    }
                if parsed_win != token_win:
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
            if nonce_hash:
                self.known_qr_scan_nonce_hashes.add(nonce_hash)

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
