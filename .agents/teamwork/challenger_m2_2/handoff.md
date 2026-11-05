# Báo Cáo Thẩm Định Đối Kháng (Empirical Challenge Report) — Challenger M2_2

**Nhiệm vụ:** Thẩm định đối kháng thực nghiệm Milestone 2 (R2 Anti-Double-Send Cooldown & Trigger Fixes)  
**Tác giả:** Challenger 2 (`challenger_m2_2` — Role: `critic`, `specialist`)  
**Ngày thực hiện:** 05/11/2026  
**Thư mục làm việc:** `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\challenger_m2_2`  
**Quyết định thẩm định (Verdict):** **APPROVE**  
**Loại bàn giao:** Hard (Task complete)

---

## 1. Quan Sát Thực Tế (Observation)

### 1.1. Khảo Sát và Kiểm Chứng Frontend Triggers trong `simulator/static/js/app.js`
- **Loại bỏ cơ chế `button.click()` bên trong submit listeners:**
  - Tại dòng 1718–1720: Lời gọi submit gọi `button.click()` cũ đã bị xóa bỏ hoàn toàn. Dòng 1720 chỉ là comment ghi nhận (`// btnSubmitGateLogin.click(), btnSubmitGateRegister.click(), btnSubmitForgotReset.click()`).
  - Lời gọi `.click()` duy nhất còn hoạt động trong toàn bộ tệp `app.js` là dòng 1515 (`btnHoldRecordVoice.click()`), phục vụ phím tắt micro Push-To-Talk.
  - Các form submit listener (`gatePanelLogin`, `gatePanelRegister`, `gatePanelForgot`) được gắn trực tiếp vào các hàm xử lý (`handleGateLoginSubmit`, `handleGateRegisterSubmit`, `handleForgotResetSubmit`), không có bất kỳ hành vi gọi đúp hay đệ quy nào.

- **Bảo vệ Trạng thái `inFlight` và `disabled` trên tất cả các nút bấm Auth:**
  - `btnSubmitGateLogin` (dòng 1739–1793):
    - Dòng 1740: `if (e && e.preventDefault) e.preventDefault();`
    - Dòng 1741: `if (isGateLoginInFlight) return;`
    - Dòng 1751–1754: `isGateLoginInFlight = true; btn.disabled = true; btn.textContent = "⏳ Đang đăng nhập...";`
    - Dòng 1786–1791 (khối `finally`): `isGateLoginInFlight = false; btn.disabled = false; btn.textContent = "Đăng nhập vào Nhà thông minh";`
  - `btnSubmitGateRegister` (dòng 1796–1864):
    - Dòng 1797: `if (e && e.preventDefault) e.preventDefault();`
    - Dòng 1798: `if (isGateRegisterInFlight) return;`
    - Dòng 1821–1824: `isGateRegisterInFlight = true; btn.disabled = true; btn.textContent = "⏳ Đang lưu...";`
    - Dòng 1857–1862 (khối `finally`): `isGateRegisterInFlight = false; btn.disabled = false; btn.textContent = "Xác nhận 2 mật khẩu & Lưu tài khoản";`
  - `btnSubmitForgotReset` (dòng 1952–2012):
    - Dòng 1953: `if (e && e.preventDefault) e.preventDefault();`
    - Dòng 1954: `if (isGateForgotInFlight) return;`
    - Dòng 1978–1981: `isGateForgotInFlight = true; btn.disabled = true; btn.textContent = "⏳ Đang đặt lại...";`
    - Dòng 2005–2010 (khối `finally`): `isGateForgotInFlight = false; btn.disabled = false; btn.textContent = "Đặt lại mật khẩu";`
  - `btnSendForgotOtp` (dòng 1893–1948):
    - Dòng 1896: `if (isSendingForgotOtp) return;`
    - Dòng 1903–1905: `isSendingForgotOtp = true; btnSendForgotOtp.disabled = true; btnSendForgotOtp.textContent = "⏳ Đang gửi...";`
    - Dòng 1945–1947 (khối `finally`): `isSendingForgotOtp = false;`

- **Bộ đếm ngược trực quan 60 giây (Visual Countdown Timer) trên `#btnSendForgotOtp`:**
  - Dòng 1918–1933:
    - Đọc `let remaining = Number(data.cooldown_remaining_seconds) || 60;`
    - Cập nhật nhãn nút: `btnSendForgotOtp.textContent = \`Gửi lại sau (\${remaining}s)\`;`
    - Xóa timer cũ nếu còn tồn tại: `if (forgotOtpCooldownTimer) clearInterval(forgotOtpCooldownTimer);`
    - Kích hoạt `setInterval` chu kỳ 1000ms: giảm dần `remaining--`.
    - Khi `remaining <= 0`: `clearInterval(forgotOtpCooldownTimer); forgotOtpCooldownTimer = null; btnSendForgotOtp.disabled = false; btnSendForgotOtp.textContent = "Gửi OTP";`
  - Khi gặp lỗi API (`data.ok == false`) hoặc lỗi kết nối (khối `catch` dòng 1941–1944): Nút lập tức mở khóa `btnSendForgotOtp.disabled = false; btnSendForgotOtp.textContent = "Gửi OTP";`, không gây treo nút vĩnh viễn.

- **Loại bỏ inline onclick trên `simulator/static/index.html`:**
  - Dòng 442–444: Nút `<button type="submit" id="btnLockdownUnlock">` hoàn toàn không có thuộc tính inline `onclick`, ngăn chặn kích hoạt 2 lần cùng lúc với sự kiện `onsubmit` của `#lockdownForm`.

### 1.2. Khảo Sát và Kiểm Chứng Cooldown Backend trong `simulator/auth_3layer.py`
- Khóa luồng an toàn: `self._otp_lock = threading.Lock()` tại dòng 85.
- Hàm `request_password_reset_otp` (dòng 547–650):
  - Dòng 560: `with self._otp_lock:` bảo vệ toàn vẹn dữ liệu trong môi trường nhiều luồng đồng thời.
  - Dòng 564–566:
    ```python
    elapsed = now - existing.get("created_at", 0)
    if elapsed < 60.0:
        remaining_sec = max(0, int(60.0 - elapsed))
        ...
        return {
            "ok": True,
            "idempotent": True,
            "cooldown_active": True,
            "cooldown_remaining_seconds": remaining_sec,
            ...
        }
    ```
  - Khi đặt lại mật khẩu thành công (`reset_password_with_otp`, dòng 679–681):
    ```python
    if res.get("ok"):
        with self._otp_lock:
            self.pending_otps.pop(clean_email, None)
    ```
    Mã OTP đã tiêu thụ bị hủy hoàn toàn, ngăn chặn tấn công replay.

---

## 2. Chuỗi Suy Luận Kỹ Thuật (Logic Chain)

1. **Từ Quan Sát 1.1 (Frontend Triggers & inFlight):**
   - Không còn sự kiện submit nào gọi `button.click()`, loại bỏ 100% nguyên nhân gây phát sinh 2 fetch request song song từ 1 lần click submit.
   - Các hàm submit form đều gọi `e.preventDefault()`, ngăn trình duyệt kích hoạt submit HTTP POST mặc định gây tải lại trang.
   - Cờ `inFlight` (`isGateLoginInFlight`, `isGateRegisterInFlight`, `isGateForgotInFlight`, `isSendingForgotOtp`) được kiểm tra ngay đầu hàm bằng guard early return (`if (inFlight) return;`), ngăn triệt để việc nhấp chuột nhanh liên tiếp (rapid double click).
   - Trạng thái `btn.disabled = true` được thiết lập trước khi gửi fetch và được bảo đảm khôi phục trong khối `finally`, loại trừ hoàn toàn nguy cơ nút bị treo khóa vĩnh viễn khi mạng rớt hoặc server trả mã lỗi 500.

2. **Từ Quan Sát 1.1 (Visual Countdown Timer):**
   - Giá trị thời gian đếm ngược được đồng bộ từ backend (`cooldown_remaining_seconds`), tự động thích ứng với thời gian cooldown còn lại thực tế nếu client gửi lại yêu cầu.
   - Cơ chế dọn dẹp timer cũ trước khi gán mới (`if (forgotOtpCooldownTimer) clearInterval(...)`) triệt tiêu nguy cơ rò rỉ bộ nhớ (timer leak) và xung đột nhiều bộ đếm.
   - Khi đếm ngược kết thúc (`remaining <= 0`), nút bấm trở lại trạng thái sẵn sàng (`disabled = false`, text `"Gửi OTP"`).
   - Khi có lỗi mạng/API, nút bấm được phục hồi tức thì mà không khởi động timer vô ích.

3. **Từ Quan Sát 1.2 & Bộ Kiểm Thử Thực Nghiệm (Backend Cooldown Boundaries):**
   - Đã xây dựng và thực thi bộ kiểm thử đối kháng `tests/test_challenger_phase6_m2_empirical.py` với việc đóng băng mốc thời gian bằng `patch("time.time")`:
     - Tại $t = 0.0s$ (ngay sau phát hành): `elapsed = 0.0s < 60.0s` $\rightarrow$ Throttled (`idempotent=True`, `remaining=60`, giữ nguyên OTP, không gửi email).
     - Tại $t = 30.0s$: `elapsed = 30.0s < 60.0s` $\rightarrow$ Throttled (`idempotent=True`, `remaining=30`).
     - Tại $t = 59.0s$: `elapsed = 59.0s < 60.0s` $\rightarrow$ Throttled (`idempotent=True`, `remaining=1`).
     - Tại $t = 59.9s$: `elapsed = 59.9s < 60.0s` $\rightarrow$ Throttled (`idempotent=True`, `remaining=0`).
     - Tại $t = 60.0s$: Điểm biên chính xác! `elapsed = 60.0s < 60.0s` là `False` $\rightarrow$ Cooldown hết hạn, sinh mã OTP mới khác mã cũ, chuyển phát email mới.
     - Tại $t = 61.0s$ (tương ứng $1.0s$ sau mã mới tại $60.0s$): Bị cooldown theo chu kỳ mới (`remaining=59`), bảo toàn mã mới.
   - Thử nghiệm phân biệt chữ hoa/thường: `SENAT6031@GMAIL.COM` và `senat6031@gmail.com` cùng trỏ về 1 khóa cooldown duy nhất nhờ `clean_email = str(email or "").strip().lower()`.
   - Thử nghiệm bắn đồng thời 15–30 threads từ nhiều luồng độc lập: Duy nhất 1 luồng được sinh mã và gửi email, toàn bộ các luồng còn lại nhận phản hồi idempotent bảo toàn đúng mã OTP đó mà không gây race condition.

---

## 3. Điểm Cần Lưu Ý (Caveats)

- **Lưu trữ Cooldown Bộ Nhớ:** Trạng thái cooldown `pending_otps` được quản lý trong bộ nhớ RAM của tiến trình backend. Đây là thiết kế tối ưu và phù hợp cho vòng đời 5 phút của OTP trong ứng dụng Smart Home.
- **Không Đọc/In Bí Mật:** 100% quá trình kiểm thử không đọc, không ghi, không in bất kỳ mật khẩu hoặc secret SMTP nào.

---

## 4. Kết Luận (Conclusion)

- **VERDICT: APPROVE**
- Toàn bộ các yêu cầu của Milestone 2 (R2 Anti-Double-Send Cooldown & Trigger Fixes) đã được thực hiện chính xác, đầy đủ và đạt chuẩn chất lượng cao:
  1. Loại bỏ triệt để double-firing trigger và đệ quy `button.click()`.
  2. Đảm bảo trạng thái `inFlight` và `disabled` với khối phục hồi `finally` trên toàn bộ các form đăng nhập, đăng ký và quên mật khẩu.
  3. Bộ đếm ngược trực quan 60 giây hoạt động mượt mà, chính xác và có khả năng tự phục hồi khi có sự cố.
  4. Cơ chế Cooldown 60 giây phía backend đạt độ chuẩn xác tuyệt đối tại mọi mốc biên ($0s, 30s, 59s, 59.9s, 60s, 61s$), bảo toàn mã OTP và an toàn đa luồng.

---

## 5. Phương Pháp Kiểm Chứng Độc Lập (Verification Method)

### 5.1. Chạy Bộ Kiểm Thử Đối Kháng Thực Nghiệm Python Mới
```powershell
pytest tests/test_challenger_phase6_m2_empirical.py -v
```
**Kết quả thực tế:**
- **8 passed, 0 failed, 3 warnings in 35.60s** (Exit Code: 0)

### 5.2. Chạy Bộ Kiểm Thử Mô Phỏng DOM & Timer Node.js Mới
```powershell
node tests/test_challenger_m2_frontend_node.js
```
**Kết quả thực tế:**
- **All 5 Challenger 2 Node.js tests PASSED cleanly!** (Exit Code: 0)

### 5.3. Chạy Toàn Bộ Các Bộ Kiểm Thử Mục Tiêu Milestone 2 & Milestone 1
```powershell
pytest tests/test_challenger_phase6_m2_empirical.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py tests/test_phase5_r3_otp_email.py -v
```
**Kết quả thực tế:**
- **59 passed, 0 failed, 3 warnings in 19.02s** (Exit Code: 0)

### 5.4. Chạy Toàn Bộ Bộ Kiểm Thử Hồi Quy Cũ (Regression)
```powershell
pytest tests/test_challenger_m2_gate_ux_empirical.py tests/test_challenger_phase6_m1.py tests/test_challenger_phase6_m1_2.py -v
```
**Kết quả thực tế:**
- **175 passed, 0 failed, 3 warnings in 7.54s** (Exit Code: 0)

### 5.5. Điều Kiện Vô Hiệu Hóa (Invalidation Conditions)
Báo cáo thẩm định này sẽ bị vô hiệu hóa nếu:
- Gửi 2 request OTP liên tiếp trong vòng 60 giây cho cùng một email mà mã OTP bị thay đổi hoặc email bị gửi lần 2.
- Nhấp nút submit form mà phát sinh 2 fetch request song song trên Network tab.
- Nút `#btnSendForgotOtp` không đếm ngược hoặc không mở khóa sau khi hết 60 giây.
