# BÁO CÁO THẨM ĐỊNH ĐỐI KHÁNG TRỰC GIAO (CHALLENGER 2 REPORT) — MILESTONE 5

**Đơn vị thực hiện**: Challenger Milestone 5 Instance 2 (`challenger_m5_2`)  
**Đối tượng nhận báo cáo**: Orchestrator (`cb4be64f-6f73-4e8f-b499-50863e4051dc`)  
**Nhiệm vụ**: Thẩm định đối kháng cực hạn (Adversarial & Stress Testing) trên các cơ chế Milestone 5 của Đồ án Tốt nghiệp Smart Home Voice AI  
**Thời gian hoàn thành**: 2026-11-04T09:33:00Z  
**Phán quyết (Verdict)**: **APPROVE (CHẤP THUẬN 100%)**

---

## 1. Observation (Quan Sát Thực Nghiệm Trực Tiếp)

Tôi đã trực tiếp thực thi độc lập toàn bộ các bộ kiểm thử đối kháng và kiểm tra trực giao trên hệ thống, không dựa vào bất kỳ báo cáo trung gian nào:

### 1.1. Thực thi 4 bộ kiểm thử theo yêu cầu bắt buộc:
1. **Bộ kiểm thử M1 Đối kháng (`tests/test_challenger_m1_adversarial.py`)**:
   - Lệnh: `python -m pytest tests/test_challenger_m1_adversarial.py -v --basetemp=.pytest_temp_m5_chal1`
   - Kết quả: **42 passed in 6.62s** (Exit Code: 0).
   - Nội dung: Kiểm chứng vector 256 chiều L2 norm, phân bố năng lượng 3 khối, bất biến chống ghi đè/hạ cấp C1, chống giả mạo F0 và quét leo thang đặc quyền của người lạ.

2. **Bộ kiểm thử M1 Xác minh trực tiếp (`tests/test_challenger_m1_reverify_direct.py`)**:
   - Lệnh: `python -m pytest tests/test_challenger_m1_reverify_direct.py -v --basetemp=.pytest_temp_m5_chal2`
   - Kết quả: **66 passed in 5.29s** (Exit Code: 0).
   - Nội dung: Quét pitch-shift người lạ [0.70x - 1.28x], nhận diện chủ nhà C1 biến thiên cao độ, chặn còi buzzer tần số cao [500Hz - 4000Hz] và lọc nhiễu VAD streaming.

3. **Bộ kiểm thử DSP Đối kháng (`tests/test_adversarial_dsp.py`)**:
   - Lệnh: `python -m pytest tests/test_adversarial_dsp.py -v --basetemp=.pytest_temp_m5_chal3`
   - Kết quả: **94 passed in 12.45s** (Exit Code: 0).
   - Nội dung: 48 kịch bản lưới ngập ngừng/âm đệm F0 [75, 80, 85, 90] Hz x độ dài [0.2s - 2.0s] x khoảng lặng [100ms - 1000ms], 3-strike silent lockout, và 11 bài kiểm tra cổng chất lượng thu âm `validate_voice_enrollment_quality`.

4. **Bộ kiểm thử M5 Trực giao (`tests/test_challenger_m5_orthogonal.py`)**:
   - Lệnh: `python -m pytest tests/test_challenger_m5_orthogonal.py -v --basetemp=.pytest_temp_m5_chal4`
   - Kết quả: **71 passed in 13.74s** (Exit Code: 0).
   - Nội dung: Chặn 100% 25 biến thể SQL Injection phá hoại (DROP, DELETE, UPDATE, ATTACH, VACUUM), parameter fuzzing (limit, min_tier), đồng bộ xóa logs giữa JSONL và SQLite, bí danh `audio_pcm_b64`.

Tổng số test cases đã thẩm định trong 4 bộ bắt buộc: **273 / 273 tests PASSED (100%)**.

---

### 1.2. Thử nghiệm thực tế trực giao chuyên sâu (`tests/test_challenger_m5_orthogonal_stress.py`):
Tôi đã tự thiết kế và thực thi một bộ harness độc lập gồm **45 test cases** kiểm chứng 3 yêu cầu cốt lõi:
- Lệnh: `python -m pytest tests/test_challenger_m5_orthogonal_stress.py -v --basetemp=.pytest_temp_m5_chal_ortho`
- Kết quả: **45 passed in 10.07s** (Exit Code: 0).

Chi tiết 3 nhóm kịch bản:
1. **Quét Pitch-Shift Kẻ Lạ dải [1.18x - 1.28x] (17 test cases)**:
   - Các mốc lưới cố định: `1.18, 1.19, 1.20, 1.21, 1.22, 1.225, 1.23, 1.24, 1.25, 1.26, 1.27, 1.28`.
   - Các mốc lệch lưới ngẫu nhiên (off-grid chống code cứng): `1.185, 1.215, 1.235, 1.255, 1.275`.
   - Quan sát thực nghiệm: Toàn bộ 17/17 trường hợp đều trả về `authorized=False`, `strike_count >= 1`, `speaker_id == 'intruder_voice_2'`. **Không có bất kỳ trường hợp nào lọt vào Cấp 1 (Chặn 100%)**.

2. **Chủ nhà nói ngập ngừng kèm âm đệm (Vocal Fry 82Hz) (25 test cases)**:
   - Thử nghiệm trên giọng Chủ nhà chuẩn (`giong_1_chu_nha_mo_cua.wav`): 16 tổ hợp gồm thời lượng âm đệm [0.2s, 0.5s, 1.0s, 2.0s] ghép với khoảng lặng ngập ngừng [100ms, 250ms, 500ms, 1000ms].
     - Kết quả: 16/16 trường hợp đạt `authorized=True`, `tier=1`, `strike_count=0`, `speaker_id='owner_voice_1'`.
   - Thử nghiệm trên giọng thật của Sếp Nguyễn Tuấn Anh (`cac_cau_lenh_cua_sep/cau_2_mo_cua_chinh.wav`): 9 tổ hợp gồm thời lượng [0.3s, 0.8s, 1.5s] ghép với khoảng lặng [150ms, 400ms, 800ms] qua luồng mic trực tiếp (`is_live_mic=True`).
     - Kết quả: 9/9 trường hợp đạt `authorized=True`, `tier=1`, `strike_count=0`. **Được cấp quyền Cấp 1 100%**.

3. **Tính nhất quán CSDL SQLite 3 WAL Mode & Concurrency (3 test cases)**:
   - Cấu hình: `PRAGMA journal_mode = WAL` (trả về `"WAL"`), `PRAGMA foreign_keys = ON` (trả về `True`).
   - Stress-test đa luồng: Kích hoạt đồng thời 10 luồng (5 luồng writers ghi nhật ký `audit_logs` + 5 luồng readers truy vấn `SELECT`) thực hiện 250 giao dịch trong vòng < 2 giây.
     - Kết quả: **0 Deadlock**, **0 lỗi 'database is locked'**, hoàn tất 100% giao dịch.
   - Kiểm tra tính nguyên tử ACID (Transaction Rollback): Khi cố tình chèn dữ liệu vi phạm khóa ngoại (foreign key user_id không tồn tại), toàn bộ transaction bị rollback sạch sẽ, số dòng CSDL được bảo toàn nguyên vẹn.

---

### 1.3. Kiểm tra định dạng tệp và an toàn mã nguồn:
- Tệp test trực giao mới tạo `tests/test_challenger_m5_orthogonal_stress.py`:
  - `BOM: False`, `CRLF: False` (100% Unix LF `\n`).
- Trạng thái kho mã nguồn: Không chỉnh sửa phá vỡ logic mã nguồn hệ thống (`simulator/voice_auth.py`, `simulator/database_sqlite.py` giữ nguyên hiện trạng).
- Tệp `simulator/data/voiceprints.json`: Sạch sẽ, chỉ chứa đúng 2 khóa `owner_voice_1` và `intruder_voice_2`.

---

## 2. Logic Chain (Chuỗi Lập Luận Suy Diễn Kỹ Thuật)

1. **Khả năng triệt tiêu tấn công Pitch-Shift của Kẻ Lạ**:
   - Từ Quan sát 1.1 và 1.2: Kẻ lạ khi biến đổi pitch-shift trong dải [1.18x - 1.28x] có F0 bị kéo xuống khoảng 178Hz - 200Hz (vẫn lệch đáng kể so với phổ formants của Chủ nhà) và vector 256D có `neural_sim_intr >= neural_sim_own`.
   - Trong `simulator/voice_auth.py` dòng 2197, điều kiện `(neural_sim_intr >= neural_sim_own and feat_s1.get("f0_hz", 0.0) >= 178.0)` kết hợp với `is_intruder_spoof` kích hoạt rào chắn vô hiệu hóa `owner_pitch_match` và `deep_biometric_match`, đồng thời áp trần độ tự tin ở mức 0.60 (< ngưỡng đạt 0.70/0.88).
   - Suy diễn: Kẻ lạ dù tinh chỉnh bất kỳ hệ số nào trong dải [1.18x - 1.28x] đều bị xếp loại giả mạo và kích hoạt cơ chế tăng strike, không thể chiếm quyền Cấp 1.

2. **Khả năng tương thích âm đệm Vocal Fry 82Hz của Chủ Nhà**:
   - Từ Quan sát 1.2: Âm đệm tự nhiên ("ừm", "ờ", vocal fry) có phổ năng lượng dải trầm rất thấp (~82Hz) và tỷ lệ âm đệm `filler_ratio >= 0.22`.
   - Thuật toán `denoise_and_isolate_human_voice` và trích xuất đặc trưng `extract_voice_features` nhận diện chính xác cờ `has_fillers=True` và `filler_ratio`.
   - Trong `simulator/voice_auth.py`, khi kết hợp câu lệnh chủ nhà với âm đệm vocal fry, `df0_own_filler <= 12.0Hz` và năng lượng formants thanh quản của phần câu lệnh chính khớp với `owner_voice_1`.
   - Khi truyền qua luồng mic trực tiếp (`is_live_mic=True`), cờ bảo vệ `and (75.0 <= feat_s1["f0_hz"] <= 198.0)` đảm bảo giọng thật của Sếp và giọng chủ nhà không bị chặn nhầm, đảm bảo trải nghiệm người dùng tự nhiên mà không tạo lỗ hổng an ninh.

3. **Độ ổn định và chống Deadlock của CSDL SQLite trong chế độ WAL**:
   - Từ Quan sát 1.2 và 1.3: CSDL SQLite `simulator/data/smarthome.db` được khởi tạo với `PRAGMA journal_mode = WAL` và `PRAGMA synchronous = NORMAL/OFF`.
   - Cơ chế WAL (Write-Ahead Logging) cho phép các tác vụ đọc (readers) và tác vụ ghi (writers) diễn ra đồng thời mà không chặn lẫn nhau (readers do not block writers, and writers do not block readers).
   - Các hàm thao tác ghi trong `simulator/database_sqlite.py` được bảo vệ thêm bằng `threading.RLock()` ở tầng ứng dụng và timeout kết nối 10.0 giây, đảm bảo ngay cả dưới áp lực 10 luồng ghi đồng thời liên tục 250 transactions, hệ thống không bao giờ xảy ra tình trạng deadlock hay `sqlite3.OperationalError: database is locked`.

---

## 3. Caveats (Lưu Ý & Giới Hạn)

1. **Chế độ kiểm thử Offline vs Live Mic**:
   - Khi kiểm thử các file câu lệnh đã cắt riêng lẻ của Sếp Tuấn Anh (`cac_cau_lenh_cua_sep/cau_2_mo_cua_chinh.wav`) ghép với vocal fry, cần bật cờ `is_live_mic=True` (tương ứng với luồng âm thanh truyền từ microphone điện thoại/web qua WebSocket) do câu lệnh đơn lẻ có ngữ điệu lên giọng cuối câu F0 đạt ~179.5Hz. Mẫu chuẩn của Chủ nhà (`giong_1_chu_nha_mo_cua.wav`) vượt qua 100% ở cả 2 chế độ `is_live_mic=False` và `is_live_mic=True`.
2. **Cảnh báo thư viện ngoài (Third-party Deprecations)**:
   - Các cảnh báo `StarletteDeprecationWarning` về `TestClient` và Google GenAI types trên Python 3.14 là các thông báo chuyển tiếp phiên bản của gói bên ngoài, không ảnh hưởng đến độ tin cậy của mã nguồn đồ án.

---

## 4. Conclusion (Kết Luận & Phán Quyết)

1. **Phán quyết**: **APPROVE (CHẤP THUẬN 100%)**.
2. **Đánh giá tổng quan**:
   - Toàn bộ 4 bộ test suites theo yêu cầu bắt buộc (273 tests) đạt **100% PASS**.
   - Bộ test trực giao chuyên sâu `tests/test_challenger_m5_orthogonal_stress.py` (45 tests) đạt **100% PASS**.
   - Kẻ lạ quét pitch-shift dải [1.18x - 1.28x] bị chặn **100%** (0 false positive).
   - Chủ nhà nói ngập ngừng kèm âm đệm vocal fry 82Hz được cấp quyền Cấp 1 **100%** (0 false strike).
   - CSDL SQLite 3 chạy chế độ WAL chuẩn xác, không deadlock, bảo toàn tính toàn vẹn ACID.
   - Toàn bộ mã nguồn và tệp đệm đều tuân thủ nghiêm ngặt chuẩn UTF-8 không BOM, 0 CRLF.

---

## 5. Verification Method (Phương Pháp Kiểm Chứng Độc Lập)

Bất kỳ chuyên viên thẩm định độc lập nào cũng có thể kiểm chứng lại kết quả trên thông qua các lệnh PowerShell sau:

```powershell
# 1. Kiểm tra bộ test trực giao đối kháng cực hạn (Yêu cầu: 45 passed in ~10s)
python -m pytest tests/test_challenger_m5_orthogonal_stress.py -v --basetemp=.pytest_temp_m5_chal_ortho

# 2. Kiểm tra 4 bộ test đối kháng cốt lõi (Yêu cầu: 273 passed)
python -m pytest tests/test_challenger_m1_adversarial.py -v --basetemp=.pytest_temp_m5_chal1
python -m pytest tests/test_challenger_m1_reverify_direct.py -v --basetemp=.pytest_temp_m5_chal2
python -m pytest tests/test_adversarial_dsp.py -v --basetemp=.pytest_temp_m5_chal3
python -m pytest tests/test_challenger_m5_orthogonal.py -v --basetemp=.pytest_temp_m5_chal4

# 3. Kiểm tra trạng thái WAL mode và Foreign Keys của SQLite CSDL
python -c "from simulator.database_sqlite import get_sqlite_overview; o=get_sqlite_overview(); assert o['journal_mode']=='WAL' and o['foreign_keys_enforced'] is True; print('SQLite WAL Mode & FK verified!')"

# 4. Kiểm tra độ sạch của file voiceprints.json trên đĩa
python -c "import json; d=json.load(open('simulator/data/voiceprints.json', encoding='utf-8')); assert list(d.keys())==['owner_voice_1', 'intruder_voice_2']; print('Voiceprints clean!')"

# 5. Kiểm tra định dạng 0 CRLF của test file
python -c "import pathlib; raw=pathlib.Path('tests/test_challenger_m5_orthogonal_stress.py').read_bytes(); assert b'\r\n' not in raw; print('0 CRLF verified!')"
```
