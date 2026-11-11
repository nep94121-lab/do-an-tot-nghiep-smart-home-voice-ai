"""Tạo mã QR SVG cho liên kết mời khách (không phụ thuộc dịch vụ trả phí)."""

from __future__ import annotations

from typing import Any


def invite_qr_svg(data: str, *, scale: int = 6, border: int = 2) -> str:
    text = str(data or "").strip()
    if not text:
        raise ValueError("empty_qr_payload")
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage

        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=scale, border=border)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(image_factory=SvgPathImage)
        if hasattr(img, "to_string"):
            raw = img.to_string()
        else:
            import io

            buf = io.BytesIO()
            img.save(buf)
            raw = buf.getvalue()
        if isinstance(raw, bytes):
            svg = raw.decode("utf-8")
        else:
            svg = str(raw)
        if "<svg" not in svg:
            raise RuntimeError("qrcode produced no svg")
        if "xmlns=" not in svg:
            svg = svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
        return svg
    except Exception:
        return _fallback_qr_svg(text, scale=scale, border=border)


def _fallback_qr_svg(data: str, *, scale: int = 6, border: int = 2) -> str:
    """Bộ tạo QR tối giản (byte mode, ECC M) khi thư viện qrcode thiếu factory SVG."""
    matrix = _qr_matrix(data)
    n = len(matrix)
    dim = (n + border * 2) * scale
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dim} {dim}" width="{dim}" height="{dim}" role="img" aria-label="Mã QR khách">',
        f'<rect width="{dim}" height="{dim}" fill="#ffffff"/>',
    ]
    for y, row in enumerate(matrix):
        for x, bit in enumerate(row):
            if bit:
                px = (x + border) * scale
                py = (y + border) * scale
                parts.append(f'<rect x="{px}" y="{py}" width="{scale}" height="{scale}" fill="#111111"/>')
    parts.append("</svg>")
    return "".join(parts)


def _qr_matrix(data: str) -> list[list[int]]:
    try:
        import qrcode

        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0, box_size=1)
        qr.add_data(data)
        qr.make(fit=True)
        return [[1 if cell else 0 for cell in row] for row in qr.get_matrix()]
    except Exception as exc:  # pragma: no cover - chỉ khi thiếu qrcode
        raise RuntimeError("Cần gói qrcode để tạo mã QR khách") from exc


def public_invite_payload(invite: dict[str, Any], *, include_token: bool = False) -> dict[str, Any]:
    out = {
        "ok": bool(invite.get("ok", True)),
        "invite_id": invite.get("invite_id") or invite.get("jti"),
        "tier": invite.get("tier"),
        "role": invite.get("role"),
        "created_at": invite.get("created_at"),
        "expires_at": invite.get("expires_at"),
        "ttl_sec": invite.get("ttl_sec"),
        "revoked": bool(invite.get("revoked")),
    }
    if include_token and invite.get("token"):
        out["token"] = invite["token"]
        out["path"] = invite.get("path")
        out["url"] = invite.get("url")
    return out
