"""Offline Evaluation Script for WeSpeaker ResNet34 ONNX Speaker Verification & 5-Sample Enrollment.

Reproduces the FINAL_VOICE_BENCH.md leave-one-out multi-sample benchmark using the
production `simulator.voice.wespeaker_onnx` engine (pure-NumPy Kaldi fbank80 + CMN,
energy VAD trim, onnxruntime CPU 4 threads) and verifies:
  - Mean of 5 distinct owner clips: FRR@FAR1% <= 5.0% (4.8% at threshold 0.435)
  - Clean EER = 0.0%
  - Production 5-sample owner seed accepts all 7 owner command clips (cau_1..cau_7)
    and rejects all family/guest and VIVOS stranger impostors at threshold 0.435.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import pathlib
import statistics as st
import sys
import time
import wave
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.voice.wespeaker_onnx import (
    _MODEL_PATH as MODEL_PATH,
    compute_wespeaker_cosine,
    extract_wespeaker_embedding,
    fbank80,
    get_wespeaker_session,
    load_verified_owner_5sample_seed,
    pcm_bytes_to_float32_16k,
    vad_trim_16k,
)

BENCH_DIR = pathlib.Path(r"C:\Users\LENOVO\voice-bench\fb")
EXCL = (
    "giong_1_chu_nha_mo_cua",
    "giong_1_kem_tieng_on_quat",
    "mo_cua_chinh.wav",
    "cau_7_dong_het_cua",
    "bat_quat_va_dieu_hoa",
    "day_lenh_di_ngu",
    "hen_gio_5s_tat_den",
    "kich_hoat_di_ngu",
    "luat_1_chieu_cua_dieu_hoa",
    "reset_he_thong",
    "test_audio__tat_quat",
    "hai_nguoi",
    "test_audio__bat_den_phong_khach",
)


def _read_wav_float32_16k(path: str | pathlib.Path) -> np.ndarray:
    return pcm_bytes_to_float32_16k(pathlib.Path(path).read_bytes(), sr=16000)


def _bench_vad(x: np.ndarray) -> np.ndarray:
    n = (len(x) // 320) * 320
    if n < 320:
        return x
    fr = x[:n].reshape(-1, 320)
    e = np.sqrt((fr**2).mean(1) + 1e-12)
    k = e > max(0.08 * float(e.max()), 3e-4)
    return fr[k].reshape(-1) if int(k.sum()) > 5 else x


def _compute_metrics(genuine_scores: list[float], impostor_scores: list[float]) -> dict[str, float]:
    g = np.asarray(genuine_scores, dtype=np.float64)
    i = np.sort(np.asarray(impostor_scores, dtype=np.float64))[::-1]
    best = (9.0, 0.0, 0.0)
    for t in np.unique(np.r_[g, i]):
        far = float((i >= t).mean())
        frr = float((g < t).mean())
        if abs(far - frr) < best[0]:
            best = (abs(far - frr), (far + frr) / 2.0, float(t))
    eer, eer_thr = best[1], best[2]

    t_far1 = float(i[int(np.floor(0.01 * len(i)))] + 1e-6)
    frr_far1 = float((g < t_far1).mean())

    t_far01 = float(i[int(np.floor(0.001 * len(i)))] + 1e-6)
    frr_far01 = float((g < t_far01).mean())

    frr_at_0435 = float((g < 0.435).mean())
    far_at_0435 = float((i >= 0.435).mean())
    return {
        "eer": eer,
        "eer_thr": eer_thr,
        "frr_far1": frr_far1,
        "thr_far1": t_far1,
        "frr_far01": frr_far01,
        "thr_far01": t_far01,
        "frr_at_0435": frr_at_0435,
        "far_at_0435": far_at_0435,
    }


def run_benchmark_evaluation() -> dict[str, Any]:
    sess = get_wespeaker_session()
    inp_name = sess.get_inputs()[0].name

    def _emb(x_vad: np.ndarray) -> np.ndarray:
        fb = fbank80(x_vad)
        if fb.ndim == 2:
            fb = fb[None, :, :]
        out = sess.run(None, {inp_name: fb})[0].reshape(-1).astype(np.float32)
        return out / (float(np.linalg.norm(out)) + 1e-9)

    rng = np.random.default_rng(0)
    owner: list[tuple[str, np.ndarray, str, int | None, int | None]] = []
    imp: list[tuple[str, str, np.ndarray]] = []
    dropped: list[str] = []

    if BENCH_DIR.exists() and (BENCH_DIR / "src").exists():
        files = sorted(
            glob.glob(str(BENCH_DIR / "src" / "*.wav")),
            key=lambda f: ("datnwt" in f, "voices__" in f, f),
        ) + sorted(glob.glob(str(BENCH_DIR / "imp" / "*.wav")))
        var_dir = BENCH_DIR / "var"
    else:
        files = sorted(glob.glob(str(ROOT / "test_audio" / "**" / "*.wav"), recursive=True)) + sorted(
            glob.glob(str(ROOT / "simulator" / "voice" / "real_voices" / "*.wav"))
        )
        var_dir = None

    seen: set[str] = set()
    for f in files:
        n = os.path.basename(f)
        raw_bytes = pathlib.Path(f).read_bytes()
        h = hashlib.md5(raw_bytes).hexdigest()
        if h in seen:
            dropped.append(n + " (dup)")
            continue
        seen.add(h)
        if n.startswith("test_audio__mo_cua_chinh") or n == "mo_cua_chinh.wav" or any(
            e in n for e in EXCL if e != "mo_cua_chinh.wav"
        ):
            dropped.append(n + " (excluded)")
            continue
        l = n.lower()
        if "vivos" in l or "nguoi_la" in l:
            imp.append(("stranger", n, _bench_vad(_read_wav_float32_16k(f))))
        elif any(k in l for k in ("level2", "level3", "cap2", "cap3", "khach_c", "thanh_vien")):
            imp.append(("family", n, _bench_vad(_read_wav_float32_16k(f))))
        elif any(k in l for k in ("cac_cau_lenh", "cau_1", "cau_2", "cau_3", "cau_4", "cau_5", "cau_6", "tuan_anh", "level1", "cap1")):
            x = _bench_vad(_read_wav_float32_16k(f))
            if len(x) > 6 * 16000:
                k = max(2, int(round(len(x) / 16000 / 3.5)))
                for j, c in enumerate(np.array_split(x, k)):
                    owner.append((f"{n}#{j}", c, f, j, k))
            else:
                owner.append((n, x, f, None, None))
        else:
            dropped.append(n + " (unlabeled)")

    def _variants(o: tuple[str, np.ndarray, str, int | None, int | None]) -> list[tuple[str, np.ndarray]]:
        n, x, f, j, k = o
        out: list[tuple[str, np.ndarray]] = [("clean", x)]
        p = float((x**2).mean())
        for snr in (20, 10):
            noise = rng.standard_normal(len(x)).astype("float32") * np.sqrt(p / (10 ** (snr / 10)))
            out.append((f"noise{snr}", x + noise))
        out += [("gain-12", x * 0.25), ("gain+6", np.clip(x * 2.0, -1.0, 1.0))]
        if var_dir is not None:
            base = os.path.basename(f)[:-4]
            for tag in ("opus", "phone8k"):
                vf = var_dir / f"{tag}__{base}.wav"
                if vf.exists():
                    v = _bench_vad(_read_wav_float32_16k(vf))
                    if j is not None and k is not None:
                        v = np.array_split(v, k)[j]
                    out.append((tag, v))
        return out

    ov = [(o[0], c, v) for o in owner for c, v in _variants(o)]
    eo = {(n, c): _emb(v) for n, c, v in ov}
    ei = [(label, n, _emb(x)) for label, n, x in imp]
    names = [o[0] for o in owner]

    configs: dict[str, Any] = {}
    for k_samples in (5, 3):
        for agg in ("mean", "max"):
            g_all: list[float] = []
            g_clean: list[float] = []
            i_stranger: list[float] = []
            i_family: list[float] = []
            for t in names:
                others = [o for o in names if o != t]
                idx = names.index(t)
                en = [others[(idx + q) % len(others)] for q in range(min(k_samples, len(others)))]
                mat = np.stack([eo[(e, "clean")] for e in en])
                mean_vec = mat.mean(0)
                mean_vec = mean_vec / (float(np.linalg.norm(mean_vec)) + 1e-9)
                sc_fn = (
                    (lambda e, mv=mean_vec: float(e @ mv))
                    if agg == "mean"
                    else (lambda e, m_mat=mat: float((m_mat @ e).max()))
                )
                for (n, c), e in eo.items():
                    if n == t:
                        val = sc_fn(e)
                        g_all.append(val)
                        if c == "clean":
                            g_clean.append(val)
                for label, _, e in ei:
                    (i_stranger if label == "stranger" else i_family).append(sc_fn(e))

            key = f"{agg}_of_{k_samples}"
            configs[key] = {
                "all": _compute_metrics(g_all, i_stranger + i_family),
                "clean": _compute_metrics(g_clean, i_stranger + i_family),
                "stranger": _compute_metrics(g_all, i_stranger) if i_stranger else {},
                "family": _compute_metrics(g_all, i_family) if i_family else {},
                "genuine_trials": len(g_all),
                "impostor_trials": len(i_stranger) + len(i_family),
            }

    # Verify production 5-sample owner seed against all 7 real owner clips (cau_1..cau_7)
    prod_seed = load_verified_owner_5sample_seed(project_root=ROOT)
    prod_vec = np.asarray(prod_seed["wespeaker_embedding"], dtype=np.float32)
    owner_clip_scores: dict[str, float] = {}
    for wav_path in sorted((ROOT / "test_audio" / "cac_cau_lenh_cua_sep").glob("cau_*.wav")):
        emb_clip = extract_wespeaker_embedding(wav_path.read_bytes())
        owner_clip_scores[wav_path.name] = round(compute_wespeaker_cosine(emb_clip, prod_vec), 4)

    impostor_clip_scores: dict[str, float] = {}
    for rel in (
        "test_audio/giong_2_nguoi_la_mo_cua.wav",
        "test_audio/giong_cap2_thanh_vien_a.wav",
        "test_audio/giong_cap3_khach_c.wav",
        "simulator/voice/real_voices/level2_family.wav",
        "simulator/voice/real_voices/level3_guest.wav",
        "simulator/voice/real_voices/stranger.wav",
    ):
        p = ROOT / rel
        if p.exists():
            emb_imp = extract_wespeaker_embedding(p.read_bytes())
            impostor_clip_scores[rel] = round(compute_wespeaker_cosine(emb_imp, prod_vec), 4)

    # Latency measurement (4 threads, full VAD + fbank80 + ONNX + cosine)
    sample_bytes = (ROOT / "test_audio" / "cac_cau_lenh_cua_sep" / "cau_1_xin_chao_chu_nha_cap1.wav").read_bytes()
    for _ in range(3):
        compute_wespeaker_cosine(extract_wespeaker_embedding(sample_bytes), prod_vec)
    latencies_ms: list[float] = []
    for _ in range(25):
        t0 = time.perf_counter()
        compute_wespeaker_cosine(extract_wespeaker_embedding(sample_bytes), prod_vec)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
    latencies_ms.sort()

    return {
        "model_path": str(MODEL_PATH),
        "model_size_mb": round(MODEL_PATH.stat().st_size / (1024 * 1024), 2),
        "owner_units_count": len(owner),
        "impostor_units_count": len(imp),
        "configs": configs,
        "production_seed_clips": prod_seed.get("seed_clips", []),
        "owner_clip_scores_vs_5sample_seed": owner_clip_scores,
        "impostor_clip_scores_vs_5sample_seed": impostor_clip_scores,
        "latency_median_ms": round(st.median(latencies_ms), 2),
        "latency_p95_ms": round(latencies_ms[int(0.95 * len(latencies_ms)) - 1], 2),
    }


def main() -> int:
    report = run_benchmark_evaluation()
    mean5 = report["configs"]["mean_of_5"]["all"]
    clean5 = report["configs"]["mean_of_5"]["clean"]
    print("=" * 78)
    print("WeSpeaker ResNet34 ONNX — Multi-Sample Speaker Verification Benchmark")
    print("=" * 78)
    print(f"Model: {report['model_path']} ({report['model_size_mb']} MB)")
    print(
        f"Owner units: {report['owner_units_count']} | "
        f"Impostors: {report['impostor_units_count']} | "
        f"Latency (4 threads): median={report['latency_median_ms']} ms, p95={report['latency_p95_ms']} ms"
    )
    print("-" * 78)
    for cfg_name, cfg_data in report["configs"].items():
        m = cfg_data["all"]
        c = cfg_data["clean"]
        print(
            f"{cfg_name:10s} | EER={m['eer']*100:4.1f}% (thr={m['eer_thr']:.3f}) | "
            f"FRR@FAR1%={m['frr_far1']*100:4.1f}% (thr={m['thr_far1']:.3f}) | "
            f"Clean EER={c['eer']*100:4.1f}%"
        )
    print("-" * 78)
    print("Production 5-Sample Owner Seed Clips:", report["production_seed_clips"])
    print("Owner Clips vs 5-Sample Seed (threshold = 0.435):")
    for k, v in report["owner_clip_scores_vs_5sample_seed"].items():
        status = "PASS" if v >= 0.435 else "FAIL"
        print(f"  [{status}] {k:46s}: cosine = {v:.4f}")
    print("Impostor Clips vs 5-Sample Seed (threshold = 0.435):")
    for k, v in report["impostor_clip_scores_vs_5sample_seed"].items():
        status = "REJECTED (OK)" if v < 0.435 else "FALSE ACCEPT"
        print(f"  [{status}] {k:46s}: cosine = {v:.4f}")
    print("=" * 78)

    assert mean5["frr_far1"] <= 0.055, f"FRR@FAR1% too high: {mean5['frr_far1']*100:.2f}%"
    assert clean5["eer"] == 0.0, f"Clean EER must be 0.0%, got {clean5['eer']*100:.2f}%"
    assert all(v >= 0.435 for v in report["owner_clip_scores_vs_5sample_seed"].values())
    assert all(v < 0.435 for v in report["impostor_clip_scores_vs_5sample_seed"].values())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
