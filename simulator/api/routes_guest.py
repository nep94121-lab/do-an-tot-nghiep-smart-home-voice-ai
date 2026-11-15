"""API mời khách (tạo / thu hồi / kiểm tra / đổi lấy phiên) và trang điều khiển khách."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from simulator.auth.guest_invites import (
    create_invite,
    inspect_token,
    list_invites,
    redeem_token,
    revoke_invite,
)
from simulator.auth.session_store import (
    get_session_store,
    resolve_request_session,
    session_is_current,
)
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


def _attach_session_cookies(
    resp: JSONResponse,
    session_id: str,
    max_age: int,
    request: Request | None = None,
) -> JSONResponse:
    from simulator.api.routes_auth import set_dual_session_cookies

    return set_dual_session_cookies(resp, session_id, request, max_age=max_age)


def _request_origin(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def _resolve_bound_guest_session(request: Request) -> Any:
    """Resolve active guest session strictly from headers/cookies (never from invite query/body token)."""
    tok = ""
    auth_header = str(request.headers.get("authorization", "") or "")
    if auth_header.lower().startswith("bearer "):
        tok = auth_header[7:].strip()
    if not tok:
        tok = str(request.headers.get("x-session-token", "") or "").strip()
    if not tok and hasattr(request, "cookies"):
        tok = str(request.cookies.get("sh_session_token") or request.cookies.get("session_token") or "").strip()
    if not tok:
        return None
    sess = get_session_store().get_session(tok)
    if not session_is_current(sess):
        return None
    return sess


@router.get("/guest", response_class=HTMLResponse)
@router.get("/guest/", response_class=HTMLResponse)
@router.get("/guest_enroll", response_class=HTMLResponse)
@router.get("/guest-qr", response_class=HTMLResponse)
async def guest_page(request: Request) -> Response:
    token = str(request.query_params.get("token") or request.query_params.get("invite") or "").strip()
    if not token:
        return HTMLResponse(_INVALID_HTML, status_code=403, headers={"Cache-Control": "no-store"})
    req_sess = _resolve_bound_guest_session(request)
    checked = inspect_token(token, existing_session=req_sess)
    if not checked.get("valid"):
        if checked.get("reason") == "used":
            return RedirectResponse(url="/qr_expired?reason=used", status_code=302, headers={"Cache-Control": "no-store"})
        return HTMLResponse(_INVALID_HTML, status_code=403, headers={"Cache-Control": "no-store"})
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "static" / "guest_control.html"
    html = path.read_text(encoding="utf-8")
    return HTMLResponse(html, status_code=200, headers={"Cache-Control": "no-store"})


@router.get("/api/guest/invite/validate")
async def api_guest_invite_validate(request: Request) -> JSONResponse:
    token = str(request.query_params.get("token") or request.query_params.get("invite") or "").strip()
    if not token:
        body = request.query_params
        token = str(body.get("t") or "").strip()
    req_sess = _resolve_bound_guest_session(request)
    checked = inspect_token(token, existing_session=req_sess)
    status = 200 if checked.get("valid") else 403
    public = {
        "ok": bool(checked.get("valid")),
        "valid": bool(checked.get("valid")),
        "reason": checked.get("reason"),
        "error": checked.get("error") or "",
        "tier": checked.get("tier"),
        "role": checked.get("role"),
        "duration_code": checked.get("duration_code") or "",
        "duration_label": checked.get("duration_label") or "",
        "duration_seconds": checked.get("duration_seconds"),
        "guest_name": checked.get("guest_name") or "",
        "expires_at": checked.get("expires_at"),
        "ttl_remaining_sec": checked.get("ttl_remaining_sec"),
        "invite_id": checked.get("invite_id"),
    }
    return JSONResponse(public, status_code=status, headers={"Cache-Control": "no-store"})


@router.post("/api/guest/redeem")
async def api_guest_redeem(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    body = payload if isinstance(payload, dict) else {}
    token = str(body.get("token") or body.get("invite") or request.query_params.get("token") or "").strip()
    req_sess = _resolve_bound_guest_session(request)
    result = redeem_token(token, existing_session=req_sess)
    if not result.get("ok"):
        reason = result.get("reason") or "invalid"
        err_body: dict[str, Any] = {
            "ok": False,
            "valid": False,
            "reason": reason,
            "error": result.get("error") or "Mã mời không hợp lệ hoặc đã hết hạn.",
        }
        if reason == "used":
            err_body["redirect"] = "/qr_expired?reason=used"
        return JSONResponse(err_body, status_code=403, headers={"Cache-Control": "no-store"})
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
            "guest_name": result.get("guest_name") or "",
            "duration_code": result.get("duration_code") or "",
            "duration_label": result.get("duration_label") or "",
            "duration_seconds": result.get("duration_seconds"),
            "expires_at": session.expires_at,
            "session_token": session.session_id,
        },
        headers={"Cache-Control": "no-store"},
    )
    return _attach_session_cookies(resp, session.session_id, ttl, request)


def _create_invite_with_owner_pin(
    request: Request,
    payload: dict[str, Any],
    *,
    unauth_error: str,
    include_public_guest_path: bool = False,
) -> JSONResponse:
    """Shared PIN check + invite generation for Owner dashboard and compat endpoints."""
    session = resolve_request_session(request, payload=payload)
    if not _is_owner_session(session):
        return JSONResponse({"ok": False, "error": unauth_error}, status_code=401)
    body = payload if isinstance(payload, dict) else {}
    from simulator.auth.owner_pin import pin_status, setup_or_replace_pin, verify_pin

    status = pin_status()
    pin_val = body.get("pin")
    pin_confirm = body.get("pin_confirm")
    if not status.get("pin_set"):
        if pin_confirm is None or str(pin_confirm).strip() == "":
            return JSONResponse(
                {
                    "ok": False,
                    "needs_pin_setup": True,
                    "status_code": 400,
                    "error": "Hãy đặt mã PIN 4 số lần đầu (nhập hai lần: pin và pin_confirm) rồi tạo mã.",
                },
                status_code=400,
            )
        setup = setup_or_replace_pin(str(pin_val or ""), str(pin_confirm))
        if not setup.get("ok"):
            setup["needs_pin_setup"] = int(setup.get("status_code") or 400) != 409
            return JSONResponse(setup, status_code=int(setup.get("status_code") or 400))
    else:
        checked = verify_pin(str(pin_val or ""))
        if not checked.get("ok"):
            return JSONResponse(checked, status_code=int(checked.get("status_code") or 403))

    tier = body.get("tier") if body.get("tier") is not None else request.query_params.get("tier", 3)
    raw_dur = (
        body.get("duration_code")
        or body.get("duration")
        or request.query_params.get("duration_code")
        or request.query_params.get("duration")
    )
    raw_ttl = body.get("ttl_sec") or body.get("ttl") or request.query_params.get("ttl_sec")
    ttl_arg: int | None = None
    if raw_ttl is not None and str(raw_ttl).strip() != "":
        try:
            ttl_arg = int(raw_ttl)
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "error": "ttl_sec không hợp lệ."}, status_code=400)
    guest_name = str(body.get("guest_name") or "")
    try:
        invite = create_invite(
            owner_user_id=session.user_id,
            tier=tier,
            ttl_sec=ttl_arg,
            duration_code=str(raw_dur).strip() if raw_dur is not None and str(raw_dur).strip() else None,
            guest_name=guest_name,
            host_origin=_request_origin(request),
        )
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    qr_svg = invite_qr_svg(invite["url"])
    public = public_invite_payload(invite, include_token=True)
    public["qr_svg"] = qr_svg
    public["ok"] = True
    if include_public_guest_path:
        public["public_guest_path"] = invite["path"]
    return JSONResponse(public)


@router.post("/api/auth3/guest_invites")
@router.post("/api/guest/invites")
async def api_create_guest_invite(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    return _create_invite_with_owner_pin(
        request,
        payload,
        unauth_error="Chỉ chủ nhà (đã đăng nhập) mới tạo được mã mời khách.",
        include_public_guest_path=False,
    )


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
    if request.method == "GET":
        return JSONResponse({"ok": False, "error": "Hãy dùng POST với mã PIN."}, status_code=405)
    return _create_invite_with_owner_pin(
        request,
        payload,
        unauth_error="Chỉ chủ nhà (đã đăng nhập) mới tạo được mã QR khách.",
        include_public_guest_path=True,
    )
