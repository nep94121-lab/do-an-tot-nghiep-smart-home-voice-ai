# Báo Cáo Khắc Phục Bảo Mật `p7-sec3` (`FIX_REPORT_SEC3.md`)

## 1. Tóm Tắt Vấn Đề & Giải Pháp
- **Vấn đề phát hiện trên Production**: Endpoint `GET /api/auth3/overview` (khi đã đăng nhập) trả về mã OTP 6 chữ số dạng rõ (`plaintext`) bên trong `verification_logs[].extra.otp_code`, `recent_logs[].extra.otp_code`, chuỗi mô tả `detail` và báo cáo `test_report.cases`. Ngoài ra, các tệp nhật ký lưu trữ (`simulator/data/auth_3layer_events.json`, `simulator/data/system_audit_logs.jsonl`, bảng `audit_logs` trong `simulator/data/smarthome.db`) còn lưu các bản ghi lịch sử chứa `otp_code`, `otp_code_for_test_table`, `demo_otp_preview`, mật khẩu cấp phát và vector sinh trắc học giọng nói.
- **Giải pháp đã triển khai**:
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
     - Bảo toàn không mật khẩu cứng, không bypass chủ nhà, từ chối giọng người lạ, cấu hình [`simulator/config/voice_auth.json`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/config/voice_auth.json), ẩn `voiceprint`, bắt buộc xác thực trên `/api/state` và `/api/auth3/overview`, cùng cơ chế cooldown 60 giây và giới hạn tốc độ 429 khi nhập sai OTP quá số lần quy định.

---

## 2. URL Triển Khai Vercel Preview
- **Nhánh Git**: `p7-sec3` (không đẩy lên `master`, không dùng `--prod`)
- **Preview Deployment URL**: `https://sec3-h2xpveesq-tuananhs-projects-8aea56ce.vercel.app`
- **Alias URL**: `https://sec3-puce.vercel.app`
- **Deployment ID**: `dpl_EgmwD6knBdMoxiFftaS5TGTdiDgU`

---

## 3. Danh Sách Tệp Thay Đổi
1. [`simulator/voice_config.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/voice_config.py): Mở rộng `_FORBIDDEN_RESPONSE_KEYS`, bổ sung `is_forbidden_overview_or_log_key`, `redact_otp_and_secrets_in_text`, `sanitize_overview_and_logs_payload`.
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
12. [`tests/test_p7_sec3_otp_log_redaction.py`](file:///C:/Users/LENOVO/datn-wt/sec3/tests/test_p7_sec3_otp_log_redaction.py) & [`tests/test_p4_survey1_security_auth.py`](file:///C:/Users/LENOVO/datn-wt/sec3/tests/test_p4_survey1_security_auth.py): Bộ kiểm thử TDD toàn diện cho 4 yêu cầu bảo mật `p7-sec3`.

---

## 4. Kết Quả Kiểm Thử (TDD Red -> Green)
- **TDD Red Phase** (`pytest tests/test_p7_sec3_otp_log_redaction.py -q` trước khi sửa): `4 failed` (phát hiện chính xác `$.verification_logs[*].extra.otp_code`, `$.recent_logs[*].extra.otp_code`, lộ OTP trong lỗi link mời và trong tệp log lưu trữ).
- **TDD Green Phase** (`pytest tests/test_p7_sec3_otp_log_redaction.py -q` sau khi sửa): `4 passed`.
- **Full Security & OTP Regression Suite**:
  ```bash
  python -m pytest tests/test_p7_sec3_otp_log_redaction.py tests/test_p7_security_hardening.py tests/test_r1_security_otp_response_fields.py tests/test_r2_cooldown_and_rate_limit_tdd.py tests/test_p4_survey1_security_auth.py tests/test_milestone_m2_qr_guest.py tests/test_m3_email_allowlist_and_mobile.py -q
  ```
  - **Kết quả**: `67 passed in 37.17s` (Exit Code: `0`).

---

## 5. Các Bước Xác Minh (Verification Steps)
1. **Chạy kiểm thử tự động**:
   ```bash
   python -m pytest tests/test_p7_sec3_otp_log_redaction.py -q
   ```
2. **Kiểm tra tệp nhật ký lưu trữ trên đĩa không còn bất kỳ khóa `otp_code` hay chuỗi 6 số OTP nào**:
   ```bash
   python -c "import json, pathlib, re; ev = json.loads(pathlib.Path('simulator/data/auth_3layer_events.json').read_text(encoding='utf-8')); assert 'otp_code' not in json.dumps(ev); assert not [x for x in ev if re.search(r'\b\d{6}\b', json.dumps({k:v for k,v in x.items() if k!='id'}))]; print('CLEAN')"
   ```
3. **Kiểm tra bản triển khai Vercel Preview**:
   ```bash
   npx vercel curl /api/auth3/overview --deployment https://sec3-h2xpveesq-tuananhs-projects-8aea56ce.vercel.app
   ```
   Phản hồi trả về `401 Unauthorized` khi chưa đăng nhập, và khi truy vấn đã xác thực hoàn toàn không chứa khóa `otp_code`, `password_hash`, hay `voiceprint`.
