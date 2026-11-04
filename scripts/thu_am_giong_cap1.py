"""Công cụ Thu Âm Giọng Mẫu & Câu Lệnh Chủ Nhà Cấp 1 (Nguyễn Tuấn Anh) — KHÔNG GIỚI HẠN THỜI GIAN.

- Bấm '🎤 BẮT ĐẦU THU ÂM': Thu liên tục không giới hạn thời gian (nói bao lâu tùy ý).
- Bấm '⏹️ DỪNG & LƯU BẢN THU': Dừng thu, lưu file WAV 16kHz chuẩn tại:
    + test_audio/giong_chu_nha_cap1_tuan_anh.wav (file chính dùng làm mẫu & test câu lệnh)
    + test_audio/lich_su_thu_am/giong_cap1_<timestamp>.wav (lưu lịch sử mọi lần thu)
  Và tự động nạp hồ sơ giọng Cấp 1 (owner_voice_1) vào hệ thống.
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import pathlib
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
import urllib.request
import wave
import winsound

import numpy as np

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

OUT_WAV_PATH = ROOT_DIR / "test_audio" / "giong_chu_nha_cap1_tuan_anh.wav"
HISTORY_DIR = ROOT_DIR / "test_audio" / "lich_su_thu_am"
RECEIPT_JSON_PATH = ROOT_DIR / "test_audio" / "ket_qua_thu_am_cap1.json"

SAMPLE_RATE = 16000
CHANNELS = 1
BITS_PER_SAMPLE = 16

winmm = ctypes.windll.winmm
WAVE_MAPPER = ctypes.c_uint(-1).value
CALLBACK_NULL = 0
WHDR_DONE = 0x00000001


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


class WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_char_p),
        ("dwBufferLength", wintypes.DWORD),
        ("dwBytesRecorded", wintypes.DWORD),
        ("dwUser", ctypes.c_size_t),
        ("dwFlags", wintypes.DWORD),
        ("dwLoops", wintypes.DWORD),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_size_t),
    ]


winmm.waveInOpen.argtypes = [
    ctypes.POINTER(ctypes.c_void_p),
    wintypes.UINT,
    ctypes.POINTER(WAVEFORMATEX),
    ctypes.c_size_t,
    ctypes.c_size_t,
    wintypes.DWORD,
]
winmm.waveInOpen.restype = wintypes.UINT
winmm.waveInPrepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wintypes.UINT]
winmm.waveInPrepareHeader.restype = wintypes.UINT
winmm.waveInAddBuffer.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wintypes.UINT]
winmm.waveInAddBuffer.restype = wintypes.UINT
winmm.waveInStart.argtypes = [ctypes.c_void_p]
winmm.waveInStart.restype = wintypes.UINT
winmm.waveInStop.argtypes = [ctypes.c_void_p]
winmm.waveInStop.restype = wintypes.UINT
winmm.waveInReset.argtypes = [ctypes.c_void_p]
winmm.waveInReset.restype = wintypes.UINT
winmm.waveInUnprepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wintypes.UINT]
winmm.waveInUnprepareHeader.restype = wintypes.UINT
winmm.waveInClose.argtypes = [ctypes.c_void_p]
winmm.waveInClose.restype = wintypes.UINT


def record_unlimited_winmm(stop_event: threading.Event, on_progress=None) -> np.ndarray:
    """Thu âm liên tục không giới hạn thời gian cho tới khi stop_event được bật."""
    num_devs = winmm.waveInGetNumDevs()
    if num_devs <= 0:
        raise RuntimeError("Không tìm thấy Microphone nào trên máy tính Windows!")

    wfx = WAVEFORMATEX()
    wfx.wFormatTag = 1  # WAVE_FORMAT_PCM
    wfx.nChannels = CHANNELS
    wfx.nSamplesPerSec = SAMPLE_RATE
    wfx.wBitsPerSample = BITS_PER_SAMPLE
    wfx.nBlockAlign = (CHANNELS * BITS_PER_SAMPLE) // 8
    wfx.nAvgBytesPerSec = SAMPLE_RATE * wfx.nBlockAlign
    wfx.cbSize = 0

    h_wave_in = ctypes.c_void_p()
    res = winmm.waveInOpen(
        ctypes.byref(h_wave_in),
        WAVE_MAPPER,
        ctypes.byref(wfx),
        0,
        0,
        CALLBACK_NULL,
    )
    if res != 0:
        raise RuntimeError(f"Không thể mở Microphone (Mã lỗi winmm: {res}). Hãy kiểm tra quyền Micro của Windows.")

    chunk_samples = SAMPLE_RATE // 4  # 0.25 giây mỗi khối
    chunk_bytes = chunk_samples * 2
    ring_size = 8  # Vòng đệm 8 buffer xoay vòng liên tục không giới hạn thời gian

    buffers = []
    headers = []
    for _ in range(ring_size):
        buf = ctypes.create_string_buffer(chunk_bytes)
        hdr = WAVEHDR()
        hdr.lpData = ctypes.cast(buf, ctypes.c_char_p)
        hdr.dwBufferLength = chunk_bytes
        hdr.dwBytesRecorded = 0
        hdr.dwUser = 0
        hdr.dwFlags = 0
        hdr.dwLoops = 0
        winmm.waveInPrepareHeader(h_wave_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
        winmm.waveInAddBuffer(h_wave_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
        buffers.append(buf)
        headers.append(hdr)

    winmm.waveInStart(h_wave_in)
    recorded_parts: list[np.ndarray] = []
    start_ts = time.time()
    cur_idx = 0

    try:
        while not stop_event.is_set():
            buf = buffers[cur_idx]
            hdr = headers[cur_idx]
            while not (hdr.dwFlags & WHDR_DONE) and not stop_event.is_set():
                time.sleep(0.015)
            if hdr.dwBytesRecorded > 0:
                raw = buf.raw[: hdr.dwBytesRecorded]
                arr = np.frombuffer(raw, dtype=np.int16).copy()
                recorded_parts.append(arr)
                if on_progress is not None and arr.size > 0:
                    rms = float(np.sqrt(np.mean((arr.astype(np.float32) / 32768.0) ** 2)))
                    elapsed = time.time() - start_ts
                    on_progress(elapsed, rms)
            if not stop_event.is_set():
                winmm.waveInUnprepareHeader(h_wave_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
                hdr.dwBytesRecorded = 0
                hdr.dwFlags = 0
                winmm.waveInPrepareHeader(h_wave_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
                winmm.waveInAddBuffer(h_wave_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
                cur_idx = (cur_idx + 1) % ring_size
    finally:
        winmm.waveInStop(h_wave_in)
        winmm.waveInReset(h_wave_in)
        for hdr in headers:
            if hdr.dwBytesRecorded > 0 and (hdr.dwFlags & WHDR_DONE):
                pass
            winmm.waveInUnprepareHeader(h_wave_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
        winmm.waveInClose(h_wave_in)

    if not recorded_parts:
        return np.zeros(0, dtype=np.int16)
    return np.concatenate(recorded_parts)


def enroll_and_save_owner_voice(pcm_arr: np.ndarray) -> dict:
    """Lưu file WAV 16kHz (không giới hạn độ dài) và đăng ký làm giọng mẫu Cấp 1 (Chủ nhà Nguyễn Tuấn Anh)."""
    from simulator.voice_auth import VoiceAuthManager, validate_voice_enrollment_quality
    from simulator.auth_3layer import get_auth_3layer_manager

    OUT_WAV_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    x_float = pcm_arr.astype(np.float32) / 32768.0
    if x_float.size > 0:
        x_float = x_float - float(np.mean(x_float))
    raw_rms = float(np.sqrt(np.mean(x_float ** 2))) if x_float.size > 0 else 0.0
    peak = float(np.max(np.abs(x_float))) if x_float.size > 0 else 0.0
    duration_sec = round(float(pcm_arr.size) / SAMPLE_RATE, 2)

    # Tự động khuếch đại chuẩn hóa (AGC) nếu Micro laptop thu âm nhỏ (RMS ~ 0.0008 - 0.06)
    if peak > 1e-4 and raw_rms < 0.07:
        gain = min(20.0, 0.68 / peak)
        x_norm = np.clip(x_float * gain, -1.0, 1.0)
        pcm_to_save = (x_norm * 32767.0).astype(np.int16)
    else:
        pcm_to_save = pcm_arr.astype(np.int16)

    pcm_bytes = pcm_to_save.tobytes()

    # Lưu ra file WAV chính và file lịch sử
    for target_path in [
        OUT_WAV_PATH,
        HISTORY_DIR / f"giong_cap1_{time.strftime('%Y%m%d_%H%M%S')}.wav",
    ]:
        with wave.open(str(target_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_bytes)

    quality = validate_voice_enrollment_quality(pcm_to_save, SAMPLE_RATE)

    va = VoiceAuthManager(ROOT_DIR / "test_audio")
    enroll_res = va.enroll_tier_voice_from_pcm16k(
        pcm_bytes=pcm_bytes,
        user_id="tuan_anh",
        user_name="Nguyễn Tuấn Anh",
        tier=1,
        role="ADMIN",
        custom_label="Giọng Cấp 1 — Nguyễn Tuấn Anh (Đã thu âm giọng thật)",
        check_duplicate=False,
    )

    mgr3 = get_auth_3layer_manager()
    res3 = mgr3.validate_and_enroll_voice(
        email="nep94121@gmail.com",
        pcm_bytes=pcm_bytes,
        source_device="Microphone Desktop (Giọng thật Cấp 1)",
    )

    # Đồng bộ lên Server 8088 nếu đang chạy
    server_synced = False
    try:
        b64_pcm = base64.b64encode(pcm_bytes).decode("ascii")
        payload = json.dumps({
            "email": "nep94121@gmail.com",
            "spoken_text": "Xin chào hệ thống Nhà Thông Minh Bách Khoa, tôi là Nguyễn Tuấn Anh đọc câu này để lưu mẫu giọng nói gốc lên máy chủ.",
            "source_device": "Microphone Desktop (Giọng thật Cấp 1)",
            "audio_pcm_b64": b64_pcm,
            "pcm16k_b64": b64_pcm,
        }).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8088/api/auth3/enroll_voice_sample",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                server_synced = True
    except Exception:
        server_synced = False

    prof_data = enroll_res.get("profile", {})
    summary = {
        "ok": bool(enroll_res.get("ok")),
        "timestamp": time.strftime("%H:%M:%S %d/%m/%Y"),
        "duration_sec": duration_sec,
        "wav_path": str(OUT_WAV_PATH),
        "wav_bytes": OUT_WAV_PATH.stat().st_size if OUT_WAV_PATH.exists() else 0,
        "raw_rms": round(raw_rms, 5),
        "f0_hz": prof_data.get("f0_hz") or quality.get("details", {}).get("f0_mean_hz", 0.0),
        "centroid_hz": prof_data.get("centroid_hz", 0.0),
        "hnr_db": prof_data.get("hnr_db", 0.0),
        "formants_hz": prof_data.get("formants_hz", []),
        "quality_check": quality,
        "auth3_status": res3.get("status"),
        "server_8088_synced": server_synced,
    }
    RECEIPT_JSON_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2).replace("\r\n", "\n") + "\n",
        encoding="utf-8",
    )
    return summary


class VoiceRecorderDesktopApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("🎙️ Thu Âm Giọng Mẫu & Câu Lệnh Cấp 1 (Không Giới Hạn Thời Gian)")
        self.root.geometry("720x520")
        self.root.configure(bg="#F4F7F6")
        self.root.attributes("-topmost", True)
        self.stop_event = threading.Event()
        self.is_recording = False

        # Căn giữa màn hình
        self.root.update_idletasks()
        w, h = 720, 520
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        title = tk.Label(
            root,
            text="🎙️ THU ÂM GIỌNG CHỦ NHÀ CẤP 1 (KHÔNG GIỚI HẠN THỜI GIAN)",
            font=("Segoe UI", 14, "bold"),
            bg="#F4F7F6",
            fg="#0F5156",
        )
        title.pack(pady=(16, 4))

        sub = tk.Label(
            root,
            text="Tài khoản: Nguyễn Tuấn Anh (nep94121@gmail.com) · Bấm Bắt đầu -> Nói thoải mái các câu lệnh -> Bấm Dừng",
            font=("Segoe UI", 10),
            bg="#F4F7F6",
            fg="#4A5568",
        )
        sub.pack(pady=(0, 10))

        prompt_frame = tk.Frame(root, bg="#E6F4F1", bd=1, relief="solid", padx=16, pady=10)
        prompt_frame.pack(fill="x", padx=26, pady=4)

        tk.Label(
            prompt_frame,
            text="Gợi ý các câu nói & câu ra lệnh để dùng làm mẫu và test hệ thống:",
            font=("Segoe UI", 9, "bold"),
            bg="#E6F4F1",
            fg="#0F5156",
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            prompt_frame,
            text=(
                "1. “Xin chào ngôi nhà thông minh, tôi là Nguyễn Tuấn Anh, Chủ nhà Cấp 1.”\n"
                "2. “Mở cửa chính cho anh” · “Khóa cửa chính lại” · “Tắt còi báo động”\n"
                "3. “Bật đèn phòng khách” · “Bật quạt trần và điều hòa phòng ngủ” · “Tắt hết đèn”"
            ),
            font=("Segoe UI", 11, "bold"),
            bg="#E6F4F1",
            fg="#1A202C",
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(6, 2))

        # Thanh đo âm lượng Micro
        meter_frame = tk.Frame(root, bg="#F4F7F6")
        meter_frame.pack(fill="x", padx=26, pady=(10, 4))
        self.meter_label = tk.Label(
            meter_frame,
            text="⏱️ Thời gian: 0.0 giây | Độ nhạy Micro: Đang chờ bấm Bắt đầu thu âm...",
            font=("Segoe UI", 10, "bold"),
            bg="#F4F7F6",
            fg="#2D3748",
        )
        self.meter_label.pack(anchor="w")

        self.progress = ttk.Progressbar(meter_frame, orient="horizontal", length=660, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(4, 4))

        # Hàng nút bấm
        btn_frame = tk.Frame(root, bg="#F4F7F6")
        btn_frame.pack(pady=10)

        self.btn_record = tk.Button(
            btn_frame,
            text="🎤 BẮT ĐẦU THU ÂM (KHÔNG GIỚI HẠN)",
            font=("Segoe UI", 12, "bold"),
            bg="#0D7A6F",
            fg="white",
            activebackground="#095C53",
            activeforeground="white",
            padx=18,
            pady=10,
            cursor="hand2",
            command=self.toggle_recording,
        )
        self.btn_record.pack(side="left", padx=6)

        self.btn_play = tk.Button(
            btn_frame,
            text="▶️ Nghe lại bản thu",
            font=("Segoe UI", 11, "bold"),
            bg="#E2E8F0",
            fg="#1A202C",
            padx=14,
            pady=10,
            cursor="hand2",
            state="disabled",
            command=self.play_recorded,
        )
        self.btn_play.pack(side="left", padx=6)

        self.btn_stop_play = tk.Button(
            btn_frame,
            text="⏹️ Dừng nghe",
            font=("Segoe UI", 10),
            bg="#EDF2F7",
            fg="#4A5568",
            padx=10,
            pady=10,
            cursor="hand2",
            command=lambda: winsound.PlaySound(None, winsound.SND_PURGE),
        )
        self.btn_stop_play.pack(side="left", padx=6)

        # Hộp trạng thái kết quả
        self.status_box = tk.Label(
            root,
            text="👉 Bấm '🎤 BẮT ĐẦU THU ÂM', nói thoải mái các câu lệnh bạn muốn, khi nào nói xong thì bấm '⏹️ DỪNG THU ÂM & LƯU'!",
            font=("Segoe UI", 10, "bold"),
            bg="#FFFFFF",
            fg="#2D3748",
            bd=1,
            relief="solid",
            padx=14,
            pady=12,
            wraplength=650,
            justify="left",
        )
        self.status_box.pack(fill="both", expand=True, padx=26, pady=(6, 16))

        if OUT_WAV_PATH.exists():
            self.btn_play.config(state="normal")

    def toggle_recording(self) -> None:
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self) -> None:
        winsound.PlaySound(None, winsound.SND_PURGE)
        self.is_recording = True
        self.stop_event.clear()
        self.btn_record.config(
            text="⏹️ DỪNG THU ÂM & LƯU MẪU GIỌNG CẤP 1",
            bg="#DC2626",
            activebackground="#B91C1C",
        )
        self.btn_play.config(state="disabled")
        self.status_box.config(
            bg="#FFFBEB",
            fg="#92400E",
            text="🔴 ĐANG THU ÂM LIÊN TỤC (KHÔNG GIỚI HẠN THỜI GIAN)...\nHãy nói thoải mái các câu lệnh của bạn. Khi nào nói xong hết thì bấm nút màu đỏ '⏹️ DỪNG THU ÂM & LƯU'!",
        )
        threading.Thread(target=self._record_worker, daemon=True).start()

    def stop_recording(self) -> None:
        if not self.is_recording:
            return
        self.btn_record.config(state="disabled", text="⏳ Đang xử lý & lưu giọng mẫu Cấp 1...")
        self.stop_event.set()

    def _on_progress(self, elapsed_sec: float, rms: float) -> None:
        level = min(100, int(rms * 18000))
        self.root.after(0, lambda: self._update_ui_progress(elapsed_sec, rms, level))

    def _update_ui_progress(self, elapsed_sec: float, rms: float, level: int) -> None:
        if not self.is_recording:
            return
        self.progress["value"] = level
        self.meter_label.config(
            text=f"🔴 ĐANG THU ÂM: {elapsed_sec:.1f} giây (Không giới hạn) | Độ nhạy Micro (RMS): {rms:.4f}"
        )

    def _record_worker(self) -> None:
        try:
            pcm_arr = record_unlimited_winmm(self.stop_event, on_progress=self._on_progress)
            summary = enroll_and_save_owner_voice(pcm_arr)
            self.root.after(0, lambda: self._on_record_done(summary))
        except Exception as exc:
            err_msg = str(exc)
            self.root.after(0, lambda: self._on_record_error(err_msg))

    def _on_record_done(self, summary: dict) -> None:
        self.is_recording = False
        self.btn_record.config(
            state="normal",
            text="🎤 BẮT ĐẦU THU ÂM MỚI (KHÔNG GIỚI HẠN)",
            bg="#0D7A6F",
            activebackground="#095C53",
        )
        self.btn_play.config(state="normal")
        self.progress["value"] = 100
        f0 = summary.get("f0_hz", 0.0)
        rms = summary.get("raw_rms", 0.0)
        dur = summary.get("duration_sec", 0.0)
        if summary.get("ok") and f0 > 0:
            self.meter_label.config(
                text=f"✅ Đã lưu bản thu dài {dur:.1f} giây | Giọng Cấp 1: F0 = {f0:.1f} Hz"
            )
            self.status_box.config(
                bg="#ECFDF5",
                fg="#065F46",
                text=(
                    f"✅ ĐÃ LƯU GIỌNG MẪU & CÂU LỆNH CHỦ NHÀ CẤP 1 THÀNH CÔNG!\n"
                    f"• Thời lượng thu âm: {dur:.1f} giây | Tần số giọng (F0): {f0:.1f} Hz | RMS gốc: {rms:.4f}\n"
                    f"• Đã lưu file WAV: {OUT_WAV_PATH.name} ({summary.get('wav_bytes', 0)} bytes)\n"
                    f"• Bạn có thể bấm '▶️ Nghe lại bản thu' để kiểm tra rồi nhắn báo lại cho AI!"
                ),
            )
        else:
            self.meter_label.config(text=f"⚠️ Bản thu ({dur:.1f}s) có âm lượng quá nhỏ hoặc quá ngắn")
            self.status_box.config(
                bg="#FEF2F2",
                fg="#991B1B",
                text=(
                    f"⚠️ Chưa bắt rõ tiếng nói trong bản thu ({dur:.1f}s, RMS = {rms:.4f}).\n"
                    f"Vui lòng thu âm ít nhất 2 giây, nói gần Micro hơn và bấm nút thu lại!"
                ),
            )

    def _on_record_error(self, err_msg: str) -> None:
        self.is_recording = False
        self.btn_record.config(
            state="normal",
            text="🎤 BẮT ĐẦU THU ÂM (KHÔNG GIỚI HẠN)",
            bg="#0D7A6F",
            activebackground="#095C53",
        )
        self.status_box.config(
            bg="#FEF2F2",
            fg="#991B1B",
            text=f"❌ Lỗi thu âm: {err_msg}",
        )

    def play_recorded(self) -> None:
        if OUT_WAV_PATH.exists():
            winsound.PlaySound(str(OUT_WAV_PATH), winsound.SND_FILENAME | winsound.SND_ASYNC)


if __name__ == "__main__":
    app_root = tk.Tk()
    app = VoiceRecorderDesktopApp(app_root)
    app_root.mainloop()
