# Báo Cáo Khảo Sát Yêu Cầu R1: Email Allowlist & Test Isolation

**Người thực hiện:** Explorer 1 (`survey_exp1` - `teamwork_explorer`)  
**Ngày thực hiện:** 05/11/2026  
**Workspace:** `C:\Users\LENOVO\datn-wt\p6-otp`  
**Chế độ:** Điều tra Độc lập Chỉ Đọc (Read-Only Investigation)  

---

## 1. Bản Đồ Điều Hướng & Điểm Phát Email Hiện Tại

Hệ thống phát tán email thực tế (qua SMTP hoặc CLI `gws`) tập trung tại tệp [invite_and_gmail_mixin.py](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth/invite_and_gmail_mixin.py) và được gọi qua các Router tại [routes_auth.py](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/api/routes_auth.py) và [routes_qr.py](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/api/routes_qr.py).

### 1.1. Các Hàm Chuyển Phát Email Cốt Lõi

| Hàm | Vị trí định nghĩa | Giao thức / Công cụ | Lỗ hổng / Bất cập quan sát được |
|---|---|---|---|
| `send_real_gmail_otp` | [invite_and_gmail_mixin.py:578-706](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth/invite_and_gmail_mixin.py#L578-L706) | `smtplib.SMTP`, `smtplib.SMTP_SSL` (cổng 587/465) fallback sang `gws gmail users messages send` | Chỉ lọc 4 hậu tố hardcoded (`.hust@gmail.com`, `.guest@gmail.com`, `.invite@gmail.com`, `.family@gmail.com`). Mọi email khác (kể cả email test ảo như `thanh_vien_chuan@gmail.com`, `hoc_sinh_moi@gmail.com`, `tan_binh_gia_dinh@gmail.com`) đều bị đẩy thẳng vào SMTP/gws thật, gây bounce mail hoặc spam ra bên ngoài. |
| `send_invite_link_via_gmail` | [invite_and_gmail_mixin.py:503-576](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth/invite_and_gmail_mixin.py#L503-L576) | `gws gmail users messages send` | Hoàn toàn **không kiểm tra allowlist**! Bất kỳ ai gọi route `/api/auth3/send_invite_email` với email bất kỳ đều kích hoạt lệnh `gws` gửi thư thật. |
| `read_latest_otp_from_gmail_inbox` | [invite_and_gmail_mixin.py:708-773](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth/invite_and_gmail_mixin.py#L708-L773) | `gws gmail users messages list/get` | Đọc thư từ hộp thư thật bằng query `"Smart Home Mã xác nhận OTP"`. |

### 1.2. Call Traces: Ai Gọi `send_real_gmail_otp`?

1. **`ThreeLayerAuthManager.layer1_login`** ([auth_3layer.py:391-393](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth_3layer.py#L391-L393)):
   ```python
   otp_code = f"{random.randint(100000, 999999)}"
   gmail_res = {"sent_real_gmail": False, "actual_recipient": "nep94121@gmail.com"}
   if send_gmail:
       gmail_res = self.send_real_gmail_otp(acc["email"], otp_code, acc["display_name"])
   ```
   *Lỗi kích hoạt:* Route `/api/auth3/layer1_login` ([routes_auth.py:534](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/api/routes_auth.py#L534)) thiết lập `send_gmail = bool(payload.get("send_gmail", True))` mặc định là `True`. Do đó nếu frontend hoặc test không gửi kèm `"send_gmail": false`, thư thật sẽ được kích hoạt gửi!

2. **`ThreeLayerAuthManager.request_password_reset_otp`** ([auth_3layer.py:559-560](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth_3layer.py#L559-L560)):
   ```python
   if send_gmail:
       gmail_res = self.send_real_gmail_otp(acc["email"], otp_code, acc["display_name"])
   ```
   Được gọi từ route `/api/auth3/forgot_password_send_otp` ([routes_auth.py:657](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/api/routes_auth.py#L657)).

3. **`AuthInviteGmailMixin.start_invite_oauth_registration`** ([invite_and_gmail_mixin.py:803-810](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth/invite_and_gmail_mixin.py#L803-L810)):
   ```python
   if send_gmail:
       gmail_res = self.send_real_gmail_otp(
           target_email=clean_email,
           otp_code=otp_code,
           display_name=name_clean,
           issued_password=issued_password,
           invite_info=inv,
       )
   ```
   Được gọi từ route `/api/auth3/invite_oauth_start` ([routes_auth.py:127-147](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/api/routes_auth.py#L127-L147)).

4. **`AuthQrTotpMixin.send_and_verify_email_otp`** ([qr_totp_mixin.py:260-265](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth/qr_totp_mixin.py#L260-L265)):
   ```python
   if send_gmail:
       gmail_res = self.send_real_gmail_otp(
           target_email=clean_email,
           otp_code=gen_otp,
           display_name="Khách Quét QR Cấp 3",
       )
   ```
   Được gọi từ route `/api/auth3/guest_qr_send_otp` ([routes_qr.py:421](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/api/routes_qr.py#L421)).

---

## 2. Thiết Kế Hệ Thống Bảo Vệ 3 Tầng (3-Tier Protection System)

Để bảo đảm thư thật 100% **CHỈ ĐƯỢC GỬI** tới các địa chỉ thuộc danh sách cho phép (`REAL_EMAIL_ALLOWLIST`), và tuyệt đối không bao giờ gửi ra các email test/ảo nhằm chống bounce và chống lộ lọt, hệ thống cần được kiến trúc thành 3 lớp phòng vệ độc lập:

```
┌────────────────────────────────────────────────────────────────────────┐
│  Tier 1: Canonical Allowlist Engine (Cấu hình & Nhận diện Hợp lệ)     │
│  - HARDCODED: nep94121@gmail.com, senat6031@gmail.com, kbanh376@gmail  │
│  - ENV OVERRIDE: os.environ.get("REAL_EMAIL_ALLOWLIST")               │
│  - is_real_email_allowed(email) -> True/False                          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Tier 2: Dispatch Gate & Non-Bounce Shield (Tại Dispatcher Backend)   │
│  - send_real_gmail_otp & send_invite_link_via_gmail                   │
│  - Nếu email KHÔNG thuộc Allowlist:                                   │
│    -> Chặn ngay trước khi mở kết nối SMTP / gws                      │
│    -> Trả về sent_real_gmail: False, blocked_by_allowlist: True        │
│    -> Không ném lỗi làm crash hệ thống, không gửi thư rác, 0 bounce   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Tier 3: Test & UI Isolation (Môi trường Kiểm thử & Giao diện)       │
│  - tests/conftest.py autouse fixture: mock triệt để smtplib & gws     │
│  - UI Gate (/): form gửi send_gmail: false mặc định                   │
│  - Playwright test flows: 100% chạy không phát sinh email thật        │
└────────────────────────────────────────────────────────────────────────┘
```

### Chi Tiết Cụ Thể Từng Tầng:

#### Tầng 1: Canonical Allowlist Engine
- Định nghĩa trong [constants_and_crypto.py](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth/constants_and_crypto.py):
  ```python
  HARDCODED_REAL_EMAIL_ALLOWLIST: frozenset[str] = frozenset({
      "nep94121@gmail.com",
      "senat6031@gmail.com",
      "kbanh376@gmail.com",
  })

  def get_real_email_allowlist() -> set[str]:
      allowlist = set(HARDCODED_REAL_EMAIL_ALLOWLIST)
      env_extra = os.environ.get("REAL_EMAIL_ALLOWLIST", "").strip()
      if env_extra:
          for raw_item in re.split(r"[,;:\s]+", env_extra):
              item = raw_item.strip().lower()
              if item and "@" in item:
                  allowlist.add(item)
      return allowlist

  def is_real_email_allowed(email: str) -> bool:
      clean = (email or "").strip().lower()
      return clean in get_real_email_allowlist()
  ```

#### Tầng 2: Dispatch Gate Chặn Chuyển Phát (Chống Bounce Mail)
- Trong `send_real_gmail_otp` ([invite_and_gmail_mixin.py:587](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth/invite_and_gmail_mixin.py#L587)):
  Thay thế đoạn logic cũ (chỉ kiểm tra đuôi `.hust@gmail.com`...):
  ```python
  recipient = (target_email or "").strip().lower()
  if not is_real_email_allowed(recipient):
      self._log_event(
          layer="Email Allowlist Protection Gate",
          action="blocked_non_allowlisted_email",
          email=recipient,
          status="BLOCKED",
          detail=f"Chặn gửi thư thật tới '{recipient}' vì không thuộc REAL_EMAIL_ALLOWLIST (Chống bounce mail).",
          source="EmailProtectionGate",
      )
      return {
          "sent_real_gmail": False,
          "blocked_by_allowlist": True,
          "actual_recipient": recipient,
          "status": "BLOCKED_NOT_ALLOWLISTED",
          "message": f"Địa chỉ '{recipient}' không thuộc danh sách REAL_EMAIL_ALLOWLIST. Chặn gửi an toàn.",
      }
  ```
- Trong `send_invite_link_via_gmail` ([invite_and_gmail_mixin.py:515](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth/invite_and_gmail_mixin.py#L515)):
  ```python
  to_addr = (recipient_email or "").strip().lower()
  if not is_real_email_allowed(to_addr):
      return {
          "ok": False,
          "blocked_by_allowlist": True,
          "recipient": to_addr,
          "error": f"Email '{to_addr}' không nằm trong REAL_EMAIL_ALLOWLIST!",
      }
  ```

#### Tầng 3: Test & UI Isolation
- Pytest: Không bao giờ chạm vào mạng hay SMTP ngoài.
- UI: Mọi luồng đăng nhập cổng vào (`/`) gửi `send_gmail: false`.

---

## 3. Khảo Sát `tests/conftest.py` & Thiết Kế `autouse` Fixture

### 3.1. Hiện Trạng Thư Mục `tests/`
- Hiện tại, file [tests/conftest.py](file:///C:/Users/LENOVO/datn-wt/p6-otp/tests/conftest.py) **hoàn toàn chưa tồn tại**! Chỉ có tệp [tests/e2e/conftest.py](file:///C:/Users/LENOVO/datn-wt/p6-otp/tests/e2e/conftest.py) dành riêng cho e2e.
- Do đó, khi chạy các bộ test độc lập như `pytest tests/test_*.py`, không có fixture gốc nào bảo vệ ngăn chặn việc gọi `smtplib` hay `subprocess.run(gws...)`.
- Một số test hiện tại phải tự dùng `unittest.mock.patch` cục bộ (ví dụ: `tests/test_phase5_r3_otp_email.py`). Nếu ai đó viết test mới quên patch, thư thật sẽ bị gửi đi ngay lập tức!

### 3.2. Thiết Kế `tests/conftest.py` Hoàn Chỉnh

Cần tạo mới file `tests/conftest.py` với fixture `autouse=True`:

```python
"""Root pytest conftest: Test Isolation & Mocking for Smart Home Voice AI."""
from __future__ import annotations

import json
import os
import smtplib
import subprocess
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def isolate_email_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tự động kích hoạt trên 100% test case:
    1. Mock smtplib.SMTP và smtplib.SMTP_SSL ngăn không cho kết nối SMTP thật.
    2. Mock subprocess.run đối với các lệnh 'gws' CLI.
    3. Bảo đảm tính tương thích với các bài test dùng patch cục bộ.
    """
    # 1. Mock SMTP Client
    mock_smtp_inst = MagicMock()
    mock_smtp_inst.__enter__.return_value = mock_smtp_inst
    mock_smtp_inst.send_message.return_value = {}
    mock_smtp_inst.sendmail.return_value = {}
    mock_smtp_inst.login.return_value = (235, b"2.7.0 Authentication successful")
    mock_smtp_inst.starttls.return_value = (220, b"2.0.0 Ready to start TLS")

    monkeypatch.setattr(smtplib, "SMTP", MagicMock(return_value=mock_smtp_inst))
    monkeypatch.setattr(smtplib, "SMTP_SSL", MagicMock(return_value=mock_smtp_inst))

    # 2. Mock subprocess.run for gws CLI
    orig_subprocess_run = subprocess.run

    def safe_subprocess_run(cmd: Any, *args: Any, **kwargs: Any) -> Any:
        cmd_str = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "gws" in cmd_str:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            if "messages" in cmd_str and "send" in cmd_str:
                mock_proc.stdout = json.dumps({"id": "mock_gws_msg_test_isolation_id", "threadId": "mock_thread_id"})
                mock_proc.stderr = ""
            elif "messages" in cmd_str and "list" in cmd_str:
                mock_proc.stdout = json.dumps({"messages": [{"id": "mock_gws_msg_test_isolation_id"}]})
                mock_proc.stderr = ""
            elif "messages" in cmd_str and "get" in cmd_str:
                mock_proc.stdout = json.dumps({
                    "id": "mock_gws_msg_test_isolation_id",
                    "snippet": "Mã xác nhận OTP: 654321",
                    "payload": {"headers": [{"name": "Subject", "value": "Mã xác nhận OTP"}]},
                })
                mock_proc.stderr = ""
            else:
                mock_proc.stdout = "{}"
                mock_proc.stderr = ""
            return mock_proc
        return orig_subprocess_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", safe_subprocess_run)
```

**Tính tương thích kiểm chứng:**
- Khi một test dùng `with patch("smtplib.SMTP", return_value=mock_custom):`, context manager của `patch` sẽ ghi đè lên monkeypatch của conftest trong phạm vi khối `with`, bảo đảm các bài test kiểm tra hành vi SMTP (như `test_r3_successful_smtp_dispatch_when_secret_provided`) vẫn chạy chuẩn xác 100%.

---

## 4. Khảo Sát Cổng Đăng Nhập Trang Chủ (`/`) & Luồng Playwright 3 Roles

### 4.1. Hiện Trạng Cổng Đăng Nhập (`/`)
- Giao diện HTML: [simulator/static/index.html:277-312](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/static/index.html#L277-L312) chứa modal `#homeLoginGateModal`, form `#gatePanelLogin`, nút `#btnSubmitGateLogin`.
- Bộ điều khiển JavaScript: [simulator/static/js/app.js:1739-1781](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/static/js/app.js#L1739-L1781):
  ```javascript
  const btnSubmitGateLogin = byId("btnSubmitGateLogin");
  if (btnSubmitGateLogin) {
    btnSubmitGateLogin.addEventListener("click", async () => {
      // ...
      const res = await fetch("/api/auth3/layer1_login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, login_method: "password", method: "password" }),
      });
  ```
  **Điểm thiếu hụt:** `body` của request **hoàn toàn không truyền tham số `send_gmail: false`**!
  Do backend [routes_auth.py:534](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/api/routes_auth.py#L534) mặc định `send_gmail = bool(payload.get("send_gmail", True))`, mọi lượt bấm nút đăng nhập tại Cổng Vào trên Trang Chủ đều kích hoạt việc gửi mã OTP về Gmail thật!

- Ngoài ra trong [simulator/static/js/auth.js:685](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/static/js/auth.js#L685) hàm `submitLayer1`:
  ```javascript
  const res = await fetch('/api/auth3/layer1_login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, login_method: loginMethod, method: loginMethod, google_id_token: 'GOOGLE_OAUTH_SIM_TOKEN_OK' })
  });
  ```
  Cũng chưa thiết lập `send_gmail: false`.

### 4.2. Luồng Kiểm Thử Playwright 3 Roles
- File: [tests/test_playwright_3roles_live.py](file:///C:/Users/LENOVO/datn-wt/p6-otp/tests/test_playwright_3roles_live.py):
  - `test_live_desktop_owner_tier1_flow` (dòng 38-41): Điền `nep94121@gmail.com` -> click `#btnSubmitGateLogin`.
  - `test_live_desktop_family_tier2_flow` (dòng 80-83): Điền `senat6031@gmail.com` -> click `#btnSubmitGateLogin`.
  - `test_live_desktop_guest_tier3_flow` (dòng 122-125): Điền `kbanh376@gmail.com` -> click `#btnSubmitGateLogin`.
- Cả 3 luồng này đều tương tác trực tiếp với `#btnSubmitGateLogin` trên trình duyệt thật Chromium.
- Vì `#btnSubmitGateLogin` chưa gửi `send_gmail: false`, mỗi lần chạy test Playwright, hệ thống backend đều gọi `send_real_gmail_otp()` cho cả 3 email trên! Nếu có cấu hình `GMAIL_APP_PASSWORD` hoặc CLI `gws`, 3 lá thư OTP thật sẽ bị gửi đi trong mỗi lần test!

### 4.3. Giải Pháp Khắc Phục Cụ Thể
1. Tại [simulator/static/js/app.js:1755](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/static/js/app.js#L1755), sửa payload gửi đi:
   ```javascript
   body: JSON.stringify({
     email,
     password,
     login_method: "password",
     method: "password",
     send_gmail: false,
   }),
   ```
2. Tại [simulator/static/js/auth.js:685](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/static/js/auth.js#L685), bổ sung `send_gmail: false`.
3. Kiểm tra các modal khác trong `app.js` (như `SecurityLockdownModal` tại dòng 2086) để đảm bảo đồng nhất `send_gmail: false` khi chỉ xác thực mật khẩu.

---

## 5. Kiểm Tra Tệp Dữ Liệu `accounts_3layer.json` & `family_email_allowlist.json`

### 5.1. Hiện Trạng Bị Ô Nhiễm Dữ Liệu (Data Pollution)

#### Tệp [simulator/data/accounts_3layer.json](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/data/accounts_3layer.json) (752 dòng):
Chứa tổng cộng **18 tài khoản**, trong đó:
- **6 tài khoản mặc định chuẩn (Clean Seed Accounts):**
  1. `tuan_anh` (`nep94121@gmail.com`, Tier 1 - Chủ nhà Toàn quyền)
  2. `thanh_vien_a` (`thanhviena.hust@gmail.com`, Tier 2 - Thành viên)
  3. `thanh_vien_b` (`thanhvienb.hust@gmail.com`, Tier 2 - Thành viên)
  4. `khach_c` (`khachc.guest@gmail.com`, Tier 3 - Khách)
  5. `senat6031` (`senat6031@gmail.com`, Tier 2 - Gia đình)
  6. `kbanh376` (`kbanh376@gmail.com`, Tier 3 - Khách)
- **12 tài khoản rác bị ghi đè sau các lượt chạy test:**
  `thanhvien_test_c2`, `khach_test_c3`, `khach_tu_c2`, `con_yeu_e2e_test`, `con_yeu_family`, `emgai_invite`, `member_m5_test`, `hacker_trying_duplicate`, `thành_viên_mới`, `alias_auth1`, `alias_auth2`, `api_test_member`.

#### Tệp [simulator/data/family_email_allowlist.json](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/data/family_email_allowlist.json) (93 dòng):
Chứa **10 bản ghi email test rác** sinh ra từ các bài kiểm thử:
- `thanhvien_test_c2@gmail.com`
- `khach_test_c3@gmail.com`
- `khach_tu_c2@gmail.com`
- `con_yeu_e2e_test@gmail.com`
- `con_yeu_family@gmail.com`
- `member_m5_test@gmail.com`
- `hacker_trying_duplicate@gmail.com`
- `alias_auth1@gmail.com`
- `alias_auth2@gmail.com`
- `api_test_member@gmail.com`

### 5.2. Nguyên Nhân Gây Ô Nhiễm
Khi chạy các bài test gọi trực tiếp hàm `ThreeLayerAuthManager.add_family_email` hoặc `ThreeLayerAuthManager.layer1_login` mà không cô lập đường dẫn qua `monkeypatch` hoặc thư mục tạm, hàm `_save_accounts()` và `_save_family_allowlist()` đã ghi thẳng đè vào hai tệp dữ liệu trên đĩa gốc.

### 5.3. Khuyến Nghị Làm Sạch (Actionable Recommendation)
1. **Làm sạch `simulator/data/accounts_3layer.json`**:
   Chỉ giữ lại đúng 6 tài khoản mặc định chuẩn (trích xuất đồng bộ với `DEFAULT_ACCOUNTS` trong [constants_and_crypto.py:50-248](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth/constants_and_crypto.py#L50-L248)).
2. **Làm sạch `simulator/data/family_email_allowlist.json`**:
   Đặt lại về dictionary rỗng `{}`.
3. **Bảo vệ chống tái ô nhiễm**:
   Trong `tests/conftest.py`, thêm fixture quản lý dữ liệu (autouse hoặc scoped) để sao lưu và khôi phục (backup/restore) nội dung của hai file dữ liệu này sau mỗi phiên chạy pytest, hoặc điều hướng ghi tạm sang `tmp_path`.

---

## 6. Bảng Kế Hoạch Thực Hiện Cho Coder / Implementer

| Hạng mục | Tệp mục tiêu | Hành động đề xuất |
|---|---|---|
| **1. Allowlist Engine** | `simulator/auth/constants_and_crypto.py` | Thêm `HARDCODED_REAL_EMAIL_ALLOWLIST`, `get_real_email_allowlist()`, `is_real_email_allowed()` |
| **2. Dispatcher Gate** | `simulator/auth/invite_and_gmail_mixin.py` | Trong `send_real_gmail_otp` và `send_invite_link_via_gmail`, chặn ngay nếu `not is_real_email_allowed(email)`, trả về `sent_real_gmail: False, blocked_by_allowlist: True` |
| **3. Test Isolation Fixture** | `tests/conftest.py` (tạo mới) | Viết fixture `autouse=True` mock `smtplib.SMTP`, `smtplib.SMTP_SSL` và `subprocess.run(gws...)` |
| **4. Login Gate UI** | `simulator/static/js/app.js` | Thêm `"send_gmail": false` vào payload của `btnSubmitGateLogin` |
| **5. Auth Studio UI** | `simulator/static/js/auth.js` | Thêm `"send_gmail": false` vào payload của `submitLayer1` |
| **6. Data Cleanup** | `simulator/data/accounts_3layer.json` | Cắt bỏ 12 tài khoản test rác, giữ đúng 6 tài khoản mặc định |
| **7. Data Cleanup** | `simulator/data/family_email_allowlist.json` | Đưa về `{}` |

---
*Báo cáo được lập đầy đủ căn cứ mã nguồn, số dòng, và chuỗi logic phục vụ bàn giao sang nhóm thực thi.*
