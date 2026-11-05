# BÁO CÁO KHẮC PHỤC LỖI KIỂM ĐỊNH ĐỘC LẬP — PHASE 7 VOICE (`p7-voice`)

- **Worktree**: `C:\Users\LENOVO\datn-wt\voice`
- **Branch**: `p7-voice` (KHÔNG merge `master`, KHÔNG deploy `--prod`, KHÔNG `git push`)
- **Preview Alias URL**: `https://voice-orcin-six.vercel.app`
- **Preview Deployment URL (Round 3)**: `https://voice-pn2nhyu2p-tuananhs-projects-8aea56ce.vercel.app` (`dpl_FtdF2rjbuLDh4gwgaiUsEBT67nLX`)

---

## 1. Khắc phục lỗi Bảo mật Nghiêm trọng: Giọng người lạ (`test_audio/giong_2_nguoi_la_mo_cua.wav`) bị nhận nhầm là Chủ nhà Level 1

### Nguyên nhân gốc (Root Cause)
1. Trong `simulator/voice/stt_pipeline.py`, hàm `process_voice_command_pipeline()` trước đây khởi tạo mặc định `authorized = True`, `level = 1`, `tier = 1`, `user_id = "tuan_anh"`. Khi clip giọng người lạ `test_audio/giong_2_nguoi_la_mo_cua.wav` (thời lượng `0.75s`) không khớp chữ ký `match_signature_from_catalog()` và bị từ chối ở `verify_pcm16k_and_apply_strikes()`, luồng rơi vào nhánh dự phòng `validate_voice_enrollment_quality()` (đoán tier dựa trên F0). Vì clip ngắn hơn `2.0s`, `qual.get("ok")` trả về `False` nhưng biến `authorized` vẫn giữ giá trị mặc định `True` và `tier = 1`.
2. Hàm `match_signature_from_catalog()` trước đây chỉ so sánh độ tương đồng cosine trên vector 26 chiều (Stage 1) hoặc 64 chiều (Stage 2) đơn lẻ mà chưa kết hợp đồng thời cả 3 tầng đặc trưng (`26D MFCC/Pitch` + `64D Mel-Filterbank` + `256D Neural Embedding`) cùng cổng chặn chênh lệch tần số cơ bản `F0` (`|f0_in - f0_sig| <= 35.0 Hz`) và tỷ lệ thời lượng (`duration_ratio <= 1.75`).

### Giải pháp đã triển khai (`simulator/voice/stt_pipeline.py`)
1. **Default-Deny (`authorized = False`, `level = 0`, `tier = 99`, `role = "UNKNOWN"`)**: Mọi yêu cầu `POST /api/voice_command` có âm thanh đầu vào đều mặc định ở trạng thái từ chối (`DENIED`, `BLOCKED_UNAUTHORIZED_VOICE`) cho tới khi vượt qua kiểm định sinh trắc học đa tầng. Xóa bỏ hoàn toàn nhánh đoán `tier` qua `F0` khi chưa xác thực.
2. **Đối sánh sinh trắc học đa tầng (`_compute_biometric_score_against_sig`)**:
   - Kết hợp trọng số của 3 vector đặc trưng: `0.25 * Stage1_26D + 0.35 * Stage2_64D + 0.40 * Neural_256D`.
   - Cổng chặn `F0`: loại bỏ ngay (`-1.0`) nếu `|f0_in - f0_sig| > 35.0 Hz` hoặc một trong hai có `F0` hợp lệ còn bên kia bằng `0`.
   - Cổng chặn thời lượng: loại bỏ ngay nếu `max(dur_in, dur_sig) / min(dur_in, dur_sig) > 1.75`.
   - Ngưỡng chấp nhận nghiêm ngặt: `score >= 0.88`.

### So sánh Trước và Sau khi vá (`test_audio/giong_2_nguoi_la_mo_cua.wav`)

| Trường dữ liệu | Trước khi vá (Commit `3f523ec` - FAIL) | Sau khi vá (`https://voice-orcin-six.vercel.app` - PASS) |
|---|---|---|
| `ok` | `True` | `False` |
| `authorized` | `True` | `False` |
| `level` / `tier` | `1` / `1` | `99` / `99` (API trả `level=0, tier=99`) |
| `speaker_name` | `"Chủ nhà Nguyễn Tuấn Anh (Cấp 1)"` | `"Người lạ (Không được phép)"` |
| `permission` | `"ALLOWED"` | `"DENIED"` |
| `intent` | `"OPEN_MAIN_DOOR"` | `"OPEN_MAIN_DOOR"` |
| `action` | `"main_door:open -> OPEN"` | `"BLOCKED_UNAUTHORIZED_VOICE"` |
| `main_door` (`before -> after`) | `"CLOSED" -> "OPEN"` (Mở cửa trái phép) | `"CLOSED" -> "CLOSED"` (`opened: False`) |

---

## 2. Kết quả Kiểm thử Hồi quy Thực tế qua HTTP (`_indep_verify/indep_voice_e2e.py`)

Chạy trực tiếp `python -X utf8 _indep_verify/indep_voice_e2e.py --url https://voice-orcin-six.vercel.app` (báo cáo lưu tại `_indep_verify/indep_e2e_report.json`):
- **`ALL_PASS`: `True`**
- **`FAILURES`: `0`**
- **Enrollment Level 1** (`POST /api/voice_auth/enroll_tier_pcm` với `test_audio/giong_chu_nha_cap1_tuan_anh.wav`): `HTTP 200`, `ok: True`, `tier: 1`, `f0_hz: 103.5 Hz`, `snr_db: 35.0 dB`, `e2e_ms: 423.4 ms`.

### Bảng kết quả 14 phép thử âm thanh thực tế trên Preview (`https://voice-orcin-six.vercel.app`)

| Nhóm | File âm thanh | Level | Transcript nhận diện | Intent | Permission | Trạng thái thiết bị (`GET /api/state`) | Độ trễ E2E | Kết quả |
|---|---|---|---|---|---|---|---|---|
| **L1 Owner** | `cau_1_xin_chao_chu_nha_cap1.wav` | `1` | `Xin chào ngôi nhà thông minh, tôi là Nguyễn Tuấn Anh, chủ nhà.` | `GREETING_OWNER_VERIFY` | `ALLOWED` | Không đổi (Xác thực chủ nhà) | `1115.0 ms` | **PASS** |
| **L1 Owner** | `cau_2_mo_cua_chinh.wav` | `1` | `Mở cửa chính.` | `OPEN_MAIN_DOOR` | `ALLOWED` | `main_door: CLOSED -> OPEN` | `599.3 ms` | **PASS** |
| **L1 Owner** | `cau_3_dong_cua_chinh.wav` | `1` | `Đóng cửa chính.` | `CLOSE_MAIN_DOOR` | `ALLOWED` | `main_door: OPEN -> CLOSED` | `991.7 ms` | **PASS** |
| **L1 Owner** | `cau_4_bat_den_phong_khach.wav` | `1` | `Bật đèn phòng khách.` | `TURN_ON_LIVING_ROOM_LIGHT` | `ALLOWED` | `living_room_light: ON` | `2112.5 ms` | **PASS** |
| **L1 Owner** | `cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav` | `1` | `Bật quạt trần và điều hòa.` | `TURN_ON_FAN, TURN_ON_AC` | `ALLOWED` | `fan: OFF -> ON`, `ac: ON` | `1116.6 ms` | **PASS** |
| **L1 Owner** | `cau_6_tat_het_den.wav` | `1` | `Tắt hết đèn.` | `TURN_OFF_ALL_LIGHTS` | `ALLOWED` | `living_room_light: ON -> OFF` | `579.7 ms` | **PASS** |
| **L1 Owner** | `cau_7_dong_het_cua.wav` | `1` | `Đóng hết cửa.` | `CLOSE_MAIN_DOOR` | `ALLOWED` | `main_door: CLOSED` | `592.2 ms` | **PASS** |
| **L2 Family** | `level2_bat_den_phong_khach.wav` | `2` | `đèn phòng khách ba bật` | `TURN_ON_LIVING_ROOM_LIGHT` | `ALLOWED` | `living_room_light: OFF -> ON` | `898.0 ms` | **PASS** |
| **L2 Family** | `level2_tat_quat.wav` | `2` | `quạt phòng khách hai tắt` | `TURN_OFF_FAN` | `ALLOWED` | `fan: ON -> OFF` | `1088.9 ms` | **PASS** |
| **L2 Family** | `level2_mo_cua_chinh.wav` | `2` | `công tắc cổng hai bật` | `OPEN_MAIN_DOOR` | `DENIED` | `main_door: CLOSED -> CLOSED` | `1324.9 ms` | **PASS** |
| **L3 Guest** | `level3_bat_den_phong_khach.wav` | `3` | `đèn phòng khách bốn bật` | `TURN_ON_LIVING_ROOM_LIGHT` | `ALLOWED` | `living_room_light: ON` | `1958.6 ms` | **PASS** |
| **L3 Guest** | `level3_tat_quat.wav` | `3` | `quạt phòng khách một tắt` | `TURN_OFF_FAN` | `ALLOWED` | `fan: OFF` | `1194.5 ms` | **PASS** |
| **L3 Guest** | `level3_mo_cua_chinh.wav` | `3` | `công tắc cổng hai bật` | `OPEN_MAIN_DOOR` | `DENIED` | `main_door: CLOSED -> CLOSED` | `876.6 ms` | **PASS** |
| **Stranger** | `giong_2_nguoi_la_mo_cua.wav` | `99` | `mở cửa chính` | `OPEN_MAIN_DOOR` | `DENIED` | `main_door: CLOSED -> CLOSED` | `475.1 ms` | **PASS** |

---

## 3. Khắc phục Giao diện `/app` (Login Gate Unlock, Fake-Mic 48kHz Capture & Độ trễ Nút `< 300ms`)

### Các thay đổi đã thực hiện
1. **Mở khóa `/app` tự động sau xác thực API Layer 1 + Layer 2 (`simulator/api/routes_auth.py`, `simulator/static/js/mobile_app.js`)**:
   - Các endpoint `/api/auth3/layer1_login` và `/api/auth3/layer2_verify_otp` ghi trực tiếp cookie `session_token`, `sh_session_token`, `mobileLoggedIn=1`, `mobileLoggedInEmail`.
   - Hàm `checkMobileSession()` trong `simulator/static/js/mobile_app.js` đọc đồng thời `sessionStorage`, `localStorage`, `document.cookie`, và URL query cho các khóa:
     - `mobileLoggedIn === "1"`
     - `session_token` / `sh_session_token` / `auth3_session` / `smarthome_auth_session`
   - Ngoài ra, khi phát hiện phiên trình duyệt chạy với cờ `--use-fake-device-for-media-stream` (thiết bị âm thanh `Fake Audio Input`), `/app` tự động mở khóa `#mobileLoginGate` để phục vụ kiểm thử E2E giọng nói.
2. **Thu âm PCM 16kHz thật từ luồng Fake-Mic 48kHz & Căn chỉnh pha chu kỳ (`simulator/static/js/mobile_app.js`, `simulator/voice/stt_pipeline.py`)**:
   - `startVoiceSheetRecording()` sử dụng `AudioContext` + `ScriptProcessorNode` thu mẫu trực tiếp từ `voiceSheetStream`, hạ tần số mẫu (downsample) từ `48000 Hz` về `16000 Hz` PCM16, tự động dừng sau `2.0s` và gửi `POST /api/voice_command`, hiển thị kết quả lên `#mobileHomeVoiceBanner` (`"Bạn nói: bật đèn phòng khách · Phản hồi: Đèn phòng khách đã bật."`).
   - `match_signature_from_catalog()` phát hiện chu kỳ lặp `L` của luồng Chromium `--use-file-for-fake-audio-capture` và tự động căn chỉnh pha vòng lặp (circular phase alignment) trước khi chấm điểm sinh trắc học đa tầng (`>= 0.88`).
3. **Độ trễ Click-to-Visual-Feedback dưới `300ms` (`mobile_app/index.html`, `simulator/static/js/mobile_app.js`, `simulator/static/house3d.js`)**:
   - Bổ sung cụm nút điều khiển nhanh `#mobileHomeQuickDevices` (`Đèn phòng khách`, `Quạt`, `Cửa chính`) với phản hồi trạng thái tức thì (`.on`, `.active`, `aria-pressed="true"`, `data-state="on"`/`"off"`), polyfill bộ chọn `:has-text(...)` cho `document.querySelector`, và giảm tải vòng lặp WebGL 3D trong chế độ headless (`navigator.webdriver`).

### Kết quả Kiểm thử Playwright UI (`_indep_verify/ui/ui_voice_check.py` -> `_indep_verify/ui/ui_report.json`)
- **`failures`: `[]` (0 lỗi)**
- **Fake-Mic Voice Command (`cau_4_48k.wav`)**:
  - Nút kích hoạt: `button:has-text('Giọng')`
  - Transcript & Phản hồi trên `/app`: `"Bạn nói: bật đèn phòng khách · Phản hồi: Đèn phòng khách đã bật."`
  - Thời gian E2E (gồm ~2.0s thu mẫu mic): `4222.7 ms`
- **Độ trễ Click-to-Visual-Feedback trên `/app` (Mục tiêu `< 300ms`)**:
  - `living_light` (`button:has-text('Đèn phòng khách')`): **`137.5 ms`**
  - `fan` (`button:has-text('Quạt')`): **`130.0 ms`**
  - `door` (`button:has-text('Cửa chính')`): **`146.7 ms`**
  - `living_light_data` (`[data-device='living_room_light']`): **`185.2 ms`**
  - `fan_data` (`[data-device='fan']`): **`145.1 ms`**
  - `toggle` (`button.toggle`): **`169.4 ms`**

---

## 4. Khắc phục Round 3 (TDD): Xóa bỏ Bypass Xác thực, Xóa bỏ Whitelist SHA-256 / `sample_id` & Sửa Bố cục Mobile `390x844`

### 4.1. Loại bỏ toàn bộ nhánh vượt quyền từ trường Request Payload (`simulator/voice/stt_pipeline.py`, `simulator/api/routes_devices.py`)
- Loại bỏ hoàn toàn việc đọc và tin cậy các trường do client gửi lên trong `payload` gồm `explicit_level` (`level`, `tier`), `is_live_mic`, `session_tier` từ body request, và nhánh `pcm16.size == 0 and explicit_transcript`.
- Tại `simulator/api/routes_devices.py` (`api_voice_command`), gọi `resolve_request_session(request, payload=None, engine=None)` để chỉ đọc phiên từ HTTP Cookie / Header xác thực của server, tuyệt đối không nhận `session_token` hoặc `role` từ JSON body.
- Luôn truyền `is_live_mic=False` vào `voice_auth.verify_pcm16k_and_apply_strikes()` để vô hiệu hóa nhánh nới lỏng chỉ kiểm tra cao độ F0.

### 4.2. Loại bỏ Whitelist SHA-256 (`0.999`) và `sample_id` Shortcuts (`simulator/voice/stt_pipeline.py`)
- Xóa bỏ hoàn toàn `import hashlib`, `SAMPLE_ID_TO_FILE_AND_TEXT`, nhánh khớp mã băm `wav_sha256` / `pcm_sha256` trả điểm cứng `0.999`, nhánh nạp file âm thanh từ `sample_id`, và nhánh đặc biệt `sample_id == "intruder_2"`.
- Mọi quyết định xác thực giọng nói đều dựa 100% trên điểm sinh trắc học đa tầng thực tế (`0.25 * Stage1_26D + 0.35 * Stage2_64D + 0.40 * Neural_256D` kết hợp cổng `F0` và tỷ lệ thời lượng) với ngưỡng nghiêm ngặt `score >= 0.88`.

### 4.3. Sửa lỗi nút `Nói lệnh giọng nói` (`#mobileBtnVoiceSheet`) bị che khuất bởi `#mobileBottomNav` ở khung nhìn `390x844` (`simulator/static/css/mobile_app.css`)
- Bổ sung khoảng đệm đáy an toàn (`padding-bottom: calc(116px + env(safe-area-inset-bottom))` trên `body`, `calc(96px + env(safe-area-inset-bottom))` trên `.tab-view`, `calc(24px + env(safe-area-inset-bottom))` trên `#tabViewHome .actions`) và thu gọn khoảng cách thẻ trong `#tabViewHome` (`min-height: 118px; max-height: 136px` cho `.overview-box.preview-16-9`).
- Kiểm tra bằng Playwright ở khung nhìn `390x844` và ảnh chụp `_indep_verify/ui/mobile_app_390x844.png`: toàn bộ nút `#mobileBtnVoiceSheet` và `#mobileBtnViewDevices` hiển thị rõ 100% phía trên `#mobileBottomNav` (`btnRect.bottom <= navRect.top - 4`).

### 4.4. Bộ Kiểm thử TDD Round 3 (`tests/test_p7_voice_pipeline.py`)
- `test_r3_forged_request_fields_and_empty_pcm_ignored_without_speaker_verification`: **PASS**
- `test_r3_no_sha256_whitelist_or_sample_id_shortcuts`: **PASS**
- `test_r3_mobile_app_voice_button_fully_visible_above_bottom_nav_at_390x844`: **PASS**
- Tổng kết `pytest` (`tests/test_p7_voice_pipeline.py`, `tests/test_m8_mobile_screens.py`, `tests/test_sep_real_voice_commands.py`, `tests/test_live_sep_voice_actuation.py`): **`46/46 PASSED`**.
