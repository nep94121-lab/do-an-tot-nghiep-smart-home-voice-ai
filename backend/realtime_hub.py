"""Realtime Push Hub (SSE /api/events + WS state_snapshot fanout) & short-lived realtime tickets."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator

from fastapi import Request

from backend.auth.session_store import (
    UserSession,
    _get_session_hmac_key,
    get_session_store,
    session_is_current,
)


def mint_realtime_ticket(session: UserSession, ttl_sec: int = 60) -> str:
    """Mint a short-lived HMAC-signed ticket bound to an active session for SSE/WS upgrade."""
    if session is None or not getattr(session, "is_authenticated", False):
        raise ValueError("Cannot mint realtime ticket for unauthenticated session")
    now = int(time.time())
    exp = now + max(10, min(300, int(ttl_sec)))
    payload = {
        "sid": session.session_id,
        "uid": session.user_id,
        "tier": int(session.tier),
        "role": str(session.role),
        "iat": now,
        "exp": exp,
        "typ": "rt_ticket",
    }
    raw_b64 = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).decode("ascii").rstrip("=")
    sig = hmac.new(
        _get_session_hmac_key(),
        b"rt_ticket:" + raw_b64.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return f"{raw_b64}.{sig}"


def verify_realtime_ticket(ticket: str | None) -> UserSession | None:
    """Verify HMAC signature, expiry, and active SQLite session state for a realtime ticket."""
    raw = str(ticket or "").strip()
    if "." not in raw:
        return None
    try:
        raw_b64, sig = raw.rsplit(".", 1)
        expected_sig = hmac.new(
            _get_session_hmac_key(),
            b"rt_ticket:" + raw_b64.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected_sig):
            return None
        pad = "=" * ((4 - len(raw_b64) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(raw_b64 + pad).decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("typ") != "rt_ticket":
            return None
        if float(payload.get("exp") or 0) <= time.time():
            return None
        sid = str(payload.get("sid") or "").strip()
        if not sid:
            return None
        sess = get_session_store().get_session(sid)
        if not session_is_current(sess):
            return None
        return sess
    except Exception:
        return None


def build_snapshot_for_session(engine: Any, session: UserSession | None, *, sync: bool = False) -> dict[str, Any]:
    """Build RBAC-appropriate state snapshot without exposing owner secrets to lower tiers."""
    if session is not None and session_is_current(session):
        return engine.get_snapshot(session=session, sync=sync)
    return engine.get_public_device_snapshot(sync=sync)


def _format_sse_event(event_name: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False)
    return f"event: {event_name}\ndata: {body}\n\n"


@dataclass
class _Subscriber:
    sub_id: str
    session: UserSession | None
    tier: int
    user_id: str
    queue: asyncio.Queue[str]
    loop: asyncio.AbstractEventLoop


class RealtimePushHub:
    """In-memory pub/sub hub pushing SQLite-committed state snapshots immediately over SSE/WS."""

    def __init__(self, max_queue_size: int = 32) -> None:
        self._max_queue_size = max(8, int(max_queue_size))
        self._lock = threading.RLock()
        self._subscribers: dict[str, _Subscriber] = {}

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def register(self, session: UserSession | None, loop: asyncio.AbstractEventLoop | None = None) -> _Subscriber:
        target_loop = loop or asyncio.get_running_loop()
        is_auth = session is not None and session_is_current(session)
        sub = _Subscriber(
            sub_id=uuid.uuid4().hex,
            session=session if is_auth else None,
            tier=int(session.tier) if is_auth and session is not None else 99,
            user_id=str(session.user_id) if is_auth and session is not None else "",
            queue=asyncio.Queue(maxsize=self._max_queue_size),
            loop=target_loop,
        )
        with self._lock:
            self._subscribers[sub.sub_id] = sub
        return sub

    def unregister(self, sub_id: str) -> None:
        with self._lock:
            self._subscribers.pop(sub_id, None)

    @staticmethod
    def _enqueue_drop_oldest(q: asyncio.Queue[str], frame: str) -> None:
        if q.full():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            q.put_nowait(frame)
        except asyncio.QueueFull:
            pass

    def publish_snapshot(self, engine: Any, reason: str = "mutation") -> int:
        """Broadcast latest snapshot (from RAM/SQLite) to all active SSE subscribers."""
        with self._lock:
            subs = list(self._subscribers.values())
        if not subs:
            return 0

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        _PUBLIC_SSE_REASONS = frozenset({
            "initial",
            "rest_broadcast",
            "mutation",
            "device_updated",
            "device_already_in_state",
            "server_mode_changed",
        })
        cached_frames: dict[tuple[int, str, str], str] = {}
        pushed = 0
        for sub in subs:
            eff_sess = sub.session if (sub.session is not None and session_is_current(sub.session)) else None
            if eff_sess is not None:
                eff_tier = int(eff_sess.tier)
                safe_reason = reason if (eff_tier == 1 or reason in _PUBLIC_SSE_REASONS) else "state_sync"
                cache_key = (eff_tier, str(eff_sess.user_id), safe_reason)
            else:
                safe_reason = reason if reason in _PUBLIC_SSE_REASONS else "state_sync"
                cache_key = (99, "", safe_reason)
            frame = cached_frames.get(cache_key)
            if frame is None:
                snap = build_snapshot_for_session(engine, eff_sess, sync=False)
                envelope = {
                    "type": "state_snapshot",
                    "reason": safe_reason,
                    "ts_ms": int(time.time() * 1000),
                    "snapshot": snap,
                }
                frame = _format_sse_event("state_snapshot", envelope)
                cached_frames[cache_key] = frame
            try:
                if running_loop is sub.loop and not sub.loop.is_closed():
                    self._enqueue_drop_oldest(sub.queue, frame)
                elif not sub.loop.is_closed():
                    sub.loop.call_soon_threadsafe(self._enqueue_drop_oldest, sub.queue, frame)
                else:
                    self.unregister(sub.sub_id)
                    continue
                pushed += 1
            except RuntimeError:
                self.unregister(sub.sub_id)
        return pushed

    async def subscribe_sse(
        self,
        request: Request,
        session: UserSession | None,
        engine: Any,
        *,
        keepalive_sec: float = 15.0,
    ) -> AsyncIterator[str]:
        """Async SSE stream emitting an immediate snapshot then real-time push frames."""
        loop = asyncio.get_running_loop()
        sub = self.register(session, loop=loop)
        try:
            yield ": connected" + (" " * 2048) + "\nretry: 400\n\n"
            initial_snap = build_snapshot_for_session(engine, sub.session, sync=True)
            yield _format_sse_event(
                "state_snapshot",
                {
                    "type": "state_snapshot",
                    "reason": "initial",
                    "ts_ms": int(time.time() * 1000),
                    "snapshot": initial_snap,
                },
            )
            while True:
                if await request.is_disconnected():
                    break
                try:
                    frame = await asyncio.wait_for(sub.queue.get(), timeout=keepalive_sec)
                    yield frame
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break
                    yield ": keepalive\n\n"
        finally:
            self.unregister(sub.sub_id)


_REALTIME_HUB = RealtimePushHub()


def get_realtime_hub() -> RealtimePushHub:
    return _REALTIME_HUB
