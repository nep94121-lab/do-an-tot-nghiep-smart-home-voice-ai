"""Bộ quản lý Thiết bị 3D, Phân quyền (RBAC), 2 Bể (Bể Hẹn Giờ & Bể Luật Động),
Đổi từ, Đổi lệnh, Quan hệ IF sát nghĩa (1 chiều vs 2 chiều) và Reset có Xác nhận 2 bước.

Nguyên tắc cốt lõi theo yêu cầu của Sếp:
1. Hiểu sát nghĩa Quan hệ IF (Không tự suy diễn ngược lại):
   - Khi nói "Nếu mở cửa chính thì mở điều hòa" -> CHỈ lưu 1 chiều: `main_door == OPEN => ac = ON`.
   - Khi đóng cửa chính (`main_door == CLOSED`), điều hòa GIỮ NGUYÊN KHÔNG TẮT (trừ khi người dùng dặn rõ cả vế ngược lại).
2. Khi nói "Vừng ơi mở ra" (khẩu lệnh đã đổi của mở cửa chính) -> mở cửa chính -> tự động kích hoạt luật "Khi cửa mở thì mở điều hòa".
3. Quản lý 2 Bể rõ ràng:
   - Bể 1 (Bể Hẹn Giờ - `timer_pool`): Chứa tất cả các lịch hẹn giờ đang đếm ngược (hỗ trợ hỏi có bao nhiêu hẹn giờ và chi tiết từng cái).
   - Bể 2 (Bể Luật & Ngôn Ngữ - `rule_pool`): Chứa các từ đã đổi, lệnh đã đổi và luật IF đang hoạt động.
4. Reset hệ thống có hỏi xác nhận:
   - Khi người dùng bảo "Reset", hệ thống chuyển sang trạng thái `pending_reset_confirmation = True` và hỏi lại:
     "Bạn muốn reset tất cả đúng không?"
   - Chỉ khi người dùng xác nhận ("Đúng", "Có", "Đồng ý"), hệ thống mới xóa sạch cả 2 bể về 0, trả về ngôn ngữ gốc nguyên bản (mở cửa chỉ mở cửa, bật đèn chỉ bật đèn).
"""

from __future__ import annotations

import asyncio
import datetime
import json
import pathlib
import re
import time
from typing import Any, Callable, Coroutine

DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

FACTORY_FILE = DATA_DIR / "factory_default_rules.json"
OVERLAY_FILE = DATA_DIR / "custom_rules_overlay.json"

VN_TZ = datetime.timezone(datetime.timedelta(hours=7), name="ICT")


def get_vn_now() -> datetime.datetime:
    return datetime.datetime.now(VN_TZ)


def format_vn_time_ampm(dt: datetime.datetime | None = None) -> str:
    dt = dt or get_vn_now()
    return dt.strftime("%I:%M:%S %p (GMT+7)")


DEFAULT_DEVICES: dict[str, dict[str, Any]] = {
    "main_door": {
        "id": "main_door",
        "name": "Cửa chính",
        "gpio": "GPIO4 (Servo/Lock)",
        "type": "door",
        "state": "CLOSED",
        "min_role": "CHILD_GUEST",
        "updated_at": 0.0,
    },
    "living_room_light": {
        "id": "living_room_light",
        "name": "Đèn phòng khách",
        "gpio": "GPIO5 (Relay 1)",
        "type": "light",
        "state": "OFF",
        "min_role": "CHILD_GUEST",
        "updated_at": 0.0,
    },
    "bedroom_light": {
        "id": "bedroom_light",
        "name": "Đèn phòng ngủ",
        "gpio": "GPIO6 (Relay 2)",
        "type": "light",
        "state": "OFF",
        "min_role": "CHILD_GUEST",
        "updated_at": 0.0,
    },
    "fan": {
        "id": "fan",
        "name": "Quạt trần",
        "gpio": "GPIO7 (Relay 3)",
        "type": "fan",
        "state": "OFF",
        "min_role": "CHILD_GUEST",
        "updated_at": 0.0,
    },
    "ac": {
        "id": "ac",
        "name": "Điều hòa",
        "gpio": "GPIO15 (IR/Relay 4)",
        "type": "ac",
        "state": "OFF",
        "min_role": "CHILD_GUEST",
        "updated_at": 0.0,
    },
    "alarm_siren": {
        "id": "alarm_siren",
        "name": "Còi báo động",
        "gpio": "GPIO16 (Buzzer/Siren)",
        "type": "siren",
        "state": "OFF",
        "min_role": "CHILD_GUEST",
        "updated_at": 0.0,
    },
}

ROLE_LEVELS: dict[str, int] = {
    "UNKNOWN": 0,
    "CHILD_GUEST": 1,
    "MEMBER": 2,
    "ADMIN": 3,
}

ROLE_NAMES: dict[str, str] = {
    "UNKNOWN": "Đã hủy quyền / Người lạ (Chặn toàn bộ)",
    "CHILD_GUEST": "Tầng 3 — Khách (Chỉ gọi lệnh đóng/mở cố định)",
    "MEMBER": "Tầng 2 — Thành viên gia đình (Có bể lệnh & hẹn giờ riêng, cấp/hủy Tầng 3)",
    "ADMIN": "Tầng 1 — Admin tối cao: Nguyễn Tuấn Anh (Toàn quyền ưu tiên số 1)",
}

DEFAULT_USERS: dict[str, dict[str, Any]] = {
    "tuan_anh": {
        "id": "tuan_anh",
        "name": "Nguyễn Tuấn Anh",
        "tier": 1,
        "role": "ADMIN",
        "granted_by": "SYSTEM_ROOT",
        "granted_by_name": "Hệ thống gốc",
        "granted_by_tier": 1,
        "active": True,
    },
    "thanh_vien_a": {
        "id": "thanh_vien_a",
        "name": "Thành viên A",
        "tier": 2,
        "role": "MEMBER",
        "granted_by": "tuan_anh",
        "granted_by_name": "Nguyễn Tuấn Anh (Tầng 1)",
        "granted_by_tier": 1,
        "active": True,
    },
    "thanh_vien_b": {
        "id": "thanh_vien_b",
        "name": "Thành viên B",
        "tier": 2,
        "role": "MEMBER",
        "granted_by": "tuan_anh",
        "granted_by_name": "Nguyễn Tuấn Anh (Tầng 1)",
        "granted_by_tier": 1,
        "active": True,
    },
    "khach_c": {
        "id": "khach_c",
        "name": "Khách C",
        "tier": 3,
        "role": "CHILD_GUEST",
        "granted_by": "tuan_anh",
        "granted_by_name": "Nguyễn Tuấn Anh (Tầng 1)",
        "granted_by_tier": 1,
        "active": True,
    },
    "khach_d": {
        "id": "khach_d",
        "name": "Khách D",
        "tier": 3,
        "role": "CHILD_GUEST",
        "granted_by": "thanh_vien_a",
        "granted_by_name": "Thành viên A (Tầng 2)",
        "granted_by_tier": 2,
        "active": True,
    },
}

ACTION_TO_STATE: dict[str, str] = {
    "open": "OPEN",
    "close": "CLOSED",
    "turn_on": "ON",
    "turn_off": "OFF",
}

ACTION_VI_LABEL: dict[str, str] = {
    "open": "Mở",
    "close": "Đóng",
    "turn_on": "Bật",
    "turn_off": "Tắt",
}

STATE_TO_OPPOSITE: dict[str, str] = {
    "OPEN": "CLOSED",
    "CLOSED": "OPEN",
    "ON": "OFF",
    "OFF": "ON",
}


def _format_clock_12h(hour_24: int, minute: int, second: int = 0) -> str:
    period = "AM" if hour_24 < 12 else "PM"
    h12 = hour_24 % 12
    if h12 == 0:
        h12 = 12
    if second > 0:
        return f"{h12}:{minute:02d}:{second:02d} {period}"
    return f"{h12}:{minute:02d} {period}"


def _extract_vn_date(
    time_str: str, date_str: str, now_vn: datetime.datetime
) -> tuple[str, datetime.date | None, str]:
    """Tách thông tin ngày/tháng (nếu người dùng có nói rõ) ra khỏi chuỗi giờ.
    Trả về: (cleaned_time_str, target_date_or_None, date_label_vi)
    """
    combined = f"{date_str.strip()} {time_str.strip()}".strip()
    cleaned_time = time_str

    # 1. Kiểm tra từ khóa tương đối: hôm nay, ngày mai, ngày kia/ngày mốt
    if re.search(r"\b(ngày\s+mai|sáng\s+mai|chiều\s+mai|tối\s+mai|đêm\s+mai|\bmai\b)\b", combined, flags=re.I):
        cleaned_time = re.sub(r"\b(ngày\s+mai|mai)\b", " ", cleaned_time, flags=re.I)
        return cleaned_time, now_vn.date() + datetime.timedelta(days=1), "ngày mai"

    if re.search(r"\b(ngày\s+kia|ngày\s+mốt)\b", combined, flags=re.I):
        cleaned_time = re.sub(r"\b(ngày\s+kia|ngày\s+mốt)\b", " ", cleaned_time, flags=re.I)
        return cleaned_time, now_vn.date() + datetime.timedelta(days=2), "ngày kia"

    if re.search(r"\bhôm\s+nay\b", combined, flags=re.I):
        cleaned_time = re.sub(r"\bhôm\s+nay\b", " ", cleaned_time, flags=re.I)
        return cleaned_time, now_vn.date(), "hôm nay"

    day: int | None = None
    month: int | None = None
    year: int | None = None
    has_explicit_year = False

    # 2. Định dạng: "ngày 25 tháng 10 (năm 2026)"
    m_vn = re.search(
        r"(?:ngày\s*)?(\d{1,2})\s*tháng\s*(\d{1,2})(?:\s*năm\s*(\d{4}))?",
        combined,
        flags=re.I,
    )
    if m_vn:
        day = int(m_vn.group(1))
        month = int(m_vn.group(2))
        if m_vn.group(3):
            year = int(m_vn.group(3))
            has_explicit_year = True
        cleaned_time = re.sub(
            r"(?:ngày\s*)?\d{1,2}\s*tháng\s*\d{1,2}(?:\s*năm\s*\d{4})?",
            " ",
            cleaned_time,
            flags=re.I,
        )
    else:
        # 3. Định dạng ISO: YYYY-MM-DD
        m_iso = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", combined)
        if m_iso:
            year = int(m_iso.group(1))
            month = int(m_iso.group(2))
            day = int(m_iso.group(3))
            has_explicit_year = True
            cleaned_time = re.sub(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", " ", cleaned_time)
        else:
            # 4. Định dạng: "(ngày) DD/MM(/YYYY)" hoặc "DD-MM(-YYYY)"
            m_slash = re.search(
                r"(?:ngày\s*)?\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b",
                combined,
                flags=re.I,
            )
            if m_slash:
                day = int(m_slash.group(1))
                month = int(m_slash.group(2))
                if m_slash.group(3):
                    y_raw = int(m_slash.group(3))
                    year = 2000 + y_raw if y_raw < 100 else y_raw
                    has_explicit_year = True
                cleaned_time = re.sub(
                    r"(?:ngày\s*)?\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
                    " ",
                    cleaned_time,
                    flags=re.I,
                )

    if day is not None and month is not None:
        target_year = year if year is not None else now_vn.year
        try:
            d_obj = datetime.date(target_year, month, day)
            if not has_explicit_year and d_obj < now_vn.date():
                d_obj = datetime.date(target_year + 1, month, day)
            lbl = f"ngày {d_obj.day:02d}/{d_obj.month:02d}/{d_obj.year}" if has_explicit_year else f"ngày {d_obj.day:02d}/{d_obj.month:02d}"
            return cleaned_time, d_obj, lbl
        except ValueError:
            pass

    return cleaned_time, None, ""


REPEAT_VI_LABELS: dict[str, str] = {
    "once": "",
    "daily": "hàng ngày",
    "weekly": "hàng tuần",
    "hourly": "hàng giờ",
    "monthly": "hàng tháng",
}

REPEAT_INTERVAL_SECONDS: dict[str, float] = {
    "daily": 86400.0,
    "weekly": 7.0 * 86400.0,
    "hourly": 3600.0,
    "monthly": 30.0 * 86400.0,
}


def detect_repeat_mode(text: str, explicit_repeat: str = "") -> str:
    """Tự động nhận diện chu kỳ lặp nếu người dùng nói 'hàng ngày', 'hàng tuần', 'hàng giờ', 'hàng tháng'.
    Mặc định là 'once' (chỉ chạy 1 lần duy nhất rồi dừng).
    """
    r = explicit_repeat.strip().lower()
    if r in ("daily", "hàng ngày", "mỗi ngày", "hang ngay", "moi ngay"):
        return "daily"
    if r in ("weekly", "hàng tuần", "mỗi tuần", "hang tuan", "moi tuan"):
        return "weekly"
    if r in ("hourly", "hàng giờ", "mỗi giờ", "hang gio", "moi gio"):
        return "hourly"
    if r in ("monthly", "hàng tháng", "mỗi tháng", "hang thang", "moi thang"):
        return "monthly"

    s = text.strip().lower()
    if re.search(r"\b(hàng\s+ngày|mỗi\s+ngày|hằng\s+ngày|mọi\s+ngày)\b", s):
        return "daily"
    if re.search(r"\b(hàng\s+tuần|mỗi\s+tuần|hằng\s+tuần)\b", s):
        return "weekly"
    if re.search(r"\b(hàng\s+giờ|mỗi\s+giờ|hằng\s+giờ)\b", s):
        return "hourly"
    if re.search(r"\b(hàng\s+tháng|mỗi\s+tháng|hằng\s+tháng)\b", s):
        return "monthly"
    return "once"


def normalize_reset_scope(raw_scope: str) -> str:
    """Chuẩn hóa 4 loại Reset:
    1. 'voice'  : Reset cấp quyền giọng nói (xóa giọng phụ, chỉ giữ về giọng Chủ nhà).
    2. 'timers' : Reset đặt thời gian / hẹn giờ (xóa sạch Bể 1).
    3. 'rules'  : Reset luật động / đổi từ / đổi lệnh (xóa sạch Bể 2).
    4. 'all'    : Reset tất cả (cả giọng nói, thời gian, luật và thiết bị).
    """
    s = (raw_scope or "all").strip().lower()
    if s in ("voice", "voices", "speaker", "voice_auth") or any(
        k in s for k in ("giọng", "quyền giọng", "xóa giọng", "cấp quyền")
    ):
        return "voice"
    if s in ("timer", "timers", "time", "schedule") or any(
        k in s for k in ("thời gian", "hẹn giờ", "bể hẹn giờ", "lịch hẹn")
    ):
        return "timers"
    if s in ("rule", "rules", "alias", "word", "words") or any(
        k in s for k in ("luật", "đổi từ", "đổi lệnh", "ngôn ngữ")
    ):
        return "rules"
    return "all"


def parse_vn_clock_and_date(
    time_str: str, date_str: str = "", repeat: str = "", now_vn: datetime.datetime | None = None
) -> dict[str, Any] | None:
    """Phân tích chuỗi giờ Việt Nam theo đúng 4 quy tắc của Sếp + chu kỳ lặp (1 lần vs hàng ngày/tuần):
    - Nếu có nói rõ AM / PM (hoặc sáng/trưa/chiều/tối/đêm, hoặc giờ 24h >= 13): đặt 1 mốc tiếp theo.
    - Nếu chỉ nói giờ (1..12) mà KHÔNG nói AM hay PM: tự động đặt CẢ 2 MỐC (AM và PM).
    - Chỉ khi người dùng có nói thêm ngày/tháng thì mới kèm ngày/tháng.
    - Mặc định chạy 1 lần ('once') rồi dừng; chỉ lặp lại khi nói 'hàng ngày', 'hàng tuần', 'hàng giờ'...
    """
    now_vn = now_vn or get_vn_now()
    repeat_mode = detect_repeat_mode(f"{time_str} {date_str}", repeat)
    cleaned_time, target_date, date_label = _extract_vn_date(time_str, date_str, now_vn)
    cleaned_time = re.sub(
        r"\b(hàng\s+ngày|mỗi\s+ngày|hằng\s+ngày|hàng\s+tuần|mỗi\s+tuần|hằng\s+tuần|hàng\s+giờ|mỗi\s+giờ|hàng\s+tháng|mỗi\s+tháng)\b",
        " ",
        cleaned_time,
        flags=re.I,
    )
    s = cleaned_time.strip().lower()

    is_pm = bool(re.search(r"\b(pm|chiều|tối|đêm)\b", s)) or ("p.m" in s)
    is_am = bool(re.search(r"\b(am|sáng|trưa)\b", s)) or ("a.m" in s)

    nums = [int(x) for x in re.findall(r"\d+", s)]
    if not nums:
        return None
    hh = nums[0]
    mm = nums[1] if len(nums) >= 2 else 0
    ss = nums[2] if len(nums) >= 3 else 0

    if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
        return None

    # Nếu chỉ nói giờ (1..12) mà KHÔNG nói AM/PM -> Đặt cả AM và PM!
    if not is_am and not is_pm and 1 <= hh <= 12:
        am_h24 = 0 if hh == 12 else hh
        pm_h24 = 12 if hh == 12 else hh + 12
        hours_24 = [am_h24, pm_h24]
        both_ampm = True
    else:
        if is_pm and hh < 12:
            h24 = hh + 12
        elif is_am and hh == 12:
            h24 = 0
        else:
            h24 = hh
        hours_24 = [h24]
        both_ampm = False

    rep_lbl = REPEAT_VI_LABELS.get(repeat_mode, "")
    slots: list[dict[str, Any]] = []
    for h24 in hours_24:
        clock_label = _format_clock_12h(h24, mm, ss)
        if target_date is not None:
            dt = datetime.datetime(
                target_date.year, target_date.month, target_date.day, h24, mm, ss, tzinfo=VN_TZ
            )
            if dt <= now_vn:
                dt += datetime.timedelta(days=1)
            full_label = f"{clock_label} {date_label}"
        else:
            dt = now_vn.replace(hour=h24, minute=mm, second=ss, microsecond=0)
            if dt <= now_vn:
                dt += datetime.timedelta(days=1)
            full_label = clock_label

        if rep_lbl:
            full_label = f"{full_label} ({rep_lbl})"

        delay_sec = max(1.0, (dt - now_vn).total_seconds())
        slots.append({
            "hour_24": h24,
            "minute": mm,
            "second": ss,
            "target_dt": dt,
            "delay_seconds": delay_sec,
            "clock_label": clock_label,
            "target_vn_time": full_label,
            "repeat": repeat_mode,
        })

    return {
        "both_ampm": both_ampm,
        "has_date": target_date is not None,
        "date_label": date_label,
        "repeat": repeat_mode,
        "repeat_label": rep_lbl,
        "slots": slots,
    }


def parse_vn_time_string(time_str: str) -> tuple[int, int, int] | None:
    """Hàm tương thích ngược trả về (hh, mm, ss) của mốc đầu tiên."""
    info = parse_vn_clock_and_date(time_str)
    if not info or not info["slots"]:
        return None
    s0 = info["slots"][0]
    return s0["hour_24"], s0["minute"], s0["second"]


def ensure_factory_file() -> dict[str, Any]:
    """Mặc định gốc hoàn toàn nguyên bản: mở cửa chỉ mở cửa, bật đèn chỉ bật đèn (không có luật phụ)."""
    factory_data = {
        "version": "3.0-FACTORY-PURE",
        "description": "Cấu hình gốc nguyên bản (Mở cửa chỉ mở cửa, bật đèn chỉ bật đèn, 2 bể trống 100%)",
        "word_mappings": {},
        "aliases": {},
        "if_else_rules": [],
    }
    FACTORY_FILE.write_text(json.dumps(factory_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return factory_data


class SmartHomeEngine:
    def __init__(
        self,
        on_event: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
        on_voice_reset: Callable[[], dict[str, Any]] | None = None,
    ):
        self.on_event = on_event
        self.on_voice_reset = on_voice_reset
        self._current_user_id: str = "tuan_anh"
        self._current_role: str = "ADMIN"
        self.devices: dict[str, dict[str, Any]] = {
            k: dict(v, updated_at=time.time()) for k, v in DEFAULT_DEVICES.items()
        }
        self.factory_rules = ensure_factory_file()
        self.overlay_rules = self._load_overlay()
        self.users: dict[str, dict[str, Any]] = self._init_users()
        self.active_timers: dict[str, dict[str, Any]] = {}
        self._timer_tasks: dict[str, asyncio.Task] = {}
        self._timer_seq = 0
        self.pending_reset_confirmation: bool = False
        self.pending_reset_scope: str = "all"
        self.pending_rule: dict[str, Any] | None = None
        self.pending_voice_enrollment: dict[str, Any] | None = None

    @property
    def system_policies(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "tier3_can_schedule_timer": False,
            "tier3_can_custom_rules": False,
            "tier3_can_grant_revoke": False,
            "tier2_can_grant_tier2": False,
            "tier2_can_revoke_same_tier": False,
            "tier2_can_override_tier1": False,
            "require_rule_confirmation": True,
            "require_reset_confirmation": True,
            "enrollment_signal_device_id": "living_room_light",
            "enrollment_duration_seconds": 5,
            "device_min_tiers": {
                "main_door": 3,
                "living_room_light": 3,
                "bedroom_light": 3,
                "fan": 3,
                "ac": 3,
                "alarm_siren": 3,
            },
            "custom_system_directives": [],
        }
        pol = self.overlay_rules.setdefault("system_policies", {})
        if not isinstance(pol, dict):
            pol = {}
            self.overlay_rules["system_policies"] = pol
        for k, v in defaults.items():
            if k not in pol:
                pol[k] = dict(v) if isinstance(v, dict) else (list(v) if isinstance(v, list) else v)
        if not isinstance(pol.get("device_min_tiers"), dict):
            pol["device_min_tiers"] = dict(defaults["device_min_tiers"])
        else:
            for dk, dv in defaults["device_min_tiers"].items():
                pol["device_min_tiers"].setdefault(dk, dv)
        if not isinstance(pol.get("custom_system_directives"), list):
            pol["custom_system_directives"] = []
        return pol

    @property
    def query_permission_mode(self) -> str:
        return str(self.overlay_rules.get("query_permission_mode", "tier_restricted"))

    async def set_query_permission_policy(self, mode: str) -> dict[str, Any]:
        """Thay đổi quy tắc phân quyền hỏi đáp (CHỈ Cấp 1 Nguyễn Tuấn Anh mới có quyền thay đổi):
        - 'open_all': Tất cả các cấp (Cấp 1, 2, 3) hỏi gì cũng được AI trả lời hết mọi thông tin.
        - 'tier_restricted': Từng tầng chỉ được hỏi thông tin thuộc phạm vi quyền của tầng đó; riêng Cấp 1 được trả lời tất cả.
        """
        if self.current_tier > 1:
            msg = "Từ chối truy cập! Chỉ Cấp 1 Nguyễn Tuấn Anh mới có quyền thay đổi quy định trả lời câu hỏi của hệ thống."
            await self.emit({"type": "rbac_blocked", "action": "set_query_permission_policy", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        m_low = (mode or "").strip().lower()
        if m_low in ("open_all", "all", "everyone", "tat_ca", "open", "true", "allow"):
            norm_mode = "open_all"
            spoken = "Đã mở quyền hỏi: Tất cả các cấp đều được trả lời mọi thông tin."
        else:
            norm_mode = "tier_restricted"
            spoken = "Đã giới hạn quyền hỏi: Từng cấp chỉ được trả lời trong phạm vi quyền của cấp đó."

        self.overlay_rules["query_permission_mode"] = norm_mode
        self._save_overlay()
        await self.emit({
            "type": "query_policy_updated",
            "query_permission_mode": norm_mode,
            "message": spoken,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "query_permission_mode": norm_mode,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
            "message": spoken,
        }

    async def admin_update_system_policy(
        self,
        policy_key: str,
        policy_value: str = "",
        target_device_id: str = "",
    ) -> dict[str, Any]:
        """Cho phép Admin Cấp 1 (Nguyễn Tuấn Anh) sửa BẤT KỲ quy tắc hệ thống, quyền hạn của Cấp 2/Cấp 3,
        quyền thiết bị, quy tắc hỏi xác nhận, hoặc thêm chỉ thị hệ thống tự do hoàn toàn bằng giọng nói!
        Nếu Cấp 2 hoặc Cấp 3 gọi hàm này -> Chặn ngay lập tức!
        """
        if self.current_tier > 1:
            msg = "Từ chối truy cập! Chỉ Admin Cấp 1 Nguyễn Tuấn Anh mới có quyền sửa quy tắc và phân quyền hệ thống bằng giọng nói."
            await self.emit({"type": "rbac_blocked", "action": "admin_update_system_policy", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        key = (policy_key or "").strip().lower()
        val_str = (policy_value or "").strip()
        val_low = val_str.lower()
        is_true = val_low in ("true", "1", "yes", "on", "allow", "open", "open_all", "cho_phep", "bat", "co")
        pol = self.system_policies

        if key == "query_permission_mode":
            return await self.set_query_permission_policy(val_str)

        if key == "tier3_can_schedule_timer":
            pol["tier3_can_schedule_timer"] = is_true
            spoken = (
                "Đã cập nhật luật: Cho phép Cấp 3 (Khách) được đặt và hủy hẹn giờ."
                if is_true
                else "Đã cập nhật luật: Cấm Cấp 3 (Khách) hẹn giờ."
            )
        elif key == "tier3_can_custom_rules":
            pol["tier3_can_custom_rules"] = is_true
            spoken = (
                "Đã cập nhật luật: Cho phép Cấp 3 (Khách) tùy chỉnh khẩu lệnh và đặt luật IF-ELSE."
                if is_true
                else "Đã cập nhật luật: Cấp 3 (Khách) chỉ được gọi lệnh đóng mở cố định."
            )
        elif key == "tier3_can_grant_revoke":
            pol["tier3_can_grant_revoke"] = is_true
            spoken = (
                "Đã cập nhật luật: Cho phép Cấp 3 được cấp và hủy quyền Cấp 3."
                if is_true
                else "Đã cập nhật luật: Cấm Cấp 3 cấp hoặc hủy quyền của bất kỳ ai."
            )
        elif key == "tier2_can_grant_tier2":
            pol["tier2_can_grant_tier2"] = is_true
            spoken = (
                "Đã cập nhật luật: Cho phép Cấp 2 được cấp quyền cho cả Cấp 2 và Cấp 3."
                if is_true
                else "Đã cập nhật luật: Cấp 2 chỉ được cấp quyền cho Cấp 3."
            )
        elif key == "tier2_can_revoke_same_tier":
            pol["tier2_can_revoke_same_tier"] = is_true
            spoken = (
                "Đã cập nhật luật: Cho phép Cấp 2 được hủy quyền cùng cấp Cấp 2."
                if is_true
                else "Đã cập nhật luật: Cấm Cấp 2 hủy quyền cùng cấp."
            )
        elif key == "tier2_can_override_tier1":
            pol["tier2_can_override_tier1"] = is_true
            spoken = (
                "Đã cập nhật luật: Cho phép Cấp 2 điều chỉnh lịch hẹn và luật của Cấp 1."
                if is_true
                else "Đã cập nhật luật: Bảo vệ tuyệt đối lịch hẹn và luật của Cấp 1 Nguyễn Tuấn Anh."
            )
        elif key == "require_rule_confirmation":
            pol["require_rule_confirmation"] = is_true
            spoken = (
                "Đã cập nhật luật: Khi xét luật mới phải hỏi xác nhận trước khi lưu."
                if is_true
                else "Đã cập nhật luật: Khi xét luật mới sẽ lưu thẳng ngay lập tức, không cần hỏi xác nhận."
            )
        elif key == "require_reset_confirmation":
            pol["require_reset_confirmation"] = is_true
            spoken = (
                "Đã cập nhật luật: Khi reset hệ thống phải hỏi xác nhận trước."
                if is_true
                else "Đã cập nhật luật: Khi gọi reset sẽ thực thi ngay lập tức không cần hỏi lại."
            )
        elif key == "enrollment_signal_device_id":
            dev_id = target_device_id.strip() or val_str
            if dev_id not in self.devices:
                dev_id = "living_room_light"
            pol["enrollment_signal_device_id"] = dev_id
            dname = self.devices[dev_id]["name"].lower()
            spoken = f"Đã cập nhật luật: Khi thu âm cấp quyền sẽ nháy {dname} làm tín hiệu bắt đầu."
        elif key == "enrollment_duration_seconds":
            try:
                sec = max(3, min(int(float(val_str)), 15))
            except Exception:
                sec = 5
            pol["enrollment_duration_seconds"] = sec
            spoken = f"Đã cập nhật luật: Thời gian thu âm giọng nói cấp quyền là {sec} giây."
        elif key == "device_min_tier":
            dev_id = (target_device_id or "").strip()
            try:
                min_t = max(1, min(int(float(val_str)), 3))
            except Exception:
                min_t = 3
            if dev_id in ("all_devices", "all"):
                for dk in self.devices:
                    pol["device_min_tiers"][dk] = min_t
                spoken = f"Đã cập nhật luật: Tất cả thiết bị yêu cầu tối thiểu Cấp {min_t} mới được điều khiển."
            elif dev_id in self.devices:
                pol["device_min_tiers"][dev_id] = min_t
                dname = self.devices[dev_id]["name"].lower()
                spoken = f"Đã cập nhật luật: Chỉ từ Cấp {min_t} trở lên mới được điều khiển {dname}."
            else:
                return {"ok": False, "error": f"Không tìm thấy thiết bị '{dev_id}'."}
        elif key in ("custom_directive_add", "custom_rule", "add_directive"):
            if not val_str:
                return {"ok": False, "error": "Nội dung quy tắc mới không được để trống."}
            directives: list[str] = pol.setdefault("custom_system_directives", [])
            if val_str not in directives:
                directives.append(val_str)
            spoken = f"Đã ghi nhận quy tắc hệ thống mới: {val_str}."
        elif key in ("custom_directive_remove", "remove_directive", "clear_directives"):
            directives = pol.setdefault("custom_system_directives", [])
            if not val_str or val_low in ("all", "tat_ca", "clear"):
                directives.clear()
                spoken = "Đã xóa toàn bộ các quy tắc hệ thống tùy chỉnh."
            else:
                pol["custom_system_directives"] = [
                    d for d in directives if val_low not in d.lower()
                ]
                spoken = f"Đã xóa quy tắc hệ thống khớp với '{val_str}'."
        else:
            # Nếu Admin nói một quy tắc bất kỳ khác, tự động lưu vào custom_system_directives
            rule_text = f"{policy_key}: {val_str}".strip(": ")
            directives = pol.setdefault("custom_system_directives", [])
            if rule_text and rule_text not in directives:
                directives.append(rule_text)
            spoken = f"Đã cập nhật quy tắc hệ thống: {rule_text}."

        self._save_overlay()
        await self.emit({
            "type": "system_policy_updated",
            "policy_key": key,
            "policy_value": val_str,
            "system_policies": pol,
            "message": spoken,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "policy_key": key,
            "system_policies": pol,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
            "message": spoken,
        }

    def _init_users(self) -> dict[str, dict[str, Any]]:
        users_map = {k: dict(v) for k, v in DEFAULT_USERS.items()}
        saved_users = self.overlay_rules.get("users", {})
        if isinstance(saved_users, dict):
            for uid, uinfo in saved_users.items():
                if isinstance(uinfo, dict):
                    users_map[uid] = dict(uinfo)
        # Đảm bảo Tầng 1 Nguyễn Tuấn Anh luôn toàn quyền bất khả xâm phạm
        users_map["tuan_anh"] = dict(DEFAULT_USERS["tuan_anh"])
        self.overlay_rules["users"] = users_map
        return users_map

    @property
    def current_user_id(self) -> str:
        return self._current_user_id

    @property
    def current_tier(self) -> int:
        if self._current_role == "UNKNOWN":
            return 4
        u = self.users.get(self._current_user_id)
        if u:
            if not u.get("active", True):
                return 4
            return int(u.get("tier", 3))
        if self._current_role == "ADMIN":
            return 1
        if self._current_role == "MEMBER":
            return 2
        if self._current_role == "CHILD_GUEST":
            return 3
        return 4

    def get_current_user_name(self) -> str:
        u = self.users.get(self._current_user_id)
        if u:
            return u.get("name", self._current_user_id)
        return "Người lạ"

    @property
    def current_role(self) -> str:
        return self._current_role

    @current_role.setter
    def current_role(self, val: str) -> None:
        v = (val or "").strip()
        v_low = v.lower()
        # Cho phép gán bằng user_id ("tuan_anh", "thanh_vien_a", "thanh_vien_b", "khach_c", "khach_d")
        if hasattr(self, "users") and v_low in self.users:
            u = self.users[v_low]
            self._current_user_id = v_low
            self._current_role = u["role"] if u.get("active", True) else "UNKNOWN"
            return
        # Cho phép tìm theo tên hiển thị (VD: "Nguyễn Tuấn Anh", "Thành viên A", "Khách C")
        if hasattr(self, "users"):
            for uid, u in self.users.items():
                if u.get("name", "").strip().lower() == v_low:
                    self._current_user_id = uid
                    self._current_role = u["role"] if u.get("active", True) else "UNKNOWN"
                    return
        r = v.upper()
        if r in ROLE_LEVELS:
            self._current_role = r
            if r == "ADMIN":
                self._current_user_id = "tuan_anh"
            elif r == "MEMBER":
                if not hasattr(self, "users") or self.users.get(self._current_user_id, {}).get("tier") != 2:
                    self._current_user_id = "thanh_vien_a"
            elif r == "CHILD_GUEST":
                if not hasattr(self, "users") or self.users.get(self._current_user_id, {}).get("tier") != 3:
                    self._current_user_id = "khach_c"
            else:
                self._current_user_id = "unknown"

    def set_active_user(self, user_or_role: str) -> dict[str, Any]:
        self.current_role = user_or_role
        u = self.users.get(self._current_user_id, {
            "id": self._current_user_id,
            "name": self.get_current_user_name(),
            "tier": self.current_tier,
            "role": self._current_role,
            "active": self._current_role != "UNKNOWN",
        })
        return {
            "ok": True,
            "user_id": self._current_user_id,
            "user_name": u.get("name", self._current_user_id),
            "tier": self.current_tier,
            "role": self._current_role,
            "active": u.get("active", True),
        }

    def _default_overlay(self) -> dict[str, Any]:
        return {
            "word_mappings": {},   # Bể Tầng 1 mặc định (backward-compat)
            "aliases": {},         # Bể Tầng 1 mặc định (backward-compat)
            "if_else_rules": [],   # Bể Tầng 1 mặc định (backward-compat)
            "chains": [],
            "users": {k: dict(v) for k, v in DEFAULT_USERS.items()},
            "user_pools": {
                "tuan_anh": {"word_mappings": {}, "aliases": {}, "if_else_rules": []},
                "thanh_vien_a": {"word_mappings": {}, "aliases": {}, "if_else_rules": []},
                "thanh_vien_b": {"word_mappings": {}, "aliases": {}, "if_else_rules": []},
            },
        }

    def _load_overlay(self) -> dict[str, Any]:
        if OVERLAY_FILE.exists():
            try:
                data = json.loads(OVERLAY_FILE.read_text(encoding="utf-8"))
                base = self._default_overlay()
                base.update(data)
                if "user_pools" not in base or not isinstance(base["user_pools"], dict):
                    base["user_pools"] = self._default_overlay()["user_pools"]
                # Đồng bộ bể Tầng 1 với top-level nếu top-level có dữ liệu
                t1_pool = base["user_pools"].setdefault(
                    "tuan_anh", {"word_mappings": {}, "aliases": {}, "if_else_rules": []}
                )
                if base.get("word_mappings") and not t1_pool.get("word_mappings"):
                    t1_pool["word_mappings"] = dict(base["word_mappings"])
                if base.get("aliases") and not t1_pool.get("aliases"):
                    t1_pool["aliases"] = dict(base["aliases"])
                if base.get("if_else_rules") and not t1_pool.get("if_else_rules"):
                    t1_pool["if_else_rules"] = list(base["if_else_rules"])
                return base
            except Exception:
                pass
        default_ov = self._default_overlay()
        OVERLAY_FILE.write_text(json.dumps(default_ov, ensure_ascii=False, indent=2), encoding="utf-8")
        return default_ov

    def _get_user_pool(self, user_id: str | None = None) -> dict[str, Any]:
        uid = user_id or self._current_user_id
        pools = self.overlay_rules.setdefault("user_pools", {})
        if uid not in pools or not isinstance(pools[uid], dict):
            pools[uid] = {"word_mappings": {}, "aliases": {}, "if_else_rules": []}
        pools[uid].setdefault("word_mappings", {})
        pools[uid].setdefault("aliases", {})
        pools[uid].setdefault("if_else_rules", [])
        return pools[uid]

    def _save_overlay(self) -> None:
        # Đồng bộ bể của Tầng 1 Nguyễn Tuấn Anh ra top-level để tương thích ngược
        t1_pool = self._get_user_pool("tuan_anh")
        self.overlay_rules["word_mappings"] = dict(t1_pool.get("word_mappings", {}))
        self.overlay_rules["aliases"] = dict(t1_pool.get("aliases", {}))
        self.overlay_rules["if_else_rules"] = list(t1_pool.get("if_else_rules", []))
        self.overlay_rules["users"] = self.users
        OVERLAY_FILE.write_text(json.dumps(self.overlay_rules, ensure_ascii=False, indent=2), encoding="utf-8")

    async def emit(self, event: dict[str, Any]) -> None:
        if self.on_event is not None:
            await self.on_event(event)

    def get_merged_aliases(self, user_id: str | None = None) -> dict[str, list[dict[str, str]]]:
        merged = dict(self.factory_rules.get("aliases", {}))
        # Cấp 3 (Khách) chỉ được gọi các lệnh đóng/mở cố định (trừ khi Admin Cấp 1 mở quyền tier3_can_custom_rules)
        if user_id is None and self.current_tier >= 3 and not self.system_policies.get("tier3_can_custom_rules", False):
            return merged
        pool = self._get_user_pool(user_id)
        merged.update(pool.get("aliases", {}))
        return merged

    def get_word_mappings(self, user_id: str | None = None) -> dict[str, str]:
        if user_id is None and self.current_tier >= 3 and not self.system_policies.get("tier3_can_custom_rules", False):
            return {}
        pool = self._get_user_pool(user_id)
        return dict(pool.get("word_mappings", {}))

    def get_if_else_rules(self, user_id: str | None = None) -> list[dict[str, Any]]:
        if user_id is None and self.current_tier >= 3 and not self.system_policies.get("tier3_can_custom_rules", False):
            return []
        pool = self._get_user_pool(user_id)
        return list(pool.get("if_else_rules", []))

    def get_chains(self) -> list[dict[str, Any]]:
        return self.get_if_else_rules()

    def format_duration_vi(self, total_sec: float) -> str:
        s = int(round(max(0.0, total_sec)))
        h = s // 3600
        m = (s % 3600) // 60
        sec = s % 60
        parts = []
        if h > 0:
            parts.append(f"{h} giờ")
        if m > 0:
            parts.append(f"{m} phút")
        if sec > 0 or not parts:
            parts.append(f"{sec} giây")
        return " ".join(parts)

    def _action_device_phrase_vi(self, device_id: str, action: str) -> str:
        if device_id == "all_lights":
            verb = "bật" if action in ("open", "turn_on") else "tắt"
            return f"{verb} tất cả đèn"
        if device_id == "all_devices":
            verb = "bật" if action in ("open", "turn_on") else "tắt"
            return f"{verb} tất cả thiết bị"
        dev = self.devices.get(device_id, {})
        dname = dev.get("name", device_id).lower()
        dtype = dev.get("type", "light")
        if dtype == "door":
            verb = "mở" if action in ("open", "turn_on") else "đóng"
        elif dtype == "ac":
            verb = "mở" if action in ("open", "turn_on") else "tắt"
        else:
            verb = "bật" if action in ("open", "turn_on") else "tắt"
        return f"{verb} {dname}"

    def describe_device_command(self, device_id: str) -> str:
        """Trả lời ngắn gọn lệnh điều khiển hiện tại của một thiết bị (gồm mặc định, từ đổi, khẩu lệnh đổi và luật IF)."""
        if device_id not in self.devices:
            return "Không tìm thấy thiết bị này."
        dev = self.devices[device_id]
        dname = dev["name"].lower()
        dtype = dev["type"]
        if dtype == "door":
            default_cmd = f"'mở {dname}' và 'đóng {dname}'"
        elif dtype == "ac":
            default_cmd = f"'mở {dname}' và 'tắt {dname}'"
        else:
            default_cmd = f"'bật {dname}' và 'tắt {dname}'"

        words = [
            f"'{w}'"
            for w, m in self.get_word_mappings().items()
            if device_id in m.lower() or dname in m.lower()
        ]
        aliases = [
            f"'{p}' ({', '.join(self._action_device_phrase_vi(s['device_id'], s['action']) for s in steps)})"
            for p, steps in self.get_merged_aliases().items()
            if any(s["device_id"] == device_id for s in steps)
        ]
        ifs = []
        for r in self.get_if_else_rules():
            if r["when_device_id"] == device_id or r["then_device_id"] == device_id or r.get("else_device_id") == device_id:
                when_v = "mở" if r["when_state"] in ("OPEN", "ON") else ("đóng" if r["when_state"] == "CLOSED" else "tắt")
                then_p = self._action_device_phrase_vi(r["then_device_id"], r["then_action"])
                ifs.append(f"nếu {when_v} {r['when_device_name'].lower()} thì {then_p}")

        if not words and not aliases and not ifs:
            return f"Lệnh của {dname} đang ở mặc định: {default_cmd}."

        parts = [f"Lệnh mặc định là {default_cmd}"]
        if words:
            parts.append(f"tên gọi thêm: {', '.join(words)}")
        if aliases:
            parts.append(f"khẩu lệnh đã đổi: {', '.join(aliases)}")
        if ifs:
            parts.append(f"luật đi kèm: {'; '.join(ifs)}")
        return "; ".join(parts) + "."

    def get_pools_summary(self, query_type: str = "all", target_device_id: str = "") -> dict[str, Any]:
        """Trả về thông tin chi tiết của 2 Bể (Bể Hẹn Giờ & Bể Luật Động) hoặc lệnh của 1 thiết bị.
        Tôn trọng quy tắc phân quyền hỏi (`query_permission_mode`: 'tier_restricted' vs 'open_all').
        """
        q_type = (query_type or "all").strip().lower()
        q_mode = self.query_permission_mode

        # Nếu đang ở chế độ giới hạn hỏi theo cấp ('tier_restricted'):
        # - Cấp 3 (Khách) chỉ được hỏi lệnh đóng mở cơ bản của thiết bị, không được hỏi lịch hẹn giờ hay bể luật!
        if q_mode != "open_all" and self.current_tier >= 3:
            if target_device_id and target_device_id in self.devices and q_type == "device_command":
                spoken = self.describe_device_command(target_device_id)
                return {
                    "ok": True,
                    "query_type": q_type,
                    "current_user_id": self._current_user_id,
                    "current_user_name": self.get_current_user_name(),
                    "current_tier": self.current_tier,
                    "timer_pool_count": 0,
                    "timer_pool_items": [],
                    "rule_pool_count": 0,
                    "rule_pool_items": [],
                    "exact_spoken_reply": spoken,
                    "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
                    "summary": spoken,
                }
            deny_msg = "Bạn đang ở Cấp 3 (Khách), chỉ được hỏi về lệnh đóng mở thiết bị cơ bản."
            return {
                "ok": False,
                "query_type": q_type,
                "current_user_id": self._current_user_id,
                "current_user_name": self.get_current_user_name(),
                "current_tier": self.current_tier,
                "timer_pool_count": 0,
                "timer_pool_items": [],
                "rule_pool_count": 0,
                "rule_pool_items": [],
                "exact_spoken_reply": deny_msg,
                "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{deny_msg}'",
                "summary": deny_msg,
            }

        snap = self.get_snapshot()
        all_timers = snap["timers"]
        # Nếu ở Cấp 2 và chế độ 'tier_restricted', chỉ trả lời lịch hẹn giờ thuộc quyền của chính Cấp 2 đó
        if q_mode != "open_all" and self.current_tier == 2:
            timers = [t for t in all_timers if t.get("owner_id") == self._current_user_id]
        else:
            timers = all_timers

        # Nếu chế độ 'open_all' và người hỏi là Cấp 3, lấy bể lệnh của Tầng 1 để trả lời đầy đủ
        if q_mode == "open_all" and self.current_tier >= 3:
            t1_p = self._get_user_pool("tuan_anh")
            words = dict(t1_p.get("word_mappings", {}))
            aliases = dict(t1_p.get("aliases", {}))
            if_rules = list(t1_p.get("if_else_rules", []))
        else:
            words = snap["word_mappings"]
            aliases = snap["custom_aliases"]
            if_rules = snap["if_else_rules"]

        timer_descriptions = []
        spoken_timers = []
        for idx, t in enumerate(timers, 1):
            act_vi = ACTION_VI_LABEL.get(t["action"], t["action"])
            act_phrase = self._action_device_phrase_vi(t["device_id"], t["action"])
            owner_tag = f" [Tầng {t.get('owner_tier', 1)}: {t.get('owner_name', '')}]" if t.get("owner_name") else ""
            if t.get("target_vn_time"):
                timer_descriptions.append(
                    f"#{idx}: {act_vi} {t['device_name']} lúc {t['target_vn_time']}{owner_tag}"
                )
                spoken_timers.append(f"{t['target_vn_time']} {act_phrase}")
            else:
                timer_descriptions.append(
                    f"#{idx}: {act_vi} {t['device_name']} sau {t['remaining_label']}{owner_tag}"
                )
                spoken_timers.append(f"{t['remaining_label']} nữa {act_phrase}")

        rule_descriptions = []
        spoken_rules = []
        for w, m in words.items():
            rule_descriptions.append(f"Đổi từ '{w}' thành {m}")
            spoken_rules.append(f"đổi từ '{w}' thành {m}")
        for p, steps in aliases.items():
            step_vi = ", ".join(
                f"{ACTION_VI_LABEL.get(s['action'], s['action'])} {self.devices.get(s['device_id'], {}).get('name', s['device_id'])}"
                for s in steps
            )
            step_spoken = ", ".join(
                self._action_device_phrase_vi(s["device_id"], s["action"]) for s in steps
            )
            rule_descriptions.append(f"Đổi lệnh '{p}' -> {step_vi}")
            spoken_rules.append(f"lệnh '{p}' là {step_spoken}")
        for r in if_rules:
            then_vi = f"{ACTION_VI_LABEL.get(r['then_action'], r['then_action'])} {r['then_device_name']}"
            when_v = "mở" if r["when_state"] in ("OPEN", "ON") else ("đóng" if r["when_state"] == "CLOSED" else "tắt")
            then_spoken = self._action_device_phrase_vi(r["then_device_id"], r["then_action"])
            desc = f"Quan hệ IF: Khi {r['when_device_name']}={r['when_state']} thì {then_vi}"
            sp_desc = f"nếu {when_v} {r['when_device_name'].lower()} thì {then_spoken}"
            if r.get("else_device_id") and r.get("else_action"):
                else_vi = f"{ACTION_VI_LABEL.get(r['else_action'], r['else_action'])} {r['else_device_name']}"
                else_spoken = self._action_device_phrase_vi(r["else_device_id"], r["else_action"])
                desc += f", ngược lại thì {else_vi}"
                sp_desc += f", ngược lại {else_spoken}"
            rule_descriptions.append(desc)
            spoken_rules.append(sp_desc)

        if target_device_id and target_device_id in self.devices and q_type in ("device_command", "rules", "all"):
            spoken = self.describe_device_command(target_device_id)
        elif q_type == "timers":
            if not spoken_timers:
                spoken = "Hiện không có lịch hẹn giờ nào."
            else:
                spoken = f"Đang có {len(spoken_timers)} lịch hẹn giờ: {', '.join(spoken_timers)}."
        elif q_type == "rules":
            if not spoken_rules:
                spoken = "Hiện không có luật hay lệnh đổi nào, các lệnh đều ở mặc định gốc."
            else:
                spoken = f"Đang có {len(spoken_rules)} luật: {'; '.join(spoken_rules)}."
        else:
            t_part = (
                f"Đang có {len(spoken_timers)} hẹn giờ ({', '.join(spoken_timers)})"
                if spoken_timers
                else "Không có hẹn giờ nào"
            )
            r_part = (
                f"có {len(spoken_rules)} luật ({'; '.join(spoken_rules)})"
                if spoken_rules
                else "không có luật phụ nào"
            )
            spoken = f"{t_part}, và {r_part}."

        return {
            "ok": True,
            "query_type": q_type,
            "query_permission_mode": q_mode,
            "current_user_id": self._current_user_id,
            "current_user_name": self.get_current_user_name(),
            "current_tier": self.current_tier,
            "timer_pool_count": len(timers),
            "timer_pool_items": timer_descriptions,
            "rule_pool_count": len(rule_descriptions),
            "rule_pool_items": rule_descriptions,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời NGẮN GỌN, ĐỦ Ý, KHÔNG LỄ NGHI đúng câu: '{spoken}'",
            "summary": spoken,
        }

    def get_snapshot(self) -> dict[str, Any]:
        now = time.time()
        timers_list = []
        for tid, tinfo in self.active_timers.items():
            rem = max(0.0, round(tinfo["fire_at"] - now, 1))
            dev_name = (
                self.devices[tinfo["device_id"]]["name"]
                if tinfo["device_id"] in self.devices
                else tinfo["device_id"]
            )
            timers_list.append({
                "id": tid,
                "device_id": tinfo["device_id"],
                "device_name": dev_name,
                "action": tinfo["action"],
                "action_vi": ACTION_VI_LABEL.get(tinfo["action"], tinfo["action"]),
                "delay_seconds": tinfo["delay_seconds"],
                "remaining_seconds": rem,
                "remaining_label": self.format_duration_vi(rem),
                "target_vn_time": tinfo.get("target_vn_time", ""),
                "reason": tinfo.get("reason", "Hẹn giờ"),
                "owner_id": tinfo.get("owner_id", "tuan_anh"),
                "owner_name": tinfo.get("owner_name", "Nguyễn Tuấn Anh"),
                "owner_tier": tinfo.get("owner_tier", 1),
            })
        can_custom = self.current_tier <= 2 or self.system_policies.get("tier3_can_custom_rules", False)
        cur_pool = self._get_user_pool(self._current_user_id) if can_custom else {"word_mappings": {}, "aliases": {}, "if_else_rules": []}
        t1_pool = self._get_user_pool("tuan_anh")
        return {
            "vn_time_now": format_vn_time_ampm(),
            "current_user_id": self._current_user_id,
            "current_user_name": self.get_current_user_name(),
            "current_tier": self.current_tier,
            "query_permission_mode": self.query_permission_mode,
            "system_policies": self.system_policies,
            "role": self.current_role,
            "role_name": f"Tầng {self.current_tier} — {self.get_current_user_name()} ({ROLE_NAMES.get(self.current_role, self.current_role)})",
            "users": list(self.users.values()),
            "pending_reset_confirmation": self.pending_reset_confirmation,
            "pending_rule": self.pending_rule,
            "pending_voice_enrollment": self.pending_voice_enrollment,
            "devices": list(self.devices.values()),
            "word_mappings": dict(cur_pool.get("word_mappings", {})),
            "factory_aliases": self.factory_rules.get("aliases", {}),
            "custom_aliases": dict(cur_pool.get("aliases", {})),
            "if_else_rules": list(cur_pool.get("if_else_rules", [])),
            "t1_global_if_else_rules": list(t1_pool.get("if_else_rules", [])),
            "chains": list(cur_pool.get("if_else_rules", [])),
            "timers": timers_list,
        }

    def check_permission(self, required_role: str) -> tuple[bool, str]:
        u = self.users.get(self._current_user_id)
        if u and not u.get("active", True):
            return (
                False,
                f"Từ chối truy cập! Quyền của {u.get('name', self._current_user_id)} đã bị hủy.",
            )
        user_lvl = ROLE_LEVELS.get(self.current_role, 0)
        req_lvl = ROLE_LEVELS.get(required_role, 3)
        if user_lvl < req_lvl:
            return (
                False,
                f"Từ chối truy cập! Cấp hiện tại ({self.get_current_user_name()} - Tầng {self.current_tier}) không đủ quyền.",
            )
        return True, "OK"

    def _check_custom_directive_device_lock(self, dev_id: str) -> tuple[bool, str]:
        """Kiểm tra xem có quy định tự nhiên nào của Admin Cấp 1 (trong custom_system_directives)
        đang khóa thiết bị này theo khung giờ hoặc theo cấp độ hay không.
        """
        directives = self.system_policies.get("custom_system_directives", [])
        if not directives:
            return True, "OK"
        dev = self.devices.get(dev_id, {})
        dname_low = dev.get("name", "").lower()
        dev_keywords = {
            "main_door": ("cửa chính", "cửa", "main_door"),
            "living_room_light": ("đèn phòng khách", "đèn khách", "living_room_light"),
            "bedroom_light": ("đèn phòng ngủ", "đèn ngủ", "bedroom_light"),
            "fan": ("quạt", "fan"),
            "ac": ("điều hòa", "máy lạnh", "ac"),
            "alarm_siren": ("còi báo động", "còi", "báo động", "alarm_siren"),
        }.get(dev_id, (dname_low, dev_id))

        cur_hour = now_vn().hour
        for raw_dir in directives:
            d_low = str(raw_dir).lower()
            if not any(kw in d_low for kw in dev_keywords):
                continue
            if not any(neg in d_low for neg in ("không được", "cấm", "không cho", "khóa")):
                continue
            # Kiểm tra giới hạn theo cấp nếu có nói rõ cấp (VD: "cấm cấp 3 ..."):
            if "cấp 3" in d_low and "cấp 2" not in d_low and self.current_tier < 3:
                continue
            if "cấp 2" in d_low and "cấp 3" not in d_low and self.current_tier != 2:
                continue
            # Nếu Admin Cấp 1 tự thao tác mà quy định chỉ cấm cấp dưới
            if self.current_tier == 1 and ("cấp 2" in d_low or "cấp 3" in d_low or "khách" in d_low):
                continue
            # Kiểm tra giới hạn theo giờ (VD: "sau 11 giờ đêm", "sau 23 giờ", "sau 22h"):
            m_after = re.search(r"sau\s+(\d{1,2})\s*(?:giờ|h)", d_low)
            if m_after:
                hr = int(m_after.group(1))
                if any(w in d_low for w in ("đêm", "tối", "chiều", "pm")) and hr < 12:
                    hr += 12
                # "Sau X giờ đêm" được hiểu là từ X giờ đêm đến 5 giờ sáng hôm sau
                in_locked_hours = (cur_hour >= hr) or (hr >= 18 and cur_hour < 5)
                if in_locked_hours:
                    return False, f"Từ chối truy cập! Đang bị khóa theo quy định của Admin: '{raw_dir}'."
            else:
                return False, f"Từ chối truy cập! Đang bị khóa theo quy định của Admin: '{raw_dir}'."
        return True, "OK"

    def check_device_permission(self, dev_id: str) -> tuple[bool, str]:
        u = self.users.get(self._current_user_id)
        if u and not u.get("active", True):
            return (
                False,
                f"Từ chối truy cập! Quyền của {u.get('name', self._current_user_id)} đã bị hủy.",
            )
        dev = self.devices.get(dev_id, {})
        min_tier = int(self.system_policies.get("device_min_tiers", {}).get(dev_id, 3))
        if self.current_tier > min_tier:
            dname = dev.get("name", dev_id)
            return (
                False,
                f"Từ chối truy cập! Thiết bị {dname} chỉ cho phép từ Cấp {min_tier} trở lên điều khiển.",
            )
        ok_dir, reason_dir = self._check_custom_directive_device_lock(dev_id)
        if not ok_dir:
            return False, reason_dir
        return self.check_permission(dev.get("min_role", "CHILD_GUEST"))

    # -------------------------------------------------------------------------
    # CẤP QUYỀN & HỦY QUYỀN THEO KIẾN TRÚC 3 TẦNG (ADMIN / GIA ĐÌNH / KHÁCH)
    # -------------------------------------------------------------------------
    def _find_or_slug_user(self, target_name: str) -> tuple[str, dict[str, Any] | None]:
        t_clean = target_name.strip()
        t_low = t_clean.lower()
        if t_low in self.users:
            return t_low, self.users[t_low]
        for uid, uinfo in self.users.items():
            if uinfo.get("name", "").strip().lower() == t_low or uid == t_low:
                return uid, uinfo
            # Hỗ trợ gọi tắt: "Khách C" hoặc "C", "Thành viên A" hoặc "A"
            uname_low = uinfo.get("name", "").strip().lower()
            if t_low in uname_low or uname_low in t_low:
                return uid, uinfo
        slug = re.sub(r"[^a-z0-9_]+", "_", t_low).strip("_") or f"user_{int(time.time())}"
        return slug, self.users.get(slug)

    async def blink_signal_light(self, device_id: str = "living_room_light", pulse_sec: float = 0.35) -> None:
        """Nháy đèn 1 phát (Bật -> Tắt hoặc Tắt -> Bật) để làm tín hiệu bắt đầu/kết thúc thu âm cấp quyền."""
        dev = self.devices.get(device_id)
        if not dev:
            return
        orig_state = dev["state"]
        flash_state = "OFF" if orig_state == "ON" else "ON"

        dev["state"] = flash_state
        dev["updated_at"] = time.time()
        await self.emit({
            "type": "device_updated",
            "device_id": device_id,
            "device_name": dev["name"],
            "gpio": dev["gpio"],
            "old_state": orig_state,
            "new_state": flash_state,
            "source": "tín hiệu nháy đèn thu âm",
            "timestamp": dev["updated_at"],
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})

        await asyncio.sleep(max(0.15, float(pulse_sec)))

        dev["state"] = orig_state
        dev["updated_at"] = time.time()
        await self.emit({
            "type": "device_updated",
            "device_id": device_id,
            "device_name": dev["name"],
            "gpio": dev["gpio"],
            "old_state": flash_state,
            "new_state": orig_state,
            "source": "tín hiệu nháy đèn thu âm",
            "timestamp": dev["updated_at"],
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})

    async def start_voice_enrollment(
        self,
        target_tier: int = 3,
        target_name: str = "",
        duration_seconds: int = 0,
        duration_sec: int | None = None,
    ) -> dict[str, Any]:
        """Bước 1 của Thu âm cấp quyền giọng nói:
        - Kiểm tra quyền (Cấp 1 được thu âm cấp cho Cấp 2 & 3; Cấp 2 chỉ được thu âm cấp cho Cấp 3 trừ khi Cấp 1 mở quyền tier2_can_grant_tier2).
        - Đếm 3, 2, 1, nháy thiết bị tín hiệu 1 phát báo hiệu bắt đầu, mở thu âm trong `duration_seconds` giây.
        """
        pol = self.system_policies
        if self.current_tier >= 3 and not pol.get("tier3_can_grant_revoke", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền thu âm cấp quyền cho ai."
            await self.emit({"type": "rbac_blocked", "action": "start_voice_enrollment", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        target_tier = int(target_tier or 3)
        if target_tier not in (2, 3):
            target_tier = 3

        if self.current_tier == 2 and target_tier != 3 and not pol.get("tier2_can_grant_tier2", False):
            msg = "Thành viên Cấp 2 chỉ được phép thu âm cấp quyền cho Cấp 3 (Khách)."
            await self.emit({"type": "rbac_blocked", "action": "start_voice_enrollment", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        default_dur = int(pol.get("enrollment_duration_seconds", 5) or 5)
        raw_dur = duration_sec if duration_sec is not None else (duration_seconds or default_dur)
        dur = max(3, min(int(raw_dur or default_dur), 15))
        sig_dev = str(pol.get("enrollment_signal_device_id", "living_room_light"))
        if sig_dev not in self.devices:
            sig_dev = "living_room_light"
        clean_name = (target_name or "").strip()
        self.pending_voice_enrollment = {
            "step": "RECORDING",
            "target_tier": target_tier,
            "target_name": clean_name,
            "duration_seconds": dur,
            "signal_device_id": sig_dev,
            "granted_by": self._current_user_id,
            "granted_by_tier": self.current_tier,
        }
        tier_label = "Cấp 2 (Thành viên gia đình)" if target_tier == 2 else "Cấp 3 (Khách)"
        spoken = f"Tôi sẽ cấp quyền {tier_label} trong 3, 2, 1. Khi đèn nháy một phát, hãy nói trong {dur} giây để thu âm."
        await self.emit({
            "type": "voice_enrollment_countdown",
            "target_tier": target_tier,
            "target_name": clean_name,
            "duration_seconds": dur,
            "signal_device_id": sig_dev,
            "message": spoken,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "status": "VOICE_ENROLLMENT_COUNTDOWN",
            "target_tier": target_tier,
            "target_name": clean_name,
            "duration_seconds": dur,
            "signal_device_id": sig_dev,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
            "message": spoken,
        }

    async def stage_voice_enrollment_analysis(
        self,
        f0_hz: float,
        centroid_hz: float,
        embedding: list[float],
        duration_sec: float = 5.0,
    ) -> dict[str, Any]:
        """Bước 2 của Thu âm cấp quyền: Sau khi thu âm đủ -> Báo đã thu âm đủ, đã phân tích xong -> Hỏi tên (hoặc lưu luôn nếu đã có tên)."""
        pending = self.pending_voice_enrollment or {
            "target_tier": 3,
            "target_name": "",
            "duration_seconds": 5,
            "granted_by": self._current_user_id,
            "granted_by_tier": self.current_tier,
        }
        target_tier = int(pending.get("target_tier", 3))
        target_name = str(pending.get("target_name", "")).strip()

        pending["step"] = "AWAITING_NAME"
        pending["f0_hz"] = f0_hz
        pending["centroid_hz"] = centroid_hz
        pending["embedding"] = embedding
        pending["duration_sec"] = duration_sec
        self.pending_voice_enrollment = pending

        if target_name and target_name.lower() not in ("người mới", "nguoi moi", "khách mới", "thành viên mới"):
            return await self.finalize_voice_enrollment(target_name=target_name, target_tier=target_tier)

        tier_label = "Cấp 2 (Thành viên gia đình)" if target_tier == 2 else "Cấp 3 (Khách)"
        spoken = (
            f"Đã thu âm đủ và đã phân tích xong giọng nói (tần số {f0_hz} Hz), "
            f"người này sẽ được cấp quyền {tier_label}. Người ấy tên là gì?"
        )
        await self.emit({
            "type": "voice_enrollment_analyzed",
            "f0_hz": f0_hz,
            "centroid_hz": centroid_hz,
            "target_tier": target_tier,
            "message": spoken,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "status": "VOICE_ENROLLMENT_ANALYZED_AWAITING_NAME",
            "f0_hz": f0_hz,
            "centroid_hz": centroid_hz,
            "target_tier": target_tier,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC nói đúng câu: '{spoken}'",
            "message": spoken,
        }

    async def finalize_voice_enrollment(self, target_name: str, target_tier: int = 0) -> dict[str, Any]:
        """Bước 3 của Thu âm cấp quyền: Gán tên cho người vừa thu âm phân tích xong và lưu quyền chính thức."""
        clean_name = (target_name or "").strip()
        if not clean_name:
            return {"ok": False, "error": "Vui lòng cho biết tên của người được cấp quyền."}

        pending = self.pending_voice_enrollment or {}
        tier = int(target_tier or pending.get("target_tier", 3))
        if tier not in (2, 3):
            tier = 3

        res = await self.grant_user_permission(target_name=clean_name, target_tier=tier)
        if not res.get("ok"):
            return res

        f0_hz = pending.get("f0_hz", 185.0)
        centroid_hz = pending.get("centroid_hz", 1520.0)
        embedding = pending.get("embedding", [0.15] * 26)
        self.pending_voice_enrollment = None

        user_obj = res["target_user"]
        user_obj["voice_f0_hz"] = f0_hz
        user_obj["voice_centroid_hz"] = centroid_hz
        self._save_overlay()

        tier_label = "Cấp 2 (Thành viên gia đình)" if tier == 2 else "Cấp 3 (Khách)"
        spoken = f"Đã lưu giọng nói (tần số {f0_hz} Hz) và cấp quyền {tier_label} cho {user_obj['name']}."
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "status": "VOICE_ENROLLMENT_COMPLETED",
            "user_id": user_obj["id"],
            "target_name": user_obj["name"],
            "target_tier": tier,
            "target_user": user_obj,
            "f0_hz": f0_hz,
            "centroid_hz": centroid_hz,
            "embedding": embedding,
            "voice_profile": {
                "f0_hz": f0_hz,
                "centroid_hz": centroid_hz,
                "embedding": embedding,
            },
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
            "message": spoken,
        }

    async def grant_user_permission(self, target_name: str, target_tier: int = 3) -> dict[str, Any]:
        """Cấp quyền theo 3 Tầng (Tôn trọng cấu hình động `system_policies` do Admin Cấp 1 thiết lập)."""
        pol = self.system_policies
        if self.current_tier >= 3 and not pol.get("tier3_can_grant_revoke", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền cấp quyền cho bất kỳ ai."
            await self.emit({"type": "rbac_blocked", "action": "grant_user_permission", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        target_tier = int(target_tier)
        if target_tier not in (2, 3):
            target_tier = 3

        if self.current_tier == 2 and target_tier != 3 and not pol.get("tier2_can_grant_tier2", False):
            msg = "Thành viên Tầng 2 chỉ được cấp quyền cho Khách (Tầng 3), không được cấp quyền Tầng 1 hay Tầng 2."
            await self.emit({"type": "rbac_blocked", "action": "grant_user_permission", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if self.current_tier >= 3 and target_tier != 3:
            msg = "Cấp khách (Tầng 3) chỉ được phép cấp quyền Tầng 3."
            await self.emit({"type": "rbac_blocked", "action": "grant_user_permission", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        uid, existing = self._find_or_slug_user(target_name)
        if uid == "tuan_anh":
            msg = "Nguyễn Tuấn Anh đã là Admin tối cao Tầng 1."
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if (
            existing
            and existing.get("granted_by_tier") == 1
            and existing.get("active", True)
            and self.current_tier > 1
            and not pol.get("tier2_can_override_tier1", False)
        ):
            msg = f"Không thể sửa quyền: {existing['name']} do Tầng 1 Nguyễn Tuấn Anh trực tiếp cấp quyền."
            await self.emit({"type": "rbac_blocked", "action": "grant_user_permission", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        role_code = "MEMBER" if target_tier == 2 else "CHILD_GUEST"
        disp_name = existing["name"] if existing else target_name.strip()
        self.users[uid] = {
            "id": uid,
            "name": disp_name,
            "tier": target_tier,
            "role": role_code,
            "granted_by": self._current_user_id,
            "granted_by_name": f"{self.get_current_user_name()} (Tầng {self.current_tier})",
            "granted_by_tier": self.current_tier,
            "active": True,
        }
        if target_tier == 2:
            self._get_user_pool(uid)
        self._save_overlay()

        tier_label = "Tầng 2 (Thành viên gia đình)" if target_tier == 2 else "Tầng 3 (Khách)"
        spoken = f"Đã cấp quyền {tier_label} cho {disp_name}."
        await self.emit({
            "type": "permission_granted",
            "target_user": self.users[uid],
            "by_user": self._current_user_id,
            "by_tier": self.current_tier,
            "message": spoken,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "target_user": self.users[uid],
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
            "message": spoken,
        }

    async def revoke_user_permission(self, target_name: str) -> dict[str, Any]:
        """Hủy quyền theo 3 Tầng (Tôn trọng cấu hình động `system_policies` do Admin Cấp 1 thiết lập)."""
        pol = self.system_policies
        if self.current_tier >= 3 and not pol.get("tier3_can_grant_revoke", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền hủy quyền của bất kỳ ai."
            await self.emit({"type": "rbac_blocked", "action": "revoke_user_permission", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        uid, existing = self._find_or_slug_user(target_name)
        if not existing:
            msg = f"Không tìm thấy người dùng '{target_name}'."
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if uid == "tuan_anh" or existing.get("tier") == 1:
            msg = "Không ai được phép hủy quyền của Tầng 1 Nguyễn Tuấn Anh."
            await self.emit({"type": "rbac_blocked", "action": "revoke_user_permission", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if self.current_tier >= 2:
            # Kiểm tra bảo vệ người do Tầng 1 cấp quyền (dù ở Tầng 2 hay Tầng 3)
            if existing.get("granted_by_tier") == 1 and not pol.get("tier2_can_override_tier1", False):
                msg = f"Không thể hủy quyền: {existing['name']} được Tầng 1 Nguyễn Tuấn Anh cấp quyền, ngoài Tầng 1 ra không ai được phép hủy."
                await self.emit({"type": "rbac_blocked", "action": "revoke_user_permission", "role": self.current_role, "reason": msg})
                return {"ok": False, "error": msg, "exact_spoken_reply": msg}
            # Kiểm tra cấm hủy cùng cấp Tầng 2 (trừ khi Admin Cấp 1 cho phép tier2_can_revoke_same_tier)
            if self.current_tier == 2 and existing.get("tier") == 2 and not pol.get("tier2_can_revoke_same_tier", False):
                msg = f"Không thể hủy quyền: Thành viên Tầng 2 không được phép hủy quyền cùng cấp ({existing['name']})."
                await self.emit({"type": "rbac_blocked", "action": "revoke_user_permission", "role": self.current_role, "reason": msg})
                return {"ok": False, "error": msg, "exact_spoken_reply": msg}
            if self.current_tier >= 3 and existing.get("tier") < 3:
                msg = f"Không thể hủy quyền của cấp cao hơn ({existing['name']})."
                await self.emit({"type": "rbac_blocked", "action": "revoke_user_permission", "role": self.current_role, "reason": msg})
                return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        existing["active"] = False
        existing["role"] = "UNKNOWN"
        self._save_overlay()

        spoken = f"Đã hủy quyền của {existing['name']}."
        await self.emit({
            "type": "permission_revoked",
            "target_user": existing,
            "by_user": self._current_user_id,
            "by_tier": self.current_tier,
            "message": spoken,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "target_user": existing,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
            "message": spoken,
        }

    def _expand_targets(self, device_id: str, action: str) -> list[tuple[str, str]]:
        if device_id == "all_lights":
            act = "turn_on" if action in ("open", "turn_on") else "turn_off"
            return [("living_room_light", act), ("bedroom_light", act)]
        if device_id == "all_devices":
            if action in ("close", "turn_off"):
                return [
                    ("living_room_light", "turn_off"),
                    ("bedroom_light", "turn_off"),
                    ("fan", "turn_off"),
                    ("ac", "turn_off"),
                    ("alarm_siren", "turn_off"),
                    ("main_door", "close"),
                ]
            return [
                ("living_room_light", "turn_on"),
                ("bedroom_light", "turn_on"),
                ("fan", "turn_on"),
                ("ac", "turn_on"),
            ]
        return [(device_id, action)]

    def _state_verb_vi(self, dev_type: str, state: str, already: bool = False) -> str:
        suffix = " sẵn rồi" if already else ""
        if dev_type == "door":
            return f"đã {'mở' if state == 'OPEN' else 'đóng'}{suffix}"
        if dev_type == "ac":
            return f"đã {'mở' if state == 'ON' else 'tắt'}{suffix}"
        return f"đã {'bật' if state == 'ON' else 'tắt'}{suffix}"

    def _build_concise_spoken_reply(self, results: list[dict[str, Any]]) -> str:
        ok_items = [r for r in results if r.get("ok")]
        if not ok_items:
            errs = [r.get("error", "Lỗi") for r in results if not r.get("ok")]
            return errs[0] if errs else "Không thể thực hiện."

        changed = [r for r in ok_items if not r.get("already_in_state")]
        already = [r for r in ok_items if r.get("already_in_state")]

        # Nếu tất cả thiết bị được gọi đều ĐÃ ở sẵn trạng thái đó rồi
        if not changed and already:
            parts = []
            for r in already:
                dtype = self.devices.get(r["device_id"], {}).get("type", "light")
                parts.append(f"{r['device_name']} {self._state_verb_vi(dtype, r['state'], already=True)}")
            return ", ".join(parts) + "."

        # Nếu có từ 2 thiết bị trở lên cùng mở/bật liên tiếp (VD: bật đèn khách kéo theo mở điều hòa)
        if len(changed) >= 2:
            all_on_or_open = all(r["state"] in ("ON", "OPEN") for r in changed)
            all_off_or_closed = all(r["state"] in ("OFF", "CLOSED") for r in changed)
            names = [changed[0]["device_name"]] + [r["device_name"].lower() for r in changed[1:]]
            joined_names = " và ".join(names) if len(names) == 2 else ", ".join(names[:-1]) + " và " + names[-1]
            if all_on_or_open:
                return f"{joined_names} đã mở."
            if all_off_or_closed:
                has_door = any(self.devices.get(r["device_id"], {}).get("type") == "door" for r in changed)
                if not has_door:
                    return f"{joined_names} đã tắt."

        clauses = []
        for idx, r in enumerate(changed):
            dtype = self.devices.get(r["device_id"], {}).get("type", "light")
            dname = r["device_name"] if idx == 0 else r["device_name"].lower()
            clauses.append(f"{dname} {self._state_verb_vi(dtype, r['state'], already=False)}")
        return " và ".join(clauses) + "."

    async def execute_device_action(
        self,
        device_id: str,
        action: str,
        source: str = "voice",
        bypass_rbac: bool = False,
        trigger_chains: bool = True,
    ) -> dict[str, Any]:
        targets = self._expand_targets(device_id, action)
        results = []
        for dev_id, act in targets:
            if dev_id not in self.devices:
                results.append({"ok": False, "device_id": dev_id, "error": f"Thiết bị '{dev_id}' không tồn tại."})
                continue
            dev = self.devices[dev_id]
            if not bypass_rbac:
                allowed, reason = self.check_device_permission(dev_id)
                if not allowed:
                    await self.emit({
                        "type": "rbac_blocked",
                        "device_id": dev_id,
                        "device_name": dev["name"],
                        "action": act,
                        "role": self.current_role,
                        "reason": reason,
                    })
                    results.append({"ok": False, "device_id": dev_id, "error": reason})
                    continue

            if dev["type"] == "door":
                new_state = "OPEN" if act in ("open", "turn_on") else "CLOSED"
            else:
                new_state = "ON" if act in ("open", "turn_on") else "OFF"

            old_state = dev["state"]
            if old_state == new_state:
                already_msg = f"{dev['name']} {self._state_verb_vi(dev['type'], new_state, already=True)}."
                await self.emit({
                    "type": "device_already_in_state",
                    "device_id": dev_id,
                    "device_name": dev["name"],
                    "state": new_state,
                    "message": already_msg,
                })
                results.append({
                    "ok": True,
                    "device_id": dev_id,
                    "device_name": dev["name"],
                    "state": new_state,
                    "already_in_state": True,
                })
                continue

            dev["state"] = new_state
            dev["updated_at"] = time.time()

            await self.emit({
                "type": "device_updated",
                "device_id": dev_id,
                "device_name": dev["name"],
                "gpio": dev["gpio"],
                "old_state": old_state,
                "new_state": new_state,
                "source": source,
                "timestamp": dev["updated_at"],
            })

            results.append({
                "ok": True,
                "device_id": dev_id,
                "device_name": dev["name"],
                "state": new_state,
                "already_in_state": False,
            })

            # Kiểm tra các luật quan hệ IF theo trạng thái thiết bị (Ưu tiên Tầng 1 trước, sau đó Bể riêng Tầng 2)
            if trigger_chains:
                triggered_fx = await self._evaluate_reactive_if_else(dev_id, new_state)
                results.extend(triggered_fx)

        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        all_ok = all(r["ok"] for r in results) if results else False
        concise_reply = self._build_concise_spoken_reply(results)
        return {
            "ok": all_ok,
            "results": results,
            "exact_spoken_reply": concise_reply,
            "instruction_for_ai": f"BẮT BUỘC trả lời CỰC NGẮN GỌN đúng nguyên văn câu này: '{concise_reply}'",
            "summary": concise_reply,
        }

    async def _evaluate_reactive_if_else(self, changed_dev_id: str, new_state: str) -> list[dict[str, Any]]:
        """Kiểm tra luật IF khi `changed_dev_id` chuyển sang `new_state`.
        - Luật của Tầng 1 (Nguyễn Tuấn Anh) luôn chạy trước và ưu tiên tuyệt đối toàn nhà.
        - Nếu người ra lệnh thuộc Tầng 2 (Thành viên gia đình), chạy tiếp luật trong bể riêng của người đó (không đè lên thiết bị Tầng 1 vừa khóa).
        """
        triggered_results: list[dict[str, Any]] = []
        t1_locked_targets: set[str] = set()

        t1_rules = list(self._get_user_pool("tuan_anh").get("if_else_rules", []))
        rule_batches: list[tuple[int, list[dict[str, Any]]]] = [(1, t1_rules)]
        if self.current_tier == 2 and self._current_user_id != "tuan_anh":
            t2_rules = list(self._get_user_pool(self._current_user_id).get("if_else_rules", []))
            rule_batches.append((2, t2_rules))

        for batch_tier, rules_list in rule_batches:
            for rule in rules_list:
                if rule.get("when_device_id") != changed_dev_id:
                    continue

                if_state = rule.get("when_state", "OPEN")
                delay_sec = float(rule.get("delay_seconds", 0.0))

                # Chiều thuận: khi trạng thái khớp đúng với `when_state`
                if new_state == if_state:
                    then_dev = rule.get("then_device_id")
                    then_act = rule.get("then_action")
                    if then_dev and then_act:
                        if batch_tier > 1 and then_dev in t1_locked_targets:
                            continue
                        if batch_tier == 1:
                            t1_locked_targets.add(then_dev)
                        reason_lbl = f"IF {self.devices[changed_dev_id]['name']}={new_state}"
                        if delay_sec <= 0.2:
                            res = await self.execute_device_action(
                                device_id=then_dev,
                                action=then_act,
                                source=reason_lbl,
                                bypass_rbac=True,
                                trigger_chains=False,
                            )
                            triggered_results.extend(res.get("results", []))
                        else:
                            await self.schedule_action(
                                device_id=then_dev,
                                action=then_act,
                                delay_seconds=delay_sec,
                                reason=reason_lbl,
                                bypass_rbac=True,
                                trigger_chains=False,
                            )

                # Chiều ngược lại (ELSE): CHỈ CHẠY NẾU có khai báo rõ `else_device_id` và `else_action`
                elif new_state == STATE_TO_OPPOSITE.get(if_state):
                    else_dev = rule.get("else_device_id", "")
                    else_act = rule.get("else_action", "")
                    if else_dev and else_act:
                        if batch_tier > 1 and else_dev in t1_locked_targets:
                            continue
                        if batch_tier == 1:
                            t1_locked_targets.add(else_dev)
                        reason_lbl = f"ELSE {self.devices[changed_dev_id]['name']}={new_state}"
                        if delay_sec <= 0.2:
                            res = await self.execute_device_action(
                                device_id=else_dev,
                                action=else_act,
                                source=reason_lbl,
                                bypass_rbac=True,
                                trigger_chains=False,
                            )
                            triggered_results.extend(res.get("results", []))
                        else:
                            await self.schedule_action(
                                device_id=else_dev,
                                action=else_act,
                                delay_seconds=delay_sec,
                                reason=reason_lbl,
                                bypass_rbac=True,
                                trigger_chains=False,
                            )
        return triggered_results

    # -------------------------------------------------------------------------
    # BỂ 1: HẸN GIỜ (1 LẦN MẶC ĐỊNH HOẶC LẶP HÀNG NGÀY/TUẦN, BẢO VỆ HẸN GIỜ TẦNG 1)
    # -------------------------------------------------------------------------
    def _check_t1_timer_conflict(self, device_id: str, new_fire_at: float) -> str | None:
        """Kiểm tra xem cấp dưới có đặt lệnh vướng vào khung giờ hẹn giờ của Tầng 1 Nguyễn Tuấn Anh hay không."""
        if self.current_tier <= 1 or self.system_policies.get("tier2_can_override_tier1", False):
            return None
        target_dev_id = "living_room_light" if device_id in ("all_lights", "all_devices") else device_id
        for tinfo in self.active_timers.values():
            if tinfo.get("owner_tier", 1) != 1:
                continue
            same_dev = (
                device_id == "all_devices"
                or tinfo.get("raw_target") == "all_devices"
                or tinfo.get("device_id") == target_dev_id
                or tinfo.get("raw_target") == device_id
            )
            if not same_dev:
                continue
            # Nếu lịch hẹn của Tầng 1 nằm trong cùng khung giờ (±30 phút = 1800s) trên cùng thiết bị
            if abs(new_fire_at - tinfo["fire_at"]) <= 1800.0:
                dname = self.devices.get(target_dev_id, {}).get("name", target_dev_id)
                return f"Không thể đặt hẹn giờ: {dname} đang có lịch hẹn giờ của Tầng 1 Nguyễn Tuấn Anh trong khung giờ này."
        return None

    async def schedule_timer_flexible(
        self,
        device_id: str,
        action: str,
        hours: float = 0.0,
        minutes: float = 0.0,
        seconds: float = 0.0,
        vn_time_ampm: str = "",
        vn_date: str = "",
        repeat: str = "once",
        reason: str = "Hẹn giờ giọng nói",
    ) -> dict[str, Any]:
        if self.current_tier >= 3 and not self.system_policies.get("tier3_can_schedule_timer", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) chỉ được gọi lệnh đóng mở cố định, không có quyền hẹn giờ."
            await self.emit({"type": "rbac_blocked", "device_id": device_id, "action": "schedule_timer", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        act_phrase = self._action_device_phrase_vi(device_id, action)
        repeat_mode = detect_repeat_mode(f"{vn_time_ampm} {vn_date} {reason}", repeat)
        rep_vi = REPEAT_VI_LABELS.get(repeat_mode, "")

        # Trường hợp 1: Hẹn theo giờ đồng hồ (có AM/PM, hoặc chỉ nói giờ 8:00 -> cả AM & PM, hoặc có kèm ngày)
        if vn_time_ampm and vn_time_ampm.strip():
            parsed = parse_vn_clock_and_date(vn_time_ampm, vn_date, repeat=repeat_mode)
            if not parsed or not parsed.get("slots"):
                return {"ok": False, "error": f"Không hiểu định dạng giờ '{vn_time_ampm}'."}

            slots = parsed["slots"]
            repeat_mode = parsed.get("repeat", repeat_mode)
            rep_vi = parsed.get("repeat_label", rep_vi)
            scheduled_ids: list[str] = []
            for slot in slots:
                res = await self.schedule_action(
                    device_id=device_id,
                    action=action,
                    delay_seconds=slot["delay_seconds"],
                    reason=f"Hẹn lúc {slot['target_vn_time']}",
                    target_vn_time=slot["target_vn_time"],
                    repeat=repeat_mode,
                )
                if not res.get("ok"):
                    return res
                scheduled_ids.append(res["timer_id"])

            rep_part = f" {rep_vi}" if rep_vi else ""
            if parsed["both_ampm"] and len(slots) == 2:
                date_part = f" {parsed['date_label']}" if parsed.get("date_label") else ""
                spoken = f"Đã hẹn {slots[0]['clock_label']} và {slots[1]['clock_label']}{date_part}{rep_part} {act_phrase}."
            else:
                date_part = f" {parsed['date_label']}" if parsed.get("date_label") else ""
                spoken = f"Đã hẹn {slots[0]['clock_label']}{date_part}{rep_part} {act_phrase}."

            return {
                "ok": True,
                "timer_id": scheduled_ids[0],
                "timer_ids": scheduled_ids,
                "both_ampm": parsed["both_ampm"],
                "has_date": parsed["has_date"],
                "repeat": repeat_mode,
                "timer_pool_count": len(self.active_timers),
                "exact_spoken_reply": spoken,
                "instruction_for_ai": f"BẮT BUỘC trả lời CỰC NGẮN GỌN đúng nguyên văn câu này: '{spoken}'",
                "message": spoken,
            }

        # Trường hợp 2: Hẹn theo khoảng thời gian đếm ngược (giây / phút / giờ)
        delay_seconds = float(hours) * 3600.0 + float(minutes) * 60.0 + float(seconds)
        if delay_seconds <= 0:
            delay_seconds = 5.0
        dur_str = self.format_duration_vi(delay_seconds)
        res = await self.schedule_action(
            device_id=device_id,
            action=action,
            delay_seconds=delay_seconds,
            reason=f"Đếm ngược {dur_str}" + (f" ({rep_vi})" if rep_vi else ""),
            target_vn_time=f"({rep_vi})" if rep_vi else "",
            repeat=repeat_mode,
        )
        if not res.get("ok"):
            return res

        rep_part = f" ({rep_vi})" if rep_vi else ""
        spoken = f"Đã hẹn {dur_str} nữa{rep_part} {act_phrase}."
        return {
            "ok": True,
            "timer_id": res["timer_id"],
            "timer_ids": [res["timer_id"]],
            "both_ampm": False,
            "has_date": False,
            "repeat": repeat_mode,
            "timer_pool_count": len(self.active_timers),
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời CỰC NGẮN GỌN đúng nguyên văn câu này (TUYỆT ĐỐI KHÔNG đọc kèm giờ đồng hồ hay ngày): '{spoken}'",
            "message": spoken,
        }

    async def schedule_action(
        self,
        device_id: str,
        action: str,
        delay_seconds: float,
        reason: str = "Hẹn giờ giọng nói",
        bypass_rbac: bool = False,
        trigger_chains: bool = True,
        target_vn_time: str = "",
        repeat: str = "once",
    ) -> dict[str, Any]:
        if device_id not in self.devices and device_id not in ("all_lights", "all_devices"):
            return {"ok": False, "error": f"Thiết bị '{device_id}' không hợp lệ."}

        delay_seconds = max(1.0, min(float(delay_seconds), 365.0 * 86400.0))
        new_fire_at = time.time() + delay_seconds

        if not bypass_rbac:
            if self.current_tier >= 3 and not self.system_policies.get("tier3_can_schedule_timer", False):
                msg = "Từ chối truy cập! Cấp khách (Tầng 3) chỉ được đóng mở cố định, không có quyền hẹn giờ."
                await self.emit({"type": "rbac_blocked", "device_id": device_id, "action": action, "role": self.current_role, "reason": msg})
                return {"ok": False, "error": msg, "exact_spoken_reply": msg}

            req_role = "CHILD_GUEST" if self.system_policies.get("tier3_can_schedule_timer", False) else "MEMBER"
            allowed, msg = self.check_permission(req_role)
            if not allowed:
                await self.emit({"type": "rbac_blocked", "device_id": device_id, "action": action, "role": self.current_role, "reason": msg})
                return {"ok": False, "error": msg, "exact_spoken_reply": msg}

            # Kiểm tra bảo vệ lịch hẹn giờ của Tầng 1 Nguyễn Tuấn Anh
            conflict_err = self._check_t1_timer_conflict(device_id, new_fire_at)
            if conflict_err:
                await self.emit({"type": "rbac_blocked", "device_id": device_id, "action": action, "role": self.current_role, "reason": conflict_err})
                return {"ok": False, "error": conflict_err, "exact_spoken_reply": conflict_err}

        repeat_mode = repeat if repeat in REPEAT_VI_LABELS else "once"

        self._timer_seq += 1
        tid = f"timer_{self._timer_seq}"
        target_dev_id = "living_room_light" if device_id in ("all_lights", "all_devices") else device_id
        self.active_timers[tid] = {
            "id": tid,
            "device_id": target_dev_id,
            "raw_target": device_id,
            "action": action,
            "delay_seconds": delay_seconds,
            "fire_at": new_fire_at,
            "target_vn_time": target_vn_time,
            "repeat": repeat_mode,
            "reason": reason,
            "owner_id": self._current_user_id,
            "owner_name": self.get_current_user_name(),
            "owner_tier": self.current_tier,
        }

        async def _runner() -> None:
            try:
                cur_wait = delay_seconds
                while True:
                    await asyncio.sleep(cur_wait)
                    if repeat_mode == "once":
                        self.active_timers.pop(tid, None)
                        self._timer_tasks.pop(tid, None)
                        await self.execute_device_action(
                            device_id=device_id,
                            action=action,
                            source=f"timer ({reason})",
                            bypass_rbac=True,
                            trigger_chains=trigger_chains,
                        )
                        break

                    await self.execute_device_action(
                        device_id=device_id,
                        action=action,
                        source=f"timer lặp ({reason})",
                        bypass_rbac=True,
                        trigger_chains=trigger_chains,
                    )
                    cur_wait = REPEAT_INTERVAL_SECONDS.get(repeat_mode, 86400.0)
                    if tid in self.active_timers:
                        self.active_timers[tid]["delay_seconds"] = cur_wait
                        self.active_timers[tid]["fire_at"] = time.time() + cur_wait
                        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
                    else:
                        break
            except asyncio.CancelledError:
                self.active_timers.pop(tid, None)
                self._timer_tasks.pop(tid, None)
                raise

        self._timer_tasks[tid] = asyncio.create_task(_runner())
        await self.emit({
            "type": "timer_scheduled",
            "timer_id": tid,
            "device_id": device_id,
            "action": action,
            "delay_seconds": delay_seconds,
            "target_vn_time": target_vn_time,
            "repeat": repeat_mode,
            "reason": reason,
            "owner_id": self._current_user_id,
            "owner_tier": self.current_tier,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        act_phrase = self._action_device_phrase_vi(device_id, action)
        if target_vn_time:
            spoken = f"Đã hẹn {target_vn_time} {act_phrase}."
        else:
            dur_str = self.format_duration_vi(delay_seconds)
            spoken = f"Đã hẹn {dur_str} nữa {act_phrase}."
        return {
            "ok": True,
            "timer_id": tid,
            "repeat": repeat_mode,
            "timer_pool_count": len(self.active_timers),
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời CỰC NGẮN GỌN đúng nguyên văn câu này: '{spoken}'",
            "message": spoken,
        }

    async def update_or_cancel_timer(
        self,
        device_id: str,
        operation: str = "modify",
        new_action: str = "",
        hours: float = 0.0,
        minutes: float = 0.0,
        seconds: float = 0.0,
        vn_time_ampm: str = "",
        vn_date: str = "",
        repeat: str = "once",
    ) -> dict[str, Any]:
        if self.current_tier >= 3 and not self.system_policies.get("tier3_can_schedule_timer", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền sửa hoặc hủy hẹn giờ."
            await self.emit({"type": "rbac_blocked", "device_id": device_id, "action": "update_or_cancel_timer", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        all_matched = [
            tid
            for tid, info in self.active_timers.items()
            if device_id in ("all_devices", info["device_id"], info["raw_target"])
        ]
        if not all_matched and len(self.active_timers) == 1:
            all_matched = list(self.active_timers.keys())

        if self.current_tier == 1 or self.system_policies.get("tier2_can_override_tier1", False):
            matched_tids = all_matched
        else:
            # Tầng 2 chỉ được sửa/hủy lịch hẹn của chính mình, TUYỆT ĐỐI KHÔNG được đụng vào lịch của Tầng 1!
            own_tids = [tid for tid in all_matched if self.active_timers[tid].get("owner_id") == self._current_user_id]
            t1_tids = [tid for tid in all_matched if self.active_timers[tid].get("owner_tier", 1) == 1]
            if not own_tids and t1_tids:
                msg = "Không thể sửa hoặc hủy lịch hẹn giờ của Tầng 1 Nguyễn Tuấn Anh."
                await self.emit({"type": "rbac_blocked", "device_id": device_id, "action": "update_or_cancel_timer", "role": self.current_role, "reason": msg})
                return {"ok": False, "error": msg, "exact_spoken_reply": msg}
            if not own_tids and all_matched:
                msg = "Bạn chỉ được phép sửa hoặc hủy lịch hẹn giờ do chính bạn đặt."
                await self.emit({"type": "rbac_blocked", "device_id": device_id, "action": "update_or_cancel_timer", "role": self.current_role, "reason": msg})
                return {"ok": False, "error": msg, "exact_spoken_reply": msg}
            matched_tids = own_tids

        if not matched_tids:
            if operation == "cancel":
                return {"ok": False, "error": "Trong Bể hẹn giờ hiện không có lịch nào khớp để hủy."}
            act = new_action or "turn_off"
            return await self.schedule_timer_flexible(
                device_id=device_id if device_id in self.devices else "living_room_light",
                action=act,
                hours=hours,
                minutes=minutes,
                seconds=seconds,
                vn_time_ampm=vn_time_ampm,
                vn_date=vn_date,
                repeat=repeat,
                reason="Tạo/Sửa hẹn giờ",
            )

        old_info = self.active_timers[matched_tids[-1]]
        target_dev = old_info["raw_target"]
        target_act = new_action if new_action in ACTION_TO_STATE else old_info["action"]

        for tid in matched_tids:
            t = self._timer_tasks.pop(tid, None)
            if t:
                t.cancel()
            self.active_timers.pop(tid, None)

        if operation == "cancel":
            await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
            dev_n = self.devices.get(target_dev, {}).get("name", target_dev).lower()
            spoken = f"Đã hủy hẹn giờ {dev_n}."
            return {
                "ok": True,
                "timer_pool_count": len(self.active_timers),
                "exact_spoken_reply": spoken,
                "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn: '{spoken}'",
                "message": spoken,
            }

        return await self.schedule_timer_flexible(
            device_id=target_dev,
            action=target_act,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            vn_time_ampm=vn_time_ampm,
            vn_date=vn_date,
            repeat=repeat,
            reason="Đã sửa hẹn giờ",
        )

    # -------------------------------------------------------------------------
    # BỂ 2: ĐỔI TỪ, ĐỔI LỆNH & QUAN HỆ IF THEO BỂ RIÊNG TỪNG NGƯỜI (TẦNG 1 & TẦNG 2)
    # -------------------------------------------------------------------------
    async def set_word_mapping(
        self, custom_word: str, target_meaning: str, require_confirmation: bool = False
    ) -> dict[str, Any]:
        pol = self.system_policies
        if self.current_tier >= 3 and not pol.get("tier3_can_custom_rules", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) chỉ được gọi lệnh đóng mở cố định, không được tùy chỉnh từ ngữ."
            await self.emit({"type": "rbac_blocked", "action": "set_word_mapping", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        req_role = "CHILD_GUEST" if pol.get("tier3_can_custom_rules", False) else "MEMBER"
        allowed, msg = self.check_permission(req_role)
        if not allowed:
            await self.emit({"type": "rbac_blocked", "action": "set_word_mapping", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        w = custom_word.strip().lower()
        m = target_meaning.strip()
        if not w or not m:
            return {"ok": False, "error": "Từ mới và ý nghĩa đích không được để trống."}

        if require_confirmation and pol.get("require_rule_confirmation", True):
            ask_msg = f"Bạn muốn đổi từ '{w}' thành {m}, đúng không?"
            self.pending_rule = {
                "rule_type": "word_mapping",
                "user_id": self._current_user_id,
                "word": w,
                "meaning": m,
                "summary_vi": f"Đổi từ '{w}' -> {m}",
            }
            await self.emit({"type": "rule_confirmation_requested", "message": ask_msg, "pending_rule": self.pending_rule})
            await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
            return {
                "ok": True,
                "status": "AWAITING_RULE_CONFIRMATION",
                "exact_spoken_reply": ask_msg,
                "instruction_for_ai": f"CHƯA LƯU! BẮT BUỘC nhắc lại và hỏi người dùng đúng câu: '{ask_msg}'",
                "message": ask_msg,
            }

        self.pending_rule = None
        pool = self._get_user_pool(self._current_user_id)
        pool["word_mappings"][w] = m
        self._save_overlay()
        await self.emit({"type": "rule_created", "rule_type": "word_mapping", "user_id": self._current_user_id, "word": w, "meaning": m})
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "user_id": self._current_user_id,
            "exact_spoken_reply": f"Đã lưu đổi từ '{w}'.",
            "message": f"Đã lưu vào Bể lệnh của {self.get_current_user_name()}: '{w}' -> '{m}'.",
        }

    async def create_alias_rule(
        self,
        phrase: str,
        target_devices_csv: str,
        target_actions_csv: str,
        require_confirmation: bool = False,
    ) -> dict[str, Any]:
        pol = self.system_policies
        if self.current_tier >= 3 and not pol.get("tier3_can_custom_rules", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) chỉ được gọi lệnh đóng mở cố định, không được tùy chỉnh khẩu lệnh."
            await self.emit({"type": "rbac_blocked", "action": "create_alias_rule", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        req_role = "CHILD_GUEST" if pol.get("tier3_can_custom_rules", False) else "MEMBER"
        allowed, msg = self.check_permission(req_role)
        if not allowed:
            await self.emit({"type": "rbac_blocked", "action": "create_alias_rule", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        phrase_clean = phrase.strip().lower()
        devs = [d.strip() for d in target_devices_csv.split(",") if d.strip()]
        acts = [a.strip() for a in target_actions_csv.split(",") if a.strip()]
        if not phrase_clean or not devs or len(devs) != len(acts):
            return {"ok": False, "error": "Cú pháp đổi lệnh không hợp lệ (số thiết bị và hành động phải khớp nhau)."}

        steps = []
        step_vi_parts = []
        for d, a in zip(devs, acts):
            if d not in self.devices and d not in ("all_lights", "all_devices"):
                return {"ok": False, "error": f"Thiết bị '{d}' không tồn tại."}
            if a not in ACTION_TO_STATE:
                return {"ok": False, "error": f"Hành động '{a}' không hợp lệ."}
            steps.append({"device_id": d, "action": a})
            dname = self.devices.get(d, {}).get("name", d).lower()
            step_vi_parts.append(f"{ACTION_VI_LABEL.get(a, a).lower()} {dname}")

        step_vi = " và ".join(step_vi_parts)
        if require_confirmation and pol.get("require_rule_confirmation", True):
            ask_msg = f"Bạn muốn đổi lệnh {step_vi} thành '{phrase_clean}', đúng không?"
            self.pending_rule = {
                "rule_type": "alias",
                "user_id": self._current_user_id,
                "phrase": phrase_clean,
                "steps": steps,
                "summary_vi": f"Đổi lệnh '{phrase_clean}' -> {step_vi}",
            }
            await self.emit({"type": "rule_confirmation_requested", "message": ask_msg, "pending_rule": self.pending_rule})
            await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
            return {
                "ok": True,
                "status": "AWAITING_RULE_CONFIRMATION",
                "exact_spoken_reply": ask_msg,
                "instruction_for_ai": f"CHƯA LƯU! BẮT BUỘC nhắc lại và hỏi người dùng đúng câu: '{ask_msg}'",
                "message": ask_msg,
            }

        self.pending_rule = None
        pool = self._get_user_pool(self._current_user_id)
        pool["aliases"][phrase_clean] = steps
        self._save_overlay()
        await self.emit({
            "type": "rule_created",
            "rule_type": "alias",
            "user_id": self._current_user_id,
            "phrase": phrase_clean,
            "steps": steps,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "user_id": self._current_user_id,
            "exact_spoken_reply": f"Đã lưu lệnh '{phrase_clean}'.",
            "message": f"Đã lưu vào Bể lệnh của {self.get_current_user_name()}: '{phrase_clean}' -> {steps}.",
        }

    async def execute_alias_rule(self, phrase: str) -> dict[str, Any]:
        if self.current_tier >= 3 and not self.system_policies.get("tier3_can_custom_rules", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) chỉ được gọi các lệnh đóng mở cố định, không sử dụng khẩu lệnh tùy chỉnh."
            await self.emit({"type": "rbac_blocked", "action": "execute_alias_rule", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        phrase_clean = phrase.strip().lower()
        aliases = self.get_merged_aliases()
        matched_steps = aliases.get(phrase_clean)
        if not matched_steps:
            for k, v in aliases.items():
                if k in phrase_clean or phrase_clean in k:
                    matched_steps = v
                    phrase_clean = k
                    break
        if not matched_steps:
            return {"ok": False, "error": f"Không tìm thấy khẩu lệnh '{phrase}' trong Bể lệnh của {self.get_current_user_name()}."}

        all_results: list[dict[str, Any]] = []
        for step in matched_steps:
            res = await self.execute_device_action(
                device_id=step["device_id"],
                action=step["action"],
                source=f"khẩu lệnh '{phrase_clean}' ({self.get_current_user_name()})",
                trigger_chains=True,
            )
            all_results.extend(res.get("results", []))
        concise_reply = self._build_concise_spoken_reply(all_results)
        return {
            "ok": True,
            "results": all_results,
            "exact_spoken_reply": concise_reply,
            "instruction_for_ai": f"BẮT BUỘC trả lời CỰC NGẮN GỌN đúng nguyên văn câu này: '{concise_reply}'",
            "message": concise_reply,
        }

    def _has_cycle(self, rules: list[dict[str, Any]]) -> bool:
        adj: dict[str, set[str]] = {}
        for r in rules:
            u = r["when_device_id"]
            if r.get("then_device_id"):
                adj.setdefault(u, set()).add(r["then_device_id"])
            if r.get("else_device_id"):
                adj.setdefault(u, set()).add(r["else_device_id"])

        visited: set[str] = set()
        in_stack: set[str] = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            in_stack.add(node)
            for nxt in adj.get(node, ()):
                if nxt not in visited:
                    if dfs(nxt):
                        return True
                elif nxt in in_stack:
                    return True
            in_stack.remove(node)
            return False

        for n in list(adj.keys()):
            if n not in visited and dfs(n):
                return True
        return False

    def _check_t1_rule_conflict(self, new_rule: dict[str, Any]) -> str | None:
        """Kiểm tra xem luật IF-ELSE của Tầng 2 có mâu thuẫn hoặc vướng luật ưu tiên của Tầng 1 Nguyễn Tuấn Anh hay không."""
        if self.current_tier <= 1 or self.system_policies.get("tier2_can_override_tier1", False):
            return None
        t1_rules = list(self._get_user_pool("tuan_anh").get("if_else_rules", []))
        for r1 in t1_rules:
            # Cùng điều kiện kích hoạt và cùng thiết bị đích nhưng khác/đè hành động của Tầng 1
            if (
                r1.get("when_device_id") == new_rule["when_device_id"]
                and r1.get("when_state") == new_rule["when_state"]
                and r1.get("then_device_id") == new_rule["then_device_id"]
            ):
                return "Không thể đặt luật: Đã có luật ưu tiên của Tầng 1 Nguyễn Tuấn Anh trên cặp thiết bị này."
        if self._has_cycle(t1_rules + [new_rule]):
            return "Không thể đặt luật: Luật này gây xung đột vòng lặp với luật của Tầng 1 Nguyễn Tuấn Anh."
        return None

    async def set_if_else_rule(
        self,
        when_device_id: str,
        when_state: str,
        then_device_id: str,
        then_action: str,
        delay_seconds: float = 0.0,
        else_device_id: str = "",
        else_action: str = "",
        evaluate_now: bool = False,
        require_confirmation: bool = False,
    ) -> dict[str, Any]:
        pol = self.system_policies
        if self.current_tier >= 3 and not pol.get("tier3_can_custom_rules", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) chỉ được gọi lệnh đóng mở cố định, không được đặt luật IF-ELSE."
            await self.emit({"type": "rbac_blocked", "action": "set_if_else_rule", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        req_role = "CHILD_GUEST" if pol.get("tier3_can_custom_rules", False) else "MEMBER"
        allowed, msg = self.check_permission(req_role)
        if not allowed:
            await self.emit({"type": "rbac_blocked", "action": "set_if_else_rule", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if when_device_id not in self.devices or then_device_id not in self.devices:
            return {"ok": False, "error": "Thiết bị điều kiện IF hoặc thiết bị đích THEN không tồn tại."}

        norm_state = ACTION_TO_STATE.get(when_state.lower(), when_state.upper())
        if norm_state not in ("ON", "OFF", "OPEN", "CLOSED"):
            return {"ok": False, "error": f"Trạng thái điều kiện '{when_state}' không hợp lệ."}

        if then_action not in ACTION_TO_STATE:
            return {"ok": False, "error": f"Hành động THEN '{then_action}' không hợp lệ."}

        valid_else_dev = else_device_id if else_device_id in self.devices else ""
        valid_else_act = else_action if else_action in ACTION_TO_STATE else ""
        if not (valid_else_dev and valid_else_act):
            valid_else_dev = ""
            valid_else_act = ""

        if evaluate_now:
            curr_st = self.devices[when_device_id]["state"]
            if curr_st == norm_state:
                res = await self.execute_device_action(then_device_id, then_action, source="if_branch_now")
                return {"ok": True, "exact_spoken_reply": res["exact_spoken_reply"], "message": res["summary"]}
            if valid_else_dev and valid_else_act:
                res = await self.execute_device_action(valid_else_dev, valid_else_act, source="else_branch_now")
                return {"ok": True, "exact_spoken_reply": res["exact_spoken_reply"], "message": res["summary"]}
            return {"ok": True, "message": f"Điều kiện ({when_device_id}={norm_state}) hiện không thỏa mãn (đang là {curr_st})."}

        new_rule = {
            "id": f"ifelse_{int(time.time() * 1000)}",
            "owner_id": self._current_user_id,
            "owner_name": self.get_current_user_name(),
            "owner_tier": self.current_tier,
            "when_device_id": when_device_id,
            "when_device_name": self.devices[when_device_id]["name"],
            "when_state": norm_state,
            "delay_seconds": max(0.0, float(delay_seconds)),
            "then_device_id": then_device_id,
            "then_device_name": self.devices[then_device_id]["name"],
            "then_action": then_action,
            "else_device_id": valid_else_dev,
            "else_device_name": self.devices[valid_else_dev]["name"] if valid_else_dev else "",
            "else_action": valid_else_act,
        }

        conflict_err = self._check_t1_rule_conflict(new_rule)
        if conflict_err:
            await self.emit({"type": "rbac_blocked", "action": "set_if_else_rule", "role": self.current_role, "reason": conflict_err})
            return {"ok": False, "error": conflict_err, "exact_spoken_reply": conflict_err}

        existing = [
            r
            for r in self.get_if_else_rules(self._current_user_id)
            if not (r["when_device_id"] == when_device_id and r["when_state"] == norm_state)
        ]
        candidate = existing + [new_rule]
        if self._has_cycle(candidate):
            return {
                "ok": False,
                "error": "Từ chối tạo luật IF: Phát hiện vòng lặp vô hạn (Cycle Detected) giữa các thiết bị!",
            }

        when_verb = "mở" if norm_state in ("OPEN", "ON") else ("đóng" if norm_state == "CLOSED" else "tắt")
        then_verb = "mở" if then_action in ("open", "turn_on") and then_device_id in ("main_door", "ac") else ACTION_VI_LABEL.get(then_action, then_action).lower()
        when_n = new_rule["when_device_name"].lower()
        then_n = new_rule["then_device_name"].lower()
        else_vi = ""
        if valid_else_dev and valid_else_act:
            ev = ACTION_VI_LABEL.get(valid_else_act, valid_else_act).lower()
            else_vi = f", ngược lại thì {ev} {new_rule['else_device_name'].lower()}"

        if require_confirmation and pol.get("require_rule_confirmation", True):
            ask_msg = f"Bạn muốn đặt luật: nếu {when_verb} {when_n} thì {then_verb} {then_n}{else_vi}, đúng không?"
            self.pending_rule = {
                "rule_type": "if_else",
                "user_id": self._current_user_id,
                "rule": new_rule,
                "candidate_list": candidate,
                "summary_vi": f"Nếu {when_verb} {when_n} -> {then_verb} {then_n}{else_vi}",
            }
            await self.emit({"type": "rule_confirmation_requested", "message": ask_msg, "pending_rule": self.pending_rule})
            await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
            return {
                "ok": True,
                "status": "AWAITING_RULE_CONFIRMATION",
                "exact_spoken_reply": ask_msg,
                "instruction_for_ai": f"CHƯA LƯU LUẬT! BẮT BUỘC nhắc lại luật và hỏi xác nhận đúng câu: '{ask_msg}'",
                "message": ask_msg,
            }

        self.pending_rule = None
        pool = self._get_user_pool(self._current_user_id)
        pool["if_else_rules"] = candidate
        self._save_overlay()
        await self.emit({"type": "rule_created", "rule_type": "if_else", "user_id": self._current_user_id, "rule": new_rule})
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})

        else_desc = (
            f", NGƯỢC LẠI sẽ {valid_else_act} {new_rule['else_device_name']}"
            if valid_else_dev
            else " (1 chiều: trạng thái ngược lại giữ nguyên không đổi)"
        )
        delay_desc = f" sau {new_rule['delay_seconds']:.0f}s" if new_rule["delay_seconds"] > 0 else " ngay lập tức"
        return {
            "ok": True,
            "user_id": self._current_user_id,
            "exact_spoken_reply": "Đã lưu luật.",
            "message": (
                f"Đã lưu vào Bể lệnh của {self.get_current_user_name()}: NẾU {new_rule['when_device_name']} = {norm_state} "
                f"THÌ{delay_desc} sẽ {then_action} {new_rule['then_device_name']}{else_desc}."
            ),
        }

    async def confirm_pending_action(self, confirmed: bool = True) -> dict[str, Any]:
        """Xác nhận hoặc hủy hành động đang chờ (bao gồm cả Xét Luật mới lẫn Reset Hệ Thống)."""
        if self.current_tier >= 3 and not self.system_policies.get("tier3_can_custom_rules", False):
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền xác nhận cài đặt."
            await self.emit({"type": "rbac_blocked", "action": "confirm_pending_action", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if self.pending_rule is not None:
            pr = self.pending_rule
            self.pending_rule = None
            if not confirmed:
                await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
                return {
                    "ok": True,
                    "status": "RULE_CANCELLED",
                    "exact_spoken_reply": "Đã hủy cài đặt luật.",
                    "message": "Đã hủy cài đặt luật đang chờ.",
                }
            rtype = pr["rule_type"]
            target_uid = pr.get("user_id", self._current_user_id)
            pool = self._get_user_pool(target_uid)
            if rtype == "word_mapping":
                pool["word_mappings"][pr["word"]] = pr["meaning"]
                self._save_overlay()
                await self.emit({"type": "rule_created", "rule_type": "word_mapping", "user_id": target_uid, "word": pr["word"], "meaning": pr["meaning"]})
            elif rtype == "alias":
                pool["aliases"][pr["phrase"]] = pr["steps"]
                self._save_overlay()
                await self.emit({"type": "rule_created", "rule_type": "alias", "user_id": target_uid, "phrase": pr["phrase"], "steps": pr["steps"]})
            elif rtype == "if_else":
                pool["if_else_rules"] = pr["candidate_list"]
                self._save_overlay()
                await self.emit({"type": "rule_created", "rule_type": "if_else", "user_id": target_uid, "rule": pr["rule"]})

            await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
            return {
                "ok": True,
                "status": "RULE_CONFIRMED_AND_SAVED",
                "exact_spoken_reply": "Đã lưu luật.",
                "instruction_for_ai": "BẮT BUỘC trả lời ngắn gọn: 'Đã lưu luật.'",
                "message": f"Đã xác nhận và lưu vào Bể luật: {pr['summary_vi']}.",
            }

        if self.pending_reset_confirmation:
            return await self.confirm_factory_reset(confirmed=confirmed)

        return {
            "ok": True,
            "status": "NOTHING_PENDING",
            "exact_spoken_reply": "Hiện không có yêu cầu nào đang chờ xác nhận.",
            "message": "Không có luật hay lệnh reset nào đang chờ xác nhận.",
        }

    # -------------------------------------------------------------------------
    # 4 LOẠI RESET HỆ THỐNG CÓ XÁC NHẬN 2 BƯỚC (TẦNG 1 TOÀN HỆ THỐNG / TẦNG 2 CHỈ XÓA BỂ RIÊNG):
    # 1) 'voice'  : Reset cấp quyền giọng nói (CHỈ Tầng 1 Nguyễn Tuấn Anh được gọi)
    # 2) 'timers' : Reset đặt thời gian / hẹn giờ (Tầng 1 xóa toàn bộ; Tầng 2 chỉ xóa lịch của mình)
    # 3) 'rules'  : Reset luật động / đổi từ / đổi lệnh (Tầng 1 xóa toàn bộ; Tầng 2 chỉ xóa bể lệnh của mình)
    # 4) 'all'    : Reset tất cả (Tầng 1 reset toàn nhà; Tầng 2 chỉ xóa bể lệnh & hẹn giờ của mình)
    # -------------------------------------------------------------------------
    async def request_factory_reset(self, scope: str = "all") -> dict[str, Any]:
        """Bước 1: Khi người dùng nói 'Reset ...', chưa xóa ngay mà bật cờ chờ xác nhận đúng theo loại reset và tầng."""
        if self.current_tier >= 3:
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền thực hiện reset."
            await self.emit({"type": "rbac_blocked", "action": "request_factory_reset", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        norm_scope = normalize_reset_scope(scope)
        if self.current_tier == 2 and norm_scope == "voice":
            msg = "Chỉ Tầng 1 Nguyễn Tuấn Anh mới có quyền reset giọng nói toàn hệ thống."
            await self.emit({"type": "rbac_blocked", "action": "request_factory_reset", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if not self.system_policies.get("require_reset_confirmation", True):
            return await self.factory_reset(scope=norm_scope)

        self.pending_reset_confirmation = True
        self.pending_reset_scope = norm_scope

        if self.current_tier == 2:
            question_map = {
                "timers": "Bạn muốn reset lịch đặt thời gian riêng của bạn đúng không?",
                "rules": "Bạn muốn reset bể lệnh riêng của bạn đúng không?",
                "all": "Bạn muốn reset toàn bộ lệnh và hẹn giờ riêng của bạn đúng không?",
            }
            ask_q = question_map.get(norm_scope, "Bạn muốn reset toàn bộ cài đặt riêng của bạn đúng không?")
        else:
            question_map = {
                "voice": "Bạn muốn reset giọng nói chỉ về của bạn đúng không?",
                "timers": "Bạn muốn reset đặt thời gian đúng không?",
                "rules": "Bạn muốn reset toàn bộ luật đúng không?",
                "all": "Bạn muốn reset tất cả đúng không?",
            }
            ask_q = question_map.get(norm_scope, "Bạn muốn reset tất cả đúng không?")

        await self.emit({
            "type": "reset_confirmation_requested",
            "scope": norm_scope,
            "user_id": self._current_user_id,
            "tier": self.current_tier,
            "message": f"Đang chờ xác nhận Reset ({norm_scope}): {ask_q}",
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "status": "AWAITING_CONFIRMATION",
            "reset_scope": norm_scope,
            "exact_spoken_reply": ask_q,
            "instruction_for_ai": f"BẮT BUỘC hỏi lại người dùng đúng câu: '{ask_q}' và chờ người dùng xác nhận.",
            "message": ask_q,
        }

    async def confirm_factory_reset(self, confirmed: bool = True) -> dict[str, Any]:
        """Bước 2: Thực thi hoặc hủy Reset (hoặc Luật đang chờ) sau khi người dùng trả lời câu hỏi xác nhận."""
        if self.pending_rule is not None and not self.pending_reset_confirmation:
            return await self.confirm_pending_action(confirmed=confirmed)

        if self.current_tier >= 3:
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền xác nhận reset."
            await self.emit({"type": "rbac_blocked", "action": "confirm_factory_reset", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if not confirmed:
            self.pending_reset_confirmation = False
            self.pending_reset_scope = "all"
            await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
            return {
                "ok": True,
                "status": "CANCELLED",
                "exact_spoken_reply": "Đã hủy reset.",
                "message": "Đã hủy yêu cầu reset, giữ nguyên toàn bộ cài đặt hiện tại.",
            }

        target_scope = self.pending_reset_scope or "all"
        return await self.factory_reset(scope=target_scope)

    async def factory_reset(self, scope: str = "all") -> dict[str, Any]:
        if self.current_tier >= 3:
            msg = "Từ chối truy cập! Cấp khách (Tầng 3) không có quyền thực hiện reset."
            await self.emit({"type": "rbac_blocked", "action": "factory_reset", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        norm_scope = normalize_reset_scope(scope)
        if self.current_tier == 2 and norm_scope == "voice":
            msg = "Chỉ Tầng 1 Nguyễn Tuấn Anh mới có quyền reset giọng nói toàn hệ thống."
            await self.emit({"type": "rbac_blocked", "action": "factory_reset", "role": self.current_role, "reason": msg})
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        self.pending_reset_confirmation = False
        self.pending_reset_scope = "all"

        # TRƯỜNG HỢP TẦNG 2 (THÀNH VIÊN GIA ĐÌNH): CHỈ XÓA BỂ LỆNH & HẸN GIỜ CỦA CHÍNH MÌNH!
        if self.current_tier == 2:
            uid = self._current_user_id
            uname = self.get_current_user_name()
            if norm_scope in ("timers", "all"):
                own_tids = [
                    tid for tid, info in self.active_timers.items()
                    if info.get("owner_id") == uid
                ]
                for tid in own_tids:
                    t = self._timer_tasks.pop(tid, None)
                    if t:
                        t.cancel()
                    self.active_timers.pop(tid, None)

            if norm_scope in ("rules", "all"):
                self.pending_rule = None
                self.overlay_rules.setdefault("user_pools", {})[uid] = {
                    "word_mappings": {},
                    "aliases": {},
                    "if_else_rules": [],
                }
                self._save_overlay()

            spoken_t2 = {
                "timers": "Đã reset đặt thời gian riêng của bạn.",
                "rules": "Đã reset bể lệnh riêng của bạn.",
                "all": "Đã reset toàn bộ lệnh và hẹn giờ riêng của bạn.",
            }[norm_scope]
            detail_t2 = f"Đã xóa cài đặt ({norm_scope}) trong bể riêng của {uname}. Giữ nguyên 100% lệnh và hẹn giờ của Tầng 1 Nguyễn Tuấn Anh và người khác."
            await self.emit({
                "type": "factory_reset_completed",
                "scope": norm_scope,
                "user_id": uid,
                "tier": 2,
                "message": detail_t2,
            })
            await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
            return {
                "ok": True,
                "status": "RESET_COMPLETED",
                "reset_scope": norm_scope,
                "user_id": uid,
                "tier": 2,
                "exact_spoken_reply": spoken_t2,
                "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken_t2}'",
                "message": detail_t2,
            }

        # TRƯỜNG HỢP TẦNG 1 (NGUYỄN TUẤN ANH): RESET TOÀN HỆ THỐNG
        # 1. Reset Giọng nói & Quyền (khi scope == 'voice' hoặc 'all')
        if norm_scope in ("voice", "all"):
            self.current_role = "ADMIN"
            self.users = {k: dict(v) for k, v in DEFAULT_USERS.items()}
            self._save_overlay()
            if self.on_voice_reset is not None:
                try:
                    self.on_voice_reset()
                except Exception:
                    pass

        # 2. Reset Đặt thời gian / Bể 1 (khi scope == 'timers' hoặc 'all')
        if norm_scope in ("timers", "all"):
            for task in list(self._timer_tasks.values()):
                task.cancel()
            self._timer_tasks.clear()
            self.active_timers.clear()

        # 3. Reset Luật động / Bể 2 (khi scope == 'rules' hoặc 'all')
        if norm_scope in ("rules", "all"):
            self.pending_rule = None
            self.factory_rules = ensure_factory_file()
            saved_users = self.users
            self.overlay_rules = self._default_overlay()
            if norm_scope == "rules":
                self.overlay_rules["users"] = saved_users
            self._save_overlay()

        # 4. Đưa trạng thái 6 thiết bị về Đóng/Tắt (khi scope == 'all')
        if norm_scope == "all":
            self.devices = {
                k: dict(v, updated_at=time.time()) for k, v in DEFAULT_DEVICES.items()
            }

        spoken_map = {
            "voice": "Đã reset giọng nói chỉ về của bạn.",
            "timers": "Đã reset đặt thời gian.",
            "rules": "Đã reset toàn bộ luật về ngôn ngữ gốc.",
            "all": "Đã reset tất cả về nguyên bản.",
        }
        detail_map = {
            "voice": "Đã xóa các giọng phụ và reset quyền giọng nói chỉ về duy nhất giọng của bạn (Nguyễn Tuấn Anh - Tầng 1). Giữ nguyên Bể hẹn giờ và Bể luật.",
            "timers": "Đã xóa sạch toàn bộ lịch hẹn trong Bể 1 (Bể hẹn giờ = 0). Giữ nguyên Bể luật và quyền giọng nói.",
            "rules": "Đã xóa sạch toàn bộ từ đã đổi, lệnh đã đổi và luật IF trong Bể 2. Giữ nguyên Bể hẹn giờ và quyền giọng nói.",
            "all": "Đã reset tất cả: Giọng nói chỉ về của bạn, xóa sạch Bể hẹn giờ (0), xóa sạch Bể luật động (0) và đưa 6 thiết bị về nguyên bản.",
        }
        spoken = spoken_map[norm_scope]
        detail = detail_map[norm_scope]

        await self.emit({
            "type": "factory_reset_completed",
            "scope": norm_scope,
            "user_id": "tuan_anh",
            "tier": 1,
            "message": detail,
        })
        await self.emit({"type": "state_snapshot", "snapshot": self.get_snapshot()})
        return {
            "ok": True,
            "status": "RESET_COMPLETED",
            "reset_scope": norm_scope,
            "user_id": "tuan_anh",
            "tier": 1,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
            "message": detail,
        }

