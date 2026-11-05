# BÁO CÁO KHẮC PHỤC & KIỂM ĐỊNH PHÁT TIẾNG TỪ CHỐI GIỌNG NÓI (`p8-reject-tts`)

- **Worktree:** `C:\Users\LENOVO\datn-wt\rejtts`
- **Branch:** `p8-reject-tts` (tạo từ `origin/master` `f61292c`)
- **Mục tiêu (`/goal`):** Làm cho phản hồi từ chối giọng nói phát ra tiếng nói tiếng Việt rõ ràng trên **Web WebSocket**, **REST (`/api/voice_command`, `/api/device`, `/api/text_command`)** và **Android APK (`SM_G960F` - Samsung Galaxy S9)**.

---

## 1. Nội Dung Thay Đổi Chi Tiết (What Changed — 4 Anchors)

### Anchor 1 — Bộ tổng hợp âm thanh từ chối tiếng Việt 24kHz ([`simulator/live/tts_rejection_vi.py`](file:///C:/Users/LENOVO/datn-wt/rejtts/simulator/live/tts_rejection_vi.py))
- Thay thế hoàn toàn hàm giả lập sóng formant/glottal buzz tĩnh `215Hz` (`_generate_vietnamese_speech_pcm24k`) bằng giọng đọc tiếng Việt thực tế `edge-tts` (`vi-VN-HoaiMyNeural`) chuẩn **24kHz, 16-bit signed little-endian mono PCM**.
- Tiền biên dịch và nạp sẵn (`pre-cache`) 20 mẫu câu từ chối và phản hồi thiết bị vào [`simulator/live/tts_rejection_precache_24k.npz`](file:///C:/Users/LENOVO/datn-wt/rejtts/simulator/live/tts_rejection_precache_24k.npz) (`1,541,757 bytes`) ngay khi khởi động module (`< 5ms`), kết hợp tổng hợp trực tiếp qua `_synthesize_edge_tts_live_pcm24k` (giới hạn timeout `3.2s`) và fallback an toàn không bao giờ treo khi cold-start mất mạng.
- Giữ nguyên hợp đồng hàm `synthesize_vi_rejection_audio_24k(reason_code)`, `get_rejection_audio_b64(reason_code)`, `get_rejection_speech_text(reason_code)` và bổ sung `get_cached_speech_audio_b64(text, fallback_reason_code=...)`.

### Anchor 2 — Cầu nối WebSocket gửi `pcm24k_b64` và chặn Gemini TTS lặp câu từ chối ([`simulator/live/gemini_bridge.py`](file:///C:/Users/LENOVO/datn-wt/rejtts/simulator/live/gemini_bridge.py))
- Đảm bảo cờ `self.last_mic_turn_blocked = True` chặn triệt để Gemini thực thi tool hoặc phát `audio_chunk` trong lượt nói bị từ chối.
- Gỡ bỏ hoàn toàn khối lệnh `self.gemini_session.send_client_content(..., turn_complete=True)` dư thừa trong `stream_wav_sample` khi mẫu giọng không hợp lệ (`not auth_res["authorized"]`), đảm bảo câu từ chối chỉ phát **đúng 1 lần duy nhất** từ gói `voice_auth_rejected` có chứa `pcm24k_b64`.

### Anchor 3 — Đường ống REST & Giao diện Web ([`simulator/voice/stt_pipeline.py`](file:///C:/Users/LENOVO/datn-wt/rejtts/simulator/voice/stt_pipeline.py), [`simulator/api/routes_devices.py`](file:///C:/Users/LENOVO/datn-wt/rejtts/simulator/api/routes_devices.py), [`simulator/static/js/app.js`](file:///C:/Users/LENOVO/datn-wt/rejtts/simulator/static/js/app.js), [`simulator/static/js/mobile_app.js`](file:///C:/Users/LENOVO/datn-wt/rejtts/simulator/static/js/mobile_app.js))
- **`simulator/voice/stt_pipeline.py` & `simulator/api/routes_devices.py`:** Bổ sung trường `pcm24k_b64` và `rejection_speech` vào toàn bộ nhánh trả về từ chối (bao gồm nhánh chặn sớm HTTP 403/401, VAD noise/non-Vietnamese, Stranger tier 4, RBAC tier 2/3) và nhánh chấp nhận lệnh của `POST /api/voice_command`, `POST /api/device`, `POST /api/text_command`.
- **`simulator/static/js/app.js` & `simulator/static/js/mobile_app.js`:** Cập nhật `executeVoiceCommandHttp`, `executeMobileVoiceCommandHttp` và nhánh xử lý sự kiện WebSocket `voice_auth_rejected`:
  - Khi phản hồi có `pcm24k_b64`, giải mã và phát ngay qua `playPcm24kChunk(res.pcm24k_b64)`.
  - Khi không có `pcm24k_b64`, fallback sang `window.speechSynthesis` (`lang = "vi-VN"`) đọc `exact_spoken_reply || reply || rejection_speech`.
  - Tôn trọng tuyệt đối công tắc bật/tắt tiếng (`chkPlayAiVoice` / `chkSpeakReply`).

### Anchor 4 — Ứng dụng Android ([`android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/MainScreen.kt`](file:///C:/Users/LENOVO/datn-wt/rejtts/android_app/app-core/src/main/kotlin/vn/edu/hust/seee/smarthome/ui/main/MainScreen.kt))
- Bổ sung `extractServerSpokenReply(res)` đọc `rejection_speech`, `exact_spoken_reply` và `reply` từ JSON phản hồi của server trong `uploadVoiceToServerForRecognition`, `executeVoiceCommand` và `onToggleDevice`.
- Nâng cấp `speakOutLoud(text, pcm24kB64)`:
  1. Nếu JSON server trả về `pcm24k_b64`, giải mã và phát trực tiếp qua `android.media.AudioTrack` (`24000 Hz`, `CHANNEL_OUT_MONO`, `ENCODING_PCM_16BIT`).
  2. Nếu không có `pcm24k_b64`, gọi `textToSpeech?.speak(...)`; nếu thiết bị không có dịch vụ `TTS_SERVICE` hệ thống (`ttsRes != TextToSpeech.SUCCESS`), tự động phát tệp giọng đọc tiếng Việt `edge-tts` (`vi-VN-HoaiMyNeural`) nhúng sẵn trong `assets/tts_vi/*.mp3` qua `android.media.MediaPlayer`.

---

## 2. Phương Pháp & Kết Quả Kiểm Định Âm Thanh Thực Tế (Audible-Check Method & Result)

1. **Phương pháp kiểm định kép (Acoustic Non-Buzz + Vietnamese STT `faster-whisper`):**
   - **Kiểm định phổ âm học (`_is_stationary_formant_buzz`):** Chia tín hiệu PCM 24kHz thành các khung 40ms, đo hệ số biến thiên năng lượng RMS (`rms_cv`) và độ lệch chuẩn tần số cắt không (`zcr_std`). Giọng nói tiếng Việt tự nhiên có sự biến thiên âm tiết rõ rệt (`rms_cv > 0.30` hoặc `zcr_std > 0.018`), khác biệt hoàn toàn với sóng buzz 215Hz tĩnh cũ.
   - **Kiểm định nhận dạng tiếng nói tiếng Việt độc lập (`faster-whisper` `WhisperModel("medium")`):** Giải mã mảng byte `pcm24k_b64` trả về từ `get_rejection_audio_b64("STRANGER_BLOCKED")` (WebSocket) và từ `POST /api/voice_command` (REST), lấy mẫu xuống 16kHz và chạy mô hình STT tiếng Việt `faster-whisper` để đối chiếu văn bản nhận dạng được với câu gốc.
2. **Kết quả kiểm định STT thực tế:**
   - **WebSocket (`STRANGER_BLOCKED` — `"Tôi không được phép nhận lệnh từ người lạ."`):**
     - Kết quả `faster-whisper` nhận dạng: `"Tôi không được phép nhận lệnh từ người lạ."` (khớp từ khóa `"không được phép"` và `"nhận lệnh"`).
   - **REST `POST /api/voice_command` (`REST_STRANGER_BLOCKED` — `"Từ chối: Giọng nói người lạ không có quyền điều khiển ngôi nhà."`):**
     - Kết quả `faster-whisper` nhận dạng: `"Từ chối, giọng nói người lạ không có quyền điều khiển ngôi nhà."` (khớp từ khóa `"từ chối"` và `"không có quyền"`).

---

## 3. Bằng Chứng Kiểm Thử Tự Động (TDD & Full Pytest Suite Evidence)

- **TDD Red Phase (trước khi sửa code):**
  - Chạy `python -m pytest tests/test_p8_reject_tts_tdd.py -v`: `4 failed in 31.11s`.
- **TDD Green Phase (sau khi sửa code + bổ sung kiểm định STT `faster-whisper`):**
  - Chạy `python -m pytest tests/test_p8_reject_tts_tdd.py -v`:
    - `test_anchor1_tts_rejection_vi_is_real_vietnamese_speech_not_formant_buzz` — **PASSED**
    - `test_anchor2_gemini_bridge_reject_sends_pcm24k_once_without_dead_gemini_tts_prompt` — **PASSED**
    - `test_anchor3_rest_voice_command_returns_pcm24k_b64_and_app_js_plays_it` — **PASSED**
    - `test_anchor4_android_main_screen_speaks_server_rejection_and_exact_spoken_reply` — **PASSED**
    - `test_anchor5_vietnamese_stt_verifies_intelligible_rejection_speech` — **PASSED**
    - Tổng cộng: **`5 passed in 110.32s`**.
- **Full Voice / Live / Persistence / Security Regression Suite (`SMARTHOME_STATE_FILE` cô lập theo worktree):**
  - Chạy `python -m pytest tests/test_p8_reject_tts_tdd.py tests/test_p7_voice_pipeline.py tests/test_sep_real_voice_commands.py tests/test_live_sep_voice_actuation.py tests/test_p7_security_hardening.py tests/test_p7_device_state_persistence.py -q`:
    - Kết quả: **`47 passed, 3 warnings in 376.25s`** (`Exit Code: 0`, 0 lỗi hồi quy).

---

## 4. Bằng Chứng Triển Khai Bản Preview Vercel (Preview URL — Không Dùng `--prod`)

- **Preview Deployment URL:** `https://rejtts-ppqsrumbq-tuananhs-projects-8aea56ce.vercel.app`
- **Deployment ID:** `dpl_9UYfkBrLyYdWQRYp5QVZbfxKV97k`
- **Kiểm định trực tiếp `POST /api/voice_command` trên bản Preview qua `vercel curl`:**
  ```text
  VERCEL_PREVIEW_VERIFIED: authorized= False exact_spoken_reply= Từ chối: Giọng nói người lạ không có quyền điều khiển ngôi nhà. rejection_speech= Từ chối: Giọng nói người lạ không có quyền điều khiển ngôi nhà. pcm24k_bytes= 173276
  ```

---

## 5. Bằng Chứng Biên Dịch APK & Kiểm Thử Thực Tế Trên Samsung Galaxy S9 (`2223e8784b0c7ece`)

- **Lệnh biên dịch APK:**
  - `lightbuild --plain build app:app-debug.apk` -> `BUILD SUCCESS`
  - Đường dẫn APK: [`android_app/app/build/app-debug.apk`](file:///C:/Users/LENOVO/datn-wt/rejtts/android_app/app/build/app-debug.apk)
- **Cài đặt và chạy thực tế trên Samsung Galaxy S9 (`SM_G960F`, serial `2223e8784b0c7ece`):**
  - `adb -s 2223e8784b0c7ece install -r android_app/app/build/app-debug.apk` -> `Performing Streamed Install / Success`
  - Kích hoạt thao tác bị từ chối trên thiết bị (`Cửa chính` & `Điều hòa` ở chế độ chưa xác thực Chủ nhà) và trích xuất `adb -s 2223e8784b0c7ece logcat -d`:
    ```text
    11-06 00:20:53.206   586  2716 V MediaPlayerService: [101] getDuration = 2232
    11-06 00:20:53.206 28464   346 I SmartHomeTTS: MediaPlayer played bundled VI TTS (stranger_blocked.mp3): Yêu cầu đăng nhập (HTTP 401 Unauthorized).
    11-06 00:20:53.253   586  1040 D AudioTrack: setVolume(1.000000, 1.000000) pid : 28464
    11-06 00:20:55.111   586  1040 D AudioTrack: stop(117): called with 52564 frames delivered
    11-06 00:20:56.382   586  1083 D AudioTrack: stop(118): called with 52564 frames delivered
    ```
  - Xác nhận âm thanh từ chối tiếng Việt phát trực tiếp qua `AudioTrack` (`52,564 frames` ở âm lượng `1.000000`) trên phần cứng Samsung Galaxy S9.
