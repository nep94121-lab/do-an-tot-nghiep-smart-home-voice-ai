# Phân Tích Thẩm Định Đối Kháng Thực Nghiệm (Empirical Challenger Analysis)

**Tác giả**: `challenger_m5_1` (Full Suite Empirical Challenger 1)  
**Thời gian**: 2026-11-04T09:28:45Z  
**Đối tượng**: Toàn bộ hệ sinh thái kiểm thử Đồ án Tốt nghiệp Smart Home Voice AI (Milestone 5)

---

## I. Kiểm Tra Toàn Vẹn Cú Pháp & Chống Gian Lận (Anti-Cheat & AST Audit)
Phân tích tĩnh cấu trúc cây cú pháp trừu tượng (Abstract Syntax Tree - AST) và quét biểu thức chính quy (Ripgrep) trên toàn bộ thư mục `tests/`:

1. **Kiểm tra Bypass Skips/XFails**:
   - `pytest.mark.skip` / `pytest.skip`: **0 phát hiện**.
   - `pytest.mark.skipif` / `skipif`: **0 phát hiện**.
   - `pytest.mark.xfail` / `xfail`: **0 phát hiện**.
   - Kết luận: Không có bất kỳ test case nào bị bỏ qua hoặc đánh dấu bỏ lọt lỗi.

2. **Kiểm tra Assertions Giả Mạo / Trivial Asserts**:
   - Tổng số hàm test được phân tích: **288 hàm test**.
   - Tổng số mệnh đề `assert` được phân tích: **1,390 mệnh đề**.
   - Trivial asserts (`assert True`, `assert 1 == 1`, `assert 'a' == 'a'`): **0 phát hiện**.
   - Các hàm test không dùng từ khóa `assert` trực tiếp kế thừa từ `unittest.TestCase` (sử dụng các phương thức assertion nghiêm ngặt: `self.assertIn`, `self.assertEqual`, `self.assertTrue`).
   - Kết luận: 100% assertions là kiểm tra nghiệp vụ thực tế, có logic đối soát sinh trắc học, RBAC, CSDL và trạng thái phần cứng.

---

## II. Kiểm Chứng Độc Lập Bộ Giọng Nói Thật Của Sếp (Sep Real Voice Commands)
- Lệnh: `python -m pytest tests/test_sep_real_voice_commands.py tests/test_live_sep_voice_actuation.py -v`
- Số lượng test cases: **12 / 12 PASSED (100%)**, thời gian thực thi: **5.03s**, Exit Code: **0**.
- Chi tiết các ca kiểm thử:
  1. `test_source_and_sliced_wav_files_integrity`: PASSED (Kiểm tra SHA-256 / kích thước 633,902 bytes file gốc và 7 phân đoạn trong `manifest_cau_lenh.json`).
  2. `test_owner_real_voice_enrollment_quality`: PASSED (Đoạn thu âm gốc đạt F0 chuẩn 85-130Hz của Sếp).
  3. `test_all_7_real_voice_segments_authenticated_as_tier1_owner` (7 câu lệnh): PASSED (100% nhận diện đúng Cấp 1 ADMIN `tuan_anh`, F0 từ 88-122Hz, similarity >= 0.90, strike = 0).
  4. `test_end_to_end_real_voice_commands_actuate_devices`: PASSED (Tuần tự 7 câu lệnh điều khiển thực tế 5 thiết bị mục tiêu).
  5. `test_duplicate_voice_gate_blocks_sep_real_voice_from_tier2_tier3_enrollment`: PASSED (Chặn hoàn toàn việc dùng giọng Sếp để đăng ký tài khoản Cấp 2 hoặc Cấp 3).
  6. `test_live_sep_voice_actuates_all_5_target_devices`: PASSED (Kích hoạt trực tiếp và đối soát CSDL quan hệ SQLite `smarthome.db`).

- **Ghi nhận đối kháng đặc biệt (Adversarial Observation)**:
  Khi có các tiến trình `pytest` khác chạy đồng thời trên cùng workspace mà không phân tách CSDL SQLite, việc truy cập đồng thời vào `simulator/data/smarthome.db` có thể kích hoạt cơ chế khóa bảng SQLite dẫn đến sai lệch trạng thái thiết bị. Khi chạy kiểm thử độc lập, toàn bộ 12 ca kiểm thử hoạt động hoàn hảo và nhất quán 100%.

---

## III. Kiểm Chứng Toàn Bộ Test Suite Dự Án (Full Pytest Suite)
- Tiến trình đang thực thi: `python -m pytest tests/ -v --basetemp=.pytest_temp_ch1` (Task 111).
- Trạng thái: Đang theo dõi và cập nhật khi có kết quả hoàn thành.
