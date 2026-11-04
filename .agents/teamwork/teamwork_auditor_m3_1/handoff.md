# BÁO CÁO KIỂM TOÁN TÍNH TOÀN VẸN VÀ BÀN GIAO (FORENSIC AUDIT HANDOFF REPORT) — MILESTONE 3

**Kiểm toán viên**: `teamwork_auditor_m3_1` (Forensic Auditor / Critic / Specialist)  
**Mục tiêu kiểm định**: Độc lập kiểm toán toàn diện tính xác thực (authenticity), chống facade/mã giả lập/gian lận test, bảo toàn 0 CRLF, tính toàn vẹn 68 DOM IDs & 25 window hooks, và chạy kiểm thử độc lập toàn bộ suite cho Milestone 3 (Bugs 6, 7, 8, 9, 12, 13).  
**Thời gian hoàn thành**: 2026-11-04T21:33:00Z  
**Tập tin bàn giao**: `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_auditor_m3_1\handoff.md`  

---

## Forensic Audit Report

**Work Product**: Milestone 3 Deliverables (`mobile_app/index.html`, `simulator/static/js/mobile_app.js`, `simulator/static/css/mobile_app.css`, `simulator/static/index.html`, `simulator/static/js/app.js`, `simulator/static/logs.html`, `simulator/static/js/logs.js`, `tests/test_p4_survey3_ui_layout.py`, `simulator/data/*`)  
**Profile**: General Project (Forensic Integrity)  
**Verdict**: **CLEAN**

### Phase Results
- **Hardcoded Output Detection**: **PASS** — Không tìm thấy chuỗi kết quả kiểm thử hay mảng dữ liệu tĩnh giả mạo trong mã nguồn sản phẩm.
- **Facade Detection**: **PASS** — Toàn bộ tính năng (Three.js 3D render, clamp cảm biến bằng `Math.max`/`Math.min`, phân trang client-side `pageSize=20`, filter ngày, che mật khẩu) đều là mã thực thi tính toán thật, không có hàm dummy trả về hằng số.
- **Pre-populated Artifact Detection**: **PASS** — Không có log giả định hay file kết quả đệm trước kiểm toán.
- **0 CRLF Invariance Verification (Pre-Test & Post-Test)**: **PASS** — 100% tệp mã nguồn, tệp kiểm thử và dữ liệu text/JSON trong `simulator/data/*` đạt chuẩn POSIX LF (0 byte CRLF `\r\n`).
- **DOM & Window Hooks Integrity**: **PASS** — 68/68 DOM IDs và 25/25 `window.*` hooks tồn tại đầy đủ, 58/58 test trong `test_challenger_m4_dom.py` và `test_m8_mobile_screens.py` PASS 100%.
- **Behavioral Verification & Full Test Suite Execution**: **PASS** — Chạy `pytest` 5 file kiểm thử liên tầng: 102/102 test PASS (`Exit Code: 0`). Dọn dẹp sạch `.pytest_tmp`.

---

## 1. OBSERVATION (QUAN SÁT THỰC NGHIỆM ĐỘC LẬP)

### 1.1. Kiểm tra mã nguồn thực chất (Anti-Facade & Anti-Hardcoding)
1. **Bug 6 (Three.js & house3d trên Mobile)**:
   - Trong `mobile_app/index.html` (L690–L693):
     ```html
     <script src="/static/vendor/three.min.js"></script>
     <script src="/static/vendor/GLTFLoader.js"></script>
     <script src="/static/house3d.js"></script>
     <script src="/static/js/mobile_app.js"></script>
     ```
     Nạp đúng thứ tự các thư viện Three.js trước `mobile_app.js`.
   - Trong `simulator/static/js/mobile_app.js` (L1030–L1050):
     ```javascript
     if (typeof window !== 'undefined' && window.SmartHome3D) {
       if (!window._mobile3dInited && typeof window.SmartHome3D.init === 'function') {
         const overviewBox = document.getElementById('mobileOverviewBox');
         if (overviewBox) {
           try {
             window.SmartHome3D.init('mobileOverviewBox', null, async (devId) => {
               const card = document.querySelector(`.dev-row[data-device-id="${devId}"]`);
               if (card) card.click();
             });
             window._mobile3dInited = true;
           } catch (e) {
             console.warn('SmartHome3D init in renderState error:', e);
           }
         }
       }
       if (typeof window.SmartHome3D.updateDevices === 'function' && snap.devices) {
         window.SmartHome3D.updateDevices(snap.devices);
       }
       if (typeof window.SmartHome3D.updateSensors === 'function' && snap.mqtt) {
         window.SmartHome3D.updateSensors(snap.mqtt, true);
       }
     }
     ```
     Khởi tạo WebGL renderer thực, gắn tương tác click thiết bị thật, đồng bộ trạng thái thiết bị và cảm biến MQTT theo thời gian thực.

2. **Bug 7 (Hiển thị đầy đủ 7 thiết bị vật lý trên Mobile)**:
   - Trong `simulator/static/js/mobile_app.js` (L21): `let showAllDevices = true;`.
   - Trong `simulator/static/js/mobile_app.js` (L921): `const visibleDevices = showAllDevices ? filtered : filtered.slice(0, 4);`.
   - Khi `showAllDevices = true`, toàn bộ 7 thiết bị (`main_door`, `living_room_light`, `bedroom_light`, `fan`, `ac`, `alarm_siren`, `garden_pump`) đều được render vào `#devGrid`. Nút `#btnToggleShowAllDevices` hiển thị `"Thu gọn"` theo đúng trạng thái ban đầu.

3. **Bug 8 (Safe-Area & Đếm ngược Mời khách rõ ràng)**:
   - Trong `mobile_app/index.html`: Dòng thừa `"Mỗi tab mở một màn riêng, không cuộn tới mục khác."` đã được loại bỏ hoàn toàn khỏi DOM.
   - Trong `simulator/static/css/mobile_app.css` (L441–L446):
     ```css
     #tabViewAccount {
       padding-bottom: calc(56px + env(safe-area-inset-bottom));
     }
     #mobileBtnLogout {
       margin-bottom: calc(24px + env(safe-area-inset-bottom));
     }
     ```
     Đảm bảo nút đăng xuất không bị thanh điều hướng ảo trên các trình duyệt Samsung Internet / mobile che khuất.
   - Trong `simulator/static/js/mobile_app.js` (L1483):
     `cdEl.textContent = 'Đổi mã sau ' + rem + 's';`
     Không còn dùng chuỗi cụt ngủn `"Còn ${rem}s"`.

4. **Bug 9 (Desktop Sensor Panel & Clamping thực chất)**:
   - Trong `simulator/static/index.html` (L135–L156): Đã bổ sung thẻ `<section class="panel sensors" id="secSensors" aria-labelledby="sensors-title">` chứa đủ 3 ô: Nhiệt độ (`#sensorTempVal`), Độ ẩm (`#sensorHumVal`), Độ ẩm đất (`#sensorSoilVal`).
   - Trong `simulator/static/js/app.js` (L555–L575):
     ```javascript
     const rawT = Number(dht.temp_c);
     const safeT = Number.isFinite(rawT) ? Math.max(0, Math.min(60, rawT)) : 28.5;
     tempLabel.textContent = (Math.round(safeT * 10) / 10) + "°C";

     const rawH = Number(dht.humidity_pct);
     const safeH = Number.isFinite(rawH) ? Math.max(0, Math.min(100, rawH)) : 65;
     humLabel.textContent = Math.round(safeH) + "%";

     const rawS = Number(soil.soil_moisture_pct);
     const safeS = Number.isFinite(rawS) ? Math.max(0, Math.min(100, rawS)) : 62;
     soilLabel.textContent = Math.round(safeS) + "%";
     ```
     Thuật toán clamp sử dụng `Math.max`/`Math.min` toán học thật, xử lý an toàn giá trị ngoại lai NaN hoặc vượt biên.

5. **Bug 12 (QR Scanner Deduplication)**:
   - Trong `simulator/static/js/mobile_app.js` (L775–L778):
     ```javascript
     function openQrScanner() {
       const modal = document.getElementById('mobileQrScannerModal');
       if (modal) modal.hidden = false;
     }
     ```
     Đã xóa bỏ dòng gán đè `status.textContent = 'Đưa mã QR vào trong khung để quét'`, triệt tiêu hoàn toàn hiện tượng lặp lại 2 lần với `p.instruction`.

6. **Bug 13 (Logs Client Pagination, Date Filtering & Masking)**:
   - Trong `simulator/static/logs.html` (L127–L132): Bổ sung container `#logsPaginationBar` chứa `#logsPaginationInfo` và nút `#btnLogsLoadMore`.
   - Trong `simulator/static/js/logs.js`: Cài đặt logic phân trang `pageSize = 20`, hàm `renderLogsPage()` cắt mảng động `filtered.slice(0, visibleCount)`, hàm `loadMoreLogs()` tăng trang, hàm `getFilteredLogs()` lọc đúng theo khoảng ngày (`today`, `7d`, `all`), và `maskSensitiveLogText()` che mật khẩu dạng regex thực tế.

---

### 1.2. Kiểm tra chuẩn 0 CRLF Pre-Test & Post-Test
Kiểm tra bằng lệnh độc lập:
```powershell
python -c "
import glob, pathlib
targets = [
    'mobile_app/index.html', 'simulator/static/js/mobile_app.js', 'simulator/static/css/mobile_app.css',
    'simulator/static/index.html', 'simulator/static/js/app.js', 'simulator/static/logs.html',
    'simulator/static/js/logs.js', 'tests/test_p4_survey3_ui_layout.py', 'tests/test_p4_survey2_realtime.py',
    'tests/test_p4_survey1_security_auth.py', 'tests/test_challenger_m4_dom.py', 'tests/test_m8_mobile_screens.py'
]
data_files = [f for f in pathlib.Path('simulator/data').iterdir() if f.is_file() and f.suffix != '.db']
all_checked = [pathlib.Path(t) for t in targets] + data_files
crlf_violations = [str(f) for f in all_checked if b'\r\n' in f.read_bytes()]
print(f'Total files checked: {len(all_checked)}, CRLF violations: {len(crlf_violations)}')
assert not crlf_violations
"
```
**Kết quả**:
- Pre-test: `Total files checked: 24, CRLF violations: 0` (100% LF).
- Post-test (sau khi chạy toàn bộ pytest trên Windows): `Total files checked: 24, CRLF violations: 0` (Bảo toàn 100% LF, không bị Windows carriage-return xâm nhập).

---

### 1.3. Kiểm tra tính toàn vẹn 68 DOM IDs & 25 window.* hooks
Kiểm tra thông qua thực thi bộ test chuyên biệt:
```powershell
python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_m8_mobile_screens.py
```
**Kết quả**:
`58 passed, 3 warnings in 7.60s` (`Exit Code: 0`).
- `test_all_68_dom_ids_exist`: **PASSED** (Toàn bộ 68 DOM IDs bắt buộc tồn tại chính xác).
- `test_all_25_window_hooks_exported`: **PASSED** (Toàn bộ 25 hàm toàn cục được gắn lên `window.*`).

---

### 1.4. Thực thi độc lập Full Pytest Suite Milestone 3
Lệnh thực thi độc lập:
```powershell
python -X utf8 -m pytest tests/test_p4_survey3_ui_layout.py tests/test_p4_survey2_realtime.py tests/test_p4_survey1_security_auth.py tests/test_challenger_m4_dom.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp
```
**Kết quả đầu ra trực tiếp**:
```
collected 102 items

tests\test_p4_survey3_ui_layout.py .............                         [ 12%]
tests\test_p4_survey2_realtime.py ..............                         [ 26%]
tests\test_p4_survey1_security_auth.py .................                 [ 43%]
tests\test_challenger_m4_dom.py ....................................     [ 78%]
tests\test_m8_mobile_screens.py ......................                   [100%]

======================= 102 passed, 3 warnings in 8.43s =======================
Exit Code: 0
```
Dọn dẹp thư mục tạm `.pytest_tmp`: hoàn tất không để lại rác trong workspace.

---

## 2. LOGIC CHAIN (CHUỖI SUY LUẬN TỪ QUAN SÁT ĐẾN KẾT LUẬN)

1. **Từ Quan sát 1.1**: Mã nguồn của Worker 3 đã trực tiếp hiện thực các thuật toán xử lý dữ liệu (clamping toán học, WebGL canvas hooks, dynamic client pagination, regex masking) thay vì gán giá trị cứng hay trả về mock objects. Do đó, loại trừ hoàn toàn nghi vấn Facade Implementation và Hardcoded Test Results.
2. **Từ Quan sát 1.2**: Các tệp mã nguồn và tệp JSON/data trong `simulator/data/` trước và sau khi chạy test đều được bảo toàn 100% định dạng byte-level POSIX LF, không có ký tự `\r` (CRLF = 0). Quy tắc bất biến encoding được tuân thủ nghiêm ngặt.
3. **Từ Quan sát 1.3**: Không có DOM ID hay hook `window.*` nào bị đổi tên, xóa bỏ hoặc xung đột trong quá trình refactor/sửa lỗi. Bộ kiểm thử hồi quy DOM và Mobile đạt 100% PASSED.
4. **Từ Quan sát 1.4**: Toàn bộ 102 bài kiểm thử từ Milestone 1, Milestone 2, Milestone 3 đến Challenger Suite đều hoàn thành với mã thoát 0, không có bài kiểm thử nào bị skip hay fail ngầm.

$\implies$ **Kết luận logic**: Sản phẩm của Milestone 3 hoàn toàn thỏa mãn các tiêu chí kỹ thuật và quy chuẩn liêm chính mã nguồn.

---

## 3. CAVEATS (GIỚI HẠN & ĐIỀU KIỆN BIÊN)

1. Tệp cơ sở dữ liệu `simulator/data/smarthome.db` là tệp nhị phân SQLite (B-tree binary pages) nên tự nhiên chứa các chuỗi byte ngẫu nhiên trùng với `0x0D 0x0A`. Điều này hoàn toàn đúng tính chất kỹ thuật của định dạng SQLite, không phải vi phạm CRLF mã nguồn. Toàn bộ 100% tệp văn bản/JSON đều đạt 0 CRLF tuyệt đối.
2. Việc kiểm toán tính năng Three.js WebGL dựa trên AST, cấu trúc DOM canvas, và kiểm thử headless environment. Việc kết xuất GPU thực tế phụ thuộc vào thiết bị đầu cuối của người dùng.

---

## 4. CONCLUSION (KẾT LUẬN KIỂM TOÁN)

- **Audit Verdict**: **CLEAN** (Xác nhận 100% liêm chính, không facade, không test gian lận, 0 CRLF, 0 lỗi rò rỉ).
- Sản phẩm Milestone 3 được **CHẤP THUẬN (ACCEPTED)**.
- Đủ điều kiện chuyển tiếp sang **Milestone 4 (Comprehensive Multi-Role & Cross-Platform Gate)**.

---

## 5. VERIFICATION METHOD (LỆNH KIỂM CHỨNG ĐỘC LẬP CHO BÊN THẨM ĐỊNH)

Bất kỳ kiểm toán viên hoặc reviewer độc lập nào đều có thể kiểm chứng lại kết quả bằng chuỗi lệnh sau:

```powershell
# 1. Chạy full test suite Milestone 3 và hồi quy
python -X utf8 -m pytest tests/test_p4_survey3_ui_layout.py tests/test_p4_survey2_realtime.py tests/test_p4_survey1_security_auth.py tests/test_challenger_m4_dom.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp

# 2. Xác thực 0 CRLF
python -c "
import pathlib
targets = ['mobile_app/index.html', 'simulator/static/js/mobile_app.js', 'simulator/static/css/mobile_app.css', 'simulator/static/index.html', 'simulator/static/js/app.js', 'simulator/static/logs.html', 'simulator/static/js/logs.js', 'tests/test_p4_survey3_ui_layout.py']
data_files = [f for f in pathlib.Path('simulator/data').iterdir() if f.is_file() and f.suffix != '.db']
assert all(b'\r\n' not in f.read_bytes() for f in [pathlib.Path(t) for t in targets] + data_files)
print('VERIFIED: 100% LF - 0 CRLF')
"

# 3. Dọn dẹp .pytest_tmp
if (Test-Path .pytest_tmp) { Remove-Item -Recurse -Force .pytest_tmp }
```
