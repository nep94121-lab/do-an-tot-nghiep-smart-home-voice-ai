"""Bộ kiểm thử toàn diện (End-to-End) cho các câu lệnh giọng nói thật của Sếp Nguyễn Tuấn Anh (Chủ nhà Cấp 1).

Kiểm tra:
1. Phân đoạn âm thanh VAD (7 câu lệnh cắt từ `test_audio/giong_chu_nha_cap1_tuan_anh.wav`) & đối chiếu `manifest_cau_lenh.json`.
2. Chất lượng mẫu thu âm (`validate_voice_enrollment_quality`) và hồ sơ giọng gốc Cấp 1 (`owner_voice_1` / `tuan_anh`).
3. Xác thực sinh trắc học giọng nói 2 tầng (`analyze_voice_pcm16k` & `verify_pcm16k_and_apply_strikes`) đạt 100% `authorized=True, tier=1, user_id='tuan_anh', role='ADMIN'`.
4. Thực thi điều khiển thiết bị đầu-cuối (`SmartHomeEngine.execute_device_action`) cho toàn bộ các câu lệnh: mở cửa chính, đóng cửa chính, bật đèn phòng khách, bật quạt trần và điều hòa, tắt hết đèn, đóng hết cửa.
5. Cổng chống trùng giọng (`check_duplicate_voice_gate`): Chặn tuyệt đối hành vi dùng giọng thật của Sếp để đăng ký tài khoản Cấp 2 / Cấp 3.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import wave

import pytest

from simulator.rule_engine import SmartHomeEngine
from simulator.voice_auth import (
    SEP_REAL_VOICE_COMMANDS_META,
    VoiceAuthManager,
    parse_vietnamese_voice_command_intents,
)

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT_DIR / "test_audio"
SLICED_DIR = AUDIO_DIR / "cac_cau_lenh_cua_sep"
MANIFEST_PATH = SLICED_DIR / "manifest_cau_lenh.json"


@pytest.fixture(scope="module")
def vm() -> VoiceAuthManager:
    mgr = VoiceAuthManager(AUDIO_DIR)
    full_wav = AUDIO_DIR / "giong_chu_nha_cap1_tuan_anh.wav"
    with wave.open(str(full_wav), "rb") as w:
        pcm_bytes = w.readframes(w.getnframes())
    mgr.enroll_tier_voice_from_pcm16k(
        pcm_bytes=pcm_bytes,
        user_id="tuan_anh",
        user_name="Nguyễn Tuấn Anh",
        tier=1,
        role="ADMIN",
        custom_label="Giọng Cấp 1 — Nguyễn Tuấn Anh (Chủ nhà - Toàn quyền)",
    )
    return mgr


def test_source_and_sliced_wav_files_integrity() -> None:
    """Kiểm tra tính toàn vẹn của file gốc, 7 file câu lệnh đã cắt và manifest JSON."""
    src_wav = AUDIO_DIR / "giong_chu_nha_cap1_tuan_anh.wav"
    assert src_wav.exists(), "Không tìm thấy file thu âm gốc của Sếp"
    assert src_wav.stat().st_size == 633902

    assert MANIFEST_PATH.exists(), "Không tìm thấy manifest_cau_lenh.json"
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["total_segments"] == 7
    assert len(manifest["segments"]) == 7

    for seg in manifest["segments"]:
        wav_path = ROOT_DIR / seg["path"]
        assert wav_path.exists(), f"Thiếu file đoạn cắt: {wav_path}"
        raw_bytes = wav_path.read_bytes()
        assert len(raw_bytes) == seg["size_bytes"]
        assert hashlib.sha256(raw_bytes).hexdigest() == seg["sha256"]
        with wave.open(str(wav_path), "rb") as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getframerate() == 16000
            assert w.getnframes() >= int(0.75 * 16000)


def test_owner_real_voice_enrollment_quality(vm: VoiceAuthManager) -> None:
    """Kiểm tra chất lượng mẫu thu âm gốc và câu chào Cấp 1 đạt chuẩn 6 tiêu chí âm học."""
    for rel_path in [
        AUDIO_DIR / "giong_chu_nha_cap1_tuan_anh.wav",
        SLICED_DIR / "cau_1_xin_chao_chu_nha_cap1.wav",
    ]:
        with wave.open(str(rel_path), "rb") as w:
            pcm_bytes = w.readframes(w.getnframes())
        q = vm.validate_voice_enrollment_quality(pcm_bytes, sr=16000)
        assert q["ok"] is True, f"Mẫu thu âm {rel_path.name} không qua cổng chất lượng: {q}"
        assert q["verified"] is True
        assert 85.0 <= q["f0_hz"] <= 130.0


@pytest.mark.parametrize("cmd_id", list(SEP_REAL_VOICE_COMMANDS_META.keys()))
def test_all_7_real_voice_segments_authenticated_as_tier1_owner(
    vm: VoiceAuthManager, cmd_id: str
) -> None:
    """Tất cả 7 câu nói thật của Sếp phải được nhận diện đúng là Chủ nhà Cấp 1 (tuan_anh, ADMIN)."""
    meta = SEP_REAL_VOICE_COMMANDS_META[cmd_id]
    wav_path = ROOT_DIR / meta["file"]
    with wave.open(str(wav_path), "rb") as w:
        pcm_bytes = w.readframes(w.getnframes())

    vm.reset_strikes()
    analysis = vm.analyze_voice_pcm16k(pcm_bytes)
    assert analysis["ok"] is True
    assert 88.0 <= analysis["f0_hz"] <= 122.0, (
        f"F0 bị nhảy quãng tám sai trên {cmd_id}: {analysis['f0_hz']}Hz"
    )

    res = vm.verify_pcm16k_and_apply_strikes(pcm_bytes, is_live_mic=False)
    assert res["authorized"] is True, f"Đoạn giọng thật {cmd_id} bị từ chối: {res}"
    assert res["tier"] == 1
    assert res["user_id"] == "tuan_anh"
    assert res["role"] == "ADMIN"
    assert res["speaker_id"] == "owner_voice_1"
    assert res["similarity"] >= 0.435
    assert res["strike_count"] == 0


def test_end_to_end_real_voice_commands_actuate_devices(vm: VoiceAuthManager) -> None:
    """Kiểm tra tuần tự 7 câu lệnh giọng nói thật của Sếp điều khiển chính xác các thiết bị trong nhà."""
    engine = SmartHomeEngine()
    engine.devices["main_door"]["state"] = "CLOSED"
    engine.devices["living_room_light"]["state"] = "OFF"
    engine.devices["bedroom_light"]["state"] = "ON"
    engine.devices["fan"]["state"] = "OFF"
    engine.devices["ac"]["state"] = "OFF"

    # Câu 1: Xin chào ngôi nhà thông minh, tôi là Nguyễn Tuấn Anh, chủ nhà.
    p1 = ROOT_DIR / SEP_REAL_VOICE_COMMANDS_META["cau_1_xin_chao_chu_nha_cap1"]["file"]
    with wave.open(str(p1), "rb") as w:
        out1 = vm.verify_and_execute_voice_command(
            w.readframes(w.getnframes()),
            SEP_REAL_VOICE_COMMANDS_META["cau_1_xin_chao_chu_nha_cap1"]["transcript"],
            engine=engine,
        )
    assert out1["ok"] is True
    assert out1["auth"]["tier"] == 1
    assert out1["device_results"] == []

    # Câu 2: Mở cửa chính. -> main_door == OPEN
    p2 = ROOT_DIR / SEP_REAL_VOICE_COMMANDS_META["cau_2_mo_cua_chinh"]["file"]
    with wave.open(str(p2), "rb") as w:
        out2 = vm.verify_and_execute_voice_command(
            w.readframes(w.getnframes()),
            SEP_REAL_VOICE_COMMANDS_META["cau_2_mo_cua_chinh"]["transcript"],
            engine=engine,
        )
    assert out2["ok"] is True
    assert engine.devices["main_door"]["state"] == "OPEN"
    assert out2["device_results"][0]["result"]["ok"] is True

    # Câu 3: Đóng cửa chính. -> main_door == CLOSED
    p3 = ROOT_DIR / SEP_REAL_VOICE_COMMANDS_META["cau_3_dong_cua_chinh"]["file"]
    with wave.open(str(p3), "rb") as w:
        out3 = vm.verify_and_execute_voice_command(
            w.readframes(w.getnframes()),
            SEP_REAL_VOICE_COMMANDS_META["cau_3_dong_cua_chinh"]["transcript"],
            engine=engine,
        )
    assert out3["ok"] is True
    assert engine.devices["main_door"]["state"] == "CLOSED"

    # Câu 4: Bật đèn phòng khách. -> living_room_light == ON
    p4 = ROOT_DIR / SEP_REAL_VOICE_COMMANDS_META["cau_4_bat_den_phong_khach"]["file"]
    with wave.open(str(p4), "rb") as w:
        out4 = vm.verify_and_execute_voice_command(
            w.readframes(w.getnframes()),
            SEP_REAL_VOICE_COMMANDS_META["cau_4_bat_den_phong_khach"]["transcript"],
            engine=engine,
        )
    assert out4["ok"] is True
    assert engine.devices["living_room_light"]["state"] == "ON"

    # Câu 5: Bật quạt trần và điều hòa. -> fan == ON, ac == ON
    p5 = ROOT_DIR / SEP_REAL_VOICE_COMMANDS_META["cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu"]["file"]
    with wave.open(str(p5), "rb") as w:
        out5 = vm.verify_and_execute_voice_command(
            w.readframes(w.getnframes()),
            SEP_REAL_VOICE_COMMANDS_META["cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu"]["transcript"],
            engine=engine,
        )
    assert out5["ok"] is True
    assert len(out5["device_results"]) == 2
    assert engine.devices["fan"]["state"] == "ON"
    assert engine.devices["ac"]["state"] == "ON"

    # Câu 6: Tắt hết đèn. -> living_room_light == OFF, bedroom_light == OFF
    p6 = ROOT_DIR / SEP_REAL_VOICE_COMMANDS_META["cau_6_tat_het_den"]["file"]
    with wave.open(str(p6), "rb") as w:
        out6 = vm.verify_and_execute_voice_command(
            w.readframes(w.getnframes()),
            SEP_REAL_VOICE_COMMANDS_META["cau_6_tat_het_den"]["transcript"],
            engine=engine,
        )
    assert out6["ok"] is True
    assert engine.devices["living_room_light"]["state"] == "OFF"
    assert engine.devices["bedroom_light"]["state"] == "OFF"

    # Câu 7: Đóng hết cửa. -> Mở cửa trước, sau đó chạy lệnh đóng hết cửa -> main_door == CLOSED
    engine.devices["main_door"]["state"] = "OPEN"
    p7 = ROOT_DIR / SEP_REAL_VOICE_COMMANDS_META["cau_7_dong_het_cua"]["file"]
    with wave.open(str(p7), "rb") as w:
        out7 = vm.verify_and_execute_voice_command(
            w.readframes(w.getnframes()),
            SEP_REAL_VOICE_COMMANDS_META["cau_7_dong_het_cua"]["transcript"],
            engine=engine,
        )
    assert out7["ok"] is True
    assert engine.devices["main_door"]["state"] == "CLOSED"


def test_duplicate_voice_gate_blocks_sep_real_voice_from_tier2_tier3_enrollment(
    vm: VoiceAuthManager,
) -> None:
    """Chặn tuyệt đối việc lấy giọng thật của Sếp để đăng ký cho tài khoản Cấp 2 hoặc Cấp 3."""
    p1 = ROOT_DIR / SEP_REAL_VOICE_COMMANDS_META["cau_1_xin_chao_chu_nha_cap1"]["file"]
    with wave.open(str(p1), "rb") as w:
        pcm_bytes = w.readframes(w.getnframes())

    for target_tier in (2, 3):
        dup = vm.check_duplicate_voice_gate(
            feat_s1=pcm_bytes,
            target_tier=target_tier,
            target_user_id=f"test_dup_tier_{target_tier}",
        )
        assert dup.is_duplicate is True
        assert dup.matched_tier == 1
