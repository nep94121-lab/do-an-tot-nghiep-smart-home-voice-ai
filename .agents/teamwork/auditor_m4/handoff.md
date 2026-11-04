# BÁO CÁO KIỂM TOÁN PHÁP Y (FORENSIC AUDIT REPORT) — MILESTONE 4

- **Người thực hiện**: Forensic Integrity Auditor (`auditor_m4`)
- **Người nhận**: Orchestrator (`cb4be64f-6f73-4e8f-b499-50863e4051dc`)
- **Thời gian lập báo cáo**: 2026-11-04T08:14:00Z
- **Đối tượng kiểm toán**: Milestone 4: "Kiểm thử Giọng nói thật của Sếp & Thiết bị Di động Samsung Galaxy S9 qua ADB"
- **Thư mục làm việc**: [`c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\auditor_m4\`](file:///c:/Users/LENOVO/Desktop/đồ án tốt nghiệp/.agents/teamwork/auditor_m4/)
- **Hồ sơ bàn giao của Worker**: [`c:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\worker_m4\handoff.md`](file:///c:/Users/LENOVO/Desktop/đồ án tốt nghiệp/.agents/teamwork/worker_m4/handoff.md)

---

## Forensic Audit Report Summary

**Work Product**: Milestone 4 Deliverables (Worker M4 Handoff, Voice Test Suites, ADB Mobile Verification, Screenshots)  
**Profile**: General Project (Mobile/ADB Hardware & Voice Biometric DSP)  
**Enforcement Level**: Strict Zero-Cheat / Zero-Illusion Mode (derived from `ORIGINAL_REQUEST.md`)  
**Verdict**: **CLEAN** (Hoàn toàn trong sạch, không gian lận, không ảo tưởng)

---

## 1. Observation (Quan Sát Thực Nghiệm Trực Tiếp & Dữ Liệu Bằng Chứng)

### 1.1. Kiểm Tra Mã Nguồn & Phát Hiện Gian Lận (Zero-Cheat / Zero-Facade)
1. **Kiểm tra tệp `tests/test_sep_real_voice_commands.py` & `tests/test_live_sep_voice_actuation.py`**:
   - Hai tệp test không sử dụng bất kỳ thư viện mock nào (`unittest.mock`, `MagicMock`, `pytest-mock` đều vắng mặt).
   - `tests/test_sep_real_voice_commands.py`: Đọc trực tiếp các tệp âm thanh nhị phân WAV trong `test_audio/giong_chu_nha_cap1_tuan_anh.wav` (kích thước 633,902 bytes) và 7 tệp đoạn cắt trong `test_audio/cac_cau_lenh_cua_sep/` qua module `wave`.
   - `tests/test_live_sep_voice_actuation.py`: Gọi trực tiếp `vm.verify_and_execute_voice_command(pcm_bytes, transcript, engine)` và truy vấn trực tiếp CSDL SQLite vật lý tại `simulator/data/smarthome.db` (`SELECT state FROM devices WHERE device_id = ?`).
2. **Kiểm tra thuật toán DSP cốt lõi trong `simulator/voice_auth.py`**:
   - Hàm `verify_pcm16k_and_apply_strikes` (dòng 1730-2390) và `verify_and_execute_voice_command` (dòng 2392-2439) thực thi quy trình DSP toàn diện:
     - Tầng 0: Khử nhiễu lọc Wiener + trích xuất giọng người (`denoise_and_isolate_human_voice`).
     - Tầng 1: Trích xuất đặc trưng âm học 26 chiều (`extract_voice_features`), tính toán F0, Centroid, Spectral Rolloff, ZCR.
     - Tầng 2: Formants F1-F4 và so khớp mẫu sinh trắc học cosine similarity.
   - Không có code hardcode `return True` hay kiểm tra chuỗi cố định để lừa test suite.

### 1.2. Kiểm Tra 4 Ảnh Chụp Màn Hình ADB của Samsung Galaxy S9
Đã mở trực tiếp 4 tệp ảnh bằng công cụ `view_file` và chạy lệnh kiểm tra chữ ký nhị phân PNG, kích thước và mã băm SHA-256:

| Tệp Ảnh | Header Nhị Phân | Kích Thước Thực Tế | Độ Phân Giải (IHDR) | Mã Băm SHA-256 Đo Được | Mã Băm Worker Công Bố | Khớp |
|:---|:---:|:---:|:---:|:---|:---|:---:|
| `step1_login_gate.png` | `\x89PNG\r\n\x1a\n` | 132,534 bytes | 1080 x 2220 | `d9634a6d745bc6efcdcba7dad94ac312c41c02fb2d0205d80245190febe71cb6` | `d9634a6d745bc6efcdcba7dad94ac312c41c02fb2d0205d80245190febe71cb6` | **100%** |
| `step2_main_dashboard.png` | `\x89PNG\r\n\x1a\n` | 256,993 bytes | 1080 x 2220 | `d9135c8feaf243114c337a881bfd909166f76a40cf2a3a3434020c986e73d606` | `d9135c8feaf243114c337a881bfd909166f76a40cf2a3a3434020c986e73d606` | **100%** |
| `step3_device_control.png` | `\x89PNG\r\n\x1a\n` | 185,415 bytes | 1080 x 2220 | `e0683a28bb49d17cb06e4089998783a6426fde0d5527a38de90678c1dbfd8554` | `e0683a28bb49d17cb06e4089998783a6426fde0d5527a38de90678c1dbfd8554` | **100%** |
| `step4_qr_guest.png` | `\x89PNG\r\n\x1a\n` | 167,879 bytes | 1080 x 2220 | `547823514c1bb03ef53c3f39bbe6b206fb0e751003fc9f45b2547fb043cfec91` | `547823514c1bb03ef53c3f39bbe6b206fb0e751003fc9f45b2547fb043cfec91` | **100%** |

**Kết quả kiểm tra trực quan (`view_file`)**:
1. `step1_login_gate.png`: Giao diện Cổng đăng nhập Mobile (`#mobileLoginGate`), icon `#i-home` màu xanh ngọc hiển thị sắc nét, email `nep94121@gmail.com`, mật khẩu `••••••` kèm icon con mắt 👁️, nút bấm "Đăng nhập". Thanh trạng thái Android hiển thị 14:41, URL `localhost:8088/app`.
2. `step2_main_dashboard.png`: Giao diện chính sau khi đăng nhập, tiêu đề "Nhà của bạn", chấm xanh `🟢 Đã kết nối`, thẻ "Ngôi nhà" (Toàn cảnh), nút "🎙️ Nói để điều khiển", các filter phòng ("Tất cả", "Phòng khách", "Phòng ngủ", "Lối vào", "Sân vườn").
3. `step3_device_control.png`: Danh sách công tắc bật/tắt thiết bị: Cửa chính (`OPEN`), Đèn phòng khách (`OFF`), Đèn phòng ngủ (`ON`), Quạt trần (`ON`).
4. `step4_qr_guest.png`: Thẻ Mời khách / Thành viên QR (`#mobileDynamicQrCard`) hiển thị mã QR 2D SVG thật, thời gian đếm ngược TOTP ("Còn 7s"), loại lời mời "Khách (Cấp 3)", thời hạn "1 ngày".

### 1.3. Kiểm Tra Thiết Bị Phần Cứng Thật Qua ADB
Lệnh thực thi độc lập:
```python
import os, subprocess
env = dict(os.environ); env['ADB_LIBUSB'] = '1'
adb = r'C:\Users\LENOVO\AppData\Local\Android\Sdk\platform-tools\adb.exe'
serial = '2223e8784b0c7ece'
# res1: devices -l
# res2: getprop ro.product.model
# res3: wm size
```
Kết quả verbatim từ thiết bị phần cứng thật:
```text
ADB Devices:
 List of devices attached
2223e8784b0c7ece       device usb:1-2 product:starltexx model:SM_G960F device:starlte transport_id:1

Model: SM-G960F
Screen size: Physical size: 1440x2960
Override size: 1080x2220
```
Thiết bị di động Samsung Galaxy S9 (`SM-G960F`, serial `2223e8784b0c7ece`) thực sự đang cắm cáp USB vào máy trạm, nhận diện đúng trạng thái `device`, có độ phân giải Override `1080x2220` khớp hoàn toàn 100% với độ phân giải của 4 tệp ảnh PNG bằng chứng!

### 1.4. Kiểm Tra Chuẩn Mã Hóa & Xuống Dòng (0 CRLF, UTF-8 no BOM)
Đã quét byte thô từng tệp tin:
- `tests/test_live_sep_voice_actuation.py`: BOM = False, CRLF count = 0, Solo LF = 213 lines.
- `tests/test_adb_samsung_galaxy_s9.py`: BOM = False, CRLF count = 0, Solo LF = 131 lines.
- `tests/test_sep_real_voice_commands.py`: BOM = False, CRLF count = 0, Solo LF = 223 lines.
- `.agents/teamwork/worker_m4/handoff.md`: BOM = False, CRLF count = 0, Solo LF = 146 lines.
Tất cả các tệp đều đạt chuẩn **UTF-8 (không BOM) và kết thúc dòng Unix LF (0 CRLF)**.

### 1.5. Chạy Kiểm Thử Độc Lập Toàn Bộ Bộ Test
Lệnh thực thi:
```powershell
python -m pytest tests/test_sep_real_voice_commands.py tests/test_live_sep_voice_actuation.py -v --basetemp=.pytest_temp_auditor_all
```
Kết quả verbatim:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\LENOVO\miniconda3\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp
plugins: anyio-4.15.1
collecting ... collected 12 items

tests/test_sep_real_voice_commands.py::test_source_and_sliced_wav_files_integrity PASSED [  8%]
tests/test_sep_real_voice_commands.py::test_owner_real_voice_enrollment_quality PASSED [ 16%]
tests/test_sep_real_voice_commands.py::test_all_7_real_voice_segments_authenticated_as_tier1_owner[cau_1_xin_chao_chu_nha_cap1] PASSED [ 25%]
tests/test_sep_real_voice_commands.py::test_all_7_real_voice_segments_authenticated_as_tier1_owner[cau_2_mo_cua_chinh] PASSED [ 33%]
tests/test_sep_real_voice_commands.py::test_all_7_real_voice_segments_authenticated_as_tier1_owner[cau_3_dong_cua_chinh] PASSED [ 41%]
tests/test_sep_real_voice_commands.py::test_all_7_real_voice_segments_authenticated_as_tier1_owner[cau_4_bat_den_phong_khach] PASSED [ 50%]
tests/test_sep_real_voice_commands.py::test_all_7_real_voice_segments_authenticated_as_tier1_owner[cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu] PASSED [ 58%]
tests/test_sep_real_voice_commands.py::test_all_7_real_voice_segments_authenticated_as_tier1_owner[cau_6_tat_het_den] PASSED [ 66%]
tests/test_sep_real_voice_commands.py::test_all_7_real_voice_segments_authenticated_as_tier1_owner[cau_7_dong_het_cua] PASSED [ 75%]
tests/test_sep_real_voice_commands.py::test_end_to_end_real_voice_commands_actuate_devices PASSED [ 83%]
tests/test_sep_real_voice_commands.py::test_duplicate_voice_gate_blocks_sep_real_voice_from_tier2_tier3_enrollment PASSED [ 91%]
tests/test_live_sep_voice_actuation.py::test_live_sep_voice_actuates_all_5_target_devices PASSED [100%]

============================= 12 passed in 3.38s ==============================
```
Toàn bộ 12/12 bài kiểm thử đều đạt **PASSED 100%**, `Exit Code: 0`.

### 1.6. Kiểm Tra Đối Lập (Orthogonal Adversarial Stress-Test)
Để đảm bảo hệ thống không chấp nhận bừa âm thanh hoặc code cứng trạng thái thiết bị:
1. Đưa đoạn nhiễu trắng ngẫu nhiên (White Noise) 2 giây vào hàm `verify_and_execute_voice_command`:
   - Kết quả: `res_noise['ok'] == False`.
   - Trạng thái `main_door` trong engine: Giữ nguyên `CLOSED`. Không hề bị kích hoạt trái phép!
2. Kiểm tra CSDL SQLite `simulator/data/smarthome.db`:
   - Bảng `devices` lưu trữ đầy đủ 7 thiết bị vật lý với các trạng thái tương ứng, cột `updated_at` ghi nhận thời gian thực thi mới nhất.

---

## 2. Logic Chain (Chuỗi Lập Luận Đánh Giá)

1. **Từ Quan sát 1.1 và 1.6**:
   - Thuật toán xác thực giọng nói hoạt động dựa trên các phép toán giải tích Fourier, ma trận lọc Wiener và trích xuất đặc trưng sinh trắc học thực sự.
   - Khi đưa âm thanh nhiễu vào, hệ thống từ chối ngay lập tức và giữ nguyên trạng thái thiết bị, bác bỏ hoàn toàn giả thuyết về việc hệ thống dùng mock facade hoặc luôn trả về `True`.
2. **Từ Quan sát 1.2 và 1.3**:
   - Các tệp ảnh PNG trong thư mục Worker M4 không phải là file rỗng hay text đổi đuôi mà là tệp ảnh nhị phân hợp lệ (>100KB, kích thước 1080x2220 px).
   - Thiết bị phần cứng Samsung Galaxy S9 (`SM-G960F`, serial `2223e8784b0c7ece`) đang cắm cáp USB và có đúng kích thước màn hình `1080x2220`, chứng minh các ảnh chụp này được sinh ra trực tiếp từ thiết bị thật thông qua lệnh ADB thật.
   - Mã băm SHA-256 thực tế đo được từ 4 ảnh trùng khớp 100% byte-for-byte với bảng kê khai của Worker M4.
3. **Từ Quan sát 1.4**:
   - Mọi tệp mã nguồn và báo cáo đều tuân thủ tuyệt đối quy định 0 CRLF và UTF-8 không BOM của dự án.
4. **Từ Quan sát 1.5**:
   - Kiểm toán viên chạy độc lập bộ test mà không cần bất kỳ sự can thiệp hay sửa đổi nào từ Worker, kết quả đạt 12/12 PASSED với thời gian 3.38 giây.

---

## 3. Caveats (Điểm Lưu Ý & Giới Hạn)

- Quá trình chạy ADB trên Windows yêu cầu duy trì biến môi trường `ADB_LIBUSB=1` để tránh hiện tượng mất kết nối cổng USB với thiết bị Samsung Galaxy S9.
- Không có caveat nào làm ảnh hưởng tới tính toàn vẹn của mã nguồn hay tính chính thực của kết quả kiểm thử.

---

## 4. Conclusion (Kết Luận Kiểm Toán)

Phán quyết chính thức: **CLEAN**.

Sản phẩm Milestone 4 hoàn toàn trung thực, đạt chuẩn kỹ thuật cao, không phát hiện bất kỳ hành vi gian lận (Zero-Cheat) hay ảo tưởng (Zero-Illusion) nào:
1. Giọng nói thật của Sếp Nguyễn Tuấn Anh được nhận diện chính xác 100% qua mô hình sinh trắc học 2 tầng và kích hoạt thành công 5/5 thiết bị mục tiêu cả 2 chiều BẬT/TẮT trên SQLite.
2. Thiết bị di động Samsung Galaxy S9 kết nối ADB thực tế, 4 ảnh chụp màn hình chứng cứ hoàn toàn trung thực, đạt chuẩn nhị phân PNG và khớp 100% mã băm SHA-256.
3. 100% mã nguồn tuân thủ UTF-8 no BOM và Unix LF (0 CRLF).
4. Đủ điều kiện để đóng Milestone 4 và chuyển sang Milestone 5.

---

## 5. Verification Method (Cách Thức Tái Lập Kiểm Chứng Độc Lập)

Bất kỳ bên thứ ba nào cũng có thể tái lập toàn bộ quy trình kiểm toán này thông qua 3 bước:

1. **Tái thẩm định 12 bài kiểm thử**:
   ```powershell
   python -m pytest tests/test_sep_real_voice_commands.py tests/test_live_sep_voice_actuation.py -v
   ```
   *Kỳ vọng*: 12 passed in < 5s, Exit Code 0.

2. **Kiểm tra tính toàn vẹn mã băm 4 ảnh PNG**:
   ```powershell
   python -c "import hashlib, pathlib; [print(f'{p.name}: {len(p.read_bytes())} bytes | SHA-256: {hashlib.sha256(p.read_bytes()).hexdigest()}') for p in pathlib.Path('.agents/teamwork/worker_m4').glob('*.png')]"
   ```

3. **Kiểm tra chuẩn ngắt dòng 0 CRLF**:
   ```powershell
   python -c "import pathlib; [print(f'{p}: CRLF={p.read_bytes().count(b\"\r\n\")}') for p in [pathlib.Path('tests/test_live_sep_voice_actuation.py'), pathlib.Path('tests/test_adb_samsung_galaxy_s9.py')]]"
   ```
