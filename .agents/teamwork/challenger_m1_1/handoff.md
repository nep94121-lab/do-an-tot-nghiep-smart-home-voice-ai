# Báo Cáo Thẩm Định & Thách Thức Thực Nghiệm (Challenger Handoff Report)

- **Người thực hiện:** Challenger 1 (`challenger_m1_1` - Archetype: `teamwork_challenger`)
- **Nhiệm vụ:** Thách thức thực nghiệm (Empirical Challenge) Milestone 1: R1 Email Allowlist & Test Isolation
- **Thư mục làm việc:** `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\challenger_m1_1`
- **Tập tin kiểm thử độc lập:** `tests/test_challenger_phase6_m1.py` (109 ca kiểm thử mới)
- **Phán quyết cuối cùng (Verdict):** **APPROVE**

---

## 1. Quan Sát Thực Tế (Observation)

### 1.1. Thách thức các kỹ thuật né tránh (Evasion Payloads) trên Allowlist Engine
Tôi đã thiết kế và thực thi trực tiếp 109 ca kiểm thử thách thức thực nghiệm tại `tests/test_challenger_phase6_m1.py`, bao phủ toàn diện 8 hướng tấn công vượt cổng:

1. **Unicode Lookalikes & Homoglyph Spoofing (24 payloads):**
   - Cyrillic lookalikes: `nep94121@gmаil.com` (\u0430), `nеp94121@gmail.com` (\u0435), `sеnat6031@gmail.com` (\u0435), `senаt6031@gmail.com` (\u0430), `kbanh376@gmаil.com`, `nep94121@gmaіl.com` (\u0456), `nep94121@сom` (\u0441).
   - Greek lookalikes: `senαt6031@gmail.com` (\u03b1), `nep94121@gmαil.com`, `nep94121@gmaιl.com` (\u03b9), `nep94121@gmail.cοm` (\u03bf).
   - Fullwidth characters: `ｎｅｐ94121@gmail.com`, `nep94121@ｇｍａｉｌ.com`, `ｎｅｐ９４１２１＠ｇｍａｉｌ．ｃｏｍ`.
   - Zero-width & invisible characters: `nep\u200b94121@gmail.com`, `nep94121@gmail\u200b.com`, `nep94121\u200c@gmail.com`, `nep94121\u200d@gmail.com`, `nep94121@\ufeffgmail.com`, `\u200enep94121@gmail.com` (LRM), `\u202enep94121@gmail.com` (RLO), `nep94121\u00a0@gmail.com` (NBSP).
   - Accented & Turkish: `nép94121@gmail.com`, `İep94121@gmail.com`.
   - **Kết quả trực tiếp:** 100% (24/24) bị `is_email_allowlisted_for_real_send` từ chối (`False`).

2. **CRLF & Header Injection Payloads (8 payloads):**
   - `nep94121@gmail.com\r\nBcc: evil@attacker.org`, `nep94121@gmail.com\nBcc: evil@attacker.org`, `nep94121@gmail.com\rBcc: evil@attacker.org`, `nep94121@gmail.com\r\nTo: victim@example.com`, `senat6031@gmail.com\r\nSubject: Overwrite`, `kbanh376@gmail.com%0d%0aBcc:evil@attacker.org`, `nep94121@gmail.com%0ABcc:evil@attacker.org`, `nep94121@gmail.com\r\n\r\nDATA INJECTION`.
   - **Kết quả trực tiếp:** 100% (8/8) bị từ chối (`False`).

3. **Subdomain & Domain Hijacking (12 payloads):**
   - `nep94121@sub.gmail.com`, `nep94121@mail.gmail.com`, `nep94121@gmail.com.attacker.com`, `senat6031@gmail.com.evil.org`, `kbanh376@attacker.org`, `nep94121@attacker-gmail.com`, `nep94121@fakegmail.com`, `nep94121@gmail.co`, `nep94121@gmail.company`, `nep94121@gmail.com.br`, `attacker@nep94121@gmail.com`, `nep94121@gmail.com@evil.com`.
   - **Kết quả trực tiếp:** 100% (12/12) bị từ chối (`False`).

4. **Syntax Anomalies, Dots Placement & Incomplete Addresses (12 payloads):**
   - `nep94121@gmail.com.`, `nep94121.@gmail.com`, `.nep94121@gmail.com`, `nep94121..test@gmail.com`, `senat6031@gmail..com`, `senat6031@.gmail.com`, `nep94121@gmail`, `@gmail.com`, `nep94121@`, `nep94121`, `nep94121@@gmail.com`, `nep94121@gmail@com`.
   - **Kết quả trực tiếp:** 100% (12/12) bị từ chối (`False`).

5. **Embedded Null Bytes & ASCII Control Characters (7 payloads):**
   - `nep94121@gmail.com\x00evil@attacker.com`, `evil@attacker.com\x00nep94121@gmail.com`, `nep94121@gmail.com\x00`, `\x00nep94121@gmail.com`, `nep94121\x07@gmail.com`, `nep94121\x1b@gmail.com`, `nep94121\x08@gmail.com`.
   - **Kết quả trực tiếp:** 100% (7/7) bị từ chối (`False`).

6. **Delimiter Injections & Multi-Recipient Payloads (8 payloads):**
   - `nep94121@gmail.com,evil@attacker.com`, `nep94121@gmail.com;evil@attacker.com`, `nep94121@gmail.com evil@attacker.com`, `nep94121@gmail.com\tevil@attacker.com`, `nep94121@gmail.com|evil@attacker.com`, `nep94121@gmail.com/evil@attacker.com`, `nep94121@gmail.com:evil@attacker.com`, `nep94121@gmail.com\nevil@attacker.com`.
   - **Kết quả trực tiếp:** 100% (8/8) bị từ chối (`False`).

7. **RFC Display Names, Quotes, Comments & Subaddressing Tags (10 payloads):**
   - `<nep94121@gmail.com>`, `"nep94121@gmail.com"`, `'nep94121@gmail.com'`, `"Nguyen Tuan Anh" <nep94121@gmail.com>`, `<evil@attacker.com> nep94121@gmail.com`, `nep94121(comment)@gmail.com`, `nep94121@gmail.com(comment)`, `nep94121+tag@gmail.com`, `senat6031+dev@gmail.com`, `kbanh376+backup@gmail.com`.
   - **Kết quả trực tiếp:** 100% (10/10) bị từ chối (`False`).

8. **Type Confusion & Non-String Objects (11 payloads):**
   - `None`, `12345`, `123.456`, `[]`, `["nep94121@gmail.com"]`, `{}`, `{"email": "nep94121@gmail.com"}`, `True`, `False`, `object()`, `b"nep94121@gmail.com"`.
   - **Kết quả trực tiếp:** 100% (11/11) trả về `False` mượt mà, không phát sinh lỗi ngoại lệ `TypeError` hay sập tiến trình.

9. **Case Variations & Surrounding Whitespace Acceptance (9 valid test cases):**
   - `nep94121@gmail.com`, `NEP94121@GMAIL.COM`, `Nep94121@Gmail.Com`, `senat6031@gmail.com`, `SENAT6031@GMAIL.COM`, `kbanh376@gmail.com`, `KBANH376@GMAIL.COM`, `  nep94121@gmail.com  `, `\t\n  senat6031@gmail.com \r\n`.
   - **Kết quả trực tiếp:** 100% (9/9) được chấp thuận (`True`).

### 1.2. Thách thức Dispatcher Airtightness (`send_real_gmail_otp` & `send_invite_link_via_gmail`)
- Tôi đã đưa toàn bộ 81 payloads tấn công nói trên qua hai hàm phát thư:
  - `send_real_gmail_otp`: Cài đặt mock giám sát phát hiện kết nối SMTP và gws. Kết quả: 81/81 payloads đều nhận kết quả `sent_real_gmail = False`, `blocked_by_allowlist = True`. Số lần gọi `smtplib.SMTP` = 0, số lần gọi `gws` = 0.
  - `send_invite_link_via_gmail`: 81/81 payloads đều nhận kết quả `sent_real_gmail = False`, `blocked_by_allowlist = True`. Số lần gọi `gws` = 0.
  - Trường hợp email hợp lệ có khoảng trắng/newline bao quanh (`"\r\n  senat6031@gmail.com \n\t "`): Kiểm tra thuộc tính `msg['To']` gửi vào SMTP server, kết quả là `senat6031@gmail.com`, hoàn toàn sạch sẽ, không có bất kỳ ký tự `\r` hay `\n` nào làm ô nhiễm header RFC 5322.

### 1.3. Thách thức Đồng Thời & Khả Năng Chặn Mạng Của Fixture Cô Lập (`tests/conftest.py`)
- Kích hoạt bài kiểm tra stress đa luồng (`TestIsolationConcurrencyAndEdgeCases.test_concurrent_smtp_and_gws_mocking`):
  - 20 luồng đồng thời chạy song song thực hiện hàng loạt thao tác `smtplib.SMTP`, `smtplib.SMTP_SSL`, gọi `.login()`, `.sendmail()`, dùng context manager và non-context-manager, cùng các biến thể gọi `subprocess.run` (lệnh dạng `list`, lệnh dạng `string` kèm `shell=True`, lệnh dạng `tuple`).
  - Kết quả: 20/20 luồng hoàn thành với 0 lỗi, không xảy ra race condition, deadlock hay rò rỉ socket mạng thật.
  - Kiểm tra lệnh ngoài `gws`: Gọi `subprocess.run([sys.executable, "--version"])` không bị fixture can thiệp nhầm, thực thi lệnh thật trả về đúng phiên bản Python.

### 1.4. Kiểm Tra Tệp Dữ Liệu Seed Accounts & Cổng Đăng Nhập
- `simulator/data/accounts_3layer.json`:
  - Độ dài chính xác: đúng 6 tài khoản (`tuan_anh`, `thanh_vien_a`, `thanh_vien_b`, `khach_c`, `senat6031`, `kbanh376`).
  - Toàn bộ 6 mật khẩu lưu dưới dạng mã băm PBKDF2-HMAC-SHA256 (64 ký tự hex hợp lệ), đối soát khớp 100% với hàm chuẩn `verify_password_hash(hint, pwd_hash)`.
  - Không có bất kỳ tài khoản test/hacker rác nào.
- `simulator/data/family_email_allowlist.json`: Khớp đúng `{}` (dict rỗng).
- `simulator/static/js/app.js`: Tại dòng 1755, sự kiện `#btnSubmitGateLogin` truyền `send_gmail: false` trong payload `layer1_login`.

### 1.5. Kết Quả Chạy Toàn Bộ Test Suites (Full Regression)
Lệnh thực thi:
```powershell
pytest tests/test_phase6_r1_allowlist_isolation.py tests/test_phase5_r3_otp_email.py tests/test_challenger_phase6_m1.py tests/test_challenger_phase5_r2_r3.py -v
```
Kết quả verbatim:
```
================= 172 passed, 3 warnings in 114.42s (0:01:54) =================
Exit Code: 0
```
Chi tiết từng suite:
- `tests/test_phase6_r1_allowlist_isolation.py`: 35/35 PASSED
- `tests/test_phase5_r3_otp_email.py`: 4/4 PASSED
- `tests/test_challenger_phase6_m1.py`: 109/109 PASSED
- `tests/test_challenger_phase5_r2_r3.py`: 24/24 PASSED
Tổng cộng: **172/172 bài test PASSED**.

---

## 2. Chuỗi Logic Suy Luận (Logic Chain)

1. **Từ Quan sát 1.1:** Hàm `is_email_allowlisted_for_real_send` thực hiện chuẩn hóa `email.strip().lower()` rồi so khớp tập hợp `clean in allowlist` (với `allowlist` là `set` các chuỗi cố định).  
   $\rightarrow$ Vì là kiểm tra tập hợp chính xác (`exact set membership`), bất kỳ ký tự Unicode lạ (Cyrillic, Greek, fullwidth, zero-width spaces), phần mở rộng subdomain (`nep94121@sub.gmail.com`), CRLF chèn giữa, hay dấu chấm đuôi nào đều làm chuỗi `clean` khác biệt hoàn toàn với các phần tử trong tập hợp `allowlist`. Do đó, 100% các kỹ thuật evasion đều bị chặn dứt khoát.

2. **Từ Quan sát 1.2:** Tại đầu hàm `send_real_gmail_otp` và `send_invite_link_via_gmail`, cổng Allowlist Gate được đặt ngay dòng đầu tiên trước khi khởi tạo bất kỳ socket `smtplib` hay tiến trình `gws` nào. Khi `is_email_allowlisted_for_real_send` trả về `False`, hàm lập tức ngắt và trả về `sent_real_gmail: False, blocked_by_allowlist: True`.  
   $\rightarrow$ Điều này đảm bảo rằng ngay cả khi có mật khẩu SMTP hợp lệ trong môi trường, không có bất kỳ byte dữ liệu nào bị đẩy ra Internet tới các địa chỉ lạ.

3. **Từ Quan sát 1.3:** Fixture `mock_email_and_gws_network_isolation` trong `tests/conftest.py` mock `smtplib.SMTP`, `smtplib.SMTP_SSL` bằng `MagicMock` và bọc hàm `subprocess.run` kiểm tra chuỗi lệnh chứa `"gws"`.  
   $\rightarrow$ Kiểm thử đa luồng với 20 thread chạy đồng thời chứng minh cấu trúc này thread-safe, không tạo race condition, đồng thời không gây ảnh hưởng đến các lệnh subprocess khác của hệ thống.

4. **Từ Quan sát 1.4:** Tệp `accounts_3layer.json` có đúng 6 tài khoản chuẩn, mật khẩu được mã hóa an toàn bằng PBKDF2-HMAC-SHA256, tệp `family_email_allowlist.json` rỗng, và mã nguồn frontend `app.js` đã được gán cờ `send_gmail: false`.  
   $\rightarrow$ Cả backend, frontend và data fixtures đều đồng bộ tuyệt đối với yêu cầu của Milestone 1.

5. **Từ Quan sát 1.5:** Toàn bộ 172 bài test bao gồm cả các bài test kiểm tra hồi quy khắt khe nhất đều xanh 100%, không có bất kỳ secret nào của SMTP bị in ra hay ghi vào file log/report.  
   $\rightarrow$ Đủ điều kiện phê duyệt hoàn thành Milestone 1.

---

## 3. Vùng Chưa Khảo Sát & Giả Định (Caveats)

- **Vùng chưa khảo sát:** Các luồng kiểm thử giao diện điện thoại di động (Milestone 2) và chuẩn hóa tiêu đề/nội dung email RFC 5322 (Milestone 3). Các nội dung này đã được phân định rõ cho các Milestone tiếp theo.
- **Giả định:** Người dùng và hệ thống vận hành tuân thủ quy tắc bảo mật không commit credentials vào repository.
- **Không có giả định ẩn nào khác.**

---

## 4. Đánh Giá & Phán Quyết (Conclusion & Verdict)

- **Phán quyết:** **APPROVE**
- **Đánh giá tổng thể:**
  - Giải pháp của Worker M1 hoàn toàn kháng cự thành công trước 109 ca tấn công né tránh và chèn tải độc hại.
  - Test Isolation đạt độ tin cậy tuyệt đối, bảo vệ 100% môi trường kiểm thử không bị rò rỉ mail thật ra ngoài.
  - Tệp dữ liệu tài khoản mẫu sạch và chuẩn xác theo cấu trúc 3 tầng.
  - Không có bất kỳ bí mật SMTP nào bị rò rỉ.

---

## 5. Phương Pháp Kiểm Chứng Độc Lập (Verification Method)

Người giám sát có thể độc lập tái lập toàn bộ kết quả kiểm thử bằng các lệnh:

1. **Chạy bộ thử thách thực nghiệm Milestone 1 (109 tests):**
   ```powershell
   pytest tests/test_challenger_phase6_m1.py -v
   ```
   *Kỳ vọng:* 109 passed trong ~2.5s, Exit Code 0.

2. **Chạy toàn bộ 172 tests liên tầng (Milestone 1 + Phase 5 Regression):**
   ```powershell
   pytest tests/test_phase6_r1_allowlist_isolation.py tests/test_phase5_r3_otp_email.py tests/test_challenger_phase6_m1.py tests/test_challenger_phase5_r2_r3.py -v
   ```
   *Kỳ vọng:* 172 passed trong ~115s, Exit Code 0.

3. **Kiểm tra tính toàn vẹn của fixtures:**
   ```powershell
   python -c "import json; a=json.load(open('simulator/data/accounts_3layer.json', encoding='utf-8')); f=json.load(open('simulator/data/family_email_allowlist.json', encoding='utf-8')); assert len(a) == 6; assert f == {}; print('FIXTURES INTEGRITY VERIFIED')"
   ```
   *Kỳ vọng:* In ra `FIXTURES INTEGRITY VERIFIED`.
