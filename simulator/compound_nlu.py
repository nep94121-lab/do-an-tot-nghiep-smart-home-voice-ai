"""General Vietnamese structural NLU parser that routes typed commands into ai_tool_registry."""

from __future__ import annotations

import re
from typing import Any

from simulator.ai_tool_registry import dispatch_tool
from simulator.automation_engine import (
    CANONICAL_6_DEVICES,
    REMOVED_DEVICE_HINT_VI,
    parse_weekdays_vi,
)
from simulator.automation_nlu import (
    _parse_clock_hhmm_vi,
    _parse_countdown_seconds,
    _session_actor,
    parse_multi_steps_from_text,
    parse_single_device_and_action,
)
from simulator.automation_repo import (
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
    r"(?:^|\s)(?:neu|khi|he|cu|tao\s+luat|dat\s+luat|them\s+luat|tao\s+quy\s+tac|dat\s+quy\s+tac|luat\s+tu\s+dong)(?:\s|$)"
)


def _norm(text: str) -> str:
    return normalize_phrase(text)


def is_ui_guidance_question(text: str) -> bool:
    norm = _norm(text)
    if not norm:
        return False
    return bool(_UI_LOCATION_QUESTION_RE.search(norm) and _UI_DOMAIN_NOUN_RE.search(norm))


def _to_handled_result(tool_res: dict[str, Any]) -> dict[str, Any]:
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
    # Determine sensor source first
    source = ""
    if "do am dat" in clause_norm or "cam bien dat" in clause_norm or ("dat" in clause_norm and "%" in raw_clause):
        source = "soil_sensor"
    elif "nhiet do" in clause_norm:
        source = "temp_sensor"
    elif "do am" in clause_norm and "dat" not in clause_norm:
        source = "humidity_sensor"
    if not source:
        return None

    # Symbolic operator in raw text: >=, <=, !=, ==, >, <
    m_sym = re.search(r"(>=|<=|!=|==|>|<)\s*(\d+(?:\.\d+)?)", raw_clause)
    if m_sym:
        return {"source": source, "operator": m_sym.group(1), "value": float(m_sym.group(2))}

    # Vietnamese comparator words
    m_num = re.search(r"(\d+(?:\.\d+)?)", clause_norm)
    if not m_num:
        return None
    val = float(m_num.group(1))
    padded = f" {clause_norm} "
    if any(k in padded for k in (" tro len ", " tu ", " lon hon hoac bang ", " it nhat ")):
        if " tu " in padded and (" tro xuong " in padded or " den " in padded):
            return {"source": source, "operator": "<=", "value": val}
        if any(k in padded for k in (" tro len ", " lon hon hoac bang ", " it nhat ")):
            return {"source": source, "operator": ">=", "value": val}
    if any(k in padded for k in (" tro xuong ", " nho hon hoac bang ", " toi da ")):
        return {"source": source, "operator": "<=", "value": val}
    if any(k in padded for k in (" tren ", " vuot ", " vuot qua ", " lon hon ", " cao hon ", " len tren ")):
        return {"source": source, "operator": ">", "value": val}
    if any(k in padded for k in (" duoi ", " nho hon ", " thap hon ", " xuong duoi ", " it hon ")):
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

    # 4. Qualitative sensor condition
    if any(k in padded for k in (" dat kho ", " do am dat thap ", " dat bi kho ", " dat qua kho ")):
        return {"source": "soil_sensor", "state": "DRY"}
    if any(k in padded for k in (" dat am ", " dat uot ", " dat du am ", " do am dat cao ")):
        return {"source": "soil_sensor", "state": "WET"}
    if any(k in padded for k in (" tieng dong lon ", " co tieng dong ", " am thanh lon ", " tieng on lon ", " vo tay ", " phat hien am thanh ")):
        return {"source": "sound_sensor", "state": "LOUD"}
    if any(k in padded for k in (" yen tinh ", " het tieng dong ", " khong co tieng dong ")):
        return {"source": "sound_sensor", "state": "QUIET"}
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
    dev, act = parse_single_device_and_action(raw_clause, allow_den_asr_homophone=True)
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
    norm = _norm(raw)
    if not _RULE_START_RE.search(f" {norm} "):
        return None

    # Split condition part and action part on "thì" / "thi" / "->"
    m_then = re.search(r"\b(?:thì|thi)\b|->", raw, flags=re.IGNORECASE)
    if not m_then:
        return {"ambiguous": True, "reason": "missing_then"}

    cond_part_raw = raw[: m_then.start()].strip()
    action_part_raw = raw[m_then.end() :].strip()

    # Strip leading rule verbs
    cond_part_raw = re.sub(
        r"^(?:hãy\s+|xin\s+|vui\s+lòng\s+|tạo\s+luật\s+(?:tự\s+động\s+)?|đặt\s+luật\s+(?:tự\s+động\s+)?|"
        r"thêm\s+luật\s+(?:tự\s+động\s+)?|tạo\s+quy\s+tắc\s+|đặt\s+quy\s+tắc\s+|luật\s+tự\s+động\s+)*"
        r"(?:nếu|khi|hễ|cứ)\s+",
        "",
        cond_part_raw,
        flags=re.IGNORECASE,
    ).strip()

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
            r"(?:,|;|\bvà\b|\bva\b|\bđồng\s+thời\b|\bdong\s+thoi\b|\bcùng\s+lúc\b|\bcung\s+luc\b|\bmà\b|\bma\b|\btrong\s+khi\b)",
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

    # Check if this truly needs compound_rules vs legacy 1-to-1 rule:
    is_compound = (
        len(conditions) >= 2
        or len(actions) >= 2
        or len(else_actions) >= 2
        or logic == "OR"
        or any(
            c.get("source") in ("time_window", "house_mode") or "operator" in c
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

    # 2. Polite refusal for removed / unsupported devices (even inside timers, schedules, rules, custom commands)
    if _REMOVED_OR_UNSUPPORTED_DEVICE_RE.search(padded):
        # Allow legitimate queries about what devices exist; refuse commands targeting removed devices
        msg = (
            f"Xin lỗi, thiết bị bạn vừa nhắc không có trong hệ thống. {REMOVED_DEVICE_HINT_VI}"
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
    is_rule_phrase = bool(_RULE_START_RE.search(padded) or re.search(r"\b(?:thi|luat|quy\s+tac)\b", norm))
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

        # Delete compound rule by explicit id or keyword
        m_del_r = re.search(r"^(?:xoa|huy|bo)\s+(?:luat|quy\s+tac)(?:\s+tu\s+dong)?\s+(.+)$", norm)
        if m_del_r:
            tail = m_del_r.group(1).strip()
            if tail not in ("tat ca", "het", "toan bo"):
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
        m_stog_off = re.search(r"^(?:tam\s+dung|tam\s+tat|tat|ngung)\s+lich(?:\s+trinh)?\s*(.*)$", norm)
        m_stog_on = re.search(r"^(?:kich\s+hoat|bat\s+lai|bat|mo\s+lai)\s+lich(?:\s+trinh)?\s*(.*)$", norm)
        if m_stog_off or m_stog_on:
            enabled_val = bool(m_stog_on)
            tail = (m_stog_on.group(1) if m_stog_on else m_stog_off.group(1)).strip()  # type: ignore[union-attr]
            # Parse clock time from raw text (preserving ':' in HH:MM) rather than colon-stripped norm
            m_raw_tail = re.search(r"(?:lịch(?:\s+trình)?|lich(?:\s+trinh)?)\s*(.*)$", raw, flags=re.IGNORECASE)
            raw_tail = m_raw_tail.group(1).strip() if m_raw_tail else raw
            hhmm_t, _, _ = _parse_clock_hhmm_vi(raw_tail)
            if not hhmm_t:
                hhmm_t, _, _ = _parse_clock_hhmm_vi(f"lúc {raw_tail}")
            dev_t, _ = parse_single_device_and_action(raw_tail or tail, allow_den_asr_homophone=True)
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
    if weekdays_found and re.search(r"\b(?:lich|hen\s+gio|dat\s+lich|lap\s+lai|moi|hang)\b", norm):
        hhmm_w, _, cleaned_w = _parse_clock_hhmm_vi(raw)
        dev_w, act_w = parse_single_device_and_action(cleaned_w or raw, allow_den_asr_homophone=True)
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

    # 7. Ambiguity guard for incomplete timer / schedule requests (never silently default missing time or device!)
    is_timer_intent = bool(re.search(r"^(?:hay\s+)?(?:dat\s+)?hen\s+gio\b", norm))
    is_sched_intent = bool(re.search(r"^(?:hay\s+)?dat\s+lich\b", norm))
    if (is_timer_intent or is_sched_intent) and not re.search(r"\b(?:xem|danh\s+sach|xoa|huy|sua|doi|reset)\b", norm):
        hhmm_chk, _, cleaned_chk = _parse_clock_hhmm_vi(raw)
        cd_sec, cleaned_cd = _parse_countdown_seconds(raw)
        dev_chk, act_chk = parse_single_device_and_action(cleaned_chk or cleaned_cd or raw, allow_den_asr_homophone=True)
        if not hhmm_chk and cd_sec <= 0:
            if is_sched_intent:
                return _clarify("Bạn muốn đặt lịch vào lúc mấy giờ?")
            return _clarify("Bạn muốn hẹn giờ sau bao lâu hoặc vào lúc mấy giờ?")
        if not dev_chk or not act_chk:
            return _clarify("Bạn muốn hẹn giờ bật hay tắt thiết bị nào?")

    # 8. General Vietnamese activation/deactivation verbs (e.g. "kích hoạt", "ngưng kích hoạt") for direct 6-device control
    if (
        not is_rule_phrase
        and not re.search(r"\b(?:hen\s+gio|dat\s+lich|lich|tao\s+lenh|xoa|huy|sua|doi|reset)\b", norm)
        and not re.search(r"\b(?:khong|dung|cho|chua)\s+kich\s+hoat\b", norm)
        and re.search(r"\bkich\s+hoat\b", norm)
    ):
        dev_kh, _ = parse_single_device_and_action(raw, default_action="turn_on", allow_den_asr_homophone=True)
        if dev_kh in CANONICAL_6_DEVICES or dev_kh in ("all_lights", "all_devices"):
            act_kh = "open" if dev_kh == "main_door" else "turn_on"
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
