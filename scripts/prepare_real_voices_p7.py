"""Script tai va chuan bi du lieu giong noi nguoi that (REAL Human Speech - NOT TTS)
tu bo du lieu Mozilla Common Voice vi / VIVOS / FOSD cho Phase 7 Voice Auth 3 Levels.

Luu file WAV 16kHz mono PCM vao C:/Users/LENOVO/datn-wt/voices/ va trich xuat
van giong sinh trac hoc (Stage 1 26D, Stage 2 64D, Neural 256D, SHA-256) vao
simulator/voice/real_voices_signatures.json de Vercel Serverless nhan dien tuc thi.
"""

from __future__ import annotations

import glob
import hashlib
import io
import json
import pathlib
import sys
import urllib.request
import wave
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.voice.biometrics_neural import extract_neural_embedding_256d
from simulator.voice.dsp_features import (
    denoise_and_isolate_human_voice,
    extract_stage2_deep_features,
    extract_voice_features,
)
from simulator.voice.enrollment_quality import validate_voice_enrollment_quality

VOICES_DIR = pathlib.Path(r"C:\Users\LENOVO\datn-wt\voices")
SIGNATURES_JSON_PATH = ROOT / "simulator" / "voice" / "real_voices_signatures.json"

DATASET_ID = "tuanmanh28/VIVOS_CommonVoice_FOSD_CleanControl_dataset"

# Danh sach mau giong nguoi that (2 nguoi noi khac nhau: Speaker A Nu F0~274Hz, Speaker B Nam F0~131Hz)
REAL_SPEECH_SPECS: list[dict[str, Any]] = [
    # Level 2: Thanh vien gia dinh (Tier 2 - Speaker A: Nu, F0 ~ 260-284 Hz)
    {
        "filename": "level2_family.wav",
        "level": 2,
        "tier": 2,
        "speaker_id": "user_voice_thanh_vien_a",
        "user_id": "thanh_vien_a",
        "speaker_name": "Thành viên A (Cấp 2 - VIVOS/CommonVoice/FOSD Speaker A)",
        "role": "MEMBER",
        "split": "test",
        "row_idx": 4718,
        "command_key": "enroll_reference",
        "canonical_command": "bật quạt phòng khách",
        "expected_dataset_text": "quạt phòng khách ba bật",
    },
    {
        "filename": "level2_bat_den_phong_khach.wav",
        "level": 2,
        "tier": 2,
        "speaker_id": "user_voice_thanh_vien_a",
        "user_id": "thanh_vien_a",
        "speaker_name": "Thành viên A (Cấp 2 - VIVOS/CommonVoice/FOSD Speaker A)",
        "role": "MEMBER",
        "split": "test",
        "row_idx": 4704,
        "command_key": "bat_den_phong_khach",
        "canonical_command": "bật đèn phòng khách",
        "expected_dataset_text": "đèn phòng khách ba bật",
    },
    {
        "filename": "level2_tat_quat.wav",
        "level": 2,
        "tier": 2,
        "speaker_id": "user_voice_thanh_vien_a",
        "user_id": "thanh_vien_a",
        "speaker_name": "Thành viên A (Cấp 2 - VIVOS/CommonVoice/FOSD Speaker A)",
        "role": "MEMBER",
        "split": "test",
        "row_idx": 4727,
        "command_key": "tat_quat",
        "canonical_command": "tắt quạt",
        "expected_dataset_text": "quạt phòng khách hai tắt",
    },
    {
        "filename": "level2_mo_cua_chinh.wav",
        "level": 2,
        "tier": 2,
        "speaker_id": "user_voice_thanh_vien_a",
        "user_id": "thanh_vien_a",
        "speaker_name": "Thành viên A (Cấp 2 - VIVOS/CommonVoice/FOSD Speaker A)",
        "role": "MEMBER",
        "split": "test",
        "row_idx": 4702,
        "command_key": "mo_cua_chinh",
        "canonical_command": "mở cửa chính",
        "expected_dataset_text": "công tắc cổng hai bật",
    },
    # Level 3: Khach (Tier 3 - Speaker B: Nam, F0 ~ 122-139 Hz, khac han Speaker A va Chu nha)
    {
        "filename": "level3_guest.wav",
        "level": 3,
        "tier": 3,
        "speaker_id": "user_voice_khach_c",
        "user_id": "khach_c",
        "speaker_name": "Khách C (Cấp 3 - VIVOS/CommonVoice/FOSD Speaker B)",
        "role": "GUEST",
        "split": "test",
        "row_idx": 4749,
        "command_key": "enroll_reference",
        "canonical_command": "bật quạt phòng khách",
        "expected_dataset_text": "quạt phòng khách một bật",
    },
    {
        "filename": "level3_bat_den_phong_khach.wav",
        "level": 3,
        "tier": 3,
        "speaker_id": "user_voice_khach_c",
        "user_id": "khach_c",
        "speaker_name": "Khách C (Cấp 3 - VIVOS/CommonVoice/FOSD Speaker B)",
        "role": "GUEST",
        "split": "test",
        "row_idx": 4927,
        "command_key": "bat_den_phong_khach",
        "canonical_command": "bật đèn phòng khách",
        "expected_dataset_text": "đèn phòng khách bốn bật",
    },
    {
        "filename": "level3_tat_quat.wav",
        "level": 3,
        "tier": 3,
        "speaker_id": "user_voice_khach_c",
        "user_id": "khach_c",
        "speaker_name": "Khách C (Cấp 3 - VIVOS/CommonVoice/FOSD Speaker B)",
        "role": "GUEST",
        "split": "test",
        "row_idx": 4735,
        "command_key": "tat_quat",
        "canonical_command": "tắt quạt",
        "expected_dataset_text": "quạt phòng khách một tắt",
    },
    {
        "filename": "level3_mo_cua_chinh.wav",
        "level": 3,
        "tier": 3,
        "speaker_id": "user_voice_khach_c",
        "user_id": "khach_c",
        "speaker_name": "Khách C (Cấp 3 - VIVOS/CommonVoice/FOSD Speaker B)",
        "role": "GUEST",
        "split": "test",
        "row_idx": 4799,
        "command_key": "mo_cua_chinh",
        "canonical_command": "mở cửa chính",
        "expected_dataset_text": "công tắc cổng hai bật",
    },
]


def fetch_dataset_row(split: str, row_idx: int) -> dict[str, Any]:
    url = (
        f"https://datasets-server.huggingface.co/rows?"
        f"dataset={DATASET_ID}&config=default&split={split}&offset={row_idx}&length=1"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    rows = data.get("rows", [])
    if not rows:
        raise RuntimeError(f"Khong tim thay row {split}[{row_idx}] tren HuggingFace datasets-server")
    return rows[0]["row"]


def read_wav_pcm16k(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        ch = wf.getnchannels()
        sr = wf.getframerate()
        sw = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())
    if sw == 2:
        pcm = np.frombuffer(raw, dtype=np.int16)
    elif sw == 4:
        pcm = (np.frombuffer(raw, dtype=np.int32) >> 16).astype(np.int16)
    else:
        pcm = ((np.frombuffer(raw, dtype=np.uint8).astype(np.int16) - 128) << 8).astype(np.int16)
    if ch > 1:
        pcm = pcm.reshape(-1, ch).mean(axis=1).astype(np.int16)
    if sr != 16000 and pcm.size > 0:
        dur = pcm.size / float(sr)
        target_len = int(round(dur * 16000))
        x_old = np.linspace(0.0, 1.0, num=pcm.size, endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=target_len, endpoint=False)
        pcm = np.interp(x_new, x_old, pcm.astype(np.float32)).astype(np.int16)
        sr = 16000
    return pcm, sr


def encode_wav_16k_mono(pcm16: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(pcm16.astype(np.int16).tobytes())
    return buf.getvalue()


def compute_audio_signature(
    pcm16: np.ndarray,
    *,
    level: int,
    tier: int,
    speaker_id: str,
    user_id: str,
    speaker_name: str,
    role: str,
    command_key: str,
    recognized_text: str,
    canonical_command: str,
    source_label: str,
    filename: str,
    wav_bytes: bytes,
) -> dict[str, Any]:
    pcm_clean, _ = denoise_and_isolate_human_voice(pcm16, 16000)
    feat_s1 = extract_voice_features(pcm_clean, 16000)
    feat_s2 = extract_stage2_deep_features(pcm_clean, 16000)
    emb_256 = extract_neural_embedding_256d(pcm_clean, 16000)
    qual = validate_voice_enrollment_quality(pcm16, 16000)

    pcm_sha256 = hashlib.sha256(pcm16.astype(np.int16).tobytes()).hexdigest()
    wav_sha256 = hashlib.sha256(wav_bytes).hexdigest()

    return {
        "filename": filename,
        "level": int(level),
        "tier": int(tier),
        "speaker_id": speaker_id,
        "user_id": user_id,
        "speaker_name": speaker_name,
        "role": role,
        "command_key": command_key,
        "recognized_text": recognized_text,
        "canonical_command": canonical_command,
        "source": source_label,
        "duration_sec": round(float(pcm16.size / 16000.0), 3),
        "f0_hz": round(float(qual.get("f0_hz") or feat_s1.get("f0_hz") or 0.0), 1),
        "centroid_hz": round(float(feat_s1.get("centroid_hz") or 0.0), 1),
        "snr_db": round(float(qual.get("snr_db") or 0.0), 1),
        "quality_ok": bool(qual.get("ok", False)),
        "wav_sha256": wav_sha256,
        "pcm_sha256": pcm_sha256,
        "embedding": [round(float(x), 5) for x in feat_s1.get("embedding", [])],
        "deep_embedding": [round(float(x), 5) for x in feat_s2.get("deep_embedding", [])],
        "formants_hz": [round(float(x), 1) for x in feat_s2.get("formants_hz", [])],
        "embedding_256d": [round(float(x), 5) for x in emb_256],
    }


def resolve_level1_owner_files() -> dict[str, Any]:
    """Kiem tra C:/Users/LENOVO/datn-wt/voices/level1_owner.* va C:/Users/LENOVO/datn-wt/voices/level1_commands/*.wav."""
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    matches = sorted(glob.glob(str(VOICES_DIR / "level1_owner.*")))
    l1_cmd_dir = VOICES_DIR / "level1_commands"
    sep_dir = l1_cmd_dir if l1_cmd_dir.exists() else (ROOT / "test_audio" / "cac_cau_lenh_cua_sep")
    enroll_path = (
        pathlib.Path(matches[0])
        if matches
        else (ROOT / "test_audio" / "giong_chu_nha_cap1_tuan_anh.wav")
    )
    return {
        "custom_owner_file_present": bool(matches),
        "owner_enroll_path": str(enroll_path),
        "commands_dir": str(sep_dir),
        "commands": {
            "cau_1_xin_chao_chu_nha_cap1": str(sep_dir / "cau_1_xin_chao_chu_nha_cap1.wav"),
            "cau_2_mo_cua_chinh": str(sep_dir / "cau_2_mo_cua_chinh.wav"),
            "cau_3_dong_cua_chinh": str(sep_dir / "cau_3_dong_cua_chinh.wav"),
            "cau_4_bat_den_phong_khach": str(sep_dir / "cau_4_bat_den_phong_khach.wav"),
            "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu": str(sep_dir / "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav"),
            "cau_6_tat_het_den": str(sep_dir / "cau_6_tat_het_den.wav"),
            "cau_7_dong_het_cua": str(sep_dir / "cau_7_dong_het_cua.wav"),
        },
    }


def main() -> int:
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    signatures: list[dict[str, Any]] = []

    # 1. Nap (hoac tai neu thieu) 8 file WAV giong nguoi that cho Level 2 (Speaker A) va Level 3 (Speaker B)
    for spec in REAL_SPEECH_SPECS:
        target_path = VOICES_DIR / spec["filename"]
        if target_path.exists() and target_path.stat().st_size > 1000:
            clean_wav = target_path.read_bytes()
            pcm16, _ = read_wav_pcm16k(clean_wav)
            raw_text = spec["expected_dataset_text"]
            print(f"[Cached Real Speech] {target_path.name} ({DATASET_ID} {spec['split']}[{spec['row_idx']}])")
        else:
            print(f"[Download] {DATASET_ID} {spec['split']}[{spec['row_idx']}] -> {target_path.name}")
            row = fetch_dataset_row(spec["split"], spec["row_idx"])
            raw_text = (row.get("text") or "").strip()
            audio_url = row["audio"][0]["src"]
            req = urllib.request.Request(audio_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                raw_wav = resp.read()
            pcm16, _ = read_wav_pcm16k(raw_wav)
            clean_wav = encode_wav_16k_mono(pcm16)
            target_path.write_bytes(clean_wav)

        sig = compute_audio_signature(
            pcm16,
            level=spec["level"],
            tier=spec["tier"],
            speaker_id=spec["speaker_id"],
            user_id=spec["user_id"],
            speaker_name=spec["speaker_name"],
            role=spec["role"],
            command_key=spec["command_key"],
            recognized_text=raw_text,
            canonical_command=spec["canonical_command"],
            source_label=f"{DATASET_ID}:{spec['split']}[{spec['row_idx']}]",
            filename=spec["filename"],
            wav_bytes=clean_wav,
        )
        if not sig["quality_ok"]:
            raise RuntimeError(f"File {spec['filename']} khong dat chuan giong nguoi that: {sig}")
        signatures.append(sig)
        print(
            f"  -> OK: f0={sig['f0_hz']}Hz, dur={sig['duration_sec']}s, "
            f"text={raw_text!r} (canonical={spec['canonical_command']!r})"
        )

    # 2. Trich xuat van giong cho Level 1 (Owner - level1_owner.wav + 7 clip trong level1_commands/)
    l1_info = resolve_level1_owner_files()
    l1_cmd_dir = VOICES_DIR / "level1_commands"
    sep_dir = l1_cmd_dir if l1_cmd_dir.exists() else (ROOT / "test_audio" / "cac_cau_lenh_cua_sep")
    l1_command_meta: list[tuple[str, str, str, str]] = [
        (
            "enroll_level1_owner",
            str(VOICES_DIR / "level1_owner.wav"),
            "Xin chào ngôi nhà thông minh, tôi là Nguyễn Tuấn Anh, chủ nhà.",
            "bật đèn phòng khách",
        ),
        (
            "cau_1_xin_chao_chu_nha_cap1",
            str(sep_dir / "cau_1_xin_chao_chu_nha_cap1.wav"),
            "Xin chào ngôi nhà thông minh, tôi là Nguyễn Tuấn Anh, chủ nhà.",
            "xin chào chủ nhà cấp 1",
        ),
        (
            "cau_2_mo_cua_chinh",
            str(sep_dir / "cau_2_mo_cua_chinh.wav"),
            "Mở cửa chính.",
            "mở cửa chính",
        ),
        (
            "cau_3_dong_cua_chinh",
            str(sep_dir / "cau_3_dong_cua_chinh.wav"),
            "Đóng cửa chính.",
            "đóng cửa chính",
        ),
        (
            "cau_4_bat_den_phong_khach",
            str(sep_dir / "cau_4_bat_den_phong_khach.wav"),
            "Bật đèn phòng khách.",
            "bật đèn phòng khách",
        ),
        (
            "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu",
            str(sep_dir / "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav"),
            "Bật quạt trần và điều hòa.",
            "bật quạt trần và điều hòa",
        ),
        (
            "cau_6_tat_het_den",
            str(sep_dir / "cau_6_tat_het_den.wav"),
            "Tắt hết đèn.",
            "tắt hết đèn",
        ),
        (
            "cau_7_dong_het_cua",
            str(sep_dir / "cau_7_dong_het_cua.wav"),
            "Đóng hết cửa.",
            "đóng hết cửa",
        ),
    ]
    seen_l1_files: set[tuple[str, str]] = set()
    for cmd_key, fpath_str, rec_text, canon_cmd in l1_command_meta:
        fpath = pathlib.Path(fpath_str)
        if not fpath.exists() or (cmd_key, str(fpath)) in seen_l1_files:
            continue
        seen_l1_files.add((cmd_key, str(fpath)))
        wav_bytes = fpath.read_bytes()
        pcm16, _ = read_wav_pcm16k(wav_bytes)
        sig = compute_audio_signature(
            pcm16,
            level=1,
            tier=1,
            speaker_id="owner_voice_1",
            user_id="tuan_anh",
            speaker_name="Chủ nhà Nguyễn Tuấn Anh (Cấp 1)",
            role="ADMIN",
            command_key=cmd_key,
            recognized_text=rec_text,
            canonical_command=canon_cmd,
            source_label=f"owner_real_voice:{fpath.name}",
            filename=fpath.name,
            wav_bytes=wav_bytes,
        )
        signatures.append(sig)
        print(f"[Level 1] {fpath.name}: f0={sig['f0_hz']}Hz, dur={sig['duration_sec']}s, cmd={canon_cmd!r}")

    # Kiem tra 2 nguoi noi Level 2 va Level 3 khac nhau ro ret
    l2_f0s = [s["f0_hz"] for s in signatures if s["level"] == 2]
    l3_f0s = [s["f0_hz"] for s in signatures if s["level"] == 3]
    mean_l2_f0 = float(np.mean(l2_f0s))
    mean_l3_f0 = float(np.mean(l3_f0s))
    print(f"[Verify Speakers] Level 2 Mean F0 = {mean_l2_f0:.1f}Hz vs Level 3 Mean F0 = {mean_l3_f0:.1f}Hz (Diff = {abs(mean_l2_f0 - mean_l3_f0):.1f}Hz)")
    assert abs(mean_l2_f0 - mean_l3_f0) >= 80.0, "Level 2 va Level 3 phai la 2 nguoi noi khac nhau!"

    payload = {
        "dataset_source": DATASET_ID,
        "voices_dir": str(VOICES_DIR),
        "level1_owner_hook": l1_info,
        "speaker_summary": {
            "level1": {
                "tier": 1,
                "speaker_id": "owner_voice_1",
                "user_id": "tuan_anh",
                "name": "Chủ nhà Nguyễn Tuấn Anh (Cấp 1)",
                "custom_file_glob": r"C:\Users\LENOVO\datn-wt\voices\level1_owner.*",
            },
            "level2": {
                "tier": 2,
                "speaker_id": "user_voice_thanh_vien_a",
                "user_id": "thanh_vien_a",
                "name": "Thành viên A (Cấp 2 - VIVOS/CommonVoice/FOSD Speaker A)",
                "mean_f0_hz": round(mean_l2_f0, 1),
            },
            "level3": {
                "tier": 3,
                "speaker_id": "user_voice_khach_c",
                "user_id": "khach_c",
                "name": "Khách C (Cấp 3 - VIVOS/CommonVoice/FOSD Speaker B)",
                "mean_f0_hz": round(mean_l3_f0, 1),
            },
        },
        "signatures": signatures,
    }

    manifest_out = VOICES_DIR / "manifest_voices.json"
    manifest_out.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    SIGNATURES_JSON_PATH.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"[Done] Saved {manifest_out} and {SIGNATURES_JSON_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
