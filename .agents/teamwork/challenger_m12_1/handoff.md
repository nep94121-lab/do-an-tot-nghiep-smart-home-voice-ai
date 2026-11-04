# BÁO CÁO KIỂM ĐỊNH ĐỐI KHÁNG ĐỘC LẬP (ADVERSARIAL CHALLENGE REPORT)
## MILESTONE M12: SESSION-BASED RBAC SECURITY & CONCURRENT SESSION TESTS (REQUIREMENT R2)

- **Người thực hiện**: `teamwork_challenger` (Challenger M12)
- **Parent Agent ID**: `39d935a1-0551-429d-ac45-c89f1e361ad0`
- **Thời gian**: 2026-11-04T16:06:00Z
- **Loại bàn giao**: Hard Handoff (Kiểm thử đối kháng hoàn tất với bằng chứng thực nghiệm độc lập)
- **ĐÁNH GIÁ CHUNG (VERDICT)**: **REJECT** (TỪ CHỐI DUYỆT DO PHÁT HIỆN LỖ HỔNG BẢO MẬT NGHIÊM TRỌNG)

---

## Challenge Summary

- **Overall risk assessment**: **CRITICAL**
- **Điểm mạnh đã xác nhận**:
  - Cơ chế cách ly đa luồng khi chịu tải cao (High Concurrency Hammering) đạt chuẩn: Thử nghiệm độc lập 200 requests đan xen trên 20 worker threads (100 lệnh mở cửa từ Khách xen kẽ 60 lệnh đèn và 40 lệnh cửa từ Chủ nhà) cho kết quả 100% Khách bị chặn HTTP 403, 100% Chủ nhà thực thi thành công HTTP 200, 0% rò rỉ quyền hay lẫn lộn trạng thái Singleton.
  - Xử lý SQL Injection, fuzzing độ dài 5000 ký tự và phiên hết hạn (TTL âm) hoạt động chính xác, không gây lỗi máy chủ HTTP 500.
- **Lỗ hổng nghiêm trọng phát hiện (Critical Flaw)**:
  - **Lỗ hổng leo thang đặc quyền qua giả mạo Cookie (CWE-565 / CWE-287 - RBAC Bypass via Unsigned Legacy Cookie Tampering)** tại `simulator/auth/session_store.py` (dòng 286–295). Bất kỳ kẻ tấn công nào không cần tài khoản, không cần mật khẩu, chỉ cần đính kèm Cookie `sh_session_tier=1` đều được backend tổng hợp quyền Admin (Tầng 1) và mở được cửa chính của ngôi nhà thông minh.

---

## 1. Observation (Quan sát thực nghiệm & Bằng chứng mã nguồn)

1. **Kiểm tra bộ test của Worker**:
   - Lệnh thực thi:
     ```powershell
     python -X utf8 -m pytest tests/test_p3_session_rbac_concurrency.py -v --basetemp=.pytest_tmp
     ```
   - Kết quả: `10 passed, 45 warnings in 21.76s (Exit Code: 0)`.

2. **Phân tích mã nguồn `simulator/auth/session_store.py` (dòng 286–295)**:
   ```python
   # 6. Legacy cookie fallback
   if request is not None and hasattr(request, "cookies"):
       c_tier = request.cookies.get("sh_session_tier")
       c_user = request.cookies.get("sh_session_user")
       if c_tier:
           try:
               tier_int = int(c_tier)
               return store.synthesize_legacy_session(c_user or "user", tier_int)
           except ValueError:
               pass
   ```
   Hàm `synthesize_legacy_session` (dòng 227–240) nhận `tier_int` do client tự gửi lên và trả về một phiên xác thực hợp lệ:
   ```python
   def synthesize_legacy_session(self, user_id: str, tier: int) -> UserSession:
       role_map = {1: "ADMIN", 2: "MEMBER", 3: "CHILD_GUEST"}
       return UserSession(
           session_id="legacy_cookie",
           user_id=user_id,
           tier=int(tier),
           role=role_map.get(int(tier), "CHILD_GUEST"),
           is_authenticated=True,
           ...
       )
   ```

3. **Thực nghiệm khai thác trực tiếp (Empirical Exploit Verification)**:
   - Chạy lệnh gửi request không có token xác thực nhưng kèm cookie giả mạo `sh_session_tier=1`:
     ```powershell
     python -c "from fastapi.testclient import TestClient; from simulator.server import app; c = TestClient(app); r = c.post('/api/device', json={'device_id': 'main_door', 'action': 'open'}, cookies={'sh_session_tier': '1'}); print(r.status_code, r.json())"
     ```
   - Kết quả thu được nguyên văn:
     ```json
     200 {
       "ok": true,
       "results": [{"ok": true, "device_id": "main_door", "device_name": "Cửa chính", "state": "OPEN", "already_in_state": false}],
       "exact_spoken_reply": "Cửa chính đã mở.",
       "tier": 1,
       "user_name": "user",
       "rbac_blocked": false
     }
     ```
   - Kiểm tra tiếp các endpoint khác với cookie `sh_session_tier=1`:
     - `/api/mobile/schedule`: Tạo hẹn giờ thành công (HTTP 200, trong khi Khách Cấp 3 bị cấm hoàn toàn).
     - `/api/text_command`: Khẩu lệnh "Mở cửa chính" được thực thi thành công dưới quyền Cấp 1 (HTTP 200).

4. **Kiểm tra bộ test độc lập `tests/test_p3_challenger_m12_adversarial.py`**:
   - Khi chạy test `test_adversarial_cookie_tampering_sh_session_tier_forgery`:
     ```
     FAILED tests/test_p3_challenger_m12_adversarial.py::test_adversarial_cookie_tampering_sh_session_tier_forgery
     AssertionError: LỖ HỔNG BẢO MẬT NGHIÊM TRỌNG (RBAC Bypass via Cookie Tampering tại /api/device): Kẻ tấn công không đăng nhập gửi cookie sh_session_tier=1 đã mở được cửa chính! Status: 200, Body: {'ok': True, 'results': [{'ok': True, 'device_id': 'main_door', 'device_name': 'Cửa chính', 'state': 'OPEN', 'already_in_state': False}], 'tier': 1, 'user_name': 'user', 'rbac_blocked': False}
     assert 200 == 403
     ```

---

## 2. Logic Chain (Chuỗi suy luận kiểm chứng)

1. Từ **Quan sát 2**: `resolve_request_session` cung cấp bước fallback số 6 mang tên "Legacy cookie fallback". Bước này đọc cookie thô `sh_session_tier` và `sh_session_user` từ HTTP request. Các cookie này không hề có chữ ký số (HMAC / Cryptographic Signature), không được đối soát với bất kỳ token nào trong `SessionStore` SQLite / Memory cache.
2. Từ **Quan sát 2 & 3**: Nếu một client gửi `Cookie: sh_session_tier=1`, biến `token` rỗng hoặc không tìm thấy trong DB, hàm sẽ rơi vào bước số 6, tự động gán `tier=1` và `role="ADMIN"`, coi như đã xác thực (`is_authenticated=True`).
3. Từ **Quan sát 3 & 4**: Hậu quả là mọi biện pháp bảo vệ RBAC ở các endpoint `/api/device`, `/api/devices/{id}/control`, `/api/mobile/schedule`, `/api/text_command` đều bị vô hiệu hóa hoàn toàn đối với bất kỳ ai chỉ cần sửa cookie trong trình duyệt hoặc qua script. Cửa chính nhà thông minh bị mở tung mà không hề có phiên đăng nhập của Chủ nhà.
4. Điều này vi phạm trực tiếp yêu cầu **R2 (Bảo mật RBAC theo session)** trong `ORIGINAL_REQUEST.md`:
   *"Đổi tier RBAC từ lấy state global của engine (user đăng nhập cuối) sang quản lý theo từng session (cookie/token) cho mỗi request để 2 người dùng đồng thời không bao giờ lẫn quyền."*
   Việc tin cậy cookie unsigned mà không xác thực session token thực chất đã tạo ra một "backdoor" bảo mật nghiêm trọng.

---

## 3. Caveats (Khu vực Lưu ý)

1. **Khả năng tương thích ngược**: Worker đã thêm fallback này có thể vì lo ngại các ứng dụng cũ hoặc test cũ bị lỗi. Tuy nhiên, qua khảo sát mã nguồn:
   - Toàn bộ thư mục `tests/` không có bài test nào sử dụng hay yêu cầu cookie `sh_session_tier`.
   - Các bài test Phase 1 (`test_phase1_bugfixes_20261104.py`) sử dụng `_REST_ENGINE.set_active_user(...)`, vốn đã được xử lý riêng tại bước số 7 (`_explicit_test_user_set`).
   - Việc duy trì fallback cookie thô này là hoàn toàn dư thừa và gây nguy hiểm trực tiếp cho hệ thống.

---

## 4. Conclusion (Kết luận Đánh giá & Khuyến nghị)

- **Kết luận**: **REJECT**. Milestone M12 **chưa thể nghiệm thu** cho tới khi lỗ hổng bảo mật này được khắc phục triệt để.
- **Yêu cầu hành động đối với Worker**:
  1. Xóa bỏ hoàn toàn bước số 6 "Legacy cookie fallback" (dòng 286–295) trong `simulator/auth/session_store.py`. Chỉ chấp nhận các phiên xác thực có `session_token` hợp lệ được quản lý và đối soát trong `SessionStore`.
  2. Tại `simulator/api/routes_auth.py` (dòng 576–577): Xóa bỏ việc ghi cookie không bảo mật `sh_session_tier` và `sh_session_user`, chỉ duy trì cookie bảo mật duy nhất là `sh_session_token`.
  3. Chạy lại toàn bộ test suite để đảm bảo:
     - `tests/test_p3_session_rbac_concurrency.py` PASS 100%.
     - `tests/test_p3_challenger_m12_adversarial.py` PASS 100% (kể cả test `test_adversarial_cookie_tampering_sh_session_tier_forgery` chặn thành công 403 Forbidden).

---

## 5. Verification Method (Phương pháp Tái hiện Độc lập)

Bất kỳ thành viên nào trong nhóm hoặc Orchestrator có thể tái hiện độc lập lỗi này bằng lệnh một dòng sau:

```powershell
python -c "from fastapi.testclient import TestClient; from simulator.server import app; c = TestClient(app); r = c.post('/api/device', json={'device_id': 'main_door', 'action': 'open'}, cookies={'sh_session_tier': '1'}); assert r.status_code == 403, f'VULNERABLE: {r.status_code} {r.json()}'; print('SECURE')"
```

- **Kết quả hiện tại**: Ném ra ngoại lệ `AssertionError: VULNERABLE: 200 {'ok': True, 'results': [{'ok': True, 'device_id': 'main_door', 'state': 'OPEN'...}]}`.
- **Tiêu chuẩn để APPROVE**: Lệnh trên phải in ra `SECURE` (trả về status code 403).
