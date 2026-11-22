"""Compound cross-device automation engine, SQLite repository, hysteresis/cooldown evaluator, and weekday helpers."""

from __future__ import annotations

import datetime
import json
import pathlib
import re
import sqlite3
import time
import uuid
from typing import Any

from simulator.auth.tier_permissions import DEVICE_LABELS_VI, can_control_device
from simulator.automation_repo import (
    SENSOR_TRIGGER_DEVICES,
    _ensure_fk_parents,
    _resolve_db,
    can_user_create_links,
    format_device_action_vi,
    invalidate_automation_cache,
    list_automation_rules,
    now_saigon,
    strip_accents,
)
from simulator.database_sqlite import _DB_LOCK, get_connection
from simulator.db_migrations import run_write_transaction
from simulator.engine.audit_logger import append_audit_log
from simulator.engine.constants_and_time import ACTION_TO_STATE, DEFAULT_DEVICES

CANONICAL_6_DEVICES: tuple[str, ...] = (
    "main_door",
    "living_room_light",
    "bedroom_light",
    "garden_pump",
    "alarm_siren",
    "speaker_amp",
)

NUMERIC_SENSOR_SOURCES: frozenset[str] = frozenset(
    {"temp_sensor", "humidity_sensor", "soil_sensor"}
)
ALL_SENSOR_SOURCES: frozenset[str] = frozenset(
    {"temp_sensor", "humidity_sensor", "soil_sensor", "sound_sensor"}
)
VALID_OPERATORS: frozenset[str] = frozenset({">", ">=", "<", "<=", "==", "!="})
VALID_LOGIC: frozenset[str] = frozenset({"AND", "OR"})
VALID_HOUSE_MODES: frozenset[str] = frozenset({"HOME", "AWAY"})

DEFAULT_HYSTERESIS: dict[str, float] = {
    "temp_sensor": 2.0,
    "humidity_sensor": 5.0,
    "soil_sensor": 5.0,
}

QUALITATIVE_SENSOR_THRESHOLDS: dict[str, dict[str, tuple[str, float]]] = {
    "temp_sensor": {"HIGH": (">=", 32.0), "LOW": ("<=", 22.0)},
    "humidity_sensor": {"HIGH": (">=", 80.0), "LOW": ("<=", 40.0)},
    "soil_sensor": {"DRY": ("<", 40.0), "WET": (">=", 70.0)},
}

WEEKDAY_LABELS_VI: dict[int, str] = {
    0: "Thứ 2",
    1: "Thứ 3",
    2: "Thứ 4",
    3: "Thứ 5",
    4: "Thứ 6",
    5: "Thứ 7",
    6: "Chủ nhật",
}

REMOVED_DEVICE_HINT_VI = (
    "Hệ thống chỉ hỗ trợ 6 thiết bị: cửa chính, đèn phòng khách, đèn phòng ngủ, "
    "máy bơm tưới cây, còi báo động và nguồn mạch loa PAM8403."
)

_COMPOUND_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS compound_automation_rules (
    rule_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    owner_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    owner_tier INTEGER NOT NULL DEFAULT 1,
    logic TEXT NOT NULL DEFAULT 'AND' CHECK (logic IN ('AND', 'OR')),
    conditions_json TEXT NOT NULL DEFAULT '[]',
    actions_json TEXT NOT NULL DEFAULT '[]',
    else_actions_json TEXT NOT NULL DEFAULT '[]',
    cooldown_seconds REAL NOT NULL DEFAULT 10.0,
    hysteresis REAL,
    enabled INTEGER NOT NULL DEFAULT 1,
    label TEXT NOT NULL DEFAULT '',
    last_fired_at REAL NOT NULL DEFAULT 0,
    last_matched INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_compound_rules_owner ON compound_automation_rules(owner_user_id, enabled);
"""


def ensure_compound_rules_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_COMPOUND_TABLE_SQL)


# =============================================================================
# WEEKDAY HELPERS (0=Mon .. 5=Sat, 6=Sun)
# =============================================================================


def parse_weekdays_vi(text: str) -> list[int]:
    """Parse Vietnamese weekday phrases into sorted unique ints [0..6] (0=Mon..6=Sun)."""
    norm = " ".join(strip_accents(str(text or "").lower()).split())
    if not norm:
        return []
    # Normalize spoken Vietnamese weekday numbers before range/list matching
    for word, digit in (
        ("hai", "2"),
        ("ba", "3"),
        ("tu", "4"),
        ("bon", "4"),
        ("nam", "5"),
        ("sau", "6"),
        ("bay", "7"),
    ):
        norm = re.sub(rf"\bthu\s+{word}\b", f"thu {digit}", norm)
    days: set[int] = set()

    if any(k in norm for k in ("cuoi tuan", "weekend")):
        days.update((5, 6))
    if any(k in norm for k in ("ngay thuong", "trong tuan", "dau tuan den cuoi tuan", "weekday", "weekdays")):
        days.update((0, 1, 2, 3, 4))

    # Weekday ranges (numeric or spoken Vietnamese days)
    for m_rng in re.finditer(
        r"(?:tu\s+)?(?:thu\s*|t)([2-7])\s*(?:den|toi|-)\s*(?:(?:thu\s*|t)([2-7])|(chu\s*nhat|cn))",
        norm,
    ):
        start_d = int(m_rng.group(1)) - 2
        end_d = 6 if m_rng.group(3) else (int(m_rng.group(2)) - 2)
        if 0 <= start_d <= end_d <= 6:
            days.update(range(start_d, end_d + 1))

    # Explicit "thu 2, 4, 6" or "thu 2 va thu 5"
    for m_list in re.finditer(
        r"\b(?:thu|t)\s*([2-7](?:\s*(?:,|va|&)\s*(?:(?:thu|t)\s*)?[2-7])*)",
        norm,
    ):
        for num_s in re.findall(r"[2-7]", m_list.group(1)):
            days.add(int(num_s) - 2)

    if re.search(r"\b(?:chu\s+nhat|cn)\b", norm):
        days.add(6)

    # English aliases for tool inputs (only match pure ASCII weekday abbreviations, never Vietnamese 'thứ'/'thử'/'thư'/'thú')
    raw_low = str(text or "").lower()
    raw_toks = set(re.findall(r"[a-zA-ZÀ-ỹ]+", raw_low))
    eng_probe = re.sub(r"\bthu\s*[2-7]\b", " ", norm)
    eng_map = {
        "mon": 0, "monday": 0,
        "tue": 1, "tuesday": 1,
        "wed": 2, "wednesday": 2,
        "thu": 3, "thursday": 3,
        "fri": 4, "friday": 4,
        "sat": 5, "saturday": 5,
        "sun": 6, "sunday": 6,
    }
    for tok in re.findall(r"[a-z]+", eng_probe):
        if tok in eng_map:
            if tok == "thu" and ("thu" not in raw_toks or re.search(r"\b(?:moi|cac|nhung|mot|mua|cai|thu)\s+thu\b", norm)):
                continue
            days.add(eng_map[tok])

    return sorted(d for d in days if 0 <= d <= 6)


def normalize_weekdays(raw: Any) -> list[int]:
    """Normalize weekdays from list[int|str], CSV string, or Vietnamese text -> sorted list[int] in 0..6."""
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple, set)):
        out: set[int] = set()
        for item in raw:
            if isinstance(item, bool):
                continue
            if isinstance(item, int):
                if 0 <= item <= 6:
                    out.add(item)
            else:
                s = str(item or "").strip()
                if s.isdigit():
                    v = int(s)
                    if 0 <= v <= 6:
                        out.add(v)
                else:
                    out.update(parse_weekdays_vi(s))
        return sorted(out)
    s = str(raw).strip()
    if not s:
        return []
    if re.fullmatch(r"\d(?:\s*,\s*\d)*", s):
        return sorted({int(p.strip()) for p in s.split(",") if 0 <= int(p.strip()) <= 6})
    return parse_weekdays_vi(s)


def weekdays_to_csv(raw: Any) -> str:
    days = normalize_weekdays(raw)
    return ",".join(str(d) for d in days)


def format_weekdays_vi(raw: Any) -> str:
    days = normalize_weekdays(raw)
    if not days:
        return ""
    if days == [0, 1, 2, 3, 4, 5, 6]:
        return "hằng ngày"
    if days == [0, 1, 2, 3, 4]:
        return "các ngày trong tuần (Thứ 2 đến Thứ 6)"
    if days == [5, 6]:
        return "cuối tuần (Thứ 7, Chủ nhật)"
    return ", ".join(WEEKDAY_LABELS_VI[d] for d in days)


# =============================================================================
# VALIDATION & NORMALIZATION
# =============================================================================


def _parse_hhmm_strict(raw: str) -> str:
    s = str(raw or "").strip()
    if ":" not in s:
        raise ValueError(f"Giờ '{raw}' phải có định dạng HH:MM (00:00 đến 23:59).")
    parts = s.split(":", 1)
    try:
        hh = int(parts[0])
        mm = int(parts[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Giờ '{raw}' không hợp lệ.") from exc
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError(f"Giờ '{raw}' phải nằm trong khoảng 00:00 đến 23:59.")
    return f"{hh:02d}:{mm:02d}"


def _hhmm_to_minutes(hhmm: str) -> int:
    hh, mm = hhmm.split(":", 1)
    return int(hh) * 60 + int(mm)


def normalize_and_validate_condition(cond: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(cond, dict):
        raise ValueError("Mỗi điều kiện phải là một đối tượng hợp lệ.")
    source = str(cond.get("source") or cond.get("device_id") or cond.get("sensor") or "").strip().lower()
    if not source:
        raise ValueError("Thiếu nguồn điều kiện (thiết bị, cảm biến, khung giờ hoặc chế độ nhà).")

    # Normalize common aliases
    alias_map = {
        "temperature": "temp_sensor",
        "temp": "temp_sensor",
        "dht11_temp": "temp_sensor",
        "humidity": "humidity_sensor",
        "air_humidity": "humidity_sensor",
        "dht11_humidity": "humidity_sensor",
        "soil": "soil_sensor",
        "soil_moisture": "soil_sensor",
        "sound": "sound_sensor",
        "ky037": "sound_sensor",
        "time": "time_window",
        "schedule_window": "time_window",
        "presence": "house_mode",
        "mode": "house_mode",
    }
    source = alias_map.get(source, source)

    if source in NUMERIC_SENSOR_SOURCES:
        op_raw = str(cond.get("operator") or cond.get("op") or "").strip()
        val_raw = cond.get("value")
        state_raw = str(cond.get("state") or "").strip().upper()
        hyst_raw = cond.get("hysteresis")
        hyst_val: float | None = None
        if hyst_raw is not None and str(hyst_raw).strip() != "":
            try:
                hyst_val = max(0.0, float(hyst_raw))
            except (TypeError, ValueError) as exc:
                raise ValueError("Giá trị độ trễ ngưỡng (hysteresis) không hợp lệ.") from exc

        if op_raw or (val_raw is not None and str(val_raw).strip() != ""):
            if op_raw not in VALID_OPERATORS:
                raise ValueError(f"Toán tử so sánh '{op_raw}' không hợp lệ (chỉ hỗ trợ >, >=, <, <=, ==, !=).")
            try:
                num_val = float(val_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Ngưỡng số '{val_raw}' không hợp lệ cho {source}.") from exc
            out: dict[str, Any] = {
                "source": source,
                "operator": op_raw,
                "value": num_val,
                "hysteresis": hyst_val if hyst_val is not None else DEFAULT_HYSTERESIS[source],
            }
            return out

        allowed_states = SENSOR_TRIGGER_DEVICES[source]["states"]
        if state_raw not in allowed_states:
            raise ValueError(
                f"Điều kiện cho {SENSOR_TRIGGER_DEVICES[source]['name']} cần ngưỡng số (operator + value) "
                f"hoặc trạng thái hợp lệ ({', '.join(allowed_states)})."
            )
        return {
            "source": source,
            "state": state_raw,
            "hysteresis": hyst_val if hyst_val is not None else DEFAULT_HYSTERESIS[source],
        }

    if source == "sound_sensor":
        st = str(cond.get("state") or "LOUD").strip().upper()
        if st in ("TRUE", "1", "DETECTED", "ON"):
            st = "LOUD"
        elif st in ("FALSE", "0", "NONE", "OFF"):
            st = "QUIET"
        if st not in ("LOUD", "QUIET"):
            raise ValueError("Cảm biến âm thanh KY-037 chỉ nhận trạng thái LOUD hoặc QUIET.")
        return {"source": "sound_sensor", "state": st}

    if source == "time_window":
        start_hhmm = _parse_hhmm_strict(str(cond.get("start_hhmm") or cond.get("start") or ""))
        end_hhmm = _parse_hhmm_strict(str(cond.get("end_hhmm") or cond.get("end") or ""))
        weekdays = normalize_weekdays(cond.get("weekdays"))
        out_tw: dict[str, Any] = {
            "source": "time_window",
            "start_hhmm": start_hhmm,
            "end_hhmm": end_hhmm,
        }
        if weekdays:
            out_tw["weekdays"] = weekdays
        return out_tw

    if source == "house_mode":
        st = str(cond.get("state") or cond.get("value") or "").strip().upper()
        if st in ("VANG_NHA", "VANG", "OUT", "ABSENT"):
            st = "AWAY"
        elif st in ("O_NHA", "IN", "PRESENT"):
            st = "HOME"
        if st not in VALID_HOUSE_MODES:
            raise ValueError("Chế độ nhà chỉ hỗ trợ HOME (ở nhà) hoặc AWAY (vắng nhà).")
        return {"source": "house_mode", "state": st}

    if source in CANONICAL_6_DEVICES:
        raw_st = str(cond.get("state") or cond.get("value") or "").strip()
        norm_st = ACTION_TO_STATE.get(raw_st.lower(), raw_st.upper())
        if source == "main_door":
            if norm_st == "ON":
                norm_st = "OPEN"
            elif norm_st == "OFF":
                norm_st = "CLOSED"
            if norm_st not in ("OPEN", "CLOSED"):
                raise ValueError("Trạng thái cửa chính chỉ hỗ trợ OPEN hoặc CLOSED.")
        else:
            if norm_st == "OPEN":
                norm_st = "ON"
            elif norm_st == "CLOSED":
                norm_st = "OFF"
            if norm_st not in ("ON", "OFF"):
                raise ValueError(f"Trạng thái của {DEVICE_LABELS_VI.get(source, source)} chỉ hỗ trợ ON hoặc OFF.")
        return {"source": source, "state": norm_st}

    raise ValueError(f"Nguồn điều kiện '{source}' không được hỗ trợ. {REMOVED_DEVICE_HINT_VI}")


def normalize_and_validate_actions(
    actions: list[dict[str, Any]] | None,
    *,
    allow_empty: bool = False,
    actor_tier: int | None = None,
) -> list[dict[str, str]]:
    if not actions:
        if allow_empty:
            return []
        raise ValueError("Luật tự động phải có ít nhất 1 hành động thiết bị hợp lệ.")
    if not isinstance(actions, list):
        raise ValueError("Danh sách hành động không hợp lệ.")

    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in actions:
        if not isinstance(item, dict):
            continue
        did = str(item.get("device_id") or "").strip().lower()
        act = str(item.get("action") or "").strip().lower()
        if act in ("on", "bat"):
            act = "turn_on"
        elif act in ("off", "tat"):
            act = "turn_off"
        elif act in ("mo",):
            act = "open"
        elif act in ("dong", "khoa"):
            act = "close"

        if act not in ACTION_TO_STATE:
            raise ValueError(f"Hành động '{act}' không hợp lệ (chỉ hỗ trợ open, close, turn_on, turn_off).")

        if did == "all_lights":
            exp_act = "turn_on" if act in ("open", "turn_on") else "turn_off"
            pairs = [("living_room_light", exp_act), ("bedroom_light", exp_act)]
        elif did == "all_devices":
            if act in ("close", "turn_off"):
                pairs = [
                    ("living_room_light", "turn_off"),
                    ("bedroom_light", "turn_off"),
                    ("garden_pump", "turn_off"),
                    ("speaker_amp", "turn_off"),
                    ("alarm_siren", "turn_off"),
                    ("main_door", "close"),
                ]
            else:
                pairs = [
                    ("living_room_light", "turn_on"),
                    ("bedroom_light", "turn_on"),
                    ("speaker_amp", "turn_on"),
                ]
        elif did in CANONICAL_6_DEVICES:
            fixed_act = (
                ("open" if act in ("open", "turn_on") else "close")
                if did == "main_door"
                else ("turn_on" if act in ("open", "turn_on") else "turn_off")
            )
            pairs = [(did, fixed_act)]
        else:
            raise ValueError(f"Thiết bị '{did}' không tồn tại trong hệ thống. {REMOVED_DEVICE_HINT_VI}")

        for pd, pa in pairs:
            if actor_tier is not None and not can_control_device(int(actor_tier), pd):
                dname = DEVICE_LABELS_VI.get(pd, pd)
                raise PermissionError(f"Từ chối: Cấp {actor_tier} không có quyền điều khiển {dname}.")
            if (pd, pa) not in seen:
                seen.add((pd, pa))
                out.append({"device_id": pd, "action": pa})

    if not out and not allow_empty:
        raise ValueError("Luật tự động phải có ít nhất 1 hành động thiết bị hợp lệ.")
    return out


def _edges_have_cycle(edges: list[tuple[str, str]]) -> bool:
    adj: dict[str, set[str]] = {}
    for src, dst in edges:
        if src and dst:
            adj.setdefault(src, set()).add(dst)
    visited: set[str] = set()
    in_stack: set[str] = set()

    def _dfs(node: str) -> bool:
        visited.add(node)
        in_stack.add(node)
        for nxt in adj.get(node, ()):
            if nxt == node:
                return True
            if nxt not in visited:
                if _dfs(nxt):
                    return True
            elif nxt in in_stack:
                return True
        in_stack.remove(node)
        return False

    return any(n not in visited and _dfs(n) for n in list(adj.keys()))


def _extract_device_edges(conditions: list[dict[str, Any]], actions: list[dict[str, str]], else_actions: list[dict[str, str]]) -> list[tuple[str, str]]:
    cond_devs = [c["source"] for c in conditions if c.get("source") in CANONICAL_6_DEVICES]
    act_devs = [a["device_id"] for a in (actions or []) if a.get("device_id") in CANONICAL_6_DEVICES]
    else_devs = [a["device_id"] for a in (else_actions or []) if a.get("device_id") in CANONICAL_6_DEVICES]
    edges: list[tuple[str, str]] = []
    for src in cond_devs:
        for dst in act_devs + else_devs:
            edges.append((src, dst))
    return edges


def format_condition_vi(cond: dict[str, Any]) -> str:
    src = str(cond.get("source") or "")
    op_vi = {
        ">": "trên",
        ">=": "từ",
        "<": "dưới",
        "<=": "tối đa",
        "==": "bằng",
        "!=": "khác",
    }
    if src == "temp_sensor":
        if "operator" in cond and "value" in cond:
            op = str(cond["operator"])
            val = float(cond["value"])
            v_str = f"{val:g}"
            if op == ">=":
                return f"nhiệt độ từ {v_str}°C trở lên"
            return f"nhiệt độ {op_vi.get(op, op)} {v_str}°C"
        return "nhiệt độ cao" if str(cond.get("state")) == "HIGH" else "nhiệt độ thấp"

    if src == "humidity_sensor":
        if "operator" in cond and "value" in cond:
            op = str(cond["operator"])
            val = float(cond["value"])
            v_str = f"{val:g}"
            if op == ">=":
                return f"độ ẩm không khí từ {v_str}% trở lên"
            return f"độ ẩm không khí {op_vi.get(op, op)} {v_str}%"
        return "độ ẩm không khí cao" if str(cond.get("state")) == "HIGH" else "độ ẩm không khí thấp"

    if src == "soil_sensor":
        if "operator" in cond and "value" in cond:
            op = str(cond["operator"])
            val = float(cond["value"])
            v_str = f"{val:g}"
            if op == ">=":
                return f"độ ẩm đất từ {v_str}% trở lên"
            return f"độ ẩm đất {op_vi.get(op, op)} {v_str}%"
        return "đất khô" if str(cond.get("state")) == "DRY" else "đất ẩm"

    if src == "sound_sensor":
        return "có tiếng động lớn" if str(cond.get("state")) == "LOUD" else "yên tĩnh"

    if src == "time_window":
        tw = f"trong khung giờ {cond['start_hhmm']}–{cond['end_hhmm']}"
        if cond.get("weekdays"):
            tw += f" ({format_weekdays_vi(cond['weekdays'])})"
        return tw

    if src == "house_mode":
        return "ở chế độ vắng nhà" if str(cond.get("state")) == "AWAY" else "ở chế độ ở nhà"

    if src in CANONICAL_6_DEVICES:
        dname = DEVICE_LABELS_VI.get(src, src).lower()
        st = str(cond.get("state") or "").upper()
        if src == "main_door":
            st_vi = "đang mở" if st == "OPEN" else "đang đóng"
        else:
            st_vi = "đang bật" if st == "ON" else "đang tắt"
        return f"{dname} {st_vi}"

    return str(cond)


def format_compound_rule_vi(
    logic: str,
    conditions: list[dict[str, Any]],
    actions: list[dict[str, str]],
    else_actions: list[dict[str, str]] | None = None,
) -> str:
    """Format a compound rule into clear, natural Vietnamese for confirmation read-back and UI labels."""
    joiner = " và " if str(logic or "AND").upper() == "AND" else " hoặc "
    cond_txt = joiner.join(format_condition_vi(c) for c in conditions)
    act_txt = " và ".join(format_device_action_vi(a["device_id"], a["action"]).lower() for a in actions)
    out = f"Khi {cond_txt} thì {act_txt}"
    if else_actions:
        else_txt = " và ".join(format_device_action_vi(a["device_id"], a["action"]).lower() for a in else_actions)
        out += f", ngược lại {else_txt}"
    return out


def validate_compound_rule_input(
    *,
    owner_user_id: str,
    owner_tier: int,
    logic: str = "AND",
    conditions: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    else_actions: list[dict[str, Any]] | None = None,
    cooldown_seconds: float = 10.0,
    hysteresis: float | None = None,
    exclude_rule_id: str | None = None,
    engine: Any = None,
    db_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    tier = int(owner_tier or 3)
    if tier >= 3:
        raise PermissionError("Khách chỉ được bật tắt thiết bị thôi ạ.")
    if tier == 2 and not can_user_create_links(owner_user_id, tier, engine=engine, db_path=db_path):
        raise PermissionError("Cấp 2 chưa được Chủ nhà cấp quyền tạo luật tự động ạ.")

    norm_logic = str(logic or "AND").strip().upper()
    if norm_logic not in VALID_LOGIC:
        raise ValueError("Logic kết hợp điều kiện chỉ hỗ trợ AND hoặc OR.")
    if not isinstance(conditions, list) or not conditions:
        raise ValueError("Luật tự động phải có ít nhất 1 điều kiện.")

    norm_conds = [normalize_and_validate_condition(c) for c in conditions]
    norm_acts = normalize_and_validate_actions(actions, allow_empty=False, actor_tier=tier)
    norm_else = normalize_and_validate_actions(else_actions or [], allow_empty=True, actor_tier=tier)

    try:
        cd = float(cooldown_seconds if cooldown_seconds is not None else 10.0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Thời gian nghỉ (cooldown) không hợp lệ.") from exc
    if cd < 0:
        raise ValueError("Thời gian nghỉ (cooldown) không được âm.")

    norm_hyst: float | None = None
    if hysteresis is not None and str(hysteresis).strip() != "":
        try:
            norm_hyst = float(hysteresis)
        except (TypeError, ValueError) as exc:
            raise ValueError("Giá trị hysteresis không hợp lệ.") from exc
        if norm_hyst < 0:
            raise ValueError("Giá trị hysteresis không được âm.")

    # Direct self-loop check first
    candidate_edges = _extract_device_edges(norm_conds, norm_acts, norm_else)
    for src, dst in candidate_edges:
        if src == dst:
            raise ValueError("Từ chối tạo luật vì thiết bị tự kích hoạt chính nó (vòng lặp vô hạn).")

    # Global DFS cycle check across enabled legacy simple rules + enabled compound rules
    all_edges: list[tuple[str, str]] = []
    for simple_r in list_automation_rules(include_disabled=False, db_path=db_path):
        w = str(simple_r.get("when_device_id") or "")
        t = str(simple_r.get("then_device_id") or "")
        e = str(simple_r.get("else_device_id") or "")
        if w in CANONICAL_6_DEVICES and t in CANONICAL_6_DEVICES:
            all_edges.append((w, t))
        if w in CANONICAL_6_DEVICES and e in CANONICAL_6_DEVICES:
            all_edges.append((w, e))

    for comp_r in list_compound_rules(include_disabled=False, db_path=db_path):
        if exclude_rule_id and str(comp_r.get("rule_id")) == str(exclude_rule_id):
            continue
        all_edges.extend(
            _extract_device_edges(
                comp_r.get("conditions") or [],
                comp_r.get("actions") or [],
                comp_r.get("else_actions") or [],
            )
        )

    all_edges.extend(candidate_edges)
    if _edges_have_cycle(all_edges):
        raise ValueError("Từ chối tạo luật tự động vì phát hiện vòng lặp giữa các thiết bị.")

    return {
        "logic": norm_logic,
        "conditions": norm_conds,
        "actions": norm_acts,
        "else_actions": norm_else,
        "cooldown_seconds": cd,
        "hysteresis": norm_hyst,
    }


# =============================================================================
# SQLITE REPOSITORY
# =============================================================================


def _row_to_compound_rule(r: sqlite3.Row) -> dict[str, Any]:
    try:
        conds = json.loads(str(r["conditions_json"] or "[]"))
    except Exception:
        conds = []
    try:
        acts = json.loads(str(r["actions_json"] or "[]"))
    except Exception:
        acts = []
    try:
        else_acts = json.loads(str(r["else_actions_json"] or "[]"))
    except Exception:
        else_acts = []
    logic = str(r["logic"] or "AND").upper()
    lbl = str(r["label"] or "").strip() or format_compound_rule_vi(logic, conds, acts, else_acts)
    return {
        "id": str(r["rule_id"]),
        "rule_id": str(r["rule_id"]),
        "is_compound": True,
        "name": str(r["name"] or ""),
        "owner_id": str(r["owner_user_id"]),
        "owner_user_id": str(r["owner_user_id"]),
        "owner_name": str(r["owner_name"]),
        "owner_tier": int(r["owner_tier"] or 1),
        "logic": logic,
        "conditions": conds if isinstance(conds, list) else [],
        "actions": acts if isinstance(acts, list) else [],
        "else_actions": else_acts if isinstance(else_acts, list) else [],
        "cooldown_seconds": float(r["cooldown_seconds"] if r["cooldown_seconds"] is not None else 10.0),
        "hysteresis": float(r["hysteresis"]) if r["hysteresis"] is not None else None,
        "enabled": bool(int(r["enabled"] or 0)),
        "label": lbl,
        "last_fired_at": float(r["last_fired_at"] or 0.0),
        "last_matched": bool(int(r["last_matched"] or 0)),
        "created_at": float(r["created_at"] or 0.0),
        "updated_at": float(r["updated_at"] or 0.0),
    }


def list_compound_rules(
    *,
    include_disabled: bool = True,
    owner_user_id: str | None = None,
    db_path: pathlib.Path | None = None,
) -> list[dict[str, Any]]:
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            ensure_compound_rules_table(conn)
            sql = """
                SELECT c.rule_id, c.name, c.owner_user_id,
                       COALESCE(u.full_name, c.owner_user_id) AS owner_name,
                       c.owner_tier, c.logic, c.conditions_json, c.actions_json,
                       c.else_actions_json, c.cooldown_seconds, c.hysteresis,
                       c.enabled, c.label, c.last_fired_at, c.last_matched,
                       c.created_at, c.updated_at
                FROM compound_automation_rules c
                LEFT JOIN users u ON u.user_id = c.owner_user_id
            """
            clauses: list[str] = []
            params: list[Any] = []
            if not include_disabled:
                clauses.append("c.enabled = 1")
            if owner_user_id is not None and str(owner_user_id).strip():
                clauses.append("c.owner_user_id = ?")
                params.append(str(owner_user_id).strip())
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY c.owner_tier ASC, c.created_at DESC"
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [_row_to_compound_rule(r) for r in rows]
        finally:
            conn.close()


def get_compound_rule(rule_id: str, *, db_path: pathlib.Path | None = None) -> dict[str, Any] | None:
    rid = str(rule_id or "").strip()
    if not rid:
        return None
    for r in list_compound_rules(include_disabled=True, db_path=db_path):
        if r["rule_id"] == rid:
            return r
    return None


def create_compound_rule(
    *,
    owner_user_id: str,
    owner_tier: int,
    logic: str = "AND",
    conditions: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    else_actions: list[dict[str, Any]] | None = None,
    cooldown_seconds: float = 10.0,
    hysteresis: float | None = None,
    name: str = "",
    label: str = "",
    enabled: bool = True,
    owner_name: str = "",
    rule_id: str | None = None,
    engine: Any = None,
    db_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    validated = validate_compound_rule_input(
        owner_user_id=owner_user_id,
        owner_tier=owner_tier,
        logic=logic,
        conditions=conditions,
        actions=actions,
        else_actions=else_actions,
        cooldown_seconds=cooldown_seconds,
        hysteresis=hysteresis,
        engine=engine,
        db_path=db_path,
    )
    rid = rule_id or f"crule_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    now_ts = time.time()
    clean_label = str(label or "").strip() or format_compound_rule_vi(
        validated["logic"],
        validated["conditions"],
        validated["actions"],
        validated["else_actions"],
    )
    clean_name = str(name or "").strip() or clean_label[:180]
    safe_tier = int(owner_tier if owner_tier in (1, 2, 3) else 1)

    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            ensure_compound_rules_table(conn)

            def _tx(c: sqlite3.Connection) -> None:
                uid = _ensure_fk_parents(
                    c, owner_user_id=owner_user_id, owner_tier=safe_tier, owner_name=owner_name
                )
                c.execute(
                    """
                    INSERT INTO compound_automation_rules (
                        rule_id, name, owner_user_id, owner_tier, logic,
                        conditions_json, actions_json, else_actions_json,
                        cooldown_seconds, hysteresis, enabled, label,
                        last_fired_at, last_matched, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
                    """,
                    (
                        rid,
                        clean_name,
                        uid,
                        safe_tier,
                        validated["logic"],
                        json.dumps(validated["conditions"], ensure_ascii=False),
                        json.dumps(validated["actions"], ensure_ascii=False),
                        json.dumps(validated["else_actions"], ensure_ascii=False),
                        validated["cooldown_seconds"],
                        validated["hysteresis"],
                        1 if enabled else 0,
                        clean_label,
                        now_ts,
                        now_ts,
                    ),
                )

            run_write_transaction(conn, _tx)
        finally:
            conn.close()
    invalidate_automation_cache(db_path)
    created = get_compound_rule(rid, db_path=db_path)
    assert created is not None
    return created


def update_compound_rule(
    rule_id: str,
    *,
    name: str | None = None,
    logic: str | None = None,
    conditions: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]] | None = None,
    else_actions: list[dict[str, Any]] | None = None,
    cooldown_seconds: float | None = None,
    hysteresis: float | None = None,
    enabled: bool | None = None,
    label: str | None = None,
    actor_user_id: str | None = None,
    actor_tier: int | None = None,
    engine: Any = None,
    db_path: pathlib.Path | None = None,
) -> dict[str, Any] | None:
    existing = get_compound_rule(rule_id, db_path=db_path)
    if existing is None:
        return None

    eff_tier = int(actor_tier if actor_tier is not None else existing["owner_tier"])
    eff_uid = str(actor_user_id or existing["owner_user_id"])
    if eff_tier >= 3:
        raise PermissionError("Khách chỉ được bật tắt thiết bị thôi ạ.")
    if eff_tier > 1 and existing["owner_user_id"] != eff_uid:
        raise PermissionError("Bạn chỉ có quyền sửa luật tự động của chính mình.")

    cand_logic = logic if logic is not None else existing["logic"]
    cand_conds = conditions if conditions is not None else existing["conditions"]
    cand_acts = actions if actions is not None else existing["actions"]
    cand_else = else_actions if else_actions is not None else existing["else_actions"]
    cand_cd = cooldown_seconds if cooldown_seconds is not None else existing["cooldown_seconds"]
    cand_hyst = hysteresis if hysteresis is not None else existing["hysteresis"]
    cand_enabled = bool(enabled) if enabled is not None else bool(existing["enabled"])

    validated = validate_compound_rule_input(
        owner_user_id=existing["owner_user_id"],
        owner_tier=eff_tier,
        logic=cand_logic,
        conditions=cand_conds,
        actions=cand_acts,
        else_actions=cand_else,
        cooldown_seconds=cand_cd,
        hysteresis=cand_hyst,
        exclude_rule_id=rule_id,
        engine=engine,
        db_path=db_path,
    )

    new_label = (
        str(label).strip()
        if label is not None and str(label).strip()
        else format_compound_rule_vi(
            validated["logic"],
            validated["conditions"],
            validated["actions"],
            validated["else_actions"],
        )
    )
    new_name = str(name).strip() if name is not None and str(name).strip() else (existing["name"] or new_label[:80])
    now_ts = time.time()
    reset_match = (conditions is not None or logic is not None or hysteresis is not None)

    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            ensure_compound_rules_table(conn)

            def _tx(c: sqlite3.Connection) -> None:
                c.execute(
                    """
                    UPDATE compound_automation_rules
                    SET name = ?, logic = ?, conditions_json = ?, actions_json = ?,
                        else_actions_json = ?, cooldown_seconds = ?, hysteresis = ?,
                        enabled = ?, label = ?, last_matched = ?, updated_at = ?
                    WHERE rule_id = ?
                    """,
                    (
                        new_name,
                        validated["logic"],
                        json.dumps(validated["conditions"], ensure_ascii=False),
                        json.dumps(validated["actions"], ensure_ascii=False),
                        json.dumps(validated["else_actions"], ensure_ascii=False),
                        validated["cooldown_seconds"],
                        validated["hysteresis"],
                        1 if cand_enabled else 0,
                        new_label,
                        0 if reset_match else (1 if existing["last_matched"] else 0),
                        now_ts,
                        str(rule_id),
                    ),
                )

            run_write_transaction(conn, _tx)
        finally:
            conn.close()
    invalidate_automation_cache(db_path)
    return get_compound_rule(rule_id, db_path=db_path)


def toggle_compound_rule(
    rule_id: str,
    enabled: bool,
    *,
    db_path: pathlib.Path | None = None,
) -> dict[str, Any] | None:
    existing = get_compound_rule(rule_id, db_path=db_path)
    if existing is None:
        return None
    if enabled:
        validate_compound_rule_input(
            owner_user_id=str(existing.get("owner_user_id") or "tuan_anh"),
            owner_tier=int(existing.get("owner_tier") or 1),
            logic=str(existing.get("logic") or "AND"),
            conditions=list(existing.get("conditions") or []),
            actions=list(existing.get("actions") or []),
            else_actions=list(existing.get("else_actions") or []),
            cooldown_seconds=float(existing.get("cooldown_seconds") or 10.0),
            hysteresis=existing.get("hysteresis"),
            exclude_rule_id=str(rule_id),
            db_path=db_path,
        )
    now_ts = time.time()
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            ensure_compound_rules_table(conn)

            def _tx(c: sqlite3.Connection) -> None:
                c.execute(
                    """
                    UPDATE compound_automation_rules
                    SET enabled = ?, last_matched = CASE WHEN ? = 0 THEN 0 ELSE last_matched END, updated_at = ?
                    WHERE rule_id = ?
                    """,
                    (1 if enabled else 0, 1 if enabled else 0, now_ts, str(rule_id)),
                )

            run_write_transaction(conn, _tx)
        finally:
            conn.close()
    invalidate_automation_cache(db_path)
    return get_compound_rule(rule_id, db_path=db_path)


def delete_compound_rule(rule_id: str, *, db_path: pathlib.Path | None = None) -> bool:
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            ensure_compound_rules_table(conn)

            def _tx(c: sqlite3.Connection) -> int:
                cur = c.execute("DELETE FROM compound_automation_rules WHERE rule_id = ?", (str(rule_id),))
                return int(cur.rowcount or 0)

            deleted = run_write_transaction(conn, _tx) > 0
        finally:
            conn.close()
    if deleted:
        invalidate_automation_cache(db_path)
    return deleted


def clear_compound_rules_scoped(
    *,
    target_owner_id: str | None = None,
    clear_all: bool = False,
    db_path: pathlib.Path | None = None,
) -> int:
    uid = str(target_owner_id or "").strip()
    if not clear_all and not uid:
        return 0
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            ensure_compound_rules_table(conn)

            def _tx(c: sqlite3.Connection) -> int:
                if clear_all:
                    cur = c.execute("DELETE FROM compound_automation_rules")
                    return int(cur.rowcount or 0)
                cur = c.execute("DELETE FROM compound_automation_rules WHERE owner_user_id = ?", (uid,))
                return int(cur.rowcount or 0)

            removed = run_write_transaction(conn, _tx)
        finally:
            conn.close()
    if removed:
        invalidate_automation_cache(db_path)
    return removed


def _update_compound_rule_runtime(
    rule_id: str,
    *,
    last_fired_at: float | None = None,
    last_matched: bool | None = None,
    db_path: pathlib.Path | None = None,
) -> None:
    with _DB_LOCK:
        target = _resolve_db(db_path)
        conn = get_connection(target)
        try:
            ensure_compound_rules_table(conn)

            def _tx(c: sqlite3.Connection) -> None:
                if last_fired_at is not None and last_matched is not None:
                    c.execute(
                        "UPDATE compound_automation_rules SET last_fired_at = ?, last_matched = ? WHERE rule_id = ?",
                        (float(last_fired_at), 1 if last_matched else 0, str(rule_id)),
                    )
                elif last_matched is not None:
                    c.execute(
                        "UPDATE compound_automation_rules SET last_matched = ? WHERE rule_id = ?",
                        (1 if last_matched else 0, str(rule_id)),
                    )
                elif last_fired_at is not None:
                    c.execute(
                        "UPDATE compound_automation_rules SET last_fired_at = ? WHERE rule_id = ?",
                        (float(last_fired_at), str(rule_id)),
                    )

            run_write_transaction(conn, _tx)
        finally:
            conn.close()


# =============================================================================
# EVALUATION ENGINE (HYSTERESIS + COOLDOWN + LOOP GUARD)
# =============================================================================


def _compare_numeric_with_hysteresis(
    val: float,
    operator: str,
    threshold: float,
    hysteresis: float,
    *,
    prev_matched: bool,
) -> bool:
    h = max(0.0, float(hysteresis or 0.0)) if prev_matched else 0.0
    if operator == ">":
        return val > (threshold - h)
    if operator == ">=":
        return val >= (threshold - h)
    if operator == "<":
        return val < (threshold + h)
    if operator == "<=":
        return val <= (threshold + h)
    if operator == "==":
        return abs(val - threshold) <= (h if prev_matched else 1e-6)
    if operator == "!=":
        return abs(val - threshold) > 1e-6
    return False


def _read_sensor_numeric(source: str, engine: Any) -> float | None:
    mqtt = getattr(engine, "mqtt_bridge", None)
    if mqtt is None:
        return None
    if source == "temp_sensor":
        val = (getattr(mqtt, "dht11_telemetry", None) or {}).get("temp_c")
        return float(val) if val is not None else None
    if source == "humidity_sensor":
        val = (getattr(mqtt, "dht11_telemetry", None) or {}).get("humidity_pct")
        return float(val) if val is not None else None
    if source == "soil_sensor":
        val = (getattr(mqtt, "soil_moisture_telemetry", None) or {}).get("soil_moisture_pct")
        return float(val) if val is not None else None
    return None


def evaluate_condition(
    cond: dict[str, Any],
    engine: Any,
    *,
    now_dt: datetime.datetime,
    prev_matched: bool = False,
    rule_hysteresis: float | None = None,
) -> bool:
    src = str(cond.get("source") or "")

    if src in NUMERIC_SENSOR_SOURCES:
        val = _read_sensor_numeric(src, engine)
        if val is None:
            return False
        hyst = (
            float(rule_hysteresis)
            if rule_hysteresis is not None
            else float(cond.get("hysteresis") if cond.get("hysteresis") is not None else DEFAULT_HYSTERESIS[src])
        )
        if "operator" in cond and "value" in cond:
            return _compare_numeric_with_hysteresis(
                val,
                str(cond["operator"]),
                float(cond["value"]),
                hyst,
                prev_matched=prev_matched,
            )
        st = str(cond.get("state") or "").upper()
        q_spec = QUALITATIVE_SENSOR_THRESHOLDS.get(src, {}).get(st)
        if q_spec is None:
            return False
        q_op, q_thresh = q_spec
        return _compare_numeric_with_hysteresis(
            val,
            q_op,
            q_thresh,
            hyst,
            prev_matched=prev_matched,
        )

    if src == "sound_sensor":
        mqtt = getattr(engine, "mqtt_bridge", None)
        snd = (getattr(mqtt, "sound_telemetry", None) or {}) if mqtt is not None else {}
        is_loud = bool(snd.get("sound_detected", False))
        expected = str(cond.get("state") or "LOUD").upper()
        return is_loud if expected == "LOUD" else (not is_loud)

    if src == "time_window":
        start_m = _hhmm_to_minutes(str(cond.get("start_hhmm") or "00:00"))
        end_m = _hhmm_to_minutes(str(cond.get("end_hhmm") or "23:59"))
        cur_m = now_dt.hour * 60 + now_dt.minute
        weekdays = normalize_weekdays(cond.get("weekdays"))
        if weekdays and now_dt.weekday() not in weekdays:
            return False
        if start_m <= end_m:
            return start_m <= cur_m <= end_m
        # Midnight wrap-around (e.g., 18:00 -> 06:00)
        return cur_m >= start_m or cur_m <= end_m

    if src == "house_mode":
        root = getattr(engine, "_root_engine", engine)
        cur_mode = str(getattr(root, "house_mode", getattr(engine, "house_mode", "HOME")) or "HOME").upper()
        return cur_mode == str(cond.get("state") or "HOME").upper()

    if src in CANONICAL_6_DEVICES:
        dev = (getattr(engine, "devices", None) or {}).get(src) or {}
        cur_state = str(dev.get("state") or "").upper()
        return cur_state == str(cond.get("state") or "").upper()

    return False


async def evaluate_compound_rules(
    engine: Any,
    *,
    trigger_source: str = "",
    now_dt: datetime.datetime | None = None,
    now_epoch: float | None = None,
    db_path: pathlib.Path | None = None,
) -> list[dict[str, Any]]:
    """Evaluate all enabled compound rules with hysteresis, cooldown, and runtime loop guard."""
    if engine is None or not getattr(engine, "server_connected", True):
        return []
    root = getattr(engine, "_root_engine", engine)
    depth = int(getattr(root, "_compound_eval_depth", 0) or 0)
    if depth > 0:
        return []

    setattr(root, "_compound_eval_depth", depth + 1)
    triggered_results: list[dict[str, Any]] = []
    try:
        ref_dt = now_dt if now_dt is not None else now_saigon()
        ref_ep = float(now_epoch) if now_epoch is not None else time.time()
        rules = list_compound_rules(include_disabled=False, db_path=db_path)
        t1_locked_targets: set[str] = set()

        for rule in rules:
            rid = str(rule["rule_id"])
            owner_tier = int(rule.get("owner_tier") or 1)
            owner_name = str(rule.get("owner_name") or rule.get("owner_user_id") or "Hệ thống")
            if owner_tier >= 3:
                continue
            conds = list(rule.get("conditions") or [])
            if not conds:
                continue
            logic = str(rule.get("logic") or "AND").upper()
            prev_matched = bool(rule.get("last_matched", False))
            last_fired = float(rule.get("last_fired_at") or 0.0)
            cooldown = max(0.0, float(rule.get("cooldown_seconds") if rule.get("cooldown_seconds") is not None else 10.0))
            rule_hyst = rule.get("hysteresis")

            cond_results = [
                evaluate_condition(
                    c,
                    engine,
                    now_dt=ref_dt,
                    prev_matched=prev_matched,
                    rule_hysteresis=rule_hyst,
                )
                for c in conds
            ]
            matched_now = all(cond_results) if logic == "AND" else any(cond_results)

            if not prev_matched and matched_now:
                if (ref_ep - last_fired) < cooldown:
                    continue
                actions = list(rule.get("actions") or [])
                fired_any = False
                for act_item in actions:
                    tdev = str(act_item.get("device_id") or "")
                    tact = str(act_item.get("action") or "")
                    if not tdev or not tact or tdev not in CANONICAL_6_DEVICES:
                        continue
                    if not can_control_device(owner_tier, tdev):
                        continue
                    if owner_tier > 1 and tdev in t1_locked_targets:
                        continue
                    if owner_tier == 1:
                        t1_locked_targets.add(tdev)
                    res = await engine.execute_device_action(
                        device_id=tdev,
                        action=tact,
                        source=f"compound_rule ({rid})",
                        bypass_rbac=True,
                        trigger_chains=False,
                    )
                    triggered_results.extend(res.get("results", []))
                    fired_any = True

                _update_compound_rule_runtime(rid, last_fired_at=ref_ep, last_matched=True, db_path=db_path)
                if fired_any:
                    append_audit_log(
                        "AUTOMATION",
                        "compound_rule_fired",
                        f"Kích hoạt luật tự động {rid} ({rule.get('label') or rid}) [nguồn: {trigger_source or 'auto'}]",
                        user_name=owner_name,
                        tier=owner_tier,
                        details={"rule_id": rid, "branch": "then", "trigger_source": trigger_source},
                    )
                    try:
                        await engine.emit(
                            {
                                "type": "compound_rule_fired",
                                "rule_id": rid,
                                "branch": "then",
                                "label": rule.get("label", ""),
                                "trigger_source": trigger_source,
                                "owner_user_id": rule.get("owner_user_id", ""),
                            }
                        )
                    except Exception:
                        pass

            elif prev_matched and not matched_now:
                else_acts = list(rule.get("else_actions") or [])
                if else_acts and (ref_ep - last_fired) >= cooldown:
                    fired_else = False
                    for act_item in else_acts:
                        tdev = str(act_item.get("device_id") or "")
                        tact = str(act_item.get("action") or "")
                        if not tdev or not tact or tdev not in CANONICAL_6_DEVICES:
                            continue
                        if not can_control_device(owner_tier, tdev):
                            continue
                        if owner_tier > 1 and tdev in t1_locked_targets:
                            continue
                        if owner_tier == 1:
                            t1_locked_targets.add(tdev)
                        res = await engine.execute_device_action(
                            device_id=tdev,
                            action=tact,
                            source=f"compound_rule ({rid}:else)",
                            bypass_rbac=True,
                            trigger_chains=False,
                        )
                        triggered_results.extend(res.get("results", []))
                        fired_else = True
                    _update_compound_rule_runtime(rid, last_fired_at=ref_ep, last_matched=False, db_path=db_path)
                    if fired_else:
                        append_audit_log(
                            "AUTOMATION",
                            "compound_rule_fired",
                            f"Kích hoạt nhánh ngược lại luật {rid} ({rule.get('label') or rid})",
                            user_name=owner_name,
                            tier=owner_tier,
                            details={"rule_id": rid, "branch": "else", "trigger_source": trigger_source},
                        )
                        try:
                            await engine.emit(
                                {
                                    "type": "compound_rule_fired",
                                    "rule_id": rid,
                                    "branch": "else",
                                    "label": rule.get("label", ""),
                                    "trigger_source": trigger_source,
                                    "owner_user_id": rule.get("owner_user_id", ""),
                                }
                            )
                        except Exception:
                            pass
                else:
                    _update_compound_rule_runtime(rid, last_matched=False, db_path=db_path)
    finally:
        setattr(root, "_compound_eval_depth", max(0, int(getattr(root, "_compound_eval_depth", 1) or 1) - 1))
    return triggered_results
