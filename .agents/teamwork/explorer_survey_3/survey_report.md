# Báo Cáo Khảo Sát Kỹ Thuật: Yêu Cầu R3 — Tiêu Chuẩn Email RFC 5322 và Khả Năng Chuyển Phát (Deliverability)

**Tác giả:** Explorer 3 (`survey_exp3`) — Archetype: `teamwork_explorer`  
**Dự án:** Smart Home Voice AI (DATN SEEE - HUST)  
**Mục tiêu:** Phân tích mã nguồn gửi/nhận email OTP qua Gmail/SMTP, rà soát tính tuân thủ chuẩn RFC 5322, ngăn chặn bộ lọc spam Gmail, cải tiến hàm trích xuất OTP từ hộp thư `read_latest_otp_from_gmail_inbox`, và đề xuất cập nhật bộ kiểm thử TDD.  
**Thời gian hoàn thành:** 2026-11-05  

---

## 1. Tóm Tắt Cốt Lõi (Executive Summary)

Khảo sát hệ thống cho thấy module gửi email hiện tại (`simulator/auth/invite_and_gmail_mixin.py`) đang vi phạm nghiêm trọng các tiêu chuẩn RFC 5322 và các quy tắc phân phối email chống spam (Deliverability & Anti-Phishing Heuristics) của Google Gmail:

1. **Tiêu đề thư (Subject) vi phạm nặng quy tắc chống spam:**
   - Đang chèn trực tiếp mã OTP 6 số vào Subject (`Mã xác nhận OTP: 123456`), vi phạm quy tắc bảo mật và kích hoạt bộ lọc spam (heuristics cảnh báo lừa đảo tài chính/mã số giao dịch).
   - Chứa từ viết hoa toàn bộ (ALL-CAPS): `OTP`, `OAUTH`, `AI` trong tiêu đề thư (bộ lọc SpamAssassin và Gmail gán điểm spam cao cho các token ALL-CAPS).
   - Chứa các ký tự emoji trang trí.
2. **Thiếu hoàn toàn các trường Headers bắt buộc theo chuẩn RFC 5322:**
   - Trường `From` không sử dụng `email.utils.formataddr(('Smart Home Voice AI', sender_addr))`, chỉ để địa chỉ email trần (`nep94121@gmail.com`).
   - Trường `Date` hoàn toàn **vắng bóng** (vi phạm RFC 5322 §3.6.1 bắt buộc mọi thư phải có `Date:` theo định dạng RFC 2822/5322).
   - Trường `Message-ID` hoàn toàn **vắng bóng** (vi phạm RFC 5322 §3.6.4).
   - Trường `Reply-To` không được thiết lập.
3. **Cấu trúc MIME không hoàn chỉnh và giao diện HTML gây kích hoạt cảnh báo lừa đảo (Phishing Warning):**
   - Mặc dù khởi tạo `MIMEMultipart("alternative")`, code hiện tại **chỉ đính kèm duy nhất** `MIMEText(html_body, "html")` mà **không hề có phần `text/plain`** dự phòng (kích hoạt luật `MIME_HTML_ONLY` của các bộ lọc thư rác).
   - Giao diện HTML dùng nền tối đen `#0f172a` với viền neon sáng chói, chèn nhiều biểu tượng cảm xúc (emojis: `🔐`, `🔗`, `🏷️`, `🔑`, `🎙️`, `👉`).
   - Tiêu đề HTML sử dụng thương hiệu Google gây hiểu lầm: `🔐 XÁC NHẬN GOOGLE OAUTH & GMAIL OTP - SMART HOME AI` cùng câu chữ `Tài khoản Google/Gmail`. Khi gửi từ máy chủ ngoài (SMTP tự host), bộ lọc chống lừa đảo giả mạo (Anti-phishing spoofing detector) của Gmail ngay lập tức gắn cờ cảnh báo đỏ "Be careful with this message - This message seems dangerous" hoặc đưa thư thẳng vào hòm Thư rác (Spam/Junk).
4. **Hàm cào hộp thư Gmail `read_latest_otp_from_gmail_inbox` có nguy cơ hỏng hoàn toàn (Fatal Breakdown) khi đổi Subject:**
   - Lệnh tìm kiếm của `gws` đang dùng query cứng: `q: "Smart Home Mã xác nhận OTP"`. Nếu đổi Subject sang định dạng chuẩn mới không có chữ "OTP", lệnh tìm kiếm sẽ **trả về 0 kết quả**.
   - Logic trích xuất chỉ lấy `combined_text = f"{subject} {snippet}"` và match `\b(\d{6})\b`. Trước đây nó trích xuất mã OTP thành công là do **mã OTP nằm ngay trong Subject**. Khi bỏ mã OTP khỏi Subject, và nếu `snippet` bị Gmail cắt ngắn hoặc không chứa mã số, regex sẽ thất bại. Hơn nữa, hàm chưa hề giải mã nội dung multipart từ `payload["parts"]` (base64url data).

---

## 2. Chi Tiết Khảo Sát Cấu Trúc MIME Email Đi (`simulator/auth/invite_and_gmail_mixin.py`)

### 2.1. Vị trí mã nguồn liên quan
- **File:** `simulator/auth/invite_and_gmail_mixin.py`
- **Hàm `send_real_gmail_otp`:** Dòng 578 – 706
- **Hàm `send_invite_link_via_gmail`:** Dòng 503 – 576

### 2.2. Phân tích hiện trạng mã nguồn `send_real_gmail_otp` (Dòng 596–629)

```python
596:         smtp_user = os.environ.get("SMTP_USER", "").strip() or "nep94121@gmail.com"
597:         msg = MIMEMultipart("alternative")
598:         msg["To"] = actual_to
599:         msg["From"] = smtp_user
600:         subject_prefix = "[Smart Home Invite OAuth]" if invite_info else "[Smart Home Voice AI]"
601:         msg["Subject"] = f"{subject_prefix} Mã xác nhận OTP: {otp_code} ({display_name})"
...
616:         html_body = f"""
617:         <div style="font-family:Arial,sans-serif;max-width:540px;margin:0 auto;padding:20px;background:#0f172a;color:#f8fafc;border-radius:14px;border:1px solid #38bdf8;">
618:           <h2 style="color:#38bdf8;margin-top:0;">🔐 XÁC NHẬN GOOGLE OAUTH & GMAIL OTP - SMART HOME AI</h2>
619:           <p>Xin chào <b>{display_name}</b> (Tài khoản Google/Gmail: <code>{recipient}</code>),</p>
620:           {extra_invite_html}
621:           <div style="background:#1e293b;padding:16px;border-radius:10px;text-align:center;margin:18px 0;border:1px solid #10b981;">
622:             <div style="font-size:12px;color:#94a3b8;">MÃ XÁC NHẬN OTP 6 SỐ CỦA BẠN LÀ:</div>
623:             <div id="otp-code-value" style="font-size:32px;font-weight:bold;letter-spacing:6px;color:#10b981;margin-top:6px;">OTP:{otp_code}</div>
624:           </div>
625:           <p style="font-size:12px;color:#94a3b8;">• Mã có hiệu lực trong 5 phút.<br>• Hệ thống Nhà Thông Minh Điều Khiển Bằng Giọng Nói Tiếng Việt (ĐATN SEEE - HUST).</p>
626:         </div>
627:         """
628:         msg.attach(MIMEText(html_body, "html", "utf-8"))
```

### 2.3. Bảng đối chiếu vi phạm tiêu chuẩn (Compliance Gap Analysis)

| Hạng mục | Hiện trạng trong Code | Yêu cầu Chuẩn RFC 5322 & Deliverability | Đánh giá |
| :--- | :--- | :--- | :--- |
| **`From` Header** | `msg["From"] = smtp_user`<br>(ví dụ: `"nep94121@gmail.com"`) | Phải định dạng `formataddr(('Smart Home Voice AI', sender_addr))`<br>(kết quả: `"Smart Home Voice AI" <nep94121@gmail.com>`) | ❌ **Không đạt** |
| **`Date` Header** | Hoàn toàn không có | Phải có `msg["Date"] = email.utils.formatdate(localtime=True)` (RFC 5322 §3.6.1) | ❌ **Thiếu nghiêm trọng** |
| **`Message-ID` Header** | Hoàn toàn không có | Phải có `msg["Message-ID"] = email.utils.make_msgid(domain=...)` (RFC 5322 §3.6.4) | ❌ **Thiếu nghiêm trọng** |
| **`Reply-To` Header** | Hoàn toàn không có | Phải có `msg["Reply-To"] = email.utils.formataddr(('Smart Home Voice AI', smtp_user))` | ❌ **Thiếu** |
| **`To` Header** | `msg["To"] = actual_to` | Khuyên dùng `email.utils.formataddr((display_name, actual_to))` hoặc địa chỉ sạch | ⚠️ **Cần chuẩn hóa** |
| **`Subject` Line** | `[Smart Home ...] Mã xác nhận OTP: {otp_code} ({display_name})` | **TUYỆT ĐỐI KHÔNG** chứa mã OTP, **KHÔNG** chứa từ ALL-CAPS (`OTP`, `AI`, `OAUTH`), **KHÔNG** chứa emoji | ❌ **Vi phạm nặng** |
| **Cấu trúc MIME** | `MIMEMultipart("alternative")` nhưng chỉ attach 1 part HTML | Phải chứa đủ cả 2 part: `text/plain` (đứng trước) và `text/html` (đứng sau) theo RFC 2046 | ❌ **Vi phạm chuẩn MIME** |
| **Nội dung HTML** | Nền tối `#0f172a`, viền dạ quang neon `#38bdf8`, nhiều emoji (`🔐`, `🔗`, `🏷️`, `🔑`, `🎙️`) | Nền sáng (light background: `#ffffff`, `#f8fafc`), viền xám trang nhã `#e2e8f0`, **0 emoji** | ❌ **Vi phạm UI/Deliverability** |
| **Thương hiệu HTML** | `🔐 XÁC NHẬN GOOGLE OAUTH & GMAIL OTP` | **KHÔNG** mạo danh Google OAuth; dùng thương hiệu dịch vụ thực tế `Smart Home Voice - Xác thực tài khoản` | ❌ **Kích hoạt cảnh báo Phishing** |

### 2.4. Phân tích hiện trạng `send_invite_link_via_gmail` (Dòng 515–535)

Tương tự hàm gửi OTP, hàm gửi link mời cũng gặp các lỗi giống hệt:
- Dòng 518: `msg["From"] = "nep94121@gmail.com"` (chuỗi trần, thiếu display name).
- Thiếu `Date`, `Message-ID`, `Reply-To`.
- Dòng 519: `msg["Subject"] = f"[Smart Home Voice AI] Lời mời đăng ký tài khoản..."` (chứa từ ALL-CAPS `AI`).
- Dòng 522–534: Nền tối `#0f172a`, tiêu đề ALL-CAPS, chứa emoji `🔗`, `👉`, không có `text/plain` part.

### 2.5. Đề xuất giải pháp và mã nguồn khuyến nghị (Implementation Recommendations)

#### Module cần import thêm:
```python
import email.utils
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
```

#### Chuẩn hóa Subject Line (Không OTP, Không ALL-CAPS, Không Emoji):
- Cho xác thực tài khoản / Quên mật khẩu / Đăng nhập:
  ```python
  subject = "Smart Home Voice - Mã xác thực tài khoản"
  ```
  *(Các từ "Smart", "Home", "Voice", "Mã" viết hoa chữ cái đầu Title Case; không có từ nào ALL-CAPS; không có mã số OTP; không có emoji).*
- Cho link mời thành viên:
  ```python
  subject = f"Smart Home Voice - Lời mời đăng ký tài khoản Cấp {inv['target_tier']} ({inv['target_role_label']})"
  ```

#### Chuẩn hóa Headers RFC 5322:
```python
sender_name = "Smart Home Voice AI"
domain = smtp_user.split("@")[-1] if "@" in smtp_user else "gmail.com"

msg = MIMEMultipart("alternative")
msg["From"] = email.utils.formataddr((sender_name, smtp_user))
msg["To"] = email.utils.formataddr((display_name or actual_to.split("@")[0], actual_to))
msg["Date"] = email.utils.formatdate(localtime=True)
msg["Message-ID"] = email.utils.make_msgid(domain=domain)
msg["Reply-To"] = email.utils.formataddr((sender_name, smtp_user))
msg["Subject"] = subject
```

#### Chuẩn hóa Cấu trúc Multipart (Plain Text + Light HTML):
```python
# 1. Plain Text Body (Zero Emojis, No Deceptive Branding)
if invite_info or issued_password:
    inv_by = (invite_info or {}).get("issuer_name", "Chủ nhà")
    t_tier = (invite_info or {}).get("target_tier", 2)
    plain_text = (
        f"Xin chào {display_name},\n\n"
        f"Bạn vừa nhận được lời mời tham gia hệ thống Smart Home Voice từ {inv_by}.\n"
        f"Cấp quyền: Tầng {t_tier}\n"
        f"Mật khẩu cấp phát: {issued_password}\n\n"
        f"Mã xác thực của bạn là: {otp_code}\n"
        f"Mã có hiệu lực trong vòng 5 phút.\n\n"
        f"Lưu ý: Sau khi xác thực, hãy vào Trang Đầu đọc câu mẫu để hệ thống lưu giọng nói mẫu.\n\n"
        f"Hệ thống Nhà Thông Minh Điều Khiển Bằng Giọng Nói (ĐATN SEEE - HUST)."
    )
else:
    plain_text = (
        f"Xin chào {display_name},\n\n"
        f"Mã xác thực Smart Home Voice của bạn là: {otp_code}\n"
        f"Mã có hiệu lực trong vòng 5 phút.\n"
        f"Vui lòng không chia sẻ mã này cho bất kỳ ai để bảo mật tài khoản.\n\n"
        f"Hệ thống Nhà Thông Minh Điều Khiển Bằng Giọng Nói (ĐATN SEEE - HUST)."
    )

# 2. Light-background HTML Body (Zero Emojis, Clean CSS, No Deceptive Branding)
extra_invite_html = ""
if invite_info or issued_password:
    inv_by = (invite_info or {}).get("issuer_name", "Chủ nhà")
    t_tier = (invite_info or {}).get("target_tier", 2)
    extra_invite_html = f"""
    <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:14px;margin:16px 0;font-size:13px;color:#0369a1;">
      <div><b>Người mời:</b> {inv_by}</div>
      <div style="margin-top:4px;"><b>Cấp quyền được gán:</b> Tầng {t_tier}</div>
      <div style="margin-top:4px;"><b>Mật khẩu tài khoản:</b> <code style="color:#0284c7;font-weight:bold;font-size:14px;">{issued_password}</code></div>
      <div style="margin-top:8px;font-size:12px;color:#0c4a6e;"><i>Lưu ý: Sau khi xác thực tài khoản và vào Trang Đầu, hãy đọc câu mẫu để lưu giọng nói chủ trên máy chủ.</i></div>
    </div>
    """

html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;margin:0;padding:24px;background-color:#f8fafc;color:#1e293b;">
  <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width:540px;background-color:#ffffff;border:1px solid #e2e8f0;border-radius:12px;padding:32px;box-shadow:0 1px 3px rgba(0,0,0,0.05);" border="0" cellspacing="0" cellpadding="0">
          <tr>
            <td>
              <h2 style="color:#0f172a;font-size:20px;font-weight:700;margin:0 0 4px 0;">Smart Home Voice</h2>
              <div style="color:#64748b;font-size:14px;margin-bottom:20px;">Xác thực tài khoản người dùng</div>
              
              <p style="font-size:14px;line-height:1.6;color:#334155;margin:0 0 16px 0;">Xin chào <b>{display_name}</b>,</p>
              <p style="font-size:14px;line-height:1.6;color:#334155;margin:0 0 16px 0;">Bạn vừa yêu cầu mã xác thực cho tài khoản <code>{recipient}</code> trên hệ thống Smart Home Voice. Vui lòng sử dụng mã bên dưới:</p>
              
              {extra_invite_html}
              
              <div style="background-color:#f1f5f9;border:1px solid #cbd5e1;border-radius:8px;padding:20px;text-align:center;margin:24px 0;">
                <div style="font-size:12px;font-weight:600;letter-spacing:1px;color:#64748b;text-transform:uppercase;">Mã xác thực của bạn</div>
                <div id="otp-code-value" style="font-size:32px;font-weight:700;letter-spacing:6px;color:#0f172a;margin-top:8px;">{otp_code}</div>
              </div>
              
              <p style="font-size:12px;line-height:1.5;color:#64748b;margin:0 0 8px 0;">• Mã có hiệu lực trong vòng 5 phút.<br>• Vui lòng không tiết lộ mã xác thực này cho người khác để bảo vệ an toàn cho ngôi nhà của bạn.</p>
              <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0 16px 0;">
              <div style="font-size:11px;color:#94a3b8;text-align:center;">Hệ thống Nhà Thông Minh Điều Khiển Bằng Giọng Nói Tiếng Việt (ĐATN SEEE - HUST)</div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

# Attach Plain Text trước, HTML sau theo RFC 2046
msg.attach(MIMEText(plain_text, "plain", "utf-8"))
msg.attach(MIMEText(html_body, "html", "utf-8"))
```

---

## 3. Khảo Sát `read_latest_otp_from_gmail_inbox` & Đề Xuất Cải Tiến

### 3.1. Hiện trạng gọi và vị trí mã nguồn
- **File:** `simulator/auth/invite_and_gmail_mixin.py` (Dòng 708 – 773)
- **Điểm gọi trong API:** `simulator/api/routes_auth.py` (Dòng 185 – 190):
  ```python
  @router.post("/api/auth3/read_gmail_otp")
  async def api_auth3_read_gmail_otp(payload: dict[str, Any] | None = None) -> JSONResponse:
      msg_id = str((payload or {}).get("message_id", "")).strip()
      res = get_auth_3layer_manager().read_latest_otp_from_gmail_inbox(message_id=msg_id)
      return JSONResponse(res)
  ```
- **Điểm gọi trong Test Suite:** `simulator/auth/test_suite_mixin.py` (Dòng 46):
  ```python
  inbox_read = self.read_latest_otp_from_gmail_inbox(message_id=msg_id_t1)
  ```

### 3.2. Cơ chế truy vấn Gmail của `read_latest_otp_from_gmail_inbox` (Dòng 710–755)

```python
710:         try:
711:             target_id = message_id.strip()
712:             if not target_id:
713:                 list_params = json.dumps({"userId": "me", "maxResults": 1, "q": "Smart Home Mã xác nhận OTP"})
714:                 proc_list = subprocess.run(
715:                     ["gws", "gmail", "users", "messages", "list", "--params", list_params],
...
732:             get_params = json.dumps({"userId": "me", "id": target_id, "format": "full"})
733:             proc_get = subprocess.run(
734:                 ["gws", "gmail", "users", "messages", "get", "--params", get_params],
...
745:             msg_obj = json.loads(proc_get.stdout[proc_get.stdout.find("{") :])
746:             snippet = str(msg_obj.get("snippet", ""))
747:             headers = msg_obj.get("payload", {}).get("headers", [])
748:             subject = ""
749:             for h in headers:
750:                 if str(h.get("name", "")).lower() == "subject":
751:                     subject = str(h.get("value", ""))
752:                     break
753: 
754:             combined_text = f"{subject} {snippet}"
755:             m = re.search(r"\b(\d{6})\b", combined_text)
```

### 3.3. Điểm yếu và rủi ro hỏng hóc khi triển khai R3 (Breakage Analysis)

1. **Truy vấn tìm kiếm Gmail (`q`) bị đứt gãy:**
   - Dòng 713 đang đặt `q: "Smart Home Mã xác nhận OTP"`.
   - Khi Subject chuyển sang chuẩn RFC mới (`"Smart Home Voice - Mã xác thực tài khoản"`), không còn chữ `"xác nhận"` và chữ `"OTP"`.
   - Kết quả: Lệnh tìm kiếm của `gws` sẽ trả về danh sách rỗng (`[]`), dẫn đến lỗi `"Không tìm thấy message_id trong hộp thư Gmail."`.
2. **Tham số `maxResults: 1` dễ bốc nhầm thư cũ:**
   - Nếu có thư rác hoặc thư thử nghiệm cũ, việc chỉ lấy đúng 1 thư có thể bốc phải thư không chứa OTP mới nhất.
3. **Regex trích xuất OTP phụ thuộc vào Subject cũ:**
   - Trước đây `subject` có dạng: `"... Mã xác nhận OTP: 123456 ..."`. Regex `\b(\d{6})\b` bắt ngay lập tức 6 số từ `subject`.
   - Khi xóa mã OTP khỏi Subject, `combined_text` chỉ còn `snippet`.
   - Trong Gmail API, `snippet` là chuỗi văn bản tóm tắt tự động bị cắt ngắn (khoảng 100 ký tự đầu tiên). Nếu phần đầu chứa các thông tin giới thiệu dài hoặc chữ chào hỏi, mã OTP có thể nằm ngoài phạm vi của `snippet`.
4. **Bỏ quên việc giải mã nội dung MIME Multipart Payload:**
   - Với định dạng `format="full"`, Gmail API trả về toàn bộ cây cấu trúc thư trong `payload["parts"]`.
   - Mỗi part chứa `mimeType` (`text/plain` hoặc `text/html`) và `body["data"]` được mã hóa Base64URL (RFC 4648).
   - Code hiện tại hoàn toàn không đọc hoặc giải mã `payload["parts"]`, bỏ phí 100% dữ liệu thân thư chính thức.

### 3.4. Đề xuất cải tiến toàn diện cho `read_latest_otp_from_gmail_inbox`

#### A. Cải tiến câu lệnh tìm kiếm Gmail (`q`)
Thay thế `q: "Smart Home Mã xác nhận OTP"` bằng truy vấn linh hoạt, bao quát cả Subject mới lẫn cũ:
```python
search_query = 'subject:"Smart Home" (xác thực OR OTP OR verification OR "Mã")'
list_params = json.dumps({"userId": "me", "maxResults": 5, "q": search_query})
```

#### B. Cải tiến logic giải mã MIME Multipart Payload
Viết hàm giải mã đệ quy để gom toàn bộ nội dung từ các parts (`text/plain` và `text/html`):
```python
def _extract_payload_text(payload_dict: dict[str, Any]) -> str:
    """Đệ quy giải mã dữ liệu Base64URL từ tất cả các part MIME của Gmail API."""
    texts: list[str] = []
    
    def _walk(part: dict[str, Any]):
        data = part.get("body", {}).get("data", "")
        if data:
            try:
                # Bù padding Base64 nếu thiếu
                pad = len(data) % 4
                padded_data = data + ("=" * (4 - pad) if pad else "")
                decoded = base64.urlsafe_b64decode(padded_data.encode("ascii")).decode("utf-8", errors="replace")
                texts.append(decoded)
            except Exception:
                pass
        for sub_part in part.get("parts", []):
            _walk(sub_part)
            
    _walk(payload_dict)
    return "\n".join(texts)
```

#### C. Cải tiến Regex trích xuất mã OTP 3 tầng
Thay vì chỉ `\b(\d{6})\b` dễ bắt nhầm năm hoặc mã số khác, dùng 3 tầng ưu tiên:
```python
full_search_text = f"{subject}\n{snippet}\n{body_content}"

# Tầng 1: Match theo ngữ cảnh từ khóa OTP / mã xác thực
m = re.search(r"(?:OTP[:\s-]*|mã[:\s-]*|code[:\s-]*|xác thực[:\s-]*|xác nhận[:\s-]*)\s*(\d{6})\b", full_search_text, re.IGNORECASE)

# Tầng 2: Match theo thuộc tính HTML container id="otp-code-value"
if not m:
    m = re.search(r'id=["\']otp-code-value["\'][^>]*>(?:OTP:)?\s*(\d{6})<', full_search_text, re.IGNORECASE)

# Tầng 3: Dự phòng match 6 chữ số liên tiếp độc lập
if not m:
    m = re.search(r"\b(\d{6})\b", full_search_text)
```

---

## 4. Rà Soát Bộ Kiểm Thử Hiện Có (`tests/test_phase5_r3_otp_email.py` & `test_challenger_phase5_r2_r3.py`)

### 4.1. Khảo sát `tests/test_phase5_r3_otp_email.py`
Tập kiểm thử này có 4 test cases:
1. `test_r3_missing_secret_fails_with_explicit_error_and_no_fake_success`: Kiểm tra trả về 400/503 khi thiếu secret. (Đạt, không bị ảnh hưởng).
2. `test_r3_successful_smtp_dispatch_when_secret_provided` (Dòng 83–106):
   - Hiện chỉ kiểm tra `mock_smtp_cls.called` và `sent_real_gmail: True`.
   - **Lỗ hổng kiểm thử:** Chưa hề inspect đối tượng email `msg` được truyền vào `server.send_message(msg)`. Do đó, hiện tại không có test nào ngăn chặn việc gửi thư thiếu RFC headers hoặc chứa emoji/ALL-CAPS!
3. `test_r3_frontend_js_guards_against_fake_step_transition`: Kiểm tra guard code `sent_real_gmail` trên JS. (Đạt, không bị ảnh hưởng).
4. `test_r3_no_otp_leak_on_wrong_otp_verification`: Kiểm tra không lộ mã đúng khi nhập sai OTP. (Đạt, không bị ảnh hưởng).

### 4.2. Khảo sát `tests/test_challenger_phase5_r2_r3.py` (Section 2)
Tập kiểm thử đối kháng này có 5 test cases chính:
1. `test_r3_adversarial_missing_secret_returns_503_or_400_and_identifies_secret_zero_leaks`: (Đạt, không bị ảnh hưởng).
2. `test_r3_adversarial_nonexistent_and_malformed_email_queries`: (Đạt, không bị ảnh hưởng).
3. `test_r3_wrong_otp_returns_generic_error_without_leaking_correct_otp`: (Đạt, không bị ảnh hưởng).
4. `test_r3_ui_static_guards_prevent_fake_otp_transition`: (Đạt, không bị ảnh hưởng).
5. `test_r3_live_browser_ui_never_shows_otp_sent_on_delivery_failure`: (Đạt, kiểm thử giao diện Playwright).

### 4.3. Rà soát các giả định cũ về Subject / Body
- **Kết quả rà soát:** Cả hai file test trên **KHÔNG CÓ** câu `assert` nào kiểm tra cứng chuỗi Subject cũ (`"Mã xác nhận OTP"`).
- Tuy nhiên, hệ thống đang **thiếu hẳn các test assertions bắt buộc để xác nhận chuẩn RFC 5322**.

### 4.4. Đề xuất cập nhật và bổ sung Test Cases cho Phase 6 R3

#### Đề xuất 1: Cập nhật `test_r3_successful_smtp_dispatch_when_secret_provided` trong `tests/test_phase5_r3_otp_email.py`
Bổ sung kiểm tra trực tiếp đối tượng MIME message:
```python
    # Bổ sung vào test_r3_successful_smtp_dispatch_when_secret_provided:
    assert mock_smtp.send_message.called, "server.send_message chưa được gọi!"
    msg = mock_smtp.send_message.call_args[0][0]

    # 1. Kiểm tra RFC 5322 Headers
    assert "Smart Home Voice AI" in msg["From"] and "<senat6031@gmail.com>" not in msg["From"]
    assert msg["Date"] is not None and len(msg["Date"]) > 5
    assert msg["Message-ID"] is not None and msg["Message-ID"].startswith("<") and msg["Message-ID"].endswith(">")
    assert msg["Reply-To"] is not None and "Smart Home Voice AI" in msg["Reply-To"]

    # 2. Kiểm tra Subject: Không chứa OTP, không ALL-CAPS, không Emoji
    subject = msg["Subject"]
    assert re.search(r"\b\d{6}\b", subject) is None, f"Subject chứa mã OTP: {subject}"
    all_caps_words = [w for w in re.findall(r"\b[A-Z]{2,}\b", subject)]
    assert not all_caps_words, f"Subject chứa từ ALL-CAPS: {all_caps_words} in '{subject}'"
    assert re.search(r"[\U00010000-\U0010ffff]", subject) is None, f"Subject chứa emoji: {subject}"

    # 3. Kiểm tra Multipart Structure
    assert msg.is_multipart(), "Thư phải là MIME multipart/alternative!"
    payload_parts = msg.get_payload()
    assert len(payload_parts) >= 2, "Thư phải có ít nhất 2 part (text/plain và text/html)!"
    
    content_types = [p.get_content_type() for p in payload_parts]
    assert "text/plain" in content_types, "Thiếu part text/plain!"
    assert "text/html" in content_types, "Thiếu part text/html!"

    # 4. Kiểm tra Plain Text & HTML không chứa emoji và không có Google OAuth lừa đảo
    for part in payload_parts:
        body = part.get_payload(decode=True).decode("utf-8", errors="replace")
        assert re.search(r"[\U00010000-\U0010ffff]", body) is None, f"Part {part.get_content_type()} chứa emoji!"
        assert "Google OAuth" not in body, f"Part {part.get_content_type()} chứa deceptive Google OAuth branding!"
```

#### Đề xuất 2: Bổ sung Test trích xuất hộp thư `test_r3_read_latest_otp_from_gmail_inbox_multipart`
Tạo test kiểm thử độc lập cho hàm `read_latest_otp_from_gmail_inbox` với cấu trúc Gmail API Multipart:
- Giả lập `subprocess.run` trả về payload Gmail API chuẩn có cả `text/plain` và `text/html` mã hóa Base64URL.
- Subject không chứa OTP.
- Xác nhận hàm bóc tách chính xác mã OTP 6 số từ thân thư.

---

## 5. Cây Gọi Hàm và Phân Tích Bán Kính Ảnh Hưởng (AST Call-Graph & Blast-Radius)

### 5.1. Cây gọi hàm `send_real_gmail_otp`
```
AuthInviteGmailMixin.send_real_gmail_otp (simulator/auth/invite_and_gmail_mixin.py:578)
  ▲── ThreeLayerAuthManager.layer1_login (simulator/auth_3layer.py:392)
  ▲── ThreeLayerAuthManager.request_password_reset_otp (simulator/auth_3layer.py:560)
  ▲── AuthInviteGmailMixin.start_invite_oauth_registration (simulator/auth/invite_and_gmail_mixin.py:804)
  ▲── AuthQrTotpMixin.send_and_verify_email_otp (simulator/auth/qr_totp_mixin.py:261)
```

### 5.2. Cây gọi hàm `send_invite_link_via_gmail`
```
AuthInviteGmailMixin.send_invite_link_via_gmail (simulator/auth/invite_and_gmail_mixin.py:503)
  ▲── routes_auth.api_auth3_send_invite_email (/api/auth3/send_invite_email) (simulator/api/routes_auth.py:53)
```

### 5.3. Cây gọi hàm `read_latest_otp_from_gmail_inbox`
```
AuthInviteGmailMixin.read_latest_otp_from_gmail_inbox (simulator/auth/invite_and_gmail_mixin.py:708)
  ▲── routes_auth.api_auth3_read_gmail_otp (/api/auth3/read_gmail_otp) (simulator/api/routes_auth.py:189)
  ▲── AuthTestSuiteMixin.run_automated_3layer_test_suite (simulator/auth/test_suite_mixin.py:46)
```

### 5.4. Tương tác đa chiều với các yêu cầu khác (Cross-Requirement Interactions)
- **Tương tác với R1 (Email Allowlist & Test Mocking):**
  - R1 triển khai autouse fixture trong `tests/conftest.py` để mock `smtplib.SMTP` và `gws`.
  - Thay đổi trong R3 về việc thêm headers RFC 5322 (`From`, `Date`, `Message-ID`, `Reply-To`) và multipart payload hoàn toàn tương thích với mock fixture của R1, vì mock fixture chỉ chặn kết nối mạng socket mà vẫn giữ nguyên đối tượng `msg` để các test kiểm tra.
- **Tương tác với R2 (Anti-Double-Send Cooldown & Idempotency):**
  - Khi người dùng gửi OTP nhiều lần trong 60s, R2 trả về trạng thái cooldown/idempotent mà không gửi email mới.
  - R3 đảm bảo rằng mỗi khi email ĐƯỢC PHÉP gửi, email đó đạt 100% chuẩn RFC 5322 và không bị Gmail lọc vào thư rác.
- **Tương tác với R4 (TDD & Single Real Email Verification):**
  - Sau khi toàn bộ test TDD của R1, R2, R3 chuyển sang xanh (Green), hệ thống chỉ gửi duy nhất 1 email thật tới `senat6031@gmail.com`.
  - Nhờ các cải tiến RFC 5322 của R3 (Headers đầy đủ, Subject không chứa OTP/ALL-CAPS/emoji, HTML nền sáng, không mạo danh Google OAuth), bức thư gửi tới `senat6031@gmail.com` sẽ vào thẳng Hộp thư đến (Inbox) thay vì bị đẩy vào Thư rác (Spam).

---

## 6. Kế Hoạch Chuyển Giao và Khuyến Nghị Thực Thi (Actionable Recommendations)

1. **Thứ tự thực thi đề xuất cho Agent Lập Trình (Implementer):**
   - **Bước 1:** Bổ sung các test assertions thất bại (TDD Red) vào `tests/test_phase5_r3_otp_email.py` để kiểm định các headers RFC 5322 và kiểm tra cấu trúc multipart alternative.
   - **Bước 2:** Cập nhật `simulator/auth/invite_and_gmail_mixin.py`:
     * Thêm `email.utils` vào import.
     * Cập nhật `send_real_gmail_otp` và `send_invite_link_via_gmail` với `formataddr`, `formatdate`, `make_msgid`, `Reply-To`.
     * Cập nhật Subject không chứa OTP, không ALL-CAPS, không emoji.
     * Đính kèm cả `text/plain` và `text/html` nền sáng, không có emoji, loại bỏ hoàn toàn branding "Google OAuth".
   - **Bước 3:** Cập nhật `read_latest_otp_from_gmail_inbox`:
     * Nâng cấp query tìm kiếm `q` sang `subject:"Smart Home" (xác thực OR OTP OR verification)`.
     * Bổ sung hàm giải mã payload parts Base64URL.
     * Nâng cấp regex trích xuất OTP 3 tầng.
   - **Bước 4:** Chạy toàn bộ test suite để đạt TDD Green.
   - **Bước 5:** Không được đọc/in ra bất kỳ giá trị mật khẩu SMTP nào.
