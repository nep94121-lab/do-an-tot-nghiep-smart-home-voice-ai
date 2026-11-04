# BÁO CÁO BÀN GIAO TRIỂN KHAI: MILESTONE M12 — SESSION-BASED RBAC SECURITY & CONCURRENT SESSION TESTS (REQUIREMENT R2)

- **Người thực hiện**: `teamwork_worker` (Milestone M12 Worker)
- **Parent Agent ID**: `39d935a1-0551-429d-ac45-c89f1e361ad0`
- **Thời gian**: 2026-11-04T15:53:00Z
- **Loại bàn giao**: Hard Handoff (Nhiệm vụ hoàn thành 100%, sẵn sàng cho Forensic Auditor kiểm định độc lập)

---

## 1. Observation (Quan sát thực nghiệm & Bằng chứng mã nguồn)

1. **Khảo sát ban đầu**:
   - Tệp `simulator/api/routes_devices.py` (dòng 124–128 cũ) đọc trực tiếp biến Singleton:
     ```python
     session_tier = int(_REST_ENGINE.current_tier)
     session_user = _REST_ENGINE.get_current_user_name()
     res = await _REST_ENGINE.execute_device_action(dev_id, act, source=source, bypass_rbac=False)
     ```
   - Tệp `simulator/api/routes_auth.py` (dòng 546–548 & 578–580 cũ) khi có người dùng đăng nhập HTTP đã gọi tác dụng phụ toàn cục:
     ```python
     _REST_ENGINE.set_active_user(active_uid)
     await broadcast_rest_state_to_bridges()
     ```
     dẫn tới hiện tượng rò rỉ và xung đột quyền nghiêm trọng khi có nhiều người dùng đồng thời gửi request.

2. **Các tệp thuộc phạm vi sở hữu độc quyền đã tạo mới và chỉnh sửa**:
   - `simulator/auth/session_store.py` (Tạo mới): 258 dòng, triển khai `UserSession`, `SessionStore` (bộ nhớ đệm thread-safe `threading.RLock` + bảng SQLite `user_sessions`), nạp sẵn 3 phiên định danh (`sess_owner_t1_nep94121`, `sess_family_t2_member_a`, `sess_guest_t3_visitor_c`), hàm phân giải `resolve_request_session` đa kênh.
   - `simulator/rule_engine.py` (Chỉnh sửa):
     - Hàm `execute_device_action` nhận thêm `request_tier: int | None = None`, `request_user_name: str | None = None`, `request_role: str | None = None`. Khi truyền vào, RBAC tính toán trên `effective_tier = request_tier`, không đọc hay ghi đè `self.current_tier`.
     - Bổ sung `check_device_permission(self, dev_id: str, action: str | None = None, actor_tier: int | None = None, actor_user_id: str | None = None)` và `_check_custom_directive_device_lock_parameterized(self, dev_id: str, tier: int)` để kiểm tra quyền và chỉ thị khóa của Admin theo tier truyền vào trực tiếp.
     - `set_active_user` và `factory_reset` quản lý cờ tương thích `_explicit_test_user_set`.
   - `simulator/api/routes_devices.py` (Chỉnh sửa):
     - `api_control_device`, `api_control_device_by_path`, `api_mobile_schedule`, `api_text_command` sử dụng `resolve_request_session(request, payload=body, engine=_REST_ENGINE)` để trích xuất quyền stateless theo từng request.
     - Truyền `request_tier=session.tier`, `request_user_name=session.display_name`, `request_role=session.role` vào `execute_device_action`.
     - Trả về HTTP 403 Forbidden khi bị chặn bởi RBAC (`ok: False, rbac_blocked: True`) đối với client session hiện đại.
   - `simulator/api/routes_auth.py` (Chỉnh sửa):
     - Tại `api_auth3_layer1_login` và `api_auth3_layer2_verify_otp`: Khi xác thực thành công, sinh `session_token` mới qua `SessionStore.create_session`, trả về trong JSON (`session_token`, `session`) và `Set-Cookie: sh_session_token=...; Path=/; HttpOnly; SameSite=Lax`.
     - Xóa bỏ hoàn toàn lệnh `_REST_ENGINE.set_active_user(active_uid)` để tránh làm ô nhiễm trạng thái toàn cục của engine.
   - `tests/test_p3_session_rbac_concurrency.py` (Tạo mới): 348 dòng, 10 bài test tự động bao quát toàn diện:
     - Khởi tạo seed sessions định danh.
     - Trích xuất phiên qua 4 kênh: Authorization Bearer, X-Session-Token, Cookie `sh_session_token`, Query param `?token=...`.
     - Yêu cầu không xác thực (unauthenticated) tự động rơi vào Tầng 3 và bị chặn mở cửa chính (HTTP 403).
     - **Stress test 120 requests đan xen ngẫu nhiên giữa 3 vai trò (Owner, Member, Guest) trên 16 worker threads song song**: 100% Owner door/alarm thành công (200 OK); 100% Member/Guest door bị chặn (403 Forbidden); 100% Member AC/Light thành công (200 OK); 100% Guest schedule bị chặn (403 Forbidden); 0% rò rỉ quyền hay lẫn trạng thái.
     - Kiểm tra đăng nhập stateless không làm thay đổi biến engine toàn cục.
     - Thu hồi phiên (revoke) và hết hạn phiên (expiration cleanup).

3. **Bằng chứng tuân thủ chuẩn định dạng & toàn vẹn**:
   - `simulator/auth/session_store.py`: BOM=False, CRLF=False.
   - `simulator/api/routes_devices.py`: BOM=False, CRLF=False.
   - `simulator/rule_engine.py`: BOM=False, CRLF=False.
   - `simulator/api/routes_auth.py`: BOM=False, CRLF=False.
   - `tests/test_p3_session_rbac_concurrency.py`: BOM=False, CRLF=False.
   - Không can thiệp hay sửa đổi `vercel.json`, `server.py`, hoặc các file Android.

---

## 2. Logic Chain (Chuỗi suy luận giải pháp)

1. **Từ Quan sát 1 (Singleton race condition)**:
   - Khi 2 người dùng đồng thời gửi request tới backend, việc phụ thuộc vào `_REST_ENGINE.current_tier` tạo ra điều kiện tương tranh (Race Condition): nếu Khách đăng nhập ngay trước khi Chủ nhà gửi lệnh, lệnh của Chủ nhà bị từ chối DoS; ngược lại nếu Khách gửi lệnh sau khi Chủ nhà login, Khách có thể leo thang đặc quyền.
2. **Từ Thiết kế Stateless Session (Mục 1 & 2)**:
   - `SessionStore` duy trì liên kết an toàn giữa `session_token` ngẫu nhiên bảo mật cao (`secrets.token_urlsafe(24)`) với `{ user_id, email, display_name, tier, role, expires_at }`.
   - `resolve_request_session` trích xuất thông tin người dùng từ chính request hiện tại theo thứ tự ưu tiên: Header Authorization Bearer -> Header X-Session-Token -> Cookie `sh_session_token` -> Query `token` -> Body `session_token` -> Legacy cookie `sh_session_tier`.
   - Khi request không cung cấp thông tin xác thực, nó được gán mặc định phiên Khách (Tier 3, `is_authenticated=False`).
3. **Từ Tham số hóa RuleEngine (Mục 2)**:
   - `execute_device_action` nhận `request_tier` và truyền trực tiếp xuống `check_device_permission(..., actor_tier=effective_tier)` cũng như gói tin MQTT `publish_actuate_command(..., tier=effective_tier)`.
   - Toàn bộ chu trình kiểm tra và thực thi lệnh không phụ thuộc và không làm thay đổi `_REST_ENGINE.current_tier`.
4. **Từ Kiểm định Thực nghiệm (Mục 1.2)**:
   - 120 requests đồng thời chạy trên 16 luồng song song đan xen ngẫu nhiên chứng minh rằng mỗi luồng thực thi độc lập 100%, không xảy ra bất kỳ sự rò rỉ hay ô nhiễm quyền giữa các phiên.
   - Toàn bộ các bài test cũ (`test_phase1_bugfixes_20261104.py`, `test_challenger_m4_security.py`) tiếp tục pass 100% nhờ cơ chế fallback tương thích ngược.

---

## 3. Caveats (Khu vực Lưu ý)

1. **WebSocket Gemini Live Bridge**: Kết nối WebSocket `/ws` duy trì một session bridge âm thanh thời gian thực kéo dài (`LiveBridgeSession`). Các lệnh thoại qua bridge này gán vai trò riêng của bridge đó và hoàn toàn tách biệt với các request HTTP REST API.
2. **Phiên hết hạn**: SQLite `user_sessions` lưu trữ mốc `expires_at`. Phương thức `cleanup_expired()` được cung cấp để dọn dẹp định kỳ các bản ghi đã hết hạn.

---

## 4. Conclusion (Kết luận Đánh giá)

- Toàn bộ yêu cầu của Milestone M12 (Requirement R2) đã được hoàn thành trọn vẹn, chân thực, không có facade hay hardcode:
  1. Module `simulator/auth/session_store.py` hoạt động thread-safe, đồng bộ SQLite WAL và memory cache.
  2. Phân giải phiên đa kênh stateless hoạt động chính xác.
  3. `RuleEngine` và `routes_devices.py` tham số hóa hoàn toàn theo request session, phản hồi HTTP 403 khi bị chặn quyền.
  4. `routes_auth.py` cấp phát session token và cookie an toàn, không ghi đè `_REST_ENGINE` khi đăng nhập.
  5. Bộ kiểm thử tự động `tests/test_p3_session_rbac_concurrency.py` chứng minh độ cô lập tuyệt đối của 120 requests đồng thời giữa 3 vai trò.
  6. 100% test suite chỉ định (64/64 tests) đạt kết quả PASS trong 33.67 giây.

---

## 5. Verification Method (Phương pháp Kiểm chứng Độc lập cho Auditor)

Kiểm định viên độc lập (Forensic Auditor / Reviewer) có thể tái hiện và kiểm chứng toàn diện kết quả bằng các bước sau:

1. **Chạy bộ kiểm thử xác minh chính thức**:
   ```powershell
   python -X utf8 -m pytest tests/test_p3_session_rbac_concurrency.py tests/test_phase1_bugfixes_20261104.py tests/test_challenger_m4_security.py --basetemp=.pytest_tmp
   python -c "import shutil; shutil.rmtree('.pytest_tmp', ignore_errors=True)"
   ```
   *Kết quả mong đợi*: 64 passed, 0 failed.

2. **Chạy riêng biệt bộ kiểm thử đồng thời 120 requests**:
   ```powershell
   python -X utf8 -m pytest tests/test_p3_session_rbac_concurrency.py -v --basetemp=.pytest_tmp
   python -c "import shutil; shutil.rmtree('.pytest_tmp', ignore_errors=True)"
   ```
   *Kết quả mong đợi*: 10 passed, 0 failed.

3. **Kiểm tra định dạng UTF-8 không BOM và 0 CRLF**:
   ```powershell
   python -c "
   files = ['simulator/auth/session_store.py', 'simulator/api/routes_devices.py', 'simulator/rule_engine.py', 'simulator/api/routes_auth.py', 'tests/test_p3_session_rbac_concurrency.py']
   for f in files:
       b = open(f, 'rb').read()
       assert not b.startswith(b'\xef\xbb\xbf'), f'BOM found in {f}'
       assert b'\r\n' not in b, f'CRLF found in {f}'
       print(f'OK: {f}')
   "
   ```
   *Kết quả mong đợi*: Cả 5 tệp đều in ra `OK`.
