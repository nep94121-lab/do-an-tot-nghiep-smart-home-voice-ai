# BÁO CÁO XUẤT XƯỞNG PRODUCTION & KIỂM ĐỊNH KHOÁ CỔNG NHẬT KÝ / CSDL (`p8-logs-gate` -> `master`)

- **Worktree:** `C:\Users\LENOVO\datn-wt\logsgate`
- **Branch:** `p8-logs-gate` $\rightarrow$ Rebase lên `origin/master` (`7013d49`), Fast-Forward Merge vào `master` & đẩy lên `origin/master`
- **Production Alias URL:** `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`
- **Production Deployment URL:** `https://do-an-tot-nghiep-smart-home-voice-ei3wv495c.vercel.app` (`dpl_Cua7ejSjoUDLvZuxugScWDu1sMDY`)
- **Báo cáo khắc phục kỹ thuật trước đó:** [`FIX_REPORT_LOGSGATE.md`](file:///C:/Users/LENOVO/datn-wt/logsgate/FIX_REPORT_LOGSGATE.md)

---

## 1. Tự Vấn Thiết Kế (`/grill-me`), Mục Tiêu (`/goal`) & Phối Hợp Đội Ngũ (`/teamwork`)

1. **Tự vấn & Quyết định kỹ thuật (`/grill-me`):**
   - *Hỏi:* Làm thế nào để hợp nhất `p8-logs-gate` (`d7329d8`) vào `master` sau khi `p8-reject-tts` (`7013d49`) đã hạ cánh trên `origin/master`, đảm bảo giữ trọn vẹn cả cơ chế khóa cổng Admin Tier 1 + che email/OTP/password/hint của `p8-logs-gate` lẫn tính năng phát tiếng từ chối giọng nói của `p8-reject-tts`?
     - *Quyết định:* Xác nhận worktree tạm `C:\Users\LENOVO\lg_base` không còn tồn tại (`Test-Path False`), khôi phục các tệp dữ liệu runtime bị thay đổi khi chạy test (`reports/screenshots/*`, `simulator/data/*`, `specs/001-smart-home-voice-ai/tasks.md`), thực hiện `git fetch origin` và `git rebase origin/master` (`7013d49` $\rightarrow$ `c3b5716`) hoàn toàn sạch không xung đột, sau đó `git merge --ff-only p8-logs-gate` vào `master` mà không làm mất dữ liệu dở dang ở repo chính.
   - *Hỏi:* Làm thế nào để đẩy `master` lên GitHub và triển khai Vercel Production an toàn khi các tiến trình khác có thể chạy song song?
     - *Quyết định:* Sử dụng `schtasks /Create /SC ONCE /IT /RU LENOVO /F` và `schtasks /Run` để chạy `git push origin master:master` (normal push, tuyệt đối không dùng `--force`) trong phiên desktop tương tác có quyền truy cập Windows Credential Manager; đồng thời sử dụng cơ chế khóa [`C:\Users\LENOVO\datn-wt\deploy.lock`](file:///C:/Users/LENOVO/datn-wt/deploy.lock) bao quanh lệnh `vercel deploy --prod --yes`.
2. **Đội ngũ Subagent (`/teamwork` — `Gemini 4 Argon High`, `Model: "inherit"`):**
   - Subagent `cc523765-9905-407e-97d0-8ede3bfe8668` (*Security Ship Auditor*): Kiểm toán độc lập (Tier 2 Verify) toàn bộ 12 tệp trong commit của `p8-logs-gate` ([`simulator/api/routes_logs.py`](file:///C:/Users/LENOVO/datn-wt/logsgate/simulator/api/routes_logs.py), [`simulator/static/js/logs.js`](file:///C:/Users/LENOVO/datn-wt/logsgate/simulator/static/js/logs.js), [`simulator/static/js/auth_pages.js`](file:///C:/Users/LENOVO/datn-wt/logsgate/simulator/static/js/auth_pages.js), [`tests/test_p8_logsgate.py`](file:///C:/Users/LENOVO/datn-wt/logsgate/tests/test_p8_logsgate.py)), xác nhận 11/11 route paths bắt buộc `_require_admin_session(request)`, che email `n***@domain` + ẩn OTP/password/hint đầy đủ và đạt chuẩn `Zero-Leak` (`0` secret cứng, `0` CRLF).

---

## 2. Bằng Chứng Rebase, Fast-Forward Merge & Push Lên `origin/master`

### 2.1. Kiểm tra `C:\Users\LENOVO\lg_base` & Rebase lên `origin/master` (`7013d49`)
- Kiểm tra worktree cũ: `Test-Path "C:\Users\LENOVO\lg_base"` $\rightarrow$ `False` (đã được dọn sạch, không nằm trong `git worktree list`).
- Lệnh thực thi:
  ```text
  git fetch origin
  git rebase origin/master
  ```
- Kết quả Rebase:
  ```text
  Rebasing (1/1)
  Successfully rebased and updated refs/heads/p8-logs-gate.
  c3b5716 security(logs): gate all log/sqlite/devops endpoints to Admin Tier 1 and mask emails/secrets
  7013d49 docs(voice-tts): add SHIP_REPORT_REJTTS.md with prod verification and APK evidence
  c7f191a fix(voice-tts): import get_rejection_speech_text in routes_devices 401 reject paths
  73aad8a fix(voice-tts): make voice rejection replies audible on WebSocket, REST, and Android (p8-reject-tts)
  f61292c Merge origin/p7-guest into p7-guest-merge: Level 3 Guest QR page + Master Security Hardening
  ```

### 2.2. Fast-Forward Merge `p8-logs-gate` vào `master`
- Lệnh thực thi:
  ```text
  git -C "C:\Users\LENOVO\Desktop\đồ án tốt nghiệp" merge --ff-only p8-logs-gate
  ```
- Kết quả:
  ```text
  Updating 7013d49..c3b5716
  Fast-forward
   FIX_REPORT_LOGSGATE.md                     |  98 +++++++
   simulator/api/routes_logs.py               | 187 +++++++++++---
   simulator/static/js/auth_pages.js          |   5 +
   simulator/static/js/logs.js                |  75 +++++-
   tests/test_challenger_m1_2_adversarial.py  |   5 +-
   tests/test_challenger_m3_playwright_e2e.py |  13 +-
   tests/test_challenger_m4_orthogonal_sec.py |   2 +
   tests/test_challenger_m5_interactions.py   |   6 +-
   tests/test_challenger_m5_orthogonal.py     |   6 +-
   tests/test_m3_challenger_api.py            |  34 ++-
   tests/test_p4_survey1_security_auth.py     |  10 +-
   tests/test_p8_logsgate.py                  | 397 +++++++++++++++++++++++++++++
   12 files changed, 781 insertions(+), 57 deletions(-)
  ```

### 2.3. Push `master` qua Interactive Scheduled Task (`schtasks /IT /RU LENOVO`, Normal Push — Không Force)
- Lệnh thực thi:
  ```text
  schtasks /Create /TN "PushMasterLogsgate" /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File push_master_logsgate.ps1" /SC ONCE /ST 23:59 /IT /RU LENOVO /F
  schtasks /Run /TN "PushMasterLogsgate"
  ```
- Kết quả Push & Xác nhận `git ls-remote origin refs/heads/master`:
  ```text
  To https://github.com/nep94121-lab/do-an-tot-nghiep-smart-home-voice-ai.git
     7013d49..c3b5716  master -> master
  EXIT_CODE=0
  c3b571615a658b630c5fb5026ece8111494c0c3a	refs/heads/master
  ```

---

## 3. Tổng Hợp Kết Quả Kiểm Thử Pytest (Base `origin/master` vs. Sau Khi Hợp Nhất `p8-logs-gate`)

| Hạng Mục Kiểm Thử | Base `f61292c` | Sau Khi Hợp Nhất (`p8-logs-gate` `c3b5716`) | Chênh Lệch / Đánh Giá |
| :--- | :-: | :-: | :--- |
| **`python -m pytest tests/test_p8_logsgate.py -q`** | Chưa có (`48 failed, 1 passed` ở pha RED) | **`49 passed in 17.60s`** | **100% PASS (`Exit Code: 0`)** |
| **Bộ 6 file test bảo mật (`auth`, `logs`, `OTP`, `hint`, `RBAC`)** | `63 passed` | **`63 passed in 35.45s`** | **100% PASS (`Exit Code: 0`)** |
| **Tổ hợp `test_p8_logsgate.py` + `test_p8_reject_tts_tdd.py` + 6 file bảo mật sau Rebase** | — | **`117 passed in 173.92s`** | **100% PASS (tương thích hoàn toàn với `p8-reject-tts`)** |
| **Toàn bộ `python -m pytest tests -q`** | `1387 passed, 118 failed, 1 skipped, 5 errors` | **`1441 passed, 112 failed, 1 skipped, 5 errors`** | **`+54 passed`, `-6 failed`, `0 NEW failures`** |

*(Ghi chú: Các bài test `failed`/`errors` trong `pytest tests -q` đều là các bài kiểm thử E2E/Playwright pre-existing yêu cầu live server ngoài tại `http://127.0.0.1:8088` hoặc kiểm tra `<style>` inline cũ trên `origin/master`; không có bất kỳ lỗi mới nào phát sinh từ `p8-logs-gate`).*

---

## 4. Triển Khai Vercel Production (`deploy.lock`) & Kiểm Định Trực Tiếp (`curl` / `urllib`)

### 4.1. Bằng chứng triển khai `vercel deploy --prod --yes`
- **Khóa đồng bộ:** Tạo `C:\Users\LENOVO\datn-wt\deploy.lock` trước khi deploy và giải phóng ngay sau khi hoàn tất.
- **Deployment ID:** `dpl_Cua7ejSjoUDLvZuxugScWDu1sMDY`
- **Production Deployment URL:** `https://do-an-tot-nghiep-smart-home-voice-ei3wv495c.vercel.app`
- **Production Alias URL:** `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`
- **Trạng thái:** `READY` (`target: "production"`)

### 4.2. Bảng Mã Trạng Thái HTTP Thực Tế Trên Production (`https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`, Unauthenticated)

Kiểm chứng độc lập bằng cả `curl.exe -s -o NUL -w "%{http_code}"` và Python `urllib.request` trực tiếp tới `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`:

| STT | Nhóm Endpoint | Phương Thức & Đường Dẫn (`Path`) | Mã HTTP Kỳ Vọng | Mã HTTP Thực Tế (`curl`) | Phản Hồi Thực Tế Trên Production |
| :-: | :--- | :--- | :-: | :-: | :--- |
| 1 | **Cổng Nhật Ký / CSDL (Đã khóa Admin Tier 1)** | `GET /api/logs/dashboard` | `401` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| 2 | **Cổng Nhật Ký / CSDL (Đã khóa Admin Tier 1)** | `GET /api/server_logs_and_db` | `401` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| 3 | **Cổng Nhật Ký / CSDL (Đã khóa Admin Tier 1)** | `GET /api/sqlite/overview` | `401` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| 4 | **Cổng Nhật Ký / CSDL (Đã khóa Admin Tier 1)** | `GET /api/devops/status` | `401` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| 5 | **Cổng Nhật Ký / CSDL (Đã khóa Admin Tier 1)** | `POST /api/logs/sql_query` | `401` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| 6 | **Cổng Nhật Ký / CSDL (Đã khóa Admin Tier 1)** | `POST /api/sqlite/query` | `401` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| 7 | **Cổng Nhật Ký / CSDL (Đã khóa Admin Tier 1)** | `POST /api/logs/knowledge/add` | `401` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| 8 | **Cổng Nhật Ký / CSDL (Đã khóa Admin Tier 1)** | `POST /api/kb_upsert` | `401` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| 9 | **Cổng Nhật Ký / CSDL (Đã khóa Admin Tier 1)** | `POST /api/logs/append` | `401` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| 10 | **Cổng Nhật Ký / CSDL (Đã khóa Admin Tier 1)** | `POST /api/logs/clear` | `401` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| 11 | **Cổng Nhật Ký / CSDL (Đã khóa Admin Tier 1)** | `POST /api/clear_audit_logs` | `401` | **`401`** | `{"ok":false,"authenticated":false,"error":"Yêu cầu đăng nhập quyền Chủ nhà (Admin Cấp 1) để truy cập nhật ký và cơ sở dữ liệu hệ thống."}` |
| 12 | **Giao diện & Trạng thái Công khai** | `GET /` | `200` | **`200`** | Trang chủ Smart Home (`34,116 bytes`) hoạt động bình thường |
| 13 | **Giao diện & Trạng thái Công khai** | `GET /guest` | `200` | **`200`** | Trang Guest QR (`7,165 bytes`) hoạt động bình thường |
| 14 | **Giao diện & Trạng thái Công khai** | `GET /api/state` | `200` | **`200`** | JSON trạng thái nhà (`1,853 bytes`, chế độ công khai ẩn danh) hoạt động bình thường |
