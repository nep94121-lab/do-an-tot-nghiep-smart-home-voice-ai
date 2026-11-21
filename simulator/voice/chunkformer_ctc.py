"""Fast local Vietnamese ChunkFormer-CTC decoder and closed-vocabulary acoustic rescorer."""

from __future__ import annotations

import logging
import os
import pathlib
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
_CF_FAILED: bool = False

# Closed 6-device Vietnamese command grammar + competitive bare-noun/bare-verb/unsupported/smalltalk anchors.
# Every command MUST beat all bare nouns, unsupported appliances, bare verbs, and opposite polarities in CTC log-prob.
_CLOSED_GRAMMAR: tuple[tuple[str, str, str], ...] = (
    # Main door
    ("mở cửa chính", "cmd:main_door:open", "main_door"),
    ("mở cửa", "cmd:main_door:open", "main_door"),
    ("đóng cửa chính", "cmd:main_door:close", "main_door"),
    ("đóng cửa", "cmd:main_door:close", "main_door"),
    ("khóa cửa chính", "cmd:main_door:close", "main_door"),
    ("khóa cửa", "cmd:main_door:close", "main_door"),
    ("khép cửa chính", "cmd:main_door:close", "main_door"),
    # Living room light
    ("bật đèn phòng khách", "cmd:living_room_light:turn_on", "living_room_light"),
    ("tắt đèn phòng khách", "cmd:living_room_light:turn_off", "living_room_light"),
    ("bật đèn khách", "cmd:living_room_light:turn_on", "living_room_light"),
    ("tắt đèn khách", "cmd:living_room_light:turn_off", "living_room_light"),
    # Bedroom light
    ("bật đèn phòng ngủ", "cmd:bedroom_light:turn_on", "bedroom_light"),
    ("tắt đèn phòng ngủ", "cmd:bedroom_light:turn_off", "bedroom_light"),
    ("bật đèn ngủ", "cmd:bedroom_light:turn_on", "bedroom_light"),
    ("tắt đèn ngủ", "cmd:bedroom_light:turn_off", "bedroom_light"),
    ("bật đèn buồng", "cmd:bedroom_light:turn_on", "bedroom_light"),
    ("tắt đèn buồng", "cmd:bedroom_light:turn_off", "bedroom_light"),
    # All lights
    ("bật tất cả đèn", "cmd:all_lights:turn_on", "all_lights"),
    ("tắt tất cả đèn", "cmd:all_lights:turn_off", "all_lights"),
    ("bật hết đèn", "cmd:all_lights:turn_on", "all_lights"),
    ("tắt hết đèn", "cmd:all_lights:turn_off", "all_lights"),
    # Garden pump
    ("bật máy bơm", "cmd:garden_pump:turn_on", "garden_pump"),
    ("tắt máy bơm", "cmd:garden_pump:turn_off", "garden_pump"),
    ("bật máy bơm tưới cây", "cmd:garden_pump:turn_on", "garden_pump"),
    ("tắt máy bơm tưới cây", "cmd:garden_pump:turn_off", "garden_pump"),
    ("bật bơm", "cmd:garden_pump:turn_on", "garden_pump"),
    ("tắt bơm", "cmd:garden_pump:turn_off", "garden_pump"),
    ("dừng tưới vườn", "cmd:garden_pump:turn_off", "garden_pump"),
    # Alarm siren
    ("bật còi báo động", "cmd:alarm_siren:turn_on", "alarm_siren"),
    ("tắt còi báo động", "cmd:alarm_siren:turn_off", "alarm_siren"),
    ("bật còi", "cmd:alarm_siren:turn_on", "alarm_siren"),
    ("tắt còi", "cmd:alarm_siren:turn_off", "alarm_siren"),
    ("bật còi hú", "cmd:alarm_siren:turn_on", "alarm_siren"),
    ("tắt còi hú", "cmd:alarm_siren:turn_off", "alarm_siren"),
    # Speaker amp
    ("bật nguồn mạch loa", "cmd:speaker_amp:turn_on", "speaker_amp"),
    ("tắt nguồn mạch loa", "cmd:speaker_amp:turn_off", "speaker_amp"),
    ("bật loa", "cmd:speaker_amp:turn_on", "speaker_amp"),
    ("tắt loa", "cmd:speaker_amp:turn_off", "speaker_amp"),
    # All devices
    ("bật tất cả thiết bị", "cmd:all_devices:turn_on", "all_devices"),
    ("tắt tất cả thiết bị", "cmd:all_devices:turn_off", "all_devices"),
    # Competitive negative anchors (never executed; prevent false positives)
    ("cửa chính", "bare", "main_door"),
    ("đèn phòng khách", "bare", "living_room_light"),
    ("đèn phòng ngủ", "bare", "bedroom_light"),
    ("tất cả đèn", "bare", "all_lights"),
    ("máy bơm", "bare", "garden_pump"),
    ("còi báo động", "bare", "alarm_siren"),
    ("nguồn mạch loa", "bare", "speaker_amp"),
    ("tất cả thiết bị", "bare", "all_devices"),
    ("bật lên đi", "bare", ""),
    ("tắt đi", "bare", ""),
    ("mở đi", "bare", ""),
    ("đóng đi", "bare", ""),
    ("bật quạt trần", "unsupported", ""),
    ("tắt điều hòa", "unsupported", ""),
    ("mở tivi", "unsupported", ""),
    ("bật máy giặt", "unsupported", ""),
    ("đóng rèm cửa", "unsupported", ""),
    ("bật bình nóng lạnh", "unsupported", ""),
    ("học lệnh hồng ngoại", "unsupported", ""),
    ("mở cửa cuốn", "unsupported", ""),
    ("chào bạn", "smalltalk", ""),
    ("xin chào", "smalltalk", ""),
    ("tạm biệt bạn", "smalltalk", ""),
    ("tốt lắm", "smalltalk", ""),
    ("ok", "confirm", ""),
    ("được", "confirm", ""),
    ("đồng ý", "confirm", ""),
    ("không", "confirm", ""),
    ("thôi", "confirm", ""),
    ("hủy", "confirm", ""),
)


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
    global _CF_MODEL, _CF_ID2TOK, _CF_TOK2ID, _CF_GRAMMAR_ENC, _CF_FAILED
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

            num_threads = max(1, int(os.environ.get("SMARTHOME_STT_THREADS", "8") or "8"))
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

            _CF_ID2TOK = id2tok
            _CF_TOK2ID = tok2id
            _CF_GRAMMAR_ENC = grammar_enc
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


def rescore_closed_command_ctc(
    log_probs: Any,
    greedy_text: str,
    *,
    expected_device: str | None = None,
    max_delta: float = -12.5,
    min_margin: float = 2.8,
) -> str | None:
    """Score closed-vocabulary Vietnamese smart-home commands directly on CTC posteriors.

    Returns a canonical command phrase ONLY when it beats all competitors (bare nouns,
    unsupported devices, bare verbs, confirmations, opposite polarity) by a clear acoustic margin.
    """
    if log_probs is None or not _CF_GRAMMAR_ENC:
        return None
    import torch
    import torch.nn.functional as F
    from simulator.voice.vietnamese_policy import (
        _UNSUPPORTED_DEVICE_RE,
        is_foreign_or_nonsense_input,
        strip_vi_accents,
    )

    if greedy_text:
        is_bad, kind = is_foreign_or_nonsense_input(greedy_text)
        if is_bad and kind == "foreign":
            return None
        g_norm = " ".join(strip_vi_accents(greedy_text.lower()).split())
        if _UNSUPPORTED_DEVICE_RE.search(f" {g_norm} "):
            return None

    T = int(log_probs.shape[0])
    if T < 4:
        return None
    lp_t = log_probs.unsqueeze(1)
    in_len = torch.tensor([T], dtype=torch.long)

    g_ids = _encode_bpe(greedy_text, _CF_TOK2ID) if greedy_text else None
    if g_ids and len(g_ids) <= T:
        g_sc = -float(
            F.ctc_loss(
                lp_t,
                torch.tensor(g_ids, dtype=torch.long),
                in_len,
                torch.tensor([len(g_ids)], dtype=torch.long),
                blank=0,
                reduction="sum",
                zero_infinity=True,
            ).item()
        )
    else:
        g_sc = -999.0

    best_by_kind: dict[str, tuple[str, float]] = {}
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
        sc = -float(
            F.ctc_loss(
                lp_t,
                tgt,
                in_len,
                torch.tensor([int(tgt.numel())], dtype=torch.long),
                blank=0,
                reduction="sum",
                zero_infinity=True,
            ).item()
        )
        prev = best_by_kind.get(kind)
        if prev is None or sc > prev[1]:
            best_by_kind[kind] = (ph, sc)

    if not best_by_kind:
        return None

    ranked = sorted(best_by_kind.items(), key=lambda kv: kv[1][1], reverse=True)
    top1_kind, (top1_ph, top1_sc) = ranked[0]
    if not top1_kind.startswith("cmd:"):
        return None

    second_sc = ranked[1][1][1] if len(ranked) > 1 else -999.0
    delta = top1_sc - g_sc
    margin = top1_sc - second_sc

    if expected_device is not None:
        if delta >= max(-18.0, max_delta - 5.5) and margin >= 2.0:
            return top1_ph
        return None

    if delta >= max_delta and margin >= min_margin:
        return top1_ph
    return None
