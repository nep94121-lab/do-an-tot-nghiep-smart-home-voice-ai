# Báo Cáo Khắc Phục Bảo Mật `p7-sec3` (`FIX_REPORT_SEC3.md`)

## 1. Tóm Tắt Vấn Đề & Giải Pháp
- **Vấn đề gốc phát hiện trên Production**: Endpoint `GET /api/auth3/overview` (khi đã đăng nhập) trả về mã OTP 6 chữ số dạng rõ (`plaintext`) bên trong `verification_logs[].extra.otp_code`, `recent_logs[].extra.otp_code`, chuỗi mô tả `detail` và báo cáo `test_report.cases`. Ngoài ra, các tệp nhật ký lưu trữ (`simulator/data/auth_3layer_events.json`, `simulator/data/system_audit_logs.jsonl`, bảng `audit_logs` trong `simulator/data/smarthome.db`) còn lưu các bản ghi lịch sử chứa `otp_code`, `otp_code_for_test_table`, `demo_otp_preview`, mật khẩu cấp phát và vector sinh trắc học giọng nói.
- **Vấn đề hồi quy ở vòng xác minh (`ed4625d`) & Bản vá bổ sung**:
  - Trong commit `ed4625d`, hàm `redact_otp_and_secrets_in_text` ([`simulator/voice_config.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/voice_config.py)) thay thế `(Mật khẩu gợi ý:\s*)([^\s\)]+)` bằng `\1[REDACTED]`, ghi đè lên chuỗi che `"******"` của `mask_sensitive_log_data` ([`simulator/api/routes_logs.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/api/routes_logs.py)), làm cho `tests/test_p4_survey1_security_auth.py::TestBug1SecurityCredentialCleanup::test_bug1_logs_api_masks_password_hints` (và `tests/test_challenger_m1_2_adversarial.py::TestAdversarialBug1CredentialScan::test_adversarial_logs_dict_key_masking_edge_case`) bị lỗi khi kiểm tra định dạng `"******"`.
  - **Cách khắc phục**: Chuẩn hóa đầu ra của `redact_otp_and_secrets_in_text` trong [`simulator/voice_config.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/voice_config.py#L219-L263) để che gợi ý mật khẩu (`Mật khẩu gợi ý: ...`) và các cặp khóa-giá trị mật khẩu/hint/secret/token/otp nội dòng bằng `"******"`, giữ nguyên hoàn toàn assertion của `test_bug1_logs_api_masks_password_hints`, đồng thời bổ sung ca kiểm thử chống hồi quy `test_logs_api_masks_password_hints_with_asterisks_not_redacted_token` trong [`tests/test_p7_sec3_otp_log_redaction.py`](file:///C:/Users/LENOVO/datn-wt/sec3/tests/test_p7_sec3_otp_log_redaction.py#L435-L457).
- **Tổng hợp 4 trụ cột bảo mật trên nhánh `p7-sec3`**:
  1. **Chặn ghi mã OTP và mật khẩu tại nguồn (`At Source`)**:
     - Loại bỏ toàn bộ việc đưa `otp_code` và mật khẩu vào `detail` và `extra` trong `layer1_login`, `request_password_reset_otp`, `layer2_verify_otp` ([`simulator/auth_3layer.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/auth_3layer.py)) và `start_invite_oauth_registration`, `verify_invite_otp_and_create_account` ([`simulator/auth/invite_and_gmail_mixin.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/auth/invite_and_gmail_mixin.py)).
     - Loại bỏ lộ mã OTP thật trong thông báo lỗi khi nhập sai OTP link mời (`verify_invite_otp_and_create_account`).
     - Loại bỏ việc nhúng mã OTP thật vào báo cáo kiểm thử tự động `TEST-01`, `TEST-02`, `TEST-04` ([`simulator/auth/test_suite_mixin.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/auth/test_suite_mixin.py)).
     - Áp dụng bộ lọc `sanitize_overview_and_logs_payload` và `redact_otp_and_secrets_in_text` ngay trong `_log_event`, `append_audit_log` ([`simulator/engine/audit_logger.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/engine/audit_logger.py)) và `insert_audit_log_sqlite` ([`simulator/database_sqlite.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/database_sqlite.py)).
     - Ẩn các trường OTP thử nghiệm (`otp_code_for_test`, `otp_code_for_test_table`, `demo_otp_preview`, `issued_password_for_test`, `otp_code`) trên các route `/api/auth3/layer1_login`, `/api/auth3/invite_oauth_start`, `/api/auth3/guest_qr_send_otp`, `/api/auth3/guest_qr_verify_otp` khi `is_test_otp_fields_allowed(app)` là `False`.
  2. **Làm sạch dữ liệu nhật ký đã lưu trữ (`Startup & Migration Redaction`)**:
     - Tự động quét và làm sạch khi khởi động (`_load_state`, `redact_stored_audit_logs_jsonl`, `_redact_sqlite_audit_logs_in_conn`) và đã làm sạch trực tiếp trên đĩa 70 sự kiện trong [`simulator/data/auth_3layer_events.json`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/data/auth_3layer_events.json), 92 dòng trong [`simulator/data/system_audit_logs.jsonl`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/data/system_audit_logs.jsonl) và 91 bản ghi trong bảng `audit_logs` của [`simulator/data/smarthome.db`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/data/smarthome.db).
  3. **Bộ lọc phản hồi đệ quy (`Response Sanitizer`)**:
     - Bổ sung `sanitize_overview_and_logs_payload`, `is_forbidden_overview_or_log_key` và `redact_otp_and_secrets_in_text` trong [`simulator/voice_config.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/voice_config.py) để cắt bỏ đệ quy mọi khóa nhạy cảm (`otp`, `otp_code`, `code`, `otp_code_for_test`, `otp_code_for_test_table`, `demo_otp_preview`, `extracted_otp`, `password`, `password_hash`, `password_hint`, `password_plain_hint`, `issued_password`, `voiceprint`, `voiceprints`, `embedding`, `deep_embedding`, v.v., bao gồm cả chuỗi JSON bên trong cột `details_json` của SQLite) trên toàn bộ các endpoint tổng quan và nhật ký (`/api/auth3/overview`, `/api/logs/dashboard`, `/api/server_logs_and_db`, `/api/sqlite/overview`, `/api/logs/sql_query`, `/api/sqlite/query`).
  4. **Giữ nguyên 100% các bản vá `p7-sec` và `p6-otp`**:
     - Bảo toàn không mật khẩu cứng, không bypass chủ nhà, từ chối giọng người lạ, cấu hình [`simulator/config/voice_auth.json`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/config/voice_auth.json), ẩn `voiceprint`, bắt buộc xác thực `401` trên `/api/auth3/overview` khi chưa đăng nhập, `/api/state` không trả về `users` khi chưa đăng nhập, cùng cơ chế cooldown 60 giây và giới hạn tốc độ 429 khi nhập sai OTP quá số lần quy định.

---

## 2. URL Triển Khai Vercel Preview
- **Nhánh Git**: `p7-sec3` (không gộp vào `master`, không dùng `--prod`)
- **Preview Deployment URL (Mới nhất)**: `https://sec3-eirptowwv-tuananhs-projects-8aea56ce.vercel.app` (`dpl_G9CxqGZ7Jh5ticNTAAtoBtXVaXjg`)
- **Preview Deployment URL (Vòng 1)**: `https://sec3-h2xpveesq-tuananhs-projects-8aea56ce.vercel.app` (`dpl_EgmwD6knBdMoxiFftaS5TGTdiDgU`)
- **Alias URL**: `https://sec3-puce.vercel.app`

---

## 3. Danh Sách Tệp Thay Đổi
1. [`simulator/voice_config.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/voice_config.py): Mở rộng `_FORBIDDEN_RESPONSE_KEYS`, bổ sung `is_forbidden_overview_or_log_key`, `redact_otp_and_secrets_in_text` (che `Mật khẩu gợi ý: ...` và cặp khóa-giá trị mật khẩu nội dòng bằng `"******"`), `sanitize_overview_and_logs_payload`.
2. [`simulator/auth_3layer.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/auth_3layer.py): Ngừng ghi `otp_code` vào `detail` và `extra` trong `layer1_login`, `request_password_reset_otp`, `layer2_verify_otp`; lọc tại `_log_event` và tự động làm sạch `AUTH_EVENTS_FILE` trong `_load_state`.
3. [`simulator/auth/invite_and_gmail_mixin.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/auth/invite_and_gmail_mixin.py): Ngừng ghi `otp_code` và `issued_password` vào `detail`/`extra` trong `start_invite_oauth_registration`; xóa lộ mã OTP thật trong thông báo lỗi của `verify_invite_otp_and_create_account`.
4. [`simulator/auth/test_suite_mixin.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/auth/test_suite_mixin.py): Ngừng nhúng mã OTP thật vào báo cáo kiểm thử `TEST-01`, `TEST-02`, `TEST-04`; bọc `get_overview` bằng `sanitize_overview_and_logs_payload`.
5. [`simulator/engine/audit_logger.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/engine/audit_logger.py): Bổ sung `redact_stored_audit_logs_jsonl()`, lọc `summary` và `details` trước khi ghi xuống `system_audit_logs.jsonl` và SQLite.
6. [`simulator/database_sqlite.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/database_sqlite.py): Bổ sung `_redact_sqlite_audit_logs_in_conn()` khi khởi tạo CSDL và lọc `summary`/`details_json` trong `insert_audit_log_sqlite` và `sync_engine_state_to_sqlite`.
7. [`simulator/api/routes_auth.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/api/routes_auth.py): Bọc `/api/auth3/overview` và `/api/auth3/run_tests` bằng `sanitize_overview_and_logs_payload`; ẩn các trường test OTP trên `/api/auth3/layer1_login` và `/api/auth3/invite_oauth_start` khi không ở chế độ test; làm sạch `details` trước khi truyền vào `append_audit_log`.
8. [`simulator/api/routes_qr.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/api/routes_qr.py): Xóa trường `otp_code` khỏi phản hồi `/api/auth3/guest_qr_send_otp`, kiểm soát trường test OTP theo `is_test_otp_fields_allowed`, và làm sạch `details` trong `append_audit_log`.
9. [`simulator/api/routes_logs.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/api/routes_logs.py): Bọc `/api/logs/dashboard`, `/api/server_logs_and_db`, `/api/sqlite/overview`, `/api/logs/sql_query`, `/api/sqlite/query` bằng `sanitize_overview_and_logs_payload`.
10. [`simulator/static/js/guest_enroll.js`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/static/js/guest_enroll.js): Không tự điền `otp_code` từ phản hồi API vào ô nhập OTP của khách.
11. [`simulator/data/auth_3layer_events.json`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/data/auth_3layer_events.json), [`simulator/data/system_audit_logs.jsonl`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/data/system_audit_logs.jsonl), [`simulator/data/smarthome.db`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/data/smarthome.db): Đã làm sạch toàn bộ mã OTP, mật khẩu gợi ý và vector giọng nói lịch sử.
12. [`tests/test_p7_sec3_otp_log_redaction.py`](file:///C:/Users/LENOVO/datn-wt/sec3/tests/test_p7_sec3_otp_log_redaction.py) & [`tests/test_p4_survey1_security_auth.py`](file:///C:/Users/LENOVO/datn-wt/sec3/tests/test_p4_survey1_security_auth.py): Bộ kiểm thử TDD toàn diện cho các yêu cầu bảo mật `p7-sec3` (5 ca kiểm thử trong `test_p7_sec3_otp_log_redaction.py`).

---

## 4. Kết Quả Kiểm Thử & Đối Chiếu Toàn Bộ Suite (`p7-sec3` vs `base 5f6f200`)

### 4.1. Kiểm thử mục tiêu (Failure #1 & Bộ 8 tệp Bảo mật + OTP)
- **Kiểm thử ca hồi quy `test_bug1_logs_api_masks_password_hints`**:
  ```bash
  python -m pytest tests/test_challenger_m1_2_adversarial.py tests/test_p4_survey1_security_auth.py tests/test_p7_sec3_otp_log_redaction.py -q
  ```
  - **Kết quả**: `27 passed in 19.56s` (`Exit Code: 0`).
- **Full Security & OTP Regression Suite (8 tệp)**:
  ```bash
  python -m pytest tests/test_p7_sec3_otp_log_redaction.py tests/test_p7_security_hardening.py tests/test_r1_security_otp_response_fields.py tests/test_r2_cooldown_and_rate_limit_tdd.py tests/test_p4_survey1_security_auth.py tests/test_challenger_m1_2_adversarial.py tests/test_milestone_m2_qr_guest.py tests/test_m3_email_allowlist_and_mobile.py -q
  ```
  - **Kết quả**: `73 passed, 3 warnings in 80.46s` (`Exit Code: 0`).

### 4.2. Đối chiếu toàn bộ `python -m pytest tests -q` giữa `base 5f6f200` và `p7-sec3`

| Môi trường / Nhánh | Tổng số test thu thập | `passed` | `failed` | `errors` | `skipped` | Ghi chú đối chiếu |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Base `5f6f200`** (`C:\Users\LENOVO\datn-wt\base5f6f` sạch) | 1.478 | **1.365** (1.368 ổn định) | **107** (104 cố định + 3 nhạy thứ tự/thời gian) | **5** | 1 | 104 lỗi cố định và 5 error tồn tại sẵn trên `master` (`5f6f200`). |
| **`p7-sec3` trước khi vá** (`ed4625d`) | 1.482 | **1.371** | **105** (104 cố định + 1 hồi quy) | **5** | 1 | 1 hồi quy so với base: `test_bug1_logs_api_masks_password_hints` (do `[REDACTED]` thay vì `******`). |
| **`p7-sec3` sau khi vá** (Bản hiện tại) | 1.483 | **1.373** | **104** | **5** | 1 | **0 hồi quy so với `base 5f6f200`**. Toàn bộ 100% test đạt trên `5f6f200` đều đạt trên `p7-sec3`, cộng thêm 5/5 test mới trong `test_p7_sec3_otp_log_redaction.py`. |

- **Chi tiết các test chênh lệch đã xử lý triệt để**:
  1. `tests/test_p4_survey1_security_auth.py::TestBug1SecurityCredentialCleanup::test_bug1_logs_api_masks_password_hints`: **ĐÃ SỬA (`PASS`)** — giữ nguyên assertion của test và chuẩn hóa `redact_otp_and_secrets_in_text` xuất `"Mật khẩu gợi ý: ******"`.
  2. `tests/test_challenger_m1_2_adversarial.py::TestAdversarialBug1CredentialScan::test_adversarial_logs_dict_key_masking_edge_case`: **ĐÃ SỬA (`PASS`)** — `mask_sensitive_log_data` giữ nguyên chuỗi che `"******"` khi gọi qua `redact_otp_and_secrets_in_text`.
  3. `tests/test_phase7_m3_invariants.py::TestPhase7InvariantsAndSafetyBoundaries::test_zero_crlf_in_tracked_and_modified_files`: **ĐẠT (`PASS`)** — chuẩn hóa 0 dòng trắng thừa cuối tệp và 0 CRLF (`git diff --check` trả về `0`).
  4. `tests/test_challenger_m3_playwright_e2e.py` (6 ca E2E Playwright trên cổng cố định `8993`): **ĐẠT 6/6 (`PASS`)** khi chạy độc lập không tranh chấp cổng `8993`.

---

## 5. Báo Cáo Tìm Hiểu Bổ Sung (Yêu Cầu 4 — Report Only: `/api/logs/dashboard`)
- **Câu hỏi**: Endpoint `GET /api/logs/dashboard` không yêu cầu xác thực và trả về nhiều địa chỉ email trong nhật ký. Hành vi này có tồn tại từ trước trên `master` (`5f6f200`) hay không?
- **Kết luận**: **CÓ — Tồn tại từ trước (Pre-existing) 100% trên `master` (`5f6f200`)**.
- **Bằng chứng mã nguồn trên `5f6f200`** (`git show 5f6f200:simulator/api/routes_logs.py`, dòng `99-250`):
  - Hàm `api_logs_dashboard` phục vụ `GET /api/logs/dashboard` và `GET /api/server_logs_and_db` không chặn `401` khi `sess.is_authenticated` là `False`. Biến `is_admin` chỉ được dùng để ẩn `sample_rows` của 2 bảng `users` và `voiceprints`, ẩn `all_user_pools`, và ẩn `accounts_3layer`.
  - Khi gọi không xác thực trên `5f6f200`, endpoint này vẫn trả về `audit_logs` (tối đa 300 bản ghi từ `read_audit_logs(limit=300)`) và `sqlite_overview` (bao gồm `sample_rows` của bảng `audit_logs`), trong đó các trường `actor`, `user`, `user_name`, `summary`, `details` chứa các địa chỉ email lịch sử.
  - Theo đúng yêu cầu số 4 (`do not change it in this round`), cơ chế xác thực của `/api/logs/dashboard` được giữ nguyên trong vòng này.

---

## 6. Các Bước Xác Minh (Verification Steps)
1. **Chạy kiểm thử bảo mật & chống lộ OTP**:
   ```bash
   python -m pytest tests/test_p7_sec3_otp_log_redaction.py tests/test_p4_survey1_security_auth.py tests/test_challenger_m1_2_adversarial.py -q
   ```
2. **Kiểm tra tệp nhật ký lưu trữ trên đĩa không còn bất kỳ khóa `otp_code` hay chuỗi 6 số OTP nào**:
   ```bash
   python -c "import json, pathlib, re; ev = json.loads(pathlib.Path('simulator/data/auth_3layer_events.json').read_text(encoding='utf-8')); assert 'otp_code' not in json.dumps(ev); assert not [x for x in ev if re.search(r'\b\d{6}\b', json.dumps({k:v for k,v in x.items() if k!='id'}))]; print('CLEAN')"
   ```
3. **Kiểm tra chuẩn dòng kết thúc LF & `git diff --check`**:
   ```bash
   git diff --check
   python -m pytest tests/test_phase7_m3_invariants.py -k test_zero_crlf -q
   ```
