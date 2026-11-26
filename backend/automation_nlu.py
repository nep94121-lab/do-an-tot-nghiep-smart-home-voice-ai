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

from difflib import SequenceMatcher
import re
import time
from typing import Any

try:
    from rapidfuzz import fuzz as _rapidfuzz_fuzz
except Exception:  # pragma: no cover - optional dependency
    _rapidfuzz_fuzz = None  # type: ignore[assignment]


def _fuzzy_ratio(a: str, b: str) -> float:
    if _rapidfuzz_fuzz is not None:
        return float(_rapidfuzz_fuzz.ratio(a, b))
    return float(SequenceMatcher(None, a, b).ratio() * 100.0)

from backend.auth.tier_permissions import can_control_device
from backend.automation_repo import (
    GUEST_ONLY_TOGGLE_MSG_VI,
    PENDING_CONFIRM_TTL_SEC,
    SENSOR_QUERY_TARGETS,
    SENSOR_TRIGGER_DEVICES,
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
    format_duration_vi,
    format_sensor_trigger_vi,
    get_pending_confirmation,
    is_custom_query_step,
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
from backend.database_sqlite import strip_emojis_for_audit
from backend.engine.audit_logger import append_audit_log
from backend.engine.constants_and_time import ACTION_TO_STATE, DEFAULT_DEVICES

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
    ("coi bao dong", "alarm_siren"),
    ("bao dong", "alarm_siren"),
    ("coi hu", "alarm_siren"),
    ("may bom tuoi cay", "garden_pump"),
    ("may bom", "garden_pump"),
    ("tuoi cay", "garden_pump"),
    ("bom nuoc", "garden_pump"),
    ("nguon mach loa", "speaker_amp"),
    ("mach loa", "speaker_amp"),
    ("nguon loa", "speaker_amp"),
    ("pam8403", "speaker_amp"),
    ("loa mach", "speaker_amp"),
    ("speaker amp", "speaker_amp"),
)


_REMOVED_DEVICE_MENTION_RE = re.compile(
    r"(?:^|\s)(?:quat(?:\s+tran)?|dieu\s+hoa|may\s+lanh|hoc\s+lenh|remote|hong\s+ngoai|ir|vs1838b?)(?:\s|$)"
)


def has_removed_device_mention(text: str) -> bool:
    norm = f" {normalize_phrase(text)} "
    return bool(_REMOVED_DEVICE_MENTION_RE.search(norm))


def parse_single_device_and_action(
    clause: str,
    *,
    default_action: str | None = None,
    allow_den_asr_homophone: bool = False,
) -> tuple[str | None, str | None]:
    """Extract primary device/target and canonical action from a single clause (diacritic-aware)."""
    _ = allow_den_asr_homophone  # Never coerce wrong-diacritic 'đền' -> 'đèn'
    raw_s = str(clause or "").strip().lower()
    norm = f" {normalize_phrase(raw_s)} "
    try:
        from backend.voice.vietnamese_policy import (
            _UNSUPPORTED_DEVICE_RE,
            _extract_clause_device,
            has_vi_diacritics,
        )

        if _UNSUPPORTED_DEVICE_RE.search(norm):
            return None, None
        has_diac = has_vi_diacritics(raw_s)
    except Exception:
        has_diac = False
        _extract_clause_device = None  # type: ignore[assignment]

    dev: str | None = None
    if _extract_clause_device is not None:
        dev = _extract_clause_device(norm.strip(), raw_clause=raw_s, input_has_diacritics=has_diac)
    if dev is None and not has_diac:
        for kw, target in _DEVICE_SYNONYMS:
            if f" {kw} " in norm:
                dev = target
                break
        if dev is None:
            if " cua " in norm and not any(
                bad_c in norm
                for bad_c in (
                    " cua hang ", " cua tiem ", " cua hieu ", " cua so ",
                    " cua mieng ", " cua song ", " cua bien ",
                )
            ):
                dev = "main_door"
            elif " coi " in norm:
                dev = "alarm_siren"
            elif " bom " in norm:
                dev = "garden_pump"
            elif " loa " in norm:
                dev = "speaker_amp"

    action_norm = norm
    for _non_verb in (
        "bao dong",
        "tu dong",
        "tieng dong",
        "chuyen dong",
        "hoat dong",
        "cong tac",
        "dong y",
        "dong thoi",
        "dong bo",
    ):
        action_norm = action_norm.replace(f" {_non_verb} ", " ")
    action_norm = re.sub(r"\b(?:ngung|dung|tat|ngat|cup)\s+(?:chay|hoat\s+dong|kich\s+hoat|keu|sang|tuoi)\b", "ngung", action_norm)
    if not has_diac or "tất cả" in raw_s:
        action_norm = action_norm.replace(" tat ca ", " ")
    if not has_diac or "đồng hồ" in raw_s:
        action_norm = action_norm.replace(" dong ho ", " ")
    action_norm = action_norm.replace(" khoi dong ", " __khoi_dong__ ")
    action_norm = f" {' '.join(action_norm.split())} "

    _acc_off_guard = {
        "tat": r"\btắt\b",
        "dong": r"\bđóng\b",
        "khoa": r"\b(?:khóa|khoá)\b",
        "chot": r"\bchốt\b",
        "khep": r"\bkhép\b",
        "gai": r"\bgài\b",
        "ngat": r"\bngắt\b",
        "dung": r"\bdừng\b",
        "ngung": r"\b(?:ngừng|ngưng|dừng|tắt|ngắt|cúp)\b",
        "cup": r"\bcúp\b",
        "dap": r"\bdập\b",
    }
    _acc_on_guard = {
        "bat": r"\bbật\b",
        "mo": r"\bmở\b",
        "he mo": r"\bhé\s+mở\b",
        "chay": r"\bchạy\b",
    }
    off_words = ("tat nguon", "ngat nguon", "cup nguon", "tat han", "dong kin", "tat", "dong", "khoa", "chot", "khep", "gai", "ngat", "dung", "ngung", "cup", "dap")
    on_words = ("he mo", "kich hoat", "__khoi_dong__", "cap nguon", "mo nguon", "bat nguon", "cho chay", "cho sang", "lam sang", "cho hoat dong", "cho keu", "cho hu", "bat", "mo", "chay", "tuoi")
    act: str | None = None
    for w in off_words:
        if f" {w} " in action_norm:
            g_pat = _acc_off_guard.get(w)
            if g_pat and has_diac and not re.search(g_pat, raw_s):
                continue
            act = "close" if (dev == "main_door" or w in ("dong", "dong kin", "khoa", "chot", "khep", "gai")) else "turn_off"
            break
    if act is None:
        for w in on_words:
            if f" {w} " in action_norm:
                g_pat = _acc_on_guard.get(w)
                if g_pat and has_diac and not re.search(g_pat, raw_s):
                    continue
                act = "open" if (dev == "main_door" or w in ("mo", "he mo")) else "turn_on"
                break
    if act is None and dev == "main_door":
        if has_diac and re.search(r"\bhé\b", raw_s):
            act = "open"
        elif not has_diac and re.search(r"\bhe\s+(?:cua|cong)\b", action_norm):
            act = "open"
    if act is None and dev in ("speaker_amp", "alarm_siren") and " keu " in action_norm:
        act = "turn_on"
    if act is None and dev == "alarm_siren" and " hu " in action_norm and (not has_diac or re.search(r"\bhú\b", raw_s)):
        act = "turn_on"
    if act is None:
        act = default_action

    if (dev is None or act is None) and clause:
        from backend.voice.vietnamese_policy import normalize_vietnamese_utterance

        norm_vi = normalize_vietnamese_utterance(clause)
        if norm_vi and normalize_phrase(norm_vi) != normalize_phrase(clause):
            dev2, act2 = parse_single_device_and_action(
                norm_vi,
                default_action=default_action,
            )
            if dev is None and dev2 is not None:
                dev = dev2
            if act is None and act2 is not None:
                act = act2

    if dev == "main_door" and act in ("turn_on", "turn_off"):
        act = "open" if act == "turn_on" else "close"
    return dev, act


def _parse_query_steps_from_clause(
    clause: str,
    *,
    inherited_query: bool = False,
) -> list[dict[str, str]]:
    """Parse sensor-read or device-state-read custom-command steps from a single clause."""
    raw_s = str(clause or "").strip().lower()
    if not raw_s:
        return []
    norm = f" {normalize_phrase(raw_s)} "
    try:
        from backend.voice.vietnamese_policy import (
            _UNSUPPORTED_DEVICE_RE,
            _extract_clause_device,
            has_vi_diacritics,
        )

        if _UNSUPPORTED_DEVICE_RE.search(norm):
            return []
        has_diac = has_vi_diacritics(raw_s)
    except Exception:
        has_diac = False
        _extract_clause_device = None  # type: ignore[assignment]

    has_query_verb = any(
        k in norm
        for k in (
            " doc ", " xem ", " kiem tra ", " check ", " bao cao ",
            " hoi ", " trang thai ", " so do ", " thong so ", " gia tri ",
        )
    )
    has_state_cue = any(k in norm for k in (" trang thai ", " xem ", " kiem tra ", " check ", " doc ", " bao cao "))

    # 1. Sensor queries (temperature, air humidity, soil moisture, sound)
    is_temp = any(k in norm for k in (" nhiet do ", " bao nhieu do ", " do c "))
    is_soil = any(
        k in norm
        for k in (" do am dat ", " cam bien dat ", " cam bien do am dat ", " am dat ")
    ) or (" dat " in norm and any(k in norm for k in (" do am ", " am ", " kho ", " uot ", " vuon ")))
    is_air_hum = (" do am " in norm) and not (is_soil and " khong khi " not in norm)
    is_sound = any(k in norm for k in (" am thanh ", " ky037 ", " ky 037 ", " tieng dong ", " tieng on ", " cam bien tieng dong ", " phat hien tieng "))
    is_dht11_only = any(k in norm for k in (" dht11 ", " dht 11 ")) and not (is_temp or is_air_hum)
    is_all_sensors = (" cam bien " in norm) and not (is_temp or is_air_hum or is_soil or is_sound or is_dht11_only)

    if is_temp or is_air_hum or is_soil or is_sound or is_dht11_only or is_all_sensors:
        out: list[dict[str, str]] = []
        if is_all_sensors:
            out.append({"device_id": "sensor_all", "action": "read"})
        else:
            if is_temp:
                out.append({"device_id": "sensor_temperature", "action": "read"})
            if is_air_hum:
                out.append({"device_id": "sensor_humidity", "action": "read"})
            if is_dht11_only:
                out.append({"device_id": "sensor_temperature", "action": "read"})
                out.append({"device_id": "sensor_humidity", "action": "read"})
            if is_soil:
                out.append({"device_id": "sensor_soil", "action": "read"})
            if is_sound:
                out.append({"device_id": "sensor_sound", "action": "read"})
        return out

    # 2. Device state query (only when query/state cue is present and NO explicit device-control verb)
    if has_state_cue or (inherited_query and has_query_verb) or inherited_query:
        ctrl_dev, ctrl_act = parse_single_device_and_action(clause, default_action=None)
        if ctrl_act is not None:
            return []
        dev_q = ctrl_dev
        if dev_q is None and any(k in norm for k in (" cac thiet bi ", " tat ca thiet bi ", " toan bo thiet bi ", " moi thiet bi ")):
            dev_q = "all_devices"
        elif dev_q is None and any(k in norm for k in (" cac den ", " tat ca den ", " toan bo den ", " hai den ")):
            dev_q = "all_lights"
        elif dev_q is None and _extract_clause_device is not None:
            dev_q = _extract_clause_device(norm.strip(), raw_clause=raw_s, input_has_diacritics=has_diac)
        if dev_q and (has_state_cue or inherited_query):
            return [{"device_id": dev_q, "action": "read_state"}]

    return []


def parse_multi_steps_from_text(text: str) -> list[dict[str, str]]:
    """Parse one or more device-control and/or sensor/device-state query steps."""
    raw_clauses = re.split(
        r"(?:,|;|\bvà\b|\bva\b|\brồi\b|\broi\b|\bcùng với\b|\bcung voi\b|\bvới\b|\bvoi\b|\blẫn\b|\blan\b)",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    steps: list[dict[str, str]] = []
    seen_steps: set[tuple[str, str]] = set()
    last_act: str | None = None
    last_dev: str | None = None
    last_is_query: bool = False
    for cl in raw_clauses:
        cl_s = cl.strip()
        if not cl_s:
            continue
        # Try sensor/state query step first when no explicit device-control verb overrides it
        q_steps = _parse_query_steps_from_clause(cl_s, inherited_query=last_is_query)
        if q_steps:
            last_is_query = True
            last_act = None
            for qs in q_steps:
                key = (qs["device_id"], qs["action"])
                if key not in seen_steps:
                    seen_steps.add(key)
                    steps.append(qs)
            continue

        dev, act = parse_single_device_and_action(cl_s, default_action=last_act)
        if dev is None and last_dev in ("living_room_light", "bedroom_light", "all_lights"):
            cn = normalize_phrase(cl_s)
            if cn in ("phong ngu", "ngu"):
                dev = "bedroom_light"
                act = act or last_act
            elif cn in ("phong khach", "khach"):
                dev = "living_room_light"
                act = act or last_act
        if act:
            last_act = act
            last_is_query = False
        if dev and act:
            last_dev = dev
            key = (dev, act)
            if key not in seen_steps:
                seen_steps.add(key)
                steps.append({"device_id": dev, "action": act})
    return steps


_VI_NUMBER_UNIT_MAP: dict[str, int] = {
    "khong": 0,
    "mot": 1,
    "__most__": 1,
    "hai": 2,
    "ba": 3,
    "bon": 4,
    "nam": 5,
    "__six__": 6,
    "bay": 7,
    "__bai__": 7,
    "bai": 7,
    "tam": 8,
    "chin": 9,
}

_VI_AFTER_TEN_UNIT_MAP: dict[str, int] = {
    **_VI_NUMBER_UNIT_MAP,
    "sau": 6,
    "tu": 4,
    "lam": 5,
    "__five_unit__": 5,
}

_VI_TENS_BASE: frozenset[str] = frozenset({
    "hai", "ba", "bon", "nam", "__six__", "bay", "tam", "chin",
})


def _vi_words_to_int(words: list[str], *, allow_unaccented_sau_single: bool = False) -> int | None:
    if len(words) == 1:
        w0 = words[0]
        if w0 == "muoi":
            return 10
        if w0 == "sau" and allow_unaccented_sau_single:
            return 6
        return _VI_NUMBER_UNIT_MAP.get(w0)
    if len(words) == 2:
        w0, w1 = words
        if w0 == "muoi" and w1 in _VI_AFTER_TEN_UNIT_MAP and 1 <= _VI_AFTER_TEN_UNIT_MAP[w1] <= 9:
            return 10 + _VI_AFTER_TEN_UNIT_MAP[w1]
        if w0 in _VI_TENS_BASE and w1 == "muoi":
            return _VI_NUMBER_UNIT_MAP[w0] * 10
        if w0 in _VI_TENS_BASE and w1 in ("__most__", "__five_unit__", "tu"):
            return _VI_NUMBER_UNIT_MAP[w0] * 10 + _VI_AFTER_TEN_UNIT_MAP[w1]
        return None
    if len(words) == 3:
        w0, w1, w2 = words
        if (
            w0 in _VI_TENS_BASE
            and w1 == "muoi"
            and w2 in _VI_AFTER_TEN_UNIT_MAP
            and 1 <= _VI_AFTER_TEN_UNIT_MAP[w2] <= 9
        ):
            return _VI_NUMBER_UNIT_MAP[w0] * 10 + _VI_AFTER_TEN_UNIT_MAP[w2]
    return None


def _normalize_vi_spoken_numbers(text: str) -> str:
    """Convert Vietnamese spoken number words to ASCII digits ONLY when adjacent to time units."""
    s = str(text or "").strip().lower()
    if not s:
        return ""

    # Preserve accented tokens whose unaccented forms collide with non-number words ("sau", "từ", "làm", etc.)
    sentinels = (
        (r"\bsáu\b", "__six__"),
        (r"\btừ\b", "__from__"),
        (r"\blàm\b", "__do__"),
        (r"\bbài\b", "__bai__"),
        (r"\bmốt\b", "__most__"),
        (r"\blăm\b", "__five_unit__"),
        (r"\brưỡi\b", "__half__"),
        (r"\bnửa\b", "__nua_half__"),
    )
    for pat, repl in sentinels:
        s = re.sub(pat, repl, s)

    s = strip_accents(s)

    # Half-unit idioms ("nửa tiếng" -> "30 phut", "nửa phút" -> "30 giay")
    s = re.sub(r"\b__nua_half__\s+(?:tieng|gio)\b", "30 phut", s)
    s = re.sub(r"\b__nua_half__\s+phut\b", "30 giay", s)

    # Position A: spoken number immediately BEFORE a time unit (gio / phut / giay / tieng)
    def _repl_before_unit(m: re.Match[str]) -> str:
        words = m.group(1).split()
        unit = m.group(2)
        after_ctx = s[m.end():m.end() + 18]
        before_ctx = s[max(0, m.start() - 18):m.start()]
        for k in (3, 2, 1):
            if len(words) < k:
                continue
            cand = words[-k:]
            allow_sau = False
            if k == 1 and cand[0] == "sau":
                if unit in ("phut", "giay", "tieng"):
                    allow_sau = True
                elif unit == "gio":
                    not_non_clock = not re.match(r"^\s*(?:__do__|lam|hoc|an|ngu|choi)\b", after_ctx)
                    has_clock_ctx = bool(
                        re.search(r"\b(?:luc|vao|lich|thanh|sang|hen)\s*$", before_ctx)
                        or re.match(r"^\s*(?:sang|trua|chieu|toi|dem|__half__|\d)\b", after_ctx)
                    )
                    allow_sau = not_non_clock and has_clock_ctx
            val = _vi_words_to_int(cand, allow_unaccented_sau_single=allow_sau)
            if val is not None:
                prefix = " ".join(words[:-k])
                return f"{prefix + ' ' if prefix else ''}{val} {unit}"
        return m.group(0)

    s = re.sub(
        r"\b([a-z_]+(?:\s+[a-z_]+){0,2})\s+(gio|phut|giay|tieng)\b",
        _repl_before_unit,
        s,
    )

    # Half-hour / half-tieng after a number ("7 gio rưỡi" -> "7 gio 30")
    s = re.sub(r"\b(\d{1,2})\s*gio\s+__half__\b", r"\1 gio 30", s)
    s = re.sub(r"\b(\d{1,2})\s*tieng\s+__half__\b", r"\1 tieng 30 phut", s)

    # Position B: spoken minutes immediately AFTER "<digit> gio" (e.g., "7 gio muoi lam sang" -> "7 gio 15 sang")
    def _repl_after_gio(m: re.Match[str]) -> str:
        hh_str = m.group(1)
        words = m.group(2).split()
        for k in (3, 2, 1):
            if len(words) < k:
                continue
            cand = words[:k]
            val = _vi_words_to_int(cand, allow_unaccented_sau_single=False)
            if val is not None and 0 <= val <= 59:
                tail = " ".join(words[k:])
                return f"{hh_str} gio {val}" + (f" {tail}" if tail else "")
        return m.group(0)

    s = re.sub(
        r"\b(\d{1,2})\s*gio\s+([a-z_]+(?:\s+[a-z_]+){0,2})(?=\s*(?:phut\b|p\b|sang\b|trua\b|chieu\b|toi\b|dem\b|am\b|pm\b|hang\b|moi\b|$|[.,!?]))",
        _repl_after_gio,
        s,
    )

    # Restore any untouched sentinels back to clean unaccented Vietnamese words
    for sentinel, clean_w in (
        ("__six__", "sau"),
        ("__from__", "tu"),
        ("__do__", "lam"),
        ("__bai__", "bai"),
        ("__most__", "mot"),
        ("__five_unit__", "lam"),
        ("__half__", "ruoi"),
        ("__nua_half__", "nua"),
    ):
        s = s.replace(sentinel, clean_w)
    return s


def _parse_clock_hhmm_vi(text: str) -> tuple[str | None, bool, str]:
    """Parse explicit clock time ('14 giờ 35', '22:30', '7h15 sáng', 'bảy giờ sáng') + daily repeat flag."""
    norm = _normalize_vi_spoken_numbers(text)
    is_daily = bool(
        re.search(r"\b(?:hang ngay|moi ngay|ngay nao cung|lap lai|moi sang|moi toi|hang tuan|daily)\b", norm)
    )

    m = re.search(
        r"(?:vao\s+luc|dung|luc|vao|toi)?\s*"
        r"(\d{1,2})\s*(?:gio|h|:)\s*(\d{1,2})?\s*(?:phut|p)?\s*"
        r"(sang|trua|chieu|toi|dem|am|pm)?",
        norm,
    )
    if not m:
        return None, is_daily, ""

    prefix = norm[max(0, m.start() - 12):m.start()]
    suffix = norm[m.end():m.end() + 10]
    m_has_clock_prefix = bool(
        re.match(r"^(?:vao\s+luc|luc|vao)\b", m.group(0).strip())
        or any(w in norm[:m.start()] for w in ("luc", "vao"))
    )
    if re.search(r"(?<!thu\s)\b(?:sau|nua|trong|con)\s*$", prefix) or re.match(r"^\s*(?:nua|sau)\b", suffix):
        if ":" not in m.group(0) and not m_has_clock_prefix:
            return None, is_daily, ""

    has_clock_marker = (
        any(k in norm for k in ("luc", "vao", ":"))
        or (m.group(3) is not None)
        or (("gio" in m.group(0) or "h" in m.group(0)) and "nua" not in norm and not re.search(r"(?<!thu\s)\bsau\s+\d", norm))
    )
    if not has_clock_marker:
        return None, is_daily, ""

    # Support period BEFORE clock time ("tối nay lúc 9 giờ", "sáng mai 6 giờ") as well as after ("9 giờ tối")
    lead_period = ""
    m_lead_p = re.search(r"\b(sang|trua|chieu|toi|dem)\s+(?:nay|mai)\b", norm[:m.start() + 4])
    if m_lead_p:
        lead_period = m_lead_p.group(1).strip()

    hh = int(m.group(1))
    mm = int(m.group(2) or 0)
    period = (m.group(3) or lead_period or "").strip()
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

    cleaned_clause = (norm[:m.start()] + " " + norm[m.end():]).strip()
    cleaned_clause = re.sub(r"\b(?:hang|moi)\s+ngay\b", " ", cleaned_clause)
    return f"{hh:02d}:{mm:02d}", is_daily, cleaned_clause


def _parse_countdown_seconds(text: str) -> tuple[float, str]:
    norm = _normalize_vi_spoken_numbers(text)
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


_DESTRUCTIVE_PENDING_KINDS: frozenset[str] = frozenset({
    "delete_timer",
    "delete_schedule",
    "delete_automation_rule",
    "delete_custom_command",
    "delete_compound_rule",
    "reset_pool",
    "reset_devices",
    "factory_reset",
    "reset_automations",
})


def _classify_confirmation_utterance(
    raw_text: str,
    *,
    has_pending: bool = False,
    pending_action_kind: str = "",
) -> str | None:
    """Return 'confirm', 'cancel', or None while distinguishing 'đúng' vs 'đừng'/'dừng' and natural Vietnamese replies."""
    raw_s_full = str(raw_text or "").strip()
    raw_low = re.sub(r"[?!.,;:]+$", "", raw_s_full.lower()).strip()
    if not raw_low:
        return None
    raw_collapsed = re.sub(r"\s+", " ", re.sub(r"[,;]+", " ", raw_low)).strip()
    norm = re.sub(r"\s+", " ", normalize_phrase(raw_collapsed)).strip()

    lead_vi = r"(?:(?:ừ|ừm|ư|ờ|vâng|dạ|ok|okay|oke|okie|ô\s*kê|rồi|thôi|à)\s+){0,2}"
    lead_en = r"(?:(?:u|um|uh|o|vang|da|ok|okay|oke|okie|o\s*ke|roi|thoi|a)\s+){0,2}"
    # Cancel lead-in excludes affirmative particles ('ừ', 'vâng', 'dạ', 'ok') so 'ừ hủy đi' confirms a pending cancel/delete!
    cancel_lead_vi = r"(?:(?:thôi|à|ờ|không)\s+){0,2}"
    cancel_lead_en = r"(?:(?:thoi|a|o|khong)\s+){0,2}"
    polite_vi = (
        r"(?:\s+(?:giúp\s+(?:anh|chị|em|tôi|mình)|giùm\s+(?:anh|chị|em|tôi|mình)|"
        r"dùm\s+(?:anh|chị|em|tôi|mình)|hộ\s+(?:anh|chị|em|tôi|mình)|"
        r"xác\s+nhận|đồng\s+ý|nhất\s+trí|chốt(?:\s+đơn)?|được|đúng|chuẩn|làm|thực\s+hiện|tiến\s+hành|triển\s+khai|"
        r"lưu(?:\s+lại)?|đặt|tạo|cài|sửa|xóa|xoá|hủy|huỷ|reset|chạy|mở|bật|tắt|đóng|"
        r"như\s+vậy|như\s+thế|đấy|đó|ơi|ạ|nhé|nha|nhá|đi|luôn|ngay|rồi|nữa|đâu|em|bạn|anh|chị|nào))*"
    )
    polite_en = (
        r"(?:\s+(?:giup\s+(?:anh|chi|em|toi|minh)|gium\s+(?:anh|chi|em|toi|minh)|"
        r"dum\s+(?:anh|chi|em|toi|minh)|ho\s+(?:anh|chi|em|toi|minh)|"
        r"xac\s+nhan|dong\s+y|nhat\s+tri|chot(?:\s+don)?|duoc|dung|chuan|lam|thuc\s+hien|tien\s+hanh|trien\s+khai|"
        r"luu(?:\s+lai)?|dat|tao|cai|sua|xoa|huy|reset|chay|mo|bat|tat|dong|"
        r"nhu\s+vay|nhu\s+the|day|do|oi|a|nhe|nha|di|luon|ngay|roi|nua|dau|em|ban|anh|chi|nao))*"
    )

    # Check accented cancel words first so 'đừng' / 'dừng' never collide with 'đúng' ('dung')
    if re.search(
        rf"^{cancel_lead_vi}(?:"
        r"đừng(?:\s+đừng){0,2}|đừng\s+(?:làm|thực\s+hiện|tạo|đặt|cài|lưu|xóa|xoá|chạy|reset)|"
        r"dừng(?:\s+dừng){0,2}|dừng\s+lại|"
        r"không(?:\s+không){0,2}|không\s+(?:làm|cần|đồng\s+ý|muốn|thực\s+hiện|xác\s+nhận)|"
        r"hủy(?:\s+hủy){0,2}|huỷ(?:\s+huỷ){0,2}|hủy\s+bỏ|huỷ\s+bỏ|"
        r"thôi(?:\s+thôi){0,2}|thôi\s+(?:hủy|huỷ|hủy\s+bỏ|huỷ\s+bỏ|bỏ|không|đừng|khỏi)|"
        r"bỏ(?:\s+bỏ){0,2}|bỏ\s+đi|bỏ\s+qua|đổi\s+ý|quay\s+lại|khoan\s+đã|từ\s+chối|khỏi\s+cần"
        rf"){polite_vi}\s*$",
        raw_collapsed,
    ):
        return "cancel"

    if re.search(
        rf"^{cancel_lead_en}(?:"
        r"khong(?:\s+khong){0,2}|k|khong\s+(?:lam|can|dong\s+y|muon|thuc\s+hien|xac\s+nhan)|"
        r"dung\s+(?:lam|lai|thuc\s+hien|tao|dat|cai|luu|xoa|chay|reset)|"
        r"huy(?:\s+huy){0,2}|huy\s+bo|"
        r"thoi(?:\s+thoi){0,2}|thoi\s+(?:huy|huy\s+bo|bo|khong|dung|khoi)|"
        r"bo(?:\s+bo){0,2}|bo\s+di|bo\s+qua|doi\s+y|quay\s+lai|khoan\s+da|no|cancel|tu\s+choi|khoi\s+can"
        rf"){polite_en}\s*$",
        norm,
    ):
        return "cancel"

    confirm_verbs_vi = (
        r"(?:làm|thực\s+hiện|tiến\s+hành|triển\s+khai|tiếp\s+tục|lưu|tạo|đặt|cài|chạy|xóa|xoá|reset|mở|bật|tắt|đóng)\s+"
        r"(?:lại|đi|luôn|ngay|nhé|nha|ạ|rồi|giúp\s+(?:anh|chị|em|tôi|mình)|giùm\s+(?:anh|chị|em|tôi|mình)|hộ\s+(?:anh|chị|em|tôi|mình))"
    )
    confirm_verbs_en = (
        r"(?:lam|thuc\s+hien|tien\s+hanh|trien\s+khai|tiep\s+tuc|luu|tao|dat|cai|chay|xoa|reset|mo|bat|tat|dong)\s+"
        r"(?:lai|di|luon|ngay|nhe|nha|a|roi|giup\s+(?:anh|chi|em|toi|minh)|gium\s+(?:anh|chi|em|toi|minh)|ho\s+(?:anh|chi|em|toi|minh))"
    )

    if re.search(
        rf"^{lead_vi}(?:"
        r"đúng(?:\s+đúng){0,2}|đúng\s+(?:rồi|vậy|ý|thế)|chuẩn(?:\s+(?:rồi|luôn|đấy))?|chốt(?:\s+(?:đơn|đi|luôn|ngay|nhé|nha))?|"
        r"xác\s+nhận|đồng\s+ý|nhất\s+trí|chắc\s+chắn|"
        r"ừ(?:\s+ừ){0,2}|ừm(?:\s+ừm){0,2}|ư|ờ|"
        r"ok(?:\s+ok){0,2}|okay(?:\s+okay){0,2}|oke(?:\s+oke){0,2}|okie|ô\s*kê|"
        r"đc|được(?:\s+được){0,2}|được\s+(?:rồi|đấy)|yes|"
        r"vâng(?:\s+vâng){0,2}|dạ(?:\s+dạ){0,2}|dạ\s+(?:vâng|được|đúng|ok|oke|chốt|đồng\s+ý|nhất\s+trí)|có(?:\s+có){0,2}|"
        r"thực\s+hiện|tiến\s+hành|triển\s+khai|tiếp\s+tục|"
        rf"{confirm_verbs_vi}"
        rf"){polite_vi}\s*$",
        raw_collapsed,
    ):
        return "confirm"

    # Unaccented fallback (safe because accented 'đừng'/'dừng' already returned 'cancel' above)
    if (has_pending or not re.match(r"^dược(?:\s|$)", raw_collapsed)) and re.search(
        rf"^{lead_en}(?:"
        r"xac\s+nhan|dong\s+y|nhat\s+tri|chac\s+chan|chuan(?:\s+(?:roi|luon|day))?|chot(?:\s+(?:don|di|luon|ngay|nhe|nha))?|"
        r"ok(?:\s+ok){0,2}|okay(?:\s+okay){0,2}|oke(?:\s+oke){0,2}|okie|o\s*ke|dc|yes|confirm|"
        r"u(?:\s+u){0,2}|uh|um(?:\s+um){0,2}|duoc(?:\s+duoc){0,2}|duoc\s+(?:roi|day)|"
        r"dung(?:\s+dung){0,2}|dung\s+(?:roi|vay|y|the)|"
        r"vang(?:\s+vang){0,2}|da(?:\s+da){0,2}|da\s+(?:vang|duoc|dung|ok|oke|chot|dong\s+y|nhat\s+tri)|co(?:\s+co){0,2}|"
        r"thuc\s+hien|tien\s+hanh|trien\s+khai|tiep\s+tuc|"
        rf"{confirm_verbs_en}"
        rf"){polite_en}\s*$",
        norm,
    ):
        return "confirm"

    # General natural Vietnamese multi-word confirmation / cancellation when a pending confirmation is actively waiting
    if has_pending:
        # Never hijack genuine questions into confirm/cancel
        if "?" in raw_s_full or re.search(
            r"\b(?:bao\s+nhieu|the\s+nao|ra\s+sao|o\s+dau|la\s+ai|la\s+gi|may\s+gio|may\s+do|co\s+nhung)\b",
            norm,
        ):
            return None

        has_diac = any(ord(ch) > 127 for ch in raw_collapsed)
        if re.search(r"^(?:ờ|o)(?:\s+(?:ạ|nhé|nha|đi|luôn|rồi|em|bạn|a|nhe|di|luon|roi|ban))*\s*$", raw_collapsed):
            return "confirm"

        is_destructive_pending = pending_action_kind in _DESTRUCTIVE_PENDING_KINDS

        # Accent-safe refusal/negation cues (excluding bare 'hủy'/'xóa' so destructive pending confirms like 'ừ hủy đi' work)
        has_refusal_non_huy = bool(
            (
                re.search(
                    r"\b(?:không|đừng|chưa|thôi|khoan|đổi\s+ý|bỏ\s+qua|bỏ\s+đi|từ\s+chối|khỏi\s+cần|dừng\s+lại|quay\s+lại)\b",
                    raw_collapsed,
                )
                if has_diac
                else re.search(
                    r"\b(?:khong|chua|thoi|khoan|doi\s+y|bo\s+qua|bo\s+di|tu\s+choi|khoi\s+can|dung\s+lai|quay\s+lai|no|cancel|"
                    r"dung\s+(?:lam|luu|dat|tao|cai|reset|xoa|chay|thuc\s+hien|tien\s+hanh|sua|doi|hen))\b",
                    norm,
                )
            )
            or re.match(r"^(?:không|khong|k|no|cancel)\b", raw_collapsed)
        )
        has_huy_word = bool(
            re.search(r"\b(?:hủy|huỷ)\b", raw_collapsed) if has_diac else re.search(r"\bhuy\b", norm)
        )

        # Affirmative heads/verbs (excluding 'chốt cửa')
        has_chot_confirm = bool(
            re.search(r"\bchốt(?!\s+(?:cửa|cổng))\b", raw_collapsed)
            if has_diac
            else re.search(r"\bchot(?!\s+(?:cua|cong))\b", norm)
        )
        has_affirmative = bool(
            has_chot_confirm
            or (
                re.search(
                    r"\b(?:đồng\s+ý|xác\s+nhận|nhất\s+trí|chắc\s+chắn|"
                    r"đúng\s+(?:rồi|vậy|ý|thế|như\s+vậy|luôn)|"
                    r"chuẩn\s+(?:rồi|luôn|quá|đấy|nhé|đó)|"
                    r"ok|oke|okay|okie|ô\s*kê|yes|confirm|"
                    r"được\s+(?:rồi|đấy|luôn|nhé|nha|ạ|đó)|"
                    r"tiến\s+hành|triển\s+khai|thực\s+hiện|tiếp\s+tục|"
                    r"làm\s+(?:đi|ngay|luôn|giúp|giùm|hộ|vậy|thế)|"
                    r"lưu\s+(?:đi|lại|ngay|luôn|giúp|giùm|hộ)|"
                    r"cứ\s+(?:thế|vậy|như\s+thế|như\s+vậy|lưu|tạo|đặt|chạy|xóa|xoá|hủy|huỷ|reset|làm|tiến\s+hành|thực\s+hiện|triển\s+khai|hẹn|sửa|đổi|khôi\s+phục))\b|"
                    r"^(?:ừ|ừa|ừm|vâng|dạ)\b",
                    raw_collapsed,
                )
                if has_diac
                else re.search(
                    r"\b(?:dong\s+y|xac\s+nhan|nhat\s+tri|chac\s+chan|"
                    r"dung\s+(?:roi|vay|y|the|nhu\s+vay|luon)|"
                    r"chuan\s+(?:roi|luon|qua|day|nhe|do)|"
                    r"ok|oke|okay|okie|o\s*ke|yes|confirm|"
                    r"duoc\s+(?:roi|day|luon|nhe|nha|a|do)|"
                    r"tien\s+hanh|trien\s+khai|thuc\s+hien|tiep\s+tuc|"
                    r"lam\s+(?:di|ngay|luon|giup|gium|ho|vay|the)|"
                    r"luu\s+(?:di|lai|ngay|luon|giup|gium|ho)|"
                    r"cu\s+(?:the|vay|nhu\s+the|nhu\s+vay|luu|tao|dat|chay|xoa|huy|reset|lam|tien\s+hanh|thuc\s+hien|trien\s+khai|hen|sua|doi|khoi\s+phuc))\b|"
                    r"^(?:u|ua|um|vang|da)\b",
                    norm,
                )
            )
        )

        # Confirm pending destructive/delete/reset action when affirmative + NO non-huy refusal (e.g. 'ừ hủy đi', 'đồng ý xóa đi')
        if has_affirmative and not has_refusal_non_huy:
            if is_destructive_pending:
                return "confirm"
            if not has_huy_word:
                return "confirm"
            if not pending_action_kind and re.match(
                r"^(?:ừ|ừm|vâng|dạ|ok|oke|okay|đồng\s+ý|xác\s+nhận|u|um|vang|da|dong\s+y|xac\s+nhan)\b.+\b(?:hủy|huỷ|xóa|xoá|reset|huy|xoa)\s+(?:đi|luôn|ngay|giúp|giùm|hộ|di|luon|ngay|giup)\b",
                raw_collapsed,
            ):
                return "confirm"

        # Natural multi-word cancel sentences (even when echoing the pending action noun like 'đừng reset thiết bị nữa, hủy đi')
        if has_refusal_non_huy or has_huy_word:
            if re.search(
                r"\b(?:hủy|huỷ|huy|thôi|thoi|bỏ\s+đi|bỏ\s+qua|bo\s+di|bo\s+qua|đổi\s+ý|doi\s+y|"
                r"từ\s+chối|tu\s+choi|khỏi\s+cần|khoi\s+can|dừng\s+lại|dung\s+lai|quay\s+lại|quay\s+lai|"
                r"khoan(?:\s+đã|\s+da|\s+hẵng)?|"
                r"(?:không|khong)\s+(?:làm|cần|đồng\s+ý|dong\s+y|muốn|muon|xác\s+nhận|xac\s+nhan|thực\s+hiện|thuc\s+hien|tiến\s+hành|tien\s+hanh|reset|xóa|xoá|xoa|đặt|dat|tạo|tao|lưu|luu|cài|cai|chạy|chay|sửa|sua|đổi|doi|hẹn|hen|hủy|huỷ|huy)|"
                r"đừng\s+(?:làm|lưu|đặt|tạo|cài|reset|xóa|xoá|chạy|thực\s+hiện|tiến\s+hành|sửa|đổi|hẹn))\b|"
                r"^(?:không|khong|k|no|cancel)\b",
                raw_collapsed if has_diac else norm,
            ) or (
                not has_diac
                and re.search(r"\bdung\s+(?:lam|luu|dat|tao|cai|reset|xoa|chay|thuc\s+hien|tien\s+hanh|sua|doi|hen)\b", norm)
            ):
                return "cancel"

    return None


def _parse_sensor_trigger_with_threshold(clause: str) -> tuple[str, str, str, float | None] | None:
    """Parse sensor trigger phrases with optional per-rule numeric operator and threshold value."""
    raw_c = str(clause or "").strip()
    norm = f" {normalize_phrase(raw_c)} "
    raw_no_model = re.sub(r"\b(?:dht\s*11|ky\s*-?\s*03[78]|yl\s*-?\s*69|pam\s*8403)\b", " ", raw_c, flags=re.IGNORECASE)
    norm_no_model = f" {normalize_phrase(raw_no_model)} "

    def _extract_num_op(sensor_id: str) -> tuple[str, float] | None:
        m_sym = re.search(r"(>=|<=|!=|==|>|<)\s*(\d+(?:\.\d+)?)", raw_no_model)
        if m_sym:
            return m_sym.group(1), float(m_sym.group(2))
        val: float | None = None
        m_dig = re.search(r"(\d+(?:\.\d+)?)", norm_no_model)
        if m_dig:
            val = float(m_dig.group(1))
        else:
            units = {
                "khong": 0, "mot": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4,
                "nam": 5, "lam": 5, "sau": 6, "bay": 7, "tam": 8, "chin": 9,
            }
            toks = norm_no_model.split()
            for idx in range(len(toks)):
                t0 = toks[idx]
                if t0 == "muoi":
                    val = float(10 + units[toks[idx + 1]]) if (idx + 1 < len(toks) and toks[idx + 1] in units and 1 <= units[toks[idx + 1]] <= 9) else 10.0
                    break
                if t0 in units and 2 <= units[t0] <= 9 and idx + 1 < len(toks) and toks[idx + 1] == "muoi":
                    base = units[t0] * 10
                    val = float(base + units[toks[idx + 2]]) if (idx + 2 < len(toks) and toks[idx + 2] in units and 1 <= units[toks[idx + 2]] <= 9) else float(base)
                    break
        if val is None:
            return None
        if any(k in norm_no_model for k in (" tro len ", " lon hon hoac bang ", " it nhat ")):
            return ">=", val
        if any(k in norm_no_model for k in (" tro xuong ", " nho hon hoac bang ", " toi da ")):
            return "<=", val
        if any(k in norm_no_model for k in (" len tren ", " tren ", " vuot ", " vuot qua ", " cao hon ", " lon hon ")):
            return ">", val
        if any(
            k in norm_no_model
            for k in (
                " giam xuong duoi ", " giam duoi ", " lanh duoi ", " xuong duoi ", " duoi ",
                " thap hon ", " nho hon ", " lanh hon ", " it hon ", " giam xuong ", " ha xuong ",
            )
        ):
            return "<", val
        if any(k in norm_no_model for k in (" bang ",)):
            return "==", val
        return None

    # Soil moisture triggers (allows optional intervening location words)
    if (
        any(k in norm for k in (" do am dat ", " cam bien dat "))
        or (" dat " in norm and any(k in norm for k in (" kho ", " am ", " uot ", " duoi ", " tren ", " vuot ", " thap ", " cao ", " nho hon ", " lon hon ")))
    ):
        num_spec = _extract_num_op("soil_sensor")
        if num_spec is not None:
            op, val = num_spec
            st = "DRY" if op in ("<", "<=") else "WET"
            return "soil_sensor", st, op, val
        if (
            any(k in norm for k in (" dat kho ", " bi kho ", " qua kho ", " do am dat thap ", " do am dat kho ", " dat bi kho ", " dat qua kho ", " dat kho qua ", " duoi ", " thap hon ", " nho hon ", " it hon "))
            or re.search(r"\bdat\b(?:\s+\S+){0,3}\s+(?:bi\s+|qua\s+|hoi\s+|dang\s+)?kho\b", norm)
        ):
            return "soil_sensor", "DRY", "", None
        if (
            any(k in norm for k in (" dat am ", " dat uot ", " do am dat cao ", " dat du am ", " vuot ", " tren ", " cao hon ", " lon hon "))
            or re.search(r"\bdat\b(?:\s+\S+){0,3}\s+(?:du\s+|qua\s+|bi\s+|dang\s+)?(?:am|uot)\b", norm)
        ):
            return "soil_sensor", "WET", "", None

    # Sound sensor KY-037 triggers (check quiet/negated first)
    if any(k in norm for k in (" yen tinh ", " het tieng dong ", " khong co tieng dong ", " khong co tieng on ")):
        return "sound_sensor", "QUIET", "", None
    if any(
        k in norm
        for k in (
            " tieng dong ", " tieng on ", " am thanh lon ", " am thanh bat thuong ",
            " on ao ", " phat hien am thanh ", " phat hien tieng ", " nghe thay tieng ",
            " vo tay ", " ky037 ", " ky 037 ",
        )
    ):
        return "sound_sensor", "LOUD", "", None

    # DHT11 temperature triggers
    if (
        " nhiet do " in norm
        or (" dht11 " in norm and " do c " in norm)
        or (
            " do am " not in norm
            and (
                " do c " in norm
                or "°c" in raw_c.lower()
                or (
                    " do " in norm
                    and any(
                        k in norm
                        for k in (
                            " lanh ", " nong ", " duoi ", " tren ", " thap ", " cao ", " vuot ",
                            " giam ", " tang ", " xuong ", " tro xuong ", " tro len ",
                        )
                    )
                )
            )
        )
    ):
        num_spec = _extract_num_op("temp_sensor")
        if num_spec is not None:
            op, val = num_spec
            st = "HIGH" if op in (">", ">=") else "LOW"
            return "temp_sensor", st, op, val
        if any(k in norm for k in (" len tren ", " tren ", " vuot ", " cao ", " nong ")):
            return "temp_sensor", "HIGH", "", None
        if any(k in norm for k in (" xuong duoi ", " giam duoi ", " lanh duoi ", " duoi ", " thap ", " lanh ")):
            return "temp_sensor", "LOW", "", None

    # DHT11 air humidity triggers
    if " do am khong khi " in norm or (" do am " in norm and " dat " not in norm):
        num_spec = _extract_num_op("humidity_sensor")
        if num_spec is not None:
            op, val = num_spec
            st = "LOW" if op in ("<", "<=") else "HIGH"
            return "humidity_sensor", st, op, val
        if any(k in norm for k in (" xuong duoi ", " duoi ", " thap ")):
            return "humidity_sensor", "LOW", "", None
        if any(k in norm for k in (" len tren ", " tren ", " vuot ", " cao ")):
            return "humidity_sensor", "HIGH", "", None
    return None


def _parse_sensor_trigger(clause: str) -> tuple[str, str] | None:
    """Parse sensor trigger phrases ('đất khô', 'độ ẩm đất dưới 30%', 'nhiệt độ trên 35°C', 'có tiếng động lớn', etc.)."""
    res = _parse_sensor_trigger_with_threshold(clause)
    if res is None:
        return None
    return res[0], res[1]


def _ensure_confirmation_question(summary_text: str) -> str:
    raw = str(summary_text or "").strip()
    if raw.endswith("?"):
        return raw
    txt = raw.rstrip("?!.,;:")
    if not txt:
        txt = "Thực hiện thay đổi này"
    low = txt.lower()
    if low.endswith("đúng không ạ") or low.endswith("đồng ý không") or low.endswith("đúng không"):
        return f"{txt}?"
    return f"{txt}, đúng không ạ?"


async def stage_device_intents_for_confirmation(
    *,
    engine: Any,
    session: Any,
    source: str,
    intents: list[dict[str, Any]],
    session_key: str = "",
    ttl_sec: float = PENDING_CONFIRM_TTL_SEC,
) -> dict[str, Any]:
    """Validate RBAC upfront, normalize toggle intents, and stage a pending set_device confirmation.

    Shared across /api/voice_command and /api/text_command so direct device commands always
    repeat back in natural Vietnamese and wait for explicit user confirmation ("ok"/"được"/"làm đi").
    """
    from backend.live.echo_and_speech_guard import sanitize_spoken_vietnamese_text

    _user_id, tier, _user_name, _role = _session_actor(session)
    skey = session_key or _resolve_session_key(session, source)

    validated_intents: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for intent in intents:
        raw_dev = str(intent.get("device_id") or "").strip()
        raw_act = str(intent.get("action") or intent.get("target_state") or "toggle").strip().lower() or "toggle"
        if not raw_dev:
            continue
        for td in _expand_targets(raw_dev):
            cid = engine.resolve_canonical_device_id(td) if hasattr(engine, "resolve_canonical_device_id") else td
            act = raw_act
            if act == "toggle":
                cur_state = str((getattr(engine, "devices", {}).get(cid) or {}).get("state") or "").upper()
                if cid == "main_door":
                    act = "close" if cur_state == "OPEN" else "open"
                else:
                    act = "turn_off" if cur_state == "ON" else "turn_on"
            elif act in ("on", "open"):
                act = "open" if cid == "main_door" else "turn_on"
            elif act in ("off", "close"):
                act = "close" if cid == "main_door" else "turn_off"
            elif cid == "main_door" and act in ("turn_on", "turn_off"):
                act = "open" if act == "turn_on" else "close"

            ok_v, v_info = engine.validate_device_set_request(
                cid,
                action=act,
                brightness_pct=intent.get("brightness_pct"),
                temperature_c=intent.get("temperature_c"),
                fan_speed=intent.get("fan_speed"),
                actor_tier=tier,
                actor_user_id=_user_id,
            )
            if not ok_v:
                is_rbac = bool(v_info.get("rbac_blocked")) or int(v_info.get("status_code") or 0) == 403
                err_msg = str(
                    v_info.get("exact_spoken_reply")
                    or v_info.get("error")
                    or "Xin lỗi, bạn không có quyền thực hiện lệnh này."
                )
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category=f"rbac_deny_{source}" if is_rbac else f"invalid_{source}",
                    msg=err_msg,
                    status_code=int(v_info.get("status_code") or (403 if is_rbac else 400)),
                    target=cid or raw_dev or "device",
                    extra={"results": [v_info], "intents": intents},
                )

            norm_cid = str(v_info["device_id"])
            norm_act = str(v_info["action"])
            norm_params = dict(v_info.get("params") or {})
            pair_key = (norm_cid, norm_act)
            if pair_key not in seen_pairs:
                seen_pairs.add(pair_key)
                validated_intents.append({
                    "device_id": norm_cid,
                    "action": norm_act,
                    "brightness_pct": norm_params.get("brightness_pct"),
                    "temperature_c": norm_params.get("temperature_c"),
                    "fan_speed": norm_params.get("fan_speed"),
                })

    if not validated_intents:
        return _deny_mutation_error(
            session=session,
            source=source,
            category=f"invalid_{source}",
            msg="Không xác định được thiết bị cần điều khiển ạ.",
            status_code=400,
            target="device",
        )

    action_phrases = [
        format_device_action_vi(it["device_id"], it["action"]).lower()
        for it in validated_intents
    ]
    raw_prompt = f"Mình sẽ {' và '.join(action_phrases)}, bạn đồng ý không?"
    prompt_q = sanitize_spoken_vietnamese_text(raw_prompt) or raw_prompt
    pending_payload: dict[str, Any] = {
        "device_id": validated_intents[0]["device_id"],
        "action": validated_intents[0]["action"],
        "brightness_pct": validated_intents[0].get("brightness_pct"),
        "temperature_c": validated_intents[0].get("temperature_c"),
        "fan_speed": validated_intents[0].get("fan_speed"),
        "intents": validated_intents,
    }
    staged = await prepare_pending_mutation(
        engine=engine,
        session=session,
        source=source,
        session_key=skey,
        action_kind="set_device",
        payload=pending_payload,
        prompt_summary=prompt_q,
        ttl_sec=ttl_sec,
    )
    staged["payload"]["executed"] = False
    staged["payload"]["intents"] = validated_intents
    staged["payload"]["results"] = []
    return staged


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
    """Store 20s server-side pending draft and return Step-1 confirmation question."""
    user_id, tier, user_name, _ = _session_actor(session)
    if tier >= 3 and action_kind != "set_device":
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
    if tier >= 3 and action_kind != "set_device":
        return _deny_mutation_error(
            session=session,
            source=source,
            category=f"rbac_deny_{action_kind}",
            msg=GUEST_ONLY_TOGGLE_MSG_VI,
            status_code=403,
            target=action_kind,
        )

    if action_kind == "set_device":
        raw_intents = payload.get("intents")
        if isinstance(raw_intents, list) and raw_intents:
            exec_results: list[dict[str, Any]] = []
            spoken_parts: list[str] = []
            for item in raw_intents:
                if not isinstance(item, dict):
                    continue
                item_dev = str(item.get("device_id") or "").strip()
                item_act = str(item.get("action") or "").strip()
                if not item_dev:
                    continue
                res_item = await engine.set_device_parameters(
                    device_id=item_dev,
                    action=item_act,
                    brightness_pct=item.get("brightness_pct"),
                    temperature_c=item.get("temperature_c"),
                    fan_speed=item.get("fan_speed"),
                    source=source,
                    request_tier=tier,
                    request_role=role,
                    request_user_name=user_name,
                    request_user_id=user_id,
                )
                if not res_item.get("ok"):
                    return _deny_mutation_error(
                        session=session,
                        source=source,
                        category="rbac_deny_set_device" if res_item.get("rbac_blocked") else "invalid_set_device",
                        msg=str(res_item.get("exact_spoken_reply") or res_item.get("error") or "Không thực hiện được lệnh."),
                        status_code=int(res_item.get("status_code") or (403 if res_item.get("rbac_blocked") else 400)),
                        target=item_dev or "device",
                    )
                exec_results.append(res_item)
                act_phrase = format_device_action_vi(
                    str(res_item.get("device_id") or item_dev),
                    item_act,
                ).lower()
                if act_phrase:
                    spoken_parts.append(act_phrase)
            if not exec_results:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="invalid_set_device",
                    msg="Không tìm thấy thiết bị để thực hiện lệnh.",
                    status_code=400,
                    target="device",
                )
            if len(exec_results) == 1:
                spoken = str(exec_results[0].get("exact_spoken_reply") or "Đã thực hiện xong rồi ạ.")
            else:
                spoken = f"Mình đã {' và '.join(spoken_parts)} rồi ạ."
            last_res = exec_results[-1]
            return {
                "handled": True,
                "status_code": 200,
                "payload": {
                    "ok": True,
                    "confirmed": True,
                    "executed": True,
                    "kind": "device_set",
                    "device_id": last_res.get("device_id"),
                    "device_name": last_res.get("device_name"),
                    "state": last_res.get("state"),
                    "settings": last_res.get("settings", {}),
                    "intents": raw_intents,
                    "results": exec_results,
                    "reply": spoken,
                    "exact_spoken_reply": spoken,
                    "snapshot": engine.get_snapshot(session=session, sync=False),
                },
            }

        dev_id = str(payload.get("device_id") or "").strip()
        act = payload.get("action")
        res_set = await engine.set_device_parameters(
            device_id=dev_id,
            action=act,
            brightness_pct=payload.get("brightness_pct"),
            temperature_c=payload.get("temperature_c"),
            fan_speed=payload.get("fan_speed"),
            source=source,
            request_tier=tier,
            request_role=role,
            request_user_name=user_name,
            request_user_id=user_id,
        )
        if not res_set.get("ok"):
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_set_device" if res_set.get("rbac_blocked") else "invalid_set_device",
                msg=str(res_set.get("exact_spoken_reply") or res_set.get("error") or "Không thực hiện được lệnh."),
                status_code=int(res_set.get("status_code") or (403 if res_set.get("rbac_blocked") else 400)),
                target=dev_id or "device",
            )
        spoken = str(res_set.get("exact_spoken_reply") or "Đã thực hiện xong rồi ạ.")
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "executed": True,
                "kind": "device_set",
                "device_id": res_set.get("device_id"),
                "device_name": res_set.get("device_name"),
                "state": res_set.get("state"),
                "settings": res_set.get("settings", {}),
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": res_set.get("snapshot") or engine.get_snapshot(session=session, sync=False),
            },
        }

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
        t_act = str(payload.get("then_action") or "").strip()
        if not t_dev or not t_act:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="invalid_automation_rule",
                msg="Thiếu thiết bị đích hoặc hành động cho liên kết.",
                status_code=400,
                target="automation_rules",
            )
        e_dev = str(payload.get("else_device_id") or "")
        e_act = str(payload.get("else_action") or "")
        delay_sec = float(payload.get("delay_seconds") or 0.0)
        label = str(payload.get("label") or "").strip()

        allowed_then, reason_then = engine.check_device_permission(t_dev, actor_tier=tier, actor_user_id=user_id)
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
            allowed_else, reason_else = engine.check_device_permission(e_dev, actor_tier=tier, actor_user_id=user_id)
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
                threshold_op=str(payload.get("threshold_op") or ""),
                threshold_value=payload.get("threshold_value"),
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
        act = str(payload.get("action") or "").strip()
        if not target_devs or not act:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="invalid_schedule",
                msg="Bạn muốn đặt lịch cho thiết bị nào và bật hay tắt?",
                status_code=400,
                target="schedules",
            )
        hhmm = str(payload.get("time_hhmm") or "")
        schedule_type = str(payload.get("schedule_type") or "once")
        weekdays = payload.get("weekdays")
        run_date_vn = str(payload.get("run_date_vn") or "")
        label = str(payload.get("label") or "")
        for td in target_devs:
            allowed_td, reason_td = engine.check_device_permission(td, actor_tier=tier, actor_user_id=user_id)
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
            schedule_type="daily" if (schedule_type == "weekly" or weekdays) else schedule_type,
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
                    weekdays=weekdays,
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
                weekdays=payload.get("weekdays"),
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
        dev = str(payload.get("device_id") or "").strip()
        act = str(payload.get("action") or "").strip()
        if not dev or not act:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="invalid_timer",
                msg="Bạn muốn hẹn giờ cho thiết bị nào và bật hay tắt?",
                status_code=400,
                target="timers",
            )
        hours = float(payload.get("hours") or 0.0)
        minutes = float(payload.get("minutes") or 0.0)
        seconds = float(payload.get("seconds") or 0.0)
        repeat = str(payload.get("repeat") or "once").strip() or "once"
        total_sec = hours * 3600.0 + minutes * 60.0 + seconds
        if total_sec <= 0:
            seconds = 10.0
            total_sec = 10.0
        for td in _expand_targets(dev):
            allowed_td, reason_td = engine.check_device_permission(td, actor_tier=tier, actor_user_id=user_id)
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
            target_dev = str(payload.get("device_id") or existing_t.get("raw_target") or existing_t.get("device_id") or "").strip()
            target_act = (new_action or str(existing_t.get("action") or "")).strip()
            if not target_dev or not target_act:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="timer_update_failed",
                    msg="Bạn muốn đổi hẹn giờ cho thiết bị nào và bật hay tắt?",
                    status_code=400,
                    target=tid,
                )
            for td in _expand_targets(target_dev):
                allowed_td, reason_td = engine.check_device_permission(td, actor_tier=tier, actor_user_id=user_id)
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
            match_devs = {"all_lights", "living_room_light", "bedroom_light"} if dev == "all_lights" else ({dev} if dev else set())
            for r in list_automation_rules(include_disabled=True, owner_user_id=(None if tier == 1 else user_id)):
                if match_devs and r["when_device_id"] not in match_devs and r["then_device_id"] not in match_devs:
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

    if action_kind == "run_custom_command":
        cid = str(payload.get("command_id") or "").strip()
        phrase_q = str(payload.get("phrase") or "").strip()
        matched_cmd = None
        if cid:
            matched_cmd = next(
                (c for c in list_custom_commands(include_disabled=False, owner_user_id=user_id) if c["command_id"] == cid),
                None,
            )
        if matched_cmd is None and phrase_q:
            matched_cmd = find_custom_command_by_text(phrase_q, owner_user_id=user_id)
        if matched_cmd is None:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="scene_not_found",
                msg="Không tìm thấy lệnh tùy chỉnh cần chạy.",
                status_code=404,
                target=cid or phrase_q or "custom_command",
            )
        steps = list(matched_cmd.get("steps") or [])
        ok_steps_run, err_steps_run = check_steps_rbac(steps, tier)
        if not ok_steps_run:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_custom_command_step",
                msg=err_steps_run,
                status_code=403,
                target=str(matched_cmd.get("phrase") or "custom_command"),
            )
        control_steps = [st for st in steps if not is_custom_query_step(str(st.get("device_id") or ""), str(st.get("action") or ""))]
        query_steps = [st for st in steps if is_custom_query_step(str(st.get("device_id") or ""), str(st.get("action") or ""))]
        results: list[dict[str, Any]] = []
        exec_items: list[dict[str, Any]] = []
        prev_uid = getattr(engine, "_current_user_id", user_id)
        prev_role = getattr(engine, "_current_role", role)
        try:
            engine._current_user_id = user_id
            engine._current_role = role
            for st in control_steps:
                dev_id = str(st.get("device_id") or "")
                action = str(st.get("action") or "")
                for td in _expand_targets(dev_id):
                    prev_st = str((engine.devices.get(td) or {}).get("state") or "")
                    res = await engine.execute_device_action(
                        td,
                        action,
                        request_tier=tier,
                        request_user_name=user_name,
                        request_role=role,
                        request_user_id=user_id,
                        source=source,
                    )
                    results.append(res)
                    if not res.get("ok") and res.get("rbac_blocked"):
                        err_msg = str(res.get("exact_spoken_reply") or res.get("error") or "Xin lỗi, bạn không có quyền thực hiện lệnh này.")
                        return _deny_mutation_error(
                            session=session,
                            source=source,
                            category="rbac_deny_custom_command_step",
                            msg=err_msg,
                            status_code=403,
                            target=td,
                            extra={"results": results},
                        )
                    if not res.get("ok") and res.get("board_offline"):
                        bh_off = res.get("board_health") or (
                            engine.get_board_health() if hasattr(engine, "get_board_health") else {}
                        )
                        err_msg = str(
                            res.get("exact_spoken_reply")
                            or res.get("error")
                            or "Mạch điều khiển hiện đang mất kết nối."
                        )
                        return {
                            "handled": True,
                            "status_code": 503,
                            "payload": {
                                "ok": False,
                                "confirmed": False,
                                "executed": False,
                                "board_offline": True,
                                "delivery_status": "BOARD_OFFLINE",
                                "kind": "custom_command_board_offline",
                                "command": matched_cmd,
                                "results": results,
                                "last_seen": res.get("last_seen", bh_off.get("last_seen")),
                                "last_seen_vi": res.get("last_seen_vi", bh_off.get("last_seen_vi", "")),
                                "board_health": bh_off,
                                "error": err_msg,
                                "reply": err_msg,
                                "exact_spoken_reply": err_msg,
                                "rejection_speech": err_msg,
                                "snapshot": engine.get_snapshot(session=session, sync=False),
                            },
                        }
                    new_st = str((engine.devices.get(td) or {}).get("state") or "")
                    exec_items.append({
                        "device_id": td,
                        "action": action,
                        "previous_state": prev_st,
                        "state": new_st,
                    })
        finally:
            engine._current_user_id = prev_uid
            engine._current_role = prev_role

        from backend.voice.vietnamese_policy import (
            execute_custom_command_query_steps,
            format_short_action_reply_vi,
        )

        query_spoken = ""
        query_data: dict[str, Any] = {}
        if query_steps:
            q_ok, q_rbac, q_err, query_spoken, query_data = execute_custom_command_query_steps(
                query_steps, engine, tier
            )
            if not q_ok and q_rbac:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="rbac_deny_custom_command_step",
                    msg=q_err,
                    status_code=403,
                    target=str(matched_cmd.get("phrase") or "custom_command"),
                )

        if control_steps:
            await engine.emit({"type": "state_snapshot", "snapshot": engine.get_snapshot()})

        ctrl_spoken = format_short_action_reply_vi(exec_items, engine.devices) if exec_items else ""
        if ctrl_spoken and query_spoken:
            spoken_exec = f"{ctrl_spoken} {query_spoken}"
        elif query_spoken:
            spoken_exec = query_spoken
        elif ctrl_spoken:
            spoken_exec = ctrl_spoken
        else:
            spoken_exec = f"Đã chạy lệnh '{matched_cmd['phrase']}'."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "executed": True,
                "kind": "custom_command_executed",
                "command": matched_cmd,
                "results": results,
                **query_data,
                "reply": spoken_exec,
                "exact_spoken_reply": spoken_exec,
                "snapshot": engine.get_snapshot(session=session, sync=False),
            },
        }

    if action_kind == "reset_devices":
        if tier != 1:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_reset_devices",
                msg="Chỉ chủ nhà cấp 1 mới có quyền đặt lại trạng thái toàn bộ thiết bị.",
                status_code=403,
                target="reset_devices",
            )
        device_reset_plan = [
            ("living_room_light", "turn_off"),
            ("bedroom_light", "turn_off"),
            ("garden_pump", "turn_off"),
            ("alarm_siren", "turn_off"),
            ("speaker_amp", "turn_off"),
            ("main_door", "close"),
        ]
        reset_results: list[dict[str, Any]] = []
        for did, act in device_reset_plan:
            if not can_control_device(tier, did):
                continue
            r_dev = await engine.execute_device_action(
                did,
                act,
                source=source,
                request_tier=tier,
                request_user_name=user_name,
                request_role=role,
                request_user_id=user_id,
                trigger_chains=False,
            )
            reset_results.append(r_dev)
            if not r_dev.get("ok") and r_dev.get("board_offline"):
                bh_off = r_dev.get("board_health") or (
                    engine.get_board_health() if hasattr(engine, "get_board_health") else {}
                )
                err_msg = str(
                    r_dev.get("exact_spoken_reply")
                    or r_dev.get("error")
                    or "Mạch điều khiển hiện đang mất kết nối."
                )
                return {
                    "handled": True,
                    "status_code": 503,
                    "payload": {
                        "ok": False,
                        "confirmed": False,
                        "executed": False,
                        "board_offline": True,
                        "delivery_status": "BOARD_OFFLINE",
                        "kind": "devices_reset_board_offline",
                        "results": reset_results,
                        "last_seen": r_dev.get("last_seen", bh_off.get("last_seen")),
                        "last_seen_vi": r_dev.get("last_seen_vi", bh_off.get("last_seen_vi", "")),
                        "board_health": bh_off,
                        "error": err_msg,
                        "reply": err_msg,
                        "exact_spoken_reply": err_msg,
                        "rejection_speech": err_msg,
                        "snapshot": engine.get_snapshot(session=session, sync=False),
                    },
                }
        await engine.emit({"type": "state_snapshot", "snapshot": engine.get_snapshot()})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã đặt lại trạng thái các thiết bị về mặc định."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "executed": True,
                "kind": "devices_reset",
                "results": reset_results,
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
        if hasattr(engine, "factory_reset"):
            res_rst = await engine.factory_reset(scope="all", bypass_rbac=True)
        else:
            res_rst = await engine.confirm_factory_reset(confirmed=True)
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = str(res_rst.get("exact_spoken_reply") or "Đã xác nhận. Đã khôi phục cài đặt gốc toàn hệ thống.")
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "executed": True,
                "kind": "factory_reset",
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind in (
        "create_compound_rule",
        "update_compound_rule",
        "toggle_compound_rule",
        "delete_compound_rule",
        "toggle_schedule",
        "reset_automations",
    ):
        from backend.ai_tool_registry import execute_extended_confirmed_mutation

        ext_res = await execute_extended_confirmed_mutation(
            engine=engine,
            session=session,
            source=source,
            action_kind=action_kind,
            payload=payload,
        )
        if ext_res is not None:
            return ext_res

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
    """Resolve Step-2 confirmation ('xác nhận'/'đúng'/'ừ'/'ok'/'chốt đi' vs 'không'/'hủy'/>20s TTL)."""
    user_id, tier, _, _ = _session_actor(session)
    skey = session_key or _resolve_session_key(session, source)
    pending, was_expired = get_pending_confirmation(owner_user_id=user_id, session_key=skey)
    if pending is None and not was_expired:
        return None

    pending_kind = str((pending or {}).get("action_kind") or "")
    decision = _classify_confirmation_utterance(
        raw_text,
        has_pending=True,
        pending_action_kind=pending_kind,
    )
    if decision is None:
        return None
    if pending is not None and tier >= 3 and pending.get("action_kind") != "set_device":
        return _deny_mutation_error(
            session=session,
            source=source,
            category="rbac_deny_confirmation",
            msg=GUEST_ONLY_TOGGLE_MSG_VI,
            status_code=403,
            target="pending_confirmation",
        )
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


async def handle_pending_interruption_if_any(
    *,
    raw_text: str,
    engine: Any,
    session: Any,
    source: str,
    session_key: str = "",
    is_new_valid_intent: bool = False,
) -> dict[str, Any] | None:
    """Handle unrelated utterances while a pending confirmation exists.

    - If the new utterance is a valid command/query, cancel the stale pending confirmation and return None so the new command runs.
    - If it is unrelated chatter/nonsense, keep the pending confirmation and return a brief reminder without executing it.
    """
    user_id, _, _, _ = _session_actor(session)
    skey = session_key or _resolve_session_key(session, source)
    pending, _ = get_pending_confirmation(owner_user_id=user_id, session_key=skey)
    if pending is None:
        return None
    if is_new_valid_intent:
        consume_or_cancel_pending_confirmation(
            pending["pending_id"],
            owner_user_id=user_id,
            new_status="cancelled",
        )
        return None
    q = str(pending.get("prompt_question") or "Xác nhận thao tác đang chờ?").strip()
    spoken = f"Đang chờ xác nhận: {q} Bạn nói đồng ý hoặc hủy nhé."
    return {
        "handled": True,
        "status_code": 200,
        "payload": {
            "ok": True,
            "executed": False,
            "confirmed": False,
            "requires_confirmation": True,
            "pending_id": pending["pending_id"],
            "kind": "confirmation_reminder",
            "reply": spoken,
            "exact_spoken_reply": spoken,
            "snapshot": engine.get_snapshot(session=session, sync=False) if engine is not None else {},
        },
    }


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
    if cand_norm in ("he thong", "toan he thong", "nha thong minh", "ca nha", "tat ca", "moi nguoi", "tat ca moi nguoi"):
        return True, None
    if cand_norm in ("toi", "minh", "ban than", "nha minh", "thiet bi"):
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
            fire_ts = float(t.get("fire_at") or t.get("fire_at_epoch") or t.get("fire_epoch") or 0.0)
            rem = max(1, int(round(fire_ts - time.time())))
            act_txt = format_device_action_vi(t["device_id"], t["action"])
            own = str(t.get("owner_name") or t.get("owner_user_id") or "")
            items.append(f"{act_txt} còn {format_duration_vi(rem)}" + (f" của {own}" if tier == 1 else ""))
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
    """Detect and answer ADDENDUM A pool/member questions without hijacking device/macro/run/delete commands."""
    raw_low = str(raw_text or "").strip().lower()
    norm_s = normalize_phrase(raw_text)
    norm = f" {norm_s} "
    from backend.voice.vietnamese_policy import has_vi_diacritics

    has_diac = has_vi_diacritics(raw_low)
    # Never hijack explicit create/edit/delete/run/reset or direct device-control imperatives into pool/member queries
    norm_no_lead = re.sub(r"^(?:hay|xin|vui\s+long|lam\s+on)\s+", "", norm_s).strip()
    if re.match(
        r"^(?:tao|them|cai|dat|luu|thiet\s+lap|dang\s+ky|gan|ghi\s+nho|nho|"
        r"sua|chinh\s+sua|chinh|cap\s+nhat|doi|xoa|go(?:\s+bo)?|huy|reset|dat\s+lai|"
        r"chay|kich\s+hoat|thuc\s+hien|bat|tat|mo|dong|khoa|khep|ngat|cup|dap|dung|ngung|khoi\s+dong|cho\s+chay)\b",
        norm_no_lead,
    ):
        return None

    is_mutation_verb = any(
        w in norm
        for w in (
            " tao ", " them ", " cai ", " dat ", " luu ", " thiet lap ", " dang ky ", " gan ", " ghi nho ",
            " sua ", " chinh sua ", " doi ", " xoa ", " go ", " go bo ", " huy ", " reset ", " dat lai ",
            " chay ", " kich hoat ", " thuc hien ",
            " bat ", " tat ", " mo ", " dong ", " ngat ", " cup ", " khoi dong ",
        )
    )
    # Avoid ASCII 'may' colliding with 'máy bơm' / 'máy lạnh'
    has_may_question = bool(
        (re.search(r"\bmấy\b", raw_low) if has_diac else re.search(r"\b(?:co\s+may|cap\s+may|may\s+(?:nguoi|thanh\s+vien|lenh|lich|luat|thiet\s+bi))\b", norm_s))
    )
    has_question_cue = (
        "?" in str(raw_text)
        or has_may_question
        or any(
            q in norm
            for q in (
                " nao ", " gi ", " bao nhieu ", " danh sach ", " liet ke ",
                " co nhung ", " xem ", " hien co ", " ai ", " ten gi ", " cap may ",
            )
        )
    )
    if not has_question_cue:
        return None

    # Never hijack AI identity questions ("bạn là ai", "bạn tên gì") as household member queries
    if any(k in norm for k in (" ban la ai ", " em la ai ", " ban ten gi ", " ban ten la gi ", " ten cua ban ", " ai tao ra ban ")):
        return None

    pool_kind: str | None = None
    has_member_noun = (
        any(
            k in norm
            for k in (
                " thanh vien ", " tai khoan ", " nguoi dung ", " danh sach quyen ",
                " ai co quyen ", " ai dang co quyen ", " toi cap may ",
                " trong nha co ai ", " co nhung ai ", " nha co may nguoi ",
                " ai trong gia dinh ", " gia dinh co may nguoi ",
            )
        )
        or (has_may_question and " cap " in norm)
    )
    if has_member_noun:
        pool_kind = "members"
    elif any(k in norm for k in (" lenh custom", " lenh tuy chinh", " khau lenh", " nhung lenh", " cac lenh", " phim tat", " scene", " kich ban")):
        pool_kind = "custom_commands"
    elif any(k in norm for k in (" lien ket", " luat lien ket", " luat tu dong", " nhung luat", " cac luat")):
        pool_kind = "links"
    elif any(k in norm for k in (" hen gio", " lich hen", " nhung lich", " cac lich", " co lich", " xem lich", " liet ke lich", " danh sach lich")) and " lich su " not in norm:
        pool_kind = "timers"

    if pool_kind is None:
        return None
    if is_mutation_verb and not any(q in norm for q in (" nao", " gi", " co nhung", " danh sach", " liet ke", " bao nhieu")) and not has_may_question:
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
    """Detect explicit scoped reset or bulk-clear intents for timers, links, or custom commands."""
    raw_clean = str(raw_text or "").strip()
    norm = normalize_phrase(raw_clean)
    norm_no_lead = re.sub(
        r"^(?:(?:toi|minh|em)\s+muon\s+|giup\s+(?:toi|minh|anh|chi|em)\s+|ban\s+|hay\s+|xin\s+|vui\s+long\s+|lam\s+on\s+)+",
        "",
        norm,
    ).strip()
    polite_infix = r"(?:(?:giup|gium|dum|ho|cho)\s+(?:toi|minh|anh|chi|em)\s+)?"
    has_reset = bool(
        re.match(
            rf"^(?:reset|ri\s+set|dat\s+lai|thiet\s+lap\s+lai|khoi\s+tao\s+lai)\b|"
            rf"^(?:xoa|huy|don|go|bo|dep|loai)(?:\s+(?:bo|sach|di))?\s+{polite_infix}"
            r"(?:het|toan\s+bo|tat\s+ca|moi|cac|sach)\b|"
            rf"^(?:xoa|don|huy)\s+(?:sach|het)\b",
            norm_no_lead,
        )
        or re.search(
            r"^(?:xoa|huy|don|go|bo|dep|reset)\b.+\b(?:hen\s+gio|lich(?:\s+(?:hen|trinh))?)\b.+\b(?:het|toan\s+bo|tat\s+ca|sach)\b",
            norm_no_lead,
        )
    )
    has_bare_timer_reset = bool(
        re.match(
            rf"^(?:xoa|huy(?:\s+bo)?|don(?:\s+sach)?|bo|tat|dung)\s+{polite_infix}(?:hen\s+gio|lich\s+(?:hen|trinh))(?:\s+(?:va\s+(?:hen\s+gio|lich(?:\s+(?:hen|trinh))?)|cua\s+.+))?$",
            norm_no_lead,
        )
    )
    if not has_reset and not has_bare_timer_reset:
        return None

    if any(k in norm_no_lead for k in ("lien ket", "luat", "quy tac")):
        pool_kind = "links"
    elif any(k in norm_no_lead for k in ("hen gio", "lich")):
        pool_kind = "timers"
    elif any(k in norm_no_lead for k in ("lenh custom", "lenh tuy chinh", "khau lenh", "cau lenh", "scene", "kich ban", "ngu canh", "bi danh", "lenh")):
        pool_kind = "custom_commands"
    elif any(k in norm_no_lead for k in ("tat ca", "toan bo")):
        pool_kind = "all"
    else:
        return None

    clear_all, target_q = _extract_target_member_scope(raw_clean)
    return pool_kind, clear_all, target_q


def _has_clock_or_timer_marker(snippet: str, *, reject_any_digit: bool = False) -> bool:
    """Return True if snippet contains clock/timer markers so schedules/timers never match STEP 4."""
    n_time = _normalize_vi_spoken_numbers(snippet)
    if re.search(r"\d+\s*(?:gio|giay|phut|tieng|h\b|:)|\b(?:hang ngay|moi ngay|hen gio)\b", n_time):
        return True
    if reject_any_digit and re.search(r"\d", n_time):
        return True
    return False


_STEP4_ACTION_VERB_START_RE = (
    r"(?:bật|tắt|mở|đóng|khóa|khoá|ngắt|dừng|ngừng|ngưng|cúp|tưới|đọc|xem|kiểm\s+tra|"
    r"bat|tat|mo|dong|khoa|ngat|dung|ngung|cup|tuoi|doc|xem|kiem\s+tra)"
)
_STEP4_IMPLICIT_BLOCKED_PREFIX_RE = re.compile(
    r"^(?:khi|neu|he|cu|tu\s+gio|hen\s+gio|dat\s+lich|sua\s+lich|doi\s+lich|cap\s+nhat\s+lich|"
    r"doi\s+hen\s+gio|sua\s+hen\s+gio|xoa|huy|reset|ri\s+set|dat\s+lai|thiet\s+lap\s+lai|khoi\s+phuc|"
    r"hoi\s+phuc|cap\s+quyen|thu\s+hoi|xem|kiem\s+tra|trang\s+thai)\b"
)
_STEP4_IMPLICIT_BLOCKED_PHRASE_WORDS: frozenset[str] = frozenset({
    "nhiet do", "do am", "cam bien", "trang thai", "ban", "em", "toi", "anh", "chi",
})
_CONDITIONAL_BODY_IN_MACRO_RE = re.compile(
    r"^(?:(?:tôi|mình|em)\s+muốn\s+|giúp\s+(?:tôi|mình)\s+|hãy\s+)?"
    r"(?:tạo|thêm|đặt|lưu|cài|tao|them|dat|luu|cai)\s+"
    r"(?:khẩu\s+lệnh|lệnh|khau\s+lenh|lenh)(?:\s+mới|\s+moi)?\s+"
    r"(?:cứ|khi|nếu|hễ|cu|khi|neu|he)\s+.+\s+(?:là|thì|la|thi)\s+.+$",
    re.IGNORECASE,
)


def _parse_custom_command_create_or_edit(
    raw: str,
) -> tuple[str, list[dict[str, str]], bool, bool] | None:
    """Parse compositional Vietnamese custom-command create/edit utterances.

    Returns (phrase, steps, is_edit, is_strict_explicit) or None.
    Conditional rule grammar ('tạo lệnh cứ <trigger> là/thì <action>') takes precedence and returns None here.
    """
    from backend.voice.vietnamese_policy import _UNSUPPORTED_DEVICE_RE

    raw_s = str(raw or "").strip()
    if not raw_s:
        return None
    # Conditional rule precedence: if body starts with cứ/khi/nếu/hễ ... là/thì ..., route to STEP 5 rule parser.
    if _CONDITIONAL_BODY_IN_MACRO_RE.match(raw_s):
        return None

    # Strip optional polite lead-in like "tôi muốn ..." / "giúp tôi ..." / "hãy ..."
    raw_s = re.sub(
        r"^(?:tôi\s+muốn|mình\s+muốn|em\s+muốn|giúp\s+(?:tôi|mình)|hãy|xin|toi\s+muon|minh\s+muon|hay)\s+",
        "",
        raw_s,
        flags=re.IGNORECASE,
    ).strip()
    norm_full = normalize_phrase(raw_s)
    has_unsupported = bool(_UNSUPPORTED_DEVICE_RE.search(f" {norm_full} "))

    def _clean_custom_phrase(p: str) -> str:
        c = p.strip(" '\".,:")
        c = re.sub(r"^(?:gọi\s+là|có\s+tên(?:\s+là)?|tên(?:\s+là)?|goi\s+la|co\s+ten(?:\s+la)?|ten(?:\s+la)?)\s+", "", c, flags=re.IGNORECASE).strip(" '\".,:")
        c = re.sub(r"[,;:\s]+(?:nội\s+dung|noi\s+dung)$", "", c, flags=re.IGNORECASE).strip(" '\".,:")
        c = re.sub(r"^(?:khẩu\s+lệnh|câu\s+lệnh|lệnh|câu|chế\s+độ|bí\s+danh|khau\s+lenh|cau\s+lenh|lenh|cau|che\s+do|bi\s+danh)\s+", "", c, flags=re.IGNORECASE).strip(" '\".,:")
        return c

    # Branch 1: Explicit compositional macro-creation / edit grammar (preserves HTTP 400 on invalid/unsupported steps)
    m_strict = re.match(
        r"^(?P<verb>tạo|thêm|đặt|lưu|gán|cài|thiết\s+lập|đăng\s+ký|ghi\s+nhớ|nhớ|chỉnh\s+sửa|sửa|cập\s+nhật|đổi)\s+"
        r"(?:(?:giúp|giùm|dùm|hộ|cho)\s+(?:tôi|mình|anh|chị|em|bạn)\s+)?"
        r"(?:một\s+)?"
        r"(?:khẩu\s+lệnh|câu\s+lệnh|lệnh(?:\s+(?:mới|riêng|tắt|tùy\s+chỉnh|custom|giọng\s+nói))?|"
        r"câu|ngữ\s+cảnh|kịch\s+bản|scene|chế\s+độ|bí\s+danh|phím\s+tắt(?:\s+giọng\s+nói)?)"
        r"(?:\s+mới|\s+moi)?\s+"
        r"(?:(?:gọi\s+là|có\s+tên(?:\s+là)?|tên(?:\s+là)?)\s+)?"
        r"(?:'([^']+)'|\"([^\"]+)\"|(.+?))\s+"
        r"(?:(?:,\s*)?nội\s+dung\s+là|cho\s+thao\s+tác|thành\s+lệnh|để|là|gồm|bao\s+gồm|sẽ|thành|như\s+sau|:|=|->)\s+(.+)$",
        raw_s,
        flags=re.IGNORECASE,
    )
    if not m_strict:
        m_strict = re.match(
            r"^(?P<verb>tao|them|dat|luu|gan|cai|thiet\s+lap|dang\s+ky|ghi\s+nho|nho|chinh\s+sua|sua|cap\s+nhat|doi)\s+"
            r"(?:(?:giup|gium|dum|ho|cho)\s+(?:toi|minh|anh|chi|em|ban)\s+)?"
            r"(?:mot\s+)?"
            r"(?:khau\s+lenh|cau\s+lenh|lenh(?:\s+(?:moi|rieng|tat|tuy\s+chinh|custom|giong\s+noi))?|"
            r"cau|ngu\s+canh|kich\s+ban|scene|che\s+do|bi\s+danh|phim\s+tat(?:\s+giong\s+noi)?)"
            r"(?:\s+moi)?\s+"
            r"(?:(?:goi\s+la|co\s+ten(?:\s+la)?|ten(?:\s+la)?)\s+)?"
            r"(?:'([^']+)'|\"([^\"]+)\"|(.+?))\s+"
            r"(?:(?:,\s*)?noi\s+dung\s+la|cho\s+thao\s+tac|thanh\s+lenh|de|la|gom|bao\s+gom|se|thanh|nhu\s+sau|:|=|->)\s+(.+)$",
            strip_accents(raw_s),
            flags=re.IGNORECASE,
        )
    if m_strict:
        verb_norm = normalize_phrase(m_strict.group("verb") or "")
        phrase = _clean_custom_phrase(m_strict.group(2) or m_strict.group(3) or m_strict.group(4) or "")
        steps_text = (m_strict.group(5) or "").strip()
        if phrase and not _has_clock_or_timer_marker(phrase, reject_any_digit=False):
            # Guard against conditional cue prefixes inside the macro name
            if re.match(r"^(?:cu|khi|neu|he)\s+", normalize_phrase(phrase)):
                return None
            if _UNSUPPORTED_DEVICE_RE.search(f" {normalize_phrase(steps_text)} "):
                steps = []
            else:
                steps = parse_multi_steps_from_text(steps_text)
            is_edit = verb_norm in ("sua", "chinh sua", "cap nhat", "doi")
            return phrase, steps, is_edit, True

    # Non-strict branch never accepts unsupported devices or clock/timer/rule markers
    if has_unsupported or _STEP4_IMPLICIT_BLOCKED_PREFIX_RE.search(norm_full) or " thi " in f" {norm_full} ":
        return None

    # Branch 2: Clean implicit "<1-3 word phrase> (là|thành) <valid steps>" (no garbled ASR wrappers)
    m_imp = re.match(
        r"^(?P<phrase>\S+(?:\s+\S+){0,2})\s+(?P<sep>là|thành|la|thanh)\s+(?P<steps>.+)$",
        raw_s,
        flags=re.IGNORECASE,
    )
    if m_imp:
        phrase = _clean_custom_phrase(m_imp.group("phrase") or "")
        sep_norm = normalize_phrase(m_imp.group("sep") or "")
        steps_text = (m_imp.group("steps") or "").strip()
        if (
            phrase
            and not _has_clock_or_timer_marker(phrase, reject_any_digit=True)
            and not _has_clock_or_timer_marker(steps_text, reject_any_digit=False)
            and _parse_sensor_trigger(phrase) is None
        ):
            phrase_norm = normalize_phrase(phrase)
            if phrase_norm and phrase_norm not in _STEP4_IMPLICIT_BLOCKED_PHRASE_WORDS:
                p_dev, p_act = parse_single_device_and_action(phrase)
                if p_dev is None and p_act is None:
                    steps = parse_multi_steps_from_text(steps_text)
                    if steps:
                        is_edit = sep_norm == "thanh"
                        return phrase, steps, is_edit, False

    return None


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
    # STEP 3. RESETS: Compositional destructive-verb + target parser (confirmation mandatory)
    # Block non-destructive save/status/query verbs & negated/deferred/question utterances from matching resets!
    # ------------------------------------------------------------------
    from backend.voice.vietnamese_policy import is_no_action_safety_blocked_vi

    norm_step3 = re.sub(r"^(?:hay|xin|vui\s+long|lam\s+on)\s+", "", norm).strip()
    is_non_destructive_save_or_status = bool(
        "?" in raw
        or is_no_action_safety_blocked_vi(raw)
        or re.match(r"^(?:save|luu|sao\s+luu|truy\s+van|kiem\s+tra|xem|doc|hoi)\b", norm_step3)
    )
    has_keep_settings = bool(re.search(r"\bgiu\s+nguyen\s+(?:cai\s+dat|cau\s+hinh)\b", norm))
    is_reboot_system = bool(
        not is_non_destructive_save_or_status
        and re.search(r"\bkhoi\s+dong\s+lai\b", norm)
        and (
            has_keep_settings
            or re.search(r"\bkhoi\s+dong\s+lai\s+(?:bo\s+dieu\s+khien|he\s+thong|nha\s+thong\s+minh|thiet\s+bi|toan\s+bo)\b", norm)
            or parse_single_device_and_action(raw)[0] is None
        )
    )
    if not is_non_destructive_save_or_status and (
        is_reboot_system
        or re.search(
            r"\b(?:"
            r"(?:reset|ri\s+set|dat\s+lai|thiet\s+lap\s+lai)\s+(?:lai\s+)?(?:trang\s+thai\s+)?(?:cac\s+|toan\s+bo\s+|tat\s+ca\s+|moi\s+)?thiet\s+bi|"
            r"(?:reset|ri\s+set|dat\s+lai|thiet\s+lap\s+lai)\s+trang\s+thai|"
            r"(?:dua|dat|tra)\s+(?:trang\s+thai\s+)?(?:cac\s+|toan\s+bo\s+|tat\s+ca\s+|moi\s+)?thiet\s+bi\s+ve\s+(?:trang\s+thai\s+)?(?:ban\s+dau|mac\s+dinh)"
            r")\b",
            norm,
        )
    ):
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_reset_devices",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target="reset_devices",
            )
        if tier != 1:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_reset_devices",
                msg="Chỉ chủ nhà cấp 1 mới có quyền đặt lại trạng thái toàn bộ thiết bị.",
                status_code=403,
                target="reset_devices",
            )
        return await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="reset_devices",
            payload={"scope": "devices"},
            prompt_summary="Đặt lại trạng thái các thiết bị về mặc định",
        )

    if not is_non_destructive_save_or_status and not has_keep_settings and "he thong tuoi" not in norm and re.search(
        r"\b(?:"
        r"(?:khoi\s+phuc|hoi\s+phuc|dat\s+lai|thiet\s+lap\s+lai|reset|ri\s+set|xoa(?:\s+(?:sach|het|bo))?|don(?:\s+(?:sach|het))?)\s+"
        r"(?:(?:giup|gium|dum|ho|cho)\s+(?:toi|minh|anh|chi|em)\s+)?"
        r"(?:toan\s+bo\s+|tat\s+ca\s+|moi\s+|het\s+|cac\s+|toan\s+)?(?:cai\s+dat(?:\s+(?:goc|mac\s+dinh|nha\s+san\s+xuat))?|"
        r"cau\s+hinh(?:\s+(?:goc|mac\s+dinh|he\s+thong))?|thiet\s+lap(?:\s+(?:goc|mac\s+dinh|he\s+thong))?|"
        r"mac\s+dinh(?:\s+goc)?|trang\s+thai\s+xuat\s+xuong|xuat\s+xuong|he\s+thong)|"
        r"factory\s+reset|"
        r"(?:dua|dat|tra)\s+(?:(?:toan\s+bo|tat\s+ca|moi|cac)\s+)?(?:moi\s+thu(?:\s+trong\s+he\s+thong)?|he\s+thong|cai\s+dat|cau\s+hinh|thiet\s+lap)\s+ve\s+(?:trang\s+thai\s+)?(?:mac\s+dinh|xuat\s+xuong|goc|ban\s+dau)|"
        r"(?:xoa|don)\s+(?:sach\s+|het\s+|toan\s+bo\s+|tat\s+ca\s+|moi\s+|cac\s+)?(?:cai\s+dat|cau\s+hinh|thiet\s+lap)\b"
        r")\b",
        norm,
    ):
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_factory_reset",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target="factory_reset",
            )
        if tier != 1:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_factory_reset",
                msg="Chỉ chủ nhà cấp 1 mới được khôi phục cài đặt gốc ạ.",
                status_code=403,
                target="factory_reset",
            )
        return await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="factory_reset",
            payload={"confirmed_via": source},
            prompt_summary="Khôi phục cài đặt gốc toàn hệ thống",
        )

    reset_intent = None if is_non_destructive_save_or_status else _detect_scoped_reset_intent(raw)
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
    # Compositional grammar: <create|edit verb> <command noun> [name introducer] <phrase> <separator> <steps>
    # ------------------------------------------------------------------
    parsed_custom = _parse_custom_command_create_or_edit(raw)
    if parsed_custom is not None:
        phrase, steps, is_edit_custom, is_strict_custom = parsed_custom
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_create_custom_command",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target="custom_commands",
            )
        if not steps:
            if is_strict_custom:
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
        else:
            allowed_steps, reason_steps = check_steps_rbac(steps, tier)
            if not allowed_steps:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="rbac_deny_custom_command_device",
                    msg=reason_steps,
                    status_code=403,
                    target="custom_commands",
                )
            steps_summary = ", ".join(format_device_action_vi(st["device_id"], st["action"]) for st in steps)

            existing_match = None
            if is_edit_custom:
                owner_scope = None if tier == 1 else user_id
                existing_cmds = list_custom_commands(include_disabled=True, owner_user_id=owner_scope)
                p_norm = normalize_phrase(phrase)
                p_stripped = re.sub(r"^(?:sap|sua|doi|bat|me)\s+", "", p_norm).strip()
                for cmd in existing_cmds:
                    c_norm = str(cmd.get("phrase_norm") or normalize_phrase(str(cmd.get("phrase") or ""))).strip()
                    if c_norm == p_norm or (p_stripped and c_norm == p_stripped):
                        existing_match = cmd
                        break
                if existing_match is None and p_norm:
                    for cmd in existing_cmds:
                        c_norm = str(cmd.get("phrase_norm") or normalize_phrase(str(cmd.get("phrase") or ""))).strip()
                        if c_norm.endswith(f" {p_norm}") or (p_stripped and c_norm.endswith(f" {p_stripped}")):
                            existing_match = cmd
                            break
                if existing_match is None and p_norm:
                    best_sc = 0.0
                    for cmd in existing_cmds:
                        c_norm = str(cmd.get("phrase_norm") or normalize_phrase(str(cmd.get("phrase") or ""))).strip()
                        sc = _fuzzy_ratio(p_stripped or p_norm, c_norm)
                        if sc >= 78.0 and sc > best_sc:
                            best_sc = sc
                            existing_match = cmd

            if existing_match is not None:
                clean_phrase = existing_match["phrase"]
                return await prepare_pending_mutation(
                    engine=engine,
                    session=session,
                    source=source,
                    session_key=skey,
                    action_kind="update_custom_command",
                    payload={"command_id": existing_match["command_id"], "phrase": clean_phrase, "steps": steps},
                    prompt_summary=f"Cập nhật lệnh '{clean_phrase}' gồm {steps_summary}",
                )

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
    # STEP 4b. MODIFY EXISTING TIMER OR CLOCK SCHEDULE
    # ------------------------------------------------------------------
    m_mod_sched = re.match(
        r"^(?:hãy\s+|hay\s+|giúp\s+(?:tôi|mình|anh|chị|em)\s+)?(?:đổi|chỉnh\s+sửa|sửa|cập\s+nhật|doi|chinh\s+sua|sua|cap\s+nhat)\s+"
        r"(?:(?:giúp|giùm|dùm|hộ)\s+(?:tôi|mình|anh|chị|em)\s+)?"
        r"(?:lịch\s+(?:hẹn|trình|định\s+kỳ|tự\s+động)|lịch|lich\s+(?:hen|trinh|dinh\s+ky|tu\s+dong)|lich)\s+(.+?)\s+(?:thành|sang|thanh)\s+(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if not m_mod_sched:
        m_from_to_sched = re.match(
            r"^(?:từ|tu)\s+(.+?)\s+(?:đến|tới|sang|thành|den|toi|sang|thanh)\s+(.+)$",
            raw.rstrip("?!.,;: "),
            flags=re.IGNORECASE,
        )
        if m_from_to_sched:
            _old_hh_chk, _, _ = _parse_clock_hhmm_vi(f"lúc {m_from_to_sched.group(1).strip()}")
            _new_hh_chk, _, _ = _parse_clock_hhmm_vi(f"lúc {m_from_to_sched.group(2).strip()}")
            if _old_hh_chk and _new_hh_chk:
                _scope_chk = None if tier == 1 else user_id
                if any(sc.get("time_hhmm") == _old_hh_chk for sc in list_schedules(include_disabled=False, owner_user_id=_scope_chk)):
                    m_mod_sched = m_from_to_sched
    if m_mod_sched:
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_update_schedule",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target="schedules",
            )
        from backend.automation_engine import parse_weekdays_vi

        old_part = m_mod_sched.group(1).strip()
        new_part = m_mod_sched.group(2).strip()
        old_hhmm, _, _ = _parse_clock_hhmm_vi(f"lúc {old_part}")
        new_hhmm, new_daily, _ = _parse_clock_hhmm_vi(f"lúc {new_part}")
        old_dev, _ = parse_single_device_and_action(old_part)
        new_dev, new_act = parse_single_device_and_action(new_part)
        new_weekdays = parse_weekdays_vi(new_part)
        if new_hhmm or new_act or new_weekdays:
            owner_scope = None if tier == 1 else user_id
            candidates = list_schedules(include_disabled=False, owner_user_id=owner_scope) or list_schedules(include_disabled=True, owner_user_id=owner_scope)
            target_sc = None
            for sc in candidates:
                if old_hhmm and sc.get("time_hhmm") != old_hhmm:
                    continue
                if old_dev and sc.get("device_id") != old_dev:
                    continue
                target_sc = sc
                break
            if target_sc is None:
                return {
                    "handled": True,
                    "status_code": 404,
                    "payload": {
                        "ok": False,
                        "error": "Không tìm thấy lịch hẹn cần sửa.",
                        "reply": "Không tìm thấy lịch hẹn cần sửa.",
                        "exact_spoken_reply": "Không tìm thấy lịch hẹn cần sửa.",
                    },
                }
            eff_hhmm = new_hhmm or str(target_sc.get("time_hhmm") or "")
            sc_type = "daily" if (new_daily or new_weekdays) else str(target_sc.get("schedule_type") or "once")
            conflict_msg = check_tier1_schedule_conflict(
                actor_tier=tier,
                time_hhmm=eff_hhmm,
                schedule_type=sc_type,
                exclude_schedule_id=str(target_sc["schedule_id"]),
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
            upd_payload: dict[str, Any] = {
                "schedule_id": target_sc["schedule_id"],
                "time_hhmm": eff_hhmm,
                "schedule_type": sc_type,
            }
            if new_weekdays:
                upd_payload["weekdays"] = new_weekdays
            if new_dev and new_dev in DEFAULT_DEVICES:
                upd_payload["device_id"] = new_dev
            if new_act and new_act in ACTION_TO_STATE:
                upd_payload["action"] = new_act
            return await prepare_pending_mutation(
                engine=engine,
                session=session,
                source=source,
                session_key=skey,
                action_kind="update_schedule",
                payload=upd_payload,
                prompt_summary=f"Đổi lịch {target_sc['time_hhmm']} thành {eff_hhmm}",
            )

    m_mod_timer = re.match(
        r"^(?:đổi|sửa|cập\s+nhật|doi|sua|cap\s+nhat)\s+(?:hẹn\s+giờ|hen\s+gio)\s*(.*?)\s+(?:thành|sang|thanh)\s+(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if m_mod_timer:
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_modify_timer",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target="timers",
            )
        old_part = m_mod_timer.group(1).strip()
        new_part = m_mod_timer.group(2).strip()
        dev_mod, act_mod = parse_single_device_and_action(old_part)
        total_sec, _ = _parse_countdown_seconds(new_part)
        if total_sec > 0:
            owner_scope = None if tier == 1 else user_id
            timers_list = list_pending_timers(owner_user_id=owner_scope)
            target_tm = None
            for tm in timers_list:
                if dev_mod and tm.get("device_id") != dev_mod:
                    continue
                target_tm = tm
                break
            conflict_msg = check_tier1_schedule_conflict(
                actor_tier=tier,
                fire_epoch=time.time() + total_sec,
                exclude_timer_id=str(target_tm["timer_id"]) if target_tm else None,
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
            dev_target = dev_mod or (str(target_tm.get("device_id") or "all_devices") if target_tm else "all_devices")
            dev_name = DEFAULT_DEVICES.get(dev_target, {}).get("name", "thiết bị").lower()
            return await prepare_pending_mutation(
                engine=engine,
                session=session,
                source=source,
                session_key=skey,
                action_kind="modify_timer",
                payload={
                    "timer_id": str(target_tm["timer_id"]) if target_tm else "",
                    "device_id": dev_target,
                    "new_action": act_mod or "",
                    "seconds": total_sec,
                },
                prompt_summary=f"Đổi hẹn giờ {dev_name} thành {format_duration_vi(sec_i)}",
            )

    # ------------------------------------------------------------------
    # STEP 5. CREATE LINKED AUTOMATION RULE (device-trigger AND sensor-trigger with per-rule thresholds)
    # ------------------------------------------------------------------
    m_rule = re.search(
        r"(?:^|\b)(?:(?:tạo|thêm|đặt|cài|tao|them|dat|cai)\s+(?:cho\s+(?:tôi|mình)\s+)?(?:luật|luat|quy\s+tắc|quy\s+tac|liên\s+kết|lien\s+ket|khẩu\s+lệnh|khau\s+lenh|lệnh|lenh)(?:\s+mới|\s+moi)?\s*)?"
        r"(?:khi|nếu|hễ|bất\s+cứ\s+lúc\s+nào|mỗi\s+lúc|từ\s+giờ|neu|he|bat\s+cu\s+luc\s+nao|moi\s+luc|tu\s+gio)\s+(.+?)\s+(?:thì|thi)\s+(?:luôn|cả|tự\s+động|cùng|luon|ca|tu\s+dong|cung)?\s*(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if not m_rule:
        m_rule = re.search(
            r"^(?:(?:tạo|thêm|đặt|cài|tao|them|dat|cai)\s+(?:cho\s+(?:tôi|mình)\s+)?(?:luật|luat|quy\s+tắc|quy\s+tac|liên\s+kết|lien\s+ket)(?:\s+mới|\s+moi)?(?:\s+là|\s+la|\s*:)?\s+)?"
            r"(.+?)\s+(?:thì|thi)\s+(?:luôn|cả|tự\s+động|cùng|luon|ca|tu\s+dong|cung)?\s*(.+)$",
            raw,
            flags=re.IGNORECASE,
        )
    if not m_rule:
        m_rule = re.search(
            r"(?:^|\b)(?:(?:(?:tạo|thêm|đặt|cài|tao|them|dat|cai)\s+(?:cho\s+(?:tôi|mình)\s+)?(?:luật|luat|quy\s+tắc|quy\s+tac|liên\s+kết|lien\s+ket|khẩu\s+lệnh|khau\s+lenh|lệnh|lenh)(?:\s+mới|\s+moi)?|quy\s+tắc|quy\s+tac)\s+)?"
            r"(?:cứ|cu)\s+(.+?)\s+(?:là|la|thì|thi)\s+(?:tự\s+động\s+)?(.+)$",
            raw,
            flags=re.IGNORECASE,
        )
    if not m_rule:
        m_rule = re.search(
            r"^(?:đặt|tạo|thêm|cài|dat|tao|them|cai)\s+(?:quy\s+tắc|quy\s+tac|luật|luat|liên\s+kết|lien\s+ket)\s+(.+?)\s+(?:là|la)\s+(.+)$",
            raw,
            flags=re.IGNORECASE,
        )
    if not m_rule:
        m_rule = re.search(
            r"(?:^|\b)(?:(?:tạo|thêm|đặt|cài|tao|them|dat|cai)\s+(?:cho\s+(?:tôi|mình)\s+)?(?:luật|luat|quy\s+tắc|quy\s+tac|liên\s+kết|lien\s+ket)(?:\s+mới|\s+moi)?\s*)?"
            r"(?:khi|nếu|hễ|bất\s+cứ\s+lúc\s+nào|mỗi\s+lúc|từ\s+giờ|neu|he|bat\s+cu\s+luc\s+nao|moi\s+luc|tu\s+gio)?\s*"
            r"(.+?)\s+(?:hệ\s+thống\s+(?:tự\s+động|tự|sẽ)|he\s+thong\s+(?:tu\s+dong|tu|se)|tự\s+động|tu\s+dong|sẽ|se)\s+(.+)$",
            raw,
            flags=re.IGNORECASE,
        )
        if m_rule and _parse_sensor_trigger_with_threshold(m_rule.group(1).strip()) is None:
            m_rule = None
    comma_sensor_when_then: tuple[str, str] | None = None
    if not m_rule and "," in raw:
        _c_left, _c_right = raw.split(",", 1)
        _c_trig = _parse_sensor_trigger_with_threshold(_c_left.strip())
        if _c_trig is not None and _c_right.strip():
            _c_left_n = f" {normalize_phrase(_c_left)} "
            _c_right_n = f" {normalize_phrase(_c_right)} "
            _has_rule_intent_cue = bool(
                _c_trig[3] is not None
                or any(k in _c_right_n for k in (" tu dong ", " tu bat ", " tu tat ", " tu mo ", " tu dong ", " he thong tu "))
                or any(k in f" {norm} " for k in (" tao luat ", " dat luat ", " quy tac ", " lien ket "))
            )
            _is_situational_direct_ctx = bool(
                any(k in _c_left_n for k in (" qua roi ", " qua ", " roi ", " dang ", " la ", " ngoai san ", " ngoai cong "))
                or any(k in _c_right_n for k in (" ho toi ", " giup toi ", " giup minh ", " giup em ", " giup anh ", " ho em ", " gium toi ", " ngay ", " di "))
            )
            if _has_rule_intent_cue and not (not (_c_trig[3] is not None) and _is_situational_direct_ctx):
                comma_sensor_when_then = (_c_left.strip(), _c_right.strip())

    if comma_sensor_when_then is not None or (
        m_rule
        and (
            " thi " in f" {norm} "
            or _parse_sensor_trigger_with_threshold(m_rule.group(1).strip()) is not None
            or any(
                k in norm
                for k in (
                    "khi ", "neu ", "he ", "bat cu luc nao", "moi luc", "tu gio",
                    "tao luat", "lien ket", "quy tac", "cu mo ", "cu dong ", "cu bat ", "cu tat ",
                )
            )
        )
    ):
        if comma_sensor_when_then is not None:
            when_part, then_part_full = comma_sensor_when_then
        else:
            when_part = m_rule.group(1).strip()  # type: ignore[union-attr]
            then_part_full = m_rule.group(2).strip()  # type: ignore[union-attr]
        else_part = ""
        m_else = re.split(r"\b(?:ngược lại|nguoc lai|còn nếu|con neu)\b", then_part_full, maxsplit=1, flags=re.IGNORECASE)
        then_part = m_else[0].strip()
        if len(m_else) > 1:
            else_part = m_else[1].strip()

        sensor_trig = _parse_sensor_trigger_with_threshold(when_part)
        w_dev: str | None = None
        w_act: str | None = None
        w_state: str = "ON"
        th_op: str = ""
        th_val: float | None = None
        is_sensor_when = False

        if sensor_trig is not None:
            w_dev, w_state, th_op, th_val = sensor_trig
            is_sensor_when = True
        else:
            w_dev, w_act = parse_single_device_and_action(when_part)
            if w_dev and w_act:
                w_state = ACTION_TO_STATE.get(w_act, "ON")
                if w_dev == "main_door" and w_state in ("ON", "OFF"):
                    w_state = "OPEN" if w_state == "ON" else "CLOSED"
            else:
                w_dev = None

        t_dev, t_act = parse_single_device_and_action(then_part, default_action=w_act)
        if t_dev == "all_lights":
            t_dev = "living_room_light"

        if w_dev and (is_sensor_when or w_dev in DEFAULT_DEVICES) and t_dev and t_dev in DEFAULT_DEVICES and t_act:
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

            allowed_then, reason_then = engine.check_device_permission(t_dev, actor_tier=tier, actor_user_id=user_id)
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
                    allowed_else, reason_else = engine.check_device_permission(ed, actor_tier=tier, actor_user_id=user_id)
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

            w_label = (
                format_sensor_trigger_vi(w_dev, w_state, threshold_op=th_op, threshold_value=th_val)
                if is_sensor_when
                else format_device_action_vi(w_dev, w_act or "turn_on").lower()
            )
            t_label = format_device_action_vi(t_dev, t_act).lower()
            prompt_desc = f"Tạo liên kết khi {w_label} thì {t_label}"
            if e_dev:
                prompt_desc += f", ngược lại {format_device_action_vi(e_dev, e_act).lower()}"
            return await prepare_pending_mutation(
                engine=engine,
                session=session,
                source=source,
                session_key=skey,
                action_kind="create_automation_rule",
                payload={
                    "when_device_id": w_dev,
                    "when_state": w_state,
                    "threshold_op": th_op,
                    "threshold_value": th_val,
                    "then_device_id": t_dev,
                    "then_action": t_act,
                    "else_device_id": e_dev,
                    "else_action": e_act,
                },
                prompt_summary=prompt_desc,
            )

    # ------------------------------------------------------------------
    # STEP 6. CANCEL / DELETE SINGLE TIMER, SCHEDULE, RULE, CUSTOM COMMAND
    # ------------------------------------------------------------------
    norm_del = re.sub(
        r"^(?:(?:toi|minh|em)\s+muon\s+|giup\s+(?:toi|minh|anh|chi|em)\s+|ban\s+|hay\s+|xin\s+|vui\s+long\s+|lam\s+on\s+)+",
        "",
        norm,
    ).strip()
    if re.match(
        r"^(?:huy(?:\s+bo)?|xoa(?:\s+(?:bo|di))?|go(?:\s+bo)?|dep(?:\s+bo)?|loai\s+bo|bo(?:\s+di)?|tat|dung)\s+"
        r"(?:(?:giup|gium|dum|ho|cho)\s+(?:toi|minh|anh|chi|em)\s+)?"
        r"(?:(?:cai|mot)\s+)?"
        r"(?:hen\s+gio|lich(?:\s+(?:hen|trinh|dinh\s+ky))?|luat|quy\s+tac|lien\s+ket|"
        r"cau\s+lenh|khau\s+lenh|lenh(?:\s+(?:rieng|tat|tuy\s+chinh|custom|giong\s+noi|da\s+luu|cu|moi))?|"
        r"phim\s+tat(?:\s+giong\s+noi)?|ngu\s+canh|scene|kich\s+ban|bi\s+danh)\b",
        norm_del,
    ):
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_delete_automation",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target="automation",
            )
        if "hen gio" in norm_del:
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
        if "lich" in norm_del:
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
        if any(k in norm_del for k in ("luat", "quy tac", "lien ket")):
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
        if any(k in norm_del for k in ("lenh", "khau lenh", "cau lenh", "phim tat", "ngu canh", "scene", "kich ban", "bi danh")):
            phrase_clean = re.sub(
                r"^(?:huy(?:\s+bo)?|xoa(?:\s+(?:bo|di))?|go(?:\s+bo)?|dep(?:\s+bo)?|loai\s+bo|bo(?:\s+di)?|tat|dung)\s+"
                r"(?:(?:giup|gium|dum|ho|cho)\s+(?:toi|minh|anh|chi|em)\s+)?"
                r"(?:(?:cai|mot)\s+)?"
                r"(?:khau\s+lenh|cau\s+lenh|lenh(?:\s+(?:rieng|tat|tuy\s+chinh|custom|giong\s+noi|da\s+luu|cu|moi))?|"
                r"phim\s+tat(?:\s+giong\s+noi)?|ngu\s+canh|scene|kich\s+ban|bi\s+danh)\s*"
                r"(?:(?:goi\s+la|co\s+ten(?:\s+la)?|ten(?:\s+la)?)\s+)?",
                "",
                norm_del,
            ).strip(" '\".,:")
            phrase_clean = re.sub(
                r"\s+(?:giup\s+(?:minh|toi|anh|chi|em)|cho\s+(?:minh|toi|anh|chi|em)|ho\s+(?:minh|toi|anh|chi|em)|(?:gium|dum)(?:\s+(?:minh|toi|tui|em))?|di|luon|ngay|nhe|nha|a)+$",
                "",
                phrase_clean,
            ).strip(" '\".,:")
            owner_scope = None if tier == 1 else user_id
            existing_cmds = list_custom_commands(include_disabled=True, owner_user_id=owner_scope)
            matched_del = None
            if phrase_clean:
                for cmd in existing_cmds:
                    c_norm = str(cmd.get("phrase_norm") or normalize_phrase(str(cmd.get("phrase") or ""))).strip()
                    if c_norm == phrase_clean or c_norm in phrase_clean or phrase_clean in c_norm:
                        matched_del = cmd
                        break
                if matched_del is None:
                    best_sc = 0.0
                    for cmd in existing_cmds:
                        c_norm = str(cmd.get("phrase_norm") or normalize_phrase(str(cmd.get("phrase") or ""))).strip()
                        sc = _fuzzy_ratio(phrase_clean, c_norm)
                        if sc >= 72.0 and sc > best_sc:
                            best_sc = sc
                            matched_del = cmd
            del_payload: dict[str, Any] = {"phrase": matched_del["phrase"] if matched_del else (phrase_clean or norm_del)}
            if matched_del is not None:
                del_payload["command_id"] = matched_del["command_id"]
            del_label = matched_del["phrase"] if matched_del else (phrase_clean or raw)
            return await prepare_pending_mutation(
                engine=engine,
                session=session,
                source=source,
                session_key=skey,
                action_kind="delete_custom_command",
                payload=del_payload,
                prompt_summary=f"Xóa lệnh '{del_label}'",
            )

    # ------------------------------------------------------------------
    # STEP 7. CLOCK SCHEDULE ("bật đèn phòng ngủ lúc 14 giờ 35", "tắt đèn lúc 22:30 hằng ngày")
    # ------------------------------------------------------------------
    def _clarify_missing_timer_or_schedule(
        *,
        kind_vi: str,
        dev_opt: str | None,
        act_opt: str | None,
        missing_time: bool = False,
    ) -> dict[str, Any]:
        if missing_time:
            msg_c = f"Bạn muốn {kind_vi} sau bao lâu?"
        elif not dev_opt and not act_opt:
            msg_c = f"Bạn muốn {kind_vi} cho thiết bị nào và bật hay tắt?"
        elif not dev_opt:
            act_vi = "tắt" if act_opt in ("turn_off", "close") else ("mở" if act_opt == "open" else "bật")
            if re.search(r"\b(?:đèn|den)\b", raw, flags=re.IGNORECASE):
                msg_c = f"Bạn muốn {kind_vi} {act_vi} đèn phòng khách hay đèn phòng ngủ?"
            else:
                msg_c = f"Bạn muốn {kind_vi} {act_vi} thiết bị nào?"
        else:
            if dev_opt == "main_door":
                msg_c = f"Bạn muốn {kind_vi} mở hay đóng cửa chính?"
            elif dev_opt == "all_lights":
                msg_c = f"Bạn muốn {kind_vi} bật hay tắt tất cả đèn?"
            elif dev_opt == "all_devices":
                msg_c = f"Bạn muốn {kind_vi} bật hay tắt tất cả thiết bị?"
            else:
                lbl = str(DEFAULT_DEVICES.get(dev_opt, {}).get("name") or "thiết bị này").lower()
                msg_c = f"Bạn muốn {kind_vi} bật hay tắt {lbl}?"
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "executed": False,
                "requires_confirmation": False,
                "needs_clarification": True,
                "kind": "clarify_missing_timer_target",
                "reply": msg_c,
                "exact_spoken_reply": msg_c,
            },
        }

    hhmm, is_daily, cleaned_clock = _parse_clock_hhmm_vi(raw)
    if hhmm is not None and not is_no_action_safety_blocked_vi(raw):
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_schedule",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target="schedules",
            )
        from backend.voice.vietnamese_policy import (
            _detect_wrong_diacritic_near_miss_clarification,
            has_vi_diacritics,
        )

        raw_has_diac = has_vi_diacritics(raw)
        dev, act = parse_single_device_and_action(raw)
        # Only fall back to ASCII-stripped cleaned_clock when input is unaccented (never bypass diacritic safety!)
        if (not dev or not act) and not raw_has_diac and cleaned_clock:
            dev2, act2 = parse_single_device_and_action(cleaned_clock)
            dev = dev or dev2
            act = act or act2
        if dev is None and has_removed_device_mention(raw):
            return _deny_mutation_error(
                session=session,
                source=source,
                category="unsupported_removed_device",
                msg=(
                    "Thiết bị hoặc tính năng bạn yêu cầu (quạt, điều hòa, học lệnh hồng ngoại IR) "
                    "không còn được hỗ trợ trên hệ thống 6 thiết bị mới."
                ),
                status_code=400,
                target="removed_device",
            )
        if dev is None:
            nm_sched = _detect_wrong_diacritic_near_miss_clarification(raw)
            if nm_sched is not None:
                return {
                    "handled": True,
                    "status_code": 200,
                    "payload": {
                        "ok": True,
                        "executed": False,
                        "requires_confirmation": False,
                        "needs_clarification": True,
                        "kind": "clarify_near_miss_schedule",
                        "reply": nm_sched,
                        "exact_spoken_reply": nm_sched,
                    },
                }
        if not dev or not act:
            has_explicit_sched_cue = any(
                k in f" {norm} "
                for k in (" dat lich ", " lich ", " hen gio ", " hen lich ", " hang ngay ", " moi ngay ", " ngay nao cung ", " sang mai ", " toi nay ")
            )
            if has_explicit_sched_cue:
                return _clarify_missing_timer_or_schedule(kind_vi="đặt lịch", dev_opt=dev, act_opt=act)
        if dev and act:
            target_devs = _expand_targets(dev)
            for td in target_devs:
                allowed_td, reason_td = engine.check_device_permission(td, actor_tier=tier, actor_user_id=user_id)
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
    # STEP 8. COUNTDOWN TIMER ("tắt đèn phòng khách sau 1 phút", "10 giây nữa bật đèn phòng ngủ")
    # ------------------------------------------------------------------
    norm_time = _normalize_vi_spoken_numbers(raw)
    is_del_or_reset_verb = bool(
        re.match(
            r"^(?:(?:toi|minh|em)\s+muon\s+|giup\s+(?:toi|minh|anh|chi|em)\s+|hay\s+|xin\s+|vui\s+long\s+|lam\s+on\s+)*"
            r"(?:xoa|huy|don|go|dep|loai\s+bo|reset)\b",
            norm,
        )
    )
    has_countdown_cue = bool(
        not is_del_or_reset_verb
        and re.search(
            r"(?:\bsau\s+\d+|\d+(?:\.\d+)?\s*(?:giay|phut|tieng)\b|\bhen\s+\d+|\b\d+(?:\.\d+)?\s*(?:giay|phut|gio)\s+nua\b|\bhen gio\b)",
            norm_time,
        )
    )
    if has_countdown_cue and not is_no_action_safety_blocked_vi(raw):
        if tier >= 3:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_timer",
                msg=GUEST_ONLY_TOGGLE_MSG_VI,
                status_code=403,
                target="timers",
            )
        from backend.voice.vietnamese_policy import (
            _detect_wrong_diacritic_near_miss_clarification,
            has_vi_diacritics,
        )

        raw_has_diac = has_vi_diacritics(raw)
        total_sec, cleaned_cd = _parse_countdown_seconds(raw)
        dev, act = parse_single_device_and_action(raw)
        # Only fall back to ASCII-stripped cleaned_cd when input is unaccented (never bypass diacritic safety!)
        if (not dev or not act) and not raw_has_diac and cleaned_cd:
            dev2, act2 = parse_single_device_and_action(cleaned_cd)
            dev = dev or dev2
            act = act or act2
        if dev is None and has_removed_device_mention(raw):
            return _deny_mutation_error(
                session=session,
                source=source,
                category="unsupported_removed_device",
                msg=(
                    "Thiết bị hoặc tính năng bạn yêu cầu (quạt, điều hòa, học lệnh hồng ngoại IR) "
                    "không còn được hỗ trợ trên hệ thống 6 thiết bị mới."
                ),
                status_code=400,
                target="removed_device",
            )
        if dev is None:
            nm_timer = _detect_wrong_diacritic_near_miss_clarification(raw)
            if nm_timer is not None:
                return {
                    "handled": True,
                    "status_code": 200,
                    "payload": {
                        "ok": True,
                        "executed": False,
                        "requires_confirmation": False,
                        "needs_clarification": True,
                        "kind": "clarify_near_miss_timer",
                        "reply": nm_timer,
                        "exact_spoken_reply": nm_timer,
                    },
                }
        if not dev or not act:
            return _clarify_missing_timer_or_schedule(kind_vi="hẹn giờ", dev_opt=dev, act_opt=act)
        if total_sec <= 0:
            return _clarify_missing_timer_or_schedule(kind_vi="hẹn giờ", dev_opt=dev, act_opt=act, missing_time=True)
        for td in _expand_targets(dev):
            allowed_td, reason_td = engine.check_device_permission(td, actor_tier=tier, actor_user_id=user_id)
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
            prompt_summary=f"Đặt hẹn giờ sau {format_duration_vi(sec_i)} sẽ {act_label.lower()}",
        )

    # Defense-in-depth: explicit schedule creation without clock time MUST clarify instead of leaking to direct execution
    if (
        not is_del_or_reset_verb
        and "?" not in raw
        and not is_no_action_safety_blocked_vi(raw)
        and re.search(
            r"(?:^|\s)(?:dat\s+lich|len\s+lich|tao\s+lich|hen\s+lich|lap\s+lich|lich\s+tu\s+dong)(?:\s|$)",
            f" {norm} ",
        )
        and not re.search(r"\b(?:xem|danh\s+sach|liet\s+ke|sua|chinh\s+sua|doi|tam\s+dung|tam\s+tat|bat\s+lai)\b", norm)
    ):
        msg_sched_time = "Bạn muốn đặt lịch vào lúc mấy giờ?"
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "executed": False,
                "requires_confirmation": False,
                "needs_clarification": True,
                "kind": "clarify_missing_schedule_time",
                "reply": msg_sched_time,
                "exact_spoken_reply": msg_sched_time,
            },
        }

    # ------------------------------------------------------------------
    # STEP 9. RUN PER-USER CUSTOM COMMAND FROM SQLITE POOL (stages short confirmation)
    # ------------------------------------------------------------------
    matched_cmd = find_custom_command_by_text(raw, owner_user_id=user_id)
    if matched_cmd is None:
        raw_punct_clean = re.sub(r"[?!.,;:\"'`]+", " ", raw).strip()
        if raw_punct_clean and raw_punct_clean != raw:
            matched_cmd = find_custom_command_by_text(raw_punct_clean, owner_user_id=user_id)
        if matched_cmd is None and raw_punct_clean:
            q_norm = normalize_phrase(raw_punct_clean)
            q_toks = q_norm.split()
            if q_toks:
                from backend.voice.vietnamese_policy import (
                    _UNSUPPORTED_DEVICE_RE,
                    is_foreign_or_nonsense_input,
                )

                is_bad_q, _ = is_foreign_or_nonsense_input(raw_punct_clean)
                if not is_bad_q and not _UNSUPPORTED_DEVICE_RE.search(f" {q_norm} "):
                    scored_cmds: list[tuple[float, dict[str, Any]]] = []
                    suffix_cmds: list[dict[str, Any]] = []
                    for cmd in list_custom_commands(include_disabled=False, owner_user_id=user_id):
                        c_norm = str(cmd.get("phrase_norm") or normalize_phrase(str(cmd.get("phrase") or ""))).strip()
                        c_toks = c_norm.split()
                        if not c_toks:
                            continue
                        if len(c_toks) == len(q_toks):
                            sc = _fuzzy_ratio(q_norm, c_norm)
                            if sc >= 88.0:
                                scored_cmds.append((sc, cmd))
                        elif len(q_toks) >= 2 and len(q_norm) >= 5 and len(c_toks) == len(q_toks) + 1 and c_norm.endswith(f" {q_norm}"):
                            suffix_cmds.append(cmd)
                    if scored_cmds:
                        scored_cmds.sort(key=lambda pair: pair[0], reverse=True)
                        best_sc, best_cmd = scored_cmds[0]
                        second_sc = scored_cmds[1][0] if len(scored_cmds) > 1 else 0.0
                        if len(scored_cmds) == 1 or (best_sc - second_sc) >= 5.0:
                            matched_cmd = best_cmd
                    elif len(suffix_cmds) == 1:
                        matched_cmd = suffix_cmds[0]
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
        ok_steps, err_steps = check_steps_rbac(steps, tier)
        if not ok_steps:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_custom_command_step",
                msg=err_steps,
                status_code=403,
                target=str(matched_cmd.get("phrase") or "custom_command"),
            )
        steps_summary = str(
            matched_cmd.get("steps_summary")
            or ", ".join(format_device_action_vi(s.get("device_id", ""), s.get("action", "")) for s in steps)
        )
        return await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="run_custom_command",
            payload={
                "command_id": matched_cmd["command_id"],
                "phrase": matched_cmd["phrase"],
            },
            prompt_summary=f"Chạy lệnh '{matched_cmd['phrase']}' ({steps_summary})",
        )

    return None
