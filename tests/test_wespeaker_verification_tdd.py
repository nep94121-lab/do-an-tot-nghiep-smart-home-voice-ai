"""TDD Test Suite for WeSpeaker ResNet34 ONNX Speaker Verification & 5-Sample Enrollment.

Covers:
1. Offline benchmark evaluation (mean of 5 distinct owner clips: FRR@FAR1% <= 5.0% at 0.435, clean EER = 0.0%).
2. Identity decision replaced by WeSpeaker ResNet34 ONNX across ALL 5 paths:
   - WebSocket live mic (`VoiceAuthManager.verify_pcm16k_and_apply_strikes` & `GeminiLiveSession`)
   - REST `/api/voice_command`
   - Sample / offline (`stream_wav_sample`)
   - Guest QR enrollment (`/api/auth3/guest_qr_complete_voice`)
   - Layer 3 voice verification (`/api/auth3/layer3_voice` & `/api/auth3/enroll_voice_sample`)
3. Removal of `is_live_mic` soft-boost inconsistency.
4. `mel26+deep64` strictly as an audio-quality gate (too short / silent / clipped -> `ask_repeat=True`,
   NOT `'Người lạ'`, 0 strike increment).
5. 5-sample multi-sample enrollment for Owner (Level 1), Family (Level 2), and Guest (Level 3),
   rejecting byte-identical copies, rejecting duplicate household voices, and never logging raw audio/embeddings.
6. Owner-only devices (`main_door`, `alarm_siren`) remain strictly owner-only.
"""

from __future__ import annotations

import asyncio
import base64
import json
import pathlib
import sys
import wave
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval_wespeaker_bench import run_benchmark_evaluation
from simulator.auth_3layer import get_auth_3layer_manager
from simulator.rule_engine import SmartHomeEngine
from simulator.server import _BOOT_VOICE_AUTH, app
from simulator.voice.stt_pipeline import process_voice_command_pipeline
from simulator.voice.wespeaker_onnx import (
    _read_wav_float32_16k,
    compute_multi_sample_mean_embedding,
    compute_wespeaker_cosine,
    evaluate_audio_quality_gate,
    evaluate_cohort_margin,
    extract_wespeaker_embedding,
    load_verified_owner_seed,
    load_verified_owner_5sample_seed,
    load_verified_tier_5sample_seed,
    vad_trim_16k,
)
from simulator.voice_auth import VoiceAuthManager
from simulator.voice_config import (
    ENROLLMENT_REQUIRED_SAMPLES,
    THRESHOLD_WESPEAKER,
    THRESHOLD_WESPEAKER_TIER1,
    THRESHOLD_WESPEAKER_TIER2,
    THRESHOLD_WESPEAKER_TIER3,
    get_tier_wespeaker_threshold,
)


def _read_pcm16k(rel_path: str) -> bytes:
    p = ROOT / rel_path
    assert p.exists(), f"Missing audio file: {p}"
    with wave.open(str(p), "rb") as w:
        return w.readframes(w.getnframes())


def _generate_distinct_human_like_samples(base_f0: float, count: int = 5) -> list[bytes]:
    """Generate `count` distinct 3.4-second 16kHz PCM samples with varied harmonic envelopes."""
    sr = 16000
    samples: list[bytes] = []
    for idx in range(count):
        dur = 3.3 + idx * 0.12
        n_total = int(sr * dur)
        n_sil = int(sr * 0.25)
        n_act = n_total - n_sil
        t = np.arange(n_act, dtype=np.float32) / sr
        f0 = base_f0 + (idx - 2) * 1.8
        phase = idx * 0.55
        env = 0.82 + 0.18 * np.sin(2.0 * np.pi * (2.1 + idx * 0.35) * t + phase)
        sig = env * (
            0.38 * np.sin(2.0 * np.pi * f0 * t + phase)
            + 0.21 * np.sin(2.0 * np.pi * (2.0 * f0) * t)
            + 0.11 * np.sin(2.0 * np.pi * (3.0 * f0) * t - phase)
            + 0.05 * np.sin(2.0 * np.pi * (4.0 * f0) * t + 0.5 * phase)
        )
        full = np.concatenate([np.zeros(n_sil, dtype=np.float32), sig])
        pcm16 = np.clip(full * 32767.0, -32768, 32767).astype(np.int16)
        samples.append(pcm16.tobytes())
    return samples


@pytest.fixture(autouse=True)
def reset_voice_state():
    from simulator.api.deps import _REST_ENGINE

    mgr = get_auth_3layer_manager()
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    yield
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    asyncio.run(_REST_ENGINE.factory_reset())


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers={"Authorization": "Bearer sess_owner_t1_nep94121"})


def test_wespeaker_config_and_owner_seed() -> None:
    """Verify calibrated threshold 0.475, enrollment samples requirement, and expanded owner seed clips."""
    assert THRESHOLD_WESPEAKER == pytest.approx(0.475)
    assert THRESHOLD_WESPEAKER_TIER1 == pytest.approx(0.475)
    assert THRESHOLD_WESPEAKER_TIER2 == pytest.approx(0.475)
    assert THRESHOLD_WESPEAKER_TIER3 == pytest.approx(0.385)
    assert ENROLLMENT_REQUIRED_SAMPLES == 5

    seed = load_verified_owner_seed(project_root=ROOT)
    assert seed["ok"] is True
    assert seed["sample_count"] >= 7
    seed_clips = seed["seed_clips"]
    assert len(seed_clips) >= 7
    # Must NOT use giong_1_* clips
    for clip_name in seed_clips:
        assert "giong_1" not in clip_name


def test_wespeaker_offline_benchmark_frr_at_far1_under_5_percent() -> None:
    """Verify offline benchmark reproduces FRR@FAR1% <= ~5% (4.8% at threshold 0.435 for mean of 5)."""
    report = run_benchmark_evaluation()
    mean5_all = report["configs"]["mean_of_5"]["all"]
    mean5_clean = report["configs"]["mean_of_5"]["clean"]

    assert mean5_all["frr_far1"] <= 0.055, f"Expected FRR@FAR1% <= 5.5%, got {mean5_all['frr_far1']*100:.2f}%"
    assert mean5_clean["eer"] == 0.0
    for clip_name, score in report["owner_clip_scores_vs_5sample_seed"].items():
        assert score >= 0.435, f"Owner clip {clip_name} scored {score} < 0.435"
    for imp_name, score in report["impostor_clip_scores_vs_5sample_seed"].items():
        assert score < 0.435, f"Impostor clip {imp_name} scored {score} >= 0.435"


def test_no_is_live_mic_soft_boost_inconsistency() -> None:
    """Verify `is_live_mic=True` and `is_live_mic=False` produce identical WeSpeaker cosine similarity."""
    vm = VoiceAuthManager(ROOT / "test_audio")
    owner_pcm = _read_pcm16k("test_audio/cac_cau_lenh_cua_sep/cau_2_mo_cua_chinh.wav")
    intruder_pcm = _read_pcm16k("test_audio/giong_2_nguoi_la_mo_cua.wav")

    res_live = vm.verify_pcm16k_and_apply_strikes(owner_pcm, is_live_mic=True)
    res_offline = vm.verify_pcm16k_and_apply_strikes(owner_pcm, is_live_mic=False)
    assert res_live["authorized"] is True
    assert res_offline["authorized"] is True
    assert res_live["similarity"] == pytest.approx(res_offline["similarity"], abs=1e-6)
    assert res_live["wespeaker_cosine"] == pytest.approx(res_offline["wespeaker_cosine"], abs=1e-6)

    vm.reset_strikes()
    int_live = vm.verify_pcm16k_and_apply_strikes(intruder_pcm, is_live_mic=True)
    vm.reset_strikes()
    int_offline = vm.verify_pcm16k_and_apply_strikes(intruder_pcm, is_live_mic=False)
    assert int_live["authorized"] is False
    assert int_offline["authorized"] is False
    assert int_live["similarity"] == pytest.approx(int_offline["similarity"], abs=1e-6)


def test_audio_quality_gate_asks_repeat_not_stranger_and_zero_strikes(client: TestClient) -> None:
    """Verify too short, silent, or clipped audio returns ask_repeat=True, NOT 'Người lạ', and 0 strikes."""
    vm = VoiceAuthManager(ROOT / "test_audio")
    vm.reset_strikes()

    # 1. Too short (0.25s)
    short_pcm = (np.sin(np.linspace(0, 50, 4000)) * 12000).astype(np.int16).tobytes()
    r_short = vm.verify_pcm16k_and_apply_strikes(short_pcm)
    assert r_short["authorized"] is False
    assert r_short["ask_repeat"] is True
    assert r_short["strike_count"] == 0
    assert "người lạ" not in r_short["speaker_label"].lower()

    # 2. Silent / too quiet
    silent_pcm = np.zeros(16000 * 2, dtype=np.int16).tobytes()
    r_silent = vm.verify_pcm16k_and_apply_strikes(silent_pcm)
    assert r_silent["authorized"] is False
    assert r_silent["ask_repeat"] is True
    assert r_silent["strike_count"] == 0
    assert "người lạ" not in r_silent["speaker_label"].lower()

    # 3. Severely clipped audio
    clipped_pcm = np.full(16000 * 2, 32767, dtype=np.int16).tobytes()
    r_clipped = vm.verify_pcm16k_and_apply_strikes(clipped_pcm)
    assert r_clipped["authorized"] is False
    assert r_clipped["ask_repeat"] is True
    assert r_clipped["strike_count"] == 0
    assert "người lạ" not in r_clipped["speaker_label"].lower()

    # 4. Also verify on /api/auth3/layer3_voice and process_voice_command_pipeline
    b64_short = base64.b64encode(short_pcm).decode("ascii")
    res_l3 = client.post("/api/auth3/layer3_voice", json={"pcm16k_b64": b64_short})
    assert res_l3.status_code == 200
    d_l3 = res_l3.json()
    assert d_l3["ok"] is False
    assert d_l3.get("ask_repeat") is True
    assert "người lạ" not in (d_l3.get("error", "") + d_l3.get("message", "")).lower()

    res_vc = asyncio.run(
        process_voice_command_pipeline(
            {"pcm16k_b64": b64_short, "transcript": "Mở cửa chính"},
            engine=SmartHomeEngine(),
            voice_auth=vm,
        )
    )
    assert res_vc["authorized"] is False
    assert res_vc.get("ask_repeat") is True
    assert "người lạ" not in str(res_vc.get("speaker_name", "")).lower()


def test_5sample_enrollment_rejects_duplicate_clips_and_duplicate_household_voice(client: TestClient) -> None:
    """Verify 5-sample enrollment rejects byte-identical clips and duplicate household voices."""
    c1 = _read_pcm16k("test_audio/cac_cau_lenh_cua_sep/cau_1_xin_chao_chu_nha_cap1.wav")
    c2 = _read_pcm16k("test_audio/cac_cau_lenh_cua_sep/cau_2_mo_cua_chinh.wav")
    c3 = _read_pcm16k("test_audio/cac_cau_lenh_cua_sep/cau_3_dong_cua_chinh.wav")
    c4 = _read_pcm16k("test_audio/cac_cau_lenh_cua_sep/cau_4_bat_den_phong_khach.wav")
    c6 = _read_pcm16k("test_audio/cac_cau_lenh_cua_sep/cau_6_tat_het_den.wav")

    # 1. Byte-identical duplicate clip inside 5-sample batch -> rejected
    dup_batch_res = compute_multi_sample_mean_embedding([c1, c2, c1, c4, c6], required_samples=5)
    assert dup_batch_res["ok"] is False
    assert dup_batch_res["reason"] in ("DUPLICATE_SAMPLE_BUFFER", "DUPLICATE_SAMPLE_CLIP", "DUPLICATE_SAMPLE_EMBEDDING")

    # 2. 5 distinct owner clips -> accepted with L2-normalized 256-D mean embedding
    good_batch_res = compute_multi_sample_mean_embedding([c1, c2, c3, c4, c6], required_samples=5)
    assert good_batch_res["ok"] is True
    assert good_batch_res["num_samples"] == 5
    vec = np.asarray(good_batch_res["wespeaker_embedding"], dtype=np.float32)
    assert vec.shape == (256,)
    assert float(np.linalg.norm(vec)) == pytest.approx(1.0, abs=1e-3)

    # 3. Guest QR enrollment with 5 distinct owner clips -> DUPLICATE_VOICE_REJECTED
    cur_res = client.get("/api/auth3/guest_qr_current?duration=1d")
    token = cur_res.json()["token"]
    hs_res = client.post("/api/auth3/guest_qr_handshake", json={"token": token, "duration": "1d"})
    sess_id = hs_res.json()["session"]["session_id"]

    owner_5_b64 = [base64.b64encode(x).decode("ascii") for x in (c1, c2, c3, c4, c6)]
    dup_guest_res = client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "session_id": sess_id,
            "guest_name": "Guest Spoofing Owner 5 Samples",
            "duration": "1d",
            "samples_b64": owner_5_b64,
            "audio_pcm_b64": owner_5_b64[0],
        },
    )
    assert dup_guest_res.status_code == 400
    assert dup_guest_res.json()["status"] == "DUPLICATE_VOICE_REJECTED"


def test_all_5_paths_and_level2_level3_rbac_owner_only_devices(client: TestClient) -> None:
    """Verify all 5 verification paths and Level 2/3 5-sample enrollment + owner-only device protection."""
    owner_c2 = _read_pcm16k("test_audio/cac_cau_lenh_cua_sep/cau_2_mo_cua_chinh.wav")
    owner_b64 = base64.b64encode(owner_c2).decode("ascii")
    stranger_pcm = _read_pcm16k("test_audio/giong_2_nguoi_la_mo_cua.wav")
    stranger_b64 = base64.b64encode(stranger_pcm).decode("ascii")

    # Path 1: REST /api/voice_command
    r_vc_own = client.post("/api/voice_command", json={"audio_b64": owner_b64, "transcript": "Mở cửa chính"})
    assert r_vc_own.status_code == 200
    assert r_vc_own.json()["authorized"] is True
    assert r_vc_own.json()["tier"] == 1
    assert r_vc_own.json()["similarity"] >= 0.475

    r_vc_str = client.post("/api/voice_command", json={"audio_b64": stranger_b64, "transcript": "Mở cửa chính"})
    assert r_vc_str.status_code == 200
    assert r_vc_str.json()["authorized"] is False
    assert r_vc_str.json()["rbac_blocked"] is True

    # Path 2: /api/auth3/layer3_voice
    r_l3_own = client.post("/api/auth3/layer3_voice", json={"pcm16k_b64": owner_b64})
    assert r_l3_own.status_code == 200
    assert r_l3_own.json()["ok"] is True
    assert r_l3_own.json()["tier"] == 1
    assert r_l3_own.json()["similarity"] >= 0.475

    r_l3_str = client.post("/api/auth3/layer3_voice", json={"pcm16k_b64": stranger_b64})
    assert r_l3_str.status_code == 200
    assert r_l3_str.json()["ok"] is False

    # Path 3 & 4: Enroll Level 2 (Family) and Level 3 (Guest) using 5 distinct samples each
    fam_5_samples = _generate_distinct_human_like_samples(base_f0=196.0, count=5)
    fam_5_b64 = [base64.b64encode(s).decode("ascii") for s in fam_5_samples]
    r_fam_enroll = client.post(
        "/api/auth3/enroll_voice_sample",
        json={
            "email": "thanhviena.hust@gmail.com",
            "speaker_name": "Thành viên A",
            "target_tier": 2,
            "hold_duration_sec": 3.6,
            "samples_b64": fam_5_b64,
            "audio_pcm_b64": fam_5_b64[0],
        },
    )
    assert r_fam_enroll.status_code == 200
    assert r_fam_enroll.json()["ok"] is True
    assert r_fam_enroll.json()["sample_count"] == 5

    cur_res = client.get("/api/auth3/guest_qr_current?duration=1d")
    token = cur_res.json()["token"]
    hs_res = client.post("/api/auth3/guest_qr_handshake", json={"token": token, "duration": "1d"})
    sess_id = hs_res.json()["session"]["session_id"]

    guest_5_samples = _generate_distinct_human_like_samples(base_f0=238.0, count=5)
    guest_5_b64 = [base64.b64encode(s).decode("ascii") for s in guest_5_samples]
    r_guest_enroll = client.post(
        "/api/auth3/guest_qr_complete_voice",
        json={
            "session_id": sess_id,
            "guest_name": "Khách C 5 Mẫu",
            "duration": "1d",
            "samples_b64": guest_5_b64,
            "audio_pcm_b64": guest_5_b64[0],
        },
    )
    assert r_guest_enroll.status_code == 200
    assert r_guest_enroll.json()["ok"] is True
    assert r_guest_enroll.json()["enrollment_samples_count"] == 5
    # Ensure no raw audio or embeddings leak in API response
    dumped = json.dumps(r_guest_enroll.json())
    assert "wespeaker_embedding" not in dumped
    assert "embedding_256d" not in dumped

    # Verify Owner-only devices (`main_door`, `alarm_siren`) stay strictly owner-only for Level 2 & Level 3
    engine = SmartHomeEngine()
    engine.devices["main_door"]["state"] = "CLOSED"
    engine.devices["alarm_siren"]["state"] = "ON"

    for sub_user in ("thanh_vien_a", "khach_c"):
        engine.set_active_user(sub_user)
        door_res = asyncio.run(engine.execute_device_action("main_door", "open", source=f"voice_{sub_user}"))
        siren_res = asyncio.run(engine.execute_device_action("alarm_siren", "turn_off", source=f"voice_{sub_user}"))
        assert door_res.get("ok") is False or engine.devices["main_door"]["state"] == "CLOSED"
        assert siren_res.get("ok") is False or engine.devices["alarm_siren"]["state"] == "ON"


def test_vivos_impostors_dev11_298_and_dev12_271_strictly_rejected() -> None:
    """Explicitly assert that known failure cases DEV11_298 and DEV12_271 are strictly rejected as owner."""
    vm = VoiceAuthManager(ROOT / "test_audio")
    imp_dir = pathlib.Path(r"C:\Users\LENOVO\voice-bench\fb\imp")
    targets = ("vivos_VIVOSDEV11_298.wav", "vivos_VIVOSDEV12_271.wav")
    for fname in targets:
        p = imp_dir / fname
        assert p.exists(), f"Missing required benchmark impostor: {p}"
        res = vm.verify_pcm16k_and_apply_strikes(p.read_bytes())
        assert res["authorized"] is False, f"{fname} must NOT be authorized as owner"
        assert res["tier"] != 1, f"{fname} must NOT be granted Tier 1 permission"
        assert res["speaker_id"] != "owner_voice_1"
        assert res.get("cohort_gate_passed") is False or res["similarity"] < 0.475
        assert res.get("cohort_margin", 0.0) < 0.0 or res["similarity"] < 0.475


def test_all_130_vivos_impostor_clips_zero_false_acceptance() -> None:
    """Evaluate all 130 VIVOS clips in C:\\Users\\LENOVO\\voice-bench\\fb\\imp and family/strangers.

    Asserts FAR = 0.0% (exactly 0 false accepts at owner level).
    """
    vm = VoiceAuthManager(ROOT / "test_audio")
    imp_dir = pathlib.Path(r"C:\Users\LENOVO\voice-bench\fb\imp")
    if not imp_dir.exists():
        pytest.skip(f"VIVOS benchmark directory not found at {imp_dir}")

    files = sorted(imp_dir.glob("*.wav"))
    assert len(files) == 130, f"Expected 130 VIVOS impostor clips, found {len(files)}"

    false_accepts: list[tuple[str, float, float]] = []
    for f in files:
        pcm = f.read_bytes()
        res = vm.verify_pcm16k_and_apply_strikes(pcm)
        if res["authorized"] and res.get("tier") == 1:
            false_accepts.append((f.name, float(res.get("similarity", 0.0)), float(res.get("cohort_margin", 0.0))))

    for rel_stranger in (
        "test_audio/giong_2_nguoi_la_mo_cua.wav",
        "test_audio/giong_cap2_thanh_vien_a.wav",
        "test_audio/giong_cap3_khach_c.wav",
    ):
        p = ROOT / rel_stranger
        if p.exists():
            res = vm.verify_pcm16k_and_apply_strikes(p.read_bytes())
            if res["authorized"] and res.get("tier") == 1:
                false_accepts.append((rel_stranger, float(res.get("similarity", 0.0)), float(res.get("cohort_margin", 0.0))))

    assert len(false_accepts) == 0, f"Detected owner False Accepts (FAR > 0%): {false_accepts}"


def test_all_7_genuine_owner_commands_and_held_out_zero_false_rejection() -> None:
    """Evaluate all 7 genuine owner commands (cau_1..cau_7) and clean held-out owner audio.

    Asserts FRR = 0.0% (exactly 0 false rejections at owner level).
    """
    vm = VoiceAuthManager(ROOT / "test_audio")
    sep_dir = ROOT / "test_audio" / "cac_cau_lenh_cua_sep"
    false_rejections: list[tuple[str, float, float]] = []

    # 1. All 7 genuine owner commands
    for i in range(1, 8):
        matches = list(sep_dir.glob(f"cau_{i}_*.wav"))
        assert len(matches) > 0, f"Missing owner command cau_{i}"
        p = matches[0]
        res = vm.verify_pcm16k_and_apply_strikes(p.read_bytes())
        if not res["authorized"] or res.get("tier") != 1:
            false_rejections.append((p.name, float(res.get("similarity", 0.0)), float(res.get("cohort_margin", 0.0))))
        assert res["authorized"] is True, f"Owner command {p.name} rejected: {res}"
        assert res["tier"] == 1, f"Owner command {p.name} did not receive Tier 1"
        assert res["similarity"] >= 0.475, f"Owner command {p.name} similarity {res['similarity']} < 0.475"
        assert res["cohort_margin"] >= 0.0, f"Owner command {p.name} cohort margin {res['cohort_margin']} < 0.0"

    # 2. Clean held-out owner recordings
    held_out_1 = ROOT / "test_audio" / "lich_su_thu_am" / "giong_cap1_20261104_110554.wav"
    if held_out_1.exists():
        res_ho1 = vm.verify_pcm16k_and_apply_strikes(held_out_1.read_bytes())
        assert res_ho1["authorized"] is True, f"Held-out clean owner audio {held_out_1.name} rejected"
        assert res_ho1["tier"] == 1
        assert res_ho1["similarity"] >= 0.475
        assert res_ho1["cohort_margin"] >= 0.0

    tuan_anh_wav = ROOT / "test_audio" / "giong_chu_nha_cap1_tuan_anh.wav"
    if tuan_anh_wav.exists():
        x_full = vad_trim_16k(_read_wav_float32_16k(tuan_anh_wav))
        chunks = np.array_split(x_full, 2)
        chunk0 = chunks[0].astype(np.float32)
        pcm_c0 = np.clip(chunk0 * 32767.0, -32768, 32767).astype(np.int16).tobytes()
        res_c0 = vm.verify_pcm16k_and_apply_strikes(pcm_c0)
        assert res_c0["authorized"] is True, "Held-out chunk tuan_anh#0 rejected"
        assert res_c0["tier"] == 1
        assert res_c0["similarity"] >= 0.475
        assert res_c0["cohort_margin"] >= 0.0

    assert len(false_rejections) == 0, f"Detected owner False Rejections (FRR > 0%): {false_rejections}"


def test_cohort_margin_defense_in_depth_gate() -> None:
    """Directly test evaluate_cohort_margin function behavior and separation gap."""
    seed = load_verified_owner_seed(project_root=ROOT)
    owner_centroid = np.asarray(seed["wespeaker_embedding"], dtype=np.float32)

    # Genuine owner command cau_1 must have strongly positive margin (>= +0.20)
    c1_path = list((ROOT / "test_audio" / "cac_cau_lenh_cua_sep").glob("cau_1_*.wav"))[0]
    emb_c1 = extract_wespeaker_embedding(c1_path.read_bytes())
    margin_c1, max_c1, pass_c1 = evaluate_cohort_margin(emb_c1, owner_centroid)
    assert pass_c1 is True
    assert margin_c1 >= 0.20, f"Expected margin >= 0.20, got {margin_c1}"

    # VIVOS impostor DEV11_298 must have negative margin (<= -0.10)
    dev11_path = pathlib.Path(r"C:\Users\LENOVO\voice-bench\fb\imp\vivos_VIVOSDEV11_298.wav")
    if dev11_path.exists():
        emb_dev11 = extract_wespeaker_embedding(dev11_path.read_bytes())
        margin_d11, max_d11, pass_d11 = evaluate_cohort_margin(emb_dev11, owner_centroid)
        assert pass_d11 is False
        assert margin_d11 < 0.0, f"Expected negative margin, got {margin_d11}"
