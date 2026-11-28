"""Live code-excerpt extractor pulling real 10-30 line snippets directly from repo source files.

Every excerpt used in Graduation Report v2 is read directly from the actual repository
source file so listings stay 100% faithful to the running code (zero fabricated code,
zero terminal/code screenshots).
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ExcerptSpec:
    key: str
    rel_path: str
    start_line: int  # 1-based inclusive
    end_line: int    # 1-based inclusive
    caption: str
    max_line_len: int = 160


EXCERPT_SPECS: dict[str, ExcerptSpec] = {
    "fw_bootstrap_pins": ExcerptSpec(
        key="fw_bootstrap_pins",
        rel_path="firmware/esp8266_smarthome/esp8266_smarthome.ino",
        start_line=1072,
        end_line=1098,
        caption="Khởi tạo an toàn chân boot-strap và ngoại vi trong hàm setup() của ESP8266",
    ),
    "fw_offline_door_lock": ExcerptSpec(
        key="fw_offline_door_lock",
        rel_path="firmware/esp8266_smarthome/offline_fsm.h",
        start_line=251,
        end_line=279,
        caption="Khóa cứng cấm mở cửa chính khi mất kết nối máy chủ trong OfflineFsm",
    ),
    "be_rbac_permissions": ExcerptSpec(
        key="be_rbac_permissions",
        rel_path="backend/auth/tier_permissions.py",
        start_line=10,
        end_line=35,
        caption="Bảng ngưỡng phân quyền 3 tầng cố định trên máy chủ (DEVICE_MIN_TIER)",
    ),
    "be_rbac_check_fn": ExcerptSpec(
        key="be_rbac_check_fn",
        rel_path="backend/auth/tier_permissions.py",
        start_line=38,
        end_line=58,
        caption="Hàm kiểm tra quyền điều khiển và lọc danh sách thiết bị theo tầng phiên",
    ),
    "be_fastapi_device": ExcerptSpec(
        key="be_fastapi_device",
        rel_path="backend/api/routes_devices.py",
        start_line=342,
        end_line=370,
        caption="Xử lý điều khiển thiết bị trên FastAPI và trả snapshot lọc theo đúng phiên",
    ),
    "be_voice_control": ExcerptSpec(
        key="be_voice_control",
        rel_path="backend/live/tool_dispatcher_mixin.py",
        start_line=888,
        end_line=912,
        caption="Chuẩn hóa thiết bị đích và kiểm tra RBAC khi trợ lý giọng nói gọi control_device",
    ),
    "be_custom_cmd_noreconfirm": ExcerptSpec(
        key="be_custom_cmd_noreconfirm",
        rel_path="backend/live/tool_dispatcher_mixin.py",
        start_line=1423,
        end_line=1448,
        caption="Tạo lệnh tùy chỉnh qua bước xác nhận 1 lần và đối khớp lệnh đã lưu để chạy ngay",
    ),
    "be_custom_cmd_run": ExcerptSpec(
        key="be_custom_cmd_run",
        rel_path="backend/live/tool_dispatcher_mixin.py",
        start_line=1467,
        end_line=1480,
        caption="Thực thi ngay lệnh tùy chỉnh đã lưu không hỏi xác nhận lại",
    ),
    "be_qr_totp": ExcerptSpec(
        key="be_qr_totp",
        rel_path="backend/auth/qr_totp_mixin.py",
        start_line=62,
        end_line=79,
        caption="Sinh mã QR động bằng chữ ký HMAC-SHA256 theo chu kỳ TOTP 10 giây",
    ),
}


def _wrap_line(line: str, max_len: int) -> str:
    clean = line.rstrip("\r\n").replace("\t", "  ")
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3] + "..."


def load_code_excerpt(key: str, repo_root: pathlib.Path = REPO_ROOT) -> tuple[str, str, int, list[str]]:
    """Return (caption, source_ref, start_line, lines) from the actual repository file."""
    spec = EXCERPT_SPECS[key]
    src_path = repo_root / spec.rel_path
    if not src_path.is_file():
        raise FileNotFoundError(f"Missing code excerpt source: {src_path}")
    all_lines = src_path.read_text(encoding="utf-8", errors="replace").splitlines()
    raw_slice = all_lines[spec.start_line - 1 : spec.end_line]
    if not (10 <= len(raw_slice) <= 30):
        raise ValueError(f"Excerpt {key!r} has {len(raw_slice)} lines; expected 10..30")
    wrapped = [_wrap_line(ln, spec.max_line_len) for ln in raw_slice]
    source_ref = f"{spec.rel_path}, dòng {spec.start_line}–{spec.end_line}"
    return spec.caption, source_ref, spec.start_line, wrapped


def verify_all_excerpts(repo_root: pathlib.Path = REPO_ROOT) -> dict[str, dict[str, object]]:
    """Verify every excerpt loads cleanly from real repo files and stays within 10..30 lines."""
    summary: dict[str, dict[str, object]] = {}
    for key in EXCERPT_SPECS:
        caption, source_ref, start_line, lines = load_code_excerpt(key, repo_root=repo_root)
        summary[key] = {
            "source_ref": source_ref,
            "start_line": start_line,
            "line_count": len(lines),
            "caption": caption,
        }
    return summary
