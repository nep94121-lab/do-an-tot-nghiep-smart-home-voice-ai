# Forensic Audit Report — Phase 2 Deliverables

**Work Product**: Phase 2 Deliverables (Milestones M6, M7, M8)
- Error Pages & Service Worker: `simulator/static/offline.html`, `404.html`, `500.html`, `qr_expired.html`, `403.html`, `sw.js`
- Server & Routing: `simulator/server.py`, `vercel.json`
- Web Frontend: `simulator/static/index.html`, `simulator/static/js/app.js`, `simulator/static/css/style.css`
- Mobile Frontend: `mobile_app/index.html`, `simulator/static/js/mobile_app.js`, `simulator/static/css/mobile_app.css`
- Test Suites: `tests/test_m6_web_error_sw.py`, `tests/test_m7_security_modals_banner.py`, `tests/test_m8_mobile_screens.py`
- Preserved 3D Villa: `simulator/static/house3d.js`

**Profile**: General Project
**Integrity Mode**: Development (per `ORIGINAL_REQUEST.md` line 49)
**Verdict**: **CLEAN** (Không phát hiện bất kỳ hành vi gian lận, facade hay rò rỉ bảo mật nào)
**Advisory Flag**: Phát hiện 1 lỗi tuân thủ kiến trúc bóc tách mã: thẻ inline `<script>` tại `simulator/static/index.html:441-447` vi phạm kiểm thử bảo mật `tests/test_challenger_m4_security.py:445`.

---

## Phase Results (Integrity Forensics Truth Table)

| # | Check Name | Expected Behavior | Observed Result | Status |
|---|------------|-------------------|-----------------|:------:|
| 1 | **Hardcoded test results** | Không có kết quả test giả lập, không mock dữ liệu cứng để qua mặt test | Quét toàn bộ mã nguồn: 0 hardcoded test results. Mọi assertion đều kiểm tra DOM, logic hoặc API thật | **PASS** |
| 2 | **Facade implementations** | Không có hàm rỗng `return true`, `pass`, hay stub che giấu logic thật | Mọi hàm trong `app.js`, `mobile_app.js`, `server.py`, `sw.js` đều hiện thực đầy đủ luồng xử lý và rẽ nhánh lỗi/thành công | **PASS** |
| 3 | **Backend API genuine calls** | Các endpoint (`/api/auth3/forgot_password_send_otp`, `/forgot_password_reset`, `/guest_handshake`, `/layer1_login`, `/layer2_verify_otp`) được gọi thật bằng `fetch()` | Xác nhận các lệnh gọi `fetch()` với payload JSON thật, nhận kết quả và cập nhật UI/WebSocket tương ứng | **PASS** |
| 4 | **Service Worker authentic logic** | `sw.js` đăng ký thật, xử lý cache shell và network-first navigate | `sw.js` hiện thực `install`, `activate`, precache `SHELL_ASSETS`, skipWaiting, clients.claim, fallback `/offline.html` khi mất mạng, bỏ qua `/api/` và `/ws` | **PASS** |
| 5 | **Security & Zero-Leak** | Không lộ password thật, OTP, secret key, Google API token | Quét regex (`AIza...`, `ghp_...`, `console.log(password/otp)`): Không phát hiện bất kỳ token hay thông tin nhạy cảm nào bị ghi vào file hay log | **PASS** |
| 6 | **Line endings & Encoding** | 0 CRLF (`\r\n`), 100% UTF-8 without BOM | Toàn bộ 17 tệp thuộc phạm vi Phase 2 đều đạt CRLF = 0, BOM = False | **PASS** |
| 7 | **3D House Model & Toàn cảnh** | `simulator/static/house3d.js` không bị can thiệp hay sửa sai lệch | `git diff HEAD simulator/static/house3d.js` trả về 0 dòng thay đổi (bảo toàn 100% từ commit `7e2576e`) | **PASS** |
| 8 | **DOM IDs & Hooks backward compatibility** | Đầy đủ 68 DOM IDs và 25 window.* hooks | `tests/test_m8_mobile_screens.py` và `tests/test_challenger_m4_dom.py` (36/36 test) đạt 100% PASS | **PASS** |
| 9 | **Phase 2 Test Suites Execution** | M6, M7, M8 test suites thực thi thành công | `python -X utf8 -m pytest tests/test_m6_web_error_sw.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py`: **55/55 PASSED (100%)** | **PASS** |

---

## 5-Component Forensic Handoff Report

### 1. Observation

1. **Kiểm tra Mã hóa & Ký tự dòng (0 CRLF, UTF-8 no BOM)**:
   - Chạy kiểm tra byte-level trên toàn bộ 17 tệp mục tiêu:
     - `simulator/static/offline.html`: size=7441, CRLF=0, LF=247, BOM=False
     - `simulator/static/404.html`: size=4272, CRLF=0, LF=161, BOM=False
     - `simulator/static/500.html`: size=4633, CRLF=0, LF=170, BOM=False
     - `simulator/static/qr_expired.html`: size=4502, CRLF=0, LF=169, BOM=False
     - `simulator/static/403.html`: size=4989, CRLF=0, LF=186, BOM=False
     - `simulator/static/sw.js`: size=3590, CRLF=0, LF=114, BOM=False
     - `simulator/server.py`: size=8375, CRLF=0, LF=249, BOM=False
     - `simulator/static/index.html`: size=30200, CRLF=0, LF=449, BOM=False
     - `simulator/static/js/app.js`: size=72880, CRLF=0, LF=1956, BOM=False
     - `simulator/static/css/style.css`: size=19118, CRLF=0, LF=1137, BOM=False
     - `mobile_app/index.html`: size=40931, CRLF=0, LF=668, BOM=False
     - `simulator/static/js/mobile_app.js`: size=64053, CRLF=0, LF=1483, BOM=False
     - `simulator/static/css/mobile_app.css`: size=15010, CRLF=0, LF=699, BOM=False
     - `vercel.json`: size=1694, CRLF=0, LF=34, BOM=False
     - `tests/test_m6_web_error_sw.py`: size=10762, CRLF=0, LF=229, BOM=False
     - `tests/test_m7_security_modals_banner.py`: size=15275, CRLF=0, LF=342, BOM=False
     - `tests/test_m8_mobile_screens.py`: size=18870, CRLF=0, LF=300, BOM=False
   - Kết quả: **100% tệp đạt chuẩn 0 CRLF và UTF-8 không BOM**.

2. **Kiểm tra tính bất biến của Mô hình 3D (`house3d.js`)**:
   - Lệnh: `git diff HEAD simulator/static/house3d.js`
   - Kết quả: 0 bytes diff. File được bảo toàn tuyệt đối từ commit `7e2576ee237feb2b3e695863ad8bc5369ce6f860` với đầy đủ nhãn 3D (`#house3dLabels`), 7 nút pin nổi, camera toolbar và raycaster.

3. **Kiểm tra Chống gian lận & Tính chân thực (Authenticity)**:
   - Các API endpoints được gọi thực chất từ client:
     - `/api/auth3/forgot_password_send_otp`: gọi tại `app.js` line 1776 và `mobile_app.js` line 434.
     - `/api/auth3/forgot_password_reset`: gọi tại `app.js` line 1618 và `mobile_app.js` line 483.
     - `/api/auth3/guest_handshake`: gọi tại `mobile_app.js` line 768 (`processQrHandshake`) và tích hợp trong `routes_qr.py`.
     - `/api/auth3/layer1_login`: gọi tại `app.js` line 1526, 1813 và `mobile_app.js` line 60.
     - `/api/auth3/layer2_verify_otp`: gọi tại `app.js` line 1834 phục vụ mở khóa an ninh khẩn cấp khi bị khóa do 3 lần nhận diện sai.
   - Không có bất kỳ hàm dummy nào trả về kết quả giả.

4. **Kiểm tra Bảo mật (Zero-Leak)**:
   - Quét mẫu regex khóa API (`AIza[0-9A-Za-z-_]{35}`, `ghp_[0-9a-zA-Z]{36}`): **0 phát hiện**.
   - Quét log rò rỉ (`console.log` chứa password, otp, token, secret): **0 phát hiện**.

5. **Thực thi Kiểm thử Độc lập**:
   - Lệnh 1: `python -X utf8 -m pytest tests/test_m6_web_error_sw.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp -v`
     - Kết quả: **55 passed, 3 warnings in 5.99s (100% PASS)**.
   - Lệnh 2: `python -X utf8 -m pytest tests/test_challenger_m4_dom.py --basetemp=.pytest_tmp -v`
     - Kết quả: **36 passed in 2.43s (100% PASS)**.
   - Lệnh 3 (Full suite): `python -X utf8 -m pytest tests/ --basetemp=.pytest_tmp -q`
     - Kết quả: **733 passed, 6 failed out of 739 executed tests in 204.17s**.
     - Chi tiết 6 lỗi:
       1. `tests/test_challenger_m4_security.py:445`: `AssertionError: Tệp index.html vẫn còn 1 khối inline <script>!`
          Nguyên nhân: Khối đăng ký Service Worker được đặt trực tiếp dưới dạng thẻ `<script>` inline tại `simulator/static/index.html:441-447`.
       2. `tests/test_m8_mobile_screens.py:282`: Khi chạy full suite 759 test kéo dài 3.5 phút, token sinh bởi `/api/auth3/guest_qr_current` bị trùng window hoặc đã bị test khác consume trước đó, trả về HTTP 400. Khi chạy riêng lẻ `tests/test_m8_mobile_screens.py`: **22/22 PASSED**.
       3. 4 test trong `tests/test_phase1_bugfixes_20261104.py`: Khi chạy full suite bị ảnh hưởng bởi state singleton của engine `_REST_ENGINE` do các test trước không reset state thiết bị. Khi chạy riêng `tests/test_phase1_bugfixes_20261104.py`: **6/6 PASSED**.

---

### 2. Logic Chain

1. **Tiền đề 1 (Authenticity)**: Toàn bộ 5 trang HTML lỗi (`offline.html`, `404.html`, `500.html`, `qr_expired.html`, `403.html`), Service Worker `sw.js`, 5 màn hình mobile và 3 modal/banner bảo mật đều có mã nguồn hiện thực thật, không dùng facade hay hardcoded outcomes.
2. **Tiền đề 2 (Integrity Mode)**: `ORIGINAL_REQUEST.md` quy định `Integrity mode: development`. Trong chế độ này, tiêu chí cấm là: kết quả test hardcode, facade rỗng, file output giả mạo. Các điều này đều KHÔNG xuất hiện.
3. **Tiền đề 3 (Security)**: Không có secret, OTP hay token nào bị rò rỉ.
4. **Tiền đề 4 (Hygiene)**: 100% các file mới/chỉnh sửa đều có 0 CRLF và UTF-8 không BOM.
5. **Tiền đề 5 (3D Model)**: `house3d.js` giữ nguyên trạng 100%, không bị sửa đổi hay phá vỡ.
6. **Suy luận**: Toàn bộ yêu cầu về tính chính trực, chân thực và bảo mật của Phase 2 đều được thỏa mãn. Do đó, phán quyết kiểm định tính chính trực là **CLEAN**.

---

### 3. Caveats & Architectural Flaw

1. **Khối inline `<script>` tại `simulator/static/index.html:441-447`**:
   - Thẻ `<script>` inline được thêm vào để đăng ký Service Worker:
     ```html
     <script>
       if ('serviceWorker' in navigator) {
         window.addEventListener('load', function() {
           navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function() {});
         });
       }
     </script>
     ```
   - Thẻ này vi phạm quy tắc 100% tách biệt (Zero Inline Scripts) được kiểm chứng bởi `tests/test_challenger_m4_security.py:445`.
   - **Khắc phục đề xuất**: Chuyển đoạn mã đăng ký Service Worker này vào trong file `simulator/static/js/app.js` (hoặc bóc tách ra file `<script src="/static/js/sw_register.js"></script>`) và xóa bỏ thẻ `<script>` inline khỏi `index.html`.

2. **Nhiễm bẩn trạng thái giữa các bài test khi chạy Full Suite**:
   - Singleton `_REST_ENGINE` lưu trạng thái thiết bị trong bộ nhớ tiến trình Python, nên các bài test trong `test_phase1_bugfixes_20261104.py` phụ thuộc vào trạng thái ban đầu (`living_room_light == OFF`, `garden_pump == OFF`) sẽ bị ảnh hưởng nếu các bài test phía trước thay đổi trạng thái mà không reset.

---

### 4. Conclusion

- **Verdict**: **CLEAN**
- Các thành phần Phase 2 (M6, M7, M8) được hiện thực đầy đủ, đúng đặc tả thiết kế `DESIGN_NEW_PAGES.md`, bảo toàn 100% 68 DOM IDs, 25 window hooks, và 3D Villa view.
- 55/55 test chuyên biệt của Phase 2 (M6, M7, M8) và 36/36 test Challenger DOM đều vượt qua thành công.
- Khuyến nghị bàn giao cho đội phát triển xử lý ngay điểm lưu ý (di dời đoạn đăng ký Service Worker từ inline `index.html` vào `app.js`) để đảm bảo 100% test bộ `test_challenger_m4_security.py` đạt PASS.

---

### 5. Verification Method

Người nhận hoặc kiểm toán viên độc lập có thể tự tái hiện bằng các lệnh sau:

```powershell
# 1. Kiểm tra mã hóa và line endings (phải in ra 0 CRLF)
python -c "
files = ['simulator/static/offline.html', 'simulator/static/404.html', 'simulator/static/500.html', 'simulator/static/qr_expired.html', 'simulator/static/403.html', 'simulator/static/sw.js', 'simulator/server.py', 'simulator/static/index.html', 'simulator/static/js/app.js', 'simulator/static/css/style.css', 'mobile_app/index.html', 'simulator/static/js/mobile_app.js', 'simulator/static/css/mobile_app.css', 'vercel.json']
for f in files:
    with open(f, 'rb') as fp: c = fp.read()
    assert b'\r\n' not in c, f'{f} has CRLF'
    assert not c.startswith(b'\xef\xbb\xbf'), f'{f} has BOM'
print('ALL 14 CORE FILES: 0 CRLF, UTF-8 NO BOM')
"

# 2. Kiểm tra tính bất biến của house3d.js
git diff HEAD simulator/static/house3d.js

# 3. Chạy toàn bộ 55 test chuyên biệt Phase 2
python -X utf8 -m pytest tests/test_m6_web_error_sw.py tests/test_m7_security_modals_banner.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp -v

# 4. Chạy 36 test Challenger DOM
python -X utf8 -m pytest tests/test_challenger_m4_dom.py --basetemp=.pytest_tmp -v
```
