# Báo Cáo Khắc Phục Lỗ Hổng Bảo Mật Cổng Nhật Ký & CSDL (`p8-logs-gate`)

## 1. Bối Cảnh & Lỗ Hổng Trên Production
- **Worktree:** `C:\Users\LENOVO\datn-wt\logsgate`
- **Nhánh:** `p8-logs-gate` (tách từ `origin/master` tại commit `f61292c3621e1650cb6aa311a7a29a43034bdedd`)
- **Hiện tượng lỗ hổng đã xác nhận trước đó:** Truy vấn không xác thực `GET /api/logs/dashboard` trên Production trả về `HTTP 200` (~462 KB) kèm địa chỉ Gmail nguyên bản của người dùng trong `audit_logs`, `sqlite_overview` và `accounts_3layer`.

---

## 2. Danh Sách Toàn Bộ 11 Endpoints Nhật Ký / CSDL / DevOps Được Kiểm Toán & Khoá Cổng Admin Tier 1

Qua kiểm toán toàn diện [`simulator/api/routes_logs.py`](file:///C:/Users/LENOVO/datn-wt/logsgate/simulator/api/routes_logs.py), [`simulator/api/routes_auth.py`](file:///C:/Users/LENOVO/datn-wt/logsgate/simulator/api/routes_auth.py), [`simulator/api/routes_devices.py`](file:///C:/Users/LENOVO/datn-wt/logsgate/simulator/api/routes_devices.py), [`simulator/api/routes_qr.py`](file:///C:/Users/LENOVO/datn-wt/logsgate/simulator/api/routes_qr.py) và [`api/index.py`](file:///C:/Users/LENOVO/datn-wt/logsgate/api/index.py), toàn bộ **11 route paths (7 hàm handler)** phục vụ nhật ký, truy vấn/tổng quan SQLite, tri thức RAG và trạng thái DevOps nằm tại [`simulator/api/routes_logs.py`](file:///C:/Users/LENOVO/datn-wt/logsgate/simulator/api/routes_logs.py):

| STT | Phương Thức & Đường Dẫn (`Path`) | Hàm Xử Lý (`Handler`) | Cổng Phân Quyền | Che Email & Bí Mật |
| :-: | :--- | :--- | :--- | :--- |
| 1 | `GET /api/logs/dashboard` | `api_logs_dashboard` | `_require_admin_session` (`Tier 1 ADMIN`) | `sanitize_api_payload(mask_sensitive_log_data(...))` |
| 2 | `GET /api/server_logs_and_db` | `api_logs_dashboard` (alias) | `_require_admin_session` (`Tier 1 ADMIN`) | `sanitize_api_payload(mask_sensitive_log_data(...))` |
| 3 | `POST /api/logs/sql_query` | `api_logs_sql_query` | `_require_admin_session` (`Tier 1 ADMIN`) + `_FORBIDDEN_SQL_KEYWORDS` | `sanitize_api_payload(mask_sensitive_log_data(...))` |
| 4 | `POST /api/sqlite/query` | `api_logs_sql_query` (alias) | `_require_admin_session` (`Tier 1 ADMIN`) + `_FORBIDDEN_SQL_KEYWORDS` | `sanitize_api_payload(mask_sensitive_log_data(...))` |
| 5 | `POST /api/logs/knowledge/add` | `api_logs_knowledge_add` | `_require_admin_session` (`Tier 1 ADMIN`) | `sanitize_api_payload(mask_sensitive_log_data(...))` |
| 6 | `POST /api/kb_upsert` | `api_logs_knowledge_add` (alias) | `_require_admin_session` (`Tier 1 ADMIN`) | `sanitize_api_payload(mask_sensitive_log_data(...))` |
| 7 | `POST /api/logs/append` | `api_logs_append` | `_require_admin_session` (`Tier 1 ADMIN`) | Trả `{"ok": True}` |
| 8 | `POST /api/logs/clear` | `api_logs_clear` | `_require_admin_session` (`Tier 1 ADMIN`) | Trả thông điệp xác nhận tĩnh |
| 9 | `POST /api/clear_audit_logs` | `api_logs_clear` (alias) | `_require_admin_session` (`Tier 1 ADMIN`) | Trả thông điệp xác nhận tĩnh |
| 10 | `GET /api/sqlite/overview` | `api_sqlite_overview` | `_require_admin_session` (`Tier 1 ADMIN`) | `sanitize_api_payload(mask_sensitive_log_data(...))` |
| 11 | `GET /api/devops/status` | `api_devops_status` | `_require_admin_session` (`Tier 1 ADMIN`) | `sanitize_api_payload(mask_sensitive_log_data(...))` |

---

## 3. Phân Định Phần Đã Thực Hiện Trước Khi Gián Đoạn vs. Phần Hoàn Thiện Mới

### 3.1. Phần đã có trong working tree từ phiên trước (được giữ nguyên & kế thừa)
1. **Backend ([`simulator/api/routes_logs.py`](file:///C:/Users/LENOVO/datn-wt/logsgate/simulator/api/routes_logs.py)):**
   - Đã cài đặt `_require_admin_session(request)` sử dụng `resolve_request_session(request, payload=None, engine=None)` (từ chối giả mạo danh tính qua JSON payload):
     - Chưa xác thực (`not sess.is_authenticated`) $\rightarrow$ `HTTP 401 Unauthorized`.
     - Đã xác thực nhưng không phải Chủ nhà (`sess.tier != 1 or sess.role != "ADMIN"`) $\rightarrow$ `HTTP 403 Forbidden`.
   - Đã cài đặt `mask_email_address` (`n***@domain`), `_mask_string_secrets_and_emails` và `mask_sensitive_log_data` đệ quy trên `str`, `dict`, `list` và chuỗi JSON lồng nhau.
2. **Frontend ([`simulator/static/js/logs.js`](file:///C:/Users/LENOVO/datn-wt/logsgate/simulator/static/js/logs.js) & [`simulator/static/js/auth_pages.js`](file:///C:/Users/LENOVO/datn-wt/logsgate/simulator/static/js/auth_pages.js)):**
   - Đã cài đặt `installLogsAuthFetchInterceptor()` trong `logs.js` tự động đính kèm `credentials: 'same-origin'` và header phiên xác thực khi gọi `/api/*`.
   - Đã đồng bộ `auth_pages.js` lưu khóa phiên vào `localStorage` và `sessionStorage` khi đăng nhập qua `/login`.
3. **Kiểm thử TDD ([`tests/test_p8_logsgate.py`](file:///C:/Users/LENOVO/datn-wt/logsgate/tests/test_p8_logsgate.py)) & 7 tệp test hồi quy:**
   - Đã viết 49 ca kiểm thử trong `tests/test_p8_logsgate.py` và cập nhật 7 tệp test hồi quy gọi `/api/logs/*` với phiên Admin hợp lệ.

### 3.2. Phần hoàn thiện mới trong phiên tiếp nối này
1. **Tăng cường che bí mật dạng `key=value` / `key: value` không bọc dấu nháy trong văn bản tự do:**
   - Bổ sung biểu thức chính quy trong `_mask_string_secrets_and_emails` ([`simulator/api/routes_logs.py`](file:///C:/Users/LENOVO/datn-wt/logsgate/simulator/api/routes_logs.py#L70-L75)) và `maskSensitiveLogText` ([`simulator/static/js/logs.js`](file:///C:/Users/LENOVO/datn-wt/logsgate/simulator/static/js/logs.js#L75-L76)) để che triệt cả các cặp khóa-giá trị nhạy cảm (`password`, `password_hint`, `password_plain_hint`, `hint`, `otp`, `otp_code`, `secret`, `token`, `mat_khau`, `mk`) khi xuất hiện trong chuỗi tự do không có dấu nháy bao quanh.
2. **Phòng thủ chiều sâu (Defense-in-Depth) trên giao diện `/logs`:**
   - Bọc `maskSensitiveLogText(...)` cho toàn bộ dữ liệu xuất CSV trong `exportLogsCsv()` ([`simulator/static/js/logs.js`](file:///C:/Users/LENOVO/datn-wt/logsgate/simulator/static/js/logs.js#L341-L351)) và bảng kết quả truy vấn SQL trong `executeCustomSql()` ([`simulator/static/js/logs.js`](file:///C:/Users/LENOVO/datn-wt/logsgate/simulator/static/js/logs.js#L409-L413)).
3. **Mở rộng kiểm thử & Chuẩn hóa LF:**
   - Mở rộng [`tests/test_p8_logsgate.py`](file:///C:/Users/LENOVO/datn-wt/logsgate/tests/test_p8_logsgate.py#L207-L229) kiểm tra mẫu `password_hint` và `otp_code` không dấu nháy.
   - Chuẩn hóa định dạng UTF-8 (không BOM) và ngắt dòng chuẩn LF (`\n`, `0 CRLF`) trên toàn bộ tệp thay đổi.
4. **Commit trên nhánh `p8-logs-gate`, triển khai Vercel Preview và xác minh thực tế bằng `vercel curl`.**

---

## 4. Kết Quả Kiểm Thử Pytest (Base `f61292c` vs. Sau Khi Vá `p8-logs-gate`)

| Hạng Mục Kiểm Thử | Base `f61292c` | Sau Khi Vá (`p8-logs-gate`) | Chênh Lệch |
| :--- | :-: | :-: | :-: |
| **Tổng số bài test thu thập (`collected`)** | `1511` | `1560` | **`+49` tests mới** |
| **Số bài test đạt (`passed`)** | `1387` | `1436` | **`+49` passed** |
| **Số bài test lỗi mới phát sinh (`new failures`)** | `0` | `0` | **`0` hồi quy** |
| **Số bài test lỗi/error pre-existing (Playwright live server ngoài)** | `118 failed, 1 skipped, 5 errors` | `118 failed, 1 skipped, 5 errors` | Không đổi (`0` lỗi mới) |
| **Bộ test chuyên biệt `pytest tests/test_p8_logsgate.py`** | Chưa có (`48 failed, 1 passed` ở pha RED) | **`49 passed in 17.61s`** | **100% PASS** |
| **Bộ test bảo mật `pytest tests/test_p7_security_hardening.py`** | `10 passed` | **`10 passed`** | **100% PASS** |

---

## 5. Triển Khai Vercel Preview & Xác Minh Thực Tế (`curl` / `vercel curl`)

- **Môi trường triển khai:** Vercel **PREVIEW** (tuyệt đối không dùng `--prod`)
- **Preview URL:** `https://do-an-tot-nghiep-smart-home-voice-aem6ef86f.vercel.app`
- **Deployment ID:** `dpl_Hf92MDRxk9ezNQH5B44DWZpXN5cL`

### 5.1. Kiểm tra truy cập không xác thực (Unauthenticated) trên toàn bộ 11 Endpoints
Thực thi `vercel curl <endpoint> --deployment https://do-an-tot-nghiep-smart-home-voice-aem6ef86f.vercel.app` (không đính kèm phiên đăng nhập):

| Endpoint | Phương Thức | Mã HTTP Thực Tế Trên Preview | Phản Hồi JSON |
| :--- | :-: | :-: | :--- |
| `/api/logs/dashboard` | `GET` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| `/api/server_logs_and_db` | `GET` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| `/api/sqlite/overview` | `GET` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| `/api/devops/status` | `GET` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| `/api/logs/sql_query` | `POST` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| `/api/sqlite/query` | `POST` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| `/api/logs/knowledge/add` | `POST` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| `/api/kb_upsert` | `POST` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| `/api/logs/append` | `POST` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| `/api/logs/clear` | `POST` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| `/api/clear_audit_logs` | `POST` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |

### 5.2. Kiểm tra phân quyền RBAC (Non-Admin -> `403`, Admin Tier 1 -> `200` + Che Email/Bí mật) trên Preview

| Vai Trò Phiên Kiểm Thử | Endpoint | Mã HTTP Thực Tế | Kết Quả Kiểm Chứng Bảo Mật |
| :--- | :--- | :-: | :--- |
| **Thành viên Gia đình (`Tier 2 MEMBER`)** | `GET /api/logs/dashboard` | **`403`** | `{"ok":false,"authenticated":true,"rbac_blocked":true,"tier":2,"role":"MEMBER",...}` |
| **Khách (`Tier 3 CHILD_GUEST`)** | `GET /api/logs/dashboard` | **`403`** | `{"ok":false,"authenticated":true,"rbac_blocked":true,"tier":3,"role":"CHILD_GUEST",...}` |
| **Chủ nhà (`Tier 1 ADMIN`)** | `GET /api/logs/dashboard` | **`200`** | `ok: true`, số email nguyên bản chưa che: **`0`**, định dạng email đã che: `['k***@gmail.com', 'n***@gmail.com', 's***@gmail.com', 't***@gmail.com']`, **`0`** mã OTP / mật khẩu / gợi ý mật khẩu lộ trong payload. |
