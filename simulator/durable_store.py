"""Module simulator.durable_store: Lưu trữ bền vững miễn phí đa tầng (Multi-Tier Free Durable Persistence)
cho Hồ sơ Giọng nói (Enrollments), Phân quyền Tài khoản (Grants), Link mời và Phiên đăng nhập trên Vercel Serverless.

Kiến trúc 3 tầng bền vững 100% miễn phí (không phụ thuộc Vercel Blob đang bị 403 suspended):
1. Tầng 1 (Cloud Durable - Gmail IMAP App-State Store):
   - Tận dụng trực tiếp `SMTP_USER` + `GMAIL_APP_PASSWORD` đã có sẵn trên Vercel Production.
   - Dùng thư viện chuẩn `imaplib.IMAP4_SSL("imap.gmail.com", timeout=6.0)` và `email.message.EmailMessage`.
   - Nén trạng thái tổng hợp JSON (`gzip` + `base64`) của các tệp trạng thái quan trọng:
     `voiceprints.json`, `accounts_3layer.json`, `invite_links_3layer.json`,
     `family_email_allowlist.json`, `custom_rules_overlay.json`, `user_sessions.json`.
   - Ghi trực tiếp vào hộp thư qua lệnh `imap.append("[Gmail]/Drafts" hoặc "INBOX", "\\Seen \\Draft", ..., msg_bytes)`
     với tiêu đề cố định `Subject: [SMARTHOME_DURABLE_STATE_V1]`.
   - Tuyệt đối KHÔNG gửi email ra ngoài hay tạo thông báo đẩy, miễn phí 100% trong 15GB Google,
     bền vững qua mọi lần cold-start của Vercel Serverless.
2. Tầng 2 (Local Persistent SQLite + JSON Directory ngoài `/tmp` & Upstash REST KV):
   - Lưu đồng thời vào bảng SQLite bền vững (`durable_kv_store.sqlite3`) và thư mục JSON ngoài `/tmp/smarthome_data`
     (hoặc qua biến môi trường `SMARTHOME_DURABLE_DIR` / `UPSTASH_REDIS_REST_URL`).
3. Tầng 3 (Chế độ Offline/Test Sandbox `SIMULATOR_OFFLINE_SANDBOX=1` hoặc `PYTEST_CURRENT_TEST`):
   - Hỗ trợ kiểm thử mô phỏng cold-start cục bộ (xóa `/tmp/smarthome_data`, khôi phục 100% enrollments & grants
     từ `DurableStateStore`) mà không cần gọi mạng khi đang chạy pytest/sandbox.
"""

from __future__ import annotations

import base64
import contextlib
import email
from email.message import EmailMessage
import email.policy
import email.utils
import gzip
import hashlib
import imaplib
import json
import logging
import os
import pathlib
import re
import sqlite3
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

DURABLE_IMAP_SUBJECT = "[SMARTHOME_DURABLE_STATE_V1]"
DURABLE_MARKER_START = "SMARTHOME_STATE_GZIP_B64_START"
DURABLE_MARKER_END = "SMARTHOME_STATE_GZIP_B64_END"
IMAP_HOST_DEFAULT = "imap.gmail.com"
IMAP_TIMEOUT_SECONDS = 6.0
CLOUD_SYNC_TTL_SECONDS = 5.0

TRACKED_STATE_FILES: tuple[str, ...] = (
    "voiceprints.json",
    "accounts_3layer.json",
    "invite_links_3layer.json",
    "family_email_allowlist.json",
    "custom_rules_overlay.json",
    "user_sessions.json",
)

_STORE_LOCK = threading.RLock()
_MEMORY_VAULT: dict[str, bytes] = {}


def is_offline_sandbox_or_test() -> bool:
    """Kiểm tra có đang chạy trong môi trường kiểm thử/sandbox offline hay không."""
    if os.environ.get("SMARTHOME_FORCE_CLOUD_DURABLE") == "1":
        return False
    if not os.environ.get("VERCEL"):
        return True
    if (
        os.environ.get("SIMULATOR_OFFLINE_SANDBOX") == "1"
        or os.environ.get("PYTEST_CURRENT_TEST")
        or os.environ.get("PYTEST") == "1"
    ):
        return True
    return False


def _resolve_durable_vault_dir() -> pathlib.Path:
    """Xác định thư mục lưu trữ bền vững nằm ngoài `/tmp/smarthome_data`."""
    custom_dir = os.environ.get("SMARTHOME_DURABLE_DIR", "").strip()
    if custom_dir:
        p = pathlib.Path(custom_dir)
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass

    if not os.environ.get("VERCEL"):
        home_vault = pathlib.Path(tempfile.gettempdir()) / "smarthome_durable_vault"
        try:
            home_vault.mkdir(parents=True, exist_ok=True)
            return home_vault
        except Exception:
            pass

    fallback = pathlib.Path(tempfile.gettempdir()) / "smarthome_durable_vault"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


class DurableStateStore:
    """Bộ quản lý lưu trữ bền vững đa tầng miễn phí (Gmail IMAP + SQLite + REST KV + Memory Vault)."""

    def __init__(
        self,
        vault_dir: pathlib.Path | None = None,
        durable_dir: pathlib.Path | None = None,
        offline_sandbox: bool | None = None,
        **kwargs: Any,
    ) -> None:
        self._lock = _STORE_LOCK
        self.vault_dir = vault_dir or durable_dir or _resolve_durable_vault_dir()
        self.offline_sandbox = offline_sandbox
        self.sqlite_path = self.vault_dir / "durable_kv_store.sqlite3"
        self._memory_vault: dict[str, bytes] = {}
        self._last_cloud_pull_ts: float = 0.0
        self._last_cloud_push_hash: str = ""
        self._init_sqlite()

    def _init_sqlite(self) -> None:
        try:
            self.vault_dir.mkdir(parents=True, exist_ok=True)
            with self._lock, contextlib.closing(sqlite3.connect(str(self.sqlite_path), timeout=5.0)) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS durable_kv (
                        key TEXT PRIMARY KEY,
                        value_b64 TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.commit()
        except Exception as exc:
            logger.debug("Durable SQLite init skipped: %s", exc)

    def _write_local_sqlite_and_file(self, filename: str, raw_bytes: bytes) -> bool:
        clean_name = pathlib.Path(filename).name
        b64_str = base64.b64encode(raw_bytes).decode("ascii")
        digest = hashlib.sha256(raw_bytes).hexdigest()
        now = time.time()
        file_ok = False
        sql_ok = False
        with self._lock:
            self._memory_vault[clean_name] = raw_bytes
            try:
                self.vault_dir.mkdir(parents=True, exist_ok=True)
                bak_file = self.vault_dir / clean_name
                bak_file.write_bytes(raw_bytes)
                file_ok = True
            except Exception:
                pass
            try:
                with contextlib.closing(sqlite3.connect(str(self.sqlite_path), timeout=5.0)) as conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO durable_kv (key, value_b64, sha256, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (clean_name, b64_str, digest, now),
                    )
                    conn.commit()
                    sql_ok = True
            except Exception:
                pass
        return bool(file_ok or sql_ok)

    def _read_local_sqlite_or_file(self, filename: str) -> bytes | None:
        clean_name = pathlib.Path(filename).name
        with self._lock:
            if clean_name in self._memory_vault:
                return self._memory_vault[clean_name]
            try:
                if self.sqlite_path.exists():
                    with contextlib.closing(sqlite3.connect(str(self.sqlite_path), timeout=5.0)) as conn:
                        cur = conn.execute(
                            "SELECT value_b64 FROM durable_kv WHERE key = ?",
                            (clean_name,),
                        )
                        row = cur.fetchone()
                        if row and row[0]:
                            raw = base64.b64decode(row[0].encode("ascii"))
                            self._memory_vault[clean_name] = raw
                            return raw
            except Exception:
                pass
            try:
                bak_file = self.vault_dir / clean_name
                if bak_file.exists():
                    raw = bak_file.read_bytes()
                    self._memory_vault[clean_name] = raw
                    return raw
            except Exception:
                pass
        return None

    @staticmethod
    def encode_bundle_gzip_b64(bundle: dict[str, Any]) -> str:
        """Nén từ điển trạng thái bằng gzip + base64 chuẩn UTF-8."""
        raw_json = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        compressed = gzip.compress(raw_json, compresslevel=6)
        return base64.b64encode(compressed).decode("ascii")

    @staticmethod
    def decode_bundle_gzip_b64(encoded_str: str) -> dict[str, Any] | None:
        """Giải mã chuỗi base64 + gzip về lại từ điển trạng thái."""
        try:
            clean = re.sub(r"\s+", "", encoded_str.strip())
            if not clean:
                return None
            compressed = base64.b64decode(clean.encode("ascii"))
            raw_json = gzip.decompress(compressed)
            obj = json.loads(raw_json.decode("utf-8"))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    def _collect_current_bundle(self, data_dir: pathlib.Path | None = None) -> dict[str, Any]:
        files_map: dict[str, str] = {}
        with self._lock:
            for fname in TRACKED_STATE_FILES:
                raw: bytes | None = None
                if data_dir is not None:
                    candidate = data_dir / fname
                    if candidate.exists():
                        try:
                            raw = candidate.read_bytes()
                            self._write_local_sqlite_and_file(fname, raw)
                        except Exception:
                            raw = None
                if raw is None:
                    raw = self._read_local_sqlite_or_file(fname)
                if raw is not None:
                    files_map[fname] = base64.b64encode(raw).decode("ascii")
        return {
            "version": 1,
            "updated_at": time.time(),
            "files": files_map,
        }

    def _apply_bundle_to_local(self, bundle: dict[str, Any], target_dir: pathlib.Path | None = None) -> list[str]:
        restored: list[str] = []
        if not isinstance(bundle, dict):
            return restored
        files_map = bundle.get("files")
        if not isinstance(files_map, dict):
            return restored
        with self._lock:
            for fname, b64_content in files_map.items():
                clean_name = pathlib.Path(str(fname)).name
                if clean_name not in TRACKED_STATE_FILES or not isinstance(b64_content, str):
                    continue
                try:
                    raw_bytes = base64.b64decode(b64_content.encode("ascii"))
                except Exception:
                    continue
                self._write_local_sqlite_and_file(clean_name, raw_bytes)
                if target_dir is not None:
                    try:
                        target_dir.mkdir(parents=True, exist_ok=True)
                        dst = target_dir / clean_name
                        dst.write_bytes(raw_bytes)
                    except Exception:
                        pass
                restored.append(clean_name)
        return restored

    _oauth_token_cache: tuple[str, float] = ("", 0.0)

    @staticmethod
    def _get_gmail_credentials() -> tuple[str, str]:
        user = os.environ.get("SMTP_USER", "").strip() or "nep94121@gmail.com"
        pw = (
            os.environ.get("GMAIL_APP_PASSWORD", "").strip()
            or os.environ.get("SMTP_PASSWORD", "").strip()
        )
        return user, pw

    @classmethod
    def _get_gmail_oauth_access_token(cls) -> str:
        """Đổi GOOGLE_OAUTH_REFRESH_TOKEN sang access_token (có bộ nhớ đệm 50 phút, chỉ dùng thư viện chuẩn)."""
        cid = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
        csec = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
        rtok = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN", "").strip()
        if not cid or not csec or not rtok:
            return ""
        cached_tok, exp_ts = cls._oauth_token_cache
        now = time.time()
        if cached_tok and now < exp_ts:
            return cached_tok
        try:
            form = urllib.parse.urlencode(
                {
                    "client_id": cid,
                    "client_secret": csec,
                    "refresh_token": rtok,
                    "grant_type": "refresh_token",
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                "https://oauth2.googleapis.com/token",
                data=form,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=IMAP_TIMEOUT_SECONDS) as resp:
                obj = json.loads(resp.read().decode("utf-8"))
                tok = str(obj.get("access_token") or "").strip()
                ttl = float(obj.get("expires_in") or 3500.0)
                if tok:
                    cls._oauth_token_cache = (tok, now + max(60.0, ttl - 300.0))
                    return tok
        except Exception as exc:
            logger.debug("Gmail OAuth2 token exchange skipped: %s", exc)
        return ""

    def _save_rfc822_via_gmail_oauth_drafts(self, msg_bytes: bytes) -> bool:
        """Lưu/cập nhật bản nháp RFC822 `[SMARTHOME_DURABLE_STATE_V1]` qua Gmail REST API (0 gửi email, 100% miễn phí)."""
        access_token = self._get_gmail_oauth_access_token()
        if not access_token:
            return False
        raw_b64url = base64.urlsafe_b64encode(msg_bytes).decode("ascii")
        payload_bytes = json.dumps({"message": {"raw": raw_b64url}}).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        try:
            q = urllib.parse.quote(f'subject:"{DURABLE_IMAP_SUBJECT}"')
            list_req = urllib.request.Request(
                f"https://gmail.googleapis.com/gmail/v1/users/me/drafts?q={q}&maxResults=1",
                headers={"Authorization": f"Bearer {access_token}"},
                method="GET",
            )
            existing_id = ""
            with contextlib.suppress(Exception):
                with urllib.request.urlopen(list_req, timeout=IMAP_TIMEOUT_SECONDS) as lresp:
                    lobj = json.loads(lresp.read().decode("utf-8"))
                    drafts = lobj.get("drafts") or []
                    if drafts and isinstance(drafts[0], dict):
                        existing_id = str(drafts[0].get("id") or "").strip()
            if existing_id:
                put_body = json.dumps({"id": existing_id, "message": {"raw": raw_b64url}}).encode("utf-8")
                put_req = urllib.request.Request(
                    f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{existing_id}",
                    data=put_body,
                    headers=headers,
                    method="PUT",
                )
                with contextlib.suppress(Exception):
                    with urllib.request.urlopen(put_req, timeout=IMAP_TIMEOUT_SECONDS) as presp:
                        if 200 <= presp.status < 300:
                            return True
            post_req = urllib.request.Request(
                "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
                data=payload_bytes,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(post_req, timeout=IMAP_TIMEOUT_SECONDS) as cresp:
                return 200 <= cresp.status < 300
        except Exception as exc:
            logger.debug("Gmail OAuth2 Drafts save skipped: %s", exc)
            return False

    def _load_rfc822_via_gmail_oauth_drafts(self) -> dict[str, Any] | None:
        """Tải bản nháp RFC822 `[SMARTHOME_DURABLE_STATE_V1]` mới nhất qua Gmail REST API."""
        access_token = self._get_gmail_oauth_access_token()
        if not access_token:
            return None
        try:
            q = urllib.parse.quote(f'subject:"{DURABLE_IMAP_SUBJECT}"')
            list_req = urllib.request.Request(
                f"https://gmail.googleapis.com/gmail/v1/users/me/drafts?q={q}&maxResults=5",
                headers={"Authorization": f"Bearer {access_token}"},
                method="GET",
            )
            with urllib.request.urlopen(list_req, timeout=IMAP_TIMEOUT_SECONDS) as lresp:
                lobj = json.loads(lresp.read().decode("utf-8"))
                drafts = lobj.get("drafts") or []
            for d_item in drafts:
                did = str((d_item or {}).get("id") or "").strip()
                if not did:
                    continue
                get_req = urllib.request.Request(
                    f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{did}?format=raw",
                    headers={"Authorization": f"Bearer {access_token}"},
                    method="GET",
                )
                with urllib.request.urlopen(get_req, timeout=IMAP_TIMEOUT_SECONDS) as gresp:
                    gobj = json.loads(gresp.read().decode("utf-8"))
                    raw_str = str(((gobj.get("message") or {}).get("raw")) or "").strip()
                    if not raw_str:
                        continue
                    padded = raw_str + ("=" * (-len(raw_str) % 4))
                    raw_email = base64.urlsafe_b64decode(padded.encode("ascii"))
                    bundle = self._extract_bundle_from_rfc822_bytes(raw_email)
                    if bundle:
                        return bundle
        except Exception as exc:
            logger.debug("Gmail OAuth2 Drafts fetch skipped: %s", exc)
        return None

    def _can_use_live_gmail_oauth(self) -> bool:
        if self.offline_sandbox is True:
            return False
        if (
            os.environ.get("SIMULATOR_OFFLINE_SANDBOX") == "1"
            or os.environ.get("PYTEST_CURRENT_TEST")
            or os.environ.get("PYTEST") == "1"
        ):
            return False
        if getattr(imaplib.IMAP4_SSL, "__module__", "") != "imaplib":
            return False
        return bool(
            os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
            and os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
            and os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN", "").strip()
        )

    def _save_bundle_to_gmail_imap(self, bundle: dict[str, Any]) -> bool:
        """Lưu gói trạng thái nén vào Gmail Drafts (qua OAuth2 REST hoặc IMAP SSL, không gửi email, không thông báo)."""
        smtp_user, app_pw = self._get_gmail_credentials()
        can_oauth = self._can_use_live_gmail_oauth()
        if (not smtp_user or not app_pw) and not can_oauth:
            return False

        encoded_payload = self.encode_bundle_gzip_b64(bundle)
        payload_hash = hashlib.sha256(encoded_payload.encode("ascii")).hexdigest()

        msg = EmailMessage()
        msg["Subject"] = DURABLE_IMAP_SUBJECT
        msg["From"] = smtp_user or "nep94121@gmail.com"
        msg["To"] = smtp_user or "nep94121@gmail.com"
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["X-SmartHome-Durable"] = "v1"
        msg["X-SmartHome-Sha256"] = payload_hash
        msg.set_content(
            f"{DURABLE_MARKER_START}\n{encoded_payload}\n{DURABLE_MARKER_END}\n",
            charset="utf-8",
        )
        msg_bytes = msg.as_bytes()
        if can_oauth:
            if self._save_rfc822_via_gmail_oauth_drafts(msg_bytes):
                self._last_cloud_push_hash = payload_hash
                return True

        if not smtp_user or not app_pw:
            return False
        imap_host = os.environ.get("IMAP_HOST", "").strip() or IMAP_HOST_DEFAULT

        try:
            with imaplib.IMAP4_SSL(imap_host, 993, timeout=IMAP_TIMEOUT_SECONDS) as imap:
                imap.login(smtp_user, app_pw)
                target_mailbox = "INBOX"
                for folder_cand in ("[Gmail]/Drafts", "Drafts", "INBOX"):
                    try:
                        typ, _ = imap.select(folder_cand)
                        if typ == "OK":
                            target_mailbox = folder_cand
                            break
                    except Exception:
                        continue

                date_time = imaplib.Time2Internaldate(time.time())
                typ, _ = imap.append(target_mailbox, "(\\Seen \\Draft)", date_time, msg_bytes)
                if typ == "OK":
                    self._last_cloud_push_hash = payload_hash
                    return True
        except Exception as exc:
            logger.debug("Gmail IMAP durable state append skipped: %s", exc)
            if has_oauth and not imap_is_mocked:
                if self._save_rfc822_via_gmail_oauth_drafts(msg_bytes):
                    self._last_cloud_push_hash = payload_hash
                    return True
        return False

    @classmethod
    def _extract_bundle_from_rfc822_bytes(cls, raw_email: bytes) -> dict[str, Any] | None:
        """Giải mã RFC822 MIME email (hỗ trợ base64, quoted-printable, multipart) để trích xuất gói trạng thái."""
        if not raw_email:
            return None
        candidate_texts: list[str] = []
        try:
            parsed_msg = email.message_from_bytes(raw_email, policy=email.policy.default)
            parts = list(parsed_msg.walk()) if parsed_msg.is_multipart() else [parsed_msg]
            for p in parts:
                if p.get_content_maintype() == "multipart":
                    continue
                with contextlib.suppress(Exception):
                    c = p.get_content()
                    if isinstance(c, str):
                        candidate_texts.append(c)
                    elif isinstance(c, (bytes, bytearray)):
                        candidate_texts.append(bytes(c).decode("utf-8", errors="ignore"))
                with contextlib.suppress(Exception):
                    dec = p.get_payload(decode=True)
                    if isinstance(dec, (bytes, bytearray)):
                        candidate_texts.append(bytes(dec).decode("utf-8", errors="ignore"))
        except Exception:
            pass
        candidate_texts.append(raw_email.decode("utf-8", errors="ignore"))

        pattern = rf"{re.escape(DURABLE_MARKER_START)}\s*(.+?)\s*{re.escape(DURABLE_MARKER_END)}"
        for text in candidate_texts:
            if not text:
                continue
            m = re.search(pattern, text, flags=re.DOTALL)
            if m:
                bundle = cls.decode_bundle_gzip_b64(m.group(1))
                if bundle:
                    return bundle
        return None

    def _load_bundle_from_gmail_imap(self) -> dict[str, Any] | None:
        """Tải bản ghi `[SMARTHOME_DURABLE_STATE_V1]` mới nhất từ Gmail Drafts (OAuth2 REST hoặc IMAP)."""
        smtp_user, app_pw = self._get_gmail_credentials()
        can_oauth = self._can_use_live_gmail_oauth()
        if (not smtp_user or not app_pw) and not can_oauth:
            return None

        if can_oauth:
            bundle_oauth = self._load_rfc822_via_gmail_oauth_drafts()
            if bundle_oauth:
                return bundle_oauth

        if not smtp_user or not app_pw:
            return None

        imap_host = os.environ.get("IMAP_HOST", "").strip() or IMAP_HOST_DEFAULT
        try:
            with imaplib.IMAP4_SSL(imap_host, 993, timeout=IMAP_TIMEOUT_SECONDS) as imap:
                imap.login(smtp_user, app_pw)
                for folder_cand in ("[Gmail]/Drafts", "Drafts", "INBOX"):
                    try:
                        typ, _ = imap.select(folder_cand, readonly=True)
                        if typ != "OK":
                            continue
                        typ_s, data_s = imap.search(None, f'(SUBJECT "{DURABLE_IMAP_SUBJECT}")')
                        if typ_s != "OK" or not data_s or not data_s[0]:
                            continue
                        msg_ids = data_s[0].split()
                        if not msg_ids:
                            continue
                        latest_id = msg_ids[-1]
                        typ_f, data_f = imap.fetch(latest_id, "(RFC822)")
                        if typ_f != "OK" or not data_f:
                            continue
                        raw_email = b""
                        for part in data_f:
                            if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], (bytes, bytearray)):
                                raw_email = bytes(part[1])
                                break
                        bundle = self._extract_bundle_from_rfc822_bytes(raw_email)
                        if bundle:
                            return bundle
                    except Exception:
                        continue
        except Exception as exc:
            logger.debug("Gmail IMAP durable state fetch skipped: %s", exc)
            if can_oauth:
                return self._load_rfc822_via_gmail_oauth_drafts()
        return None

    def _save_bundle_to_upstash_kv(self, bundle: dict[str, Any]) -> bool:
        """Lưu trạng thái lên Upstash Redis REST KV miễn phí nếu biến môi trường được cấu hình."""
        rest_url = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
        rest_token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
        if not rest_url or not rest_token:
            return False
        encoded_payload = self.encode_bundle_gzip_b64(bundle)
        try:
            body = json.dumps(["SET", "smarthome:durable_state:v1", encoded_payload]).encode("utf-8")
            req = urllib.request.Request(
                rest_url,
                data=body,
                headers={
                    "Authorization": f"Bearer {rest_token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False

    def _load_bundle_from_upstash_kv(self) -> dict[str, Any] | None:
        rest_url = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
        rest_token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
        if not rest_url or not rest_token:
            return None
        try:
            req = urllib.request.Request(
                f"{rest_url}/get/smarthome:durable_state:v1",
                headers={"Authorization": f"Bearer {rest_token}"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                raw_val = data.get("result") if isinstance(data, dict) else None
                if isinstance(raw_val, str) and raw_val:
                    return self.decode_bundle_gzip_b64(raw_val)
        except Exception:
            pass
        return None

    def save_state_file(
        self,
        filename: str,
        data_bytes: bytes | str,
        sync_cloud: bool = True,
        data_dir: pathlib.Path | None = None,
    ) -> bool:
        """Lưu một tệp trạng thái vào Durable Store (SQLite + Memory + Cloud IMAP/KV).
        Nếu `sync_cloud=True`, bắt buộc ít nhất một kênh lưu trữ Cloud (Upstash KV hoặc Gmail IMAP) thành công mới trả về `True`.
        """
        clean_name = pathlib.Path(filename).name
        raw = data_bytes.encode("utf-8") if isinstance(data_bytes, str) else bytes(data_bytes)
        local_ok = self._write_local_sqlite_and_file(clean_name, raw)

        # Đồng bộ kèm voiceprints.json và custom_rules_overlay.json nếu có trong cùng thư mục
        if data_dir is not None:
            for extra_name in ("voiceprints.json", "custom_rules_overlay.json"):
                if extra_name != clean_name:
                    extra_path = data_dir / extra_name
                    if extra_path.exists():
                        try:
                            self._write_local_sqlite_and_file(extra_name, extra_path.read_bytes())
                        except Exception:
                            pass

        if sync_cloud:
            bundle = self._collect_current_bundle(data_dir=data_dir)
            kv_ok = self._save_bundle_to_upstash_kv(bundle)
            imap_ok = self._save_bundle_to_gmail_imap(bundle)
            cloud_ok = bool(kv_ok or imap_ok)
            return bool(local_ok and cloud_ok)
        return bool(local_ok)

    def load_state_file(
        self,
        filename: str,
        sync_cloud: bool = False,
        data_dir: pathlib.Path | None = None,
    ) -> bytes | None:
        """Đọc tệp trạng thái từ Durable Store (ưu tiên bộ nhớ/SQLite, fallback tải từ Cloud IMAP/KV)."""
        clean_name = pathlib.Path(filename).name
        local_raw = self._read_local_sqlite_or_file(clean_name)
        if local_raw is not None and not sync_cloud:
            return local_raw

        if sync_cloud or local_raw is None:
            now = time.time()
            if sync_cloud or local_raw is None or (now - self._last_cloud_pull_ts) >= CLOUD_SYNC_TTL_SECONDS:
                self._last_cloud_pull_ts = now
                bundle = self._load_bundle_from_upstash_kv() or self._load_bundle_from_gmail_imap()
                if bundle:
                    self._apply_bundle_to_local(bundle, target_dir=data_dir)
                    local_raw = self._read_local_sqlite_or_file(clean_name)
        return local_raw

    def sync_to_durable_store(
        self,
        data_dir: pathlib.Path | None = None,
        force_cloud: bool = False,
    ) -> dict[str, Any]:
        """Đồng bộ toàn bộ các tệp trạng thái trong `data_dir` vào Durable Store."""
        bundle = self._collect_current_bundle(data_dir=data_dir)
        cloud_saved = False
        if force_cloud or not is_offline_sandbox_or_test():
            kv_ok = self._save_bundle_to_upstash_kv(bundle)
            imap_ok = self._save_bundle_to_gmail_imap(bundle)
            cloud_saved = bool(kv_ok or imap_ok)
        return {
            "ok": True if not force_cloud else cloud_saved,
            "files_saved": list(bundle.get("files", {}).keys()),
            "cloud_saved": cloud_saved,
        }

    def sync_from_durable_store(
        self,
        data_dir: pathlib.Path | None = None,
        force_cloud: bool = False,
        only_missing: bool = False,
    ) -> dict[str, Any]:
        """Khôi phục các tệp trạng thái từ Durable Store về `data_dir` (phục hồi sau cold-start)."""
        cloud_loaded = False
        has_any_local = any(self._read_local_sqlite_or_file(f) is not None for f in TRACKED_STATE_FILES)
        if force_cloud or not has_any_local or not is_offline_sandbox_or_test():
            now = time.time()
            if force_cloud or not has_any_local or (now - self._last_cloud_pull_ts) >= CLOUD_SYNC_TTL_SECONDS:
                self._last_cloud_pull_ts = now
                bundle = self._load_bundle_from_upstash_kv() or self._load_bundle_from_gmail_imap()
                if bundle:
                    self._apply_bundle_to_local(bundle, target_dir=None)
                    cloud_loaded = True

        restored_files: list[str] = []
        if data_dir is not None:
            data_dir.mkdir(parents=True, exist_ok=True)
            for fname in TRACKED_STATE_FILES:
                dst = data_dir / fname
                if only_missing and dst.exists():
                    continue
                raw = self._read_local_sqlite_or_file(fname)
                if raw is not None:
                    try:
                        dst.write_bytes(raw)
                        restored_files.append(fname)
                    except Exception:
                        pass

        return {
            "ok": True,
            "restored_files": restored_files,
            "cloud_loaded": cloud_loaded,
        }

    def simulate_cold_start_recovery(self, target_dir: pathlib.Path) -> dict[str, Any]:
        """Mô phỏng xóa sạch thư mục `/tmp` khi Vercel cold-start và khôi phục 100% từ DurableStateStore."""
        if target_dir.exists():
            for child in list(target_dir.iterdir()):
                if child.is_file():
                    with contextlib.suppress(Exception):
                        child.unlink()
        return self.sync_from_durable_store(data_dir=target_dir, force_cloud=False, only_missing=False)


_GLOBAL_DURABLE_STORE: DurableStateStore | None = None


def get_durable_store() -> DurableStateStore:
    global _GLOBAL_DURABLE_STORE
    with _STORE_LOCK:
        if _GLOBAL_DURABLE_STORE is None:
            _GLOBAL_DURABLE_STORE = DurableStateStore()
        return _GLOBAL_DURABLE_STORE


def save_state_file(
    filename: str,
    data_bytes: bytes | str,
    sync_cloud: bool | None = None,
    data_dir: pathlib.Path | None = None,
) -> bool:
    target_store = get_durable_store()
    if sync_cloud is None:
        effective_sync_cloud = not (
            bool(target_store.offline_sandbox) or is_offline_sandbox_or_test()
        )
    else:
        effective_sync_cloud = bool(sync_cloud)
    return target_store.save_state_file(
        filename=filename,
        data_bytes=data_bytes,
        sync_cloud=effective_sync_cloud,
        data_dir=data_dir,
    )


def load_state_file(
    filename: str,
    sync_cloud: bool = False,
    data_dir: pathlib.Path | None = None,
) -> bytes | None:
    return get_durable_store().load_state_file(
        filename=filename,
        sync_cloud=sync_cloud,
        data_dir=data_dir,
    )


def load_durable_json(
    filename: str,
    path_or_default: Any = None,
    *,
    data_dir: pathlib.Path | None = None,
    sync_cloud: bool = False,
    store: DurableStateStore | None = None,
) -> Any:
    """Đọc cấu trúc JSON từ DurableStateStore (hoặc tệp đĩa dự phòng)."""
    resolved_data_dir = data_dir
    fallback_path: pathlib.Path | None = None
    default_val: Any = None

    if isinstance(path_or_default, (pathlib.Path, str)):
        p = pathlib.Path(path_or_default)
        if p.suffix:
            fallback_path = p
            if resolved_data_dir is None:
                resolved_data_dir = p.parent
        else:
            if resolved_data_dir is None:
                resolved_data_dir = p
    else:
        default_val = path_or_default

    target_store = store or get_durable_store()
    raw = target_store.load_state_file(
        filename=filename,
        sync_cloud=sync_cloud,
        data_dir=resolved_data_dir,
    )
    if raw is None and fallback_path is not None and fallback_path.exists():
        with contextlib.suppress(Exception):
            raw = fallback_path.read_bytes()
    if raw is not None:
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return default_val
    return default_val


def save_durable_json(
    filename: str,
    payload: Any,
    path_or_data_dir: pathlib.Path | str | None = None,
    *,
    data_dir: pathlib.Path | None = None,
    sync_cloud: bool | None = None,
    store: DurableStateStore | None = None,
) -> bool:
    """Lưu cấu trúc JSON vào DurableStateStore và tệp đích (nếu được truyền vào)."""
    resolved_data_dir = data_dir
    target_file: pathlib.Path | None = None
    if isinstance(path_or_data_dir, (pathlib.Path, str)):
        p = pathlib.Path(path_or_data_dir)
        if p.suffix:
            target_file = p
            if resolved_data_dir is None:
                resolved_data_dir = p.parent
        else:
            if resolved_data_dir is None:
                resolved_data_dir = p

    raw_bytes = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if target_file is not None:
        with contextlib.suppress(Exception):
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_bytes(raw_bytes)

    target_store = store or get_durable_store()
    if sync_cloud is None:
        effective_sync_cloud = not (
            bool(target_store.offline_sandbox) or is_offline_sandbox_or_test()
        )
    else:
        effective_sync_cloud = bool(sync_cloud)

    return target_store.save_state_file(
        filename=filename,
        data_bytes=raw_bytes,
        sync_cloud=effective_sync_cloud,
        data_dir=resolved_data_dir,
    )


def sync_to_durable_store(
    data_dir: pathlib.Path | None = None,
    force_cloud: bool = False,
) -> dict[str, Any]:
    return get_durable_store().sync_to_durable_store(data_dir=data_dir, force_cloud=force_cloud)


def sync_from_durable_store(
    data_dir: pathlib.Path | None = None,
    force_cloud: bool = False,
    only_missing: bool = False,
) -> dict[str, Any]:
    return get_durable_store().sync_from_durable_store(
        data_dir=data_dir,
        force_cloud=force_cloud,
        only_missing=only_missing,
    )


def simulate_cold_start_recovery(
    target_dir: pathlib.Path,
    store: DurableStateStore | None = None,
) -> dict[str, Any]:
    target_store = store or get_durable_store()
    return target_store.simulate_cold_start_recovery(target_dir=target_dir)


__all__ = [
    "DURABLE_IMAP_SUBJECT",
    "TRACKED_STATE_FILES",
    "DurableStateStore",
    "get_durable_store",
    "is_offline_sandbox_or_test",
    "load_durable_json",
    "load_state_file",
    "save_durable_json",
    "save_state_file",
    "simulate_cold_start_recovery",
    "sync_from_durable_store",
    "sync_to_durable_store",
]
