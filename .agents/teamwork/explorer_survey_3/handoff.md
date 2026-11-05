# Báo Cáo Bàn Giao (Handoff Report) — Explorer 3: Requirement R3 (RFC 5322 Standards & Deliverability)

**Tác giả:** Explorer 3 (`survey_exp3`) — Archetype: `teamwork_explorer`  
**Đơn vị tiếp nhận:** Orchestrator (`91485de0-7c6f-449a-ba3f-ed6820ebb01a`) & Implementer Agent  
**Đường dẫn file báo cáo chi tiết:** `file:///C:/Users/LENOVO/datn-wt/p6-otp/.agents/teamwork/explorer_survey_3/survey_report.md`  
**Thời gian hoàn thành:** 2026-11-05T05:43:00Z  

---

## 1. Observation (Quan Sát Trực Tiếp)

1. **Cấu trúc MIME và Headers trong `simulator/auth/invite_and_gmail_mixin.py` (Dòng 515–535 và Dòng 596–629):**
   - Dòng 598–601:
     ```python
     msg = MIMEMultipart("alternative")
     msg["To"] = actual_to
     msg["From"] = smtp_user
     subject_prefix = "[Smart Home Invite OAuth]" if invite_info else "[Smart Home Voice AI]"
     msg["Subject"] = f"{subject_prefix} Mã xác nhận OTP: {otp_code} ({display_name})"
     ```
     * Quan sát: `msg["From"]` chỉ gán chuỗi email trần `smtp_user` (`nep94121@gmail.com`), không dùng `email.utils.formataddr(('Smart Home Voice AI', sender_addr))`.
     * Quan sát: Hoàn toàn không có headers `Date`, `Message-ID`, và `Reply-To`.
     * Quan sát: `msg["Subject"]` chứa mã OTP trực tiếp (`{otp_code}`), chứa các từ viết hoa toàn bộ (ALL-CAPS: `OTP`, `AI`, `OAUTH`).
   - Dòng 616–628:
     * Quan sát: Khởi tạo `MIMEMultipart("alternative")` nhưng chỉ attach duy nhất 1 part HTML `msg.attach(MIMEText(html_body, "html", "utf-8"))`, hoàn toàn không có `text/plain` fallback part.
     * Quan sát: `html_body` có nền tối đen `background:#0f172a`, viền dạ quang neon `#38bdf8`, chứa nhiều emoji (`🔐`, `🔗`, `🏷️`, `🔑`, `🎙️`), và tiêu đề mạo danh `🔐 XÁC NHẬN GOOGLE OAUTH & GMAIL OTP - SMART HOME AI` cùng câu chữ `Tài khoản Google/Gmail:`.
   - Dòng 515–534 (`send_invite_link_via_gmail`):
     * Quan sát tương tự: `msg["From"] = "nep94121@gmail.com"`, thiếu `Date`, `Message-ID`, `Reply-To`, Subject chứa từ ALL-CAPS `AI`, chỉ attach HTML nền tối `#0f172a`, chứa emoji `🔗`, `👉`.

2. **Cơ chế truy vấn và bóc tách OTP của `read_latest_otp_from_gmail_inbox` (Dòng 708–773):**
   - Dòng 713:
     ```python
     list_params = json.dumps({"userId": "me", "maxResults": 1, "q": "Smart Home Mã xác nhận OTP"})
     ```
     * Quan sát: Lệnh tìm kiếm của `gws` sử dụng query cứng `"Smart Home Mã xác nhận OTP"`.
   - Dòng 754–757:
     ```python
     combined_text = f"{subject} {snippet}"
     m = re.search(r"\b(\d{6})\b", combined_text)
     if m:
         extracted_otp = m.group(1)
     ```
     * Quan sát: Hàm chỉ nối `subject` và `snippet` để tìm chuỗi 6 số. Trước đây hàm hoạt động được là nhờ mã OTP nằm ngay trong `subject`. Khi bỏ mã OTP khỏi `subject`, nếu `snippet` bị Gmail cắt ngắn hoặc không chứa mã, hàm sẽ báo lỗi không tìm thấy chuỗi 6 số.
     * Quan sát: Hàm không hề duyệt hoặc giải mã cây `payload["parts"]` (dữ liệu Base64URL) của Gmail API `format="full"`.

3. **Hiện trạng các bộ kiểm thử (`tests/test_phase5_r3_otp_email.py` và `tests/test_challenger_phase5_r2_r3.py`):**
   - Chạy lệnh: `python -m pytest tests/test_phase5_r3_otp_email.py -v` $\rightarrow$ 4 passed.
   - Chạy lệnh: `python -m pytest tests/test_challenger_phase5_r2_r3.py -k "TestChallengerR3OtpEmailAdversarial and not test_r3_live_browser_ui_never_shows_otp_sent_on_delivery_failure" -v` $\rightarrow$ 13 passed.
   - Chạy lệnh browser Playwright: `test_r3_live_browser_ui_never_shows_otp_sent_on_delivery_failure` $\rightarrow$ 1 passed.
   - Quan sát trong `tests/test_phase5_r3_otp_email.py`: `test_r3_successful_smtp_dispatch_when_secret_provided` (dòng 83–106) chỉ assert `mock_smtp_cls.called` và `data.get("ok") is True`, hoàn toàn **chưa assert cấu trúc `msg`** (`From`, `Date`, `Message-ID`, `Reply-To`, `Subject` sạch, và 2 part `text/plain` + `text/html`).

---

## 2. Logic Chain (Chuỗi Lập Luận Suy Diễn)

1. **Từ Quan sát 1 $\rightarrow$ Nguy cơ bị Gmail gắn cờ Phishing & Spam:**
   - Việc tiêu đề thư chứa mã xác nhận (`Mã xác nhận OTP: 123456`) cùng các token viết hoa `OTP`, `AI` là đặc điểm nhận diện điển hình của thư rác tự động.
   - Việc thiếu vắng trường `Date` và `Message-ID` vi phạm nghiêm trọng RFC 5322 (§3.6.1 và §3.6.4), khiến thư bị trừ điểm uy tín (reputation score) trên tất cả các mail server hiện đại.
   - Việc thiếu trường `From` định dạng chuẩn theo `formataddr` (`"Smart Home Voice AI" <email>`) khiến trình duyệt thư không thể hiển thị tên người gửi đáng tin cậy.
   - Việc thư là `multipart/alternative` nhưng chỉ có `text/html` mà không có `text/plain` vi phạm RFC 2046 và kích hoạt trực tiếp luật `MIME_HTML_ONLY` của bộ lọc thư rác SpamAssassin/Gmail.
   - Tiêu đề HTML sử dụng từ ngữ thương hiệu Google (`🔐 XÁC NHẬN GOOGLE OAUTH & GMAIL OTP`) khi gửi từ SMTP tự host là nguyên nhân kích hoạt cảnh báo lừa đảo (Anti-Phishing Red Warning) của Google.

2. **Từ Quan sát 2 $\rightarrow$ Nguy cơ sập hàm cào thư `read_latest_otp_from_gmail_inbox`:**
   - Khi sửa Subject để tuân thủ chuẩn RFC và Deliverability (không chứa `OTP`, không chứa `Mã xác nhận OTP`), lệnh tìm kiếm `gws` với query `q: "Smart Home Mã xác nhận OTP"` chắc chắn sẽ trả về 0 kết quả.
   - Nếu Subject không còn mã OTP, logic cũ `f"{subject} {snippet}"` sẽ phụ thuộc 100% vào `snippet`. Do `snippet` chỉ là chuỗi tóm tắt khoảng 100 ký tự đầu tiên của thân thư, nếu thư có đoạn mở đầu dài, mã OTP sẽ bị cắt mất.
   - Do đó, bắt buộc phải cập nhật câu query `q` và viết logic giải mã Base64URL đệ quy từ `payload["parts"]` để lấy toàn bộ nội dung `text/plain` và `text/html`.

3. **Từ Quan sát 3 $\rightarrow$ Nhu cầu bổ sung TDD Red Test Cases:**
   - Vì các bài test hiện tại chưa kiểm tra nội dung của `msg` gửi qua SMTP, nếu không bổ sung các test assertion cho RFC 5322 và Deliverability thì quá trình vá lỗi sẽ không có "lưới an toàn" kiểm thử tự động (TDD).
   - Cần bổ sung các assert vào `test_phase5_r3_otp_email.py` để verify các headers, subject, và 2-part body.

---

## 3. Caveats (Điểm Giới Hạn & Giả Định)

1. **Chế độ Chỉ Đọc (Read-Only):** Agent không được phép chỉnh sửa mã nguồn sản phẩm hay file test; toàn bộ đề xuất mã cụ thể được lưu trong `survey_report.md`.
2. **Không Truy Cập Secret:** Tuyệt đối không đọc, in, hoặc ghi bất kỳ giá trị secret SMTP nào (`GMAIL_APP_PASSWORD`, `SMTP_PASSWORD`).
3. **Môi Trường `gws` CLI:** Trong môi trường test tự động, các lệnh `gws` và `smtplib.SMTP` phải được mock 100% (được bảo vệ bởi fixture autouse của R1). Chỉ khi chạy verification cuối cùng mới sử dụng 1 lần gửi mail thật duy nhất tới `senat6031@gmail.com` (theo R4).

---

## 4. Conclusion (Kết Luận Đánh Giá)

Hạng mục R3 cần được triển khai theo 3 nhóm công việc cụ thể:
1. **Chuẩn hóa MIME Email Đi trong `simulator/auth/invite_and_gmail_mixin.py`:**
   - Import `email.utils`.
   - Cấu hình đầy đủ: `From` (qua `formataddr`), `Date` (qua `formatdate(localtime=True)`), `Message-ID` (qua `make_msgid(domain=...)`), và `Reply-To`.
   - Subject: Đổi thành `"Smart Home Voice - Mã xác thực tài khoản"` (hoặc `"Smart Home Voice - Lời mời đăng ký tài khoản Cấp ..."`), tuyệt đối không chứa OTP, không có từ ALL-CAPS, không có emoji.
   - Body: Gửi chuẩn `multipart/alternative` gồm 2 parts: `text/plain` (0 emoji) và `text/html` (giao diện nền sáng `#ffffff`/`#f8fafc`, 0 emoji, loại bỏ hoàn toàn branding "Google OAuth").
2. **Nâng cấp `read_latest_otp_from_gmail_inbox`:**
   - Nâng cấp câu query `q` sang: `'subject:"Smart Home" (xác thực OR OTP OR verification)'`.
   - Thêm hàm đệ quy giải mã Base64URL từ `payload["parts"]`.
   - Bổ sung regex 3 tầng: Ngữ cảnh từ khóa $\rightarrow$ Container HTML `id="otp-code-value"` $\rightarrow$ Fallback 6 chữ số.
3. **Cập nhật Bộ Kiểm Thử TDD:**
   - Bổ sung kiểm tra cấu trúc MIME và headers vào `test_r3_successful_smtp_dispatch_when_secret_provided` trong `tests/test_phase5_r3_otp_email.py`.
   - Bổ sung test case giải mã multipart cho `read_latest_otp_from_gmail_inbox`.

---

## 5. Remaining Work (Các Bước Tiếp Theo cho Implementer Agent)

1. **Bước 1:** Cập nhật `tests/test_phase5_r3_otp_email.py` thêm các assertion kiểm tra RFC 5322 headers (`From`, `Date`, `Message-ID`, `Reply-To`), Subject không chứa OTP/ALL-CAPS/emoji, và cấu trúc 2 parts `text/plain` + `text/html` (Chạy test để xác nhận TDD Red).
2. **Bước 2:** Chỉnh sửa `simulator/auth/invite_and_gmail_mixin.py` (hàm `send_real_gmail_otp`, `send_invite_link_via_gmail`, và `read_latest_otp_from_gmail_inbox`) theo đúng mã nguồn chi tiết trong Section 2 và Section 3 của `survey_report.md`.
3. **Bước 3:** Chạy lại toàn bộ test suite để xác nhận TDD Green:
   ```powershell
   python -m pytest tests/test_phase5_r3_otp_email.py tests/test_challenger_phase5_r2_r3.py -v
   ```

---

## 6. Verification Method (Phương Pháp Kiểm Chứng Độc Lập)

Để kiểm chứng độc lập các phát hiện và mã nguồn:

1. **Kiểm tra trực tiếp mã nguồn hiện tại:**
   - Mở `simulator/auth/invite_and_gmail_mixin.py` tại dòng 515–535 và 596–629 để xác nhận sự thiếu vắng của `Date`, `Message-ID`, `Reply-To`, và part `text/plain`.
   - Mở `simulator/auth/invite_and_gmail_mixin.py` tại dòng 713 và 754 để xác nhận câu query cứng và logic trích xuất OTP từ Subject.
2. **Chạy các lệnh kiểm thử hiện tại:**
   ```powershell
   python -m pytest tests/test_phase5_r3_otp_email.py -v
   python -m pytest tests/test_challenger_phase5_r2_r3.py -k "TestChallengerR3OtpEmailAdversarial" -v
   ```
3. **Điều kiện bác bỏ (Invalidation Conditions):**
   - Nếu tiêu đề thư được gửi đi vẫn còn chứa chuỗi 6 số OTP hoặc từ ALL-CAPS $\rightarrow$ Bác bỏ.
   - Nếu đối tượng thư không chứa header `Date:` hoặc `Message-ID:` $\rightarrow$ Bác bỏ.
   - Nếu thư không thể đọc được bởi `read_latest_otp_from_gmail_inbox` khi Subject thay đổi $\rightarrow$ Bác bỏ.
