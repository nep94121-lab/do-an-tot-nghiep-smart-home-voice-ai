"""BỘ KIỂM ĐỊNH ĐỐI KHÁNG TRỰC GIAO CỰC HẠN — CHALLENGER M5 (INSTANCE 2)
Tác giả: Teamwork Challenger M5-2 (Empirical Adversarial & Orthogonal Challenger)
Milestone: M5 (Final Robustness, Biometric Integrity & Database Concurrency)

3 Trọng tâm kiểm định:
1. Quét Pitch-Shift Kẻ Lạ dải [1.18x - 1.28x]:
   - Quét lưới dày đặc [1.18, 1.19, 1.20, 1.21, 1.22, 1.225, 1.23, 1.24, 1.25, 1.26, 1.27, 1.28]
   - Thử nghiệm các hệ số ngẫu nhiên không thẳng hàng (1.185, 1.215, 1.235, 1.255, 1.275)
   - Yêu cầu: 100% BỊ CHẶN (authorized == False, không nhận nhầm Cấp 1, tăng strike).
2. Chủ Nhà Nói Ngập Ngừng Kèm Âm Đệm (Vocal Fry 82Hz):
   - Quét lưới âm đệm vocal fry 82Hz kết hợp các khoảng lặng (100ms, 250ms, 500ms, 1000ms)
   - Kết hợp trên cả giọng chuẩn ("giong_1_chu_nha_mo_cua.wav", "mo_cua_chinh.wav") và giọng thật của Sếp ("cau_2_mo_cua_chinh.wav")
   - Yêu cầu: 100% ĐƯỢC CẤP QUYỀN CẤP 1 (authorized == True, tier == 1, strike_count == 0).
3. Kiểm Tra Tính Nhất Quán CSDL SQLite 3 (WAL Mode + Concurrency):
   - Kiểm tra PRAGMA journal_mode == 'WAL'
   - Stress-test đa luồng (10 luồng: writers + readers) thực thi đồng thời hàng trăm giao dịch
   - Xác nhận: 0 Deadlock, 0 'database is locked', dữ liệu ACID toàn vẹn.
"""

from __future__ import annotations

import concurrent.futures
import json
import pathlib
import random
import sqlite3
import sys
import threading
import time
import wave

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.database_sqlite import (
    SQLITE_DB_PATH,
    _DB_LOCK,
    clear_audit_logs_sqlite,
    execute_readonly_sql,
    get_connection,
    get_sqlite_overview,
    init_sqlite_database,
    insert_audit_log_sqlite,
)
from simulator.voice_auth import (
    VoiceAuthManager,
    transform_pcm_by_pitch_factor,
)

AUDIO_DIR = ROOT / "test_audio"


def load_wav_pcm(relative_path: str) -> np.ndarray:
    p = AUDIO_DIR / relative_path
    if not p.exists():
        raise FileNotFoundError(f"Missing audio asset: {p}")
    with wave.open(str(p), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def synthesize_vocal_fry_82hz(f0_hz: float = 82.0, duration_sec: float = 0.5, sr: int = 16000) -> np.ndarray:
    n_samples = int(sr * duration_sec)
    t = np.arange(n_samples, dtype=np.float32) / sr
    sig = (
        0.32 * np.sin(2.0 * np.pi * f0_hz * t)
        + 0.12 * np.sin(2.0 * np.pi * 2.0 * f0_hz * t)
        + 0.04 * np.sin(2.0 * np.pi * 3.0 * f0_hz * t)
    )
    env = np.sin(np.pi * np.linspace(0.0, 1.0, n_samples, endpoint=False)) ** 2
    out = sig * env * 32767.0
    return np.clip(out, -32768, 32767).astype(np.int16)


@pytest.fixture
def vm() -> VoiceAuthManager:
    manager = VoiceAuthManager(AUDIO_DIR)
    manager.reset_strikes()
    return manager


# ==============================================================================
# PHẦN 1: QUÉT PITCH-SHIFT KẺ LẠ [1.18x - 1.28x] -> CHẶN 100%
# ==============================================================================

class TestAdversarialIntruderPitchShiftSweep:
    """Stress-test quét đối kháng dải pitch-shift của kẻ lạ [1.18x - 1.28x]."""

    PITCH_FACTORS_GRID = [
        1.180, 1.190, 1.200, 1.210, 1.220, 1.225,
        1.230, 1.240, 1.250, 1.260, 1.270, 1.280,
    ]

    @pytest.mark.parametrize("pitch_factor", PITCH_FACTORS_GRID)
    def test_intruder_pitch_shift_grid_blocked_100_pct(
        self, vm: VoiceAuthManager, pitch_factor: float
    ) -> None:
        """Kẻ lạ biến đổi pitch factor trong khoảng [1.18x - 1.28x] bắt buộc bị chặn 100%."""
        pcm_intruder = load_wav_pcm("giong_2_nguoi_la_mo_cua.wav")
        shifted = transform_pcm_by_pitch_factor(pcm_intruder, factor=pitch_factor, sr=16000)

        vm.reset_strikes()
        res = vm.verify_pcm16k_and_apply_strikes(shifted.tobytes())

        assert res["authorized"] is False, (
            f"LỖ HỔNG AN NINH: Kẻ lạ pitch-shift {pitch_factor}x được cấp quyền! "
            f"authorized={res['authorized']}, speaker={res.get('speaker_id')}"
        )
        assert res["strike_count"] >= 1, (
            f"Kẻ lạ pitch-shift {pitch_factor}x không bị phạt strike! strike_count={res['strike_count']}"
        )
        assert res.get("speaker_id") != "owner_voice_1", (
            f"Kẻ lạ pitch-shift {pitch_factor}x bị nhận nhầm thành Chủ nhà C1!"
        )

    @pytest.mark.parametrize("pitch_factor", [1.185, 1.215, 1.235, 1.255, 1.275])
    def test_intruder_pitch_shift_offgrid_blocked_100_pct(
        self, vm: VoiceAuthManager, pitch_factor: float
    ) -> None:
        """Kiểm tra các điểm biên lệch lưới (off-grid) trong khoảng [1.18x - 1.28x] chống code cứng."""
        pcm_intruder = load_wav_pcm("giong_2_nguoi_la_mo_cua.wav")
        shifted = transform_pcm_by_pitch_factor(pcm_intruder, factor=pitch_factor, sr=16000)

        vm.reset_strikes()
        res = vm.verify_pcm16k_and_apply_strikes(shifted.tobytes())

        assert res["authorized"] is False, (
            f"LỖ HỔNG AN NINH (Off-grid): Kẻ lạ pitch-shift {pitch_factor}x được cấp quyền!"
        )
        assert res["strike_count"] >= 1


# ==============================================================================
# PHẦN 2: CHỦ NHÀ NÓI NGẬP NGỪNG VOCAL FRY 82Hz -> CẤP QUYỀN CẤP 1 (100%)
# ==============================================================================

class TestHomeownerVocalFryHesitationTier1:
    """Kiểm tra chủ nhà nói ngập ngừng kèm âm đệm vocal fry 82Hz phải được cấp quyền Cấp 1."""

    DURATIONS_SEC = [0.2, 0.5, 1.0, 2.0]
    PAUSES_MS = [100, 250, 500, 1000]

    @pytest.mark.parametrize("dur_sec", DURATIONS_SEC)
    @pytest.mark.parametrize("pause_ms", PAUSES_MS)
    def test_owner_vocal_fry_82hz_hesitation_granted_tier1(
        self, vm: VoiceAuthManager, dur_sec: float, pause_ms: int
    ) -> None:
        """Chủ nhà nói ngập ngừng với vocal fry 82Hz và khoảng lặng ghép trước câu lệnh mở cửa."""
        pcm_owner = load_wav_pcm("giong_1_chu_nha_mo_cua.wav")
        sr = 16000
        filler = synthesize_vocal_fry_82hz(f0_hz=82.0, duration_sec=dur_sec, sr=sr)
        pause = np.zeros(int(sr * (pause_ms / 1000.0)), dtype=np.int16)
        audio = np.concatenate([filler, pause, pcm_owner])

        vm.reset_strikes()
        res = vm.verify_pcm16k_and_apply_strikes(audio.tobytes())

        assert res["authorized"] is True, (
            f"TỪ CHỐI NHẦM CHỦ NHÀ: dur={dur_sec}s, pause={pause_ms}ms, "
            f"authorized={res['authorized']}, strike={res['strike_count']}"
        )
        assert res.get("tier") == 1, (
            f"SAI CẤP PHÂN QUYỀN: Kỳ vọng Cấp 1, nhận tier={res.get('tier')}"
        )
        assert res["strike_count"] == 0, (
            f"FALSE STRIKE: strike_count={res['strike_count']} (kỳ vọng 0)"
        )
        assert res.get("speaker_id") == "owner_voice_1"

    @pytest.mark.parametrize("dur_sec", [0.3, 0.8, 1.5])
    @pytest.mark.parametrize("pause_ms", [150, 400, 800])
    def test_sep_tuan_anh_real_voice_with_vocal_fry_82hz(
        self, vm: VoiceAuthManager, dur_sec: float, pause_ms: int
    ) -> None:
        """Giọng thật của Sếp Nguyễn Tuấn Anh ghép với âm đệm vocal fry 82Hz khi nói qua Live Mic."""
        pcm_sep = load_wav_pcm("cac_cau_lenh_cua_sep/cau_2_mo_cua_chinh.wav")
        sr = 16000
        filler = synthesize_vocal_fry_82hz(f0_hz=82.0, duration_sec=dur_sec, sr=sr)
        pause = np.zeros(int(sr * (pause_ms / 1000.0)), dtype=np.int16)
        audio = np.concatenate([filler, pause, pcm_sep])

        vm.reset_strikes()
        res = vm.verify_pcm16k_and_apply_strikes(audio.tobytes(), is_live_mic=True)

        assert res["authorized"] is True, (
            f"SẾP TUẤN ANH BỊ CHẶN: dur={dur_sec}s, pause={pause_ms}ms"
        )
        assert res.get("tier") == 1
        assert res["strike_count"] == 0


# ==============================================================================
# PHẦN 3: KIỂM TRA TÍNH NHẤT QUÁN SQLITE (WAL MODE + CONCURRENCY ZERO-DEADLOCK)
# ==============================================================================

class TestSqliteWalConcurrencyAndIntegrity:
    """Stress-test tính nhất quán của CSDL SQLite 3 dưới áp lực đa luồng đồng thời."""

    def test_sqlite_wal_mode_and_foreign_keys_configured(self) -> None:
        """Xác nhận SQLite CSDL đang chạy đúng chế độ WAL và Foreign Keys bật."""
        init_sqlite_database()
        overview = get_sqlite_overview()
        assert overview["ok"] is True
        assert overview["journal_mode"].upper() == "WAL", (
            f"CSDL chưa bật WAL mode! journal_mode={overview['journal_mode']}"
        )
        assert overview["foreign_keys_enforced"] is True, (
            "CSDL chưa bật Foreign Key Constraints!"
        )

    def test_concurrent_read_write_zero_deadlocks(self) -> None:
        """Chạy đồng thời 10 luồng (5 luồng ghi audit_logs + 5 luồng đọc SELECT)
        với 25 vòng lặp mỗi luồng (tổng 250 tác vụ đồng thời).
        Yêu cầu: 0 lỗi deadlock, 0 lỗi database is locked, 100% hoàn thành.
        """
        init_sqlite_database()
        errors: list[str] = []
        num_threads = 10
        ops_per_thread = 25

        def writer_worker(tid: int) -> None:
            for i in range(ops_per_thread):
                try:
                    entry = {
                        "ts_iso": f"2026-11-04T12:05:{tid:02d}.{i:03d}Z",
                        "time_vn": "12:05:00 04/11/2026",
                        "category": "CONCURRENCY_TEST",
                        "event_type": "stress_write",
                        "user": f"tester_{tid}",
                        "tier": 1,
                        "summary": f"Stress test worker {tid} op {i}",
                        "details": {"tid": tid, "op": i, "nonce": random.randint(10000, 99999)},
                    }
                    insert_audit_log_sqlite(entry, user_id="tuan_anh")
                    time.sleep(random.uniform(0.001, 0.004))
                except Exception as exc:
                    errors.append(f"Writer-{tid}-op{i}: {exc}")

        def reader_worker(tid: int) -> None:
            for i in range(ops_per_thread):
                try:
                    res = execute_readonly_sql("SELECT COUNT(*) AS total FROM audit_logs;", limit=5)
                    if not res.get("ok"):
                        errors.append(f"Reader-{tid}-op{i}: {res.get('error')}")
                    time.sleep(random.uniform(0.001, 0.004))
                except Exception as exc:
                    errors.append(f"Reader-{tid}-op{i}: {exc}")

        threads: list[threading.Thread] = []
        for tid in range(num_threads // 2):
            threads.append(threading.Thread(target=writer_worker, args=(tid,)))
            threads.append(threading.Thread(target=reader_worker, args=(tid,)))

        t_start = time.perf_counter()
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=20.0)
        elapsed = time.perf_counter() - t_start

        assert len(errors) == 0, f"Phát hiện lỗi xung đột/deadlock CSDL ({len(errors)} lỗi): {errors[:5]}"
        assert elapsed < 15.0, f"Thời gian thực thi quá lâu ({elapsed:.2f}s), có thể bị nghẽn I/O!"

    def test_acid_atomicity_transaction_rollback(self) -> None:
        """Xác nhận tính toàn vẹn Transaction ACID: Rollback khi gặp lỗi vi phạm ràng buộc Foreign Key."""
        init_sqlite_database()
        conn = get_connection()
        try:
            initial_count = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE event_type = 'ev1'").fetchone()[0]
            with pytest.raises(sqlite3.IntegrityError):
                with conn:
                    # Chèn bản ghi hợp lệ
                    conn.execute(
                        """
                        INSERT INTO audit_logs (
                            ts_iso, time_vn, category, event_type, user_id, user_name, tier, summary, details_json
                        ) VALUES ('2026-11-04T00:00:00Z', '00:00:00', 'TEST', 'ev1', 'tuan_anh', 'Tuấn Anh', 1, 'sum1', '{}')
                        """
                    )
                    # Chèn bản ghi vi phạm Foreign Key (user_id không tồn tại)
                    conn.execute(
                        """
                        INSERT INTO audit_logs (
                            ts_iso, time_vn, category, event_type, user_id, user_name, tier, summary, details_json
                        ) VALUES ('2026-11-04T00:00:00Z', '00:00:00', 'TEST', 'ev2', 'non_existent_user_9999', 'Ghost', 3, 'sum2', '{}')
                        """
                    )
            # Sau khi bị rollback, số lượng bản ghi ev1 phải bằng ban đầu (0)
            final_count = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE event_type = 'ev1'").fetchone()[0]
            assert final_count == initial_count, (
                f"ACID Atomicity thất bại! Số bản ghi thay đổi dù transaction bị lỗi: {initial_count} -> {final_count}"
            )
        finally:
            conn.close()
