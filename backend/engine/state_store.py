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

from backend.engine.constants_and_time import DEFAULT_DEVICES

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
        self.setdefault("version", 1)
        self.setdefault("last_client_seq", 0)
        self.setdefault("last_client_ts_ms", 0)
        self._engine = _engine

    def __setitem__(self, key: str, value: Any) -> None:
        old_val = self.get(key)
        super().__setitem__(key, value)
        eng = getattr(self, "_engine", None)
        if eng is not None and not getattr(eng, "_applying_shared_state", False):
            if key == "state":
                if old_val != value or "updated_at" not in self:
                    prev_ts = float(self.get("updated_at") or 0.0)
                    super().__setitem__("updated_at", max(time.time(), prev_ts + 1e-6))
                    super().__setitem__("version", int(self.get("version") or 1) + 1)
            if key in ("state", "min_role", "name", "gpio", "type", "version", "last_client_seq", "last_client_ts_ms", "settings"):
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

    supports_cas: bool = True
    authoritative_cas: bool = True

    def read_cas(self) -> tuple[dict[str, Any] | None, int, str]:
        with self._lock:
            if self._state is None:
                return None, 0, ""
            rev = int(self._state.get("revision_seq", 0) or 0)
            return copy.deepcopy(self._state), rev, str(rev)

    def compare_and_swap(
        self,
        state: dict[str, Any],
        *,
        expected_revision: int,
        expected_token: str = "",
    ) -> tuple[bool, dict[str, Any]]:
        with self._lock:
            cur_rev = int(self._state.get("revision_seq", 0) or 0) if self._state is not None else 0
            if self._state is None:
                if int(expected_revision) != 0 or expected_token:
                    return False, {}
            else:
                if cur_rev != int(expected_revision) or (expected_token and expected_token != str(cur_rev)):
                    return False, copy.deepcopy(self._state)
            snap = copy.deepcopy(state)
            seq = int(expected_revision) + 1
            ts_ns = max(time.time_ns(), int(snap.get("revision_ts_ns", 0) or 0), self._last_ts_ns + 1)
            snap["revision_seq"] = seq
            snap["revision_ts_ns"] = ts_ns
            self._last_seq = max(self._last_seq, seq)
            self._last_ts_ns = max(self._last_ts_ns, ts_ns)
            self._state = copy.deepcopy(snap)
            return True, snap

    def save_state(self, state: dict[str, Any], *, preserve_revision: bool = False) -> dict[str, Any]:
        with self._lock:
            snap = copy.deepcopy(state)
            if preserve_revision and int(snap.get("revision_seq", 0)) > 0:
                seq = int(snap["revision_seq"])
                ts_ns = int(snap.get("revision_ts_ns") or time.time_ns())
            else:
                seq = max(int(snap.get("revision_seq", 0)), self._last_seq) + 1
                ts_ns = max(time.time_ns(), int(snap.get("revision_ts_ns", 0)), self._last_ts_ns + 1)
            snap["revision_seq"] = seq
            snap["revision_ts_ns"] = ts_ns
            self._last_seq = max(self._last_seq, seq)
            self._last_ts_ns = max(self._last_ts_ns, ts_ns)
            self._state = copy.deepcopy(snap)
            return snap

    def clear(self) -> None:
        with self._lock:
            self._state = None
            self._last_seq = 0
            self._last_ts_ns = 0


class StateConflictError(Exception):
    """Lỗi xung đột Compare-And-Swap khi có phiên bản mới hơn đã được ghi trước đó."""


import contextlib as _contextlib


@_contextlib.contextmanager
def _interprocess_file_lock(lock_path: pathlib.Path, timeout_sec: float = 5.0):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    deadline = time.monotonic() + timeout_sec
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for file lock: {lock_path}") from None
                time.sleep(0.005)
        yield
    finally:
        if acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)


class FileStateBackend:
    """Kho lưu trữ trạng thái chia sẻ qua tệp JSON cục bộ với khóa liên tiến trình và CAS."""

    is_remote: bool = False
    supports_cas: bool = True
    authoritative_cas: bool = True
    _GLOBAL_LOCK = threading.RLock()

    def __init__(self, file_path: pathlib.Path | None = None) -> None:
        if file_path is None:
            env_data_dir = os.environ.get("SMARTHOME_DATA_DIR", "").strip()
            if env_data_dir and not os.environ.get("VERCEL"):
                file_path = pathlib.Path(env_data_dir) / "shared_device_state.json"
            else:
                import hashlib

                wt_root = str(pathlib.Path(__file__).resolve().parent.parent.parent)
                wt_hash = hashlib.sha256(wt_root.encode("utf-8")).hexdigest()[:12]
                file_path = pathlib.Path(tempfile.gettempdir()) / f"smarthome_shared_device_state_{wt_hash}.json"
        self.file_path = file_path
        self._lock_path = self.file_path.with_suffix(self.file_path.suffix + ".lock")
        self._lock = threading.RLock()
        self._cached_state: dict[str, Any] | None = None
        self._cached_mtime_ns: int = -1
        self._cached_size: int = -1
        self._last_seq: int = 0
        self._last_ts_ns: int = 0

    def _read_cas_unlocked(self) -> tuple[dict[str, Any] | None, int, str]:
        import hashlib

        if not self.file_path.exists():
            self._cached_state = None
            return None, 0, ""
        try:
            raw_bytes = self.file_path.read_bytes()
            if not raw_bytes.strip():
                return None, 0, ""
            tok = hashlib.sha1(raw_bytes).hexdigest()
            data = json.loads(raw_bytes.decode("utf-8"))
            if isinstance(data, dict) and "devices" in data:
                rev = int(data.get("revision_seq", 0) or 0)
                self._cached_state = copy.deepcopy(data)
                self._last_seq = max(self._last_seq, rev)
                self._last_ts_ns = max(self._last_ts_ns, int(data.get("revision_ts_ns", 0) or 0))
                return copy.deepcopy(data), rev, tok
        except Exception:
            return None, 0, ""
        return None, 0, ""

    def _write_bytes_atomic_unlocked(self, payload_bytes: bytes) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.file_path.with_name(
            f".{self.file_path.name}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
        )
        for _ in range(5):
            try:
                tmp_path.write_bytes(payload_bytes)
                os.replace(tmp_path, self.file_path)
                st = self.file_path.stat()
                self._cached_mtime_ns = st.st_mtime_ns
                self._cached_size = st.st_size
                return
            except OSError:
                time.sleep(0.005)
            finally:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
        self.file_path.write_bytes(payload_bytes)

    def read_cas(self) -> tuple[dict[str, Any] | None, int, str]:
        with self._GLOBAL_LOCK, self._lock, _interprocess_file_lock(self._lock_path):
            return self._read_cas_unlocked()

    def load_state(self) -> dict[str, Any] | None:
        with self._GLOBAL_LOCK, self._lock, _interprocess_file_lock(self._lock_path):
            data, _rev, _tok = self._read_cas_unlocked()
            return data

    def compare_and_swap(
        self,
        state: dict[str, Any],
        *,
        expected_revision: int,
        expected_token: str = "",
    ) -> tuple[bool, dict[str, Any]]:
        with self._GLOBAL_LOCK, self._lock, _interprocess_file_lock(self._lock_path):
            cur_data, cur_rev, cur_tok = self._read_cas_unlocked()
            if cur_data is None:
                if int(expected_revision) != 0 or expected_token:
                    return False, {}
                cur_ts_ns = 0
            else:
                if cur_rev != int(expected_revision) or (expected_token and cur_tok != expected_token):
                    return False, copy.deepcopy(cur_data)
                cur_ts_ns = int(cur_data.get("revision_ts_ns", 0) or 0)
            snap = copy.deepcopy(state)
            seq = int(expected_revision) + 1
            ts_ns = max(
                time.time_ns(),
                int(snap.get("revision_ts_ns", 0) or 0),
                cur_ts_ns + 1,
                self._last_ts_ns + 1,
            )
            snap["revision_seq"] = seq
            snap["revision_ts_ns"] = ts_ns
            self._last_seq = max(self._last_seq, seq)
            self._last_ts_ns = max(self._last_ts_ns, ts_ns)
            self._cached_state = copy.deepcopy(snap)
            payload_bytes = (json.dumps(snap, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._write_bytes_atomic_unlocked(payload_bytes)
            return True, snap

    def save_state(self, state: dict[str, Any], *, preserve_revision: bool = False) -> dict[str, Any]:
        with self._GLOBAL_LOCK, self._lock, _interprocess_file_lock(self._lock_path):
            cur_data, cur_rev, _cur_tok = self._read_cas_unlocked()
            cur_ts_ns = int((cur_data or {}).get("revision_ts_ns", 0) or 0)
            snap = copy.deepcopy(state)
            if preserve_revision and int(snap.get("revision_seq", 0)) > 0:
                seq = int(snap["revision_seq"])
                ts_ns = int(snap.get("revision_ts_ns") or time.time_ns())
            else:
                seq = max(int(snap.get("revision_seq", 0)), cur_rev, self._last_seq) + 1
                ts_ns = max(
                    time.time_ns(),
                    int(snap.get("revision_ts_ns", 0)),
                    cur_ts_ns + 1,
                    self._last_ts_ns + 1,
                )
            snap["revision_seq"] = seq
            snap["revision_ts_ns"] = ts_ns
            self._last_seq = max(self._last_seq, seq)
            self._last_ts_ns = max(self._last_ts_ns, ts_ns)
            self._cached_state = copy.deepcopy(snap)

            payload_bytes = (json.dumps(snap, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._write_bytes_atomic_unlocked(payload_bytes)
            return snap

    def clear(self) -> None:
        with self._GLOBAL_LOCK, self._lock, _interprocess_file_lock(self._lock_path):
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
        api_base: str | None = None,
        timeout_sec: float = 8.0,
        fallback_file_path: pathlib.Path | None = None,
    ) -> None:
        self._token = token.strip().strip('"')
        self.prefix = prefix.rstrip("/") + "/"
        resolved_base = (
            api_base
            if api_base is not None
            else os.environ.get("SMARTHOME_BLOB_API_BASE", "https://blob.vercel-storage.com")
        )
        self.api_base = (resolved_base.strip() or "https://blob.vercel-storage.com").rstrip("/")
        self.timeout_sec = timeout_sec
        self._lock = threading.RLock()
        self._cached_pathname: str = ""
        self._cached_url: str = ""
        self._cached_state: dict[str, Any] | None = None
        self._known_blobs: list[dict[str, Any]] = []
        self._last_seq: int = 0
        self._last_ts_ns: int = 0
        self._blob_suspended_until: float = 0.0
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
        if self._blob_suspended_until > time.time():
            raise urllib.error.URLError("Vercel Blob suspended circuit breaker active")
        req_headers = dict(headers or {})
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, data=data, method=method, headers=req_headers)
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as exc:
                last_err = exc
                if exc.code in (401, 403):
                    self._blob_suspended_until = time.time() + 600.0
                    break
                if attempt + 1 < retries:
                    time.sleep(0.12 * (attempt + 1))
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

    def _select_newest_state(self, *candidates: dict[str, Any] | None) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        best_key = (-1, -1)
        for item in candidates:
            if not isinstance(item, dict) or "devices" not in item:
                continue
            key = (int(item.get("revision_seq") or 0), int(item.get("revision_ts_ns") or 0))
            if key > best_key:
                best_key = key
                best = item
        return copy.deepcopy(best) if best is not None else None

    def _load_durable_state(self) -> dict[str, Any] | None:
        try:
            from backend.durable_store import load_durable_json

            data = load_durable_json("shared_device_state.json", None)
            if isinstance(data, dict):
                by_prefix = data.get("by_prefix")
                if isinstance(by_prefix, dict):
                    scoped = by_prefix.get(self.prefix)
                    if isinstance(scoped, dict) and "devices" in scoped:
                        return scoped
                if "devices" in data and self.prefix == "smarthome_shared_state_v1/":
                    return data
        except Exception:
            pass
        return None

    def _save_durable_state(self, snap: dict[str, Any]) -> None:
        try:
            from backend.durable_store import is_offline_sandbox_or_test, load_durable_json, save_durable_json

            existing = load_durable_json("shared_device_state.json", {})
            if not isinstance(existing, dict):
                existing = {}
            by_prefix = existing.get("by_prefix")
            if not isinstance(by_prefix, dict):
                by_prefix = {}
            by_prefix[self.prefix] = copy.deepcopy(snap)
            payload = {"by_prefix": by_prefix}
            sync_cloud = not is_offline_sandbox_or_test()
            save_durable_json("shared_device_state.json", payload, sync_cloud=sync_cloud)
        except Exception:
            pass

    def _load_local_and_durable_best(self) -> dict[str, Any] | None:
        fb_state = None
        if self._fallback_backend is not None:
            try:
                fb_state = self._fallback_backend.load_state()
            except Exception:
                fb_state = None
        durable_state = self._load_durable_state()
        return self._select_newest_state(self._cached_state, fb_state, durable_state)

    def load_state(self) -> dict[str, Any] | None:
        with self._lock:
            try:
                blobs = self._list_blobs()
            except Exception as exc:
                logger.warning("Vercel Blob _list_blobs failed: %s; falling back to RAM cache / local file / durable store", exc)
                best = self._load_local_and_durable_best()
                if best is not None:
                    self._cached_state = copy.deepcopy(best)
                    self._last_seq = max(self._last_seq, int(best.get("revision_seq", 0)))
                    self._last_ts_ns = max(self._last_ts_ns, int(best.get("revision_ts_ns", 0)))
                return best

            self._known_blobs = blobs
            if not blobs:
                return self._load_local_and_durable_best()

            latest = blobs[-1]
            latest_pathname = str(latest.get("pathname") or "")
            latest_url = str(latest.get("url") or latest.get("downloadUrl") or "")
            sort_ts_ns, sort_seq, _ = _extract_blob_sort_key(latest)

            local_best = self._load_local_and_durable_best()
            if local_best is not None and int(local_best.get("revision_seq") or 0) > sort_seq:
                self._cached_state = copy.deepcopy(local_best)
                self._last_seq = max(self._last_seq, int(local_best.get("revision_seq", 0)))
                self._last_ts_ns = max(self._last_ts_ns, int(local_best.get("revision_ts_ns", 0)))
                return local_best

            self._last_ts_ns = max(self._last_ts_ns, sort_ts_ns)
            self._last_seq = max(self._last_seq, sort_seq)

            if latest_pathname and latest_pathname == self._cached_pathname and self._cached_state is not None:
                return copy.deepcopy(self._cached_state)

            if not latest_url:
                return self._load_local_and_durable_best()

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
                    best = self._select_newest_state(data, local_best)
                    if best is not None:
                        self._cached_state = copy.deepcopy(best)
                        self._last_seq = max(self._last_seq, int(best.get("revision_seq", 0)), sort_seq)
                        self._last_ts_ns = max(self._last_ts_ns, int(best.get("revision_ts_ns", 0)), sort_ts_ns)
                    return best if best is not None else copy.deepcopy(data)
            except Exception as exc:
                logger.warning("Vercel Blob read latest blob failed: %s", exc)

            return self._load_local_and_durable_best()

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
                    self._fallback_backend.save_state(snap, preserve_revision=True)
                except Exception as fb_exc:
                    logger.warning("Local fallback FileStateBackend.save_state failed: %s", fb_exc)

            # Always preserve snapshot in durable store (Upstash KV / Memory / IMAP) scoped by prefix
            self._save_durable_state(snap)

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
            try:
                from backend.durable_store import is_offline_sandbox_or_test, load_durable_json, save_durable_json

                existing = load_durable_json("shared_device_state.json", {})
                if isinstance(existing, dict) and isinstance(existing.get("by_prefix"), dict):
                    existing["by_prefix"].pop(self.prefix, None)
                    save_durable_json("shared_device_state.json", existing, sync_cloud=not is_offline_sandbox_or_test())
            except Exception:
                pass


class GitHubCasStateBackend:
    """Kho lưu trữ trạng thái chia sẻ qua GitHub Private Repo Contents API với Compare-And-Swap (CAS)."""

    is_remote: bool = True
    supports_cas: bool = True
    authoritative_cas: bool = True

    def __init__(
        self,
        repository: str,
        token: str,
        filename: str = "shared_device_state.json",
        api_base: str = "",
    ) -> None:
        from backend.auth.security_state import GitHubSecurityState

        self.repository = (repository or "").strip().strip('"').strip("'").strip()
        clean_token = (token or "").strip().strip('"').strip("'").strip()
        clean_base = (api_base or "").strip().strip('"').strip("'").strip()
        self.filename = (filename or "shared_device_state.json").strip()
        self._gh = GitHubSecurityState(
            repository=self.repository,
            token=clean_token,
            api_base=clean_base or None,
        )
        self._lock = threading.RLock()
        self._migration_attempted = False

    def read_cas(self) -> tuple[dict[str, Any] | None, int, str]:
        with self._lock:
            raw, sha, doc_rev = self._gh.read(self.filename)
            if (
                not sha
                and int(doc_rev or 0) == 0
                and not self._migration_attempted
                and bool(os.environ.get("VERCEL"))
                and not bool(os.environ.get("PYTEST_CURRENT_TEST"))
            ):
                self._migration_attempted = True
                try:
                    from backend.durable_store import load_durable_json

                    legacy = load_durable_json("shared_device_state.json", None)
                    seed_state: dict[str, Any] | None = None
                    if isinstance(legacy, dict):
                        by_prefix = legacy.get("by_prefix")
                        if isinstance(by_prefix, dict):
                            cand = by_prefix.get("smarthome_shared_state_v1/")
                            if isinstance(cand, dict) and isinstance(cand.get("devices"), dict):
                                seed_state = cand
                        if seed_state is None and isinstance(legacy.get("devices"), dict):
                            seed_state = legacy
                    if seed_state is not None:
                        seed_rev = max(0, int(seed_state.get("revision_seq", 0) or 0))
                        try:
                            self.compare_and_swap(
                                seed_state,
                                expected_revision=seed_rev,
                                expected_token="",
                            )
                        except Exception:
                            pass
                        raw, sha, doc_rev = self._gh.read(self.filename)
                except Exception:
                    pass
            if not raw or raw == b"{}":
                return None, int(doc_rev or 0), sha
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return None, int(doc_rev or 0), sha
            if not isinstance(data, dict) or "devices" not in data:
                return None, int(doc_rev or 0), sha
            rev = max(int(data.get("revision_seq", 0) or 0), int(doc_rev or 0))
            data["revision_seq"] = rev
            return data, rev, sha

    def load_state(self) -> dict[str, Any] | None:
        data, _rev, _sha = self.read_cas()
        return data

    def compare_and_swap(
        self,
        state: dict[str, Any],
        *,
        expected_revision: int,
        expected_token: str = "",
    ) -> tuple[bool, dict[str, Any]]:
        from backend.auth.security_state import StateConflict

        with self._lock:
            snap = copy.deepcopy(state)
            seq = int(expected_revision) + 1
            ts_ns = max(time.time_ns(), int(snap.get("revision_ts_ns", 0) or 0), 1)
            snap["revision_seq"] = seq
            snap["revision_ts_ns"] = ts_ns
            raw_bytes = json.dumps(snap, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            try:
                self._gh.compare_and_swap(
                    self.filename,
                    raw_bytes,
                    expected_token,
                    int(expected_revision),
                )
                return True, snap
            except StateConflict:
                fresh, _r, _s = self.read_cas()
                return False, fresh or {}

    def save_state(self, state: dict[str, Any], *, preserve_revision: bool = False) -> dict[str, Any]:
        import secrets as _secrets

        for attempt in range(10):
            cur, cur_rev, cur_sha = self.read_cas()
            snap = copy.deepcopy(state)
            if preserve_revision and cur is None and int(snap.get("revision_seq", 0)) > 0:
                target_rev = max(0, int(snap["revision_seq"]) - 1)
            else:
                target_rev = cur_rev
            ok, committed = self.compare_and_swap(
                snap,
                expected_revision=target_rev,
                expected_token=cur_sha,
            )
            if ok:
                return committed
            time.sleep(0.01 * (attempt + 1) + _secrets.randbelow(20) / 1000.0)
        raise StateConflictError("GitHub CAS save_state exceeded 10 retry attempts")

    def clear(self) -> None:
        from backend.auth.security_state import StateConflict

        for _ in range(3):
            try:
                _raw, sha, rev = self._gh.read(self.filename)
                if not sha:
                    return
                self._gh.compare_and_swap(self.filename, b"{}", sha, rev)
                return
            except StateConflict:
                continue
            except Exception:
                return


class SqliteStateBackend:
    """Single-source-of-truth device state backend backed by SQLite WAL ACID transactions."""

    is_remote: bool = False
    supports_cas: bool = True
    authoritative_cas: bool = True

    def __init__(self, db_path: pathlib.Path | None = None) -> None:
        self._explicit_db_path = pathlib.Path(db_path) if db_path is not None else None
        self._lock = threading.RLock()
        self._last_ts_ns: int = 0
        self._bootstrapped_key: str | None = None

    def _db_path(self) -> pathlib.Path:
        if self._explicit_db_path is not None:
            return self._explicit_db_path
        from backend.db_migrations import resolve_sqlite_db_path

        return resolve_sqlite_db_path()

    def _open_ready_conn(self) -> Any:
        from backend.database_sqlite import init_sqlite_database
        from backend.db_migrations import bootstrap_device_state_from_devices, open_wal_connection

        dbp = self._db_path()
        if not dbp.exists():
            self._bootstrapped_key = None
        target = init_sqlite_database(dbp)
        tkey = str(target)
        conn = open_wal_connection(target, readonly=False)
        if self._bootstrapped_key != tkey:
            from backend.auth.tier_permissions import min_tier_for_device
            from backend.db_migrations import role_for_tier

            canonical_ids = set(DEFAULT_DEVICES.keys())
            short_pins = {
                "main_door": "D1",
                "living_room_light": "D0",
                "bedroom_light": "D4",
                "garden_pump": "D6",
                "alarm_siren": "D8",
                "speaker_amp": "D7",
            }
            dev_rows = conn.execute("SELECT device_id, gpio_pin, min_tier_required, min_role FROM devices").fetchall()
            ds_ids = {str(r[0]) for r in conn.execute("SELECT device_id FROM device_state").fetchall()}
            meta_row = conn.execute("SELECT COUNT(*) FROM system_state_meta WHERE id = 1").fetchone()
            dev_ids = {str(r[0]) for r in dev_rows}
            drift = (
                dev_ids != canonical_ids
                or ds_ids != canonical_ids
                or int(meta_row[0]) == 0
                or any(
                    str(r[1] or "").split()[0].split("/")[0].strip() != short_pins.get(str(r[0]), "")
                    or int(r[2] or 0) != min_tier_for_device(str(r[0]))
                    or str(r[3] or "") != role_for_tier(min_tier_for_device(str(r[0])))
                    for r in dev_rows
                )
            )
            if drift:
                conn.execute("BEGIN IMMEDIATE;")
                try:
                    bootstrap_device_state_from_devices(conn, DEFAULT_DEVICES)
                    conn.execute("COMMIT;")
                except Exception:
                    conn.execute("ROLLBACK;")
                    raise
            self._bootstrapped_key = tkey
        return conn

    def _read_snapshot_in_conn(self, conn: Any) -> dict[str, Any] | None:
        meta = conn.execute(
            """
            SELECT revision_seq, revision_ts_ns, server_connected, pump_manual_override_off,
                   dht11_json, soil_moisture_json, sound_json, updated_at
            FROM system_state_meta WHERE id = 1
            """
        ).fetchone()
        dev_rows = conn.execute(
            """
            SELECT d.device_id, d.device_name, d.gpio_pin, d.room, d.device_type, d.min_role,
                   ds.state, ds.version, ds.updated_at, ds.last_client_id, ds.last_client_seq,
                   ds.last_client_ts_ms, ds.last_request_id, ds.last_requested_state,
                   ds.client_seqs_json, ds.extra_json
            FROM devices d
            LEFT JOIN device_state ds ON ds.device_id = d.device_id
            """
        ).fetchall()
        if not dev_rows or meta is None:
            return None
        devices_map: dict[str, Any] = {}
        for r in dev_rows:
            did = str(r["device_id"])
            if did not in DEFAULT_DEVICES:
                continue
            base = dict(DEFAULT_DEVICES[did])
            try:
                client_seqs = json.loads(str(r["client_seqs_json"] or "{}"))
            except Exception:
                client_seqs = {}
            try:
                extra = json.loads(str(r["extra_json"] or "{}"))
            except Exception:
                extra = {}
            entry: dict[str, Any] = {
                **base,
                **(extra if isinstance(extra, dict) else {}),
                "id": did,
                "name": str(r["device_name"] or base.get("name") or did),
                "gpio": str(r["gpio_pin"] or base.get("gpio") or "GPIO"),
                "room": str(r["room"] or base.get("room") or "home"),
                "type": str(r["device_type"] or base.get("type") or "switch"),
                "min_role": str(r["min_role"] or base.get("min_role") or "CHILD_GUEST"),
                "state": str(r["state"] if r["state"] is not None else base.get("state") or "OFF"),
                "version": int(r["version"] or 1),
                "updated_at": float(r["updated_at"] or 0.0),
                "last_client_id": str(r["last_client_id"] or ""),
                "last_client_seq": int(r["last_client_seq"] or 0),
                "last_client_ts_ms": int(r["last_client_ts_ms"] or 0),
                "last_request_id": str(r["last_request_id"] or ""),
                "last_requested_state": str(r["last_requested_state"] or ""),
                "client_seqs": client_seqs if isinstance(client_seqs, dict) else {},
            }
            devices_map[did] = entry
        out: dict[str, Any] = {
            "revision_seq": int(meta["revision_seq"] or 0),
            "revision_ts_ns": int(meta["revision_ts_ns"] or 0),
            "server_connected": bool(meta["server_connected"]),
            "pump_manual_override_off": bool(meta["pump_manual_override_off"]),
            "devices": devices_map,
        }
        try:
            dht = json.loads(str(meta["dht11_json"] or "{}"))
            if isinstance(dht, dict) and dht:
                out["dht11_telemetry"] = dht
        except Exception:
            pass
        try:
            soil = json.loads(str(meta["soil_moisture_json"] or "{}"))
            if isinstance(soil, dict) and soil:
                out["soil_moisture_telemetry"] = soil
        except Exception:
            pass
        try:
            snd = json.loads(str(meta["sound_json"] or "{}"))
            if isinstance(snd, dict) and snd:
                out["sound_telemetry"] = snd
        except Exception:
            pass
        return out

    def _write_snapshot_in_tx(self, conn: Any, snap: dict[str, Any]) -> None:
        import datetime as _dt

        now = time.time()
        tz = _dt.timezone(_dt.timedelta(hours=7))
        now_iso = _dt.datetime.now(tz).isoformat()
        dht_obj = snap.get("dht11_telemetry") or {}
        soil_obj = snap.get("soil_moisture_telemetry") or {}
        sound_obj = snap.get("sound_telemetry") or {}
        conn.execute(
            """
            INSERT INTO system_state_meta (
                id, revision_seq, revision_ts_ns, server_connected, pump_manual_override_off,
                dht_temp_c, dht_hum_pct, soil_moisture_pct, dht11_json, soil_moisture_json, sound_json, updated_at
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                revision_seq = excluded.revision_seq,
                revision_ts_ns = excluded.revision_ts_ns,
                server_connected = excluded.server_connected,
                pump_manual_override_off = excluded.pump_manual_override_off,
                dht_temp_c = excluded.dht_temp_c,
                dht_hum_pct = excluded.dht_hum_pct,
                soil_moisture_pct = excluded.soil_moisture_pct,
                dht11_json = excluded.dht11_json,
                soil_moisture_json = excluded.soil_moisture_json,
                sound_json = excluded.sound_json,
                updated_at = excluded.updated_at
            """,
            (
                int(snap.get("revision_seq") or 0),
                int(snap.get("revision_ts_ns") or 0),
                1 if snap.get("server_connected", True) else 0,
                1 if snap.get("pump_manual_override_off", False) else 0,
                dht_obj.get("temp_c") if isinstance(dht_obj, dict) else None,
                dht_obj.get("humidity_pct") if isinstance(dht_obj, dict) else None,
                soil_obj.get("soil_moisture_pct") if isinstance(soil_obj, dict) else None,
                json.dumps(dht_obj, ensure_ascii=False) if isinstance(dht_obj, dict) else "{}",
                json.dumps(soil_obj, ensure_ascii=False) if isinstance(soil_obj, dict) else "{}",
                json.dumps(sound_obj, ensure_ascii=False) if isinstance(sound_obj, dict) else "{}",
                now,
            ),
        )
        known_cols = {
            "id",
            "name",
            "gpio",
            "room",
            "type",
            "min_role",
            "state",
            "version",
            "updated_at",
            "last_client_id",
            "last_client_seq",
            "last_client_ts_ms",
            "last_request_id",
            "last_requested_state",
            "client_seqs",
        }
        devices_dict = snap.get("devices") or {}
        if isinstance(devices_dict, dict):
            if "fan" not in devices_dict and "ac" not in devices_dict:
                conn.execute("DELETE FROM device_state WHERE device_id IN ('fan', 'ac')")
                conn.execute("DELETE FROM devices WHERE device_id IN ('fan', 'ac')")
            for did, dinfo in devices_dict.items():
                if not isinstance(dinfo, dict) or did not in DEFAULT_DEVICES:
                    continue
                extra = {k: v for k, v in dinfo.items() if k not in known_cols}
                min_role = str(dinfo.get("min_role") or DEFAULT_DEVICES.get(did, {}).get("min_role") or "CHILD_GUEST")
                if min_role not in ("ADMIN", "MEMBER", "CHILD_GUEST"):
                    min_role = "CHILD_GUEST"
                min_tier = 1 if min_role == "ADMIN" else (2 if min_role == "MEMBER" else 3)
                state_str = str(dinfo.get("state") or "OFF")
                conn.execute(
                    """
                    INSERT INTO devices (
                        device_id, device_name, gpio_pin, state, min_tier_required,
                        offline_controllable, updated_at, min_role, room, device_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_id) DO UPDATE SET
                        device_name = excluded.device_name,
                        gpio_pin = excluded.gpio_pin,
                        state = excluded.state,
                        min_tier_required = excluded.min_tier_required,
                        offline_controllable = excluded.offline_controllable,
                        min_role = excluded.min_role,
                        device_type = excluded.device_type,
                        updated_at = excluded.updated_at
                    """,
                    (
                        str(did),
                        str(dinfo.get("name") or did),
                        str(dinfo.get("gpio") or "GPIO"),
                        state_str,
                        min_tier,
                        0 if did in ("main_door", "alarm_siren") else 1,
                        now_iso,
                        min_role,
                        str(dinfo.get("room") or "home"),
                        str(dinfo.get("type") or "switch"),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO device_state (
                        device_id, state, version, updated_at, last_client_id, last_client_seq,
                        last_client_ts_ms, last_request_id, last_requested_state, client_seqs_json, extra_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_id) DO UPDATE SET
                        state = excluded.state,
                        version = excluded.version,
                        updated_at = excluded.updated_at,
                        last_client_id = excluded.last_client_id,
                        last_client_seq = excluded.last_client_seq,
                        last_client_ts_ms = excluded.last_client_ts_ms,
                        last_request_id = excluded.last_request_id,
                        last_requested_state = excluded.last_requested_state,
                        client_seqs_json = excluded.client_seqs_json,
                        extra_json = excluded.extra_json
                    """,
                    (
                        str(did),
                        state_str,
                        int(dinfo.get("version") or 1),
                        float(dinfo.get("updated_at") or now),
                        str(dinfo.get("last_client_id") or ""),
                        int(dinfo.get("last_client_seq") or 0),
                        int(dinfo.get("last_client_ts_ms") or 0),
                        str(dinfo.get("last_request_id") or ""),
                        str(dinfo.get("last_requested_state") or ""),
                        json.dumps(dinfo.get("client_seqs") or {}, ensure_ascii=False),
                        json.dumps(extra, ensure_ascii=False),
                    ),
                )

    def read_cas(self) -> tuple[dict[str, Any] | None, int, str]:
        with self._lock:
            conn = self._open_ready_conn()
            try:
                snap = self._read_snapshot_in_conn(conn)
                if snap is None:
                    return None, 0, ""
                rev = int(snap.get("revision_seq") or 0)
                return snap, rev, str(rev)
            finally:
                conn.close()

    def load_state(self) -> dict[str, Any] | None:
        snap, _rev, _tok = self.read_cas()
        return snap

    def compare_and_swap(
        self,
        state: dict[str, Any],
        *,
        expected_revision: int,
        expected_token: str = "",
    ) -> tuple[bool, dict[str, Any]]:
        with self._lock:
            conn = self._open_ready_conn()
            try:
                conn.execute("BEGIN IMMEDIATE;")
                cur_row = conn.execute("SELECT revision_seq FROM system_state_meta WHERE id = 1").fetchone()
                cur_rev = int(cur_row["revision_seq"] or 0) if cur_row is not None else 0
                if cur_rev != int(expected_revision) or (expected_token and expected_token != str(cur_rev)):
                    fresh = self._read_snapshot_in_conn(conn)
                    conn.execute("ROLLBACK;")
                    return False, fresh or {}
                snap = copy.deepcopy(state)
                seq = int(expected_revision) + 1
                ts_ns = max(time.time_ns(), int(snap.get("revision_ts_ns", 0) or 0), self._last_ts_ns + 1)
                snap["revision_seq"] = seq
                snap["revision_ts_ns"] = ts_ns
                self._last_ts_ns = max(self._last_ts_ns, ts_ns)
                self._write_snapshot_in_tx(conn, snap)
                conn.execute("COMMIT;")
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise
            finally:
                conn.close()
        from backend.async_cloud_backup import schedule_github_backup

        schedule_github_backup("shared_device_state.json", snap)
        return True, snap

    def save_state(self, state: dict[str, Any], *, preserve_revision: bool = False) -> dict[str, Any]:
        with self._lock:
            conn = self._open_ready_conn()
            try:
                conn.execute("BEGIN IMMEDIATE;")
                cur_row = conn.execute("SELECT revision_seq, revision_ts_ns FROM system_state_meta WHERE id = 1").fetchone()
                cur_seq = int(cur_row["revision_seq"] or 0) if cur_row is not None else 0
                cur_ts_ns = int(cur_row["revision_ts_ns"] or 0) if cur_row is not None else 0
                snap = copy.deepcopy(state)
                if preserve_revision and int(snap.get("revision_seq", 0)) > 0:
                    seq = max(int(snap["revision_seq"]), cur_seq)
                    ts_ns = max(int(snap.get("revision_ts_ns") or 0), cur_ts_ns, time.time_ns())
                else:
                    seq = max(int(snap.get("revision_seq", 0) or 0), cur_seq) + 1
                    ts_ns = max(time.time_ns(), int(snap.get("revision_ts_ns", 0) or 0), cur_ts_ns + 1, self._last_ts_ns + 1)
                snap["revision_seq"] = seq
                snap["revision_ts_ns"] = ts_ns
                self._last_ts_ns = max(self._last_ts_ns, ts_ns)
                self._write_snapshot_in_tx(conn, snap)
                conn.execute("COMMIT;")
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise
            finally:
                conn.close()
        from backend.async_cloud_backup import schedule_github_backup

        schedule_github_backup("shared_device_state.json", snap)
        return snap

    def clear(self) -> None:
        self._bootstrapped_key = None
        with self._lock:
            conn = self._open_ready_conn()
            self._bootstrapped_key = None
            try:
                conn.execute("BEGIN IMMEDIATE;")
                conn.execute("DELETE FROM device_state;")
                conn.execute("DELETE FROM system_state_meta;")
                bootstrap_devices = build_default_shared_state_payload()
                self._write_snapshot_in_tx(conn, bootstrap_devices)
                conn.execute("COMMIT;")
                self._bootstrapped_key = str(self._db_path())
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise
            finally:
                conn.close()


_DEFAULT_BACKEND: StateBackend | None = None
_BACKEND_LOCK = threading.RLock()


def create_state_backend_from_env() -> StateBackend:
    """Chọn backend trạng thái: SQLite WAL (máy chủ cố định LENOVO), GitHub CAS, Vercel Blob hoặc File."""
    forced_mode = os.environ.get("SMARTHOME_STATE_BACKEND", "").strip().lower()
    blob_token = os.environ.get("BLOB_READ_WRITE_TOKEN", "").strip().strip('"').strip("'").strip()
    blob_prefix = os.environ.get("SMARTHOME_BLOB_PREFIX", "smarthome_shared_state_v1/").strip()

    sec_repo = os.environ.get("SMARTHOME_SECURITY_REPO", "").strip().strip('"').strip("'").strip()
    sec_token = os.environ.get("SMARTHOME_SECURITY_TOKEN", "").strip().strip('"').strip("'").strip()
    sec_api_base = os.environ.get("SMARTHOME_SECURITY_API_BASE", "").strip().strip('"').strip("'").strip()
    sec_file = os.environ.get("SMARTHOME_STATE_GITHUB_FILE", "shared_device_state.json").strip() or "shared_device_state.json"

    running_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules)
    force_blob = os.environ.get("SMARTHOME_FORCE_BLOB_STORE", "").strip() == "1"
    force_gh = os.environ.get("SMARTHOME_FORCE_GITHUB_CAS", "").strip() == "1"
    custom_path = os.environ.get("SMARTHOME_STATE_FILE", "").strip()

    if forced_mode == "sqlite":
        return SqliteStateBackend()
    if forced_mode == "memory":
        return InMemoryStateBackend()
    if forced_mode == "file":
        return FileStateBackend(pathlib.Path(custom_path) if custom_path else None)
    if forced_mode in ("github", "github_cas") and sec_repo and sec_token:
        return GitHubCasStateBackend(
            repository=sec_repo,
            token=sec_token,
            filename=sec_file,
            api_base=sec_api_base,
        )
    if forced_mode == "blob" and blob_token:
        return VercelBlobStateBackend(token=blob_token, prefix=blob_prefix)

    # On permanent LENOVO host (non-pytest, non-Vercel) default to local SQLite WAL unless CAS test overrides
    if not running_pytest and not os.environ.get("VERCEL") and not custom_path and not force_gh and not sec_api_base:
        return SqliteStateBackend()

    if sec_repo and sec_token and (not running_pytest or force_gh or bool(sec_api_base)):
        return GitHubCasStateBackend(
            repository=sec_repo,
            token=sec_token,
            filename=sec_file,
            api_base=sec_api_base,
        )
    if blob_token and (not running_pytest or force_blob):
        return VercelBlobStateBackend(token=blob_token, prefix=blob_prefix)

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
    """Tạo payload trạng thái mặc định chuẩn cho 6 thiết bị phần cứng."""
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
