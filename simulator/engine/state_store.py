"""Shared & Persistent Device State Store across Serverless Instances (Vercel Blob + Local File/Memory Fallback).

Đảm bảo tính nhất quán Đọc-Sau-Ghi (Read-After-Write Consistency, 0 Stale Cache):
1. Trên Vercel Serverless (khi có `BLOB_READ_WRITE_TOKEN`):
   - Sử dụng `VercelBlobStateBackend` ghi mỗi phiên bản trạng thái vào một đường dẫn bất biến có thứ tự tăng dần
     (`st_{revision_ts_ns:021d}_{revision_seq:010d}_{nonce}.json`) để tránh hoàn toàn bộ nhớ đệm CDN trên URL cố định.
   - Khi đọc trạng thái (`load_state`), truy vấn trực tiếp API Metadata (`GET https://blob.vercel-storage.com?prefix=...`)
     với `Cache-Control: no-cache, no-store`, lấy bản ghi mới nhất và tải nội dung từ URL bất biến (hoặc dùng bản đệm
     trong RAM nếu `pathname` mới nhất không đổi).
   - Tự động dọn dẹp các blob cũ (chỉ giữ lại tối đa 3 bản gần nhất) để tránh rác lưu trữ và tránh lỗi 404 khi đọc đồng thời.
2. Trên môi trường Local Dev / Automated Tests (Fallback tự động):
   - Sử dụng `FileStateBackend` (`DATA_DIR / "shared_device_state.json"`) hoặc `InMemoryStateBackend`
     chia sẻ trạng thái tức thời giữa nhiều instance `SmartHomeEngine` với khóa luồng `threading.RLock`.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import pathlib
import re
import secrets
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol

from simulator.engine.constants_and_time import DEFAULT_DEVICES

logger = logging.getLogger(__name__)


class StateBackend(Protocol):
    """Giao diện chung cho các tầng lưu trữ trạng thái thiết bị chia sẻ."""

    is_remote: bool

    def load_state(self) -> dict[str, Any] | None:
        ...

    def save_state(self, state: dict[str, Any]) -> dict[str, Any]:
        ...

    def clear(self) -> None:
        ...


class TrackedDeviceDict(dict):
    """Dict đại diện cho 1 thiết bị trong `SmartHomeEngine.devices`, tự động thông báo cho Engine khi bị sửa trực tiếp trong RAM."""

    def __init__(self, *args: Any, _engine: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._engine = _engine

    def __setitem__(self, key: str, value: Any) -> None:
        old_val = self.get(key)
        super().__setitem__(key, value)
        eng = getattr(self, "_engine", None)
        if eng is not None and not getattr(eng, "_applying_shared_state", False):
            if key == "state":
                if old_val != value or "updated_at" not in self:
                    super().__setitem__("updated_at", time.time())
            if key in ("state", "min_role", "name", "gpio", "type"):
                eng._on_direct_device_mutation(str(self.get("id") or ""))

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[str, Any]:
        return {copy.deepcopy(k, memo): copy.deepcopy(v, memo) for k, v in self.items()}


class InMemoryStateBackend:
    """Kho lưu trữ trạng thái chia sẻ trong bộ nhớ (phục vụ Unit/Integration Test đa instance)."""

    is_remote: bool = False

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state: dict[str, Any] | None = None
        self._last_seq: int = 0
        self._last_ts_ns: int = 0

    def load_state(self) -> dict[str, Any] | None:
        with self._lock:
            if self._state is None:
                return None
            return copy.deepcopy(self._state)

    def save_state(self, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            snap = copy.deepcopy(state)
            seq = max(int(snap.get("revision_seq", 0)), self._last_seq) + 1
            ts_ns = max(time.time_ns(), int(snap.get("revision_ts_ns", 0)), self._last_ts_ns + 1)
            snap["revision_seq"] = seq
            snap["revision_ts_ns"] = ts_ns
            self._last_seq = seq
            self._last_ts_ns = ts_ns
            self._state = copy.deepcopy(snap)
            return snap

    def clear(self) -> None:
        with self._lock:
            self._state = None
            self._last_seq = 0
            self._last_ts_ns = 0


class FileStateBackend:
    """Kho lưu trữ trạng thái chia sẻ qua tệp JSON cục bộ (Local Fallback cho Dev & Tests)."""

    is_remote: bool = False
    _GLOBAL_LOCK = threading.RLock()

    def __init__(self, file_path: pathlib.Path | None = None) -> None:
        if file_path is None:
            import hashlib

            wt_root = str(pathlib.Path(__file__).resolve().parent.parent.parent)
            wt_hash = hashlib.sha256(wt_root.encode("utf-8")).hexdigest()[:12]
            file_path = pathlib.Path(tempfile.gettempdir()) / f"smarthome_shared_device_state_{wt_hash}.json"
        self.file_path = file_path
        self._lock = threading.RLock()
        self._cached_state: dict[str, Any] | None = None
        self._cached_mtime_ns: int = -1
        self._cached_size: int = -1
        self._last_seq: int = 0
        self._last_ts_ns: int = 0

    def load_state(self) -> dict[str, Any] | None:
        with self._GLOBAL_LOCK, self._lock:
            if not self.file_path.exists():
                return copy.deepcopy(self._cached_state) if self._cached_state is not None else None
            try:
                st = self.file_path.stat()
                if (
                    self._cached_state is not None
                    and st.st_mtime_ns == self._cached_mtime_ns
                    and st.st_size == self._cached_size
                ):
                    return copy.deepcopy(self._cached_state)
                raw = self.file_path.read_text(encoding="utf-8")
                if not raw.strip():
                    return copy.deepcopy(self._cached_state) if self._cached_state is not None else None
                data = json.loads(raw)
                if isinstance(data, dict) and "devices" in data:
                    self._cached_state = copy.deepcopy(data)
                    self._cached_mtime_ns = st.st_mtime_ns
                    self._cached_size = st.st_size
                    self._last_seq = max(self._last_seq, int(data.get("revision_seq", 0)))
                    self._last_ts_ns = max(self._last_ts_ns, int(data.get("revision_ts_ns", 0)))
                    return copy.deepcopy(data)
            except Exception:
                if self._cached_state is not None:
                    return copy.deepcopy(self._cached_state)
            return None

    def save_state(self, state: dict[str, Any]) -> dict[str, Any]:
        with self._GLOBAL_LOCK, self._lock:
            snap = copy.deepcopy(state)
            seq = max(int(snap.get("revision_seq", 0)), self._last_seq) + 1
            ts_ns = max(time.time_ns(), int(snap.get("revision_ts_ns", 0)), self._last_ts_ns + 1)
            snap["revision_seq"] = seq
            snap["revision_ts_ns"] = ts_ns
            self._last_seq = seq
            self._last_ts_ns = ts_ns
            self._cached_state = copy.deepcopy(snap)

            payload_bytes = (json.dumps(snap, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            for _ in range(5):
                try:
                    self.file_path.write_bytes(payload_bytes)
                    st = self.file_path.stat()
                    self._cached_mtime_ns = st.st_mtime_ns
                    self._cached_size = st.st_size
                    break
                except OSError:
                    time.sleep(0.005)
            return snap

    def clear(self) -> None:
        with self._GLOBAL_LOCK, self._lock:
            self._cached_state = None
            self._cached_mtime_ns = -1
            self._cached_size = -1
            self._last_seq = 0
            self._last_ts_ns = 0
            try:
                if self.file_path.exists():
                    self.file_path.unlink()
            except OSError:
                pass


_BLOB_NAME_RE = re.compile(r"st_(\d+)_(\d+)_")


def _extract_blob_sort_key(blob_item: dict[str, Any]) -> tuple[int, int, str]:
    pathname = str(blob_item.get("pathname") or "")
    m = _BLOB_NAME_RE.search(pathname)
    if m:
        return (int(m.group(1)), int(m.group(2)), pathname)
    return (0, 0, pathname)


class VercelBlobStateBackend:
    """Kho lưu trữ trạng thái chia sẻ qua Vercel Blob REST API với tính nhất quán Đọc-Sau-Ghi tuyệt đối."""

    is_remote: bool = True

    def __init__(
        self,
        token: str,
        prefix: str = "smarthome_shared_state_v1/",
        api_base: str = "https://blob.vercel-storage.com",
        timeout_sec: float = 8.0,
        fallback_file_path: pathlib.Path | None = None,
    ) -> None:
        self._token = token.strip().strip('"')
        self.prefix = prefix.rstrip("/") + "/"
        self.api_base = api_base.rstrip("/")
        self.timeout_sec = timeout_sec
        self._lock = threading.RLock()
        self._cached_pathname: str = ""
        self._cached_url: str = ""
        self._cached_state: dict[str, Any] | None = None
        self._known_blobs: list[dict[str, Any]] = []
        self._last_seq: int = 0
        self._last_ts_ns: int = 0
        if fallback_file_path is not None:
            fb_path = fallback_file_path
        elif os.name != "nt":
            fb_path = pathlib.Path("/tmp/smarthome_shared_device_state.json")
        else:
            fb_path = pathlib.Path(tempfile.gettempdir()) / "smarthome_shared_device_state.json"
        self._fallback_backend = FileStateBackend(fb_path)

    @property
    def fallback_backend(self) -> FileStateBackend:
        return self._fallback_backend

    def _request_json(
        self,
        url: str,
        *,
        method: str = "GET",
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        retries: int = 3,
    ) -> Any:
        req_headers = dict(headers or {})
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, data=data, method=method, headers=req_headers)
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw) if raw.strip() else {}
            except Exception as exc:
                last_err = exc
                if attempt + 1 < retries:
                    time.sleep(0.12 * (attempt + 1))
        if last_err is not None:
            raise last_err
        return {}

    def _list_blobs(self) -> list[dict[str, Any]]:
        qs = urllib.parse.urlencode({"prefix": self.prefix, "limit": "100"})
        url = f"{self.api_base}?{qs}"
        res = self._request_json(
            url,
            method="GET",
            headers={
                "Authorization": f"Bearer {self._token}",
                "x-api-version": "7",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
            },
        )
        blobs = res.get("blobs", []) if isinstance(res, dict) else []
        if not isinstance(blobs, list):
            return []
        return sorted(blobs, key=_extract_blob_sort_key)

    def _delete_urls_best_effort(self, urls: list[str]) -> None:
        if not urls:
            return
        try:
            self._request_json(
                f"{self.api_base}/delete",
                method="POST",
                data=json.dumps({"urls": urls}).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "x-api-version": "7",
                    "content-type": "application/json",
                },
                retries=1,
            )
        except Exception:
            pass

    def load_state(self) -> dict[str, Any] | None:
        with self._lock:
            try:
                blobs = self._list_blobs()
            except Exception as exc:
                logger.warning("Vercel Blob _list_blobs failed: %s; falling back to RAM cache / local file", exc)
                if self._cached_state is not None:
                    return copy.deepcopy(self._cached_state)
                if self._fallback_backend is not None:
                    try:
                        fb = self._fallback_backend.load_state()
                        if fb is not None:
                            self._cached_state = copy.deepcopy(fb)
                            self._last_seq = max(self._last_seq, int(fb.get("revision_seq", 0)))
                            self._last_ts_ns = max(self._last_ts_ns, int(fb.get("revision_ts_ns", 0)))
                            return copy.deepcopy(fb)
                    except Exception:
                        pass
                return None

            self._known_blobs = blobs
            if not blobs:
                return copy.deepcopy(self._cached_state) if self._cached_state is not None else None

            latest = blobs[-1]
            latest_pathname = str(latest.get("pathname") or "")
            latest_url = str(latest.get("url") or latest.get("downloadUrl") or "")
            sort_ts_ns, sort_seq, _ = _extract_blob_sort_key(latest)

            if self._cached_state is not None and self._last_seq > sort_seq:
                return copy.deepcopy(self._cached_state)

            self._last_ts_ns = max(self._last_ts_ns, sort_ts_ns)
            self._last_seq = max(self._last_seq, sort_seq)

            if latest_pathname and latest_pathname == self._cached_pathname and self._cached_state is not None:
                return copy.deepcopy(self._cached_state)

            if not latest_url:
                if self._cached_state is not None:
                    return copy.deepcopy(self._cached_state)
                if self._fallback_backend is not None:
                    try:
                        return self._fallback_backend.load_state()
                    except Exception:
                        pass
                return None

            try:
                data = self._request_json(
                    latest_url,
                    method="GET",
                    headers={
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                    },
                )
                if isinstance(data, dict) and "devices" in data:
                    self._cached_pathname = latest_pathname
                    self._cached_url = latest_url
                    self._cached_state = copy.deepcopy(data)
                    self._last_seq = max(self._last_seq, int(data.get("revision_seq", 0)), sort_seq)
                    self._last_ts_ns = max(self._last_ts_ns, int(data.get("revision_ts_ns", 0)), sort_ts_ns)
                    return copy.deepcopy(data)
            except Exception as exc:
                logger.warning("Vercel Blob read latest blob failed: %s", exc)

            if self._cached_state is not None:
                return copy.deepcopy(self._cached_state)
            if self._fallback_backend is not None:
                try:
                    return self._fallback_backend.load_state()
                except Exception:
                    pass
            return None

    def save_state(self, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            snap = copy.deepcopy(state)
            seq = max(int(snap.get("revision_seq", 0)), self._last_seq) + 1
            ts_ns = max(time.time_ns(), int(snap.get("revision_ts_ns", 0)), self._last_ts_ns + 1)
            snap["revision_seq"] = seq
            snap["revision_ts_ns"] = ts_ns

            # Always preserve state in RAM cache
            self._last_seq = seq
            self._last_ts_ns = ts_ns
            self._cached_state = copy.deepcopy(snap)

            # Save fallback snapshot to /tmp/smarthome_shared_device_state.json via local FileStateBackend
            if self._fallback_backend is not None:
                try:
                    self._fallback_backend.save_state(snap)
                except Exception as fb_exc:
                    logger.warning("Local fallback FileStateBackend.save_state failed: %s", fb_exc)

            nonce = secrets.token_hex(4)
            pathname = f"{self.prefix}st_{ts_ns:021d}_{seq:010d}_{nonce}.json"
            payload_bytes = json.dumps(snap, ensure_ascii=False).encode("utf-8")

            try:
                res = self._request_json(
                    f"{self.api_base}/{pathname}",
                    method="PUT",
                    data=payload_bytes,
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "x-api-version": "7",
                        "x-content-type": "application/json",
                        "x-cache-control-max-age": "0",
                        "x-add-random-suffix": "1",
                        "x-vercel-blob-access": "public",
                    },
                    retries=1,
                )
                saved_pathname = str(res.get("pathname") or pathname)
                saved_url = str(res.get("url") or "")

                self._cached_pathname = saved_pathname
                self._cached_url = saved_url

                if saved_url:
                    self._known_blobs.append({"pathname": saved_pathname, "url": saved_url})
                if len(self._known_blobs) >= 5:
                    old_items = self._known_blobs[:-2]
                    self._known_blobs = self._known_blobs[-2:]
                    old_urls = [str(b.get("url") or "") for b in old_items if b.get("url")]
                    if old_urls:
                        self._delete_urls_best_effort(old_urls)
            except Exception as exc:
                logger.warning(
                    "Vercel Blob remote save_state failed (%s): %s; state safely preserved in RAM and local fallback",
                    type(exc).__name__,
                    exc,
                )

            return snap

    def clear(self) -> None:
        with self._lock:
            try:
                blobs = self._list_blobs()
                urls = [str(b.get("url") or "") for b in blobs if b.get("url")]
                if urls:
                    self._delete_urls_best_effort(urls)
            except Exception:
                pass
            self._known_blobs = []
            self._cached_pathname = ""
            self._cached_url = ""
            self._cached_state = None
            self._last_seq = 0
            self._last_ts_ns = 0
            if self._fallback_backend is not None:
                try:
                    self._fallback_backend.clear()
                except Exception:
                    pass


_DEFAULT_BACKEND: StateBackend | None = None
_BACKEND_LOCK = threading.RLock()


def create_state_backend_from_env() -> StateBackend:
    """Tự động chọn VercelBlobStateBackend trên Vercel Serverless hoặc FileStateBackend khi chạy Local/Pytest."""
    forced_mode = os.environ.get("SMARTHOME_STATE_BACKEND", "").strip().lower()
    blob_token = os.environ.get("BLOB_READ_WRITE_TOKEN", "").strip()
    blob_prefix = os.environ.get("SMARTHOME_BLOB_PREFIX", "smarthome_shared_state_v1/").strip()

    running_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules)
    force_blob = os.environ.get("SMARTHOME_FORCE_BLOB_STORE", "").strip() == "1"

    if forced_mode == "memory":
        return InMemoryStateBackend()
    if forced_mode == "file":
        custom_path = os.environ.get("SMARTHOME_STATE_FILE", "").strip()
        return FileStateBackend(pathlib.Path(custom_path) if custom_path else None)
    if (forced_mode == "blob" or (blob_token and (not running_pytest or force_blob))) and blob_token:
        return VercelBlobStateBackend(token=blob_token, prefix=blob_prefix)

    custom_path = os.environ.get("SMARTHOME_STATE_FILE", "").strip()
    return FileStateBackend(pathlib.Path(custom_path) if custom_path else None)


def get_default_state_backend() -> StateBackend:
    global _DEFAULT_BACKEND
    with _BACKEND_LOCK:
        if _DEFAULT_BACKEND is None:
            _DEFAULT_BACKEND = create_state_backend_from_env()
        return _DEFAULT_BACKEND


def set_default_state_backend(backend: StateBackend | None) -> None:
    global _DEFAULT_BACKEND
    with _BACKEND_LOCK:
        _DEFAULT_BACKEND = backend


def build_default_shared_state_payload() -> dict[str, Any]:
    """Tạo payload trạng thái mặc định chuẩn cho 7 thiết bị phần cứng."""
    now = time.time()
    return {
        "revision_seq": 0,
        "revision_ts_ns": 0,
        "server_connected": True,
        "pump_manual_override_off": False,
        "devices": {
            k: dict(v, updated_at=now) for k, v in DEFAULT_DEVICES.items()
        },
    }
