"""Natural-language parser & shared dispatcher for Smart Home Automation.

Handles ADDENDUM A-D rules across REST (/api/text_command, /api/voice_command)
and Gemini Live WebSocket tool dispatch:
- Scoped queries for timers/schedules, custom commands, linked rules, members
- Scoped reset ('của tôi' default, Tier 1 can target 'của <tên>' / 'của mọi người')
- 4-step confirmation store per (owner_user_id, session_key), 20s TTL
- Tier 3 immediate HTTP 403 block on all automation/query/mutation paths
- Tier 2 link permission check + +/-60s Tier 1 schedule/timer conflict (HTTP 409)
- Zero-emoji audit logging for every denial
"""

from __future__ import annotations

import re
import time
from typing import Any

from simulator.auth.tier_permissions import can_control_device
from simulator.automation_repo import (
    GUEST_ONLY_TOGGLE_MSG_VI,
    PENDING_CONFIRM_TTL_SEC,
    TIER1_SCHEDULE_CONFLICT_MSG_VI,
    ScheduleConflictError,
    can_user_create_links,
    check_steps_rbac,
    check_tier1_schedule_conflict,
    compute_candidate_schedule_state,
    consume_or_cancel_pending_confirmation,
    create_automation_rule,
    create_pending_confirmation,
    create_schedule,
    delete_automation_rule,
    delete_custom_command,
    delete_schedule,
    find_custom_command_by_text,
    format_device_action_vi,
    get_pending_confirmation,
    list_automation_rules,
    list_custom_commands,
    list_household_members,
    list_pending_timers,
    list_schedules,
    normalize_phrase,
    resolve_target_user_by_query,
    reset_custom_commands_scoped,
    reset_links_scoped,
    reset_timers_and_schedules_scoped,
    set_user_can_create_links,
    strip_accents,
    update_schedule,
    upsert_custom_command,
)
from simulator.database_sqlite import strip_emojis_for_audit
from simulator.engine.audit_logger import append_audit_log
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
    raw_clauses = re.split(
        r"(?:,|;|\bvà\b|\bva\b|\brồi\b|\broi\b|\bcùng với\b|\bcung voi\b)",
        text,
        flags=re.IGNORECASE,
    )
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

    prefix = norm[max(0, m.start() - 12):m.start()]
    suffix = norm[m.end():m.end() + 10]
    if re.search(r"\b(?:sau|nua|trong|con)\s*$", prefix) or re.match(r"^\s*(?:nua|sau)\b", suffix):
        if ":" not in m.group(0) and not any(w in norm[:m.start()] for w in ("luc", "vao")):
            return None, is_daily, ""

    has_clock_marker = (
        any(k in norm for k in ("luc", "vao", ":"))
        or (m.group(3) is not None)
        or (("gio" in m.group(0) or "h" in m.group(0)) and "nua" not in norm and "sau " not in norm)
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


def _resolve_session_key(session: Any, source: str) -> str:
    s_key = str(
        getattr(session, "token_hash", "")
        or getattr(session, "session_id", "")
        or getattr(session, "user_id", "")
        or source
    ).strip()
    return s_key or str(source or "default")


def _session_actor(session: Any) -> tuple[str, int, str, str]:
    tier = int(getattr(session, "tier", 3) or 3)
    user_id = str(getattr(session, "user_id", "") or ("guest" if tier >= 3 else "tuan_anh")).strip()
    user_name = str(getattr(session, "display_name", "") or user_id).strip()
    role = str(getattr(session, "role", "") or ("OWNER" if tier == 1 else ("MEMBER" if tier == 2 else "GUEST"))).strip()
    return user_id, tier, user_name, role


def _log_denial(
    *,
    session: Any,
    source: str,
    category: str,
    message: str,
    detail: dict[str, Any] | None = None,
) -> None:
    user_id, tier, user_name, _ = _session_actor(session)
    clean_msg = strip_emojis_for_audit(message)
    try:
        append_audit_log(
            "SECURITY",
            category,
            clean_msg,
            user_name=user_name or user_id,
            tier=tier,
            details={
                **(detail or {}),
                "user_id": user_id,
                "status": "DENIED",
                "source": source,
            },
        )
    except Exception:
        pass


def _rbac_error_payload(
    msg: str,
    tier: int,
    *,
    status_code: int = 403,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_msg = strip_emojis_for_audit(msg)
    return {
        "handled": True,
        "status_code": int(status_code),
        "payload": {
            "ok": False,
            "rbac_blocked": int(status_code) == 403,
            "conflict_blocked": int(status_code) == 409,
            "conflict_tier1": int(status_code) == 409,
            "http_status": int(status_code),
            "tier": int(tier),
            "error": clean_msg,
            "reply": clean_msg,
            "exact_spoken_reply": clean_msg,
            "rejection_speech": clean_msg,
            **(extra or {}),
        },
    }


def _deny_mutation_error(
    *,
    session: Any,
    source: str,
    category: str,
    msg: str,
    status_code: int = 403,
    target: str = "automation",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _, tier, _, _ = _session_actor(session)
    _log_denial(
        session=session,
        source=source,
        category=category,
        message=msg,
        detail={"target": target, **(extra or {})},
    )
    return _rbac_error_payload(msg, tier, status_code=status_code, extra=extra)


def _expand_targets(dev: str) -> list[str]:
    if dev == "all_lights":
        return ["living_room_light", "bedroom_light"]
    if dev == "all_devices":
        return list(DEFAULT_DEVICES.keys())
    return [dev]


def _classify_confirmation_utterance(raw_text: str) -> str | None:
    """Return 'confirm', 'cancel', or None while distinguishing 'đúng' vs 'đừng'/'dừng'."""
    raw_low = re.sub(r"[?!.,;:]+$", "", str(raw_text or "").strip().lower()).strip()
    if not raw_low:
        return None
    norm = re.sub(r"\s+", " ", normalize_phrase(raw_low)).strip()

    # Check accented cancel words first so 'đừng' / 'dừng' never collide with 'đúng' ('dung')
    if re.search(r"^(?:đừng|dừng|không|hủy|huỷ|thôi|bỏ)(?:\s+(?:ạ|nhé|nha|đi|nữa|nhá|em|bạn))*\s*$", raw_low):
        return "cancel"

    if re.search(
        r"^(?:khong|k|huy|huy bo|thoi|bo|no|cancel)(?:\s+(?:a|nhe|nha|di|nua|nha|em|ban))*\s*$",
        norm,
    ):
        return "cancel"

    if re.search(
        r"^(?:đúng|đúng rồi|đúng vậy|xác nhận|đồng ý|chắc chắn|ừ|ờ|ok|okay|được|được rồi|yes)(?:\s+(?:ạ|nhé|nha|đi|luôn|em|bạn))*\s*$",
        raw_low,
    ):
        return "confirm"

    # Unaccented fallback (safe because accented 'đừng'/'dừng' already returned 'cancel' above)
    if re.search(
        r"^(?:xac nhan|dong y|chac chan|ok|okay|yes|confirm|u|uh|um|duoc|duoc roi|dung|dung roi|dung vay)(?:\s+(?:a|nhe|nha|di|luon|em|ban))*\s*$",
        norm,
    ):
        return "confirm"

    return None


def _ensure_confirmation_question(summary_text: str) -> str:
    txt = str(summary_text or "").strip().rstrip("?!.,;:")
    if not txt:
        txt = "Thực hiện thay đổi này"
    if not txt.lower().endswith("đúng không ạ"):
        txt = f"{txt}, đúng không ạ?"
    else:
        txt = f"{txt}?"
    return txt


async def prepare_pending_mutation(
    *,
    engine: Any,
    session: Any,
    source: str,
    action_kind: str,
    payload: dict[str, Any],
    prompt_summary: str,
    session_key: str = "",
    ttl_sec: float = PENDING_CONFIRM_TTL_SEC,
) -> dict[str, Any]:
    """Store 20s server-side pending draft and return Step-1 question ('... đúng không ạ?')."""
    user_id, tier, user_name, _ = _session_actor(session)
    if tier >= 3:
        return _deny_mutation_error(
            session=session,
            source=source,
            category=f"rbac_deny_{action_kind}",
            msg=GUEST_ONLY_TOGGLE_MSG_VI,
            status_code=403,
            target=action_kind,
        )

    skey = session_key or _resolve_session_key(session, source)
    question = _ensure_confirmation_question(prompt_summary)
    pending = create_pending_confirmation(
        owner_user_id=user_id,
        owner_tier=tier,
        session_key=skey,
        action_kind=action_kind,
        payload=payload,
        prompt_question=question,
        owner_name=user_name,
        ttl_sec=ttl_sec,
    )
    if engine is not None:
        try:
            await engine.emit(
                {
                    "type": "pending_confirmation_created",
                    "pending": pending,
                }
            )
        except Exception:
            pass
    return {
        "handled": True,
        "status_code": 200,
        "payload": {
            "ok": True,
            "confirmed": False,
            "requires_confirmation": True,
            "kind": "confirmation_required",
            "pending_id": pending["pending_id"],
            "confirm_token": pending["pending_id"],
            "expires_at": pending["expires_at"],
            "action_kind": action_kind,
            "prompt_question": question,
            "reply": question,
            "exact_spoken_reply": question,
            "snapshot": engine.get_snapshot(session=session, sync=False) if engine is not None else {},
        },
    }


async def execute_confirmed_mutation(
    *,
    engine: Any,
    session: Any,
    source: str,
    action_kind: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute Step-2 validated mutation against SQLite + engine pools."""
    user_id, tier, user_name, role = _session_actor(session)
    if tier >= 3:
        return _deny_mutation_error(
            session=session,
            source=source,
            category=f"rbac_deny_{action_kind}",
            msg=GUEST_ONLY_TOGGLE_MSG_VI,
            status_code=403,
            target=action_kind,
        )

    if action_kind == "create_custom_command":
        phrase = str(payload.get("phrase") or "").strip()
        steps = list(payload.get("steps") or [])
        allowed_steps, rbac_msg = check_steps_rbac(steps, tier)
        if not allowed_steps:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_custom_command",
                msg=rbac_msg,
                status_code=403,
                target="custom_commands",
            )
        try:
            created = upsert_custom_command(
                phrase=phrase,
                steps=steps,
                owner_user_id=user_id,
                owner_tier=tier,
                owner_name=user_name,
            )
        except ValueError as exc:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="invalid_custom_command",
                msg=str(exc),
                status_code=400,
                target="custom_commands",
            )
        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        append_audit_log("AUTOMATION", "scene_created", f"Lưu ngữ cảnh '{created['phrase']}'", user_name=user_name, tier=tier)
        await engine.emit({"type": "custom_command_created", "command": created})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Xong rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "kind": "custom_command_created",
                "scene": created,
                "command": created,
                "scenes": snap.get("scenes", []),
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "update_custom_command":
        cid = str(payload.get("command_id") or "").strip()
        existing = next((c for c in list_custom_commands(include_disabled=True) if c["command_id"] == cid), None)
        if existing is None:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="scene_not_found",
                msg="Không tìm thấy ngữ cảnh.",
                status_code=404,
                target=cid,
            )
        if tier > 1 and existing["owner_user_id"] != user_id:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="scene_update_blocked",
                msg="Bạn chỉ có quyền sửa ngữ cảnh của chính mình.",
                status_code=403,
                target=cid,
            )
        phrase = str(payload.get("phrase") or existing["phrase"]).strip()
        steps = list(payload.get("steps") or existing["steps"])
        enabled = bool(payload["enabled"]) if "enabled" in payload else bool(existing["enabled"])
        allowed_steps, rbac_msg = check_steps_rbac(steps, tier)
        if not allowed_steps:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_custom_command",
                msg=rbac_msg,
                status_code=403,
                target=cid,
            )
        try:
            scene = upsert_custom_command(
                phrase=phrase,
                steps=steps,
                owner_user_id=existing["owner_user_id"],
                owner_tier=int(existing["owner_tier"]),
                enabled=enabled,
                command_id=cid,
            )
        except ValueError as exc:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="invalid_custom_command",
                msg=str(exc),
                status_code=400,
                target=cid,
            )
        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        append_audit_log("AUTOMATION", "scene_updated", f"Cập nhật ngữ cảnh '{scene['phrase']}'", user_name=user_name, tier=tier)
        await engine.emit({"type": "custom_command_updated", "command": scene})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Xong rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "kind": "custom_command_updated",
                "scene": scene,
                "command": scene,
                "scenes": snap.get("scenes", []),
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "create_automation_rule":
        if not can_user_create_links(user_id, tier, engine=engine):
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_create_link",
                msg="Bạn chưa được chủ nhà cấp quyền tạo liên kết thiết bị.",
                status_code=403,
                target="automation_rules",
            )
        w_dev = str(payload.get("when_device_id") or "")
        w_state = str(payload.get("when_state") or "ON")
        t_dev = str(payload.get("then_device_id") or "")
        t_act = str(payload.get("then_action") or "turn_on")
        e_dev = str(payload.get("else_device_id") or "")
        e_act = str(payload.get("else_action") or "")
        delay_sec = float(payload.get("delay_seconds") or 0.0)
        label = str(payload.get("label") or "").strip()

        allowed_then, reason_then = engine.check_device_permission(t_dev, actor_tier=tier)
        if not allowed_then:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_link_device",
                msg=reason_then,
                status_code=403,
                target=t_dev,
            )
        if e_dev:
            allowed_else, reason_else = engine.check_device_permission(e_dev, actor_tier=tier)
            if not allowed_else:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="rbac_deny_link_device",
                    msg=reason_else,
                    status_code=403,
                    target=e_dev,
                )
        try:
            rule = create_automation_rule(
                owner_user_id=user_id,
                owner_tier=tier,
                when_device_id=w_dev,
                when_state=w_state,
                then_device_id=t_dev,
                then_action=t_act,
                else_device_id=e_dev,
                else_action=e_act,
                delay_seconds=delay_sec,
                label=label,
                owner_name=user_name,
            )
        except ValueError as exc:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="invalid_automation_rule",
                msg=str(exc),
                status_code=400,
                target="automation_rules",
            )
        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        append_audit_log("AUTOMATION", "rule_created", f"Tạo luật {rule['rule_id']} ({rule['label']})", user_name=user_name, tier=tier)
        await engine.emit({"type": "automation_rule_created", "rule": rule})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Xong rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "kind": "automation_rule_created",
                "rule": rule,
                "rules": snap.get("automation_rules", []),
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "create_schedule":
        target_devs = list(payload.get("target_devs") or [])
        act = str(payload.get("action") or "turn_on")
        hhmm = str(payload.get("time_hhmm") or "")
        schedule_type = str(payload.get("schedule_type") or "once")
        run_date_vn = str(payload.get("run_date_vn") or "")
        label = str(payload.get("label") or "")
        for td in target_devs:
            allowed_td, reason_td = engine.check_device_permission(td, actor_tier=tier)
            if not allowed_td:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="rbac_deny_schedule_device",
                    msg=reason_td,
                    status_code=403,
                    target=td,
                )
        conflict_msg = check_tier1_schedule_conflict(
            actor_tier=tier,
            time_hhmm=hhmm,
            schedule_type=schedule_type,
            run_date_vn=run_date_vn,
            engine=engine,
        )
        if conflict_msg:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="tier1_schedule_conflict",
                msg=conflict_msg,
                status_code=409,
                target="schedules",
            )
        try:
            created_list = [
                create_schedule(
                    owner_user_id=user_id,
                    owner_tier=tier,
                    device_id=td,
                    action=act,
                    time_hhmm=hhmm,
                    schedule_type=schedule_type,
                    run_date_vn=run_date_vn,
                    label=label,
                    owner_name=user_name,
                )
                for td in target_devs
            ]
        except ScheduleConflictError as exc:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="tier1_schedule_conflict",
                msg=str(exc),
                status_code=409,
                target="schedules",
            )
        except ValueError as exc:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="invalid_schedule",
                msg=str(exc),
                status_code=400,
                target="schedules",
            )
        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        for sc in created_list:
            append_audit_log("AUTOMATION", "schedule_created", f"Đặt lịch {sc['schedule_id']} ({sc['device_id']}:{sc['action']} lúc {sc['time_hhmm']})", user_name=user_name, tier=tier)
        await engine.emit({"type": "schedule_created", "schedules": created_list, "owner_user_id": user_id})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Xong rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "kind": "schedule_created",
                "schedule": created_list[0] if created_list else None,
                "schedules": snap.get("schedules", []),
                "created_schedules": created_list,
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "update_schedule":
        sid = str(payload.get("schedule_id") or "").strip()
        existing = next((s for s in list_schedules(include_disabled=True) if s["schedule_id"] == sid), None)
        if existing is None:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="schedule_not_found",
                msg="Không tìm thấy lịch hẹn.",
                status_code=404,
                target=sid,
            )
        if tier > 1 and existing["owner_user_id"] != user_id:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="schedule_update_blocked",
                msg="Bạn chỉ có quyền sửa lịch của chính mình.",
                status_code=403,
                target=sid,
            )
        new_dev = payload.get("device_id")
        if new_dev is not None and not can_control_device(tier, str(new_dev)):
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_schedule_device",
                msg=f"Bậc {tier} không có quyền điều khiển {new_dev}.",
                status_code=403,
                target=str(new_dev),
            )
        new_enabled = bool(payload["enabled"]) if payload.get("enabled") is not None else bool(existing.get("enabled", True))
        try:
            cand_hhmm, cand_type, cand_date, cand_enabled = compute_candidate_schedule_state(
                existing,
                time_hhmm=payload.get("time_hhmm"),
                schedule_type=payload.get("schedule_type"),
                run_date_vn=payload.get("run_date_vn"),
                enabled=new_enabled,
            )
        except ValueError as exc:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="invalid_schedule_update",
                msg=str(exc),
                status_code=400,
                target=sid,
            )
        if cand_enabled:
            conflict_msg = check_tier1_schedule_conflict(
                actor_tier=tier,
                time_hhmm=cand_hhmm,
                schedule_type=cand_type,
                run_date_vn=cand_date,
                exclude_schedule_id=sid,
                engine=engine,
            )
            if conflict_msg:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="tier1_schedule_conflict",
                    msg=conflict_msg,
                    status_code=409,
                    target=sid,
                )
        try:
            updated = update_schedule(
                sid,
                time_hhmm=payload.get("time_hhmm"),
                schedule_type=payload.get("schedule_type"),
                run_date_vn=payload.get("run_date_vn"),
                device_id=new_dev,
                action=payload.get("action"),
                enabled=payload.get("enabled"),
                label=payload.get("label"),
                actor_tier=tier,
                engine=engine,
            )
        except ScheduleConflictError as exc:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="tier1_schedule_conflict",
                msg=str(exc),
                status_code=409,
                target=sid,
            )
        except ValueError as exc:
            err_s = str(exc)
            st_c = 409 if "Trùng lịch" in err_s else 400
            return _deny_mutation_error(
                session=session,
                source=source,
                category="invalid_schedule_update",
                msg=err_s,
                status_code=st_c,
                target=sid,
            )
        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        append_audit_log("AUTOMATION", "schedule_updated", f"Cập nhật lịch {sid}", user_name=user_name, tier=tier)
        await engine.emit({"type": "schedule_updated", "schedule": updated})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Xong rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "kind": "schedule_updated",
                "schedule": updated,
                "schedules": snap.get("schedules", []),
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "create_timer":
        dev = str(payload.get("device_id") or "living_room_light")
        act = str(payload.get("action") or "turn_on")
        hours = float(payload.get("hours") or 0.0)
        minutes = float(payload.get("minutes") or 0.0)
        seconds = float(payload.get("seconds") or 0.0)
        repeat = str(payload.get("repeat") or "once").strip() or "once"
        total_sec = hours * 3600.0 + minutes * 60.0 + seconds
        if total_sec <= 0:
            seconds = 10.0
            total_sec = 10.0
        for td in _expand_targets(dev):
            allowed_td, reason_td = engine.check_device_permission(td, actor_tier=tier)
            if not allowed_td:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="rbac_deny_timer_device",
                    msg=reason_td,
                    status_code=403,
                    target=td,
                )
        conflict_msg = check_tier1_schedule_conflict(
            actor_tier=tier,
            fire_epoch=time.time() + total_sec,
            schedule_type=repeat,
            engine=engine,
        )
        if conflict_msg:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="tier1_timer_conflict",
                msg=conflict_msg,
                status_code=409,
                target="timers",
            )
        prev_uid = getattr(engine, "_current_user_id", user_id)
        prev_role = getattr(engine, "_current_role", role)
        try:
            engine._current_user_id = user_id
            engine._current_role = role
            res_t = await engine.schedule_timer_flexible(
                device_id=dev,
                action=act,
                hours=hours,
                minutes=minutes,
                seconds=seconds,
                repeat=repeat,
            )
        finally:
            engine._current_user_id = prev_uid
            engine._current_role = prev_role
        if not res_t.get("ok"):
            err_msg = str(res_t.get("exact_spoken_reply") or res_t.get("error") or "Không thể đặt hẹn giờ.")
            st_code = 409 if "trùng lịch" in err_msg.lower() else (403 if res_t.get("rbac_blocked") else 400)
            return _deny_mutation_error(
                session=session,
                source=source,
                category="timer_create_failed",
                msg=err_msg,
                status_code=st_code,
                target=dev,
            )
        append_audit_log("AUTOMATION", "timer_created", f"Tạo hẹn giờ {res_t.get('timer_id')} ({dev}:{act})", user_name=user_name, tier=tier)
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Xong rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "kind": "timer_created",
                "timer_id": res_t.get("timer_id"),
                "timer": res_t,
                "timers": snap.get("timers", []),
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "modify_timer":
        tid = str(payload.get("timer_id") or "").strip()
        dev_id = str(payload.get("device_id") or "all_devices").strip()
        new_action = str(payload.get("new_action") or payload.get("action") or "").strip()
        hours = float(payload.get("hours") or 0.0)
        minutes = float(payload.get("minutes") or 0.0)
        seconds = float(payload.get("seconds") or 0.0)
        vn_ampm = str(payload.get("vn_time_ampm") or "").strip()
        vn_date = str(payload.get("vn_date") or "").strip()
        repeat = str(payload.get("repeat") or "once").strip() or "once"

        if tid:
            existing_t = engine.active_timers.get(tid) or next(
                (r for r in list_pending_timers() if str(r.get("timer_id") or r.get("id")) == tid),
                None,
            )
            if existing_t is None:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="timer_not_found",
                    msg="Không tìm thấy hẹn giờ cần cập nhật.",
                    status_code=404,
                    target=tid,
                )
            t_owner = str(existing_t.get("owner_user_id") or existing_t.get("owner_id") or "")
            t_owner_tier = int(existing_t.get("owner_tier") or 1)
            if tier > 1 and (t_owner_tier == 1 or t_owner != user_id):
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="timer_update_blocked",
                    msg="Bạn chỉ có quyền sửa hẹn giờ của chính mình.",
                    status_code=403,
                    target=tid,
                )
            target_dev = str(payload.get("device_id") or existing_t.get("raw_target") or existing_t.get("device_id") or "living_room_light")
            target_act = new_action or str(existing_t.get("action") or "turn_on")
            for td in _expand_targets(target_dev):
                allowed_td, reason_td = engine.check_device_permission(td, actor_tier=tier)
                if not allowed_td:
                    return _deny_mutation_error(
                        session=session,
                        source=source,
                        category="rbac_deny_timer_device",
                        msg=reason_td,
                        status_code=403,
                        target=td,
                    )
            total_sec = hours * 3600.0 + minutes * 60.0 + seconds
            if total_sec <= 0 and not vn_ampm:
                total_sec = max(1.0, float(existing_t.get("delay_seconds") or 10.0))
                seconds = total_sec
            if total_sec > 0:
                conflict_msg = check_tier1_schedule_conflict(
                    actor_tier=tier,
                    fire_epoch=time.time() + total_sec,
                    schedule_type=repeat,
                    exclude_timer_id=tid,
                    engine=engine,
                )
                if conflict_msg:
                    return _deny_mutation_error(
                        session=session,
                        source=source,
                        category="tier1_timer_conflict",
                        msg=conflict_msg,
                        status_code=409,
                        target=tid,
                    )
            cancel_res = await engine.cancel_timer_by_id(tid, actor_user_id=user_id, actor_tier=tier)
            if not cancel_res.get("ok"):
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="timer_update_failed",
                    msg=str(cancel_res.get("error") or "Không thể cập nhật hẹn giờ."),
                    status_code=403 if cancel_res.get("rbac_blocked") else 400,
                    target=tid,
                )
            prev_uid = getattr(engine, "_current_user_id", user_id)
            prev_role = getattr(engine, "_current_role", role)
            try:
                engine._current_user_id = user_id
                engine._current_role = role
                res_m = await engine.schedule_timer_flexible(
                    device_id=target_dev,
                    action=target_act,
                    hours=hours,
                    minutes=minutes,
                    seconds=seconds,
                    vn_time_ampm=vn_ampm,
                    vn_date=vn_date,
                    repeat=repeat,
                    reason="Đã sửa hẹn giờ",
                )
            finally:
                engine._current_user_id = prev_uid
                engine._current_role = prev_role
        else:
            prev_uid = getattr(engine, "_current_user_id", user_id)
            prev_role = getattr(engine, "_current_role", role)
            try:
                engine._current_user_id = user_id
                engine._current_role = role
                res_m = await engine.update_or_cancel_timer(
                    device_id=dev_id,
                    operation="modify",
                    new_action=new_action,
                    hours=hours,
                    minutes=minutes,
                    seconds=seconds,
                    vn_time_ampm=vn_ampm,
                    vn_date=vn_date,
                    repeat=repeat,
                )
            finally:
                engine._current_user_id = prev_uid
                engine._current_role = prev_role

        if not res_m.get("ok"):
            err_m = str(res_m.get("exact_spoken_reply") or res_m.get("error") or "Không thể cập nhật hẹn giờ.")
            st_m = 409 if "trùng lịch" in err_m.lower() else (403 if res_m.get("rbac_blocked") else 400)
            return _deny_mutation_error(
                session=session,
                source=source,
                category="timer_update_failed",
                msg=err_m,
                status_code=st_m,
                target=tid or dev_id,
            )
        append_audit_log("AUTOMATION", "timer_updated", f"Cập nhật hẹn giờ {res_m.get('timer_id')}", user_name=user_name, tier=tier)
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Xong rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "kind": "timer_updated",
                "timer_id": res_m.get("timer_id"),
                "timer": res_m,
                "timers": snap.get("timers", []),
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "delete_timer":
        dev = str(payload.get("device_id") or "all_devices")
        tid = str(payload.get("timer_id") or "").strip()
        prev_uid = getattr(engine, "_current_user_id", user_id)
        prev_role = getattr(engine, "_current_role", role)
        try:
            engine._current_user_id = user_id
            engine._current_role = role
            if tid:
                res_c = await engine.cancel_timer_by_id(tid, actor_user_id=user_id, actor_tier=tier)
            else:
                res_c = await engine.update_or_cancel_timer(device_id=dev, operation="cancel")
        finally:
            engine._current_user_id = prev_uid
            engine._current_role = prev_role
        if not res_c.get("ok"):
            err_c = str(res_c.get("exact_spoken_reply") or res_c.get("error") or "Không tìm thấy hẹn giờ phù hợp để hủy.")
            st_code = 403 if res_c.get("rbac_blocked") else (404 if "Không tìm thấy" in err_c else 400)
            return _deny_mutation_error(
                session=session,
                source=source,
                category="delete_timer_denied",
                msg=err_c,
                status_code=st_code,
                target=tid or dev,
            )
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Xong rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "deleted": True,
                "timer_id": tid or None,
                "kind": "timer_deleted",
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "delete_schedule":
        dev = payload.get("device_id")
        hhmm = payload.get("time_hhmm")
        sid = str(payload.get("schedule_id") or "").strip()
        deleted = 0
        deleted_owner = user_id
        if sid:
            existing = next((s for s in list_schedules(include_disabled=True) if s["schedule_id"] == sid), None)
            if existing is None:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="schedule_not_found",
                    msg="Không tìm thấy lịch hẹn.",
                    status_code=404,
                    target=sid,
                )
            if tier > 1 and existing["owner_user_id"] != user_id:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="schedule_delete_blocked",
                    msg="Bạn chỉ có quyền xóa lịch của chính mình.",
                    status_code=403,
                    target=sid,
                )
            deleted_owner = str(existing["owner_user_id"])
            if delete_schedule(sid):
                deleted = 1
                append_audit_log("AUTOMATION", "schedule_deleted", f"Xóa lịch {sid}", user_name=user_name, tier=tier)
        else:
            for sc in list_schedules(include_disabled=True, owner_user_id=(None if tier == 1 else user_id)):
                if dev and sc["device_id"] != dev:
                    continue
                if hhmm and sc["time_hhmm"] != hhmm:
                    continue
                if delete_schedule(sc["schedule_id"]):
                    deleted += 1
                    deleted_owner = str(sc["owner_user_id"])
                    sid = str(sc["schedule_id"])
                    append_audit_log("AUTOMATION", "schedule_deleted", f"Xóa lịch {sid}", user_name=user_name, tier=tier)
                    break
        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        await engine.emit({"type": "schedule_deleted", "schedule_id": sid, "owner_user_id": deleted_owner, "deleted": deleted})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Xong rồi ạ." if deleted else "Không tìm thấy lịch phù hợp để xóa."
        return {
            "handled": True,
            "status_code": 200 if deleted else 404,
            "payload": {
                "ok": deleted > 0,
                "confirmed": deleted > 0,
                "deleted": deleted > 0,
                "schedule_id": sid or None,
                "kind": "schedule_deleted",
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "delete_automation_rule":
        dev = payload.get("device_id")
        rid = str(payload.get("rule_id") or "").strip()
        deleted = 0
        deleted_owner = user_id
        if rid:
            existing = next((r for r in list_automation_rules(include_disabled=True) if r["rule_id"] == rid), None)
            if existing is None:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="rule_not_found",
                    msg="Không tìm thấy luật liên kết.",
                    status_code=404,
                    target=rid,
                )
            if tier > 1 and existing["owner_user_id"] != user_id:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="rule_delete_blocked",
                    msg="Bạn chỉ có quyền xóa luật của chính mình.",
                    status_code=403,
                    target=rid,
                )
            deleted_owner = str(existing["owner_user_id"])
            if delete_automation_rule(rid):
                deleted = 1
                append_audit_log("AUTOMATION", "rule_deleted", f"Xóa luật {rid}", user_name=user_name, tier=tier)
        else:
            for r in list_automation_rules(include_disabled=True, owner_user_id=(None if tier == 1 else user_id)):
                if dev and r["when_device_id"] != dev and r["then_device_id"] != dev:
                    continue
                if delete_automation_rule(r["rule_id"]):
                    deleted += 1
                    deleted_owner = str(r["owner_user_id"])
                    rid = str(r["rule_id"])
                    append_audit_log("AUTOMATION", "rule_deleted", f"Xóa luật {rid}", user_name=user_name, tier=tier)
                    break
        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        await engine.emit({"type": "automation_rule_deleted", "rule_id": rid, "owner_user_id": deleted_owner, "deleted": deleted})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Xong rồi ạ." if deleted else "Không tìm thấy liên kết phù hợp để xóa."
        return {
            "handled": True,
            "status_code": 200 if deleted else 404,
            "payload": {
                "ok": deleted > 0,
                "confirmed": deleted > 0,
                "deleted": deleted > 0,
                "rule_id": rid or None,
                "kind": "automation_rule_deleted",
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "delete_custom_command":
        cid = str(payload.get("command_id") or "").strip()
        phrase_q = normalize_phrase(str(payload.get("phrase") or ""))
        deleted = 0
        deleted_owner = user_id
        if cid:
            existing = next((c for c in list_custom_commands(include_disabled=True) if c["command_id"] == cid), None)
            if existing is None:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="scene_not_found",
                    msg="Không tìm thấy ngữ cảnh.",
                    status_code=404,
                    target=cid,
                )
            if tier > 1 and existing["owner_user_id"] != user_id:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="scene_delete_blocked",
                    msg="Bạn chỉ có quyền xóa ngữ cảnh của chính mình.",
                    status_code=403,
                    target=cid,
                )
            deleted_owner = str(existing["owner_user_id"])
            if delete_custom_command(cid):
                deleted = 1
                append_audit_log("AUTOMATION", "scene_deleted", f"Xóa ngữ cảnh '{existing['phrase']}'", user_name=user_name, tier=tier)
        else:
            for cmd in list_custom_commands(include_disabled=True, owner_user_id=(None if tier == 1 else user_id)):
                if phrase_q and cmd["phrase_norm"] not in phrase_q and phrase_q not in cmd["phrase_norm"]:
                    continue
                if delete_custom_command(cmd["command_id"]):
                    deleted += 1
                    deleted_owner = str(cmd["owner_user_id"])
                    cid = str(cmd["command_id"])
                    append_audit_log("AUTOMATION", "scene_deleted", f"Xóa ngữ cảnh '{cmd['phrase']}'", user_name=user_name, tier=tier)
                    break
        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        await engine.emit({"type": "custom_command_deleted", "command_id": cid, "owner_user_id": deleted_owner, "deleted": deleted})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Xong rồi ạ." if deleted else "Không tìm thấy lệnh tùy chỉnh phù hợp để xóa."
        return {
            "handled": True,
            "status_code": 200 if deleted else 404,
            "payload": {
                "ok": deleted > 0,
                "confirmed": deleted > 0,
                "deleted": deleted > 0,
                "command_id": cid or None,
                "kind": "custom_command_deleted",
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "reset_pool":
        pool_kind = str(payload.get("pool_kind") or "custom_commands").strip().lower()
        target_uid = str(payload.get("target_owner_id") or user_id).strip()
        clear_all = bool(payload.get("clear_all", False))
        if tier > 1 and (clear_all or target_uid != user_id):
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_cross_user_reset",
                msg="Chỉ chủ nhà cấp 1 mới được reset dữ liệu của người khác ạ.",
                status_code=403,
                target=pool_kind,
            )
        removed = 0
        if pool_kind in ("custom_commands", "rules", "commands", "all"):
            removed += reset_custom_commands_scoped(
                target_owner_id=target_uid,
                clear_all=clear_all,
                engine=engine,
            )
        if pool_kind in ("links", "if_else", "all"):
            removed += reset_links_scoped(
                target_owner_id=target_uid,
                clear_all=clear_all,
                engine=engine,
            )
        if pool_kind in ("timers", "schedules", "all"):
            removed += reset_timers_and_schedules_scoped(
                target_owner_id=target_uid,
                clear_all=clear_all,
                engine=engine,
            )
        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        await engine.emit(
            {
                "type": "pool_reset_completed",
                "pool_kind": pool_kind,
                "target_owner_id": None if clear_all else target_uid,
                "clear_all": clear_all,
                "removed": removed,
            }
        )
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Xong rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "kind": "pool_reset_completed",
                "pool_kind": pool_kind,
                "removed": removed,
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "set_member_link_permission":
        if tier != 1:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_grant_link_perm",
                msg="Chỉ chủ nhà cấp 1 mới được cấp hoặc thu hồi quyền liên kết ạ.",
                status_code=403,
                target=str(payload.get("target_user_id") or ""),
            )
        t_uid = str(payload.get("target_user_id") or "").strip()
        members = {m["user_id"]: m for m in list_household_members(include_inactive=True)}
        if t_uid not in members:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="member_not_found",
                msg="Không tìm thấy thành viên.",
                status_code=404,
                target=t_uid,
            )
        target_m = members[t_uid]
        t_name = str(payload.get("target_name") or target_m.get("full_name") or t_uid).strip()
        t_tier = int(payload.get("target_tier") or target_m.get("tier") or 2)
        allowed = bool(payload.get("allowed", False))
        res_u = set_user_can_create_links(
            t_uid,
            allowed,
            owner_tier=t_tier,
            display_name=t_name,
        )
        append_audit_log(
            "SECURITY",
            "member_link_permission_updated",
            f"Chủ nhà cập nhật quyền tạo liên kết cho {t_name} ({t_uid}): {allowed}",
            user_name=user_name,
            tier=1,
        )
        await engine.emit({"type": "member_permission_updated", "member": res_u})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Xong rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "kind": "member_permission_updated",
                **res_u,
                "member": res_u,
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "factory_reset":
        if tier != 1:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_factory_reset",
                msg="Chỉ chủ nhà cấp 1 mới được khôi phục cài đặt gốc ạ.",
                status_code=403,
                target="factory_reset",
            )
        res_rst = await engine.manual_factory_reset()
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = str(res_rst.get("exact_spoken_reply") or "Đã xác nhận. Đã khôi phục cài đặt gốc toàn hệ thống.")
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "kind": "factory_reset",
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    return {
        "handled": True,
        "status_code": 400,
        "payload": {
            "ok": False,
            "error": f"Loại thao tác chưa được hỗ trợ: {action_kind}",
            "reply": "Không thể xác nhận thao tác này ạ.",
            "exact_spoken_reply": "Không thể xác nhận thao tác này ạ.",
        },
    }


async def handle_confirmation_reply(
    *,
    raw_text: str,
    engine: Any,
    session: Any,
    source: str,
    session_key: str = "",
) -> dict[str, Any] | None:
    """Resolve Step-2 confirmation ('xác nhận'/'đúng'/'ừ'/'ok' vs 'không'/'hủy'/>20s TTL)."""
    decision = _classify_confirmation_utterance(raw_text)
    if decision is None:
        return None

    user_id, tier, _, _ = _session_actor(session)
    if tier >= 3:
        return _deny_mutation_error(
            session=session,
            source=source,
            category="rbac_deny_confirmation",
            msg=GUEST_ONLY_TOGGLE_MSG_VI,
            status_code=403,
            target="pending_confirmation",
        )

    skey = session_key or _resolve_session_key(session, source)
    pending, was_expired = get_pending_confirmation(owner_user_id=user_id, session_key=skey)
    if was_expired or pending is None:
        if was_expired:
            spoken = "Đã hủy."
            return {
                "handled": True,
                "status_code": 200,
                "payload": {
                    "ok": False,
                    "cancelled": True,
                    "expired": True,
                    "kind": "confirmation_expired",
                    "reply": spoken,
                    "exact_spoken_reply": spoken,
                    "snapshot": engine.get_snapshot(session=session, sync=False) if engine is not None else {},
                },
            }
        return None

    if decision == "cancel":
        consume_or_cancel_pending_confirmation(
            pending["pending_id"],
            owner_user_id=user_id,
            new_status="cancelled",
        )
        if engine is not None:
            try:
                await engine.emit({
                    "type": "pending_confirmation_cancelled",
                    "pending_id": pending["pending_id"],
                    "owner_user_id": user_id,
                })
            except Exception:
                pass
        spoken = "Đã hủy."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": False,
                "cancelled": True,
                "kind": "confirmation_cancelled",
                "pending_id": pending["pending_id"],
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": engine.get_snapshot(session=session, sync=False) if engine is not None else {},
            },
        }

    consumed = consume_or_cancel_pending_confirmation(
        pending["pending_id"],
        owner_user_id=user_id,
        new_status="confirmed",
    )
    if consumed is None:
        spoken = "Đã hủy."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": False,
                "cancelled": True,
                "expired": True,
                "kind": "confirmation_expired",
                "reply": spoken,
                "exact_spoken_reply": spoken,
            },
        }

    return await execute_confirmed_mutation(
        engine=engine,
        session=session,
        source=source,
        action_kind=consumed["action_kind"],
        payload=consumed["payload"],
    )


def _extract_target_member_scope(raw_text: str) -> tuple[bool, str | None]:
    """Extract ('của mọi người', '<target member phrase>') from queries/resets."""
    raw = str(raw_text or "").strip()
    norm = f" {normalize_phrase(raw)} "
    if any(k in norm for k in (" cua moi nguoi ", " tat ca moi nguoi ", " toan bo moi nguoi ", " toan he thong ")):
        return True, None
    m = re.search(
        r"\bcủa\s+([a-zA-Z0-9_\u00C0-\u024F\u1E00-\u1EFF\s]{1,40})$",
        raw.strip().rstrip("?!.,"),
        flags=re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r"\bcua\s+([a-zA-Z0-9_\s]{1,40})$",
            norm.strip(),
            flags=re.IGNORECASE,
        )
    if not m:
        return False, None
    cand = m.group(1).strip()
    cand_norm = normalize_phrase(cand)
    if cand_norm in ("toi", "minh", "ban than", "nha minh"):
        return False, None
    return False, cand


def _resolve_query_owner_scope(
    *,
    session: Any,
    target_query: str | None = None,
    include_all_default: bool = True,
) -> tuple[str | None, str | None]:
    """Resolve SQLite owner filter per ADDENDUM A. Returns (owner_user_id_or_None, error_msg)."""
    user_id, tier, _, _ = _session_actor(session)
    if tier >= 3:
        return user_id, GUEST_ONLY_TOGGLE_MSG_VI
    if tier >= 2:
        # Tier 2 strictly sees only own pool
        return user_id, None
    if target_query:
        resolved = resolve_target_user_by_query(target_query)
        if resolved is None:
            return None, f"Không tìm thấy thành viên '{target_query}' trong hệ thống ạ."
        return str(resolved["user_id"]), None
    return (None if include_all_default else user_id), None


def format_pool_items_summary(
    *,
    pool_kind: str,
    engine: Any,
    session: Any,
    target_query: str | None = None,
) -> tuple[bool, int, str, dict[str, Any]]:
    """Shared formatter for Tier 1 (all + 'của <tên>') / Tier 2 (own) / Tier 3 (403) queries."""
    user_id, tier, user_name, _ = _session_actor(session)
    if tier >= 3:
        return False, 403, GUEST_ONLY_TOGGLE_MSG_VI, {}

    if pool_kind == "members":
        members = list_household_members(include_inactive=False)
        if tier >= 2:
            spoken = f"Bạn đang đăng nhập tài khoản {user_name} (cấp {tier}). Tài khoản cấp {tier} chỉ xem thông tin của chính mình ạ."
            return True, 200, spoken, {"members": [{"user_id": user_id, "display_name": user_name, "tier": tier}]}
        if not members:
            return True, 200, "Hiện chưa có thành viên nào trong hệ thống ạ.", {"members": []}
        parts = [f"{m.get('display_name') or m.get('full_name') or m['user_id']} (cấp {m['tier']})" for m in members]
        spoken = f"Nhà có {len(members)} thành viên: {', '.join(parts)}."
        return True, 200, spoken, {"members": members}

    owner_filter, err_scope = _resolve_query_owner_scope(
        session=session,
        target_query=target_query,
        include_all_default=True,
    )
    if err_scope:
        return False, 404, err_scope, {}

    if pool_kind == "timers":
        timers = list_pending_timers(owner_user_id=owner_filter)
        schedules = list_schedules(include_disabled=False, owner_user_id=owner_filter)
        if tier >= 2:
            timers = [t for t in timers if str(t.get("owner_user_id") or "") == user_id]
            schedules = [s for s in schedules if str(s.get("owner_user_id") or "") == user_id]
        items: list[str] = []
        for t in timers:
            rem = max(1, int(round(float(t.get("fire_epoch") or 0.0) - time.time())))
            act_txt = format_device_action_vi(t["device_id"], t["action"])
            own = str(t.get("owner_name") or t.get("owner_user_id") or "")
            items.append(f"{act_txt} còn {rem} giây" + (f" của {own}" if tier == 1 else ""))
        for sc in schedules:
            act_txt = format_device_action_vi(sc["device_id"], sc["action"])
            rep = " hằng ngày" if sc.get("schedule_type") == "daily" else ""
            own = str(sc.get("owner_name") or sc.get("owner_user_id") or "")
            items.append(f"{act_txt} lúc {sc['time_hhmm']}{rep}" + (f" của {own}" if tier == 1 else ""))
        if not items:
            spoken = "Hiện chưa có hẹn giờ hoặc lịch hẹn nào ạ."
        else:
            prefix = f"Hiện có {len(items)} hẹn giờ" if tier == 1 else f"Bạn có {len(items)} hẹn giờ"
            spoken = f"{prefix}: {'; '.join(items)}."
        return True, 200, spoken, {"timers": timers, "schedules": schedules}

    if pool_kind == "custom_commands":
        cmds = list_custom_commands(include_disabled=False, owner_user_id=owner_filter)
        if tier >= 2:
            cmds = [c for c in cmds if str(c.get("owner_user_id") or "") == user_id]
        if not cmds:
            spoken = "Hiện chưa có lệnh custom nào ạ."
            return True, 200, spoken, {"custom_commands": []}
        items = []
        for c in cmds:
            own = str(c.get("owner_name") or c.get("owner_user_id") or "")
            seg = f"'{c['phrase']}' ({c['steps_summary']})"
            if tier == 1:
                seg += f" của {own}"
            items.append(seg)
        prefix = f"Hiện có {len(items)} lệnh custom" if tier == 1 else f"Bạn có {len(items)} lệnh custom"
        spoken = f"{prefix}: {'; '.join(items)}."
        return True, 200, spoken, {"custom_commands": cmds}

    if pool_kind == "links":
        rules = list_automation_rules(include_disabled=False, owner_user_id=owner_filter)
        if tier >= 2:
            rules = [r for r in rules if str(r.get("owner_user_id") or "") == user_id]
        if not rules:
            spoken = "Hiện chưa có liên kết thiết bị nào ạ."
            return True, 200, spoken, {"automation_rules": []}
        items = []
        for r in rules:
            own = str(r.get("owner_name") or r.get("owner_user_id") or "")
            seg = str(r.get("label") or f"{r['when_device_id']} -> {r['then_device_id']}")
            if tier == 1:
                seg += f" của {own}"
            items.append(seg)
        prefix = f"Hiện có {len(items)} liên kết" if tier == 1 else f"Bạn có {len(items)} liên kết"
        spoken = f"{prefix}: {'; '.join(items)}."
        return True, 200, spoken, {"automation_rules": rules}

    return False, 400, "Loại truy vấn chưa được hỗ trợ ạ.", {}


def answer_pool_or_member_query(
    *,
    raw_text: str,
    engine: Any,
    session: Any,
    source: str,
) -> dict[str, Any] | None:
    """Detect and answer ADDENDUM A pool/member questions."""
    norm = f" {normalize_phrase(raw_text)} "
    is_mutation_verb = any(
        w in norm for w in (" tao ", " them ", " sua ", " xoa ", " huy ", " reset ", " dat lai ", " bat ", " tat ", " mo ", " dong ")
    )
    has_question_cue = (
        "?" in str(raw_text)
        or any(
            q in norm
            for q in (
                " nao ", " gi ", " may ", " bao nhieu ", " danh sach ", " liet ke ",
                " co nhung ", " co may ", " xem ", " hien co ", " ai ", " ten gi ", " cap may ",
            )
        )
    )
    if not has_question_cue:
        return None

    pool_kind: str | None = None
    if any(k in norm for k in (" thanh vien", " gia dinh", " cap may", " ten gi", " trong nha co ai", " co nhung ai")):
        pool_kind = "members"
    elif any(k in norm for k in (" lenh custom", " lenh tuy chinh", " khau lenh", " nhung lenh", " cac lenh", " scene", " kich ban")):
        pool_kind = "custom_commands"
    elif any(k in norm for k in (" lien ket", " luat lien ket", " luat tu dong", " nhung luat", " cac luat")):
        pool_kind = "links"
    elif any(k in norm for k in (" hen gio", " lich hen", " nhung lich", " cac lich")):
        pool_kind = "timers"

    if pool_kind is None:
        return None
    if is_mutation_verb and not any(q in norm for q in (" nao", " may", " gi", " co nhung", " danh sach", " liet ke", " bao nhieu")):
        return None

    _, tier, _, _ = _session_actor(session)
    if tier >= 3:
        return _deny_mutation_error(
            session=session,
            source=source,
            category=f"rbac_deny_query_{pool_kind}",
            msg=GUEST_ONLY_TOGGLE_MSG_VI,
            status_code=403,
            target=pool_kind,
        )

    clear_all, target_q = _extract_target_member_scope(raw_text)
    if clear_all:
        target_q = None
    ok, code, spoken, data = format_pool_items_summary(
        pool_kind=pool_kind,
        engine=engine,
        session=session,
        target_query=target_q,
    )
    return {
        "handled": True,
        "status_code": code,
        "payload": {
            "ok": ok,
            "kind": f"query_{pool_kind}",
            **data,
            "reply": spoken,
            "exact_spoken_reply": spoken,
            "snapshot": engine.get_snapshot(session=session, sync=False) if engine is not None else {},
        },
    }


def _detect_member_link_permission_intent(raw_text: str) -> tuple[bool, str] | None:
    """Detect Tier 1 commands like 'cấp quyền tạo liên kết cho Mẹ' / 'thu hồi quyền liên kết của Mẹ'."""
    norm = normalize_phrase(raw_text)
    if "lien ket" not in norm or "quyen" not in norm:
        return None
    is_grant = bool(re.search(r"\b(?:cap|cho phep|mo|bat|cho)\b", norm))
    is_revoke = bool(re.search(r"\b(?:thu hoi|tat|bo|khoa|cam|tuoc|xoa)\b", norm))
    if not is_grant and not is_revoke:
        return None
    allowed = is_grant and not is_revoke
    m_target = re.search(
        r"(?:cho|của|cua)\s+([a-zA-Z0-9_\u00C0-\u024F\u1E00-\u1EFF\s]{1,40})$",
        str(raw_text or "").strip().rstrip("?!.,"),
        flags=re.IGNORECASE,
    )
    if not m_target:
        m_target = re.search(r"\b([A-Za-zÀ-ỹ][A-Za-zÀ-ỹ0-9_\s]{0,25})\s+(?:tạo|tao)\s+(?:liên kết|lien ket)", str(raw_text or ""), flags=re.IGNORECASE)
    target_name = (m_target.group(1).strip() if m_target else "")
    target_name = re.sub(r"\b(?:tạo|tao|liên kết|lien ket|quyền|quyen)\b", "", target_name, flags=re.IGNORECASE).strip()
    if not target_name:
        return None
    return allowed, target_name


def _detect_scoped_reset_intent(raw_text: str) -> tuple[str, bool, str | None] | None:
    """Detect scoped reset intents ('reset lệnh custom', 'reset liên kết', 'xóa hẹn giờ')."""
    raw_clean = str(raw_text or "").strip()
    norm = normalize_phrase(raw_clean)
    has_reset = bool(
        re.match(
            r"^(?:reset|dat lai|xoa het|xoa toan bo|xoa tat ca|xoa moi|huy het|huy toan bo|huy tat ca|huy moi|don sach)\b",
            norm,
        )
    )
    has_bare_timer_reset = bool(re.match(r"^(?:xoa|huy)\s+(?:hen gio|lich hen)(?:\s+cua\s+.+)?$", norm))
    if not has_reset and not has_bare_timer_reset:
        return None

    if any(k in norm for k in ("lenh custom", "lenh tuy chinh", "khau lenh", "scene", "kich ban", "lenh")):
        pool_kind = "custom_commands"
    elif any(k in norm for k in ("lien ket", "luat")):
        pool_kind = "links"
    elif any(k in norm for k in ("hen gio", "lich")):
        pool_kind = "timers"
    elif any(k in norm for k in ("tat ca", "toan bo")):
        pool_kind = "all"
    else:
        return None

    clear_all, target_q = _extract_target_member_scope(raw_clean)
    return pool_kind, clear_all, target_q


async def process_automation_nlu_command(
    *,
    text: str,
    engine: Any,
    session: Any,
    source: str = "text_command",
    session_key: str = "",
) -> dict[str, Any] | None:
    """Parse and execute or stage (4-step confirm) Vietnamese automation commands."""
    raw = str(text or "").strip()
    if not raw:
        return None

    user_id, tier, user_name, _ = _session_actor(session)
    norm = normalize_phrase(raw)
    skey = session_key or _resolve_session_key(session, source)

    # ------------------------------------------------------------------
    # STEP 0. PENDING 4-STEP CONFIRMATION REPLY ("xác nhận"/"đúng"/"ừ"/"ok" vs "không"/"hủy")
    # ------------------------------------------------------------------
    conf_res = await handle_confirmation_reply(
        raw_text=raw,
        engine=engine,
        session=session,
        source=source,
        session_key=skey,
    )
    if conf_res is not None:
        return conf_res

    # ------------------------------------------------------------------
    # STEP 1. ADDENDUM A SCOPED QUERIES (timers, custom commands, links, members)
    # ------------------------------------------------------------------
    query_res = answer_pool_or_member_query(
        raw_text=raw,
        engine=engine,
        session=session,
        source=source,
    )
    if query_res is not None:
        return query_res

    # ------------------------------------------------------------------
    # STEP 2. ADDENDUM D MEMBER LINK-PERMISSION GRANT / REVOKE
    # ------------------------------------------------------------------
    perm_intent = _detect_member_link_permission_intent(raw)
    if perm_intent is not None:
        allowed_flag, target_name = perm_intent
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_grant_link_perm",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target="link_permission",
            )
        if tier != 1:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_grant_link_perm",
                msg="Chỉ chủ nhà cấp 1 mới được cấp hoặc thu hồi quyền liên kết ạ.",
                status_code=403,
                target="link_permission",
            )
        resolved = resolve_target_user_by_query(target_name)
        if resolved is None:
            return {
                "handled": True,
                "status_code": 404,
                "payload": {
                    "ok": False,
                    "error": f"Không tìm thấy thành viên '{target_name}' ạ.",
                    "reply": f"Không tìm thấy thành viên '{target_name}' ạ.",
                    "exact_spoken_reply": f"Không tìm thấy thành viên '{target_name}' ạ.",
                },
            }
        verb_txt = "Cấp quyền tạo liên kết cho" if allowed_flag else "Thu hồi quyền tạo liên kết của"
        return await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="set_member_link_permission",
            payload={
                "target_user_id": resolved["user_id"],
                "target_name": resolved["display_name"],
                "target_tier": resolved["tier"],
                "allowed": allowed_flag,
            },
            prompt_summary=f"{verb_txt} {resolved['display_name']}",
        )

    # ------------------------------------------------------------------
    # STEP 3. ADDENDUM B SCOPED RESET ("reset lệnh custom", "reset liên kết", "xóa hẹn giờ")
    # ------------------------------------------------------------------
    reset_intent = _detect_scoped_reset_intent(raw)
    if reset_intent is not None:
        pool_kind, clear_all, target_q = reset_intent
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category=f"rbac_deny_reset_{pool_kind}",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target=pool_kind,
            )
        target_uid = user_id
        target_label = "của bạn"
        if clear_all:
            if tier != 1:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category=f"rbac_deny_reset_all_{pool_kind}",
                    msg="Chỉ chủ nhà cấp 1 mới được reset dữ liệu của mọi người ạ.",
                    status_code=403,
                    target=pool_kind,
                )
            target_label = "của mọi người"
        elif target_q:
            resolved = resolve_target_user_by_query(target_q)
            if resolved is None:
                return {
                    "handled": True,
                    "status_code": 404,
                    "payload": {
                        "ok": False,
                        "error": f"Không tìm thấy thành viên '{target_q}' ạ.",
                        "reply": f"Không tìm thấy thành viên '{target_q}' ạ.",
                        "exact_spoken_reply": f"Không tìm thấy thành viên '{target_q}' ạ.",
                    },
                }
            if tier != 1 and resolved["user_id"] != user_id:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category=f"rbac_deny_cross_reset_{pool_kind}",
                    msg="Chỉ chủ nhà cấp 1 mới được reset dữ liệu của người khác ạ.",
                    status_code=403,
                    target=str(resolved["user_id"]),
                )
            target_uid = str(resolved["user_id"])
            target_label = f"của {resolved['display_name']}"

        pool_vi = {
            "custom_commands": "Reset lệnh custom",
            "links": "Reset liên kết thiết bị",
            "timers": "Xóa toàn bộ hẹn giờ và lịch hẹn",
            "all": "Reset toàn bộ dữ liệu tùy chỉnh",
        }.get(pool_kind, "Reset dữ liệu")
        return await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="reset_pool",
            payload={
                "pool_kind": pool_kind,
                "target_owner_id": target_uid,
                "clear_all": clear_all,
                "target_display_name": target_label,
            },
            prompt_summary=f"{pool_vi} {target_label}",
        )

    # ------------------------------------------------------------------
    # STEP 4. CREATE / UPDATE CUSTOM COMMAND OR SCENE
    # Examples:
    # - "tạo lệnh 'chế độ ngủ' là tắt hết đèn và đóng cửa"
    # - "tạo lệnh mới 'giờ đi ngủ' là tắt hết đèn"
    # ------------------------------------------------------------------
    m_scene = re.match(
        r"^(?:tạo|thêm|đặt|lưu|sửa|cập\s+nhật|đổi)\s+"
        r"(?:khẩu\s+lệnh|lệnh\s+(?:tùy\s+chỉnh|custom)|lệnh|ngữ\s+cảnh|kịch\s+bản|scene|chế\s+độ)"
        r"(?:\s+mới|\s+moi)?\s+"
        r"(?:'([^']+)'|\"([^\"]+)\"|(.+?))\s+"
        r"(?:là|gồm|bao\s+gồm|thành|như\s+sau|:|=|->)\s+(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if not m_scene:
        m_scene = re.match(
            r"^(?:tao|them|dat|luu|sua|cap\s+nhat|doi)\s+"
            r"(?:khau\s+lenh|lenh\s+(?:tuy\s+chinh|custom)|lenh|ngu\s+canh|kich\s+ban|scene|che\s+do)"
            r"(?:\s+moi)?\s+"
            r"(?:'([^']+)'|\"([^\"]+)\"|(.+?))\s+"
            r"(?:la|gom|bao\s+gom|thanh|nhu\s+sau|:|=|->)\s+(.+)$",
            strip_accents(raw),
            flags=re.IGNORECASE,
        )
    if m_scene:
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_create_custom_command",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target="custom_commands",
            )
        phrase = (m_scene.group(1) or m_scene.group(2) or m_scene.group(3) or "").strip(" '\".,:")
        steps_text = (m_scene.group(4) or "").strip()
        steps = parse_multi_steps_from_text(steps_text)
        if not steps:
            msg_empty = "Không nhận diện được các bước thiết bị cho lệnh tùy chỉnh."
            return {
                "handled": True,
                "status_code": 400,
                "payload": {
                    "ok": False,
                    "error": msg_empty,
                    "reply": msg_empty,
                    "exact_spoken_reply": msg_empty,
                },
            }
        for st in steps:
            allowed_dev, reason_dev = engine.check_device_permission(st["device_id"], actor_tier=tier)
            if not allowed_dev:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="rbac_deny_custom_command_device",
                    msg=reason_dev,
                    status_code=403,
                    target=str(st["device_id"]),
                )
        steps_summary = ", ".join(format_device_action_vi(st["device_id"], st["action"]) for st in steps)
        return await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="create_custom_command",
            payload={"phrase": phrase, "steps": steps},
            prompt_summary=f"Tạo lệnh '{phrase}' gồm {steps_summary}",
        )

    # ------------------------------------------------------------------
    # STEP 5. CREATE LINKED AUTOMATION RULE
    # Examples:
    # - "khi bật quạt thì bật luôn đèn"
    # - "tạo liên kết mới khi bật quạt thì bật đèn"
    # - "từ giờ mở quạt thì mở cả đèn"
    # ------------------------------------------------------------------
    m_rule = re.search(
        r"(?:^|\b)(?:(?:tạo|thêm|đặt|tao|them|dat)\s+(?:luật|luat|liên\s+kết|lien\s+ket)(?:\s+mới|\s+moi)?\s*)?"
        r"(?:khi|nếu|hễ|từ\s+giờ|neu|he|tu\s+gio)\s+(.+?)\s+(?:thì|thi)\s+(?:luôn|cả|tự\s+động|cùng|luon|ca|tu\s+dong|cung)?\s*(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if not m_rule:
        m_rule = re.search(
            r"^(?:tạo|thêm|đặt|tao|them|dat)\s+(?:luật|luat|liên\s+kết|lien\s+ket)(?:\s+mới|\s+moi)?(?:\s+là|\s+la|\s*:)?\s+"
            r"(.+?)\s+(?:thì|thi)\s+(?:luôn|cả|tự\s+động|cùng|luon|ca|tu\s+dong|cung)?\s*(.+)$",
            raw,
            flags=re.IGNORECASE,
        )
    if m_rule and any(k in norm for k in ("khi ", "neu ", "he ", "tu gio", "tao luat", "lien ket")):
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_create_link",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target="automation_rules",
            )
        if not can_user_create_links(user_id, tier, engine=engine):
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_create_link_permission",
                msg="Bạn chưa được chủ nhà cấp quyền tạo liên kết thiết bị.",
                status_code=403,
                target="automation_rules",
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
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_link_then_device",
                msg=reason_then,
                status_code=403,
                target=t_dev,
            )

        e_dev, e_act = ("", "")
        if else_part:
            ed, ea = parse_single_device_and_action(else_part)
            if ed in DEFAULT_DEVICES and ea in ACTION_TO_STATE:
                allowed_else, reason_else = engine.check_device_permission(ed, actor_tier=tier)
                if not allowed_else:
                    return _deny_mutation_error(
                        session=session,
                        source=source,
                        category="rbac_deny_link_else_device",
                        msg=reason_else,
                        status_code=403,
                        target=ed,
                    )
                e_dev, e_act = ed, ea

        if w_dev == t_dev:
            msg_cycle = "Không thể tạo liên kết tự kích hoạt chính thiết bị nguồn."
            return _deny_mutation_error(
                session=session,
                source=source,
                category="invalid_automation_rule_cycle",
                msg=msg_cycle,
                status_code=400,
                target=w_dev,
            )

        w_label = format_device_action_vi(w_dev, w_act or "turn_on")
        t_label = format_device_action_vi(t_dev, t_act or "turn_on")
        prompt_desc = f"Tạo liên kết khi {w_label} thì {t_label}"
        if e_dev:
            prompt_desc += f", ngược lại {format_device_action_vi(e_dev, e_act)}"
        return await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="create_automation_rule",
            payload={
                "when_device_id": w_dev,
                "when_state": w_state,
                "then_device_id": t_dev,
                "then_action": t_act or "turn_on",
                "else_device_id": e_dev,
                "else_action": e_act,
            },
            prompt_summary=prompt_desc,
        )

    # ------------------------------------------------------------------
    # STEP 6. CANCEL / DELETE SINGLE TIMER, SCHEDULE, RULE, CUSTOM COMMAND
    # ------------------------------------------------------------------
    if re.match(r"^(?:huy|xoa)\s+(?:hen gio|lich|luat|lien ket|lenh|scene|kich ban)\b", norm):
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_delete_automation",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target="automation",
            )
        if "hen gio" in norm:
            dev, _ = parse_single_device_and_action(raw)
            dev_target = dev or "all_devices"
            dev_label = DEFAULT_DEVICES.get(dev_target, {}).get("name", dev_target)
            return await prepare_pending_mutation(
                engine=engine,
                session=session,
                source=source,
                session_key=skey,
                action_kind="delete_timer",
                payload={"device_id": dev_target},
                prompt_summary=f"Hủy hẹn giờ {dev_label}" if dev else "Hủy hẹn giờ hiện tại",
            )
        if "lich" in norm:
            dev, _ = parse_single_device_and_action(raw)
            hhmm, _, _ = _parse_clock_hhmm_vi(raw)
            desc = "Xóa lịch hẹn"
            if dev:
                desc += f" {DEFAULT_DEVICES.get(dev, {}).get('name', dev)}"
            if hhmm:
                desc += f" lúc {hhmm}"
            return await prepare_pending_mutation(
                engine=engine,
                session=session,
                source=source,
                session_key=skey,
                action_kind="delete_schedule",
                payload={"device_id": dev, "time_hhmm": hhmm},
                prompt_summary=desc,
            )
        if any(k in norm for k in ("luat", "lien ket")):
            dev, _ = parse_single_device_and_action(raw)
            desc = "Xóa liên kết" + (f" liên quan tới {DEFAULT_DEVICES.get(dev, {}).get('name', dev)}" if dev else "")
            return await prepare_pending_mutation(
                engine=engine,
                session=session,
                source=source,
                session_key=skey,
                action_kind="delete_automation_rule",
                payload={"device_id": dev},
                prompt_summary=desc,
            )
        if any(k in norm for k in ("lenh", "scene", "kich ban")):
            phrase_clean = re.sub(
                r"^(?:huy|xoa)\s+(?:lenh tuy chinh|lenh custom|lenh|scene|kich ban)\s*",
                "",
                norm,
            ).strip(" '\".,:")
            return await prepare_pending_mutation(
                engine=engine,
                session=session,
                source=source,
                session_key=skey,
                action_kind="delete_custom_command",
                payload={"phrase": phrase_clean or norm},
                prompt_summary=f"Xóa lệnh '{phrase_clean or raw}'",
            )

    # ------------------------------------------------------------------
    # STEP 7. CLOCK SCHEDULE ("bật quạt trần lúc 14 giờ 35", "tắt đèn lúc 22:30 hằng ngày")
    # ------------------------------------------------------------------
    hhmm, is_daily, cleaned_clock = _parse_clock_hhmm_vi(raw)
    if hhmm is not None:
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_schedule",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target="schedules",
            )
        dev, act = parse_single_device_and_action(cleaned_clock or raw)
        if not dev or not act:
            dev, act = parse_single_device_and_action(raw)
        if dev and act:
            target_devs = _expand_targets(dev)
            for td in target_devs:
                allowed_td, reason_td = engine.check_device_permission(td, actor_tier=tier)
                if not allowed_td:
                    return _deny_mutation_error(
                        session=session,
                        source=source,
                        category="rbac_deny_schedule_device",
                        msg=reason_td,
                        status_code=403,
                        target=td,
                    )
            schedule_type = "daily" if is_daily else "once"
            conflict_msg = check_tier1_schedule_conflict(
                actor_tier=tier,
                time_hhmm=hhmm,
                schedule_type=schedule_type,
                engine=engine,
            )
            if conflict_msg:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="tier1_schedule_conflict",
                    msg=conflict_msg,
                    status_code=409,
                    target="schedules",
                )
            rep_txt = "hằng ngày " if is_daily else ""
            acts_txt = ", ".join(format_device_action_vi(td, act) for td in target_devs)
            return await prepare_pending_mutation(
                engine=engine,
                session=session,
                source=source,
                session_key=skey,
                action_kind="create_schedule",
                payload={
                    "target_devs": target_devs,
                    "action": act,
                    "time_hhmm": hhmm,
                    "schedule_type": schedule_type,
                },
                prompt_summary=f"Đặt lịch lúc {hhmm} {rep_txt}{acts_txt}",
            )

    # ------------------------------------------------------------------
    # STEP 8. COUNTDOWN TIMER ("tắt đèn phòng khách sau 1 phút", "10 giây nữa bật quạt")
    # ------------------------------------------------------------------
    has_countdown_cue = bool(
        re.search(
            r"(?:\bsau\s+\d+|\d+(?:\.\d+)?\s*(?:giay|phut|tieng)\b|\bhen\s+\d+|\b\d+(?:\.\d+)?\s*(?:giay|phut|gio)\s+nua\b|\bhen gio\b)",
            norm,
        )
    )
    if has_countdown_cue:
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_timer",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target="timers",
            )
        total_sec, cleaned_cd = _parse_countdown_seconds(raw)
        if total_sec <= 0:
            total_sec = 10.0
        dev, act = parse_single_device_and_action(cleaned_cd)
        if not dev:
            dev, act = parse_single_device_and_action(raw)
        dev = dev or "living_room_light"
        act = act or "turn_on"
        for td in _expand_targets(dev):
            allowed_td, reason_td = engine.check_device_permission(td, actor_tier=tier)
            if not allowed_td:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="rbac_deny_timer_device",
                    msg=reason_td,
                    status_code=403,
                    target=td,
                )
        conflict_msg = check_tier1_schedule_conflict(
            actor_tier=tier,
            fire_epoch=time.time() + total_sec,
            engine=engine,
        )
        if conflict_msg:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="tier1_timer_conflict",
                msg=conflict_msg,
                status_code=409,
                target="timers",
            )
        sec_i = max(1, int(round(total_sec)))
        act_label = format_device_action_vi(dev, act)
        return await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="create_timer",
            payload={"device_id": dev, "action": act, "seconds": total_sec},
            prompt_summary=f"Đặt hẹn giờ sau {sec_i} giây sẽ {act_label.lower()}",
        )

    # ------------------------------------------------------------------
    # STEP 9. RUN PER-USER CUSTOM COMMAND FROM SQLITE POOL (isolated by owner_user_id)
    # ------------------------------------------------------------------
    matched_cmd = find_custom_command_by_text(raw, owner_user_id=user_id)
    if matched_cmd:
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_run_custom_command",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target=str(matched_cmd.get("phrase") or "custom_command"),
            )
        steps = matched_cmd.get("steps") or []
        results = []
        spoken_parts = []
        prev_uid = getattr(engine, "_current_user_id", user_id)
        try:
            engine._current_user_id = user_id
            for st in steps:
                dev_id = str(st.get("device_id") or "")
                action = str(st.get("action") or "")
                targets = _expand_targets(dev_id)
                for td in targets:
                    res = await engine.execute_device_action(
                        td,
                        action,
                        actor_tier=tier,
                        actor_name=user_name,
                        source=source,
                    )
                    results.append(res)
                    if not res.get("ok") and res.get("rbac_blocked"):
                        err_msg = str(res.get("exact_spoken_reply") or res.get("error") or "Từ chối theo phân quyền.")
                        return _deny_mutation_error(
                            session=session,
                            source=source,
                            category="rbac_deny_custom_command_step",
                            msg=err_msg,
                            status_code=403,
                            target=td,
                            extra={"results": results},
                        )
                    if res.get("exact_spoken_reply"):
                        spoken_parts.append(str(res["exact_spoken_reply"]))
        finally:
            engine._current_user_id = prev_uid
        await engine.emit({"type": "state_snapshot", "snapshot": engine.get_snapshot()})
        spoken_exec = " ".join(spoken_parts).strip() or f"Đã thực hiện lệnh '{matched_cmd['phrase']}'."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "kind": "custom_command_executed",
                "command": matched_cmd,
                "results": results,
                "reply": spoken_exec,
                "exact_spoken_reply": spoken_exec,
                "snapshot": engine.get_snapshot(session=session, sync=False),
            },
        }

    return None
