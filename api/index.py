"""Vercel Serverless Entrypoint acting as stateless HTTPS + SSE reverse proxy to permanent server."""

import os
import pathlib
import re
import sys
from typing import Any, Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_UPSTREAM_ORIGIN = "https://laptop-6i654f8c.tail3020d6.ts.net"
_HOP_BY_HOP_REQUEST = frozenset(
    {
        "host",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "content-length",
        "accept-encoding",
    }
)
_HOP_BY_HOP_RESPONSE = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "content-length",
        "content-encoding",
        "set-cookie",
    }
)


def _strip_cookie_domain(raw_cookie: str) -> str:
    """Remove Domain=... from Set-Cookie so cookies bind first-party on the proxy origin."""
    return re.sub(r";\s*domain=[^;]*", "", raw_cookie, flags=re.IGNORECASE).strip()


def create_vercel_proxy_app(
    upstream_origin: str = DEFAULT_UPSTREAM_ORIGIN,
    *,
    transport: Optional[object] = None,
):
    """Build a stateless FastAPI reverse proxy forwarding REST, cookies, and SSE streams."""
    from fastapi import FastAPI, Request, Response
    from fastapi.responses import JSONResponse, StreamingResponse
    import httpx

    base_url = (upstream_origin or DEFAULT_UPSTREAM_ORIGIN).strip().rstrip("/")
    proxy_app = FastAPI(title="Smart Home Vercel Edge Proxy", docs_url=None, redoc_url=None)

    def _build_client() -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "base_url": base_url,
            "timeout": httpx.Timeout(connect=5.0, read=60.0, write=15.0, pool=5.0),
            "follow_redirects": False,
        }
        if transport is not None:
            kwargs["transport"] = transport
        return httpx.AsyncClient(**kwargs)

    @proxy_app.api_route(
        "/{full_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        response_model=None,
    )
    async def _forward(full_path: str, request: Request) -> Response:
        rel_path = f"/{full_path}" if full_path else "/"
        if request.url.query:
            target = f"{rel_path}?{request.url.query}"
        else:
            target = rel_path

        fwd_headers: list[tuple[str, str]] = []
        for k, v in request.headers.raw:
            name = k.decode("latin-1").lower()
            if name in _HOP_BY_HOP_REQUEST:
                continue
            fwd_headers.append((k.decode("latin-1"), v.decode("latin-1")))
        fwd_headers.append(("Accept-Encoding", "identity"))
        incoming_host = str(request.headers.get("x-forwarded-host") or request.headers.get("host") or "").strip()
        if incoming_host:
            fwd_headers.append(("X-Forwarded-Host", incoming_host))
        fwd_headers.append(("X-Forwarded-Proto", "https"))

        body = await request.body()
        client = _build_client()
        req = client.build_request(
            method=request.method,
            url=target,
            headers=fwd_headers,
            content=body if body else None,
        )
        try:
            upstream_resp = await client.send(req, stream=True)
        except Exception as exc:
            await client.aclose()
            return JSONResponse(
                {
                    "ok": False,
                    "error": "Máy chủ thường trú tạm thời không phản hồi qua đường hầm HTTPS.",
                    "detail": type(exc).__name__,
                },
                status_code=502,
                headers={"Cache-Control": "no-store"},
            )

        out_headers: list[tuple[str, str]] = []
        for k, v in upstream_resp.headers.multi_items():
            low = k.lower()
            if low in _HOP_BY_HOP_RESPONSE:
                continue
            out_headers.append((k, v))

        set_cookies = [_strip_cookie_domain(c) for c in upstream_resp.headers.get_list("set-cookie")]
        content_type = str(upstream_resp.headers.get("content-type") or "").lower()
        is_stream = "text/event-stream" in content_type or rel_path == "/api/events"

        if is_stream:
            async def _stream_chunks():
                try:
                    async for chunk in upstream_resp.aiter_bytes():
                        if chunk:
                            yield chunk
                finally:
                    await upstream_resp.aclose()
                    await client.aclose()

            stream_resp = StreamingResponse(
                _stream_chunks(),
                status_code=upstream_resp.status_code,
                media_type=upstream_resp.headers.get("content-type") or "text/event-stream",
            )
            for k, v in out_headers:
                if k.lower() != "content-type":
                    stream_resp.headers.append(k, v)
            for sc in set_cookies:
                stream_resp.headers.append("set-cookie", sc)
            return stream_resp

        try:
            raw_content = await upstream_resp.aread()
        finally:
            await upstream_resp.aclose()
            await client.aclose()

        resp = Response(
            content=raw_content,
            status_code=upstream_resp.status_code,
        )
        for k, v in out_headers:
            resp.headers.append(k, v)
        for sc in set_cookies:
            resp.headers.append("set-cookie", sc)
        return resp

    return proxy_app


if (
    os.environ.get("VERCEL", "").strip() == "1"
    and os.environ.get("SMARTHOME_DISABLE_UPSTREAM_PROXY", "").strip() != "1"
):
    upstream = os.environ.get("SMARTHOME_UPSTREAM_ORIGIN", DEFAULT_UPSTREAM_ORIGIN).strip() or DEFAULT_UPSTREAM_ORIGIN
    app = create_vercel_proxy_app(upstream)
else:
    from simulator.server import app  # noqa: E402

__all__ = ["app", "create_vercel_proxy_app", "DEFAULT_UPSTREAM_ORIGIN"]
