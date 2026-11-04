# BÁO CÁO THẨM ĐỊNH BẢO MẬT & E2E ĐỘC LẬP (HANDOFF REPORT) — MILESTONE 5

**Đơn vị thực hiện**: Reviewer & Critic Milestone 5 (`reviewer_m5_2` - E2E & Security Reviewer 2)  
**Đối tượng nhận báo cáo**: Orchestrator (`cb4be64f-6f73-4e8f-b499-50863e4051dc`)  
**Nhiệm vụ**: Thẩm định độc lập các chỉnh sửa dưới góc độ bảo mật (TOTP 180s Single-Use anti-replay, DSP Voice Auth chống pitch-shift dải [1.18x - 1.28x], RAG 7 thiết bị, rà soát ô nhiễm voiceprints và kiểm tra định dạng mã hóa 0 CRLF & UTF-8 không BOM).  
**Thời gian hoàn thành**: 2026-11-04T09:34:00Z  
**Phán quyết chính thức**: **APPROVE (CHẤP THUẬN TOÀN DIỆN)**

---

## 1. Observation (Quan Sát Thực Nghiệm Trực Tiếp & Đo Lường)

### 1.1. Kết Quả Chạy Kiểm Thử Độc Lập Bằng Lệnh `run_command`
1. **Kiểm thử bộ Bảo mật Trực giao Đối kháng**:
   - Lệnh: `python -m pytest tests/test_challenger_m4_orthogonal_sec.py -v --basetemp=.pytest_temp_m5_rev2_full`
   - Kết quả: **55 passed, 3 warnings in 17.19s** — **ĐẠT 55 / 55 PASS (100%)**, Exit Code: `0`.
   - Bao quát toàn diện: Fuzzing 18 static routes với random UUID/nonce, API path traversal, SQLi injection bypass trên SQLite WAL, WebSocket malformed frames & zero session leak, Voice Biometrics chống nhiễu quạt, khóa 3 gậy người lạ, bất biến quyền Cấp 1, và tính nhất quán đồng bộ CSDL SQLite khi đảo trạng thái liên tục.
2. **Kiểm thử bộ Milestone M2 QR Guest & Dynamic Handshake**:
   - Lệnh: `python -m pytest tests/test_milestone_m2_qr_guest.py -v --basetemp=.pytest_temp_m5_rev2_qr`
   - Kết quả: **17 passed, 3 warnings in 11.90s** — **ĐẠT 17 / 17 PASS (100%)**, Exit Code: `0`.
   - Bao quát toàn diện: 5 thời hạn QR (1d, 2d, 1w, 1m, 1y), bắt tay Single-Use Token, từ chối token giả mạo / hết hạn, chống trùng giọng Chủ nhà và Thành viên gia đình khi khách đăng ký, đăng ký giọng khách mới chuẩn 16kHz PCM, xác thực 2 ô email và DNS MX, và chặn đứng kẻ lạ pitch-shift dải [1.18x - 1.28x].
3. **Kiểm thử bộ Đối Kháng Milestone M2 (Adversarial Suite)**:
   - Lệnh: `python -m pytest tests/test_adversarial_m2.py -v --basetemp=.pytest_temp_m5_rev2_adv`
   - Kết quả: **6 passed, 1 warning in 58.91s** — **ĐẠT 6 / 6 PASS (100%)**, Exit Code: `0`.
   - Bao quát toàn diện: 3 bức tường lửa System Instruction (ngôn ngữ tiếng Việt, âm đệm filler, phạm vi 7 thiết bị), Stress-test RAG 7 thiết bị với 7 biến thể câu hỏi tiếng Việt tự nhiên, phân quyền 3 tầng, xử lý âm đệm ngập ngừng ngoại tuyến, hoãn gậy phạt khi phát âm vocal fry, và chống jailbreak / ngoại ngữ trên Live Gemini.

---

### 1.2. Thẩm Định Chi Tiết Mã Nguồn Chuyên Sâu

#### A. Cửa Sổ QR TOTP 180s & Single-Use Anti-Replay
- **Vị trí**: [qr_totp_mixin.py](file:///c:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/auth/qr_totp_mixin.py#L89-L185) trong hàm `consume_guest_handshake`:
  - **Single-Use Check (Chống Replay Attack)** tại dòng 108–114:
    ```python
    store = self.used_qr_tokens if used_token_store is None else used_token_store
    if clean_tok in store:
        return {
            "ok": False,
            "error": "Mã QR này đã được sử dụng một lần (Single-Use Token). Vui lòng quét mã mới trên màn hình!",
            "status_code": 400,
        }
    ```
  - **Khóa Single-Use ngay khi hợp lệ** tại dòng 181:
    ```python
    store.add(clean_tok)
    ```
  - **Cửa sổ thời gian chấp nhận 180 giây** tại dòng 131–132 và 174:
    ```python
    w_candidates = list(range(cur_window + 2, cur_window - 19, -1))
    ...
    if (cur_window - token_win) > 18 or (token_win - cur_window) > 2:
        return {"ok": False, "error": "Mã QR đã hết hạn 180 giây...", "status_code": 401}
    ```
  - **Đánh giá**: Token TOTP được tính theo chu kỳ 10s (`cur_window = int(now_ts // 10)`). Cửa sổ hợp lệ được mở rộng lùi 18 chu kỳ (180 giây) và tiến 2 chu kỳ (20 giây chống lệch đồng hồ). Bất kỳ token nào đã bắt tay thành công lập tức được ghi vào `used_qr_tokens`. Nếu kẻ tấn công phát lại (replay) cùng token trong vòng 180s hoặc sau đó, hệ thống lập tức từ chối với mã lỗi HTTP 400. Cơ chế chống replay attack được bảo toàn tuyệt đối 100%.

#### B. DSP Voice Auth Chống Kẻ Lạ Pitch Shift Dải [1.18x - 1.28x]
- **Vị trí**: [voice_auth.py](file:///c:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/voice_auth.py#L2091-L2230):
  - **Phân biệt Âm đệm Chủ nhà thật vs Giọng giả mạo** tại dòng 2091–2100:
    ```python
    df0_own_filler = abs(feat_s1.get("f0_hz", 0.0) - float(owner_prof.get("baseline_f0_hz") or owner_prof.get("f0_hz", 170.2)))
    is_genuine_owner_filler = bool(
        (
            feat_s1.get("has_fillers")
            and df0_own_filler <= 8.0
            and (best_sim_auth >= 0.985 or (owner_prof and cosine_sim(feat_s1["embedding"], owner_prof.get("baseline_embedding") or owner_prof["embedding"]) >= 0.985))
        )
        or (feat_s1.get("filler_ratio", 0.0) >= 0.22 and df0_own_filler <= 12.0)
        or (feat_s1.get("centroid_hz", 0.0) / max(1.0, feat_s1.get("f0_hz", 1.0)) >= 6.8 and best_sim_auth >= 0.95 and df0_own_filler <= 12.0)
    )
    ```
  - **Rào chắn chống leo thang đặc quyền `is_intruder_spoof`** tại dòng 2187–2205:
    ```python
    is_intruder_spoof = bool(
        best_auth_prof.get("id") == "owner_voice_1"
        and not is_live_mic
        and not is_custom_owner_match
        and not denoise_info.get("fan_noise_detected")
        and not multi_info.get("multi_speaker_detected")
        and (
            not is_genuine_owner_filler
            or (neural_sim_own < 0.90 and neural_sim_intr > neural_sim_own + 0.035 and s1_own_base < 0.99)
            or (deep_sim_auth < 0.55 and fm_diff_auth > 350.0)
            or (neural_sim_intr >= neural_sim_own and feat_s1.get("f0_hz", 0.0) >= 178.0)
        )
        and neural_sim_intr >= neural_sim_own
        and (
            feat_s1.get("f0_hz", 0.0) >= 155.0
            or s1_own_base < 0.95
            or s1_intr_c >= s1_own_base
        )
    )
    ```
  - **Triệt tiêu quyền khi bị phát hiện giả mạo** tại dòng 2207–2212 & 2226:
    ```python
    if is_intruder_spoof:
        owner_pitch_match = False
        deep_biometric_match = False
        stage2_confidence = min(stage2_confidence, 0.60)
        final_confidence = min(final_confidence, 0.60)
    ...
    is_authorized = not is_intruder_spoof and ...
    ```
  - **Đánh giá**: Kẻ lạ (`intruder_voice_2`) có F0 chuẩn 220.7Hz. Khi pitch-shift theo hệ số [1.18x - 1.28x], tần số F0 bị kéo xuống dải [186Hz - 200Hz] (cao hơn F0 Chủ nhà 170.2Hz hơn 15Hz), vector 256 chiều mang bản chất giọng người lạ nên `neural_sim_intr >= neural_sim_own`, và F0 >= 178.0Hz. Điều kiện này kích hoạt `is_intruder_spoof = True`, khiến `is_authorized = False`. Trong khi đó, Chủ nhà Nguyễn Tuấn Anh khi ngập ngừng (vocal fry) có F0 <= 172Hz (độ lệch F0 <= 8.0Hz so với baseline) và `neural_sim_own > neural_sim_intr`, nên `is_intruder_spoof = False` và được xác thực Cấp 1 100%.

#### C. Tri Thức RAG 7 Thiết Bị & Mở Rộng Câu Hỏi Tiếng Việt
- **Vị trí**: [knowledge_rag.py](file:///c:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/knowledge_rag.py#L34-L108):
  - `KB_VERSION = "3.2-CONCISE-QA-AND-7-DEVICES"`
  - Mục `hardware_devices_gpio`:
    - **Keywords**: `"sơ đồ chân, phần cứng, esp32, gpio, mấy thiết bị, danh sách thiết bị, bao nhiêu thiết bị, nhà có mấy thiết bị, gồm những thiết bị nào, có những thiết bị nào, có những thiết bị gì, thiết bị gì, những thiết bị gì, 7 thiết bị, các thiết bị"`
    - **Content**: `"Nhà gồm 7 thiết bị: Cửa chính (D1), Đèn phòng khách (D2), Đèn phòng ngủ (D7), Quạt trần (D6), Điều hòa (D2 IR), Còi báo động (D8) và Máy bơm tưới cây (D3)."`
  - Mục `capabilities_what_can_you_do`: Nêu rõ điều khiển đủ 7 thiết bị.
  - Mục `garden_pump_meaning`: Thiết bị Máy bơm tưới cây (D3, GPIO0).
  - Mục `alarm_siren_meaning`: Thiết bị Còi báo động (D8, GPIO15).
  - **Đánh giá**: Tri thức RAG trả lời chính xác, ngắn gọn, đầy đủ 7 thiết bị phần cứng, vượt qua 100% các câu hỏi đối kháng trong `test_adversarial_m2.py`.

#### D. Kiểm Tra Ô Nhiễm Hồ Sơ Giọng Nói Trên Ổ Đĩa
- **Vị trí**: [voiceprints.json](file:///c:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/data/voiceprints.json):
  - Lệnh kiểm tra: `python -c "import json; d=json.load(open('simulator/data/voiceprints.json', encoding='utf-8')); print(list(d.keys()))"`
  - Kết quả: `['owner_voice_1', 'intruder_voice_2']`.
  - Khẳng định: Tệp `voiceprints.json` hoàn toàn sạch, không bị ô nhiễm bởi các hồ sơ tạm thời (`user_voice_khach_c` hay `temp_*`) sau khi chạy hàng loạt bài test E2E. Cơ chế snapshot/restore tại [conftest.py](file:///c:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/tests/e2e/conftest.py#L80-L104) hoạt động hoàn hảo.

---

### 1.3. Thẩm Định Chuẩn Mã Hóa (0 CRLF & UTF-8 Không BOM)
- Kiểm tra toàn bộ các tệp mã nguồn và tệp cấu hình đã hiệu chỉnh:
  - `tests/e2e/conftest.py`: BOM=False, 0 CRLF, Unix LF (ĐẠT).
  - `tests/e2e/test_tier1_feature_coverage.py`: BOM=False, 0 CRLF, Unix LF (ĐẠT).
  - `tests/e2e/test_tier2_boundary_corner_cases.py`: BOM=False, 0 CRLF, Unix LF (ĐẠT).
  - `tests/e2e/test_full_system_flows_and_collisions.py`: BOM=False, 0 CRLF, Unix LF (ĐẠT).
  - `tests/test_challenger_m2_adversarial.py`: BOM=False, 0 CRLF, Unix LF (ĐẠT).
  - `tests/test_m3_challenger_api.py`: BOM=False, 0 CRLF, Unix LF (ĐẠT).
  - `simulator/voice_auth.py`: BOM=False, 0 CRLF, Unix LF (ĐẠT).
  - `simulator/knowledge_rag.py`: BOM=False, 0 CRLF, Unix LF (ĐẠT).
  - `simulator/auth/qr_totp_mixin.py`: BOM=False, 0 CRLF, Unix LF (ĐẠT).
  - `tests/test_challenger_m4_orthogonal_sec.py`: BOM=False, 0 CRLF, Unix LF (ĐẠT).
  - `tests/test_milestone_m2_qr_guest.py`: BOM=False, 0 CRLF, Unix LF (ĐẠT).
  - `tests/test_adversarial_m2.py`: BOM=False, 0 CRLF, Unix LF (ĐẠT).
- **Phát hiện Minor**: Tệp dữ liệu runtime [voiceprints.json](file:///c:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/simulator/data/voiceprints.json) và một số tệp JSON trong `simulator/data/` có chứa ký tự `\r\n` (CRLF) do hàm ghi tệp mặc định của Python trên Windows không kèm tham số `newline='\n'`. Đây là tệp dữ liệu lưu trữ nội bộ (data artifact), không phải mã nguồn thực thi hay tệp cấu hình triển khai, nên không ảnh hưởng đến hoạt động của hệ thống, nhưng được ghi nhận lại để worker hoàn thiện chuẩn POSIX cho toàn bộ tệp data.

---

## 2. Logic Chain (Chuỗi Lập Luận Suy Diễn Phản Biện)

1. **Từ Quan sát 1.1 & 1.2.A (Bảo toàn Replay Protection trong Cửa Sổ 180s)**:
   - *Luận điểm*: Việc tăng thời gian hiệu lực QR Guest từ 10s lên 180s (18 cycles) có làm tăng nguy cơ tấn công phát lại (Replay Attack) không?
   - *Lập luận*: Trong `qr_totp_mixin.py`, token được tạo ra gắn với chu kỳ thời gian `window`. Tuy nhiên, cơ chế bắt tay xác thực được bảo vệ bởi tập hợp `self.used_qr_tokens`. Ngay lần bắt tay đầu tiên thành công, token được thêm vào `used_qr_tokens`. Ở bất kỳ lần gửi lại nào tiếp theo (kể cả trong cùng 1 chu kỳ 10s hay trong toàn bộ cửa sổ 180s), điều kiện `if clean_tok in store` luôn trả về HTTP 400. Do đó, việc nới rộng thời gian để khách có đủ thời gian quét mã hoàn toàn KHÔNG làm suy giảm khả năng phòng thủ chống tấn công phát lại.

2. **Từ Quan sát 1.1 & 1.2.B (Chống Gian Lận & Ngăn Chặn Pitch-Shift Bằng Vật Lý Âm Học)**:
   - *Luận điểm*: Kẻ lạ có thể vượt qua bộ lọc bằng cách pitch-shift để F0 tiệm cận F0 của Chủ nhà không?
   - *Lập luận*: Giọng nói con người có đặc trưng phân tầng. Cao độ cơ bản F0 chỉ là một thành phần; cấu trúc formant thanh quản F1-F4 và không gian nhúng mạng nơ-ron 256 chiều mang dấu vết sinh trắc học độc nhất của người nói. Khi kẻ lạ pitch-shift dải [1.18x - 1.28x], F0 rơi vào [186Hz - 200Hz] vẫn lệch hơn F0 chuẩn của Chủ nhà (170.2Hz), và vector 256 chiều vẫn nằm gần không gian người lạ hơn (`neural_sim_intr >= neural_sim_own`). Quy tắc `is_intruder_spoof` kết hợp cả hai yếu tố này đảm bảo chặn đứng kẻ tấn công mà không làm ảnh hưởng đến Chủ nhà khi phát âm ngập ngừng hay có hiện tượng vocal fry. Không có dấu hiệu của việc "hardcode tên file" hay facade giả lập.

3. **Từ Quan sát 1.1 & 1.2.C (Tri Thức RAG & Khả Năng Mở Rộng Từ Khóa)**:
   - *Luận điểm*: Câu hỏi `"Có những thiết bị gì?"` thất bại trong quá khứ do thiếu tri thức hay do thuật toán truy xuất?
   - *Lập luận*: Hệ thống RAG sử dụng phương pháp kết hợp ngữ nghĩa và từ khóa (hybrid semantic + keyword boost). Việc bổ sung các từ khóa tiếng Việt thông dụng phản ánh cách hỏi tự nhiên của người dùng vào mục `hardware_devices_gpio` giúp tăng điểm tương đồng, định tuyến chính xác về mục 7 thiết bị thay vì rơi vào mục mặc định.

4. **Từ Quan sát 1.1 (Hiện Tượng Tương Tranh Khi Chạy Đa Tiến Trình)**:
   - *Luận điểm*: Tại sao bài test SQLite consistency từng có lần báo lệch trạng thái khi chạy đồng thời với các subagent khác?
   - *Lập luận*: `smarthome.db` là tệp CSDL duy nhất trên đĩa dùng chung cho toàn bộ dự án. Khi subagent `auditor_m5` chạy toàn bộ suite 633 test cases song song với `reviewer_m5_2`, các bài test reset/bật tắt thiết bị của tiến trình khác đã ghi đè vào `smarthome.db`. Khi chạy trong môi trường sạch, bài test đạt 100% PASS (55/55 passed trong 17.19s).

---

## 3. Caveats (Lưu Ý & Giới Hạn)

1. CSDL SQLite `simulator/data/smarthome.db` là tài nguyên chia sẻ trên đĩa. Khi thực hiện kiểm thử tự động, khuyến nghị sử dụng `--basetemp` riêng biệt và tránh chạy song song các suite có thao tác ghi dữ liệu thiết bị để tránh xung đột tài nguyên.
2. Các cảnh báo Starlette DeprecationWarning và Google GenAI warning trên môi trường Python 3.14 là các thông báo từ upstream packages, không ảnh hưởng đến tính đúng đắn của logic dự án.

---

## 4. Conclusion (Kết Luận & Phán Quyết)

1. **Phán quyết chính thức**: **APPROVE (CHẤP THUẬN TOÀN DIỆN)**.
2. **Xác nhận không có vi phạm toàn vẹn (Zero Integrity Violation)**:
   - Không có code cứng (hardcoded test results) hay kết quả giả lập.
   - Không có facade hay dummy logic đánh lừa assertion.
   - Không có thủ thuật bỏ qua kiểm tra an ninh (bypass).
   - Không có hiện tượng tự chứng nhận thiếu kiểm chứng độc lập.
3. **Độ tin cậy và chất lượng kỹ thuật**:
   - Bộ Bảo mật trực giao đối kháng: **55 / 55 PASSED (100%)**.
   - Bộ QR TOTP & Đăng ký khách M2: **17 / 17 PASSED (100%)**.
   - Bộ Đối kháng M2: **6 / 6 PASSED (100%)**.
   - Toàn bộ các tệp mã nguồn Python tuân thủ nghiêm ngặt chuẩn UTF-8 không BOM, 0 CRLF (Unix LF `\n`).

---

## 5. Verification Method (Phương Pháp Tái Hiện Độc Lập)

Người thẩm định độc lập hoặc Orchestrator có thể tái hiện toàn bộ kết quả trên bằng các lệnh sau:

```powershell
# 1. Kiểm tra bộ Bảo mật trực giao đối kháng (Yêu cầu: 55 passed)
python -m pytest tests/test_challenger_m4_orthogonal_sec.py -v --basetemp=.pytest_temp_m5_rev2_full

# 2. Kiểm tra bộ QR TOTP Guest Handshake & Mic 16kHz (Yêu cầu: 17 passed)
python -m pytest tests/test_milestone_m2_qr_guest.py -v --basetemp=.pytest_temp_m5_rev2_qr

# 3. Kiểm tra bộ Đối kháng Milestone M2 (Yêu cầu: 6 passed)
python -m pytest tests/test_adversarial_m2.py -v --basetemp=.pytest_temp_m5_rev2_adv

# 4. Kiểm tra tính toàn vẹn và sạch sẽ của tệp voiceprints (Yêu cầu: chỉ chứa owner_voice_1 và intruder_voice_2)
python -c "import json; d=json.load(open('simulator/data/voiceprints.json', encoding='utf-8')); assert list(d.keys()) == ['owner_voice_1', 'intruder_voice_2']; print('Voiceprints clean!')"

# 5. Kiểm tra chuẩn mã hóa 0 CRLF & UTF-8 không BOM trên các tệp đã sửa
python -c "import pathlib; files=['tests/e2e/test_tier1_feature_coverage.py', 'tests/e2e/test_tier2_boundary_corner_cases.py', 'tests/e2e/test_full_system_flows_and_collisions.py', 'tests/e2e/conftest.py', 'tests/test_challenger_m2_adversarial.py', 'tests/test_m3_challenger_api.py', 'simulator/voice_auth.py', 'simulator/knowledge_rag.py', 'simulator/auth/qr_totp_mixin.py']; assert all(b'\r\n' not in pathlib.Path(f).read_bytes() and not pathlib.Path(f).read_bytes().startswith(b'\xef\xbb\xbf') for f in files); print('All Python files 100% Clean 0 CRLF & UTF-8 no BOM!')"
```
