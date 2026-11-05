# Handoff Report: Requirement R2 (Anti-Double-Send Cooldown & Trigger Fixes)

**Agent:** Explorer 2 (`survey_exp2` / `teamwork_explorer`)  
**Working Directory:** `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\explorer_survey_2`  
**Recipient:** Orchestrator (`91485de0-7c6f-449a-ba3f-ed6820ebb01a`) / Implementer Agent  
**Date:** 2026-11-05  
**Handoff Type:** Hard (Task complete)  

---

## 1. Observation

### Observation 1: Backend OTP Dispatch Lacks Cooldown & Overwrites Active OTP
- **File:** `simulator/auth_3layer.py`
- **Lines 557–596:**
  ```python
  557:         otp_code = f"{random.randint(100000, 999999)}"
  558:         gmail_res = {"sent_real_gmail": False, "actual_recipient": acc["email"]}
  559:         if send_gmail:
  560:             gmail_res = self.send_real_gmail_otp(acc["email"], otp_code, acc["display_name"])
  ...
  584:         self.pending_otps[acc["email"].lower()] = {
  585:             "email": acc["email"],
  586:             "account_id": acc["account_id"],
  587:             "display_name": acc["display_name"],
  588:             "tier": acc["tier"],
  589:             "otp_code": otp_code,
  590:             "created_at": time.time(),
  591:             "expires_at": time.time() + 300,
  592:             "verified_layer2": False,
  593:             "verified_layer3": False,
  594:             "gmail_delivery": gmail_res,
  595:             "source": source,
  596:         }
  ```
- **File:** `simulator/api/routes_auth.py:653-664`:
  ```python
  653: @router.post("/api/auth3/forgot_password_send_otp")
  654: async def api_auth3_forgot_password_send_otp(payload: dict[str, Any]) -> JSONResponse:
  655:     """Gửi mã OTP 6 số về Gmail cho tính năng Quên mật khẩu."""
  656:     email = str(payload.get("email", "nep94121@gmail.com")).strip()
  657:     send_gmail = bool(payload.get("send_gmail", True))
  658:     res = get_auth_3layer_manager().request_password_reset_otp(
  659:         email=email,
  660:         send_gmail=send_gmail,
  661:         source=str(payload.get("source", "Web Quên Mật Khẩu")),
  662:     )
  663:     status_code = 200 if res.get("ok") else int(res.get("status_code", 400))
  664:     return JSONResponse(res, status_code=status_code)
  ```
- Không có bất kỳ kiểm tra thời gian trôi qua (`elapsed < 60`) giữa các lần gửi. Mỗi lần gọi hàm đều vô điều kiện tạo mã mới và gửi email thật, đồng thời ghi đè mã cũ.

### Observation 2: Frontend Form Submit Calls Button `.click()` Causing Double-Firing
- **File:** `simulator/static/index.html`
  - Dòng 296, 308:
    ```html
    296: <form id="gatePanelLogin" style="display:grid; gap:10px;" onsubmit="event.preventDefault();">
    ...
    308:   <button type="submit" id="btnSubmitGateLogin" class="btn btn-primary" style="width:100%;">
    309:     Đăng nhập vào Nhà thông minh
    310:   </button>
    ```
  - Dòng 314, 345: Form `#gatePanelRegister` có nút `<button type="submit" id="btnSubmitGateRegister">`.
  - Dòng 351, 394: Form `#gatePanelForgot` có nút `<button type="submit" id="btnSubmitForgotReset">`.
  - Dòng 422, 442: Form `#lockdownForm` có `onsubmit="event.preventDefault(); window.unlockSecurityLockdown();"` và nút `<button type="submit" id="btnLockdownUnlock" onclick="window.unlockSecurityLockdown()">`.
- **File:** `simulator/static/js/app.js`
  - Dòng 1711–1728:
    ```javascript
    1711:   if (gatePanelLogin) {
    1712:     gatePanelLogin.addEventListener("submit", (e) => {
    1713:       e.preventDefault();
    1714:       if (btnSubmitGateLogin) btnSubmitGateLogin.click();
    1715:     });
    1716:   }
    1717:   if (gatePanelRegister) {
    1718:     gatePanelRegister.addEventListener("submit", (e) => {
    1719:       e.preventDefault();
    1720:       if (btnSubmitGateRegister) btnSubmitGateRegister.click();
    1721:     });
    1722:   }
    1723:   if (gatePanelForgot) {
    1724:     gatePanelForgot.addEventListener("submit", (e) => {
    1725:       e.preventDefault();
    1726:       if (btnSubmitForgotReset) btnSubmitForgotReset.click();
    1727:     });
    1728:   }
    ```
  - Dòng 1739–1782:
    ```javascript
    1740:   if (btnSubmitGateLogin) {
    1741:     btnSubmitGateLogin.addEventListener("click", async () => {
    1742:       // ... fetch("/api/auth3/layer1_login", ...)
    ```

### Observation 3: Absence of inFlight / Disabled State on Desktop Buttons
- **File:** `simulator/static/js/app.js`
  - Dòng 1740–1782 (`btnSubmitGateLogin`): Không thiết lập `disabled = true`, không có cờ `inFlight`.
  - Dòng 1785–1841 (`btnSubmitGateRegister`): Không thiết lập `disabled = true`, không có cờ `inFlight`.
  - Dòng 1863–1890 (`btnSendForgotOtp`): Không thiết lập `disabled = true`, không có cờ `inFlight`, không có countdown timer 60s.
  - Dòng 1893–1941 (`btnSubmitForgotReset`): Không thiết lập `disabled = true`, không có cờ `inFlight`.
- **So sánh đối chiếu với Mobile App:** `simulator/static/js/mobile_app.js` (dòng 50, 72, 457, 480-496) đã có sẵn mẫu `btn.disabled = true` và `forgotOtpCountdownTimer = setInterval(..., 1000)` đếm ngược 60 giây, nhưng phía desktop `app.js` hoàn toàn chưa được áp dụng.

---

## 2. Logic Chain

1. **Từ Observation 1 đến Rủi ro Gửi Lặp (Spam / Overwrite OTP):**
   - Khi người dùng gửi yêu cầu OTP quên mật khẩu (hoặc bấm đúp nút), API `/api/auth3/forgot_password_send_otp` gọi `request_password_reset_otp()`.
   - Vì không có kiểm tra thời gian giữa các yêu cầu cho cùng một email, mỗi request ngay lập tức kích hoạt `send_real_gmail_otp()` và tạo `otp_code` mới.
   - Thư thứ 2 được gửi tới Gmail; mã trong thư thứ nhất lập tức bị ghi đè trong `self.pending_otps`.
   - Người dùng mở email thấy mã đầu tiên, nhập vào web sẽ thất bại vì server chỉ chấp nhận mã thứ 2.
   - Do đó, cần cơ chế kiểm tra `elapsed = now - existing["created_at"]`: Nếu `elapsed < 60.0`, không gửi email mới, không tạo mã mới, trả về trạng thái idempotent kèm `cooldown_active: True`, bảo toàn mã OTP đang còn hạn.

2. **Từ Observation 2 đến Hiện tượng Double-Firing trên Frontend:**
   - Khi người dùng bấm nút submit `#btnSubmitGateLogin`, trình duyệt phát sự kiện `click` trên button trước -> listener `click` tại `app.js:1741` thực thi, khởi động `fetch()` lần 1.
   - Theo chuẩn HTML5, việc click vào `<button type="submit">` lập tức kích hoạt sự kiện `submit` trên thẻ cha `<form id="gatePanelLogin">`.
   - Listener `submit` tại `app.js:1712` bắt được sự kiện, gọi `btnSubmitGateLogin.click()`.
   - Lệnh gọi `.click()` bằng code phát tiếp một sự kiện `click` DOM nữa -> listener `click` tại `app.js:1741` chạy lần 2 -> khởi động `fetch()` lần 2.
   - Như vậy, 1 lần bấm chuột của người dùng sinh ra chính xác 2 request mạng song song.
   - Điều này giải thích tại sao cùng một lúc server nhận được 2 request đăng nhập hoặc 2 request gửi OTP.

3. **Từ Observation 3 đến Yêu cầu inFlight / Disabled State:**
   - Trong quá trình mạng đang gửi request (thường mất từ 300ms đến 2000ms), nút bấm không bị `disabled`.
   - Nếu người dùng nhấp chuột nhiều lần hoặc nhấn phím liên tục, mỗi lần nhấp đều phát sinh request mới.
   - Khắc phục bằng cách khóa nút (`disabled = true`, `inFlight = true`) ngay khi bắt đầu request, và mở lại trong khối `finally` (hoặc chuyển sang đếm ngược 60s đối với nút gửi OTP).

---

## 3. Caveats

1. **Chế độ kiểm thử (send_gmail: False):**
   Trong các bài kiểm thử tự động (pytest/Playwright), cờ `send_gmail` thường là `False`. Cơ chế cooldown vẫn cần hoạt động chính xác (trả về `idempotent: True` và bảo toàn `demo_otp_preview` / `otp_code_for_test` của mã đang còn hiệu lực).
2. **Khởi động lại Server:**
   Bộ nhớ `self.pending_otps` là In-memory. Nếu server khởi động lại, bộ đếm cooldown sẽ được làm mới. Điều này là chấp nhận được và đúng thông lệ đối với OTP có thời hạn 5 phút.
3. **Phạm vi email:**
   Cooldown được tính theo từng email nhận (`email.strip().lower()`), đảm bảo người dùng A yêu cầu OTP không làm ảnh hưởng hay chặn người dùng B.

---

## 4. Conclusion

1. **Backend:**
   Cần bổ sung `self._otp_lock = threading.Lock()` vào `ThreeLayerAuthManager` và cài đặt điều kiện kiểm tra cooldown 60 giây trong `request_password_reset_otp`. Khi nhận request trong vòng 60s từ lần gửi trước, trả về HTTP 200 idempotent với `cooldown_active: True`, giữ nguyên `otp_code` cũ và không phát email. Tiêu hủy OTP (`self.pending_otps.pop(clean_email, None)`) sau khi đặt lại mật khẩu thành công ở `reset_password_with_otp`.
2. **Frontend:**
   Xóa bỏ hoàn toàn cơ chế `form.submit -> button.click()` tại các dòng 1711–1728 trong `simulator/static/js/app.js`. Chuyển toàn bộ logic xử lý sang một listener duy nhất gắn vào sự kiện `submit` của từng form (`gatePanelLogin`, `gatePanelRegister`, `gatePanelForgot`).
3. **Trạng thái Nút bấm:**
   Thêm cờ `inFlight` và vô hiệu hóa (`btn.disabled = true`) cho `#btnSubmitGateLogin`, `#btnSubmitGateRegister`, `#btnSubmitForgotReset`, `#btnSendForgotOtp` trong suốt thời gian gọi API. Thêm bộ đếm ngược 60 giây (`setInterval` 1000ms) cho `#btnSendForgotOtp` sau khi gửi thành công.
4. **Chi tiết thiết kế và mã đề xuất:**
   Đã được lập chi tiết đầy đủ trong [survey_report.md](file:///C:/Users/LENOVO/datn-wt/p6-otp/.agents/teamwork/explorer_survey_2/survey_report.md).

---

## 5. Verification Method

Để kiểm chứng độc lập sau khi Implementer cài đặt bản vá:

1. **Kiểm tra Backend Cooldown 60s (Unit / Integration Test):**
   - Viết test gửi 2 request liên tiếp tới `/api/auth3/forgot_password_send_otp` với cùng 1 email:
     ```python
     res1 = client.post("/api/auth3/forgot_password_send_otp", json={"email": "senat6031@gmail.com", "send_gmail": False})
     res2 = client.post("/api/auth3/forgot_password_send_otp", json={"email": "senat6031@gmail.com", "send_gmail": False})
     assert res2.status_code == 200
     assert res2.json()["idempotent"] is True
     assert res2.json()["cooldown_active"] is True
     assert res1.json()["otp_code_for_test"] == res2.json()["otp_code_for_test"] # Mã OTP không bị đổi
     ```
   - Chạy lệnh test: `pytest tests/test_phase5_r3_otp_email.py -v` (đảm bảo pass 100%).

2. **Kiểm tra Loại Bỏ Kích Hoạt Kép (Frontend Code Inspection):**
   - Tìm kiếm chuỗi `btnSubmitGateLogin.click()` trong `simulator/static/js/app.js`. Kết quả phải là 0 kết quả bên trong event listener submit.
   - Kiểm tra các nút bấm `#btnSubmitGateLogin`, `#btnSendForgotOtp` có thuộc tính `disabled` trong khối async handler.

3. **Điều Kiện Vô Hiệu Hóa Kết Luận (Invalidation Conditions):**
   - Nếu gửi 2 request liên tiếp mà `self.pending_otps` sinh ra 2 mã OTP khác nhau -> Kết luận bị vô hiệu hóa (cooldown chưa hoạt động).
   - Nếu bấm nút submit trên giao diện mà console network ghi nhận 2 request POST đồng thời -> Kết luận bị vô hiệu hóa (kích hoạt kép vẫn còn).
