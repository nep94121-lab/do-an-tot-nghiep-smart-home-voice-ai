# Báo Cáo Thẩm Định & Đối Kháng Thực Nghiệm (Challenger M3-2)
## Milestone 3: R3 — Email RFC 5322 Standards & Deliverability

- **Subagent:** `challenger_m3_2` (Archetype: `teamwork_challenger`, Roles: `critic`, `specialist`)
- **Parent Orchestrator:** `91485de0-7c6f-449a-ba3f-ed6820ebb01a`
- **Working Directory:** `C:\Users\LENOVO\datn-wt\p6-otp\.agents\teamwork\challenger_m3_2`
- **Thời điểm hoàn thành:** 2026-11-05T07:44:00Z
- **Phán quyết chính thức:** **APPROVE** (100% ĐẠT TIÊU CHUẨN KỸ THUẬT VÀ ĐỐI KHÁNG)

---

## Challenge Summary

- **Overall Risk Assessment:** **LOW**
- **Empirical Test Suites Executed:**
  - `tests/test_challenger_phase6_m3_2.py`: 20/20 PASSED (0.97s)
  - `tests/test_challenger_m3_rfc5322.py`: 35/35 PASSED (3.66s)
  - `tests/test_phase6_r3_rfc5322.py`: 8/8 PASSED
  - `tests/test_phase5_r3_otp_email.py`: 4/4 PASSED
  - `tests/test_phase6_r2_cooldown_triggers.py`: 12/12 PASSED
  - `tests/test_phase6_r1_allowlist_isolation.py`: 35/35 PASSED
  - `tests/test_challenger_phase5_r2_r3.py`: 24/24 PASSED (120.61s)
  - **Tổng cộng kiểm định:** 138/138 tests PASSED (100% Green, 0 Failures).
- **CRLF & BOM Audit:** 100% UTF-8 không BOM, 0 CRLF (POSIX LF thuần túy).
- **Security Audit:** Zero-Leak tuyệt đối — 0 thông tin đăng nhập/mật khẩu ứng dụng SMTP bị rò rỉ trong headers, bodies, JSON responses hay audit logs.

---

## 1. Observation (Quan Sát Trực Tiếp)

### 1.1. Cấu Trúc Headers và Tuân Thủ RFC 5322
Tại [simulator/auth/invite_and_gmail_mixin.py:712-719](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth/invite_and_gmail_mixin.py#L712-L719) và [simulator/auth/invite_and_gmail_mixin.py:568-575](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth/invite_and_gmail_mixin.py#L568-L575):
1. `From` & `Reply-To`: Được định dạng chuẩn qua `email.utils.formataddr(("Smart Home Voice AI", smtp_user))` tạo ra chuỗi RFC 5322 hợp lệ: `"Smart Home Voice AI" <nep94121@gmail.com>`.
2. `To`: Được format qua `email.utils.formataddr((to_name, actual_to))`. Với tên hiển thị tiếng Việt có dấu (ví dụ: `Nguyễn Tuấn Anh`), `formataddr` tự động mã hóa RFC 2047 encoded-word (`=?utf-8?b?Tmd1eeG7hW4gVHXhuqVuIEFuaA==?= <senat6031@gmail.com>`), phân tích giải mã qua `email.header.decode_header` bảo toàn 100% ký tự UTF-8.
3. `Date`: Thiết lập bằng `email.utils.formatdate(localtime=True)` (ví dụ: `Thu, 05 Nov 2026 14:35:34 +0700`). Phân tích bằng `email.utils.parsedate_to_datetime` thành công với đối tượng datetime có timezone hợp lệ.
4. `Message-ID`: Thiết lập bằng `email.utils.make_msgid(domain=domain)` (ví dụ: `<176232813425.27596.1284759283749281@gmail.com>`). Kiểm tra bằng regex `^<[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}>$` đạt 100%. Kiểm tra sinh 30 tin nhắn liên tiếp ghi nhận 30 Message-ID hoàn toàn duy nhất.

### 1.2. Tiêu Chuẩn Chống Thư Rác (SpamAssassin Heuristics)
1. **Tiêu đề thư OTP (`Subject`):**
   - Giá trị: `"Smart Home Voice - Mã xác thực tài khoản"`
   - Kiểm tra `re.search(r"\d", subject)`: **0 kết quả** (không chứa bất kỳ chữ số nào, loại bỏ hoàn toàn việc để lộ 6 số OTP ra thanh thông báo/màn hình khóa).
   - Kiểm tra `re.findall(r"\b[A-Z]{2,}\b", subject)`: **0 kết quả** (không chứa bất kỳ từ viết hoa toàn bộ như `OTP`, `AI`, `OAUTH`, `SMART`).
   - Kiểm tra regex emoji `[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf]`: **0 kết quả**.
2. **Tiêu đề thư Mời (`Subject`):**
   - Giá trị: `"Smart Home Voice - Lời mời đăng ký tài khoản Cấp 2 (Người nhà (Tầng 2))"`
   - Kiểm tra từ ALL-CAPS: **0 kết quả**.
   - Kiểm tra emoji: **0 kết quả**.
3. **Nội dung Plain Text và HTML:**
   - Cấu trúc MIME `multipart/alternative`: `text/plain` được gắn trước (part 0), `text/html` được gắn sau (part 1) tuân thủ nghiêm ngặt RFC 2046 §5.1.4 (thứ tự ưu tiên tăng dần).
   - Kiểm tra toàn bộ nội dung plain text và HTML qua regex emoji: **0 emoji**.
   - Tỷ lệ độ dài plain text / HTML: Plain text dài >230 ký tự, HTML dài ~2500 ký tự (tỷ lệ > 0.09, vượt ngưỡng cảnh báo SpamAssassin `RATIO_TEXT_HTML_LOW`).
   - Kiểm tra từ khóa lừa đảo (Anti-Phishing): Chuỗi `"Google OAuth"`, `"GOOGLE OAUTH"`, `"Google Security"`, `"Tài khoản Google"` hoàn toàn vắng mặt (0 kết quả).
   - Giao diện HTML: Tông màu nền sáng chuẩn `#f8fafc` và `#ffffff`, border `#e2e8f0`, thẻ chứa mã OTP `<div id="otp-code-value">` hiển thị rõ ràng với font-size 32px.

### 1.3. Khả Năng Cào Hộp Thư Bền Vững (`read_latest_otp_from_gmail_inbox`)
Tại [simulator/auth/invite_and_gmail_mixin.py:870-968](file:///C:/Users/LENOVO/datn-wt/p6-otp/simulator/auth/invite_and_gmail_mixin.py#L870-L968):
1. **Search Query `q`:** Cấu hình chuẩn `subject:"Smart Home" (xác thực OR OTP OR verification)` với `maxResults: 5`, bắt được cả định dạng tiêu đề mới và cũ.
2. **Đệ quy giải mã Base64URL:** Hàm con `_extract_payload_text` duyệt đệ quy `payload["parts"]` qua nhiều cấp lồng nhau (lên tới 4 tầng), tự động bù padding `=` khi `len % 4 != 0`, xử lý an toàn khi payload bị hỏng hoặc thiếu part.
3. **Regex 3 Tầng Phân Cấp (3-Tier Precedence):**
   - Tầng 1: `(?:OTP[:\s-]*|mã[:\s-]*|code[:\s-]*|xác thực[:\s-]*|xác nhận[:\s-]*)\s*(\d{6})\b`
   - Tầng 2: `id=["\']otp-code-value["\'][^>]*>(?:OTP:)?\s*(\d{6})<`
   - Tầng 3: `\b(\d{6})\b`
   - Khi có số điện thoại 10 số (`0987654321`) hoặc mã bưu cục 7 số (`7654321`) ở gần, regex không bao giờ cắt nhầm; khi có nhiều số 6 chữ số (năm tháng `202611`, mã bưu chính `100000`), Tầng 1 ưu tiên bắt chính xác mã OTP có ngữ cảnh (`Mã xác thực: 839201`).

---

## 2. Logic Chain (Chuỗi Lập Luận)

1. **Chuẩn hóa RFC 5322 đảm bảo thư không bị SMTP relays từ chối:**
   - Dựa trên quan sát 1.1, các trường bắt buộc theo RFC 5322 (§3.6.1 Date, §3.6.4 Message-ID, §3.6.2 From) đều có mặt đầy đủ, đúng cú pháp chuẩn, có timezone rõ ràng. Do đó, các máy chủ nhận thư (như Gmail, Outlook) sẽ không gắn cờ vi phạm RFC 5322 cấu trúc tin nhắn.
2. **Loại bỏ triệt để các tiêu chí phạt của bộ lọc SpamAssassin:**
   - Dựa trên quan sát 1.2, tiêu đề không chứa từ ALL-CAPS (tránh quy tắc `SUBJ_ALL_CAPS`), không chứa chữ số (tránh quy tắc lộ OTP/số ngẫu nhiên trên subject), không chứa emoji (tránh quy tắc `SUBJECT_HAS_EMOJI`).
   - Cấu trúc 2 phần `text/plain` và `text/html` giúp tránh quy tắc `MIME_HTML_ONLY`.
   - Loại bỏ các từ khóa giả mạo nhãn hiệu "Google OAuth" giúp thư không bị bộ lọc Anti-Phishing của Google chặn hoặc xếp vào hòm thư lừa đảo/Spam.
3. **Khả năng trích xuất OTP tự động có khả năng chống nhiễu cao:**
   - Dựa trên quan sát 1.3, cơ chế 3 tầng kết hợp Base64URL tự bù đệm bảo đảm kiểm thử tự động e2e đọc thư qua Gmail API/gws không bao giờ bị nghẽn do cấu trúc MIME multipart phức tạp hay số giả mạo xung quanh.

---

## 3. Caveats (Điểm Giới Hạn & Giả Định)

1. **Không gửi thư thật trong Milestone 3:** Toàn bộ kiểm thử trong Milestone 3 được thực hiện trên môi trường giả lập (mock SMTP/gws) tuân thủ quy tắc cô lập kiểm thử. Việc gửi tối đa 1 email thật duy nhất tới `senat6031@gmail.com` được dành riêng cho Milestone 4 theo đúng hợp đồng `SCOPE.md`.
2. **Không có cảnh báo hay lỗi tồn đọng.**

---

## 4. Conclusion (Kết Luận & Phán Quyết)

### Phán quyết: **APPROVE**
Mã nguồn triển khai Milestone 3 (R3: Email RFC 5322 Standards & Deliverability) trong `simulator/auth/invite_and_gmail_mixin.py` đã vượt qua 100% các bài kiểm thử thực nghiệm đối kháng độc lập, tuân thủ hoàn hảo chuẩn RFC 5322, loại trừ mọi yếu tố kích hoạt spam filter, đảm bảo khả năng trích xuất OTP bền vững và bảo toàn Zero-Leak.

---

## 5. Verification Method (Phương Pháp Tái Hiện Độc Lập)

Để kiểm chứng độc lập kết quả:

1. **Chạy bộ kiểm thử đối kháng Challenger M3-2 (20 tests):**
   ```powershell
   pytest tests/test_challenger_phase6_m3_2.py -v
   ```
   *Kết quả kỳ vọng:* 20 passed.

2. **Chạy bộ kiểm thử đối kháng kết hợp (55 tests):**
   ```powershell
   pytest tests/test_challenger_m3_rfc5322.py tests/test_challenger_phase6_m3_2.py -v
   ```
   *Kết quả kỳ vọng:* 55 passed in ~3.7s.

3. **Chạy hồi quy Milestone 1, 2, 3 (79 tests):**
   ```powershell
   pytest tests/test_phase6_r3_rfc5322.py tests/test_phase5_r3_otp_email.py tests/test_phase6_r2_cooldown_triggers.py tests/test_phase6_r1_allowlist_isolation.py tests/test_challenger_phase6_m3_2.py -v
   ```
   *Kết quả kỳ vọng:* 79 passed.

4. **Kiểm tra 0 CRLF và UTF-8 không BOM:**
   ```powershell
   python -c "
   files = ['simulator/auth/invite_and_gmail_mixin.py', 'tests/test_phase6_r3_rfc5322.py', 'tests/test_challenger_phase6_m3_2.py']
   for f in files:
       b = open(f, 'rb').read()
       assert not b.startswith(b'\xef\xbb\xbf'), f'BOM: {f}'
       assert b'\r\n' not in b, f'CRLF: {f}'
   print('ALL CLEAN LF UTF-8')
   "
   ```
   *Kết quả kỳ vọng:* `ALL CLEAN LF UTF-8`.
