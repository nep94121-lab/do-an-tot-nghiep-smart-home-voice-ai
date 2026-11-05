# Báo Cáo Phản Biện Thực Nghiệm (Empirical Challenge Report) — Challenger 1

**Nhiệm vụ:** Thẩm định đối kháng thực nghiệm Milestone 2 (R2 Anti-Double-Send Cooldown & Trigger Fixes)  
**Tác giả:** Challenger 1 (`challenger_m2_1` - `teamwork_challenger`, vai trò `critic`, `specialist`)  
**Thư mục làm việc:** `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\challenger_m2_1`  
**Quyết định thẩm định (Verdict):** **APPROVE**  
**Loại bàn giao:** Hard (Task complete)  

---

## 1. Quan Sát Thực Tế (Observation)

### 1.1. Mã nguồn Backend và Cơ chế Khóa Đa Luồng
- **Tệp `simulator/auth_3layer.py`:**
  - Khởi tạo khóa luồng `self._otp_lock = threading.Lock()` tại `ThreeLayerAuthManager.__init__`.
  - Trong phương thức `request_password_reset_otp` (dòng 553–650):
    * Khối `with self._otp_lock:` bao bọc toàn bộ luồng kiểm tra `self.pending_otps.get(clean_email)` và phát hành mã OTP mới cùng lệnh gửi Gmail.
    * Khi phát hiện request gửi lặp trong vòng 60 giây (`elapsed < 60.0`), hệ thống không gửi thêm email mới, bảo toàn nguyên vẹn mã OTP hiện có (`existing["otp_code"]`), và trả về response với `ok=True`, `idempotent=True`, `cooldown_active=True`, `cooldown_remaining_seconds`.
    * Chuẩn hóa email `clean_email = str(email or "").strip().lower()` ngăn ngừa tấn công qua mặt bằng chữ hoa hoặc khoảng trắng thừa.
  - Trong phương thức `reset_password_with_otp` (dòng 679–682):
    * Sau khi đổi mật khẩu thành công (`res.get("ok")`), thực hiện `with self._otp_lock: self.pending_otps.pop(clean_email, None)` tiêu hủy ngay lập tức mã OTP đã sử dụng.
- **Tệp `simulator/api/routes_auth.py`:**
  - Endpoint `POST /api/auth3/forgot_password_reset` (dòng 668–682): Khi mã OTP không hợp lệ hoặc đã bị tiêu hủy, `res.get("ok")` là `False`, endpoint trả về `status_code=400` (`int(res.get("status_code", 400))`).

### 1.2. Mã nguồn Frontend và Triệt Tiêu Double-Firing
- **Tệp `simulator/static/js/app.js`:**
  - Các khối listener `gatePanelLogin.addEventListener("submit", ... btnSubmitGateLogin.click())`, `gatePanelRegister`, `gatePanelForgot` đã được xóa bỏ hoàn toàn.
  - Trạng thái `isGateLoginInFlight`, `isGateRegisterInFlight`, `isGateForgotInFlight`, `isSendingForgotOtp` và `.disabled = true` / `.disabled = false` được kiểm soát chặt chẽ trong `try ... finally`.
  - Nút `#btnSendForgotOtp` có bộ đếm ngược trực quan 60 giây (`setInterval` / `clearInterval`) hiển thị `Gửi lại sau (${remaining}s)`.
- **Tệp `simulator/static/index.html`:**
  - Nút `#btnLockdownUnlock` đã loại bỏ thuộc tính inline `onclick="window.unlockSecurityLockdown()"` trùng lặp.

### 1.3. Kết Quả Thực Thi Kiểm Thử Đối Kháng Thực Nghiệm (Empirical Stress Testing)
Challenger đã tự thiết kế và thực thi trực tiếp bộ test đối kháng chuyên sâu `tests/test_challenger_m2_r2_stress.py`:
- Lệnh thực thi:
  ```powershell
  pytest tests/test_challenger_m2_r2_stress.py -v
  ```
- Kết quả thực tế (Verbatim Output):
  ```
  tests/test_challenger_m2_r2_stress.py::TestMilestone2EmpiricalChallenge::test_challenge_1_concurrency_stress_30_threads PASSED [ 16%]
  tests/test_challenger_m2_r2_stress.py::TestMilestone2EmpiricalChallenge::test_challenge_2_rapid_fire_10_sequential_requests_within_5_seconds PASSED [ 33%]
  tests/test_challenger_m2_r2_stress.py::TestMilestone2EmpiricalChallenge::test_challenge_3_different_recipients_independent_cooldown PASSED [ 50%]
  tests/test_challenger_m2_r2_stress.py::TestMilestone2EmpiricalChallenge::test_challenge_4_consumed_otp_reuse_fails_with_400 PASSED [ 66%]
  tests/test_challenger_m2_r2_stress.py::TestMilestone2EmpiricalChallenge::test_challenge_5_adversarial_email_casing_and_whitespace_isolation PASSED [ 83%]
  tests/test_challenger_m2_r2_stress.py::TestMilestone2EmpiricalChallenge::test_challenge_6_timing_boundary_under_and_over_60s PASSED [100%]
  ======================= 6 passed, 3 warnings in 11.56s =======================
  ```

### 1.4. Kết Quả Hồi Quy Toàn Diện (Full Regression)
- Lệnh thực thi 5 bộ test kết hợp:
  ```powershell
  pytest tests/test_challenger_m2_r2_stress.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py tests/test_phase5_r3_otp_email.py tests/test_challenger_m2_gate_ux_empirical.py -v
  ```
- Kết quả thực tế:
  ```
  ======================= 90 passed, 3 warnings in 36.60s =======================
  Exit Code: 0
  ```

---

## 2. Chuỗi Suy Luận Kỹ Thuật (Logic Chain)

1. **Từ Quan sát 1.1 và Kết quả Test Challenge 1 (30 Concurrent Threads):**
   - 30 luồng chạy đồng thời cùng gửi request OTP cho 1 email (`senat6031@gmail.com`) được đồng bộ điểm xuất phát bằng `threading.Barrier(30)`. Thêm độ trễ mạng giả lập `0.03s` trong hàm gửi email.
   - Kết quả: Hàm `send_real_gmail_otp` chỉ được gọi **đúng 1 lần duy nhất** (`email_dispatch_counter == 1`).
   - Toàn bộ 30 luồng nhận phản hồi HTTP 200 với `ok=True`. Trong đó có 1 response khởi tạo ban đầu và 29 responses mang cờ `idempotent=True`, `cooldown_active=True`.
   - Mã OTP được bảo toàn đồng nhất 100% trên cả 30 luồng. Điều này chứng minh khóa `self._otp_lock` giải quyết triệt để vấn đề race condition và chống gửi email trùng lặp ở mức tải cao.

2. **Từ Quan sát 1.1 và Kết quả Test Challenge 2 (Rapid-fire 10 requests trong <5s):**
   - 10 request liên tiếp được gửi trong tổng thời gian `0.55s` (nhỏ hơn rất nhiều so với ngưỡng 5s).
   - Kết quả: Chỉ 1 email phát đi, 9 request tiếp theo được đánh dấu `idempotent=True` và `cooldown_active=True`, mã OTP trong `pending_otps` không bị thay đổi hay ghi đè.

3. **Từ Quan sát 1.1 và Kết quả Test Challenge 3 (Phân lập giữa các Recipients):**
   - Gửi liên tiếp cho Recipient A (`senat6031@gmail.com`), Recipient B (`nep94121@gmail.com`), Recipient C (`kbanh376@gmail.com`).
   - Cả 3 người nhận đều nhận được mã OTP riêng và phát sinh 3 email độc lập. Cooldown của người A hoàn toàn không ảnh hưởng tới người B hay người C. Khi người A gửi lại, chỉ người A bị throttled.

4. **Từ Quan sát 1.1 và Kết quả Test Challenge 4 (Anti-Replay / Consumed OTP):**
   - Khi mã OTP được dùng để đổi mật khẩu thành công qua `POST /api/auth3/forgot_password_reset`, nó lập tức bị xóa khỏi `pending_otps`.
   - Khi kẻ tấn công hoặc client gửi lại request đổi mật khẩu với cùng mã OTP vừa dùng, API từ chối với mã lỗi **HTTP 400** và `ok: False`. Gọi trực tiếp qua backend manager cũng trả về `status_code: 400` và `ok: False`.

5. **Từ Quan sát 1.1 và Kết quả Test Challenge 5 & 6 (Chuẩn hóa ký tự & Biên thời gian):**
   - Email viết hoa `SENAT6031@GMAIL.COM` hay có khoảng trắng thừa `   senat6031@gmail.com   ` đều được ánh xạ về cùng một bucket cooldown với `senat6031@gmail.com`.
   - Tại mốc `elapsed = 59.5s`: Cooldown vẫn kích hoạt (idempotent=True). Tại mốc `elapsed = 60.5s`: Cooldown tự động hết hạn và cho phép sinh mã OTP mới.

6. **Từ Quan sát 1.2, 1.4:**
   - 90/90 bài kiểm tra liên tầng (bao gồm kiểm tra định dạng tệp 0 CRLF, UTF-8 không BOM, DOM Enter key, toggle password visibility, SVG symbol, và các bộ test của Milestone 1, Milestone 2) đều vượt qua 100%.

---

## 3. Điểm Cần Lưu Ý (Caveats)

- **Mock Môi trường Email:** Theo đúng yêu cầu cô lập kiểm thử (R1/R4) và quy tắc Zero-Leak, toàn bộ các bài test sử dụng SMTP mock / test mode `send_gmail=False` / mock dispatch. Quá trình kiểm tra không in, không đọc, không làm rò rỉ bất kỳ thông tin nhạy cảm (Gmail App Password) nào.
- **Tính Phụ Thuộc Bộ Nhớ RAM:** Cooldown và `pending_otps` được quản lý in-memory trên tiến trình máy chủ. Nếu máy chủ khởi động lại, cooldown sẽ được thiết lập lại từ đầu. Đây là thiết kế chuẩn xác đối với OTP tạm thời 5 phút.

---

## 4. Kết Luận (Conclusion)

- **Quyết định (Verdict):** **APPROVE**
- Milestone 2 (R2 Anti-Double-Send Cooldown & Trigger Fixes) do Worker M2 thực hiện đạt tiêu chuẩn chất lượng cao, bền bỉ trước các bài kiểm thử áp lực cao (30 luồng đồng thời, 10 request dồn dập, phân lập người nhận, chống tái sử dụng mã OTP đã tiêu thụ, chuẩn hóa ký tự hoa/khoảng trắng).
- Không phát hiện bất kỳ lỗi hồi quy hay lỗ hổng logic nào.

---

## 5. Phương Pháp Kiểm Chứng Độc Lập (Verification Method)

### 5.1. Lệnh Kiểm Thử Đối Kháng Chuyên Sâu
```powershell
pytest tests/test_challenger_m2_r2_stress.py -v
```
*Kỳ vọng: 6 passed, 0 failed trong ~12s.*

### 5.2. Lệnh Kiểm Thử Hồi Quy Toàn Diện Cả Hệ Thống
```powershell
pytest tests/test_challenger_m2_r2_stress.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py tests/test_phase5_r3_otp_email.py tests/test_challenger_m2_gate_ux_empirical.py -v
```
*Kỳ vọng: 90 passed, 0 failed trong ~37s, Exit Code: 0.*

### 5.3. Điều Kiện Vô Hiệu Hóa (Invalidation Conditions)
Báo cáo và quyết định APPROVE sẽ bị vô hiệu nếu:
1. Có bất kỳ bài test nào trong `tests/test_challenger_m2_r2_stress.py` bị FAIL khi chạy lại.
2. Có hiện tượng 30 luồng đồng thời phát sinh trên 1 email được gửi đi.
3. Mã OTP đã dùng để đổi mật khẩu thành công mà gọi lại API đổi mật khẩu vẫn trả về HTTP 200.
