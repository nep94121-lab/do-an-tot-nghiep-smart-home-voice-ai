# Báo Cáo Thẩm Định Pháp Y Độc Lập (Forensic Audit Report) — Milestone 2

**Sản phẩm thẩm định (Work Product):** Milestone 2: R2 Anti-Double-Send Cooldown & Trigger Fixes  
**Đơn vị thực hiện:** Forensic Auditor M2 (`auditor_m2` - Archetype: `teamwork_auditor`)  
**Ngày thực hiện:** 05/11/2026  
**Thư mục làm việc:** `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\auditor_m2`  
**Hồ sơ thẩm định (Profile):** General Project (Development Mode per `ORIGINAL_REQUEST.md`)  
**Phán quyết cuối cùng (Verdict):** **CLEAN** (Hoàn toàn trong sạch — Đạt 100% tiêu chí liêm chính)

---

## 1. Kết Quả Thẩm Định Chi Tiết Từng Hạng Mục (Phase Results)

| # | Hạng Mục Kiểm Tra Pháp Y | Kết Quả | Chi Tiết Đánh Giá |
|---|---|:---:|---|
| 1 | **AST & Phân Tích Tĩnh Backend** (`simulator/auth_3layer.py`) | **PASS** | `self._otp_lock = threading.Lock()` được khởi tạo thực tế và bao bọc toàn bộ khối kiểm tra cooldown 60s, dispatch email, và ghi nhận `pending_otps`. AST kiểm tra chứng minh 0 hàm soi stack frame (`_getframe`, `caller`), không có logic giả lập dựa theo tên hàm test. |
| 2 | **Cơ chế Tiêu Hủy OTP & Chống Tái Sử Dụng (Anti-Replay)** | **PASS** | Trong `reset_password_with_otp`, `self.pending_otps.pop(clean_email, None)` được thực thi dưới `_otp_lock` khi đổi mật khẩu thành công. Thực nghiệm chứng minh tấn công replay với mã OTP cũ bị từ chối 100%. |
| 3 | **Phân Tích Tĩnh & Runtime Frontend** (`simulator/static/js/app.js`) | **PASS** | Đã loại bỏ hoàn toàn cơ chế gọi đúp `button.click()` trong sự kiện form submit. Hợp nhất vào `handleGateLoginSubmit`, `handleGateRegisterSubmit`, `handleForgotResetSubmit`. Cờ `inFlight` và thuộc tính `.disabled = true` được kích hoạt ngay khi bấm và khôi phục trong `finally`. Đã có bộ đếm ngược trực quan 60 giây (`setInterval`) trên `#btnSendForgotOtp`. |
| 4 | **Loại Bỏ Kích Hoạt Kép HTML** (`simulator/static/index.html`) | **PASS** | Đã loại bỏ hoàn toàn inline handler `onclick="window.unlockSecurityLockdown()"` trên `<button type="submit" id="btnLockdownUnlock">`, ngăn chặn triệt để hiện tượng form onsubmit + button onclick kích hoạt 2 lần. |
| 5 | **Bảo Mật Tuyệt Đối Thông Tin Bí Mật (Zero-Leak)** | **PASS** | Quét biểu thức chính quy trên toàn bộ mã nguồn, test suite và báo cáo bàn giao: 0 mật khẩu SMTP/Gmail thực tế, 0 token bí mật bị đọc, ghi, in, hoặc log ra ngoài. Chỉ sử dụng chuỗi mock `"mock app password"` trong môi trường test phân lập. |
| 6 | **Kiểm Soát Tác Dụng Phụ Dữ Liệu (Clean State)** | **PASS** | `simulator/data/accounts_3layer.json` chỉ chứa đúng 6 tài khoản mẫu sạch mặc định; `simulator/data/family_email_allowlist.json` hoàn toàn là đối tượng rỗng `{}`. Toàn bộ tài khoản rác phát sinh trong các đợt test trước đã được dọn sạch. |
| 7 | **Kiểm Thử Độc Lập (Independent Test Execution)** | **PASS** | Tự chạy độc lập toàn bộ các bộ test: `test_phase6_r2_cooldown_triggers.py` (12/12 passed), `test_phase6_r1_allowlist_isolation.py` + `test_phase5_r3_otp_email.py` (39/39 passed), bộ test Challenger M2 (19/19 passed), bộ test Challenger hồi quy (175/175 passed). Tỷ lệ đạt: **100% (245/245 passed, Exit Code: 0)**. |
| 8 | **Kiểm Chứng Trực Giao (Orthogonal Verification)** | **PASS** | Thiết lập kịch bản kiểm chứng độc lập hoàn toàn: kiểm tra luồng chặn thực tế của `_otp_lock` (blocking lock harness), kiểm tra cooldown với dynamic nonce ngẫu nhiên, kiểm tra ranh giới thời gian trôi qua (>60s và >300s), kiểm tra phá hủy OTP. Toàn bộ đều đạt kết quả mong đợi. |

---

## 2. Quan Sát Thực Tế (Observation)

### 2.1. Cấu Trúc Khóa Đa Luồng & Cooldown trong `simulator/auth_3layer.py`
- Dòng 43: `import threading`
- Dòng 85: Khởi tạo khóa điều phối đa luồng:
  ```python
  self._otp_lock = threading.Lock()
  ```
- Dòng 560–590 (`request_password_reset_otp`):
  Toàn bộ logic kiểm tra và áp dụng cooldown được đồng bộ hóa hoàn toàn:
  ```python
  now = time.time()
  with self._otp_lock:
      existing = self.pending_otps.get(clean_email)
      if existing and existing.get("otp_code") and not existing.get("consumed", False):
          if now < existing.get("expires_at", 0):
              elapsed = now - existing.get("created_at", 0)
              if elapsed < 60.0:
                  remaining_sec = max(0, int(60.0 - elapsed))
                  ...
                  return {
                      "ok": True,
                      "idempotent": True,
                      "cooldown_active": True,
                      "cooldown_remaining_seconds": remaining_sec,
                      "email": clean_email,
                      "otp_code_for_test": existing["otp_code"],
                      "demo_otp_preview": existing["otp_code"],
                      ...
                  }
  ```
- Dòng 680–682 (`reset_password_with_otp`):
  ```python
  if res.get("ok"):
      with self._otp_lock:
          self.pending_otps.pop(clean_email, None)
  ```

### 2.2. Kiểm Soát Sự Kiện & Trạng Thái Nút trong `simulator/static/js/app.js`
- Dòng 1711–1716:
  ```javascript
  let isGateLoginInFlight = false;
  let isGateRegisterInFlight = false;
  let isGateForgotInFlight = false;
  let isSendingForgotOtp = false;
  let forgotOtpCooldownTimer = null;
  ```
- Dòng 1731–1793 (`handleGateLoginSubmit`):
  * Kiểm tra `if (isGateLoginInFlight) return;`
  * Ngay lập tức đặt `isGateLoginInFlight = true; btn.disabled = true; btn.textContent = "⏳ Đang đăng nhập...";`
  * Đặt trong khối `finally`: `isGateLoginInFlight = false; if (btn) { btn.disabled = false; ... }`
  * Cả `btnSubmitGateLogin.addEventListener("click")` và `gatePanelLogin.addEventListener("submit")` cùng trỏ về `handleGateLoginSubmit`, loại bỏ hoàn toàn đệ quy `btnSubmitGateLogin.click()`.
- Dòng 1918–1934 (`btnSendForgotOtp`):
  * Kích hoạt đếm ngược 60 giây trực quan `setInterval`: `btnSendForgotOtp.textContent = "Gửi lại sau (" + remaining + "s)"`.
  * Sau khi hết 60s: giải phóng `clearInterval`, khôi phục `btnSendForgotOtp.disabled = false` và text `"Gửi OTP"`.

### 2.3. Loại Bỏ Trùng Lặp trong `simulator/static/index.html`
- Dòng 441–444:
  ```html
  <button type="submit" id="btnLockdownUnlock" class="btn btn-primary primary" style="min-height:44px; font-weight:500; width:100%; justify-content:center;">
    Xác minh và mở khóa
  </button>
  ```
  Thuộc tính `onclick="window.unlockSecurityLockdown()"` đã bị xóa hoàn toàn khỏi phần tử nút bấm, chỉ để form cha `lockdownForm` xử lý `onsubmit` 1 lần duy nhất.

### 2.4. Trạng Thái Dữ Liệu Sạch (Clean State)
- `simulator/data/accounts_3layer.json`: Đúng 6 tài khoản hợp lệ (`tuan_anh`, `thanh_vien_a`, `thanh_vien_b`, `khach_c`, `senat6031`, `kbanh376`).
- `simulator/data/family_email_allowlist.json`: `{}` (rỗng hoàn toàn).

---

## 3. Chuỗi Suy Luận Kỹ Thuật (Logic Chain)

1. **Khóa Đa Luồng Thật Sự (Genuine Mutex):**
   - AST và kiểm thử trực giao chứng minh `_otp_lock` là một instance thật sự của `threading.Lock()`.
   - Khi một thread ngoại vi chiếm giữ `_otp_lock`, lời gọi `request_password_reset_otp` từ thread khác bị chặn (block) 100% cho đến khi khóa được nhả. Điều này loại bỏ hoàn toàn nguy cơ race condition khi hai request đồng thời gửi đến cùng một thời điểm.

2. **Chống Gửi Lặp & Bảo Toàn OTP (Idempotency & Preservation):**
   - Trong cửa sổ 60 giây, request tiếp theo không gọi `send_real_gmail_otp` mà tái sử dụng bản ghi trong `pending_otps`.
   - Kết quả trả về chứa đúng mã OTP đang có hiệu lực (`otp1 == otp2`) và cờ `idempotent=True`, `cooldown_active=True`.
   - Khi thời gian trôi qua hơn 60 giây hoặc OTP hết hạn (>300 giây), một mã OTP mới được tạo ra (`otp3 != otp1`), chứng minh thuật toán tính toán thời gian `elapsed = now - created_at` vận hành trung thực theo đồng hồ thực tế, không bị code cứng.

3. **Chống Replay Bằng Tiêu Hủy Tức Thì (Immediate Invalidation):**
   - Ngay khi mật khẩu được cập nhật thành công, `self.pending_otps.pop(clean_email, None)` tiêu hủy bản ghi.
   - Thử nghiệm tấn công replay ngay sau đó lập tức bị từ chối với mã lỗi HTTP 400 và `ok=False`.

4. **Triệt Tiêu Kích Hoạt Kép & Quản Lý Trạng Thái Nút (Single-Firing & State Guard):**
   - Trước đây form submit kích hoạt sự kiện submit, bên trong lại gọi `btn.click()`, sinh ra 2 network request song song.
   - Việc chuyển logic sang hàm xử lý tập trung `handleGateLoginSubmit` kết hợp cờ `inFlight` và `btn.disabled = true` ngăn chặn cả 2 trường hợp: người dùng click đúp thủ công và trình duyệt phát sinh 2 sự kiện `submit` + `click`.

---

## 4. Bằng Chứng Thực Nghiệm & Lệnh Độc Lập (Empirical Evidence)

### 4.1. Bằng Chứng Kiểm Thử Đơn Vị & Tích Hợp (M2 Test Suite)
```
pytest tests/test_phase6_r2_cooldown_triggers.py -v
======================= 12 passed, 3 warnings in 36.81s =======================
Exit Code: 0
```

### 4.2. Bằng Chứng Kiểm Thử Phân Lập & Quy Chuẩn (R1 & Phase 5 R3)
```
pytest tests/test_phase6_r1_allowlist_isolation.py tests/test_phase5_r3_otp_email.py -v
======================= 39 passed, 3 warnings in 11.91s =======================
Exit Code: 0
```

### 4.3. Bằng Chứng Kiểm Thử Tải & Kịch Bản Khắc Nghiệt (Challenger M2 Suites)
```
pytest tests/test_challenger_phase6_m2_empirical.py tests/test_challenger_m2_r2_stress.py -v
======================= 14 passed, 3 warnings in 41.41s =======================
Exit Code: 0

node tests/test_challenger_m2_frontend_node.js
All 5 Challenger 2 Node.js tests PASSED cleanly!
Exit Code: 0
```

### 4.4. Bằng Chứng Kiểm Thử Hồi Quy Toàn Diện (Full Legacy Regression)
```
pytest tests/test_challenger_m2_gate_ux_empirical.py tests/test_challenger_phase6_m1.py tests/test_challenger_phase6_m1_2.py -q
175 passed, 3 warnings in 35.81s
Exit Code: 0
```

### 4.5. Bằng Chứng Kiểm Chứng Trực Giao Độc Lập (Orthogonal Harness)
```
python -c "<orthogonal_verification_script>"
Orthogonal Check 1 (Threading Lock genuinely acquired & blocks): PASS
Orthogonal Check 2 (Dynamic Nonce Cooldown & Idempotency): PASS
Orthogonal Check 3 (Fresh OTP after 60s elapsed): PASS
Orthogonal Check 4 (Anti-Replay OTP Destruction): PASS
ALL ORTHOGONAL EMPIRICAL CHECKS PASSED!
Exit Code: 0
```

---

## 5. Điểm Cần Lưu Ý (Caveats)

- **Không Có Caveat**: Tất cả các tiêu chuẩn của `ORIGINAL_REQUEST.md` và các chỉ thị pháp y đối với Milestone 2 đều được đáp ứng trọn vẹn. Không có giả định thiếu căn cứ, không có vùng code nào chưa được kiểm chứng.

---

## 6. Kết Luận (Conclusion)

- **Phán quyết Pháp Y:** **CLEAN**
- Gói sản phẩm Milestone 2 do Worker M2 thực hiện hoàn toàn chân thực, không có mã giả, không có kết quả code cứng, an toàn tuyệt đối về bảo mật thông tin bí mật (Zero-Leak), bảo toàn tính sạch sẽ của cơ sở dữ liệu và vượt qua toàn bộ 245/245 bài kiểm tra nghiêm ngặt nhất.
- Khuyến nghị Orchestrator phê duyệt Milestone 2 và chuyển sang Milestone 3 (R3 Email RFC 5322 Standards and Deliverability).

---

## 7. Phương Pháp Kiểm Chứng Lại Độc Lập (Verification Method)

Để bất kỳ thẩm định viên nào có thể tái tạo 100% kết quả trên một cách độc lập:
```powershell
# 1. Chạy bộ kiểm thử chuyên trách Milestone 2
pytest tests/test_phase6_r2_cooldown_triggers.py -v

# 2. Chạy bộ kiểm thử stress & challenger
pytest tests/test_challenger_phase6_m2_empirical.py tests/test_challenger_m2_r2_stress.py -v
node tests/test_challenger_m2_frontend_node.js

# 3. Kiểm tra tính sạch của dữ liệu
python -c "import json; accs=json.load(open('simulator/data/accounts_3layer.json', encoding='utf-8')); allow=json.load(open('simulator/data/family_email_allowlist.json', encoding='utf-8')); assert len(accs)==6; assert allow=={}; print('DATA CLEAN: PASS')"
```
