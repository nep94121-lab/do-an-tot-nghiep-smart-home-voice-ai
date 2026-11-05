# Báo Cáo Khảo Sát Kiến Trúc: Yêu Cầu R2 (Anti-Double-Send Cooldown & Trigger Fixes)

**Tác giả:** Explorer 2 (`survey_exp2` / `teamwork_explorer`)  
**Ngày báo cáo:** 2026-11-05  
**Phạm vi:** Điều tra và thiết kế giải pháp cho Yêu cầu R2 (Cooldown 60s gửi OTP, chống gửi lặp, sửa lỗi kích hoạt kép frontend, và quản lý trạng thái inFlight/disabled cho nút bấm).  
**Dự án:** Smart Home Voice AI (`p6-otp`)  

---

## 1. Tóm Tắt Cốt Lõi (Executive Summary)

1. **Backend OTP Dispatch & Thiếu Cơ Chế Cooldown:**
   - Trong `simulator/auth_3layer.py` (`request_password_reset_otp`, dòng 545–615), mỗi lần API `/api/auth3/forgot_password_send_otp` được gọi, hàm này **vô điều kiện tạo mã OTP 6 số ngẫu nhiên mới** (`f"{random.randint(100000, 999999)}"`), gọi `self.send_real_gmail_otp(...)` để chuyển phát email thật (SMTP/gws) và **ghi đè hoàn toàn** vào `self.pending_otps[email.lower()]`.
   - Nếu người dùng hoặc client gửi 2 yêu cầu trong vòng 60 giây (hoặc nhấp đúp liên tiếp trong 200ms), máy chủ sẽ gửi 2 email với 2 mã OTP khác nhau; mã OTP trước bị vô hiệu hóa ngay lập tức khiến người dùng nhập mã vừa nhận bị báo sai.
   - Chưa có bộ khóa luồng (`threading.Lock`), dẫn tới nguy cơ race condition khi nhiều worker/thread xử lý song song.
   - Chưa có cơ chế tiêu hủy OTP (`consume / pop`) sau khi người dùng đặt lại mật khẩu thành công ở `reset_password_with_otp`, tiềm ẩn rủi ro replay mã cũ trong thời hạn 300s.

2. **Frontend Kích Hoạt Kép (Double-Firing Triggers):**
   - Tại `simulator/static/index.html` (dòng 296, 308) và `simulator/static/js/app.js` (dòng 1711–1715, 1740–1782):
     `<button type="submit" id="btnSubmitGateLogin">` nằm trong `<form id="gatePanelLogin">`.
     - `app.js:1741` gắn sự kiện `btnSubmitGateLogin.addEventListener("click", async () => { ... })` thực hiện `fetch("/api/auth3/layer1_login")`.
     - `app.js:1712` lại gắn thêm sự kiện `gatePanelLogin.addEventListener("submit", (e) => { e.preventDefault(); if (btnSubmitGateLogin) btnSubmitGateLogin.click(); })`.
     - **Cơ chế xung đột:** Khi người dùng bấm nút `#btnSubmitGateLogin`, trình duyệt kích hoạt sự kiện `click` của nút trước (gửi request lần 1), sau đó trình duyệt kích hoạt sự kiện `submit` của form, và sự kiện submit lại gọi `btnSubmitGateLogin.click()`, kích hoạt lại listener `click` lần 2 (gửi request lần 2). **Kết quả: 2 network request được gửi song song cho 1 lần bấm!**
     - Hiện tượng tương tự xảy ra 100% với:
       * Form Đặt/Đổi mật khẩu: `gatePanelRegister` (`app.js:1717-1721`) + `btnSubmitGateRegister` (`app.js:1785-1840`).
       * Form Quên mật khẩu: `gatePanelForgot` (`app.js:1723-1727`) + `btnSubmitForgotReset` (`app.js:1893-1941`).
       * Modal Khóa an ninh: `index.html:422, 442` vừa có `onsubmit="event.preventDefault(); window.unlockSecurityLockdown();"` trên form vừa có `onclick="window.unlockSecurityLockdown()"` trên `<button type="submit">`.

3. **Thiếu Trạng Thái inFlight / Disabled Cho Nút Bấm:**
   - Trong `simulator/static/js/app.js`: Cả 3 nút submit (`#btnSubmitGateLogin`, `#btnSubmitGateRegister`, `#btnSubmitForgotReset`) và nút gửi mã OTP (`#btnSendForgotOtp`) **đều không hề thiết lập thuộc tính `disabled = true`** hay cờ `inFlight` trong suốt quá trình chờ fetch.
   - Khi mạng trễ 1–3 giây, người dùng nhấp nhiều lần sẽ gửi hàng loạt request lên server.
   - Nút `#btnSendForgotOtp` sau khi gửi thành công không có bộ đếm ngược 60 giây (cooldown countdown timer) như màn hình mobile (`mobile_app.js:480-496`).

---

## 2. Chi Tiết Khảo Sát Backend & Thiết Kế Cooldown 60 Giây

### 2.1. Phân Tích Call Trace Hiện Tại

```
Client (Web / Mobile / API)
   │
   ▼
[POST /api/auth3/forgot_password_send_otp] (simulator/api/routes_auth.py:653-664)
   │
   ▼
get_auth_3layer_manager().request_password_reset_otp(email, send_gmail, source) (simulator/auth_3layer.py:545-615)
   │
   ├── 1. clean_email = email.strip().lower()
   ├── 2. acc = self.find_account(clean_email)
   ├── 3. otp_code = f"{random.randint(100000, 999999)}"  <-- ⚠️ Luôn tạo mã mới
   ├── 4. if send_gmail: self.send_real_gmail_otp(...)     <-- ⚠️ Luôn gửi mail thật (SMTP/gws)
   └── 5. self.pending_otps[clean_email] = { ... }        <-- ⚠️ Luôn ghi đè, vô hiệu hóa mã cũ
```

### 2.2. Thiết Kế Cơ Chế Cooldown 60s & Idempotency

#### A. Nguyên Tắc Hoạt Động (Idempotent Cooldown Rule)
- Khi một email yêu cầu OTP:
  1. Kiểm tra xem trong `self.pending_otps` đã có bản ghi của email đó chưa.
  2. Nếu **đã có** bản ghi, bản ghi chưa hết hạn (`time.time() < existing["expires_at"]`), và chưa bị tiêu hủy (`consumed != True`):
     - Tính thời gian trôi qua kể từ lần gửi trước: `elapsed = time.time() - existing["created_at"]`.
     - Nếu `elapsed < 60.0`:
       * **KÍCH HOẠT COOLDOWN.**
       * **KHÔNG** tạo mã OTP mới.
       * **KHÔNG** gọi `send_real_gmail_otp` (không gọi SMTP hay CLI `gws`).
       * **KHÔNG** ghi đè `self.pending_otps`.
       * **BẢO TOÀN NGUYÊN VẸN** mã OTP đang có hiệu lực (`existing["otp_code"]`).
       * Trả về kết quả **Idempotent** với HTTP 200:
         ```python
         remaining_sec = int(math.ceil(60.0 - elapsed))
         return {
             "ok": True,
             "email": acc["email"],
             "display_name": acc["display_name"],
             "idempotent": True,
             "cooldown_active": True,
             "cooldown_remaining_seconds": remaining_sec,
             "gmail_delivery": existing.get("gmail_delivery", {}),
             "message": f"Mã xác nhận OTP đã được gửi trước đó. Vui lòng kiểm tra hộp thư hoặc chờ {remaining_sec} giây trước khi gửi lại.",
             # Nếu send_gmail == False (chế độ kiểm thử/demo):
             "demo_otp_preview": existing["otp_code"],
             "otp_code_for_test": existing["otp_code"],
         }
         ```
  3. Nếu `elapsed >= 60.0` (hoặc chưa có bản ghi, hoặc bản ghi cũ đã hết hạn >300s):
     - Cooldown đã hết, cho phép tạo OTP mới và phát email mới bình thường.
     - Cập nhật lại `created_at = time.time()` và `expires_at = time.time() + 300`.

#### B. Phân Tích An Toàn Đa Luồng (Thread-Safety)
- **Môi trường vận hành:** FastAPI / Starlette với Uvicorn. Mặc dù `api_auth3_forgot_password_send_otp` là hàm `async def`, nhưng bên trong nó gọi hàm đồng bộ `ThreeLayerAuthManager.request_password_reset_otp()`.
- Nếu Uvicorn chạy đa luồng hoặc nếu các tác vụ I/O blocking (như `smtplib.SMTP.connect()` mất 500ms–2s) giải phóng GIL hoặc chạy qua thread pool, 2 request đồng thời có thể cùng lúc thấy `existing` chưa tồn tại và cùng sinh 2 mã OTP.
- **Giải pháp:**
  - Khởi tạo `self._otp_lock = threading.Lock()` trong `ThreeLayerAuthManager.__init__()`.
  - Khối kiểm tra cooldown, sinh mã OTP, và cập nhật dictionary `self.pending_otps` được bọc trong ngữ cảnh `with self._otp_lock:`.
  - Để tránh giữ lock quá lâu trong lúc kết nối mạng SMTP (có thể mất 1–5s), sử dụng mô hình 2 pha:
    1. Pha 1 (Atomic Check & Claim): Dưới `_otp_lock`, kiểm tra cooldown. Nếu đang trong cooldown -> trả về ngay. Nếu không, đặt cờ `dispatching = True`, lưu tạm timestamp và mã OTP.
    2. Pha 2 (I/O Dispatch): Gửi email (ngoài lock).
    3. Pha 3 (Atomic Commit): Dưới `_otp_lock`, cập nhật kết quả `gmail_delivery` vào `self.pending_otps`.
  - Đối với cấu trúc đơn giản hiện tại, việc giữ lock ngắn hoặc kiểm tra nguyên tử đảm bảo 100% không bao giờ xảy ra tình trạng 2 thread cùng gửi mail cho 1 địa chỉ.

#### C. Lưu Trữ Bộ Nhớ (In-Memory) vs Bền Vững (Persistence)
- Mã OTP có tuổi thọ rất ngắn (300 giây = 5 phút).
- Việc lưu trữ trong `self.pending_otps` (In-memory dict) của singleton `ThreeLayerAuthManager` là giải pháp tối ưu:
  - Tốc độ truy xuất vi giây ($O(1)$).
  - Không gây I/O disk rác (zero-disk-wear).
  - Tự động giải phóng khi phiên kết thúc hoặc server restart.
- Khi cần ghi nhận kiểm toán (audit log), hệ thống đã có sẵn `self._log_event` ghi vào `auth_3layer_events.json` khi có sự kiện `forgot_password_otp_sent` hoặc `forgot_password_otp_throttled`.

#### D. Tương Tác Với Xác Minh Đặt Lại Mật Khẩu (Reset Verification & Consumption)
- Trong `simulator/auth_3layer.py`:
  ```python
  def reset_password_with_otp(self, email, otp_code, new_password, confirm_password, source="Web Quên Mật Khẩu"):
      clean_email = str(email or "").strip().lower()
      ...
      otp_res = self.layer2_verify_otp(clean_email, otp_code, source=source)
      if not otp_res.get("ok"):
          return otp_res

      res = self.register_or_update_password(
          email=clean_email,
          password=pw1,
          confirm_password=pw2,
          source=source,
      )
      if res.get("ok"):
          # 🔒 TIÊU HỦY OTP (SINGLE-USE / ANTI-REPLAY)
          with self._otp_lock:
              self.pending_otps.pop(clean_email, None)
      return res
  ```
- **Ý nghĩa:**
  1. Ngăn chặn tấn công phát lại (Replay Attack): Sau khi mật khẩu đã đổi thành công, mã OTP đó lập tức bị hủy, không thể sử dụng lại trong 5 phút còn lại.
  2. Xóa trạng thái để nếu sau này người dùng cần reset lại, hệ thống không bị vướng trạng thái cũ.

#### E. Mở Rộng Cooldown Cho Các Endpoint Khác
- Endpoint Guest QR OTP (`/api/auth3/guest_qr_send_otp` trong `simulator/api/routes_qr.py:410-425`):
  Áp dụng cùng cơ chế cooldown 60s trên `mgr3.pending_guest_email_otps[clean_email]`. Khi khách bấm quét/gửi lại nhiều lần trong 60s, hệ thống giữ nguyên mã `otp_code` cũ và trả về `idempotent: True`.

---

## 3. Khảo Sát Chi Tiết Frontend: Sự Cố Kích Hoạt Kép (Double-Firing)

### 3.1. Vị Trí Mã Nguồn Gây Xung Đột

#### 1. Form Đăng Nhập Trang Chủ (`#gatePanelLogin`)
- **Tệp HTML:** `simulator/static/index.html`
  - Dòng 296: `<form id="gatePanelLogin" style="display:grid; gap:10px;" onsubmit="event.preventDefault();">`
  - Dòng 308–310:
    ```html
    <button type="submit" id="btnSubmitGateLogin" class="btn btn-primary" style="width:100%;">
      Đăng nhập vào Nhà thông minh
    </button>
    ```
- **Tệp JS:** `simulator/static/js/app.js`
  - Dòng 1711–1716:
    ```javascript
    if (gatePanelLogin) {
      gatePanelLogin.addEventListener("submit", (e) => {
        e.preventDefault();
        if (btnSubmitGateLogin) btnSubmitGateLogin.click(); // <-- 💣 GÂY KÍCH HOẠT KÉP
      });
    }
    ```
  - Dòng 1740–1782:
    ```javascript
    const btnSubmitGateLogin = byId("btnSubmitGateLogin");
    if (btnSubmitGateLogin) {
      btnSubmitGateLogin.addEventListener("click", async () => {
        // ... thực hiện fetch("/api/auth3/layer1_login", ...)
      });
    }
    ```

#### 2. Form Đặt/Đổi Mật Khẩu (`#gatePanelRegister`)
- **Tệp HTML:** `simulator/static/index.html:314, 345–347`
  - Form có nút `<button type="submit" id="btnSubmitGateRegister">`.
- **Tệp JS:** `simulator/static/js/app.js`
  - Dòng 1717–1722:
    ```javascript
    if (gatePanelRegister) {
      gatePanelRegister.addEventListener("submit", (e) => {
        e.preventDefault();
        if (btnSubmitGateRegister) btnSubmitGateRegister.click(); // <-- 💣 GÂY KÍCH HOẠT KÉP
      });
    }
    ```
  - Dòng 1785–1841: `btnSubmitGateRegister.addEventListener("click", async () => { ... })`.

#### 3. Form Quên Mật Khẩu Bước 3 (`#gatePanelForgot`)
- **Tệp HTML:** `simulator/static/index.html:351, 394–396`
  - Form có nút `<button type="submit" id="btnSubmitForgotReset">`.
- **Tệp JS:** `simulator/static/js/app.js`
  - Dòng 1723–1728:
    ```javascript
    if (gatePanelForgot) {
      gatePanelForgot.addEventListener("submit", (e) => {
        e.preventDefault();
        if (btnSubmitForgotReset) btnSubmitForgotReset.click(); // <-- 💣 GÂY KÍCH HOẠT KÉP
      });
    }
    ```
  - Dòng 1893–1941: `btnSubmitForgotReset.addEventListener("click", async () => { ... })`.

#### 4. Form Mở Khóa An Ninh (`#lockdownForm`)
- **Tệp HTML:** `simulator/static/index.html`
  - Dòng 422: `<form id="lockdownForm" onsubmit="event.preventDefault(); window.unlockSecurityLockdown();" ...>`
  - Dòng 442: `<button type="submit" id="btnLockdownUnlock" onclick="window.unlockSecurityLockdown()" ...>`
  - Cả `onsubmit` của form và `onclick` của nút submit đều gọi `window.unlockSecurityLockdown()`.

### 3.2. Cơ Chế Chuỗi Sự Kiện DOM Gây Ra Lỗi (Event Propagation Sequence)

Khi người dùng nhấn chuột vào nút submit `<button type="submit" id="btnSubmitGateLogin">`:
1. **T0 ms:** Chuột nhả trên button -> Trình duyệt phát sinh sự kiện `click` trên phần tử `#btnSubmitGateLogin`.
2. **T+1 ms:** Listener `btnSubmitGateLogin.addEventListener("click", ...)` bắt được sự kiện -> Đọc email/password -> Bắt đầu gọi `fetch("/api/auth3/layer1_login")` **(Request #1 được gửi đi)**.
3. **T+2 ms:** Theo chuẩn W3C HTML5 Form Submission, khi một phần tử `<button type="submit">` nhận sự kiện click thành công, form chứa nó (`#gatePanelLogin`) lập tức phát sinh sự kiện `submit`.
4. **T+3 ms:** Listener `gatePanelLogin.addEventListener("submit", ...)` bắt được sự kiện submit -> Gọi `e.preventDefault()`, sau đó thực thi dòng lệnh:
   `btnSubmitGateLogin.click();`
5. **T+4 ms:** Phương thức DOM `.click()` được gọi theo chương trình (programmatic click) -> Trình duyệt phát sinh tiếp một sự kiện `click` mới trên `#btnSubmitGateLogin`!
6. **T+5 ms:** Listener `btnSubmitGateLogin.addEventListener("click", ...)` lại được gọi lần thứ 2 -> Bắt đầu gọi `fetch("/api/auth3/layer1_login")` **(Request #2 được gửi đi song song)**.
7. **Hậu quả:** 2 request giống hệt nhau cùng bay lên server trong vòng vài mili-giây! Nếu là request gửi OTP, server sẽ nhận 2 lệnh liên tiếp và gửi 2 email. Nếu là request đăng nhập, cả 2 cùng ghi session và kiểm tra database trùng lặp.

### 3.3. Giải Pháp Triệt Để Loại Bỏ Kích Hoạt Kép

**Nguyên tắc chuẩn HTML5:** Không gắn logic vào `button.click` rồi để `form.submit` gọi lại `button.click()`.
Thay vào đó, **chỉ gắn 1 listener duy nhất vào sự kiện `submit` của thẻ `<form>`** (hoặc chuyển button thành `type="button"`).

Mô hình chuẩn:
```javascript
// ✅ CHUẨN DUY NHẤT: Bắt sự kiện submit của Form
if (gatePanelLogin) {
  gatePanelLogin.addEventListener("submit", async (e) => {
    e.preventDefault();
    await handleGateLoginSubmit();
  });
}
// KHÔNG gọi btnSubmitGateLogin.click() trong submit!
// Nút <button type="submit"> trong form khi được bấm sẽ tự động trigger form submit 1 lần duy nhất!
// Người dùng bấm Enter trong ô input cũng trigger form submit 1 lần duy nhất!
```

---

## 4. Thiết Kế Quản Lý Trạng Thái Nút Bấm (inFlight & Disabled State)

### 4.1. Trạng Thái inFlight Cho Các Nút Đăng Nhập & Gửi OTP

Mỗi hành động mạng bất đồng bộ cần tuân thủ máy trạng thái sau:

```
[IDLE] (Button enabled, Text gốc)
   │
   ▼ Người dùng bấm / Form submit
[IN_FLIGHT] 
   - Kiểm tra cờ isInFlight: Nếu true -> return ngay lập tức (chặn click liên tiếp)
   - Đặt isInFlight = true
   - btn.disabled = true
   - btn.setAttribute("aria-busy", "true")
   - Lưu text gốc vào dataset: btn.dataset.origText = btn.innerHTML
   - Hiển thị spinner/text đang tải: btn.innerHTML = "⏳ Đang xử lý..."
   │
   ▼ (Trong khối try ... catch ... finally)
[COMPLETED / ERROR]
   - Trong finally:
     * isInFlight = false
     * btn.removeAttribute("aria-busy")
     * Nếu là nút đăng nhập / thao tác xong -> btn.disabled = false, khôi phục text gốc.
     * Nếu là nút gửi OTP thành công -> Chuyển sang trạng thái [COOLDOWN_COUNTDOWN].
```

### 4.2. Bộ Đếm Ngược 60s Cho Nút Gửi OTP (`#btnSendForgotOtp`)

Khi gửi mã OTP thành công, nút gửi mã cần bị khóa trong đúng 60 giây (hoặc số giây `cooldown_remaining_seconds` do backend trả về) kèm hiển thị đếm ngược trực quan:

```javascript
let forgotOtpCooldownInterval = null;

function startForgotOtpCooldown(seconds = 60) {
  const btn = document.getElementById("btnSendForgotOtp");
  if (!btn) return;
  if (forgotOtpCooldownInterval) clearInterval(forgotOtpCooldownInterval);

  let remaining = seconds;
  btn.disabled = true;
  btn.textContent = `Gửi lại sau (${remaining}s)`;

  forgotOtpCooldownInterval = setInterval(() => {
    remaining--;
    if (remaining <= 0) {
      clearInterval(forgotOtpCooldownInterval);
      forgotOtpCooldownInterval = null;
      btn.disabled = false;
      btn.textContent = "Gửi mã OTP";
    } else {
      btn.textContent = `Gửi lại sau (${remaining}s)`;
    }
  }, 1000);
}
```

---

## 5. Đề Xuất Mã Nguồn Cụ Thể (Implementation Recipes)

Dành cho Implementer agent thực hiện tại Milestone 2:

### Recipe 1: Cập Nhật `simulator/auth_3layer.py`
Thêm `threading.Lock()` và kiểm tra cooldown trong `request_password_reset_otp`, tiêu hủy mã trong `reset_password_with_otp`:

```python
# Trong ThreeLayerAuthManager.__init__:
import math
import threading

self._otp_lock = threading.Lock()

# Trong request_password_reset_otp (lines 545-615):
def request_password_reset_otp(
    self,
    email: str,
    send_gmail: bool = True,
    source: str = "Web Quên Mật Khẩu",
) -> dict[str, Any]:
    clean_email = str(email or "").strip().lower()
    acc = self.find_account(clean_email)
    if not acc:
        return {"ok": False, "status_code": 404, "error": f"Không tìm thấy tài khoản với email '{email}'!"}

    now = time.time()
    with self._otp_lock:
        existing = self.pending_otps.get(clean_email)
        if existing and existing.get("otp_code") and not existing.get("consumed", False):
            if now < existing.get("expires_at", 0):
                elapsed = now - existing.get("created_at", 0)
                if elapsed < 60.0:
                    remaining_sec = int(math.ceil(60.0 - elapsed))
                    delivery_res = existing.get("gmail_delivery") or {"sent_real_gmail": False}
                    self._log_event(
                        layer="Quên Mật Khẩu (Gmail OTP)",
                        action="forgot_password_otp_throttled",
                        email=acc["email"],
                        status="PASS",
                        detail=f"Yêu cầu OTP trong thời gian chờ ({remaining_sec}s còn lại). Giữ nguyên mã OTP đang hiệu lực ({existing['otp_code']}).",
                        source=source,
                        extra={"cooldown_remaining_sec": remaining_sec, "idempotent": True},
                    )
                    resp = {
                        "ok": True,
                        "email": acc["email"],
                        "display_name": acc["display_name"],
                        "idempotent": True,
                        "cooldown_active": True,
                        "cooldown_remaining_seconds": remaining_sec,
                        "gmail_delivery": delivery_res,
                        "message": f"Mã OTP đã được gửi trước đó. Vui lòng kiểm tra hộp thư hoặc chờ {remaining_sec} giây trước khi gửi lại.",
                    }
                    if not send_gmail or not delivery_res.get("sent_real_gmail"):
                        resp["demo_otp_preview"] = existing["otp_code"]
                        resp["otp_code_for_test"] = existing["otp_code"]
                    return resp

    # Nếu hết cooldown (>60s) hoặc chưa có OTP:
    otp_code = f"{random.randint(100000, 999999)}"
    gmail_res = {"sent_real_gmail": False, "actual_recipient": acc["email"]}
    if send_gmail:
        gmail_res = self.send_real_gmail_otp(acc["email"], otp_code, acc["display_name"])
        if not gmail_res.get("sent_real_gmail"):
            err_msg = gmail_res.get("error") or gmail_res.get("note") or "Không thể gửi email OTP đến hộp thư người dùng."
            missing_sec = gmail_res.get("missing_secret")
            self._log_event(...)
            # ... (giữ nguyên error response khi thiếu secret)
            return fail_resp

    with self._otp_lock:
        self.pending_otps[clean_email] = {
            "email": acc["email"],
            "account_id": acc["account_id"],
            "display_name": acc["display_name"],
            "tier": acc["tier"],
            "otp_code": otp_code,
            "created_at": now,
            "expires_at": now + 300,
            "verified_layer2": False,
            "verified_layer3": False,
            "consumed": False,
            "gmail_delivery": gmail_res,
            "source": source,
        }
    # ... log và trả kết quả thành công

# Trong reset_password_with_otp (lines 634-644):
    otp_res = self.layer2_verify_otp(clean_email, otp_code, source=source)
    if not otp_res.get("ok"):
        return otp_res

    res = self.register_or_update_password(
        email=clean_email,
        password=pw1,
        confirm_password=pw2,
        source=source,
    )
    if res.get("ok"):
        with self._otp_lock:
            self.pending_otps.pop(clean_email, None) # 🔒 Tiêu hủy OTP chống replay
    return res
```

### Recipe 2: Cập Nhật `simulator/static/js/app.js`
Loại bỏ kích hoạt kép, hợp nhất logic vào `submit` của Form, thêm `inFlight` và countdown 60s:

```javascript
  // 1. Quản lý trạng thái inFlight cho Login Gate
  let isGateLoginInFlight = false;
  let isGateRegisterInFlight = false;
  let isGateForgotInFlight = false;
  let isSendingForgotOtp = false;
  let forgotOtpCooldownTimer = null;

  // Xóa bỏ đoạn mã cũ dòng 1711-1728 (nơi submit gọi button.click())
  // Thay thế bằng event listener duy nhất trên submit của mỗi form:

  if (gatePanelLogin) {
    gatePanelLogin.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (isGateLoginInFlight) return;
      const btn = byId("btnSubmitGateLogin");
      const emailEl = byId("gateLoginEmail");
      const pwEl = byId("gateLoginPassword");
      const email = emailEl ? emailEl.value.trim() : "";
      const password = pwEl ? pwEl.value : "";
      if (!email || !password) {
        if (gateStatusBox) gateStatusBox.textContent = "❌ Vui lòng nhập đầy đủ Email và Mật khẩu!";
        return;
      }
      isGateLoginInFlight = true;
      if (btn) { btn.disabled = true; btn.textContent = "⏳ Đang đăng nhập..."; }
      if (gateStatusBox) gateStatusBox.textContent = "Đang kiểm tra đăng nhập...";
      try {
        const res = await fetch("/api/auth3/layer1_login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, login_method: "password", method: "password", send_gmail: false }),
        });
        const data = await res.json();
        // ... (xử lý kết quả đăng nhập)
      } catch (_) {
        if (gateStatusBox) gateStatusBox.textContent = "Lỗi kết nối máy chủ khi đăng nhập.";
      } finally {
        isGateLoginInFlight = false;
        if (btn) { btn.disabled = false; btn.textContent = "Đăng nhập vào Nhà thông minh"; }
      }
    });
  }

  // Nút gửi OTP Quên mật khẩu với Countdown 60s
  if (btnSendForgotOtp) {
    btnSendForgotOtp.addEventListener("click", async () => {
      if (isSendingForgotOtp) return;
      const emailEl = byId("gateForgotEmail");
      const email = emailEl ? emailEl.value.trim() : "";
      if (!email) {
        if (gateStatusBox) gateStatusBox.textContent = "❌ Vui lòng nhập email nhận mã OTP!";
        return;
      }
      isSendingForgotOtp = true;
      btnSendForgotOtp.disabled = true;
      btnSendForgotOtp.textContent = "⏳ Đang gửi...";
      if (gateStatusBox) gateStatusBox.textContent = "Đang gửi mã OTP về Gmail...";
      try {
        const res = await fetch("/api/auth3/forgot_password_send_otp", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, send_gmail: true }),
        });
        const data = await res.json();
        if (data.ok && (!data.gmail_delivery || data.gmail_delivery.sent_real_gmail !== false)) {
          if (gateStatusBox) gateStatusBox.textContent = `📧 ${data.message}`;
          setForgotStep(2);

          // Khởi động đếm ngược 60s
          let countdown = data.cooldown_remaining_seconds || 60;
          btnSendForgotOtp.disabled = true;
          btnSendForgotOtp.textContent = `Gửi lại (${countdown}s)`;
          if (forgotOtpCooldownTimer) clearInterval(forgotOtpCooldownTimer);
          forgotOtpCooldownTimer = setInterval(() => {
            countdown--;
            if (countdown <= 0) {
              clearInterval(forgotOtpCooldownTimer);
              forgotOtpCooldownTimer = null;
              btnSendForgotOtp.disabled = false;
              btnSendForgotOtp.textContent = "Gửi OTP";
            } else {
              btnSendForgotOtp.textContent = `Gửi lại (${countdown}s)`;
            }
          }, 1000);
        } else {
          if (gateStatusBox) gateStatusBox.textContent = `❌ ${data.error || (data.gmail_delivery && data.gmail_delivery.note) || "Không gửi được OTP."}`;
          btnSendForgotOtp.disabled = false;
          btnSendForgotOtp.textContent = "Gửi OTP";
        }
      } catch (_) {
        if (gateStatusBox) gateStatusBox.textContent = "Lỗi kết nối khi gửi OTP.";
        btnSendForgotOtp.disabled = false;
        btnSendForgotOtp.textContent = "Gửi OTP";
      } finally {
        isSendingForgotOtp = false;
      }
    });
  }
```

---

## 6. Kế Hoạch Kiểm Thử TDD Cho Yêu Cầu R2

Người thực hiện (Implementer / Tester) cần viết bộ test TDD mới (ví dụ `tests/test_p6_r2_cooldown_and_triggers.py`):

1. **Test Cooldown Backend (Idempotent OTP):**
   - Gửi yêu cầu POST `/api/auth3/forgot_password_send_otp` lần 1 cho `senat6031@gmail.com` với mock SMTP. Xác nhận mã OTP $X$ được tạo và gửi.
   - Gửi tiếp yêu cầu POST lần 2 trong vòng 2 giây cho cùng email đó.
   - Xác nhận:
     * HTTP status là 200.
     * Response có `idempotent: True`, `cooldown_active: True`, `cooldown_remaining_seconds` xấp xỉ 58–60s.
     * Mock SMTP **chỉ được gọi đúng 1 lần duy nhất** (không phát email thứ 2).
     * Mã OTP trong `self.pending_otps` vẫn giữ nguyên là $X$.
   - Dùng mã $X$ để gọi `/api/auth3/forgot_password_reset` -> Đặt lại mật khẩu thành công.
   - Kiểm tra `self.pending_otps` không còn chứa `senat6031@gmail.com` (đã tiêu hủy).

2. **Test Single-Firing Frontend (Static Analysis & DOM Simulation):**
   - Đọc nội dung `simulator/static/js/app.js` và `simulator/static/index.html`.
   - Khẳng định không còn đoạn mã `submit` gọi `.click()` trên các nút submit.
   - Khẳng định các nút submit có trạng thái `disabled = true` trong khối try-finally.
   - Khẳng định nút gửi OTP có bộ đếm ngược countdown timer.

---
*Báo cáo hoàn tất và sẵn sàng để bàn giao cho Implementer.*
