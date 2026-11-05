# Báo Cáo Bàn Giao (Handoff Report) — Explorer 1 (survey_exp1)

**Nhiệm vụ:** Khảo sát Yêu cầu R1: Email Allowlist và Cách Ly Kiểm Thử (Test Isolation)  
**Tác giả:** Explorer 1 (`survey_exp1` - `teamwork_explorer`)  
**Ngày bàn giao:** 05/11/2026  
**Thư mục làm việc:** `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\explorer_survey_1`  
**Tệp báo cáo chi tiết:** [survey_report.md](file:///C:/Users/LENOVO/datn-wt/p6-otp/.agents/teamwork/explorer_survey_1/survey_report.md)  

---

## 1. Quan Sát Thực Tế (Observation)

### 1.1. Hiện trạng Chuyển phát Email trong Mã Nguồn
- **Tệp [simulator/auth/invite_and_gmail_mixin.py](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth/invite_and_gmail_mixin.py)**:
  - Dòng 503–576: Hàm `send_invite_link_via_gmail` thực thi `subprocess.run(["gws", "gmail", "users", "messages", "send", ...], shell=True)` trực tiếp mà **không có bất kỳ bước kiểm tra allowlist nào**.
  - Dòng 587–594: Hàm `send_real_gmail_otp`:
    ```python
    recipient = target_email.strip()
    if not recipient or "@" not in recipient:
        recipient = "nep94121@gmail.com"
    actual_to = (
        "nep94121@gmail.com"
        if any(recipient.endswith(suf) for suf in (".hust@gmail.com", ".guest@gmail.com", ".invite@gmail.com", ".family@gmail.com"))
        else recipient
    )
    ```
    Logic này chỉ lọc 4 đuôi domain giả lập. Mọi email không kết thúc bằng 4 đuôi này (ví dụ `thanh_vien_chuan@gmail.com`, `hoc_sinh_moi@gmail.com`, `tan_binh_gia_dinh@gmail.com`) đều được giữ nguyên `actual_to = recipient` và cố gắng gửi SMTP thật hoặc CLI `gws` thật, gây ra nguy cơ bounce mail hoặc gửi email ra bên ngoài.
  - Dòng 630–663: Gửi qua `smtplib.SMTP(smtp_host, smtp_port)` hoặc `smtplib.SMTP_SSL`.
  - Dòng 664–697: Fallback sang `subprocess.run(["gws", ...])`.

- **Tệp [simulator/api/routes_auth.py](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/api/routes_auth.py)**:
  - Dòng 534: Trong `api_auth3_layer1_login`:
    `send_gmail = bool(payload.get("send_gmail", True))` mặc định là `True`.
  - Dòng 657: Trong `api_auth3_forgot_password_send_otp`:
    `send_gmail = bool(payload.get("send_gmail", True))` mặc định là `True`.

### 1.2. Hiện trạng Giao diện Cổng Đăng Nhập Trang Chủ (`/`)
- **Tệp [simulator/static/js/app.js](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/static/js/app.js)**:
  - Dòng 1739–1756: Trình lắng nghe sự kiện của `#btnSubmitGateLogin` (form modal đăng nhập tại trang `/`):
    ```javascript
    const res = await fetch("/api/auth3/layer1_login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, login_method: "password", method: "password" }),
    });
    ```
    Payload hoàn toàn không gửi thuộc tính `send_gmail: false`. Do đó kết hợp với dòng 534 ở `routes_auth.py`, backend tự hiểu `send_gmail: true` và gửi thư thật.

- **Tệp [tests/test_playwright_3roles_live.py](file:///C:/Users/LENOVO/datn-wt/p6-otp/tests/test_playwright_3roles_live.py)**:
  - Dòng 41, 83, 125: Các ca kiểm thử Playwright thực hiện `page.click("#btnSubmitGateLogin")` cho 3 vai trò (`nep94121@gmail.com`, `senat6031@gmail.com`, `kbanh376@gmail.com`). Do `app.js` không truyền `send_gmail: false`, mỗi lượt chạy test Playwright đều kích hoạt việc phát tán email thật trên máy trạm.

### 1.3. Hiện trạng Thư Mục Kiểm Thử `tests/`
- Tệp `tests/conftest.py` **không tồn tại** trên hệ thống đĩa (chỉ có `tests/e2e/conftest.py`).
- Không có fixture `autouse` toàn cục nào để cô lập `smtplib.SMTP`, `smtplib.SMTP_SSL` và lệnh `gws` subprocess.

### 1.4. Hiện trạng Dữ Liệu Tệp Cấu Hình
- **Tệp [simulator/data/accounts_3layer.json](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/data/accounts_3layer.json)**: Đang chứa 18 tài khoản (752 dòng). Trong đó 12 tài khoản là dữ liệu test rác bị lưu vết (`thanhvien_test_c2`, `khach_test_c3`, `khach_tu_c2`, `con_yeu_e2e_test`, `con_yeu_family`, `emgai_invite`, `member_m5_test`, `hacker_trying_duplicate`, `thành_viên_mới`, `alias_auth1`, `alias_auth2`, `api_test_member`).
- **Tệp [simulator/data/family_email_allowlist.json](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/data/family_email_allowlist.json)**: Đang chứa 10 bản ghi email test rác (93 dòng).
- Đối chiếu với [simulator/auth/constants_and_crypto.py:50-248](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth/constants_and_crypto.py#L50-L248): Chỉ có đúng 6 tài khoản mặc định chuẩn (`tuan_anh`, `thanh_vien_a`, `thanh_vien_b`, `khach_c`, `senat6031`, `kbanh376`).

---

## 2. Chuỗi Logic Suy Luận (Logic Chain)

1. Từ **Quan sát 1.1**: Hàm `send_real_gmail_otp` và `send_invite_link_via_gmail` thiếu tầng kiểm tra `REAL_EMAIL_ALLOWLIST`. Vì chỉ chặn một số đuôi danh xưng, các email giả lập (`hoc_sinh_moi@gmail.com`, `thanh_vien_chuan@gmail.com`...) không bị chặn, dẫn đến gửi SMTP/gws thật ra ngoài và bị nhà mạng báo lỗi bounce mail.  
   $\rightarrow$ **Kết luận 1**: Cần cài đặt hệ thống bảo vệ 3 tầng (3-tier protection), với Tầng 1 là Canonical Allowlist Engine và Tầng 2 là Dispatch Gate chặn gửi ngay lập tức trước khi chạm vào giao thức mạng, trả về `sent_real_gmail: False, blocked_by_allowlist: True` sạch sẽ, không bounce.

2. Từ **Quan sát 1.2**: Trang chủ `/` khi nhấn nút `#btnSubmitGateLogin` chỉ nhằm xác thực mật khẩu Lớp 1 để mở màn hình điều khiển. Nhưng vì payload thiếu `send_gmail: false` và backend mặc định `True`, mỗi lần đăng nhập hợp lệ tại Trang Chủ đều bị kích hoạt gửi mail thật. Điều này khiến Playwright 3-roles test flows (Quan sát 1.2) gửi mail thật mỗi lần chạy test.  
   $\rightarrow$ **Kết luận 2**: Phải bổ sung `"send_gmail": false` vào body của fetch gọi `/api/auth3/layer1_login` trong [simulator/static/js/app.js](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/static/js/app.js) và [simulator/static/js/auth.js](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/static/js/auth.js).

3. Từ **Quan sát 1.3**: Vì `tests/conftest.py` chưa có, việc cô lập kiểm thử chưa được tự động hóa. Nếu một test case mới được bổ sung mà quên mock thủ công, thư thật sẽ rò rỉ.  
   $\rightarrow$ **Kết luận 3**: Cần khởi tạo [tests/conftest.py](file:///C:/Users/LENOVO/datn-wt/p6-otp/tests/conftest.py) với fixture `@pytest.fixture(autouse=True)` mock toàn diện `smtplib.SMTP`, `smtplib.SMTP_SSL` và `subprocess.run(gws...)`.

4. Từ **Quan sát 1.4**: Các ca test trước đây đã lưu trực tiếp vào `simulator/data/accounts_3layer.json` và `simulator/data/family_email_allowlist.json` khiến dữ liệu mặc định bị ô nhiễm nghiêm trọng (18 tài khoản thay vì 6 tài khoản).  
   $\rightarrow$ **Kết luận 4**: Cần làm sạch triệt để hai tệp dữ liệu này, đưa `accounts_3layer.json` về đúng 6 tài khoản mẫu chuẩn và `family_email_allowlist.json` về `{}`.

---

## 3. Vùng Chưa Khảo Sát & Giả Định (Caveats)

- **Vùng chưa khảo sát:** Các tệp kiểm thử tải nặng e2e trong `tests/random_flow_20261103/` chưa được duyệt từng dòng, tuy nhiên chúng kế thừa conftest toàn cục nên sẽ được hưởng lợi trực tiếp từ fixture cách ly mới.
- **Giả định:** Biến môi trường `REAL_EMAIL_ALLOWLIST` nếu có sẽ là chuỗi phân tách bởi dấu phẩy, chấm phẩy hoặc khoảng trắng.
- **Không có giả định ẩn nào khác.**

---

## 4. Đánh Giá & Kết Luận (Conclusion)

Yêu cầu R1 đã được khảo sát tường tận 100% về mã nguồn, điểm nghẽn, và cách thức vận hành. Phương án triển khai rõ ràng, có tính khả thi cao và hoàn toàn giải quyết triệt để vấn đề rò rỉ email thật:

1. **Thêm Allowlist Engine**: Hằng số `HARDCODED_REAL_EMAIL_ALLOWLIST` gồm `nep94121@gmail.com`, `senat6031@gmail.com`, `kbanh376@gmail.com` kết hợp với biến môi trường `REAL_EMAIL_ALLOWLIST`.
2. **Cài Đặt Cổng Chặn Không Bounce**: Tại `send_real_gmail_otp` và `send_invite_link_via_gmail`, từ chối ngay lập tức mọi email không thuộc allowlist, trả về trạng thái chặn an toàn.
3. **Thiết Lập Fixture Cách Ly Toàn Cục**: Tạo `tests/conftest.py` với `autouse=True` mock toàn bộ `smtplib` và `gws`.
4. **Sửa Giao Diện Login Gate**: Cập nhật `app.js` gửi `send_gmail: false` trong `#btnSubmitGateLogin`.
5. **Thanh Lọc Dữ Liệu Demo**: Khôi phục `accounts_3layer.json` về đúng 6 tài khoản và `family_email_allowlist.json` về `{}`.

---

## 5. Phương Pháp Kiểm Chứng Độc Lập (Verification Method)

Khi đội triển khai thực hiện xong, người kiểm thử có thể kiểm chứng độc lập bằng các bước sau:

1. **Kiểm chứng Cổng Chặn Allowlist (Không bounce):**
   Gọi API gửi OTP với email không thuộc allowlist (ví dụ `thanh_vien_chuan@gmail.com`):
   ```python
   # Kỳ vọng: sent_real_gmail: False, blocked_by_allowlist: True, không gọi SMTP/gws
   res = client.post("/api/auth3/forgot_password_send_otp", json={"email": "thanh_vien_chuan@gmail.com", "send_gmail": True})
   assert res.json().get("gmail_delivery", {}).get("sent_real_gmail") is False
   assert res.json().get("gmail_delivery", {}).get("blocked_by_allowlist") is True
   ```
2. **Kiểm chứng Fixture Cách Ly Pytest:**
   Chạy toàn bộ test suite không có kết nối internet hoặc không có mật khẩu SMTP:
   ```powershell
   pytest tests/test_phase5_r3_otp_email.py tests/test_challenger_phase5_r2_r3.py -v
   ```
   Tất cả các ca test phải xanh 100% và không có bất kỳ email nào lọt ra ngoài.
3. **Kiểm chứng Login Gate Không Gửi Mail Thật:**
   Chạy test luồng Playwright:
   ```powershell
   pytest tests/test_playwright_3roles_live.py -v
   ```
   Kiểm tra log của backend: không có sự kiện `send_real_gmail` nào được kích hoạt từ `#btnSubmitGateLogin`.
4. **Kiểm chứng Dữ Liệu Sạch:**
   Kiểm tra số lượng bản ghi trong JSON:
   - `accounts_3layer.json` phải có đúng 6 bản ghi (`len(data) == 6`).
   - `family_email_allowlist.json` phải rỗng (`data == {}`).

---
*Báo cáo được hoàn thiện và ký xác nhận bởi Explorer 1.*
