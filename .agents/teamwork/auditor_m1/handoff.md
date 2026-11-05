# Forensic Audit Report — Milestone 1 (R1 Email Allowlist & Test Isolation)

**Work Product**: Milestone 1 Implementation (`simulator/auth/invite_and_gmail_mixin.py`, `tests/conftest.py`, `simulator/static/js/app.js`, `simulator/data/accounts_3layer.json`, `simulator/data/family_email_allowlist.json`, `tests/test_phase6_r1_allowlist_isolation.py`)  
**Profile**: General Project (Forensic Integrity)  
**Integrity Mode**: Development Mode (as specified in `ORIGINAL_REQUEST.md`)  
**Auditor**: Forensic Auditor M1 (`auditor_m1` - `teamwork_auditor`)  
**Timestamp**: 2026-11-05T06:08:00Z  
**Verdict**: **CLEAN**

---

## 1. Quan Sát Thực Tế (Observation)

### 1.1. Phân Tích Tĩnh Mã Nguồn (Static Code & AST Analysis)
1. **Kiểm tra AST & Caller-Inspection:**
   - Trong `simulator/auth/invite_and_gmail_mixin.py`:
     - AST parser kiểm tra toàn bộ cây cú pháp không phát hiện bất kỳ lệnh can thiệp kiểm tra stack hoặc caller nào (`_getframe`, `currentframe`, `inspect.stack`, `caller`, `pytest`).
     - `HARDCODED_REAL_EMAIL_ALLOWLIST` (dòng 25–29):
       ```python
       HARDCODED_REAL_EMAIL_ALLOWLIST: set[str] = {
           "nep94121@gmail.com",
           "senat6031@gmail.com",
           "kbanh376@gmail.com",
       }
       ```
     - Hàm `is_email_allowlisted_for_real_send` (dòng 32–46):
       - Chuẩn hóa đầu vào: `clean = email.strip().lower()`, kiểm tra type và ký tự `@`.
       - Mở rộng qua biến môi trường: `re.split(r"[,;:\s]+", env_val)`.
       - Đối soát thành viên: `return clean in allowlist` (sử dụng cấu trúc dữ liệu `set` với độ phức tạp $O(1)$).
       - Không có code cứng kết quả kiểm thử hay facade return `True` vô điều kiện.

2. **Cổng Chặn Dispatcher Trong Backend:**
   - Trong `send_real_gmail_otp` (dòng 646–664):
     ```python
     recipient = (target_email or "").strip().lower()
     if not is_email_allowlisted_for_real_send(recipient):
         if hasattr(self, "_log_event"):
             self._log_event(
                 layer="Email Allowlist Protection Gate",
                 action="blocked_non_allowlisted_email",
                 email=recipient,
                 status="BLOCKED",
                 detail=f"Chặn gửi thư thật tới '{recipient}' vì không thuộc REAL_EMAIL_ALLOWLIST (Chống bounce mail).",
                 source="EmailProtectionGate",
             )
         return {
             "sent_real_gmail": False,
             "blocked_by_allowlist": True,
             "actual_recipient": recipient,
             "status": "BLOCKED_NOT_ALLOWLISTED",
             "message": f"Địa chỉ '{recipient}' không thuộc danh sách REAL_EMAIL_ALLOWLIST. Chặn gửi an toàn.",
         }
     ```
   - Trong `send_invite_link_via_gmail` (dòng 541–560):
     Tương tự, kiểm tra `if not is_email_allowlisted_for_real_send(to_addr):` ngay đầu hàm, trả về `sent_real_gmail: False, blocked_by_allowlist: True` trước khi gọi `subprocess.run(["gws", ...])`.

3. **Mock Mạng & Cô Lập Kiểm Thử Trong `tests/conftest.py`:**
   - Dòng 25–78: `@pytest.fixture(autouse=True)` `mock_email_and_gws_network_isolation(monkeypatch)`:
     - Intercept `smtplib.SMTP` và `smtplib.SMTP_SSL` qua `MagicMock`.
     - Intercept `subprocess.run` khi câu lệnh chứa chuỗi `"gws"`, trả về mock process với `mock_gws_isolation_msg_id`. Các lệnh hệ thống khác (`git`, `python`...) vẫn chạy qua `orig_subprocess_run`.
     - Được giới hạn hoàn toàn trong phạm vi kiểm thử `tests/` và tự giải phóng sau mỗi test nhờ `pytest.MonkeyPatch`, không rò rỉ vào runtime của production.

4. **Cấu Hình Frontend `simulator/static/js/app.js`:**
   - Dòng 1752–1756:
     ```javascript
     const res = await fetch("/api/auth3/layer1_login", {
       method: "POST",
       headers: { "Content-Type": "application/json" },
       body: JSON.stringify({ email, password, login_method: "password", method: "password", send_gmail: false }),
     });
     ```
     Đã thêm tường minh `"send_gmail": false` vào payload của `#btnSubmitGateLogin`.

### 1.2. Kiểm Tra Rò Rỉ Bí Mật (Secret Protection Verification)
- Quét toàn bộ repository, git diff và tệp báo cáo với `git grep` cho `GMAIL_APP_PASSWORD` và `SMTP_PASSWORD`:
  - Mã nguồn thực thi không chứa bất kỳ secret hay mật khẩu tĩnh nào (chỉ gọi `os.environ.get`).
  - Trong test `tests/test_phase6_r1_allowlist_isolation.py`, chỉ sử dụng chuỗi giả định `"mocked_dummy_password"` và `"mock_dummy_pwd"` qua `monkeypatch.setenv`.
  - Không có bất kỳ mật khẩu thật, App Password 16 ký tự của Google hay token nào bị in, ghi đĩa, ghi log hay đưa vào git.

### 1.3. Kiểm Tra Tính Trong Sạch Của Tệp Dữ Liệu (Clean State Verification)
- `simulator/data/accounts_3layer.json`:
  - Chứa chính xác 6 tài khoản mặc định chuẩn:
    `['tuan_anh', 'thanh_vien_a', 'thanh_vien_b', 'khach_c', 'senat6031', 'kbanh376']`.
  - Không có tài khoản test rác (`test`, `hacker`, `con_yeu`, `emgai`).
- `simulator/data/family_email_allowlist.json`:
  - Chứa đúng một dictionary rỗng: `{}` (kích thước 3 bytes).

### 1.4. Kiểm Chứng Thực Nghiệm & Bẫy Mạng Tripwire (Empirical Tripwire Tests)
1. **Fuzzing & Evasion Testing:**
   - 25 biến thể đầu vào độc hại/tấn công (`nep94121@gmail.com.evil.com`, `attacker@nep94121@gmail.com`, `nep94121+alias@gmail.com`, `nep94121@gmail.com\x00`, `nep94121@gmail.com\r\nBcc:...`, `None`, `[]`, `{}`...) đều bị từ chối 100% (`is_email_allowlisted_for_real_send == False`).
2. **Cài đặt bẫy Tripwire ngoại lệ:**
   - Thay thế trực tiếp `smtplib.SMTP`, `smtplib.SMTP_SSL`, `subprocess.run` (gws) bằng các hàm ném `TripwireException`.
   - Cung cấp sẵn secret trong `os.environ['GMAIL_APP_PASSWORD']`.
   - Thực thi `send_real_gmail_otp` và `send_invite_link_via_gmail` với 4 địa chỉ email ngoài allowlist (`thanh_vien_chuan@gmail.com`, `hoc_sinh_moi@gmail.com`, `tan_binh_gia_dinh@gmail.com`, `evil@hacker.org`).
   - **Kết quả:** `Tripwire traps triggered: 0`. Cả hai hàm đều ngắt ngay tại cổng chặn, không có bất kỳ lệnh mạng nào được kích hoạt.

### 1.5. Kết Quả Kiểm Thử Độc Lập
1. **Bộ kiểm thử Milestone 1 & Phase 5 R3:**
   - Lệnh: `pytest tests/test_phase6_r1_allowlist_isolation.py tests/test_phase5_r3_otp_email.py -v`
   - Kết quả: **39 passed, 3 warnings in 8.87s (Exit Code: 0)**.
2. **Bộ kiểm thử hồi quy Phase 5 Challenger:**
   - Lệnh: `pytest tests/test_challenger_phase5_r2_r3.py -v`
   - Kết quả: **24 passed, 3 warnings in 126.56s (Exit Code: 0)**.

---

## 2. Chuỗi Logic Suy Luận (Logic Chain)

1. **Từ Quan sát 1.1:** Hàm `is_email_allowlisted_for_real_send` được hiện thực bằng logic so khớp chuỗi chuẩn hóa trên cấu trúc `set`, kết hợp regex phân tách biến môi trường `REAL_EMAIL_ALLOWLIST`. AST parser chứng minh không có kiểm tra stack hay facade return giả tạo.  
   $\rightarrow$ Giải pháp kiểm tra danh sách email gửi thật là trung thực và đạt chuẩn kỹ thuật.

2. **Từ Quan sát 1.1 & 1.4:** Cả hai kênh gửi thư (`send_real_gmail_otp` và `send_invite_link_via_gmail`) đều đặt cổng chặn allowlist ngay tại dòng đầu tiên. Thử nghiệm bẫy mạng tripwire chứng minh rằng kể cả khi biến môi trường secret tồn tại, hệ thống vẫn không bao giờ mở socket SMTP hay gọi CLI `gws` cho các email không nằm trong danh sách được phép.  
   $\rightarrow$ Nguy cơ gửi thư ra ngoài gây bounce mail hoặc spam cho các tài khoản không cho phép đã bị triệt tiêu hoàn toàn.

3. **Từ Quan sát 1.1.3 & 1.5.1:** Fixture `mock_email_and_gws_network_isolation` trong `tests/conftest.py` là một autouse fixture chuẩn của pytest. Khi chạy 100% test cases trong dự án, toàn bộ lời gọi SMTP và `gws` đều được hứng trọn vẹn và cô lập, trong khi các lệnh shell khác không bị ảnh hưởng.  
   $\rightarrow$ Yêu cầu cô lập môi trường kiểm thử (Test Isolation) đạt chuẩn 100%.

4. **Từ Quan sát 1.1.4:** Tệp `simulator/static/js/app.js` tại sự kiện `#btnSubmitGateLogin` đã truyền tường minh `"send_gmail": false`.  
   $\rightarrow$ Đăng nhập tại cổng Web (`/`) và các luồng kiểm thử tự động của Playwright không kích hoạt gửi thư thật.

5. **Từ Quan sát 1.2:** Không có bất kỳ credential nào bị rò rỉ trong mã nguồn, tests, nhật ký hay báo cáo.  
   $\rightarrow$ Thỏa mãn triệt để quy tắc bảo mật Zero-Leak.

6. **Từ Quan sát 1.3:** Hai tệp dữ liệu cốt lõi đã được dọn sạch hoàn toàn các bản ghi rác, chỉ lưu trữ 6 tài khoản mẫu chuẩn và một từ điển rỗng cho family allowlist.  
   $\rightarrow$ Trạng thái dữ liệu hệ thống đạt trạng thái Clean State hoàn hảo.

---

## 3. Vùng Chưa Khảo Sát & Giả Định (Caveats)

- **Vùng chưa khảo sát:** Các nút bấm trên giao diện Mobile (`mobile_app.js`) và cơ chế chống gửi đúp (anti-double-send cooldown) thuộc phạm vi của Milestone 2, tuy nhiên backend đã có Allowlist Gate bảo vệ chặn mọi request ngoài danh sách.
- **Giả định:** Người vận hành khi cần thêm email hợp lệ gửi thật qua biến môi trường `REAL_EMAIL_ALLOWLIST` sẽ sử dụng các ký tự phân cách chuẩn (dấu phẩy, chấm phẩy, khoảng trắng).
- **Không có giả định ẩn nào khác.**

---

## 4. Đánh Giá & Kết Luận (Conclusion)

- **Bản đánh giá:** Sản phẩm của Milestone 1 (R1 Email Allowlist & Test Isolation) được thực hiện trung thực, đạt chất lượng cao, không có gian lận kiểm thử, không có mã facade, không rò rỉ secret, và hoàn thành 100% tiêu chí nghiệm thu.
- **Phán quyết cuối cùng (Verdict):** **CLEAN**
- **Khuyến nghị:** Phê duyệt chuyển giao Milestone 1 để dàn dựng tiếp Milestone 2 (Anti-Double-Send Cooldown & Frontend Trigger Fixes).

---

## 5. Phương Pháp Kiểm Chứng Độc Lập (Verification Method)

Người kiểm tra độc lập có thể tái hiện toàn bộ bằng chứng pháp y qua các lệnh sau:

1. **Chạy bộ kiểm thử tự động của Milestone 1:**
   ```powershell
   pytest tests/test_phase6_r1_allowlist_isolation.py tests/test_phase5_r3_otp_email.py -v
   ```
   *Kỳ vọng:* 39 passed, Exit Code: 0.

2. **Chạy kiểm tra tính trong sạch của tệp dữ liệu:**
   ```powershell
   python -c "import json; a=json.load(open('simulator/data/accounts_3layer.json', encoding='utf-8')); f=json.load(open('simulator/data/family_email_allowlist.json', encoding='utf-8')); assert len(a) == 6; assert f == {}; print('CLEAN DATA PASS')"
   ```
   *Kỳ vọng:* In ra `CLEAN DATA PASS`.

3. **Chạy kiểm chứng bẫy mạng Tripwire độc lập:**
   ```powershell
   python -c "import smtplib; from simulator.auth.invite_and_gmail_mixin import AuthInviteGmailMixin; smtplib.SMTP = None; m = AuthInviteGmailMixin(); res = m.send_real_gmail_otp('fake@test.com', '123456', 'Fake'); assert res['sent_real_gmail'] is False and res['blocked_by_allowlist'] is True; print('TRIPWIRE PASS')"
   ```
   *Kỳ vọng:* In ra `TRIPWIRE PASS`.
