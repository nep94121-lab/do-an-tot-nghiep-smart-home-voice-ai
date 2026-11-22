"""Fast local Vietnamese ChunkFormer-CTC decoder and closed-vocabulary acoustic rescorer."""

from __future__ import annotations

import logging
import os
import pathlib
import re
import threading
from typing import Any

import numpy as np

LOG = logging.getLogger("simulator.voice.chunkformer_ctc")

_CHUNKFORMER_REPO = "models--khanhld--chunkformer-ctc-large-vie"
_CF_LOCK = threading.Lock()
_CF_MODEL: Any = None
_CF_ID2TOK: dict[int, str] = {}
_CF_TOK2ID: dict[str, int] = {}
_CF_GRAMMAR_ENC: list[tuple[str, str, str, Any]] = []
_CF_CONFIRM_ENC: list[tuple[str, str, tuple[Any, ...]]] = []
_CF_LONG_NEG_ENC: list[tuple[str, Any]] = []
_CF_FAILED: bool = False

_NON_VERB_LEADING_TOKENS_RAW: frozenset[str] = frozenset({
    "không", "khong", "đừng", "dung", "chớ", "cho", "khỏi", "khoi", "chưa", "chua",
    "ờ", "à", "ừm", "ừ", "ơ", "này", "ơi", "dạ", "vâng", "thưa",
    "cái", "chiếc", "mấy", "các",
})


def _get_registry_vocab() -> dict[str, Any]:
    from simulator.voice.vietnamese_stt import get_registry_asr_vocabulary

    return get_registry_asr_vocabulary()


def _build_sensor_query_grammar() -> tuple[tuple[str, str], ...]:
    """Derive read-only sensor & device status query candidates from the canonical hardware registry."""
    vocab = _get_registry_vocab()
    spoken = vocab["spoken_labels"]
    items: list[tuple[str, str]] = [
        ("nhiệt độ và độ ẩm hiện tại là bao nhiêu", "qry:temp_hum"),
        ("nhiệt độ hiện tại là bao nhiêu", "qry:temp"),
        ("nhiệt độ hiện tại bao nhiêu", "qry:temp"),
        ("độ ẩm không khí bao nhiêu", "qry:air_hum"),
        ("độ ẩm đất bao nhiêu", "qry:soil"),
        ("cảm biến âm thanh hiện tại thế nào", "qry:sound"),
        ("kiểm tra cảm biến trong nhà", "qry:all_sensors"),
    ]
    for dev_id, lbl in spoken.items():
        if dev_id == "main_door":
            items.append((f"{lbl} đang mở hay đóng", f"qry:{dev_id}_status"))
        elif "light" in dev_id:
            items.append((f"{lbl} đang bật hay tắt", f"qry:{dev_id}_status"))
    return tuple(items)


def _build_confirm_system_grammar() -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """Derive confirmation-gated system commands strictly from clean canonical registry names (zero garbles)."""
    vocab = _get_registry_vocab()
    items: list[tuple[str, str, tuple[str, ...]]] = [
        (
            "reset trạng thái thiết bị",
            "sys:reset_devices",
            ("reset trạng thái thiết bị", "đặt lại trạng thái thiết bị"),
        ),
        ("reset liên kết", "sys:reset_links", ("reset liên kết", "xóa liên kết")),
        ("khôi phục cài đặt gốc", "sys:factory_reset", ("khôi phục cài đặt gốc",)),
        ("xóa hết hẹn giờ", "sys:clear_timers", ("xóa hết hẹn giờ", "hủy tất cả hẹn giờ")),
    ]
    for dev_id, spoken in vocab["spoken_labels"].items():
        short = "máy bơm" if dev_id == "garden_pump" else spoken
        variants = (f"hủy hẹn giờ {short}",) if short == spoken else (f"hủy hẹn giờ {short}", f"hủy hẹn giờ {spoken}")
        items.append((f"hủy hẹn giờ {short}", f"sys:cancel_{dev_id}", variants))
    return tuple(items)


# Neutral general Vietnamese sentences (4-7 words) used as length-matched negative anchors for CTC rescoring
_LONG_NEGATIVE_ANCHORS: tuple[str, ...] = (
    "trời hôm nay khá dịu mát",
    "chiều nay trời có chút nắng nhẹ",
    "mọi người đang ăn cơm tối",
    "nhà mình vừa dọn dẹp xong rồi",
    "bạn có khỏe không hôm nay",
    "nhiệt độ phòng đang khá dễ chịu",
    "độ ẩm không khí ngoài trời cao",
    "cảm biến ngoài sân vẫn ổn định",
    "mở quạt máy ngoài hành lang",
    "tắt máy lạnh trên tầng hai",
    "mở tivi xem bản tin tối",
    "kéo rèm cửa sổ phòng ngủ",
    "không cần bật đèn lúc này",
    "đừng mở cửa khi trời mưa",
    "cảm ơn bạn rất nhiều nhé",
    "chào buổi tối cả gia đình",
)


def _build_conditional_triggers() -> tuple[tuple[str, str], ...]:
    vocab = _get_registry_vocab()
    spoken = vocab["spoken_labels"]
    door_lbl = spoken.get("main_door", "cửa chính")
    living_lbl = spoken.get("living_room_light", "đèn phòng khách")
    return (
        (f"khi mở {door_lbl}", "trig:door_open"),
        (f"khi đóng {door_lbl}", "trig:door_close"),
        ("khi đất khô", "trig:soil_dry"),
        ("khi có tiếng động lớn", "trig:loud_sound"),
        (f"khi {living_lbl} bật", "trig:living_on"),
        (f"khi {living_lbl} tắt", "trig:living_off"),
    )


def _build_conditional_actions() -> tuple[tuple[str, str, str], ...]:
    vocab = _get_registry_vocab()
    actions: list[tuple[str, str, str]] = []
    light_count = 0
    for dev_id, spoken in vocab["spoken_labels"].items():
        if "light" in dev_id:
            light_count += 1
        verbs = vocab["action_verbs"][dev_id]
        on_v = next((v for a, v in verbs if a in ("open", "turn_on")), "bật")
        off_v = next((v for a, v in verbs if a in ("close", "turn_off")), "tắt")
        actions.append((f"{on_v} {spoken}", dev_id, "on"))
        actions.append((f"{off_v} {spoken}", dev_id, "off"))
    if light_count >= 2:
        actions.append(("bật tất cả đèn", "all_lights", "on"))
        actions.append(("tắt tất cả đèn", "all_lights", "off"))
    return tuple(actions)


_CONDITIONAL_NEG_ANCHORS: tuple[str, ...] = (
    "khi trời mưa thì đóng cửa sổ",
    "khi xem phim thì tắt máy lạnh",
    "khi ra ngoài thì kéo rèm lại",
    "khi nóng quá thì mở quạt trần",
    "buổi chiều trời mát mọi người nghỉ ngơi",
    "bạn giới thiệu chức năng giúp tôi",
    "nhiệt độ phòng bây giờ khoảng mấy độ",
)


def _build_closed_grammar() -> tuple[tuple[str, str, str], ...]:
    """Derive closed-vocabulary device commands and neutral negative anchors from the hardware registry."""
    vocab = _get_registry_vocab()
    entries: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(phrase: str, kind: str, dev_id: str) -> None:
        key = (phrase, kind)
        if phrase and key not in seen:
            seen.add(key)
            entries.append((phrase, kind, dev_id))

    light_count = 0
    for dev_id, spoken in vocab["spoken_labels"].items():
        if "light" in dev_id:
            light_count += 1
        verbs = vocab["action_verbs"][dev_id]
        aliases = vocab["device_aliases"][dev_id]
        for alias in aliases:
            if alias in ("cổng", "máy bơm nước", "bơm nước", "bơm vườn", "chuông báo động", "mạch loa", "nguồn loa"):
                continue
            for act_id, verb in verbs:
                if verb in ("khóa", "khép") and alias != spoken and alias != "cửa":
                    continue
                if verb == "khép" and alias == "cửa":
                    continue
                _add(f"{verb} {alias}", f"cmd:{dev_id}:{act_id}", dev_id)
        if dev_id == "garden_pump":
            _add("dừng tưới vườn", f"cmd:{dev_id}:turn_off", dev_id)

    if light_count >= 2:
        for alias in ("tất cả đèn", "hết đèn"):
            _add(f"bật {alias}", "cmd:all_lights:turn_on", "all_lights")
            _add(f"tắt {alias}", "cmd:all_lights:turn_off", "all_lights")

    _add("bật tất cả thiết bị", "cmd:all_devices:turn_on", "all_devices")
    _add("tắt tất cả thiết bị", "cmd:all_devices:turn_off", "all_devices")

    # Bare-noun negative anchors derived from the same device registry
    for dev_id, spoken in vocab["spoken_labels"].items():
        bare_lbl = "máy bơm" if dev_id == "garden_pump" else spoken
        _add(bare_lbl, "bare", dev_id)
    if light_count >= 2:
        _add("tất cả đèn", "bare", "all_lights")
    _add("tất cả thiết bị", "bare", "all_devices")

    # General neutral negative anchors (bare verbs, unsupported appliances, greetings, negations, confirmations)
    for phrase, kind in (
        ("bật lên đi", "bare"),
        ("tắt đi", "bare"),
        ("mở đi", "bare"),
        ("đóng đi", "bare"),
        ("bật quạt trần", "unsupported"),
        ("tắt điều hòa", "unsupported"),
        ("mở tivi", "unsupported"),
        ("bật máy giặt", "unsupported"),
        ("đóng rèm cửa", "unsupported"),
        ("mở cửa cuốn", "unsupported"),
        ("bật lò vi sóng", "unsupported"),
        ("chào bạn", "smalltalk"),
        ("xin chào", "smalltalk"),
        ("chào buổi sáng", "smalltalk"),
        ("chào buổi tối", "smalltalk"),
        ("tạm biệt", "smalltalk"),
        ("cảm ơn", "smalltalk"),
        ("cảm ơn bạn", "smalltalk"),
        ("ngủ ngon", "smalltalk"),
        ("hẹn gặp lại", "smalltalk"),
        ("không mở cửa", "negated"),
        ("đừng mở cửa", "negated"),
        ("không bật đèn", "negated"),
        ("đừng bật đèn", "negated"),
        ("không bật máy bơm", "negated"),
        ("đừng bật còi", "negated"),
        ("ok", "confirm"),
        ("được", "confirm"),
        ("đồng ý", "confirm"),
        ("không", "confirm"),
        ("thôi", "confirm"),
        ("hủy", "confirm"),
    ):
        _add(phrase, kind, "")

    return tuple(entries)


_SENSOR_QUERY_GRAMMAR: tuple[tuple[str, str], ...] = _build_sensor_query_grammar()
_CONFIRM_SYSTEM_GRAMMAR: tuple[tuple[str, str, tuple[str, ...]], ...] = _build_confirm_system_grammar()
_CONDITIONAL_TRIGGERS: tuple[tuple[str, str], ...] = _build_conditional_triggers()
_CONDITIONAL_ACTIONS: tuple[tuple[str, str, str], ...] = _build_conditional_actions()
_CLOSED_GRAMMAR: tuple[tuple[str, str, str], ...] = _build_closed_grammar()


def _encode_bpe(phrase: str, tok2id: dict[str, int]) -> list[int] | None:
    ids: list[int] = []
    for word in phrase.lower().split():
        s = "\u2581" + word
        if s in tok2id:
            ids.append(tok2id[s])
            continue
        i = 0
        while i < len(s):
            matched = None
            for j in range(len(s), i, -1):
                sub = s[i:j]
                if sub in tok2id:
                    matched = sub
                    break
            if matched is None:
                return None
            ids.append(tok2id[matched])
            i += len(matched)
    return ids


def _get_chunkformer_model() -> Any:
    global _CF_MODEL, _CF_ID2TOK, _CF_TOK2ID, _CF_GRAMMAR_ENC, _CF_CONFIRM_ENC, _CF_LONG_NEG_ENC, _CF_FAILED
    if os.environ.get("SMARTHOME_DISABLE_LOCAL_STT", "0").strip() == "1":
        return None
    if os.environ.get("SMARTHOME_DISABLE_CHUNKFORMER", "0").strip() == "1":
        return None
    if _CF_MODEL is not None:
        return _CF_MODEL
    if _CF_FAILED:
        return None

    with _CF_LOCK:
        if _CF_MODEL is not None:
            return _CF_MODEL
        if _CF_FAILED:
            return None
        try:
            import torch
            from chunkformer import ChunkFormerModel
            from simulator.voice.vietnamese_stt import _find_local_hf_snapshot

            snap_str = _find_local_hf_snapshot(_CHUNKFORMER_REPO, required_file="pytorch_model.bin")
            if not snap_str:
                LOG.debug("ChunkFormer local snapshot not found (%s)", _CHUNKFORMER_REPO)
                _CF_FAILED = True
                return None

            # 4 PyTorch threads avoids OpenMP spin-wait contention with single-threaded Sherpa-ONNX Zipformer.
            num_threads = max(1, int(os.environ.get("SMARTHOME_TORCH_THREADS", "4") or "4"))
            torch.set_num_threads(num_threads)
            model = ChunkFormerModel.from_pretrained(snap_str)
            model.eval()
            id2tok = dict(model.char_dict)
            tok2id = {v: int(k) for k, v in id2tok.items()}
            grammar_enc: list[tuple[str, str, str, Any]] = []
            for ph, kind, dev in _CLOSED_GRAMMAR:
                ids = _encode_bpe(ph, tok2id)
                if ids:
                    grammar_enc.append((ph, kind, dev, torch.tensor(ids, dtype=torch.long)))

            confirm_enc: list[tuple[str, str, tuple[Any, ...]]] = []
            for canon, kind, variants in _CONFIRM_SYSTEM_GRAMMAR:
                tensors = []
                for v in variants:
                    ids = _encode_bpe(v, tok2id)
                    if ids:
                        tensors.append(torch.tensor(ids, dtype=torch.long))
                if tensors:
                    confirm_enc.append((canon, kind, tuple(tensors)))

            long_neg_enc: list[tuple[str, Any]] = []
            for ph in _LONG_NEGATIVE_ANCHORS:
                ids = _encode_bpe(ph, tok2id)
                if ids:
                    long_neg_enc.append((ph, torch.tensor(ids, dtype=torch.long)))

            _CF_ID2TOK = id2tok
            _CF_TOK2ID = tok2id
            _CF_GRAMMAR_ENC = grammar_enc
            _CF_CONFIRM_ENC = confirm_enc
            _CF_LONG_NEG_ENC = long_neg_enc
            _CF_MODEL = model
            LOG.info("Loaded local Vietnamese ChunkFormer-CTC model (%s)", pathlib.Path(snap_str).name)
            return _CF_MODEL
        except Exception as exc:
            LOG.warning("Failed loading ChunkFormer-CTC: %s", exc)
            _CF_FAILED = True
            return None


def estimate_pitch_f0_hz(audio_f32: np.ndarray, sr: int = 16000) -> float:
    """Fast (<1ms) median autocorrelation F0 estimate on voiced frames (80-450 Hz)."""
    if audio_f32 is None or audio_f32.size < 512:
        return 0.0
    frame_len = 512
    min_lag = max(1, int(sr / 450))
    max_lag = min(frame_len - 1, int(sr / 80))
    if max_lag <= min_lag:
        return 0.0
    f0s: list[float] = []
    for i in range(0, audio_f32.size - frame_len, 256):
        fr = audio_f32[i : i + frame_len]
        if float(np.sqrt(np.mean(fr * fr))) < 0.05:
            continue
        fr_z = fr - float(np.mean(fr))
        ac = np.correlate(fr_z, fr_z, mode="full")[frame_len - 1 :]
        if ac[0] <= 1e-6:
            continue
        seg = ac[min_lag:max_lag]
        if seg.size == 0:
            continue
        pk = int(np.argmax(seg))
        if float(seg[pk]) / float(ac[0]) > 0.45:
            f0s.append(float(sr) / float(min_lag + pk))
    return float(np.median(f0s)) if f0s else 0.0


def vtln_resample(audio_f32: np.ndarray, factor: float = 0.78) -> np.ndarray:
    """Fast (<1ms) Vocal Tract Length Normalization resampling for high-pitch/fast speakers."""
    if audio_f32.size < 160 or abs(factor - 1.0) < 1e-3:
        return audio_f32
    new_len = max(160, int(round(audio_f32.size / float(factor))))
    idx = np.linspace(0.0, float(audio_f32.size - 1), new_len)
    return np.interp(idx, np.arange(audio_f32.size, dtype=np.float64), audio_f32).astype(np.float32)


def _clean_ctc_ids(hyps_1d: list[int]) -> str:
    prev = -1
    pieces: list[str] = []
    for idx in hyps_1d:
        if idx != prev and idx != 0:
            tok = _CF_ID2TOK.get(int(idx), "")
            if tok and tok not in ("<blank>", "<unk>", "<sos/eos>"):
                pieces.append(tok)
        prev = idx
    txt = "".join(pieces).replace("\u2581", " ")
    return " ".join(txt.strip().lower().split())


def decode_chunkformer_with_logprobs(
    audio_f32: np.ndarray,
    sr: int = 16000,
    *,
    pad_s: float = 0.15,
) -> tuple[str, Any]:
    """Run ChunkFormer-CTC forward pass and return (greedy_text, ctc_log_probs[T, V])."""
    model = _get_chunkformer_model()
    if model is None or audio_f32 is None or audio_f32.size < 160:
        return "", None
    import torch
    import torchaudio.compliance.kaldi as kaldi

    pad = np.zeros(int(sr * pad_s), dtype=np.float32)
    x = np.concatenate([pad, audio_f32, pad])
    pcm16_f = np.clip(np.round(x * 32767.0), -32767, 32767).astype(np.float32)
    wf = torch.from_numpy(pcm16_f).unsqueeze(0)
    feats = kaldi.fbank(
        wf,
        num_mel_bins=80,
        frame_length=25,
        frame_shift=10,
        dither=0.0,
        energy_floor=0.0,
        sample_frequency=sr,
    ).unsqueeze(0)
    feat_lens = torch.tensor([feats.shape[1]], dtype=torch.long)
    with torch.no_grad():
        enc_out, _ = model.encode(
            feats,
            feat_lens,
            chunk_size=64,
            left_context_size=128,
            right_context_size=128,
        )
        log_probs = model.model.ctc.log_softmax(enc_out)[0]
        greedy_ids = log_probs.argmax(dim=-1).tolist()
    return _clean_ctc_ids(greedy_ids), log_probs


def _ctc_score_tensor(lp_t: Any, in_len: Any, T: int, tgt: Any) -> float:
    import torch
    import torch.nn.functional as F

    n_tok = int(tgt.numel())
    if n_tok <= 0 or n_tok > T:
        return -999.0
    return -float(
        F.ctc_loss(
            lp_t,
            tgt,
            in_len,
            torch.tensor([n_tok], dtype=torch.long),
            blank=0,
            reduction="sum",
            zero_infinity=True,
        ).item()
    )


def _ctc_score_phrase(lp_t: Any, in_len: Any, T: int, phrase: str) -> float:
    import torch

    ids = _encode_bpe(phrase, _CF_TOK2ID) if phrase else None
    if not ids or len(ids) > T:
        return -999.0
    return _ctc_score_tensor(lp_t, in_len, T, torch.tensor(ids, dtype=torch.long))


def _compute_audio_noise_ratio(audio_f32: np.ndarray, sr: int = 16000) -> float:
    frame_len = max(1, int(sr * 0.02))
    n_frames = audio_f32.size // frame_len
    if n_frames < 6:
        return 0.0
    frames = audio_f32[: n_frames * frame_len].reshape(n_frames, frame_len)
    frame_rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    p15 = float(np.percentile(frame_rms, 15))
    p90 = float(np.percentile(frame_rms, 90))
    return p15 / max(p90, 1e-6)


def verify_light_den_tone_ctc(
    audio_f32: np.ndarray,
    transcript: str,
    *,
    sr: int = 16000,
    log_probs: Any = None,
    greedy_text: str | None = None,
    threshold: float = 0.5,
) -> tuple[str, bool]:
    """Acoustically verify Vietnamese tone 'đèn' (huyền) vs 'đen' (ngang) via ChunkFormer-CTC.

    Counteracts RNN-T LM bias that can convert spoken 'đen' (ngang tone) into 'đèn' (huyền tone)
    in light-command contexts. Returns (verified_transcript, was_flipped_to_den_ngang).
    """
    if not transcript or not re.search(r"\bđèn\b", transcript, flags=re.IGNORECASE):
        return transcript, False

    clean_huyen = re.sub(r"[?!.,;:]+$", "", transcript.strip().lower()).strip()
    clean_ngang = re.sub(r"\bđèn\b", "đen", clean_huyen)
    if clean_ngang == clean_huyen:
        return transcript, False

    if log_probs is None:
        if audio_f32 is None or audio_f32.size < 160:
            return transcript, False
        greedy_text, log_probs = decode_chunkformer_with_logprobs(audio_f32, sr=sr, pad_s=0.25)

    if log_probs is None or not _CF_TOK2ID:
        return transcript, False

    import torch

    T = int(log_probs.shape[0])
    if T < 4:
        return transcript, False
    lp_t = log_probs.unsqueeze(1)
    in_len = torch.tensor([T], dtype=torch.long)

    s_huyen = _ctc_score_phrase(lp_t, in_len, T, clean_huyen)
    s_ngang = _ctc_score_phrase(lp_t, in_len, T, clean_ngang)
    if s_huyen <= -900.0 or s_ngang <= -900.0:
        return transcript, False

    diff = s_ngang - s_huyen
    noise_ratio = _compute_audio_noise_ratio(audio_f32, sr=sr) if (audio_f32 is not None and audio_f32.size > 0) else 0.0
    greedy_has_den = bool(greedy_text and re.search(r"\bđen\b", greedy_text.lower()))

    if noise_ratio < 0.14:
        # Require ChunkFormer greedy to actually hear 'đen' (or a clear >= 2.0 tone margin)
        # so degraded speech with a weak greedy match is never false-flipped.
        if (greedy_has_den and diff >= threshold) or diff >= 2.0:
            return re.sub(r"\bđèn\b", "đen", transcript, flags=re.IGNORECASE), True
    else:
        if diff >= max(1.2, threshold + 0.7) and greedy_has_den:
            return re.sub(r"\bđèn\b", "đen", transcript, flags=re.IGNORECASE), True
    return transcript, False


def rescore_closed_command_ctc(
    log_probs: Any,
    greedy_text: str,
    *,
    expected_device: str | None = None,
    onset_gap: float = 0.0,
    high_pitch_short: bool = False,
    max_delta: float = -12.5,
    min_margin: float = 2.8,
) -> str | None:
    """Score closed-vocabulary Vietnamese smart-home commands directly on CTC posteriors.

    Returns a canonical command phrase ONLY when it beats all competitors (bare nouns,
    unsupported devices, bare verbs, confirmations, opposite polarity) by a clear acoustic margin.
    Uses length-fair bare-noun competition when greedy CTC clearly decoded an extra leading verb syllable.
    """
    if log_probs is None or not _CF_GRAMMAR_ENC:
        return None
    import torch
    from simulator.voice.vietnamese_policy import (
        _NEGATED_OR_RHETORICAL_DIRECT_RE,
        _UNSUPPORTED_DEVICE_RE,
        is_foreign_or_nonsense_input,
        strip_vi_accents,
    )

    g_norm = ""
    g_toks: list[str] = []
    g_raw_toks: list[str] = []
    if greedy_text:
        is_bad, kind = is_foreign_or_nonsense_input(greedy_text)
        if is_bad and kind == "foreign":
            return None
        if _NEGATED_OR_RHETORICAL_DIRECT_RE.search(greedy_text.lower()):
            return None
        g_raw_toks = re.sub(r"[?!.,;:]+$", "", greedy_text.strip().lower()).split()
        g_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(greedy_text.lower())).split())
        if _UNSUPPORTED_DEVICE_RE.search(f" {g_norm} "):
            return None
        g_toks = g_norm.split()
        if g_toks and g_toks[0] in ("khong", "dung", "cho", "khoi", "chua"):
            return None

    T = int(log_probs.shape[0])
    if T < 4:
        return None
    lp_t = log_probs.unsqueeze(1)
    in_len = torch.tensor([T], dtype=torch.long)

    g_sc = _ctc_score_phrase(lp_t, in_len, T, greedy_text) if greedy_text else -999.0

    best_by_kind: dict[str, tuple[str, str, float]] = {}
    for ph, kind, dev, tgt in _CF_GRAMMAR_ENC:
        if int(tgt.numel()) > T:
            continue
        if expected_device is not None:
            # When acoustic onset gap already confirmed a spoken verb precedes expected_device,
            # compare ON vs OFF for expected_device against unsupported devices & greedy fit.
            if kind.startswith("cmd:") and dev != expected_device:
                continue
            if kind in ("bare", "smalltalk", "confirm"):
                continue
        if (
            (kind == "confirm" and len(ph.split()) == 1 and (len(g_toks) >= 4 or (high_pitch_short and len(g_toks) >= 2)))
            or (kind in ("confirm", "smalltalk") and len(ph.split()) <= 2 and len(g_toks) >= 4)
        ):
            # Prevent 1-2 word confirm/smalltalk anchors from beating 4-word commands via CTC blank-skipping
            continue
        sc = _ctc_score_tensor(lp_t, in_len, T, tgt)
        prev = best_by_kind.get(kind)
        if prev is None or sc > prev[2]:
            best_by_kind[kind] = (ph, dev, sc)

    if not best_by_kind:
        return None

    ranked = sorted(best_by_kind.items(), key=lambda kv: kv[1][2], reverse=True)
    top1_kind, (top1_ph, top1_dev, top1_sc) = ranked[0]
    second_sc = ranked[1][1][2] if len(ranked) > 1 else -999.0

    if expected_device is not None:
        if not top1_kind.startswith("cmd:"):
            return None
        delta = top1_sc - g_sc
        margin = top1_sc - second_sc
        if delta >= max(-18.0, max_delta - 5.5) and margin >= 2.0:
            return top1_ph
        return None

    if top1_kind.startswith("cmd:"):
        delta = top1_sc - g_sc
        margin = top1_sc - second_sc
        eff_delta = -17.5 if high_pitch_short else max_delta
        eff_margin = 1.8 if high_pitch_short else min_margin
        if delta >= eff_delta and margin >= eff_margin:
            return top1_ph

    # Length-Fair Spoken-Verb Override & Acoustic Onset-Gap Override:
    # In CTC, a 3-word bare device noun can absorb a degraded leading spoken verb syllable as <blank>
    # frames, beating the full 4-word command by 0-3.5 log-prob. Real bare nouns have bare - cmd >= 8.0
    # and no spoken leading verb syllable.
    cmd_entries = [(k, v) for k, v in ranked if k.startswith("cmd:")]
    if cmd_entries and "bare" in best_by_kind and g_raw_toks and g_raw_toks[0] not in _NON_VERB_LEADING_TOKENS_RAW:
        best_cmd_kind, (best_cmd_ph, best_cmd_dev, best_cmd_sc) = cmd_entries[0]
        second_cmd_sc = cmd_entries[1][1][2] if len(cmd_entries) > 1 else -999.0
        bare_ph, bare_dev, bare_sc = best_by_kind["bare"]
        non_bare_negs = [v[2] for k, v in best_by_kind.items() if not k.startswith("cmd:") and k != "bare"]
        best_non_bare_neg = max(non_bare_negs) if non_bare_negs else -999.0
        bare_n_words = len(bare_ph.split())
        pol_margin = best_cmd_sc - second_cmd_sc
        neg_margin = best_cmd_sc - best_non_bare_neg
        bare_gap = bare_sc - best_cmd_sc
        cmd_delta = best_cmd_sc - g_sc

        if best_cmd_dev and best_cmd_dev == bare_dev and bare_n_words >= 2:
            bare_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(bare_ph.lower())).split())
            bare_first_tok = bare_norm.split()[0] if bare_norm else ""
            has_leading_non_device_tok = bool(
                g_toks
                and bare_first_tok
                and g_toks[0] != bare_first_tok
                and not g_norm.startswith(bare_norm)
            )
            # Case A: Greedy decoded an extra LEADING spoken verb syllable before the bare device noun
            # (never fire when greedy already starts with the device noun itself).
            if has_leading_non_device_tok and len(g_toks) >= bare_n_words + 1 and bare_gap <= 4.0:
                if pol_margin >= 2.2 and neg_margin >= 2.8 and cmd_delta >= -14.5:
                    return best_cmd_ph
                # High non-bare certainty (beats all noise/smalltalk/unsupported by >= 6.0) with clear polarity >= 1.2
                if pol_margin >= 1.2 and neg_margin >= 6.0 and cmd_delta >= -14.5:
                    return best_cmd_ph
                # Moderate noise with strong polarity >= 3.5 and tight bare gap <= 2.5
                if pol_margin >= 3.5 and neg_margin >= 3.0 and bare_gap <= 2.5 and cmd_delta >= -16.5:
                    return best_cmd_ph
            # Case B: Reverb/dropped verb where Zipformer measured strong pre-token acoustic onset_gap >= 0.14s
            # and CTC scores the full command within 1.5 log-prob of bare (real bare nouns have bare_gap >= 8.0)
            if onset_gap >= 0.14 and bare_gap <= 1.5 and pol_margin >= 3.0 and neg_margin >= 5.0 and cmd_delta >= -12.0:
                return best_cmd_ph

    return None


_TIMER_PREFIX_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # '<num> phút/giây nữa <tail>'
    (
        re.compile(
            r"^((?:\d+|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười(?:\s+(?:một|lăm|hai|ba|bốn|năm|sáu|bảy|tám|chín))?|"
            r"(?:hai|ba|bốn|năm)\s+mươi(?:\s+(?:mốt|lăm|một|hai|ba|bốn|năm|sáu|bảy|tám|chín))?)\s+"
            r"(?:phút|giây|tiếng|giờ)\s+nữa)\s+(.+)$",
            re.IGNORECASE,
        ),
        "keep",
    ),
    # 'hẹn giờ <num> giây/phút <tail>'
    (
        re.compile(
            r"^(?:hẹn\s+giờ\s+)"
            r"((?:\d+|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười(?:\s+(?:một|lăm|hai|ba|bốn|năm|sáu|bảy|tám|chín))?|"
            r"(?:hai|ba|bốn|năm|sáu)\s+mươi(?:\s+(?:mốt|lăm|một|hai|ba|bốn|năm|sáu|bảy|tám|chín))?)\s+"
            r"(?:giây|phút|tiếng|giờ))\s+(.+)$",
            re.IGNORECASE,
        ),
        "hen_gio",
    ),
    # 'sau <num> giây/phút <tail>'
    (
        re.compile(
            r"^(sau\s+(?:\d+|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười(?:\s+(?:một|lăm|hai|ba|bốn|năm|sáu|bảy|tám|chín))?)\s+"
            r"(?:giây|phút|tiếng|giờ))\s+(.+)$",
            re.IGNORECASE,
        ),
        "keep",
    ),
)


def rescore_timer_or_conditional_ctc(
    log_probs: Any,
    greedy_text: str,
) -> str | None:
    """Rescore garbled action tails on countdown timers and conditional rules ('khi ... thì ...') using CTC posteriors.

    All outputs of this function are confirmation-gated (never immediate device execution).
    """
    if log_probs is None or not greedy_text or not _CF_GRAMMAR_ENC or not _CF_TOK2ID:
        return None
    import torch
    from simulator.automation_nlu import parse_single_device_and_action
    from simulator.voice.vietnamese_policy import (
        _NEGATED_OR_RHETORICAL_DIRECT_RE,
        _UNSUPPORTED_DEVICE_RE,
        is_foreign_or_nonsense_input,
        strip_vi_accents,
    )

    low = re.sub(r"[?!.,;:]+$", "", greedy_text.strip().lower()).strip()
    if not low:
        return None
    is_bad, kind = is_foreign_or_nonsense_input(low)
    if is_bad and kind == "foreign":
        return None
    if _NEGATED_OR_RHETORICAL_DIRECT_RE.search(low):
        return None
    g_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(low)).split())
    if _UNSUPPORTED_DEVICE_RE.search(f" {g_norm} "):
        return None
    g_words = g_norm.split()
    if len(g_words) < 4:
        return None

    T = int(log_probs.shape[0])
    if T < 6:
        return None
    lp_t = log_probs.unsqueeze(1)
    in_len = torch.tensor([T], dtype=torch.long)
    g_sc = _ctc_score_phrase(lp_t, in_len, T, low)

    # 1. Countdown / Timer prefix + garbled tail rescoring
    for pat, mode in _TIMER_PREFIX_PATTERNS:
        m = pat.match(low)
        if not m:
            continue
        if mode == "hen_gio":
            raw_prefix = f"hẹn giờ {m.group(1).strip()}"
            canon_prefix = raw_prefix
            tail = m.group(2).strip()
        else:
            raw_prefix = m.group(1).strip()
            canon_prefix = raw_prefix
            tail = m.group(2).strip()
        tail_words = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(tail)).split()).split()
        if len(tail_words) < 2:
            continue
        dev0, act0 = parse_single_device_and_action(tail)
        if dev0 is not None and act0 is not None:
            return None  # Already complete

        best_by_kind: dict[str, tuple[str, str, float]] = {}
        for ph, g_kind, dev, _tgt in _CF_GRAMMAR_ENC:
            if g_kind in ("smalltalk", "confirm"):
                continue
            cand = f"{raw_prefix} {ph}"
            sc = _ctc_score_phrase(lp_t, in_len, T, cand)
            prev = best_by_kind.get(g_kind)
            if prev is None or sc > prev[2]:
                best_by_kind[g_kind] = (ph, dev, sc)

        if not best_by_kind:
            return None
        ranked = sorted(best_by_kind.items(), key=lambda kv: kv[1][2], reverse=True)
        top1_kind, (top1_ph, top1_dev, top1_sc) = ranked[0]
        second_sc = ranked[1][1][2] if len(ranked) > 1 else -999.0

        if top1_kind.startswith("cmd:") and (top1_sc - second_sc) >= 2.0 and (top1_sc - g_sc) >= -22.0:
            return f"{canon_prefix} {top1_ph}"

        # Length-fair bare override on the action tail when tail has a spoken leading verb syllable
        cmd_entries = [(k, v) for k, v in ranked if k.startswith("cmd:")]
        tail_raw_words = tail.split()
        if cmd_entries and "bare" in best_by_kind and tail_raw_words and tail_raw_words[0] not in _NON_VERB_LEADING_TOKENS_RAW:
            _ck, (best_cmd_ph, best_cmd_dev, best_cmd_sc) = cmd_entries[0]
            second_cmd_sc = cmd_entries[1][1][2] if len(cmd_entries) > 1 else -999.0
            bare_ph, bare_dev, bare_sc = best_by_kind["bare"]
            non_bare_negs = [v[2] for k, v in best_by_kind.items() if not k.startswith("cmd:") and k != "bare"]
            best_non_bare_neg = max(non_bare_negs) if non_bare_negs else -999.0
            bare_n_words = len(bare_ph.split())
            if (
                best_cmd_dev
                and best_cmd_dev == bare_dev
                and len(tail_words) >= bare_n_words + 1
                and (best_cmd_sc - second_cmd_sc) >= 1.5
                and (best_cmd_sc - best_non_bare_neg) >= 2.5
                and (bare_sc - best_cmd_sc) <= 4.5
                and (best_cmd_sc - g_sc) >= -22.0
            ):
                return f"{canon_prefix} {best_cmd_ph}"
        return None

    # 1b. Daily clock schedule ('... <hour> giờ sáng/tối ... <action>') tail rescoring
    m_clk = re.search(
        r"\b((?:\d{1,2}|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười(?:\s+(?:một|hai))?|"
        r"hai\s+mươi(?:\s+mốt)?)\s+giờ\s+(?:sáng|trưa|chiều|tối))\b",
        low,
        flags=re.IGNORECASE,
    )
    if m_clk and len(g_words) >= 6:
        clk_phrase = m_clk.group(1).strip()
        prefix_c = f"đặt lịch {clk_phrase} hằng ngày"
        neg_clk_sc = max(_ctc_score_phrase(lp_t, in_len, T, neg) for neg in _CONDITIONAL_NEG_ANCHORS)
        clk_scored: list[tuple[str, str, str, float]] = []
        for act_ph, act_dev, act_pol in _CONDITIONAL_ACTIONS:
            cand = f"{prefix_c} {act_ph}"
            clk_scored.append((cand, act_dev, act_pol, _ctc_score_phrase(lp_t, in_len, T, cand)))
        clk_scored.sort(key=lambda x: x[3], reverse=True)
        if clk_scored:
            c1, d1, p1, s1 = clk_scored[0]
            s2 = clk_scored[1][3] if len(clk_scored) > 1 else -999.0
            if (s1 - neg_clk_sc) >= 4.0 and (s1 - s2) >= 2.0 and (s1 - g_sc) >= -32.0:
                return c1

    # 2. Conditional rule ('khi ... thì ...') rescoring
    padded_g = f" {g_norm} "
    has_cond_cue = (
        len(g_words) >= 5
        and (
            " thi " in padded_g
            or g_words[0] in ("khi", "neu")
            or any(k in padded_g for k in (" dat kho ", " tieng dong ", " mo cua ", " dong cua "))
        )
    )
    if not has_cond_cue:
        return None

    # Exclude queries/custom-create/schedules that shouldn't be turned into rules
    if any(k in padded_g for k in (" nhiet do ", " do am ", " tao lenh ", " dat lich ", " hen gio ", " bao nhieu ")):
        return None

    neg_sc = max(_ctc_score_phrase(lp_t, in_len, T, neg) for neg in _CONDITIONAL_NEG_ANCHORS)
    best_rule: tuple[str, str, str, str, float] | None = None
    scores_by_trig_dev_pol: dict[tuple[str, str, str], float] = {}

    for trig_ph, trig_id in _CONDITIONAL_TRIGGERS:
        for act_ph, act_dev, act_pol in _CONDITIONAL_ACTIONS:
            cand = f"{trig_ph} thì {act_ph}"
            sc = _ctc_score_phrase(lp_t, in_len, T, cand)
            scores_by_trig_dev_pol[(trig_id, act_dev, act_pol)] = sc
            if best_rule is None or sc > best_rule[4]:
                best_rule = (cand, trig_id, act_dev, act_pol, sc)

    if best_rule is None:
        return None
    cand, trig_id, act_dev, act_pol, best_sc = best_rule
    opp_pol = "off" if act_pol == "on" else "on"
    opp_sc = scores_by_trig_dev_pol.get((trig_id, act_dev, opp_pol), -999.0)

    eff_delta = -34.0 if (len(g_words) >= 8 and (best_sc - neg_sc) >= 5.0) else -26.0
    if (best_sc - neg_sc) >= 3.5 and (best_sc - opp_sc) >= 2.0 and (best_sc - g_sc) >= eff_delta:
        return cand
    return None


def rescore_confirm_command_ctc(
    log_probs: Any,
    greedy_text: str,
) -> str | None:
    """Rescore confirmation-gated system commands (reset, factory reset, timer cancel) via CTC posteriors.

    Strictly guarded against short clips, queries, small talk, foreign speech, and unsupported devices.
    """
    if log_probs is None or not greedy_text or not _CF_CONFIRM_ENC:
        return None
    import torch
    from simulator.voice.vietnamese_policy import (
        _NEGATED_OR_RHETORICAL_DIRECT_RE,
        _UNSUPPORTED_DEVICE_RE,
        classify_small_talk_vi,
        is_foreign_or_nonsense_input,
        strip_vi_accents,
    )

    low = re.sub(r"[?!.,;:]+$", "", greedy_text.strip().lower()).strip()
    if not low:
        return None
    is_bad, kind = is_foreign_or_nonsense_input(low)
    if is_bad and kind == "foreign":
        return None
    if _NEGATED_OR_RHETORICAL_DIRECT_RE.search(low):
        return None
    if classify_small_talk_vi(low) is not None:
        return None
    g_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(low)).split())
    padded_g = f" {g_norm} "
    if _UNSUPPORTED_DEVICE_RE.search(padded_g):
        return None
    if any(k in padded_g for k in (" nhiet do ", " do am ", " cam bien ", " am thanh ", " bao nhieu ", " the nao ")):
        return None
    if not any(
        k in padded_g
        for k in (" reset ", " dat lai ", " khoi phuc ", " huy ", " xoa ", " hen gio ", " cai dat ", " lien ket ", " trang thai ")
    ):
        return None
    g_words = g_norm.split()
    if len(g_words) < 3:
        return None

    T = int(log_probs.shape[0])
    if T < 6:
        return None
    lp_t = log_probs.unsqueeze(1)
    in_len = torch.tensor([T], dtype=torch.long)
    g_sc = _ctc_score_phrase(lp_t, in_len, T, low)

    best_sys: list[tuple[str, str, float]] = []
    for canon, skind, tensors in _CF_CONFIRM_ENC:
        best_v = max(_ctc_score_tensor(lp_t, in_len, T, t) for t in tensors)
        best_sys.append((canon, skind, best_v))
    best_sys.sort(key=lambda x: x[2], reverse=True)
    top_canon, top_kind, top_sc = best_sys[0]
    second_sys_sc = best_sys[1][2] if len(best_sys) > 1 else -999.0

    # Length-matched negative anchors (4+ words when utterance has >= 4 words, preventing 3-word blank-skip bias)
    min_neg_words = 4 if len(g_words) >= 4 else 3
    neg_scores: list[float] = [_ctc_score_tensor(lp_t, in_len, T, tgt) for _ph, tgt in _CF_LONG_NEG_ENC]
    for ph, g_kind, _dev, tgt in _CF_GRAMMAR_ENC:
        if len(ph.split()) >= min_neg_words:
            neg_scores.append(_ctc_score_tensor(lp_t, in_len, T, tgt))
    best_neg_sc = max(neg_scores) if neg_scores else -999.0

    neg_margin = top_sc - best_neg_sc
    sys_margin = top_sc - second_sys_sc
    delta = top_sc - g_sc

    if neg_margin >= 3.5 and sys_margin >= 3.0 and delta >= -35.0:
        return top_canon
    return None


def rescore_sensor_query_ctc(
    log_probs: Any,
    greedy_text: str,
) -> str | None:
    """Rescore read-only Vietnamese sensor/status queries via CTC posteriors (0 device mutations possible)."""
    if log_probs is None or not greedy_text or not _CF_TOK2ID or not _CF_LONG_NEG_ENC:
        return None
    import torch
    from simulator.voice.vietnamese_policy import (
        _NEGATED_OR_RHETORICAL_DIRECT_RE,
        _UNSUPPORTED_DEVICE_RE,
        classify_small_talk_vi,
        is_foreign_or_nonsense_input,
        strip_vi_accents,
    )

    low = re.sub(r"[?!.,;:]+$", "", greedy_text.strip().lower()).strip()
    if not low:
        return None
    is_bad, kind = is_foreign_or_nonsense_input(low)
    if is_bad and kind == "foreign":
        return None
    if _NEGATED_OR_RHETORICAL_DIRECT_RE.search(low):
        return None
    if classify_small_talk_vi(low) is not None:
        return None
    g_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(low)).split())
    padded_g = f" {g_norm} "
    if _UNSUPPORTED_DEVICE_RE.search(padded_g):
        return None
    g_words = g_norm.split()
    if len(g_words) < 3:
        return None

    # Require at least one genuine Vietnamese query/sensor lexical cue
    if not any(
        k in padded_g
        for k in (
            " bao nhieu ", " the nao ", " hien tai ", " dat ", " am ",
            " cam bien ", " nhiet ", " dang ", " hay tat ", " hay dong ", " kiem tra ",
        )
    ):
        return None

    T = int(log_probs.shape[0])
    if T < 6:
        return None
    lp_t = log_probs.unsqueeze(1)
    in_len = torch.tensor([T], dtype=torch.long)
    g_sc = _ctc_score_phrase(lp_t, in_len, T, low)

    q_scored = sorted(
        [(qph, qkind, _ctc_score_phrase(lp_t, in_len, T, qph)) for qph, qkind in _SENSOR_QUERY_GRAMMAR],
        key=lambda x: x[2],
        reverse=True,
    )
    top_q, _top_k, top_sc = q_scored[0]

    neg_scores = [
        _ctc_score_tensor(lp_t, in_len, T, tgt)
        for ph, tgt in _CF_LONG_NEG_ENC
        if not any(w in ph for w in ("nhiệt độ", "độ ẩm", "cảm biến", "trạng thái"))
    ]
    best_neg_sc = max(neg_scores) if neg_scores else -999.0

    if (top_sc - best_neg_sc) >= 6.0 and (top_sc - g_sc) >= -34.0:
        return top_q
    return None


def _build_polarity_pairs() -> dict[str, tuple[tuple[str, ...], tuple[str, ...]]]:
    """Derive ON/OFF acoustic polarity comparison pairs directly from the registry-built closed grammar."""
    on_by_dev: dict[str, list[str]] = {}
    off_by_dev: dict[str, list[str]] = {}
    for phrase, kind, dev_id in _CLOSED_GRAMMAR:
        if not kind.startswith("cmd:") or not dev_id:
            continue
        act = kind.split(":", 2)[2]
        if act in ("open", "turn_on"):
            on_by_dev.setdefault(dev_id, []).append(phrase)
        elif act in ("close", "turn_off"):
            off_by_dev.setdefault(dev_id, []).append(phrase)
    return {
        dev_id: (tuple(on_by_dev.get(dev_id, ())), tuple(off_by_dev.get(dev_id, ())))
        for dev_id in set(on_by_dev) | set(off_by_dev)
        if on_by_dev.get(dev_id) and off_by_dev.get(dev_id)
    }


_POLARITY_PAIR_BY_TARGET: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = _build_polarity_pairs()


def verify_command_polarity_ctc(
    audio_f32: np.ndarray,
    target_key: str,
    claimed_polarity: str,
    *,
    sr: int = 16000,
    veto_margin: float = 1.8,
    min_confirm_margin: float | None = None,
) -> bool:
    """Return False if ChunkFormer-CTC acoustic posteriors favor the OPPOSITE polarity (or lack margin under severe noise)."""
    pairs = _POLARITY_PAIR_BY_TARGET.get(target_key)
    if not pairs or claimed_polarity not in ("on", "off"):
        return True
    _g, log_probs = decode_chunkformer_with_logprobs(audio_f32, sr=sr, pad_s=0.25)
    if log_probs is None or not _CF_TOK2ID:
        return True
    import torch
    import torch.nn.functional as F

    T = int(log_probs.shape[0])
    if T < 4:
        return True
    lp_t = log_probs.unsqueeze(1)
    in_len = torch.tensor([T], dtype=torch.long)

    def _best_score(phrases: tuple[str, ...]) -> float:
        best = -999.0
        for ph in phrases:
            ids = _encode_bpe(ph, _CF_TOK2ID)
            if not ids or len(ids) > T:
                continue
            sc = -float(
                F.ctc_loss(
                    lp_t,
                    torch.tensor(ids, dtype=torch.long),
                    in_len,
                    torch.tensor([len(ids)], dtype=torch.long),
                    blank=0,
                    reduction="sum",
                    zero_infinity=True,
                ).item()
            )
            if sc > best:
                best = sc
        return best

    on_sc = _best_score(pairs[0])
    off_sc = _best_score(pairs[1])
    if on_sc <= -900.0 or off_sc <= -900.0:
        return True
    if min_confirm_margin is not None:
        if claimed_polarity == "on" and (on_sc - off_sc) < min_confirm_margin:
            return False
        if claimed_polarity == "off" and (off_sc - on_sc) < min_confirm_margin:
            return False
    if claimed_polarity == "on" and (off_sc - on_sc) >= veto_margin:
        return False
    if claimed_polarity == "off" and (on_sc - off_sc) >= veto_margin:
        return False
    return True
