"""Server-side Acoustic Echo Guard and Natural Vietnamese Speech Sanitizer.

Provides two focused guards for the voice assistant pipeline:
1. ServerEchoGuard: suppresses incoming user transcripts or mic frames that echo
   recent AI speech within ECHO_WINDOW_SEC (8s) or during active AI playback + 400ms tail.
2. sanitize_spoken_vietnamese_text: strips command syntax, JSON payloads, function calls,
   and internal device/action tokens so spoken Vietnamese output stays natural.
"""

from __future__ import annotations

import collections
import difflib
import logging
import re
import time
import unicodedata
from typing import Deque

LOG = logging.getLogger("simulator.live.echo_guard")

ECHO_WINDOW_SEC = 8.0
ECHO_SIMILARITY_THRESHOLD = 0.80
ECHO_MIN_SUBSTRING_CHARS = 12
ECHO_MIN_SUBSTRING_WORDS = 3
SERVER_PLAYBACK_TAIL_SEC = 0.40

_DEVICE_ID_VI_MAP: dict[str, str] = {
    "main_door": "cửa chính",
    "living_room_light": "đèn phòng khách",
    "bedroom_light": "đèn phòng ngủ",
    "alarm_siren": "còi báo động",
    "garden_pump": "máy bơm tưới cây",
    "all_lights": "tất cả đèn",
    "all_devices": "tất cả thiết bị",
}

_KNOWN_TOOL_NAMES = (
    "control_device",
    "set_device",
    "list_devices",
    "get_device_state",
    "read_sensors",
    "create_timer",
    "list_timers",
    "delete_timer",
    "create_schedule",
    "list_schedules",
    "delete_schedule",
    "schedule_action",
    "update_timer",
    "create_schedule_clock",
    "create_custom_scene",
    "run_custom_scene",
    "delete_automation_item",
    "confirm_or_cancel_pending_action",
    "confirm_pending_action",
    "confirm_factory_reset",
    "query_pools_or_members",
    "query_pools",
    "reset_user_pool",
    "set_if_else_rule",
    "set_word_mapping",
    "create_alias_rule",
    "execute_alias_rule",
    "set_or_query_sensors",
    "query_knowledge_rag",
    "manage_member_link_permission",
    "grant_user_permission",
    "revoke_user_permission",
    "set_query_permission_policy",
    "admin_update_system_policy",
    "admin_upsert_knowledge_rag",
    "request_factory_reset",
)

_RE_CODE_FENCE = re.compile(r"```[\s\S]*?```")
_RE_JSON_OBJECT = re.compile(r"\{[^{}]*(?:\"[^\"]+\"\s*:[^{}]*)+[^{}]*\}")
_RE_JSON_ARRAY = re.compile(r"\[\s*(?:\{[^{}]*\}|\"[^\"]+\")(?:\s*,\s*(?:\{[^{}]*\}|\"[^\"]+\"))*\s*\]")
_RE_TOOL_CALL = re.compile(
    r"\b(?:" + "|".join(re.escape(n) for n in _KNOWN_TOOL_NAMES) + r")\s*\([^)]*\)",
    re.IGNORECASE,
)
_RE_BARE_TOOL_NAME = re.compile(
    r"\b(?:" + "|".join(re.escape(n) for n in _KNOWN_TOOL_NAMES) + r")\b",
    re.IGNORECASE,
)
_RE_CMD_SYNTAX_PAIR = re.compile(
    r"\b(?:open|close|turn_on|turn_off|set_device|exec|cmd|command)\s+"
    r"(?:main_door|living_room_light|bedroom_light|alarm_siren|garden_pump|all_lights|all_devices|fan|ac)\b",
    re.IGNORECASE,
)
_RE_KV_SYNTAX = re.compile(
    r"\b(?:device_id|action|target_state|when_device_id|when_state|then_device_id|then_action|"
    r"time_hhmm|schedule_type|delay_seconds|brightness_pct|temperature_c|fan_speed|timer_id|schedule_id)\s*[:=]\s*['\"]?[\w.:-]+['\"]?",
    re.IGNORECASE,
)
_RE_TECH_KEYS = re.compile(
    r"\b(?:device_id|target_state|when_device_id|then_device_id|then_action|schedule_type|time_hhmm|turn_on|turn_off)\b",
    re.IGNORECASE,
)
_RE_PARENS_WITH_CODE = re.compile(r"\(\s*[a-z_][a-z0-9_]*(?:\s*=\s*[^)]+)?\s*\)", re.IGNORECASE)
_RE_DEVICE_IDS = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _DEVICE_ID_VI_MAP) + r")\b",
    re.IGNORECASE,
)


def normalize_for_echo_compare(text: str) -> str:
    """Strip Vietnamese diacritics, lowercase, remove punctuation, collapse whitespace."""
    if not text:
        return ""
    s = str(text).replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", s)
    no_marks = "".join(ch for ch in nfkd if unicodedata.category(ch) != "Mn")
    cleaned = re.sub(r"[^a-z0-9\s]+", " ", no_marks.lower())
    return " ".join(cleaned.split())


_IMPERATIVE_CMD_PREFIXES = (
    "bat ",
    "tat ",
    "mo ",
    "dong ",
    "khoa ",
    "chinh ",
    "dat ",
    "hen ",
)


def _is_bare_imperative_echo_false_positive(user_norm: str, ai_norm: str) -> bool:
    """Avoid suppressing a fresh bare imperative user command ('mo cua chinh') because AI earlier replied 'da mo cua chinh'."""
    if not any(user_norm.startswith(p) for p in _IMPERATIVE_CMD_PREFIXES):
        return False
    if any(tok in user_norm.split() for tok in ("da", "roi", "minh", "em", "toi", "xin", "loi")):
        return False
    return ai_norm in (f"da {user_norm}", f"da {user_norm} roi", f"da {user_norm} roi a")


def compute_echo_similarity(user_norm: str, ai_norm: str) -> tuple[float, str]:
    """Return (score, match_reason) comparing normalized user and AI utterances."""
    if not user_norm or not ai_norm:
        return 0.0, ""
    if user_norm == ai_norm:
        return 1.0, "exact"
    if _is_bare_imperative_echo_false_positive(user_norm, ai_norm):
        return 0.0, ""

    seq_ratio = difflib.SequenceMatcher(None, user_norm, ai_norm).ratio()
    if seq_ratio >= ECHO_SIMILARITY_THRESHOLD:
        return seq_ratio, "sequence_similarity"

    user_words = user_norm.split()
    ai_words = ai_norm.split()

    if (
        len(user_norm) >= ECHO_MIN_SUBSTRING_CHARS
        and len(user_words) >= ECHO_MIN_SUBSTRING_WORDS
        and user_norm in ai_norm
    ):
        return 0.95, "user_in_ai_substring"

    if (
        len(ai_norm) >= ECHO_MIN_SUBSTRING_CHARS
        and len(ai_words) >= ECHO_MIN_SUBSTRING_WORDS
        and ai_norm in user_norm
    ):
        return 0.92, "ai_in_user_substring"

    if len(user_words) >= ECHO_MIN_SUBSTRING_WORDS and ai_words:
        ai_set = set(ai_words)
        overlap = sum(1 for w in user_words if w in ai_set) / float(len(user_words))
        if overlap >= 0.85:
            return overlap, "token_overlap"

    return seq_ratio, ""


class ServerEchoGuard:
    """Tracks recent AI spoken utterances and playback window to reject echo loops."""

    def __init__(
        self,
        *,
        window_sec: float = ECHO_WINDOW_SEC,
        similarity_threshold: float = ECHO_SIMILARITY_THRESHOLD,
        playback_tail_sec: float = SERVER_PLAYBACK_TAIL_SEC,
    ) -> None:
        self.window_sec = float(window_sec)
        self.similarity_threshold = float(similarity_threshold)
        self.playback_tail_sec = float(playback_tail_sec)
        self._recent_ai_utterances: Deque[tuple[float, str]] = collections.deque(maxlen=24)
        self._ai_playback_end_ts: float = 0.0

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_sec
        while self._recent_ai_utterances and self._recent_ai_utterances[0][0] < cutoff:
            self._recent_ai_utterances.popleft()

    def record_ai_utterance(self, text: str, now: float | None = None) -> None:
        ts = time.monotonic() if now is None else float(now)
        self._prune(ts)
        norm = normalize_for_echo_compare(text)
        if not norm:
            return
        if self._recent_ai_utterances and self._recent_ai_utterances[-1][1] == norm:
            self._recent_ai_utterances[-1] = (ts, norm)
            return
        self._recent_ai_utterances.append((ts, norm))

    def note_ai_audio_chunk(
        self,
        pcm_bytes_len: int,
        *,
        sample_rate: int = 24000,
        bytes_per_sample: int = 2,
        now: float | None = None,
    ) -> None:
        if pcm_bytes_len <= 0 or sample_rate <= 0:
            return
        ts = time.monotonic() if now is None else float(now)
        duration_sec = float(pcm_bytes_len) / float(sample_rate * bytes_per_sample)
        base = self._ai_playback_end_ts if self._ai_playback_end_ts > ts else ts
        self._ai_playback_end_ts = base + duration_sec

    def clear_ai_playback(self) -> None:
        self._ai_playback_end_ts = 0.0

    def is_playback_or_tail_active(self, now: float | None = None) -> bool:
        ts = time.monotonic() if now is None else float(now)
        return self._ai_playback_end_ts > 0.0 and ts < (self._ai_playback_end_ts + self.playback_tail_sec)

    def check_echo_transcript(
        self,
        user_text: str,
        now: float | None = None,
    ) -> tuple[bool, float, str]:
        """Return (is_echo, similarity, reason) without logging sensitive text."""
        ts = time.monotonic() if now is None else float(now)
        self._prune(ts)
        user_norm = normalize_for_echo_compare(user_text)
        if not user_norm:
            return False, 0.0, ""

        best_score = 0.0
        best_reason = ""
        best_age_ms = 0
        for ai_ts, ai_norm in reversed(self._recent_ai_utterances):
            score, reason = compute_echo_similarity(user_norm, ai_norm)
            if score > best_score:
                best_score = score
                best_reason = reason
                best_age_ms = max(0, int(round((ts - ai_ts) * 1000.0)))
            if reason and score >= self.similarity_threshold:
                LOG.debug(
                    "Suppressed echoed user transcript (reason=%s score=%.2f age_ms=%d user_len=%d)",
                    reason,
                    score,
                    best_age_ms,
                    len(user_norm),
                )
                return True, score, reason
        return False, best_score, best_reason


def sanitize_spoken_vietnamese_text(text: str) -> str:
    """Strip command tokens, JSON, function calls, and brackets from spoken AI output."""
    if not text:
        return ""
    s = str(text)
    s = _RE_CODE_FENCE.sub(" ", s)
    s = s.replace("`", "")
    s = _RE_JSON_OBJECT.sub(" ", s)
    s = _RE_JSON_ARRAY.sub(" ", s)
    s = _RE_TOOL_CALL.sub(" ", s)
    s = _RE_KV_SYNTAX.sub(" ", s)
    s = _RE_CMD_SYNTAX_PAIR.sub(" ", s)
    s = _RE_BARE_TOOL_NAME.sub(" ", s)
    s = _RE_TECH_KEYS.sub(" ", s)
    s = _RE_PARENS_WITH_CODE.sub(" ", s)
    s = _RE_DEVICE_IDS.sub(lambda m: _DEVICE_ID_VI_MAP.get(m.group(1).lower(), m.group(1)), s)
    s = re.sub(r"[\{\}\[\]<>]", " ", s)
    s = re.sub(r"\(\s*\)", " ", s)
    s = re.sub(r"\s+([.,!?;:])", r"\1", s)
    s = re.sub(r"([.,!?;:])\1+", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^[,;:\-–—]+\s*", "", s).strip()
    return s
