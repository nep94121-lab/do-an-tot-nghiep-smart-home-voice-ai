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
import math
import re
import struct
import time
import unicodedata
from typing import Deque

LOG = logging.getLogger("simulator.live.echo_guard")

ECHO_WINDOW_SEC = 8.0
ECHO_SIMILARITY_THRESHOLD = 0.80
ECHO_MIN_SUBSTRING_CHARS = 12
ECHO_MIN_SUBSTRING_WORDS = 3
SERVER_PLAYBACK_TAIL_SEC = 0.40
SERVER_BARGE_IN_HOLD_SEC = 0.25
SERVER_BARGE_IN_MIN_RMS = 0.038
SERVER_BARGE_IN_ECHO_RATIO = 1.85
SERVER_BARGE_IN_GAP_TOL_SEC = 0.14
SERVER_ECHO_WARMUP_SEC = 0.34
SERVER_ECHO_WARMUP_NEAR_RMS = 0.095
SERVER_ECHO_CORR_SUPPRESS_RHO = 0.76
SERVER_ECHO_CORR_LOCK_RHO = 0.72
SERVER_ECHO_ENV_HISTORY_LEN = 12
SERVER_REF_TARGET_SR = 2000
SERVER_MAX_REF_SAMPLES_2K = 24000
SERVER_MIN_NEG_LAG_SEC = 0.14
SERVER_MAX_SEARCH_LAG_SEC = 0.38

_DEVICE_ID_VI_MAP: dict[str, str] = {
    "main_door": "cửa chính",
    "living_room_light": "đèn phòng khách",
    "bedroom_light": "đèn phòng ngủ",
    "garden_pump": "máy bơm tưới cây",
    "alarm_siren": "còi báo động",
    "speaker_amp": "nguồn mạch loa",
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
    r"(?:main_door|living_room_light|bedroom_light|garden_pump|alarm_siren|speaker_amp|all_lights|all_devices)\b",
    re.IGNORECASE,
)
_RE_KV_SYNTAX = re.compile(
    r"\b(?:device_id|action|target_state|when_device_id|when_state|then_device_id|then_action|"
    r"time_hhmm|schedule_type|delay_seconds|brightness_pct|timer_id|schedule_id)\s*[:=]\s*['\"]?[\w.:-]+['\"]?",
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

_ECHO_NON_VERB_PHRASES = (
    "bao dong",
    "tu dong",
    "tieng dong",
    "chuyen dong",
    "hoat dong",
    "cong tac",
    "dong y",
    "tat ca",
)
_ECHO_ON_VERBS = frozenset({"bat", "mo"})
_ECHO_OFF_VERBS = frozenset({"tat", "dong", "khoa", "ngat", "ngung", "dung"})


def _extract_echo_polarity_verbs(norm_text: str) -> tuple[set[str], set[str]]:
    padded = f" {norm_text} "
    for phrase in _ECHO_NON_VERB_PHRASES:
        padded = padded.replace(f" {phrase} ", " ")
    toks = set(padded.split())
    return toks & _ECHO_ON_VERBS, toks & _ECHO_OFF_VERBS


def _has_opposite_action_verbs(user_norm: str, ai_norm: str) -> bool:
    u_on, u_off = _extract_echo_polarity_verbs(user_norm)
    a_on, a_off = _extract_echo_polarity_verbs(ai_norm)
    if (u_off and a_on and not a_off) or (u_on and a_off and not a_on):
        return True
    if (u_off and a_on and not u_on) or (u_on and a_off and not u_off):
        return True
    return False


def _is_bare_imperative_echo_false_positive(user_norm: str, ai_norm: str) -> bool:
    """Avoid suppressing a fresh bare imperative user command ('mo cua chinh', 'dong cua chinh',
    or multi-device imperatives like 'dong cua chinh lai tat luon den phong khach') because AI
    earlier spoke a framed confirmation question or completion/status reply."""
    if not any(user_norm.startswith(p) for p in _IMPERATIVE_CMD_PREFIXES):
        return False
    tokens = user_norm.split()
    if len(tokens) > 14:
        return False
    non_verb_forbidden = ("da", "se", "minh", "em", "toi", "xin", "loi", "ban", "khong")
    if any(tok in tokens for tok in non_verb_forbidden) or "dong y" in user_norm:
        return False
    if tokens[-1] == "roi" or user_norm.endswith("roi a"):
        return False
    is_ai_framed = (
        ai_norm in (f"da {user_norm}", f"da {user_norm} roi", f"da {user_norm} roi a")
        or ai_norm.startswith(("da ", "minh da ", "minh se ", "em da ", "em se ", "ban muon "))
        or ai_norm.endswith(("ban dong y khong", "dung khong a", "roi a", " roi"))
        or " dang " in f" {ai_norm} "
    )
    if not is_ai_framed:
        return False
    if _has_opposite_action_verbs(user_norm, ai_norm):
        return True
    if len(tokens) <= 7:
        return True
    # For longer multi-device imperatives (8-14 tokens), allow unless user_norm is a verbatim clipped substring of ai_norm
    return user_norm not in ai_norm


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


def _pcm16_bytes_to_floats(pcm_bytes: bytes) -> list[float]:
    n = len(pcm_bytes) // 2
    if n <= 0:
        return []
    raw = struct.unpack(f"<{n}h", pcm_bytes[: n * 2])
    inv = 1.0 / 32768.0
    return [s * inv for s in raw]


def _downsample_floats_to_2k(samples: list[float], sample_rate: int) -> list[float]:
    if not samples or sample_rate <= 0:
        return []
    ratio = float(sample_rate) / float(SERVER_REF_TARGET_SR)
    out_len = int(len(samples) / ratio)
    if out_len <= 0:
        return []
    out: list[float] = []
    n_in = len(samples)
    for i in range(out_len):
        st = int(i * ratio)
        en = min(n_in, max(st + 1, int((i + 1) * ratio)))
        out.append(sum(samples[st:en]) / float(en - st))
    return out


def _rms_floats(samples: list[float]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / float(len(samples)))


def _zcr_floats(samples: list[float]) -> float:
    if len(samples) < 2:
        return 0.1
    crossings = 0
    prev = samples[0]
    for cur in samples[1:]:
        if (prev >= 0.0 and cur < 0.0) or (prev < 0.0 and cur >= 0.0):
            crossings += 1
        prev = cur
    return float(crossings) / float(len(samples) - 1)


def _spectral_mag_corr(mic_2k: list[float], ref_sl: list[float]) -> float:
    """Phase-invariant Hann-windowed DFT magnitude cosine similarity (100-800 Hz @ 2 kHz)."""
    n = min(len(mic_2k), len(ref_sl))
    if n < 16:
        return 0.0
    max_bin = min(17, n // 2)
    if max_bin <= 2:
        return 0.0
    two_pi_n = (2.0 * math.pi) / float(n)
    m_energy = 0.0
    r_energy = 0.0
    dot = 0.0
    for k in range(2, max_bin):
        m_re = 0.0
        m_im = 0.0
        r_re = 0.0
        r_im = 0.0
        for i in range(n):
            w = 0.5 * (1.0 - math.cos(two_pi_n * i))
            ang = two_pi_n * k * i
            ca = math.cos(ang)
            sa = math.sin(ang)
            mv = mic_2k[i] * w
            rv = ref_sl[i] * w
            m_re += mv * ca
            m_im -= mv * sa
            r_re += rv * ca
            r_im -= rv * sa
        m_mag = math.sqrt(m_re * m_re + m_im * m_im)
        r_mag = math.sqrt(r_re * r_re + r_im * r_im)
        m_energy += m_mag * m_mag
        r_energy += r_mag * r_mag
        dot += m_mag * r_mag
    if m_energy < 1e-12 or r_energy < 1e-12:
        return 0.0
    return min(1.0, dot / math.sqrt(m_energy * r_energy))


class ServerEchoGuard:
    """Tracks recent AI spoken utterances, TTS playback reference, and barge-in gate."""

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
        self._ai_playback_start_ts: float = 0.0
        self._ai_playback_end_ts: float = 0.0
        self._ref_2k: list[float] = []
        self._ref_origin_ts: float = 0.0
        self._locked_lag_2k: int | None = None
        self._lock_hits: int = 0
        self._echo_gain_est: float = 0.0
        self._env_hist_mic: list[float] = []
        self._env_hist_ref: list[float] = []
        self._estimated_echo_rms: float = 0.004
        self._barge_in_accum_sec: float = 0.0
        self._barge_in_miss_sec: float = 0.0

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
        pcm_bytes_len: int | bytes,
        *,
        sample_rate: int = 24000,
        bytes_per_sample: int = 2,
        pcm_bytes: bytes | None = None,
        now: float | None = None,
    ) -> None:
        if isinstance(pcm_bytes_len, (bytes, bytearray)):
            pcm_bytes = bytes(pcm_bytes_len)
            n_bytes = len(pcm_bytes)
        else:
            n_bytes = int(pcm_bytes_len)
        if n_bytes <= 0 or sample_rate <= 0:
            return
        ts = time.monotonic() if now is None else float(now)
        duration_sec = float(n_bytes) / float(sample_rate * bytes_per_sample)
        was_playing = self._ai_playback_end_ts > ts
        base = self._ai_playback_end_ts if was_playing else ts
        if not was_playing:
            self._ai_playback_start_ts = base
            self._ref_2k = []
            self._ref_origin_ts = base
            self._locked_lag_2k = None
            self._lock_hits = 0
            self._echo_gain_est = 0.0
            self._env_hist_mic = []
            self._env_hist_ref = []
            self._barge_in_accum_sec = 0.0
            self._barge_in_miss_sec = 0.0
        self._ai_playback_end_ts = base + duration_sec
        if pcm_bytes:
            ds = _downsample_floats_to_2k(_pcm16_bytes_to_floats(pcm_bytes), sample_rate)
            if ds:
                if not self._ref_2k:
                    self._ref_origin_ts = base
                self._ref_2k.extend(ds)
                if len(self._ref_2k) > SERVER_MAX_REF_SAMPLES_2K:
                    drop = len(self._ref_2k) - SERVER_MAX_REF_SAMPLES_2K
                    self._ref_2k = self._ref_2k[drop:]
                    self._ref_origin_ts += float(drop) / float(SERVER_REF_TARGET_SR)

    def clear_recent_utterances(self) -> None:
        self._recent_ai_utterances.clear()

    def clear_ai_playback(self) -> None:
        self._ai_playback_start_ts = 0.0
        self._ai_playback_end_ts = 0.0
        self._ref_2k = []
        self._ref_origin_ts = 0.0
        self._locked_lag_2k = None
        self._lock_hits = 0
        self._echo_gain_est = 0.0
        self._env_hist_mic = []
        self._env_hist_ref = []
        self._barge_in_accum_sec = 0.0
        self._barge_in_miss_sec = 0.0

    def is_playback_or_tail_active(self, now: float | None = None) -> bool:
        ts = time.monotonic() if now is None else float(now)
        return self._ai_playback_end_ts > 0.0 and ts < (self._ai_playback_end_ts + self.playback_tail_sec)

    def _compute_waveform_corr(self, mic_2k: list[float], now_ts: float) -> dict[str, float] | None:
        if len(self._ref_2k) < 16 or len(mic_2k) < 8:
            return None
        n = len(mic_2k)
        mic_e = sum(x * x for x in mic_2k)
        if mic_e < 1e-9:
            return {"rho": 0.0, "abs_rho": 0.0, "spec_rho": 0.0, "env_rho": 0.0, "ref_rms": 0.0}
        cur_idx = int(round((now_ts - self._ref_origin_ts) * float(SERVER_REF_TARGET_SR)))
        min_lag = -int(round(SERVER_MIN_NEG_LAG_SEC * float(SERVER_REF_TARGET_SR)))
        max_lag = int(round(SERVER_MAX_SEARCH_LAG_SEC * float(SERVER_REF_TARGET_SR)))
        best_rho = 0.0
        best_abs_rho = 0.0
        best_lag = 0
        best_st = -1
        best_ref_rms = 0.0
        evaluated = False

        def score(lag: int, min_accept_rho: float = 0.0) -> None:
            nonlocal best_rho, best_abs_rho, best_lag, best_st, best_ref_rms, evaluated
            st = cur_idx - lag
            if st < 0 or st + n > len(self._ref_2k):
                return
            evaluated = True
            ref_sl = self._ref_2k[st : st + n]
            ref_e = sum(r * r for r in ref_sl)
            if ref_e < 1e-9:
                return
            dot = sum(mic_2k[j] * ref_sl[j] for j in range(n))
            denom = math.sqrt(mic_e * ref_e)
            rho = abs(dot) / denom
            if rho > best_rho and rho >= min_accept_rho:
                best_rho = rho
                best_abs_rho = sum(abs(mic_2k[j]) * abs(ref_sl[j]) for j in range(n)) / denom
                best_lag = lag
                best_st = st
                best_ref_rms = math.sqrt(ref_e / float(n))

        if self._locked_lag_2k is not None:
            lo = max(min_lag, self._locked_lag_2k - 18)
            hi = min(max_lag, self._locked_lag_2k + 18)
            for lag in range(lo, hi + 1):
                score(lag, 0.0)
        if self._locked_lag_2k is None:
            for lag in range(min_lag, max_lag + 1, 2):
                score(lag, 0.0)
            if best_rho > 0.25:
                score(max(min_lag, best_lag - 1), 0.0)
                score(min(max_lag, best_lag + 1), 0.0)
        elif best_rho < 0.55:
            far_min_rho = 0.70 if self._lock_hits >= 3 else 0.0
            for lag in range(min_lag, max_lag + 1, 2):
                if abs(lag - self._locked_lag_2k) <= 18:
                    continue
                score(lag, far_min_rho)
            if best_rho > 0.25 and abs(best_lag - self._locked_lag_2k) > 18:
                score(max(min_lag, best_lag - 1), far_min_rho)
                score(min(max_lag, best_lag + 1), far_min_rho)

        if not evaluated:
            return None

        spec_rho = (
            _spectral_mag_corr(mic_2k, self._ref_2k[best_st : best_st + n])
            if best_st >= 0 and best_st + n <= len(self._ref_2k)
            else 0.0
        )

        if best_rho >= SERVER_ECHO_CORR_LOCK_RHO:
            if self._locked_lag_2k is None:
                self._locked_lag_2k = best_lag
            else:
                self._locked_lag_2k = int(round(self._locked_lag_2k * 0.6 + best_lag * 0.4))
            self._lock_hits = min(20, self._lock_hits + 1)

        mic_2k_rms = math.sqrt(mic_e / float(n))
        ref_env_rms = best_ref_rms
        if self._locked_lag_2k is not None:
            lst = cur_idx - self._locked_lag_2k
            if 0 <= lst and lst + n <= len(self._ref_2k):
                lref = self._ref_2k[lst : lst + n]
                lref_e = sum(r * r for r in lref)
                ref_env_rms = math.sqrt(lref_e / float(n))
                if lref_e >= 1e-9:
                    labs = sum(abs(mic_2k[j]) * abs(lref[j]) for j in range(n)) / math.sqrt(mic_e * lref_e)
                    if labs > best_abs_rho:
                        best_abs_rho = labs
                lspec = _spectral_mag_corr(mic_2k, lref)
                if lspec > spec_rho:
                    spec_rho = lspec

        self._env_hist_mic.append(mic_2k_rms)
        self._env_hist_ref.append(ref_env_rms)
        if len(self._env_hist_mic) > SERVER_ECHO_ENV_HISTORY_LEN:
            self._env_hist_mic.pop(0)
            self._env_hist_ref.pop(0)

        env_rho = 0.0
        if len(self._env_hist_mic) >= 6:
            hm = self._env_hist_mic
            hr = self._env_hist_ref
            mean_m = sum(hm) / float(len(hm))
            mean_r = sum(hr) / float(len(hr))
            var_m = sum((x - mean_m) ** 2 for x in hm)
            var_r = sum((x - mean_r) ** 2 for x in hr)
            if var_m > 1e-9 and var_r > 1e-9:
                cov = sum((hm[i] - mean_m) * (hr[i] - mean_r) for i in range(len(hm)))
                env_rho = max(0.0, cov / math.sqrt(var_m * var_r))

        return {
            "rho": min(1.0, best_rho),
            "abs_rho": min(1.0, best_abs_rho),
            "spec_rho": min(1.0, spec_rho),
            "env_rho": min(1.0, env_rho),
            "ref_rms": ref_env_rms,
        }

    def evaluate_mic_audio_chunk(
        self,
        pcm16k_bytes: bytes,
        *,
        is_barge_in_hint: bool = False,
        sample_rate: int = 16000,
        now: float | None = None,
    ) -> tuple[bool, bool, str]:
        """Server-side audio echo/barge-in gate synced with client VoiceEchoGuard.

        Returns (allow_send, barge_in_triggered, reason).
        """
        ts = time.monotonic() if now is None else float(now)
        if is_barge_in_hint:
            self.clear_ai_playback()
            return True, True, "client_barge_in"
        if not self.is_playback_or_tail_active(now=ts):
            self._barge_in_accum_sec = 0.0
            self._barge_in_miss_sec = 0.0
            return True, False, "idle"

        samples = _pcm16_bytes_to_floats(pcm16k_bytes)
        if not samples:
            return False, False, "empty_during_playback"

        sub_len = max(1, int(round(sample_rate * 0.02)))
        total_dur = float(len(samples)) / float(max(1, sample_rate))
        num_subs = max(1, len(samples) // sub_len)
        is_playing = ts < self._ai_playback_end_ts

        for k in range(num_subs):
            st = k * sub_len
            en = len(samples) if k == num_subs - 1 else (k + 1) * sub_len
            sub = samples[st:en]
            sub_dur = float(len(sub)) / float(max(1, sample_rate))
            sub_ts = ts - total_dur + float(en) / float(max(1, sample_rate))
            rms = _rms_floats(sub)
            zcr = _zcr_floats(sub)
            speech_like = 0.006 <= zcr <= 0.48

            corr = self._compute_waveform_corr(_downsample_floats_to_2k(sub, sample_rate), sub_ts)
            strong_pure_echo = False
            if corr is not None:
                rho = corr["rho"]
                abs_rho = corr["abs_rho"]
                spec_rho = corr["spec_rho"]
                env_rho = corr["env_rho"]
                ref_rms = corr["ref_rms"]
                strong_pure_echo = rho >= 0.88 and abs_rho >= 0.90

                if rho >= SERVER_ECHO_CORR_LOCK_RHO and ref_rms > 0.02 and rms > 0.01:
                    g = rms / ref_rms
                    if self._echo_gain_est <= 0.0:
                        self._echo_gain_est = min(4.0, g)
                    elif g > self._echo_gain_est:
                        self._echo_gain_est = min(4.0, self._echo_gain_est * 0.70 + g * 0.30)
                    else:
                        self._echo_gain_est = min(4.0, self._echo_gain_est * 0.85 + g * 0.15)

                expected_echo = (
                    self._echo_gain_est * ref_rms
                    if (self._locked_lag_2k is not None and self._lock_hits >= 2 and self._echo_gain_est > 0.0 and ref_rms > 0.015)
                    else 0.0
                )
                within_expected_echo = expected_echo > 0.0 and rms <= expected_echo * 1.65

                echo_matched = (
                    rho >= SERVER_ECHO_CORR_SUPPRESS_RHO
                    or (rho >= 0.54 and spec_rho >= 0.91)
                    or (rho >= 0.62 and abs_rho >= 0.83 and spec_rho >= 0.84)
                    or (within_expected_echo and rho >= 0.54 and abs_rho >= 0.78)
                    or (within_expected_echo and rho >= 0.54 and spec_rho >= 0.80 and env_rho >= 0.25)
                    or (within_expected_echo and abs_rho >= 0.82 and spec_rho >= 0.84 and env_rho >= 0.65 and rho >= 0.42)
                    or (self._locked_lag_2k is not None and self._lock_hits >= 2 and spec_rho >= 0.90 and env_rho >= 0.75 and abs_rho >= 0.82 and rho >= 0.45)
                    or (self._locked_lag_2k is not None and self._lock_hits >= 3 and spec_rho >= 0.88 and abs_rho >= 0.75 and rho >= 0.56)
                )

                eff_rho = max(rho, abs_rho * 0.86 if (within_expected_echo and rho >= 0.50 and abs_rho >= 0.78) else 0.0)
                near_rms = rms * math.sqrt(max(0.0, 1.0 - min(1.0, eff_rho) ** 2))
                in_warmup = self._ai_playback_start_ts > 0.0 and (sub_ts - self._ai_playback_start_ts) < SERVER_ECHO_WARMUP_SEC
                if self._ai_playback_start_ts > 0.0 and sub_ts < self._ai_playback_start_ts:
                    is_near = False
                elif in_warmup:
                    is_near = speech_like and (not echo_matched) and rho < 0.62 and near_rms >= max(SERVER_BARGE_IN_MIN_RMS * 2.0, SERVER_ECHO_WARMUP_NEAR_RMS)
                else:
                    adaptive_near_min = max(SERVER_BARGE_IN_MIN_RMS, min(0.085, expected_echo * 0.35))
                    is_near = speech_like and (not echo_matched) and near_rms >= adaptive_near_min and rms >= SERVER_BARGE_IN_MIN_RMS
            else:
                in_warmup_nc = self._ai_playback_start_ts > 0.0 and (sub_ts - self._ai_playback_start_ts) < SERVER_ECHO_WARMUP_SEC
                if len(self._ref_2k) >= 16 and (sub_ts < self._ai_playback_start_ts or in_warmup_nc):
                    is_near = False
                else:
                    thr = max(SERVER_BARGE_IN_MIN_RMS, self._estimated_echo_rms * SERVER_BARGE_IN_ECHO_RATIO)
                    is_near = speech_like and rms >= thr
                    if not is_near and is_playing and self._barge_in_accum_sec <= 0.0 and rms < thr * 0.85:
                        alpha = 0.12 if rms > self._estimated_echo_rms else 0.20
                        self._estimated_echo_rms = min(0.075, max(0.004, self._estimated_echo_rms * (1.0 - alpha) + rms * alpha))

            if is_near:
                self._barge_in_accum_sec += sub_dur
                self._barge_in_miss_sec = 0.0
                if self._barge_in_accum_sec >= SERVER_BARGE_IN_HOLD_SEC:
                    self.clear_ai_playback()
                    return True, True, "server_barge_in_triggered"
            else:
                if self._barge_in_accum_sec > 0.0:
                    self._barge_in_miss_sec += sub_dur
                    if strong_pure_echo and self._barge_in_miss_sec >= 0.04:
                        self._barge_in_accum_sec = max(0.0, self._barge_in_accum_sec - sub_dur)
                    if self._barge_in_miss_sec > SERVER_BARGE_IN_GAP_TOL_SEC:
                        self._barge_in_accum_sec = 0.0
                        self._barge_in_miss_sec = 0.0

        return False, False, "echo_suppressed_during_playback"

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
