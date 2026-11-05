# BÁO CÁO REBASE & KHẮC PHỤC 10 HỒI QUY TRÊN NHÁNH `p7-sec3` (ROUND 2)

- **Nhánh làm việc:** `p7-sec3`
- **Worktree:** `C:\Users\LENOVO\datn-wt\sec3`
- **Base commit sau khi Rebase (`origin/master`):** `f61292c3621e1650cb6aa311a7a29a43034bdedd` (*Merge origin/p7-guest into p7-guest-merge: Level 3 Guest QR page + Master Security Hardening*)
- **Vercel Preview URL (Non-Production):** `https://sec3-kcjlksohy-tuananhs-projects-8aea56ce.vercel.app` (`dpl_8FjXJozauUtr48MQ5X92YRFEgs8S`, `target: null`)

---

## 1. Kết Quả Rebase `p7-sec3` Lên `origin/master` (`f61292c`) & Giải Quyết Xung Đột

1. **Quá trình Rebase:**
   - Trước khi rebase, `p7-sec3` (`87bf528`) nằm trên `5f6f200` (thiếu bản merge `f61292c` từ nhánh `p7-guest`).
   - Đã chạy `git fetch origin` và `git rebase origin/master` (`f61292c3621e1650cb6aa311a7a29a43034bdedd`).
   - Tệp [`simulator/api/routes_qr.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/api/routes_qr.py) tự động gộp sạch (auto-merged), giữ nguyên toàn bộ cổng xác thực phiên của `f61292c` đồng thời giữ cơ chế ẩn `otp_code` và `sanitize_overview_and_logs_payload` của `p7-sec3`.
2. **Giải quyết xung đột tại [`simulator/static/js/guest_enroll.js`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/static/js/guest_enroll.js):**
   - **Giữ nguyên toàn bộ tính năng Khách Cấp 3 từ `origin/master` (`f61292c`):** Luồng thu âm giọng nói `sendGuestVoicePayload`, bước xác nhận kích hoạt `confirmAndActivateGuestVoice` / `retryGuestVoiceRecording`, và luồng xác thực 2 ô email `submitDoubleEmailOtp` / `verifyGuestEmailOtp`.
   - **Giữ nguyên bất biến bảo mật của `p7-sec3` (Zero OTP Autofill):** Tại hàm [`submitDoubleEmailOtp`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/static/js/guest_enroll.js#L620-L654), ô nhập OTP luôn được đặt rỗng (`if (otpIn) otpIn.value = '';`), tuyệt đối không tự điền `data.demo_otp_preview` hay `data.otp_code` vào DOM hoặc console/log.
   - Đã kiểm tra không còn bất kỳ conflict marker (`<<<<<<<`, `=======`, `>>>>>>>`) nào trong toàn bộ mã nguồn.

---

## 2. Nguyên Nhân Gốc Rễ (Root Cause) & Giải Pháp Cho 10 Bài Test Hồi Quy

| # | Bài kiểm thử (Test NodeID) | Nguyên nhân gốc rễ (Root Cause) | Giải pháp khắc phục | Trạng thái |
|---|---|---|---|---|
| 1 | `tests/e2e/test_tier1_feature_coverage.py::TestTier1FeatureCoverage::test_feat09_7_devices_actuation` | [`FileStateBackend.__init__`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/engine/state_store.py#L115-L122) dùng chung một đường dẫn tệp toàn cục duy nhất trong `%TEMP%\smarthome_shared_device_state.json` cho mọi worktree trên máy. Khi có tiến trình kiểm thử hoặc server ở worktree khác ghi đè trạng thái thiết bị, `execute_device_action` đọc phải trạng thái đã bật sẵn (`old_state == new_state`) và trả câu `"Đèn phòng khách đã bật sẵn rồi."` thay vì `"Đèn phòng khách đã bật."`. | Cô lập đường dẫn mặc định của `FileStateBackend` theo mã băm SHA-256 của thư mục gốc worktree (`smarthome_shared_device_state_{wt_hash}.json`) tại [`simulator/engine/state_store.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/engine/state_store.py#L115-L122), vừa bảo toàn chia sẻ đa instance trong cùng worktree vừa chống nhiễu chéo giữa các worktree. | **PASSED** |
| 2 | `tests/test_challenger_m3_playwright_e2e.py::TestMilestone3LiveBrowserE2E::test_e2e_bug13_logs_pagination_and_load_more` | Khi chạy tuần tự cả bộ test, `tests/test_challenger_m1_2_adversarial.py` chạy ngay trước `tests/test_challenger_m3_playwright_e2e.py` và gọi `clear_audit_logs()`, xóa trắng `simulator/data/system_audit_logs.jsonl` về 0 dòng. Bản `p7-sec3` trước khi rebase lên `f61292c` thiếu hàm `_restore_tracked_data_files()` trong [`tests/conftest.py`](file:///C:/Users/LENOVO/datn-wt/sec3/tests/conftest.py#L48-L62), khiến trang `/logs` không đủ >20 bản ghi để phân trang. | Rebase lên `f61292c` đưa `_restore_tracked_data_files()` vào autouse fixture [`clean_auth_pending_otps`](file:///C:/Users/LENOVO/datn-wt/sec3/tests/conftest.py#L80-L120) và hook `pytest_sessionfinish`, tự động khôi phục nguyên trạng 942 dòng log đã che mặt nạ của `system_audit_logs.jsonl` sau mỗi bài test. | **PASSED** |
| 3 | `tests/test_challenger_phase6_m1.py::TestSeedAccountsAndFixturesAudit::test_accounts_3layer_deep_audit` | Các bài test chạy trước (như `test_challenger_m2_gen2_stress.py`) tạo thêm tài khoản hoặc sửa đổi `simulator/data/accounts_3layer.json` trên đĩa và trong RAM `mgr.accounts`; trước khi rebase lên `f61292c`, `tests/conftest.py` không hoàn nguyên `accounts_3layer.json` và `mgr.accounts` sau mỗi bài test. | Khôi phục cả `mgr.accounts = copy.deepcopy(_INITIAL_MGR_ACCOUNTS)` trong RAM lẫn tệp `accounts_3layer.json` trên đĩa thông qua `_restore_tracked_data_files()` trong [`tests/conftest.py`](file:///C:/Users/LENOVO/datn-wt/sec3/tests/conftest.py#L80-L120). | **PASSED** |
| 4 | `tests/test_challenger_phase6_m1.py::TestSeedAccountsAndFixturesAudit::test_family_email_allowlist_is_empty_json_object` | Các bài test đăng ký/mời thành viên chạy trước ghi thêm email vào `simulator/data/family_email_allowlist.json` và `mgr.family_email_allowlist` mà không dọn dẹp sau khi kết thúc test. | Bổ sung sao lưu & khôi phục `_INITIAL_MGR_ALLOWLIST` (`mgr.family_email_allowlist`), dọn `mgr.pending_invite_registrations`, và khôi phục `family_email_allowlist.json` về `{}` trong [`tests/conftest.py`](file:///C:/Users/LENOVO/datn-wt/sec3/tests/conftest.py#L80-L120). | **PASSED** |
| 5 | `tests/test_challenger_phase6_m1_2.py::TestDataIntegrityAndAllowlistCleanliness::test_family_email_allowlist_json_is_strictly_empty_object` | Cùng nguyên nhân rò rỉ dữ liệu `family_email_allowlist.json` trên đĩa và `mgr.family_email_allowlist` trong bộ nhớ giữa các bài test. | Đã khắc phục triệt để bằng cơ chế khôi phục `_INITIAL_MGR_ALLOWLIST` + `_restore_tracked_data_files()` trong [`tests/conftest.py`](file:///C:/Users/LENOVO/datn-wt/sec3/tests/conftest.py#L80-L120). | **PASSED** |
| 6 | `tests/test_challenger_phase6_m1_2.py::TestDataIntegrityAndAllowlistCleanliness::test_accounts_3layer_json_contains_only_six_canonical_accounts` | Cùng nguyên nhân rò rỉ tài khoản phát sinh vào `accounts_3layer.json` và `mgr.accounts` từ các bài test trước. | Đã khắc phục triệt để bằng cơ chế khôi phục `_INITIAL_MGR_ACCOUNTS` + `_restore_tracked_data_files()` trong [`tests/conftest.py`](file:///C:/Users/LENOVO/datn-wt/sec3/tests/conftest.py#L80-L120). | **PASSED** |
| 7 | `tests/test_phase6_r1_allowlist_isolation.py::TestCleanDataFixtures::test_accounts_3layer_json_contains_only_clean_default_accounts` | Cùng nguyên nhân rò rỉ tài khoản phát sinh vào `accounts_3layer.json` từ các bài test chạy trước. | Đã khắc phục triệt để bằng cơ chế khôi phục `_INITIAL_MGR_ACCOUNTS` + `_restore_tracked_data_files()` trong [`tests/conftest.py`](file:///C:/Users/LENOVO/datn-wt/sec3/tests/conftest.py#L80-L120). | **PASSED** |
| 8 | `tests/test_phase6_r1_allowlist_isolation.py::TestCleanDataFixtures::test_family_email_allowlist_json_is_empty_object` | Cùng nguyên nhân rò rỉ `family_email_allowlist.json` từ các bài test chạy trước. | Đã khắc phục triệt để bằng cơ chế khôi phục `_INITIAL_MGR_ALLOWLIST` + `_restore_tracked_data_files()` trong [`tests/conftest.py`](file:///C:/Users/LENOVO/datn-wt/sec3/tests/conftest.py#L80-L120). | **PASSED** |
| 9 | `tests/test_p3_session_rbac_concurrency.py::test_unauthenticated_request_defaults_to_tier3_and_blocked` | Có 2 nguyên nhân kết hợp: (a) Trước khi rebase lên `f61292c`, nhánh `p7-sec3` thiếu bản cập nhật tại `routes_devices.py` và `test_p3_session_rbac_concurrency.py` (kỳ vọng HTTP `401` cho request chưa xác thực); (b) Khi một bài test trước đăng nhập bằng tài khoản có `account_id = "owner_root_t1"` (hoặc `"family_member_a"`, `"guest_temp_c"`), `routes_auth.py` gọi `_REST_ENGINE.set_active_user(acc_id)` nhưng `role_alias_map` trong [`voice_rbac_mixin.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/engine/voice_rbac_mixin.py#L391-L401) chưa ánh xạ các `account_id` này, làm `_REST_ENGINE._current_role` rơi vào `"UNKNOWN"` và khiến `resolve_request_session` trả về `403` thay vì `401`. | (1) Rebase lên `f61292c`; (2) Bổ sung ánh xạ `"owner_root_t1": OWNER_ID`, `"family_member_a"`, `"family_member_b"`, `"guest_temp_c"` vào `role_alias_map` trong [`simulator/engine/voice_rbac_mixin.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/engine/voice_rbac_mixin.py#L391-L401); (3) Reset `_REST_ENGINE._explicit_test_user_set = False`, `_REST_ENGINE._current_role = "ADMIN"`, `_REST_ENGINE._current_user_id = "tuan_anh"` trong [`tests/conftest.py`](file:///C:/Users/LENOVO/datn-wt/sec3/tests/conftest.py#L102-L120). | **PASSED** |
| 10 | `tests/test_p3_session_rbac_concurrency.py::test_unsigned_cookie_tampering_ignored_and_defaults_to_tier3` | Cùng nguyên nhân với bài số 9: rò rỉ `_REST_ENGINE._current_role = "UNKNOWN"` giữa các bài test làm request gửi cookie không chữ ký bị trả về `403` thay vì `401`. | Đã khắc phục triệt để cùng bài số 9 tại [`simulator/engine/voice_rbac_mixin.py`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/engine/voice_rbac_mixin.py#L391-L401) và [`tests/conftest.py`](file:///C:/Users/LENOVO/datn-wt/sec3/tests/conftest.py#L102-L120). | **PASSED** |

---

## 3. Kết Quả Chạy Full Test Suite (`python -m pytest tests -q`) So Sánh Giữa `p7-sec3` Và `f61292c`

### 3.1. Các bộ kiểm thử bắt buộc và 10 bài test hồi quy
- `tests/test_p7_sec3_otp_log_redaction.py`: **5/5 PASSED (100%)**
- `tests/test_p7_security_hardening.py`: **15/15 PASSED (100%)**
- `tests/test_p4_survey1_security_auth.py`: **8/8 PASSED (100%)**
- `tests/test_phase7_guest_qr.py`: **13/13 PASSED (100%)**
- `tests/test_p3_session_rbac_concurrency.py`: **18/18 PASSED (100%)**
- Toàn bộ 10 bài test hồi quy được liệt kê trong `p7_sec3_fix2.txt`: **10/10 PASSED (100%)**

### 3.2. Đối chiếu toàn bộ 1.510 bài test (`python -m pytest tests -q`) với baseline `f61292c`
| Chỉ số | Baseline sạch `f61292c` (`basef612`) | Nhánh `p7-sec3` sau khi sửa | Chênh lệch |
|---|---|---|---|
| **Tổng số bài test thu thập** | 1.505 (chưa gồm 5 bài mới của `test_p7_sec3_otp_log_redaction.py`) | 1.510 (gồm 5 bài mới của `test_p7_sec3_otp_log_redaction.py`) | +5 bài test bảo mật mới |
| **Passed** | 1.389 | **1.394** | **+5 passed** |
| **Skipped** | 1 | **1** | 0 |
| **Failed + Errors (Pre-existing trên `f61292c`)** | 115 (110 failed + 5 errors; gồm 95 bài trong tập 105 nodeids ban đầu + 20 bài M2/M3/M4/M5/M8 cũ gọi `/api/auth3/guest_qr_current` không kèm header sau khi `f61292c` bật cổng 401) | **115** (110 failed + 5 errors — trùng khớp 100% từng nodeid với `f61292c`) | **0 NEW failures** |
| **Số lỗi mới phát sinh do `p7-sec3`** | — | **0** | **0** |

---

## 4. Kiểm Chứng Các Bất Biến Bảo Mật & Vercel Preview Deployment

### 4.1. Kiểm chứng các bất biến bảo mật cục bộ
1. **Không có mã OTP 6 chữ số dạng rõ hoặc khóa `otp_code` trong mọi tệp log & CSDL:**
   - [`simulator/data/auth_3layer_events.json`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/data/auth_3layer_events.json): `0` mã OTP 6 số dạng rõ.
   - [`simulator/data/system_audit_logs.jsonl`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/data/system_audit_logs.jsonl): `0` mã OTP 6 số dạng rõ (giữ nguyên đủ 942 dòng lịch sử).
   - [`simulator/data/smarthome.db`](file:///C:/Users/LENOVO/datn-wt/sec3/simulator/data/smarthome.db) (`audit_logs`): `0` mã OTP 6 số dạng rõ.
2. **Các API trả dữ liệu tổng quan, log và gửi OTP:**
   - `/api/auth3/overview` (kể cả khi dùng `X-Session-Token` của Chủ nhà Cấp 1): `0` khóa nhạy cảm (`otp`, `otp_code`, `password_hash`, `voiceprint`, ...), `0` mã OTP 6 số dạng rõ.
   - `/api/auth3/overview` khi chưa xác thực: trả về **HTTP `401 Unauthorized`**.
   - `/api/state`: tuyệt đối không chứa khóa `users` (`has_users: False`).
   - `/api/logs/dashboard`: `0` mã OTP 6 số dạng rõ; các gợi ý mật khẩu vẫn được che bằng `******`.

### 4.2. Kiểm chứng trực tiếp trên Vercel Preview (`https://sec3-kcjlksohy-tuananhs-projects-8aea56ce.vercel.app`)
Đã triển khai bằng lệnh `npx vercel --yes` (tuyệt đối không dùng `--prod`) và kiểm chứng trực tiếp qua `npx vercel curl`:

1. **`GET /api/auth3/overview` (Unauthenticated):**
   - **HTTP Status:** `401 Unauthorized`
   - **Payload:** `{"ok":false,"error":"Yêu cầu đăng nhập Chủ nhà Cấp 1 hoặc Thành viên để xem tổng quan xác thực 3 lớp (HTTP 401 Unauthorized).","status_code":401,"accounts":[],"total_accounts":0,"verification_logs":[],"family_email_allowlist":[]}`
2. **`GET /api/state`:**
   - **HTTP Status:** `200 OK`
   - **Kiểm tra khóa `users`:** `has_users: False` (không lộ danh sách người dùng).
3. **`GET /api/logs/dashboard`:**
   - **HTTP Status:** `200 OK` (`ok: True`, `audit_logs_count: 100`)
   - **Số mẫu OTP 6 chữ số dạng rõ (`plaintext_6digit_otp_matches`):** `0`.
