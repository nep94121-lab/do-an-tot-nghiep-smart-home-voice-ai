"""Vietnamese STT dispatcher: Sherpa-ONNX Zipformer (offline primary), PhoWhisper/Whisper fallback, and Gemini STT."""

from __future__ import annotations

import logging
import math
import os
import pathlib
import re
import threading
import time
from typing import Any

import numpy as np

LOG = logging.getLogger("simulator.voice.vietnamese_stt")

_MODEL_LOCK = threading.Lock()
_CACHED_MODEL: Any = None
_CACHED_MODEL_NAME: str = ""
_LOAD_FAILED: bool = False

_PHOWHISPER_LOCK = threading.Lock()
_CACHED_PHOWHISPER: Any = None
_PHOWHISPER_FAILED: bool = False

_ZIPFORMER_LOCK = threading.Lock()
_ZIPFORMER_CACHE: dict[str, Any] = {}
_ZIPFORMER_FAILED: set[str] = set()

_ZIPFORMER_REPOS: dict[str, str] = {
    "70m": "models--csukuangfj--sherpa-onnx-zipformer-vi-int8-2025-04-20",
    "30m": "models--csukuangfj2--sherpa-onnx-zipformer-vi-30M-int8-2026-02-09",
}
_PHOWHISPER_REPO = "models--diepho--PhoWhisper-base-ct2"

# Concise domain prompt for Whisper fallback only (avoids hallucination loops on silence/noise)
_SMART_HOME_VI_PROMPT = (
    "Đèn phòng khách, đèn phòng ngủ, cửa chính, máy bơm tưới cây, còi báo động, nguồn mạch loa."
)

_HALLUCINATION_RE = re.compile(
    r"(?:"
    r"hãy\s+subscribe|subscribe\s+cho\s+kênh|đăng\s+ký\s+kênh|bấm\s+chuông|"
    r"cảm\s+ơn\s+(?:các\s+bạn\s+)?đã\s+(?:xem|theo\s+dõi)|"
    r"hẹn\s+gặp\s+lại\s+các\s+bạn|video\s+tiếp\s+theo|like\s+và\s+share|"
    r"chào\s+mừng\s+các\s+bạn\s+đến\s+với\s+kênh|theo\s+dõi\s+kênh|"
    r"người\s+dịch|phụ\s+đề\s+bởi|amara\.org|ghiền\s+mì\s+gõ"
    r")",
    re.IGNORECASE,
)

_VALID_SHORT_SINGLE_TOKENS: frozenset[str] = frozenset({
    "ok", "okay", "oke", "okie", "yes", "no", "cancel", "confirm",
    "được", "duoc", "ừ", "u", "ờ", "có", "co", "không", "khong",
    "thôi", "thoi", "hủy", "huỷ", "huy", "đúng", "dung", "đừng", "dừng",
    "vâng", "vang", "dạ", "da", "chào", "chao", "bỏ", "bo",
})


def _candidate_hf_hub_dirs() -> list[pathlib.Path]:
    candidate_hubs: list[pathlib.Path] = []
    hf_home = os.environ.get("HF_HOME", "").strip()
    if hf_home:
        candidate_hubs.append(pathlib.Path(hf_home) / "hub")
    home_dir = pathlib.Path.home()
    candidate_hubs.append(home_dir / ".cache" / "huggingface" / "hub")
    # Fallback to Windows user profile parent when running under an isolated HOME (e.g. agyhome4)
    candidate_hubs.append(home_dir.parent / ".cache" / "huggingface" / "hub")
    user_profile = os.environ.get("USERPROFILE", "").strip()
    if user_profile:
        candidate_hubs.append(pathlib.Path(user_profile) / ".cache" / "huggingface" / "hub")
    win_user = os.environ.get("USERNAME", "").strip()
    if win_user:
        candidate_hubs.append(pathlib.Path("C:/Users") / win_user / ".cache" / "huggingface" / "hub")

    unique: list[pathlib.Path] = []
    seen: set[str] = set()
    for hub in candidate_hubs:
        key = str(hub).lower()
        if key not in seen:
            seen.add(key)
            unique.append(hub)
    return unique


def _find_local_hf_snapshot(repo_folder: str, required_file: str = "model.bin") -> str | None:
    """Resolve local HuggingFace cache snapshot even when HOME is overridden."""
    for hub in _candidate_hf_hub_dirs():
        snap_root = hub / repo_folder / "snapshots"
        if not snap_root.is_dir():
            continue
        for snap in sorted(snap_root.iterdir(), reverse=True):
            if snap.is_dir() and (snap / required_file).is_file():
                return str(snap)
    return None


def _find_local_whisper_snapshot(model_size: str) -> str | None:
    """Resolve local HuggingFace cache snapshot for faster-whisper-<size> even if HOME is overridden."""
    repo_folder = f"models--Systran--faster-whisper-{model_size}"
    return _find_local_hf_snapshot(repo_folder, required_file="model.bin")


def _pick_onnx_file(snap_dir: pathlib.Path, prefix: str) -> str | None:
    int8_matches = sorted(snap_dir.glob(f"{prefix}*int8*.onnx"))
    if int8_matches:
        return str(int8_matches[0])
    plain_matches = sorted(snap_dir.glob(f"{prefix}*.onnx"))
    if plain_matches:
        return str(plain_matches[0])
    return None


def _get_zipformer_recognizer(variant: str = "70m") -> Any:
    if os.environ.get("SMARTHOME_DISABLE_LOCAL_STT", "0").strip() == "1":
        return None
    if variant in _ZIPFORMER_CACHE:
        return _ZIPFORMER_CACHE[variant]
    if variant in _ZIPFORMER_FAILED:
        return None

    with _ZIPFORMER_LOCK:
        if variant in _ZIPFORMER_CACHE:
            return _ZIPFORMER_CACHE[variant]
        if variant in _ZIPFORMER_FAILED:
            return None

        repo_folder = _ZIPFORMER_REPOS.get(variant)
        if not repo_folder:
            _ZIPFORMER_FAILED.add(variant)
            return None
        try:
            import sherpa_onnx
        except Exception as exc:
            LOG.warning("sherpa_onnx unavailable: %s", exc)
            _ZIPFORMER_FAILED.add(variant)
            return None

        snap_str = _find_local_hf_snapshot(repo_folder, required_file="tokens.txt")
        if not snap_str:
            LOG.debug("Zipformer-%s local snapshot not found (%s)", variant, repo_folder)
            _ZIPFORMER_FAILED.add(variant)
            return None

        snap_dir = pathlib.Path(snap_str)
        encoder = _pick_onnx_file(snap_dir, "encoder")
        decoder = _pick_onnx_file(snap_dir, "decoder")
        joiner = _pick_onnx_file(snap_dir, "joiner")
        tokens = str(snap_dir / "tokens.txt")
        if not (encoder and decoder and joiner):
            LOG.warning("Incomplete Zipformer-%s files in %s", variant, snap_dir)
            _ZIPFORMER_FAILED.add(variant)
            return None

        num_threads = max(1, int(os.environ.get("SMARTHOME_STT_THREADS", "8") or "8"))
        try:
            rec = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=encoder,
                decoder=decoder,
                joiner=joiner,
                tokens=tokens,
                num_threads=num_threads,
                sample_rate=16000,
                feature_dim=80,
                decoding_method="greedy_search",
                provider="cpu",
            )
            _ZIPFORMER_CACHE[variant] = rec
            LOG.info("Loaded local Vietnamese Zipformer-%s model (%s)", variant, snap_dir)
            return rec
        except Exception as exc:
            LOG.warning("Failed loading Zipformer-%s: %s", variant, exc)
            _ZIPFORMER_FAILED.add(variant)
            return None


def _get_phowhisper_model() -> Any:
    global _CACHED_PHOWHISPER, _PHOWHISPER_FAILED
    if os.environ.get("SMARTHOME_DISABLE_LOCAL_STT", "0").strip() == "1":
        return None
    if _CACHED_PHOWHISPER is not None:
        return _CACHED_PHOWHISPER
    if _PHOWHISPER_FAILED:
        return None

    with _PHOWHISPER_LOCK:
        if _CACHED_PHOWHISPER is not None:
            return _CACHED_PHOWHISPER
        if _PHOWHISPER_FAILED:
            return None
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            LOG.warning("faster_whisper unavailable for PhoWhisper: %s", exc)
            _PHOWHISPER_FAILED = True
            return None

        snap_path = _find_local_hf_snapshot(_PHOWHISPER_REPO, required_file="model.bin")
        if not snap_path:
            _PHOWHISPER_FAILED = True
            return None

        cpu_threads = max(1, int(os.environ.get("SMARTHOME_STT_THREADS", "8") or "8"))
        try:
            model = WhisperModel(
                snap_path,
                device="cpu",
                compute_type="int8",
                cpu_threads=cpu_threads,
                local_files_only=True,
            )
            _CACHED_PHOWHISPER = model
            LOG.info("Loaded local PhoWhisper-base-ct2 model (%s)", snap_path)
            return _CACHED_PHOWHISPER
        except Exception as exc:
            LOG.warning("Failed loading PhoWhisper-base-ct2: %s", exc)
            _PHOWHISPER_FAILED = True
            return None


def _get_whisper_model() -> Any:
    global _CACHED_MODEL, _CACHED_MODEL_NAME, _LOAD_FAILED
    if os.environ.get("SMARTHOME_DISABLE_LOCAL_STT", "0").strip() == "1":
        return None
    if _CACHED_MODEL is not None:
        return _CACHED_MODEL
    if _LOAD_FAILED:
        return None

    with _MODEL_LOCK:
        if _CACHED_MODEL is not None:
            return _CACHED_MODEL
        if _LOAD_FAILED:
            return None
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            LOG.warning("faster_whisper unavailable: %s", exc)
            _LOAD_FAILED = True
            return None

        preferred = os.environ.get("SMARTHOME_WHISPER_MODEL", "small").strip() or "small"
        candidates = [preferred]
        if preferred != "tiny":
            candidates.append("tiny")

        cpu_threads = max(1, int(os.environ.get("SMARTHOME_STT_THREADS", "8") or "8"))
        for size in candidates:
            snap_path = _find_local_whisper_snapshot(size)
            model_arg = snap_path or size
            try:
                model = WhisperModel(
                    model_arg,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=cpu_threads,
                    local_files_only=True,
                )
                _CACHED_MODEL = model
                _CACHED_MODEL_NAME = size
                LOG.info("Loaded local Vietnamese Whisper model: %s (%s)", size, model_arg)
                return _CACHED_MODEL
            except Exception as exc:
                LOG.debug("Failed loading faster-whisper model %s: %s", size, exc)

        _LOAD_FAILED = True
        return None


def _analyze_and_preprocess_audio(pcm16: np.ndarray, sr: int = 16000) -> tuple[np.ndarray, bool]:
    """Return (float32_16k_audio, is_noise_or_silence)."""
    if pcm16 is None or pcm16.size < int(sr * 0.15):
        return np.array([], dtype=np.float32), True

    if np.issubdtype(pcm16.dtype, np.floating):
        x = pcm16.astype(np.float64)
        if float(np.max(np.abs(x))) > 1.5:
            x = x / 32768.0
    else:
        x = pcm16.astype(np.float64) / 32768.0

    # Resample linearly if sample rate differs from 16kHz
    if sr != 16000 and sr > 0:
        target_len = max(1, int(round(x.size * 16000.0 / float(sr))))
        idx = np.linspace(0.0, float(x.size - 1), target_len)
        x = np.interp(idx, np.arange(x.size, dtype=np.float64), x)
        sr = 16000

    # DC removal
    x = x - float(np.mean(x))
    if not np.all(np.isfinite(x)):
        x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)

    rms = float(np.sqrt(np.mean(x * x)))
    peak = float(np.max(np.abs(x)))
    if rms < 0.0012 or peak < 0.004:
        return np.array([], dtype=np.float32), True

    # Frame-level energy modulation & spectral flatness check to reject flat white noise / steady tones
    frame_len = 320  # 20ms at 16kHz
    n_frames = x.size // frame_len
    if n_frames >= 8:
        frames = x[: n_frames * frame_len].reshape(n_frames, frame_len)
        frame_rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
        rms_mean = float(np.mean(frame_rms))
        rms_cv = float(np.std(frame_rms) / max(rms_mean, 1e-9))

        # Spectral flatness on FFT of active signal
        win_n = min(x.size, 16384)
        spec = np.abs(np.fft.rfft(x[:win_n] * np.hanning(win_n))) ** 2 + 1e-18
        geo_mean = float(np.exp(np.mean(np.log(spec))))
        arith_mean = float(np.mean(spec))
        flatness = geo_mean / max(arith_mean, 1e-18)

        # Stationary broadband white noise: high spectral flatness AND low temporal modulation
        if flatness > 0.55 and rms_cv < 0.18:
            return np.array([], dtype=np.float32), True

        # Pure steady synthetic sine tone: >92% of energy in top 3 bins AND flat envelope
        top3_ratio = float(np.sum(np.sort(spec)[-3:]) / max(float(np.sum(spec)), 1e-18))
        if top3_ratio > 0.92 and rms_cv < 0.15:
            return np.array([], dtype=np.float32), True

    # Simple first-order high-pass filter (~78 Hz at 16kHz) to strip DC/hum rumble
    if x.size > 2:
        alpha = 0.97
        try:
            from scipy.signal import lfilter

            x = lfilter([1.0, -1.0], [1.0, -alpha], x)
        except Exception:
            pass

    # Soft de-clipping when input is heavily clipped
    clipped_ratio = float(np.mean(np.abs(x) >= 0.985))
    if clipped_ratio > 0.01:
        x = np.tanh(x * 0.92) / math.tanh(0.92)

    # Gentle gain normalization for low-volume speech (boost up to peak 0.75, max gain 20x)
    new_peak = float(np.max(np.abs(x)))
    if 0.004 <= new_peak < 0.55:
        gain = min(20.0, 0.75 / new_peak)
        x = np.clip(x * gain, -0.98, 0.98)

    return x.astype(np.float32), False


def _is_muffled_babble_only(audio_f32: np.ndarray, sr: int = 16000) -> bool:
    """Detect continuous, heavily lowpassed, low-modulation room babble (no clear foreground speech)."""
    if audio_f32.size < int(sr * 1.4):
        return False
    frame_len = 320
    n_frames = audio_f32.size // frame_len
    if n_frames < 40:
        return False
    frames = audio_f32[: n_frames * frame_len].reshape(n_frames, frame_len)
    frame_rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    p20 = float(np.percentile(frame_rms, 20))
    p80 = float(np.percentile(frame_rms, 80))
    rms_mean = float(np.mean(frame_rms))
    rms_cv = float(np.std(frame_rms) / max(rms_mean, 1e-9))

    # Real speech has syllable pauses / dynamic modulation; dense reversed babble has a steady energy floor
    if p80 <= 1e-6 or (p20 / p80) < 0.36 or rms_cv > 0.45:
        return False

    # Check high-frequency energy (>2200 Hz) across the clip
    win_n = min(audio_f32.size, 32768)
    freqs = np.fft.rfftfreq(win_n, d=1.0 / float(sr))
    spec = np.abs(np.fft.rfft(audio_f32[:win_n] * np.hanning(win_n))) ** 2
    total_pow = float(np.sum(spec)) + 1e-18
    hf_ratio = float(np.sum(spec[freqs >= 2200.0]) / total_pow)
    return hf_ratio < 0.004


def _clean_whisper_text(raw_text: str) -> str:
    txt = re.sub(r"\s+", " ", str(raw_text or "")).strip()
    if not txt:
        return ""
    if _HALLUCINATION_RE.search(txt):
        cleaned = _HALLUCINATION_RE.sub("", txt)
        cleaned = re.sub(r"^[\s.,!?;:\-]+|[\s.,!?;:\-]+$", "", cleaned).strip()
        txt = cleaned
    if len(txt) <= 1 and not txt.isalnum():
        return ""
    return txt


def _clean_zipformer_text(raw_text: str) -> str:
    txt = _clean_whisper_text(raw_text)
    if not txt:
        return ""
    # Zipformer Vietnamese BPE models output ALL CAPS; normalize cleanly to lowercase.
    return txt.lower().strip()


def _decode_zipformer_with_gap(
    rec: Any,
    audio_f32: np.ndarray,
    sr: int = 16000,
    *,
    pad_sec: float = 0.25,
) -> tuple[str, float]:
    """Decode with Zipformer using universal silence padding and compute pre-token acoustic onset gap."""
    samples = audio_f32
    if pad_sec > 0.0:
        pad = np.zeros(int(sr * pad_sec), dtype=np.float32)
        samples = np.concatenate([pad, samples, pad])
    stream = rec.create_stream()
    stream.accept_waveform(sr, samples.tolist() if samples.dtype != np.float32 else samples)
    rec.decode_stream(stream)
    txt = _clean_zipformer_text(getattr(stream.result, "text", ""))
    tok_ts = list(getattr(stream.result, "timestamps", []) or [])
    if not tok_ts:
        return txt, 0.0
    frame_len = max(1, int(sr * 0.02))
    n_frames = samples.size // frame_len
    if n_frames < 4:
        return txt, 0.0
    frames = samples[: n_frames * frame_len].reshape(n_frames, frame_len)
    frame_rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    peak_rms = float(np.max(frame_rms))
    speech_idx = np.where(frame_rms > peak_rms * 0.12)[0]
    onset_s = float(speech_idx[0] * 0.02) if speech_idx.size else 0.0
    first_tok_s = float(tok_ts[0])
    return txt, (first_tok_s - onset_s)


def _decode_zipformer(rec: Any, audio_f32: np.ndarray, sr: int = 16000, *, pad_short: bool = True) -> str:
    txt, _gap = _decode_zipformer_with_gap(rec, audio_f32, sr=sr, pad_sec=(0.25 if pad_short else 0.0))
    return txt


def _classify_offline_transcript_kind(text: str) -> tuple[str, str | None]:
    """Classify an offline transcript to decide whether ensemble rescue is needed.

    Returns (kind, device_id_if_bare_noun) where kind is one of:
    'empty' | 'unsupported' | 'foreign' | 'recognized' | 'bare_device' | 'bare_verb' | 'unrecognized'.
    """
    low = re.sub(r"[?!.,;:]+$", "", (text or "").strip().lower()).strip()
    if not low:
        return "empty", None
    try:
        from simulator.automation_nlu import (
            _classify_confirmation_utterance,
            _detect_scoped_reset_intent,
            _parse_clock_hhmm_vi,
            _parse_countdown_seconds,
            _parse_custom_command_create_or_edit,
            _parse_sensor_trigger,
        )
        from simulator.voice.vietnamese_policy import (
            _UNSUPPORTED_DEVICE_RE,
            _extract_clause_action,
            _extract_clause_device,
            classify_small_talk_vi,
            is_foreign_or_nonsense_input,
            normalize_vietnamese_utterance,
            parse_direct_device_intents_vi,
            strip_vi_accents,
        )
    except Exception:
        return "recognized", None

    is_bad, bad_kind = is_foreign_or_nonsense_input(low)
    if is_bad and bad_kind == "foreign":
        return "foreign", None
    if is_bad and bad_kind == "nonsense":
        return "nonsense", None

    norm_raw = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(low)).split())
    padded_raw = f" {norm_raw} "
    if _UNSUPPORTED_DEVICE_RE.search(padded_raw):
        return "unsupported", None

    tokens = low.split()
    if len(tokens) == 1 and tokens[0] in _VALID_SHORT_SINGLE_TOKENS:
        return "recognized", None
    if _classify_confirmation_utterance(low, has_pending=False) is not None:
        return "recognized", None
    if classify_small_talk_vi(low) is not None:
        return "recognized", None
    if parse_direct_device_intents_vi(low):
        return "recognized", None

    # Sensor/status queries
    if any(
        k in padded_raw
        for k in (
            " nhiet do ", " do am ", " cam bien ", " am thanh ", " ky037 ", " ky 037 ",
            " bom tu dong ", " che do bom ", " dang mo hay dong ",
            " dang bat hay tat ", " co dang bat ", " co dang mo ", " co dang keu ",
            " co nhung ", " danh sach ", " liet ke ", " thanh vien ",
        )
    ):
        if not re.match(r"^(?:rep|rex|rexit|vi\s+sep|viet|re\s+logic|logic|reet)\b", norm_raw):
            return "recognized", None
    if " trang thai " in padded_raw and not re.match(
        r"^(?:rep|rex|rexit|vi\s+sep|viet|re\s+logic|logic|reet|reset|ri\s+set|dat\s+lai|tuyet|vi\s+thich)\b",
        norm_raw,
    ):
        if any(
            k in padded_raw
            for k in (
                " thiet bi ", " trong nha ", " cua ", " den ", " bom ", " coi ", " loa ",
                " cam bien ", " dang ", " nao ", " the nao ",
            )
        ):
            return "recognized", None

    # Automation: reset, custom create/edit/delete, schedule, timer, cross-rule
    if _detect_scoped_reset_intent(low) is not None:
        return "recognized", None
    if any(
        k in padded_raw
        for k in (
            " reset trang thai ", " ri set trang thai ", " rexit trang thai ",
            " rep trang thai ", " vi sep trang thai ", " viet trang thai ",
            " re logic trang thai ", " logic trang thai ", " reet trang thai ",
            " dat lai trang thai ", " khoi phuc cai dat ",
            " hoi phuc cai dat ", " khoi phuc ngay dan ",
            " factory reset ", " cap quyen ", " thu hoi ",
        )
    ):
        return "recognized", None
    if _parse_custom_command_create_or_edit(low) is not None:
        return "recognized", None
    if re.match(r"^(?:huy|xoa)\s+(?:hen gio|lich|luat|lien ket|lien het|lien thiep|lenh|scene|kich ban)\b", norm_raw):
        return "recognized", None
    if re.match(r"^(?:doi|sua|cap nhat|du)\s+(?:lich|hen gio)\b", norm_raw):
        return "recognized", None
    if re.match(r"^(?:xu ly|du dinh)\s+.+\s+(?:thanh|sang)\s+.+", norm_raw):
        return "recognized", None
    if " thi " in padded_raw and (
        _parse_sensor_trigger(low) is not None
        or any(k in padded_raw for k in (" khi ", " neu ", " mo cua ", " dong cua ", " bat ", " tat "))
    ):
        from simulator.automation_nlu import parse_single_device_and_action

        parts_thi = re.split(r"\b(?:thì|thi)\b", low, maxsplit=1, flags=re.IGNORECASE)
        if len(parts_thi) == 2:
            t_dev, t_act = parse_single_device_and_action(parts_thi[1].strip())
            if t_dev is not None and t_act is not None:
                return "recognized", None
    hhmm, _, _ = _parse_clock_hhmm_vi(low)
    if hhmm is not None and any(k in padded_raw for k in (" mo ", " dong ", " bat ", " tat ")):
        return "recognized", None
    cd_sec, _ = _parse_countdown_seconds(low)
    if cd_sec > 0 and any(k in padded_raw for k in (" sau ", " nua ", " hen gio ")) and any(
        k in padded_raw for k in (" mo ", " dong ", " bat ", " tat ")
    ):
        return "recognized", None

    # Check bare device noun vs bare verb (for onset-gap physics guard!)
    # Strictly require NO extra unrecognized leading/trailing word (e.g. 'các còi báo động' or 'bật kết quả' is NOT bare).
    normalized = normalize_vietnamese_utterance(low)
    norm_clean = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(normalized.lower())).split())
    norm_stripped = re.sub(r"\s+(?:a|nha|nhe|oi|di|nay|voi|giup minh|ho minh)$", "", norm_clean).strip()
    dev = _extract_clause_device(norm_clean) if norm_clean else None
    act = _extract_clause_action(norm_clean, dev) if norm_clean else None
    _EXACT_BARE_DEVICE_PHRASES = {
        "cua", "cua chinh", "cong", "cua ra vao", "cua nha", "cai cua",
        "den", "bong den", "tat ca den", "het den", "toan bo den", "ca hai den", "hai den", "ca den", "may cai den",
        "den phong khach", "bong den phong khach", "den khach", "phong khach",
        "den phong ngu", "bong den phong ngu", "den ngu", "phong ngu",
        "may bom", "may bom tuoi cay", "bom", "bom tuoi cay", "bom vuon", "may bom nuoc", "bom nuoc",
        "coi", "coi bao dong", "chuong bao dong", "bao dong",
        "loa", "mach loa", "nguon mach loa", "nguon loa", "am li", "amply",
        "tat ca thiet bi", "cac thiet bi", "thiet bi",
    }
    _EXACT_BARE_VERB_PHRASES = {
        "bat", "tat", "mo", "dong", "khoa",
        "bat len", "tat xuong", "mo ra", "dong lai", "khoa lai",
        "bat len di", "mo ra di", "dong lai di",
        "bat het len", "tat het di", "bat no len", "tat no di",
    }
    if dev is not None and act is None and norm_stripped in _EXACT_BARE_DEVICE_PHRASES:
        return "bare_device", dev
    if act is not None and dev is None and norm_stripped in _EXACT_BARE_VERB_PHRASES:
        return "bare_verb", None

    return "unrecognized", None


def _is_plausible_short_reply_or_command(text: str) -> bool:
    kind, _ = _classify_offline_transcript_kind(text)
    return kind == "recognized"


def _transcribe_with_whisper_model(
    model: Any,
    audio_f32: np.ndarray,
    *,
    is_phowhisper: bool,
) -> tuple[str, float]:
    kwargs: dict[str, Any] = {
        "language": "vi",
        "task": "transcribe",
        "beam_size": 1,
        "best_of": 1,
        "temperature": 0.0,
        "max_new_tokens": 48,
        "without_timestamps": True,
        "vad_filter": False if is_phowhisper else True,
        "condition_on_previous_text": False,
        "no_speech_threshold": 0.65,
    }
    if not is_phowhisper:
        kwargs["initial_prompt"] = _SMART_HOME_VI_PROMPT

    segments, _info = model.transcribe(audio_f32, **kwargs)
    kept_texts: list[str] = []
    confidences: list[float] = []
    for seg in segments:
        no_speech_prob = float(getattr(seg, "no_speech_prob", 0.0) or 0.0)
        avg_logprob = float(getattr(seg, "avg_logprob", 0.0) or 0.0)
        if no_speech_prob > 0.78 or avg_logprob < -1.35:
            continue
        seg_txt = _clean_whisper_text(getattr(seg, "text", ""))
        if not seg_txt:
            continue
        kept_texts.append(seg_txt)
        conf = max(0.0, min(1.0, math.exp(max(-5.0, avg_logprob)) * (1.0 - no_speech_prob)))
        confidences.append(conf)

    final_text = _clean_whisper_text(" ".join(kept_texts))
    avg_conf = round(float(sum(confidences) / max(1, len(confidences))), 4) if final_text else 0.0
    return final_text, avg_conf


def transcribe_short_zipformer30m_pcm16k(
    pcm16: np.ndarray,
    sr: int = 16000,
) -> dict[str, Any]:
    """Fast (~280ms) local Vietnamese Zipformer-30M-int8 transcription for short clips."""
    t0 = time.perf_counter()
    audio_f32, is_noise = _analyze_and_preprocess_audio(pcm16, sr=sr)
    if is_noise or audio_f32.size == 0:
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": True,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": "acoustic_gate",
        }
    rec30 = _get_zipformer_recognizer("30m")
    if rec30 is None:
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": False,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": "zipformer_30m_unavailable",
        }
    try:
        txt = _decode_zipformer(rec30, audio_f32, sr=16000, pad_short=True)
        elapsed = round((time.perf_counter() - t0) * 1000.0, 1)
        if not txt:
            return {
                "ok": False,
                "text": "",
                "confidence": 0.0,
                "is_noise": True,
                "stt_ms": elapsed,
                "stt_engine": "zipformer_30m",
            }
        return {
            "ok": True,
            "text": txt,
            "confidence": 0.85,
            "is_noise": False,
            "stt_ms": elapsed,
            "stt_engine": "zipformer_30m",
        }
    except Exception as exc:
        LOG.warning("Zipformer-30M decode failed: %s", exc)
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": False,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": "zipformer_30m_error",
        }


def transcribe_vietnamese_offline_pcm16k(
    pcm16: np.ndarray,
    sr: int = 16000,
) -> dict[str, Any]:
    """Transcribe 16kHz mono PCM16 Vietnamese speech locally (Zipformer-70M/30M -> PhoWhisper -> Whisper)."""
    t0 = time.perf_counter()
    audio_f32, is_noise = _analyze_and_preprocess_audio(pcm16, sr=sr)
    if is_noise or audio_f32.size == 0:
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": True,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": "acoustic_gate",
        }

    if os.environ.get("SMARTHOME_DISABLE_LOCAL_STT", "0").strip() == "1":
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": False,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": "disabled",
        }

    duration_sec = float(audio_f32.size) / 16000.0
    muffled_babble = _is_muffled_babble_only(audio_f32, sr=16000)
    engine_pref = os.environ.get("SMARTHOME_OFFLINE_STT_ENGINE", "").strip().lower()

    # Engine 1 (primary offline): Sherpa-ONNX Zipformer-70M/30M + ChunkFormer-CTC acoustic rescue
    if engine_pref != "whisper":
        primary_variant = "30m" if duration_sec < 1.20 else "70m"
        alt_variant = "70m" if primary_variant == "30m" else "30m"
        rec_primary = _get_zipformer_recognizer(primary_variant)
        if rec_primary is not None:
            try:
                # Pad only very short clips (< 1.25s); leading silence pad on >= 1.25s clips causes
                # Zipformer-70M to hallucinate a leading 'bật' on bare nouns like 'tất cả đèn'.
                zip_pad = 0.25 if duration_sec < 1.25 else 0.0
                txt, onset_gap = _decode_zipformer_with_gap(rec_primary, audio_f32, sr=16000, pad_sec=zip_pad)
                variant = primary_variant
                if not txt and muffled_babble:
                    return {
                        "ok": False,
                        "text": "",
                        "confidence": 0.0,
                        "is_noise": True,
                        "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                        "stt_engine": f"zipformer_{variant}:babble_guard",
                    }

                tokens = txt.split() if txt else []
                # Reject random 1-3 nonsense syllables produced on pure muffled babble
                if txt and muffled_babble and len(tokens) <= 3 and not _is_plausible_short_reply_or_command(txt):
                    return {
                        "ok": False,
                        "text": "",
                        "confidence": 0.0,
                        "is_noise": True,
                        "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                        "stt_engine": f"zipformer_{variant}:babble_guard",
                    }

                # Preserve trailing unsupported-noun tail rescue (e.g. 'mở cửa cuốn' truncated to 'mở cửa')
                if (
                    variant == "70m"
                    and duration_sec >= 1.50
                    and len(tokens) == 2
                    and not muffled_babble
                ):
                    rec_alt = _get_zipformer_recognizer("30m")
                    if rec_alt is not None:
                        alt_txt, _ = _decode_zipformer_with_gap(rec_alt, audio_f32, sr=16000, pad_sec=zip_pad)
                        alt_tokens = alt_txt.split()
                        if len(alt_tokens) >= 3 and (
                            alt_txt.startswith(txt + " ")
                            or alt_tokens[:2] == tokens[:2]
                        ):
                            txt = alt_txt
                            variant = "30m_tail_rescue"

                kind, bare_dev = _classify_offline_transcript_kind(txt)

                # Long multi-device utterances (>= 3.5s with ' và '): if Zipformer garbled a trailing clause
                # after ' và ', check ChunkFormer-CTC and prefer it if it recovers strictly more device intents.
                if (
                    kind == "recognized"
                    and duration_sec >= 3.50
                    and not muffled_babble
                    and " và " in txt.lower()
                ):
                    try:
                        from simulator.voice.vietnamese_policy import parse_direct_device_intents_vi

                        base_intents = parse_direct_device_intents_vi(txt)
                        tail_part = txt.lower().rsplit(" và ", 1)[-1].strip()
                        if base_intents and tail_part and not parse_direct_device_intents_vi(tail_part):
                            from simulator.voice.chunkformer_ctc import decode_chunkformer_with_logprobs

                            cf_multi, _ = decode_chunkformer_with_logprobs(audio_f32, sr=16000, pad_s=0.25)
                            cf_multi_kind, _ = _classify_offline_transcript_kind(cf_multi)
                            if (
                                cf_multi_kind == "recognized"
                                and len(parse_direct_device_intents_vi(cf_multi)) > len(base_intents)
                            ):
                                return {
                                    "ok": True,
                                    "text": cf_multi,
                                    "confidence": 0.90,
                                    "is_noise": False,
                                    "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                                    "stt_engine": f"zipformer_{variant}+chunkformer_ctc_multi",
                                }
                    except Exception:
                        pass

                # Fast path (~0.8-1.2s): return immediately on recognized intents, unsupported devices,
                # foreign speech, bare verbs, or bare nouns with NO un-decoded leading speech (onset_gap < 0.08s).
                if kind in ("recognized", "unsupported", "foreign", "bare_verb"):
                    return {
                        "ok": True,
                        "text": txt,
                        "confidence": 0.88 if variant == "70m" else 0.85,
                        "is_noise": False,
                        "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                        "stt_engine": f"zipformer_{variant}",
                    }
                if kind == "bare_device" and onset_gap < 0.08:
                    return {
                        "ok": True,
                        "text": txt,
                        "confidence": 0.86,
                        "is_noise": False,
                        "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                        "stt_engine": f"zipformer_{variant}:bare_verified",
                    }

                # Pass 2 (~0.42s): ChunkFormer-CTC rescue for unrecognized utterances or dropped-verb commands (onset_gap >= 0.08s)
                cf_greedy = ""
                if not muffled_babble:
                    try:
                        from simulator.voice.chunkformer_ctc import (
                            decode_chunkformer_with_logprobs,
                            estimate_pitch_f0_hz,
                            rescore_closed_command_ctc,
                            vtln_resample,
                        )

                        cf_greedy, cf_lp = decode_chunkformer_with_logprobs(audio_f32, sr=16000, pad_s=0.25)
                        cf_kind, _ = _classify_offline_transcript_kind(cf_greedy)
                        if cf_kind in ("unsupported", "foreign"):
                            return {
                                "ok": True,
                                "text": cf_greedy,
                                "confidence": 0.88,
                                "is_noise": False,
                                "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                                "stt_engine": f"zipformer_{variant}+chunkformer_ctc",
                            }
                        if cf_kind == "recognized":
                            return {
                                "ok": True,
                                "text": cf_greedy,
                                "confidence": 0.90,
                                "is_noise": False,
                                "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                                "stt_engine": f"zipformer_{variant}+chunkformer_ctc",
                            }
                        # Constrained CTC acoustic rescoring
                        expected_dev = bare_dev if (kind == "bare_device" and onset_gap >= 0.08) else None
                        rescored = rescore_closed_command_ctc(
                            cf_lp,
                            cf_greedy,
                            expected_device=expected_dev,
                        )
                        if rescored:
                            return {
                                "ok": True,
                                "text": rescored,
                                "confidence": 0.87,
                                "is_noise": False,
                                "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                                "stt_engine": (
                                    f"zipformer_{variant}+chunkformer_ctc_onset"
                                    if expected_dev
                                    else f"zipformer_{variant}+chunkformer_ctc_rescore"
                                ),
                            }
                        # High-pitch fast speaker VTLN rescue (e.g. children F0 >= 245 Hz, dur <= 1.5s)
                        if expected_dev is None and duration_sec <= 1.50 and estimate_pitch_f0_hz(audio_f32, sr=16000) >= 245.0:
                            vtln_audio = vtln_resample(audio_f32, factor=0.75)
                            vg, vlp = decode_chunkformer_with_logprobs(vtln_audio, sr=16000, pad_s=0.25)
                            v_kind, _ = _classify_offline_transcript_kind(vg)
                            if v_kind in ("unsupported", "foreign", "recognized"):
                                return {
                                    "ok": True,
                                    "text": vg,
                                    "confidence": 0.87,
                                    "is_noise": False,
                                    "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                                    "stt_engine": f"zipformer_{variant}+chunkformer_ctc_vtln",
                                }
                            v_rescored = rescore_closed_command_ctc(vlp, vg)
                            if v_rescored:
                                return {
                                    "ok": True,
                                    "text": v_rescored,
                                    "confidence": 0.86,
                                    "is_noise": False,
                                    "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                                    "stt_engine": f"zipformer_{variant}+chunkformer_ctc_vtln_rescore",
                                }
                    except Exception as exc:
                        LOG.debug("ChunkFormer-CTC rescue skipped: %s", exc)

                # Pass 3 (~0.45s): Alternate Zipformer tie-breaker (e.g. 30M catches elderly/fast clauses 70M missed)
                if not muffled_babble:
                    rec_alt = _get_zipformer_recognizer(alt_variant)
                    if rec_alt is not None:
                        alt_txt, _ = _decode_zipformer_with_gap(rec_alt, audio_f32, sr=16000, pad_sec=zip_pad)
                        alt_kind, _ = _classify_offline_transcript_kind(alt_txt)
                        if alt_kind in ("unsupported", "foreign", "recognized"):
                            return {
                                "ok": True,
                                "text": alt_txt,
                                "confidence": 0.85,
                                "is_noise": False,
                                "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                                "stt_engine": f"zipformer_{alt_variant}_rescue",
                            }

                # Preserve bare device noun for clean clarification; otherwise prefer ChunkFormer (e.g. custom scene phrases like 'đi làm')
                final_txt = txt if kind == "bare_device" else (cf_greedy or txt)
                if final_txt:
                    return {
                        "ok": True,
                        "text": final_txt,
                        "confidence": 0.82,
                        "is_noise": False,
                        "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                        "stt_engine": f"zipformer_{variant}+chunkformer_ctc_fallback" if (final_txt == cf_greedy and cf_greedy) else f"zipformer_{variant}",
                    }
            except Exception as exc:
                LOG.warning("Local Zipformer-%s STT failed: %s", primary_variant, exc)

    # Engine 2 (secondary fallback): PhoWhisper-base-ct2 -> faster-whisper-small/tiny
    if muffled_babble:
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": True,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": "babble_guard",
        }

    pho = _get_phowhisper_model()
    if pho is not None:
        try:
            final_text, avg_conf = _transcribe_with_whisper_model(pho, audio_f32, is_phowhisper=True)
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            if final_text:
                return {
                    "ok": True,
                    "text": final_text,
                    "confidence": avg_conf,
                    "is_noise": False,
                    "stt_ms": elapsed_ms,
                    "stt_engine": "phowhisper_base",
                }
        except Exception as exc:
            LOG.warning("Local PhoWhisper STT failed: %s", exc)

    model = _get_whisper_model()
    if model is None:
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": False,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": "unavailable",
        }

    try:
        final_text, avg_conf = _transcribe_with_whisper_model(model, audio_f32, is_phowhisper=False)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        if not final_text:
            return {
                "ok": False,
                "text": "",
                "confidence": 0.0,
                "is_noise": True,
                "stt_ms": elapsed_ms,
                "stt_engine": f"whisper_{_CACHED_MODEL_NAME or 'small'}",
            }
        return {
            "ok": True,
            "text": final_text,
            "confidence": avg_conf,
            "is_noise": False,
            "stt_ms": elapsed_ms,
            "stt_engine": f"whisper_{_CACHED_MODEL_NAME or 'small'}",
        }
    except Exception as exc:
        LOG.warning("Local Vietnamese Whisper STT failed: %s", exc)
        return {
            "ok": False,
            "text": "",
            "confidence": 0.0,
            "is_noise": False,
            "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "stt_engine": "whisper_error",
        }


def transcribe_vietnamese_pcm16k(
    pcm16: np.ndarray,
    sr: int = 16000,
) -> dict[str, Any]:
    """Backward-compatible offline local Vietnamese STT entry point."""
    return transcribe_vietnamese_offline_pcm16k(pcm16, sr=sr)


def transcribe_vietnamese_audio(
    pcm16: np.ndarray,
    sr: int = 16000,
    *,
    stt_mode: str = "auto",
    has_pending_confirmation: bool = False,
) -> dict[str, Any]:
    """Unified STT entry point dispatching between Gemini STT (online) and offline Zipformer+PhoWhisper."""
    mode = (stt_mode or "auto").strip().lower()
    offline_sandbox = os.environ.get("SIMULATOR_OFFLINE_SANDBOX", "").strip() == "1"

    if mode == "offline" or offline_sandbox:
        return transcribe_vietnamese_offline_pcm16k(pcm16, sr=sr)

    has_key = False
    try:
        from simulator.api.deps import load_key

        has_key = bool(load_key())
    except Exception:
        has_key = bool(os.environ.get("GEMINI_API_KEY", "").strip())

    if mode in ("gemini", "cascade") or (mode == "auto" and has_key):
        from simulator.voice.gemini_stt import (
            transcribe_vietnamese_cascade_pcm16k,
            transcribe_vietnamese_gemini_pcm16k,
        )

        # Production quota-aware cascade (offline-first, escalate to Gemini only on low-confidence/unrecognized/noisy)
        if os.environ.get("SMARTHOME_GEMINI_DIRECT_ONLY", "0").strip() == "1":
            return transcribe_vietnamese_gemini_pcm16k(
                pcm16,
                sr=sr,
                has_pending_confirmation=has_pending_confirmation,
            )
        return transcribe_vietnamese_cascade_pcm16k(
            pcm16,
            sr=sr,
            has_pending_confirmation=has_pending_confirmation,
        )

    return transcribe_vietnamese_offline_pcm16k(pcm16, sr=sr)
