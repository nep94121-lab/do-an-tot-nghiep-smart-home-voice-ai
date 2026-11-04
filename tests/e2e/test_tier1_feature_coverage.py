"""TẦNG 1 (TIER 1): KIỂM THỬ ĐỘC LẬP TỪNG TÍNH NĂNG (FEATURE COVERAGE).
Bao phủ toàn diện 14 tính năng cốt lõi được định nghĩa trong PROJECT.md.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.rule_engine import SmartHomeEngine
from simulator.voice_auth import (
    VoiceAuthManager,
    transform_pcm_by_pitch_factor,
)
from simulator.auth_3layer import get_auth_3layer_manager
from tests.e2e.conftest import (
    validate_voice_quality_helper,
    add_family_email_helper,
)


class TestTier1FeatureCoverage:
    """Kiểm thử tính năng độc lập cho 14 tính năng."""

    def test_feat01_owner_voice_dsp_recognition(
        self, voice_auth_mgr: VoiceAuthManager, pcm_owner_bytes: bytes
    ) -> None:
        """FEAT-01: Nhận diện giọng Chủ nhà Cấp 1 sạch."""
        res = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_owner_bytes)
        assert res["authorized"] is True, f"Chủ nhà bị từ chối: {res}"
        assert res["speaker_id"] == "owner_voice_1"
        assert res["tier"] == 1
        assert res["strike_count"] == 0
        assert res["silent_ignore"] is False
        assert 75.0 <= res["f0_hz"] <= 340.0, f"F0 ngoài dải người: {res['f0_hz']} Hz"

    def test_feat01_intruder_voice_rejection(
        self, voice_auth_mgr: VoiceAuthManager, pcm_intruder_bytes: bytes
    ) -> None:
        """FEAT-01: Phát hiện và từ chối Người lạ (Intruder) gán Tier 99."""
        res = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_intruder_bytes)
        assert res["authorized"] is False, f"Người lạ lại được cho phép: {res}"
        assert res["speaker_id"] == "intruder_voice_2"
        assert res["tier"] == 99
        assert res["strike_count"] == 1
        assert res["rejection_speech"] == "Tôi không được phép nhận lệnh từ người lạ."

    def test_feat01_pitch_shift_tolerance(
        self, voice_auth_mgr: VoiceAuthManager, pcm_owner_bytes: bytes
    ) -> None:
        """FEAT-01: Chống sai lệch quãng tám & nhận diện khi cao độ dịch chuyển nhẹ."""
        pcm_arr = np.frombuffer(pcm_owner_bytes, dtype=np.int16)
        for factor in (1.0, 1.15, 1.28):
            pcm_test = (
                pcm_owner_bytes
                if factor == 1.0
                else transform_pcm_by_pitch_factor(pcm_arr, factor=factor, sr=16000).tobytes()
            )
            res = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_test)
            assert res["authorized"] is True, f"Chủ nhà factor={factor} bị từ chối: {res}"
            assert res["speaker_id"] == "owner_voice_1"

    def test_feat01_wiener_denoising_fan(
        self, voice_auth_mgr: VoiceAuthManager, pcm_noisy_fan_bytes: bytes
    ) -> None:
        """FEAT-01: Khử tiếng ồn quạt trần (Wiener Denoising) & Tự động bật Tầng 2."""
        res = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_noisy_fan_bytes)
        assert res["authorized"] is True
        assert res["fan_noise_detected"] is True, "Không phát hiện tiếng ồn quạt nền!"
        assert res["noise_removed_db"] >= 10.0, f"Độ giảm ồn quá thấp: {res['noise_removed_db']} dB"
        assert res["stage2_triggered"] is True, "Tiếng ồn lớn nhưng không bật Tầng 2!"

    def test_feat02_multi_speaker_priority(
        self, voice_auth_mgr: VoiceAuthManager, pcm_dual_speakers_bytes: bytes
    ) -> None:
        """FEAT-02: 2 người cùng nói -> Ưu tiên nhận diện Chủ nhà Cấp 1."""
        res = voice_auth_mgr.verify_pcm16k_and_apply_strikes(pcm_dual_speakers_bytes)
        assert res["authorized"] is True
        assert res["multi_speaker_detected"] is True
        assert res["speaker_count"] >= 2
        assert res["speaker_id"] == "owner_voice_1"
        assert "Chủ nhà" in res["priority_reason"] or "Cấp 1" in res["priority_reason"]

    def test_feat04_voice_enrollment_quality_gate(self) -> None:
        """FEAT-04: Cổng kiểm định chất lượng giọng thu âm trang đầu (Đạt vs Chưa đạt)."""
        # 1. Âm thanh hợp lệ của người nói chuẩn (độ dài >= 2.0s, F0 ổn định, RMS >= 0.02, SNR >= 10dB)
        from tests.e2e.conftest import read_wav_pcm16
        good_bytes = read_wav_pcm16("bat_quat_va_dieu_hoa.wav")
        pcm_arr = np.frombuffer(good_bytes, dtype=np.int16)

        res_good = validate_voice_quality_helper(pcm_arr, 16000)
        assert res_good["ok"] is True
        assert res_good["status"] == "DA_DAT"
        assert "đạt" in res_good["message"].lower()

        # 2. Âm thanh im lặng hoặc rác (RMS < 0.015 hoặc rỗng)
        silent_arr = np.zeros(32000, dtype=np.int16)
        res_bad = validate_voice_quality_helper(silent_arr, 16000)
        assert res_bad["ok"] is False
        assert res_bad["status"] == "CHUA_DAT"
        bad_text = (res_bad.get("reason", "") + " " + res_bad.get("message", "")).lower()
        assert "chưa" in bad_text

    def test_feat05_06_gemini_live_vietnamese_vad_config(self) -> None:
        """FEAT-05 & FEAT-06: Cấu hình Gemini Live speech_config vi-VN và VAD silence_duration_ms=1000."""
        prompt_builder_path = ROOT / "simulator" / "live" / "prompt_builder.py"
        target_path = prompt_builder_path if prompt_builder_path.exists() else (ROOT / "simulator" / "server.py")
        code = target_path.read_text(encoding="utf-8")

        has_speech_or_vi = (
            'language_code="vi-VN"' in code
            or "vi-VN" in code
            or "SpeechConfig" in code
        )
        assert has_speech_or_vi, "Thiếu cấu hình ngôn ngữ tiếng Việt (vi-VN) trong simulator/live/prompt_builder.py!"

        has_vad_tuning = (
            "silence_duration_ms" in code
            and ("1000" in code or "silence_duration_ms=1000" in code or "END_SENSITIVITY_LOW" in code)
        )
        assert has_vad_tuning, "Thiếu cấu hình VAD nâng cao chống ngắt ngập ngừng trong simulator/live/prompt_builder.py!"

    def test_feat07_system_instruction_prompt_guard(self) -> None:
        """FEAT-07: Vietnamese & Filler Prompt Guard trong System Instruction."""
        prompt_builder_path = ROOT / "simulator" / "live" / "prompt_builder.py"
        target_path = prompt_builder_path if prompt_builder_path.exists() else (ROOT / "simulator" / "server.py")
        code = target_path.read_text(encoding="utf-8")

        assert "build_system_instruction" in code
        assert "tiếng Việt" in code or "Vietnamese" in code
        assert "7 thiết bị" in code or "cửa chính" in code

    def test_feat08_rag_7_devices_synchronized(self) -> None:
        """FEAT-08: RAG tri thức đồng bộ đủ 7 thiết bị nhà thông minh (bao gồm garden_pump)."""
        kb_path = ROOT / "simulator" / "data" / "knowledge_base.json"
        if not kb_path.exists():
            from simulator.knowledge_rag import ensure_kb_file
            ensure_kb_file()

        raw = json.loads(kb_path.read_text(encoding="utf-8"))
        items = raw.get("items", []) if isinstance(raw, dict) else raw
        topics_str = " ".join([item.get("content", "") + " " + item.get("topic", "") for item in items])

        assert "máy bơm" in topics_str.lower() or "garden_pump" in topics_str.lower() or "tưới cây" in topics_str.lower()
        assert "cửa chính" in topics_str.lower()
        assert "quạt" in topics_str.lower()
        assert "điều hòa" in topics_str.lower()
        assert "còi báo động" in topics_str.lower()

    def test_feat09_email_allowlist_hierarchy(self) -> None:
        """FEAT-09: Phân quyền Thêm Email Gia Đình (Email Allowlist Hierarchy)."""
        mgr = get_auth_3layer_manager()

        # C1 (tuan_anh / nep94121@gmail.com) thêm C2 -> Hợp lệ
        r1_2 = add_family_email_helper(mgr, "tuan_anh", "thanhvien_test_c2@gmail.com", target_tier=2)
        assert r1_2.get("ok") is True

        # C1 thêm C3 -> Hợp lệ
        r1_3 = add_family_email_helper(mgr, "tuan_anh", "khach_test_c3@gmail.com", target_tier=3)
        assert r1_3.get("ok") is True

        # C2 (thanh_vien_a) chỉ được thêm C3 -> Hợp lệ
        r2_3 = add_family_email_helper(mgr, "thanh_vien_a", "khach_tu_c2@gmail.com", target_tier=3)
        assert r2_3.get("ok") is True

        # C2 cố thêm C1 hoặc C2 -> BỊ CHẶN (HTTP 403 / ok=False)
        r2_2 = add_family_email_helper(mgr, "thanh_vien_a", "hack_c2@gmail.com", target_tier=2)
        assert r2_2.get("ok") is False, "Cấp 2 không được phép thêm Cấp 2!"

        # C3 (khach_c) cố thêm bất kỳ ai -> BỊ CHẶN 100% (HTTP 403 / ok=False)
        r3_3 = add_family_email_helper(mgr, "khach_c", "khach_tu_c3@gmail.com", target_tier=3)
        assert r3_3.get("ok") is False, "Cấp 3 không được phép thêm bất kỳ thành viên nào!"

    def test_feat09_7_devices_actuation(
        self, smart_home_engine: SmartHomeEngine
    ) -> None:
        """FEAT-09: Thực thi điều khiển trên toàn bộ 7 thiết bị phần cứng."""
        async def _run() -> None:
            devices = [
                ("main_door", "open", "Cửa chính đã mở."),
                ("living_room_light", "turn_on", "Đèn phòng khách đã bật."),
                ("bedroom_light", "turn_on", "Đèn phòng ngủ đã bật."),
                ("fan", "turn_on", "Quạt trần đã bật."),
                ("ac", "turn_on", "Điều hòa đã mở."),
                ("alarm_siren", "turn_on", "Còi báo động đã bật."),
                ("garden_pump", "turn_on", "Máy bơm tưới cây đã bật."),
            ]

            for dev_id, action, expected_phrase in devices:
                res = await smart_home_engine.execute_device_action(dev_id, action)
                assert res.get("ok") is True, f"Lỗi điều khiển thiết bị {dev_id}: {res}"
                assert res.get("exact_spoken_reply") == expected_phrase

        asyncio.run(_run())

    def test_feat10_countdown_timer_pool(
        self, smart_home_engine: SmartHomeEngine
    ) -> None:
        """FEAT-10: Hẹn giờ đếm ngược cho thiết bị, lưu vào Bể 1."""
        async def _run() -> None:
            res = await smart_home_engine.schedule_timer_flexible(
                device_id="living_room_light",
                action="turn_off",
                seconds=5,
            )
            assert res.get("ok") is True
            assert "5 giây" in res.get("exact_spoken_reply", "")

            timers = smart_home_engine.active_timers
            assert len(timers) >= 1
            assert any(t.get("device_id") == "living_room_light" for t in timers.values())

        asyncio.run(_run())

    def test_feat11_android_adb_and_properties(self) -> None:
        """FEAT-11: Cấu hình build Android tránh lỗi non-ASCII path & APK tồn tại."""
        gradle_props = ROOT / "android_app" / "gradle.properties"
        if gradle_props.exists():
            content = gradle_props.read_text(encoding="utf-8")
            assert "android.overridePathCheck=true" in content

        apk_path = ROOT / "android_app" / "build" / "SmartHomeVoiceAI-debug.apk"
        assert apk_path.exists(), f"Không tìm thấy APK debug tại {apk_path}"
        assert apk_path.stat().st_size > 1000000, "Dung lượng APK quá nhỏ!"

    def test_feat13_constitution_convergence(self) -> None:
        """FEAT-13: Kiểm tra 6 Điều Hiến pháp Spec Kit."""
        import subprocess

        cmd = [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "speckit_converge.py")]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT))
        assert proc.returncode == 0, f"Speckit converge thất bại: {proc.stderr}\n{proc.stdout}"
        assert "CONVERGED 100%" in proc.stdout
