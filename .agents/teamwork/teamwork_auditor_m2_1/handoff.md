# Forensic Audit Report — Milestone 2 (Phase 4)

**Work Product**: Milestone 2 Implementation (Bugs 3, 10, 11, 14 from `REAL_TEST_BUGS_20261105.md`)  
**Auditor**: teamwork_auditor_m2_1  
**Integrity Mode**: development (`ORIGINAL_REQUEST.md` line 12 & line 116)  
**Profile**: General Project  
**Verdict**: **CLEAN**

---

## 1. Observation (Quan sát thực nghiệm & Bằng chứng trực tiếp)

### 1.1. Kiểm tra tính xác thực mã nguồn (Không Facade, Không Dummy Mocks, Không Hardcoded Response)
- **Bug 3 (WebSocket Fallback & Favicon):**
  - Trong `simulator/static/js/app.js` (dòng 811–841): `ws.onclose` thực thi `fetch('/api/state')`. Khi thành công gọi `applySnapshot(snap)`, `updateConnectionUI(true)`, và `hideWsReconnectBanner()`. Khi thất bại trong khối `catch` mới kích hoạt `updateConnectionUI(false)` và `showWsReconnectBanner(...)`.
  - Trong `pollRestStateFallback()`: khi `fetch('/api/state')` thành công, cũng đồng bộ gọi `hideWsReconnectBanner()` và `updateConnectionUI(true)`.
  - Trong `vercel.json` (dòng 18): route `{ "src": "^/favicon\\.ico$", "dest": "/simulator/static/favicon.ico" }` được cấu hình chuẩn xác.
  - Trong `simulator/server.py` (dòng 195–196): route `@app.get("/favicon.ico")` được phục vụ thực tế qua backend.
- **Bug 10 (Optimistic UI & In-place DOM Updates):**
  - Trong `simulator/static/js/app.js` (dòng 241–326): `toggleDeviceById(devId)` ngay lập tức cập nhật in-memory `dev.state`, gán `swInput.checked = nextIsOn`, cập nhật icon `.device-icon.classList.toggle('off', !nextIsOn)`, gọi `updateDeviceCardUI(devId, dev, nextIsOn)`, đếm lại tổng thiết bị bật, phát âm thanh relay và đồng bộ mô hình 3D. Khối `rollback()` được định nghĩa đầy đủ để hoàn tác trạng thái nếu fetch trả về lỗi (`data.ok === false`) hoặc đứt kết nối (`catch`).
  - Trong `simulator/static/js/app.js` (dòng 349–358): `renderDevices()` loại bỏ hoàn toàn `devicesGrid.innerHTML = ""`, chuyển sang cập nhật in-place các node `#dev-card-${dev.id}` có sẵn, triệt tiêu hiện tượng chớp nháy DOM.
  - Trong `simulator/static/js/app.js` (dòng 340–345): `getDeviceRoomLabel()` trả về nhãn đầy đủ `"Đã bật"` / `"Đã tắt"` và `"Đã mở"` / `"Đã khóa"`.
  - Trong `simulator/static/js/mobile_app.js` (dòng 940–975): cập nhật optimistic class `card.classList.toggle('on', nextIsOn)` và rollback an toàn.
- **Bug 11 (Mic Waiting State & Rejection Modal):**
  - Trong `mobile_app/index.html` (dòng 597 & 619): tiêu đề ban đầu là `<h2 id="mobileVoiceSheetTitle">Đang chờ quyền mic</h2>` và timer `<span id="mobileVoiceTimerCur">00:00</span>`.
  - Trong `mobile_app/index.html` (dòng 665–689): bổ sung đầy đủ `#mobileMicPermissionModal` với `#mobileMictitle`, `#mobileMicPermissionDesc`, `#mobileMicPermissionHttpNote`, `#mobileBtnMicPermissionRetry`, `#mobileBtnMicPermissionClose`.
  - Trong `simulator/static/js/mobile_app.js` (dòng 637–680): `startVoiceSheetRecording()` yêu cầu `navigator.mediaDevices.getUserMedia({ audio: true })`. Khi bị từ chối hoặc lỗi, tự động đóng bottom sheet và mở `#mobileMicPermissionModal`. Chỉ khi nhận được audio stream thật mới đổi tiêu đề sang `"Đang thu âm"`, kích hoạt sóng âm động và timer.
  - Các hàm `openMobileMicPermissionModal` và `closeMobileMicPermissionModal` được export đầy đủ ra `window`.
- **Bug 14 (Wokwi Layout & Telemetry):**
  - Trong `simulator/static/wokwi.html` (dòng 58): `#hoverHoleInfo` khởi tạo với `"Nhiệt độ: 28.5°C · Độ ẩm: 65% · Độ ẩm đất: 62%"`, loại bỏ hoàn toàn `"Chưa có dữ liệu"`.
  - Trong `simulator/static/wokwi.html` (dòng 169 & 175): thẻ nhãn DHT11 đặt tại `left: 480px; top: 360px`, Buzzer đặt tại `left: 648px; top: 388px`. Khoảng cách ngang $648 - 480 = 168\text{px} \ge 150\text{px}$ và độ lệch dọc $388 - 360 = 28\text{px} \ge 20\text{px}$, loại bỏ 100% hiện tượng đè nhãn.
  - Trong `simulator/static/js/wokwi.js` (dòng 545–565): `syncWokwiComponents()` liên tục cập nhật telemetry cảm biến thời gian thực vào `#hoverHoleInfo`. Thẻ `#circuitStage` có `onmouseleave="clearHoleHover()"` để khôi phục telemetry khi chuột rời khỏi bảng mạch.

### 1.2. Kiểm tra định dạng tệp `simulator/static/favicon.ico`
- Lệnh thực thi:
  ```powershell
  python -c "
  import struct, pathlib
  p = pathlib.Path('simulator/static/favicon.ico')
  data = p.read_bytes()
  reserved, ico_type, num_images = struct.unpack('<HHH', data[:6])
  w, h, colors, res2, planes, bpp, size, offset = struct.unpack('<BBBBHHII', data[6:22])
  from PIL import Image
  im = Image.open(p)
  print(f'Size: {len(data)} bytes | Type: {ico_type} | Images: {num_images} | Entry: {w}x{h} bpp={bpp} | Pillow: format={im.format}, size={im.size}, mode={im.mode}')
  "
  ```
- Kết quả thực tế:
  `Size: 1118 bytes | Type: 1 | Images: 1 | Entry: 16x16 bpp=32 | Pillow: format=ICO, size=(16, 16), mode=RGBA`
- Đánh giá: Tệp favicon.ico là file nhị phân chuẩn định dạng ICO, 16x16 32-bit RGBA, mở hoàn hảo bởi Pillow.

### 1.3. Kiểm tra tính bất biến 0 CRLF (100% POSIX LF)
- Đã quét toàn bộ các file sửa đổi và `simulator/data/*` trước và sau khi chạy test:
  - 28 file trong danh mục sửa đổi và dữ liệu `simulator/data/*`.
  - 129 file mã nguồn toàn diện trên toàn bộ cây thư mục `simulator/`, `tests/`, `mobile_app/`.
- Kết quả thực tế:
  `Checked 129 files across simulator/, tests/, mobile_app/. PASS: Zero CRLF in all scanned source/data files!`

### 1.4. Kiểm tra bảo toàn 68 DOM IDs và 25 window.* hooks
- Chạy kiểm thử: `python -X utf8 -m pytest tests/test_challenger_m4_dom.py tests/test_m8_mobile_screens.py -v --basetemp=.pytest_tmp`
- Kết quả thực tế:
  - `test_all_68_dom_ids_exist`: **PASSED**
  - `test_all_25_window_hooks_exported`: **PASSED**
  - Toàn bộ 36 tests trong `test_challenger_m4_dom.py`: **PASSED**
  - Toàn bộ 22 tests trong `test_m8_mobile_screens.py`: **PASSED**

### 1.5. Chạy bộ kiểm thử độc lập toàn diện
- Lệnh thực thi:
  ```powershell
  python -X utf8 -m pytest tests/test_p4_survey2_realtime.py tests/test_p4_survey1_security_auth.py tests/test_challenger_m4_dom.py tests/test_m8_mobile_screens.py -v --basetemp=.pytest_tmp
  ```
- Kết quả thực tế:
  `======================= 89 passed, 3 warnings in 8.15s ========================`
  Exit Code: `0`
- Dọn dẹp: Đã xóa hoàn toàn thư mục tạm `.pytest_tmp` sau khi kiểm thử kết thúc (`.pytest_tmp exists=False`).

---

## 2. Logic Chain (Chuỗi suy luận pháp y)

1. **Từ Quan sát 1.1:** Mọi thay đổi trong `app.js`, `mobile_app.js`, `index.html`, `wokwi.html`, `wokwi.js` đều xử lý logic thực tế: kết nối WebSocket fallback, cập nhật lạc quan có rollback, gọi API trình duyệt `getUserMedia`, xử lý từ chối quyền, tính toán telemetry cảm biến và căn chỉnh tọa độ nhãn CSS. Không có hàm trả về hằng số rỗng (facade), không có việc bỏ qua xử lý logic hay mock tạm bợ.
2. **Từ Quan sát 1.2:** Tệp `favicon.ico` được phân tích cấu trúc byte nhị phân `struct.unpack`, kiểm tra header ICO `0x00000100`, xác nhận 32-bit color depth và được thư viện đồ họa Pillow load thành công `RGBA (16, 16)`. Đây là tệp nhị phân hợp lệ 100%, không phải file rỗng hay đổi đuôi giả mạo.
3. **Từ Quan sát 1.3:** Toàn bộ 129 tệp mã nguồn và tệp dữ liệu trong `simulator/data/` đều bảo toàn 100% POSIX LF (0 ký tự `\r\n`), cả trước và sau khi thực thi pytest trên hệ điều hành Windows.
4. **Từ Quan sát 1.4 & 1.5:** Cả 68 DOM IDs bắt buộc và 25 window hooks đều tồn tại nguyên vẹn. Toàn bộ 89 ca kiểm thử trong 4 test suites chuyên trách đều đạt 100% PASS (Exit code 0).
5. **Tổng hợp:** Tất cả 8 tiêu chí kiểm định pháp y đều được thỏa mãn đầy đủ bằng chứng thực nghiệm độc lập.

---

## 3. Caveats (Giới hạn & Giả định)

- Kiểm thử micro phụ thuộc vào môi trường trình duyệt thật (Playwright / Chromium) hoặc các thiết bị di động có hỗ trợ MediaDevices API. Kiểm thử tĩnh và unit test đã xác thực logic bắt lỗi và hiện modal khi không có stream âm thanh.
- Thư mục `.pytest_tmp` đã được chủ động xóa bỏ sau phiên chạy test để đảm bảo không để lại file rác trong workspace.

---

## 4. Conclusion (Kết luận)

**Verdict**: **CLEAN**

Công việc của Worker 2 (Milestone 2: Bugs 3, 10, 11, 14) đã được triển khai một cách thực chất, bảo toàn toàn bộ giao diện và hợp đồng kỹ thuật (contracts, DOM IDs, window hooks), đáp ứng 100% tiêu chuẩn chất lượng và tính toàn vẹn hệ thống.

---

## 5. Verification Method (Lệnh kiểm chứng độc lập)

Bất kỳ kiểm định viên hoặc hệ thống nào cũng có thể tái tạo 100% kết quả trên bằng các lệnh sau:

```powershell
# 1. Chạy toàn bộ 89 ca kiểm thử Milestone 2 và liên quan
python -X utf8 -m pytest tests/test_p4_survey2_realtime.py tests/test_p4_survey1_security_auth.py tests/test_challenger_m4_dom.py tests/test_m8_mobile_screens.py --basetemp=.pytest_tmp

# 2. Xóa thư mục tạm sau kiểm thử
python -c "import pathlib, shutil; p = pathlib.Path('.pytest_tmp'); shutil.rmtree(p, ignore_errors=True) if p.exists() else None"

# 3. Kiểm tra tính toàn vẹn 0 CRLF
python -c "
import pathlib
for folder in ['simulator', 'tests', 'mobile_app']:
    for p in pathlib.Path(folder).rglob('*'):
        if p.is_file() and p.suffix in ('.py', '.js', '.html', '.css', '.json', '.jsonl'):
            assert b'\r\n' not in p.read_bytes(), f'CRLF in {p}'
print('All source files: 0 CRLF (POSIX LF)')
"

# 4. Kiểm tra cấu trúc nhị phân favicon.ico
python -c "
import pathlib, struct
p = pathlib.Path('simulator/static/favicon.ico')
assert p.exists() and p.read_bytes()[:4] == b'\x00\x00\x01\x00', 'Invalid ICO'
print('Favicon valid binary ICO')
"
```
