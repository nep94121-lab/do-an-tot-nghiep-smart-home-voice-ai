"""Vietnamese STT dispatcher: Sherpa-ONNX Zipformer (offline primary), PhoWhisper/Whisper fallback, and Gemini STT."""

from __future__ import annotations

import logging
import math
import os
import pathlib
import re
import tempfile
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
_ZIPFORMER_HW_CACHE: dict[str, Any] = {}
_ZIPFORMER_HW_FAILED: set[str] = set()

_CANONICAL_SENSOR_LABELS_VI: tuple[str, ...] = (
    "nhiệt độ",
    "độ ẩm không khí",
    "độ ẩm đất",
    "cảm biến âm thanh",
)

# Concise natural spoken synonyms per canonical device ID, paired with DEVICE_LABELS_VI
_DEVICE_SPOKEN_ALIASES_VI: dict[str, tuple[str, ...]] = {
    "main_door": ("cửa chính", "cửa", "cổng"),
    "living_room_light": ("đèn phòng khách", "đèn khách"),
    "bedroom_light": ("đèn phòng ngủ", "đèn ngủ", "đèn buồng"),
    "garden_pump": ("máy bơm tưới cây", "máy bơm", "bơm", "bơm vườn", "máy bơm nước", "bơm nước"),
    "alarm_siren": ("còi báo động", "còi", "còi hú", "chuông báo động"),
    "speaker_amp": ("nguồn mạch loa", "loa", "mạch loa", "nguồn loa"),
}

_DEVICE_ACTION_VERBS_VI: dict[str, tuple[tuple[str, str], ...]] = {
    "main_door": (("open", "mở"), ("close", "đóng"), ("close", "khóa"), ("close", "khép")),
    "_default": (("turn_on", "bật"), ("turn_off", "tắt")),
}


def _strip_hardware_code_from_label(label: str) -> str:
    """Strip hardware model codes (e.g. 'PAM8403') from a display label for spoken ASR vocabulary."""
    cleaned = re.sub(r"\b[A-Z]{2,}\d+[A-Z0-9]*\b", "", str(label or "")).strip()
    return " ".join(cleaned.lower().split())


def get_registry_asr_vocabulary() -> dict[str, Any]:
    """Derive canonical ASR device, action, and sensor vocabularies from the hardware permission registry."""
    try:
        from simulator.auth.tier_permissions import DEVICE_LABELS_VI

        device_labels = dict(DEVICE_LABELS_VI)
    except Exception:
        device_labels = {
            "main_door": "Cửa chính",
            "living_room_light": "Đèn phòng khách",
            "bedroom_light": "Đèn phòng ngủ",
            "garden_pump": "Máy bơm tưới cây",
            "alarm_siren": "Còi báo động",
            "speaker_amp": "Nguồn mạch loa PAM8403",
        }

    spoken_labels: dict[str, str] = {}
    device_aliases: dict[str, tuple[str, ...]] = {}
    action_verbs: dict[str, tuple[tuple[str, str], ...]] = {}

    for dev_id, raw_label in device_labels.items():
        spoken = _strip_hardware_code_from_label(raw_label) or dev_id.replace("_", " ")
        spoken_labels[dev_id] = spoken
        merged: list[str] = [spoken]
        for alias in _DEVICE_SPOKEN_ALIASES_VI.get(dev_id, ()):
            a_low = " ".join(alias.lower().split())
            if a_low and a_low not in merged:
                merged.append(a_low)
        device_aliases[dev_id] = tuple(merged)
        action_verbs[dev_id] = _DEVICE_ACTION_VERBS_VI.get(dev_id, _DEVICE_ACTION_VERBS_VI["_default"])

    return {
        "device_labels": device_labels,
        "spoken_labels": spoken_labels,
        "device_aliases": device_aliases,
        "sensor_labels": _CANONICAL_SENSOR_LABELS_VI,
        "action_verbs": action_verbs,
    }


def _build_registry_hotwords() -> tuple[tuple[str, float], ...]:
    """Build Zipformer BPE hotwords dynamically from the canonical 6-device / 3-sensor registry."""
    vocab = get_registry_asr_vocabulary()
    hotwords: list[tuple[str, float]] = []
    seen: set[str] = set()

    def _add(phrase: str, weight: float) -> None:
        key = " ".join(phrase.upper().split())
        if key and key not in seen:
            seen.add(key)
            hotwords.append((key, weight))

    light_count = 0
    for dev_id, spoken in vocab["spoken_labels"].items():
        if "light" in dev_id:
            light_count += 1
        primary_verbs = tuple(v for _a, v in vocab["action_verbs"][dev_id][:2])
        aliases = vocab["device_aliases"][dev_id]
        # Canonical full spoken label + primary short aliases
        for idx, alias in enumerate(aliases[:3]):
            if alias in ("cửa", "cổng"):
                continue
            w = 2.0 if len(alias.split()) <= 2 else 1.8
            for verb in primary_verbs:
                _add(f"{verb} {alias}", w)
            if idx == 0 and len(alias.split()) >= 3:
                _add(alias, 1.8)
        if dev_id == "garden_pump":
            _add("bơm vườn", 2.0)

    if light_count >= 2:
        _add("bật tất cả đèn", 1.8)
        _add("tắt tất cả đèn", 1.8)

    for sensor in vocab["sensor_labels"]:
        _add(sensor, 1.8)
    for phrase, weight in (
        ("đất khô", 1.8),
        ("tiếng động lớn", 1.8),
        ("hẹn giờ", 1.8),
        ("hủy hẹn giờ", 2.0),
        ("đặt lịch", 1.8),
        ("tạo lệnh", 1.8),
        ("sửa lệnh", 1.8),
        ("xóa lệnh", 1.8),
        ("reset trạng thái thiết bị", 2.0),
        ("reset liên kết", 1.9),
        ("khôi phục cài đặt gốc", 2.0),
    ):
        _add(phrase, weight)

    return tuple(hotwords)


def _build_registry_whisper_prompt() -> str:
    vocab = get_registry_asr_vocabulary()
    labels = list(vocab["spoken_labels"].values())
    if not labels:
        return "Nhà thông minh."
    formatted = [labels[0].capitalize()] + labels[1:]
    return ", ".join(formatted) + "."


# Registry-derived Vietnamese smart-home domain hotwords (pre-tokenized to BPE tokens from tokens.txt)
_SMART_HOME_HOTWORDS: tuple[tuple[str, float], ...] = _build_registry_hotwords()

_ENHANCER_LOCK = threading.Lock()
_ENHANCER_MODEL: Any = None
_ENHANCER_NAME: str = ""
_ENHANCER_FAILED: bool = False

_WARM_LOCK = threading.Lock()
_STT_WARM_STATE: dict[str, Any] = {
    "ready": False,
    "cold_start_ms": 0.0,
    "models": [],
}

_ZIPFORMER_REPOS: dict[str, str] = {
    "70m": "models--csukuangfj--sherpa-onnx-zipformer-vi-int8-2025-04-20",
    "30m": "models--csukuangfj2--sherpa-onnx-zipformer-vi-30M-int8-2026-02-09",
}
_PHOWHISPER_REPO = "models--diepho--PhoWhisper-base-ct2"

# Concise registry-derived domain prompt for Whisper fallback only (avoids hallucination loops on silence/noise)
_SMART_HOME_VI_PROMPT = _build_registry_whisper_prompt()

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

        # 1 thread per Sherpa-ONNX Zipformer instance is fastest (~150-210ms) and avoids OpenMP spin-wait
        # contention with PyTorch ChunkFormer-CTC (which otherwise slows ChunkFormer by ~7-9x).
        num_threads = max(1, int(os.environ.get("SMARTHOME_ZIPFORMER_THREADS", "1") or "1"))
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
            LOG.info("Loaded local Vietnamese Zipformer-%s model (%s, threads=%d)", variant, snap_dir, num_threads)
            return rec
        except Exception as exc:
            LOG.warning("Failed loading Zipformer-%s: %s", variant, exc)
            _ZIPFORMER_FAILED.add(variant)
            return None


def _encode_bpe_hotwords_for_tokens(tokens_path: pathlib.Path, hotwords: tuple[tuple[str, float], ...]) -> list[str]:
    tok_set = {
        ln.split()[0]
        for ln in tokens_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    }
    encoded_lines: list[str] = []
    for phrase, score in hotwords:
        pieces: list[str] = []
        ok = True
        for w in phrase.upper().split():
            s = "\u2581" + w
            if s in tok_set:
                pieces.append(s)
                continue
            i = 0
            while i < len(s):
                matched = None
                for j in range(len(s), i, -1):
                    if s[i:j] in tok_set:
                        matched = s[i:j]
                        break
                if matched is None:
                    ok = False
                    break
                pieces.append(matched)
                i += len(matched)
            if not ok:
                break
        if ok and pieces:
            encoded_lines.append(f"{' '.join(pieces)} :{score:.1f}")
    return encoded_lines


def _get_zipformer_hotwords_recognizer(variant: str = "70m") -> Any:
    """Load Zipformer with modified_beam_search + pre-tokenized Vietnamese smart-home BPE hotwords."""
    if os.environ.get("SMARTHOME_DISABLE_LOCAL_STT", "0").strip() == "1":
        return None
    if variant in _ZIPFORMER_HW_CACHE:
        return _ZIPFORMER_HW_CACHE[variant]
    if variant in _ZIPFORMER_HW_FAILED:
        return None

    with _ZIPFORMER_LOCK:
        if variant in _ZIPFORMER_HW_CACHE:
            return _ZIPFORMER_HW_CACHE[variant]
        if variant in _ZIPFORMER_HW_FAILED:
            return None

        repo_folder = _ZIPFORMER_REPOS.get(variant)
        if not repo_folder:
            _ZIPFORMER_HW_FAILED.add(variant)
            return None
        try:
            import sherpa_onnx
        except Exception:
            _ZIPFORMER_HW_FAILED.add(variant)
            return None

        snap_str = _find_local_hf_snapshot(repo_folder, required_file="tokens.txt")
        if not snap_str:
            _ZIPFORMER_HW_FAILED.add(variant)
            return None

        snap_dir = pathlib.Path(snap_str)
        encoder = _pick_onnx_file(snap_dir, "encoder")
        decoder = _pick_onnx_file(snap_dir, "decoder")
        joiner = _pick_onnx_file(snap_dir, "joiner")
        tokens_path = snap_dir / "tokens.txt"
        if not (encoder and decoder and joiner and tokens_path.is_file()):
            _ZIPFORMER_HW_FAILED.add(variant)
            return None

        try:
            hw_lines = _encode_bpe_hotwords_for_tokens(tokens_path, _SMART_HOME_HOTWORDS)
            if not hw_lines:
                _ZIPFORMER_HW_FAILED.add(variant)
                return None
            hw_file = pathlib.Path(tempfile.gettempdir()) / f"smarthome_zf_{variant}_bpe_hotwords_v2.txt"
            hw_content = "\n".join(hw_lines) + "\n"
            if not hw_file.is_file() or hw_file.read_text(encoding="utf-8") != hw_content:
                hw_file.write_text(hw_content, encoding="utf-8")

            num_threads = max(1, int(os.environ.get("SMARTHOME_ZIPFORMER_THREADS", "1") or "1"))
            rec = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=encoder,
                decoder=decoder,
                joiner=joiner,
                tokens=str(tokens_path),
                num_threads=num_threads,
                sample_rate=16000,
                feature_dim=80,
                decoding_method="modified_beam_search",
                max_active_paths=4,
                hotwords_file=str(hw_file),
                hotwords_score=1.5,
                provider="cpu",
            )
            _ZIPFORMER_HW_CACHE[variant] = rec
            LOG.info(
                "Loaded local Vietnamese Zipformer-%s hotwords model (%d hotwords, threads=%d)",
                variant,
                len(hw_lines),
                num_threads,
            )
            return rec
        except Exception as exc:
            LOG.warning("Failed loading Zipformer-%s hotwords model: %s", variant, exc)
            _ZIPFORMER_HW_FAILED.add(variant)
            return None


def _find_local_enhancer_model() -> tuple[str, str] | None:
    """Locate cached free Sherpa-ONNX neural speech enhancement model (DPDFNet-baseline or GTCRN)."""
    candidate_dirs: list[pathlib.Path] = []
    home_dir = pathlib.Path.home()
    candidate_dirs.append(home_dir / ".cache" / "sherpa_onnx_enhancer")
    candidate_dirs.append(home_dir.parent / ".cache" / "sherpa_onnx_enhancer")
    user_profile = os.environ.get("USERPROFILE", "").strip()
    if user_profile:
        candidate_dirs.append(pathlib.Path(user_profile) / ".cache" / "sherpa_onnx_enhancer")
    win_user = os.environ.get("USERNAME", "").strip()
    if win_user:
        candidate_dirs.append(pathlib.Path("C:/Users") / win_user / ".cache" / "sherpa_onnx_enhancer")

    seen: set[str] = set()
    for d in candidate_dirs:
        key = str(d).lower()
        if key in seen or not d.is_dir():
            continue
        seen.add(key)
        for kind, fname in (("dpdfnet", "dpdfnet_baseline.onnx"), ("gtcrn", "gtcrn_simple.onnx")):
            p = d / fname
            if p.is_file() and p.stat().st_size > 10000:
                return kind, str(p)
    return None


def _get_speech_enhancer() -> tuple[Any, str]:
    global _ENHANCER_MODEL, _ENHANCER_NAME, _ENHANCER_FAILED
    if os.environ.get("SMARTHOME_DISABLE_LOCAL_STT", "0").strip() == "1":
        return None, ""
    if _ENHANCER_MODEL is not None:
        return _ENHANCER_MODEL, _ENHANCER_NAME
    if _ENHANCER_FAILED:
        return None, ""

    with _ENHANCER_LOCK:
        if _ENHANCER_MODEL is not None:
            return _ENHANCER_MODEL, _ENHANCER_NAME
        if _ENHANCER_FAILED:
            return None, ""
        found = _find_local_enhancer_model()
        if not found:
            _ENHANCER_FAILED = True
            return None, ""
        kind, model_path = found
        try:
            import sherpa_onnx

            if kind == "dpdfnet":
                mcfg = sherpa_onnx.OfflineSpeechDenoiserModelConfig(
                    dpdfnet=sherpa_onnx.OfflineSpeechDenoiserDpdfNetModelConfig(model=model_path),
                    num_threads=1,
                    provider="cpu",
                )
            else:
                mcfg = sherpa_onnx.OfflineSpeechDenoiserModelConfig(
                    gtcrn=sherpa_onnx.OfflineSpeechDenoiserGtcrnModelConfig(model=model_path),
                    num_threads=1,
                    provider="cpu",
                )
            _ENHANCER_MODEL = sherpa_onnx.OfflineSpeechDenoiser(
                sherpa_onnx.OfflineSpeechDenoiserConfig(model=mcfg)
            )
            _ENHANCER_NAME = kind
            LOG.info("Loaded local speech enhancer: %s (%s)", kind, model_path)
            return _ENHANCER_MODEL, _ENHANCER_NAME
        except Exception as exc:
            LOG.debug("Speech enhancer unavailable: %s", exc)
            _ENHANCER_FAILED = True
            return None, ""


def is_broadband_white_noise(audio_f32: np.ndarray, sr: int = 16000) -> bool:
    """Detect stationary broadband white noise (SNR <= ~12 dB) with high energy >= 2200 Hz."""
    if audio_f32 is None or audio_f32.size < int(sr * 0.4):
        return False
    frame_len = max(1, int(sr * 0.02))
    n_frames = audio_f32.size // frame_len
    if n_frames < 8:
        return False
    frames = audio_f32[: n_frames * frame_len].reshape(n_frames, frame_len)
    frame_rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    p15 = float(np.percentile(frame_rms, 15))
    p90 = float(np.percentile(frame_rms, 90))
    if (p15 / max(p90, 1e-6)) < 0.14:
        return False
    win_n = min(audio_f32.size, 32768)
    freqs = np.fft.rfftfreq(win_n, d=1.0 / float(sr))
    spec = np.abs(np.fft.rfft(audio_f32[:win_n] * np.hanning(win_n))) ** 2
    hf_ratio = float(np.sum(spec[freqs >= 2200.0]) / (float(np.sum(spec)) + 1e-18))
    return hf_ratio >= 0.03


def enhance_white_noise_audio(audio_f32: np.ndarray, sr: int = 16000) -> tuple[np.ndarray, str]:
    """Suppress broadband white noise using cached neural enhancer (DPDFNet/GTCRN) or stationary spectral gate."""
    if audio_f32 is None or audio_f32.size < int(sr * 0.3):
        return audio_f32, ""
    enh, name = _get_speech_enhancer()
    if enh is not None:
        try:
            res = enh(audio_f32.astype(np.float32), int(sr))
            y = np.asarray(res.samples, dtype=np.float32)
            pk = float(np.max(np.abs(y))) if y.size else 0.0
            if pk > 0.02:
                y = np.clip(y * (0.78 / pk), -0.98, 0.98).astype(np.float32)
                return y, name
        except Exception as exc:
            LOG.debug("Neural enhancer failed: %s", exc)
    try:
        import noisereduce as nr_lib

        y = nr_lib.reduce_noise(y=audio_f32, sr=int(sr), stationary=True, prop_decrease=0.72).astype(np.float32)
        pk = float(np.max(np.abs(y))) if y.size else 0.0
        if pk > 0.02:
            y = np.clip(y * (0.78 / pk), -0.98, 0.98).astype(np.float32)
        return y, "noisereduce"
    except Exception:
        return audio_f32, ""


def get_local_stt_warm_state() -> dict[str, Any]:
    with _WARM_LOCK:
        return {
            "ready": bool(_STT_WARM_STATE.get("ready")),
            "cold_start_ms": float(_STT_WARM_STATE.get("cold_start_ms") or 0.0),
            "models": list(_STT_WARM_STATE.get("models") or []),
        }


def preload_local_stt_models() -> dict[str, Any]:
    """Load and warm Zipformer-30M, Zipformer-70M, ChunkFormer-CTC, and neural enhancer at server startup."""
    if os.environ.get("SMARTHOME_DISABLE_LOCAL_STT", "0").strip() == "1":
        return get_local_stt_warm_state()
    with _WARM_LOCK:
        if _STT_WARM_STATE.get("ready"):
            return dict(_STT_WARM_STATE)
        t0 = time.perf_counter()
        loaded: list[str] = []
        dummy_f32 = (np.sin(np.linspace(0.0, 240.0, 9600, dtype=np.float32)) * 0.15).astype(np.float32)

        for var in ("30m", "70m"):
            rec = _get_zipformer_recognizer(var)
            if rec is not None:
                loaded.append(f"zipformer_{var}")
                try:
                    _decode_zipformer_with_gap(rec, dummy_f32, sr=16000, pad_sec=0.1)
                except Exception:
                    pass

        rec_hw = _get_zipformer_hotwords_recognizer("70m")
        if rec_hw is not None:
            loaded.append("zipformer_70m_hw")
            try:
                _decode_zipformer_with_gap(rec_hw, dummy_f32, sr=16000, pad_sec=0.1)
            except Exception:
                pass

        try:
            from simulator.voice.chunkformer_ctc import _get_chunkformer_model, decode_chunkformer_with_logprobs

            cf = _get_chunkformer_model()
            if cf is not None:
                loaded.append("chunkformer_ctc")
                decode_chunkformer_with_logprobs(dummy_f32, sr=16000, pad_s=0.1)
        except Exception as exc:
            LOG.debug("ChunkFormer preload skipped: %s", exc)

        enh, enh_name = _get_speech_enhancer()
        if enh is not None and enh_name:
            loaded.append(f"enhancer_{enh_name}")
            try:
                enh(dummy_f32, 16000)
            except Exception:
                pass

        cold_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        _STT_WARM_STATE["ready"] = True
        _STT_WARM_STATE["cold_start_ms"] = cold_ms
        _STT_WARM_STATE["models"] = loaded
        LOG.info("Preloaded & warmed local STT models (%s) in %.1f ms", ", ".join(loaded), cold_ms)
        return dict(_STT_WARM_STATE)


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

    # Real speech has clear syllable-level energy pauses; continuous muffled room babble has a flat envelope.
    if p80 <= 1e-6 or (p20 / p80) < 0.56 or rms_cv > 0.34:
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
            _NEGATED_OR_RHETORICAL_DIRECT_RE,
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
    if _NEGATED_OR_RHETORICAL_DIRECT_RE.search(low) and not parse_direct_device_intents_vi(low):
        return "negated", None

    norm_raw = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(low)).split())
    padded_raw = f" {norm_raw} "
    if _UNSUPPORTED_DEVICE_RE.search(padded_raw):
        # Conditional/automation utterances with a single-phoneme slip (e.g. 'khi mở cửa kính thì ...')
        # whose 'then'-clause is garbled must escalate rather than be locked in locally as unsupported.
        if " thi " in padded_raw and any(k in padded_raw for k in (" khi ", " neu ", " mo cua ", " dong cua ")):
            from simulator.automation_nlu import parse_single_device_and_action

            parts_u = re.split(r"\b(?:thì|thi)\b", low, maxsplit=1, flags=re.IGNORECASE)
            if len(parts_u) == 2:
                u_dev, u_act = parse_single_device_and_action(parts_u[1].strip())
                if u_dev is None or u_act is None:
                    return "unrecognized", None
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
        return "recognized", None
    if " trang thai " in padded_raw and re.match(
        r"^(?:trang\s+thai|xem|kiem\s+tra|cho\s+(?:toi\s+|minh\s+)?(?:xem|biet)|hoi|bao\s+cao|doc|"
        r"cac|tat\s+ca|toan\s+bo|den|cua|may\s+bom|coi|loa|thiet\s+bi)\b",
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

    # Automation: canonical reset, custom create/edit/delete, schedule, timer, cross-rule.
    # Uncertain or garbled transcripts must fall through as 'unrecognized' so they escalate cleanly
    # on cascade or ask for clarification offline rather than matching destructive intents.
    if _detect_scoped_reset_intent(low) is not None:
        return "recognized", None
    if any(
        k in padded_raw
        for k in (
            " reset trang thai ", " dat lai trang thai ",
            " khoi phuc cai dat goc ", " khoi phuc cai dat mac dinh ",
            " factory reset ", " cap quyen ", " thu hoi ",
        )
    ):
        return "recognized", None
    cc_parsed = _parse_custom_command_create_or_edit(low)
    if cc_parsed is not None:
        # _parse_custom_command_create_or_edit returns (phrase, steps, is_edit, is_strict_explicit).
        # Only count as recognized when at least one valid step was parsed.
        cc_steps = cc_parsed[1] if isinstance(cc_parsed, tuple) and len(cc_parsed) >= 2 else []
        if cc_steps:
            return "recognized", None
        return "unrecognized", None
    if re.match(r"^(?:huy|xoa)\s+(?:hen gio|lich|luat|lien ket|lenh|scene|kich ban)\b", norm_raw):
        return "recognized", None
    if re.match(r"^(?:doi|sua|cap nhat)\s+(?:lich|hen gio)\b", norm_raw):
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
    # Strictly require NO extra unrecognized leading/trailing word.
    normalized = normalize_vietnamese_utterance(low)
    norm_clean = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(normalized.lower())).split())
    norm_stripped = re.sub(r"\s+(?:a|nha|nhe|oi|di|nay|voi|giup minh|ho minh)$", "", norm_clean).strip()
    dev = _extract_clause_device(norm_clean, raw_clause=normalized) if norm_clean else None
    act = _extract_clause_action(norm_clean, dev, raw_clause=normalized) if norm_clean else None
    vocab = get_registry_asr_vocabulary()
    exact_bare_device_phrases: set[str] = {
        "cua ra vao", "cua nha", "cai cua",
        "den", "bong den", "tat ca den", "het den", "toan bo den", "ca hai den", "hai den", "ca den", "may cai den",
        "bong den phong khach", "phong khach",
        "bong den phong ngu", "phong ngu",
        "bao dong", "am li", "amply",
        "tat ca thiet bi", "cac thiet bi", "thiet bi",
    }
    for aliases in vocab["device_aliases"].values():
        for alias in aliases:
            a_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(alias.lower())).split())
            if a_norm:
                exact_bare_device_phrases.add(a_norm)
    exact_bare_verb_phrases = {
        "bat", "tat", "mo", "dong", "khoa",
        "bat len", "tat xuong", "mo ra", "dong lai", "khoa lai",
        "bat len di", "mo ra di", "dong lai di",
        "bat het len", "tat het di", "bat no len", "tat no di",
    }
    if dev is not None and act is None and norm_stripped in exact_bare_device_phrases:
        return "bare_device", dev
    if act is not None and dev is None and norm_stripped in exact_bare_verb_phrases:
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


def _finalize_offline_result(
    text: str,
    audio_f32: np.ndarray,
    engine: str,
    confidence: float,
    t0: float,
    *,
    cf_lp: Any = None,
    cf_greedy: str | None = None,
) -> dict[str, Any]:
    """Finalize offline STT response with acoustic tone verification ('đèn' vs 'đen') on direct light commands."""
    final_text = text
    final_engine = engine
    if final_text and re.search(r"\bđèn\b", final_text, flags=re.IGNORECASE):
        try:
            from simulator.voice.vietnamese_policy import parse_direct_device_intents_vi

            ints = parse_direct_device_intents_vi(final_text)
            if any(
                str(it.get("device_id") or "") in ("living_room_light", "bedroom_light")
                for it in ints
            ):
                from simulator.voice.chunkformer_ctc import verify_light_den_tone_ctc

                verified_txt, flipped = verify_light_den_tone_ctc(
                    audio_f32,
                    final_text,
                    sr=16000,
                    log_probs=cf_lp,
                    greedy_text=cf_greedy,
                )
                if flipped:
                    final_text = verified_txt
                    final_engine = f"{final_engine}+ctc_den_tone"
        except Exception:
            pass
    return {
        "ok": True,
        "text": final_text,
        "confidence": confidence,
        "is_noise": False,
        "stt_ms": round((time.perf_counter() - t0) * 1000.0, 1),
        "stt_engine": final_engine,
    }


def _is_safe_rescue_direct_command(cand_txt: str, base_txt: str, cf_greedy: str) -> bool:
    """Prevent hotword/alt/denoised rescues from turning automation/custom/long utterances into immediate direct actions."""
    if not cand_txt:
        return False
    try:
        from simulator.voice.vietnamese_policy import parse_direct_device_intents_vi, strip_vi_accents
    except Exception:
        return True
    if not parse_direct_device_intents_vi(cand_txt):
        return True  # Not a direct device command (e.g. confirmation prompt, query, smalltalk, unsupported)

    c_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(cand_txt.lower())).split())
    c_toks = c_norm.split()
    _AUTO_LEAD_TOKENS = {"tao", "sua", "xoa", "luu", "dat", "hen", "khi", "neu", "them"}
    if c_toks and c_toks[0] in _AUTO_LEAD_TOKENS:
        return False

    for ref in (base_txt, cf_greedy):
        if not ref:
            continue
        r_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(ref.lower())).split())
        r_toks = r_norm.split()
        r_pad = f" {r_norm} "
        if r_toks and r_toks[0] in _AUTO_LEAD_TOKENS:
            return False
        if any(
            k in r_pad
            for k in (
                " tao lenh ", " sua lenh ", " xoa lenh ", " dat lich ",
                " hen gio ", " phut nua ", " giay nua ", " tieng nua ", " gio nua ", " thi ",
            )
        ):
            return False
        if len(r_toks) >= 7 and len(c_toks) <= len(r_toks) - 2:
            return False
    return True


def _has_background_noise_for_denoise(audio_f32: np.ndarray, sr: int = 16000) -> bool:
    """Detect non-trivial background noise for selective neural speech enhancement."""
    if is_broadband_white_noise(audio_f32, sr=sr):
        return True
    if audio_f32 is None or audio_f32.size < int(sr * 0.4):
        return False
    frame_len = max(1, int(sr * 0.02))
    n_frames = audio_f32.size // frame_len
    if n_frames < 8:
        return False
    frames = audio_f32[: n_frames * frame_len].reshape(n_frames, frame_len)
    frame_rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    p15 = float(np.percentile(frame_rms, 15))
    p90 = float(np.percentile(frame_rms, 90))
    return (p15 / max(p90, 1e-6)) >= 0.08


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

                # Detect Pass-1 anomalies where greedy Zipformer returned a partial or phonetically confused transcript
                # (near-homophones 'bom'/'tắc', dropped multi-clause tail, or short high-pitch small-talk decode).
                low_txt = txt.lower()
                has_bom_or_tac = bool(re.search(r"\b(?:bom|tắc)\b", low_txt))
                has_query_smalltalk_collision = bool(
                    kind == "recognized"
                    and re.search(r"\b(?:thế nào|bao nhiêu)\b", low_txt)
                    and "cảm ơn" in low_txt
                )
                has_partial_multi = False
                base_intents_count = 0
                if kind == "recognized" and not muffled_babble:
                    try:
                        from simulator.voice.vietnamese_policy import parse_direct_device_intents_vi

                        base_intents = parse_direct_device_intents_vi(txt)
                        base_intents_count = len(base_intents)
                        if base_intents and (" và " in low_txt or " rồi " in low_txt):
                            clauses = re.split(r"\b(?:và|rồi)\b", low_txt)
                            if any(c.strip() and not parse_direct_device_intents_vi(c.strip()) for c in clauses):
                                has_partial_multi = True
                    except Exception:
                        pass

                is_high_pitch_short = False
                is_high_pitch_short_smalltalk = False
                if not muffled_babble and duration_sec <= 1.35:
                    try:
                        from simulator.voice.chunkformer_ctc import estimate_pitch_f0_hz
                        from simulator.voice.vietnamese_policy import classify_small_talk_vi

                        if estimate_pitch_f0_hz(audio_f32, sr=16000) >= 245.0:
                            is_high_pitch_short = True
                            if len(tokens) <= 2 and classify_small_talk_vi(low_txt) is not None:
                                is_high_pitch_short_smalltalk = True
                    except Exception:
                        pass

                pass1_needs_anomaly_rescue = bool(
                    not muffled_babble
                    and (
                        has_bom_or_tac
                        or has_partial_multi
                        or is_high_pitch_short_smalltalk
                        or has_query_smalltalk_collision
                    )
                )

                # Fast path (~0.2-0.5s): return immediately on clean recognized intents, unsupported devices,
                # negated utterances, foreign speech, bare verbs, or bare nouns with NO un-decoded leading speech.
                if not pass1_needs_anomaly_rescue:
                    if kind in ("recognized", "unsupported", "negated", "foreign", "bare_verb"):
                        return _finalize_offline_result(
                            txt,
                            audio_f32,
                            f"zipformer_{variant}",
                            0.88 if variant == "70m" else 0.85,
                            t0,
                        )
                    if kind == "bare_device" and onset_gap < 0.08:
                        return _finalize_offline_result(
                            txt,
                            audio_f32,
                            f"zipformer_{variant}:bare_verified",
                            0.86,
                            t0,
                        )

                # Pass 2 (~0.42s): ChunkFormer-CTC + Domain Hotwords Zipformer rescue
                cf_greedy = ""
                cf_lp: Any = None
                hw_txt = ""
                alt_txt = ""
                if not muffled_babble:
                    try:
                        from simulator.voice.chunkformer_ctc import (
                            decode_chunkformer_with_logprobs,
                            rescore_closed_command_ctc,
                            rescore_confirm_command_ctc,
                            rescore_sensor_query_ctc,
                            rescore_timer_or_conditional_ctc,
                            vtln_resample,
                        )

                        cf_greedy, cf_lp = decode_chunkformer_with_logprobs(audio_f32, sr=16000, pad_s=0.25)
                        cf_kind, _ = _classify_offline_transcript_kind(cf_greedy)

                        if pass1_needs_anomaly_rescue and not is_high_pitch_short_smalltalk and not has_query_smalltalk_collision:
                            # Compare greedy Pass-1 vs ChunkFormer vs Zipformer-70M-Hotwords vs Zipformer-30M
                            from simulator.voice.vietnamese_policy import parse_direct_device_intents_vi

                            best_cand = txt
                            best_eng = f"zipformer_{variant}"
                            best_score_tuple = (
                                base_intents_count,
                                int("bơm" in low_txt),
                                int("tắt" in low_txt),
                                int(not has_bom_or_tac),
                            )

                            def _consider(cand: str, eng_name: str) -> None:
                                nonlocal best_cand, best_eng, best_score_tuple
                                if not cand:
                                    return
                                c_kind, _ = _classify_offline_transcript_kind(cand)
                                if c_kind in ("unsupported", "negated", "foreign") and kind != "recognized":
                                    return
                                c_low = cand.lower()
                                c_ints = len(parse_direct_device_intents_vi(cand)) if c_kind == "recognized" else 0
                                sc = (
                                    c_ints,
                                    int("bơm" in c_low),
                                    int("tắt" in c_low),
                                    int(not bool(re.search(r"\b(?:bom|tắc)\b", c_low))),
                                )
                                if sc > best_score_tuple:
                                    best_score_tuple = sc
                                    best_cand = cand
                                    best_eng = eng_name

                            _consider(cf_greedy, f"zipformer_{variant}+chunkformer_ctc_multi")
                            rec_hw = _get_zipformer_hotwords_recognizer("70m")
                            if rec_hw is not None:
                                hw_txt, _ = _decode_zipformer_with_gap(rec_hw, audio_f32, sr=16000, pad_sec=zip_pad)
                                _consider(hw_txt, "zipformer_70m_hw_rescue")
                            rec_alt_a = _get_zipformer_recognizer(alt_variant)
                            if rec_alt_a is not None:
                                alt_txt, _ = _decode_zipformer_with_gap(rec_alt_a, audio_f32, sr=16000, pad_sec=zip_pad)
                                _consider(alt_txt, f"zipformer_{alt_variant}_rescue")

                            return _finalize_offline_result(
                                best_cand,
                                audio_f32,
                                best_eng,
                                0.89,
                                t0,
                                cf_lp=cf_lp,
                                cf_greedy=cf_greedy,
                            )

                        if cf_kind in ("unsupported", "negated", "foreign"):
                            return _finalize_offline_result(
                                cf_greedy,
                                audio_f32,
                                f"zipformer_{variant}+chunkformer_ctc",
                                0.88,
                                t0,
                                cf_lp=cf_lp,
                                cf_greedy=cf_greedy,
                            )
                        if cf_kind == "recognized":
                            return _finalize_offline_result(
                                cf_greedy,
                                audio_f32,
                                f"zipformer_{variant}+chunkformer_ctc",
                                0.90,
                                t0,
                                cf_lp=cf_lp,
                                cf_greedy=cf_greedy,
                            )

                        # Pass 2b (~0.25s): Zipformer-70M with registry-derived Vietnamese smart-home BPE hotwords
                        # Rescues domain device and automation phrases under accent or low-gain conditions.
                        rec_hw = _get_zipformer_hotwords_recognizer("70m")
                        if rec_hw is not None and not is_high_pitch_short_smalltalk and not has_query_smalltalk_collision:
                            hw_txt, _ = _decode_zipformer_with_gap(rec_hw, audio_f32, sr=16000, pad_sec=zip_pad)
                            hw_kind, _ = _classify_offline_transcript_kind(hw_txt)
                            if hw_kind in ("unsupported", "negated", "foreign") or (
                                hw_kind == "recognized" and _is_safe_rescue_direct_command(hw_txt, txt, cf_greedy)
                            ):
                                return _finalize_offline_result(
                                    hw_txt,
                                    audio_f32,
                                    "zipformer_70m_hw",
                                    0.88,
                                    t0,
                                    cf_lp=cf_lp,
                                    cf_greedy=cf_greedy,
                                )

                        # Pass 2c (~3ms, zero extra encoder pass): Constrained CTC acoustic rescoring
                        expected_dev = bare_dev if (kind == "bare_device" and onset_gap >= 0.08) else None
                        rescored = rescore_closed_command_ctc(
                            cf_lp,
                            cf_greedy,
                            expected_device=expected_dev,
                            onset_gap=onset_gap,
                            high_pitch_short=is_high_pitch_short,
                        )
                        if rescored:
                            return _finalize_offline_result(
                                rescored,
                                audio_f32,
                                (
                                    f"zipformer_{variant}+chunkformer_ctc_onset"
                                    if expected_dev
                                    else f"zipformer_{variant}+chunkformer_ctc_rescore"
                                ),
                                0.87,
                                t0,
                                cf_lp=cf_lp,
                                cf_greedy=cf_greedy,
                            )

                        # Pass 2d (~4ms, zero extra encoder pass): Timer tail, conditional rule, confirm system & read-only sensor query CTC rescoring
                        if expected_dev is None and kind != "bare_device":
                            tc_rescored = rescore_timer_or_conditional_ctc(cf_lp, cf_greedy)
                            if tc_rescored:
                                return _finalize_offline_result(
                                    tc_rescored,
                                    audio_f32,
                                    f"zipformer_{variant}+chunkformer_ctc_timer_cond",
                                    0.87,
                                    t0,
                                    cf_lp=cf_lp,
                                    cf_greedy=cf_greedy,
                                )
                            sys_rescored = rescore_confirm_command_ctc(cf_lp, cf_greedy)
                            if sys_rescored:
                                return _finalize_offline_result(
                                    sys_rescored,
                                    audio_f32,
                                    f"zipformer_{variant}+chunkformer_ctc_confirm_sys",
                                    0.86,
                                    t0,
                                    cf_lp=cf_lp,
                                    cf_greedy=cf_greedy,
                                )
                            qry_rescored = rescore_sensor_query_ctc(cf_lp, cf_greedy)
                            if qry_rescored:
                                return _finalize_offline_result(
                                    qry_rescored,
                                    audio_f32,
                                    f"zipformer_{variant}+chunkformer_ctc_sensor_qry",
                                    0.86,
                                    t0,
                                    cf_lp=cf_lp,
                                    cf_greedy=cf_greedy,
                                )

                        # High-pitch short speaker VTLN rescue (F0 >= 245 Hz, dur <= 1.5s)
                        if expected_dev is None and duration_sec <= 1.50 and is_high_pitch_short:
                            vtln_audio = vtln_resample(audio_f32, factor=0.78)
                            vg, vlp = decode_chunkformer_with_logprobs(vtln_audio, sr=16000, pad_s=0.25)
                            v_kind, _ = _classify_offline_transcript_kind(vg)
                            if v_kind in ("unsupported", "negated", "foreign", "recognized"):
                                return _finalize_offline_result(
                                    vg,
                                    audio_f32,
                                    f"zipformer_{variant}+chunkformer_ctc_vtln",
                                    0.87,
                                    t0,
                                    cf_lp=vlp,
                                    cf_greedy=vg,
                                )
                            v_rescored = rescore_closed_command_ctc(vlp, vg, high_pitch_short=True)
                            if v_rescored:
                                return _finalize_offline_result(
                                    v_rescored,
                                    audio_f32,
                                    f"zipformer_{variant}+chunkformer_ctc_vtln_rescore",
                                    0.86,
                                    t0,
                                    cf_lp=vlp,
                                    cf_greedy=vg,
                                )
                    except Exception as exc:
                        LOG.debug("ChunkFormer-CTC rescue skipped: %s", exc)

                # If high-pitch short small talk was not rescued into a clear command, return original transcript safely
                if is_high_pitch_short_smalltalk:
                    return _finalize_offline_result(txt, audio_f32, f"zipformer_{variant}", 0.85, t0)

                # Pass 3 (~0.35s): Alternate Zipformer size tie-breaker
                if not muffled_babble:
                    rec_alt = _get_zipformer_recognizer(alt_variant)
                    if rec_alt is not None:
                        alt_txt, _ = _decode_zipformer_with_gap(rec_alt, audio_f32, sr=16000, pad_sec=zip_pad)
                        alt_kind, _ = _classify_offline_transcript_kind(alt_txt)
                        if alt_kind in ("unsupported", "negated", "foreign") or (
                            alt_kind == "recognized" and _is_safe_rescue_direct_command(alt_txt, txt, cf_greedy)
                        ):
                            return _finalize_offline_result(
                                alt_txt,
                                audio_f32,
                                f"zipformer_{alt_variant}_rescue",
                                0.85,
                                t0,
                                cf_lp=cf_lp,
                                cf_greedy=cf_greedy,
                            )

                # Pass 4 (selective neural speech enhancement rescue ONLY when raw passes 1-3 failed AND background noise is present):
                if not muffled_babble and kind not in ("bare_device",) and _has_background_noise_for_denoise(audio_f32, sr=16000):
                    try:
                        enh_audio, enh_name = enhance_white_noise_audio(audio_f32, sr=16000)
                        if enh_name and enh_audio.size > 0:
                            from simulator.voice.chunkformer_ctc import (
                                decode_chunkformer_with_logprobs,
                                rescore_closed_command_ctc,
                                rescore_confirm_command_ctc,
                                rescore_sensor_query_ctc,
                                rescore_timer_or_conditional_ctc,
                            )

                            enh_cf, enh_lp = decode_chunkformer_with_logprobs(enh_audio, sr=16000, pad_s=0.25)
                            enh_kind, _ = _classify_offline_transcript_kind(enh_cf)
                            if enh_kind in ("unsupported", "negated") or (
                                enh_kind == "recognized" and _is_safe_rescue_direct_command(enh_cf, txt, cf_greedy)
                            ):
                                return _finalize_offline_result(
                                    enh_cf,
                                    audio_f32,
                                    f"zipformer_{variant}+enh_{enh_name}+chunkformer_ctc",
                                    0.86,
                                    t0,
                                    cf_lp=enh_lp,
                                    cf_greedy=enh_cf,
                                )
                            enh_res = (
                                rescore_closed_command_ctc(enh_lp, enh_cf)
                                or rescore_timer_or_conditional_ctc(enh_lp, enh_cf)
                                or rescore_confirm_command_ctc(enh_lp, enh_cf)
                                or rescore_sensor_query_ctc(enh_lp, enh_cf)
                            )
                            if enh_res and _is_safe_rescue_direct_command(enh_res, txt, cf_greedy):
                                return _finalize_offline_result(
                                    enh_res,
                                    audio_f32,
                                    f"zipformer_{variant}+enh_{enh_name}+chunkformer_ctc_rescore",
                                    0.85,
                                    t0,
                                    cf_lp=enh_lp,
                                    cf_greedy=enh_cf,
                                )
                            rec_enh_zf = _get_zipformer_hotwords_recognizer("70m") or rec_primary
                            enh_z70, _ = _decode_zipformer_with_gap(rec_enh_zf, enh_audio, sr=16000, pad_sec=zip_pad)
                            enh_z_kind, _ = _classify_offline_transcript_kind(enh_z70)
                            if enh_z_kind in ("unsupported", "negated") or (
                                enh_z_kind == "recognized" and _is_safe_rescue_direct_command(enh_z70, txt, cf_greedy)
                            ):
                                return _finalize_offline_result(
                                    enh_z70,
                                    audio_f32,
                                    f"zipformer_{variant}+enh_{enh_name}_hw",
                                    0.85,
                                    t0,
                                    cf_lp=enh_lp,
                                    cf_greedy=enh_cf,
                                )
                    except Exception as exc:
                        LOG.debug("Selective neural enhancer rescue skipped: %s", exc)

                # Preserve bare device noun for clean clarification; otherwise prefer ChunkFormer for open-vocabulary phrases
                final_txt = txt if kind == "bare_device" else (cf_greedy or hw_txt or txt)
                if final_txt:
                    return _finalize_offline_result(
                        final_txt,
                        audio_f32,
                        f"zipformer_{variant}+chunkformer_ctc_fallback" if (final_txt == cf_greedy and cf_greedy) else f"zipformer_{variant}",
                        0.82,
                        t0,
                        cf_lp=cf_lp,
                        cf_greedy=cf_greedy,
                    )
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
