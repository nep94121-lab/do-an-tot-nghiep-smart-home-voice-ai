"""General Vietnamese structural NLU parser that routes typed commands into ai_tool_registry."""

from __future__ import annotations

import re
from typing import Any

from backend.ai_tool_registry import dispatch_tool
from backend.automation_engine import (
    CANONICAL_6_DEVICES,
    REMOVED_DEVICE_HINT_VI,
    parse_weekdays_vi,
)
from backend.automation_nlu import (
    _parse_clock_hhmm_vi,
    _parse_countdown_seconds,
    _session_actor,
    parse_multi_steps_from_text,
    parse_single_device_and_action,
)
from backend.automation_repo import (
    find_custom_command_by_text,
    normalize_phrase,
    strip_accents,
)

_REMOVED_OR_UNSUPPORTED_DEVICE_RE = re.compile(
    r"(?:^|\s)("
    r"quat(?:\s+tran|\s+dung|\s+may)?|"
    r"dieu\s+hoa|may\s+lanh|"
    r"hoc\s+lenh|hong\s+ngoai|vs1838b?|remote\s+ir|ir|"
    r"tivi|tv|tu\s+lanh|may\s+giat|rem\s+cua|binh\s+nong\s+lanh|lo\s+vi\s+song|robot\s+hut\s+bui|cua\s+cuon"
    r")(?:\s|$)"
)

_UI_LOCATION_QUESTION_RE = re.compile(
    r"(?:"
    r"\bo\s+dau\b|\bcho\s+nao\b|\bmuc\s+nao\b|\btrang\s+nao\b|\btab\s+nao\b|\bnut\s+nao\b|"
    r"\bbam\s+(?:vao\s+)?dau\b|\bnhan\s+(?:vao\s+)?dau\b|\bclick\s+(?:vao\s+)?dau\b|"
    r"\bmo\s+(?:trang|muc|tab|bang)\b|\bhuong\s+dan\s+(?:mo|xem|tim|vao|tao)\b|"
    r"\blam\s+sao\s+(?:de\s+)?(?:mo|tim|vao|xem|bam)\b|\bcach\s+(?:mo|vao|tim)\b|"
    r"\bvao\s+dau\s+de\b|\btim\s+(?:trang|muc|tab|nut|bang)\b"
    r")"
)

_UI_DOMAIN_NOUN_RE = re.compile(
    r"\b(?:"
    r"tu\s+dong\s+hoa|hen\s+gio|lich\s+trinh|dat\s+lich|lenh\s+tuy\s+chinh|lenh\s+custom|"
    r"luat\s+tu\s+dong|quy\s+tac|che\s+do\s+vang\s+nha|vang\s+nha|o\s+nha|"
    r"xac\s+thuc|ma\s+qr|qr|moi\s+khach|phan\s+cung|wokwi|nhat\s+ky|log|"
    r"cam\s+bien|thiet\s+bi|giong\s+noi|micro|dat\s+lai|reset|giao\s+dien|bang\s+dieu\s+khien"
    r")\b"
)

_RULE_START_RE = re.compile(
    r"(?:^|\s)(?:neu|khi|bat\s+cu\s+luc\s+nao|moi\s+luc|tao\s+luat|dat\s+luat|them\s+luat|tao\s+quy\s+tac|dat\s+quy\s+tac|luat\s+tu\s+dong)(?:\s|$)"
)

_RESET_OR_CLEAR_GUARD_RE = re.compile(
    r"(?:^|\s)(?:"
    r"reset|ri\s+set|factory\s+reset|khoi\s+phuc|hoi\s+phuc|dat\s+lai|thiet\s+lap\s+lai|khoi\s+dong\s+lai|"
    r"(?:xoa|huy|don|go|dep|loai)(?:\s+(?:bo|sach|het|toan\s+bo|tat\s+ca|cac|moi))?\s+(?:(?:giup|gium|dum|ho|cho)\s+(?:toi|minh|anh|chi|em)\s+)?"
    r"(?:toan\s+bo\s+|tat\s+ca\s+|cac\s+|moi\s+)?(?:cai\s+dat|cau\s+hinh|thiet\s+lap|luat|quy\s+tac|lien\s+ket|hen\s+gio|lich|lenh|khau\s+lenh|cau\s+lenh|phim\s+tat)|"
    r"(?:dua|dat|tra)\s+.+\s+ve\s+(?:trang\s+thai\s+)?(?:mac\s+dinh|ban\s+dau|xuat\s+xuong|goc)"
    r")(?:\s|$)"
)

_KEEP_UNCHANGED_GUARD_RE = re.compile(
    r"(?:^|\s)(?:cu\s+de\s+nguyen|de\s+nguyen|giu\s+nguyen|cu\s+giu\s+nguyen|dung\s+dung\s+toi|khong\s+can\s+dung)(?:\s|$)"
)

_MACRO_CREATION_PREFIX_RE = re.compile(
    r"^(?:(?:toi|minh|em)\s+muon\s+|giup\s+(?:toi|minh|anh|chi|em)\s+|hay\s+|xin\s+|vui\s+long\s+)?"
    r"(?:tao|them|dat|luu|gan|cai|thiet\s+lap|dang\s+ky|ghi\s+nho|nho|sua|chinh\s+sua|chinh|cap\s+nhat|doi|go(?:\s+bo)?|xoa(?:\s+(?:bo|di))?|dep(?:\s+bo)?|loai\s+bo|huy(?:\s+bo)?|bo)\s+"
    r"(?:(?:giup|gium|dum|ho|cho)\s+(?:toi|minh|anh|chi|em|ban)\s+)?"
    r"(?:(?:mot|cai)\s+)?(?:khau\s+lenh|cau\s+lenh|lenh(?:\s+(?:moi|rieng|tat|tuy\s+chinh|custom|giong\s+noi|da\s+luu|cu))?|cau|ngu\s+canh|kich\s+ban|scene|che\s+do|bi\s+danh|phim\s+tat(?:\s+giong\s+noi)?)\b"
)

_MACRO_CONDITIONAL_BODY_RE = re.compile(
    r"^(?:(?:toi|minh|em)\s+muon\s+|giup\s+(?:toi|minh)\s+|hay\s+)?"
    r"(?:tao|them|dat|luu|cai)\s+"
    r"(?:khau\s+lenh|lenh|luat|quy\s+tac|lien\s+ket)(?:\s+moi)?\s+"
    r"(?:cu|khi|neu|he)\s+.+\s+(?:la|thi)\s+.+$"
)


def _has_explicit_rule_cue(raw: str, norm_safe: str) -> bool:
    """Return True only when an explicit conditional/rule cue is present (without 'hệ'/'hè'/'hé' or 'cứ để nguyên' collisions)."""
    padded = f" {norm_safe} "
    if _RULE_START_RE.search(padded):
        return True
    raw_low = str(raw or "").lower()
    # Accent-safe 'hễ' (never collide with 'hệ thống', 'đi hè', or 'hé mở'/'hé cửa')
    if any(ord(ch) > 127 for ch in raw_low):
        if re.search(r"\bhễ\b", raw_low):
            return True
    elif re.search(r"\bhe\s+(?!thong\b|mo\b|cua\b)\S+", norm_safe) and (" thi " in padded or " la " in padded):
        return True
    # 'cứ' as conditional trigger (never collide with 'cứ để nguyên' / 'cứ giữ nguyên' / 'cứ kệ')
    if re.search(r"\bcu\s+(?!(?:de\s+nguyen|giu\s+nguyen|ke|mac\s+ke|vay)\b)\S+", norm_safe):
        return True
    return False


def _norm_protect_air(text: str) -> str:
    """Normalize phrase while protecting ambient-air noun from colliding with conditional cues."""
    s = re.sub(r"\b(?:không\s+khí|khong\s+khi)\b", " khongkhi ", str(text or ""), flags=re.IGNORECASE)
    return normalize_phrase(s)


def _vi_spoken_number_to_float(clause_norm: str) -> float | None:
    """Convert Vietnamese spoken integer (0..99) in sensor clauses to float."""
    m_dig = re.search(r"(\d+(?:\.\d+)?)", clause_norm)
    if m_dig:
        return float(m_dig.group(1))
    units = {
        "khong": 0, "mot": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4,
        "nam": 5, "lam": 5, "sau": 6, "bay": 7, "tam": 8, "chin": 9,
    }
    toks = clause_norm.split()
    for i in range(len(toks)):
        t0 = toks[i]
        if t0 == "muoi":
            if i + 1 < len(toks) and toks[i + 1] in units and 1 <= units[toks[i + 1]] <= 9:
                return float(10 + units[toks[i + 1]])
            return 10.0
        if t0 in units and 2 <= units[t0] <= 9 and i + 1 < len(toks) and toks[i + 1] == "muoi":
            base = units[t0] * 10
            if i + 2 < len(toks) and toks[i + 2] in units and 1 <= units[toks[i + 2]] <= 9:
                return float(base + units[toks[i + 2]])
            return float(base)
    return None


def _norm(text: str) -> str:
    return normalize_phrase(text)


def is_ui_guidance_question(text: str) -> bool:
    norm = _norm(text)
    if not norm:
        return False
    return bool(_UI_LOCATION_QUESTION_RE.search(norm) and _UI_DOMAIN_NOUN_RE.search(norm))


def _to_handled_result(tool_res: dict[str, Any]) -> dict[str, Any]:
    if tool_res.get("board_offline"):
        st = 503
    else:
        st = int(tool_res.get("status_code") or (403 if tool_res.get("rbac_blocked") else (200 if tool_res.get("ok", True) else 400)))
    return {
        "handled": True,
        "status_code": st,
        "payload": tool_res,
    }


def _clarify(msg: str) -> dict[str, Any]:
    return {
        "handled": True,
        "status_code": 200,
        "payload": {
            "ok": True,
            "executed": False,
            "requires_confirmation": False,
            "needs_clarification": True,
            "reply": msg,
            "exact_spoken_reply": msg,
        },
    }


def _parse_time_window_from_clause(clause_norm: str) -> dict[str, Any] | None:
    # Explicit range: "tu 18 gio den 6 gio", "tu 22:00 den 05:30", "khung gio 18h-6h"
    m_rng = re.search(
        r"(?:tu|khung\s+gio|trong\s+khoang)\s*"
        r"(\d{1,2})(?:\s*(?::|gio|h)\s*(\d{1,2})?)?\s*(sang|trua|chieu|toi|dem)?\s*"
        r"(?:den|toi|-)\s*"
        r"(\d{1,2})(?:\s*(?::|gio|h)\s*(\d{1,2})?)?\s*(sang|trua|chieu|toi|dem)?",
        clause_norm,
    )
    if m_rng:
        sh, sm = int(m_rng.group(1)), int(m_rng.group(2) or 0)
        sp = m_rng.group(3) or ""
        eh, em = int(m_rng.group(4)), int(m_rng.group(5) or 0)
        ep = m_rng.group(6) or ""
        if sp in ("chieu", "toi") and 1 <= sh <= 11:
            sh += 12
        elif sp == "dem" and 6 <= sh <= 11:
            sh += 12
        if ep in ("chieu", "toi") and 1 <= eh <= 11:
            eh += 12
        elif ep == "dem" and 6 <= eh <= 11:
            eh += 12
        if 0 <= sh <= 23 and 0 <= sm <= 59 and 0 <= eh <= 23 and 0 <= em <= 59:
            tw: dict[str, Any] = {
                "source": "time_window",
                "start_hhmm": f"{sh:02d}:{sm:02d}",
                "end_hhmm": f"{eh:02d}:{em:02d}",
            }
            wds = parse_weekdays_vi(clause_norm)
            if wds:
                tw["weekdays"] = wds
            return tw

    # "sau 22 gio" -> 22:00 - 06:00 ; "truoc 6 gio" -> 00:00 - 06:00
    m_after = re.search(r"\bsau\s+(\d{1,2})(?:\s*(?::|gio|h)\s*(\d{1,2})?)?\s*(sang|chieu|toi|dem)?\b", clause_norm)
    if m_after:
        hh, mm = int(m_after.group(1)), int(m_after.group(2) or 0)
        per = m_after.group(3) or ""
        if per in ("chieu", "toi") and 1 <= hh <= 11:
            hh += 12
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return {"source": "time_window", "start_hhmm": f"{hh:02d}:{mm:02d}", "end_hhmm": "06:00"}

    m_before = re.search(r"\btruoc\s+(\d{1,2})(?:\s*(?::|gio|h)\s*(\d{1,2})?)?\s*(sang|chieu|toi|dem)?\b", clause_norm)
    if m_before:
        hh, mm = int(m_before.group(1)), int(m_before.group(2) or 0)
        per = m_before.group(3) or ""
        if per in ("chieu", "toi") and 1 <= hh <= 11:
            hh += 12
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return {"source": "time_window", "start_hhmm": "00:00", "end_hhmm": f"{hh:02d}:{mm:02d}"}

    if any(k in f" {clause_norm} " for k in (" ban dem ", " dem khuya ", " buoi dem ")):
        return {"source": "time_window", "start_hhmm": "22:00", "end_hhmm": "06:00"}
    if any(k in f" {clause_norm} " for k in (" buoi toi ", " troi toi ")):
        return {"source": "time_window", "start_hhmm": "18:00", "end_hhmm": "06:00"}
    if any(k in f" {clause_norm} " for k in (" buoi sang ", " ban ngay ")):
        return {"source": "time_window", "start_hhmm": "06:00", "end_hhmm": "18:00"}
    return None


def _parse_numeric_sensor_condition(raw_clause: str, clause_norm: str) -> dict[str, Any] | None:
    # Determine sensor source first (strip DHT11/KY037 model digits before extracting threshold number!)
    source = ""
    padded_c = f" {clause_norm} "
    if "do am dat" in clause_norm or "cam bien dat" in clause_norm or ("dat" in clause_norm and "%" in raw_clause):
        source = "soil_sensor"
    elif "nhiet do" in clause_norm or (
        "do am" not in clause_norm
        and (
            "do c" in clause_norm
            or "°c" in raw_clause.lower()
            or (
                " do " in padded_c
                and any(
                    k in padded_c
                    for k in (" lanh ", " nong ", " duoi ", " tren ", " thap ", " cao ", " vuot ", " giam ", " tang ", " xuong ", " tro xuong ", " tro len ")
                )
            )
        )
    ):
        source = "temp_sensor"
    elif "do am" in clause_norm and "dat" not in clause_norm:
        source = "humidity_sensor"
    if not source:
        return None

    raw_no_model = re.sub(r"\b(?:dht\s*11|ky\s*-?\s*03[78]|yl\s*-?\s*69|pam\s*8403)\b", " ", raw_clause, flags=re.IGNORECASE)
    norm_no_model = re.sub(r"\b(?:dht\s*11|ky\s*03[78]|yl\s*69|pam\s*8403)\b", " ", clause_norm)

    # Symbolic operator in raw text: >=, <=, !=, ==, >, <
    m_sym = re.search(r"(>=|<=|!=|==|>|<)\s*(\d+(?:\.\d+)?)", raw_no_model)
    if m_sym:
        return {"source": source, "operator": m_sym.group(1), "value": float(m_sym.group(2))}

    # Vietnamese comparator words (supports both digits and spoken Vietnamese numbers)
    val = _vi_spoken_number_to_float(norm_no_model)
    if val is None:
        return None
    padded = f" {norm_no_model} "
    if any(k in padded for k in (" tro len ", " tu ", " lon hon hoac bang ", " it nhat ")):
        if " tu " in padded and (" tro xuong " in padded or " den " in padded):
            return {"source": source, "operator": "<=", "value": val}
        if any(k in padded for k in (" tro len ", " lon hon hoac bang ", " it nhat ")):
            return {"source": source, "operator": ">=", "value": val}
    if any(k in padded for k in (" tro xuong ", " nho hon hoac bang ", " toi da ")):
        return {"source": source, "operator": "<=", "value": val}
    if any(k in padded for k in (" tren ", " vuot ", " vuot qua ", " lon hon ", " cao hon ", " len tren ")):
        return {"source": source, "operator": ">", "value": val}
    if any(
        k in padded
        for k in (
            " giam xuong duoi ", " giam duoi ", " lanh duoi ", " xuong duoi ", " duoi ",
            " nho hon ", " thap hon ", " lanh hon ", " it hon ", " giam xuong ", " ha xuong ",
        )
    ):
        return {"source": source, "operator": "<", "value": val}
    if any(k in padded for k in (" bang ", " dung ")):
        return {"source": source, "operator": "==", "value": val}
    return None


def _parse_single_condition(raw_clause: str) -> dict[str, Any] | None:
    clause_norm = _norm(raw_clause)
    if not clause_norm:
        return None
    padded = f" {clause_norm} "

    # 1. Time window
    tw = _parse_time_window_from_clause(clause_norm)
    if tw is not None:
        return tw

    # 2. House mode
    if any(k in padded for k in (" vang nha ", " di vang ", " khong co ai o nha ", " khong o nha ", " che do vang ")):
        return {"source": "house_mode", "state": "AWAY"}
    if any(k in padded for k in (" che do o nha ", " dang o nha ", " co nguoi o nha ", " o nha ")):
        return {"source": "house_mode", "state": "HOME"}

    # 3. Numeric sensor threshold
    num_cond = _parse_numeric_sensor_condition(raw_clause, clause_norm)
    if num_cond is not None:
        return num_cond

    # 4. Qualitative sensor condition (allows optional intervening location words)
    if (
        any(k in padded for k in (" dat kho ", " do am dat thap ", " dat bi kho ", " dat qua kho "))
        or re.search(r"\bdat\b(?:\s+\S+){0,3}\s+(?:bi\s+|qua\s+|hoi\s+|dang\s+)?kho\b", clause_norm)
    ):
        return {"source": "soil_sensor", "state": "DRY"}
    if (
        any(k in padded for k in (" dat am ", " dat uot ", " dat du am ", " do am dat cao "))
        or re.search(r"\bdat\b(?:\s+\S+){0,3}\s+(?:du\s+|qua\s+|bi\s+|dang\s+)?(?:am|uot)\b", clause_norm)
    ):
        return {"source": "soil_sensor", "state": "WET"}
    if any(k in padded for k in (" yen tinh ", " het tieng dong ", " khong co tieng dong ", " khong co tieng on ")):
        return {"source": "sound_sensor", "state": "QUIET"}
    if any(
        k in padded
        for k in (
            " tieng dong ", " tieng on ", " am thanh lon ", " am thanh bat thuong ",
            " on ao ", " vo tay ", " phat hien am thanh ", " phat hien tieng ", " nghe thay tieng ",
        )
    ) or (
        any(k in padded for k in (" cam bien am thanh ", " ky037 ", " ky 037 "))
        and any(k in padded for k in (" phat hien ", " tieng dong ", " tieng on ", " am thanh ", " keu ", " bao "))
    ):
        return {"source": "sound_sensor", "state": "LOUD"}
    if " nhiet do " in padded:
        if any(k in padded for k in (" cao ", " nong ")):
            return {"source": "temp_sensor", "state": "HIGH"}
        if any(k in padded for k in (" thap ", " lanh ")):
            return {"source": "temp_sensor", "state": "LOW"}
    if " do am " in padded and " dat " not in padded:
        if " cao " in padded:
            return {"source": "humidity_sensor", "state": "HIGH"}
        if " thap " in padded:
            return {"source": "humidity_sensor", "state": "LOW"}

    # 5. Device state condition
    dev, act = parse_single_device_and_action(raw_clause)
    if dev in CANONICAL_6_DEVICES and act:
        if dev == "main_door":
            st = "OPEN" if act in ("open", "turn_on") else "CLOSED"
        else:
            st = "ON" if act in ("open", "turn_on") else "OFF"
        return {"source": dev, "state": st}
    return None


def _parse_compound_rule_text(text: str) -> dict[str, Any] | None:
    """Parse general Vietnamese compound rule statement into {logic, conditions, actions, else_actions, cooldown_seconds}."""
    raw = str(text or "").strip()
    norm_safe = _norm_protect_air(raw)
    # Never hijack reset/delete/restore/clear commands or keep-unchanged clauses
    if _RESET_OR_CLEAR_GUARD_RE.search(f" {norm_safe} "):
        return None
    # Never hijack custom-command/scene creation unless the body is an explicit conditional rule (<cue> <condition> <sep> <action>).
    is_macro_cond = bool(_MACRO_CONDITIONAL_BODY_RE.match(norm_safe))
    if _MACRO_CREATION_PREFIX_RE.match(norm_safe) and not is_macro_cond:
        return None
    has_rule_cue = _has_explicit_rule_cue(raw, norm_safe)
    if not has_rule_cue and not is_macro_cond:
        # Also allow threshold-first form without leading conditional cue when explicit consequence separator + sensor condition present
        if not (" thi " in f" {norm_safe} " and any(k in f" {norm_safe} " for k in (" nhiet do ", " do am ", " dat kho ", " tieng dong "))):
            return None

    # Split condition part and action part on consequence separator (also allow 'là' for 'cứ' or explicit rule-creation prefixes)
    m_then = re.search(r"\b(?:thì|thi)\b|->", raw, flags=re.IGNORECASE)
    if not m_then and re.search(
        r"\b(?:cứ|cu|(?:đặt|tạo|thêm|cài|dat|tao|them|cai)\s+(?:quy\s+tắc|quy\s+tac|luật|luat|liên\s+kết|lien\s+ket))\b",
        raw,
        flags=re.IGNORECASE,
    ):
        m_then = re.search(r"\b(?:là|la)\b", raw, flags=re.IGNORECASE)
    if not m_then and has_rule_cue:
        # Support comma or 'tự động' / 'sẽ' separators when a valid condition precedes a valid action
        m_alt_sep = re.search(
            r",\s*(?=(?:tự\s+động|tu\s+dong|hệ\s+thống|he\s+thong|hãy|hay|bật|tắt|mở|đóng|khóa|ngắt|dừng|ngừng|cúp|kích\s+hoạt|khởi\s+động|bat|tat|mo|dong|khoa|ngat|dung|ngung|cup)\b)|"
            r"\b(?:hệ\s+thống\s+(?:tự\s+động|tự|sẽ)|he\s+thong\s+(?:tu\s+dong|tu|se)|tự\s+động|tu\s+dong|sẽ|se)\b",
            raw,
            flags=re.IGNORECASE,
        )
        if m_alt_sep:
            cand_left = raw[: m_alt_sep.start()].strip()
            cand_right = raw[m_alt_sep.end() :].strip()
            if cand_left and cand_right and parse_multi_steps_from_text(cand_right):
                m_then = m_alt_sep
    if not m_then:
        if _KEEP_UNCHANGED_GUARD_RE.search(f" {norm_safe} "):
            return None
        # Only ask for missing action when an explicit conditional cue introduces a valid parsed condition
        if not has_rule_cue:
            return None
        probe_cond = re.sub(
            r"^(?:hãy\s+|xin\s+|vui\s+lòng\s+|"
            r"(?:tạo|đặt|thêm|cài)\s+(?:luật(?:\s+tự\s+động)?|quy\s+tắc|liên\s+kết|lệnh(?:\s+tự\s+động)?|khẩu\s+lệnh)\s+|"
            r"luật\s+tự\s+động\s+)*"
            r"(?:nếu|khi|hễ|cứ|bất\s+cứ\s+lúc\s+nào|mỗi\s+lúc)\s+",
            "",
            raw,
            flags=re.IGNORECASE,
        ).strip()
        if probe_cond == raw or _parse_single_condition(probe_cond) is None:
            return None
        return {"ambiguous": True, "reason": "missing_then"}

    cond_part_raw = raw[: m_then.start()].strip()
    action_part_raw = raw[m_then.end() :].strip()

    # Strip leading rule verbs
    cond_part_raw = re.sub(
        r"^(?:hãy\s+|xin\s+|vui\s+lòng\s+|"
        r"(?:tạo|đặt|thêm|cài)\s+(?:luật(?:\s+tự\s+động)?|quy\s+tắc|liên\s+kết|lệnh(?:\s+tự\s+động)?|khẩu\s+lệnh)\s+|"
        r"luật\s+tự\s+động\s+)*"
        r"(?:nếu|khi|hễ|cứ|bất\s+cứ\s+lúc\s+nào|mỗi\s+lúc)?\s*",
        "",
        cond_part_raw,
        flags=re.IGNORECASE,
    ).strip()

    # Do not hijack single-clock-time recurring schedules (let schedule parser handle HH:MM without a time window)
    cond_norm_chk = _norm(cond_part_raw)
    if _parse_time_window_from_clause(cond_norm_chk) is None:
        hhmm_c, _, _ = _parse_clock_hhmm_vi(cond_part_raw)
        if hhmm_c is not None and _parse_single_condition(cond_part_raw) is None:
            return None

    # Optional cooldown extraction: "nghỉ 30 giây", "chờ 60 giây mới lặp lại", "cooldown 20s"
    cooldown_sec = 10.0
    m_cd = re.search(
        r"(?:nghỉ|chờ|cooldown|giãn\s+cách)\s+(\d+(?:\.\d+)?)\s*(giây|s|phút|p)\b",
        action_part_raw,
        flags=re.IGNORECASE,
    )
    if m_cd:
        cd_val = float(m_cd.group(1))
        cd_unit = strip_accents(m_cd.group(2).lower())
        cooldown_sec = cd_val * 60.0 if cd_unit in ("phut", "p") else cd_val
        action_part_raw = (action_part_raw[: m_cd.start()] + " " + action_part_raw[m_cd.end() :]).strip()

    # Optional else clause: "ngược lại ..."
    else_part_raw = ""
    m_else = re.search(r"\b(?:ngược\s+lại|nguoc\s+lai|còn\s+không|con\s+khong)\b", action_part_raw, flags=re.IGNORECASE)
    if m_else:
        else_part_raw = action_part_raw[m_else.end() :].strip()
        action_part_raw = action_part_raw[: m_else.start()].strip()

    # Determine logic (OR vs AND) and split condition clauses
    has_or = bool(re.search(r"\b(?:hoặc|hoac|hay\s+là|hay\s+la)\b", cond_part_raw, flags=re.IGNORECASE))
    logic = "OR" if has_or else "AND"
    if has_or:
        raw_cond_clauses = re.split(r"\b(?:hoặc|hoac|hay\s+là|hay\s+la)\b", cond_part_raw, flags=re.IGNORECASE)
    else:
        raw_cond_clauses = re.split(
            r"(?:,|;|\bvà\b|\bva\b|\bđồng\s+thời\b|\bdong\s+thoi\b|\bcùng\s+lúc\b|\bcung\s+luc\b|\btrong\s+khi\b)",
            cond_part_raw,
            flags=re.IGNORECASE,
        )

    conditions: list[dict[str, Any]] = []
    for cl in raw_cond_clauses:
        cl_s = cl.strip()
        if not cl_s:
            continue
        parsed_c = _parse_single_condition(cl_s)
        if parsed_c is not None:
            conditions.append(parsed_c)
        else:
            # A clause may contain a time phrase + another condition (e.g. "ban đêm có tiếng động lớn")
            tw_sub = _parse_time_window_from_clause(_norm(cl_s))
            if tw_sub is not None:
                conditions.append(tw_sub)

    actions = parse_multi_steps_from_text(action_part_raw)
    else_actions = parse_multi_steps_from_text(else_part_raw) if else_part_raw else []

    if not conditions or not actions:
        return {"ambiguous": True, "reason": "missing_parts", "conditions": conditions, "actions": actions}

    # Check if this truly needs compound_rules vs 1-to-1 automation_rule (single numeric sensor thresholds route to automation_nlu)
    is_compound = (
        len(conditions) >= 2
        or len(actions) >= 2
        or len(else_actions) >= 2
        or logic == "OR"
        or any(
            c.get("source") in ("time_window", "house_mode")
            for c in conditions
        )
        or cooldown_sec != 10.0
    )
    if not is_compound:
        return None

    return {
        "ambiguous": False,
        "logic": logic,
        "conditions": conditions,
        "actions": actions,
        "else_actions": else_actions,
        "cooldown_seconds": cooldown_sec,
    }


async def process_compound_nlu_command(
    *,
    text: str,
    engine: Any,
    session: Any,
    source: str = "text_command",
    session_key: str = "",
) -> dict[str, Any] | None:
    """Process compound rules, UI guidance, house mode, weekday schedules, rule/schedule toggles, and safety guards."""
    raw = str(text or "").strip()
    if not raw:
        return None
    norm = _norm(raw)
    padded = f" {norm} "
    user_id, tier, _, _ = _session_actor(session)

    # 1. UI guidance questions (available for all authenticated tiers, never blocked by removed-device regex)
    if _UI_LOCATION_QUESTION_RE.search(norm) and _UI_DOMAIN_NOUN_RE.search(norm):
        res_ui = await dispatch_tool(
            "get_ui_guidance",
            {"query": raw},
            engine=engine,
            session=session,
            source=source,
            session_key=session_key,
        )
        return _to_handled_result(res_ui)

    # 2. Polite refusal for removed / unsupported devices (let explicit macro creation return 400 in automation_nlu)
    norm_safe = _norm_protect_air(raw)
    if _REMOVED_OR_UNSUPPORTED_DEVICE_RE.search(padded) and not _MACRO_CREATION_PREFIX_RE.match(norm_safe):
        # Allow legitimate queries about what devices exist; refuse commands targeting removed devices
        msg = (
            f"Xin lỗi, thiết bị bạn vừa nhắc không có trong hệ thống và chưa được hỗ trợ. {REMOVED_DEVICE_HINT_VI}"
        )
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": False,
                "unsupported_device": True,
                "executed": False,
                "requires_confirmation": False,
                "error": msg,
                "reply": msg,
                "exact_spoken_reply": msg,
            },
        }

    # 3. Direct house presence mode commands (skip if it's a rule or matches an existing custom command)
    is_rule_phrase = bool(
        (_has_explicit_rule_cue(raw, norm_safe) or re.search(r"\b(?:thi|luat|quy\s+tac)\b", norm_safe))
        and not (_MACRO_CREATION_PREFIX_RE.match(norm_safe) and not _MACRO_CONDITIONAL_BODY_RE.match(norm_safe))
    )
    if not is_rule_phrase:
        saved_custom = find_custom_command_by_text(raw, owner_user_id=user_id) if tier < 3 else None
        if saved_custom is None:
            if any(
                k in padded
                for k in (
                    " che do vang nha ",
                    " bat che do vang nha ",
                    " chuyen sang vang nha ",
                    " dat che do vang nha ",
                    " toi di vang ",
                    " minh di vang ",
                    " nha vang nguoi ",
                )
            ):
                res_hm = await dispatch_tool(
                    "set_house_mode",
                    {"mode": "AWAY"},
                    engine=engine,
                    session=session,
                    source=source,
                    session_key=session_key,
                )
                return _to_handled_result(res_hm)
            if any(
                k in padded
                for k in (
                    " che do o nha ",
                    " bat che do o nha ",
                    " chuyen sang o nha ",
                    " dat che do o nha ",
                    " toi da ve nha ",
                    " minh ve nha roi ",
                    " ve nha roi ",
                )
            ):
                res_hm = await dispatch_tool(
                    "set_house_mode",
                    {"mode": "HOME"},
                    engine=engine,
                    session=session,
                    source=source,
                    session_key=session_key,
                )
                return _to_handled_result(res_hm)

    # 4. Automation rule management: toggle / list / edit / delete
    if re.search(r"\b(?:luat|quy\s+tac)\b", norm):
        # Toggle rule on/off
        m_tog_off = re.search(r"^(?:tam\s+dung|tam\s+tat|tat|vo\s+hieu\s+hoa|ngung)\s+(?:luat|quy\s+tac)(?:\s+tu\s+dong)?\s*(.*)$", norm)
        m_tog_on = re.search(r"^(?:kich\s+hoat|bat\s+lai|bat|mo\s+lai)\s+(?:luat|quy\s+tac)(?:\s+tu\s+dong)?\s*(.*)$", norm)
        if m_tog_off or m_tog_on:
            enabled_val = bool(m_tog_on)
            tail = (m_tog_on.group(1) if m_tog_on else m_tog_off.group(1)).strip()  # type: ignore[union-attr]
            rid_m = re.search(r"\b((?:c?rule)_[a-z0-9_]+)\b", tail)
            res_t = await dispatch_tool(
                "toggle_automation_rule",
                {
                    "rule_id": rid_m.group(1) if rid_m else "",
                    "keyword": "" if rid_m else tail,
                    "enabled": enabled_val,
                },
                engine=engine,
                session=session,
                source=source,
                session_key=session_key,
            )
            return _to_handled_result(res_t)

        # List rules
        if re.search(r"\b(?:xem|danh\s+sach|liet\s+ke|co\s+nhung|cac\s+luat|co\s+luat\s+nao)\b", norm) and not re.search(
            r"\b(?:tao|dat|them|xoa|huy|sua|doi)\b", norm
        ):
            res_l = await dispatch_tool(
                "list_automation_rules",
                {"include_disabled": True},
                engine=engine,
                session=session,
                source=source,
                session_key=session_key,
            )
            return _to_handled_result(res_l)

        # Edit rule: "sửa luật <id/kw> thành nếu ... thì ..."
        m_edit = re.search(r"^(?:sửa|đổi|cập\s+nhật|chỉnh)\s+(?:luật|quy\s+tắc)(?:\s+tự\s+động)?\s+(.+?)\s+(?:thành|sang)\s+(.+)$", raw, flags=re.IGNORECASE)
        if m_edit:
            target_ref = m_edit.group(1).strip()
            new_body = m_edit.group(2).strip()
            parsed_new = _parse_compound_rule_text(new_body if _RULE_START_RE.search(f" {_norm(new_body)} ") else f"nếu {new_body}")
            if parsed_new and not parsed_new.get("ambiguous"):
                rid_m = re.search(r"\b(crule_[a-z0-9_]+)\b", target_ref, flags=re.IGNORECASE)
                res_e = await dispatch_tool(
                    "edit_automation_rule",
                    {
                        "rule_id": rid_m.group(1) if rid_m else "",
                        "keyword": "" if rid_m else target_ref,
                        "logic": parsed_new["logic"],
                        "conditions": parsed_new["conditions"],
                        "actions": parsed_new["actions"],
                        "else_actions": parsed_new["else_actions"],
                        "cooldown_seconds": parsed_new["cooldown_seconds"],
                    },
                    engine=engine,
                    session=session,
                    source=source,
                    session_key=session_key,
                )
                return _to_handled_result(res_e)

        # Delete compound rule by explicit id or keyword (bulk clears route to automation_nlu reset_pool)
        m_del_r = re.search(r"^(?:xoa|huy|bo)\s+(?:luat|quy\s+tac)(?:\s+tu\s+dong)?\s+(.+)$", norm)
        if m_del_r:
            tail = m_del_r.group(1).strip()
            if not re.match(r"^(?:tat\s+ca|het|toan\s+bo|sach|cac)\b", tail):
                rid_m = re.search(r"\b((?:c?rule)_[a-z0-9_]+)\b", tail)
                dev_m, _ = parse_single_device_and_action(tail, allow_den_asr_homophone=True)
                res_dr = await dispatch_tool(
                    "delete_automation_rule",
                    {
                        "rule_id": rid_m.group(1) if rid_m else "",
                        "keyword": "" if rid_m else tail,
                        "device_id": dev_m or "",
                    },
                    engine=engine,
                    session=session,
                    source=source,
                    session_key=session_key,
                )
                if res_dr.get("status_code") != 404:
                    return _to_handled_result(res_dr)

    # 5. Schedule toggle & recurring weekday schedule creation
    if re.search(r"\blich\b", norm):
        norm_stog = re.sub(r"^(?:hay|xin|vui\s+long|lam\s+on|giup\s+(?:toi|minh|anh|chi|em))\s+", "", norm).strip()
        m_stog_off = re.search(
            r"^(?:tam\s+dung|tam\s+ngung|tam\s+tat|tat|ngung|dung)\s+"
            r"(?:(?:giup|gium|ho)\s+(?:toi|minh|anh|chi|em)\s+)?"
            r"lich(?:\s+(?:trinh|hen|dinh\s+ky|tu\s+dong))?\s*(.*)$",
            norm_stog,
        )
        m_stog_on = re.search(
            r"^(?:kich\s+hoat|bat\s+lai|bat|mo\s+lai|tiep\s+tuc|cho\s+chay\s+lai)\s+"
            r"(?:(?:giup|gium|ho)\s+(?:toi|minh|anh|chi|em)\s+)?"
            r"lich(?:\s+(?:trinh|hen|dinh\s+ky|tu\s+dong))?\s*(.*)$",
            norm_stog,
        )
        if m_stog_off or m_stog_on:
            enabled_val = bool(m_stog_on)
            tail = (m_stog_on.group(1) if m_stog_on else m_stog_off.group(1)).strip()  # type: ignore[union-attr]
            # Parse clock time from raw text (preserving ':' in HH:MM) rather than colon-stripped norm
            m_raw_tail = re.search(r"(?:lịch(?:\s+(?:trình|hẹn|định\s+kỳ|tự\s+động))?|lich(?:\s+(?:trinh|hen|dinh\s+ky|tu\s+dong))?)\s*(.*)$", raw, flags=re.IGNORECASE)
            raw_tail = m_raw_tail.group(1).strip() if m_raw_tail else raw
            hhmm_t, _, _ = _parse_clock_hhmm_vi(raw_tail)
            if not hhmm_t:
                hhmm_t, _, _ = _parse_clock_hhmm_vi(f"lúc {raw_tail}")
            dev_t, _ = parse_single_device_and_action(raw_tail or tail)
            sid_m = re.search(r"\b(sched_[a-z0-9_]+)\b", tail)
            res_st = await dispatch_tool(
                "toggle_schedule",
                {
                    "schedule_id": sid_m.group(1) if sid_m else "",
                    "time_hhmm": hhmm_t or "",
                    "device_id": dev_t or "",
                    "enabled": enabled_val,
                },
                engine=engine,
                session=session,
                source=source,
                session_key=session_key,
            )
            return _to_handled_result(res_st)

    weekdays_found = parse_weekdays_vi(raw)
    has_sched_repeat_cue = bool(
        re.search(r"\b(?:lich|hen\s+gio|dat\s+lich|lap\s+lai|hang|dinh\s+ky)\b", norm)
        or (re.search(r"\bmỗi\b", raw.lower()) if any(ord(ch) > 127 for ch in raw) else re.search(r"\bmoi\s+(?:ngay|sang|toi|tuan|thu)\b", norm))
    )
    is_sched_edit_or_del = bool(
        re.match(r"^(?:hay\s+|xin\s+|vui\s+long\s+)?(?:doi|sua|chinh\s+sua|cap\s+nhat|xoa|huy|go|tam\s+dung|tam\s+tat|bat\s+lai)\b", norm)
    )
    if (
        weekdays_found
        and has_sched_repeat_cue
        and not is_sched_edit_or_del
        and not _RESET_OR_CLEAR_GUARD_RE.search(f" {norm_safe} ")
    ):
        hhmm_w, _, cleaned_w = _parse_clock_hhmm_vi(raw)
        dev_w, act_w = parse_single_device_and_action(raw)
        if not dev_w or not act_w:
            dev_w2, act_w2 = parse_single_device_and_action(cleaned_w or raw)
            dev_w = dev_w or dev_w2
            act_w = act_w or act_w2
        if hhmm_w and dev_w in CANONICAL_6_DEVICES and act_w:
            res_ws = await dispatch_tool(
                "create_schedule",
                {
                    "device_id": dev_w,
                    "action": act_w,
                    "time_hhmm": hhmm_w,
                    "schedule_type": "weekly",
                    "weekdays": weekdays_found,
                },
                engine=engine,
                session=session,
                source=source,
                session_key=session_key,
            )
            return _to_handled_result(res_ws)
        if not hhmm_w:
            return _clarify("Bạn muốn đặt lịch vào lúc mấy giờ?")
        if not dev_w or not act_w:
            return _clarify("Bạn muốn đặt lịch bật hay tắt thiết bị nào?")

    # 6. Compound automation rule creation (multi-condition AND/OR, numeric thresholds, time window, house mode, multi-action)
    parsed_rule = _parse_compound_rule_text(raw)
    if parsed_rule is not None:
        if parsed_rule.get("ambiguous"):
            if parsed_rule.get("reason") == "missing_then":
                return _clarify("Khi điều kiện đó xảy ra, bạn muốn hệ thống bật hay tắt thiết bị nào?")
            if not parsed_rule.get("conditions"):
                return _clarify("Bạn muốn đặt luật theo điều kiện cảm biến, thiết bị hay khung giờ nào?")
            return _clarify("Bạn muốn thực hiện hành động gì với thiết bị nào khi điều kiện đúng?")
        res_cr = await dispatch_tool(
            "create_automation_rule",
            {
                "logic": parsed_rule["logic"],
                "conditions": parsed_rule["conditions"],
                "actions": parsed_rule["actions"],
                "else_actions": parsed_rule["else_actions"],
                "cooldown_seconds": parsed_rule["cooldown_seconds"],
            },
            engine=engine,
            session=session,
            source=source,
            session_key=session_key,
        )
        return _to_handled_result(res_cr)

    # 7. Ambiguity guard for incomplete timer / schedule requests (never leak into direct device execution!)
    from backend.voice.vietnamese_policy import (
        _UNSUPPORTED_DEVICE_RE,
        has_vi_diacritics,
        is_no_action_safety_blocked_vi,
    )

    raw_has_diac_7 = has_vi_diacritics(raw)
    is_timer_intent = bool(re.search(r"(?:^|\s)(?:dat\s+)?hen\s+gio(?:\s|$)", padded))
    has_explicit_sched_phrase = bool(
        re.search(r"(?:^|\s)(?:dat\s+lich|len\s+lich|tao\s+lich|hen\s+lich|lap\s+lich|lich\s+tu\s+dong)(?:\s|$)", padded)
    )
    has_recurring_sched_phrase = bool(
        re.search(r"(?:^|\s)(?:hang\s+(?:ngay|sang|trua|chieu|toi|dem|tuan)|ngay\s+nao\s+cung|dinh\s+ky)(?:\s|$)", padded)
        or (
            bool(re.search(r"\bmỗi\s+(?:ngày|sáng|trưa|chiều|tối|đêm|tuần)\b", raw.lower()))
            if raw_has_diac_7
            else bool(re.search(r"(?:^|\s)moi\s+(?:ngay|sang|trua|chieu|toi|dem|tuan)(?:\s|$)", padded))
        )
    )
    is_sched_intent = has_explicit_sched_phrase or (not is_rule_phrase and has_recurring_sched_phrase)
    is_query_or_crud_sched = bool(
        "?" in raw
        or re.search(
            r"\b(?:xem|danh\s+sach|liet\s+ke|co\s+nhung|nao|bao\s+nhieu|xoa|huy|go|don|dep|sua|chinh\s+sua|cap\s+nhat|doi|reset|tam\s+dung|tam\s+tat|bat\s+lai)\b",
            norm,
        )
    )
    if (
        (is_timer_intent or is_sched_intent)
        and not is_query_or_crud_sched
        and not _RESET_OR_CLEAR_GUARD_RE.search(f" {norm_safe} ")
        and not _UNSUPPORTED_DEVICE_RE.search(padded)
        and not is_no_action_safety_blocked_vi(raw)
    ):
        hhmm_chk, _, cleaned_chk = _parse_clock_hhmm_vi(raw)
        cd_sec, cleaned_cd = _parse_countdown_seconds(raw)
        dev_chk, act_chk = parse_single_device_and_action(raw)
        if not dev_chk or not act_chk:
            dev_chk2, act_chk2 = parse_single_device_and_action(cleaned_chk or cleaned_cd or raw)
            dev_chk = dev_chk or dev_chk2
            act_chk = act_chk or act_chk2
        if not hhmm_chk and cd_sec <= 0:
            if is_sched_intent and not is_timer_intent:
                return _clarify("Bạn muốn đặt lịch vào lúc mấy giờ?")
            return _clarify("Bạn muốn hẹn giờ sau bao lâu?")
        if not dev_chk or not act_chk:
            if not dev_chk and re.search(r"\b(?:đèn|den)\b", raw, flags=re.IGNORECASE):
                act_vi = "tắt" if act_chk in ("turn_off", "close") else ("bật" if act_chk else "bật hay tắt")
                return _clarify(f"Bạn muốn {act_vi} đèn phòng khách hay đèn phòng ngủ?")
            return _clarify("Bạn muốn hẹn giờ bật hay tắt thiết bị nào?")

    # 8. General Vietnamese activation/deactivation verbs (e.g. "kích hoạt") for direct 6-device control
    # ALWAYS enforce vietnamese_policy safety guards (deferral/hesitation/negation/keep-unchanged/past-narration/wrong-diacritic/bare-light/macro)!
    if (
        not is_rule_phrase
        and "?" not in raw
        and not _MACRO_CREATION_PREFIX_RE.match(norm_safe)
        and not re.search(
            r"\b(?:hen\s+gio|dat\s+lich|len\s+lich|tao\s+lich|lap\s+lich|hen\s+lich|lich|dinh\s+ky|hang\s+ngay|moi\s+ngay|tao\s+lenh|xoa|huy|sua|doi|reset)\b",
            norm,
        )
        and not re.search(r"\bkich\s+hoat\s+(?:khau\s+lenh|cau\s+lenh|lenh|kich\s+ban|ngu\s+canh|phim\s+tat|che\s+do|scene)\b", norm)
        and re.search(r"\bkich\s+hoat\b", norm)
    ):
        from backend.voice.vietnamese_policy import (
            _detect_wrong_diacritic_near_miss_clarification,
            is_no_action_safety_blocked_vi,
            parse_direct_device_intents_vi,
        )

        if (
            not is_no_action_safety_blocked_vi(raw)
            and _detect_wrong_diacritic_near_miss_clarification(raw) is None
        ):
            safe_intents = parse_direct_device_intents_vi(raw)
            if len(safe_intents) == 1:
                dev_kh = safe_intents[0]["device_id"]
                act_kh = safe_intents[0]["action"]
                if dev_kh in CANONICAL_6_DEVICES:
                    res_kh = await dispatch_tool(
                        "control_device",
                        {"device_id": dev_kh, "action": act_kh},
                        engine=engine,
                        session=session,
                        source=source,
                        session_key=session_key,
                    )
                    return _to_handled_result(res_kh)

    return None
