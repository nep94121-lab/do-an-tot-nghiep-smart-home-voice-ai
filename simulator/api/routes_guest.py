"""API mời khách (tạo / thu hồi / kiểm tra / đổi lấy phiên) và trang điều khiển khách."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse

from simulator.auth.guest_invites import (
    INVITE_TTL_DEFAULT_SEC,
    create_invite,
    inspect_token,
    list_invites,
    redeem_token,
    revoke_invite,
)
from simulator.auth.session_store import resolve_request_session
from simulator.voice.qr_svg import invite_qr_svg, public_invite_payload

router = APIRouter()

_INVALID_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Mã mời không hợp lệ — Nhà thông minh</title>
  <link rel="stylesheet" href="/static/guest_control.css"/>
</head>
<body class="guest-only">
  <main class="guest-invalid">
    <h1>Liên kết khách không hợp lệ hoặc đã hết hạn</h1>
    <p>Hãy nhờ chủ nhà tạo mã QR hoặc liên kết mời mới. Trang này không mở được nếu thiếu mã còn hiệu lực.</p>
  </main>
</body>
</html>
"""


def _is_owner_session(session: Any) -> bool:
    if session is None:
        return False
    if not bool(getattr(session, "is_authenticated", False)):
        return False
    return int(getattr(session, "tier", 99) or 99) == 1 or str(getattr(session, "role", "")).upper() == "ADMIN"


def _attach_session_cookies(resp: JSONResponse, session_id: str, max_age: int) -> JSONResponse:
    resp.set_cookie("sh_session_token", session_id, path="/", httponly=True, samesite="lax", max_age=max_age)
    resp.set_cookie("session_token", session_id, path="/", httponly=False, samesite="lax", max_age=max_age)
    return resp


def _request_origin(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


@router.get("/guest", response_class=HTMLResponse)
@router.get("/guest/", response_class=HTMLResponse)
async def guest_page(request: Request) -> HTMLResponse:
    token = str(request.query_params.get("token") or request.query_params.get("invite") or "").strip()
    if not token:
        return HTMLResponse(_INVALID_HTML, status_code=403)
    checked = inspect_token(token)
    if not checked.get("valid"):
        return HTMLResponse(_INVALID_HTML, status_code=403)
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "static" / "guest_control.html"
    html = path.read_text(encoding="utf-8")
    return HTMLResponse(html, status_code=200)


@router.get("/api/guest/invite/validate")
async def api_guest_invite_validate(request: Request) -> JSONResponse:
    token = str(request.query_params.get("token") or request.query_params.get("invite") or "").strip()
    if not token:
        body = request.query_params
        token = str(body.get("t") or "").strip()
    checked = inspect_token(token)
    status = 200 if checked.get("valid") else 403
    public = {
        "ok": bool(checked.get("valid")),
        "valid": bool(checked.get("valid")),
        "reason": checked.get("reason"),
        "error": checked.get("error") or "",
        "tier": checked.get("tier"),
        "role": checked.get("role"),
        "expires_at": checked.get("expires_at"),
        "ttl_remaining_sec": checked.get("ttl_remaining_sec"),
        "invite_id": checked.get("invite_id"),
    }
    return JSONResponse(public, status_code=status)


@router.post("/api/guest/redeem")
async def api_guest_redeem(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    body = payload if isinstance(payload, dict) else {}
    token = str(body.get("token") or body.get("invite") or request.query_params.get("token") or "").strip()
    result = redeem_token(token)
    if not result.get("ok"):
        return JSONResponse(
            {
                "ok": False,
                "valid": False,
                "reason": result.get("reason") or "invalid",
                "error": result.get("error") or "Mã mời không hợp lệ hoặc đã hết hạn.",
            },
            status_code=403,
        )
    session = result["session"]
    ttl = max(30, int(result["expires_at"] - __import__("time").time()))
    resp = JSONResponse(
        {
            "ok": True,
            "valid": True,
            "invite_id": result["invite_id"],
            "tier": session.tier,
            "role": session.role,
            "display_name": session.display_name,
            "expires_at": session.expires_at,
            "session_token": session.session_id,
        }
    )
    return _attach_session_cookies(resp, session.session_id, ttl)


@router.post("/api/auth3/guest_invites")
@router.post("/api/guest/invites")
async def api_create_guest_invite(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    session = resolve_request_session(request, payload=payload)
    if not _is_owner_session(session):
        return JSONResponse({"ok": False, "error": "Chỉ chủ nhà (đã đăng nhập) mới tạo được mã mời khách."}, status_code=401)
    body = payload if isinstance(payload, dict) else {}
    try:
        invite = create_invite(
            owner_user_id=session.user_id,
            tier=body.get("tier", 3),
            ttl_sec=int(body.get("ttl_sec") or body.get("ttl") or INVITE_TTL_DEFAULT_SEC),
            host_origin=_request_origin(request),
        )
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    qr_svg = invite_qr_svg(invite["url"])
    public = public_invite_payload(invite, include_token=True)
    public["qr_svg"] = qr_svg
    public["ok"] = True
    return JSONResponse(public)


@router.get("/api/auth3/guest_invites")
@router.get("/api/guest/invites")
async def api_list_guest_invites(request: Request) -> JSONResponse:
    session = resolve_request_session(request)
    if not _is_owner_session(session):
        return JSONResponse({"ok": False, "error": "Chỉ chủ nhà (đã đăng nhập) mới xem được danh sách mã mời."}, status_code=401)
    items = []
    for raw in list_invites(include_expired=True)[:40]:
        row = public_invite_payload(raw, include_token=False)
        row["invite_id"] = raw.get("jti")
        row["redeem_count"] = raw.get("redeem_count") or 0
        items.append(row)
    return JSONResponse({"ok": True, "invites": items})


@router.post("/api/auth3/guest_invites/{invite_id}/revoke")
@router.post("/api/guest/invites/{invite_id}/revoke")
async def api_revoke_guest_invite(invite_id: str, request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    session = resolve_request_session(request, payload=payload)
    if not _is_owner_session(session):
        return JSONResponse({"ok": False, "error": "Chỉ chủ nhà (đã đăng nhập) mới thu hồi được mã mời."}, status_code=401)
    result = revoke_invite(invite_id)
    status = 200 if result.get("ok") else 404
    return JSONResponse(result, status_code=status)


@router.post("/api/auth3/guest_qr_current")
@router.get("/api/auth3/guest_qr_current")
async def api_guest_qr_current_compat(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Tương thích panel chủ nhà cũ: tạo (hoặc trả) mã QR khách cấp 2/3, không lộ URL tĩnh /guest."""
    session = resolve_request_session(request, payload=payload)
    if not _is_owner_session(session):
        return JSONResponse({"ok": False, "error": "Chỉ chủ nhà (đã đăng nhập) mới tạo được mã QR khách."}, status_code=401)
    body = payload if isinstance(payload, dict) else {}
    tier = body.get("tier") or request.query_params.get("tier") or 3
    ttl = body.get("ttl_sec") or request.query_params.get("ttl_sec") or INVITE_TTL_DEFAULT_SEC
    try:
        invite = create_invite(
            owner_user_id=session.user_id,
            tier=tier,
            ttl_sec=int(ttl),
            host_origin=_request_origin(request),
        )
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    qr_svg = invite_qr_svg(invite["url"])
    public = public_invite_payload(invite, include_token=True)
    public["qr_svg"] = qr_svg
    public["ok"] = True
    # Không trả public_guest_path = "/guest" (đường dẫn tĩnh đã bỏ).
    public["public_guest_path"] = invite["path"]
    return JSONResponse(public)
