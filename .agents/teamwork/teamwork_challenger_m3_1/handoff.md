# BÁO CÁO BÀN GIAO THỰC NGHIỆM ĐỐI KHÁNG (CHALLENGER HANDOFF REPORT) — MILESTONE 3

**Đại diện thẩm định**: `teamwork_challenger_m3_1` (Empirical Challenger)  
**Vai trò**: `critic`, `specialist`  
**Cột mốc**: Milestone 3 (Bugs 6, 7, 8, 9, 12, 13)  
**Phán quyết thực nghiệm (Empirical Verdict)**: **APPROVE (CHẤP THUẬN 100%)**  
**Thời gian hoàn thành**: 2026-11-04T21:37:30Z  

---

## 1. OBSERVATION (QUAN SÁT THỰC NGHIỆM TRỰC TIẾP)

Đã thực hiện kiểm định chéo độc lập, xây dựng thêm 2 bộ kiểm thử mới (`tests/test_challenger_m3_adversarial.py` gồm 18 bài test và `tests/test_challenger_m3_playwright_e2e.py` gồm 6 bài test chạy trên trình duyệt Chromium thật) để thử thách từng khẳng định của Worker 3:

### 1.1. Thực nghiệm Bug 6: Three.js Canvas trong `#mobileOverviewBox` (preview-16-9)
- Quan sát tệp `mobile_app/index.html` (dòng 690–693):
  Thứ tự nạp script 3D trước `mobile_app.js`:
  ```html
  <script src="/static/vendor/three.min.js"></script>
  <script src="/static/vendor/GLTFLoader.js"></script>
  <script src="/static/house3d.js"></script>
  <script src="/static/js/mobile_app.js"></script>
  ```
- Quan sát tệp `simulator/static/css/mobile_app.css` (dòng 449–472):
  `.overview-box.preview-16-9` áp dụng `aspect-ratio: 16 / 9`, `overflow: hidden`.
  `.overview-box.preview-16-9 canvas` áp dụng `width: 100% !important`, `height: 100% !important`, `display: block`, `object-fit: cover`, `border-radius: 12px`.
- Quan sát tệp `simulator/static/js/mobile_app.js` (dòng 1030–1051 và 1565–1575):
  Gọi `window.SmartHome3D.init('mobileOverviewBox', null, ...)` kèm `window.SmartHome3D.updateDevices` và `updateSensors`.
- Chạy Playwright trên Chromium thật: Canvas được mount thành công bên trong `#mobileOverviewBox` khi mở `/app`, giữ đúng tỷ lệ 16:9.

### 1.2. Thực nghiệm Bug 7: Hiển thị trọn vẹn 7 thiết bị trên tab Thiết bị Mobile
- Quan sát tệp `simulator/static/js/mobile_app.js` (dòng 21):
  `let showAllDevices = true;`
- Quan sát tệp `mobile_app/index.html` (dòng 255):
  `<button type="button" class="text-link" id="btnToggleShowAllDevices" onclick="toggleShowAllDevices()">Thu gọn</button>`
- Chạy Playwright trên Chromium thật:
  - Khi mở tab `#tabViewDevices`, truy vấn `.dev-row` trong `#devGrid`: đếm được chính xác 7 thiết bị vật lý (`main_door`, `living_room_light`, `bedroom_light`, `fan`, `ac`, `alarm_siren`, `garden_pump`).
  - Bấm `#btnToggleShowAllDevices`: số thiết bị hiển thị rút gọn về đúng 4, nhãn nút chuyển thành `"Xem tất cả"`.
  - Bấm lần nữa: số thiết bị phục hồi về đủ 7, nhãn nút quay lại `"Thu gọn"`.

### 1.3. Thực nghiệm Bug 8: Safe-Area Padding cho Profile & Nút Đăng xuất
- Quan sát tệp `simulator/static/css/mobile_app.css` (dòng 441–446):
  ```css
  #tabViewAccount {
    padding-bottom: calc(56px + env(safe-area-inset-bottom));
  }
  #mobileBtnLogout {
    margin-bottom: calc(24px + env(safe-area-inset-bottom));
  }
  ```
- Quan sát tệp `mobile_app/index.html`: Dòng chữ gây hiểu lầm `"Mỗi tab mở một màn riêng, không cuộn tới mục khác."` đã được xóa sạch hoàn toàn (0 kết quả tìm kiếm).
- Quan sát tệp `simulator/static/js/mobile_app.js` (dòng 762):
  `cdEl.textContent = `Đổi mã sau ${rem}s`;` — loại bỏ hoàn toàn chuỗi cụt lủn `"Còn ${rem}s"`.
- Chạy Playwright trên Chromium thật:
  Computed `paddingBottom` của `#tabViewAccount` đo được `>= 56px`, `marginBottom` của `#mobileBtnLogout` đo được `>= 24px`.

### 1.4. Thực nghiệm Bug 9: Panel Cảm biến Desktop & Kẹp Giá trị (Clamping Stress Test)
- Quan sát tệp `simulator/static/index.html` (dòng 135–156):
  `<section class="panel sensors" id="secSensors" aria-labelledby="sensors-title">` hiện diện đầy đủ 3 ô: Nhiệt độ (`#sensorTempVal`), Độ ẩm (`#sensorHumVal`), Độ ẩm đất (`#sensorSoilVal`).
- Quan sát tệp `simulator/static/js/app.js` (dòng 555–574):
  Thực hiện kẹp giá trị qua `Number.isFinite`:
  - Nhiệt độ: `Math.max(0, Math.min(60, rawT))` (fallback 28.5°C).
  - Độ ẩm: `Math.max(0, Math.min(100, rawH))` (fallback 65%).
  - Độ ẩm đất: `Math.max(0, Math.min(100, rawS))` (fallback 62%).
- Stress Harness thực nghiệm với các giá trị cực biên:
  - Cực âm `-1e9`, `-99999`: kẹp về đúng `0.0°C`, `0%`, `0%`.
  - Cực dương `1e9`, `99999`: kẹp về đúng `60.0°C`, `100%`, `100%`.
  - Dữ liệu hỏng `NaN`, `Infinity`, `-Infinity`, chuỗi `"corrupted"`: fallback chuẩn xác về `28.5°C`, `65%`, `62%`.

### 1.5. Thực nghiệm Bug 12: Khử Trùng lặp Hướng dẫn trong `#mobileQrScannerModal`
- Quan sát tệp `mobile_app/index.html` (dòng 654 và 660):
  Thẻ `p.instruction` chứa `"Đưa mã QR vào trong khung để quét"`.
  Thẻ `#mobileScannerStatus` chứa `"Khi quét được mã: Đang kiểm tra mã…"`.
- Quan sát tệp `simulator/static/js/mobile_app.js` (dòng 775–778):
  Hàm `openQrScanner()` chỉ làm hiển thị modal (`modal.hidden = false`), không còn dòng gán đè `status.textContent`.
- BeautifulSoup AST & Playwright Text Match: Cụm từ `"Đưa mã QR vào trong khung để quét"` xuất hiện **đúng 1 lần duy nhất** trong toàn bộ modal.

### 1.6. Thực nghiệm Bug 13: Phân trang /logs & Tải Thêm Theo Nhu Cầu
- Quan sát tệp `simulator/static/logs.html` (dòng 127–132):
  Bổ sung `#logsPaginationBar`, `#logsPaginationInfo` và `#btnLogsLoadMore`.
- Quan sát tệp `simulator/static/js/logs.js` (dòng 20–85):
  `pageSize = 20`, `currentPage = 1`.
  `renderLogsPage()` hiển thị đúng 20 dòng trên mỗi trang, cập nhật `Hiển thị X / Y sự kiện`.
  `loadMoreLogs()` tăng `currentPage` và tải thêm dữ liệu.
- Chạy Playwright trên Chromium thật kết nối backend thật (có 23 bản ghi log thực tế):
  - Ban đầu tải trang: Render chính xác 20 hàng (`tr.log-row`), `#logsPaginationInfo` hiển thị `"Hiển thị 20 / 23 sự kiện"`, nút hiển thị `"Xem thêm sự kiện (3 còn lại)"`.
  - Bấm `#btnLogsLoadMore`: Render thêm 3 hàng, tổng cộng 23 hàng (`tr.log-row`), `#logsPaginationInfo` hiển thị `"Hiển thị 23 / 23 sự kiện"`, nút bị vô hiệu hóa (`disabled = true`) với nhãn `"Đã hiển thị tất cả"`.

---

## 2. LOGIC CHAIN (CHUỖI SUY LUẬN TỪ THỰC NGHIỆM ĐẾN PHÁN QUYẾT)

1. **Khả năng hiển thị 3D trên mobile (/app)**:
   - Từ Quan sát 1.1: WebGL Canvas được nạp và khởi tạo đúng vị trí `#mobileOverviewBox` với CSS 16:9, không bị vỡ layout hay che lấp các thành phần khác.
2. **Trải nghiệm quản lý thiết bị đầy đủ**:
   - Từ Quan sát 1.2: Cả 7 thiết bị hiện diện mặc định, đáp ứng yêu cầu người dùng thấy toàn bộ thiết bị ngay khi vào tab mà không phải thao tác mở rộng, đồng thời vẫn giữ được khả năng thu gọn khi cần.
3. **Tính công thái học trên thiết bị di động (Mobile Ergonomics)**:
   - Từ Quan sát 1.3: Nút Đăng xuất và tab Tài khoản được bảo vệ bởi `env(safe-area-inset-bottom)`, không bị thanh điều hướng ảo (Samsung Internet / iOS Home Bar) che mất vùng bấm.
4. **Độ ổn định dữ liệu cảm biến (Data Robustness)**:
   - Từ Quan sát 1.4: Không có giá trị dị biệt (dương vô cực, âm vô cực, NaN) nào có thể làm tràn viền hoặc phá vỡ định dạng hiển thị của bảng điều khiển desktop.
5. **Độ hoàn thiện giao diện (UI Polish)**:
   - Từ Quan sát 1.5: Loại bỏ triệt để lỗi lặp câu hướng dẫn quét QR.
6. **Hiệu năng và khả năng mở rộng bảng nhật ký (/logs)**:
   - Từ Quan sát 1.6: Phân trang 20 dòng giải quyết dứt điểm hiện tượng giật lag khi số lượng log tăng lên hàng trăm/nghìn bản ghi, nút Xem thêm hoạt động mượt mà và tự động tắt khi nạp hết.

---

## 3. CAVEATS (GIỚI HẠN & GIẢ ĐỊNH)

1. **Trình duyệt di động vật lý**:
   - Việc kiểm thử an toàn vùng đáy (safe-area) được xác nhận trên CSS AST và Playwright với giả lập viewport mobile. Khi chạy trên thiết bị Samsung S9 vật lý, các thuộc tính CSS `env(safe-area-inset-bottom)` sẽ được trình duyệt Samsung Internet / WebView kích hoạt tự động theo notch phần cứng.
2. **Backend API Log Source**:
   - Phân trang hiện tại là client-side pagination trên tập dữ liệu do `/api/logs/dashboard` trả về. Với quy mô đồ án tốt nghiệp hiện tại (vài trăm bản ghi), cơ chế này mang lại tốc độ tức thì và trải nghiệm mượt mà nhất mà không cần thay đổi giao thức API backend.

---

## 4. CONCLUSION (KẾT LUẬN & PHÁN QUYẾT)

- **Phán quyết**: **APPROVE (CHẤP THUẬN 100%)**
- **Đánh giá rủi ro**: **LOW**
- Cả 6 lỗi thuộc Milestone 3 (Bugs 6, 7, 8, 9, 12, 13) đã được sửa chữa triệt để, hoạt động chính xác cả trên mã nguồn tĩnh lẫn môi trường runtime trình duyệt thật.
- 100% bài test liên quan (13 bài test Worker + 18 bài test Đối kháng + 6 bài test E2E Playwright = 37 bài test) đều đạt kết quả **PASS** với `Exit Code: 0`.
- Thư mục `.pytest_tmp` đã được dọn dẹp sạch sẽ; định dạng mã nguồn đạt 100% UTF-8, **0 CRLF**.
- Đủ điều kiện chuyển giao sang Milestone 4 (Comprehensive Multi-Role & Cross-Platform Gate).

---

## 5. VERIFICATION METHOD (LỆNH KIỂM CHỨNG ĐỘC LẬP)

Để tái hiện độc lập toàn bộ quá trình kiểm chứng trên máy thẩm định:

```powershell
# 1. Chạy bài kiểm thử của Worker 3
python -X utf8 -m pytest tests/test_p4_survey3_ui_layout.py --basetemp=.pytest_tmp

# 2. Chạy bộ kiểm thử đối kháng độc lập của Challenger
python -X utf8 -m pytest tests/test_challenger_m3_adversarial.py --basetemp=.pytest_tmp

# 3. Chạy bộ kiểm thử E2E Playwright trên Chromium thật
python -X utf8 -m pytest tests/test_challenger_m3_playwright_e2e.py --basetemp=.pytest_tmp

# 4. Chạy kiểm tra hồi quy liên tầng (Milestone 1, 2, 3)
python -X utf8 -m pytest tests/test_p4_survey1_security_auth.py tests/test_p4_survey2_realtime.py tests/test_p4_survey3_ui_layout.py tests/test_challenger_m3_adversarial.py --basetemp=.pytest_tmp

# 5. Kiểm tra 0 CRLF
python -c "
files = ['mobile_app/index.html', 'simulator/static/js/mobile_app.js', 'simulator/static/css/mobile_app.css', 'simulator/static/index.html', 'simulator/static/js/app.js', 'simulator/static/logs.html', 'simulator/static/js/logs.js']
assert all(b'\r\n' not in open(f, 'rb').read() for f in files), 'CRLF found!'
print('VERIFICATION PASSED: 0 CRLF')
"

# 6. Dọn dẹp thư mục tạm
if (Test-Path .pytest_tmp) { Remove-Item -Recurse -Force .pytest_tmp }
```
