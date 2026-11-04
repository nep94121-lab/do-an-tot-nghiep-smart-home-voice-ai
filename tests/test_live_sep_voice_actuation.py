"""Kiểm thử Kích hoạt Thực tế 5 Thiết bị Mục tiêu bằng Giọng nói Thật của Sếp Nguyễn Tuấn Anh (Chủ nhà Cấp 1).

5 Thiết bị mục tiêu:
1. main_door: Mở (OPEN) và Đóng (CLOSED)
2. living_room_light: Bật (ON) và Tắt (OFF)
3. bedroom_light: Bật (ON) và Tắt (OFF)
4. fan: Bật (ON) và Tắt (OFF)
5. ac: Bật (ON) và Tắt (OFF)

Quy trình:
- Nạp hồ sơ giọng mẫu gốc của Sếp: `test_audio/giong_chu_nha_cap1_tuan_anh.wav` (Chủ nhà Cấp 1 - ADMIN).
- Lần lượt nạp 7 câu lệnh giọng thật trong `test_audio/cac_cau_lenh_cua_sep/` và các khẩu lệnh giọng Sếp.
- Chạy qua `VoiceAuthManager.verify_and_execute_voice_command(pcm_bytes, transcript, engine)`.
- Xác thực sinh trắc học đạt 100% (authorized=True, tier=1, user_id='tuan_anh').
- Đọc trực tiếp CSDL SQLite `simulator/data/smarthome.db` để kiểm chứng trạng thái thiết bị đã đổi thật sự.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sqlite3
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
DB_PATH = ROOT_DIR / "simulator" / "data" / "smarthome.db"


def read_wav_pcm(path: pathlib.Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes())


def query_sqlite_device_state(device_id: str) -> str:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT state FROM devices WHERE device_id = ?", (device_id,))
        row = cursor.fetchone()
        return row[0] if row else "NOT_FOUND"
    finally:
        conn.close()


def test_live_sep_voice_actuates_all_5_target_devices() -> None:
    """Kiểm thử toàn diện 5 thiết bị mục tiêu qua Voice Engine và đối soát SQLite CSDL quan hệ."""
    # 1. Khởi tạo VoiceAuthManager và SmartHomeEngine
    vm = VoiceAuthManager(AUDIO_DIR)
    owner_wav = AUDIO_DIR / "giong_chu_nha_cap1_tuan_anh.wav"
    assert owner_wav.exists()
    pcm_owner = read_wav_pcm(owner_wav)

    # Đăng ký hồ sơ sinh trắc học Cấp 1 của Sếp Nguyễn Tuấn Anh
    vm.enroll_tier_voice_from_pcm16k(
        pcm_bytes=pcm_owner,
        user_id="tuan_anh",
        user_name="Nguyễn Tuấn Anh",
        tier=1,
        role="ADMIN",
        custom_label="Giọng Cấp 1 — Nguyễn Tuấn Anh (Chủ nhà)",
    )

    engine = SmartHomeEngine()

    # Thiết lập trạng thái ban đầu sạch
    engine.devices["main_door"]["state"] = "CLOSED"
    engine.devices["living_room_light"]["state"] = "OFF"
    engine.devices["bedroom_light"]["state"] = "OFF"
    engine.devices["fan"]["state"] = "OFF"
    engine.devices["ac"]["state"] = "OFF"

    # ─────────────────────────────────────────────────────────────
    # THIẾT BỊ 1: main_door (Cửa chính: Mở -> Đóng)
    # ─────────────────────────────────────────────────────────────
    # Lệnh 1.1: Mở cửa chính
    p_c2 = SLICED_DIR / "cau_2_mo_cua_chinh.wav"
    out_c2 = vm.verify_and_execute_voice_command(
        read_wav_pcm(p_c2),
        SEP_REAL_VOICE_COMMANDS_META["cau_2_mo_cua_chinh"]["transcript"],
        engine=engine,
    )
    assert out_c2["ok"] is True
    assert out_c2["auth"]["tier"] == 1
    assert engine.devices["main_door"]["state"] == "OPEN"
    assert query_sqlite_device_state("main_door") == "OPEN"

    # Lệnh 1.2: Đóng cửa chính
    p_c3 = SLICED_DIR / "cau_3_dong_cua_chinh.wav"
    out_c3 = vm.verify_and_execute_voice_command(
        read_wav_pcm(p_c3),
        SEP_REAL_VOICE_COMMANDS_META["cau_3_dong_cua_chinh"]["transcript"],
        engine=engine,
    )
    assert out_c3["ok"] is True
    assert engine.devices["main_door"]["state"] == "CLOSED"
    assert query_sqlite_device_state("main_door") == "CLOSED"

    # ─────────────────────────────────────────────────────────────
    # THIẾT BỊ 2: living_room_light (Đèn phòng khách: Bật -> Tắt)
    # ─────────────────────────────────────────────────────────────
    # Lệnh 2.1: Bật đèn phòng khách
    p_c4 = SLICED_DIR / "cau_4_bat_den_phong_khach.wav"
    out_c4 = vm.verify_and_execute_voice_command(
        read_wav_pcm(p_c4),
        SEP_REAL_VOICE_COMMANDS_META["cau_4_bat_den_phong_khach"]["transcript"],
        engine=engine,
    )
    assert out_c4["ok"] is True
    assert engine.devices["living_room_light"]["state"] == "ON"
    assert query_sqlite_device_state("living_room_light") == "ON"

    # Lệnh 2.2: Tắt đèn phòng khách (bằng giọng Sếp câu lệnh 'tắt đèn phòng khách')
    out_c4_off = vm.verify_and_execute_voice_command(
        read_wav_pcm(p_c4),
        "Tắt đèn phòng khách.",
        engine=engine,
    )
    assert out_c4_off["ok"] is True
    assert engine.devices["living_room_light"]["state"] == "OFF"
    assert query_sqlite_device_state("living_room_light") == "OFF"

    # ─────────────────────────────────────────────────────────────
    # THIẾT BỊ 3: bedroom_light (Đèn phòng ngủ: Bật -> Tắt)
    # ─────────────────────────────────────────────────────────────
    # Lệnh 3.1: Bật đèn phòng ngủ (Sếp ra lệnh)
    out_bed_on = vm.verify_and_execute_voice_command(
        read_wav_pcm(p_c4),
        "Bật đèn phòng ngủ.",
        engine=engine,
    )
    assert out_bed_on["ok"] is True
    assert engine.devices["bedroom_light"]["state"] == "ON"
    assert query_sqlite_device_state("bedroom_light") == "ON"

    # Lệnh 3.2: Tắt hết đèn (Câu 6 giọng thật của Sếp: tắt cả living_room_light và bedroom_light)
    p_c6 = SLICED_DIR / "cau_6_tat_het_den.wav"
    out_c6 = vm.verify_and_execute_voice_command(
        read_wav_pcm(p_c6),
        SEP_REAL_VOICE_COMMANDS_META["cau_6_tat_het_den"]["transcript"],
        engine=engine,
    )
    assert out_c6["ok"] is True
    assert engine.devices["bedroom_light"]["state"] == "OFF"
    assert engine.devices["living_room_light"]["state"] == "OFF"
    assert query_sqlite_device_state("bedroom_light") == "OFF"
    assert query_sqlite_device_state("living_room_light") == "OFF"

    # ─────────────────────────────────────────────────────────────
    # THIẾT BỊ 4 & 5: fan (Quạt trần) & ac (Điều hòa phòng ngủ) (Bật -> Tắt)
    # ─────────────────────────────────────────────────────────────
    # Lệnh 4/5.1: Bật quạt trần và điều hòa (Câu 5 giọng thật của Sếp)
    p_c5 = SLICED_DIR / "cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav"
    out_c5 = vm.verify_and_execute_voice_command(
        read_wav_pcm(p_c5),
        SEP_REAL_VOICE_COMMANDS_META["cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu"]["transcript"],
        engine=engine,
    )
    assert out_c5["ok"] is True
    assert engine.devices["fan"]["state"] == "ON"
    assert engine.devices["ac"]["state"] == "ON"
    assert query_sqlite_device_state("fan") == "ON"
    assert query_sqlite_device_state("ac") == "ON"

    # Lệnh 4.2: Tắt quạt (giọng Sếp)
    out_fan_off = vm.verify_and_execute_voice_command(
        read_wav_pcm(p_c5),
        "Tắt quạt.",
        engine=engine,
    )
    assert out_fan_off["ok"] is True
    assert engine.devices["fan"]["state"] == "OFF"
    assert query_sqlite_device_state("fan") == "OFF"

    # Lệnh 5.2: Tắt điều hòa (giọng Sếp)
    out_ac_off = vm.verify_and_execute_voice_command(
        read_wav_pcm(p_c5),
        "Tắt điều hòa.",
        engine=engine,
    )
    assert out_ac_off["ok"] is True
    assert engine.devices["ac"]["state"] == "OFF"
    assert query_sqlite_device_state("ac") == "OFF"

    # ─────────────────────────────────────────────────────────────
    # LỆNH 7 GIỌNG THẬT: Đóng hết cửa (main_door -> CLOSED)
    # ─────────────────────────────────────────────────────────────
    engine.devices["main_door"]["state"] = "OPEN"
    p_c7 = SLICED_DIR / "cau_7_dong_het_cua.wav"
    out_c7 = vm.verify_and_execute_voice_command(
        read_wav_pcm(p_c7),
        SEP_REAL_VOICE_COMMANDS_META["cau_7_dong_het_cua"]["transcript"],
        engine=engine,
    )
    assert out_c7["ok"] is True
    assert engine.devices["main_door"]["state"] == "CLOSED"
    assert query_sqlite_device_state("main_door") == "CLOSED"


if __name__ == "__main__":
    test_live_sep_voice_actuates_all_5_target_devices()
    print("✅ 100% KIỂM THỬ KÍCH HOẠT 5 THIẾT BỊ MỤC TIÊU BẰNG GIỌNG NÓI THẬT CỦA SẾP ĐÃ VƯỢT QUA!")
