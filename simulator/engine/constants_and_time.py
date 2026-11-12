"""Module simulator.engine.constants_and_time: Hằng số thiết bị, phân quyền 3 tầng và bộ phân tích giờ/ngày Việt Nam."""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import shutil
from typing import Any

from simulator.voice_config import (
    OWNER_DISPLAY_NAME,
    OWNER_EMAIL,
    OWNER_ID,
    ROLE_MAP,
    USER_ROLE_MAP,
)


def resolve_data_dir() -> pathlib.Path:
    repo_data = pathlib.Path(__file__).resolve().parent.parent / "data"
    if not os.environ.get("VERCEL") and os.environ.get("SMARTHOME_DATA_DIR"):
        test_data = pathlib.Path(os.environ["SMARTHOME_DATA_DIR"])
        test_data.mkdir(parents=True, exist_ok=True)
        return test_data
    if os.environ.get("VERCEL"):
        tmp_data = pathlib.Path("/tmp/smarthome_data")
        tmp_data.mkdir(parents=True, exist_ok=True)
        try:
            from simulator import durable_store

            durable_store.sync_from_durable_store(data_dir=tmp_data, only_missing=False)
        except Exception:
            pass
        if repo_data.exists():
            for src in repo_data.iterdir():
                if src.is_file():
                    dst = tmp_data / src.name
                    if not dst.exists():
                        shutil.copy2(src, dst)
        return tmp_data
    repo_data.mkdir(parents=True, exist_ok=True)
    try:
        from simulator import durable_store

        durable_store.sync_from_durable_store(data_dir=repo_data, only_missing=True)
    except Exception:
        pass
    return repo_data


DATA_DIR = resolve_data_dir()

FACTORY_FILE = DATA_DIR / "factory_default_rules.json"
OVERLAY_FILE = DATA_DIR / "custom_rules_overlay.json"
AUDIT_LOG_FILE = DATA_DIR / "system_audit_logs.jsonl"

VN_TZ = datetime.timezone(datetime.timedelta(hours=7), name="ICT")


def get_vn_now() -> datetime.datetime:
    return datetime.datetime.now(VN_TZ)


def format_vn_time_ampm(dt: datetime.datetime | None = None) -> str:
    dt = dt or get_vn_now()
    return dt.strftime("%I:%M:%S %p (GMT+7)")


HARDWARE_AUDIO_PINS: dict[str, str] = {
    "voice_mic_rx": "RX / GPIO3 (VC-02 / MAX9814 Micro Thu Âm)",
    "speaker_out": "D4 / GPIO2 (PAM8403 Loa Phát 8Ω 3W)",
}

DEFAULT_DEVICES: dict[str, dict[str, Any]] = {
    "main_door": {
        "id": "main_door",
        "name": "Cửa chính",
        "gpio": "D1 / GPIO5 (Servo PWM)",
        "type": "door",
        "state": "CLOSED",
        "min_role": "ADMIN",
        "updated_at": 0.0,
    },
    "living_room_light": {
        "id": "living_room_light",
        "name": "Đèn phòng khách",
        "gpio": "D2 / GPIO4 (Relay 1)",
        "type": "light",
        "state": "OFF",
        "min_role": "CHILD_GUEST",
        "updated_at": 0.0,
    },
    "bedroom_light": {
        "id": "bedroom_light",
        "name": "Đèn phòng ngủ",
        "gpio": "D7 / GPIO13 (Relay 2)",
        "type": "light",
        "state": "OFF",
        "min_role": "CHILD_GUEST",
        "updated_at": 0.0,
    },
    "fan": {
        "id": "fan",
        "name": "Quạt trần",
        "gpio": "D6 / GPIO12 (Relay 3)",
        "type": "fan",
        "state": "OFF",
        "min_role": "CHILD_GUEST",
        "updated_at": 0.0,
    },
    "ac": {
        "id": "ac",
        "name": "Điều hòa",
        "gpio": "D2 / GPIO4 (IR 38kHz)",
        "type": "ac",
        "state": "OFF",
        "min_role": "MEMBER",
        "updated_at": 0.0,
    },
    "alarm_siren": {
        "id": "alarm_siren",
        "name": "Còi báo động",
        "gpio": "D8 / GPIO15 (Buzzer 5V)",
        "type": "siren",
        "state": "OFF",
        "min_role": "ADMIN",
        "updated_at": 0.0,
    },
    "garden_pump": {
        "id": "garden_pump",
        "name": "Máy bơm tưới cây",
        "gpio": "D3 / GPIO0 (Relay 5V + Diode 1N4007)",
        "type": "pump",
        "state": "OFF",
        "min_role": "MEMBER",
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
    "ADMIN": f"Tầng 1 — Admin tối cao: {OWNER_DISPLAY_NAME} (Toàn quyền ưu tiên số 1)",
}

DEFAULT_USERS: dict[str, dict[str, Any]] = {
    OWNER_ID: {
        "id": OWNER_ID,
        "name": OWNER_DISPLAY_NAME,
        "email": OWNER_EMAIL,
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
        "granted_by": OWNER_ID,
        "granted_by_name": f"{OWNER_DISPLAY_NAME} (Tầng 1)",
        "granted_by_tier": 1,
        "active": True,
    },
    "thanh_vien_b": {
        "id": "thanh_vien_b",
        "name": "Thành viên B",
        "tier": 2,
        "role": "MEMBER",
        "granted_by": OWNER_ID,
        "granted_by_name": f"{OWNER_DISPLAY_NAME} (Tầng 1)",
        "granted_by_tier": 1,
        "active": True,
    },
    "khach_c": {
        "id": "khach_c",
        "name": "Khách C",
        "tier": 3,
        "role": "CHILD_GUEST",
        "granted_by": OWNER_ID,
        "granted_by_name": f"{OWNER_DISPLAY_NAME} (Tầng 1)",
        "granted_by_tier": 1,
        "active": True,
    },
    "khach_d": {
        "id": "khach_d",
        "name": "Khách D",
        "tier": 3,
        "role": "CHILD_GUEST",
        "granted_by": OWNER_ID,
        "granted_by_name": f"{OWNER_DISPLAY_NAME} (Tầng 1)",
        "granted_by_tier": 1,
        "active": True,
    },
}

DEVICE_ID_ALIASES: dict[str, str] = {
    "light_living": "living_room_light",
    "living_light": "living_room_light",
    "light_bedroom": "bedroom_light",
    "fan_bedroom": "fan",
    "fan_living": "fan",
    "ceiling_fan": "fan",
    "alarm_buzzer": "alarm_siren",
    "buzzer": "alarm_siren",
    "siren": "alarm_siren",
    "alarm": "alarm_siren",
    "door": "main_door",
    "front_door": "main_door",
    "door_main": "main_door",
    "air_conditioner": "ac",
    "ac_living": "ac",
    "ac_bedroom": "ac",
    "pump": "garden_pump",
    "water_pump": "garden_pump",
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
        m_iso = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", combined)
        if m_iso:
            year = int(m_iso.group(1))
            month = int(m_iso.group(2))
            day = int(m_iso.group(3))
            has_explicit_year = True
            cleaned_time = re.sub(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", " ", cleaned_time)
        else:
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
    FACTORY_FILE.write_bytes((json.dumps(factory_data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return factory_data
