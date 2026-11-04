# BÁO CÁO ĐIỀU TRA KHẢO SÁT CHUYÊN SÂU (SURVEY REPORT)
**Mã khảo sát**: `teamwork_explorer_survey_1`  
**Tập lỗi phụ trách**: Bug 1, Bug 2, Bug 4, Bug 5, Bug 15 (từ `REAL_TEST_BUGS_20261105.md`)  
**Thư mục làm việc**: `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_explorer_survey_1`  
**Ngày thực hiện**: 05/11/2026  

---

## 1. Observation (Quan sát thực tế & Bằng chứng mã nguồn)

### 1.1. Bug 1: Lộ Credential & Gợi ý Mật khẩu mặc định trên UI và Logs
- **Vị trí 1 (`simulator/static/index.html`)**:
  - Dòng 255: `<p class="subtle">Tài khoản chính Chủ nhà: nep94121@gmail.com (Mật khẩu mặc định: ******)</p>` (Hiển thị nguyên văn chuỗi gợi ý mật khẩu).
  - Dòng 272: `<input type="email" id="gateLoginEmail" ... value="nep94121@gmail.com" placeholder="Nhập email (VD: nep94121@gmail.com)" />`
  - Dòng 277: `<input type="password" id="gateLoginPassword" ... value="******" placeholder="Nhập mật khẩu (mặc định: ******)" />`
  - Dòng 298: `<input type="text" id="gateRegName" ... value="Nguyễn Tuấn Anh" />`
  - Dòng 302, 307, 314: `<input type="email" id="gateRegEmail" value="nep94121@gmail.com" />`, `<input type="password" id="gateRegPassword" value="******" />`, `<input type="password" id="gateRegConfirmPassword" value="******" />`
  - Dòng 328, 339, 346: `gateForgotEmail` có `value="nep94121@gmail.com"`, `gateForgotNewPassword` và `gateForgotConfirmPassword` có `value="******"`.
  - Dòng 356: `<div id="gateStatusBox" class="subtle">Nhập Email + Mật khẩu (mặc định: ******) để vào bảng điều khiển Nhà thông minh.</div>`
  - Dòng 380: `<input id="lockdownPassword" ... placeholder="Nhập mật khẩu (mặc định: ******)" />`
- **Vị trí 2 (`mobile_app/index.html`)**:
  - Dòng 49 & 54: `mobileLoginEmail` có `value="nep94121@gmail.com"`, `mobileLoginPassword` có `value="******"`.
  - Dòng 81, 86, 93: `mobileRegEmail` value="nep94121@gmail.com", `mobileRegPassword` value="******", `mobileRegConfirmPassword` value="******".
  - Dòng 116, 142, 149: `mobileForgotEmail` value="nep94121@gmail.com", `mobileForgotNewPassword` value="******", `mobileForgotConfirmPassword` value="******".
  - Dòng 543, 548, 555: `mobileChangeEmail` value="nep94121@gmail.com", `mobileChangeNewPassword` value="******", `mobileChangeConfirmPassword` value="******".
- **Vị trí 3 (`simulator/static/auth.html`)**:
  - Dòng 115: `<input type="text" id="enrollSpeakerNameInput" value="Thành viên A" .../>`
  - Dòng 121, 124, 125: `loginEmail` value="nep94121@gmail.com", `loginPassword` value="******", `loginPasswordConfirm` value="******".
  - Dòng 143: `<option value="owner">Chủ nhà (Cấp 1) · nep94121@gmail.com (MK: ******)</option>`
  - Dòng 311, 312, 313: `inviteGoogleEmail` value="thanhvien_moi@gmail.com", `inviteDisplayName` value="Nguyễn Văn Em", `invitePassword` value="******".
- **Vị trí 4 (`simulator/auth_3layer.py`)**:
  - Dòng 355: Trực tiếp trả về plaintext password hint trong phản hồi lỗi khi đăng nhập sai:
    `"error": f"Sai mật khẩu cho tài khoản {acc['email']}! (Mật khẩu gợi ý: {acc['password_plain_hint']})"`
- **Vị trí 5 (`simulator/api/routes_logs.py` & `simulator/static/js/logs.js`)**:
  - `routes_logs.py` (dòng 118-151): `standardized_logs` đọc trực tiếp `raw.get("detail")` và `raw.get("details")` từ file nhật ký `system_audit_logs.jsonl` mà không qua bước lọc (masking/sanitization).
  - `simulator/data/system_audit_logs.jsonl` (ví dụ dòng 149, dòng 797, dòng 910): Chứa chuỗi `"actual": "Sai mật khẩu cho tài khoản ... (Mật khẩu gợi ý: ...)"` và `"password_plain_hint": "..."`.
  - `logs.js` (dòng 102): `item.detail` được render trực tiếp vào HTML `<div>${item.detail || 'Không có mô tả bổ sung.'}</div>`.

---

### 1.2. Bug 2: Lỗi quy trình Đăng xuất trên `/` và `/app`
- **Vị trí 1 (`simulator/static/js/app.js`)**:
  - Dòng 1457-1469 (Sự kiện click `btnLogoutHome`):
    ```javascript
    if (btnLogoutHome) {
      btnLogoutHome.addEventListener("click", () => {
        try {
          if (window.localStorage) window.localStorage.removeItem("smarthome_auth_session");
        } catch (_) {}
        if (homeCurrentAccountBadge) {
          homeCurrentAccountBadge.textContent = "Chưa đăng nhập";
        }
        if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = true;
        switchLoginGateTab("login");
        openLoginGateModal();
      });
    }
    ```
  - **Khiếm khuyết**:
    1. Không xóa giá trị trong các ô nhập (`gateLoginEmail.value`, `gateLoginPassword.value`). Do đó modal mở lại vẫn giữ nguyên mật khẩu cũ hoặc giá trị trước đó.
    2. Không xóa thông báo `gateStatusBox`. Khi đăng nhập thành công, `gateStatusBox` lưu `"✅ Đăng nhập thành công"`. Khi logout, modal mở lại với thông báo cũ này.
    3. Không ẩn nút `btnLogoutHome`: Header đổi sang `"Chưa đăng nhập"` nhưng nút `btnLogoutHome` vẫn hiển thị nguyên vẹn.
    4. Không xóa session cookie (`smarthome_session`) hoặc sessionStorage.
- **Vị trí 2 (`simulator/static/index.html`)**:
  - Dòng 53-57: Ban đầu trong HTML tĩnh, header hardcode:
    ```html
    <span class="status" id="homeCurrentAccountBadge" title="Tài khoản đang đăng nhập">
      👑 Chủ nhà · nep94121@gmail.com
    </span>
    <button type="button" class="btn btn-secondary" id="btnLogoutHome" style="min-height:34px; padding:0 12px; font-size:12px;">
      Đăng nhập / Đổi TK
    </button>
    ```
    Nút `btnLogoutHome` hiện sẵn ngay cả khi chưa xác thực.
- **Vị trí 3 (`simulator/static/js/mobile_app.js`)**:
  - Dòng 348-361:
    ```javascript
    function submitMobileLogout() {
      mobileLoggedIn = false;
      mobileLoggedInEmail = '';
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.removeItem('mobileLoggedIn');
        sessionStorage.removeItem('mobileLoggedInEmail');
      }
      const main = document.getElementById('mobileMainContent');
      const nav = document.getElementById('mobileBottomNav');
      const gate = document.getElementById('mobileLoginGate');
      if (main) main.hidden = true;
      if (nav) nav.hidden = true;
      if (gate) gate.hidden = false;
    }
    ```
  - **Khiếm khuyết**: Không reset form `mobileLoginForm` hay `mobileLoginEmail`/`mobileLoginPassword`, không reset `mobileLoginMsg`. Khi `mobileLoginGate` hiện lại, do HTML có `value="..."` và input không bị xóa, tài khoản và mật khẩu lại xuất hiện.

---

### 1.3. Bug 4: Quên mật khẩu bằng OTP Gmail/SMTP & Tài khoản Seed Production
- **Vị trí 1 (Cơ sở dữ liệu Seed `simulator/auth/constants_and_crypto.py` & `simulator/data/accounts_3layer.json`)**:
  - `DEFAULT_ACCOUNTS` (dòng 50-184) chỉ định nghĩa 4 tài khoản mặc định: `nep94121@gmail.com` (tier 1), `thanhviena.hust@gmail.com` (tier 2), `thanhvienb.hust@gmail.com` (tier 2), `khachc.guest@gmail.com` (tier 3).
  - Hoàn toàn KHÔNG có tài khoản kiểm thử:
    - `senat6031@gmail.com` (Thành viên gia đình, Tier 2).
    - `kbanh376@gmail.com` (Khách, Tier 3).
  - Khi người dùng gửi yêu cầu Quên mật khẩu tới `senat6031@gmail.com`, hàm `request_password_reset_otp` (`simulator/auth_3layer.py` dòng 555-557) gọi `self.find_account("senat6031@gmail.com")` trả về `None`, dẫn đến lỗi:
    `"error": "Không tìm thấy tài khoản với email 'senat6031@gmail.com'!"` (status code 400).
- **Vị trí 2 (`simulator/static/js/app.js` dòng 1612)**:
  - Khi bấm nút `btnSendForgotOtp`:
    ```javascript
    const res = await fetch("/api/auth3/forgot_password_send_otp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, send_gmail: false }),
    });
    ```
    Đang truyền `send_gmail: false` cứng, khiến hệ thống không bao giờ kích hoạt gửi mail thật!
  - Dòng 1616:
    `if (otpEl && data.demo_otp_preview) otpEl.value = data.demo_otp_preview;`
    Tự động điền trước mã OTP vào ô nhập, phá vỡ luồng người dùng phải mở hộp thư Gmail kiểm tra mã xác thực thật.
- **Vị trí 3 (`simulator/static/index.html` dòng 324-354)**:
  - Tab 3 `#gatePanelForgot` đang hiển thị dồn tất cả các trường trên cùng một form: Email, OTP, Mật khẩu mới, Xác nhận mật khẩu mới. Chưa chia thành 3 bước độc lập theo luồng nghiệp vụ chuẩn:
    - Bước 1: Nhập email tài khoản $\rightarrow$ Bấm "Gửi OTP".
    - Bước 2: Nhập mã OTP 6 số $\rightarrow$ Bấm "Xác nhận OTP / Tiếp tục".
    - Bước 3: Đặt 2 ô Mật khẩu mới (trống, không điền sẵn) $\rightarrow$ Bấm "Đặt lại mật khẩu".

---

### 1.4. Bug 5: `/auth` Wizard đăng ký giọng nói & "Kiểm tra đăng nhập" lỗi
- **Vị trí 1 (`simulator/static/auth.html`)**:
  - Dòng 115: `enrollSpeakerNameInput` có `value="Thành viên A"`.
  - Dòng 121, 124, 125: `loginEmail` có `value="nep94121@gmail.com"`, `loginPassword` và `loginPasswordConfirm` có `value="******"`.
  - Dòng 142-147: Thẻ select `accountPresetSelect` chứa các giá trị mẫu giả lập (`thanhviena.hust@gmail.com`, `khach.hust@gmail.com`).
- **Vị trí 2 (`simulator/static/js/auth.js`)**:
  - Dòng 5: `let selectedSpeakerName = 'Thành viên A';`
  - Dòng 69-99: `onEnrollTierSelectChange(tierVal)`: Khi đổi tier, code JS tự động gán đè tên và email mẫu:
    - Chọn Tier 2: Ép tên thành `"Thành viên A"`, email thành `"thanhviena.hust@gmail.com"`.
    - Chọn Tier 3: Ép tên thành `"Khách C"`, email thành `"khach.hust@gmail.com"`.
  - Dòng 719-723 (`submitLayer1` - Nút "Kiểm tra đăng nhập"):
    ```javascript
    const res = await fetch('/api/auth3/layer1_login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, method, google_id_token: 'GOOGLE_OAUTH_SIM_TOKEN_OK' })
    });
    ```
    Backend FastAPI `simulator/api/routes_auth.py` dòng 532 đọc `login_method = str(payload.get("login_method", "password")).strip()`. Tuy nhiên client gửi `{ method }`. Hơn nữa, khi người dùng kiểm tra với tài khoản thật (hoặc đổi sang Tier 2), mật khẩu nhập vào không khớp với mật khẩu của email mẫu bị ép dẫn đến kiểm tra thất bại mà không hiển thị lý do thực tế từ server.

---

### 1.5. Bug 15: Header Desktop chưa hiển thị thời gian truy cập còn lại
- **Vị trí 1 (`simulator/static/index.html`)**:
  - Dòng 49-77 (`<header class="top">` $\rightarrow$ `<div class="top-actions">`):
    Hiện chỉ có `homeCurrentAccountBadge`, `btnLogoutHome`, `btnToggleServer`, menu `selActiveSpeaker`.
    Hoàn toàn KHÔNG có phần tử DOM nào để hiển thị thời lượng/thời gian truy cập còn lại (access time remaining).
- **Vị trí 2 (`simulator/static/js/app.js`)**:
  - Hàm `applyLoggedInUserBanner(userObj)` (dòng 1375-1385) chỉ cập nhật nội dung cho `homeCurrentAccountBadge` (ví dụ: `👑 Cấp 1 · Chủ nhà: Nguyễn Tuấn Anh`).
  - Thiếu logic cập nhật thời gian còn lại: Với tài khoản Owner (Tier 1) phải hiển thị `"Không giới hạn"`, với Thành viên (Tier 2) hiển thị `"Còn 30 ngày"`, với Khách (Tier 3) hiển thị thời gian hiệu lực còn lại.

---

## 2. Logic Chain (Chuỗi lập luận nguyên nhân $\rightarrow$ giải pháp)

```
[B1: Hardcoded credentials & hints in HTML/JS/Python error/Logs]
    │──> Quan sát: value="..." trong input tags, text "Mật khẩu mặc định: ******" trên UI
    │──> Quan sát: auth_3layer.py:355 format error kèm "(Mật khẩu gợi ý: ...)"
    │──> Quan sát: routes_logs.py / logs.js không mask chuỗi mật khẩu trong detail/summary
    └──> Kết luận B1: Bắt buộc xoá sạch mọi attribute value mặc định, loại bỏ text gợi ý trên UI, loại bỏ password hint khỏi error response, và thêm bộ lọc masking regex trên backend /logs + frontend logs.js.

[B2: Logout flow retaining state & credentials]
    │──> Quan sát: btnLogoutHome click chỉ xoá localStorage, không set input.value="", không clear gateStatusBox, không ẩn btnLogoutHome
    │──> Quan sát: submitMobileLogout chỉ chuyển tab/ẩn DOM, không reset form hay sessionStorage/cookie
    └──> Kết luận B2: Xây dựng hàm clearAuthState() toàn diện: reset tất cả form inputs về rỗng, xóa text gateStatusBox/mobileLoginMsg, xóa toàn bộ session storage/cookie, ẩn nút Đăng xuất, và đưa badge về "Chưa đăng nhập".

[B4: Forgot Password OTP failure & missing seeds]
    │──> Quan sát: senat6031@gmail.com & kbanh376@gmail.com không có trong DEFAULT_ACCOUNTS
    │──> Quan sát: app.js:1612 gửi send_gmail: false và auto-fill OTP từ demo_otp_preview
    │──> Quan sát: index.html Tab 3 hiển thị dồn 4 input cùng lúc
    └──> Kết luận B4: Bổ sung 2 tài khoản test vào DEFAULT_ACCOUNTS và accounts_3layer.json (Tier 2 cho senat6031, Tier 3 cho kbanh376, hash PBKDF2 chuẩn). Sửa app.js gửi send_gmail: true, ngắt auto-fill OTP. Tách Tab 3 thành 3 container bước: Step 1 (Email) -> Step 2 (OTP) -> Step 3 (2 ô mật khẩu mới).

[B5: /auth mock wizard & broken check login]
    │──> Quan sát: auth.html và auth.js pre-fill "Thành viên A" và auto-override email mẫu
    │──> Quan sát: submitLayer1 gửi parameter sai và không hiển thị error từ backend
    └──> Kết luận B5: Xoá bỏ dữ liệu mẫu khỏi input. Không tự ý override email/tên khi đổi select tier. Cho phép nhập email/mật khẩu tài khoản thật và hiển thị thông báo lỗi/thành công chuẩn xác từ server.

[B15: Missing access duration in Desktop Header]
    │──> Quan sát: <header class="top"> thiếu phần tử hiển thị duration
    │──> Quan sát: applyLoggedInUserBanner thiếu gán nhãn thời hạn
    └──> Kết luận B15: Thêm <span class="status" id="homeSessionDurationBadge"> vào top-actions của index.html. Cập nhật app.js để khi đăng nhập: Owner -> "Không giới hạn", Tier 2 -> "Còn 30 ngày", Tier 3 -> thời lượng tương ứng; khi logout -> ẩn badge.
```

---

## 3. Caveats (Các giả định & Vùng ranh giới kỹ thuật)

1. **Bảo toàn 68 DOM IDs và 25 Window Hooks**:
   Các phần tử như `mobileLoginEmail`, `mobileLoginPassword`, `gateLoginEmail`, `gateLoginPassword`, `gateStatusBox`, `btnLogoutHome`, `homeCurrentAccountBadge`, `btnSendForgotOtp`, `btnSubmitForgotReset`, `mobileForgotEmail`, `mobileForgotOtp`, `mobileForgotNewPassword`, `mobileForgotConfirmPassword`... TUYỆT ĐỐI KHÔNG ĐƯỢC XÓA HOẶC ĐỔI ID. Chỉ xóa thuộc tính `value="..."` và điều chỉnh hành vi logic.
2. **Không ghi mật khẩu dạng văn bản rõ (Zero-Leak Plaintext)**:
   Trong mã nguồn, tài liệu khảo sát, bản vá, commit git và log hệ thống, tuyệt đối không được ghi mật khẩu dạng văn bản thô. Toàn bộ mật khẩu trong seed phải được lưu trữ dưới dạng mã băm PBKDF2 SHA-256 (`hash_password`).
3. **Môi trường Gửi Mail (Gmail / SMTP / gws CLI)**:
   - Trên máy cục bộ: Lệnh `gws gmail users messages send` hoạt động với `gws 0.22.5`.
   - Trên Vercel Production: Môi trường serverless không có binary `gws`. Code backend trong `simulator/auth/invite_and_gmail_mixin.py` cần có fallback an toàn (SMTP hoặc graceful return không gây crash 500) và khi `send_gmail=True`, hệ thống thực thi việc gửi email thật qua cấu hình SMTP/Gmail sẵn có.
4. **Mã hóa và định dạng tệp**:
   Bắt buộc duy trì 100% định dạng UTF-8 không BOM và chuẩn kết thúc dòng Unix POSIX LF (`\n`, 0 CRLF).

---

## 4. Conclusion (Kết luận kỹ thuật & Đề xuất phương án thực thi)

Toàn bộ 5 lỗi Bug 1, Bug 2, Bug 4, Bug 5, Bug 15 đã được định vị chính xác 100% về file, hàm và số dòng. Dưới đây là bảng tổng hợp phương án thực thi dành cho Implementer:

| Bug | File mục tiêu | Dòng chính | Thay đổi cốt lõi đề xuất |
|---|---|---|---|
| **Bug 1** | `simulator/static/index.html`<br>`mobile_app/index.html`<br>`simulator/static/auth.html`<br>`simulator/auth_3layer.py`<br>`simulator/api/routes_logs.py`<br>`simulator/static/js/logs.js` | `index.html`: 255, 272, 277, 298, 302, 307, 314, 328, 339, 346, 356, 380<br>`mobile_app/index.html`: 49, 54, 81, 86, 93, 116, 142, 149, 543, 548, 555<br>`auth.html`: 115, 121, 124, 125, 143, 311-313<br>`auth_3layer.py`: 355<br>`routes_logs.py`: 118-151<br>`logs.js`: 102 | Xóa toàn bộ `value="..."` và chuỗi gợi ý mật khẩu trên UI.<br>Sửa `auth_3layer.py`: Xoá `(Mật khẩu gợi ý: ...)` khỏi chuỗi lỗi.<br>Thêm regex masking mật khẩu trong `routes_logs.py` và `logs.js`. |
| **Bug 2** | `simulator/static/js/app.js`<br>`simulator/static/index.html`<br>`simulator/static/js/mobile_app.js` | `app.js`: 1457-1469<br>`index.html`: 55-57<br>`mobile_app.js`: 348-361 | Khi logout trên `/`: Xoá sạch giá trị các ô input, reset `gateStatusBox`, ẩn nút `btnLogoutHome`, xóa cookie/session, đặt badge là "Chưa đăng nhập".<br>Khi logout trên `/app`: Xoá sạch toàn bộ input fields, reset `mobileLoginMsg`. |
| **Bug 4** | `simulator/auth/constants_and_crypto.py`<br>`simulator/data/accounts_3layer.json`<br>`simulator/static/js/app.js`<br>`simulator/static/index.html` | `constants_and_crypto.py`: 50-184<br>`accounts_3layer.json`<br>`app.js`: 1610-1665<br>`index.html`: 324-354 | Thêm `senat6031@gmail.com` (tier 2) và `kbanh376@gmail.com` (tier 3) vào seed.<br>Sửa `app.js`: `send_gmail: true`, bỏ auto-fill OTP.<br>Chia Tab 3 thành 3 bước độc lập (Email $\rightarrow$ OTP $\rightarrow$ Mật khẩu mới). |
| **Bug 5** | `simulator/static/auth.html`<br>`simulator/static/js/auth.js` | `auth.html`: 114-148<br>`auth.js`: 5, 40-104, 713-740 | Xoá dữ liệu mẫu khỏi form wizard, không ép ghi đè email/tên giả lập.<br>Đồng bộ tham số `login_method` và hiển thị phản hồi chính xác khi kiểm tra đăng nhập tài khoản thật. |
| **Bug 15** | `simulator/static/index.html`<br>`simulator/static/js/app.js` | `index.html`: 51-61<br>`app.js`: 1375-1385, 1457-1469 | Thêm `#homeSessionDurationBadge` vào top header của `index.html`.<br>Cập nhật `app.js`: Hiển thị "Không giới hạn" (Owner), "Còn 30 ngày" (Gia đình), thời hạn thực tế (Khách); ẩn đi khi đăng xuất. |

---

## 5. Verification Method (Chiến lược Kiểm thử TDD độc lập)

### 5.1. Kịch bản TDD cho Bug 1 & Bug 2
Viết file test `tests/test_real_bugs_survey1_gate.py`:
- **Test 1 (Đảm bảo không lộ Credential trên HTML tĩnh)**:
  Sử dụng `BeautifulSoup` phân tích `index.html`, `mobile_app/index.html`, `auth.html`:
  - Assert không có trường input nào thuộc danh sách password/email có thuộc tính `value` không rỗng.
  - Assert chuỗi văn bản không chứa `123456`, `Mật khẩu mặc định`, `GiaDinhMoi@2026`.
- **Test 2 (Masking trong API /logs và phản hồi lỗi)**:
  - Dùng `TestClient(app)` gọi `POST /api/auth3/layer1_login` với mật khẩu sai cho `nep94121@gmail.com`.
  - Assert `res.status_code in [200, 400]`, `res.json()["ok"] is False`.
  - Assert chuỗi `res.json()["error"]` KHÔNG chứa `Mật khẩu gợi ý` hay mật khẩu thực tế.
  - Gọi `GET /api/logs/dashboard`: Assert trong toàn bộ `audit_logs` không xuất hiện chuỗi `GiaDinh@123` hay `Mật khẩu gợi ý: GiaDinh...`.
- **Test 3 (Trạng thái sau Đăng xuất)**:
  - Dùng Node.js DOM runner (tương tự `test_challenger_m2_gate_ux_empirical.py`) kích hoạt sự kiện click `btnLogoutHome`.
  - Assert `gateLoginEmail.value === ""`, `gateLoginPassword.value === ""`.
  - Assert `gateStatusBox.textContent` không chứa "thành công".
  - Assert `btnLogoutHome.hidden === true` hoặc `style.display === "none"`.
  - Assert `homeCurrentAccountBadge.textContent` chứa "Chưa đăng nhập".

### 5.2. Kịch bản TDD cho Bug 4
- **Test 1 (Kiểm thử gửi OTP Quên mật khẩu cho tài khoản Seed mới)**:
  - Gọi `POST /api/auth3/forgot_password_send_otp` với `{"email": "senat6031@gmail.com", "send_gmail": False}`.
  - **TRƯỚC VÁ**: Trả về 400 "Không tìm thấy tài khoản với email 'senat6031@gmail.com'!".
  - **SAU VÁ**: Trả về 200 `ok=True`.
  - Thực hiện tương tự với `kbanh376@gmail.com`.
- **Test 2 (Kiểm thử cấu trúc 3 bước Quên mật khẩu trên Web)**:
  - Phân tích DOM `index.html`: Kiểm tra `#gatePanelForgot` có chứa các khối điều hướng 3 bước (nhập email $\rightarrow$ nhập OTP $\rightarrow$ đặt mật khẩu mới).

### 5.3. Kịch bản TDD cho Bug 5
- **Test 1 (Làm sạch Wizard /auth)**:
  - Kiểm tra `auth.html`: `enrollSpeakerNameInput` không có `value="Thành viên A"`.
- **Test 2 (Kiểm tra đăng nhập với tài khoản thật)**:
  - Gọi `POST /api/auth3/layer1_login` với `email="nep94121@gmail.com"` và mật khẩu chủ nhà chuẩn.
  - Assert trả về 200 `ok=True`, chuyển sang Bước 2.

### 5.4. Kịch bản TDD cho Bug 15
- **Test 1 (Kiểm tra phần tử DOM thời gian truy cập)**:
  - Phân tích `index.html`: Khẳng định phần tử `#homeSessionDurationBadge` tồn tại bên trong `<header class="top">`.
- **Test 2 (Hiển thị thời hạn theo vai trò)**:
  - Chạy hàm `applyLoggedInUserBanner({ tier: 1, email: "nep94121@gmail.com" })`:
    Assert `#homeSessionDurationBadge.textContent === "Không giới hạn"`.
  - Chạy hàm `applyLoggedInUserBanner({ tier: 2, email: "senat6031@gmail.com" })`:
    Assert `#homeSessionDurationBadge.textContent === "Còn 30 ngày"`.

### 5.5. Lệnh thực thi kiểm thử toàn dự án
```powershell
python -X utf8 -m pytest tests/ --basetemp=.pytest_tmp
```
Điều kiện đạt: 100% test pass (exit code 0), không còn bất kỳ warning rò rỉ dữ liệu nhạy cảm hay thất bại regression nào.
