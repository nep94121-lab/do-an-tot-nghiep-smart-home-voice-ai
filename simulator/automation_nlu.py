"""Vietnamese NLU parser for timers, clock schedules, linked rules, and custom scenes."""

from __future__ import annotations

import datetime
import re
from typing import Any

from simulator.automation_repo import (
    create_automation_rule,
    create_schedule,
    delete_automation_rule,
    delete_custom_command,
    delete_schedule,
    find_custom_command_by_text,
    format_device_action_vi,
    list_automation_rules,
    list_custom_commands,
    list_schedules,
    normalize_phrase,
    now_saigon,
    strip_accents,
    upsert_custom_command,
)
from simulator.engine.constants_and_time import ACTION_TO_STATE, DEFAULT_DEVICES

_DEVICE_SYNONYMS: tuple[tuple[str, str], ...] = (
    ("tat ca thiet bi", "all_devices"),
    ("toan bo thiet bi", "all_devices"),
    ("moi thiet bi", "all_devices"),
    ("het thiet bi", "all_devices"),
    ("ca nha", "all_devices"),
    ("tat ca den", "all_lights"),
    ("toan bo den", "all_lights"),
    ("hai den", "all_lights"),
    ("ca hai den", "all_lights"),
    ("ca 2 den", "all_lights"),
    ("het den", "all_lights"),
    ("cac den", "all_lights"),
    ("den phong khach", "living_room_light"),
    ("den khach", "living_room_light"),
    ("den phong ngu", "bedroom_light"),
    ("den ngu", "bedroom_light"),
    ("cua chinh", "main_door"),
    ("cua lon", "main_door"),
    ("cua nha", "main_door"),
    ("cua ra vao", "main_door"),
    ("quat tran", "fan"),
    ("quat dien", "fan"),
    ("dieu hoa", "ac"),
    ("may lanh", "ac"),
    ("coi bao dong", "alarm_siren"),
    ("bao dong", "alarm_siren"),
    ("coi hu", "alarm_siren"),
    ("may bom tuoi cay", "garden_pump"),
    ("may bom", "garden_pump"),
    ("tuoi cay", "garden_pump"),
    ("bom nuoc", "garden_pump"),
)


def parse_single_device_and_action(
    clause: str,
    *,
    default_action: str | None = None,
) -> tuple[str | None, str | None]:
    """Extract primary device/target and canonical action from a single clause."""
    norm = f" {normalize_phrase(clause)} "
    dev: str | None = None
    for kw, target in _DEVICE_SYNONYMS:
        if f" {kw} " in norm:
            dev = target
            break
    if dev is None:
        if " den " in norm:
            dev = "living_room_light"
        elif " quat " in norm:
            dev = "fan"
        elif " cua " in norm:
            dev = "main_door"
        elif " coi " in norm:
            dev = "alarm_siren"
        elif " ac " in norm:
            dev = "ac"
        elif " bom " in norm:
            dev = "garden_pump"

    off_words = ("tat", "dong", "khoa", "ngat", "dung")
    on_words = ("bat", "mo", "khoi dong", "chay", "tuoi")
    act: str | None = None
    for w in off_words:
        if f" {w} " in norm:
            act = "close" if (dev == "main_door" or w in ("dong", "khoa")) else "turn_off"
            break
    if act is None:
        for w in on_words:
            if f" {w} " in norm:
                act = "open" if (dev in ("main_door", "ac") or w == "mo") else "turn_on"
                break
    if act is None:
        act = default_action

    if dev == "main_door" and act in ("turn_on", "turn_off"):
        act = "open" if act == "turn_on" else "close"
    return dev, act


def parse_multi_steps_from_text(text: str) -> list[dict[str, str]]:
    """Parse one or more actions like 'tắt hết đèn và đóng cửa' into explicit device steps."""
    raw_clauses = re.split(r"(?:,|;|\bvà\b|\bva\b|\brồi\b|\broi\b|\bcùng với\b|\bcung voi\b)", text, flags=re.IGNORECASE)
    steps: list[dict[str, str]] = []
    for cl in raw_clauses:
        cl_s = cl.strip()
        if not cl_s:
            continue
        dev, act = parse_single_device_and_action(cl_s)
        if dev and act:
            steps.append({"device_id": dev, "action": act})
    return steps


def _parse_clock_hhmm_vi(text: str) -> tuple[str | None, bool, str]:
    """Parse explicit clock time ('14 giờ 35', '22:30', '7h15 sáng') + daily repeat flag."""
    raw_low = str(text or "").strip().lower()
    norm = strip_accents(raw_low)
    is_daily = bool(
        re.search(r"\b(?:hang ngay|moi ngay|ngay nao cung|lap lai|daily)\b", norm)
    )

    m = re.search(
        r"(?:vào\s+lúc|vao\s+luc|đúng|dung|lúc|luc|vào|vao|tới|toi)?\s*"
        r"(\d{1,2})\s*(?:giờ|gio|h|:)\s*(\d{1,2})?\s*(?:phút|phut|p)?\s*"
        r"(sáng|sang|trưa|trua|chiều|chieu|tối|toi|đêm|dem|am|pm)?",
        norm,
    )
    if not m:
        return None, is_daily, ""

    # Avoid matching duration phrases like "sau 1 giờ nữa" or "trong 2 giờ" as clock time
    prefix = norm[max(0, m.start() - 12):m.start()]
    suffix = norm[m.end():m.end() + 10]
    if re.search(r"\b(?:sau|nua|trong|con)\s*$", prefix) or re.match(r"^\s*(?:nua|sau)\b", suffix):
        if ":" not in m.group(0) and not any(w in norm[:m.start()] for w in ("luc", "vao")):
            return None, is_daily, ""

    has_clock_marker = any(k in norm for k in ("luc", "vao", ":") ) or (m.group(3) is not None) or (
        ("gio" in m.group(0) or "h" in m.group(0)) and "nua" not in norm and "sau " not in norm
    )
    if not has_clock_marker:
        return None, is_daily, ""

    hh = int(m.group(1))
    mm = int(m.group(2) or 0)
    period = (m.group(3) or "").strip()
    if mm < 0 or mm > 59 or hh < 0 or hh > 23:
        return None, is_daily, ""

    if period in ("chieu", "toi", "pm"):
        if 1 <= hh <= 11:
            hh += 12
    elif period == "dem":
        if hh == 12:
            hh = 0
        elif 1 <= hh <= 5:
            hh += 0
        elif 6 <= hh <= 11:
            hh += 12
    elif period == "trua":
        if 1 <= hh <= 10:
            hh += 12
    elif period in ("sang", "am") and hh == 12:
        hh = 0

    cleaned_clause = (raw_low[:m.start()] + " " + raw_low[m.end():]).strip()
    cleaned_clause = re.sub(r"\b(?:hằng|hàng|mỗi)\s+ngày\b", " ", cleaned_clause)
    return f"{hh:02d}:{mm:02d}", is_daily, cleaned_clause


def _parse_countdown_seconds(text: str) -> tuple[float, str]:
    norm = strip_accents(str(text or "").strip().lower())
    m_hr = re.search(r"(\d+(?:\.\d+)?)\s*(?:gio|tieng|h\b)", norm)
    m_min = re.search(r"(\d+(?:\.\d+)?)\s*(?:phut|p\b)", norm)
    m_sec = re.search(r"(\d+(?:\.\d+)?)\s*(?:giay|s\b)", norm)
    hrs = float(m_hr.group(1)) if m_hr else 0.0
    mins = float(m_min.group(1)) if m_min else 0.0
    secs = float(m_sec.group(1)) if m_sec else 0.0
    total = hrs * 3600.0 + mins * 60.0 + secs
    cleaned = norm
    for m in (m_hr, m_min, m_sec):
        if m:
            cleaned = cleaned.replace(m.group(0), " ")
    cleaned = re.sub(r"\b(?:hen gio|hen|sau|nua|dat lich|trong)\b", " ", cleaned)
    return total, cleaned


def _rbac_error_payload(msg: str, tier: int) -> dict[str, Any]:
    return {
        "handled": True,
        "status_code": 403,
        "payload": {
            "ok": False,
            "rbac_blocked": True,
            "tier": tier,
            "error": msg,
            "reply": msg,
            "exact_spoken_reply": msg,
            "rejection_speech": msg,
        },
    }


async def process_automation_nlu_command(
    *,
    text: str,
    engine: Any,
    session: Any,
    source: str = "text_command",
) -> dict[str, Any] | None:
    """Handle automation creation/cancellation/scene-execution before plain device toggle."""
    raw = str(text or "").strip()
    if not raw:
        return None
    norm = strip_accents(raw.lower())
    tier = int(getattr(session, "tier", 3) or 3)
    user_id = str(getattr(session, "user_id", "") or "tuan_anh")
    user_name = str(getattr(session, "display_name", "") or user_id)
    pol = getattr(engine, "system_policies", {}) or {}
    can_custom = tier <= 2 or bool(pol.get("tier3_can_custom_rules", False))
    can_timer = tier <= 2 or bool(pol.get("tier3_can_schedule_timer", False))

    # ------------------------------------------------------------------
    # 1. CREATE / UPDATE CUSTOM COMMAND OR SCENE
    # Examples:
    # - "tạo lệnh 'chế độ ngủ' là tắt hết đèn và đóng cửa"
    # - "tạo scene chế độ ra ngoài gồm tắt toàn bộ thiết bị"
    # ------------------------------------------------------------------
    m_scene = re.match(
        r"^(?:tạo|thêm|đặt|lưu|sửa|cập\s+nhật|đổi)\s+"
        r"(?:khẩu\s+lệnh|lệnh\s+tùy\s+chỉnh|lệnh|ngữ\s+cảnh|kịch\s+bản|scene|che\s+do)\s+"
        r"(?:'([^']+)'|\"([^\"]+)\"|(.+?))\s+"
        r"(?:là|gồm|bao\s+gồm|thành|như\s+sau|:|=|->)\s+(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if not m_scene:
        m_scene = re.match(
            r"^(?:tao|them|dat|luu|sua|cap\s+nhat|doi)\s+"
            r"(?:khau\s+lenh|lenh\s+tuy\s+chinh|lenh|ngu\s+canh|kich\s+ban|scene)\s+"
            r"(?:'([^']+)'|\"([^\"]+)\"|(.+?))\s+"
            r"(?:la|gom|bao\s+gom|thanh|nhu\s+sau|:|=|->)\s+(.+)$",
            strip_accents(raw),
            flags=re.IGNORECASE,
        )
    if m_scene:
        if not can_custom:
            return _rbac_error_payload(
                "Từ chối: Cấp khách (Tầng 3) không có quyền tạo lệnh tùy chỉnh hoặc ngữ cảnh.", tier
            )
        phrase = (m_scene.group(1) or m_scene.group(2) or m_scene.group(3) or "").strip(" '\".,:")
        steps_text = (m_scene.group(4) or "").strip()
        steps = parse_multi_steps_from_text(steps_text)
        if not steps:
            return {
                "handled": True,
                "status_code": 400,
                "payload": {
                    "ok": False,
                    "error": "Không nhận diện được các bước thiết bị cho lệnh tùy chỉnh.",
                    "reply": "Không nhận diện được các bước thiết bị cho lệnh tùy chỉnh.",
                    "exact_spoken_reply": "Không nhận diện được các bước thiết bị cho lệnh tùy chỉnh.",
                },
            }
        # Tier 2 cannot store a scene controlling Tier 1-only devices (main_door, alarm_siren)
        for st in steps:
            allowed_dev, reason_dev = engine.check_device_permission(st["device_id"], actor_tier=tier)
            if not allowed_dev:
                return _rbac_error_payload(reason_dev, tier)

        created = upsert_custom_command(
            phrase=phrase,
            steps=steps,
            owner_user_id=user_id,
            owner_tier=tier,
            owner_name=user_name,
        )
        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        await engine.emit({"type": "custom_command_created", "command": created})
        await engine.emit({"type": "state_snapshot", "snapshot": engine.get_snapshot()})
        spoken = f"Đã lưu lệnh '{created['phrase']}' gồm {created['steps_summary']}."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "kind": "custom_command_created",
                "command": created,
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": engine.get_snapshot(session=session, sync=False),
            },
        }

    # ------------------------------------------------------------------
    # 2. CREATE LINKED AUTOMATION RULE ("khi bật quạt thì bật luôn đèn")
    # MUST run BEFORE plain device action so it does NOT fire immediately!
    # ------------------------------------------------------------------
    m_rule = re.search(
        r"(?:^|\b)(?:tạo\s+luật\s+|thêm\s+luật\s+|đặt\s+luật\s+|tao\s+luat\s+|them\s+luat\s+|dat\s+luat\s+)?"
        r"(?:khi|nếu|hễ|neu|he)\s+(.+?)\s+(?:thì|thi)\s+(?:luôn|cả|tự động|cùng|luon|ca|tu dong|cung)?\s*(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if m_rule and any(k in norm for k in ("khi ", "neu ", "he ", "tao luat", "lien ket")):
        if not can_custom:
            return _rbac_error_payload(
                "Từ chối: Cấp khách (Tầng 3) không được phép tạo luật liên kết tự động.", tier
            )
        when_part = m_rule.group(1).strip()
        then_part_full = m_rule.group(2).strip()
        else_part = ""
        m_else = re.split(r"\b(?:ngược lại|nguoc lai|còn nếu|con neu)\b", then_part_full, maxsplit=1, flags=re.IGNORECASE)
        then_part = m_else[0].strip()
        if len(m_else) > 1:
            else_part = m_else[1].strip()

        w_dev, w_act = parse_single_device_and_action(when_part)
        t_dev, t_act = parse_single_device_and_action(then_part, default_action=w_act)
        if t_dev == "all_lights":
            t_dev = "living_room_light"
        if not w_dev or w_dev in ("all_lights", "all_devices"):
            return None
        if not t_dev or t_dev not in DEFAULT_DEVICES:
            return None
        w_state = ACTION_TO_STATE.get(w_act or "turn_on", "ON")
        if w_dev == "main_door" and w_state in ("ON", "OFF"):
            w_state = "OPEN" if w_state == "ON" else "CLOSED"

        allowed_then, reason_then = engine.check_device_permission(t_dev, actor_tier=tier)
        if not allowed_then:
            return _rbac_error_payload(reason_then, tier)

        e_dev, e_act = ("", "")
        if else_part:
            ed, ea = parse_single_device_and_action(else_part)
            if ed in DEFAULT_DEVICES and ea in ACTION_TO_STATE:
                allowed_else, reason_else = engine.check_device_permission(ed, actor_tier=tier)
                if not allowed_else:
                    return _rbac_error_payload(reason_else, tier)
                e_dev, e_act = ed, ea

        try:
            rule = create_automation_rule(
                owner_user_id=user_id,
                owner_tier=tier,
                when_device_id=w_dev,
                when_state=w_state,
                then_device_id=t_dev,
                then_action=t_act or "turn_on",
                else_device_id=e_dev,
                else_action=e_act,
                owner_name=user_name,
            )
        except ValueError as exc:
            msg_err = str(exc)
            return {
                "handled": True,
                "status_code": 400,
                "payload": {"ok": False, "error": msg_err, "reply": msg_err, "exact_spoken_reply": msg_err},
            }

        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        await engine.emit({"type": "automation_rule_created", "rule": rule})
        await engine.emit({"type": "state_snapshot", "snapshot": engine.get_snapshot()})
        spoken = f"Đã lưu luật liên kết: {rule['label']}."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "kind": "automation_rule_created",
                "rule": rule,
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": engine.get_snapshot(session=session, sync=False),
            },
        }

    # ------------------------------------------------------------------
    # 3. CANCEL / DELETE TIMER, SCHEDULE, RULE, SCENE
    # ------------------------------------------------------------------
    if re.match(r"^(?:hủy|huy|xóa|xoa)\s+(?:hẹn giờ|hen gio|lịch|lich|luật|luat|lệnh|lenh|scene|kịch bản|kich ban)\b", norm):
        if any(k in norm for k in ("hen gio", "hẹn giờ")):
            if not can_timer:
                return _rbac_error_payload("Từ chối: Cấp khách (Tầng 3) không được hủy hẹn giờ.", tier)
            dev, _ = parse_single_device_and_action(raw)
            prev_uid = getattr(engine, "_current_user_id", user_id)
            prev_role = getattr(engine, "_current_role", "ADMIN")
            try:
                engine._current_user_id = user_id
                engine._current_role = str(getattr(session, "role", "MEMBER") or "MEMBER")
                res_c = await engine.update_or_cancel_timer(device_id=dev or "all_devices", operation="cancel")
            finally:
                engine._current_user_id = prev_uid
                engine._current_role = prev_role
            await engine.emit({"type": "state_snapshot", "snapshot": engine.get_snapshot()})
            msg_c = res_c.get("exact_spoken_reply") or res_c.get("error") or "Đã xử lý hủy hẹn giờ."
            return {
                "handled": True,
                "status_code": 200 if res_c.get("ok") else 400,
                "payload": {"ok": bool(res_c.get("ok")), "reply": msg_c, "exact_spoken_reply": msg_c},
            }

        if any(k in norm for k in ("lich", "lịch")):
            if not can_timer:
                return _rbac_error_payload("Từ chối: Cấp khách (Tầng 3) không được xóa lịch.", tier)
            dev, _ = parse_single_device_and_action(raw)
            hhmm, _, _ = _parse_clock_hhmm_vi(raw)
            deleted = 0
            for sc in list_schedules(include_disabled=True):
                if dev and sc["device_id"] != dev:
                    continue
                if hhmm and sc["time_hhmm"] != hhmm:
                    continue
                if tier > 1 and sc["owner_user_id"] != user_id:
                    continue
                if delete_schedule(sc["schedule_id"]):
                    deleted += 1
                    break
            engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
            await engine.emit({"type": "schedule_deleted", "deleted": deleted})
            await engine.emit({"type": "state_snapshot", "snapshot": engine.get_snapshot()})
            spoken = "Đã xóa lịch hẹn theo giờ." if deleted else "Không tìm thấy lịch phù hợp để xóa."
            return {"handled": True, "status_code": 200, "payload": {"ok": deleted > 0, "reply": spoken, "exact_spoken_reply": spoken}}

        if any(k in norm for k in ("luat", "luật")):
            if not can_custom:
                return _rbac_error_payload("Từ chối: Cấp khách (Tầng 3) không được xóa luật liên kết.", tier)
            dev, _ = parse_single_device_and_action(raw)
            deleted = 0
            for r in list_automation_rules(include_disabled=True):
                if dev and r["when_device_id"] != dev and r["then_device_id"] != dev:
                    continue
                if delete_automation_rule(r["rule_id"]):
                    deleted += 1
                    break
            engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
            await engine.emit({"type": "automation_rule_deleted", "deleted": deleted})
            await engine.emit({"type": "state_snapshot", "snapshot": engine.get_snapshot()})
            spoken = "Đã xóa luật liên kết." if deleted else "Không tìm thấy luật phù hợp để xóa."
            return {"handled": True, "status_code": 200, "payload": {"ok": deleted > 0, "reply": spoken, "exact_spoken_reply": spoken}}

        if any(k in norm for k in ("lenh", "scene", "kich ban")):
            if not can_custom:
                return _rbac_error_payload("Từ chối: Cấp khách (Tầng 3) không được xóa lệnh tùy chỉnh.", tier)
            deleted = 0
            for cmd in list_custom_commands(include_disabled=True):
                if cmd["phrase_norm"] in norm:
                    if delete_custom_command(cmd["command_id"]):
                        deleted += 1
                        break
            engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
            await engine.emit({"type": "custom_command_deleted", "deleted": deleted})
            await engine.emit({"type": "state_snapshot", "snapshot": engine.get_snapshot()})
            spoken = "Đã xóa lệnh tùy chỉnh." if deleted else "Không tìm thấy lệnh tùy chỉnh để xóa."
            return {"handled": True, "status_code": 200, "payload": {"ok": deleted > 0, "reply": spoken, "exact_spoken_reply": spoken}}

    # ------------------------------------------------------------------
    # 4. CLOCK SCHEDULE ("bật quạt trần lúc 14 giờ 35", "tắt đèn lúc 22:30 hằng ngày")
    # MUST run BEFORE countdown timer & plain device control!
    # ------------------------------------------------------------------
    hhmm, is_daily, cleaned_clock = _parse_clock_hhmm_vi(raw)
    if hhmm is not None:
        if not can_timer:
            return _rbac_error_payload(
                "Từ chối: Cấp khách (Tầng 3) không có quyền đặt lịch theo giờ.", tier
            )
        dev, act = parse_single_device_and_action(cleaned_clock or raw)
        if not dev or not act:
            dev, act = parse_single_device_and_action(raw)
        if dev and act:
            target_devs = (
                ["living_room_light", "bedroom_light"]
                if dev == "all_lights"
                else (list(DEFAULT_DEVICES.keys()) if dev == "all_devices" else [dev])
            )
            for td in target_devs:
                allowed_td, reason_td = engine.check_device_permission(td, actor_tier=tier)
                if not allowed_td:
                    return _rbac_error_payload(reason_td, tier)

            created_list = []
            for td in target_devs:
                sc = create_schedule(
                    owner_user_id=user_id,
                    owner_tier=tier,
                    device_id=td,
                    action=act,
                    time_hhmm=hhmm,
                    schedule_type="daily" if is_daily else "once",
                    owner_name=user_name,
                )
                created_list.append(sc)
            engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
            await engine.emit({"type": "schedule_created", "schedules": created_list})
            await engine.emit({"type": "state_snapshot", "snapshot": engine.get_snapshot()})
            rep_txt = "hằng ngày " if is_daily else ""
            spoken = f"Đã đặt lịch lúc {hhmm} {rep_txt}{format_device_action_vi(target_devs[0], act)} (múi giờ Asia/Saigon)."
            return {
                "handled": True,
                "status_code": 200,
                "payload": {
                    "ok": True,
                    "kind": "schedule_created",
                    "schedule": created_list[0],
                    "schedules": created_list,
                    "reply": spoken,
                    "exact_spoken_reply": spoken,
                    "snapshot": engine.get_snapshot(session=session, sync=False),
                },
            }

    # ------------------------------------------------------------------
    # 5. COUNTDOWN TIMER ("tắt đèn phòng khách sau 1 phút", "10 giây nữa bật quạt")
    # MUST run BEFORE plain device control!
    # ------------------------------------------------------------------
    has_countdown_cue = bool(
        re.search(
            r"(?:\bsau\s+\d+|\d+(?:\.\d+)?\s*(?:giay|phut|tieng)\b|\bhen\s+\d+|\b\d+(?:\.\d+)?\s*(?:giay|phut|gio)\s+nua\b|\bhen gio\b)",
            norm,
        )
    )
    if has_countdown_cue:
        if not can_timer:
            return _rbac_error_payload(
                "Từ chối: Cấp khách (Tầng 3) không có quyền tạo hẹn giờ thiết bị.", tier
            )
        total_sec, cleaned_cd = _parse_countdown_seconds(raw)
        if total_sec <= 0:
            total_sec = 10.0
        dev, act = parse_single_device_and_action(cleaned_cd)
        if not dev:
            dev, act = parse_single_device_and_action(raw)
        dev = dev or "living_room_light"
        act = act or "turn_on"
        target_devs = (
            ["living_room_light", "bedroom_light"]
            if dev == "all_lights"
            else (list(DEFAULT_DEVICES.keys()) if dev == "all_devices" else [dev])
        )
        for td in target_devs:
            allowed_td, reason_td = engine.check_device_permission(td, actor_tier=tier)
            if not allowed_td:
                return _rbac_error_payload(reason_td, tier)

        prev_uid = getattr(engine, "_current_user_id", user_id)
        prev_role = getattr(engine, "_current_role", "ADMIN")
        try:
            engine._current_user_id = user_id
            engine._current_role = str(getattr(session, "role", "MEMBER") or "MEMBER")
            res_t = await engine.schedule_timer_flexible(device_id=dev, action=act, seconds=total_sec)
        finally:
            engine._current_user_id = prev_uid
            engine._current_role = prev_role
        await engine.emit({"type": "state_snapshot", "snapshot": engine.get_snapshot()})
        spoken_t = res_t.get("exact_spoken_reply") or res_t.get("message") or "Đã đặt hẹn giờ."
        return {
            "handled": True,
            "status_code": 200 if res_t.get("ok") else 400,
            "payload": {
                "ok": bool(res_t.get("ok")),
                "kind": "timer_created",
                "timer": res_t,
                "reply": spoken_t,
                "exact_spoken_reply": spoken_t,
                "snapshot": engine.get_snapshot(session=session, sync=False),
            },
        }

    # ------------------------------------------------------------------
    # 6. RUN CUSTOM COMMAND / SCENE ("chế độ ngủ")
    # ------------------------------------------------------------------
    matched_cmd = find_custom_command_by_text(raw)
    if matched_cmd is not None:
        from simulator.automation_repo import check_steps_rbac

        steps_ok, rbac_err = check_steps_rbac(list(matched_cmd.get("steps") or []), tier)
        if not steps_ok:
            return _rbac_error_payload(rbac_err, tier)
        res_scene = await engine.execute_custom_scene(
            matched_cmd["command_id"],
            session=session,
            source=f"{source} (scene '{matched_cmd['phrase']}')",
        )
        st_code = 403 if res_scene.get("rbac_blocked") else (200 if res_scene.get("ok") else 400)
        return {
            "handled": True,
            "status_code": st_code,
            "payload": {
                "ok": bool(res_scene.get("ok")),
                "rbac_blocked": bool(res_scene.get("rbac_blocked")),
                "kind": "custom_command_executed",
                "command": matched_cmd,
                "results": res_scene.get("results", []),
                "reply": res_scene.get("exact_spoken_reply", ""),
                "exact_spoken_reply": res_scene.get("exact_spoken_reply", ""),
                "snapshot": engine.get_snapshot(session=session, sync=False),
            },
        }

    return None
